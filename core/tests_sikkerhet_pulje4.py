"""Sikkerhetsgjennomgangen 28. sep. 2026, pulje 4: rammeverksdelen.

- Auditeksporten nøytraliserer formler også i brukernavn- og feltkolonnene.
  Brukernavn hadde ingen tegnregel før 28. sep., så eldre kontoer kan ha hva som
  helst; feltnavnet kan være en innstillingsnøkkel.
"""
from __future__ import annotations

from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AuditeksportenTests(TestCase):

    def test_formler_i_brukernavn_og_felt_noytraliseres(self):
        admin = CustomUser.objects.create_user(
            username='adm_csv', password='x', role='admin', must_change_password=False)
        gi_standardtilgang(admin, 'admin')
        # Et eldre brukernavn, fra før tegnregelen — skrevet rett i basen.
        gammel = CustomUser.objects.create_user(username='=HYPERLINK("x")', password='x')
        AuditLog.objects.create(table_name='core_x', record_id=1, action='UPDATE',
                                field_name='+SUM(A1)', old_value='a', new_value='b', user=gammel)
        c = Client()
        c.force_login(admin)
        tekst = c.get('/portal-admin/auditlog/eksport.csv').content.decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", tekst)
        self.assertIn("'+SUM(A1)", tekst)
        self.assertNotIn(';=HYPERLINK', tekst)
        self.assertNotIn(';+SUM', tekst)
