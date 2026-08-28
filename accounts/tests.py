"""Tester for accounts-appen.

Kjør med: python manage.py test accounts
"""
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang


def _create_session_for_user(user):
    """Opprett en aktiv databasesesjon koblet til brukeren."""
    store = SessionStore()
    store['_auth_user_id'] = str(user.pk)
    store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
    store['_auth_user_hash'] = user.get_session_auth_hash()
    store.save()
    return store.session_key


@override_settings(SECURE_SSL_REDIRECT=False)
class SessionInvalidationOnPasswordChangeTests(TestCase):
    """Tester at andre sesjoner invalideres ved passordbytte."""

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='testbruker',
            password='GammeltPassord123!',
            role='read_write',
        )

    def test_other_sessions_invalidated_on_password_change(self):
        """Andre aktive sesjoner for brukeren skal slettes ved passordbytte."""
        # Opprett en ekstra sesjon som simulerer at brukeren er logget inn
        # fra en annen klient
        other_session_key = _create_session_for_user(self.user)
        self.assertTrue(
            Session.objects.filter(session_key=other_session_key).exists(),
            'Den ekstra sesjonen skal finnes før passordbytte'
        )

        # Logg inn og bytt passord
        self.client.login(username='testbruker', password='GammeltPassord123!')
        response = self.client.post(
            reverse('accounts:change_password'),
            {
                'old_password': 'GammeltPassord123!',
                'new_password1': 'NyttPassord456!',
                'new_password2': 'NyttPassord456!',
            },
            follow=True,
        )

        # Passordbyttet skal gi redirect til /
        self.assertEqual(response.status_code, 200)

        # Den andre sesjonen skal nå være slettet
        self.assertFalse(
            Session.objects.filter(session_key=other_session_key).exists(),
            'Den ekstra sesjonen skal være slettet etter passordbytte'
        )

    def test_own_session_kept_on_password_change(self):
        """Nåværende sesjon skal beholdes etter passordbytte (brukeren logges ikke ut)."""
        self.client.login(username='testbruker', password='GammeltPassord123!')

        response = self.client.post(
            reverse('accounts:change_password'),
            {
                'old_password': 'GammeltPassord123!',
                'new_password1': 'NyttPassord456!',
                'new_password2': 'NyttPassord456!',
            },
        )
        # Etter vellykket passordbytte: redirect til /
        self.assertRedirects(response, '/')
        # Brukeren er fortsatt autentisert
        self.assertTrue(response.wsgi_request.user.is_authenticated)


@override_settings(SECURE_SSL_REDIRECT=False)
class SingleSessionTests(TestCase):
    """Tester at ny innlogging invaliderer tidligere sesjoner."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testbruker',
            password='Passord123!',
            role='read_write',
        )

    def test_new_login_invalidates_previous_session(self):
        """Når bruker logger inn på enhet 2, skal sesjon fra enhet 1 slettes."""
        # Enhet 1 logger inn
        client1 = Client()
        client1.post(
            reverse('accounts:login'),
            {'username': 'testbruker', 'password': 'Passord123!'},
        )
        session_key_1 = client1.session.session_key
        self.assertIsNotNone(session_key_1)
        self.assertTrue(Session.objects.filter(session_key=session_key_1).exists())

        # Enhet 2 logger inn med samme bruker
        client2 = Client()
        client2.post(
            reverse('accounts:login'),
            {'username': 'testbruker', 'password': 'Passord123!'},
        )
        session_key_2 = client2.session.session_key
        self.assertIsNotNone(session_key_2)
        self.assertNotEqual(session_key_1, session_key_2)

        # Enhet 1 sin sesjon skal nå være slettet
        self.assertFalse(
            Session.objects.filter(session_key=session_key_1).exists(),
            'Sesjon fra enhet 1 skal være slettet etter at enhet 2 logget inn'
        )
        # Enhet 2 sin sesjon skal fremdeles finnes
        self.assertTrue(
            Session.objects.filter(session_key=session_key_2).exists(),
            'Sesjon fra enhet 2 skal fremdeles være aktiv'
        )


# ── Rate-limit: dobbel dekorator (per brukernavn + per IP) ─────────────────────

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class RateLimitTests(TestCase):
    """Tester at login har både per-brukernavn og per-IP rate-limit."""

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='bruker1', password='riktigpass123', role='read_write',
            must_change_password=False,
        )

    def _clear_cache(self):
        """Nullstill rate-limit-cache mellom testene."""
        from django.core.cache import cache
        cache.clear()

    def _is_blocked(self, response):
        """Ratelimited gir enten 429 (via RATELIMIT_VIEW) eller 403 (uten)."""
        return response.status_code in (403, 429)

    def test_per_username_limit_blocks_after_10(self):
        """10. POST med feil passord mot samme brukernavn gir blokkering."""
        self._clear_cache()
        # 10 forsøk skal gå igjennom (200 OK med feilmelding)
        for i in range(10):
            r = self.client.post('/accounts/login/', {
                'username': 'bruker1', 'password': 'feilpass',
            })
            self.assertFalse(self._is_blocked(r), f'Forsøk {i+1} skulle ikke være blokkert')
        # 11. forsøk skal være blokkert
        r = self.client.post('/accounts/login/', {
            'username': 'bruker1', 'password': 'feilpass',
        })
        self.assertTrue(self._is_blocked(r))

    def test_different_usernames_not_blocked_under_ip_limit(self):
        """Ulike brukernavn fra samme IP deler IKKE per-bruker-kvoten.

        Simulerer 12 enheter bak samme NAT som logger inn samtidig: hver har
        sin egen konto, ingen av dem skal blokkeres.
        """
        self._clear_cache()
        for i in range(12):
            u = CustomUser.objects.create_user(
                username=f'user{i}', password='rett123', role='read_write',
                must_change_password=False,
            )
            r = self.client.post('/accounts/login/', {
                'username': f'user{i}', 'password': 'rett123',
            })
            # 200 (inn) eller 302 (redirect etter login) er OK – ikke blokkert
            self.assertNotIn(r.status_code, (403, 429),
                f'Bruker {i} skulle ikke være blokkert under IP-grensen (50/5m)')

    def test_per_ip_limit_protects_against_username_spraying(self):
        """50 forsøk mot ulike brukernavn fra samme IP utløser IP-grensen."""
        self._clear_cache()
        # Skap 60 unike brukernavn (under per-bruker-grensen på 10 hver)
        for i in range(60):
            CustomUser.objects.create_user(
                username=f'spray{i}', password='x', role='read_write',
                must_change_password=False,
            )
        # 50 første skal gå igjennom
        for i in range(50):
            r = self.client.post('/accounts/login/', {
                'username': f'spray{i}', 'password': 'feil',
            })
            self.assertNotIn(r.status_code, (403, 429),
                f'Forsøk {i+1} skulle ikke være blokkert før IP-grensen')
        # 51. skal være blokkert av IP-limiteren
        r = self.client.post('/accounts/login/', {
            'username': 'spray50', 'password': 'feil',
        })
        self.assertIn(r.status_code, (403, 429))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class RateLimitDisabledTests(TestCase):
    """Verifiserer at RATELIMIT_ENABLE=False (nød-bryter) skrur av grensene."""

    def test_no_limit_when_disabled(self):
        from django.core.cache import cache
        cache.clear()
        CustomUser.objects.create_user(
            username='nolimit', password='x', role='read_write',
            must_change_password=False,
        )
        client = Client()
        # 60 forsøk – ingen skal blokkeres når rate-limit er av
        for i in range(60):
            r = client.post('/accounts/login/', {
                'username': 'nolimit', 'password': 'feil',
            })
            self.assertNotIn(r.status_code, (403, 429),
                f'Forsøk {i+1}: ingen grense skal gjelde når RATELIMIT_ENABLE=False')


# ── Frys/tø-action tests ─────────────────────────────────────────────────────

class FreezeThawAdminActionTests(TestCase):
    """Tester for fryse- og tine-actionene i CustomUserAdmin."""

    def setUp(self):
        from accounts.admin import CustomUserAdmin
        from django.contrib.admin.sites import AdminSite
        self.admin = CustomUserAdmin(CustomUser, AdminSite())
        self.superuser = CustomUser.objects.create_user(
            username='superadmin', password='Test1234!', role='admin',
            is_staff=True, is_superuser=True, must_change_password=False,
        )
        self.user1 = CustomUser.objects.create_user(
            username='alice', password='Test1234!', role='vakt',
            must_change_password=False,
        )
        self.user2 = CustomUser.objects.create_user(
            username='bob', password='Test1234!', role='vakt',
            must_change_password=False,
        )

    def _request(self):
        """Lager mock-request med superadmin innlogget."""
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage
        req = RequestFactory().post('/admin/accounts/customuser/')
        req.user = self.superuser
        # Messages-framework krever en storage for å fungere i tester
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))
        return req

    def test_freeze_deactivates_users(self):
        """Fryse-actionen skal sette is_active=False på valgte brukere."""
        req = self._request()
        qs = CustomUser.objects.filter(pk__in=[self.user1.pk, self.user2.pk])
        self.admin.freeze_users(req, qs)
        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        self.assertFalse(self.user1.is_active)
        self.assertFalse(self.user2.is_active)

    def test_freeze_blocks_self_freeze(self):
        """Admin skal ikke kunne fryse seg selv ut av systemet."""
        req = self._request()
        qs = CustomUser.objects.filter(pk__in=[self.superuser.pk, self.user1.pk])
        self.admin.freeze_users(req, qs)
        # Ingen skal være endret når superuser er i utvalget
        self.superuser.refresh_from_db()
        self.user1.refresh_from_db()
        self.assertTrue(self.superuser.is_active)
        self.assertTrue(self.user1.is_active)

    def test_freeze_deletes_active_sessions(self):
        """Aktive sesjoner for fryste brukere skal slettes."""
        # Lag en aktiv session som tilhører user1
        session = SessionStore()
        session['_auth_user_id'] = str(self.user1.pk)
        session.save()
        self.assertTrue(Session.objects.filter(session_key=session.session_key).exists())

        req = self._request()
        qs = CustomUser.objects.filter(pk=self.user1.pk)
        self.admin.freeze_users(req, qs)

        self.assertFalse(Session.objects.filter(session_key=session.session_key).exists())

    def test_freeze_does_not_touch_other_sessions(self):
        """Sesjoner som tilhører andre brukere skal ikke berøres."""
        session_other = SessionStore()
        session_other['_auth_user_id'] = str(self.superuser.pk)
        session_other.save()

        req = self._request()
        qs = CustomUser.objects.filter(pk=self.user1.pk)
        self.admin.freeze_users(req, qs)

        # Superusers sesjon skal være intakt
        self.assertTrue(Session.objects.filter(session_key=session_other.session_key).exists())

    def test_thaw_reactivates_users(self):
        """Tine-actionen skal reaktivere kontoer."""
        self.user1.is_active = False
        self.user1.save()
        self.user2.is_active = False
        self.user2.save()

        req = self._request()
        qs = CustomUser.objects.filter(pk__in=[self.user1.pk, self.user2.pk])
        self.admin.thaw_users(req, qs)

        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        self.assertTrue(self.user1.is_active)
        self.assertTrue(self.user2.is_active)

    def test_frozen_user_cannot_login(self):
        """End-to-end: frossen bruker skal ikke kunne logge inn."""
        req = self._request()
        qs = CustomUser.objects.filter(pk=self.user1.pk)
        self.admin.freeze_users(req, qs)

        client = Client()
        resp = client.post('/accounts/login/', {
            'username': 'alice', 'password': 'Test1234!',
        })
        # Skal IKKE bli redirect til index/dashboard – frossen bruker avvises
        self.user1.refresh_from_db()
        self.assertFalse(self.user1.is_active)
        # Login feiler: enten 200 (re-render skjema) eller 401/403
        # Hovedsaken: ikke 302 til pasient-listen
        if resp.status_code == 302:
            self.assertNotIn('/patients', resp.url)
            self.assertNotIn('/index', resp.url)


# ════════════════════════════════════════════════════════════════════════════
# Fase 3b: Bulk-aksjoner og permission-redigering
# ════════════════════════════════════════════════════════════════════════════


@override_settings(SECURE_SSL_REDIRECT=False)
class BulkPermissionActionsTests(TestCase):
    """Tester bulk-aksjoner for pasient-permissions på user_list_view."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='bulk_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        self.lead = CustomUser.objects.create_user(
            username='bulk_lead', password='x', role='lead',
            must_change_password=False,
            kan_redigere_pasienter=False,
        )
        self.lead_view = CustomUser.objects.create_user(
            username='bulk_lead_view', password='x', role='lead_view',
            must_change_password=False,
            kan_redigere_pasienter=False,
        )
        self.read_only = CustomUser.objects.create_user(
            username='bulk_ro', password='x', role='read_only',
            must_change_password=False,
            kan_redigere_pasienter=True,
        )
        self.client.force_login(self.admin)

    def test_grant_pasienter_to_leads_setter_flag_paa_alle_leder(self):
        resp = self.client.post(
            reverse('accounts:user_list'),
            {'action': 'grant_pasienter_to_leads'},
        )
        self.assertEqual(resp.status_code, 302)
        self.lead.refresh_from_db()
        self.lead_view.refresh_from_db()
        self.read_only.refresh_from_db()
        self.assertTrue(self.lead.kan_redigere_pasienter)
        self.assertTrue(self.lead_view.kan_redigere_pasienter)
        # Read-only-brukere skal IKKE påvirkes av grant-aksjonen
        self.assertTrue(self.read_only.kan_redigere_pasienter)

    def test_revoke_pasienter_from_all_skipper_admin(self):
        # Sett admin-flagget for å bekrefte at den ikke endres
        self.admin.kan_redigere_pasienter = True
        self.admin.save(update_fields=['kan_redigere_pasienter'])

        resp = self.client.post(
            reverse('accounts:user_list'),
            {'action': 'revoke_pasienter_from_all'},
        )
        self.assertEqual(resp.status_code, 302)
        self.admin.refresh_from_db()
        self.read_only.refresh_from_db()
        self.assertTrue(self.admin.kan_redigere_pasienter,
                        'Admin skal ikke få fjernet flagget')
        self.assertFalse(self.read_only.kan_redigere_pasienter,
                         'Read-only skal få fjernet flagget')

    def test_grant_er_idempotent(self):
        """Kjøres aksjonen to ganger skal resultatet være det samme."""
        for _ in range(2):
            self.client.post(
                reverse('accounts:user_list'),
                {'action': 'grant_pasienter_to_leads'},
            )
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.kan_redigere_pasienter)

    def test_bulk_aksjon_kun_admin(self):
        """Read-only skal ikke kunne kjøre bulk-aksjon."""
        self.client.force_login(self.read_only)
        resp = self.client.post(
            reverse('accounts:user_list'),
            {'action': 'grant_pasienter_to_leads'},
        )
        # Ikke 302 til user_list — admin_required skal blokkere
        # (typisk 302 til /-redirect eller 403)
        self.assertIn(resp.status_code, (302, 403))
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.kan_redigere_pasienter)

    def test_bulk_knapper_synlige_paa_user_list(self):
        resp = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'grant_pasienter_to_leads')
        self.assertContains(resp, 'revoke_pasienter_from_all')


@override_settings(SECURE_SSL_REDIRECT=False)
class ModulTilgangMatriseTests(TestCase):
    """Matrisen modul x nivaa erstattet de fem avkrysningsboksene.

    Boksene styrte kun meny og dashboard, aldri et endepunkt. Etter at
    synligheten begynte aa lese `ModulTilgang`, gjorde de ingenting i det hele
    tatt - og en boks som ikke gjoer noe er verre enn ingen boks.
    """

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='edit_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        self.target = CustomUser.objects.create_user(
            username='edit_target', password='x', role='read_only',
            must_change_password=False,
        )
        self.client.force_login(self.admin)

    def _detalj(self):
        return reverse('accounts:user_detail', kwargs={'pk': self.target.pk})

    def test_matrisen_genereres_fra_registeret(self):
        """Ikke en hardkodet liste: nye moduler skal dukke opp av seg selv."""
        from accounts.forms import ModulTilgangForm
        from core.modules import get_all_modules

        felter = set(ModulTilgangForm().fields)
        forventet = {f'modul_{m.slug}' for m in get_all_modules() if not m.admin_only}
        self.assertEqual(felter, forventet)

    def test_admin_only_moduler_er_utelatt(self):
        from accounts.forms import ModulTilgangForm
        felter = ModulTilgangForm().fields
        self.assertNotIn('modul_accounts', felter)
        self.assertNotIn('modul_core', felter)

    def test_tomt_nivaa_tilbys_ikke_i_grensesnittet(self):
        """`skriv_handling` finnes i modellen, men gir ingenting ennaa.

        Et nivaa som ikke gjoer noe er lett aa dele ut i god tro, og gir
        automatisk mer den dagen det fylles. Tilbys naar en modul har et
        handling-endepunkt aa bruke det paa (par. 3.2).
        """
        from accounts.forms import ModulTilgangForm
        valg = dict(ModulTilgangForm().fields['modul_patients'].choices)
        self.assertNotIn('skriv_handling', valg)
        self.assertIn('les', valg)
        self.assertIn('skriv_full', valg)

    def test_redigering_skriver_radene(self):
        resp = self.client.post(self._detalj(), {
            'action': 'edit', 'role': 'read_only', 'is_active': 'on',
            'modul_patients': 'skriv_full', 'modul_statistikk': 'les',
        })
        self.assertEqual(resp.status_code, 302)
        rader = dict(ModulTilgang.objects.filter(bruker=self.target)
                     .values_list('modul_slug', 'nivaa'))
        self.assertEqual(rader, {'patients': 'skriv_full', 'statistikk': 'les'})

    def test_ingen_tilgang_sletter_raden(self):
        """Fravaer av rad *er* ingen tilgang - ingen 'ingen'-verdi lagres."""
        ModulTilgang.objects.create(
            bruker=self.target, modul_slug='patients', nivaa='les')
        self.client.post(self._detalj(), {
            'action': 'edit', 'role': 'read_only', 'is_active': 'on',
            'modul_patients': '', 'modul_statistikk': '',
        })
        self.assertFalse(ModulTilgang.objects.filter(bruker=self.target).exists())

    def test_endring_auditeres_per_modul(self):
        from audit.models import AuditLog
        self.client.post(self._detalj(), {
            'action': 'edit', 'role': 'read_only', 'is_active': 'on',
            'modul_patients': 'skriv_full',
        })
        rader = AuditLog.objects.filter(table_name='accounts_modultilgang')
        self.assertEqual(rader.count(), 1)
        rad = rader.first()
        self.assertEqual(rad.field_name, 'patients')
        self.assertEqual(rad.old_value, 'ingen')
        self.assertEqual(rad.new_value, 'skriv_full')
        self.assertEqual(rad.app_label, 'accounts')

    def test_rolleendring_auditeres(self):
        """Frysing og sletting ble logget; det aa gi noen admin ble ikke."""
        from audit.models import AuditLog
        self.client.post(self._detalj(), {
            'action': 'edit', 'role': 'admin', 'is_active': 'on',
        })
        rad = AuditLog.objects.filter(
            table_name='accounts_customuser', field_name='role').first()
        self.assertIsNotNone(rad, 'rolleendring skal loggfoeres')
        self.assertEqual(rad.old_value, 'read_only')
        self.assertEqual(rad.new_value, 'admin')

    def test_uendret_matrise_gir_ingen_auditrader(self):
        from audit.models import AuditLog
        ModulTilgang.objects.create(
            bruker=self.target, modul_slug='patients', nivaa='les')
        self.client.post(self._detalj(), {
            'action': 'edit', 'role': 'read_only', 'is_active': 'on',
            'modul_patients': 'les', 'modul_statistikk': '',
        })
        self.assertEqual(
            AuditLog.objects.filter(table_name='accounts_modultilgang').count(), 0)

    def test_matrisen_vises_paa_detaljsiden(self):
        resp = self.client.get(self._detalj())
        self.assertContains(resp, 'name="modul_patients"')
        self.assertContains(resp, 'name="modul_statistikk"')

    def test_matrisen_vises_paa_opprettingsskjemaet(self):
        """Par. 10.3: uten den lander den nyinviterte i en tom portal."""
        resp = self.client.get(reverse('accounts:user_create'))
        self.assertContains(resp, 'name="modul_patients"')

    def test_ny_bruker_far_tilgangen_med_en_gang(self):
        self.client.post(reverse('accounts:user_create'), {
            'username': 'ny_med_tilgang', 'role': 'read_write',
            'metode': 'midlertidig', 'modul_patients': 'skriv_full',
        })
        ny = CustomUser.objects.get(username='ny_med_tilgang')
        self.assertEqual(
            list(ModulTilgang.objects.filter(bruker=ny)
                 .values_list('modul_slug', 'nivaa')),
            [('patients', 'skriv_full')],
        )
