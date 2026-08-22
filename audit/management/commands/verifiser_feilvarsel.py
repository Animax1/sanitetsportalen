"""Verifiserer at e-postvarselet ved uhåndterte feil faktisk når fram.

Kjøres som:
  python manage.py verifiser_feilvarsel              # full sjekk, sender e-post
  python manage.py verifiser_feilvarsel --dry-run    # sjekk oppsettet, send ingenting

**Hvorfor denne kommandoen finnes.** Varslingsstien er stille når den er ødelagt.
Djangos ``AdminEmailHandler`` kaller ``mail_admins(..., fail_silently=True)``, og
en loggehandler som feiler river aldri ned requesten som utløste den — det er
riktig oppførsel, men det betyr at feil SMTP-oppsett ser nøyaktig ut som et
system uten feil. Det samme gjelder tom ``ADMINS``: da har varselet ingen
mottakere, og ingenting protesterer.

Kommandoen skiller derfor de tre tingene som kan svikte, og sier hvilken det er:

1. **Oppsettet** — er backenden SMTP, har ``ADMINS`` mottakere, er avsenderen satt?
2. **SMTP-forbindelsen** — åpnes eksplisitt med ``fail_silently=False``, slik at
   feil legitimasjon eller avvist avsenderadresse gir et unntak i stedet for
   stillhet.
3. **Varslingskjeden** — en ekte exception logges til ``django.request`` med
   ``exc_info`` og et syntetisk request-objekt, altså nøyaktig slik Django gjør
   det ved en uhåndtert feil i et view. Det kjører gjennom dempingsfilteret og
   ``AdminEmailHandler``.

Steg 2 er det som gir høylytt feilmelding. Steg 3 beviser at kjeden er koblet,
men kan ikke rapportere leveranse — handleren svelger som nevnt sine egne feil.
Derfor kjøres begge: steg 2 utelukker at steg 3 feiler stille.

Kommandoen skriver ingenting til databasen.
"""
import logging

from django.conf import settings
from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

EMNE = 'Verifisering av feilvarsling'


class FeilvarselTest(Exception):
    """Reist med vilje for å få en ekte traceback inn i varselet."""


class Command(BaseCommand):
    help = 'Verifiser at e-postvarsel ved uhåndterte feil når fram'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Kontroller oppsettet uten å sende e-post',
        )

    def handle(self, *args, **valg):
        torrkjor = valg['dry_run']

        # ── 1. Oppsettet ────────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('1. Oppsett'))

        backend = settings.EMAIL_BACKEND
        er_smtp = backend.endswith('smtp.EmailBackend')
        self.stdout.write(f'   EMAIL_BACKEND      {backend}')
        if not er_smtp:
            self.stdout.write(self.style.WARNING(
                '   ↳ Ikke SMTP. Uten EMAIL_HOST faller Django tilbake til konsoll,\n'
                '     og varselet skrives til loggen i stedet for å sendes.'
            ))

        mottakere = [e for _, e in settings.ADMINS]
        self.stdout.write(f'   ADMINS             {mottakere or "(tom)"}')
        if not mottakere:
            raise CommandError(
                'ADMINS er tom — varselet ville hatt null mottakere, uten at noe '
                'protesterer. Formatet er "Navn:epost", komma-separert.'
            )

        self.stdout.write(f'   DEFAULT_FROM_EMAIL {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'   SERVER_EMAIL       {settings.SERVER_EMAIL}')
        if er_smtp:
            self.stdout.write(
                f'   SMTP               {settings.EMAIL_HOST}:{settings.EMAIL_PORT} '
                f'(TLS={settings.EMAIL_USE_TLS})'
            )

        if torrkjor:
            self.stdout.write(self.style.SUCCESS(
                '\nTørrkjøring: oppsettet ser riktig ut. Kjør uten --dry-run for '
                'å teste forbindelsen og selve varslingskjeden.'
            ))
            return

        # ── 2. SMTP-forbindelsen ────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n2. SMTP-forbindelse'))
        forbindelse = get_connection(fail_silently=False)
        try:
            forbindelse.open()
        except Exception as exc:
            raise CommandError(
                f'Kunne ikke åpne forbindelsen: {type(exc).__name__}: {exc}\n'
                'Sjekk EMAIL_HOST, EMAIL_HOST_USER og EMAIL_HOST_PASSWORD. '
                'Avvist avsenderadresse gir gjerne 550 eller 553 — da er '
                'DEFAULT_FROM_EMAIL på et domene leverandøren ikke er autorisert for.'
            ) from exc
        else:
            self.stdout.write(self.style.SUCCESS('   Åpnet og autentisert.'))
            forbindelse.close()

        # ── 3. Varslingskjeden ──────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('\n3. Varslingskjede'))

        logger = logging.getLogger('django.request')
        handlere = [type(h).__name__ for h in logger.handlers]
        self.stdout.write(f'   Handlere på django.request: {handlere}')
        if not any(h == 'AdminEmailHandler' for h in handlere):
            self.stdout.write(self.style.WARNING(
                '   ↳ AdminEmailHandler mangler. Varselet ville aldri blitt sendt, '
                'uansett hvor riktig SMTP-oppsettet er.'
            ))

        request = RequestFactory().get('/verifiser-feilvarsel/')
        try:
            raise FeilvarselTest(
                'Reist med vilje av «manage.py verifiser_feilvarsel». '
                'Dette er ikke en reell feil.'
            )
        except FeilvarselTest:
            logger.error(
                'Verifisering av feilvarsling — ikke en reell feil',
                exc_info=True,
                extra={'status_code': 500, 'request': request},
            )

        self.stdout.write(self.style.SUCCESS(
            '   Logget en ekte exception til django.request med exc_info.'
        ))
        self.stdout.write(
            '   Merk: AdminEmailHandler bruker fail_silently=True, så den kan\n'
            '   ikke rapportere om utsendingen lyktes. Steg 2 er det som viser\n'
            '   at forbindelsen virker.'
        )
        self.stdout.write(self.style.SUCCESS(
            f'\nFerdig. Se etter to e-poster til {", ".join(mottakere)}:\n'
            f'  · én fra dempingsfilteret/handleren med emne som starter på "[Django] ERROR"\n'
            f'  · tracebacken skal nevne {FeilvarselTest.__name__}'
        ))
