"""«Avbrutt» og «trenger ny ressurs» er to ulike beskjeder (15. sep. 2026).

**Andrés melding fra staging:**

    «akutt oppdrag opprettes, to enheter varsles. Ene bilen behandler på
    stedet, andre bil slo avbrutt. Da står det trenger ressurs selv om
    oppdraget er løst — og trykker en bil avbryt så må det vises.»

**Feilen var at ett spørsmål ble stilt der to trengs.** Regelen sto som
«finnes det andre enheter som ikke er ledige», og den kan ikke skille en bil
som ble ledig fordi hun *ble ferdig* fra en som ble ledig fordi hun *avbrøt* —
begge deler er `Ledig` på koblingsraden. `trenger_ny_ressurs()` spør nå begge:
er noen fortsatt på vei, **og** var noen framme.
"""
from django.test import TestCase

from oppdrag import choices, services
from oppdrag.models import Enhetshendelse, Oppdragsenhet
from oppdrag.tests import _enhet, _oppdrag


class ToEnheterBasis(TestCase):
    """Ett akutt oppdrag, to biler varslet — Andrés scenario."""

    def setUp(self):
        self.a = _enhet('Bil A')
        self.b = _enhet('Bil B')
        self.oppdrag = _oppdrag(self.a, status=choices.VENTER)
        Oppdragsenhet.objects.create(
            oppdrag=self.oppdrag, enhet=self.b, status=choices.VENTER, rekkefolge=1)

    def _rykk_ut(self, *enheter):
        for e in enheter:
            services.sett_status(self.oppdrag, choices.RYKKER_UT, enhet=e)

    def _frisk(self):
        self.oppdrag.refresh_from_db()
        return self.oppdrag


class TrengerNyRessursTests(ToEnheterBasis):

    def test_behandlet_paa_sted_saa_avbrutt(self):
        """**Feilen André meldte.** Bil A løste oppdraget; at Bil B avbrøt
        etterpå endrer ikke at jobben er gjort."""
        self._rykk_ut(self.a, self.b)
        services.sett_status(self.oppdrag, choices.FREMME, enhet=self.a)
        services.behandle_paa_sted(self.oppdrag, enhet=self.a)

        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)

        o = self._frisk()
        self.assertFalse(o.trenger_ressurs, 'oppdraget ble løst av Bil A')
        self.assertIsNone(o.trenger_ressurs_siden)
        self.assertEqual(o.status, choices.TERMINAL)
        self.assertIsNotNone(o.historikk_fra, 'et løst oppdrag ryddes av tavla')

    def test_leverer_teller_som_lost(self):
        """Behandlet på sted er ikke den eneste utgangen — den som leverte
        løste det også."""
        self._rykk_ut(self.a, self.b)
        for status in (choices.FREMME, choices.AVREIST, choices.LEVERER):
            services.sett_status(self.oppdrag, status, enhet=self.a)
        services.sett_status(self.oppdrag, choices.LEDIG, enhet=self.a)

        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)

        self.assertFalse(self._frisk().trenger_ressurs)

    def test_ingen_var_framme_gir_trenger_ny_ressurs(self):
        """Regelen skal ikke slå for bredt: avbryter begge bilene, står
        oppdraget igjen uten noen — og da *trengs* en ny ressurs."""
        self._rykk_ut(self.a, self.b)
        services.avbryt_oppdrag(self.oppdrag, enhet=self.a)
        self.assertFalse(self._frisk().trenger_ressurs,
                         'Bil B er fortsatt på vei')

        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)

        o = self._frisk()
        self.assertTrue(o.trenger_ressurs, 'ingen løste det, ingen er igjen')
        self.assertIsNotNone(o.trenger_ressurs_siden)
        self.assertEqual(o.status, choices.VENTER, 'står på tavla og venter')

    def test_avbrutt_foer_den_andre_rakk_fram(self):
        """Rekkefølgen skal ikke avgjøre svaret. Avbryter Bil B først, og Bil A
        behandler etterpå, er oppdraget like løst."""
        self._rykk_ut(self.a, self.b)
        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)
        services.sett_status(self.oppdrag, choices.FREMME, enhet=self.a)
        services.behandle_paa_sted(self.oppdrag, enhet=self.a)

        o = self._frisk()
        self.assertFalse(o.trenger_ressurs)
        self.assertIsNotNone(o.historikk_fra)

    def test_en_bil_alene_som_avbryter(self):
        """Regelen må ikke ha blitt mildere for det vanlige tilfellet."""
        alene = _enhet('Bil C')
        o = _oppdrag(alene, status=choices.VENTER)
        services.sett_status(o, choices.RYKKER_UT, enhet=alene)

        services.avbryt_oppdrag(o, enhet=alene)

        o.refresh_from_db()
        self.assertTrue(o.trenger_ressurs)

    def test_noen_loste_oppdraget_leser_meldingene_ikke_radene(self):
        """`behandle_paa_sted` sender raden videre til `Ledig`, så
        koblingsraden bærer ikke lenger spor av at jobben ble gjort. Svaret
        må derfor leses av statusmeldingene."""
        self._rykk_ut(self.a)
        services.sett_status(self.oppdrag, choices.FREMME, enhet=self.a)
        services.behandle_paa_sted(self.oppdrag, enhet=self.a)

        rad = services.koblingsrad(self.oppdrag, self.a)
        self.assertEqual(rad.status, choices.LEDIG, 'raden er ledig …')
        self.assertTrue(services.noen_loste_oppdraget(self.oppdrag),
                        '… men oppdraget ble løst')


class RykketVidereTests(ToEnheterBasis):
    """Samme regel når bilen rykker videre til et annet oppdrag."""

    def test_rykket_videre_fra_et_lost_oppdrag(self):
        self._rykk_ut(self.a, self.b)
        services.sett_status(self.oppdrag, choices.FREMME, enhet=self.a)
        services.behandle_paa_sted(self.oppdrag, enhet=self.a)

        # Bil B sendes til et nytt oppdrag mens dette står uferdig for henne.
        nytt = _oppdrag(self.b, status=choices.VENTER)
        services.start_oppdrag(nytt, enhet=self.b)

        self.assertFalse(self._frisk().trenger_ressurs,
                         'Bil A løste det; Bil B som drar endrer ikke det')

    def test_rykket_videre_fra_et_ulost_oppdrag(self):
        """Eget oppdrag med bare Bil B: da er hun den siste, og ingen var
        framme. `self.oppdrag` duger ikke her — der står Bil A fortsatt og
        venter, og et oppdrag med en bil igjen trenger ingen ny."""
        alene = _oppdrag(self.b, status=choices.VENTER)
        services.sett_status(alene, choices.RYKKER_UT, enhet=self.b)
        nytt = _oppdrag(self.b, status=choices.VENTER)

        services.start_oppdrag(nytt, enhet=self.b)

        alene.refresh_from_db()
        self.assertTrue(alene.trenger_ressurs, 'ingen har vært framme')

    def test_en_bil_som_venter_holder_oppdraget_dekket(self):
        """Regelen skal ikke slå for bredt andre veien heller: rykker Bil B
        videre mens Bil A fortsatt står varslet, er oppdraget ikke uten
        ressurs — Bil A er der."""
        self._rykk_ut(self.b)
        nytt = _oppdrag(self.b, status=choices.VENTER)

        services.start_oppdrag(nytt, enhet=self.b)

        self.assertFalse(self._frisk().trenger_ressurs, 'Bil A står igjen')


class AvbruttVisesTests(ToEnheterBasis):
    """«Trykker en bil avbryt så må det vises» — merket i lista.

    Detaljvisningen har hatt avbrytelsen i tidslinja hele tiden
    (`Enhetshendelse.AVBRUTT`). Det som manglet var å se den **uten å åpne
    oppdraget** — og etter feilrettingen over er det viktigere enn før: et
    oppdrag en annen bil løste ryddes nå bort av seg selv.
    """

    def test_avbrutt_av_navngir_enheten(self):
        self._rykk_ut(self.b)
        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)
        self.assertEqual(services.avbrutt_av(self.oppdrag), ['Bil B'])

    def test_uten_avbrytelse_er_lista_tom(self):
        self.assertEqual(services.avbrutt_av(self.oppdrag), [])

    def test_flere_avbrytelser_i_rekkefolge(self):
        self._rykk_ut(self.a, self.b)
        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)
        services.avbryt_oppdrag(self.oppdrag, enhet=self.a)
        self.assertEqual(services.avbrutt_av(self.oppdrag), ['Bil B', 'Bil A'])

    def test_bulk_gir_samme_svar_som_enkeltoppslaget(self):
        """Bulk finnes fordi tavla tegnes hvert tiende sekund. Svarer den noe
        annet enn enkeltoppslaget, viser lista og detaljen ulike ting."""
        annet = _oppdrag(self.a, status=choices.VENTER)
        self._rykk_ut(self.a, self.b)
        # **To avbrytelser, ikke én.** Med bare én kan rekkefølgen ikke vises,
        # og en bulk som sorterte feil vei gikk grønn.
        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)
        services.avbryt_oppdrag(self.oppdrag, enhet=self.a)

        bulk = services.avbrutt_av_bulk([self.oppdrag.pk, annet.pk])
        self.assertEqual(bulk.get(self.oppdrag.pk), ['Bil B', 'Bil A'])
        self.assertEqual(bulk.get(self.oppdrag.pk),
                         services.avbrutt_av(self.oppdrag),
                         'bulk og enkeltoppslag må svare likt')
        self.assertEqual(bulk.get(annet.pk, []), [],
                         'et oppdrag uten avbrytelse skal ikke få en rad')

    def test_hendelsen_skrives_uansett_om_flagget_settes(self):
        """Selv når oppdraget var løst og `trenger_ressurs` blir stående av,
        skal avbrytelsen etterlate et spor. Ellers ville feilrettingen gjort
        avbrytelsen usynlig i stedet for feilmerket."""
        self._rykk_ut(self.a, self.b)
        services.sett_status(self.oppdrag, choices.FREMME, enhet=self.a)
        services.behandle_paa_sted(self.oppdrag, enhet=self.a)

        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)

        self.assertFalse(self._frisk().trenger_ressurs)
        self.assertTrue(
            Enhetshendelse.objects.filter(
                oppdrag=self.oppdrag, type=Enhetshendelse.AVBRUTT).exists())
        self.assertEqual(services.avbrutt_av(self.oppdrag), ['Bil B'])


# ── Grensesnittet ────────────────────────────────────────────────────────

from django.test import SimpleTestCase                                 # noqa: E402
from django.urls import reverse                                        # noqa: E402

from patients.js_test_utils import (                                   # noqa: E402
    OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node,
)


class AvbruttIListaJsTests(SimpleTestCase):
    """Merket i enhetsmatrisen — det operatøren ser uten å åpne oppdraget."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (OPPDRAG_SENTRAL_JS, ('_enhetsmatrise', 'tidSiden', '_manglerTrinn',
                              '_manglerMinutter')),
    )

    def setUp(self):
        from .tests_runde_d import _konst
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = _konst(OPPDRAG_SENTRAL_JS, 'MANGLER_TRINN') + build_harness(self.HARNESS)

    LEDIG_RAD = ("{enhet_id: 1, enhet_navn: 'HGSD 56', status: 'ledig', "
                 "status_navn: 'Ledig', status_tidspunkt: null}")

    def _matrise(self, felt):
        return run_node(self.harness, f"""
            console.log(_enhetsmatrise({{{felt}, enheter: [{self.LEDIG_RAD}]}}));
        """)

    def test_avbrutt_navngir_enheten(self):
        ut = self._matrise("trenger_ressurs: false, avbrutt_av: ['Bil B']")
        self.assertIn('Avbrutt av Bil B', ut)

    def test_uten_avbrytelse_staar_merket_ikke(self):
        ut = self._matrise('trenger_ressurs: false, avbrutt_av: []')
        self.assertNotIn('Avbrutt av', ut)

    def test_eldre_svar_uten_feltet_kaster_ikke(self):
        """Et svar fra før 15. sep. 2026 har ingen `avbrutt_av`. Tavla
        polles hvert tiende sekund; en `TypeError` der tar ned hele lista."""
        ut = self._matrise('trenger_ressurs: false')
        self.assertNotIn('Avbrutt av', ut)
        self.assertIn('HGSD 56', ut)

    def test_begge_merkene_kan_staa_samtidig(self):
        """**De to er ulike opplysninger**: hvem som falt fra, og at noen må
        ut. Avbryter siste bil på et uløst oppdrag, er begge sanne."""
        ut = self._matrise("trenger_ressurs: true, avbrutt_av: ['Bil B']")
        self.assertIn('Trenger ny ressurs', ut)
        self.assertIn('Avbrutt av Bil B', ut)
        self.assertLess(ut.index('Trenger ny ressurs'), ut.index('Avbrutt av'),
                        'kravet om handling står først, opplysningen etter')

    def test_flere_enheter_listes_med_komma(self):
        ut = self._matrise("trenger_ressurs: false, avbrutt_av: ['Bil B', 'Bil C']")
        self.assertIn('Avbrutt av Bil B, Bil C', ut)

    def test_enhetsnavn_escapes(self):
        ut = self._matrise("trenger_ressurs: false, avbrutt_av: ['<img src=x onerror=alert(1)>']")
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)


class AvbruttISvaretTests(TestCase):
    """Feltet må faktisk komme ut av endepunktene lista leses fra."""

    def setUp(self):
        from .tests_runde_c import _bruker, _klient
        self.a = _enhet('Bil A')
        self.b = _enhet('Bil B')
        self.oppdrag = _oppdrag(self.a, status=choices.VENTER)
        Oppdragsenhet.objects.create(
            oppdrag=self.oppdrag, enhet=self.b, status=choices.VENTER, rekkefolge=1)
        services.sett_status(self.oppdrag, choices.RYKKER_UT, enhet=self.b)
        services.avbryt_oppdrag(self.oppdrag, enhet=self.b)
        self.klient = _klient(_bruker('sentral_avbrutt', 'skriv_full'))

    def test_tavla_baerer_avbrytelsen(self):
        rader = {r['id']: r for r in
                 self.klient.get('/oppdrag/api/oppdrag/').json()['data']}
        self.assertEqual(rader[self.oppdrag.pk]['avbrutt_av'], ['Bil B'])

    def test_detaljen_baerer_avbrytelsen(self):
        svar = self.klient.get(f'/oppdrag/api/oppdrag/{self.oppdrag.pk}/').json()
        self.assertEqual(svar['data']['avbrutt_av'], ['Bil B'])

    def test_historikken_baerer_avbrytelsen(self):
        """**Andrés scenario helt ut.** Bil A behandler på stedet, Bil B har
        avbrutt — oppdraget er løst og ryddes bort av seg selv. Historikken er
        da det eneste stedet avbrytelsen kan leses i en liste."""
        services.sett_status(self.oppdrag, choices.RYKKER_UT, enhet=self.a)
        services.sett_status(self.oppdrag, choices.FREMME, enhet=self.a)
        services.behandle_paa_sted(self.oppdrag, enhet=self.a)

        self.oppdrag.refresh_from_db()
        self.assertFalse(self.oppdrag.trenger_ressurs)
        self.assertIsNotNone(self.oppdrag.historikk_fra,
                             'oppdraget skal ha ryddet seg selv bort')

        rader = self.klient.get('/oppdrag/api/historikk/').json()['data']
        self.assertEqual([r['id'] for r in rader], [self.oppdrag.pk])
        self.assertEqual(rader[0]['avbrutt_av'], ['Bil B'])

    def test_etagen_endrer_seg_naar_en_bil_avbryter(self):
        """**Testen må isolere avbrytelsen**, ellers måler den noe annet.

        Avbryter siste bil, endres oppdragets status — og da hadde ETag-en
        endret seg uansett, også uten avbrytelsen i den. Her står Bil C
        fortsatt i Fremme, så oppdragets status og tidspunkt er de samme før og
        etter: det eneste som skiller de to svarene er merket.

        Første versjon av denne testen gikk grønn uten feltet i ETag-en.
        """
        c = _enhet('Bil C')
        d = _enhet('Bil D')
        annet = _oppdrag(c, status=choices.VENTER)
        Oppdragsenhet.objects.create(
            oppdrag=annet, enhet=d, status=choices.VENTER, rekkefolge=1)
        services.sett_status(annet, choices.RYKKER_UT, enhet=c)
        services.sett_status(annet, choices.FREMME, enhet=c)
        services.sett_status(annet, choices.RYKKER_UT, enhet=d)

        svar_foer = self.klient.get('/oppdrag/api/oppdrag/')
        rad_foer = [r for r in svar_foer.json()['data'] if r['id'] == annet.pk][0]

        services.avbryt_oppdrag(annet, enhet=d)

        svar_etter = self.klient.get('/oppdrag/api/oppdrag/')
        rad_etter = [r for r in svar_etter.json()['data'] if r['id'] == annet.pk][0]

        self.assertEqual(rad_foer['status'], rad_etter['status'],
                         'Bil C står fortsatt i Fremme — statusen er uendret')
        self.assertEqual(rad_foer['status_tidspunkt'], rad_etter['status_tidspunkt'])
        self.assertEqual(rad_etter['avbrutt_av'], ['Bil D'])
        self.assertNotEqual(svar_foer['ETag'], svar_etter['ETag'],
                            'merket ville ellers druknet i en 304')
