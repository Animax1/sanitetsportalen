"""Den avviste CSRF-sjekken — se `core/csrf_feil.py`."""
from __future__ import annotations

import re

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from core.csrf_feil import MELDING


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class CsrfFeilTests(TestCase):

    def setUp(self):
        self.c = Client(enforce_csrf_checks=True)

    def test_skjemaet_faar_portalens_side_paa_norsk_med_stilene(self):
        svar = self.c.post('/accounts/login/', {'username': 'x', 'password': 'y'})
        self.assertEqual(svar.status_code, 403)
        tekst = svar.content.decode()
        self.assertIn('Siden må lastes på nytt', tekst)
        self.assertIn(MELDING, tekst)
        self.assertNotIn('CSRF verification failed', tekst)
        # Stilene slippes inn: blokka bærer headerens nonce.
        header = re.search(r"'nonce-([\w-]+)'", svar['Content-Security-Policy']).group(1)
        self.assertIn(f'<style nonce="{header}">', tekst)

    def test_apifetch_faar_json_som_klienten_kan_lese(self):
        admin = CustomUser.objects.create_user(username='csrf_adm', password='x', role='admin',
                                               must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        self.c.force_login(admin)
        svar = self.c.post('/backlog/api/innspill/', data='{}', content_type='application/json',
                           HTTP_X_PORTAL_INAKTIV='0')
        self.assertEqual(svar.status_code, 403)
        self.assertEqual(svar.json(), {'status': 'error', 'message': MELDING})

    def test_kjennetegnet_alene_holder(self):
        """Et skjema sendt med `apiFetch` (FormData) har ikke JSON-typen."""
        svar = self.c.post('/accounts/login/', {'username': 'x'}, HTTP_X_PORTAL_INAKTIV='3')
        self.assertEqual(svar['Content-Type'], 'application/json')

    def test_vanlig_403_sier_fortsatt_ingen_tilgang(self):
        bruker = CustomUser.objects.create_user(username='csrf_vanlig', password='x',
                                                must_change_password=False)
        # Medlem av portalen, som hver aktiv konto i prod (`accounts/0019`) — men uten rader.
        from accounts.test_helpers import medlemskap
        medlemskap(bruker)
        c = Client()
        c.force_login(bruker)
        svar = c.get('/admin/server-status/')
        self.assertEqual(svar.status_code, 403)
        self.assertIn('Ingen tilgang', svar.content.decode())
        self.assertNotIn(MELDING, svar.content.decode())
