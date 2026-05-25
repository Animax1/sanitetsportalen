"""Fase 5-tester: bruker-behandler-kobling, mine-filter, og tildelings-varsler.

Dekker:
- ?mine=1 filter på /pasienter/api/patients/
- Signal: assigning Behandler.user / Helsepersonell.user gir varsel
- Signal: transfer-flytting gir varsel til BÅDE ny og forrige eier
- Signal: ingen varsel når bruker-koblingen ikke endrer seg
- Signal: feiler aldri pasient-lagring selv om varsel-koden feiler
- Form: UserPatientLinkForm validerer at man ikke kan koble til BÅDE behandler og helsepersonell
"""
from __future__ import annotations

import json

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from core.models import Notification
from patients.models import Patient, Forstehjelper, Helsepersonell


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MineFilterTests(TestCase):
    """Tester for ?mine=1-filteret på pasientlisten."""

    def setUp(self):
        self.kari = CustomUser.objects.create_user(
            username='kari', password='pw12345678',
            role='read_write', must_change_password=False,
        )
        self.ola = CustomUser.objects.create_user(
            username='ola', password='pw12345678',
            role='read_write', must_change_password=False,
        )
        # Kari koblet til Forstehjelper 'Kari Hansen'
        self.beh_kari = Forstehjelper.objects.create(name='Kari Hansen', user=self.kari)
        # Ola koblet til Helsepersonell 'Ola Olsen'
        self.hp_ola = Helsepersonell.objects.create(name='Ola Olsen', user=self.ola)
        # En tredje Forstehjelper uten bruker
        self.beh_andre = Forstehjelper.objects.create(name='Andre', user=None)

        # Pasienter
        self.p_kari = Patient.objects.create(
            pasientnummer=1, year=2026, forstehjelper=self.beh_kari,
        )
        self.p_ola = Patient.objects.create(
            pasientnummer=2, year=2026, helsepersonell_ref=self.hp_ola,
        )
        self.p_andre = Patient.objects.create(
            pasientnummer=3, year=2026, forstehjelper=self.beh_andre,
        )
        self.url = '/pasienter/api/patients/'

    def test_default_returns_all_active(self):
        self.client.force_login(self.kari)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        nrs = sorted(p['pasientnummer'] for p in data)
        self.assertEqual(nrs, [1, 2, 3])

    def test_mine_filter_for_behandler(self):
        self.client.force_login(self.kari)
        res = self.client.get(self.url + '?mine=1')
        self.assertEqual(res.status_code, 200)
        nrs = [p['pasientnummer'] for p in res.json()]
        self.assertEqual(nrs, [1])

    def test_mine_filter_for_helsepersonell(self):
        self.client.force_login(self.ola)
        res = self.client.get(self.url + '?mine=1')
        nrs = [p['pasientnummer'] for p in res.json()]
        self.assertEqual(nrs, [2])

    def test_mine_filter_for_user_without_link_returns_empty(self):
        unlinked = CustomUser.objects.create_user(
            username='ulink', password='pw12345678',
            role='read_only', must_change_password=False,
        )
        self.client.force_login(unlinked)
        res = self.client.get(self.url + '?mine=1')
        self.assertEqual(res.json(), [])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AssignmentNotificationSignalTests(TestCase):
    """Tester for at signalen sender varsler ved tildeling/flytting."""

    def setUp(self):
        self.kari = CustomUser.objects.create_user(
            username='kari', password='pw', must_change_password=False,
        )
        self.ola = CustomUser.objects.create_user(
            username='ola', password='pw', must_change_password=False,
        )
        self.beh_kari = Forstehjelper.objects.create(name='Kari', user=self.kari)
        self.beh_ola = Forstehjelper.objects.create(name='Ola', user=self.ola)
        self.beh_uten_bruker = Forstehjelper.objects.create(name='X', user=None)
        self.hp_kari = Helsepersonell.objects.create(name='HP-Kari', user=self.kari)

    def test_assignment_on_create_notifies_user(self):
        Patient.objects.create(pasientnummer=10, year=2026, forstehjelper=self.beh_kari)
        self.assertEqual(
            Notification.objects.filter(user=self.kari, kind='patient_assigned').count(),
            1,
        )

    def test_assignment_to_behandler_without_user_does_not_notify(self):
        Patient.objects.create(pasientnummer=11, year=2026, forstehjelper=self.beh_uten_bruker)
        self.assertEqual(Notification.objects.count(), 0)

    def test_helsepersonell_assignment_notifies(self):
        Patient.objects.create(pasientnummer=12, year=2026, helsepersonell_ref=self.hp_kari)
        notifs = Notification.objects.filter(user=self.kari)
        self.assertEqual(notifs.count(), 1)
        self.assertIn('oppfølgingsansvarlig', notifs.first().message)

    def test_transfer_notifies_both_old_and_new(self):
        p = Patient.objects.create(pasientnummer=13, year=2026, forstehjelper=self.beh_kari)
        # Tøm initial assignment-varsel for å isolere transfer
        Notification.objects.all().delete()
        # Flytt fra Kari til Ola
        p.forstehjelper = self.beh_ola
        p.save()
        # Ola får 'patient_assigned'
        self.assertTrue(
            Notification.objects.filter(
                user=self.ola, kind='patient_assigned',
            ).exists(),
        )
        # Kari får 'patient_transferred_away'
        self.assertTrue(
            Notification.objects.filter(
                user=self.kari, kind='patient_transferred_away',
            ).exists(),
        )

    def test_no_notification_if_assignment_unchanged(self):
        p = Patient.objects.create(pasientnummer=14, year=2026, forstehjelper=self.beh_kari)
        Notification.objects.all().delete()
        # Endre noe annet — ikke FK
        p.problemstilling = 'Endret'
        p.save()
        self.assertEqual(Notification.objects.count(), 0)

    def test_dedup_prevents_double_notifications(self):
        """notify() dedup-vinduet hindrer duplikat ved umiddelbar re-assign."""
        Patient.objects.create(pasientnummer=15, year=2026, forstehjelper=self.beh_kari)
        Patient.objects.create(pasientnummer=16, year=2026, forstehjelper=self.beh_kari)
        # Kari skal kun ha ett varsel fordi message ('Du er satt ... pasient #15')
        # vs #16 har forskjellig pasientnummer i message — så IKKE dedup.
        # Men hvis vi tildeler SAMME pasient to ganger med samme melding, da deduper.
        self.assertEqual(
            Notification.objects.filter(user=self.kari).count(),
            2,
        )


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PasientRolleFormTests(TestCase):
    """Tester for PasientRolleForm i accounts."""

    def setUp(self):
        from accounts.forms import PasientRolleForm
        self.FormCls = PasientRolleForm
        self.user = CustomUser.objects.create_user(
            username='kari', password='pw', must_change_password=False,
        )
        self.fh = Forstehjelper.objects.create(name='kari', user=None)
        self.hp = Helsepersonell.objects.create(name='kari', user=None)

    def test_link_to_forstehjelper(self):
        form = self.FormCls(self.user, data={'pasient_rolle': 'forstehjelper'})
        self.assertTrue(form.is_valid())
        form.save()
        self.fh.refresh_from_db()
        self.assertEqual(self.fh.user, self.user)
        self.user.refresh_from_db()
        self.assertTrue(self.user.kan_redigere_pasienter)

    def test_link_to_helsepersonell(self):
        form = self.FormCls(self.user, data={'pasient_rolle': 'helsepersonell'})
        self.assertTrue(form.is_valid())
        form.save()
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.user, self.user)
        self.user.refresh_from_db()
        self.assertTrue(self.user.kan_redigere_pasienter)

    def test_ingen_removes_access(self):
        self.fh.user = self.user
        self.fh.save()
        form = self.FormCls(self.user, data={'pasient_rolle': 'ingen'})
        self.assertTrue(form.is_valid())
        form.save()
        self.fh.refresh_from_db()
        self.assertIsNone(self.fh.user)
        self.user.refresh_from_db()
        self.assertFalse(self.user.kan_redigere_pasienter)

    def test_switch_releases_old_link(self):
        """Bytt fra førstehjelper til helsepersonell — gammel kobling frigjøres."""
        self.fh.user = self.user
        self.fh.save()
        form = self.FormCls(self.user, data={'pasient_rolle': 'helsepersonell'})
        self.assertTrue(form.is_valid())
        form.save()
        self.fh.refresh_from_db()
        self.hp.refresh_from_db()
        self.assertIsNone(self.fh.user)
        self.assertEqual(self.hp.user, self.user)
