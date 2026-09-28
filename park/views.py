"""De innloggede flatene i park-modulen: oppsettet på `/park/` (pulje 2).

Siden lagene bruker, uten innlogging, står i `views_lag.py` — med vilje i en
egen fil, så regelen «les aldri `request.user`» kan håndheves på hele fila.

| Handling | Krav |
|---|---|
| Se `/park/` | `les` — men `les` får bare en henvisning til statistikken (B17) |
| Lenkene: se, lage, fjerne | `skriv_leder` |
| Problemstillingene | `skriv_leder` (B6) |
| Utfallene | **global admin** (B7) |
| Slette en rad fra en verdimengde | global admin (`core.verdilister`) |
| Registreringene: se, slette én, slette alt fra en lenke etter kl. X | `skriv_leder` (B20) |

**Ingen rett, bare slett** (B20): en sletting og en ny registrering fra laget er
ærligere enn at noen andre skriver om det laget sa.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves, nivaa_for
from core.jsonkropp import json_body, json_feil
from core.klientip import klient_ip
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt
from core.verdilister import Verdiliste, lag_views

from . import services
from .models import Parklenke, Problemstilling, Registrering, Utfall

#: Hvor mange registreringer lista viser. Tallene hører hjemme i statistikken;
#: lista er for å finne den ene feilregistreringen.
LISTE_MAKS = 500


def kan_lede(user) -> bool:
    return har_tilgang(user, 'park', 'skriv_leder')


@modul_kreves('park', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """`/park/`. For `les` er tallene i `/statistikk/`, og siden sier det —
    en menyoppføring som fører til en vegg er verre enn ingen."""
    return render(request, 'park/index.html', {
        'leder': kan_lede(request.user),
        'modul_nivaa': nivaa_for(request.user, 'park') or '',
        'er_global_admin': er_global_admin(request.user),
    })


# ── Lenkene ──────────────────────────────────────────────────────────────────

def _lenke_til_dict(lenke, naa) -> dict:
    return {
        'id': lenke.pk,
        'navn': lenke.navn,
        'aapen_fra': lenke.aapen_fra.isoformat(),
        'aapen_til': lenke.aapen_til.isoformat(),
        'fjernet': lenke.fjernet_at is not None,
        'aapen_naa': (lenke.fjernet_at is None and lenke.aapen_fra <= naa < lenke.aapen_til),
        'sist_brukt_at': lenke.sist_brukt_at.isoformat() if lenke.sist_brukt_at else None,
        'opprettet_av': lenke.opprettet_av_navn,
        'antall': lenke.registreringer.filter(slettet_at__isnull=True).count(),
    }


def _tidspunkt(raa):
    t = parse_datetime(str(raa or ''))
    if t is None:
        return None
    return timezone.make_aware(t) if timezone.is_naive(t) else t


@never_cache
@modul_kreves('park', 'skriv_leder', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='park:lenker', rate='20/m', method='POST')
def lenker_view(request):
    """Lista (GET) eller en ny lenke (POST).

    **Tokenet står i svaret én gang, og aldri igjen** (§4.1). Klienten viser
    adressen og sier det; lukkes vinduet, lages en ny.
    """
    naa = timezone.now()
    if request.method == 'GET':
        return JsonResponse({'status': 'ok', 'data': [
            _lenke_til_dict(lenke, naa) for lenke in Parklenke.objects.all()[:100]]})
    data = json_body(request)
    fra, til = _tidspunkt(data.get('aapen_fra')), _tidspunkt(data.get('aapen_til'))
    if fra is None or til is None:
        return json_feil('Oppgi når lenken skal være åpen, fra og til.')
    try:
        lenke, token = services.lag_lenke(navn=data.get('navn'), aapen_fra=fra, aapen_til=til,
                                          bruker=request.user, ip=klient_ip(request))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _lenke_til_dict(lenke, naa),
                         'adresse': request.build_absolute_uri('/park/r/') + '#' + token},
                        status=201)


@modul_kreves('park', 'skriv_leder', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='park:lenke-fjern', rate='20/m', method='POST')
def lenke_fjern_view(request, pk):
    """Lenken slutter å virke med en gang. Krever `confirm`: tiltakskortet
    peker fortsatt på den, og lagene får en død lenke til det er oppdatert."""
    lenke = get_object_or_404(Parklenke, pk=pk)
    if not json_body(request).get('confirm'):
        return json_feil('Bekreftelse mangler.')
    services.fjern_lenke(lenke, bruker=request.user, ip=klient_ip(request))
    return JsonResponse({'status': 'ok', 'data': _lenke_til_dict(lenke, timezone.now())})


@modul_kreves('park', 'skriv_leder', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='park:lenke-slett-etter', rate='10/m', method='POST')
def lenke_slett_etter_view(request, pk):
    """«Slett alt fra denne lenken etter kl. X» — oppryddingen etter misbruk (§4.6).

    **Uten `confirm` svarer den 409 med antallet**, og sletter ingenting: den
    som rydder skal se hvor mye som går før det går. En dør hun må åpne
    bevisst, ikke en vegg (`FORSLAG_KO.md` §4.6).
    """
    lenke = get_object_or_404(Parklenke, pk=pk)
    data = json_body(request)
    etter = _tidspunkt(data.get('etter'))
    if etter is None:
        return json_feil('Oppgi tidspunktet slettingen skal gjelde fra.')
    vakt = hent_aktiv_vakt()
    antall = services.fra_lenke_etter(lenke, etter, vakt).count()
    if not data.get('confirm'):
        return JsonResponse({'status': 'error', 'antall': antall,
                             'message': f'{antall} registrering(er) slettes. Bekreft.'}, status=409)
    try:
        slettet = services.slett_fra_lenke(lenke, etter=etter, vakt=vakt, bruker=request.user,
                                           grunn=data.get('grunn'), ip=klient_ip(request))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'antall': slettet})


# ── Registreringene ──────────────────────────────────────────────────────────

def _registrering_til_dict(r) -> dict:
    return {
        'id': r.pk, 'registrert_at': r.registrert_at.isoformat(), 'lag': r.ressurs_navn,
        'sted': r.lokasjon_navn, 'problemstilling': r.problemstilling, 'antall': r.antall,
        'utfall': r.utfall, 'lenke': r.lenke_id,
        'slettet': r.slettet_at is not None, 'slettet_av': r.slettet_av_navn,
        'slettet_grunn': r.slettet_grunn,
    }


@never_cache
@modul_kreves('park', 'skriv_leder', svar='json')
@require_http_methods(['GET'])
def registreringer_view(request):
    """Denne vaktas registreringer, nyeste først — de slettede med, merket."""
    vakt = hent_aktiv_vakt()
    rader = Registrering.objects.filter(vakt=vakt)[:LISTE_MAKS]
    return JsonResponse({'status': 'ok', 'vakt': vakt.navn,
                         'maks': LISTE_MAKS,
                         'data': [_registrering_til_dict(r) for r in rader]})


@modul_kreves('park', 'skriv_leder', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='park:registrering-slett', rate='60/m', method='POST')
def registrering_slett_view(request, pk):
    rad = get_object_or_404(Registrering, pk=pk)
    try:
        services.slett_registrering(rad, bruker=request.user, grunn=json_body(request).get('grunn'),
                                    ip=klient_ip(request))
    except services.Ugyldig as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': _registrering_til_dict(rad)})


# ── Verdimengdene ────────────────────────────────────────────────────────────
#
# Samme fabrikk som oppdrag og KO (`core.verdilister`). I bruk = registreringer
# som bærer navnet: de lagrer det som tekst, så en sletting ville ikke rive
# dem — men en rad i bruk skal deaktiveres, ikke slettes, så statistikken
# fortsatt har noe å kalle den.

VERDILISTER = {
    'problemstillinger': (
        Verdiliste(Problemstilling,
                   i_bruk=lambda r: Registrering.objects.filter(problemstilling=r.navn).count()),
        kan_lede, 'Problemstillingene settes opp av skriv_leder i park.'),
    'utfall': (
        Verdiliste(Utfall, i_bruk=lambda r: Registrering.objects.filter(utfall=r.navn).count()),
        er_global_admin, 'Utfallene settes opp av global admin.'),
}


def _views(slug):
    liste, regel, nekt = VERDILISTER[slug]
    return lag_views(modul='park', liste=liste, slug=slug, kan_lede=regel, nekt=nekt,
                     gruppe='park:')


problemstillinger_view, problemstilling_detalj_view, problemstillinger_rekkefolge_view = \
    _views('problemstillinger')
utfall_view, utfall_detalj_view, utfall_rekkefolge_view = _views('utfall')
