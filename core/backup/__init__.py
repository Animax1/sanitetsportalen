"""Per-modul backup/restore-system.

Hovedeksport:

- ``BaseBackupHandler`` — subklasses i hver modul som vil ha backup
- ``register(handler)`` — registrer handler (kall fra apps.ready())
- ``create_backup(slug, kind, user, note)`` — lag en backup
- ``restore_backup(backup, user)`` — gjenopprett en backup
- ``enforce_cap(slug, max_backups)`` — håndhev cap på antall backups
- Konstanter: ``KIND_AUTO``, ``KIND_MANUAL``, ``KIND_PRE_RESTORE``,
  ``KIND_PRE_RESET``
"""
from .handlers import (
    BaseBackupHandler,
    all_handlers,
    clear_registry,
    get_handler,
    register,
)
from .service import (
    KIND_AUTO,
    KIND_MANUAL,
    KIND_PRE_RESET,
    KIND_PRE_RESTORE,
    PROTECTED_KINDS,
    VALID_KINDS,
    create_backup,
    enforce_cap,
    get_backup_dir,
    restore_backup,
)

__all__ = [
    'BaseBackupHandler',
    'KIND_AUTO',
    'KIND_MANUAL',
    'KIND_PRE_RESET',
    'KIND_PRE_RESTORE',
    'PROTECTED_KINDS',
    'VALID_KINDS',
    'all_handlers',
    'clear_registry',
    'create_backup',
    'enforce_cap',
    'get_backup_dir',
    'get_handler',
    'register',
    'restore_backup',
]
