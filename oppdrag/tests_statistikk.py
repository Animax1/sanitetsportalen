"""Oppdragstallene (fase 6).

Det som testes er reglene tallene hviler på, ikke at aggregering fungerer:

- varigheter regnes fra **gjeldende** statusmeldinger, så en korreksjon slår
  gjennom og originalen teller ikke
- en varighet som slutter i en **automatisk** stempling telles ikke (§12.2),
  mens oppdraget fortsatt telles i antall og fordelinger
- en **negativ** varighet telles ikke, og begge utelatelsene rapporteres
- scopet er vakta: forrige vakts oppdrag skal ikke blande seg inn
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from patients.services import vakt_for_year
from patients.test_helpers import sett_aktiv_vakt

from oppdrag import choices, services
from oppdrag.models import Enhet, Lokasjon, Oppdrag, Statusmelding
from oppdrag.statistikk import oppdrag_stats

AAR = 2098


class OppdragStatsBasis(TestCase):
    def setUp(self):
        self.vakt = sett_aktiv_vakt(AAR)
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        self.enhet = Enhet.objects.create(navn='Haugesund 56', pa_vakt=True)
        self.bruker = CustomUser.objects.create_user(
            username='sentral', password='x', must_change_password=False)
        self.naa = timezone.now()

    def _oppdrag(self, *, vakt=None, hastegrad='Akutt',
                 problemstilling='Pustevansker', enhet=None, minutter_siden=60):
        vakt = vakt or self.vakt
        oppdrag = Oppdrag.objects.create(
            vakt=vakt,
            oppdragsnummer=services.neste_oppdragsnummer(vakt),
            enhet=enhet or self.enhet,
            problemstilling=problemstilling,
            hastegrad=hastegrad,
            lokasjon=self.lokasjon,
        )
        # `created_at` settes av auto_now_add — statistikken regner fra den,
        # så testene må kunne plassere oppdraget i tid.
        opprettet = self.naa - timedelta(minutes=minutter_siden)
        Oppdrag.objects.filter(pk=oppdrag.pk).update(created_at=opprettet)
        oppdrag.refresh_from_db()
        return oppdrag

    def _stempel(self, oppdrag, status, minutter_etter_opprettelse,
                 *, automatisk=False):
        return services.sett_status(
            oppdrag, status, bruker=self.bruker,
            tidspunkt=oppdrag.created_at + timedelta(
                minutes=minutter_etter_opprettelse),
            automatisk=automatisk,
        )


class VarighetTests(OppdragStatsBasis):
    def test_responstid_regnes_fra_opprettelse_til_fremme(self):
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 3)
        self._stempel(oppdrag, choices.FREMME, 11)

        sum_ = oppdrag_stats(self.vakt)['summary']
        self.assertEqual(sum_['responstid']['n'], 1)
        self.assertEqual(sum_['responstid']['median'], 11.0)
        self.assertEqual(sum_['ventetid']['median'], 3.0)
        self.assertEqual(sum_['utrykningstid']['median'], 8.0)

    def test_hele_kjeden_gir_alle_tidsledd(self):
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 2)
        self._stempel(oppdrag, choices.FREMME, 10)
        self._stempel(oppdrag, choices.AVREIST, 25)
        self._stempel(oppdrag, choices.LEVERER, 35)
        self._stempel(oppdrag, choices.LEDIG, 40)

        sum_ = oppdrag_stats(self.vakt)['summary']
        self.assertEqual(sum_['tid_pa_stedet']['median'], 15.0)
        self.assertEqual(sum_['oppdragstid']['median'], 40.0)
        self.assertEqual(sum_['fullforte'], 1)
        self.assertEqual(sum_['aktive'], 0)

    def test_uferdig_oppdrag_teller_i_antall_men_ikke_i_tid(self):
        self._oppdrag()
        data = oppdrag_stats(self.vakt)
        self.assertEqual(data['summary']['total'], 1)
        self.assertEqual(data['summary']['aktive'], 1)
        self.assertEqual(data['summary']['responstid']['n'], 0)
        self.assertIsNone(data['summary']['responstid']['median'])

    def test_korreksjon_er_det_som_teller(self):
        """Regelen bor i `gjeldende()` — statistikken må lese den samme."""
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 2)
        original = self._stempel(oppdrag, choices.FREMME, 30)

        services.korriger_tidspunkt(
            original, oppdrag.created_at + timedelta(minutes=9),
            bruker=self.bruker)

        sum_ = oppdrag_stats(self.vakt)['summary']
        self.assertEqual(sum_['responstid']['median'], 9.0)


class AutomatiskTests(OppdragStatsBasis):
    """§12.2, besluttet 29. aug. 2026: avledet sluttid telles ikke."""

    def test_automatisk_ledig_teller_ikke_som_oppdragstid(self):
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 2)
        self._stempel(oppdrag, choices.FREMME, 10)
        self._stempel(oppdrag, choices.LEDIG, 40, automatisk=True)

        data = oppdrag_stats(self.vakt)
        sum_ = data['summary']
        self.assertEqual(sum_['oppdragstid']['n'], 0)
        self.assertEqual(sum_['utelatt']['automatisk'], 1)

    def test_oppdraget_telles_fortsatt_i_antall_og_fordelinger(self):
        """Det er varigheten som mangler måling, ikke oppdraget."""
        oppdrag = self._oppdrag(hastegrad='Haster')
        self._stempel(oppdrag, choices.LEDIG, 12, automatisk=True)

        data = oppdrag_stats(self.vakt)
        self.assertEqual(data['summary']['total'], 1)
        self.assertEqual(data['summary']['fullforte'], 1)
        self.assertEqual(data['per_hastegrad']['Haster'], 1)
        self.assertEqual(data['per_enhet']['Haugesund 56'], 1)

    def test_maalte_ledd_paa_samme_oppdrag_teller_som_vanlig(self):
        """Responstiden ble målt selv om sluttiden ble avledet."""
        oppdrag = self._oppdrag()
        self._stempel(oppdrag, choices.RYKKER_UT, 2)
        self._stempel(oppdrag, choices.FREMME, 7)
        self._stempel(oppdrag, choices.LEDIG, 55, automatisk=True)

        sum_ = oppdrag_stats(self.vakt)['summary']
        self.assertEqual(sum_['responstid']['median'], 7.0)
        self.assertEqual(sum_['utrykningstid']['median'], 5.0)
        self.assertEqual(sum_['oppdragstid']['n'], 0)

    def test_start_oppdrag_lukker_forrige_og_utelater_varigheten(self):
        """Hele mekanismen, ikke bare flagget: to oppdrag på én enhet."""
        forrige = self._oppdrag(minutter_siden=90)
        self._stempel(forrige, choices.RYKKER_UT, 2)
        self._stempel(forrige, choices.FREMME, 8)

        neste = self._oppdrag(minutter_siden=30)
        services.start_oppdrag(neste, bruker=self.bruker, tidspunkt=self.naa)

        data = oppdrag_stats(self.vakt)
        self.assertEqual(data['summary']['total'], 2)
        # Det forrige oppdraget ble lukket automatisk — oppdragstiden er
        # avledet og telles ikke, men responstiden ble målt.
        self.assertEqual(data['summary']['oppdragstid']['n'], 0)
        self.assertEqual(data['summary']['responstid']['n'], 1)
        self.assertEqual(data['summary']['utelatt']['automatisk'], 1)


class NegativVarighetTests(OppdragStatsBasis):
    def test_omvendt_rekkefolge_telles_ikke(self):
        """En klokke som går feil offline skal ikke dra medianen.

        Korreksjoner kan ikke lage dette — rekkefølgen håndheves der — men
        en enhet uten dekning sender klienttid.
        """
        oppdrag = self._oppdrag()
        Statusmelding.objects.create(
            oppdrag=oppdrag, status=choices.RYKKER_UT,
            tidspunkt=oppdrag.created_at + timedelta(minutes=20))
        Statusmelding.objects.create(
            oppdrag=oppdrag, status=choices.FREMME,
            tidspunkt=oppdrag.created_at + timedelta(minutes=5))

        data = oppdrag_stats(self.vakt)
        self.assertEqual(data['summary']['utrykningstid']['n'], 0)
        self.assertEqual(data['summary']['utelatt']['negativ'], 1)
        # Responstiden fra opprettelse er positiv og teller.
        self.assertEqual(data['summary']['responstid']['median'], 5.0)


class ScopeOgFordelingTests(OppdragStatsBasis):
    def test_bare_vaktas_oppdrag_telles(self):
        self._oppdrag()
        self._oppdrag(vakt=vakt_for_year(2097))

        self.assertEqual(oppdrag_stats(self.vakt)['summary']['total'], 1)
        self.assertEqual(
            oppdrag_stats(vakt_for_year(2097))['summary']['total'], 1)

    def test_fordelinger_sorteres_synkende(self):
        """Rekkefølgen er visningsrekkefølgen — stolpene skal stå stille."""
        for _ in range(3):
            self._oppdrag(problemstilling='Brannskade')
        self._oppdrag(problemstilling='Kramper')

        per = oppdrag_stats(self.vakt)['per_problemstilling']
        self.assertEqual(list(per.keys()), ['Brannskade', 'Kramper'])

    def test_responstid_per_hastegrad_skiller_gruppene(self):
        rask = self._oppdrag(hastegrad='Akutt')
        self._stempel(rask, choices.RYKKER_UT, 1)
        self._stempel(rask, choices.FREMME, 4)
        treg = self._oppdrag(hastegrad='Vanlig')
        self._stempel(treg, choices.RYKKER_UT, 12)
        self._stempel(treg, choices.FREMME, 30)

        per = oppdrag_stats(self.vakt)['responstid_per_hastegrad']
        self.assertEqual(per['Akutt']['median'], 4.0)
        self.assertEqual(per['Vanlig']['median'], 30.0)

    def test_status_naa_daekker_alle_statusene(self):
        """Tomme statuser er med — en graf som mangler en søyle er ikke tom."""
        rader = oppdrag_stats(self.vakt)['status_naa']
        self.assertEqual([r['status'] for r in rader],
                         [s for s, _ in choices.STATUS_VALG])

    def test_enheter_pa_vakt_teller_beredskapen_naa(self):
        Enhet.objects.create(navn='Karmøy 12', pa_vakt=True)
        Enhet.objects.create(navn='Reserve 1', pa_vakt=False)
        Enhet.objects.create(navn='Pensjonert', pa_vakt=True, er_aktiv=False)

        self.assertEqual(
            oppdrag_stats(self.vakt)['summary']['enheter_pa_vakt'], 2)

    def test_ankomster_har_ett_innslag_per_klokketime(self):
        self._oppdrag()
        ankomster = oppdrag_stats(self.vakt)['ankomster']
        self.assertEqual(len(ankomster), 24)
        self.assertEqual(sum(a['antall'] for a in ankomster), 1)


class GjeldendeBulkTests(OppdragStatsBasis):
    """Bulk-varianten må gi nøyaktig det `gjeldende()` gir, ellers har
    regelen delt seg i to — som er det manageren finnes for å hindre."""

    def test_korrigert_rad_er_ikke_med(self):
        """Selve regelen, målt der den bor.

        Statistikken over ville bestått også uten regelen: den tar siste rad
        per status, og en korreksjon lagres alltid etter raden den retter.
        Sammenfallet er ikke en garanti — det er et sammentreff mellom to
        rekkefølger — så regelen låses her, på manageren, der den kan feile
        alene.
        """
        oppdrag = self._oppdrag()
        original = self._stempel(oppdrag, choices.RYKKER_UT, 5)
        korreksjon = services.korriger_tidspunkt(
            original, oppdrag.created_at + timedelta(minutes=2),
            bruker=self.bruker)

        gjeldende = Statusmelding.objects.gjeldende_bulk(
            [oppdrag.pk])[oppdrag.pk]
        pk_er = [m.pk for m in gjeldende]
        self.assertIn(korreksjon.pk, pk_er)
        self.assertNotIn(original.pk, pk_er,
                         'den korrigerte raden skal ikke være gjeldende')

    def test_kjede_av_korreksjoner_gir_bare_den_siste(self):
        """Retter man en retting, står den siste — og bare den."""
        oppdrag = self._oppdrag()
        original = self._stempel(oppdrag, choices.RYKKER_UT, 9)
        forste = services.korriger_tidspunkt(
            original, oppdrag.created_at + timedelta(minutes=5),
            bruker=self.bruker)
        andre = services.korriger_tidspunkt(
            forste, oppdrag.created_at + timedelta(minutes=3),
            bruker=self.bruker)

        pk_er = [m.pk for m in
                 Statusmelding.objects.gjeldende_bulk([oppdrag.pk])[oppdrag.pk]]
        self.assertEqual(pk_er, [andre.pk])

    def test_bulk_gir_samme_som_enkeltoppslag(self):
        a = self._oppdrag()
        self._stempel(a, choices.RYKKER_UT, 2)
        original = self._stempel(a, choices.FREMME, 20)
        services.korriger_tidspunkt(
            original, a.created_at + timedelta(minutes=8), bruker=self.bruker)
        b = self._oppdrag()
        self._stempel(b, choices.RYKKER_UT, 1)

        bulk = Statusmelding.objects.gjeldende_bulk([a.pk, b.pk])
        for oppdrag in (a, b):
            self.assertEqual(
                [m.pk for m in bulk[oppdrag.pk]],
                [m.pk for m in Statusmelding.objects.gjeldende(oppdrag)])

    def test_oppdrag_uten_meldinger_gir_tom_liste(self):
        oppdrag = self._oppdrag()
        self.assertEqual(
            Statusmelding.objects.gjeldende_bulk([oppdrag.pk])[oppdrag.pk], [])

    def test_statistikken_bruker_faa_spoerringer(self):
        """To spørringer for radene, uansett hvor mange oppdrag vakta har.

        Ett kall per oppdrag ville gitt én spørring per rad — samme felle som
        pasientlista gikk i før den fikk `select_related`.
        """
        for _ in range(5):
            oppdrag = self._oppdrag()
            self._stempel(oppdrag, choices.RYKKER_UT, 2)

        with self.assertNumQueries(3):
            # oppdrag + statusmeldinger + Enhet-tellingen i sammendraget
            oppdrag_stats(self.vakt)
