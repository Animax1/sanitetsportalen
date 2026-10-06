"""Lagene til kart.sanitet.net (`ko/kartkobling.py`, `docs/archived/PLAN_KARTKOBLING.md` §7).

Prøvd gjennom de ekte inngangene — `tavle.plasser`, `services.sett_lag`,
`services.lukk_hendelse` — og ikke gjennom `meld_lag` direkte, så et kallsted
som forsvinner blir rødt. Klienten i `core` mockes; `on_commit` kjøres.
"""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from core.models import ModuleSettings
from ko import services, tavle
from ko.kartkobling import meld_lag
from ko.models import Tavleplassering

from .tests_tavle import _Grunnlag

KOBLET = {'KART_URL': 'https://kart.example.no', 'KART_HMAC_NOKKEL': 'k' * 64}


class _Rull(Exception):
    pass


@override_settings(**KOBLET)
class LageneTilKartetTests(_Grunnlag):

    def _sendt(self, handling):
        """Kjør `handling`, la commit skje, og gi (navn, sted) som ble sendt."""
        with mock.patch('core.kartkobling.send_lag') as send, \
                self.captureOnCommitCallbacks(execute=True):
            handling()
        return [(k.args[0], k.args[1]) for k in send.call_args_list]

    def _hendelse(self, lokasjon=None):
        return services.opprett_hendelse(self.vakt, 'Besvimt', bruker=self.operator,
                                         lokasjon=lokasjon or self.park)

    def test_plassering_sender_navn_og_sted(self):
        self.assertEqual(self._sendt(lambda: self._plasser(self.lag1, self.park)),
                         [('Lag 1', 'Parkscene')])

    def test_pause_sender_tomt(self):
        self._plasser(self.lag1, self.park)
        self.assertEqual(self._sendt(lambda: self._plasser(self.lag1, pause=True)),
                         [('Lag 1', '')])

    def test_av_tavla_sender_tomt(self):
        self._plasser(self.lag1, self.park)
        self.assertEqual(
            self._sendt(lambda: tavle.avslutt(self.vakt, self.lag1, bruker=self.operator)),
            [('Lag 1', '')])

    def test_paa_hendelse_sender_hendelsens_lokasjonsnavn(self):
        self._plasser(self.lag1, self.club)
        h = self._hendelse(self.park)
        sendt = self._sendt(lambda: services.sett_lag(h, [self.lag1.pk], bruker=self.operator))
        self.assertEqual(sendt, [('Lag 1', 'Parkscene')])

    def test_fjernet_fra_hendelsen_sender_tomt(self):
        h = self._hendelse()
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        self.assertEqual(self._sendt(lambda: services.sett_lag(h, [], bruker=self.operator)),
                         [('Lag 1', '')])

    def test_lukket_hendelse_sender_tomt_og_gjenapnet_sender_stedet(self):
        h = self._hendelse()
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        self.assertEqual(self._sendt(lambda: services.lukk_hendelse(h, bruker=self.operator)),
                         [('Lag 1', '')])
        h.refresh_from_db()
        self.assertEqual(self._sendt(lambda: services.gjenapne_hendelse(h, bruker=self.operator)),
                         [('Lag 1', 'Parkscene')])

    def test_nytt_sted_paa_hendelsen_flytter_lagene(self):
        h = self._hendelse()
        services.sett_lag(h, [self.lag1.pk], bruker=self.operator)
        h.refresh_from_db()
        sendt = self._sendt(lambda: services.rediger_hendelse(
            h, bruker=self.operator, versjon=h.versjon, lokasjon=self.club, sett_lokasjon=True))
        self.assertEqual(sendt, [('Lag 1', 'Club Venue')])

    def test_hendelse_uten_sted_tar_laget_av_kartet(self):
        self._plasser(self.lag1, self.club)
        h = services.opprett_hendelse(self.vakt, 'Uten sted', bruker=self.operator)
        self.assertEqual(self._sendt(lambda: services.sett_lag(h, [self.lag1.pk], bruker=self.operator)),
                         [('Lag 1', '')])

    def test_en_bil_sender_ingenting(self):
        self.assertEqual(self._sendt(lambda: meld_lag(self.bil)), [])

    def test_retting_av_en_lukket_rad_sender_den_aapne_tilstanden(self):
        naa = timezone.now()
        park = self._plasser(self.lag1, self.park, naa=naa - timedelta(minutes=60))
        self._plasser(self.lag1, self.club, naa=naa - timedelta(minutes=30))
        park.refresh_from_db()
        sendt = self._sendt(lambda: tavle.rett(
            park, fra=naa - timedelta(minutes=50), til=park.til, bruker=self.operator, naa=naa))
        self.assertEqual(sendt, [('Lag 1', 'Club Venue')])

    def test_fjernet_aapen_plassering_sender_tomt(self):
        rad = self._plasser(self.lag1, self.park)
        self.assertEqual(self._sendt(lambda: tavle.fjern(rad, bruker=self.operator)),
                         [('Lag 1', '')])

    def test_ko_slaatt_av_sender_ingenting(self):
        ModuleSettings.objects.filter(slug='ko').update(enabled=False)
        self.assertEqual(self._sendt(lambda: self._plasser(self.lag1, self.park)), [])

    def test_rullet_tilbake_flytting_sender_ingenting(self):
        def flytt():
            try:
                with transaction.atomic():
                    self._plasser(self.lag1, self.park)
                    raise _Rull
            except _Rull:
                pass
        self.assertEqual(self._sendt(flytt), [])
        self.assertFalse(Tavleplassering.objects.filter(ressurs=self.lag1).exists())

    def test_sendefeil_tar_ikke_ned_flyttingen(self):
        # assertLogs ytterst: loggen skrives når on_commit kjøres, altså når
        # captureOnCommitCallbacks går ut.
        with self.assertLogs('ko.kartkobling', 'WARNING'), \
                mock.patch('core.kartkobling.send_lag', side_effect=RuntimeError('nede')), \
                self.captureOnCommitCallbacks(execute=True):
            self._plasser(self.lag1, self.park)
        self.assertTrue(Tavleplassering.objects.filter(ressurs=self.lag1, til__isnull=True).exists())


class UtenKoblingTests(_Grunnlag):

    @override_settings(KART_URL='', KART_HMAC_NOKKEL='')
    def test_inert_uten_oppsett(self):
        with mock.patch('core.kartkobling.send_lag') as send, \
                self.captureOnCommitCallbacks(execute=True):
            self._plasser(self.lag1, self.park)
        send.assert_not_called()
