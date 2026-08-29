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
