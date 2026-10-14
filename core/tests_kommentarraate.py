"""Det kommentarene i koden peker på, skal finnes (14. okt. 2026, F4).

`core/tests_dokumentråte.py` holder Markdown-dokumentene; kommentarene og
docstringene i `.py`, `.js` og `.html` hadde ingen vakt. Gjeldsplanen 25. sep.
anslo «rundt 40 utdaterte kommentarer» — skannet 14. okt. var det ti ekte: tre
som pekte på `patients/stats_cache.py` etter at den flyttet til `core`,
`_should_run_now()` som er `klokke.forfalt()`, to JS-hjelpere som ikke finnes, en
migrasjon med feil nummer, `core.views` som er delt, og fire «hvert 15. sekund»
i KO, der loggen følger endringsnummeret (2,5 s).

**Samme gulv som dokumentråte-testen, ikke et tak.** Den fanger at et navn er
borte, ikke at en påstand er feil — «hvert 15. sekund» står fortsatt riktig om
bilen, og ingen skanner kan vite hvilken poller setningen gjelder.

Tre slags referanser:

| Hva | Sjekkes mot |
|---|---|
| Filstier, `app/fil.py` | Fila finnes (fra rota, `static/` eller en `templates/`-mappe) |
| Punkterte navn i backticks, `` `core.vakt.hent_aktiv_vakt` `` | Modellnavn (`core.Vakt`) gjennom app-registeret; ellers **importeres** modulen og attributtet slås opp |
| Egne hjelpere, `` `_privat()` `` og `` `camelCase()` `` | Definert et sted i kodebasen. Ikke `update()`, `lower()` — de er Djangos og språkets |

En slettet ting kan nevnes i setningen som sier at den er borte — det er ofte
det man trenger å vite. Står et av ordene i `FORKLARER` i nærheten, er treffet
en forklaring.
"""
from __future__ import annotations

import ast
import importlib
import io
import re
import subprocess
import tokenize
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROT = Path(settings.BASE_DIR)
MAPPER: list[Path] = []

FORKLARER = (
    'slettet', 'fjernet', 'erstatt', 'borte', 'finnes ikke', 'historisk', 'tidligere',
    'sto ', 'gammel', 'ikke lenger', 'flyttet', 'het ', 'fram til', 'kom hit',
    'delt ut av', 'forsvant', 'nå heter', 'som nå er',
)

#: **Linja selv og den neste**, ikke tre linjer på hver side som i
#: dokumentråte-testen. Med det vinduet slapp et dødt navn gjennom bare fordi
#: det sto ved siden av en ekte forklaring om noe annet (to mutanter, 14. okt.
#: 2026). Forklaringen følger navnet — «`ko.ressursbehov` og tre felter / som er
#: borte» — men står ikke foran det. Uten «var » og «før »: de står i nesten
#: hver norsk setning. Med linja alene fant regelen to råtne referanser til,
#: men meldte også fem setninger som bryter over to linjer.
#:
#: **Kjent luke, som i dokumentråte-testen:** et dødt navn på linja rett over en
#: ekte forklaring slipper fortsatt gjennom. Regelen er et gulv.
ETTER = 1

#: (fil, navn) — hvert med grunn. Ikke for å stilne et funn som er ekte.
UNNTATT = {
    ('patients/tests.py', 'js/x.js'),                         # oppdiktet sti i en test av stimønsteret
    ('templates/ko/index.html', 'ko.oppsett'),                # nøkkel i localStorage, ikke kode
    ('patients/tests_backup.py', 'patients/backup_service.py'),  # testen av at den er slettet
    ('vaktliste/tests_xss.py', '_posterPerGruppe'),           # «Til 26. sep. 2026 ble regelen prøvd i …»
    ('core/tests_dokumentråte.py', 'sti/til/fil.py'),         # eksempel i en docstring
    ('core/kartkobling.py', 'portal/signatur.py'),           # i kartets repo, ikke dette
    ('core/views_portal.py', 'patients/views.py'),            # «samme grep som … fikk i N13.3»
    ('patients/tests_backup.py', 'patients.BackupConfig'),    # testen av at den er slettet
}

#: Filnavn på formen `app.ext` ser ut som punkterte navn (`ko.js`, `ko.css`).
FILENDELSER = {'js', 'css', 'html', 'py', 'md', 'json'}

#: JavaScripts egne metoder med camelCase — ikke prosjektets hjelpere.
JS_INNEBYGDE = {'toISOString', 'getTime', 'toLocaleString', 'querySelector', 'addEventListener',
                'preventDefault', 'stopPropagation', 'setAttribute', 'getAttribute', 'appendChild',
                'checkValidity'}

STI = re.compile(r'(?<![\w/.-])([a-z_][a-z_0-9]*(?:/[a-z_0-9.-]+)+\.(?:py|js|html|md|css|json))\b')
KALL = re.compile(r'`(_[A-Za-z]\w*|[a-z]+[A-Z]\w*)\(\)`')


def _filer() -> list[Path]:
    ut = subprocess.run(['git', '-c', 'core.quotepath=off', 'ls-files', '*.py', '*.js', '*.html'],
                        capture_output=True, text=True, cwd=ROT).stdout.split('\n')
    return [ROT / p for p in ut if p and not any(
        d in Path(p).parts for d in ('migrations', 'vendor', 'staticfiles'))]


def _kommentarer(p: Path) -> list[tuple[int, str]]:
    t = p.read_text(encoding='utf-8')
    ut = []
    if p.suffix == '.py':
        try:
            for tok in tokenize.generate_tokens(io.StringIO(t).readline):
                if tok.type == tokenize.COMMENT:
                    ut.append((tok.start[0], tok.string))
            for n in ast.walk(ast.parse(t)):
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    d = ast.get_docstring(n, clean=False)
                    if d and n.body:
                        ut += [(n.body[0].lineno + i, l) for i, l in enumerate(d.split('\n'))]
        except (SyntaxError, tokenize.TokenError):
            pass
    else:
        mønster = (r'/\*.*?\*/|//[^\n]*' if p.suffix == '.js'
                   else r'\{#.*?#\}|\{% comment %\}.*?\{% endcomment %\}|<!--.*?-->')
        for m in re.finditer(mønster, t, re.S):
            start = t.count('\n', 0, m.start()) + 1
            ut += [(start + i, l) for i, l in enumerate(m.group(0).split('\n'))]
    return ut


def _definerte(filer) -> set[str]:
    navn = set()
    for p in filer:
        t = p.read_text(encoding='utf-8')
        if p.suffix == '.py':
            try:
                navn |= {n.name for n in ast.walk(ast.parse(t))
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
            except SyntaxError:
                pass
        elif p.suffix == '.js':
            navn |= set(re.findall(r'function\s+(\w+)', t))
            navn |= set(re.findall(r'(?:const|let|var)\s+(\w+)\s*=', t))
    return navn


def _punktert_finnes(navn: str, definert: set[str]) -> bool:
    """Et modellnavn (`core.Vakt`, `patients.vaktarkiv`), et modulattributt, eller
    en metode (`core.apps.ready`) — den siste godtas når navnet er definert et sted."""
    from django.apps import apps
    deler = navn.split('.')
    if len(deler) >= 2:
        try:
            modell = apps.get_model(deler[0], deler[1])
        except (LookupError, ValueError):
            modell = None
        # `core.vakt` er både en modul og modellen `Vakt`: et modellnavn godtas
        # bare alene, eller med et felt eller attributt etter (`Vaktliste.vakt`)
        # — ellers slapp `core.vakt.finnes_ikke` gjennom (mutant, 14. okt.).
        if modell is not None and len(deler) == 2:
            return True
        if modell is not None and deler[1][:1].isupper():
            return hasattr(modell, deler[2]) or deler[2] in {f.name for f in modell._meta.get_fields()}
    for i in range(len(deler), 0, -1):
        try:
            obj = importlib.import_module('.'.join(deler[:i]))
        except ImportError:
            continue
        for attr in deler[i:]:
            if not hasattr(obj, attr):
                return attr == deler[-1] and attr in definert
            obj = getattr(obj, attr)
        return True
    return False


class KommentareneTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.filer = _filer()
        apper = sorted({p.parent.name for p in ROT.glob('*/apps.py')} | {'myproject'})
        cls.punkt = re.compile(r'`((?:' + '|'.join(apper) + r')(?:\.[A-Za-z_]\w*)+)(?:\(\))?`')
        cls.definert = _definerte(cls.filer)
        global MAPPER
        MAPPER = [ROT, ROT / 'templates', ROT / 'static', *ROT.glob('*/templates')]
        cls.funn, cls.sett = [], {'sti': 0, 'punkt': 0, 'kall': 0}
        for p in cls.filer:
            linjer = p.read_text(encoding='utf-8').split('\n')
            rel = str(p.relative_to(ROT))
            for lnr, linje in _kommentarer(p):
                for sti in STI.findall(linje):
                    cls.sett['sti'] += 1
                    if (rel, sti) in UNNTATT or any((d / sti).exists() for d in MAPPER):
                        continue
                    cls._kanskje(linjer, lnr, f'{rel}:{lnr}: {sti}')
                for navn in cls.punkt.findall(linje):
                    cls.sett['punkt'] += 1
                    if navn.rsplit('.', 1)[-1] in FILENDELSER or (rel, navn) in UNNTATT:
                        continue
                    if not _punktert_finnes(navn, cls.definert):
                        cls._kanskje(linjer, lnr, f'{rel}:{lnr}: {navn}')
                for navn in KALL.findall(linje):
                    cls.sett['kall'] += 1
                    if navn not in cls.definert and navn not in JS_INNEBYGDE and (rel, navn) not in UNNTATT:
                        cls._kanskje(linjer, lnr, f'{rel}:{lnr}: {navn}()')

    @classmethod
    def _kanskje(cls, linjer, lnr, tekst):
        kontekst = ' '.join(linjer[lnr - 1:lnr + ETTER]).lower()
        if not any(ord_ in kontekst for ord_ in FORKLARER):
            cls.funn.append(tekst)

    def test_det_kommentarene_peker_paa_finnes(self):
        self.assertEqual(sorted(self.funn), [], (
            'Disse kommentarene peker på noe som ikke finnes:\n  ' + '\n  '.join(sorted(self.funn))
            + '\n\nRett referansen, eller si i setningen at det er borte.'))

    def test_skanneren_ser_noe(self):
        """Vern mot en regel som ser ingenting."""
        self.assertGreater(self.sett['sti'], 100, self.sett)
        self.assertGreater(self.sett['punkt'], 50, self.sett)
        self.assertGreater(self.sett['kall'], 50, self.sett)
