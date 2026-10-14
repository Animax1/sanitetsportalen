"""Når CSRF-sjekken avviser en forespørsel (`CSRF_FAILURE_VIEW`, 14. okt. 2026).

Djangos egen side har en `<style>` uten nonce, og ble stående uten stiler etter at
`style-src-elem` kom — hvit tekst på hvitt, på engelsk, med en forklaring rettet
mot utviklere. Den vanlige grunnen her er ikke et angrep: en fane som har stått
over en utlogging, eller et skjema åpnet før sesjonen ble fornyet.

**To svar, etter hvem som spør.** Et `apiFetch`-kall leser JSON, og fikk HTML —
da kastet `res.json()`, og brukeren så «Nettverksfeil» om noe som var en utløpt
økt. `apiFetch` sender alltid `X-Portal-Inaktiv`; det er kjennetegnet.
Grunnen (`reason`) logges, men vises ikke: den sier hvilken sjekk som feilet, og
det er til hjelp for den som prøver å komme forbi den.
"""
from __future__ import annotations

import logging

from django.shortcuts import render

from core.jsonkropp import json_feil

logger = logging.getLogger(__name__)

MELDING = ('Økten din er utløpt, eller siden har stått åpen lenge. '
           'Last siden på nytt og prøv igjen.')


def er_api_kall(request) -> bool:
    return ('X-Portal-Inaktiv' in request.headers
            or request.content_type == 'application/json')


def csrf_feil(request, reason=''):
    logger.warning('CSRF avvist: %s %s (%s)', request.method, request.path, reason)
    if er_api_kall(request):
        return json_feil(MELDING, status=403)
    return render(request, '403.html', {
        'tittel': 'Siden må lastes på nytt',
        'melding': MELDING,
    }, status=403)
