"""Hvilket bygg kjører — til footeren.

André ba 11. sep. 2026 om «versjonsnummer som er bygg og dato» nederst på
sida. Det er spørsmålet man stiller når noe ser annerledes ut enn i går:
er dette den nye koden, eller er det cachen? Uten et tall i footeren er
svaret et skjermbilde og en gjetning.

**Tre kilder, i denne rekkefølgen — den første som svarer vinner:**

1. ``bygg.json`` i prosjektrota, skrevet av ``core/skriv_bygg.py`` i
   byggfasen på Railway (``nixpacks.toml``). Den bærer commit-SHA fra
   ``RAILWAY_GIT_COMMIT_SHA`` og klokkeslettet bygget ble laget. Fila er
   ikke i git — den finnes bare i containeren.
2. ``git`` i arbeidskatalogen: SHA og commit-tidspunkt. Det er
   utviklerens svar, og det er riktigere enn byggtiden, men ``.git``
   finnes ikke i containeren, så i prod svarer den aldri.
3. Miljøvariabelen alene, med ``manage.py`` sin mtime som dato. Den
   varianten finnes for at footeren ikke skal stå tom hvis byggsteget
   ikke kjørte — mtime-en er tidspunktet filene ble sjekket ut, som er
   nær nok byggtiden til å svare på «er dette nytt?».

Ingen kilde gir «ukjent», ikke en tom streng: en tom footer ser ut som en
feil i malen.

Svaret regnes ut én gang per prosess. Det endrer seg ikke før koden gjør
det, og da starter prosessen på nytt.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from django.conf import settings

UKJENT = 'ukjent'


def _fra_byggfil(rot: Path):
    fil = rot / 'bygg.json'
    if not fil.is_file():
        return None
    try:
        data = json.loads(fil.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    bygg = str(data.get('bygg') or '').strip()[:7]
    dato = _les_tid(data.get('dato'))
    if not bygg and dato is None:
        return None
    return {'bygg': bygg or UKJENT, 'dato': dato, 'kilde': 'bygg.json'}


def _fra_git(rot: Path):
    if not (rot / '.git').exists():
        return None
    try:
        ut = subprocess.run(
            ['git', 'log', '-1', '--format=%h %cI'],
            cwd=rot, capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    deler = ut.stdout.strip().split()
    if ut.returncode != 0 or len(deler) != 2:
        return None
    return {'bygg': deler[0][:7], 'dato': _les_tid(deler[1]), 'kilde': 'git'}


def _fra_miljo(rot: Path):
    sha = os.environ.get('RAILWAY_GIT_COMMIT_SHA', '').strip()[:7]
    if not sha:
        return None
    try:
        mtime = (rot / 'manage.py').stat().st_mtime
        dato = datetime.fromtimestamp(mtime, tz=timezone.utc)
    except OSError:
        dato = None
    return {'bygg': sha, 'dato': dato, 'kilde': 'miljø'}


def _les_tid(verdi):
    if not verdi:
        return None
    try:
        tid = datetime.fromisoformat(str(verdi))
    except ValueError:
        return None
    if tid.tzinfo is None:
        tid = tid.replace(tzinfo=timezone.utc)
    return tid


def finn_versjon(rot: Path | None = None) -> dict:
    """Bygg og dato, uten cache — testene kaller denne med egen rot."""
    rot = Path(rot or settings.BASE_DIR)
    for kilde in (_fra_byggfil, _fra_git, _fra_miljo):
        svar = kilde(rot)
        if svar:
            return svar
    return {'bygg': UKJENT, 'dato': None, 'kilde': 'ingen'}


@lru_cache(maxsize=1)
def hent_versjon() -> dict:
    """Det footeren viser. Én gang per prosess."""
    return finn_versjon()
