"""Backup av vaktlistemodulen (13. sep. 2026).

Modulen hadde ingen dekning fram til nå: korps, mannskap med telefon, e-post og
ISSI, kompetanser, ressurser og vaktposter lå utenfor alle backupfiler siden
appen gikk i prod 11. september.

Testene her er en **rundtur**, ikke en inspeksjon av dumpen: data inn, backup,
slett alt, gjenopprett, og se etter at det som kom tilbake er det som gikk inn.
En dump som ser riktig ut, men ikke lar seg laste, er ingen backup — og den
forskjellen viser seg bare når man faktisk laster den.
"""
from __future__ import annotations

import gzip
import json
import os
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from core.backup import (
    KIND_MANUAL,
    create_backup,
    get_handler,
    registrer_alle_moduler,
    restore_backup,
)
from patients.services import vakt_for_year
from vaktliste.models import (
    Korps,
    Kompetanse,
    Mannskap,
    Ressurs,
    Ressursrolle,
    Vaktliste,
    Vaktpost,
)
from vaktliste.test_helpers import gruppe

TEST_BACKUP_DIR = Path('/tmp/test-backups-vaktliste')


def _backup_dir() -> Path:
    TEST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for f in TEST_BACKUP_DIR.glob('*'):
        if f.is_file():
            f.unlink(missing_ok=True)
    return TEST_BACKUP_DIR


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class VaktlisteBackupTests(TestCase):

    def setUp(self) -> None:
        registrer_alle_moduler()
        self.backup_dir = _backup_dir()
        self.vakt = vakt_for_year(2026)

        self.korps = Korps.objects.create(navn='Testkorps')
        self.kompetanse = Kompetanse.objects.create(navn='AFØR')
        self.mannskap = Mannskap.objects.create(
            navn='Kari Nordmann', korps=self.korps,
            telefon='99887766', epost='kari@example.org', issi='0401234',
        )
        self.mannskap.kompetanser.add(self.kompetanse)

        # Gruppene er seedet av migrasjon 0007 og slås opp, ikke lages —
        # slutter seedingen å virke, skal det bli synlig her.
        self.gruppe = gruppe('Ambulanse')
        self.rolle = Ressursrolle.objects.create(navn='Sjåfør', gruppe=self.gruppe)
        self.liste = Vaktliste.objects.create(vakt=self.vakt)
        self.ressurs = Ressurs.objects.create(
            vaktliste=self.liste, navn='Bil A', gruppe=self.gruppe)
        self.vaktpost = Vaktpost.objects.create(
            ressurs=self.ressurs, mannskap=self.mannskap, rolle=self.rolle,
            fra_tid=timezone.now(),
            til_tid=timezone.now() + timedelta(hours=8),
        )

    def test_handleren_er_registrert(self) -> None:
        self.assertIsNotNone(get_handler('vaktliste'))

    def test_alle_modellene_er_med_i_dumpen(self) -> None:
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='vaktliste', kind=KIND_MANUAL)
            raa = gzip.open(self.backup_dir / backup.filename, 'rb').read()
        modeller = {o['model'] for o in json.loads(raa)}
        for ventet in ('vaktliste.korps', 'vaktliste.mannskap',
                       'vaktliste.kompetanse', 'vaktliste.ressursgruppe',
                       'vaktliste.ressursrolle', 'vaktliste.vaktliste',
                       'vaktliste.ressurs', 'vaktliste.vaktpost'):
            with self.subTest(modell=ventet):
                self.assertIn(ventet, modeller)

    def test_rundtur_gir_dataene_tilbake(self) -> None:
        """Hele veien: backup, slett alt, gjenopprett, og sammenlign."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='vaktliste', kind=KIND_MANUAL)

            Vaktpost.objects.all().delete()
            Ressurs.objects.all().delete()
            Vaktliste.objects.all().delete()
            Mannskap.objects.all().delete()
            Korps.objects.all().delete()
            self.assertEqual(Mannskap.objects.count(), 0)

            restore_backup(backup)

        self.assertEqual(Korps.objects.count(), 1)
        mannskap = Mannskap.objects.get()
        self.assertEqual(mannskap.navn, 'Kari Nordmann')
        self.assertEqual(mannskap.telefon, '99887766')
        self.assertEqual(mannskap.issi, '0401234',
                         'ISSI er nødnettsterminalens nummer og må overleve '
                         'som tekst — ledende nuller og alt.')
        self.assertEqual(mannskap.korps.navn, 'Testkorps')
        self.assertEqual(list(mannskap.kompetanser.values_list('navn', flat=True)),
                         ['AFØR'])

        post = Vaktpost.objects.get()
        self.assertEqual(post.mannskap_id, mannskap.pk)
        self.assertEqual(post.rolle.navn, 'Sjåfør')
        self.assertEqual(post.ressurs.vaktliste.vakt_id, self.vakt.pk,
                         'Lista må fortsatt peke på riktig vakt.')

    def test_kontokobling_strippes(self) -> None:
        """`Mannskap.user` lagres som brukernavn med natural_foreign. Er
        kontoen slettet, ville HELE gjenopprettingen feilet — altså akkurat når
        man trenger backupen. Koblingen settes på nytt av lederen."""
        bruker = CustomUser.objects.create_user(
            username='kari', password='x', must_change_password=False)
        self.mannskap.user = bruker
        self.mannskap.save()

        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='vaktliste', kind=KIND_MANUAL)
            raa = gzip.open(self.backup_dir / backup.filename, 'rb').read()

            bruker.delete()          # kontoen forsvinner før gjenopprettingen
            restore_backup(backup)   # skal ikke kaste

        for o in json.loads(raa):
            if o['model'] == 'vaktliste.mannskap':
                self.assertNotIn('user', o['fields'])
        self.assertIsNone(Mannskap.objects.get().user_id)

    def test_vaktpekeren_beholdes(self) -> None:
        """`Vaktliste.vakt` strippes ikke — den bærer hvilken vakt lista
        gjelder. Prisen er at portalfila må gjenopprettes først i en tom base."""
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='vaktliste', kind=KIND_MANUAL)
            raa = gzip.open(self.backup_dir / backup.filename, 'rb').read()
        for o in json.loads(raa):
            if o['model'] == 'vaktliste.vaktliste':
                self.assertEqual(o['fields']['vakt'], self.vakt.pk)
                break
        else:
            self.fail('Fant ingen vaktliste-rad i dumpen.')

    def test_slettelista_dekker_alt_som_dumpes(self) -> None:
        handler = get_handler('vaktliste')
        i_lista = {m.lower() for m in handler.get_restore_models()}
        with patch.dict(os.environ, {'BACKUP_DIR': str(self.backup_dir)}):
            backup = create_backup(slug='vaktliste', kind=KIND_MANUAL)
            raa = gzip.open(self.backup_dir / backup.filename, 'rb').read()
        i_dumpen = {o['model'].lower() for o in json.loads(raa)}
        self.assertEqual(i_dumpen - i_lista, set())
