"""Overnattingen — rommene og hvem som sover hvor.

Delt ut av `vaktliste/views.py` i G2 (14. okt. 2026) — tilgangstersklene og
kartet over filene står i docstringen der.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.auth_decorators import modul_kreves
from core.ratelimit import rate_limit

from . import overnatting
from .models import Mannskap, Overnatting, Overnattingsrom, Vaktliste
from .views import _nektet, _int


# ── Overnatting (25. sep. 2026) ─────────────────────────────────────────────
#
# Reglene står i `overnatting.py`. Tre terskler: rommene er lederens
# (`kan_sette_opp`), å plassere en person følger personens korps
# (`kan_plassere`), og å se lista er `les` — som hele siden.

def _svar_rom(rom):
    return JsonResponse({'status': 'ok', 'data': overnatting.rom_til_dict(rom)})


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:overnattingsrom', rate='60/m', method='POST')
def overnattingsrom_view(request, pk):
    """Nytt rom på en vaktliste. Lederens, som ressursene."""
    if not overnatting.kan_sette_opp(request.user):
        return _nektet('Rommene settes opp av den som setter opp vakten.')
    vl = Vaktliste.objects.select_related('vakt').filter(pk=pk).first()
    if vl is None:
        return json_feil('Vaktliste ikke funnet', status=404)
    try:
        rom = overnatting.lagre_rom(vl, json_body(request))
    except overnatting.Ugyldig as e:
        return json_feil(str(e))
    svar = _svar_rom(rom)
    svar.status_code = 201
    return svar


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='vaktliste:overnattingsrom-skriv', rate='120/m', method=['PUT', 'DELETE'])
def overnattingsrom_detalj_view(request, pk):
    """Endre eller fjern et rom.

    **DELETE krever `{"confirm": true}`**, som en ressurs: plasseringene går
    med rommet, og en brannliste som mister et rom uten at noen mente det er
    verre enn en som mangler et.
    """
    if not overnatting.kan_sette_opp(request.user):
        return _nektet('Rommene settes opp av den som setter opp vakten.')
    rom = Overnattingsrom.objects.select_related('vaktliste').filter(pk=pk).first()
    if rom is None:
        return json_feil('Rommet finnes ikke', status=404)
    data = json_body(request)
    if request.method == 'DELETE':
        if not data.get('confirm'):
            return json_feil('Bekreftelse mangler. Send {"confirm": true}.')
        antall = overnatting.slett_rom(rom)
        return JsonResponse({'status': 'ok', 'data': {'fjernet_plasseringer': antall}})
    try:
        rom = overnatting.lagre_rom(rom.vaktliste, data, rom=rom)
    except overnatting.Ugyldig as e:
        return json_feil(str(e))
    return _svar_rom(rom)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:overnatting-plasser', rate='120/m', method='POST')
def overnatting_plasser_view(request, pk):
    """Legg en person i rommet, én eller flere netter.

    `{"mannskap_id": 7, "netter": ["2026-09-12", ...], "flytt": false}`.
    Sover hun et annet sted en av nettene, er svaret **409 med nettene** —
    vinduet spør om hun skal flyttes, og sender da `flytt: true`.
    """
    rom = Overnattingsrom.objects.select_related('vaktliste__vakt').filter(pk=pk).first()
    if rom is None:
        return json_feil('Rommet finnes ikke', status=404)
    data = json_body(request)
    mannskap = Mannskap.objects.i_portal().filter(pk=_int(data.get('mannskap_id'))).first()
    if mannskap is None:
        return json_feil('Velg en person fra mannskapsregisteret.')
    if not overnatting.kan_plassere(request.user, mannskap):
        return _nektet('Du kan bare plassere mannskap fra ditt eget korps.')
    try:
        rader = overnatting.plasser(rom, mannskap, data.get('netter'),
                                    flytt=data.get('flytt') is True)
    except overnatting.Konflikt as e:
        return JsonResponse({'status': 'error', 'message': str(e), 'konflikt': e.netter},
                            status=409)
    except overnatting.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok', 'data': [
        {'id': o.pk, 'natt': o.natt.isoformat(), 'rom_id': o.rom_id} for o in rader]},
        status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['DELETE'])
@rate_limit(group='vaktliste:overnatting-fjern', rate='120/m', method='DELETE')
def overnatting_detalj_view(request, pk):
    """Ta en person ut av rommet én natt. Samme terskel som å plassere."""
    rad = Overnatting.objects.select_related('mannskap').filter(pk=pk).first()
    if rad is None:
        return json_feil('Plasseringen finnes ikke', status=404)
    if not overnatting.kan_plassere(request.user, rad.mannskap):
        return _nektet('Du kan bare flytte mannskap fra ditt eget korps.')
    overnatting.fjern(rad)
    return JsonResponse({'status': 'ok'})
