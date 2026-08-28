"""Tester for core-appens primitiver.

Dekker:
1.  Tids-validatorer (validate_time_string, validate_patient_time_fields, parse_minutes)
2.  Lokal-tid-helper (now_local_str)
3.  Global admin (er_global_admin)
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

from core.auth_decorators import admin_required, er_global_admin
from core.validators import (
    TIME_FIELDS,
    TIME_FORMAT,
    TIME_FORMAT_HUMAN,
    now_local_str,
    parse_minutes,
    validate_patient_time_fields,
    validate_time_string,
)
from accounts.test_helpers import gi_standardtilgang


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
# Global admin
#
# `ROLE_HIERARKI` og `has_role_at_least()` ble fjernet i deploy 2. Hierarkiet
# var aldri et hierarki av rettigheter — `lead_view` lå over `read_write` uten
# å ha skrivetilgang — og med `role` krympet til admin/bruker er det ingenting
# å rangere.
# ════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    """Test-helper — etterligner CustomUser uten å trekke inn DB-modeller."""
    def __init__(self, role=None, authenticated=True):
        self.role = role
        self.is_authenticated = authenticated


class ErGlobalAdminTests(TestCase):
    """Den ene rollesjekken som står igjen."""

    def test_admin_er_admin(self):
        self.assertTrue(er_global_admin(_FakeUser(role='admin')))

    def test_bruker_er_ikke_admin(self):
        self.assertFalse(er_global_admin(_FakeUser(role='bruker')))

    def test_uautentisert_er_ikke_admin(self):
        self.assertFalse(er_global_admin(_FakeUser(role='admin', authenticated=False)))

    def test_ukjent_rolle_er_ikke_admin(self):
        """Fail-closed. En rolle vi ikke kjenner skal ikke gi admin."""
        self.assertFalse(er_global_admin(_FakeUser(role='superduperadmin')))

    def test_bruker_uten_rollefelt_er_ikke_admin(self):
        class Uten:
            is_authenticated = True
        self.assertFalse(er_global_admin(Uten()))

    def test_hierarkiet_er_borte(self):
        """De fem rolleverdiene skal ikke kunne snike seg inn igjen.

        Kommer `has_role_at_least` tilbake, kommer også fella den bar med
        seg: `has_role_at_least(user, 'read_write')` ga `lead_view`
        skrivetilgang uten at noen merket det.
        """
        import core.auth_decorators as ad
        for navn in ('ROLE_HIERARKI', 'has_role_at_least', 'role_required',
                     'write_required', 'stats_required', 'dataset_scope_all'):
            with self.subTest(navn=navn):
                self.assertFalse(hasattr(ad, navn),
                                 f'{navn} skal være fjernet i deploy 2')


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

    def test_accounts_decorators_re_eksporterer(self):
        """Shimen krympet i deploy 2, men `admin_required` skal virke.

        Det er den eneste rollebaserte dekoratøren som står igjen; resten tok
        rolleverdier som ikke finnes lenger.
        """
        from accounts.decorators import admin_required as a_admin  # noqa: F401
        self.assertIs(a_admin, admin_required)

    def test_produksjonskode_importerer_ikke_fra_shimen(self):
        """Regelen i CLAUDE.md skal ikke brytes av kodebasen selv (N11).

        Shimen beholdes for bakoverkompatibilitet — testen over verifiserer at
        den fortsatt virker — men produksjonskode skal importere direkte fra
        `core.auth_decorators`. Tre filer gjorde ikke det, og en regel som
        kodebasen bryter tre steder er verre enn ingen regel.
        """
        from pathlib import Path
        from django.conf import settings

        base = Path(settings.BASE_DIR)
        unntak = {
            base / 'accounts' / 'decorators.py',   # selve shimen
            base / 'core' / 'tests.py',            # tester at shimen virker
        }

        syndere = []
        for app in ('accounts', 'audit', 'core', 'patients', 'myproject'):
            for py in (base / app).rglob('*.py'):
                if py in unntak or py.name.startswith('test'):
                    continue
                if 'from accounts.decorators import' in py.read_text(encoding='utf-8'):
                    syndere.append(str(py.relative_to(base)))

        self.assertEqual(sorted(syndere), [], (
            'Disse importerer fra bakoverkompatibilitets-shimen:\n  '
            + '\n  '.join(sorted(syndere))
            + '\n\nBytt til `from core.auth_decorators import ...` — samme objekter.'
        ))

    def test_arkiv_konstantene_er_fjernet(self):
        """ARKIV_VIEW_MIN_ROLE og ARKIV_WRITE_ROLE falt med rollene.

        De var «konfigurerbare» — kommentaren foreslo `lead_view` eller `lead`
        for å åpne arkivet — men de verdiene finnes ikke etter deploy 2. En
        knapp som ikke lar seg skru på er verre enn ingen knapp: den ser ut
        som et valg. Arkivet er global admin, per §3.3.
        """
        import patients.services as svc
        for navn in ('ARKIV_VIEW_MIN_ROLE', 'ARKIV_WRITE_ROLE'):
            with self.subTest(navn=navn):
                self.assertFalse(hasattr(svc, navn))


# ═══════════════════════════════════════════════════════════════════════════
# Fase 2: Portal-dashboard
# ═══════════════════════════════════════════════════════════════════════════


from accounts.models import ModulTilgang  # noqa: E402

User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class PortalDashboardViewTests(TestCase):
    """Verifiserer at portal-dashboardet ligger på / og krever innlogging."""

    def setUp(self):
        # Modulkortet vises kun med en ModulTilgang-rad. Flagget som sto her
        # før styrer ingenting lenger — se ModuleVisibilityTests.
        self.user = User.objects.create_user(
            username='dashbruker', password='x', role='bruker',
            must_change_password=False,
        )
        ModulTilgang.objects.create(
            bruker=self.user, modul_slug='patients', nivaa='les',
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
        """Admin skal se de administrative flatene i portal-menyen."""
        admin = User.objects.create_superuser(
            username='superadm', password='x', role='admin',
            must_change_password=False,
        )
        self.client.force_login(admin)
        resp = self.client.get('/')
        self.assertContains(resp, 'Server-status')
        self.assertContains(resp, 'Innloggingslogg')
        # Django-admin er fjernet fra menyen (S1) — flaten finnes ikke i prod
        self.assertNotContains(resp, 'Django-admin')

    def test_read_only_ser_ikke_admin_lenker(self):
        """Vanlig bruker skal IKKE se admin-lenker."""
        self.client.force_login(self.user)
        resp = self.client.get('/')
        self.assertNotContains(resp, 'Server-status')
        self.assertNotContains(resp, 'Innloggingslogg')


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
        """/admin/server-status/ → 301 → /portal-admin/server-status/"""
        resp = self.client.get('/admin/server-status/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(
            resp['Location'],
            '/portal-admin/server-status/',
        )

    def test_admin_server_status_subpath_redirectes(self):
        resp = self.client.get('/admin/server-status/json/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(
            resp['Location'],
            '/portal-admin/server-status/json/',
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
            username='paspruker', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.user, 'leser')
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
        """reverse('admin_server_status') skal gi /portal-admin/server-status/."""
        from django.urls import reverse as r
        self.assertEqual(
            r('admin_server_status'),
            '/portal-admin/server-status/',
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
    """Verifiserer at admin-nav viser 'Portal' i stedet for 'Pasientliste'.

    Docstringen pekte tidligere på `base.html`. Den malen ble slettet 23. aug.
    2026 — ingenting arvet fra den lenger, og sidene testene her treffer
    bruker `core/templates/core/base_portal.html`.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='nav_admin', password='x', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.client.force_login(self.admin)

    def test_endre_passord_har_dashboard_lenke(self):
        """Endre-passord-siden bruker base_portal.html og har Dashboard-lenke i portal-nav."""
        resp = self.client.get('/accounts/change-password/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Dashboard')
        self.assertNotContains(resp, '>Pasientliste</a>')

    def test_brukere_har_dashboard_lenke(self):
        """Brukere-siden bruker base_portal.html og har Dashboard-lenke i portal-nav."""
        resp = self.client.get('/portal-admin/brukere/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Dashboard')
        self.assertNotContains(resp, '>Pasientliste</a>')

    def test_server_status_har_dashboard_lenke(self):
        """Server-status-siden bruker base_portal.html og har Dashboard-lenke i portal-nav."""
        resp = self.client.get('/portal-admin/server-status/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Dashboard')
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

    def test_bruker_uten_modultilgang_ser_ikke_patients(self):
        bruker = User.objects.create_user(
            username='no_pas', password='x', role='bruker',
            must_change_password=False,
        )
        # Ingen ModulTilgang-rad = ingen tilgang. Det finnes ingen
        # 'ingen'-verdi å lagre; fraværet er svaret.
        slugs = {m.slug for m in get_dashboard_modules(bruker)}
        self.assertNotIn('patients', slugs)

    def test_bruker_med_modultilgang_ser_patients(self):
        bruker = User.objects.create_user(
            username='ja_pas', password='x', role='bruker',
            must_change_password=False,
        )
        ModulTilgang.objects.create(bruker=bruker, modul_slug='patients', nivaa='les')
        slugs = {m.slug for m in get_dashboard_modules(bruker)}
        self.assertIn('patients', slugs)

    def test_uten_rad_ingen_synlighet(self):
        """Fravær av rad er ingen tilgang — også i menyen.

        Testen satte tidligere `kan_redigere_pasienter=True` for å vise at
        flagget ikke lenger ga synlighet. Feltet er borte etter deploy 3, så
        det som står igjen er selve invarianten: en konto uten rad ser ikke
        modulen, uansett hva annet som er satt på den.
        """
        bruker = User.objects.create_user(
            username='uten_rad', password='x', role='bruker',
            must_change_password=False,
        )
        slugs = {m.slug for m in get_dashboard_modules(bruker)}
        self.assertNotIn('patients', slugs)

    def test_deaktivert_modul_skjules_for_ikke_admin(self):
        bruker = User.objects.create_user(
            username='ja_pas2', password='x', role='bruker',
            must_change_password=False,
        )
        ModulTilgang.objects.create(bruker=bruker, modul_slug='patients', nivaa='les')
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
        gi_standardtilgang(admin, 'admin')
        self.client.force_login(admin)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pasientregistrering')
        self.assertContains(resp, 'href="/pasienter/"')

    def test_bruker_uten_modultilgang_ser_ikke_pasient_kort(self):
        # Ingen `gi_standardtilgang` her: fraværet av rader er hele poenget.
        bruker = User.objects.create_user(
            username='dash_no', password='x', role='bruker',
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
            username='dash_dis', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(bruker, 'leser')
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
        gi_standardtilgang(admin, 'admin')
        self.client.force_login(admin)
        resp = self.client.get('/')
        # Sjekker at nav-baren har patients-lenken (i tillegg til dashboard-kortet).
        # Søk etter href="/pasienter/" som forekommer både i nav og kort —
        # vi forventer minst 2 forekomster.
        self.assertGreaterEqual(resp.content.decode().count('href="/pasienter/"'), 2)

    def test_bruker_uten_modultilgang_ser_ikke_pasient_i_nav(self):
        # Ingen `gi_standardtilgang` her: fraværet av rader er hele poenget.
        bruker = User.objects.create_user(
            username='nav_no', password='x', role='bruker',
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
    """De fem `kan_redigere_*`-flaggene er fjernet (deploy 3).

    Testen sto tidligere og krevde at feltene *fantes*. Den er snudd, ikke
    slettet: flaggene så ut som tilgangskontroll uten å være det i to år, og
    et felt som kommer tilbake ved en modell-refaktorering ville invitert
    neste utvikler til å gate på det igjen.
    """

    FJERNEDE = (
        'kan_redigere_pasienter',
        'kan_redigere_vakter',
        'kan_redigere_utstyr',
        'kan_se_rapport',
        'kan_redigere_beredskap',
    )

    def test_ingen_av_flaggene_finnes_paa_modellen(self):
        felter = {f.name for f in User._meta.get_fields()}
        for felt in self.FJERNEDE:
            with self.subTest(felt=felt):
                self.assertNotIn(felt, felter)

    def test_flaggene_kan_ikke_settes_ved_oppretting(self):
        """Et kall som prøver skal feile høylytt, ikke lagre stille."""
        with self.assertRaises(TypeError):
            User.objects.create_user(
                username='flag_test', password='x', role='bruker',
                must_change_password=False, kan_redigere_pasienter=True,
            )


# ════════════════════════════════════════════════════════════════════════════
# Fase 3b: Admin-UI for moduler, AuditLog, og Min profil
# ════════════════════════════════════════════════════════════════════════════


@override_settings(SECURE_SSL_REDIRECT=False)
class ModuleAdminUITests(TestCase):
    """Tester for /portal-admin/moduler/ og /portal-admin/moduler/<slug>/.

    Dekker tilgangskontroll, listevisning, redigering og kjernemodul-vern.
    """

    def setUp(self):
        from core.models import ModuleSettings
        # Sørg for at default-rader finnes
        ModuleSettings.ensure_defaults_exist()
        self.admin = User.objects.create_user(
            username='3b_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.read_only = User.objects.create_user(
            username='3b_ro', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.read_only, 'leser')
        self.client = Client()

    def test_modulliste_kun_admin(self):
        """GET /portal-admin/moduler/ skal kreve admin."""
        # Uautentisert → redirect/forbidden
        resp = self.client.get('/portal-admin/moduler/')
        self.assertIn(resp.status_code, (302, 403))

        # Read-only → forbidden eller redirect
        self.client.force_login(self.read_only)
        resp = self.client.get('/portal-admin/moduler/')
        self.assertIn(resp.status_code, (302, 403))

    def test_modulliste_admin_ser_moduler(self):
        """Admin skal se modul-listen og alle registrerte moduler."""
        from core.modules import get_all_modules
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/moduler/')
        self.assertEqual(resp.status_code, 200)
        # Skal vise minst kjernemodulene
        for modul in get_all_modules():
            self.assertContains(resp, modul.slug)

    def test_modulliste_url_loeses(self):
        self.assertEqual(
            reverse('core:module_admin_list'),
            '/portal-admin/moduler/',
        )

    def test_redigering_av_modul_lagrer(self):
        """POST på edit-view skal lagre `note`-felt og sette updated_by."""
        from core.models import ModuleSettings
        # Bruker en ikke-kjernemodul. Hvis ingen finnes, lager vi en.
        non_core = (
            ModuleSettings.objects
            .exclude(slug__in=['core', 'accounts'])
            .first()
        )
        if non_core is None:
            non_core = ModuleSettings.objects.create(slug='patients', enabled=True)

        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse('core:module_admin_edit', kwargs={'slug': non_core.slug}),
            {'enabled': 'on', 'backup_enabled': 'on', 'note': 'Test-notat'},
        )
        # Redirect etter suksess
        self.assertEqual(resp.status_code, 302)
        non_core.refresh_from_db()
        self.assertEqual(non_core.note, 'Test-notat')
        self.assertEqual(non_core.updated_by, self.admin)

    def test_kjernemodul_kan_ikke_deaktiveres(self):
        """Form skal avvise enabled=False for kjernemoduler."""
        from core.forms import ModuleSettingsForm
        from core.models import ModuleSettings
        from core.modules import get_all_modules

        kjerne = next(
            (m for m in get_all_modules() if m.is_core),
            None,
        )
        self.assertIsNotNone(kjerne, 'Forventer minst én kjernemodul')

        settings_obj, _ = ModuleSettings.objects.get_or_create(
            slug=kjerne.slug, defaults={'enabled': True},
        )
        form = ModuleSettingsForm(
            data={'enabled': False, 'backup_enabled': False, 'note': ''},
            instance=settings_obj,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('enabled', form.errors)

    def test_redigering_404_for_ukjent_slug(self):
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse('core:module_admin_edit', kwargs={'slug': 'finnes-ikke'}),
        )
        self.assertEqual(resp.status_code, 404)

    def test_modulliste_lenker_til_redigering(self):
        from core.models import ModuleSettings
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/moduler/')
        # Minst én rediger-lenke skal finnes
        first = ModuleSettings.objects.first()
        if first:
            self.assertContains(resp, f'/portal-admin/moduler/{first.slug}/')


@override_settings(SECURE_SSL_REDIRECT=False)
class AuditLogListViewTests(TestCase):
    """Tester for /portal-admin/auditlog/ med filter, pagination og CSV-eksport."""

    def setUp(self):
        from audit.models import AuditLog
        self.admin = User.objects.create_user(
            username='3b_audit_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.read_only = User.objects.create_user(
            username='3b_audit_ro', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.read_only, 'leser')
        # Lag noen AuditLog-rader vi kan filtrere på
        AuditLog.objects.create(
            table_name='patients_patient', record_id=1,
            action='CREATE', user=self.admin, app_label='patients',
        )
        AuditLog.objects.create(
            table_name='patients_patient', record_id=1,
            action='UPDATE', user=self.admin, app_label='patients',
            field_name='inntid', old_value='10:00', new_value='11:00',
        )
        AuditLog.objects.create(
            table_name='accounts_customuser', record_id=1,
            action='UPDATE', user=self.admin, app_label='accounts',
        )
        self.client = Client()

    def test_auditlog_kun_admin(self):
        resp = self.client.get('/portal-admin/auditlog/')
        self.assertIn(resp.status_code, (302, 403))

        self.client.force_login(self.read_only)
        resp = self.client.get('/portal-admin/auditlog/')
        self.assertIn(resp.status_code, (302, 403))

    def test_auditlog_admin_ser_alle_rader(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'patients_patient')
        self.assertContains(resp, 'accounts_customuser')

    def test_auditlog_filter_app_label(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/?app_label=accounts')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'accounts_customuser')
        self.assertNotContains(resp, 'patients_patient')

    def test_auditlog_filter_action(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/?action=CREATE')
        self.assertEqual(resp.status_code, 200)
        # Bare CREATE-rader skal være med — UPDATE skal ikke
        # (Vi sjekker antall via paginator-context)
        page_obj = resp.context['page_obj']
        for row in page_obj.object_list:
            self.assertEqual(row.action, 'CREATE')

    def test_auditlog_filter_user(self):
        self.client.force_login(self.admin)
        resp = self.client.get(f'/portal-admin/auditlog/?user={self.admin.id}')
        self.assertEqual(resp.status_code, 200)
        page_obj = resp.context['page_obj']
        for row in page_obj.object_list:
            self.assertEqual(row.user_id, self.admin.id)

    def test_auditlog_filter_q_fritekst(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/?q=inntid')
        self.assertEqual(resp.status_code, 200)
        page_obj = resp.context['page_obj']
        # Skal kun finne rad med field_name='inntid'
        self.assertEqual(len(page_obj.object_list), 1)
        self.assertEqual(page_obj.object_list[0].field_name, 'inntid')

    def test_auditlog_filter_ugyldig_user_id_ignoreres(self):
        """Ugyldig user-param skal ikke krasje viewet."""
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/?user=ikke-tall')
        self.assertEqual(resp.status_code, 200)

    def test_auditlog_pagination_50_per_side(self):
        """50 rader per side."""
        from audit.models import AuditLog
        # Lag 60 ekstra rader
        for i in range(60):
            AuditLog.objects.create(
                table_name='patients_patient', record_id=i + 100,
                action='CREATE', user=self.admin, app_label='patients',
            )
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/')
        self.assertEqual(resp.status_code, 200)
        page_obj = resp.context['page_obj']
        self.assertEqual(len(page_obj.object_list), 50)

    def test_csv_eksport_returnerer_csv(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/eksport.csv')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        body = resp.content.decode('utf-8-sig')
        self.assertIn('Tidspunkt', body)
        self.assertIn('patients_patient', body)
        # Semikolon-separert
        first_data_line = body.split('\n')[1] if '\n' in body else ''
        self.assertIn(';', first_data_line)

    def test_csv_eksport_har_bom(self):
        """UTF-8 BOM for Excel-kompatibilitet."""
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/eksport.csv')
        self.assertTrue(resp.content.startswith(b'\xef\xbb\xbf'))

    def test_csv_eksport_filename_attachment(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/auditlog/eksport.csv')
        self.assertIn('attachment', resp['Content-Disposition'])
        self.assertIn('auditlog_', resp['Content-Disposition'])

    def test_csv_eksport_kun_admin(self):
        self.client.force_login(self.read_only)
        resp = self.client.get('/portal-admin/auditlog/eksport.csv')
        self.assertIn(resp.status_code, (302, 403))


@override_settings(SECURE_SSL_REDIRECT=False)
class ProfileViewTests(TestCase):
    """Tester for /min-profil/."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='profilbruker', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.user, 'leser')
        self.client = Client()

    def test_profil_url_loeses(self):
        self.assertEqual(reverse('core:profile'), '/min-profil/')

    def test_profil_krever_innlogging(self):
        resp = self.client.get('/min-profil/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login', resp['Location'])

    def test_profil_innlogget_bruker_ser_brukernavn(self):
        self.client.force_login(self.user)
        resp = self.client.get('/min-profil/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'profilbruker')
        self.assertContains(resp, 'Min profil')

    def test_profil_viser_modulene_fra_registeret(self):
        """Kortet følger modulregisteret, ikke en hardkodet liste.

        Testen krevde tidligere «Vakter», «Utstyr», «Rapport» og «Beredskap» —
        etikettene til de fem flaggene. Ingen av dem er moduler; de var
        plassholdere for apper som aldri ble skrevet, og kortet lovet brukeren
        tilganger til noe som ikke finnes.
        """
        self.client.force_login(self.user)
        resp = self.client.get('/min-profil/')
        self.assertContains(resp, 'Pasientregistrering')
        self.assertContains(resp, 'Statistikk')
        for spoekelse in ('Vakter', 'Utstyr', 'Beredskap'):
            with self.subTest(modul=spoekelse):
                self.assertNotContains(resp, spoekelse)

    def test_profil_kun_GET(self):
        self.client.force_login(self.user)
        resp = self.client.post('/min-profil/')
        self.assertEqual(resp.status_code, 405)

    def test_profil_inkluderer_aktivitetslogg(self):
        """Recent_events skal være i context (selv om tom)."""
        self.client.force_login(self.user)
        resp = self.client.get('/min-profil/')
        self.assertIn('recent_events', resp.context)
        self.assertIn('weekly_login_count', resp.context)
        self.assertIn('visible_modules', resp.context)
        self.assertIn('permissions', resp.context)

    def test_profil_admin_info_vises_for_admin(self):
        admin = User.objects.create_user(
            username='profil_admin', password='x', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(admin, 'admin')
        self.client.force_login(admin)
        resp = self.client.get('/min-profil/')
        # Admin har bypass — info-meldingen skal vises
        self.assertContains(resp, 'administrator')


@override_settings(SECURE_SSL_REDIRECT=False)
class ProfilModulTilgangKortetTests(TestCase):
    """Kortet «Modul-tilganger» leser `ModulTilgang`, ikke de døde flaggene.

    Feilen den erstatter var brukervendt og stille: kortet bygde på de fem
    `kan_redigere_*`-flaggene, og backfillen i deploy 1 rørte dem ikke med
    vilje (§8.1). En konto med `patients: skriv_full` fikk derfor «Nei» på
    pasientregistrering, over teksten «Ta kontakt om du trenger flere
    tilganger». Siden ba brukeren melde fra om noe hen allerede hadde.

    Ingen test fanget det, fordi den som fantes bare krevde at de fem
    etikettene sto i HTML-en.
    """

    def setUp(self):
        reset_registry_cache()
        ModuleSettings.ensure_defaults_exist()
        self.client = Client()

    def _kort(self, bruker):
        self.client.force_login(bruker)
        html = self.client.get('/min-profil/').content.decode()
        return html.split('Modul-tilganger')[1].split('Ta kontakt')[0]

    def _bruker(self, navn, tilganger=(), rolle='bruker'):
        b = User.objects.create_user(
            username=navn, password='x', role=rolle, must_change_password=False)
        for slug, nivaa in tilganger:
            ModulTilgang.objects.create(bruker=b, modul_slug=slug, nivaa=nivaa)
        return b

    def test_nivaaet_vises_ikke_bare_ja(self):
        """Kollegaens matrise, slik den står i prod."""
        kort = self._kort(self._bruker('kort_kollega', [
            ('patients', 'skriv_full'), ('statistikk', 'les')]))
        self.assertIn('Skrive: full', kort)
        self.assertIn('Lese', kort)

    def test_skrivetilgang_meldes_ikke_som_ingen(self):
        """Selve feilen: skriv_full ga «Nei» fordi flagget var av."""
        kort = self._kort(self._bruker(
            'kort_skriver', [('patients', 'skriv_full')]))
        pasientrad = kort.split('Pasientregistrering')[1].split('perm-')[1]
        self.assertTrue(pasientrad.startswith('yes'),
                        'skriv_full skal ikke vises som «ingen tilgang»')

    def test_uten_rad_staar_ingen_tilgang(self):
        """Vern mot at kortet alltid sier ja."""
        kort = self._kort(self._bruker('kort_tom'))
        self.assertIn('Ingen tilgang', kort)
        self.assertNotIn('Skrive: full', kort)

    def test_admin_har_alt_uten_rader(self):
        kort = self._kort(self._bruker('kort_admin', rolle='admin'))
        self.assertNotIn('Ingen tilgang', kort)

    def test_deaktivert_modul_merkes_som_av_ikke_som_manglende_tilgang(self):
        """To ulike ting: «du har ikke fått» og «den er slått av».

        Slås de sammen, leser brukeren et driftsvalg som et tilgangsvalg og
        ber om noe hen allerede har.
        """
        bruker = self._bruker('kort_av', [('patients', 'les')])
        ModuleSettings.objects.filter(slug='patients').update(enabled=False)
        kort = self._kort(bruker)
        pasientrad = kort.split('Pasientregistrering')[1].split('</div>')[0]
        self.assertIn('Av', pasientrad)
        self.assertIn('Lese', kort)

    def test_aktiv_modul_merkes_ikke_som_av(self):
        """Vern mot at «Av»-merket alltid vises."""
        bruker = self._bruker('kort_paa', [('patients', 'les')])
        kort = self._kort(bruker)
        pasientrad = kort.split('Pasientregistrering')[1].split('</div>')[0]
        self.assertNotIn('>Av<', pasientrad)


@override_settings(SECURE_SSL_REDIRECT=False)
class NavMenuFase3bTests(TestCase):
    """Verifiserer at Min profil og admin-lenker er i nav-meny + dropdown."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='nav_admin', password='x', role='admin',
            must_change_password=False, is_staff=True,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.read_only = User.objects.create_user(
            username='nav_ro', password='x', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.read_only, 'leser')
        self.client = Client()

    def test_min_profil_lenke_i_dropdown_for_alle(self):
        self.client.force_login(self.read_only)
        resp = self.client.get('/')
        self.assertContains(resp, '/min-profil/')
        self.assertContains(resp, 'Min profil')

    def test_admin_lenker_i_nav_for_admin(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/')
        self.assertContains(resp, '/portal-admin/moduler/')
        self.assertContains(resp, '/portal-admin/auditlog/')

    def test_admin_lenker_skjult_for_read_only(self):
        self.client.force_login(self.read_only)
        resp = self.client.get('/')
        self.assertNotContains(resp, '/portal-admin/moduler/')
        self.assertNotContains(resp, '/portal-admin/auditlog/')
