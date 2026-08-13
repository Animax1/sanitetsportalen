"""Tester for portalens brukeradministrasjon (/accounts/users/).

Disse dekker funksjonaliteten som må være på plass før `/django-admin/` kan
fjernes (S1 i docs/FORBEDRINGER_2026-08.md): opprettelse, MFA-toggle, frys/tø
og permanent sletting.

Kjør med: python manage.py test accounts.tests_user_admin
"""
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from audit.models import AuditLog


def _create_session_for_user(user):
    """Opprett en aktiv databasesesjon koblet til brukeren."""
    store = SessionStore()
    store['_auth_user_id'] = str(user.pk)
    store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
    store['_auth_user_hash'] = user.get_session_auth_hash()
    store.save()
    return store.session_key


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminUserCreateEmailTests(TestCase):
    """Regresjon: tom e-post ga 500 ved opprettelse av bruker.

    Modellfeltet er null=True, så ModelForm setter empty_value=None på
    skjemafeltet. clean_email() antok tom streng og kalte .strip() på None.
    """

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='create_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        self.client.force_login(self.admin)

    def test_oppretting_uten_epost(self):
        resp = self.client.post(reverse('accounts:user_create'), {
            'username': 'utenepost',
            'email': '',
            'role': 'read_only',
        })
        self.assertEqual(resp.status_code, 200)
        ny = CustomUser.objects.get(username='utenepost')
        self.assertIsNone(ny.email)
        self.assertTrue(ny.must_change_password)

    def test_oppretting_med_epost(self):
        resp = self.client.post(reverse('accounts:user_create'), {
            'username': 'medepost',
            'email': '  post@eksempel.no  ',
            'role': 'read_write',
        })
        self.assertEqual(resp.status_code, 200)
        ny = CustomUser.objects.get(username='medepost')
        self.assertEqual(ny.email, 'post@eksempel.no')

    def test_to_brukere_uten_epost_kolliderer_ikke(self):
        """unique_email_if_set skal tillate flere NULL samtidig."""
        for navn in ['tom1', 'tom2']:
            resp = self.client.post(reverse('accounts:user_create'), {
                'username': navn, 'email': '', 'role': 'read_only',
            })
            self.assertEqual(resp.status_code, 200)
        # tom1, tom2 og create_admin har alle NULL e-post
        self.assertEqual(CustomUser.objects.filter(email__isnull=True).count(), 3)


@override_settings(SECURE_SSL_REDIRECT=False)
class MfaRequiredEditTests(TestCase):
    """mfa_required skal kunne slås både på og av fra portalen."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='mfa_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        self.target = CustomUser.objects.create_user(
            username='mfa_target', password='x', role='read_only',
            must_change_password=False, mfa_required=False,
        )
        self.client.force_login(self.admin)

    def test_form_inneholder_mfa_required(self):
        from accounts.forms import AdminUserEditForm
        self.assertIn('mfa_required', AdminUserEditForm(instance=self.target).fields)

    def test_kan_sla_paa_mfa(self):
        url = reverse('accounts:user_detail', kwargs={'pk': self.target.pk})
        resp = self.client.post(url, {
            'action': 'edit', 'role': 'read_only',
            'is_active': 'on', 'mfa_required': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.mfa_required)

    def test_kan_sla_av_mfa(self):
        """Uten denne veien var Nullstill MFA en enveisbillett."""
        self.target.mfa_required = True
        self.target.save(update_fields=['mfa_required'])

        url = reverse('accounts:user_detail', kwargs={'pk': self.target.pk})
        resp = self.client.post(url, {
            'action': 'edit', 'role': 'read_only', 'is_active': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertFalse(self.target.mfa_required)

    def test_template_viser_mfa_avkrysning(self):
        url = reverse('accounts:user_detail', kwargs={'pk': self.target.pk})
        resp = self.client.get(url)
        self.assertContains(resp, 'name="mfa_required"')


@override_settings(SECURE_SSL_REDIRECT=False)
class FreezeThawPortalTests(TestCase):
    """Frys/tø fra portalens brukerdetalj (paritet med django-admin-aksjonen)."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='fz_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        self.target = CustomUser.objects.create_user(
            username='fz_target', password='x', role='read_write',
            must_change_password=False,
        )
        self.client.force_login(self.admin)

    def _post(self, action, pk=None):
        url = reverse('accounts:user_detail', kwargs={'pk': pk or self.target.pk})
        return self.client.post(url, {'action': action})

    def test_frys_deaktiverer_og_sletter_sesjoner(self):
        key = _create_session_for_user(self.target)
        self.assertTrue(Session.objects.filter(session_key=key).exists())

        resp = self._post('freeze')
        self.assertEqual(resp.status_code, 302)

        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertFalse(Session.objects.filter(session_key=key).exists())

    def test_frys_skriver_auditlog(self):
        self._post('freeze')
        rad = AuditLog.objects.filter(
            table_name='accounts_customuser', record_id=self.target.pk,
        ).latest('created_at')
        self.assertEqual(rad.action, 'UPDATE')
        self.assertEqual(rad.field_name, 'is_active')
        self.assertEqual(rad.new_value, 'False')
        self.assertEqual(rad.user, self.admin)
        self.assertEqual(rad.app_label, 'accounts')

    def test_kan_ikke_fryse_seg_selv(self):
        resp = self._post('freeze', pk=self.admin.pk)
        self.assertEqual(resp.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_to_reaktiverer(self):
        self.target.is_active = False
        self.target.save(update_fields=['is_active'])

        resp = self._post('thaw')
        self.assertEqual(resp.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)


@override_settings(SECURE_SSL_REDIRECT=False)
class UserDeleteTests(TestCase):
    """Permanent sletting av brukerkonto fra portalen."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='del_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        # En admin til, slik at «siste admin»-sperren ikke slår inn utilsiktet
        self.admin2 = CustomUser.objects.create_user(
            username='del_admin2', password='x', role='admin',
            must_change_password=False,
        )
        self.target = CustomUser.objects.create_user(
            username='del_target', password='x', role='read_write',
            must_change_password=False,
        )
        self.client.force_login(self.admin)

    def _slett(self, pk, bekreftelse):
        url = reverse('accounts:user_delete', kwargs={'pk': pk})
        return self.client.post(url, {'confirm_username': bekreftelse})

    def test_sletting_med_riktig_bekreftelse(self):
        resp = self._slett(self.target.pk, 'del_target')
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_feil_bekreftelse_sletter_ikke(self):
        resp = self._slett(self.target.pk, 'feil_navn')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_tom_bekreftelse_sletter_ikke(self):
        self._slett(self.target.pk, '')
        self.assertTrue(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_get_gir_405(self):
        url = reverse('accounts:user_delete', kwargs={'pk': self.target.pk})
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_kan_ikke_slette_seg_selv(self):
        resp = self._slett(self.admin.pk, 'del_admin')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CustomUser.objects.filter(pk=self.admin.pk).exists())

    def test_kan_ikke_slette_siste_admin(self):
        from accounts.views import _kan_slettes
        self.admin2.delete()
        # self.admin er nå eneste aktive admin. Sperren testes direkte fordi
        # den innloggede admin uansett ville truffet «ikke deg selv»-sperren.
        tillatt, grunn = _kan_slettes(self.admin, self.target)
        self.assertFalse(tillatt)
        self.assertIn('siste aktive administrator', grunn)

    def test_sletting_fjerner_aktive_sesjoner(self):
        key = _create_session_for_user(self.target)
        self._slett(self.target.pk, 'del_target')
        self.assertFalse(Session.objects.filter(session_key=key).exists())

    def test_sletting_skriver_auditlog_som_overlever(self):
        pk = self.target.pk
        self._slett(pk, 'del_target')

        rad = AuditLog.objects.get(
            table_name='accounts_customuser', record_id=pk, action='DELETE',
        )
        self.assertEqual(rad.old_value, 'del_target')
        self.assertEqual(rad.user, self.admin)
        self.assertEqual(rad.app_label, 'accounts')

    def test_navn_bevares_paa_forstehjelper(self):
        """SET_NULL: pasienthistorikken skal beholde navnet etter sletting."""
        from patients.models import Forstehjelper
        fh = Forstehjelper.objects.create(name='del_target', user=self.target)

        self._slett(self.target.pk, 'del_target')

        fh.refresh_from_db()
        self.assertEqual(fh.name, 'del_target')
        self.assertIsNone(fh.user)

    def test_ikke_admin_far_ikke_slette(self):
        vanlig = CustomUser.objects.create_user(
            username='vanlig', password='x', role='read_write',
            must_change_password=False,
        )
        self.client.force_login(vanlig)
        self._slett(self.target.pk, 'del_target')
        self.assertTrue(CustomUser.objects.filter(pk=self.target.pk).exists())

    def test_detaljside_viser_slettesperre_for_egen_konto(self):
        url = reverse('accounts:user_detail', kwargs={'pk': self.admin.pk})
        resp = self.client.get(url)
        self.assertContains(resp, 'kan ikke slette din egen konto')
