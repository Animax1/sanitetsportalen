"""Views for core-appen (Sanitetsportal-skall).

Inneholder portal-dashboardet samt legacy-redirects fra gamle root-baserte
URL-er som flyttet til /pasienter/-prefiks i Fase 2.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.views.decorators.http import require_GET


@login_required
@require_GET
def portal_dashboard_view(request):
    """Portal-forside med oversikt over moduler.

    Vises på `/`. Krever innlogging — uautentiserte brukere blir sendt til
    login-siden via `@login_required`. Etter innlogging redirecter Django
    automatisk tilbake hit (settings.LOGIN_REDIRECT_URL = '/').
    """
    return render(request, 'core/dashboard.html')


# ─────────────────────────────────────────────────────────────────────────────
# Legacy-redirects
#
# I Fase 2 flyttet vi pasient-modulen fra `/` til `/pasienter/`. Eksisterende
# bokmerker, lenker i e-post osv. peker fortsatt på gamle URL-er.
# Vi løser dette med 301 Moved Permanently — nettlesere cacher den nye URL-en
# og oppdaterer automatisk.
#
# Vi gjør dette med en generisk view (i stedet for RedirectView) for å:
# 1. Bevare hele path-en etter det stripte prefikset (slug, query string)
# 2. Returnere skikkelig 301 selv på POST/PUT/DELETE — uten dette bytter Django
#    301 til 302 ved usikre HTTP-metoder, og noen klienter feiler da.
# 3. Logge tydelig at dette er legacy-trafikk (kan brukes til å fase ut senere).
# ─────────────────────────────────────────────────────────────────────────────


def legacy_root_redirect(request, subpath: str = '') -> HttpResponse:
    """Redirect en gammel root-URL til den nye `/pasienter/`-versjonen.

    Args:
        subpath: Den delen av URL-en som kommer ETTER prefikset som ble
                 fjernet. F.eks. for `/api/patients/` er subpath = "patients/".

    Returnerer 301 Moved Permanently og bevarer query string.
    """
    # Bygg ny path: /pasienter/<original-prefiks>/<subpath>
    # `subpath` mangler ledende slash siden det kommer fra path-converter.
    # Den opprinnelige path-en starter alltid med '/', så vi tar
    # request.path direkte og prefikser med '/pasienter'.
    new_path = '/pasienter' + request.path

    # Bevar query string (?foo=bar)
    if request.META.get('QUERY_STRING'):
        new_path = f"{new_path}?{request.META['QUERY_STRING']}"

    return HttpResponsePermanentRedirect(new_path)
