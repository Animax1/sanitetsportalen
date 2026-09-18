"""KOs felter på portalinnstillingssiden: oppbevaringstiden for loggen.

Se `core/portalinnstillinger.py` for registeret, og `ko/services.py` for
hvorfor fristen er en `AppSetting` og ikke en Railway-variabel.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.portalinnstillinger import BasePortalinnstillingHandler, register


class KoInnstillinger(BasePortalinnstillingHandler):
    slug = 'ko'
    order = 20
    mal = 'ko/portalinnstillinger.html'

    def kontekst(self) -> dict:
        from ko import services

        return {
            'ko_logg_dager': services.oppbevaringsdager(),
            'ko_logg_dager_min': services.DAGER_MIN,
            'ko_logg_dager_maks': services.DAGER_MAKS,
            'ko_chat_tillatt': services.chat_tillatt(),
        }

    def valider(self, post) -> dict:
        """Les fristen og prøv den. **Skriv ingenting her.**

        `valider()` og `lagre()` er delt i to fordi navnet skrives på `Vakt` og
        resten i `AppSetting`, uten en transaksjon mellom seg: en modul som
        nekter skal stoppe hele innsendingen, også portalens egne felter.

        **Fraværende felt og tomt felt er to forskjellige ting**, og skillet er
        ikke pedanteri:

        - *Fraværende* betyr at innsendingen ikke kom fra denne sida — en
          eldre mal, et skript, en test. Da er svaret «behold dagens verdi».
          Et avslag her ville tatt ned **hele** innstillingssiden, inkludert
          portalens eget arrangementsnavn og de andre modulenes felter, fordi
          én modul ikke fant feltet sitt. En modul som kan lamme naboene sine
          ved å mangle en nøkkel, er feil bygget.
        - *Tomt* betyr at et menneske har tømt feltet, og da skal hun få vite
          at en oppbevaringstid ikke kan være ingenting.
        """
        from ko import services

        ut = {}
        # Chat-bryteren (§4.5). En avkryssing sendes bare når den er krysset
        # av, så «fraværende» må leses sammen med et skjult følgefelt:
        # `ko_chat_sendt` sier at sida hadde feltet, og da er fravær «av».
        if post.get('ko_chat_sendt') is not None:
            ut['chat'] = post.get('ko_chat_tillatt') is not None
        raa = post.get('ko_logg_dager')
        if raa is None:
            return ut
        try:
            dager = int(str(raa).strip())
        except (TypeError, ValueError):
            raise ValidationError(
                'Oppbevaringstiden for KO-loggen må være et helt tall dager.'
            ) from None
        if not services.DAGER_MIN <= dager <= services.DAGER_MAKS:
            raise ValidationError(
                f'Oppbevaringstiden for KO-loggen må være mellom '
                f'{services.DAGER_MIN} og {services.DAGER_MAKS} dager.')
        ut['dager'] = dager
        return ut

    def lagre(self, verdier: dict) -> None:
        from core.models import AppSetting
        from ko import services

        if 'chat' in verdier:
            AppSetting.set(services.CHAT_NOKKEL, 'true' if verdier['chat'] else 'false')
        if 'dager' in verdier:
            AppSetting.set(services.DAGER_NOKKEL, verdier['dager'])


def register_handlers() -> None:
    register(KoInnstillinger())
