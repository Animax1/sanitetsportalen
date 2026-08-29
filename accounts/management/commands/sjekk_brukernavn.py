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
from django.utils import timezone

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


#: Tilstander som hver for seg stopper innlogging, med forklaringen på
#: hvorfor. Rekkefølgen er den brukeren møter dem i.
def _blokkeringer(bruker):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    funn = []
    if not bruker.is_active:
        funn.append(('Kontoen er deaktivert (is_active=False)',
                     'Aktiver den fra brukeradmin.'))
    if not bruker.has_usable_password():
        funn.append((
            'Kontoen har INGEN brukbar passord-hash',
            'Den er opprettet med invitasjon og lenken er ikke brukt ennå. '
            'Ingen passord vil virke. Sett et passord fra brukeradmin, eller '
            'send invitasjonen på nytt.'))
    if bruker.locked_until and bruker.locked_until > timezone.now():
        minutter = int(
            (bruker.locked_until - timezone.now()).total_seconds() / 60) + 1
        funn.append((f'Kontoen er LÅST i {minutter} minutt(er) til',
                     'Fem feilede forsøk låser i 15 min. Vent, eller lås opp '
                     'fra brukeradmin.'))
    if bruker.mfa_required:
        har_enhet = TOTPDevice.objects.filter(
            user=bruker, confirmed=True).exists()
        if not har_enhet:
            funn.append((
                'MFA er påkrevd, men kontoen har ingen bekreftet TOTP-enhet',
                'Innlogging går da til MFA-oppsett i stedet for til portalen — '
                'det kan se ut som at den «ikke slipper inn».'))
    return funn


class Command(BaseCommand):
    help = 'Vis brukernavn tegn for tegn, og test om et oppslag ville truffet'

    def add_arguments(self, parser):
        parser.add_argument(
            'brukernavn', nargs='?',
            help=('Valgfritt: test om denne strengen ville funnet en konto. '
                  'Godtar \\uXXXX-rømming for kanaler uten norske tegn.'))

    def _skriv_tilstand(self, bruker):
        """Kontoens tilstand — det som stopper innlogging når navnet stemmer."""
        self.stdout.write('\n  Kontotilstand:')
        self.stdout.write(f'    aktiv:                 {bruker.is_active}')
        self.stdout.write(f'    brukbart passord:      {bruker.has_usable_password()}')
        self.stdout.write(f'    må bytte passord:      {bruker.must_change_password}')
        self.stdout.write(f'    MFA påkrevd:           {bruker.mfa_required}')
        self.stdout.write(f'    delt konto:            {bruker.er_delt_konto}')
        self.stdout.write(f'    feilede forsøk:        {bruker.failed_login_attempts}')
        self.stdout.write(f'    låst til:              {bruker.locked_until or "—"}')
        self.stdout.write(f'    sist innlogget:        {bruker.last_login_at or "aldri"}')

        if bruker.must_change_password:
            self.stdout.write(self.style.WARNING(
                '\n  MERK: kontoen må bytte passord.'))
            self.stdout.write(
                '  Innlogging lykkes, men middlewaren sender deg rett til\n'
                '  /accounts/change-password/ i stedet for til portalen. Utenfra\n'
                '  kan det se ut som at du «ikke kommer inn». Fullfør byttet, så\n'
                '  forsvinner omdirigeringen.')
            if bruker.last_login_at:
                self.stdout.write(
                    f'  Kontoen logget sist inn {bruker.last_login_at} og har\n'
                    '  fortsatt flagget satt — byttet ble altså ikke fullført.')

        blokkeringer = _blokkeringer(bruker)
        if not blokkeringer:
            self.stdout.write(self.style.SUCCESS(
                '\n  Ingenting i kontotilstanden stopper innlogging.'))
            self.stdout.write(
                '  Da står passordet igjen. Merk at et passord med «å» kan '
                'feile\n  om det ble satt i én Unicode-normalform og skrives i '
                'en annen —\n  Django normaliserer ikke passord. «æ» og «ø» '
                'rammes ikke.')
            return

        self.stdout.write(self.style.ERROR('\n  Dette stopper innlogging:'))
        for hva, hvorfor in blokkeringer:
            self.stdout.write(self.style.ERROR(f'    * {hva}'))
            self.stdout.write(f'      {hvorfor}')

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

        from accounts.backends import finn_kandidater
        treff = finn_kandidater(sok)

        if len(treff) == 1:
            self.stdout.write(self.style.SUCCESS(
                f'  -> Treffer kontoen {treff[0].username!r}. '
                'Brukernavnet er altså ikke feilen.'))
            self._skriv_tilstand(treff[0])
        elif len(treff) > 1:
            self.stdout.write(self.style.WARNING(
                f'  -> Flere kontoer matcher ({", ".join(t.username for t in treff)}). '
                'Oppslaget krever da nøyaktig treff.'))
        else:
            self.stdout.write(self.style.ERROR(
                '  -> INGEN konto matcher. Sammenlign tegnlista over med '
                'kontoens egen lenger opp.'))
