"""Innlogging skal ikke bry seg om store og små bokstaver i brukernavnet.

Utløst av en konkret observasjon 23. aug. 2026: mobiltastatur setter
automatisk stor forbokstav i tekstfelt. En konto som heter `kari.nordmann`
blir da `Kari.nordmann` ved innlogging, og Postgres skiller på det. Brukeren
får «feil brukernavn eller passord» — uten noen antydning om hva som er galt,
fordi meldingen med vilje ikke røper hvilket av de to som feilet.

Det rammer nettopp de som ikke valgte brukernavnet sitt selv.
"""
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class UfolsomInnloggingTests(TestCase):

    def setUp(self):
        cache.clear()
        self.bruker = CustomUser.objects.create_user(
            username='kari.nordmann', password='RiktigPass123!',
            role='read_write', must_change_password=False,
        )

    def test_stor_forbokstav_slipper_inn(self):
        """Selve tilfellet fra mobiltastaturet."""
        self.assertEqual(
            authenticate(username='Kari.nordmann', password='RiktigPass123!'),
            self.bruker,
        )

    def test_alle_store_bokstaver_slipper_inn(self):
        self.assertEqual(
            authenticate(username='KARI.NORDMANN', password='RiktigPass123!'),
            self.bruker,
        )

    def test_feil_passord_slipper_ikke_inn(self):
        """Ufølsomheten gjelder brukernavnet, ikke passordet."""
        self.assertIsNone(
            authenticate(username='Kari.Nordmann', password='FeilPass123!')
        )

    def test_ukjent_brukernavn_gir_none(self):
        self.assertIsNone(
            authenticate(username='finnes.ikke', password='RiktigPass123!')
        )

    def test_frosset_konto_slipper_ikke_inn(self):
        self.bruker.is_active = False
        self.bruker.save()
        self.assertIsNone(
            authenticate(username='KARI.NORDMANN', password='RiktigPass123!')
        )

    def test_tvetydighet_krever_noeyaktig_treff(self):
        """To kontoer som kun skiller seg på store bokstaver skal aldri forveksles.

        Situasjonen kan finnes i data som er eldre enn normaliseringen. Da er
        riktig oppførsel å kreve nøyaktig treff — ikke å gjette. En bruker som
        må skrive navnet sitt nøyaktig er et irritasjonsmoment; feil konto er
        et sikkerhetsbrudd.
        """
        dublett = CustomUser.objects.create_user(
            username='Kari.Nordmann', password='AnnetPass123!',
            role='read_only', must_change_password=False,
        )

        self.assertEqual(
            authenticate(username='Kari.Nordmann', password='AnnetPass123!'),
            dublett,
        )
        self.assertEqual(
            authenticate(username='kari.nordmann', password='RiktigPass123!'),
            self.bruker,
        )
        # En skrivemåte som ikke matcher noen av dem nøyaktig slipper ingen inn.
        self.assertIsNone(
            authenticate(username='KARI.NORDMANN', password='RiktigPass123!')
        )

    def test_innlogging_gjennom_skjemaet_virker(self):
        """Hele veien gjennom `login_view`, ikke bare backenden."""
        svar = Client().post(reverse('accounts:login'), {
            'username': 'Kari.Nordmann',
            'password': 'RiktigPass123!',
        })
        self.assertEqual(svar.status_code, 302)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class RateLimitNokkelTests(TestCase):
    """Bøtta må normaliseres på samme måte som oppslaget.

    Ellers gir «kari», «Kari» og «KARI» hver sin teller mot én og samme konto,
    og en angriper mangedobler forsøksbudsjettet sitt ved å variere store
    bokstaver — mot en konto som nå godtar alle variantene.
    """

    def setUp(self):
        cache.clear()
        CustomUser.objects.create_user(
            username='kari.nordmann', password='RiktigPass123!',
            role='read_write', must_change_password=False,
        )

    def test_store_bokstaver_deler_botte_med_smaa(self):
        klient = Client()
        varianter = ['kari.nordmann', 'Kari.Nordmann', 'KARI.NORDMANN']

        statuser = []
        for i in range(15):
            statuser.append(klient.post(reverse('accounts:login'), {
                'username': varianter[i % 3],
                'password': 'FeilPassord123!',
            }).status_code)

        self.assertIn(
            429, statuser,
            'grensen ble aldri nådd — variasjon i store bokstaver gir '
            'fortsatt hver sin bøtte',
        )


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BrukernavnNormaliseringTests(TestCase):
    """Nye kontoer lagres med små bokstaver."""

    def setUp(self):
        cache.clear()
        self.admin = CustomUser.objects.create_user(
            username='sjef', password='AdminPass123!', role='admin',
            must_change_password=False,
        )
        self.klient = Client()
        self.klient.force_login(self.admin)

    def test_brukernavn_lagres_med_smaa_bokstaver(self):
        self.klient.post(reverse('accounts:user_create'), {
            'username': '  Kari.Nordmann  ',
            'fullt_navn': 'Kari Nordmann',
            'email': 'kari@eksempel.no',
            'role': 'read_write',
            'metode': 'invitasjon',
        })
        self.assertTrue(
            CustomUser.objects.filter(username='kari.nordmann').exists(),
            'brukernavnet ble ikke normalisert til små bokstaver',
        )
