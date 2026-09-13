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
        self.assertEqual(data['short_name'], 'Sanitetsportalen')
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


def _png_piksler(sti):
    """Minimal PNG-leser (8-bit RGB/RGBA, ikke interlaced) — nok til å lese
    hjørne- og midtpiksler uten Pillow, som ikke er i requirements."""
    import struct
    import zlib
    data = Path(sti).read_bytes()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', sti
    pos, idat, bredde, hoyde, kanaler = 8, b'', 0, 0, 0
    while pos < len(data):
        lengde, typ = struct.unpack('>I4s', data[pos:pos + 8])
        kropp = data[pos + 8:pos + 8 + lengde]
        if typ == b'IHDR':
            bredde, hoyde, dybde, farge, _, _, interlace = struct.unpack('>IIBBBBB', kropp)
            assert dybde == 8 and interlace == 0 and farge in (2, 6), (dybde, farge, interlace)
            kanaler = 3 if farge == 2 else 4
        elif typ == b'IDAT':
            idat += kropp
        pos += 12 + lengde
    raa = zlib.decompress(idat)
    stride = bredde * kanaler
    forrige = bytearray(stride)
    rader = []
    for y in range(hoyde):
        start = y * (stride + 1)
        filt = raa[start]
        linje = bytearray(raa[start + 1:start + 1 + stride])
        for i in range(stride):
            a = linje[i - kanaler] if i >= kanaler else 0
            b = forrige[i]
            c = forrige[i - kanaler] if i >= kanaler else 0
            if filt == 1:
                linje[i] = (linje[i] + a) & 255
            elif filt == 2:
                linje[i] = (linje[i] + b) & 255
            elif filt == 3:
                linje[i] = (linje[i] + ((a + b) >> 1)) & 255
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                linje[i] = (linje[i] + pred) & 255
        rader.append(bytes(linje))
        forrige = linje
    def piksel(x, y):
        r = rader[y][x * kanaler:(x + 1) * kanaler]
        return tuple(r) if kanaler == 4 else tuple(r) + (255,)
    return bredde, hoyde, piksel


class IkonfileneTests(TestCase):
    """PNG-ene er rendret fra SVG-en (`scripts/lag_ikoner.py`). Første utgave
    skalerte bakgrunnsrektangelet ned i hjørnet, så hjem-skjerm-ikonet fikk
    blå flekk øverst til venstre og gjennomsiktig resten (André, 12. sep.
    2026). Pikslene sier om flaten dekker."""

    NAVY = (15, 52, 96, 255)

    def _les(self, navn):
        return _png_piksler(Path(settings.BASE_DIR) / 'static/img' / navn)

    def test_full_flate_paa_maskable_og_apple_touch(self):
        for navn, px in (('logo-maskable-512.png', 512), ('apple-touch-icon.png', 180)):
            with self.subTest(navn=navn):
                b, h, piksel = self._les(navn)
                self.assertEqual((b, h), (px, px))
                for x, y in ((1, 1), (px - 2, 1), (1, px - 2), (px - 2, px - 2)):
                    self.assertEqual(piksel(x, y), self.NAVY, f'{navn} hjørne {x},{y}')

    def test_avrundede_ikoner_har_flate_og_figur(self):
        for navn, px in (('logo-192.png', 192), ('logo-512.png', 512)):
            with self.subTest(navn=navn):
                b, h, piksel = self._les(navn)
                self.assertEqual((b, h), (px, px))
                self.assertEqual(piksel(1, 1)[3], 0, 'hjørnet utenfor radiusen er gjennomsiktig')
                # Innenfor radiusen, men utenfor skjoldet: flaten.
                self.assertEqual(piksel(px // 2, px // 20), self.NAVY, 'flaten dekker')
                self.assertEqual(piksel(px // 2, px - px // 20), self.NAVY, 'helt ned')
                self.assertEqual(piksel(px // 2, px // 2)[:3], (255, 255, 255), 'personen i midten')


class AlleSiderLenkerTilManifestetTests(TestCase):
    """Hver mal med sitt eget `<head>` tar med `partials/_ikoner.html`."""

    # Maler som ikke er sider, men filer som forlater portalen. Vaktlista som
    # fil (12. sep. 2026) skal åpne uten nett og uten server — et manifest og
    # ikoner via `{% static %}` ville pekt på en tjener som er nede.
    IKKE_SIDER = ('templates/vaktliste/fil.html',)

    def _maler_med_eget_head(self):
        rot = Path(settings.BASE_DIR)
        for sti in list((rot / 'templates').rglob('*.html')) + list((rot / 'core/templates').rglob('*.html')):
            if 'partials' in sti.parts or str(sti.relative_to(rot)) in self.IKKE_SIDER:
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


class FanikonOgVisPassordTests(TestCase):
    """«Vis passord» på innloggingssiden var svart (André, 12. sep. 2026), og
    er portalens egen, lyse knapp, ikke nettleserens svarte øye.

    Fanikonet er **merket på blått**, samme fil som PWA-ikonet. En lys utgave
    uten bakgrunn (`favicon.svg`) ble prøvd samme dag og tatt tilbake 13. sep.
    («Jeg bruker mørk modus og det er en mørk blå bakgrunn som var der før.
    Jeg vil ha det slik det var.»)."""

    def test_fanen_bruker_merket_paa_blaatt(self):
        partial = (Path(settings.BASE_DIR) / 'templates/partials/_ikoner.html').read_text(encoding='utf-8')
        self.assertIn("rel=\"icon\" href=\"{% static 'img/logo.svg' %}\"", partial)
        self.assertNotIn('favicon.svg', partial)
        self.assertFalse((Path(settings.BASE_DIR) / 'static/img/favicon.svg').exists(),
                         'den lyse utgaven er tatt bort — ellers blir den liggende uten leser')
        svg = (Path(settings.BASE_DIR) / 'static/img/logo.svg').read_text(encoding='utf-8')
        self.assertIn('<rect', svg, 'bakgrunnsflaten er det André vil ha tilbake')
        self.assertIn('fill="#0f3460"', svg)
        self.assertIn('img/logo.svg', [i[0] for i in IKONER], 'PWA-ikonet er merket på blått')

    def test_innloggingssiden_har_egen_vis_passord_knapp(self):
        res = Client().get('/accounts/login/')
        self.assertContains(res, 'id="vis-passord"')
        self.assertContains(res, 'aria-label="Vis passord"')
        self.assertContains(res, '::-ms-reveal { display: none; }')
        # Inline-skriptet må bære nonce, ellers kjører det ikke (F5).
        self.assertRegex(res.content.decode(), r'<script nonce="[^"]+">\s*\(function \(\) \{\s*var knapp')
