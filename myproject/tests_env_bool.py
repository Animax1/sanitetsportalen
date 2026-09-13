"""Boolske miljøvariabler leses uavhengig av store og små bokstaver (13. sep. 2026).

`RATELIMIT_ENABLE=true` — slik README, runbook og Railway hadde det — ga False
med `== 'True'`, og rate-limitingen var av i prod. Denne låser regelen.
"""
import os
from unittest import mock

from django.test import SimpleTestCase

from myproject.settings import _env_bool


class EnvBoolTests(SimpleTestCase):
    def _med(self, verdi, default=True):
        with mock.patch.dict(os.environ, {'X_TEST': verdi} if verdi is not None else {}, clear=False):
            if verdi is None:
                os.environ.pop('X_TEST', None)
            return _env_bool('X_TEST', default)

    def test_true_i_alle_stavemaater(self):
        for v in ('true', 'True', 'TRUE', ' true ', '1', 'yes', 'on', 'ja'):
            self.assertTrue(self._med(v, default=False), v)

    def test_false_i_alle_stavemaater(self):
        for v in ('false', 'False', 'FALSE', '0', 'no', 'off', 'nei', 'tull'):
            self.assertFalse(self._med(v, default=True), v)

    def test_mangler_eller_tom_gir_default(self):
        self.assertTrue(self._med(None, default=True))
        self.assertFalse(self._med(None, default=False))
        self.assertTrue(self._med('', default=True))
        self.assertTrue(self._med('   ', default=True))
