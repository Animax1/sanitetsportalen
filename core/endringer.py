"""Endringsnummeret: ett tall per område som endres når noe i området endres
(24. sep. 2026).

Fanene spør om tallet ofte — tavla hvert 2,5 sekund — og henter hele bildet
bare når tallet er et annet enn sist. André etter samtalen om brukerflyten i
`/ko/`: to på tavla fordeler arbeidet muntlig, og da er 15 sekunder lenge å
vente på at kollegaens flytting skal vise seg. Skissen står i Artifact
«Tavlas endringsnummer».

**Rammeverk, ikke KO.** Oppdragslista er sentralbordets egen kode og deles med
`/oppdrag/`, og oppdragsmodulen får ikke kjenne KO. Derfor ligger telleren her,
og modulene melder inn sine områder — samme idiom som `core/driftstatus.py` og
`core/opprydding.py`. `core` kjenner ingen modul ved navn.

Å legge til et område:

1. ``registrer('navn', gate)`` fra ``apps.ready()``. ``gate(request)`` avgjør
   om brukeren får spørre — samme regel som endepunktet bak området. Et tall
   uten tilgang sendes aldri ut: det sier at noe har skjedd.
2. ``endret('navn')`` der området endres — i praksis fra signaler, så alle
   som skriver blir fanget, også de ingen har tenkt på.

**Tre valg som ser ut som detaljer:**

- **Etter commit, ikke ved lagring** (`transaction.on_commit`). Øker tallet
  før raden er synlig, henter fanen det gamle bildet, ser det nye tallet, og
  henter ikke igjen før neste endring. Bildet står da feil helt til
  sikkerhetsnettet slår inn.
- **Likhet, ikke størrelse.** Fanen spør om tallet er *annerledes*, ikke
  *større*. Forsvinner tallet — omstart med lokal cache, en tømt Redis —
  starter det på en ny verdi (`_ny_start`), og alle henter én gang. Et tall som
  startet på 1 igjen kunne truffet nøyaktig det en fane allerede hadde.
- **Aldri et unntak ut.** En cache som er nede skal ikke stoppe en stempling
  eller en flytting. Uten tall henter fanene på sikkerhetsnettet, som før.

**Per portal** (17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §4.14). Uten portalen
i nøkkelen hentet hver Brann-fane på nytt ved hver skriving i Landsskytter. Tallet
fanen får er to ledd, `<felles>.<portal>`: en endring i en forespørsel øker
portalens ledd, og en endring **uten** portal — klokka, en kommando, en global
tabell som bilene (`alle=True`) — øker det felles, så alle portalene henter. Å
hente én gang for mye koster en 200; å la være koster et bilde som står feil.

Tallet ligger i cachen: **Redis på vakt**, delt mellom workerne. Mellom vakter
er det én worker, og lokal cache holder. To workers uten Redis ville gitt hver
prosess sitt tall — fanene ville hentet for ofte, men aldri stått feil — og
server-status sier fra om den kombinasjonen (`driftsmodus`).
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

NOKKEL = 'endringer:{}'

_OMRADER: dict[str, Callable] = {}


def registrer(navn: str, gate: Callable) -> None:
    """Meld inn et område. Samme navn to ganger er en feil: to moduler som
    delte et område, ville sett hverandres endringer og ikke vist det."""
    if not navn or not callable(gate):
        raise ValueError('Et område trenger et navn og en gate.')
    if navn in _OMRADER and _OMRADER[navn] is not gate:
        raise ValueError(f'Området «{navn}» er alt registrert.')
    _OMRADER[navn] = gate


def omrader() -> tuple[str, ...]:
    return tuple(sorted(_OMRADER))


def _ny_start() -> int:
    """En startverdi ingen fane kan ha sett: millisekunder siden epoken."""
    return int(time.time() * 1000)


def _nokkel(navn: str, portal_id=None) -> str:
    return NOKKEL.format(navn) if portal_id is None else f'{NOKKEL.format(navn)}:p{portal_id}'


def _ok(nokkel: str) -> None:
    try:
        cache.incr(nokkel)
    except ValueError:
        # Nøkkelen finnes ikke (første gang, eller cachen er tømt). Ingenting å
        # gjøre: `versjon()` setter en ny start neste gang tallet leses, og den
        # er uansett en annen enn den noen fane har sett. (En `add` her sto
        # til mutasjonstestingen viste at den ikke endret noe.)
        pass
    except Exception:   # noqa: BLE001 — se modulens docstring
        logger.warning('endringer: kunne ikke øke %s', nokkel, exc_info=True)


def endret(navn: str, *, alle: bool = False) -> None:
    """Området er endret. Tallet øker når transaksjonen er commitet —
    utenfor en transaksjon med en gang.

    I portalen konteksten står i; uten kontekst, eller med `alle`, for alle."""
    try:
        from core.portal import aktiv_kontekst
        portal = None if alle else aktiv_kontekst()
        nokkel = _nokkel(navn, getattr(portal, 'pk', None))
        transaction.on_commit(lambda: _ok(nokkel))
    except Exception:   # noqa: BLE001
        logger.warning('endringer: kunne ikke melde %s', navn, exc_info=True)


def versjon(navn: str, portal=None) -> str:
    """Tallet for området, som tekst: det felles leddet, og portalens når den
    er oppgitt. Et tomt ledd betyr at cachen ikke svarte."""
    felles = _ett_ledd(_nokkel(navn))
    if portal is None:
        return felles
    return f'{felles}.{_ett_ledd(_nokkel(navn, portal.pk))}'


def _ett_ledd(nokkel: str) -> str:
    """Ett tall fra cachen, som tekst. Finnes det ikke, settes det."""
    try:
        verdi = cache.get(nokkel)
        if verdi is None:
            cache.add(nokkel, _ny_start(), timeout=None)
            verdi = cache.get(nokkel)
        return '' if verdi is None else str(verdi)
    except Exception:   # noqa: BLE001
        logger.warning('endringer: kunne ikke lese %s', nokkel, exc_info=True)
        return ''


def versjoner(request, navn: list[str]) -> dict[str, str]:
    """Tallene brukeren får se, av dem som er spurt om. Ukjente navn og
    områder uten tilgang er ikke med — heller ikke som `null`."""
    ut = {}
    for n in navn:
        gate = _OMRADER.get(n)
        if gate is None:
            continue
        try:
            if not gate(request):
                continue
        except Exception:   # noqa: BLE001 — en gate som feiler, stenger
            logger.warning('endringer: gaten for %s feilet', n, exc_info=True)
            continue
        ut[n] = versjon(n, getattr(request, 'portal', None))
    return ut
