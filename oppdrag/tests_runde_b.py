"""Andrés runde på staging 12. sep. 2026, del B — verdimengdene og lokasjonene.

Hastegraden Drift med egne problemstillinger, «Udefinert» som må bort før
bilen slås ledig, antall på transport, enhetstyper som grupperer tavla, og
lokasjoner som sentralbordet vedlikeholder selv.
"""
import json

from django.test import SimpleTestCase, TestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
    node_available, run_node)

from . import choices, verdier, services
from .models import Enhet, Enhetstype, Oppdrag, Problemstilling
from .tests_views import OppdragBasis, StemplingBasis, _bruker, _klient


class VerdimengdeneTests(TestCase):
    """Problemstillingene er en tabell (12. sep. 2026), seedet av `0020`.
    Reglene som ikke står i tabellen bor i `verdier`: Udefinert først,
    ukjent hastegrad gir tom liste."""

    def test_drift_har_egne_problemstillinger_og_alle_har_udefinert(self):
        kart = verdier.problemstillinger_per_hastegrad()
        for h in choices.HASTEGRAD:
            self.assertEqual(kart[h][0], choices.UDEFINERT, h)
        self.assertIn('Matutlevering', kart['Drift'])
        self.assertNotIn('Matutlevering', kart['Akutt'])
        self.assertNotIn('Pustevansker', kart['Drift'])
        self.assertTrue(verdier.problemstilling_passer('Drift', 'Transport'))
        self.assertTrue(verdier.problemstilling_passer('Vanlig', 'Transport'))
        self.assertFalse(verdier.problemstilling_passer('Vanlig', 'Matutlevering'))
        self.assertFalse(verdier.problemstilling_passer('Tull', 'Transport'), 'ukjent stenger')
        self.assertEqual(verdier.problemstillinger_for('Tull'), [])

    def test_seedet_er_listene_fra_choices(self):
        kart = verdier.problemstillinger_per_hastegrad()
        self.assertEqual(kart['Akutt'], list(choices.PROBLEMSTILLING_MEDISINSK))
        # Drift-lista har samme innhold; «Transport» fikk plassen sin i den
        # medisinske lista, og står derfor før «Matutlevering» her.
        self.assertEqual(set(kart['Drift']), set(choices.PROBLEMSTILLING_DRIFT))
        self.assertEqual(kart['Drift'][0], choices.UDEFINERT)
        self.assertEqual(verdier.med_antall(), list(choices.MED_ANTALL_SEED))

    def test_udefinert_staar_forst_uansett_rekkefolge(self):
        Problemstilling.objects.filter(navn=choices.UDEFINERT).update(rekkefolge=9999)
        self.assertEqual(verdier.problemstillinger_for('Akutt')[0], choices.UDEFINERT)

    def test_deaktivert_forsvinner_fra_lista_men_gjeldende_verdi_godtas(self):
        Problemstilling.objects.filter(navn='Utstyr').update(er_aktiv=False)
        self.assertNotIn('Utstyr', verdier.problemstillinger_for('Drift'))
        self.assertFalse(verdier.problemstilling_passer('Drift', 'Utstyr'))
        self.assertTrue(verdier.problemstilling_passer('Drift', 'Utstyr', gjeldende='Utstyr'))
        self.assertFalse(verdier.problemstilling_passer('Akutt', 'Utstyr', gjeldende='Utstyr'),
                         'men fortsatt bare for hastegraden den passer')


class OpprettelseTests(OppdragBasis):
    def setUp(self):
        super().setUp()
        self.c = _klient(_bruker('sentral', 'skriv_full'))

    def _post(self, **felt):
        data = {'enhet_ider': [self.enhet.pk], 'lokasjon_id': self.lokasjon.pk,
                'hastegrad': 'Akutt', 'problemstilling': 'Pustevansker', **felt}
        return self.c.post('/oppdrag/api/oppdrag/', data=json.dumps(data),
                           content_type='application/json')

    def test_drift_med_matutlevering(self):
        res = self._post(hastegrad='Drift', problemstilling='Matutlevering')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['hastegrad'], 'Drift')

    def test_problemstillingen_maa_hore_til_hastegraden(self):
        for h, p in (('Drift', 'Pustevansker'), ('Vanlig', 'Matutlevering')):
            with self.subTest(h=h, p=p):
                res = self._post(hastegrad=h, problemstilling=p)
                self.assertEqual(res.status_code, 400)
                self.assertIn('ikke en problemstilling for', res.json()['message'])
        self.assertEqual(Oppdrag.objects.count(), 0)

    def test_udefinert_kan_opprettes_med_enhver_hastegrad(self):
        for h in choices.HASTEGRAD:
            with self.subTest(h=h):
                self.assertEqual(self._post(hastegrad=h, problemstilling='Udefinert').status_code, 200)

    def test_transport_baerer_antall(self):
        res = self._post(problemstilling='Transport', antall='3')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['antall'], 3)
        self.assertEqual(self._post(problemstilling='Transport', antall='x').status_code, 400)
        self.assertEqual(self._post(problemstilling='Transport', antall='2.5').status_code, 400)
        res = self._post(problemstilling='Transport')
        self.assertIsNone(res.json()['data']['antall'], 'valgfritt')

    def test_antall_tommes_for_problemstillinger_uten(self):
        res = self._post(problemstilling='Pustevansker', antall='3')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()['data']['antall'])

    def test_redigering_sjekker_mot_gjeldende_verdier(self):
        o = self._oppdrag()   # Akutt / Pustevansker
        res = self.c.put(f'/oppdrag/api/oppdrag/{o.pk}/', data=json.dumps({'hastegrad': 'Drift'}),
                         content_type='application/json')
        self.assertEqual(res.status_code, 400, 'Pustevansker er ikke drift')
        res = self.c.put(f'/oppdrag/api/oppdrag/{o.pk}/',
                         data=json.dumps({'hastegrad': 'Drift', 'problemstilling': 'Transport', 'antall': 4}),
                         content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        o.refresh_from_db()
        self.assertEqual((o.hastegrad, o.problemstilling, o.antall), ('Drift', 'Transport', 4))
        res = self.c.put(f'/oppdrag/api/oppdrag/{o.pk}/', data=json.dumps({'problemstilling': 'Utstyr'}),
                         content_type='application/json')
        self.assertEqual(res.status_code, 200)
        o.refresh_from_db()
        self.assertIsNone(o.antall, 'antallet følger ikke med til en problemstilling uten')

    def test_siden_baerer_verdimengdene_og_verdiknappen(self):
        res = self.c.get('/oppdrag/')
        self.assertContains(res, 'OPPDRAG_PROBLEMSTILLINGER_FOR')
        self.assertContains(res, 'OPPDRAG_MED_ANTALL')
        self.assertContains(res, 'OPPDRAG_ENHETSTYPER')
        # Antallet settes av bilen (12. sep. 2026) — ikke i operatørens skjema.
        self.assertNotContains(res, 'id="nytt-antall-rad"')
        # Verdiene er skriv_leder; skriv_full har ikke vinduet.
        self.assertNotContains(res, 'id="valglisterModal"')
        leder = _klient(_bruker('leder', 'skriv_leder')).get('/oppdrag/')
        self.assertContains(leder, 'id="valglisterModal"')
        adm = _klient(_bruker('adm_b', 'skriv_full', admin=True)).get('/oppdrag/')
        self.assertContains(adm, 'id="valglisterModal"', msg_prefix='global admin ser alt')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class UdefinertSperrerLedigTests(StemplingBasis):
    def _udefinert(self):
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(problemstilling=choices.UDEFINERT)
        o.refresh_from_db()
        return o

    def test_bilen_kan_ikke_melde_ledig_foer_problemstillingen_er_satt(self):
        o = self._udefinert()
        self.assertEqual(self._stemple(o, 'rykker_ut').status_code, 200)
        self.assertEqual(self._stemple(o, 'fremme').status_code, 200)
        Oppdrag.objects.filter(pk=o.pk).update(grovsortering='gul')
        self.assertEqual(self._stemple(o, 'behandlet').status_code, 200)
        res = self._stemple(o, 'ledig')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('Udefinert', res.json()['message'])
        o.refresh_from_db()
        self.assertEqual(o.status, choices.BEHANDLET, 'ingenting ble skrevet')
        Oppdrag.objects.filter(pk=o.pk).update(problemstilling='Pustevansker')
        self.assertEqual(self._stemple(o, 'ledig').status_code, 200)

    def test_sentralbordets_foering_stoppes_ogsaa(self):
        o = self._udefinert()
        services.sett_status(o, choices.RYKKER_UT)
        with self.assertRaises(services.ProblemstillingUdefinert):
            services.sett_status(o, choices.LEDIG, manuell=True)

    def test_den_automatiske_lukkingen_slipper(self):
        """Å starte neste oppdrag er ikke et valg om det forrige."""
        o = self._udefinert()
        services.sett_status(o, choices.RYKKER_UT)
        neste = self._oppdrag()
        services.start_oppdrag(neste, enhet=self.enhet)
        o.refresh_from_db()
        self.assertEqual(services.koblingsrad(o, self.enhet).status, choices.LEDIG)
        self.assertTrue(o.trenger_ressurs, 'og oppdraget står igjen på tavla')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EnhetstypeTests(OppdragBasis):
    """Typen er en tabell (12. sep. 2026), seedet av `0020`; enheten peker
    på den med ID."""

    def setUp(self):
        super().setUp()
        self.ambulanse = Enhetstype.objects.get(navn='Ambulanse')

    def test_skriv_full_setter_typen(self):
        c = _klient(_bruker('sentral', 'skriv_full'))
        res = c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': self.ambulanse.pk}),
                    content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Enhet.objects.get(pk=self.enhet.pk).enhetstype, self.ambulanse)
        self.assertEqual(c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': 999999}),
                               content_type='application/json').status_code, 400)
        rad = next(e for e in c.get('/oppdrag/api/enheter/').json()['data'] if e['id'] == self.enhet.pk)
        self.assertEqual((rad['type'], rad['type_navn']), (self.ambulanse.pk, 'Ambulanse'))
        res = c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': None}),
                    content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(Enhet.objects.get(pk=self.enhet.pk).enhetstype)

    def test_inaktiv_type_kan_ikke_velges(self):
        self.ambulanse.er_aktiv = False
        self.ambulanse.save()
        c = _klient(_bruker('sentral', 'skriv_full'))
        self.assertEqual(c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': self.ambulanse.pk}),
                               content_type='application/json').status_code, 400)

    def test_les_kan_ikke(self):
        c = _klient(_bruker('leser', 'les'))
        self.assertEqual(c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': self.ambulanse.pk}),
                               content_type='application/json').status_code, 403)

    def test_standard_er_uten_type(self):
        self.assertIsNone(self.enhet.enhetstype)

    def test_seedet_i_rekkefolge(self):
        self.assertEqual([t.navn for t in verdier.enhetstyper()],
                         [n for _, n in choices.ENHETSTYPE_SEED])


class GrupperingJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (OPPDRAG_SENTRAL_JS, ('_grupperEnheter', '_typeRekkefolge', 'mkEnhetsvalg',
                              '_problemMedAntall', 'fyllProblemstillinger', 'hastegradEndret',
                              'problemstillingerFor', '_medAntall')),
    )
    VINDU = ("globalThis.window = { OPPDRAG_ENHETSTYPER: [[1,'Ambulanse'],[2,'Mannskapsbil'],"
             "[3,'Lag til fots'],[4,'Annet']],"
             " OPPDRAG_PROBLEMSTILLINGER_FOR: {Akutt: ['Udefinert','Pustevansker','Transport'],"
             " Drift: ['Udefinert','Matutlevering','Transport']}, OPPDRAG_MED_ANTALL: ['Transport'] };\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_ambulansene_forst_uten_type_sist_og_alfabetisk_i_gruppa(self):
        run_node(self.harness, self.VINDU + """
            const g = _grupperEnheter([
              {id: 1, navn: 'Lag 3', type: 3}, {id: 2, navn: 'Ukjent', type: null},
              {id: 3, navn: 'HGSD 56', type: 1}, {id: 4, navn: 'Bil', type: 2},
              {id: 5, navn: 'ålesund 1', type: 1}, {id: 6, navn: 'Bergen 2', type: 1},
              {id: 7, navn: 'Drone', type: 99, type_navn: 'Drone (inaktiv)'}]);
            assert(JSON.stringify(g.map((x) => x.type)) === '["1","2","3","","99"]', JSON.stringify(g));
            assert(g[0].navn === 'Ambulanse' && g[3].navn === 'Uten type' && g[4].navn === 'Drone (inaktiv)',
                   'navn fra typene, ellers «Uten type» eller navnet enheten bærer');
            assert(JSON.stringify(g[0].enheter.map((e) => e.navn)) === '["Bergen 2","HGSD 56","ålesund 1"]',
                   'alfabetisk innenfor gruppa: ' + JSON.stringify(g[0].enheter.map((e) => e.navn)));
        """)

    def test_avkryssingen_har_overskrifter_bare_med_flere_typer(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.enheter = [{id: 1, navn: 'HGSD 56', type: 1, pa_vakt: true},
                                  {id: 2, navn: 'Bil <b>2</b>', type: 2, pa_vakt: true},
                                  {id: 3, navn: 'Av', type: 1, pa_vakt: false}];
            console.log(mkEnhetsvalg());
            globalThis.enheter = [{id: 1, navn: 'HGSD 56', type: 1, pa_vakt: true}];
            console.log('---');
            console.log(mkEnhetsvalg());
        """)
        med, uten = ut.split('---')
        self.assertIn('enhet-gruppe">Ambulanse<', med)
        self.assertLess(med.index('HGSD 56'), med.index('Bil &lt;b&gt;2'), 'ambulansen først')
        self.assertNotIn('Av', med.replace('Ambulanse', ''))
        self.assertNotIn('enhet-gruppe', uten, 'én type — ingen overskrift')

    def test_problemstillingene_folger_hastegraden(self):
        run_node(self.harness, self.VINDU + """
            const felter = {
              'nytt-hastegrad': {value: 'Akutt'},
              'nytt-problemstilling': {value: 'Pustevansker', innerHTML: ''},
            };
            globalThis.document = { getElementById: (id) => felter[id] || null };
            felter['nytt-hastegrad'].value = 'Drift';
            hastegradEndret('nytt');
            const html = felter['nytt-problemstilling'].innerHTML;
            assert(html.includes('Matutlevering') && !html.includes('Pustevansker'), html);
            assert(html.includes('value="Udefinert" selected'), 'Pustevansker finnes ikke i drift: første velges');
            // Transport finnes i begge: valget beholdes.
            felter['nytt-problemstilling'].value = 'Transport';
            felter['nytt-hastegrad'].value = 'Akutt';
            hastegradEndret('nytt');
            assert(felter['nytt-problemstilling'].innerHTML.includes('value="Transport" selected'), 'beholdt');
            // Antallet er bilens, og vises som pasienter; tomt er én.
            assert(_problemMedAntall({problemstilling: 'Transport', antall: 3}) === 'Transport · 3 pasienter');
            assert(_problemMedAntall({problemstilling: 'Transport', antall: null}) === 'Transport · 1 pasient');
            assert(_problemMedAntall({problemstilling: 'Pustevansker', antall: 3}) === 'Pustevansker');
        """)


class EnhetsskjermAntallTests(SimpleTestCase):
    def test_antallet_staar_ved_problemstillingen_i_bilen(self):
        from oppdrag.tests_xss import EnhetEscapingOppforselTests
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        harness = build_harness(EnhetEscapingOppforselTests.HARNESS)
        ut = run_node(harness, EnhetEscapingOppforselTests.STUBB + """
            globalThis.window = { OPPDRAG_MED_ANTALL: ['Transport'] };
            globalThis.mineOppdrag = [{id: 1, status: 'venter', status_navn: 'Venter',
              problemstilling: 'Transport', antall: 3, hastegrad: 'Drift', lokasjon_navn: 'Scene',
              opprettet: '2026-08-29T20:00:00Z', fritekst: '', neste_overgang: 'rykker_ut',
              neste_navn: 'Rykker ut', statusmeldinger: [], varslede: []}];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            renderVentende();
            console.log(el.innerHTML);
        """)
        self.assertIn('Transport · 3 pasienter', ut)
        self.assertIn('hastegrad-drift', ut)
