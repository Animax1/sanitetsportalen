"""Tester for Fase 4 — per-modul backup-rammeverk i core.backup.

Dekker:
- Hash-skip for auto-backup når innhold er uendret
- Manual / pre_restore lagres alltid (hash-skip gjelder kun auto)
- 50-cap fjerner eldste først, beskytter pre_restore
- Restore gjenoppretter modellinstanser nøyaktig
- Pre-restore-snapshot lages før destruktiv restore
- Restore-bekreftelse via slug (BackupRestoreConfirmForm)
- Admin-only på alle backup-endepunkter
- BackupplanForm-valideringer
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
    registrer_alle_moduler,
    create_backup,
    enforce_cap,
    get_backup_dir,
    get_handler,
    register,
    restore_backup,
)
from core.forms import BackupRestoreConfirmForm, BackupplanForm
from core.models import Backupplan
from patients.backup import PatientsBackupHandler, register_handlers
from patients.models import Forstehjelper, Helsepersonell, Patient
from core.models import AppSetting, Backup
from core.vakt import vakt_for_year
from accounts.test_helpers import gi_standardtilgang


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
    """Sørg for at modulens backup-handlere er registrert (test-isolasjon).

    ``register_handlers()`` registrerer både ``patients`` og ``arkiv``; begge
    sjekkes slik at et delvis tømt registry også blir gjenopprettet.
    """
    if get_handler('patients') is None or get_handler('arkiv') is None:
        register_handlers()


# ─────────────────────────────────────────────────────────────────────────────
# Handler-registry
# ─────────────────────────────────────────────────────────────────────────────


class HandlerRegistryTests(TestCase):
    """Tester for register/get_handler/all_handlers/clear_registry."""

    def tearDown(self) -> None:
        # Gjenopprett ALLE modulenes handlere etter at vi har klottet i
        # registryet. Sto det `register_handlers()` her — pasientmodulens —
        # ble oppdragsmodulens borte for resten av kjøringen, og feilen
        # dukket opp i en helt annen testfil.
        clear_registry()
        registrer_alle_moduler()

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
        gi_standardtilgang(self.admin, 'admin')
        # Litt patient-data så dumpdata ikke er tom.
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='Test')

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
            Patient.objects.create(pasientnummer=2, vakt=vakt_for_year(2025), problemstilling='Ny')

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
        gi_standardtilgang(self.admin, 'admin')
        # Original data — eksisterende default-Forstehjelper/Helsepersonell
        # fra signaler kan være tilstede; vi bruker get_or_create.
        beh, _ = Forstehjelper.objects.get_or_create(name='Behandler-Test')
        hp, _ = Helsepersonell.objects.get_or_create(name='HP-Test')
        Patient.objects.create(
            pasientnummer=10, vakt=vakt_for_year(2025), problemstilling='Original',
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
                pasientnummer=99, vakt=vakt_for_year(2025), problemstilling='Etter-backup',
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


class BackupplanFormTests(TestCase):
    """Validering av BackupplanForm."""

    GYLDIG = {'folger_standard': '', 'modus': 'ved_endring',
              'intervall_verdi': '10', 'intervall_enhet': 'minutt',
              'behold': '50'}

    def test_valid_form_passes(self) -> None:
        form = BackupplanForm(data=dict(self.GYLDIG))
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_behold_below_minimum_rejected(self) -> None:
        form = BackupplanForm(data=dict(self.GYLDIG, behold='0'))
        self.assertFalse(form.is_valid())
        self.assertIn('behold', form.errors)

    def test_behold_above_maximum_rejected(self) -> None:
        form = BackupplanForm(data=dict(self.GYLDIG, behold='5000'))
        self.assertFalse(form.is_valid())
        self.assertIn('behold', form.errors)

    def test_intervall_under_ett_avvises(self) -> None:
        form = BackupplanForm(data=dict(self.GYLDIG, intervall_verdi='0'))
        self.assertFalse(form.is_valid())
        self.assertIn('intervall_verdi', form.errors)

    def test_fritt_intervall_godtas(self) -> None:
        """Poenget med omleggingen: 7 minutter fantes ikke i det gamle
        nedtrekket med sju faste valg."""
        form = BackupplanForm(data=dict(self.GYLDIG, intervall_verdi='7'))
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_alle_tre_enhetene_godtas(self) -> None:
        for enhet in ('minutt', 'time', 'dogn'):
            with self.subTest(enhet=enhet):
                form = BackupplanForm(data=dict(self.GYLDIG, intervall_enhet=enhet))
                self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_egenraadig_plan_viser_ikke_arvebryteren(self) -> None:
        """Standardplanen og hele databasen styrer alltid seg selv — å tilby
        avkrysningsboksen ville vært et valg som ikke finnes."""
        for slug in ('standard', 'full'):
            with self.subTest(slug=slug):
                form = BackupplanForm(instance=Backupplan.hent(slug))
                self.assertNotIn('folger_standard', form.fields)


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
# Backupplan — oppslag, intervall og arv
# ─────────────────────────────────────────────────────────────────────────────


class BackupplanTests(TestCase):
    """Tester for Backupplan-modellen."""

    def test_hent_oppretter_med_standardverdier(self) -> None:
        plan = Backupplan.hent('test-modul')
        self.assertEqual(plan.slug, 'test-modul')
        self.assertEqual(plan.modus, Backupplan.MODUS_VED_ENDRING)
        self.assertTrue(plan.folger_standard)
        self.assertEqual(plan.behold, 50)

    def test_hent_er_idempotent(self) -> None:
        a = Backupplan.hent('idem')
        b = Backupplan.hent('idem')
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Backupplan.objects.filter(slug='idem').count(), 1)

    def test_arkivene_far_eget_langsommere_intervall(self) -> None:
        """Et arkiv endres én gang per arrangement. Å serialisere hele
        arkivtabellen hvert 10. minutt er å bruke CPU på å bekrefte stillstand."""
        plan = Backupplan.hent('oppdrag_arkiv')
        self.assertFalse(plan.folger_standard)
        self.assertEqual(plan.intervall_min, 6 * 60)

    def test_intervall_min_regner_om_enheten(self) -> None:
        plan = Backupplan.hent('omregning')
        for verdi, enhet, ventet in [(45, 'minutt', 45), (2, 'time', 120),
                                     (3, 'dogn', 4320)]:
            with self.subTest(enhet=enhet):
                plan.intervall_verdi, plan.intervall_enhet = verdi, enhet
                self.assertEqual(plan.intervall_min, ventet)

    def test_intervall_tekst_boyer_riktig(self) -> None:
        """«Time» er felleskjønn, «minutt» og «døgn» intetkjønn. Utledet av
        flertallsformen ga «hver døgn» og «hvert 6. time»."""
        plan = Backupplan.hent('tekst')
        for verdi, enhet, ventet in [
            (1, 'minutt', 'hvert minutt'), (1, 'time', 'hver time'),
            (1, 'dogn', 'hvert døgn'), (10, 'minutt', 'hvert 10. minutt'),
            (6, 'time', 'hver 6. time'), (3, 'dogn', 'hvert 3. døgn'),
        ]:
            with self.subTest(verdi=verdi, enhet=enhet):
                plan.intervall_verdi, plan.intervall_enhet = verdi, enhet
                self.assertEqual(plan.intervall_tekst(), ventet)

    def test_arv_leser_standardplanen(self) -> None:
        standard = Backupplan.standardplanen()
        standard.modus = Backupplan.MODUS_ALLTID
        standard.intervall_verdi, standard.intervall_enhet = 2, 'time'
        standard.behold = 9
        standard.save()

        plan = Backupplan.hent('arving')
        self.assertTrue(plan.arver)
        self.assertEqual(plan.modus_effektiv, Backupplan.MODUS_ALLTID)
        self.assertEqual(plan.intervall_min_effektiv, 120)
        self.assertEqual(plan.behold_effektiv, 9)
        self.assertTrue(plan.skriver_alltid)

    def test_egen_plan_overstyrer_standarden(self) -> None:
        standard = Backupplan.standardplanen()
        standard.behold = 9
        standard.save()

        plan = Backupplan.hent('egen')
        plan.folger_standard = False
        plan.behold = 3
        plan.save()
        self.assertFalse(plan.arver)
        self.assertEqual(plan.behold_effektiv, 3)

    def test_standard_og_full_arver_aldri(self) -> None:
        for slug in (Backupplan.STANDARD_SLUG, Backupplan.FULL_SLUG):
            with self.subTest(slug=slug):
                plan = Backupplan.hent(slug)
                plan.folger_standard = True   # selv om noen skulle sette den
                self.assertFalse(plan.arver)

    def test_gjeldende_uten_standardrad_faller_tilbake_paa_seg_selv(self) -> None:
        """En lesning skal ikke bli en skriving — `gjeldende()` kalles fra
        visninger, og oppretter derfor ikke standardraden."""
        plan = Backupplan.hent('foreldrelos')
        Backupplan.objects.filter(slug=Backupplan.STANDARD_SLUG).delete()
        self.assertEqual(plan.gjeldende().pk, plan.pk)


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
        gi_standardtilgang(self.admin, 'admin')
        self.lead = CustomUser.objects.create_user(
            username='lead', password='pwd', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.lead, 'leder')

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

    def test_alle_moduler_staar_paa_samme_side(self) -> None:
        """Modulsidene er lagt ned. Alt skal være på én side — det var de fire
        rundene for å ta backup av alt som var tungvint."""
        client = Client()
        client.force_login(self.admin)
        resp = client.get('/portal-admin/backup/')
        for slug in ('patients', 'arkiv', 'oppdrag', 'oppdrag_arkiv'):
            with self.subTest(slug=slug):
                self.assertContains(resp, slug)

    def test_siden_har_skjema_for_hver_modul_med_prefiks(self) -> None:
        """Hver rad har sitt eget skjema, prefikset med slugen — ellers ville
        seks skjemaer på én side delt feltnavn og overskrevet hverandre."""
        client = Client()
        client.force_login(self.admin)
        resp = client.get('/portal-admin/backup/')
        for felt in ('modus', 'intervall_verdi', 'intervall_enhet', 'behold'):
            with self.subTest(felt=felt):
                self.assertContains(resp, f'name="patients-{felt}"')
                self.assertContains(resp, f'name="standard-{felt}"')

    def test_plan_view_lagrer_egen_plan(self) -> None:
        client = Client()
        client.force_login(self.admin)
        resp = client.post('/portal-admin/backup/plan/patients/', data={
            'patients-folger_standard': '',       # egen plan
            'patients-modus': 'av',
            'patients-intervall_verdi': '30',
            'patients-intervall_enhet': 'minutt',
            'patients-behold': '25',
        })
        self.assertEqual(resp.status_code, 302)
        plan = Backupplan.objects.get(slug='patients')
        self.assertFalse(plan.folger_standard)
        self.assertEqual(plan.modus, 'av')
        self.assertEqual(plan.intervall_min, 30)
        self.assertEqual(plan.behold, 25)

    def test_plan_view_lagrer_standardplanen(self) -> None:
        client = Client()
        client.force_login(self.admin)
        resp = client.post('/portal-admin/backup/plan/standard/', data={
            'standard-modus': 'alltid',
            'standard-intervall_verdi': '2',
            'standard-intervall_enhet': 'time',
            'standard-behold': '11',
        })
        self.assertEqual(resp.status_code, 302)
        standard = Backupplan.objects.get(slug='standard')
        self.assertEqual(standard.modus, 'alltid')
        self.assertEqual(standard.intervall_min, 120)
        self.assertEqual(standard.behold, 11)

    def test_plan_view_avviser_ugyldig_intervall(self) -> None:
        client = Client()
        client.force_login(self.admin)
        client.post('/portal-admin/backup/plan/patients/', data={
            'patients-folger_standard': '', 'patients-modus': 'ved_endring',
            'patients-intervall_verdi': '0', 'patients-intervall_enhet': 'minutt',
            'patients-behold': '25',
        })
        self.assertNotEqual(Backupplan.objects.get(slug='patients').intervall_verdi, 0)

    def test_run_view_creates_manual_backup(self) -> None:
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            resp = client.post('/portal-admin/backup/kjor/patients/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            Backup.objects.filter(module_slug='patients', kind=KIND_MANUAL).exists(),
        )

    def test_ta_backup_av_alle_tar_alle_modulene(self) -> None:
        """Knappen som gjorde de fire rundene overflødige."""
        from core.backup import all_handlers

        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            resp = client.post('/portal-admin/backup/kjor/')
        self.assertEqual(resp.status_code, 302)
        for handler in all_handlers():
            with self.subTest(slug=handler.slug):
                self.assertTrue(
                    Backup.objects.filter(module_slug=handler.slug).exists())

    def test_restore_requires_correct_slug(self) -> None:
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
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
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
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

    def test_run_view_requires_admin(self) -> None:
        """Manuell backup skal være admin-only, som resten av flaten."""
        client = Client()
        client.force_login(self.lead)
        resp = client.post('/portal-admin/backup/kjor/patients/')
        self.assertIn(resp.status_code, (302, 403))

    def test_restore_view_requires_admin(self) -> None:
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
        client = Client()
        client.force_login(self.lead)
        resp = client.post(
            f'/portal-admin/backup/patients/restore/{backup.pk}/',
            data={'confirm_slug': 'patients'},
        )
        self.assertIn(resp.status_code, (302, 403))

    def test_nedlasting_finnes_ikke(self) -> None:
        """Backupfilene skal ikke finnes andre steder enn hos Scaleway eller på
        Railway (André, 13. sep. 2026). Det gjelder pasientfila like mye som
        den hele: en `.json.gz` med hele pasientregisteret i nedlastingsmappa
        er en helseopplysningsdump utenfor portalens kontroll."""
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
            resp = client.get(f'/portal-admin/backup/patients/last-ned/{backup.pk}/')
        self.assertEqual(resp.status_code, 404)

        siden = client.get('/portal-admin/backup/')
        self.assertNotContains(siden, 'last-ned')

    def test_delete_view_removes_backup(self) -> None:
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
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

    def test_ukjent_modul_omdirigerer_med_feil(self) -> None:
        client = Client()
        client.force_login(self.admin)
        resp = client.post('/portal-admin/backup/kjor/finnes-ikke/')
        self.assertEqual(resp.status_code, 302)
        resp = client.post('/portal-admin/backup/plan/finnes-ikke/', data={})
        self.assertEqual(resp.status_code, 302)

    def test_bekreftelsen_sier_hvor_mange_rader_som_slettes(self) -> None:
        """«Slett og erstatt» er et annet svar når man ser tallet."""
        Patient.objects.create(pasientnummer=1, vakt=vakt_for_year(2025), problemstilling='X')
        client = Client()
        client.force_login(self.admin)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
        resp = client.get(f'/portal-admin/backup/patients/restore/{backup.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Dette slettes og erstattes')

    def test_vakthunden_vises_naar_klokka_er_stille(self) -> None:
        """Klokka er en tråd og synes ikke i Railway. Siden er beviset."""
        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = Backupplan.MODUS_VED_ENDRING
        plan.intervall_verdi, plan.intervall_enhet = 10, 'minutt'
        plan.sist_sjekket_at = timezone.now() - timedelta(hours=5)
        plan.save()

        client = Client()
        client.force_login(self.admin)
        resp = client.get('/portal-admin/backup/')
        self.assertContains(resp, 'Backup-klokka svarer ikke')


# ─────────────────────────────────────────────────────────────────────────────
# Klokka — modus, intervall og vakthund
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KlokkeForfaltTests(TestCase):
    """Når klokka mener en plan er forfalt."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()

    def test_modus_av_er_aldri_forfalt(self) -> None:
        from core.backup.klokke import forfalt

        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = Backupplan.MODUS_AV
        self.assertFalse(forfalt(plan))

    def test_aldri_vurdert_er_forfalt(self) -> None:
        from core.backup.klokke import forfalt

        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = Backupplan.MODUS_VED_ENDRING
        plan.sist_sjekket_at = None
        self.assertTrue(forfalt(plan))

    def test_respekterer_intervallet(self) -> None:
        from core.backup.klokke import forfalt

        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = Backupplan.MODUS_VED_ENDRING
        plan.intervall_verdi, plan.intervall_enhet = 1, 'time'

        plan.sist_sjekket_at = timezone.now() - timedelta(minutes=5)
        self.assertFalse(forfalt(plan))
        plan.sist_sjekket_at = timezone.now() - timedelta(minutes=90)
        self.assertTrue(forfalt(plan))

    def test_maaler_mot_vurdering_ikke_mot_siste_fil(self) -> None:
        """Den viktigste regelen i klokka.

        I «ved endring» er det normale utfallet at ingenting skrives. Målte vi
        forfall mot `sist_fil_at`, ville planen vært forfalt ved hvert eneste
        tikk etterpå — altså serialisert hele modulen hvert minutt for å
        bekrefte stillstand, i stedet for hvert intervall.
        """
        from core.backup.klokke import forfalt

        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = Backupplan.MODUS_VED_ENDRING
        plan.intervall_verdi, plan.intervall_enhet = 1, 'time'
        plan.sist_fil_at = timezone.now() - timedelta(days=3)   # gammel fil
        plan.sist_sjekket_at = timezone.now() - timedelta(minutes=2)
        self.assertFalse(forfalt(plan))

    def test_arvet_intervall_avgjor(self) -> None:
        from core.backup.klokke import forfalt

        standard = Backupplan.standardplanen()
        standard.intervall_verdi, standard.intervall_enhet = 1, 'dogn'
        standard.save()

        plan = Backupplan.hent('patients')
        plan.folger_standard = True
        plan.intervall_verdi, plan.intervall_enhet = 1, 'minutt'   # ignoreres
        plan.sist_sjekket_at = timezone.now() - timedelta(hours=2)
        self.assertFalse(forfalt(plan))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KlokkeKjoringTests(TestCase):
    """Hva `kjor_plan` faktisk gjør med filene og tidsstemplene."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()

    def _plan(self, modus):
        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = modus
        plan.intervall_verdi, plan.intervall_enhet = 1, 'minutt'
        plan.save()
        return plan

    def test_ved_endring_skriver_ikke_naar_innholdet_star_stille(self) -> None:
        from core.backup.klokke import kjor_plan

        self._plan(Backupplan.MODUS_VED_ENDRING)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            self.assertTrue(kjor_plan('patients', tving=True))
            self.assertFalse(kjor_plan('patients', tving=True))
        self.assertEqual(Backup.objects.filter(module_slug='patients').count(), 1)

        plan = Backupplan.objects.get(slug='patients')
        self.assertEqual(plan.sist_resultat, 'uendret')

    def test_alltid_skriver_selv_naar_innholdet_star_stille(self) -> None:
        """Pulsen: en fil per intervall, så et hull i rekka er en synlig feil."""
        from core.backup.klokke import kjor_plan

        self._plan(Backupplan.MODUS_ALLTID)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            self.assertTrue(kjor_plan('patients', tving=True))
            self.assertTrue(kjor_plan('patients', tving=True))
        self.assertEqual(Backup.objects.filter(module_slug='patients').count(), 2)

        plan = Backupplan.objects.get(slug='patients')
        self.assertEqual(plan.sist_resultat, 'ny')

    def test_uendret_flytter_ikke_siste_fil(self) -> None:
        """«Sist vurdert» og «siste fil» må kunne stå på hvert sitt tidspunkt —
        det er nettopp det som skiller «stille» fra «stoppet»."""
        from core.backup.klokke import kjor_plan

        self._plan(Backupplan.MODUS_VED_ENDRING)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            kjor_plan('patients', tving=True)
            forste_fil = Backupplan.objects.get(slug='patients').sist_fil_at
            kjor_plan('patients', tving=True)

        plan = Backupplan.objects.get(slug='patients')
        self.assertEqual(plan.sist_fil_at, forste_fil)
        self.assertGreater(plan.sist_sjekket_at, plan.sist_fil_at)

    def test_hopper_over_naar_handler_mangler(self) -> None:
        from core.backup.klokke import kjor_plan

        Backupplan.objects.create(slug='ukjent-modul-xyz')
        kjor_plan('ukjent-modul-xyz')   # skal ikke kaste
        self.assertEqual(
            Backup.objects.filter(module_slug='ukjent-modul-xyz').count(), 0)

    def test_feil_havner_paa_planen(self) -> None:
        """En feil som bare står i loggen, er en feil ingen ser."""
        from core.backup.klokke import kjor_plan

        self._plan(Backupplan.MODUS_VED_ENDRING)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}), \
                patch('core.backup.create_backup',
                      side_effect=RuntimeError('disken er full')):
            self.assertFalse(kjor_plan('patients', tving=True))
        plan = Backupplan.objects.get(slug='patients')
        self.assertIn('disken er full', plan.sist_resultat)

    def test_kjor_forfalte_tar_alle_registrerte(self) -> None:
        """Registeret er fasit, ikke plantabellen: en modul uten rad skal få
        dekning uten at noen åpner adminsiden først."""
        from core.backup import all_handlers
        from core.backup.klokke import kjor_forfalte

        Backupplan.objects.all().delete()
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            kjor_forfalte()
        for handler in all_handlers():
            with self.subTest(slug=handler.slug):
                self.assertTrue(
                    Backupplan.objects.filter(slug=handler.slug).exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VakthundTests(TestCase):
    """Klokka er en tråd og synes ikke noe sted. Vakthunden er beviset."""

    def setUp(self) -> None:
        _restore_patients_handler()

    def test_fersk_vurdering_gir_ingen_utslag(self) -> None:
        from core.backup.klokke import vakthund

        Backupplan.hent('patients')
        Backupplan.objects.all().update(sist_sjekket_at=timezone.now())
        self.assertEqual(vakthund(), [])

    def test_slaar_ut_etter_tre_ganger_intervallet(self) -> None:
        from core.backup.klokke import VAKTHUND_FAKTOR, vakthund

        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = Backupplan.MODUS_VED_ENDRING
        plan.intervall_verdi, plan.intervall_enhet = 10, 'minutt'
        plan.sist_sjekket_at = timezone.now() - timedelta(
            minutes=10 * VAKTHUND_FAKTOR + 1)
        plan.save()
        self.assertIn('patients', [r['slug'] for r in vakthund()])

    def test_to_ganger_intervallet_er_ikke_nok(self) -> None:
        """En deploy eller restart hopper legitimt over et tikk eller to."""
        from core.backup.klokke import vakthund

        plan = Backupplan.hent('patients')
        plan.folger_standard = False
        plan.modus = Backupplan.MODUS_VED_ENDRING
        plan.intervall_verdi, plan.intervall_enhet = 10, 'minutt'
        plan.sist_sjekket_at = timezone.now() - timedelta(minutes=20)
        plan.save()
        self.assertNotIn('patients', [r['slug'] for r in vakthund()])

    def test_planer_i_modus_av_gir_ikke_varsel(self) -> None:
        from core.backup.klokke import vakthund

        Backupplan.objects.all().update(
            modus=Backupplan.MODUS_AV, folger_standard=False,
            sist_sjekket_at=None)
        self.assertEqual(vakthund(), [])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KlokkeOppstartTests(TestCase):
    """At tråden ikke starter der den ikke skal, og rydder der den skal."""

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()

    def test_starter_ikke_under_engangskommandoer(self) -> None:
        """Tillatelsesliste, ikke blokkliste: en ny management-kommando skal
        ikke kunne etterlate seg en tråd fordi noen glemte å liste den."""
        from core.backup.klokke import skal_starte

        for kommando in ('test', 'migrate', 'makemigrations', 'collectstatic',
                         'backup_kjor', 'check', 'shell', 'en_helt_ny_kommando'):
            with self.subTest(kommando=kommando):
                with patch('sys.argv', ['manage.py', kommando]):
                    self.assertFalse(skal_starte())

    def test_starter_under_web(self) -> None:
        from core.backup.klokke import skal_starte

        for server in ('gunicorn', '/usr/local/bin/gunicorn', 'uvicorn'):
            with self.subTest(server=server):
                with patch('sys.argv', [server, 'myproject.wsgi']):
                    self.assertTrue(skal_starte())

    def test_runserver_starter_bare_i_underprosessen(self) -> None:
        """`runserver` starter seg selv på nytt; uten RUN_MAIN-sjekken får
        utviklingsserveren to klokketråder."""
        from core.backup.klokke import skal_starte

        with patch('sys.argv', ['manage.py', 'runserver']):
            with patch.dict(os.environ, {'RUN_MAIN': 'true'}):
                self.assertTrue(skal_starte())
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('RUN_MAIN', None)
                self.assertFalse(skal_starte())

    def test_miljovariabel_slaar_av(self) -> None:
        from core.backup.klokke import skal_starte

        with patch('sys.argv', ['gunicorn', 'myproject.wsgi']), \
                patch.dict(os.environ, {'BACKUP_KLOKKE': 'av'}):
            self.assertFalse(skal_starte())

    def test_rydder_foreldrelose_filer(self) -> None:
        """`create_backup` skriver fila først og raden etterpå. Drepes
        prosessen imellom, ligger det igjen en halv fil ingen kommer til å
        lese."""
        import time as _time

        from core.backup.klokke import rydd_foreldrelose

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            foreldrelos = self.backup_dir / 'backup-patients-auto-gammel.json.gz'
            foreldrelos.write_bytes(b'halv fil')
            gammel = _time.time() - 7200
            os.utime(foreldrelos, (gammel, gammel))

            fersk = self.backup_dir / 'backup-patients-auto-fersk.json.gz'
            fersk.write_bytes(b'skrives akkurat naa')

            self.assertEqual(rydd_foreldrelose(), 1)

        self.assertFalse(foreldrelos.exists())
        self.assertTrue(fersk.exists(), 'en pågående skriving skal ikke ryddes')

    def test_rydder_ikke_filer_med_rad(self) -> None:
        from core.backup.klokke import rydd_foreldrelose

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            sti = self.backup_dir / 'backup-patients-auto-kjent.json.gz'
            sti.write_bytes(b'innhold')
            gammel = 1_600_000_000
            os.utime(sti, (gammel, gammel))
            Backup.objects.create(filename=sti.name, kind='auto', size_bytes=7,
                                  module_slug='patients')
            self.assertEqual(rydd_foreldrelose(), 0)
        self.assertTrue(sti.exists())


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


class RestorePayloadInspectionTests(TestCase):
    """Kontroll av fixturen før loaddata (siste uvaliderte vei inn i basen).

    `loaddata` går utenom all applikasjonsvalidering. API-et validerer mot
    whitelisten i `patients/choices.py`, og `import_offline_data` fikk samme
    kontroll i N6 — restore var det siste hullet.

    Kontrollen *advarer*, den blokkerer ikke. Restore er nødstien, og skal
    aldri kunne stoppes av en verdi som var lovlig da den ble lagret.
    """

    def setUp(self) -> None:
        _restore_patients_handler()
        self.backup_dir = _prepare_backup_dir()
        self.admin = CustomUser.objects.create_user(
            username='admin_inspect', password='pwd', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')

    def _handler(self):
        from patients.backup import PatientsBackupHandler
        return PatientsBackupHandler()

    def _pasient(self, **felter):
        return {'model': 'patients.patient', 'pk': 1, 'fields': felter}

    def test_gyldige_verdier_gir_ingen_advarsel(self):
        advarsler = self._handler().inspect_restore_payload([
            self._pasient(problemstilling='Brystsmerter', grovsortering='Rød'),
        ])
        self.assertEqual(advarsler, [])

    def test_tomme_felt_er_greit(self):
        """Et tomt felt betyr «ikke utfylt ennå», ikke et avvik."""
        advarsler = self._handler().inspect_restore_payload([
            self._pasient(problemstilling='', grovsortering=None),
        ])
        self.assertEqual(advarsler, [])

    def test_verdi_utenfor_whitelisten_gir_advarsel(self):
        advarsler = self._handler().inspect_restore_payload([
            self._pasient(problemstilling='<img src=x onerror=alert(1)>'),
        ])
        self.assertEqual(len(advarsler), 1)
        self.assertIn('problemstilling', advarsler[0])
        self.assertIn('onerror', advarsler[0])

    def test_like_avvik_slaas_sammen_med_antall(self):
        """Rapporten er per felt og verdi, ikke én linje per pasient."""
        advarsler = self._handler().inspect_restore_payload([
            self._pasient(problemstilling='Utgått verdi'),
            self._pasient(problemstilling='Utgått verdi'),
            self._pasient(problemstilling='Utgått verdi'),
        ])
        self.assertEqual(len(advarsler), 1)
        self.assertIn('3 rad(er)', advarsler[0])

    def test_lange_verdier_forkortes(self):
        """Feltet kan i prinsippet være vilkårlig lang fritekst."""
        advarsler = self._handler().inspect_restore_payload([
            self._pasient(problemstilling='A' * 500),
        ])
        self.assertEqual(len(advarsler), 1)
        self.assertIn('...', advarsler[0])
        self.assertLess(len(advarsler[0]), 250)

    def test_andre_modeller_ignoreres(self):
        """Kun Patient har kliniske felt."""
        advarsler = self._handler().inspect_restore_payload([
            {'model': 'patients.forstehjelper', 'pk': 1,
             'fields': {'name': 'Hvem som helst', 'is_active': True}},
        ])
        self.assertEqual(advarsler, [])

    def test_restore_blokkeres_ikke_av_ugyldig_verdi(self):
        """Selve poenget: nødstien skal alltid gå gjennom.

        En pasient med en verdi utenfor whitelisten legges inn direkte i
        databasen, backupes, og gjenopprettes. Restoren skal fullføre, og
        raden skal komme tilbake uendret.
        """
        Patient.objects.create(
            pasientnummer=77, vakt=vakt_for_year(2025), problemstilling='Verdi fra gammel versjon',
        )
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='patients', kind=KIND_MANUAL, user=self.admin)
            Patient.objects.all().delete()

            with self.assertLogs('core.backup', level='WARNING') as logg:
                restore_backup(backup, user=self.admin)

        self.assertTrue(
            any('problemstilling' in linje for linje in logg.output),
            f'Forventet advarsel om problemstilling, fikk: {logg.output}')
        gjenopprettet = Patient.objects.get(pasientnummer=77)
        self.assertEqual(gjenopprettet.problemstilling, 'Verdi fra gammel versjon')

    def test_oedelagt_fixture_stopper_ikke_restore(self):
        """Kontrollen skal aldri være grunnen til at en gjenoppretting feiler."""
        from core.backup.service import _inspect_payload

        self.assertEqual(_inspect_payload(self._handler(), b'ikke json', 'x.gz'), [])
        self.assertEqual(_inspect_payload(self._handler(), b'{"ikke": "liste"}', 'x.gz'), [])

    def test_handler_som_kaster_stopper_ikke_restore(self):
        from core.backup.service import _inspect_payload

        class Sprengt(BaseBackupHandler):
            slug = 'sprengt'

            def inspect_restore_payload(self, objects):
                raise RuntimeError('noe gikk galt')

        self.assertEqual(_inspect_payload(Sprengt(), b'[]', 'x.gz'), [])


# ─────────────────────────────────────────────────────────────────────────────
# Slettelista må dekke dumpen
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SlettelistaDekkerDumpenTests(TestCase):
    """En modell som er med i dumpen, må også være med i slettelista.

    Er den ikke det, blir radene stående igjen etter en gjenoppretting: de
    andre modellene tømmes og lastes på nytt, mens denne beholder det som var
    der fra før. Utfallet er en base som ser gjenopprettet ut og ikke er det.

    Det er gjeldspunkt 3.4 (`Lydvarsel` i oppdragsdumpen, glemt i lista), og
    poenget med denne testen er at feilen ikke kan komme tilbake gjennom en ny
    modell eller en ny modul. Fra 13. sep. 2026 utledes lista, så testen skal
    passere av seg selv — den finnes for å fange den dagen noen setter
    `restore_models` for hånd igjen.
    """

    def setUp(self) -> None:
        registrer_alle_moduler()

    def test_hver_handler_dekker_alle_modellene_den_dumper(self) -> None:
        from django.core import management
        import io

        for handler in all_handlers():
            with self.subTest(slug=handler.slug):
                buf = io.StringIO()
                management.call_command(
                    'dumpdata', *handler.collect_apps(),
                    exclude=handler.collect_exclude(), format='json',
                    indent=None, stdout=buf,
                )
                i_dumpen = {o['model'].lower() for o in json.loads(buf.getvalue())}
                i_lista = {m.lower() for m in handler.get_restore_models()}
                self.assertEqual(
                    i_dumpen - i_lista, set(),
                    f'{handler.slug}: disse modellene dumpes, men tømmes ikke '
                    f'før loaddata — radene blir stående igjen etter en '
                    f'gjenoppretting.',
                )

    def test_lydvarsel_er_dekket(self) -> None:
        """Gjeldspunkt 3.4, navngitt: den ene modellen den håndskrevne lista
        manglet."""
        self.assertIn('oppdrag.Lydvarsel',
                      get_handler('oppdrag').get_restore_models())

    def test_utledningen_setter_barn_for_foreldre(self) -> None:
        from core.backup import utled_restore_models

        rekkefolge = utled_restore_models(['vaktliste'], [])
        plass = {m: i for i, m in enumerate(rekkefolge)}
        # Vaktpost peker på Ressurs, Ressurs peker på Vaktliste.
        self.assertLess(plass['vaktliste.Vaktpost'], plass['vaktliste.Ressurs'])
        self.assertLess(plass['vaktliste.Ressurs'], plass['vaktliste.Vaktliste'])

    def test_selvreferanse_gir_ikke_evig_lokke(self) -> None:
        """`Kompetanse.bygger_paa` og `Statusmelding.erstatter` peker på sin
        egen modell. En kant fra en node til seg selv ville gjort grafen
        usorterbar, og resultatet er en tom liste framfor en feil."""
        from core.backup import utled_restore_models

        self.assertIn('vaktliste.Kompetanse', utled_restore_models(['vaktliste'], []))
        self.assertIn('oppdrag.Statusmelding', utled_restore_models(['oppdrag'], []))

    def test_apps_kan_peke_paa_enkeltmodeller(self) -> None:
        """Arkivhandlerne oppgir modeller, ikke apper, fordi de deler app med
        den aktive dataen. Utledningen må lese lista som `dumpdata` gjør."""
        from core.backup import utled_restore_models

        self.assertEqual(
            utled_restore_models(['patients.VaktArkiv', 'patients.ArkivertPasient'], []),
            ['patients.ArkivertPasient', 'patients.VaktArkiv'],
        )

    def test_fk_ut_av_settet_teller_ikke(self) -> None:
        """`Vaktliste.vakt` peker på `core.Vakt`, som ikke er vår å tømme."""
        from core.backup import utled_restore_models

        self.assertNotIn('core.Vakt', utled_restore_models(['vaktliste'], []))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PortalBackupTests(TestCase):
    """Portalfila: vakta og moduloppsettet.

    Uten den kan ingen modulfil gjenopprettes i en tom base — pasienter,
    oppdrag og vaktlister peker på `core.Vakt` med et heltall.
    """

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _prepare_backup_dir()

    def test_vakta_er_med_i_dumpen(self) -> None:
        vakt_for_year(2026)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='portal', kind=KIND_MANUAL)
            innhold = gzip.open(self.backup_dir / backup.filename, 'rb').read()
        modeller = {o['model'] for o in json.loads(innhold)}
        self.assertIn('core.vakt', modeller)
        self.assertIn('core.modulesettings', modeller)

    def test_backup_metadata_er_ikke_med(self) -> None:
        """Å laste `Backupplan` tilbake fra en backup ville gjenopplive rader
        for filer som ikke finnes."""
        from core.models import Backupplan

        vakt_for_year(2026)
        Backupplan.standardplanen()
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='portal', kind=KIND_MANUAL)
            innhold = gzip.open(self.backup_dir / backup.filename, 'rb').read()
        modeller = {o['model'] for o in json.loads(innhold)}
        for uonsket in ('core.backupplan', 'core.offsitekopi', 'core.notification'):
            with self.subTest(modell=uonsket):
                self.assertNotIn(uonsket, modeller)

    def test_rundtur_gjenoppretter_vakta(self) -> None:
        from core.models import Vakt

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            vakt = vakt_for_year(2026)
            navn = vakt.navn
            backup = create_backup(slug='portal', kind=KIND_MANUAL)

            Vakt.objects.all().delete()
            self.assertEqual(Vakt.objects.count(), 0)

            restore_backup(backup)

        self.assertEqual(Vakt.objects.count(), 1)
        gjenopprettet = Vakt.objects.first()
        self.assertEqual(gjenopprettet.navn, navn)
        self.assertEqual(gjenopprettet.pk, vakt.pk,
                         'Primærnøkkelen må overleve — modulfilene peker på '
                         'vakta med et heltall.')

    def test_modulesettings_uten_bruker(self) -> None:
        """`updated_by` strippes: med natural_foreign ville en slettet konto
        tatt hele gjenopprettingen med seg."""
        from core.models import ModuleSettings

        vakt_for_year(2026)
        bruker = CustomUser.objects.create_user(
            username='slettes', password='x', must_change_password=False)
        ms = ModuleSettings.objects.first() or ModuleSettings.objects.create(slug='patients')
        ms.updated_by = bruker
        ms.save()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='portal', kind=KIND_MANUAL)
            innhold = gzip.open(self.backup_dir / backup.filename, 'rb').read()
            bruker.delete()
            restore_backup(backup)   # skal ikke kaste

        for o in json.loads(innhold):
            if o['model'] == 'core.modulesettings':
                self.assertNotIn('updated_by', o['fields'])


# ─────────────────────────────────────────────────────────────────────────────
# Gjenoppretting av alle filene, i rekkefølge
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AlleFileneGjenopprettesTests(TestCase):
    """Den prøven som avgjør om backupen er en backup (`BACKUP.md` §3.6).

    En dump som ser riktig ut, men ikke lar seg laste tilbake, er ingenting
    verdt — og forskjellen viser seg bare når man faktisk laster den. Fram til
    portalhandleren kom 13. sep. 2026, feilet dette: `core.Vakt` lå ikke i noen
    fil, og pasienter, oppdrag og vaktlister peker alle på den med et heltall.
    Målt mot ekte PostgreSQL feilet alle tre modulfilene med
    «Key (vakt_id)=(1) is not present in table core_vakt».

    Rekkefølgen er bindende: **portal først**, deretter modulene.
    """

    #: `backlog` står sist, og **plasseringen er vilkårlig** — modulen er den
    #: eneste uten peker til `core.Vakt`, så den har ingen forutsetning om at
    #: portalfila er lastet først. De andre har det, og for dem er rekkefølgen
    #: bindende.
    REKKEFOLGE = ['portal', 'patients', 'arkiv', 'oppdrag', 'oppdrag_arkiv',
                  'vaktliste', 'backlog']

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _prepare_backup_dir()

    def _seed(self):
        from datetime import timedelta

        from oppdrag.models import Enhet, Lokasjon, Oppdrag
        from patients.models import Forstehjelper, Patient
        from vaktliste.models import (
            Korps, Mannskap, Ressurs, Ressursgruppe, Vaktliste, Vaktpost,
        )

        vakt = vakt_for_year(2026)
        fh = Forstehjelper.objects.create(name='Ola')
        for nr in (1, 2, 3):
            Patient.objects.create(pasientnummer=nr, vakt=vakt,
                                   problemstilling='Test', forstehjelper=fh)
        lok = Lokasjon.objects.create(navn='Scene')
        enhet = Enhet.objects.create(navn='Bil 1')
        Oppdrag.objects.create(vakt=vakt, oppdragsnummer=1, enhet=enhet,
                               problemstilling='Udefinert', hastegrad='Gul',
                               lokasjon=lok)
        korps = Korps.objects.create(navn='Testkorps')
        mannskap = Mannskap.objects.create(navn='Kari', korps=korps,
                                           telefon='99887766', issi='0401234')
        liste = Vaktliste.objects.create(vakt=vakt)
        ressurs = Ressurs.objects.create(
            vaktliste=liste, navn='Bil A',
            gruppe=Ressursgruppe.objects.first(), enhet=enhet)
        Vaktpost.objects.create(ressurs=ressurs, mannskap=mannskap,
                                fra_tid=timezone.now(),
                                til_tid=timezone.now() + timedelta(hours=8))
        return vakt

    def _tall(self):
        from oppdrag.models import Enhet, Oppdrag
        from patients.models import Patient
        from vaktliste.models import Mannskap, Ressurs, Vaktpost
        from core.models import Vakt

        return {
            'vakt': Vakt.objects.count(),
            'pasient': Patient.objects.count(),
            'oppdrag': Oppdrag.objects.count(),
            'enhet': Enhet.objects.count(),
            'mannskap': Mannskap.objects.count(),
            'ressurs': Ressurs.objects.count(),
            'vaktpost': Vaktpost.objects.count(),
        }

    def _tom_alt(self):
        """Tøm i barn-først-rekkefølge, vakta til slutt — den er det alt
        henger på, og PROTECT stopper den ellers."""
        from django.apps import apps as django_apps

        from core.models import Vakt

        for slug in self.REKKEFOLGE:
            for etikett in get_handler(slug).get_restore_models():
                if etikett == 'core.Vakt':
                    continue
                django_apps.get_model(etikett).objects.all().delete()
        Vakt.objects.all().delete()

    def test_alle_seks_filene_kan_lastes_i_rekkefolge(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            self._seed()
            fasit = self._tall()

            filer = {}
            for slug in self.REKKEFOLGE:
                filer[slug] = create_backup(slug=slug, kind=KIND_MANUAL)

            self._tom_alt()
            self.assertEqual(self._tall()['pasient'], 0, 'basen skal være tom nå')

            for slug in self.REKKEFOLGE:
                with self.subTest(slug=slug):
                    restore_backup(filer[slug])

        self.assertEqual(self._tall(), fasit)

    def test_vakta_er_med_saa_modulfilene_finner_den(self) -> None:
        """Uten `core.Vakt` i en fil feiler modulfilene på fremmednøkkelen —
        det var hullet `docs/TEKNISK_GJELD.md` §4 beskriver."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            vakt = self._seed()
            portalfil = create_backup(slug='portal', kind=KIND_MANUAL)
            raa = gzip.open(self.backup_dir / portalfil.filename, 'rb').read()

        pekere = {o['pk'] for o in json.loads(raa) if o['model'] == 'core.vakt'}
        self.assertIn(vakt.pk, pekere)

    def test_rekkefolgen_dekker_alle_modulfilene(self) -> None:
        """Hver registrert handler skal stå i rekkefølgen — er en av dem borte,
        er rekkefølgen over en løgn. `full` er unntaket: den er ikke en
        modulfil, den er hele basen i én, og gjenopprettes alene."""
        from core.models import Backupplan

        modulfiler = {h.slug for h in all_handlers()
                      if h.slug != Backupplan.FULL_SLUG}
        self.assertEqual(set(self.REKKEFOLGE), modulfiler)


# ─────────────────────────────────────────────────────────────────────────────
# Hel databasebackup
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HelBackupTests(TestCase):
    """Katastrofekopien: alt i databasen i én fil.

    Forskjellen fra modulfilene er ikke bare omfanget — den er **selvbærende**.
    Brukerne er med, så fremmednøkler til kontoer trenger ikke strippes, og
    den kan lastes inn i en base som ikke har noe fra før.
    """

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _prepare_backup_dir()

    def _modeller_i_fila(self, backup):
        raa = gzip.open(self.backup_dir / backup.filename, 'rb').read()
        return {o['model'] for o in json.loads(raa)}

    def test_brukere_og_mfa_er_med(self) -> None:
        from django_otp.plugins.otp_totp.models import TOTPDevice

        bruker = CustomUser.objects.create_user(
            username='medmfa', password='x', must_change_password=False)
        TOTPDevice.objects.create(user=bruker, name='telefon', confirmed=True)

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='full', kind=KIND_MANUAL)
        modeller = self._modeller_i_fila(backup)
        self.assertIn('accounts.customuser', modeller)
        self.assertIn('otp_totp.totpdevice', modeller)

    def test_sesjoner_og_contenttypes_er_utelatt(self) -> None:
        """`contenttypes` og `auth.permission` gjenskapes av `migrate`; lastes
        de på nytt, kolliderer primærnøklene. Sesjoner ville gitt gamle økter
        tilbake."""
        from django.contrib.sessions.models import Session

        Session.objects.create(session_key='abc123', session_data='x',
                               expire_date=timezone.now() + timedelta(days=1))
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='full', kind=KIND_MANUAL)
        modeller = self._modeller_i_fila(backup)
        for uonsket in ('sessions.session', 'contenttypes.contenttype',
                        'auth.permission', 'admin.logentry',
                        'patients.backup', 'core.backupplan', 'core.offsitekopi'):
            with self.subTest(modell=uonsket):
                self.assertNotIn(uonsket, modeller)

    def test_appene_regnes_ut_og_ikke_listes(self) -> None:
        """En hardkodet liste er en ny sjanse til å glemme en app — og en
        katastrofekopi som stille mangler en, er verre enn ingen."""
        apper = set(get_handler('full').collect_apps())
        for ventet in ('accounts', 'audit', 'core', 'patients', 'oppdrag',
                       'vaktliste', 'otp_totp', 'otp_static'):
            with self.subTest(app=ventet):
                self.assertIn(ventet, apper)
        self.assertNotIn('sessions', apper)

    def test_slettelista_dekker_hele_settet_paa_tvers_av_apper(self) -> None:
        """Brukeren og vakta skal tømmes sist: alt annet peker på dem."""
        rekkefolge = get_handler('full').get_restore_models()
        plass = {m: i for i, m in enumerate(rekkefolge)}
        self.assertLess(plass['accounts.ModulTilgang'], plass['accounts.CustomUser'])
        self.assertLess(plass['patients.Patient'], plass['core.Vakt'])
        self.assertLess(plass['vaktliste.Vaktpost'], plass['vaktliste.Mannskap'])

    def test_rundtur_over_hele_basen(self) -> None:
        from oppdrag.models import Enhet
        from patients.models import Patient
        from vaktliste.models import Korps

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            vakt = vakt_for_year(2026)
            Patient.objects.create(pasientnummer=7, vakt=vakt, problemstilling='X')
            Enhet.objects.create(navn='Bil 9')
            Korps.objects.create(navn='Korpset')
            bruker = CustomUser.objects.create_user(
                username='overlever', password='x', must_change_password=False)

            backup = create_backup(slug='full', kind=KIND_MANUAL)

            # Alt forsvinner — også kontoen.
            Patient.objects.all().delete()
            Enhet.objects.all().delete()
            Korps.objects.all().delete()
            bruker.delete()
            self.assertFalse(CustomUser.objects.filter(username='overlever').exists())

            restore_backup(backup)

        self.assertTrue(CustomUser.objects.filter(username='overlever').exists())
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Enhet.objects.get().navn, 'Bil 9')
        self.assertEqual(Korps.objects.get().navn, 'Korpset')

    def test_passordet_overlever(self) -> None:
        """En gjenoppretting man ikke kan logge inn etter, er ingen
        gjenoppretting."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            bruker = CustomUser.objects.create_user(
                username='innlogger', password='Hemmelig-123',
                must_change_password=False)
            hash_for = bruker.password
            backup = create_backup(slug='full', kind=KIND_MANUAL)
            bruker.delete()
            restore_backup(backup)

        etter = CustomUser.objects.get(username='innlogger')
        self.assertEqual(etter.password, hash_for)
        self.assertTrue(etter.check_password('Hemmelig-123'))

    def test_offsite_legger_den_under_eget_prefiks(self) -> None:
        """To oppbevaringstider krever to prefikser: livssyklusreglene i
        bucketen filtrerer på sti, og 90 dager kan ikke skilles fra 730 uten."""
        from core import offsite

        self.assertEqual(offsite.objektnavn('backup-full-x.json.gz', 'full'),
                         'full/backup-full-x.json.gz.enc')
        self.assertEqual(offsite.objektnavn('backup-patients-x.json.gz', 'patients'),
                         'backups/backup-patients-x.json.gz.enc')

    def test_planen_er_alltid_hver_24_time(self) -> None:
        """En hel base endrer seg konstant, så «ved endring» ville aldri hoppet
        over noe. «Alltid» er det ærlige valget — og 24 timer gir 90 filer på
        90 dager, mot 2 160 for hver time."""
        from core.models import Backupplan

        plan = Backupplan.hent('full')
        self.assertEqual(plan.modus, Backupplan.MODUS_ALLTID)
        self.assertEqual(plan.intervall_min, 24 * 60)
        self.assertEqual(plan.behold, 7)
        self.assertFalse(plan.arver, 'Den hele fila skal aldri følge standardplanen.')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SignalerFyrerIkkeUnderLoaddataTests(TestCase):
    """`loaddata` skal ikke utløse applikasjonslogikk.

    Django sender `raw=True` når en rad kommer fra en fixture. Fram til
    13. sep. 2026 så ingen av de atten signalmottakerne etter det, og det ga
    to reelle problemer:

    1. **Gjenoppretting feilet.** Handlerne leser relaterte objekter, og
       `loaddata` laster i filas rekkefølge — et `Vaktpost` kan komme før sitt
       `Mannskap`. Den hele databasebackupen stoppet på nettopp det:
       «Mannskap matching query does not exist», midt i en gjenoppretting.
    2. **Auditsporet ble støy.** En gjenoppretting av tusen pasienter skrev
       tusen «endret»-rader uten en bruker som hadde endret noe.
    """

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _prepare_backup_dir()

    #: Mottakere som med vilje står uten vakten, med begrunnelse.
    #: Unntaksliste og ikke en tillatelse — den skal ikke vokse.
    VAKTEN_UNNTATT = {
        # `fyll_app_label` fyller bare et tomt felt, og en rad fra en fixture
        # har alt sitt `app_label` med fra dumpen — så den kortslutter på
        # første linje. Vakten ville ikke endret noe, og å sette den ville
        # antydet at mottakeren gjør arbeid den ikke gjør.
        'audit/signals.py: AuditLog (pre_save)',
    }

    def test_alle_lagringssignaler_har_vakten(self) -> None:
        """Statisk: en ny mottaker skal ikke kunne glemme den.

        **Apper finnes ved å lete, ikke ved å stå i en liste** (14. sep.
        2026). Fram til da sto `('oppdrag', 'patients', 'vaktliste')` skrevet
        her for hånd, og `core/signals.py` gikk rett forbi den dagen den ble
        skrevet — regelen sa «alle lagringssignaler» og målte tre apper.
        Samme feil som testkommandoen i CLAUDE.md, som utelot `myproject` og
        sto slik i lang tid uten at noe sa fra. En liste over hvor man skal
        lete er alltid et sted færre enn der koden faktisk er.
        """
        import re
        from pathlib import Path

        from django.conf import settings

        filer = sorted(Path(settings.BASE_DIR).glob('*/signals.py'))
        self.assertGreaterEqual(
            len(filer), 4,
            'fant nesten ingen signals.py — glob-en leter feil sted, og da '
            'går testen grønn uten å måle noe')

        manglende = []
        for sti in filer:
            navn = sti.parent.name
            tekst = sti.read_text(encoding='utf-8')
            for treff in re.finditer(
                    r'@receiver\((pre_save|post_save), sender=(\w+)\)\n(.*?)def ',
                    tekst, re.S):
                if 'ikke_under_loaddata' in treff.group(3):
                    continue
                rad = f'{navn}/signals.py: {treff.group(2)} ({treff.group(1)})'
                if rad in self.VAKTEN_UNNTATT:
                    continue
                manglende.append(rad)
        self.assertEqual(
            manglende, [],
            'Disse lagringssignalene mangler @ikke_under_loaddata og vil '
            'fyre under `loaddata`:\n  ' + '\n  '.join(manglende))

    def test_gjenoppretting_skriver_en_rad_og_ikke_en_per_pasient(self) -> None:
        """Sporet skal si at noen gjenopprettet noe — ikke ramse opp hva fila
        inneholdt.

        Fem pasienter inn gir **én** rad, ikke fem eller femten. Uten
        `raw`-vakten ga en gjenoppretting av tusen pasienter tusen
        «endret»-rader uten en bruker som hadde endret noe.
        """
        from patients.models import Patient

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            vakt = vakt_for_year(2026)
            for nr in range(1, 6):
                Patient.objects.create(pasientnummer=nr, vakt=vakt,
                                       problemstilling='Test')
            backup = create_backup(slug='patients', kind=KIND_MANUAL)
            Patient.objects.all().delete()

            for_restore = AuditLog.objects.count()
            restore_backup(backup, kilde='test')

        self.assertEqual(Patient.objects.count(), 5)
        self.assertEqual(
            AuditLog.objects.count(), for_restore + 1,
            'Gjenopprettingen skal skrive nøyaktig én rad: at den skjedde.')
        rad = AuditLog.objects.order_by('-created_at').first()
        self.assertEqual(rad.field_name, 'restore')
        self.assertEqual(rad.new_value, backup.filename)
