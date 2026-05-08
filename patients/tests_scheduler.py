"""Tester for in-process backup-scheduler."""
import os
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from patients.models import BackupConfig, Backup, Patient
from patients import backup_scheduler


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SchedulerShouldRunTests(TestCase):
    """Tester for _should_run_now-logikken."""

    def test_interval_av_returnerer_false(self):
        cfg = BackupConfig.get()
        cfg.interval_minutes = 0
        cfg.last_run_at = None
        self.assertFalse(backup_scheduler._should_run_now(cfg))

    def test_ingen_last_run_returnerer_true(self):
        cfg = BackupConfig.get()
        cfg.interval_minutes = 60
        cfg.last_run_at = None
        self.assertTrue(backup_scheduler._should_run_now(cfg))

    def test_nylig_kjort_returnerer_false(self):
        cfg = BackupConfig.get()
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=5)
        self.assertFalse(backup_scheduler._should_run_now(cfg))

    def test_for_lenge_siden_returnerer_true(self):
        cfg = BackupConfig.get()
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=61)
        self.assertTrue(backup_scheduler._should_run_now(cfg))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SchedulerRunBackupTests(TestCase):
    """Tester for _run_backup_with_db_lock – den faktiske utførelsen."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        self.backup_dir = Path('/tmp/test-backups-scheduler')
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        # Reset throttle-state mellom tester
        backup_scheduler._last_check_ts = 0.0
        with backup_scheduler._running_lock:
            backup_scheduler._is_running = False

    def tearDown(self):
        import gc, time as _time
        gc.collect()
        for pattern in ('backup-*.json.gz', '.restore-tmp-*.json'):
            for f in self.backup_dir.glob(pattern):
                for _ in range(5):
                    try:
                        f.unlink(missing_ok=True)
                        break
                    except PermissionError:
                        gc.collect()
                        _time.sleep(0.1)

    def test_run_oppretter_auto_backup(self):
        """Når konfig sier det er tid, skal en auto-backup opprettes."""
        cfg = BackupConfig.get()
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=61)
        cfg.save()

        count_before = Backup.objects.filter(kind='auto').count()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup_scheduler._run_backup_with_db_lock()

        count_after = Backup.objects.filter(kind='auto').count()
        self.assertEqual(count_after, count_before + 1,
                         'En ny auto-backup skal v\u00e6re opprettet')

        # last_run_at skal v\u00e6re oppdatert
        cfg.refresh_from_db()
        self.assertIsNotNone(cfg.last_run_at)
        elapsed = timezone.now() - cfg.last_run_at
        self.assertLess(elapsed.total_seconds(), 10,
                        'last_run_at skal v\u00e6re akkurat n\u00e5')

    def test_run_hopper_over_hvis_nylig(self):
        """Når konfig sier at det ikke er tid, skal ingen backup opprettes."""
        cfg = BackupConfig.get()
        cfg.interval_minutes = 60
        cfg.last_run_at = timezone.now() - timedelta(minutes=5)
        cfg.save()

        count_before = Backup.objects.filter(kind='auto').count()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup_scheduler._run_backup_with_db_lock()

        count_after = Backup.objects.filter(kind='auto').count()
        self.assertEqual(count_after, count_before,
                         'Ingen ny backup skal opprettes')

    def test_run_hopper_over_hvis_av(self):
        """N\u00e5r intervall=0 (Av), skal ingen backup opprettes."""
        cfg = BackupConfig.get()
        cfg.interval_minutes = 0
        cfg.last_run_at = None
        cfg.save()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup_scheduler._run_backup_with_db_lock()

        self.assertEqual(Backup.objects.filter(kind='auto').count(), 0)

    def test_feil_under_backup_ruller_tilbake_last_run(self):
        """Hvis create_backup feiler, skal last_run_at rulles tilbake i transaksjonen."""
        cfg = BackupConfig.get()
        cfg.interval_minutes = 60
        original_last_run = timezone.now() - timedelta(minutes=61)
        cfg.last_run_at = original_last_run
        cfg.save()

        with patch('patients.backup_scheduler.create_backup',
                   side_effect=RuntimeError('simulert feil')):
            # _run_backup_with_db_lock sluker unntaket via except-blokk
            backup_scheduler._run_backup_with_db_lock()

        cfg.refresh_from_db()
        # Transaksjonen skal ha rullet tilbake last_run_at-oppdateringen
        self.assertEqual(
            cfg.last_run_at.replace(microsecond=0),
            original_last_run.replace(microsecond=0),
            'last_run_at skal rulles tilbake ved feil',
        )
