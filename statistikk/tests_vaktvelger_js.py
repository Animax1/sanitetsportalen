"""Vaktvelgeren i nettleseren — `statistikk*.js`, kjørt i node (steg 3, 28. sep. 2026).

`statistikkUrl()` er regelen: hvor tallene for en fane hentes fra, for den
valgte vakta. Men en regel som ikke kalles, beskytter ingenting — derfor går
testene gjennom **hver fanes ekte laster** (`loadStats`, `loadOppdragStats`, …)
og krever at den henter fra riktig sted. Glemmer én fane velgeren, viser den
pågående vaktas tall under navnet til en tidligere — og ingen ville merket det.
"""
from __future__ import annotations

import json
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import (STATISTIKK_BEMANNING_JS, STATISTIKK_JS, STATISTIKK_KO_JS,
                                    STATISTIKK_OPPDRAG_JS, STATISTIKK_PARK_JS, build_harness,
                                    node_available, run_node)

HARNESS = [
    (STATISTIKK_JS, ('statistikkUrl', 'settIngenTall', 'hentStatistikk', 'loadStats',
                     'velgVakt', '_kallOppdrag', 'lastVaktvalg', 'vaktvalgTekst')),
    (STATISTIKK_OPPDRAG_JS, ('loadOppdragStats',)),
    (STATISTIKK_KO_JS, ('loadKoStats',)),
    (STATISTIKK_PARK_JS, ('loadParkStats',)),
    (STATISTIKK_BEMANNING_JS, ('sikreBemanning', 'loadBemanningStats', 'nullstillBemanning')),
]

VALGT = {'nokkel': 'frosset:3:x', 'navn': 'Sommerfest', 'tidspunkt': '2026-06-01T10:00:00+00:00',
         'kilder': {'patients': {'type': 'frosset', 'id': 11},
                    'oppdrag': {'type': 'arkiv', 'id': 4},
                    'ko': {'type': 'frosset', 'id': 12},
                    'park': {'type': 'frosset', 'id': 13},
                    'vaktliste': {'type': 'frosset', 'id': 14}}}

PREAMBLE = '''
let valgtVakt = null, fullStats = null, arkivStatsMode = false, activeStatTab = 'oversikt';
let oppdragStats = null, koStats = null, parkStats = null, bemanningStats = null, _bemanningLast = null;
let vaktvalg = [], arkivStatsMeta = null, visteKilde = null;
function aktivKilde() { return 'ko'; }
function visKilde(slug) { visteKilde = slug; }
const hentet = [], tegnet = [];
globalThis.apiFetch = async (url) => { hentet.push(url); return { ok: true, json: async () => ({ summary: {} }) }; };
function renderStatTab() { tegnet.push('patients'); }
function _oppdaterArkivBanner() {}
function renderOppdragStats() { tegnet.push('oppdrag'); }
function renderKoStats() { tegnet.push('ko'); }
function renderParkStats() { tegnet.push('park'); }
function renderBemanningStats() { tegnet.push('vaktliste'); }
const _paneler = {};
globalThis.document = {
  getElementById: id => (_paneler[id] = _paneler[id] || {
    klasser: new Set(), beskjed: null,
    classList: { toggle(k, paa) { paa ? this._p.klasser.add(k) : this._p.klasser.delete(k); } },
    querySelector() { return this.beskjed; },
    prepend(b) { this.beskjed = b; },
  }),
  createElement: () => ({ textContent: '', className: '' }),
};
for (const id of ['kilde-patients', 'kilde-oppdrag', 'kilde-ko', 'kilde-park', 'kilde-vaktliste']) {
  const p = document.getElementById(id); p.classList._p = p;
}
'''

LASTERE = 'await loadStats(); await loadOppdragStats(); await loadKoStats(); ' \
          'await loadParkStats(); await loadBemanningStats();'


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class StatistikkUrlTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _url(self, slug, valgt):
        ut = run_node(self.harness,
                      f'console.log(JSON.stringify(statistikkUrl({json.dumps(slug)}, {json.dumps(valgt)})));',
                      preamble=PREAMBLE)
        return json.loads(ut.splitlines()[0])

    def test_pagaende_er_de_levende_tallene(self):
        self.assertEqual(self._url('ko', None), '/statistikk/api/kilde/ko/full-stats/')

    def test_frosset_og_arkiv(self):
        self.assertEqual(self._url('ko', VALGT), '/statistikk/api/kilde/ko/frosset/12/')
        self.assertEqual(self._url('oppdrag', VALGT), '/statistikk/api/kilde/oppdrag/arkiv/4/full-stats/')

    def test_fane_uten_tall_og_ukjent_type_gir_null(self):
        self.assertIsNone(self._url('backlog', VALGT))
        self.assertIsNone(self._url('ko', {'kilder': {'ko': {'type': 'noe', 'id': 1}}}))


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class FaneneHenterFraValgtVaktTests(SimpleTestCase):
    """Gjennom de ekte lasterne — kallstedet er regelen."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _kjor(self, valgt, etter=''):
        ut = run_node(self.harness, f'''
          valgtVakt = {json.dumps(valgt)};
          {LASTERE}
          {etter}
          console.log(JSON.stringify({{ hentet, tegnet,
            uten: Object.entries(_paneler).filter(([, p]) => p.klasser.has('kilde-uten-tall'))
                  .map(([id]) => id).sort() }}));
        ''', preamble=PREAMBLE)
        return json.loads([l for l in ut.splitlines() if l.startswith('{')][0])

    def test_pagaende_vakt(self):
        ut = self._kjor(None)
        self.assertEqual(sorted(ut['hentet']), sorted(
            f'/statistikk/api/kilde/{s}/full-stats/' for s in ('patients', 'oppdrag', 'ko', 'park', 'vaktliste')))
        self.assertEqual(ut['uten'], [])

    def test_valgt_vakt_hentes_fra_hver_fanes_kilde(self):
        ut = self._kjor(VALGT)
        self.assertEqual(sorted(ut['hentet']), sorted([
            '/statistikk/api/kilde/patients/frosset/11/',
            '/statistikk/api/kilde/oppdrag/arkiv/4/full-stats/',
            '/statistikk/api/kilde/ko/frosset/12/',
            '/statistikk/api/kilde/park/frosset/13/',
            '/statistikk/api/kilde/vaktliste/frosset/14/',
        ]))
        self.assertEqual(sorted(ut['tegnet']), ['ko', 'oppdrag', 'park', 'patients', 'vaktliste'])

    def test_fane_uten_tall_henter_ingenting_og_skjules(self):
        """LS2026 har bare pasienttall: de andre fanene skal si det, ikke vise noe annet."""
        bare_pasienter = dict(VALGT, kilder={'patients': {'type': 'arkiv', 'id': 2}})
        ut = self._kjor(bare_pasienter)
        self.assertEqual(ut['hentet'], ['/statistikk/api/kilde/patients/arkiv/2/full-stats/'])
        self.assertEqual(ut['tegnet'], ['patients'])
        self.assertEqual(ut['uten'], ['kilde-ko', 'kilde-oppdrag', 'kilde-park', 'kilde-vaktliste'])

    def test_bemanningen_hentes_paa_nytt_etter_et_nytt_valg(self):
        """Svaret deles mellom fanene; uten nullstilling ville forrige vakts linjer stått."""
        ut = self._kjor(None, etter=f'''
          nullstillBemanning(); valgtVakt = {json.dumps(VALGT)}; await loadBemanningStats();''')
        self.assertIn('/statistikk/api/kilde/vaktliste/frosset/14/', ut['hentet'])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class VelgVaktTests(SimpleTestCase):
    """`velgVakt()` er inngangen nedtrekket kaller."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def test_valget_nullstiller_det_forrige_og_tegner_fanen(self):
        ut = run_node(self.harness, f"""
          vaktvalg = [{json.dumps(VALGT)}];
          globalThis.nullstillBemanning = nullstillBemanning;
          fullStats = {{ summary: {{}} }}; arkivStatsMode = true;
          bemanningStats = {{ gammel: true }}; _bemanningLast = Promise.resolve(bemanningStats);
          velgVakt({json.dumps(VALGT['nokkel'])});
          console.log(JSON.stringify({{ valgt: valgtVakt && valgtVakt.navn, fullStats, arkivStatsMode,
            bemanningStats, last: _bemanningLast, visteKilde }}));
        """, preamble=PREAMBLE)
        self.assertEqual(json.loads(ut.splitlines()[0]), {
            'valgt': 'Sommerfest', 'fullStats': None, 'arkivStatsMode': False,
            'bemanningStats': None, 'last': None, 'visteKilde': 'ko'})

    def test_tomt_valg_er_pagaende_vakt(self):
        ut = run_node(self.harness, f"""
          vaktvalg = [{json.dumps(VALGT)}]; valgtVakt = vaktvalg[0];
          velgVakt('');
          console.log(JSON.stringify(valgtVakt));
        """, preamble=PREAMBLE)
        self.assertEqual(ut.splitlines()[0], 'null')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class VakteneFraAdressenTests(SimpleTestCase):
    """`/statistikk/?vakt=<nøkkel>` — lenkene fra /portal-admin/vakt/."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _last(self, sok):
        ut = run_node(self.harness, f"""
          const _sel = {{ value: '', valg: [], appendChild(o) {{ this.valg.push(o); }},
                          addEventListener() {{}} }};
          const _hent = document.getElementById;
          document.getElementById = id => (id === 'stat-vakt' ? _sel : _hent(id));
          globalThis.window = {{ location: {{ search: {json.dumps(sok)} }} }};
          globalThis.apiFetch = async () => ({{ ok: true, json: async () => ({{ vakter: [{json.dumps(VALGT)}] }}) }});
          await lastVaktvalg();
          console.log(JSON.stringify({{ valgt: valgtVakt && valgtVakt.navn, verdi: _sel.value,
                                        antall: _sel.valg.length, vist: visteKilde }}));
        """, preamble=PREAMBLE)
        return json.loads([l for l in ut.splitlines() if l.startswith('{')][0])

    def test_nokkelen_i_adressen_velger_vakta(self):
        ut = self._last(f"?vakt={VALGT['nokkel']}")
        self.assertEqual(ut, {'valgt': 'Sommerfest', 'verdi': VALGT['nokkel'], 'antall': 1,
                              'vist': 'ko'})

    def test_ukjent_nokkel_lar_pagaende_sta(self):
        ut = self._last('?vakt=finnes:ikke')
        self.assertEqual((ut['valgt'], ut['verdi']), (None, ''))

    def test_uten_parameter_er_det_pagaende(self):
        self.assertIsNone(self._last('')['valgt'])
