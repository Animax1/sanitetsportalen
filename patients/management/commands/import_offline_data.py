"""Importer pasientdata fra en offline SQLite-fil til hoveddatabasen.

Bruk:
  python manage.py import_offline_data /sti/til/offline.sqlite3
  python manage.py import_offline_data /sti/til/offline.sqlite3 --year 2026
  python manage.py import_offline_data /sti/til/offline.sqlite3 --dry-run
  python manage.py import_offline_data /sti/til/offline.sqlite3 --force

Forventet flyt:
  1. Åpne offline.sqlite3 som read-only via sqlite3-modulen.
  2. Hent alle pasienter fra offline (filtrert på --year hvis oppgitt, ellers aktivt år).
  3. Valider de kliniske dropdown-feltene mot whitelisten i patients/choices.py.
     Ugyldige verdier avbryter hele importen, med rapport per rad. --force
     importerer dem likevel, for bevisst import av gamle data.
  4. For hver pasient: skap ny Patient i default-databasen. Pasientnummer re-tilordnes
     som max(eksisterende_nr globalt) + 1, 2, 3... for å unngå kollisjon.
  5. Behandler/Helsepersonell-FK matches på NAVN i default-DB. Hvis ikke funnet,
     opprettes nye med samme navn og is_active=True.
  6. Alle operasjoner i én atomic-blokk. --dry-run ruller tilbake etterpå.
  7. Rapport: antall importert, antall behandlere/helsepersonell opprettet.

Audit-loggføring: hver importert pasient får en AuditLog-oppføring med
``action='IMPORT'`` og en beskrivelse i ``new_value``-feltet. Se kommentaren
ved selve kallet for hvorfor verdien er kort og ikke står i ``ACTION_CHOICES``.
"""
import sqlite3
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from patients.choices import validate_patient_choice_fields
from patients.models import Patient, Forstehjelper, Helsepersonell
from patients.services import hent_aktiv_vakt, vakt_for_year
from audit.models import AuditLog


# Feltene på Patient som kopieres fra offline (FK og pasientnummer håndteres separat)
PATIENT_COPY_FIELDS = [
    'grovsortering', 'problemstilling', 'arsak',
    'transport', 'inntid', 'pabegynt', 'plassering', 'inn_obspost',
    'ut_obspost', 'utskrevet', 'utskrevet_til', 'journal',
    'lege', 'medisiner',
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
        parser.add_argument(
            '--force', action='store_true',
            help='Importer selv om kliniske felt bryter whitelisten i choices.py.',
        )

    def handle(self, *args, **opts):
        path = Path(opts['sqlite_path'])
        if not path.exists():
            raise CommandError(f'Finner ikke filen: {path}')

        year = opts['year'] or hent_aktiv_vakt().year
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

        # Valider før noe skrives, slik at rapporten dekker alle radene
        normalized = self._validate_choice_fields(rows, opts['force'])

        # Forbered navnemapping
        forstehjelper_cache = {b.name: b for b in Forstehjelper.objects.all()}
        hp_cache = {h.name: h for h in Helsepersonell.objects.all()}

        new_forstehjelpere = 0
        new_hp = 0
        imported = 0

        # Renummerer fra vaktas eget maks — pasientnummer er unikt per vakt
        # siden deploy 2, ikke globalt.
        vakt = vakt_for_year(year)
        existing_max = (Patient.objects.filter(vakt=vakt)
                        .order_by('-pasientnummer').first())
        next_nr = (existing_max.pasientnummer if existing_max else 0) + 1

        try:
            with transaction.atomic():
                for row, values in zip(rows, normalized):
                    # Førstehjelper-mapping (SQL leser fra patients_behandler i offline-DB)
                    forstehjelper_obj = None
                    if row['behandler_name']:
                        name = row['behandler_name']
                        if name not in forstehjelper_cache:
                            forstehjelper_cache[name] = Forstehjelper.objects.create(name=name)
                            new_forstehjelpere += 1
                        forstehjelper_obj = forstehjelper_cache[name]

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
                        # Vakta for radens eget år, ikke den aktive: en
                        # offline-import kan i prinsippet bære et annet år,
                        # og da skal koblingen følge året.
                        vakt=vakt_for_year(year),
                        forstehjelper=forstehjelper_obj,
                        helsepersonell_ref=hp_obj,
                    )
                    for f, v in values.items():
                        setattr(p, f, v)
                    p.save()

                    # Audit-logg: bruker faktiske felter på AuditLog-modellen.
                    #
                    # Verdien er 'IMPORT', ikke 'imported_offline'. Grunnen er at
                    # `AuditLog.action` er `max_length=10`, og den gamle verdien
                    # på 16 tegn ga `DataError: value too long for type character
                    # varying(10)` mot Postgres. Testene fanget det aldri fordi de
                    # kjører på SQLite, som ikke håndhever varchar-lengde —
                    # `AuditActionLengdeTests` vokter det nå backend-uavhengig.
                    #
                    # 'IMPORT' står bevisst *ikke* i `AuditLog.ACTION_CHOICES`. Å
                    # legge den til ville krevd en migrasjon i `audit`-appen, og
                    # enhver slik migrasjon drar med seg en ventende omdøping av
                    # `audit_audit_created_a3c1b8_idx` — indeksen som tok ned
                    # produksjon 13. aug. 2026. Choices håndheves ikke av
                    # databasen, og `objects.create()` validerer ikke mot dem, så
                    # verdien virker. Den kan normaliseres den dagen noen tar
                    # indeks-avviket bevisst.
                    AuditLog.objects.create(
                        user=None,
                        action='IMPORT',
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

                from patients.services import _pasientnr_nokkel
                from patients.models import AppSetting
                nokkel = _pasientnr_nokkel(vakt)
                gjeldende = AppSetting.get(nokkel, None)
                if gjeldende is None or int(gjeldende) < next_nr:
                    AppSetting.set(nokkel, next_nr)

                if dry:
                    raise _DryRun()
        except _DryRun:
            self.stdout.write(self.style.WARNING('DRY RUN – rullet tilbake.'))

        self.stdout.write(self.style.SUCCESS(
            f'Importert {imported} pasienter, '
            f'{new_forstehjelpere} nye forstehjelpere, {new_hp} nye helsepersonell.'
        ))

    def _validate_choice_fields(self, rows, force):
        """Kjør de kliniske dropdown-feltene gjennom whitelisten i choices.py.

        Importen bygger ``Patient``-objekter direkte og går dermed utenom
        API-valideringen. Det gjorde den til en av veiene inn i databasen der
        en verdi utenfor whitelisten – i verste fall HTML – kunne lande uten
        å bli sett, og bli satt inn uescapet i statistikkfanen senere (N6).

        Returnerer én dict per rad med normaliserte (trimmede) verdier, i
        samme rekkefølge som ``rows``. Feltene som ikke finnes i offline-fila
        utelates, slik at eldre skjemaversjoner fortsatt kan importeres.
        """
        normalized = []
        feil = []

        for row in rows:
            row_keys = list(row.keys())
            data = {f: (row[f] or '') for f in PATIENT_COPY_FIELDS if f in row_keys}
            try:
                validate_patient_choice_fields(data)
            except ValidationError as exc:
                for msg in exc.messages:
                    feil.append(f'offline #{row["pasientnummer"]}: {msg}')
            # validate_patient_choice_fields muterer in-place, så `data` er
            # normalisert så langt det lot seg gjøre – også ved feil.
            normalized.append(data)

        if feil:
            if not force:
                raise CommandError(
                    f'Avbrutt: {len(feil)} feltverdi(er) er ikke gyldige:\n  '
                    + '\n  '.join(feil)
                    + '\n\nRett kilden, eller kjør på nytt med --force for å '
                      'importere verdiene som de er.'
                )
            self.stdout.write(self.style.WARNING(
                f'--force: importerer {len(feil)} ugyldig(e) feltverdi(er):'))
            for msg in feil:
                self.stdout.write(self.style.WARNING(f'  {msg}'))

        return normalized

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
