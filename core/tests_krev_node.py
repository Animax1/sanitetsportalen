"""JS-testene hopper ikke stille over seg selv i CI (26. sep. 2026, D1).

Rundt 160 tester kjører JS-reglene i node og hoppet over seg selv når node
manglet. Uten CI var det ingen som så forskjellen på «grønn» og «grønn fordi
halvparten ikke kjørte». `KREV_NODE=1` (satt i `.github/workflows/tester.yml`)
gjør mangelen rød, og det virker bare hvis alle spør samme sted.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

from patients import js_test_utils


class KrevNodeTests(SimpleTestCase):

    def test_uten_kravet_hopper_den_over_som_foer(self):
        with patch.dict(os.environ, {'KREV_NODE': ''}), \
                patch('patients.js_test_utils.shutil.which', return_value=None):
            self.assertFalse(js_test_utils.node_available())

    def test_med_kravet_og_uten_node_er_det_en_feil(self):
        with patch.dict(os.environ, {'KREV_NODE': '1'}), \
                patch('patients.js_test_utils.shutil.which', return_value=None), \
                self.assertRaises(RuntimeError):
            js_test_utils.node_available()

    def test_med_node_er_svaret_ja_uansett(self):
        with patch.dict(os.environ, {'KREV_NODE': '1'}), \
                patch('patients.js_test_utils.shutil.which', return_value='/usr/bin/node'):
            self.assertTrue(js_test_utils.node_available())


class NodeSjekkesEttStedTests(SimpleTestCase):
    """En test som spør `shutil.which('node')` selv, går forbi `KREV_NODE` i
    stillhet — og det var ni av dem til 26. sep. 2026."""

    def test_bare_node_available_spoer_etter_node(self):
        rot = Path(settings.BASE_DIR)
        funn = []
        for sti in sorted(rot.glob('*/**/*.py')):
            rel = sti.relative_to(rot).as_posix()
            if rel.startswith('.') or '/site-packages/' in rel or rel == 'patients/js_test_utils.py':
                continue
            try:
                tre = ast.parse(sti.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tre):
                if (isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'which'
                        and node.args and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == 'node'):
                    funn.append(f'{rel}:{node.lineno}')
        self.assertEqual(funn, [], 'Bruk patients.js_test_utils.node_available()')
