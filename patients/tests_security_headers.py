"""Tester for SecurityHeadersMiddleware (CSP + \u00f8vrige sikkerhetsheadere)."""
from django.test import TestCase, Client, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SecurityHeadersTests(TestCase):
    """Verifiserer at sikkerhetsheadere settes p\u00e5 alle responser."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.user, 'admin')

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


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class CspNonceTests(TestCase):
    """script-src bruker nonce i stedet for 'unsafe-inline' (F5 trinn 2).

    Merk hvordan de to henger sammen: så snart CSP inneholder et nonce,
    ignorerer nettleseren 'unsafe-inline' for samme direktiv. Det finnes
    ingen mellomting — enten har hver eneste inline <script> riktig nonce,
    eller så kjører den ikke.
    """

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin_csp', password='pwd', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')

    def _direktiver(self, resp):
        csp = resp.headers['Content-Security-Policy']
        return {d.strip().split(' ', 1)[0]: d.strip()
                for d in csp.split(';') if d.strip()}

    def test_script_src_har_ikke_unsafe_inline(self):
        """Akseptansekriteriet for F5."""
        resp = self.client.get('/accounts/login/')
        self.assertNotIn("'unsafe-inline'", self._direktiver(resp)['script-src'])

    def test_script_src_har_nonce(self):
        resp = self.client.get('/accounts/login/')
        self.assertRegex(self._direktiver(resp)['script-src'], r"'nonce-[\w-]{16,}'")

    def test_style_src_beholder_unsafe_inline(self):
        """Bevisst: markup har ~50 inline style-attributter. Eget arbeid."""
        resp = self.client.get('/accounts/login/')
        self.assertIn("'unsafe-inline'", self._direktiver(resp)['style-src'])

    def test_nonce_er_unikt_per_request(self):
        """Gjenbrukt nonce er verdiløst — da kan en injisert script gjette det."""
        noncer = set()
        for _ in range(5):
            resp = self.client.get('/accounts/login/')
            noncer.add(self._direktiver(resp)['script-src'])
        self.assertEqual(len(noncer), 5, 'nonce gjenbrukes mellom requests')

    def test_inline_script_i_malen_har_samme_nonce_som_headeren(self):
        """Selve koblingen: står de to i utakt, kjører ikke skriptet.

        Dette er testen som fanger et nonce satt på feil sted i syklusen —
        f.eks. hvis middlewaren genererte det etter at templaten var rendret.
        """
        self.client.force_login(self.admin)
        resp = self.client.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)

        import re
        header_nonce = re.search(
            r"'nonce-([\w-]+)'",
            resp.headers['Content-Security-Policy']).group(1)
        markup_noncer = set(re.findall(
            r'<script nonce="([\w-]+)"', resp.content.decode('utf-8')))

        self.assertTrue(markup_noncer, 'ingen inline <script> med nonce i markup')
        self.assertEqual(markup_noncer, {header_nonce},
                         'nonce i markup matcher ikke headeren')

    def test_alle_inline_script_blokker_har_nonce(self):
        """En blokk uten nonce kjører ikke i det hele tatt.

        Går gjennom malene i stedet for én rendret side, siden ikke alle
        sider nås fra én test.
        """
        import re
        from pathlib import Path
        from django.conf import settings

        base = Path(settings.BASE_DIR)
        mapper = [base / 'templates'] + list(base.glob('*/templates'))

        uten = []
        for mappe in mapper:
            for mal in mappe.rglob('*.html'):
                for nr, linje in enumerate(
                        mal.read_text(encoding='utf-8').splitlines(), 1):
                    for treff in re.finditer(r'<script(?![^>]*\bsrc=)[^>]*>', linje):
                        if 'nonce=' not in treff.group(0):
                            uten.append(f'{mal.relative_to(base)}:{nr}')

        self.assertEqual(sorted(uten), [], (
            'Inline <script> uten nonce — disse kjører ikke:\n  '
            + '\n  '.join(sorted(uten))
            + '\n\nLegg til nonce="{{ csp_nonce }}".'
        ))
