"""Tester for selvbetjent passord-reset — de sju beslutningene i §6.

Den vanskeligste egenskapen å teste er §6.7: at svaret er identikt enten
adressen finnes eller ikke. Den kan ikke verifiseres ved å se på én respons —
den må sammenlignes mot den andre.
"""
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from accounts.passord_reset import (
    LEVETID_SEKUNDER, finn_bruker, kan_resettes, lag_token, les_token,
)
from accounts.test_helpers import gi_standardtilgang


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ResetTokenTests(TestCase):

    def setUp(self):
        cache.clear()
        self.bruker = CustomUser.objects.create_user(
            username='kari.nordmann', password='GammeltPass123!',
            role='read_write', email='kari@eksempel.no',
            must_change_password=False,
        )
        gi_standardtilgang(self.bruker)

    def test_levetiden_er_en_time(self):
        """Låst mot beslutningen 23. aug. 2026."""
        self.assertEqual(LEVETID_SEKUNDER, 60 * 60)

    def test_token_doer_naar_passordet_settes(self):
        token = lag_token(self.bruker)
        self.assertIsNotNone(les_token(token))

        self.bruker.set_password('NyttPass123!')
        self.bruker.save()
        self.assertIsNone(les_token(token))

    def test_utloept_token_avvises(self):
        token = lag_token(self.bruker)
        with patch('accounts.passord_reset.LEVETID_SEKUNDER', -1):
            self.assertIsNone(les_token(token))

    def test_invitasjonstoken_virker_ikke_som_reset(self):
        """Egen salt: tre døgns levetid skal ikke kunne brukes der én time gjelder."""
        from accounts.invitasjon import lag_token as lag_invitasjon
        self.assertIsNone(les_token(lag_invitasjon(self.bruker)))

    def test_reset_token_virker_ikke_som_invitasjon(self):
        from accounts.invitasjon import les_token as les_invitasjon
        self.assertIsNone(les_invitasjon(lag_token(self.bruker)))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HvemKanResettesTests(TestCase):
    """§6.1: delte kontoer utelates, på flagget."""

    def setUp(self):
        cache.clear()

    def _lag(self, **felt):
        data = {
            'username': 'noen', 'password': 'Pass123!',
            'role': 'read_write', 'email': 'noen@eksempel.no',
        }
        data.update(felt)
        return CustomUser.objects.create_user(**data)

    def test_personlig_konto_med_epost_kan_resettes(self):
        self.assertTrue(kan_resettes(self._lag()))

    def test_delt_konto_kan_ikke(self):
        self.assertFalse(kan_resettes(
            self._lag(username='bil1', email=None, er_delt_konto=True)
        ))

    def test_delt_konto_med_epost_kan_heller_ikke(self):
        """Utelukkelsen skjer på flagget, ikke på «har e-post».

        Utledningen ville slått feil den dagen noen la en kontakt-e-post på en
        bil-konto — og da er lenken en lateral vei inn i systemet.
        """
        self.assertFalse(kan_resettes(
            self._lag(username='bil2', email='vakt@eksempel.no',
                      er_delt_konto=True)
        ))

    def test_konto_uten_epost_kan_ikke(self):
        self.assertFalse(kan_resettes(self._lag(username='ingenpost', email=None)))

    def test_frosset_konto_kan_ikke(self):
        bruker = self._lag(username='frosset')
        bruker.is_active = False
        bruker.save()
        self.assertFalse(kan_resettes(bruker))

    def test_oppslag_er_ufolsomt_for_store_bokstaver(self):
        """Samme grunn som ved innlogging: mobiltastatur setter stor forbokstav."""
        bruker = self._lag(username='kari', email='kari@eksempel.no')
        self.assertEqual(finn_bruker('Kari@Eksempel.NO'), bruker)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class ResetFlytTests(TestCase):

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        self.bruker = CustomUser.objects.create_user(
            username='kari.nordmann', password='GammeltPass123!',
            role='read_write', email='kari@eksempel.no',
            must_change_password=False,
        )
        gi_standardtilgang(self.bruker)

    def _be_om(self, epost='kari@eksempel.no'):
        return Client().post(reverse('accounts:glemt_passord'), {'email': epost})

    def test_lenke_sendes_til_eksisterende_konto(self):
        svar = self._be_om()
        self.assertEqual(svar.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['kari@eksempel.no'])
        self.assertEqual(mail.outbox[0].reply_to, ['support@sanitet.net'])

    def test_ukjent_adresse_gir_identisk_svar(self):
        """§6.7 — selve akseptansen. Kan bare testes ved sammenligning."""
        finnes = self._be_om('kari@eksempel.no')
        mail.outbox.clear()
        finnes_ikke = self._be_om('ingen@eksempel.no')

        self.assertEqual(finnes.status_code, finnes_ikke.status_code)
        self.assertEqual(finnes.content, finnes_ikke.content)
        self.assertEqual(len(mail.outbox), 0)

    def test_delt_konto_gir_ogsaa_identisk_svar(self):
        CustomUser.objects.create_user(
            username='bil3', password='Pass123!', role='read_write',
            email='bil@eksempel.no', er_delt_konto=True,
        )
        vanlig = self._be_om('kari@eksempel.no')
        mail.outbox.clear()
        delt = self._be_om('bil@eksempel.no')

        self.assertEqual(vanlig.content, delt.content)
        self.assertEqual(len(mail.outbox), 0,
                         'en delt konto skal ikke få reset-lenke')

    def test_epostfeil_gir_ogsaa_identisk_svar(self):
        """Ellers er en feilmelding et signal om at adressen finnes."""
        vanlig = self._be_om('ingen@eksempel.no')
        with patch('django.core.mail.EmailMessage.send',
                   side_effect=OSError('SMTP nede')):
            feilet = self._be_om('kari@eksempel.no')
        self.assertEqual(vanlig.content, feilet.content)

    def test_brukeren_setter_nytt_passord(self):
        url = reverse('accounts:passord_reset', args=[lag_token(self.bruker)])
        klient = Client()
        self.assertEqual(klient.get(url).status_code, 200)

        svar = klient.post(url, {
            'new_password1': 'HeltNyttPass123!',
            'new_password2': 'HeltNyttPass123!',
        })
        self.assertRedirects(svar, reverse('accounts:login'),
                             fetch_redirect_response=False)

        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.check_password('HeltNyttPass123!'))
        self.assertFalse(self.bruker.must_change_password)

    def test_sesjoner_avsluttes(self):
        """§6.3: uten dette overlever en stjålet sesjon passordbyttet."""
        innlogget = Client()
        innlogget.login(username='kari.nordmann', password='GammeltPass123!')
        self.assertEqual(innlogget.get('/pasienter/').status_code, 200)

        url = reverse('accounts:passord_reset', args=[lag_token(self.bruker)])
        Client().post(url, {
            'new_password1': 'HeltNyttPass123!',
            'new_password2': 'HeltNyttPass123!',
        })

        etter = innlogget.get('/pasienter/')
        self.assertEqual(etter.status_code, 302)
        self.assertIn('/accounts/login/', etter['Location'])

    def test_lenken_virker_kun_en_gang(self):
        url = reverse('accounts:passord_reset', args=[lag_token(self.bruker)])
        klient = Client()
        klient.post(url, {
            'new_password1': 'HeltNyttPass123!',
            'new_password2': 'HeltNyttPass123!',
        })

        andre = klient.post(url, {
            'new_password1': 'EnTredjeTing123!',
            'new_password2': 'EnTredjeTing123!',
        })
        self.assertEqual(andre.status_code, 400)

        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.check_password('HeltNyttPass123!'))

    def test_reset_logger_ikke_inn(self):
        """§6.2: MFA kan ikke omgås, og det følger av at ingen logges inn her."""
        url = reverse('accounts:passord_reset', args=[lag_token(self.bruker)])
        klient = Client()
        klient.post(url, {
            'new_password1': 'HeltNyttPass123!',
            'new_password2': 'HeltNyttPass123!',
        })
        self.assertEqual(klient.get('/pasienter/').status_code, 302)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class ResetRateLimitTests(TestCase):
    """§6.5: egen bøtte, ellers kan hvem som helst spamme en innboks."""

    def setUp(self):
        cache.clear()
        CustomUser.objects.create_user(
            username='kari.nordmann', password='GammeltPass123!',
            role='read_write', email='kari@eksempel.no',
        )

    def test_gjentatte_forespoersler_strupes(self):
        klient = Client()
        statuser = [
            klient.post(reverse('accounts:glemt_passord'),
                        {'email': 'kari@eksempel.no'}).status_code
            for _ in range(8)
        ]
        self.assertIn(429, statuser)

    def test_store_bokstaver_deler_botte(self):
        """Telleren må normaliseres på samme måte som oppslaget."""
        klient = Client()
        varianter = ['kari@eksempel.no', 'Kari@Eksempel.no', 'KARI@EKSEMPEL.NO']
        statuser = [
            klient.post(reverse('accounts:glemt_passord'),
                        {'email': varianter[i % 3]}).status_code
            for i in range(8)
        ]
        self.assertIn(429, statuser)

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class SidestrukturTests(TestCase):
    """Sidene må faktisk rendre som HTML, ikke bare svare 200.

    Skrevet etter at `/accounts/glemt-passord/` gikk i produksjon som en blank
    side. Malene ble satt sammen med `head -22` av en annen mal, og det
    linjetallet kuttet midt i `<style>`-blokken — ingen `</style>`, ingen
    `<body>`. Nettleseren leste resten av dokumentet som CSS og viste
    ingenting.

    **Testene fanget det ikke fordi de spurte om feil ting.** De sjekket at
    responsen var 200, og at innholdet var *identisk* mellom en adresse som
    finnes og en som ikke gjør det — og begge var like ødelagte. En test på at
    to ting er like sier ingenting om at noen av dem er riktige.
    """

    SIDER = [
        ('accounts:glemt_passord', ()),
        ('accounts:login', ()),
    ]

    def _sjekk_struktur(self, html, hvor):
        for aapen, lukk in (('<style>', '</style>'),
                            ('<head>', '</head>'),
                            ('<html', '</html>')):
            if aapen in html:
                self.assertIn(
                    lukk, html,
                    f'{hvor}: {aapen} uten {lukk} — resten av dokumentet '
                    f'tolkes som innholdet i det uavsluttede elementet',
                )
        self.assertIn('<body', html, f'{hvor}: mangler <body>')

    def test_offentlige_sider_rendrer_komplett_html(self):
        klient = Client()
        for navn, args in self.SIDER:
            with self.subTest(side=navn):
                resp = klient.get(reverse(navn, args=args))
                self.assertEqual(resp.status_code, 200)
                self._sjekk_struktur(resp.content.decode('utf-8'), navn)

    def test_svarsidene_i_resetflyten_rendrer_komplett_html(self):
        """Sidene man havner på etter en POST, som er de som brakk."""
        bruker = CustomUser.objects.create_user(
            username='struktur.test', password='Pass123!', role='read_write',
            email='struktur@eksempel.no', must_change_password=False,
        )
        gi_standardtilgang(bruker)
        klient = Client()

        sendt = klient.post(reverse('accounts:glemt_passord'),
                            {'email': 'struktur@eksempel.no'})
        self._sjekk_struktur(sendt.content.decode('utf-8'), 'glemt_passord_sendt')

        reset = klient.get(
            reverse('accounts:passord_reset', args=[lag_token(bruker)])
        )
        self._sjekk_struktur(reset.content.decode('utf-8'), 'passord_reset')

        ugyldig = klient.get(reverse('accounts:passord_reset', args=['tull']))
        self._sjekk_struktur(ugyldig.content.decode('utf-8'), 'reset_ugyldig')

    def test_skjemaet_finnes_faktisk_paa_sida(self):
        """En blank side svarer også 200. Innholdet må sjekkes.

        `glemt-passord` uten et e-postfelt er en side som ser ut til å virke
        og ikke gjør noen ting.
        """
        resp = Client().get(reverse('accounts:glemt_passord'))
        self.assertContains(resp, 'name="email"')
        self.assertContains(resp, 'type="submit"')
