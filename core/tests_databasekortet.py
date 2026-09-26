"""Databasekortet på server-status (25. sep. 2026, skisse «Databasekortet»).

Svartid og tilkoblinger kan stå grønne mens én transaksjon holder en lås og alt
står i kø bak den. `db_signaler()` er regelen som farger kortet, og
`beredskap_med_databasen()` lar et rødt kort løfte trinnet til minst Oransje
(André: «la oss gjøre det du skisserte»). Begge er tjenestelag: et feil trinn er
et feil tiltak midt i en vakt, så hver grense prøves på begge sider.

SQL-en i `_db_aktivitet()` kjører bare på PostgreSQL. Den ble prøvd mot en ekte
PostgreSQL 16 med en transaksjon som holdt en lås, en forespørsel bak den og en
fremprovosert deadlock (CHANGELOG 25. sep. 2026); her prøves det SQLite gjør.
"""
import unittest
from unittest import mock

from django.test import SimpleTestCase, TestCase

from core import admin_status
from core.admin_status import (DB_HENGER_ETTER_S, DB_HENGER_ROD_S, DB_TILTAK, beredskap_med_databasen,
                               beredskapsnivaa, db_signaler)


def _sig(**kw):
    tall = dict(henger=0, henger_lenge=0, eldste_s=0, venter_laas=0, deadlocks=0)
    tall.update(kw)
    return db_signaler(tall)


class SignalreglenTests(SimpleTestCase):

    def test_rolig(self):
        self.assertEqual(_sig(), {'henger': 'gronn', 'eldste': 'gronn', 'venter_laas': 'gronn',
                                  'deadlocks': 'gronn', 'samlet': 'gronn'})

    def test_henger(self):
        self.assertEqual(_sig(henger=1)['henger'], 'gul')
        self.assertEqual(_sig(henger=2)['henger'], 'gul')
        self.assertEqual(_sig(henger=3)['henger'], 'rod')
        self.assertEqual(_sig(henger=1, henger_lenge=1)['henger'], 'rod', 'én over 30 s er nok')

    def test_eldste_transaksjon_paa_grensene(self):
        self.assertEqual(_sig(eldste_s=DB_HENGER_ETTER_S - 0.1)['eldste'], 'gronn')
        self.assertEqual(_sig(eldste_s=DB_HENGER_ETTER_S)['eldste'], 'gul')
        self.assertEqual(_sig(eldste_s=DB_HENGER_ROD_S)['eldste'], 'gul')
        self.assertEqual(_sig(eldste_s=DB_HENGER_ROD_S + 0.1)['eldste'], 'rod')

    def test_laaskoe_og_deadlocks(self):
        self.assertEqual([_sig(venter_laas=n)['venter_laas'] for n in (0, 1, 2, 3)],
                         ['gronn', 'gul', 'gul', 'rod'])
        self.assertEqual(_sig(deadlocks=1)['deadlocks'], 'gul')
        self.assertEqual(_sig(deadlocks=50)['samlet'], 'gul', 'en deadlock er en kodefeil, ikke en kø')

    def test_samlet_er_den_verste(self):
        self.assertEqual(_sig(venter_laas=1, eldste_s=DB_HENGER_ROD_S + 1)['samlet'], 'rod')
        self.assertEqual(_sig(venter_laas=1)['samlet'], 'gul')

    def test_manglende_tall_er_rolig(self):
        self.assertEqual(db_signaler({})['samlet'], 'gronn')


class TrinnetLoftesTests(SimpleTestCase):

    ROD = {'signaler': {'samlet': 'rod'}}

    def test_rodt_kort_loefter_groent_og_gult_til_oransje(self):
        for p95 in (100, 400):
            with self.subTest(p95=p95):
                t = beredskap_med_databasen(beredskapsnivaa(p95, 0, 50), self.ROD)
                self.assertEqual((t['nivaa'], t['grunn'], t['tiltak']), ('oransje', 'database', DB_TILTAK))

    def test_rodt_trinn_blir_rodt_men_faar_databasens_tiltak(self):
        """Å øke workers for en lås gjør køen lengre."""
        t = beredskap_med_databasen(beredskapsnivaa(1500, 0, 50), self.ROD)
        self.assertEqual((t['nivaa'], t['tiltak']), ('rod', DB_TILTAK))

    def test_faa_maalinger_gjelder_ikke_en_laas(self):
        t = beredskap_med_databasen(beredskapsnivaa(100, 0, 3), self.ROD)
        self.assertFalse(t['fa_maalinger'])

    def test_gult_kort_og_sqlite_rorer_ingenting(self):
        foer = beredskapsnivaa(100, 0, 50)
        self.assertEqual(beredskap_med_databasen(foer, {'signaler': {'samlet': 'gul'}}), foer)
        self.assertEqual(beredskap_med_databasen(foer, {'vendor': 'sqlite'}), foer)
        self.assertEqual(beredskap_med_databasen(foer, None), foer)


class KallstedetTests(SimpleTestCase):
    """Payloaden går gjennom `beredskap_med_databasen` med *samme* databasesvar
    som kortet viser — ellers kunne banneret og kortet si hver sin ting."""

    def test_payloaden_loefter_trinnet(self):
        db = {'healthy': True, 'signaler': {'samlet': 'rod'}}
        rolig = {'healthy': True, 'signaler': {'samlet': 'gronn'}}
        with mock.patch.object(admin_status, '_get_db_health', side_effect=[db, rolig]) as hent:
            p = admin_status._build_status_payload()
        self.assertEqual((p['beredskap']['nivaa'], p['beredskap'].get('grunn')), ('oransje', 'database'))
        self.assertIs(p['db_health'], db, 'kortet og banneret leser samme svar')
        self.assertEqual(hent.call_count, 1)



def _vendor():
    from django.db import connection
    return connection.vendor


@unittest.skipUnless(_vendor() == 'sqlite', 'prøver SQLite-grenen; CI kjører PostgreSQL')
class SqliteTests(TestCase):
    """Lokalt: kortet viser «n/a», ikke en feil.

    **Bare på SQLite** (26. sep. 2026, D1). Testen gikk ut fra at suiten
    alltid kjørte på SQLite, og ble rød første gang den møtte PostgreSQL —
    der signalene finnes, som de skal. Søsteren under prøver den grenen.
    """

    def test_sqlite_har_ingen_signaler_og_ingen_feil(self):
        db = admin_status._get_db_health()
        self.assertTrue(db['healthy'])
        self.assertNotIn('signaler', db)
        self.assertNotIn('aktivitet_feil', db)


@unittest.skipUnless(_vendor() == 'postgresql', 'krever PostgreSQL — kjøres i CI')
class EktePostgresTests(TestCase):
    """Spørringene mot `pg_stat_activity` og `pg_stat_database`, **uten mock**.

    Testene under bytter ut aktiviteten; denne kjører den. Den fantes ikke før
    suiten kjørte mot PostgreSQL (D1), og en feil i SQL-en ville ellers først
    vist seg som «aktivitet_feil» på server-status i prod.
    """

    def test_signalene_regnes_og_ingenting_feiler(self):
        db = admin_status._get_db_health()
        self.assertTrue(db['healthy'])
        self.assertNotIn('aktivitet_feil', db)
        self.assertIn(db['signaler']['samlet'], ('gronn', 'oransje', 'rod'))
        self.assertGreaterEqual(db['tilkoblinger'], 1)


class PostgresgreinenTests(TestCase):
    """Grenen som bare kjører på PostgreSQL. Tilkoblingsspørringen feiler mot
    SQLite, og det er poenget: aktiviteten har sin egen `try`, og signalene
    regnes likevel."""

    def _helse(self, **aktivitet):
        from django.db import connection
        with mock.patch.object(connection, 'vendor', 'postgresql'), \
                mock.patch.object(admin_status, '_db_aktivitet', **aktivitet):
            return admin_status._get_db_health()

    def test_signalene_regnes_av_aktiviteten(self):
        db = self._helse(return_value={'henger': 3, 'eldste_s': 40, 'venter_laas': 0, 'deadlocks': 0})
        self.assertEqual(db['signaler']['samlet'], 'rod')
        self.assertEqual(db['henger'], 3)

    def test_feil_i_aktiviteten_tar_ikke_resten(self):
        db = self._helse(side_effect=RuntimeError('permission denied for pg_stat_activity'))
        self.assertTrue(db['healthy'])
        self.assertIn('permission denied', db['aktivitet_feil'])
        self.assertNotIn('signaler', db)
