"""§4.1 — arrangementsnavn og sesjonstimeout hører til portalen, ikke modulen.

Begge lå under `/pasienter/` fordi pasientmodulen var den eneste som fantes.
Begge krevde global admin. Et admin-endepunkt inne i en modul sier at
modulgrensen ikke betyr noe — og det var nettopp den sammenblandingen
`ModulTilgang` skal fjerne.
"""
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser, ModulTilgang
from patients.models import AppSetting


def _bruker(navn, rolle='read_write', nivaa='skriv_full'):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role=rolle, must_change_password=False)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='patients', nivaa=nivaa)
    return b


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortalInnstillingerTests(TestCase):

    def setUp(self):
        self.admin = _bruker('ps_admin', rolle='admin', nivaa=None)
        self.client = Client()
        self.client.force_login(self.admin)
        self.url = reverse('core:portal_settings')

    def test_admin_ser_siden(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="event_name"')
        self.assertContains(resp, 'name="session_timeout_hours"')

    def test_ikke_admin_far_403(self):
        """Skriv_full på pasientmodulen gir ikke portalinnstillinger."""
        c = Client()
        c.force_login(_bruker('ps_skriver'))
        self.assertEqual(c.get(self.url).status_code, 403)

    def test_lagring_skriver_begge(self):
        resp = self.client.post(self.url, {
            'event_name': 'Festivalen 2026', 'session_timeout_hours': '12'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(AppSetting.get('event_name', ''), 'Festivalen 2026')
        self.assertEqual(int(AppSetting.get('session_timeout_hours', 0)), 12)

    def test_ugyldig_timeout_avvises(self):
        for verdi in ('0', '25', 'aatte', ''):
            with self.subTest(verdi=verdi):
                AppSetting.set('session_timeout_hours', 8)
                resp = self.client.post(self.url, {
                    'event_name': 'X', 'session_timeout_hours': verdi})
                self.assertEqual(resp.status_code, 200, 'skal vise skjemaet på nytt')
                self.assertEqual(int(AppSetting.get('session_timeout_hours', 0)), 8)

    def test_avvist_innsending_lagrer_ikke_halve_skjemaet(self):
        """En timeout på 0 skal ikke ha rukket å skrive arrangementsnavnet.

        `AppSetting` er en generisk nøkkel/verdi-tabell uten transaksjon rundt
        seg, så rekkefølgen i viewet er det eneste som hindrer det.
        """
        AppSetting.set('event_name', 'Uendret')
        self.client.post(self.url, {
            'event_name': 'Skulle ikke lagres', 'session_timeout_hours': '0'})
        self.assertEqual(AppSetting.get('event_name', ''), 'Uendret')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FlyttedeInnstillingsendepunkterTests(TestCase):
    """De gamle stiene under /pasienter/ skal ikke lenger kunne skrive."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(_bruker('fi_admin', rolle='admin', nivaa=None))

    def test_session_timeout_endepunktet_er_borte(self):
        self.assertEqual(
            self.client.get('/pasienter/api/session-timeout/').status_code, 404)

    def test_settings_kan_fortsatt_leses(self):
        """Headeren og årsfiltreringen trenger verdiene."""
        AppSetting.set('event_name', 'Vakt')
        resp = self.client.get('/pasienter/api/settings/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('event_name'), 'Vakt')
