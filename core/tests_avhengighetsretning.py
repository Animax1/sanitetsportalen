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

#: **Tom siden 14. sep. 2026, og skal forbli det.**
#:
#: Sto her en dag med fem rader: `admin_status` hentet modultall ved å
#: importere `vaktliste` og `oppdrag`, og portalinnstillingene importerte
#: `vaktliste.fil` for å tegne, validere og lagre modulens egne felter.
#: Begge er nå registre — `core/driftstatus.py` og
#: `core/portalinnstillinger.py` — etter samme idiom som `core/stats.py`.
#:
#: Lista blir stående tom framfor å slettes, som et sted å skrive et unntak
#: ned hvis et noen gang må tas. Et unntak som *må* tas, skal stå med
#: begrunnelse; et som bare snek seg inn, skal feile.
KJENTE_UNNTAK: set[tuple[str, str]] = set()

#: `accounts` og `audit` er også rammeverk (`TEKNISK_GJELD.md` §1), og måles
#: derfor med samme målestokk — men de har sin egen liste, fordi `core`s skal
#: stå tom og disse ikke gjør det ennå.
#:
#: **Kontoopprettelsen lager en `oppdrag.Enhet`.** Velger admin kontotypen
#: «bil», valideres enhetsnavnet i `accounts/forms.py` og raden opprettes (og
#: hentes fram igjen, om den er pensjonert) i `accounts/views.py`.
#:
#: Dette er samme slags kobling som kortet «Pasientregistrering» var, og
#: `core/kontokobling.py` er mekanismen den hører hjemme i — men det er en
#: annen form: kortet er et skjema ved siden av kontoen, dette er *selve
#: kontoopprettelsen* som får en sideeffekt i en modul. Å flytte den betyr
#: kirurgi i brukeropprettelsen, og det skal ikke skje i samme runde som alt
#: annet. Se `TODO.md`.
#:
#: Lista skal **aldri vokse**.
KJENTE_UNNTAK_RAMMEVERK: set[tuple[str, str]] = {
    ('accounts/forms.py', 'oppdrag.models'),
    ('accounts/views.py', 'oppdrag.models'),
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

    def test_accounts_og_audit_maales_med_samme_malestokk(self) -> None:
        """`accounts` og `audit` er rammeverk de også (`TEKNISK_GJELD.md` §1).

        Kontoappen importerte `patients.models` fram til 14. sep. 2026, for å
        tegne kortet «Pasientregistrering» på brukersiden — og ingen test
        hindret at det ble to moduler i morgen. Nå går kortet gjennom
        `core/kontokobling.py`, og regelen står skrevet.
        """
        rot = Path(settings.BASE_DIR)
        funn = []
        for app in ('accounts', 'audit'):
            for sti in sorted(Path(rot, app).rglob('*.py')):
                if 'migrations' in sti.parts or sti.name.startswith('tests'):
                    continue
                relativ = str(sti.relative_to(rot))
                for modul in _importer(sti):
                    if modul.split('.')[0] not in MODULAPPER:
                        continue
                    if (relativ, modul) in KJENTE_UNNTAK_RAMMEVERK:
                        continue
                    funn.append(f'{relativ}: {modul}')

        self.assertEqual(funn, [], (
            'Kontoappen importerer en modul. Hva en konto *betyr* hos en modul '
            'er modulens sak — se `core/kontokobling.py`:\n  '
            + '\n  '.join(funn)))

    def test_rammeverkets_sperrehake_krymper_bare(self) -> None:
        """Som testen under, for den andre lista."""
        rot = Path(settings.BASE_DIR)
        doede = [f'{relativ}: {modul}'
                 for relativ, modul in sorted(KJENTE_UNNTAK_RAMMEVERK)
                 if modul not in _importer(Path(rot, relativ))]
        self.assertEqual(doede, [], (
            'Disse står som kjente unntak, men importen finnes ikke lenger. '
            'Ta dem ut av lista:\n  ' + '\n  '.join(doede)))

    def test_sperrehaken_krymper_bare(self) -> None:
        """Et unntak som er ryddet skal ut av lista.

        Uten denne ville `KJENTE_UNNTAK` blitt en liste over ting som *en gang*
        var galt, og da slutter den å si noe om koden slik den er nå. Lista er
        tom i dag; testen står for den dagen noen legger noe i den.
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
