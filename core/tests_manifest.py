"""Manifestet og ikonene (André, 12. sep. 2026: «et manifest og en logo»).

Det som testes er det manifestet lover: at det kan hentes uten innlogging,
at ikonene det peker på finnes, og at hver side med sitt eget `<head>`
faktisk lenker til det — et manifest ingen side peker på er ikke installert
noe sted.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase

from django.contrib.staticfiles import finders

from core.manifest import BAKGRUNN, IKONER, TEMAFARGE, manifest_data


class ManifestTests(TestCase):
    def test_manifestet_er_offentlig_og_har_riktig_type(self):
        res = Client().get('/manifest.webmanifest')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/manifest+json')
        data = json.loads(res.content)
        self.assertEqual(data['name'], 'Sanitetsportalen')
        self.assertEqual(data['display'], 'standalone')
        self.assertEqual(data['start_url'], '/')
        self.assertEqual(data['theme_color'], TEMAFARGE)
        self.assertEqual(data['background_color'], BAKGRUNN)

    def test_ikonene_finnes_som_filer(self):
        for sti, *_ in IKONER:
            self.assertTrue(finders.find(sti), sti)
        ikoner = manifest_data()['icons']
        self.assertEqual(len(ikoner), len(IKONER))
        self.assertTrue(all(i['src'].startswith(settings.STATIC_URL) for i in ikoner))
        self.assertTrue(
            any(i.get('purpose') == 'maskable' for i in ikoner),
            'Android trenger et maskable-ikon for å ikke legge hvit ramme rundt')

    def test_temafargen_er_portalens_headerfarge(self):
        base = (Path(settings.BASE_DIR) / 'core/templates/core/base_portal.html').read_text(encoding='utf-8')
        self.assertIn(f'--portal-header-bg: {TEMAFARGE};', base)
        self.assertIn(f'--portal-bg: {BAKGRUNN};', base)

    def test_merket_er_rolig_og_uten_roedt(self):
        """Et rødt kors på hvitt er Røde Kors-emblemet og beskyttet, og André
        ville ha noe subtilt (12. sep. 2026). Merket er et skjold med en
        person i — to farger på portalens blå, ingen rødt."""
        svg = (Path(settings.BASE_DIR) / 'static/img/logo.svg').read_text(encoding='utf-8')
        self.assertIn('<title>Sanitetsportalen</title>', svg)
        farger = set(re.findall(r'#[0-9a-fA-F]{6}', svg))
        self.assertEqual(farger, {'#0f3460', '#8fb3f0', '#ffffff'}, farger)


class AlleSiderLenkerTilManifestetTests(TestCase):
    """Hver mal med sitt eget `<head>` tar med `partials/_ikoner.html`."""

    def _maler_med_eget_head(self):
        rot = Path(settings.BASE_DIR)
        for sti in list((rot / 'templates').rglob('*.html')) + list((rot / 'core/templates').rglob('*.html')):
            if 'partials' in sti.parts:
                continue
            tekst = sti.read_text(encoding='utf-8')
            if re.search(r'<head\b', tekst):
                yield sti.relative_to(rot), tekst

    def test_hver_side_med_eget_head_tar_med_ikonene(self):
        mangler = [str(sti) for sti, tekst in self._maler_med_eget_head()
                   if 'partials/_ikoner.html' not in tekst]
        self.assertEqual(mangler, [], 'maler uten manifest og ikon')

    def test_innloggingssiden_serverer_lenkene(self):
        res = Client().get('/accounts/login/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'rel="manifest" href="/manifest.webmanifest"')
        self.assertContains(res, 'rel="apple-touch-icon"')
        self.assertContains(res, 'name="theme-color"')
