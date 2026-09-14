"""Avhengighetsretningen: `core` er rammeverket, modulene ligger over.

Dette er hele gevinsten av flyttingen i `docs/PLAN_FLYTTING_TIL_CORE.md`, og
den eneste måten å beholde den. Retningen var snudd fram til 14. sep. 2026:
`core.backup`, `core.arkiv` og `core.offsite` importerte alle
`patients.models`, fordi `AppSetting` og `Backup` bodde der. Ingenting gikk i
stykker av det — det er nettopp derfor det fikk stå i et år, og nettopp derfor
det trenger en test framfor en god intensjon.

Importene leses med **AST og ikke som tekst**, slik at omtale i docstrings og
kommentarer ikke gir falske treff. De er det en god del av i akkurat disse
filene. Samme grep som `OppdragImportererIkkeVaktlista` og
`StatistikkappenNavngirIngenKilde`.
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

#: Modulappene. `core` skal kunne kjøre uten en eneste av dem.
MODULAPPER = {'patients', 'oppdrag', 'vaktliste', 'statistikk'}

#: Importer som skal være der, med begrunnelse.
#:
#: Modulregisteret **skal** navngi modulene sine — det er det et register er.
#: `_REGISTERED_MODULES` er den eksplisitte lista `CLAUDE.md` beskriver, og
#: uten den ville portalen ikke visst hvilke moduler som finnes. Den står
#: inne i en funksjon, ikke på toppnivå, nettopp for å unngå importsykelen.
TILLATT = {
    ('core/modules.py', 'oppdrag.module'),
    ('core/modules.py', 'patients.module'),
    ('core/modules.py', 'statistikk.module'),
    ('core/modules.py', 'vaktliste.module'),
}

#: **Sperrehake, ikke tillatelse.** Disse er gjeld, ikke design.
#:
#: Begge er *sider* og ikke rammeverk: server-status-dashbordet viser tall per
#: modul, og portalinnstillingene skriver vaktlistas e-postmottakere. Koblingen
#: fantes før flyttingen også — men da lå filene i `patients`, så den leste som
#: «modul → modul» og ikke som «rammeverk → modul».
#:
#: Riktig løsning er den statistikkappen alt bruker: et register modulene
#: melder seg inn i, slik at `core` ikke navngir noen av dem (`core/stats.py`,
#: samme idiom som `core.backup` og `core.arkiv`). Det er en egen jobb med egen
#: risiko, og den skal ikke ri på en flytterunde — se `TODO.md`.
#:
#: Lista skal **aldri vokse**. Nye brudd feiler; disse står oppført til noen
#: rydder dem.
KJENTE_UNNTAK = {
    ('core/admin_status.py', 'oppdrag'),
    ('core/admin_status.py', 'oppdrag.models'),
    ('core/admin_status.py', 'vaktliste'),
    ('core/admin_status.py', 'vaktliste.models'),
    ('core/views_admin.py', 'vaktliste'),
}


def _importer(sti: Path) -> list[str]:
    tre = ast.parse(sti.read_text(encoding='utf-8'), filename=str(sti))
    ut = []
    for node in ast.walk(tre):
        if isinstance(node, ast.ImportFrom) and node.module:
            ut.append(node.module)
        elif isinstance(node, ast.Import):
            ut.extend(a.name for a in node.names)
    return ut


class CoreImportererIngenModulTests(SimpleTestCase):

    def test_produksjonskoden_i_core_star_pa_egne_bein(self) -> None:
        rot = Path(settings.BASE_DIR)
        funn = []
        for sti in sorted(Path(rot, 'core').rglob('*.py')):
            if 'migrations' in sti.parts or sti.name.startswith('tests'):
                continue
            relativ = str(sti.relative_to(rot))
            for modul in _importer(sti):
                if modul.split('.')[0] not in MODULAPPER:
                    continue
                if (relativ, modul) in TILLATT or (relativ, modul) in KJENTE_UNNTAK:
                    continue
                funn.append(f'{relativ}: {modul}')

        self.assertEqual(funn, [], (
            'Rammeverket importerer en modul. Retningen skal gå én vei — '
            '`core` nederst, modulene over. Hører det som importeres hjemme '
            'i portalen, skal det flyttes til `core`; hører det hjemme i '
            'modulen, skal `core` ikke trenge det:\n  ' + '\n  '.join(funn)))

    def test_sperrehaken_krymper_bare(self) -> None:
        """Et unntak som er ryddet skal ut av lista.

        Uten denne ville `KJENTE_UNNTAK` blitt en liste over ting som *en gang*
        var galt, og da slutter den å si noe om koden slik den er nå.
        """
        rot = Path(settings.BASE_DIR)
        doede = []
        for relativ, modul in sorted(KJENTE_UNNTAK):
            if modul not in _importer(Path(rot, relativ)):
                doede.append(f'{relativ}: {modul}')
        self.assertEqual(doede, [], (
            'Disse står som kjente unntak, men importen finnes ikke lenger. '
            'Ta dem ut av lista:\n  ' + '\n  '.join(doede)))

    def test_den_tillatte_importen_finnes_fortsatt(self) -> None:
        """Speilet: en tillatelsesliste som peker på noe som er borte, er en
        regel som stille slutter å bety noe."""
        rot = Path(settings.BASE_DIR)
        for relativ, modul in sorted(TILLATT):
            with self.subTest(fil=relativ):
                self.assertIn(modul, _importer(Path(rot, relativ)))

    def test_portalens_scope_bor_i_core(self) -> None:
        """`hent_aktiv_vakt` er delt av alle modulene, og lå i pasientmodulen
        fordi `AppSetting`-pekeren gjorde det. Da måtte oppdrag, vaktliste og
        statistikk importere *pasienter* for å vite hvilken vakt de var i."""
        from core.vakt import hent_aktiv_vakt, vakt_for_year   # noqa: F401

    def test_ingen_modul_henter_vakta_fra_pasientmodulen(self) -> None:
        """Funksjonene ligger fortsatt i `patients/services`-navnerommet fordi
        modulen bruker dem selv. Det gjør det lett å fortsette den gamle vanen
        uten å merke det — derfor denne."""
        rot = Path(settings.BASE_DIR)
        funn = []
        for app in sorted(MODULAPPER - {'patients'}) + ['core', 'accounts', 'audit']:
            for sti in sorted(Path(rot, app).rglob('*.py')):
                if 'migrations' in sti.parts:
                    continue
                tre = ast.parse(sti.read_text(encoding='utf-8'), filename=str(sti))
                for node in ast.walk(tre):
                    if not isinstance(node, ast.ImportFrom) or node.module != 'patients.services':
                        continue
                    for alias in node.names:
                        if alias.name in {'hent_aktiv_vakt', 'vakt_for_year'}:
                            funn.append(f'{sti.relative_to(rot)}: {alias.name}')
        self.assertEqual(funn, [], (
            'Vakta hentes fra pasientmodulen. Den bor i `core.vakt`:\n  '
            + '\n  '.join(funn)))
