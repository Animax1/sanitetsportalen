"""Middleware for pasient-appen."""
import json
import os
import time
import threading
from collections import deque

from django.conf import settings

from .backup_scheduler import maybe_run_backup


class BackupSchedulerMiddleware:
    """Trigger sjekk av automatisk backup ved hver request.

    Throttlet internt til maks én sjekk per 60 sekund per prosess, og selve
    backup-operasjonen kjører i bakgrunnstråd – så request-latency påvirkes
    ikke merkbart.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Kjør ETTER respons slik at brukeren ikke merker noe
        try:
            maybe_run_backup()
        except Exception:
            # Backup skal aldri ta ned appen
            pass
        return response


# Content-Security-Policy (defense-in-depth mot XSS).
#
# Tillater:
#   - 'self' for egen origin
#   - cdn.jsdelivr.net og unpkg.com for Bootstrap/ikoner/QR-kode
#   - 'unsafe-inline' for style og script (appen har mye inline HTML/CSS)
#   - data: for bilder (QR-koder rendres som data-URL)
#
# Bemerk: 'unsafe-inline' reduserer effekten mot reflektert XSS, men siden
# all brukerdata escapes med escapeHtml() før innsetting i DOM, er dette
# akseptabelt som ekstra lag. CSP her hovedsakelig stopper eksterne
# ressurser fra ukjente domener.
_CSP_DIRECTIVES = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
    "img-src 'self' data:",
    "font-src 'self' https://cdn.jsdelivr.net data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
]
_CSP_HEADER = '; '.join(_CSP_DIRECTIVES)


class SecurityHeadersMiddleware:
    """Legger til sikkerhetsheadere som Django ikke setter automatisk.

    - Content-Security-Policy: begrenser hvilke ressurser som kan lastes
    - Referrer-Policy: begrenser hva som sendes til eksterne lenker
    - Permissions-Policy: slår av funksjoner vi ikke bruker
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault('Content-Security-Policy', _CSP_HEADER)
        response.setdefault('Referrer-Policy', 'same-origin')
        response.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(), payment=()',
        )
        return response


# ─────────────────────────────────────────────────────────────────────────────
# RequestMetricsMiddleware
#
# Samler inn et lett rullerende vindu av request-metrikker (in-memory per
# worker-prosess) som admin kan se på /admin/server-status/.
#
# Vi holder inntil MAX_SAMPLES siste requests i en deque – O(1) append og
# automatisk avkorting. Ingen database-skriving, ingen logging. Tråd-trygt
# via Lock.
#
# Ved 2 workers ser hver worker sitt eget vindu – det er greit, for å se
# helheten kan admin ev. laste to ganger, men snittene vil være representative.
# ─────────────────────────────────────────────────────────────────────────────

MAX_SAMPLES = 500  # ~ siste 500 requests per worker (lokal deque)

# FORBEDRINGER #15: Aggregert metrikker på tvers av workere
#
# Med 1 worker (lavkostnad-modus): lokal deque er nok, gir korrekte tall.
# Med 2+ workere (vakt-modus med Redis): hver worker skriver èn linje per
# request til en delt Redis-liste, og snapshot() aggregerer fra Redis.
#
# Designet faller gracefully tilbake til lokal deque hvis cache-backenden
# ikke er Redis (eller hvis Redis er nede). Ingen hard avhengighet.

_REDIS_KEY = 'metrics:requests'
_REDIS_MAX_SAMPLES = 5000  # ~ siste 5000 requests på tvers av alle workere
_REDIS_SAMPLE_TTL = 600    # rader eldre enn 10 min ryddes ved hver snapshot


def _redis_is_available():
    """Returnerer True hvis dagens cache-backend er Redis (vs LocMem).

    Brukes for å avgjøre om vi skal aggregere via Redis eller falle tilbake
    til lokal deque-snapshot.
    """
    backend_name = getattr(settings, 'CACHE_BACKEND_NAME', '').lower()
    return backend_name == 'redis'


class _MetricsStore:
    """In-memory ringbuffer for request-metrikker, med valgfri Redis-aggregering.

    Skriver alltid til lokal deque (rask, ingen avhengigheter).
    Hvis Redis er aktiv, skriver også dit — da leser snapshot() fra Redis
    for sann aggregering på tvers av workere. Faller tilbake til lokal
    deque hvis Redis er av eller utilgjengelig.
    """

    def __init__(self):
        self._samples = deque(maxlen=MAX_SAMPLES)
        self._lock = threading.Lock()
        self._start_time = time.time()

    def record(self, path, method, status, duration_ms):
        sample = {
            'ts': time.time(),
            'path': path,
            'method': method,
            'status': status,
            'duration_ms': duration_ms,
        }
        # 1) Skriv alltid til lokal deque — raskt, alltid tilgjengelig
        with self._lock:
            self._samples.append(sample)

        # 2) Hvis Redis er aktiv: skriv også dit for cluster-wide aggregering
        if _redis_is_available():
            try:
                self._record_to_redis(sample)
            except Exception:
                # Redis nede / problem? Bare lokal deque brukes ved snapshot —
                # ingen feilmelding skal forplante seg til request-pipelinen.
                pass

    def _get_redis_client(self):
        """Bygg en raw redis-klient mot REDIS_URL fra settings.

        Vi bruker `redis`-biblioteket direkte (som allerede er i requirements
        fordi Django >=4.0 sin RedisCache krever det) i stedet for django-redis,
        siden prosjektet bruker Django sin innebygde RedisCache-backend.

        Returnerer None hvis Redis ikke er konfigurert eller pakken mangler.
        """
        redis_url = getattr(settings, 'REDIS_URL', '') or ''
        if not redis_url:
            return None
        try:
            import redis  # noqa: WPS433
            return redis.Redis.from_url(redis_url, socket_timeout=2,
                                        socket_connect_timeout=2)
        except Exception:
            return None

    def _record_to_redis(self, sample):
        """Push én metrikk-rad til en delt Redis-liste.

        Bruker `redis`-bibliotekets raw client for å få LPUSH+LTRIM. Kapper
        listen til _REDIS_MAX_SAMPLES for å hindre ubegrenset minnebruk.
        """
        client = self._get_redis_client()
        if client is None:
            return
        # Pakk inn pid for å kunne se hvilken worker som genererte radden.
        payload = json.dumps({**sample, 'pid': os.getpid()}, separators=(',', ':'))
        # Pipeline: LPUSH ny rad + LTRIM til maks-størrelse, atomisk.
        pipe = client.pipeline()
        pipe.lpush(_REDIS_KEY, payload)
        pipe.ltrim(_REDIS_KEY, 0, _REDIS_MAX_SAMPLES - 1)
        pipe.expire(_REDIS_KEY, _REDIS_SAMPLE_TTL * 6)  # auto-purge når tomt
        pipe.execute()

    def _read_from_redis(self, window_seconds):
        """Les samples fra Redis nyere enn `window_seconds`.

        Returnerer liste med dict'er. Reiser ikke — returnerer [] ved feil.
        """
        client = self._get_redis_client()
        if client is None:
            return []
        try:
            raw = client.lrange(_REDIS_KEY, 0, _REDIS_MAX_SAMPLES - 1)
        except Exception:
            return []
        cutoff = time.time() - window_seconds
        out = []
        for item in raw:
            try:
                s = json.loads(item)
                if s.get('ts', 0) >= cutoff:
                    out.append(s)
            except (json.JSONDecodeError, ValueError):
                continue
        return out

    def snapshot(self, window_seconds=300):
        """Returner aggregert snapshot for siste `window_seconds`.

        Hvis Redis er aktiv: aggregerer på tvers av alle workere.
        Hvis Redis er av: bruker bare lokal deque (denne workerens tall).
        """
        # Hent samples — primært fra Redis hvis tilgjengelig, ellers lokal deque.
        recent = []
        source = 'local'
        if _redis_is_available():
            redis_samples = self._read_from_redis(window_seconds)
            if redis_samples:
                recent = redis_samples
                source = 'redis'

        if not recent:
            # Fall tilbake til lokal deque (både hvis Redis er av og hvis Redis var tom)
            cutoff = time.time() - window_seconds
            with self._lock:
                recent = [s for s in self._samples if s['ts'] >= cutoff]
            source = 'local' if source != 'redis' else 'redis'

        if not recent:
            return {
                'window_seconds': window_seconds,
                'count': 0,
                'rps': 0.0,
                'avg_ms': 0.0,
                'p50_ms': 0.0,
                'p95_ms': 0.0,
                'max_ms': 0.0,
                'errors_5xx': 0,
                'errors_4xx': 0,
                'uptime_seconds': int(time.time() - self._start_time),
                'pid': os.getpid(),
                'sample_size': 0,
                'source': source,
            }

        durations = sorted(s['duration_ms'] for s in recent)
        n = len(durations)

        def pct(p):
            idx = max(0, min(n - 1, int(round(p * (n - 1)))))
            return durations[idx]

        # Tell unike PIDs i samples — nyttig for å verifisere at aggregering virker
        unique_pids = len({s.get('pid') for s in recent if 'pid' in s})

        return {
            'window_seconds': window_seconds,
            'count': n,
            'rps': round(n / window_seconds, 2),
            'avg_ms': round(sum(durations) / n, 1),
            'p50_ms': round(pct(0.50), 1),
            'p95_ms': round(pct(0.95), 1),
            'max_ms': round(durations[-1], 1),
            'errors_5xx': sum(1 for s in recent if 500 <= s['status'] < 600),
            'errors_4xx': sum(1 for s in recent if 400 <= s['status'] < 500),
            'uptime_seconds': int(time.time() - self._start_time),
            'pid': os.getpid(),
            'sample_size': len(self._samples),
            'source': source,           # 'redis' = aggregert over alle workere; 'local' = bare denne
            'unique_workers': unique_pids,  # antall workere som bidro til snapshot
        }

    def reset(self):
        """Kun for tester."""
        with self._lock:
            self._samples.clear()
            self._start_time = time.time()
        # Rydd også Redis-listen hvis den er aktiv (best-effort)
        if _redis_is_available():
            try:
                client = self._get_redis_client()
                if client is not None:
                    client.delete(_REDIS_KEY)
            except Exception:
                pass


# Modul-global, én per worker-prosess
metrics_store = _MetricsStore()


class RequestMetricsMiddleware:
    """Måler varighet på hver request og lagrer i rullerende vindu.

    Lagrer kun duration + status + path + method – ingen sensitive data.
    Ingen I/O. Trygt under peak.

    Ignorerer statiske filer og selve status-endepunktet for å unngå støy.
    """

    _SKIP_PREFIXES = ('/static/', '/media/')
    _SKIP_EXACT = (
        '/portal-admin/server-status/',
        '/portal-admin/server-status/json/',
        '/healthz/',  # #2: hyppige health-checks skal ikke støye metrikkene
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path in self._SKIP_EXACT or path.startswith(self._SKIP_PREFIXES):
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000.0

        try:
            metrics_store.record(
                path=path[:100],  # truncate lang query string
                method=request.method,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        except Exception:
            # Metrics skal aldri ta ned appen
            pass

        return response
