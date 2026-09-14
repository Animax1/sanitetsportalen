"""Tester for admin server-status dashbord."""
import time

from django.test import TestCase, Client, override_settings
from django.urls import reverse

from accounts.models import CustomUser

from .middleware import metrics_store, _MetricsStore
from accounts.test_helpers import gi_standardtilgang


class MetricsStoreTests(TestCase):
    """Unit-tester for ringbuffer-logikken."""

    def setUp(self):
        self.store = _MetricsStore()

    def test_tom_snapshot(self):
        snap = self.store.snapshot(window_seconds=60)
        self.assertEqual(snap['count'], 0)
        self.assertEqual(snap['rps'], 0.0)
        self.assertEqual(snap['avg_ms'], 0.0)
        self.assertEqual(snap['errors_5xx'], 0)

    def test_record_og_snapshot(self):
        for ms in [10, 20, 30, 40, 50]:
            self.store.record('/pasienter/api/test/', 'GET', 200, ms)

        snap = self.store.snapshot(window_seconds=60)
        self.assertEqual(snap['count'], 5)
        self.assertEqual(snap['avg_ms'], 30.0)
        self.assertEqual(snap['p50_ms'], 30.0)
        self.assertEqual(snap['max_ms'], 50.0)

    def test_percentiler(self):
        # 100 samples, duration = 1..100
        for i in range(1, 101):
            self.store.record('/pasienter/api/test/', 'GET', 200, float(i))
        snap = self.store.snapshot(window_seconds=60)
        self.assertEqual(snap['count'], 100)
        # P50 ligger rundt 50, P95 rundt 95
        self.assertAlmostEqual(snap['p50_ms'], 50.5, delta=1.0)
        self.assertAlmostEqual(snap['p95_ms'], 95.0, delta=1.0)

    def test_feil_telles(self):
        self.store.record('/pasienter/api/x/', 'GET', 200, 10)
        self.store.record('/pasienter/api/y/', 'GET', 404, 20)
        self.store.record('/pasienter/api/z/', 'POST', 500, 30)
        self.store.record('/pasienter/api/w/', 'GET', 503, 40)

        snap = self.store.snapshot(window_seconds=60)
        self.assertEqual(snap['errors_4xx'], 1)
        self.assertEqual(snap['errors_5xx'], 2)

    def test_ringbuffer_avkortes(self):
        from .middleware import MAX_SAMPLES
        # Fyll til over maks
        for i in range(MAX_SAMPLES + 100):
            self.store.record('/pasienter/api/x/', 'GET', 200, float(i))

        snap = self.store.snapshot(window_seconds=60)
        self.assertEqual(snap['sample_size'], MAX_SAMPLES)

    def test_vindu_filtrerer_gamle_samples(self):
        # Manipuler en gammel timestamp direkte
        self.store.record('/pasienter/api/x/', 'GET', 200, 10)
        with self.store._lock:
            self.store._samples[0]['ts'] = time.time() - 3600  # 1 time gammel
        self.store.record('/pasienter/api/y/', 'GET', 200, 20)

        snap = self.store.snapshot(window_seconds=60)
        self.assertEqual(snap['count'], 1)  # kun den nye

    def test_snapshot_har_source_felt(self):
        # Tom snapshot skal også ha source-felt
        snap = self.store.snapshot(window_seconds=60)
        self.assertIn('source', snap)
        # Default i tester (LocMem): forventer 'local'
        self.assertEqual(snap['source'], 'local')

    def test_snapshot_har_unique_workers_naar_data(self):
        self.store.record('/x/', 'GET', 200, 10)
        snap = self.store.snapshot(window_seconds=60)
        # Når det er data skal unique_workers være med
        self.assertIn('unique_workers', snap)


class MetricsRedisAggregeringTests(TestCase):
    """Tester for FORBEDRINGER #15: Redis-aggregert metrikker.

    Vi mocker django-redis-klienten slik at testen kan kjøre uten faktisk
    Redis-server. Verifiserer at både skrive- og lese-stien går via Redis
    når CACHE_BACKEND_NAME == 'redis', og at vi faller gracefully tilbake
    til lokal deque ved feil.
    """

    def setUp(self):
        self.store = _MetricsStore()

    def test_redis_ikke_tilgjengelig_default(self):
        """I testmiljø skal _redis_is_available() returnere False (LocMem)."""
        from .middleware import _redis_is_available
        # Standard testsettings bruker LocMem, ikke Redis
        self.assertFalse(_redis_is_available())

    @override_settings(CACHE_BACKEND_NAME='redis')
    def test_redis_flag_aktiverer_aggregering(self):
        from .middleware import _redis_is_available
        self.assertTrue(_redis_is_available())

    def test_record_til_redis_feiler_stille(self):
        """Hvis Redis-skriving feiler skal lokal deque fortsatt få sample."""
        # _redis_is_available() er False i default test → record skriver kun
        # til lokal deque uansett. Bekrefter at ingen exception lekker.
        try:
            self.store.record('/x/', 'GET', 200, 12.0)
        except Exception as exc:
            self.fail(f'record() skal aldri reise: {exc}')
        self.assertEqual(len(self.store._samples), 1)

    @override_settings(CACHE_BACKEND_NAME='redis', REDIS_URL='redis://fake:6379/0')
    def test_record_redis_unntak_bryter_ikke(self):
        """Hvis Redis-klienten feiler, skal lokal deque fortsatt få sin
        sample og ingen feil skal forplante seg.
        """
        # Med CACHE_BACKEND_NAME='redis' og REDIS_URL satt, men uten faktisk
        # Redis-server, vil _record_to_redis() forsøke å koble til og feile.
        # Dette skal håndteres internt uten å lekke exception.
        try:
            self.store.record('/y/', 'GET', 200, 15.0)
        except Exception as exc:
            self.fail(f'record() lekket exception: {exc}')
        self.assertEqual(len(self.store._samples), 1)

    @override_settings(CACHE_BACKEND_NAME='redis', REDIS_URL='redis://fake:6379/0')
    def test_snapshot_aggregerer_fra_redis_naar_tilgjengelig(self):
        """Mock redis-klient slik at vi kan verifisere at snapshot()
        leser fra Redis, ikke fra lokal deque, når Redis er på.
        """
        from unittest.mock import patch, MagicMock
        import json as _json

        # Bygg fake samples som om de kom fra to ulike workere (pid)
        now = time.time()
        fake_payloads = [
            _json.dumps({'ts': now - 5, 'path': '/a/', 'method': 'GET',
                         'status': 200, 'duration_ms': 20.0, 'pid': 111}),
            _json.dumps({'ts': now - 4, 'path': '/b/', 'method': 'GET',
                         'status': 200, 'duration_ms': 40.0, 'pid': 222}),
            _json.dumps({'ts': now - 3, 'path': '/c/', 'method': 'POST',
                         'status': 500, 'duration_ms': 60.0, 'pid': 111}),
        ]
        fake_client = MagicMock()
        fake_client.lrange.return_value = fake_payloads

        with patch.object(self.store, '_get_redis_client', return_value=fake_client):
            snap = self.store.snapshot(window_seconds=60)

        self.assertEqual(snap['source'], 'redis')
        self.assertEqual(snap['count'], 3)
        self.assertEqual(snap['unique_workers'], 2)  # pid 111 + 222
        self.assertEqual(snap['errors_5xx'], 1)
        # Avg av 20, 40, 60 = 40.0
        self.assertEqual(snap['avg_ms'], 40.0)

    @override_settings(CACHE_BACKEND_NAME='redis', REDIS_URL='redis://fake:6379/0')
    def test_snapshot_faller_tilbake_til_local_om_redis_tom(self):
        """Hvis Redis-listen er tom, skal vi falle tilbake til lokal deque."""
        from unittest.mock import patch, MagicMock

        fake_client = MagicMock()
        fake_client.lrange.return_value = []  # tom liste i Redis

        # Putt noe i lokal deque
        self.store.record('/local/', 'GET', 200, 25.0)

        with patch.object(self.store, '_get_redis_client', return_value=fake_client):
            snap = self.store.snapshot(window_seconds=60)

        self.assertEqual(snap['source'], 'local')
        self.assertEqual(snap['count'], 1)
        self.assertEqual(snap['avg_ms'], 25.0)

    @override_settings(CACHE_BACKEND_NAME='redis', REDIS_URL='redis://fake:6379/0')
    def test_snapshot_faller_tilbake_om_redis_lrange_kaster(self):
        """Hvis Redis-klienten kaster ved lesing skal vi bruke lokal deque."""
        from unittest.mock import patch, MagicMock

        fake_client = MagicMock()
        fake_client.lrange.side_effect = RuntimeError('Redis nede')

        self.store.record('/local/', 'GET', 200, 99.0)

        with patch.object(self.store, '_get_redis_client', return_value=fake_client):
            snap = self.store.snapshot(window_seconds=60)

        self.assertEqual(snap['source'], 'local')
        self.assertEqual(snap['count'], 1)
        self.assertEqual(snap['avg_ms'], 99.0)

    def test_redis_filtrerer_gamle_samples_etter_vindu(self):
        """Samples eldre enn window_seconds skal filtreres bort."""
        from unittest.mock import patch, MagicMock
        import json as _json

        now = time.time()
        fake_payloads = [
            _json.dumps({'ts': now - 5, 'path': '/ny/', 'method': 'GET',
                         'status': 200, 'duration_ms': 10.0, 'pid': 1}),
            _json.dumps({'ts': now - 9999, 'path': '/gammel/', 'method': 'GET',
                         'status': 200, 'duration_ms': 999.0, 'pid': 1}),
        ]
        fake_client = MagicMock()
        fake_client.lrange.return_value = fake_payloads

        with override_settings(CACHE_BACKEND_NAME='redis', REDIS_URL='redis://fake:6379/0'):
            with patch.object(self.store, '_get_redis_client', return_value=fake_client):
                snap = self.store.snapshot(window_seconds=60)

        self.assertEqual(snap['source'], 'redis')
        self.assertEqual(snap['count'], 1)  # kun den nye
        self.assertEqual(snap['avg_ms'], 10.0)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminStatusTilgangTests(TestCase):
    """Verifiserer at kun admin kan nå endepunktene."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin1', password='testpass123', role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.lead = CustomUser.objects.create_user(
            username='lead1', password='testpass123', role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.lead, 'leder')
        self.read_only = CustomUser.objects.create_user(
            username='ro1', password='testpass123', role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.read_only, 'leser')

    def test_uinnlogget_omdirigeres_til_login(self):
        resp = self.client.get('/portal-admin/server-status/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)

    def test_lead_nektes(self):
        self.client.force_login(self.lead)
        resp = self.client.get('/portal-admin/server-status/')
        self.assertEqual(resp.status_code, 403)

    def test_read_only_nektes(self):
        self.client.force_login(self.read_only)
        resp = self.client.get('/portal-admin/server-status/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_har_tilgang_html(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/server-status/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Server-status')

    def test_admin_har_tilgang_json(self):
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/server-status/json/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/json')
        data = resp.json()
        self.assertIn('metrics_5min', data)
        self.assertIn('metrics_1min', data)
        self.assertIn('worker_config', data)
        self.assertIn('konfig', data)


@override_settings(SECURE_SSL_REDIRECT=False)
class LastBackupInfoTests(TestCase):
    """Tester at "Siste vellykkede backup"-kortet viser data når backups finnes.

    Bug-fix april 2026: tidligere brukte _get_last_backup_info en
    `filter(status='success')` mot et felt som ikke finnes på Backup-modellen.
    Dette gjorde at kortet alltid viste "Ingen backup funnet".
    """

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin1', password='testpass123', role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')

    def test_uten_backups_returnerer_found_false(self):
        from .admin_status import _get_last_backup_info
        info = _get_last_backup_info()
        self.assertFalse(info['found'])
        self.assertIn('offsite', info, 'offsite-kopien rapporteres også uten lokal backup')

    def test_med_backup_returnerer_found_true(self):
        from .admin_status import _get_last_backup_info
        from core.models import Backup
        Backup.objects.create(
            filename='backup_2026-04-26_120000.json.gz',
            kind='auto',
            size_bytes=12345,
        )
        info = _get_last_backup_info()
        self.assertTrue(info['found'])
        self.assertEqual(info['filename'], 'backup_2026-04-26_120000.json.gz')
        self.assertEqual(info['size_bytes'], 12345)
        self.assertEqual(info['kind'], 'auto')
        self.assertIn('age_minutes', info)
        self.assertIn('created_at', info)

    def test_henter_nyeste_av_flere(self):
        from .admin_status import _get_last_backup_info
        from core.models import Backup
        # Opprett flere backups; siste skal vinne
        Backup.objects.create(filename='gammel.json.gz', kind='auto', size_bytes=100)
        Backup.objects.create(filename='midt.json.gz', kind='manual', size_bytes=200)
        nyeste = Backup.objects.create(filename='nyeste.json.gz', kind='auto', size_bytes=300)
        info = _get_last_backup_info()
        self.assertEqual(info['filename'], 'nyeste.json.gz')
        self.assertEqual(info['size_bytes'], 300)

    def test_status_payload_inneholder_backup_info(self):
        # End-to-end: backup-info skal komme med i JSON-responsen
        from core.models import Backup
        Backup.objects.create(filename='end2end.json.gz', kind='auto', size_bytes=999)
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/server-status/json/')
        self.assertEqual(resp.status_code, 200)
        backup = resp.json().get('last_backup', {})
        self.assertTrue(backup.get('found'))
        self.assertEqual(backup.get('filename'), 'end2end.json.gz')


@override_settings(SECURE_SSL_REDIRECT=False)
class MetricsMiddlewareIntegrationTests(TestCase):
    """End-to-end: verifiser at middleware faktisk registrerer requests."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin1', password='testpass123', role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        metrics_store.reset()

    def test_request_registreres_i_metrics(self):
        self.client.force_login(self.admin)
        # Kall et vanlig API-endepunkt (ikke selve status)
        self.client.get('/pasienter/api/patients/')

        snap = metrics_store.snapshot(window_seconds=60)
        self.assertGreaterEqual(snap['count'], 1)

    def test_server_status_endepunkt_ignoreres(self):
        self.client.force_login(self.admin)
        metrics_store.reset()

        # Kun kall server-status – skal IKKE telles
        self.client.get('/portal-admin/server-status/json/')

        snap = metrics_store.snapshot(window_seconds=60)
        self.assertEqual(snap['count'], 0)


# ── Sesjonshåndtering ────────────────────────────────────────────────────────
# Tester for /admin/server-status/sessions/ og kill-endepunktene.

from django.contrib.sessions.models import Session  # noqa: E402
from audit.models import AuditLog  # noqa: E402


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminSessionsListTests(TestCase):
    """Verifiserer GET /admin/server-status/sessions/."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='adm', password='testpass123', role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.lead = CustomUser.objects.create_user(
            username='lederen', password='testpass123', role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.lead, 'leder')
        self.read_only = CustomUser.objects.create_user(
            username='leser', password='testpass123', role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.read_only, 'leser')

    def test_uinnlogget_nektes(self):
        resp = self.client.get('/portal-admin/server-status/sessions/')
        self.assertEqual(resp.status_code, 302)

    def test_lead_nektes(self):
        self.client.force_login(self.lead)
        resp = self.client.get('/portal-admin/server-status/sessions/')
        self.assertEqual(resp.status_code, 403)

    def test_status_side_inneholder_csrf_token_holder(self):
        """Regresjon: server-status-siden må ha #csrf-token-holder med en
        rendret csrfmiddlewaretoken-input. Uten denne kan ikke JS sende
        X-CSRFToken-header (cookien er HttpOnly), og POST-handlinger som
        utlogging gir 403 Forbidden."""
        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/server-status/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode('utf-8')
        self.assertIn('id="csrf-token-holder"', body,
                      'csrf-token-holder mangler – JS kan ikke hente CSRF-token')
        self.assertIn('name="csrfmiddlewaretoken"', body,
                      '{% csrf_token %} er ikke rendret inne i holder')

    def test_admin_ser_paalogget_brukere(self):
        # Logg inn lead i en separat klient slik at sesjonen lagres i DB
        c2 = Client()
        c2.login(username='lederen', password='testpass123')
        c3 = Client()
        c3.login(username='leser', password='testpass123')

        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/server-status/sessions/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        usernames = {s['username'] for s in data['sessions']}
        # Alle tre er pålogget
        self.assertIn('lederen', usernames)
        self.assertIn('leser', usernames)
        self.assertIn('adm', usernames)
        # Verifiser felt
        for s in data['sessions']:
            self.assertIn('session_key', s)
            self.assertIn('role', s)

    def test_anonym_sesjon_uten_bruker_filtreres_bort(self):
        # Be om en side som setter en sesjon-cookie uten å logge inn
        c2 = Client()
        c2.get('/accounts/login/')  # initierer en anonym sesjon

        self.client.force_login(self.admin)
        resp = self.client.get('/portal-admin/server-status/sessions/')
        data = resp.json()
        # Sesjoner i listen skal alle ha brukernavn (ingen anonyme)
        for s in data['sessions']:
            self.assertTrue(s['username'])


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminSessionKillTests(TestCase):
    """Verifiserer POST /admin/server-status/sessions/kill/."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='adm', password='testpass123', role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.lead = CustomUser.objects.create_user(
            username='lederen', password='testpass123', role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.lead, 'leder')

    def _get_session_key(self, username, password):
        """Logg inn og returner session_key."""
        c = Client()
        c.login(username=username, password=password)
        return c.session.session_key

    def test_lead_nektes(self):
        self.client.force_login(self.lead)
        resp = self.client.post('/portal-admin/server-status/sessions/kill/', {'session_key': 'x'})
        self.assertEqual(resp.status_code, 403)

    def test_mangler_session_key_gir_400(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/portal-admin/server-status/sessions/kill/', {})
        self.assertEqual(resp.status_code, 400)

    def test_ukjent_session_key_gir_404(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/portal-admin/server-status/sessions/kill/',
                                {'session_key': 'finnesikke'})
        self.assertEqual(resp.status_code, 404)

    def test_admin_kan_ikke_logge_ut_seg_selv(self):
        self.client.force_login(self.admin)
        my_key = self.client.session.session_key
        resp = self.client.post('/portal-admin/server-status/sessions/kill/',
                                {'session_key': my_key})
        self.assertEqual(resp.status_code, 400)
        # Min sesjon skal fortsatt finnes
        self.assertTrue(Session.objects.filter(session_key=my_key).exists())

    def test_admin_kan_logge_ut_annen_bruker(self):
        lead_key = self._get_session_key('lederen', 'testpass123')
        self.assertTrue(Session.objects.filter(session_key=lead_key).exists())

        self.client.force_login(self.admin)
        resp = self.client.post('/portal-admin/server-status/sessions/kill/',
                                {'session_key': lead_key})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['username'], 'lederen')
        # Sesjon er borte fra DB
        self.assertFalse(Session.objects.filter(session_key=lead_key).exists())

    def test_endepunkt_returnerer_json_ikke_html(self):
        """Regresjon: en gang returnerte serveren HTML-feilside (CSRF-feil) som
        krasjet klientens res.json() med 'Unexpected token <'. Dette verifiserer
        at suksess-respons har Content-Type=application/json og parser-bar JSON."""
        lead_key = self._get_session_key('lederen', 'testpass123')
        self.client.force_login(self.admin)
        resp = self.client.post('/portal-admin/server-status/sessions/kill/',
                                {'session_key': lead_key})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp['Content-Type'])
        # Skal være gyldig JSON, ikke HTML
        body = resp.content.decode('utf-8')
        self.assertFalse(body.lstrip().startswith('<'),
                         f'Endepunktet returnerte HTML i stedet for JSON: {body[:80]}')
        data = resp.json()
        self.assertTrue(data['ok'])

    def test_kill_logges_i_audit(self):
        lead_key = self._get_session_key('lederen', 'testpass123')
        self.client.force_login(self.admin)
        AuditLog.objects.all().delete()
        self.client.post('/portal-admin/server-status/sessions/kill/',
                         {'session_key': lead_key})
        log = AuditLog.objects.filter(field_name='force_logout').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.admin)
        self.assertIn('lederen', log.new_value)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminSessionKillAllTests(TestCase):
    """Verifiserer POST /admin/server-status/sessions/kill-all/."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='adm', password='testpass123', role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.lead = CustomUser.objects.create_user(
            username='lederen', password='testpass123', role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.lead, 'leder')
        self.ro = CustomUser.objects.create_user(
            username='leser', password='testpass123', role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.ro, 'leser')

    def test_lead_nektes(self):
        self.client.force_login(self.lead)
        resp = self.client.post('/portal-admin/server-status/sessions/kill-all/',
                                {'confirm': 'YES'})
        self.assertEqual(resp.status_code, 403)

    def test_mangler_bekreftelse_gir_400(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/portal-admin/server-status/sessions/kill-all/', {})
        self.assertEqual(resp.status_code, 400)

    def test_logger_ut_alle_unntatt_admin(self):
        # 2 andre brukere logger inn
        c2 = Client(); c2.login(username='lederen', password='testpass123')
        c3 = Client(); c3.login(username='leser', password='testpass123')
        lead_key = c2.session.session_key
        ro_key = c3.session.session_key

        self.client.force_login(self.admin)
        my_key = self.client.session.session_key

        resp = self.client.post('/portal-admin/server-status/sessions/kill-all/',
                                {'confirm': 'YES'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertGreaterEqual(data['deleted'], 2)
        # Min sesjon består
        self.assertTrue(Session.objects.filter(session_key=my_key).exists())
        # Andre er borte
        self.assertFalse(Session.objects.filter(session_key=lead_key).exists())
        self.assertFalse(Session.objects.filter(session_key=ro_key).exists())

    def test_kill_all_logges_i_audit(self):
        c2 = Client(); c2.login(username='lederen', password='testpass123')
        self.client.force_login(self.admin)
        AuditLog.objects.all().delete()
        self.client.post('/portal-admin/server-status/sessions/kill-all/',
                         {'confirm': 'YES'})
        log = AuditLog.objects.filter(field_name='force_logout').first()
        self.assertIsNotNone(log)
        self.assertIn('force_logout_all', log.new_value)
        self.assertIn('by=adm', log.new_value)


class TregesteStierTests(TestCase):
    """`tregeste_stier()` (13. sep. 2026): P95 per sti, stier med under tre
    treff utelatt, tregeste først."""

    def setUp(self):
        self.store = _MetricsStore()

    def test_sorterer_paa_p95_og_utelater_enkelttreff(self):
        for ms in (10, 20, 30, 40):
            self.store.record('/pasienter/api/liste/', 'GET', 200, ms)
        for ms in (100, 900, 950):
            self.store.record('/statistikk/api/x/', 'GET', 200, ms)
        self.store.record('/en-gang/', 'GET', 200, 5000)
        ut = self.store.tregeste_stier(window_seconds=60)
        self.assertEqual([r['path'] for r in ut], ['/statistikk/api/x/', '/pasienter/api/liste/'])
        self.assertEqual(ut[0]['count'], 3)
        self.assertGreaterEqual(ut[0]['p95_ms'], 900)
        self.assertNotIn('/en-gang/', [r['path'] for r in ut], 'én treg request er ikke et mønster')

    def test_tom(self):
        self.assertEqual(self.store.tregeste_stier(), [])

    def test_antall_begrenser(self):
        for i in range(8):
            for ms in (1, 2, 3):
                self.store.record(f'/sti-{i}/', 'GET', 200, ms + i)
        self.assertEqual(len(self.store.tregeste_stier(antall=5)), 5)


class UtvidetStatusTests(TestCase):
    """De nye kortene (13. sep. 2026). Hver innhenter skal tåle at delen den
    leser mangler, og payloaden skal bære alle nøklene klienten leser."""

    def setUp(self):
        self.client = Client()
        self.admin = CustomUser.objects.create_user(
            username='admin1', password='testpass123', role='admin', must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')

    def test_payload_har_alle_nokler(self):
        from .admin_status import _build_status_payload
        p = _build_status_payload()
        for n in ('memory', 'db_health', 'disk', 'tregeste', 'vaktbilde', 'konfig',
                  'innlogging', 'cron', 'epost', 'last_backup', 'cache_health'):
            self.assertIn(n, p, n)
        self.assertNotIn('memory_mb', p, 'gammel nøkkel byttet ut med memory.naa/topp')

    def test_minne_har_naa_og_topp(self):
        from .admin_status import _get_memory_mb
        m = _get_memory_mb()
        self.assertEqual(set(m), {'naa', 'topp'})
        self.assertIsNotNone(m['naa'])
        self.assertLessEqual(m['naa'], m['topp'] + 1, 'nå kan ikke være over toppen')

    def test_db_health(self):
        from .admin_status import _get_db_health
        d = _get_db_health()
        self.assertTrue(d['healthy'])
        self.assertIsNotNone(d['latency_ms'])
        self.assertIn(d['vendor'], ('sqlite', 'postgresql'))

    def test_disk(self):
        from .admin_status import _get_disk
        d = _get_disk()
        self.assertIn('brukt_prosent', d)
        self.assertGreater(d['total_mb'], 0)

    def test_konfigsjekk_flagger_debug_og_offsite(self):
        from .admin_status import _get_konfig_sjekk
        with override_settings(DEBUG=True):
            k = _get_konfig_sjekk()
        rader = {r['nokkel']: r for r in k['rader']}
        self.assertFalse(rader['DEBUG']['ok'])
        self.assertFalse(rader['Offsite backup']['ok'])
        self.assertFalse(k['alle_ok'])
        self.assertIn('bygg', k['versjon'])
        with override_settings(DEBUG=False):
            self.assertTrue({r['nokkel']: r for r in _get_konfig_sjekk()['rader']}['DEBUG']['ok'])

    def test_innlogging_teller_feilede(self):
        from accounts.models import LoginEvent
        from .admin_status import _get_innlogging
        for i in range(3):
            LoginEvent.objects.create(username_attempt='kari', success=False, ip='10.0.0.1',
                                      event_type=LoginEvent.EVENT_LOGIN)
        LoginEvent.objects.create(username_attempt='ola', success=False, ip='10.0.0.2',
                                  event_type=LoginEvent.EVENT_LOGIN)
        LoginEvent.objects.create(user=self.admin, username_attempt='admin1', success=True,
                                  event_type=LoginEvent.EVENT_LOGIN)
        LoginEvent.objects.create(user=self.admin, username_attempt='admin1', success=False,
                                  event_type=LoginEvent.EVENT_MFA_VERIFY_FAILED)
        i = _get_innlogging()
        self.assertEqual((i['feilede'], i['feilede_brukernavn'], i['feilede_ip'], i['vellykkede'], i['mfa_feilet']),
                         (4, 2, 2, 1, 1))

    def test_vaktbilde(self):
        from django.utils import timezone
        from oppdrag import choices
        from oppdrag.models import Enhet, Lokasjon, Oppdrag
        from core.vakt import hent_aktiv_vakt
        from vaktliste.models import Vaktliste
        from vaktliste import choices as vl
        from .admin_status import _get_vaktbilde
        vakt = hent_aktiv_vakt()
        Vaktliste.objects.create(vakt=vakt, status=vl.DRIFT, satt_i_drift_at=timezone.now())
        enhet = Enhet.objects.create(navn='Bil 1')
        lok = Lokasjon.objects.create(navn='Scene')

        def lag(nr, **kw):
            return Oppdrag.objects.create(vakt=vakt, oppdragsnummer=nr, enhet=enhet, lokasjon=lok,
                                          problemstilling='Udefinert', hastegrad='Akutt', **kw)
        lag(1, status=choices.VENTER)
        lag(2, status=choices.VENTER, trenger_ressurs=True)
        lag(3, status=choices.LEDIG, historikk_fra=timezone.now())
        v = _get_vaktbilde()
        self.assertEqual(v['aktiv_vakt']['id'], vakt.pk)
        self.assertEqual(len(v['vaktlister_i_drift']), 1)
        self.assertIsNone(v['siste_utsending'])
        self.assertEqual((v['oppdrag']['paa_tavla'], v['oppdrag']['ventende'], v['oppdrag']['trenger_ressurs']),
                         (2, 1, 1))
        self.assertIsNotNone(v['oppdrag']['eldste_ventende_minutter'])

    def test_cron_uten_kjoringer_og_med(self):
        from core.kommando import registrer_kjoring
        from .admin_status import _get_cron
        c = _get_cron()
        # To jobber, ikke tre: `db_backup` sto her uten å være satt opp i
        # Railway, og backup er ikke lenger en cron-jobb i det hele tatt —
        # klokka er en tråd i web-prosessen, som eier volumet.
        self.assertEqual(set(c), {'purge_old_logs', 'kollaps_arkiv'})
        self.assertIsNone(c['purge_old_logs'])
        registrer_kjoring('purge_old_logs', True)
        c = _get_cron()
        self.assertTrue(c['purge_old_logs']['ok'])
        self.assertIsNotNone(c['purge_old_logs']['timer_siden'])

    def test_epost_transport(self):
        from .admin_status import _get_epost
        with override_settings(EMAIL_BACKEND='core.mail_backends.AhaSendApiBackend'):
            self.assertEqual(_get_epost()['transport'], 'ahasend')
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'):
            self.assertEqual(_get_epost()['transport'], 'console')

    def test_json_endepunktet_baerer_de_nye_kortene(self):
        self.client.login(username='admin1', password='testpass123')
        with override_settings(SECURE_SSL_REDIRECT=False):
            r = self.client.get(reverse('portaladmin:admin_server_status_json'))
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn('naa', d['memory'])
        self.assertIn('rader', d['konfig'])
        self.assertIn('offsite', d['last_backup'])

    def test_siden_har_de_nye_kortene(self):
        self.client.login(username='admin1', password='testpass123')
        with override_settings(SECURE_SSL_REDIRECT=False):
            html = self.client.get(reverse('portaladmin:admin_server_status')).content.decode()
        for id_ in ('memory', 'memory-peak', 'db-latency', 'db-conns', 'disk-used', 'offsite-status',
                    'vakt-navn', 'vakt-drift', 'vakt-oppdrag', 'tregeste', 'konfig-rader', 'konfig-versjon',
                    'login-failed', 'cron-rader', 'epost-transport'):
            self.assertIn(f'id="{id_}"', html, id_)
