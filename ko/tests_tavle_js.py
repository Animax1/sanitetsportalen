"""Tavla i nettleseren (`static/js/ko-tavle.js`, 22. sep. 2026).

Reglene er egne funksjoner fordi de *avgjør* hva tavla viser og hva den lar
deg gjøre — hvem som kan dras, hvor et slipp havner, hvilken rad en stolpe
står i. De kjøres her i node, med data i den formen `/ko/api/tavle/` gir.

Byggerne skannes for escaping i `ko/tests_js.py` (`KO_LOGG_BYGGERE`);
oppførselsprøven med fiendtlige navn står her.
"""
import json
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import (KO_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, run_node)

TAVLE_JS = KO_JS[2]

HARNESS = (
    (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml',)),
    (KO_JS, ('koTavleKanSkrive', 'koTavleVindu', 'koTavleProsent', 'koTavleSynlig',
             'koTavleKanDras', 'koTavleMaal', 'koTavleVarighet', 'koTavleRader',
             'koTavleUtenPlass', 'koTavleStolpeHtml', 'koTavleRadHtml',
             'koTavleUtenPlassHtml', 'koTavleFilterHtml', 'koTavleKlikk',
             # Steg 2.
             'koTavleTo', 'koTavleHHMM', 'koTavleTidNaer', 'koTavlePauseStatus',
             'koTavlePlanlagtHtml', 'koTavleValgtHtml', 'koTavleDognnokkel', 'koTavleDognene',
             'koTavleBesok', 'koTavleIkkeVaert', 'koTavleDognnavn', 'koTavleSistHtml',
             'koTavleBesokHtml', 'koTavleIkkeVaertHtml', 'koTavleSkjemaData',
             'koTavleSkjemaHtml', 'koTavleSkjemaKropp', 'koTavleOppsettHtml',
             # Planlagt slutt (23. sep. 2026).
             'koTavleSlutt', 'koTavleSluttHtml',
             # Programmet (steg 2).
             'koTavleProgram', 'koTavleKonsertHtml')),
)

#: Klokka i testene: 22. sep. 2026 kl. 20:00 UTC.
NAA = '2026-09-22T20:00:00Z'

DATA = {
    'naa': NAA, 'timer': 12,
    'rader': [{'id': 1, 'navn': 'Parkscene'}, {'id': 2, 'navn': 'Village'}],
    'grupper': [{'id': 10, 'navn': 'Lag'}, {'id': 20, 'navn': 'Ambulanse'}],
    'ressurser': [
        {'id': 101, 'navn': 'Lag 1', 'gruppe_id': 10, 'bil': False, 'opptatt': None},
        {'id': 102, 'navn': 'Lag 2', 'gruppe_id': 10, 'bil': False, 'opptatt': None},
        {'id': 103, 'navn': 'Lag 3', 'gruppe_id': 10, 'bil': False,
         'opptatt': {'merke': 'På H14', 'tekst': 'På H14 · Village', 'lokasjon_id': 2,
                     'fra': '2026-09-22T19:30:00Z'}},
        {'id': 201, 'navn': 'Amb 1', 'gruppe_id': 20, 'bil': True, 'opptatt': None},
    ],
    'plasseringer': [
        # Lag 1 har stått på Parkscene siden 16:00 — over tre timer.
        {'id': 1, 'ressurs_id': 101, 'ressurs_navn': 'Lag 1', 'lokasjon_id': 1,
         'lokasjon_navn': 'Parkscene', 'pause': False, 'hendelse_nummer': None,
         'fra': '2026-09-22T16:00:00Z', 'til': None},
        # Lag 2 var på Parkscene 17–18, så pause 18–18:30, og står nå ingen steder.
        {'id': 2, 'ressurs_id': 102, 'ressurs_navn': 'Lag 2', 'lokasjon_id': 1,
         'lokasjon_navn': 'Parkscene', 'pause': False, 'hendelse_nummer': None,
         'fra': '2026-09-22T17:00:00Z', 'til': '2026-09-22T18:00:00Z'},
        {'id': 3, 'ressurs_id': 102, 'ressurs_navn': 'Lag 2', 'lokasjon_id': None,
         'lokasjon_navn': '', 'pause': True, 'hendelse_nummer': None,
         'fra': '2026-09-22T18:00:00Z', 'til': '2026-09-22T18:30:00Z'},
        # Historikk fra en lukket hendelse, og en plassering fra i går.
        {'id': 4, 'ressurs_id': 201, 'ressurs_navn': 'Amb 1', 'lokasjon_id': 2,
         'lokasjon_navn': 'Village', 'pause': False, 'hendelse_nummer': 9,
         'fra': '2026-09-22T12:00:00Z', 'til': '2026-09-22T13:00:00Z'},
        {'id': 5, 'ressurs_id': 201, 'ressurs_navn': 'Amb 1', 'lokasjon_id': 2,
         'lokasjon_navn': 'Village', 'pause': False, 'hendelse_nummer': None,
         'fra': '2026-09-21T10:00:00Z', 'til': '2026-09-21T11:00:00Z'},
    ],
}


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TavlereglerTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(HARNESS)
        self.pre = (_konst(TAVLE_JS, 'KO_TAVLE_LENGE_MIN')
                    + _konst(TAVLE_JS, 'KO_TAVLE_PAUSE_FORVARSEL_MIN')
                    + 'let koTavleValgt = null;\n'
                    + 'let koKanSkriveSvar = true;\n'
                    + 'function koKanSkrive() { return koKanSkriveSvar; }\n'
                    + f'const DATA = {json.dumps(DATA)};\n'
                    + f"const NAA = Date.parse('{NAA}');\n")

    def _kjor(self, kode):
        return run_node(self.harness, kode, preamble=self.pre).splitlines()

    def _json(self, uttrykk):
        return json.loads(self._kjor(f'console.log(JSON.stringify({uttrykk}));')[0])

    # ── Tidslinja ───────────────────────────────────────────────────────────

    def test_naa_staar_ved_to_tredjedeler(self):
        v = self._json('koTavleVindu(NAA, 12)')
        naa = self._json('NAA')
        self.assertEqual(naa - v['fra'], 8 * 3600000)
        self.assertEqual(v['til'] - naa, 4 * 3600000)
        v24 = self._json('koTavleVindu(NAA, 24)')
        self.assertEqual(v24['til'] - v24['fra'], 24 * 3600000)

    def test_timer_som_ikke_er_et_tall_gir_standarden(self):
        v = self._json("koTavleVindu(NAA, 'tull')")
        self.assertEqual(v['til'] - v['fra'], 12 * 3600000)

    def test_prosent_klemmes_til_vinduet(self):
        ut = self._json('[koTavleProsent(0, {fra: 100, til: 200}), koTavleProsent(150, {fra: 100, til: 200}),'
                        ' koTavleProsent(999, {fra: 100, til: 200})]')
        self.assertEqual(ut, [0, 50, 100])

    # ── Hvem kan dras, og hvor ──────────────────────────────────────────────

    def test_bare_en_ledig_kan_dras_og_bare_av_den_som_skriver(self):
        ut = self._json("[koTavleKanDras(DATA.ressurser[0], true), koTavleKanDras(DATA.ressurser[2], true),"
                        " koTavleKanDras(DATA.ressurser[0], false), koTavleKanDras(null, true)]")
        self.assertEqual(ut, [True, False, False, False])

    def test_maalet_leses_av_naermeste_rad(self):
        ut = self._json("""(() => {
            const el = (v) => ({ closest: () => (v === null ? null : { getAttribute: () => v }) });
            return [koTavleMaal(el('uten')), koTavleMaal(el('pause')), koTavleMaal(el('7')),
                    koTavleMaal(el('tull')), koTavleMaal(el('0')), koTavleMaal(el(null)), koTavleMaal(null)];
        })()""")
        self.assertEqual(ut, [{'uten': True}, {'pause': True}, {'lokasjon_id': 7},
                              None, None, None, None])

    def test_filteret_er_ressursgruppen(self):
        ut = self._json("[koTavleSynlig(DATA.ressurser[0], 'alle'), koTavleSynlig(DATA.ressurser[0], '10'),"
                        " koTavleSynlig(DATA.ressurser[0], '20'), koTavleSynlig(DATA.ressurser[3], 20)]")
        self.assertEqual(ut, [True, True, False, True])

    # ── Radene ──────────────────────────────────────────────────────────────

    def _rader(self, filter_='alle'):
        return self._json(f"koTavleRader(DATA, koTavleVindu(NAA, 12), '{filter_}')")

    def test_pause_staar_oeverst_og_er_ikke_en_lokasjon(self):
        rader = self._rader()
        self.assertEqual([r['navn'] for r in rader], ['Pause', 'Parkscene', 'Village'])
        self.assertEqual(rader[0]['id'], 'pause')
        self.assertEqual([s['navn'] for s in rader[0]['stolper']], ['Lag 2'])

    def test_hver_stolpe_i_sin_rad(self):
        park = self._rader()[1]
        self.assertEqual(sorted(s['navn'] for s in park['stolper']), ['Lag 1', 'Lag 2'])
        self.assertEqual(park['naa'], 1, 'bare den åpne teller som «nå»')
        aapen = next(s for s in park['stolper'] if s['aapen'])
        self.assertEqual(aapen['navn'], 'Lag 1')
        self.assertTrue(aapen['lenge'], 'fire timer på samme sted gir ⏱')
        self.assertTrue(aapen['dras'])
        self.assertAlmostEqual(aapen['hoyre'], 100 / 3, msg='den åpne slutter ved nå')

    def test_en_lang_pause_faar_ikke_klokka(self):
        """⏱ er «glemt på en rolig post». En lang pause er noe annet."""
        ut = self._json("""(() => {
            const d = JSON.parse(JSON.stringify(DATA));
            d.plasseringer.push({id: 9, ressurs_id: 102, ressurs_navn: 'Lag 2', lokasjon_id: null,
              pause: true, hendelse_nummer: null, fra: '2026-09-22T16:30:00Z', til: null});
            return koTavleRader(d, koTavleVindu(NAA, 12), 'alle')[0].stolper.find((s) => s.aapen);
        })()""")
        self.assertFalse(ut['lenge'])
        self.assertEqual(ut['varighet'], '3 t 30')

    def test_hendelsen_staar_stiplet_i_raden_sin_og_gaar_ikke_aa_dra(self):
        """André: «hendelser og oppdrag tar prioritet men skal vises på
        tavlen» — laget står der hendelsen er, men tavla satte det ikke."""
        village = self._rader()[2]
        opptatt = [s for s in village['stolper'] if s['opptatt']]
        self.assertEqual(len(opptatt), 1)
        self.assertEqual(opptatt[0]['navn'], 'Lag 3')
        self.assertEqual(opptatt[0]['merke'], 'På H14')
        self.assertFalse(opptatt[0]['dras'])
        self.assertEqual(village['naa'], 1)

    def test_lukket_hendelse_star_med_nummeret_og_gaarsdagen_er_utenfor(self):
        village = self._rader()[2]
        historikk = [s for s in village['stolper'] if s['hendelse']]
        self.assertEqual([s['merke'] for s in historikk], ['H9'])
        self.assertEqual(len(village['stolper']), 2, 'gårsdagens plassering er utenfor vinduet')

    def test_overlapp_gir_ny_bane(self):
        ut = self._json("""(() => {
            const d = JSON.parse(JSON.stringify(DATA));
            d.plasseringer.push({id: 9, ressurs_id: 102, ressurs_navn: 'Lag 2', lokasjon_id: 1,
              pause: false, hendelse_nummer: null, fra: '2026-09-22T17:30:00Z', til: '2026-09-22T17:45:00Z'});
            return koTavleRader(d, koTavleVindu(NAA, 12), 'alle')[1];
        })()""")
        self.assertEqual(ut['baner'], 3, 'Lag 1 fra 16, Lag 2 fra 17 og 17:30 — tre samtidig')

    def test_filteret_tar_stolpene_med_seg(self):
        rader = self._rader('20')
        self.assertEqual([len(r['stolper']) for r in rader], [0, 0, 1])

    def test_uten_skrivetilgang_kan_ingenting_dras(self):
        ut = self._json("(() => { koKanSkriveSvar = false;"
                        " return koTavleRader(DATA, koTavleVindu(NAA, 12), 'alle')[1].stolper.map((s) => s.dras); })()")
        self.assertEqual(ut, [False, False])

    # ── «Uten plass» ────────────────────────────────────────────────────────

    def test_uten_plass_er_de_ledige_uten_aapen_plassering(self):
        u = self._json("koTavleUtenPlass(DATA, 'alle', NAA)")
        self.assertEqual([r['navn'] for r in u['ledige']], ['Lag 2', 'Amb 1'])
        self.assertEqual([r['navn'] for r in u['opptatt']], ['Lag 3'])
        lag2 = u['ledige'][0]
        self.assertEqual(lag2['pause'], '1 t 30', 'tid siden pausen sluttet 18:30')
        self.assertEqual(u['ledige'][1]['pause'], '', 'aldri hatt pause')

    # ── Escaping gjennom den ekte inngangen ─────────────────────────────────

    def test_navnene_escapes_i_alle_byggerne(self):
        ut = self._kjor("""
            const d = JSON.parse(JSON.stringify(DATA));
            const ondt = '<img src=x onerror=alert(1)>';
            d.ressurser.forEach((r) => { r.navn = ondt; });
            d.ressurser[2].opptatt.tekst = ondt; d.ressurser[2].opptatt.merke = ondt;
            d.rader[0].navn = ondt; d.grupper[0].navn = ondt;
            const html = koTavleRader(d, koTavleVindu(NAA, 12), 'alle').map(koTavleRadHtml).join('')
              + koTavleUtenPlassHtml(koTavleUtenPlass(d, 'alle', NAA)) + koTavleFilterHtml(d, 'alle');
            assert(!html.includes('<img'), 'rå markup slapp gjennom: ' + html);
            assert(html.includes('&lt;img'), 'navnet forsvant i stedet for å escapes');
        """)
        self.assertIn('OK', ut)

    def test_dra_merket_er_borte_uten_skrivetilgang(self):
        """En knapp som fører til en vegg er verre enn ingen knapp."""
        ut = self._kjor("""
            koKanSkriveSvar = false;
            const html = koTavleRader(DATA, koTavleVindu(NAA, 12), 'alle').map(koTavleRadHtml).join('')
              + koTavleUtenPlassHtml(koTavleUtenPlass(DATA, 'alle', NAA));
            console.log(html.includes('data-dras'));
            koKanSkriveSvar = true;
            console.log(koTavleUtenPlassHtml(koTavleUtenPlass(DATA, 'alle', NAA)).includes('data-dras="1"'));
        """)
        self.assertEqual(ut[:2], ['false', 'true'])

    # ── Klikk laget, så raden ───────────────────────────────────────────────

    def test_klikk_laget_saa_raden_flytter(self):
        ut = self._kjor("""
            const flyttet = [];
            globalThis.koTavleFlytt = (id, mal) => flyttet.push([id, mal]);
            globalThis.koTegnTavle = () => {};
            const kort = { getAttribute: () => '102' };
            const paaKort = { closest: (v) => (v.startsWith('[data-tavle-ressurs]') ? kort : null) };
            const paaRad = { closest: (v) => (v === '[data-tavle-mal]' ? { getAttribute: () => '2' } : null) };
            koTavleKlikk(paaRad);
            console.log(JSON.stringify(flyttet), 'ingenting valgt, ingenting flyttes');
            koTavleKlikk(paaKort);
            console.log(koTavleValgt);
            koTavleKlikk(paaKort);
            console.log(koTavleValgt, 'klikk igjen velger bort');
            koTavleKlikk(paaKort);
            koTavleKlikk(paaRad);
            console.log(JSON.stringify(flyttet));
        """)
        self.assertEqual(ut[0], '[] ingenting valgt, ingenting flyttes')
        self.assertEqual(ut[1], '102')
        self.assertEqual(ut[2], 'null klikk igjen velger bort')
        self.assertEqual(json.loads(ut[3]), [[102, {'lokasjon_id': 2}]])


#: Data for steg 2, bygget i **lokal tid** i node — så prøvene sier det samme
#: i en container på UTC og på en PC i Norge. `L(d, t, m)` er 23.–24. sep. 2026.
STEG2 = """
const L = (d, t, m = 0) => new Date(2026, 8, d, t, m).getTime();
const I = (ms) => new Date(ms).toISOString();
const NAA2 = L(24, 2);
const D2 = {
  naa: I(NAA2), timer: 12, dognstart: '06:00', vakt_start: I(L(23, 14)), fulgte: [1],
  rader: [{id: 1, navn: 'Parkscene'}, {id: 2, navn: 'Village'}],
  grupper: [{id: 10, navn: 'Lag'}],
  ressurser: [
    {id: 101, navn: 'Lag 1', gruppe_id: 10, bil: false, opptatt: null},
    {id: 102, navn: 'Lag 2', gruppe_id: 10, bil: false, opptatt: null},
    {id: 103, navn: 'Lag 3', gruppe_id: 10, bil: false,
     opptatt: {merke: 'På H4', tekst: 'På H4', lokasjon_id: 1, fra: I(L(24, 1, 30)), hendelse_id: 4}},
  ],
  plasseringer: [
    // Lag 1: Parkscene 15–16 og 23–00:30 (fredag etter døgnstart), så Village.
    {id: 1, ressurs_id: 101, ressurs_navn: 'Lag 1', lokasjon_id: 1, lokasjon_navn: 'Parkscene', pause: false,
     hendelse_nummer: null, fra: I(L(23, 15)), til: I(L(23, 16))},
    {id: 2, ressurs_id: 101, ressurs_navn: 'Lag 1', lokasjon_id: 1, lokasjon_navn: 'Parkscene', pause: false,
     hendelse_nummer: null, fra: I(L(23, 23)), til: I(L(24, 0, 30))},
    {id: 3, ressurs_id: 101, ressurs_navn: 'Lag 1', lokasjon_id: 2, lokasjon_navn: 'Village', pause: false,
     hendelse_nummer: 7, fra: I(L(24, 0, 30)), til: I(L(24, 1))},
    {id: 4, ressurs_id: 101, ressurs_navn: 'Lag 1', lokasjon_id: 2, lokasjon_navn: 'Village', pause: false,
     hendelse_nummer: null, fra: I(L(24, 1)), til: null},
  ],
  pauser: [
    {id: 50, ressurs_id: 102, ressurs_navn: 'Lag 2', fra: I(L(24, 2, 5)), til: I(L(24, 2, 35)), startet: false},
    {id: 51, ressurs_id: 101, ressurs_navn: 'Lag 1', fra: I(L(24, 4)), til: I(L(24, 4, 30)), startet: false},
    {id: 52, ressurs_id: 101, ressurs_navn: 'Lag 1', fra: I(L(23, 20)), til: I(L(23, 20, 30)), startet: true},
  ],
};
"""


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class Steg2Tests(TavlereglerTests):
    """Steg 2 i nettleseren: tidene i skjemaet, pausene, «Besøk», «ikke vært»
    og byggerne med fiendtlige navn. Arver harness og forspill."""

    def _kjor(self, kode):
        return run_node(self.harness, STEG2 + kode, preamble=self.pre).splitlines()

    def test_klokkeslett_blir_naermeste_tidspunkt(self):
        """«20:00» betyr den nærmeste 20:00 — også over midnatt."""
        ut = self._json("""[
            koTavleTidNaer(L(24, 0, 30), '23:50') === L(23, 23, 50),
            koTavleTidNaer(L(23, 23, 30), '00:20') === L(24, 0, 20),
            koTavleTidNaer(L(23, 20), '19:00') === L(23, 19),
            koTavleTidNaer(L(23, 20), '24:00'), koTavleTidNaer(L(23, 20), 'x'),
        ]""")
        self.assertEqual(ut, [True, True, True, None, None])

    def test_pausens_status(self):
        ut = self._json("""D2.pauser.map((q) => koTavlePauseStatus(q, NAA2)).concat(
            [koTavlePauseStatus(D2.pauser[0], L(24, 1, 54)), koTavlePauseStatus(D2.pauser[0], L(24, 2, 35))])""")
        self.assertEqual(ut, ['naa', 'kommer', 'startet', 'kommer', 'ikke_tatt'],
                         'ti minutter før er «nå»; ved slutt uten start er den ikke tatt')

    def test_planlagte_staar_i_pause_raden_og_den_startede_ikke(self):
        ut = self._json("koTavleRader(D2, koTavleVindu(NAA2, 12), 'alle')[0].stolper"
                        ".map((s) => [s.pause_id, s.pause_status, s.dras])")
        self.assertEqual(ut, [[50, 'naa', False], [51, 'kommer', False]])

    def test_kortet_viser_neste_pause_som_ikke_er_tatt(self):
        """En startet pause som begynte tidligere skal ikke skygge for den
        neste."""
        ut = self._json("""(() => {
            const d = JSON.parse(JSON.stringify(D2));
            d.pauser.push({id: 60, ressurs_id: 102, ressurs_navn: 'Lag 2', fra: I(L(23, 22)), til: I(L(23, 22, 30)), startet: true},
                          {id: 61, ressurs_id: 102, ressurs_navn: 'Lag 2', fra: I(L(23, 23)), til: I(L(23, 23, 30)), startet: false});
            return koTavleUtenPlass(d, 'alle', NAA2).ledige.map((r) => r.planlagt && r.planlagt.id);
        })()""")
        self.assertEqual(ut, [50])

    def test_pause_naa_paa_kortet_og_i_raden_bare_for_den_som_skriver(self):
        ut = self._kjor("""
            const u = koTavleUtenPlass(D2, 'alle', NAA2);
            console.log(JSON.stringify(u.ledige.map((r) => [r.navn, r.planlagt])));
            const rad = koTavleRader(D2, koTavleVindu(NAA2, 12), 'alle')[0];
            console.log(koTavleRadHtml(rad).includes('data-action="koTavleStartPause" data-arg="50"'),
                        koTavleUtenPlassHtml(u).includes('data-action="koTavleStartPause"'));
            koKanSkriveSvar = false;
            console.log(koTavleRadHtml(rad).includes('koTavleStartPause'),
                        koTavleUtenPlassHtml(u).includes('koTavleStartPause'),
                        koTavleRadHtml(rad).includes('koTavlePlanlegg'));
        """)
        self.assertEqual(json.loads(ut[0]), [['Lag 2', {'id': 50, 'naa': True, 'kl': '02:05'}]])
        self.assertEqual(ut[1], 'true true')
        self.assertEqual(ut[2], 'false false false')

    def test_doegnet_begynner_ved_doegnstarten(self):
        ut = self._json("""[koTavleDognnokkel(L(24, 1), '06:00'), koTavleDognnokkel(L(24, 6), '06:00'),
                            koTavleDognnokkel(L(24, 1), '00:00'), JSON.stringify(koTavleDognene(D2, NAA2))]""")
        self.assertEqual(ut[:3], ['2026-09-23', '2026-09-24', '2026-09-24'])
        self.assertEqual(json.loads(ut[3]), ['2026-09-23'], 'kl. 02 er fortsatt onsdagens døgn')

    def test_besok_teller_per_doegn_hele_vakta_og_hendelsen_naa(self):
        b = self._json("koTavleBesok(D2, 1, 'alle', NAA2)")
        rader = {r['navn']: r for r in b['rader']}
        self.assertEqual(rader['Lag 1']['per'], {'2026-09-23': 2})
        self.assertEqual(rader['Lag 1']['antall'], 2)
        self.assertEqual(rader['Lag 1']['tid_totalt'], (60 + 90) * 60000)
        self.assertEqual(rader['Lag 3']['antall'], 1, 'laget på H4 ved Parkscene er der nå')
        self.assertEqual(rader['Lag 3']['sist'], {'naa': True, 'til': self._json('NAA2'), 'merke': 'På H4'})
        self.assertIsNone(rader['Lag 2']['sist'])

    def test_fulgt_sted_gir_nuller_oeverst(self):
        ut = self._json("""(() => {
            const d = JSON.parse(JSON.stringify(D2));
            d.ressurser[2].opptatt = null;
            const lag2 = (fra, til) => ({id: fra, ressurs_id: 102, ressurs_navn: 'Lag 2', lokasjon_id: 1,
              pause: false, hendelse_nummer: null, fra: I(fra), til: I(til)});
            d.plasseringer.push(lag2(L(23, 17), L(23, 18)), lag2(L(23, 19), L(23, 20)));
            return [koTavleBesok(D2, 1, 'alle', NAA2).rader.map((r) => r.navn),
                    koTavleBesok(d, 1, 'alle', NAA2).rader.map((r) => r.navn),
                    koTavleBesok(D2, 2, 'alle', NAA2).rader.map((r) => r.navn)];
        })()""")
        self.assertEqual(ut[0], ['Lag 2', 'Lag 3', 'Lag 1'], 'null først, så færrest besøk')
        self.assertEqual(ut[1], ['Lag 3', 'Lag 2', 'Lag 1'],
                         'likt antall: den som var der for lengst siden først')
        self.assertEqual(ut[2], ['Lag 1', 'Lag 2', 'Lag 3'], 'ikke fulgt: ressursenes egen rekkefølge')

    def test_ikke_vaert_gjelder_bare_fulgte_steder(self):
        ut = self._json("koTavleIkkeVaert(D2, 'alle', NAA2)")
        self.assertEqual(ut, [{'navn': 'Parkscene', 'ressurser': ['Lag 2']}])

    def test_skjemaet_laaser_til_der_det_ikke_kan_endres(self):
        ut = self._json("""[koTavleSkjemaData({type: 'rett', id: 4}, D2, NAA2),
                            koTavleSkjemaData({type: 'rett', id: 2}, D2, NAA2),
                            koTavleSkjemaData({type: 'rett', id: 1}, D2, NAA2),
                            koTavleSkjemaData({type: 'rett', id: 999}, D2, NAA2)]""")
        self.assertTrue(ut[0]['tilLaast'], 'den åpne slutter nå')
        self.assertTrue(ut[1]['tilLaast'], 'H7 tok over 00:30')
        self.assertIn('H7', ut[1]['hint'])
        self.assertFalse(ut[2]['tilLaast'])
        self.assertIsNone(ut[3])

    def test_skjemaet_sender_tidspunkter_naer_det_de_retter(self):
        ut = self._json("""[
            koTavleSkjemaKropp({type: 'rett', id: 2}, D2, {fra: '22:50', til: '00:30'}, NAA2),
            koTavleSkjemaKropp({type: 'rett', id: 4}, D2, {fra: '00:55', til: ''}, NAA2),
            koTavleSkjemaKropp({type: 'pause', id: null}, D2, {fra: '23:50', til: '00:20', ressurs: '102'}, L(23, 23)),
            koTavleSkjemaKropp({type: 'rett', id: 2}, D2, {fra: 'x', til: '00:30'}, NAA2),
            koTavleSkjemaKropp({type: 'pause', id: null}, D2, {fra: '23:50', til: '00:20', ressurs: ''}, L(23, 23)),
            koTavleSkjemaKropp({type: 'pause', id: 5}, D2, {fra: '23:50', til: '00:20', ressurs: ''}, L(23, 23)),
        ].map((k) => k && Object.fromEntries(Object.entries(k).map(([n, v]) => [n, typeof v === 'string' ? Date.parse(v) : v])))""")
        L = lambda d, t, m=0: self._json(f'L({d}, {t}, {m})')
        self.assertEqual(ut[0], {'fra': L(23, 22, 50), 'til': L(24, 0, 30)})
        self.assertEqual(ut[1], {'fra': L(24, 0, 55), 'planlagt_til': None},
                         'den åpne sender ingen «til» — og tomt «planlagt slutt» er ingen plan')
        self.assertEqual(ut[2], {'fra': L(23, 23, 50), 'til': L(24, 0, 20), 'ressurs_id': 102},
                         '«23:50–00:20» går over midnatt')
        self.assertIsNone(ut[3])
        # «Velg…» står først i lag-nedtrekket (23. sep. 2026): en ny pause
        # uten lag sendes ikke. En pause som finnes, har laget sitt alt.
        self.assertIsNone(ut[4], 'ny pause uten lag')
        self.assertEqual(ut[5], {'fra': L(23, 23, 50), 'til': L(24, 0, 20)})

    def test_steg2_byggerne_escaper(self):
        ut = self._kjor("""
            const ondt = '<img src=x onerror=alert(1)>';
            const d = JSON.parse(JSON.stringify(D2));
            d.ressurser.forEach((r) => { r.navn = ondt; });
            d.rader.forEach((l) => { l.navn = ondt; });
            d.plasseringer.forEach((p) => { p.ressurs_navn = ondt; p.lokasjon_navn = ondt; });
            d.ressurser[2].opptatt.merke = ondt;
            d.dognstart = ondt;
            const html = koTavleBesokHtml(d, koTavleBesok(d, 1, 'alle', NAA2), {maal: 'antall'}, 1)
              + koTavleBesokHtml(d, koTavleBesok(d, 1, 'alle', NAA2), {maal: 'tid'}, 1)
              + koTavleIkkeVaertHtml(koTavleIkkeVaert(d, 'alle', NAA2))
              + koTavleSkjemaHtml(koTavleSkjemaData({type: 'rett', id: 2}, d, NAA2))
              + koTavleSkjemaHtml(koTavleSkjemaData({type: 'pause', id: null}, d, NAA2))
              + koTavleValgtHtml(d.ressurser[0], d.plasseringer[3])
              + koTavleOppsettHtml([{id: 1, navn: ondt, paa_tavla: true, fulgt: false}]);
            assert(!html.includes('<img'), 'rå markup slapp gjennom: ' + html);
            assert(html.includes('&lt;img'), 'navnene forsvant i stedet for å escapes');
        """)
        self.assertIn('OK', ut)

    def test_klikk_uten_valgt_lag_aapner_skjemaet_og_knapper_klikker_ikke(self):
        ut = self._kjor("""
            const aapnet = [];
            globalThis.koTavleApneSkjema = (type, id) => aapnet.push([type, id]);
            globalThis.koTavleFlytt = () => aapnet.push('flytt');
            globalThis.koTegnTavle = () => {};
            const med = (sel, attr, verdi) => ({ closest: (v) => (v === sel ? { getAttribute: (a) => (a === attr ? verdi : null) } : null) });
            koTavleKlikk(med('[data-tavle-pause]', 'data-tavle-pause', '50'));
            koTavleKlikk(med('[data-tavle-plassering]', 'data-tavle-plassering', '2'));
            koTavleKlikk({ closest: (v) => (v === '[data-action]' ? {} : { getAttribute: () => '50' }) });
            console.log(JSON.stringify(aapnet), koTavleValgt);
            // Er et lag valgt, er et klikk i en rad en flytting — også når det
            // treffer en gammel stolpe der. Skjemaet åpnes ikke i tillegg.
            koTavleValgt = 101;
            koTavleKlikk({ closest: (v) => (v === '[data-tavle-mal]' ? { getAttribute: () => '2' }
              : (v === '[data-tavle-plassering]' ? { getAttribute: () => '3' } : null)) });
            console.log(JSON.stringify(aapnet));
        """)
        self.assertEqual(ut[0], '[["pause",50],["rett",2]] null', 'knappen velger ingenting')
        self.assertEqual(json.loads(ut[1]), [['pause', 50], ['rett', 2], 'flytt'])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class PlanlagtSluttJsTests(TavlereglerTests):
    """Planlagt slutt i nettleseren (23. sep. 2026): stiplet fram til
    slutten, rød kant og «over» når tida er ute. Arver harness og data —
    Lag 1 står åpen på Parkscene fra 16:00, og klokka er 20:00 UTC."""

    def _med_slutt(self, slutt_iso):
        return (f"const D = JSON.parse(JSON.stringify(DATA)); D.plasseringer[0].planlagt_til = '{slutt_iso}';\n")

    def test_regelen_sier_over_eller_igjen_og_ingenting_uten_plan(self):
        ut = self._json("""[
            koTavleSlutt({til: null, planlagt_til: '2026-09-22T21:30:00Z'}, NAA),
            koTavleSlutt({til: null, planlagt_til: '2026-09-22T19:45:00Z'}, NAA),
            koTavleSlutt({til: null, planlagt_til: null}, NAA),
            koTavleSlutt({til: '2026-09-22T19:00:00Z', planlagt_til: '2026-09-22T18:00:00Z'}, NAA),
            koTavleSlutt({til: null, planlagt_til: '2026-09-22T20:00:00Z'}, NAA),
        ]""")
        self.assertEqual(ut[0]['over'], False)
        self.assertEqual(ut[0]['min'], 90)
        self.assertEqual((ut[1]['over'], ut[1]['min']), (True, 15))
        self.assertIsNone(ut[2])
        self.assertIsNone(ut[3], 'en lukket plassering har ingen plan å vise')
        self.assertEqual(ut[4]['over'], False, 'akkurat på tida er ikke over')

    def test_stiplet_fram_til_slutten_og_banen_holdes(self):
        ut = self._kjor(self._med_slutt('2026-09-22T22:00:00Z') + """
            const rad = koTavleRader(D, koTavleVindu(NAA, 12), 'alle').find((r) => r.id === 1);
            const s = rad.stolper.find((x) => x.navn === 'Lag 1');
            console.log(JSON.stringify(s.slutt));
            console.log(koTavleStolpeHtml(s));
            console.log(rad.over);
        """)
        slutt = json.loads(ut[0])
        self.assertFalse(slutt['over'])
        self.assertIn('ko-tavle-slutt-plan', ut[1])
        self.assertIn('til ', ut[1])
        self.assertIn('data-tavle-plassering="1"', ut[1], 'klikk på den stiplede åpner skjemaet')
        self.assertNotIn('ko-tavle-over', ut[1])
        self.assertEqual(ut[2], '0')

    def test_over_tida_gir_rod_kant_minutter_og_tall_paa_raden(self):
        ut = self._kjor(self._med_slutt('2026-09-22T19:40:00Z') + """
            const rad = koTavleRader(D, koTavleVindu(NAA, 12), 'alle').find((r) => r.id === 1);
            const s = rad.stolper.find((x) => x.navn === 'Lag 1');
            console.log(koTavleStolpeHtml(s));
            console.log(koTavleRadHtml(rad));
        """)
        # Klassen alene — `ko-tavle-over-tekst` inneholder den samme strengen.
        self.assertRegex(ut[0], r'class="[^"]*\bko-tavle-over(?=[ "])')
        self.assertIn('20 min over', ut[0])
        self.assertIn('ko-tavle-slutt-merke', ut[0])
        self.assertNotIn('ko-tavle-slutt-plan', ut[0], 'ingen stiplet framtid når tida er ute')
        self.assertIn('1 over', ut[1])

    def test_uten_skrivetilgang_aapner_den_stiplede_ingenting(self):
        ut = self._kjor(self._med_slutt('2026-09-22T22:00:00Z') + """
            koKanSkriveSvar = false;
            const rad = koTavleRader(D, koTavleVindu(NAA, 12), 'alle').find((r) => r.id === 1);
            console.log(koTavleStolpeHtml(rad.stolper.find((x) => x.navn === 'Lag 1')));
        """)
        self.assertIn('ko-tavle-slutt-plan', ut[0])
        self.assertNotIn('data-tavle-plassering', ut[0])

    def test_neste_stolpe_legges_ikke_oppaa_den_stiplede(self):
        """Det eneste som står fram i tid i samme rad, er en planlagt pause i
        Pause-raden. Lag 1 står i pause til 22:00; Lag 2 har pause planlagt
        21:00 — da må de ha hver sin bane, ellers ligger den ene oppå den andre."""
        ut = self._kjor("""
            const D = JSON.parse(JSON.stringify(DATA));
            D.plasseringer[0].pause = true; D.plasseringer[0].lokasjon_id = null;
            D.plasseringer[0].fra = '2026-09-22T19:30:00Z';
            D.plasseringer[0].planlagt_til = '2026-09-22T22:00:00Z';
            D.plasseringer = D.plasseringer.filter((p) => p.id !== 3);
            D.pauser = [{id: 50, ressurs_id: 102, ressurs_navn: 'Lag 2', fra: '2026-09-22T21:00:00Z',
                         til: '2026-09-22T21:30:00Z', startet: false}];
            const rad = koTavleRader(D, koTavleVindu(NAA, 12), 'alle').find((r) => r.pause);
            console.log(JSON.stringify(rad.stolper.map((s) => [s.navn, s.bane])));
        """)
        baner = dict(json.loads(ut[0]))
        self.assertNotEqual(baner['Lag 1'], baner['Lag 2'])

    def test_skjemaet_viser_og_sender_slutten_naer_naa(self):
        ut = self._kjor(STEG2 + """
            const d = JSON.parse(JSON.stringify(D2));
            d.plasseringer[3].planlagt_til = I(L(24, 3, 30));
            const s = koTavleSkjemaData({type: 'rett', id: 4}, d, NAA2);
            console.log(JSON.stringify([s.harSlutt, s.slutt]));
            console.log(koTavleSkjemaHtml(s).includes('id="ko-tavle-skjema-slutt"'));
            const lukket = koTavleSkjemaData({type: 'rett', id: 1}, d, NAA2);
            console.log(JSON.stringify([lukket.harSlutt, koTavleSkjemaHtml(lukket).includes('ko-tavle-skjema-slutt')]));
            const k = koTavleSkjemaKropp({type: 'rett', id: 4}, d, {fra: '01:00', slutt: '02:30'}, NAA2);
            console.log(JSON.stringify([Date.parse(k.planlagt_til) === L(24, 2, 30), k.til === undefined]));
            console.log(JSON.stringify(koTavleSkjemaKropp({type: 'rett', id: 4}, d, {fra: '01:00', slutt: 'tull'}, NAA2)));
            const kl = koTavleSkjemaKropp({type: 'rett', id: 1}, d, {fra: '15:00', til: '16:00', slutt: '02:30'}, NAA2);
            console.log('planlagt_til' in kl);
        """)
        self.assertEqual(json.loads(ut[0]), [True, '03:30'])
        self.assertEqual(ut[1], 'true')
        self.assertEqual(json.loads(ut[2]), [False, False], 'bare den åpne har en planlagt slutt')
        self.assertEqual(json.loads(ut[3]), [True, True])
        self.assertEqual(ut[4], 'null', 'et felt som ikke er et klokkeslett sendes ikke')
        self.assertEqual(ut[5], 'false', 'en lukket plassering sender ingen plan')

    def test_slutten_escapes(self):
        ut = self._kjor(self._med_slutt('2026-09-22T22:00:00Z') + """
            const s = {slutt: {over: false, min: 5, kl: '<img src=x>', prosent: 80}, bane: 0, hoyre: 33.3,
                       plassering_id: '"><img src=y>'};
            console.log(koTavleSluttHtml(s, true));
            s.slutt.over = true;
            console.log(koTavleSluttHtml(s, true));
        """)
        self.assertNotIn('<img', ut[0] + ut[1])
