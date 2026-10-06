"""Lagene til kart.sanitet.net: hvor et lag står **nå** (`docs/archived/PLAN_KARTKOBLING.md` §7).

**Send tilstand, ikke hendelser.** `meld_lag(ressurs)` er den ene inngangen, og
den regner selv ut hvor laget står — så den kan kalles fra hvert sted som
endrer det, uten at kallstedet må vite hva som skal sendes:

| Laget | Sted til kartet |
|---|---|
| På en åpen hendelse (`HendelseLag`) | Hendelsens `lokasjon_navn` — opptatt har forrang, som på tavla |
| Åpen plassering på et sted | `Tavleplassering.lokasjon_navn` |
| Pause, uten plass, ingenting | `""` — kartet tar laget av |

Tre regler:

- **Etter commit, og tilstanden leses da.** Kallet legges i
  `transaction.on_commit`, og stedet regnes ut i det — en tavleendring som
  rulles tilbake sender ingenting, og det som sendes er det som faktisk står.
- **Bare lag, ikke biler.** En ressurs med `vaktliste.Ressurs.enhet` er en bil
  og sendes av oppdragsmodulen ved stempling (pulje D); sendt herfra også,
  ville den stått to ganger i kartet i to former.
- **KO slått av → ingen sending**, som `core/ressursplassering.py`.

Kaster aldri: kartet er et hjelpemiddel, og en flytting på tavla skal ikke
feile fordi det ikke svarer. `core.kartkobling` er inert uten oppsett.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def sted_naa(ressurs_id: int, vakt) -> str:
    """Hvor laget står nå, som stedsnavn — eller ``""``."""
    from .models import HENDELSE_APEN, HendelseLag, Tavleplassering

    paa = (HendelseLag.objects
           .filter(ressurs_id=ressurs_id, hendelse__status=HENDELSE_APEN,
                   hendelse__vakt=vakt)
           .select_related('hendelse').order_by('-fra', '-id').first())
    if paa is not None:
        return paa.hendelse.lokasjon_navn or ''
    plassering = (Tavleplassering.objects
                  .filter(ressurs_id=ressurs_id, vakt=vakt, til__isnull=True,
                          pause=False, lokasjon__isnull=False)
                  .only('lokasjon_navn').first())
    return plassering.lokasjon_navn if plassering is not None else ''


def meld_lag(ressurs) -> None:
    """Meld lagets sted til kartet etter commit. Tar en `Ressurs` eller en id."""
    ressurs_id = getattr(ressurs, 'pk', ressurs)
    if ressurs_id is None:
        return
    transaction.on_commit(lambda: _send(ressurs_id))


def _send(ressurs_id: int) -> None:
    try:
        from core import kartkobling
        from core.models import ModuleSettings
        from core.vakt import hent_aktiv_vakt
        from vaktliste.models import Ressurs

        if not kartkobling.er_konfigurert():
            return
        if 'ko' not in ModuleSettings.get_enabled_slugs():
            return
        ressurs = Ressurs.objects.filter(pk=ressurs_id).only('navn', 'enhet_id').first()
        if ressurs is None or ressurs.enhet_id is not None:
            return   # borte, eller en bil — bilene sendes ved stempling
        kartkobling.send_lag(ressurs.navn, sted_naa(ressurs_id, hent_aktiv_vakt()),
                             timezone.now())
    except Exception:
        logger.warning('Kartkobling: laget %s ble ikke meldt', ressurs_id, exc_info=True)
