"""Tester for backup-systemet.

Kjør med: python manage.py test patients.tests_backup
"""
import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.utils import timezone

from accounts.models import CustomUser, LoginEvent
from audit.models import AuditLog
from patients.models import Patient, AppSetting, Backup, BackupConfig
from patients.backup_service import create_backup, purge_old_backups, get_backup_dir
from patients.services import set_active_year


# Hjelpefunksjon for å sette backup-mappe til temp-dir under testing
def _test_backup_dir(tmp_path):
    """Setter BACKUP_DIR til en midlertidig testmappe."""
    return str(tmp_path)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BackupServiceTests(TestCase):
    """Tester for backup_service.py – oppretting, restore og purge."""

    def setUp(self):
        # Opprett admin-bruker for tester som trenger det
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        # Bruk en unik testmappe for backupfiler
        self.backup_dir = Path(os.environ.get('BACKUP_DIR', '/tmp/test-backups-backup'))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Rydd opp testfiler etter testen."""
        for f in self.backup_dir.glob('backup-*.json.gz'):
            f.unlink(missing_ok=True)
        for f in self.backup_dir.glob('.restore-tmp-*.json'):
            f.unlink(missing_ok=True)

    def test_create_backup_creates_file_and_metadata(self):
        """create_backup skal lage en gzip-fil og en Backup-instans i databasen."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin, note='Testnotat')

        # Verifiser metadata
        self.assertIsNotNone(backup.pk)
        self.assertEqual(backup.kind, 'manual')
        self.assertEqual(backup.note, 'Testnotat')
        self.assertEqual(backup.created_by, self.admin)
        self.assertGreater(backup.size_bytes, 0)

        # Verifiser at filen finnes på disk
        path = self.backup_dir / backup.filename
        self.assertTrue(path.exists(), f'Backup-filen {path} mangler')

        # Verifiser at innholdet er gyldig gzip med JSON
        with gzip.open(path, 'rb') as f:
            raw = f.read()
        data = json.loads(raw)
        self.assertIsInstance(data, list)

        # Verifiser at Backup-modellen finnes i databasen
        self.assertTrue(Backup.objects.filter(pk=backup.pk).exists())

    def test_restore_creates_pre_restore_backup(self):
        """restore_backup skal lage en pre_restore backup som sikkerhetsnett."""
        # Lag en backup å gjenopprette fra
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            original = create_backup(kind='manual', user=self.admin)
            count_before = Backup.objects.count()

            restore_backup_fn = __import__(
                'patients.backup_service', fromlist=['restore_backup']
            ).restore_backup
            restore_backup_fn(original, user=self.admin)

        # Det skal nå finnes én ekstra backup av typen pre_restore
        pre_restore_backups = Backup.objects.filter(kind='pre_restore')
        self.assertTrue(pre_restore_backups.exists(),
                        'Det skal finnes en pre_restore backup etter gjenoppretting')

    def test_restore_replaces_data(self):
        """Gjenoppretting skal erstatte data: pasient A bevares, pasient B forsvinner."""
        set_active_year(2026)
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            # Opprett pasient A og ta backup
            Patient.objects.create(pasientnummer=101, year=2026, problemstilling='Pasient A')
            backup = create_backup(kind='manual', user=self.admin, note='Med A')

            # Slett A, opprett B
            Patient.objects.all().delete()
            Patient.objects.create(pasientnummer=102, year=2026, problemstilling='Pasient B')

            # Gjenopprett
            from patients.backup_service import restore_backup
            restore_backup(backup, user=self.admin)

        # Etter restore: A skal finnes, B skal ikke finnes
        pnr_list = list(Patient.objects.values_list('pasientnummer', flat=True))
        self.assertIn(101, pnr_list, 'Pasient A skal finnes etter restore')
        self.assertNotIn(102, pnr_list, 'Pasient B skal ikke finnes etter restore')

    def test_purge_deletes_old_backups(self):
        """purge_old_backups skal slette backups eldre enn 72 timer."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin)

        # Manipulér created_at til >72 timer siden
        old_time = timezone.now() - timezone.timedelta(hours=73)
        Backup.objects.filter(pk=backup.pk).update(created_at=old_time)

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            purged = purge_old_backups()

        self.assertEqual(purged, 1)
        self.assertFalse(Backup.objects.filter(pk=backup.pk).exists(),
                         'Gammel backup skal slettes fra databasen')

    def test_purge_keeps_recent_backups(self):
        """purge_old_backups skal ikke slette ferske backups (<72 timer)."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin)
            purged = purge_old_backups()

        self.assertEqual(purged, 0)
        self.assertTrue(Backup.objects.filter(pk=backup.pk).exists())

    def test_backup_excludes_users_and_audit(self):
        """SIKKERHET: Backup-filen skal IKKE inneholde brukere, passord,
        revisjonslogg, LoginEvent eller sesjoner.
        """
        # Lag noen sensitive data som ikke skal havne i backupen
        CustomUser.objects.create_user(
            username='hemmelig', password='super-hemmelig-passord',
            role='read_write', must_change_password=False,
        )
        AuditLog.objects.create(
            table_name='Patient', record_id=1, action='update',
            field_name='problemstilling', new_value='hemmelig verdi',
        )
        LoginEvent.objects.create(username_attempt='hemmelig', success=True, ip='127.0.0.1')

        # Lag en pasient slik at backup har noe pasientdata
        Patient.objects.create(pasientnummer=1, year=2026, problemstilling='test')

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin)

        # Les backup-innholdet
        path = self.backup_dir / backup.filename
        with gzip.open(path, 'rb') as f:
            raw = f.read().decode('utf-8')
        data = json.loads(raw)

        # Samle alle modellnavn i backupen
        model_names = {entry['model'] for entry in data}

        # Sjekk at ingen sensitive modeller er med
        forbidden = {
            'accounts.customuser',
            'accounts.loginevent',
            'audit.auditlog',
            'sessions.session',
            'patients.backup',
            'patients.backupconfig',
        }
        overlap = forbidden & model_names
        self.assertEqual(overlap, set(),
                         f'Backup skal ikke inneholde sensitive modeller, fant: {overlap}')

        # Ekstra sjekk: passord-hash-prefikser skal ikke finnes i rå innhold
        self.assertNotIn('pbkdf2_', raw,
                         'Backup skal ikke inneholde passord-hasher (pbkdf2_*)')
        self.assertNotIn('argon2', raw,
                         'Backup skal ikke inneholde passord-hasher (argon2)')

        # Pasientdata skal faktisk være med
        self.assertIn('patients.patient', model_names,
                      'Pasientdata skal være med i backupen')

    def test_restore_preserves_users_and_audit(self):
        """SIKKERHET: Restore skal ikke slette brukere, revisjonslogg eller
        LoginEvent. Disse skal bevares på tvers av restore.
        """
        set_active_year(2026)
        # Opprett testdata som IKKE skal røres av restore
        other_user = CustomUser.objects.create_user(
            username='annen', password='pwd', role='lead',
            must_change_password=False,
        )
        AuditLog.objects.create(
            table_name='Patient', record_id=1, action='create',
            field_name='n/a', new_value='før-restore-spor',
        )
        LoginEvent.objects.create(username_attempt='annen', success=True, ip='1.2.3.4')

        users_before = set(CustomUser.objects.values_list('pk', flat=True))
        audit_count_before = AuditLog.objects.count()
        login_count_before = LoginEvent.objects.count()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            Patient.objects.create(pasientnummer=201, year=2026, problemstilling='A')
            backup = create_backup(kind='manual', user=self.admin)

            from patients.backup_service import restore_backup
            restore_backup(backup, user=self.admin)

        # Brukere bevart (alle originale, inkludert self.admin og other_user)
        users_after = set(CustomUser.objects.values_list('pk', flat=True))
        self.assertTrue(users_before.issubset(users_after),
                        'Alle brukere som fantes før restore skal fortsatt finnes')
        self.assertTrue(CustomUser.objects.filter(pk=other_user.pk).exists(),
                        'Annen bruker skal ikke slettes av restore')

        # Revisjonslogg bevart (ny audit-logg kan komme til via view-laget,
        # men eksisterende rader skal ikke slettes)
        self.assertGreaterEqual(AuditLog.objects.count(), audit_count_before,
                                'Eksisterende auditlog skal ikke slettes')
        self.assertTrue(
            AuditLog.objects.filter(new_value='før-restore-spor').exists(),
            'Spesifikk auditlog-rad skal fortsatt finnes etter restore',
        )

        # LoginEvent bevart
        self.assertGreaterEqual(LoginEvent.objects.count(), login_count_before,
                                'LoginEvent skal ikke slettes av restore')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BackupAPITests(TestCase):
    """Tester for backup API-endepunkter."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        self.lead = CustomUser.objects.create_user(
            username='lead', password='pwd', role='lead',
            must_change_password=False,
        )
        self.rw = CustomUser.objects.create_user(
            username='rw', password='pwd', role='read_write',
            must_change_password=False,
        )
        self.ro = CustomUser.objects.create_user(
            username='ro', password='pwd', role='read_only',
            must_change_password=False,
        )
        self.backup_dir = Path('/tmp/test-backups-api')
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        # Windows: FileResponse kan holde fil åpen til GC kjører. Kjør GC 
        # eksplisitt og retry på PermissionError.
        import gc, time
        gc.collect()
        for pattern in ('backup-*.json.gz', '.restore-tmp-*.json'):
            for f in self.backup_dir.glob(pattern):
                for attempt in range(5):
                    try:
                        f.unlink(missing_ok=True)
                        break
                    except PermissionError:
                        gc.collect()
                        time.sleep(0.1)

    def _admin_client(self):
        c = Client()
        c.force_login(self.admin)
        return c

    def _client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_only_admin_can_list_backups(self):
        """lead, read_write og read_only skal få 403 på backup-listen."""
        for user in [self.lead, self.rw, self.ro]:
            c = self._client_for(user)
            resp = c.get('/pasienter/api/backup/')
            self.assertEqual(resp.status_code, 403,
                             f'Bruker med rolle {user.role} skal få 403')

    def test_admin_can_list_backups(self):
        """Admin kan hente backup-listen med 200."""
        c = self._admin_client()
        resp = c.get('/pasienter/api/backup/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn('config', body)
        self.assertIn('backups', body)

    def test_only_admin_can_create_backup(self):
        """Ikke-admin brukere skal få 403 ved forsøk på å lage backup."""
        for user in [self.lead, self.rw, self.ro]:
            c = self._client_for(user)
            resp = c.post('/pasienter/api/backup/create/',
                          data='{}',
                          content_type='application/json')
            self.assertEqual(resp.status_code, 403,
                             f'Bruker med rolle {user.role} skal få 403')

    def test_admin_can_create_backup(self):
        """Admin kan lage en manuell backup."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            c = self._admin_client()
            resp = c.post('/pasienter/api/backup/create/',
                          data=json.dumps({'note': 'Testbackup'}),
                          content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body.get('ok'))
        self.assertIn('filename', body)
        self.assertGreater(body['size_bytes'], 0)

    def test_restore_requires_confirm_string(self):
        """Restore uten riktig confirm-streng skal gi 400."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin)
            c = self._admin_client()
            # Feil confirm-verdi
            resp = c.post(f'/pasienter/api/backup/{backup.pk}/restore/',
                          data=json.dumps({'confirm': 'ja'}),
                          content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_restore_accepts_correct_confirm(self):
        """Restore med riktig confirm='GJENOPPRETT' skal lykkes (200)."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin)
            c = self._admin_client()
            resp = c.post(f'/pasienter/api/backup/{backup.pk}/restore/',
                          data=json.dumps({'confirm': 'GJENOPPRETT'}),
                          content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('ok'))

    def test_download_logged_to_audit(self):
        """Nedlasting av backup skal logges i AuditLog."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin)
            c = self._admin_client()
            count_before = AuditLog.objects.filter(field_name='backup_downloaded').count()
            resp = c.get(f'/pasienter/api/backup/{backup.pk}/download/')

        self.assertEqual(resp.status_code, 200)
        # Les streaming-innholdet og lukk FileResponse eksplisitt – Windows
        # tillater ikke sletting av en åpen fil i tearDown.
        b''.join(resp.streaming_content) if getattr(resp, 'streaming', False) else None
        resp.close()
        count_after = AuditLog.objects.filter(field_name='backup_downloaded').count()
        self.assertEqual(count_after, count_before + 1,
                         'Nedlasting skal logges i AuditLog')

    def test_config_update_rejects_invalid_interval(self):
        """Backup-konfig med ugyldig intervall skal avvises med 400."""
        c = self._admin_client()
        resp = c.post('/pasienter/api/backup/config/',
                      data=json.dumps({'interval_minutes': 999}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_config_update_accepts_valid_interval(self):
        """Gyldig intervall (0, 30, 60, 360, 1440) skal aksepteres med 200."""
        c = self._admin_client()
        for interval in [0, 30, 60, 360, 1440]:
            resp = c.post('/pasienter/api/backup/config/',
                          data=json.dumps({'interval_minutes': interval}),
                          content_type='application/json')
            self.assertEqual(resp.status_code, 200,
                             f'Intervall {interval} skal aksepteres')
            cfg = BackupConfig.get()
            self.assertEqual(cfg.interval_minutes, interval)

    def test_delete_backup(self):
        """Admin kan slette en backup via DELETE-endepunktet."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='manual', user=self.admin)
            c = self._admin_client()
            resp = c.delete(f'/pasienter/api/backup/{backup.pk}/')

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Backup.objects.filter(pk=backup.pk).exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BackupResetIntegrationTests(TestCase):
    """Test at reset_active_year lager pre_reset backup automatisk."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        self.backup_dir = Path('/tmp/test-backups-reset')
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        set_active_year(2026)
        Patient.objects.create(pasientnummer=1, year=2026)

    def tearDown(self):
        for f in self.backup_dir.glob('backup-*.json.gz'):
            f.unlink(missing_ok=True)

    def test_reset_active_year_creates_pre_reset_backup(self):
        """reset_active_year_view skal automatisk lage en pre_reset backup."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            c = Client()
            c.force_login(self.admin)
            resp = c.post('/pasienter/api/reset-active-year/',
                          data=json.dumps({'confirm': True}),
                          content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        pre_reset = Backup.objects.filter(kind='pre_reset')
        self.assertTrue(pre_reset.exists(),
                        'Det skal finnes en pre_reset backup etter reset')
        self.assertIn('2026', pre_reset.first().note)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BackupContentHashSkipTests(TestCase):
    """Forbedring #0: auto-backups med identisk innhold skal hoppes over.

    Manuelle og pre_*-backups skal ALLTID lagres uavhengig av hash.
    """

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin',
            must_change_password=False,
        )
        self.backup_dir = Path(os.environ.get('BACKUP_DIR', '/tmp/test-backups-hash'))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for f in self.backup_dir.glob('backup-*.json.gz'):
            f.unlink(missing_ok=True)

    def test_auto_backup_lagrer_content_hash(self):
        """Første auto-backup skal lagre SHA256 over JSON-innholdet."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(kind='auto', note='Første')
        self.assertIsNotNone(backup, 'Første auto-backup skal alltid lagres')
        self.assertEqual(len(backup.content_hash), 64,
                         'content_hash skal være SHA256 hex (64 tegn)')
        self.assertNotEqual(backup.content_hash, '')

    def test_identisk_auto_backup_hoppes_over(self):
        """Andre auto-backup med identisk innhold skal returnere None og ikke lage fil."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            first = create_backup(kind='auto', note='Første')
            self.assertIsNotNone(first)
            count_after_first = Backup.objects.filter(kind='auto').count()

            # Ingen dataendring – andre auto-backup skal hoppes over
            second = create_backup(kind='auto', note='Andre')

        self.assertIsNone(second, 'Andre auto-backup skal returnere None')
        self.assertEqual(Backup.objects.filter(kind='auto').count(),
                         count_after_first,
                         'Antall auto-backups i DB skal være uendret')

    def test_endring_gir_ny_auto_backup(self):
        """Etter dataendring skal neste auto-backup lagres som vanlig."""
        import time as _time
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            first = create_backup(kind='auto', note='Før endring')
            self.assertIsNotNone(first)

            # Gjør en pasient-endring slik at JSON-innholdet endres
            Patient.objects.create(pasientnummer=42, year=2026,
                                    problemstilling='Ny pasient for hash-test')

            # Sov 1.1 s slik at filnavn-tidsstemplet (med sekund-uppløsning)
            # blir unikt mellom de to backupene. I prod er intervallet alltid
            # mye større, så dette er kun en test-artefakt.
            _time.sleep(1.1)

            second = create_backup(kind='auto', note='Etter endring')

        self.assertIsNotNone(second, 'Etter endring skal ny auto-backup lagres')
        self.assertNotEqual(first.content_hash, second.content_hash,
                            'Hashen skal endres når data endres')

    def test_manuell_backup_lagres_alltid(self):
        """Manuelle backups skal lagres selv om innholdet er identisk med siste auto."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            auto = create_backup(kind='auto', note='Auto')
            self.assertIsNotNone(auto)

            # Manuell backup med samme data – skal lagres uansett
            manual = create_backup(kind='manual', user=self.admin, note='Manuell')

        self.assertIsNotNone(manual,
                             'Manuell backup skal alltid lagres uansett hash-likhet')
        self.assertEqual(manual.content_hash, auto.content_hash,
                         'Hashen skal være lik når innholdet er identisk')

    def test_pre_restore_lagres_alltid(self):
        """pre_restore-backups er sikkerhetsnett og skal aldri hoppes over."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            auto = create_backup(kind='auto')
            self.assertIsNotNone(auto)

            pre = create_backup(kind='pre_restore', user=self.admin,
                                note='Før gjenoppretting')

        self.assertIsNotNone(pre, 'pre_restore skal alltid lagres')

    def test_hash_skip_ignorerer_gamle_uten_hash(self):
        """Eksisterende auto-backups uten content_hash (pre-#0) skal ikke blokkere ny backup."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            # Simuler en gammel backup-rad uten hash
            Backup.objects.create(
                filename='gammel-uten-hash.json.gz', kind='auto',
                size_bytes=100, content_hash='',
            )

            # Ny auto-backup skal lagres normalt (siste auto med hash finnes ikke)
            ny = create_backup(kind='auto', note='Ny etter gammel')

        self.assertIsNotNone(ny, 'Ny auto-backup skal lagres når siste mangler hash')
        self.assertNotEqual(ny.content_hash, '')
