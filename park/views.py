"""De innloggede flatene i park-modulen.

Siden lagene bruker, uten innlogging, står i `views_lag.py` — med vilje i en
egen fil, så regelen «les aldri `request.user`» kan håndheves på hele fila.

| Handling | Krav |
|---|---|
| Se `/park/` | `les` — men `les` får bare en henvisning til statistikken (B17) |
| Se lenkene og registreringene | `skriv_leder`, eller global admin |
"""
from __future__ import annotations

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from core.auth_decorators import har_tilgang, modul_kreves

from . import services
from .models import Parklenke, Registrering


@modul_kreves('park', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """`/park/`. For `les` er tallene i `/statistikk/`, og siden sier det —
    en menyoppføring som fører til en vegg er verre enn ingen."""
    leder = har_tilgang(request.user, 'park', 'skriv_leder')
    kontekst = {'leder': leder}
    if leder:
        vakt = services.aapen_vakt()
        kontekst.update({
            'vakt': vakt,
            'lenker': Parklenke.objects.all()[:50],
            'registreringer': (Registrering.objects.filter(vakt=vakt)[:200]
                               if vakt is not None else []),
            'lag_tilgjengelig': services.lagene().count(),
        })
    return render(request, 'park/index.html', kontekst)
