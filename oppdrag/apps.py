"""App-konfigurasjon for oppdrag-appen."""
from django.apps import AppConfig


class OppdragConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'oppdrag'
    verbose_name = 'Oppdrag'

    def ready(self):
        # Audit-signalene kobles her, slik at de er på plass fra første
        # lagring. Se `oppdrag/signals.py` — særlig `FELT_UTEN_VERDILOGGING`.
        from . import signals  # noqa: F401

        # Statistikkregisteret (fase 6). Uten registreringen finnes ikke
        # kilden, og statistikksiden viser ingen oppdragsfane.
        from .statistikk import register_handlers
        register_handlers()

        # Arkiv- og backup-registrene (fase 7). Arkivhandleren gir signatur,
        # verifisering og kollaps; backuphandlerne gir dekning — og
        # arkivbackupen er dessuten sperren foran den irreversible kollapsen.
        from .arkiv import register_handlers as register_arkiv_handlers
        register_arkiv_handlers()

        from .backup import register_handlers as register_backup_handlers
        register_backup_handlers()
