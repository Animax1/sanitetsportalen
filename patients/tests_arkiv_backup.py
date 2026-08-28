"""Tester for arkivet som egen backup-modul (GDPR-tiltaksplan fase 3.2).

Bakgrunn: tidligere var `VaktArkiv` ekskludert fra pasient-backupen mens
`ArkivertPasient` ble tatt med — altså barna uten forelderen. Det ga to
problemer:

1. Var arkivet slettet etter at backupen ble tatt, feilet `loaddata` på
   fremmednøkkel og HELE gjenopprettingen av pasientdata rullet tilbake.
2. Arkivet kunne uansett ikke gjenopprettes fra pasient-backupen, siden
   forelderen manglet. Oppsettet ga altså null gjenopprettingsevne og
   bare nedside.

Arkivet har nå egen handler med begge modellene samlet, og pasient-backupen
rører dem ikke.

Kjør med: python manage.py test patients.tests_arkiv_backup
"""
import gzip
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.backup import (
    KIND_AUTO,
    KIND_MANUAL,
    create_backup,
    get_backup_dir,
    get_handler,
    restore_backup,
)
from patients.models import (
    AppSetting, ArkivertPasient, Patient, VaktArkiv,
)
from patients.services import arkiver_aktiv_vakt
from accounts.test_helpers import gi_standardtilgang

User = get_user_model()


def _dump_innhold(backup):
    """Les tilbake den lagrede fixturen som Python-objekter."""
    path = get_backup_dir() / backup.filename
    with gzip.open(path, 'rb') as f:
        return json.loads(f.read().decode('utf-8'))


def _modeller_i(backup):
    return {obj['model'] for obj in _dump_innhold(backup)}


class ArkivBackupTestMixin:

    def setUp(self):
        # Andre testmoduler nullstiller handler-registeret. Registrer på nytt
        # her, slik at disse testene ikke avhenger av kjørerekkefølgen.
        if get_handler('arkiv') is None or get_handler('patients') is None:
            from patients.backup import register_handlers
            register_handlers()

        AppSetting.set('active_year', 2098)
        AppSetting.set('next_patient_nr', 1)
        self.admin = User.objects.create_user(
            username='arkivar', password='passord', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin)

    def _lag_pasient(self, nr, triage='Grønn'):
        return Patient.objects.create(
            pasientnummer=nr, year=2098, grovsortering=triage,
            problemstilling='Kramper', is_active=True,
        )

    def _arkiver(self, navn='Testvakt'):
        return arkiver_aktiv_vakt(navn, '', self.admin)


@override_settings(SECURE_SSL_REDIRECT=False)
class ArkivHandlerRegistreringTests(ArkivBackupTestMixin, TestCase):

    def test_arkiv_handler_er_registrert(self):
        handler = get_handler('arkiv')
        self.assertIsNotNone(handler)
        self.assertEqual(handler.display_name, 'Vaktarkiv')

    def test_arkiv_handler_dekker_begge_modellene(self):
        handler = get_handler('arkiv')
        self.assertEqual(
            set(handler.collect_apps()),
            {'patients.VaktArkiv', 'patients.ArkivertPasient'},
        )

    def test_restore_rekkefolge_er_fk_trygg(self):
        """Barn må slettes før forelder."""
        rekkefolge = get_handler('arkiv').get_restore_models()
        self.assertLess(
            rekkefolge.index('patients.ArkivertPasient'),
            rekkefolge.index('patients.VaktArkiv'),
        )

    def test_patients_handler_ekskluderer_arkivmodellene(self):
        exclude = get_handler('patients').collect_exclude()
        self.assertIn('patients.VaktArkiv', exclude)
        self.assertIn('patients.ArkivertPasient', exclude)


@override_settings(SECURE_SSL_REDIRECT=False)
class ArkivBackupInnholdTests(ArkivBackupTestMixin, TestCase):

    def test_arkiv_backup_inneholder_begge_modellene(self):
        self._lag_pasient(1)
        self._arkiver()

        backup = create_backup(slug='arkiv', kind=KIND_MANUAL)
        modeller = _modeller_i(backup)

        self.assertIn('patients.vaktarkiv', modeller)
        self.assertIn('patients.arkivertpasient', modeller)

    def test_pasient_backup_inneholder_ikke_arkiv(self):
        self._lag_pasient(1)
        self._arkiver()

        backup = create_backup(slug='patients', kind=KIND_MANUAL)
        modeller = _modeller_i(backup)

        self.assertNotIn('patients.vaktarkiv', modeller)
        self.assertNotIn(
            'patients.arkivertpasient', modeller,
            'ArkivertPasient skal ikke lenger følge med pasient-backupen',
        )
        self.assertIn('patients.patient', modeller)

    def test_importert_av_fjernes_fra_dumpen(self):
        """FK-en til CustomUser ville gjort backupen ugjenopprettelig."""
        self._lag_pasient(1)
        self._arkiver()

        backup = create_backup(slug='arkiv', kind=KIND_MANUAL)
        arkiv_objekter = [
            o for o in _dump_innhold(backup)
            if o['model'] == 'patients.vaktarkiv'
        ]

        self.assertEqual(len(arkiv_objekter), 1)
        self.assertNotIn('importert_av', arkiv_objekter[0]['fields'])
        self.assertEqual(
            arkiv_objekter[0]['fields']['importert_av_navn'], 'arkivar',
            'Det frosne navnet skal beholdes',
        )

    def test_strip_fields_paavirker_ikke_pasient_backup(self):
        """Kun arkiv-handleren har strip_fields."""
        self.assertEqual(get_handler('patients').get_strip_fields(), {})


@override_settings(SECURE_SSL_REDIRECT=False)
class ArkivRestoreTests(ArkivBackupTestMixin, TestCase):

    def test_slettet_arkiv_kan_gjenopprettes(self):
        self._lag_pasient(1)
        self._lag_pasient(2, 'Rød')
        arkiv, antall = self._arkiver('Festivalen')
        backup = create_backup(slug='arkiv', kind=KIND_MANUAL)

        arkiv.delete()
        self.assertEqual(VaktArkiv.objects.count(), 0)
        self.assertEqual(ArkivertPasient.objects.count(), 0)

        restore_backup(backup)

        self.assertEqual(VaktArkiv.objects.count(), 1)
        self.assertEqual(ArkivertPasient.objects.count(), antall)
        self.assertEqual(VaktArkiv.objects.first().arrangement_navn, 'Festivalen')

    def test_restore_virker_etter_at_brukeren_er_slettet(self):
        """Hovedscenarioet: kontoen som arkiverte vakten finnes ikke lenger.

        Med FK-en igjen i dumpen feilet dette med DeserializationError.
        """
        self._lag_pasient(1)
        arkiv, _ = self._arkiver()
        backup = create_backup(slug='arkiv', kind=KIND_MANUAL)

        self.admin.delete()
        arkiv.delete()

        restore_backup(backup)

        gjenopprettet = VaktArkiv.objects.get()
        self.assertIsNone(gjenopprettet.importert_av)
        self.assertEqual(gjenopprettet.importert_av_navn, 'arkivar')
        self.assertEqual(gjenopprettet.importert_av_visning, 'arkivar')

    def test_pasient_restore_rorer_ikke_arkivet(self):
        """Den opprinnelige feilen: arkivet blokkerte pasient-restore.

        Backup av pasientdata tas mens et arkiv finnes. Arkivet slettes.
        Restoren skal fortsatt gå gjennom.
        """
        self._lag_pasient(1)
        arkiv, _ = self._arkiver()

        pasient_backup = create_backup(slug='patients', kind=KIND_MANUAL)

        arkiv_pk = arkiv.pk
        arkiv.delete()

        restore_backup(pasient_backup)  # feilet tidligere på fremmednøkkel

        self.assertEqual(Patient.objects.count(), 1)
        self.assertFalse(
            VaktArkiv.objects.filter(pk=arkiv_pk).exists(),
            'Pasient-restore skal ikke gjenopprette et slettet arkiv',
        )

    def test_arkiv_restore_rorer_ikke_pasientdata(self):
        self._lag_pasient(1)
        self._arkiver()
        arkiv_backup = create_backup(slug='arkiv', kind=KIND_MANUAL)

        self._lag_pasient(2, 'Rød')
        self.assertEqual(Patient.objects.count(), 2)

        restore_backup(arkiv_backup)

        self.assertEqual(
            Patient.objects.count(), 2,
            'Arkiv-restore skal ikke berøre aktiv pasientdata',
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class ArkivHashSkipTests(ArkivBackupTestMixin, TestCase):

    def test_identisk_auto_backup_hoppes_over(self):
        self._lag_pasient(1)
        self._arkiver()

        self.assertIsNotNone(create_backup(slug='arkiv', kind=KIND_AUTO))
        self.assertIsNone(
            create_backup(slug='arkiv', kind=KIND_AUTO),
            'Uendret arkiv skal ikke gi ny auto-backup',
        )

    def test_nytt_arkiv_gir_ny_auto_backup(self):
        self._lag_pasient(1)
        self._arkiver('Vakt 1')
        create_backup(slug='arkiv', kind=KIND_AUTO)

        self._lag_pasient(2, 'Gul')
        self._arkiver('Vakt 2')

        self.assertIsNotNone(
            create_backup(slug='arkiv', kind=KIND_AUTO),
            'Nytt arkiv skal gi ny auto-backup',
        )
