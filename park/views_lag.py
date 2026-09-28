"""Siden lagene bruker — **uten innlogging** (`docs/FORSLAG_PARK.md` §4).

Portalens første flate som svarer en anonym klient. Reglene her er derfor
strengere enn ellers, og hver av dem har en test:

- **Ingen view her leser `request.user`.** En portalbruker som åpner siden i
  samme nettleser sender innloggingen sin med; den skal ikke bety noe.
  `park/tests.py` leser fila og håndhever det.
- **Tokenet kommer i headeren `X-Park-Lenke`**, aldri i stien: siden leser det
  fra fragmentet (`/lag/r/#…`), som nettleseren ikke sender til serveren og
  derfor aldri havner i Railways tilgangslogg.
- **Ugyldig, fjernet, stengt lenke og ingen åpen vakt gir samme svar**
  (`services.aapen_lenke`).
- **Svarene inneholder aldri registreringer** (§4.3) — bare verdimengdene, et
  forhåndsvalg for ett lag, og kvitteringen for det klienten selv sendte.

**Tre bøtter for rate-limit** (§4.5): per IP bare for *ugyldige* tokens, per
telefon, og et tak per lenke. Ikke per IP på gyldige: telefoner på mobilnett
deler adresse bak operatørens NAT.
"""
from __future__ import annotations

import uuid
from functools import wraps

from django.http import JsonResponse
from django_ratelimit import ALL
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.klientip import ratelimit_nokkel
from core.ratelimit import er_rate_limited

from . import services

LENKE_HEADER = 'HTTP_X_PARK_LENKE'
TELEFON_HEADER = 'HTTP_X_PARK_TELEFON'

#: Grensene (§4.5). Telefonen er den strammeste; lenken er et tak for misbruk i
#: stor skala, høyt nok til at alle lagene samlet aldri når det.
GRENSE_TELEFON = '60/m'
GRENSE_LENKE = '1200/m'
GRENSE_UGYLDIG = '20/m'

AVVIST = 'Lenken er ikke åpen. Sjekk tiltakskortet, eller spør KO.'


def _telefon_nokkel(group, request):
    return f'telefon:{request.park_telefon}'


def _lenke_nokkel(group, request):
    return f'lenke:{request.park_lenke.pk}'


def _telefon(request) -> str | None:
    """Telefon-ID-en klienten sender, som kanonisk UUID — eller None.

    Den identifiserer ingen person og lagres ikke; den er bare bøtta som gjør
    at ett skript ikke kan tømme kvoten for alle lagene. Den er en påstand fra
    klienten, og stopper derfor ikke den som vet hva han gjør — det gjør taket
    per lenke, oppetiden og at lenken kan fjernes (§4.5).
    """
    try:
        return str(uuid.UUID(request.META.get(TELEFON_HEADER, '')))
    except (TypeError, ValueError, AttributeError):
        return None


def park_lenke_kreves(view):
    """Gaten for API-et under `/lag/r/`: gyldig lenke, telefon-ID, grensene.

    Setter `_park_lenke_kreves`, som `park/tests.py` krever på hver slik rute —
    samme grep som `_modul_kreves`: en glemt dekoratør skal bli rød.
    """
    @csrf_exempt  # Ingen sesjon å verne; tokenet går i en header en fremmed
    # side ikke kan sette uten en CORS-preflight vi ikke besvarer (§4.5).
    @never_cache
    @wraps(view)
    def innpakket(request, *args, **kwargs):
        lenke = services.aapen_lenke(request.META.get(LENKE_HEADER, ''))
        if lenke is None:
            # Tell bare det feilede forsøket — CLAUDE.md, «Tell riktig
            # hendelse, ikke bare riktig endepunkt».
            if er_rate_limited(request, group='park:ugyldig', key=ratelimit_nokkel,
                               rate=GRENSE_UGYLDIG, method=ALL):
                return json_feil('For mange forsøk. Vent litt.', status=429)
            return json_feil(AVVIST, status=403)
        telefon = _telefon(request)
        if telefon is None:
            return json_feil('Siden mangler en nøkkel. Last den på nytt.', status=400)
        request.park_lenke = lenke
        request.park_telefon = telefon
        if er_rate_limited(request, group='park:telefon', key=_telefon_nokkel,
                           rate=GRENSE_TELEFON, method=ALL):
            return json_feil('For mange forespørsler fra denne telefonen. Vent litt.',
                             status=429)
        if er_rate_limited(request, group='park:lenke', key=_lenke_nokkel,
                           rate=GRENSE_LENKE, method=ALL):
            return json_feil('Siden er overbelastet. Vent litt og prøv igjen.', status=429)
        return view(request, *args, **kwargs)

    innpakket._park_lenke_kreves = True
    return innpakket


@require_http_methods(['GET'])
def side_view(request):
    """Selve siden. Statisk — ingen data, ingen token; alt hentes av skriptet."""
    return render(request, 'park/lag.html')


@require_http_methods(['GET'])
@park_lenke_kreves
def oppsett_view(request):
    """Nedtrekkene: lagene, stedene og verdimengdene. Ikke noe annet."""
    vakt = services.aapen_vakt()
    return JsonResponse({
        'vakt': vakt.navn,
        'lag': [{'id': r.pk, 'navn': r.navn} for r in services.lagene()],
        'steder': [{'id': s.pk, 'navn': s.navn} for s in services.steder()],
        'problemstillinger': [{'id': p.pk, 'navn': p.navn}
                              for p in services.problemstillinger()],
        'utfall': [{'id': u.pk, 'navn': u.navn} for u in services.utfall()],
        'angrefrist_min': services.angrefrist_min(),
    })


@require_http_methods(['GET'])
@park_lenke_kreves
def sted_view(request):
    """Forhåndsvalget for **ett** lag (§5.1) — aldri for alle på én gang."""
    try:
        lag_id = int(request.GET.get('lag', ''))
    except (TypeError, ValueError):
        return json_feil('Ugyldig lag.')
    if not services.lagene().filter(pk=lag_id).exists():
        return json_feil('Laget finnes ikke på vaktlista.', status=404)
    valg = services.forhandsvalg(services.aapen_vakt(), lag_id)
    return JsonResponse({
        'sted': valg['lokasjon_id'],
        'kilde': valg['kilde'],
        'tid': valg['tid'].isoformat() if valg['tid'] else None,
    })


@require_http_methods(['POST'])
@park_lenke_kreves
def registrer_view(request):
    vakt = services.aapen_vakt()
    try:
        rad, ny = services.registrer(request.park_lenke, vakt, json_body(request))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'ny': ny, 'kvittering': services.kvittering(rad, vakt)},
                        status=201 if ny else 200)


@require_http_methods(['POST'])
@park_lenke_kreves
def angre_view(request):
    try:
        services.angre(request.park_lenke, json_body(request).get('idempotency_key'))
    except services.Ugyldig as feil:
        return json_feil(str(feil), status=409)
    return JsonResponse({'status': 'ok'})
