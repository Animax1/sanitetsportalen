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

Alle innhenterne skal tåle at delen de leser er nede — kortet viser feilen,
siden viser resten. Et statusdashbord som selv gir 500 når databasen er
treg, er borte akkurat når man trenger det.

Kun for admin-rollen.
"""
import json
import os
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
from core.klientip import klient_ip
from core.sesjoner import aktive_sesjoner
# `_scrub_secrets` står igjen som navn for de mange kallstedene her; den
# offentlige er `core.vask.vask` (B7). Å døpe om kallstedene er E6.
from core.vask import vask as _scrub_secrets
from audit.models import AuditLog

from .middleware import metrics_store
from core.models import Backup


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
    try:
        ut['sortering'] = _db_sortering(connection)
    except Exception as exc:
        ut['sortering'] = {'feil': _scrub_secrets(str(exc))[:200]}
    if connection.vendor == 'postgresql':
        try:
            with connection.cursor() as cur:
                cur.execute('SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()')
                ut['tilkoblinger'] = cur.fetchone()[0]
                cur.execute("SELECT setting::int FROM pg_settings WHERE name = 'max_connections'")
                ut['maks_tilkoblinger'] = cur.fetchone()[0]
        except Exception as exc:
            ut['error'] = _scrub_secrets(str(exc))[:200]
        # Egen `try`: feiler den nye spørringen, skal svartid og tilkoblinger
        # fortsatt stå — samme regel som hver innhenter på dashbordet.
        try:
            ut.update(_db_aktivitet(connection))
            ut['signaler'] = db_signaler(ut)
        except Exception as exc:
            ut['aktivitet_feil'] = _scrub_secrets(str(exc))[:200]
    return ut


# ── Hvordan basen sorterer Æ, Ø og Å (26. sep. 2026) ─────────────────────────
#
# Rekkefølgen i nedtrekkene er databasens kollasjon, og den er ikke den samme
# overalt: en_US leser Æ som AE, Ø som O og Å som A; C legger dem sist, men
# som Å, Æ, Ø. CI viste forskjellen, og ingen kunne se hva prod gjør uten
# SQL-tilgang. Kortet viser derfor **svaret, ikke innstillingen** — på en
# ICU-base sier `datcollate` «C.UTF-8» mens sorteringen er en_US.
#
# Fra samme dag sorterer portalen selv norsk (`core/sortering.py`), og raden
# viser **portalens** svar. Basens eget står under: blir portalens rad gul, er
# den norske kollasjonen borte og `Norsk` har falt tilbake til basens.

#: «bergen» med liten b: prøven skal også avsløre en sortering uten `lower()`,
#: som ville satt små bokstaver etter alle store.
SORTERINGSPROVE = ('Oslo', 'Ørsta', 'Ærø', 'Ålesund', 'bergen', 'Zeta')
SORTERING_NORSK = ('bergen', 'Oslo', 'Zeta', 'Ærø', 'Ørsta', 'Ålesund')
#: Kodepunktorden: Æ, Ø og Å sist, men Å (U+00E5) før Æ (U+00E6).
SORTERING_KODEPUNKT = ('bergen', 'Oslo', 'Zeta', 'Ålesund', 'Ærø', 'Ørsta')


def sortering_vurdering(rekkefolge) -> str:
    """`norsk`, `kodepunkt` (sist, feil innbyrdes) eller `blandet` (inne
    blant de andre bokstavene — en_US)."""
    rekkefolge = tuple(rekkefolge)
    if rekkefolge == SORTERING_NORSK:
        return 'norsk'
    if rekkefolge == SORTERING_KODEPUNKT:
        return 'kodepunkt'
    return 'blandet'


def _db_sortering(connection) -> dict:
    """Sorterer prøvenavnene to ganger: slik **portalen** gjør (`Norsk`, se
    `core/sortering.py`) og slik **basen alene** gjør (`lower()` med basens
    standardkollasjon, som portalen brukte fram til 26. sep. 2026). Den første
    er raden; den andre sier hvorfor den trengs."""
    from core.sortering import norsk_sql, norsk_tilgjengelig

    utvalg = ' UNION ALL '.join(['SELECT %s AS n'] * len(SORTERINGSPROVE))

    def sorter(uttrykk):
        with connection.cursor() as cur:
            cur.execute(f'SELECT n FROM ({utvalg}) AS prove ORDER BY {uttrykk}', list(SORTERINGSPROVE))
            return [rad[0] for rad in cur.fetchall()]

    portalen = sorter(norsk_sql(connection, 'n'))
    basen = sorter('lower(n)')
    kollasjon = versjon = None
    if connection.vendor == 'postgresql':
        with connection.cursor() as cur:
            cur.execute("SELECT datcollate, current_setting('server_version') "
                        "FROM pg_database WHERE datname = current_database()")
            kollasjon, versjon = cur.fetchone()
    return {'rekkefolge': portalen, 'vurdering': sortering_vurdering(portalen),
            'basen': basen, 'basen_vurdering': sortering_vurdering(basen),
            'norsk_regel': norsk_tilgjengelig(connection),
            'kollasjon': kollasjon, 'versjon': versjon}


# ── Databasen under vakt (25. sep. 2026, skisse «Databasekortet») ────────────
#
# Svartid og tilkoblinger kan stå grønne mens alt står stille: én transaksjon
# som holder en lås, og forespørslene i kø bak den. Tre tall svarer på «er det
# databasen som er problemet akkurat nå?». Hentes hvert 10. sekund med resten.

#: «Idle in transaction» kortere enn dette er normalt midt i en lagring.
DB_HENGER_ETTER_S = 5
#: Så lenge før en åpen transaksjon er rød — den holder trolig en lås.
DB_HENGER_ROD_S = 30

_DB_AKTIVITET_SQL = """
    SELECT
      count(*) FILTER (WHERE state = 'active'),
      count(*) FILTER (WHERE state = 'idle'),
      count(*) FILTER (WHERE state IN ('idle in transaction', 'idle in transaction (aborted)')
                         AND now() - state_change > make_interval(secs => %s)),
      count(*) FILTER (WHERE state IN ('idle in transaction', 'idle in transaction (aborted)')
                         AND now() - state_change > make_interval(secs => %s)),
      count(*) FILTER (WHERE wait_event_type = 'Lock'),
      coalesce(extract(epoch FROM max(now() - xact_start)), 0)
    FROM pg_stat_activity
    WHERE datname = current_database()
      AND backend_type = 'client backend'
      AND pid <> pg_backend_pid()
"""


def _db_aktivitet(connection) -> dict:
    """Tilkoblingene etter tilstand, eldste åpne transaksjon og låskø — fra
    appens egne tilkoblinger. Dashbordets egen og Postgres' bakgrunnsprosesser
    (autovacuum, WAL) er ikke med: de er ikke det som får en side til å henge."""
    with connection.cursor() as cur:
        cur.execute(_DB_AKTIVITET_SQL, [DB_HENGER_ETTER_S, DB_HENGER_ROD_S])
        arbeider, ledige, henger, henger_lenge, venter, eldste = cur.fetchone()
        cur.execute('SELECT deadlocks, stats_reset FROM pg_stat_database WHERE datname = current_database()')
        deadlocks, nullstilt = cur.fetchone()
    return {'arbeider': arbeider, 'ledige': ledige, 'henger': henger, 'henger_lenge': henger_lenge,
            'venter_laas': venter, 'eldste_s': round(float(eldste), 1), 'deadlocks': deadlocks,
            'stats_reset': nullstilt.isoformat() if nullstilt else None}


_RANG = {'gronn': 0, 'gul': 1, 'oransje': 2, 'rod': 3}


def db_signaler(d) -> dict:
    """Nivået per rad og samlet — **regelen, ikke tegningen**, så kortet og
    beredskapstrinnet leser det samme. Grensene står i skissen og runbook §8;
    de justeres etter første vakt med tall, som tersklene i §2."""
    henger = d.get('henger') or 0
    eldste = d.get('eldste_s') or 0
    venter = d.get('venter_laas') or 0
    per = {
        'henger': 'rod' if henger >= 3 or (d.get('henger_lenge') or 0) >= 1 else ('gul' if henger else 'gronn'),
        'eldste': 'rod' if eldste > DB_HENGER_ROD_S else ('gul' if eldste >= DB_HENGER_ETTER_S else 'gronn'),
        'venter_laas': 'rod' if venter >= 3 else ('gul' if venter else 'gronn'),
        # Siden forrige `pg_stat_reset()` — runbook §8a nullstiller før vakt.
        'deadlocks': 'gul' if (d.get('deadlocks') or 0) else 'gronn',
    }
    return dict(per, samlet=max(per.values(), key=_RANG.get))


def _get_vaktbilde():
    """Det operative bildet: hvilken vakt portalen scoper til, hvilke
    vaktlister som er i drift, siste utsending av vaktlistefila, og hvor
    mange oppdrag som venter på tavla. Statusen sier «serveren svarer»;
    dette sier om det er noe å svare *for*."""
    from core.driftstatus import samle

    ut = {}
    vakt = None
    try:
        from core.vakt import hent_aktiv_vakt
        vakt = hent_aktiv_vakt()
        ut['aktiv_vakt'] = {'id': vakt.pk, 'navn': vakt.navn,
                            'startet': vakt.startet.isoformat()}
    except Exception as exc:
        ut['aktiv_vakt'] = None
        ut['error'] = _scrub_secrets(str(exc))[:200]

    # **Modulenes tall kommer gjennom registeret, ikke gjennom en import.**
    # Fram til 14. sep. 2026 sto `from vaktliste.models import ...` og
    # `from oppdrag.models import ...` her. Se `core/driftstatus.py` for
    # hvorfor retningen betyr noe.
    #
    # Standardverdiene står her og ikke i handlerne: er en modul slått av
    # eller ikke registrert, skal kortet vise «–» og ikke forsvinne. Nøklene
    # er de klienten leser, og de skal finnes uansett.
    ut.setdefault('vaktlister_i_drift', [])
    ut.setdefault('siste_utsending', None)
    ut.setdefault('oppdrag', None)

    verdier, feil = samle('vaktbilde', vakt)
    ut.update(verdier)
    if feil:
        ut['error'] = feil
    return ut


def _get_konfig_sjekk():
    """Det som skal stå riktig i prod, lest av settings — ikke av env
    direkte, for det er settings viewene faktisk kjører med. Hver rad har
    `ok`, så kortet kan farge det som er feil rødt uten at klienten kjenner
    reglene. Reglene gjelder prod: lokalt vil DEBUG og HTTPS stå «feil»,
    og det er riktig."""
    from core.versjon import hent_versjon
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
    from core.driftstatus import samle

    ut = _epost_transport()
    verdier, feil = samle('epost')
    ut.update(verdier)
    if feil:
        ut['error'] = feil
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


def _get_backupklokke():
    """Backup-klokka: lever tråden, og når tikket den sist?

    Står **ikke** blant cron-jobbene, for den er ingen cron-jobb — klokka er
    en tråd i web-prosessen, fordi Railway-volumet bare kan henge på én
    tjeneste og det er denne. En tråd er ikke synlig i Railways grensesnitt
    slik en cron-tjeneste er, så dette kortet er det eneste stedet man ser at
    den gjør jobben sin.
    """
    try:
        from core.backup.klokke import vakthund
        from core.models import Backupplan

        siste = (Backupplan.objects.exclude(sist_sjekket_at=None)
                 .order_by('-sist_sjekket_at')
                 .values_list('sist_sjekket_at', flat=True).first())
        forsinket = vakthund()
        return {
            'siste_tikk': siste.isoformat() if siste else None,
            'minutter_siden': (
                None if siste is None
                else int((timezone.now() - siste).total_seconds() // 60)),
            'forsinkede': [r['slug'] for r in forsinket],
            'ok': not forsinket,
        }
    except Exception as exc:   # noqa: BLE001 — et kort som feiler er borte
        return {'error': _scrub_secrets(str(exc))[:200]}


def _get_cron():
    """Siste kjøring av Railway-cron-jobbene, fra `core.kommando`.
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


# ── Beredskapstrinnene (24. sep. 2026) ────────────────────────────────────
#
# **Ett sted for tersklene og tiltakene.** De sto skrevet to steder — i
# `docs/RUNBOOK_VAKT.md` §2 og i hurtigreferansen nederst på dashbordet — og
# begge regnet fra 1 worker, mens vakt-modus starter på 2 (André: «før vakten
# skal starte spinner vi opp redis og 2 workers og 4 tråder», og Railway Pro
# på vakt). «Oransje: oppgrader til 2 workers» var da et tiltak som alt var
# gjort. Dashbordet tegner tabellen herfra, og `BeredskapstrinneneIRunbookenTests`
# holder §2 i takt.

#: Grunnlinja på vakt. Tiltakene under regnes fra denne.
VAKTMODUS = {'workers': 2, 'threads': 4, 'cache': 'redis', 'plan': 'Pro'}

#: Trinnene, i rekkefølge. `p95_fra` og `feil_5xx_fra` er nedre grense for
#: trinnet — det høyeste trinnet der én av dem er nådd, gjelder. `workers` er
#: hva `WEB_WORKERS` skal settes til, eller `None` når tiltaket ikke er flere.
BEREDSKAPSTRINN = (
    {'nivaa': 'gronn', 'navn': 'Grønt', 'p95_fra': 0, 'feil_5xx_fra': None, 'workers': None,
     'terskel': '< 300 ms, 0 feil',
     'tiltak': 'Ingen endring. Fortsett å observere.'},
    {'nivaa': 'gul', 'navn': 'Gult', 'p95_fra': 300, 'feil_5xx_fra': None, 'workers': None,
     'terskel': '300–500 ms, 0 feil',
     'tiltak': 'Observer, og se «Tregeste stier». Varer det over 15 min: be om at faner som '
               'ikke brukes lukkes, og logg ut sesjoner som har vært inaktive over én time.'},
    {'nivaa': 'oransje', 'navn': 'Oransje', 'p95_fra': 500, 'feil_5xx_fra': 1, 'workers': 3,
     'terskel': '500–1000 ms, eller 1–2 5xx',
     'tiltak': 'Se «Tregeste stier» og «Database» først — er databasen treg, hjelper ikke '
               'flere workers (§8). Ellers WEB_WORKERS=3.'},
    {'nivaa': 'rod', 'navn': 'Rødt', 'p95_fra': 1000, 'feil_5xx_fra': 3, 'workers': 4,
     'terskel': '> 1000 ms, eller ≥ 3 5xx',
     'tiltak': 'WEB_WORKERS=4. Faller ikke P95 innen 3 min, er flaskehalsen noe annet enn '
               'workers — se «Database» og Railway-loggen.'},
)

#: **Tråder er et annet verktøy enn workers, ikke et trinn over dem** (runbook §5,
#: André 24. sep. 2026: «tråder gir kjappere database?»). De gjør ikke databasen
#: raskere — de lar appen sende flere spørringer samtidig. Det hjelper bare når
#: appen venter på seg selv: lav CPU, rask database, likevel høy P95. Er det
#: databasen som er treg, gir flere tråder mer trykk på flaskehalsen.
TRADER_VED_VENTING = 6
TRAADREGEL = (f'Lav CPU i Railway (Metrics) og rask database, men likevel høy P95? Da venter appen '
              f'på seg selv: WEB_THREADS={TRADER_VED_VENTING} i stedet for flere workers (runbook §5). '
              'Er det databasen som er treg, gjør flere tråder det verre.')

#: Siste utvei, ikke et trinn dashbordet setter selv: det krever at tiltakene
#: over er prøvd.
KRITISK = {'navn': 'Kritisk', 'terskel': 'Fortsatt tregt etter alle tiltak',
           'tiltak': 'Last-shed (§9): papir for pasienter, nødnett for oppdrag. '
                     '«Logg ut alle» bare når ingen registrerer.'}


#: Under så mange forespørsler siste 5 min er P95 i praksis den tregeste
#: enkeltforespørselen — tre treff og én treg side gir «Oransje» (sett på
#: dashbordet 24. sep. 2026). Trinnet står, men kortet sier at det er tynt.
FA_MAALINGER = 20


def beredskapsnivaa(p95_ms, feil_5xx, antall=None) -> dict:
    """Trinnet P95 og 5xx siste 5 min gir. Det høyeste trinnet der én av de
    to har nådd grensen, gjelder — 5xx alene kan gi rødt.

    `fa_maalinger` er sann når `antall` er kjent og under `FA_MAALINGER`: da
    står trinnet, men det er ikke noe å handle på ennå. 5xx er likevel 5xx."""
    p95 = p95_ms or 0
    feil = feil_5xx or 0
    gjeldende = BEREDSKAPSTRINN[0]
    for trinn in BEREDSKAPSTRINN:
        if p95 >= trinn['p95_fra'] or (trinn['feil_5xx_fra'] is not None and feil >= trinn['feil_5xx_fra']):
            gjeldende = trinn
    fa = antall is not None and antall < FA_MAALINGER and not feil
    return dict(gjeldende, fa_maalinger=fa, antall=antall)


#: Tiltaket når databasen løfter trinnet. Workers-tiltaket i oransje og rødt er
#: feil her: en lås blir ikke borte av flere prosesser som venter på den.
DB_TILTAK = ('Databasen: en transaksjon henger, eller forespørsler venter på lås. Flere workers '
             'hjelper ikke — se «Database» og runbook §8.')


def beredskap_med_databasen(trinn, db) -> dict:
    """**Rødt databasekort løfter trinnet til minst Oransje** (André, 25. sep.
    2026). P95 stiger først når en hengende lås alt har rammet alle; kortet
    ser det før. Tiltaket byttes ut, også når P95 alene ga rødt — den som øker
    workers for en lås, gjør køen lengre."""
    sig = (db or {}).get('signaler') or {}
    if sig.get('samlet') != 'rod':
        return trinn
    ut = dict(trinn)
    if _RANG[ut['nivaa']] < _RANG['oransje']:
        oransje = next(t for t in BEREDSKAPSTRINN if t['nivaa'] == 'oransje')
        ut.update({k: oransje[k] for k in ('nivaa', 'navn', 'terskel', 'workers')})
    ut.update(tiltak=DB_TILTAK, fa_maalinger=False, grunn='database')
    return ut


def _heltall_fra_env(verdi, standard):
    """`WEB_WORKERS` kan stå som «1 (default)» fra `_get_worker_config`."""
    try:
        return int(str(verdi).split()[0])
    except (ValueError, IndexError):
        return standard


def driftsmodus(worker_config, cache_health) -> dict:
    """Står appen i vakt-modus, lavkostnad-modus — eller i noe midt imellom
    som ikke skal kjøres? Runbook §1b. **2+ workers uten virkende Redis er en
    feil**, ikke en modus: rate-limit og cache blir per prosess (§4)."""
    workers = _heltall_fra_env((worker_config or {}).get('workers'), 1)
    ch = cache_health or {}
    redis_ok = ch.get('backend') == 'redis' and ch.get('healthy') is True
    if workers >= 2 and not redis_ok:
        return {'modus': 'feil', 'ok': False,
                'tekst': f'{workers} workers uten virkende Redis — rate-limit og cache deles ikke. '
                         'Aktiver Redis, eller sett WEB_WORKERS=1.'}
    if workers >= VAKTMODUS['workers']:
        return {'modus': 'vakt', 'ok': True, 'tekst': f'Vakt-modus: {workers} workers, Redis OK'}
    if redis_ok:
        return {'modus': 'halvveis', 'ok': True,
                'tekst': 'Redis er på, men bare 1 worker — sett WEB_WORKERS=2 før vakt (§1c).'}
    return {'modus': 'lavkostnad', 'ok': True, 'tekst': 'Lavkostnad-modus (mellom vakter)'}


def metrikkilde(snapshot, worker_config) -> dict:
    """Hvor tallene på dashbordet kommer fra. Med flere workers og uten
    Redis er de bare denne workerens — da skal kortet si det."""
    workers = _heltall_fra_env((worker_config or {}).get('workers'), 1)
    snap = snapshot or {}
    if snap.get('source') == 'redis':
        n = snap.get('unique_workers')
        return {'ok': True, 'tekst': f'Samlet fra {n} workers' if n else 'Samlet fra alle workers'}
    if workers >= 2:
        return {'ok': False, 'tekst': 'Bare denne workeren — ikke hele appen'}
    return {'ok': True, 'tekst': 'Én worker'}


def _build_status_payload():
    """Samle alle status-data i én dict."""
    m5 = metrics_store.snapshot(window_seconds=300)
    workers = _get_worker_config()
    cache_helse = _get_cache_health()
    db_helse = _get_db_health()
    return {
        'beredskap': beredskap_med_databasen(
            beredskapsnivaa(m5.get('p95_ms'), m5.get('errors_5xx'), m5.get('count')), db_helse),
        'driftsmodus': driftsmodus(workers, cache_helse),
        'metrikkilde': metrikkilde(m5, workers),
        'timestamp': timezone.now().isoformat(),
        'metrics_5min': m5,
        'metrics_1min': metrics_store.snapshot(window_seconds=60),
        'memory': _get_memory_mb(),
        'active_sessions': _get_session_count(),
        'last_backup': _get_last_backup_info(),
        'worker_config': workers,
        'cache_health': cache_helse,
        'db_health': db_helse,
        'disk': _get_disk(),
        'tregeste': metrics_store.tregeste_stier(window_seconds=300),
        'vaktbilde': _get_vaktbilde(),
        'konfig': _get_konfig_sjekk(),
        'innlogging': _get_innlogging(),
        'cron': _get_cron(),
        'backupklokke': _get_backupklokke(),
        'epost': _get_epost(),
    }


@admin_required
def admin_status_view(request):
    """HTML-dashbord for admin."""
    payload = _build_status_payload()
    return render(request, 'patients/admin_status.html', {
        'payload': payload,
        'trinn': BEREDSKAPSTRINN,
        'kritisk': KRITISK,
        'traadregel': TRAADREGEL,
        'vaktmodus': VAKTMODUS,
        'payload_json': json.dumps(payload, indent=2, ensure_ascii=False),
    })


@admin_required
def admin_status_json(request):
    """JSON-endepunkt for polling fra dashbord."""
    return JsonResponse(_build_status_payload())


# ── Sesjonshåndtering ─────────────────────────────────────────────────────────────────
# Lar admin se og avslutte aktive brukersesjoner under høy last.

def _list_active_sessions():
    """Adminflatens projeksjon av `core.sesjoner.aktive_sesjoner()`.

    Loopen som dekoder sesjonstabellen bor i `core/sesjoner.py` siden
    17. sep. 2026, fordi KO-sidebaren trenger den samme (`FORSLAG_KO.md` §5.3)
    og to kopier er to kilder som glir fra hverandre. **Projeksjonen er
    fortsatt adminflatens egen**, og det er meningen: `session_key` er
    håndtaket `admin_session_kill` avslutter en sesjon med, og det hører bare
    hjemme her.
    """
    sessions = [{
        'session_key': rad['session_key'],
        'user_id': bruker.id,
        'username': bruker.username,
        'role': getattr(bruker, 'role', '') or '',
        'expire_date': rad['expire_date'],
        # **Alle påloggede vises, også de inaktive** (André, 16. sep. 2026:
        # «jeg må fortsatt se alle som er innlogget»). Aktiviteten er en
        # *kolonne*, ikke et filter — en fane som har stått i to timer er
        # nettopp den man leter etter, og et filter ville skjult den.
        'inaktiv_s': rad['inaktiv_s'],
    } for bruker, rad in aktive_sesjoner()]
    # Sorter alfabetisk på brukernavn for stabilt UI
    sessions.sort(key=lambda s: s['username'].lower())
    return sessions


def _audit_session_kill(request, table_name, record_id, note):
    """Loggfør tvungen utlogging i AuditLog."""
    try:
        ip = klient_ip(request)
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
