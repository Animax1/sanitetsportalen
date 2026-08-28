"""Les-only kontroll av ``ModulTilgang``.

Kommandoen skriver aldri noe. Den svarer på spørsmål om matrisen som ikke
gir seg selv av å bla gjennom brukerlista.

**Halve kommandoen ble fjernet i deploy 2, ikke deaktivert.** Fram til da
sammenlignet den matrisen med det `role` tilsa, og telte kontoene §10.1 spurte
etter — de som hadde skrivetilgang uten ``kan_redigere_pasienter``. Begge
spørsmålene krevde at de fire tilgangsverdiene fantes i feltet. Etter
krympingen gjør de ikke det, og en sammenligning ville ikke feilet: den ville
sagt «ingen avvik» og «Antall: 0» om hver eneste database. Et svar som alltid
er grønt er verre enn ingen kontroll.

Svaret på §10.1 ble tatt mot prod mellom deploy 1 og 2, og står i CHANGELOG.
Det kan ikke tas om igjen — heller ikke ved å rulle tilbake, siden
reverseringen av migrasjonen gir alle den samme rollen.

Det som er igjen er kontroller som holder seg like sanne om ti moduler:

1. **Kontoer uten en eneste rad** ser en tom portal. Global admin trenger
   ingen rader; alle andre er sannsynligvis opprettet uten at matrisen ble satt.
2. **Rader på en modul som ikke finnes** gir ingenting. En slug som er skrevet
   feil, eller en modul som er fjernet fra registeret, etterlater rader som ser
   ut som tilgang uten å være det.
3. **Rolleverdier feltet ikke kjenner** er data migrasjonen ikke fikk tak i.
"""
from django.core.management.base import BaseCommand

from accounts.models import CustomUser, TilgangsNivaa, UserRole
from core.modules import get_all_modules


class Command(BaseCommand):
    help = 'Les-only kontroll av ModulTilgang. Skriver ingenting.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--vis-alle', action='store_true',
            help='List hver konto med radene sine, ikke bare funnene.',
        )

    def handle(self, *args, **opts):
        brukere = list(
            CustomUser.objects.all().order_by('username').prefetch_related('modultilganger')
        )
        if not brukere:
            self.stdout.write(self.style.WARNING('Ingen brukere i databasen.'))
            return

        kjente_moduler = {m.slug for m in get_all_modules()}
        kjente_nivaa = set(TilgangsNivaa.values)

        uten_rader, ukjent_modul, ukjent_nivaa, ukjent_rolle = [], [], [], []
        for b in brukere:
            rader = {(t.modul_slug, t.nivaa) for t in b.modultilganger.all()}

            if b.role != 'admin' and not rader:
                uten_rader.append(b)
            for slug, nivaa in sorted(rader):
                if slug not in kjente_moduler:
                    ukjent_modul.append((b, slug, nivaa))
                if nivaa not in kjente_nivaa:
                    ukjent_nivaa.append((b, slug, nivaa))
            if b.role not in UserRole.values:
                ukjent_rolle.append(b)

            if opts['vis_alle']:
                vist = ', '.join(f'{s}:{n}' for s, n in sorted(rader)) or '(ingen)'
                self.stdout.write(f'  {b.username:24} {b.role:8} {vist}')

        self._seksjon(
            'Kontoer uten en eneste ModulTilgang-rad (ser en tom portal)',
            [f'{b.username} ({b.role})' for b in uten_rader],
            'Global admin trenger ingen rader; disse er ikke admin.\n'
            'Sannsynligvis opprettet uten at matrisen ble satt.',
        )
        self._seksjon(
            'Rader på en modul som ikke finnes i registeret',
            [f'{b.username}: {slug}:{nivaa}' for b, slug, nivaa in ukjent_modul],
            'Radene gir ingen tilgang — `har_tilgang` slår opp på slug.\n'
            'Enten er slugen skrevet feil, eller så er modulen fjernet.',
        )
        self._seksjon(
            'Rader med et nivå stigen ikke kjenner',
            [f'{b.username}: {slug}:{nivaa}' for b, slug, nivaa in ukjent_nivaa],
            'Et ukjent nivånavn gir False, ikke True — kontoen er stengt ute\n'
            'av modulen den ser ut til å ha tilgang til.',
        )
        self._seksjon(
            'Kontoer med en rolleverdi feltet ikke kjenner',
            [f'{b.username} ({b.role})' for b in ukjent_rolle],
            'Deploy 2 skrev alt som ikke var `admin` om til `bruker`.\n'
            'En verdi utenfor de to er rader migrasjonen ikke fikk tak i.',
        )

        self.stdout.write('')
        self.stdout.write(
            f'{len(brukere)} kontoer kontrollert. Kommandoen har ikke skrevet noe.')

    def _seksjon(self, tittel, linjer, forklaring):
        """Én overskrift, funnene under, og hva de betyr — eller «Ingen»."""
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(tittel))
        if not linjer:
            self.stdout.write('  Ingen.')
            return
        for linje in linjer:
            self.stdout.write(self.style.WARNING(f'  {linje}'))
        for linje in forklaring.split('\n'):
            self.stdout.write(f'  {linje}')
