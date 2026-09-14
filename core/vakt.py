"""Portalens scope: hvilken vakt nye rader hører til (flyttet hit 14. sep. 2026).

Vakta er delt av alle modulene — pasienter, oppdrag og vaktlister peker alle på
den. Funksjonene lå i `patients/services.py` fordi `AppSetting`-pekeren gjorde
det, og da måtte oppdragsmodulen, vaktlista og statistikken importere
*pasientmodulen* for å vite hvilken vakt de var i. Se
`docs/PLAN_FLYTTING_TIL_CORE.md`.

Ingen av de to rører pasientdata. De leser `core.Vakt` og `core.AppSetting`, og
hører derfor hjemme her.
"""
from __future__ import annotations

from django.utils import timezone as djtz

from core.models import AppSetting, Vakt
from core.validators import current_local_year


def vakt_for_year(year):
    """Vakta for et år — finn den, eller lag den.

    Lat opprettelse — en fersk installasjon skal ikke trenge et oppsettsteg
    for at registrering skal virke. Navnet blir årstallet — samme ærlighet som
    backfillen: vi vet ikke hva vakta heter, og påstår det ikke. Admin endrer
    navnet når hun vet det.

    Finnes flere vakter for året (mulig fra deploy 2), velges den nyeste —
    men før deploy 2 finnes maks én per år.
    """
    vakt = Vakt.objects.filter(year=year).order_by('-startet').first()
    if vakt is None:
        vakt = Vakt.objects.create(
            navn=str(year), year=year, startet=djtz.now())
    return vakt


def hent_aktiv_vakt():
    """Vakta nye rader skal peke på. Aldri ``None``.

    `AppSetting['aktiv_vakt_id']` er fasit når den finnes og peker på noe
    ekte. Gjør den ikke det — fersk installasjon, slettet rad, eller en
    rollback som tok vaktene — faller vi tilbake til vakta for aktivt år og
    reparerer pekeren. Fail-open i samme retning som resten av huset: en
    pasient som ikke lar seg registrere fordi en peker er borte, er verre enn
    en peker som må repareres.
    """
    raa = AppSetting.get('aktiv_vakt_id', None)
    if raa is not None:
        try:
            return Vakt.objects.get(pk=int(raa))
        except (Vakt.DoesNotExist, TypeError, ValueError):
            pass

    vakt = vakt_for_year(current_local_year())
    AppSetting.set('aktiv_vakt_id', vakt.pk)
    return vakt
