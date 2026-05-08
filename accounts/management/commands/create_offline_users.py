"""Opprett offline-brukere for event-laptop.

Idempotent: hvis brukerne finnes fra før, skriver kommandoen kun ut status.
Ved --rotate genereres nye passord (oppdaterer eksisterende brukere).

Passord skrives til OFFLINE_PASSORD.md i prosjektroten.
Denne filen er gitignore-beskyttet.
"""
import secrets
import string
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.models import CustomUser


OFFLINE_USERS = [
    ('admin-offline', 'admin'),
    ('vakt-offline',  'read_write'),
]

PASSWORD_FILE = Path(settings.BASE_DIR) / 'OFFLINE_PASSORD.md'


def _generate_password(length=12):
    """Generer et sikkert tilfeldig passord: bokstaver + tall + symboler."""
    alphabet = string.ascii_letters + string.digits + '!@#$%&*-_+='
    # Sikre minst én av hver type
    while True:
        pw = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw)
                and any(c in '!@#$%&*-_+=' for c in pw)):
            return pw


class Command(BaseCommand):
    help = 'Opprett offline-brukere (admin-offline, vakt-offline) for laptop-bruk.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--rotate', action='store_true',
            help='Generer nye passord selv om brukerne finnes.',
        )

    def handle(self, *args, **opts):
        rotate = opts['rotate']
        passwords = {}
        for username, role in OFFLINE_USERS:
            user, created = CustomUser.objects.get_or_create(
                username=username,
                defaults={'role': role, 'must_change_password': False, 'mfa_required': False},
            )
            if created or rotate:
                pw = _generate_password()
                user.set_password(pw)
                user.role = role
                user.must_change_password = False
                user.mfa_required = False
                user.save()
                passwords[username] = pw
                action = 'opprettet' if created else 'rotert'
                self.stdout.write(f'  {username} ({role}): passord {action}')
            else:
                self.stdout.write(f'  {username} ({role}): uendret (bruk --rotate for nytt passord)')

        if passwords:
            self._write_password_file(passwords)
            self.stdout.write(self.style.SUCCESS(
                f'\nPassord skrevet til {PASSWORD_FILE.name}. Print ut og oppbevar sikkert.'
            ))
        else:
            self.stdout.write('\nIngen nye passord generert. Bruk --rotate for å rotere.')

    def _write_password_file(self, passwords):
        from django.utils import timezone
        content = [
            '# Offline-passord',
            '',
            f'Generert: {timezone.now().strftime("%Y-%m-%d %H:%M")}',
            '',
            'Disse passordene gjelder KUN offline-versjonen på event-laptopen.',
            'De eksisterer ikke i produksjons-databasen på Railway.',
            '',
            '| Brukernavn | Rolle | Passord |',
            '|---|---|---|',
        ]
        role_map = dict(OFFLINE_USERS)
        for username, pw in passwords.items():
            content.append(f'| `{username}` | {role_map[username]} | `{pw}` |')
        content += [
            '',
            '## Tilgang',
            '',
            'Logg inn via: http://<laptop-ip>:8000',
            '',
            'Finn laptop-IP med `ipconfig` (Windows) under "IPv4-adresse".',
            '',
            '## Sikkerhet',
            '',
            '- Denne filen er ekskludert fra git (se .gitignore).',
            '- Print ut, oppbevar fysisk sikkert.',
            '- Kjør `python manage.py create_offline_users --rotate` for nye passord.',
            '- Slett `offline.sqlite3` etter synkronisering hvis ønskelig.',
        ]
        PASSWORD_FILE.write_text('\n'.join(content), encoding='utf-8')
