r"""Nullstill MFA for én konto, uten å gå veien om grensesnittet.

Finnes for tilfellet der ingen kommer inn: telefonen med autentiseringsappen er
borte, reservekodene er borte, og det er ingen annen administrator som kan
trykke «Nullstill MFA» (28. sep. 2026). Uten den var eneste vei direkte SQL mot
produksjonsbasen.

    railway ssh --service web -- python manage.py nullstill_mfa <brukernavn> --ja

**Railway-innloggingen er vakta.** Den som når kommandoen, har allerede
tilgang til databasen og miljøvariablene; kommandoen gir ingen tilgang som
ikke fantes. Derfor er det ingen ekstra sperre her — men Railway- og
GitHub-kontoene må ha 2FA, fordi de er nøkkelen til portalen.

Kommandoen gjør **nøyaktig** det knappen i brukeradministrasjonen gjør — samme
funksjon, `accounts.mfa.nullstill_mfa`: enhetene og reservekodene slettes,
`mfa_required` settes, alle sesjoner avsluttes, og det skrives én rad i
innloggingsloggen og én i auditloggen med kilden «fra kommandolinja».

`--ja` er nødvendig av samme grunn som i `gjenopprett`: `railway ssh` har ingen
terminal, så et spørsmål ville hengt. Det finnes ingen `--alle` — én navngitt
konto om gangen. Brukernavnet slås opp som i `sett_passord`, og godtar
`\uXXXX`-rømming.
"""
from django.core.management.base import BaseCommand, CommandError

from accounts import mfa
from accounts.backends import finn_kandidater


class Command(BaseCommand):
    help = 'Nullstill MFA for én konto: slett enhetene og krev nytt oppsett ved neste innlogging'

    def add_arguments(self, parser):
        parser.add_argument('brukernavn', help=r'Godtar \uXXXX-rømming, f.eks. andré')
        parser.add_argument(
            '--ja', action='store_true',
            help='Bekreft. Påkrevd — railway ssh har ingen terminal å spørre i.')

    def handle(self, *args, **options):
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

        if not options['ja']:
            raise CommandError(
                f'Dette sletter MFA-enhetene og reservekodene til {bruker.username!r} '
                'og logger kontoen ut overalt. Kjør på nytt med --ja for å bekrefte.')

        mfa.nullstill_mfa(bruker, kilde='fra kommandolinja (nullstill_mfa)')

        self.stdout.write(self.style.SUCCESS(f'MFA nullstilt for {bruker.username!r}.'))
        self.stdout.write('  Enhetene og reservekodene er slettet, og alle sesjoner er avsluttet.')
        self.stdout.write('  Ved neste innlogging settes MFA opp på nytt med en ny QR-kode.')
