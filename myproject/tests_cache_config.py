"""Tester for cache-konfigurasjon (Redis vs LocMemCache).

Verifiserer at:
- Default (uten REDIS_URL) bruker LocMemCache
- Settings eksponerer CACHE_BACKEND_NAME for diagnostikk
- Cache-operasjoner faktisk fungerer (write/read/delete)
- Helse-sjekken i admin_status returnerer riktig backend
- Settings-modulen kan re-importeres med REDIS_URL satt og bytter til Redis-backend

Vi kjører ikke faktisk Redis i testene (ingen ekstern avhengighet) — tester at
KONFIGURASJONEN er riktig, ikke at Redis-serveren funker.
"""
from __future__ import annotations

import importlib
import os
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings


class CacheBackendDefaultTests(TestCase):
    """Default-konfigurasjon (test-miljø, ingen REDIS_URL)."""

    def test_default_backend_er_locmem(self):
        """Uten REDIS_URL skal default-backend være LocMemCache."""
        backend = settings.CACHES['default']['BACKEND']
        self.assertEqual(backend, 'django.core.cache.backends.locmem.LocMemCache')

    def test_cache_backend_name_er_locmem(self):
        """Diagnostikk-flagget skal si 'locmem' uten REDIS_URL."""
        self.assertEqual(settings.CACHE_BACKEND_NAME, 'locmem')

    def test_cache_set_og_get_fungerer(self):
        """Grunnleggende write-read-delete via standard cache-API."""
        cache.set('test_key', 'test_value', 30)
        self.assertEqual(cache.get('test_key'), 'test_value')
        cache.delete('test_key')
        self.assertIsNone(cache.get('test_key'))

    def test_cache_isolert_mellom_keys(self):
        """Ulike nøkler skal ikke kollidere."""
        cache.set('key_a', 'A', 30)
        cache.set('key_b', 'B', 30)
        self.assertEqual(cache.get('key_a'), 'A')
        self.assertEqual(cache.get('key_b'), 'B')
        cache.delete('key_a')
        cache.delete('key_b')


class SettingsReloadWithRedisURLTests(TestCase):
    """Verifiser at settings.py velger Redis-backend når REDIS_URL er satt.

    Vi laster settings-modulen på nytt med en patched env-variabel og
    sjekker at CACHES-dict-en faktisk peker på RedisCache-backenden.
    Dette tester valg-logikken uten å kreve en kjørende Redis-server.
    """

    def test_redis_url_velger_redis_backend(self):
        fake_url = 'redis://fake-host:6379/0'
        with mock.patch.dict(os.environ, {'REDIS_URL': fake_url}, clear=False):
            from myproject import settings as settings_module
            reloaded = importlib.reload(settings_module)
            try:
                self.assertEqual(
                    reloaded.CACHES['default']['BACKEND'],
                    'django.core.cache.backends.redis.RedisCache',
                )
                self.assertEqual(reloaded.CACHES['default']['LOCATION'], fake_url)
                self.assertEqual(reloaded.CACHE_BACKEND_NAME, 'redis')
                self.assertEqual(
                    reloaded.CACHES['default']['KEY_PREFIX'], 'pasientregistrering'
                )
                # Django's innebygde RedisCache aksepterer ikke IGNORE_EXCEPTIONS
                # i OPTIONS — sjekk at vi IKKE feilaktig sender det videre.
                opts = reloaded.CACHES['default'].get('OPTIONS', {})
                self.assertNotIn('IGNORE_EXCEPTIONS', opts)
            finally:
                # Reload tilbake uten REDIS_URL så andre tester ikke påvirkes
                importlib.reload(settings_module)

    def test_tom_redis_url_velger_locmem(self):
        """REDIS_URL='' (tom streng) skal IKKE aktivere Redis."""
        with mock.patch.dict(os.environ, {'REDIS_URL': ''}, clear=False):
            from myproject import settings as settings_module
            reloaded = importlib.reload(settings_module)
            try:
                self.assertEqual(
                    reloaded.CACHES['default']['BACKEND'],
                    'django.core.cache.backends.locmem.LocMemCache',
                )
                self.assertEqual(reloaded.CACHE_BACKEND_NAME, 'locmem')
            finally:
                importlib.reload(settings_module)

    def test_whitespace_redis_url_velger_locmem(self):
        """REDIS_URL='   ' (kun whitespace) skal også falle tilbake."""
        with mock.patch.dict(os.environ, {'REDIS_URL': '   '}, clear=False):
            from myproject import settings as settings_module
            reloaded = importlib.reload(settings_module)
            try:
                self.assertEqual(reloaded.CACHE_BACKEND_NAME, 'locmem')
            finally:
                importlib.reload(settings_module)


class CacheHealthHelperTests(TestCase):
    """Tester _get_cache_health() i admin_status.py."""

    def test_health_helper_rapporterer_healthy_ok(self):
        from patients.admin_status import _get_cache_health
        result = _get_cache_health()
        self.assertEqual(result['backend'], 'locmem')
        self.assertTrue(result['healthy'])
        self.assertIn('latency_ms', result)
        self.assertGreaterEqual(result['latency_ms'], 0)

    def test_stats_cache_overlever_redis_feil(self):
        """Hvis cache.get/set kaster (Redis nede), skal stats-cache-dekoratøren
        fortsatt levere payload — ikke 500."""
        from django.http import JsonResponse
        from django.test import RequestFactory
        from patients import stats_cache as stats_cache_module
        from patients.stats_cache import cached_stats_response

        @cached_stats_response('test_failsafe', ttl=15)
        def fake_view(request):
            return JsonResponse({'ok': True})

        rf = RequestFactory()
        req = rf.get('/pasienter/api/stats/')

        # Simuler at cache-backenden kaster på alle operasjoner
        with mock.patch.object(
            stats_cache_module.cache, 'get',
            side_effect=ConnectionError('redis nede')
        ), mock.patch.object(
            stats_cache_module.cache, 'set',
            side_effect=ConnectionError('redis nede')
        ):
            response = fake_view(req)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"ok": true', response.content)

    def test_invalidate_cache_overlever_feil(self):
        """invalidate_stats_cache skal ikke kaste selv om backend er nede."""
        from patients import stats_cache as stats_cache_module
        from patients.stats_cache import invalidate_stats_cache

        with mock.patch.object(
            stats_cache_module.cache, 'delete',
            side_effect=ConnectionError('redis nede')
        ):
            # Må ikke kaste
            invalidate_stats_cache('noen_key', 'annen_key')

    def test_health_helper_fanger_exception(self):
        """Hvis cache.set kaster, skal helperen returnere healthy=False uten å re-raise."""
        from patients import admin_status as admin_status_module
        with mock.patch.object(
            admin_status_module.cache, 'set', side_effect=RuntimeError('redis nede')
        ):
            result = admin_status_module._get_cache_health()
            self.assertFalse(result['healthy'])
            self.assertIn('error', result)
            self.assertIn('redis nede', result['error'])

    def test_health_helper_scrubber_credentials(self):
        """Hvis exception inneholder en URL med passord, skal det scrubbes før retur."""
        from patients import admin_status as admin_status_module
        leaky = 'Failed: redis://default:hemmelig123@redis.host:6379/0 unreachable'
        with mock.patch.object(
            admin_status_module.cache, 'set', side_effect=RuntimeError(leaky)
        ):
            result = admin_status_module._get_cache_health()
            self.assertFalse(result['healthy'])
            self.assertNotIn('hemmelig123', result['error'])
            self.assertIn('[scrubbed]', result['error'])


class ScrubSecretsTests(TestCase):
    """Direkte enhetstester for _scrub_secrets-helperen."""

    def test_scrubber_redis_url(self):
        from patients.admin_status import _scrub_secrets
        text = 'Connection failed: redis://default:topsecret@host:6379/0'
        self.assertNotIn('topsecret', _scrub_secrets(text))
        self.assertIn('[scrubbed]', _scrub_secrets(text))

    def test_scrubber_postgres_url(self):
        from patients.admin_status import _scrub_secrets
        text = 'DB error: postgres://user:pass123@db.host:5432/mydb'
        self.assertNotIn('pass123', _scrub_secrets(text))

    def test_scrubber_holder_paa_resten(self):
        """Scrubber skal ikke endre tekst uten URL-credentials."""
        from patients.admin_status import _scrub_secrets
        text = 'Vanlig feilmelding uten URL'
        self.assertEqual(_scrub_secrets(text), text)

    def test_scrubber_taaler_tom_streng(self):
        from patients.admin_status import _scrub_secrets
        self.assertEqual(_scrub_secrets(''), '')
        self.assertEqual(_scrub_secrets(None), None)
