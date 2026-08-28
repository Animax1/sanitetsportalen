"""Tester for herdingen av innloggingsflyten (N1, S4, N4, S5, S6).

- N1: `next`-parameteren valideres (åpen redirect)
- S4: `Notification.url` valideres på samme måte
- N4: MFA-stegene har egne rate-limit-bøtter og er omfattet av kontosperren
- S5: utlogging krever POST
- S6: MFA trust-cookie følger `request.is_secure()`, ikke `not DEBUG`

Kjør med: python manage.py test accounts.tests_innlogging_herding
"""
import re
import time

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang


def _make_totp_code(device):
    totp = TOTP(key=device.bin_key, step=device.step, t0=device.t0, digits=device.digits)
    totp.time = time.time()
    return str(totp.token()).zfill(device.digits)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NextParameterTests(TestCase):
    """N1: ingen verdi av `next` skal kunne sende brukeren ut av appen."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='nextbruker', password='TestPassord123!',
            role='read_write', must_change_password=False,
        )
        gi_standardtilgang(self.user)

    def _login_med_next(self, next_verdi):
        return self.client.post(
            f'{self.url}?next={next_verdi}',
            {'username': 'nextbruker', 'password': 'TestPassord123!'},
        )

    def test_absolutt_url_til_fremmed_host_avvises(self):
        resp = self._login_med_next('https://falsk-sanitetsportal.example/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/')

    def test_protokoll_relativ_url_avvises(self):
        """//evil.example er den varianten folk oftest glemmer."""
        resp = self._login_med_next('//evil.example')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/')

    def test_relativ_sti_beholdes(self):
        resp = self._login_med_next('/pasienter/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/pasienter/')

    def test_uten_next_gaar_til_forsiden(self):
        resp = self.client.post(self.url, {
            'username': 'nextbruker', 'password': 'TestPassord123!',
        })
        self.assertEqual(resp['Location'], '/')

    def test_javascript_url_avvises(self):
        resp = self._login_med_next('javascript:alert(1)')
        self.assertEqual(resp['Location'], '/')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NextGjennomSkjemaTests(TestCase):
    """`next` skal overleve selve innsendingen — den ekte nettleserflyten.

    `NextParameterTests` over poster direkte til `...?next=...` og tester
    viewet. Nettleseren gjør noe annet: skjemaet poster til `{% url %}`, som
    ikke har query-strengen med. Uten et skjult next-felt gikk verdien tapt i
    det brukeren trykket «Logg inn», og man havnet alltid på forsiden.
    Oppdaget ved manuell testing i prod 13. aug. 2026.
    """

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse('accounts:login')
        CustomUser.objects.create_user(
            username='skjemabruker', password='TestPassord123!',
            role='read_write', must_change_password=False,
        )

    def _hent_skjult(self, html, navn):
        m = re.search(rf'name="{navn}" value="([^"]*)"', html)
        return m.group(1) if m else None

    def _logg_inn_som_nettleser(self, next_verdi=None):
        """Etterlikn nettleseren: hent siden, les feltene, post til action."""
        adresse = f'{self.url}?next={next_verdi}' if next_verdi else self.url
        html = self.client.get(adresse).content.decode()

        data = {
            'csrfmiddlewaretoken': self._hent_skjult(html, 'csrfmiddlewaretoken'),
            'username': 'skjemabruker',
            'password': 'TestPassord123!',
        }
        skjult_next = self._hent_skjult(html, 'next')
        if skjult_next is not None:
            data['next'] = skjult_next

        # Merk: poster til self.url uten query — nøyaktig som skjemaets action
        return self.client.post(self.url, data)

    def test_relativ_next_overlever_innsending(self):
        resp = self._logg_inn_som_nettleser('/pasienter/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/pasienter/')

    def test_ekstern_next_avvises_ogsaa_via_skjemaet(self):
        resp = self._logg_inn_som_nettleser('https://evil.example/')
        self.assertEqual(resp['Location'], '/')

    def test_uten_next_gaar_til_forsiden(self):
        resp = self._logg_inn_som_nettleser()
        self.assertEqual(resp['Location'], '/')

    def test_csrf_flyten_virker_med_haandheving(self):
        """Client(enforce_csrf_checks=True) — fanger ekte CSRF-regresjoner."""
        resp = self._logg_inn_som_nettleser('/pasienter/')
        self.assertNotEqual(resp.status_code, 403)

    def test_innloggingssiden_er_ikke_cachebar(self):
        """Uten no-cache kan nettleseren servere et skjema med utdatert
        CSRF-token, som gir 403 ved innsending. Observert i prod på iOS."""
        resp = self.client.get(self.url)
        cache_control = resp.get('Cache-Control', '')
        self.assertIn('no-store', cache_control)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MfaNextParameterTests(TestCase):
    """N1: MFA-stegene skal arve den validerte verdien, ikke rå input."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='mfanext', password='TestPassord123!',
            role='admin', must_change_password=False, mfa_required=True,
        )
        gi_standardtilgang(self.user)
        self.device = TOTPDevice.objects.create(
            user=self.user, name='Test', confirmed=True,
        )

    def test_ondsinnet_next_overlever_ikke_mfa_steget(self):
        self.client.post(
            f'{self.url}?next=https://evil.example/',
            {'username': 'mfanext', 'password': 'TestPassord123!'},
        )
        resp = self.client.post(self.url, {'totp_code': _make_totp_code(self.device)})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/')

    def test_gyldig_next_overlever_mfa_steget(self):
        self.client.post(
            f'{self.url}?next=/pasienter/',
            {'username': 'mfanext', 'password': 'TestPassord123!'},
        )
        resp = self.client.post(self.url, {'totp_code': _make_totp_code(self.device)})
        self.assertEqual(resp['Location'], '/pasienter/')

    def test_forgiftet_sesjonsverdi_avvises_ved_lesing(self):
        """En sesjon fra en eldre release kan inneholde en uvalidert verdi."""
        self.client.post(self.url, {
            'username': 'mfanext', 'password': 'TestPassord123!',
        })
        sesjon = self.client.session
        sesjon['mfa_next_url'] = 'https://evil.example/'
        sesjon.save()

        resp = self.client.post(self.url, {'totp_code': _make_totp_code(self.device)})
        self.assertEqual(resp['Location'], '/')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NotificationRedirectTests(TestCase):
    """S4: lagret open redirect i varsel-visningen."""

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='varselbruker', password='x',
            role='read_write', must_change_password=False,
        )
        gi_standardtilgang(self.user)
        self.client.force_login(self.user)

    def _varsel(self, url):
        from core.models import Notification
        return Notification.objects.create(
            user=self.user, module_slug='patients', kind='test',
            title='Test', message='', url=url,
        )

    def test_ekstern_url_sendes_til_varsler(self):
        notif = self._varsel('https://evil.example/')
        resp = self.client.get(f'/varsler/{notif.pk}/lest/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/varsler/')

    def test_relativ_url_beholdes(self):
        notif = self._varsel('/pasienter/')
        resp = self.client.get(f'/varsler/{notif.pk}/lest/')
        self.assertEqual(resp['Location'], '/pasienter/')

    def test_tom_url_gir_varselsiden(self):
        notif = self._varsel('')
        resp = self.client.get(f'/varsler/{notif.pk}/lest/')
        self.assertEqual(resp['Location'], '/varsler/')

    def test_varselet_markeres_lest_uansett(self):
        """Valideringen skal ikke hindre selve handlingen."""
        notif = self._varsel('https://evil.example/')
        self.client.get(f'/varsler/{notif.pk}/lest/')
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class MfaRateLimitTests(TestCase):
    """N4: MFA-forsøk skal ikke dele én bøtte på tvers av brukere."""

    def setUp(self):
        self.client_a = Client()
        self.client_b = Client()
        self.url = reverse('accounts:login')
        self.bruker_a = self._lag_bruker('mfa_a')
        self.bruker_b = self._lag_bruker('mfa_b')

    def _lag_bruker(self, navn):
        bruker = CustomUser.objects.create_user(
            username=navn, password='TestPassord123!',
            role='admin', must_change_password=False, mfa_required=True,
        )
        gi_standardtilgang(bruker)
        TOTPDevice.objects.create(user=bruker, name='Test', confirmed=True)
        return bruker

    def _til_verify(self, client, bruker):
        client.post(self.url, {
            'username': bruker.username, 'password': 'TestPassord123!',
        })

    def test_en_brukers_forsok_blokkerer_ikke_en_annen(self):
        """Kjernen i N4: 10 forsøk fra A skal ikke gi 429 for B.

        Med den gamle dekoratoren delte alle MFA-POST-er samme bøtte fordi
        skjemaet ikke sender `username`. Ved vaktstart ville bruker nummer 11
        fått 429 uten at noe var galt med kontoen.
        """
        self._til_verify(self.client_a, self.bruker_a)
        for _ in range(10):
            self.client_a.post(self.url, {'totp_code': '000000'})

        self._til_verify(self.client_b, self.bruker_b)
        resp = self.client_b.post(self.url, {'totp_code': '000000'})
        self.assertNotEqual(resp.status_code, 429)

    def test_egen_bruker_blir_ratelimited(self):
        """Grensen skal fortsatt virke — bare per bruker."""
        self._til_verify(self.client_a, self.bruker_a)
        statuser = [
            self.client_a.post(self.url, {'totp_code': '000000'}).status_code
            for _ in range(12)
        ]
        self.assertIn(429, statuser)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MfaKontosperreTests(TestCase):
    """N4: MFA-steget manglet kontosperre helt."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='mfalaas', password='TestPassord123!',
            role='admin', must_change_password=False, mfa_required=True,
        )
        gi_standardtilgang(self.user)
        self.device = TOTPDevice.objects.create(
            user=self.user, name='Test', confirmed=True,
        )

    def _til_verify(self):
        self.client.post(self.url, {
            'username': 'mfalaas', 'password': 'TestPassord123!',
        })

    def test_fem_feilede_koder_laser_kontoen(self):
        self._til_verify()
        for _ in range(5):
            self.client.post(self.url, {'totp_code': '000000'})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked())

    def test_last_konto_kan_ikke_verifisere_med_riktig_kode(self):
        self._til_verify()
        self.user.locked_until = timezone.now() + timedelta(minutes=15)
        self.user.save(update_fields=['locked_until'])

        resp = self.client.post(self.url, {'totp_code': _make_totp_code(self.device)})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'låst')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_feilet_kode_teller_opp(self):
        self._til_verify()
        self.client.post(self.url, {'totp_code': '000000'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 1)

    def test_vellykket_verifisering_nullstiller_telleren(self):
        self._til_verify()
        # Telleren settes direkte i stedet for via feilede POST-er: django_otp
        # throttler selve TOTP-enheten etter feilede verify_token()-kall
        # (ThrottlingMixin, eksponentiell backoff). En korrekt kode rett etter
        # noen feilforsøk ville blitt avvist av *den* mekanismen, og testen
        # ville målt django_otp i stedet for vår egen nullstilling.
        self.user.failed_login_attempts = 3
        self.user.save(update_fields=['failed_login_attempts'])

        self.client.post(self.url, {'totp_code': _make_totp_code(self.device)})
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LogoutMetodeTests(TestCase):
    """S5: utlogging via GET lot enhver nettside logge ut brukeren vår."""

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='utlogg', password='x',
            role='read_write', must_change_password=False,
        )
        gi_standardtilgang(self.user)
        self.client.force_login(self.user)

    def test_get_gir_405(self):
        resp = self.client.get(reverse('accounts:logout'))
        self.assertEqual(resp.status_code, 405)

    def test_get_logger_ikke_ut(self):
        self.client.get(reverse('accounts:logout'))
        self.assertIn('_auth_user_id', self.client.session)

    def test_post_logger_ut(self):
        resp = self.client.post(reverse('accounts:logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TrustCookieSecureTests(TestCase):
    """S6: Secure-flagget skal følge forbindelsen, ikke DEBUG-innstillingen."""

    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='trustbruker', password='TestPassord123!',
            role='admin', must_change_password=False, mfa_required=True,
        )
        gi_standardtilgang(self.user)
        self.device = TOTPDevice.objects.create(
            user=self.user, name='Test', confirmed=True,
        )

    def _verifiser_med_trust(self, secure):
        self.client.post(self.url, {
            'username': 'trustbruker', 'password': 'TestPassord123!',
        }, secure=secure)
        return self.client.post(self.url, {
            'totp_code': _make_totp_code(self.device),
            'trust_device': 'on',
        }, secure=secure)

    def test_uten_tls_settes_cookien_uten_secure(self):
        """Offline-modus kjører bevisst uten TLS. Før satte vi Secure likevel,
        og nettleseren kastet cookien — «stol på denne enheten» virket ikke."""
        resp = self._verifiser_med_trust(secure=False)
        cookie = resp.cookies.get(f'mfa_trusted_{self.user.pk}')
        self.assertIsNotNone(cookie, 'Trust-cookien ble ikke satt')
        self.assertFalse(cookie['secure'])

    def test_med_tls_settes_secure(self):
        resp = self._verifiser_med_trust(secure=True)
        cookie = resp.cookies.get(f'mfa_trusted_{self.user.pk}')
        self.assertIsNotNone(cookie, 'Trust-cookien ble ikke satt')
        self.assertTrue(cookie['secure'])
