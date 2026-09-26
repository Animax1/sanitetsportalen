"""Server-status i node (26. sep. 2026, G1).

Skriptet sto inline i malen til i dag, der ingen node-test kunne hente det.
Reglene som avgjør noe prøves her; resten er tegning man ser.
"""
import json
import unittest

from django.test import SimpleTestCase, TestCase

from patients.js_test_utils import JS_DIR, PORTAL_UTILS_JS, build_harness, node_available, run_node

STATUS_JS = JS_DIR / 'portal-status.js'

DOM = """
const elementer = {};
globalThis.document = { getElementById: (id) => (elementer[id] ||= { textContent: '', innerHTML: '', className: '' }) };
"""


@unittest.skipUnless(node_available(), 'node mangler')
class ServerStatusJsTests(SimpleTestCase):

    def _kjor(self, navn, kode):
        harness = build_harness(((PORTAL_UTILS_JS, ('escHtmlValue',)), (STATUS_JS, navn)))
        return run_node(harness, kode, preamble=DOM)

    def test_aktivitet_grensene(self):
        ut = self._kjor(('aktivitetstekst', 'aktivitetsklasse'), """
console.log(JSON.stringify([null, 0, 299, 300, 3599, 3600, 7200].map(
  (s) => [aktivitetstekst(s), aktivitetsklasse(s)])));""")
        self.assertEqual(json.loads(ut.splitlines()[0]), [
            ['ukjent', 'akt-ukjent'], ['aktiv nå', 'akt-aktiv'], ['aktiv nå', 'akt-aktiv'],
            ['inaktiv 5 min', 'akt-rolig'], ['inaktiv 60 min', 'akt-rolig'],
            ['inaktiv 1 time', 'akt-borte'], ['inaktiv 2 timer', 'akt-borte']])

    def test_tregeste_escaper_stien_og_viser_null(self):
        ut = self._kjor(('renderTregeste',), """
renderTregeste([{path: '/x/<img src=y>', count: 3, p95_ms: 0}]);
console.log(elementer['tregeste'].innerHTML);""")
        self.assertIn('&lt;img src=y&gt;', ut)
        self.assertNotIn('<img', ut)
        self.assertIn('>0 ms<', ut, 'escHtmlValue: 0 skal vises, ikke bli tom')

    def test_konfig_escaper_noekkel_og_verdi(self):
        ut = self._kjor(('setVal', 'datoKlokke', 'renderKonfig'), """
renderKonfig({rader: [{nokkel: '<b>', verdi: '"><script>', ok: false}], versjon: {}});
console.log(elementer['konfig-rader'].innerHTML);""")
        self.assertIn('&lt;b&gt;', ut)
        self.assertIn('&quot;&gt;&lt;script&gt;', ut)
        self.assertNotIn('<script>', ut)


class SidenLasterSkriptetTests(TestCase):
    """Malen bærer URL-ene og laster fila — og har ikke fått inline-JS tilbake."""

    def test_siden(self):
        import re
        from django.test import Client, override_settings
        from django.urls import reverse
        from accounts.models import CustomUser
        admin = CustomUser.objects.create_user(username='status_g1', password='x', role='admin',
                                               must_change_password=False)
        c = Client()
        c.force_login(admin)
        with override_settings(SECURE_SSL_REDIRECT=False):
            html = c.get('/portal-admin/server-status/').content.decode()
        for attr, navn in (('json', 'admin_server_status_json'), ('sessions', 'admin_sessions_list'),
                           ('kill', 'admin_session_kill'), ('kill-all', 'admin_session_kill_all')):
            self.assertIn(f'data-url-{attr}="{reverse("portaladmin:" + navn)}"', html)
        self.assertRegex(html, r'<script src="[^"]*portal-utils[^"]*\.js"></script>\s*'
                               r'<script src="[^"]*portal-status[^"]*\.js"></script>')
        inline = [s for s in re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
                  if s.strip()]
        self.assertFalse(any('refresh' in s or 'STATUS_URLS' in s for s in inline), inline)
