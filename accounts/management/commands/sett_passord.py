r"""Sett et kjent passord på en konto, uten å gå veien om grensesnittet.

Finnes for tilfellet der ingen kommer inn: det midlertidige passordet er borte
eller feillest, invitasjonslenken er utløpt, eller kontoen står i tvungen
passordbytte og ingen vet hva den nåværende verdien er.

**Brukernavnet slås opp tolerant** (samme regel som innlogging), og godtar
`\uXXXX`-rømming for kanaler som ikke bærer norske tegn — Railways `ssh` er en
slik. `sjekk_brukernavn` skriver ut den formen for hver konto.

    python manage.py sett_passord karmøy56
    python manage.py sett_passord 'karmøy56' --behold-tvungen-bytte
    python manage.py sett_passord karmøy56 --passord 'Vaktbil2026!'

Uten `--passord` genereres et passord uten forvekslingstegn, og det skrives ut
én gang. **Som standard fjernes kravet om passordbytte**, slik at kontoen
kommer rett inn i portalen — det er som regel hele poenget med å kjøre denne.
Vil du beholde kravet, bruk `--behold-tvungen-bytte`.

**Sesjonene avsluttes, og handlingen logges** (28. sep. 2026). Kommandoen satte
passordet og ingenting mer: en stjålet sesjon overlevde, og i auditloggen sto
ingenting — mens den samme handlingen i adminflaten gjorde begge deler.
Passordet skrives aldri i loggen, bare at det ble satt og hvor fra.
"""
from django.contrib.auth.password_validation import (
    ValidationError, validate_password,
)
from django.core.management.base import BaseCommand, CommandError

from accounts import kontolaas
from accounts.backends import finn_kandidater
from accounts.passord import lag_midlertidig_passord
from accounts.sesjoner import avslutt_alle_sesjoner
from audit.models import AuditLog


class Command(BaseCommand):
    help = 'Sett passord på en konto, og fjern eventuelt kravet om passordbytte'

    def add_arguments(self, parser):
        parser.add_argument(
            'brukernavn',
            help=r'Godtar \uXXXX-rømming, f.eks. karmøy56')
        parser.add_argument(
            '--passord',
            help='Passordet som settes. Uten dette genereres ett.')
        parser.add_argument(
            '--behold-tvungen-bytte', action='store_true',
            help='La must_change_password stå. Default er å fjerne det.')

    def handle(self, *args, **options):
        # Samme tolkning som sjekk_brukernavn, slik at utskriften derfra kan
        # limes rett inn her.
        from accounts.management.commands.sjekk_brukernavn import _tolk_rommet
        navn = _tolk_rommet(options['brukernavn'])

        treff = finn_kandidater(navn)
        if not treff:
            raise CommandError(
                f'Fant ingen konto for {navn!r}. Kjør '
                '«python manage.py sjekk_brukernavn» for å se hva som finnes.')
        if len(treff) > 1:
            navnene = ', '.join(t.username for t in treff)
            raise CommandError(
                f'Flere kontoer matcher {navn!r}: {navnene}. '
                'Oppgi det nøyaktige brukernavnet.')

        bruker = treff[0]
        passord = options.get('passord') or lag_midlertidig_passord()

        # Valider mot de samme reglene grensesnittet bruker. Et passord satt
        # her som skjemaet ville avvist, gir en konto brukeren ikke kan endre
        # passordet på uten å møte en feilmelding hen ikke forårsaket.
        try:
            validate_password(passord, bruker)
        except ValidationError as feil:
            raise CommandError(
                'Passordet er ikke gyldig:\n  ' + '\n  '.join(feil.messages))

        bruker.set_password(passord)
        felter = ['password']

        if not options['behold_tvungen_bytte']:
            bruker.must_change_password = False
            felter.append('must_change_password')

        bruker.save(update_fields=felter)
        # Kontolåsen nullstilles: har noen prøvd seg fram, skal ikke den nye
        # verdien møte en sperre satt av forsøkene på den gamle. `laas_opp`
        # tar også maskinlåsene på en delt konto.
        kontolaas.laas_opp(bruker)
        avslutt_alle_sesjoner(bruker)
        AuditLog.objects.create(
            table_name='accounts_customuser', record_id=bruker.pk, action='UPDATE',
            field_name='password', new_value='satt fra kommandolinja (sett_passord)',
        )

        self.stdout.write(self.style.SUCCESS(
            f'Passord satt for {bruker.username!r}.'))
        if not options.get('passord'):
            self.stdout.write(f'  Passord: {passord}')
            self.stdout.write(
                '  (generert uten tegnene 0 O 1 l I, som lett feilleses)')
        if options['behold_tvungen_bytte']:
            self.stdout.write(
                '  Kontoen må fortsatt bytte passord ved innlogging.')
        else:
            self.stdout.write(
                '  Kravet om passordbytte er fjernet — kontoen går rett inn '
                'i portalen.')
        self.stdout.write('  Kontolåsen og telleren for feilede forsøk er nullstilt.')
        self.stdout.write('  Alle sesjoner for kontoen er avsluttet.')
