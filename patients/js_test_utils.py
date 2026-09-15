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
STATISTIKK_OPPDRAG_JS = JS_DIR / 'statistikk-oppdrag.js'
#: Sentralbordet er fire filer siden 14. sep. 2026 — se `VAKTLISTE_JS`.
OPPDRAG_SENTRAL_JS = (
    JS_DIR / 'oppdrag-sentral-kjerne.js',
    JS_DIR / 'oppdrag-sentral-oppdrag.js',
    JS_DIR / 'oppdrag-sentral-admin.js',
    JS_DIR / 'oppdrag-sentral-lasting.js',
)
OPPDRAG_ENHET_JS = JS_DIR / 'oppdrag-enhet.js'
#: **Vaktlistesiden er seks filer** — fem siden 14. sep. 2026 (gjeldspunkt 3.6),
#: og `vaktliste-oversikt.js` skilt ut fra tegningsfila 15. sep. 2026 da den
#: passerte 1 800 linjer.
#: Konstanten er derfor en tuppel, og `read_js()` skjøter dem sammen i
#: lasterekkefølge — så alt som leste `VAKTLISTE_JS` før, leser det samme nå.
#: Rekkefølgen er den samme som `<script>`-taggene i malen, og
#: `VaktlisteFileneDekkerAltTests` krever at de to holdes like.
VAKTLISTE_JS = (
    JS_DIR / 'vaktliste-kjerne.js',
    JS_DIR / 'vaktliste-tegning.js',
    JS_DIR / 'vaktliste-oversikt.js',
    JS_DIR / 'vaktliste-handlinger.js',
    JS_DIR / 'vaktliste-offline.js',
    JS_DIR / 'vaktliste-register.js',
)


def node_available():
    """True hvis node finnes på PATH. Brukes med unittest.skipUnless."""
    return shutil.which('node') is not None


def read_js(path):
    """Kildekoden til én fil — eller til flere, skjøtet i rekkefølge.

    Tuppelen finnes for sider som er delt i flere filer uten bundler
    (`VAKTLISTE_JS`). De deler ett globalt navnerom i nettleseren, så for
    alt som leser kilden er de én fil — og da skal de være det her også.
    """
    if isinstance(path, (tuple, list)):
        return '\n\n'.join(Path(p).read_text(encoding='utf-8') for p in path)
    return Path(path).read_text(encoding='utf-8')


def js_navn(sti):
    """Lesbart navn for en JS-kilde, enten den er én fil eller flere.

    Sidene uten bundler er delt i flere filer (14. sep. 2026), og en test som
    skriver `sti.name` i en `subTest`-etikett skal ikke måtte vite hvilken av
    delene den snakker om.
    """
    if isinstance(sti, (tuple, list)):
        return ' + '.join(Path(p).name for p in sti)
    return Path(sti).name


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
