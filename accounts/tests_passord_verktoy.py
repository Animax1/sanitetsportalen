"""Verktøy for å få folk inn igjen når ingen vet hva passordet er.

Utløst 29. aug. 2026: enhetskontoen `karmøy56` kom ikke inn med det
midlertidige passordet. Brukernavnet var lagret rent, ingenting i
kontotilstanden blokkerte, og `last_login_at` sto stille — altså traff ikke
passordet hashen. Da trengs to ting: et passord som ikke lar seg feillese, og
en vei til å sette et kjent et.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings

from accounts.models import CustomUser
from accounts.passord import (
    ALFABET, FORVEKSLINGSTEGN, LENGDE, lag_midlertidig_passord,
)


class MidlertidigPassordTests(TestCase):
    """Passordet leses av en skjerm og tastes et annet sted, ofte på telefon."""

    def test_alfabetet_utelater_forvekslingstegn(self):
        for tegn in FORVEKSLINGSTEGN:
            with self.subTest(tegn=tegn):
                self.assertNotIn(tegn, ALFABET)

    def test_genererte_passord_har_ingen_forvekslingstegn(self):
        """Hundre trekninger: sjansen for at et utelatt tegn slipper gjennom."""
        for _ in range(100):
            passord = lag_midlertidig_passord()
            self.assertFalse(set(passord) & set(FORVEKSLINGSTEGN), passord)

    def test_lengde_og_variasjon(self):
        """Vern mot at alfabetet krymper til noe trivielt ved en redigering."""
        self.assertEqual(len(lag_midlertidig_passord()), LENGDE)
        self.assertGreaterEqual(len(ALFABET), 50)
        self.assertGreater(len({lag_midlertidig_passord() for _ in range(50)}), 45)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SettPassordKommandoTests(TestCase):
    """`sett_passord` er veien inn når ingen vet hva passordet er."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='karmøy56', password='ukjent-for-alle', er_delt_konto=True)
        self.bruker.must_change_password = True
        self.bruker.save()

    def _kjor(self, *args):
        ut = StringIO()
        call_command('sett_passord', *args, stdout=ut, stderr=ut)
        return ut.getvalue()

    def test_setter_oppgitt_passord_og_kontoen_kommer_inn(self):
        self._kjor('karmøy56', '--passord', 'Vaktbil2026Trygt')
        c = Client()
        c.post('/accounts/login/',
               {'username': 'karmøy56', 'password': 'Vaktbil2026Trygt'})
        self.assertIn('_auth_user_id', c.session)

    def test_ascii_roemmet_navn_virker(self):
        """Railways ssh bærer ikke `ø` inn — utskriften fra sjekk_brukernavn gjør."""
        self._kjor(r'karmøy56', '--passord', 'Vaktbil2026Trygt')
        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.check_password('Vaktbil2026Trygt'))

    def test_fjerner_tvungen_bytte_som_standard(self):
        """Ellers lander kontoen på passordbytte-siden i stedet for portalen."""
        self._kjor('karmøy56', '--passord', 'Vaktbil2026Trygt')
        self.bruker.refresh_from_db()
        self.assertFalse(self.bruker.must_change_password)

    def test_kan_beholde_tvungen_bytte(self):
        self._kjor('karmøy56', '--passord', 'Vaktbil2026Trygt',
                   '--behold-tvungen-bytte')
        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.must_change_password)

    def test_nullstiller_kontolaas(self):
        """Den nye verdien skal ikke møte en sperre satt av forsøk på den gamle."""
        from datetime import timedelta

        from django.utils import timezone
        self.bruker.failed_login_attempts = 4
        self.bruker.locked_until = timezone.now() + timedelta(minutes=10)
        self.bruker.save()

        self._kjor('karmøy56', '--passord', 'Vaktbil2026Trygt')
        self.bruker.refresh_from_db()
        self.assertEqual(self.bruker.failed_login_attempts, 0)
        self.assertIsNone(self.bruker.locked_until)
        self.assertFalse(self.bruker.is_locked())

    def test_generert_passord_skrives_ut_og_virker(self):
        import re
        ut = self._kjor('karmøy56')
        treff = re.search(r'Passord: (\S+)', ut)
        self.assertIsNotNone(treff, ut)
        c = Client()
        c.post('/accounts/login/',
               {'username': 'karmøy56', 'password': treff.group(1)})
        self.assertIn('_auth_user_id', c.session)

    def test_ugyldig_passord_avvises(self):
        """Samme regler som skjemaet. Ellers får kontoen et passord den ikke
        kan endre uten å møte en feilmelding den ikke forårsaket."""
        with self.assertRaises(CommandError) as ctx:
            self._kjor('karmøy56', '--passord', '123')
        self.assertIn('ikke gyldig', str(ctx.exception))

    def test_ukjent_konto_gir_feil(self):
        with self.assertRaises(CommandError) as ctx:
            self._kjor('finnes.ikke', '--passord', 'Vaktbil2026Trygt')
        self.assertIn('Fant ingen konto', str(ctx.exception))

    def test_passordet_endres_ikke_ved_ugyldig_verdi(self):
        """Vern: en avvist kjøring skal ikke etterlate kontoen halvveis endret."""
        with self.assertRaises(CommandError):
            self._kjor('karmøy56', '--passord', '123')
        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.check_password('ukjent-for-alle'))
        self.assertTrue(self.bruker.must_change_password)
