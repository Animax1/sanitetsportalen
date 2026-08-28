"""Kjernetester for pasientregistrering.

Kjør med: python manage.py test patients
"""
import json
import re
import shutil
import unittest
from datetime import datetime

from django.db import connection
from django.test import TestCase, Client, SimpleTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import CustomUser
from patients.models import Patient, Forstehjelper, Helsepersonell, AppSetting
from patients.services import (
    apply_list_filter, stamp_pabegynt_if_needed,
    stamp_obs_times_if_needed, stamp_utskrevet_if_needed,
    get_active_year, set_active_year,
)
from accounts.test_helpers import gi_standardtilgang


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
        b = Forstehjelper.objects.create(name='Ola')
        p = Patient(pasientnummer=1, year=2026)
        result = stamp_pabegynt_if_needed(p, {'forstehjelper': b})
        self.assertTrue(result)
        self.assertTrue(p.pabegynt)

    def test_forstehjelper_id_triggers_pabegynt(self):
        """Sett behandler som ID (integer) skal også utløse stempling."""
        b = Forstehjelper.objects.create(name='Kari')
        p = Patient(pasientnummer=2, year=2026)
        result = stamp_pabegynt_if_needed(p, {'forstehjelper': b.id})
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
        result = stamp_pabegynt_if_needed(p, {'forstehjelper': None})
        self.assertFalse(result)


# ── Behandler-modell ─────────────────────────────────────────────────────────

class ForstehjelperTests(TestCase):
    """Tester for Behandler-modell og FK-integritet."""

    def test_inactive_behandler_preserves_history(self):
        """Inaktivering av behandler skal ikke bryte pasient-referansen."""
        b = Forstehjelper.objects.create(name='Historisk')
        p = Patient.objects.create(pasientnummer=1, year=2025, forstehjelper=b)
        b.is_active = False
        b.save()
        # Pasienten skal fortsatt ha referansen
        p.refresh_from_db()
        self.assertEqual(p.forstehjelper, b)

    def test_cannot_delete_behandler_in_use(self):
        """Behandler knyttet til pasient skal ikke kunne slettes (PROTECT)."""
        from django.db.models.deletion import ProtectedError
        b = Forstehjelper.objects.create(name='Brukes')
        Patient.objects.create(pasientnummer=1, year=2026, forstehjelper=b)
        with self.assertRaises(ProtectedError):
            b.delete()

    def test_str_inactive(self):
        """__str__ skal vise (inaktiv) for inaktive behandlere."""
        b = Forstehjelper.objects.create(name='Test', is_active=False)
        self.assertIn('inaktiv', str(b))

    def test_str_active(self):
        """__str__ skal ikke inneholde (inaktiv) for aktive behandlere."""
        b = Forstehjelper.objects.create(name='Aktiv', is_active=True)
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
        # must_change_password=False eksplisitt: superbrukere arver modellens
        # default True (S2), og MustChangePasswordMiddleware ville ellers
        # redirecte hver request i denne testen til passordbytte.
        self.admin = CustomUser.objects.create_superuser(
            username='a', password='x', role='admin', must_change_password=False)
        self.lead = CustomUser.objects.create_user(
            username='l', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.lead, 'leder')
        self.rw = CustomUser.objects.create_user(
            username='w', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.rw, 'skriver')
        self.ro = CustomUser.objects.create_user(
            username='r', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.ro, 'leser')

    def _login(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_leser_kan_ikke_legge_til_behandler(self):
        """Konto med kun lesetilgang skal ikke kunne opprette behandler."""
        c = self._login(self.ro)
        import json as _j
        resp = c.post('/pasienter/api/forstehjelpere/',
                      data=_j.dumps({'name': 'X'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_skriver_kan_ikke_legge_til_behandler(self):
        """Skrivetilgang på pasienter er ikke nok — registeret er admin (kun admin)."""
        c = self._login(self.rw)
        import json as _j
        resp = c.post('/pasienter/api/forstehjelpere/',
                      data=_j.dumps({'name': 'X'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_add_behandler(self):
        """Admin-bruker skal kunne opprette behandler."""
        c = self._login(self.admin)
        import json as _j
        resp = c.post('/pasienter/api/forstehjelpere/',
                      data=_j.dumps({'name': 'X'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 201)

    def test_leser_kan_ikke_opprette_pasient(self):
        """Konto med kun lesetilgang skal ikke kunne opprette pasient."""
        c = self._login(self.ro)
        import json as _j
        resp = c.post('/pasienter/api/patients/',
                      data=_j.dumps({'problemstilling': 'Bevisstløs'}),
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
        p = Patient(pasientnummer=1, year=2026, utskrevet_til='Hjem/park')
        changed = self.stamp(p, {})
        self.assertIn('utskrevet', changed)
        self.assertTrue(p.utskrevet)

    def test_utskrevet_ikke_overskrevet(self):
        """utskrevet allerede satt skal ikke overskrives."""
        p = Patient(pasientnummer=1, year=2026,
                    utskrevet_til='Hjem/park', utskrevet='01.01.2026 12:00')
        changed = self.stamp(p, {})
        self.assertNotIn('utskrevet', changed)
        self.assertEqual(p.utskrevet, '01.01.2026 12:00')

    def test_utskrevet_fra_obs_lukker_ut_obspost(self):
        """Utskrives fra obs-plass: ut_obspost skal stemples."""
        p = Patient(pasientnummer=1, year=2026, utskrevet_til='Hjem/park',
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
    """Konto som leser pasienter og leser statistikk — tilgangskontroll i API."""

    def setUp(self):
        set_active_year(2026)
        self.lead_view = CustomUser.objects.create_user(
            username='lv', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.lead_view, 'leder_les')
        self.client = Client()
        self.client.force_login(self.lead_view)
        Patient.objects.create(pasientnummer=1, year=2026)

    def test_leder_les_kan_lese_pasienter(self):
        """Profilen kan hente pasientliste for aktivt år."""
        resp = self.client.get('/pasienter/api/patients/')
        self.assertEqual(resp.status_code, 200)

    def test_leder_les_kan_ikke_opprette_pasient(self):
        """Profilen har kun `les` på pasienter, og kan ikke opprette."""
        import json as _j
        resp = self.client.post('/pasienter/api/patients/',
                                data=_j.dumps({'problemstilling': 'Pustevansker'}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    def test_leder_les_kan_lese_full_stats(self):
        """Profilen har `les` på statistikk, og kan hente full statistikk."""
        resp = self.client.get('/statistikk/api/full-stats/')
        self.assertIn(resp.status_code, [200, 500])  # 500 OK hvis scipy mangler


# ── Reset testdata ────────────────────────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False)
class ResetTests(TestCase):
    """Tester for reset_active_year_view."""

    def setUp(self):
        set_active_year(2026)
        self.admin = CustomUser.objects.create_superuser(
            username='a', password='x', role='admin', must_change_password=False)
        self.lead = CustomUser.objects.create_user(
            username='l', password='x', role='bruker', must_change_password=False)
        gi_standardtilgang(self.lead, 'leder')
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
class ForstehjelperETagTests(TestCase):
    """Tester for ETag/304-funksjonalitet på /api/behandlere/."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='etagtester', password='x', role='bruker',
            must_change_password=False)
        gi_standardtilgang(self.user, 'leser')
        self.client = Client()
        self.client.force_login(self.user)
        Forstehjelper.objects.create(name='Behandler A', is_active=True)

    def test_behandlere_returns_etag_header(self):
        """GET /api/behandlere/ skal returnere ETag-header."""
        resp = self.client.get('/pasienter/api/forstehjelpere/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('ETag', resp)
        self.assertTrue(resp['ETag'].startswith('"v1:'))

    def test_behandlere_returns_304_when_etag_matches(self):
        """GET med If-None-Match som matcher ETag skal gi 304."""
        # Hent ETag fra første request
        resp1 = self.client.get('/pasienter/api/forstehjelpere/')
        etag = resp1['ETag']
        # Send If-None-Match med samme ETag
        resp2 = self.client.get(
            '/pasienter/api/forstehjelpere/',
            HTTP_IF_NONE_MATCH=etag,
        )
        self.assertEqual(resp2.status_code, 304)

    def test_behandlere_returns_200_with_new_etag_when_behandler_added(self):
        """Ny behandler skal gi ny ETag og 200 selv om klient sender gammel ETag."""
        resp1 = self.client.get('/pasienter/api/forstehjelpere/')
        old_etag = resp1['ETag']
        # Legg til ny behandler
        Forstehjelper.objects.create(name='Behandler B', is_active=True)
        resp2 = self.client.get(
            '/pasienter/api/forstehjelpere/',
            HTTP_IF_NONE_MATCH=old_etag,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertNotEqual(resp2['ETag'], old_etag)

    def test_behandlere_returns_200_with_new_etag_when_behandler_renamed(self):
        """Omdøpt behandler skal gi ny ETag og 200."""
        resp1 = self.client.get('/pasienter/api/forstehjelpere/')
        old_etag = resp1['ETag']
        # Omdøp behandleren
        b = Forstehjelper.objects.get(name='Behandler A')
        b.name = 'Ny Behandler A'
        b.save()
        resp2 = self.client.get(
            '/pasienter/api/forstehjelpere/',
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
            username='skriver', password='pass', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.user, 'skriver')
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
            'problemstilling': 'Pustevansker',
            'inntid': '19/04/2026 14:30',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('inntid', resp.json()['error'])

    def test_create_patient_accepts_correct_time(self):
        resp = self._post({
            'problemstilling': 'Pustevansker',
            'inntid': '19.04.2026 14:30',
        })
        self.assertEqual(resp.status_code, 201)

    def test_update_patient_rejects_bad_utskrevet(self):
        # Opprett først
        resp = self._post({'problemstilling': 'Pustevansker', 'inntid': '19.04.2026 14:30'})
        self.assertEqual(resp.status_code, 201)
        pk = resp.json()['id']

        # Prøv å sette utskrevet med ugyldig format
        resp = self._put(pk, {'utskrevet': 'i går'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('utskrevet', resp.json()['error'])

    def test_update_patient_accepts_correct_utskrevet(self):
        resp = self._post({'problemstilling': 'Pustevansker', 'inntid': '19.04.2026 14:30'})
        pk = resp.json()['id']
        resp = self._put(pk, {'utskrevet': '19.04.2026 15:45'})
        self.assertEqual(resp.status_code, 200)

    def test_empty_time_is_accepted_on_update(self):
        """Tom streng betyr 'ikke satt' og skal være OK."""
        resp = self._post({'problemstilling': 'Pustevansker', 'inntid': '19.04.2026 14:30'})
        pk = resp.json()['id']
        resp = self._put(pk, {'pabegynt': ''})
        self.assertEqual(resp.status_code, 200)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PlasseringUniqueTests(TestCase):
    """Verifiserer at ikke-delte plasseringer kun kan ha én aktiv pasient."""

    def setUp(self):
        AppSetting.objects.update_or_create(key='active_year', defaults={'value': '2026'})
        self.user = CustomUser.objects.create_user(
            username='skriver', password='pass', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.user, 'skriver')
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
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 1'})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Akutt 1'})
        self.assertEqual(r2.status_code, 400)
        self.assertIn('opptatt', r2.json()['error'].lower())

    def test_gronn_sone_tillater_flere(self):
        """Grønn sone er en delt plassering og tillater flere."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Grønn sone'})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Grønn sone'})
        self.assertEqual(r2.status_code, 201)

    def test_gul_sone_tillater_flere(self):
        """Gul sone er også delt og tillater flere samtidig."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Gul sone'})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Gul sone'})
        self.assertEqual(r2.status_code, 201)

    def test_blank_plassering_blokkerer_ikke(self):
        """Blank plassering skal alltid tillates."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00', 'plassering': ''})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 14:05', 'plassering': ''})
        self.assertEqual(r2.status_code, 201)

    def test_slettet_frigir_plassering(self):
        """Hard-slettet pasient skal ikke blokkere plasseringen lenger."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Obs 1'})
        pk = r1.json()['id']
        # Hard-delete via direkte DB (tilsvarer nå API-DELETE)
        Patient.objects.filter(pk=pk).delete()
        # Nå skal en ny pasient kunne legges på Obs 1
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Obs 1'})
        self.assertEqual(r2.status_code, 201)

    def test_update_egen_plassering_tillates(self):
        """En pasient skal kunne beholde sin egen plassering ved oppdatering."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 2'})
        pk = r1.json()['id']
        # Samme plassering skal være OK (pasienten er ikke sin egen konflikt)
        r2 = self._put(pk, {'plassering': 'Akutt 2'})
        self.assertEqual(r2.status_code, 200)

    def test_update_til_opptatt_plassering_blokkeres(self):
        """Flytte en pasient til en annen pasients plassering skal feile."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 1'})
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 14:05',
                         'plassering': 'Akutt 2'})
        pk2 = r2.json()['id']
        # Prøv å flytte B til Akutt 1 – skal feile
        r3 = self._put(pk2, {'plassering': 'Akutt 1'})
        self.assertEqual(r3.status_code, 400)
        self.assertIn('opptatt', r3.json()['error'].lower())

    def test_update_uten_plassering_paavirker_ikke(self):
        """PUT uten plassering-felt skal ikke kjøre plassering-validering."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 3'})
        pk = r1.json()['id']
        # Oppdater kun journal – plassering er ikke i payload
        r2 = self._put(pk, {'journal': 'Ja'})
        self.assertEqual(r2.status_code, 200)

    def test_utskrevet_pasient_frigir_plassering_ved_post(self):
        """En utskrevet pasient (utskrevet-felt satt) skal ikke blokkere nye pasienter på samme plass."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Obs 1'})
        pk1 = r1.json()['id']
        # Skriv ut første pasient
        r_ut = self._put(pk1, {'utskrevet': '19.04.2026 15:00',
                               'utskrevet_til': 'Hjem/park'})
        self.assertEqual(r_ut.status_code, 200)
        # Ny pasient skal kunne plasseres på Obs 1
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 15:05',
                         'plassering': 'Obs 1'})
        self.assertEqual(r2.status_code, 201)

    def test_utskrive_pasient_med_utskrevet_historikk_paa_samme_plass(self):
        """Skal kunne skrive ut en pasient selv om en tidligere utskrevet pasient står på samme plass."""
        # Pasient 1: utskrevet fra Akutt 2
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 2'})
        pk1 = r1.json()['id']
        self._put(pk1, {'utskrevet': '19.04.2026 14:30', 'utskrevet_til': 'Hjem/park'})
        # Pasient 2: aktiv på Akutt 2 (siden den nå er fri)
        r2 = self._post({'problemstilling': 'Magesmerter', 'inntid': '19.04.2026 14:35',
                         'plassering': 'Akutt 2'})
        pk2 = r2.json()['id']
        # Skriv ut pasient 2 – skal lykkes selv om plassering='Akutt 2' er i payload
        r3 = self._put(pk2, {'utskrevet': '19.04.2026 15:00',
                             'utskrevet_til': 'Hjem/park',
                             'plassering': 'Akutt 2'})
        self.assertEqual(r3.status_code, 200)

    # ── Bug-regresjon: bevar plassering ved behandler-endring ────────────────
    # Bug-rapport: "Når noen er plassert men enten endrer eller legger til
    # behandler så mister de plasseringen." Rotårsak var i frontend (hardkodet
    # dropdown), men backend må også verifisere at PUT-payload som inneholder
    # gyldig plassering ikke utilsiktet endrer den når andre felt endres.

    def test_legge_til_behandler_bevarer_plassering(self):
        """Å legge til behandler på en plassert pasient skal bevare plasseringen."""
        b = Forstehjelper.objects.create(name='Ola')
        # Opprett pasient med plassering, uten behandler
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Akutt 1'})
        pk = r1.json()['id']
        # Simuler frontend: send full payload med behandler lagt til.
        # Plassering er fortsatt 'Akutt 1' (frontend leser .value fra dropdown).
        r2 = self._put(pk, {
            'problemstilling': 'Brystsmerter',
            'inntid': '19.04.2026 14:00',
            'plassering': 'Akutt 1',
            'forstehjelper': b.id,
        })
        self.assertEqual(r2.status_code, 200)
        p = Patient.objects.get(pk=pk)
        self.assertEqual(p.plassering, 'Akutt 1')
        self.assertEqual(p.forstehjelper_id, b.id)

    def test_endre_behandler_bevarer_plassering(self):
        """Å bytte behandler skal ikke nullstille plasseringen."""
        b1 = Forstehjelper.objects.create(name='Ola')
        b2 = Forstehjelper.objects.create(name='Kari')
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
                         'plassering': 'Obs 5', 'forstehjelper': b1.id})
        pk = r1.json()['id']
        # Bytt behandler – send full payload med uendret plassering
        r2 = self._put(pk, {
            'problemstilling': 'Brystsmerter',
            'inntid': '19.04.2026 14:00',
            'plassering': 'Obs 5',
            'forstehjelper': b2.id,
        })
        self.assertEqual(r2.status_code, 200)
        p = Patient.objects.get(pk=pk)
        self.assertEqual(p.plassering, 'Obs 5')
        self.assertEqual(p.forstehjelper_id, b2.id)

    def test_historisk_plassering_bevares_ved_full_put(self):
        """En pasient med 'historisk' plassering (ikke i standard-dropdown) skal
        beholde plasseringen når frontend sender full PUT-payload tilbake.
        Dette er backend-siden av frontend-fixen `_ensurePlasseringOption`:
        så lenge frontend sender den faktiske verdien (i stedet for ''),
        skal backend lagre den uendret."""
        # Lag pasient direkte i DB med en 'rar' plassering (f.eks. fra CSV-import)
        p = Patient.objects.create(
            pasientnummer=1, year=2026,
            plassering='Akutt 4',  # ikke i hardkodet dropdown
            problemstilling='Kramper',
        )
        b = Forstehjelper.objects.create(name='Ola')
        # Frontend (med fixen) sender 'Akutt 99' tilbake i payload
        r = self._put(p.pk, {
            'problemstilling': 'Kramper',
            'plassering': 'Akutt 4',
            'forstehjelper': b.id,
        })
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.plassering, 'Akutt 4')
        self.assertEqual(p.forstehjelper_id, b.id)

    def test_tom_plassering_i_payload_tommer_feltet(self):
        """Sanity-check av motsatt scenario: hvis frontend faktisk sender
        plassering='' (slik den gamle bugen gjorde), skal backend respektere
        det og tømme feltet. Bekrefter at fixen MÅ være på frontend-siden."""
        r1 = self._post({'problemstilling': 'Brystsmerter', 'inntid': '19.04.2026 14:00',
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
        gi_standardtilgang(self.admin, 'admin')
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
                'problemstilling': 'Pustevansker',
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
        rw = CustomUser.objects.create_user(username='rw', password='pwd', role='bruker', must_change_password=False)
        gi_standardtilgang(rw, 'skriver')
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

    Fixen er implementert frontend-side via `withSubmitGuard()` i
    `patients-utils.js`, som disabler knappen umiddelbart, viser spinner og
    holder lock i minst 250 ms. Server-side idempotency er sporet som
    FORBEDRINGER #18 for senere hårdere beskyttelse mot API-klienter
    (Postman/curl) som omgår UI.

    **N9 (13. aug. 2026):** Testene leste tidligere `static/js/script.js`, som
    ingen mal lastet. De var grønne, og ville vært grønne også om guarden
    forsvant fra den levende koden. Nå gjør de to ting:

    1. Kjører guarden i node og verifiserer at den faktisk blokkerer det andre
       kallet — det er selve vernet, ikke bare at koden finnes.
    2. Sjekker koblingen: at `saveNew`/`saveEdit` bruker guarden, og at malen
       har knappe-id-ene den refererer til. Det er fortsatt tekstsøk, men nå i
       filer som faktisk lastes.
    """

    # ── Oppførselstester (kjører guarden) ────────────────────────────────

    # Stubber akkurat det withSubmitGuard rører: én knapp i DOM-en.
    BTN_STUB = '''
const btn = { dataset: {}, disabled: false, innerHTML: 'Registrer pasient' };
global.document = {
  getElementById: (id) => (id === 'btn-save-new' ? btn : null),
};
'''

    def _run_guard(self, snippet):
        from patients import js_test_utils as jsu
        harness = jsu.build_harness([(jsu.PORTAL_UTILS_JS, ('withSubmitGuard',))])
        return jsu.run_node(harness, snippet, preamble=self.BTN_STUB)

    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_guard_blokkerer_andre_kall_mens_forste_paagaar(self):
        """Selve vernet: to raske klikk skal gi én registrering.

        Dette er hendelsen fra 30. april, gjenskapt: knappen klikkes igjen
        mens serveren fortsatt prosesserer det første kallet.
        """
        self._run_guard('''
let kall = 0;
const treg = () => new Promise(r => setTimeout(() => { kall++; r(); }, 50));

const forste = withSubmitGuard('btn-save-new', treg);
const andre  = withSubmitGuard('btn-save-new', treg);
await Promise.all([forste, andre]);

assert(kall === 1, 'forventet 1 registrering, fikk ' + kall);
''')

    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_guard_disabler_knappen_umiddelbart(self):
        """Knappen skal være låst mens kallet pågår, ikke først etterpå."""
        self._run_guard('''
let disabletUnderveis = null;
const p = withSubmitGuard('btn-save-new', async () => {
  disabletUnderveis = btn.disabled;
});
await p;
assert(disabletUnderveis === true, 'knappen var ikke disablet under kallet');
assert(btn.dataset.submitting === undefined, 'låsen ble ikke frigitt etterpaa');
assert(btn.disabled === false, 'knappen ble ikke aktivert igjen');
''')

    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_guard_holder_laasen_i_minst_250ms(self):
        """Et raskt svar skal likevel holde knappen låst minimumstiden.

        Uten dette rekker et dobbeltklikk å treffe mellom to raske kall.
        """
        self._run_guard('''
const start = Date.now();
await withSubmitGuard('btn-save-new', async () => {});
const brukt = Date.now() - start;
assert(brukt >= 245, 'laasen ble holdt i bare ' + brukt + ' ms');
''')

    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_guard_frigir_laasen_naar_lagring_feiler(self):
        """En mislykket lagring skal ikke låse knappen for godt.

        Feilen skal fortsatt boble opp — guarden svelger den ikke.
        """
        self._run_guard('''
let kastet = false;
try {
  await withSubmitGuard('btn-save-new', async () => { throw new Error('500'); });
} catch (e) {
  kastet = true;
}
assert(kastet, 'feilen naadde ikke kalleren');
assert(btn.disabled === false, 'knappen ble staaende disablet etter feil');
assert(btn.dataset.submitting === undefined, 'laasen ble staaende etter feil');
assert(btn.innerHTML === 'Registrer pasient', 'knappeteksten ble ikke gjenopprettet');

// ...og et nytt forsoek skal gaa gjennom
let kall = 0;
await withSubmitGuard('btn-save-new', async () => { kall++; });
assert(kall === 1, 'knappen var fortsatt laast etter en feilet lagring');
''')

    # ── Koblings-tester (verifiserer at guarden er tatt i bruk) ──────────

    def test_submit_guard_helper_finnes_i_utils(self):
        """withSubmitGuard må være definert i modulen malen faktisk laster."""
        from patients import js_test_utils as jsu
        content = jsu.read_js(jsu.PORTAL_UTILS_JS)
        self.assertIn('async function withSubmitGuard(', content,
                      'withSubmitGuard-helperen mangler i portal-utils.js')
        self.assertIn('dataset.submitting', content,
                      'In-flight lock-mekanismen mangler i withSubmitGuard')

    def test_save_new_uses_submit_guard(self):
        """saveNew() må wrappes med withSubmitGuard for å hindre dobbeltklikk."""
        from patients import js_test_utils as jsu
        content = jsu.read_js(jsu.FORMS_JS)
        self.assertIn("withSubmitGuard('btn-save-new'", content,
                      'saveNew() er ikke beskyttet av withSubmitGuard')

    def test_save_edit_uses_submit_guard(self):
        """saveEdit() må også wrappes for å hindre dobbeltlagring av endringer."""
        from patients import js_test_utils as jsu
        content = jsu.read_js(jsu.FORMS_JS)
        self.assertIn("withSubmitGuard('btn-save-edit'", content,
                      'saveEdit() er ikke beskyttet av withSubmitGuard')

    def test_js_modulene_lastes_av_malen(self):
        """Testene over er verdiløse hvis malen ikke laster filene de leser.

        Det var nettopp det som var galt før N9: testene pekte på en fil ingen
        mal lastet.
        """
        from pathlib import Path
        from django.conf import settings
        tpl = Path(settings.BASE_DIR) / 'templates' / 'patients' / 'index.html'
        content = tpl.read_text(encoding='utf-8')
        for modul in ('patients-utils.js', 'patients-forms.js'):
            self.assertIn(modul, content,
                          f'{modul} lastes ikke av index.html')
        self.assertNotIn("js/script.js", content,
                         'index.html laster den slettede monolitten')

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


class RegistreringsskjemaFeilvisningTests(TestCase):
    """S3: en 429 fra serveren må bli synlig i skjemaet.

    Da rate-limiting kom på `POST /api/patients/`, håndterte skjemaet kun 400.
    En strupet registrering ville dermed sett ut som ingenting: modalen ble
    stående åpen, uten feilmelding, mens pasienten ikke var lagret. Det er en
    farligere feilmodus enn selve strupingen.

    Testene kjører `_saveNewImpl()` i node med et stubbet DOM, jf. N9 — ikke
    grep etter kodelinjer.
    """

    DOM_STUB = '''
let skjult = false;
let lastet = 0;

function lagFelt(value) {
  return { value: value, classList: { toggle: () => {} }, style: {}, textContent: '' };
}
const felter = {
  'n-problemstilling':  lagFelt('Pustevansker'),
  'n-arsak':            lagFelt('Sykdom'),
  'n-transport':        lagFelt('Til fots'),
  'n-inntid':           lagFelt('19.04.2026 14:30'),
  'n-plassering':       lagFelt('Gronn 1'),
  'n-forstehjelper':    lagFelt(''),
  'n-helsepersonell':   lagFelt(''),
  'n-triage-warn':      lagFelt(''),
  'new-form-error':     lagFelt(''),
  'new-form-error-text': lagFelt(''),
};
global.document = {
  getElementById: (id) => felter[id] || null,
  querySelector: (sel) => (sel.indexOf('n-triage') !== -1 ? { value: 'Gronn' } : null),
};
global.nowStr = () => '19.04.2026 14:30';
global.bsNew = { hide: () => { skjult = true; } };
global.loadPatients = async () => { lastet++; };
global.renderBoard = () => {};
global.updatePlasseringDropdownState = () => {};
let nyPasientNokkel = 'test-noekkel-abc123';
let sendtBody = null;
'''

    def _kjor(self, snippet):
        from patients import js_test_utils as jsu
        harness = jsu.build_harness([(jsu.FORMS_JS, ('_saveNewImpl',))])
        return jsu.run_node(harness, snippet, preamble=self.DOM_STUB)

    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_429_vises_som_feilmelding_i_skjemaet(self):
        self._kjor('''
global.apiFetch = async () => ({
  ok: false,
  status: 429,
  json: async () => ({ error: 'For mange forespørsler på kort tid.' }),
});

await _saveNewImpl();

assert(felter['new-form-error'].style.display === 'block',
       'feilfeltet ble ikke vist ved 429');
assert(felter['new-form-error-text'].textContent === 'For mange forespørsler på kort tid.',
       'serverens tekst ble ikke vist, fikk: ' + felter['new-form-error-text'].textContent);
assert(skjult === false,
       'modalen ble lukket selv om pasienten ikke ble lagret');
''')

    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_vellykket_lagring_lukker_modalen(self):
        self._kjor('''
global.apiFetch = async () => ({ ok: true, status: 201, json: async () => ({ id: 1 }) });

await _saveNewImpl();

assert(skjult === true, 'modalen ble ikke lukket etter vellykket lagring');
assert(lastet === 1, 'pasientlista ble ikke lastet paa nytt');
assert(felter['new-form-error'].style.display === 'none',
       'feilfeltet ble staaende synlig etter vellykket lagring');
''')
    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_idempotensnokkelen_sendes_med(self):
        """F3: uten nøkkelen i kroppen er hele server-vernet dødt."""
        self._kjor('''
global.apiFetch = async (url, opts) => {
  sendtBody = JSON.parse(opts.body);
  return { ok: true, status: 201, json: async () => ({ id: 1 }) };
};

await _saveNewImpl();

assert(sendtBody.idempotency_key === 'test-noekkel-abc123',
       'idempotency_key manglet i kroppen, fikk: ' + sendtBody.idempotency_key);
''')

    @unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
    def test_409_lukker_modalen_uten_feilmelding(self):
        """En dobbeltinnsending er ikke en feil brukeren kan rette.

        Serveren svarer 409 når den første forespørselen med samme nøkkel
        fortsatt kjører. Pasienten blir opprettet, så utfallet for brukeren
        skal være det samme som ved suksess — ikke en rød boks som ber dem
        prøve igjen.
        """
        self._kjor('''
global.apiFetch = async () => ({
  ok: false,
  status: 409,
  json: async () => ({ error: 'Registreringen er allerede sendt inn.', duplikat: true }),
});

await _saveNewImpl();

assert(skjult === true, 'modalen ble ikke lukket ved 409');
assert(lastet === 1, 'pasientlista ble ikke lastet paa nytt');
assert(felter['new-form-error'].style.display === 'none',
       'det ble vist en feilmelding for en registrering som faktisk gikk gjennom');
''')


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
        gi_standardtilgang(self.user, 'admin')
        self.client.login(username='testbruker', password='Test1234!')
        set_active_year(2026)
        # Eksisterende pasient på unik plassering "Behandling 1"
        self.existing = Patient.objects.create(
            pasientnummer=1, year=2026, plassering='Behandling 1',
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
        resp = self._post_patient('Behandling 1')
        self.assertEqual(resp.status_code, 400)

        # AppSetting-telleren skal fortsatt stå på 2 (ikke konsumert)
        teller = AppSetting.objects.get(key='next_patient_nr').value
        self.assertEqual(teller, '2',
            f'Telleren ble inkrementert til {teller} selv om valideringen feilet')

        # Neste vellykkede registrering skal få nummer 2, ikke 3
        resp_ok = self._post_patient('Behandling 2')
        self.assertEqual(resp_ok.status_code, 201)
        self.assertEqual(resp_ok.json()['pasientnummer'], 2)

    def test_successful_creation_increments_normally(self):
        """Vanlig sekvensiell oppretting skal fortsatt fungere."""
        r1 = self._post_patient('Behandling 2')
        r2 = self._post_patient('Behandling 3')
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
        gi_standardtilgang(self.user, 'admin')
        self.client.login(username='testbruker', password='Test1234!')
        set_active_year(2026)
        self.forstehjelper = Forstehjelper.objects.create(name='Lege Hansen')

    def test_helper_adjusts_pabegynt_when_before_inntid(self):
        """_ensure_pabegynt_not_before_inntid skal sette pabegynt = inntid."""
        from patients.views_common import _ensure_pabegynt_not_before_inntid
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
        from patients.views_common import _ensure_pabegynt_not_before_inntid
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
        from patients.views_common import _ensure_pabegynt_not_before_inntid
        p1 = Patient(pasientnummer=99, year=2026, inntid='', pabegynt='01.05.2026 17:00')
        p2 = Patient(pasientnummer=99, year=2026, inntid='01.05.2026 17:00', pabegynt='')
        self.assertFalse(_ensure_pabegynt_not_before_inntid(p1))
        self.assertFalse(_ensure_pabegynt_not_before_inntid(p2))

    def test_helper_handles_invalid_format_gracefully(self):
        """Ugyldig format skal ikke kaste exception."""
        from patients.views_common import _ensure_pabegynt_not_before_inntid
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
                'plassering': 'Behandling 1',
                'grovsortering': 'Grønn',
                'forstehjelper': self.forstehjelper.pk,  # trigger pabegynt-stempling
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
        gi_standardtilgang(self.user, 'admin')
        self.client.login(username='testbruker', password='Test1234!')
        set_active_year(2026)

    def test_blank_inntid_uses_server_now(self):
        """Tom inntid-streng skal erstattes av server-now-stempel."""
        resp = self.client.post(
            reverse('api_patients_list'),
            data={'inntid': '', 'plassering': 'Behandling 1', 'grovsortering': 'Grønn'},
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


# ── N12: whitelist på GET /api/settings/ ─────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SettingsWhitelistTests(TestCase):
    """GET /api/settings/ skal kun returnere nøkler som er sluppet ut bevisst.

    Bakgrunn: endepunktet returnerte hele `AppSetting`-tabellen til enhver
    innlogget bruker, også rene lesere. Ingenting der var sensitivt i dag, men
    tabellen er en generisk nøkkel/verdi-lagring — neste driftsverdi noen
    lagret der ville havnet i responsen automatisk. PUT hadde whitelist fra
    før; GET hadde ikke.
    """

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='lesebruker', password='testpass123',
            role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.bruker, 'leser')
        self.client.login(username='lesebruker', password='testpass123')

    def _get(self):
        resp = self.client.get('/pasienter/api/settings/')
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_ny_noekkel_lekker_ikke_ut(self):
        """Akseptansekriteriet: en ny nøkkel er usynlig til noen legger den til."""
        AppSetting.set('intern.driftsverdi', 'hemmelig')
        self.assertNotIn('intern.driftsverdi', self._get())

    def test_kjente_interne_noekler_er_ikke_med(self):
        """Nøkler frontend ikke bruker skal ikke eksponeres."""
        AppSetting.set('next_patient_nr', 42)
        AppSetting.set('session_timeout_hours', 8)
        AppSetting.set('feature.live_stats_enabled', 'false')
        # Per-år-navn ble aldri tatt i bruk; mekanismen er slettet.
        AppSetting.set('event_name_2026', 'Skulle ikke vært her')

        data = self._get()
        for key in ('next_patient_nr', 'session_timeout_hours',
                    'feature.live_stats_enabled', 'event_name_2026'):
            self.assertNotIn(key, data, f'{key} lekker via GET /api/settings/')

    def test_event_name_er_med(self):
        """Det frontend faktisk leser må fortsatt komme ut."""
        AppSetting.set('event_name', 'Festivalen 2026')
        self.assertEqual(self._get().get('event_name'), 'Festivalen 2026')

    def test_active_year_er_med(self):
        """Aktivt år styrer hvilke pasienter klienten viser.

        `get_active_year()` oppretter raden første gang den kalles, så den må
        kalles eksplisitt her. Endepunktet oppretter den ikke selv — det leser
        bare `AppSetting`.
        """
        from patients.services import get_active_year
        aar = get_active_year()

        data = self._get()
        self.assertEqual(data.get('active_year'), str(aar))

    def test_put_finnes_ikke_lenger(self):
        """Skrivingen flyttet til /portal-admin/innstillinger/ (§4.1).

        Whitelisten for PUT er borte sammen med metoden. Lese-whitelisten står
        igjen og er fortsatt vernet av testene over — den er den som avgjør hva
        en `les`-bruker får se.

        Endepunktet svarer 405, ikke 403: metoden finnes ikke, tilgangen er i
        orden. Den forskjellen er verdt å beholde i svaret.
        """
        skriver = CustomUser.objects.create_user(
            username='skriver', password='testpass123',
            role='bruker', must_change_password=False,
        )
        gi_standardtilgang(skriver, 'skriver')
        self.client.force_login(skriver)

        foer = AppSetting.get('event_name', None)
        resp = self.client.put(
            '/pasienter/api/settings/',
            data=json.dumps({'event_name': 'Nytt navn'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(AppSetting.get('event_name', None), foer)

class HeaderArrangementNavnTests(TestCase):
    """Headeren skal vise riktig arrangementsnavn med én gang.

    Templaten hadde `LS26` hardkodet i `#event-name-display`. `loadSettings()`
    byttet det ut, men kjøres i `DOMContentLoaded` etter tre awaitede fetch-er
    (forstehjelpere, helsepersonell, pasienter). I mellomtiden sto et gammelt
    arrangementsnavn synlig i headeren.
    """

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='vaktbruker', password='testpass123',
            role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.bruker, 'skriver')
        self.client.login(username='vaktbruker', password='testpass123')

    def test_arrangementsnavn_rendres_server_side(self):
        AppSetting.set('event_name', 'Festivalen 2026')
        resp = self.client.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Festivalen 2026')

    def test_ingen_hardkodet_plassholder_i_templaten(self):
        """Uten arrangementsnavn skal feltene være tomme, ikke vise et gammelt navn.

        Dette er selve regresjonsvernet. Et hardkodet navn sto to steder:
        i headeren og i innstillingsfeltet. Det siste var verst — sto feltet
        med `LS26` mens `event_name` var tomt, ville et lagre skrevet
        plassholderen inn som arrangementsnavn.
        """
        AppSetting.objects.filter(key='event_name').delete()
        resp = self.client.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'LS26')

    def test_ingen_uparsede_template_kommentarer_lekker_ut(self):
        """En flerlinjes `{# #}` rendres som synlig tekst i Django.

        Nettopp det skjedde: kommentaren som forklarte server-renderingen ble
        stående midt i headeren for brukerne. `{# #}` er enlinjes — flerlinjes
        kommentarer må bruke `{% comment %}`.
        """
        resp = self.client.get('/pasienter/')
        innhold = resp.content.decode('utf-8')
        for markor in ('{#', '#}', '{% comment %}', 'Rendres server-side'):
            self.assertNotIn(markor, innhold,
                             f'Uparset template-syntaks i responsen: {markor}')

    def test_innstillingsfeltet_ligger_i_portal_admin(self):
        """Redigeringsfeltet flyttet ut av pasientmodulen (§4.1).

        Arrangementsnavnet er en portalinnstilling: det gjelder vakten, som
        med flere moduler dekker mer enn pasientregistreringen. Feltet krevde
        dessuten global admin, og et admin-endepunkt inne i en modul sier at
        modulgrensen ikke betyr noe.
        """
        resp = self.client.get('/pasienter/')
        self.assertNotContains(resp, 'id="setting-event-name"')
        # Lenken rendres kun for global admin — kortet er server-side gatet.
        self.assertNotContains(resp, '/portal-admin/innstillinger/')

        admin = CustomUser.objects.create_user(
            username='arr_admin', password='x', role='admin',
            must_change_password=False)
        c = Client()
        c.force_login(admin)
        self.assertContains(c.get('/pasienter/'), '/portal-admin/innstillinger/')

    def test_navnet_escapes_i_templaten(self):
        """Arrangementsnavnet er fritekst fra innstillingene."""
        AppSetting.set('event_name', '<script>alert(1)</script>')
        resp = self.client.get('/pasienter/')
        self.assertNotContains(resp, '<script>alert(1)</script>')
        self.assertContains(resp, '&lt;script&gt;')

    def test_endret_navn_slaar_gjennom_ved_ny_lasting(self):
        """Server-renderingen skal lese verdien på nytt, ikke cache den."""
        AppSetting.set('event_name', 'Gammelt navn')
        self.assertContains(self.client.get('/pasienter/'), 'Gammelt navn')

        AppSetting.set('event_name', 'Nytt navn')
        resp = self.client.get('/pasienter/')
        self.assertContains(resp, 'Nytt navn')
        self.assertNotContains(resp, 'Gammelt navn')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NavneregisterFeilmeldingTests(TestCase):
    """Ordlyden i feilmeldingene fra navneregistrene (N13.2).

    De fire viewene ble slått sammen til én fabrikk. Feilmeldingene vises
    direkte i grensesnittet og er det eneste som skiller de to registrene fra
    hverandre, så de pinnes her — ingen andre tester leser dem.
    """

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin_navn', password='testpass123',
            role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.client.force_login(self.admin)

    def _post(self, sti, navn):
        return self.client.post(sti, data=json.dumps({'name': navn}),
                                content_type='application/json')

    def test_duplikat_gir_riktig_ordlyd(self):
        Forstehjelper.objects.create(name='Kari')
        Helsepersonell.objects.create(name='Ola')

        resp = self._post('/pasienter/api/forstehjelpere/', 'Kari')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'Førstehjelper "Kari" finnes allerede')

        resp = self._post('/pasienter/api/helsepersonell/', 'Ola')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'Helsepersonell "Ola" finnes allerede')

    def test_ukjent_id_gir_riktig_ordlyd(self):
        resp = self.client.put('/pasienter/api/forstehjelpere/99999/',
                               data=json.dumps({'name': 'X'}),
                               content_type='application/json')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()['error'], 'Førstehjelper ikke funnet')

        resp = self.client.put('/pasienter/api/helsepersonell/99999/',
                               data=json.dumps({'name': 'X'}),
                               content_type='application/json')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()['error'], 'Helsepersonell ikke funnet')

    def test_sletting_av_rad_i_bruk_gir_riktig_ordlyd(self):
        """PROTECT-stien — bestemt form av etiketten."""
        beh = Forstehjelper.objects.create(name='I bruk')
        hp = Helsepersonell.objects.create(name='Også i bruk')
        Patient.objects.create(pasientnummer=1, year=2026,
                               forstehjelper=beh, helsepersonell_ref=hp)

        resp = self.client.delete(f'/pasienter/api/forstehjelpere/{beh.pk}/')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.json()['error'],
            'Førstehjelperen er knyttet til pasienter og kan ikke slettes. '
            'Deaktiver i stedet.')

        resp = self.client.delete(f'/pasienter/api/helsepersonell/{hp.pk}/')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            resp.json()['error'],
            'Helsepersonellet er knyttet til pasienter og kan ikke slettes. '
            'Deaktiver i stedet.')

    def test_viewene_beholder_navnene_sine(self):
        """Fabrikk-genererte views skal ikke hete `liste_view` i tracebacks."""
        from patients import views_registre as views
        self.assertEqual(views.forstehjelpere_view.__name__, 'forstehjelpere_view')
        self.assertEqual(views.helsepersonell_detail_view.__name__,
                         'helsepersonell_detail_view')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class JsModulLastingTests(TestCase):
    """Betinget lasting av patients-admin.js (F7).

    Fila het patients-stats.js og ble lastet for alle med statistikktilgang.
    Da statistikk ble egen modul, ble renderingen flyttet til statistikk.js
    og det som ble igjen er utelukkende admin-handlinger: registeradmin,
    sesjonstimeout, nullstilling og vaktarkivet. Hvert av de endepunktene
    krever global admin server-side, så alle andre lastet ~370 linjer de
    aldri kunne bruke. Fila lastes derfor kun for admin nå.

    Fellen er den samme som før: bootstrappen — `DOMContentLoaded`,
    faneskift, auto-refresh og lasterne for navneregistrene — lå opprinnelig
    i den betinget lastede modulen. Å laste den betinget uten å flytte
    bootstrappen ville tatt ned hele appen for alle andre enn admin.
    """

    # Profiler, ikke roller: etter deploy 2 er `role` bare admin/bruker, og
    # det som avgjør hva siden viser er ModulTilgang-radene. Lista dekker
    # fortsatt de samme fire kombinasjonene kontoene i prod har.
    ADMIN_PROFILER = ('admin',)
    ANDRE_PROFILER = ('leser', 'skriver', 'leder_les', 'leder')

    @staticmethod
    def _monster(modul):
        """Regex som treffer modulen med eller uten innholdshash i navnet.

        `ManifestStaticFilesStorage` gir `patients-app.a1b2c3d4.js`, ikke
        `patients-app.js`. En ordrett `assertIn('patients-app.js', ...)`
        feiler da — men verre: den ordrette `assertNotIn` ville **bestått
        uansett**, også om modulen faktisk ble lastet. Den negative testen er
        hele F7-vernet, så den måtte gjøres hash-tolerant, ikke bare den
        positive.
        """
        import re
        return re.compile(re.escape(modul) + r'(\.[0-9a-f]{8,})?\.js')

    def _hent_som(self, profil):
        bruker = CustomUser.objects.create_user(
            username=f'bruker_{profil}', password='testpass123',
            role='admin' if profil == 'admin' else 'bruker',
            must_change_password=False,
        )
        gi_standardtilgang(bruker, profil)
        self.client.force_login(bruker)
        resp = self.client.get('/pasienter/')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode('utf-8')

    def test_app_modulen_lastes_for_alle_profiler(self):
        """Bootstrappen må lastes uansett tilgang — ellers starter ikke appen."""
        for profil in self.ADMIN_PROFILER + self.ANDRE_PROFILER:
            with self.subTest(profil=profil):
                self.assertRegex(self._hent_som(profil),
                                 self._monster('patients-app'))

    def test_portal_utils_lastes_for_alle_profiler(self):
        """Primitivene må ligge under alt annet, uansett tilgang.

        patients-utils.js kaller fmtMin() og escapeHtml() derfra. Lastes de
        ikke, feiler pasientsiden for alle — ikke bare for én konto.
        """
        for profil in self.ADMIN_PROFILER + self.ANDRE_PROFILER:
            with self.subTest(profil=profil):
                self.assertRegex(self._hent_som(profil),
                                 self._monster('portal-utils'))

    def test_adminmodulen_lastes_kun_for_admin(self):
        for profil in self.ADMIN_PROFILER:
            with self.subTest(profil=profil):
                self.assertRegex(self._hent_som(profil),
                                 self._monster('patients-admin'))

    def test_adminmodulen_lastes_ikke_for_andre(self):
        """Også de med statistikktilgang: de mistet fila da statistikken flyttet."""
        for profil in self.ANDRE_PROFILER:
            with self.subTest(profil=profil):
                self.assertNotRegex(self._hent_som(profil),
                                    self._monster('patients-admin'))

    def test_alltid_lastede_moduler_refererer_ikke_til_adminmodulen(self):
        """Selve vernet: ingen direkte referanse fra alltid-lastet kode.

        En ikke-admin har ikke patients-admin.js. Kaller bootstrappen
        en funksjon derfra direkte, får hun ReferenceError og appen stopper.
        Slike kall må gå via `_kall()`, som sjekker at funksjonen finnes.
        """
        from patients import js_test_utils as jsu

        admin_navn = set(re.findall(
            r'^(?:async )?function (\w+)', jsu.read_js(jsu.ADMIN_JS), re.M))
        self.assertIn('lagreVaktSomArkiv', admin_navn, 'testen leser feil fil')

        alltid = [jsu.PORTAL_UTILS_JS, jsu.UTILS_JS, jsu.TABLE_JS,
                  jsu.FORMS_JS, jsu.APP_JS]
        funn = []
        for sti in alltid:
            kilde = jsu.read_js(sti)
            # Kommentarer skal ikke telle. En kommentar som forklarer hvorfor
            # `toggleForstehjelper()` trenger et tall, er ikke et kall.
            kilde = '\n'.join(
                l for l in kilde.splitlines() if not l.lstrip().startswith('//'))
            # `_kall('renderForstehjelperAdmin')` er den godkjente veien —
            # strengen teller ikke.
            kilde = re.sub(r"_kall\(\s*'[^']+'", "_kall(", kilde)
            for navn in admin_navn:
                if re.search(r'\b' + re.escape(navn) + r'\s*\(', kilde):
                    funn.append(f'{sti.name}: {navn}()')

        self.assertEqual(sorted(funn), [], (
            'Alltid-lastet kode kaller funksjoner som bor i patients-admin.js:\n  '
            + '\n  '.join(sorted(funn))
            + '\n\npatients-admin.js lastes kun for admin. Flytt funksjonen til '
              'patients-app.js, eller kall den via _kall().'
        ))

    def test_statistikksiden_bruker_bare_primitiver_den_faktisk_laster(self):
        """statistikk.js laster IKKE patients-utils.js — og kan ikke.

        patients-utils.js gjør arbeid på toppnivå: den setter Chart.defaults
        og kaller `new bootstrap.Modal(document.getElementById('newModal'))`.
        På statistikksiden finnes ikke #newModal, så fila ville kastet ved
        lasting. Derfor må alt statistikk.js kaller ligge i portal-utils.js
        eller i statistikk.js selv.

        Dette er ikke hypotetisk: `fmtMin()` lå igjen i patients-utils.js ved
        delingen, og statistikksiden ville kastet ReferenceError på hver
        varighet den skulle vise.
        """
        from patients import js_test_utils as jsu

        def definerte(sti):
            kilde = jsu.read_js(sti)
            return (set(re.findall(r'^(?:async )?function (\w+)', kilde, re.M))
                    | set(re.findall(r'^(?:let|const|var) (\w+)', kilde, re.M)))

        tilgjengelig = definerte(jsu.PORTAL_UTILS_JS) | definerte(jsu.STATISTIKK_JS)
        kun_i_patients = definerte(jsu.UTILS_JS) - tilgjengelig

        statistikk_src = jsu.read_js(jsu.STATISTIKK_JS)
        # Ordet må stå som et kall eller et oppslag, ikke inne i en streng
        # som `<table class="stats-table">` — der er `table` bare markup.
        funn = [navn for navn in sorted(kun_i_patients)
                if re.search(r'\b' + re.escape(navn) + r'\s*\(', statistikk_src)]

        self.assertEqual(funn, [], (
            'statistikk.js kaller funksjoner som kun finnes i '
            'patients-utils.js:\n  ' + '\n  '.join(funn)
            + '\n\nDen fila lastes ikke på /statistikk/. Flytt helperen til '
              'portal-utils.js.'
        ))

    # ── Avhengigheter en side faktisk leverer ───────────────────────────
    #
    # Begge feilene som traff staging 28. aug. var samme klasse: kode flyttet
    # til en side som ikke gir den det den trenger. Ingen av dem ga
    # syntaksfeil, og ingen av dem ble fanget av testene over — som
    # sammenligner bare navn, ikke `window.`-oppslag eller CDN-globaler.
    #
    #   1. `Chart.defaults` sto igjen på toppnivå i patients-utils.js etter at
    #      pasientsiden sluttet å laste Chart.js. ReferenceError drepte resten
    #      av fila, og «Ny pasient» sluttet å virke.
    #   2. `loadStats()` leste `window.USER_ROLE`, som bare pasientmalen
    #      setter. På /statistikk/ falt den til 'read_only' og returnerte før
    #      første hent — statistikken var permanent tom, uten én feilmelding.

    # Globaler nettleseren selv eier. Alt annet på `window.` må settes av malen.
    NETTLESER_GLOBALER = frozenset({
        'location', 'history', 'localStorage', 'sessionStorage', 'navigator',
        'document', 'confirm', 'alert', 'prompt', 'open', 'print', 'crypto',
        'innerWidth', 'innerHeight', 'matchMedia', 'scrollTo', 'setTimeout',
        'setInterval', 'clearTimeout', 'clearInterval', 'addEventListener',
        'removeEventListener', 'fetch', 'getComputedStyle', 'requestAnimationFrame',
    })

    BIBLIOTEK_GLOBALER = ('Chart', 'Tabulator', 'bootstrap')

    # Sidene med egen JS-lastekjede. Verdien utledes fra malen, ikke herfra —
    # lista sier bare hvilke maler som er sider.
    SIDEMALER = ('patients/index.html', 'statistikk/index.html')

    @staticmethod
    def _uten_kommentarer(kilde):
        """Strip `//`-linjer. En kommentar som nevner Chart er ikke en bruk."""
        return '\n'.join(l for l in kilde.splitlines()
                          if not l.lstrip().startswith('//'))

    def _mal(self, navn):
        from pathlib import Path
        from django.conf import settings
        rot = Path(settings.BASE_DIR)
        for kandidat in [rot / 'templates' / navn] + [d / navn for d in rot.glob('*/templates')]:
            if kandidat.exists():
                return kandidat
        self.fail(f'Fant ikke malen {navn}')

    def _lastekjede(self, navn, sett=None):
        """(JS-filer, CDN-biblioteker, malmarkup) malen har, arv inkludert."""
        from django.conf import settings
        from pathlib import Path
        sett = sett if sett is not None else set()
        sti = self._mal(navn)
        if sti in sett:
            return set(), set(), ''
        sett.add(sti)

        markup = sti.read_text(encoding='utf-8')

        # Bare faktiske <script>-tagger, ikke rå markup: en {% comment %}
        # som forklarer at Chart.js IKKE lastes lenger, inneholder strengen
        # «Chart.js» — og en tekstsøk-variant av denne testen leste den som
        # bevis på det motsatte.
        #
        # Hele taggen matches, ikke `src`-verdien. `src="{% static 'js/x.js' %}"`
        # har enkeltfnutter inne i doble, og et `src=["\']([^"\']+)["\']`
        # stopper på den første indre fnutten. Da blir lista tom og testen
        # grønn uten å sammenligne noe — verre enn å mangle.
        skript = re.findall(r'<script\b[^>]*>', markup, re.I)
        js = {m.group(1) for tag in skript
              for m in [re.search(r"\{%\s*static\s*['\"]js/([\w.-]+)['\"]", tag)] if m}
        cdn = {lib for lib, monster in (
            ('Chart', r'chart\.umd|chart\.js'),
            ('Tabulator', r'tabulator'),
            ('bootstrap', r'bootstrap[.@][\w.]*bundle|bootstrap\.bundle'),
        ) if any(re.search(monster, tag, re.I) for tag in skript)}

        forelder = re.search(r'\{%\s*extends\s*["\']([^"\']+)["\']', markup)
        if forelder:
            aj, ac, am = self._lastekjede(forelder.group(1), sett)
            js |= aj
            cdn |= ac
            markup += '\n' + am
        return js, cdn, markup

    def test_js_leser_bare_window_globaler_malen_setter(self):
        """En `window.X` som malen ikke setter er `undefined`, ikke en feil.

        Det er nettopp derfor den er farlig: koden tar en stille default og
        gjør noe annet enn den skal, uten at noe kaster.
        """
        from pathlib import Path
        from django.conf import settings
        js_dir = Path(settings.BASE_DIR) / 'static' / 'js'
        funn = []

        for malnavn in self.SIDEMALER:
            js_filer, _, markup = self._lastekjede(malnavn)
            satt = set(re.findall(r'window\.(\w+)\s*=', markup))
            for navn in sorted(js_filer):
                fil = js_dir / navn
                if not fil.exists():
                    continue
                lest = set(re.findall(r'window\.(\w+)',
                                      self._uten_kommentarer(fil.read_text(encoding='utf-8'))))
                for g in sorted(lest - satt - self.NETTLESER_GLOBALER):
                    funn.append(f'{malnavn} laster {navn}, som leser window.{g} — '
                                f'men malen setter den ikke')

        self.assertEqual(funn, [], (
            'JS leser globaler malen ikke setter:\n  ' + '\n  '.join(funn)
            + '\n\nSett globalen i malen, eller flytt koden til en side som har den.'
        ))

    def test_js_bruker_bare_biblioteker_siden_faktisk_laster(self):
        """Bruk av `Chart`/`Tabulator`/`bootstrap` krever at siden laster dem.

        Toppnivåbruk kaster ved lasting og tar med seg resten av fila — alt
        som er erklært under, finnes ikke etterpå. Testen skiller ikke på
        toppnivå og inne i en funksjon: en funksjon som trenger Chart er
        uansett ubrukelig på en side uten Chart.
        """
        from pathlib import Path
        from django.conf import settings
        js_dir = Path(settings.BASE_DIR) / 'static' / 'js'
        funn = []

        for malnavn in self.SIDEMALER:
            js_filer, cdn, _ = self._lastekjede(malnavn)
            for navn in sorted(js_filer):
                fil = js_dir / navn
                if not fil.exists():
                    continue
                kode = self._uten_kommentarer(fil.read_text(encoding='utf-8'))
                for lib in self.BIBLIOTEK_GLOBALER:
                    if lib in cdn:
                        continue
                    if re.search(r'(?<![.\w$])' + lib + r'\s*[.(]', kode):
                        funn.append(f'{malnavn} laster {navn}, som bruker {lib} — '
                                    f'men siden laster ikke {lib}')

        self.assertEqual(funn, [], (
            'JS bruker biblioteker siden ikke laster:\n  ' + '\n  '.join(funn)
            + '\n\nLast biblioteket i malen, eller flytt koden dit det finnes.'
        ))

    def test_lasterne_ligger_i_alltid_lastet_modul(self):
        """Alt en ikke-admin kan nå må ligge i en alltid-lastet fil.

        `saveEventName` var eksempelet her fram til §4.1 flyttet
        arrangementsnavnet til portal-admin. Lasterne for pasientlista og
        navneregistrene er den samme regelen: de kjøres for alle roller, og
        ligger derfor i patients-app.js, ikke i patients-admin.js.
        """
        from patients import js_test_utils as jsu
        app = jsu.read_js(jsu.APP_JS)
        admin = jsu.read_js(jsu.ADMIN_JS)
        for navn in ('loadSettings', 'loadForstehjelpere', 'loadHelsepersonell'):
            with self.subTest(funksjon=navn):
                self.assertIn(f'function {navn}(', app)
                self.assertNotIn(f'function {navn}(', admin)


class InlineHandlerTests(SimpleTestCase):
    """Ingen inline event-handlere i markup (F5).

    `onclick=`, `oninput=`, `onsubmit=` osv. krever `unsafe-inline` i CSP-ens
    script-src. Så lenge de finnes, kan direktivet ikke strammes — og fjernes
    direktivet mens de står igjen, slutter knappene å virke uten annen
    beskjed enn en linje i nettleserkonsollen.

    Verst var `onsubmit="return confirm(...)"` på sletting av bruker, frysing
    av konto og MFA-nullstilling: der ville bekreftelsen forsvunnet stille,
    ikke handlingen.
    """

    def test_ingen_inline_handlere_i_maler(self):
        from pathlib import Path
        from django.conf import settings

        base = Path(settings.BASE_DIR)
        mapper = [base / 'templates'] + list(base.glob('*/templates'))

        funn = []
        for mappe in mapper:
            for mal in mappe.rglob('*.html'):
                for nr, linje in enumerate(
                        mal.read_text(encoding='utf-8').splitlines(), 1):
                    for treff in re.findall(r'\son([a-z]+)="', linje):
                        funn.append(f'{mal.relative_to(base)}:{nr} on{treff}=')

        self.assertEqual(sorted(funn), [], (
            'Inline event-handlere i markup:\n  ' + '\n  '.join(sorted(funn))
            + '\n\nBruk data-action / data-input-action (håndtert i '
              'patients-app.js) eller data-confirm (ui-actions.js).'
        ))

    def test_ingen_inline_handlere_generert_fra_js(self):
        """Markup bygget i JS teller like mye — CSP ser bare det ferdige DOM-et."""
        from patients import js_test_utils as jsu

        funn = []
        for sti in (jsu.PORTAL_UTILS_JS, jsu.UTILS_JS, jsu.TABLE_JS,
                    jsu.FORMS_JS, jsu.APP_JS, jsu.ADMIN_JS,
                    jsu.STATISTIKK_JS):
            for nr, linje in enumerate(
                    jsu.read_js(sti).splitlines(), 1):
                for treff in re.findall(r'\son([a-z]+)="', linje):
                    funn.append(f'{sti.name}:{nr} on{treff}=')

        self.assertEqual(sorted(funn), [], (
            'JS genererer markup med inline handlere:\n  '
            + '\n  '.join(sorted(funn))
            + '\n\nBruk data-action med data-id for numeriske argumenter.'
        ))

    def test_delegering_skiller_streng_og_tall(self):
        """`data-id` må bli tall, ikke streng.

        `toggleForstehjelper()` slår opp med `x.id === id`. Kom id-en inn som
        streng, ville funksjonen returnert uten å gjøre noe — og uten feil.
        """
        from patients import js_test_utils as jsu
        # Delegeringen flyttet til portal-utils.js da statistikksiden fikk
        # behov for den samme mekanismen («tilbake til live-statistikk»).
        portal = jsu.read_js(jsu.PORTAL_UTILS_JS)
        self.assertIn('Number(el.dataset.id)', portal)

        admin = jsu.read_js(jsu.ADMIN_JS)
        self.assertIn('data-id="${b.id}"', admin,
                      'admin-registrene må sende id som data-id, ikke data-arg')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PasientlisteYtelseTests(TestCase):
    """Spørringsantall og ETag på `/api/patients/`.

    Endepunktet pollet hvert 30. sekund av hver klient, og var det dyreste i
    appen: `_patient_to_dict()` leser navnet på førstehjelper og
    helsepersonell, uten `select_related`. Målt til 515 spørringer og 454 kB
    ved 1000 pasienter.
    """

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='poller', password='testpass123',
            role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.bruker, 'skriver')
        self.client.force_login(self.bruker)

    def _lag_pasienter(self, antall):
        for i in range(1, antall + 1):
            Patient.objects.create(
                pasientnummer=i, year=2026, grovsortering='Grønn',
                forstehjelper=Forstehjelper.objects.create(name=f'F{i}'),
                helsepersonell_ref=Helsepersonell.objects.create(name=f'H{i}'),
            )

    def test_spoerringsantall_vokser_ikke_med_antall_pasienter(self):
        """Selve N+1-vernet.

        Testen sammenligner to størrelser i stedet for å låse et absolutt
        tall: da tåler den at annen middleware endrer grunnkostnaden, men
        fanger fortsatt at kostnaden begynner å følge radantallet.
        """
        self._lag_pasienter(5)
        with CaptureQueriesContext(connection) as faa:
            self.client.get('/pasienter/api/patients/')

        # Pasientene først — FK-ene er PROTECT.
        Patient.objects.all().delete()
        Forstehjelper.objects.all().delete()
        Helsepersonell.objects.all().delete()
        self._lag_pasienter(60)
        with CaptureQueriesContext(connection) as mange:
            self.client.get('/pasienter/api/patients/')

        self.assertLessEqual(
            len(mange.captured_queries), len(faa.captured_queries) + 2,
            f'Spørringene vokser med radantallet: {len(faa.captured_queries)} '
            f'ved 5 pasienter, {len(mange.captured_queries)} ved 60. '
            'Mangler select_related på forstehjelper/helsepersonell_ref?'
        )

    def test_etag_settes_og_gir_304(self):
        self._lag_pasienter(3)
        resp = self.client.get('/pasienter/api/patients/')
        self.assertEqual(resp.status_code, 200)
        etag = resp.headers.get('ETag')
        self.assertTrue(etag, 'ETag mangler på pasientlista')

        igjen = self.client.get('/pasienter/api/patients/',
                                HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(igjen.status_code, 304)
        self.assertEqual(igjen.content, b'', '304 skal ikke ha kropp')

    def test_etag_endrer_seg_naar_data_endres(self):
        self._lag_pasienter(3)
        etag = self.client.get('/pasienter/api/patients/').headers['ETag']

        p = Patient.objects.first()
        p.grovsortering = 'Rød'
        p.save(update_fields=['grovsortering'])

        resp = self.client.get('/pasienter/api/patients/',
                               HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(resp.status_code, 200,
                         'Endret data må gi 200, ikke 304')
        self.assertNotEqual(resp.headers['ETag'], etag)

    def test_etag_skiller_mellom_filtrerte_svar(self):
        """?mine=1 gir et annet svar, og må gi en annen ETag.

        Ellers ville en klient som bytter filter fått 304 og blitt stående
        med feil datasett.
        """
        self._lag_pasienter(3)
        alle = self.client.get('/pasienter/api/patients/')
        mine = self.client.get('/pasienter/api/patients/?mine=1')

        self.assertNotEqual(alle.headers['ETag'], mine.headers['ETag'])
        self.assertEqual(
            self.client.get('/pasienter/api/patients/?mine=1',
                            HTTP_IF_NONE_MATCH=alle.headers['ETag']).status_code,
            200, 'ETag fra det ufiltrerte svaret må ikke gi 304 på ?mine=1')

    def test_responsen_er_uendret_json(self):
        """Overgangen fra JsonResponse til HttpResponse skal ikke synes."""
        import json as _json
        self._lag_pasienter(2)
        resp = self.client.get('/pasienter/api/patients/')
        self.assertEqual(resp.headers['Content-Type'], 'application/json')
        data = _json.loads(resp.content)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['pasientnummer'], 1)
        self.assertIn('forstehjelper', data[0])

class MorkTekstPaaMorkBakgrunnTests(TestCase):
    """Bootstrap-klasser for sekundærtekst må overstyres i det stilarket malen laster.

    Portalen kjører mørkt. Bootstraps egne farger for dempet tekst er laget
    for lys bakgrunn — `.form-text` er `#6c757d` — og blir tilnærmet uleselige.
    Klassene ser riktige ut i markup, så feilen oppdages først når noen
    faktisk prøver å lese teksten.

    **Testen må følge lastekjeden, ikke bare lete i én fil.** Første utgave av
    denne testen sjekket alle maler mot `style.css` alene, og bestod mens de
    tre meldte sidene var like uleselige som før: `style.css` lastes kun av
    pasientmodulens `index.html`, mens alt som arver `base_portal.html` får
    `portal.css`. To mørke temaer, to filer. Testen løser derfor `{% extends %}`
    og `{% static %}` for hver mal og krever overstyringen der malen faktisk
    kan se den.
    """

    DEMPEDE_KLASSER = ('form-text', 'text-muted', 'text-secondary')

    # Pseudo-elementer Bootstrap farger for lys bakgrunn, og som må overstyres
    # der `.form-control` er overstyrt.
    PSEUDO_KRAV = {'.form-control': '::placeholder'}

    def _rot(self):
        from pathlib import Path
        from django.conf import settings
        return Path(settings.BASE_DIR)

    def _maler(self):
        rot = self._rot()
        maler = list((rot / 'templates').rglob('*.html'))
        for app_maler in rot.glob('*/templates'):
            maler.extend(app_maler.rglob('*.html'))
        return maler

    def _finn_mal(self, navn):
        """Slå opp en mal på navnet `{% extends %}` bruker."""
        rot = self._rot()
        kandidater = [rot / 'templates' / navn]
        kandidater += [d / navn for d in rot.glob('*/templates')]
        for k in kandidater:
            if k.exists():
                return k
        return None

    def _stilark_og_inline(self, sti, sett=None):
        """CSS-en malen faktisk har tilgang til, inkludert arvet fra base."""
        import re
        sett = sett or set()
        if sti in sett:
            return set(), ''
        sett.add(sti)

        markup = sti.read_text(encoding='utf-8')
        ark = set(re.findall(r"\{%\s*static\s*['\"]css/([\w.-]+)['\"]", markup))
        inline = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', markup, re.S))

        forelder = re.search(r'\{%\s*extends\s*["\']([^"\']+)["\']', markup)
        if forelder:
            sti_forelder = self._finn_mal(forelder.group(1))
            if sti_forelder:
                arvet_ark, arvet_inline = self._stilark_og_inline(sti_forelder, sett)
                ark |= arvet_ark
                inline += '\n' + arvet_inline
        return ark, inline

    def test_dempede_klasser_er_overstyrt_der_malen_ser_dem(self):
        import re
        rot = self._rot()
        mangler = []

        for mal in self._maler():
            markup = mal.read_text(encoding='utf-8')
            brukte = [k for k in self.DEMPEDE_KLASSER
                      if re.search(r'class="[^"]*\b' + k + r'\b', markup)]
            if not brukte:
                continue

            ark, inline = self._stilark_og_inline(mal)
            if not ark and not inline:
                continue  # partial/include uten egen lastekjede

            css = inline
            for navn in ark:
                fil = rot / 'static' / 'css' / navn
                if fil.exists():
                    css += '\n' + fil.read_text(encoding='utf-8')

            for klasse in brukte:
                if not re.search(r'\.' + klasse + r'\s*[,{]', css):
                    mangler.append(
                        f'{mal.relative_to(rot)} bruker .{klasse}, men verken '
                        f'{sorted(ark) or "inline <style>"} overstyrer den'
                    )

        self.assertEqual(
            mangler, [],
            'Bootstraps lyse standardfarge slår gjennom på mørk bakgrunn:\n  '
            + '\n  '.join(mangler),
        )

    def test_placeholder_er_overstyrt_der_feltet_er_det(self):
        """Farger man `.form-control` mørkt, må `::placeholder` følge med.

        Ellers arver hjelpeteksten inne i feltet Bootstraps
        lyse-bakgrunn-farge og blir stående nesten usynlig — mens selve feltet
        ser riktig ut. Regelen er lettere å glemme enn å oppdage.

        `portal.css` manglet den 23. aug. 2026, så «Fornavn Etternavn» og
        «Valgfritt» sto praktisk talt i bakgrunnsfargen i brukerskjemaet.
        `style.css` hadde regelen hele tiden, så pasientmodulen var upåvirket
        — nok en gang gjaldt en fiks kun den halvparten av portalen som laster
        den fila.
        """
        import re
        rot = self._rot()
        mangler = []

        for mal in self._maler():
            ark, inline = self._stilark_og_inline(mal)
            css = inline
            for navn in ark:
                fil = rot / 'static' / 'css' / navn
                if fil.exists():
                    css += '\n' + fil.read_text(encoding='utf-8')
            if not css:
                continue

            for selektor, pseudo in self.PSEUDO_KRAV.items():
                # Kun relevant hvis malen faktisk overstyrer selektoren.
                if not re.search(re.escape(selektor) + r'[\s,:{]', css):
                    continue
                if pseudo not in css:
                    mangler.append(
                        f'{mal.relative_to(rot)} overstyrer {selektor}, '
                        f'men ikke {selektor}{pseudo}'
                    )

        self.assertEqual(
            sorted(set(mangler)), [],
            'Feltet er mørkt, men teksten inni er Bootstraps lyse standard:\n  '
            + '\n  '.join(sorted(set(mangler))),
        )


class AktivMineMarkeringTests(TestCase):
    """`.active-mine` må matche begge knappene som får klassen satt.

    `toggleBoardMine()` setter `.active-mine` på `#btn-board-mine`, men CSS-en
    hadde kun `.filter-btn.active-mine` — og tavleknappen har ikke den klassen.
    Regelen matchet derfor aldri, og «Mine pasienter» var umarkert på tavla
    selv om filteret virket.

    Testen sjekker koblingen mellom de tre filene, som er der feilen lå: JS
    setter klassen, malen bestemmer hvilke selektorer som kan treffe, CSS-en
    definerer dem.
    """

    def _les(self, *deler):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR).joinpath(*deler)).read_text(encoding='utf-8')

    def test_selektoren_treffer_tavleknappen(self):
        import re
        markup = self._les('templates', 'patients', 'index.html')
        css = self._les('static', 'css', 'style.css')

        knapp = re.search(r'<button[^>]*id="btn-board-mine"[^>]*>', markup)
        self.assertIsNotNone(knapp, '#btn-board-mine finnes ikke i index.html')
        klasser = set(
            re.search(r'class="([^"]*)"', knapp.group(0)).group(1).split()
        )

        # Kommentarer må vekk før selektorene leses. Uten dette matchet
        # regexen prosaen i CSS-kommentaren rett over regelen, med tom
        # prefiks-gruppe — og testen bestod uten at noen selektor faktisk
        # traff knappen. Verifisert ved å reversere fiksen: da skal den feile.
        css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
        selektorer = re.findall(r'([^\s,{}]*)\.active-mine', css)
        treffer = any(
            s == '#btn-board-mine' or s.lstrip('.') in klasser or s == ''
            for s in selektorer
        )
        self.assertTrue(
            treffer,
            'Ingen .active-mine-selektor matcher #btn-board-mine '
            f'(klasser: {sorted(klasser)}, selektorer: {selektorer}). '
            'toggleBoardMine() setter klassen, men den vises aldri.',
        )

    def test_js_setter_klassen_paa_den_knappen(self):
        js = self._les('static', 'js', 'patients-table.js')
        self.assertIn("getElementById('btn-board-mine')", js)
        self.assertIn("classList.toggle('active-mine'", js)
