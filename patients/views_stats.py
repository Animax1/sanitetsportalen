"""Statistikk-endepunktene. Skilt ut fra ``views.py`` i N13.3."""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from core.auth_decorators import stats_required

from .services import basic_stats, full_stats, get_active_year


# ── Statistikk ────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def stats_view(request):
    """Basis-statistikk for header-chips. Filtrerer alltid på aktivt år.

    Cachet 15s med ETag/304 for å redusere last ved gjentatt polling.
    Cache-nøkkel inkluderer aktivt år slik at bytte av år gir ny cache.
    """
    from .stats_cache import cached_stats_response
    year = get_active_year()

    @cached_stats_response(cache_key=f'basic:{year}', ttl=15)
    def _inner(req):
        return basic_stats(year=year)

    return _inner(request)


@stats_required
@require_http_methods(['GET'])
def full_stats_view(request):
    """Full statistikk for statistikk-dashboard. Kun admin, lead og lead_view.

    Cachet 60s med ETag/304. Dyre aggregater (percentiler, gruppetellinger)
    regnes kun én gang per minutt per år.
    """
    from .stats_cache import cached_stats_response
    year = get_active_year()

    @cached_stats_response(cache_key=f'full:{year}', ttl=60)
    def _inner(req):
        return full_stats(year=year)

    return _inner(request)


