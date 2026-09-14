"""Health-endepunkt for Railway og eksterne overvåkingstjenester.

Forbedring #2 (mai 2026): Et lett endepunkt som svarer raskt og uten auth.
Returnerer:
  - HTTP 200 hvis DB og cache fungerer
  - HTTP 200 med advarsel hvis cache er degradert (vi vil fortsatt at appen
    skal regnes som "live" siden funksjonalitet kan kjøre uten cache)
  - HTTP 503 hvis DB ikke svarer (appen er reelt nede)

Endepunktet er bevisst minimalt: én SELECT 1 mot DB, én probe mot cache.
Ingen pasient-data eksponeres. Ingen credentials lekkes (cache-feil scrubes).
"""
import logging
import os
import secrets
import time

from django.core.cache import cache
from django.db import connections, OperationalError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


def _check_db():
    """Returner (ok: bool, latency_ms: int|None, error: str)."""
    start = time.monotonic()
    try:
        conn = connections['default']
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
            row = cur.fetchone()
        latency_ms = int((time.monotonic() - start) * 1000)
        if row != (1,):
            return False, latency_ms, 'Uventet svar fra DB'
        return True, latency_ms, ''
    except OperationalError as exc:
        return False, None, f'OperationalError: {type(exc).__name__}'
    except Exception as exc:
        # Generisk fallback — vi vil ikke at health-endepunktet selv kaster
        return False, None, f'{type(exc).__name__}'


def _check_cache():
    """Returner (ok: bool, latency_ms: int|None, error: str).

    Skriver, leser og sletter en probe-nøkkel. Probe-key er tilfeldig per kall
    slik at to samtidige health-checks ikke kolliderer.
    """
    probe_key = f'_healthz_probe_{secrets.token_hex(8)}'
    probe_value = secrets.token_hex(8)
    start = time.monotonic()
    try:
        cache.set(probe_key, probe_value, timeout=10)
        got = cache.get(probe_key)
        cache.delete(probe_key)
        latency_ms = int((time.monotonic() - start) * 1000)
        if got != probe_value:
            return False, latency_ms, 'Probe-verdi stemmer ikke'
        return True, latency_ms, ''
    except Exception as exc:
        # Cache-feil skal ikke ta ned health-endepunktet
        return False, None, f'{type(exc).__name__}'


@csrf_exempt
@require_safe
@never_cache
def healthz(request):
    """Lightweight health check for Railway / eksterne monitorer.

    URL: /healthz/
    Auth: ingen — fritatt fra alle login-decoratorer.

    Respons-format::

        {
          "status": "ok" | "degraded" | "error",
          "db": {"ok": true, "latency_ms": 3},
          "cache": {"ok": true, "latency_ms": 1, "backend": "redis"},
          "version": "<git-sha-7>"
        }

    HTTP-koder:
      - 200 hvis DB ok (selv om cache feiler — appen er fortsatt brukbar)
      - 503 hvis DB feiler

    Begrunnelse for 200 ved cache-feil: I lavkostnad-modus bruker vi LocMemCache
    som alltid fungerer. I vakt-modus bruker vi Redis, men metrikk- og
    rate-limit-koden har fallback til lokal state. Cache-feil er degradering,
    ikke nedetid.
    """
    db_ok, db_lat, db_err = _check_db()
    cache_ok, cache_lat, cache_err = _check_cache()

    # Backend-navn fra settings (satt i settings.py basert på REDIS_URL)
    from django.conf import settings
    cache_backend = getattr(settings, 'CACHE_BACKEND_NAME', 'unknown')

    # Versjons-info fra Railway (RAILWAY_GIT_COMMIT_SHA settes automatisk)
    sha = os.environ.get('RAILWAY_GIT_COMMIT_SHA', '')
    version = sha[:7] if sha else 'unknown'

    if not db_ok:
        status = 'error'
        http_status = 503
    elif not cache_ok:
        status = 'degraded'
        http_status = 200
    else:
        status = 'ok'
        http_status = 200

    payload = {
        'status': status,
        'db': {
            'ok': db_ok,
            **({'latency_ms': db_lat} if db_lat is not None else {}),
            **({'error': db_err} if db_err else {}),
        },
        'cache': {
            'ok': cache_ok,
            'backend': cache_backend,
            **({'latency_ms': cache_lat} if cache_lat is not None else {}),
            **({'error': cache_err} if cache_err else {}),
        },
        'version': version,
    }

    if status == 'error':
        # Logg degraderte svar (ikke ok-statuser, det blir for mye støy)
        logger.warning('healthz: %s db=%s cache=%s', status, db_err or 'ok', cache_err or 'ok')

    return JsonResponse(payload, status=http_status)
