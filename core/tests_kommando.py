# -*- coding: utf-8 -*-
"""Cron-jobbene skal si hva som gikk galt, på én linje.

30. aug. 2026 falt `purge_old_logs` og `kollaps_arkiv` i staging på samme
avviste databasepassord. Begge la igjen fire stablede tracebacks der den ene
setningen som betyr noe sto omtrent på linje 140, mellom to identiske kopier
av seg selv — og de to loggene måtte leses i sin helhet for å fastslå at de
sa det samme.

Testene her holder fast på tre ting:

1. Meldingen bærer den underliggende årsaken. Kortere er ikke bedre hvis den
   koster deg diagnosen.
2. Jobben er fortsatt rød. En lesbar feil som avslutter med kode 0 er verre
   enn en uleselig som feiler.
3. **Alle tre jobbene bruker den.** Den som blir glemt, er den som feiler
   uleselig den dagen det haster.
"""
from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase, SimpleTestCase, override_settings

from core.kommando import lesbar_dbfeil

#: Slik psycopg2 faktisk formulerer seg — den gjentar seg selv, og det er
#: gjentakelsen som gjør loggen dobbelt så lang som den trenger å være.
PSYCOPG_TEKST = (
    'connection to server at "postgres.railway.internal" '
    '(fd12:d621:b18d:1:b000:fd:13f:e7be), port 5432 failed: FATAL:  '
    'password authentication failed for user "postgres"\n'
    'connection to server at "postgres.railway.internal" '
    '(fd12:d621:b18d:1:b000:fd:13f:e7be), port 5432 failed: FATAL:  '
    'password authentication failed for user "postgres"\n'
)


class LesbarDbfeilTests(SimpleTestCase):

    def test_tilkoblingsfeil_blir_en_kommandofeil(self):
        with self.assertRaises(CommandError) as ctx:
            with lesbar_dbfeil('ingenting ble slettet'):
                raise OperationalError(PSYCOPG_TEKST)
        melding = str(ctx.exception)
        self.assertIn('ingenting ble slettet', melding,
                      'meldingen sier ikke hva som ikke skjedde')
        self.assertIn('password authentication failed', melding,
                      'aarsaken forsvant — da er den ubrukelig')
        self.assertIn('DATABASE_URL', melding, 'ingen vei videre for leseren')

    def test_gjentakelsen_klippes_bort(self):
        """Psycopg2 sier det samme to ganger. Én gang holder."""
        with self.assertRaises(CommandError) as ctx:
            with lesbar_dbfeil('ingenting ble slettet'):
                raise OperationalError(PSYCOPG_TEKST)
        aarsakslinjer = [rad for rad in str(ctx.exception).splitlines()
                         if 'password authentication' in rad]
        self.assertEqual(len(aarsakslinjer), 1, aarsakslinjer)

    def test_aarsaken_henger_ved_for_den_som_vil_ha_hele(self):
        """`raise … from` beholder sporet. Vi forkorter visningen, ikke
        historikken."""
        with self.assertRaises(CommandError) as ctx:
            with lesbar_dbfeil('ingenting ble slettet'):
                raise OperationalError(PSYCOPG_TEKST)
        self.assertIsInstance(ctx.exception.__cause__, OperationalError)

    def test_tom_feil_gir_likevel_en_melding(self):
        """En `OperationalError` uten tekst finnes — timeouts har det. Da er
        klassenavnet bedre enn en tom linje."""
        with self.assertRaises(CommandError) as ctx:
            with lesbar_dbfeil('ingen backup ble tatt'):
                raise OperationalError()
        self.assertIn('OperationalError', str(ctx.exception))

    def test_andre_feil_slipper_gjennom_uroert(self):
        """Bare tilkoblingsfeil. En `ValueError` inne i jobben er en bug, og
        den skal ha hele sporet sitt."""
        with self.assertRaises(ValueError):
            with lesbar_dbfeil('ingenting ble slettet'):
                raise ValueError('en ekte bug')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class CronjobbeneBrukerDenTests(TestCase):
    """Alle tre, ikke to.

    Den som blir glemt er den som feiler uleselig den dagen det haster — og
    for `db_backup` er «den dagen» per definisjon en dag noe alt har gått
    galt.
    """

    def _krev_lesbar(self, kommando, maal, forventet_tekst):
        with mock.patch(maal, side_effect=OperationalError(PSYCOPG_TEKST)):
            with self.assertRaises(CommandError) as ctx:
                call_command(kommando, stdout=StringIO(), stderr=StringIO())
        melding = str(ctx.exception)
        self.assertIn(forventet_tekst, melding)
        self.assertIn('password authentication failed', melding)
        self.assertIn('DATABASE_URL', melding)

    def test_purge_old_logs(self):
        self._krev_lesbar(
            'purge_old_logs',
            'audit.management.commands.purge_old_logs.LoginEvent.objects.filter',
            'ingenting ble slettet')

    def test_kollaps_arkiv(self):
        self._krev_lesbar(
            'kollaps_arkiv',
            # Nøyaktig der staging-sporet brakk: `handler.kandidater()`,
            # den første spørringen etter at handlerne er funnet.
            'patients.management.commands.kollaps_arkiv.Command._kjor_modul',
            'ingen arkiv ble kollapset')

    def test_db_backup(self):
        self._krev_lesbar(
            'db_backup',
            'patients.models.BackupConfig.get',
            'ingen backup ble tatt')
