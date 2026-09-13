"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 1 — pasientmodulen.

L2: en pasient i en annen vakt kan ikke redigeres eller slettes via pk.
"""
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from patients.models import Patient
from patients.test_helpers import sett_aktiv_vakt


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PasientScopetTilAktivVaktTests(TestCase):
    def setUp(self):
        self.forrige = sett_aktiv_vakt(2097)
        self.gammel = Patient.objects.create(pasientnummer=1, vakt=self.forrige, grovsortering='Rød')
        self.vakt = sett_aktiv_vakt(2098)
        self.naa = Patient.objects.create(pasientnummer=1, vakt=self.vakt, grovsortering='Gul')
        adm = CustomUser.objects.create_user(username='adm_p', password='x', role='admin',
                                             must_change_password=False)
        gi_standardtilgang(adm, 'admin')
        self.c = Client(); self.c.force_login(adm)

    def test_annen_vakt_er_404(self):
        for metode in ('put', 'delete'):
            res = getattr(self.c, metode)(f'/pasienter/api/patients/{self.gammel.pk}/',
                                          content_type='application/json', data={'grovsortering': 'Grønn'})
            self.assertEqual(res.status_code, 404, metode)
        self.gammel.refresh_from_db()
        self.assertEqual(self.gammel.grovsortering, 'Rød')

    def test_aktiv_vakt_som_foer(self):
        res = self.c.put(f'/pasienter/api/patients/{self.naa.pk}/', content_type='application/json',
                         data={'grovsortering': 'Grønn'})
        self.assertEqual(res.status_code, 200, res.content)
