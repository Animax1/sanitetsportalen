"""Fjern legitimasjon fra feiltekst før den vises eller lagres.

**Offentlig, fordi den har lesere utenfor server-status** (26. sep. 2026, B7).
Den lå som `_scrub_secrets` i `core/admin_status.py`, og `core/driftstatus.py`
importerte det private navnet derfra. Da vaktlista trengte den samme vaskingen
for feilen fra e-postutsendingen, var valget å importere et privat navn fra en
tredje fil eller å skrive regexen en gang til — og en kopi av en sikkerhetsregel
er en kopi som glir.

**Én funksjon, to slags hemmeligheter** (26. sep. 2026, E6). `core/offsite.py`
hadde sin egen `_vask`, som byttet ut S3-nøklene men ikke URL-legitimasjon —
mens `vask` gjorde det motsatte. Og den ble brukt på én av tre steder der
offsite-feil når nettleseren. Nå tar `vask` begge: URL-er alltid, og kjente
hemmeligheter når kallstedet oppgir dem.
"""
from __future__ import annotations

import re

# Treffer 'redis://default:hemmelig123@host:6379/0' → 'redis://[scrubbed]@host:6379/0'.
_URL_CREDS_RE = re.compile(r'([a-zA-Z][a-zA-Z0-9+.\-]*://)([^/@\s]*@)')


def vask(tekst: str, *, hemmeligheter=(), maks: int | None = None) -> str:
    """Fjern brukernavn og passord fra URL-er, og hver av `hemmeligheter`.

    Forsvarslag: dagens biblioteker legger ikke passord i feilmeldingene sine,
    men tekst i et grensesnitt havner i skjermbilder og e-poster, og en ny
    versjon kan begynne. Tom inn gir tom ut. `maks` kapper **etter** vaskingen
    — kappet først, kunne en halv nøkkel stått igjen.
    """
    if not tekst:
        return tekst
    tekst = _URL_CREDS_RE.sub(r'\1[scrubbed]@', tekst)
    for hemmelig in hemmeligheter:
        if hemmelig:
            tekst = tekst.replace(hemmelig, '***')
    return tekst[:maks] if maks else tekst
