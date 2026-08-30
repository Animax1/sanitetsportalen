# -*- coding: utf-8 -*-
"""Databasen skal aldri velges stille.

`dj_database_url.config()` faller tilbake til en SQLite-fil når
`DATABASE_URL` ikke finnes. Lokalt er det riktig. På Railway er containeren
flyktig, så filen er tom og forsvinner igjen — og fallbacken er *stille*:
appen starter, og ingenting feiler.

Det farligste tilfellet er ikke websiden, som ville vist en tom portal og
blitt oppdaget samme minutt. Det er cron-jobbene: `purge_old_logs` ville talt
null rader i en tom base, skrevet «Slettet 0 audit-logger» og avsluttet med
kode 0 — en grønn jobb som aldri håndhever lagringstidene i A.9. Det er en
feil som først oppdages den dagen noen spør hvorfor det ligger fire år med
logger i basen.

Sjekken henger på `RAILWAY_ENVIRONMENT`, ikke på `DEBUG`, fordi offline-modus
kjører `DEBUG=False` på en laptop og *skal* bruke SQLite. Testene holder
begge halvdelene fast.
"""
from __future__ import annotations

import importlib
import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class DatabaseFallbackTests(SimpleTestCase):
    """Merk: hver test laster `myproject.settings` på nytt.

    Modulen må lastes tilbake til det ekte miljøet etterpå, og *utenfor*
    miljøpatchen — gjør man det inni, feiler oppryddingen av samme grunn som
    testen, og resten av kjøringen arver en halvlastet settings-modul.
    """

    def setUp(self):
        from myproject import settings as settings_module
        self.settings_module = settings_module
        self.addCleanup(lambda: importlib.reload(settings_module))

    def _last(self, **env):
        """Miljøet som er, med `env` lagt oppå."""
        with mock.patch.dict(os.environ, env, clear=False):
            return importlib.reload(self.settings_module)

    def _last_uten(self, *fjern, **env):
        """Miljøet som er, minus navngitte variabler, med `env` lagt oppå.

        `SECRET_KEY` og `DEBUG` blir stående: uten dem ville oppstarten
        stoppet på SECRET_KEY-sjekken i stedet, og testen gått grønt av feil
        grunn.
        """
        miljo = {k: v for k, v in os.environ.items() if k not in fjern}
        miljo.update(env)
        with mock.patch.dict(os.environ, miljo, clear=True):
            return importlib.reload(self.settings_module)

    def test_sqlite_paa_railway_stopper_oppstarten(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            self._last(RAILWAY_ENVIRONMENT='production',
                       DATABASE_URL='sqlite:///tmp/flyktig.sqlite3')
        self.assertIn('DATABASE_URL', str(ctx.exception),
                      'stoppet av en annen grunn enn databasen')

    def test_manglende_variabel_stopper_ogsaa(self):
        """Den ekte formen: variabelen finnes ikke i det hele tatt.

        `load_dotenv()` i settings ville hentet den fra utviklerens `.env`, så
        den slås av her — på Railway finnes det ingen slik fil.
        """
        with mock.patch.object(self.settings_module, 'load_dotenv',
                               lambda *a, **k: None):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                self._last_uten('DATABASE_URL',
                                RAILWAY_ENVIRONMENT='production')
        self.assertIn('DATABASE_URL', str(ctx.exception))

    def test_postgres_paa_railway_slipper_gjennom(self):
        """Speilet: en riktig konfigurert tjeneste skal ikke merke sjekken."""
        lastet = self._last(
            RAILWAY_ENVIRONMENT='production',
            DATABASE_URL='postgres://bruker:hemmelig'
                         '@postgres.railway.internal:5432/railway')
        self.assertIn('postgresql', lastet.DATABASES['default']['ENGINE'])

    def test_offline_paa_laptop_slipper_gjennom(self):
        """Offline-modus kjører `DEBUG=False` på en laptop og bruker SQLite.

        Hang sjekken på `DEBUG` i stedet, ville feltbruken vært umulig — og
        det er nettopp den bruken portalen har når nettet er borte.

        **`DEBUG=False` settes eksplisitt her.** Uten det gikk testen grønt
        uansett hvordan sjekken var skrudd sammen, fordi utviklermiljøet
        kjører med `DEBUG=True` — og da beviste den ingenting. Funnet ved
        mutasjonstesting 30. aug. 2026.
        """
        lastet = self._last_uten(
            'RAILWAY_ENVIRONMENT',
            DEBUG='False', OFFLINE_MODE='True',
            DATABASE_URL='sqlite:///tmp/offline.sqlite3')
        self.assertIn('sqlite', lastet.DATABASES['default']['ENGINE'])
        self.assertFalse(lastet.DEBUG, 'testen kjørte ikke i den formen den beskriver')
