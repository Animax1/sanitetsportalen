"""Hendelsene (pulje 5) — de navngitte skrivestiene.

Delt ut av `ko/views.py` i G2 (13. okt. 2026). Lesingen går med logg-pollen
(`logg_view` der), og `_hendelse_til_dict` bor der fordi både pollen,
utskriften og stiene her bruker den. Tilgangstabellen står i docstringen til
`ko/views.py`.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from core.auth_decorators import har_tilgang, modul_kreves
from core.jsonkropp import json_body, json_feil
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt

from . import services
from .models import Hendelse, Logglinje
from .views import _hendelse_til_dict


# ── Hendelsene (pulje 5) ─────────────────────────────────────────────────────
#
# Navngitte stier, som loggen: `ny`, `rediger`, `lukk`, `gjenapne`, og
# oppdragets `hendelse`. Hver av dem er én regel i `services`, og viewet eier
# bare HTTP-en: 400 for det som ikke lar seg gjøre, 409 for en konflikt om en
# tilstand, 404 for noe utenfor vakta.

def _hendelse(pk):
    return get_object_or_404(Hendelse, pk=pk, vakt=hent_aktiv_vakt())


def _lokasjon_fra(data):
    """`(lokasjon, feil)`. `lokasjon_id` som tall gir raden, `None`/tom gir
    ingen; et ukjent tall er 400 og ikke stille `None` — en lokasjon som
    forsvinner uten å si fra er en feil man finner i loggen et døgn senere."""
    from oppdrag.models import Lokasjon

    raa = data.get('lokasjon_id')
    if raa in (None, '', 0):
        return None, None
    try:
        return Lokasjon.objects.i_portal().get(pk=int(raa)), None
    except (Lokasjon.DoesNotExist, ValueError, TypeError):
        return None, 'Ukjent lokasjon.'


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_ny', rate='60/m', method='POST')
def hendelse_ny_view(request):
    """Ny hendelse — fra en logglinje (`fra_linje`) eller fra ingenting."""
    data = json_body(request)
    vakt = hent_aktiv_vakt()
    lokasjon, feil = _lokasjon_fra(data)
    if feil:
        return json_feil(feil)
    fra_linje = None
    if data.get('fra_linje'):
        fra_linje = get_object_or_404(Logglinje, pk=data['fra_linje'], vakt=vakt)
    try:
        hendelse = services.opprett_hendelse(
            vakt, data.get('tittel'), bruker=request.user,
            lokasjon=lokasjon, fra_linje=fra_linje,
            prioritet=data.get('prioritet'),
            beskrivelse=data.get('beskrivelse'),
            melder_typer=data.get('melder_typer'),
            melder=data.get('melder'),
            lag=data.get('lag'))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    hendelse = services.hendelse_med_telling(hendelse)
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)},
                        status=201)


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_rediger', rate='60/m', method='POST')
def hendelse_rediger_view(request, pk):
    """Tittel og lokasjon, med `versjon` — 409 når noen andre rakk det først
    (§7.1). `lokasjon_id` sendt som `null` tømmer; utelatt rører ikke."""
    hendelse = _hendelse(pk)
    data = json_body(request)
    lokasjon, feil = _lokasjon_fra(data)
    if feil:
        return json_feil(feil)
    try:
        services.rediger_hendelse(
            hendelse, bruker=request.user, versjon=data.get('versjon'),
            tittel=data.get('tittel'),
            lokasjon=lokasjon, sett_lokasjon='lokasjon_id' in data,
            melder_typer=data.get('melder_typer'),
            melder=data.get('melder'),
            lag=data.get('lag'))
    except services.Konflikt as feil:
        return json_feil(str(feil), status=409)
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_prioritet', rate='60/m', method='POST')
def hendelse_prioritet_view(request, pk):
    """Prioriteten — logget som egen linje (18. sep. 2026)."""
    hendelse = _hendelse(pk)
    try:
        services.sett_prioritet(hendelse, json_body(request).get('prioritet'),
                                bruker=request.user)
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_bli_med', rate='60/m', method='POST')
def hendelse_bli_med_view(request, pk):
    """«Bli med» (18. sep. 2026). Idempotent; svarer med lista."""
    hendelse = _hendelse(pk)
    services.bli_med(hendelse, request.user)
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_lest', rate='240/m', method='POST')
def hendelse_lest_view(request, pk):
    """«Jeg har sett hendelsen til og med linje `til`» (27. sep. 2026).

    **`les` holder**: å lese er det nivået gir, og merket er brukerens eget —
    det endrer ingenting noen andre ser. Samme grunn som ansvarsmerket.
    Svarer med merket slik det står etterpå; det går bare framover.
    """
    hendelse = _hendelse(pk)
    try:
        til = int(json_body(request).get('til'))
    except (TypeError, ValueError):
        return json_feil('«til» må være et tall.')
    return JsonResponse({'status': 'ok',
                         'til': services.merk_lest(request.user, hendelse, til)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_lag', rate='60/m', method='POST')
def hendelse_lag_view(request, pk):
    """Lagene på hendelsen (19. sep. 2026): hele lista med ressurs-id-er,
    og tjenestelaget regner differansen og logger hvert lag som kom til
    eller gikk. Lukket hendelse tar ikke imot."""
    hendelse = _hendelse(pk)
    try:
        services.sett_lag(hendelse, json_body(request).get('lag'), bruker=request.user)
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    hendelse = services.hendelse_med_telling(hendelse)
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_lukk', rate='60/m', method='POST')
def hendelse_lukk_view(request, pk):
    """Lukk. **409 med antallet** når hendelsen har åpne oppdrag, og gjennom
    med `{"confirm": true}` (§4.6). Operatøren skal aldri møte en vegg, bare
    en dør hun må åpne bevisst."""
    hendelse = _hendelse(pk)
    try:
        services.lukk_hendelse(
            hendelse, bruker=request.user,
            confirm=bool(json_body(request).get('confirm')))
    except services.HarApneOppdrag as feil:
        return JsonResponse({'status': 'error', 'message': str(feil),
                             'apne_oppdrag': feil.antall}, status=409)
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:hendelse_gjenapne', rate='60/m', method='POST')
def hendelse_gjenapne_view(request, pk):
    """Åpne igjen — logget som egen linje (André, 18. sep. 2026)."""
    hendelse = _hendelse(pk)
    try:
        services.gjenapne_hendelse(hendelse, bruker=request.user)
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _hendelse_til_dict(hendelse)})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:oppdrag_hendelse', rate='60/m', method='POST')
def oppdrag_hendelse_view(request, pk):
    """Knytt oppdraget til en hendelse (`hendelse_id`), eller løsne det
    (`null`).

    **Krever `skriv_full` i oppdragsmodulen også**, sjekket her og ikke bare
    i dekoratøren: kallet skriver på en oppdragsrad, og hvem som får skrive på
    oppdrag er oppdragsmodulens sak (komposisjonsregelen, rollemodellen §5).
    Dekoratøren gir KO-nivået; denne linja gir det andre.
    """
    from oppdrag.models import Oppdrag

    if not har_tilgang(request.user, 'oppdrag', 'skriv_full'):
        return json_feil('Krever skrivetilgang i oppdragsmodulen.', status=403)
    vakt = hent_aktiv_vakt()
    oppdrag = get_object_or_404(Oppdrag, pk=pk, vakt=vakt)
    data = json_body(request)
    hendelse = None
    if data.get('hendelse_id') is not None:
        hendelse = get_object_or_404(Hendelse, pk=data['hendelse_id'], vakt=vakt)
    try:
        services.knytt_oppdrag(oppdrag, hendelse, bruker=request.user)
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'hendelse_id': oppdrag.hendelse_id})

