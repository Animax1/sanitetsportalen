"""Statistikk-endepunktet som ble igjen i pasientmodulen.

Full statistikk flyttet til ``statistikk``-appen august 2026. ``/api/stats/``
ble ikke med, men begrunnelsen som først ble skrevet her var feil: den sa at
endepunktet mater header-chipsene øverst på pasientsiden.

**Det gjør det ikke.** Chipsene regnes ut i nettleseren, i
``patients-table.js``, fra pasientlista ``/api/patients/`` allerede har hentet.
Ingen JS-fil i dette repoet har noen gang kalt ``/api/stats/`` — endepunktet er
en rest fra Flask-porten, og ``basic_stats``-docstringen sier det selv.

Det står altså uten kjent konsument. Om det skal gates på pasientmodulen eller
slettes, avgjøres i rollemodell-arbeidet; se «Rollemodellen» i TODO.md.
``basic_stats()`` som *funksjon* blir uansett stående — den deler
aggregeringen med ``compute_arkiv_stats``.
"""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from core.stats_cache import cached_stats_response

from .services import basic_stats, get_active_year


@login_required
@require_http_methods(['GET'])
def stats_view(request):
    """Basis-statistikk for aktivt år. Ingen kjent konsument, se modul-docstring.

    Cachet 15s med ETag/304 for å redusere last ved gjentatt polling.
    Cache-nøkkel inkluderer aktivt år slik at bytte av år gir ny cache.
    """
    year = get_active_year()

    @cached_stats_response(cache_key=f'basic:{year}', ttl=15)
    def _inner(req):
        return basic_stats(year=year)

    return _inner(request)
