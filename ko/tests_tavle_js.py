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
    (PORTAL_UTILS_JS, ('escapeHtml',)),
    (KO_JS, ('koTavleKanSkrive', 'koTavleVindu', 'koTavleProsent', 'koTavleSynlig',
             'koTavleKanDras', 'koTavleMaal', 'koTavleVarighet', 'koTavleRader',
             'koTavleUtenPlass', 'koTavleStolpeHtml', 'koTavleRadHtml',
             'koTavleUtenPlassHtml', 'koTavleFilterHtml', 'koTavleKlikk')),
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
