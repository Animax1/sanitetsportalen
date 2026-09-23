"""Programmet — konsertene og de faste behovene per sted (tavleplanleggeren,
steg 2, 23. sep. 2026).

Skissene og svarene står i Artifact «Tavleplanleggeren» og i CHANGELOG. Det
som ble avgjort før koden, og som reglene her holder:

| Regel | Hvorfor |
|---|---|
| **Typen setter ingen ressurser** | André: «Konserttyper skal ikke automatisk sette ressurser.» Behovet skrives inn for hånd på hver konsert |
| Beredskapsnivå grønn/gul/oransje/rød, eller tomt for et fast behov | «En standardisert form» (André). Ukjent verdi avvises, rettes ikke — som prioriteten på hendelsene |
| Behovet telles i **vaktlistas ressursgrupper** | «Spesiallag» er en egen gruppe der (André: «en fast type lag»). Da kan planleggeren sammenligne med skiftene, og tavla med plasseringene |
| Alt valideres før noe lagres, og behovet lagres i samme transaksjon | En konsert uten behovet sitt er et halvt svar som ser helt ut |
| Navnene ut av modulen fryses (sted, type, gruppe) | Programmet skal kunne leses år etter år, også når stedet er omdøpt |
| **KO-leder skriver**, alle med `les` i KO ser | André: «KO-leder», både før og under vakta |

`ko` → `oppdrag` (lokasjonen) og `ko` → `vaktliste` (ressursgruppa) er de
tillatte retningene; ingen av dem kjenner programmet.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction

from .models import (BEREDSKAP_NAVN, Kjennetegn, Konserttype, Programbehov, Programendring,
                     Programpost, Tavleplassering)
from .services import Ugyldig, systemlinje

#: Lengre enn dette er nesten sikkert en skrivefeil i klokkeslettet. Et fast
#: behov — inngangen hele dagen — er det lengste som gir mening.
MAKS_LENGDE = timedelta(hours=24)

#: Mer enn dette av én gruppe på én konsert er en skrivefeil, ikke en plan.
MAKS_ANTALL = 99

MAKS_NAVN = 120

#: En endring løftes inn i KO-loggen når konserten pågår eller begynner innen
#: dette — da er den situasjon, ikke planlegging (steg 5).
I_DRIFT_FORVARSEL = timedelta(hours=2)


def _navn(bruker) -> str:
    return getattr(bruker, 'username', '') or ''


def _bruker(bruker):
    return bruker if bruker is not None and getattr(bruker, 'is_authenticated', False) else None


def _heltall(raa, hva, *, tomt_er_none=False):
    if raa in (None, '') and tomt_er_none:
        return None
    if isinstance(raa, bool):
        raise Ugyldig(f'{hva} må være et tall.')
    try:
        verdi = int(raa)
    except (TypeError, ValueError):
        raise Ugyldig(f'{hva} må være et tall.')
    if verdi < 0:
        raise Ugyldig(f'{hva} kan ikke være negativt.')
    return verdi


def _behov(raa) -> list[tuple]:
    """``[(gruppe, antall), …]`` fra ``[{gruppe_id, antall}, …]``. Null er
    «ingen» og tas ut; samme gruppe to ganger er en feil — to linjer «Lag»
    ville bli lagt sammen eller den ene stille borte."""
    from vaktliste.models import Ressursgruppe

    if raa in (None, ''):
        return []
    if not isinstance(raa, list):
        raise Ugyldig('Behovet må være en liste.')
    ut, sett = [], set()
    for linje in raa:
        if not isinstance(linje, dict):
            raise Ugyldig('Behovet må være en liste med gruppe og antall.')
        gruppe_id = _heltall(linje.get('gruppe_id'), 'Ressursgruppe')
        antall = _heltall(linje.get('antall'), 'Antall')
        if antall == 0:
            continue
        if antall > MAKS_ANTALL:
            raise Ugyldig(f'Mer enn {MAKS_ANTALL} av én gruppe er ikke en plan.')
        if gruppe_id in sett:
            raise Ugyldig('Samme ressursgruppe står to ganger i behovet.')
        gruppe = Ressursgruppe.objects.filter(pk=gruppe_id, er_aktiv=True).first()
        if gruppe is None:
            raise Ugyldig('Ukjent eller inaktiv ressursgruppe i behovet.')
        sett.add(gruppe_id)
        ut.append((gruppe, antall))
    return ut


def _kjennetegn(raa) -> list:
    if raa in (None, ''):
        return []
    if not isinstance(raa, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in raa):
        raise Ugyldig('Kjennetegnene må være en liste med tall.')
    ider = set(raa)
    rader = list(Kjennetegn.objects.filter(pk__in=ider))
    if len(rader) != len(ider):
        raise Ugyldig('Ukjent kjennetegn — hent lista på nytt.')
    return rader


# ── Endringene (steg 5) ───────────────────────────────────────────────────────

#: Feltene i bildet, i den rekkefølgen en endring leses. Navnet er det man
#: sier; resten er det som kan endre seg under vakta.
BILDE_FELT = (('navn', 'navn'), ('sted', 'sted'), ('tid', 'tid'), ('type', 'type'),
              ('beredskap', 'beredskap'), ('publikum', 'publikum'), ('kjennetegn', 'kjennetegn'),
              ('behov', 'behov'))


def _tid(fra, til) -> str:
    """«25.09 22:00–00:30». **Med dato**: flyttes konserten til neste døgn på
    samme klokkeslett, er det en endring — uten datoen hadde historikken ikke
    sett den."""
    from django.utils import timezone
    return f'{timezone.localtime(fra):%d.%m %H:%M}–{timezone.localtime(til):%H:%M}'


def bilde(post) -> dict:
    """Konserten som lesbar tekst, felt for felt — det som lagres i
    historikken og sammenlignes ved hver endring. Tekst, ikke pekere: bildet
    skal kunne leses også når typen eller gruppa er borte."""
    return {
        'navn': post.navn,
        'sted': post.lokasjon_navn,
        'tid': _tid(post.fra, post.til),
        'type': post.konserttype_navn,
        'beredskap': BEREDSKAP_NAVN.get(post.beredskap, ''),
        'publikum': str(post.publikum) if post.publikum is not None else '',
        'kjennetegn': ', '.join(sorted(k.navn for k in post.kjennetegn.all())),
        'behov': ', '.join(f'{b.antall} {b.gruppe_navn}' for b in post.behov.order_by('gruppe_navn')),
    }


def forskjell(foer: dict, etter: dict) -> list[dict]:
    """Feltene som endret seg, som `[{felt, fra, til}]`, i lesefølge."""
    return [{'felt': navn, 'fra': foer.get(felt, ''), 'til': etter.get(felt, '')}
            for felt, navn in BILDE_FELT if foer.get(felt, '') != etter.get(felt, '')]


def i_drift(post_fra, post_til, naa) -> bool:
    """Pågår konserten, eller begynner den innen forvarselet?"""
    return post_fra - I_DRIFT_FORVARSEL <= naa < post_til


def _loggfor(post, hva, detaljer, *, bruker, naa, i_drift_naa, vakt=None):
    """Historikken alltid; KO-loggen bare når det gjelder noe som skjer nå."""
    from . import systemlinjer
    vakt = vakt or post.vakt
    Programendring.objects.create(
        vakt=vakt, post=post if hva != Programendring.SLETTET else None, post_navn=post.navn,
        hva=hva, detaljer=detaljer, tidspunkt=naa, av=_bruker(bruker), av_navn=_navn(bruker))
    if not i_drift_naa:
        return
    data = {'hva': hva, 'navn': post.navn, 'sted': post.lokasjon_navn}
    if hva == Programendring.OPPRETTET:
        data.update({'tid': detaljer.get('tid', ''),
                     'beredskap': f'beredskap {detaljer["beredskap"].lower()}' if detaljer.get('beredskap') else ''})
    elif hva == Programendring.ENDRET:
        data['endringer'] = detaljer
    systemlinje(vakt, systemlinjer.PROGRAM_ENDRET, data, tidspunkt=naa, bruker=bruker)


@transaction.atomic
def lagre_post(vakt, data: dict, *, fra, til, bruker, post=None, naa=None) -> Programpost:
    """Ny konsert, eller `post` endret. `fra`/`til` er tolket av viewet.

    **Alt valideres før noe skrives.** En inaktiv type eller et inaktivt sted
    avvises på en *ny* post, men en post som alt har dem, beholder dem ved
    endring — samme regel som en deaktivert problemstilling på et oppdrag.
    """
    from oppdrag.models import Lokasjon

    navn = str(data.get('navn') or '').strip()
    if not navn:
        raise Ugyldig('Konserten må ha et navn.')
    if len(navn) > MAKS_NAVN:
        raise Ugyldig(f'Navnet er for langt (maks {MAKS_NAVN} tegn).')
    if til <= fra:
        raise Ugyldig('«Til» må være etter «fra».')
    if til - fra > MAKS_LENGDE:
        raise Ugyldig('En programpost kan ikke vare mer enn et døgn.')

    lokasjon_id = _heltall(data.get('lokasjon_id'), 'Sted')
    lokasjon = Lokasjon.objects.filter(pk=lokasjon_id).first()
    if lokasjon is None:
        raise Ugyldig('Ukjent sted.')
    if not lokasjon.er_aktiv and (post is None or post.lokasjon_id != lokasjon.pk):
        raise Ugyldig('Stedet er ikke aktivt.')

    type_id = _heltall(data.get('konserttype_id'), 'Konserttype', tomt_er_none=True)
    konserttype = None
    if type_id is not None:
        konserttype = Konserttype.objects.filter(pk=type_id).first()
        if konserttype is None:
            raise Ugyldig('Ukjent konserttype.')
        if not konserttype.er_aktiv and (post is None or post.konserttype_id != konserttype.pk):
            raise Ugyldig('Konserttypen er ikke aktiv.')

    beredskap = str(data.get('beredskap') or '')
    if beredskap and beredskap not in BEREDSKAP_NAVN:
        raise Ugyldig('Ukjent beredskapsnivå — bruk grønn, gul, oransje eller rød.')

    publikum = _heltall(data.get('publikum'), 'Forventet publikum', tomt_er_none=True)
    kjennetegn = _kjennetegn(data.get('kjennetegn'))
    behov = _behov(data.get('behov'))

    from django.utils import timezone
    naa = naa or timezone.now()
    ny = post is None
    foer = None if ny else bilde(post)
    var_i_drift = not ny and i_drift(post.fra, post.til, naa)
    if post is None:
        post = Programpost(vakt=vakt)
    post.lokasjon = lokasjon
    post.lokasjon_navn = lokasjon.navn
    post.navn = navn
    post.konserttype = konserttype
    post.konserttype_navn = konserttype.navn if konserttype else ''
    post.beredskap = beredskap
    post.fra, post.til = fra, til
    post.publikum = publikum
    post.endret_av = _bruker(bruker)
    post.endret_av_navn = _navn(bruker)
    post.save()
    post.kjennetegn.set(kjennetegn)
    # Behovet byttes ut i sin helhet — det er slik skjemaet sender det, og en
    # linje som ble tatt bort i skjemaet skal være borte.
    post.behov.all().delete()
    for gruppe, antall in behov:
        Programbehov.objects.create(post=post, gruppe=gruppe, gruppe_navn=gruppe.navn, antall=antall)
    etter = bilde(post)
    er_i_drift = var_i_drift or i_drift(post.fra, post.til, naa)
    if ny:
        _loggfor(post, Programendring.OPPRETTET, etter, bruker=bruker, naa=naa, i_drift_naa=er_i_drift)
    else:
        endret = forskjell(foer, etter)
        # En lagring uten endring er ingen endring — og ingen linje.
        if endret:
            _loggfor(post, Programendring.ENDRET, endret, bruker=bruker, naa=naa, i_drift_naa=er_i_drift)
    return post


@transaction.atomic
def slett_post(post, *, bruker=None, naa=None) -> None:
    """Slett en konsert. Et lag som fulgte den, har ingen planlagt slutt
    lenger — `folger` settes til tom av basen. Historikken står: slettingen
    er en rad med hele bildet, og de tidligere radene beholder navnet."""
    from django.utils import timezone
    naa = naa or timezone.now()
    _loggfor(post, Programendring.SLETTET, bilde(post), bruker=bruker, naa=naa,
             i_drift_naa=i_drift(post.fra, post.til, naa))
    post.delete()


def til_dict(post) -> dict:
    from .tavle import _iso
    return {
        'id': post.pk,
        'lokasjon_id': post.lokasjon_id,
        'lokasjon_navn': post.lokasjon_navn,
        'navn': post.navn,
        'konserttype_id': post.konserttype_id,
        'konserttype_navn': post.konserttype_navn,
        'beredskap': post.beredskap,
        'beredskap_navn': BEREDSKAP_NAVN.get(post.beredskap, ''),
        'fra': _iso(post.fra),
        'til': _iso(post.til),
        'publikum': post.publikum,
        'kjennetegn': [{'id': k.pk, 'navn': k.navn} for k in post.kjennetegn.all()],
        'behov': [{'gruppe_id': b.gruppe_id, 'gruppe_navn': b.gruppe_navn, 'antall': b.antall}
                  for b in post.behov.all()],
    }


def poster(vakt) -> list[dict]:
    return [til_dict(p) for p in (Programpost.objects.filter(vakt=vakt)
                                  .prefetch_related('kjennetegn', 'behov'))]


def program_data(vakt) -> dict:
    """Alt skjemaet og tavla trenger om programmet: postene, og valgene."""
    from oppdrag.models import Lokasjon
    from vaktliste.models import Ressursgruppe

    return {
        'vakt_id': vakt.pk,
        'poster': poster(vakt),
        # Stedene her og ikke fra sentralbordet: planleggeren skal virke for
        # den som har KO uten oppdragstilgang, og stedsnavnene er ikke oppdrag.
        'steder': [{'id': l.pk, 'navn': l.navn}
                   for l in Lokasjon.objects.filter(er_aktiv=True).order_by('rekkefolge', 'navn')],
        'konserttyper': [{'id': t.pk, 'navn': t.navn, 'er_aktiv': t.er_aktiv}
                         for t in Konserttype.objects.all()],
        'kjennetegn': [{'id': k.pk, 'navn': k.navn, 'er_aktiv': k.er_aktiv}
                       for k in Kjennetegn.objects.all()],
        'grupper': [{'id': g.pk, 'navn': g.navn}
                    for g in Ressursgruppe.objects.filter(er_aktiv=True).order_by('rekkefolge', 'navn')],
        'beredskap': [{'verdi': v, 'navn': n} for v, n in BEREDSKAP_NAVN.items()],
    }


def folg(plassering, post, *, naa) -> Tavleplassering:
    """«Følger konserten»: den åpne plasseringen slutter når `post` slutter.

    **Samme sted, samme vakt, og konserten er ikke over.** Å følge en konsert
    på et annet sted ville gitt en slutt som ikke har noe med laget å gjøre.
    """
    plassering = Tavleplassering.objects.select_for_update().get(pk=plassering.pk)
    if plassering.til is not None:
        raise Ugyldig('Plasseringen er avsluttet — en planlagt slutt gjelder der laget står nå.')
    if post.vakt_id != plassering.vakt_id or post.lokasjon_id is None \
            or post.lokasjon_id != plassering.lokasjon_id:
        raise Ugyldig('Laget kan bare følge en konsert på stedet det står.')
    if post.til <= naa:
        raise Ugyldig('Konserten er alt over.')
    plassering.folger = post
    plassering.planlagt_til = None
    plassering.save(update_fields=['folger', 'planlagt_til'])
    return plassering


#: Dekningsstripa (steg 4) teller midt i hver time: et skift som begynner
#: 22:15 dekker 22-timen, et som slutter 22:15 gjør det ikke.
MIDT_I_TIMEN = timedelta(minutes=30)


def dogn_start(dogn: str):
    """Døgnets start som et tidspunkt — `YYYY-MM-DD` og tavlas døgnstart, i
    portalens tidssone. `None` for noe som ikke er en dato."""
    from datetime import date, datetime, time

    from django.utils import timezone

    from .tavle import dognstart
    try:
        d = date.fromisoformat(str(dogn))
    except ValueError:
        return None
    t, m = (int(x) for x in dognstart().split(':'))
    return timezone.make_aware(datetime.combine(d, time(t, m)), timezone.get_current_timezone())


def paa_vakt_per_time(start) -> list[dict]:
    """Hvor mange av hver ressursgruppe vaktlista har på vakt, time for time
    i døgnet som begynner `start`. **Samme regel som resten av portalen**
    (`vaktliste.services.ressurser_med_skift`) — planleggeren skal ikke ha sin
    egen mening om hvem som er på vakt.

    Tjuefire spørringer, én per time: svaret hentes når planleggeren åpnes
    eller bytter døgn, ikke ved hver poll.
    """
    from django.db.models import Count

    from vaktliste.services import ressurser_med_skift, vaktliste_i_bruk

    liste = vaktliste_i_bruk()
    ut = []
    for i in range(24):
        fra = start + timedelta(hours=i)
        grupper = {}
        if liste is not None:
            grupper = {str(r['gruppe_id']): r['n'] for r in (
                ressurser_med_skift(liste, fra + MIDT_I_TIMEN)
                .values('gruppe_id').annotate(n=Count('pk')))}
        ut.append({'fra': fra.isoformat(), 'grupper': grupper})
    return ut


# ── Plan mot faktisk (steg 5) ─────────────────────────────────────────────────
#
# André: «det er egentlig kjempesmart. Og fint for videre år på samme
# arrangement å kunne se hva vi hadde på de konsertene og
# risikovurdering/beredskapsnivå.»

def _dekket(intervaller, fra, til, trengs):
    """Snittet av hvor mange som sto der i `[fra, til)`, og hvor lenge det var
    **færre enn** `trengs`. `intervaller` er `(start, slutt)` per ressurs, alt
    klippet til vinduet. Et feie over grensene — der antallet kan endre seg."""
    lengde = (til - fra).total_seconds()
    if lengde <= 0:
        return None, 0
    punkter = sorted({fra, til} | {a for a, _ in intervaller} | {b for _, b in intervaller})
    sum_tid, under = 0.0, 0.0
    for a, b in zip(punkter, punkter[1:]):
        n = sum(1 for s, e in intervaller if s <= a and e >= b)
        sek = (b - a).total_seconds()
        sum_tid += n * sek
        if n < trengs:
            under += sek
    return sum_tid / lengde, round(under / 60)


def _oppdrag_paa_stedet(post):
    """Oppdrag på stedet mens konserten pågikk — fra den levende tabellen, eller
    fra arkivet når vakta er arkivert. **`None` etter kollaps**: da finnes ikke
    radene lenger, og null ville vært en påstand, ikke et tall."""
    from oppdrag.models import ArkivertOppdrag, Oppdrag, OppdragArkiv

    arkiv = OppdragArkiv.objects.filter(vakt_id=post.vakt_id).order_by('-pk').first()
    if arkiv is None:
        if post.lokasjon_id is None:
            return None
        return Oppdrag.objects.filter(vakt_id=post.vakt_id, lokasjon_id=post.lokasjon_id,
                                      created_at__gte=post.fra, created_at__lt=post.til).count()
    if arkiv.kollapset_at:
        return None
    return (ArkivertOppdrag.objects.filter(arkiv=arkiv, lokasjon_navn=post.lokasjon_navn,
                                           opprettet_at__gte=post.fra, opprettet_at__lt=post.til)
            .values('oppdragsnummer').distinct().count())


def plan_mot_faktisk(vakt, naa=None) -> list[dict]:
    """Per konsert: behovet (nå og opprinnelig), hvor mange som i snitt sto
    der mens den pågikk, minuttene under behovet, oppdragene på stedet og hvor
    mange ganger den ble endret.

    «Sto der» er **tavlas plasseringer på stedet** — også tida på en hendelse
    der, som tavla skriver som historikk. Bilens tid på et oppdrag er ikke med
    (kjent grense, som i «Besøk»). En konsert som ikke har begynt har ikke noe
    faktisk ennå; en som pågår regnes fram til nå.
    """
    from django.utils import timezone

    naa = naa or timezone.now()
    poster = list(Programpost.objects.filter(vakt=vakt)
                  .prefetch_related('behov', 'endringer').order_by('fra', 'lokasjon_navn', 'id'))
    plasseringer = list(Tavleplassering.objects.filter(vakt=vakt, pause=False)
                        .select_related('ressurs__gruppe'))
    ut = []
    for post in poster:
        slutt = min(post.til, naa)
        startet = post.fra < naa
        historikk = list(post.endringer.all())
        opprinnelig = next((e.detaljer.get('behov', '') for e in historikk
                            if e.hva == Programendring.OPPRETTET and isinstance(e.detaljer, dict)), None)
        behov = []
        for b in post.behov.all():
            intervaller = []
            if startet:
                for p in plasseringer:
                    if p.lokasjon_id != post.lokasjon_id or p.ressurs is None:
                        continue
                    # På id, og på navnet når id-en er borte (en gjenopprettet
                    # backup stripper pekeren) — aldri «alle».
                    if b.gruppe_id and p.ressurs.gruppe_id != b.gruppe_id:
                        continue
                    if not b.gruppe_id and p.ressurs.gruppe.navn != b.gruppe_navn:
                        continue
                    a, e = max(p.fra, post.fra), min(p.til or naa, slutt)
                    if a < e:
                        intervaller.append((a, e))
            snitt, under = _dekket(intervaller, post.fra, slutt, b.antall) if startet else (None, 0)
            behov.append({'gruppe_navn': b.gruppe_navn, 'trengs': b.antall,
                          'snitt': round(snitt, 1) if snitt is not None else None, 'under_min': under})
        ut.append({
            'id': post.pk,
            'navn': post.navn,
            'sted': post.lokasjon_navn,
            'type': post.konserttype_navn,
            'tid': _tid(post.fra, post.til),
            'beredskap': post.beredskap,
            'beredskap_navn': BEREDSKAP_NAVN.get(post.beredskap, ''),
            'publikum': post.publikum,
            'behov': behov,
            'behov_opprinnelig': opprinnelig,
            'behov_naa': bilde(post)['behov'],
            'startet': startet,
            'oppdrag': _oppdrag_paa_stedet(post) if startet else None,
            'endringer': sum(1 for e in historikk if e.hva == Programendring.ENDRET),
        })
    return ut


def endringer(vakt) -> list[dict]:
    """Historikken for vakta, eldste først."""
    return [{'tidspunkt': e.tidspunkt.isoformat(), 'navn': e.post_navn, 'hva': e.hva,
             'hva_navn': e.get_hva_display(), 'detaljer': e.detaljer, 'av_navn': e.av_navn}
            for e in Programendring.objects.filter(vakt=vakt).order_by('tidspunkt', 'id')]


# ── Kopier programmet til en ny vakt (steg 5) ─────────────────────────────────

def _dogn_dato(t):
    """Døgnet et tidspunkt hører til, som dato — døgnstarten som på tavla."""
    from django.utils import timezone

    from .tavle import dognstart
    timer, minutter = (int(x) for x in dognstart().split(':'))
    return (timezone.localtime(t) - timedelta(hours=timer, minutes=minutter)).date()


@transaction.atomic
def kopier_program(fra_vakt, til_vakt, *, forste_dogn, bruker, naa=None) -> dict:
    """Programmet fra en tidligere vakt inn i `til_vakt`, **flyttet i hele
    døgn** så første konsertdøgn lander på `forste_dogn`. Klokkeslettene står.

    Hver konsert går gjennom `lagre_post` — samme validering og samme
    historikk som en lagt inn for hånd. Stedet og gruppene finnes på id, ellers
    på navnet; en konsert som ikke lar seg legge inn (stedet er borte, eller
    ugyldig av en annen grunn) hoppes over og **nevnes**, ikke stille borte.
    Samme tanke som «Kopier oppsett» i vaktlista: strukturen, ikke det som
    skjedde.
    """
    from oppdrag.models import Lokasjon
    from vaktliste.models import Ressursgruppe

    kilde = list(Programpost.objects.filter(vakt=fra_vakt).prefetch_related('behov', 'kjennetegn')
                 .order_by('fra', 'id'))
    if not kilde:
        raise Ugyldig('Vakta har ikke noe program å kopiere.')
    skift = timedelta(days=(forste_dogn - _dogn_dato(kilde[0].fra)).days)
    kopiert, hoppet_over = 0, []
    for post in kilde:
        lokasjon = (Lokasjon.objects.filter(pk=post.lokasjon_id, er_aktiv=True).first()
                    or Lokasjon.objects.filter(navn=post.lokasjon_navn, er_aktiv=True).first())
        if lokasjon is None:
            hoppet_over.append(f'{post.navn} — stedet «{post.lokasjon_navn}» finnes ikke lenger')
            continue
        behov = []
        for b in post.behov.all():
            gruppe = (Ressursgruppe.objects.filter(pk=b.gruppe_id, er_aktiv=True).first()
                      or Ressursgruppe.objects.filter(navn=b.gruppe_navn, er_aktiv=True).first())
            if gruppe is None:
                hoppet_over.append(f'{post.navn} — behovet for «{b.gruppe_navn}» er ikke med, gruppa finnes ikke')
            else:
                behov.append({'gruppe_id': gruppe.pk, 'antall': b.antall})
        data = {'lokasjon_id': lokasjon.pk, 'navn': post.navn,
                'konserttype_id': post.konserttype_id if post.konserttype and post.konserttype.er_aktiv else None,
                'beredskap': post.beredskap, 'publikum': post.publikum,
                'kjennetegn': [k.pk for k in post.kjennetegn.all() if k.er_aktiv], 'behov': behov}
        # `lagre_post` er selv atomisk — nøstet er det et lagringspunkt, så en
        # konsert som avvises tar ikke de andre med seg.
        try:
            lagre_post(til_vakt, data, fra=post.fra + skift, til=post.til + skift, bruker=bruker, naa=naa)
        except Ugyldig as e:
            hoppet_over.append(f'{post.navn} — {e}')
            continue
        kopiert += 1
    return {'kopiert': kopiert, 'hoppet_over': hoppet_over, 'dager': skift.days}
