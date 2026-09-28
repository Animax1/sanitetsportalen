"""Statistikken for en avsluttet vakt fryses før radene går (steg 1, 28. sep. 2026).

`core/vaktstatistikk.py`. Tre egenskaper er hele poenget, og hver har en test:

1. **Tallene er de radene ga før de ble tømt** — prøvd gjennom det ekte
   «Avslutt vakt»-endepunktet, ikke ved å kalle `frys()` for seg: regelen er at
   frysingen skjer *før* slettingen, og det er kallstedet som bærer den.
2. **Alt eller ingenting** — feiler én fane, slettes ingenting og vakta står.
3. **Legges til, skrives aldri over** — en gjenåpnet vakt som avsluttes igjen
   får et sett til, og det første står urørt.
"""
from __future__ import annotations

import os
import tempfile
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from core.models import VaktStatistikk
from core.stats import BaseStatistikkHandler, all_handlers
from core.vakt import hent_aktiv_vakt
from core.vaktstatistikk import frys
from patients.models import Patient
from patients.test_helpers import sett_aktiv_vakt


class _Teller(BaseStatistikkHandler):
    slug = 'teller'
    statistikk_versjon = 3

    def full_stats(self, vakt):
        return {'vakt': vakt.navn, 'pasienter': Patient.objects.filter(vakt=vakt).count()}


class _Feiler(BaseStatistikkHandler):
    slug = 'feiler'

    def full_stats(self, vakt):
        raise RuntimeError('treg spørring')


class FrysTests(TestCase):

    def setUp(self):
        self.vakt = sett_aktiv_vakt(2026)
        self.admin = CustomUser.objects.create_user(
            username='a', password='x', role='admin', must_change_password=False)

    def test_en_rad_per_fane_med_samme_tidspunkt(self):
        Patient.objects.create(pasientnummer=1, vakt=self.vakt)
        with mock.patch('core.vaktstatistikk.all_handlers', return_value=[_Teller()]):
            rader = frys(self.vakt, bruker=self.admin)
        self.assertEqual(len(rader), 1)
        rad = VaktStatistikk.objects.get()
        self.assertEqual(rad.data, {'vakt': self.vakt.navn, 'pasienter': 1})
        self.assertEqual((rad.slug, rad.versjon, rad.vakt_navn, rad.frosset_av_navn),
                         ('teller', 3, self.vakt.navn, 'a'))

    def test_hver_registrerte_fane_fryses(self):
        """Ingen liste å huske: en ny statistikkhandler fryses fra dag én."""
        frys(self.vakt, bruker=self.admin)
        self.assertEqual(
            sorted(VaktStatistikk.objects.values_list('slug', flat=True)),
            sorted(h.slug for h in all_handlers()))
        self.assertEqual(
            VaktStatistikk.objects.values('frosset_at').distinct().count(), 1)

    def test_en_feilende_fane_lagrer_ingenting(self):
        with mock.patch('core.vaktstatistikk.all_handlers',
                        return_value=[_Teller(), _Feiler()]):
            with self.assertRaises(RuntimeError):
                frys(self.vakt, bruker=self.admin)
        self.assertFalse(VaktStatistikk.objects.exists())

    def test_ny_frysing_skriver_ikke_over(self):
        with mock.patch('core.vaktstatistikk.all_handlers', return_value=[_Teller()]):
            Patient.objects.create(pasientnummer=1, vakt=self.vakt)
            frys(self.vakt, bruker=self.admin)
            Patient.objects.filter(vakt=self.vakt).delete()
            frys(self.vakt, bruker=self.admin)
        forste, andre = VaktStatistikk.objects.order_by('frosset_at')
        self.assertEqual(forste.data['pasienter'], 1)
        self.assertEqual(andre.data['pasienter'], 0)


@override_settings(SECURE_SSL_REDIRECT=False)
class AvsluttVaktFryserTests(TestCase):
    """Gjennom den ekte inngangen — kallstedet er regelen."""

    def setUp(self):
        # Frekvensgrensen på avslutningen teller per bruker-ID på tvers av testene.
        cache.clear()
        # Avslutningen tar en pre_reset-backup; den skal ikke havne i den ekte mappa.
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)
        self.vakt = sett_aktiv_vakt(2026)
        self.admin = CustomUser.objects.create_superuser(
            username='a', password='x', role='admin', must_change_password=False)
        for nr in (1, 2, 3):
            Patient.objects.create(pasientnummer=nr, vakt=self.vakt)
        self.c = Client()
        self.c.force_login(self.admin)

    def _avslutt(self, navn='Neste vakt'):
        return self.c.post('/portal-admin/vakt/avslutt/',
                           {'bekreft': 'ja', 'ny_vakt_navn': navn})

    def test_tallene_er_fra_for_slettingen(self):
        self.assertEqual(self._avslutt().status_code, 302)
        self.assertFalse(Patient.objects.filter(vakt=self.vakt).exists())
        rad = VaktStatistikk.objects.get(vakt=self.vakt, slug='patients')
        self.assertEqual(rad.data['summary']['total'], 3)
        self.assertEqual(rad.frosset_av_navn, 'a')
        # Den nye vakta har ingenting frosset — den er ikke avsluttet.
        self.assertFalse(VaktStatistikk.objects.filter(vakt=hent_aktiv_vakt()).exists())

    def test_feilet_frysing_sletter_ingenting(self):
        with mock.patch('core.vaktstatistikk.all_handlers', return_value=[_Feiler()]):
            with self.assertRaises(RuntimeError):
                self._avslutt()
        self.assertEqual(Patient.objects.filter(vakt=self.vakt).count(), 3)
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)
        self.assertFalse(VaktStatistikk.objects.exists())

    def test_avvist_avslutning_fryser_ingenting(self):
        """Navnet tatt midt i avslutningen: transaksjonen rulles tilbake, og
        frysingen med den — ellers sto tallene for en vakt som fortsatt er aktiv."""
        from core.vakt import VaktnavnOpptatt
        with mock.patch('core.vakt.opprett_vakt',
                        side_effect=VaktnavnOpptatt('Neste vakt')):
            self._avslutt()
        self.assertEqual(hent_aktiv_vakt().pk, self.vakt.pk)
        self.assertFalse(VaktStatistikk.objects.exists())
        self.assertEqual(Patient.objects.filter(vakt=self.vakt).count(), 3)
