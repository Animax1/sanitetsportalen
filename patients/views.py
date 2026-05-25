"""
Views for pasientregistreringssystemet.

Alle API-endepunkter returnerer JSON.
Bruker CSRF-token fra cookie via X-CSRFToken-header (Django-konvensjon).
"""
import hashlib
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseNotModified
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.conf import settings

from django.core.exceptions import ValidationError

from django.db import transaction
from django.db.models import Q

from .models import Patient, AppSetting, Forstehjelper, Helsepersonell
from .services import (
    basic_stats, full_stats, next_patient_nr,
    apply_list_filter, stamp_pabegynt_if_needed,
    get_active_year, set_active_year,
    stamp_obs_times_if_needed, stamp_utskrevet_if_needed,
    validate_patient_time_fields, validate_plassering_unique,
    SHARED_PLASSERINGER, now_local_str,
    recycle_patient_nr_if_last,
    has_role_at_least, ARKIV_VIEW_MIN_ROLE, ARKIV_WRITE_ROLE,
    arkiver_aktiv_vakt, compute_arkiv_stats, compute_arkiv_full_stats,
)
from accounts.decorators import admin_required, stats_required, write_required

# Roller med skrivetilgang til pasienter
WRITE_ROLES = ('admin', 'lead', 'read_write')


def _json_body(request):
    """Parse JSON-body fra request, returner tom dict ved feil."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


def _ensure_pabegynt_not_before_inntid(patient):
    """Sikkerhetsnett: hvis pabegynt < inntid, juster pabegynt opp til inntid.

    Bakgrunn: `inntid` settes ofte fra klient-tid (nettleserens klokke) ved
    opprettelse, mens `pabegynt` stemples av server. Klient-klokker kan
    drive 1-5 min fra NTP-synkronisert server. Resultat: pabegynt < inntid,
    som gir negative ventetider i statistikken.

    Funksjonen muterer `patient` in-place og kaller ikke save().
    Returnerer True hvis pabegynt ble justert.
    """
    inntid = (patient.inntid or '').strip()
    pabegynt = (patient.pabegynt or '').strip()
    if not inntid or not pabegynt:
        return False
    fmt = '%d.%m.%Y %H:%M'
    try:
        t_inn = datetime.strptime(inntid, fmt)
        t_pab = datetime.strptime(pabegynt, fmt)
    except (ValueError, TypeError):
        return False  # Ugyldig format – latt valideringen ta det
    if t_pab < t_inn:
        patient.pabegynt = inntid
        return True
    return False


def _patient_to_dict(p):
    """Konverter Patient-objekt til dict for JSON-respons."""
    return {
        'id': p.id,
        'patient_nr': p.pasientnummer,
        'pasientnummer': p.pasientnummer,
        'year': p.year,
        'problemstilling': p.problemstilling,
        'arsak': p.arsak,
        'transport': p.transport,
        'inntid': p.inntid,
        'grovsortering': p.grovsortering,
        'pabegynt': p.pabegynt,
        'plassering': p.plassering,
        'forstehjelper': (
            {'id': p.forstehjelper.id, 'name': p.forstehjelper.name}
            if p.forstehjelper else None
        ),
        'helsepersonell_ref': (
            {'id': p.helsepersonell_ref.id, 'name': p.helsepersonell_ref.name}
            if p.helsepersonell_ref else None
        ),
        'lege': p.lege,
        'medisiner': p.medisiner,
        'inn_obspost': p.inn_obspost,
        'ut_obspost': p.ut_obspost,
        'utskrevet': p.utskrevet,
        'utskrevet_til': p.utskrevet_til,
        'journal': p.journal,
        'created_at': p.created_at.strftime('%d.%m.%Y %H:%M') if p.created_at else '',
        'is_active': p.is_active,
    }


# ── Hoved-side ────────────────────────────────────────────────────────────────

@login_required
def index_view(request):
    """Render hoved-siden."""
    return render(request, 'patients/index.html')


# ── Innstillinger ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET', 'PUT'])
def settings_view(request):
    """Hent eller oppdater appinnstillinger."""
    if request.method == 'GET':
        settings_dict = {s.key: s.value for s in AppSetting.objects.all()}
        return JsonResponse(settings_dict)

    # PUT – oppdater event_name (krever skrivetilgang)
    if request.user.role not in WRITE_ROLES:
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    allowed = {'event_name'}
    for k, v in data.items():
        if k in allowed:
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

@login_required
@require_http_methods(['GET', 'POST'])
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

        qs = Patient.objects.order_by('pasientnummer')
        if not include_archived:
            qs = qs.filter(is_active=True)

        if mine_only and request.user.is_authenticated:
            qs = qs.filter(
                Q(forstehjelper__user=request.user)
                | Q(helsepersonell_ref__user=request.user)
            )

        qs = apply_list_filter(qs, filter_name=filter_name, year=year)
        return JsonResponse([_patient_to_dict(p) for p in qs], safe=False)

    # POST – opprett ny pasient i aktivt år (krever skrivetilgang)
    if request.user.role not in WRITE_ROLES:
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)

    # Valider tidsfelter – kun format dd.mm.åååå tt:mm godtas
    try:
        validate_patient_time_fields(data)
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

        patient.save()
    return JsonResponse(_patient_to_dict(patient), status=201)


@login_required
@require_http_methods(['PUT', 'DELETE'])
def patient_detail_view(request, pk):
    """Oppdater eller slett (soft-delete) en pasient."""
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


# ── Forstehjelpere ────────────────────────────────────────────────────────────

@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def forstehjelpere_view(request):
    """Liste alle forstehjelpere (GET), eller opprett ny (POST, kun admin).

    GET returnerer alle forstehjelpere (inkl. inaktive) sortert etter is_active desc, name.
    Støtter ETag/304-mønsteret:
      - Beregner ETag basert på innholdet. Hvis klienten sender If-None-Match med
        samme ETag, returneres 304 Not Modified uten kropp.
      - never_cache og ETag er kompatible: never_cache sier "bekreft med server"
        og ETag sier "hvis samme, send 304". Kombinasjonen er ideell.
    """
    if request.method == 'GET':
        forstehjelpere = list(Forstehjelper.objects.all().order_by('-is_active', 'name'))
        data = [{'id': b.id, 'name': b.name, 'is_active': b.is_active} for b in forstehjelpere]

        # Beregn ETag som SHA-256-hash av (id, name, is_active)-tupler
        hash_input = str(sorted([(b.id, b.name, b.is_active) for b in forstehjelpere]))
        # sha256 brukes kun for ETag-identitet (ikke sikkerhet). Kortes til
        # 16 tegn for å holde header-verdien kompakt.
        etag_value = '"v1:' + hashlib.sha256(hash_input.encode('utf-8')).hexdigest()[:16] + '"'

        # Sjekk If-None-Match-header fra klient
        if request.META.get('HTTP_IF_NONE_MATCH') == etag_value:
            return HttpResponseNotModified()

        response = JsonResponse(data, safe=False)
        response['ETag'] = etag_value
        response['Cache-Control'] = 'private, must-revalidate'
        return response

    # POST – kun admin
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Navn er påkrevd'}, status=400)

    if Forstehjelper.objects.filter(name=name).exists():
        return JsonResponse({'error': f'Førstehjelper "{name}" finnes allerede'}, status=400)

    b = Forstehjelper.objects.create(name=name, is_active=True)
    return JsonResponse({'id': b.id, 'name': b.name, 'is_active': b.is_active}, status=201)


@login_required
@require_http_methods(['PUT', 'DELETE'])
def forstehjelper_detail_view(request, pk):
    """Oppdater (PUT) eller slett (DELETE) en førstehjelper. Kun admin."""
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    try:
        forstehjelper = Forstehjelper.objects.get(pk=pk)
    except Forstehjelper.DoesNotExist:
        return JsonResponse({'error': 'Førstehjelper ikke funnet'}, status=404)

    if request.method == 'PUT':
        data = _json_body(request)
        if 'name' in data:
            name = (data['name'] or '').strip()
            if not name:
                return JsonResponse({'error': 'Navn kan ikke være tomt'}, status=400)
            forstehjelper.name = name
        if 'is_active' in data:
            forstehjelper.is_active = bool(data['is_active'])
        forstehjelper.save()
        return JsonResponse({'id': forstehjelper.id, 'name': forstehjelper.name, 'is_active': forstehjelper.is_active})

    # DELETE – blokkert hvis førstehjelper er i bruk (PROTECT vil kaste IntegrityError)
    from django.db.models.deletion import ProtectedError
    try:
        forstehjelper.delete()
        return JsonResponse({'ok': True})
    except ProtectedError:
        return JsonResponse(
            {'error': 'Førstehjelperen er knyttet til pasienter og kan ikke slettes. Deaktiver i stedet.'},
            status=409,
        )


# ── Helsepersonell ────────────────────────────────────────────────────────
# Samme mønster som behandlere: CRUD + ETag/304.

@never_cache
@login_required
@require_http_methods(['GET', 'POST'])
def helsepersonell_view(request):
    """Liste alle helsepersonell (GET), eller opprett ny (POST, kun admin)."""
    if request.method == 'GET':
        qs = list(Helsepersonell.objects.all().order_by('-is_active', 'name'))
        data = [{'id': h.id, 'name': h.name, 'is_active': h.is_active} for h in qs]

        # Beregn ETag som SHA-256-hash av (id, name, is_active)-tupler
        hash_input = str(sorted([(h.id, h.name, h.is_active) for h in qs]))
        # sha256 brukes kun for ETag-identitet (ikke sikkerhet). Kortes til
        # 16 tegn for å holde header-verdien kompakt.
        etag_value = '"v1:' + hashlib.sha256(hash_input.encode('utf-8')).hexdigest()[:16] + '"'

        if request.META.get('HTTP_IF_NONE_MATCH') == etag_value:
            return HttpResponseNotModified()

        response = JsonResponse(data, safe=False)
        response['ETag'] = etag_value
        response['Cache-Control'] = 'private, must-revalidate'
        return response

    # POST – kun admin
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Navn er påkrevd'}, status=400)

    if Helsepersonell.objects.filter(name=name).exists():
        return JsonResponse({'error': f'Helsepersonell "{name}" finnes allerede'}, status=400)

    h = Helsepersonell.objects.create(name=name, is_active=True)
    return JsonResponse({'id': h.id, 'name': h.name, 'is_active': h.is_active}, status=201)


@login_required
@require_http_methods(['PUT', 'DELETE'])
def helsepersonell_detail_view(request, pk):
    """Oppdater (PUT) eller slett (DELETE) helsepersonell. Kun admin."""
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    try:
        h = Helsepersonell.objects.get(pk=pk)
    except Helsepersonell.DoesNotExist:
        return JsonResponse({'error': 'Helsepersonell ikke funnet'}, status=404)

    if request.method == 'PUT':
        data = _json_body(request)
        if 'name' in data:
            name = (data['name'] or '').strip()
            if not name:
                return JsonResponse({'error': 'Navn kan ikke være tomt'}, status=400)
            h.name = name
        if 'is_active' in data:
            h.is_active = bool(data['is_active'])
        h.save()
        return JsonResponse({'id': h.id, 'name': h.name, 'is_active': h.is_active})

    from django.db.models.deletion import ProtectedError
    try:
        h.delete()
        return JsonResponse({'ok': True})
    except ProtectedError:
        return JsonResponse(
            {'error': 'Helsepersonellet er knyttet til pasienter og kan ikke slettes. Deaktiver i stedet.'},
            status=409,
        )


# ═══════════════════════════════════════════════════════════════════════
# BACKUP / RESTORE
# ═══════════════════════════════════════════════════════════════════════

def _log_audit(request, action, detail):
    """Hjelpefunksjon for å logge backup-hendelser til AuditLog."""
    from audit.models import AuditLog
    AuditLog.objects.create(
        table_name='backup',
        record_id=0,
        action='CREATE',
        field_name=action,
        new_value=detail,
        user=request.user if request.user.is_authenticated else None,
        ip=request.META.get('REMOTE_ADDR'),
    )


@login_required
@admin_required
@require_http_methods(['GET'])
def backup_list_view(request):
    """Liste alle backups. Admin-only."""
    from .models import Backup, BackupConfig
    cfg = BackupConfig.get()
    backups = [{
        'id': b.id,
        'filename': b.filename,
        'kind': b.kind,
        'kind_display': b.get_kind_display(),
        'size_bytes': b.size_bytes,
        'created_at': b.created_at.isoformat(),
        'created_by': b.created_by.username if b.created_by else None,
        'note': b.note,
    } for b in Backup.objects.all()[:200]]

    return JsonResponse({
        'config': {
            'interval_minutes': cfg.interval_minutes,
            'last_run_at': cfg.last_run_at.isoformat() if cfg.last_run_at else None,
            'choices': [{'value': v, 'label': l} for v, l in [(0, 'Av'), (30, 'Hver 30. min'), (60, 'Hver time'), (360, 'Hver 6. time'), (1440, 'Hver 24. time')]],
        },
        'backups': backups,
    })


@login_required
@admin_required
@require_http_methods(['POST'])
def backup_config_view(request):
    """Oppdater intervall. Admin-only."""
    from .models import BackupConfig
    data = _json_body(request)
    interval = int(data.get('interval_minutes', 60))
    if interval not in (0, 30, 60, 360, 1440):
        return JsonResponse({'error': 'Ugyldig intervall'}, status=400)

    cfg = BackupConfig.get()
    cfg.interval_minutes = interval
    cfg.save(update_fields=['interval_minutes'])
    _log_audit(request, 'backup_config_changed', f'interval={interval}')
    return JsonResponse({'ok': True, 'interval_minutes': interval})


@login_required
@admin_required
@require_http_methods(['POST'])
def backup_create_now_view(request):
    """Lag en manuell backup nå. Admin-only."""
    from .backup_service import create_backup
    data = _json_body(request)
    note = (data.get('note') or '').strip()[:200]
    backup = create_backup(kind='manual', user=request.user, note=note)
    _log_audit(request, 'backup_created_manual', backup.filename)
    return JsonResponse({
        'ok': True,
        'id': backup.id,
        'filename': backup.filename,
        'size_bytes': backup.size_bytes,
    }, status=201)


@login_required
@admin_required
@require_http_methods(['POST'])
def backup_restore_view(request, pk):
    """Gjenopprett fra en backup. Krever confirm='GJENOPPRETT'. Admin-only."""
    from .models import Backup
    from .backup_service import restore_backup
    data = _json_body(request)
    if data.get('confirm') != 'GJENOPPRETT':
        return JsonResponse(
            {'error': 'Bekreftelse mangler. Send confirm="GJENOPPRETT".'}, status=400,
        )

    try:
        backup = Backup.objects.get(pk=pk)
    except Backup.DoesNotExist:
        return JsonResponse({'error': 'Backup ikke funnet'}, status=404)

    try:
        restore_backup(backup, user=request.user)
    except FileNotFoundError:
        logger.exception('Backup-fil mangler på disk for pk=%s', pk)
        return JsonResponse({'error': 'Backup-fil mangler på disk'}, status=404)
    except Exception:
        logger.exception('Gjenoppretting feilet for backup pk=%s', pk)
        return JsonResponse(
            {'error': 'Gjenoppretting feilet. Se server-logg for detaljer.'},
            status=500,
        )

    _log_audit(request, 'backup_restored', backup.filename)
    return JsonResponse({'ok': True, 'restored': backup.filename})


@login_required
@admin_required
@require_http_methods(['GET'])
def backup_download_view(request, pk):
    """Last ned en backup-fil. Admin-only. Logges i audit."""
    from .models import Backup
    from .backup_service import get_backup_dir
    from django.http import FileResponse

    try:
        backup = Backup.objects.get(pk=pk)
    except Backup.DoesNotExist:
        return JsonResponse({'error': 'Backup ikke funnet'}, status=404)

    path = get_backup_dir() / backup.filename
    if not path.exists():
        return JsonResponse({'error': 'Fil mangler på disk'}, status=404)

    _log_audit(request, 'backup_downloaded', backup.filename)
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=backup.filename)


@login_required
@admin_required
@require_http_methods(['DELETE'])
def backup_delete_view(request, pk):
    """Slett en backup-fil og metadata. Admin-only."""
    from .models import Backup
    from .backup_service import get_backup_dir

    try:
        backup = Backup.objects.get(pk=pk)
    except Backup.DoesNotExist:
        return JsonResponse({'error': 'Backup ikke funnet'}, status=404)

    path = get_backup_dir() / backup.filename
    if path.exists():
        path.unlink()
    filename = backup.filename
    backup.delete()
    _log_audit(request, 'backup_deleted', filename)
    return JsonResponse({'ok': True})


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


# ── Statistikk ────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def stats_view(request):
    """Basis-statistikk for header-chips. Filtrerer alltid på aktivt år.

    Cachet 15s med ETag/304 for å redusere last ved gjentatt polling.
    Cache-nøkkel inkluderer aktivt år slik at bytte av år gir ny cache.
    """
    from .stats_cache import cached_stats_response
    year = get_active_year()

    @cached_stats_response(cache_key=f'basic:{year}', ttl=15)
    def _inner(req):
        return basic_stats(year=year)

    return _inner(request)


@stats_required
@require_http_methods(['GET'])
def full_stats_view(request):
    """Full statistikk for statistikk-dashboard. Kun admin, lead og lead_view.

    Cachet 60s med ETag/304. Dyre aggregater (percentiler, gruppetellinger)
    regnes kun én gang per minutt per år.
    """
    from .stats_cache import cached_stats_response
    year = get_active_year()

    @cached_stats_response(cache_key=f'full:{year}', ttl=60)
    def _inner(req):
        return full_stats(year=year)

    return _inner(request)


# ── Arkiv-liste ───────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def archives_view(request):
    """List JSON-arkivfiler."""
    import json as _json
    arkiv_dir = os.path.join(settings.BASE_DIR, 'arkiv')
    os.makedirs(arkiv_dir, exist_ok=True)
    files = sorted(
        [f for f in os.listdir(arkiv_dir) if f.endswith('.json')],
        reverse=True,
    )
    result = []
    for f in files:
        try:
            with open(os.path.join(arkiv_dir, f), encoding='utf-8') as fh:
                d = _json.load(fh)
            result.append({
                'fil': f,
                'arkivert': d.get('arkivert', ''),
                'antall': d.get('antall_pasienter', 0),
            })
        except Exception:
            result.append({'fil': f, 'arkivert': '', 'antall': '?'})
    return JsonResponse(result, safe=False)


# ════════════════════════════════════════════════════════════════════════
# VAKTARKIV – database-basert arkiv av vakter
# ════════════════════════════════════════════════════════════════════════

@login_required
@require_http_methods(['POST'])
def arkiv_lagre_view(request):
    """Lagre aktiv vakt som arkiv-snapshot. Kun admin.

    Body: {arrangement_navn: str, notat: str (valgfri)}
    Returnerer: {ok: true, id, tittel, antall_pasienter}
    """
    if not has_role_at_least(request.user, ARKIV_WRITE_ROLE):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    arrangement_navn = (data.get('arrangement_navn') or '').strip()
    if not arrangement_navn:
        return JsonResponse({'error': 'arrangement_navn er påkrevd'}, status=400)

    notat = (data.get('notat') or '').strip()

    try:
        arkiv, antall = arkiver_aktiv_vakt(arrangement_navn, notat, request.user)
    except Exception:
        logger.exception('Feil ved arkivering av vakt')
        return JsonResponse({'error': 'Arkivering feilet. Se server-logg.'}, status=500)

    _log_audit(request, 'arkiv_lagret', f'arkiv_id={arkiv.pk}, tittel={arkiv.tittel}')
    return JsonResponse({
        'ok': True,
        'id': arkiv.pk,
        'tittel': arkiv.tittel,
        'antall_pasienter': antall,
    }, status=201)


@login_required
@require_http_methods(['GET'])
def arkiv_liste_view(request):
    """Liste alle arkiver. Krever ARKIV_VIEW_MIN_ROLE (standard: admin).

    Returnerer: [{id, tittel, arrangement_navn, importert_at, antall_pasienter, importert_av}]
    """
    if not has_role_at_least(request.user, ARKIV_VIEW_MIN_ROLE):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    from .models import VaktArkiv
    arkiver = VaktArkiv.objects.select_related('importert_av').all()
    data = [{
        'id': a.pk,
        'tittel': a.tittel,
        'arrangement_navn': a.arrangement_navn,
        'importert_at': a.importert_at.isoformat(),
        'antall_pasienter': a.antall_pasienter,
        'importert_av': a.importert_av.username,
    } for a in arkiver]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(['GET', 'DELETE'])
def arkiv_detalj_view(request, pk):
    """Vis (GET) eller slett (DELETE) et arkiv.

    GET: Returnerer full statistikk + metadata + SHA-256-verifikasjon.
    DELETE: Krever admin og {confirm: true} i body.
    """
    from .models import VaktArkiv, ArkivertPasient
    import hashlib
    import json as _jmod

    try:
        arkiv = VaktArkiv.objects.select_related('importert_av').get(pk=pk)
    except VaktArkiv.DoesNotExist:
        return JsonResponse({'error': 'Arkiv ikke funnet'}, status=404)

    if request.method == 'GET':
        if not has_role_at_least(request.user, ARKIV_VIEW_MIN_ROLE):
            return JsonResponse({'error': 'Ingen tilgang'}, status=403)

        stats = compute_arkiv_stats(arkiv)

        # SHA-256-verifikasjon
        from .services import _compute_sha256_for_arkiv
        pasienter_dicts = list(
            ArkivertPasient.objects.filter(arkiv=arkiv).values(
                'pasientnummer', 'problemstilling', 'arsak', 'transport',
                'grovsortering', 'plassering', 'inntid', 'pabegynt',
                'inn_obspost', 'ut_obspost', 'utskrevet', 'utskrevet_til',
                'forstehjelper_navn', 'helsepersonell_navn', 'lege', 'medisiner', 'journal',
            )
        )
        sha_now = _compute_sha256_for_arkiv(arkiv, pasienter_dicts)
        tamper_detected = bool(arkiv.sha256 and sha_now != arkiv.sha256)

        return JsonResponse({
            'id': arkiv.pk,
            'tittel': arkiv.tittel,
            'arrangement_navn': arkiv.arrangement_navn,
            'importert_at': arkiv.importert_at.isoformat(),
            'importert_av': arkiv.importert_av.username,
            'antall_pasienter': arkiv.antall_pasienter,
            'year_snapshot': arkiv.year_snapshot,
            'notat': arkiv.notat,
            'sha256': arkiv.sha256,
            'tamper_detected': tamper_detected,
            'stats': stats,
        })

    # DELETE
    if not has_role_at_least(request.user, ARKIV_WRITE_ROLE):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    data = _json_body(request)
    if not data.get('confirm'):
        return JsonResponse(
            {'error': 'Bekreftelse mangler. Send {\"confirm\": true} for å slette.'},
            status=400,
        )

    tittel = arkiv.tittel
    arkiv.delete()  # CASCADE sletter ArkivertPasient-rader
    _log_audit(request, 'arkiv_slettet', f'arkiv_id={pk}, tittel={tittel}')
    return JsonResponse({'ok': True})


@login_required
@require_http_methods(['GET'])
def arkiv_full_stats_view(request, pk):
    """Returner full statistikk for et arkivert vakt.

    Samme struktur som /api/full-stats/ (chi2, Kruskal-Wallis,
    krysstabeller, tids-statistikk pr. gruppe, ankomster, obs-stats).
    Tilgang: ARKIV_VIEW_MIN_ROLE (default admin).
    """
    from .models import VaktArkiv

    if not has_role_at_least(request.user, ARKIV_VIEW_MIN_ROLE):
        return JsonResponse({'error': 'Ingen tilgang'}, status=403)

    try:
        arkiv = VaktArkiv.objects.get(pk=pk)
    except VaktArkiv.DoesNotExist:
        return JsonResponse({'error': 'Arkiv ikke funnet'}, status=404)

    stats = compute_arkiv_full_stats(arkiv)
    return JsonResponse(stats)
