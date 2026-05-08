"""Backup- og restore-tjeneste.

Bruker Django dumpdata/loaddata (ren Python) for å unngå pg_dump-avhengighet.
Backups lagres som gzip-komprimerte JSON-filer i BACKUP_DIR.

Forbedring #0 (mai 2026): Auto-backups beregner SHA256 over JSON-innholdet og
hopper over filskriving + DB-rad hvis siste auto-backup har samme hash. Dette
hindrer opphoping av identiske backups når appen er aktiv men data er stabile.
Manuelle backups (kind != 'auto') lagres alltid.
"""
import gzip
import hashlib
import io
import json
import logging
import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core import management
from django.core.management import CommandError
from django.db import transaction
from django.utils import timezone

from .models import Backup

logger = logging.getLogger(__name__)


# Apper som skal inkluderes i backup.
# SIKKERHET: Vi inkluderer KUN pasientrelaterte data.
# Brukere (accounts) og revisjonslogg (audit) ekskluderes bevisst fordi:
#  - accounts inneholder passord-hasher og MFA-hemmeligheter
#  - audit/LoginEvent inneholder innloggingshistorikk og sensitive spor
#  - sessions inneholder aktive øktnøkler
# Disse skal aldri havne i en nedlastbar backup-fil.
# Backup og BackupConfig ekskluderes fra dumpdata for å unngå selvreferanse
# (backupen som lages lagrer en Backup-rad – den skal ikke være med i innholdet).
BACKUP_APPS = ['patients']
BACKUP_EXCLUDE = ['patients.Backup', 'patients.BackupConfig']
RETENTION_HOURS = 72


def get_backup_dir():
    """Returnerer Path til backup-mappen, opprett den hvis den ikke finnes."""
    path = Path(os.environ.get('BACKUP_DIR', settings.BASE_DIR / 'backups'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _serialize_db_to_json():
    """Kjør dumpdata for valgte apper og returner (bytes, sha256_hex).

    Ekskluderer Backup og BackupConfig for å unngå selvreferanse.
    SHA256 beregnes over ukomprimert JSON slik at samme data alltid gir samme
    hash uansett gzip-nivå eller dato-stempel i filnavn.
    """
    buf = io.StringIO()
    management.call_command(
        'dumpdata',
        *BACKUP_APPS,
        exclude=BACKUP_EXCLUDE,
        format='json',
        indent=None,
        natural_foreign=True,
        natural_primary=True,
        stdout=buf,
    )
    raw = buf.getvalue().encode('utf-8')
    content_hash = hashlib.sha256(raw).hexdigest()
    return raw, content_hash


def create_backup(kind='manual', user=None, note=''):
    """Lag en ny backup og lagre metadata.

    For kind='auto': hvis innholdet er identisk med siste auto-backup,
    hoppes filskriving og DB-rad over. Returnerer da None.
    For andre kind ('manual', 'pre_restore', 'pre_reset') lagres alltid.

    Returnerer Backup-instansen, eller None hvis auto-backup ble hoppet over.
    """
    assert kind in dict(Backup.KIND_CHOICES), f'Ugyldig kind: {kind}'

    raw, content_hash = _serialize_db_to_json()

    # Forbedring #0: hopp over identiske auto-backups.
    # Manuelle og pre_*-backups skal alltid lagres (audit-spor / sikkerhetsnett).
    if kind == 'auto':
        last_auto = (
            Backup.objects
            .filter(kind='auto')
            .exclude(content_hash='')
            .order_by('-created_at')
            .first()
        )
        if last_auto is not None and last_auto.content_hash == content_hash:
            logger.info(
                'backup_service: auto-backup hoppet over (identisk med %s, hash=%s)',
                last_auto.filename, content_hash[:12],
            )
            return None

    ts = timezone.now().strftime('%Y%m%d-%H%M%S')
    filename = f'backup-{kind}-{ts}.json.gz'
    path = get_backup_dir() / filename

    with gzip.open(path, 'wb', compresslevel=6) as f:
        f.write(raw)

    size = path.stat().st_size
    backup = Backup.objects.create(
        filename=filename, kind=kind, size_bytes=size,
        created_by=user, note=note, content_hash=content_hash,
    )
    return backup


def restore_backup(backup, user=None):
    """Gjenopprett en backup av pasientdata.

    SIKKERHET: Brukere, revisjonslogg, LoginEvent og sesjoner berøres IKKE.
    Kun pasientrelaterte data (Patient, Behandler, Helsepersonell, AppSetting)
    slettes og erstattes med innholdet fra backupen.

    Lager en pre-restore backup FØR sletting. Kjører i transaksjon slik at en
    feil ruller tilbake slettingen.
    """
    path = get_backup_dir() / backup.filename
    if not path.exists():
        raise FileNotFoundError(f'Backup-fil mangler: {backup.filename}')

    # 1) Sikkerhetsnett – tar snapshot av nåværende pasientdata
    create_backup(kind='pre_restore', user=user,
                  note=f'Før gjenoppretting av {backup.filename}')

    # 2) Les og dekomprimer
    with gzip.open(path, 'rb') as f:
        raw = f.read()

    # 3) Slett kun pasientrelaterte data + loaddata i samme transaksjon.
    #    Vi rører IKKE CustomUser, AuditLog, LoginEvent eller sesjoner –
    #    disse bevares på tvers av restore.
    from patients.models import Patient, Behandler, Helsepersonell, AppSetting

    with transaction.atomic():
        # Slett i rekkefølge som respekterer FK-er
        Patient.objects.all().delete()
        Behandler.objects.all().delete()
        Helsepersonell.objects.all().delete()
        AppSetting.objects.all().delete()

        # Skriv midlertidig fil som loaddata kan lese
        tmp_path = get_backup_dir() / f'.restore-tmp-{backup.pk}.json'
        try:
            tmp_path.write_bytes(raw)
            management.call_command('loaddata', str(tmp_path), verbosity=0)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


def purge_old_backups():
    """Slett backup-filer og metadata eldre enn RETENTION_HOURS."""
    cutoff = timezone.now() - timedelta(hours=RETENTION_HOURS)
    old = Backup.objects.filter(created_at__lt=cutoff)
    count = 0
    for b in old:
        path = get_backup_dir() / b.filename
        if path.exists():
            path.unlink()
        b.delete()
        count += 1
    return count
