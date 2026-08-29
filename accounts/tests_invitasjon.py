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
from accounts.test_helpers import gi_standardtilgang


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InvitasjonTokenTests(TestCase):
    """Tokenet for seg, uten HTTP i veien."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='invitert', password='MidlertidigPass1!',
            role='bruker', email='invitert@eksempel.no',
        )
        gi_standardtilgang(self.bruker, 'skriver')

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
            username='bil3', password='pass', role='bruker',
            er_delt_konto=True,
        )
        gi_standardtilgang(bil, 'skriver')
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
        gi_standardtilgang(self.admin, 'admin')
        self.client = Client()
        self.client.force_login(self.admin)
        mail.outbox.clear()

    def _opprett(self, **felt):
        data = {
            'username': 'nyfrivillig',
            'fullt_navn': 'Kari Nordmann',
            'email': 'kari@eksempel.no',
            'role': 'bruker',
            'kontotype': 'person',
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
            username='bil7', fullt_navn='', email='', kontotype='delt',
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
            email='bil8@eksempel.no', kontotype='delt',
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

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class EksisterendeKontoerTests(TestCase):
    """Kontoene som fantes før feltene ble lagt til.

    Migrasjonen ga alle `fullt_navn=''` og `er_delt_konto=False`. Spørsmålet
    som utløste disse testene: hva skjer med dem — særlig admin-kontoen, som
    `create_admin` oppretter uten e-post?

    Svaret skal være «ingenting», og det er verdt å låse: en konto uten
    e-post og navn skal fortsatt kunne logge inn, redigeres og få rolle
    endret, helt uavhengig av invitasjonsflyten.
    """

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='gammeladmin', password='AdminPass123!', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.klient = Client()
        self.klient.force_login(self.admin)

    def test_konto_uten_epost_og_navn_er_gyldig(self):
        self.assertEqual(self.admin.fullt_navn, '')
        self.assertFalse(self.admin.er_delt_konto)
        self.assertIsNone(self.admin.email)

    def test_konto_uten_epost_kan_ikke_inviteres(self):
        """Ikke en feil — bare ingen adresse å sende til.

        Kontoen fungerer som før: den logges inn på med passordet sitt.
        """
        self.assertFalse(kan_inviteres(self.admin))

    def test_admin_kan_fylle_inn_navn_og_epost_etterpaa(self):
        """Uten dette ville alle eksisterende kontoer stått navnløse for godt.

        Feltene manglet i redigeringsskjemaet i første utgave av
        invitasjonsflyten, og funksjonen var dermed halvferdig for alle som
        allerede fantes — altså alle.
        """
        svar = self.klient.post(
            reverse('accounts:user_detail', args=[self.admin.pk]),
            {
                'action': 'edit',
                'fullt_navn': 'Andre Eritsland',
                'email': 'andre@eksempel.no',
                'role': 'admin',
                'is_active': 'on',
            },
        )
        self.assertEqual(svar.status_code, 302)

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.fullt_navn, 'Andre Eritsland')
        self.assertEqual(self.admin.email, 'andre@eksempel.no')
        self.assertTrue(kan_inviteres(self.admin))

    def test_kan_ikke_gjore_konto_delt_og_beholde_epost(self):
        """Ellers ville flagget vært verdiløst i etterkant.

        En konto kunne blitt opprettet som personlig og gjort delt senere med
        e-posten i behold — og da har reset-lenken en vei til en delt innboks
        likevel.
        """
        self.admin.email = 'andre@eksempel.no'
        self.admin.save()

        svar = self.klient.post(
            reverse('accounts:user_detail', args=[self.admin.pk]),
            {
                'action': 'edit',
                'fullt_navn': '',
                'email': 'andre@eksempel.no',
                'role': 'admin',
                'is_active': 'on',
                'er_delt_konto': 'on',
            },
        )
        self.assertEqual(svar.status_code, 200)

        self.admin.refresh_from_db()
        self.assertFalse(self.admin.er_delt_konto)

    def test_mfa_kan_ikke_kreves_paa_delt_konto(self):
        bil = CustomUser.objects.create_user(
            username='bil9', password='pass', role='bruker',
            er_delt_konto=True,
        )
        gi_standardtilgang(bil, 'skriver')
        svar = self.klient.post(
            reverse('accounts:user_detail', args=[bil.pk]),
            {
                'action': 'edit', 'fullt_navn': '', 'email': '',
                'role': 'bruker', 'is_active': 'on',
                'mfa_required': 'on', 'kontotype': 'delt',
            },
        )
        self.assertEqual(svar.status_code, 200)

        bil.refresh_from_db()
        self.assertFalse(bil.mfa_required)

@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TvungenUtloggingTests(TestCase):
    """Admin kan avslutte en brukers sesjoner uten å fryse kontoen.

    Utløst av et konkret behov: slås «Krev MFA» på mens brukeren har sju timer
    igjen av sesjonen, gjelder ikke kravet for den personen før cookien dør av
    seg selv. En sikkerhetsinnstilling som venter på en cookie er valgfri i
    praksis.
    """

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='sjef2', password='AdminPass123!', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.bruker = CustomUser.objects.create_user(
            username='frivillig', password='BrukerPass123!', role='bruker',
            must_change_password=False,
        )
        gi_standardtilgang(self.bruker, 'skriver')
        self.adminklient = Client()
        self.adminklient.force_login(self.admin)

    def _bruker_er_innlogget(self, klient):
        return klient.get(reverse('accounts:user_list')).status_code != 200

    def test_utlogging_avslutter_sesjonen_men_beholder_kontoen(self):
        brukerklient = Client()
        self.assertTrue(brukerklient.login(
            username='frivillig', password='BrukerPass123!',
        ))

        svar = self.adminklient.post(
            reverse('accounts:user_detail', args=[self.bruker.pk]),
            {'action': 'logg_ut'},
        )
        self.assertEqual(svar.status_code, 302)

        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.is_active,
                        'utlogging skal ikke fryse kontoen — det er «frys»')

        # Sesjonen skal være borte: en forespørsel havner på innlogging.
        etter = brukerklient.get('/pasienter/')
        self.assertEqual(etter.status_code, 302)
        self.assertIn('/accounts/login/', etter['Location'])

    def test_kan_logge_inn_igjen_med_en_gang(self):
        """Forskjellen fra «frys»: kontoen er urørt."""
        self.adminklient.post(
            reverse('accounts:user_detail', args=[self.bruker.pk]),
            {'action': 'logg_ut'},
        )
        paa_nytt = Client()
        self.assertTrue(paa_nytt.login(
            username='frivillig', password='BrukerPass123!',
        ))

    def test_admin_kan_ikke_logge_ut_seg_selv_herfra(self):
        svar = self.adminklient.post(
            reverse('accounts:user_detail', args=[self.admin.pk]),
            {'action': 'logg_ut'},
        )
        self.assertEqual(svar.status_code, 302)
        self.assertEqual(
            self.adminklient.get(reverse('accounts:user_list')).status_code, 200,
            'admin ble logget ut av sin egen handling',
        )

    def test_aa_slaa_paa_mfa_avslutter_sesjonen(self):
        """Kjernen i behovet: kravet skal gjelde med en gang, ikke om sju timer."""
        brukerklient = Client()
        brukerklient.login(username='frivillig', password='BrukerPass123!')

        self.adminklient.post(
            reverse('accounts:user_detail', args=[self.bruker.pk]),
            {
                'action': 'edit', 'fullt_navn': '', 'email': '',
                'role': 'bruker', 'is_active': 'on', 'mfa_required': 'on',
            },
        )

        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.mfa_required)

        etter = brukerklient.get('/pasienter/')
        self.assertEqual(etter.status_code, 302)
        self.assertIn('/accounts/login/', etter['Location'])

    def test_annen_endring_logger_ikke_ut(self):
        """Kun overgangen av→på for MFA skal avslutte sesjoner.

        Ellers ville hver eneste lagring av brukersiden kastet folk ut midt i
        en vakt.
        """
        brukerklient = Client()
        brukerklient.login(username='frivillig', password='BrukerPass123!')

        self.adminklient.post(
            reverse('accounts:user_detail', args=[self.bruker.pk]),
            {
                'action': 'edit', 'fullt_navn': 'Ny Navnesen', 'email': '',
                'role': 'bruker', 'is_active': 'on',
            },
        )

        self.assertEqual(brukerklient.get('/pasienter/').status_code, 200,
                         'brukeren ble logget ut av en ren navneendring')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class MfaVedOpprettingTests(TestCase):
    """«Krev MFA» skal kunne settes allerede når kontoen opprettes."""

    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='sjef3', password='AdminPass123!', role='admin',
            must_change_password=False,
        )
        gi_standardtilgang(self.admin, 'admin')
        self.klient = Client()
        self.klient.force_login(self.admin)

    def test_mfa_kan_settes_ved_oppretting(self):
        self.klient.post(reverse('accounts:user_create'), {
            'username': 'med.mfa',
            'fullt_navn': 'Med Mfa',
            'email': 'medmfa@eksempel.no',
            'role': 'bruker',
            'mfa_required': 'on',
            'kontotype': 'person',
            'metode': 'invitasjon',
        })
        self.assertTrue(
            CustomUser.objects.get(username='med.mfa').mfa_required
        )

    def test_mfa_kan_ikke_kreves_paa_delt_konto_ved_oppretting(self):
        svar = self.klient.post(reverse('accounts:user_create'), {
            'username': 'bil10',
            'fullt_navn': '',
            'email': '',
            'role': 'bruker',
            'mfa_required': 'on',
            'kontotype': 'delt',
            'metode': 'passord',
        })
        self.assertEqual(svar.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username='bil10').exists())
