"""Offline-køen på enhetsskjermen (fase 5).

Kjøres i node, ikke grep-et: `patients/js_test_utils.py` laster funksjonene og
kaller dem. Det som testes er oppførselen mannskapet er avhengig av — at et
trykk uten dekning ikke forsvinner, og at det som ligger usendt vises på
skjermen i stedet for å se ut som om det gikk gjennom.
"""
from django.test import SimpleTestCase

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node,
)

#: Et minimalt `localStorage`, slik at køen kan kjøres utenfor en nettleser.
#: `crypto.randomUUID` stubbes ikke — node har den innebygd, og globalen er
#: skrivebeskyttet fra node 19. Nøklene blir derfor ekte tilfeldige, og
#: testene under sammenligner dem aldri mot en fast verdi.
FORSPILL = '''
globalThis.localStorage = {
  _d: {},
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};
globalThis.OPPDRAG_NESTE = {
  venter: 'rykker_ut', rykker_ut: 'fremme', fremme: 'avreist',
  avreist: 'leverer', leverer: null, ledig: null,
};
globalThis.OPPDRAG_STATUSNAVN = {
  venter: 'Venter', rykker_ut: 'Rykker ut', fremme: 'Fremme',
  avreist: 'Avreist', leverer: 'Leverer', ledig: 'Ledig',
};
'''

HARNESS = (
    (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml',
                       'klokke')),
    (OPPDRAG_ENHET_JS, ('koNokkel', 'koLes', 'koSkriv', 'koLeggTil', 'koFjern',
                        'lagNokkel', 'projiser')),
)


class OfflineKoTests(SimpleTestCase):
    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(HARNESS)

    def _kjor(self, snippet):
        return run_node(self.harness, FORSPILL + snippet)

    # ── Køen som lager ──────────────────────────────────────────────────────

    def test_trykk_overlever_i_localstorage(self):
        """Poenget med hele fasen: trykket skal ikke forsvinne uten dekning."""
        ut = self._kjor('''
            koLeggTil(7, 'rykker_ut');
            const ko = koLes();
            console.log(JSON.stringify([ko.length, ko[0].oppdragId, ko[0].overgang]));
        ''')
        self.assertIn('[1,7,"rykker_ut"]', ut.replace(' ', ''))

    def test_noekkelen_lages_ved_trykket_og_staar_fast(self):
        """Den er det som gjør avspilling trygg — den må ikke lages på nytt."""
        ut = self._kjor('''
            const rad = koLeggTil(7, 'rykker_ut');
            const fra_ko = koLes()[0];
            console.log(JSON.stringify([rad.nokkel === fra_ko.nokkel,
                                        rad.nokkel.length >= 8]));
        ''')
        self.assertIn('[true,true]', ut.replace(' ', ''))

    def test_klienttiden_fryses_ved_trykket(self):
        ut = self._kjor('''
            const rad = koLeggTil(7, 'rykker_ut');
            console.log(typeof rad.klienttid === 'string'
                        && !Number.isNaN(Date.parse(rad.klienttid)));
        ''')
        self.assertIn('true', ut)

    def test_flere_trykk_beholder_rekkefoelgen(self):
        """Statusmeldinger er et spor. «Avreist» før «Fremme» ville løyet."""
        ut = self._kjor('''
            koLeggTil(7, 'rykker_ut');
            koLeggTil(7, 'fremme');
            koLeggTil(7, 'avreist');
            console.log(JSON.stringify(koLes().map((r) => r.overgang)));
        ''')
        self.assertIn('["rykker_ut","fremme","avreist"]', ut.replace(' ', ''))

    def test_fjerning_treffer_kun_egen_rad(self):
        ut = self._kjor('''
            const a = koLeggTil(7, 'rykker_ut');
            koLeggTil(8, 'rykker_ut');
            koFjern(a.nokkel);
            console.log(JSON.stringify(koLes().map((r) => r.oppdragId)));
        ''')
        self.assertIn('[8]', ut.replace(' ', ''))

    def test_uleselig_ko_gir_tom_ko_i_stedet_for_krasj(self):
        """Skjermen skal virke også når lagringen er blokkert eller rar."""
        ut = self._kjor('''
            localStorage.setItem(koNokkel(), 'ikke json');
            console.log(JSON.stringify(koLes()));
            localStorage.setItem(koNokkel(), '{"ikke":"liste"}');
            console.log(JSON.stringify(koLes()));
        ''')
        self.assertEqual(ut.split()[:2], ['[]', '[]'])

    # ── Projeksjonen ────────────────────────────────────────────────────────

    def test_usendt_trykk_vises_paa_skjermen(self):
        """Uten dette ville neste poll visket ut trykket mannskapet nettopp gjorde."""
        ut = self._kjor('''
            const fra_server = [{ id: 7, status: 'venter', status_navn: 'Venter',
                                  neste_overgang: 'rykker_ut', neste_navn: 'Rykker ut' }];
            koLeggTil(7, 'rykker_ut');
            const vist = projiser(fra_server, koLes());
            console.log(JSON.stringify([vist[0].status, vist[0].status_navn,
                                        vist[0].usendt]));
        ''')
        self.assertIn('["rykker_ut","Rykkerut",true]', ut.replace(' ', ''))

    def test_neste_knapp_peker_videre_i_kjeden(self):
        """Ellers dør knappen ved første trykk uten dekning, og køen er halvveis."""
        ut = self._kjor('''
            const fra_server = [{ id: 7, status: 'venter', status_navn: 'Venter',
                                  neste_overgang: 'rykker_ut', neste_navn: 'Rykker ut' }];
            koLeggTil(7, 'rykker_ut');
            const vist = projiser(fra_server, koLes());
            console.log(JSON.stringify([vist[0].neste_overgang, vist[0].neste_navn]));
        ''')
        self.assertIn('["fremme","Fremme"]', ut.replace(' ', ''))

    def test_flere_usendte_trykk_viser_det_siste(self):
        ut = self._kjor('''
            const fra_server = [{ id: 7, status: 'venter', status_navn: 'Venter' }];
            koLeggTil(7, 'rykker_ut');
            koLeggTil(7, 'fremme');
            const vist = projiser(fra_server, koLes());
            console.log(JSON.stringify([vist[0].status, vist[0].neste_overgang]));
        ''')
        self.assertIn('["fremme","avreist"]', ut.replace(' ', ''))

    def test_oppdrag_uten_usendt_er_uroert(self):
        ut = self._kjor('''
            const fra_server = [{ id: 7, status: 'fremme', status_navn: 'Fremme' },
                                { id: 8, status: 'venter', status_navn: 'Venter' }];
            koLeggTil(8, 'rykker_ut');
            const vist = projiser(fra_server, koLes());
            console.log(JSON.stringify([vist[0].status, vist[0].usendt === undefined,
                                        vist[1].status]));
        ''')
        self.assertIn('["fremme",true,"rykker_ut"]', ut.replace(' ', ''))

    def test_terminal_status_gir_ingen_neste_knapp(self):
        ut = self._kjor('''
            const fra_server = [{ id: 7, status: 'avreist', status_navn: 'Avreist' }];
            koLeggTil(7, 'leverer');
            const vist = projiser(fra_server, koLes());
            console.log(JSON.stringify([vist[0].status, vist[0].neste_overgang]));
        ''')
        self.assertIn('["leverer",null]', ut.replace(' ', ''))

    def test_uten_kjede_faller_projeksjonen_tilbake_uten_aa_kaste(self):
        """Lastes ikke kjeden, skal skjermen fortsatt virke — «Ledig» holder."""
        ut = self._kjor('''
            delete globalThis.OPPDRAG_NESTE;
            const fra_server = [{ id: 7, status: 'venter', status_navn: 'Venter' }];
            koLeggTil(7, 'rykker_ut');
            const vist = projiser(fra_server, koLes());
            console.log(JSON.stringify([vist[0].status, vist[0].neste_overgang]));
        ''')
        self.assertIn('["rykker_ut",null]', ut.replace(' ', ''))
