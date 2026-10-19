"""Billetten for innlogging i kartet fra KO (`core/kartkobling.py`, 19. okt. 2026).

`docs/PLAN_FELLES_INNLOGGING.md`. Kartet sjekker den i `konto/portalinnlogging.py`; formen er
låst av samme testvektor i begge repoene.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings

from core import kartkobling

NOKKEL = 'k' * 64

#: Samme verdi som `TESTVEKTOR` i kartets `konto/tests/test_fra_portalen.py`. Endres formen på
#: én side, er testen rød på begge — og da er det endringen som er feil, ikke vektoren.
TESTVEKTOR = (
    'eyJhdWQiOiJrYXJ0LnNhbml0ZXQubmV0IiwiYnJ1a2VyIjo0MiwiZXhwIjoxNzYwMDAwMDYwLCJpYXQiOjE3NjAwMDAw'
    'MDAsImp0aSI6IjAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmIiwibmF2biI6IkthcmkgTm9yZG1hbm4iLCJw'
    'b3J0YWwiOiJzdGFuZGFyZCIsInNrcml2Ijp0cnVlfQ'
    '.62db04a292c27e123363392fa9e1d3fe6ae380a3ea7a45a73a5f8b3d7bccf9cd'
)


def les_billett(billett: str, nokkel: str = NOKKEL) -> dict:
    """Det kartet gjør, i kortform: sjekk signaturen og les innholdet."""
    innhold, signatur = billett.split('.')
    venter = hmac.new(nokkel.encode(), b'kartinnlogging.v1.' + innhold.encode(),
                      hashlib.sha256).hexdigest()
    assert hmac.compare_digest(venter, signatur), 'signaturen stemmer ikke'
    return json.loads(base64.urlsafe_b64decode(innhold + '=' * (-len(innhold) % 4)))


@override_settings(KART_URL='https://kart.sanitet.net', KART_INNLOGGING_NOKKEL=NOKKEL,
                   KART_HMAC_NOKKEL='p' * 64)
class BillettenTests(SimpleTestCase):

    def test_testvektoren(self):
        self.assertEqual(kartkobling.lag_billett(
            bruker_id=42, navn='Kari Nordmann', portal='standard', skriv=True,
            naa=1760000000, jti='0123456789abcdef0123456789abcdef'), TESTVEKTOR)

    def test_innholdet(self):
        data = les_billett(kartkobling.lag_billett(
            bruker_id=7, navn='Ola', portal='brann', skriv=False, naa=1000))
        self.assertEqual(data['aud'], 'kart.sanitet.net', 'vertsnavnet, uten skjema og sti')
        self.assertEqual((data['bruker'], data['navn'], data['portal'], data['skriv']),
                         (7, 'Ola', 'brann', False))
        self.assertEqual(data['exp'] - data['iat'], kartkobling.INNLOGGING_LEVETID_S)
        self.assertRegex(data['jti'], r'^[0-9a-f]{32}$')

    def test_hver_billett_har_sitt_eget_nummer(self):
        a, b = (les_billett(kartkobling.lag_billett(bruker_id=1, navn='A', portal='s', skriv=True))
                for _ in range(2))
        self.assertNotEqual(a['jti'], b['jti'])

    def test_posisjonsnokkelen_signerer_ikke_innlogging(self):
        """Egen nøkkel: en lekket posisjonsnøkkel skal ikke kunne logge inn."""
        billett = kartkobling.lag_billett(bruker_id=1, navn='A', portal='s', skriv=True)
        with self.assertRaises(AssertionError):
            les_billett(billett, nokkel='p' * 64)

    def test_satt_opp_krever_adresse_og_nokkel(self):
        self.assertTrue(kartkobling.innlogging_satt_opp())
        with self.settings(KART_INNLOGGING_NOKKEL=''):
            self.assertFalse(kartkobling.innlogging_satt_opp())
        with self.settings(KART_URL=''):
            self.assertFalse(kartkobling.innlogging_satt_opp())

    def test_adressene(self):
        with self.settings(KART_URL='https://testkart.sanitet.net/'):
            self.assertEqual(kartkobling.innlogging_url(),
                             'https://testkart.sanitet.net/konto/fra-portalen/')
            self.assertEqual(kartkobling.kart_opprinnelse(), 'https://testkart.sanitet.net')


@override_settings(KART_URL='https://kart.sanitet.net', KART_INNLOGGING_NOKKEL=NOKKEL)
class BryterenTests(TestCase):
    """Admins bryter i kortet «Kartet» på `/admin/innstillinger/`. Av som standard."""

    def setUp(self):
        from core.kart_innstillinger import KartInnstillinger
        self.h = KartInnstillinger()

    def test_av_som_standard(self):
        self.assertFalse(kartkobling.innlogging_paa())

    def test_paa_og_av_gjennom_innstillingene(self):
        self.h.lagre(self.h.valider({'kart_innlogging_sendt': '1', 'kart_innlogging': '1'}))
        self.assertTrue(kartkobling.innlogging_paa())
        self.h.lagre(self.h.valider({'kart_innlogging_sendt': '1'}))
        self.assertFalse(kartkobling.innlogging_paa(), 'avkrysset bort er av')

    def test_fravaerende_er_behold(self):
        self.h.lagre(self.h.valider({'kart_innlogging_sendt': '1', 'kart_innlogging': '1'}))
        self.h.lagre(self.h.valider({}))
        self.assertTrue(kartkobling.innlogging_paa())
        self.h.lagre(self.h.valider({'kart_delt_posisjon': '20'}))
        self.assertTrue(kartkobling.innlogging_paa(), 'et annet felt i kortet rører ikke bryteren')

    def test_pa_uten_nokkel_er_av(self):
        self.h.lagre(self.h.valider({'kart_innlogging_sendt': '1', 'kart_innlogging': '1'}))
        with self.settings(KART_INNLOGGING_NOKKEL=''):
            self.assertFalse(kartkobling.innlogging_paa())

    def test_feil_i_et_annet_felt_stopper_ogsa_bryteren(self):
        with self.assertRaises(ValidationError):
            self.h.valider({'kart_innlogging_sendt': '1', 'kart_innlogging': '1',
                            'kart_delt_posisjon': 'x'})

    def test_bryteren_er_systemets_ikke_portalens(self):
        """Tom `portalfelt`: moderatoren får ikke sende den, bare admin."""
        self.assertNotIn('kart_innlogging', self.h.portalfelt)

    def test_kortet_tegner_bryteren_og_sier_fra_uten_nokkel(self):
        html = render_to_string(self.h.mal, self.h.kontekst())
        self.assertIn('name="kart_innlogging"', html)
        self.assertIn('name="kart_innlogging_sendt"', html)
        self.assertNotIn('KART_INNLOGGING_NOKKEL', html)
        with self.settings(KART_INNLOGGING_NOKKEL=''):
            self.assertIn('KART_INNLOGGING_NOKKEL', render_to_string(self.h.mal, self.h.kontekst()))
