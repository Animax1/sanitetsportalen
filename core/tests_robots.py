"""Tester for crawler-sperren: /robots.txt og X-Robots-Tag.

Portalen skal aldri dukke opp i et søkeresultat. Testene her vokter begge
mekanismene, og at de ikke krever innlogging for å virke.
"""
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from core.robots import AI_CRAWLERS
from accounts.test_helpers import gi_standardtilgang


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RobotsTxtTests(TestCase):

    def test_robots_txt_er_offentlig(self):
        """Uten innlogging — ellers ser crawleren aldri reglene."""
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            resp['Content-Type'].startswith('text/plain'),
            f'robots.txt må serveres som text/plain, ikke {resp["Content-Type"]}',
        )

    def test_alt_er_blokkert_for_alle(self):
        body = self.client.get('/robots.txt').content.decode()
        self.assertIn('User-agent: *', body)
        self.assertIn('Disallow: /', body)
        # Ingen Allow-linje skal slippe noe gjennom
        self.assertNotIn('Allow:', body)

    def test_ai_crawlere_er_navngitt(self):
        """`User-agent: *` respekteres ikke alltid — botene må navngis."""
        body = self.client.get('/robots.txt').content.decode()
        for bot in AI_CRAWLERS:
            self.assertIn(f'User-agent: {bot}', body,
                          f'{bot} mangler i robots.txt')

    def test_hver_user_agent_har_egen_disallow(self):
        """En User-agent-linje uten Disallow under seg blokkerer ingenting."""
        linjer = [l.strip() for l in
                  self.client.get('/robots.txt').content.decode().splitlines()]
        for i, linje in enumerate(linjer):
            if linje.startswith('User-agent:'):
                rest = [l for l in linjer[i + 1:] if l and not l.startswith('#')]
                self.assertTrue(
                    rest and rest[0] == 'Disallow: /',
                    f'{linje} følges ikke av "Disallow: /"',
                )


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class XRobotsTagTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.user)

    def test_header_paa_offentlig_side(self):
        resp = self.client.get('/accounts/login/')
        self.assertIn('noindex', resp.headers.get('X-Robots-Tag', ''))

    def test_header_paa_innlogget_side(self):
        self.client.force_login(self.user)
        resp = self.client.get('/')
        self.assertIn('noindex', resp.headers.get('X-Robots-Tag', ''))

    def test_header_dekker_lenker_og_arkiv(self):
        """nofollow hindrer at crawleren følger videre; noarchive at den
        lagrer en kopi som kan vises selv om siden er borte."""
        tag = self.client.get('/accounts/login/').headers.get('X-Robots-Tag', '')
        for direktiv in ('noindex', 'nofollow', 'noarchive'):
            self.assertIn(direktiv, tag)

    def test_header_ogsaa_paa_healthz(self):
        """Healthz er det eneste andre offentlige endepunktet."""
        resp = self.client.get('/healthz/')
        self.assertIn('noindex', resp.headers.get('X-Robots-Tag', ''))
