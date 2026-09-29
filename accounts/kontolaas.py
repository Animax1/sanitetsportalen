"""Kontolåsen: feilede innlogginger telles, og for mange stenger kontoen en stund.

Passordsteget og MFA-steget deler telleren. Før MFA-steget fikk den, kunne man
gjette TOTP-koder i det uendelige uten at noe skjedde med kontoen.

**Telleren er atomisk** (28. sep. 2026). Den leste `failed_login_attempts` fra
et objekt hentet tidligere i forespørselen og skrev tilbake +1. Samtidige gjett
leste da samme verdi, og «fem forsøk, så lås» holdt ikke — grensen ble i
praksis rate-limiten. Nå låses raden mens den telles.

**En delt konto låses per maskin, ikke overalt** (André, 28. sep. 2026:
«brukernavn + IP, og behold IP-bremsen»). Bilkontoene har forutsigbare navn og
ingen MFA, og fem feil passord hvert kvarter fra hvor som helst holdt dem låst
midt i en hendelse — admins «Lås opp» ble opphevet ved neste runde. For en
delt konto gjelder derfor:

| Grense | Hvor | Hvorfor |
|---|---|---|
| `TERSKEL` feil fra én IP → den IP-en stenges i `SPERRETID` | cachen | Den som gjetter stenger seg selv ute, ikke bilen |
| `DELT_KONTO_TAK` feil totalt → hele kontoen låses | databasen | Ellers er gjetting fra mange adresser ubegrenset |
| 50 innlogginger per IP per 5 min | `login_view` | Uendret |

Taket står i databasen og ikke i cachen med vilje: mellom vaktene kjører
portalen med `LocMemCache` og én arbeider som startes på nytt hvert tusende
kall (`docs/RUNBOOK_VAKT.md` §1b), så tellerne i cachen nullstilles jevnlig.
Det er greit for maskinlåsen — den er en bekvemmelighet for den ekte bilen.
Det ville ikke vært greit for taket. Cachefeil gir åpen maskinlås, samme valg
som rate-limiten; taket står uansett.

**Og en låst delt konto svarer «låst» uansett passord** (andre gjennomgang,
29. sep. 2026; `login_view`). Svarte den «låst» bare på riktig passord, røpte
låsen svaret, og gjettingen fortsatte gjennom den fra så mange adresser man har —
taket var da ingen grense. Og mens den er låst, telles ingenting (tredje
gjennomgang): talte bare galt passord, flyttet hvert femtiende gjett
`locked_until`, og minuttene i meldingen røpte gjettet imellom.

En personlig konto har MFA å falle tilbake på og en eier som kan kontaktes, og
låses fortsatt overalt ved `TERSKEL`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

TERSKEL = 5
SPERRETID = timedelta(minutes=15)
DELT_KONTO_TAK = 50


def _generasjon(bruker) -> str:
    """Byttes av «Lås opp», så alle maskinlåsene for kontoen slipper samtidig.

    Cachen kan ikke slette på mønster uten Redis-spesifikke kall, og hvilke
    IP-er som er låst vet vi ikke. En ny generasjon gjør de gamle nøklene
    uleselige; de utløper av seg selv.
    """
    return cache.get(f'kontolaas:gen:{bruker.pk}') or '0'


def _nokler(bruker, ip):
    gen = _generasjon(bruker)
    return (f'kontolaas:{bruker.pk}:{gen}:{ip}:antall',
            f'kontolaas:{bruker.pk}:{gen}:{ip}:laast')


def er_laast(bruker, ip) -> bool:
    if bruker.is_locked():
        return True
    if not bruker.er_delt_konto:
        return False
    try:
        return bool(cache.get(_nokler(bruker, ip)[1]))
    except Exception:  # noqa: BLE001 — åpen ved cachefeil, se modulen
        logger.warning('kontolaas: cachen svarte ikke', exc_info=True)
        return False


def registrer_mislykket(bruker, ip) -> None:
    """Tell ett feilet forsøk. Låser maskinen eller kontoen når grensen nås.

    Oppdaterer også `bruker` i minnet, så kallstedet ser samme verdi som raden.
    """
    delt = bruker.er_delt_konto
    grense = DELT_KONTO_TAK if delt else TERSKEL
    with transaction.atomic():
        rad = type(bruker).objects.select_for_update().only(
            'pk', 'failed_login_attempts', 'locked_until').get(pk=bruker.pk)
        rad.failed_login_attempts += 1
        if rad.failed_login_attempts >= grense:
            rad.locked_until = timezone.now() + SPERRETID
            rad.failed_login_attempts = 0
        rad.save(update_fields=['failed_login_attempts', 'locked_until'])
    bruker.failed_login_attempts = rad.failed_login_attempts
    bruker.locked_until = rad.locked_until

    if delt:
        _tell_maskin(bruker, ip)


def _tell_maskin(bruker, ip) -> None:
    sekunder = int(SPERRETID.total_seconds())
    # `_nokler` leser generasjonen fra cachen, så den står *inne* i `try`:
    # utenfor ga et Redis-utfall 500 på feil passord for en bilkonto, i stedet
    # for «Feil brukernavn eller passord» (funnet i gjennomgangen 29. sep. 2026).
    try:
        antall_nokkel, laast_nokkel = _nokler(bruker, ip)
        cache.add(antall_nokkel, 0, sekunder)
        if cache.incr(antall_nokkel) >= TERSKEL:
            cache.set(laast_nokkel, True, sekunder)
            cache.delete(antall_nokkel)
    except Exception:  # noqa: BLE001
        logger.warning('kontolaas: cachen svarte ikke', exc_info=True)


def nullstill(bruker, ip) -> None:
    """Innloggingen er fullført: telleren og maskinens teller starter på null."""
    if bruker.failed_login_attempts or bruker.locked_until:
        bruker.failed_login_attempts = 0
        bruker.locked_until = None
        bruker.save(update_fields=['failed_login_attempts', 'locked_until'])
    if bruker.er_delt_konto:
        try:
            cache.delete(_nokler(bruker, ip)[0])
        except Exception:  # noqa: BLE001
            logger.warning('kontolaas: cachen svarte ikke', exc_info=True)


def laas_opp(bruker) -> None:
    """Admins «Lås opp»: kontoen og alle maskinlåsene."""
    bruker.failed_login_attempts = 0
    bruker.locked_until = None
    bruker.save(update_fields=['failed_login_attempts', 'locked_until'])
    try:
        cache.set(f'kontolaas:gen:{bruker.pk}', uuid.uuid4().hex, None)
    except Exception:  # noqa: BLE001
        logger.warning('kontolaas: cachen svarte ikke', exc_info=True)
