"""App-konfigurasjon for audit."""
from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit'
    verbose_name = 'Revisjonslogg'

    def ready(self):
        """Last inn signal-håndterere ved app-oppstart.

        ``audit.signals.fyll_app_label`` er en pre_save-handler som auto-fyller
        ``AuditLog.app_label`` fra ``table_name`` når caller ikke setter det
        eksplisitt. Importeres her for å registrere @receiver-dekoratorene.
        """
        from . import signals  # noqa: F401  (import for side-effect: registrerer signaler)
