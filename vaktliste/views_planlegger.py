"""Planleggeren, «Del ut», belastningen med grensene, og pausene.

Delt ut av `vaktliste/views.py` i G2 (14. okt. 2026) — tilgangstersklene og
kartet over filene står i docstringen der.
"""
from __future__ import annotations

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.jsonkropp import json_body, json_feil
from core.auth_decorators import modul_kreves
from core.ratelimit import rate_limit

from . import belastning, pauser, planlegger, services
from .models import Belastningsgrenser, Korps, Pause, Ressurs, Vaktliste
from .views import _nektet, _int, _tid


# ── Planleggeren (15. sep. 2026) ─────────────────────────────────────────────


def _planleggerlinjer(data):
    """Oppsettet fra klienten, med tidene lest og validert.

    Formen er **ressurs → vinduer**, ikke en flat liste linjer: Sola 56 har to
    adskilte 12-timersvakter, og var linja enheten og ikke ressursen, ville
    hun blitt til to ulike biler.
    """
    linjer = data.get('linjer')
    if not isinstance(linjer, list):
        raise planlegger.Planleggerfeil('Oppsettet mangler.')
    ut = []
    for raa in linjer:
        if not isinstance(raa, dict):
            raise planlegger.Planleggerfeil('Ugyldig linje i oppsettet.')
        vinduer = raa.get('vinduer')
        if not isinstance(vinduer, list) or not vinduer:
            raise planlegger.Planleggerfeil(
                'Hver enhet må ha minst ett skiftvindu.')
        lest = []
        for vindu in vinduer:
            if not isinstance(vindu, dict):
                raise planlegger.Planleggerfeil('Ugyldig skiftvindu.')
            fra, til = _tid(vindu.get('fra')), _tid(vindu.get('til'))
            if fra is None or til is None:
                raise planlegger.Planleggerfeil(
                    'Skiftvinduet mangler fra- eller til-tidspunkt.')
            # **Ett vindu er ett skift**, og **plassene hører til vinduet**
            # (15. sep. 2026): samleplassen kan ha seks 14–22 og to 22–06, og
            # det er én ressurs med to vinduer — ikke to samleplasser. Feltet
            # `skiftlengde`, som delte vinduet i bolker, er fjernet.
            # Rå verdi videre: `planlegger._linjens_skift()` eier regelen, og
            # et `_int(...) or 1` her ville gjort et eksplisitt `0` til 1 før
            # den fikk se det.
            lest.append({'fra': fra, 'til': til,
                         'plasser': vindu.get('plasser')})
        ut.append({
            # **`ressurs_id` gjør linja til en redigering** (15. sep. 2026):
            # planleggeren leser oppsettet tilbake fra vaktlista, så et andre
            # trykk retter det som ble laget i stedet for å lage det på nytt.
            # Gruppa og navnet følger da ressursen — se `planlegger._planlegg`.
            'ressurs_id': _int(raa.get('ressurs_id')),
            'gruppe_id': _int(raa.get('gruppe_id')),
            'antall': _int(raa.get('antall')) or 1,
            'vinduer': lest,
            # Pauseregelen, rå: `pauser.les_regel()` eier tolkningen, som
            # `plasser` over.
            'pause_etter_min': raa.get('pause_etter_min'),
            'pause_min': raa.get('pause_min'),
            'pause_forskyv': raa.get('pause_forskyv', True) is not False,
        })
    return ut


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:generer', rate='30/m', method='POST')
def generer_view(request, pk):
    """Lag grunnlaget for vaktlista: ressursene og de tomme plassene.

    **`skriv_leder` og global admin** (André, 15. sep. 2026: «Den skal bare
    admin og leder ha tilgang til. For den genererer grunnlaget på alt»). Det
    er samme terskel som resten av vaktas rammer — spennet, taket — og av
    samme grunn: dette gjelder hele lista, ikke ett korps' del av den.

    **`?forhaandsvis=1` skriver ingenting.** Klienten viser hva oppsettet vil
    lage før knappen trykkes, og svaret regnes av nøyaktig samme kode. En
    generator man må kontrollere etterpå er ikke raskere enn å skrive radene.

    **En linje med `ressurs_id` retter en ressurs som alt står** (André, 15.
    sep. 2026: «når en har lagt grunnlag og vil redigere så er det ikke lenger
    i planlegger»). Bare kladden på de ressursene oppsettet nevner røres —
    plasser som er delt ut, til ett korps eller til alle, og alle bemannede,
    står. Se `generer_grunnlag`.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    try:
        vl = Vaktliste.objects.select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)

    data = json_body(request)
    try:
        linjer = _planleggerlinjer(data)
        if data.get('forhaandsvis'):
            svar = planlegger.forhaandsvis_grunnlag(vl, linjer)
        else:
            svar = planlegger.generer_grunnlag(vl, linjer)
    except planlegger.Planleggerfeil as feil:
        return json_feil(str(feil))
    return JsonResponse({'status': 'ok', 'data': svar})


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:del-ut', rate='60/m', method='POST')
def del_ut_view(request, pk):
    """**«Del ut»** (pulje 4, 30. sep. 2026): gi kladden på én eller flere
    enheter til et korps eller til alle.

    Kroppen er `{"fordeling": [{"ressurs_id": 3, "korps_id": 2},
    {"ressurs_id": 4, "alle": true}]}`. Vinduet på enhetskortet sender én rad,
    planleggerens sluttsteg sender alle — **samme endepunkt**, så regelen for
    hva som deles ut finnes ett sted (`services.del_ut`).

    **`kan_sette_opp_skift`**, som nedtrekket på plassen: å dele ut en hel
    enhet og å dele ut én plass er samme handling (André: «de kan begge ha
    likt»). **Alt eller ingenting**: en ukjent enhet eller et ukjent korps
    stopper hele fordelingen før noe er skrevet, og skrivingen står i én
    transaksjon — en halvt utdelt vakt er verre å rydde enn en som ikke ble det.
    """
    if not services.kan_sette_opp_skift(request.user):
        return _nektet('Enhetene deles ut av den som setter opp skiftene.')
    try:
        vl = Vaktliste.objects.get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)

    rader = json_body(request).get('fordeling')
    if not isinstance(rader, list) or not rader:
        return json_feil('Ingenting å dele ut.')
    ressurser = {r.pk: r for r in vl.ressurser.all()}
    plan = []
    for rad in rader:
        if not isinstance(rad, dict):
            return json_feil('Ugyldig fordeling.')
        ressurs = ressurser.get(_int(rad.get('ressurs_id')))
        if ressurs is None:
            return json_feil('Enheten finnes ikke på denne vaktlisten.')
        alle = rad.get('alle') is True
        korps_id = None if alle else _int(rad.get('korps_id'))
        if not alle and (korps_id is None
                         or not Korps.objects.filter(pk=korps_id).exists()):
            return json_feil(f'Velg hvem som skal få «{ressurs.navn}».')
        plan.append((ressurs, korps_id, alle))

    with transaction.atomic():
        delt_ut = sum(services.del_ut(r, korps_id=k, alle=a) for r, k, a in plan)
    return JsonResponse({'status': 'ok', 'data': {'delt_ut': delt_ut}})


# ── Planleggingstall (fase 5) ────────────────────────────────────────────────

@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['GET'])
def belastning_view(request, pk):
    """Timer, skift og hvile per person — belastningen før vakta.

    **`les` ser tallene.** De er lista, regnet sammen: hvem som står oppført
    hvor mange timer er ikke en annen opplysning enn selve vaktlista, og en
    korps-fører som planlegger sine egne folk trenger nettopp dette for å se
    at hun er i ferd med å slite dem ut.

    **Regnestykket ligger i `services`,** ikke her — det er ikke et view som
    skal kunne svare på hva «korteste hvile» betyr.
    """
    try:
        vl = Vaktliste.objects.select_related('vakt').get(pk=pk)
    except Vaktliste.DoesNotExist:
        return json_feil('Vaktliste ikke funnet', status=404)

    grenser = Belastningsgrenser.hent()
    # `?korps=<id>` er korpsvelgeren for den som ser alle (11. sep. 2026).
    # Bare for henne: korps-brukeren er alt avgrenset av badgen, og et
    # parameter som kunne flytte den avgrensningen ville vært en dør.
    korps_id = (_int(request.GET.get('korps'))
                if services.ser_alle_korps(request.user) else None)
    rader = belastning.belastning_per_person(
        vl, grenser, user=request.user, korps_id=korps_id)
    # **Budsjettallene følger med her, uten et eget kall.** Fanen henter
    # allerede dette svaret, og to runder til serveren for tall som tegnes
    # ved siden av hverandre er én for mye.
    #
    # **Men bare til den som ser alle korps** (15. sep. 2026). Tallene er
    # hele vaktas, fordi taket er det — og for en `les` med badge ville de
    # vært et aggregat over skift hun ikke får se. Det er samme regel som
    # statistikkmodulen bruker: aggregater gir avledet innsyn, og skal gates
    # der dataene bor.
    planlegging = (belastning.planleggingstall(vl)
                   if services.ser_alle_korps(request.user) else None)
    return JsonResponse({'status': 'ok', 'data': {
        'personer': rader,
        'sammendrag': belastning.belastning_sammendrag(
            vl, rader, user=request.user, korps_id=korps_id),
        'planlegging': planlegging,
        'kan_sette_tak': services.kan_lede(request.user),
        'grenser': {
            'maks_skift_timer': grenser.maks_skift_timer,
            'min_hvile_timer': grenser.min_hvile_timer,
        },
    }})


@never_cache
@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT'])
@rate_limit(group='vaktliste:grenser', rate='30/m', method='PUT')
def grenser_view(request):
    """Sett grensene varslene måler mot. `skriv_leder`.

    **Organisasjonens regler, ikke portalens** (§8b) — derfor er de data og
    ikke tall i en `if`. Og derfor er de `skriv_leder`: å flytte grensa
    endrer hva *alle* vaktlister varsler om, og det er en beslutning om
    hvordan organisasjonen bemanner, ikke om hvem som står på bilen i kveld.

    Grensene sperrer ingenting. Settes de urimelig høyt, forsvinner varslene —
    og det er en beslutning noen har tatt, ikke en feil portalen skal hindre.
    """
    if not services.kan_lede(request.user):
        return _nektet()

    data = json_body(request)
    grenser = Belastningsgrenser.hent()
    for felt in ('maks_skift_timer', 'min_hvile_timer'):
        if felt not in data:
            continue
        verdi = _int(data[felt])
        if verdi is None or not 1 <= verdi <= 168:
            return json_feil('Grensene oppgis i hele timer, mellom 1 og 168 '
                         '(en uke).')
        setattr(grenser, felt, verdi)
    grenser.save()

    return JsonResponse({'status': 'ok', 'data': {
        'maks_skift_timer': grenser.maks_skift_timer,
        'min_hvile_timer': grenser.min_hvile_timer,
    }})


# ── Pauser (23. sep. 2026) ──────────────────────────────────────────────────

def _pausetider(data):
    return _tid(data.get('fra')), _tid(data.get('til'))


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='vaktliste:pauser', rate='120/m', method='POST')
def pauser_view(request, pk):
    """Ny pause på en ressurs. **Lederens** (André, 23. sep. 2026: «leder») —
    samme terskel som planleggeren og resten av oppsettet."""
    if not services.kan_lede(request.user):
        return _nektet('Pausene settes av den som setter opp vakten.')
    ressurs = Ressurs.objects.filter(pk=pk).first()
    if ressurs is None:
        return json_feil('Enhet ikke funnet', status=404)
    fra, til = _pausetider(json_body(request))
    try:
        pause = pauser.lagre(ressurs, fra, til)
    except pauser.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok', 'data': pauser.til_dict(pause)}, status=201)


@modul_kreves('vaktliste', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='vaktliste:pause-skriv', rate='120/m', method=['PUT', 'DELETE'])
def pause_detalj_view(request, pk):
    """Flytt eller fjern en pause. Lederens, som opprettingen."""
    if not services.kan_lede(request.user):
        return _nektet('Pausene settes av den som setter opp vakten.')
    pause = Pause.objects.select_related('ressurs').filter(pk=pk).first()
    if pause is None:
        return json_feil('Pausen finnes ikke', status=404)
    if request.method == 'DELETE':
        pauser.slett(pause)
        return JsonResponse({'status': 'ok'})
    fra, til = _pausetider(json_body(request))
    try:
        pause = pauser.lagre(pause.ressurs, fra, til, pause=pause)
    except pauser.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok', 'data': pauser.til_dict(pause)})
