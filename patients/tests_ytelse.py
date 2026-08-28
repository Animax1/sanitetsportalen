"""Tester for ytelsespuljen: N7 (delt Redis-klient), N8 (bulk audit), N10 (sesjoner).

Disse tester ikke hastighet i sekunder — de tester de strukturelle egenskapene
som gjør stien billig: at klienten gjenbrukes, at antall spørringer er konstant,
og at innlogging ikke skalerer med antall sesjoner i systemet.

Kjør med: python manage.py test patients.tests_ytelse
"""
from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from audit.models import AuditLog
from patients.models import Patient, Forstehjelper
from accounts.test_helpers import gi_standardtilgang


class DeltRedisKlientTests(TestCase):
    """N7: klienten skal bygges én gang per prosess, ikke per kall.

    `redis.Redis.from_url()` lager en ny ConnectionPool hver gang, så den gamle
    varianten betalte en TCP-handshake per request for å skrive én metrikk-linje.
    """

    def setUp(self):
        from patients.middleware import _reset_shared_redis_client
        _reset_shared_redis_client()

    def tearDown(self):
        from patients.middleware import _reset_shared_redis_client
        _reset_shared_redis_client()

    @override_settings(REDIS_URL='redis://localhost:6379/0')
    def test_klienten_bygges_kun_en_gang(self):
        from patients.middleware import _get_shared_redis_client

        with patch('redis.Redis.from_url') as fake_from_url:
            fake_from_url.return_value = object()

            forste = _get_shared_redis_client()
            for _ in range(50):
                _get_shared_redis_client()

            self.assertEqual(
                fake_from_url.call_count, 1,
                'from_url skal kalles én gang, ikke per oppslag',
            )
            self.assertIs(_get_shared_redis_client(), forste)

    @override_settings(REDIS_URL='')
    def test_uten_redis_url_gir_none(self):
        from patients.middleware import _get_shared_redis_client
        self.assertIsNone(_get_shared_redis_client())

    @override_settings(REDIS_URL='redis://localhost:6379/0')
    def test_feil_ved_oppkobling_gir_none_og_kaster_ikke(self):
        """Død Redis skal degradere til lokal deque, ikke velte requesten."""
        from patients.middleware import _get_shared_redis_client

        with patch('redis.Redis.from_url', side_effect=OSError('nede')):
            self.assertIsNone(_get_shared_redis_client())

    @override_settings(REDIS_URL='redis://localhost:6379/0')
    def test_metrics_store_bruker_den_delte_klienten(self):
        from patients.middleware import _MetricsStore, _get_shared_redis_client

        with patch('redis.Redis.from_url') as fake_from_url:
            fake_from_url.return_value = object()
            store = _MetricsStore()
            self.assertIs(store._get_redis_client(), _get_shared_redis_client())
            self.assertEqual(fake_from_url.call_count, 1)


class AuditBulkCreateTests(TestCase):
    """N8: antall spørringer per lagring skal ikke vokse med antall felt."""

    def setUp(self):
        self.pasient = Patient.objects.create(pasientnummer=801, year=2026)
        AuditLog.objects.all().delete()

    def _tell_insert_spørringer(self, endre):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            endre()
        return [
            q for q in ctx.captured_queries
            if 'audit_auditlog' in q['sql'].lower() and 'insert' in q['sql'].lower()
        ]

    def test_ett_felt_gir_en_insert(self):
        def endre():
            self.pasient.problemstilling = 'A'
            self.pasient.save()

        self.assertEqual(len(self._tell_insert_spørringer(endre)), 1)

    def test_tre_felt_gir_ogsaa_en_insert(self):
        """Kjernen i N8: konstant antall spørringer uansett antall endringer."""
        def endre():
            self.pasient.problemstilling = 'B'
            self.pasient.transport = 'Baare'
            self.pasient.plassering = 'Gronn 3'
            self.pasient.save()

        self.assertEqual(len(self._tell_insert_spørringer(endre)), 1)

    def test_alle_radene_blir_faktisk_skrevet(self):
        self.pasient.problemstilling = 'C'
        self.pasient.transport = 'Rullestol'
        self.pasient.plassering = 'Gul 1'
        self.pasient.save()

        self.assertEqual(AuditLog.objects.count(), 3)
        felt = set(AuditLog.objects.values_list('field_name', flat=True))
        self.assertEqual(felt, {'problemstilling', 'transport', 'plassering'})

    def test_app_label_settes_selv_om_bulk_create_hopper_over_pre_save(self):
        """bulk_create kjører ikke pre_save-signalet som ellers fyller feltet.

        Uten eksplisitt app_label ville radene vist seg som «Ukjent» i
        modulfilteret i revisjonsloggen.
        """
        self.pasient.problemstilling = 'D'
        self.pasient.save()

        for rad in AuditLog.objects.all():
            self.assertEqual(rad.app_label, 'patients')

    def test_ingen_endring_gir_ingen_spørring(self):
        def endre():
            self.pasient.save()

        self.assertEqual(len(self._tell_insert_spørringer(endre)), 0)

    def test_fk_endring_logges_med_id(self):
        fh = Forstehjelper.objects.create(name='Hjelper N8')

        self.pasient.forstehjelper = fh
        self.pasient.save()

        rad = AuditLog.objects.get(field_name='forstehjelper_id')
        self.assertEqual(rad.new_value, str(fh.pk))
        self.assertEqual(rad.app_label, 'patients')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SesjonsinvalideringTests(TestCase):
    """N10: innlogging skal ikke skalere med antall sesjoner i systemet."""

    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='sesjonsbruker', password='TestPassord123!',
            role='read_write', must_change_password=False,
        )
        gi_standardtilgang(self.user)

    def _logg_inn(self, client=None):
        c = client or Client()
        c.post(reverse('accounts:login'), {
            'username': 'sesjonsbruker', 'password': 'TestPassord123!',
        })
        return c

    def _lag_fremmede_sesjoner(self, antall):
        """Sesjoner for andre brukere — støy som den gamle koden dekodet."""
        for i in range(antall):
            annen = CustomUser.objects.create_user(
                username=f'annen{i}', password='x', must_change_password=False,
            )
            gi_standardtilgang(annen)
            store = SessionStore()
            store['_auth_user_id'] = str(annen.pk)
            store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
            store.save()

    def test_en_sesjon_per_bruker_bevares(self):
        """Policyen skal være uendret — dette er ikke en oppførselsendring."""
        klient1 = self._logg_inn()
        nokkel1 = klient1.session.session_key

        klient2 = self._logg_inn()
        nokkel2 = klient2.session.session_key

        self.assertNotEqual(nokkel1, nokkel2)
        self.assertFalse(Session.objects.filter(session_key=nokkel1).exists())
        self.assertTrue(Session.objects.filter(session_key=nokkel2).exists())

    def test_uregistrert_sesjon_ryddes_ved_innlogging(self):
        """Regresjon fra produksjon 13. aug. 2026.

        En sesjon som fantes før `current_session_key` ble innført, er ikke
        registrert på brukeren. Tom nøkkel betyr ikke «ingen sesjoner» — den
        betyr at vi ikke vet. Uten fallback til full gjennomgang forble brukeren
        innlogget på begge enheter.
        """
        # Etterlikn en sesjon fra før feltet fantes: den finnes i tabellen,
        # men er ikke registrert på brukeren.
        store = SessionStore()
        store['_auth_user_id'] = str(self.user.pk)
        store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        store['_auth_user_hash'] = self.user.get_session_auth_hash()
        store.save()
        gammel = store.session_key

        self.user.current_session_key = None
        self.user.save(update_fields=['current_session_key'])

        self._logg_inn()

        self.assertFalse(
            Session.objects.filter(session_key=gammel).exists(),
            'Uregistrert sesjon overlevde innlogging på ny enhet',
        )

    def test_fallback_gaar_ikke_ut_over_andre_brukere(self):
        self._lag_fremmede_sesjoner(3)
        self.user.current_session_key = None
        self.user.save(update_fields=['current_session_key'])
        antall_for = Session.objects.count()

        self._logg_inn()

        self.assertEqual(Session.objects.count(), antall_for + 1)

    def test_sesjonsnokkelen_lagres_paa_brukeren(self):
        klient = self._logg_inn()
        self.user.refresh_from_db()
        self.assertEqual(self.user.current_session_key, klient.session.session_key)

    def test_andre_brukeres_sesjoner_roeres_ikke(self):
        self._lag_fremmede_sesjoner(5)
        antall_for = Session.objects.count()

        self._logg_inn()

        self.assertEqual(Session.objects.count(), antall_for + 1)

    def test_innlogging_gjor_konstant_antall_sporringer(self):
        """Kjernen i N10: kostnaden skal ikke vokse med sesjonstabellen.

        Den gamle koden itererte alle ikke-utløpte sesjoner og kalte
        get_decoded() på hver — signaturverifisering og JSON-parsing per rad —
        ved hver eneste innlogging.
        """
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        self._logg_inn()  # etabler en forrige sesjon å rydde bort

        with CaptureQueriesContext(connection) as faa:
            self._logg_inn()
        antall_med_faa = len(faa.captured_queries)

        self._lag_fremmede_sesjoner(30)

        with CaptureQueriesContext(connection) as mange:
            self._logg_inn()
        antall_med_mange = len(mange.captured_queries)

        self.assertEqual(
            antall_med_faa, antall_med_mange,
            'Antall spørringer ved innlogging varierer med antall sesjoner',
        )

    def test_passordbytte_gjor_fortsatt_grundig_opprydding(self):
        """Sikkerhetsstien skal beholde den fullstendige gjennomgangen."""
        klient = self._logg_inn()

        # En uregistrert sesjon for samme bruker — slik en sesjon fra før
        # current_session_key ble innført ville sett ut.
        store = SessionStore()
        store['_auth_user_id'] = str(self.user.pk)
        store['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        store['_auth_user_hash'] = self.user.get_session_auth_hash()
        store.save()
        foreldreloes = store.session_key

        klient.post(reverse('accounts:change_password'), {
            'old_password': 'TestPassord123!',
            'new_password1': 'HeltNyttPassord456!',
            'new_password2': 'HeltNyttPassord456!',
        })

        self.assertFalse(
            Session.objects.filter(session_key=foreldreloes).exists(),
            'Passordbytte skal fjerne også sesjoner som ikke var registrert',
        )
