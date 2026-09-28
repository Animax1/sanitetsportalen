"""Lagenes registreringer når en tidligere vakt slettes (`core/vaktsletting.py`)."""
from __future__ import annotations

from core.vaktsletting import BaseVaktslettHandler, register


class ParkVaktsletting(BaseVaktslettHandler):
    slug = 'park'
    # Først: registreringene peker på vaktlistas ressurser.
    order = 10
    modeller = ('park.Registrering',)

    def antall(self, vakt):
        from .models import Registrering
        return [('lagregistreringer', Registrering.objects.filter(vakt=vakt).count())]

    def slett(self, vakt) -> None:
        from .models import Registrering
        Registrering.objects.filter(vakt=vakt).delete()


def register_handlers() -> None:
    register(ParkVaktsletting())
