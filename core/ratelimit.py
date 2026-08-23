"""Rate-limiting for innloggede endepunkter (S3).

Innlogging har hatt rate-limiting siden N4. Alt annet var ubeskyttet: en
``read_write``-bruker — eller en stjålet sesjonscookie — kunne opprette
pasienter i løkke så fort serveren rakk å svare, og en admin kunne hente
5000 auditrader per kall uten øvre grense på antall kall.

**Én bøtte per endepunkt.** ``group``-strengen inngår i cache-nøkkelen, så to
ulike grupper deler aldri teller. Det er lærdommen fra N4: der havnet alle
MFA-forsøk fra alle brukere i samme bøtte fordi nøkkelen slo opp et felt som
ikke fantes i skjemaet, og ved vaktstart fikk den ellevte brukeren 429 uten at
noe var galt med kontoen. Grupper skal derfor navngis eksplisitt, aldri
utledes av funksjonsnavnet.

**Grensen faller åpen ved cache-feil.** ``django-ratelimit`` gjør ikke dette
av seg selv, og det stod feil i ``settings.py`` fram til 23. aug. 2026:

* Med Redis nede kaster ``cache.add()`` en ``ConnectionError`` som pakken ikke
  fanger — endepunktet ville svart 500, ikke fallt åpent.
* Selv når cachen svarer, men uten verdi, gir pakkens default
  (``RATELIMIT_FAIL_OPEN = False``) ``should_limit=True`` — altså 429 på alt.

Begge er feil prioritering her. Dette er et system som brukes under
sanitetsvakt: en pasient som ikke kan registreres fordi en cache er nede er
verre enn en manglende bremse. Samme avveining som ``patients/stats_cache.py``
gjør for statistikken, og samme prinsipp som F3 formulerer for idempotens —
bedre dobbel registrering enn ingen registrering.

Innlogging beholder sin egen beskyttelse uavhengig av cachen: individuell
kontolåsing (5 feilede forsøk = 15 min) ligger i databasen, ikke her.

**Telleren er bare så delt som cachen er.** I lavkostnad-modus kjører appen
én gunicorn-worker med fire tråder mot LocMemCache, og da er telleren felles
for all trafikk — som er riktig. Settes ``WEB_WORKERS`` høyere uten at
``REDIS_URL`` er satt, får hver worker sin egen teller, og den reelle grensen
blir grensen ganger antall workers. ``--max-requests 1000`` resirkulerer i
tillegg workeren jevnlig, så tellerne nullstilles av og til. Begge avvikene
går samme vei: bremsen blir mildere enn den er konfigurert, aldri strengere.
Det er den ufarlige retningen for et system som brukes under vakt.
"""
import logging
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import render
from django_ratelimit.core import is_ratelimited

logger = logging.getLogger(__name__)


def er_rate_limited(request, *, group, key, rate, method='POST'):
    """Tell ett forsøk mot bøtta ``group`` og si om grensen er passert.

    ``increment=True`` betyr at selve kallet teller forsøket — kall den derfor
    én gang per forespørsel, ikke i en betingelse som kan evalueres flere
    ganger.

    Respekterer ``RATELIMIT_ENABLE`` (nød-bryteren) og ``method`` internt i
    ``is_ratelimited``: er bryteren av, eller matcher ikke metoden, returneres
    False uten at noe telles.

    Returnerer alltid False ved feil i cache-laget. Se modulens docstring.
    """
    try:
        return is_ratelimited(
            request=request,
            group=group,
            key=key,
            rate=rate,
            method=method,
            increment=True,
        )
    except Exception:
        logger.warning(
            'Rate-limit-sjekk feilet for gruppe %r — slipper forespørselen '
            'gjennom. Bremsen er ute av drift til cachen er tilbake.',
            group,
            exc_info=True,
        )
        return False


def _for_mange(request, on_limit):
    """Bygg 429-svaret i det formatet kallstedet forventer."""
    if on_limit == 'json':
        # Formen matcher det pasient-API-et ellers svarer med ved feil, og
        # det `patients-forms.js` faktisk leser (`d.error`).
        return JsonResponse(
            {'error': 'For mange forespørsler på kort tid. '
                      'Vent litt og prøv igjen.'},
            status=429,
        )
    # Samme mal som `accounts.views.ratelimited_view`, som står som
    # RATELIMIT_VIEW for innloggingsstien. Rendres direkte her for å slippe
    # en import fra core til accounts — avhengigheten går motsatt vei.
    return render(request, 'accounts/ratelimited.html', status=429)


def rate_limit(*, group, rate, method='POST', key='user', on_limit='json'):
    """Dekorator: svar 429 når bøtta ``group`` er tømt for denne nøkkelen.

    ``on_limit`` velger svarformatet — ``'json'`` for API-endepunkter,
    ``'html'`` for vanlige sider. Skillet finnes fordi ``RATELIMIT_VIEW``, som
    ``@ratelimit``-dekoratoren i django-ratelimit bruker, alltid rendrer en
    HTML-side. En JSON-klient ville fått markup den ikke kan lese, og
    frontenden ville vist «kunne ikke lagre» uten å kunne si hvorfor.

    ``key='user'`` forutsetter innlogget bruker. Alle endepunktene dette
    brukes på ligger bak ``@login_required`` eller en rollesjekk, så det
    holder — men rekkefølgen betyr noe: sett denne dekoratoren *under*
    tilgangssjekken, ellers telles anonyme forsøk mot ``AnonymousUser.pk``,
    som er None for alle.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if er_rate_limited(
                request, group=group, key=key, rate=rate, method=method,
            ):
                logger.info(
                    'Rate-limit nådd: gruppe=%s bruker=%s',
                    group, getattr(request.user, 'pk', None),
                )
                return _for_mange(request, on_limit)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
