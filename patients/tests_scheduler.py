"""Tester for in-process backup-scheduler — per-modul (Fase 4).

Den gamle singleton-baserte scheduleren er erstattet med en per-modul-flyt
som leser fra ``core.models.ModuleBackupConfig``. Disse testene verifiserer
at den nye scheduleren respekterer:

- ``enabled=False`` stopper backup
- ``interval_minutes=0`` stopper backup
- ``last_run_at`` styrer om det er tid for ny backup
- Database-låsen oppdaterer ``last_run_at`` før selve backupen kjøres
- Feil under backup ruller tilbake ``last_run_at``-oppdateringen

Mer omfattende dekning ligger i ``core.tests_backup.SchedulerTests``.
"""
import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from core.models import ModuleBackupConfig
from patients import backup_scheduler
from patients.backup import register_handlers
from patients.models import Backup, Patient
from patients.services import vakt_for_year
from accounts.test_helpers import gi_standardtilgang


def _ensure_handler() -> None:
    from core.backup import get_handler
    if get_handler('patients') is None:
        register_handlers()


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SchedulerShouldRunTests(TestCase):
    """Tester for _should_run_now-logikken (per-modul-config)."""

    def test_interval_av_returnerer_false(self):
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 0
        cfg.last_run_at = None
        self.assertFalse(backup_scheduler._should_run_now(cfg))

    def test_disabled_returnerer_false(self):
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = False
        cfg.interval_minutes = 60
        cfg.last_run_at = None
        self.assertFalse(backup_scheduler._should_run_now(cfg))

    def test_ingen_last_run_returnerer_true(self):
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60
        cfg.last_run_at = None
        self.assertTrue(backup_scheduler._should_run_now(cfg))

    def test_nylig_kjort_returnerer_false(self):
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=5)
        self.assertFalse(backup_scheduler._should_run_now(cfg))

    def test_for_lenge_siden_returnerer_true(self):
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=61)
        self.assertTrue(backup_scheduler._should_run_now(cfg))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SchedulerFinnerModulerTests(TestCase):
    """Registeret er fasit for hvilke moduler som finnes, ikke konfigtabellen.

    Scheduleren leste tidligere `ModuleBackupConfig`-radene direkte. Radene
    ble opprettet først når en admin åpnet `/portal-admin/backup/`, så en
    nyregistrert modul hadde ingen automatisk backup før noen tilfeldigvis
    besøkte den siden — og for et arkiv betyr manglende backup at kollapsen
    nekter å kjøre, altså en feil som først viser seg to år senere.
    """

    def setUp(self):
        from core.backup import registrer_alle_moduler
        registrer_alle_moduler()

    def test_alle_registrerte_moduler_er_med(self):
        from core.backup import all_handlers

        slugs = {slug for slug, _ in backup_scheduler._konfigurasjoner()}
        self.assertEqual(slugs, {h.slug for h in all_handlers()})
        # Konkret: oppdragsmodulen kom til i fase 7 og skal være dekket.
        self.assertIn('oppdrag', slugs)
        self.assertIn('oppdrag_arkiv', slugs)

    def test_modul_uten_konfigrad_faar_en(self):
        """Selve hullet: uten rad var modulen usynlig for scheduleren."""
        ModuleBackupConfig.objects.all().delete()

        konfig = dict(backup_scheduler._konfigurasjoner())

        self.assertIn('oppdrag_arkiv', konfig)
        self.assertTrue(
            ModuleBackupConfig.objects.filter(module_slug='oppdrag_arkiv').exists())
        # Standardverdiene gjelder — modulen er påslått fra første stund.
        self.assertTrue(konfig['oppdrag_arkiv'].enabled)

    def test_ny_modul_er_klar_for_backup_med_en_gang(self):
        """`last_run_at` er tom på en fersk rad, altså forfaller den straks."""
        ModuleBackupConfig.objects.all().delete()

        konfig = dict(backup_scheduler._konfigurasjoner())
        self.assertTrue(backup_scheduler._should_run_now(konfig['oppdrag']))

    def test_opprettelsen_er_idempotent(self):
        ModuleBackupConfig.objects.all().delete()
        backup_scheduler._konfigurasjoner()
        backup_scheduler._konfigurasjoner()

        self.assertEqual(
            ModuleBackupConfig.objects.filter(module_slug='oppdrag').count(), 1)

    def test_konfig_uten_handler_hoppes_over(self):
        """En rest etter en modul som er fjernet fra koden skal ikke telle."""
        ModuleBackupConfig.objects.create(module_slug='fjernet_modul')

        slugs = {slug for slug, _ in backup_scheduler._konfigurasjoner()}
        self.assertNotIn('fjernet_modul', slugs)

    def test_deaktivert_modul_kjorer_ikke(self):
        """Raden opprettes, men admin bestemmer fortsatt om den er på."""
        cfg = ModuleBackupConfig.get_or_default('oppdrag')
        cfg.enabled = False
        cfg.save(update_fields=['enabled'])

        konfig = dict(backup_scheduler._konfigurasjoner())
        self.assertFalse(backup_scheduler._should_run_now(konfig['oppdrag']))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SchedulerRunBackupTests(TestCase):
    """Tester for _run_backup_for_module – den faktiske utførelsen."""

    def setUp(self):
        _ensure_handler()
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.backup_dir = Path('/tmp/test-backups-scheduler')
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        # Rydd opp gamle filer.
        for pattern in ('backup-*.json.gz', '.restore-tmp-*.json'):
            for f in self.backup_dir.glob(pattern):
                f.unlink(missing_ok=True)
        # Reset throttle-state mellom tester.
        backup_scheduler._last_check_ts = 0.0
        with backup_scheduler._running_lock:
            backup_scheduler._is_running = False
        # Patient-data slik at dumpdata ikke er tom.
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')

    def tearDown(self):
        import gc
        gc.collect()
        for pattern in ('backup-*.json.gz', '.restore-tmp-*.json'):
            for f in self.backup_dir.glob(pattern):
                f.unlink(missing_ok=True)

    def test_run_oppretter_auto_backup(self):
        """Når konfig sier det er tid, skal en auto-backup opprettes."""
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=61)
        cfg.save()

        count_before = Backup.objects.filter(
            module_slug='patients', kind='auto',
        ).count()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup_scheduler._run_backup_for_module('patients')

        count_after = Backup.objects.filter(
            module_slug='patients', kind='auto',
        ).count()
        self.assertEqual(count_after, count_before + 1,
                         'En ny auto-backup skal være opprettet')

        cfg.refresh_from_db()
        self.assertIsNotNone(cfg.last_run_at)
        elapsed = timezone.now() - cfg.last_run_at
        self.assertLess(elapsed.total_seconds(), 10,
                        'last_run_at skal være akkurat nå')

    def test_run_hopper_over_hvis_nylig(self):
        """Når konfig sier at det ikke er tid, skal ingen backup opprettes."""
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=5)
        cfg.save()

        count_before = Backup.objects.filter(
            module_slug='patients', kind='auto',
        ).count()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup_scheduler._run_backup_for_module('patients')

        count_after = Backup.objects.filter(
            module_slug='patients', kind='auto',
        ).count()
        self.assertEqual(count_after, count_before,
                         'Ingen ny backup skal opprettes')

    def test_run_hopper_over_hvis_disabled(self):
        """Når enabled=False, skal ingen backup opprettes."""
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = False
        cfg.interval_minutes = 60
        cfg.last_run_at = None
        cfg.save()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup_scheduler._run_backup_for_module('patients')

        self.assertEqual(
            Backup.objects.filter(module_slug='patients', kind='auto').count(),
            0,
        )

    def test_feil_under_backup_ruller_tilbake_last_run(self):
        """Hvis create_backup feiler, skal last_run_at rulles tilbake."""
        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60
        original_last_run = timezone.now() - timedelta(minutes=61)
        cfg.last_run_at = original_last_run
        cfg.save()

        # `create_backup` importeres lazy i scheduleren, så vi patcher
        # selve kilden i core.backup.
        with patch('core.backup.create_backup',
                   side_effect=RuntimeError('simulert feil')):
            # _run_backup_for_module sluker unntaket via except-blokk
            backup_scheduler._run_backup_for_module('patients')

        cfg.refresh_from_db()
        # Transaksjonen skal ha rullet tilbake last_run_at-oppdateringen
        self.assertEqual(
            cfg.last_run_at.replace(microsecond=0),
            original_last_run.replace(microsecond=0),
            'last_run_at skal rulles tilbake ved feil',
        )
