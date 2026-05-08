"""Management-kommando for å slette gamle revisjonslogger og innloggingshendelser.

Kjøres som:
  python manage.py purge_old_logs                # Slett eldre enn 730 dager (2 år)
  python manage.py purge_old_logs --days 365     # Slett eldre enn 365 dager
  python manage.py purge_old_logs --dry-run      # Rapporter uten å slette

Kan kjøres av Railway Cron eller annen scheduler daglig.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from accounts.models import LoginEvent
from audit.models import AuditLog


class Command(BaseCommand):
    help = 'Slett gamle revisjonslogger og innloggingshendelser'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=730,
            help='Slett poster eldre enn N dager (standard: 730 = 2 år)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Rapporter antall som ville bli slettet uten å faktisk slette',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        if dry_run:
            self.stdout.write(f'[Tørrkjøring] Viser hva som ville blitt slettet (eldre enn {days} dager):')

        # ── Slett LoginEvent ──────────────────────────────────────────────────
        login_qs = LoginEvent.objects.filter(created_at__lt=cutoff)
        login_count = login_qs.count()
        if dry_run:
            self.stdout.write(f'  Ville slettet {login_count} login-events eldre enn {days} dager.')
        else:
            login_qs.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Slettet {login_count} login-events eldre enn {days} dager.'
            ))

        # ── Slett AuditLog ────────────────────────────────────────────────────
        audit_qs = AuditLog.objects.filter(created_at__lt=cutoff)
        audit_count = audit_qs.count()
        if dry_run:
            self.stdout.write(f'  Ville slettet {audit_count} audit-logger eldre enn {days} dager.')
        else:
            audit_qs.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Slettet {audit_count} audit-logger eldre enn {days} dager.'
            ))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'[Tørrkjøring fullført] Ingen data ble slettet. '
                f'Kjør uten --dry-run for å slette.'
            ))
