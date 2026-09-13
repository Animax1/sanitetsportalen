"""Backupene ut av Railway — til Scaleway Object Storage (13. sep. 2026).

Det som skal overleve at Railway faller, er dataene. `core.backup` skriver
per-modul-filer til volumet; dette modulen laster hver ny fil opp til en
S3-bucket i Amsterdam, **kryptert før den forlater Railway** — pasientfilene
er helseopplysninger, og Scaleways egen kryptering (SSE) beskytter bare mot
at noen leser diskene hos dem, ikke mot en lekket bucket-nøkkel.

Tre regler:

- **Frekvens = når noe har endret seg.** Opplastingen henger på at
  `create_backup` faktisk skrev en ny fil (hash-skip gjør at en kjøring uten
  endringer ikke skriver noe). Ingen egen klokke, ingen egen cron.
- **Kaster aldri.** En bucket som ikke svarer skal ikke stoppe backupen på
  volumet, som er det første sikkerhetsnettet. Feilen skrives i
  `OffsiteKopi.feil` og logges; oversikten på /portal-admin/backup/ viser den.
- **Inert uten variablene.** Uten `OFFSITE_S3_BUCKET` og `OFFSITE_BACKUP_KEY`
  gjør `meld_ny_backup` ingenting — staging og lokal utvikling har ingen
  offsite-backup, med vilje.

Kryptering: AES-256-GCM med nøkkel avledet av `OFFSITE_BACKUP_KEY` (SHA-256).
Formatet er `SPBK1` + 12 byte nonce + chiffertekst med tag. Nøkkelen må
finnes *utenfor* Railway også (passordbehandler): uten den er bucketen
uleselig, og det er hele poenget.

Gjenoppretting: `python manage.py hent_offsite --list` og
`python manage.py hent_offsite <objektnavn>` henter, dekrypterer og legger
fila der `restore_backup` finner den, med en `Backup`-rad.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MAGI = b'SPBK1'
SUFFIKS = '.enc'

#: **Ett prefiks per oppbevaringstid** (13. sep. 2026). Fristene kan bare
#: skilles i bucketen hvis filene ligger på hver sin sti, og livssyklusreglene
#: filtrerer på prefiks: `backups/` i 730 dager, `full/` i 90. Se
#: `docs/PLAN_BACKUP_OMLEGGING.md` §6.2 og §7.
PREFIKS = 'backups/'
PREFIKS_FULL = 'full/'
ALLE_PREFIKS = (PREFIKS, PREFIKS_FULL)


def prefiks_for(module_slug: str) -> str:
    """Hvor i bucketen filene til denne modulen skal ligge.

    Den hele basen ligger for seg selv fordi den har en annen frist — ikke
    fordi den er en annen slags fil.
    """
    return PREFIKS_FULL if module_slug == 'full' else PREFIKS


# ── Konfigurasjon ────────────────────────────────────────────────────────────

def konfig() -> dict:
    return {
        'bucket': getattr(settings, 'OFFSITE_S3_BUCKET', ''),
        'region': getattr(settings, 'OFFSITE_S3_REGION', 'nl-ams'),
        'endpoint': getattr(settings, 'OFFSITE_S3_ENDPOINT', 'https://s3.nl-ams.scw.cloud'),
        'access_key': getattr(settings, 'OFFSITE_S3_ACCESS_KEY', ''),
        'secret_key': getattr(settings, 'OFFSITE_S3_SECRET_KEY', ''),
        'nokkel': getattr(settings, 'OFFSITE_BACKUP_KEY', ''),
    }


def er_konfigurert() -> bool:
    k = konfig()
    return bool(k['bucket'] and k['access_key'] and k['secret_key'] and k['nokkel'])


def mangler() -> list[str]:
    """Hvilke variabler som mangler — for oversikten og for kommandoen."""
    k = konfig()
    navn = {'bucket': 'OFFSITE_S3_BUCKET', 'access_key': 'OFFSITE_S3_ACCESS_KEY',
            'secret_key': 'OFFSITE_S3_SECRET_KEY', 'nokkel': 'OFFSITE_BACKUP_KEY'}
    return [navn[felt] for felt in navn if not k[felt]]


# ── Kryptering ───────────────────────────────────────────────────────────────

def _avledet_nokkel(hemmelighet: str) -> bytes:
    if not hemmelighet:
        raise ValueError('OFFSITE_BACKUP_KEY mangler.')
    return hashlib.sha256(hemmelighet.encode('utf-8')).digest()


def krypter(data: bytes, hemmelighet: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return MAGI + nonce + AESGCM(_avledet_nokkel(hemmelighet)).encrypt(nonce, data, MAGI)


def dekrypter(blob: bytes, hemmelighet: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not blob.startswith(MAGI) or len(blob) < len(MAGI) + 12 + 16:
        raise ValueError('Fila er ikke en kryptert backup fra portalen.')
    nonce = blob[len(MAGI):len(MAGI) + 12]
    try:
        return AESGCM(_avledet_nokkel(hemmelighet)).decrypt(nonce, blob[len(MAGI) + 12:], MAGI)
    except Exception as exc:   # InvalidTag — feil nøkkel eller tuklet fil
        raise ValueError('Kunne ikke dekryptere: feil OFFSITE_BACKUP_KEY, eller fila er endret.') from exc


# ── S3 ───────────────────────────────────────────────────────────────────────

def _klient():
    import boto3
    from botocore.config import Config
    k = konfig()
    return boto3.client(
        's3',
        region_name=k['region'],
        endpoint_url=k['endpoint'],
        aws_access_key_id=k['access_key'],
        aws_secret_access_key=k['secret_key'],
        config=Config(connect_timeout=10, read_timeout=60, retries={'max_attempts': 2}),
    )


def objektnavn(filnavn: str, module_slug: str = '') -> str:
    return f'{prefiks_for(module_slug)}{filnavn}{SUFFIKS}'


def last_opp(backup, sti) -> 'OffsiteKopi':
    """Krypter og last opp én backup-fil. Returnerer raden, med `feil` satt
    hvis det ikke gikk. Kaster aldri."""
    from core.models import OffsiteKopi
    k = konfig()
    rad = OffsiteKopi(backup_filnavn=backup.filename, module_slug=backup.module_slug,
                      objektnavn=objektnavn(backup.filename, backup.module_slug))
    try:
        raa = open(sti, 'rb').read()
        blob = krypter(raa, k['nokkel'])
        rad.bytes = len(blob)
        _klient().put_object(
            Bucket=k['bucket'], Key=rad.objektnavn, Body=blob,
            ContentType='application/octet-stream',
            Metadata={'modul': backup.module_slug, 'kind': backup.kind,
                      'sha256': hashlib.sha256(raa).hexdigest()})
        rad.sendt_at = timezone.now()
        logger.info('core.offsite: lastet opp %s (%d bytes)', rad.objektnavn, rad.bytes)
    except Exception as exc:   # noqa: BLE001 — sporet skal ha årsaken
        rad.feil = f'{exc.__class__.__name__}: {exc}'[:500]
        logger.exception('core.offsite: opplasting av %s feilet', backup.filename)
    rad.save()
    return rad


def meld_ny_backup(backup, sti) -> None:
    """Kalles av `create_backup` etter at fila er skrevet. Inert uten
    konfigurasjon; kaster aldri."""
    if backup is None or not er_konfigurert():
        return
    try:
        last_opp(backup, sti)
    except Exception:   # noqa: BLE001
        logger.exception('core.offsite: uventet feil ved opplasting')


def list_objekter() -> list[dict]:
    """[{navn, bytes, endret}] for alt under begge prefiksene, nyeste først."""
    k = konfig()
    ut = []
    for prefiks in ALLE_PREFIKS:
        token = None
        while True:
            args = {'Bucket': k['bucket'], 'Prefix': prefiks}
            if token:
                args['ContinuationToken'] = token
            svar = _klient().list_objects_v2(**args)
            for o in svar.get('Contents', []) or []:
                ut.append({'navn': o['Key'], 'bytes': o.get('Size', 0),
                           'endret': o.get('LastModified')})
            if not svar.get('IsTruncated'):
                break
            token = svar.get('NextContinuationToken')
    ut.sort(key=lambda o: (o['endret'] is None, o['endret']), reverse=True)
    return ut


def hent(objekt: str):
    """Hent, dekrypter og legg fila der `restore_backup` finner den. Lager en
    `Backup`-rad hvis den mangler (fila kan komme fra en annen Railway-base).
    Returnerer (Backup, sti)."""
    from core.backup import get_backup_dir
    from patients.models import Backup
    k = konfig()
    # Filnavnet alene holder: prefikset utledes av slugen i navnet, så
    # `hent_offsite backup-full-...` finner fila under `full/` uten at man må
    # vite hvor den ligger.
    if not objekt.startswith(ALLE_PREFIKS):
        objekt = prefiks_for(_slug_fra_filnavn(objekt)) + objekt
    if not objekt.endswith(SUFFIKS):
        objekt += SUFFIKS
    brukt_prefiks = next(p for p in ALLE_PREFIKS if objekt.startswith(p))
    filnavn = objekt[len(brukt_prefiks):-len(SUFFIKS)]
    # Objektnavnet bestemmer stien fila skrives til (13. sep. 2026, L3): en
    # kompromittert bucket skal ikke være en vei ut av BACKUP_DIR.
    if not filnavn or '/' in filnavn or '\\' in filnavn or filnavn != Path(filnavn).name:
        raise ValueError(f'Objektnavnet «{objekt}» er ikke et filnavn.')
    svar = _klient().get_object(Bucket=k['bucket'], Key=objekt)
    blob = svar['Body'].read()
    raa = dekrypter(blob, k['nokkel'])
    sti = get_backup_dir() / filnavn
    with open(sti, 'wb') as f:
        f.write(raa)
    meta = svar.get('Metadata') or {}
    backup, _ = Backup.objects.get_or_create(
        filename=filnavn,
        defaults={'kind': meta.get('kind') or 'manual', 'size_bytes': len(raa),
                  'module_slug': meta.get('modul') or _slug_fra_filnavn(filnavn),
                  'note': f'Hentet fra offsite {timezone.localtime():%d.%m.%Y %H:%M}'})
    return backup, sti


def _slug_fra_filnavn(filnavn: str) -> str:
    # backup-<slug>-<kind>-<tidsstempel>.json.gz. Tidsstempelet har selv
    # bindestreker, så let etter typen (som aldri har det) og ta alt foran.
    from core.backup.service import VALID_KINDS
    deler = filnavn.removeprefix('backup-').split('-')
    for i in range(len(deler) - 1, 0, -1):
        if deler[i] in VALID_KINDS:
            return '-'.join(deler[:i])
    return ''


def status() -> dict:
    """Til oversikten: konfigurert, siste opplasting, siste feil, antall."""
    from core.models import OffsiteKopi
    siste = OffsiteKopi.objects.order_by('-created_at').first()
    siste_ok = OffsiteKopi.objects.filter(feil='').order_by('-created_at').first()
    return {
        'konfigurert': er_konfigurert(),
        'mangler': mangler(),
        'bucket': konfig()['bucket'],
        'antall': OffsiteKopi.objects.filter(feil='').count(),
        'siste_ok': siste_ok,
        'siste_feil': siste if siste is not None and siste.feil else None,
    }
