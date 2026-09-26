"""Hver handling i brukeradministrasjonen setter spor (26. sep. 2026, B2).

Frysing, tining, utlogging, rolle og modultilgang skrev auditrad. Men:

- **«Nytt midlertidig passord»** — den mest inngripende handlingen på en konto,
  den som gir admin et passord som virker — skrev ingenting.
- **«Lås opp»** skrev ingenting.
- **Redigering** logget bare `role` og modultilgang. `mfa_required`,
  `er_delt_konto`, `email` og `fullt_navn` kunne endres sporløst — og en endret
  e-post er veien til en passordlenke.
- **«Nullstill MFA»** og **«Send invitasjon»** sto bare i innloggingsloggen,
  eller ingen steder.

Det er mønsteret `CLAUDE.md` kaller feil vei rundt: jo mer inngripende, jo
mindre spor. Passordet skrives aldri i loggen — bare at det ble byttet.
"""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BrukeradminSetterSporTests(TestCase):

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='adm_b2', password='x', role='admin', must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.offer = CustomUser.objects.create_user(
            username='kari_b2', password='GammeltPassord123!', must_change_password=False,
            email='kari@example.com', fullt_navn='Kari Nordmann')
        self.c = Client()
        self.c.force_login(self.admin)

    def _post(self, **data):
        return self.c.post(f'/portal-admin/brukere/{self.offer.pk}/', data)

    def _rader(self, felt):
        return list(AuditLog.objects.filter(record_id=self.offer.pk, field_name=felt))

    def test_nytt_passord_logges_uten_passordet(self):
        res = self._post(action='reset_password')
        self.assertEqual(res.status_code, 200)
        rad, = self._rader('password')
        self.assertEqual((rad.user, rad.action), (self.admin, 'UPDATE'))
        self.offer.refresh_from_db()
        self.assertFalse(self.offer.check_password('GammeltPassord123!'))
        # Passordet står i svaret — og aldri i loggen.
        passord = res.context['temp_password']
        self.assertFalse(AuditLog.objects.filter(new_value__contains=passord).exists())

    def test_laas_opp_logges(self):
        self.offer.locked_until = timezone.now() + timedelta(minutes=10)
        self.offer.save(update_fields=['locked_until'])
        self._post(action='unlock')
        rad, = self._rader('locked_until')
        self.assertEqual(rad.user, self.admin)

    def test_nullstill_mfa_logges_i_auditloggen_ogsaa(self):
        self._post(action='reset_mfa')
        self.assertEqual(len(self._rader('mfa')), 1)

    def test_invitasjon_logges(self):
        with patch('accounts.views.send_invitasjon', return_value=True):
            self._post(action='send_invitasjon')
        rad, = self._rader('invitasjon')
        self.assertEqual(rad.new_value, 'kari@example.com')

    def test_hvert_endret_felt_i_redigeringen_logges(self):
        res = self._post(action='edit', fullt_navn='Kari Hansen', email='kari@annet.no',
                         role='bruker', mfa_required='on')
        self.assertEqual(res.status_code, 302, getattr(res, 'context', None)
                         and res.context['form'].errors)
        felt = {r.field_name: (r.old_value, r.new_value)
                for r in AuditLog.objects.filter(record_id=self.offer.pk,
                                                 table_name='accounts_customuser')}
        self.assertEqual(felt['email'], ('kari@example.com', 'kari@annet.no'))
        self.assertEqual(felt['fullt_navn'], ('Kari Nordmann', 'Kari Hansen'))
        self.assertEqual(felt['mfa_required'], ('False', 'True'))
        self.assertNotIn('role', felt, 'uendret felt gir ingen rad')

    def test_uendret_redigering_gir_ingen_rader(self):
        self._post(action='edit', fullt_navn='Kari Nordmann', email='kari@example.com',
                   role='bruker')
        self.assertFalse(AuditLog.objects.filter(record_id=self.offer.pk,
                                                 table_name='accounts_customuser').exists())
