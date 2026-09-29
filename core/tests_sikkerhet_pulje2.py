"""Sikkerhetsgjennomgangen 28. sep. 2026, pulje 2: rammeverksdelen.

Pulje 2 er det som må være på plass før `staging` går til `main` — all koden
er ny der. Modulenes del (hva som ikke fryses) prøves i modulenes egne
testfiler; her står porten i `core`:

- **Frysingen går gjennom `frys_stats()`**, ikke `full_stats()`. Det er
  kallstedet som bærer regelen om at fritekst ikke fryses.
- **Pekeren til aktiv vakt låses** før den byttes, og en vakt som ikke er den
  aktive lenger, kan ikke avsluttes.
- **«Tidligere vakter» viser alle utenom den aktive** — ikke alle med
  `er_aktiv=False`, som lot en vakt med feil flagg forsvinne.
- **`json_body` avviser tall som ikke er endelige** — `Infinity`, `NaN` og
  `1e999` ga 500 fra `/lag/r/` uten innlogging.

Se `docs/SIKKERHETSGJENNOMGANG_2026-09-28.md`.
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from core import vaktslutt
from core.jsonkropp import json_body
from core.models import Vakt, VaktStatistikk
from core.stats import BaseStatistikkHandler
from core.vakt import hent_aktiv_vakt
from core.vaktstatistikk import frys
from patients.test_helpers import sett_aktiv_vakt


class _MedFritekst(BaseStatistikkHandler):
    slug = 'fritekst'

    def full_stats(self, vakt):
        return {'antall': 2, 'tekster': ['Hjem til Storgata 5']}

    def frys_stats(self, vakt):
        data = self.full_stats(vakt)
        data['tekster'] = []
        return data


class FrysingenGaarGjennomFrysStatsTests(TestCase):

    def test_frys_bruker_frys_stats(self):
        vakt = sett_aktiv_vakt(2026)
        with mock.patch('core.vaktstatistikk.all_handlers', return_value=[_MedFritekst()]):
            frys(vakt)
        self.assertEqual(VaktStatistikk.objects.get().data, {'antall': 2, 'tekster': []})

    def test_standarden_er_full_stats(self):
        """En modul uten fritekst skal ikke måtte skrive noe for å bli frosset."""
        class _Bare(BaseStatistikkHandler):
            slug = 'bare'

            def full_stats(self, vakt):
                return {'antall': 1}

        self.assertEqual(_Bare().frys_stats(None), {'antall': 1})


@override_settings(SECURE_SSL_REDIRECT=False)
class AktivVaktLaasesTests(TestCase):

    def setUp(self):
        cache.clear()
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)
        self.vakt = sett_aktiv_vakt(2026)
        self.admin = CustomUser.objects.create_user(
            username='a', password='x', role='admin', must_change_password=False)
        self.c = Client()
        self.c.force_login(self.admin)

    def _vakt(self, navn, **kw):
        kw.setdefault('er_aktiv', False)
        kw.setdefault('avsluttet', timezone.now())
        return Vakt.objects.create(navn=navn, year=2026, startet=timezone.now(), **kw)

    def test_gjenaapning_rydder_alle_andre_aktive(self):
        """To samtidige gjenåpninger kunne gi to vakter med `er_aktiv=True`."""
        vill = self._vakt('Vill', er_aktiv=True, avsluttet=None)
        gammel = self._vakt('Gammel')
        self.c.post(f'/portal-admin/vakt/{gammel.pk}/gjenaapne/')
        self.assertEqual(hent_aktiv_vakt().pk, gammel.pk)
        self.assertEqual(list(Vakt.objects.filter(er_aktiv=True)), [gammel])
        vill.refresh_from_db()
        self.assertIsNotNone(vill.avsluttet)

    def test_tidligere_vakter_viser_ogsaa_en_med_feil_flagg(self):
        """Taperen av et kappløp skal ikke forsvinne fra lista."""
        vill = self._vakt('Vill', er_aktiv=True, avsluttet=None)
        svar = self.c.get('/portal-admin/vakt/')
        self.assertIn(vill.pk, [t['vakt'].pk for t in svar.context['tidligere']])
        self.assertNotIn(self.vakt.pk, [t['vakt'].pk for t in svar.context['tidligere']])

    def test_en_vakt_som_ikke_er_aktiv_kan_ikke_avsluttes(self):
        """Den andre av to samtidige avslutninger har en vakt som alt er avsluttet."""
        gammel = self._vakt('Gammel')
        with self.assertRaises(vaktslutt.Sperret):
            vaktslutt.avslutt(gammel, ny_vakt_navn='Ny', bruker=self.admin)
        self.assertFalse(VaktStatistikk.objects.exists(), 'frosset på nytt med tomme tall')
        from core.models import Backup
        self.assertFalse(Backup.objects.exists(), 'en avsluttet vakt skal ikke koste backuper')
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)
        self.assertFalse(Vakt.objects.filter(navn='Ny').exists())

    def test_laasen_tar_den_som_ble_avsluttet_mens_backupene_gikk(self):
        """Den tidlige sjekken er et kappløp: backupene tar tid, og den andre
        avslutningen kan ha kommet først. Da er det låsen i transaksjonen som holder."""
        from core.vakt import opprett_vakt
        from core.models import AppSetting

        def annen_avslutning_imens(*args, **kwargs):
            if not Vakt.objects.filter(navn='Kom først').exists():
                ny = opprett_vakt('Kom først', year=2026, startet=timezone.now())
                AppSetting.set('aktiv_vakt_id', ny.pk)

        with mock.patch('core.backup.create_backup', side_effect=annen_avslutning_imens):
            with self.assertRaises(vaktslutt.Sperret):
                vaktslutt.avslutt(self.vakt, ny_vakt_navn='Ny', bruker=self.admin)
        self.assertFalse(VaktStatistikk.objects.exists())
        self.assertFalse(Vakt.objects.filter(navn='Ny').exists())

    def test_den_aktive_kan_fortsatt_avsluttes(self):
        """Motprøven."""
        vaktslutt.avslutt(self.vakt, ny_vakt_navn='Ny', bruker=self.admin)
        self.assertEqual(hent_aktiv_vakt().navn, 'Ny')


class JsonBodyTests(TestCase):

    def _body(self, raa):
        return json_body(RequestFactory().post('/', data=raa, content_type='application/json'))

    def test_tall_som_ikke_er_endelige_avvises(self):
        for raa in ('{"lag": Infinity}', '{"lag": -Infinity}', '{"lag": NaN}',
                    '{"lag": 1e999}', '{"lag": -1e999}'):
            with self.subTest(raa=raa):
                self.assertEqual(self._body(raa), {})

    def test_vanlige_tall_og_tekst_slipper_gjennom(self):
        self.assertEqual(self._body('{"lag": 3, "x": 1.5, "t": "Infinity"}'),
                         {'lag': 3, 'x': 1.5, 't': 'Infinity'})

    def test_uendelig_dypt_inne_avvises_ogsaa(self):
        self.assertEqual(self._body(json.dumps({'a': [1, {'b': 2}]}).replace('2', '1e400')), {})


class FrosneRaderVaskesTests(TestCase):
    """Datamigrasjonene tar settene staging frøs før `frys_stats` fantes."""

    def _kjor(self, modul):
        import importlib

        from django.apps import apps
        importlib.import_module(modul).vask(apps, None)

    def _rad(self, slug, data):
        return VaktStatistikk.objects.create(vakt=None, vakt_navn='Gammel', slug=slug,
                                             data=data, frosset_at=timezone.now())

    def test_oppdrag(self):
        rad = self._rad('oppdrag', {'avreist_til': {
            'per_sted': {'Annet sted': 1},
            'annet_tekster': [{'oppdragsnummer': 1, 'enhet': 'A1', 'tekst': 'Storgata 5'}]}})
        annen = self._rad('ko', {'avreist_til': {'annet_tekster': ['står']}})
        self._kjor('oppdrag.migrations.0034_frosset_statistikk_uten_fritekst')
        rad.refresh_from_db()
        annen.refresh_from_db()
        self.assertEqual(rad.data, {'avreist_til': {'per_sted': {'Annet sted': 1},
                                                    'annet_tekster': []}})
        self.assertEqual(annen.data['avreist_til']['annet_tekster'], ['står'], 'bare sin egen slug')

    def test_ko(self):
        rad = self._rad('ko', {'hvem_loste': {'verken_liste': [
            {'hendelsesnummer': 3, 'tittel': 'Savnet Ola', 'siste_linje': 'Funnet',
             'lukket_av': 'ko1', 'minutter': 17.0}]}})
        self._kjor('ko.migrations.0024_frosset_statistikk_uten_fritekst')
        rad.refresh_from_db()
        self.assertEqual(rad.data['hvem_loste']['verken_liste'], [
            {'hendelsesnummer': 3, 'tittel': '', 'siste_linje': '', 'lukket_av': '',
             'minutter': 17.0}])

    def test_rader_uten_formen_toles(self):
        """Eldre eller rare sett skal ikke stoppe release-fasen."""
        for data in ({}, {'avreist_til': None}, {'hvem_loste': {'verken_liste': None}}, None):
            self._rad('oppdrag', data if data is not None else {})
            self._rad('ko', data if data is not None else {})
        self._kjor('oppdrag.migrations.0034_frosset_statistikk_uten_fritekst')
        self._kjor('ko.migrations.0024_frosset_statistikk_uten_fritekst')
