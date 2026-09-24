"""Tavla og konsertplanleggeren, runde 2 (23. sep. 2026), i nettleseren.

André etter staging: navnet på en stolpe begynte «i fortid»; tavla må se
lenger fram enn bak og kunne rulles; «planlegg knapp på alle lokasjonene»;
«KO skal trykke flytt nå»; planleggeren og tavla skal følge samme tidslinje;
og hvert vindu skal kunne åpnes for seg.

Reglene kjøres i node gjennom de ekte byggerne. Tegningen prøves gjennom
`koTegnTavle` — **kallstedet**, ikke bare hjelperen: vinduet må komme fra
`koTidVindu`, ellers ruller ikke tavla med planleggeren.
"""
import json
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import (KO_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, run_node)

from .tests_tavle_js import DATA, NAA

LAYOUT_JS = KO_JS[0]
TAVLE_JS = KO_JS[2]

HARNESS = (
    (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml')),
    (KO_JS, (
        # Tida.
        'koTavleVindu', 'koTavleIVinduet', 'koTidInnstillinger', 'koTidVindu', 'koTidNyttAnker',
        'koTidEtterDrag', 'koTidMelding', 'koTidKontrollHtml',
        # Tavla.
        'koTavleKanSkrive', 'koTavleLesFilter', 'koTavleProsent', 'koTavleSynlig', 'koTavleKanDras',
        'koTavleVarighet', 'koTavleTo', 'koTavleHHMM', 'koTavleTidNaer', 'koTavleTilEtter',
        'koTavlePauseStatus', 'koTavlePauseKildetekst', 'koTavleSlutt', 'koTavleProgram', 'koTavleBehovNaa',
        'koTavleRader', 'koTavleUtenPlass', 'koTavleStolpeHtml', 'koTavleSluttHtml', 'koTavleKonsertHtml',
        'koTavleBehovHtml', 'koTavleRadHtml', 'koTavleTimerHtml', 'koTavleUtenPlassHtml', 'koTavlePlanlagtHtml',
        'koTavleValgtHtml', 'koTavleFilterHtml', 'koTavleDognnokkel', 'koTavleDognnavn', 'koTavleIkkeVaert',
        'koTavleIkkeVaertHtml', 'koTavleSkjemaData', 'koTavleSkjemaHtml', 'koTavleSkjemaKropp',
        'koTavleOppsettHtml', 'koTegnTavle', 'koTegnTavleSkjema',
        # Et vindu for seg.
        'koEgetVinduNavn', 'koEgetVinduUrl',
    )),
)

FORSPILL = f"""
let koTavle = null; let koPlan = null; let koTidAnker = null;
let koTavleKlokkeavvik = 0; let koTavleDrag = null; let koTavleTegnEtterDrag = false;
let koTavleVisning = 'tavle'; let koTavleSkjema = null; let koTavleValgt = null;
let koTavleBesokValg = {{ lokasjon: null, maal: 'antall' }};
let koKanSkriveSvar = true;
function koKanSkrive() {{ return koKanSkriveSvar; }}
const DATA = {json.dumps(DATA)};
const NAA = Date.parse('{NAA}');
const T = 3600000;
// Planene i runde 2: en pause, og en plan på Village (id 2) for Lag 2.
DATA.pauser = [
  {{id: 50, ressurs_id: 102, ressurs_navn: 'Lag 2', fra: new Date(NAA + 5 * 60000).toISOString(),
    til: new Date(NAA + 35 * 60000).toISOString(), startet: false, kilde: 'ko', pause: true,
    lokasjon_id: null, lokasjon_navn: ''}},
  {{id: 51, ressurs_id: 102, ressurs_navn: 'Lag 2', fra: new Date(NAA + 2 * T).toISOString(),
    til: new Date(NAA + 4 * T).toISOString(), startet: false, kilde: 'ko', pause: false,
    lokasjon_id: 2, lokasjon_navn: 'Village'}},
  // Et lag som ikke er på tavla nå, men har skift i morgen.
  {{id: 52, ressurs_id: 109, ressurs_navn: 'Lag 9', fra: new Date(NAA + 3 * T).toISOString(),
    til: new Date(NAA + 5 * T).toISOString(), startet: false, kilde: 'ko', pause: false,
    lokasjon_id: 1, lokasjon_navn: 'Parkscene'}},
];
DATA.alle_ressurser = DATA.ressurser.map((r) => ({{id: r.id, navn: r.navn, gruppe_id: r.gruppe_id, bil: r.bil}}))
  .concat([{{id: 109, navn: 'Lag 9', gruppe_id: 10, bil: false}}]);
DATA.andel_bak = 25; DATA.steg_min = 120; DATA.dognstart = '06:00';
"""

DOM = """
const ELS = {};
const nyEl = () => ({ innerHTML: '', dataset: {}, classList: { toggle() {}, add() {}, remove() {} } });
globalThis.document = { getElementById: (id) => (ELS[id] = ELS[id] || nyEl()) };
"""


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TidsvinduetJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(HARNESS)
        self.pre = (_konst(TAVLE_JS, 'KO_TAVLE_LENGE_MIN') + _konst(TAVLE_JS, 'KO_TAVLE_PAUSE_FORVARSEL_MIN')
                    + _konst(TAVLE_JS, 'KO_TAVLE_BEHOV_FORVARSEL_MIN')
                    + _konst(LAYOUT_JS, 'KO_VINDUER') + FORSPILL)

    def _kjor(self, kode, dom=False):
        ut = run_node(self.harness, kode, preamble=self.pre + (DOM if dom else '')).splitlines()
        return ut[:-1] if ut and ut[-1] == 'OK' else ut

    def _json(self, uttrykk):
        return json.loads(self._kjor(f'console.log(JSON.stringify({uttrykk}));')[0])

    # ── Tida ────────────────────────────────────────────────────────────────

    def test_steg_og_drag_flytter_ankeret(self):
        ut = self._json("""[koTidNyttAnker({fra: NAA}, 1, 120) - NAA, koTidNyttAnker({fra: NAA}, -1, 30) - NAA,
                            koTidNyttAnker({fra: NAA}, 1, 'x') - NAA,
                            koTidEtterDrag(NAA, -100, 1000, 12 * T) - NAA, koTidEtterDrag(NAA, 100, 1000, 12 * T) - NAA,
                            koTidEtterDrag(NAA, 7, 1000, 12 * T) - NAA, koTidEtterDrag(NAA, 50, 0, 12 * T) - NAA]""")
        self.assertEqual(ut[:3], [2 * 3600000, -30 * 60000, 2 * 3600000])
        self.assertEqual(ut[3:5], [72 * 60000, -72 * 60000], 'dra mot venstre, og vinduet går fram')
        self.assertEqual(ut[5] % 60000, 0, 'hele minutter')
        self.assertEqual(ut[6], 0, 'uten bredde flyttes ingenting')

    def test_meldingen_fra_et_annet_vindu_er_data(self):
        ut = self._json("""[koTidMelding({anker: NAA}), koTidMelding({anker: null}), koTidMelding({sporr: true}),
                            koTidMelding({anker: 'x'}), koTidMelding({anker: -5}), koTidMelding('tull'),
                            koTidMelding(null), koTidMelding({})]""")
        self.assertEqual(ut[:3], [{'anker': self._json('NAA')}, {'anker': None}, {'sporr': True}])
        self.assertEqual(ut[3:], [None, None, None, None, None])

    def test_innstillingene_fra_tavla_ellers_programmet_ellers_standarden(self):
        ut = self._json("""(() => {
            const a = koTidInnstillinger();
            koPlan = {rulling: {timer: 18, andel_bak: 10, steg_min: 60, dognstart: '07:00'}};
            const b = koTidInnstillinger();
            koTavle = {timer: 24, andel_bak: 0, steg_min: 30, dognstart: '06:00'};
            const c = koTidInnstillinger();
            return [a, b, c, koTidVindu(NAA).fra === NAA];
        })()""")
        self.assertEqual(ut[0], {'timer': 12, 'andel_bak': 25, 'steg_min': 120, 'dognstart': '06:00'})
        self.assertEqual(ut[1]['andel_bak'], 10, 'planleggeren virker uten tavla')
        self.assertEqual(ut[2]['andel_bak'], 0, '0 er en verdi, ikke «mangler»')
        self.assertTrue(ut[3])

    def test_kontrollen_sier_fra_naar_nå_er_utenfor(self):
        ut = self._kjor("""
            const v = koTavleVindu(NAA, 12, 25, null);
            console.log(koTidKontrollHtml(v, null).includes('Du ser ikke nå'));
            const langt = koTavleVindu(NAA, 12, 25, NAA + 24 * T);
            console.log(koTidKontrollHtml(langt, NAA + 24 * T).includes('Tilbake til nå'));
            // Rullet, men nå er fortsatt i vinduet: ikke «borte», men ikke «Nå» heller.
            const litt = koTavleVindu(NAA, 12, 25, NAA - T);
            const h = koTidKontrollHtml(litt, NAA - T);
            console.log(h.includes('Du ser ikke nå'), /btn-outline-secondary active/.test(h));
        """)
        self.assertEqual(ut[:3], ['false', 'true', 'false false'])

    def test_teksten_bruker_kalenderdatoen_ikke_doegnet(self):
        """«ons. 14:00 – ons. 02:00» sto det i nettleseren: natta hører til
        onsdagens døgn i «Besøk», men klokka 02 er torsdag."""
        ut = self._kjor("""
            const fra = new Date(2026, 8, 23, 14, 0).getTime();
            console.log(koTidKontrollHtml({fra, til: fra + 12 * T, naa: fra}, null).match(/ko-tid-tekst">([^<]*)</)[1]);
        """)
        self.assertEqual(ut, ['Ons. 23.09. 14:00 – Tor. 24.09. 02:00'])

    # ── Tegningen, gjennom den ekte inngangen ───────────────────────────────

    def test_tavla_tegnes_i_vinduet_koTidVindu_gir(self):
        """Uten kallstedet ruller ikke tavla med planleggeren."""
        ut = self._kjor("""
            koTavle = DATA;
            Date.now = () => NAA;
            koTegnTavle();
            const naa = ELS['ko-tavle'].innerHTML;
            koTidAnker = NAA + 24 * T;
            koTegnTavle();
            const i_morgen = ELS['ko-tavle'].innerHTML;
            console.log(naa.includes('class="ko-tavle-naa"'), naa.includes('Lag 1'));
            console.log(i_morgen.includes('class="ko-tavle-naa"'), i_morgen.includes('Du ser ikke nå'),
                        i_morgen.includes('data-tid-akse="1"'));
        """, dom=True)
        self.assertEqual(ut[0], 'true true')
        self.assertEqual(ut[1], 'false true true', 'nå-streken klemmes ikke til kanten')

    # ── Stolpen vokser framover ─────────────────────────────────────────────

    def test_den_aapne_stolpen_begynner_der_laget_kom(self):
        """André: «Når du drar over en enhet så begynner navnet i "fortid", det
        må heller gå fremover i fremtid»."""
        ut = self._kjor("""
            const d = JSON.parse(JSON.stringify(DATA));
            d.plasseringer[0].fra = new Date(NAA - 2 * 60000).toISOString();
            const v = koTavleVindu(NAA, 12, 25, null);
            const s = koTavleRader(d, v, 'alle')[1].stolper.find((x) => x.aapen);
            const html = koTavleStolpeHtml(s);
            console.log(/style="left:24\\.\\d+%;width:max\\(72px,/.test(html), html.includes('right:'));
        """)
        self.assertEqual(ut, ['true false'])

    # ── Planen på alle rader ────────────────────────────────────────────────

    def test_planen_staar_i_raden_den_skal_til(self):
        ut = self._json("""(() => {
            const rader = koTavleRader(DATA, koTavleVindu(NAA, 12, 25, null), 'alle');
            const plan = (r) => r.stolper.filter((s) => s.pause_id).map((s) => [s.pause_id, s.plan_pause, s.navn]);
            return [plan(rader[0]), plan(rader[1]), plan(rader[2])];
        })()""")
        self.assertEqual(ut, [[[50, True, 'Lag 2']], [[52, False, 'Lag 9']], [[51, False, 'Lag 2']]],
                         'pausen i Pause-raden, planen på stedet — også for et lag som ikke er på tavla nå')

    def test_et_svar_uten_pause_feltet_er_en_pause(self):
        ut = self._json("""(() => {
            const d = JSON.parse(JSON.stringify(DATA));
            d.pauser = [Object.assign({}, d.pauser[0])]; delete d.pauser[0].pause; delete d.pauser[0].lokasjon_id;
            return koTavleRader(d, koTavleVindu(NAA, 12, 25, null), 'alle').map((r) => r.stolper.filter((s) => s.pause_id).length);
        })()""")
        self.assertEqual(ut, [1, 0, 0])

    def test_filteret_finner_gruppa_i_hele_lista(self):
        ut = self._json("""(() => {
            const v = koTavleVindu(NAA, 12, 25, null);
            const antall = (f) => koTavleRader(DATA, v, f)[1].stolper.filter((s) => s.pause_id === 52).length;
            return [antall('10'), antall('20')];
        })()""")
        self.assertEqual(ut, [1, 0], 'Lag 9 er ikke på tavla, men gruppa står i alle_ressurser')

    def test_flytt_naa_paa_stolpen_og_kortet(self):
        ut = self._kjor("""
            const v = koTavleVindu(NAA + 2 * T, 12, 25, null);
            const s = koTavleRader(DATA, v, 'alle')[2].stolper.find((x) => x.pause_id === 51);
            console.log(s.pause_status, koTavleStolpeHtml(s).includes('>Flytt nå</button>'));
            console.log(koTavlePlanlagtHtml({id: 51, naa: true, kl: '22:00', pause: false, sted: 'Village'}));
            console.log(koTavlePlanlagtHtml({id: 51, naa: false, kl: '22:00', pause: false, sted: 'Village'}));
            console.log(koTavlePlanlagtHtml({id: 50, naa: true, kl: '22:00', pause: true, sted: ''}).includes('Pause nå'));
            koKanSkriveSvar = false;
            console.log(koTavleStolpeHtml(s).includes('Flytt nå'));
        """)
        self.assertEqual(ut[0], 'naa true')
        self.assertIn('Flytt nå · Village', ut[1])
        self.assertIn('Village 22:00', ut[2])
        self.assertEqual(ut[3:], ['true', 'false'])

    def test_kortet_i_uten_plass_sier_hvor_planen_gaar(self):
        """Gjennom `koTavleUtenPlass`, ikke bare byggeren: kortet skal si
        «Village 22:00», ikke «Pause 22:00», for en plan på et sted."""
        ut = self._json("""(() => {
            const d = JSON.parse(JSON.stringify(DATA));
            d.pauser = d.pauser.filter((q) => q.id !== 50);
            const p = koTavleUtenPlass(d, 'alle', NAA).ledige.find((r) => r.id === 102).planlagt;
            return [p.id, p.pause, p.sted, koTavlePlanlagtHtml(p).includes('Village')];
        })()""")
        self.assertEqual(ut, [51, False, 'Village', True])

    def test_planlegg_i_hver_rad_bare_for_den_som_skriver(self):
        ut = self._kjor("""
            const rader = koTavleRader(DATA, koTavleVindu(NAA, 12, 25, null), 'alle');
            const html = rader.map(koTavleRadHtml).join('');
            console.log((html.match(/data-action="koTavlePlanlegg"/g) || []).length,
                        html.includes('data-action="koTavlePlanlegg" data-arg="2"'));
            koKanSkriveSvar = false;
            console.log(rader.map(koTavleRadHtml).join('').includes('koTavlePlanlegg'));
        """)
        self.assertEqual(ut, ['3 true', 'false'])

    # ── Skjemaet ────────────────────────────────────────────────────────────

    def test_skjemaet_for_et_sted_tilbyr_hele_lista_ogsaa_biler(self):
        ut = self._json("""(() => {
            const sted = koTavleSkjemaData({type: 'pause', id: null, lokasjon_id: 2, ref: NAA}, DATA, NAA);
            const pause = koTavleSkjemaData({type: 'pause', id: null, lokasjon_id: null, ref: NAA}, DATA, NAA);
            const endre = koTavleSkjemaData({type: 'pause', id: 51}, DATA, NAA);
            return [sted.tittel, sted.ressurser.map((r) => r.id), pause.ressurser.map((r) => r.id),
                    endre.tittel, endre.lokasjon_id, endre.ressurser,
                    koTavleSkjemaData({type: 'pause', id: null, lokasjon_id: 99}, DATA, NAA)];
        })()""")
        self.assertEqual(ut[0], 'Planlegg · Village')
        self.assertEqual(ut[1], [101, 102, 103, 201, 109], 'et lag med skift i morgen, og bilen')
        self.assertEqual(ut[2], [101, 102, 103, 109], 'en bil tar ikke pause')
        self.assertEqual(ut[3:6], ['Endre plan · Village · Lag 2', 2, None])
        self.assertIsNone(ut[6], 'en rad som ikke finnes, gir ikke et skjema')

    def test_forslaget_og_tidene_er_der_man_ser(self):
        ut = self._json("""(() => {
            const i_morgen = NAA + 24 * T;
            const d = koTavleSkjemaData({type: 'pause', id: null, lokasjon_id: 2, ref: i_morgen}, DATA, NAA);
            const k = koTavleSkjemaKropp({type: 'pause', id: null, lokasjon_id: 2, ref: i_morgen}, DATA,
              {fra: d.fra, til: koTavleHHMM(i_morgen + 14 * T), ressurs: '109'}, NAA);
            const p = koTavleSkjemaKropp({type: 'pause', id: null, ref: NAA}, DATA,
              {fra: koTavleHHMM(NAA), til: koTavleHHMM(NAA + 30 * 60000), ressurs: '101'}, NAA);
            return [d.ref === i_morgen, Date.parse(k.fra) === i_morgen, Date.parse(k.til) - Date.parse(k.fra),
                    k.lokasjon_id, k.ressurs_id, 'lokasjon_id' in p];
        })()""")
        self.assertEqual(ut[:2], [True, True], 'i morgen, ikke nærmeste klokkeslett rundt nå')
        self.assertEqual(ut[2], 14 * 3600000, 'en plan på et sted kan vare mer enn tolv timer')
        self.assertEqual(ut[3:], [2, 109, False])

    def test_oppsettet_har_rullingen(self):
        ut = self._kjor("""
            const h = koTavleOppsettHtml({lokasjoner: [{id: 1, navn: '<b>Park</b>', paa_tavla: true, fulgt: false}],
                                          andel_bak: 10, steg_min: 60});
            console.log(h.includes('id="ko-tavle-andel-bak"') && h.includes('value="10"'), h.includes('value="60"'),
                        h.includes('<b>'));
            console.log(koTavleOppsettHtml({lokasjoner: [], andel_bak: 0}).includes('value="0"'));
        """)
        self.assertEqual(ut, ['true true false', 'true'])

    def test_byggerne_escaper(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._kjor(f"""
            const ond = {json.dumps(ond)};
            const d = JSON.parse(JSON.stringify(DATA));
            d.pauser.forEach((q) => {{ q.ressurs_navn = ond; q.lokasjon_navn = ond; }});
            d.rader[1].navn = ond;
            const rader = koTavleRader(d, koTavleVindu(NAA + 2 * T, 12, 25, null), 'alle');
            console.log(rader.map(koTavleRadHtml).join('')
              + koTavlePlanlagtHtml({{id: 1, naa: true, kl: '22:00', pause: false, sted: ond}})
              + koTavlePlanlagtHtml({{id: 1, naa: false, kl: '22:00', pause: false, sted: ond}})
              + koTavleSkjemaHtml(koTavleSkjemaData({{type: 'pause', id: 51}}, d, NAA))
              + koTavleSkjemaHtml(koTavleSkjemaData({{type: 'pause', id: null, lokasjon_id: 2}}, d, NAA)));
        """)
        self.assertNotIn('<img', ut[0])
        self.assertIn('&lt;img', ut[0])

    # ── Et vindu for seg ────────────────────────────────────────────────────

    def test_bare_et_kjent_vindu_i_adressen(self):
        ut = self._json("""[koEgetVinduNavn('?vindu=tavle'), koEgetVinduNavn('?vindu=plan&x=1'),
                            koEgetVinduNavn('?vindu=%3Cscript%3E'), koEgetVinduNavn(''), koEgetVinduNavn(null),
                            koEgetVinduUrl('tavle'), koEgetVinduUrl('javascript:alert(1)')]""")
        self.assertEqual(ut, ['tavle', 'plan', None, None, None, '/ko/?vindu=tavle', None])


PLAN_HARNESS = (
    (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml')),
    (KO_JS, ('koTavleVindu', 'koTavleIVinduet', 'koTidInnstillinger', 'koTidVindu', 'koTidKontrollHtml',
             'koTavleProsent', 'koTavleTo', 'koTavleHHMM', 'koTavleDognnokkel', 'koTavleDognnavn',
             'koPlanDognstart', 'koPlanKanLede', 'koPlanDognene', 'koPlanSkjemaData', 'koPlanTimene',
             'koPlanBehovPerTime', 'koPlanDekningsgrupper', 'koPlanDekningNokkel', 'koPlanDekningForGruppe',
             'koPlanTidslinje', 'koPlanTidslinjeHtml', 'koPlanDekningHtml', 'koPlanBehovTekst', 'koTegnPlan')),
)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KonsertplanleggerenFolgerTavlaJsTests(SimpleTestCase):
    """«hvis jeg går frem i tid på planlegger tidslinjen skjer det samme med
    tavlen» — prøvd gjennom `koTegnPlan`, og dekningen hentes for vinduet."""

    def test_tegningen_bruker_det_felles_vinduet(self):
        pre = (_konst(KO_JS[3], 'KO_PLAN_TIME') + _konst(KO_JS[3], 'KO_PLAN_DOGN') + """
            const T = 3600000;
            const NAA = new Date(2026, 8, 25, 18, 0).getTime();
            let koTavle = null; let koTidAnker = null; let koTavleKlokkeavvik = 0;
            let koPlanSkjema = null; let koPlanVisning = 'tidslinje'; let koPlanDekning = null;
            let koPlanDekningGruppe = null; let koPlanEtterpaa = null;
            const hentet = [];
            function koHentDekning(timene) { hentet.push(koPlanDekningNokkel(timene)); }
            function koKanFjerne() { return false; }
            let koPlan = {rulling: {timer: 12, andel_bak: 25, steg_min: 120, dognstart: '06:00'}, grupper: [],
              steder: [{id: 1, navn: 'Park'}],
              poster: [{id: 1, lokasjon_id: 1, lokasjon_navn: 'Park', navn: 'I morgen', fra: new Date(NAA + 26 * T).toISOString(),
                        til: new Date(NAA + 27 * T).toISOString(), behov: [], kjennetegn: []}]};
            const ELS = {};
            const nyEl = () => ({ innerHTML: '', textContent: '', dataset: {},
                                  classList: { toggle() {}, add() {}, remove() {} } });
            globalThis.document = { getElementById: (id) => (ELS[id] = ELS[id] || nyEl()), querySelectorAll: () => [] };
        """)
        # Klokka fryses. Med `koTavleKlokkeavvik = NAA - Date.now()` leste
        # `koTegnPlan` klokka noen millisekunder senere, vinduet begynte like
        # etter hel time, og timene ble 13 i stedet for 12 — rødt av og til
        # (23.–24. sep. 2026, først uforklart).
        ut = run_node(build_harness(PLAN_HARNESS), """
            Date.now = () => NAA;
            koTegnPlan();
            const idag = ELS['ko-plan'].innerHTML;
            koTidAnker = NAA + 24 * T;
            koTegnPlan();
            const imorgen = ELS['ko-plan'].innerHTML;
            console.log(idag.includes('I morgen'), imorgen.includes('I morgen'), imorgen.includes('Du ser ikke nå'));
            console.log(JSON.stringify(hentet.map((k) => (Number(k.split('|')[0]) - NAA) / T + '|' + k.split('|')[1])));
        """, preamble=pre).splitlines()
        self.assertEqual(ut[0], 'false true true')
        # 15:00 (¼ av tolv timer før 18) og 13 timer; så i morgen fra 18:00.
        self.assertEqual(json.loads(ut[1]), ['-3|12', '24|12'])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class HendelsenIEgetVinduJsTests(SimpleTestCase):
    """André, 23. sep. 2026: «Når vi skal åpne en hendelse som ligger i
    loggstrøms vinduets plass og vil åpne som et eget vindu så åpner du
    loggstrøms vinduet istedenfor.» Prøvd gjennom knappens egen inngang,
    `koApneEgetVindu`."""

    HARNESS = (
        (KO_JS, ('koEgetVinduNavn', 'koEgetVinduHendelse', 'koEgetVinduUrl', 'koAapenHendelseILoggen',
                 'koApneEgetVindu', 'koLoggVinduTittel', 'koOppsettStart', 'koTegnEgetVindu', 'koVinduElement',
                 'koSettKonsollhoyde')),
    )

    def _kjor(self, kode):
        pre = _konst(LAYOUT_JS, 'KO_VINDUER') + """
            let koApenHendelseId = null; let koOppsett = null;
            const aapnet = []; let lukket = 0; let skjult = [];
            globalThis.window = { open: (url, navn) => aapnet.push([url, navn]) };
            function koLukkDetalj() { lukket += 1; koApenHendelseId = null; }
            function koLesOppsett() { return {skjult: []}; }
            function koSkjul(o, navn) { skjult.push(navn); return {skjult: [navn]}; }
            function koLagreOppsett() {}
            function koTegnOppsett() {}
        """
        ut = run_node(build_harness(self.HARNESS), kode, preamble=pre).splitlines()
        return ut[:-1] if ut and ut[-1] == 'OK' else ut

    def test_hendelsen_som_staar_aapen_faar_vinduet_og_stroemmen_blir(self):
        ut = self._kjor("""
            koApenHendelseId = 12;
            koApneEgetVindu('logg');
            console.log(JSON.stringify([aapnet, lukket, skjult]));
        """)
        self.assertEqual(json.loads(ut[0]), [[['/ko/?vindu=logg&hendelse=12', 'ko-hendelse-12']], 1, []],
                         'hendelsen i eget vindu, lukket her, og loggvinduet ikke skjult')

    def test_uten_aapen_hendelse_er_det_loggstroemmen(self):
        ut = self._kjor("""
            koApneEgetVindu('logg');
            koApenHendelseId = 12;
            koApneEgetVindu('tavle');
            console.log(JSON.stringify([aapnet, lukket, skjult]));
        """)
        self.assertEqual(json.loads(ut[0]), [[['/ko/?vindu=logg', 'ko-logg'], ['/ko/?vindu=tavle', 'ko-tavle']],
                                             0, ['logg', 'tavle']],
                         'en åpen hendelse gjelder bare loggvinduet')

    def test_adressen_leses_som_data(self):
        ut = self._kjor("""
            console.log(JSON.stringify([koEgetVinduHendelse('?vindu=logg&hendelse=12'),
              koEgetVinduHendelse('?vindu=tavle&hendelse=12'), koEgetVinduHendelse('?vindu=logg&hendelse=0'),
              koEgetVinduHendelse('?vindu=logg&hendelse=12abc'), koEgetVinduHendelse('?vindu=logg&hendelse=-3'),
              koEgetVinduHendelse('?vindu=logg'), koEgetVinduHendelse(null),
              koEgetVinduUrl('logg', 7), koEgetVinduUrl('tavle', 7), koEgetVinduUrl('logg', '7'),
              koLoggVinduTittel({kode: 'H3', tittel: 'Fall'}), koLoggVinduTittel(null)]));
        """)
        self.assertEqual(json.loads(ut[0]), [12, None, None, None, None, None, None,
                                             '/ko/?vindu=logg&hendelse=7', '/ko/?vindu=tavle', '/ko/?vindu=logg',
                                             'H3 · Fall · KO', 'Loggstrøm · KO'])

    def test_siden_aapner_hendelsen_fra_adressen_ved_oppstart(self):
        """Kallstedet i `koOppsettStart`, ikke bare lesingen av adressen."""
        ut = self._kjor("""
            let koEgetVinduAktivt = null;
            globalThis.document = { getElementById: () => null, querySelector: () => null,
                                    querySelectorAll: () => [], title: '' };
            window.location = { search: '?vindu=logg&hendelse=5' };
            window.addEventListener = () => {};
            koOppsettStart();
            console.log(koApenHendelseId, koEgetVinduAktivt);
            koApenHendelseId = null;
            window.location = { search: '?vindu=tavle&hendelse=5' };
            koOppsettStart();
            console.log(koApenHendelseId, koEgetVinduAktivt);
        """)
        self.assertEqual(ut, ['5 logg', 'null tavle'])
