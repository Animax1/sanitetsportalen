"""App-konfigurasjon for patients – kobler signals i ready()."""
from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'patients'
    verbose_name = 'Pasienter'

    def ready(self):
        """Koble signals + registrer backup-handler når appen er klar."""
        import patients.signals  # noqa: F401
        from patients.backup import register_handlers
        register_handlers()
