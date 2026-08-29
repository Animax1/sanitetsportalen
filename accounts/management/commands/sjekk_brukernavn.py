"""Vis nøyaktig hva et brukernavn består av, tegn for tegn.

Finnes fordi «brukernavnet ser riktig ut, men innlogging feiler» ikke lar seg
feilsøke ved å se på det: to strenger kan være pikselidentiske på skjermen og
likevel forskjellige for databasen. De vanlige årsakene er ulik
Unicode-normalform (`å` som ett tegn eller som `a` pluss ring), usynlig
mellomrom i hver ende, eller et tegn fra feil alfabet — en kyrillisk `е` ser
ut som en latinsk `e`.

Les-only. Endrer ingenting.

    python manage.py sjekk_brukernavn                 # list alle kontoer
    python manage.py sjekk_brukernavn bjørn.rød       # og test dette oppslaget
"""
import unicodedata

from django.core.management.base import BaseCommand

from accounts.brukernavn import normaliser, oppslagsnokkel
from accounts.models import CustomUser


def _tegnvis(tekst):
    """Hver kodepunkt med navn, slik at lookalikes blir synlige."""
    biter = []
    for ch in tekst:
        if ch.isascii() and ch.isalnum():
            biter.append(ch)
        else:
            biter.append(f'[{ch} U+{ord(ch):04X} {unicodedata.name(ch, "?")}]')
    return ' '.join(biter)


class Command(BaseCommand):
    help = 'Vis brukernavn tegn for tegn, og test om et oppslag ville truffet'

    def add_arguments(self, parser):
        parser.add_argument(
            'brukernavn', nargs='?',
            help='Valgfritt: test om denne strengen ville funnet en konto')

    def handle(self, *args, **options):
        self.stdout.write('Kontoer i basen:\n')
        for bruker in CustomUser.objects.order_by('username'):
            navn = bruker.username
            merknader = []
            if normaliser(navn) != navn:
                merknader.append('IKKE NFKC-normalisert')
            if navn != navn.strip():
                merknader.append('har mellomrom i enden')
            if navn != navn.casefold():
                merknader.append('har store bokstaver')
            hale = ('   <-- ' + ', '.join(merknader)) if merknader else ''
            self.stdout.write(f'  {navn!r}{hale}')
            if not navn.isascii():
                self.stdout.write(f'      {_tegnvis(navn)}')

        sok = options.get('brukernavn')
        if not sok:
            return

        self.stdout.write(f'\nTester oppslag på {sok!r}:')
        self.stdout.write(f'  {_tegnvis(sok)}')
        self.stdout.write(f'  normalisert:   {normaliser(sok)!r}')
        self.stdout.write(f'  oppslagsnøkkel: {oppslagsnokkel(sok)!r}')

        from accounts.backends import CaseInsensitiveModelBackend
        treff = CaseInsensitiveModelBackend()._finn_kandidater(sok)

        if len(treff) == 1:
            self.stdout.write(self.style.SUCCESS(
                f'  -> Treffer kontoen {treff[0].username!r}.'))
            self.stdout.write(
                '     Feiler innlogging likevel, er det passordet eller '
                'kontolåsen (5 feil = 15 min), ikke brukernavnet.')
        elif len(treff) > 1:
            self.stdout.write(self.style.WARNING(
                f'  -> Flere kontoer matcher ({", ".join(t.username for t in treff)}). '
                'Oppslaget krever da nøyaktig treff.'))
        else:
            self.stdout.write(self.style.ERROR(
                '  -> INGEN konto matcher. Sammenlign tegnlista over med '
                'kontoens egen lenger opp.'))
