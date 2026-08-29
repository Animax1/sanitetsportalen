"""Tester for offline-pakken: create_offline_users og import_offline_data.

Kjør med: python manage.py test patients.tests_offline
"""
import sqlite3
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import CustomUser
from audit.models import AuditLog
from patients.models import Patient, Forstehjelper, Helsepersonell
from patients.services import vakt_for_year


# ── Hjelpefunksjon – bygg mini offline-SQLite ────────────────────────────────

def _build_offline_sqlite(path, patients, behandlere=None, helsepersonell=None):
    """Opprett en minimal offline.sqlite3 med pasienter for testing.

    Args:
        path: filsti til SQLite-filen (str eller Path)
        patients: liste med dicts – pasient-rader (pasientnummer, year, ...)
        behandlere: liste med dicts – {'id': int, 'name': str, 'is_active': bool}
        helsepersonell: liste med dicts – {'id': int, 'name': str, 'is_active': bool}
    """
    behandlere = behandlere or []
    helsepersonell = helsepersonell or []

    conn = sqlite3.connect(str(path))
    cur = conn.cursor()

    # Behandler-tabell
    cur.execute("""
        CREATE TABLE patients_behandler (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)
    for b in behandlere:
        cur.execute(
            "INSERT INTO patients_behandler (id, name, is_active, created_at) VALUES (?, ?, ?, '')",
            (b['id'], b['name'], 1 if b.get('is_active', True) else 0),
        )

    # Helsepersonell-tabell
    cur.execute("""
        CREATE TABLE patients_helsepersonell (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)
    for h in helsepersonell:
        cur.execute(
            "INSERT INTO patients_helsepersonell (id, name, is_active, created_at) VALUES (?, ?, ?, '')",
            (h['id'], h['name'], 1 if h.get('is_active', True) else 0),
        )

    # Pasient-tabell – alle felt fra Patient-modellen
    cur.execute("""
        CREATE TABLE patients_patient (
            id INTEGER PRIMARY KEY,
            pasientnummer INTEGER NOT NULL,
            year INTEGER NOT NULL,
            grovsortering TEXT NOT NULL DEFAULT '',
            problemstilling TEXT NOT NULL DEFAULT '',
            arsak TEXT NOT NULL DEFAULT '',
            transport TEXT NOT NULL DEFAULT '',
            inntid TEXT NOT NULL DEFAULT '',
            pabegynt TEXT NOT NULL DEFAULT '',
            plassering TEXT NOT NULL DEFAULT '',
            inn_obspost TEXT NOT NULL DEFAULT '',
            ut_obspost TEXT NOT NULL DEFAULT '',
            utskrevet TEXT NOT NULL DEFAULT '',
            utskrevet_til TEXT NOT NULL DEFAULT '',
            journal TEXT NOT NULL DEFAULT '',
            lege TEXT NOT NULL DEFAULT '',
            medisiner TEXT NOT NULL DEFAULT '',
            helsepersonell TEXT NOT NULL DEFAULT '',
            behandler_id INTEGER REFERENCES patients_behandler(id),
            helsepersonell_ref_id INTEGER REFERENCES patients_helsepersonell(id),
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    for p in patients:
        cur.execute("""
            INSERT INTO patients_patient
                (pasientnummer, year, grovsortering, problemstilling, arsak,
                 transport, inntid, pabegynt, plassering, inn_obspost,
                 ut_obspost, utskrevet, utskrevet_til, journal,
                 lege, medisiner, helsepersonell,
                 behandler_id, helsepersonell_ref_id,
                 created_at, updated_at, is_active)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 1)
        """, (
            p.get('pasientnummer', 1),
            p.get('year', 2026),
            p.get('grovsortering', ''),
            p.get('problemstilling', ''),
            p.get('arsak', ''),
            p.get('transport', ''),
            p.get('inntid', ''),
            p.get('pabegynt', ''),
            p.get('plassering', ''),
            p.get('inn_obspost', ''),
            p.get('ut_obspost', ''),
            p.get('utskrevet', ''),
            p.get('utskrevet_til', ''),
            p.get('journal', ''),
            p.get('lege', ''),
            p.get('medisiner', ''),
            p.get('helsepersonell', ''),
            p.get('behandler_id', None),
            p.get('helsepersonell_ref_id', None),
        ))

    conn.commit()
    conn.close()


def _call_create_offline_users(*args):
    """Kjør create_offline_users-kommandoen og returner stdout som streng."""
    from django.core.management import call_command
    out = StringIO()
    call_command('create_offline_users', *args, stdout=out)
    return out.getvalue()


def _call_import_offline_data(path, **kwargs):
    """Kjør import_offline_data-kommandoen og returner stdout som streng."""
    from django.core.management import call_command
    out = StringIO()
    call_command('import_offline_data', str(path), stdout=out, **kwargs)
    return out.getvalue()


# ── Tester for create_offline_users ──────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class CreateOfflineUsersTests(TestCase):
    """Tester for management-kommandoen create_offline_users."""

    def test_create_offline_users_creates_both(self):
        """Kommandoen skal opprette admin-offline og vakt-offline med rett rolle."""
        _call_create_offline_users()

        admin = CustomUser.objects.get(username='admin-offline')
        vakt = CustomUser.objects.get(username='vakt-offline')

        self.assertEqual(admin.role, 'admin')
        self.assertEqual(vakt.role, 'bruker')
        self.assertFalse(admin.must_change_password)
        self.assertFalse(admin.mfa_required)
        self.assertFalse(vakt.must_change_password)
        self.assertFalse(vakt.mfa_required)

    def test_create_offline_users_is_idempotent(self):
        """Kommandoen kan kjøres to ganger uten å lage duplikater."""
        _call_create_offline_users()
        _call_create_offline_users()

        antall_admin = CustomUser.objects.filter(username='admin-offline').count()
        antall_vakt = CustomUser.objects.filter(username='vakt-offline').count()
        self.assertEqual(antall_admin, 1)
        self.assertEqual(antall_vakt, 1)

    def test_create_offline_users_rotate_changes_password(self):
        """Med --rotate skal passordet endres slik at det gamle ikke lenger virker."""
        # Første kjøring – noter passordet via check_password
        _call_create_offline_users()
        user = CustomUser.objects.get(username='admin-offline')
        old_hash = user.password

        # Roter
        _call_create_offline_users('--rotate')
        user.refresh_from_db()

        # Hash skal ha endret seg
        self.assertNotEqual(user.password, old_hash,
                            'Passordhash skal endres etter --rotate')

    def test_password_file_written_and_format_ok(self):
        """OFFLINE_PASSORD.md skal skrives og inneholde riktig innhold."""
        from django.conf import settings
        pw_file = Path(settings.BASE_DIR) / 'OFFLINE_PASSORD.md'

        # Sørg for at filen ikke finnes fra før
        if pw_file.exists():
            pw_file.unlink()

        _call_create_offline_users()

        self.assertTrue(pw_file.exists(), 'OFFLINE_PASSORD.md skal eksistere')
        innhold = pw_file.read_text(encoding='utf-8')

        self.assertIn('# Offline-passord', innhold)
        self.assertIn('admin-offline', innhold)
        self.assertIn('vakt-offline', innhold)
        self.assertIn('Generert:', innhold)
        self.assertIn('| Brukernavn | Rolle | Passord |', innhold)

        # Rydder opp etter testen
        pw_file.unlink(missing_ok=True)


# ── Tester for import_offline_data ───────────────────────────────────────────

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ImportOfflineDataTests(TestCase):
    """Tester for management-kommandoen import_offline_data."""

    def _make_sqlite(self, patients, behandlere=None, helsepersonell=None):
        """Hjelpemetode: opprett midlertidig SQLite-fil og returner (tf, path)."""
        tf = tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False)
        tf.close()
        p = Path(tf.name)
        _build_offline_sqlite(p, patients, behandlere, helsepersonell)
        return tf, p

    def test_import_offline_data_creates_patients(self):
        """Import av 2 pasienter fra offline-SQLite skal lage 2 nye Patient-rader."""
        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026, 'grovsortering': 'Rød'},
                {'pasientnummer': 2, 'year': 2026, 'grovsortering': 'Gul'},
            ]
        )
        try:
            _call_import_offline_data(path, year=2026)
            self.assertEqual(Patient.objects.filter(vakt=vakt_for_year(2026)).count(), 2)
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_dry_run_rolls_back(self):
        """Dry-run skal ikke etterlate noen pasienter i databasen."""
        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026, 'grovsortering': 'Grønn'},
            ]
        )
        try:
            out = _call_import_offline_data(path, year=2026, dry_run=True)
            self.assertEqual(Patient.objects.filter(vakt=vakt_for_year(2026)).count(), 0)
            self.assertIn('DRY RUN', out)
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_renumbers_patient_nr(self):
        """Pasienter i default-DB og offline-DB med overlappende nr skal få nye unike nr."""
        # Opprett en eksisterende pasient med pasientnummer 1000 i default-DB
        Patient.objects.create(pasientnummer=1000, vakt=vakt_for_year(2026))

        tf, path = self._make_sqlite(
            patients=[
                # Offline-pasienten har pasientnummer 1000 – kollisjon med eksisterende
                {'pasientnummer': 1000, 'year': 2026, 'grovsortering': 'Gul'},
                {'pasientnummer': 1001, 'year': 2026, 'grovsortering': 'Rød'},
            ]
        )
        try:
            _call_import_offline_data(path, year=2026)
            alle_nr = list(
                Patient.objects.filter(vakt=vakt_for_year(2026))
                .order_by('pasientnummer')
                .values_list('pasientnummer', flat=True)
            )
            # Alle pasientnummer skal være unike
            self.assertEqual(len(alle_nr), len(set(alle_nr)),
                             f'Duplikate pasientnummer funnet: {alle_nr}')
            # To nye pasienter skal ha fått nr > 1000
            self.assertEqual(
                Patient.objects.filter(vakt=vakt_for_year(2026), pasientnummer__gt=1000).count(), 2
            )
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_creates_missing_behandlere(self):
        """Førstehjelper som finnes i offline men ikke i default skal opprettes automatisk."""
        # Sørg for at forstehjelperen ikke finnes i default-DB
        self.assertFalse(Forstehjelper.objects.filter(name='Dr. Offline').exists())

        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026, 'behandler_id': 99},
            ],
            behandlere=[
                {'id': 99, 'name': 'Dr. Offline'},
            ],
        )
        try:
            out = _call_import_offline_data(path, year=2026)
            self.assertTrue(Forstehjelper.objects.filter(name='Dr. Offline').exists())
            self.assertIn('1 nye forstehjelpere', out)
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_reuses_existing_behandler(self):
        """Førstehjelper som allerede finnes i default-DB skal gjenbrukes, ikke dupliseres."""
        Forstehjelper.objects.create(name='Dr. Eksisterende')

        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026, 'behandler_id': 1},
            ],
            behandlere=[
                {'id': 1, 'name': 'Dr. Eksisterende'},
            ],
        )
        try:
            _call_import_offline_data(path, year=2026)
            antall = Forstehjelper.objects.filter(name='Dr. Eksisterende').count()
            self.assertEqual(antall, 1, 'Førstehjelper skal ikke dupliseres')
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_audit_log_created(self):
        """Hver importert pasient skal få en AuditLog-rad med action=IMPORT."""
        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026},
                {'pasientnummer': 2, 'year': 2026},
            ]
        )
        try:
            _call_import_offline_data(path, year=2026)
            antall_logger = AuditLog.objects.filter(action='IMPORT').count()
            self.assertEqual(antall_logger, 2)
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_audit_action_passer_i_kolonnen(self):
        """Verdien må få plass i `AuditLog.action`, uansett database.

        Testene kjører på SQLite, som ikke håndhever varchar-lengde. Postgres
        gjør det. 22. aug. 2026 stoppet importen mot produksjon med
        `DataError: value too long for type character varying(10)` fordi
        verdien var `imported_offline` — 16 tegn mot en grense på 10 — mens hele
        testsuiten var grønn. Denne testen leser grensen fra modellen og er
        derfor uavhengig av hvilken backend som kjører.
        """
        tf, path = self._make_sqlite(patients=[{'pasientnummer': 1, 'year': 2026}])
        try:
            _call_import_offline_data(path, year=2026)
            grense = AuditLog._meta.get_field('action').max_length
            for verdi in AuditLog.objects.values_list('action', flat=True):
                self.assertLessEqual(
                    len(verdi), grense,
                    f'action={verdi!r} er {len(verdi)} tegn, men kolonnen tar '
                    f'{grense}. Dette feiler mot Postgres, ikke mot SQLite.',
                )
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_empty_db_gives_warning(self):
        """Tom offline-DB (ingen pasienter for året) skal gi en advarsel, ikke kræsje."""
        tf, path = self._make_sqlite(patients=[])
        try:
            out = _call_import_offline_data(path, year=2026)
            self.assertIn('Ingen pasienter', out)
            self.assertEqual(Patient.objects.filter(vakt=vakt_for_year(2026)).count(), 0)
        finally:
            path.unlink(missing_ok=True)

    # ── Whitelist-validering (N6) ────────────────────────────────────────────

    def test_import_avviser_verdi_utenfor_whitelisten(self):
        """Import bygger Patient direkte, så whitelisten må håndheves her også.

        Uten dette var kommandoen en av veiene inn i databasen der en verdi
        utenfor `patients/choices.py` kunne lande – og senere bli satt inn i
        statistikkfanen.
        """
        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026,
                 'problemstilling': '<img src=x onerror=alert(1)>'},
            ]
        )
        try:
            with self.assertRaises(CommandError) as ctx:
                _call_import_offline_data(path, year=2026)
            self.assertIn('problemstilling', str(ctx.exception))
            self.assertIn('--force', str(ctx.exception),
                          'Feilmeldingen må peke på utveien for bevisst import')
            self.assertEqual(Patient.objects.filter(vakt=vakt_for_year(2026)).count(), 0,
                             'Ingenting skal være skrevet når importen avbrytes')
        finally:
            path.unlink(missing_ok=True)

    def test_import_rapporterer_alle_ugyldige_rader_samtidig(self):
        """Rapporten skal dekke alle radene, ikke stoppe på den første."""
        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026, 'problemstilling': 'Tull'},
                {'pasientnummer': 2, 'year': 2026, 'transport': 'Teleport'},
            ]
        )
        try:
            with self.assertRaises(CommandError) as ctx:
                _call_import_offline_data(path, year=2026)
            melding = str(ctx.exception)
            self.assertIn('offline #1', melding)
            self.assertIn('offline #2', melding)
        finally:
            path.unlink(missing_ok=True)

    def test_import_med_force_tar_inn_ugyldig_verdi_og_advarer(self):
        """--force finnes for bevisst import av gamle, uvaliderte data."""
        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026, 'problemstilling': 'Gammel verdi'},
            ]
        )
        try:
            out = _call_import_offline_data(path, year=2026, force=True)
            self.assertEqual(Patient.objects.filter(vakt=vakt_for_year(2026)).count(), 1)
            self.assertEqual(
                Patient.objects.get(vakt=vakt_for_year(2026)).problemstilling, 'Gammel verdi')
            self.assertIn('--force', out, 'Importen skal si tydelig fra i loggen')
            self.assertIn('problemstilling', out)
        finally:
            path.unlink(missing_ok=True)

    def test_import_normaliserer_whitespace_i_gyldige_felt(self):
        """Valideringen trimmer, på samme måte som API-veien gjør."""
        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026,
                 'problemstilling': '  Brystsmerter  ', 'grovsortering': 'Rød'},
            ]
        )
        try:
            _call_import_offline_data(path, year=2026)
            p = Patient.objects.get(vakt=vakt_for_year(2026))
            self.assertEqual(p.problemstilling, 'Brystsmerter')
            self.assertEqual(p.grovsortering, 'Rød')
        finally:
            path.unlink(missing_ok=True)

    def test_import_offline_data_creates_missing_helsepersonell(self):
        """Helsepersonell som finnes i offline men ikke i default skal opprettes."""
        self.assertFalse(Helsepersonell.objects.filter(name='Sykepleier Offline').exists())

        tf, path = self._make_sqlite(
            patients=[
                {'pasientnummer': 1, 'year': 2026, 'helsepersonell_ref_id': 77},
            ],
            helsepersonell=[
                {'id': 77, 'name': 'Sykepleier Offline'},
            ],
        )
        try:
            out = _call_import_offline_data(path, year=2026)
            self.assertTrue(Helsepersonell.objects.filter(name='Sykepleier Offline').exists())
            self.assertIn('1 nye helsepersonell', out)
        finally:
            path.unlink(missing_ok=True)
