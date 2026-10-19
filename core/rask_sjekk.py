"""Hvilke tester en endring trenger — `manage.py rask_sjekk` (19. okt. 2026).

Hele suiten er om lag fem minutter lokalt, og det er riktig før en push. Mens man
arbeider, er spørsmålet smalere: *har jeg ødelagt noe i det jeg rørte?* Svaret her
er appene filene ligger i, med testbasen beholdt (`--keepdb`, sparer om lag 16 s
per kjøring) og uten testene merket `@tag('treg')`.

**Valget utledes, det står ikke i en liste.** En JS- eller CSS-fil hører til appene
hvis maler laster den — `oppdrag-kort.js` lastes av både sentralbordet og `/ko/`,
og da kjøres begge. En håndskrevet tabell fra fil til app ville vært «et sted færre
enn der koden er» (`core/tests_testkommandoen.py`).

**Er det tvil, kjøres alt.** `core`, malene i `partials/`, `portal-utils.js`,
`requirements.txt` og alt annet uten et entydig hjem gir hele suiten. En rask
kjøring som hopper over det den burde ha tatt, er verre enn en treg.

**Hva den ikke dekker:** de tverrgående skannerne i `core` (escaping, ordboka,
avhengighetsretningen) leser filer i alle moduler, men kjøres bare når `core`
er med. De tas før push og i CI. Kommandoen sier det hver gang.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Taggen på testene som hoppes over: underprosesser, migreringer, alle rutene.
TREG = 'treg'

#: Mapper der en endring ikke har noe entydig hjem — `core` er rammeverket alle
#: modulene står på.
ALT_UTLOSES_AV = frozenset({'core'})


@dataclass
class Valg:
    """Etikettene til `manage.py test`, eller `None` for hele suiten."""
    etiketter: list[str] | None
    grunner: list[str] = field(default_factory=list)


def apper_med_tester(rot: Path) -> set[str]:
    """Toppnivåpakker med `tests*.py` — det Django-kjøreren finner tester i."""
    return {p.parent.name for p in rot.glob('*/tests*.py')
            if (p.parent / '__init__.py').exists()}


def dokumenttestene(rot: Path) -> list[str]:
    """Dokumenttestene, slik de står i CLAUDE.md.

    Lista utledes ikke her: `core/tests_testkommandoen.py` krever at linja i
    CLAUDE.md er nøyaktig testene som leser Markdown, så linja *er* fasiten.
    """
    tekst = (rot / 'CLAUDE.md').read_text(encoding='utf-8')
    treff = re.search(r'^python manage\.py test (core\.tests_\S+(?: \S+)*?) -v \d$', tekst, re.M)
    return treff.group(1).split() if treff else []


def _maler(rot: Path):
    for mappe in [rot / 'templates', *rot.glob('*/templates')]:
        yield from mappe.rglob('*.html')


def _app_for_mal(rot: Path, mal: Path, apper: set[str]) -> str | None:
    """`templates/ko/index.html` → `ko`. `None` for delte maler og for `core`."""
    deler = mal.relative_to(rot).parts
    if deler[0] == 'templates' and len(deler) > 2 and deler[1] in apper:
        app = deler[1]
    elif len(deler) > 2 and deler[1] == 'templates' and deler[0] in apper:
        app = deler[0]
    else:
        return None
    return None if app in ALT_UTLOSES_AV else app


def _apper_for_statisk(rot: Path, filnavn: str, apper: set[str]) -> set[str] | None:
    """Appene med en mal som laster fila — `None` hvis en delt mal gjør det, eller ingen."""
    ut: set[str] = set()
    for mal in _maler(rot):
        if filnavn in mal.read_text(encoding='utf-8', errors='replace'):
            app = _app_for_mal(rot, mal, apper)
            if app is None:
                return None
            ut.add(app)
    return ut or None


def velg(filer: list[str], rot: Path) -> Valg:
    """Testetikettene for de endrede filene (stier relativt til prosjektroten)."""
    apper = apper_med_tester(rot)
    valgt: set[str] = set()
    dok = False
    grunner: list[str] = []
    for fil in sorted(set(filer)):
        sti = Path(fil)
        deler = sti.parts
        if sti.suffix == '.md':
            dok = True
            continue
        if deler[0] in ALT_UTLOSES_AV:
            return Valg(None, [f'{fil}: rammeverket'])
        if deler[0] in apper:
            valgt.add(deler[0])
            continue
        if deler[0] == 'templates':
            app = _app_for_mal(rot, sti if sti.is_absolute() else rot / sti, apper)
            if app is None:
                return Valg(None, [f'{fil}: delt mal'])
            valgt.add(app)
            continue
        if deler[:2] in (('static', 'js'), ('static', 'css')):
            treff = _apper_for_statisk(rot, sti.name, apper)
            if treff is None:
                return Valg(None, [f'{fil}: lastes av en delt mal, eller av ingen'])
            grunner.append(f'{fil}: lastes av {", ".join(sorted(treff))}')
            valgt |= treff
            continue
        return Valg(None, [f'{fil}: ikke et entydig hjem'])
    etiketter = sorted(valgt)
    if dok:
        etiketter += [t for t in dokumenttestene(rot) if t.split('.')[0] not in valgt]
        grunner.append('Markdown endret: dokumenttestene')
    return Valg(etiketter, grunner)
