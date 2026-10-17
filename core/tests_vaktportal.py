"""Portalene og aktiv vakt per portal (17. okt. 2026, `docs/BESLUTNING_PORTALER.md`).

Det som avgjør om en rad havner i riktig portal, står her. Tre regler:

1. **`gjeldende_portal()` gjetter aldri.** Med to aktive portaler og ingen
   kontekst kaster den — kodeveien som manglet konteksten stopper, i stedet for
   å skrive i feil portal. Den viktigste testen i fila er
   `test_to_portaler_uten_kontekst_stopper`.
2. **Databasen sier én aktiv vakt per portal**, ikke koden.
3. **Å bytte aktiv vakt rører bare sin egen portal.**
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser
from core import vaktslutt
from core.models import Vakt, Vaktportal
from core.portal import (
    STANDARD_SLUG, UklarPortal, aktiv_kontekst, aktiver_portal, eneste_portal,
    gjeldende_portal,
)
from core.vakt import gjor_aktiv, hent_aktiv_vakt, laas_aktiv_vakt, opprett_vakt


def _vakt(navn, portal, **kw):
    return Vakt.objects.create(navn=navn, year=2026, startet=timezone.now(),
                               portal=portal, **kw)


class GjeldendePortalTests(TestCase):

    def test_migrasjonen_lager_standard(self):
        """Testbasen kjører migrasjonene, og 0018 lager «Standard»."""
        self.assertEqual(eneste_portal().slug, STANDARD_SLUG)

    def test_en_aktiv_portal_er_svaret(self):
        standard = eneste_portal()
        Vaktportal.objects.create(navn='Gammel', slug='gammel', er_aktiv=False)
        self.assertEqual(gjeldende_portal(), standard)

    def test_to_portaler_uten_kontekst_stopper(self):
        """Den viktigste: ingen gjetning når svaret ikke er entydig."""
        Vaktportal.objects.create(navn='Brann', slug='brann')
        with self.assertRaises(UklarPortal):
            gjeldende_portal()
        with self.assertRaises(UklarPortal):
            hent_aktiv_vakt()

    def test_ingen_aktive_portaler_stopper(self):
        Vaktportal.objects.update(er_aktiv=False)
        with self.assertRaises(UklarPortal):
            gjeldende_portal()

    def test_tom_tabell_lager_standard(self):
        """En fersk installasjon — eller en `TransactionTestCase` som har tømt tabellen.

        Modulenes portaleide rader (hjelperne fra migrasjonen) peker på portalen
        med `PROTECT`, så de må ut først. Lest av modellene, ikke navngitt: en
        test i `core` skal ikke kjenne modulene."""
        from django.apps import apps
        for modell in apps.get_models():
            for felt in modell._meta.fields:
                if felt.is_relation and felt.related_model is Vaktportal:
                    modell._base_manager.filter(**{f'{felt.name}__isnull': False}).delete()
        Vaktportal.objects.all().delete()
        self.assertEqual(gjeldende_portal().slug, STANDARD_SLUG)
        self.assertEqual(Vaktportal.objects.count(), 1)

    def test_konteksten_vinner_og_nullstilles(self):
        standard = eneste_portal()
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.assertIsNone(aktiv_kontekst())
        with aktiver_portal(brann):
            self.assertEqual(gjeldende_portal(), brann)
            with aktiver_portal(standard):
                self.assertEqual(gjeldende_portal(), standard)
            self.assertEqual(gjeldende_portal(), brann)
        self.assertIsNone(aktiv_kontekst())

    def test_konteksten_nullstilles_ogsaa_ved_unntak(self):
        brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        with self.assertRaises(RuntimeError), aktiver_portal(brann):
            raise RuntimeError('midt i')
        self.assertIsNone(aktiv_kontekst())


class EnAktivVaktPerPortalTests(TestCase):

    def setUp(self):
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')

    def test_basen_avviser_to_aktive_i_samme_portal(self):
        _vakt('A', self.brann, er_aktiv=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            _vakt('B', self.brann, er_aktiv=True)

    def test_hver_portal_har_sin_aktive(self):
        a = _vakt('Kamp 7', self.brann, er_aktiv=True)
        b = _vakt('Stevnet', self.standard, er_aktiv=True)
        self.assertEqual(hent_aktiv_vakt(self.brann), a)
        self.assertEqual(hent_aktiv_vakt(self.standard), b)
        with aktiver_portal(self.brann):
            self.assertEqual(hent_aktiv_vakt(), a)

    def test_ny_vakt_er_aldri_aktiv(self):
        """Ellers ville en ny vakt i en portal med aktiv vakt feilet — og feilen
        ville blitt meldt som «navnet er tatt»."""
        _vakt('A', self.brann, er_aktiv=True)
        ny = opprett_vakt('B', year=2026, startet=timezone.now(), portal=self.brann)
        self.assertFalse(ny.er_aktiv)

    def test_gjor_aktiv_roerer_bare_sin_egen_portal(self):
        brann_aktiv = _vakt('Kamp 6', self.brann, er_aktiv=True)
        standard_aktiv = _vakt('Stevnet', self.standard, er_aktiv=True)
        neste = _vakt('Kamp 7', self.brann)
        with transaction.atomic():
            gjor_aktiv(neste)
        brann_aktiv.refresh_from_db()
        standard_aktiv.refresh_from_db()
        self.assertFalse(brann_aktiv.er_aktiv)
        self.assertIsNotNone(brann_aktiv.avsluttet)
        self.assertTrue(standard_aktiv.er_aktiv, 'den andre portalens vakt skal stå')
        self.assertIsNone(standard_aktiv.avsluttet)

    def test_laasen_svarer_for_riktig_portal(self):
        a = _vakt('Kamp 7', self.brann, er_aktiv=True)
        _vakt('Stevnet', self.standard, er_aktiv=True)
        with transaction.atomic():
            self.assertEqual(laas_aktiv_vakt(self.brann), a)

    def test_aarets_vakt_hentes_fra_riktig_portal(self):
        """Mutanten som droppet portalfilteret i `vakt_for_year` overlevde: Branns
        «2026» ble returnert når Standard spurte, og lat opprettelse ville gjort
        Branns vakt aktiv i feil portal."""
        from core.vakt import vakt_for_year
        brann_2026 = _vakt('Brann 2026', self.brann)
        standard_2026 = vakt_for_year(2026, self.standard)
        self.assertNotEqual(standard_2026, brann_2026)
        self.assertEqual(standard_2026.portal, self.standard)
        self.assertEqual(vakt_for_year(2026, self.brann), brann_2026)

    def test_lat_opprettelse_skjer_i_portalen(self):
        vakt = hent_aktiv_vakt(self.brann)
        self.assertEqual(vakt.portal, self.brann)
        self.assertTrue(vakt.er_aktiv)


class AvsluttVaktPerPortalTests(TestCase):
    """«Avslutt vakt» i én portal skal ikke røre den andre."""

    def setUp(self):
        import os
        import tempfile
        from unittest import mock
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)
        self.standard = eneste_portal()
        self.brann = Vaktportal.objects.create(navn='Brann', slug='brann')
        self.kamp = _vakt('Kamp 6', self.brann, er_aktiv=True)
        self.stevnet = _vakt('Stevnet', self.standard, er_aktiv=True)
        self.admin = CustomUser.objects.create_user(
            username='a', password='x', role='admin', must_change_password=False)

    def test_ny_vakt_havner_i_samme_portal(self):
        vaktslutt.avslutt(self.kamp, ny_vakt_navn='Kamp 7', bruker=self.admin)
        ny = hent_aktiv_vakt(self.brann)
        self.assertEqual(ny.navn, 'Kamp 7')
        self.assertEqual(ny.portal, self.brann)

    def test_den_andre_portalens_vakt_staar(self):
        vaktslutt.avslutt(self.kamp, ny_vakt_navn='Kamp 7', bruker=self.admin)
        self.stevnet.refresh_from_db()
        self.assertTrue(self.stevnet.er_aktiv)
        self.assertEqual(hent_aktiv_vakt(self.standard), self.stevnet)
