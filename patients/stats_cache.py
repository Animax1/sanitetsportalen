"""Cache- og ETag-hjelpere for stats-endepunkter.

Gir kortvarig caching (15s/60s) med ETag/304-støtte for å redusere
serverlast ved gjentatte requests fra samme klient. Designet for å
være trygt å aktivere uten live-polling: cachen fylles først når
noen faktisk laster stats-siden, og TTL-ene er så korte at data
aldri oppleves som utdaterte.

Bruk:
    @cached_stats_response(cache_key='stats:basic', ttl=15)
    def stats_view(request):
        ...
"""
from __future__ import annotations

import hashlib
import json
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse, HttpResponseNotModified


# Prefix for å unngå kollisjon med andre cache-brukere (rate-limiting osv.)
CACHE_PREFIX = 'statscache'


def _make_etag(payload: dict) -> str:
    """Lag stabil ETag fra response-body.

    SHA-256 gir vesentlig kollisjonsfrihet og er raskere enn
    MD5 på moderne CPUer. Prefiks 'W/' markerer weak ETag
    (tillater gzip/transformasjoner uten å bryte matching).
    """
    body = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]
    return f'W/"{digest}"'


def cached_stats_response(cache_key: str, ttl: int):
    """Dekoratør som cacher JSON-response og støtter ETag/304.

    Args:
        cache_key: Nøkkel under CACHE_PREFIX. Bør inkludere varianter
            (f.eks. aktivt år) hvis responsen varierer.
        ttl: Cache-TTL i sekunder.

    View-funksjonen skal returnere dict/list (serialiseres til JSON)
    eller en JsonResponse. Andre response-typer passeres uendret.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Bygg full cache-nøkkel. Views kan overstyre ved å sette
            # request._stats_cache_key_suffix før vi kommer hit, men i
            # praksis bruker vi get_active_year() inne i view.
            full_key = f'{CACHE_PREFIX}:{cache_key}'

            # 1) Forsøk cache-lookup. Hvis cache-backenden (typisk Redis)
            #    er nede, faller vi tilbake til å kjøre view-en uten cache.
            try:
                cached = cache.get(full_key)
            except Exception:
                cached = None

            if cached is not None:
                payload, etag = cached
            else:
                # 2) Miss: kjør view og cache resultatet
                result = view_func(request, *args, **kwargs)

                # Hvis view returnerer JsonResponse, hent ut data
                if isinstance(result, JsonResponse):
                    payload = json.loads(result.content.decode('utf-8'))
                elif isinstance(result, (dict, list)):
                    payload = result
                else:
                    # Ukjent type — passér gjennom uten caching
                    return result

                etag = _make_etag(payload)
                # Cache-skriving skal aldri kunne få endepunktet til å
                # returnere 500 — ignorer feil og levér uansett payload.
                try:
                    cache.set(full_key, (payload, etag), ttl)
                except Exception:
                    pass

            # 3) Sjekk If-None-Match for 304
            client_etag = request.META.get('HTTP_IF_NONE_MATCH', '')
            if client_etag and client_etag == etag:
                response = HttpResponseNotModified()
                response['ETag'] = etag
                response['Cache-Control'] = f'private, max-age={ttl}'
                return response

            # 4) Returner frisk response med headers
            response = JsonResponse(payload, safe=False)
            response['ETag'] = etag
            response['Cache-Control'] = f'private, max-age={ttl}'
            return response

        return wrapper
    return decorator


def invalidate_stats_cache(*keys: str) -> None:
    """Fjern spesifikke cache-nøkler. Brukes ved pasient-endringer
    om man vil tvinge fersk beregning. I praksis er TTL så kort (15s)
    at eksplisitt invalidering sjelden er nødvendig.
    """
    for key in keys:
        # Cache-feil under invalidering skal ikke ta ned skriveoperasjonen
        # som kalte oss — bare logg implisitt og fortsett.
        try:
            cache.delete(f'{CACHE_PREFIX}:{key}')
        except Exception:
            pass
