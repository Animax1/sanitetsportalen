"""Oppdragene ved «Avslutt vakt»: arkiveres og tømmes (28. sep. 2026).

Se `core/vaktslutt.py`. Arkiveringen er den samme som knappen i oppdragsmodulen
alltid har gjort (`arkiv.arkiver_vakt`, som tømmer tavla og historikken og
nullstiller nummeret); nå skjer den også når vakta avsluttes, så ingen trenger
å huske den.

**Sperren er den samme som knappens:** et oppdrag som står på tavla, ville
blitt slettet halvveis — en hendelse uten slutt. Da kan ikke vakta avsluttes
før det er lagt i historikken eller slettet.
"""
from __future__ import annotations

from core.vaktslutt import BaseVaktsluttHandler, register


class OppdragVaktslutt(BaseVaktsluttHandler):
    slug = 'oppdrag'
    etikett = 'oppdrag'
    backup_slug = 'oppdrag'
    order = 20

    def antall(self, vakt) -> int:
        from .models import Oppdrag
        return Oppdrag.objects.filter(vakt=vakt).count()

    def sperre(self, vakt) -> str:
        from .models import Oppdrag
        paa_tavla = Oppdrag.objects.filter(vakt=vakt, historikk_fra__isnull=True).count()
        if not paa_tavla:
            return ''
        return (f'{paa_tavla} oppdrag står fortsatt på tavla. Legg dem i historikken '
                'eller slett dem før vakta avsluttes.')

    def avslutt(self, vakt, bruker, request=None) -> int:
        from core.arkiv import logg_arkivhendelse

        from .arkiv import arkiver_vakt
        from .models import OppdragArkiv

        if not self.antall(vakt):
            return 0
        arkiv, antall = arkiver_vakt(vakt, '', bruker)
        logg_arkivhendelse(OppdragArkiv, 'arkiv_lagret',
                           f'arkiv_id={arkiv.pk}, vakt={vakt.navn}, antall={antall}, '
                           'ved avslutning', request=request, record_id=arkiv.pk)
        return antall


def register_handlers() -> None:
    """Kalles fra `OppdragConfig.ready()`."""
    register(OppdragVaktslutt())
