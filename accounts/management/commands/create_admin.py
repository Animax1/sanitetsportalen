"""Management-kommando for å opprette første admin-bruker.

Idempotent: kan trygt kjøres ved hver oppstart. Oppretter admin hvis brukeren
ikke finnes, ellers går den stille ut uten feil.
"""
from django.core.management.base import BaseCommand, CommandError
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

        # **Superbrukeren er eksklusiv til bootstrap-kontoen** (André, 15. sep.
        # 2026). Kommandoen er idempotent på *brukernavn*, så den ville laget
        # en superbruker til hver gang den ble kjørt med et nytt navn — og da
        # er «bootstrap-kontoen» ikke lenger én konto, men en kategori. Da
        # betyr heller ikke sperrene mot degradering og sletting det de skal:
        # de verner en nødutgang det finnes flere av.
        annen = CustomUser.objects.filter(is_superuser=True).first()
        if annen is not None:
            raise CommandError(
                f'Portalen har allerede en superbruker: «{annen.username}». '
                f'Superbrukeren er bootstrap-kontoen, og det skal være én. '
                f'Trenger du en administrator til, opprett den i '
                f'brukeradministrasjonen; skal bootstrap-kontoen byttes, må '
                f'«{annen.username}» fjernes først.'
            )

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
