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
import socket
import time

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
        parser.add_argument(
            '--timeout', type=int, default=15, metavar='SEK',
            help='Tidsgrense for SMTP-tilkoblingen i sekunder (standard 15)',
        )

    def handle(self, *args, **valg):
        torrkjor = valg['dry_run']

        # ── 1. Oppsettet ────────────────────────────────────────────────────
        self._hvor_kjorer_vi()

        self.stdout.write(self.style.MIGRATE_HEADING('\n1. Oppsett'))

        backend = settings.EMAIL_BACKEND
        er_smtp = backend.endswith('smtp.EmailBackend')
        er_sendende = er_smtp or 'AhaSend' in backend
        self.stdout.write(f'   EMAIL_BACKEND      {backend}')
        if not er_sendende:
            self.stdout.write(self.style.WARNING(
                '   -> Denne backenden sender ingenting ut av systemet. Uten\n'
                '      AHASEND_API_KEY/AHASEND_ACCOUNT_ID eller EMAIL_HOST faller\n'
                '      Django tilbake til konsoll, og varselet havner i loggen.'
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
        self.stdout.write(self.style.MIGRATE_HEADING('\n2. Transport'))
        # HTTP-backenden har ingen forbindelse å åpne — BaseEmailBackend.open()
        # er en no-op. Å kalle den ville gitt «Åpnet og autentisert» uten at noe
        # var kontaktet, altså falsk grønt på nøyaktig det spørsmålet denne
        # kommandoen finnes for å svare på. Vi sender en ekte melding i stedet:
        # det er det eneste som prøver DNS, TLS, autentisering og om
        # avsenderdomenet er godkjent.
        if not er_sendende:
            self.stdout.write(self.style.WARNING(
                '   Hoppet over: denne backenden har ingen transport a prove. '
                'Alt "sendes" lokalt.'
            ))
            self._varslingskjede(mottakere, sendte_testmelding=False)
            return

        if not er_smtp:
            self._verifiser_http(mottakere)
            self._varslingskjede(mottakere, sendte_testmelding=True)
            return

        # Egen tidsgrense her, uavhengig av EMAIL_TIMEOUT, slik at kommandoen
        # rapporterer i stedet for å stå i ro. Uten en grense arver smtplib
        # Pythons globale socket-timeout (None), og en vert som svelger pakkene
        # i stedet for å avvise dem henger for alltid — se hendelsen 22. aug.
        # 2026 i CHANGELOG.
        tidsgrense = valg['timeout']
        self.stdout.write(
            f'   Prøver {settings.EMAIL_HOST}:{settings.EMAIL_PORT} '
            f'med {tidsgrense} s tidsgrense …'
        )
        forbindelse = get_connection(fail_silently=False, timeout=tidsgrense)
        start = time.monotonic()
        try:
            forbindelse.open()
        except (socket.timeout, TimeoutError) as exc:
            raise CommandError(
                f'Tidsavbrudd etter {time.monotonic() - start:.1f} s. Ingenting '
                f'svarte på {settings.EMAIL_HOST}:{settings.EMAIL_PORT}.\n'
                'Pakkene blir droppet, ikke avvist — det peker på en brannmur '
                'eller sperret utgående trafikk, ikke på feil legitimasjon.\n'
                'Kjører du i en container: verifiser at plattformen tillater '
                'utgående SMTP. Mange skyleverandører sperrer port 25, og noen '
                'sperrer også 587.'
            ) from exc
        except OSError as exc:
            raise CommandError(
                f'Fikk ikke kontakt: {type(exc).__name__}: {exc}\n'
                f'Sjekk at {settings.EMAIL_HOST} lar seg slå opp i DNS, og at '
                'porten er åpen utgående.'
            ) from exc
        except Exception as exc:
            raise CommandError(
                f'Kunne ikke åpne forbindelsen: {type(exc).__name__}: {exc}\n'
                'Sjekk EMAIL_HOST, EMAIL_HOST_USER og EMAIL_HOST_PASSWORD. '
                'Avvist avsenderadresse gir gjerne 550 eller 553 — da er '
                'DEFAULT_FROM_EMAIL på et domene leverandøren ikke er autorisert for.'
            ) from exc
        else:
            self.stdout.write(self.style.SUCCESS(
                f'   Åpnet og autentisert på {time.monotonic() - start:.1f} s.'
            ))
            forbindelse.close()

        self._varslingskjede(mottakere, sendte_testmelding=False)

    # ── Kontekst ─────────────────────────────────────────────────────────────

    def _hvor_kjorer_vi(self):
        """Sier hvor kommandoen kjører, fordi svaret bare gjelder der.

        Kjørt lokalt leser den `.env`; kjørt via `railway run` leser den
        Railways variabler, men fra utviklingsmaskinens nettverk; kjørt i
        containeren gjelder svaret faktisk produksjon. Forskjellen er ikke
        akademisk: 22. aug. 2026 så e-postoppsettet grønt ut i to av de tre
        tilfellene, mens containeren ikke fikk pakkene ut i det hele tatt.
        """
        import os
        import platform

        miljo = os.environ.get('RAILWAY_ENVIRONMENT_NAME')
        if miljo:
            tjeneste = os.environ.get('RAILWAY_SERVICE_NAME', '?')
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'Kjorer i Railway: miljo "{miljo}", tjeneste "{tjeneste}", '
                f'vert {platform.node()}'
            ))
            self.stdout.write(
                '   Svaret under gjelder dette miljoet. Merk at miljonavnene er '
                'arvet:\n   portalen kjorer i "staging", mens "production" er den '
                'gamle appen.'
            )
        else:
            self.stdout.write(self.style.WARNING(
                f'Kjorer lokalt paa {platform.node()} og leser .env.'
            ))
            self.stdout.write(self.style.WARNING(
                '   Svaret gjelder IKKE produksjon. Nettverket er et annet, og\n'
                '   utgaaende SMTP er sperret i containeren men ikke her.\n'
                '   For a teste produksjon: railway ssh, og kjor kommandoen der.'
            ))

    # ── Steg 2, HTTP-varianten ───────────────────────────────────────────────

    def _verifiser_http(self, mottakere):
        """Sender en ekte melding, fordi det er det eneste som beviser noe.

        For SMTP kan vi åpne forbindelsen og se at den svarer. HTTP-backenden
        har ingen slik tilstand — den bygger og sender i ett. En melding med
        ``fail_silently=False`` er derfor den eneste måten å få en høylytt feil
        på, og den prøver hele kjeden: DNS, TLS, autentisering og om
        avsenderdomenet er godkjent hos leverandøren.
        """
        from django.core.mail import EmailMessage

        self.stdout.write(f'   Backend: {settings.EMAIL_BACKEND}')
        self.stdout.write('   Sender en ekte melding for å prøve hele kjeden …')

        start = time.monotonic()
        try:
            sendt = EmailMessage(
                subject='Verifisering av e-postoppsettet',
                body=(
                    'Sendt av «manage.py verifiser_feilvarsel».\n'
                    'Dette er ikke en reell feil — kommandoen bekrefter kun at '
                    'utsending virker.'
                ),
                to=list(mottakere),
                connection=get_connection(fail_silently=False),
            ).send()
        except Exception as exc:
            raise CommandError(
                f'Utsending feilet etter {time.monotonic() - start:.1f} s:\n'
                f'{type(exc).__name__}: {exc}\n\n'
                'Vanlige årsaker:\n'
                '  · 401/403 — nøkkelen mangler «messages:send»-scope for domenet\n'
                '  · 404     — feil AHASEND_ACCOUNT_ID\n'
                '  · domenet i DEFAULT_FROM_EMAIL er ikke verifisert hos leverandøren\n'
                '  · tidsavbrudd — utgående 443 er sperret'
            ) from exc

        if not sendt:
            raise CommandError(
                'Backenden rapporterte 0 sendte meldinger uten å kaste. '
                'Se loggen for årsaken.'
            )
        self.stdout.write(self.style.SUCCESS(
            f'   Sendt og godtatt på {time.monotonic() - start:.1f} s.'
        ))

    # ── Steg 3 ───────────────────────────────────────────────────────────────

    def _varslingskjede(self, mottakere, sendte_testmelding):
        self.stdout.write(self.style.MIGRATE_HEADING('\n3. Varslingskjede'))

        logger = logging.getLogger('django.request')
        handlere = [type(h).__name__ for h in logger.handlers]
        self.stdout.write(f'   Handlere på django.request: {handlere}')
        if not any(h == 'AdminEmailHandler' for h in handlere):
            self.stdout.write(self.style.WARNING(
                '   -> AdminEmailHandler mangler. Varselet ville aldri blitt sendt, '
                'uansett hvor riktig transporten er satt opp.'
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
            '   at transporten virker.'
        )
        til = ', '.join(mottakere)
        if sendte_testmelding:
            self.stdout.write(self.style.SUCCESS(
                f'\nFerdig. Se etter to e-poster til {til}:\n'
                f'  - "Verifisering av e-postoppsettet" fra steg 2\n'
                f'  - ett feilvarsel med emne som starter pa "[Django] ERROR",\n'
                f'    der tracebacken nevner {FeilvarselTest.__name__}'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nFerdig. Se etter ett feilvarsel til {til}, med emne som\n'
                f'starter pa "[Django] ERROR" og en traceback som nevner\n'
                f'{FeilvarselTest.__name__}.'
            ))
