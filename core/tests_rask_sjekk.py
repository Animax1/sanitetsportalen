"""`manage.py rask_sjekk` — valget av tester ut fra endrede filer (19. okt. 2026).

Faren ved en rask kjøring er at den hopper over det den burde ha tatt, og
melder grønt. Testene her krever derfor mest av den konservative siden: at
alt uten et entydig hjem gir hele suiten, og at en fil som lastes av to
moduler gir begge.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.management.commands.rask_sjekk import testkommando
from core.rask_sjekk import TREG, apper_med_tester, dokumenttestene, velg

ROT = Path(settings.BASE_DIR)


class UtvalgetTests(SimpleTestCase):

    def test_en_fil_i_en_app_gir_appen(self):
        self.assertEqual(velg(['ko/views.py'], ROT).etiketter, ['ko'])

    def test_hver_app_med_tester_kan_velges_alene(self):
        """Ellers ville en endring i en ny app gitt hele suiten for alltid —
        eller, verre, ingenting."""
        for app in sorted(apper_med_tester(ROT) - {'core'}):
            with self.subTest(app=app):
                self.assertEqual(velg([f'{app}/x.py'], ROT).etiketter, [app])

    def test_core_gir_hele_suiten(self):
        self.assertIsNone(velg(['ko/views.py', 'core/modules.py'], ROT).etiketter)

    def test_ukjent_hjem_gir_hele_suiten(self):
        for fil in ('requirements.txt', '.github/workflows/tester.yml',
                    'static/img/logo.svg', 'templates/partials/_ikoner.html'):
            with self.subTest(fil=fil):
                self.assertIsNone(velg([fil], ROT).etiketter)

    def test_en_mal_i_en_app_gir_appen(self):
        self.assertEqual(velg(['templates/vaktliste/index.html'], ROT).etiketter, ['vaktliste'])

    def test_statisk_fil_gir_appene_som_laster_den(self):
        """`oppdrag-kort.js` lastes av både sentralbordet og `/ko/` — se rota
        i CLAUDE.md. Valget skal finne begge av seg selv."""
        etiketter = velg(['static/js/oppdrag-kort.js'], ROT).etiketter
        self.assertIn('oppdrag', etiketter)
        self.assertIn('ko', etiketter)
        self.assertEqual(velg(['static/js/vaktliste-kjerne.js'], ROT).etiketter, ['vaktliste'])

    def test_statisk_fil_i_en_delt_mal_gir_hele_suiten(self):
        self.assertIsNone(velg(['static/js/portal-utils.js'], ROT).etiketter)

    def test_statisk_fil_ingen_mal_laster_gir_hele_suiten(self):
        """En ny fil som ennå ikke er koblet inn — eller en som lastes fra JS.
        Tomt utvalg ville vært en grønn kjøring av ingenting."""
        self.assertIsNone(velg(['static/js/finnes-ikke-ennaa.js'], ROT).etiketter)

    def test_markdown_gir_dokumenttestene(self):
        self.assertEqual(velg(['TODO.md', 'ko/CLAUDE.md'], ROT).etiketter, dokumenttestene(ROT))

    def test_dokumenttestene_finnes(self):
        """Finner regexen ingenting, gir en .md-endring en tom kjøring som er grønn."""
        self.assertIn('core.tests_todo', dokumenttestene(ROT))


class KommandoenTests(SimpleTestCase):

    def test_beholder_basen_og_hopper_over_de_trege(self):
        kommando = testkommando(['ko'], med_treg=False, parallel='auto')
        self.assertEqual(kommando[1:4], ['manage.py', 'test', 'ko'])
        self.assertIn('--keepdb', kommando)
        self.assertEqual(kommando[kommando.index('--exclude-tag') + 1], TREG)

    def test_med_treg_tar_dem_med(self):
        self.assertNotIn('--exclude-tag', testkommando(['ko'], med_treg=True, parallel='2'))


class DeTregeErMerketTests(SimpleTestCase):
    """Uten merket er den raske kjøringen ikke rask. De tre er de tregeste klassene
    i målingen 19. okt. 2026; en ny treg test merkes på samme måte."""

    def test_de_tregeste_klassene_er_merket(self):
        from core.tests_inline_stiler import EkteSvarTests
        from core.tests_verifiser_backup import VerifiserBackupTests
        from oppdrag.tests_runde_e import SeedMigrasjonTests
        for klasse in (VerifiserBackupTests, SeedMigrasjonTests, EkteSvarTests):
            with self.subTest(klasse=klasse.__name__):
                self.assertIn(TREG, getattr(klasse, 'tags', set()))
