"""Grensesnittet må gate på det samme som endepunktene gjør (§7.4).

Meldt fra staging: en konto med `skriv_full` ble satt ned til `les`, og
«Ny pasient» ble stående. Brukeren fikk opp registreringsskjemaet, fylte det
ut, og møtte 403 på lagre. Serveren var riktig hele tiden — `applyRoleVisibility`
gatet på `window.USER_ROLE`, altså rollen, som ikke lenger sier noe om hva du
får gjøre i modulen.

En knapp som fører til en vegg er verre enn ingen knapp: brukeren rekker å
gjøre arbeidet før hen får vite at det ikke gikk.
"""
import shutil
import unittest

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from patients import js_test_utils as jsu


def _bruker(navn, nivaa):
    bruker = CustomUser.objects.create_user(
        username=navn, password='x', role='read_write', must_change_password=False,
    )
    if nivaa:
        ModulTilgang.objects.create(
            bruker=bruker, modul_slug='patients', nivaa=nivaa)
    return bruker


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ModulTilgangIMalenTests(TestCase):
    """Malen må sende nivået, ikke rollen."""

    def _hent(self, navn, nivaa):
        c = Client()
        c.force_login(_bruker(navn, nivaa))
        resp = c.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode('utf-8')

    def test_nivaaet_sendes_til_klienten(self):
        self.assertIn('patients: "les"', self._hent('m_les', 'les'))
        self.assertIn('patients: "skriv_full"', self._hent('m_skriv', 'skriv_full'))

    def test_rollen_sendes_ikke_lenger(self):
        """`window.USER_ROLE` var kilden som gatet feil. Den skal være borte."""
        self.assertNotIn('USER_ROLE', self._hent('m_rolle', 'les'))

    def test_global_admin_merkes_eget(self):
        """Admin står utenfor modulaksen og trenger et eget felt."""
        admin = CustomUser.objects.create_user(
            username='m_admin', password='x', role='admin',
            must_change_password=False)
        c = Client()
        c.force_login(admin)
        html = c.get('/pasienter/').content.decode('utf-8')
        self.assertIn('admin: true', html)


@unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
class ApplyRoleVisibilityTests(TestCase):
    """Kjører funksjonen i node, med et stubbet DOM.

    Ikke en grep etter kodelinjer: det er oppførselen som betyr noe, og
    `patients/js_test_utils.py` finnes nettopp for dette.
    """

    HARNESS = ((jsu.UTILS_JS, ('modulNivaa', 'erAdmin', 'applyRoleVisibility')),)

    # Minimalt DOM: registrerer hvilke selektorer som ble skjult.
    PREAMBLE = '''
    globalThis.skjult = [];
    function lagEl() {
      return { style: {}, classList: { add(){}, remove(){}, toggle(){} } };
    }
    globalThis.document = {
      querySelectorAll(sel) {
        const el = lagEl();
        el.style = new Proxy({}, {
          set(o, k, v) { if (k === 'display' && v === 'none') skjult.push(sel); o[k] = v; return true; }
        });
        return [el];
      },
      querySelector() { return lagEl(); },
      getElementById() { return lagEl(); },
    };
    '''

    def _kjor(self, tilgang):
        snippet = (
            f'globalThis.window = {{ MODUL_TILGANG: {tilgang} }};\n'
            'applyRoleVisibility();\n'
            'console.log(JSON.stringify(skjult));'
        )
        ut = jsu.run_node(jsu.build_harness(self.HARNESS), snippet, self.PREAMBLE)
        import json
        return set(json.loads(ut.splitlines()[0]))

    def test_les_skjuler_skrivehandlingene(self):
        """Selve feilen fra staging: «Ny pasient» sto der for en `les`-bruker."""
        self.assertIn('.write-only', self._kjor('{patients: "les"}'))

    def test_skriv_full_beholder_dem(self):
        """Vern mot at testen over passerer fordi alt skjules for alle."""
        self.assertNotIn('.write-only', self._kjor('{patients: "skriv_full"}'))

    def test_manglende_global_skjuler_alt(self):
        """Standarden er ingen tilgang.

        Feiler malen, skal knappene forsvinne — ikke dukke opp.
        """
        skjult = self._kjor('{}')
        self.assertIn('.write-only', skjult)
        self.assertIn('.admin-only', skjult)

    def test_admin_beholder_adminhandlingene(self):
        skjult = self._kjor('{patients: "skriv_full", admin: true}')
        self.assertNotIn('.admin-only', skjult)

    def test_skriv_full_uten_admin_skjuler_adminhandlingene(self):
        skjult = self._kjor('{patients: "skriv_full"}')
        self.assertIn('.admin-only', skjult)
