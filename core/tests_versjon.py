"""Bygg og dato i footeren (11. sep. 2026).

André: «kan vi nederst i footer ha versjonsnummer som er bygg og dato?» Det
er spørsmålet man stiller når noe ser annerledes ut enn i går — er dette den
nye koden, eller cachen?
"""
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from django.test import Client, SimpleTestCase, TestCase

from core import skriv_bygg, versjon


class FinnVersjonTests(SimpleTestCase):
    """Tre kilder i rekkefølge, og den første som svarer vinner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rot = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_byggfila_vinner(self):
        (self.rot / 'bygg.json').write_text(json.dumps(
            {'bygg': 'abc1234def', 'dato': '2026-09-11T10:15:00+00:00'}))
        v = versjon.finn_versjon(self.rot)
        self.assertEqual(v['bygg'], 'abc1234', 'SHA kortes til sju tegn')
        self.assertEqual(v['dato'], datetime(2026, 9, 11, 10, 15, tzinfo=timezone.utc))
        self.assertEqual(v['kilde'], 'bygg.json')

    def test_byggfila_uten_sha_gir_ukjent_bygg_men_datoen(self):
        """Lokalt kjørt `skriv_bygg` har ingen SHA — datoen er likevel verdt
        noe, og «ukjent» er bedre enn en tom footer."""
        (self.rot / 'bygg.json').write_text(json.dumps(
            {'bygg': '', 'dato': '2026-09-11T10:15:00+00:00'}))
        v = versjon.finn_versjon(self.rot)
        self.assertEqual(v['bygg'], versjon.UKJENT)
        self.assertIsNotNone(v['dato'])

    def test_odelagt_byggfil_hoppes_over(self):
        (self.rot / 'bygg.json').write_text('{ikke json')
        with mock.patch.dict(os.environ, {'RAILWAY_GIT_COMMIT_SHA': 'feedbeefcafe'}):
            (self.rot / 'manage.py').write_text('')
            v = versjon.finn_versjon(self.rot)
        self.assertEqual(v['kilde'], 'miljø')
        self.assertEqual(v['bygg'], 'feedbee')

    def test_git_svarer_naar_arbeidskatalogen_har_historikk(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.rot, check=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t',
                        'commit', '-q', '--allow-empty', '-m', 'x',
                        '--date', '2026-09-11T12:00:00+02:00'],
                       cwd=self.rot, check=True,
                       env={**os.environ, 'GIT_COMMITTER_DATE': '2026-09-11T12:00:00+02:00'})
        v = versjon.finn_versjon(self.rot)
        self.assertEqual(v['kilde'], 'git')
        self.assertEqual(len(v['bygg']), 7)
        self.assertEqual(v['dato'].astimezone(timezone.utc).hour, 10)

    def test_miljoet_alene_gir_sha_og_filas_tid(self):
        """Byggsteget kjørte ikke, og containeren har ingen .git — men
        Railway satte variabelen. Datoen er da utsjekkstidspunktet."""
        (self.rot / 'manage.py').write_text('')
        with mock.patch.dict(os.environ, {'RAILWAY_GIT_COMMIT_SHA': '0123456789'}):
            v = versjon.finn_versjon(self.rot)
        self.assertEqual(v['bygg'], '0123456')
        self.assertIsNotNone(v['dato'])
        self.assertEqual(v['kilde'], 'miljø')

    def test_ingen_kilde_gir_ukjent_ikke_tomt(self):
        with mock.patch.dict(os.environ, {'RAILWAY_GIT_COMMIT_SHA': ''}):
            v = versjon.finn_versjon(self.rot)
        self.assertEqual(v['bygg'], versjon.UKJENT)
        self.assertIsNone(v['dato'])


class SkrivByggTests(SimpleTestCase):
    """Byggsteget: stdlib, to felter, og en fil `core.versjon` kan lese."""

    def test_skriver_det_versjon_leser(self):
        with tempfile.TemporaryDirectory() as tmp:
            rot = Path(tmp)
            naa = datetime(2026, 9, 11, 10, 15, 30, tzinfo=timezone.utc)
            skriv_bygg.skriv(rot / 'bygg.json', 'a03b5e5ffff', naa)
            v = versjon.finn_versjon(rot)
        self.assertEqual(v['bygg'], 'a03b5e5')
        self.assertEqual(v['dato'], naa)

    def test_skriptet_bruker_bare_standardbiblioteket(self):
        """Kjører før Django er satt opp i bygget — et `import django` her
        ville gjort footeren til en grunn til at deployen feiler."""
        import re
        kilde = Path(skriv_bygg.__file__).read_text(encoding='utf-8')
        # Importene, ikke teksten: docstringen forklarer nettopp hvorfor
        # Django *ikke* er med, og et ordsøk ville lest sin egen begrunnelse.
        importer = re.findall(r'(?m)^\s*(?:import|from)\s+([\w.]+)', kilde)
        self.assertTrue(importer, 'fant ingen importer')
        self.assertFalse([i for i in importer if i.split('.')[0] == 'django'],
                         importer)

    def test_nixpacks_kaller_skriptet(self):
        from django.conf import settings
        toml = (Path(settings.BASE_DIR) / 'nixpacks.toml').read_text(encoding='utf-8')
        self.assertIn('python core/skriv_bygg.py', toml)

    def test_byggfila_er_ikke_i_git(self):
        from django.conf import settings
        ignore = (Path(settings.BASE_DIR) / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('bygg.json', ignore.splitlines())


class FooterTests(TestCase):
    """Tallet står nederst på hver portalside."""

    def setUp(self):
        from accounts.models import CustomUser
        from core.versjon import hent_versjon
        hent_versjon.cache_clear()
        self.addCleanup(hent_versjon.cache_clear)
        self.c = Client()
        self.c.force_login(CustomUser.objects.create_user(
            username='adm', password='x', role='admin', must_change_password=False))

    def test_footeren_viser_bygg_og_dato(self):
        naa = datetime(2026, 9, 11, 10, 15, tzinfo=timezone.utc)
        with mock.patch('core.versjon.finn_versjon',
                        return_value={'bygg': 'a03b5e5', 'dato': naa, 'kilde': 'test'}):
            res = self.c.get('/vaktliste/')
        self.assertContains(res, 'portal-versjon')
        self.assertContains(res, 'a03b5e5')
        self.assertContains(res, '11.09.2026')

    def test_uten_dato_staar_bygget_alene(self):
        with mock.patch('core.versjon.finn_versjon',
                        return_value={'bygg': 'ukjent', 'dato': None, 'kilde': 'ingen'}):
            res = self.c.get('/vaktliste/')
        self.assertContains(res, 'ukjent')
