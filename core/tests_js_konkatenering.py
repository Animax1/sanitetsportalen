"""Markup bygget med `+`: hvert datafelt escapes (26. sep. 2026, D3).

**Hvorfor i `core` og for alle filene.** Skanneren sto i `ko/tests_js.py` og
dekket KO. Elleve filer bygger markup med `'<…' + x`, og `backlog.js` og
overnattingen i vaktlista sto uten. Byggerne **utledes** av kilden — en
funksjon som limer noe inn i en streng med en tagg i — så en ny fil er dekket
den dagen den kommer, uten at noen husker å føre den opp.

`oppdrag/tests_xss.py` og `vaktliste/tests_xss.py` leser *mal-strenger*
(`` `…${x}…` ``). Denne leser *konkatenering*. De to utfyller hverandre.

**Grensen for hva den ser, skrevet ned så den ikke må gjettes:** et
**datafelt** (`rad.navn`) limt rett inn. En *lokal variabel* bygget lenger
oppe (`+ merke`) fanges ikke — det er 131 av dem, og for dem er motmiddelet
oppførselsprøvene som kjører byggerne med fiendtlige data gjennom den ekte
inngangen (`ko/tests_js.py`, `backlog/tests_js.py`). KO hadde en liste med 32
slike «gjennomgåtte» navn til 26. sep. 2026; regexen krevde et punktum, så
ingen av dem kunne noen gang treffe. En unntaksliste som ikke påvirker noe,
ser ut som en dekning den ikke er.
"""
from __future__ import annotations

import re

from django.test import SimpleTestCase

from patients.js_test_utils import JS_DIR, extract_function

#: Gjennomgått, med grunn: (fil, funksjon, uttrykk). Skal ikke vokse uten
#: begrunnelse — foretrekk å escape i koden.
GJENNOMGATT = {
    ('oppdrag-kort.js', 'tegnEnhetsliste', 'g.type'):
        'del av en nøkkel (`type:…`) til gruppeErSkjult(), ikke markup',
    ('vaktliste-overnatting.js', 'apnePlasser', 'rom.navn'):
        'går til textContent, ikke innerHTML',
    ('vaktliste-overnatting.js', 'apnePlasser', 'der.navn'):
        'del av en tekst som escapes samlet i <option> rett under',
}

#: En streng med en tagg i, limt sammen med noe: da er funksjonen en bygger.
_BYGGER = re.compile(r"'[^']*<\w[^']*'\s*\+")
#: Et datafelt limt inn. `(?![\w(.\[])` holder kall og kjeder utenfor:
#: `rader.map(` og `s.grupper.map(` er ikke felter i markup. **`\w` må med i
#: klassen** — uten den backtracker `\w+` til et halvt navn for å tilfredsstille
#: lookaheaden, og funnet blir «rader.ma».
_DATAFELT = re.compile(r'\+\s*([a-z]\w*(?:\.\w+)+)(?![\w(.\[])')


def _uten_kommentarer(kropp: str) -> str:
    # En test som leser sin egen prosa måler at noen har skrevet om
    # begrunnelsen, ikke at koden gjør det den sier (CLAUDE.md).
    return '\n'.join(l for l in kropp.splitlines() if not l.lstrip().startswith('//'))


def byggere(katalog=JS_DIR):
    """(fil, funksjon, kropp) for hver funksjon som bygger markup med `+`."""
    for fil in sorted(katalog.glob('*.js')):
        kilde = fil.read_text(encoding='utf-8')
        for navn in re.findall(r'^(?:async )?function (\w+)\(', kilde, re.M):
            kropp = _uten_kommentarer(extract_function(kilde, navn))
            if _BYGGER.search(kropp):
                yield fil.name, navn, kropp


class KonkateneringEscapesTests(SimpleTestCase):

    def test_hvert_datafelt_er_escapet_eller_gjennomgaatt(self):
        uescapet = []
        for fil, navn, kropp in byggere():
            for uttrykk in _DATAFELT.findall(kropp):
                if (fil, navn, uttrykk) not in GJENNOMGATT:
                    uescapet.append(f'{fil} {navn}(): + {uttrykk}')
        self.assertEqual(uescapet, [], (
            'Datafelt limt rett inn i markup:\n  ' + '\n  '.join(uescapet)
            + '\n\nPakk verdien i escapeHtml()/escHtmlValue(). trustedHtml() er '
              'IKKE svaret: den blir «[object Object]» når den konkateneres '
              '(core/tests_js_regler.py).'))

    def test_unntakene_finnes_fortsatt(self):
        """Et unntak for en funksjon som er omdøpt eller rettet, er en død rad
        — og en død rad er nøyaktig det `KO_GJENNOMGATT` ble."""
        funnet = {(fil, navn, u) for fil, navn, kropp in byggere()
                  for u in _DATAFELT.findall(kropp)}
        self.assertEqual(sorted(set(GJENNOMGATT) - funnet), [])

    def test_skanneren_ser_det_den_skal(self):
        """Vern mot at testen blir tom: den må finne byggerne den er laget for,
        og regexen må fange et felt og slippe et kall."""
        filer = {fil for fil, _, _ in byggere()}
        for fil in ('backlog.js', 'ko.js', 'ko-hendelser.js', 'vaktliste-overnatting.js'):
            self.assertIn(fil, filer)
        self.assertEqual(_DATAFELT.findall("'<b>' + rad.navn + '</b>'"), ['rad.navn'])
        self.assertEqual(_DATAFELT.findall("'<b>' + rader.map(f).join('')"), [])
        self.assertEqual(_DATAFELT.findall("'<b>' + s.grupper.map(f).join('')"), [])
        self.assertEqual(_DATAFELT.findall("'<b>' + escapeHtml(rad.navn)"), [])

    def test_kommentarer_skannes_ikke(self):
        """En kommentar som viser den gamle, feil formen skal ikke gjøre
        funksjonen til en bygger — og ikke gi et funn."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as mappe:
            (Path(mappe) / 'prove.js').write_text(
                "function forklart(rad) {\n"
                "  // Var: '<b>' + rad.navn — nå textContent.\n"
                "  return rad.navn;\n"
                "}\n", encoding='utf-8')
            self.assertEqual(list(byggere(Path(mappe))), [])
