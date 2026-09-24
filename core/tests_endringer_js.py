"""Endringsnummeret i nettleseren (`portal-utils.js`, 24. sep. 2026).

`sjekkEndringer()` avgjør hvor fort en kollegas flytting, en bil som
stempler og en ny linje i loggen vises — 2,5 sekunder eller et halvt
minutt. **Ett spørsmål for alle områdene fanen følger**: tre løkker ville
tredoblet trafikken og brakt en delt drifts-PC over bremsen.

Kallstedene — tavla, loggen og sentralbordet som melder seg — prøves gjennom
den ekte inngangen, ikke ved å lese kilden.
"""
import json
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import (KO_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, read_js, run_node)

HARNESS = ((PORTAL_UTILS_JS, ('endringSkalHente', 'folgEndringer', 'sjekkEndringer')),)

FORSPILL = (_konst(PORTAL_UTILS_JS, 'ENDRING_MS') + """
    const endringFolgere = []; let endringTimer = null; let endringPaagaar = false;
    const spurt = []; const hentet = []; const intervaller = [];
    let svar = [];
    globalThis.setInterval = (fn, ms) => { intervaller.push([fn.name, ms]); return intervaller.length; };
    globalThis.document = { visibilityState: 'visible' };
    globalThis.apiFetch = async (url) => { spurt.push(url); return { ok: true, json: async () => svar.shift() || {} }; };
    const hent = (navn) => async () => { hentet.push(navn); };
""")


def _kjor(kode):
    ut = run_node(build_harness(HARNESS), '(async () => {\n' + kode + '\n})();', preamble=FORSPILL)
    # «OK» skrives synkront på slutten, og kan komme før utskriften fra den
    # asynkrone blokka. Den tas ut der den står.
    return [linje for linje in ut.splitlines() if linje != 'OK']


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class EndringsklientenTests(SimpleTestCase):

    def test_likhet_ikke_stoerrelse(self):
        ut = _kjor("""console.log(JSON.stringify([endringSkalHente(null, '5'), endringSkalHente('5', '5'),
            endringSkalHente('9', '5'), endringSkalHente('5', ''), endringSkalHente('5', undefined),
            endringSkalHente('5', 6)]));""")
        self.assertEqual(json.loads(ut[0]), [True, False, True, False, False, False],
                         'et mindre tall er også nytt — cachen kan ha startet på nytt')

    def test_ett_spoersmaal_for_alle_omraadene_og_bare_de_nye_hentes(self):
        ut = _kjor("""
            folgEndringer('tavle', hent('tavle'));
            folgEndringer('logg', hent('logg'));
            folgEndringer('logg', hent('logg2'));
            svar = [{tavle: 'a', logg: '1'}, {tavle: 'a', logg: '2'}, {tavle: 'b', logg: '2'}];
            for (let i = 0; i < 3; i += 1) await sjekkEndringer();
            console.log(JSON.stringify([spurt.length, decodeURIComponent(spurt[0]), hentet, intervaller]));
        """)
        antall, url, hentet, intervaller = json.loads(ut[0])
        self.assertEqual(antall, 3, 'ett spørsmål per runde, ikke ett per liste')
        self.assertEqual(url, '/api/endringer/?omrader=logg,tavle', 'hvert område én gang, sortert')
        self.assertEqual(hentet, ['tavle', 'logg', 'logg2', 'logg', 'logg2', 'tavle'])
        self.assertEqual(intervaller, [['sjekkEndringer', 2500]], 'én løkke, startet av den første')

    def test_en_liste_som_ikke_er_framme_spoer_ikke_og_henter_ikke(self):
        ut = _kjor("""
            let framme = false;
            folgEndringer('tavle', hent('tavle'), () => framme);
            folgEndringer('logg', hent('logg'));
            svar = [{logg: '1'}, {tavle: 'a', logg: '1'}];
            await sjekkEndringer();
            framme = true;
            await sjekkEndringer();
            console.log(JSON.stringify([spurt.map(decodeURIComponent), hentet]));
        """)
        self.assertEqual(json.loads(ut[0]), [['/api/endringer/?omrader=logg', '/api/endringer/?omrader=logg,tavle'],
                                             ['logg', 'tavle']])

    def test_skjult_fane_og_ingen_aktive_spoer_ikke(self):
        ut = _kjor("""
            folgEndringer('tavle', hent('tavle'), () => false);
            await sjekkEndringer();
            folgEndringer('logg', hent('logg'));
            document.visibilityState = 'hidden';
            await sjekkEndringer();
            console.log(spurt.length);
        """)
        self.assertEqual(ut[0], '0')

    def test_en_henting_som_feiler_stopper_ikke_de_andre(self):
        ut = _kjor("""
            folgEndringer('tavle', async () => { throw new Error('nede'); });
            folgEndringer('logg', hent('logg'));
            svar = [{tavle: 'a', logg: '1'}];
            await sjekkEndringer();
            console.log(JSON.stringify([hentet, endringPaagaar]));
        """)
        self.assertEqual(json.loads(ut[0]), [['logg'], False])

    def test_ikke_to_spoersmaal_samtidig(self):
        ut = _kjor("""
            folgEndringer('logg', hent('logg'));
            svar = [{logg: '1'}, {logg: '1'}];
            await Promise.all([sjekkEndringer(), sjekkEndringer()]);
            console.log(spurt.length);
        """)
        self.assertEqual(ut[0], '1')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KallstedeneTests(SimpleTestCase):
    """**Hvem som melder seg, med hva.** Uten kallstedet henter lista bare på
    sikkerhetsnettet, med alle testene av `sjekkEndringer` grønne."""

    def _krok(self, kilde, start):
        """Kjør en ekte `DOMContentLoaded`-krok med hvert navn den bruker
        byttet mot en opptaker (`with` over en Proxy)."""
        i = kilde.index(start) + len(start)
        slutt = kilde.index('\n});', i) + 2
        krok = kilde[i:slutt]
        ut = run_node('', 'const kall = [];\n'
                      'const stub = new Proxy({}, { has: (t, k) => k !== "kall" && k !== "JSON",'
                      ' get: (t, k) => k === "document" ? { getElementById: () => null }'
                      ' : Object.assign((...a) => { kall.push([String(k), ...a.map((x) => typeof x === "function"'
                      ' ? (x.navn || "fn") : x)]); return null; }, { navn: String(k) }) });\n'
                      'Promise.resolve(new Function("stub", "with (stub) { return (" + ' + json.dumps(krok)
                      + ' + ")(); }")(stub)).then(() => console.log(JSON.stringify(kall)));').splitlines()
        return json.loads([linje for linje in ut if linje != 'OK'][0])

    def test_loggen_i_ko(self):
        kall = self._krok(read_js(KO_JS), "document.addEventListener('DOMContentLoaded', ")
        self.assertIn(['folgEndringer', 'logg', 'koHentLogg'], kall)

    def test_sentralbordet_i_ko_og_paa_oppdrag(self):
        kall = self._krok(read_js(OPPDRAG_SENTRAL_JS), "document.addEventListener('DOMContentLoaded', ")
        self.assertIn(['folgEndringer', 'oppdrag', 'lastAlt'], kall)

    def test_tavla_bare_mens_den_staar_framme(self):
        pre = _konst(KO_JS[2], 'KO_TAVLE_MS') + """
            const kall = [];
            globalThis.setInterval = () => {};
            globalThis.document = { getElementById: () => ({}) };
            function koTavleLyttere() {}
            function koTavleSynligNaa() {}
            function koHentTavle() {}
            function koTavleErFramme() {}
            function folgEndringer(omrade, hent, aktiv) { kall.push([omrade, hent.name, aktiv && aktiv.name]); }
        """
        ut = run_node(build_harness(((KO_JS, ('koTavleStart',)),)),
                      'koTavleStart(); console.log(JSON.stringify(kall));', preamble=pre)
        self.assertEqual(json.loads(ut.splitlines()[0]), [['tavle', 'koHentTavle', 'koTavleErFramme']])
