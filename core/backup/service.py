"""Sentral backup/restore-tjeneste — modul-agnostisk.

Bruker registrerte handlers (core.backup.handlers) for å lage og
gjenopprette backuper per modul. Hver backup lagres som en
gzip-komprimert JSON-fil i BACKUP_DIR med filnavn på formen
``backup-<slug>-<kind>-<timestamp>.json.gz``.

Hash-skip: Hvis innholdet er identisk med siste auto-backup for samme
modul, hoppes filskriving og DB-rad over (sjekkes via ``content_hash``).

Cap: Etter hver vellykket skriving slettes eldste backuper for modulen
slik at totalt antall ikke overstiger ``ModuleBackupConfig.max_backups``.
Pre-restore-backuper er IKKE inkludert i cap-håndteringen — de er et
sikkerhetsnett.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import logging
import os
from pathlib import Path

from django.conf import settings
from django.core import management
from django.db import transaction
from django.utils import timezone

from .handlers import BaseBackupHandler, get_handler

logger = logging.getLogger(__name__)


# Backup-typer.
KIND_AUTO = 'auto'
KIND_MANUAL = 'manual'
KIND_PRE_RESTORE = 'pre_restore'
KIND_PRE_RESET = 'pre_reset'

VALID_KINDS = {KIND_AUTO, KIND_MANUAL, KIND_PRE_RESTORE, KIND_PRE_RESET}

# Disse skal IKKE telles mot cap, og IKKE slettes når cap håndheves.
# pre_restore-backuper er sikkerhetsnett som må overleve uavhengig av cap.
PROTECTED_KINDS = {KIND_PRE_RESTORE}


def get_backup_dir() -> Path:
    """Returnerer Path til backup-mappen, opprett ved behov."""
    path = Path(os.environ.get('BACKUP_DIR', settings.BASE_DIR / 'backups'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _serialize_with_handler(handler: BaseBackupHandler) -> tuple[bytes, str]:
    """Kjør dumpdata for handlerens apps og returner (bytes, sha256_hex).

    SHA256 beregnes over den ukomprimerte JSON-en slik at samme data
    alltid gir samme hash uavhengig av gzip-nivå eller filnavn-tidsstempel.
    """
    buf = io.StringIO()
    apps = handler.collect_apps()
    exclude = handler.collect_exclude()
    management.call_command(
        'dumpdata', *apps,
        exclude=exclude,
        format='json',
        indent=None,
        natural_foreign=True,
        natural_primary=True,
        stdout=buf,
    )
    raw = buf.getvalue().encode('utf-8')
    content_hash = hashlib.sha256(raw).hexdigest()
    return raw, content_hash


def _build_filename(slug: str, kind: str) -> str:
    # Inkluderer mikrosekunder slik at to backups innen samme sekund
    # (f.eks. en manuell rett etter en pre_restore) ikke kolliderer på unique
    # filename.
    ts = timezone.now().strftime('%Y%m%d-%H%M%S-%f')
    return f'backup-{slug}-{kind}-{ts}.json.gz'


def create_backup(slug: str, kind: str = KIND_MANUAL,
                  user=None, note: str = ''):
    """Lag en backup for modulen ``slug``.

    For ``kind=KIND_AUTO``: hvis innholdet er identisk med siste
    auto-backup for modulen, hoppes lagring over og None returneres.
    For andre typer (manual/pre_restore/pre_reset) lagres alltid.

    Returnerer Backup-instansen, eller None hvis auto-backup ble hoppet
    over.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f'Ugyldig kind: {kind!r}. Må være en av {VALID_KINDS}')

    handler = get_handler(slug)
    if handler is None:
        raise ValueError(f'Ingen registrert backup-handler for modul {slug!r}.')

    # Lazy-import for å unngå sirkulær avhengighet ved app-loading.
    from patients.models import Backup

    raw, content_hash = _serialize_with_handler(handler)

    # Hash-skip kun for auto-backups.
    if kind == KIND_AUTO:
        last = (
            Backup.objects
            .filter(module_slug=slug, kind=KIND_AUTO)
            .exclude(content_hash='')
            .order_by('-created_at')
            .first()
        )
        if last is not None and last.content_hash == content_hash:
            logger.info(
                'core.backup: auto-backup hoppet over for %s (hash=%s, '
                'identisk med %s)', slug, content_hash[:12], last.filename,
            )
            return None

    filename = _build_filename(slug, kind)
    path = get_backup_dir() / filename

    with gzip.open(path, 'wb', compresslevel=6) as f:
        f.write(raw)

    size = path.stat().st_size
    backup = Backup.objects.create(
        filename=filename,
        kind=kind,
        size_bytes=size,
        created_by=user,
        note=note,
        content_hash=content_hash,
        module_slug=slug,
    )
    logger.info('core.backup: opprettet %s (%d bytes)', filename, size)
    return backup


def enforce_cap(slug: str, max_backups: int) -> int:
    """Slett eldste backuper for modulen slik at totalt antall <= max_backups.

    pre_restore-backuper telles ikke og slettes ikke. Returnerer antall
    slettede filer/rader.
    """
    if max_backups <= 0:
        return 0

    from patients.models import Backup

    qs = (
        Backup.objects
        .filter(module_slug=slug)
        .exclude(kind__in=PROTECTED_KINDS)
        .order_by('-created_at')
    )
    total = qs.count()
    if total <= max_backups:
        return 0

    excess_ids = list(qs.values_list('id', flat=True)[max_backups:])
    deleted = 0
    backup_dir = get_backup_dir()
    for backup in Backup.objects.filter(id__in=excess_ids):
        path = backup_dir / backup.filename
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning(
                    'core.backup: kunne ikke slette %s: %s',
                    backup.filename, exc,
                )
        backup.delete()
        deleted += 1
    if deleted:
        logger.info(
            'core.backup: cap (%d) tvang sletting av %d gamle backuper for %s',
            max_backups, deleted, slug,
        )
    return deleted


def restore_backup(backup, user=None) -> None:
    """Gjenopprett en backup for modulen den tilhører.

    Steg:
    1. Lag en pre_restore-backup av nåværende tilstand (sikkerhetsnett).
    2. Slett eksisterende rader i restore_models (FK-trygg rekkefølge).
    3. Kall loaddata på den lagrede JSON-fila.

    Hele restore (steg 2-3) kjører i én transaksjon. Feiler noe ruller
    alt tilbake. pre_restore-backupen i steg 1 er allerede commitet og
    forblir på disk uansett.
    """
    handler = get_handler(backup.module_slug)
    if handler is None:
        raise ValueError(
            f'Kan ikke gjenopprette: ingen handler for modul '
            f'{backup.module_slug!r}.'
        )

    backup_dir = get_backup_dir()
    path = backup_dir / backup.filename
    if not path.exists():
        raise FileNotFoundError(f'Backup-fil mangler: {backup.filename}')

    # 1) Sikkerhetsnett — pre_restore-snapshot FØR vi rører noe.
    create_backup(
        slug=backup.module_slug,
        kind=KIND_PRE_RESTORE,
        user=user,
        note=f'Før gjenoppretting av {backup.filename}',
    )

    with gzip.open(path, 'rb') as f:
        raw = f.read()

    # Slett-rekkefølge bestemt av handler.
    restore_models = handler.get_restore_models()

    with transaction.atomic():
        for model_label in restore_models:
            app_label, model_name = model_label.split('.')
            from django.apps import apps as django_apps
            model_cls = django_apps.get_model(app_label, model_name)
            model_cls.objects.all().delete()

        tmp_path = backup_dir / f'.restore-tmp-{backup.pk}.json'
        try:
            tmp_path.write_bytes(raw)
            management.call_command('loaddata', str(tmp_path), verbosity=0)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    logger.info(
        'core.backup: restored modul=%s fra %s av bruker=%s',
        backup.module_slug, backup.filename,
        user.username if user else '<system>',
    )
