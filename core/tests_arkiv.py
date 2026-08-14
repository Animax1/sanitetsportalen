"""Tester for det modul-agnostiske arkivmønsteret i ``core.arkiv``.

Testene bruker en dummy-handler, ikke pasientmodulens, slik at de dekker det
generiske laget for seg. Pasientmodulens egen bruk — og at signaturene er
uendret etter flyttingen — dekkes av ``patients/tests_arkiv.py``, særlig
``ArkivSignaturLaastTests``.

``VaktArkiv`` brukes som lagringsmodell fordi den er den eneste arkivmodellen
som finnes i dag. En egen testmodell ville krevd migrasjoner.
"""
from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from core.arkiv import (
    BaseArkivHandler,
    beregn_aggregat_sha256,
    beregn_sha256,
    get_handler,
    har_backup_etter,
    kollaps,
    register,
    verifiser,
)
from core.arkiv.handlers import _Registry
from patients.models import ArkivertPasient, Backup, VaktArkiv


class DummyHandler(BaseArkivHandler):
    """Minimal handler. Teller kall, slik at orkestreringen kan verifiseres."""

    slug = 'dummy'
    display_name = 'Dummy'
    backup_slug = 'arkiv'

    def __init__(self):
        self.aggregat_kall = 0
        self.slett_kall = 0

    def sha_payload(self, arkiv, rader):
        return {'id': arkiv.pk, 'rader': sorted(rader, key=lambda r: r['nr'])}

    def aggregat_sha_payload(self, arkiv, aggregat):
        return {'id': arkiv.pk, 'aggregat': aggregat}

    def rad_dicts(self, arkiv):
        return [
            {'nr': p.pasientnummer, 'problem': p.problemstilling}
            for p in ArkivertPasient.objects.filter(arkiv=arkiv)
        ]

    def bygg_aggregat(self, arkiv):
        self.aggregat_kall += 1
        return {'antall': ArkivertPasient.objects.filter(arkiv=arkiv).count()}

    def slett_rader(self, arkiv):
        self.slett_kall += 1
        return ArkivertPasient.objects.filter(arkiv=arkiv).delete()[0]


class RegistryTests(TestCase):
    """Registryet, testet isolert fra den globale instansen."""

    def test_register_og_hent(self):
        reg = _Registry()
        h = DummyHandler()
        reg.register(h)
        self.assertIs(reg.get('dummy'), h)
        self.assertEqual(reg.all(), [h])

    def test_ukjent_slug_gir_none(self):
        self.assertIsNone(_Registry().get('finnes-ikke'))

    def test_handler_uten_slug_avvises(self):
        class UtenSlug(BaseArkivHandler):
            pass

        with self.assertRaises(ValueError) as ctx:
            _Registry().register(UtenSlug())
        self.assertIn('slug', str(ctx.exception))

    def test_registrering_er_idempotent(self):
        """apps.ready() kan kjøre flere ganger under testing."""
        reg = _Registry()
        reg.register(DummyHandler())
        reg.register(DummyHandler())
        self.assertEqual(len(reg.all()), 1)

    def test_pasientmodulen_er_registrert(self):
        """Selve koblingen — registreres fra patients.apps.ready()."""
        handler = get_handler('patients')
        self.assertIsNotNone(handler, 'patients-handleren mangler i registryet')
        self.assertEqual(handler.backup_slug, 'arkiv')
        self.assertEqual(handler.retention_dager, 730)


class ArkivTjenesteTests(TestCase):
    """Signatur, verifikasjon og kollaps på det generiske laget."""

    def setUp(self):
        self.handler = DummyHandler()
        self.admin = CustomUser.objects.create_user(
            username='arkivadmin', password='pwd', role='admin',
            must_change_password=False,
        )
        self.arkiv = VaktArkiv.objects.create(
            tittel='Dummy-arkiv', arrangement_navn='Test',
            antall_pasienter=2, year_snapshot=2026,
        )
        for nr in (2, 1):
            ArkivertPasient.objects.create(
                arkiv=self.arkiv, pasientnummer=nr, problemstilling='Kramper')

    # ── Signatur ─────────────────────────────────────────────────────────

    def test_signaturen_er_stabil(self):
        self.assertEqual(
            beregn_sha256(self.handler, self.arkiv),
            beregn_sha256(self.handler, self.arkiv))

    def test_signaturen_endrer_seg_naar_data_endres(self):
        foer = beregn_sha256(self.handler, self.arkiv)
        rad = ArkivertPasient.objects.filter(arkiv=self.arkiv).first()
        rad.problemstilling = 'Brystsmerter'
        rad.save(update_fields=['problemstilling'])
        self.assertNotEqual(beregn_sha256(self.handler, self.arkiv), foer)

    # ── Verifikasjon ─────────────────────────────────────────────────────

    def test_uten_lagret_signatur_meldes_ikke_tukling(self):
        """Arkiver fra før signaturen ble innført skal ikke slå ut."""
        self.arkiv.sha256 = ''
        self.assertFalse(verifiser(self.handler, self.arkiv))

    def test_gyldig_signatur_gir_ingen_tukling(self):
        self.arkiv.sha256 = beregn_sha256(self.handler, self.arkiv)
        self.assertFalse(verifiser(self.handler, self.arkiv))

    def test_endret_rad_meldes_som_tukling(self):
        self.arkiv.sha256 = beregn_sha256(self.handler, self.arkiv)
        rad = ArkivertPasient.objects.filter(arkiv=self.arkiv).first()
        rad.problemstilling = 'Tuklet'
        rad.save(update_fields=['problemstilling'])
        self.assertTrue(verifiser(self.handler, self.arkiv))

    def test_etter_kollaps_sjekkes_aggregatet(self):
        """Radsignaturen kan aldri verifiseres igjen — radene finnes ikke."""
        self.arkiv.sha256 = beregn_sha256(self.handler, self.arkiv)
        self.arkiv.save(update_fields=['sha256'])
        kollaps(self.handler, self.arkiv)

        self.assertTrue(self.arkiv.er_kollapset)
        self.assertFalse(verifiser(self.handler, self.arkiv))

        # Tukling med det frosne aggregatet skal fanges
        self.arkiv.aggregat = {'antall': 999}
        self.assertTrue(verifiser(self.handler, self.arkiv))

    # ── Kollaps ──────────────────────────────────────────────────────────

    def test_kollaps_sletter_rader_og_fryser_aggregat(self):
        antall = kollaps(self.handler, self.arkiv)

        self.assertEqual(antall, 2)
        self.assertEqual(ArkivertPasient.objects.filter(arkiv=self.arkiv).count(), 0)
        self.assertEqual(self.arkiv.aggregat, {'antall': 2})
        self.assertTrue(self.arkiv.aggregat_sha256)
        self.assertIsNotNone(self.arkiv.kollapset_at)

        self.arkiv.refresh_from_db()
        self.assertEqual(self.arkiv.aggregat, {'antall': 2})

    def test_kollaps_er_idempotent(self):
        kollaps(self.handler, self.arkiv)
        self.assertEqual(kollaps(self.handler, self.arkiv), 0)
        self.assertEqual(self.handler.slett_kall, 1,
                         'slett_rader() skal ikke kalles på nytt')

    def test_aggregatet_beregnes_foer_slettingen(self):
        """Rekkefølgen er poenget: går beregningen galt, er ingenting slettet.

        Aggregatet inneholder 2, altså er det beregnet mens radene fortsatt
        fantes. Ble det beregnet etterpå, ville tallet vært 0.
        """
        kollaps(self.handler, self.arkiv)
        self.assertEqual(self.arkiv.aggregat['antall'], 2)
        self.assertEqual(self.handler.aggregat_kall, 1)

    def test_aggregatsignaturen_daekker_aggregatet(self):
        kollaps(self.handler, self.arkiv)
        self.assertEqual(
            self.arkiv.aggregat_sha256,
            beregn_aggregat_sha256(self.handler, self.arkiv, self.arkiv.aggregat))

    # ── Backup-sperre ────────────────────────────────────────────────────

    def test_ingen_backup_gir_false(self):
        self.assertFalse(har_backup_etter(self.handler, timezone.now()))

    def test_backup_etter_tidspunktet_gir_true(self):
        Backup.objects.create(
            module_slug='arkiv', filename='b.json.gz', size_bytes=1, kind='manual')
        self.assertTrue(
            har_backup_etter(self.handler, timezone.now() - timezone.timedelta(hours=1)))

    def test_backup_fra_annen_modul_teller_ikke(self):
        Backup.objects.create(
            module_slug='patients', filename='b.json.gz', size_bytes=1, kind='manual')
        self.assertFalse(
            har_backup_etter(self.handler, timezone.now() - timezone.timedelta(hours=1)))

    def test_handler_uten_backup_slug_gir_false(self):
        """Ingen sperre betyr at kollaps må tvinges bevisst, ikke at den er fri."""
        class UtenBackup(DummyHandler):
            slug = 'uten-backup'
            backup_slug = ''

        self.assertFalse(
            har_backup_etter(UtenBackup(),
                             timezone.now() - timezone.timedelta(hours=1)))
