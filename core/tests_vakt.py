"""Vakt-scopingen etter deploy 2: vakta er fasit.

Skrevet for deploy 1 (FK-en skrives, `year` leses) og omskrevet da deploy 2
fjernet `year` fra radene. Testene som sammenlignet de to kildene er borte
med grunnlaget sitt — det som står igjen er det som fortsatt kan være galt:
skrivestiene, pekeren, og arkivets frosne år mot vaktas.
"""
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from core.models import Vakt
from core.validators import current_local_year
from patients.models import AppSetting, Patient, VaktArkiv
from patients.services import hent_aktiv_vakt, vakt_for_year
from patients.test_helpers import sett_aktiv_vakt

AAR = 2098


class HentAktivVaktTests(TestCase):
    def test_lat_opprettelse_paa_fersk_base(self):
        """En fersk installasjon skal ikke trenge et oppsettsteg.

        Uten peker og uten vakter faller `hent_aktiv_vakt` tilbake til
        inneværende år — `active_year`-nøkkelen den falt tilbake til før
        deploy 2 finnes ikke lenger.
        """
        self.assertEqual(Vakt.objects.count(), 0)
        vakt = hent_aktiv_vakt()
        self.assertEqual(vakt.year, current_local_year())
        self.assertEqual(vakt.navn, str(current_local_year()))
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
        self.assertEqual(vakt.year, current_local_year())
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
        sett_aktiv_vakt(AAR)
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
        self.assertEqual(pasient.vakt_id, hent_aktiv_vakt().pk)

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
        self.assertEqual(oppdrag.vakt_id, hent_aktiv_vakt().pk)

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
        Patient.objects.create(pasientnummer=1, vakt=hent_aktiv_vakt())
        arkiv, antall = arkiver_aktiv_vakt('LS98', '', self.bruker)
        self.assertEqual(arkiv.vakt_id, hent_aktiv_vakt().pk)
        self.assertEqual(arkiv.year_snapshot, hent_aktiv_vakt().year)


class VerifiserVaktTests(TestCase):
    """Kommandoen som sto mellom deploy 1 og 2 — og fortsatt vokter arkivet."""

    def setUp(self):
        sett_aktiv_vakt(AAR)

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
        # Testene som sammenlignet `year` på raden mot vaktas år er fjernet
        # med deploy 2 — grunnlaget (year-kolonnen) finnes ikke, og en test
        # som ikke kan feile er verre enn ingen.
        Patient.objects.create(pasientnummer=1, vakt=hent_aktiv_vakt())
        kode, ut = self._kjor()
        self.assertEqual(kode, 0)

    def test_roed_naar_arkivets_aar_ikke_stemmer(self):
        """Arkivets frosne år mot vaktas — eneste year-sammenligning igjen."""
        VaktArkiv.objects.create(
            tittel='LS', arrangement_navn='LS', importert_av_navn='a',
            antall_pasienter=0, year_snapshot=2050,
            vakt=hent_aktiv_vakt(), sha256='x')
        kode, ut = self._kjor()
        self.assertEqual(kode, 1)
        self.assertIn('year_snapshot', ut)

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

    def test_nummerkollisjon_stoppes_av_skjemaet(self):
        """Kollisjonssjekken i kommandoen er fjernet — sperren bor i basen nå.

        Testen står igjen som beviset på at fjerningen var trygg: databasen
        nekter selv, så en kommando-sjekk kunne aldri funnet noe.
        """
        from django.db import IntegrityError, transaction

        from oppdrag.models import Enhet, Lokasjon, Oppdrag
        enhet = Enhet.objects.create(navn='H56')
        lokasjon = Lokasjon.objects.create(navn='Scene')
        vakt = hent_aktiv_vakt()
        Oppdrag.objects.create(
            vakt=vakt, oppdragsnummer=1, enhet=enhet,
            problemstilling='Transport', hastegrad='Vanlig', lokasjon=lokasjon)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Oppdrag.objects.create(
                    vakt=vakt, oppdragsnummer=1, enhet=enhet,
                    problemstilling='Transport', hastegrad='Vanlig',
                    lokasjon=lokasjon)
