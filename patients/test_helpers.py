"""Delte testhjelpere for vakt-scoping.

Fram til deploy 2 satte testene `AppSetting['active_year']` og opprettet rader
med `year=`. Begge deler er borte: scopet er vakta. Denne hjelperen er den ene
veien testene skal sette scope på — å gjøre en vakt aktiv for hånd i hver
testfil ville gitt like mange varianter som filer.

`lag_pasient` (17. okt. 2026): `Patient.save()` fylte inn aktiv vakt når den
manglet, og om lag 25 tester lente seg på det. Fallbacken er fjernet
(`docs/BESLUTNING_PORTALER.md`, beslutning 22) — denne gjør det samme, i
klartekst, samme mønster som `oppdrag.test_helpers.lag_oppdrag`.
"""
from django.db import transaction

from core.vakt import gjor_aktiv, hent_aktiv_vakt, vakt_for_year


def sett_aktiv_vakt(year=2098, portal=None):
    """Gjør vakta for `year` aktiv i portalen, og returner den.

    Lager vakta om den ikke finnes (navn = årstallet, som backfillen).
    Idempotent — kall den fritt i setUp.
    """
    with transaction.atomic():
        return gjor_aktiv(vakt_for_year(year, portal))


def aktiver_vakt(vakt):
    """Gjør en bestemt vakt aktiv i portalen sin — det testene gjorde med
    `AppSetting.set('aktiv_vakt_id', …)` før pekeren ble borte (17. okt. 2026)."""
    with transaction.atomic():
        return gjor_aktiv(vakt)


def lag_pasient(**felter):
    """Som `Patient.objects.create(**felter)`, med aktiv vakt når `vakt` mangler."""
    from patients.models import Patient

    if 'vakt' not in felter and 'vakt_id' not in felter:
        felter['vakt'] = hent_aktiv_vakt()
    return Patient.objects.create(**felter)
