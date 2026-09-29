"""JSON inn og feil ut — rammeverkets versjon (26. sep. 2026, E5).

Fem moduler hadde hver sin `_json_body`/`json_body`, og fire hadde i tillegg sin
egen `_feil` — pluss en i `core.verdilister`. Innholdet hadde *ikke* glidd:
M8 rettet alle fem samtidig. Men det var flaks at det gikk, ikke en egenskap:
M8 fant kopiene ved å lete, og en sjette kopi skrevet før M8 ville stått igjen
med 500 på `[]`. `core/tests_jsonkropp.py` håndhever at ingen modul definerer
sin egen.

Avhengighetsretningen er den vanlige: modulene importerer herfra, `core`
importerer ingen modul.
"""
from __future__ import annotations

import json
import math

from django.http import JsonResponse


def _endelig(tekst: str) -> float:
    verdi = float(tekst)
    if not math.isfinite(verdi):
        raise ValueError(f'Tallet er ikke endelig: {tekst[:20]}')
    return verdi


def _ikke_konstant(navn: str):
    raise ValueError(f'{navn} er ikke et tall.')


def les_json(raa):
    """`json.loads` uten tall som ikke er endelige. Kaster `ValueError`.

    For kallsteder som trenger sin egen feilmelding (stemplingen i oppdrag);
    ellers `json_body`. `JSONDecodeError` er en `ValueError`.
    """
    return json.loads(raa, parse_float=_endelig, parse_constant=_ikke_konstant)


def json_body(request) -> dict:
    """Parse JSON-kroppen, eller returner tom dict.

    `[]`, `"x"` og `null` er gyldig JSON og ga 500 på første `.get()` (M8).

    **Og tall som ikke er endelige avvises** (sikkerhetsgjennomgangen 28. sep.
    2026). Pythons `json` godtar `Infinity`, `NaN` og `1e999` (som blir `inf`),
    og `int(float('inf'))` kaster `OverflowError` — som ingen av de rundt 40
    kallstedene fanger. Det ga 500 fra `/lag/r/`, uten innlogging. Å rette det
    her tar alle kallstedene; å rette det i hvert av dem hadde vært 40
    muligheter til å glemme ett.
    """
    try:
        data = les_json(request.body)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def json_feil(melding, status=400) -> JsonResponse:
    """`{'status': 'error', 'message': …}` — formen klientenes `apiFetch` leser."""
    return JsonResponse({'status': 'error', 'message': melding}, status=status)
