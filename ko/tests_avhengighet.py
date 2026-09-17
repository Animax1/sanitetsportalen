"""KO er øverste lag: ingen annen modul kjenner den (`FORSLAG_KO.md` §3.3).

`ko` → `vaktliste` og `ko` → `oppdrag`. Motsatt vei er det som må vernes, og
det er nettopp den veien som er lett å ta uten å merke det: sentralbordet skal
til slutt vise hendelsen et oppdrag hører til, og den korteste veien dit fra
`oppdrag/views.py` er en import.

Testen bor **her** og ikke i de to andre modulene, av samme grunn som
`OppdragImportererIkkeVaktlista` bor i `vaktliste/`: det er den importerte som
mister uavhengigheten sin, og det er derfor dens kant å forsvare.

Importene leses med **AST og ikke som tekst**, slik at omtale i docstrings og
kommentarer ikke gir falske treff. Det er en god del av det i akkurat disse
filene.
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

#: Modulene som ligger **under** KO. De leser ikke oppover.
UNDER_KO = ('oppdrag', 'vaktliste', 'statistikk', 'patients')

#: Importer av `ko` som skal være der, med begrunnelse.
#:
#: Modulregisteret **skal** navngi modulene sine — det er det et register er.
#: Den står inne i en funksjon og ikke på toppnivå, for å unngå importsykelen.
TILLATT: set[tuple[str, str]] = {
    ('core/modules.py', 'ko.module'),
}

#: Den ene kanten som en dag skal gå andre veien: `Oppdrag.hendelse`, en nullbar
#: FK fra oppdrag til hendelsen (pulje 3/5). Den peker fra oppdrag til hendelse
#: og aldri motsatt — men en FK krever ikke en Python-import av `ko` i
#: `oppdrag/`, den krever en strengreferanse (`'ko.Hendelse'`). Lista står tom
#: i dag, og et unntak som **må** tas skal stå her med begrunnelse.
KJENTE_UNNTAK: set[tuple[str, str]] = set()


def _importer(sti: Path) -> list[str]:
    tre = ast.parse(sti.read_text(encoding='utf-8'), filename=str(sti))
    ut = []
    for node in ast.walk(tre):
        if isinstance(node, ast.ImportFrom) and node.module:
            ut.append(node.module)
        elif isinstance(node, ast.Import):
            ut.extend(a.name for a in node.names)
    return ut


class IngenImportererKoTests(SimpleTestCase):

    def _filer(self, app: str) -> list[Path]:
        rot = Path(settings.BASE_DIR)
        return [s for s in sorted(Path(rot, app).rglob('*.py'))
                if 'migrations' not in s.parts and not s.name.startswith('tests')]

    def test_ingen_modul_under_ko_importerer_ko(self) -> None:
        rot = Path(settings.BASE_DIR)
        funn = []
        for app in UNDER_KO:
            for sti in self._filer(app):
                relativ = str(sti.relative_to(rot))
                for modul in _importer(sti):
                    if modul.split('.')[0] != 'ko':
                        continue
                    if (relativ, modul) in KJENTE_UNNTAK:
                        continue
                    funn.append(f'{relativ}: {modul}')
        self.assertEqual(funn, [], (
            'En modul under KO importerer KO. Retningen skal gå én vei — KO '
            'leser dem, de kjenner ikke den:\n  ' + '\n  '.join(funn)
            + '\n\nTrenger oppdrag å peke på en hendelse, er det en FK med '
              'strengreferanse («ko.Hendelse»), og unntaket skal navngis og '
              'begrunnes i KJENTE_UNNTAK her.'))

    def test_rammeverket_importerer_ikke_ko_utenfor_registeret(self) -> None:
        """`core`, `accounts` og `audit` er rammeverk, og skal kunne kjøre uten
        en eneste modul. Regelen er den samme som i
        `core/tests_avhengighetsretning.py`; den gjentas ikke for `core` der,
        men denne dekker `accounts` og `audit` for `ko` spesifikt."""
        rot = Path(settings.BASE_DIR)
        funn = []
        for app in ('core', 'accounts', 'audit'):
            for sti in self._filer(app):
                relativ = str(sti.relative_to(rot))
                for modul in _importer(sti):
                    if modul.split('.')[0] != 'ko':
                        continue
                    if (relativ, modul) in TILLATT:
                        continue
                    funn.append(f'{relativ}: {modul}')
        self.assertEqual(funn, [], (
            'Rammeverket importerer KO utenfor modulregisteret:\n  '
            + '\n  '.join(funn)))

    def test_den_tillatte_importen_finnes_fortsatt(self) -> None:
        """Speilet: en tillatelsesliste som peker på noe som er borte, er en
        regel som stille slutter å bety noe."""
        rot = Path(settings.BASE_DIR)
        for relativ, modul in sorted(TILLATT):
            with self.subTest(fil=relativ):
                self.assertIn(modul, _importer(Path(rot, relativ)))

    def test_sperrehaken_krymper_bare(self) -> None:
        """Et unntak som er ryddet skal ut av lista — ellers blir den en liste
        over ting som *en gang* var galt."""
        rot = Path(settings.BASE_DIR)
        doede = [f'{relativ}: {modul}'
                 for relativ, modul in sorted(KJENTE_UNNTAK)
                 if modul not in _importer(Path(rot, relativ))]
        self.assertEqual(doede, [], (
            'Disse står som kjente unntak, men importen finnes ikke lenger:\n  '
            + '\n  '.join(doede)))

    def test_testen_finner_faktisk_filer(self) -> None:
        """Sperrehake. Finner gjennomgangen ingen filer, passerer den trivielt
        — og det har skjedd i denne kodebasen før."""
        for app in UNDER_KO:
            with self.subTest(app=app):
                self.assertGreaterEqual(len(self._filer(app)), 4)
