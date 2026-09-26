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

from django.http import JsonResponse


def json_body(request) -> dict:
    """Parse JSON-kroppen, eller returner tom dict.

    `[]`, `"x"` og `null` er gyldig JSON og ga 500 på første `.get()` (M8).
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def json_feil(melding, status=400) -> JsonResponse:
    """`{'status': 'error', 'message': …}` — formen klientenes `apiFetch` leser."""
    return JsonResponse({'status': 'error', 'message': melding}, status=status)
