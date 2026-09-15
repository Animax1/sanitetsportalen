"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 1 — innlogging og kontoer.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import CustomUser, LoginEvent
from accounts.test_helpers import gi_standardtilgang
from accounts.tests_mfa import _make_totp_code


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class UtloggingRydderTests(TestCase):
    """H4: «Logg ut» er det som rydder drifts-PC-en."""

    def test_clear_site_data(self):
        b = CustomUser.objects.create_user(username='ut', password='x', must_change_password=False)
        c = Client(); c.force_login(b)
        res = c.post(reverse('accounts:logout'))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res['Clear-Site-Data'], '"cache", "storage"')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KontolaasOgMfaTests(TestCase):
    """M1: riktig passord nullstiller ikke telleren før MFA er bestått."""

    def setUp(self):
        self.url = reverse('accounts:login')
        self.user = CustomUser.objects.create_user(
            username='mfalaas', password='TestPassord123!', role='admin',
            must_change_password=False, mfa_required=True)
        gi_standardtilgang(self.user, 'admin')
        self.device = TOTPDevice.objects.create(user=self.user, name='T', confirmed=True)

    def test_passordsteget_lar_telleren_staa(self):
        self.user.failed_login_attempts = 4
        self.user.save(update_fields=['failed_login_attempts'])
        c = Client()
        c.post(self.url, {'username': 'mfalaas', 'password': 'TestPassord123!'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 4, 'MFA gjenstår')
        # Ett feil MFA-forsøk til låser kontoen.
        c.post(self.url, {'totp_code': '000000'})
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.locked_until)

    def test_mfa_bestaatt_nullstiller(self):
        self.user.failed_login_attempts = 3
        self.user.save(update_fields=['failed_login_attempts'])
        c = Client()
        c.post(self.url, {'username': 'mfalaas', 'password': 'TestPassord123!'})
        res = c.post(self.url, {'totp_code': _make_totp_code(self.device)})
        self.assertEqual(res.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.locked_until)

    def test_uten_mfa_nullstiller_passordet_som_foer(self):
        b = CustomUser.objects.create_user(username='utenmfa', password='TestPassord123!',
                                           must_change_password=False, failed_login_attempts=2)
        Client().post(self.url, {'username': 'utenmfa', 'password': 'TestPassord123!'})
        b.refresh_from_db()
        self.assertEqual(b.failed_login_attempts, 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InnloggingValidererSkjemaetTests(TestCase):
    """M2: et brukernavn over 64 tegn skal ikke nå databasen."""

    def test_for_langt_brukernavn_gir_vanlig_feil(self):
        res = Client().post(reverse('accounts:login'), {'username': 'x' * 70, 'password': 'y'})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Feil brukernavn eller passord')
        self.assertEqual(LoginEvent.objects.count(), 0)

    def test_innloggingsloggen_faar_proxyens_ip(self):
        """H2 på innloggingsloggen."""
        Client().post(reverse('accounts:login'), {'username': 'finnesikke', 'password': 'y'},
                      HTTP_X_FORWARDED_FOR='6.6.6.6, 5.6.7.8', REMOTE_ADDR='10.0.0.1')
        self.assertEqual(LoginEvent.objects.get().ip, '5.6.7.8')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MfaStegKreverAktivKontoTests(TestCase):
    """L5: en frosset konto kommer ikke gjennom MFA-steget."""

    def test_inaktiv_i_verifiseringssteget(self):
        u = CustomUser.objects.create_user(username='frys', password='TestPassord123!',
                                           must_change_password=False, mfa_required=True)
        d = TOTPDevice.objects.create(user=u, name='T', confirmed=True)
        c = Client()
        c.post(reverse('accounts:login'), {'username': 'frys', 'password': 'TestPassord123!'})
        u.is_active = False
        u.save(update_fields=['is_active'])
        res = c.post(reverse('accounts:login'), {'totp_code': _make_totp_code(d)})
        self.assertEqual(res.status_code, 302)
        self.assertNotIn('_auth_user_id', c.session)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RedigerAdminTests(TestCase):
    """M7: «Rediger» kan ikke ta admin-rollen fra deg selv eller siste admin,
    og `is_active` er ikke i skjemaet."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(username='adm_r', password='x', role='admin',
                                                    must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.c = Client(); self.c.force_login(self.admin)

    def _rediger(self, bruker, rolle):
        return self.c.post(reverse('portaladmin:user_detail', kwargs={'pk': bruker.pk}),
                           {'action': 'edit', 'role': rolle})

    def test_ikke_seg_selv(self):
        self._rediger(self.admin, 'bruker')
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, 'admin')

    def test_annen_admin_kan_degradere(self):
        annen = CustomUser.objects.create_user(username='adm2', password='x', role='admin',
                                               must_change_password=False)
        self._rediger(annen, 'bruker')
        annen.refresh_from_db()
        self.assertEqual(annen.role, 'bruker', 'det finnes en admin igjen')

    def test_siste_admin_sperres_i_hjelperen(self):
        """Gjennom viewet er «siste admin» alltid også «deg selv» (den som
        redigerer er admin). Hjelperen skal likevel svare riktig på egen hånd."""
        from accounts.views import _kan_degraderes
        ikke_admin = CustomUser.objects.create_user(username='b_x', password='x', must_change_password=False)
        self.assertIn('siste', _kan_degraderes(self.admin, ikke_admin, 'bruker', 'admin'))
        self.assertEqual(_kan_degraderes(self.admin, ikke_admin, 'admin'), '')
        self.assertEqual(_kan_degraderes(ikke_admin, self.admin, 'bruker'), '', 'ikke admin fra før')

    def test_is_active_ikke_i_skjemaet(self):
        from accounts.forms import AdminUserEditForm
        self.assertNotIn('is_active', AdminUserEditForm(instance=self.admin).fields)
        annen = CustomUser.objects.create_user(username='b_r', password='x', must_change_password=False)
        self.c.post(reverse('portaladmin:user_detail', kwargs={'pk': annen.pk}),
                    {'action': 'edit', 'role': 'bruker', 'is_active': ''})
        annen.refresh_from_db()
        self.assertTrue(annen.is_active, 'frys/tø er veien')

    def test_midlertidig_passord_caches_ikke(self):
        """L11."""
        annen = CustomUser.objects.create_user(username='b_nc', password='x', must_change_password=False)
        res = self.c.get(reverse('portaladmin:user_detail', kwargs={'pk': annen.pk}))
        self.assertIn('no-store', res.get('Cache-Control', ''))
        res = self.c.get(reverse('portaladmin:user_create'))
        self.assertIn('no-store', res.get('Cache-Control', ''))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PassordbytteOgSesjonsnokkelTests(TestCase):
    """M11: `current_session_key` peker på sesjonen som finnes etter byttet."""

    def test_nokkelen_er_den_roterte(self):
        u = CustomUser.objects.create_user(username='pb', password='GammeltPassord123!',
                                           must_change_password=False)
        c = Client()
        c.login(username='pb', password='GammeltPassord123!')
        res = c.post(reverse('accounts:change_password'), {
            'old_password': 'GammeltPassord123!',
            'new_password1': 'NyttSterktPassord456!', 'new_password2': 'NyttSterktPassord456!'})
        self.assertEqual(res.status_code, 302, res.content)
        u.refresh_from_db()
        self.assertEqual(u.current_session_key, c.session.session_key)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SuperbrukerenErNodutgangenTests(TestCase):
    """`is_superuser` kan ikke fratas admin-rollen (André, 15. sep. 2026).

    **Hvorfor flagget, og ikke rollen.** `is_superuser` og `is_staff` betyr
    ingenting for portalen: tilgang er `role == 'admin'` og `ModulTilgang`,
    og de to Django-flaggene gjelder bare `/django-admin/`, som er rutet av i
    produksjon (S1). De settes derfor bare av `manage.py create_admin`, og
    **følger bevisst ikke med** når noen gjøres til administrator gjennom
    brukeradministrasjonen — det var André sin observasjon, og den er riktig.

    Det gjør kontoen til noe annet enn «en administrator til»: den er den ene
    man kommer tilbake inn med. «Siste admin»-sperra dekker den ikke — er det
    tre administratorer, kan superbrukeren degraderes uten at noe protesterer,
    og da er nødutgangen borte mens portalen ser helt normal ut.
    """

    def setUp(self):
        self.super = CustomUser.objects.create_user(
            username='rot', password='x', role='admin',
            must_change_password=False, is_staff=True, is_superuser=True)
        gi_standardtilgang(self.super, 'admin')
        self.admin = CustomUser.objects.create_user(
            username='adm_s', password='x', role='admin',
            must_change_password=False)
        gi_standardtilgang(self.admin, 'admin')
        self.c = Client()
        self.c.force_login(self.admin)

    def test_superbrukeren_beholder_admin_selv_om_det_finnes_andre(self):
        """Den ene testen «siste admin» ikke ville fanget: her *er* det en
        admin igjen, så den gamle sperra sier ja."""
        self.c.post(reverse('portaladmin:user_detail',
                            kwargs={'pk': self.super.pk}),
                    {'action': 'edit', 'role': 'bruker'})
        self.super.refresh_from_db()
        self.assertEqual(self.super.role, 'admin')

    def test_hjelperen_sier_hvorfor(self):
        from accounts.views import _kan_degraderes
        grunn = _kan_degraderes(self.super, self.admin, 'bruker', 'admin')
        self.assertIn('superbruker', grunn.lower())

    def test_en_vanlig_admin_kan_fortsatt_degraderes(self):
        """Den andre retningen. Sperrer flagget for mye, blir hver admin
        udegraderbar — og det ville vært like galt, bare stillere."""
        from accounts.views import _kan_degraderes
        self.assertEqual(
            _kan_degraderes(self.admin, self.super, 'bruker', 'admin'), '')

    def test_den_slettes_ikke_heller(self):
        """En regel som sperrer degradering, men slipper sletting, verner
        ingenting: sletting tar kontoen og ikke bare rollen."""
        from accounts.views import _kan_slettes
        kan, grunn = _kan_slettes(self.super, self.admin)
        self.assertFalse(kan)
        self.assertIn('superbruker', grunn.lower())

        res = self.c.post(reverse('portaladmin:user_delete',
                                  kwargs={'pk': self.super.pk}))
        self.assertTrue(CustomUser.objects.filter(pk=self.super.pk).exists())
        self.assertIn(res.status_code, (302, 403))

    def test_frysing_staar_igjen_med_vilje(self):
        """**Grensen er om handlingen lar seg reversere.** Frysing er det —
        «Tø konto» står ved siden av — og en annen administrator kan alltid
        tine kontoen. Degradering og sletting er det ikke."""
        self.c.post(reverse('portaladmin:user_detail',
                            kwargs={'pk': self.super.pk}), {'action': 'freeze'})
        self.super.refresh_from_db()
        self.assertFalse(self.super.is_active)
        self.assertEqual(self.super.role, 'admin', 'rollen står, kontoen er tint tilbake')
