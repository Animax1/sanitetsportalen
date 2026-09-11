"""Skriv ``bygg.json`` — kjøres i byggfasen på Railway, se ``nixpacks.toml``.

**Bare standardbiblioteket, med vilje.** Skriptet kjører før noe annet i
bygget, og et Django-oppsett der ville trengt SECRET_KEY og en database
bare for å skrive to felter til en fil — og feilet det, feilet hele
deployen for en footer. Det eneste det trenger er miljøet og klokka.

``RAILWAY_GIT_COMMIT_SHA`` settes av Railway i både bygg og kjøring. Mangler
den (lokalt), skrives fila uten SHA, og ``core.versjon`` faller videre til
git.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def skriv(maal: Path, sha: str = '', naa: datetime | None = None) -> dict:
    data = {
        'bygg': (sha or '').strip()[:7],
        # `fromtimestamp` med sone, ikke `datetime.now`: portalens regel er at
        # ingen kode utleder tid uten sone, og `IngenNaivDatetimeTests`
        # håndhever den ved å lete etter selve kallet.
        'dato': (naa or datetime.fromtimestamp(time.time(), tz=timezone.utc))
        .isoformat(timespec='seconds'),
    }
    maal.write_text(json.dumps(data), encoding='utf-8')
    return data


if __name__ == '__main__':
    rot = Path(__file__).resolve().parent.parent
    data = skriv(rot / 'bygg.json', os.environ.get('RAILWAY_GIT_COMMIT_SHA', ''))
    print(f'bygg.json: {data["bygg"] or "(uten sha)"} {data["dato"]}', file=sys.stderr)
