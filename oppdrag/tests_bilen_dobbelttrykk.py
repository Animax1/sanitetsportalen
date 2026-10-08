"""Bilens stemplingsknapp tåler et dobbelttrykk (27. sep. 2026).

André fikk «Oppdraget står i Leverer — skjermen er oppdatert» i en rød boks midt
i en vanlig kjøring. `_stemple` tegnet skjermen på nytt før sendingen var ferdig,
med den gamle projeksjonen: knappen sto med *samme* tekst og uten låsen, så et
nytt trykk sendte samme overgang én gang til, og serveren svarte 409.

Prøvd gjennom den ekte inngangen, `_stemple`, med en treg server.
"""
import json
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import INNLOGGET, INNLOGGET_STUBB
from patients.js_test_utils import OPPDRAG_ENHET_JS, build_harness, node_available, run_node

from .tests_runde_d import _konst

HARNESS = (INNLOGGET, (OPPDRAG_ENHET_JS, ('lagNokkel', 'koNokkel', 'koLes', 'koSkriv', 'koLeggTil',
                               'koFjern', 'projiser', 'synk', '_stemple',
                               # `_stemple` legger posisjonen i køraden (30. sep. 2026).
                               'posisjonTilKo', 'kartKoblingAktiv', 'delerPosisjon',
                               'delPosisjonNokkel', 'posisjonForStempling',
                               'posisjonMaksAlderMs',
                               # og posisjonsdelingen (4. okt. 2026)
                               'posisjonsdelingTilstand', 'erPaVakt', 'paVaktNokkel')),)

FORSPILL = _konst(OPPDRAG_ENHET_JS, 'STEMPEL_LAAS_MS') + """
globalThis.localStorage = (() => { const m = {}; return {
  getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
  removeItem: (k) => { delete m[k]; } }; })();
globalThis.window = { ENHET_ID: 5 };
globalThis.OPPDRAG_NESTE = { avreist: 'leverer', leverer: 'ledig' };
globalThis.OPPDRAG_STATUSNAVN = { leverer: 'Leverer', ledig: 'Ledig' };
let mineOppdrag = [{ id: 7, status: 'avreist', neste_overgang: 'leverer', neste_navn: 'Leverer' }];
let stemplingPaagaar = false; let synkerNaa = false; let etagMine = null;
const sendt = []; const feil = []; const tegnet = [];
let svar = { ok: true };
function renderAlt() { tegnet.push(mineOppdrag[0].neste_overgang); }
function visFeil(m) { feil.push(m); }
function skjulFeil() { feil.push('skjult'); }
function visUsendt() {}
async function lastMine() {}
globalThis.apiFetch = (url) => new Promise((ok) => {
  sendt.push(url); setTimeout(() => ok(svar), 50); });
"""


def _kjor(kode):
    ut = run_node(INNLOGGET_STUBB + build_harness(HARNESS), '(async () => {\n' + kode + '\n})();', preamble=FORSPILL)
    return [json.loads(l) for l in ut.splitlines() if l != 'OK']


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class DobbelttrykkTests(SimpleTestCase):

    def test_to_raske_trykk_gir_en_sending(self):
        (ut,) = _kjor("""
            const a = _stemple(7, 'leverer', 'stemple-neste-7');
            const b = _stemple(7, 'leverer', 'stemple-neste-7');
            await Promise.all([a, b]);
            console.log(JSON.stringify({ sendt, ko: koLes().length }));
        """)
        self.assertEqual(len(ut['sendt']), 1, ut)
        self.assertEqual(ut['ko'], 0)

    def test_skjermen_viser_neste_steg_med_en_gang(self):
        """Første tegning etter trykket skal si «Ledig», ikke «Leverer»."""
        (ut,) = _kjor("""
            await _stemple(7, 'leverer', 'stemple-neste-7');
            console.log(JSON.stringify(tegnet));
        """)
        self.assertEqual(ut[0], 'ledig', ut)

    def test_etter_laasen_gaar_neste_trykk_gjennom(self):
        (ut,) = _kjor("""
            await _stemple(7, 'leverer', 'stemple-neste-7');
            await _stemple(7, 'ledig', 'stemple-neste-7');
            console.log(JSON.stringify(sendt.map((u) => u.split('/status/')[1])));
        """)
        self.assertEqual(ut, ['leverer/', 'ledig/'])

    def test_409_gir_ingen_rod_boks(self):
        """Oppdraget har gått videre; skjermen hentes på nytt uansett."""
        (ut,) = _kjor("""
            svar = { ok: false, status: 409,
                     json: async () => ({ message: 'Oppdraget står i Leverer — skjermen er oppdatert.' }) };
            await _stemple(7, 'leverer', 'stemple-neste-7');
            console.log(JSON.stringify({ feil, ko: koLes().length }));
        """)
        self.assertEqual(ut['feil'], ['skjult'])
        self.assertEqual(ut['ko'], 0)

    def test_400_vises_fortsatt(self):
        """«Udefinert» og grovsortering er beskjeder bilen kan handle på."""
        (ut,) = _kjor("""
            svar = { ok: false, status: 400,
                     json: async () => ({ message: 'Meld problemstillingen til KO' }) };
            await _stemple(7, 'ledig', 'stemple-neste-7');
            console.log(JSON.stringify(feil));
        """)
        self.assertEqual(ut, ['Meld problemstillingen til KO'])


GRAA_HARNESS = ((OPPDRAG_ENHET_JS, ('renderAlt', 'laasStempelknapper')),)

GRAA_FORSPILL = """
let stemplingPaagaar = false; let knapper = [];
function renderAktivt() {
  // Hver tegning lager nye knapper, som i bilen.
  knapper = [{ action: 'stempleNeste', disabled: false }, { action: 'grov', disabled: false }];
}
function renderVentende() {} function renderAvsluttet() {} function visUsendt() {}
function klokke() { return ''; }
globalThis.document = {
  getElementById: () => null,
  querySelectorAll: (sel) => knapper.filter((k) => k.action.startsWith('stemple')).map((k) => ({
    set disabled(v) { k.disabled = v; } })),
};
"""


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KnappeneErGraaMensDetSendesTests(SimpleTestCase):
    """Gjennom den ekte `renderAlt`: kallstedet er regelen, ikke hjelperen."""

    def _tegn(self, paagaar):
        kode = f"""
            stemplingPaagaar = {'true' if paagaar else 'false'};
            renderAlt();
            console.log(JSON.stringify(knapper.map((k) => k.disabled)));
        """
        ut = run_node(build_harness(GRAA_HARNESS), kode, preamble=GRAA_FORSPILL)
        return json.loads(ut.splitlines()[0])

    def test_nye_knapper_er_laast_mens_et_trykk_sendes(self):
        self.assertEqual(self._tegn(True), [True, False])

    def test_ingen_laas_ellers(self):
        self.assertEqual(self._tegn(False), [False, False])
