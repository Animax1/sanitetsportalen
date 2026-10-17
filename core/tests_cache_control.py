"""Standard `Cache-Control` for svar viewet ikke har tatt stilling til (17. okt. 2026).

Regelen står i `core.middleware.sett_standard_cache_control`: `private, no-store` der
viewet ikke har satt headeren, og ingenting der det har det. Testene går gjennom den
ekte middleware-stakken, ikke bare funksjonen — det er kallstedet i
`SecurityHeadersMiddleware` som må være der (`CLAUDE.md`, «Mutasjonstesting»).
"""
from django.http import HttpResponse
from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from core.middleware import STANDARD_CACHE_CONTROL, sett_standard_cache_control
from patients.models import Forstehjelper


class RegelenTests(SimpleTestCase):
    def test_svar_uten_header_faar_private_no_store(self):
        svar = sett_standard_cache_control(HttpResponse('x'))
        self.assertEqual(svar['Cache-Control'], 'private, no-store')

    def test_svar_med_egen_header_beholder_den(self):
        svar = HttpResponse('x')
        svar['Cache-Control'] = 'private, max-age=60'
        self.assertEqual(sett_standard_cache_control(svar)['Cache-Control'],
                         'private, max-age=60')

    def test_standarden_har_begge_direktivene(self):
        """`private` stenger delte mellomlagre ute, `no-store` nettleserens disk."""
        direktiver = {d.strip() for d in STANDARD_CACHE_CONTROL.split(',')}
        self.assertEqual(direktiver, {'private', 'no-store'})


@override_settings(SECURE_SSL_REDIRECT=False)
class GjennomMiddlewareTests(TestCase):
    """Gjennom den ekte stakken: åpen side, innlogget side, og en view med egen header."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='cachetest', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.bruker, 'leser')
        self.klient = Client()

    def _direktiver(self, svar):
        return {d.strip() for d in svar['Cache-Control'].split(',')}

    def test_svar_uten_innlogging_og_uten_egen_header(self):
        """En 404 og en omdirigering til innloggingen — ingen av dem har bestemt noe."""
        for sti, status in (('/finnes-ikke-hos-oss/', 404), ('/', 302)):
            svar = self.klient.get(sti)
            self.assertEqual(svar.status_code, status, sti)
            self.assertLessEqual({'private', 'no-store'}, self._direktiver(svar), sti)

    def test_robots_har_bestemt_selv(self):
        """`robots.txt` har `max-age` med vilje: den er lik for alle."""
        svar = self.klient.get('/robots.txt')
        self.assertNotIn('no-store', self._direktiver(svar))

    def test_aapen_side_som_har_bestemt_selv(self):
        """`/personvern/` har `@cache_control(no_cache=True)` — offentlig, uten
        personopplysninger, og bevisst. Den skal ikke overstyres."""
        svar = self.klient.get('/personvern/')
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(self._direktiver(svar), {'no-cache'})

    def test_innlogget_side_uten_egen_header(self):
        self.klient.force_login(self.bruker)
        svar = self.klient.get('/min-profil/')
        self.assertEqual(svar.status_code, 200)
        self.assertLessEqual({'private', 'no-store'}, self._direktiver(svar))

    def test_etag_endepunkt_beholder_sin_egen_header(self):
        """`/pasienter/api/forstehjelpere/` setter `private, must-revalidate` for ETag/304.

        Et `=` i stedet for `setdefault` ville gjort den til `private, no-store`, og
        `must-revalidate` ville forsvunnet.
        """
        Forstehjelper.objects.create(name='Behandler A', is_active=True)
        self.klient.force_login(self.bruker)
        svar = self.klient.get('/pasienter/api/forstehjelpere/')
        self.assertEqual(svar.status_code, 200)
        self.assertIn('must-revalidate', self._direktiver(svar))
        etag = svar['ETag']
        self.assertEqual(self.klient.get('/pasienter/api/forstehjelpere/',
                                         HTTP_IF_NONE_MATCH=etag).status_code, 304)
