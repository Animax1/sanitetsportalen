"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 2 — core.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
from pathlib import Path

from django.conf import settings
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import get_resolver
from django.urls.resolvers import URLResolver

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang

ROT = Path(__file__).resolve().parent.parent


class VendorFilerTests(SimpleTestCase):
    """H3: bibliotekene ligger i repoet, uten kartreferanser, og malene peker dit."""

    FILER = (
        'vendor/bootstrap/bootstrap.min.css', 'vendor/bootstrap/bootstrap.bundle.min.js',
        'vendor/bootstrap-icons/bootstrap-icons.min.css',
        'vendor/bootstrap-icons/fonts/bootstrap-icons.woff2', 'vendor/bootstrap-icons/fonts/bootstrap-icons.woff',
        'vendor/tabulator/tabulator_bootstrap5.min.css', 'vendor/tabulator/tabulator.min.js',
        'vendor/chartjs/chart.umd.js',
    )

    def test_filene_finnes_og_er_uten_sourcemap(self):
        for rel in self.FILER:
            p = ROT / 'static' / rel
            self.assertTrue(p.is_file(), rel)
            self.assertGreater(p.stat().st_size, 10_000, rel)
            if rel.endswith(('.css', '.js')):
                self.assertNotIn('sourceMappingURL', p.read_text(encoding='utf-8'), rel)

    def test_filene_er_sporet_av_git(self):
        """`.gitignore` hadde `vendor/`, og første deploy av H3 gikk uten
        filene: manifestet manglet dem, og alle sider ga 500. Filer som ikke er
        i git finnes ikke i bygget."""
        import subprocess
        ut = subprocess.run(['git', 'ls-files', 'static/vendor'], capture_output=True, text=True, cwd=ROT)
        if ut.returncode != 0:
            self.skipTest('ingen git her')
        sporet = set(ut.stdout.split())
        for rel in self.FILER:
            self.assertIn(f'static/{rel}', sporet, f'{rel} er ikke sporet av git — sjekk .gitignore')

    def test_malene_laster_dem_gjennom_static(self):
        import glob
        brukt = set()
        for p in glob.glob(str(ROT / '**' / 'templates' / '**' / '*.html'), recursive=True):
            tekst = Path(p).read_text(encoding='utf-8')
            for rel in self.FILER:
                if f"{{% static '{rel}' %}}" in tekst:
                    brukt.add(rel)
        for rel in self.FILER:
            if 'fonts/' in rel:
                continue   # lastes av ikon-CSS-en
            self.assertIn(rel, brukt, f'{rel} brukes ikke av noen mal')

    def test_ikon_css_peker_paa_fontene_relativt(self):
        css = (ROT / 'static/vendor/bootstrap-icons/bootstrap-icons.min.css').read_text(encoding='utf-8')
        self.assertIn('url("fonts/bootstrap-icons.woff2', css)

    def test_service_workeren_har_ingen_cdn(self):
        sw = (ROT / 'static/js/vaktliste-sw.js').read_text(encoding='utf-8')
        self.assertIn('const CDN = [];', sw)
        self.assertNotIn('jsdelivr', sw)


class FeilrapportUtenCookiesTests(SimpleTestCase):
    """L1: `sessionid` skal ikke stå i Djangos reserve-feilrapport."""

    def test_filteret_er_satt_og_skjuler_alle_cookies(self):
        from django.views.debug import get_exception_reporter_filter
        req = RequestFactory().get('/')
        req.COOKIES = {'sessionid': 'hemmelig', 'csrftoken': 'x', 'mfa_trusted_1': 'y'}
        f = get_exception_reporter_filter(req)
        self.assertEqual(type(f).__name__, 'SlankReporterFilter')
        trygge = f.get_safe_cookies(req)
        self.assertEqual(set(trygge), {'sessionid', 'csrftoken', 'mfa_trusted_1'})
        for verdi in trygge.values():
            self.assertNotIn('hemmelig', str(verdi))
            self.assertNotEqual(verdi, 'x')


class CacheStorrelseTests(SimpleTestCase):
    """M15."""

    def test_locmem_har_plass_til_tellerne(self):
        c = settings.CACHES['default']
        if 'locmem' in c['BACKEND']:
            self.assertGreaterEqual(c['OPTIONS']['MAX_ENTRIES'], 5000)


def _ruter_under(prefiks):
    ut = []
    def gaa(resolver, sti=''):
        for p in resolver.url_patterns:
            if isinstance(p, URLResolver):
                gaa(p, sti + str(p.pattern))
            else:
                full = sti + str(p.pattern)
                if full.startswith(prefiks):
                    ut.append((full, p.name, p.callback))
    gaa(get_resolver())
    return ut


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortalAdminRuteneErStengtTests(TestCase):
    """L14: dekoratørtesten dekket bare modulprefiksene. Her går vi gjennom
    `/portal-admin/`, `/varsler/`, `/api/varsler/` og `/min-profil/` og krever
    at anonym får omdirigering eller 403, og at en vanlig bruker får 403 på
    alt under `/portal-admin/`. Rutene finnes fra `urlpatterns`, så en ny
    rute uten dekoratør fanges."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(username='b_l14', password='x', must_change_password=False)
        gi_standardtilgang(self.bruker, 'leser')

    def _sti(self, monster):
        # <int:pk> → 1, <slug:slug> → patients, <str:x> → x
        import re
        return '/' + re.sub(r'<(?:\w+:)?(\w+)>', lambda m: 'patients' if m.group(1) == 'slug' else ('1' if 'pk' in m.group(1) else 'x'), monster)

    def test_admin_required_har_markoer(self):
        for full, navn, cb in _ruter_under('portal-admin/'):
            self.assertTrue(getattr(cb, '_admin_required', False) or getattr(cb, '_modul_kreves', None),
                            f'{full} ({navn}) mangler @admin_required')

    def test_anonym_slipper_ikke_inn(self):
        c = Client()
        ruter = [r for r in _ruter_under('portal-admin/') + _ruter_under('varsler/')
                 + _ruter_under('api/varsler/') + _ruter_under('min-profil/')]
        self.assertGreaterEqual(len(ruter), 20)
        for full, navn, cb in ruter:
            res = c.get(self._sti(full))
            self.assertIn(res.status_code, (301, 302, 401, 403, 405), f'{full} ({navn}) → {res.status_code}')
            if res.status_code in (301, 302):
                self.assertIn('/accounts/login/', res['Location'], full)

    def test_vanlig_bruker_faar_403_under_portal_admin(self):
        c = Client(); c.force_login(self.bruker)
        for full, navn, cb in _ruter_under('portal-admin/'):
            res = c.get(self._sti(full))
            self.assertIn(res.status_code, (403, 405), f'{full} ({navn}) → {res.status_code}')
