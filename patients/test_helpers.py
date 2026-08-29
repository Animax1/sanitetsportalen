"""Delte testhjelpere for vakt-scoping.

Fram til deploy 2 satte testene `AppSetting['active_year']` og opprettet rader
med `year=`. Begge deler er borte: scopet er vakta. Denne hjelperen er den ene
veien testene skal sette scope på — å peke `aktiv_vakt_id` for hånd i hver
testfil ville gitt like mange varianter som filer.
"""
from patients.models import AppSetting
from patients.services import vakt_for_year


def sett_aktiv_vakt(year=2098):
    """Gjør vakta for `year` aktiv, og returner den.

    Lager vakta om den ikke finnes (navn = årstallet, som backfillen).
    Idempotent — kall den fritt i setUp.
    """
    vakt = vakt_for_year(year)
    AppSetting.set('aktiv_vakt_id', vakt.pk)
    return vakt
