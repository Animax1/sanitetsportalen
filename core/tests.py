"""Tester for core-appens primitiver.

Dekker:
1.  Tids-validatorer (validate_time_string, validate_patient_time_fields, parse_minutes)
2.  Lokal-tid-helper (now_local_str)
3.  Rolle-hierarki (has_role_at_least)
4.  Bakoverkompatibilitet: at re-eksporter fra patients.services og
    accounts.decorators fortsatt fungerer slik at eksisterende kode
    ikke brekker.
"""
from datetime import datetime
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
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
