"""Oversikten i «Avslutt vakt»-vinduet — `patients-admin.js`, kjørt i node.

Knappen skal være av så lenge noe sperrer, og mens oversikten ikke er hentet.
`avsluttKanTrykkes()` er regelen; `lastAvsluttOversikt()` er kallstedet, og
prøves for seg — en regel ingen kaller, beskytter ingenting.
"""
from __future__ import annotations

import json
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import ADMIN_JS, build_harness, node_available, run_node

HARNESS = [(ADMIN_JS, ('avsluttOversiktLinjer', 'avsluttKanTrykkes', 'lastAvsluttOversikt'))]

OVERSIKT = {
    'vakt': 'LS2026',
    'moduler': [{'slug': 'patients', 'etikett': 'pasienter', 'entall': 'pasient', 'antall': 212, 'sperre': ''},
                {'slug': 'oppdrag', 'etikett': 'oppdrag', 'antall': 0, 'sperre': ''}],
    'fryses': ['Pasienter', 'Oppdrag', 'Lag'],
    'sperrer': [],
}

#: Et minimalt DOM: to elementer, og `apiFetch` som svarer det testen ber om.
PREAMBLE = '''
const _el = () => ({ textContent: '', disabled: false, className: '', barn: [],
  replaceChildren() { this.barn = []; }, appendChild(b) { this.barn.push(b); } });
const _dom = { 'avslutt-oversikt': _el(), 'avslutt-vakt-knapp': _el() };
globalThis.document = { getElementById: id => _dom[id] || null, createElement: () => _el() };
let _svar = null;
globalThis.apiFetch = async () => _svar;
'''


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class AvsluttOversiktTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _json(self, uttrykk):
        ut = run_node(self.harness, f'console.log(JSON.stringify({uttrykk}));', preamble=PREAMBLE)
        return json.loads(ut.splitlines()[0])

    def test_linjene(self):
        linjer = self._json(f'avsluttOversiktLinjer({json.dumps(OVERSIKT)})')
        self.assertEqual([l['tekst'] for l in linjer], [
            '212 pasienter arkiveres og tømmes.',
            'Ingen oppdrag å arkivere.',
            'Statistikken fryses for: Pasienter, Oppdrag, Lag.',
        ])

    def test_entall(self):
        data = dict(OVERSIKT, moduler=[dict(OVERSIKT['moduler'][0], antall=1)])
        linjer = self._json(f'avsluttOversiktLinjer({json.dumps(data)})')
        self.assertEqual(linjer[0]['tekst'], '1 pasient arkiveres og tømmes.')

    def test_en_sperre_er_en_sperre(self):
        data = dict(OVERSIKT, sperrer=['1 oppdrag står fortsatt på tavla.'])
        linjer = self._json(f'avsluttOversiktLinjer({json.dumps(data)})')
        self.assertEqual(linjer[-1], {'tekst': '1 oppdrag står fortsatt på tavla.', 'sperre': True})
        self.assertIs(self._json(f'avsluttKanTrykkes({json.dumps(data)})'), False)

    def test_uten_sperrer_kan_det_trykkes(self):
        self.assertIs(self._json(f'avsluttKanTrykkes({json.dumps(OVERSIKT)})'), True)

    def test_uten_oversikt_kan_det_ikke_trykkes(self):
        self.assertIs(self._json('avsluttKanTrykkes(null)'), False)
        self.assertIs(self._json('avsluttKanTrykkes({})'), False)

    def _last(self, svar):
        ut = run_node(self.harness, f'''
          _svar = {svar};
          await lastAvsluttOversikt();
          console.log(JSON.stringify({{
            av: _dom['avslutt-vakt-knapp'].disabled,
            linjer: _dom['avslutt-oversikt'].barn.map(b => b.textContent),
            tekst: _dom['avslutt-oversikt'].textContent }}));
        ''', preamble=PREAMBLE)
        return json.loads(ut.splitlines()[0])

    def test_knappen_skrus_paa_naar_oversikten_er_ren(self):
        ut = self._last(f'{{ ok: true, json: async () => ({json.dumps(OVERSIKT)}) }}')
        self.assertFalse(ut['av'])
        self.assertEqual(len(ut['linjer']), 3)

    def test_knappen_blir_av_ved_sperre(self):
        data = dict(OVERSIKT, sperrer=['1 oppdrag står fortsatt på tavla.'])
        ut = self._last(f'{{ ok: true, json: async () => ({json.dumps(data)}) }}')
        self.assertTrue(ut['av'])

    def test_linjene_settes_som_tekst(self):
        """Sperreteksten og etikettene kommer fra serveren: tekst, aldri markup."""
        data = dict(OVERSIKT, sperrer=['<img src=x onerror=alert(1)>'])
        ut = self._last(f'{{ ok: true, json: async () => ({json.dumps(data)}) }}')
        self.assertEqual(ut['linjer'][-1], '<img src=x onerror=alert(1)>')

    def test_knappen_blir_av_naar_oversikten_feiler(self):
        ut = self._last('{ ok: false, json: async () => ({}) }')
        self.assertTrue(ut['av'])
        self.assertIn('kunne ikke hentes', ut['tekst'])
