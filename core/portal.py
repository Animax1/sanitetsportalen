"""Hvilken portal en forespørsel, en kommando eller en jobb gjelder (17. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.4 og §4.13. Portalen ligger over vakta: hver
vakt hører til én `core.Vaktportal`, og «aktiv vakt» er et spørsmål *per portal*.

**Hvor portalen kommer fra**, i den rekkefølgen den leses:

1. **Konteksten** — `aktiver_portal()`. Middlewaren setter den for hver
   forespørsel (fase 2), parks side uten innlogging fra lenken, og en kommando
   fra argumentet sitt. Alt som kjører *inne i* forespørselen — signaler,
   `on_commit` — arver den, fordi det kjører i samme kontekst.
2. **Den eneste aktive portalen**, hvis det finnes nøyaktig én. Ellers
   `UklarPortal`.

**Det andre leddet er ikke «Standard» som reserve.** Det gjetter aldri: med to
aktive portaler og ingen kontekst kaster det, og kodeveien som manglet
konteksten stopper der i stedet for å skrive i feil portal. Det er
installasjonens svar, ikke brukerens — derfor skal en forespørsel aldri havne
her når fase 2 er på plass, og testene med to portaler (§6.1) krever at den
ikke gjør det.

**Null portaler** er en fersk installasjon — eller en `TransactionTestCase`
som har tømt tabellen. Da lages «Standard», samme latskap som `vakt_for_year`:
en ny installasjon skal ikke trenge et oppsettsteg for å registrere en pasient.
Finnes det portaler, men ingen er aktive, kastes `UklarPortal`.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager

from django.db import IntegrityError, transaction

from core.models import Vaktportal

STANDARD_NAVN = 'Standard'
STANDARD_SLUG = 'standard'

_aktiv: contextvars.ContextVar = contextvars.ContextVar('aktiv_portal', default=None)


class UklarPortal(LookupError):
    """Det finnes ikke ett entydig svar på hvilken portal dette gjelder."""


@contextmanager
def aktiver_portal(portal):
    """Gjør `portal` gjeldende innenfor blokken. Nøstes og nullstilles riktig."""
    token = _aktiv.set(portal)
    try:
        yield portal
    finally:
        _aktiv.reset(token)


def aktiv_kontekst():
    """Portalen konteksten bærer, eller ``None``. Gjetter ikke."""
    return _aktiv.get()


def gjeldende_portal() -> Vaktportal:
    """Portalen konteksten bærer, ellers den eneste aktive. Aldri en gjetning."""
    portal = _aktiv.get()
    if portal is not None:
        return portal
    return eneste_portal()


def eneste_portal() -> Vaktportal:
    """Den ene aktive portalen. `UklarPortal` når det er flere eller ingen aktive."""
    aktive = list(Vaktportal.objects.filter(er_aktiv=True).order_by('pk')[:2])
    if len(aktive) == 1:
        return aktive[0]
    if aktive:
        raise UklarPortal(
            'Det finnes flere portaler, og ingen er valgt. Velg portal, '
            'eller oppgi den eksplisitt.')
    if Vaktportal.objects.exists():
        raise UklarPortal('Ingen portal er aktiv.')
    try:
        with transaction.atomic():
            return Vaktportal.objects.create(navn=STANDARD_NAVN, slug=STANDARD_SLUG)
    except IntegrityError:
        # En samtidig forespørsel rakk å lage den.
        return Vaktportal.objects.get(slug=STANDARD_SLUG)


# ── Brukerens portal — portalregelen (§4.4, beslutning 21) ───────────────────
#
# Over sto installasjonens svar. Her står brukerens: hvilke portaler *denne
# kontoen* kan stå i, og hvilken den står i nå. Middlewaren skriver valget i
# sesjonen og legger det på brukerobjektet; `har_tilgang` leser det derfra.

#: Navnet på attributtet middlewaren setter på `request.user`.
BRUKER_ATTR = '_aktiv_portal'
#: Nøkkelen i sesjonen.
SESJON_NOKKEL = 'portal_id'


def mulige_portaler(user):
    """De aktive portalene kontoen kan stå i. Global admin: alle aktive."""
    from core.auth_decorators import er_global_admin

    aktive = Vaktportal.objects.filter(er_aktiv=True)
    if not getattr(user, 'is_authenticated', False):
        return aktive.none()
    if er_global_admin(user):
        return aktive.order_by('pk')
    return aktive.filter(portaltilganger__bruker=user).order_by('pk').distinct()


def brukerens_portal(user):
    """Portalen kontoen står i, eller ``None``. Gjetter aldri.

    Middlewaren har lagt den på brukerobjektet for hver forespørsel. Mangler
    den — et brukerobjekt fra en test, en kommando eller et tjenestelag — er
    svaret portalen kontoen *kan* stå i, hvis det er nøyaktig én. Det er
    brukerens svar, ikke installasjonens: en konto med én portal har bare ett
    sted å være, uansett hvor mange portaler som finnes.
    """
    if hasattr(user, BRUKER_ATTR):
        return getattr(user, BRUKER_ATTR)
    mulige = list(mulige_portaler(user)[:2])
    return mulige[0] if len(mulige) == 1 else None
