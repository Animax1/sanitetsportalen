"""§4.2 — `skriv_full` kan slette egne pasienter de siste 30 minuttene.

Vinduet treffer feilregistrering: en duplikat eller et feiltrykk som blokkerer
et pasientnummer og forstyrrer statistikken. Den som oppdager feilen er den som
registrerte, ikke en admin som kanskje ikke er på vakt.

Det er en **hard-delete som resirkulerer pasientnummeret**. Derfor er vinduet
smalt, og derfor er alt annet enn «egen, nettopp opprettet» fortsatt global
admin.
"""
import json
from datetime import timedelta

from django.test import Client, TestCase, override_settings

from patients.services import vakt_for_year
from django.utils import timezone

from accounts.models import CustomUser, ModulTilgang
from audit.models import AuditLog
from patients.models import Patient
from patients.services import SLETTEVINDU, kan_slette_selv


def _bruker(navn, nivaa='skriv_full', rolle='bruker'):
    b = CustomUser.objects.create_user(
        username=navn, password='x', role=rolle, must_change_password=False)
    if nivaa:
        ModulTilgang.objects.create(bruker=b, modul_slug='patients', nivaa=nivaa)
    return b


def _pasient(nr, oppretter, *, alder=timedelta(0)):
    """Pasient med en CREATE-rad i auditloggen, slik viewet lager den."""
    p = Patient.objects.create(pasientnummer=nr, vakt=vakt_for_year(2026))
    AuditLog.objects.filter(table_name='patients_patient', record_id=p.pk).delete()
    rad = AuditLog.objects.create(
        table_name='patients_patient', record_id=p.pk, action='CREATE',
        new_value=str(nr), user=oppretter,
    )
    # auto_now_add lar seg ikke sette ved create.
    AuditLog.objects.filter(pk=rad.pk).update(created_at=timezone.now() - alder)
    return p


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KanSletteSelvTests(TestCase):
    """Regelen isolert, uten HTTP."""

    def setUp(self):
        self.bruker = _bruker('sletter')

    def test_egen_fersk_pasient_kan_slettes(self):
        self.assertTrue(kan_slette_selv(self.bruker, _pasient(1, self.bruker)))

    def test_egen_gammel_pasient_kan_ikke(self):
        gammel = _pasient(2, self.bruker, alder=SLETTEVINDU + timedelta(minutes=1))
        self.assertFalse(kan_slette_selv(self.bruker, gammel))

    def test_grensen_er_inklusiv(self):
        """Nøyaktig på vinduet skal fortsatt gå — ellers er grensen tilfeldig."""
        paa_grensen = _pasient(3, self.bruker, alder=SLETTEVINDU - timedelta(seconds=1))
        self.assertTrue(kan_slette_selv(self.bruker, paa_grensen))

    def test_andres_pasient_kan_ikke(self):
        annen = _bruker('annen')
        self.assertFalse(kan_slette_selv(self.bruker, _pasient(4, annen)))

    def test_uten_create_rad_nektes(self):
        """Fail-closed.

        Raden kan mangle for pasienter opprettet før auditloggen, eller for
        importerte rader. «Vet ikke hvem som opprettet den» skal ikke bety
        «hvem som helst».
        """
        p = Patient.objects.create(pasientnummer=5, vakt=vakt_for_year(2026))
        AuditLog.objects.filter(table_name='patients_patient', record_id=p.pk).delete()
        self.assertFalse(kan_slette_selv(self.bruker, p))

    def test_create_rad_uten_bruker_nektes(self):
        """Importerte rader har CREATE-rad, men ingen `user`."""
        p = Patient.objects.create(pasientnummer=6, vakt=vakt_for_year(2026))
        AuditLog.objects.filter(table_name='patients_patient', record_id=p.pk).delete()
        AuditLog.objects.create(
            table_name='patients_patient', record_id=p.pk, action='CREATE',
            new_value='6', user=None,
        )
        self.assertFalse(kan_slette_selv(self.bruker, p))

    def test_les_kan_ikke_slette_selv_sin_egen(self):
        leser = _bruker('leser_sletter', nivaa='les')
        self.assertFalse(kan_slette_selv(leser, _pasient(7, leser)))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SlettEndepunktTests(TestCase):
    """Hele veien gjennom HTTP."""

    def _slett(self, bruker, pasient):
        c = Client()
        c.force_login(bruker)
        return c.delete(f'/pasienter/api/patients/{pasient.pk}/',
                        data=json.dumps({'confirm': True}),
                        content_type='application/json')

    def test_egen_fersk_pasient_slettes(self):
        bruker = _bruker('ep_egen')
        p = _pasient(1, bruker)
        self.assertEqual(self._slett(bruker, p).status_code, 200)
        self.assertFalse(Patient.objects.filter(pk=p.pk).exists())

    def test_andres_pasient_gir_403_og_beholdes(self):
        bruker = _bruker('ep_meg')
        annen = _bruker('ep_annen')
        p = _pasient(2, annen)
        self.assertEqual(self._slett(bruker, p).status_code, 403)
        self.assertTrue(Patient.objects.filter(pk=p.pk).exists(),
                        'et avvist kall skal ikke ha slettet noe')

    def test_gammel_egen_pasient_gir_403(self):
        bruker = _bruker('ep_gammel')
        p = _pasient(3, bruker, alder=SLETTEVINDU + timedelta(minutes=1))
        self.assertEqual(self._slett(bruker, p).status_code, 403)

    def test_admin_sletter_uansett(self):
        """Global admin er ikke begrenset av vinduet."""
        admin = _bruker('ep_admin', nivaa=None, rolle='admin')
        annen = _bruker('ep_annen2')
        p = _pasient(4, annen, alder=timedelta(days=30))
        self.assertEqual(self._slett(admin, p).status_code, 200)
