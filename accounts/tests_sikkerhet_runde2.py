"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 2 — innlogging.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
from datetime import timedelta

from django.core import signing
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import CustomUser, LoginEvent
from accounts.test_helpers import gi_standardtilgang
from accounts.views import _check_mfa_trust, _trust_token


class _Req:
    def __init__(self, cookies):
        self.COOKIES = cookies


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TrustCookieTests(TestCase):
    """M12: cookien er bundet til passordet og signert med egen salt."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(username='tc', password='TestPassord123!',
                                                   must_change_password=False, mfa_required=True)
        self.device = TOTPDevice.objects.create(user=self.user, name='T', confirmed=True)

    def _req(self, token):
        return _Req({f'mfa_trusted_{self.user.pk}': token})

    def test_gyldig(self):
        self.assertTrue(_check_mfa_trust(self._req(_trust_token(self.user, self.device)), self.user))

    def test_gammelt_format_uten_salt_avvises(self):
        gammel = signing.TimestampSigner().sign(f'{self.user.pk}:{self.device.pk}')
        self.assertFalse(_check_mfa_trust(self._req(gammel), self.user))

    def test_passordbytte_ugyldiggjoer(self):
        token = _trust_token(self.user, self.device)
        self.user.set_password('NyttPassord456!')
        self.user.save()
        self.assertFalse(_check_mfa_trust(self._req(token), self.user))

    def test_annen_brukers_cookie(self):
        annen = CustomUser.objects.create_user(username='tc2', password='x', must_change_password=False)
        d2 = TOTPDevice.objects.create(user=annen, name='T', confirmed=True)
        self.assertFalse(_check_mfa_trust(self._req(_trust_token(annen, d2)), self.user))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LikhetsvalidatorTests(TestCase):
    """M13: passordet kan ikke ligne brukernavnet — i alle tre skjemaene."""

    def test_change_password(self):
        u = CustomUser.objects.create_user(username='karinordmann', password='GammeltPassord123!',
                                           must_change_password=False)
        c = Client(); c.login(username='karinordmann', password='GammeltPassord123!')
        res = c.post(reverse('accounts:change_password'), {
            'old_password': 'GammeltPassord123!',
            'new_password1': 'karinordmann1', 'new_password2': 'karinordmann1'})
        self.assertEqual(res.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.check_password('GammeltPassord123!'), 'passordet ble ikke byttet')

    def test_sett_passord_skjemaet_faar_brukeren(self):
        from accounts.forms import SettPassordForm
        u = CustomUser.objects.create_user(username='olanordmann', password='x', must_change_password=False)
        f = SettPassordForm({'new_password1': 'olanordmann99', 'new_password2': 'olanordmann99'}, user=u)
        self.assertFalse(f.is_valid())
        f = SettPassordForm({'new_password1': 'HeltAnnetPassord77!', 'new_password2': 'HeltAnnetPassord77!'}, user=u)
        self.assertTrue(f.is_valid(), f.errors)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KontolaasRoeperIkkeTests(TestCase):
    """M14: en låst konto svarer som feil passord for den som ikke har
    passordet; bare eieren får vite at kontoen er låst."""

    def setUp(self):
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(username='laast', password='TestPassord123!',
                                                   must_change_password=False)
        gi_standardtilgang(self.user, 'leser')
        self.user.locked_until = timezone.now() + timedelta(minutes=10)
        self.user.save(update_fields=['locked_until'])

    def test_feil_passord_paa_laast_konto_gir_vanlig_melding(self):
        res = Client().post(self.url, {'username': 'laast', 'password': 'feil'})
        self.assertContains(res, 'Feil brukernavn eller passord')
        self.assertNotContains(res, 'låst')

    def test_ukjent_bruker_ser_likt_ut(self):
        a = Client().post(self.url, {'username': 'laast', 'password': 'feil'}).content
        b = Client().post(self.url, {'username': 'finnesikke', 'password': 'feil'}).content
        # Selve feilmeldingen er den samme; CSRF-token og nonce varierer.
        self.assertIn(b'Feil brukernavn eller passord', a)
        self.assertIn(b'Feil brukernavn eller passord', b)

    def test_riktig_passord_paa_laast_konto_sier_laast(self):
        c = Client()
        res = c.post(self.url, {'username': 'laast', 'password': 'TestPassord123!'})
        self.assertContains(res, 'midlertidig låst')
        self.assertNotIn('_auth_user_id', c.session)
        self.assertTrue(LoginEvent.objects.filter(user=self.user, success=False).exists())


@override_settings(SECURE_SSL_REDIRECT=False)
class RateLimitPaaBrukeradminTests(TestCase):
    """L13: brukeradmin bremses."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        # Bøtta er nøklet på bruker-pk, og pk-ene gjentar seg mellom
        # testklasser — tøm etterpå også, ellers arver neste klasse 429.
        self.addCleanup(cache.clear)

    def test_sletting_strupes(self):
        adm = CustomUser.objects.create_user(username='adm_rl', password='x', role='admin',
                                             must_change_password=False)
        gi_standardtilgang(adm, 'admin')
        offer = CustomUser.objects.create_user(username='offer', password='x', must_change_password=False)
        c = Client(); c.force_login(adm)
        koder = [c.post(reverse('portaladmin:user_delete', kwargs={'pk': offer.pk}), {'bekreft': 'feil'}).status_code
                 for _ in range(12)]
        self.assertIn(429, koder)
