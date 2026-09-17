"""KO-siden og endepunktene — pulje 1: skallet.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md`. To ruter i dag: siden med de fire
flatene, og sidebarens liste over hvem som har KO oppe.

**Flatene er tomme, og de sier det selv.** En «Oppdragsliste»-fane som bare er
blank ser ødelagt ut — særlig mens sentralbordet fortsatt står på `/oppdrag/`
og flyttes først i pulje 5. Hver flate bærer derfor én linje om hva som kommer
og hvor tingen bor i dag. Det er samme regel som «en knapp som fører til en
vegg er verre enn ingen knapp», bare fra den andre siden: en flate som ikke
forklarer seg leses som en feil.

**Alt her gater på `les`.** Modulen deklarerer ingen skrivenivåer i pulje 1 —
se `ko/module.py` for hvorfor.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, modul_kreves, nivaa_for
from core.ratelimit import rate_limit

from .tilstede import tilstede


@modul_kreves('ko', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """Situasjonsbildet. Fire flater og en sidebar, alle tomme i pulje 1.

    Konteksten bærer nivået fordi **grensesnittet gater på
    `window.MODUL_TILGANG`, ikke på rollen** (`CLAUDE.md`). Ingenting er gatet
    på klienten ennå — skallet har ingen knapper — men mønsteret settes her,
    slik at pulje 2 ikke må finne det opp.
    """
    return render(request, 'ko/index.html', {
        'modul_nivaa': nivaa_for(request.user, 'ko') or '',
        'er_global_admin': er_global_admin(request.user),
    })


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:tilstede', rate='120/m', method='GET')
def tilstede_view(request):
    """Hvem har KO oppe (§5.3).

    `never_cache`: en liste over hvem som sitter der nå, servert fra en cache,
    er en liste som lyver om nøyaktig det den finnes for.

    Bremsen er satt over pollingintervallet med god margin — sida henter hvert
    30. sekund, altså to i minuttet per fane. `120/m` treffer først den som
    poller i en løkke, og det er den vi vil bremse. Gruppen oppgis eksplisitt,
    som alle andre steder: den er cache-nøkkelen, og to endepunkter skal aldri
    dele teller.
    """
    return JsonResponse({'status': 'ok', 'data': tilstede()})
