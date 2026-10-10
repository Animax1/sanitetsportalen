"""Oppdragsmodulens felt på portalinnstillingssiden: fristen på fritekst.

Se `core/portalinnstillinger.py` for registeret og `oppdrag/fritekstfrist.py`
for regelen. Fraværende felt er «behold dagens verdi», tomt felt er en feil —
samme skille som KO (`ko/portalinnstillinger.py`).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.portalinnstillinger import BasePortalinnstillingHandler, register


class OppdragInnstillinger(BasePortalinnstillingHandler):
    slug = 'oppdrag'
    order = 15
    mal = 'oppdrag/portalinnstillinger.html'

    def kontekst(self) -> dict:
        from . import fritekstfrist

        return {
            'oppdrag_fritekst_dager': fritekstfrist.frist_dager(),
            'oppdrag_fritekst_dager_min': fritekstfrist.DAGER_MIN,
            'oppdrag_fritekst_dager_maks': fritekstfrist.DAGER_MAKS,
        }

    def valider(self, post) -> dict:
        """Les fristen og prøv den. **Skriv ingenting her.**"""
        from . import fritekstfrist

        raa = post.get('oppdrag_fritekst_dager')
        if raa is None:
            return {}
        try:
            dager = int(str(raa).strip())
        except (TypeError, ValueError):
            raise ValidationError('Fristen på oppdragsnotatet må være et helt tall dager.') from None
        if not fritekstfrist.DAGER_MIN <= dager <= fritekstfrist.DAGER_MAKS:
            raise ValidationError(
                f'Fristen på oppdragsnotatet må være mellom {fritekstfrist.DAGER_MIN} '
                f'og {fritekstfrist.DAGER_MAKS} dager.')
        return {'dager': dager}

    def lagre(self, verdier: dict) -> None:
        from core.models import AppSetting

        from . import fritekstfrist

        if 'dager' in verdier:
            AppSetting.set(fritekstfrist.DAGER_NOKKEL, verdier['dager'])


def register_handlers() -> None:
    register(OppdragInnstillinger())
