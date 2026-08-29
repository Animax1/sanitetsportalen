"""Sentralbordet og oppdrags-API-et.

Fase 3 av `docs/BESLUTNING_OPPDRAGSMODULEN.md`. Enhetsskjermen og de smale
stemplingsendepunktene kommer i fase 4; alt her er sentralbordets side.

**Hvert view er dekorert.** `patients/tests_modul_dekorator.py` går gjennom
`urlpatterns` og håndhever det — risikoen ved dekoratør framfor middleware er
en glemt dekoratør, og en manuell gjennomgang holder bare til neste endepunkt.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import er_global_admin, har_tilgang, modul_kreves
from core.ratelimit import rate_limit
from patients.services import get_active_year

from . import choices, services
from .choices import validate_oppdrag_choice_fields
from .models import Enhet, Lokasjon, Oppdrag
from .views_common import (
    bytte_til_dict, er_enhetskonto, etag_for, json_body, melding_til_dict,
    oppdrag_til_dict,
)


# ── Siden ────────────────────────────────────────────────────────────────────

@modul_kreves('oppdrag', 'les')
@require_http_methods(['GET'])
def index_view(request):
    """Én URL, to grensesnitt.

    **Skjermen velges av om kontoen er knyttet til en `Enhet`, ikke av
    nivået.** Se `views_common.er_enhetskonto` for hvorfor.

    Enhetsskjermen finnes ikke ennå (fase 4). Fram til da får en enhetskonto
    en mellomtilstand som sier det rett ut, i stedet for sentralbordet — det
    ville vist henne alle oppdrag i vakta, som er nettopp det hun ikke skal se.
    """
    if er_enhetskonto(request.user):
        return render(request, 'oppdrag/enhet_kommer.html', {
            'enhet': request.user.enhet,
        })

    return render(request, 'oppdrag/sentral.html', {
        'kan_skrive': har_tilgang(request.user, 'oppdrag', 'skriv_full'),
        'problemstillinger': choices.PROBLEMSTILLING,
        'hastegrader': choices.HASTEGRAD,
    })


# ── Enheter ──────────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET'])
def enheter_view(request):
    """Enhetslista med **utledet** status.

    Enheten har ingen statuskolonne. `Ledig (2 venter)` regnes ut fra
    oppdragene hver gang — se `services.enhet_status` for hvorfor det ikke
    lagres.
    """
    year = get_active_year()
    enheter = list(Enhet.objects.filter(er_aktiv=True).order_by('navn'))
    data = [
        {
            'id': e.pk,
            'navn': e.navn,
            'status': info['status'],
            'status_navn': info['status_navn'],
            'antall_ventende': info['antall_ventende'],
            'aktivt_oppdrag_id': (
                info['aktivt_oppdrag'].pk if info['aktivt_oppdrag'] else None),
        }
        for e, info in ((e, services.enhet_status(e, year)) for e in enheter)
    ]

    etag = etag_for([
        (r['id'], r['status'], r['antall_ventende'], r['aktivt_oppdrag_id'])
        for r in data
    ])
    if request.META.get('HTTP_IF_NONE_MATCH') == etag:
        svar = HttpResponseNotModified()
        svar['ETag'] = etag
        return svar

    svar = JsonResponse({'status': 'ok', 'data': data})
    svar['ETag'] = etag
    return svar


# ── Lokasjoner ───────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
def lokasjoner_view(request):
    """Liste (alle med `les`), eller opprett (kun global admin).

    Lokasjonene er arrangementsdata og hører til modulen, på samme måte som
    navneregistrene hører til pasientmodulen. Admin-gaten ligger inne i viewet
    fordi lesing og skriving har ulike krav — modulgaten dekker begge.
    """
    if request.method == 'GET':
        rader = list(Lokasjon.objects.all())
        data = [
            {'id': r.pk, 'navn': r.navn, 'er_aktiv': r.er_aktiv,
             'rekkefolge': r.rekkefolge}
            for r in rader
        ]
        etag = etag_for([(r['id'], r['navn'], r['er_aktiv'], r['rekkefolge'])
                         for r in data])
        if request.META.get('HTTP_IF_NONE_MATCH') == etag:
            svar = HttpResponseNotModified()
            svar['ETag'] = etag
            return svar
        svar = JsonResponse({'status': 'ok', 'data': data})
        svar['ETag'] = etag
        return svar

    if not er_global_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    navn = (json_body(request).get('navn') or '').strip()
    if not navn:
        return JsonResponse(
            {'status': 'error', 'message': 'Navn kan ikke være tomt.'}, status=400)
    if Lokasjon.objects.filter(navn=navn).exists():
        return JsonResponse(
            {'status': 'error', 'message': f'«{navn}» finnes allerede.'}, status=400)

    lok = Lokasjon.objects.create(navn=navn)
    return JsonResponse({'status': 'ok', 'data': {
        'id': lok.pk, 'navn': lok.navn, 'er_aktiv': lok.er_aktiv,
        'rekkefolge': lok.rekkefolge}})


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['PUT', 'DELETE'])
def lokasjon_detalj_view(request, pk):
    """Endre navn/aktiv (PUT) eller deaktiver (DELETE). Kun global admin.

    **DELETE deaktiverer, den sletter ikke.** FK-en fra `Oppdrag` er `PROTECT`,
    så en lokasjon i bruk kan ikke forsvinne uten å ta historikken med seg.
    Å la knappen hete «slett» og gjøre noe annet ville vært verre enn å la
    være — den heter «deaktiver» i grensesnittet.
    """
    if not er_global_admin(request.user):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    try:
        lok = Lokasjon.objects.get(pk=pk)
    except Lokasjon.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Lokasjon ikke funnet'}, status=404)

    if request.method == 'DELETE':
        lok.er_aktiv = False
        lok.save(update_fields=['er_aktiv', 'updated_at'])
        return JsonResponse({'status': 'ok'})

    data = json_body(request)
    if 'navn' in data:
        navn = (data.get('navn') or '').strip()
        if not navn:
            return JsonResponse(
                {'status': 'error', 'message': 'Navn kan ikke være tomt.'}, status=400)
        if Lokasjon.objects.filter(navn=navn).exclude(pk=lok.pk).exists():
            return JsonResponse(
                {'status': 'error', 'message': f'«{navn}» finnes allerede.'}, status=400)
        lok.navn = navn
    if 'er_aktiv' in data:
        lok.er_aktiv = bool(data['er_aktiv'])
    if 'rekkefolge' in data:
        try:
            lok.rekkefolge = int(data['rekkefolge'])
        except (TypeError, ValueError):
            return JsonResponse(
                {'status': 'error', 'message': 'Rekkefølge må være et tall.'}, status=400)
    lok.save()
    return JsonResponse({'status': 'ok', 'data': {
        'id': lok.pk, 'navn': lok.navn, 'er_aktiv': lok.er_aktiv,
        'rekkefolge': lok.rekkefolge}})


# ── Oppdrag ──────────────────────────────────────────────────────────────────

@never_cache
@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'POST'])
@rate_limit(group='oppdrag:create', rate='60/m', method='POST')
def oppdrag_liste_view(request):
    """Liste oppdrag i aktiv vakt (GET), eller opprett (POST).

    **Enhetskontoer får kun egne rader.** Modulgaten sier at kontoen kan lese
    modulen; hvilke *rader* den kan lese er en objektsjekk dekoratoren ikke
    gjør, og den ligger her.
    """
    year = get_active_year()

    if request.method == 'GET':
        if er_enhetskonto(request.user):
            oppdrag = services.synlige_for_enhet(request.user.enhet, year)
            data = [oppdrag_til_dict(o, for_enhet=True) for o in oppdrag]
        else:
            qs = (Oppdrag.objects.filter(year=year)
                  .select_related('enhet', 'lokasjon').order_by('-created_at'))
            data = [oppdrag_til_dict(o) for o in qs]

        etag = etag_for([(r['id'], r['status'], r['enhet_id']) for r in data])
        if request.META.get('HTTP_IF_NONE_MATCH') == etag:
            svar = HttpResponseNotModified()
            svar['ETag'] = etag
            return svar
        svar = JsonResponse({'status': 'ok', 'data': data})
        svar['ETag'] = etag
        return svar

    # POST — kun sentralbordet oppretter oppdrag.
    if not har_tilgang(request.user, 'oppdrag', 'skriv_full'):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    data = json_body(request)
    try:
        validate_oppdrag_choice_fields(data)
    except ValidationError as feil:
        return JsonResponse(
            {'status': 'error', 'message': '; '.join(feil.messages)}, status=400)

    try:
        enhet = Enhet.objects.get(pk=data.get('enhet_id'), er_aktiv=True)
    except (Enhet.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error', 'message': 'Ukjent eller inaktiv enhet.'}, status=400)
    try:
        lokasjon = Lokasjon.objects.get(pk=data.get('lokasjon_id'), er_aktiv=True)
    except (Lokasjon.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error', 'message': 'Ukjent eller inaktiv lokasjon.'}, status=400)

    oppdrag = Oppdrag.objects.create(
        year=year,
        enhet=enhet,
        problemstilling=data['problemstilling'],
        hastegrad=data['hastegrad'],
        lokasjon=lokasjon,
        fritekst=(data.get('fritekst') or '').strip(),
        opprettet_av=request.user,
    )
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@modul_kreves('oppdrag', 'les', svar='json')
@require_http_methods(['GET', 'PUT'])
@rate_limit(group='oppdrag:detalj-skriv', rate='120/m', method='PUT')
def oppdrag_detalj_view(request, pk):
    """Hent ett oppdrag med tidslinje (GET), eller rediger felt (PUT).

    Tidslinjen er unionen av statusmeldinger og enhetsbytter. De to er skilt i
    databasen fordi et bytte ikke er en status og statistikken måler statusene;
    å slå dem sammen her er en visningsjobb.

    Statusmeldingene er de **gjeldende** — en korreksjon overstyrer raden den
    peker på. Den fulle historikken sendes med som `historikk`, slik at
    tidslinjen kan vise rettingen uten at klienten må regne den ut.
    """
    try:
        oppdrag = (Oppdrag.objects.select_related('enhet', 'lokasjon')
                   .get(pk=pk, year=get_active_year()))
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    if er_enhetskonto(request.user) and oppdrag.enhet_id != request.user.enhet.pk:
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    if request.method == 'GET':
        from .models import Statusmelding
        gjeldende = Statusmelding.objects.gjeldende(oppdrag)
        alle = Statusmelding.objects.filter(oppdrag=oppdrag).order_by('created_at')
        return JsonResponse({'status': 'ok', 'data': {
            **oppdrag_til_dict(oppdrag, for_enhet=er_enhetskonto(request.user)),
            'statusmeldinger': [melding_til_dict(m) for m in gjeldende],
            'historikk': [melding_til_dict(m) for m in alle],
            'enhetsbytter': [bytte_til_dict(b) for b in oppdrag.enhetsbytter.all()],
        }})

    if not har_tilgang(request.user, 'oppdrag', 'skriv_full'):
        return JsonResponse({'status': 'error', 'message': 'Ingen tilgang'}, status=403)

    data = json_body(request)
    try:
        validate_oppdrag_choice_fields(data)
    except ValidationError as feil:
        return JsonResponse(
            {'status': 'error', 'message': '; '.join(feil.messages)}, status=400)

    if 'problemstilling' in data:
        oppdrag.problemstilling = data['problemstilling']
    if 'hastegrad' in data:
        oppdrag.hastegrad = data['hastegrad']
    if 'fritekst' in data:
        oppdrag.fritekst = (data.get('fritekst') or '').strip()
    if 'lokasjon_id' in data:
        try:
            oppdrag.lokasjon = Lokasjon.objects.get(pk=data['lokasjon_id'])
        except (Lokasjon.DoesNotExist, ValueError, TypeError):
            return JsonResponse(
                {'status': 'error', 'message': 'Ukjent lokasjon.'}, status=400)
    oppdrag.save()
    return JsonResponse({'status': 'ok', 'data': oppdrag_til_dict(oppdrag)})


@modul_kreves('oppdrag', 'skriv_full', svar='json')
@require_http_methods(['POST'])
@rate_limit(group='oppdrag:flytt', rate='60/m', method='POST')
def flytt_view(request, pk):
    """Flytt oppdraget til en annen enhet, og skriv det i oppdragets logg.

    Statusen står. Meldingene den første enheten rakk å sende blir stående med
    `meldt_av` intakt: de skjedde.
    """
    try:
        oppdrag = Oppdrag.objects.get(pk=pk, year=get_active_year())
    except Oppdrag.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdrag ikke funnet'}, status=404)

    try:
        ny_enhet = Enhet.objects.get(pk=json_body(request).get('enhet_id'), er_aktiv=True)
    except (Enhet.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {'status': 'error', 'message': 'Ukjent eller inaktiv enhet.'}, status=400)

    bytte = services.flytt_til_enhet(oppdrag, ny_enhet, bruker=request.user)
    if bytte is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Oppdraget står allerede på denne enheten.'},
            status=400)
    return JsonResponse({'status': 'ok', 'data': bytte_til_dict(bytte)})
