"""Statistikk-handler for pasientmodulen.

Registrerer en ``BaseStatistikkHandler`` i ``core.stats``-registryet. Fram til
fase 6 av oppdragsmodulen importerte statistikkappen ``patients.services``
direkte; nå spør den registeret, og denne fila er svaret pasientmodulen gir.

**Tallene flyttet ikke.** ``full_stats()`` og ``compute_arkiv_full_stats()``
ligger fortsatt i ``patients/services.py``, og handleren er en tynn kobling
mellom dem og registeret. Det er med vilje: utregningen kjenner pasientdata,
og en flytting ville gjort en refaktorering av koblingen til en refaktorering
av tallene — akseptansekriteriet for fase 6 er at pasientfanen ser lik ut.
"""
from __future__ import annotations

from core.stats import BaseStatistikkHandler, register


class PasientStatistikkHandler(BaseStatistikkHandler):
    """Pasienttallene: fordelinger, tidsanalyse, krysstabeller, tester."""

    slug = 'patients'
    display_name = 'Pasienter'
    # Først i fanerekka: pasientregistreringen er portalens hovedflate, og
    # den fanen var hele statistikksiden fram til denne fasen.
    order = 10

    def full_stats(self, vakt):
        from .services import full_stats
        return full_stats(vakt=vakt)

    def arkiv_full_stats(self, pk):
        """Tallene for én arkivert vakt, eller ``None``.

        Oppslaget ligger her framfor i statistikkappen fordi ``VaktArkiv`` er
        pasientmodulens modell. Slik slipper statistikkappen å importere den
        — det var nettopp den importen fase 6 fjernet.
        """
        from .models import VaktArkiv
        from .services import compute_arkiv_full_stats

        try:
            arkiv = VaktArkiv.objects.get(pk=pk)
        except VaktArkiv.DoesNotExist:
            return None
        return compute_arkiv_full_stats(arkiv)


def register_handlers() -> None:
    """Kalles fra ``patients.apps.PatientsConfig.ready()``."""
    register(PasientStatistikkHandler())
