"""Portalens scope: hvilken vakt nye rader hører til (flyttet hit 14. sep. 2026).

Vakta er delt av alle modulene — pasienter, oppdrag og vaktlister peker alle på
den. Funksjonene lå i `patients/services.py` fordi `AppSetting`-pekeren gjorde
det, og da måtte oppdragsmodulen, vaktlista og statistikken importere
*pasientmodulen* for å vite hvilken vakt de var i. Se
`docs/PLAN_FLYTTING_TIL_CORE.md`.

Ingen av de to rører pasientdata. De leser `core.Vakt`, og hører derfor hjemme her.

**Aktiv vakt er per portal** (17. okt. 2026, `docs/BESLUTNING_PORTALER.md`
§4.1). `AppSetting['aktiv_vakt_id']` var fasit fram til da; nå er det
`Vakt.er_aktiv`, og en delvis unik indeks sier at hver portal har høyst én.
Hver funksjon her tar `portal`; utelates den, brukes `core.portal.gjeldende_portal()`,
som aldri gjetter.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone as djtz

from core.models import Vakt, Vaktportal
from core.portal import gjeldende_portal
from core.validators import current_local_year


class VaktnavnOpptatt(ValueError):
    """Navnet er tatt. En `ValueError`, så kallerne som alt svarer 400 på
    en ugyldig verdi gjør det her også."""


def vaktnavn_opptatt_melding(navn: str) -> str:
    return (f'En vakt med navnet «{navn}» finnes allerede. '
            f'Legg på en dato eller velg et annet navn.')


def opprett_vakt(navn, *, year, startet, portal=None):
    """Den ene fabrikken for `Vakt`-rader (26. sep. 2026).

    **Databasen avgjør om navnet er ledig, ikke et `exists()` foran.** Tre
    steder laget vakter, hvert med sin egen sjekk, og en sjekk før `create()`
    er et kappløp: to samtidige innsendinger av samme navn består begge, og
    den andre fikk 500 fra unikhetskravet. Her fanges `IntegrityError` i et
    eget savepoint, så en kaller inne i en større transaksjon kan fortsette,
    og svaret blir det samme som om sjekken hadde sagt nei.

    **Vakta lages aldri aktiv** (17. okt. 2026). Med den unike indeksen ville
    en ny rad som påstod å være aktiv feilet så snart portalen hadde en — og
    feilen ville blitt meldt som «navnet er tatt». Det å gjøre en vakt aktiv er
    `gjor_aktiv()`, en egen handling.
    """
    navn = (navn or '').strip()
    if not navn:
        raise ValueError('Vakten må ha et navn.')
    portal = portal or gjeldende_portal()
    try:
        with transaction.atomic():
            return Vakt.objects.create(navn=navn, year=year, startet=startet,
                                       portal=portal, er_aktiv=False)
    except IntegrityError:
        raise VaktnavnOpptatt(vaktnavn_opptatt_melding(navn)) from None


def vakt_for_year(year, portal=None):
    """Vakta for et år i portalen — finn den, eller lag den.

    Lat opprettelse — en fersk installasjon skal ikke trenge et oppsettsteg
    for at registrering skal virke. Navnet blir årstallet — samme ærlighet som
    backfillen: vi vet ikke hva vakta heter, og påstår det ikke. Admin endrer
    navnet når hun vet det. Vakta som lages er **ikke** aktiv.

    Finnes flere vakter for året, velges den nyeste.
    """
    portal = portal or gjeldende_portal()
    vakt = Vakt.objects.filter(portal=portal, year=year).order_by('-startet').first()
    if vakt is not None:
        return vakt
    try:
        return opprett_vakt(str(year), year=year, startet=djtz.now(), portal=portal)
    except VaktnavnOpptatt:
        # En samtidig forespørsel rakk å lage den. Finnes den fortsatt ikke,
        # er navnet tatt av en vakt i en annen portal eller et annet år — det
        # skal synes.
        vakt = Vakt.objects.filter(portal=portal, year=year).order_by('-startet').first()
        if vakt is None:
            raise
        return vakt


def gjor_aktiv(vakt):
    """Gjør `vakt` til portalens aktive vakt, og returner den. **Bare i en transaksjon.**

    Låser portalen, og slår av en annen aktiv vakt i samme portal *før* denne
    slås på — rekkefølgen den unike indeksen krever. Den andre får `avsluttet`
    satt, som gjenåpningen alltid har gjort. En vakt uten portal (fra en backup
    tatt før portalene) tas inn i den gjeldende.
    """
    if vakt.portal_id is None:
        vakt.portal = gjeldende_portal()
        vakt.save(update_fields=['portal'])
    Vaktportal.objects.select_for_update().filter(pk=vakt.portal_id).first()
    (Vakt.objects.filter(portal_id=vakt.portal_id, er_aktiv=True)
     .exclude(pk=vakt.pk).update(er_aktiv=False, avsluttet=djtz.now()))
    vakt.er_aktiv = True
    vakt.avsluttet = None
    vakt.save(update_fields=['er_aktiv', 'avsluttet'])
    return vakt


def laas_aktiv_vakt(portal=None):
    """Lås portalen og returner dens aktive vakt. **Bare inne i en transaksjon.**

    For de som *bytter* aktiv vakt — «Avslutt vakt», gjenåpning og sletting
    (sikkerhetsgjennomgangen 28. sep. 2026). Alle leste `hent_aktiv_vakt()`
    utenfor transaksjonen: to samtidige gjenåpninger ga to vakter med
    `er_aktiv=True`, og to samtidige avslutninger kunne fryse samme vakt to
    ganger — den andre gangen med tomme tall, som da ble de som ble vist.
    Låsen satt på `AppSetting['aktiv_vakt_id']` fram til 17. okt. 2026; nå er
    det portalraden, som er det ene stedet alle som bytter i portalen må
    innom. PostgreSQL låser; SQLite serialiserer skrivinger uansett.
    """
    portal = portal or gjeldende_portal()
    Vaktportal.objects.select_for_update().filter(pk=portal.pk).first()
    return hent_aktiv_vakt(portal)


def hent_aktiv_vakt(portal=None):
    """Vakta nye rader i portalen skal peke på. Aldri ``None``.

    `Vakt.er_aktiv` er fasit, og indeksen sier at det er høyst én per portal.
    Har portalen ingen — fersk installasjon, eller en gjenoppretting som tok
    vaktene — gjøres vakta for året aktiv. Fail-open i samme retning som
    resten av huset: en pasient som ikke lar seg registrere fordi portalen
    mangler en aktiv vakt, er verre enn en vakt som må gis riktig navn.
    """
    portal = portal or gjeldende_portal()
    vakt = Vakt.objects.filter(portal=portal, er_aktiv=True).first()
    if vakt is not None:
        return vakt
    try:
        with transaction.atomic():
            return gjor_aktiv(vakt_for_year(current_local_year(), portal))
    except IntegrityError:
        # En samtidig forespørsel rakk å gjøre en annen vakt aktiv.
        return Vakt.objects.get(portal=portal, er_aktiv=True)
