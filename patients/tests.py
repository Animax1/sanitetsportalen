"""Kjernetester for pasientregistrering.

Kjør med: python manage.py test patients
"""
from datetime import datetime

from django.test import TestCase, Client, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from patients.models import Patient, Behandler, Helsepersonell, AppSetting
from patients.services import (
    apply_list_filter, stamp_pabegynt_if_needed,
    stamp_obs_times_if_needed, stamp_utskrevet_if_needed,
    get_active_year, set_active_year,
)


# ── Filtertester ──────────────────────────────────────────────────────────────

class FilterTests(TestCase):
    """Tester for apply_list_filter – server-side filtreringslogikk."""

    @classmethod
    def setUpTestData(cls):
        cls.year = 2026
        cls.p_rod_aktiv = Patient.objects.create(
            pasientnummer=1, year=cls.year, grovsortering='Rød')
        cls.p_gul_aktiv = Patient.objects.create(
            pasientnummer=2, year=cls.year, grovsortering='Gul')
        cls.p_gronn_aktiv = Patient.objects.create(
            pasientnummer=3, year=cls.year, grovsortering='Grønn')
        cls.p_rod_utskrevet = Patient.objects.create(
            pasientnummer=4, year=cls.year, grovsortering='Rød',
            utskrevet='01.01.2026 10:00')
        cls.p_gul_utskrevet = Patient.objects.create(
            pasientnummer=5, year=cls.year, grovsortering='Gul',
            utskrevet='01.01.2026 10:00')
        cls.p_gronn_utskrevet = Patient.objects.create(
            pasientnummer=6, year=cls.year, grovsortering='Grønn',
            utskrevet='01.01.2026 10:00')

    def test_rod_filter_excludes_utskrevet(self):
        """Rødt-filter skal bare vise aktive (ikke utskrevne) røde pasienter."""
        qs = apply_list_filter(Patient.objects.all(), 'rod', year=self.year)
        self.assertEqual(list(qs), [self.p_rod_aktiv])

    def test_gul_filter_excludes_utskrevet(self):
        """Gult-filter skal bare vise aktive gule pasienter."""
        qs = apply_list_filter(Patient.objects.all(), 'gul', year=self.year)
        self.assertEqual(list(qs), [self.p_gul_aktiv])

    def test_gronn_filter_excludes_utskrevet(self):
        """Grønt-filter skal bare vise aktive grønne pasienter."""
        qs = apply_list_filter(Patient.objects.all(), 'gronn', year=self.year)
        self.assertEqual(list(qs), [self.p_gronn_aktiv])

    def test_rodgul_filter_excludes_utskrevet(self):
        """Rød+Gul-filter skal bare vise aktive røde og gule pasienter."""
        qs = apply_list_filter(Patient.objects.all(), 'rodgul', year=self.year)
        self.assertCountEqual(list(qs), [self.p_rod_aktiv, self.p_gul_aktiv])

    def test_utskrevet_filter(self):
        """Utskrevet-filter skal bare vise utskrevne pasienter."""
        qs = apply_list_filter(Patient.objects.all(), 'utskrevet', year=self.year)
        self.assertCountEqual(
            list(qs),
            [self.p_rod_utskrevet, self.p_gul_utskrevet, self.p_gronn_utskrevet],
        )

    def test_alle_filter_returns_all(self):
        """Alle-filter skal returnere alle pasienter for valgt år."""
        qs = apply_list_filter(Patient.objects.all(), 'alle', year=self.year)
        self.assertEqual(qs.count(), 6)

    def test_year_filter(self):
        """Year-parameter skal filtrere på år."""
        Patient.objects.create(pasientnummer=99, year=2025, grovsortering='Rød')
        qs = apply_list_filter(Patient.objects.all(), 'rod', year=self.year)
        # Pasient fra 2025 skal ikke inkluderes
        pns = list(qs.values_list('pasientnummer', flat=True))
        self.assertNotIn(99, pns)


# ── Påbegynt-stempler ─────────────────────────────────────────────────────────

class PabegyntTests(TestCase):
    """Tester for stamp_pabegynt_if_needed."""

    def test_behandler_triggers_pabegynt(self):
        """Sett behandler skal utløse påbegynt-stempling."""
        b = Behandler.objects.create(name='Ola')
        p = Patient(pasientnummer=1, year=2026)
        result = stamp_pabegynt_if_needed(p, {'behandler': b})
        self.assertTrue(result)
        self.assertTrue(p.pabegynt)

    def test_behandler_id_triggers_pabegynt(self):
        """Sett behandler som ID (integer) skal også utløse stempling."""
        b = Behandler.objects.create(name='Kari')
        p = Patient(pasientnummer=2, year=2026)
        result = stamp_pabegynt_if_needed(p, {'behandler': b.id})
        self.assertTrue(result)

    def test_helsepersonell_ref_triggers_pabegynt(self):
        """helsepersonell_ref-felt skal utløse påbegynt-stempling."""
        p = Patient(pasientnummer=1, year=2026)
        result = stamp_pabegynt_if_needed(p, {'helsepersonell_ref': 2})
        self.assertTrue(result)

    def test_pabegynt_not_overwritten(self):
        """Påbegynt skal ikke overskrives hvis det allerede er satt."""
        p = Patient(pasientnummer=1, year=2026, pabegynt='15.04.2026 10:00')
        result = stamp_pabegynt_if_needed(p, {'helsepersonell_ref': 2})
        self.assertFalse(result)
        self.assertEqual(p.pabegynt, '15.04.2026 10:00')

    def test_empty_trigger_does_not_stamp(self):
        """Tom trigger-verdi skal ikke utløse stempling."""
        p = Patient(pasientnummer=1, year=2026)
        result = stamp_pabegynt_if_needed(p, {'helsepersonell_ref': None})
        self.assertFalse(result)
        self.assertFalse(p.pabegynt)

    def test_none_behandler_does_not_stamp(self):
        """None-behandler skal ikke utløse stempling."""
        p = Patient(pasientnummer=1, year=2026)
        result = stamp_pabegynt_if_needed(p, {'behandler': None})
        self.assertFalse(result)


# ── Behandler-modell ─────────────────────────────────────────────────────────

class BehandlerTests(TestCase):
    """Tester for Behandler-modell og FK-integritet."""

    def test_inactive_behandler_preserves_history(self):
        """Inaktivering av behandler skal ikke bryte pasient-referansen."""
        b = Behandler.objects.create(name='Historisk')
        p = Patient.objects.create(pasientnummer=1, year=2025, behandler=b)
        b.is_active = False
        b.save()
        # Pasienten skal fortsatt ha referansen
        p.refresh_from_db()
        self.assertEqual(p.behandler, b)

    def test_cannot_delete_behandler_in_use(self):
        """Behandler knyttet til pasient skal ikke kunne slettes (PROTECT)."""
        from django.db.models.deletion import ProtectedError
        b = Behandler.objects.create(name='Brukes')
        Patient.objects.create(pasientnummer=1, year=2026, behandler=b)
        with self.assertRaises(ProtectedError):
            b.delete()

    def test_str_inactive(self):
        """__str__ skal vise (inaktiv) for inaktive behandlere."""
        b = Behandler.objects.create(name='Test', is_active=False)
        self.assertIn('inaktiv', str(b))

    def test_str_active(self):
        """__str__ skal ikke inneholde (inaktiv) for aktive behandlere."""
        b = Behandler.objects.create(name='Aktiv', is_active=True)
        self.assertNotIn('inaktiv', str(b))


# ── Årsarkivering ────────────────────────────────────────────────────────────

class YearArchiveTests(TestCase):
    """Tester for arkivering av år (data-laget – is_active-feltet beholdes)."""

    def test_archive_year_sets_inactive(self):
        """Arkivering av et år skal sette is_active=False på alle pasienter det året."""
        Patient.objects.create(pasientnummer=1, year=2025)
        Patient.objects.create(pasientnummer=2, year=2025)
        Patient.objects.create(pasientnummer=3, year=2026)
        Patient.objects.filter(year=2025).update(is_active=False)
        self.assertEqual(Patient.objects.filter(is_active=True).count(), 1)

    def test_restore_year(self):
        """Gjenoppretting av et år skal sette is_active=True igjen."""
        Patient.objects.create(pasientnummer=1, year=2025)
        Patient.objects.create(pasientnummer=2, year=2025)
        Patient.objects.create(pasientnummer=3, year=2026)
        Patient.objects.filter(year=2025).update(is_active=False)
        # Gjenopprett
        Patient.objects.filter(year=2025).update(is_active=True)
        self.assertEqual(Patient.objects.filter(is_active=True).count(), 3)


# ── Tilgangskontroll ─────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class AccessControlTests(TestCase):
    """Tester for rolle-basert tilgangskontroll."""

    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            username='a', password='x', role='admin')
        self.lead = CustomUser.objects.create_user(
            username='l', password='x', role='lead', must_change_password=False)
        self.rw = CustomUser.objects.create_user(
            username='w', password='x', role='read_write', must_change_password=False)
        self.ro = CustomUser.objects.create_user(
            username='r', password='x', role='read_only', must_change_password=False)

    def _login(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_read_only_cannot_add_behandler(self):
        """read_only-bruker skal ikke kunne opprette behandler."""
        c = self._login(self.ro)
        import json as _j
        resp = c.post('/pasienter/api/behandlere/',
                      data=_j.dumps({'name': 'X'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_read_write_cannot_add_behandler(self):
        """read_write-bruker skal ikke kunne opprette behandler (kun admin)."""
        c = self._login(self.rw)
        import json as _j
        resp = c.post('/pasienter/api/behandlere/',
                      data=_j.dumps({'name': 'X'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_add_behandler(self):
        """Admin-bruker skal kunne opprette behandler."""
        c = self._login(self.admin)
        import json as _j
        resp = c.post('/pasienter/api/behandlere/',
                      data=_j.dumps({'name': 'X'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 201)

    def test_read_only_cannot_create_patient(self):
        """read_only-bruker skal ikke kunne opprette pasient."""
        c = self._login(self.ro)
        import json as _j
        resp = c.post('/pasienter/api/patients/',
                      data=_j.dumps({'problemstilling': 'X'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_cannot_access_patients(self):
        """Uautentisert bruker skal bli videresendt til innlogging."""
        c = Client()
        resp = c.get('/pasienter/api/patients/')
        self.assertIn(resp.status_code, [302, 403])

# ── Obs-stempler ──────────────────────────────────────────────────────────────

class ObsStampTests(TestCase):
    """Tester for stamp_obs_times_if_needed."""

    def setUp(self):
        self.stamp = stamp_obs_times_if_needed

    def test_obs_plassering_stempler_inn_obspost(self):
        """Plassering til Obs-plass stempler inn_obspost hvis den er tom."""
        p = Patient(pasientnummer=1, year=2026, plassering='Obs 1')
        changed = self.stamp(p, '', {})
        self.assertIn('inn_obspost', changed)
        self.assertTrue(p.inn_obspost)

    def test_inn_obspost_ikke_overskrevet(self):
        """inn_obspost som allerede er satt skal ikke overskrives."""
        p = Patient(pasientnummer=1, year=2026, plassering='Obs 1',
                    inn_obspost='01.01.2026 10:00')
        changed = self.stamp(p, '', {})
        self.assertNotIn('inn_obspost', changed)
        self.assertEqual(p.inn_obspost, '01.01.2026 10:00')

    def test_fra_obs_til_annen_stempler_ut_obspost(self):
        """Bytte fra obs-plass til annen plass stempler ut_obspost."""
        p = Patient(pasientnummer=1, year=2026, plassering='Grønn sone',
                    inn_obspost='01.01.2026 10:00')
        changed = self.stamp(p, 'Obs 1', {})
        self.assertIn('ut_obspost', changed)
        self.assertTrue(p.ut_obspost)

    def test_ut_obspost_ikke_overskrevet(self):
        """ut_obspost som allerede er satt skal ikke overskrives."""
        p = Patient(pasientnummer=1, year=2026, plassering='Grønn sone',
                    inn_obspost='01.01.2026 10:00',
                    ut_obspost='01.01.2026 11:00')
        changed = self.stamp(p, 'Obs 1', {})
        self.assertNotIn('ut_obspost', changed)
        self.assertEqual(p.ut_obspost, '01.01.2026 11:00')

    def test_forblir_obs_stempler_ikke_ut(self):
        """Forblir i obs uten overgang: ut_obspost skal ikke settes."""
        p = Patient(pasientnummer=1, year=2026, plassering='Obs 2',
                    inn_obspost='01.01.2026 10:00')
        changed = self.stamp(p, 'Obs 1', {})
        self.assertNotIn('ut_obspost', changed)

    def test_is_obs_location_case_insensitive(self):
        """Obs-sjekk er case-insensitiv."""
        from patients.services import _is_obs_location
        self.assertTrue(_is_obs_location('obs 1'))
        self.assertTrue(_is_obs_location('Obs 5'))
        self.assertFalse(_is_obs_location('Grønn sone'))
        self.assertFalse(_is_obs_location(''))


# ── Utskrevet-stempler ────────────────────────────────────────────────────────

class UtskrevetStampTests(TestCase):
    """Tester for stamp_utskrevet_if_needed."""

    def setUp(self):
        self.stamp = stamp_utskrevet_if_needed

    def test_utskrevet_til_stempler_utskrevet(self):
        """Sett utskrevet_til stempler utskrevet-tidspunkt."""
        p = Patient(pasientnummer=1, year=2026, utskrevet_til='Hjem')
        changed = self.stamp(p, {})
        self.assertIn('utskrevet', changed)
        self.assertTrue(p.utskrevet)

    def test_utskrevet_ikke_overskrevet(self):
        """utskrevet allerede satt skal ikke overskrives."""
        p = Patient(pasientnummer=1, year=2026,
                    utskrevet_til='Hjem', utskrevet='01.01.2026 12:00')
        changed = self.stamp(p, {})
        self.assertNotIn('utskrevet', changed)
        self.assertEqual(p.utskrevet, '01.01.2026 12:00')

    def test_utskrevet_fra_obs_lukker_ut_obspost(self):
        """Utskrives fra obs-plass: ut_obspost skal stemples."""
        p = Patient(pasientnummer=1, year=2026, utskrevet_til='Hjem',
                    plassering='Obs 3', inn_obspost='01.01.2026 10:00')
        changed = self.stamp(p, {})
        self.assertIn('utskrevet', changed)
        self.assertIn('ut_obspost', changed)

    def test_ingen_utskrevet_til_ingen_stempling(self):
        """Tom utskrevet_til skal ikke utløse stempling."""
        p = Patient(pasientnummer=1, year=2026, utskrevet_til='')
        changed = self.stamp(p, {})
        self.assertEqual(changed, [])
        self.assertFalse(p.utskrevet)


# ── Lead_view-rolle ───────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class LeadViewTests(TestCase):
    """Tester for lead_view-rollen – tilgangskontroll i API."""

    def setUp(self):
        set_active_year(2026)
        self.lead_view = CustomUser.objects.create_user(
            username='lv', password='x', role='lead_view', must_change_password=False)
        self.client = Client()
        self.client.force_login(self.lead_view)
        Patient.objects.create(pasientnummer=1, year=2026)

    def test_lead_view_kan_lese_pasienter(self):
        """lead_view kan hente pasientliste for aktivt år."""
        resp = self.client.get('/pasienter/api/patients/')
        self.assertEqual(resp.status_code, 200)

    def test_lead_view_kan_ikke_opprette_pasient(self):
        """lead_view kan ikke opprette ny pasient."""
        import json as _j
        resp = self.client.post('/pasienter/api/patients/',
                                data=_j.dumps({'problemstilling': 'Test'}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_lead_view_kan_lese_full_stats(self):
        """lead_view kan hente full statistikk."""
        resp = self.client.get('/pasienter/api/full-stats/')
        self.assertIn(resp.status_code, [200, 500])  # 500 OK hvis scipy mangler


# ── Reset testdata ────────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class ResetTests(TestCase):
    """Tester for reset_active_year_view."""

    def setUp(self):
        set_active_year(2026)
        self.admin = CustomUser.objects.create_superuser(
            username='a', password='x', role='admin')
        self.lead = CustomUser.objects.create_user(
            username='l', password='x', role='lead', must_change_password=False)
        Patient.objects.create(pasientnummer=1, year=2026)
        Patient.objects.create(pasientnummer=2, year=2026)
        Patient.objects.create(pasientnummer=3, year=2025)  # annet år

    def _client(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_reset_krever_confirm(self):
        """Reset uten confirm=true skal gi 400."""
        import json as _j
        c = self._client(self.admin)
        resp = c.post('/pasienter/api/reset-active-year/',
                      data=_j.dumps({}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_reset_sletter_kun_aktivt_aar(self):
        """Reset sletter kun pasienter i aktivt år."""
        import json as _j
        c = self._client(self.admin)
        resp = c.post('/pasienter/api/reset-active-year/',
                      data=_j.dumps({'confirm': True}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        # 2026-pasienter slettet, 2025 intakt
        self.assertEqual(Patient.objects.filter(year=2026).count(), 0)
        self.assertEqual(Patient.objects.filter(year=2025).count(), 1)

    def test_lead_kan_ikke_resette(self):
        """lead kan ikke kalle reset-endepunktet."""
        import json as _j
        c = self._client(self.lead)
        resp = c.post('/pasienter/api/reset-active-year/',
                      data=_j.dumps({'confirm': True}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)


# ── ETag-tester for /api/behandlere/ ──────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class BehandlerETagTests(TestCase):
    """Tester for ETag/304-funksjonalitet på /api/behandlere/."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='etagtester', password='x', role='read_only',
            must_change_password=False)
        self.client = Client()
        self.client.force_login(self.user)
        Behandler.objects.create(name='Behandler A', is_active=True)

    def test_behandlere_returns_etag_header(self):
        """GET /api/behandlere/ skal returnere ETag-header."""
        resp = self.client.get('/pasienter/api/behandlere/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('ETag', resp)
        self.assertTrue(resp['ETag'].startswith('"v1:'))

    def test_behandlere_returns_304_when_etag_matches(self):
        """GET med If-None-Match som matcher ETag skal gi 304."""
        # Hent ETag fra første request
        resp1 = self.client.get('/pasienter/api/behandlere/')
        etag = resp1['ETag']
        # Send If-None-Match med samme ETag
        resp2 = self.client.get(
            '/pasienter/api/behandlere/',
            HTTP_IF_NONE_MATCH=etag,
        )
        self.assertEqual(resp2.status_code, 304)

    def test_behandlere_returns_200_with_new_etag_when_behandler_added(self):
        """Ny behandler skal gi ny ETag og 200 selv om klient sender gammel ETag."""
        resp1 = self.client.get('/pasienter/api/behandlere/')
        old_etag = resp1['ETag']
        # Legg til ny behandler
        Behandler.objects.create(name='Behandler B', is_active=True)
        resp2 = self.client.get(
            '/pasienter/api/behandlere/',
            HTTP_IF_NONE_MATCH=old_etag,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertNotEqual(resp2['ETag'], old_etag)

    def test_behandlere_returns_200_with_new_etag_when_behandler_renamed(self):
        """Omdøpt behandler skal gi ny ETag og 200."""
        resp1 = self.client.get('/pasienter/api/behandlere/')
        old_etag = resp1['ETag']
        # Omdøp behandleren
        b = Behandler.objects.get(name='Behandler A')
        b.name = 'Ny Behandler A'
        b.save()
        resp2 = self.client.get(
            '/pasienter/api/behandlere/',
            HTTP_IF_NONE_MATCH=old_etag,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertNotEqual(resp2['ETag'], old_etag)


# ── Tidsformat-validering ────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TimeFormatValidationTests(TestCase):
    """Verifiserer at tidsfelter kun aksepterer dd.mm.åååå tt:mm."""

    def setUp(self):
        AppSetting.objects.update_or_create(key='active_year', defaults={'value': '2026'})
        self.user = CustomUser.objects.create_user(
            username='skriver', password='pass', role='read_write',
            must_change_password=False,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _post(self, data):
        import json as _j
        return self.client.post(
            '/pasienter/api/patients/',
            data=_j.dumps(data),
            content_type='application/json',
        )

    def _put(self, pk, data):
        import json as _j
        return self.client.put(
            f'/pasienter/api/patients/{pk}/',
            data=_j.dumps(data),
            content_type='application/json',
        )

    def test_validator_accepts_correct_format(self):
        from patients.services import validate_time_string
        self.assertEqual(
            validate_time_string('19.04.2026 14:30'),
            '19.04.2026 14:30',
        )

    def test_validator_accepts_empty_string(self):
        from patients.services import validate_time_string
        self.assertEqual(validate_time_string(''), '')
        self.assertEqual(validate_time_string(None), '')

    def test_validator_rejects_wrong_separator(self):
        from patients.services import validate_time_string
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_time_string('19/04/2026 14:30')

    def test_validator_rejects_iso_format(self):
        from patients.services import validate_time_string
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_time_string('2026-04-19T14:30')

    def test_validator_rejects_single_digit_day(self):
        from patients.services import validate_time_string
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_time_string('9.04.2026 14:30')

    def test_validator_rejects_invalid_date(self):
        from patients.services import validate_time_string
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            validate_time_string('32.04.2026 14:30')
        with self.assertRaises(ValidationError):
            validate_time_string('19.13.2026 14:30')
        with self.assertRaises(ValidationError):
            validate_time_string('19.04.2026 25:00')

    def test_create_patient_rejects_bad_time(self):
        resp = self._post({
            'problemstilling': 'Test',
            'inntid': '19/04/2026 14:30',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('inntid', resp.json()['error'])

    def test_create_patient_accepts_correct_time(self):
        resp = self._post({
            'problemstilling': 'Test',
            'inntid': '19.04.2026 14:30',
        })
        self.assertEqual(resp.status_code, 201)

    def test_update_patient_rejects_bad_utskrevet(self):
        # Opprett først
        resp = self._post({'problemstilling': 'Test', 'inntid': '19.04.2026 14:30'})
        self.assertEqual(resp.status_code, 201)
        pk = resp.json()['id']

        # Prøv å sette utskrevet med ugyldig format
        resp = self._put(pk, {'utskrevet': 'i går'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('utskrevet', resp.json()['error'])

    def test_update_patient_accepts_correct_utskrevet(self):
        resp = self._post({'problemstilling': 'Test', 'inntid': '19.04.2026 14:30'})
        pk = resp.json()['id']
        resp = self._put(pk, {'utskrevet': '19.04.2026 15:45'})
        self.assertEqual(resp.status_code, 200)

    def test_empty_time_is_accepted_on_update(self):
        """Tom streng betyr 'ikke satt' og skal være OK."""
        resp = self._post({'problemstilling': 'Test', 'inntid': '19.04.2026 14:30'})
        pk = resp.json()['id']
        resp = self._put(pk, {'pabegynt': ''})
        self.assertEqual(resp.status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PlasseringUniqueTests(TestCase):
    """Verifiserer at ikke-delte plasseringer kun kan ha én aktiv pasient."""

    def setUp(self):
        AppSetting.objects.update_or_create(key='active_year', defaults={'value': '2026'})
        self.user = CustomUser.objects.create_user(
            username='skriver', password='pass', role='read_write',
            must_change_password=False,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _post(self, data):
        import json as _j
        return self.client.post(
            '/pasienter/api/patients/',
            data=_j.dumps(data),
            content_type='application/json',
        )

    def _put(self, pk, data):
        import json as _j
        return self.client.put(
            f'/pasienter/api/patients/{pk}/',
            data=_j.dumps(data),
            content_type='application/json',
        )

    def test_unique_plassering_blokkerer_andre_pasient(self):
        """Akutt 1 kan kun ha én pasient samtidig."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 1'})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Akutt 1'})
        self.assertEqual(r2.status_code, 400)
        self.assertIn('opptatt', r2.json()['error'].lower())

    def test_gronn_sone_tillater_flere(self):
        """Grønn sone er en delt plassering og tillater flere."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Grønn sone'})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Grønn sone'})
        self.assertEqual(r2.status_code, 201)

    def test_gul_sone_tillater_flere(self):
        """Gul sone er også delt og tillater flere samtidig."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Gul sone'})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Gul sone'})
        self.assertEqual(r2.status_code, 201)

    def test_blank_plassering_blokkerer_ikke(self):
        """Blank plassering skal alltid tillates."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00', 'plassering': ''})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 14:05', 'plassering': ''})
        self.assertEqual(r2.status_code, 201)

    def test_slettet_frigir_plassering(self):
        """Hard-slettet pasient skal ikke blokkere plasseringen lenger."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Obs 1'})
        pk = r1.json()['id']
        # Hard-delete via direkte DB (tilsvarer nå API-DELETE)
        Patient.objects.filter(pk=pk).delete()
        # Nå skal en ny pasient kunne legges på Obs 1
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Obs 1'})
        self.assertEqual(r2.status_code, 201)

    def test_update_egen_plassering_tillates(self):
        """En pasient skal kunne beholde sin egen plassering ved oppdatering."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 2'})
        pk = r1.json()['id']
        # Samme plassering skal være OK (pasienten er ikke sin egen konflikt)
        r2 = self._put(pk, {'plassering': 'Akutt 2'})
        self.assertEqual(r2.status_code, 200)

    def test_update_til_opptatt_plassering_blokkeres(self):
        """Flytte en pasient til en annen pasients plassering skal feile."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 1'})
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Akutt 2'})
        pk2 = r2.json()['id']
        # Prøv å flytte B til Akutt 1 – skal feile
        r3 = self._put(pk2, {'plassering': 'Akutt 1'})
        self.assertEqual(r3.status_code, 400)
        self.assertIn('opptatt', r3.json()['error'].lower())

    def test_update_uten_plassering_paavirker_ikke(self):
        """PUT uten plassering-felt skal ikke kjøre plassering-validering."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 3'})
        pk = r1.json()['id']
        # Oppdater kun journal – plassering er ikke i payload
        r2 = self._put(pk, {'journal': 'Oppfølging'})
        self.assertEqual(r2.status_code, 200)

    def test_utskrevet_pasient_frigir_plassering_ved_post(self):
        """En utskrevet pasient (utskrevet-felt satt) skal ikke blokkere nye pasienter på samme plass."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Obs 1'})
        pk1 = r1.json()['id']
        # Skriv ut første pasient
        r_ut = self._put(pk1, {'utskrevet': '19.04.2026 15:00',
                               'utskrevet_til': 'Hjem'})
        self.assertEqual(r_ut.status_code, 200)
        # Ny pasient skal kunne plasseres på Obs 1
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 15:05',
                         'plassering': 'Obs 1'})
        self.assertEqual(r2.status_code, 201)

    def test_utskrive_pasient_med_utskrevet_historikk_paa_samme_plass(self):
        """Skal kunne skrive ut en pasient selv om en tidligere utskrevet pasient står på samme plass."""
        # Pasient 1: utskrevet fra Akutt 2
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 2'})
        pk1 = r1.json()['id']
        self._put(pk1, {'utskrevet': '19.04.2026 14:30', 'utskrevet_til': 'Hjem'})
        # Pasient 2: aktiv på Akutt 2 (siden den nå er fri)
        r2 = self._post({'problemstilling': 'B', 'inntid': '19.04.2026 14:35',
                         'plassering': 'Akutt 2'})
        pk2 = r2.json()['id']
        # Skriv ut pasient 2 – skal lykkes selv om plassering='Akutt 2' er i payload
        r3 = self._put(pk2, {'utskrevet': '19.04.2026 15:00',
                             'utskrevet_til': 'Hjem',
                             'plassering': 'Akutt 2'})
        self.assertEqual(r3.status_code, 200)

    # ── Bug-regresjon: bevar plassering ved behandler-endring ────────────────
    # Bug-rapport: "Når noen er plassert men enten endrer eller legger til
    # behandler så mister de plasseringen." Rotårsak var i frontend (hardkodet
    # dropdown), men backend må også verifisere at PUT-payload som inneholder
    # gyldig plassering ikke utilsiktet endrer den når andre felt endres.

    def test_legge_til_behandler_bevarer_plassering(self):
        """Å legge til behandler på en plassert pasient skal bevare plasseringen."""
        b = Behandler.objects.create(name='Ola')
        # Opprett pasient med plassering, uten behandler
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 1'})
        pk = r1.json()['id']
        # Simuler frontend: send full payload med behandler lagt til.
        # Plassering er fortsatt 'Akutt 1' (frontend leser .value fra dropdown).
        r2 = self._put(pk, {
            'problemstilling': 'A',
            'inntid': '19.04.2026 14:00',
            'plassering': 'Akutt 1',
            'behandler': b.id,
        })
        self.assertEqual(r2.status_code, 200)
        p = Patient.objects.get(pk=pk)
        self.assertEqual(p.plassering, 'Akutt 1')
        self.assertEqual(p.behandler_id, b.id)

    def test_endre_behandler_bevarer_plassering(self):
        """Å bytte behandler skal ikke nullstille plasseringen."""
        b1 = Behandler.objects.create(name='Ola')
        b2 = Behandler.objects.create(name='Kari')
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Obs 5', 'behandler': b1.id})
        pk = r1.json()['id']
        # Bytt behandler – send full payload med uendret plassering
        r2 = self._put(pk, {
            'problemstilling': 'A',
            'inntid': '19.04.2026 14:00',
            'plassering': 'Obs 5',
            'behandler': b2.id,
        })
        self.assertEqual(r2.status_code, 200)
        p = Patient.objects.get(pk=pk)
        self.assertEqual(p.plassering, 'Obs 5')
        self.assertEqual(p.behandler_id, b2.id)

    def test_historisk_plassering_bevares_ved_full_put(self):
        """En pasient med 'historisk' plassering (ikke i standard-dropdown) skal
        beholde plasseringen når frontend sender full PUT-payload tilbake.
        Dette er backend-siden av frontend-fixen `_ensurePlasseringOption`:
        så lenge frontend sender den faktiske verdien (i stedet for ''),
        skal backend lagre den uendret."""
        # Lag pasient direkte i DB med en 'rar' plassering (f.eks. fra CSV-import)
        p = Patient.objects.create(
            pasientnummer=1, year=2026,
            plassering='Akutt 99',  # ikke i hardkodet dropdown
            problemstilling='Historisk',
        )
        b = Behandler.objects.create(name='Ola')
        # Frontend (med fixen) sender 'Akutt 99' tilbake i payload
        r = self._put(p.pk, {
            'problemstilling': 'Historisk',
            'plassering': 'Akutt 99',
            'behandler': b.id,
        })
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.plassering, 'Akutt 99')
        self.assertEqual(p.behandler_id, b.id)

    def test_tom_plassering_i_payload_tommer_feltet(self):
        """Sanity-check av motsatt scenario: hvis frontend faktisk sender
        plassering='' (slik den gamle bugen gjorde), skal backend respektere
        det og tømme feltet. Bekrefter at fixen MÅ være på frontend-siden."""
        r1 = self._post({'problemstilling': 'A', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 3'})
        pk = r1.json()['id']
        r2 = self._put(pk, {'plassering': ''})
        self.assertEqual(r2.status_code, 200)
        p = Patient.objects.get(pk=pk)
        self.assertEqual(p.plassering, '')


# ── Helsepersonell-modell og FK ──────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class HelsepersonellTests(TestCase):
    """Tester for Helsepersonell-modell, API og FK-integritet."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin', password='pwd', role='admin', must_change_password=False
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_create_helsepersonell(self):
        """Admin kan opprette ny helsepersonell via API."""
        res = self.client.post(
            '/pasienter/api/helsepersonell/',
            data='{"name": "Kari"}',
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Helsepersonell.objects.count(), 1)
        self.assertEqual(Helsepersonell.objects.first().name, 'Kari')

    def test_duplicate_name_rejected(self):
        """Samme navn skal avvises med 400."""
        Helsepersonell.objects.create(name='Kari')
        res = self.client.post(
            '/pasienter/api/helsepersonell/',
            data='{"name": "Kari"}',
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)

    def test_list_with_etag(self):
        """GET returnerer ETag, og If-None-Match gir 304."""
        Helsepersonell.objects.create(name='Kari')
        res1 = self.client.get('/pasienter/api/helsepersonell/')
        self.assertEqual(res1.status_code, 200)
        etag = res1.get('ETag')
        self.assertTrue(etag)
        res2 = self.client.get('/pasienter/api/helsepersonell/', HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(res2.status_code, 304)

    def test_cannot_delete_helsepersonell_in_use(self):
        """Helsepersonell brukt av pasient kan ikke slettes (PROTECT)."""
        from django.db.models.deletion import ProtectedError
        h = Helsepersonell.objects.create(name='Bruk')
        Patient.objects.create(pasientnummer=1, year=2026, helsepersonell_ref=h)
        with self.assertRaises(ProtectedError):
            h.delete()

    def test_inactive_helsepersonell_preserves_history(self):
        """Deaktivering bryter ikke pasient-FK."""
        h = Helsepersonell.objects.create(name='Historisk')
        p = Patient.objects.create(pasientnummer=1, year=2025, helsepersonell_ref=h)
        h.is_active = False
        h.save()
        p.refresh_from_db()
        self.assertEqual(p.helsepersonell_ref, h)

    def test_pabegynt_triggered_by_helsepersonell_ref(self):
        """stamp_pabegynt_if_needed skal sette påbegynt når helsepersonell_ref settes."""
        h = Helsepersonell.objects.create(name='Kari')
        p = Patient(pasientnummer=1, year=2026)
        result = stamp_pabegynt_if_needed(p, {'helsepersonell_ref': h.id})
        self.assertTrue(result)
        self.assertTrue(p.pabegynt)

    def test_patient_post_with_helsepersonell_ref(self):
        """POST /api/patients/ med helsepersonell_ref ID kobler FK korrekt."""
        h = Helsepersonell.objects.create(name='Kari')
        import json
        res = self.client.post(
            '/pasienter/api/patients/',
            data=json.dumps({
                'problemstilling': 'Test',
                'inntid': '19.04.2026 14:00',
                'plassering': 'Akutt 1',
                'helsepersonell_ref': h.id,
            }),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertIsNotNone(body.get('helsepersonell_ref'))
        self.assertEqual(body['helsepersonell_ref']['id'], h.id)
        self.assertEqual(body['helsepersonell_ref']['name'], 'Kari')

    def test_patient_put_clears_helsepersonell_ref(self):
        """PUT med helsepersonell_ref=null skal nullstille FK."""
        h = Helsepersonell.objects.create(name='Kari')
        p = Patient.objects.create(pasientnummer=1, year=2026, helsepersonell_ref=h,
                                    inntid='19.04.2026 14:00')
        import json
        res = self.client.put(
            f'/pasienter/api/patients/{p.pk}/',
            data=json.dumps({'helsepersonell_ref': None}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        p.refresh_from_db()
        self.assertIsNone(p.helsepersonell_ref)

    def test_non_admin_cannot_create(self):
        """Read-write-rolle skal ikke kunne opprette helsepersonell."""
        self.client.logout()
        rw = CustomUser.objects.create_user(username='rw', password='pwd', role='read_write', must_change_password=False)
        self.client.force_login(rw)
        res = self.client.post(
            '/pasienter/api/helsepersonell/',
            data='{"name": "Nei"}',
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 403)


class DoubleClickGuardTests(TestCase):
    """
    Verifiserer beskyttelse mot dobbeltklikk-registrering (Fix A).

    Bakgrunn: 30. april 2026 ble en pasient registrert dobbelt opp på Grønn sone
    fordi brukeren dobbeltklikket på "Registrer pasient"-knappen mens serveren
    fortsatt prosesserte første request. På delte soner (Grønn/Gul/blank) finnes
    ingen unik-sjekk, så begge requests gikk gjennom og skapte to pasienter.

    Fixen er implementert frontend-side via `withSubmitGuard()` i script.js, som
    disabler knappen umiddelbart, viser spinner og holder lock i minst 250 ms.
    Server-side idempotency er sporet som FORBEDRINGER #18 for senere hårdere
    beskyttelse mot API-klienter (Postman/curl) som omgår UI.

    Disse testene verifiserer at fixen er installert i frontend-koden:

    1. withSubmitGuard-helperen finnes i script.js
    2. saveNew() og saveEdit() er begge wrappet med guarden
    3. Lagre-knappene har stabile id-er som guarden refererer til
    """

    # ── Frontend-koblings-tester (verifiserer at fixen er installert) ──

    def test_script_js_has_submit_guard_helper(self):
        """withSubmitGuard-helperen må være definert i script.js."""
        from pathlib import Path
        from django.conf import settings
        js_path = Path(settings.BASE_DIR) / 'static' / 'js' / 'script.js'
        self.assertTrue(js_path.exists(), 'script.js mangler')
        content = js_path.read_text(encoding='utf-8')
        self.assertIn('async function withSubmitGuard(', content,
                      'withSubmitGuard-helperen mangler i script.js')
        self.assertIn('dataset.submitting', content,
                      'In-flight lock-mekanismen mangler i withSubmitGuard')

    def test_save_new_uses_submit_guard(self):
        """saveNew() må wrappes med withSubmitGuard for å hindre dobbeltklikk."""
        from pathlib import Path
        from django.conf import settings
        js_path = Path(settings.BASE_DIR) / 'static' / 'js' / 'script.js'
        content = js_path.read_text(encoding='utf-8')
        # saveNew skal kalle withSubmitGuard med btn-save-new
        self.assertIn("withSubmitGuard('btn-save-new'", content,
                      'saveNew() er ikke beskyttet av withSubmitGuard')

    def test_save_edit_uses_submit_guard(self):
        """saveEdit() må også wrappes for å hindre dobbeltlagring av endringer."""
        from pathlib import Path
        from django.conf import settings
        js_path = Path(settings.BASE_DIR) / 'static' / 'js' / 'script.js'
        content = js_path.read_text(encoding='utf-8')
        self.assertIn("withSubmitGuard('btn-save-edit'", content,
                      'saveEdit() er ikke beskyttet av withSubmitGuard')

    def test_save_buttons_have_stable_ids_in_template(self):
        """Lagre-knappene må ha id-ene som withSubmitGuard refererer til."""
        from pathlib import Path
        from django.conf import settings
        tpl = Path(settings.BASE_DIR) / 'templates' / 'patients' / 'index.html'
        self.assertTrue(tpl.exists(), 'index.html mangler')
        content = tpl.read_text(encoding='utf-8')
        self.assertIn('id="btn-save-new"', content,
                      'btn-save-new-id mangler på "Registrer pasient"-knappen')
        self.assertIn('id="btn-save-edit"', content,
                      'btn-save-edit-id mangler på "Lagre endringer"-knappen')



# ── FORBEDRINGER #19 + klokkedrift-fix ───────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PatientNumberGapTests(TestCase):
    """Tester for at pasientnummer ikke hopper når validering feiler.

    Bug: next_patient_nr() ble tidligere kalt før validate_plassering_unique().
    Hvis valideringen feilet, ble telleren økt uten at pasienten ble lagret,
    og neste vellykkede registrering fikk et nummer høyere enn forrige + 1.
    """

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='testbruker', password='Test1234!', role='admin',
            must_change_password=False,
        )
        self.client.login(username='testbruker', password='Test1234!')
        set_active_year(2026)
        # Eksisterende pasient på unik plassering "Båre 1"
        self.existing = Patient.objects.create(
            pasientnummer=1, year=2026, plassering='Båre 1',
            grovsortering='Rød',
        )
        # Synkroniser AppSetting-telleren med den manuelle pasienten over.
        # next_patient_nr() leser fra AppSetting, ikke MAX(Patient.pasientnummer),
        # så vi må sette telleren til 2 for at neste registrering skal bli nr=2.
        AppSetting.objects.update_or_create(
            key='next_patient_nr',
            defaults={'value': '2'},
        )

    def _post_patient(self, plassering, grovsortering='Grønn'):
        return self.client.post(
            reverse('api_patients_list'),
            data={'plassering': plassering, 'grovsortering': grovsortering},
            content_type='application/json',
        )

    def test_failed_validation_does_not_consume_number(self):
        """En mislykket POST skal ikke øke pasientnummer-telleren."""
        # Forsøk å registrere ny pasient på opptatt plassering
        resp = self._post_patient('Båre 1')
        self.assertEqual(resp.status_code, 400)

        # AppSetting-telleren skal fortsatt stå på 2 (ikke konsumert)
        teller = AppSetting.objects.get(key='next_patient_nr').value
        self.assertEqual(teller, '2',
            f'Telleren ble inkrementert til {teller} selv om valideringen feilet')

        # Neste vellykkede registrering skal få nummer 2, ikke 3
        resp_ok = self._post_patient('Båre 2')
        self.assertEqual(resp_ok.status_code, 201)
        self.assertEqual(resp_ok.json()['pasientnummer'], 2)

    def test_successful_creation_increments_normally(self):
        """Vanlig sekvensiell oppretting skal fortsatt fungere."""
        r1 = self._post_patient('Båre 2')
        r2 = self._post_patient('Båre 3')
        self.assertEqual(r1.json()['pasientnummer'], 2)
        self.assertEqual(r2.json()['pasientnummer'], 3)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PabegyntNotBeforeInntidTests(TestCase):
    """Tester for sikkerhetsnett mot pabegynt < inntid (klient-klokkedrift)."""

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='testbruker', password='Test1234!', role='admin',
            must_change_password=False,
        )
        self.client.login(username='testbruker', password='Test1234!')
        set_active_year(2026)
        self.behandler = Behandler.objects.create(name='Lege Hansen')

    def test_helper_adjusts_pabegynt_when_before_inntid(self):
        """_ensure_pabegynt_not_before_inntid skal sette pabegynt = inntid."""
        from patients.views import _ensure_pabegynt_not_before_inntid
        p = Patient(
            pasientnummer=99, year=2026,
            inntid='01.05.2026 17:32',
            pabegynt='01.05.2026 17:29',  # 3 min før inntid (klokkedrift)
        )
        changed = _ensure_pabegynt_not_before_inntid(p)
        self.assertTrue(changed)
        self.assertEqual(p.pabegynt, '01.05.2026 17:32')

    def test_helper_leaves_pabegynt_alone_when_after_inntid(self):
        """Hvis pabegynt > inntid, skal verdien beholdes."""
        from patients.views import _ensure_pabegynt_not_before_inntid
        p = Patient(
            pasientnummer=99, year=2026,
            inntid='01.05.2026 17:00',
            pabegynt='01.05.2026 17:15',
        )
        changed = _ensure_pabegynt_not_before_inntid(p)
        self.assertFalse(changed)
        self.assertEqual(p.pabegynt, '01.05.2026 17:15')

    def test_helper_handles_blank_fields(self):
        """Hvis et av feltene er tomt, skal helperen ikke gjøre noe."""
        from patients.views import _ensure_pabegynt_not_before_inntid
        p1 = Patient(pasientnummer=99, year=2026, inntid='', pabegynt='01.05.2026 17:00')
        p2 = Patient(pasientnummer=99, year=2026, inntid='01.05.2026 17:00', pabegynt='')
        self.assertFalse(_ensure_pabegynt_not_before_inntid(p1))
        self.assertFalse(_ensure_pabegynt_not_before_inntid(p2))

    def test_helper_handles_invalid_format_gracefully(self):
        """Ugyldig format skal ikke kaste exception."""
        from patients.views import _ensure_pabegynt_not_before_inntid
        p = Patient(
            pasientnummer=99, year=2026,
            inntid='ikke-en-dato',
            pabegynt='01.05.2026 17:00',
        )
        # Skal ikke kaste – returnerer False
        changed = _ensure_pabegynt_not_before_inntid(p)
        self.assertFalse(changed)

    def test_create_with_drifting_client_clock_yields_consistent_times(self):
        """End-to-end: klient sender inntid 3 min frem, behandler i samme request.

        Etter fix skal pabegynt ikke være før inntid – sikkerhetsnettet
        justerer pabegynt opp til inntid-verdien.
        """
        # Frontend simulerer en klient med klokke 3 min foran serveren
        future_inntid = '01.05.2026 17:32'
        resp = self.client.post(
            reverse('api_patients_list'),
            data={
                'inntid': future_inntid,
                'plassering': 'Båre 1',
                'grovsortering': 'Grønn',
                'behandler': self.behandler.pk,  # trigger pabegynt-stempling
            },
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()

        # pabegynt skal aldri være før inntid
        fmt = '%d.%m.%Y %H:%M'
        t_inn = datetime.strptime(body['inntid'], fmt)
        t_pab = datetime.strptime(body['pabegynt'], fmt)
        self.assertGreaterEqual(t_pab, t_inn,
            f'pabegynt ({body["pabegynt"]}) må være >= inntid ({body["inntid"]})')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BlankInntidFallbackTests(TestCase):
    """Hvis frontend sender inntid='' skal server-tid brukes som fallback."""

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='testbruker', password='Test1234!', role='admin',
            must_change_password=False,
        )
        self.client.login(username='testbruker', password='Test1234!')
        set_active_year(2026)

    def test_blank_inntid_uses_server_now(self):
        """Tom inntid-streng skal erstattes av server-now-stempel."""
        resp = self.client.post(
            reverse('api_patients_list'),
            data={'inntid': '', 'plassering': 'Båre 1', 'grovsortering': 'Grønn'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        # Skal være et gyldig dd.mm.YYYY HH:MM-stempel, ikke tom streng
        self.assertNotEqual(body['inntid'], '')
        # Skal kunne parses
        datetime.strptime(body['inntid'], '%d.%m.%Y %H:%M')


class NowLocalStrTests(TestCase):
    """Tester for now_local_str() – returnerer Europe/Oslo-tid uavh. av container-TZ."""

    def test_now_local_str_returns_correct_format(self):
        """Skal returnere 'dd.mm.YYYY HH:MM'-streng."""
        from patients.services import now_local_str
        import re
        result = now_local_str()
        self.assertRegex(result, r'^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$')
        # Skal kunne parses
        datetime.strptime(result, '%d.%m.%Y %H:%M')

    def test_now_local_str_uses_django_timezone(self):
        """now_local_str skal bruke Djangos TIME_ZONE, ikke system-tid.

        Verifiserer at funksjonen bruker timezone.localtime() som honorerer
        TIME_ZONE='Europe/Oslo' selv om containeren kjører i UTC.
        """
        from django.utils import timezone as djtz
        from patients.services import now_local_str
        # Sammenlign med direkte localtime-kall – skal være samme minutt
        expected = djtz.localtime(djtz.now()).strftime('%d.%m.%Y %H:%M')
        self.assertEqual(now_local_str(), expected)
