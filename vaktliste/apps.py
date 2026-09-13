"""App-konfigurasjon for vaktliste-appen."""
from django.apps import AppConfig


class VaktlisteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vaktliste'
    verbose_name = 'Vaktliste'

    def ready(self):
        # Audit-signalene kobles her, slik at de er på plass fra første
        # lagring. Se `vaktliste/signals.py` — særlig unntaket for `notat`.
        from . import signals  # noqa: F401

        # Backup-dekning (13. sep. 2026). Modulen sto uten i det hele tatt
        # fram til nå — korps, mannskap med telefon og ISSI, ressursene og
        # vaktpostene lå utenfor alle filer siden appen gikk i prod.
        from .backup import register_handlers as register_backup_handlers
        register_backup_handlers()
