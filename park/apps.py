"""App-konfigurasjon for park-modulen."""
from django.apps import AppConfig


class ParkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'park'
    verbose_name = 'Park'

    def ready(self):
        # Backup-dekning fra første lagring — i samme commit som modellen, som
        # `backlog` og `ko`. Vaktlistemodulen sto uten backup fra den gikk i
        # prod til 13. sep. 2026, og det ble oppdaget ved en gjennomgang.
        from . import backup, portalinnstillinger

        backup.register_handlers()
        # Angrefristen og KO-bryteren på /portal-admin/innstillinger/ (pulje 2).
        portalinnstillinger.register_handlers()
