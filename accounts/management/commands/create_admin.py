"""Management-kommando for å opprette første admin-bruker.

Idempotent: kan trygt kjøres ved hver oppstart. Oppretter admin hvis brukeren
ikke finnes, ellers går den stille ut uten feil.
"""
from django.core.management.base import BaseCommand
from accounts.models import CustomUser


class Command(BaseCommand):
    help = 'Opprett admin-bruker for bootstrapping. Idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='Brukernavn')
        parser.add_argument('--email', default=None, help='E-postadresse (valgfritt)')
        parser.add_argument('--password', required=True, help='Passord')

    def handle(self, *args, **options):
        username = options['username']
        email = options['email'] or None
        password = options['password']

        existing = CustomUser.objects.filter(username=username).first()
        if existing is not None:
            self.stdout.write(
                self.style.WARNING(
                    f'Admin-bruker «{username}» finnes allerede — hopper over.'
                )
            )
            return

        user = CustomUser.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Admin-bruker «{user.username}» er opprettet med role=admin, is_staff=True, is_superuser=True.'
            )
        )
