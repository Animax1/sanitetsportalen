"""Fjern legitimasjon fra feiltekst før den vises eller lagres.

**Offentlig, fordi den har lesere utenfor server-status** (26. sep. 2026, B7).
Den lå som `_scrub_secrets` i `core/admin_status.py`, og `core/driftstatus.py`
importerte det private navnet derfra. Da vaktlista trengte den samme vaskingen
for feilen fra e-postutsendingen, var valget å importere et privat navn fra en
tredje fil eller å skrive regexen en gang til — og en kopi av en sikkerhetsregel
er en kopi som glir. `core/offsite.py` har sin egen `_vask` for S3-feil, med
andre mønstre; å slå dem sammen står i planen for teknisk gjeld (E6).
"""
from __future__ import annotations

import re

# Treffer 'redis://default:hemmelig123@host:6379/0' → 'redis://[scrubbed]@host:6379/0'.
_URL_CREDS_RE = re.compile(r'([a-zA-Z][a-zA-Z0-9+.\-]*://)([^/@\s]*@)')


def vask(tekst: str) -> str:
    """Fjern brukernavn og passord fra URL-er i en feiltekst.

    Forsvarslag: dagens biblioteker legger ikke passord i feilmeldingene sine,
    men tekst i et grensesnitt havner i skjermbilder og e-poster, og en ny
    versjon kan begynne. Tom inn gir tom ut.
    """
    if not tekst:
        return tekst
    return _URL_CREDS_RE.sub(r'\1[scrubbed]@', tekst)
