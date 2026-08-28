"""App-konfigurasjon for statistikk-appen."""
from django.apps import AppConfig


class StatistikkConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'statistikk'
    verbose_name = 'Statistikk'
