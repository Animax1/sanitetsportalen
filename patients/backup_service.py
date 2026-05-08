"""Backup- og restore-tjeneste for patients-modulen.

**Fase 4-endring:** Logikken er flyttet til ``core.backup`` for å støtte
per-modul backup. Denne fila er nå en tynn proxy som beholder bakoverkompatibel
API for eksisterende kode (admin-views, kommandoer, tester).

Nye moduler som vil ha backup skal IKKE bruke denne fila — de skal
registrere en ``BaseBackupHandler`` i ``core.backup`` og bruke
``core.backup.create_backup(slug=...)`` direkte.
"""
from __future__ import annotations

import logging

from core.backup import (
    KIND_AUTO,
    create_backup as _core_create_backup,
    enforce_cap as _core_enforce_cap,
    get_backup_dir as _core_get_backup_dir,
    restore_backup as _core_restore_backup,
)
from core.backup.service import _serialize_with_handler  # noqa: F401 — testbruk

from .models import Backup

logger = logging.getLogger(__name__)


# Apper og ekskluderinger oppgis nå av PatientsBackupHandler.
# Disse beholdes som dokumentasjon-konstanter for å hindre at gammel
# kode/tester importerer ikke-eksisterende navn.
BACKUP_APPS = ['patients']
BACKUP_EXCLUDE = ['patients.Backup', 'patients.BackupConfig', 'patients.VaktArkiv']

# Beholdes for bakoverkompatibilitet, men brukes ikke aktivt — cap erstatter
# tidsbasert retention. Fra Fase 4 styres oppryddingen av
# ModuleBackupConfig.max_backups (default 50).
RETENTION_HOURS = 72

# Default cap for legacy-kall som ikke spesifiserer noe.
_DEFAULT_CAP = 50


def get_backup_dir():
    """Proxy mot core.backup.get_backup_dir()."""
    return _core_get_backup_dir()


def create_backup(kind: str = 'manual', user=None, note: str = ''):
    """Bakoverkompatibel: lag backup for ``patients``-modulen.

    For ``kind='auto'`` med identisk innhold returneres None (hash-skip).
    For andre typer lagres alltid.
    """
    return _core_create_backup(slug='patients', kind=kind, user=user, note=note)


def restore_backup(backup, user=None) -> None:
    """Bakoverkompatibel: gjenopprett en backup.

    Routes til core.backup.restore_backup, som bruker handler-en
    registrert for backup.module_slug.
    """
    _core_restore_backup(backup, user=user)


def purge_old_backups() -> int:
    """Bakoverkompatibel: håndhev cap for patients-modulen.

    Bruker default-capen (50). Auto-backup-flyten i scheduleren bruker
    config.max_backups direkte og kaller ikke denne funksjonen.
    """
    from core.models import ModuleBackupConfig
    cfg = ModuleBackupConfig.objects.filter(module_slug='patients').first()
    cap = cfg.max_backups if cfg else _DEFAULT_CAP
    return _core_enforce_cap('patients', cap)


# Re-eksporter konstant for legacy-tester.
__all__ = [
    'BACKUP_APPS',
    'BACKUP_EXCLUDE',
    'RETENTION_HOURS',
    'Backup',
    'KIND_AUTO',
    'create_backup',
    'get_backup_dir',
    'purge_old_backups',
    'restore_backup',
]
