"""Vaktlistas felter på portalinnstillingssiden (14. sep. 2026).

Lå inne i `core/views_admin.py` som en direkte import av `vaktliste.fil` fram
til registeret ble bygget. Se `core/portalinnstillinger.py`.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.portalinnstillinger import BasePortalinnstillingHandler, register


class VaktlistefilInnstillinger(BasePortalinnstillingHandler):
    slug = 'vaktliste'
    order = 10
    mal = 'vaktliste/portalinnstillinger.html'

    def kontekst(self) -> dict:
        from vaktliste import fil, pauser

        return {
            'vaktliste_fil_mottakere': '\n'.join(fil.mottakere()),
            'vaktliste_fil_ved_drift': fil.sendes_ved_drift(),
            'vaktliste_fil_intervall_min': fil.intervall_minutter(),
            'vaktliste_fil_bare_endret': fil.bare_ved_endring(),
            'vaktliste_fil_maks_intervall': fil.MAKS_INTERVALL_MIN,
            'vaktliste_vis_pauser': pauser.vises_for_mannskapet(),
        }

    def valider(self, post) -> dict:
        """Mottakerne og intervallet, lest og prøvd — ingenting skrives.

        `valider_mottakere` kaster `ValidationError` selv; intervallet prøves
        her fordi `0` er en gyldig verdi som betyr «av», og et tomt felt skal
        leses som nettopp det og ikke som en feil.
        """
        from vaktliste import fil

        mottakere = fil.valider_mottakere(post.get('vaktliste_fil_mottakere') or '')

        raa = (post.get('vaktliste_fil_intervall_min') or '0').strip()
        try:
            intervall = int(raa)
            if not 0 <= intervall <= fil.MAKS_INTERVALL_MIN:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError(
                f'Intervallet må være et helt tall mellom 0 og '
                f'{fil.MAKS_INTERVALL_MIN} minutter.') from None

        return {
            'mottakere': mottakere,
            'ved_drift': '1' if post.get('vaktliste_fil_ved_drift') else '0',
            'intervall': intervall,
            'bare_endret': '1' if post.get('vaktliste_fil_bare_endret') else '0',
            'vis_pauser': '1' if post.get('vaktliste_vis_pauser') else '0',
        }

    def lagre(self, verdier: dict) -> None:
        from core.models import AppSetting
        from vaktliste import fil, pauser

        AppSetting.set(fil.MOTTAKERE_NOKKEL, '\n'.join(verdier['mottakere']))
        AppSetting.set(fil.VED_DRIFT_NOKKEL, verdier['ved_drift'])
        AppSetting.set(fil.INTERVALL_NOKKEL, verdier['intervall'])
        AppSetting.set(fil.BARE_ENDRET_NOKKEL, verdier['bare_endret'])
        AppSetting.set(pauser.VIS_NOKKEL, verdier['vis_pauser'])


def register_handlers() -> None:
    register(VaktlistefilInnstillinger())
