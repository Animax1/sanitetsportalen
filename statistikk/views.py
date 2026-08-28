"""Statistikk-endepunktene og statistikksiden.

Skilt ut fra pasientmodulen august 2026. Bakgrunnen står i CHANGELOG:
statistikk skulle uansett bli sin egen modul, og rollemodellen kunne ikke
utformes før den var det — så lenge «ser statistikk» og «kan skrive» var to
akser i samme modul, trengte tilgangsnivået fire trinn i stedet for tre.

**Avhengighetsretningen er med vilje statistikk → patients.** Presentasjonen
kjenner domenet; domenet kjenner ikke presentasjonen. Tallene beregnes
fortsatt av ``patients.services`` — denne appen henter dem, cacher dem og
viser dem fram. Når modul nummer to skal levere tall, byttes den direkte
importen ut med et registry etter samme idiom som ``core.backup`` og
``core.arkiv``.

``/pasienter/api/stats/`` (header-chipsene) ble bevisst *ikke* flyttet: de er
for alle innloggede og hører til pasientsiden de står på.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from core.auth_decorators import has_role_at_least, stats_required
from core.ratelimit import rate_limit
from core.stats_cache import cached_stats_response

from patients.services import (
    ARKIV_VIEW_MIN_ROLE,
    compute_arkiv_full_stats,
    full_stats,
    get_active_year,
)


@stats_required
@require_http_methods(['GET'])
def statistikk_view(request):
    """Statistikksiden. Samme tilgang som tallene den viser."""
    return render(request, 'statistikk/index.html')


@stats_required
@require_http_methods(['GET'])
# S3: appens dyreste spørring. Cachen tar 60 sekunder av gangen, men
# cache-miss-stien var helt ubeskyttet — og det er nettopp den en klient
# i løkke treffer gang på gang. Statistikksiden lastes ved åpning og ved
# auto-refresh hvert 30. sekund, altså rundt 2/min i normal bruk.
#
# Gruppenavnet beholdt prefikset `patients:` ved flyttingen. Det er
# cache-nøkkelen for tellerne, og å bytte den ville nullstilt bøtta for alle
# som var midt i et vindu i det deployen traff.
@rate_limit(group='patients:full-stats', rate='30/m', method='GET')
def full_stats_view(request):
    """Full statistikk. Kun admin, lead og lead_view.

    Cachet 60s med ETag/304. Dyre aggregater (percentiler, gruppetellinger)
    regnes kun én gang per minutt per år.
    """
    year = get_active_year()

    @cached_stats_response(cache_key=f'full:{year}', ttl=60)
    def _inner(req):
        return full_stats(year=year)

    return _inner(request)


@login_required
@require_http_methods(['GET'])
def arkiv_full_stats_view(request, pk):
    """Full statistikk for én arkivert vakt.

    Samme struktur som ``/statistikk/api/full-stats/`` (chi2, Kruskal-Wallis,
    krysstabeller, tids-statistikk pr. gruppe, ankomster, obs-stats).

    **To gates, ikke én.** Visningen flyttet hit sammen med resten av
    statistikkrenderingen, men tilgangen fulgte ikke med: arkivet er
    strengere beskyttet enn live-statistikken (``ARKIV_VIEW_MIN_ROLE``,
    i dag ``admin``). Hadde endepunktet arvet statistikkmodulens gate ved
    flyttingen, ville ``lead_view`` fått innsyn i arkiverte vakter uten at
    noen bestemte det.
    """
    if not has_role_at_least(request.user, ARKIV_VIEW_MIN_ROLE):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    from patients.models import VaktArkiv

    try:
        arkiv = VaktArkiv.objects.get(pk=pk)
    except VaktArkiv.DoesNotExist:
        return JsonResponse({'error': 'Arkiv ikke funnet'}, status=404)

    return JsonResponse(compute_arkiv_full_stats(arkiv))
