"""Offsite backup til Scaleway (13. sep. 2026) — kryptering, opplasting,
henting og at alt er inert uten konfigurasjon.

S3 mockes: `core.offsite._klient` byttes ut med en falsk klient som husker
hva den fikk. Krypteringen kjøres ekte.
"""
import gzip
import io
import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from core import offsite
from core.backup import KIND_AUTO, KIND_MANUAL, create_backup, get_backup_dir
from core.models import OffsiteKopi
from patients.models import Backup

KONFIG = dict(OFFSITE_S3_BUCKET='sanitet-backup', OFFSITE_S3_ACCESS_KEY='ak',
              OFFSITE_S3_SECRET_KEY='sk', OFFSITE_BACKUP_KEY='hemmelig-nøkkel-42')


class FalskS3:
    def __init__(self):
        self.objekter = {}
        self.feil = None

    def put_object(self, Bucket, Key, Body, ContentType=None, Metadata=None):
        if self.feil:
            raise self.feil
        self.objekter[Key] = {'Body': Body, 'Metadata': Metadata or {}, 'Bucket': Bucket}

    def get_object(self, Bucket, Key):
        if Key not in self.objekter:
            raise KeyError(Key)
        o = self.objekter[Key]
        return {'Body': io.BytesIO(o['Body']), 'Metadata': o['Metadata']}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        from datetime import datetime, timezone as tz
        return {'Contents': [{'Key': k, 'Size': len(o['Body']), 'LastModified': datetime(2026, 9, 13, tzinfo=tz.utc)}
                             for k, o in self.objekter.items() if k.startswith(Prefix)],
                'IsTruncated': False}


class KrypteringTests(SimpleTestCase):
    def test_rundtur_og_feil_nokkel(self):
        data = b'{"pasient": "Kari"}' * 50
        blob = offsite.krypter(data, 'n1')
        self.assertTrue(blob.startswith(offsite.MAGI))
        self.assertNotIn(b'Kari', blob)
        self.assertEqual(offsite.dekrypter(blob, 'n1'), data)
        with self.assertRaises(ValueError):
            offsite.dekrypter(blob, 'n2')
        with self.assertRaises(ValueError):
            offsite.dekrypter(blob[:-1] + bytes([blob[-1] ^ 1]), 'n1')
        with self.assertRaises(ValueError):
            offsite.dekrypter(b'ikke en backup', 'n1')

    def test_to_krypteringer_av_samme_data_er_ulike(self):
        """Nonce per fil — ellers kunne to like backuper sammenlignes utenfra."""
        self.assertNotEqual(offsite.krypter(b'x', 'n'), offsite.krypter(b'x', 'n'))

    def test_uten_nokkel(self):
        with self.assertRaises(ValueError):
            offsite.krypter(b'x', '')

    def test_slug_fra_filnavn(self):
        self.assertEqual(offsite._slug_fra_filnavn('backup-patients-auto-20260913-101500-123456.json.gz'), 'patients')
        self.assertEqual(offsite._slug_fra_filnavn('backup-oppdrag_arkiv-manual-20260913-101500-1.json.gz'), 'oppdrag_arkiv')


class _MedBackupDir(TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {'BACKUP_DIR': self._tmp.name})
        self._env.start()
        self.s3 = FalskS3()
        self._klient = patch('core.offsite._klient', return_value=self.s3)
        self._klient.start()

    def tearDown(self):
        self._klient.stop()
        self._env.stop()
        self._tmp.cleanup()


class InertUtenKonfigTests(_MedBackupDir):
    def test_ingen_opplasting_uten_variablene(self):
        self.assertFalse(offsite.er_konfigurert())
        self.assertEqual(set(offsite.mangler()), {'OFFSITE_S3_BUCKET', 'OFFSITE_S3_ACCESS_KEY',
                                                  'OFFSITE_S3_SECRET_KEY', 'OFFSITE_BACKUP_KEY'})
        create_backup('patients', KIND_MANUAL)
        self.assertEqual(OffsiteKopi.objects.count(), 0)
        self.assertEqual(self.s3.objekter, {})

    def test_kommandoen_sier_hva_som_mangler(self):
        with self.assertRaises(CommandError) as cm:
            call_command('hent_offsite', '--list', stdout=StringIO())
        self.assertIn('OFFSITE_BACKUP_KEY', str(cm.exception))


@override_settings(**KONFIG)
class OpplastingTests(_MedBackupDir):
    def test_ny_backup_lastes_opp_kryptert(self):
        backup = create_backup('patients', KIND_MANUAL)
        rad = OffsiteKopi.objects.get()
        self.assertEqual(rad.backup_filnavn, backup.filename)
        self.assertEqual(rad.objektnavn, f'backups/{backup.filename}.enc')
        self.assertEqual(rad.feil, '')
        self.assertIsNotNone(rad.sendt_at)
        o = self.s3.objekter[rad.objektnavn]
        self.assertEqual(o['Bucket'], 'sanitet-backup')
        self.assertEqual(o['Metadata']['modul'], 'patients')
        self.assertEqual(o['Metadata']['kind'], 'manual')
        self.assertTrue(o['Body'].startswith(offsite.MAGI))
        klartekst = offsite.dekrypter(o['Body'], KONFIG['OFFSITE_BACKUP_KEY'])
        self.assertEqual(klartekst, (get_backup_dir() / backup.filename).read_bytes())
        self.assertIn(b'"model"', gzip.decompress(klartekst))

    def test_hash_skip_gir_ingen_opplasting(self):
        create_backup('patients', KIND_AUTO)
        self.assertEqual(OffsiteKopi.objects.count(), 1)
        self.assertIsNone(create_backup('patients', KIND_AUTO), 'identisk innhold')
        self.assertEqual(OffsiteKopi.objects.count(), 1, 'ingen ny fil, ingen opplasting')

    def test_feil_i_bucketen_stopper_ikke_backupen(self):
        self.s3.feil = ConnectionError('bucket nede')
        backup = create_backup('patients', KIND_MANUAL)
        self.assertIsNotNone(backup, 'volumet er første nett')
        self.assertTrue((get_backup_dir() / backup.filename).exists())
        rad = OffsiteKopi.objects.get()
        self.assertIn('bucket nede', rad.feil)
        self.assertIsNone(rad.sendt_at)
        st = offsite.status()
        self.assertTrue(st['konfigurert'])
        self.assertEqual(st['antall'], 0)
        self.assertEqual(st['siste_feil'].pk, rad.pk)

    def test_status_og_oversikten(self):
        create_backup('patients', KIND_MANUAL)
        st = offsite.status()
        self.assertEqual((st['konfigurert'], st['antall'], st['siste_feil']), (True, 1, None))
        self.assertEqual(st['siste_ok'].module_slug, 'patients')
        from accounts.models import CustomUser
        from django.test import Client
        adm = CustomUser.objects.create_user(username='adm_off', password='x', role='admin',
                                             must_change_password=False)
        c = Client(); c.force_login(adm)
        with override_settings(SECURE_SSL_REDIRECT=False):
            html = c.get('/portal-admin/backup/').content.decode()
        self.assertIn('Offsite-kopi (Scaleway)', html)
        self.assertIn('sanitet-backup', html)
        self.assertIn('1 fil lastet opp', html)


@override_settings(**KONFIG)
class HentingTests(_MedBackupDir):
    def test_list_og_hent_legger_fila_der_restore_finner_den(self):
        backup = create_backup('patients', KIND_MANUAL)
        original = (get_backup_dir() / backup.filename).read_bytes()
        # Slett den lokale fila og raden — som om volumet er borte.
        (get_backup_dir() / backup.filename).unlink()
        Backup.objects.all().delete()

        ut = StringIO()
        call_command('hent_offsite', '--list', stdout=ut)
        self.assertIn(backup.filename, ut.getvalue())
        self.assertIn('1 objekt(er).', ut.getvalue())

        ut = StringIO()
        call_command('hent_offsite', backup.filename, stdout=ut)
        self.assertIn('Hentet og dekryptert', ut.getvalue())
        self.assertEqual((get_backup_dir() / backup.filename).read_bytes(), original)
        rad = Backup.objects.get(filename=backup.filename)
        self.assertEqual(rad.module_slug, 'patients')
        self.assertEqual(rad.kind, 'manual')
        self.assertIn('offsite', rad.note)

    def test_feil_nokkel_gir_lesbar_feil(self):
        backup = create_backup('patients', KIND_MANUAL)
        with override_settings(OFFSITE_BACKUP_KEY='feil'):
            with self.assertRaises(CommandError) as cm:
                call_command('hent_offsite', backup.filename, stdout=StringIO())
        self.assertIn('OFFSITE_BACKUP_KEY', str(cm.exception))

    def test_ukjent_objekt(self):
        with self.assertRaises(CommandError) as cm:
            call_command('hent_offsite', 'finnes-ikke.json.gz', stdout=StringIO())
        self.assertIn('Henting feilet', str(cm.exception))


# ─────────────────────────────────────────────────────────────────────────────
# Oppbevaringen i bucketen (livssyklusreglene)
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(OFFSITE_S3_BUCKET='sanitetsportalen',
                   OFFSITE_S3_ACCESS_KEY='a', OFFSITE_S3_SECRET_KEY='b',
                   OFFSITE_BACKUP_KEY='hemmelig')
class LivssyklusTests(SimpleTestCase):
    """Reglene leses fra bucketen, ikke fra det vi tror vi satte.

    Scaleway sletter offsite-kopiene; portalens IAM-nøkkel har ikke sletterett,
    og `enforce_cap` rører bare volumet. Livssyklusreglene er altså den eneste
    mekanismen som fjerner en offsite-kopi — og en regel som stille slutter å
    treffe, er en oppbevaringstid som stille blir uendelig.
    """

    def _med_regler(self, regler):
        class Klient:
            def get_bucket_lifecycle_configuration(self, **_):
                return {'Rules': regler}
        return patch('core.offsite._klient', return_value=Klient())

    def _les(self, regler):
        with self._med_regler(regler):
            return offsite.livssyklus(bruk_cache=False)

    @staticmethod
    def _regel(prefiks, dager, aktiv=True, id_='r'):
        return {'ID': id_, 'Status': 'Enabled' if aktiv else 'Disabled',
                'Filter': {'Prefix': prefiks}, 'Expiration': {'Days': dager}}

    def test_riktig_oppsett_gir_ingen_avvik(self) -> None:
        svar = self._les([self._regel('backups/', 730),
                          self._regel('full/', 90)])
        self.assertTrue(svar['kjent'])
        self.assertEqual(svar['avvik'], [])

    def test_prefiks_med_skraastrek_foran_treffer_ingenting(self) -> None:
        """Den stilleste feilen i hele oppsettet: `/full` ser riktig ut i
        konsollen, men objektnøklene heter `full/…`, så regelen sletter aldri
        noe."""
        svar = self._les([self._regel('backups/', 730),
                          self._regel('/full', 90)])
        self.assertEqual(len(svar['avvik']), 1)
        self.assertIn('«/full»', svar['avvik'][0])
        self.assertIn('nøyaktig', svar['avvik'][0])

    def test_manglende_regel_meldes(self) -> None:
        svar = self._les([self._regel('backups/', 730)])
        self.assertIn('full/', svar['avvik'][0])
        self.assertIn('for alltid', svar['avvik'][0])

    def test_feil_antall_dager_meldes(self) -> None:
        svar = self._les([self._regel('backups/', 730),
                          self._regel('full/', 730)])
        self.assertIn('730 dager', svar['avvik'][0])
        self.assertIn('skal være 90', svar['avvik'][0])

    def test_avslaatt_regel_meldes(self) -> None:
        svar = self._les([self._regel('backups/', 730),
                          self._regel('full/', 90, aktiv=False)])
        self.assertIn('slått av', svar['avvik'][0])

    def test_bucket_uten_regler_er_verre_enn_en_lesefeil(self) -> None:
        """Ingen regler betyr at ingenting noen gang slettes — en
        oppbevaringstid ingen har bestemt."""
        class Klient:
            def get_bucket_lifecycle_configuration(self, **_):
                feil = Exception('ingen regler')
                feil.response = {'Error': {'Code': 'NoSuchLifecycleConfiguration'}}
                raise feil

        with patch('core.offsite._klient', return_value=Klient()):
            svar = offsite.livssyklus(bruk_cache=False)
        self.assertTrue(svar['kjent'])
        self.assertEqual(len(svar['avvik']), 2)

    def test_manglende_leserett_sier_hva_som_mangler(self) -> None:
        class Klient:
            def get_bucket_lifecycle_configuration(self, **_):
                feil = Exception('nei')
                feil.response = {'Error': {'Code': 'AccessDenied'}}
                raise feil

        with patch('core.offsite._klient', return_value=Klient()):
            svar = offsite.livssyklus(bruk_cache=False)
        self.assertFalse(svar['kjent'])
        self.assertIn('ObjectStorageBucketsRead', svar['feil'])

    def test_kaster_aldri(self) -> None:
        """Et kort som selv gir feil er borte akkurat når man trenger det."""
        class Klient:
            def get_bucket_lifecycle_configuration(self, **_):
                raise RuntimeError('nettverket er nede')

        with patch('core.offsite._klient', return_value=Klient()):
            svar = offsite.livssyklus(bruk_cache=False)
        self.assertFalse(svar['kjent'])
        self.assertIn('nettverket er nede', svar['feil'])


class LivssyklusUtenKonfigTests(SimpleTestCase):
    def test_inert_uten_variablene(self) -> None:
        svar = offsite.livssyklus(bruk_cache=False)
        self.assertFalse(svar['kjent'])
        self.assertEqual(svar['regler'], [])
        self.assertEqual(svar['avvik'], [])


class PrefiksRutingTests(TestCase):
    """Hvilken mappe i bucketen en fil havner i — og dermed hvor lenge den lever.

    `prefiks_for()` sammenligner mot strengen `'full'` direkte, ikke mot
    `Backupplan.FULL_SLUG`, for å slippe å importere modeller inn i
    `offsite.py`. Avveiningen er grei, men den etterlater slugen skrevet to
    steder som må endres samtidig.

    **Og de to feiler ulikt.** Døper noen om den hele fila i modellen uten å
    røre `offsite.py`, går ingenting i stykker med det samme: filene lastes
    opp som før, bare til `backups/` i stedet for `full/`. Da lever hele
    databasen — med passordhasher og TOTP-hemmeligheter — i 730 dager i stedet
    for 90, og det er en personvernbeslutning som ble endret av en
    navneendring. Ingenting feiler, ingen logg sier fra, og kortet på
    backup-siden ser riktig ut: reglene *står* jo som de skal, det er filene
    som ligger feil sted.
    """

    def test_den_hele_fila_folger_konstanten(self) -> None:
        from core.models import Backupplan

        self.assertEqual(
            offsite.prefiks_for(Backupplan.FULL_SLUG), offsite.PREFIKS_FULL,
            'Slugen for hele databasen er endret ett sted og ikke det andre. '
            'Filene ville havnet under backups/ og fått 730 dagers '
            'oppbevaring i stedet for 90.')

    def test_alle_andre_moduler_gaar_til_backups(self) -> None:
        """Registeret er fasit, ikke en liste i denne testen — en ny modul
        skal ikke kunne legge seg under 90-dagersregelen ubemerket."""
        from core.backup import all_handlers, registrer_alle_moduler
        from core.models import Backupplan

        registrer_alle_moduler()
        slugger = [h.slug for h in all_handlers()]
        self.assertIn(Backupplan.FULL_SLUG, slugger, 'hel-handleren er ikke registrert')

        for slug in slugger:
            with self.subTest(slug=slug):
                forventet = (offsite.PREFIKS_FULL if slug == Backupplan.FULL_SLUG
                             else offsite.PREFIKS)
                self.assertEqual(offsite.prefiks_for(slug), forventet)

    def test_filnavnet_leser_tilbake_til_samme_prefiks(self) -> None:
        """Ett navn, to lesere, og de må bli enige.

        Opplastingen får slugen som argument; hentingen leser den ut av
        filnavnet (`hent_offsite <filnavn>`). Blir de uenige — en framtidig
        slug som forvirrer `slug_fra_filnavn` — lastes fila opp ett sted og
        letes etter et annet, og det oppdages den dagen man skal gjenopprette.
        """
        from core.backup import all_handlers, registrer_alle_moduler
        from core.backup.service import _build_filename, slug_fra_filnavn

        registrer_alle_moduler()
        for handler in all_handlers():
            for kind in (KIND_AUTO, KIND_MANUAL, 'pre_restore', 'pre_reset'):
                with self.subTest(slug=handler.slug, kind=kind):
                    filnavn = _build_filename(handler.slug, kind)
                    self.assertEqual(slug_fra_filnavn(filnavn), handler.slug)
                    self.assertTrue(
                        offsite.objektnavn(filnavn, handler.slug).startswith(
                            offsite.prefiks_for(slug_fra_filnavn(filnavn))))

    def test_de_to_prefiksene_utelukker_hverandre(self) -> None:
        """`backups/` skal ikke være et forstavelse av `full/` eller omvendt —
        da ville én livssyklusregel truffet begge, og fristene ikke latt seg
        skille."""
        self.assertFalse(offsite.PREFIKS_FULL.startswith(offsite.PREFIKS))
        self.assertFalse(offsite.PREFIKS.startswith(offsite.PREFIKS_FULL))
        self.assertEqual(set(offsite.FORVENTET_DAGER), set(offsite.ALLE_PREFIKS),
                         'en frist uten prefiks, eller et prefiks uten frist')
