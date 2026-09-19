"""Andrés runde på staging 12. sep. 2026, del F — lydvarsel i bilen.

«Lydvarsel hos bil enheter når de ikke trykker på rykker ut: Rød innen 1
minutt, deretter hvert 10 sekund. Gul innen 5 minutt deretter hvert 1
minutt. Grønn etter 15 minutt deretter hvert 1 minutt. Lydvarselet trenger
ikke vare langt når det avspilles 1-3 sekunder maks.»
"""
import json

from django.test import SimpleTestCase

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node)

from . import choices
from .tests_runde_d import _konst
from .tests_views import StemplingBasis


class VarsletAtTests(StemplingBasis):
    def test_bilens_rad_baerer_naar_hun_ble_varslet(self):
        o = self._oppdrag()
        rad = self.bil.get('/oppdrag/api/oppdrag/').json()['data'][0]
        self.assertEqual(rad['varslet_at'], o.enheter.get(enhet=self.enhet).varslet_at.isoformat())

    def test_siden_har_ingen_lydbryter_men_baerer_tersklene(self):
        # Lyden er alltid på (12. sep. 2026: «Det skal ikke være et alternativ»).
        res = self.bil.get('/oppdrag/')
        self.assertNotContains(res, 'id="lyd-knapp"')
        self.assertContains(res, 'id="lyd-hint"')
        self.assertContains(res, 'OPPDRAG_BILINNSTILLINGER')
        self.assertContains(res, 'id="lyd-demp"')


class LydvarselJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (OPPDRAG_ENHET_JS, ('skalPipe', 'ventetSekunder', '_lydTerskler', 'lydTerskler',
                            'ventendeSomSkalPipe', '_strengeste', 'lydTikk', 'lydErKlar',
                            'lydSkalSpille', 'bilinnstillinger', 'erDempet', 'dempNokkel')),
    )
    LAGER = ("globalThis.localStorage = (() => { const m = {}; return {"
             "getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },"
             "removeItem: (k) => { delete m[k]; } }; })();\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        # Tilstanden er globaler her (ikke `let`), så testene kan sette dem.
        self.harness = (_konst(OPPDRAG_ENHET_JS, 'HASTEGRAD_REKKEFOLGE')
                        + 'globalThis.lydKontekst = null;\nglobalThis.lydSistFor = {};\n'
                        + build_harness(self.HARNESS))

    def test_tersklene_er_andres(self):
        ut = run_node(self.harness, "console.log(JSON.stringify(lydTerskler()));")
        verdier = json.loads(ut.strip().splitlines()[0])
        self.assertEqual(verdier, {'Akutt': [60, 10], 'Haster': [300, 60], 'Vanlig': [900, 60], 'Drift': [900, 60],
                                   'Plassering': [900, 60]})
        self.assertEqual(set(verdier), set(choices.HASTEGRAD), 'én terskel per hastegrad')

    def test_forste_pip_og_kadensen_per_hastegrad(self):
        ut = run_node(self.harness, """
            const t0 = Date.UTC(2026, 8, 12, 10, 0, 0);
            const o = (h) => ({ id: 1, status: 'venter', hastegrad: h, varslet_at: new Date(t0).toISOString() });
            const s = (o_, sek, sist) => skalPipe(o_, t0 + sek * 1000, sist == null ? null : t0 + sist * 1000);
            console.log(JSON.stringify([
              s(o('Akutt'), 59), s(o('Akutt'), 60), s(o('Akutt'), 65, 60), s(o('Akutt'), 70, 60),
              s(o('Haster'), 299), s(o('Haster'), 300), s(o('Haster'), 330, 300), s(o('Haster'), 360, 300),
              s(o('Vanlig'), 899), s(o('Vanlig'), 900), s(o('Drift'), 900), s(o('Drift'), 959, 900), s(o('Drift'), 960, 900),
            ]));
            // Ikke ventende, eller trykket på (usendt i køen): stille.
            console.log(JSON.stringify([
              skalPipe({ ...o('Akutt'), status: 'rykker_ut' }, t0 + 999000, null),
              skalPipe({ ...o('Akutt'), usendt: true }, t0 + 999000, null),
              skalPipe({ ...o('Akutt'), varslet_at: null, opprettet: new Date(t0).toISOString() }, t0 + 61000, null),
            ]));
        """)
        linjer = ut.strip().splitlines()
        self.assertEqual(json.loads(linjer[0]), [
            False, True, False, True,
            False, True, False, True,
            False, True, True, False, True])
        self.assertEqual(json.loads(linjer[1]), [False, False, True])

    def test_tikket_piper_for_den_strengeste_og_husker_tidspunktet(self):
        ut = run_node(self.harness, self.LAGER + """
            const t0 = Date.UTC(2026, 8, 12, 10, 0, 0);
            const iso = new Date(t0).toISOString();
            globalThis.mineOppdrag = [
              { id: 1, status: 'venter', hastegrad: 'Vanlig', varslet_at: iso },
              { id: 2, status: 'venter', hastegrad: 'Akutt', varslet_at: iso },
              { id: 3, status: 'venter', hastegrad: 'Haster', varslet_at: iso },
              { id: 4, status: 'fremme', hastegrad: 'Akutt', varslet_at: iso }];
            const pipet = [];
            globalThis.pip = (h) => pipet.push(h);
            // Konteksten ikke vekket ennå (nettleseren krever et trykk): stille.
            console.log(JSON.stringify(lydTikk(t0 + 1000000)));
            globalThis.lydKontekst = { state: 'suspended' };
            console.log(JSON.stringify(lydTikk(t0 + 1000000)));
            globalThis.lydKontekst = { state: 'running' };
            console.log(JSON.stringify(lydTikk(t0 + 61000)));     // bare Akutt er forbi
            console.log(JSON.stringify(lydTikk(t0 + 65000)));     // 4 s siden: stille
            console.log(JSON.stringify(lydTikk(t0 + 301000)));    // Akutt igjen (10 s) + Haster først
            console.log(JSON.stringify(pipet));
            // Oppdraget som ikke lenger venter ryddes ut av minnet.
            globalThis.mineOppdrag = [];
            lydTikk(t0 + 400000);
            console.log(JSON.stringify(lydSistFor));
        """)
        l = ut.strip().splitlines()
        self.assertEqual(json.loads(l[0]), [])
        self.assertEqual(json.loads(l[1]), [])
        self.assertEqual(json.loads(l[2]), [2])
        self.assertEqual(json.loads(l[3]), [])
        self.assertEqual(sorted(json.loads(l[4])), [2, 3])
        self.assertEqual(json.loads(l[5]), ['Akutt', 'Akutt'], 'strengeste hastegrad velger lyden')
        self.assertEqual(json.loads(l[6]), {})



class LydenJsTests(SimpleTestCase):
    HARNESS = ((OPPDRAG_ENHET_JS, ('pip', '_tone')),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = 'globalThis.lydKontekst = null;\n' + build_harness(self.HARNESS)

    def test_lyden_varer_hoyst_tre_sekunder(self):
        ut = run_node(self.harness, """
            const toner = [];
            const ctx = {
              currentTime: 100, destination: {},
              createOscillator: () => ({ type: '', frequency: {}, connect() { return this; }, start(t) { this.fra = t; }, stop(t) { toner.push([this.fra, t]); } }),
              createGain: () => ({ gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() { return this; } }),
            };
            globalThis.lydKontekst = ctx;
            for (const h of ['Akutt', 'Haster', 'Vanlig', 'Drift']) {
              toner.length = 0;
              pip(h);
              const slutt = Math.max(...toner.map((t) => t[1])) - ctx.currentTime;
              console.log(h + ' ' + toner.length + ' ' + slutt.toFixed(2));
            }
        """)
        linjer = ut.strip().splitlines()[:4]
        for linje in linjer:
            _, antall, slutt = linje.split()
            self.assertGreaterEqual(int(antall), 3)
            self.assertLessEqual(float(slutt), 3.0, linje)
            self.assertGreaterEqual(float(slutt), 2.0, 'lengre enn første utgave (André, 12. sep. 2026)')
        self.assertTrue(linjer[0].startswith('Akutt 6 '), 'Akutt: seks toner')
