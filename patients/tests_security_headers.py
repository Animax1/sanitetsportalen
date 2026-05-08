"""Tester for SecurityHeadersMiddleware (CSP + \u00f8vrige sikkerhetsheadere)."""
from django.test import TestCase, Client, override_settings

from accounts.models import CustomUser


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SecurityHeadersTests(TestCase):
    """Verifiserer at sikkerhetsheadere settes p\u00e5 alle responser."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )

    def test_csp_header_er_satt(self):
        resp = self.client.get('/accounts/login/')
        self.assertIn('Content-Security-Policy', resp.headers)
        csp = resp.headers['Content-Security-Policy']
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)

    def test_csp_tillater_nodvendige_cdns(self):
        resp = self.client.get('/accounts/login/')
        csp = resp.headers['Content-Security-Policy']
        # Del CSP i direktiver for presis sjekk per direktiv
        directives = {d.strip().split(' ', 1)[0]: d.strip()
                      for d in csp.split(';') if d.strip()}
        # Både script og style må tillate jsdelivr og unpkg – ellers
        # blir Tabulator/Bootstrap/Chart.js blokkert og UI kollapser.
        for src in ('script-src', 'style-src'):
            self.assertIn('https://cdn.jsdelivr.net', directives.get(src, ''),
                          f'{src} må tillate cdn.jsdelivr.net')
            self.assertIn('https://unpkg.com', directives.get(src, ''),
                          f'{src} må tillate unpkg.com')

    def test_referrer_policy_satt(self):
        resp = self.client.get('/accounts/login/')
        self.assertEqual(resp.headers.get('Referrer-Policy'), 'same-origin')

    def test_permissions_policy_slar_av_sensors(self):
        resp = self.client.get('/accounts/login/')
        perm = resp.headers.get('Permissions-Policy', '')
        self.assertIn('camera=()', perm)
        self.assertIn('microphone=()', perm)
        self.assertIn('geolocation=()', perm)

    def test_headers_settes_paa_innlogget_side(self):
        self.client.login(username='admin', password='pwd')
        resp = self.client.get('/')
        self.assertIn('Content-Security-Policy', resp.headers)
        self.assertIn('Referrer-Policy', resp.headers)
