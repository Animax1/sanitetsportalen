"""KO-loggen og tavla når en tidligere vakt slettes (`core/vaktsletting.py`).

Pekerne mellom KO-modellene er `SET_NULL` eller `CASCADE`, så rekkefølgen her
er for lesbarheten: loggen, så det loggen handler om.
"""
from __future__ import annotations

from core.vaktsletting import BaseVaktslettHandler, register


class KoVaktsletting(BaseVaktslettHandler):
    slug = 'ko'
    order = 40
    modeller = ('ko.Logglinje', 'ko.Hendelse', 'ko.Tavleplassering', 'ko.PlanlagtPause',
                'ko.Programpost', 'ko.Programendring')

    def _modeller(self):
        from django.apps import apps
        return [apps.get_model(etikett) for etikett in self.modeller]

    def antall(self, vakt):
        from .models import Hendelse, Logglinje
        return [('KO-logglinjer', Logglinje.objects.filter(vakt=vakt).count()),
                ('KO-hendelser', Hendelse.objects.filter(vakt=vakt).count())]

    def slett(self, vakt) -> None:
        for modell in self._modeller():
            modell.objects.filter(vakt=vakt).delete()


def register_handlers() -> None:
    register(KoVaktsletting())
