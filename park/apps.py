"""App-konfigurasjon for park-modulen."""
from django.apps import AppConfig


class ParkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'park'
    verbose_name = 'Lagregistrering'

    def ready(self):
        # Backup-dekning fra første lagring — i samme commit som modellen, som
        # `backlog` og `ko`. Vaktlistemodulen sto uten backup fra den gikk i
        # prod til 13. sep. 2026, og det ble oppdaget ved en gjennomgang.
        from . import backup, portalinnstillinger, statistikk

        backup.register_handlers()
        # Angrefristen og KO-bryteren på /portal-admin/innstillinger/ (pulje 2).
        portalinnstillinger.register_handlers()
        # Fanen «Lag» i /statistikk/ (pulje 3). Uten registreringen finnes
        # ikke kilden, og ingen ser tallene.
        statistikk.register_handlers()

        # Sletting av en tidligere vakt (28. sep. 2026, `core/vaktsletting.py`).
        from .vaktsletting import register_handlers as register_vaktsletting
        register_vaktsletting()
