"""Prodtestfunnene 13. sep. 2026, oppdragsmodulen.

Kjøres i node (`patients/js_test_utils.py`), ikke grep-et.

- 3.1: første besøk på `/oppdrag/` sto med tomme «Laster…»-felt. Oppstarten
  var fire kall på rad uten feilhåndtering.
- 3.4: «venter på dekning» kom opp i det halve sekundet sendingen tok.
"""
import json
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_offline_ko import FORSPILL
from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
    node_available, read_js, run_node,
)


class SentralbordetsOppstartTests(SimpleTestCase):
    """3.1: listene tegnes uansett hvordan første henting gikk, og pollingen
    settes selv om oppstarten kastet."""

    HARNESS = ((OPPDRAG_SENTRAL_JS, ('_trygt', 'lastAlt', 'oppstart', '_visLastefeil', 'lastEnheter',
                                     'lastOppdrag', 'renderEnheter', 'tegnEnhetsliste',
                                     'settEnhetslisteKilde', 'renderOppdrag', '_oppdragRadHtml', 'oppdragsnr', 'hendelsesnr')),)

    FORSPILL = '''
    let enheter = []; let oppdragsliste = []; let lokasjoner = [];
    let etagEnheter = null; let etagOppdrag = null;
    let enheterHentet = false; let oppdragHentet = false;
    let besetninger = {}; let apenBesetning = null;
    let sisteEnhetsliste = []; let enhetslisteKilde = null;
    const elementer = {};
    globalThis.document = {
      getElementById: (id) => (elementer[id] ||= { innerHTML: '<div class="tom-melding">Laster…</div>', textContent: '' }),
    };
    globalThis.fyllNedtrekk = () => {};
    globalThis.visManglendeOppsett = () => {};
    globalThis.lastLokasjoner = async () => { throw new Error('nede'); };
    globalThis._grupperEnheter = (l) => [{ navn: '', enheter: l }];
    globalThis._enhetskort = (e) => `<div class="enhet">${e.navn}</div>`;
    globalThis._sorterOppdrag = (l) => l;
    globalThis.escapeHtml = (s) => String(s);
    let nettet = 'nede';
    globalThis.apiFetch = async (url) => {
      if (nettet === 'nede') throw new TypeError('Failed to fetch');
      if (nettet === '500') return { ok: false, status: 500, headers: { get: () => null } };
      const data = url.includes('enheter') ? [{ id: 1, navn: 'Bil A', pa_vakt: true }] : [];
      return { ok: true, status: 200, headers: { get: () => '"e"' }, json: async () => ({ data }) };
    };
    '''

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = _konst(OPPDRAG_SENTRAL_JS, 'LASTEFEIL') + build_harness(self.HARNESS)

    def _kjor(self, snippet):
        ut = run_node(self.harness, self.FORSPILL + snippet)
        return json.loads(ut.strip().splitlines()[-1])

    def test_uten_nett_sier_listene_fra_i_stedet_for_laster(self):
        ut = self._kjor('''
            (async () => {
              await oppstart();
              console.log(JSON.stringify([
                elementer.enhetsliste.innerHTML.includes('prøver igjen'),
                elementer.oppdragsliste.innerHTML.includes('prøver igjen'),
                elementer.enhetsliste.innerHTML.includes('Laster'),
              ]));
            })();
        ''')
        self.assertEqual(ut, [True, True, False])

    def test_serverfeil_gir_samme_melding_ikke_ingen_enheter(self):
        """`!res.ok` ga tidligere stille `false` — og «Ingen enheter på vakt»
        hadde vært en løgn: de er ikke hentet."""
        ut = self._kjor('''
            (async () => {
              nettet = '500';
              await oppstart();
              console.log(JSON.stringify([
                elementer.enhetsliste.innerHTML.includes('prøver igjen'),
                elementer.enhetsliste.innerHTML.includes('Ingen enheter'),
              ]));
            })();
        ''')
        self.assertEqual(ut, [True, False])

    def test_neste_poll_retter_det_opp(self):
        ut = self._kjor('''
            (async () => {
              await oppstart();
              nettet = 'oppe';
              await lastAlt();
              console.log(JSON.stringify([
                elementer.enhetsliste.innerHTML.includes('Bil A'),
                elementer.oppdragsliste.innerHTML.includes('Ingen oppdrag'),
                enheterHentet, oppdragHentet,
              ]));
            })();
        ''')
        self.assertEqual(ut, [True, True, True, True])

    def test_oppstarten_kaster_ikke_naar_lokasjonene_feiler(self):
        """Lokasjonene hentes først. Feilet de, kom ingen av de andre kallene
        — og pollingen som skulle rettet det opp ble aldri satt."""
        ut = self._kjor('''
            (async () => {
              nettet = 'oppe';
              let feil = null;
              try { await oppstart(); } catch (e) { feil = e.message; }
              console.log(JSON.stringify([feil, elementer.enhetsliste.innerHTML.includes('Bil A')]));
            })();
        ''')
        self.assertEqual(ut, [None, True])

    def test_domcontentloaded_setter_pollingen_i_finally(self):
        """Den delen kan ikke kjøres i node uten DOM — men regelen er at
        `setInterval` står i `finally`, og den leses her."""
        src = read_js(OPPDRAG_SENTRAL_JS)
        start = src.index("document.addEventListener('DOMContentLoaded'")
        blokk = src[start:src.index('});', start)]
        self.assertIn('try {', blokk)
        self.assertIn('await oppstart();', blokk)
        self.assertIn('} finally {', blokk)
        self.assertLess(blokk.index('} finally {'), blokk.index('setInterval(lastAlt, 30000)'))
        # Minuttegningen skriver ikke over LASTEFEIL.
        self.assertIn('if (oppdragHentet) renderOppdrag();', blokk)
        self.assertIn('if (enheterHentet) renderEnheter();', blokk)


class VenterPaaDekningTests(SimpleTestCase):
    """3.4: meldingen venter tre sekunder på at sendingen skal lykkes."""

    HARNESS = ((OPPDRAG_ENHET_JS, ('koNokkel', 'koLes', 'koSkriv', 'koLeggTil', 'koFjern', 'lagNokkel',
                                   'usendtAlder', 'visUsendt')),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = (_konst(OPPDRAG_ENHET_JS, 'USENDT_VENTETID_MS') + 'let usendtTimer = null;\n'
                        + build_harness(self.HARNESS))

    DOM = '''
    const klasser = new Set(['d-none']);
    const el = { textContent: '', classList: { add: (k) => klasser.add(k), remove: (k) => klasser.delete(k) } };
    globalThis.document = { getElementById: (id) => id === 'enhet-usendt' ? el : null };
    const timere = [];
    globalThis.setTimeout = (fn, ms) => { timere.push({ fn, ms }); return timere.length; };
    globalThis.clearTimeout = (id) => { if (id) timere[id - 1].avlyst = true; };
    const synlig = () => !klasser.has('d-none');
    '''

    def _kjor(self, snippet):
        # Synkront: svaret står på første linje, harnessens «OK» på siste.
        ut = run_node(self.harness, FORSPILL + self.DOM + snippet)
        return json.loads(ut.strip().splitlines()[0])

    def test_alderen_er_eldste_rad(self):
        ut = self._kjor('''
            const naa = Date.parse('2026-09-13T20:00:10Z');
            console.log(JSON.stringify([
              usendtAlder([], naa),
              usendtAlder([{ klienttid: '2026-09-13T20:00:09Z' }], naa),
              usendtAlder([{ klienttid: '2026-09-13T20:00:09Z' }, { klienttid: '2026-09-13T20:00:00Z' }], naa),
              usendtAlder([{ klienttid: 'tull' }], naa) === Infinity,
            ]));
        ''')
        self.assertEqual(ut, [0, 1000, 10000, True])

    def test_et_ferskt_trykk_viser_ingenting_men_setter_en_timer(self):
        ut = self._kjor('''
            koLeggTil(7, 'rykker_ut');
            visUsendt();
            console.log(JSON.stringify([synlig(), timere.length, timere[0].ms > 2500 && timere[0].ms <= 3000]));
        ''')
        self.assertEqual(ut, [False, 1, True])

    def test_gaar_koen_tom_foer_fristen_avlyses_timeren(self):
        ut = self._kjor('''
            const rad = koLeggTil(7, 'rykker_ut');
            visUsendt();
            koFjern(rad.nokkel);
            visUsendt();
            console.log(JSON.stringify([synlig(), timere[0].avlyst === true, el.textContent]));
        ''')
        self.assertEqual(ut, [False, True, ''])

    def test_etter_fristen_vises_meldingen(self):
        ut = self._kjor('''
            const ko = [{ nokkel: 'a', oppdragId: 7, overgang: 'rykker_ut', sted: null,
                          klienttid: new Date(Date.now() - 5000).toISOString() }];
            koSkriv(ko);
            visUsendt();
            console.log(JSON.stringify([synlig(), el.textContent, timere.length]));
        ''')
        self.assertEqual(ut, [True, '1 stempling venter på dekning — den sendes av seg selv.', 0])

    def test_timeren_viser_meldingen_naar_den_fyrer(self):
        ut = self._kjor('''
            koLeggTil(7, 'rykker_ut');
            visUsendt();
            const foer = synlig();
            // Fristen går ut: la klokka gå, og fyr timeren slik nettleseren ville.
            const ekte = Date.now; Date.now = () => ekte() + 3100;
            timere[0].fn();
            console.log(JSON.stringify([foer, synlig()]));
        ''')
        self.assertEqual(ut, [False, True])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class DenDelteListaLeserDenLevendeEnhetslistaTests(SimpleTestCase):
    """`lastEnheter()` bytter ut `enheter` med en **ny** array uten å tegne.

    Da ressurslista ble delt med `/ko/` (18. sep. 2026) husket den delte koden
    den sist tegnede lista i stedet for å spørre sida. En besetning som ble
    hentet i vinduet mellom bytte og tegning ville da tegnet forrige rundes
    enheter. Vinduet var kort og rettet seg selv — men forskjellen var ekte, og
    før delingen leste `renderEnheter()` alltid den levende `enheter`.

    Prøven går gjennom `tegnEnhetslistePaaNytt()`, som er veien
    `hentBesetning()` faktisk bruker.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (OPPDRAG_SENTRAL_JS, ('renderEnheter', 'tegnEnhetsliste',
                              'tegnEnhetslistePaaNytt',
                              'settEnhetslisteKilde', '_grupperEnheter',
                              '_typeRekkefolge', '_enhetskort',
                              'enhetskortInnmat', 'kanSeBesetning',
                              'mkBesetning', '_besetningKontakt', 'tidSiden',
                              'hastegradKlasse', '_grovMerke',
                              '_problemMedAntall', '_medAntall')),
    )

    def setUp(self):
        self.harness = build_harness(self.HARNESS)

    def test_ny_array_naas_uten_en_tegning_imellom(self):
        """**Gjennom `renderEnheter()`, ikke ved å sette kilden selv.**

        Første utgave av denne testen kalte `settEnhetslisteKilde()` direkte,
        og da kunne sentralbordet slutte å melde inn kilden uten at noe ble
        rødt — mutantløgn nummer tre i `CLAUDE.md`. Innmeldingen ligger derfor
        nå *i* `renderEnheter()`, som er den ekte inngangen.
        """
        ut = run_node(self.harness, """
            let enheter = [{id: 1, navn: 'Gammel bil', pa_vakt: true,
                            status: 'ledig', status_navn: 'Ledig',
                            antall_ventende: 0}];
            renderEnheter();

            // Det `lastEnheter()` gjør: bytter ut arrayen, tegner ikke.
            enheter = [{id: 2, navn: 'Ny bil', pa_vakt: true,
                        status: 'ledig', status_navn: 'Ledig',
                        antall_ventende: 0}];

            // Det `hentBesetning()` gjør når svaret kommer.
            tegnEnhetslistePaaNytt();
            console.log(document.getElementById('enhetsliste').innerHTML);
        """, preamble=self.DOM_STUBB)
        self.assertIn('Ny bil', ut,
                      'den delte lista tegnet forrige rundes enheter')
        self.assertNotIn('Gammel bil', ut)

    def test_uten_en_kilde_brukes_den_sist_tegnede(self):
        """`/ko/` melder ingen kilde — den henter og tegner i samme kall, og
        har ingen levende liste å spørre etter."""
        ut = run_node(self.harness, """
            settEnhetslisteKilde(null);
            tegnEnhetsliste([{id: 1, navn: 'Fra KO', pa_vakt: true,
                              status: 'ledig', status_navn: 'Ledig',
                              antall_ventende: 0}]);
            tegnEnhetslistePaaNytt();
            console.log(document.getElementById('enhetsliste').innerHTML);
        """, preamble=self.DOM_STUBB)
        self.assertIn('Fra KO', ut)

    # `build_harness` plukker ut funksjoner, ikke modulnivå-variablene de
    # lukker over — de må derfor erklæres her, som i de andre harnessene i
    # denne fila.
    DOM_STUBB = """
        globalThis.window = { KAN_SE_BESETNING: false, OPPDRAG_ENHETSTYPER: [] };
        globalThis.apenBesetning = null;
        globalThis.besetninger = {};
        let enhetslisteKilde = null;
        let sisteEnhetsliste = [];
        const _noder = {};
        globalThis.document = {
          getElementById: (id) => (_noder[id] ||= { innerHTML: '', textContent: '' }),
        };
    """
