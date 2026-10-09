"""Bilskjermen holdes våken med Screen Wake Lock (9. okt. 2026).

André: telefonen står i holderen gjennom vakta, og **skjermen sovner** — da
stopper pollingen og lydvarselet, og bilen hører ikke det nye oppdraget.

Testene går gjennom de ekte hendelsene (`pointerdown`, `visibilitychange`) mot
`startVaakenLaas()`, og én kjører selve `DOMContentLoaded`-kroken fra fila: en
test som bare kalte `hentVaakenLaas()` ville gått grønn om lytteren forsvant —
og det er nettopp lytteren som gjør at låsen kommer tilbake etter en
telefonsamtale.
"""
import json

from django.test import SimpleTestCase

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, build_harness, node_available, read_js, run_node,
)

FUNKSJONER = ('skjermSkalHoldesVaaken', 'vaakenTekst', 'tegnVaaken',
              'hentVaakenLaas', 'startVaakenLaas')

#: Et DOM med lyttere man kan fyre, linja låsen skriver i, og en `wakeLock`
#: som teller forespørslene og kan avvise som iOS i strømsparing.
OPPSETT = """
globalThis.vaakenLaas = null; globalThis.vaakenStatus = 'ukjent'; globalThis.vaakenTrykket = false;
const lyttere = {};
const linje = { textContent: '', klasser: new Set(),
  classList: { toggle(k, paa) { paa ? linje.klasser.add(k) : linje.klasser.delete(k); } } };
globalThis.document = {
  visibilityState: 'visible',
  addEventListener(navn, fn) { (lyttere[navn] = lyttere[navn] || []).push(fn); },
  getElementById(id) { return id === 'vaaken-linje' ? linje : null; },
};
async function fyr(navn) { for (const fn of (lyttere[navn] || [])) await fn(); await new Promise(r => setTimeout(r, 0)); }
let foresporsler = 0; let avvis = null; let sluppet = null;
// Node 22 har en egen `navigator` med bare getter — byttes ut, ikke tilordnes.
function settNavigator(v) {
  Object.defineProperty(globalThis, 'navigator', { value: v, configurable: true, writable: true });
}
settNavigator({ wakeLock: { request: async (type) => {
  foresporsler += 1;
  if (type !== 'screen') throw new Error('feil type');
  if (avvis) { const e = new Error('avvist'); e.name = avvis; throw e; }
  return { addEventListener(navn, fn) { if (navn === 'release') sluppet = fn; } };
} } });
const tilstand = () => ({ status: vaakenStatus, foresporsler, tekst: linje.textContent,
  problem: linje.klasser.has('vaaken-problem'), skjult: linje.klasser.has('d-none') });
"""


class WakeLockTests(SimpleTestCase):

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(((OPPDRAG_ENHET_JS, FUNKSJONER),))

    def _kjor(self, kode):
        ut = run_node(self.harness, '(async () => {\n' + kode + '\n})();', preamble=OPPSETT)
        return [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']

    def test_regelen(self):
        (ut,) = self._kjor("""
            console.log(JSON.stringify([
              skjermSkalHoldesVaaken(true, true, false),
              skjermSkalHoldesVaaken(false, true, false),   // skjult side
              skjermSkalHoldesVaaken(true, false, false),   // ingen har trykket
              skjermSkalHoldesVaaken(true, true, true),     // holder alt
            ]));
        """)
        self.assertEqual(ut, [True, False, False, False])

    def test_ingenting_foer_foerste_trykk_saa_holder_den(self):
        ut = self._kjor("""
            startVaakenLaas();
            await fyr('visibilitychange');
            console.log(JSON.stringify(tilstand()));
            await fyr('pointerdown');
            console.log(JSON.stringify(tilstand()));
            await fyr('pointerdown');                   // holder alt: ingen ny forespørsel
            console.log(JSON.stringify(tilstand()));
        """)
        self.assertEqual(ut[0]['foresporsler'], 0, 'ingen forespørsel uten et trykk')
        self.assertEqual(ut[1], {'status': 'holder', 'foresporsler': 1,
                                 'tekst': 'Skjermen holdes våken', 'problem': False,
                                 'skjult': False})
        self.assertEqual(ut[2]['foresporsler'], 1)

    def test_hentes_paa_nytt_naar_siden_synes_igjen(self):
        """Den vanlige feilen med API-et: det virker ved første test og ikke
        etter første telefonsamtale."""
        ut = self._kjor("""
            startVaakenLaas();
            await fyr('pointerdown');
            document.visibilityState = 'hidden';
            sluppet();                                  // nettleseren slipper låsen
            await fyr('visibilitychange');              // skjult: ingen forespørsel
            console.log(JSON.stringify(tilstand()));
            document.visibilityState = 'visible';
            await fyr('visibilitychange');              // tilbake: hentes på nytt
            console.log(JSON.stringify(tilstand()));
        """)
        self.assertEqual((ut[0]['status'], ut[0]['foresporsler']), ('sluppet', 1))
        self.assertEqual((ut[1]['status'], ut[1]['foresporsler']), ('holder', 2))

    def test_avslaget_i_stroemsparing_synes_og_kaster_ikke(self):
        ut = self._kjor("""
            avvis = 'NotAllowedError';
            startVaakenLaas();
            await fyr('pointerdown');
            console.log(JSON.stringify(tilstand()));
        """)
        self.assertEqual(ut[0]['status'], 'avvist')
        self.assertEqual(ut[0]['tekst'], 'Skjermen kan sovne — slå av strømsparing')
        self.assertTrue(ut[0]['problem'])

    def test_uten_api_sier_den_fra_og_kaster_ikke(self):
        ut = self._kjor("""
            settNavigator({});
            startVaakenLaas();
            await fyr('pointerdown');
            console.log(JSON.stringify(tilstand()));
            settNavigator(undefined);
            globalThis.vaakenStatus = 'ukjent';
            await fyr('pointerdown');
            console.log(JSON.stringify(tilstand()));
        """)
        self.assertEqual((ut[0]['status'], ut[0]['problem']), ('mangler', True))
        self.assertEqual(ut[1]['status'], 'mangler')

    def test_en_lukket_side_kaster_ikke(self):
        """`tegnVaaken` uten DOM, og en `request` som kaster synkront."""
        ut = self._kjor("""
            const dok = globalThis.document; delete globalThis.document;
            tegnVaaken();
            globalThis.document = dok;
            settNavigator({ wakeLock: { request() { throw new TypeError('synkront'); } } });
            globalThis.vaakenTrykket = true;
            await hentVaakenLaas();
            console.log(JSON.stringify(tilstand()));
        """)
        self.assertEqual(ut[0]['status'], 'avvist')

    def test_den_ekte_oppstartskroken_kobler_inn_laasen(self):
        """`DOMContentLoaded`-kroken klippes ut av fila og kjøres med resten
        stubbet. Forsvinner `startVaakenLaas()` derfra, blir denne rød."""
        kilde = read_js(OPPDRAG_ENHET_JS)
        start = kilde.index("document.addEventListener('DOMContentLoaded', ")
        uttrykk = kilde[start + len("document.addEventListener('DOMContentLoaded', "):
                        kilde.index('\n});', start) + 2]
        ut = self._kjor("""
            for (const navn of ['tegnPosisjonLinje', 'startPosisjon', 'visUsendt', '_lydHintTegn',
                                'lydTikk', 'lastBilinnstillinger', 'synk', 'pollOgSynk']) {
              globalThis[navn] = () => {};
            }
            globalThis.lastMine = async () => {}; globalThis._lydKlar = async () => false;
            globalThis.koLes = () => []; globalThis.setInterval = () => 0;
            globalThis.addEventListener = () => {};
            const kroken = """ + uttrykk + """;
            await kroken();
            await fyr('pointerdown');
            document.visibilityState = 'hidden'; sluppet();
            document.visibilityState = 'visible';
            await fyr('visibilitychange');
            console.log(JSON.stringify(tilstand()));
        """)
        self.assertEqual((ut[0]['status'], ut[0]['foresporsler']), ('holder', 2))
