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
class SchedulerRunBackupTests(TestCase):
    """Tester for _run_backup_for_module – den faktiske utførelsen."""

    def setUp(self):
        _ensure_handler()
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
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
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='X')

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
