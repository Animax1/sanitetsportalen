"""Last backupfilene inn i en engangsbase og tell radene (13. sep. 2026).

    python manage.py verifiser_backup            # modulfilene, i rekkefølge
    python manage.py verifiser_backup --full     # den hele fila alene
    python manage.py verifiser_backup --modul oppdrag
    python manage.py verifiser_backup --behold   # ikke rydd, si hvor basen ligger

**En backup ingen har gjenopprettet er en hypotese.** Suiten har en test som
gjør det samme med syntetiske data (`AlleFileneGjenopprettesTests`), og den
fanger at *koden* virker. Denne kommandoen gjør det med **filene som faktisk
ligger på volumet i prod**, og fanger at *innholdet* virker: at fila lar seg
pakke ut, at den laster, og at radene som var i den kommer tilbake.

Den rører ingenting. Alt skjer i en engangs-SQLite-fil i en midlertidig mappe,
og både den og mappa slettes når kommandoen er ferdig. Backupfilene kopieres
dit før de brukes, så pre-restore-øyeblikksbildene gjenopprettingen lager havner
i søpla og ikke i `BACKUP_DIR`.

## Hvorfor SQLite og ikke PostgreSQL

Fordi kommandoen skal kunne kjøres **der filene er**, altså i prod-containeren,
uten at det finnes en ekstra databaseserver og uten å lage og slette baser ved
siden av produksjonsdata. Spørsmålet den svarer på er «lastes filene, og kommer
radene tilbake» — ikke «oppfører PostgreSQL seg likt», som suiten dekker ved å
kjøre `AlleFileneGjenopprettesTests` mot ekte PostgreSQL. Django slår på
fremmednøkkelsjekk i SQLite, så en feil slettelista eller et brutt
fremmednøkkelforhold slår ut her også.

## Hvorfor den kaller `gjenopprett` og ikke `restore_backup`

Den kjører nøyaktig den kommandoen man ville kjørt i en katastrofe. Da er det
den veien som er prøvd, ikke en nabo til den.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

#: Bindende: alt peker på vakta, og `portal` bærer den.
REKKEFOLGE = ['portal', 'patients', 'arkiv', 'oppdrag', 'oppdrag_arkiv',
              'vaktliste']

#: Modeller gjenopprettingen **selv** skriver til etter at fila er lastet.
#:
#: `restore_backup` legger én auditrad om at gjenopprettingen skjedde — og i
#: den hele fila er `audit.AuditLog` med i slettelista, så den tømmes, lastes,
#: og får så den ene raden på toppen. Basen skal altså ha én rad *mer* enn
#: fila, og det er riktig. Sammenlignes de strengt, melder prøven avvik på noe
#: som fungerer akkurat som det skal — og en prøve som roper ulv gjør at ingen
#: leser den neste gang.
SKRIVES_AV_GJENOPPRETTINGEN = {'audit.auditlog'}

TELLEKODE = '''
import json
from django.apps import apps
ut = {}
for modell in apps.get_models():
    try:
        ut[modell._meta.label_lower] = modell.objects.count()
    except Exception:
        pass
print('TALL:' + json.dumps(ut))
'''


class Command(BaseCommand):
    help = ('Last backupfilene inn i en engangsbase og sammenlign radene med '
            'det filene inneholder.')

    def add_arguments(self, parser):
        parser.add_argument('--full', action='store_true',
                            help='Bruk den hele databasefila alene.')
        parser.add_argument('--modul', metavar='SLUG',
                            help='Bare denne modulen.')
        parser.add_argument('--behold', action='store_true',
                            help='Ikke slett engangsbasen — skriv hvor den ligger.')

    # ── Kjøring ──────────────────────────────────────────────────────────────

    def handle(self, *args, **valg):
        filer = self._velg_filer(valg)
        arbeidsmappe = Path(tempfile.mkdtemp(prefix='verifiser-backup-'))
        try:
            self._kjor(filer, arbeidsmappe, valg)
        finally:
            if valg['behold']:
                self.stdout.write(f'\nEngangsbasen ble beholdt: {arbeidsmappe}')
            else:
                shutil.rmtree(arbeidsmappe, ignore_errors=True)

    def _velg_filer(self, valg) -> list[tuple[str, Path]]:
        """Den nyeste ekte fila per modul, i gjenopprettingsrekkefølge.

        Pre-restore-øyeblikksbildene hoppes over: de er tilstanden *før* en
        tidligere gjenoppretting, og å verifisere dem ville målt noe annet enn
        backupen.
        """
        from core.backup import get_backup_dir, get_handler

        mappe = get_backup_dir()
        if valg['full']:
            slugger = ['full']
        elif valg['modul']:
            if get_handler(valg['modul']) is None:
                raise CommandError(f'Ingen backup-handler for «{valg["modul"]}».')
            slugger = [valg['modul']]
        else:
            slugger = [s for s in REKKEFOLGE if get_handler(s) is not None]

        ut, mangler = [], []
        for slug in slugger:
            treff = sorted(
                (f for f in mappe.glob(f'backup-{slug}-*.json.gz')
                 if 'pre_restore' not in f.name),
                key=lambda f: f.stat().st_mtime)
            if treff:
                ut.append((slug, treff[-1]))
            else:
                mangler.append(slug)

        if mangler:
            self.stdout.write(self.style.WARNING(
                f'Ingen fil for: {", ".join(mangler)}. '
                f'De er ikke verifisert.'))
        if not ut:
            raise CommandError(
                f'Ingen backupfiler i {mappe}. Ta en med `backup_kjor --alle`, '
                f'eller hent en fra Scaleway med `hent_offsite --list`.')
        return ut

    def _kjor(self, filer, arbeidsmappe: Path, valg):
        backup_dir = arbeidsmappe / 'backups'
        backup_dir.mkdir()
        basefil = arbeidsmappe / 'engangs.sqlite3'

        # Filene kopieres, så gjenopprettingens pre-restore-øyeblikksbilder
        # havner her og ikke i den ekte backup-mappa.
        for _, sti in filer:
            shutil.copy2(sti, backup_dir / sti.name)

        miljo = dict(
            os.environ,
            DATABASE_URL=f'sqlite:///{basefil}',
            BACKUP_DIR=str(backup_dir),
            # Se `settings.py`: dette er den ene, navngitte åpningen for at en
            # flyktig SQLite-fil er lov også inne i prod-containeren.
            PORTAL_ENGANGSBASE='1',
            BACKUP_KLOKKE='av',
        )

        self.stdout.write(f'Engangsbase: {basefil}')
        self._underprosess(miljo, ['migrate', '--noinput', '-v', '0'],
                           'migrate mot engangsbasen')

        forventet = Counter()
        tomme = []
        for slug, sti in filer:
            i_fila = self._modeller_i(sti)
            antall = sum(i_fila.values())
            self.stdout.write(
                f'  laster {slug}: {sti.name} '
                f'({sti.stat().st_size} B, {antall} objekt(er))')
            if antall == 0:
                tomme.append((slug, sti.name))
            forventet.update(i_fila)
            args = ['gjenopprett', sti.name, '--ja']
            if slug == 'full':
                args.append('--full')
            self._underprosess(miljo, args, f'gjenoppretting av {slug}')

        faktisk = self._tell(miljo)
        self._rapporter(forventet, faktisk, filer, tomme)

    # ── Hjelpere ─────────────────────────────────────────────────────────────

    @staticmethod
    def _modeller_i(sti: Path) -> Counter:
        """Hvor mange objekter fila inneholder, per modell."""
        try:
            innhold = json.loads(gzip.open(sti, 'rb').read())
        except Exception as feil:   # noqa: BLE001
            raise CommandError(
                f'{sti.name} lar seg ikke pakke ut eller lese som JSON: '
                f'{feil.__class__.__name__}: {feil}') from feil
        return Counter(o['model'].lower() for o in innhold
                       if isinstance(o, dict) and 'model' in o)

    def _underprosess(self, miljo, argumenter, hva: str) -> str:
        """Kjør `manage.py …` mot engangsbasen i en **underprosess**.

        Ikke som et andre databasealias i denne prosessen, av samme grunn som
        `verifiser_migrasjoner`: migrasjonene og gjenopprettingen arbeider mot
        `default`, og med et alias ville de skrevet til den ekte basen i stedet
        for prøvebasen — altså målt noe helt annet enn de later som.
        """
        res = subprocess.run(
            [sys.executable, 'manage.py', *argumenter],
            env=miljo, capture_output=True, text=True)
        if res.returncode != 0:
            hale = (res.stderr or res.stdout or '').strip().splitlines()
            raise CommandError(
                f'{hva} feilet:\n  ' + '\n  '.join(hale[-10:]))
        return res.stdout

    def _tell(self, miljo) -> dict:
        ut = self._underprosess(miljo, ['shell', '-c', TELLEKODE],
                                'telling av rader')
        for linje in ut.splitlines():
            if linje.startswith('TALL:'):
                return json.loads(linje[len('TALL:'):])
        raise CommandError('Fikk ingen radtelling ut av engangsbasen.')

    def _rapporter(self, forventet: Counter, faktisk: dict, filer, tomme):
        """Sammenlign fil mot base, modell for modell.

        Å skrive ut radtall alene ville sagt at *noe* kom inn. Det som betyr
        noe er om det som var i fila er det som ligger i basen.
        """
        # Modeller som `migrate` seeder selv (ressursgruppene, moduloppsettet)
        # kan ligge i basen uten å stå i en fil vi lastet. De er ikke avvik.
        avvik, ok = [], 0
        self.stdout.write('')
        self.stdout.write(f'{"Modell":<34}{"I fila":>8}{"I basen":>9}')
        for modell, antall in sorted(forventet.items()):
            i_basen = faktisk.get(modell, 0)
            linje = f'{modell:<34}{antall:>8}{i_basen:>9}'

            if modell in SKRIVES_AV_GJENOPPRETTINGEN and i_basen >= antall:
                ok += 1
                ekstra = i_basen - antall
                self.stdout.write(
                    linje + (f'   (+{ekstra} fra gjenopprettingen selv)'
                             if ekstra else ''))
            elif i_basen == antall:
                ok += 1
                self.stdout.write(linje)
            else:
                avvik.append((modell, antall, i_basen))
                self.stdout.write(self.style.ERROR(linje + '   ← avvik'))

        self.stdout.write('')
        # **En tom fil er ikke en bestått prøve.** Uten denne linja ville
        # «alle modeller kom tilbake» stått grønt for en modul som ikke hadde
        # noe å komme tilbake med — og det er nøyaktig den backupen man tror
        # man har, helt til man trenger den.
        for slug, filnavn in tomme:
            self.stdout.write(self.style.WARNING(
                f'  {slug}: {filnavn} inneholder ingen rader. Enten er '
                f'modulen tom, eller så ble fila tatt før dataene fantes.'))
        if tomme:
            self.stdout.write('')

        navn = ', '.join(slug for slug, _ in filer)
        if avvik:
            raise CommandError(
                f'{len(avvik)} modell(er) kom ikke tilbake som de sto i fila. '
                f'Backupen er ikke gjenopprettbar slik den er.')
        self.stdout.write(self.style.SUCCESS(
            f'{ok} modell(er) kom tilbake med nøyaktig samme antall rader. '
            f'Verifisert: {navn}.'))
