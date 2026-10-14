"""Tavla (22. sep. 2026): lesingen, plasseringene, rettingen, pausene, oppsettet.

Delt ut av `ko/views.py` i G2 (13. okt. 2026). `_tavle_gate` og `_tavle_tid`
brukes også av programmet (`views_program.py`) — retningen er program → tavle,
aldri omvendt.
"""
from __future__ import annotations

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import har_tilgang, modul_kreves
from core.jsonkropp import json_body, json_feil
from core.ratelimit import rate_limit
from core.sortering import Norsk
from core.vakt import hent_aktiv_vakt

from . import services
from .views import _heltall_eller_none, _kan_lede_ko


# ── Tavla (22. sep. 2026) ─────────────────────────────────────────────────────
#
# **Tavla viser vaktlistas ressurser, så gaten er vaktlistas også** — `les` i
# vaktlista, som ressursoversikten og besetningen. Bilene og oppdragene på dem
# tas med bare for den som ser oppdragene: KO *viser* modulenes data, og hvem
# som får se dem er modulens sak (komposisjonsregelen, rollemodellen §5).

def _tavle_gate(request):
    if not har_tilgang(request.user, 'vaktliste', 'les'):
        return json_feil('Tavlen viser vaktlistens ressurser, og krever lesetilgang i vaktlisten.', 403)
    return None


def _tavle_ressurs(request, data):
    """Ressursen i kroppen — og **en bil bare med lesetilgang i
    oppdragsmodulen**, samme regel som `tavle_view` bruker for å vise den. En
    bil man ikke får se, finnes ikke: 404, ikke 403."""
    from vaktliste.models import Ressurs
    try:
        ressurs = Ressurs.objects.get(pk=int(data.get('ressurs_id')))
    except (Ressurs.DoesNotExist, TypeError, ValueError):
        return None
    if ressurs.enhet_id is not None and not har_tilgang(request.user, 'oppdrag', 'les'):
        return None
    return ressurs


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:tavle', rate='240/m', method='GET')
def tavle_view(request):
    """Alt tavla trenger, i ett svar. Polles som loggen."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    data = tavle.tavle_data(hent_aktiv_vakt(),
                            med_biler=har_tilgang(request.user, 'oppdrag', 'les'))
    return JsonResponse({'status': 'ok', 'data': data})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_plasser', rate='120/m', method='POST')
def tavle_plasser_view(request):
    """Sett en ledig ressurs på en lokasjon, eller i pause, fra nå."""
    from oppdrag.models import Lokasjon

    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    data = json_body(request)
    ressurs = _tavle_ressurs(request, data)
    if ressurs is None:
        return json_feil('Ukjent enhet.', 404)
    lokasjon = None
    if not data.get('pause'):
        try:
            lokasjon = Lokasjon.objects.get(pk=int(data.get('lokasjon_id')))
        except (Lokasjon.DoesNotExist, TypeError, ValueError):
            return json_feil('Ukjent lokasjon.', 404)
    try:
        p = tavle.plasser(hent_aktiv_vakt(), ressurs, bruker=request.user,
                          lokasjon=lokasjon, pause=bool(data.get('pause')))
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok', 'data': {'id': p.pk}})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_uten_plass', rate='120/m', method='POST')
def tavle_uten_plass_view(request):
    """Ta ressursen av tavla — dit man drar den når den ikke står noe sted."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    ressurs = _tavle_ressurs(request, json_body(request))
    if ressurs is None:
        return json_feil('Ukjent enhet.', 404)
    try:
        tavle.avslutt(hent_aktiv_vakt(), ressurs, bruker=request.user)
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok'})


# ── Tavla, steg 2: retting, pauser, oppsett ──────────────────────────────────

def _tavle_tid(raa, hva):
    """Et tidspunkt fra tavlas skjemaer. **Ugyldig er en 400 her**, ikke «nå»
    som i loggen: en retting som stille ble til nå, har skrevet om historikken
    til noe ingen ba om."""
    t = parse_datetime(raa) if isinstance(raa, str) and raa else None
    if t is None or timezone.is_naive(t):
        raise services.Ugyldig(f'«{hva}» mangler eller er ikke et tidspunkt.')
    return t


def _bil_skjult(request, ressurs_id) -> bool:
    """En bil man ikke får se uten oppdragstilgang (som `_tavle_ressurs`)."""
    from vaktliste.models import Ressurs
    if ressurs_id is None or har_tilgang(request.user, 'oppdrag', 'les'):
        return False
    return Ressurs.objects.filter(pk=ressurs_id, enhet__isnull=False).exists()


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='ko:tavle_rett', rate='60/m', method=['PUT', 'DELETE'])
def tavle_plassering_view(request, pk):
    """Rett tidene på en plassering, sett den planlagte slutten, eller fjern
    den (skisse 3; planlagt slutt 23. sep. 2026)."""
    from . import tavle
    from .models import Tavleplassering

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    p = Tavleplassering.objects.filter(pk=pk, vakt=hent_aktiv_vakt()).first()
    if p is None or _bil_skjult(request, p.ressurs_id):
        return json_feil('Ukjent plassering.', 404)
    data = json_body(request)
    try:
        if request.method == 'DELETE':
            tavle.fjern(p, bruker=request.user)
            return JsonResponse({'status': 'ok'})
        if 'fra' not in data and 'planlagt_til' not in data and 'folger_id' not in data:
            raise services.Ugyldig('Ingenting å endre.')
        # Tidene og den planlagte slutten i ett: feiler den ene, er heller
        # ikke den andre lagret — skjemaet sendte dem som én ting.
        with transaction.atomic():
            if 'fra' in data:
                fra = _tavle_tid(data.get('fra'), 'Fra')
                til = _tavle_tid(data.get('til'), 'Til') if p.til is not None else None
                tavle.rett(p, fra=fra, til=til, bruker=request.user)
            if data.get('folger_id'):
                # «Følger konserten» (steg 2) går foran en egen tid.
                from . import program
                from .models import Programpost
                post = Programpost.objects.filter(pk=_heltall_eller_none(data.get('folger_id'))).first()
                if post is None:
                    raise services.Ugyldig('Ukjent konsert.')
                program.folg(p, post, naa=timezone.now())
            elif 'planlagt_til' in data or 'folger_id' in data:
                # Tomt er «ingen plan»; noe annet enn et tidspunkt er en feil.
                raa = data.get('planlagt_til')
                slutt = _tavle_tid(raa, 'Planlagt slutt') if raa else None
                tavle.sett_planlagt_slutt(p, slutt)
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok'})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_pauser', rate='60/m', method='POST')
def tavle_pauser_view(request):
    """«+ Planlegg» på en rad: en pause, eller et sted (23. sep. 2026). Alle som
    fører tavla (`skriv_full`) — André: «Alle i første omgang»."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    data = json_body(request)
    ressurs = _tavle_ressurs(request, data)
    if ressurs is None:
        return json_feil('Ukjent enhet.', 404)
    # **Hvilken som helst rad** (23. sep. 2026): `lokasjon_id` er et sted,
    # uten er det Pause-raden.
    lokasjon = None
    if data.get('lokasjon_id') not in (None, ''):
        from oppdrag.models import Lokasjon
        lokasjon = Lokasjon.objects.filter(pk=_heltall_eller_none(data.get('lokasjon_id'))).first()
        if lokasjon is None:
            return json_feil('Ukjent lokasjon.', 404)
    try:
        q = tavle.planlegg_pause(hent_aktiv_vakt(), ressurs, bruker=request.user,
                                 fra=_tavle_tid(data.get('fra'), 'Fra'),
                                 til=_tavle_tid(data.get('til'), 'Til'), lokasjon=lokasjon)
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok', 'data': {'id': q.pk}})


def _tavle_pause(request, ref):
    """Pausen `ref` peker på: KOs egen (et tall), eller vaktlistas (`v<pk>`,
    23. sep. 2026). **En vaktlistepause overtas her** — den blir KOs rad i det
    KO rører den. Kalles derfor inne i `transaction.atomic()`, så en endring
    som avvises ikke etterlater en overtakelse ingen ba om."""
    from . import tavle
    from .models import PlanlagtPause

    vakt = hent_aktiv_vakt()
    ref = str(ref)
    if ref.startswith(tavle.VAKTLISTE_PREFIKS):
        from vaktliste.models import Pause
        from vaktliste.vaktdrift import vaktliste_i_bruk

        liste = vaktliste_i_bruk()
        pk = _heltall_eller_none(ref[len(tavle.VAKTLISTE_PREFIKS):])
        vp = (Pause.objects.select_related('ressurs').filter(pk=pk, ressurs__vaktliste=liste).first()
              if liste is not None and pk else None)
        if vp is None or _bil_skjult(request, vp.ressurs_id):
            return None
        q = tavle.overta_pause(vakt, vp, bruker=request.user)
    else:
        pk = _heltall_eller_none(ref)
        q = PlanlagtPause.objects.filter(pk=pk, vakt=vakt).first() if pk else None
    if q is None or q.avlyst or _bil_skjult(request, q.ressurs_id):
        return None
    return q


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='ko:tavle_pause', rate='60/m', method=['PUT', 'DELETE'])
def tavle_pause_view(request, ref):
    """Endre eller fjern en planlagt pause — KOs egen eller vaktlistas."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    data = json_body(request)
    try:
        with transaction.atomic():
            q = _tavle_pause(request, ref)
            if q is None:
                return json_feil('Ukjent pause.', 404)
            if request.method == 'DELETE':
                tavle.slett_pause(q)
                return JsonResponse({'status': 'ok'})
            tavle.planlegg_pause(q.vakt, q.ressurs, pause=q, bruker=request.user,
                                 fra=_tavle_tid(data.get('fra'), 'Fra'),
                                 til=_tavle_tid(data.get('til'), 'Til'))
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok'})


@modul_kreves('ko', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:tavle_pause_start', rate='60/m', method='POST')
def tavle_pause_start_view(request, ref):
    """«Pause nå»: KO starter den; tavla flytter ingen av seg selv. Også på
    en av vaktlistas — da overtas den i samme transaksjon."""
    from . import tavle

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    try:
        with transaction.atomic():
            q = _tavle_pause(request, ref)
            if q is None:
                return json_feil('Ukjent pause.', 404)
            tavle.start_pause(q, bruker=request.user)
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok'})


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET', 'PUT'])
@rate_limit(group='ko:tavle_oppsett', rate='30/m', method='PUT')
def tavle_oppsett_view(request):
    """KO-innstillinger, fanen «Tavla»: per lokasjon «På tavla» og «Følg
    besøk ★». Å lese er `les`; å endre er KO-lederens (`skriv_leder`), som
    resten av KO-innstillingene."""
    from oppdrag.models import Lokasjon

    from . import tavle

    if request.method == 'PUT':
        if not _kan_lede_ko(request):
            return json_feil('Å sette opp tavlen er skriv_leder i KO.', 403)
        data = json_body(request)
        try:
            with transaction.atomic():
                tavle.lagre_oppsett(skjulte_ider=data.get('skjulte'), fulgte_ider=data.get('fulgte'))
                # Rullingen (23. sep. 2026): sendes den, lagres den — samme dør.
                if 'andel_bak' in data or 'steg_min' in data:
                    tavle.lagre_rulling(andel=data.get('andel_bak', tavle.andel_bak()),
                                        steg=data.get('steg_min', tavle.steg_min()))
        except services.Ugyldig as e:
            return json_feil(str(e))
    ute, fulgt = set(tavle.skjulte()), set(tavle.fulgte())
    return JsonResponse({'status': 'ok', 'data': {
        'lokasjoner': [{
            'id': l.pk, 'navn': l.navn, 'paa_tavla': l.pk not in ute, 'fulgt': l.pk in fulgt,
        } for l in Lokasjon.objects.filter(er_aktiv=True).order_by('rekkefolge', Norsk('navn'))],
        'andel_bak': tavle.andel_bak(),
        'steg_min': tavle.steg_min(),
    }})

