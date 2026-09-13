"""Intervallsending av vaktlista som fil (13. sep. 2026).

Samme mønster som `patients.middleware.BackupSchedulerMiddleware`: portalen
har ingen egen klokke, så sjekken henger på trafikken — etter en respons,
maks én gang i minuttet per prosess, og selve sendingen i en bakgrunnstråd
slik at ingen venter på AHASend. Under en vakt er det alltid trafikk; utenom
vakt finnes ingen liste i drift, og da er det ingenting å sende.

Reglene ligger i `fil.send_planlagte()` — dette er bare klokka.
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
    from . import fil
    try:
        fil.send_planlagte()
    except Exception:   # noqa: BLE001 — sendingen skal aldri ta ned appen
        logger.exception('Intervallsending av vaktlista feilet')
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
