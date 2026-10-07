"""Parks felter på portalinnstillingssiden: angrefristen, KO-bryteren og hjelpeposisjonens varighet.

Se `core/portalinnstillinger.py` for registeret. **Fraværende felt er «behold»,
tomt felt er en feil** — samme regel som `ko/portalinnstillinger.py`, og av
samme grunn: en modul som nekter fordi feltet mangler, tar ned hele siden.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.portalinnstillinger import BasePortalinnstillingHandler, register


class ParkInnstillinger(BasePortalinnstillingHandler):
    slug = 'park'
    order = 30
    mal = 'park/portalinnstillinger.html'

    def kontekst(self) -> dict:
        from park import services

        return {
            'park_angrefrist': services.angrefrist_min(),
            'park_angrefrist_min': services.ANGREFRIST_MIN,
            'park_angrefrist_maks': services.ANGREFRIST_MAKS,
            'park_ko_posisjon': services.ko_posisjon_paa(),
            'park_hjelp_varighet': services.hjelp_varighet_min(),
            'park_hjelp_varighet_min': services.HJELP_VARIGHET_MIN,
            'park_hjelp_varighet_maks': services.HJELP_VARIGHET_MAKS,
        }

    def valider(self, post) -> dict:
        """Les og prøv. **Skriv ingenting her** — se `ko/portalinnstillinger.py`."""
        from park import services

        ut = {}
        # RISIKOVALG(park-ko-posisjon): bryteren. En avkryssing sendes bare når
        # den er krysset av, så det skjulte følgefeltet sier at sida hadde den.
        if post.get('park_ko_posisjon_sendt') is not None:
            ut['ko_posisjon'] = post.get('park_ko_posisjon') is not None
        raa = post.get('park_angrefrist')
        if raa is not None:
            try:
                minutter = int(str(raa).strip())
            except (TypeError, ValueError):
                raise ValidationError('Angrefristen i lagregistreringen må være et helt tall minutter.') from None
            if not services.ANGREFRIST_MIN <= minutter <= services.ANGREFRIST_MAKS:
                raise ValidationError(
                    f'Angrefristen i lagregistreringen må være mellom {services.ANGREFRIST_MIN} '
                    f'og {services.ANGREFRIST_MAKS} minutter.')
            ut['angrefrist'] = minutter
        raa = post.get('park_hjelp_varighet')
        if raa is not None:
            try:
                minutter = int(str(raa).strip())
            except (TypeError, ValueError):
                raise ValidationError(
                    'Hvor lenge «Vi finner ikke fram» står i kartet, må være et helt tall minutter.'
                ) from None
            if not services.HJELP_VARIGHET_MIN <= minutter <= services.HJELP_VARIGHET_MAKS:
                raise ValidationError(
                    f'Hvor lenge «Vi finner ikke fram» står i kartet, må være mellom '
                    f'{services.HJELP_VARIGHET_MIN} og {services.HJELP_VARIGHET_MAKS} minutter.')
            ut['hjelp_varighet'] = minutter
        return ut

    def lagre(self, verdier: dict) -> None:
        from core.models import AppSetting
        from park import services

        if 'ko_posisjon' in verdier:
            AppSetting.set(services.KO_POSISJON_NOKKEL, 'true' if verdier['ko_posisjon'] else 'false')
        if 'angrefrist' in verdier:
            AppSetting.set(services.ANGREFRIST_NOKKEL, verdier['angrefrist'])
        if 'hjelp_varighet' in verdier:
            AppSetting.set(services.HJELP_VARIGHET_NOKKEL, verdier['hjelp_varighet'])


def register_handlers() -> None:
    register(ParkInnstillinger())
