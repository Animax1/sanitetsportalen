"""L17: offline-køene tilhører kontoen som trykket (8. okt. 2026).

Sikkerhetsgjennomgangen 13. sep. 2026: «Offline-køene i localStorage er ikke
knyttet til bruker; en annen konto på samme enhet spiller av forgjengerens
usendte stemplinger.» Begge køene — bilens i `oppdrag-enhet.js` og vaktlistas i
`vaktliste-offline.js` — lå under én fast nøkkel. På en delt drifts-PC eller en
telefon som går mellom to kontoer, ble A sine trykk sendt under B sin
innlogging, og ingen så det.

Testene gjennomfører angrepet gjennom den ekte synkingen (`synk()` og
`synkKo()`), ikke bare nøkkelfunksjonen: en test som bare spør `koNokkel()`
ville gått grønn om én av køene sluttet å bruke den.
"""
import json
import re

from django.test import SimpleTestCase, TestCase

from accounts.models import CustomUser, ModulTilgang
from oppdrag import tests_bilen_dobbelttrykk as bilen
from patients.js_test_utils import (
    INNLOGGET, PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness, node_available, run_node,
)

#: Et lager som viser hvilke nøkler som faktisk ble skrevet — det er nøklene
#: som er påstanden, ikke bare hva `koLes()` svarer.
LAGER = """
globalThis.localStorage = (() => { const m = {}; return {
  getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
  removeItem: (k) => { delete m[k]; }, _nokler: () => Object.keys(m).sort() }; })();
"""


def _ut(stdout):
    return [json.loads(linje) for linje in stdout.splitlines() if linje != 'OK']


class BilensKoTests(SimpleTestCase):
    """`oppdrag-enhet.js`: en telefon som går fra bil A sin konto til bil B sin."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def _kjor(self, kode):
        return _ut(run_node(build_harness(bilen.HARNESS),
                            '(async () => {\n' + kode + '\n})();',
                            preamble=bilen.FORSPILL + LAGER))

    def test_en_annen_konto_spiller_ikke_av_koen_og_eieren_faar_den_sendt(self):
        (ut,) = self._kjor("""
            globalThis.PORTAL_BRUKER_ID = 7;
            koLeggTil(7, 'leverer');                 // A trykker uten dekning
            globalThis.PORTAL_BRUKER_ID = 8;         // B logger inn på samme telefon
            const bSer = koLes().length;
            await synk();
            const sendtUnderB = sendt.length;
            globalThis.PORTAL_BRUKER_ID = 7;         // A logger inn igjen
            const aSer = koLes().length;
            await synk();
            console.log(JSON.stringify([bSer, sendtUnderB, aSer, sendt, koLes().length]));
        """)
        self.assertEqual(ut, [0, 0, 1, ['/oppdrag/api/oppdrag/7/status/leverer/'], 0])

    def test_uten_innlogget_bruker_skrives_ingen_felles_nokkel(self):
        """En reserve til den gamle nøkkelen ville gjenåpnet hullet i det stille."""
        (ut,) = self._kjor("""
            delete globalThis.PORTAL_BRUKER_ID;
            const skrevet = koSkriv([{ id: 'x' }]);
            console.log(JSON.stringify([skrevet, koLes(), localStorage._nokler()]));
        """)
        self.assertEqual(ut, [False, [], []])

    def test_den_gamle_felles_koen_leses_ikke(self):
        (ut,) = self._kjor("""
            localStorage.setItem('oppdrag_ko_v1', JSON.stringify([{ id: 'gammel', oppdragId: 7 }]));
            globalThis.PORTAL_BRUKER_ID = 7;
            console.log(JSON.stringify(koLes()));
        """)
        self.assertEqual(ut, [])


class VaktlistasKoTests(SimpleTestCase):
    """`vaktliste-offline.js`: en delt PC der én fører logger ut og en annen inn."""

    HARNESS = (INNLOGGET, (PORTAL_UTILS_JS, ('escapeHtml',)),
               (VAKTLISTE_JS, ('koNokkel', 'koLes', 'koSkriv', 'synkKo', '_sesjonUtgaatt')))
    STUBB = LAGER + """
let synkPaagaar = false; let aktivListe = null;
let offlineTilstand = { frakoblet: false, kopiFra: null, sesjonUtgaatt: false, sistFeil: '' };
function tegnOffline() {}
async function lastListe() {}
const sendt = [];
globalThis.apiFetch = async (url) => { sendt.push(url);
  return { ok: true, status: 200, redirected: false, url, json: async () => ({ status: 'ok' }) }; };
"""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def _kjor(self, kode):
        return _ut(run_node(build_harness(self.HARNESS),
                            '(async () => {\n' + kode + '\n})();', preamble=self.STUBB))

    def test_en_annen_konto_spiller_ikke_av_koen_og_eieren_faar_den_sendt(self):
        (ut,) = self._kjor("""
            globalThis.PORTAL_BRUKER_ID = 7;
            koSkriv([{ id: 'a1', vaktpostId: 3, handling: 'mott', tidspunkt: '2026-10-08T10:00:00Z' }]);
            globalThis.PORTAL_BRUKER_ID = 8;
            await synkKo();
            const sendtUnderB = sendt.length;
            globalThis.PORTAL_BRUKER_ID = 7;
            await synkKo();
            console.log(JSON.stringify([sendtUnderB, sendt, koLes().length]));
        """)
        self.assertEqual(ut, [0, ['/vaktliste/api/vaktposter/3/stempling/mott/'], 0])

    def test_uten_innlogget_bruker_skrives_ingen_felles_nokkel(self):
        (ut,) = self._kjor("""
            delete globalThis.PORTAL_BRUKER_ID;
            console.log(JSON.stringify([koSkriv([{ id: 'x' }]), koLes(), localStorage._nokler()]));
        """)
        self.assertEqual(ut, [False, [], []])


class BrukerIdenSettesPaaSidenTests(TestCase):
    """`brukerNokkel()` er ingenting verdt uten ID-en, og den settes ett sted:
    `base_portal.html`. Siden må ha den *før* skriptene som leser den."""

    def test_vaktlista_faar_id_en_foer_koskriptet(self):
        bruker = CustomUser.objects.create_user(
            username='forer', password='pwd', role='bruker', must_change_password=False)
        ModulTilgang.objects.create(bruker=bruker, modul_slug='vaktliste', nivaa='les_alle')
        self.client.force_login(bruker)
        html = self.client.get('/vaktliste/').content.decode()
        treff = re.search(r'window\.PORTAL_BRUKER_ID = (\d+);', html)
        self.assertIsNotNone(treff, 'ID-en står på siden')
        self.assertEqual(int(treff.group(1)), bruker.pk)
        self.assertLess(treff.start(), html.index('js/vaktliste-offline'),
                        'ID-en er satt før køen leses')
