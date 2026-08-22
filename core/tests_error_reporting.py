"""Tester for den slanke feilrapporten i e-postvarselet.

Poenget med rapporten er hva den *ikke* inneholder. Testene her vokter fravalgene,
fordi det er de som er sikkerhetsegenskapen — innholdet er lett å se at stemmer,
mens en gjeninnført Settings-dump ville gått upåaktet hen.

Kjør med: python manage.py test core.tests_error_reporting
"""
import sys

from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings

from core.error_reporting import SlankExceptionReporter


def _rapport(request=None, exc=None):
    try:
        raise exc or ValueError('noe gikk galt')
    except Exception:
        return SlankExceptionReporter(
            request, *sys.exc_info(), is_email=True
        ).get_traceback_text()


class UtelatelserTests(TestCase):
    """Det som ikke skal ut av systemet."""

    def setUp(self):
        self.request = RequestFactory().post(
            '/pasienter/api/patients/',
            data={'lege': 'DR_HEMMELIG', 'triage': 'Rød'},
            HTTP_COOKIE='sessionid=SESJON_HEMMELIG',
        )
        self.request.META['REMOTE_ADDR'] = '10.0.0.5'

    def test_skjemadata_er_ikke_med(self):
        """En POST mot pasient-API-et har kliniske opplysninger i kroppen."""
        self.assertNotIn('DR_HEMMELIG', _rapport(self.request))

    def test_sesjonscookie_er_ikke_med(self):
        self.assertNotIn('SESJON_HEMMELIG', _rapport(self.request))

    def test_settings_dumpen_er_ikke_med(self):
        r = _rapport(self.request)
        self.assertNotIn('Settings:', r)
        self.assertNotIn('INSTALLED_APPS', r)

    def test_secret_key_er_ikke_med(self):
        self.assertNotIn(settings.SECRET_KEY, _rapport(self.request))

    def test_full_meta_dump_er_ikke_med(self):
        """Kun de tre feltene som forklarer noe — ikke hele WSGI-miljøet."""
        self.request.META['HTTP_X_TILFELDIG'] = 'SKAL_IKKE_MED'
        r = _rapport(self.request)
        self.assertNotIn('SKAL_IKKE_MED', r)
        self.assertNotIn('META:', r)

    def test_rapporten_er_vesentlig_kortere_enn_djangos(self):
        from django.views.debug import ExceptionReporter
        try:
            raise ValueError('x')
        except ValueError:
            standard = ExceptionReporter(
                self.request, *sys.exc_info(), is_email=True
            ).get_traceback_text()
        self.assertLess(len(_rapport(self.request)), len(standard) / 4)


class InnholdTests(TestCase):
    """Det som må være med for at varselet skal være til nytte."""

    def test_exception_og_melding(self):
        r = _rapport(exc=KeyError('mangler felt'))
        self.assertIn('KeyError', r)
        self.assertIn('mangler felt', r)

    def test_traceback_er_med(self):
        self.assertIn('Traceback', _rapport())

    def test_forespoersel_og_klient(self):
        req = RequestFactory().get('/pasienter/?fane=tavle')
        req.META['REMOTE_ADDR'] = '10.0.0.5'
        req.META['HTTP_USER_AGENT'] = 'Mozilla/5.0 (Test)'
        r = _rapport(req)
        self.assertIn('/pasienter/?fane=tavle', r)
        self.assertIn('10.0.0.5', r)
        self.assertIn('Mozilla/5.0 (Test)', r)

    def test_uten_request_velter_ikke(self):
        """Feil utenfor en request — f.eks. i en management-kommando."""
        r = _rapport(None)
        self.assertIn('ingen', r.lower())
        self.assertIn('Traceback', r)

    def test_bruker_uten_auth_middleware_haandteres(self):
        """RequestFactory kjører ikke middleware, så request.user finnes ikke."""
        req = RequestFactory().get('/')
        self.assertIn('Bruker', _rapport(req))


class RobusthetTests(TestCase):
    """Rapportøren skal aldri ta med seg varslingen den skulle levere."""

    def test_faller_tilbake_til_django_ved_intern_feil(self):
        class Sabotert(SlankExceptionReporter):
            def _slank_rapport(self):
                raise RuntimeError('sabotasje')

        req = RequestFactory().get('/')
        try:
            raise ValueError('den ekte feilen')
        except ValueError:
            r = Sabotert(req, *sys.exc_info(), is_email=True).get_traceback_text()
        # Djangos egen rapport er fyldig — men vi fikk *en* rapport.
        self.assertIn('den ekte feilen', r)


class KoblingTests(TestCase):
    """Rapportøren må faktisk være i bruk av e-posthandleren."""

    def test_logging_bruker_slank_rapportoer(self):
        konf = settings.LOGGING['handlers']['mail_admins']
        self.assertEqual(
            konf.get('reporter_class'),
            'core.error_reporting.SlankExceptionReporter',
        )

    def test_html_er_avslaatt(self):
        """HTML-malen har lokale variabler — altså pasientdata i minnet."""
        self.assertIs(
            settings.LOGGING['handlers']['mail_admins'].get('include_html'), False
        )
