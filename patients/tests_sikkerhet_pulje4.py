"""Sikkerhetsgjennomgangen 28. sep. 2026, pulje 4: navnene i pasienttabellen.

Tabulator setter en streng fra en egen formatter inn med `innerHTML`;
standardformatteren escaper, en egen gjør det ikke. Førstehjelper- og
helsepersonellnavnene gikk rett inn. Prøvd gjennom `COLS` — kolonnedefinisjonen
tabellen faktisk bygges fra — så en kolonne som mister formatteren blir rød,
ikke bare en hjelpefunksjon som fortsatt er riktig.
"""
from __future__ import annotations

import json
import re
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import JS_DIR, extract_function, node_available, read_js, run_node

ANGREP = '<img src=x onerror=alert(1)>'


def _harness():
    tabell = read_js(JS_DIR / 'patients-table.js')
    cols = re.search(r'^const COLS = \[.*?^\];', tabell, re.S | re.M).group(0)
    deler = [extract_function(read_js(JS_DIR / 'portal-utils.js'), 'escapeHtml')]
    deler += [extract_function(tabell, n) for n in ('trFmt', 'personFmt')]
    stubber = 'function totalFmt() { return ""; }\n'
    return stubber + '\n\n'.join(deler) + '\n\n' + cols


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class NavneneEscapesTests(SimpleTestCase):

    def _celle(self, felt, verdi):
        ut = run_node(_harness(), f'''
          const kol = COLS.find(c => c.field === {json.dumps(felt)});
          const html = kol.formatter({{getValue: () => ({json.dumps(verdi)})}});
          console.log(JSON.stringify(html));''')
        return json.loads(ut.splitlines()[0])

    def test_forstehjelperen(self):
        html = self._celle('forstehjelper', {'id': 1, 'name': ANGREP})
        self.assertNotIn('<img', html)
        self.assertIn('&lt;img', html)

    def test_helsepersonellet(self):
        html = self._celle('helsepersonell_ref', {'id': 1, 'name': ANGREP})
        self.assertNotIn('<img', html)

    def test_triage_utenfor_lista(self):
        html = self._celle('grovsortering', ANGREP)
        self.assertNotIn('<img', html)

    def test_vanlige_navn_vises(self):
        """Motprøven."""
        self.assertEqual(self._celle('forstehjelper', {'id': 1, 'name': 'Kari Nordmann'}),
                         'Kari Nordmann')
        self.assertEqual(self._celle('helsepersonell_ref', None), '')
