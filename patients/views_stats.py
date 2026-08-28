"""Statistikk-endepunktet som ble igjen i pasientmodulen.

Full statistikk flyttet til ``statistikk``-appen august 2026.
``/api/stats/`` ble bevisst *ikke* med: den mater header-chipsene øverst på
pasientsiden, er åpen for alle innloggede, og hører til siden den står på.
Flyttet ville den gitt statistikkmodulen et endepunkt uten statistikkgate.
"""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from core.stats_cache import cached_stats_response

from .services import basic_stats, get_active_year


@login_required
@require_http_methods(['GET'])
def stats_view(request):
    """Basis-statistikk for header-chips. Filtrerer alltid på aktivt år.

    Cachet 15s med ETag/304 for å redusere last ved gjentatt polling.
    Cache-nøkkel inkluderer aktivt år slik at bytte av år gir ny cache.
    """
    year = get_active_year()

    @cached_stats_response(cache_key=f'basic:{year}', ttl=15)
    def _inner(req):
        return basic_stats(year=year)

    return _inner(request)
