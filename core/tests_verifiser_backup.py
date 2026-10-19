"""`manage.py verifiser_backup` — last filene i en engangsbase og tell radene.

Suiten har alt en test som gjenoppretter alle filene i rekkefølge
(`AlleFileneGjenopprettesTests`), og den svarer på om *koden* virker.
Kommandoen svarer på om **filene som ligger på volumet** virker, og det er et
annet spørsmål: en backup ingen har gjenopprettet er en hypotese.

Testene her kjører kommandoen med ekte underprosesser mot en ekte
engangs-SQLite-fil. Det gjør dem tregere enn resten av suiten, og det er
poenget — det er nettopp underprosessen og filstien som skal prøves.

**Men `migrate` kjøres én gang per klasse, ikke per test** (19. okt. 2026). Hver
test migrerte sin egen engangsbase, om lag 17 s, og de ti sto for 141 av 329
sekunder i `core` — CI-steget som går serielt. Nå migreres én mal i
`setUpClass`, og kommandoens `migrate`-steg kopierer den. Gjenopprettingen,
tellingen og opprydningen er like ekte som før. **Én test går hele veien**
(`EKTE_MIGRATE`): ellers kunne kommandoen sluttet å migrere uten at noe ble rødt.
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from core.management.commands.verifiser_backup import Command as VerifiserBackup
from django.core.management.base import CommandError
from django.test import TestCase, override_settings, tag

from vaktliste.test_helpers import lag_korps
from core.backup import KIND_MANUAL, create_backup, registrer_alle_moduler
from core.vakt import vakt_for_year
from core.test_helpers import prosessmappe


def _testmappe() -> Path:
    """Per prosess, så `--parallel` ikke deler den — `core.test_helpers.prosessmappe`."""
    return prosessmappe('verifiser')


def _backup_dir() -> Path:
    for f in _testmappe().glob('*'):
        if f.is_file():
            f.unlink(missing_ok=True)
    return _testmappe()


_EKTE_UNDERPROSESS = VerifiserBackup._underprosess

#: Testen som kjører kommandoens egen `migrate`. Resten får malen.
EKTE_MIGRATE = 'test_modulfilene_lastes_og_radene_stemmer'


#: **Treg** (ekte underprosesser og én ekte `migrate`, om lag 45 s).
#: `rask_sjekk` hopper over den; CI kjører den.
@tag('treg')
@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VerifiserBackupTests(TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        mappe = Path(tempfile.mkdtemp(prefix='verifiser-mal-'))
        cls.addClassCleanup(shutil.rmtree, mappe, ignore_errors=True)
        cls.malbase = mappe / 'mal.sqlite3'
        miljo = VerifiserBackup.engangsmiljo(os.environ, basefil=cls.malbase,
                                             backup_dir=mappe)
        _EKTE_UNDERPROSESS(VerifiserBackup(), miljo,
                           ['migrate', '--noinput', '-v', '0'], 'migrate av malen')

    def _underprosess_med_mal(self, kommando, miljo, argumenter, hva):
        if argumenter[0] != 'migrate':
            return _EKTE_UNDERPROSESS(kommando, miljo, argumenter, hva)
        self.migreringer.append(miljo['DATABASE_URL'])
        shutil.copyfile(self.malbase, miljo['DATABASE_URL'].removeprefix('sqlite:///'))
        return ''

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _backup_dir()
        self.miljo = patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)})
        self.migreringer: list[str] = []
        if self._testMethodName != EKTE_MIGRATE:
            mal = patch.object(VerifiserBackup, '_underprosess', autospec=True,
                               side_effect=self._underprosess_med_mal)
            mal.start()
            self.addCleanup(mal.stop)

    def _kall(self, *args):
        ut = StringIO()
        with self.miljo:
            call_command('verifiser_backup', *args, stdout=ut, stderr=StringIO())
        return ut.getvalue()

    def _lag_fil(self, slug):
        if slug == 'full':
            # En hel base har alltid brukere — bootstrap-kontoen, minst — og
            # `restore_backup` avviser en «hel» fil uten (29. sep. 2026): da er
            # den en modulfil med nytt navn. Fiksturen skal ha prod-formen.
            from accounts.models import CustomUser
            CustomUser.objects.get_or_create(username='bootstrap', defaults={'role': 'admin'})
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
        lag_korps(navn='Testkorps')
        for slug in ('portal', 'patients', 'vaktliste'):
            self._lag_fil(slug)

        ut = self._kall()
        self.assertIn('core.vakt', ut)
        self.assertIn('patients.patient', ut)
        self.assertIn('core.tilhorighet', ut)   # korpset, i portalfila siden 17. okt. 2026
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
        # Malen ble kopiert inn i stedet for at kommandoen migrerte — én gang.
        self.assertEqual(len(self.migreringer), 1)

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
