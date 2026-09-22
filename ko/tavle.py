"""KO-tavla — hvor lagene står, og hvor de har vært (André, 22. sep. 2026).

Tavla på veggen i KO digitalt: lokasjonene som rader, tida som kolonner, og
lagene plassert i rutene. Skissene ble avtalt før koden (Artifact «KO-tavla —
skisser»); svarene står i `TODO.md` og CHANGELOG.

**Hva tavla eier, og hva den bare viser.** Den eier én ting: plasseringene
(`Tavleplassering`) — hvor en *ledig* ressurs står. Alt annet er projeksjon:

| Hva | Kilde |
|---|---|
| Hvem som er på vakt | Vaktlista — `ressurser_paa_vakt_naa` for lagene, `Ressurs.enhet` + `pa_vakt` for bilene |
| Hvem som er opptatt, og hvor | Hendelsene (`HendelseLag` på en åpen hendelse) og oppdragene (`enhet_status`) |
| Radene | Oppdragsmodulens lokasjoner, pluss den faste Pause-raden |
| Filteret | Vaktlistas ressursgrupper |

**Opptatt har forrang** (André: «hendelser og oppdrag tar prioritet»). En
ressurs på en hendelse eller et oppdrag kan ikke plasseres, og når laget går
på en hendelse, lukkes plasseringen. Tida på hendelsen skrives som en lukket
rad med `hendelse_nummer` når laget går av eller hendelsen lukkes — så
«Besøk» teller den — og laget står **uten plass**.

`ko` → `vaktliste` og `ko` → `oppdrag` er de tillatte retningene; ingen av
dem kjenner tavla.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import HENDELSE_APEN, HendelseLag, Tavleplassering
from .services import Ugyldig, systemlinje

#: Statusene der en bil er **opptatt** på et oppdrag. `Venter` (tildelt) er
#: ikke med: bilen står der den står til den rykker ut, og kan fortsatt
#: flyttes på tavla.
OPPTATT_STATUSER = frozenset({'rykker_ut', 'fremme', 'avreist', 'leverer', 'behandlet'})

#: Statusene der bilen hører hjemme **på oppdragets lokasjon** på tavla. Fra
#: Avreist er hun på vei bort med en pasient, og oppdragets lokasjon er ikke
#: lenger der hun er — da står hun blant de opptatte uten rad.
PAA_OPPDRAGETS_STED = frozenset({'rykker_ut', 'fremme', 'behandlet'})


def _navn(bruker) -> str:
    return getattr(bruker, 'username', '') or ''


def _bruker(bruker):
    return bruker if bruker is not None and getattr(bruker, 'is_authenticated', False) else None


# ── Hvem som er på tavla ──────────────────────────────────────────────────────

def ressurser_paa_tavla(naa=None, *, med_biler=True):
    """Ressursene tavla viser: lagene med et skift som dekker nå, og bilene som
    er på vakt. Samme regel som ressursoversikten — en ressurs man kan se der,
    skal man kunne se her.

    Bilene er vaktlistas ressurser **med** oppdragsenhet, og de er på vakt når
    enheten er det (`Enhet.pa_vakt`): «bilene styres ikke herfra; de skrus av
    og på av KO» (`vaktliste.services.ressurser_paa_vakt_naa`). En bil uten
    ressurs i vaktlista har ingen gruppe å filtrere på, og står ikke på tavla.
    """
    from django.db.models import Q

    from vaktliste.models import Ressurs
    from vaktliste.services import ressurser_paa_vakt_naa, vaktliste_i_bruk

    liste = vaktliste_i_bruk()
    if liste is None:
        return []
    utvalg = Q(pk__in=ressurser_paa_vakt_naa(liste, naa).values('pk'))
    if med_biler:
        utvalg |= Q(vaktliste=liste, enhet__isnull=False, enhet__pa_vakt=True,
                    enhet__er_aktiv=True)
    return list(Ressurs.objects.filter(utvalg)
                .select_related('gruppe', 'enhet')
                .order_by('gruppe__rekkefolge', 'gruppe__navn', 'rekkefolge', 'navn'))


def opptatt(ressurser, vakt) -> dict:
    """``{ressurs_id: {merke, tekst, lokasjon_id, fra}}`` for ressursene som er
    opptatt — på en åpen hendelse, eller på et oppdrag.

    **Utledet ved hver lesing, aldri lagret**: hendelsen og oppdraget er
    kildene, og en kopi her ville gått i utakt første gang noe feilet halvveis
    (samme regel som `oppdrag.services.enhet_status`).
    """
    from oppdrag.models import Statusmelding
    from oppdrag.services import enhet_status

    ut: dict = {}
    lag_ider = [r.pk for r in ressurser if r.enhet_id is None]
    for rad in (HendelseLag.objects
                .filter(ressurs_id__in=lag_ider, hendelse__vakt=vakt,
                        hendelse__status=HENDELSE_APEN)
                .select_related('hendelse')):
        h = rad.hendelse
        merke = f'På H{h.hendelsesnummer}'
        ut[rad.ressurs_id] = {
            'merke': merke,
            'tekst': ' · '.join(d for d in (merke, h.lokasjon_navn) if d),
            'lokasjon_id': h.lokasjon_id,
            'fra': rad.fra,
            'hendelse_id': h.pk,
        }
    # Bilene er med når de er blant `ressurser` — det er `ressurser_paa_tavla`
    # sin `med_biler` som bestemmer, ett sted.
    for r in ressurser:
        if r.enhet_id is None or r.pk in ut:
            continue
        info = enhet_status(r.enhet, vakt)
        kobling = info['koblingsrad']
        if kobling is None or info['status'] not in OPPTATT_STATUSER:
            continue
        o = info['aktivt_oppdrag']
        merke = f'O{o.oppdragsnummer} {info["status_navn"]}'
        # Fra da hun rykket ut, ikke fra siste status: det er da hun forlot
        # plassen på tavla.
        ut_melding = Statusmelding.objects.gjeldende_for_status(o, 'rykker_ut', oppdragsenhet=kobling)
        ut[r.pk] = {
            'merke': merke,
            'tekst': ' · '.join(d for d in (merke, getattr(o.lokasjon, 'navn', '')) if d),
            'lokasjon_id': o.lokasjon_id if info['status'] in PAA_OPPDRAGETS_STED else None,
            'fra': ut_melding.tidspunkt if ut_melding else kobling.updated_at,
            'oppdrag_id': o.pk,
        }
    return ut


def aapen(ressurs):
    """Plasseringen ressursen står på nå, eller ``None``."""
    return Tavleplassering.objects.filter(ressurs=ressurs, til__isnull=True).first()


# ── Å flytte ──────────────────────────────────────────────────────────────────

def _stedsnavn(plassering) -> str:
    if plassering is None:
        return ''
    return 'Pause' if plassering.pause else plassering.lokasjon_navn


@transaction.atomic
def plasser(vakt, ressurs, *, bruker, lokasjon=None, pause=False, naa=None) -> Tavleplassering:
    """Sett en **ledig** ressurs på en lokasjon, eller i pause, fra **nå**.

    Den forrige plasseringen lukkes i samme transaksjon — tavla får aldri et
    lag på to steder, og basen sier det samme (`en_aapen_tavleplassering_per_
    ressurs`). Til samme sted igjen er en feil og ikke en ny rad: ellers
    teller «Besøk» ett besøk som to.
    """
    naa = naa or timezone.now()
    if (lokasjon is None) == (not pause):
        raise Ugyldig('Velg én lokasjon, eller pause.')
    if lokasjon is not None and not lokasjon.er_aktiv:
        raise Ugyldig('Lokasjonen er ikke aktiv.')
    if ressurs.pk not in {r.pk for r in ressurser_paa_tavla(naa)}:
        raise Ugyldig(f'{ressurs.navn} er ikke på vakt nå.')
    if ressurs.pk in opptatt([ressurs], vakt):
        raise Ugyldig(f'{ressurs.navn} er på en hendelse eller et oppdrag, og kan ikke '
                      'plasseres før det er ferdig.')
    forrige = (Tavleplassering.objects.select_for_update()
               .filter(ressurs=ressurs, til__isnull=True).first())
    if forrige is not None and forrige.pause == pause and forrige.lokasjon_id == getattr(lokasjon, 'pk', None):
        raise Ugyldig(f'{ressurs.navn} står der alt.')
    if forrige is not None:
        forrige.til = naa
        forrige.save(update_fields=['til'])
    try:
        with transaction.atomic():
            ny = Tavleplassering.objects.create(
                vakt=vakt, ressurs=ressurs, ressurs_navn=ressurs.navn,
                lokasjon=lokasjon, lokasjon_navn=getattr(lokasjon, 'navn', '') or '',
                pause=pause, fra=naa, av=_bruker(bruker), av_navn=_navn(bruker))
    except IntegrityError:
        # En annen operatør flyttet det samme laget i samme øyeblikk.
        raise Ugyldig(f'{ressurs.navn} ble flyttet av noen andre. Prøv igjen.')
    _logg(vakt, ressurs.navn, til=_stedsnavn(ny), fra=_stedsnavn(forrige),
          naa=naa, bruker=bruker)
    return ny


@transaction.atomic
def avslutt(vakt, ressurs, *, bruker, naa=None) -> Tavleplassering:
    """Ta ressursen av tavla: plasseringen lukkes nå, og den står **uten
    plass**. Det er det «Uten plass»-kolonnen er når man drar et lag dit."""
    naa = naa or timezone.now()
    forrige = (Tavleplassering.objects.select_for_update()
               .filter(ressurs=ressurs, til__isnull=True).first())
    if forrige is None:
        raise Ugyldig(f'{ressurs.navn} står alt uten plass.')
    forrige.til = naa
    forrige.save(update_fields=['til'])
    _logg(vakt, ressurs.navn, til='', fra=_stedsnavn(forrige), naa=naa, bruker=bruker)
    return forrige


def _logg(vakt, navn, *, til, fra, naa, bruker):
    from . import systemlinjer
    systemlinje(vakt, systemlinjer.TAVLE_FLYTTET,
                {'ressurs': navn, 'til': til, 'fra': fra}, tidspunkt=naa, bruker=bruker)


# ── Hendelsene har forrang ────────────────────────────────────────────────────

def avslutt_for_hendelse(ressurs_id, naa) -> None:
    """Laget gikk på en hendelse: plasseringen lukkes, uten egen logglinje —
    «Lag 3 registrert på H14» står alt. Kalles fra `services.sett_lag`."""
    Tavleplassering.objects.filter(
        ressurs_id=ressurs_id, til__isnull=True).update(til=naa)


def skriv_hendelsestid(rad: HendelseLag, til) -> None:
    """Tida laget sto på hendelsen, som en lukket rad på tavla — så «Besøk»
    teller den, og tavla viser den som historikk. Kalles når laget går av
    hendelsen og når hendelsen lukkes. Uten lokasjon på hendelsen finnes ingen
    rad å skrive den i, og da skrives den ikke."""
    h = rad.hendelse
    if h.lokasjon_id is None or til is None:
        return
    # En hendelse som ble lukket, åpnet igjen og lukket på nytt har alt en
    # rad for første del. Den nye begynner der den forrige sluttet.
    fra = rad.fra
    tidligere = (Tavleplassering.objects
                 .filter(vakt=h.vakt, ressurs_id=rad.ressurs_id,
                         hendelse_nummer=h.hendelsesnummer, til__isnull=False)
                 .order_by('-til').first())
    if tidligere is not None and tidligere.til > fra:
        fra = tidligere.til
    if til <= fra:
        return
    Tavleplassering.objects.create(
        vakt=h.vakt, ressurs_id=rad.ressurs_id, ressurs_navn=rad.ressurs_navn,
        lokasjon_id=h.lokasjon_id, lokasjon_navn=h.lokasjon_navn,
        hendelse_nummer=h.hendelsesnummer, fra=fra, til=til,
        av=rad.av, av_navn=rad.av_navn)


# ── Det klienten får ──────────────────────────────────────────────────────────

#: Hvor lenge tidslinja strekker seg, i timer. Admininnstilling i steg 2.
STANDARD_TIMER = 12


def _iso(t):
    return t.isoformat() if t else None


def tavle_data(vakt, naa=None, *, med_biler=True) -> dict:
    """Alt tavla trenger, i ett svar som polles.

    **Hele vaktas plasseringer følger med**, ikke bare vinduets: «Ikke vært på
    Parkscene» og «Besøk» teller hele vakta, og det er noen hundre rader.
    """
    from oppdrag.models import Lokasjon

    naa = naa or timezone.now()
    ressurser = ressurser_paa_tavla(naa, med_biler=med_biler)
    travle = opptatt(ressurser, vakt)
    grupper = {}
    for r in ressurser:
        if r.gruppe_id not in grupper:
            grupper[r.gruppe_id] = {'id': r.gruppe_id, 'navn': r.gruppe.navn,
                                    'ikon': r.gruppe.ikon or ''}
    plasseringer = list(Tavleplassering.objects.filter(vakt=vakt).order_by('fra', 'id'))
    return {
        'naa': naa.isoformat(),
        'timer': STANDARD_TIMER,
        'rader': [{'id': l.pk, 'navn': l.navn}
                  for l in Lokasjon.objects.filter(er_aktiv=True).order_by('rekkefolge', 'navn')],
        'grupper': list(grupper.values()),
        'ressurser': [{
            'id': r.pk,
            'navn': r.navn,
            'gruppe_id': r.gruppe_id,
            'bil': r.enhet_id is not None,
            'opptatt': ({k: (_iso(v) if k == 'fra' else v) for k, v in travle[r.pk].items()}
                        if r.pk in travle else None),
        } for r in ressurser],
        'plasseringer': [{
            'id': p.pk,
            'ressurs_id': p.ressurs_id,
            'ressurs_navn': p.ressurs_navn,
            'lokasjon_id': p.lokasjon_id,
            'lokasjon_navn': p.lokasjon_navn,
            'pause': p.pause,
            'hendelse_nummer': p.hendelse_nummer,
            'fra': _iso(p.fra),
            'til': _iso(p.til),
        } for p in plasseringer],
    }

