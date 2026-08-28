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
