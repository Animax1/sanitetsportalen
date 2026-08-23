"""Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD og nullstilling.

Skilt ut fra ``views.py`` i N13.3.
"""
import hashlib
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.auth_decorators import admin_required
from core.idempotency import bygg_nokkel, forkast, fullfor, reserver
from core.ratelimit import rate_limit

from .choices import validate_patient_choice_fields
from .models import Patient, AppSetting, Forstehjelper, Helsepersonell
from .services import (
    next_patient_nr,
    apply_list_filter, stamp_pabegynt_if_needed,
    get_active_year,
    stamp_obs_times_if_needed, stamp_utskrevet_if_needed,
    validate_patient_time_fields, validate_plassering_unique,
    SHARED_PLASSERINGER, now_local_str,
    recycle_patient_nr_if_last,
)
from .views_common import (
    WRITE_ROLES, _json_body, _ensure_pabegynt_not_before_inntid,
    _patient_to_dict,
)


# ── Hoved-side ────────────────────────────────────────────────────────────────

@login_required
def index_view(request):
    """Render hoved-siden.

    Arrangementsnavnet sendes med i konteksten slik at headeren er riktig
    allerede i første render. Templaten hadde tidligere `LS26` hardkodet som
    innhold, og `loadSettings()` byttet det ut — men først etter tre awaitede
    fetch-er, så et gammelt arrangementsnavn sto synlig i mellomtiden.
    """
    return render(request, 'patients/index.html', {
        # Samme nøkkel som PUT /api/settings/ skriver og loadSettings() leser,
        # slik at server og klient ikke kan vise hver sin verdi.
        'event_name': AppSetting.get('event_name', '') or '',
    })


# ── Innstillinger ─────────────────────────────────────────────────────────────

#: Nøkler `GET /api/settings/` returnerer.
#:
#: `AppSetting` er en generisk nøkkel/verdi-tabell. Uten denne lista havnet
#: enhver ny driftsverdi automatisk i responsen til *alle* innloggede, også
#: `read_only` — inkludert verdier som ikke er ment for klienten. PUT har
#: alltid hatt en whitelist; at GET ikke hadde det var en asymmetri som
#: ville blitt et problem lenge etter at den ble innført (N12).
#:
#: Skal en ny nøkkel ut til frontend, legg den til her bevisst.
SETTINGS_READ_WHITELIST = frozenset({
    'event_name',   # arrangementsnavn
    'active_year',  # aktivt år, styrer hvilke pasienter som vises
})

#: Nøkler `PUT /api/settings/` godtar å skrive. Bevisst smalere enn lese-lista:
#: `active_year` settes via egne endepunkter, ikke ved fri skriving hit.
SETTINGS_WRITE_WHITELIST = frozenset({'event_name'})


@login_required
@require_http_methods(['GET', 'PUT'])
def settings_view(request):
    """Hent eller oppdater appinnstillinger."""
    if request.method == 'GET':
        settings_dict = {
            s.key: s.value
            for s in AppSetting.objects.filter(key__in=SETTINGS_READ_WHITELIST)
        }
        return JsonResponse(settings_dict)

    # PUT – oppdater event_name (krever skrivetilgang)
    if request.user.role not in WRITE_ROLES:
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    for k, v in data.items():
        if k in SETTINGS_WRITE_WHITELIST:
            AppSetting.set(k, v)
    return JsonResponse({'ok': True})


# ── Sesjonstimeout ────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET', 'PUT'])
def session_timeout_view(request):
    """Hent eller sett sesjonstimeout i timer. Kun admin kan sette."""
    if request.method == 'GET':
        try:
            hours = int(AppSetting.get('session_timeout_hours', 8))
        except (ValueError, TypeError):
            hours = 8
        return JsonResponse({'hours': hours})
    # PUT
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)
    data = _json_body(request)
    try:
        hours = int(data.get('hours', 8))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Ugyldig verdi'}, status=400)
    if hours < 1 or hours > 24:
        return JsonResponse({'error': 'Må være mellom 1 og 24'}, status=400)
    AppSetting.set('session_timeout_hours', hours)
    return JsonResponse({'ok': True, 'hours': hours})


# ── Pasienter ─────────────────────────────────────────────────────────────────

@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
# S3: kun POST telles — GET er pollet hvert 30. sekund av hver klient og
# svarer 304 uten kropp når ingenting er endret. 60/min er langt over det
# et menneske rekker, og godt under det en løpsk klient produserer.
@rate_limit(group='patients:create', rate='60/m', method='POST')
def patients_list_view(request):
    """Liste pasienter for aktivt år, eller opprett ny.

    Query-parametre:
      ?filter=<name>        – Filtrer på status (rod/gul/gronn/rodgul/aktive/utskrevet/alle)
      ?include_archived=1   – Inkluder inaktive pasienter
    """
    if request.method == 'GET':
        year = get_active_year()

        filter_name = request.GET.get('filter', 'alle')
        include_archived = request.GET.get('include_archived') == '1'
        # Fase 5: "mine"-filter — default AV, slås på via ?mine=1.
        # Filtrerer på Behandler.user ELLER Helsepersonell.user lik innlogget bruker.
        # Tilgjengelig for alle innloggede roller, også read_only.
        mine_only = request.GET.get('mine') == '1'

        # select_related: `_patient_to_dict()` leser navnet på både
        # forstehjelper og helsepersonell. Uten dette ble det én ekstra
        # spørring per pasient per felt — målt til 515 spørringer ved 1000
        # pasienter, mot 8 med. Endepunktet pollet hvert 30. sekund av hver
        # klient, så det var den dyreste stien i appen.
        qs = (Patient.objects
              .select_related('forstehjelper', 'helsepersonell_ref')
              .order_by('pasientnummer'))
        if not include_archived:
            qs = qs.filter(is_active=True)

        if mine_only and request.user.is_authenticated:
            qs = qs.filter(
                Q(forstehjelper__user=request.user)
                | Q(helsepersonell_ref__user=request.user)
            )

        qs = apply_list_filter(qs, filter_name=filter_name, year=year)

        # ETag/304 — samme mønster som navneregistrene.
        #
        # Kroppen serialiseres én gang og hashes, i stedet for å hashe
        # feltverdier separat: da kan ETag-en per definisjon ikke komme i
        # utakt med det som faktisk sendes. Det dekker samtidig at svaret
        # varierer med ?filter, ?mine og ?include_archived — ulike parametre
        # gir ulik kropp og dermed ulik ETag, uten at de må hashes eksplisitt.
        #
        # Merk hva dette sparer: båndbredden (454 kB per kall ved 1000
        # pasienter), ikke databasearbeidet. Spørringen og serialiseringen
        # kjører uansett for å regne ut hashen.
        kropp = json.dumps([_patient_to_dict(p) for p in qs], default=str)
        etag_value = ('"v1:'
                      + hashlib.sha256(kropp.encode('utf-8')).hexdigest()[:16]
                      + '"')

        if request.META.get('HTTP_IF_NONE_MATCH') == etag_value:
            return HttpResponseNotModified()

        response = HttpResponse(kropp, content_type='application/json')
        response['ETag'] = etag_value
        response['Cache-Control'] = 'private, must-revalidate'
        return response

    # POST – opprett ny pasient i aktivt år (krever skrivetilgang)
    if request.user.role not in WRITE_ROLES:
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)

    # Valider tidsfelter – kun format dd.mm.åååå tt:mm godtas
    try:
        validate_patient_time_fields(data)
    except ValidationError as exc:
        return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

    # Valider kliniske felt mot fast verdimengde. Uten dette kan en klient som
    # går utenom grensesnittet lagre vilkårlig fritekst i feltene.
    try:
        validate_patient_choice_fields(data)
    except ValidationError as exc:
        return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

    active = get_active_year()

    # FORBEDRINGER #19: Valider plassering FØR nummer-tildeling
    # – hindrer hopp i pasientnummer hvis valideringen feiler.
    try:
        validate_plassering_unique(data.get('plassering', ''), active)
    except ValidationError as exc:
        return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

    # Én felles tidsstempel for hele requesten:
    # – inntid og pabegynt skal aldri kunne gå i utakt på grunn av mikro-drift
    # – alltid Europe/Oslo, uavhengig av container-TZ (UTC på Railway)
    now_str = now_local_str()
    data['_now_str'] = now_str  # leses av stamp_*_if_needed

    # Konverter forstehjelper-ID til Forstehjelper-objekt
    forstehjelper_obj = None
    forstehjelper_id = data.get('forstehjelper')
    if forstehjelper_id:
        try:
            forstehjelper_obj = Forstehjelper.objects.get(pk=int(forstehjelper_id))
        except (Forstehjelper.DoesNotExist, ValueError, TypeError):
            pass

    # Konverter helsepersonell_ref-ID til Helsepersonell-objekt
    helsepersonell_obj = None
    helsepersonell_id = data.get('helsepersonell_ref')
    if helsepersonell_id:
        try:
            helsepersonell_obj = Helsepersonell.objects.get(pk=int(helsepersonell_id))
        except (Helsepersonell.DoesNotExist, ValueError, TypeError):
            pass

    # Bruk server-tid hvis frontend sendte blank/manglende inntid.
    # Tidligere: data.get('inntid', now) – returnerte '' hvis nøkkelen fantes med tom verdi.
    inntid_value = (data.get('inntid') or '').strip() or now_str

    # F3: idempotens. Reserveres FØRST her — etter all validering, rett før
    # noe opprettes. Reserverte vi tidligere, ville en avvist innsending brent
    # nøkkelen, og brukeren som rettet feilen fått «allerede sendt inn» på det
    # korrigerte forsøket.
    idem = bygg_nokkel('patient_create', request.user.pk,
                       data.get('idempotency_key'))
    if idem:
        status, verdi = reserver(idem)
        if status == 'ferdig':
            # Retry etter at den første forespørselen var ferdig: svar med
            # pasienten den opprettet, og 200 i stedet for 201 — ingenting ble
            # opprettet nå.
            try:
                return JsonResponse(
                    _patient_to_dict(Patient.objects.get(pk=verdi)),
                )
            except Patient.DoesNotExist:
                # Pasienten er slettet i mellomtiden. Nøkkelen beskytter ikke
                # lenger noe, så la forespørselen gå videre og opprette.
                forkast(idem)
        elif status == 'pagar':
            # Dobbeltinnsending mens den første fortsatt kjører. Raden er på
            # vei; klienten skal laste lista på nytt, ikke sende igjen.
            return JsonResponse(
                {'error': 'Registreringen er allerede sendt inn.',
                 'duplikat': True},
                status=409,
            )

    # FORBEDRINGER #19: Atomisk transaksjon – alt eller ingenting.
    # next_patient_nr() kalles inne i blokken slik at en eventuell IntegrityError
    # ved save() ruller tilbake nummer-allokeringen.
    with transaction.atomic():
        nr = next_patient_nr()
        patient = Patient(
            pasientnummer=nr,
            year=active,  # alltid i aktivt år
            problemstilling=data.get('problemstilling', ''),
            arsak=data.get('arsak', ''),
            transport=data.get('transport', ''),
            inntid=inntid_value,
            grovsortering=data.get('grovsortering', ''),
            pabegynt=data.get('pabegynt', ''),
            plassering=data.get('plassering', ''),
            forstehjelper=forstehjelper_obj,
            helsepersonell_ref=helsepersonell_obj,
            lege=data.get('lege', ''),
            medisiner=data.get('medisiner', ''),
            inn_obspost=data.get('inn_obspost', ''),
            ut_obspost=data.get('ut_obspost', ''),
            utskrevet=data.get('utskrevet', ''),
            utskrevet_til=data.get('utskrevet_til', ''),
            journal=data.get('journal', ''),
        )
        # Rekkefølge: påbegynt → obs-stempling → utskrevet-stempling
        # Alle stamp_*-funksjoner leser data['_now_str'] for konsistent tidsstempel.
        stamp_pabegynt_if_needed(patient, data)
        stamp_obs_times_if_needed(patient, '', data)
        stamp_utskrevet_if_needed(patient, data)

        # Sikkerhetsnett: pabegynt skal aldri kunne være før inntid på nyopprettet pasient.
        # Hvis det skjer (f.eks. brukeren skrev inn inntid manuelt frem i tid),
        # justeres pabegynt opp til inntid.
        _ensure_pabegynt_not_before_inntid(patient)

        try:
            patient.save()
        except Exception:
            # Frigi nøkkelen, ellers står brukeren igjen med en reservasjon
            # for en pasient som aldri ble opprettet, og kan ikke prøve igjen.
            if idem:
                forkast(idem)
            raise

    if idem:
        fullfor(idem, patient.pk)
    return JsonResponse(_patient_to_dict(patient), status=201)


@login_required
@require_http_methods(['PUT', 'DELETE'])
# S3: redigering skjer oftere enn opprettelse — obs-tider stemples, sonen
# endres, pasienten skrives ut — så bøtta er romsligere enn ved
# opprettelse. Den stopper en løpsk klient, ikke en travel sykestue.
@rate_limit(group='patients:detail-write', rate='120/m',
            method=['PUT', 'DELETE'])
def patient_detail_view(request, pk):
    """Oppdater eller slett en pasient.

    **DELETE er en hard-delete**, ikke en soft-delete som docstringen tidligere
    påsto. Raden fjernes fra databasen og pasientnummeret resirkuleres hvis den
    var den siste. Eneste vei tilbake er en backup tatt før slettingen.

    `Patient.is_active` finnes på modellen og leses av `?include_archived`, men
    ingen produksjonskode setter den til False — feltet kan bare endres via
    Django-admin. Det er derfor ikke slettemekanismen appen faktisk bruker.
    """
    try:
        patient = Patient.objects.get(pk=pk)
    except Patient.DoesNotExist:
        return JsonResponse({'error': 'Pasient ikke funnet'}, status=404)

    if request.method == 'PUT':
        if request.user.role not in WRITE_ROLES:
            return JsonResponse({'error': 'Ingen tilgang'}, status=403)

        data = _json_body(request)

        # Valider tidsfelter – kun format dd.mm.åååå tt:mm godtas
        try:
            validate_patient_time_fields(data)
        except ValidationError as exc:
            return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

        # Valider kliniske felt mot fast verdimengde (samme regel som ved opprettelse)
        try:
            validate_patient_choice_fields(data)
        except ValidationError as exc:
            return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

        # Valider plassering-unikhet hvis plassering er i payload
        if 'plassering' in data:
            try:
                validate_plassering_unique(
                    data.get('plassering', ''),
                    patient.year,
                    exclude_pk=patient.pk,
                )
            except ValidationError as exc:
                return JsonResponse({'error': '; '.join(exc.messages)}, status=400)

        allowed_text_fields = {
            'problemstilling', 'arsak', 'transport', 'inntid', 'grovsortering',
            'pabegynt', 'plassering', 'lege',
            'medisiner', 'inn_obspost', 'ut_obspost', 'utskrevet',
            'utskrevet_til', 'journal',
        }

        # Lagre gammel plassering FØR mutasjon for obs-stempling
        old_plassering = patient.plassering or ''

        for field, value in data.items():
            if field in allowed_text_fields:
                setattr(patient, field, value)

        # Forstehjelper: konverter ID til objekt
        if 'forstehjelper' in data:
            forstehjelper_id = data['forstehjelper']
            if forstehjelper_id:
                try:
                    patient.forstehjelper = Forstehjelper.objects.get(pk=int(forstehjelper_id))
                except (Forstehjelper.DoesNotExist, ValueError, TypeError):
                    pass
            else:
                patient.forstehjelper = None

        # Helsepersonell_ref: konverter ID til objekt
        if 'helsepersonell_ref' in data:
            hp_id = data['helsepersonell_ref']
            if hp_id:
                try:
                    patient.helsepersonell_ref = Helsepersonell.objects.get(pk=int(hp_id))
                except (Helsepersonell.DoesNotExist, ValueError, TypeError):
                    pass
            else:
                patient.helsepersonell_ref = None

        # Én felles tidsstempel for hele requesten (Europe/Oslo, uavh. av container-TZ).
        data['_now_str'] = now_local_str()

        # Rekkefølge: påbegynt → obs-stempling → utskrevet-stempling
        stamp_pabegynt_if_needed(patient, data)
        stamp_obs_times_if_needed(patient, old_plassering, data)
        stamp_utskrevet_if_needed(patient, data)

        # Sikkerhetsnett: pabegynt < inntid skal ikke kunne forekomme.
        _ensure_pabegynt_not_before_inntid(patient)

        patient.save()
        return JsonResponse(_patient_to_dict(patient))

    # DELETE – hard-delete med recycle av pasientnummer (krever admin)
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    pasientnummer = patient.pasientnummer
    with transaction.atomic():
        patient.delete()
        recycled = recycle_patient_nr_if_last(pasientnummer)
    return JsonResponse({'ok': True, 'recycled_nr': recycled})


# ── Reset testdata ─────────────────────────────────────────────────────────────

@login_required
@admin_required
@require_http_methods(['POST'])
def reset_active_year_view(request):
    """Slett alle pasienter i aktivt år. Kun admin.

    Krever at request-body inneholder {"confirm": true} for å unngå feilklikk.
    """
    data = _json_body(request)
    if not data.get('confirm'):
        return JsonResponse(
            {'error': 'Bekreftelse mangler. Send {"confirm": true} for å slette.'},
            status=400,
        )

    active = get_active_year()
    # Lag pre-reset backup før sletting
    from .backup_service import create_backup
    create_backup(kind='pre_reset', user=request.user,
                  note=f'Før nullstilling av år {active}')
    # Hard delete – testdata skal bort. Tidligere år berøres ikke.
    deleted, _ = Patient.objects.filter(year=active).delete()
    # Nullstill next_patient_nr til 1
    AppSetting.set('next_patient_nr', 1)
    return JsonResponse({
        'ok': True,
        'year': active,
        'antall_slettet': deleted,
        'melding': f'{deleted} pasienter i år {active} slettet. next_patient_nr nullstilt til 1.',
    })


