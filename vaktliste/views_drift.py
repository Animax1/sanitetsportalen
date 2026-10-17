"""Drift: inn og ut av drift, stemplingene, fila på e-post og service workeren.

Delt ut av `vaktliste/views.py` i G2 (14. okt. 2026) — tilgangstersklene og
kartet over filene står i docstringen der.
"""
from __future__ import annotations

from pathlib import Path

from django.db import transaction
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.auth_decorators import modul_kreves
from core.ratelimit import rate_limit

from . import choices, fil, services, vaktdrift
from .models import Utsending, Vaktliste, Vaktpost
from .views import _nektet, _vaktliste_til_dict, _vaktpost_til_dict


# ── Drift (fase 4) ───────────────────────────────────────────────────────────

@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:drift', rate='30/m', method='POST')
def drift_view(request, pk, tilstand):
    """Åpne eller stenge innsjekken. Ett navngitt endepunkt per retning.

    **Drift betyr én ting: innsjekk er åpen** (§5). Ikke en livssyklus, ikke
    en låsing — lista kan fortsatt endres, for folk uteblir og bytter, og en
    liste som låser seg idet vakta starter er en liste som forlates til
    fordel for et ark.

    **Retningen står i URL-en, ikke i kroppen.** Samme grep som
    `oppdrag.views.stempling_view`: `POST .../veksle/` ville gitt et kappløp
    når to trykk kommer tett, og den som trykket sist ville ikke visst hva
    hun endte på.

    `skriv_full`, ikke `skriv_leder`: å åpne innsjekken er en driftshandling
    under vakta, ikke en del av oppsettet. Og ikke `skriv_handling` — se
    `services.kan_stemple`.

    Ut av drift er reversibel og **rører ingen stempler**. Det er en dør, ikke
    en sletting.
    """
    if tilstand not in ('start', 'stopp'):
        return json_feil(f'Ukjent tilstand «{tilstand}».', status=404)
    if not services.kan_skrive_alt(request.user):
        return _nektet()

    try:
        vl = Vaktliste.objects.i_portal().select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)

    if tilstand == 'stopp':
        vl.status = choices.PLANLEGGING
        vl.save(update_fields=['status', 'updated_at'])
        return _svar(request, vl, None)

    if vl.arkivert_at is not None:
        # Samme sperre motsatt vei (A6): en arkivert liste er ute av velgeren.
        return json_feil('Listen er arkivert. Hent den tilbake før den settes i drift.',
                         status=409)
    with transaction.atomic():
        # **Én vaktliste i drift per portal** (`vaktdrift.annen_i_drift`). Portalen
        # låses først, så to trykk på to ulike lister ikke begge slipper gjennom.
        vaktdrift.laas_portalen(vl)
        annen = vaktdrift.annen_i_drift(vl)
        if annen is not None:
            return json_feil(
                f'«{annen.vakt.navn}» står alt i drift. Det kan bare være én vaktliste '
                f'i drift om gangen — ta den ut av drift først.', status=409)
        vl.status = choices.DRIFT
        # Tidspunktet settes kun ved åpning, og beholdes ved en senere
        # stenging: «i drift siden 08:04» skal fortsatt kunne leses etterpå.
        vl.satt_i_drift_at = timezone.now()
        vl.satt_i_drift_av = request.user
        # Knappen er overstyringen: en person satte den, ikke klokka.
        vl.drift_automatisk = False
        vl.save(update_fields=['status', 'satt_i_drift_at', 'satt_i_drift_av',
                               'drift_automatisk', 'updated_at'])
    # **Reserven sendes ved vaktstart** (12. sep. 2026) når admin har slått det
    # på og satt mottakere. Etter at drift er lagret, og aldri som en sperre: en
    # e-posttjeneste som er nede skal ikke hindre at innsjekken åpner.
    # `send_fil` kaster ikke; svaret bærer resultatet.
    utsending = None
    if fil.sendes_ved_drift(vl.vakt.portal) and fil.mottakere(vl.vakt.portal):
        utsending = fil.send_fil(vl, bruker=request.user, utloest=Utsending.DRIFT)
    return _svar(request, vl, utsending)


def _svar(request, vl, utsending):
    data = _vaktliste_til_dict(vl, request.user)
    data['utsending'] = fil.utsending_til_dict(utsending)
    return JsonResponse({'status': 'ok', 'data': data})


@never_cache
@modul_kreves('vaktliste', 'les', svar='html')
@require_http_methods(['GET'])
def fil_view(request, pk):
    """Vaktlista som selvstendig HTML-fil, til nedlasting (12. sep. 2026).

    Samme fil som e-posten sender. `skriv_full` (`kan_skrive_alt`): fila
    bærer telefonnumre for hele vakta, og det er vaktleders bord. Ingen
    `Utsending`-rad — nedlasting til egen maskin er ikke en utlevering.
    """
    from django.http import HttpResponse
    if not services.kan_skrive_alt(request.user):
        return HttpResponse('Ingen tilgang', status=403)
    try:
        vl = Vaktliste.objects.i_portal().select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return HttpResponse('Vaktliste ikke funnet', status=404)
    svar = HttpResponse(fil.bygg_fil(vl), content_type='text/html; charset=utf-8')
    svar['Content-Disposition'] = f'attachment; filename="{fil.filnavn(vl)}"'
    return svar


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:send_fil', rate='10/m', method='POST')
def send_fil_view(request, pk):
    """Send vaktlista som fil til mottakerne admin har satt (12. sep. 2026).

    `skriv_full`, som drift. Mottakerne velges ikke her — de er en fast
    liste under portalinnstillingene, så vi vet hvor fila går. 400 uten
    mottakere, med beskjed om hvor de settes; 502 når e-posttjenesten sa nei,
    men raden er lagret uansett, med feilen.
    """
    if not services.kan_skrive_alt(request.user):
        return _nektet()
    try:
        vl = Vaktliste.objects.i_portal().select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)
    if not fil.mottakere(vl.vakt.portal):
        return json_feil('Ingen mottakere er satt. Global admin setter dem under '
                     'Portalinnstillinger → «Vaktlisten på e-post».')
    rad = fil.send_fil(vl, bruker=request.user, utloest=Utsending.KNAPP)
    if rad.feil:
        return JsonResponse({'status': 'error', 'message': f'Filen ble ikke sendt: {rad.feil}',
                             'data': fil.utsending_til_dict(rad)}, status=502)
    return JsonResponse({'status': 'ok', 'data': fil.utsending_til_dict(rad)})


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:stempling', rate='120/m', method='POST')
def stempling_view(request, pk, handling):
    """Møtt, av vakt, og angring av begge. Ett endepunkt per navngitt overgang.

    **Kroppen bærer bare `tidspunkt`, og den er valgfri.** Knappen vet
    hvilken overgang den utfører, og serveren utleder ingenting av gjeldende
    tilstand — nøyaktig som `oppdrag.views.stempling_view`. Reglene selv
    ligger som data i `services.STEMPLINGER`. Tidspunktet kom 13. sep. 2026
    med offline drift: en stempling som lå i kø på drifts-PC-en skal få tida
    trykket skjedde, ikke tida nettet kom tilbake — `services.vurder_klienttid`
    sier når klienttida er til å stole på.

    Tre porter, og de svarer på hver sin ting:

    1. **Hvem:** `services.kan_stemple` — ikke korps-føreren (avklaring 11.3).
    2. **Når:** lista må være i drift. Et møtt-stempel før vakta finnes ikke,
       og et stempel etter at innsjekken er stengt er en rad ingen har tatt
       ansvar for.
    3. **Hva:** overgangens egne forutsetninger — «av vakt» krever «møtt».

    Rekkefølgen er med vilje: en korps-fører som trykker skal få vite at hun
    ikke har lov, ikke at lista ikke er i drift.
    """
    if handling not in services.STEMPLINGER:
        return json_feil(f'Ukjent stempling «{handling}».', status=404)
    if not services.kan_stemple(request.user):
        return _nektet()

    try:
        vp = (Vaktpost.objects.i_portal()
              .select_related('ressurs__vaktliste', 'mannskap__korps', 'rolle')
              .get(pk=pk))
    except Vaktpost.DoesNotExist:
        return json_feil('Skiftet finnes ikke', status=404)

    # Klokka før porten: første stempel etter start skal ikke få 409 fordi
    # middlewaren ennå ikke har sjekket (30. sep. 2026).
    if vaktdrift.sett_i_drift_ved_start(vp.ressurs.vaktliste):
        vp.ressurs.vaktliste.refresh_from_db()
    if not vp.ressurs.vaktliste.i_drift:
        return json_feil(
            'Innsjekken er stengt. Sett vaktlisten i drift først — da åpnes '
            'møtt og av vakt.', status=409)

    klienttid = None
    raa = json_body(request).get('tidspunkt') if request.body else None
    if raa:
        klienttid = parse_datetime(str(raa))
        if klienttid is None:
            return json_feil('Ugyldig tidspunkt.')

    ok, melding = services.stemple(vp, handling, naa=services.vurder_klienttid(klienttid))
    if not ok:
        return json_feil(melding)
    vp.save(update_fields=['mott_at', 'av_vakt_at', 'updated_at'])

    return JsonResponse({
        'status': 'ok',
        'data': _vaktpost_til_dict(vp, services.foreldrekart()),
    })


@require_http_methods(['GET'])
def sw_view(request):
    """Service workeren for `/vaktliste/` — offline drift (13. sep. 2026).

    Serveres fra en view, ikke fra `/static/`, fordi en service worker bare
    kan styre stier under sin egen: lå den under `/static/js/`, dekket den
    ingenting. Ingen innlogging: registreringen skjer fra den innloggede
    siden, men en utgått sesjon skal ikke gi en workeren som er en
    innloggingsside. Fila bærer ingen data.

    `Cache-Control: no-cache` så nettleseren sjekker for ny versjon ved hver
    sidelasting, og en egen CSP: workeren henter Bootstrap fra CDN-en for å
    legge det i cachen, og sidens `connect-src 'self'` ville stoppet det.
    """
    from django.conf import settings as _settings
    from django.http import HttpResponse
    sti = Path(_settings.BASE_DIR) / 'static' / 'js' / 'vaktliste-sw.js'
    svar = HttpResponse(sti.read_text(encoding='utf-8'),
                        content_type='application/javascript; charset=utf-8')
    svar['Cache-Control'] = 'no-cache'
    svar['Service-Worker-Allowed'] = '/vaktliste/'
    # Bibliotekene ligger under /static/ siden 13. sep. 2026 (H3) — workeren
    # trenger ikke nå noe utenfor eget opphav.
    svar['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'"
    return svar
