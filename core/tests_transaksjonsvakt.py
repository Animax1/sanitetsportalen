"""Vakten i `core/transaksjonsvakt.py`: under test krever `select_for_update` en transaksjon
koden selv har åpnet, ikke bare den `TestCase` legger rundt hver test (20. okt. 2026).

Prøvene går mot ekte spørringer, ikke mot hjelperen alene — det som skal holdes i live er at
vakten **er installert** i kjøringen, ikke bare at funksjonen finnes.
"""
from __future__ import annotations

from django.conf import settings
from django.db import connection, transaction
from django.test import TestCase

from core.models import AppSetting
from core.transaksjonsvakt import har_egen_transaksjon


def _laas():
    return AppSetting.objects.select_for_update().filter(key='vakt.prove').first()


class TransaksjonsvaktenTests(TestCase):

    def test_slaatt_paa_under_test(self):
        self.assertTrue(settings.TRANSAKSJONSVAKT)

    def test_bare_testens_transaksjon_avvises(self):
        """Det er hele feilen fra tavla: her ville Django selv sagt ja, også på PostgreSQL."""
        self.assertTrue(connection.in_atomic_block, 'premisset: TestCase har en transaksjon åpen')
        self.assertFalse(har_egen_transaksjon(connection))
        with self.assertRaises(transaction.TransactionManagementError):
            _laas()

    def test_kodens_egen_transaksjon_slipper_gjennom(self):
        with transaction.atomic():
            self.assertTrue(har_egen_transaksjon(connection))
            self.assertIsNone(_laas())

    def test_dekoratoren_slipper_gjennom(self):
        self.assertIsNone(transaction.atomic(_laas)())

    def test_vanlige_spoerringer_roeres_ikke(self):
        self.assertIsNone(AppSetting.objects.filter(key='vakt.prove').first())
        self.assertEqual(AppSetting.objects.filter(key='vakt.prove').count(), 0)
