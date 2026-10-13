"""Programmet — konsertplanleggeren (23. sep. 2026).

Delt ut av `ko/views.py` i G2 (13. okt. 2026). Reglene står i `ko/program.py`.
Tidene leses med tavlas `_tavle_tid` og dekningen gates av `_tavle_gate`: én
regel, ikke to.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import modul_kreves
from core.jsonkropp import json_body, json_feil
from core.ratelimit import rate_limit
from core.vakt import hent_aktiv_vakt

from . import services
from .views import _heltall_eller_none, _kan_lede_ko
from .views_tavle import _tavle_gate, _tavle_tid


# ── Programmet (tavleplanleggeren, steg 2 — 23. sep. 2026) ───────────────────
#
# **Å lese er `les` i KO, å skrive er KO-lederens** (André: «KO-leder»), både
# før og under vakta. Behovet peker på vaktlistas ressursgrupper, men bærer
# bare navnene deres — ingen vaktlistedata om personer — så gaten er KOs egen.

def _program_tider(data):
    return _tavle_tid(data.get('fra'), 'Fra'), _tavle_tid(data.get('til'), 'Til')


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='ko:program', rate='60/m', method='POST')
def program_view(request):
    """Programmet for aktiv vakt, og valgene skjemaet trenger. POST lager en
    ny konsert."""
    from . import program

    vakt = hent_aktiv_vakt()
    if request.method == 'POST':
        if not _kan_lede_ko(request):
            return json_feil('Å legge programmet er KO-lederens (skriv_leder i KO).', 403)
        data = json_body(request)
        try:
            fra, til = _program_tider(data)
            post = program.lagre_post(vakt, data, fra=fra, til=til, bruker=request.user)
        except services.Ugyldig as e:
            return json_feil(str(e))
        return JsonResponse({'status': 'ok', 'data': program.til_dict(post)})
    return JsonResponse({'status': 'ok', 'data': program.program_data(vakt)})


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
@rate_limit(group='ko:program_post', rate='60/m', method=['PUT', 'DELETE'])
def program_post_view(request, pk):
    """Endre eller slett en konsert i aktiv vakt."""
    from . import program
    from .models import Programpost

    if not _kan_lede_ko(request):
        return json_feil('Å legge programmet er KO-lederens (skriv_leder i KO).', 403)
    post = Programpost.objects.filter(pk=pk, vakt=hent_aktiv_vakt()).first()
    if post is None:
        return json_feil('Ukjent konsert.', 404)
    if request.method == 'DELETE':
        program.slett_post(post, bruker=request.user)
        return JsonResponse({'status': 'ok'})
    data = json_body(request)
    try:
        fra, til = _program_tider(data)
        post = program.lagre_post(post.vakt, data, fra=fra, til=til, bruker=request.user, post=post)
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok', 'data': program.til_dict(post)})


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:program_dekning', rate='60/m', method='GET')
def program_dekning_view(request):
    """Dekningsstripa i planleggeren (steg 4): på vakt per ressursgruppe, time
    for time, i døgnet `?dogn=YYYY-MM-DD`. **Tallene er vaktlistas**, så
    gaten er vaktlistas også — som tavla."""
    from . import program

    stengt = _tavle_gate(request)
    if stengt:
        return stengt
    # **Et vindu, ikke et døgn** (23. sep. 2026): konsertplanleggeren følger
    # tavlas tidsvindu, og det kan stå over to døgn. `?fra=` er starten på den
    # første timen, `?timer=` hvor mange. `?dogn=` står igjen for et døgn.
    antall = _heltall_eller_none(request.GET.get('timer'))
    antall = 24 if antall is None else antall
    if not 1 <= antall <= program.MAKS_DEKNINGSTIMER:
        return json_feil(f'Oppgi mellom 1 og {program.MAKS_DEKNINGSTIMER} timer.')
    if request.GET.get('fra'):
        try:
            start = _tavle_tid(request.GET.get('fra'), 'Fra')
        except services.Ugyldig as e:
            return json_feil(str(e))
    else:
        start = program.dogn_start(request.GET.get('dogn', ''))
        if start is None:
            return json_feil('Oppgi vinduet som ?fra=<tidspunkt>&timer=N, eller døgnet som ?dogn=ÅÅÅÅ-MM-DD.')
    return JsonResponse({'status': 'ok', 'data': {
        'fra': start.isoformat(),
        'timer': program.paa_vakt_per_time(start, hent_aktiv_vakt(), antall)}})


# ── Plan mot faktisk og kopiering (steg 5) ──────────────────────────────────
#
# **Aktiv vakt er `les`; tidligere vakter er KO-lederens** — samme skille som
# loggen (dataminimering). Programmet selv bærer ingen personopplysninger,
# men tabellen ved siden av teller oppdrag, og regelen skal være én.

def _program_vakt(request):
    from core.models import Vakt
    aktiv = hent_aktiv_vakt()
    raa = request.GET.get('vakt')
    if not raa:
        return aktiv, None
    vakt = Vakt.objects.filter(pk=_heltall_eller_none(raa)).first()
    if vakt is None:
        return None, json_feil('Ukjent vakt.', 404)
    if vakt.pk != aktiv.pk and not _kan_lede_ko(request):
        return None, json_feil('Tidligere vakter er KO-lederens (skriv_leder i KO).', 403)
    return vakt, None


@never_cache
@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['GET'])
@rate_limit(group='ko:program_etterpaa', rate='60/m', method='GET')
def program_etterpaa_view(request):
    """Plan mot faktisk per konsert, og historikken, for en vakt."""
    from core.models import Vakt

    from . import program
    from .models import Programpost

    vakt, feil = _program_vakt(request)
    if feil:
        return feil
    data = {'vakt': {'id': vakt.pk, 'navn': vakt.navn},
            'poster': program.plan_mot_faktisk(vakt),
            'endringer': program.endringer(vakt),
            'vakter': []}
    if _kan_lede_ko(request):
        med_program = set(Programpost.objects.values_list('vakt_id', flat=True).distinct())
        data['vakter'] = [{'id': v.pk, 'navn': v.navn, 'aar': v.year}
                          for v in Vakt.objects.filter(pk__in=med_program | {vakt.pk}).order_by('-startet')]
    return JsonResponse({'status': 'ok', 'data': data})


@modul_kreves('ko', 'les', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='ko:program_kopier', rate='10/m', method='POST')
def program_kopier_view(request):
    """«Kopier programmet» fra en tidligere vakt inn i aktiv vakt.

    **Har aktiv vakt alt et program, er det en 409 med antallet** — kopien
    legges til, den erstatter ingenting, og to programmer oppå hverandre er
    ikke noe man skal få ved et feilklikk. `{"confirm": true}` går gjennom.
    """
    from datetime import date

    from core.models import Vakt

    from . import program
    from .models import Programpost

    if not _kan_lede_ko(request):
        return json_feil('Å legge programmet er KO-lederens (skriv_leder i KO).', 403)
    data = json_body(request)
    aktiv = hent_aktiv_vakt()
    kilde = Vakt.objects.filter(pk=_heltall_eller_none(data.get('fra_vakt_id'))).first()
    if kilde is None or kilde.pk == aktiv.pk:
        return json_feil('Velg en annen vakt å kopiere fra.')
    try:
        forste = date.fromisoformat(str(data.get('forste_dogn') or ''))
    except ValueError:
        return json_feil('Oppgi første konsertdøgn som ÅÅÅÅ-MM-DD.')
    har = Programpost.objects.filter(vakt=aktiv).count()
    if har and not data.get('confirm'):
        return JsonResponse({'status': 'error', 'message':
                             f'Aktiv vakt har alt {har} i programmet. Kopien legges til ved siden av, ingenting erstattes. Fortsette?',
                             'antall': har}, status=409)
    try:
        svar = program.kopier_program(kilde, aktiv, forste_dogn=forste, bruker=request.user)
    except services.Ugyldig as e:
        return json_feil(str(e))
    return JsonResponse({'status': 'ok', 'data': svar})

