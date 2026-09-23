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

from .models import (BEREDSKAP_NAVN, Kjennetegn, Konserttype, Programbehov, Programpost,
                     Tavleplassering)
from .services import Ugyldig

#: Lengre enn dette er nesten sikkert en skrivefeil i klokkeslettet. Et fast
#: behov — inngangen hele dagen — er det lengste som gir mening.
MAKS_LENGDE = timedelta(hours=24)

#: Mer enn dette av én gruppe på én konsert er en skrivefeil, ikke en plan.
MAKS_ANTALL = 99

MAKS_NAVN = 120


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


@transaction.atomic
def lagre_post(vakt, data: dict, *, fra, til, bruker, post=None) -> Programpost:
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
    return post


def slett_post(post) -> None:
    """Slett en konsert. Et lag som fulgte den, har ingen planlagt slutt
    lenger — `folger` settes til tom av basen."""
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
