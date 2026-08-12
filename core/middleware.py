import logging
import time

# `resource` finnes kun på Unix. Produksjon (Railway) og offline-Linux har den,
# men lokal utvikling og testkjøring på Windows har det ikke — og siden denne
# middlewaren står ubetinget i MIDDLEWARE, ville en hard import gjort at hver
# eneste HTTP-test feiler på Windows. Vi degraderer i stedet til ren
# responstid-logging der minnemåling ikke er tilgjengelig.
try:
    import resource
except ImportError:  # pragma: no cover – plattformavhengig
    resource = None

log = logging.getLogger('memory')


def _max_rss_kb():
    """Maks RSS i kB, eller None på plattformer uten `resource`."""
    if resource is None:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


class MemoryLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        mem_before = _max_rss_kb()
        t0 = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - t0) * 1000
        mem_after = _max_rss_kb()

        if mem_before is None or mem_after is None:
            # Uten minnemåling logger vi kun trege requests.
            if duration_ms > 200:
                log.info(
                    'mem path=%s status=%s dur=%.0fms rss=n/a',
                    request.path, response.status_code, duration_ms,
                )
            return response

        delta = mem_after - mem_before
        if duration_ms > 200 or delta > 1024:
            log.info(
                'mem path=%s status=%s dur=%.0fms rss=%dkB delta=%+dkB',
                request.path, response.status_code, duration_ms, mem_after, delta,
            )
        return response
