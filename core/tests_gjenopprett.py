"""`manage.py gjenopprett` — gjenoppretting fra kommandolinja (13. sep. 2026).

Veien fantes ikke før: `hent_offsite` henter og dekrypterer fila, men rører
ikke databasen, og i en tom base finnes det ingen å logge inn som. Katastrofe-
veien gikk altså gjennom en nettleser uten bruker.

Testene her handler mest om **sperrene**. Selve gjenopprettingen er den samme
funksjonen knappen kaller, og er dekket i `core/tests_backup.py`; det som er
nytt og kan gå galt, er hva kommandoen nekter å gjøre.
"""
from __future__ import annotations

import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from audit.models import AuditLog
from core.backup import (
    KIND_MANUAL,
    create_backup,
    registrer_alle_moduler,
    restore_backup,
)
from core.models import Backup
from patients.services import vakt_for_year

TEST_BACKUP_DIR = Path('/tmp/test-backups-gjenopprett')


def _backup_dir() -> Path:
    TEST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for f in TEST_BACKUP_DIR.glob('*'):
        if f.is_file():
            f.unlink(missing_ok=True)
    return TEST_BACKUP_DIR


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class GjenopprettKommandoTests(TestCase):

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _backup_dir()
        self.miljo = patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)})

    def _kall(self, *args):
        ut = StringIO()
        with self.miljo:
            call_command('gjenopprett', *args, stdout=ut, stderr=StringIO())
        return ut.getvalue()

    def _lag_fil(self, slug='patients'):
        with self.miljo:
            return create_backup(slug=slug, kind=KIND_MANUAL)

    # ── Utlisting ────────────────────────────────────────────────────────────

    def test_list_uten_filer_sier_hvor_man_henter_dem(self) -> None:
        ut = self._kall('--list')
        self.assertIn('hent_offsite', ut)

    def test_list_viser_modul_og_filnavn(self) -> None:
        backup = self._lag_fil()
        ut = self._kall('--list')
        self.assertIn(backup.filename, ut)
        self.assertIn('patients', ut)

    # ── Sperrene ─────────────────────────────────────────────────────────────

    def test_uten_ja_og_uten_terminal_sier_hva_som_mangler(self) -> None:
        """`railway ssh -- <kommando>` har ingen terminal. Uten denne sjekken
        ville `input()` hengt til noe ga opp — i en katastrofe."""
        self._lag_fil()
        with self.assertRaises(CommandError) as ctx:
            self._kall('--siste', 'patients')
        self.assertIn('--ja', str(ctx.exception))

    def test_hel_base_krever_eget_flagg(self) -> None:
        """Slugen leses av filnavnet, så flagget er teknisk overflødig — men
        hele databasen skal ikke kunne erstattes av en skrivefeil."""
        self._lag_fil(slug='full')
        with self.assertRaises(CommandError) as ctx:
            self._kall('--siste', 'full', '--ja')
        self.assertIn('--full', str(ctx.exception))
        self.assertIn('HELE databasen', str(ctx.exception))

    def test_hel_base_med_flagget_gaar_gjennom(self) -> None:
        self._lag_fil(slug='full')
        ut = self._kall('--siste', 'full', '--full', '--ja')
        self.assertIn('Gjenopprettet full', ut)

    def test_ukjent_modul_avvises(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self._kall('--siste', 'finnes-ikke', '--ja')
        self.assertIn('backup-handler', str(ctx.exception))

    def test_fil_som_ikke_finnes_avvises(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self._kall('backup-patients-manual-20260101-000000-000000.json.gz', '--ja')
        self.assertIn('--list', str(ctx.exception))

    def test_uten_argumenter_sier_hva_som_finnes(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self._kall('--ja')
        for forventet in ('--siste', '--hent', '--list'):
            with self.subTest(flagg=forventet):
                self.assertIn(forventet, str(ctx.exception))

    def test_hent_uten_offsite_sier_hvilke_variabler_som_mangler(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self._kall('--hent', 'backup-patients-x.json.gz', '--ja')
        self.assertIn('OFFSITE_S3_BUCKET', str(ctx.exception))

    def test_interaktiv_bekreftelse_maa_stemme(self) -> None:
        self._lag_fil()
        with patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', return_value='feil-slug'):
            with self.assertRaises(CommandError) as ctx:
                self._kall('--siste', 'patients')
        self.assertIn('Avbrutt', str(ctx.exception))

    # ── Valg av fil ──────────────────────────────────────────────────────────

    def test_siste_hopper_over_pre_restore(self) -> None:
        """Et pre-restore-øyeblikksbilde er tilstanden man nettopp gikk bort
        fra. Å tilby det som «siste» ville gitt akkurat den tilbake."""
        vakt = vakt_for_year(2026)
        from patients.models import Patient

        Patient.objects.create(pasientnummer=1, vakt=vakt, problemstilling='Original')
        onsket = self._lag_fil()
        with self.miljo:
            restore_backup(onsket)   # lager en pre_restore som er nyere

        self.assertTrue(
            Backup.objects.filter(kind='pre_restore', module_slug='patients').exists())
        ut = self._kall('--siste', 'patients', '--ja')
        self.assertIn(onsket.filename, ut)
        self.assertNotIn('pre_restore', ut.split('Gjenopprettet')[-1])

    def test_fil_uten_rad_far_en(self) -> None:
        """Fila kan ligge på volumet uten en `Backup`-rad — hentet inn for
        hånd, eller fordi basen er ny."""
        backup = self._lag_fil()
        filnavn = backup.filename
        Backup.objects.filter(pk=backup.pk).delete()

        self._kall(filnavn, '--ja')
        self.assertTrue(Backup.objects.filter(filename=filnavn).exists())

    # ── Effekt og spor ───────────────────────────────────────────────────────

    def test_gjenoppretter_faktisk_dataene(self) -> None:
        from patients.models import Patient

        vakt = vakt_for_year(2026)
        Patient.objects.create(pasientnummer=42, vakt=vakt, problemstilling='Før')
        backup = self._lag_fil()
        Patient.objects.all().delete()

        self._kall(backup.filename, '--ja')
        self.assertEqual(Patient.objects.get().pasientnummer, 42)

    def test_skriver_en_auditrad_med_kilde(self) -> None:
        """Sto loggingen i viewet, ville katastrofeveien vært den eneste som
        ikke etterlot seg et spor."""
        backup = self._lag_fil()
        for_ = AuditLog.objects.filter(field_name='restore').count()

        self._kall(backup.filename, '--ja')

        rader = AuditLog.objects.filter(field_name='restore').order_by('-created_at')
        self.assertEqual(rader.count(), for_ + 1)
        rad = rader.first()
        self.assertEqual(rad.old_value, 'kommandolinja')
        self.assertEqual(rad.new_value, backup.filename)
        self.assertIsNone(rad.user, 'Kommandolinja har ingen innlogget bruker.')

    def test_grensesnittet_skriver_ogsa_bare_en_rad(self) -> None:
        """Auditraden flyttet inn i tjenesten 13. sep. 2026. Ble den stående i
        viewet også, ville hver gjenoppretting derfra gitt to rader."""
        from accounts.models import CustomUser
        from accounts.test_helpers import gi_standardtilgang
        from django.test import Client

        admin = CustomUser.objects.create_user(
            username='adm', password='pwd', role='admin',
            must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        backup = self._lag_fil()

        klient = Client()
        klient.force_login(admin)
        for_ = AuditLog.objects.filter(field_name='restore').count()
        with self.miljo:
            klient.post(f'/portal-admin/backup/patients/restore/{backup.pk}/',
                        data={'confirm_slug': 'patients'})

        rader = AuditLog.objects.filter(field_name='restore')
        self.assertEqual(rader.count(), for_ + 1)
        self.assertEqual(rader.order_by('-created_at').first().old_value,
                         'grensesnittet')

    def test_bekreftelsen_sier_hva_som_slettes(self) -> None:
        from patients.models import Patient

        vakt = vakt_for_year(2026)
        for nr in range(1, 4):
            Patient.objects.create(pasientnummer=nr, vakt=vakt, problemstilling='X')
        backup = self._lag_fil()

        ut = self._kall(backup.filename, '--ja')
        self.assertIn('Slettes og erstattes', ut)
        self.assertIn('patients.Patient: 3', ut)
