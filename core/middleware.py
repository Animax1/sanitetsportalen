import logging
import resource
import time

log = logging.getLogger('memory')


class MemoryLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        t0 = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - t0) * 1000
        mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        delta = mem_after - mem_before
        if duration_ms > 200 or delta > 1024:
            log.info(
                'mem path=%s status=%s dur=%.0fms rss=%dkB delta=%+dkB',
                request.path, response.status_code, duration_ms, mem_after, delta,
            )
        return response
