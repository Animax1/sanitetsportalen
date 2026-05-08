"""Tester for core-appens primitiver.

Dekker:
1.  Tids-validatorer (validate_time_string, validate_patient_time_fields, parse_minutes)
2.  Lokal-tid-helper (now_local_str)
3.  Rolle-hierarki (has_role_at_least)
4.  Bakoverkompatibilitet: at re-eksporter fra patients.services og
    accounts.decorators fortsatt fungerer slik at eksisterende kode
    ikke brekker.
5.  Portal-skall (Fase 2): dashboard-view, legacy-redirects fra gamle
    root-URL-er, og at navigasjonen i base_portal.html peker på riktig.
"""
from datetime import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone as djtz

from core.auth_decorators import (
    ROLE_HIERARKI,
    admin_required,
    has_role_at_least,
    role_required,
    stats_required,
    write_required,
)
from core.validators import (
    TIME_FIELDS,
    TIME_FORMAT,
    TIME_FORMAT_HUMAN,
    now_local_str,
    parse_minutes,
    validate_patient_time_fields,
    validate_time_string,
)


# ════════════════════════════════════════════════════════════════════════════
# Tids-validator-tester
# ════════════════════════════════════════════════════════════════════════════


class ValidateTimeStringTests(TestCase):
    """Verifiserer at validate_time_string aksepterer kun dd.mm.åååå tt:mm."""

    def test_gyldig_tid_godkjennes(self):
        self.assertEqual(validate_time_string('19.04.2026 14:30'), '19.04.2026 14:30')

    def test_tom_streng_returnerer_tom(self):
        self.assertEqual(validate_time_string(''), '')

    def test_none_returnerer_tom(self):
        self.assertEqual(validate_time_string(None), '')

    def test_whitespace_trimmes(self):
        self.assertEqual(validate_time_string('  19.04.2026 14:30  '), '19.04.2026 14:30')

    def test_iso_format_avvises(self):
        with self.assertRaises(ValidationError):
            validate_time_string('2026-04-19T14:30')

    def test_dato_uten_tid_avvises(self):
        with self.assertRaises(ValidationError):
            validate_time_string('19.04.2026')

    def test_ugyldig_dato_avvises(self):
        # Riktig format men 32. april finnes ikke
        with self.assertRaises(ValidationError):
            validate_time_string('32.04.2026 14:30')

    def test_ugyldig_time_avvises(self):
        with self.assertRaises(ValidationError):
            validate_time_string('19.04.2026 25:30')

    def test_field_name_inkluderes_i_feilmelding(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_time_string('xx', field_name='inntid')
        self.assertIn('inntid', str(ctx.exception))


class ValidatePatientTimeFieldsTests(TestCase):
    """Verifiserer at validate_patient_time_fields validerer alle TIME_FIELDS."""

    def test_alle_kjente_felter_valideres(self):
        data = {
            'inntid': '19.04.2026 14:30',
            'pabegynt': '19.04.2026 14:35',
            'inn_obspost': '',
            'ut_obspost': None,
            'utskrevet': '19.04.2026 16:00',
            'annet': 'urørt',
        }
        result = validate_patient_time_fields(data)
        self.assertEqual(result['inntid'], '19.04.2026 14:30')
        self.assertEqual(result['inn_obspost'], '')
        self.assertEqual(result['ut_obspost'], '')
        self.assertEqual(result['annet'], 'urørt')  # ikke et tidsfelt → ikke rørt

    def test_ugyldig_felt_kaster(self):
        data = {'inntid': '2026-04-19'}
        with self.assertRaises(ValidationError):
            validate_patient_time_fields(data)

    def test_alle_kjente_tidsfelter_definert(self):
        forventede = {'inntid', 'pabegynt', 'inn_obspost', 'ut_obspost', 'utskrevet'}
        self.assertEqual(set(TIME_FIELDS), forventede)


class ParseMinutesTests(TestCase):
    """Verifiserer parse_minutes for de tre aksepterte tidsformatene."""

    def test_norsk_format_30_min(self):
        self.assertEqual(
            parse_minutes('19.04.2026 14:00', '19.04.2026 14:30'),
            30,
        )

    def test_iso_t_format(self):
        self.assertEqual(
            parse_minutes('2026-04-19T14:00', '2026-04-19T14:30'),
            30,
        )

    def test_iso_space_format(self):
        self.assertEqual(
            parse_minutes('2026-04-19 14:00', '2026-04-19 14:30'),
            30,
        )

    def test_negativ_differanse_returnerer_none(self):
        self.assertIsNone(
            parse_minutes('19.04.2026 14:30', '19.04.2026 14:00'),
        )

    def test_for_stor_differanse_returnerer_none(self):
        # Mer enn 48 timer → None (urimelig vakttid)
        self.assertIsNone(
            parse_minutes('19.04.2026 00:00', '22.04.2026 00:00'),
        )

    def test_ugyldig_input_returnerer_none(self):
        self.assertIsNone(parse_minutes('tull', 'tull'))


# ════════════════════════════════════════════════════════════════════════════
# Lokal-tid-helper
# ════════════════════════════════════════════════════════════════════════════


class NowLocalStrTests(TestCase):
    """now_local_str skal alltid returnere streng i dd.mm.YYYY HH:MM-format."""

    def test_format_er_riktig(self):
        result = now_local_str()
        # Skal kunne re-parses som TIME_FORMAT
        parsed = datetime.strptime(result, TIME_FORMAT)
        self.assertIsInstance(parsed, datetime)

    @override_settings(TIME_ZONE='Europe/Oslo', USE_TZ=True)
    def test_bruker_djangos_timezone(self):
        # Med Europe/Oslo skal lokal-tid være 1-2 timer foran UTC
        # (avhengig av sommertid). Vi sjekker bare at vi får et gyldig
        # streng-resultat — eksakt verdi er tids-avhengig.
        result = now_local_str()
        self.assertRegex(result, r'^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$')


# ════════════════════════════════════════════════════════════════════════════
# Rolle-hierarki og has_role_at_least
# ════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    """Test-helper — etterligner CustomUser uten å trekke inn DB-modeller."""
    def __init__(self, role=None, authenticated=True):
        self.role = role
        self.is_authenticated = authenticated


class HasRoleAtLeastTests(TestCase):
    """Verifiserer at rolle-hierarkiet brukes konsistent."""

    def test_admin_har_alle_niveaer(self):
        admin = _FakeUser(role='admin')
        for nivå in ROLE_HIERARKI:
            self.assertTrue(
                has_role_at_least(admin, nivå),
                f'admin skal ha tilgang til {nivå}',
            )

    def test_read_only_har_kun_eget_nivaa(self):
        ro = _FakeUser(role='read_only')
        self.assertTrue(has_role_at_least(ro, 'read_only'))
        self.assertFalse(has_role_at_least(ro, 'read_write'))
        self.assertFalse(has_role_at_least(ro, 'lead_view'))
        self.assertFalse(has_role_at_least(ro, 'lead'))
        self.assertFalse(has_role_at_least(ro, 'admin'))

    def test_lead_view_har_lavere_men_ikke_lead(self):
        lv = _FakeUser(role='lead_view')
        self.assertTrue(has_role_at_least(lv, 'read_only'))
        self.assertTrue(has_role_at_least(lv, 'read_write'))
        self.assertTrue(has_role_at_least(lv, 'lead_view'))
        self.assertFalse(has_role_at_least(lv, 'lead'))
        self.assertFalse(has_role_at_least(lv, 'admin'))

    def test_uautentisert_returnerer_false(self):
        anon = _FakeUser(role=None, authenticated=False)
        self.assertFalse(has_role_at_least(anon, 'read_only'))

    def test_ukjent_rolle_returnerer_false(self):
        ukjent = _FakeUser(role='superduperadmin')
        self.assertFalse(has_role_at_least(ukjent, 'read_only'))

    def test_hierarki_har_5_niveaer(self):
        self.assertEqual(len(ROLE_HIERARKI), 5)
        forventede = {'read_only', 'read_write', 'lead_view', 'lead', 'admin'}
        self.assertEqual(set(ROLE_HIERARKI), forventede)


class RoleRequiredDecoratorTests(TestCase):
    """Verifiserer at role_required-dekoratoren krever riktig rolle."""

    def test_admin_required_er_role_required_admin(self):
        # admin_required skal være ekvivalent med role_required('admin')
        # Vi kan ikke sammenligne lukninger direkte, men vi kan sjekke
        # at den finnes og er kallbar.
        self.assertTrue(callable(admin_required))
        self.assertTrue(callable(write_required))
        self.assertTrue(callable(stats_required))


# ════════════════════════════════════════════════════════════════════════════
# Bakoverkompatibilitet: re-eksporter fra patients.services og accounts.decorators
# ════════════════════════════════════════════════════════════════════════════


class BakoverkompatibilitetTests(TestCase):
    """Sikrer at all eksisterende import fortsatt fungerer etter refaktoren."""

    def test_patients_services_re_eksporterer_validatorer(self):
        from patients.services import (  # noqa: F401
            TIME_FIELDS as p_fields,
            TIME_FORMAT as p_format,
            now_local_str as p_now,
            parse_minutes as p_parse,
            validate_patient_time_fields as p_val,
            validate_time_string as p_str,
        )
        # Skal være de samme objektene som i core
        self.assertIs(p_fields, TIME_FIELDS)
        self.assertIs(p_format, TIME_FORMAT)
        self.assertIs(p_now, now_local_str)
        self.assertIs(p_parse, parse_minutes)
        self.assertIs(p_val, validate_patient_time_fields)
        self.assertIs(p_str, validate_time_string)

    def test_patients_services_re_eksporterer_rolle(self):
        from patients.services import (  # noqa: F401
            ROLE_HIERARKI as p_hierarki,
            has_role_at_least as p_has,
        )
        self.assertIs(p_hierarki, ROLE_HIERARKI)
        self.assertIs(p_has, has_role_at_least)

    def test_accounts_decorators_re_eksporterer(self):
        from accounts.decorators import (  # noqa: F401
            admin_required as a_admin,
            role_required as a_role,
            stats_required as a_stats,
            write_required as a_write,
        )
        self.assertIs(a_admin, admin_required)
        self.assertIs(a_role, role_required)
        self.assertIs(a_stats, stats_required)
        self.assertIs(a_write, write_required)

    def test_arkiv_konstanter_uendret(self):
        """ARKIV_VIEW_MIN_ROLE og ARKIV_WRITE_ROLE skal være uendret."""
        from patients.services import ARKIV_VIEW_MIN_ROLE, ARKIV_WRITE_ROLE
        self.assertEqual(ARKIV_VIEW_MIN_ROLE, 'admin')
        self.assertEqual(ARKIV_WRITE_ROLE, 'admin')


# ═══════════════════════════════════════════════════════════════════════════
# Fase 2: Portal-dashboard
# ═══════════════════════════════════════════════════════════════════════════


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class PortalDashboardViewTests(TestCase):
    """Verifiserer at portal-dashboardet ligger på / og krever innlogging."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='dashbruker', password='x', role='read_only',
            must_change_password=False,
        )
        self.client = Client()

    def test_dashboard_url_loeses(self):
        """`core:portal_dashboard` skal løse til /."""
        self.assertEqual(reverse('core:portal_dashboard'), '/')

    def test_uautentisert_redirectes_til_login(self):
        """Anonyme brukere blir sendt til login."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login', resp['Location'])

    def test_innlogget_bruker_ser_dashboard(self):
        """Innlogget bruker får dashbordet (200)."""
        self.client.force_login(self.user)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        # Skal inneholde modulkortet for pasientregistrering
        self.assertContains(resp, 'Pasientregistrering')
        self.assertContains(resp, 'href="/pasienter/"')

    def test_dashboard_inneholder_portal_navigasjon(self):
        """Dashbordet skal vise portal-meny med Dashboard og Pasienter."""
        self.client.force_login(self.user)
        resp = self.client.get('/')
        # Brand-lenke til dashboard
        self.assertContains(resp, 'Sanitetsportal')
        # Modul-meny — sjekker nøkkelinnhold (HTML har whitespace mellom
        # ikon og tekst, så vi sjekker bare at navnene finnes i nav-en)
        self.assertContains(resp, 'class="portal-nav"')
        self.assertContains(resp, 'Dashboard')
        self.assertContains(resp, 'Pasienter')

    def test_dashboard_velkomst_inkluderer_brukernavn(self):
        """Hero-seksjonen skal hilse på brukeren med brukernavn."""
        self.client.force_login(self.user)
        resp = self.client.get('/')
        self.assertContains(resp, 'Velkommen, dashbruker')

    def test_dashboard_kun_GET_tillatt(self):
        """POST/PUT/DELETE skal gi 405."""
        self.client.force_login(self.user)
        resp = self.client.post('/')
        self.assertEqual(resp.status_code, 405)

    def test_admin_ser_admin_lenker_i_meny(self):
        """Admin skal se Server-status og Django-admin i portal-meny."""
        admin = User.objects.create_superuser(
            username='superadm', password='x', role='admin',
        )
        self.client.force_login(admin)
        resp = self.client.get('/')
        self.assertContains(resp, 'Server-status')
        self.assertContains(resp, 'Django-admin')

    def test_read_only_ser_ikke_admin_lenker(self):
        """Vanlig bruker skal IKKE se admin-lenker."""
        self.client.force_login(self.user)
        resp = self.client.get('/')
        self.assertNotContains(resp, 'Server-status')
        self.assertNotContains(resp, 'Django-admin')


# ═══════════════════════════════════════════════════════════════════════════
# Fase 2: Legacy-redirects fra gamle root-URL-er
# ═══════════════════════════════════════════════════════════════════════════


@override_settings(SECURE_SSL_REDIRECT=False)
class LegacyRedirectTests(TestCase):
    """Verifiserer at gamle root-URL-er gir 301 til /pasienter/-versjonen.

    I Fase 2 flyttet vi pasient-modulen fra `/` til `/pasienter/`. Gamle
    bokmerker, lenker og e-post-referanser må fortsatt fungere via 301.
    """

    def test_api_patients_redirectes(self):
        """/api/patients/ → 301 → /pasienter/api/patients/"""
        resp = self.client.get('/api/patients/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], '/pasienter/api/patients/')

    def test_api_full_stats_redirectes(self):
        resp = self.client.get('/api/full-stats/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], '/pasienter/api/full-stats/')

    def test_api_med_pk_redirectes(self):
        resp = self.client.get('/api/patients/42/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], '/pasienter/api/patients/42/')

    def test_api_med_query_string_bevares(self):
        """Query string skal bevares i redirect."""
        resp = self.client.get('/api/patients/?foo=bar&baz=2')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(
            resp['Location'],
            '/pasienter/api/patients/?foo=bar&baz=2',
        )

    def test_api_arkiv_redirectes(self):
        resp = self.client.get('/api/innstillinger/arkiv/5/full-stats/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(
            resp['Location'],
            '/pasienter/api/innstillinger/arkiv/5/full-stats/',
        )

    def test_admin_server_status_redirectes(self):
        """/admin/server-status/ → 301 → /pasienter/admin/server-status/"""
        resp = self.client.get('/admin/server-status/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(
            resp['Location'],
            '/pasienter/admin/server-status/',
        )

    def test_admin_server_status_subpath_redirectes(self):
        resp = self.client.get('/admin/server-status/json/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(
            resp['Location'],
            '/pasienter/admin/server-status/json/',
        )

    def test_django_admin_paavirkes_ikke(self):
        """/django-admin/ skal IKKE bli redirected (det er Django-admin selv)."""
        resp = self.client.get('/django-admin/')
        # Django-admin redirecter selv til login (302), ikke 301 fra core.
        self.assertNotEqual(resp.status_code, 301)

    def test_healthz_paavirkes_ikke(self):
        """/healthz/ skal forbli aktiv på root, ikke redirected."""
        resp = self.client.get('/healthz/')
        # healthz returnerer enten 200 eller 503 — aldri 301.
        self.assertNotEqual(resp.status_code, 301)
        self.assertIn(resp.status_code, [200, 503])

    def test_accounts_paavirkes_ikke(self):
        """/accounts/login/ skal forbli på root."""
        resp = self.client.get('/accounts/login/')
        # accounts/login returnerer 200 (loginskjema), ikke 301.
        self.assertNotEqual(resp.status_code, 301)

    def test_redirect_er_permanent_301_ikke_302(self):
        """Bekrefter eksplisitt 301 (Moved Permanently), ikke 302 (Found).

        Forskjellen er kritisk: 301 cacher i nettleseren og oppdaterer
        bokmerker; 302 gjør ikke det.
        """
        resp = self.client.get('/api/patients/')
        self.assertEqual(resp.status_code, 301)
        # Django setter kun status — ingen Cache-Control-header trengs.

    def test_post_til_legacy_redirectes_med_307_kompatibel(self):
        """POST til legacy-URL skal også redirecte (HttpResponsePermanentRedirect).

        Django bruker 308 for POST-redirect via HttpResponsePermanentRedirect
        i nyere versjoner — men i dag returnerer den 301 selv for POST. Vi
        sjekker bare at det IKKE er 200 (ingen åpen ende) og at klient
        kommer seg videre til /pasienter/.
        """
        # Bruker en URL som finnes både på gammel og ny path.
        resp = self.client.post('/api/patients/', data='{}',
                                content_type='application/json')
        self.assertIn(resp.status_code, [301, 308])
        self.assertTrue(resp['Location'].startswith('/pasienter/api/patients/'))


# ═══════════════════════════════════════════════════════════════════════════
# Fase 2: Pasient-app fortsatt funksjonell på ny URL
# ═══════════════════════════════════════════════════════════════════════════


@override_settings(SECURE_SSL_REDIRECT=False)
class PasientAppPaaNyURLTests(TestCase):
    """Sanity-tester: pasient-app fungerer fra /pasienter/-prefiks."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='paspruker', password='x', role='read_only',
            must_change_password=False,
        )
        self.client.force_login(self.user)

    def test_pasient_index_paa_ny_url(self):
        """GET /pasienter/ skal rendre pasient-index."""
        resp = self.client.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pasientregistrering')

    def test_pasient_api_paa_ny_url(self):
        """GET /pasienter/api/patients/ skal returnere JSON-liste."""
        from patients.services import set_active_year
        set_active_year(2026)
        resp = self.client.get('/pasienter/api/patients/')
        self.assertEqual(resp.status_code, 200)

    def test_url_navn_for_index_loeses_riktig(self):
        """reverse('index') skal nå gi /pasienter/."""
        from django.urls import reverse as r
        self.assertEqual(r('index'), '/pasienter/')

    def test_url_navn_for_api_løses_riktig(self):
        """reverse('api_patients_list') skal nå gi /pasienter/api/patients/."""
        from django.urls import reverse as r
        self.assertEqual(r('api_patients_list'), '/pasienter/api/patients/')

    def test_url_navn_for_admin_status_loeses_riktig(self):
        """reverse('admin_server_status') skal nå gi /pasienter/admin/server-status/."""
        from django.urls import reverse as r
        self.assertEqual(
            r('admin_server_status'),
            '/pasienter/admin/server-status/',
        )
