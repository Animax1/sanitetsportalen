"""Management-kommando som verifiserer at databasetilkoblingen bruker TLS/SSL.

Skrives til stdout slik at den vises i Railway sine deploy-logger eller kan
kjøres manuelt via `python manage.py check_ssl`. Brukes som GDPR-dokumentasjon
for å bevise at tilkoblingen til Postgres er kryptert i transitt.
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Verifiser at databasetilkoblingen bruker TLS/SSL. Skriver status til stdout.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-insecure',
            action='store_true',
            help='Avslutt med exit-kode 1 hvis tilkoblingen ikke er kryptert.',
        )

    def handle(self, *args, **options):
        vendor = connection.vendor  # 'postgresql', 'sqlite', ...

        if vendor == 'sqlite':
            self.stdout.write(
                self.style.WARNING(
                    '[SSL-sjekk] SQLite er i bruk (lokal fil). '
                    'TLS er ikke relevant – ingen nettverkstilkobling. '
                    'Datasikkerhet avhenger av filsystem-tilganger.'
                )
            )
            return

        if vendor != 'postgresql':
            self.stdout.write(
                self.style.WARNING(
                    f'[SSL-sjekk] Ukjent database-vendor: {vendor}. Hopper over SSL-sjekk.'
                )
            )
            return

        try:
            with connection.cursor() as cur:
                # Postgres: SHOW ssl returnerer 'on' hvis SSL er aktivert på serveren
                cur.execute('SHOW ssl')
                ssl_setting = cur.fetchone()[0]

                # pg_stat_ssl viser om den gjeldende tilkoblingen faktisk bruker SSL
                cur.execute(
                    'SELECT ssl, version, cipher '
                    'FROM pg_stat_ssl WHERE pid = pg_backend_pid()'
                )
                row = cur.fetchone()
                if row is None:
                    self.stdout.write(
                        self.style.WARNING(
                            '[SSL-sjekk] Kunne ikke hente pg_stat_ssl – '
                            'usikker på om tilkoblingen er kryptert.'
                        )
                    )
                    if options['fail_on_insecure']:
                        raise SystemExit(1)
                    return

                ssl_active, tls_version, cipher = row

            self.stdout.write(f'[SSL-sjekk] Database: PostgreSQL')
            self.stdout.write(f'[SSL-sjekk] Server-innstilling (SHOW ssl): {ssl_setting}')
            self.stdout.write(f'[SSL-sjekk] Tilkobling kryptert: {ssl_active}')
            self.stdout.write(f'[SSL-sjekk] TLS-versjon: {tls_version or "N/A"}')
            self.stdout.write(f'[SSL-sjekk] Cipher: {cipher or "N/A"}')

            if ssl_active:
                self.stdout.write(
                    self.style.SUCCESS(
                        '[SSL-sjekk] OK – databasetilkoblingen er kryptert i transitt.'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        '[SSL-sjekk] ADVARSEL – tilkoblingen er IKKE kryptert.'
                    )
                )
                if options['fail_on_insecure']:
                    raise SystemExit(1)

        except Exception as exc:  # pragma: no cover – defensive
            self.stdout.write(
                self.style.ERROR(f'[SSL-sjekk] Feil under SSL-verifisering: {exc}')
            )
            if options['fail_on_insecure']:
                raise SystemExit(1)
