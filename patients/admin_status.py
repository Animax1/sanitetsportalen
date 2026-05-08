"""Admin server-status dashbord.

Gir admin innsyn i live serverbelastning:
- Requests/sek, responstid (snitt/P50/P95)
- Antall aktive sesjoner
- Minnebruk (RSS)
- Tid siden siste backup
- Feature-flag-kontroll (fremtidig bruk)

Kun for admin-rollen.
"""
import json
import os
import re
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.decorators import admin_required
from audit.models import AuditLog

from .middleware import metrics_store
from .models import AppSetting, Backup


# Feature-flag nøkler
# MERK: Live-statistikk-funksjonen er IKKE implementert. Default er derfor
# 'false' så dashbordet ikke gir inntrykk av at noe er aktivt når det ikke er det.
# Når funksjonen bygges, flytt defaulten tilbake til 'true' i samme commit som
# leverer funksjonen, slik at de ikke kommer ut av sync.
FLAG_LIVE_STATS = 'feature.live_stats_enabled'
FLAG_LIVE_STATS_DEFAULT = 'false'


def _get_memory_mb():
    """Returner RSS i MB, eller None hvis ikke tilgjengelig."""
    try:
        import resource
        # ru_maxrss er i KB på Linux, B på macOS
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # På Linux er dette KB, vi antar Linux (Railway)
        return round(rss_kb / 1024, 1)
    except Exception:
        return None


def _get_session_count():
    """Tell aktive (ikke-utløpte) sesjoner."""
    try:
        from django.contrib.sessions.models import Session
        return Session.objects.filter(expire_date__gt=timezone.now()).count()
    except Exception:
        return None


def _get_last_backup_info():
    """Returner info om siste vellykkede backup.

    Backup-modellen lagrer KUN vellykkede kjøringer (mislykkede backups commitet
    aldri raden), så vi henter bare siste rad uten ekstra status-filter.
    Tidligere `filter(status='success')` traff aldri fordi feltet ikke finnes
    på modellen — da viste dashbordet alltid "Ingen backup funnet".
    """
    try:
        latest = Backup.objects.order_by('-created_at').first()
        if not latest:
            return {'found': False}
        age = timezone.now() - latest.created_at
        return {
            'found': True,
            'created_at': latest.created_at.isoformat(),
            'age_minutes': int(age.total_seconds() / 60),
            'filename': latest.filename,
            'size_bytes': latest.size_bytes,
            'kind': latest.kind,
        }
    except Exception:
        return {'found': False}


def _get_worker_config():
    """Hent gjeldende Gunicorn-konfigurasjon fra env."""
    return {
        'workers': os.environ.get('WEB_WORKERS', '1 (default)'),
        'threads': os.environ.get('WEB_THREADS', '4 (default)'),
        'max_requests': os.environ.get('WEB_MAX_REQUESTS', '1000 (default)'),
        'pid': os.getpid(),
    }


# Regex for å fjerne credentials fra URL-er som kan forekomme i error-strenger.
# Treffer mønster som 'redis://default:hemmelig123@host:6379/0' → 'redis://[scrubbed]@host:6379/0'
_URL_CREDS_RE = re.compile(r'([a-zA-Z][a-zA-Z0-9+.\-]*://)([^/@\s]*@)')


def _scrub_secrets(text: str) -> str:
    """Fjern credentials fra error-meldinger før de vises i admin-UI.

    Forsvarslag mot fremtidige redis-py-versjoner som kunne lekket passord.
    Dagens versjon gjør ikke det, men admin-UI-data ender ofte i logger,
    skjermbilder, support-mailer etc. — best å scrubbe defensivt.
    """
    if not text:
        return text
    return _URL_CREDS_RE.sub(r'\1[scrubbed]@', text)


def _get_cache_health():
    """Sjekk cache-backend og at den faktisk fungerer (write-read-delete).

    Returnerer dict med 'backend' (redis|locmem) og 'healthy' (bool) +
    'latency_ms'. Brukes av admin for å verifisere at delt cache funker
    på tvers av workers før en stor vakt.

    Skal aldri kaste — alle feil fanges og rapporteres som unhealthy.
    Eventuelle credentials i feilmeldinger scrubbes før retur.
    """
    backend_name = getattr(settings, 'CACHE_BACKEND_NAME', 'unknown')
    probe_key = f'_health_probe_{uuid.uuid4().hex[:8]}'
    probe_value = f'ok_{int(time.time())}'
    try:
        start = time.perf_counter()
        cache.set(probe_key, probe_value, 30)
        got = cache.get(probe_key)
        cache.delete(probe_key)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            'backend': backend_name,
            'healthy': got == probe_value,
            'latency_ms': latency_ms,
        }
    except Exception as exc:
        return {
            'backend': backend_name,
            'healthy': False,
            'error': _scrub_secrets(str(exc))[:200],
        }


def _build_status_payload():
    """Samle alle status-data i én dict."""
    return {
        'timestamp': timezone.now().isoformat(),
        'metrics_5min': metrics_store.snapshot(window_seconds=300),
        'metrics_1min': metrics_store.snapshot(window_seconds=60),
        'memory_mb': _get_memory_mb(),
        'active_sessions': _get_session_count(),
        'last_backup': _get_last_backup_info(),
        'worker_config': _get_worker_config(),
        'cache_health': _get_cache_health(),
        'feature_flags': {
            FLAG_LIVE_STATS: AppSetting.get(FLAG_LIVE_STATS, FLAG_LIVE_STATS_DEFAULT),
        },
    }


@admin_required
def admin_status_view(request):
    """HTML-dashbord for admin."""
    payload = _build_status_payload()
    return render(request, 'patients/admin_status.html', {
        'payload': payload,
        'payload_json': json.dumps(payload, indent=2, ensure_ascii=False),
    })


@admin_required
def admin_status_json(request):
    """JSON-endepunkt for polling fra dashbord."""
    return JsonResponse(_build_status_payload())


# ── Sesjonshåndtering ─────────────────────────────────────────────────────────────────
# Lar admin se og avslutte aktive brukersesjoner under høy last.

def _list_active_sessions():
    """Returner liste over aktive sesjoner med (kun) brukernavn og rolle.

    Sesjoner som ikke er knyttet til en bruker (anonyme) hoppes over.
    Sesjoner med slettet bruker hoppes over (orphan).
    """
    User = get_user_model()
    now = timezone.now()
    active_qs = Session.objects.filter(expire_date__gt=now)
    sessions = []
    # Bygg user_id-liste i én queryset for å unngå N+1
    user_ids = []
    decoded_per_session = []
    for sess in active_qs:
        try:
            data = sess.get_decoded()
        except Exception:
            continue
        uid = data.get('_auth_user_id')
        if not uid:
            continue
        try:
            uid_int = int(uid)
        except (TypeError, ValueError):
            continue
        user_ids.append(uid_int)
        decoded_per_session.append((sess, uid_int))

    users_by_id = {u.id: u for u in User.objects.filter(id__in=user_ids)}
    for sess, uid in decoded_per_session:
        user = users_by_id.get(uid)
        if not user:
            continue
        sessions.append({
            'session_key': sess.session_key,
            'user_id': user.id,
            'username': user.username,
            'role': getattr(user, 'role', '') or '',
            'expire_date': sess.expire_date.isoformat(),
        })
    # Sorter alfabetisk på brukernavn for stabilt UI
    sessions.sort(key=lambda s: s['username'].lower())
    return sessions


def _audit_session_kill(request, table_name, record_id, note):
    """Loggfør tvungen utlogging i AuditLog."""
    try:
        ip = request.META.get('REMOTE_ADDR') or None
        AuditLog.objects.create(
            table_name=table_name,
            record_id=record_id,
            action='UPDATE',
            field_name='force_logout',
            old_value='active',
            new_value=note,
            user=request.user if request.user.is_authenticated else None,
            ip=ip,
        )
    except Exception:
        # Audit-logging skal aldri blokkere selve handlingen
        pass


@admin_required
def admin_sessions_list(request):
    """GET: returner liste over aktive sesjoner som JSON."""
    return JsonResponse({
        'sessions': _list_active_sessions(),
        'count': _get_session_count() or 0,
        'timestamp': timezone.now().isoformat(),
    })


@admin_required
@require_http_methods(['POST'])
def admin_session_kill(request):
    """POST: avslutt én konkret sesjon. Body: session_key."""
    session_key = request.POST.get('session_key', '').strip()
    if not session_key:
        return JsonResponse({'ok': False, 'error': 'Mangler session_key'}, status=400)

    # Beskytt mot å logge ut seg selv ved et uhell – admin skal bruke logout-knappen
    if request.session.session_key == session_key:
        return JsonResponse(
            {'ok': False, 'error': 'Kan ikke logge ut din egen sesjon her. Bruk "Logg ut" i menyen.'},
            status=400,
        )

    # Finn sesjonen og hent brukernavn for audit før sletting
    try:
        sess = Session.objects.get(session_key=session_key)
    except Session.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Sesjon finnes ikke (allerede utløpt)'}, status=404)

    username = ''
    user_id = 0
    try:
        data = sess.get_decoded()
        uid = data.get('_auth_user_id')
        if uid:
            User = get_user_model()
            user = User.objects.filter(id=int(uid)).first()
            if user:
                username = user.username
                user_id = user.id
    except Exception:
        pass

    sess.delete()
    _audit_session_kill(
        request,
        table_name='Session',
        record_id=user_id,
        note=f'force_logout_one user={username or "<ukjent>"} by={request.user.username}',
    )
    return JsonResponse({'ok': True, 'username': username})


@admin_required
@require_http_methods(['POST'])
def admin_session_kill_all(request):
    """POST: nødbrems – avslutt alle aktive sesjoner unntatt admin sin egen.

    Krever at klient sender 'confirm=YES' for å unngå utilsiktet trigg.
    """
    if request.POST.get('confirm', '') != 'YES':
        return JsonResponse({'ok': False, 'error': 'Bekreftelse mangler'}, status=400)

    my_key = request.session.session_key
    qs = Session.objects.filter(expire_date__gt=timezone.now())
    if my_key:
        qs = qs.exclude(session_key=my_key)
    deleted = qs.count()
    qs.delete()
    _audit_session_kill(
        request,
        table_name='Session',
        record_id=0,
        note=f'force_logout_all count={deleted} by={request.user.username}',
    )
    return JsonResponse({'ok': True, 'deleted': deleted})


@admin_required
@require_http_methods(['POST'])
def admin_set_flag(request):
    """Endre feature-flag. Body: key, value."""
    key = request.POST.get('key', '').strip()
    value = request.POST.get('value', '').strip()

    # Kun kjente flagg kan endres via dette endepunktet
    allowed_keys = {FLAG_LIVE_STATS}
    if key not in allowed_keys:
        return JsonResponse({'ok': False, 'error': 'Ukjent flagg'}, status=400)

    if value not in ('true', 'false'):
        return JsonResponse({'ok': False, 'error': 'Ugyldig verdi'}, status=400)

    AppSetting.set(key, value)
    return JsonResponse({'ok': True, 'key': key, 'value': value})
