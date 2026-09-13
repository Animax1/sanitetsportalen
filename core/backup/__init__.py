"""Per-modul backup/restore-system.

Hovedeksport:

- ``BaseBackupHandler`` — subklasses i hver modul som vil ha backup
- ``register(handler)`` — registrer handler (kall fra apps.ready())
- ``create_backup(slug, kind, user, note)`` — lag en backup
- ``restore_backup(backup, user)`` — gjenopprett en backup
- ``enforce_cap(slug, max_backups)`` — håndhev cap på antall backups
- ``klokke`` — tråden som utløser automatisk backup (se modulens docstring for
  hvorfor det ikke er en cron-tjeneste)
- Konstanter: ``KIND_AUTO``, ``KIND_MANUAL``, ``KIND_PRE_RESTORE``,
  ``KIND_PRE_RESET``
"""
from .handlers import (
    BaseBackupHandler,
    all_handlers,
    clear_registry,
    get_handler,
    registrer_alle_moduler,
    register,
    utled_restore_models,
)
from . import klokke
from .full import FullBackupHandler
from .full import register_handlers as _register_full
from .portal import PortalBackupHandler
from .portal import register_handlers as _register_portal
from .klokke import (
    kjor_forfalte,
    kjor_plan,
    start_klokke,
    vakthund,
    varsle_stoppet_klokke,
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

def register_handlers() -> None:
    """Registrer `core` sine egne handlere — portalfila og den hele basen.

    Ligger her og ikke bare i `apps.py` fordi `registrer_alle_moduler()`
    importerer `<app>.backup` og kaller modulens `register_handlers`. For
    `core` er «`core.backup`» denne pakka, og uten funksjonen her ville en test
    som kaller `clear_registry()` fått tilbake alle modulene *unntatt* portalen
    og den hele — og feilen dukket opp i en helt annen fil, som den gangen
    oppdragsmodulen forsvant fra registeret midt i suiten.
    """
    _register_portal()
    _register_full()


__all__ = [
    'BaseBackupHandler',
    'FullBackupHandler',
    'PortalBackupHandler',
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
    'kjor_forfalte',
    'kjor_plan',
    'klokke',
    'register_handlers',
    'registrer_alle_moduler',
    'register',
    'restore_backup',
    'start_klokke',
    'utled_restore_models',
    'vakthund',
    'varsle_stoppet_klokke',
]
