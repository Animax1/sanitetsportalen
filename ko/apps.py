"""App-konfigurasjon for KO-modulen."""
from django.apps import AppConfig


class KoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ko'
    verbose_name = 'KO'
