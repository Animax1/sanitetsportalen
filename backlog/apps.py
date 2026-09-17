"""App-konfigurasjon for backlog-modulen."""
from django.apps import AppConfig


class BacklogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backlog'
    verbose_name = 'Backlog'

    def ready(self):
        # Backup-dekning fra første lagring. Vaktlistemodulen sto uten backup i
        # det hele tatt fra den gikk i prod til 13. sep. 2026, og det ble
        # oppdaget ved en gjennomgang og ikke av noe rødt — en ny modul med en
        # tabell registrerer derfor handleren i samme commit som modellen.
        from .backup import register_handlers
        register_handlers()
