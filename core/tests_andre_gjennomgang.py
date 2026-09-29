"""Andre gjennomgang av sikkerhetspuljene, 29. sep. 2026.

Tre funn, hvert prøvd gjennom den ekte inngangen: sletting av en vakt som ble
gjenåpnet mens backupen gikk, innlogginger for MFA-kontoer som ikke ble talt, og
en backup som feilet før sletting og ga 500.
"""
from __future__ import annotations

import os
import tempfile
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser, LoginEvent
from core.models import Vakt
from core.vakt import hent_aktiv_vakt
from patients.test_helpers import sett_aktiv_vakt


class _MedAdmin(TestCase):

    def setUp(self):
        cache.clear()
        mappe = tempfile.TemporaryDirectory()
        self.addCleanup(mappe.cleanup)
        miljo = mock.patch.dict(os.environ, {'BACKUP_DIR': mappe.name})
        miljo.start()
        self.addCleanup(miljo.stop)
        self.aktiv = sett_aktiv_vakt(2026)
        self.gammel = Vakt.objects.create(
            navn='Gammel', year=2026, startet=timezone.now(), er_aktiv=False,
            avsluttet=timezone.now())
        self.admin = CustomUser.objects.create_user(
            username='adm_ag', password='x', role='admin', must_change_password=False)
        self.c = Client()
        self.c.force_login(self.admin)


@override_settings(SECURE_SSL_REDIRECT=False)
class VaktGjenaapnetUnderSlettingenTests(_MedAdmin):

    def test_vakta_som_ble_aktiv_imens_slettes_ikke(self):
        andre = Client()
        andre.force_login(self.admin)

        def gjenaapne_imens(*a, **k):
            andre.post(f'/portal-admin/vakt/{self.gammel.pk}/gjenaapne/')

        with mock.patch('core.backup.create_backup', side_effect=gjenaapne_imens):
            self.c.post(f'/portal-admin/vakt/{self.gammel.pk}/slett/', {'navn': 'Gammel'})
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists())
        self.assertEqual(hent_aktiv_vakt().pk, self.gammel.pk)

    def test_en_tidligere_vakt_slettes_fortsatt(self):
        """Motprøven."""
        self.c.post(f'/portal-admin/vakt/{self.gammel.pk}/slett/', {'navn': 'Gammel'})
        self.assertFalse(Vakt.objects.filter(pk=self.gammel.pk).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class BackupenFeilerForSlettingenTests(_MedAdmin):

    def test_vaktslettingen_gir_melding_og_ikke_500(self):
        with mock.patch('core.backup.create_backup', side_effect=OSError('disken er full')):
            svar = self.c.post(f'/portal-admin/vakt/{self.gammel.pk}/slett/',
                               {'navn': 'Gammel'}, follow=True)
        self.assertEqual(svar.status_code, 200)
        self.assertContains(svar, 'Backupen før slettingen feilet')
        self.assertTrue(Vakt.objects.filter(pk=self.gammel.pk).exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class FullforteInnloggingerTelles(TestCase):
    """Passordsteget for en MFA-konto er `passord_ok`; innloggingen fullføres av
    MFA-hendelsen. Tellingene så bare `login`, og viste 0 for hver MFA-bruker."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='mfa_ag', password='x', must_change_password=False)
        for typ in (LoginEvent.EVENT_PASSORD_OK, LoginEvent.EVENT_MFA_VERIFY_SUCCESS,
                    LoginEvent.EVENT_PASSORD_OK, LoginEvent.EVENT_MFA_TRUST_COOKIE_USED):
            LoginEvent.objects.create(user=self.bruker, username_attempt='mfa_ag',
                                      success=True, event_type=typ)

    def test_min_profil_teller_to(self):
        c = Client()
        c.force_login(self.bruker)
        svar = c.get('/min-profil/')
        self.assertEqual(svar.context['weekly_login_count'], 2)

    def test_driftsstatusen_teller_to(self):
        from core.admin_status import _get_innlogging
        self.assertEqual(_get_innlogging()['vellykkede'], 2)
