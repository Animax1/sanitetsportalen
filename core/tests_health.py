"""Tester for /healthz/-endepunktet (forbedring #2).

Kjør med: python manage.py test patients.tests_health
"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HealthzTests(TestCase):
    """Verifiser at /healthz/ svarer riktig i ulike scenarioer."""

    def setUp(self):
        self.client = Client()

    def tearDown(self):
        cache.clear()

    def test_healthz_returnerer_200_uten_auth(self):
        """Health-endepunktet skal svare uten innlogging."""
        resp = self.client.get('/healthz/')
        self.assertEqual(resp.status_code, 200)

    def test_healthz_har_status_ok_naar_alt_fungerer(self):
        """Med fungerende DB og cache skal status være 'ok'."""
        resp = self.client.get('/healthz/')
        body = resp.json()
        self.assertEqual(body['status'], 'ok')
        self.assertTrue(body['db']['ok'])
        self.assertTrue(body['cache']['ok'])

    def test_healthz_inkluderer_db_latency(self):
        """DB-sjekk skal rapportere latency_ms."""
        resp = self.client.get('/healthz/')
        body = resp.json()
        self.assertIn('latency_ms', body['db'])
        self.assertIsInstance(body['db']['latency_ms'], int)
        self.assertGreaterEqual(body['db']['latency_ms'], 0)

    def test_healthz_inkluderer_cache_backend_navn(self):
        """Cache-sjekk skal eksponere backend-navnet (locmem/redis)."""
        resp = self.client.get('/healthz/')
        body = resp.json()
        self.assertIn('backend', body['cache'])
        # I tester er backend typisk 'locmem' (CACHE_BACKEND_NAME settes
        # i settings basert på REDIS_URL — i tester er REDIS_URL tomt)
        self.assertIn(body['cache']['backend'], ('locmem', 'redis', 'unknown'))

    def test_healthz_inkluderer_version_felt(self):
        """Respons skal inneholde version-felt (kan være 'unknown' lokalt)."""
        resp = self.client.get('/healthz/')
        body = resp.json()
        self.assertIn('version', body)
        self.assertIsInstance(body['version'], str)

    def test_healthz_returnerer_503_ved_db_feil(self):
        """Hvis DB-tilkobling feiler skal endepunktet svare 503 'error'."""
        with patch('core.health._check_db', return_value=(False, None, 'OperationalError')):
            resp = self.client.get('/healthz/')
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertEqual(body['status'], 'error')
        self.assertFalse(body['db']['ok'])

    def test_healthz_returnerer_200_degraded_ved_cache_feil(self):
        """Cache-feil skal gi 'degraded' men HTTP 200 (appen er fortsatt brukbar)."""
        with patch('core.health._check_cache',
                   return_value=(False, None, 'ConnectionError')):
            resp = self.client.get('/healthz/')
        self.assertEqual(resp.status_code, 200,
                         'Cache-feil skal IKKE føre til 503 — appen er degradert, ikke nede')
        body = resp.json()
        self.assertEqual(body['status'], 'degraded')
        self.assertTrue(body['db']['ok'])
        self.assertFalse(body['cache']['ok'])

    def test_healthz_avviser_post(self):
        """Endepunktet skal kun akseptere GET/HEAD (require_safe)."""
        resp = self.client.post('/healthz/')
        self.assertEqual(resp.status_code, 405)

    def test_healthz_har_no_cache_header(self):
        """Helse-respons skal ikke caches av mellomliggende proxyer."""
        resp = self.client.get('/healthz/')
        cache_control = resp.get('Cache-Control', '')
        self.assertIn('no-cache', cache_control.lower() + cache_control)

    def test_healthz_lekker_ikke_credentials_ved_cache_feil(self):
        """Selv ved exception med credentials i meldingen, skal ikke disse vises."""
        # Simuler en cache-feil der exception-typen ikke inneholder credentials
        with patch('core.health._check_cache',
                   return_value=(False, None, 'ConnectionError')):
            resp = self.client.get('/healthz/')
        body = resp.json()
        # Vi rapporterer kun exception-type, ikke meldingen — så ingen passwords kan lekke
        self.assertEqual(body['cache']['error'], 'ConnectionError')
        # Verifiser at typiske credential-mønstre ikke finnes i hele responsen
        text = resp.content.decode()
        self.assertNotIn('@', text.split('cache')[1] if 'cache' in text else '',
                         'Cache-error skal ikke inneholde URL-stil credentials')

    def test_healthz_er_unntatt_fra_ssl_redirect(self):
        """SECURE_REDIRECT_EXEMPT må inneholde healthz/ slik at Railways interne
        healthcheck (ren HTTP, ingen X-Forwarded-Proto) ikke får 301-redirect."""
        import re
        from django.conf import settings
        exempt = getattr(settings, 'SECURE_REDIRECT_EXEMPT', [])
        self.assertTrue(
            any(re.match(p, 'healthz/') for p in exempt),
            f"healthz/ må være i SECURE_REDIRECT_EXEMPT, fant: {exempt}",
        )


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HealthzMiddlewareIsolationTests(TestCase):
    """Verifiser at /healthz/ ikke forstyrrer andre middleware-mekanismer."""

    def test_healthz_ekskluderes_fra_metrics_store(self):
        """RequestMetricsMiddleware skal ikke registrere health-checks."""
        from core.middleware import metrics_store
        # Reset til tom state
        metrics_store._samples.clear()

        client = Client()
        for _ in range(5):
            client.get('/healthz/')

        snapshot = metrics_store.snapshot(window_seconds=300)
        self.assertEqual(snapshot.get('count', 0), 0,
                         'Health-checks skal ikke føre opp i metrics-vinduet')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ProbeneGjennomDenEkteVeienTests(TestCase):
    """Målingen er delt med server-status (26. sep. 2026, E6). Testene over
    patcher `_check_cache` og ser derfor aldri hva som skjer med et ekte
    unntak — disse går gjennom proben."""

    def test_healthz_viser_bare_unntakstypen(self):
        lekk = RuntimeError('redis://default:hemmelig123@redis.host:6379/0 nede')
        with patch.object(cache, 'set', side_effect=lekk):
            body = self.client.get('/healthz/').json()
        self.assertEqual(body['cache']['error'], 'RuntimeError')
        self.assertNotIn('hemmelig123', str(body))

    def test_server_status_viser_den_vaskede_meldingen(self):
        from core.admin_status import _get_cache_health
        lekk = RuntimeError('redis://default:hemmelig123@redis.host:6379/0 nede')
        with patch.object(cache, 'set', side_effect=lekk):
            ut = _get_cache_health()
        self.assertIn('[scrubbed]@redis.host', ut['error'])
        self.assertNotIn('hemmelig123', ut['error'])

    def test_select_1_som_ikke_gir_1_er_en_feil(self):
        """Server-status sjekket ikke svaret før E6 — bare at spørringen gikk."""
        from core import health
        from core.admin_status import _get_db_health

        class Markor:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def execute(self, sql): pass
            def fetchone(self): return (0,)

        class Tilkobling:
            def cursor(self): return Markor()

        with patch.object(health, 'connections', {'default': Tilkobling()}):
            self.assertFalse(health.maal_db().ok)
            self.assertEqual(self.client.get('/healthz/').status_code, 503)
            db = _get_db_health()
        self.assertFalse(db['healthy'])
        self.assertEqual(db['error'], 'Uventet svar fra DB')
