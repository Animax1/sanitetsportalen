"""Utlogging i kartet når noen ikke lenger skal være der (19. okt. 2026).

`core.kartkobling.logg_ut_i_kartet`, kalt fra `accounts.sesjoner.avslutt_alle_sesjoner` og fra
`accounts/signals.py`. Kartet tar imot i `/api/portal/utlogging`.
"""
from __future__ import annotations

from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser, ModulTilgang, Portaltilgang
from accounts.sesjoner import avslutt_alle_sesjoner
from accounts.test_helpers import gi_modultilgang, gi_modultilgang_oppdater, gi_standardtilgang
from core import kartkobling
from core.models import AppSetting

NOKKEL = 'k' * 64
OPPSATT = {'KART_URL': 'https://testkart.sanitet.net', 'KART_INNLOGGING_NOKKEL': NOKKEL,
           'SECURE_SSL_REDIRECT': False, 'RATELIMIT_ENABLE': False}


def _bruker(navn, **kw):
    return CustomUser.objects.create_user(username=navn, password='x',
                                          must_change_password=False, **kw)


@override_settings(**OPPSATT)
class _Grunnlag(TestCase):
    """Fanger det som ville blitt sendt, etter commit."""

    def setUp(self):
        self.sendt = []
        p = mock.patch.object(kartkobling, '_logg_ut',
                              side_effect=lambda data, navn: self.sendt.append(data) or True)
        p.start()
        self.addCleanup(p.stop)

    def _utfor(self, fn):
        with self.captureOnCommitCallbacks(execute=True):
            fn()
        return self.sendt


class SikkerhetsoperasjoneneTests(_Grunnlag):
    """Alt som går gjennom `avslutt_alle_sesjoner`, logger også ut av kartet."""

    def setUp(self):
        super().setUp()
        self.admin = _bruker('ku_admin', role='admin', is_staff=True)
        gi_standardtilgang(self.admin, 'admin')
        self.admin2 = _bruker('ku_admin2', role='admin')
        gi_standardtilgang(self.admin2, 'admin')
        self.mal = _bruker('ku_mal')
        gi_modultilgang(bruker=self.mal, modul_slug='ko', nivaa='les')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_frysing(self):
        url = reverse('portaladmin:user_detail', kwargs={'pk': self.mal.pk})
        self._utfor(lambda: self.client.post(url, {'action': 'freeze'}))
        self.assertIn({'bruker': self.mal.pk}, self.sendt)

    def test_sletting(self):
        pk = self.mal.pk
        url = reverse('portaladmin:user_delete', kwargs={'pk': pk})
        self._utfor(lambda: self.client.post(url, {'confirm_username': 'ku_mal'}))
        self.assertFalse(CustomUser.objects.filter(pk=pk).exists())
        self.assertIn({'bruker': pk}, self.sendt)

    def test_avslutt_alle_sesjoner_direkte(self):
        self._utfor(lambda: avslutt_alle_sesjoner(self.mal))
        self.assertEqual(self.sendt, [{'bruker': self.mal.pk}])

    def test_uten_innloggingsnokkel_sendes_ingenting(self):
        with self.settings(KART_INNLOGGING_NOKKEL=''):
            self._utfor(lambda: avslutt_alle_sesjoner(self.mal))
        self.assertEqual(self.sendt, [])

    def test_rullet_tilbake_sendes_ikke(self):
        from django.db import transaction

        class Avbrudd(Exception):
            pass

        def rull_tilbake():
            try:
                with transaction.atomic():
                    avslutt_alle_sesjoner(self.mal)
                    raise Avbrudd
            except Avbrudd:
                pass

        self._utfor(rull_tilbake)
        self.assertEqual(self.sendt, [])


class KoTilgangenTests(_Grunnlag):
    """Signalene i `accounts/signals.py`: KO borte, eller tegneretten mistet."""

    def setUp(self):
        super().setUp()
        self.bruker = _bruker('ku_ko')

    def _sett_ko(self, nivaa):
        return gi_modultilgang_oppdater(bruker=self.bruker, modul_slug='ko',
                                        defaults={'nivaa': nivaa})

    def test_ny_rad_logger_ikke_ut(self):
        self._utfor(lambda: self._sett_ko('skriv_full'))
        self.assertEqual(self.sendt, [])

    def test_ko_fjernet(self):
        self._sett_ko('les')
        self._utfor(lambda: ModulTilgang.objects.filter(bruker=self.bruker, modul_slug='ko').delete())
        self.assertEqual(self.sendt, [{'bruker': self.bruker.pk}])

    def test_medlemskapet_fjernet_tar_ko_med_seg(self):
        self._sett_ko('les')
        self._utfor(lambda: Portaltilgang.objects.filter(bruker=self.bruker).delete())
        self.assertEqual(self.sendt, [{'bruker': self.bruker.pk}])

    def test_annen_modul_fjernet_logger_ikke_ut(self):
        self._sett_ko('les')
        gi_modultilgang(bruker=self.bruker, modul_slug='patients', nivaa='les')
        self._utfor(lambda: ModulTilgang.objects.filter(
            bruker=self.bruker, modul_slug='patients').delete())
        self.assertEqual(self.sendt, [])

    def test_annen_modul_senket_logger_ikke_ut(self):
        gi_modultilgang_oppdater(bruker=self.bruker, modul_slug='patients',
                                 defaults={'nivaa': 'skriv_full'})
        self._utfor(lambda: gi_modultilgang_oppdater(bruker=self.bruker, modul_slug='patients',
                                                     defaults={'nivaa': 'les'}))
        self.assertEqual(self.sendt, [])

    def test_mistet_tegneretten(self):
        self._sett_ko('skriv_full')
        self._utfor(lambda: self._sett_ko('les'))
        self.assertEqual(self.sendt, [{'bruker': self.bruker.pk}])

    def test_lavere_men_fortsatt_tegner_logger_ikke_ut(self):
        self._sett_ko('skriv_leder')
        self._utfor(lambda: self._sett_ko('skriv_full'))
        self.assertEqual(self.sendt, [])

    def test_hoyere_niva_logger_ikke_ut(self):
        self._sett_ko('les')
        self._utfor(lambda: self._sett_ko('skriv_full'))
        self.assertEqual(self.sendt, [])

    def test_les_lagret_igjen_logger_ikke_ut(self):
        """Den som aldri kunne tegne, har ingenting å miste."""
        rad, _ = self._sett_ko('les')
        self._utfor(rad.save)
        self.assertEqual(self.sendt, [])

    def test_lagret_uten_endring_logger_ikke_ut(self):
        rad, _ = self._sett_ko('skriv_full')
        self._utfor(rad.save)
        self.assertEqual(self.sendt, [])


class BryterenAvTests(_Grunnlag):
    """Av betyr av: også de som alt er inne."""

    def setUp(self):
        super().setUp()
        from core.kart_innstillinger import KartInnstillinger
        self.h = KartInnstillinger()

    def _sett(self, paa):
        post = {'kart_innlogging_sendt': '1'} | ({'kart_innlogging': '1'} if paa else {})
        self._utfor(lambda: self.h.lagre(self.h.valider(post)))

    def test_paa_til_av_logger_ut_alle(self):
        self._sett(True)
        self._sett(False)
        self.assertEqual(self.sendt, [{'alle': True}])

    def test_av_til_av_og_paa_til_paa_sender_ingenting(self):
        self._sett(False)
        self._sett(True)
        self._sett(True)
        self.assertEqual(self.sendt, [])

    def test_annet_felt_i_kortet_sender_ingenting(self):
        self._sett(True)
        self._utfor(lambda: self.h.lagre(self.h.valider({'kart_delt_posisjon': '20'})))
        self.assertEqual(self.sendt, [])
        self.assertEqual(AppSetting.get(kartkobling.INNLOGGING_NOKKEL), 'true')


@override_settings(**OPPSATT, KART_HMAC_NOKKEL='')
class SendingenTests(TestCase):
    """Selve sendingen: innloggingsnøkkelen, riktig sti, og uten posisjonsnøkkel i miljøet."""

    def setUp(self):
        from django.core.cache import cache
        cache.delete(kartkobling.PAUSE_NOKKEL)

    def test_signert_med_innloggingsnokkelen_til_utlogging(self):
        fanget = {}

        class _Svar:
            status = 204

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout):
            fanget['url'] = req.full_url
            fanget['kropp'] = req.data
            fanget['tid'] = req.headers['X-portal-tid']
            fanget['signatur'] = req.headers['X-portal-signatur']
            return _Svar()

        with mock.patch('core.kartkobling.request.urlopen', side_effect=urlopen):
            self.assertTrue(kartkobling._logg_ut({'bruker': 7}, 'bruker 7'))
        self.assertEqual(fanget['url'], 'https://testkart.sanitet.net/api/portal/utlogging')
        self.assertEqual(fanget['kropp'], b'{"bruker":7}')
        self.assertEqual(fanget['signatur'],
                         kartkobling.signer(NOKKEL, fanget['tid'], fanget['kropp']))

    def test_uten_innloggingsnokkel_ingen_sending(self):
        with self.settings(KART_INNLOGGING_NOKKEL=''), \
                mock.patch('core.kartkobling.request.urlopen') as urlopen:
            self.assertFalse(kartkobling._logg_ut({'alle': True}, 'alle'))
        urlopen.assert_not_called()

    def test_venter_ikke_paa_pausen_etter_en_feilet_posisjon(self):
        from django.core.cache import cache
        cache.set(kartkobling.PAUSE_NOKKEL, True, 60)
        self.addCleanup(cache.delete, kartkobling.PAUSE_NOKKEL)
        with mock.patch('core.kartkobling.request.urlopen') as urlopen:
            kartkobling._logg_ut({'bruker': 7}, 'bruker 7')
        urlopen.assert_called_once()

    def test_kaster_aldri(self):
        with mock.patch('core.kartkobling.request.urlopen', side_effect=OSError):
            self.assertFalse(kartkobling._logg_ut({'alle': True}, 'alle'))
