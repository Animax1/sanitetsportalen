"""App-konfigurasjon for KO-modulen."""
from django.apps import AppConfig


class KoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ko'
    verbose_name = 'KO'

    def ready(self):
        """Registrer handlerne og koble signalene.

        Backup registreres fra `ready()` og ikke fra en liste i `core`, slik
        registeret er bygget: **registeret er fasit for hvilke moduler som
        finnes, ikke plantabellen.** En modul uten plan får en med
        standardverdier første gang klokka ser handleren.
        """
        from . import backup, opprydding, portalinnstillinger, signals, statistikk  # noqa: F401

        backup.register_handlers()
        opprydding.register_handlers()
        portalinnstillinger.register_handlers()
        # Statistikkfanen «KO» (pulje 7a). Uten registreringen finnes ikke
        # kilden, og statistikksiden viser ingen KO-fane.
        statistikk.register_handlers()
