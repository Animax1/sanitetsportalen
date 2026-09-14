"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 1 — det som hører hjemme i core.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
import importlib
import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser, ModulTilgang
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog
from core.auth_decorators import NIVAA_HIERARKI, har_tilgang, nivaa_for
from core.jsdata import js_json
from core.klientip import klient_ip, ratelimit_nokkel


class KlientIpTests(SimpleTestCase):
    """H2: siste ledd i X-Forwarded-For, validert, ellers REMOTE_ADDR."""

    def _req(self, xff=None, remote='10.0.0.9'):
        r = RequestFactory().get('/')
        r.META['REMOTE_ADDR'] = remote
        if xff is not None:
            r.META['HTTP_X_FORWARDED_FOR'] = xff
        return r

    def test_siste_ledd_er_det_proxyen_la_til(self):
        self.assertEqual(klient_ip(self._req('1.2.3.4, 5.6.7.8')), '5.6.7.8')
        self.assertEqual(klient_ip(self._req('5.6.7.8')), '5.6.7.8')
        self.assertEqual(klient_ip(self._req(' 2001:db8::1 ')), '2001:db8::1')

    def test_forste_ledd_er_klientens_paastand_og_ignoreres(self):
        self.assertEqual(klient_ip(self._req('9.9.9.9, 5.6.7.8')), '5.6.7.8')

    def test_ugyldig_ledd_gir_remote_addr(self):
        self.assertEqual(klient_ip(self._req('ikke-en-ip')), '10.0.0.9')
        self.assertEqual(klient_ip(self._req('1.2.3.4, <script>')), '10.0.0.9')

    def test_uten_header_er_remote_addr_klienten(self):
        self.assertEqual(klient_ip(self._req()), '10.0.0.9')
        self.assertIsNone(klient_ip(self._req(remote='')))

    def test_port_strippes(self):
        self.assertEqual(klient_ip(self._req('5.6.7.8:1234')), '5.6.7.8')
        self.assertEqual(klient_ip(self._req('[2001:db8::1]:1234')), '2001:db8::1')

    def test_ratelimit_nokkel(self):
        self.assertEqual(ratelimit_nokkel('login:ip', self._req('1.1.1.1, 5.6.7.8')), '5.6.7.8')
        self.assertEqual(ratelimit_nokkel('login:ip', self._req(remote='')), 'ukjent')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AuditIpTests(TestCase):
    """H2: auditsporet bruker samme regel — ikke klientens påstand."""

    def test_pasientaudit_logger_proxyens_ledd(self):
        adm = CustomUser.objects.create_user(username='adm_ip', password='x', role='admin',
                                             must_change_password=False)
        gi_standardtilgang(adm, 'admin')
        c = Client(); c.force_login(adm)
        res = c.post('/pasienter/api/patients/', content_type='application/json',
                     data={'grovsortering': 'Rød'},
                     HTTP_X_FORWARDED_FOR='6.6.6.6, 5.6.7.8', REMOTE_ADDR='10.0.0.1')
        self.assertIn(res.status_code, (200, 201), res.content)
        rad = AuditLog.objects.filter(table_name__icontains='patient').order_by('-pk').first()
        self.assertIsNotNone(rad)
        self.assertEqual(rad.ip, '5.6.7.8')


class JsJsonTests(SimpleTestCase):
    """H1: data inn i <script> kan ikke lukke skriptet."""

    def test_escaper_de_tre_tegnene(self):
        ut = str(js_json({'navn': '</script><script>x</script>', 'a': '&<>'}))
        self.assertNotIn('<', ut)
        self.assertNotIn('>', ut)
        self.assertNotIn('&', ut)
        self.assertIn('\\u003c/script\\u003e', ut)

    def test_er_gyldig_json_og_leses_likt(self):
        import json
        verdi = {'x': ['</script>', 1, None, 'æøå']}
        self.assertEqual(json.loads(str(js_json(verdi))), verdi)

    def test_er_trygg_streng(self):
        from django.utils.safestring import SafeData
        self.assertIsInstance(js_json([]), SafeData)


class AdminFaarToppenAvStigenTests(TestCase):
    """M10: `nivaa_for(admin)` er toppen, så `skriv_leder`-kallsteder ikke
    trenger huske `er_global_admin(...) or`."""

    def test_admin_har_skriv_leder(self):
        adm = CustomUser.objects.create_user(username='adm_top', password='x', role='admin',
                                             must_change_password=False)
        self.assertEqual(nivaa_for(adm, 'vaktliste'), max(NIVAA_HIERARKI, key=NIVAA_HIERARKI.get))
        for modul in ('vaktliste', 'oppdrag', 'patients'):
            self.assertTrue(har_tilgang(adm, modul, 'skriv_leder'), modul)
            self.assertTrue(har_tilgang(adm, modul, 'les'), modul)

    def test_vanlig_bruker_uendret(self):
        b = CustomUser.objects.create_user(username='b_top', password='x', must_change_password=False)
        ModulTilgang.objects.create(bruker=b, modul_slug='vaktliste', nivaa='skriv_full')
        self.assertEqual(nivaa_for(b, 'vaktliste'), 'skriv_full')
        self.assertFalse(har_tilgang(b, 'vaktliste', 'skriv_leder'))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class CsvFormelTests(TestCase):
    """M9: en verdi som begynner med `=` skal ikke bli en formel i Excel."""

    def test_csv_trygg(self):
        from core.views_admin import _csv_trygg
        for farlig in ('=1+1', '+1', '-1', '@SUM', '\tx', '\rx'):
            self.assertEqual(_csv_trygg(farlig), "'" + farlig, farlig)
        self.assertEqual(_csv_trygg('Kari'), 'Kari')
        self.assertEqual(_csv_trygg(None), '')
        self.assertEqual(_csv_trygg(''), '')

    def test_eksporten_bruker_den(self):
        adm = CustomUser.objects.create_user(username='adm_csv', password='x', role='admin',
                                             must_change_password=False)
        gi_standardtilgang(adm, 'admin')
        AuditLog.objects.create(table_name='patients_patient', record_id=1, action='UPDATE',
                                field_name='arsak', old_value='=cmd|calc', new_value='Kari')
        c = Client(); c.force_login(adm)
        tekst = c.get('/portal-admin/auditlog/eksport.csv').content.decode('utf-8-sig')
        self.assertIn("'=cmd|calc", tekst)
        self.assertNotIn(';=cmd|calc', tekst)


class OffsiteObjektnavnTests(SimpleTestCase):
    """L3: objektnavnet fra bucketen kan ikke peke ut av BACKUP_DIR."""

    def test_katalogskilletegn_avvises_foer_s3(self):
        from core import offsite
        with mock.patch('core.offsite._klient', side_effect=AssertionError('S3 skal ikke kalles')):
            for objekt in ('backups/../../x.json.gz.enc', 'backups/a/b.json.gz.enc', 'backups/.enc'):
                with self.assertRaises(ValueError, msg=objekt):
                    offsite.hent(objekt)


class SettingsRobusthetTests(SimpleTestCase):
    """L10: ALLOWED_HOSTS med mellomrom, og SECRET_KEY-lengde i prod."""

    def setUp(self):
        import myproject.settings as settings_module
        self.settings_module = settings_module
        self.addCleanup(lambda: importlib.reload(settings_module))

    def _last(self, **env):
        with mock.patch.dict(os.environ, env, clear=False):
            return importlib.reload(self.settings_module)

    def test_allowed_hosts_strippes(self):
        lastet = self._last(ALLOWED_HOSTS='a.example, b.example ,, c.example')
        self.assertEqual(lastet.ALLOWED_HOSTS, ['a.example', 'b.example', 'c.example'])

    def test_kort_secret_key_stopper_prod(self):
        with self.assertRaises(ImproperlyConfigured) as cm:
            self._last(DEBUG='False', SECRET_KEY='x' * 30)
        self.assertIn('30 tegn', str(cm.exception))

    def test_lang_secret_key_slipper_gjennom(self):
        lastet = self._last(DEBUG='False', SECRET_KEY='x' * 50)
        self.assertFalse(lastet.DEBUG)
