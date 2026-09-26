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

from django.db import IntegrityError, transaction
from django.utils import timezone as djtz

from core.models import AppSetting, Vakt
from core.validators import current_local_year


class VaktnavnOpptatt(ValueError):
    """Navnet er tatt. En `ValueError`, så kallerne som alt svarer 400 på
    en ugyldig verdi gjør det her også."""


def vaktnavn_opptatt_melding(navn: str) -> str:
    return (f'En vakt med navnet «{navn}» finnes allerede. '
            f'Legg på en dato eller velg et annet navn.')


def opprett_vakt(navn, *, year, startet, er_aktiv=True):
    """Den ene fabrikken for `Vakt`-rader (26. sep. 2026).

    **Databasen avgjør om navnet er ledig, ikke et `exists()` foran.** Tre
    steder laget vakter, hvert med sin egen sjekk, og en sjekk før `create()`
    er et kappløp: to samtidige innsendinger av samme navn består begge, og
    den andre fikk 500 fra unikhetskravet. Her fanges `IntegrityError` i et
    eget savepoint, så en kaller inne i en større transaksjon kan fortsette,
    og svaret blir det samme som om sjekken hadde sagt nei.
    """
    navn = (navn or '').strip()
    if not navn:
        raise ValueError('Vakta må ha et navn.')
    try:
        with transaction.atomic():
            return Vakt.objects.create(navn=navn, year=year, startet=startet,
                                       er_aktiv=er_aktiv)
    except IntegrityError:
        raise VaktnavnOpptatt(vaktnavn_opptatt_melding(navn)) from None


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
    if vakt is not None:
        return vakt
    try:
        return opprett_vakt(str(year), year=year, startet=djtz.now())
    except VaktnavnOpptatt:
        # En samtidig forespørsel rakk å lage den. Finnes den fortsatt ikke,
        # er navnet tatt av en vakt for et annet år — det skal synes.
        vakt = Vakt.objects.filter(year=year).order_by('-startet').first()
        if vakt is None:
            raise
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
