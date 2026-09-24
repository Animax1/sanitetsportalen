"""«Per · nå» på stolpen (24. sep. 2026). **Når** tavla hentes, avgjøres av den
felles endringsklienten i `portal-utils.js`, og prøves i
`core/tests_endringer_js.py` — også at `koTavleStart` melder tavla inn."""
import json
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import KO_JS, build_harness, node_available, run_node

from .tests_tavle_runde2_js import FORSPILL, HARNESS, LAYOUT_JS, TAVLE_JS

NY_HARNESS = HARNESS[:1] + ((KO_JS, HARNESS[1][1] + ('koTavleErFramme',)),)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TavleversjonJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(NY_HARNESS)
        self.pre = (_konst(TAVLE_JS, 'KO_TAVLE_LENGE_MIN') + _konst(TAVLE_JS, 'KO_TAVLE_PAUSE_FORVARSEL_MIN')
                    + _konst(TAVLE_JS, 'KO_TAVLE_BEHOV_FORVARSEL_MIN') + _konst(TAVLE_JS, 'KO_TAVLE_FLYTTET_MS')
                    + _konst(LAYOUT_JS, 'KO_VINDUER') + FORSPILL)

    def _kjor(self, kode):
        # «OK» skrives synkront på slutten, og kan komme før utskriften fra en
        # asynkron runde. Den tas ut der den står.
        return [linje for linje in run_node(self.harness, kode, preamble=self.pre).splitlines() if linje != 'OK']

    def test_flyttet_av_bare_andre_og_bare_en_stund(self):
        ut = self._kjor("""
            const p = (fra, av, til = null) => ({fra: new Date(fra).toISOString(), til, av_navn: av});
            console.log(JSON.stringify([
              koTavleFlyttetAv(p(NAA - 5000, 'per'), NAA, 'kari'),
              koTavleFlyttetAv(p(NAA - 5000, 'kari'), NAA, 'kari'),
              koTavleFlyttetAv(p(NAA - KO_TAVLE_FLYTTET_MS, 'per'), NAA, 'kari'),
              koTavleFlyttetAv(p(NAA - KO_TAVLE_FLYTTET_MS + 1, 'per'), NAA, 'kari'),
              koTavleFlyttetAv(p(NAA - 5000, 'per', 'x'), NAA, 'kari'),
              koTavleFlyttetAv(p(NAA - 5000, ''), NAA, 'kari'),
            ]));""")
        self.assertEqual(json.loads(ut[0]), ['per', '', '', 'per', '', ''])

    def test_merket_paa_stolpen_gjennom_radene_og_escapet(self):
        ut = self._kjor("""
            globalThis.window = { KO_BRUKERNAVN: 'kari' };
            const d = JSON.parse(JSON.stringify(DATA));
            d.plasseringer[0].fra = new Date(NAA - 3000).toISOString();
            d.plasseringer[0].av_navn = '<img src=x>';
            const s = koTavleRader(d, koTavleVindu(NAA, 12, 25, null), 'alle')[1].stolper.find((x) => x.aapen);
            const html = koTavleStolpeHtml(s);
            console.log(html.includes('ko-tavle-flyttet'), html.includes('<img'), html.includes('&lt;img'));
            d.plasseringer[0].av_navn = 'kari';
            const egen = koTavleRader(d, koTavleVindu(NAA, 12, 25, null), 'alle')[1].stolper.find((x) => x.aapen);
            console.log(koTavleStolpeHtml(egen).includes('ko-tavle-flyttet'));
        """)
        self.assertEqual(ut, ['true false true', 'false'])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TavlaStarterSikkerhetsnettetTests(SimpleTestCase):
    """**Kallstedet** for sikkerhetsnettet og nå-streken. Endringsnummeret
    meldes inn gjennom `folgEndringer` — se `core/tests_endringer_js.py`."""

    def test_start_setter_i_gang_sikkerhetsnettet_og_naa_streken(self):
        pre = (_konst(TAVLE_JS, 'KO_TAVLE_MS') + """
            const intervaller = [];
            globalThis.setInterval = (fn, ms) => intervaller.push(ms);
            globalThis.document = { getElementById: () => ({}) };
            function koTavleLyttere() {}
            function koTavleSynligNaa() {}
            function folgEndringer() {}
            function koHentTavle() {}
            function koTavleErFramme() {}
        """)
        ut = run_node(build_harness(((KO_JS, ('koTavleStart',)),)),
                      'koTavleStart(); console.log(JSON.stringify(intervaller));', preamble=pre)
        self.assertEqual(json.loads(ut.splitlines()[0]), [60000, 60000],
                         'sikkerhetsnettet og nå-streken, hver for seg')
