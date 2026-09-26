"""Polling i skjulte faner (26. sep. 2026, G5).

Hvert `setInterval` i `static/js/` går gjennom `naarSynlig()`, eller står i
`UNNTAK` med grunnen. Listen er over **kallstedene**, lest ut av kilden — et
nytt sikkerhetsnett uten `naarSynlig` gjør testen rød den dagen det skrives.
"""
from __future__ import annotations

import re
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import JS_DIR, PORTAL_UTILS_JS, build_harness, node_available, run_node

#: (fil, det som kalles) → hvorfor det skal gå også når fana er skjult.
UNNTAK = {
    ('ko-hendelser.js', 'koMeldTilstede'): 'BroadcastChannel mellom to vinduer, ikke nett — skjerm 2 ligger ofte bak',
    ('notifications.js', 'pollCount'): 'sjekker synligheten selv, og henter når fana kommer fram',
    ('oppdrag-enhet.js', '() => lydTikk()'): 'bilens lydvarsel — skal pipe med skjermen av',
    ('oppdrag-enhet.js', 'lastBilinnstillinger'): 'tersklene lydvarselet bruker, hvert femte minutt',
    ('oppdrag-enhet.js', 'pollOgSynk'): 'bilens henting og kø — nye oppdrag skal gi lyd',
    ('patients-app.js', 'doAutoRefresh'): 'stoppes og startes av egen visibilitychange-lytter',
    ('patients-utils.js', 'updateClock'): 'klokka i toppen, ingen nett',
    ('portal-clock.js', 'updateClock'): 'klokka i toppen, ingen nett',
    ('portal-utils.js', 'sjekkEndringer'): 'sjekker `fanenErSkjult()` selv',
    ('vaktliste-offline.js', 'synkKo'): 'sender stemplinger som ligger i kø — skal gå uansett',
}

_KALL = re.compile(r'setInterval\(\s*(.+?),\s*[\w.*\s]+\)\s*;', re.S)


def kallsteder(katalog=JS_DIR):
    """(fil, første argument) for hvert `setInterval` utenom service workeren."""
    for fil in sorted(katalog.glob('*.js')):
        if fil.name.endswith('-sw.js'):
            continue
        for m in _KALL.finditer(fil.read_text(encoding='utf-8')):
            yield fil.name, m.group(1).strip()


class SikkerhetsnettetPollerIkkeSkjulteFanerTests(SimpleTestCase):

    def test_hvert_kallsted_er_gatet_eller_begrunnet(self):
        uten = [f'{fil}: setInterval({arg[:60]}…)' for fil, arg in kallsteder()
                if not arg.startswith('naarSynlig(') and (fil, arg) not in UNNTAK]
        self.assertEqual(uten, [], (
            'Pakk sikkerhetsnettet i naarSynlig(), eller før det opp i UNNTAK '
            'med grunnen — det som varsler eller sender skal gå i bakgrunnen.'))

    def test_unntakene_finnes_fortsatt(self):
        self.assertEqual(sorted(set(UNNTAK) - set(kallsteder())), [])

    def test_skanneren_ser_dem(self):
        steder = list(kallsteder())
        self.assertIn(('oppdrag-sentral-lasting.js', 'naarSynlig(lastAlt)'), steder)
        self.assertGreaterEqual(len(steder), 15)

    @unittest.skipUnless(node_available(), 'node mangler')
    def test_naar_synlig(self):
        harness = build_harness(((PORTAL_UTILS_JS, ('fanenErSkjult', 'naarSynlig')),))
        run_node(harness, """
let n = 0;
const f = naarSynlig((x) => { n += x; return 'kjort'; });
globalThis.document = { visibilityState: 'visible' };
assert(f(2) === 'kjort' && n === 2, 'synlig: kjører med argumentene');
document.visibilityState = 'hidden';
assert(f(5) === undefined && n === 2, 'skjult: kjører ikke');
""")
