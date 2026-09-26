"""Hjelperne bilskjermen har sin egen kopi av (26. sep. 2026, E5).

`oppdrag-enhet.js` laster ikke `oppdrag-kort.js` — bilskjermen skal ikke bære
tavlas tilstand for å låne fem enlinjere — så `oppdragsnr`, `hendelsesnr`,
`hastegradKlasse`, `_medAntall` og `_problemMedAntall` står i begge. Kopiene
er et valg; at de **glir**, er det ikke. Denne testen krever at hver funksjon
som står i begge filene er lik, bortsett fra kommentarene.

`lydTerskler` har samme navn i bilen og i sentralbordet, men leser tersklene
fra hvert sitt sted og kan derfor ikke være lik. Reserven den faller tilbake
på skal likevel være den samme — den manglet «Plassering» i sentralbordet
til 26. sep. 2026.
"""
from __future__ import annotations

import re
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import (
    JS_DIR, OPPDRAG_ENHET_JS, build_harness, extract_function, node_available,
    read_js, run_node,
)

KORT_JS = JS_DIR / 'oppdrag-kort.js'
SENTRAL_OPPDRAG_JS = JS_DIR / 'oppdrag-sentral-oppdrag.js'


def _toppfunksjoner(kilde):
    return set(re.findall(r'^(?:async )?function (\w+)\(', kilde, re.M))


def _uten_kommentarer(kropp):
    return '\n'.join(l for l in kropp.splitlines() if not l.strip().startswith('//'))


class KopieneErLikeTests(SimpleTestCase):

    def test_hver_delt_funksjon_er_lik(self):
        kort, enhet = read_js(KORT_JS), read_js(OPPDRAG_ENHET_JS)
        felles = _toppfunksjoner(kort) & _toppfunksjoner(enhet)
        self.assertIn('oppdragsnr', felles, 'utledningen finner ikke kopiene')
        for navn in sorted(felles):
            with self.subTest(navn):
                self.assertEqual(
                    _uten_kommentarer(extract_function(enhet, navn)),
                    _uten_kommentarer(extract_function(kort, navn)),
                    f'{navn}() i oppdrag-enhet.js har glidd fra oppdrag-kort.js')

    @unittest.skipUnless(node_available(), 'node mangler')
    def test_lydterskler_faller_tilbake_paa_samme_tabell(self):
        ut = []
        for fil, forspann in ((OPPDRAG_ENHET_JS, ('bilinnstillinger', 'lydTerskler')),
                              (SENTRAL_OPPDRAG_JS, ('lydTerskler',))):
            harness = build_harness(((fil, forspann),))
            ut.append(run_node(harness, 'console.log(JSON.stringify(lydTerskler()));'))
        self.assertEqual(ut[0], ut[1])
        self.assertIn('Plassering', ut[0])
