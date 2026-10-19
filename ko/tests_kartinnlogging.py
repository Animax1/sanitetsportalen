"""«Åpne kartet» i KO (19. okt. 2026, `docs/PLAN_FELLES_INNLOGGING.md`)."""
from __future__ import annotations

import re

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_modultilgang_oppdater
from core import kartkobling
from core.models import AppSetting
from core.tests_kartinnlogging import les_billett

NOKKEL = 'k' * 64


def _bruker(navn, **kwargs):
    return CustomUser.objects.create_user(
        username=navn, password='x', must_change_password=False, **kwargs)


def _gi_ko(bruker, nivaa='les'):
    return gi_modultilgang_oppdater(bruker=bruker, modul_slug='ko', defaults={'nivaa': nivaa})


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False,
                   KART_URL='https://testkart.sanitet.net', KART_INNLOGGING_NOKKEL=NOKKEL)
class AapneKartetTests(TestCase):

    def setUp(self):
        self.client = Client()
        AppSetting.set(kartkobling.INNLOGGING_NOKKEL, 'true')

    def _logg_inn(self, nivaa='les', **kwargs):
        bruker = _bruker(f'ko-{nivaa}', **kwargs)
        _gi_ko(bruker, nivaa)
        self.client.force_login(bruker)
        return bruker

    def _billett(self, svar) -> dict:
        treff = re.search(r'name="billett" value="([^"]+)"', svar.content.decode())
        self.assertIsNotNone(treff, 'svaret har ingen billett')
        return les_billett(treff.group(1))

    # --- Knappen ----------------------------------------------------------------------

    def test_knappen_vises_naar_alt_er_paa(self):
        self._logg_inn()
        self.assertContains(self.client.get('/ko/'), 'action="/ko/kart/"')

    def test_ingen_knapp_naar_admin_har_slatt_av(self):
        AppSetting.set(kartkobling.INNLOGGING_NOKKEL, 'false')
        self._logg_inn()
        self.assertNotContains(self.client.get('/ko/'), 'action="/ko/kart/"')

    def test_ingen_knapp_uten_nokkel_i_miljoet(self):
        self._logg_inn()
        with self.settings(KART_INNLOGGING_NOKKEL=''):
            self.assertNotContains(self.client.get('/ko/'), 'action="/ko/kart/"')

    # --- Endepunktet ------------------------------------------------------------------

    def test_ko_les_far_billett_til_a_se(self):
        bruker = self._logg_inn('les', fullt_navn='Kari Nordmann')
        svar = self.client.post('/ko/kart/')
        self.assertEqual(svar.status_code, 200)
        self.assertContains(svar, 'action="https://testkart.sanitet.net/konto/fra-portalen/"')
        data = self._billett(svar)
        self.assertEqual((data['bruker'], data['navn'], data['skriv']),
                         (bruker.pk, 'Kari Nordmann', False))
        self.assertEqual(data['aud'], 'testkart.sanitet.net')

    def test_ko_skriv_full_far_billett_til_a_tegne(self):
        self._logg_inn('skriv_full')
        self.assertTrue(self._billett(self.client.post('/ko/kart/'))['skriv'])

    def test_uten_fullt_navn_brukes_brukernavnet(self):
        self._logg_inn('les')
        self.assertEqual(self._billett(self.client.post('/ko/kart/'))['navn'], 'ko-les')

    def test_slugen_er_portalen_brukeren_star_i(self):
        from core.portal import gjeldende_portal
        self._logg_inn()
        self.assertEqual(self._billett(self.client.post('/ko/kart/'))['portal'],
                         gjeldende_portal().slug)

    def test_slugen_folger_portalen_ikke_standarden(self):
        """«standard» er også det kartet gjetter uten slug — med den alene ville en hardkodet
        verdi gått grønn."""
        from types import SimpleNamespace
        from unittest import mock
        self._logg_inn()
        with mock.patch('core.portal.gjeldende_portal', return_value=SimpleNamespace(slug='brann')):
            self.assertEqual(self._billett(self.client.post('/ko/kart/'))['portal'], 'brann')

    def test_slugen_kan_ikke_velges_av_klienten(self):
        self._logg_inn()
        svar = self.client.post('/ko/kart/', {'portal': 'en-annen'})
        self.assertNotEqual(self._billett(svar)['portal'], 'en-annen')

    def test_bryteren_av_stenger_endepunktet_ikke_bare_knappen(self):
        AppSetting.set(kartkobling.INNLOGGING_NOKKEL, 'false')
        self._logg_inn()
        svar = self.client.post('/ko/kart/')
        self.assertEqual(svar.status_code, 403)
        self.assertNotContains(svar, 'name="billett"', status_code=403)

    def test_uten_nokkel_stengt(self):
        self._logg_inn()
        with self.settings(KART_INNLOGGING_NOKKEL=''):
            self.assertEqual(self.client.post('/ko/kart/').status_code, 403)

    def test_uten_ko_ingen_billett(self):
        self.client.force_login(_bruker('uten'))
        self.assertEqual(self.client.post('/ko/kart/').status_code, 403)

    def test_get_gir_ingen_billett(self):
        """Billetten skal aldri kunne hentes med en lenke — den ville stått i en URL."""
        self._logg_inn()
        self.assertEqual(self.client.get('/ko/kart/').status_code, 405)

    def test_csp_slipper_skjemaet_ut_til_kartet_bare_her(self):
        self._logg_inn()
        csp = self.client.post('/ko/kart/')['Content-Security-Policy']
        self.assertIn("form-action 'self' https://testkart.sanitet.net", csp)
        self.assertIn("script-src 'self' 'nonce-", csp, 'resten av CSP-en står')
        self.assertIn("form-action 'self';", self.client.get('/ko/')['Content-Security-Policy'])

    def test_skriptet_som_poster_videre_har_nonce(self):
        self._logg_inn()
        svar = self.client.post('/ko/kart/')
        nonce = re.search(r"'nonce-([^']+)'", svar['Content-Security-Policy']).group(1)
        self.assertContains(svar, f'<script nonce="{nonce}">')

    def test_svaret_caches_ikke(self):
        self._logg_inn()
        self.assertIn('no-store', self.client.post('/ko/kart/')['Cache-Control'])
