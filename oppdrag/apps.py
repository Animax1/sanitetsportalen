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

        # Driftsdashbordet (14. sep. 2026). Tallene fra tavla hentes gjennom
        # registeret, ikke ved at `core` importerer oppdragsmodulen. Se
        # `core/driftstatus.py`.
        from .driftstatus import register_handlers as register_driftstatus
        register_driftstatus()

        # Endringsnummeret (24. sep. 2026). Uten registreringen svarer
        # `/api/endringer/` ingenting for `oppdrag`, og sentralbordet henter
        # bare på sikkerhetsnettet hvert 30. sekund.
        from .endringer import register_handlers as register_endringer
        register_endringer()
