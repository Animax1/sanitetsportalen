"""MFA-tester for accounts-appen.

Kjør med: python manage.py test accounts.tests_mfa
"""
import time

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase, Client, override_settings, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.core import signing

from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken

from accounts.models import CustomUser, LoginEvent
from accounts.views import _check_mfa_trust


def _make_totp_code(device):
    """Generer gyldig TOTP-kode for en enhet ved hjelp av ekte TOTP-beregning."""
    totp = TOTP(key=device.bin_key, step=device.step, t0=device.t0, digits=device.digits)
    totp.time = time.time()
    return str(totp.token()).zfill(device.digits)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MFASetupFlowTests(TestCase):
    """Tester for MFA-oppsett ved første innlogging."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')

    def _create_user(self, role, mfa_required=True):
        return CustomUser.objects.create_user(
            username=f'user_{role}',
            password='TestPassord123!',
            role=role,
            must_change_password=False,
            mfa_required=mfa_required,
        )

    def test_admin_user_forced_to_mfa_setup_on_first_login(self):
        """Admin-bruker uten TOTP-enhet skal omdirigeres til MFA-oppsett."""
        user = self._create_user('admin')
        resp = self.client.post(self.url, {
            'username': user.username, 'password': 'TestPassord123!',
        })
        # Etter redirect til login-URL på nytt, skal stage 2 vises
        self.assertRedirects(resp, self.url)
        resp2 = self.client.get(self.url)
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, 'Sett opp to-faktor')

    def test_lead_user_forced_to_mfa_setup_on_first_login(self):
        """Lead-bruker uten TOTP-enhet skal omdirigeres til MFA-oppsett."""
        user = self._create_user('lead')
        resp = self.client.post(self.url, {
            'username': user.username, 'password': 'TestPassord123!',
        })
        self.assertRedirects(resp, self.url)
        resp2 = self.client.get(self.url)
        self.assertContains(resp2, 'Sett opp to-faktor')

    def test_read_write_user_not_forced_to_mfa(self):
        """read_write-bruker uten MFA-krav skal gå rett inn."""
        user = self._create_user('read_write', mfa_required=False)
        resp = self.client.post(self.url, {
            'username': user.username, 'password': 'TestPassord123!',
        }, follow=True)
        # Skal landes på / (eller change_password)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse('mfa_setup_user_id' in self.client.session)
        self.assertFalse('mfa_verify_user_id' in self.client.session)

    def test_mfa_setup_shows_qr_and_backup_codes(self):
        """MFA-oppsett-siden skal vise QR-kode og backup-koder."""
        user = self._create_user('admin')
        # Trinn 1: Send inn legitimasjon
        self.client.post(self.url, {
            'username': user.username, 'password': 'TestPassord123!',
        })
        # Trinn 2: Hent oppsett-siden
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data:image/png;base64,')
        self.assertContains(resp, 'Skriv disse ned nå')
        self.assertContains(resp, 'backup-code')

    def test_mfa_setup_confirms_device_with_correct_code(self):
        """Korrekt TOTP-kode under oppsett skal bekrefte enheten og logge inn."""
        user = self._create_user('admin')
        # Steg 1: Legitimasjon → får session med mfa_setup_user_id
        self.client.post(self.url, {
            'username': user.username, 'password': 'TestPassord123!',
        })
        # Steg 2: GET oppsett-siden – dette oppretter en ubekreftet TOTP-enhet
        self.client.get(self.url)
        # Finn den ukonfirmerte enheten
        device = TOTPDevice.objects.get(user=user, confirmed=False)
        code = _make_totp_code(device)
        resp = self.client.post(self.url, {'totp_code': code})
        # Skal logge inn og redirecte
        self.assertRedirects(resp, '/', fetch_redirect_response=False)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        # Sjekk audit-logg
        self.assertTrue(
            LoginEvent.objects.filter(
                user=user,
                event_type=LoginEvent.EVENT_MFA_SETUP_COMPLETED,
            ).exists()
        )

    def test_mfa_setup_rejects_wrong_code(self):
        """Feil kode under oppsett skal vise feilmelding og ikke logge inn."""
        user = self._create_user('admin')
        self.client.post(self.url, {
            'username': user.username, 'password': 'TestPassord123!',
        })
        # GET oppsett-siden slik at TOTP-enheten opprettes
        self.client.get(self.url)
        resp = self.client.post(self.url, {'totp_code': '000000'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Feil kode')
        # Enheten er fortsatt ubekreftet
        device = TOTPDevice.objects.get(user=user, confirmed=False)
        self.assertFalse(device.confirmed)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MFAVerifyFlowTests(TestCase):
    """Tester for MFA-verifisering ved gjentatt innlogging."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='mfabruker',
            password='TestPassord123!',
            role='admin',
            must_change_password=False,
            mfa_required=True,
        )
        # Opprett bekreftet TOTP-enhet
        self.device = TOTPDevice.objects.create(
            user=self.user,
            name='Test enhet',
            confirmed=True,
        )

    def _login_to_verify_stage(self):
        """Logg inn med passord for å komme til verifiserings-stage."""
        self.client.post(self.url, {
            'username': self.user.username, 'password': 'TestPassord123!',
        })

    def test_mfa_verify_accepts_correct_totp(self):
        """Korrekt TOTP-kode skal logge inn brukeren."""
        self._login_to_verify_stage()
        code = _make_totp_code(self.device)
        resp = self.client.post(self.url, {'totp_code': code})
        self.assertRedirects(resp, '/', fetch_redirect_response=False)
        self.assertTrue(
            LoginEvent.objects.filter(
                user=self.user,
                event_type=LoginEvent.EVENT_MFA_VERIFY_SUCCESS,
            ).exists()
        )

    def test_mfa_verify_accepts_backup_code(self):
        """Gyldig backup-kode skal logge inn brukeren."""
        static_device = StaticDevice.objects.create(user=self.user, name='Backup')
        StaticToken.objects.create(device=static_device, token='ABCD1234')

        self._login_to_verify_stage()
        resp = self.client.post(self.url, {'backup_code': 'ABCD1234'})
        self.assertRedirects(resp, '/', fetch_redirect_response=False)
        self.assertTrue(
            LoginEvent.objects.filter(
                user=self.user,
                event_type=LoginEvent.EVENT_MFA_BACKUP_USED,
            ).exists()
        )

    def test_mfa_backup_code_single_use(self):
        """Backup-kode kan kun brukes én gang."""
        static_device = StaticDevice.objects.create(user=self.user, name='Backup')
        StaticToken.objects.create(device=static_device, token='ONCE1234')

        # Første gangs bruk – skal lykkes
        self._login_to_verify_stage()
        resp = self.client.post(self.url, {'backup_code': 'ONCE1234'})
        self.assertRedirects(resp, '/', fetch_redirect_response=False)

        # Logg ut og prøv på nytt
        self.client.logout()
        self._login_to_verify_stage()
        resp2 = self.client.post(self.url, {'backup_code': 'ONCE1234'})
        # Koden er brukt opp – skal ikke lykkes
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, 'Ugyldig backup-kode')

    def test_mfa_verify_wrong_code_shows_error(self):
        """Feil TOTP-kode skal vise feilmelding."""
        self._login_to_verify_stage()
        resp = self.client.post(self.url, {'totp_code': '000000'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Feil kode')
        self.assertTrue(
            LoginEvent.objects.filter(
                user=self.user,
                event_type=LoginEvent.EVENT_MFA_VERIFY_FAILED,
            ).exists()
        )


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MFATrustCookieTests(TestCase):
    """Tester for trust-cookie-logikk."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='trustbruker',
            password='TestPassord123!',
            role='admin',
            must_change_password=False,
            mfa_required=True,
        )
        self.device = TOTPDevice.objects.create(
            user=self.user,
            name='Test enhet',
            confirmed=True,
        )

    def test_mfa_trust_cookie_skips_verify(self):
        """Gyldig trust-cookie skal hoppe over MFA-verifisering."""
        # Sett trust-cookie manuelt
        signer = signing.TimestampSigner()
        token = signer.sign(f'{self.user.pk}:{self.device.pk}')
        self.client.cookies[f'mfa_trusted_{self.user.pk}'] = token

        resp = self.client.post(self.url, {
            'username': self.user.username, 'password': 'TestPassord123!',
        })
        # Skal logge inn direkte (ingen verifiserings-stage)
        self.assertRedirects(resp, '/', fetch_redirect_response=False)
        self.assertFalse('mfa_verify_user_id' in self.client.session)
        self.assertTrue(
            LoginEvent.objects.filter(
                user=self.user,
                event_type=LoginEvent.EVENT_MFA_TRUST_COOKIE_USED,
            ).exists()
        )

    def test_mfa_trust_cookie_expires_after_30_days(self):
        """Trust-cookie som er eldre enn 30 dager skal ikke aksepteres."""
        from unittest.mock import patch
        import datetime

        signer = signing.TimestampSigner()
        # Lag en kode som er 31 dager gammel
        token = signer.sign(f'{self.user.pk}:{self.device.pk}')

        # Simuler at cookien ble satt for 31 dager siden
        future_time = timezone.now() + datetime.timedelta(days=31)
        request_mock = type('Req', (), {'COOKIES': {f'mfa_trusted_{self.user.pk}': token}})()

        with patch('django.core.signing.time') as mock_time:
            mock_time.time.return_value = future_time.timestamp()
            result = _check_mfa_trust(request_mock, self.user)

        self.assertFalse(result)

    def test_trust_cookie_set_when_checkbox_checked(self):
        """Innlogging med 'Stol på enheten'-haken satt skal sette trust-cookie."""
        # Gå til verifiserings-stage
        self.client.post(self.url, {
            'username': self.user.username, 'password': 'TestPassord123!',
        })
        code = _make_totp_code(self.device)
        resp = self.client.post(self.url, {
            'totp_code': code,
            'trust_device': 'on',
        })
        cookie_name = f'mfa_trusted_{self.user.pk}'
        self.assertIn(cookie_name, resp.cookies)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MFAAdminResetTests(TestCase):
    """Tester for admin-nullstilling av MFA."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_superuser(
            username='adminbruker',
            password='AdminPassord123!',
            role='admin',
            must_change_password=False,
            mfa_required=False,  # Admin trenger ikke MFA for denne testen
        )
        self.target = CustomUser.objects.create_user(
            username='målbruker',
            password='TestPassord123!',
            role='lead',
            must_change_password=False,
            mfa_required=True,
        )
        self.device = TOTPDevice.objects.create(
            user=self.target,
            name='Test enhet',
            confirmed=True,
        )
        self.client.force_login(self.admin)

    def test_mfa_reset_by_admin_clears_devices_and_cookies(self):
        """Admin skal kunne nullstille MFA – sletter enheter og logg."""
        url = reverse('accounts:user_detail', kwargs={'pk': self.target.pk})
        resp = self.client.post(url, {'action': 'reset_mfa'})
        self.assertRedirects(resp, url)
        # Alle TOTP-enheter skal være slettet
        self.assertEqual(TOTPDevice.objects.filter(user=self.target).count(), 0)
        # mfa_required skal fortsatt være True
        self.target.refresh_from_db()
        self.assertTrue(self.target.mfa_required)
        # Audit-logg skal finnes
        self.assertTrue(
            LoginEvent.objects.filter(
                user=self.target,
                event_type=LoginEvent.EVENT_MFA_RESET_BY_ADMIN,
            ).exists()
        )

    def test_mfa_required_can_be_toggled_via_django_admin(self):
        """mfa_required-feltet skal kunne endres via Django admin."""
        from django.contrib.admin.sites import AdminSite
        from accounts.admin import CustomUserAdmin

        site = AdminSite()
        admin_instance = CustomUserAdmin(CustomUser, site)
        form_class = admin_instance.get_form(None, self.target)
        form = form_class(
            instance=self.target,
            data={
                'username': self.target.username,
                'role': self.target.role,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
                'must_change_password': False,
                'mfa_required': False,  # Skru av MFA
                'failed_login_attempts': 0,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        user.refresh_from_db()
        self.assertFalse(user.mfa_required)
