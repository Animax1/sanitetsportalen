"""Oversikten over oppdateringsintervallene i `docs/RUNBOOK_VAKT.md` §3d
(André, 24. sep. 2026: «så vi har oversikt»).

En håndholdt tabell forfaller i stillhet — neste løkke noen legger til, står
ikke der, og tallet noen endrer, står feil. To ting håndheves:

1. **Hver fil med en løkke er nevnt i §3d.** Filene finnes ved å lete
   (`setInterval` i `static/js/` og malene), ikke ved å stå i en liste.
2. **Tallet for hver navngitt konstant stemmer.** Står `KO_LOGG_MS` i en rad,
   skal raden si det antallet sekunder konstanten har i koden.

Grensen: et intervall skrevet som et tall rett i kallet (`setInterval(lastAlt,
30000)`) har ikke noe navn å slå opp på, og tallet i raden kontrolleres ikke.
Filen er fortsatt kontrollert.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROT = Path(settings.BASE_DIR)
RUNBOOK = ROT / 'docs' / 'RUNBOOK_VAKT.md'


def seksjon_3d() -> str:
    tekst = RUNBOOK.read_text(encoding='utf-8')
    start = tekst.index('## 3d.')
    slutt = tekst.index('\n## ', start + 1)
    return tekst[start:slutt]


def _uten_kommentarer(kilde: str) -> str:
    kilde = re.sub(r'/\*.*?\*/', '', kilde, flags=re.S)
    kilde = re.sub(r'<!--.*?-->', '', kilde, flags=re.S)
    kilde = re.sub(r'\{#.*?#\}', '', kilde, flags=re.S)
    return re.sub(r'(^|[^:])//.*$', r'\1', kilde, flags=re.M)


def filer_med_loekke() -> list[Path]:
    kandidater = list((ROT / 'static' / 'js').glob('*.js'))
    for mappe in ('templates', 'core/templates'):
        kandidater += list((ROT / mappe).rglob('*.html'))
    return sorted(f for f in kandidater
                  if 'setInterval(' in _uten_kommentarer(f.read_text(encoding='utf-8')))


def ms_konstant(navn: str) -> int | None:
    """`const NAVN = 30000;`, `30_000` eller `5 * 60 * 1000` i en av JS-filene."""
    for f in (ROT / 'static' / 'js').glob('*.js'):
        m = re.search(r'^const ' + re.escape(navn) + r'\s*=\s*([\d_\s*]+);', f.read_text(encoding='utf-8'), re.M)
        if m:
            verdi = 1
            for ledd in m.group(1).replace('_', '').split('*'):
                verdi *= int(ledd.strip())
            return verdi
    return None


def _sekundtekst(ms: int) -> set[str]:
    s = ms / 1000
    former = {f'{s:g} s'.replace('.', ',')}
    if s >= 60 and s % 60 == 0:
        former.add(f'{int(s // 60)} min')
    return former


class OversiktenDekkerHverLoekkeTests(SimpleTestCase):

    def test_hver_fil_med_en_loekke_staar_i_3d(self):
        tekst = seksjon_3d()
        mangler = [f.relative_to(ROT).as_posix() for f in filer_med_loekke()
                   if f.name not in tekst]
        self.assertEqual(mangler, [], 'ny løkke i nettleseren — før den inn i RUNBOOK_VAKT.md §3d')

    def test_letingen_finner_noe(self):
        """En leting som finner null, melder grønt om en dekning den ikke har."""
        navn = {f.name for f in filer_med_loekke()}
        self.assertTrue({'ko.js', 'portal-utils.js', 'admin_status.html'} <= navn, navn)


class TalleneStemmerTests(SimpleTestCase):

    def test_hver_navngitt_konstant_har_riktig_tall_i_raden(self):
        feil = []
        rader = [r for r in seksjon_3d().splitlines() if r.startswith('|')]
        sett = 0
        for rad in rader:
            for navn in re.findall(r'`([A-Z][A-Z0-9_]+_MS)`', rad):
                ms = ms_konstant(navn)
                if ms is None:
                    feil.append(f'{navn} finnes ikke i static/js/')
                    continue
                sett += 1
                # Hele tallet: «2,5 s» inneholder «5 s», og en endring fra 2,5
                # til 5 sekunder gikk grønt til mutasjonstestingen fant det.
                if not any(re.search(r'(?<![\d,])' + re.escape(t) + r'\b', rad) for t in _sekundtekst(ms)):
                    feil.append(f'{navn} er {ms} ms i koden, men raden sier: {rad[:90]}')
        self.assertEqual(feil, [])
        self.assertGreaterEqual(sett, 6, 'tabellen har mistet konstantene sine')
