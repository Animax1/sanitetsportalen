"""JSON-kroppen fra en forespørsel — rammeverkets versjon (26. sep. 2026).

Fem moduler har hver sin `_json_body`/`json_body` (E5 i
`docs/PLAN_TEKNISK_GJELD_2026-09-25.md`). Denne er den oppdragsmodulen
herdet i M8, og den første som bor i `core`: verdilistefabrikken
(`core.verdilister`) trengte en, og en sjette kopi ville gjort E5 større.
De andre samles hit når E5 tas.
"""
from __future__ import annotations

import json


def json_body(request) -> dict:
    """Parse JSON-kroppen, eller returner tom dict.

    `[]`, `"x"` og `null` er gyldig JSON og ga 500 på første `.get()` (M8).
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
