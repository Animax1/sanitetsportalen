"""Løpende posisjon fra bilen, og «Hent posisjon» fra KO (19. okt. 2026).

Regelen — når, hvor ofte, hvem — står i `oppdrag/posisjon.py`. Her står de tre
portene: bilen som sender, KO som spør etter én bil, og KO som spør en gruppe.
`docs/PLAN_LOPENDE_POSISJON.md` har avveiningene.
"""
from __future__ import annotations

import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core import kartkobling
from core.jsonkropp import json_body, json_feil, les_json
from core.auth_decorators import modul_kreves
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt

from . import choices, posisjon
from . import endringer as oppdrag_endringer
from .models import Enhet
from .views_common import er_enhetskonto, ikke_for_enhetskonto

logger = logging.getLogger(__name__)


def _bremset(enhet, intervall: int, naa) -> bool:
    """Sendte bilen løpende for nylig, målt mot intervallet **nå**? Husker
    tidspunktet når den ikke gjorde det.

    Tidspunktet lagres, ikke en sperre med levetid: rykker bilen ut på akutt
    rett etter en sending på fem minutter, skal neste gå om 30 sekunder, ikke
    om fire minutter. **Faller åpen ved cache-feil**, som rate-limitingen:
    kartet er et hjelpemiddel, og en død cache skal ikke stanse posisjonene."""
    nokkel = f'oppdrag:posisjon_lopende:{enhet.pk}'
    try:
        sist = cache.get(nokkel)
        if sist is not None and naa.timestamp() - sist < posisjon.bremse_s(intervall):
            return True
        cache.set(nokkel, naa.timestamp(), posisjon.MAKS_S)
    except Exception:   # noqa: BLE001 — se docstringen
        return False
    return False


@modul_kreves('oppdrag', 'skriv_handling', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:posisjon_lopende', rate='20/m', method='POST')
def posisjon_lopende_view(request):
    """Bilens løpende posisjon, eller svaret på «Hent posisjon» fra KO.

    **Til kartets vanlige bilmarkør** (`send_enhet`), ikke til «OBS: Posisjon
    delt» — en bil som oppdateres hvert 30. sekund skal ikke stå oransje.

    **Serveren er bremsen.** Intervallet regnes ut her, med samme funksjon som
    sender det til bilen på pollet; sender bilen oftere, er svaret 429. Et svar
    på en forespørsel fra KO slipper forbi bremsen — det er nettopp den ene
    sendingen KO ba om. Kroppen er lukket, `{"posisjon": {"lat", "lon", "tid"}}`,
    og posisjonen lagres aldri.

    **Direkte, ikke i `on_commit`**: ingenting skrives før kartet har svart, og
    KO skal bare se «mottatt» når kartet tok imot. Kallet mot kartet har
    `TIMEOUT_S` og pause etter feil (`core/kartkobling.py`), så et kart som er
    nede holder en tråd i høyst tre sekunder i minuttet.
    """
    if not er_enhetskonto(request.user):
        return json_feil('Bare enhetskontoer sender posisjon.', 403)
    if not kartkobling.er_konfigurert():
        return json_feil('Kartkoblingen er ikke satt opp.', 409)
    enhet = request.user.enhet
    try:
        data = les_json(request.body or b'{}')
    except ValueError:
        return json_feil('Ugyldig JSON i kroppen.', 400)
    if not isinstance(data, dict) or set(data) != {'posisjon'}:
        return json_feil('Kroppen skal være {"posisjon": …}.', 400)
    try:
        lat, lon, tid = kartkobling.les_posisjon(data['posisjon'])
    except ValueError:
        return json_feil('Ugyldig posisjon.', 400)
    vakt = hent_aktiv_vakt()
    naa = timezone.now()
    onsket = enhet.pa_vakt and posisjon.lopende_aktiv() and posisjon.er_onsket(enhet)
    if not onsket:
        intervall = posisjon.intervall_for(enhet, vakt)
        if intervall is None:
            return json_feil('Løpende posisjon er ikke på for bilen nå.', 409)
        if enhet.posisjonsdeling == choices.POSISJONSDELING_AV:
            return json_feil('Deling av posisjon er slått av på bilskjermen.', 409)
        if _bremset(enhet, intervall, naa):
            return json_feil('For tett — neste posisjon sendes ved neste intervall.', 429)
    if not kartkobling.send_enhet(enhet.navn, lat, lon, tid, vakt=vakt):
        return json_feil('Kartet tok ikke imot posisjonen.', 424)
    if onsket:
        posisjon.noter_mottatt(enhet, naa)
    return JsonResponse({'status': 'ok', 'data': {'sendt_at': naa.isoformat(), 'onsket': onsket}})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@ikke_for_enhetskonto
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:hent_posisjon', rate='30/m', method='POST')
def hent_posisjon_view(request, pk):
    """«Hent posisjon» på én bil (André, 19. okt. 2026, skisse A).

    Merker enheten; bilen ser det på neste poll (innen 15 s) og sender en fersk
    posisjon. **Også i passiv vakt** — det er KO som spør, ikke en klokke.
    Svaret er 202: forespørselen er tatt imot, posisjonen er ikke kommet ennå.
    Hver henting logges i KO med hvem (C3), gjennom `posisjon.posisjon_hentet`.
    """
    enhet = Enhet.objects.filter(pk=pk, er_aktiv=True).first()
    if enhet is None:
        return json_feil('Enhet ikke funnet', 404)
    grunn = posisjon.hindring(enhet)
    if grunn:
        return json_feil(grunn, 409)
    naa = timezone.now()
    posisjon.be_om(enhet, request.user, naa=naa)
    _meld_hentet([enhet], request.user, gruppe=None)
    return JsonResponse({'status': 'ok', 'data': {'id': enhet.pk, 'bedt_at': naa.isoformat()}},
                        status=202)


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@ikke_for_enhetskonto
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:hent_posisjon_alle', rate='6/m', method='POST')
def hent_posisjon_alle_view(request):
    """«Hent posisjon fra alle» i en gruppe i ressursoversikten (skisse A).

    Kroppen `{"type": <enhetstype-id>}` avgrenser til gruppa, `{"type": null}`
    er enhetene uten type; uten feltet spørres alle på vakt. Biler som ikke kan
    svare — av vakt, deling slått av, nektet — hoppes over og telles, i stedet
    for at hele trykket avvises. **Én linje i KO-loggen**, ikke én per bil.
    """
    data = json_body(request)
    if not kartkobling.er_konfigurert():
        return json_feil('Kartkoblingen er ikke satt opp.', 409)
    if not posisjon.lopende_aktiv():
        return json_feil('Løpende posisjon er slått av i bilinnstillingene.', 409)
    qs = Enhet.objects.filter(er_aktiv=True, pa_vakt=True).select_related('enhetstype')
    gruppe = None
    if 'type' in data:
        if data['type'] is None:
            qs = qs.filter(enhetstype__isnull=True)
            gruppe = 'Uten type'
        else:
            try:
                qs = qs.filter(enhetstype_id=int(data['type']))
            except (TypeError, ValueError):
                return json_feil('Send `type` som en enhetstype-ID eller null.', 400)
    kandidater = list(qs)
    if gruppe is None and 'type' in data and kandidater:
        gruppe = kandidater[0].enhetstype.navn
    bedt = [e for e in kandidater if posisjon.hindring(e) is None]
    if not bedt:
        return json_feil('Ingen av bilene kan svare nå — se ikonene på kortene.', 409)
    naa = timezone.now()
    Enhet.objects.filter(pk__in=[e.pk for e in bedt]).update(
        posisjon_bedt_at=naa, posisjon_bedt_av=request.user.username)
    # `update()` sender ingen `post_save`, så tallet økes her — ellers ville
    # kortene i KO stått uten «venter» til noe annet endret seg.
    oppdrag_endringer.oppdrag_endret(alle=True)
    _meld_hentet(bedt, request.user, gruppe=gruppe, antall_totalt=len(kandidater))
    return JsonResponse({'status': 'ok', 'data': {
        'bedt': [e.pk for e in bedt], 'hoppet_over': len(kandidater) - len(bedt),
        'bedt_at': naa.isoformat()}}, status=202)


def _meld_hentet(enheter, bruker, *, gruppe, antall_totalt=None) -> None:
    """Signalet KO logger på. `send_robust`: en loggfeil er aldri en feil for KO-operatøren."""
    for mottaker, svar in posisjon.posisjon_hentet.send_robust(
            sender=None, enheter=enheter, bruker=bruker, gruppe=gruppe,
            antall_totalt=antall_totalt):
        if isinstance(svar, Exception):
            logger.warning('Hent posisjon: mottakeren %s feilet (%s)',
                           getattr(mottaker, '__name__', mottaker), type(svar).__name__)
