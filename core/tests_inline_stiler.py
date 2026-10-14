"""Inline stiler under CSP 3 (14. okt. 2026) — se kommentaren ved `_CSP_DIRECTIVES`.

`style-src-elem` krever nonce: et injisert `<style>` restyler hele siden. Hver
`<style>` portalen selv skriver, må derfor bære **nøyaktig** headerens nonce —
og den kommer fra context-processoren, så en mal rendret uten request får
ingen. Det er fella: `vaktliste/fil.py` rendret vaktlistefila med
`render_to_string`, og fila ville åpnet seg uten stiler i nettleseren.

Derfor prøves regelen på **ekte svar**, ikke bare på malene: hver GET-rute i
portalen hentes som admin og som anonym, og hver `<style>` i svaret sammenlignes
med headeren. Den statiske regelen står ved siden av fordi ikke alle maler nås
av én forespørsel uten data.

**Ett unntak, `vaktliste/fil.html`**: den rendres uten request, men vises aldri
under portalens CSP — den sendes på e-post, og `fil_view` sender den som
nedlasting (`Content-Disposition: attachment`), som åpnes fra disk uten header.
Jeg trodde først den ville miste stilene; en prøve i Chromium viste at den ble
lastet ned. `VaktlistefilaTests` holder forutsetningen: blir den en side i
nettleseren, er testen rød og sier hva som må til.

`style-src-attr` står med `'unsafe-inline'` til attributtene er borte. Tallet
holdes på vei ned av `StilattributteneGaarBareNedTests` — senk taket i samme
commit som en mal ryddes, aldri opp.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang

ROT = Path(settings.BASE_DIR)
_STYLE = re.compile(r'<style(?:\s[^>]*)?>')

#: Maler som aldri vises under portalens CSP — se docstringen.
UNNTATT = {'templates/vaktliste/fil.html'}


def _maler():
    return [p for d in [ROT / 'templates', *ROT.glob('*/templates')] for p in d.rglob('*.html')]


def _uten_malkommentarer(tekst: str) -> str:
    tekst = re.sub(r'\{#.*?#\}', '', tekst, flags=re.S)
    tekst = re.sub(r'\{% comment %\}.*?\{% endcomment %\}', '', tekst, flags=re.S)
    return re.sub(r'<!--.*?-->', '', tekst, flags=re.S)


def _uten_jskommentarer(tekst: str) -> str:
    tekst = re.sub(r'/\*.*?\*/', '', tekst, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', tekst)


def _direktiver(svar) -> dict:
    return {d.strip().split(' ', 1)[0]: d.strip()
            for d in svar.headers['Content-Security-Policy'].split(';') if d.strip()}


class DirektiveneTests(SimpleTestCase):

    def test_elementene_krever_nonce_og_slipper_ikke_inline(self):
        d = _direktiver(Client().get('/accounts/login/'))
        self.assertRegex(d['style-src-elem'], r"'nonce-[\w-]{16,}'")
        self.assertNotIn("'unsafe-inline'", d['style-src-elem'])
        self.assertIn("'self'", d['style-src-elem'], 'stilarkene under /static/')

    def test_attributtene_er_eksplisitte(self):
        """Står `-attr` ikke der, faller den tilbake til `style-src` — samme
        utfall i dag, men da finnes det ingen linje å skru til den dagen
        attributtene er borte."""
        d = _direktiver(Client().get('/accounts/login/'))
        self.assertIn('style-src-attr', d)

    def test_samme_nonce_for_skript_og_stil(self):
        d = _direktiver(Client().get('/accounts/login/'))
        self.assertEqual(re.search(r"'nonce-([\w-]+)'", d['script-src']).group(1),
                         re.search(r"'nonce-([\w-]+)'", d['style-src-elem']).group(1))


class MaleneTests(SimpleTestCase):

    def test_hver_style_blokk_har_nonce(self):
        uten = []
        for mal in _maler():
            if str(mal.relative_to(ROT)) in UNNTATT:
                continue
            for nr, linje in enumerate(_uten_malkommentarer(mal.read_text(encoding='utf-8')).splitlines(), 1):
                for tagg in _STYLE.findall(linje):
                    if 'nonce=' not in tagg:
                        uten.append(f'{mal.relative_to(ROT)}:{nr}')
        self.assertEqual(uten, [], 'Legg til nonce="{{ csp_nonce }}" — uten blokkeres stilene')

    def test_leseren_ser_blokkene(self):
        """Vern mot en regel som ser ingenting: blokkene finnes."""
        antall = sum(len(_STYLE.findall(_uten_malkommentarer(m.read_text(encoding='utf-8'))))
                     for m in _maler())
        self.assertGreaterEqual(antall, 20)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EkteSvarTests(TestCase):
    """Hver GET-rute, som admin og som anonym."""

    def _sjekk(self, klient, sti, funn, sider):
        try:
            svar = klient.get(sti)
        except Exception:   # noqa: BLE001 — en rute uten data kan kaste; det er ikke denne regelens sak
            return
        if 'text/html' not in svar.get('Content-Type', '') or 'Content-Security-Policy' not in svar:
            return
        tekst = svar.content.decode('utf-8', 'replace')
        tagger = _STYLE.findall(tekst)
        if not tagger:
            return
        sider.add(sti)
        header = re.search(r"'nonce-([\w-]+)'", _direktiver(svar)['style-src-elem']).group(1)
        for tagg in tagger:
            m = re.search(r'nonce="([^"]*)"', tagg)
            if not m or m.group(1) != header:
                funn.append(f'{sti} ({svar.status_code}): {tagg}')

    def test_hver_style_i_svaret_har_headerens_nonce(self):
        from core.sikkerhetsruter import _eksempel, alle_monstre
        admin = CustomUser.objects.create_user(username='stil_adm', password='x', role='admin',
                                               must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        innlogget = Client()
        innlogget.force_login(admin)
        funn, sider = [], set()
        for monster in alle_monstre():
            sti = _eksempel(monster)
            for klient in (innlogget, Client()):
                self._sjekk(klient, sti, funn, sider)
        self.assertEqual(funn, [], 'En <style> uten riktig nonce blokkeres av nettleseren')
        # Vern mot en test som ser ingenting: portalsiden, innloggingen, 403, personvern …
        self.assertGreaterEqual(len(sider), 10, sorted(sider))


class VaktlistefilaTests(TestCase):
    """Unntaket holder bare så lenge fila lastes ned."""

    def setUp(self):
        from patients.test_helpers import sett_aktiv_vakt
        from vaktliste.models import Vaktliste
        self.vl = Vaktliste.objects.create(vakt=sett_aktiv_vakt(2033))

    @override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
    def test_fila_lastes_ned_og_vises_ikke_under_csp(self):
        admin = CustomUser.objects.create_user(username='stil_vl', password='x', role='admin',
                                               must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        c = Client()
        c.force_login(admin)
        svar = c.get(f'/vaktliste/api/vaktlister/{self.vl.pk}/fil/')
        self.assertEqual(svar.status_code, 200)
        self.assertTrue(svar['Content-Disposition'].startswith('attachment'), (
            'Fila vises nå i nettleseren: da gjelder style-src-elem, og <style> i '
            'vaktliste/fil.html trenger nonce — den rendres uten request, så send '
            'request.csp_nonce inn, og ta den ut av UNNTATT.'))

    def test_unntaket_er_bare_fila(self):
        self.assertEqual(UNNTATT, {'templates/vaktliste/fil.html'})


class StilattributteneGaarBareNedTests(SimpleTestCase):
    """Sperrehaken: senk tallene når en mal ryddes. Aldri opp."""

    MAKS_MALER = 216
    MAKS_JS = 104

    def test_malene(self):
        n = sum(len(re.findall(r'\sstyle="', _uten_malkommentarer(m.read_text(encoding='utf-8'))))
                for m in _maler())
        self.assertLessEqual(n, self.MAKS_MALER, 'Nytt style="…" i en mal — bruk en klasse')
        if n < self.MAKS_MALER:
            self.fail(f'Bra! {n} igjen i malene — senk MAKS_MALER til {n}.')

    def test_js(self):
        n = sum(len(re.findall(r'\sstyle=', _uten_jskommentarer(p.read_text(encoding='utf-8'))))
                for p in (ROT / 'static' / 'js').glob('*.js'))
        self.assertLessEqual(n, self.MAKS_JS, 'Nytt style= i JS-bygget markup — bruk en klasse eller el.style')
        if n < self.MAKS_JS:
            self.fail(f'Bra! {n} igjen i JS — senk MAKS_JS til {n}.')
