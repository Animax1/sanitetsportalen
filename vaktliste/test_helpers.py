"""Hjelpere for vaktlistetestene.

**Gruppene opprettes ikke av testene — de seedes av migrasjon `0007`.** Å lage
dem på nytt i hver `setUp` ville testet en verden som ikke finnes: enhver
installasjon har de seks standardgruppene fra det øyeblikket migrasjonene har
kjørt, og en test som lager sin egen «Ambulanse» ville ikke oppdaget at seedingen
sluttet å virke.

`gruppe()` slår derfor opp en seedet rad, og feiler tydelig hvis den mangler.
"""
from __future__ import annotations

from .models import Ressursgruppe

#: Navnene migrasjon 0007 seeder. Brukes av testene for å slippe strenger
#: spredd utover, og for å feile ett sted hvis en av dem forsvinner.
SAMLEPLASS = 'Samleplass'
MANNSKAPSBIL = 'Mannskapsbil'
AMBULANSE = 'Ambulanse'
LAG = 'Lag'
KO = 'KO'
ANNET = 'Annet'


def gruppe(navn=ANNET):
    """Den seedede ressursgruppa med dette navnet."""
    try:
        return Ressursgruppe.objects.get(navn=navn)
    except Ressursgruppe.DoesNotExist as feil:      # pragma: no cover
        raise AssertionError(
            f'Ressursgruppa «{navn}» mangler. Migrasjon 0007 seeder de seks '
            f'standardgruppene — kjører den ikke, er det den som er feil, '
            f'ikke testen.') from feil


def lag_rolle(navn, gruppenavn=ANNET, **kwargs):
    """En `Ressursrolle` i en av standardgruppene.

    Rollen hører til en gruppe fra 30. aug. 2026, og gruppa er påkrevd. En
    test som bare trenger «en rolle» skal slippe å velge hvilken.
    """
    from .models import Ressursrolle
    return Ressursrolle.objects.create(
        navn=navn, gruppe=gruppe(gruppenavn), **kwargs)


def lag_ressurs(**kwargs):
    """En `Ressurs` med en gruppe, uten at hver test må velge hvilken.

    Gruppa ble påkrevd 30. aug. 2026. De aller fleste testene bryr seg ikke om
    hvilken gruppe ressursen står i — de tester bemanning, tilgang eller
    tider — og skulle de likevel måtte oppgi en, ville `gruppe=gruppe(ANNET)`
    stått som støy i tjue `setUp`-metoder. Testene som *faktisk* handler om
    gruppa oppgir den eksplisitt, og da sier linja hva den mener.
    """
    from .models import Ressurs
    if 'gruppe' not in kwargs and 'gruppe_id' not in kwargs:
        kwargs['gruppe'] = gruppe(ANNET)
    return Ressurs.objects.create(**kwargs)
