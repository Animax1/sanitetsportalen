"""Den dokumenterte testkommandoen må dekke alle testene (14. sep. 2026).

**Hvorfor dette er en test og ikke en kommentar.** Kommandoen i `CLAUDE.md`
utelot appen `myproject` — 32 tester på databasevalg, cache, `_env_bool`,
statiske filer og migrasjoner. Altså vaktene rundt «`DATABASE_URL` må være
PostgreSQL når `RAILWAY_ENVIRONMENT` er satt» og rundt den `_env_bool` som
hadde rate-limitingen av i prod til 13. sep. Den som fulgte dokumentasjonen
kjørte dem aldri, og ingenting sa fra.

Feilen ble oppdaget ved et tilfelle: testtallet stemte ikke mot forrige
kjøring. Det er ikke en mekanisme, det er flaks — og den flaksen kan man ikke
planlegge to ganger.

Det var samme dag som `SignalerFyrerIkkeUnderLoaddataTests` viste seg å lete i
en håndskrevet liste over tre apper, og dermed ikke ville sett `core/signals.py`
den dagen den ble skrevet. To ganger samme lærdom: **en liste over hvor man
skal lete er alltid et sted færre enn der koden er.**
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CLAUDE_MD = Path(settings.BASE_DIR) / 'CLAUDE.md'

#: Mapper som har `test*.py` uten at Django-kjøreren skal ta dem.
#: Unntaksliste med begrunnelse, ikke en tillatelse.
IKKE_TESTPAKKER: frozenset[str] = frozenset({
    '.venv', 'node_modules', 'staticfiles', 'docs', 'scripts',
})


def _pakker_med_tester() -> set[str]:
    """Toppnivåpakker som Django-kjøreren ville funnet tester i.

    Kravet er å være en importerbar pakke (`__init__.py`) med minst én
    `test*.py` — det er nøyaktig det kjøreren leter etter når den får et
    app-navn som etikett.
    """
    ut = set()
    for sti in Path(settings.BASE_DIR).iterdir():
        if not sti.is_dir() or sti.name in IKKE_TESTPAKKER or sti.name.startswith('.'):
            continue
        if not (sti / '__init__.py').exists():
            continue
        if any(sti.glob('test*.py')) or any(sti.glob('*/test*.py')):
            ut.add(sti.name)
    return ut


def _dokumentert_kommando() -> list[str]:
    """Etikettene i `python manage.py test …` i CLAUDE.md, hele suiten."""
    tekst = CLAUDE_MD.read_text(encoding='utf-8')
    treff = re.findall(r'^python manage\.py test ([a-z_ ]+?)(?: -v \d)?$',
                       tekst, re.M)
    # Den lengste linja er hele suiten; de andre er enkelt-test-eksempler.
    if not treff:
        return []
    return max(treff, key=lambda t: len(t.split())).split()


class TestkommandoenDekkerAltTests(SimpleTestCase):

    def test_kommandoen_finnes_i_claude_md(self):
        """Finner ikke regexen kommandoen, måler resten av fila ingenting —
        og går grønn mens den gjør det."""
        self.assertNotEqual(
            _dokumentert_kommando(), [],
            'fant ingen «python manage.py test …»-linje i CLAUDE.md — enten er '
            'kommandoen borte, eller så leter regexen her feil')

    def test_vi_finner_flere_pakker_med_tester(self):
        """Samme sperrehake fra den andre siden: finner oppdagelsen nesten
        ingenting, er den i stykker og testen under blir meningsløs."""
        self.assertGreaterEqual(len(_pakker_med_tester()), 7)

    def test_hver_pakke_med_tester_staar_i_kommandoen(self):
        dokumentert = set(_dokumentert_kommando())
        mangler = sorted(_pakker_med_tester() - dokumentert)
        self.assertEqual(
            mangler, [],
            'Disse pakkene har tester som den dokumenterte kommandoen i '
            'CLAUDE.md ikke kjører:\n  ' + '\n  '.join(mangler)
            + '\n\nLegg dem til i kommandoen under «Tester – hele suiten».')

    def test_kommandoen_navngir_ingenting_som_ikke_finnes(self):
        """Den andre retningen. En etikett som ikke finnes får kjøringen til å
        stoppe med «No installed app with label», altså hele suiten rød —
        men først hos den som prøver, ikke her."""
        ukjente = sorted(set(_dokumentert_kommando()) - _pakker_med_tester())
        self.assertEqual(
            ukjente, [],
            'CLAUDE.md navngir pakker som ikke har tester: ' + ', '.join(ukjente))


# ── Dokumenttestene (9. okt. 2026) ──────────────────────────────────────────

def _uten_docstrings(tre) -> set[int]:
    ids = set()
    for node in ast.walk(tre):
        if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)):
            ids.add(id(node.body[0].value))
    return ids


def _leser_markdown(sti: Path) -> bool:
    """Har fila en strengkonstant som ender på `.md` — utenom docstrings?

    Docstringene teller ikke: `patients.tests_choices` *nevner*
    personverndokumentet uten å lese det.
    """
    try:
        tre = ast.parse(sti.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError):
        return False
    docs = _uten_docstrings(tre)
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str)
               and n.value.endswith('.md') and id(n) not in docs
               for n in ast.walk(tre))


def _prosjektimporter(sti: Path) -> list[Path]:
    """Prosjektfilene en testfil importerer, som `core/changelog.py` —
    `tests_changelog` leser CHANGELOG gjennom den, ikke selv."""
    rot = Path(settings.BASE_DIR)
    ut = []
    for node in ast.walk(ast.parse(sti.read_text(encoding='utf-8'))):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for navn in node.names:
                for kandidat in (f"{node.module.replace('.', '/')}/{navn.name}.py",
                                 f"{node.module.replace('.', '/')}.py"):
                    if (rot / kandidat).is_file():
                        ut.append(rot / kandidat)
        elif isinstance(node, ast.Import):
            for navn in node.names:
                kandidat = rot / f"{navn.name.replace('.', '/')}.py"
                if kandidat.is_file():
                    ut.append(kandidat)
    return ut


def _dokumenttestene_utledet() -> set[str]:
    rot = Path(settings.BASE_DIR)
    ut = set()
    for pakke in _pakker_med_tester():
        for sti in sorted((rot / pakke).glob('**/tests*.py')):
            if '/migrations/' in sti.as_posix():
                continue
            if _leser_markdown(sti) or any(
                    _leser_markdown(i) and not i.name.startswith('tests')
                    for i in _prosjektimporter(sti)):
                ut.add('.'.join(sti.relative_to(rot).with_suffix('').parts))
    return ut


def _dokumenttestene_dokumentert() -> set[str]:
    tekst = CLAUDE_MD.read_text(encoding='utf-8')
    treff = re.search(r'^python manage\.py test (core\.tests_\S+(?: \S+)*?) -v \d$',
                      tekst, re.M)
    return set(treff.group(1).split()) if treff else set()


class DokumenttesteneTests(SimpleTestCase):
    """«Bare `.md`-filer endret: dokumenttestene» (André, 9. okt. 2026).

    Kommandoen i `CLAUDE.md` er en liste over hvor man skal lete, og den er
    alltid et sted færre enn der koden er — se docstringen øverst. Derfor
    utledes settet av testene som faktisk leser Markdown, direkte eller
    gjennom en prosjektmodul, og kommandoen må være nøyaktig det settet.
    """

    def test_utledningen_finner_noe(self):
        utledet = _dokumenttestene_utledet()
        self.assertIn('core.tests_claude_md', utledet)
        self.assertIn('core.tests_changelog', utledet, 'leser CHANGELOG gjennom core/changelog.py')
        self.assertNotIn('patients.tests_choices', utledet, 'nevner bare et dokument i en docstring')

    def test_kommandoen_er_noeyaktig_dokumenttestene(self):
        dokumentert = _dokumenttestene_dokumentert()
        self.assertNotEqual(dokumentert, set(), 'fant ikke dokumenttest-kommandoen i CLAUDE.md')
        utledet = _dokumenttestene_utledet()
        self.assertEqual(
            sorted(dokumentert), sorted(utledet),
            'Dokumenttest-kommandoen i CLAUDE.md stemmer ikke med testene som leser .md.\n'
            f'  Mangler: {sorted(utledet - dokumentert)}\n'
            f'  Leser ikke Markdown: {sorted(dokumentert - utledet)}')

    def test_en_docstring_som_nevner_et_dokument_teller_ikke(self):
        """Funnet ved mutasjon: `patients.tests_choices` sin docstring slutter
        ikke på `.md`, så unntaket for docstrings ble aldri prøvd."""
        import tempfile
        with tempfile.TemporaryDirectory() as mappe:
            bare_nevnt = Path(mappe) / 'a.py'
            bare_nevnt.write_text('"""Se CLAUDE.md"""\n\ndef f():\n    """og docs/X.md"""\n',
                                  encoding='utf-8')
            leser = Path(mappe) / 'b.py'
            leser.write_text('"""Leser."""\nFIL = "CLAUDE.md"\n', encoding='utf-8')
            self.assertFalse(_leser_markdown(bare_nevnt))
            self.assertTrue(_leser_markdown(leser))
