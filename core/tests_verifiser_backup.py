"""`manage.py verifiser_backup` — last filene i en engangsbase og tell radene.

Suiten har alt en test som gjenoppretter alle filene i rekkefølge
(`AlleFileneGjenopprettesTests`), og den svarer på om *koden* virker.
Kommandoen svarer på om **filene som ligger på volumet** virker, og det er et
annet spørsmål: en backup ingen har gjenopprettet er en hypotese.

Testene her kjører kommandoen med ekte underprosesser mot en ekte
engangs-SQLite-fil. Det gjør dem tregere enn resten av suiten, og det er
poenget — det er nettopp underprosessen og filstien som skal prøves.
"""
from __future__ import annotations

import gzip
import json
import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.backup import KIND_MANUAL, create_backup, registrer_alle_moduler
from patients.services import vakt_for_year

TEST_BACKUP_DIR = Path('/tmp/test-backups-verifiser')


def _backup_dir() -> Path:
    TEST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for f in TEST_BACKUP_DIR.glob('*'):
        if f.is_file():
            f.unlink(missing_ok=True)
    return TEST_BACKUP_DIR


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VerifiserBackupTests(TestCase):

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _backup_dir()
        self.miljo = patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)})

    def _kall(self, *args):
        ut = StringIO()
        with self.miljo:
            call_command('verifiser_backup', *args, stdout=ut, stderr=StringIO())
        return ut.getvalue()

    def _lag_fil(self, slug):
        with self.miljo:
            return create_backup(slug=slug, kind=KIND_MANUAL)

    # ── Sperrer og feilstier ─────────────────────────────────────────────────

    def test_uten_filer_sier_hvor_man_far_tak_i_dem(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self._kall()
        self.assertIn('backup_kjor', str(ctx.exception))
        self.assertIn('hent_offsite', str(ctx.exception))

    def test_ukjent_modul_avvises(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self._kall('--modul', 'finnes-ikke')
        self.assertIn('backup-handler', str(ctx.exception))

    def test_odelagt_fil_sier_hva_som_er_galt(self) -> None:
        """En fil som ikke lar seg pakke ut er den verste slags backup: den
        ser ut som en."""
        backup = self._lag_fil('patients')
        (self.backup_dir / backup.filename).write_bytes(b'ikke gzip i det hele tatt')

        with self.assertRaises(CommandError) as ctx:
            self._kall('--modul', 'patients')
        self.assertIn('lar seg ikke pakke ut', str(ctx.exception))

    def test_fil_som_lover_mer_enn_den_leverer_gir_avvik(self) -> None:
        """Kontrollen som gjør resten av utskriften verdt å lese.

        Uten den ville «alt kom tilbake» bare betydd «noe kom tilbake». Her
        dubleres én pasient i fila med samme primærnøkkel: fila påstår fire,
        `loaddata` skriver over og gir tre, og prøven skal se forskjellen.
        """
        vakt = vakt_for_year(2026)
        from patients.models import Patient

        for nr in (1, 2, 3):
            Patient.objects.create(pasientnummer=nr, vakt=vakt,
                                   problemstilling='Test')
        self._lag_fil('portal')
        backup = self._lag_fil('patients')

        sti = self.backup_dir / backup.filename
        innhold = json.loads(gzip.open(sti, 'rb').read())
        pasient = next(o for o in innhold if o['model'] == 'patients.patient')
        innhold.append(dict(pasient))          # samme pk — overskriver seg selv
        with gzip.open(sti, 'wb') as f:
            f.write(json.dumps(innhold).encode('utf-8'))

        with self.assertRaises(CommandError) as ctx:
            self._kall()
        self.assertIn('ikke tilbake som de sto i fila', str(ctx.exception))

    # ── Normalveien ──────────────────────────────────────────────────────────

    def test_modulfilene_lastes_og_radene_stemmer(self) -> None:
        vakt = vakt_for_year(2026)
        from patients.models import Patient
        from vaktliste.models import Korps

        Patient.objects.create(pasientnummer=1, vakt=vakt, problemstilling='X')
        Korps.objects.create(navn='Testkorps')
        for slug in ('portal', 'patients', 'vaktliste'):
            self._lag_fil(slug)

        ut = self._kall()
        self.assertIn('core.vakt', ut)
        self.assertIn('patients.patient', ut)
        self.assertIn('vaktliste.korps', ut)
        self.assertIn('samme antall rader', ut)

    def test_hel_fil_alene(self) -> None:
        """Auditraden gjenopprettingen selv skriver skal ikke telle som avvik —
        en prøve som roper ulv blir ikke lest neste gang."""
        vakt = vakt_for_year(2026)
        from patients.models import Patient

        Patient.objects.create(pasientnummer=1, vakt=vakt, problemstilling='X')
        self._lag_fil('full')

        ut = self._kall('--full')
        self.assertIn('audit.auditlog', ut)
        self.assertIn('fra gjenopprettingen selv', ut)
        self.assertIn('samme antall rader', ut)

    def test_tom_fil_far_en_advarsel(self) -> None:
        """«Alt kom tilbake» skal ikke stå grønt for en modul som ikke hadde
        noe å komme tilbake med."""
        self._lag_fil('arkiv')   # ingen arkiver finnes i en fersk testbase
        ut = self._kall('--modul', 'arkiv')
        self.assertIn('inneholder ingen rader', ut)

    def test_manglende_modul_nevnes_men_stopper_ikke(self) -> None:
        self._lag_fil('patients')
        ut = self._kall()
        self.assertIn('Ingen fil for:', ut)
        self.assertIn('samme antall rader', ut)

    def test_rorer_ikke_den_ekte_backupmappa(self) -> None:
        """Gjenopprettingen lager pre-restore-øyeblikksbilder. De skal havne i
        søpla, ikke blant backupene man faktisk har."""
        self._lag_fil('patients')
        for_ = sorted(f.name for f in self.backup_dir.glob('*'))

        self._kall('--modul', 'patients')

        self.assertEqual(sorted(f.name for f in self.backup_dir.glob('*')), for_)

    def test_engangsbasen_slettes(self) -> None:
        self._lag_fil('patients')
        ut = self._kall('--modul', 'patients')
        bane = [linje for linje in ut.splitlines()
                if linje.startswith('Engangsbase: ')][0]
        sti = Path(bane.removeprefix('Engangsbase: ').strip())
        self.assertFalse(sti.exists(), 'Engangsbasen skal ikke bli liggende.')
        self.assertFalse(sti.parent.exists())
