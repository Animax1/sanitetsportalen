"""«Deling med biler: Popper opp oppdragsvindu ved deling av loggføring i hendelse til biler.»
(Feilmelding fra André, 20. okt. 2026.)

`_koDeling()` tegner detaljvinduet på nytt når et oppdrag *står åpent* — riktig når «Del med
<enhet>» trykkes inne i vinduet. Men `apentOppdragId` ble aldri satt tilbake når vinduet ble
lukket. Hadde operatøren sett på ett oppdrag én gang, åpnet hvert senere «Del» eller «Angre» i
en hendelse det oppdraget igjen. Det samme gjorde «Knytt» på det oppdraget fra hendelsen.

Prøvene kjører den ekte toppnivåkoden i `oppdrag-sentral-lasting.js`, der lytteren registreres,
og fyrer lukkingen gjennom den. Forsvinner kallstedet, blir de røde.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from patients.js_test_utils import (
    JS_DIR, KO_JS, OPPDRAG_SENTRAL_JS, build_harness, extract_function, read_js, run_node,
)

LASTING_JS = JS_DIR / 'oppdrag-sentral-lasting.js'

#: Det lasting.js rører på toppnivå, pluss det `_koDeling` kaller. Detaljvinduet
#: husker lytterne sine, så prøven kan lukke det slik Bootstrap gjør.
DOM = """
const lyttere = {};
const detaljvindu = { addEventListener: (navn, fn) => { (lyttere[navn] ||= []).push(fn); } };
globalThis.document = {
  addEventListener: () => {},
  getElementById: (id) => (id === 'oppdragDetaljModal' ? detaljvindu : null),
};
function lukkDetaljvinduet() { (lyttere['hide.bs.modal'] || []).forEach((fn) => fn({})); }
function nullstillNyttOppdrag() {}
function nullstillModalVedLukking() {}
let apentOppdragId = null;
const vist = [];
async function visOppdrag(id) { apentOppdragId = id; vist.push(id); }
globalThis.apiFetch = async () => ({ ok: true, json: async () => ({ data: { rot: 1 } }) });
const koLinjer = new Map();
async function koHentLogg() {}
function koHentOppdragPaaNytt() {}
"""


class DelingAapnerIkkeOppdragsvindetTests(SimpleTestCase):

    def setUp(self):
        self.harness = '\n\n'.join([
            extract_function(read_js(OPPDRAG_SENTRAL_JS), 'glemApentOppdrag'),
            build_harness(((KO_JS, ('_koDeling',)),)),
            # Hele fila: toppnivået er det som skal prøves, og resten er funksjoner.
            read_js(LASTING_JS),
        ])

    def _kjor(self, kode):
        return run_node(self.harness, kode, preamble=DOM).splitlines()[0]

    def test_del_etter_at_vinduet_er_lukket_aapner_ingenting(self):
        """Feilen slik André så den: se på O12, lukk, del en linje i en hendelse."""
        self.assertEqual(self._kjor("""
            await visOppdrag(12);
            lukkDetaljvinduet();
            vist.length = 0;
            await _koDeling('del', 5);
            await _koDeling('angre-deling', 5);
            console.log(JSON.stringify([vist, apentOppdragId]));
        """), '[[],null]')

    def test_del_med_enhet_inne_i_aapent_vindu_tegner_det_paa_nytt(self):
        """Grunnen til at kallet finnes: «Del med HGSD 56» inne i vinduet skal vises der."""
        self.assertEqual(self._kjor("""
            await visOppdrag(12);
            vist.length = 0;
            await _koDeling('del', 5, 12);
            console.log(JSON.stringify(vist));
        """), '[12]')
