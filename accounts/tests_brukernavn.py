"""Innlogging skal ikke bry seg om store og små bokstaver i brukernavnet.

Utløst av en konkret observasjon 23. aug. 2026: mobiltastatur setter
automatisk stor forbokstav i tekstfelt. En konto som heter `kari.nordmann`
blir da `Kari.nordmann` ved innlogging, og Postgres skiller på det. Brukeren
får «feil brukernavn eller passord» — uten noen antydning om hva som er galt,
fordi meldingen med vilje ikke røper hvilket av de to som feilet.

Det rammer nettopp de som ikke valgte brukernavnet sitt selv.
"""
import unicodedata

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class UfolsomInnloggingTests(TestCase):

    def setUp(self):
        cache.clear()
        self.bruker = CustomUser.objects.create_user(
            username='kari.nordmann', password='RiktigPass123!',
            role='bruker', must_change_password=False,
        )
        gi_standardtilgang(self.bruker, 'skriver')

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
            role='bruker', must_change_password=False,
        )
        gi_standardtilgang(dublett, 'leser')

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
            role='bruker', must_change_password=False,
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
        gi_standardtilgang(self.admin, 'admin')
        self.klient = Client()
        self.klient.force_login(self.admin)

    def test_brukernavn_lagres_med_smaa_bokstaver(self):
        self.klient.post(reverse('accounts:user_create'), {
            'username': '  Kari.Nordmann  ',
            'fullt_navn': 'Kari Nordmann',
            'email': 'kari@eksempel.no',
            'role': 'bruker',
            'kontotype': 'person',
            'metode': 'invitasjon',
        })
        self.assertTrue(
            CustomUser.objects.filter(username='kari.nordmann').exists(),
            'brukernavnet ble ikke normalisert til små bokstaver',
        )


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BrukernavnMedNorskeTegnTests(TestCase):
    """Innlogging skal tåle æ, ø og å — også limt inn fra et annet system.

    Bakgrunn: en konto med `ø` i navnet fikk ikke logget inn i prod. Feilen lot
    seg ikke reprodusere for `ø` alene, men to ekte feil i samme mekanikk ble
    funnet på veien, og begge er dekket her.
    """

    PASSORD = 'ForSvartHemmelig123'

    def _lag(self, navn):
        return CustomUser.objects.create_user(
            username=navn, password=self.PASSORD, must_change_password=False)

    def _logg_inn(self, navn):
        c = Client()
        c.post('/accounts/login/', {'username': navn, 'password': self.PASSORD})
        return '_auth_user_id' in c.session

    def test_alle_norske_tegn_kan_logge_inn(self):
        for navn in ('bjørn.rød', 'kåre.aas', 'næss.øye', 'ævind.åsmund'):
            with self.subTest(navn=navn):
                self._lag(navn)
                self.assertTrue(self._logg_inn(navn))

    def test_nfd_variant_kommer_inn(self):
        """`å` limt inn fra macOS er `a` + kombinerende ring, ikke ett tegn.

        Strengene ser identiske ut på skjermen. Uten normalisering finner
        databasen ingenting, og brukeren får «feil brukernavn eller passord»
        på et navn hun har kopiert ordrett.
        """
        self._lag('kåre.aas')
        nfd = unicodedata.normalize('NFD', 'kåre.aas')
        self.assertNotEqual(nfd, 'kåre.aas')      # vern: testen måler noe
        self.assertTrue(self._logg_inn(nfd))

    def test_nfc_variant_mot_nfd_lagret(self):
        """Motsatt vei: kontoen ble opprettet med en unormalisert streng."""
        CustomUser.objects.create_user(
            username=unicodedata.normalize('NFD', 'såre.øye'),
            password=self.PASSORD, must_change_password=False)
        self.assertTrue(self._logg_inn(unicodedata.normalize('NFC', 'såre.øye')))

    def test_store_norske_bokstaver_kommer_inn(self):
        """`iexact` case-folder ikke unicode på SQLite — og offline-modus er SQLite."""
        self._lag('bjørn.rød')
        for variant in ('BJØRN.RØD', 'Bjørn.Rød', 'bjØrn.rød'):
            with self.subTest(variant=variant):
                self.assertTrue(self._logg_inn(variant))

    def test_feil_passord_slipper_fortsatt_ikke_inn(self):
        """Vern: toleransen gjelder brukernavnet, ikke passordet."""
        self._lag('bjørn.rød')
        c = Client()
        c.post('/accounts/login/',
               {'username': 'BJØRN.RØD', 'password': 'feil-passord'})
        self.assertNotIn('_auth_user_id', c.session)

    def test_ukjent_brukernavn_slipper_ikke_inn(self):
        self._lag('bjørn.rød')
        self.assertFalse(self._logg_inn('bjørn.grønn'))

    def test_skjemaet_normaliserer_ved_oppretting(self):
        """Lagres én form, slipper oppslaget å lete etter flere."""
        from accounts.forms import AdminUserCreateForm
        felt = AdminUserCreateForm().fields
        self.assertIn('username', felt)

        from accounts.brukernavn import oppslagsnokkel
        self.assertEqual(
            oppslagsnokkel(unicodedata.normalize('NFD', 'KÅRE.Aas')),
            'kåre.aas')
