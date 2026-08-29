"""Deploy 1 av vakt-scopingen: FK-en skrives, `year` leses.

Kontrakten disse testene låser er nettopp den `verifiser_vakt` kontrollerer i
prod: hver ny rad får en vakt, og vakta og `year` er aldri uenige. Deploy 2
gjør vakta til fasit — disse testene er grunnen til at den kan stole på den.
"""
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import Vakt
from patients.models import AppSetting, Patient, VaktArkiv
from patients.services import get_active_year, hent_aktiv_vakt, vakt_for_year

AAR = 2098


def _sett_aar(year=AAR):
    AppSetting.objects.update_or_create(
        key='active_year', defaults={'value': str(year)})


class HentAktivVaktTests(TestCase):
    def setUp(self):
        _sett_aar()

    def test_lat_opprettelse_paa_fersk_base(self):
        """En fersk installasjon skal ikke trenge et oppsettsteg."""
        self.assertEqual(Vakt.objects.count(), 0)
        vakt = hent_aktiv_vakt()
        self.assertEqual(vakt.year, AAR)
        self.assertEqual(vakt.navn, str(AAR))
        self.assertTrue(vakt.er_aktiv)
        self.assertEqual(AppSetting.get('aktiv_vakt_id'), str(vakt.pk))

    def test_pekeren_er_fasit_naar_den_finnes(self):
        vakt = Vakt.objects.create(
            navn='Landsskytterstevnet', year=AAR, startet=timezone.now())
        AppSetting.set('aktiv_vakt_id', vakt.pk)
        self.assertEqual(hent_aktiv_vakt().pk, vakt.pk)
        self.assertEqual(Vakt.objects.count(), 1)

    def test_doed_peker_repareres(self):
        """En rollback som tok vaktene skal ikke stoppe registrering."""
        AppSetting.set('aktiv_vakt_id', 99999)
        vakt = hent_aktiv_vakt()
        self.assertEqual(vakt.year, AAR)
        self.assertEqual(AppSetting.get('aktiv_vakt_id'), str(vakt.pk))

    def test_to_kall_gir_samme_vakt(self):
        self.assertEqual(hent_aktiv_vakt().pk, hent_aktiv_vakt().pk)
        self.assertEqual(Vakt.objects.count(), 1)

    def test_vakt_for_year_gjenbruker_eksisterende(self):
        vakt = Vakt.objects.create(
            navn='LS97', year=2097, startet=timezone.now())
        self.assertEqual(vakt_for_year(2097).pk, vakt.pk)
        self.assertEqual(vakt_for_year(2096).navn, '2096')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SkrivestierTests(TestCase):
    """Hver sti som lager rader skal sette vakta. Glemmes én, sier
    `verifiser_vakt` fra i prod — men helst skal den aldri få sjansen."""

    def setUp(self):
        _sett_aar()
        self.bruker = CustomUser.objects.create_user(
            username='skriver', password='x', must_change_password=False)
        ModulTilgang.objects.create(
            bruker=self.bruker, modul_slug='patients', nivaa='skriv_full')
        ModulTilgang.objects.create(
            bruker=self.bruker, modul_slug='oppdrag', nivaa='skriv_full')
        self.client = Client()
        self.client.force_login(self.bruker)

    def test_ny_pasient_faar_aktiv_vakt(self):
        resp = self.client.post(
            '/pasienter/api/patients/', content_type='application/json',
            data={'problemstilling': 'Pustevansker'})
        self.assertEqual(resp.status_code, 201)
        pasient = Patient.objects.get()
        self.assertIsNotNone(pasient.vakt)
        self.assertEqual(pasient.vakt.year, pasient.year)

    def test_nytt_oppdrag_faar_aktiv_vakt(self):
        from oppdrag.models import Enhet, Lokasjon, Oppdrag
        enhet = Enhet.objects.create(navn='Haugesund 56')
        lokasjon = Lokasjon.objects.create(navn='Scene')
        resp = self.client.post(
            '/oppdrag/api/oppdrag/', content_type='application/json',
            data={'enhet_id': enhet.pk, 'lokasjon_id': lokasjon.pk,
                  'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt'})
        self.assertEqual(resp.status_code, 200)
        oppdrag = Oppdrag.objects.get()
        self.assertIsNotNone(oppdrag.vakt)
        self.assertEqual(oppdrag.vakt.year, oppdrag.year)

    def test_pasient_og_oppdrag_deler_vakt(self):
        """Én vakt, to moduler — det er hele poenget med scopet."""
        self.test_ny_pasient_faar_aktiv_vakt()
        self.test_nytt_oppdrag_faar_aktiv_vakt()
        from oppdrag.models import Oppdrag
        self.assertEqual(Patient.objects.get().vakt_id,
                         Oppdrag.objects.get().vakt_id)
        self.assertEqual(Vakt.objects.count(), 1)

    def test_arkivering_setter_vakt(self):
        from patients.services import arkiver_aktiv_vakt
        Patient.objects.create(pasientnummer=1, year=AAR,
                               vakt=hent_aktiv_vakt())
        arkiv, antall = arkiver_aktiv_vakt('LS98', '', self.bruker)
        self.assertEqual(arkiv.vakt_id, hent_aktiv_vakt().pk)


class VerifiserVaktTests(TestCase):
    """Kommandoen som står mellom deploy 1 og 2."""

    def setUp(self):
        _sett_aar()

    def _kjor(self):
        ut = StringIO()
        try:
            call_command('verifiser_vakt', stdout=ut, stderr=ut)
            kode = 0
        except SystemExit as e:
            kode = e.code
        return kode, ut.getvalue()

    def test_groenn_paa_ren_base(self):
        kode, ut = self._kjor()
        self.assertEqual(kode, 0)
        self.assertIn('Ingen funn', ut)

    def test_groenn_naar_alt_er_koblet(self):
        Patient.objects.create(pasientnummer=1, year=AAR,
                               vakt=hent_aktiv_vakt())
        kode, ut = self._kjor()
        self.assertEqual(kode, 0)

    def test_roed_paa_pasient_uten_vakt(self):
        Patient.objects.create(pasientnummer=1, year=AAR)
        kode, ut = self._kjor()
        self.assertEqual(kode, 1)
        self.assertIn('uten vakt', ut)

    def test_roed_naar_year_og_vakt_er_uenige(self):
        """Selve kontrakten: en skrivesti som glemmer vakta skal bli sett."""
        feil_vakt = Vakt.objects.create(
            navn='2097', year=2097, startet=timezone.now())
        Patient.objects.create(pasientnummer=1, year=AAR, vakt=feil_vakt)
        kode, ut = self._kjor()
        self.assertEqual(kode, 1)
        self.assertIn('ikke stemmer med', ut)

    def test_arkiv_uten_vakt_er_info_ikke_feil(self):
        """NULL på gamle arkiver betyr «fra før grupperingen» — i orden."""
        VaktArkiv.objects.create(
            tittel='LS96', arrangement_navn='LS96', importert_av_navn='a',
            antall_pasienter=0, year_snapshot=2096, sha256='x')
        kode, ut = self._kjor()
        self.assertEqual(kode, 0)
        self.assertIn('fra før grupperingen', ut)

    def test_roed_paa_doed_aktiv_peker(self):
        AppSetting.set('aktiv_vakt_id', 99999)
        kode, ut = self._kjor()
        self.assertEqual(kode, 1)
        self.assertIn('finnes', ut)

    def test_roed_paa_nummerkollisjon_i_vakta(self):
        """Forhåndssjekken for deploy 2-sperren (vakt, oppdragsnummer)."""
        from oppdrag.models import Enhet, Lokasjon, Oppdrag
        enhet = Enhet.objects.create(navn='H56')
        lokasjon = Lokasjon.objects.create(navn='Scene')
        vakt = hent_aktiv_vakt()
        for year in (2097, AAR):
            Oppdrag.objects.create(
                year=year, oppdragsnummer=1, enhet=enhet,
                problemstilling='Transport', hastegrad='Vanlig',
                lokasjon=lokasjon, vakt=vakt)
        kode, ut = self._kjor()
        self.assertEqual(kode, 1)
        self.assertIn('kollisjon', ut)
