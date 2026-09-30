"""Intervallsending av vaktlista som fil (13. sep. 2026).

Samme mønster som `core.middleware.BackupSchedulerMiddleware`: portalen
har ingen egen klokke, så sjekken henger på trafikken — etter en respons,
maks én gang i minuttet per prosess, og selve sendingen i en bakgrunnstråd
slik at ingen venter på AHASend. Under en vakt er det alltid trafikk; utenom
vakt finnes ingen liste i drift, og da er det ingenting å sende.

Reglene ligger i `fil.send_planlagte()` og `services.sett_forfalte_i_drift()`
— dette er bare klokka.
"""
from __future__ import annotations

import logging
import threading
import time

from django.db import connection

logger = logging.getLogger(__name__)

_THROTTLE_SEKUNDER = 60
_siste_sjekk = 0.0
_kjorer = False
_laas = threading.Lock()


def maybe_send_planlagte() -> bool:
    """Start en sjekk i bakgrunnen hvis det er over et minutt siden forrige.
    Returnerer True når en tråd ble startet — for testene."""
    global _siste_sjekk, _kjorer
    naa = time.monotonic()
    with _laas:
        if naa - _siste_sjekk < _THROTTLE_SEKUNDER or _kjorer:
            return False
        _siste_sjekk = naa
        _kjorer = True
    threading.Thread(target=_kjor, daemon=True).start()
    return True


def _kjor():
    global _kjorer
    from . import fil, services
    # **Drift ved vaktas start** (30. sep. 2026) går på samme klokke, og før
    # intervallsendingen: en liste som nettopp gikk i drift skal ikke få en
    # intervallfil i samme runde som driftfila. Hver for seg i try — en feil i
    # den ene skal ikke stoppe den andre.
    try:
        services.sett_forfalte_i_drift()
    except Exception:   # noqa: BLE001 — klokka skal aldri ta ned appen
        logger.exception('Automatisk drift av vaktlisten feilet')
    try:
        fil.send_planlagte()
    except Exception:   # noqa: BLE001 — sendingen skal aldri ta ned appen
        logger.exception('Intervallsending av vaktlisten feilet')
    finally:
        # Tråden har sin egen databasetilkobling; uten close() blir den
        # liggende til prosessen dør.
        try:
            connection.close()
        except Exception:   # noqa: BLE001
            pass
        with _laas:
            _kjorer = False


def nullstill_for_test():
    global _siste_sjekk, _kjorer
    with _laas:
        _siste_sjekk = 0.0
        _kjorer = False


class FilutsendingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            maybe_send_planlagte()
        except Exception:   # noqa: BLE001
            pass
        return response
