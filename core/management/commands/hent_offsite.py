"""Hent en backup ned fra Scaleway — gjenopprettingsveien (13. sep. 2026).

    python manage.py hent_offsite --list
    python manage.py hent_offsite backup-patients-auto-20260913-101500-123456.json.gz

Henter, dekrypterer med OFFSITE_BACKUP_KEY, og legger fila i BACKUP_DIR med
en `Backup`-rad, så den dukker opp under /portal-admin/backup/ og kan
gjenopprettes derfra — eller med `restore_backup`. Rører ikke basen ellers.

Kjøres i containeren (`railway ssh`) eller lokalt med de samme variablene.
Prøvd én gang mot staging før den regnes som ferdig.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core import offsite


class Command(BaseCommand):
    help = 'Hent en kryptert backup fra offsite-bucketen og legg den i BACKUP_DIR.'

    def add_arguments(self, parser):
        parser.add_argument('objekt', nargs='?', help='Objektnavn eller filnavn (som i --list).')
        parser.add_argument('--list', action='store_true', help='List objektene i bucketen.')

    def handle(self, *args, **opts):
        if not offsite.er_konfigurert():
            raise CommandError(
                'Offsite-backup er ikke konfigurert. Mangler: ' + ', '.join(offsite.mangler()))
        if opts['list']:
            objekter = offsite.list_objekter()
            if not objekter:
                self.stdout.write('Bucketen er tom.')
                return
            for o in objekter:
                endret = o['endret'].strftime('%Y-%m-%d %H:%M') if o['endret'] else '?'
                self.stdout.write(f"{endret}  {o['bytes']:>10}  {o['navn'][len(offsite.PREFIKS):]}")
            self.stdout.write(f'{len(objekter)} objekt(er).')
            return
        if not opts['objekt']:
            raise CommandError('Oppgi et objektnavn, eller --list.')
        try:
            backup, sti = offsite.hent(opts['objekt'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:   # noqa: BLE001 — boto-feil skal leses, ikke traces
            raise CommandError(f'Henting feilet: {exc.__class__.__name__}: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(
            f'Hentet og dekryptert {backup.filename} ({backup.size_bytes} bytes) til {sti}. '
            f'Gjenopprett fra /portal-admin/backup/{backup.module_slug}/.'))
