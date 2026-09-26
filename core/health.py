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
from dataclasses import dataclass

from django.core.cache import cache
from django.db import connections

from core.vask import vask
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


# ── Målingene: ett sted, to lesere (26. sep. 2026, E6) ─────────────────────
#
# Probene sto to ganger — her og i `core/admin_status.py` — og hadde glidd:
# server-status sjekket ikke at `SELECT 1` faktisk ga 1, og /healthz/ skrev
# «OperationalError: OperationalError». **Målingen er felles, framstillingen
# er leserens:** /healthz/ er offentlig og viser bare unntakstypen;
# server-status er admin og viser den vaskede meldingen.

@dataclass
class Maaling:
    ok: bool
    ms: float | None = None
    #: Unntaket, hvis proben kastet. Leseren velger hva som vises av det.
    unntak: Exception | None = None
    #: Svar som kom, men var feil — trygt å vise hvor som helst.
    avvik: str = ''

    def feiltekst(self, *, detaljert: bool) -> str:
        if self.unntak is not None:
            return vask(str(self.unntak), maks=200) if detaljert else type(self.unntak).__name__
        return self.avvik


def maal_db() -> Maaling:
    """`SELECT 1` mot `default`. Kaster aldri."""
    start = time.perf_counter()
    try:
        with connections['default'].cursor() as cur:
            cur.execute('SELECT 1')
            rad = cur.fetchone()
    except Exception as exc:   # noqa: BLE001 — proben skal aldri kaste
        return Maaling(False, unntak=exc)
    ms = (time.perf_counter() - start) * 1000
    if rad != (1,):
        return Maaling(False, ms, avvik='Uventet svar fra DB')
    return Maaling(True, ms)


def maal_cache() -> Maaling:
    """Skriv, les og slett en nøkkel. Kaster aldri.

    Nøkkelen er tilfeldig per kall, slik at to samtidige prober ikke kolliderer.
    """
    nokkel = f'_healthz_probe_{secrets.token_hex(8)}'
    verdi = secrets.token_hex(8)
    start = time.perf_counter()
    try:
        cache.set(nokkel, verdi, timeout=10)
        fikk = cache.get(nokkel)
        cache.delete(nokkel)
    except Exception as exc:   # noqa: BLE001
        return Maaling(False, unntak=exc)
    ms = (time.perf_counter() - start) * 1000
    if fikk != verdi:
        return Maaling(False, ms, avvik='Probe-verdi stemmer ikke')
    return Maaling(True, ms)


def _til_healthz(m: Maaling):
    """(ok, latency_ms: int|None, error: str) — formen /healthz/ svarer med."""
    return m.ok, (int(m.ms) if m.ms is not None else None), (
        '' if m.ok else m.feiltekst(detaljert=False))


def _check_db():
    return _til_healthz(maal_db())


def _check_cache():
    return _til_healthz(maal_cache())


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
