"""Ingen testmetode skygger for en annen i samme klasse (19. okt. 2026).

To `def test_x` i én klasse er gyldig Python: den siste vinner, og den første
kjøres aldri — uten feil, uten advarsel, og med et testtall som ser riktig ut.
Det er en dekning som bare finnes i kildekoden. Sveipet 19. okt. 2026 fant
ingen; denne holder det slik.
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def skyggede(kilde: str) -> list[str]:
    """`Klasse.metode` for hver metode som står to ganger i samme klasse."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        tre = ast.parse(kilde)
    funn = []
    for klasse in (n for n in ast.walk(tre) if isinstance(n, ast.ClassDef)):
        sett = set()
        for metode in klasse.body:
            if isinstance(metode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if metode.name in sett:
                    funn.append(f'{klasse.name}.{metode.name} (linje {metode.lineno})')
                sett.add(metode.name)
    return funn


class IngenSkyggedeTesterTests(SimpleTestCase):

    def test_ingen_metode_staar_to_ganger_i_samme_klasse(self):
        rot = Path(settings.BASE_DIR)
        funn = [f'{sti.relative_to(rot)}: {navn}'
                for sti in sorted(rot.glob('*/tests*.py'))
                for navn in skyggede(sti.read_text(encoding='utf-8'))]
        self.assertEqual(funn, [], 'Den første av hver kjøres aldri:\n  ' + '\n  '.join(funn))

    def test_sveipet_ser_en_skygge(self):
        """Sperrehaken: finner sveipet ingenting her, er testen over tom."""
        kilde = 'class A:\n    def test_x(self): pass\n    def test_x(self): pass\n'
        self.assertEqual(skyggede(kilde), ['A.test_x (linje 3)'])
        self.assertEqual(skyggede('class B:\n    def test_x(self): pass\n'
                                  'class C:\n    def test_x(self): pass\n'), [])
