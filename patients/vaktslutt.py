"""Pasientene ved «Avslutt vakt»: arkiveres, så slettes de (28. sep. 2026).

Se `core/vaktslutt.py`. Fram til nå slettet avslutningen pasientene etter bare
en backup — arkivet var en egen knapp man måtte huske å trykke *før*. Glemte
man det, fantes vakta bare i en backupfil: ingen statistikk, ingen aggregat
etter 24 måneder. Nå arkiveres de alltid, i samme transaksjon som slettingen.
"""
from __future__ import annotations

from core.vaktslutt import BaseVaktsluttHandler, register


class PasientVaktslutt(BaseVaktsluttHandler):
    slug = 'patients'
    etikett = 'pasienter'
    entall = 'pasient'
    backup_slug = 'patients'
    order = 10

    def antall(self, vakt) -> int:
        from .models import Patient
        return Patient.objects.filter(vakt=vakt).count()

    def avslutt(self, vakt, bruker, request=None) -> int:
        from core.arkiv import logg_arkivhendelse

        from .models import Patient, VaktArkiv
        from .services import arkiver_aktiv_vakt

        if Patient.objects.filter(vakt=vakt, is_active=True).exists():
            arkiv, antall = arkiver_aktiv_vakt(vakt.navn, '', bruker, vakt=vakt)
            logg_arkivhendelse(VaktArkiv, 'arkiv_lagret',
                               f'arkiv_id={arkiv.pk}, tittel={arkiv.tittel}, ved avslutning',
                               request=request, record_id=arkiv.pk)
        slettet, _ = Patient.objects.filter(vakt=vakt).delete()
        return slettet


def register_handlers() -> None:
    """Kalles fra `PatientsConfig.ready()`."""
    register(PasientVaktslutt())
