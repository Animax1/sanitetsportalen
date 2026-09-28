"""«Avslutt vakt» arkiverer og tømmer alle modulene i ett (steg 2, 28. sep. 2026).

`core/vaktslutt.py`, prøvd gjennom det ekte endepunktet
`/pasienter/api/avslutt-vakt/`. Det som skal holde:

- Pasientene **arkiveres** før de slettes — hullet var at de bare ble slettet.
- Oppdragene arkiveres og tømmes med resten, og Bemanning er frosset med
  oppdragstallene fra *før* tømmingen (ellers 0 for en avsluttet vakt).
- Et oppdrag på tavla sperrer, og da er ingenting rørt — heller ingen backup.
- Feiler én modul midt i, er ingenting arkivert, slettet eller frosset.
- Ingen rader gir intet arkiv.
"""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog
from core.models import Backup, VaktStatistikk
from core.vakt import hent_aktiv_vakt
from oppdrag import services as oppdrag_services
from oppdrag.models import Enhet, Lokasjon, Oppdrag, OppdragArkiv
from patients.models import ArkivertPasient, Patient, VaktArkiv
from patients.test_helpers import sett_aktiv_vakt

URL = '/pasienter/api/avslutt-vakt/'


@override_settings(SECURE_SSL_REDIRECT=False)
class AvsluttVaktTests(TestCase):

    def setUp(self):
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)

        self.vakt = sett_aktiv_vakt(2026)
        self.admin = CustomUser.objects.create_superuser(
            username='a', password='x', role='admin', must_change_password=False)
        self.c = Client()
        self.c.force_login(self.admin)
        self.lokasjon = Lokasjon.objects.create(navn='Hovedscene')
        self.enhet = Enhet.objects.create(navn='Haugesund 56', pa_vakt=True)

    # ── Hjelpere ──────────────────────────────────────────────────────────
    def _pasienter(self, n):
        for nr in range(1, n + 1):
            Patient.objects.create(pasientnummer=nr, vakt=self.vakt, problemstilling='Svimmelhet')

    def _oppdrag(self, *, paa_tavla=False):
        oppdrag = Oppdrag.objects.create(
            vakt=self.vakt, oppdragsnummer=oppdrag_services.neste_oppdragsnummer(self.vakt),
            problemstilling='Pustevansker', hastegrad='Akutt', lokasjon=self.lokasjon,
            enhet=self.enhet)
        if not paa_tavla:
            Oppdrag.objects.filter(pk=oppdrag.pk).update(historikk_fra=timezone.now())
        return oppdrag

    def _avslutt(self, navn='Neste vakt'):
        return self.c.post(URL, data=json.dumps({'confirm': True, 'ny_vakt_navn': navn}),
                           content_type='application/json')

    # ── Det som skjer ─────────────────────────────────────────────────────
    def test_pasientene_arkiveres_for_de_slettes(self):
        self._pasienter(3)
        svar = self._avslutt()
        self.assertEqual(svar.status_code, 200, svar.content)
        self.assertFalse(Patient.objects.filter(vakt=self.vakt).exists())
        arkiv = VaktArkiv.objects.get(vakt=self.vakt)
        self.assertEqual((arkiv.antall_pasienter, arkiv.arrangement_navn), (3, self.vakt.navn))
        self.assertEqual(ArkivertPasient.objects.filter(arkiv=arkiv).count(), 3)
        self.assertTrue(arkiv.sha256)

    def test_oppdragene_arkiveres_og_tommes(self):
        self._oppdrag()
        self._oppdrag()
        self.assertEqual(self._avslutt().status_code, 200)
        self.assertFalse(Oppdrag.objects.filter(vakt=self.vakt).exists())
        self.assertEqual(OppdragArkiv.objects.get(vakt=self.vakt).antall_rader, 2)

    def test_bemanning_er_frosset_med_oppdragene_for_tommingen(self):
        """Fanen regner oppdragstallet fra oppdragstabellen — som er tom etterpå."""
        self._oppdrag()
        self._oppdrag()
        self._oppdrag()
        self.assertEqual(self._avslutt().status_code, 200)
        rad = VaktStatistikk.objects.get(vakt=self.vakt, slug='vaktliste')
        self.assertEqual(rad.data['summary']['antall_oppdrag'], 3)

    def test_vakta_lukkes_og_den_nye_er_aktiv(self):
        svar = self._avslutt('Vinterfestivalen').json()
        self.assertEqual(hent_aktiv_vakt().navn, 'Vinterfestivalen')
        self.vakt.refresh_from_db()
        self.assertFalse(self.vakt.er_aktiv)
        self.assertIn('Statistikken er frosset', svar['melding'])

    def test_meldingen_bruker_entall(self):
        self._pasienter(1)
        self.assertIn('1 pasient,', self._avslutt().json()['melding'])

    def test_ingen_rader_gir_intet_arkiv(self):
        self.assertEqual(self._avslutt().status_code, 200)
        self.assertFalse(VaktArkiv.objects.exists())
        self.assertFalse(OppdragArkiv.objects.exists())

    def test_arkiveringen_logges_med_hvem(self):
        self._pasienter(1)
        self._oppdrag()
        self._avslutt()
        for tabell in (VaktArkiv._meta.db_table, OppdragArkiv._meta.db_table):
            rad = AuditLog.objects.get(table_name=tabell, field_name='arkiv_lagret')
            self.assertEqual(rad.user, self.admin)
            self.assertIn('ved avslutning', rad.new_value)

    def test_backup_tas_av_hver_modul_som_tommes(self):
        self._pasienter(1)
        self._avslutt()
        self.assertEqual(
            set(Backup.objects.filter(kind='pre_reset').values_list('module_slug', flat=True)),
            {'patients', 'oppdrag'})

    # ── Det som stopper ───────────────────────────────────────────────────
    def test_oppdrag_paa_tavla_sperrer_og_ingenting_er_rort(self):
        self._pasienter(2)
        self._oppdrag(paa_tavla=True)
        svar = self._avslutt()
        self.assertEqual(svar.status_code, 409)
        self.assertIn('står fortsatt på tavla', svar.json()['error'])
        self.assertEqual(Patient.objects.filter(vakt=self.vakt).count(), 2)
        self.assertEqual(Oppdrag.objects.filter(vakt=self.vakt).count(), 1)
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)
        self.assertFalse(VaktArkiv.objects.exists())
        self.assertFalse(VaktStatistikk.objects.exists())
        self.assertFalse(Backup.objects.filter(kind='pre_reset').exists())

    def test_sperren_sjekkes_igjen_etter_backupen(self):
        """Et oppdrag lagt på tavla mens backupene ble tatt, stopper fortsatt."""
        self._pasienter(1)
        from core.backup import create_backup as ekte

        def backup_og_nytt_oppdrag(**kw):
            if kw.get('slug') == 'oppdrag':
                self._oppdrag(paa_tavla=True)
            return ekte(**kw)
        with mock.patch('core.backup.create_backup', side_effect=backup_og_nytt_oppdrag):
            self.assertEqual(self._avslutt().status_code, 409)
        self.assertEqual(Patient.objects.filter(vakt=self.vakt).count(), 1)
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)
        self.assertFalse(VaktStatistikk.objects.exists())

    def test_en_modul_som_feiler_ruller_tilbake_alt(self):
        """Oppdrag feiler etter at pasientene er arkivert og slettet i transaksjonen."""
        self._pasienter(2)
        self._oppdrag()
        with mock.patch('oppdrag.arkiv.arkiver_vakt', side_effect=RuntimeError('midt i')):
            with self.assertRaises(RuntimeError):
                self._avslutt()
        self.assertEqual(Patient.objects.filter(vakt=self.vakt).count(), 2)
        self.assertEqual(Oppdrag.objects.filter(vakt=self.vakt).count(), 1)
        self.assertFalse(VaktArkiv.objects.exists())
        self.assertFalse(VaktStatistikk.objects.exists())
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)

    # ── Oversikten ────────────────────────────────────────────────────────
    def test_oversikten_viser_antall_faner_og_sperrer(self):
        self._pasienter(2)
        self._oppdrag(paa_tavla=True)
        data = self.c.get(URL).json()
        antall = {m['slug']: m['antall'] for m in data['moduler']}
        self.assertEqual(antall, {'patients': 2, 'oppdrag': 1})
        self.assertEqual(len(data['sperrer']), 1)
        self.assertIn('Lag', data['fryses'])
        self.assertEqual(data['vakt'], self.vakt.navn)

    def test_bare_global_admin(self):
        leder = CustomUser.objects.create_user(
            username='l', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(leder, 'leder')
        c = Client()
        c.force_login(leder)
        self.assertEqual(c.get(URL).status_code, 403)
        self.assertEqual(c.post(URL, data=json.dumps({'confirm': True, 'ny_vakt_navn': 'X'}),
                                content_type='application/json').status_code, 403)
