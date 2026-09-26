"""`core.jsonkropp` er den eneste kopien (26. sep. 2026, E5).

Regelen leses av koden med AST, ikke av en liste over hvor kopiene sto: en ny
modul som skriver sin egen `_json_body` er dekket den dagen den kommer.
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase

from core.jsonkropp import json_body, json_feil

#: Navn en modul ikke skal definere på toppnivå — de finnes i `core.jsonkropp`.
REGISTRERTE = {'json_body', '_json_body', 'json_feil', '_feil'}

APPER = ('accounts', 'audit', 'backlog', 'core', 'ko', 'oppdrag', 'patients',
         'statistikk', 'vaktliste')


def egne_kopier(rot=None):
    """(fil, navn) for hver toppnivå-funksjon med et av navnene over."""
    rot = Path(rot or settings.BASE_DIR)
    funn = []
    for app in APPER:
        for fil in sorted((rot / app).rglob('*.py')):
            if fil.name == 'jsonkropp.py' or 'migrations' in fil.parts:
                continue
            tre = ast.parse(fil.read_text(encoding='utf-8'), filename=str(fil))
            for node in tre.body:
                if isinstance(node, ast.FunctionDef) and node.name in REGISTRERTE:
                    funn.append((str(fil.relative_to(rot)), node.name))
    return funn


class IngenEgneKopierTests(SimpleTestCase):

    def test_ingen_modul_definerer_sin_egen(self):
        self.assertEqual(egne_kopier(), [], (
            'Importér fra core.jsonkropp i stedet: fem like kopier holdt seg like '
            'bare fordi M8 fant alle da den rettet dem.'))

    def test_regelen_ser_en_kopi(self):
        """Vern mot at testen blir tom: en oppdiktet app med en kopi skal gi funn."""
        import tempfile
        with tempfile.TemporaryDirectory() as mappe:
            app = Path(mappe) / 'ko'
            app.mkdir()
            (app / 'views.py').write_text(
                'def _json_body(request):\n    return {}\n'
                'class K:\n    def _feil(self):\n        pass\n', encoding='utf-8')
            self.assertEqual(egne_kopier(mappe), [('ko/views.py', '_json_body')])


class JsonKroppTests(SimpleTestCase):

    def test_bare_et_objekt_er_en_kropp(self):
        for kropp in (b'[]', b'"x"', b'null', b'1', b'[{"a": 1}]', b'{', b''):
            req = RequestFactory().post('/', data=kropp, content_type='application/json')
            self.assertEqual(json_body(req), {}, kropp)
        req = RequestFactory().post('/', data=b'{"a": 1}', content_type='application/json')
        self.assertEqual(json_body(req), {'a': 1})

    def test_feilsvaret_har_formen_klienten_leser(self):
        svar = json_feil('Nei', 403)
        self.assertEqual(svar.status_code, 403)
        self.assertEqual(svar.content, b'{"status": "error", "message": "Nei"}')
