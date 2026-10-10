"""«Logg ut» sier fra før usendte stemplinger slettes (10. okt. 2026).

Funnet under L17 (8. okt.): utloggingen sender `Clear-Site-Data: "storage"`
(H4), som tømmer offline-køene i bilen og vaktlista — trykk som ble gjort uten
dekning forsvant uten at noen ble spurt. Køen skal fortsatt slettes (ellers
ligger den igjen på en delt PC), men den som logger ut skal vite det.

Testene kjører hele `ui-actions.js` og sender skjemaet gjennom den ekte
`submit`-lytteren: en test som bare kalte `usendteStemplinger()` ville gått
grønn om lytteren sluttet å spørre.
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from patients.js_test_utils import (
    INNLOGGET, JS_DIR, OPPDRAG_ENHET_JS, VAKTLISTE_JS, build_harness, node_available,
    read_js, run_node,
)

UI_ACTIONS_JS = JS_DIR / 'ui-actions.js'

#: Nok DOM til at fila kan lastes, et lager, og en `confirm` som husker hva
#: den ble spurt om og svarer det testen sier.
OPPSETT = """
class HTMLFormElement { constructor(dataset) { this.dataset = dataset; } }
globalThis.HTMLFormElement = HTMLFormElement;
const lyttere = [];
globalThis.document = { addEventListener(navn, fn) { if (navn === 'submit') lyttere.push(fn); } };
globalThis.window = globalThis;
globalThis.localStorage = (() => { const m = {}; return {
  getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } }; })();
const spurt = []; let svar = false;
globalThis.confirm = (melding) => { spurt.push(melding); return svar; };
function send(dataset) {
  let stoppet = false;
  const e = { target: new HTMLFormElement(dataset), preventDefault() { stoppet = true; } };
  for (const fn of lyttere) fn(e);
  return stoppet;
}
"""


def _kjor(kode, preamble=OPPSETT):
    ut = run_node(read_js(UI_ACTIONS_JS), kode, preamble=preamble)
    return [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']


class UtloggingenTests(SimpleTestCase):

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_tom_ko_logger_ut_uten_aa_spoerre(self):
        (ut,) = _kjor("""
            globalThis.PORTAL_BRUKER_ID = 7;
            console.log(JSON.stringify([send({ utlogging: '' }), spurt.length]));
        """)
        self.assertEqual(ut, [False, 0])

    def test_usendte_i_begge_koene_spoer_og_avbryt_stopper(self):
        (ut,) = _kjor("""
            globalThis.PORTAL_BRUKER_ID = 7;
            localStorage.setItem('oppdrag_ko_v1:u7', JSON.stringify([{ id: 'a' }]));
            localStorage.setItem('vl_stemplinger_v1:u7', JSON.stringify([{ id: 'b' }, { id: 'c' }]));
            const stoppet = send({ utlogging: '' });
            svar = true;
            const likevel = send({ utlogging: '' });
            console.log(JSON.stringify([stoppet, likevel, spurt]));
        """)
        stoppet, likevel, spurt = ut
        self.assertTrue(stoppet, 'Avbryt holder deg innlogget')
        self.assertFalse(likevel, 'OK logger ut likevel')
        self.assertEqual(len(spurt), 2)
        self.assertIn('3 stemplinger som ikke er sendt', spurt[0])

    def test_entall(self):
        (ut,) = _kjor("""
            globalThis.PORTAL_BRUKER_ID = 7;
            localStorage.setItem('oppdrag_ko_v1:u7', JSON.stringify([{ id: 'a' }]));
            send({ utlogging: '' });
            console.log(JSON.stringify(spurt[0]));
        """)
        self.assertIn('1 stempling som ikke er sendt', ut)
        self.assertIn('slettes den', ut)

    def test_en_annen_brukers_ko_teller_ikke(self):
        """Køene er per bruker (L17). En forgjengers kø på samme PC er ikke
        noe denne utloggingen sletter mer av enn den ellers ville."""
        (ut,) = _kjor("""
            globalThis.PORTAL_BRUKER_ID = 8;
            localStorage.setItem('oppdrag_ko_v1:u7', JSON.stringify([{ id: 'a' }]));
            localStorage.setItem('oppdrag_ko_v1', JSON.stringify([{ id: 'gammel' }]));
            console.log(JSON.stringify([send({ utlogging: '' }), spurt.length]));
        """)
        self.assertEqual(ut, [False, 0])

    def test_andre_skjemaer_spoer_ikke(self):
        """Bare «Logg ut». Et vanlig skjema med `data-confirm` får sin egen
        bekreftelse, ikke denne."""
        (ut,) = _kjor("""
            globalThis.PORTAL_BRUKER_ID = 7;
            localStorage.setItem('oppdrag_ko_v1:u7', JSON.stringify([{ id: 'a' }]));
            svar = true;
            send({});
            send({ confirm: 'Slette Kari?' });
            console.log(JSON.stringify(spurt));
        """)
        self.assertEqual(ut, ['Slette Kari?'])

    def test_oedelagt_eller_sperret_lager_hindrer_ikke_utloggingen(self):
        (ut,) = _kjor("""
            globalThis.PORTAL_BRUKER_ID = 7;
            localStorage.setItem('oppdrag_ko_v1:u7', '{ikke json');
            localStorage.setItem('vl_stemplinger_v1:u7', '"en streng har også length"');
            const oedelagt = send({ utlogging: '' });
            Object.defineProperty(globalThis, 'localStorage', { get() { throw new Error('sperret'); } });
            const sperret = send({ utlogging: '' });
            delete globalThis.PORTAL_BRUKER_ID;
            const anonym = send({ utlogging: '' });
            console.log(JSON.stringify([oedelagt, sperret, anonym, spurt.length]));
        """)
        self.assertEqual(ut, [False, False, False, 0])


class NoklerneErKoenesTests(SimpleTestCase):
    """`ui-actions.js` bygger nøklene selv. Endrer en av køfilene prefikset sitt,
    skal dette bli rødt — ellers spør utloggingen om en kø som ikke finnes."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def _koNokkel(self, sti):
        ut = run_node(build_harness((INNLOGGET, (sti, ('koNokkel',)))),
                      'console.log(JSON.stringify(koNokkel()));',
                      preamble='globalThis.PORTAL_BRUKER_ID = 7;')
        return json.loads(ut.splitlines()[0])

    def test_samme_nokler_som_koene_skriver(self):
        (prefikser,) = _kjor('console.log(JSON.stringify(OFFLINE_KOER));')
        self.assertEqual(
            sorted(f'{p}:u7' for p in prefikser),
            sorted([self._koNokkel(OPPDRAG_ENHET_JS), self._koNokkel(VAKTLISTE_JS)]))


class SkjemaeneTests(TestCase):
    """Hvert «Logg ut» har merket, og sidene laster fila og bruker-ID-en."""

    def test_hvert_utloggingsskjema_er_merket(self):
        rot = Path(settings.BASE_DIR)
        umerket = []
        for sti in sorted(rot.glob('**/templates/**/*.html')):
            if '.venv' in sti.parts or 'site-packages' in sti.parts:
                continue
            for skjema in re.findall(r'<form\b[^>]*>', sti.read_text(encoding='utf-8')):
                if 'accounts:logout' in skjema and 'data-utlogging' not in skjema:
                    umerket.append(sti.relative_to(rot).as_posix())
        self.assertEqual(umerket, [])

    def test_sidene_har_det_advarselen_trenger(self):
        bruker = CustomUser.objects.create_user(
            username='forer', password='pwd', role='bruker', must_change_password=False)
        gi_standardtilgang(bruker, 'skriver')
        self.client.force_login(bruker)
        for adresse in ('/', '/pasienter/'):    # base_portal, og pasientsidens eget skall
            with self.subTest(adresse=adresse):
                svar = self.client.get(adresse)
                self.assertEqual(svar.status_code, 200)
                html = svar.content.decode()
                self.assertIn('data-utlogging', html)
                self.assertIn('js/ui-actions', html)
                treff = re.search(r'window\.PORTAL_BRUKER_ID = (\d+);', html)
                self.assertIsNotNone(treff)
                self.assertEqual(int(treff.group(1)), bruker.pk)
