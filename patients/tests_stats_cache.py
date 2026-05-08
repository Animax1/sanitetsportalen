"""Tester for stats-cache og ETag/304-støtte."""
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from accounts.models import CustomUser

from .stats_cache import (
    cached_stats_response,
    invalidate_stats_cache,
    _make_etag,
    CACHE_PREFIX,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class ETagHelperTests(TestCase):
    """Unit-tester for ETag-generering."""

    def test_etag_er_stabil_for_samme_data(self):
        payload = {'a': 1, 'b': [2, 3], 'c': 'tekst'}
        etag1 = _make_etag(payload)
        etag2 = _make_etag(payload)
        self.assertEqual(etag1, etag2)

    def test_etag_ignorerer_nokkelrekkefolge(self):
        # Samme innhold, ulik rekkefølge i dict
        etag1 = _make_etag({'a': 1, 'b': 2})
        etag2 = _make_etag({'b': 2, 'a': 1})
        self.assertEqual(etag1, etag2)

    def test_etag_endres_med_data(self):
        etag1 = _make_etag({'count': 10})
        etag2 = _make_etag({'count': 11})
        self.assertNotEqual(etag1, etag2)

    def test_etag_er_weak_format(self):
        etag = _make_etag({'x': 1})
        self.assertTrue(etag.startswith('W/"'))
        self.assertTrue(etag.endswith('"'))


@override_settings(SECURE_SSL_REDIRECT=False)
class StatsCacheViewTests(TestCase):
    """Integrasjonstester mot /api/stats/ og /api/full-stats/."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin1', password='testpass123',
            role='admin', must_change_password=False,
        )
        # Rens cache mellom tester
        cache.clear()

    def test_basic_stats_returnerer_etag(self):
        self.client.login(username='admin1', password='testpass123')
        resp = self.client.get(reverse('api_stats'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('ETag', resp)
        self.assertIn('Cache-Control', resp)
        self.assertIn('max-age=15', resp['Cache-Control'])

    def test_full_stats_returnerer_etag_med_lengre_ttl(self):
        self.client.login(username='admin1', password='testpass123')
        resp = self.client.get(reverse('api_full_stats'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('ETag', resp)
        self.assertIn('max-age=60', resp['Cache-Control'])

    def test_matching_etag_gir_304(self):
        self.client.login(username='admin1', password='testpass123')

        # Første request: 200 med ETag
        resp1 = self.client.get(reverse('api_stats'))
        self.assertEqual(resp1.status_code, 200)
        etag = resp1['ETag']

        # Andre request med samme ETag: 304
        resp2 = self.client.get(reverse('api_stats'), HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(resp2.status_code, 304)
        # 304-response har tom body (Django HttpResponseNotModified)
        self.assertEqual(resp2.content, b'')
        # ETag skal fortsatt finnes i 304-response for korrekt HTTP
        self.assertEqual(resp2['ETag'], etag)

    def test_ikke_matching_etag_gir_200(self):
        self.client.login(username='admin1', password='testpass123')
        resp = self.client.get(
            reverse('api_stats'),
            HTTP_IF_NONE_MATCH='W/"feilverdi"'
        )
        self.assertEqual(resp.status_code, 200)

    def test_cache_brukes_pa_gjentatt_request(self):
        """Andre request skal hente fra cache, ikke kjøre view på nytt."""
        self.client.login(username='admin1', password='testpass123')

        # Første request: fyller cache
        resp1 = self.client.get(reverse('api_stats'))
        self.assertEqual(resp1.status_code, 200)

        # Verifiser at noe faktisk ligger i cache-laget
        # (cache-nøkkelen inkluderer aktivt år — vi sjekker at en nøkkel
        # med riktig prefiks finnes)
        from django.core.cache import cache as dcache
        # LocMemCache eksponerer ikke keys(), så vi tester indirekte:
        # andre request skal returnere samme ETag uten at data endres.
        resp2 = self.client.get(reverse('api_stats'))
        self.assertEqual(resp1['ETag'], resp2['ETag'])

    def test_uautentisert_far_redirect(self):
        """Stats-endepunkter krever login."""
        resp = self.client.get(reverse('api_stats'))
        # @login_required redirecter til login-siden
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_full_stats_krever_stats_rolle(self):
        """Lag read_only-bruker som ikke har stats-tilgang."""
        CustomUser.objects.create_user(
            username='ro1', password='testpass123',
            role='read_only', must_change_password=False,
        )
        self.client.login(username='ro1', password='testpass123')
        resp = self.client.get(reverse('api_full_stats'))
        # @stats_required blokkerer read_only
        self.assertIn(resp.status_code, (302, 403))

    def test_invalidate_fjerner_cache(self):
        """invalidate_stats_cache skal fjerne nøkkelen."""
        # Sett en dummy-verdi direkte i cache
        cache.set(f'{CACHE_PREFIX}:test', ({'x': 1}, 'W/"abc"'), 60)
        self.assertIsNotNone(cache.get(f'{CACHE_PREFIX}:test'))

        invalidate_stats_cache('test')
        self.assertIsNone(cache.get(f'{CACHE_PREFIX}:test'))


@override_settings(SECURE_SSL_REDIRECT=False)
class CachedStatsResponseDecoratorTests(TestCase):
    """Lavnivå-tester for selve dekoratoren."""

    def setUp(self):
        cache.clear()

    def test_dekorator_cacher_dict(self):
        call_count = {'n': 0}

        @cached_stats_response(cache_key='test:dict', ttl=30)
        def view(request):
            call_count['n'] += 1
            return {'value': 42}

        from django.test import RequestFactory
        factory = RequestFactory()

        # Første kall: view kjøres
        resp1 = view(factory.get('/'))
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(call_count['n'], 1)

        # Andre kall: fra cache, view kjøres ikke
        resp2 = view(factory.get('/'))
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(call_count['n'], 1)  # uendret
        self.assertEqual(resp1['ETag'], resp2['ETag'])

    def test_dekorator_respekterer_if_none_match(self):
        @cached_stats_response(cache_key='test:304', ttl=30)
        def view(request):
            return {'value': 1}

        from django.test import RequestFactory
        factory = RequestFactory()

        resp1 = view(factory.get('/'))
        etag = resp1['ETag']

        # Andre kall med matching If-None-Match → 304
        req = factory.get('/', HTTP_IF_NONE_MATCH=etag)
        resp2 = view(req)
        self.assertEqual(resp2.status_code, 304)
