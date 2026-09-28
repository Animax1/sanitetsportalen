"""Oppdragene når en tidligere vakt slettes (`core/vaktsletting.py`).

Gjennom `services.nullstill_vakt`, som KO-innstillingenes «Nullstill» — den
løser opp korreksjonene før oppdragene slettes (`korrigerer` er PROTECT) og tar
telleren. Vaktmodusperiodene (passiv vakt) går med.
"""
from __future__ import annotations

from core.vaktsletting import BaseVaktslettHandler, register


class OppdragVaktsletting(BaseVaktslettHandler):
    slug = 'oppdrag'
    # Før KO: oppdragene peker på KO-hendelsene.
    order = 30
    modeller = ('oppdrag.Oppdrag', 'oppdrag.Vaktmodusperiode')

    def antall(self, vakt):
        from .models import Oppdrag
        return [('oppdrag', Oppdrag.objects.filter(vakt=vakt).count())]

    def slett(self, vakt) -> None:
        from . import services
        from .models import Vaktmodusperiode
        services.nullstill_vakt(vakt)
        Vaktmodusperiode.objects.filter(vakt=vakt).delete()


def register_handlers() -> None:
    register(OppdragVaktsletting())
