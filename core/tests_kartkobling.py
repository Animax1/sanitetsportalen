"""Klienten mot kart.sanitet.net (`core/kartkobling.py`, `docs/archived/PLAN_KARTKOBLING.md` §5).

`urlopen` mockes; signaturen prøves mot kartets regel slik den står i
`kart.sanitet/portal/signatur.py`, skrevet av her uavhengig av klientens egen
`signer()` — ellers ville en feil i den ene blitt godtatt av den andre.
"""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone as dt_timezone
from unittest import mock
from urllib import error

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from core import kartkobling

NOKKEL = 'k' * 64
OPPSATT = {'KART_URL': 'https://kart.example.no/', 'KART_HMAC_NOKKEL': NOKKEL}
TID = datetime(2026, 9, 30, 17, 4, 11, tzinfo=dt_timezone.utc)


def kartets_regel(nokkel, tid, kropp, signatur, naa):
    """Kartets mottak, kopiert i ånd: tid innenfor 300 s og HMAC over «tid.kropp»."""
    if abs(int(tid) - naa) > 300:
        return False
    forventet = 'sha256=' + hmac.new(nokkel.encode(), tid.encode() + b'.' + kropp,
                                     hashlib.sha256).hexdigest()
    return hmac.compare_digest(forventet, signatur)


class _Svar:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@override_settings(**OPPSATT)
class KartkoblingTests(SimpleTestCase):

    def setUp(self):
        cache.delete(kartkobling.PAUSE_NOKKEL)
        cache.delete(kartkobling.SISTE_NOKKEL)
        patcher = mock.patch('core.kartkobling.request.urlopen', return_value=_Svar())
        self.urlopen = patcher.start()
        self.addCleanup(patcher.stop)

    def _foresporsel(self, n=0):
        return self.urlopen.call_args_list[n].args[0]

    def test_enhet_sendes_signert_og_lar_seg_verifisere_med_kartets_regel(self):
        kartkobling.send_enhet('Haugesund 56', 59.4136, 5.2683, TID)
        req = self._foresporsel()
        self.assertEqual(req.full_url, 'https://kart.example.no/api/portal/enhet')
        self.assertEqual(req.get_method(), 'POST')
        tid = req.get_header('X-portal-tid')
        self.assertTrue(kartets_regel(NOKKEL, tid, req.data, req.get_header('X-portal-signatur'),
                                      time.time()))
        self.assertEqual(self.urlopen.call_args.kwargs['timeout'], 3)

    def test_egen_user_agent_ikke_urllibs(self):
        """Cloudflare foran testkart.sanitet.net ga 403 («error code: 1010») på
        «Python-urllib/3.13» (30. sep. 2026)."""
        kartkobling.send_enhet('Bil', 59.4, 5.2, TID)
        ua = self._foresporsel().get_header('User-agent')
        self.assertEqual(ua, kartkobling.USER_AGENT)
        self.assertNotIn('urllib', ua.lower())

    def test_signaturen_er_ikke_over_kroppen_alene(self):
        kartkobling.send_enhet('Haugesund 56', 59.4, 5.2, TID)
        req = self._foresporsel()
        bare_kropp = 'sha256=' + hmac.new(NOKKEL.encode(), req.data, hashlib.sha256).hexdigest()
        self.assertNotEqual(req.get_header('X-portal-signatur'), bare_kropp)

    def test_feil_nokkel_verifiserer_ikke(self):
        kartkobling.send_lag('Lag 3', 'Parkscene', TID)
        req = self._foresporsel()
        self.assertFalse(kartets_regel('x' * 64, req.get_header('X-portal-tid'), req.data,
                                       req.get_header('X-portal-signatur'), time.time()))

    def test_kroppen_har_noyaktig_feltene_i_planen(self):
        kartkobling.send_enhet('Haugesund 56', 59.4136, 5.2683, TID)
        kartkobling.send_lag('Lag 3', 'Parkscene', TID)
        enhet = json.loads(self._foresporsel(0).data)
        lag = json.loads(self._foresporsel(1).data)
        self.assertEqual(enhet, {'navn': 'Haugesund 56', 'lat': 59.4136, 'lon': 5.2683,
                                 'tidspunkt': '2026-09-30T19:04:11+02:00'})
        self.assertEqual(lag, {'navn': 'Lag 3', 'sted': 'Parkscene',
                               'tidspunkt': '2026-09-30T19:04:11+02:00'})
        self.assertEqual(self._foresporsel(1).full_url, 'https://kart.example.no/api/portal/lag')

    def test_delt_posisjon_har_eget_endepunkt_og_noyaktig_feltene(self):
        """«OBS: Posisjon delt» (7. okt. 2026): ikke et felt på `lag`, som er der
        KO har plassert laget — og utløpet er et tidspunkt, ikke en varighet."""
        utloper = datetime(2026, 9, 30, 17, 19, 11, tzinfo=dt_timezone.utc)
        self.assertTrue(kartkobling.send_delt_posisjon('lag', 'Lag 3', 59.41, 5.27, TID, utloper))
        req = self._foresporsel()
        self.assertEqual(req.full_url, 'https://kart.example.no/api/portal/delt-posisjon')
        self.assertEqual(json.loads(req.data), {
            'type': 'lag', 'navn': 'Lag 3', 'lat': 59.41, 'lon': 5.27,
            'tidspunkt': '2026-09-30T19:04:11+02:00', 'utloper': '2026-09-30T19:19:11+02:00'})
        kartkobling.send_delt_posisjon('enhet', 'Haugesund 56', 59.41, 5.27, TID, utloper)
        self.assertEqual(json.loads(self._foresporsel(1).data)['type'], 'enhet')
        with self.assertRaises(ValueError):
            kartkobling.send_delt_posisjon('båt', 'X', 59, 5, TID, utloper)
        tid = req.get_header('X-portal-tid')
        self.assertTrue(kartets_regel(NOKKEL, tid, req.data, req.get_header('X-portal-signatur'),
                                      int(time.time())))

    def test_sendingen_svarer_om_kartet_tok_imot(self):
        """Knappene har noen som venter på svaret; stemplingene lar det ligge."""
        self.assertTrue(kartkobling.send_enhet('Bil', 59, 5, TID))
        self.urlopen.side_effect = error.HTTPError('u', 404, 'x', {}, None)
        with self.assertLogs('core.kartkobling', 'WARNING'):
            self.assertFalse(kartkobling.send_enhet('Bil', 59, 5, TID))
        with override_settings(KART_URL=''):
            self.assertFalse(kartkobling.send_enhet('Bil', 59, 5, TID))

    def test_et_raskt_nei_gir_ingen_pause(self):
        """Et 4xx kom fram og ble besvart med en gang — pausen verner mot det
        trege. Uten unntaket ville et kart som ennå ikke kjenner et nytt endepunkt
        stoppet bilenes posisjon i et minutt for hvert trykk på lagenes knapp."""
        self.urlopen.side_effect = error.HTTPError('u', 404, 'x', {}, None)
        with self.assertLogs('core.kartkobling', 'WARNING'):
            kartkobling.send_delt_posisjon('lag', 'Lag 3', 59, 5, TID, TID)
        self.assertFalse(kartkobling.status()['pause'])
        self.urlopen.side_effect = None
        self.assertTrue(kartkobling.send_enhet('Bil', 59, 5, TID))
        self.assertEqual(self.urlopen.call_count, 2)

    def test_et_5xx_gir_pause(self):
        self.urlopen.side_effect = error.HTTPError('u', 502, 'x', {}, None)
        with self.assertLogs('core.kartkobling', 'WARNING'):
            kartkobling.send_enhet('Bil', 59, 5, TID)
        self.assertTrue(kartkobling.status()['pause'])

    def test_tidspunktet_har_alltid_sone(self):
        kartkobling.send_lag('Lag 3', '', datetime(2026, 9, 30, 19, 4, 11))
        self.assertRegex(json.loads(self._foresporsel().data)['tidspunkt'], r'[+-]\d\d:\d\d$')

    @override_settings(KART_URL='', KART_HMAC_NOKKEL=NOKKEL)
    def test_inert_uten_adresse(self):
        kartkobling.send_enhet('Bil', 59, 5, TID)
        self.urlopen.assert_not_called()
        self.assertIsNone(kartkobling.siste_utfall())

    @override_settings(KART_URL='https://kart.example.no', KART_HMAC_NOKKEL='')
    def test_inert_uten_nokkel(self):
        kartkobling.send_lag('Lag', 'x', TID)
        self.urlopen.assert_not_called()

    @override_settings(KART_URL='file:///etc/passwd')
    def test_annet_enn_http_sendes_ikke(self):
        with self.assertLogs('core.kartkobling', 'WARNING'):
            kartkobling.send_enhet('Bil', 59, 5, TID)
        self.urlopen.assert_not_called()

    def test_urlerror_kaster_ikke_og_logger_uten_posisjon(self):
        self.urlopen.side_effect = error.URLError('nede')
        with self.assertLogs('core.kartkobling', 'WARNING') as logg:
            kartkobling.send_enhet('Haugesund 56', 59.4136, 5.2683, TID)
        tekst = '\n'.join(logg.output)
        self.assertIn('Haugesund 56', tekst)
        self.assertNotIn('59.41', tekst)
        self.assertFalse(kartkobling.siste_utfall()['ok'])

    def test_httperror_kaster_ikke_og_statuskoden_huskes(self):
        self.urlopen.side_effect = error.HTTPError('u', 401, 'x', {}, None)
        with self.assertLogs('core.kartkobling', 'WARNING') as logg:
            kartkobling.send_lag('Lag 3', 'Parkscene', TID)
        self.assertIn('401', '\n'.join(logg.output))
        self.assertEqual(kartkobling.siste_utfall()['status'], 401)

    def test_timeout_kaster_ikke(self):
        self.urlopen.side_effect = TimeoutError()
        with self.assertLogs('core.kartkobling', 'WARNING'):
            kartkobling.send_lag('Lag 3', 'x', TID)

    def test_ugyldig_tidspunkt_kaster_ikke(self):
        with self.assertLogs('core.kartkobling', 'WARNING'):
            kartkobling.send_lag('Lag 3', 'x', 'ikke en dato')
        self.urlopen.assert_not_called()

    def test_pause_etter_feil_hopper_over_neste_og_slipper_etter_60_s(self):
        self.urlopen.side_effect = error.URLError('nede')
        with self.assertLogs('core.kartkobling', 'WARNING'):
            kartkobling.send_enhet('Bil', 59, 5, TID)
        self.assertEqual(self.urlopen.call_count, 1)
        kartkobling.send_enhet('Bil', 59, 5, TID)
        self.assertEqual(self.urlopen.call_count, 1, 'sendingen i pausen skal hoppes over')
        self.urlopen.side_effect = None
        with mock.patch('django.core.cache.backends.locmem.time.time',
                        return_value=time.time() + kartkobling.PAUSE_S + 1):
            kartkobling.send_enhet('Bil', 59, 5, TID)
        self.assertEqual(self.urlopen.call_count, 2)

    def test_pausen_varer_ikke_evig(self):
        self.urlopen.side_effect = error.URLError('nede')
        with self.assertLogs('core.kartkobling', 'WARNING'):
            kartkobling.send_enhet('Bil', 59, 5, TID)
        with mock.patch('django.core.cache.backends.locmem.time.time',
                        return_value=time.time() + kartkobling.PAUSE_S - 5):
            self.assertTrue(kartkobling.status()['pause'])
        self.assertEqual(kartkobling.PAUSE_S, 60)

    def test_vellykket_sending_huskes_uten_pause(self):
        kartkobling.send_enhet('Bil', 59, 5, TID)
        siste = kartkobling.siste_utfall()
        self.assertEqual((siste['ok'], siste['status'], siste['hva']), (True, 204, 'enhet'))
        self.assertFalse(kartkobling.status()['pause'])

    def test_status_viser_verten_men_aldri_nokkelen(self):
        s = kartkobling.status()
        self.assertEqual(s['vert'], 'kart.example.no')
        self.assertTrue(s['konfigurert'])
        self.assertNotIn(NOKKEL, json.dumps(s))

    def test_dod_cache_kaster_ikke(self):
        with mock.patch('core.kartkobling.cache') as c:
            c.get.side_effect = RuntimeError('redis nede')
            c.set.side_effect = RuntimeError('redis nede')
            kartkobling.send_enhet('Bil', 59, 5, TID)
        self.urlopen.assert_called_once()


class StatuskortetTests(SimpleTestCase):

    @override_settings(KART_URL='', KART_HMAC_NOKKEL='')
    def test_payloaden_har_kortet_og_sier_ikke_satt_opp(self):
        from core.admin_status import _get_kartkobling
        self.assertEqual(_get_kartkobling()['konfigurert'], False)

    def test_kortet_i_node(self):
        import unittest
        from patients.js_test_utils import JS_DIR, build_harness, node_available, run_node
        if not node_available():
            raise unittest.SkipTest('node mangler')
        harness = build_harness(((JS_DIR / 'portal-status.js', ('datoKlokke', 'kartkoblingTekst')),))
        ut = run_node(harness, """
console.log(JSON.stringify([
  kartkoblingTekst({konfigurert: false}).kobling[0],
  kartkoblingTekst({konfigurert: true, vert: 'kart.x', siste: null}).siste[0],
  kartkoblingTekst({konfigurert: true, vert: 'kart.x', siste: {ok: false, status: 401, hva: 'lag', tid: '2026-09-30T19:00:00Z'}}).hint,
  kartkoblingTekst({konfigurert: true, vert: 'kart.x', siste: {ok: true, status: 204, hva: 'enhet', tid: '2026-09-30T19:00:00Z'}}).siste[1],
  kartkoblingTekst({konfigurert: true, vert: 'kart.x', siste: {ok: false, status: 403, hva: 'enhet', tid: '2026-09-30T19:00:00Z'}}).hint.slice(0, 4),
]));""")
        self.assertEqual(json.loads(ut.splitlines()[0]),
                         ['–', 'Ingen ennå',
                          '401: nøkkelen stemmer ikke med kartets PORTAL_HMAC_NOKKEL.', 'status-ok',
                          '403:'])


class LesPosisjonTests(SimpleTestCase):
    """Den ene valideringen av en posisjon fra en telefon (7. okt. 2026) —
    stemplingen, bilens knapp og lagenes knapp går alle gjennom den."""

    def _pos(self, **felt):
        from django.utils import timezone
        return {'lat': 59.41, 'lon': 5.27, 'tid': timezone.now().isoformat(), **felt}

    def test_gyldig(self):
        lat, lon, tid = kartkobling.les_posisjon(self._pos())
        self.assertEqual((lat, lon), (59.41, 5.27))
        self.assertIsNotNone(tid.tzinfo)

    def test_naiv_tid_faar_sone(self):
        self.assertIsNotNone(kartkobling.les_posisjon(self._pos(tid='2026-09-30T19:04:11'))[2].tzinfo)

    def test_ugyldig(self):
        from datetime import timedelta
        from django.utils import timezone
        fram = (timezone.now() + kartkobling.POSISJON_MAKS_FRAM + timedelta(seconds=30)).isoformat()
        for pos in ([], None, {'lat': 59, 'lon': 5}, self._pos(navn='x'), self._pos(lat=True),
                    self._pos(lat='59'), self._pos(lat=90.1), self._pos(lon=-180.1),
                    self._pos(lat=float('nan')), self._pos(tid='i går'), self._pos(tid=fram),
                    self._pos(tid='2026-13-45T99:00:00')):
            with self.subTest(pos=pos), self.assertRaises(ValueError):
                kartkobling.les_posisjon(pos)

    def test_grensene_er_med(self):
        self.assertEqual(kartkobling.les_posisjon(self._pos(lat=-90, lon=180))[:2], (-90.0, 180.0))


class DeltVarighetTests(TestCase):
    """«Delt posisjon vises i kartet» (André, 7. okt. 2026): én felles innstilling
    for bil og lag, i kortet «Kartet» på `/portal-admin/innstillinger/`."""

    def setUp(self):
        from core.kart_innstillinger import KartInnstillinger
        self.h = KartInnstillinger()

    def test_standard_er_15_og_klemmes(self):
        from core.models import AppSetting
        self.assertEqual(kartkobling.delt_posisjon_min(), 15)
        AppSetting.set(kartkobling.DELT_VARIGHET_NOKKEL, '999')
        self.assertEqual(kartkobling.delt_posisjon_min(), 120)
        AppSetting.set(kartkobling.DELT_VARIGHET_NOKKEL, 'tull')
        self.assertEqual(kartkobling.delt_posisjon_min(), 15)

    def test_settes_paa_innstillingene_og_valideres(self):
        from django.core.exceptions import ValidationError
        self.assertEqual(self.h.valider({}), {}, 'fraværende felt er «behold»')
        self.h.lagre(self.h.valider({'kart_delt_posisjon': '30'}))
        self.assertEqual(kartkobling.delt_posisjon_min(), 30)
        for feil in ('0', '121', 'x', ''):
            with self.assertRaises(ValidationError, msg=feil):
                self.h.valider({'kart_delt_posisjon': feil})

    def test_kortet_er_registrert_og_heter_det_vi_ble_enige_om(self):
        from django.template.loader import render_to_string
        from core.portalinnstillinger import all_handlers
        self.assertIn('kart', [h.slug for h in all_handlers()])
        html = render_to_string(self.h.mal, self.h.kontekst())
        self.assertIn('name="kart_delt_posisjon"', html)
        self.assertIn('Delt posisjon vises i kartet', html)
        self.assertIn('OBS: Posisjon delt', html)

    def test_admin_ser_kortet_paa_siden(self):
        from accounts.models import CustomUser
        from django.test import Client
        from django.urls import reverse
        admin = CustomUser.objects.create_user(username='kartadmin', password='x', role='admin',
                                               must_change_password=False)
        c = Client()
        c.force_login(admin)
        with self.settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False):
            svar = c.get(reverse('portaladmin:portal_settings'))
        self.assertContains(svar, 'Delt posisjon vises i kartet')


class VarighetenFlytterTests(TestCase):
    """`core/0016`: varigheten admin satte under «Vi finner ikke fram» på staging,
    følger med til «Delt posisjon vises i kartet», og den gamle raden er borte."""

    def _flytt(self):
        import importlib
        from django.apps import apps
        importlib.import_module('core.migrations.0016_delt_posisjon_varighet').flytt(apps, None)

    def test_verdien_folger_med(self):
        from core.models import AppSetting
        AppSetting.objects.create(key='park_hjelp_varighet_min', value='40')
        self._flytt()
        self.assertEqual(kartkobling.delt_posisjon_min(), 40)
        self.assertFalse(AppSetting.objects.filter(key='park_hjelp_varighet_min').exists())

    def test_en_ny_verdi_overskrives_ikke_og_uten_gammel_skjer_ingenting(self):
        from core.models import AppSetting
        self._flytt()
        self.assertFalse(AppSetting.objects.filter(key=kartkobling.DELT_VARIGHET_NOKKEL).exists())
        AppSetting.objects.create(key=kartkobling.DELT_VARIGHET_NOKKEL, value='10')
        AppSetting.objects.create(key='park_hjelp_varighet_min', value='40')
        self._flytt()
        self.assertEqual(kartkobling.delt_posisjon_min(), 10)
