"""Idempotens for skriveendepunkter (F3).

Utløst av en reell hendelse: 30. april 2026 ble en pasient registrert dobbelt
på Grønn sone i prod fordi brukeren dobbeltklikket før serveren rakk å svare.
Delte soner har ingen unik-sjekk, så begge forespørslene gikk gjennom.

Klienten lager en nøkkel når skjemaet åpnes og sender den med hver innsending
fra det skjemaet. Serveren reserverer nøkkelen før den oppretter noe, og en
andre innsending med samme nøkkel oppretter ikke en ny rad.

**Hva dette dekker, og hva det ikke gjør.** Nøkkelen lages når skjemaet åpnes,
så to *faner* med hvert sitt skjema har hver sin nøkkel og teller som to
registreringer — slik det skal være, for det kan være to reelle pasienter.
Det dekket er:

* dobbeltinnsending fra samme skjema (klikk + Enter, eller en guard som svikter)
* automatisk nettverks-retry, der klient eller mellomledd sender samme POST på nytt
* API-klienter som prøver på nytt etter et tidsavbrudd

``withSubmitGuard()`` i `patients-utils.js` dekker det rene dobbeltklikket i
grensesnittet. Denne modulen dekker tilfellene guarden ikke ser, fordi de skjer
utenfor knappen.

**Reserver etter validering, aldri før.** En avvist innsending skal ikke brenne
nøkkelen — ellers får brukeren som retter en feil i skjemaet en «allerede
sendt inn»-melding på det korrigerte forsøket. Feiler opprettelsen etter
reservasjonen, skal nøkkelen frigis med :func:`forkast`.

**Cache-feil betyr opprett uansett.** Alle kall faller åpne. Under sanitetsvakt
er en dobbeltregistrering et irritasjonsmoment; en pasient som ikke lar seg
registrere fordi en cache er nede er det ikke. Samme avveining som
``core/ratelimit.py`` og ``patients/stats_cache.py`` gjør.

**Beskyttelsen er bare så delt som cachen er.** I dag kjører appen én
gunicorn-worker med fire tråder mot LocMemCache, så alle forespørsler ser samme
reservasjon. Settes ``WEB_WORKERS`` høyere uten ``REDIS_URL``, gjelder vernet
kun innenfor én worker — og to raske forespørsler kan da havne i hver sin. Det
avviket går samme vei som før: verst tenkelige utfall er dagens oppførsel.
"""
import logging
import re

from django.core.cache import cache

logger = logging.getLogger(__name__)

# 5 minutter. Lenge nok til å dekke en retry etter tidsavbrudd, kort nok til at
# en nøkkel ikke blokkerer en reell ny registrering fra samme åpne skjema.
TTL = 300

# Markør for «en forespørsel med denne nøkkelen er i gang, men ikke ferdig».
PAGAR = '__pagar__'

# Nøkkelen kommer fra klienten og går inn i en cache-nøkkel. Uten en form her
# kan en klient sende vilkårlig lange strenger, eller tegn som kolliderer med
# nøkkelseparatoren. UUID-er og hex-strenger passer; alt annet avvises og
# behandles som «ingen nøkkel sendt».
_GYLDIG = re.compile(r'^[A-Za-z0-9-]{8,64}$')


def bygg_nokkel(prefiks, bruker_id, klientnokkel):
    """Sett sammen cache-nøkkelen, eller None hvis klienten ikke sendte noe brukbart.

    None betyr «ingen idempotens for denne forespørselen» — kallstedet skal da
    oppføre seg nøyaktig som før F3. Det holder eldre klienter og
    API-integrasjoner virksomme uten endring.

    Nøkkelen er alltid navnerommet per bruker, slik at to personer ikke kan
    kollidere på samme tilfeldige verdi.
    """
    if not klientnokkel or not _GYLDIG.match(str(klientnokkel)):
        return None
    return f'idem:{prefiks}:{bruker_id}:{klientnokkel}'


def reserver(nokkel):
    """Ta nøkkelen i bruk. Returnerer ``(status, verdi)``.

    * ``('ny', None)`` – nøkkelen var ledig, kallstedet skal opprette
    * ``('pagar', None)`` – en annen forespørsel med samme nøkkel er i gang
    * ``('ferdig', verdi)`` – nøkkelen er brukt, og dette er resultatet

    ``cache.add()`` er atomisk; ``get()`` etterfulgt av ``set()`` er det ikke,
    og ville sluppet begge forespørslene gjennom i nettopp det vinduet
    mekanismen finnes for å lukke.
    """
    try:
        if cache.add(nokkel, PAGAR, TTL):
            return ('ny', None)
        verdi = cache.get(nokkel)
    except Exception:
        logger.warning(
            'Idempotens-sjekk feilet for %r — oppretter uansett. Dobbeltvernet '
            'er ute av drift til cachen er tilbake.',
            nokkel, exc_info=True,
        )
        return ('ny', None)

    if verdi is None:
        # Nøkkelen fantes da add() kjørte, men er borte nå — cachen har mistet
        # den (omstart, flush). Da finnes det ikke lenger bevis for en tidligere
        # forespørsel, og fail-open-regelen gjelder: opprett.
        return ('ny', None)
    if verdi == PAGAR:
        return ('pagar', None)
    return ('ferdig', verdi)


def fullfor(nokkel, verdi):
    """Lagre resultatet, slik at en senere retry får svaret i stedet for en ny rad."""
    try:
        cache.set(nokkel, verdi, TTL)
    except Exception:
        logger.warning('Kunne ikke lagre idempotens-resultat for %r', nokkel,
                       exc_info=True)


def forkast(nokkel):
    """Frigi nøkkelen etter en feilet opprettelse, så brukeren kan prøve igjen."""
    try:
        cache.delete(nokkel)
    except Exception:
        logger.warning('Kunne ikke frigi idempotens-nøkkel %r', nokkel,
                       exc_info=True)
