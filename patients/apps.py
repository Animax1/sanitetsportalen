"""App-konfigurasjon for patients – kobler signals i ready()."""
from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'patients'
    verbose_name = 'Pasienter'

    def ready(self):
        """Koble signals når appen er klar."""
        import patients.signals  # noqa: F401
