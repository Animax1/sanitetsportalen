"""Ressursgruppene og rollene — typen ressurs, og plassene på den.

Delt ut av `vaktliste/views.py` i G2 (14. okt. 2026) — tilgangstersklene og
kartet over filene står i docstringen der.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.auth_decorators import modul_kreves
from core.ratelimit import rate_limit

from . import services
from .models import Ressursgruppe, Ressursrolle
from .views import _nektet, _int, _rolle_til_dict, _gruppe_til_dict


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='vaktliste:grupper', rate='60/m', method='POST')
def grupper_view(request):
    """Ressursgruppene: liste (GET) eller opprett (POST).

    **Å opprette en gruppe er `skriv_leder`.** Gruppa bestemmer hvilke roller
    en ressurs kan få og hvilken bemanningskurve den telles i; den er en del
    av oppsettet, ikke av bemanningen.

    Rekkefølgen settes automatisk til «sist», som på ressursene: den som
    legger til «Førstehjelpstelt» skal ikke måtte finne på et tall.
    """
    if request.method == 'GET':
        return JsonResponse({'status': 'ok', 'data': [
            _gruppe_til_dict(g) for g in Ressursgruppe.objects.all()]})

    if not services.kan_lede(request.user):
        return _nektet()

    data = json_body(request)
    navn = (data.get('navn') or '').strip()
    if not navn:
        return json_feil('Ressurstypen må ha et navn.')
    ikon = (data.get('ikon') or '').strip() or 'box'

    try:
        with transaction.atomic():
            gruppe = Ressursgruppe.objects.create(
                navn=navn, ikon=ikon,
                # Standard er en flåte. En gruppe som finnes i ett eksemplar
                # er unntaket, og skal oppgis eksplisitt.
                flere_enheter=bool(data.get('flere_enheter', True)),
                rekkefolge=(_int(data.get('rekkefolge'))
                            or services.neste_grupperekkefolge()))
    except IntegrityError:
        return json_feil(f'«{navn}» finnes allerede.')

    return JsonResponse(
        {'status': 'ok', 'data': _gruppe_til_dict(gruppe)}, status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='vaktliste:gruppe-skriv', rate='60/m', method=['PUT', 'DELETE'])
def gruppe_detalj_view(request, pk):
    """Rediger eller fjern en ressursgruppe. `skriv_leder`/admin.

    Sletting stoppes av `PROTECT` på `Ressurs.gruppe` når noen ressurs står på
    gruppa. Det er med vilje: en gruppe i bruk deaktiveres, den fjernes ikke —
    ellers ville en vaktliste mistet fanen sin fordi noen ryddet i et register.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    try:
        gruppe = Ressursgruppe.objects.get(pk=pk)
    except Ressursgruppe.DoesNotExist:
        return json_feil('Ressurstype ikke funnet', status=404)

    if request.method == 'DELETE':
        if gruppe.ressurser.exists():
            return json_feil(
                f'«{gruppe.navn}» er i bruk av {gruppe.ressurser.count()} '
                'enheter og kan ikke slettes. Deaktiver den i stedet — da '
                'forsvinner den fra nedtrekkene, men står igjen der den brukes.')
        # **Rollene følger med, og det skal sies høyt** (André, 16. sep. 2026).
        # `Ressursrolle.gruppe` er `CASCADE`, mens `Ressurs.gruppe` er
        # `PROTECT`: en gruppe uten ressurser *kan* slettes, og tok da rollene
        # sine med seg uten et ord. «Lagleder» og «Sjåfør» er oppsett noen har
        # skrevet inn, og de er borte for godt.
        #
        # Bekreftelsen kreves bare når det faktisk finnes roller — et
        # ekstra klikk på en tom gruppe er en vane man slutter å lese.
        roller = gruppe.roller.count()
        if roller and not json_body(request).get('confirm'):
            return json_feil(
                f'«{gruppe.navn}» har {roller} rolle(r) som slettes sammen med '
                'den. Bekreft for å fortsette.', status=409)
        gruppe.delete()
        return JsonResponse({'status': 'ok'})

    data = json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return json_feil('Ressurstypen må ha et navn.')
        gruppe.navn = navn
    if 'ikon' in data:
        gruppe.ikon = (data.get('ikon') or '').strip() or 'box'
    if 'flere_enheter' in data:
        gruppe.flere_enheter = bool(data['flere_enheter'])
    if 'er_aktiv' in data:
        gruppe.er_aktiv = bool(data['er_aktiv'])
    # Rutingflagget (`docs/FORSLAG_PARK.md` §3.4): gruppas ressurser kan
    # velges på parksiden. Oppsett, altså `skriv_leder` som resten her.
    if 'registrerer_i_park' in data:
        gruppe.registrerer_i_park = data['registrerer_i_park'] is True
    if 'rekkefolge' in data:
        gruppe.rekkefolge = _int(data['rekkefolge']) or 100

    try:
        with transaction.atomic():
            gruppe.save()
    except IntegrityError:
        return json_feil(f'«{gruppe.navn}» finnes allerede.')

    return JsonResponse({'status': 'ok', 'data': _gruppe_til_dict(gruppe)})


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT'])
@rate_limit(group='vaktliste:rollerekkefolge', rate='60/m', method='PUT')
def roller_rekkefolge_view(request):
    """Sett rekkefølgen på rollene i én gruppe. `skriv_leder`/admin.

    **Hele lista, ikke «opp» per rad** (samme idiom som verdimengdene i
    oppdragsmodulen). To «opp»-kall som krysser hverandre bytter to par og
    etterlater en rekkefølge ingen ba om; én forespørsel med den rekkefølgen
    klienten viser er atomisk og lar seg gjenta uten skade.

    **Bare roller i den oppgitte gruppa.** Uten avgrensningen kunne en liste
    med ID-er fra en annen gruppe skrevet tall inn der, og rekkefølgen er per
    gruppe — «Lagleder» på ambulansen og på samleplassen er to rader.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    data = json_body(request)
    gruppe_id = _int(data.get('gruppe_id'))
    ider = data.get('ider')
    if not gruppe_id or not isinstance(ider, list):
        return json_feil('Oppgi «gruppe_id» og «ider» som en liste.')

    roller = {r.pk: r for r in Ressursrolle.objects.filter(gruppe_id=gruppe_id)}
    if {_int(i) for i in ider} != set(roller):
        # **Hele gruppa, ikke et utvalg.** Et delvis sett ville gitt noen rader
        # nye tall og latt resten stå — og da er rekkefølgen en blanding av to
        # oppfatninger. Feilen er også den eneste måten å oppdage at klienten
        # og serveren ser ulike lister.
        return json_feil('Listen må inneholde nøyaktig rollene for ressurstypen.')

    with transaction.atomic():
        for plass, rolle_id in enumerate(ider, start=1):
            rolle = roller[_int(rolle_id)]
            rolle.rekkefolge = plass * 10
            rolle.save(update_fields=['rekkefolge'])

    return JsonResponse({'status': 'ok', 'data': [
        _rolle_til_dict(r) for r in
        Ressursrolle.objects.filter(gruppe_id=gruppe_id)]})
