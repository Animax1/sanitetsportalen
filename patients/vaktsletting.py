"""Pasientene når en tidligere vakt slettes (`core/vaktsletting.py`).

Normalt er de alt tømt av «Avslutt vakt»; her ligger de som står igjen — en
gjenåpnet vakt, eller en fra før avslutningen arkiverte. Telleren går med, som
når oppdragsmodulen nullstiller sin.
"""
from __future__ import annotations

from core.vaktsletting import BaseVaktslettHandler, register


class PasientVaktsletting(BaseVaktslettHandler):
    slug = 'patients'
    order = 20
    modeller = ('patients.Patient',)

    def antall(self, vakt):
        from .models import Patient
        return [('pasienter', Patient.objects.filter(vakt=vakt).count())]

    def slett(self, vakt) -> None:
        from core.models import AppSetting

        from .models import Patient
        from .services import _pasientnr_nokkel
        Patient.objects.filter(vakt=vakt).delete()
        AppSetting.objects.filter(key=_pasientnr_nokkel(vakt)).delete()


def register_handlers() -> None:
    register(PasientVaktsletting())
