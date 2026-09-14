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

        # Driftsdashbordet (14. sep. 2026). Uten registreringen viser
        # `/portal-admin/server-status/` ingen vaktlister i drift og ingen
        # siste utsending — og `core` skal ikke kjenne modulen ved navn for
        # å hente dem. Se `core/driftstatus.py`.
        from .driftstatus import register_handlers as register_driftstatus
        register_driftstatus()

        # Portalinnstillingene (14. sep. 2026). Feltene for vaktlista på
        # e-post er modulens, og registreres derfor herfra — `core` skal ikke
        # importere `vaktliste.fil` for å tegne sitt eget skjema. Se
        # `core/portalinnstillinger.py`.
        from .portalinnstillinger import register_handlers as register_innstillinger
        register_innstillinger()
