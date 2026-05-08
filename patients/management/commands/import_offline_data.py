"""Importer pasientdata fra en offline SQLite-fil til hoveddatabasen.

Bruk:
  python manage.py import_offline_data /sti/til/offline.sqlite3
  python manage.py import_offline_data /sti/til/offline.sqlite3 --year 2026
  python manage.py import_offline_data /sti/til/offline.sqlite3 --dry-run

Forventet flyt:
  1. Åpne offline.sqlite3 som read-only via sqlite3-modulen.
  2. Hent alle pasienter fra offline (filtrert på --year hvis oppgitt, ellers aktivt år).
  3. For hver pasient: skap ny Patient i default-databasen. Pasientnummer re-tilordnes
     som max(eksisterende_nr globalt) + 1, 2, 3... for å unngå kollisjon.
  4. Behandler/Helsepersonell-FK matches på NAVN i default-DB. Hvis ikke funnet,
     opprettes nye med samme navn og is_active=True.
  5. Alle operasjoner i én atomic-blokk. --dry-run ruller tilbake etterpå.
  6. Rapport: antall importert, antall behandlere/helsepersonell opprettet.

Audit-loggføring: hver importert pasient får en AuditLog-oppføring med
action='imported_offline' og object_repr i new_value-feltet.
"""
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from patients.models import Patient, Behandler, Helsepersonell
from patients.services import get_active_year
from audit.models import AuditLog


# Feltene på Patient som kopieres fra offline (FK og pasientnummer håndteres separat)
PATIENT_COPY_FIELDS = [
    'grovsortering', 'problemstilling', 'arsak',
    'transport', 'inntid', 'pabegynt', 'plassering', 'inn_obspost',
    'ut_obspost', 'utskrevet', 'utskrevet_til', 'journal',
    'lege', 'medisiner', 'helsepersonell',
]


class _DryRun(Exception):
    """Brukes til å rulle tilbake transaksjonen ved --dry-run."""
    pass


class Command(BaseCommand):
    help = 'Importer pasientdata fra offline SQLite til hoveddatabasen.'

    def add_arguments(self, parser):
        parser.add_argument('sqlite_path', type=str)
        parser.add_argument('--year', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        path = Path(opts['sqlite_path'])
        if not path.exists():
            raise CommandError(f'Finner ikke filen: {path}')

        year = opts['year'] or get_active_year()
        dry = opts['dry_run']

        # Åpne offline-SQLite som read-only
        conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row

        # Hent behandler- og helsepersonell-navn fra offline via join
        try:
            rows = self._fetch_offline_patients(conn, year)
        finally:
            conn.close()

        if not rows:
            self.stdout.write(self.style.WARNING(
                f'Ingen pasienter i offline-DB for år {year}.'))
            return

        self.stdout.write(f'Fant {len(rows)} pasienter i offline-DB (år {year}).')

        # Forbered navnemapping
        behandler_cache = {b.name: b for b in Behandler.objects.all()}
        hp_cache = {h.name: h for h in Helsepersonell.objects.all()}

        new_behandlere = 0
        new_hp = 0
        imported = 0

        # Start maks pasientnummer globalt i default-DB (pasientnummer er globalt unikt)
        existing_max = Patient.objects.order_by('-pasientnummer').first()
        next_nr = (existing_max.pasientnummer if existing_max else 0) + 1

        try:
            with transaction.atomic():
                for row in rows:
                    row_keys = list(row.keys())

                    # Behandler-mapping
                    behandler_obj = None
                    if row['behandler_name']:
                        name = row['behandler_name']
                        if name not in behandler_cache:
                            behandler_cache[name] = Behandler.objects.create(name=name)
                            new_behandlere += 1
                        behandler_obj = behandler_cache[name]

                    # Helsepersonell-mapping
                    hp_obj = None
                    if row['helsepersonell_name']:
                        name = row['helsepersonell_name']
                        if name not in hp_cache:
                            hp_cache[name] = Helsepersonell.objects.create(name=name)
                            new_hp += 1
                        hp_obj = hp_cache[name]

                    # Bygg ny Patient (re-nummerert for å unngå kollisjon)
                    p = Patient(
                        pasientnummer=next_nr,
                        year=year,
                        behandler=behandler_obj,
                        helsepersonell_ref=hp_obj,
                    )
                    for f in PATIENT_COPY_FIELDS:
                        if f in row_keys:
                            setattr(p, f, row[f] or '')
                    p.save()

                    # Audit-logg: bruker faktiske felter på AuditLog-modellen
                    AuditLog.objects.create(
                        user=None,
                        action='imported_offline',
                        table_name='patients_patient',
                        record_id=p.pk,
                        field_name=None,
                        old_value=None,
                        new_value=(
                            f'Importert fra offline: '
                            f'Patient #{next_nr} (offline #{row["pasientnummer"]})'
                        ),
                        ip=None,
                    )

                    imported += 1
                    next_nr += 1

                if dry:
                    raise _DryRun()
        except _DryRun:
            self.stdout.write(self.style.WARNING('DRY RUN – rullet tilbake.'))

        self.stdout.write(self.style.SUCCESS(
            f'Importert {imported} pasienter, '
            f'{new_behandlere} nye behandlere, {new_hp} nye helsepersonell.'
        ))

    def _fetch_offline_patients(self, conn, year):
        """Hent pasienter med joinede navn for behandler og helsepersonell_ref."""
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*,
                   b.name AS behandler_name,
                   h.name AS helsepersonell_name
            FROM patients_patient p
            LEFT JOIN patients_behandler b ON p.behandler_id = b.id
            LEFT JOIN patients_helsepersonell h ON p.helsepersonell_ref_id = h.id
            WHERE p.year = ?
            ORDER BY p.pasientnummer
        """, (year,))
        return cur.fetchall()
