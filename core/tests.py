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
        # Bruker med kan_redigere_pasienter=True slik at pasient-modulen vises.
        # (Fase 3a la til permission-flagg som default er False; tester som
        # forventer modulen synlig må sette flagget eksplisitt.)
        self.user = User.objects.create_user(
            username='dashbruker', password='x', role='read_only',
            must_change_password=False,
            kan_redigere_pasienter=True,
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
        """Dashbordet skal vise portal-meny med Dashboard og Pasientregistrering."""
        self.client.force_login(self.user)
        resp = self.client.get('/')
        # Brand-lenke til dashboard
        self.assertContains(resp, 'Sanitetsportal')
        # Modul-meny — sjekker nøkkelinnhold (HTML har whitespace mellom
        # ikon og tekst, så vi sjekker bare at navnene finnes i nav-en)
        self.assertContains(resp, 'class="portal-nav"')
        self.assertContains(resp, 'Dashboard')
        self.assertContains(resp, 'Pasientregistrering')

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

    def test_pasient_index_har_synlig_portal_knapp(self):
        """Pasient-app header skal ha en synlig 'Portal'-knapp som lenker til /."""
        resp = self.client.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        # Synlig knapp i header med klassen portal-back-btn
        self.assertContains(resp, 'class="portal-back-btn"')
        # Knappen skal lenke til portal-roten
        self.assertContains(resp, 'href="/" class="portal-back-btn"')
        # Knappen skal ha tekst-label 'Portal'
        self.assertContains(resp, 'portal-back-label')


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminNavPortalLenkeTests(TestCase):
    """Verifiserer at admin-nav (base.html) viser 'Portal' i stedet for 'Pasientliste'."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='nav_admin', password='x', role='admin',
            must_change_password=False,
        )
        self.client.force_login(self.admin)

    def test_endre_passord_har_portal_lenke(self):
        """Endre-passord-siden skal ha 'Portal'-lenke i admin-nav, ikke 'Pasientliste'."""
        resp = self.client.get('/accounts/change-password/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '>Portal</a>')
        self.assertNotContains(resp, '>Pasientliste</a>')

    def test_brukere_har_portal_lenke(self):
        """Brukere-siden skal ha 'Portal'-lenke i admin-nav, ikke 'Pasientliste'."""
        resp = self.client.get('/accounts/users/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '>Portal</a>')
        self.assertNotContains(resp, '>Pasientliste</a>')

    def test_server_status_har_portal_lenke(self):
        """Server-status-siden skal ha 'Portal'-lenke i admin-nav, ikke 'Pasientliste'."""
        resp = self.client.get('/pasienter/admin/server-status/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '>Portal</a>')
        self.assertNotContains(resp, '>Pasientliste</a>')


# ════════════════════════════════════════════════════════════════════════════
# Fase 3a: Modul-registry, ModuleSettings, permissions, AuditLog app_label
# ════════════════════════════════════════════════════════════════════════════


from core.models import ModuleSettings
from core.modules import (
    Module,
    get_all_modules,
    get_dashboard_modules,
    get_module,
    get_nav_modules,
    get_visible_modules,
    reset_registry_cache,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class ModuleRegistryTests(TestCase):
    """Verifiserer at modul-registret er konsistent og inneholder forventede moduler."""

    def setUp(self):
        reset_registry_cache()

    def test_alle_registrerte_moduler_har_unik_slug(self):
        slugs = [m.slug for m in get_all_modules()]
        self.assertEqual(len(slugs), len(set(slugs)),
                         f'Duplikate slugs i registret: {slugs}')

    def test_patients_modul_er_registrert(self):
        modul = get_module('patients')
        self.assertIsNotNone(modul)
        self.assertEqual(modul.slug, 'patients')
        self.assertEqual(modul.permission_flag, 'kan_redigere_pasienter')
        self.assertFalse(modul.is_core)
        self.assertTrue(modul.show_in_dashboard)

    def test_core_og_accounts_er_kjernemoduler(self):
        for slug in ('core', 'accounts'):
            modul = get_module(slug)
            self.assertIsNotNone(modul, f'{slug} mangler i registret')
            self.assertTrue(modul.is_core, f'{slug} skal være is_core=True')
            self.assertFalse(modul.show_in_dashboard,
                             f'{slug} skal ikke vises på dashboardet')

    def test_get_module_med_ukjent_slug_returnerer_none(self):
        self.assertIsNone(get_module('finnes-ikke'))

    def test_modul_sortering_etter_order(self):
        moduler = list(get_all_modules())
        orders = [m.order for m in moduler]
        self.assertEqual(orders, sorted(orders),
                         'Moduler skal være sortert etter order')


@override_settings(SECURE_SSL_REDIRECT=False)
class ModuleVisibilityTests(TestCase):
    """Verifiserer permission-styring for modul-synlighet."""

    def setUp(self):
        reset_registry_cache()
        ModuleSettings.ensure_defaults_exist()

    def test_uautentisert_bruker_ser_ingen_moduler(self):
        self.assertEqual(get_dashboard_modules(None), [])

    def test_admin_ser_alle_dashboard_moduler(self):
        admin = User.objects.create_user(
            username='vis_admin', password='x', role='admin',
            must_change_password=False,
        )
        moduler = get_dashboard_modules(admin)
        slugs = {m.slug for m in moduler}
        # Admin skal i hvert fall se patients-modulen.
        self.assertIn('patients', slugs)

    def test_bruker_uten_kan_redigere_pasienter_ser_ikke_patients(self):
        bruker = User.objects.create_user(
            username='no_pas', password='x', role='read_only',
            must_change_password=False,
        )
        # Default for nye brukere er kan_redigere_pasienter=False.
        self.assertFalse(bruker.kan_redigere_pasienter)
        slugs = {m.slug for m in get_dashboard_modules(bruker)}
        self.assertNotIn('patients', slugs)

    def test_bruker_med_kan_redigere_pasienter_ser_patients(self):
        bruker = User.objects.create_user(
            username='ja_pas', password='x', role='read_only',
            must_change_password=False,
        )
        bruker.kan_redigere_pasienter = True
        bruker.save(update_fields=['kan_redigere_pasienter'])
        slugs = {m.slug for m in get_dashboard_modules(bruker)}
        self.assertIn('patients', slugs)

    def test_deaktivert_modul_skjules_for_ikke_admin(self):
        bruker = User.objects.create_user(
            username='ja_pas2', password='x', role='read_only',
            must_change_password=False,
            kan_redigere_pasienter=True,
        )
        # Deaktiver patients i ModuleSettings.
        ms, _ = ModuleSettings.objects.get_or_create(slug='patients')
        ms.enabled = False
        ms.save()

        slugs = {m.slug for m in get_dashboard_modules(bruker)}
        self.assertNotIn('patients', slugs,
                         'Deaktiverte moduler skal ikke vises i dashboard')

    def test_kjernemodul_synlig_selv_om_modulesettings_deaktivert(self):
        """Kjernemoduler skal IKKE kunne skjules via ModuleSettings.enabled.

        Dette er en defensiv test: get_visible_modules har en eksplisitt
        is_core-bypass slik at en feilkonfigurasjon ikke kan låse ute admin.
        """
        admin = User.objects.create_user(
            username='kjerne_admin', password='x', role='admin',
            must_change_password=False,
        )
        # Forsøk å deaktivere accounts (kjernemodul) — selv om admin-UI hindrer
        # dette, kan en SQL-redigering av ModuleSettings gjøre det. Vi tester
        # at koden er robust likevel.
        ms, _ = ModuleSettings.objects.get_or_create(slug='accounts')
        ms.enabled = False
        ms.save()

        synlige = get_visible_modules(admin, only_enabled=True)
        slugs = {m.slug for m in synlige}
        self.assertIn('accounts', slugs)


@override_settings(SECURE_SSL_REDIRECT=False)
class ModuleSettingsModelTests(TestCase):
    """Verifiserer ModuleSettings-modellen og ensure_defaults_exist."""

    def test_ensure_defaults_oppretter_rad_for_hver_modul(self):
        # Slett alle rader og kjør på nytt — skal være idempotent.
        ModuleSettings.objects.all().delete()
        ModuleSettings.ensure_defaults_exist()

        slugs_i_db = set(ModuleSettings.objects.values_list('slug', flat=True))
        slugs_i_registry = {m.slug for m in get_all_modules()}
        self.assertEqual(slugs_i_db, slugs_i_registry)

    def test_ensure_defaults_er_idempotent(self):
        ModuleSettings.ensure_defaults_exist()
        antall_for = ModuleSettings.objects.count()
        ModuleSettings.ensure_defaults_exist()
        self.assertEqual(ModuleSettings.objects.count(), antall_for)

    def test_get_enabled_slugs_returnerer_kun_aktive(self):
        ModuleSettings.ensure_defaults_exist()
        # Deaktiver patients
        ModuleSettings.objects.filter(slug='patients').update(enabled=False)
        aktive = ModuleSettings.get_enabled_slugs()
        self.assertNotIn('patients', aktive)
        self.assertIn('core', aktive)

    def test_str_representasjon(self):
        ms = ModuleSettings(slug='testmodul', enabled=True)
        self.assertEqual(str(ms), 'testmodul (aktiv)')
        ms.enabled = False
        self.assertEqual(str(ms), 'testmodul (deaktivert)')


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardRendringTests(TestCase):
    """End-to-end: dashboard rendrer riktige modul-kort basert på permissions."""

    def setUp(self):
        reset_registry_cache()
        ModuleSettings.ensure_defaults_exist()

    def test_admin_ser_pasient_kort(self):
        admin = User.objects.create_user(
            username='dash_admin', password='x', role='admin',
            must_change_password=False,
        )
        self.client.force_login(admin)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pasientregistrering')
        self.assertContains(resp, 'href="/pasienter/"')

    def test_bruker_uten_pasient_flagg_ser_ikke_pasient_kort(self):
        bruker = User.objects.create_user(
            username='dash_no', password='x', role='read_only',
            must_change_password=False,
        )
        self.client.force_login(bruker)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        # Kortet skal ikke vises (Pasientregistrering finnes hverken som tittel
        # eller modul-link). Vi sjekker fraværet av modul-kortets href.
        self.assertNotContains(resp, 'aria-label="Åpne Pasientregistrering"')
        # Empty-state skal vises
        self.assertContains(resp, 'Ingen moduler er tilgjengelige')

    def test_deaktivert_pasient_skjules_for_ikke_admin(self):
        bruker = User.objects.create_user(
            username='dash_dis', password='x', role='read_only',
            must_change_password=False,
            kan_redigere_pasienter=True,
        )
        ModuleSettings.objects.filter(slug='patients').update(enabled=False)
        self.client.force_login(bruker)
        resp = self.client.get('/')
        self.assertNotContains(resp, 'aria-label="Åpne Pasientregistrering"')


@override_settings(SECURE_SSL_REDIRECT=False)
class NavMenuTests(TestCase):
    """Verifiserer at base_portal.html-nav rendres fra registry."""

    def setUp(self):
        reset_registry_cache()
        ModuleSettings.ensure_defaults_exist()

    def test_admin_ser_pasient_lenke_i_nav(self):
        admin = User.objects.create_user(
            username='nav_a', password='x', role='admin',
            must_change_password=False,
        )
        self.client.force_login(admin)
        resp = self.client.get('/')
        # Sjekker at nav-baren har patients-lenken (i tillegg til dashboard-kortet).
        # Søk etter href="/pasienter/" som forekommer både i nav og kort —
        # vi forventer minst 2 forekomster.
        self.assertGreaterEqual(resp.content.decode().count('href="/pasienter/"'), 2)

    def test_bruker_uten_flagg_ser_ikke_pasient_i_nav(self):
        bruker = User.objects.create_user(
            username='nav_no', password='x', role='read_only',
            must_change_password=False,
        )
        self.client.force_login(bruker)
        resp = self.client.get('/')
        # Verken nav-lenke eller kort skal være med.
        self.assertNotContains(resp, 'href="/pasienter/"')


@override_settings(SECURE_SSL_REDIRECT=False)
class AuditLogAppLabelTests(TestCase):
    """Verifiserer at AuditLog.app_label fylles automatisk fra table_name."""

    def test_pre_save_fyller_patients_for_patient_tabell(self):
        from audit.models import AuditLog
        log = AuditLog.objects.create(
            table_name='patients_patient',
            record_id=1,
            action='CREATE',
        )
        self.assertEqual(log.app_label, 'patients')

    def test_pre_save_fyller_patients_for_backup(self):
        from audit.models import AuditLog
        log = AuditLog.objects.create(
            table_name='backup',
            record_id=0,
            action='CREATE',
            field_name='backup_created',
        )
        self.assertEqual(log.app_label, 'patients',
                         'backup-rader skal mappes til patients-modulen')

    def test_eksplisitt_app_label_overstyrer_auto(self):
        from audit.models import AuditLog
        log = AuditLog.objects.create(
            table_name='patients_patient',
            record_id=2,
            action='UPDATE',
            app_label='custom_label',
        )
        self.assertEqual(log.app_label, 'custom_label')

    def test_utled_app_label_helper(self):
        from audit.signals import utled_app_label
        self.assertEqual(utled_app_label('patients_patient'), 'patients')
        self.assertEqual(utled_app_label('accounts_customuser'), 'accounts')
        self.assertEqual(utled_app_label('backup'), 'patients')
        self.assertEqual(utled_app_label(''), '')

    def test_index_paa_app_label_finnes(self):
        from audit.models import AuditLog
        index_felt = [
            tuple(idx.fields) for idx in AuditLog._meta.indexes
        ]
        self.assertIn(('app_label', 'created_at'), index_felt)


@override_settings(SECURE_SSL_REDIRECT=False)
class CustomUserPermissionFlagsTests(TestCase):
    """Verifiserer at de 5 permission-flaggene finnes på CustomUser."""

    def test_alle_fem_flagg_eksisterer(self):
        bruker = User.objects.create_user(
            username='flag_test', password='x', role='read_only',
            must_change_password=False,
        )
        for felt in [
            'kan_redigere_pasienter',
            'kan_redigere_vakter',
            'kan_redigere_utstyr',
            'kan_se_rapport',
            'kan_redigere_beredskap',
        ]:
            self.assertTrue(hasattr(bruker, felt), f'CustomUser mangler {felt}')
            # Default skal være False for nye brukere.
            self.assertFalse(getattr(bruker, felt),
                             f'{felt} skal default være False')
