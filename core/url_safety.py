"""Validering av redirect-mål (N1 og S4).

`django.shortcuts.redirect()` godtar en absolutt URL. Sender vi en verdi som
kommer fra en query-streng eller fra databasen rett inn i den, har vi en åpen
redirect: en lenke som ser ut til å høre til portalen, men som sender brukeren
til en fremmed host.

Det farligste tilfellet er ``?next=``-parameteren ved innlogging. Brukeren
lander på angriperens side **rett etter en vellykket innlogging** — nøyaktig i
det øyeblikket de har mest tillit til at de er på riktig sted. Det er steg to i
en klassisk phishing-kjede.

Django sin egen ``LoginView`` beskytter seg med
``url_has_allowed_host_and_scheme``. Denne appen har et egenskrevet
innloggingsview og har aldri hatt den sjekken.

Alle redirect-mål som ikke er hardkodet i koden skal gjennom
``safe_redirect_url()``.
"""
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect_url(request, candidate, fallback='/'):
    """Returner ``candidate`` hvis den peker innenfor appen, ellers ``fallback``.

    Godtar relative stier (``/pasienter/``) og absolutte URL-er som peker på
    appens egen host. Avviser andre hoster, protokoll-relative URL-er
    (``//evil.example``) og alt annet Django ikke anerkjenner som trygt.

    ``require_https`` følger requesten: på en HTTPS-side avvises et
    ``http://``-mål, slik at en redirect ikke kan nedgradere forbindelsen.
    Offline-modus kjører uten TLS, og der blir kravet tilsvarende av seg selv.
    """
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback
