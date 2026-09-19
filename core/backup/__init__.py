"""Per-modul backup/restore-system.

Hovedeksport:

- ``BaseBackupHandler`` — subklasses i hver modul som vil ha backup
- ``register(handler)`` — registrer handler (kall fra apps.ready())
- ``create_backup(slug, kind, user, note)`` — lag en backup
- ``restore_backup(backup, user)`` — gjenopprett en backup
- ``enforce_cap(slug, max_backups)`` — håndhev cap på antall backups
- ``GJENOPPRETTINGSREKKEFOLGE`` — rekkefølgen modulfilene tas i, i en tom base
  (se ``rekkefolge``-modulens docstring for hvorfor den ligger i kode)
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
from .rekkefolge import (
    avvik as rekkefolge_avvik,
    bindinger as rekkefolge_bindinger,
    GJENOPPRETTINGSREKKEFOLGE,
    som_pilsetning,
    UTEN_BINDING,
)
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
    create_backup,
    enforce_cap,
    GAMLE_MODELLNAVN,
    UTGAATTE_FELT,
    UTGAATTE_MODELLER,
    fjern_utgaatte,
    get_backup_dir,
    KIND_AUTO,
    KIND_MANUAL,
    KIND_PRE_RESET,
    KIND_PRE_RESTORE,
    oversett_modellnavn,
    PROTECTED_KINDS,
    restore_backup,
    slug_fra_filnavn,
    VALID_KINDS,
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
    'GAMLE_MODELLNAVN',
    'UTGAATTE_FELT',
    'UTGAATTE_MODELLER',
    'fjern_utgaatte',
    'GJENOPPRETTINGSREKKEFOLGE',
    'UTEN_BINDING',
    'rekkefolge_avvik',
    'rekkefolge_bindinger',
    'som_pilsetning',
    'oversett_modellnavn',
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
    'slug_fra_filnavn',
    'start_klokke',
    'utled_restore_models',
    'vakthund',
    'varsle_stoppet_klokke',
]
