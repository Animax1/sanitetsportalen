"""Andrés runde på staging 12. sep. 2026, del D — småfeil og visning.

Avkryssingen i «Nytt oppdrag» som forsvant under polling, nedtrekk som skal
starte øverst, lista sortert på hastegrad og nummer, «trenger ny ressurs»
som blir tydeligere med tida og skjuler bilen som dro, nummer i «nylig
avsluttet», og «Udefinert»-meldingen som bilen aldri fikk se.
"""
import re

from django.test import SimpleTestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
    node_available, read_js, run_node)

from . import choices, services
from .tests_flere_enheter import FlereEnheterBasis, _bruker, _klient


def _konst(sti, navn):
    """Én toppnivåkonstant fra JS-fila, som kildelinje — så testene kjører
    mot den verdien fila faktisk har, ikke en kopi."""
    m = re.search(r'^const ' + navn + r' = .*?;$', read_js(sti), re.M | re.S)
    assert m, f'{navn} finnes ikke i {sti}'
    return m.group(0) + '\n'


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TrengerRessursSidenTests(FlereEnheterBasis):
    """Tidspunktet følger flagget: settes når bilen rykker videre, tømmes
    når en ny enhet varsles, og står i svaret så lista kan gradere."""

    def _rykk_videre(self):
        forste = self._oppdrag(self.a)
        services.sett_status(forste, choices.RYKKER_UT, enhet=self.a)
        andre = self._oppdrag(self.a)
        services.start_oppdrag(andre, enhet=self.a)
        forste.refresh_from_db()
        return forste

    def test_settes_sammen_med_flagget(self):
        forste = self._rykk_videre()
        self.assertTrue(forste.trenger_ressurs)
        self.assertIsNotNone(forste.trenger_ressurs_siden)

    def test_toemmes_naar_en_ny_enhet_varsles(self):
        forste = self._rykk_videre()
        services.varsle_enhet(forste, self.b)
        forste.refresh_from_db()
        self.assertFalse(forste.trenger_ressurs)
        self.assertIsNone(forste.trenger_ressurs_siden)

    def test_staar_i_svaret_til_sentralbordet(self):
        forste = self._rykk_videre()
        c = _klient(_bruker('sentral_e', 'skriv_full'))
        rad = {r['id']: r for r in c.get('/oppdrag/api/oppdrag/').json()['data']}[forste.pk]
        self.assertEqual(rad['trenger_ressurs_siden'], forste.trenger_ressurs_siden.isoformat())

    def test_udefinert_meldingen_sier_meld_til_ko(self):
        o = self._oppdrag(self.a)
        o.problemstilling = choices.UDEFINERT
        o.save(update_fields=['problemstilling'])
        services.sett_status(o, choices.RYKKER_UT, enhet=self.a)
        with self.assertRaises(services.ProblemstillingUdefinert) as cm:
            services.sett_status(o, choices.LEDIG, enhet=self.a)
        self.assertIn('Meld problemstillingen til KO', str(cm.exception))


class SorteringJsTests(SimpleTestCase):
    HARNESS = ((OPPDRAG_SENTRAL_JS, ('_sorterOppdrag',)),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)
        self.preamble = _konst(OPPDRAG_SENTRAL_JS, 'HASTEGRAD_REKKEFOLGE')

    def test_hastegrad_forst_saa_nummer_og_ferdige_nederst(self):
        ut = run_node(self.harness, """
            const liste = [
              {nummer: 7, hastegrad: 'Vanlig', status: 'fremme'},
              {nummer: 2, hastegrad: 'Akutt', status: 'ledig'},
              {nummer: 5, hastegrad: 'Akutt', status: 'venter'},
              {nummer: 3, hastegrad: 'Drift', status: 'rykker_ut'},
              {nummer: 1, hastegrad: 'Akutt', status: 'rykker_ut'},
              {nummer: 4, hastegrad: 'Haster', status: 'leverer'},
            ];
            console.log(JSON.stringify(_sorterOppdrag(liste).map((o) => o.nummer)));
            console.log(JSON.stringify(liste.map((o) => o.nummer)));
        """, preamble=self.preamble)
        sortert, original = ut.strip().splitlines()[:2]
        self.assertEqual(sortert, '[1,5,4,7,3,2]')
        self.assertEqual(original, '[7,2,5,3,1,4]', 'sorteringen rører ikke lista den fikk')

    def test_klientens_hastegrader_er_serverens(self):
        for sti in (OPPDRAG_SENTRAL_JS, OPPDRAG_ENHET_JS):
            verdier = re.findall(r"'([^']+)'", _konst(sti, 'HASTEGRAD_REKKEFOLGE'))
            self.assertEqual(verdier, list(choices.HASTEGRAD), sti)


class ManglerTrinnJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (OPPDRAG_SENTRAL_JS, ('_enhetsmatrise', '_manglerTrinn', '_manglerMinutter', 'tidSiden')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)
        self.preamble = _konst(OPPDRAG_SENTRAL_JS, 'MANGLER_TRINN')

    def test_trinnene_stiger_med_tida(self):
        ut = run_node(self.harness, """
            const o = (min) => ({trenger_ressurs_siden: '2026-09-12T10:00:00Z'});
            const naa = (min) => new Date(Date.UTC(2026, 8, 12, 10, min)).toISOString();
            console.log([0, 4, 5, 14, 15, 60].map((m) => _manglerTrinn(o(), naa(m))).join(' '));
            console.log(_manglerMinutter(o(), naa(12)));
            // Eldre svar uten feltet regner fra siste status.
            console.log(_manglerTrinn({status_tidspunkt: '2026-09-12T09:00:00Z'}, naa(0)));
        """, preamble=self.preamble)
        linjer = ut.strip().splitlines()
        self.assertEqual(linjer[0], 'ny ny varsel varsel alvorlig alvorlig')
        self.assertEqual(linjer[1], '12')
        self.assertEqual(linjer[2], 'alvorlig')

    def test_bilen_som_dro_staar_ikke_i_matrisen(self):
        ut = run_node(self.harness, """
            const rader = [
              {enhet_id: 1, enhet_navn: 'HGSD 56', status: 'ledig', status_navn: 'Ledig', status_tidspunkt: null},
              {enhet_id: 2, enhet_navn: 'KARM 12', status: 'venter', status_navn: 'Venter', status_tidspunkt: null}];
            console.log(_enhetsmatrise({trenger_ressurs: true, trenger_ressurs_siden: new Date().toISOString(), enheter: rader}));
            console.log('---');
            console.log(_enhetsmatrise({trenger_ressurs: false, enheter: rader}));
        """, preamble=self.preamble)
        med, uten = ut.split('---')
        self.assertNotIn('HGSD 56', med, 'den som rykket videre står i loggen, ikke i lista')
        self.assertIn('KARM 12', med)
        self.assertIn('bi-exclamation-triangle-fill', med, 'egen trekant, ikke statusprikken')
        self.assertIn('mangler-ny', med)
        self.assertIn('Trenger ny ressurs · 0 min', med)
        self.assertIn('HGSD 56', uten, 'uten flagget står ferdige biler som før')


class NyttOppdragSkjemaJsTests(SimpleTestCase):
    """`fyllNedtrekk` bygger avkryssingen om ved hver polling — det som sto
    krysset av og valgt skal overleve. `nullstillNyttOppdrag` starter alle
    nedtrekkene øverst."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (OPPDRAG_SENTRAL_JS, ('fyllNedtrekk', 'mkEnhetsvalg', '_valgteEnheter',
                              '_grupperEnheter', '_typeRekkefolge',
                              'nullstillNyttOppdrag', 'hastegradEndret')),
    )

    #: En liten DOM: avkryssingslista lager input-objekter av sin egen
    #: innerHTML, nedtrekkene har `options`, `value` og `selectedIndex`.
    DOM = """
        function nedtrekk(verdier) {
          const sel = { options: verdier.map((v) => ({value: v})), selectedIndex: 0 };
          Object.defineProperty(sel, 'value', {
            get() { return sel.options[sel.selectedIndex]?.value ?? ''; },
            set(v) { const i = sel.options.findIndex((o) => o.value === String(v)); sel.selectedIndex = i < 0 ? 0 : i; },
          });
          Object.defineProperty(sel, 'innerHTML', {
            set(html) {
              sel.options = [...html.matchAll(/value="([^"]*)"/g)].map((m) => ({value: m[1]}));
              sel.selectedIndex = 0;
            },
          });
          return sel;
        }
        const enhetsvalg = { inputs: [] };
        Object.defineProperty(enhetsvalg, 'innerHTML', {
          set(html) {
            enhetsvalg.inputs = [...html.matchAll(/name="nytt-enhet" value="([^"]*)"/g)]
              .map((m) => ({ value: m[1], checked: false }));
          },
        });
        enhetsvalg.querySelectorAll = () => enhetsvalg.inputs;
        const felter = {
          'nytt-enheter': enhetsvalg,
          'nytt-lokasjon': nedtrekk([]),
          'nytt-hastegrad': nedtrekk(['Akutt', 'Haster', 'Vanlig', 'Drift']),
          'nytt-problemstilling': nedtrekk(['Udefinert', 'Transport']),
          'nytt-fritekst': { value: '' }, 'nytt-antall': { value: '' },
          'nytt-antall-rad': { classList: { toggle() {} } },
          'nytt-feil': { classList: { add() {} } },
        };
        globalThis.document = {
          getElementById: (id) => felter[id] || null,
          querySelectorAll: (sel) => sel.includes(':checked')
            ? enhetsvalg.inputs.filter((i) => i.checked) : enhetsvalg.inputs,
        };
        globalThis.fyllProblemstillinger = (p, h, valgt) => { globalThis.sisteFyll = [h, valgt]; };
        globalThis.enheter = [
          {id: 1, navn: 'A', pa_vakt: true, type: 'ambulanse', type_navn: 'Ambulanse'},
          {id: 2, navn: 'B', pa_vakt: true, type: 'ambulanse', type_navn: 'Ambulanse'},
          {id: 3, navn: 'C', pa_vakt: true, type: 'lag', type_navn: 'Lag'}];
        globalThis.lokasjoner = [{id: 10, navn: 'Scene', er_aktiv: true}, {id: 11, navn: 'Port', er_aktiv: true}];
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_avkryssing_og_lokasjon_overlever_ny_tegning(self):
        ut = run_node(self.harness, self.DOM + """
            fyllNedtrekk();
            enhetsvalg.inputs[1].checked = true;   // B
            enhetsvalg.inputs[2].checked = true;   // C
            felter['nytt-lokasjon'].value = '11';
            fyllNedtrekk();                         // pollingen tegner på nytt
            console.log(JSON.stringify(_valgteEnheter()));
            console.log(felter['nytt-lokasjon'].value);
            // En bil som gikk av vakt i mellomtida forsvinner, resten står.
            enheter[2].pa_vakt = false;
            fyllNedtrekk();
            console.log(JSON.stringify(_valgteEnheter()));
        """)
        linjer = ut.strip().splitlines()
        self.assertEqual(linjer[0], '[2,3]')
        self.assertEqual(linjer[1], '11')
        self.assertEqual(linjer[2], '[2]')

    def test_nullstilling_starter_alle_nedtrekk_overst(self):
        ut = run_node(self.harness, self.DOM + """
            fyllNedtrekk();
            enhetsvalg.inputs[0].checked = true;
            felter['nytt-hastegrad'].value = 'Drift';
            felter['nytt-lokasjon'].value = '11';
            felter['nytt-problemstilling'].value = 'Transport';
            felter['nytt-fritekst'].value = 'noe';
            felter['nytt-antall'].value = '3';
            nullstillNyttOppdrag();
            console.log(JSON.stringify([
              _valgteEnheter(), felter['nytt-hastegrad'].value, felter['nytt-lokasjon'].value,
              felter['nytt-problemstilling'].value, felter['nytt-fritekst'].value,
              felter['nytt-antall'].value, globalThis.sisteFyll]));
        """)
        self.assertEqual(ut.strip().splitlines()[0],
                         '[[],"Akutt","10","Udefinert","","",["Akutt","Udefinert"]]')


class EnhetsskjermJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (OPPDRAG_ENHET_JS, ('renderAvsluttet', '_problemMedAntall', '_udefinertVarsel',
                            'koLes', 'koSkriv', 'koFjern', 'koNokkel', 'synk')),
    )
    STUBB = (
        "globalThis.localStorage = (() => { const m = {}; return {"
        "getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },"
        "removeItem: (k) => { delete m[k]; } }; })();\n"
        "globalThis.window = { ENHET_ID: 5 };\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_nylig_avsluttet_baerer_nummeret(self):
        ut = run_node(self.harness, """
            const seksjon = { classList: { add() {}, remove() {} } };
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: (id) => id === 'avsluttet-liste' ? el : seksjon };
            globalThis.mineOppdrag = [{ id: 1, nummer: 12, status: 'ledig', problemstilling: 'Fallskade',
              statusmeldinger: [{status: 'ledig', tidspunkt: '2026-09-12T10:00:00Z', automatisk: false}] }];
            renderAvsluttet();
            console.log(el.innerHTML);
        """)
        self.assertIn('#12', ut)
        self.assertIn('Fallskade', ut)

    def test_udefinert_varsles_paa_kortet_foer_bilen_trykker(self):
        ut = run_node(self.harness, """
            console.log(_udefinertVarsel({problemstilling: 'Udefinert'}));
            console.log('---');
            console.log(JSON.stringify(_udefinertVarsel({problemstilling: 'Fallskade'})));
        """)
        med, uten = ut.split('---')
        self.assertIn('Meld problemstillingen til KO', med)
        self.assertEqual(uten.strip().splitlines()[0], '""')

    def test_avvisningen_blir_staaende_naar_koen_er_tom(self):
        # Serveren strøk raden med en beskjed; at køen da er tom er ikke
        # grunn til å skjule beskjeden.
        ut = run_node(self.harness, self.STUBB + """
            koSkriv([{nokkel: 'k1', oppdragId: 7, overgang: 'ledig', sted: null, klienttid: 'x'}]);
            const logg = [];
            globalThis.apiFetch = async () => ({ ok: false, status: 400,
              json: async () => ({ status: 'error', message: 'Meld problemstillingen til KO' }) });
            globalThis.synkerNaa = false; globalThis.etagMine = null;
            globalThis.skjulFeil = () => logg.push('skjul');
            globalThis.visFeil = (m) => logg.push('feil:' + m);
            globalThis.visUsendt = () => logg.push('usendt');
            globalThis.lastMine = async () => {};
            await synk();
            console.log(JSON.stringify(logg));
            console.log(koLes().length);
            // Går alt gjennom, skjules gammel feil som før.
            koSkriv([{nokkel: 'k2', oppdragId: 7, overgang: 'fremme', sted: null, klienttid: 'x'}]);
            globalThis.apiFetch = async () => ({ ok: true });
            logg.length = 0;
            await synk();
            console.log(JSON.stringify(logg));
        """)
        linjer = ut.strip().splitlines()
        self.assertEqual(linjer[0], '["feil:Meld problemstillingen til KO"]')
        self.assertEqual(linjer[1], '0', 'raden er strøket')
        self.assertEqual(linjer[2], '["skjul"]')
