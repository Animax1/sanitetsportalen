"""
Tester for hard-delete av pasienter og recycle av pasientnummer.

Dekker:
  1. Slett siste pasient → next_patient_nr rulles tilbake
  2. Slett ikke-siste pasient → telleren uendret
  3. Slett to ganger på rad (siste, så ny siste) → telleren rulles tilbake to ganger
  4. Tom database edge case (slett siste, ny pasient skal få nummer 1)
  5. Ikke-admin kan ikke slette (403)
  6. Slett pasient som ikke finnes (404)
"""
import json

from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model

from patients.models import Patient, AppSetting
from patients.services import recycle_patient_nr_if_last

User = get_user_model()


class PatientDeleteSetupMixin:
    """Felles oppsett for slett-tester."""

    def setUp(self):
        # Admin-bruker for skrivetilgang
        self.admin = User.objects.create_user(
            username='admin_delete',
            password='passord123',
            role='admin',
            must_change_password=False,
        )
        # Read-write-bruker uten sletterett
        self.rw_user = User.objects.create_user(
            username='rw_delete',
            password='passord123',
            role='read_write',
            must_change_password=False,
        )
        # Sett aktivt år
        AppSetting.set('active_year', 2099)

        self.admin_client = Client()
        self.admin_client.force_login(self.admin)

        self.rw_client = Client()
        self.rw_client.force_login(self.rw_user)

    def _slett(self, pk, client=None):
        c = client or self.admin_client
        return c.delete(
            f'/api/patients/{pk}/',
            content_type='application/json',
        )

    def _opprett(self, nr):
        """Opprett pasient med gitt pasientnummer direkte i DB."""
        AppSetting.set('next_patient_nr', nr + 1)
        return Patient.objects.create(
            pasientnummer=nr,
            year=2099,
            problemstilling='Test',
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class RecycleFunctionTests(PatientDeleteSetupMixin, TestCase):
    """Enhetstester for recycle_patient_nr_if_last-funksjonen."""

    def test_slett_siste_rullerer_tilbake(self):
        """Slett siste pasient → next_patient_nr rulles tilbake."""
        p = self._opprett(5)
        # next_patient_nr er nå 6
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 6)

        resp = self._slett(p.pk)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['recycled_nr'])

        # Telleren skal ha gått tilbake til 5
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 5)

    def test_slett_ikke_siste_teller_uendret(self):
        """Slett ikke-siste pasient → telleren uendret."""
        p1 = self._opprett(5)
        p2 = self._opprett(6)
        # next_patient_nr er nå 7
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 7)

        # Slett første (nr 5) – det er ikke den siste
        resp = self._slett(p1.pk)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['recycled_nr'])

        # Telleren skal fremdeles være 7
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 7)

        # Rydd opp
        p2.delete()

    def test_slett_to_ganger_paa_rad(self):
        """Slett to ganger på rad (siste, så ny siste) → telleren rulles tilbake to ganger."""
        p1 = self._opprett(3)
        p2 = self._opprett(4)
        p3 = self._opprett(5)
        # next_patient_nr er nå 6

        # Slett p3 (nr 5 – den siste)
        resp = self._slett(p3.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['recycled_nr'])
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 5)

        # Slett p2 (nr 4 – ny siste)
        resp = self._slett(p2.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['recycled_nr'])
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 4)

        # Rydd opp
        p1.delete()

    def test_tom_db_slett_siste_ny_pasient_faar_nr_1(self):
        """Tom database edge case: slett eneste pasient, neste pasient skal få nummer 1."""
        p = self._opprett(1)
        # next_patient_nr er nå 2
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 2)

        resp = self._slett(p.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['recycled_nr'])

        # Telleren skal ha gått tilbake til 1
        self.assertEqual(int(AppSetting.get('next_patient_nr')), 1)

        # Ny pasient opprettet via API skal få nummer 1
        resp2 = self.admin_client.post(
            '/api/patients/',
            data=json.dumps({'problemstilling': 'Ny', 'inntid': '01.01.2099 10:00'}),
            content_type='application/json',
        )
        self.assertEqual(resp2.status_code, 201)
        self.assertEqual(resp2.json()['pasientnummer'], 1)

    def test_ikke_admin_kan_ikke_slette(self):
        """Ikke-admin (read_write) kan ikke slette pasient (403)."""
        p = self._opprett(7)
        resp = self._slett(p.pk, client=self.rw_client)
        self.assertEqual(resp.status_code, 403)
        # Pasienten skal fremdeles finnes
        self.assertTrue(Patient.objects.filter(pk=p.pk).exists())
        p.delete()

    def test_slett_pasient_som_ikke_finnes(self):
        """Slett pasient som ikke finnes → 404."""
        resp = self._slett(99999)
        self.assertEqual(resp.status_code, 404)
