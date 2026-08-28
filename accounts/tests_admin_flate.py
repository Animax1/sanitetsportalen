"""Tester for S1/S2: én innloggingsflate, og admin samlet under /portal-admin/.

- S1: `/django-admin/` er av i produksjon, og portalen dekker det den ble brukt til
- S2: superbrukere arver `must_change_password=True`
- URL-konsolidering: brukeradmin ligger under /portal-admin/, gamle stier redirecter

Kjør med: python manage.py test accounts.tests_admin_flate
"""
from django.test import TestCase, Client, override_settings
from django.urls import NoReverseMatch, reverse

from accounts.models import CustomUser, LoginEvent
from accounts.test_helpers import gi_standardtilgang


@override_settings(SECURE_SSL_REDIRECT=False)
class DjangoAdminAvskruddTests(TestCase):
    """S1: Django admin skal ikke være montert når DEBUG=False."""

    def test_django_admin_gir_404_i_prod(self):
        """URLconf-en bygges ved import, så DEBUG må settes før den lastes.

        Testkjøringen har DEBUG=False, og urls.py er allerede importert med den
        verdien — flaten skal derfor ikke finnes.
        """
        resp = self.client.get('/django-admin/')
        self.assertEqual(resp.status_code, 404)

    def test_django_admin_login_gir_404(self):
        """Selve innloggingsskjemaet er det som var problemet, ikke listesidene."""
        resp = self.client.get('/django-admin/login/')
        self.assertEqual(resp.status_code, 404)

    def test_ingen_admin_urlnavn_er_reversible(self):
        with self.assertRaises(NoReverseMatch):
            reverse('admin:index')


class SuperuserPasswordChangeTests(TestCase):
    """S2: superbrukere skal arve must_change_password=True fra modellen."""

    def test_create_superuser_krever_passordbytte(self):
        bruker = CustomUser.objects.create_superuser(
            username='boot_admin', password='fra-miljovariabel',
        )
        self.assertTrue(bruker.must_change_password)
        self.assertTrue(bruker.is_staff)
        self.assertTrue(bruker.is_superuser)
        self.assertEqual(bruker.role, 'admin')

    def test_eksplisitt_false_respekteres(self):
        """Tester og fixtures skal fortsatt kunne overstyre."""
        bruker = CustomUser.objects.create_superuser(
            username='boot_admin2', password='x', must_change_password=False,
        )
        self.assertFalse(bruker.must_change_password)

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_superbruker_sendes_til_passordbytte(self):
        """Hele poenget med S2 — middlewaren skal fange bootstrap-adminen."""
        bruker = CustomUser.objects.create_superuser(
            username='boot_admin3', password='x',
        )
        client = Client()
        client.force_login(bruker)

        resp = client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/change-password/', resp['Location'])


@override_settings(SECURE_SSL_REDIRECT=False)
class BrukeradminUrlFlyttingTests(TestCase):
    """Brukeradmin ligger under /portal-admin/, gamle stier redirecter."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='url_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin)
        self.client.force_login(self.admin)

    def test_ny_sti_svarer(self):
        resp = self.client.get('/portal-admin/brukere/')
        self.assertEqual(resp.status_code, 200)

    def test_url_navn_peker_paa_ny_sti(self):
        """Malene bruker {% url %}, så navnet må gi den nye stien."""
        self.assertEqual(reverse('accounts:user_list'), '/portal-admin/brukere/')
        self.assertEqual(reverse('accounts:user_create'), '/portal-admin/brukere/ny/')
        self.assertEqual(
            reverse('accounts:user_detail', kwargs={'pk': 7}),
            '/portal-admin/brukere/7/',
        )
        self.assertEqual(
            reverse('accounts:user_delete', kwargs={'pk': 7}),
            '/portal-admin/brukere/7/slett/',
        )

    def test_gammel_liste_redirecter_permanent(self):
        resp = self.client.get('/accounts/users/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], '/portal-admin/brukere/')

    def test_gammel_ny_bruker_redirecter(self):
        resp = self.client.get('/accounts/users/ny/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], '/portal-admin/brukere/ny/')

    def test_gammel_detalj_redirecter_med_pk(self):
        resp = self.client.get(f'/accounts/users/{self.admin.pk}/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], f'/portal-admin/brukere/{self.admin.pk}/')

    def test_innlogging_ligger_fortsatt_under_accounts(self):
        """Innlogging er ikke en admin-flate og skal ikke flyttes."""
        self.assertEqual(reverse('accounts:login'), '/accounts/login/')
        self.assertEqual(reverse('accounts:logout'), '/accounts/logout/')
        self.assertEqual(reverse('accounts:change_password'), '/accounts/change-password/')


@override_settings(SECURE_SSL_REDIRECT=False)
class LoginEventListTests(TestCase):
    """Global innloggingslogg — erstatter LoginEventAdmin i django-admin."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='log_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin)
        self.annen = CustomUser.objects.create_user(
            username='log_bruker', password='x', role='read_write',
            must_change_password=False,
        )
        gi_standardtilgang(self.annen)
        LoginEvent.objects.create(
            user=self.annen, username_attempt='log_bruker',
            success=True, ip='10.0.0.1',
        )
        LoginEvent.objects.create(
            user=None, username_attempt='ukjent_konto',
            success=False, ip='10.0.0.2',
        )
        LoginEvent.objects.create(
            user=self.annen, username_attempt='log_bruker',
            success=False, ip='10.0.0.1',
            event_type=LoginEvent.EVENT_MFA_VERIFY_FAILED,
        )
        self.client.force_login(self.admin)

    def test_krever_admin(self):
        self.client.force_login(self.annen)
        resp = self.client.get(reverse('accounts:login_event_list'))
        self.assertNotEqual(resp.status_code, 200)

    def test_viser_alle_hendelser(self):
        resp = self.client.get(reverse('accounts:login_event_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_count'], 3)

    def test_filter_paa_brukernavn(self):
        resp = self.client.get(reverse('accounts:login_event_list'), {'q': 'ukjent'})
        self.assertEqual(resp.context['total_count'], 1)

    def test_filter_paa_ip(self):
        resp = self.client.get(reverse('accounts:login_event_list'), {'q': '10.0.0.1'})
        self.assertEqual(resp.context['total_count'], 2)

    def test_filter_paa_feilede(self):
        resp = self.client.get(reverse('accounts:login_event_list'), {'result': 'fail'})
        self.assertEqual(resp.context['total_count'], 2)

    def test_filter_paa_hendelsestype(self):
        resp = self.client.get(reverse('accounts:login_event_list'), {
            'event_type': LoginEvent.EVENT_MFA_VERIFY_FAILED,
        })
        self.assertEqual(resp.context['total_count'], 1)

    def test_hendelse_uten_konto_vises(self):
        """Forsøk på et brukernavn som ikke finnes er nettopp det man vil se."""
        resp = self.client.get(reverse('accounts:login_event_list'))
        self.assertContains(resp, 'ukjent_konto')


class AppSettingCommandTests(TestCase):
    """Management command som erstatter AppSettingAdmin."""

    def _kjor(self, *args):
        from io import StringIO
        from django.core.management import call_command
        ut = StringIO()
        call_command('appsetting', *args, stdout=ut)
        return ut.getvalue()

    def test_set_oppretter_ny_noekkel(self):
        from patients.models import AppSetting
        self._kjor('--set', 'test_noekkel', 'verdi1')
        self.assertEqual(AppSetting.objects.get(key='test_noekkel').value, 'verdi1')

    def test_set_endrer_eksisterende(self):
        from patients.models import AppSetting
        AppSetting.objects.create(key='test_noekkel', value='gammel')
        ut = self._kjor('--set', 'test_noekkel', 'ny')
        self.assertEqual(AppSetting.objects.get(key='test_noekkel').value, 'ny')
        self.assertIn('gammel', ut)
        self.assertIn('ny', ut)

    def test_get_viser_verdi(self):
        from patients.models import AppSetting
        AppSetting.objects.create(key='test_noekkel', value='verdi42')
        self.assertIn('verdi42', self._kjor('--get', 'test_noekkel'))

    def test_get_ukjent_noekkel_feiler(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self._kjor('--get', 'finnes_ikke')

    def test_list_viser_alle(self):
        from patients.models import AppSetting
        AppSetting.objects.create(key='aaa', value='1')
        AppSetting.objects.create(key='bbb', value='2')
        ut = self._kjor('--list')
        self.assertIn('aaa', ut)
        self.assertIn('bbb', ut)

    def test_delete_fjerner_noekkel(self):
        from patients.models import AppSetting
        AppSetting.objects.create(key='slettmeg', value='1')
        self._kjor('--delete', 'slettmeg')
        self.assertFalse(AppSetting.objects.filter(key='slettmeg').exists())
