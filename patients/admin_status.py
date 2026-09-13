"""Admin server-status dashbord.

Gir admin innsyn i live serverbelastning:
- Requests/sek, responstid (snitt/P50/P95) og de tregeste stiene
- Antall aktive sesjoner
- Minnebruk (RSS nå og topp), disk på volumet, databasens svartid og
  tilkoblinger
- Tid siden siste backup, og offsite-kopien
- Vaktbildet: aktiv vakt, vaktlister i drift, siste utsending, oppdrag som
  venter
- Konfigsjekk (DEBUG, HTTPS, rate-limit, cache, e-post, offsite, versjon),
  innloggingsfeil siste time, cron-jobbenes siste kjøring
- Feature-flag-kontroll (fremtidig bruk)

Alle innhenterne skal tåle at delen de leser er nede — kortet viser feilen,
siden viser resten. Et statusdashbord som selv gir 500 når databasen er
treg, er borte akkurat når man trenger det.

Kun for admin-rollen.
"""
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.auth_decorators import admin_required
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
    """Minne for denne workeren: {'naa': RSS nå, 'topp': høyeste RSS i
    prosessens levetid}, i MB. `ru_maxrss` er toppen — den går aldri ned, så
    fram til 13. sep. 2026 viste kortet «minne» som bare kunne stige, og
    sa ingenting om hva prosessen holder på *nå*. Nå-verdien leses fra
    `/proc/self/status` (Linux — Railway); mangler den, står toppen alene."""
    ut = {'naa': None, 'topp': None}
    try:
        import resource
        # ru_maxrss er i KB på Linux, B på macOS. Vi antar Linux (Railway).
        ut['topp'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:
        pass
    try:
        with open('/proc/self/status', encoding='ascii') as f:
            for linje in f:
                if linje.startswith('VmRSS:'):
                    ut['naa'] = round(int(linje.split()[1]) / 1024, 1)
                    break
    except Exception:
        pass
    if ut['naa'] is None:
        ut['naa'] = ut['topp']
    return ut


def _get_session_count():
    """Tell aktive (ikke-utløpte) sesjoner."""
    try:
        from django.contrib.sessions.models import Session
        return Session.objects.filter(expire_date__gt=timezone.now()).count()
    except Exception:
        return None


def _get_last_backup_info():
    """Returner info om siste vellykkede backup, og om offsite-kopien.

    Backup-modellen lagrer KUN vellykkede kjøringer (mislykkede backups commitet
    aldri raden), så vi henter bare siste rad uten ekstra status-filter.
    Tidligere `filter(status='success')` traff aldri fordi feltet ikke finnes
    på modellen — da viste dashbordet alltid "Ingen backup funnet".

    `offsite` (13. sep. 2026) er `core.offsite.status()` gjort JSON-vennlig:
    volumet er første nett, bucketen det andre, og en opplasting som har
    feilet i stillhet i tre uker er nettopp det man skal se her.
    """
    try:
        latest = Backup.objects.order_by('-created_at').first()
        if not latest:
            ut = {'found': False}
        else:
            age = timezone.now() - latest.created_at
            ut = {
                'found': True,
                'created_at': latest.created_at.isoformat(),
                'age_minutes': int(age.total_seconds() / 60),
                'filename': latest.filename,
                'size_bytes': latest.size_bytes,
                'kind': latest.kind,
            }
    except Exception:
        ut = {'found': False}
    ut['offsite'] = _get_offsite_info()
    return ut


def _get_offsite_info():
    try:
        from core import offsite
        st = offsite.status()
        ok, feil = st['siste_ok'], st['siste_feil']
        return {
            'konfigurert': st['konfigurert'],
            'mangler': st['mangler'],
            'bucket': st['bucket'],
            'antall': st['antall'],
            'siste_ok_at': ok.sendt_at.isoformat() if ok and ok.sendt_at else None,
            'siste_ok_minutter': (int((timezone.now() - ok.sendt_at).total_seconds() / 60)
                                  if ok and ok.sendt_at else None),
            'siste_ok_fil': ok.backup_filnavn if ok else None,
            'siste_feil_at': feil.created_at.isoformat() if feil else None,
            'siste_feil': _scrub_secrets(feil.feil)[:200] if feil else None,
        }
    except Exception as exc:
        return {'konfigurert': None, 'error': _scrub_secrets(str(exc))[:200]}


def _get_disk():
    """Volumet backupene ligger på (`BACKUP_DIR`) — brukt/ledig/andel.
    Railway-volumet er fast størrelse, og et fullt volum stopper backupen
    uten at noe annet i portalen merker det."""
    try:
        import shutil
        from core.backup import get_backup_dir
        sti = get_backup_dir()
        st = shutil.disk_usage(sti)
        brukt = st.total - st.free
        backup_bytes = sum(p.stat().st_size for p in sti.iterdir() if p.is_file())
        return {
            'sti': str(sti),
            'total_mb': round(st.total / 1048576, 1),
            'brukt_mb': round(brukt / 1048576, 1),
            'ledig_mb': round(st.free / 1048576, 1),
            'brukt_prosent': round(100 * brukt / st.total, 1) if st.total else None,
            'backup_mb': round(backup_bytes / 1048576, 1),
        }
    except Exception as exc:
        return {'error': _scrub_secrets(str(exc))[:200]}


def _get_db_health():
    """Databasen: svarer den, hvor fort, og — på PostgreSQL — hvor mange
    tilkoblinger av maks. Tilkoblingstaket er den feilen som kommer først
    når WEB_WORKERS skrus opp under vakt."""
    from django.db import connection
    ut = {'vendor': connection.vendor, 'healthy': False, 'latency_ms': None,
          'tilkoblinger': None, 'maks_tilkoblinger': None}
    try:
        start = time.perf_counter()
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        ut['latency_ms'] = round((time.perf_counter() - start) * 1000, 2)
        ut['healthy'] = True
    except Exception as exc:
        ut['error'] = _scrub_secrets(str(exc))[:200]
        return ut
    if connection.vendor == 'postgresql':
        try:
            with connection.cursor() as cur:
                cur.execute('SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()')
                ut['tilkoblinger'] = cur.fetchone()[0]
                cur.execute("SELECT setting::int FROM pg_settings WHERE name = 'max_connections'")
                ut['maks_tilkoblinger'] = cur.fetchone()[0]
        except Exception as exc:
            ut['error'] = _scrub_secrets(str(exc))[:200]
    return ut


def _get_vaktbilde():
    """Det operative bildet: hvilken vakt portalen scoper til, hvilke
    vaktlister som er i drift, siste utsending av vaktlistefila, og hvor
    mange oppdrag som venter på tavla. Statusen sier «serveren svarer»;
    dette sier om det er noe å svare *for*."""
    ut = {}
    try:
        from patients.services import hent_aktiv_vakt
        vakt = hent_aktiv_vakt()
        ut['aktiv_vakt'] = {'id': vakt.pk, 'navn': vakt.navn, 'startet': vakt.startet.isoformat()}
    except Exception as exc:
        ut['aktiv_vakt'] = None
        ut['error'] = _scrub_secrets(str(exc))[:200]
    try:
        from vaktliste import choices as vl_choices
        from vaktliste.models import Utsending, Vaktliste
        ut['vaktlister_i_drift'] = [
            {'id': v.pk, 'vakt': v.vakt.navn,
             'siden': v.satt_i_drift_at.isoformat() if v.satt_i_drift_at else None}
            for v in Vaktliste.objects.filter(status=vl_choices.DRIFT).select_related('vakt')
        ]
        u = Utsending.objects.order_by('-created_at').first()
        ut['siste_utsending'] = None if u is None else {
            'tid': u.created_at.isoformat(),
            'minutter_siden': int((timezone.now() - u.created_at).total_seconds() / 60),
            'utloest': u.utloest,
            'antall_mottakere': len([m for m in (u.mottakere or '').replace(';', ',').split(',') if m.strip()]),
            'ok': not u.feil,
            'feil': (u.feil or '')[:200],
        }
    except Exception as exc:
        ut['vaktlister_i_drift'] = []
        ut['siste_utsending'] = None
        ut['error'] = _scrub_secrets(str(exc))[:200]
    try:
        from oppdrag import choices as op_choices
        from oppdrag.models import Oppdrag
        vakt_id = (ut.get('aktiv_vakt') or {}).get('id')
        tavla = Oppdrag.objects.filter(vakt_id=vakt_id, historikk_fra__isnull=True)
        ventende = tavla.filter(status=op_choices.VENTER, trenger_ressurs=False)
        eldste = ventende.order_by('created_at').first()
        ut['oppdrag'] = {
            'paa_tavla': tavla.count(),
            'ventende': ventende.count(),
            'trenger_ressurs': tavla.filter(trenger_ressurs=True).count(),
            'eldste_ventende_minutter': (int((timezone.now() - eldste.created_at).total_seconds() / 60)
                                         if eldste else None),
        }
    except Exception as exc:
        ut['oppdrag'] = None
        ut['error'] = _scrub_secrets(str(exc))[:200]
    return ut


def _get_konfig_sjekk():
    """Det som skal stå riktig i prod, lest av settings — ikke av env
    direkte, for det er settings viewene faktisk kjører med. Hver rad har
    `ok`, så kortet kan farge det som er feil rødt uten at klienten kjenner
    reglene. Reglene gjelder prod: lokalt vil DEBUG og HTTPS stå «feil»,
    og det er riktig."""
    from core.versjon import hent_versjon
    from django.core.cache import caches
    epost = _epost_transport()
    ver = hent_versjon()
    rader = [
        {'nokkel': 'DEBUG', 'verdi': str(settings.DEBUG), 'ok': not settings.DEBUG},
        {'nokkel': 'RATELIMIT_ENABLE', 'verdi': str(getattr(settings, 'RATELIMIT_ENABLE', True)),
         'ok': bool(getattr(settings, 'RATELIMIT_ENABLE', True))},
        {'nokkel': 'HTTPS (SECURE_SSL_REDIRECT)', 'verdi': str(getattr(settings, 'SECURE_SSL_REDIRECT', False)),
         'ok': bool(getattr(settings, 'SECURE_SSL_REDIRECT', False))},
        {'nokkel': 'ALLOWED_HOSTS', 'verdi': ', '.join(settings.ALLOWED_HOSTS),
         'ok': bool(settings.ALLOWED_HOSTS) and '*' not in settings.ALLOWED_HOSTS},
        {'nokkel': 'CSRF_TRUSTED_ORIGINS', 'verdi': ', '.join(settings.CSRF_TRUSTED_ORIGINS) or '(tom)',
         'ok': bool(settings.CSRF_TRUSTED_ORIGINS)},
        {'nokkel': 'Cache', 'verdi': getattr(settings, 'CACHE_BACKEND_NAME', 'unknown'),
         'ok': getattr(settings, 'CACHE_BACKEND_NAME', '') == 'redis'},
        {'nokkel': 'E-post', 'verdi': epost['transport'], 'ok': epost['transport'] == 'ahasend'},
        {'nokkel': 'ADMINS (feilvarsel)', 'verdi': f'{len(settings.ADMINS)} mottaker(e)',
         'ok': bool(settings.ADMINS)},
        {'nokkel': 'Offsite backup', 'verdi': 'konfigurert' if _offsite_konfigurert() else 'ikke konfigurert',
         'ok': _offsite_konfigurert()},
    ]
    return {'rader': rader, 'alle_ok': all(r['ok'] for r in rader),
            'versjon': {'bygg': ver.get('bygg'), 'dato': ver.get('dato').isoformat() if ver.get('dato') else None,
                        'kilde': ver.get('kilde')}}


def _offsite_konfigurert():
    try:
        from core import offsite
        return offsite.er_konfigurert()
    except Exception:
        return False


def _epost_transport():
    """Hvilken transport e-post faktisk går med. AHASend er den eneste som
    virker i prod (Railway sperrer SMTP); konsoll betyr at ingenting sendes."""
    backend = getattr(settings, 'EMAIL_BACKEND', '') or ''
    if 'AhaSend' in backend:
        transport = 'ahasend'
    elif 'smtp' in backend:
        transport = 'smtp'
    elif 'console' in backend:
        transport = 'console'
    elif 'locmem' in backend:
        transport = 'locmem'
    else:
        transport = backend.rsplit('.', 1)[-1] or 'ukjent'
    return {'transport': transport, 'backend': backend}


def _get_epost():
    """Transport + siste utsending av vaktlistefila, som er den e-posten
    portalen sender som betyr noe. Ingen prøvesending — et statuskort som
    sender e-post hvert 10. sekund er ikke et statuskort."""
    ut = _epost_transport()
    try:
        from vaktliste.models import Utsending
        siste_ok = Utsending.objects.filter(feil='').order_by('-created_at').first()
        siste = Utsending.objects.order_by('-created_at').first()
        ut['siste_ok_at'] = siste_ok.created_at.isoformat() if siste_ok else None
        ut['siste_feil'] = (siste.feil[:200] if siste and siste.feil else None)
        ut['siste_feil_at'] = siste.created_at.isoformat() if siste and siste.feil else None
    except Exception as exc:
        ut['error'] = _scrub_secrets(str(exc))[:200]
    return ut


def _get_innlogging(minutter=60):
    """Innloggingsbildet siste time, fra `LoginEvent`: feilede forsøk,
    hvor mange brukernavn og IP-er de kom fra, og feilede MFA-koder. Mange
    feil fra én IP er et angrep; mange feil fra mange brukere er et passord
    ingen husker etter ferien."""
    try:
        from accounts.models import LoginEvent
        siden = timezone.now() - timedelta(minutes=minutter)
        qs = LoginEvent.objects.filter(created_at__gte=siden)
        feilet = qs.filter(event_type=LoginEvent.EVENT_LOGIN, success=False)
        return {
            'vindu_minutter': minutter,
            'vellykkede': qs.filter(event_type=LoginEvent.EVENT_LOGIN, success=True).count(),
            'feilede': feilet.count(),
            'feilede_brukernavn': feilet.values('username_attempt').distinct().count(),
            'feilede_ip': feilet.exclude(ip=None).values('ip').distinct().count(),
            'mfa_feilet': qs.filter(event_type=LoginEvent.EVENT_MFA_VERIFY_FAILED).count(),
        }
    except Exception as exc:
        return {'error': _scrub_secrets(str(exc))[:200]}


def _get_cron():
    """Siste kjøring av de tre Railway-cron-jobbene, fra `core.kommando`.
    None betyr «aldri registrert» — enten har jobben ikke kjørt siden
    sporingen kom (13. sep. 2026), eller cron er ikke satt opp."""
    try:
        from core.kommando import siste_kjoringer
        ut = {}
        for navn, k in siste_kjoringer().items():
            if k is None:
                ut[navn] = None
                continue
            try:
                tid = datetime.fromisoformat(k['tid'])
                timer = round((timezone.now() - tid).total_seconds() / 3600, 1)
            except Exception:
                timer = None
            ut[navn] = {'tid': k.get('tid'), 'ok': k.get('ok'), 'melding': k.get('melding', ''),
                        'timer_siden': timer}
        return ut
    except Exception as exc:
        return {'error': _scrub_secrets(str(exc))[:200]}


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
        'memory': _get_memory_mb(),
        'active_sessions': _get_session_count(),
        'last_backup': _get_last_backup_info(),
        'worker_config': _get_worker_config(),
        'cache_health': _get_cache_health(),
        'db_health': _get_db_health(),
        'disk': _get_disk(),
        'tregeste': metrics_store.tregeste_stier(window_seconds=300),
        'vaktbilde': _get_vaktbilde(),
        'konfig': _get_konfig_sjekk(),
        'innlogging': _get_innlogging(),
        'cron': _get_cron(),
        'epost': _get_epost(),
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
