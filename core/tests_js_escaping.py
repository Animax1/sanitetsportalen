"""Alle HTML-escaperne i `static/js/` gir samme svar (26. sep. 2026, E5).

Det sto fem varianter. To av dem — `_escHtml` og `esc` i `notifications.js` —
escapet ikke `'`, og var dermed trygge i tekst og i `"`-attributter men ikke i
`'`-attributter. Navnene sa ingenting om det.

Escaperne **utledes**: hver funksjon, også en nøstet, hvis kropp gjør `<` om
til `&lt;`. En ny kopi er dermed med den dagen den skrives, og må gi samme
svar som de andre — eller stå her med en grunn. Den ene forskjellen som er
lov, er hva de gjør med *falsy*: `escapeHtml(0)` er `''` med vilje, og
`escHtmlValue(0)` er `'0'` med vilje (se `portal-utils.js`).
"""
from __future__ import annotations

import json
import re
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import JS_DIR, node_available, run_node

FIENDTLIG = '<img src=x onerror=\'a("b")\'>&amp;'
FASIT = '&lt;img src=x onerror=&#39;a(&quot;b&quot;)&#39;&gt;&amp;amp;'

_SIGNATUR = re.compile(r'^(\s*)function (\w+)\s*\(', re.M)


def escapere(katalog=JS_DIR):
    """(fil, navn, kilde) for hver funksjon som escaper `<`."""
    for fil in sorted(katalog.glob('*.js')):
        linjer = fil.read_text(encoding='utf-8').splitlines()
        for i, linje in enumerate(linjer):
            m = _SIGNATUR.match(linje)
            if not m:
                continue
            slutt = m.group(1) + '}'
            for j in range(i + 1, len(linjer)):
                if linjer[j] == slutt:
                    kilde = '\n'.join(l[len(m.group(1)):] for l in linjer[i:j + 1])
                    if '&lt;' in kilde and 'replace' in kilde:
                        yield fil.name, m.group(2), kilde
                    break


class EscaperneErLikeTests(SimpleTestCase):

    def test_utledningen_finner_dem(self):
        funnet = {(fil, navn) for fil, navn, _ in escapere()}
        for forventet in (('portal-utils.js', 'escapeHtml'),
                          ('portal-utils.js', 'escHtmlValue'),
                          ('notifications.js', 'esc')):
            self.assertIn(forventet, funnet)

    @unittest.skipUnless(node_available(), 'node mangler')
    def test_alle_gir_fasiten(self):
        for fil, navn, kilde in escapere():
            with self.subTest(f'{fil} {navn}()'):
                run_node(kilde, f'''
const ut = {navn}({json.dumps(FIENDTLIG)});
assert(ut === {json.dumps(FASIT)}, "{fil} {navn}(): " + ut);
''')
