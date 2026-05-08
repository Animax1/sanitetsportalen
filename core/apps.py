"""Django-konfigurasjon for core-appen.

Fase 3a: ``ready()`` kobler ``post_migrate``-signal til
``ModuleSettings.ensure_defaults_exist()`` slik at alle registrerte moduler
har en rad i ``core_modulesettings`` etter hver migrasjon.

Vi gjør IKKE ``ensure_defaults_exist()`` direkte i ``ready()``, fordi
ready() kjører før migrasjoner og før tabellen finnes (gir
ProgrammingError ved første ``manage.py migrate``). post_migrate er det
offisielle hookpunktet for "data som må finnes etter migrate".
"""
from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _ensure_module_settings_defaults(sender, **kwargs):
    """post_migrate-handler som sikrer at hver modul har en ModuleSettings-rad.

    Kjører kun når core-appen selv er målet for migreringen — ikke for hver
    annen apps post_migrate (ellers kjører den én gang per app, unødvendig
    dyrt selv om det er idempotent).
    """
    if sender.name != 'core':
        return
    # Lazy import: modeller må kun importeres etter at app-registret er ferdig.
    from core.models import ModuleSettings
    ModuleSettings.ensure_defaults_exist()


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Sanitetsportal – fellesprimitiver'

    def ready(self):
        post_migrate.connect(_ensure_module_settings_defaults, sender=self)
