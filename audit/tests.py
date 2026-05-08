"""Tester for audit-appen, inkludert purge_old_logs management-kommando.

Kjør med: python manage.py test audit
"""
from io import StringIO
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command

from accounts.models import CustomUser, LoginEvent
from audit.models import AuditLog


def _create_login_event(user, days_ago):
    """Hjelpefunksjon: opprett LoginEvent med kunstig created_at."""
    evt = LoginEvent.objects.create(
        user=user,
        username_attempt=user.username,
        success=True,
        ip='127.0.0.1',
    )
    # Oppdater created_at direkte (auto_now_add tillater ikke dette via create)
    LoginEvent.objects.filter(pk=evt.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )
    return evt


def _create_audit_log(user, days_ago):
    """Hjelpefunksjon: opprett AuditLog med kunstig created_at."""
    log = AuditLog.objects.create(
        table_name='test',
        record_id=1,
        action='CREATE',
        user=user,
    )
    AuditLog.objects.filter(pk=log.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )
    return log


class PurgeOldLogsTests(TestCase):
    """Tester for purge_old_logs management-kommando."""

    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(
            username='purgebruker',
            password='Passord123!',
            role='read_only',
        )

    def test_purge_deletes_old_login_events(self):
        """Eldre login-events (> 730 dager) skal slettes."""
        old_evt = _create_login_event(self.user, days_ago=731)
        out = StringIO()
        call_command('purge_old_logs', stdout=out)
        self.assertFalse(
            LoginEvent.objects.filter(pk=old_evt.pk).exists(),
            'Gammel login-event skal være slettet',
        )

    def test_purge_keeps_recent_login_events(self):
        """Nylige login-events (< 730 dager) skal ikke slettes."""
        recent_evt = _create_login_event(self.user, days_ago=10)
        out = StringIO()
        call_command('purge_old_logs', stdout=out)
        self.assertTrue(
            LoginEvent.objects.filter(pk=recent_evt.pk).exists(),
            'Nylig login-event skal ikke slettes',
        )

    def test_purge_dry_run_does_not_delete(self):
        """--dry-run skal ikke slette noen data."""
        old_evt = _create_login_event(self.user, days_ago=800)
        old_log = _create_audit_log(self.user, days_ago=800)
        out = StringIO()
        call_command('purge_old_logs', dry_run=True, stdout=out)
        output = out.getvalue()
        # Data skal fortsatt finnes
        self.assertTrue(
            LoginEvent.objects.filter(pk=old_evt.pk).exists(),
            'Dry-run skal ikke slette login-events',
        )
        self.assertTrue(
            AuditLog.objects.filter(pk=old_log.pk).exists(),
            'Dry-run skal ikke slette audit-logger',
        )
        self.assertIn('Tørrkjøring', output)

    def test_purge_custom_days_argument(self):
        """--days N skal bruke N dager som grense."""
        # 100 dager gammelt skal slettes med --days 90
        medium_evt = _create_login_event(self.user, days_ago=100)
        # 50 dager gammelt skal ikke slettes med --days 90
        recent_evt = _create_login_event(self.user, days_ago=50)
        out = StringIO()
        call_command('purge_old_logs', days=90, stdout=out)
        self.assertFalse(
            LoginEvent.objects.filter(pk=medium_evt.pk).exists(),
            '100-dager gammel event skal slettes med --days 90',
        )
        self.assertTrue(
            LoginEvent.objects.filter(pk=recent_evt.pk).exists(),
            '50-dager gammel event skal ikke slettes med --days 90',
        )

    def test_purge_deletes_old_audit_logs(self):
        """Eldre AuditLog-poster skal slettes."""
        old_log = _create_audit_log(self.user, days_ago=800)
        out = StringIO()
        call_command('purge_old_logs', stdout=out)
        self.assertFalse(
            AuditLog.objects.filter(pk=old_log.pk).exists(),
            'Gammel audit-log skal være slettet',
        )

    def test_purge_keeps_recent_audit_logs(self):
        """Nylige AuditLog-poster skal ikke slettes."""
        recent_log = _create_audit_log(self.user, days_ago=30)
        out = StringIO()
        call_command('purge_old_logs', stdout=out)
        self.assertTrue(
            AuditLog.objects.filter(pk=recent_log.pk).exists(),
            'Nylig audit-log skal ikke slettes',
        )
