"""Kortet «Belastningsvarsel» på `/admin/innstillinger/` (18. okt. 2026).

Tersklene for e-posten i `core/belastning.py`. Systemets, ikke en portals — serveren er felles —
så kortet står under systemets innstillinger og bare for global admin (`portalfelt` er tomt).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.portalinnstillinger import BasePortalinnstillingHandler, register

ETIKETTER = {
    'p95_ms': 'Svartid P95',
    'feil_5xx': 'Serverfeil (5xx)',
    'minne_pst': 'Minne',
    'varighet': 'Varighet',
}


class BelastningInnstillinger(BasePortalinnstillingHandler):
    slug = 'belastning'
    order = 6
    mal = 'core/portalinnstillinger_belastning.html'

    def kontekst(self) -> dict:
        from core import belastning

        t = belastning.terskler()
        return {
            'belastning_aktiv': belastning.er_aktiv(),
            'belastning_felt': [
                {'navn': f'belastning_{navn}', 'verdi': t[navn], 'min': minst, 'maks': mest,
                 'etikett': ETIKETTER[navn]}
                for navn, (_nokkel, _std, minst, mest) in belastning.INNSTILLINGER.items()
            ],
        }

    def valider(self, post) -> dict:
        """Les og prøv. **Skriv ingenting her** — se `core/portalinnstillinger.py`."""
        from core import belastning

        ut = {}
        for navn, (_nokkel, _std, minst, mest) in belastning.INNSTILLINGER.items():
            raa = post.get(f'belastning_{navn}')
            if raa is None:
                continue
            try:
                verdi = int(str(raa).strip())
            except (TypeError, ValueError):
                raise ValidationError(f'{ETIKETTER[navn]} må være et helt tall.') from None
            if not minst <= verdi <= mest:
                raise ValidationError(f'{ETIKETTER[navn]} må være mellom {minst} og {mest}.')
            ut[navn] = verdi
        if 'belastning_sendt' in post:
            # Avkrysningsboksen sendes bare når den er krysset av; skjult felt sier at kortet var med.
            ut['aktiv'] = post.get('belastning_aktiv') == '1'
        return ut

    def lagre(self, verdier: dict) -> None:
        from core import belastning
        from core.models import AppSetting

        for navn, (nokkel, *_rest) in belastning.INNSTILLINGER.items():
            if navn in verdier:
                AppSetting.set(nokkel, verdier[navn])
        if 'aktiv' in verdier:
            AppSetting.set(belastning.AKTIV_NOKKEL, '1' if verdier['aktiv'] else '0')


def register_handlers() -> None:
    register(BelastningInnstillinger())
