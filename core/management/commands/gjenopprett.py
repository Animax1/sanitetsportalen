"""Gjenopprett en backup fra kommandolinja (13. sep. 2026).

    python manage.py gjenopprett --list                  # filene på volumet
    python manage.py gjenopprett --siste vaktliste       # nyeste fil for modulen
    python manage.py gjenopprett <filnavn>
    python manage.py gjenopprett <filnavn> --ja          # uten spørsmål
    python manage.py gjenopprett --siste full --full --ja
    python manage.py gjenopprett --hent <objekt> --ja    # fra Scaleway i ett

**Denne veien fantes ikke før.** `hent_offsite` henter og dekrypterer fila, men
rører ikke databasen — siste linje den skriver er «gjenopprett fra
/portal-admin/backup/». Og i en tom base, som er akkurat der man er når man
trenger den, finnes det ingen å logge inn som. Katastrofeveien gikk altså
gjennom en nettleser som ikke hadde noen bruker.

Samme funksjon som knappen kaller: samme pre-restore-øyeblikksbilde, samme
auditrad. Det skal ikke finnes to oppførsler å feilsøke.

## Om `--ja`

`railway ssh --service web -- python manage.py …` kjører **uten interaktiv
terminal**. Et `input()` ville hengt til noe ga opp, uten at det sto hvorfor.
Kommandoen krever derfor `--ja` når den ikke har et tastatur å spørre fra, og
sier det med rene ord i stedet for å vente.

## Om `--full`

Slugen leses av filnavnet, så flagget er teknisk overflødig. Det kreves likevel
for den hele basen: den erstatter brukere, passord og MFA, og skal ikke kunne
startes av en skrivefeil i et filnavn.
"""
from __future__ import annotations

import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.kommando import lesbar_dbfeil


class Command(BaseCommand):
    help = 'Gjenopprett en backup fra fil, eller hent den fra Scaleway først.'

    def add_arguments(self, parser):
        parser.add_argument('filnavn', nargs='?',
                            help='Fil i BACKUP_DIR, som i --list.')
        parser.add_argument('--list', action='store_true',
                            help='List filene på volumet og avslutt.')
        parser.add_argument('--siste', metavar='SLUG',
                            help='Bruk den nyeste fila for denne modulen.')
        parser.add_argument('--hent', metavar='OBJEKT',
                            help='Hent fra Scaleway først, gjenopprett så.')
        parser.add_argument('--full', action='store_true',
                            help='Bekreft at dette er hele databasen.')
        parser.add_argument('--ja', action='store_true',
                            help='Ikke spør. Nødvendig under `railway ssh`.')

    def handle(self, *args, **valg):
        with lesbar_dbfeil('ingenting ble gjenopprettet'):
            self._kjor(valg)

    # ── Underkommandoer ──────────────────────────────────────────────────────

    def _kjor(self, valg):
        if valg['list']:
            self._list()
            return

        backup = self._finn_backup(valg)
        self._bekreft(backup, valg)
        self._gjenopprett(backup)

    def _list(self):
        from core.backup import get_backup_dir, slug_fra_filnavn

        filer = sorted(get_backup_dir().glob('backup-*.json.gz'),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        if not filer:
            self.stdout.write('Ingen backupfiler på volumet. '
                              'Hent en fra Scaleway med `hent_offsite --list`.')
            return
        self.stdout.write(f'{"Modul":<16}{"Størrelse":>11}  {"Endret":<17}Filnavn')
        for f in filer:
            import datetime
            endret = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            self.stdout.write(
                f'{slug_fra_filnavn(f.name) or "?":<16}'
                f'{f.stat().st_size:>11}  {endret:%d.%m.%Y %H:%M}  {f.name}')
        self.stdout.write(f'\n{len(filer)} fil(er) i {get_backup_dir()}.')

    def _finn_backup(self, valg):
        """Backup-raden som skal gjenopprettes, uansett hvordan den ble pekt ut."""
        from core.backup import get_backup_dir, get_handler, slug_fra_filnavn
        from core.models import Backup

        if valg['hent']:
            from core import offsite
            if not offsite.er_konfigurert():
                raise CommandError(
                    'Offsite er ikke konfigurert. Mangler: '
                    + ', '.join(offsite.mangler()))
            try:
                backup, sti = offsite.hent(valg['hent'])
            except ValueError as feil:
                raise CommandError(str(feil)) from feil
            except Exception as feil:   # noqa: BLE001 — boto-feil skal leses
                raise CommandError(
                    f'Henting feilet: {feil.__class__.__name__}: {feil}') from feil
            self.stdout.write(f'Hentet og dekryptert {backup.filename} → {sti}')
            return backup

        if valg['siste']:
            slug = valg['siste']
            if get_handler(slug) is None:
                raise CommandError(f'Ingen backup-handler for «{slug}».')
            # Pre-restore-øyeblikksbildene er kopier av tilstanden *før* en
            # tidligere gjenoppretting. Å tilby dem som «siste» ville gitt
            # akkurat den tilstanden man nettopp gikk bort fra.
            treff = sorted(
                (f for f in get_backup_dir().glob(f'backup-{slug}-*.json.gz')
                 if slug_fra_filnavn(f.name) == slug and 'pre_restore' not in f.name),
                key=lambda f: f.stat().st_mtime)
            if not treff:
                raise CommandError(
                    f'Ingen fil for «{slug}» på volumet. '
                    f'Hent en med `hent_offsite --list`.')
            filnavn = treff[-1].name
        elif valg['filnavn']:
            filnavn = Path(valg['filnavn']).name
        else:
            raise CommandError(
                'Oppgi et filnavn, --siste <modul>, --hent <objekt> eller --list.')

        sti = get_backup_dir() / filnavn
        if not sti.exists():
            raise CommandError(f'Fant ikke {sti}. Se `gjenopprett --list`.')

        slug = slug_fra_filnavn(filnavn)
        if get_handler(slug) is None:
            raise CommandError(
                f'Filnavnet peker på modulen «{slug}», som ikke har en '
                f'registrert backup-handler.')

        # Fila kan ligge på volumet uten en rad — den er kopiert inn, eller
        # basen er ny. Raden er det `restore_backup` arbeider med.
        backup, _ = Backup.objects.get_or_create(
            filename=filnavn,
            defaults={'kind': 'manual', 'size_bytes': sti.stat().st_size,
                      'module_slug': slug,
                      'note': 'Registrert av `gjenopprett`'})
        return backup

    # ── Bekreftelse ──────────────────────────────────────────────────────────

    def _bekreft(self, backup, valg):
        from core.backup import get_handler
        from core.models import Backupplan

        handler = get_handler(backup.module_slug)
        navn = handler.display_name or backup.module_slug
        hel = backup.module_slug == Backupplan.FULL_SLUG

        if hel and not valg['full']:
            raise CommandError(
                f'{backup.filename} er en backup av HELE databasen — brukere, '
                f'passord, MFA og alle modulenes data erstattes. Gjenta med '
                f'--full for å bekrefte at det er det du vil.')

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'  Modul:   {navn} ({backup.module_slug})'))
        self.stdout.write(self.style.WARNING(f'  Fil:     {backup.filename}'))
        for rad in self._berorte(handler):
            self.stdout.write(f'           {rad}')
        self.stdout.write('')

        if valg['ja']:
            return

        if not sys.stdin.isatty():
            # `railway ssh -- <kommando>` har ingen terminal. Uten denne
            # sjekken ville `input()` hengt til noe ga opp, uten at det sto
            # hvorfor — og det er i en katastrofe man kjører dette.
            raise CommandError(
                'Ingen interaktiv terminal, så jeg kan ikke spørre. Legg til '
                '--ja for å bekrefte. (Det er normalt under `railway ssh`.)')

        svar = input(f'Skriv «{backup.module_slug}» for å gjenopprette: ').strip()
        if svar != backup.module_slug:
            raise CommandError('Avbrutt — bekreftelsen stemte ikke.')

    def _berorte(self, handler) -> list[str]:
        """«Dette slettes og erstattes», som i grensesnittet."""
        from django.apps import apps as django_apps

        ut, sum_rader = [], 0
        for etikett in handler.get_restore_models():
            try:
                antall = django_apps.get_model(etikett).objects.count()
            except Exception:   # noqa: BLE001
                continue
            sum_rader += antall
            if antall:
                ut.append(f'{etikett}: {antall}')
        if not ut:
            return ['Basen er tom — ingenting slettes.']
        tabeller = f'{len(ut)} tabell' + ('' if len(ut) == 1 else 'er')
        rader = f'{sum_rader} rad' + ('' if sum_rader == 1 else 'er')
        return [f'Slettes og erstattes: {rader} i {tabeller}'] + \
               [f'  {rad}' for rad in ut[:12]] + \
               ([f'  … og {len(ut) - 12} til'] if len(ut) > 12 else [])

    # ── Selve gjenopprettingen ───────────────────────────────────────────────

    def _gjenopprett(self, backup):
        from core.backup import restore_backup

        try:
            restore_backup(backup, user=None, kilde='kommandolinja')
        except Exception as feil:   # noqa: BLE001 — én lesbar linje, ikke en traceback
            raise CommandError(
                f'Gjenopprettingen feilet og ble rullet tilbake: '
                f'{feil.__class__.__name__}: {feil}') from feil

        self.stdout.write(self.style.SUCCESS(
            f'Gjenopprettet {backup.module_slug} fra {backup.filename}. '
            f'Et pre-restore-øyeblikksbilde ble tatt først.'))
        if backup.module_slug == 'full':
            self.stdout.write(
                'Alle må logge inn på nytt med passordene som gjaldt da '
                'backupen ble tatt.')
