"""Hjelpe-API for å opprette varsler fra hvilken som helst modul.

Brukes av:
- patients.signals — pasient-tildeling og -flytting (Fase 5)
- Framtidige moduler kan bruke samme API uten endring i core.

Eksempel:
    from core.notifications import notify

    notify(
        user=bruker,
        module_slug='patients',
        kind='patient_assigned',
        title='Ny pasient tildelt',
        message='Du er satt på pasient #1234',
        url='/pasienter/?focus=1234',
    )

API-en gjør automatisk dedup mot duplikater siste 24 timer slik at
gjentatte signals ikke spammer mottakeren.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from core.models import Notification

logger = logging.getLogger(__name__)

# Hvor lenge tilbake vi sjekker for duplikater. 24t er konservativt nok
# til å fange "samme handling utløst to ganger" uten å blokkere reelle
# nye varsler om samme tema dagen etter.
DEDUP_WINDOW = timedelta(hours=24)


def notify(
    user,
    *,
    module_slug: str,
    kind: str,
    title: str = '',
    message: str = '',
    url: str = '',
    level: str = Notification.LEVEL_INFO,
) -> Notification | None:
    """Opprett et nytt varsel hvis ikke duplikat finnes siste 24 timer.

    Returnerer det opprettede Notification-objektet, eller None hvis
    dedup-sjekken stoppet opprettelsen.

    Argumenter:
        user         — mottaker (CustomUser-instans eller AnonymousUser)
        module_slug  — slug for modulen ('patients', 'vakter', ...)
        kind         — varseltype-identifikator
        title        — kort overskrift
        message      — detaljtekst
        url          — relativ URL for klikk (valgfritt)
        level        — 'info' | 'warning' | 'critical' (default info)

    Sikkerhet:
        - Anonyme brukere får aldri varsler.
        - **Brukere uten lesetilgang til ``module_slug`` får aldri varsler.**
          Se under.
        - Inaktive brukere får varsler (de blir lest når kontoen
          aktiveres igjen). Det er meningen.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return None

    # §10.4: modultilgang, ikke bare innlogging.
    #
    # Tilstanden var umulig før `PasientRolleForm` ble splittet: den satte
    # koblingen (`Forstehjelper.user`) og tilgangsflagget samtidig, så den som
    # var koblet hadde per definisjon tilgang. Etter splitten er de to
    # uavhengige — man kan være koblet som helsepersonell uten
    # `ModulTilgang('patients')`.
    #
    # Da ville `_notify_assignment` sendt et varsel som inneholder et
    # **pasientnummer** og lenker til en side brukeren får 403 på. Varselet
    # er altså både en lekkasje og en blindvei.
    #
    # Sjekken ligger her, ikke hos hver kaller: en kaller som glemmer den
    # feiler stille, og `notify()` er den ene porten alle varsler går gjennom.
    from core.auth_decorators import har_tilgang  # noqa: WPS433
    from core.modules import get_module  # noqa: WPS433

    # En ukjent slug logges høyt. Uten dette skillet ville en skrivefeil
    # («patient» for «patients») fått alle varsler til å forsvinne stille —
    # samme utfall som «mangler tilgang», men en helt annen årsak, og den ene
    # er en feil ingen ville oppdaget.
    if get_module(module_slug) is None:
        logger.warning(
            'notify: ukjent module_slug=%r (kind=%s) — varselet ble ikke '
            'opprettet. Skrivefeil, eller en modul som ikke er registrert i '
            'core.modules?', module_slug, kind,
        )
        return None

    if not har_tilgang(user, module_slug, 'les'):
        logger.debug(
            'notify: hopper over user=%s kind=%s — mangler lesetilgang til %s',
            user.pk, kind, module_slug,
        )
        return None

    # Dedup: samme bruker + kind + message + siste 24t.
    # Vi bruker (kind, message) som naturlig nøkkel — title kan variere
    # litt (f.eks. annerledes pasient-status) uten at det er duplikat.
    cutoff = timezone.now() - DEDUP_WINDOW
    existing = Notification.objects.filter(
        user=user,
        kind=kind,
        message=message,
        created_at__gte=cutoff,
    ).first()
    if existing is not None:
        logger.debug(
            'notify: dedup-treff for user=%s kind=%s (eksisterende pk=%s)',
            user.pk, kind, existing.pk,
        )
        return None

    return Notification.objects.create(
        user=user,
        module_slug=module_slug,
        kind=kind,
        level=level,
        title=title,
        message=message,
        url=url,
    )
