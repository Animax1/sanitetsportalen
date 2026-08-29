r"""Vis nøyaktig hva et brukernavn består av, tegn for tegn.

Finnes fordi «brukernavnet ser riktig ut, men innlogging feiler» ikke lar seg
feilsøke ved å se på det: to strenger kan være pikselidentiske på skjermen og
likevel forskjellige for databasen. De vanlige årsakene er ulik
Unicode-normalform (`å` som ett tegn eller som `a` pluss ring), usynlig
mellomrom i hver ende, eller et tegn fra feil alfabet — en kyrillisk `е` ser
ut som en latinsk `e`.

**Kommandolinja kan ikke alltid bære norske tegn.** Railways `ssh` og en del
andre kanaler mangler eller forvrenger `æøå` på vei inn. Derfor:

* **Uten argument lister den alle kontoer** med tegnoppdeling. Det er nok til
  å se hva som faktisk står lagret — man trenger ikke skrive navnet selv.
* **Argumentet godtar `\uXXXX`-rømming**, så `bj\u00f8rn.r\u00f8d` er
  likeverdig med `bjørn.rød`. Utskriften viser hvert navn i samme form, slik
  at det kan limes rett tilbake gjennom en kanal som ikke tåler `ø`.

Les-only. Endrer ingenting.

    python manage.py sjekk_brukernavn                        # list alle kontoer
    python manage.py sjekk_brukernavn bjørn.rød              # test et oppslag
    python manage.py sjekk_brukernavn 'bj\u00f8rn.r\u00f8d'  # samme, ren ASCII
"""
import re
import unicodedata

from django.core.management.base import BaseCommand

from accounts.brukernavn import normaliser, oppslagsnokkel
from accounts.models import CustomUser


def _ascii_form(tekst):
    r"""Navnet som ren ASCII med `\uXXXX` for alt annet.

    Finnes for at utskriften skal kunne limes tilbake inn i kommandoen gjennom
    en kanal som ikke bærer norske tegn — nettopp den som gjorde denne
    kommandoen vanskelig å bruke i utgangspunktet.
    """
    # Alltid `\uXXXX`, aldri `\xXX`. Pythons egen `backslashreplace` bruker
    # `\xf8` for tegn under U+0100, og den formen tolkes ikke av
    # `_tolk_rommet` — utskriften ville da ikke kunne limes tilbake inn i
    # kommandoen, som er hele grunnen til at den finnes.
    biter = []
    for ch in tekst:
        if ch.isascii():
            biter.append(ch)
        elif ord(ch) > 0xFFFF:
            biter.append(f'\\U{ord(ch):08x}')
        else:
            biter.append(f'\\u{ord(ch):04x}')
    return ''.join(biter)


def _tolk_rommet(tekst):
    r"""Gjør `\u00f8` om til `ø`. Lar alt annet stå.

    Bare `\uXXXX` tolkes, ikke hele `unicode_escape`-settet: sistnevnte ville
    også tolket `\t` og `\n`, og et brukernavn med bakstrek er mindre rart
    enn et brukernavn med tabulator.
    """
    return re.sub(
        r'\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})',
        lambda m: chr(int(m.group(1) or m.group(2), 16)),
        tekst,
    )


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
            help=('Valgfritt: test om denne strengen ville funnet en konto. '
                  'Godtar \\uXXXX-rømming for kanaler uten norske tegn.'))

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
                self.stdout.write(f'      tegn:  {_tegnvis(navn)}')
                self.stdout.write(f'      ascii: {_ascii_form(navn)}')

        sok = options.get('brukernavn')
        if not sok:
            self.stdout.write(
                '\nTips: kjør med et brukernavn som argument for å teste et '
                'oppslag.\n     Tåler ikke kanalen norske tegn, bruk '
                'ascii-formen over (\\u00f8 for ø).')
            return

        sok = _tolk_rommet(sok)
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
