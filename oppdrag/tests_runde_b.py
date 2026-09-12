"""Andrés runde på staging 12. sep. 2026, del B — verdimengdene og lokasjonene.

Teknisk hastegrad med egne problemstillinger, «Udefinert» som må bort før
bilen slås ledig, antall på transport, enhetstyper som grupperer tavla, og
lokasjoner som sentralbordet vedlikeholder selv.
"""
import json

from django.test import SimpleTestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
    node_available, run_node)

from . import choices, services
from .models import Enhet, Oppdrag
from .tests_views import OppdragBasis, StemplingBasis, _bruker, _klient


class VerdimengdeneTests(SimpleTestCase):
    def test_teknisk_har_egne_problemstillinger_og_alle_har_udefinert(self):
        for h in choices.HASTEGRAD:
            self.assertIn(choices.UDEFINERT, choices.PROBLEMSTILLINGER_FOR[h], h)
        self.assertIn('Matutlevering', choices.PROBLEMSTILLINGER_FOR['Teknisk'])
        self.assertNotIn('Matutlevering', choices.PROBLEMSTILLINGER_FOR['Akutt'])
        self.assertNotIn('Pustevansker', choices.PROBLEMSTILLINGER_FOR['Teknisk'])
        self.assertTrue(choices.problemstilling_passer('Teknisk', 'Transport'))
        self.assertTrue(choices.problemstilling_passer('Vanlig', 'Transport'))
        self.assertFalse(choices.problemstilling_passer('Vanlig', 'Matutlevering'))
        self.assertFalse(choices.problemstilling_passer('Tull', 'Transport'), 'ukjent stenger')

    def test_alle_problemstillinger_er_unionen(self):
        for liste in choices.PROBLEMSTILLINGER_FOR.values():
            for p in liste:
                self.assertIn(p, choices.PROBLEMSTILLING)
        self.assertEqual(len(choices.PROBLEMSTILLING), len(set(choices.PROBLEMSTILLING)))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class OpprettelseTests(OppdragBasis):
    def setUp(self):
        super().setUp()
        self.c = _klient(_bruker('sentral', 'skriv_full'))

    def _post(self, **felt):
        data = {'enhet_ider': [self.enhet.pk], 'lokasjon_id': self.lokasjon.pk,
                'hastegrad': 'Akutt', 'problemstilling': 'Pustevansker', **felt}
        return self.c.post('/oppdrag/api/oppdrag/', data=json.dumps(data),
                           content_type='application/json')

    def test_teknisk_med_matutlevering(self):
        res = self._post(hastegrad='Teknisk', problemstilling='Matutlevering')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['hastegrad'], 'Teknisk')

    def test_problemstillingen_maa_hore_til_hastegraden(self):
        for h, p in (('Teknisk', 'Pustevansker'), ('Vanlig', 'Matutlevering')):
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
        res = self.c.put(f'/oppdrag/api/oppdrag/{o.pk}/', data=json.dumps({'hastegrad': 'Teknisk'}),
                         content_type='application/json')
        self.assertEqual(res.status_code, 400, 'Pustevansker er ikke teknisk')
        res = self.c.put(f'/oppdrag/api/oppdrag/{o.pk}/',
                         data=json.dumps({'hastegrad': 'Teknisk', 'problemstilling': 'Transport', 'antall': 4}),
                         content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        o.refresh_from_db()
        self.assertEqual((o.hastegrad, o.problemstilling, o.antall), ('Teknisk', 'Transport', 4))
        res = self.c.put(f'/oppdrag/api/oppdrag/{o.pk}/', data=json.dumps({'problemstilling': 'Utstyr'}),
                         content_type='application/json')
        self.assertEqual(res.status_code, 200)
        o.refresh_from_db()
        self.assertIsNone(o.antall, 'antallet følger ikke med til en problemstilling uten')

    def test_siden_baerer_verdimengdene_og_lokasjonsknappen(self):
        res = self.c.get('/oppdrag/')
        self.assertContains(res, 'OPPDRAG_PROBLEMSTILLINGER_FOR')
        self.assertContains(res, 'OPPDRAG_MED_ANTALL')
        self.assertContains(res, 'OPPDRAG_ENHETSTYPER')
        self.assertContains(res, 'id="lokasjonerModal"', msg_prefix='skriv_full har lokasjonene')
        self.assertContains(res, 'id="nytt-antall-rad"')
        leser = _klient(_bruker('leser', 'les')).get('/oppdrag/')
        self.assertNotContains(leser, 'id="lokasjonerModal"')


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
        res = self._stemple(o, 'ledig')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('Udefinert', res.json()['message'])
        o.refresh_from_db()
        self.assertEqual(o.status, choices.RYKKER_UT, 'ingenting ble skrevet')
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
        self.assertEqual(o.status, choices.LEDIG)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EnhetstypeTests(OppdragBasis):
    def test_skriv_full_setter_typen(self):
        c = _klient(_bruker('sentral', 'skriv_full'))
        res = c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': 'ambulanse'}),
                    content_type='application/json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Enhet.objects.get(pk=self.enhet.pk).type, 'ambulanse')
        self.assertEqual(c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': 'ufo'}),
                               content_type='application/json').status_code, 400)
        rad = next(e for e in c.get('/oppdrag/api/enheter/').json()['data'] if e['id'] == self.enhet.pk)
        self.assertEqual((rad['type'], rad['type_navn']), ('ambulanse', 'Ambulanse'))

    def test_les_kan_ikke(self):
        c = _klient(_bruker('leser', 'les'))
        self.assertEqual(c.put(f'/oppdrag/api/enheter/{self.enhet.pk}/', data=json.dumps({'type': 'ambulanse'}),
                               content_type='application/json').status_code, 403)

    def test_standard_er_annet(self):
        self.assertEqual(self.enhet.type, 'annet')


class GrupperingJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (OPPDRAG_SENTRAL_JS, ('_grupperEnheter', '_typeRekkefolge', 'mkEnhetsvalg',
                              '_problemMedAntall', 'fyllProblemstillinger', 'hastegradEndret',
                              'problemstillingEndret', 'problemstillingerFor', '_medAntall',
                              '_lesAntall')),
    )
    VINDU = ("globalThis.window = { OPPDRAG_ENHETSTYPER: [['ambulanse','Ambulanse'],['mannskapsbil','Mannskapsbil'],"
             "['lag','Lag til fots'],['annet','Annet']],"
             " OPPDRAG_PROBLEMSTILLINGER_FOR: {Akutt: ['Udefinert','Pustevansker','Transport'],"
             " Teknisk: ['Udefinert','Matutlevering','Transport']}, OPPDRAG_MED_ANTALL: ['Transport'] };\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_ambulansene_forst_og_ukjent_type_sist(self):
        run_node(self.harness, self.VINDU + """
            const g = _grupperEnheter([
              {id: 1, navn: 'Lag 3', type: 'lag'}, {id: 2, navn: 'Ukjent', type: 'drone'},
              {id: 3, navn: 'HGSD 56', type: 'ambulanse'}, {id: 4, navn: 'Bil', type: 'mannskapsbil'}]);
            assert(JSON.stringify(g.map((x) => x.type)) === '["ambulanse","mannskapsbil","lag","drone"]', JSON.stringify(g));
            assert(g[0].navn === 'Ambulanse' && g[3].navn === 'drone', 'navn fra typene, ellers nøkkelen');
        """)

    def test_avkryssingen_har_overskrifter_bare_med_flere_typer(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.enheter = [{id: 1, navn: 'HGSD 56', type: 'ambulanse', pa_vakt: true},
                                  {id: 2, navn: 'Bil <b>2</b>', type: 'mannskapsbil', pa_vakt: true},
                                  {id: 3, navn: 'Av', type: 'ambulanse', pa_vakt: false}];
            console.log(mkEnhetsvalg());
            globalThis.enheter = [{id: 1, navn: 'HGSD 56', type: 'ambulanse', pa_vakt: true}];
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
              'nytt-antall-rad': {klasser: new Set(['d-none']),
                 classList: {toggle(c, on) { on ? this.s.add(c) : this.s.delete(c); }, s: null}},
            };
            felter['nytt-antall-rad'].classList.s = felter['nytt-antall-rad'].klasser;
            globalThis.document = { getElementById: (id) => felter[id] || null };
            felter['nytt-hastegrad'].value = 'Teknisk';
            hastegradEndret('nytt');
            const html = felter['nytt-problemstilling'].innerHTML;
            assert(html.includes('Matutlevering') && !html.includes('Pustevansker'), html);
            assert(html.includes('value="Udefinert" selected'), 'Pustevansker finnes ikke teknisk: første velges');
            // Transport finnes i begge: valget beholdes, og antall-raden vises.
            felter['nytt-problemstilling'].value = 'Transport';
            felter['nytt-hastegrad'].value = 'Akutt';
            hastegradEndret('nytt');
            assert(felter['nytt-problemstilling'].innerHTML.includes('value="Transport" selected'), 'beholdt');
            felter['nytt-problemstilling'].value = 'Transport';
            problemstillingEndret('nytt');
            assert(!felter['nytt-antall-rad'].klasser.has('d-none'), 'antall vises for transport');
            felter['nytt-problemstilling'].value = 'Pustevansker';
            problemstillingEndret('nytt');
            assert(felter['nytt-antall-rad'].klasser.has('d-none'), 'og skjules ellers');
            assert(_problemMedAntall({problemstilling: 'Transport', antall: 3}) === 'Transport · 3');
            assert(_problemMedAntall({problemstilling: 'Transport', antall: null}) === 'Transport');
        """)


class EnhetsskjermAntallTests(SimpleTestCase):
    def test_antallet_staar_ved_problemstillingen_i_bilen(self):
        from oppdrag.tests_xss import EnhetEscapingOppforselTests
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        harness = build_harness(EnhetEscapingOppforselTests.HARNESS)
        ut = run_node(harness, EnhetEscapingOppforselTests.STUBB + """
            globalThis.mineOppdrag = [{id: 1, status: 'venter', status_navn: 'Venter',
              problemstilling: 'Transport', antall: 3, hastegrad: 'Teknisk', lokasjon_navn: 'Scene',
              opprettet: '2026-08-29T20:00:00Z', fritekst: '', neste_overgang: 'rykker_ut',
              neste_navn: 'Rykker ut', statusmeldinger: [], varslede: []}];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            renderVentende();
            console.log(el.innerHTML);
        """)
        self.assertIn('Transport · 3', ut)
        self.assertIn('hastegrad-teknisk', ut)
