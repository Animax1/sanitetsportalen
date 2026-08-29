"""Arkiv-handler for pasientmodulen.

Registrerer en ``BaseArkivHandler`` i ``core.arkiv``-registryet, slik at
signatur, integritetssjekk og kollaps kjøres av delt kode.

**Payloaden er bevart ordrett fra før flyttingen.** Nøkkelen `'pasienter'`,
sorteringen på `pasientnummer` og feltutvalget fra ``ARKIVERT_PASIENT_FELTER``
er alle del av SHA-256-signaturen som ligger lagret på hvert
``VaktArkiv``-objekt i produksjon. Endres ett tegn, melder samtlige arkiver
tukling uten at noe er rørt. ``ArkivSignaturLaastTests`` låser verdiene.
"""
from __future__ import annotations

from core.arkiv import BaseArkivHandler, register


class PasientArkivHandler(BaseArkivHandler):
    """Arkivering av vakter i pasientmodulen."""

    slug = 'patients'
    display_name = 'Vaktarkiv (pasienter)'

    # Modellen `kollaps_arkiv`-kommandoen finner kandidater i. `VaktArkiv`
    # arver ikke `AbstractArkiv` — se begrunnelsen i core/arkiv/models.py —
    # men har `importert_at` og `kollapset_at`, som er alt default-utvalget
    # trenger.
    arkiv_model = None   # settes under, når modellen kan importeres

    # `core.backup`-handleren som dekker arkivmodellene. Kollaps nektes med
    # mindre det finnes en backup med denne slugen fra etter at arkivet ble
    # opprettet — se ArkivBackupHandler i patients/backup.py.
    backup_slug = 'arkiv'

    # 24 måneder. Dekker to hele sesonger, slik at årets vakt kan
    # sammenlignes med fjorårets under planleggingen før radnivået forsvinner.
    retention_dager = 730

    def sha_payload(self, arkiv, rader):
        """Radnivå-payload. Formen er frosset — se modul-docstringen."""
        return {
            'arkiv_id': arkiv.pk,
            'arrangement_navn': arkiv.arrangement_navn,
            'year_snapshot': arkiv.year_snapshot,
            'pasienter': sorted(rader, key=lambda p: p['pasientnummer']),
        }

    def aggregat_sha_payload(self, arkiv, aggregat):
        """Aggregat-payload. Også frosset."""
        return {
            'arkiv_id': arkiv.pk,
            'arrangement_navn': arkiv.arrangement_navn,
            'year_snapshot': arkiv.year_snapshot,
            'aggregat': aggregat,
        }

    def rad_dicts(self, arkiv):
        from .services import _arkiv_pasienter_dicts
        return _arkiv_pasienter_dicts(arkiv)

    def antall_rader(self, arkiv):
        """Tell i basen framfor å bygge dictene — tørrkjøringen trenger bare
        tallet, og et arkiv kan ha tusen rader."""
        from .models import ArkivertPasient
        return ArkivertPasient.objects.filter(arkiv=arkiv).count()

    def bygg_aggregat(self, arkiv):
        from .services import bygg_aggregat
        return bygg_aggregat(arkiv)

    def slett_rader(self, arkiv):
        from .models import ArkivertPasient
        return ArkivertPasient.objects.filter(arkiv=arkiv).delete()[0]


def register_handlers() -> None:
    """Kalles fra ``patients.apps.PatientsConfig.ready()``.

    Modellen settes her og ikke i klassekroppen: modulen importeres fra
    `apps.ready()`, og en import av `models` på toppnivå ville kjørt før
    appregisteret var klart.
    """
    from .models import VaktArkiv

    PasientArkivHandler.arkiv_model = VaktArkiv
    register(PasientArkivHandler())
