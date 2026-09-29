"""Sikkerhetsgjennomgangen 28. sep. 2026, pulje 1: kontoovertakelse.

Testene her **gjennomfører angrepet** og krever at det stopper — de prøver ikke
at et vern står der. Forskjellen er hele grunnen til at hullene fantes:
MFA-stegene hadde tester for at oppsettet virket, ingen for at det sluttet å
virke når passordet byttet under det.

Funnene står i `CHANGELOG.md` under 28. sep. 2026 og i
`docs/SIKKERHETSGJENNOMGANG_2026-09-28.md`.
"""
from __future__ import annotations

import threading
import time
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.core import mail
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import CustomUser, LoginEvent
from accounts.test_helpers import gi_standardtilgang
from audit.models import AuditLog
from core.tests_ratelimit import nok_til_a_bryte

PASSORD = 'RiktigPassord123!'
LOGIN = '/accounts/login/'


def _kode(device):
    totp = TOTP(key=device.bin_key, step=device.step, t0=device.t0, digits=device.digits)
    totp.time = time.time()
    return str(totp.token()).zfill(device.digits)


def _innlogget(client) -> bool:
    return '_auth_user_id' in client.session


def _admin():
    admin = CustomUser.objects.create_user(
        username='adm_r3', password='x', role='admin', must_change_password=False)
    gi_standardtilgang(admin, 'admin')
    c = Client()
    c.force_login(admin)
    return admin, c


def _til_oppsett(bruker, client=None):
    """Passordsteget → oppsettsiden. Returnerer klienten og den ubekreftede enheten."""
    client = client or Client()
    client.post(LOGIN, {'username': bruker.username, 'password': PASSORD})
    client.get(LOGIN)
    enhet = TOTPDevice.objects.filter(user=bruker, confirmed=False).latest('pk')
    return client, enhet


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class HalvferdigMfaOppsettTests(TestCase):
    """1.1–1.3: den halvinnloggede sesjonen er bundet til passordet og brukeren."""

    def setUp(self):
        cache.clear()
        self.bruker = CustomUser.objects.create_user(
            username='kari_r3', password=PASSORD, must_change_password=False,
            mfa_required=True, email='kari_r3@example.com')

    def test_oppsettet_doer_naar_admin_tilbakestiller_passordet(self):
        """Selve angrepet: passordet lekket, admin reagerer, angriperen fullfører likevel."""
        angriper, enhet = _til_oppsett(self.bruker)

        _, admin = _admin()
        admin.post(f'/portal-admin/brukere/{self.bruker.pk}/', {'action': 'reset_password'})

        angriper.post(LOGIN, {'totp_code': _kode(enhet)})
        self.assertFalse(_innlogget(angriper),
                         'angriperen kom inn med det gamle passordet etter en reset')
        enhet.refresh_from_db()
        self.assertFalse(enhet.confirmed)

    def test_oppsettet_doer_naar_brukeren_selv_bytter_passord(self):
        """Samme angrep, men passordet byttes utenfor adminflaten (sett_passord)."""
        angriper, enhet = _til_oppsett(self.bruker)
        call_command('sett_passord', self.bruker.username,
                     '--passord', 'EtHeltAnnet456!', stdout=StringIO())

        angriper.post(LOGIN, {'totp_code': _kode(enhet)})
        self.assertFalse(_innlogget(angriper))

    def test_verifiseringen_doer_ogsaa_naar_passordet_byttes(self):
        enhet = TOTPDevice.objects.create(user=self.bruker, name='x', confirmed=True)
        angriper = Client()
        angriper.post(LOGIN, {'username': self.bruker.username, 'password': PASSORD})
        self.assertIn('mfa_verify_user_id', angriper.session)

        self.bruker.set_password('EtHeltAnnet456!')
        self.bruker.save()

        angriper.post(LOGIN, {'totp_code': _kode(enhet)})
        self.assertFalse(_innlogget(angriper))

    def test_gammel_oppsettsesjon_kan_ikke_legge_til_en_enhet_nummer_to(self):
        """Den ekte brukeren fullfører først; den gamle sesjonen skal ikke få en egen enhet."""
        angriper, angripers_enhet = _til_oppsett(self.bruker)
        eier, eiers_enhet = _til_oppsett(self.bruker)
        eier.post(LOGIN, {'totp_code': _kode(eiers_enhet)})
        self.assertTrue(_innlogget(eier))

        angriper.post(LOGIN, {'totp_code': _kode(angripers_enhet)})
        self.assertFalse(_innlogget(angriper))
        self.assertEqual(
            list(TOTPDevice.objects.filter(user=self.bruker, confirmed=True)), [eiers_enhet])

    def _eier_fullforte_et_annet_sted(self):
        """Eieren har en bekreftet enhet og reservekoder, uten at sesjonene ble rørt.

        Når eieren logger inn gjennom portalen, slettes de halvinnloggede
        sesjonene (1.3) — da prøver testene over den mekanismen, ikke denne.
        Her står den gamle oppsettsesjonen igjen, slik at sjekken i steg 2
        er det eneste som holder.
        """
        enhet = TOTPDevice.objects.create(user=self.bruker, name='eier', confirmed=True)
        StaticDevice.objects.filter(user=self.bruker).delete()
        koder = StaticDevice.objects.create(user=self.bruker, name='Backup-koder')
        koder.token_set.create(token='EIERKODE')
        return enhet

    def test_steg_to_avviser_naar_kontoen_alt_har_en_enhet(self):
        angriper, angripers_enhet = _til_oppsett(self.bruker)
        self._eier_fullforte_et_annet_sted()

        angriper.post(LOGIN, {'totp_code': _kode(angripers_enhet)})
        self.assertFalse(_innlogget(angriper))
        angripers_enhet.refresh_from_db()
        self.assertFalse(angripers_enhet.confirmed)

    def test_gammel_oppsettsesjon_sletter_ikke_eierens_reservekoder(self):
        angriper, _ = _til_oppsett(self.bruker)
        self._eier_fullforte_et_annet_sted()

        # Sesjonen mister reservekodene sine og ville laget nye — over eierens.
        s = angriper.session
        s.pop('mfa_setup_backup_codes')
        s.save()
        angriper.get(LOGIN)

        self.assertEqual(
            list(StaticDevice.objects.get(user=self.bruker).token_set.values_list(
                'token', flat=True)), ['EIERKODE'])

    def test_innlogging_et_annet_sted_sletter_den_halve_sesjonen(self):
        """1.3 gjennom den ekte inngangen: eieren logger inn, angriperens sesjon er borte."""
        angriper, _ = _til_oppsett(self.bruker)
        eier, eiers_enhet = _til_oppsett(self.bruker)
        eier.post(LOGIN, {'totp_code': _kode(eiers_enhet)})
        self.assertFalse(Session.objects.filter(
            session_key=angriper.session.session_key).exists())

    def test_oppsettet_utloper(self):
        from accounts import mfa
        angriper, enhet = _til_oppsett(self.bruker)
        senere = timezone.now() + mfa.STEG_LEVETID + timedelta(seconds=1)
        with patch('accounts.mfa.timezone.now', return_value=senere):
            angriper.post(LOGIN, {'totp_code': _kode(enhet)})
        self.assertFalse(_innlogget(angriper))
        self.assertNotIn('mfa_setup_user_id', angriper.session)

    def test_oppsettet_virker_innenfor_levetiden(self):
        """Motprøven: uten den er testen over grønn også om oppsettet aldri virker."""
        eier, enhet = _til_oppsett(self.bruker)
        eier.post(LOGIN, {'totp_code': _kode(enhet)})
        self.assertTrue(_innlogget(eier))

    def test_sesjon_fra_for_bindingen_avvises(self):
        """En sesjon uten passordavtrykk kom fra forrige release og startes på nytt."""
        angriper, enhet = _til_oppsett(self.bruker)
        s = angriper.session
        for nokkel in [k for k in s.keys() if k.startswith('mfa_steg_')]:
            s.pop(nokkel)
        s.save()
        angriper.post(LOGIN, {'totp_code': _kode(enhet)})
        self.assertFalse(_innlogget(angriper))

    def test_sesjonsslettingen_tar_de_halvinnloggede(self):
        """1.3: `slett_brukerens_sesjoner` lover alle, ikke bare de innloggede."""
        from core.sesjoner import slett_brukerens_sesjoner
        _til_oppsett(self.bruker)
        TOTPDevice.objects.create(user=self.bruker, name='y', confirmed=True)
        Client().post(LOGIN, {'username': self.bruker.username, 'password': PASSORD})
        self.assertEqual(Session.objects.count(), 2)

        slett_brukerens_sesjoner(self.bruker)
        self.assertEqual(Session.objects.count(), 0)

    def test_nullstill_mfa_i_adminflaten_tar_de_halvinnloggede(self):
        angriper, _ = _til_oppsett(self.bruker)
        _, admin = _admin()
        admin.post(f'/portal-admin/brukere/{self.bruker.pk}/', {'action': 'reset_mfa'})
        self.assertFalse(Session.objects.filter(
            session_key=angriper.session.session_key).exists())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class InnloggingsloggenTests(TestCase):
    """1.4: passordsteget er ikke en vellykket innlogging når MFA gjenstår."""

    def setUp(self):
        cache.clear()
        self.bruker = CustomUser.objects.create_user(
            username='ola_r3', password=PASSORD, must_change_password=False, mfa_required=True)
        self.enhet = TOTPDevice.objects.create(user=self.bruker, name='x', confirmed=True)

    def test_passordtreff_uten_mfa_er_ikke_en_innlogging(self):
        Client().post(LOGIN, {'username': self.bruker.username, 'password': PASSORD})
        self.assertFalse(LoginEvent.objects.filter(
            user=self.bruker, event_type=LoginEvent.EVENT_LOGIN, success=True).exists())
        self.assertTrue(LoginEvent.objects.filter(
            user=self.bruker, event_type=LoginEvent.EVENT_PASSORD_OK).exists())
        self.bruker.refresh_from_db()
        self.assertIsNone(self.bruker.last_login_at)

    def test_filteret_ok_viser_ikke_halve_innlogginger(self):
        Client().post(LOGIN, {'username': self.bruker.username, 'password': PASSORD})
        _, admin = _admin()
        svar = admin.get(reverse('portaladmin:login_event_list') + '?result=ok&q=ola_r3')
        self.assertEqual(svar.context['total_count'], 0)

    def test_siste_innlogging_settes_naar_mfa_er_bestaatt(self):
        c = Client()
        c.post(LOGIN, {'username': self.bruker.username, 'password': PASSORD})
        c.post(LOGIN, {'totp_code': _kode(self.enhet)})
        self.assertTrue(_innlogget(c))
        self.bruker.refresh_from_db()
        self.assertIsNotNone(self.bruker.last_login_at)

    def test_uten_mfa_er_passordsteget_innloggingen(self):
        """Motprøven: en konto uten MFA skal fortsatt stå som vellykket innlogging."""
        uten = CustomUser.objects.create_user(
            username='per_r3', password=PASSORD, must_change_password=False)
        Client().post(LOGIN, {'username': uten.username, 'password': PASSORD})
        self.assertTrue(LoginEvent.objects.filter(
            user=uten, event_type=LoginEvent.EVENT_LOGIN, success=True).exists())
        uten.refresh_from_db()
        self.assertIsNotNone(uten.last_login_at)

    def test_telleren_nullstilles_ved_innlogging_med_klarert_enhet(self):
        """F8: gamle skrivefeil skal ikke hope seg opp til en lås."""
        from accounts.views import _trust_token
        self.bruker.failed_login_attempts = 4
        self.bruker.save(update_fields=['failed_login_attempts'])
        c = Client()
        c.cookies[f'mfa_trusted_{self.bruker.pk}'] = _trust_token(self.bruker, self.enhet)
        c.post(LOGIN, {'username': self.bruker.username, 'password': PASSORD})
        self.assertTrue(_innlogget(c))
        self.bruker.refresh_from_db()
        self.assertEqual(self.bruker.failed_login_attempts, 0)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class TellerenTaperIkkeForsokTests(TestCase):
    """1.5: to forespørsler som leste samme verdi skal telle to."""

    def test_to_utdaterte_objekter_teller_to(self):
        from accounts.kontolaas import registrer_mislykket
        bruker = CustomUser.objects.create_user(username='r3_teller', password=PASSORD)
        a = CustomUser.objects.get(pk=bruker.pk)
        b = CustomUser.objects.get(pk=bruker.pk)
        registrer_mislykket(a, '10.0.0.1')
        registrer_mislykket(b, '10.0.0.1')
        bruker.refresh_from_db()
        self.assertEqual(bruker.failed_login_attempts, 2)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PassordbytteLoggerUtTests(TestCase):
    """1.6: to veier satte passord uten å avslutte sesjonene."""

    def setUp(self):
        self.bruker = CustomUser.objects.create_user(
            username='lise_r3', password=PASSORD, must_change_password=False,
            email='lise@example.com')
        self.innlogget = Client()
        self.innlogget.force_login(self.bruker)

    def _lever(self):
        return Session.objects.filter(session_key=self.innlogget.session.session_key).exists()

    def test_sett_passord_avslutter_sesjonene(self):
        call_command('sett_passord', self.bruker.username, '--passord', 'EtHeltAnnet456!',
                     stdout=StringIO())
        self.assertFalse(self._lever())

    def test_sett_passord_setter_spor(self):
        call_command('sett_passord', self.bruker.username, '--passord', 'EtHeltAnnet456!',
                     stdout=StringIO())
        rad = AuditLog.objects.get(record_id=self.bruker.pk, field_name='password')
        self.assertIn('kommandolinja', rad.new_value)
        self.assertNotIn('EtHeltAnnet456!', rad.new_value)

    def test_invitasjonen_avslutter_sesjonene(self):
        from accounts.invitasjon import lag_token
        Client().post(reverse('accounts:invitasjon', args=[lag_token(self.bruker)]), {
            'new_password1': 'EtHeltAnnet456!', 'new_password2': 'EtHeltAnnet456!'})
        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.check_password('EtHeltAnnet456!'))
        self.assertFalse(self._lever())


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class GlemtPassordSvartidTests(TestCase):
    """1.7: svaret skal ikke vente på e-posten — ventetiden var svaret."""

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        CustomUser.objects.create_user(
            username='nina_r3', password=PASSORD, email='nina@example.com')

    def test_svaret_venter_ikke_paa_utsendingen(self):
        from accounts.passord_reset import vent_paa_utsendinger
        slipp = threading.Event()
        startet = threading.Event()

        def treg_send(*args, **kwargs):
            startet.set()
            slipp.wait(5)
            return 1

        with patch('django.core.mail.EmailMessage.send', side_effect=treg_send, autospec=True):
            t0 = time.monotonic()
            svar = Client().post(reverse('accounts:glemt_passord'),
                                 {'email': 'nina@example.com'})
            brukt = time.monotonic() - t0
            slipp.set()
            vent_paa_utsendinger()

        self.assertEqual(svar.status_code, 200)
        self.assertLess(brukt, 2, 'svaret ventet på utsendingen')
        self.assertTrue(startet.is_set(), 'e-posten ble aldri forsøkt sendt')

    def test_e_posten_sendes_fortsatt(self):
        from accounts.passord_reset import vent_paa_utsendinger
        Client().post(reverse('accounts:glemt_passord'), {'email': 'nina@example.com'})
        vent_paa_utsendinger()
        self.assertEqual([m.to for m in mail.outbox], [['nina@example.com']])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=True)
class DeltKontoLaasesPerIpTests(TestCase):
    """1.9 (B): fem feil fra én maskin skal ikke stenge bilen ute overalt.

    André 28. sep. 2026: «brukernavn + IP, og behold IP-bremsen».
    """

    def setUp(self):
        cache.clear()
        self.bil = CustomUser.objects.create_user(
            username='bil_r3', password=PASSORD, must_change_password=False,
            er_delt_konto=True)
        self.person = CustomUser.objects.create_user(
            username='per_r3', password=PASSORD, must_change_password=False)

    def _prov(self, bruker, passord, ip):
        c = Client(REMOTE_ADDR=ip)
        svar = c.post(LOGIN, {'username': bruker.username, 'password': passord})
        return c, svar

    def _feil(self, bruker, ip, n):
        for _ in range(n):
            self._prov(bruker, 'feil', ip)

    def test_bilen_kommer_inn_fra_en_annen_maskin(self):
        # Nok til å sprenge bøtta per brukernavn (10/5 min) uansett hvor
        # vinduskanten faller — ellers dreper testen bare en mutant av og til.
        self._feil(self.bil, '10.0.0.66', nok_til_a_bryte(10))
        c, _ = self._prov(self.bil, PASSORD, '10.0.0.7')
        self.assertTrue(_innlogget(c), 'angriperen låste bilen ute fra en annen maskin')

    def test_bilen_er_laast_fra_maskinen_som_gjettet(self):
        self._feil(self.bil, '10.0.0.66', 5)
        c, svar = self._prov(self.bil, PASSORD, '10.0.0.66')
        self.assertFalse(_innlogget(c))

    def test_en_personlig_konto_laases_fortsatt_overalt(self):
        """Motprøven: regelen gjelder delte kontoer, ikke alle."""
        self._feil(self.person, '10.0.0.66', 5)
        c, _ = self._prov(self.person, PASSORD, '10.0.0.7')
        self.assertFalse(_innlogget(c))

    def test_mange_maskiner_laaser_bilen_til_slutt(self):
        """Taket per konto: ellers er gjetting fra mange adresser ubegrenset."""
        from accounts.kontolaas import DELT_KONTO_TAK
        for i in range(DELT_KONTO_TAK):
            self._prov(self.bil, 'feil', f'10.1.{i // 250}.{i % 250 + 1}')
        c, _ = self._prov(self.bil, PASSORD, '10.9.9.9')
        self.assertFalse(_innlogget(c))

    def test_laas_opp_i_adminflaten_aapner_ogsaa_maskinlaasen(self):
        self._feil(self.bil, '10.0.0.66', 5)
        _, admin = _admin()
        admin.post(f'/portal-admin/brukere/{self.bil.pk}/', {'action': 'unlock'})
        c, _ = self._prov(self.bil, PASSORD, '10.0.0.66')
        self.assertTrue(_innlogget(c))


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class NullstillMfaKommandoTests(TestCase):
    """1.8: veien inn når telefonen er borte og ingen annen admin finnes."""

    def setUp(self):
        # `mfa_required=False` med vilje: nullstillingen skal *sette* kravet.
        # Sto det alt, kunne den sluttet å gjøre det uten at noe ble rødt
        # (mutant M20, 28. sep. 2026).
        self.bruker = CustomUser.objects.create_user(
            username='andre_r3', password=PASSORD, role='admin',
            must_change_password=False, mfa_required=False)
        TOTPDevice.objects.create(user=self.bruker, name='x', confirmed=True)
        StaticDevice.objects.create(user=self.bruker, name='Backup-koder')
        self.innlogget = Client()
        self.innlogget.force_login(self.bruker)

    def _kjor(self, *args):
        ut = StringIO()
        call_command('nullstill_mfa', *args, stdout=ut)
        return ut.getvalue()

    def test_krever_ja(self):
        with self.assertRaises(CommandError):
            self._kjor(self.bruker.username)
        self.assertTrue(TOTPDevice.objects.filter(user=self.bruker).exists())

    def test_nullstiller_som_knappen(self):
        self._kjor(self.bruker.username, '--ja')
        self.assertFalse(TOTPDevice.objects.filter(user=self.bruker).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.bruker).exists())
        self.bruker.refresh_from_db()
        self.assertTrue(self.bruker.mfa_required)
        self.assertFalse(Session.objects.filter(
            session_key=self.innlogget.session.session_key).exists())

    def test_setter_spor_med_kilden(self):
        self._kjor(self.bruker.username, '--ja')
        rad = AuditLog.objects.get(record_id=self.bruker.pk, field_name='mfa')
        self.assertIsNone(rad.user)
        self.assertIn('kommandolinja', rad.new_value)
        self.assertTrue(LoginEvent.objects.filter(
            user=self.bruker, event_type=LoginEvent.EVENT_MFA_RESET_BY_ADMIN).exists())

    def test_ukjent_bruker_avvises(self):
        with self.assertRaises(CommandError):
            self._kjor('finnes_ikke', '--ja')

    def test_knappen_og_kommandoen_er_samme_handling(self):
        """Én tjenestefunksjon — ellers glir to kopier av en sikkerhetshandling fra hverandre."""
        with patch('accounts.mfa.nullstill_mfa', wraps=__import__(
                'accounts.mfa', fromlist=['nullstill_mfa']).nullstill_mfa) as tjeneste:
            _, admin = _admin()
            admin.post(f'/portal-admin/brukere/{self.bruker.pk}/', {'action': 'reset_mfa'})
            self._kjor(self.bruker.username, '--ja')
        self.assertEqual(tjeneste.call_count, 2)


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BrukernavnetsTegnTests(TestCase):
    """Pulje 4: `CustomUser` arver `AbstractBaseUser` og hadde ingen tegnregel. Et
    brukernavn med `"` brøt skriptblokka på pasientsiden, og ett som begynte med `=`
    var en formel i auditeksporten."""

    def setUp(self):
        _, self.admin = _admin()

    def _opprett(self, navn):
        return self.admin.post(reverse('portaladmin:user_create'), {
            'kontotype': 'person', 'username': navn, 'email': '', 'role': 'bruker'})

    def test_farlige_tegn_avvises(self):
        for navn in ('a"b', 'x\\y', '<b>', '=cmd', '+1', '-a', '@a', 'bil 3', '_skjult'):
            with self.subTest(navn=navn):
                self._opprett(navn)
                self.assertFalse(CustomUser.objects.filter(username=navn.lower()).exists())

    def test_vanlige_navn_godtas(self):
        """Motprøven — æøå, sifre og punktum."""
        for navn in ('bjørn.rød', 'karmøy56', 'ola@x.no', 'bil_3'):
            with self.subTest(navn=navn):
                self._opprett(navn)
                self.assertTrue(CustomUser.objects.filter(username=navn).exists())


class _DodCache:
    """En cache der hvert kall kaster, som Djangos `RedisCache` når Redis er borte."""

    def __getattr__(self, navn):
        def kast(*a, **k):
            raise ConnectionError('Redis svarer ikke')
        return kast


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class KontolaasenFallerAapenTests(TestCase):
    """Gjennomgangen 29. sep. 2026: `_tell_maskin` leste generasjonen fra cachen
    utenfor `try`, så feil passord på en bilkonto ga 500 når Redis var nede."""

    def setUp(self):
        self.bil = CustomUser.objects.create_user(
            username='bil_dod', password=PASSORD, must_change_password=False,
            er_delt_konto=True)

    def test_feil_passord_gir_feilmelding_ikke_500(self):
        with patch('accounts.kontolaas.cache', _DodCache()):
            svar = Client(REMOTE_ADDR='10.0.0.5').post(
                LOGIN, {'username': 'bil_dod', 'password': 'feil'})
        self.assertEqual(svar.status_code, 200)
        self.assertContains(svar, 'Feil brukernavn eller passord')
        self.bil.refresh_from_db()
        self.assertEqual(self.bil.failed_login_attempts, 1, 'taket i databasen teller fortsatt')

    def test_riktig_passord_slipper_inn(self):
        with patch('accounts.kontolaas.cache', _DodCache()):
            c = Client(REMOTE_ADDR='10.0.0.5')
            c.post(LOGIN, {'username': 'bil_dod', 'password': PASSORD})
        self.assertTrue(_innlogget(c))


@override_settings(SECURE_SSL_REDIRECT=False)
class StrupetIpSlaarIkkeOppKontoenTests(TestCase):
    """Gjennomgangen 29. sep. 2026: brukernavnbøtta slår opp kontoen, så en IP
    som alt er strupet skal stoppes av IP-bøtta før den koster en spørring."""

    def test_ip_boetta_sjekkes_foer_kontooppslaget(self):
        from accounts import views as kontoviews
        ekte = kontoviews.core_er_rate_limited

        def strupet_ip(request, *, group, **kw):
            if group == 'login:ip':
                return True
            return ekte(request, group=group, **kw)

        with patch.object(kontoviews, 'core_er_rate_limited', strupet_ip), \
                patch.object(kontoviews, 'finn_konto') as oppslag:
            svar = Client().post(LOGIN, {'username': 'hvem_som_helst', 'password': 'x'})
        self.assertEqual(svar.status_code, 429)
        oppslag.assert_not_called()


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LaastDeltKontoRoperIkkePassordetTests(TestCase):
    """Andre gjennomgang 29. sep. 2026: en låst bilkonto svarte «låst» på riktig
    passord og «feil» på galt, så gjettingen fortsatte gjennom låsen fra så mange
    IP-er angriperen hadde. Taket holder bare hvis svaret er det samme."""

    def setUp(self):
        cache.clear()
        self.bil = CustomUser.objects.create_user(
            username='bil_orakel', password=PASSORD, must_change_password=False,
            er_delt_konto=True)
        from accounts.kontolaas import DELT_KONTO_TAK
        for i in range(DELT_KONTO_TAK):
            Client(REMOTE_ADDR=f'10.2.{i // 250}.{i % 250 + 1}').post(
                LOGIN, {'username': 'bil_orakel', 'password': 'feil'})
        self.bil.refresh_from_db()
        self.assertTrue(self.bil.is_locked(), 'forutsetningen: taket er nådd')

    def _svar(self, passord, ip='10.9.9.9'):
        c = Client(REMOTE_ADDR=ip)
        return c, c.post(LOGIN, {'username': 'bil_orakel', 'password': passord})

    def test_riktig_og_galt_passord_gir_samme_svar(self):
        _, riktig = self._svar(PASSORD)
        _, galt = self._svar('feil', ip='10.9.9.8')
        self.assertEqual(riktig.context['error'], galt.context['error'])
        self.assertIn('låst', galt.context['error'])

    def test_og_ingen_slipper_inn(self):
        c, _ = self._svar(PASSORD)
        self.assertFalse(_innlogget(c))

    def test_en_personlig_konto_er_uendret(self):
        """Motprøven: den har MFA og en global bøtte, og låses ved fem."""
        per = CustomUser.objects.create_user(
            username='per_orakel', password=PASSORD, must_change_password=False)
        for _ in range(5):
            Client().post(LOGIN, {'username': 'per_orakel', 'password': 'feil'})
        svar = Client().post(LOGIN, {'username': 'per_orakel', 'password': 'feil'})
        self.assertEqual(svar.context['error'], 'Feil brukernavn eller passord.')


class Ipv6TellesPerNettTests(TestCase):
    """Andre gjennomgang 29. sep. 2026: én bøtte per /128 var ingen grense for den
    som har et helt /64."""

    def _nokkel(self, ip):
        from django.test import RequestFactory
        from core.klientip import ratelimit_nokkel
        with override_settings(KLIENTIP_BAK_PROXY=False):
            return ratelimit_nokkel('g', RequestFactory().get('/', REMOTE_ADDR=ip))

    def test_samme_64_er_samme_boette(self):
        self.assertEqual(self._nokkel('2001:db8:1:2::1'), self._nokkel('2001:db8:1:2:ffff::9'))

    def test_naboens_64_er_en_annen(self):
        self.assertNotEqual(self._nokkel('2001:db8:1:2::1'), self._nokkel('2001:db8:1:3::1'))

    def test_ipv4_er_uendret(self):
        self.assertEqual(self._nokkel('10.0.0.5'), '10.0.0.5')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LaastDeltKontoTellerIkkeTests(TestCase):
    """Tredje gjennomgang 29. sep. 2026: mens en delt konto var låst, talte galt
    passord og ikke riktig. Hvert femtiende gale gjett flyttet `locked_until`, og
    minuttene i meldingen røpte om gjettet imellom var riktig."""

    def setUp(self):
        cache.clear()
        from accounts.kontolaas import DELT_KONTO_TAK
        self.bil = CustomUser.objects.create_user(
            username='bil_minutt', password=PASSORD, must_change_password=False,
            er_delt_konto=True)
        CustomUser.objects.filter(pk=self.bil.pk).update(
            locked_until=timezone.now() + timedelta(minutes=5),
            failed_login_attempts=DELT_KONTO_TAK - 1)

    def _prov(self, passord):
        return Client(REMOTE_ADDR='10.3.3.3').post(
            LOGIN, {'username': 'bil_minutt', 'password': passord}).context['error']

    def test_galt_passord_flytter_ikke_laasen(self):
        for_ = CustomUser.objects.get(pk=self.bil.pk).locked_until
        self._prov('feil')
        self.assertEqual(CustomUser.objects.get(pk=self.bil.pk).locked_until, for_)

    def test_minuttene_roper_ikke_det_riktige_gjettet(self):
        """Angrepet slik det ble kjørt: riktig passord imellom, så et galt."""
        etter_riktig = self._prov(PASSORD)
        etter_galt = self._prov('feil')
        self.assertEqual(etter_riktig, etter_galt)
        self.assertIn('5 minutt', etter_galt)
