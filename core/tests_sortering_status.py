"""Server-status viser hvordan basen sorterer Æ, Ø og Å (26. sep. 2026).

CI viste at «ålesund» sorteres først i en_US og sist i C, og ingen kunne se hva
prod gjør uten SQL-tilgang. Kortet viser **svaret, ikke innstillingen**: på en
ICU-base sier `datcollate` «C.UTF-8» mens sorteringen er en_US (prøvd lokalt mot
begge). `sortering_vurdering()` er regelen; kortet tegner den.
"""
import unittest
from unittest import mock

from django.db import connection
from django.test import SimpleTestCase, TestCase

from accounts.test_helpers import gi_standardtilgang
from core import admin_status
from core.admin_status import (SORTERING_KODEPUNKT, SORTERING_NORSK, SORTERINGSPROVE,
                               sortering_vurdering)

#: Det en_US-basen i CI og lokalt svarte.
EN_US = ('Ærø', 'Ålesund', 'bergen', 'Ørsta', 'Oslo', 'Zeta')


class VurderingenTests(SimpleTestCase):

    def test_de_tre_svarene(self):
        self.assertEqual(sortering_vurdering(SORTERING_NORSK), 'norsk')
        self.assertEqual(sortering_vurdering(SORTERING_KODEPUNKT), 'kodepunkt')
        self.assertEqual(sortering_vurdering(EN_US), 'blandet')

    def test_bare_eksakt_norsk_er_norsk(self):
        """Å og Ø byttet — sist, men feil — skal ikke gå for norsk."""
        nesten = SORTERING_NORSK[:4] + (SORTERING_NORSK[5], SORTERING_NORSK[4])
        self.assertEqual(sortering_vurdering(nesten), 'blandet')
        self.assertEqual(sortering_vurdering(list(SORTERING_NORSK)), 'norsk', 'en liste fra basen')

    def test_fasitene_er_prøven_sortert(self):
        """En skrivefeil i en fasit ville gitt «blandet» for alltid."""
        for fasit in (SORTERING_NORSK, SORTERING_KODEPUNKT, EN_US):
            self.assertEqual(sorted(fasit), sorted(SORTERINGSPROVE))
        self.assertEqual(tuple(sorted(SORTERINGSPROVE, key=str.lower)), SORTERING_KODEPUNKT)


class ProvenKjorerMotBasenTests(TestCase):

    def test_svaret_står_i_databasekortet(self):
        s = admin_status._get_db_health()['sortering']
        self.assertEqual(sorted(s['rekkefolge']), sorted(SORTERINGSPROVE))
        self.assertEqual(s['vurdering'], sortering_vurdering(s['rekkefolge']))

    @unittest.skipUnless(connection.vendor == 'sqlite', 'SQLites lower() er bare ASCII')
    def test_sqlite_sorterer_paa_kodepunkt(self):
        self.assertEqual(admin_status._get_db_health()['sortering']['vurdering'], 'kodepunkt')

    @unittest.skipUnless(connection.vendor == 'postgresql', 'krever PostgreSQL — kjøres i CI')
    def test_postgresql_oppgir_kollasjon_og_versjon(self):
        s = admin_status._get_db_health()['sortering']
        self.assertTrue(s['kollasjon'])
        self.assertTrue(s['versjon'])

    def test_en_feil_i_proven_tar_ikke_kortet(self):
        with mock.patch.object(admin_status, '_db_sortering', side_effect=RuntimeError('borte')):
            db = admin_status._get_db_health()
        self.assertTrue(db['healthy'])
        self.assertEqual(db['sortering'], {'feil': 'borte'})

    def test_svaret_går_ut_til_siden(self):
        from accounts.models import CustomUser
        admin = CustomUser.objects.create_user(username='sort_admin', password='x', role='admin',
                                               must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        self.client.force_login(admin)
        res = self.client.get('/portal-admin/server-status/json/', secure=True)
        self.assertEqual(res.status_code, 200, res.content[:200])
        self.assertIn(res.json()['db_health']['sortering']['vurdering'],
                      {'norsk', 'kodepunkt', 'blandet'})
