"""Tester for invitasjonsflyten.

Beslutningene som testes er tatt i `docs/BESLUTNING_BRUKERE_OG_EPOST.md` §5 og
§7, med de tre siste avklart 23. aug. 2026: lenken varer tre døgn, brukeren
sendes til innlogging etterpå, og midlertidig passord beholdes som reserve.

Den viktigste egenskapen er at lenken er **enbruks**. Den har ingen tabell som
kan inspiseres, så den må testes gjennom oppførselen: samme lenke to ganger
skal virke første gang og ikke andre.
"""
from unittest.mock import patch

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.invitasjon import (
    LEVETID_SEKUNDER, kan_inviteres, lag_token, les_token,
)
from accounts.models import CustomUser


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InvitasjonTokenTests(TestCase):
    """Tokenet for seg, uten HTTP i veien."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='invitert', password='MidlertidigPass1!',
            role='read_write', email='invitert@eksempel.no',
        )

    def test_token_peker_paa_riktig_bruker(self):
        self.assertEqual(les_token(lag_token(self.bruker)), self.bruker)

    def test_token_doer_naar_passordet_settes(self):
        """Kjernen i at lenken er enbruks.

        Avtrykket i tokenet er en hash av passord-hashen. Settes et passord,
        endres den, og avtrykket slutter å stemme — uten at noe måtte huske å
        rydde opp.
        """
        token = lag_token(self.bruker)
        self.assertIsNotNone(les_token(token))

        self.bruker.set_password('EtHeltAnnetPass1!')
        self.bruker.save()

        self.assertIsNone(les_token(token))

    def test_utloept_token_avvises(self):
        """Levetiden håndheves av signaturens tidsstempel.

        Enklere å sette levetiden til null enn å flytte klokka: `unsign()`
        regner alderen ut fra tidsstemplet i tokenet, så et token som er
        eldre enn `max_age` avvises uansett hvordan det ble gammelt.
        """
        token = lag_token(self.bruker)
        with patch('accounts.invitasjon.LEVETID_SEKUNDER', -1):
            self.assertIsNone(les_token(token))

    def test_tuklet_token_avvises(self):
        token = lag_token(self.bruker)
        self.assertIsNone(les_token(token[:-1] + ('x' if token[-1] != 'x' else 'y')))

    def test_frosset_konto_avvises(self):
        """En frosset konto skal ikke kunne tas i bruk via en gammel lenke."""
        token = lag_token(self.bruker)
        self.bruker.is_active = False
        self.bruker.save()
        self.assertIsNone(les_token(token))

    def test_delt_konto_kan_ikke_inviteres(self):
        """Utelates på flagget, ikke på «har e-post».

        Ellers slår regelen feil den dagen noen legger en kontakt-e-post på en
        bil-konto — og da er lenken en lateral vei inn i systemet.
        """
        bil = CustomUser.objects.create_user(
            username='bil3', password='pass', role='read_write',
            er_delt_konto=True,
        )
        self.assertFalse(kan_inviteres(bil))

        bil.email = 'vakt@eksempel.no'
        bil.save()
        self.assertFalse(kan_inviteres(bil))

    def test_levetiden_er_tre_dogn(self):
        """Låst mot beslutningen 23. aug. 2026."""
        self.assertEqual(LEVETID_SEKUNDER, 3 * 24 * 60 * 60)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InvitasjonFlytTests(TestCase):
    """Hele veien: admin oppretter, brukeren setter passord, logger inn."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='sjef', password='AdminPass123!', role='admin',
            must_change_password=False,
        )
        self.client = Client()
        self.client.force_login(self.admin)
        mail.outbox.clear()

    def _opprett(self, **felt):
        data = {
            'username': 'nyfrivillig',
            'fullt_navn': 'Kari Nordmann',
            'email': 'kari@eksempel.no',
            'role': 'read_write',
            'metode': 'invitasjon',
        }
        data.update(felt)
        return self.client.post(reverse('accounts:user_create'), data)

    def test_invitasjon_sendes_og_kontoen_har_ikke_passord(self):
        resp = self._opprett()
        self.assertEqual(resp.status_code, 302)

        ny = CustomUser.objects.get(username='nyfrivillig')
        self.assertFalse(ny.has_usable_password(),
                         'kontoen skal ikke kunne logges inn på før lenken er brukt')
        self.assertFalse(ny.must_change_password,
                         'brukeren velger passordet selv, og skal ikke tvinges '
                         'gjennom passordbytte etterpå')

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('kari@eksempel.no', mail.outbox[0].to)
        self.assertIn('Kari Nordmann', mail.outbox[0].body)

    def test_brukeren_setter_passord_og_sendes_til_innlogging(self):
        self._opprett()
        ny = CustomUser.objects.get(username='nyfrivillig')

        anonym = Client()
        url = reverse('accounts:invitasjon', args=[lag_token(ny)])
        self.assertEqual(anonym.get(url).status_code, 200)

        svar = anonym.post(url, {
            'new_password1': 'MittEgetPass123!',
            'new_password2': 'MittEgetPass123!',
        })
        self.assertRedirects(svar, reverse('accounts:login'),
                             fetch_redirect_response=False)

        ny.refresh_from_db()
        self.assertTrue(ny.check_password('MittEgetPass123!'))
        self.assertFalse(ny.must_change_password)

    def test_lenken_virker_kun_en_gang(self):
        """Akseptansen for at tokenet er enbruks, hele veien gjennom HTTP."""
        self._opprett()
        ny = CustomUser.objects.get(username='nyfrivillig')
        url = reverse('accounts:invitasjon', args=[lag_token(ny)])

        anonym = Client()
        anonym.post(url, {
            'new_password1': 'MittEgetPass123!',
            'new_password2': 'MittEgetPass123!',
        })

        andre = anonym.post(url, {
            'new_password1': 'EnHeltAnnenTing1!',
            'new_password2': 'EnHeltAnnenTing1!',
        })
        self.assertEqual(andre.status_code, 400)

        ny.refresh_from_db()
        self.assertTrue(ny.check_password('MittEgetPass123!'),
                        'det andre forsøket skal ikke ha overskrevet passordet')

    def test_ugyldig_lenke_gir_samme_side_uansett_grunn(self):
        """Ingen kontoenumerering: én melding for alle avvisningsgrunner."""
        svar = Client().get(reverse('accounts:invitasjon', args=['tull']))
        self.assertEqual(svar.status_code, 400)
        self.assertNotContains(svar, 'nyfrivillig', status_code=400)

    def test_delt_konto_faar_midlertidig_passord_ikke_invitasjon(self):
        resp = self._opprett(
            username='bil7', fullt_navn='', email='', er_delt_konto='on',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

        bil = CustomUser.objects.get(username='bil7')
        self.assertTrue(bil.has_usable_password())
        self.assertTrue(bil.must_change_password)

    def test_delt_konto_nekter_epost_og_navn(self):
        """Regelen håndheves i valideringen, ikke bare i grensesnittet."""
        resp = self._opprett(
            username='bil8', fullt_navn='Noen Navnesen',
            email='bil8@eksempel.no', er_delt_konto='on',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='bil8').exists())
        self.assertContains(resp, 'delt konto')

    def test_reserven_virker_naar_epost_feiler(self):
        """Kontoen skal finnes selv om utsendingen ryker.

        Admin får en advarsel og kan sende på nytt eller sette passord
        manuelt — i stedet for en 500-side og tvil om brukeren ble opprettet.
        """
        with patch('django.core.mail.EmailMessage.send',
                   side_effect=OSError('SMTP nede')):
            resp = self._opprett(username='uheldig')

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CustomUser.objects.filter(username='uheldig').exists())

    def test_admin_kan_sende_invitasjon_paa_nytt(self):
        self._opprett()
        ny = CustomUser.objects.get(username='nyfrivillig')
        mail.outbox.clear()

        svar = self.client.post(
            reverse('accounts:user_detail', args=[ny.pk]),
            {'action': 'send_invitasjon'},
        )
        self.assertEqual(svar.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
