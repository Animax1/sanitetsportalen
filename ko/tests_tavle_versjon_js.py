"""Endringsnummeret i nettleseren (24. sep. 2026): når tavla hentes, og
«Per · nå» på stolpen. Kallstedet `koSjekkTavleVersjon` prøves med en stubbet
`apiFetch` — det er den som avgjør om en flytting vises etter 2,5 sekunder
eller etter 60."""
import json
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import KO_JS, build_harness, node_available, run_node

from .tests_tavle_runde2_js import FORSPILL, HARNESS, LAYOUT_JS, TAVLE_JS

NY_HARNESS = HARNESS[:1] + ((KO_JS, HARNESS[1][1] + ('koTavleSkalHente', 'koSjekkTavleVersjon',
                                                      'koTavleErFramme')),)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TavleversjonJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(NY_HARNESS)
        self.pre = (_konst(TAVLE_JS, 'KO_TAVLE_LENGE_MIN') + _konst(TAVLE_JS, 'KO_TAVLE_PAUSE_FORVARSEL_MIN')
                    + _konst(TAVLE_JS, 'KO_TAVLE_BEHOV_FORVARSEL_MIN') + _konst(TAVLE_JS, 'KO_TAVLE_FLYTTET_MS')
                    + _konst(LAYOUT_JS, 'KO_VINDUER') + FORSPILL
                    + 'let koTavleVersjon = null; let koTavleSporPaagaar = false;\n')

    def _kjor(self, kode):
        # «OK» skrives synkront på slutten, og kan komme før utskriften fra en
        # asynkron runde. Den tas ut der den står.
        return [linje for linje in run_node(self.harness, kode, preamble=self.pre).splitlines() if linje != 'OK']

    def test_likhet_ikke_stoerrelse(self):
        ut = self._kjor("""console.log(JSON.stringify([koTavleSkalHente(null, '5'), koTavleSkalHente('5', '5'),
            koTavleSkalHente('9', '5'), koTavleSkalHente('5', ''), koTavleSkalHente('5', undefined),
            koTavleSkalHente('5', 6)]));""")
        self.assertEqual(json.loads(ut[0]), [True, False, True, False, False, False],
                         'et mindre tall er også nytt — cachen kan ha startet på nytt')

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

    def _sjekk(self, oppsett, runder):
        return self._kjor(f"""
            const hentet = [];
            let svar = ['a1'];
            globalThis.document = {{ visibilityState: 'visible',
              querySelector: () => ({{ classList: {{ contains: () => false }} }}) }};
            globalThis.apiFetch = async () => ({{ ok: true, json: async () => ({{ tavle: svar.shift() }}) }});
            globalThis.koHentTavle = async () => {{ hentet.push(koTavleVersjon); }};
            {oppsett}
            (async () => {{
              for (let i = 0; i < {runder}; i += 1) await koSjekkTavleVersjon();
              console.log(JSON.stringify(hentet));
            }})();
        """)

    def test_henter_bare_naar_tallet_er_nytt(self):
        ut = self._sjekk("svar = ['a1', 'a1', 'a2', 'a2', 'a1'];", 5)
        self.assertEqual(json.loads(ut[0]), ['a1', 'a2', 'a1'])

    def test_skjult_fane_og_skjult_tavle_spoer_ikke(self):
        ut = self._sjekk("document.visibilityState = 'hidden';", 2)
        self.assertEqual(json.loads(ut[0]), [])
        ut = self._sjekk("document.querySelector = () => ({ classList: { contains: () => true } });", 2)
        self.assertEqual(json.loads(ut[0]), [], 'tavla står ikke framme')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TavlaStarterSpoerringenTests(SimpleTestCase):
    """**Kallstedet**, ikke bare funksjonen: uten `setInterval` i
    `koTavleStart` spør tavla aldri, og hentes bare på sikkerhetsnettet hvert
    60. sekund — med alle testene av `koSjekkTavleVersjon` grønne. Funnet ved
    mutasjonstesting 24. sep. 2026."""

    def test_start_setter_i_gang_spoerringen_og_sikkerhetsnettet(self):
        pre = (_konst(TAVLE_JS, 'KO_TAVLE_MS') + _konst(TAVLE_JS, 'KO_TAVLE_VERSJON_MS') + """
            const intervaller = [];
            globalThis.setInterval = (fn, ms) => intervaller.push([fn.name || 'anonym', ms]);
            globalThis.document = { getElementById: () => ({}) };
            function koTavleLyttere() {}
            function koTavleSynligNaa() {}
            function koSjekkTavleVersjon() {}
        """)
        ut = run_node(build_harness(((KO_JS, ('koTavleStart',)),)),
                      'koTavleStart(); console.log(JSON.stringify(intervaller));', preamble=pre)
        intervaller = json.loads(ut.splitlines()[0])
        self.assertIn(['koSjekkTavleVersjon', 2500], intervaller)
        self.assertEqual([ms for _, ms in intervaller].count(60000), 2,
                         'sikkerhetsnettet og nå-streken, hver for seg')
