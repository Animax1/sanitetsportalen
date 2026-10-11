"""`If-None-Match` sammenlignes svakt (11. okt. 2026, `core/etag.py`).

Cloudflare foran Railway gjør en sterk ETag svak når den komprimerer svaret, og
`==` mot vår sterke bommet: **ingen av listene som polles fikk 304 i prod**. Testene
sender den svake formen gjennom hvert endepunkt som bruker ETag, slik nettleseren
sender den tilbake etter Cloudflare.
"""
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from core.etag import etag_treffer


class RegelenTests(SimpleTestCase):

    def _treff(self, hode, etag='"v2:abc"'):
        req = RequestFactory().get('/', **({'HTTP_IF_NONE_MATCH': hode} if hode is not None else {}))
        return etag_treffer(req, etag)

    def test_sterk_og_svak_er_samme_versjon(self):
        self.assertTrue(self._treff('"v2:abc"'))
        self.assertTrue(self._treff('W/"v2:abc"'), 'Cloudflare-formen')
        self.assertTrue(self._treff('"v2:abc"', etag='W/"v2:abc"'))

    def test_lister_og_stjerne(self):
        self.assertTrue(self._treff('"x", W/"v2:abc"'))
        self.assertTrue(self._treff('*'))

    def test_ingen_treff(self):
        for hode in (None, '', '   ', '"v2:abd"', 'W/"v2:ab"', 'v2:abc', '"v2:abc'):
            with self.subTest(hode=hode):
                self.assertFalse(self._treff(hode))
        self.assertFalse(self._treff('*', etag=''), 'uten ETag å sammenligne mot')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HvertEndepunktTests(TestCase):
    """Den svake formen gjennom hvert endepunkt som setter ETag."""

    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        sett_aktiv_vakt(2026)
        admin = CustomUser.objects.create_user(username='adm_etag', password='x', role='admin',
                                               must_change_password=False)
        self.client.force_login(admin)

    def test_svak_etag_gir_304(self):
        for url in ('/pasienter/api/patients/', '/pasienter/api/forstehjelpere/',
                    '/pasienter/api/helsepersonell/', '/ko/api/ansvarsomraader/',
                    '/oppdrag/api/oppdrag/', '/oppdrag/api/enheter/',
                    reverse('api_kilde_full_stats', kwargs={'slug': 'patients'})):
            with self.subTest(url=url):
                forste = self.client.get(url)
                self.assertEqual(forste.status_code, 200, forste.content[:200])
                etag = forste['ETag']
                # Statistikken sender svak selv; resten sterk, som Cloudflare svekker.
                svak = etag if etag.startswith('W/') else 'W/' + etag
                self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=svak).status_code, 304)


class IngenEgenSammenligningTests(SimpleTestCase):
    """Et nytt endepunkt med `== request.META['HTTP_IF_NONE_MATCH']` ville virket i
    testene og aldri gitt 304 i prod — nøyaktig feilen som sto i et år."""

    def test_bare_core_etag_leser_headeren(self):
        from pathlib import Path

        from django.conf import settings
        rot = Path(settings.BASE_DIR)
        funn = []
        for sti in sorted(rot.glob('*/**/*.py')):
            rel = sti.relative_to(rot).as_posix()
            if ('/tests' in rel or rel.startswith('.') or '/site-packages/' in rel
                    or '/migrations/' in rel or rel == 'core/etag.py'):
                continue
            if 'HTTP_IF_NONE_MATCH' in sti.read_text(encoding='utf-8'):
                funn.append(rel)
        self.assertEqual(funn, [], 'Bruk core.etag.etag_treffer() — Cloudflare gjør ETag-en svak')
