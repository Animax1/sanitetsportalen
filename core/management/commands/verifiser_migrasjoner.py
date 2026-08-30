"""Kjør migrasjonsprøvene mot en ekte PostgreSQL, med rader i basen.

    python manage.py verifiser_migrasjoner --url postgres://.../postgres

**Kommandoen rører aldri en base som finnes.** Den kobler seg til serveren i
URL-en, lager sin egen engangsbase, kjører prøven der, og sletter den igjen.
Uten den regelen ville verktøyet som skal fange en migrasjonsfeil selv kunne
rulle produksjon bakover — og det er en verre feil enn den det leter etter.

Se `core/migrasjonsprover.py` for hvorfor dette ikke er det samme som å kjøre
testsuiten mot PostgreSQL: testbasen er tom, og en tom base skjuler nettopp
denne feilklassen.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

from django.core.management.base import BaseCommand, CommandError

from core.migrasjonsprover import PROVER

#: Miljøvariabelen testen og kommandoen deler. Peker på en PostgreSQL-server
#: (hvilken base som helst — kommandoen lager sin egen).
ENV_URL = 'MIGRASJONSPROVE_DATABASE_URL'


def server_url() -> str | None:
    return os.environ.get(ENV_URL) or None


def _med_base(url: str, navn: str) -> str:
    """Samme server-URL, men mot en annen base."""
    delt = urlsplit(url)
    return urlunsplit(delt._replace(path=f'/{navn}'))


class Command(BaseCommand):
    help = ('Kjører migrasjonsprøvene mot PostgreSQL med rader i basen. '
            f'Krever --url eller {ENV_URL}.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--url', default=None,
            help=f'PostgreSQL-server å prøve mot. Default: ${ENV_URL}.')
        parser.add_argument(
            '--prove', default=None,
            help='Kjør bare denne prøven (nøkkelen i PROVER).')

    def handle(self, *args, **valg):
        url = valg['url'] or server_url()
        if not url:
            raise CommandError(
                f'Ingen PostgreSQL å prøve mot. Sett {ENV_URL} eller gi --url.\n'
                f'Prøvene finnes bare for PostgreSQL — SQLite har ingen utsatte '
                f'triggere, og kan derfor ikke vise feilen de leter etter.')

        import dj_database_url
        grunn = dj_database_url.parse(url)
        if 'postgresql' not in grunn['ENGINE']:
            raise CommandError(f'--url må peke på PostgreSQL, ikke {grunn["ENGINE"]}.')

        prover = list(PROVER.values())
        if valg['prove']:
            if valg['prove'] not in PROVER:
                raise CommandError(f'Ukjent prøve: {valg["prove"]}')
            prover = [PROVER[valg['prove']]]

        feilet = []
        for prove in prover:
            self.stdout.write(f'{prove.migrasjon} — {prove.beskrivelse}')
            try:
                self._kjor(url, grunn, prove)
            except Exception as feil:                       # noqa: BLE001
                feilet.append(prove.migrasjon)
                self.stdout.write(self.style.ERROR(
                    f'  FEIL: {type(feil).__name__}: {feil}'))
            else:
                self.stdout.write(self.style.SUCCESS('  OK'))

        if feilet:
            raise CommandError(
                f'{len(feilet)} av {len(prover)} prøver feilet: '
                f'{", ".join(feilet)}. Migrasjonen ville tatt ned deployen.')
        self.stdout.write(self.style.SUCCESS(
            f'{len(prover)} prøve(r) gikk gjennom.'))

    # ── Selve kjøringen ──────────────────────────────────────────────────

    def _kjor(self, url, grunn, prove):
        # Navnet er tilfeldig med vilje: to samtidige kjøringer skal ikke
        # kunne slette hverandres base.
        navn = f'migrasjonsprove_{uuid.uuid4().hex[:12]}'
        self._lag_base(grunn, navn)
        try:
            base_url = _med_base(url, navn)

            # Fram til migrasjonen FØR den som prøves. Aldri bakover fra
            # siste: en migrasjon uten reverse ville stoppet prøven, og
            # basen er uansett fersk.
            self._migrate(base_url, prove.app, prove.foregaaende)

            with self._kobling(grunn, navn) as kobling:
                with kobling.cursor() as c:
                    prove.seed(c)
                kobling.commit()

            self._migrate(base_url, prove.app)

            with self._kobling(grunn, navn) as kobling:
                with kobling.cursor() as c:
                    prove.sjekk(c)
        finally:
            self._slett_base(grunn, navn)

    @staticmethod
    def _migrate(base_url, app, maal=None):
        """Kjør `migrate` i en **underprosess** med basen som `default`.

        Ikke som et andre databasealias i denne prosessen, og det er et
        bevisst valg: atten av migrasjonene i dette prosjektet gjør ORM-kall
        i `RunPython` uten `schema_editor.connection.alias`, altså mot
        `default`. Med et alias ville de skrevet til utviklerens egen base i
        stedet for prøvebasen — og prøven ville målt noe annet enn det den
        later som.

        Underprosessen kjører dessuten nøyaktig den stien release-fasen
        kjører: `manage.py migrate` mot `default`, én base, ingen router.
        """
        kommando = [sys.executable, 'manage.py', 'migrate', app]
        if maal:
            kommando.append(maal)
        kommando += ['--noinput', '-v', '0']

        miljo = dict(os.environ, DATABASE_URL=base_url)
        res = subprocess.run(kommando, env=miljo, capture_output=True, text=True)
        if res.returncode != 0:
            hale = (res.stderr or res.stdout or '').strip().splitlines()
            raise RuntimeError(
                f'migrate {app} {maal or ""} feilet:\n  '
                + '\n  '.join(hale[-12:]))

    @staticmethod
    def _kobling(grunn, navn='postgres'):
        """psycopg2-kobling til en base på samme server.

        `OPTIONS` må med: for en URL som peker på en unix-socket legger
        `dj_database_url` `host`/`port` der og lar `HOST` stå tom. Leser man
        bare `HOST`, treffer man standardsocketen — en helt annen server enn
        den man ba om.
        """
        import psycopg2
        return psycopg2.connect(
            dbname=navn,
            **{**dict(grunn.get('OPTIONS') or {}),
               **{n: v for n, v in (
                   ('user', grunn.get('USER')),
                   ('password', grunn.get('PASSWORD')),
                   ('host', grunn.get('HOST')),
                   ('port', grunn.get('PORT')),
               ) if v}},
        )

    def _lag_base(self, grunn, navn):
        # CREATE/DROP DATABASE kan ikke kjøre mot basen man står i, og må stå
        # utenfor en transaksjon.
        kobling = self._kobling(grunn)
        kobling.autocommit = True
        try:
            with kobling.cursor() as c:
                c.execute(f'CREATE DATABASE "{navn}"')
        finally:
            kobling.close()

    def _slett_base(self, grunn, navn):
        kobling = self._kobling(grunn)
        kobling.autocommit = True
        try:
            with kobling.cursor() as c:
                c.execute(f'DROP DATABASE IF EXISTS "{navn}" WITH (FORCE)')
        finally:
            kobling.close()
