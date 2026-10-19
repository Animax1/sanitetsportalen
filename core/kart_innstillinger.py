"""Kortet «Kartet» på `/admin/innstillinger/` (André, 7. okt. 2026).

To felt: **«Åpne kartet» fra KO** (19. okt. 2026, `docs/PLAN_FELLES_INNLOGGING.md`), av som
standard, og **«Delt posisjon vises i kartet»** — hvor lenge en posisjon bil eller lag har delt med
«Send posisjon» står under «OBS: Posisjon delt» i kart.sanitet.net. Felles for bil og lag, så det
hører til kartkoblingen i `core` og ikke til én modul. Registreres fra `core.apps.ready()` i
samme register som modulenes kort (`core/portalinnstillinger.py`); fraværende felt er «behold»,
tomt felt er en feil, som hos modulene.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.portalinnstillinger import BasePortalinnstillingHandler, register


class KartInnstillinger(BasePortalinnstillingHandler):
    slug = 'kart'
    order = 5   # før modulenes kort: kartet gjelder flere av dem
    mal = 'core/portalinnstillinger_kart.html'

    def kontekst(self) -> dict:
        from core import kartkobling

        return {
            'kart_delt_posisjon': kartkobling.delt_posisjon_min(),
            'kart_delt_posisjon_min': kartkobling.DELT_VARIGHET_MIN,
            'kart_delt_posisjon_maks': kartkobling.DELT_VARIGHET_MAKS,
            'kart_konfigurert': kartkobling.er_konfigurert(),
            # «Åpne kartet» fra KO (19. okt. 2026). Global og bare admin: `portalfelt` er tom.
            'kart_innlogging': kartkobling.innlogging_slatt_paa(),
            'kart_innlogging_satt_opp': kartkobling.innlogging_satt_opp(),
        }

    def valider(self, post) -> dict:
        """Les og prøv. **Skriv ingenting her** — se `core/portalinnstillinger.py`."""
        from core import kartkobling

        ut = {}
        # En avkryssing sendes bare når den er krysset av, så «fraværende» leses sammen med det
        # skjulte følgefeltet — samme form som KOs chat-bryter. Uten følgefeltet er det «behold».
        if post.get('kart_innlogging_sendt') is not None:
            ut['innlogging'] = post.get('kart_innlogging') is not None
        raa = post.get('kart_delt_posisjon')
        if raa is None:
            return ut
        try:
            minutter = int(str(raa).strip())
        except (TypeError, ValueError):
            raise ValidationError(
                'Hvor lenge en delt posisjon vises i kartet, må være et helt tall minutter.') from None
        if not kartkobling.DELT_VARIGHET_MIN <= minutter <= kartkobling.DELT_VARIGHET_MAKS:
            raise ValidationError(
                f'Hvor lenge en delt posisjon vises i kartet, må være mellom '
                f'{kartkobling.DELT_VARIGHET_MIN} og {kartkobling.DELT_VARIGHET_MAKS} minutter.')
        return ut | {'delt_posisjon': minutter}

    def lagre(self, verdier: dict) -> None:
        from core import kartkobling
        from core.models import AppSetting

        if 'delt_posisjon' in verdier:
            AppSetting.set(kartkobling.DELT_VARIGHET_NOKKEL, verdier['delt_posisjon'])
        if 'innlogging' in verdier:
            AppSetting.set(kartkobling.INNLOGGING_NOKKEL, 'true' if verdier['innlogging'] else 'false')


def register_handlers() -> None:
    register(KartInnstillinger())
