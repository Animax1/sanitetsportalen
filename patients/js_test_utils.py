"""Hjelpere for tester som leser og kjører frontend-JavaScript.

Modulen heter bevisst *ikke* ``tests_*`` — den inneholder ingen tester selv, og
skal ikke plukkes opp av Djangos testoppdagelse.

Bakgrunn: frontend har ingen bundler og ingen JS-testrunner. To testmoduler
trenger likevel å verifisere JS-oppførsel (`tests_xss_stats.py` for escaping,
`tests.py` for dobbeltklikk-vernet). Alternativet til dette var å lese filene
som tekst og grep-e etter kodelinjer, som gir en påminnelse snarere enn en
test — se N9 i CHANGELOG (13. aug. 2026).

Funksjonene her klipper ut enkeltfunksjoner fra JS-modulene og kjører dem i
node med et minimalt stubbet miljø. Det unngår å måtte laste hele modulen,
som har toppnivå-avhengigheter til Chart, bootstrap og DOM-en.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

JS_DIR = Path(settings.BASE_DIR) / 'static' / 'js'

PORTAL_UTILS_JS = JS_DIR / 'portal-utils.js'
UTILS_JS = JS_DIR / 'patients-utils.js'
TABLE_JS = JS_DIR / 'patients-table.js'
FORMS_JS = JS_DIR / 'patients-forms.js'
APP_JS = JS_DIR / 'patients-app.js'
ADMIN_JS = JS_DIR / 'patients-admin.js'
STATISTIKK_JS = JS_DIR / 'statistikk.js'
OPPDRAG_SENTRAL_JS = JS_DIR / 'oppdrag-sentral.js'


def node_available():
    """True hvis node finnes på PATH. Brukes med unittest.skipUnless."""
    return shutil.which('node') is not None


def read_js(path):
    return Path(path).read_text(encoding='utf-8')


def extract_function(source, name):
    """Klipp ut kildekoden til én toppnivåfunksjon.

    JS-modulene bruker toppnivåfunksjoner som lukkes med ``}`` i kolonne 0, så
    vi leser fra signaturen til første slike linje. Enklere og mer forutsigbart
    enn å telle klammer gjennom template-literaler.
    """
    lines = source.splitlines()
    signature = re.compile(r'^(?:async )?function ' + re.escape(name) + r'\s*\(')
    start = None
    for i, line in enumerate(lines):
        if signature.match(line):
            start = i
            break
    if start is None:
        raise AssertionError(f'Fant ikke funksjonen {name}() i JS-kilden')
    for j in range(start + 1, len(lines)):
        if lines[j] == '}':
            return '\n'.join(lines[start:j + 1])
    raise AssertionError(f'Fant ikke slutten på {name}()')


def build_harness(spec):
    """Sett sammen kildekoden til funksjonene i ``spec``.

    ``spec`` er en sekvens av ``(sti, (funksjonsnavn, ...))``.
    """
    deler = []
    for path, names in spec:
        src = read_js(path)
        deler.extend(extract_function(src, n) for n in names)
    return '\n\n'.join(deler)


ASSERT_HELPER = '''
function assert(cond, msg) {
  if (!cond) { console.error("ASSERT: " + msg); process.exit(1); }
}
'''


def run_node(harness, snippet, preamble='', timeout=30):
    """Kjør ``snippet`` med ``harness`` i scope. Returnerer stdout.

    ``preamble`` legges inn før funksjonene — brukes til å stubbe globaler
    som ``document`` for kode som rører DOM-en.

    Kaster AssertionError med node sin utskrift hvis skriptet feiler, slik at
    en feilet assert i JS blir en lesbar testfeil i Python.
    """
    script = '\n'.join([preamble, harness, ASSERT_HELPER, snippet, 'console.log("OK");'])
    with tempfile.TemporaryDirectory() as tmp:
        js_file = Path(tmp) / 'harness.mjs'
        js_file.write_text(script, encoding='utf-8')
        res = subprocess.run(
            ['node', str(js_file)], capture_output=True, text=True, timeout=timeout,
        )
    if res.returncode != 0:
        raise AssertionError(f'node feilet:\n{res.stdout}\n{res.stderr}')
    return res.stdout
