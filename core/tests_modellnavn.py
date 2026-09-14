"""Navnetabellen for modeller som flytter mellom apper (14. sep. 2026).

**Hvorfor dette finnes før det trengs.** En backupfil bærer modellnavnet:
`dumpdata` skriver `{"model": "patients.appsetting", ...}`, og `loaddata` slår
navnet opp i app-registeret. Flytter modellen til `core`, svarer en eldre fil
«Unknown model» i stedet for å laste — og modulfilene ligger 730 dager hos
Scaleway.

Tabellen er tom i dag, så mekanismen har ingen virkning ennå. Testene her
kjører den derfor mot en **oppdiktet** flytting: en fil som påstår at pasienter
hører til en app som aldri har eksistert, og en tabell som peker den tilbake.
Går det, virker røret den dagen `docs/PLAN_FLYTTING_TIL_CORE.md` fase 2 fyller
det med de ekte radene.

Alternativet — å skrive testen samtidig som flyttingen — ville gjort deployen
som flytter modellene til den samme som først prøver oversettelsen. Og feiler
den, viser det seg den dagen noen gjenoppretter.
"""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from core.backup import (
    GAMLE_MODELLNAVN,
    KIND_MANUAL,
    create_backup,
    oversett_modellnavn,
    registrer_alle_moduler,
    restore_backup,
)

#: Den oppdiktede flyttingen testene bruker. Appen har aldri eksistert, så
#: ingenting i basen kan tilfeldigvis svare på navnet.
PRØVETABELL = {'gammelapp.patient': 'patients.patient'}

TEST_BACKUP_DIR = Path('/tmp/test-backups-modellnavn')


class TabellenInneholderFlyttingeneTests(SimpleTestCase):
    """Hver rad i tabellen skal peke på en modell som finnes i dag.

    En rad med skrivefeil i høyresida er verre enn ingen rad: fila oversettes,
    og feiler så i `loaddata` med et navn ingen har sett før. Og en rad der
    venstresida fortsatt finnes, betyr at flyttingen ikke er gjennomført.
    """

    def test_de_to_flyttede_modellene_star_der(self) -> None:
        """14. sep. 2026, fase 2. Fjernes en av dem, blir eldre offsite-filer
        uleselige i stillhet — og de lever 730 dager."""
        self.assertEqual(GAMLE_MODELLNAVN, {
            'patients.appsetting': 'core.appsetting',
            'patients.backup': 'core.backup',
        })

    def test_hoyresida_peker_pa_modeller_som_finnes(self) -> None:
        from django.apps import apps as django_apps

        for gammelt, nytt in GAMLE_MODELLNAVN.items():
            with self.subTest(gammelt=gammelt):
                django_apps.get_model(nytt)      # kaster LookupError ved feil

    def test_venstresida_finnes_ikke_lenger(self) -> None:
        """Står begge, har ingenting flyttet — og oversettelsen ville byttet et
        navn som fortsatt er gyldig."""
        from django.apps import apps as django_apps

        for gammelt in GAMLE_MODELLNAVN:
            with self.subTest(gammelt=gammelt):
                with self.assertRaises(LookupError):
                    django_apps.get_model(gammelt)

    def test_uten_oppslag_returneres_bytene_urort(self) -> None:
        """Identitet, ikke bare likhet: den raske veien skal ikke parse JSON-en
        og bygge den opp igjen. En hel databasefil er ikke liten."""
        raa = b'[{"model": "patients.patient", "pk": 1, "fields": {}}]'
        self.assertIs(oversett_modellnavn(raa), raa)

    def test_en_ekte_gammel_fil_oversettes(self) -> None:
        """Uten `patch.dict` — den ekte tabellen, slik den står i dag."""
        raa = b'[{"model": "patients.appsetting", "pk": "aktiv_vakt_id", "fields": {}}]'
        ut = json.loads(oversett_modellnavn(raa).decode('utf-8'))
        self.assertEqual(ut[0]['model'], 'core.appsetting')

    def test_fil_uten_treff_rores_ikke_selv_med_tabell(self) -> None:
        raa = b'[{"model": "oppdrag.oppdrag", "pk": 1, "fields": {}}]'
        with patch.dict(GAMLE_MODELLNAVN, PRØVETABELL, clear=True):
            self.assertIs(oversett_modellnavn(raa), raa)


class OversettelsenTests(SimpleTestCase):
    """Selve byttet, kjørt mot den oppdiktede flyttingen."""

    def _oversett(self, objekter):
        raa = json.dumps(objekter).encode('utf-8')
        with patch.dict(GAMLE_MODELLNAVN, PRØVETABELL, clear=True):
            return json.loads(oversett_modellnavn(raa).decode('utf-8'))

    def test_gammelt_navn_byttes(self) -> None:
        ut = self._oversett([{'model': 'gammelapp.patient', 'pk': 1, 'fields': {}}])
        self.assertEqual(ut[0]['model'], 'patients.patient')

    def test_andre_modeller_i_samme_fil_star_urort(self) -> None:
        """En modulfil har flere modeller, og bare én av dem flyttet."""
        ut = self._oversett([
            {'model': 'gammelapp.patient', 'pk': 1, 'fields': {}},
            {'model': 'patients.forstehjelper', 'pk': 2, 'fields': {}},
        ])
        self.assertEqual([o['model'] for o in ut],
                         ['patients.patient', 'patients.forstehjelper'])

    def test_feltene_folger_med(self) -> None:
        """Det er etiketten som byttes, ikke innholdet."""
        ut = self._oversett([{'model': 'gammelapp.patient', 'pk': 7,
                              'fields': {'problemstilling': 'Kutt'}}])
        self.assertEqual(ut[0]['pk'], 7)
        self.assertEqual(ut[0]['fields'], {'problemstilling': 'Kutt'})

    def test_store_bokstaver_i_fila_treffer_ogsa(self) -> None:
        """`dumpdata` skriver små bokstaver, men en fil kan være håndredigert
        under en gjenoppretting — og da er det verre å tie enn å treffe."""
        ut = self._oversett([{'model': 'GammelApp.Patient', 'pk': 1, 'fields': {}}])
        self.assertEqual(ut[0]['model'], 'patients.patient')

    def test_odelagt_fil_sendes_videre_urort(self) -> None:
        """Fila skal feile i `loaddata`, med den feilmeldingen — ikke her, med
        en annen. En oversetter som spiser feilen gjør den vanskeligere å lese."""
        raa = b'{"gammelapp.patient": "ikke en liste"}'
        with patch.dict(GAMLE_MODELLNAVN, PRØVETABELL, clear=True):
            self.assertIs(oversett_modellnavn(raa), raa)

        raa = b'gammelapp.patient men ikke JSON'
        with patch.dict(GAMLE_MODELLNAVN, PRØVETABELL, clear=True):
            self.assertIs(oversett_modellnavn(raa), raa)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class GammelFilLastesTests(TestCase):
    """Hele veien: en fil i gammel form gjennom `restore_backup`.

    Dette er prøven som svarer på om tabellen virker der den skal virke. De
    andre måler funksjonen; denne måler gjenopprettingen.
    """

    def setUp(self) -> None:
        registrer_alle_moduler()
        TEST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for f in TEST_BACKUP_DIR.glob('*'):
            if f.is_file():
                f.unlink(missing_ok=True)
        self.miljo = patch.dict(os.environ, {'BACKUP_DIR': str(TEST_BACKUP_DIR)})

    def test_fil_med_gammelt_modellnavn_gjenopprettes(self) -> None:
        from patients.models import Patient
        from core.vakt import vakt_for_year

        vakt = vakt_for_year(2026)
        Patient.objects.create(pasientnummer=42, vakt=vakt,
                               problemstilling='Før flyttingen')

        with self.miljo:
            backup = create_backup(slug='patients', kind=KIND_MANUAL)

        # Skriv fila om til den «gamle» formen, som om pasienten ble dumpet
        # av en versjon der modellen bodde et annet sted.
        sti = TEST_BACKUP_DIR / backup.filename
        objekter = json.loads(gzip.open(sti, 'rb').read())
        antall = 0
        for objekt in objekter:
            if objekt['model'] == 'patients.patient':
                objekt['model'] = 'gammelapp.patient'
                antall += 1
        self.assertEqual(antall, 1, 'testen skrev ikke om noen rad')
        with gzip.open(sti, 'wb') as f:
            f.write(json.dumps(objekter).encode('utf-8'))

        Patient.objects.all().delete()

        with self.miljo, patch.dict(GAMLE_MODELLNAVN, PRØVETABELL, clear=True):
            restore_backup(backup)

        self.assertEqual(Patient.objects.get().pasientnummer, 42,
                         'Pasienten kom ikke tilbake fra fila i gammel form.')

    def test_uten_tabellen_feiler_den_samme_fila(self) -> None:
        """Motprøven. Uten den ville testen over bestått selv om oversettelsen
        aldri ble kalt — `loaddata` ville jo lastet en fil den forsto."""
        from django.core.serializers.base import DeserializationError
        from patients.models import Patient
        from core.vakt import vakt_for_year

        vakt = vakt_for_year(2026)
        Patient.objects.create(pasientnummer=42, vakt=vakt, problemstilling='X')

        with self.miljo:
            backup = create_backup(slug='patients', kind=KIND_MANUAL)

        sti = TEST_BACKUP_DIR / backup.filename
        objekter = json.loads(gzip.open(sti, 'rb').read())
        for objekt in objekter:
            if objekt['model'] == 'patients.patient':
                objekt['model'] = 'gammelapp.patient'
        with gzip.open(sti, 'wb') as f:
            f.write(json.dumps(objekter).encode('utf-8'))

        with self.miljo, patch.dict(GAMLE_MODELLNAVN, {}, clear=True):
            with self.assertRaises(DeserializationError) as ctx:
                restore_backup(backup)
        self.assertIn('Invalid model identifier: gammelapp.patient',
                      str(ctx.exception))

        # Og gjenopprettingen er rullet tilbake — pasienten står som før.
        self.assertEqual(Patient.objects.get().pasientnummer, 42)
