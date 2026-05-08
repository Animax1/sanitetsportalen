"""Kjør en automatisk backup. Brukes av Railway cron-service.

Eksempel: python manage.py db_backup
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from patients.backup_service import create_backup, purge_old_backups
from patients.models import BackupConfig


class Command(BaseCommand):
    help = 'Lag automatisk backup og slett gamle.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Kjør selv om intervall=Av')

    def handle(self, *args, **opts):
        cfg = BackupConfig.get()
        if cfg.interval_minutes == 0 and not opts['force']:
            self.stdout.write('Backup er slått av (intervall=0). Bruk --force for å kjøre.')
            return

        backup = create_backup(kind='auto', note='Automatisk via cron')
        cfg.last_run_at = timezone.now()
        cfg.save(update_fields=['last_run_at'])

        purged = purge_old_backups()
        if backup is None:
            # #0: identisk innhold som forrige auto-backup — hoppet over
            self.stdout.write(
                f'OK: auto-backup hoppet over (identisk innhold). Slettet {purged} gamle.'
            )
        else:
            self.stdout.write(
                f'OK: {backup.filename} ({backup.size_bytes} bytes). Slettet {purged} gamle.'
            )
