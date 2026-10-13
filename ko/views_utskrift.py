"""KO-utskriften og service workeren som holder den uten nett (13. okt. 2026).

Delt ut av `ko/views.py` i G2 (13. okt. 2026). Tilgangstabellen for hele
modulen står i docstringen der; reglene for utskriften i `ko/utskrift.py`.
"""
from __future__ import annotations

from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import modul_kreves
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt


@never_cache
@modul_kreves('ko', 'les')
@require_http_methods(['GET'])
@rate_limit(group='ko:utskrift', rate='30/m', method='GET', on_limit='html')
def utskrift_view(request):
    """KO på papir — alle vinduene, alltid. Se `ko/utskrift.py`.

    **Aktiv vakt alltid**: et øyeblikksbilde av hva som pågår har ingen mening
    for en vakt som er avsluttet. Hentes også i bakgrunnen av KO-siden, så
    `/ko/sw.js` har en kopi når nettet er borte — og **bare svar med
    `KOPI_HODE` lagres**, som settes for personlige kontoer.
    """
    from . import utskrift

    vakt = hent_aktiv_vakt()
    kontekst = utskrift.bygg(request, vakt)
    kontekst.update(vakt=vakt, utskrevet=timezone.localtime())
    svar = render(request, 'ko/utskrift.html', kontekst)
    if utskrift.kan_lagres_lokalt(request.user):
        svar[utskrift.KOPI_HODE] = '1'
    return svar


@require_http_methods(['GET'])
def sw_view(request):
    """Service workeren for `/ko/` — utskriften uten nett (13. okt. 2026).

    Serveres fra en view og ikke fra `/static/` av samme grunn som
    vaktlistas (`vaktliste.views.sw_view`): en worker styrer bare stier under
    sin egen. **Ingen innlogging** — fila bærer ingen data, og en utgått
    sesjon skal ikke gi en worker som er en innloggingsside. `no-cache` så
    nettleseren ser etter ny versjon ved hver sidelasting.
    """
    from pathlib import Path

    from django.conf import settings as _settings
    from django.http import HttpResponse
    sti = Path(_settings.BASE_DIR) / 'static' / 'js' / 'ko-sw.js'
    svar = HttpResponse(sti.read_text(encoding='utf-8'),
                        content_type='application/javascript; charset=utf-8')
    svar['Cache-Control'] = 'no-cache'
    svar['Service-Worker-Allowed'] = '/ko/'
    svar['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'"
    return svar

