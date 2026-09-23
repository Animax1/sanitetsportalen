"""Planleggeren og programmet i nettleseren (`static/js/ko-plan.js` og
båndene i `ko-tavle.js`, 23. sep. 2026).

Reglene er egne funksjoner fordi de *avgjør* noe: hvilket døgn et klokkeslett
hører til, når en konsert slutter, hva skjemaet sender. Data i den formen
`/ko/api/program/` og `/ko/api/tavle/` gir, bygget i **lokal tid** i node, så
prøvene sier det samme på UTC og i Norge.
"""
import json
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import (KO_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, run_node)

PLAN_JS = KO_JS[3]
TAVLE_JS = KO_JS[2]

HARNESS = (
    (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml')),
    (KO_JS, ('koTavleKanSkrive', 'koTavleVindu', 'koTavleProsent', 'koTavleTo', 'koTavleHHMM',
             'koTavleDognnokkel', 'koTavleDognnavn', 'koTavleTidNaer', 'koTavleProgram',
             'koTavleKonsertHtml', 'koTavleRadHtml', 'koTavleStolpeHtml', 'koTavlePauseKildetekst', 'koTavleSluttHtml',
             'koTavleSkjemaData', 'koTavleSkjemaHtml', 'koTavleSkjemaKropp', 'koTavleVarighet',
             'koTavleRader', 'koTavleSynlig', 'koTavleKanDras', 'koTavlePauseStatus', 'koTavleSlutt',
             'koTavleBehovNaa', 'koTavleBehovHtml',
             'koPlanDognene', 'koPlanTid', 'koPlanTil', 'koPlanGruppert', 'koPlanBehovTekst',
             'koPlanKropp', 'koPlanBeredskapHtml', 'koPlanPostHtml', 'koPlanListeHtml',
             'koPlanDognvalgHtml', 'koPlanSkjemaData', 'koPlanSkjemaHtml', 'koPlanSteder',
             'koPlanDognstart',
             # Steg 4: tidslinja og dekningen.
             'koPlanDognVindu', 'koPlanTimeStart', 'koPlanTidslinje', 'koPlanBehovPerTime', 'koPlanDekningForGruppe',
             'koPlanDekningsgrupper', 'koPlanTidslinjeHtml', 'koPlanDekningHtml',
             # Steg 5: etterpå.
             'koPlanFaktiskTekst', 'koPlanEndringTekst', 'koPlanEtterpaaHtml')),
)

FORSPILL = """
const L = (d, t, m = 0) => new Date(2026, 8, d, t, m).getTime();
const I = (ms) => new Date(ms).toISOString();
let koTavle = { dognstart: '06:00' };
let koKanSkriveSvar = true;
function koKanSkrive() { return koKanSkriveSvar; }
const POST = (id, sted, stedId, fra, til, extra = {}) => Object.assign({
  id, lokasjon_id: stedId, lokasjon_navn: sted, navn: 'Konsert ' + id, konserttype_id: 1,
  konserttype_navn: 'Headliner', beredskap: 'oransje', beredskap_navn: 'Oransje',
  fra: I(fra), til: I(til), publikum: null, kjennetegn: [], behov: []}, extra);
"""


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class PlanreglerTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(HARNESS)
        self.pre = (_konst(PLAN_JS, 'KO_PLAN_DOGN') + _konst(PLAN_JS, 'KO_PLAN_TIME')
                    + _konst(TAVLE_JS, 'KO_TAVLE_LENGE_MIN')
                    + _konst(TAVLE_JS, 'KO_TAVLE_BEHOV_FORVARSEL_MIN')
                    + _konst(TAVLE_JS, 'KO_TAVLE_PAUSE_FORVARSEL_MIN') + 'let koTavleValgt = null;\n' + FORSPILL)

    def _kjor(self, kode):
        return run_node(self.harness, kode, preamble=self.pre).splitlines()

    def _json(self, uttrykk):
        return json.loads(self._kjor(f'console.log(JSON.stringify({uttrykk}));')[0])

    # ── Tidene ─────────────────────────────────────────────────────────────

    def test_foer_doegnstarten_hoerer_til_natta_etter(self):
        ut = self._json("""[
            koPlanTid('2026-09-25', '22:00', '06:00') === L(25, 22),
            koPlanTid('2026-09-25', '01:30', '06:00') === L(26, 1, 30),
            koPlanTid('2026-09-25', '06:00', '06:00') === L(25, 6),
            koPlanTid('2026-09-25', '05:59', '06:00') === L(26, 5, 59),
            koPlanTid('2026-09-25', '25:00', '06:00'), koPlanTid('tull', '22:00', '06:00'),
            koPlanTid('2026-09-25', '', '06:00'),
        ]""")
        self.assertEqual(ut, [True, True, True, True, None, None, None])

    def test_til_er_foerste_gang_klokka_viser_det_etter_fra(self):
        ut = self._json("""[
            koPlanTil(L(25, 22), '00:30') === L(26, 0, 30),
            koPlanTil(L(25, 22), '23:00') === L(25, 23),
            koPlanTil(L(25, 22), '22:00') === L(26, 22),
            koPlanTil(L(25, 22), 'x'),
        ]""")
        self.assertEqual(ut, [True, True, True, None], '22–22 er et døgn, ikke null')

    def test_doegnene_fra_start_og_hvert_doegn_med_en_konsert(self):
        ut = self._json("""koPlanDognene([POST(1, 'Park', 1, L(30, 20), L(30, 22)),
                                            POST(2, 'Park', 1, L(25, 1), L(25, 2))],
                                           L(24, 14), L(24, 15), '06:00')""")
        self.assertEqual(ut[:5], ['2026-09-24', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-28'])
        self.assertIn('2026-09-30', ut, 'et døgn med en konsert er alltid med')
        self.assertEqual(ut, sorted(ut))
        self.assertEqual(ut.count('2026-09-24'), 1, 'kl. 01 natt til 25. hører til 24.')

    # ── Lista ──────────────────────────────────────────────────────────────

    def test_gruppert_paa_sted_i_tidsrekkefolge_og_bare_valgt_doegn(self):
        ut = self._json("""koPlanGruppert([
            POST(1, 'Hovedscene', 1, L(25, 22), L(26, 0)),
            POST(2, 'Scene 2', 2, L(25, 18), L(25, 19)),
            POST(3, 'Hovedscene', 1, L(25, 16), L(25, 17)),
            POST(4, 'Hovedscene', 1, L(26, 16), L(26, 17)),
            POST(5, 'Scene 2', 2, L(26, 1), L(26, 2)),
        ], '2026-09-25', '06:00').map((g) => [g.sted, g.poster.map((p) => p.id)])""")
        self.assertEqual(ut, [['Hovedscene', [3, 1]], ['Scene 2', [2, 5]]])

    def test_behovet_som_tekst(self):
        self.assertEqual(self._json("koPlanBehovTekst([{gruppe_navn: 'Lag', antall: 4},"
                                    " {gruppe_navn: 'Ambulanse', antall: 2}])"), '4 Lag · 2 Ambulanse')

    def test_bare_lederen_faar_aapne_en_konsert(self):
        ut = self._kjor("""
            const p = POST(7, 'Park', 1, L(25, 22), L(26, 0));
            console.log(koPlanPostHtml(p, true)); console.log(koPlanPostHtml(p, false));
            console.log(koPlanListeHtml([], true)); console.log(koPlanListeHtml([], false));
        """)
        self.assertIn('data-action="koPlanApne" data-arg="7"', ut[0])
        self.assertNotIn('data-action', ut[1])
        self.assertIn('+ Konsert', ut[2])
        self.assertNotIn('+ Konsert', ut[3])

    def test_ukjent_beredskap_faar_ingen_farge(self):
        ut = self._kjor("""
            console.log(koPlanBeredskapHtml({beredskap: 'rod', beredskap_navn: 'Rød'}));
            console.log(JSON.stringify(koPlanBeredskapHtml({beredskap: 'lilla" onmouseover="x', beredskap_navn: 'x'})));
        """)
        self.assertIn('ko-beredskap-rod', ut[0])
        self.assertEqual(ut[1], '""')

    # ── Skjemaet ───────────────────────────────────────────────────────────

    def test_kroppen_bygges_av_feltene_og_null_er_ingen(self):
        ut = self._json("""koPlanKropp({lokasjon_id: '3', navn: ' Headliner ', dogn: '2026-09-25', fra: '22:00',
            til: '00:30', konserttype_id: '', beredskap: 'rod', publikum: '800', kjennetegn: ['5', '6'],
            behov: {10: '4', 20: '', 30: '0', 40: '2'}}, '06:00').kropp""")
        self.assertEqual(ut['lokasjon_id'], 3)
        self.assertEqual(ut['navn'], 'Headliner')
        self.assertIsNone(ut['konserttype_id'])
        self.assertEqual(ut['publikum'], 800)
        self.assertEqual(ut['kjennetegn'], [5, 6])
        self.assertEqual(ut['behov'], [{'gruppe_id': 10, 'antall': 4}, {'gruppe_id': 40, 'antall': 2}])
        span = self._json("""(() => { const k = koPlanKropp({lokasjon_id: '3', navn: 'x', dogn: '2026-09-25',
            fra: '22:00', til: '00:30', behov: {}}, '06:00').kropp;
            return [Date.parse(k.fra) === L(25, 22), Date.parse(k.til) === L(26, 0, 30)]; })()""")
        self.assertEqual(span, [True, True])

    def test_det_som_mangler_sies_ved_knappen(self):
        grunn = "{lokasjon_id: '3', navn: 'x', dogn: '2026-09-25', fra: '22:00', til: '23:00', behov: {}}"
        tilfeller = {
            "Object.assign(G, {lokasjon_id: ''})": 'Velg stedet.',
            "Object.assign(G, {navn: '  '})": 'Konserten må ha et navn.',
            "Object.assign(G, {fra: 'nå'})": 'Fyll inn klokkeslettene som TT:MM.',
            "Object.assign(G, {til: ''})": 'Fyll inn klokkeslettene som TT:MM.',
            "Object.assign(G, {publikum: 'mange'})": 'Forventet publikum må være et tall.',
            "Object.assign(G, {behov: {10: '-1'}})": 'Behovet må være hele tall.',
            "Object.assign(G, {behov: {10: '2.5'}})": 'Behovet må være hele tall.',
        }
        for uttrykk, melding in tilfeller.items():
            with self.subTest(uttrykk):
                self.assertEqual(self._json(f"(() => {{ const G = {grunn}; return koPlanKropp({uttrykk}, '06:00').feil; }})()"),
                                 melding)

    def test_skjemaet_fylles_fra_posten_og_en_ny_starter_i_valgt_doegn(self):
        ut = self._json("""(() => {
            const data = {poster: [POST(7, 'Park', 1, L(26, 1), L(26, 2), {behov: [{gruppe_id: 10, gruppe_navn: 'Lag', antall: 4}],
                                   kjennetegn: [{id: 5, navn: 'Pyro'}]})]};
            const e = koPlanSkjemaData({id: 7}, data, '2026-09-24');
            const n = koPlanSkjemaData({id: null}, data, '2026-09-24');
            return [e.dogn, e.fra, e.til, e.behov, e.kjennetegn, n.dogn, n.navn, koPlanSkjemaData({id: 99}, data, 'x')];
        })()""")
        self.assertEqual(ut, ['2026-09-25', '01:00', '02:00', {'10': 4}, [5], '2026-09-24', '', None])

    def test_et_inaktivt_sted_posten_staar_paa_tilbys_likevel(self):
        ut = self._json("""(() => {
            const data = {steder: [{id: 1, navn: 'Park'}], poster: [POST(7, 'Gammel scene', 9, L(25, 22), L(25, 23))]};
            return [koPlanSteder(data, 9).map((s) => s.id), koPlanSteder(data, 1).map((s) => s.id)];
        })()""")
        self.assertEqual(ut, [[1, 9], [1]])

    def test_byggerne_escaper(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._kjor(f"""
            const ond = {json.dumps(ond)};
            const p = POST(1, ond, 1, L(25, 22), L(25, 23), {{navn: ond, konserttype_navn: ond, beredskap_navn: ond,
              kjennetegn: [{{id: 1, navn: ond}}], behov: [{{gruppe_id: 1, gruppe_navn: ond, antall: 2}}]}});
            const data = {{poster: [p], konserttyper: [{{id: 1, navn: ond, er_aktiv: true}}],
              kjennetegn: [{{id: 1, navn: ond, er_aktiv: true}}], grupper: [{{id: 1, navn: ond}}],
              beredskap: [{{verdi: 'rod', navn: ond}}]}};
            console.log(koPlanListeHtml(koPlanGruppert([p], '2026-09-25', '06:00'), true)
              + koPlanSkjemaHtml(koPlanSkjemaData({{id: 1}}, data, '2026-09-25'), data, [{{id: 1, navn: ond}}], ['2026-09-25'])
              + koPlanDognvalgHtml(['2026-09-25'], '2026-09-25'));
            const vindu = koTavleVindu(L(25, 22, 30), 12);
            console.log(koTavleRadHtml({{id: 1, navn: ond, pause: false, stolper: [], baner: 1, naa: 0, over: 0,
              program: koTavleProgram({{program: [p]}}, 1, vindu)}}));
        """)
        for linje in ut[:2]:
            self.assertNotIn('<img', linje)
            self.assertIn('&lt;img', linje)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class ProgrammetPaaTavlaJsTests(PlanreglerTests):
    """Båndene bak radene og «følg konserten» i skjemaet."""

    def test_baandene_i_raden_sin_innenfor_vinduet(self):
        ut = self._json("""(() => {
            const data = {program: [POST(1, 'Park', 1, L(25, 20), L(25, 23)), POST(2, 'Club', 2, L(25, 21), L(25, 22)),
                                    POST(3, 'Park', 1, L(24, 6), L(24, 7)), POST(4, 'Park', 1, L(25, 22), L(26, 1),
                                    {beredskap: 'lilla'})]};
            const v = koTavleVindu(L(25, 22), 12);
            return koTavleProgram(data, 1, v).map((k) => [k.id, k.beredskap, k.venstre < 100 - k.hoyre]);
        })()""")
        self.assertEqual(ut, [[1, 'oransje', True], [4, '', True]],
                         'bare denne raden, bare det som overlapper vinduet, og ukjent nivå uten farge')

    def test_baandet_ligger_bak_stolpene_og_bærer_teksten(self):
        ut = self._kjor("""
            const v = koTavleVindu(L(25, 22), 12);
            const k = koTavleProgram({program: [POST(1, 'Park', 1, L(25, 20), L(25, 23))]}, 1, v);
            const html = koTavleRadHtml({id: 1, navn: 'Park', pause: false, baner: 1, naa: 1, over: 0, program: k,
              stolper: [{ressurs_id: 1, navn: 'Lag 1', merke: '', venstre: 10, hoyre: 33, bane: 0, aapen: true,
                         opptatt: false, hendelse: false, bil: false, varighet: '', lenge: false, dras: false,
                         plassering_id: 1, pause_id: null, pause_status: '', slutt: null}]});
            console.log(html.indexOf('ko-tavle-konsert') < html.indexOf('ko-tavle-stolpe'));
            console.log(html.includes('ko-beredskap-oransje'));
            console.log(html.includes('Beredskap oransje'));
        """)
        self.assertEqual(ut[:3], ['true', 'true', 'true'])

    def test_raden_faar_programmet_gjennom_den_ekte_inngangen(self):
        """**Kallstedet**, ikke bare hjelperen: `koTavleRader` må gi raden
        programmet sitt, ellers tegnes ingen bånd (funnet ved mutasjon)."""
        ut = self._kjor("""
            const data = {rader: [{id: 1, navn: 'Park'}], ressurser: [], plasseringer: [], pauser: [],
                          program: [POST(1, 'Park', 1, L(25, 20), L(25, 23))]};
            const rader = koTavleRader(data, koTavleVindu(L(25, 22), 12), 'alle');
            const park = rader.find((r) => r.id === 1);
            console.log(park.program.length, rader.find((r) => r.pause).program.length);
            console.log(koTavleRadHtml(park).includes('ko-tavle-konsert'));
        """)
        self.assertEqual(ut[0], '1 0', 'Pause-raden har aldri et program')
        self.assertEqual(ut[1], 'true')

    SKJEMA = """
        const data = {program: [POST(1, 'Park', 1, L(25, 20), L(25, 23)), POST(2, 'Park', 1, L(25, 18), L(25, 19)),
                                POST(3, 'Club', 2, L(25, 20), L(25, 23))],
          plasseringer: [{id: 9, ressurs_id: 101, ressurs_navn: 'Lag 1', lokasjon_id: 1, lokasjon_navn: 'Park',
                          pause: false, hendelse_nummer: null, fra: I(L(25, 21)), til: null,
                          planlagt_til: null, folger_id: FOLGER}]};
        const NAA = L(25, 22);
    """

    def test_skjemaet_tilbyr_konsertene_paa_stedet_som_ikke_er_over(self):
        ut = self._kjor(self.SKJEMA.replace('FOLGER', '1') + """
            const d = koTavleSkjemaData({type: 'rett', id: 9}, data, NAA);
            console.log(JSON.stringify(d.konserter.map((k) => k.id)), d.folger);
            const html = koTavleSkjemaHtml(d);
            console.log(html.includes('id="ko-tavle-skjema-folger"'), /value="1" selected/.test(html));
        """)
        self.assertEqual(ut[0], '[1] 1', 'ikke den som er over, og ikke et annet sted')
        self.assertEqual(ut[1], 'true true')

    def test_uten_konserter_paa_stedet_ingen_nedtrekk(self):
        ut = self._kjor(self.SKJEMA.replace('FOLGER', 'null') + """
            data.program = [];
            console.log(koTavleSkjemaHtml(koTavleSkjemaData({type: 'rett', id: 9}, data, NAA)).includes('skjema-folger'));
        """)
        self.assertEqual(ut[0], 'false')

    def test_folg_sender_konserten_og_ikke_egen_tid(self):
        ut = self._kjor(self.SKJEMA.replace('FOLGER', 'null') + """
            console.log(JSON.stringify(koTavleSkjemaKropp({type: 'rett', id: 9}, data,
              {fra: '21:00', folger: '1', slutt: '23:59'}, NAA)));
            console.log(JSON.stringify(koTavleSkjemaKropp({type: 'rett', id: 9}, data,
              {fra: '21:00', folger: '', slutt: ''}, NAA)));
        """)
        med, uten = json.loads(ut[0]), json.loads(ut[1])
        self.assertEqual(med['folger_id'], 1)
        self.assertNotIn('planlagt_til', med)
        self.assertNotIn('folger_id', uten)
        self.assertIsNone(uten['planlagt_til'])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class BehovIDriftJsTests(PlanreglerTests):
    """Steg 3: «Lag 2/4» på raden — behovet til konsertene som pågår (eller
    begynner innen forvarselet), mot det som står der nå."""

    DATA = """
        const BEHOV = [{gruppe_id: 10, gruppe_navn: 'Lag', antall: 3}, {gruppe_id: 20, gruppe_navn: 'Ambulanse', antall: 1}];
        const data = {
          rader: [{id: 1, navn: 'Park'}, {id: 2, navn: 'Club'}], pauser: [],
          grupper: [{id: 10, navn: 'Lag'}, {id: 20, navn: 'Ambulanse'}],
          ressurser: [
            {id: 101, navn: 'Lag 1', gruppe_id: 10, bil: false, opptatt: null},
            {id: 102, navn: 'Lag 2', gruppe_id: 10, bil: false, opptatt: null},
            {id: 103, navn: 'Lag 3', gruppe_id: 10, bil: false, opptatt: {merke: 'På H1', tekst: '', lokasjon_id: 1,
                                                                        fra: I(L(25, 21)), hendelse_id: 1}},
            {id: 104, navn: 'Lag 4', gruppe_id: 10, bil: false, opptatt: null},
            {id: 201, navn: 'Amb 1', gruppe_id: 20, bil: true, opptatt: null},
          ],
          plasseringer: [
            {id: 1, ressurs_id: 101, lokasjon_id: 1, pause: false, fra: I(L(25, 20)), til: null},
            {id: 2, ressurs_id: 102, lokasjon_id: 1, pause: false, fra: I(L(25, 19)), til: I(L(25, 20))},
            {id: 3, ressurs_id: 104, lokasjon_id: 2, pause: false, fra: I(L(25, 20)), til: null},
            {id: 4, ressurs_id: 201, lokasjon_id: 1, pause: false, fra: I(L(25, 20)), til: null},
          ],
          program: [POST(1, 'Park', 1, L(25, 21), L(25, 23), {behov: BEHOV})],
        };
        const B = (naa) => JSON.stringify(koTavleBehovNaa(data, 1, naa).map((b) => [b.navn, b.har, b.trengs, b.mangler, b.kommer]));
    """

    def test_teller_det_som_staar_der_naa_ogsaa_paa_hendelse(self):
        ut = self._kjor(self.DATA + 'console.log(B(L(25, 22)));')
        # Lag 1 åpen på Park, Lag 3 på en hendelse på Park. Lag 2 er gått, Lag 4 er på Club.
        self.assertEqual(json.loads(ut[0]), [['Lag', 2, 3, True, False], ['Ambulanse', 1, 1, False, False]])

    def test_foer_forvarselet_og_etter_slutt_ingenting_innenfor_kommer(self):
        ut = self._kjor(self.DATA + """
            console.log(B(L(25, 20, 29))); console.log(B(L(25, 20, 30))); console.log(B(L(25, 23)));
        """)
        self.assertEqual(ut[0], '[]', 'mer enn 30 min før')
        self.assertEqual(json.loads(ut[1])[0][4], True, 'innen forvarselet: kommer')
        self.assertEqual(ut[2], '[]', 'konserten er over')

    def test_to_konserter_legges_sammen_og_et_annet_sted_teller_ikke(self):
        ut = self._kjor(self.DATA + """
            data.program.push(POST(2, 'Park', 1, L(25, 22), L(25, 23), {behov: [{gruppe_id: 10, gruppe_navn: 'Lag', antall: 2}]}));
            data.program.push(POST(3, 'Club', 2, L(25, 21), L(25, 23), {behov: [{gruppe_id: 10, gruppe_navn: 'Lag', antall: 9}]}));
            console.log(B(L(25, 22, 30)));
        """)
        self.assertEqual(json.loads(ut[0])[0][:3], ['Lag', 2, 5])

    def test_gruppa_matches_paa_navn_naar_id_en_er_borte(self):
        ut = self._kjor(self.DATA + """
            data.program[0].behov = [{gruppe_id: null, gruppe_navn: 'Lag', antall: 1}];
            console.log(B(L(25, 22)));
        """)
        self.assertEqual(json.loads(ut[0]), [['Lag', 2, 1, False, False]])

    def test_gjennom_den_ekte_inngangen_og_pause_raden_har_ingen(self):
        ut = self._kjor(self.DATA + """
            const rader = koTavleRader(data, koTavleVindu(L(25, 22), 12), 'alle');
            const park = rader.find((r) => r.id === 1);
            console.log(JSON.stringify([park.behov.length, rader.find((r) => r.pause).behov.length]));
            console.log(koTavleRadHtml(park));
        """)
        self.assertEqual(json.loads(ut[0]), [2, 0])
        self.assertIn('ko-tavle-behov-mangler', ut[1])
        self.assertIn('Lag 2/3', ut[1])
        self.assertIn('ko-tavle-behov-ok', ut[1])

    def test_behovet_escapes(self):
        ut = self._kjor("""
            console.log(koTavleBehovHtml([{navn: '<img src=x>', har: 1, trengs: 2, mangler: true, kommer: false}]));
        """)
        self.assertNotIn('<img', ut[0])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TidslinjeOgDekningJsTests(PlanreglerTests):
    """Steg 4: døgnet som tidslinje, og dekningsstripa — behovet time for time
    mot vaktlistas tall."""

    POSTER = """
        const B = (lag, amb) => [{gruppe_id: 10, gruppe_navn: 'Lag', antall: lag}].concat(
          amb ? [{gruppe_id: 20, gruppe_navn: 'Ambulanse', antall: amb}] : []);
        const poster = [
          POST(1, 'Scene 2', 2, L(25, 22), L(25, 23), {behov: B(2, 1)}),
          POST(2, 'Hovedscene', 1, L(25, 22, 30), L(25, 23, 30), {behov: B(4)}),
          POST(3, 'Hovedscene', 1, L(25, 23), L(26, 1), {behov: B(1)}),
          POST(4, 'Hovedscene', 1, L(26, 7), L(26, 8), {behov: B(9)}),
          POST(5, 'Teltet', 3, L(25, 20), L(25, 21), {behov: [{gruppe_id: null, gruppe_navn: 'Borte', antall: 5}]}),
        ];
        const steder = [{id: 1, navn: 'Hovedscene'}, {id: 2, navn: 'Scene 2'}, {id: 3, navn: 'Teltet'}];
        const V = koPlanDognVindu('2026-09-25', '06:00');
    """

    def test_doegnvinduet(self):
        ut = self._json("(() => { const v = koPlanDognVindu('2026-09-25', '06:00');"
                        " return [v.fra === L(25, 6), v.til === L(26, 6), koPlanDognVindu('x', '06:00')]; })()")
        self.assertEqual(ut, [True, True, None])

    def test_radene_i_stedsrekkefolge_med_baner_og_bare_doegnet(self):
        ut = self._json("(() => {" + self.POSTER + """
            return koPlanTidslinje(poster, V, steder).map((r) => [r.sted, r.baner, r.poster.map((x) => [x.post.id, x.bane])]);
        })()""")
        self.assertEqual(ut, [['Hovedscene', 2, [[2, 0], [3, 1]]], ['Scene 2', 1, [[1, 0]]], ['Teltet', 1, [[5, 0]]]],
                         '23:00 overlapper 22:30–23:30 og får ny bane; neste døgns 07:00 er ikke med')

    def test_behovet_teller_i_hver_time_konserten_beroerer(self):
        ut = self._json("(() => {" + self.POSTER + """
            const t = koPlanBehovPerTime(poster, V);
            return [16, 17, 18, 14].map((i) => [t[i].get('10') || 0, t[i].get('20') || 0]).concat([[t[14].size]]);
        })()""")
        # 22-timen: Scene 2 (2) + Hovedscene 22:30 (4). 23-timen: Hovedscene 22:30–23:30 (4) + 23:00 (1).
        self.assertEqual(ut[:4], [[6, 1], [5, 0], [1, 0], [0, 0]])
        self.assertEqual(ut[4], [0], 'en gruppe uten id telles ikke — heller ikke som «null»')

    def test_stripa_er_for_faa_bare_naar_vaktlistas_tall_er_kjent(self):
        ut = self._json("(() => {" + self.POSTER + """
            const t = koPlanBehovPerTime(poster, V);
            const timer = Array.from({length: 24}, (_, i) => ({grupper: i === 16 ? {'10': 5} : (i === 18 ? {'10': 1} : {'10': 9})}));
            const med = koPlanDekningForGruppe(t, timer, 10);
            const uten = koPlanDekningForGruppe(t, null, 10);
            return [med[16], med[17], uten[16].kort, uten[16].har, med[18]];
        })()""")
        self.assertEqual(ut[0], {'i': 16, 'trengs': 6, 'har': 5, 'pause': 0, 'kort': True})
        self.assertEqual(ut[1]['kort'], False)
        self.assertEqual(ut[2:4], [False, None])
        self.assertEqual(ut[4], {'i': 18, 'trengs': 1, 'har': 1, 'pause': 0, 'kort': False}, 'akkurat nok er nok')

    def test_pausen_forklarer_tallet_i_stripa(self):
        """Serveren har alt trukket laget i pause fra `grupper`; `pause` står
        for å si hvorfor (23. sep. 2026)."""
        ut = self._kjor(self.POSTER + """
            const t = koPlanBehovPerTime(poster, V);
            const timer = Array.from({length: 24}, (_, i) => ({grupper: {'10': 3}, pause: i === 16 ? {'10': 2} : {}}));
            const s = koPlanDekningForGruppe(t, timer, 10);
            console.log(JSON.stringify([s[16].pause, s[16].har, s[17].pause]));
            const html = koPlanDekningHtml(s, [{id: 10, navn: 'Lag'}], 10, V, null);
            console.log(html.includes('(2 i pause)'), (html.match(/i pause\)/g) || []).length);
            console.log(koPlanDekningForGruppe(t, [{grupper: {}}], 10)[0].pause);
        """)
        self.assertEqual(json.loads(ut[0]), [2, 3, 0])
        self.assertEqual(ut[1], 'true 1')
        self.assertEqual(ut[2], '0', 'et gammelt svar uten `pause` er ingen pause')

    def test_stripa_tilbyr_bare_grupper_med_behov(self):
        ut = self._json("(() => {" + self.POSTER + """
            const g = koPlanDekningsgrupper(koPlanBehovPerTime(poster, V),
              [{id: 30, navn: 'Samleplass'}, {id: 20, navn: 'Ambulanse'}, {id: 10, navn: 'Lag'}]);
            return g.map((x) => x.navn);
        })()""")
        self.assertEqual(ut, ['Ambulanse', 'Lag'])

    def test_byggerne_naa_streken_lederen_og_meldingene(self):
        ut = self._kjor(self.POSTER + """
            const rader = koPlanTidslinje(poster, V, steder);
            console.log(koPlanTidslinjeHtml(rader, V, true, L(25, 22)).includes('ko-plan-naa'));
            console.log(koPlanTidslinjeHtml(rader, V, true, L(27, 22)).includes('ko-plan-naa'));
            console.log(koPlanTidslinjeHtml(rader, V, false, L(25, 22)).includes('data-action'));
            console.log(koPlanDekningHtml([], [], null, V, 'Krever vaktlista.'));
            console.log(koPlanDekningHtml([], [], null, V, null).includes('Ingen behov'));
            const s = koPlanDekningForGruppe(koPlanBehovPerTime(poster, V),
              Array.from({length: 24}, () => ({grupper: {'10': 1}})), 10);
            console.log(koPlanDekningHtml(s, [{id: 10, navn: 'Lag'}], 10, V, null).includes('ko-plan-kort'));
        """)
        self.assertEqual(ut[:3], ['true', 'false', 'false'])
        self.assertIn('Krever vaktlista.', ut[3])
        self.assertEqual(ut[4:6], ['true', 'true'])

    def test_byggerne_escaper(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._kjor(self.POSTER + f"""
            const ond = {json.dumps(ond)};
            poster[0].navn = ond; poster[0].lokasjon_navn = ond; poster[0].beredskap_navn = ond;
            poster[0].behov = [{{gruppe_id: 10, gruppe_navn: ond, antall: 1}}];
            console.log(koPlanTidslinjeHtml(koPlanTidslinje(poster, V, steder), V, true, L(25, 22))
              + koPlanDekningHtml(koPlanDekningForGruppe(koPlanBehovPerTime(poster, V), null, 10),
                                  [{{id: 10, navn: ond}}], 10, V, null)
              + koPlanDekningHtml([], [], null, V, ond));
        """)
        self.assertNotIn('<img', ut[0])
        self.assertIn('&lt;img', ut[0])


class EtterpaaJsTests(PlanreglerTests):
    """Plan mot faktisk og historikken (steg 5)."""

    DATA = """
    const RAD = (extra = {}) => Object.assign({id: 1, navn: 'Headliner', sted: 'Parkscene', tid: '25.09 22:00–00:30',
      type: 'Headliner', beredskap: 'oransje', beredskap_navn: 'Oransje', publikum: null,
      behov: [{gruppe_navn: 'Lag', trengs: 4, snitt: 3.5, under_min: 30}], behov_opprinnelig: '4 Lag',
      behov_naa: '4 Lag', startet: true, oppdrag: 2, endringer: 0}, extra);
    const DATA = (extra = {}) => Object.assign({vakt: {id: 7, navn: 'Festival 2025'}, poster: [RAD()], endringer: [],
      vakter: [{id: 8, navn: 'Festival 2026'}, {id: 7, navn: 'Festival 2025'}]}, extra);
    """

    def test_faktisk_som_tekst(self):
        ut = self._json("""[
            koPlanFaktiskTekst({snitt: 3.5, under_min: 30}, true),
            koPlanFaktiskTekst({snitt: 4, under_min: 0}, true),
            koPlanFaktiskTekst({snitt: 4, under_min: 0}, false),
            koPlanFaktiskTekst({snitt: null, under_min: 0}, true),
        ]""")
        self.assertEqual(ut, ['3,5 i snitt · 30 min under', '4 i snitt', 'ikke begynt', 'ikke begynt'])

    def test_endringen_som_tekst(self):
        ut = self._json("""[
            koPlanEndringTekst({navn: 'X', hva: 'endret', detaljer: [{felt: 'beredskap', fra: 'Gul', til: 'Rød'},
                                                                   {felt: 'behov', fra: '', til: '2 Lag'}]}),
            koPlanEndringTekst({navn: 'X', hva: 'opprettet', detaljer: {sted: 'Park', tid: '22:00', beredskap: 'Gul'}}),
            koPlanEndringTekst({navn: 'X', hva: 'slettet', detaljer: {}}),
        ]""")
        self.assertEqual(ut, ['X: beredskap Gul → Rød, behov – → 2 Lag',
                              'X lagt til · Park · 22:00 · beredskap gul', 'X slettet'])

    def test_vaktvelger_og_kopiering_bare_for_lederen_og_ikke_paa_aktiv_vakt(self):
        ut = self._kjor(self.DATA + """
            const h = (d, leder, aktiv) => koPlanEtterpaaHtml(d, leder, aktiv);
            console.log(h(DATA(), true, 8).includes('ko-plan-vakt'));
            console.log(h(DATA(), false, 8).includes('ko-plan-vakt'));
            console.log(h(DATA({vakter: [{id: 7, navn: 'x'}]}), true, 7).includes('ko-plan-vakt'));
            console.log(h(DATA(), true, 8).includes('koPlanKopier'));
            console.log(h(DATA(), false, 8).includes('koPlanKopier'));
            console.log(h(DATA(), true, 7).includes('koPlanKopier'));
            console.log(h(DATA({poster: []}), true, 8).includes('koPlanKopier'));
        """)
        self.assertEqual(ut[:7], ['true', 'false', 'false', 'true', 'false', 'false', 'false'])

    def test_opprinnelig_bare_naar_det_er_endret_og_oppdrag_null_er_strek(self):
        ut = self._kjor(self.DATA + """
            console.log(koPlanEtterpaaHtml(DATA(), false, 7).includes('opprinnelig'));
            console.log(koPlanEtterpaaHtml(DATA({poster: [RAD({behov_naa: '5 Lag'})]}), false, 7).includes('opprinnelig: 4 Lag'));
            console.log(koPlanEtterpaaHtml(DATA({poster: [RAD({behov_opprinnelig: '', behov_naa: '2 Lag'})]}), false, 7)
              .includes('opprinnelig: ingen'));
            const html = koPlanEtterpaaHtml(DATA({poster: [RAD({oppdrag: null, startet: false})]}), false, 7);
            console.log(/<td class="text-end">–<\/td><td class="text-end">–<\/td>/.test(html));
            console.log(koPlanEtterpaaHtml(DATA(), false, 7).includes('ko-plan-under'));
            console.log(koPlanEtterpaaHtml(DATA({poster: []}), false, 7).includes('Ingen konserter'));
        """)
        self.assertEqual(ut[:6], ['false', 'true', 'true', 'true', 'true', 'true'])

    def test_etterpaa_escaper(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._kjor(self.DATA + f"""
            const ond = {json.dumps(ond)};
            const d = DATA({{vakter: [{{id: 8, navn: ond}}, {{id: 7, navn: ond}}],
              poster: [RAD({{navn: ond, sted: ond, tid: ond, type: ond, beredskap_navn: ond, behov_opprinnelig: ond,
                behov: [{{gruppe_navn: ond, trengs: 1, snitt: 1, under_min: 0}}]}})],
              endringer: [{{tidspunkt: '2026-09-25T20:00:00Z', navn: ond, hva: 'endret', av_navn: ond,
                detaljer: [{{felt: ond, fra: ond, til: ond}}]}}]}});
            console.log(koPlanEtterpaaHtml(d, true, 8));
        """)
        self.assertNotIn('<img', ut[0])
        self.assertIn('&lt;img', ut[0])
