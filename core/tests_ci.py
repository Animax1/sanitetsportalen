"""CI kjører alle appene med tester (26. sep. 2026, D1).

`myproject` sto utenfor kommandoen i `CLAUDE.md` til 14. sep. 2026, og da kjørte
ingen settings-vaktene. Samme feil i `.github/workflows/tester.yml` ville gitt
et grønt merke på GitHub over tester som aldri kjørte. Regelen har ingen
kjøretid — den gjelder hva en YAML-fil sier — så her leses fila.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

WORKFLOW = Path(settings.BASE_DIR) / '.github' / 'workflows' / 'tester.yml'


def _apper_med_tester() -> set[str]:
    rot = Path(settings.BASE_DIR)
    return {p.parent.name for p in rot.glob('*/tests*.py')} | {
        p.parent.parent.name for p in rot.glob('*/tests/__init__.py')}


def _uten_kommentarer(tekst: str) -> str:
    return '\n'.join(l for l in tekst.splitlines() if not l.lstrip().startswith('#'))


class WorkflowenTests(SimpleTestCase):

    def setUp(self):
        self.tekst = _uten_kommentarer(WORKFLOW.read_text(encoding='utf-8'))

    def test_alle_appene_med_tester_kjoeres(self):
        kjoert = set()
        for linje in re.findall(r'manage\.py test ([^\n]+)', self.tekst):
            kjoert |= {ord for ord in linje.split() if not ord.startswith('-')}
        self.assertEqual(sorted(_apper_med_tester() - kjoert), [],
                         'Legg appen til i .github/workflows/tester.yml og i CLAUDE.md')

    def test_node_kreves_og_basen_er_postgresql(self):
        self.assertRegex(self.tekst, r"KREV_NODE: '1'")
        self.assertRegex(self.tekst, r'image: postgres:\d+')
        self.assertIn('verifiser_migrasjoner', self.tekst)
