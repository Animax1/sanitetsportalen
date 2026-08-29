"""Tester for kollaps av gamle vaktarkiv til aggregat (GDPR-tiltaksplan 3.1).

Etter 24 måneder slettes arkiverte pasientrader permanent og erstattes av
ferdig beregnet statistikk. Operasjonen er irreversibel, så testene dekker
både at den gjør riktig og at sikkerhetssperrene holder.

Kjør med: python manage.py test patients.tests_arkiv_kollaps
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from audit.models import AuditLog
from core.backup import KIND_MANUAL, create_backup, get_handler
from patients.models import AppSetting, ArkivertPasient, Patient, VaktArkiv
from patients.services import (
    arkiver_aktiv_vakt,
    compute_arkiv_full_stats,
    compute_arkiv_stats,
    kollaps_arkiv, vakt_for_year,
)
from accounts.test_helpers import gi_standardtilgang
from patients.test_helpers import sett_aktiv_vakt

User = get_user_model()


class KollapsTestMixin:

    def setUp(self):
        if get_handler('arkiv') is None or get_handler('patients') is None:
            from patients.backup import register_handlers
            register_handlers()

        self.vakt = sett_aktiv_vakt(2098)
        self.admin = User.objects.create_user(
            username='arkivar', password='passord', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')

    def _lag_pasienter(self):
        """Tre pasienter med tidsdata, så statistikken blir ikke-triviell."""
        Patient.objects.create(
            pasientnummer=1, vakt=vakt_for_year(2098), grovsortering='Grønn',
            problemstilling='Kramper', transport='Gående',
            inntid='01.06.2098 10:00', pabegynt='01.06.2098 10:05',
            utskrevet='01.06.2098 10:45', utskrevet_til='Hjem/park',
        )
        Patient.objects.create(
            pasientnummer=2, vakt=vakt_for_year(2098), grovsortering='Rød',
            problemstilling='Brystsmerter', transport='Beredskapsambulanse',
            inntid='01.06.2098 11:00', pabegynt='01.06.2098 11:02',
            utskrevet='01.06.2098 11:50', utskrevet_til='Sykehus',
        )
        Patient.objects.create(
            pasientnummer=3, vakt=vakt_for_year(2098), grovsortering='Gul',
            problemstilling='Magesmerter', transport='Lag',
            inntid='01.06.2098 12:00', pabegynt='01.06.2098 12:10',
        )

    def _arkiver_gammelt(self, dager=800, navn='Gammel vakt'):
        """Arkiver og daterer arkivet tilbake i tid."""
        arkiv, _ = arkiver_aktiv_vakt(navn, '', self.admin)
        VaktArkiv.objects.filter(pk=arkiv.pk).update(
            importert_at=timezone.now() - timedelta(days=dager)
        )
        arkiv.refresh_from_db()
        return arkiv

    def _ta_arkiv_backup(self):
        return create_backup(slug='arkiv', kind=KIND_MANUAL)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KollapsFunksjonTests(KollapsTestMixin, TestCase):
    """kollaps_arkiv() isolert."""

    def test_pasientrader_slettes(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        self.assertEqual(ArkivertPasient.objects.filter(arkiv=arkiv).count(), 3)

        slettet = kollaps_arkiv(arkiv)

        self.assertEqual(slettet, 3)
        self.assertEqual(ArkivertPasient.objects.filter(arkiv=arkiv).count(), 0)

    def test_arkivet_selv_bestaar(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)

        arkiv.refresh_from_db()
        self.assertTrue(VaktArkiv.objects.filter(pk=arkiv.pk).exists())
        self.assertEqual(arkiv.arrangement_navn, 'Gammel vakt')
        self.assertEqual(arkiv.antall_pasienter, 3)

    def test_statistikken_er_uendret_etter_kollaps(self):
        """Kjernekravet: tallene skal være identiske før og etter."""
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()

        basis_for = compute_arkiv_stats(arkiv)
        full_for = compute_arkiv_full_stats(arkiv)

        kollaps_arkiv(arkiv)
        arkiv.refresh_from_db()

        self.assertEqual(compute_arkiv_stats(arkiv), basis_for)
        self.assertEqual(compute_arkiv_full_stats(arkiv), full_for)

    def test_basistall_bevares(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)
        arkiv.refresh_from_db()

        basis = compute_arkiv_stats(arkiv)
        self.assertEqual(basis['total'], 3)
        self.assertEqual(basis['gronn'], 1)
        self.assertEqual(basis['gul'], 1)
        self.assertEqual(basis['rod'], 1)

    def test_avansert_statistikk_bevares(self):
        """Kruskal-Wallis og krysstabeller kan ikke regnes ut på nytt."""
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)
        arkiv.refresh_from_db()

        full = compute_arkiv_full_stats(arkiv)
        self.assertIn('crosstab_prob_triage', full)
        self.assertIn('kw_triage', full)
        self.assertIn('time_per_triage', full)
        self.assertEqual(full['summary']['total'], 3)

    def test_kollaps_er_idempotent(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)
        arkiv.refresh_from_db()

        self.assertEqual(kollaps_arkiv(arkiv), 0)

    def test_kollapset_flagg_settes(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        self.assertFalse(arkiv.er_kollapset)

        kollaps_arkiv(arkiv)
        arkiv.refresh_from_db()

        self.assertTrue(arkiv.er_kollapset)
        self.assertIsNotNone(arkiv.kollapset_at)
        self.assertNotEqual(arkiv.aggregat_sha256, '')

    def test_ingen_pasientopplysninger_igjen(self):
        """Ingen felt fra en enkeltpasient skal kunne leses ut."""
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)
        arkiv.refresh_from_db()

        rå = str(arkiv.aggregat)
        # Pasientnummer og tidsstempler er de mest identifiserende sporene.
        self.assertNotIn('pasientnummer', rå)
        self.assertNotIn('01.06.2098 10:00', rå)
        self.assertEqual(ArkivertPasient.objects.count(), 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KollapsIntegritetTests(KollapsTestMixin, TestCase):
    """SHA-256 etter kollaps."""

    def _hent_detalj(self, arkiv):
        c = Client()
        c.force_login(self.admin)
        return c.get(f'/pasienter/api/innstillinger/arkiv/{arkiv.pk}/')

    def test_ingen_tukling_rapporteres_etter_kollaps(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)

        data = self._hent_detalj(arkiv).json()
        self.assertFalse(data['tamper_detected'])
        self.assertTrue(data['kollapset'])

    def test_endret_aggregat_gir_tukling(self):
        """Integritetssjekken skal fortsatt fange endringer."""
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)
        arkiv.refresh_from_db()

        forfalsket = arkiv.aggregat
        forfalsket['basis']['total'] = 99
        VaktArkiv.objects.filter(pk=arkiv.pk).update(aggregat=forfalsket)

        data = self._hent_detalj(arkiv).json()
        self.assertTrue(
            data['tamper_detected'],
            'Endring i det frosne aggregatet skal oppdages',
        )

    def test_ikke_kollapset_arkiv_sjekkes_mot_radene(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()

        data = self._hent_detalj(arkiv).json()
        self.assertFalse(data['tamper_detected'])
        self.assertFalse(data['kollapset'])

    def test_full_stats_endepunkt_virker_etter_kollaps(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        kollaps_arkiv(arkiv)

        c = Client()
        c.force_login(self.admin)
        resp = c.get(f'/statistikk/api/kilde/patients/arkiv/{arkiv.pk}/full-stats/')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['summary']['total'], 3)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KollapsKommandoTests(KollapsTestMixin, TestCase):
    """Management-kommandoen, inkludert sikkerhetssperrene."""

    def _kjor(self, **kwargs):
        ut = StringIO()
        call_command('kollaps_arkiv', stdout=ut, stderr=ut, **kwargs)
        return ut.getvalue()

    def test_backup_sperre_stopper_kollaps(self):
        """Uten arkiv-backup skal ingenting slettes."""
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()

        ut = self._kjor()

        self.assertIn('HOPPET OVER', ut)
        arkiv.refresh_from_db()
        self.assertFalse(arkiv.er_kollapset)
        self.assertEqual(ArkivertPasient.objects.count(), 3)

    def test_kollaps_kjorer_med_backup_paa_plass(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        self._ta_arkiv_backup()

        self._kjor()

        arkiv.refresh_from_db()
        self.assertTrue(arkiv.er_kollapset)
        self.assertEqual(ArkivertPasient.objects.count(), 0)

    def test_sperren_kan_overstyres(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()

        self._kjor(ignorer_backup_sperre=True)

        arkiv.refresh_from_db()
        self.assertTrue(arkiv.er_kollapset)

    def test_dry_run_sletter_ingenting(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        self._ta_arkiv_backup()

        ut = self._kjor(dry_run=True)

        self.assertIn('Ville kollapset', ut)
        arkiv.refresh_from_db()
        self.assertFalse(arkiv.er_kollapset)
        self.assertEqual(ArkivertPasient.objects.count(), 3)

    def test_ferske_arkiv_rores_ikke(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt(dager=100)
        self._ta_arkiv_backup()

        self._kjor()

        arkiv.refresh_from_db()
        self.assertFalse(
            arkiv.er_kollapset,
            'Arkiv yngre enn 24 måneder skal ikke kollapses',
        )

    def test_grensen_kan_overstyres(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt(dager=100)
        self._ta_arkiv_backup()

        self._kjor(days=90)

        arkiv.refresh_from_db()
        self.assertTrue(arkiv.er_kollapset)

    def test_kollaps_loggfores_i_audit(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        self._ta_arkiv_backup()

        self._kjor()

        self.assertTrue(
            AuditLog.objects.filter(
                table_name='patients_vaktarkiv',
                record_id=arkiv.pk,
                field_name='kollapset_at',
            ).exists(),
            'Irreversibel sletting skal etterlate et revisjonsspor',
        )

    def test_allerede_kollapset_hoppes_over(self):
        self._lag_pasienter()
        arkiv = self._arkiver_gammelt()
        self._ta_arkiv_backup()
        self._kjor()

        ut = self._kjor()

        self.assertIn('Ingen arkiv eldre enn', ut)
