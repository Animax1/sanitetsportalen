"""App-konfigurasjon for patients – kobler signals i ready()."""
from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'patients'
    verbose_name = 'Pasienter'

    def ready(self):
        """Koble signals + registrer backup- og arkiv-handlere."""
        import patients.signals  # noqa: F401
        from patients.backup import register_handlers
        register_handlers()

        from patients.arkiv import register_handlers as register_arkiv_handlers
        register_arkiv_handlers()
