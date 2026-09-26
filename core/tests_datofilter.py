"""Et ugyldig datofilter i URL-en gir siden uten filteret, ikke 500 (26. sep. 2026, B6).

`?date_from=2026-13-45` gikk rett inn i `created_at__date__gte`, og Django
kastet `ValidationError` — en 500 på tre admin-sider for en skrivefeil i
adresselinja. Filteret leses nå av `core.validators.les_iso_dato()`, og en
verdi som ikke er en dato ignoreres og vises tom, så det synes at filteret
ikke ble brukt.
"""
from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from core.validators import les_iso_dato

UGYLDIGE = ('2026-13-45', 'i går', '2026-02-30', '99999-01-01')


class LesIsoDatoTests(SimpleTestCase):

    def test_gyldig(self):
        self.assertEqual(les_iso_dato('2026-09-26'), date(2026, 9, 26))
        self.assertEqual(les_iso_dato(' 2026-09-26 '), date(2026, 9, 26))

    def test_tomt_og_ugyldig_er_none(self):
        for raa in ('', None, *UGYLDIGE):
            with self.subTest(raa=raa):
                self.assertIsNone(les_iso_dato(raa))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SideneTaalerUgyldigDatoTests(TestCase):

    def setUp(self):
        admin = CustomUser.objects.create_user(
            username='adm_dato', password='x', role='admin', must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        self.client.force_login(admin)

    def test_ingen_500(self):
        for url in ('/portal-admin/auditlog/', '/portal-admin/auditlog/eksport.csv',
                    '/portal-admin/innloggingslogg/'):
            for felt in ('date_from', 'date_to'):
                for raa in UGYLDIGE:
                    with self.subTest(url=url, felt=felt, raa=raa):
                        self.assertEqual(self.client.get(url, {felt: raa}).status_code, 200)

    def test_gyldig_filter_virker_fortsatt(self):
        """En sperre som ignorerer alt, ville også vært grønn over."""
        from audit.models import AuditLog
        AuditLog.objects.create(table_name='t', record_id=1, action='UPDATE')
        res = self.client.get('/portal-admin/auditlog/', {'date_from': '2999-01-01'})
        self.assertEqual(res.context['page_obj'].paginator.count, 0)
        res = self.client.get('/portal-admin/auditlog/', {'date_from': '2000-01-01'})
        self.assertEqual(res.context['page_obj'].paginator.count, 1)
