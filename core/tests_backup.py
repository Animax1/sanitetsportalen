"""Tester for Fase 4 — per-modul backup-rammeverk i core.backup.

Dekker:
- Hash-skip for auto-backup når innhold er uendret
- Manual / pre_restore lagres alltid (hash-skip gjelder kun auto)
- 50-cap fjerner eldste først, beskytter pre_restore
- Restore gjenoppretter modellinstanser nøyaktig
- Pre-restore-snapshot lages før destruktiv restore
- Restore-bekreftelse via slug (BackupRestoreConfirmForm)
- Admin-only på alle backup-endepunkter
- ModuleBackupConfig-form valideringer
- Scheduler respekterer enabled=False og per-modul intervall
- Audit-log lages ved restore
- Bulk handler-registry (register/get_handler/all_handlers/clear_registry)

Kjør med:
    python manage.py test core.tests_backup
"""
from __future__ import annotations

import gzip
import json
import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from audit.models import AuditLog
from core.backup import (
    BaseBackupHandler,
    KIND_AUTO,
    KIND_MANUAL,
    KIND_PRE_RESTORE,
    KIND_PRE_RESET,
    PROTECTED_KINDS,
    VALID_KINDS,
    all_handlers,
    clear_registry,
    create_backup,
    enforce_cap,
    get_backup_dir,
    get_handler,
    register,
    restore_backup,
)
from core.forms import BackupRestoreConfirmForm, ModuleBackupConfigForm
from core.models import ModuleBackupConfig
from patients.backup import PatientsBackupHandler, register_handlers
from patients.models import AppSetting, Backup, Forstehjelper, Helsepersonell, Patient


# Felles testmappe for backup-filer.
TEST_BACKUP_DIR = Path('/tmp/test-backups-fase4')


def _prepare_backup_dir() -> Path:
    TEST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    # Rydd opp gamle filer fra forrige runde.
    for f in TEST_BACKUP_DIR.glob('backup-*.json.gz'):
        f.unlink(missing_ok=True)
    for f in TEST_BACKUP_DIR.glob('.restore-tmp-*.json'):
        f.unlink(missing_ok=True)
    return TEST_BACKUP_DIR


def _restore_patients_handler() -> None:
    """Sørg for at patients-handleren er registrert (test-isolasjon)."""
    if get_handler('patients') is None:
        register_handlers()


# ─────────────────────────────────────────────────────────────────────────────
# Handler-registry
# ─────────────────────────────────────────────────────────────────────────────


class HandlerRegistryTests(TestCase):
    """Tester for register/get_handler/all_handlers/clear_registry."""

    def tearDown(self) -> None:
        # Gjenopprett patients-handleren etter at vi har klottet i registry.
        clear_registry()
        register_handlers()

    def test_register_and_get_roundtrip(self) -> None:
        clear_registry()

        class DummyHandler(BaseBackupHandler):
            slug = 'dummy'
            display_name = 'Dummy modul'
            apps = ['patients']
            restore_models: list[str] = []

        h = DummyHandler()
        register(h)
        self.assertIs(get_handler('dummy'), h)
        self.assertIn(h, all_handlers())

    def test_register_without_slug_raises(self) -> None:
        clear_registry()

        class BrokenHandler(BaseBackupHandler):
            slug = ''  # mangler slug — skal feile
            apps = ['patients']

        with self.assertRaises(ValueError):
            register(BrokenHandler())

    def test_register_handlers_is_idempotent(self) -> None:
        clear_registry()
        register_handlers()
        register_handlers()  # ny registrering overskriver bare samme slug
        slugs = [h.slug for h in all_handlers()]
        self.assertEqual(slugs.count('patients'), 1)

    def test_unknown_slug_returns_none(self) -> None:
        self.assertIsNone(get_handler('finnes-ikke-i-registry'))


# ─────────────────────────────────────────────────────────────────────────────
# create_backup — hash-skip og kind-håndtering
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class CreateBackupTests(TestCase):
    """Tester for create_backup() — hash-skip og kind-validering."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        # Litt patient-data så dumpdata ikke er tom.
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='Test')

    def test_invalid_kind_raises(self) -> None:
        with self.assertRaises(ValueError):
            with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
                create_backup(slug='patients', kind='ulovlig', user=self.admin)

    def test_unknown_slug_raises(self) -> None:
        with self.assertRaises(ValueError):
            with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
                create_backup(slug='finnes-ikke', kind=KIND_MANUAL)

    def test_manual_backup_creates_file_and_db_row(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(
                slug='patients', kind=KIND_MANUAL, user=self.admin,
                note='Test',
            )

        self.assertIsNotNone(backup)
        self.assertEqual(backup.module_slug, 'patients')
        self.assertEqual(backup.kind, KIND_MANUAL)
        self.assertNotEqual(backup.content_hash, '')
        self.assertTrue((self.backup_dir / backup.filename).exists())

        # Innhold skal være gyldig JSON.
        with gzip.open(self.backup_dir / backup.filename, 'rb') as fh:
            data = json.loads(fh.read())
        self.assertIsInstance(data, list)

    def test_auto_backup_skipped_when_hash_matches(self) -> None:
        """To auto-backups på rad uten endring → andre returnerer None."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            first = create_backup(slug='patients', kind=KIND_AUTO)
            second = create_backup(slug='patients', kind=KIND_AUTO)

        self.assertIsNotNone(first)
        self.assertIsNone(second, 'Andre auto-backup skal hoppes over (hash-skip)')
        self.assertEqual(
            Backup.objects.filter(module_slug='patients', kind=KIND_AUTO).count(),
            1,
        )

    def test_auto_backup_runs_again_after_data_change(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            first = create_backup(slug='patients', kind=KIND_AUTO)

            # Endre data — innhold er nå ulikt forrige.
            Patient.objects.create(pasientnummer=2, year=2025, problemstilling='Ny')

            second = create_backup(slug='patients', kind=KIND_AUTO)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second, 'Auto-backup skal kjøre når data har endret seg')
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_manual_backup_ignores_hash_skip(self) -> None:
        """Manual lagres alltid — også når innhold er identisk."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            first = create_backup(slug='patients', kind=KIND_MANUAL)
            second = create_backup(slug='patients', kind=KIND_MANUAL)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second, 'Manuell backup må aldri hoppes over')
        self.assertEqual(
            Backup.objects.filter(module_slug='patients', kind=KIND_MANUAL).count(),
            2,
        )

    def test_pre_restore_kind_always_creates(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            b = create_backup(slug='patients', kind=KIND_PRE_RESTORE)
        self.assertIsNotNone(b)
        self.assertEqual(b.kind, KIND_PRE_RESTORE)


# ─────────────────────────────────────────────────────────────────────────────
# enforce_cap — 50-cap, beskytter pre_restore
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EnforceCapTests(TestCase):
    """Tester for enforce_cap() — fjerner eldste, beskytter pre_restore."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()

    _seq = 0

    def _make_backup(self, kind: str, age_minutes: int) -> Backup:
        """Lag en Backup-rad + tom fil med kunstig created_at."""
        EnforceCapTests._seq += 1
        ts = timezone.now() - timedelta(minutes=age_minutes)
        filename = (
            f'backup-patients-{kind}-{ts.strftime("%Y%m%d-%H%M%S")}'
            f'-{age_minutes}-{EnforceCapTests._seq}.json.gz'
        )
        path = self.backup_dir / filename
        with gzip.open(path, 'wb') as fh:
            fh.write(b'[]')
        b = Backup.objects.create(
            filename=filename,
            kind=kind,
            size_bytes=path.stat().st_size,
            content_hash='',
            module_slug='patients',
        )
        # auto_now_add hindrer setting i create() — oppdater direkte.
        Backup.objects.filter(pk=b.pk).update(created_at=ts)
        b.refresh_from_db()
        return b

    def test_cap_removes_oldest_first(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            # 5 auto-backuper, ulik alder.
            for i in range(5):
                self._make_backup(KIND_AUTO, age_minutes=i * 10)

            deleted = enforce_cap('patients', max_backups=3)

        self.assertEqual(deleted, 2, 'Skulle slettet de 2 eldste')
        remaining = list(
            Backup.objects.filter(module_slug='patients').order_by('-created_at')
        )
        self.assertEqual(len(remaining), 3)
        # Filene til de to eldste skal være borte fra disk.
        files_on_disk = set(p.name for p in self.backup_dir.glob('backup-*.json.gz'))
        for r in remaining:
            self.assertIn(r.filename, files_on_disk)

    def test_cap_protects_pre_restore(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            # 3 pre_restore (skal aldri røres) + 5 auto.
            for i in range(3):
                self._make_backup(KIND_PRE_RESTORE, age_minutes=i)
            for i in range(5):
                self._make_backup(KIND_AUTO, age_minutes=i * 10 + 100)

            deleted = enforce_cap('patients', max_backups=2)

        # 5 auto - 2 cap = 3 slettet. pre_restore urørt.
        self.assertEqual(deleted, 3)
        self.assertEqual(
            Backup.objects.filter(module_slug='patients', kind=KIND_PRE_RESTORE).count(),
            3, 'pre_restore må aldri telles eller slettes av cap',
        )
        self.assertEqual(
            Backup.objects.filter(module_slug='patients', kind=KIND_AUTO).count(),
            2,
        )

    def test_cap_no_op_when_under_limit(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            self._make_backup(KIND_AUTO, age_minutes=5)
            deleted = enforce_cap('patients', max_backups=10)
        self.assertEqual(deleted, 0)

    def test_cap_only_affects_own_module(self) -> None:
        """Backuper for andre moduler skal ikke berøres av cap på 'patients'."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            for i in range(4):
                self._make_backup(KIND_AUTO, age_minutes=i * 10)

            # Lag en fake annen-modul-rad.
            other = Backup.objects.create(
                filename='backup-other-auto-20250101.json.gz',
                kind=KIND_AUTO,
                size_bytes=1,
                content_hash='',
                module_slug='annen-modul',
            )

            deleted = enforce_cap('patients', max_backups=1)

        self.assertEqual(deleted, 3)
        self.assertTrue(Backup.objects.filter(pk=other.pk).exists())


# ─────────────────────────────────────────────────────────────────────────────
# restore_backup — pre_restore-snapshot, gjenoppretting, FK-trygg slett
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RestoreBackupTests(TestCase):
    """End-to-end restore: ta backup, endre data, restore, verifiser."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        # Original data — eksisterende default-Forstehjelper/Helsepersonell
        # fra signaler kan være tilstede; vi bruker get_or_create.
        beh, _ = Forstehjelper.objects.get_or_create(name='Behandler-Test')
        hp, _ = Helsepersonell.objects.get_or_create(name='HP-Test')
        Patient.objects.create(
            pasientnummer=10, year=2025, problemstilling='Original',
            forstehjelper=beh, helsepersonell_ref=hp,
        )
        self._patient_count_before = Patient.objects.count()
        self._forstehjelper_count_before = Forstehjelper.objects.count()
        self._helsepersonell_count_before = Helsepersonell.objects.count()

    def test_pre_restore_snapshot_created_before_destructive_restore(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL, user=self.admin)
            count_pre_before = Backup.objects.filter(
                module_slug='patients', kind=KIND_PRE_RESTORE,
            ).count()

            restore_backup(backup, user=self.admin)

            count_pre_after = Backup.objects.filter(
                module_slug='patients', kind=KIND_PRE_RESTORE,
            ).count()

        self.assertEqual(count_pre_after, count_pre_before + 1,
                         'Restore skal lage nøyaktig én pre_restore-backup')

    def test_restore_roundtrip_recreates_data(self) -> None:
        """Lag backup, slett alt, restore, verifiser at data er tilbake."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL, user=self.admin)
            self.assertEqual(Patient.objects.count(), self._patient_count_before)

            # Slett alt.
            Patient.objects.all().delete()
            Forstehjelper.objects.all().delete()
            Helsepersonell.objects.all().delete()
            self.assertEqual(Patient.objects.count(), 0)
            self.assertEqual(Forstehjelper.objects.count(), 0)

            restore_backup(backup, user=self.admin)

        # Etter restore skal antallene være som før slett.
        self.assertEqual(Patient.objects.count(), self._patient_count_before)
        self.assertEqual(Forstehjelper.objects.count(), self._forstehjelper_count_before)
        self.assertEqual(Helsepersonell.objects.count(),
                         self._helsepersonell_count_before)
        # Original-pasienten skal være intakt med riktige felter.
        p = Patient.objects.get(pasientnummer=10)
        self.assertEqual(p.problemstilling, 'Original')
        # Behandler-Test skal være med på lasta.
        self.assertTrue(Forstehjelper.objects.filter(name='Behandler-Test').exists())

    def test_restore_replaces_modified_data(self) -> None:
        """Endre data etter backup, restore → original-data tilbake."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL, user=self.admin)

            p = Patient.objects.get(pasientnummer=10)
            p.problemstilling = 'ENDRET ETTER BACKUP'
            p.save()
            Patient.objects.create(
                pasientnummer=99, year=2025, problemstilling='Etter-backup',
            )

            restore_backup(backup, user=self.admin)

        self.assertEqual(
            Patient.objects.count(), self._patient_count_before,
            'Etter-backup-pasient skal være borte',
        )
        p_after = Patient.objects.get(pasientnummer=10)
        self.assertEqual(p_after.problemstilling, 'Original')
        self.assertFalse(Patient.objects.filter(pasientnummer=99).exists())

    def test_restore_unknown_handler_raises(self) -> None:
        """En backup med ukjent module_slug skal feile tydelig."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
            # Tving slug til en ukjent modul.
            Backup.objects.filter(pk=backup.pk).update(module_slug='ukjent-modul')
            backup.refresh_from_db()

            with self.assertRaises(ValueError):
                restore_backup(backup, user=self.admin)

    def test_restore_missing_file_raises(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
            (self.backup_dir / backup.filename).unlink()
            with self.assertRaises(FileNotFoundError):
                restore_backup(backup, user=self.admin)


# ─────────────────────────────────────────────────────────────────────────────
# Forms
# ─────────────────────────────────────────────────────────────────────────────


class ModuleBackupConfigFormTests(TestCase):
    """Validering av ModuleBackupConfigForm."""

    def test_valid_form_passes(self) -> None:
        form = ModuleBackupConfigForm(data={
            'enabled': 'on',
            'interval_minutes': '60',
            'max_backups': '50',
        })
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_max_backups_below_minimum_rejected(self) -> None:
        form = ModuleBackupConfigForm(data={
            'enabled': 'on', 'interval_minutes': '60', 'max_backups': '0',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('max_backups', form.errors)

    def test_max_backups_above_maximum_rejected(self) -> None:
        form = ModuleBackupConfigForm(data={
            'enabled': 'on', 'interval_minutes': '60', 'max_backups': '5000',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('max_backups', form.errors)


class BackupRestoreConfirmFormTests(TestCase):
    """Tester for slug-bekreftelses-skjemaet."""

    def test_correct_slug_validates(self) -> None:
        form = BackupRestoreConfirmForm(
            data={'confirm_slug': 'patients'},
            expected_slug='patients',
        )
        self.assertTrue(form.is_valid())

    def test_wrong_slug_rejected(self) -> None:
        form = BackupRestoreConfirmForm(
            data={'confirm_slug': 'feilslug'},
            expected_slug='patients',
        )
        self.assertFalse(form.is_valid())
        self.assertIn('confirm_slug', form.errors)

    def test_whitespace_trimmed(self) -> None:
        form = BackupRestoreConfirmForm(
            data={'confirm_slug': '  patients  '},
            expected_slug='patients',
        )
        self.assertTrue(form.is_valid())


# ─────────────────────────────────────────────────────────────────────────────
# ModuleBackupConfig — get_or_default
# ─────────────────────────────────────────────────────────────────────────────


class ModuleBackupConfigTests(TestCase):
    """Tester for ModuleBackupConfig-modellen."""

    def test_get_or_default_creates_with_defaults(self) -> None:
        cfg = ModuleBackupConfig.get_or_default('test-modul')
        self.assertEqual(cfg.module_slug, 'test-modul')
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.max_backups, 50)
        self.assertEqual(cfg.interval_minutes, 60)

    def test_get_or_default_idempotent(self) -> None:
        cfg1 = ModuleBackupConfig.get_or_default('idem')
        cfg2 = ModuleBackupConfig.get_or_default('idem')
        self.assertEqual(cfg1.pk, cfg2.pk)
        self.assertEqual(ModuleBackupConfig.objects.filter(module_slug='idem').count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Admin-views — admin-only + restore-flyt
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BackupAdminViewTests(TestCase):
    """Tester for /portal-admin/backup/-views (admin-only + restore-flyt)."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        self.lead = CustomUser.objects.create_user(
            username='lead', password='pwd', role='lead',
            must_change_password=False,
        )

    def test_overview_requires_admin(self) -> None:
        client = Client()
        client.force_login(self.lead)
        resp = client.get('/portal-admin/backup/')
        # admin_required → redirect til dashboard for ikke-admin.
        self.assertIn(resp.status_code, (302, 403))

    def test_overview_renders_for_admin(self) -> None:
        client = Client()
        client.force_login(self.admin)
        resp = client.get('/portal-admin/backup/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'patients')

    def test_module_view_renders_form(self) -> None:
        client = Client()
        client.force_login(self.admin)
        resp = client.get('/portal-admin/backup/patients/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="interval_minutes"')

    def test_module_view_post_saves_config(self) -> None:
        client = Client()
        client.force_login(self.admin)
        resp = client.post('/portal-admin/backup/patients/', data={
            'enabled': '',  # av
            'interval_minutes': '30',
            'max_backups': '25',
        })
        self.assertEqual(resp.status_code, 302)
        cfg = ModuleBackupConfig.objects.get(module_slug='patients')
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.interval_minutes, 30)
        self.assertEqual(cfg.max_backups, 25)

    def test_run_view_creates_manual_backup(self) -> None:
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            resp = client.post('/portal-admin/backup/patients/run/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Backup.objects.filter(module_slug='patients', kind=KIND_MANUAL).exists(),
        )

    def test_restore_requires_correct_slug(self) -> None:
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)

            # Feil slug → form-feil, ingen restore.
            resp_wrong = client.post(
                f'/portal-admin/backup/patients/restore/{backup.pk}/',
                data={'confirm_slug': 'feil'},
            )
            self.assertEqual(resp_wrong.status_code, 200)
            self.assertContains(resp_wrong, 'eksakt')

            # Riktig slug → restore + redirect.
            resp_ok = client.post(
                f'/portal-admin/backup/patients/restore/{backup.pk}/',
                data={'confirm_slug': 'patients'},
            )
        self.assertEqual(resp_ok.status_code, 302)

    def test_restore_creates_audit_log_entry(self) -> None:
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
            client.post(
                f'/portal-admin/backup/patients/restore/{backup.pk}/',
                data={'confirm_slug': 'patients'},
            )

        log = AuditLog.objects.filter(
            table_name='patients_backup_restore',
            action='UPDATE',
        ).first()
        self.assertIsNotNone(log, 'Restore skal lage AuditLog-rad')
        self.assertEqual(log.app_label, 'core')
        self.assertEqual(log.user, self.admin)
        self.assertEqual(log.new_value, backup.filename)

    def test_restore_view_requires_admin(self) -> None:
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='X')
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
        client = Client()
        client.force_login(self.lead)
        resp = client.post(
            f'/portal-admin/backup/patients/restore/{backup.pk}/',
            data={'confirm_slug': 'patients'},
        )
        self.assertIn(resp.status_code, (302, 403))

    def test_download_view_returns_gzip(self) -> None:
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
            resp = client.get(f'/portal-admin/backup/patients/last-ned/{backup.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/gzip')
        self.assertIn(backup.filename, resp['Content-Disposition'])

    def test_delete_view_removes_backup(self) -> None:
        Patient.objects.create(pasientnummer=1, year=2025, problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
            path = self.backup_dir / backup.filename
            self.assertTrue(path.exists())

            resp = client.post(f'/portal-admin/backup/patients/slett/{backup.pk}/')

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Backup.objects.filter(pk=backup.pk).exists())
        self.assertFalse(path.exists())

    def test_unknown_module_redirects_with_error(self) -> None:
        client = Client()
        client.force_login(self.admin)
        resp = client.get('/portal-admin/backup/finnes-ikke/')
        self.assertEqual(resp.status_code, 302)


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler — respekterer enabled=False og per-modul intervall
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SchedulerTests(TestCase):
    """Tester at scheduler-logikken respekterer config."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()

    def test_should_run_now_disabled_returns_false(self) -> None:
        from patients.backup_scheduler import _should_run_now

        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = False
        self.assertFalse(_should_run_now(cfg))

    def test_should_run_now_interval_zero_returns_false(self) -> None:
        from patients.backup_scheduler import _should_run_now

        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 0
        self.assertFalse(_should_run_now(cfg))

    def test_should_run_now_first_time_returns_true(self) -> None:
        from patients.backup_scheduler import _should_run_now

        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60
        cfg.last_run_at = None
        self.assertTrue(_should_run_now(cfg))

    def test_should_run_now_respects_interval(self) -> None:
        from patients.backup_scheduler import _should_run_now

        cfg = ModuleBackupConfig.get_or_default('patients')
        cfg.enabled = True
        cfg.interval_minutes = 60

        # Sist kjørt 5 min siden — skal IKKE kjøre.
        cfg.last_run_at = timezone.now() - timedelta(minutes=5)
        self.assertFalse(_should_run_now(cfg))

        # Sist kjørt 90 min siden — SKAL kjøre.
        cfg.last_run_at = timezone.now() - timedelta(minutes=90)
        self.assertTrue(_should_run_now(cfg))

    def test_run_backup_for_module_skips_when_handler_missing(self) -> None:
        """Hvis handler er borte fra registry, skal scheduler hoppe over uten å feile."""
        from patients.backup_scheduler import _run_backup_for_module

        ModuleBackupConfig.objects.create(
            module_slug='ukjent-modul-xyz', enabled=True, interval_minutes=60,
        )
        # Skal ikke kaste exception.
        _run_backup_for_module('ukjent-modul-xyz')

        # Ingen backup-rad skal være laget.
        self.assertEqual(
            Backup.objects.filter(module_slug='ukjent-modul-xyz').count(),
            0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Konstanter — sanity check
# ─────────────────────────────────────────────────────────────────────────────


class BackupConstantsTests(TestCase):
    def test_valid_kinds_complete(self) -> None:
        self.assertEqual(
            VALID_KINDS,
            {KIND_AUTO, KIND_MANUAL, KIND_PRE_RESTORE, KIND_PRE_RESET},
        )

    def test_pre_restore_is_protected(self) -> None:
        self.assertIn(KIND_PRE_RESTORE, PROTECTED_KINDS)

    def test_get_backup_dir_returns_existing_path(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(_prepare_backup_dir())}):
            path = get_backup_dir()
        self.assertTrue(path.exists())
        self.assertTrue(path.is_dir())
