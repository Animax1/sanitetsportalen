"""Sikkerhetsgjennomgangen 28. sep. 2026, pulje 3: backup og offsite.

**Trusselen:** en som har skrivenøkkelen til bucketen, men ikke
`OFFSITE_BACKUP_KEY`. Hun kan ikke lese eller lage en backup, men hun kan
flytte og gi nytt navn til dem som ligger der. Før dette:

- chifferteksten var ikke bundet til navnet sitt (AAD var bare `SPBK1`),
- modulen ble lest av S3-metadata hun selv setter,
- og `restore_backup` *advarte* om modeller utenfor modulen, men lastet dem.

En gammel hel dump lagt ut som «pasientfil» ga da tilbake gamle passordhasher og
TOTP-hemmeligheter, uten `--full`-sperra. Og motsatt: en modulfil lagt ut som
`backup-full-…` ville, gjenopprettet som hel database, tømt alle tabellene og
lastet én modul.

`SPBK2` binder navnet for nye filer. **`SPBK1` må fortsatt leses** — filene
ligger 730 dager — og kan fortsatt gis nytt navn. Derfor er sperrene i
gjenopprettingen det egentlige vernet, og de er skrevet for å ikke avvise en
eneste ekte gammel fil: se `ModulgrensenTests`.
"""
from __future__ import annotations

import gzip
import json
import os
import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog
from core import offsite
from core.backup import KIND_MANUAL, create_backup, get_backup_dir, get_handler, restore_backup
from core.models import Backup, Backupplan
from core.tests_offsite import KONFIG, FalskS3

#: Laget med koden fra før 29. sep. 2026 — `krypter()` med `SPBK1` og AAD = `SPBK1`.
#: Skal aldri regenereres: det er en fil i det gamle formatet, ikke en test av
#: hva formatet er i dag.
SPBK1_NOKKEL = 'gammel-testnokkel-for-spbk1-formatet-0123456789'
SPBK1_BLOB = bytes.fromhex(
    '5350424b318490a68a81d9247e385f2d869b80c9dfc7492f24a4a64e31cff8c6349371d22ca2936da6'
    'f8110046aefcb9afdcbb86266660e91d565efe0ae5b1b9a41319b1869771da04603a05fb4d9b1932c8a7'
    'd69c31a4ca42d3579cfb9b9648')
SPBK1_KLARTEKST = bytes.fromhex(
    '1f8b08000000000002ff8bae56cacd4f49cd51b252504ace2f4ad52b4bcc2e51d251502ac8060a1902'
    '196999a93929c5404e756d6d2c002194ce4d2f000000')


class KrypteringTests(SimpleTestCase):

    def test_gammelt_format_leses_fortsatt(self):
        """Filene i bucketen er i `SPBK1` i 730 dager. Brekker dette, er de uleselige."""
        self.assertEqual(offsite.dekrypter(SPBK1_BLOB, SPBK1_NOKKEL, objekt='hva-som-helst'),
                         SPBK1_KLARTEKST)
        self.assertEqual(json.loads(gzip.decompress(SPBK1_KLARTEKST))[0]['model'], 'core.vakt')

    def test_nytt_format_er_bundet_til_navnet(self):
        blob = offsite.krypter(b'data', 'n', objekt='backups/a.json.gz.enc')
        self.assertTrue(blob.startswith(offsite.MAGI))
        self.assertEqual(offsite.MAGI, b'SPBK2')
        self.assertEqual(offsite.dekrypter(blob, 'n', objekt='backups/a.json.gz.enc'), b'data')
        with self.assertRaises(ValueError):
            offsite.dekrypter(blob, 'n', objekt='backups/b.json.gz.enc')
        with self.assertRaises(ValueError):
            offsite.dekrypter(blob, 'n', objekt='full/a.json.gz.enc')

    def test_nytt_format_krever_navnet(self):
        """Tomt navn på begge sider ville gitt en fil uten binding som dekrypterer
        feilfritt — og da er `SPBK2` `SPBK1` med et annet merke."""
        with self.assertRaises(ValueError):
            offsite.krypter(b'data', 'n', objekt='')
        blob = offsite.krypter(b'data', 'n', objekt='backups/a.json.gz.enc')
        with self.assertRaises(ValueError):
            offsite.dekrypter(blob, 'n', objekt='')


class _Offsite(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = patch.dict(os.environ, {'BACKUP_DIR': self._tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.s3 = FalskS3()
        klient = patch('core.offsite._klient', return_value=self.s3)
        klient.start()
        self.addCleanup(klient.stop)


@override_settings(**KONFIG)
class HentingTests(_Offsite):

    def _lastet_opp(self, slug='patients'):
        backup = create_backup(slug, KIND_MANUAL)
        objekt = offsite.objektnavn(backup.filename, slug)
        (get_backup_dir() / backup.filename).unlink()
        Backup.objects.all().delete()
        return backup.filename, objekt

    def test_omdoept_ny_fil_avvises(self):
        """Selve angrepet mot `SPBK2`: en hel dump lagt ut som modulfil."""
        _, full_objekt = self._lastet_opp('full')
        falskt = 'backups/backup-patients-manual-20990101-000000-000000.json.gz.enc'
        self.s3.objekter[falskt] = dict(self.s3.objekter[full_objekt])
        with self.assertRaises(ValueError):
            offsite.hent(falskt)
        self.assertFalse(Backup.objects.exists())
        self.assertFalse((get_backup_dir() / 'backup-patients-manual-20990101-000000-000000.json.gz').exists())

    def test_modulen_leses_av_navnet_ikke_av_metadata(self):
        filnavn, objekt = self._lastet_opp('patients')
        self.s3.objekter[objekt]['Metadata'] = {'modul': 'full', 'kind': 'pre_restore'}
        backup, _ = offsite.hent(objekt)
        self.assertEqual((backup.module_slug, backup.kind), ('patients', 'manual'))

    def test_skriver_ikke_over_en_fil_som_finnes(self):
        filnavn, objekt = self._lastet_opp('patients')
        (get_backup_dir() / filnavn).write_bytes(b'lokal fil, annen innhold')
        with self.assertRaises(ValueError):
            offsite.hent(objekt)
        self.assertEqual((get_backup_dir() / filnavn).read_bytes(), b'lokal fil, annen innhold')

    def test_samme_fil_to_ganger_er_greit(self):
        _, objekt = self._lastet_opp('patients')
        offsite.hent(objekt)
        offsite.hent(objekt)
        self.assertEqual(Backup.objects.count(), 1)

    def test_gammelt_format_sier_fra(self):
        filnavn = 'backup-portal-manual-20260913-101500-000000.json.gz'
        objekt = f'backups/{filnavn}.enc'
        self.s3.objekter[objekt] = {'Body': SPBK1_BLOB, 'Metadata': {}, 'Bucket': 'x'}
        with override_settings(OFFSITE_BACKUP_KEY=SPBK1_NOKKEL):
            backup, sti = offsite.hent(objekt)
        self.assertEqual(sti.read_bytes(), SPBK1_KLARTEKST)
        self.assertIn('SPBK1', backup.note)

    def test_gammel_fil_under_feil_prefiks_avvises(self):
        """For `SPBK1` er prefikset ikke autentisert; sjekken i `hent()` er det som holder."""
        objekt = 'full/backup-portal-manual-20260913-101500-000000.json.gz.enc'
        self.s3.objekter[objekt] = {'Body': SPBK1_BLOB, 'Metadata': {}, 'Bucket': 'x'}
        with override_settings(OFFSITE_BACKUP_KEY=SPBK1_NOKKEL):
            with self.assertRaises(ValueError):
                offsite.hent(objekt)
        self.assertFalse(Backup.objects.exists())

    def test_filnavn_uten_modul_avvises(self):
        """En gyldig gammel fil under et navn som ikke sier hvilken modul den er."""
        for navn in ('tull.json.gz', 'backup-finnesikke-manual-20260913-101500-000000.json.gz'):
            with self.subTest(navn=navn):
                self.s3.objekter[f'backups/{navn}.enc'] = {
                    'Body': SPBK1_BLOB, 'Metadata': {'modul': 'patients'}, 'Bucket': 'x'}
                with override_settings(OFFSITE_BACKUP_KEY=SPBK1_NOKKEL):
                    with self.assertRaises(ValueError):
                        offsite.hent(f'backups/{navn}.enc')
                self.assertFalse((get_backup_dir() / navn).exists())
        self.assertFalse(Backup.objects.exists())


def _fil(navn, objekter):
    sti = get_backup_dir() / navn
    sti.write_bytes(gzip.compress(json.dumps(objekter).encode()))
    from core.backup import slug_fra_filnavn
    return Backup.objects.create(filename=navn, kind='manual', size_bytes=1,
                                 module_slug=slug_fra_filnavn(navn) or 'patients')


@override_settings(SECURE_SSL_REDIRECT=False)
class ModulgrensenTests(TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = patch.dict(os.environ, {'BACKUP_DIR': self._tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.bruker = CustomUser.objects.create_user(username='naa', password='x')

    def test_hel_dump_som_modulfil_avvises_for_noe_er_rort(self):
        with patch.dict(os.environ, {'BACKUP_DIR': self._tmp.name}):
            hel = create_backup('full', KIND_MANUAL)
        raa = (get_backup_dir() / hel.filename).read_bytes()
        falsk = 'backup-patients-manual-20990101-000000-000000.json.gz'
        (get_backup_dir() / falsk).write_bytes(raa)
        backup = Backup.objects.create(filename=falsk, kind='manual', size_bytes=1,
                                       module_slug='patients')
        CustomUser.objects.create_user(username='kom_etter', password='x')
        antall_backuper = Backup.objects.count()

        with self.assertRaises(ValueError) as cm:
            restore_backup(backup)
        self.assertIn('accounts.customuser', str(cm.exception))
        self.assertTrue(CustomUser.objects.filter(username='kom_etter').exists())
        self.assertEqual(Backup.objects.count(), antall_backuper, 'intet pre_restore-bilde')

    def test_modulfil_som_hel_database_avvises(self):
        """Motsatt vei: ellers tømmes alle tabellene og én modul lastes."""
        backup = _fil('backup-full-manual-20990101-000000-000000.json.gz',
                      [{'model': 'vaktliste.korps', 'pk': 1, 'fields': {'navn': 'K', 'created_at': '2026-09-01T00:00:00Z', 'updated_at': '2026-09-01T00:00:00Z'}}])
        with self.assertRaises(ValueError) as cm:
            restore_backup(backup)
        self.assertIn('ingen brukere', str(cm.exception))
        self.assertTrue(CustomUser.objects.filter(username='naa').exists())

    def test_raden_og_navnet_maa_si_samme_modul(self):
        backup = _fil('backup-patients-manual-20990101-000000-000000.json.gz', [])
        Backup.objects.filter(pk=backup.pk).update(module_slug='vaktliste')
        backup.refresh_from_db()
        with self.assertRaises(ValueError):
            restore_backup(backup)

    def test_egne_modeller_lastes(self):
        """Motprøven."""
        backup = _fil('backup-vaktliste-manual-20990101-000000-000000.json.gz',
                      [{'model': 'vaktliste.korps', 'pk': 91, 'fields': {'navn': 'Korpset', 'created_at': '2026-09-01T00:00:00Z', 'updated_at': '2026-09-01T00:00:00Z'}}])
        restore_backup(backup)
        from vaktliste.models import Korps
        self.assertEqual(Korps.objects.get(pk=91).navn, 'Korpset')

    def test_gammel_pasientfil_med_innstillinger_lastes(self):
        """Pasientfilene fra før 14. sep. 2026 bærer `patients.appsetting`, som nå er
        `core.appsetting`. De ligger 730 dager offsite og skal fortsatt kunne brukes."""
        from core.models import AppSetting
        backup = _fil('backup-patients-manual-20260912-101500-000000.json.gz',
                      [{'model': 'patients.appsetting', 'pk': 'gammel_nokkel',
                        'fields': {'value': '7'}}])
        restore_backup(backup)
        self.assertEqual(AppSetting.objects.get(pk='gammel_nokkel').value, '7')

    def test_grensen_gaar_paa_appen_ikke_paa_dagens_utelatte(self):
        """KO-filene fra 17.–27. sep. bærer modeller som siden er utelatt. Samme app —
        de skal ikke avvises. Et arkiv lastet inn som pasientfil er samme app også;
        det er prisen, og den er liten: brukere, MFA og logg er i andre apper."""
        from core.backup.service import modeller_utenfor
        self.assertEqual(modeller_utenfor(get_handler('ko'), ['ko.ansvarsmerke', 'ko.hendelselest']), [])
        self.assertEqual(modeller_utenfor(get_handler('patients'), ['core.appsetting']), [])
        self.assertEqual(modeller_utenfor(get_handler('patients'),
                                          ['patients.patient', 'accounts.customuser', 'otp_totp.totpdevice']),
                         ['accounts.customuser', 'otp_totp.totpdevice'])
        self.assertEqual(modeller_utenfor(get_handler('arkiv'), ['patients.patient']), ['patients.patient'])
        self.assertEqual(modeller_utenfor(get_handler('portal'), ['accounts.customuser']),
                         ['accounts.customuser'])

    def test_hver_modul_godtar_sin_egen_fil(self):
        """Ingen handler skal avvise det den selv skriver."""
        from core.backup import all_handlers
        from core.backup.service import modeller_utenfor
        from core.backup.handlers import utled_restore_models
        for handler in all_handlers():
            with self.subTest(slug=handler.slug):
                egne = [m.lower() for m in utled_restore_models(handler.collect_apps(),
                                                                handler.collect_exclude())]
                self.assertEqual(modeller_utenfor(handler, egne), [])

    def test_auditraden_peker_paa_for_bildet(self):
        backup = _fil('backup-vaktliste-manual-20990101-000000-000000.json.gz', [])
        restore_backup(backup)
        rad = AuditLog.objects.get(field_name='restore')
        pre = Backup.objects.get(kind='pre_restore')
        self.assertIn(pre.filename, rad.old_value)


class VerifiserBackupTests(TestCase):
    """`verifiser_backup` arvet `OFFSITE_*` og lastet engangsbasens bilder opp."""

    def test_underprosessen_faar_ingen_offsite_variabler(self):
        from core.management.commands.verifiser_backup import Command
        miljo = Command.engangsmiljo({'OFFSITE_S3_BUCKET': 'b', 'OFFSITE_S3_ACCESS_KEY': 'a',
                                      'OFFSITE_S3_SECRET_KEY': 's', 'OFFSITE_BACKUP_KEY': 'k',
                                      'PATH': '/bin'}, basefil='/tmp/x.sqlite3', backup_dir='/tmp/b')
        for navn in ('OFFSITE_S3_BUCKET', 'OFFSITE_S3_ACCESS_KEY', 'OFFSITE_S3_SECRET_KEY',
                     'OFFSITE_BACKUP_KEY'):
            self.assertEqual(miljo[navn], '', navn)
        self.assertEqual(miljo['PATH'], '/bin')
        self.assertEqual(miljo['PORTAL_ENGANGSBASE'], '1')


class NokkellengdeTests(SimpleTestCase):

    def test_kort_nokkel_gir_advarsel(self):
        with override_settings(OFFSITE_BACKUP_KEY='kort-passord'):
            self.assertIn('32', offsite.nokkel_advarsel())
        with override_settings(OFFSITE_BACKUP_KEY='x' * 32):
            self.assertEqual(offsite.nokkel_advarsel(), '')
        with override_settings(OFFSITE_BACKUP_KEY=''):
            self.assertEqual(offsite.nokkel_advarsel(), '', 'mangler vises av `mangler()`')


@override_settings(SECURE_SSL_REDIRECT=False)
class BackupplanSetterSporTests(TestCase):

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='adm_p3', password='x', role='admin', must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.c = Client()
        self.c.force_login(self.admin)

    def test_aa_slaa_av_pasientbackupen_logges(self):
        plan = Backupplan.hent('patients')
        data = {f'patients-{k}': v for k, v in {
            'folger_standard': '', 'modus': Backupplan.MODUS_AV, 'intervall_verdi': '1',
            'intervall_enhet': Backupplan.ENHET_TIME, 'behold': '50'}.items()}
        self.c.post('/portal-admin/backup/plan/patients/', data)
        plan.refresh_from_db()
        self.assertEqual(plan.modus, Backupplan.MODUS_AV)
        felt = set(AuditLog.objects.filter(table_name='core_backupplan', record_id=plan.pk)
                   .values_list('field_name', flat=True))
        self.assertIn('modus', felt)
        rad = AuditLog.objects.get(table_name='core_backupplan', field_name='modus')
        self.assertEqual((rad.new_value, rad.user), (Backupplan.MODUS_AV, self.admin))

    def test_klokka_logges_ikke(self):
        from django.utils import timezone
        plan = Backupplan.hent('patients')
        plan.sist_sjekket_at = timezone.now()
        plan.sist_resultat = 'uendret'
        plan.save()
        self.assertFalse(AuditLog.objects.filter(table_name='core_backupplan').exists())


@override_settings(SECURE_SSL_REDIRECT=False, **KONFIG)
class FeiltekstVaskesTests(TestCase):

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='adm_p3v', password='x', role='admin', must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.c = Client()
        self.c.force_login(self.admin)

    def test_backupfeil_viser_ikke_noklene(self):
        feil = RuntimeError(f'kunne ikke: postgres://u:pw@db/x {KONFIG["OFFSITE_S3_SECRET_KEY"]}x'
                            f' {KONFIG["OFFSITE_BACKUP_KEY"]}')
        with patch('core.backup.create_backup', side_effect=feil):
            svar = self.c.post('/portal-admin/backup/kjor/patients/', follow=True)
        tekst = ' '.join(str(m) for m in svar.context['messages'])
        self.assertIn('Feilet', tekst)
        self.assertNotIn(':pw@', tekst)
        self.assertNotIn(KONFIG['OFFSITE_BACKUP_KEY'], tekst)


class VerifiserProverHverModulTests(SimpleTestCase):
    """`verifiser_backup` hadde sin egen liste, uten `ko`, `park` og `backlog`."""

    def test_hver_modulfil_proves(self):
        from core.backup import all_handlers
        from core.management.commands.verifiser_backup import rekkefolge
        moduler = {h.slug for h in all_handlers()} - {'full'}
        self.assertEqual(set(rekkefolge()), moduler)
        self.assertEqual(rekkefolge()[0], 'portal', 'portalen bærer vakta og lastes først')
