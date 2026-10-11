"""Treffer klientens `If-None-Match` ETag-en vår? (11. okt. 2026)

**Svak sammenligning, som standarden krever** (RFC 9110 §13.1.2): `W/"x"` og `"x"`
er samme versjon. Fram til i dag sammenlignet hvert endepunkt headeren tegn for
tegn med `==`, og det var riktig så lenge ingen sto mellom bilen og serveren.

**Cloudflare står der.** Railway sender trafikken gjennom den (`server: cloudflare`),
og den komprimerer dynamiske svar selv — og **gjør en sterk ETag svak** når den
gjør det. Bilen fikk `W/"v2:…"`, sendte den tilbake, og `==` mot `"v2:…"` bommet:
**hver polling ble en full kropp**, for hver bil hvert 15. sekund, for sentralbordet
hvert 2,5. Funnet 11. okt. 2026 (TODO: «Treffer ETag-en på bilens poll?»): samme
statiske fil fikk `"…"` når Cloudflare sendte den slik den lå, og `W/"…"` når den
pakket den om.

Svaret er det samme med eller uten Cloudflare; derfor ett sted, brukt av alle.
"""
from __future__ import annotations


def _uten_svak(tag: str) -> str:
    tag = tag.strip()
    return tag[2:] if tag.startswith('W/') else tag


def _tagger(hode: str) -> list[str]:
    """`If-None-Match` som liste. Komma kan ikke stå i en ETag, så komma deler."""
    return [t for t in (_uten_svak(d) for d in hode.split(',')) if t]


def etag_treffer(request, etag: str) -> bool:
    """True når klienten alt har denne versjonen — svar 304.

    `*` treffer alt (standarden). En tom eller manglende header treffer ingenting.
    """
    hode = request.META.get('HTTP_IF_NONE_MATCH', '') or ''
    if not hode.strip() or not etag:
        return False
    if hode.strip() == '*':
        return True
    return _uten_svak(etag) in _tagger(hode)
