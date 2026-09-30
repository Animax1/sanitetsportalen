"""Bilens posisjon rir på stemplingen til kart.sanitet.net (30. sep. 2026).

`docs/PLAN_KARTKOBLING.md` §6. Serversiden: `posisjon` i kroppen valideres,
droppes når den er søppel (aldri 400 — køen i bilen ville strøket stemplingen),
og sendes etter commit med navnet fra databasen. Klientsiden kjøres i node
gjennom den ekte inngangen, `_stemple` → køraden → `synk()`.
"""
import json
import unittest
from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from oppdrag import choices
from oppdrag.models import Oppdrag, Statusmelding
from patients.js_test_utils import OPPDRAG_ENHET_JS, build_harness, node_available, run_node

from .tests_views import StemplingBasis, _bruker, _klient

SEND = 'core.kartkobling.send_enhet'


def _pos(**felt):
    return {'lat': 59.4136, 'lon': 5.2683, 'tid': timezone.now().isoformat(), **felt}


class _Rull(Exception):
    pass


class PosisjonVedStemplingTests(StemplingBasis):

    def _med(self, oppdrag, overgang, posisjon, **kropp):
        return self._stemple(oppdrag, overgang, body={'posisjon': posisjon, **kropp})

    def test_gyldig_posisjon_sendes_med_navnet_fra_databasen_etter_commit(self):
        o = self._oppdrag()
        pos = _pos()
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            resp = self._med(o, 'rykker_ut', pos)
        self.assertEqual(resp.status_code, 200, resp.content)
        send.assert_called_once()
        navn, lat, lon, tid = send.call_args.args
        self.assertEqual((navn, lat, lon), ('Haugesund 56', 59.4136, 5.2683))
        self.assertEqual(tid.isoformat(), pos['tid'])

    def test_sendingen_venter_paa_commit(self):
        o = self._oppdrag()
        with mock.patch(SEND) as send:
            with self.captureOnCommitCallbacks(execute=False) as cb:
                self._med(o, 'rykker_ut', _pos())
            send.assert_not_called()
            for kall in cb:
                kall()
            send.assert_called_once()

    def test_rullet_tilbake_stempling_sender_aldri(self):
        o = self._oppdrag()
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.assertEqual(self._med(o, 'rykker_ut', _pos()).status_code, 200)
                    raise _Rull
            except _Rull:
                pass
        send.assert_not_called()
        self.assertFalse(Statusmelding.objects.filter(oppdrag=o).exists())

    def test_navnet_leses_aldri_fra_kroppen(self):
        o = self._oppdrag()
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            resp = self._med(o, 'rykker_ut', _pos(navn='Falsk bil'))
        # Et ukjent felt i posisjonen er søppel: stemplingen går, posisjonen droppes.
        self.assertEqual(resp.status_code, 200)
        send.assert_not_called()
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            self._stemple(o, 'fremme', body={'posisjon': _pos(), 'navn': 'Falsk bil'})
        send.assert_not_called()   # ukjent nøkkel i kroppen → 400, ingenting skrevet

    def test_ugyldig_posisjon_lar_stemplingen_gaa_og_sender_ikke(self):
        ugyldige = [
            _pos(lat=91), _pos(lat=-91), _pos(lon=181), _pos(lat='59.4'), _pos(lat=True),
            _pos(tid='i går'), _pos(tid=(timezone.now() + timedelta(hours=1)).isoformat()),
            {'lat': 59.4, 'lon': 5.2}, 'Haugesund', [59.4, 5.2], 0,
        ]
        for pos in ugyldige:
            with self.subTest(pos=pos):
                o = self._oppdrag()
                with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True), \
                        self.assertLogs('oppdrag.views', 'WARNING') as logg:
                    resp = self._med(o, 'rykker_ut', pos)
                self.assertEqual(resp.status_code, 200, resp.content)
                o.refresh_from_db()
                self.assertEqual(o.status, choices.RYKKER_UT)
                send.assert_not_called()
                self.assertNotIn('59.4', '\n'.join(logg.output))

    def test_posisjon_litt_fram_i_tid_godtas(self):
        o = self._oppdrag()
        pos = _pos(tid=(timezone.now() + timedelta(minutes=2)).isoformat())
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            self._med(o, 'rykker_ut', pos)
        send.assert_called_once()

    def test_uten_posisjon_gaar_stemplingen_uten_sending(self):
        o = self._oppdrag()
        for kropp in ({}, {'posisjon': None}):
            with self.subTest(kropp=kropp), mock.patch(SEND) as send, \
                    self.captureOnCommitCallbacks(execute=True):
                o = self._oppdrag()
                self.assertEqual(self._stemple(o, 'rykker_ut', body=kropp).status_code, 200)
            send.assert_not_called()

    def test_alle_fire_grenene_sender(self):
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(grovsortering='gul')
        for overgang in ('rykker_ut', 'fremme', 'behandlet'):   # start, sett_status, behandle
            with self.subTest(overgang=overgang), mock.patch(SEND) as send, \
                    self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self._med(o, overgang, _pos()).status_code, 200)
            send.assert_called_once()
        o2 = self._oppdrag()
        self._stemple(o2, 'rykker_ut')
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self._med(o2, 'avbryt', _pos()).status_code, 200)
        send.assert_called_once()

    def test_avspilling_sender_ikke(self):
        o = self._oppdrag()
        kropp = {'posisjon': _pos(), 'idempotency_key': 'nokkel-12345678'}
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self._stemple(o, 'rykker_ut', body=kropp).status_code, 200)
            send.assert_not_called()
        self.assertEqual(send.call_count, 1)
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            resp = self._stemple(o, 'rykker_ut', body=kropp)
        self.assertTrue(resp.json()['data'].get('avspilling'), resp.content)
        send.assert_not_called()

    def test_409_og_400_fra_statusmaskinen_sender_ikke(self):
        o = self._oppdrag()
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self._med(o, 'fremme', _pos()).status_code, 409)
            self._stemple(o, 'rykker_ut')
            send.reset_mock()
            self.assertEqual(self._med(o, 'ledig', _pos()).status_code, 400)
        send.assert_not_called()

    def test_sentralens_foering_sender_aldri(self):
        sentral = _bruker('sentral-pos', 'skriv_full')
        o = self._oppdrag()
        with mock.patch(SEND) as send, self.captureOnCommitCallbacks(execute=True):
            _klient(sentral).post(
                f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.enhet.pk}/status/rykker_ut/',
                data={'tidspunkt': timezone.now().isoformat(), 'posisjon': _pos()},
                content_type='application/json')
        send.assert_not_called()


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class BilskjermenOgPosisjonTests(StemplingBasis):
    """Uten kobling spørres nettleseren aldri, og resten av portalen har
    `geolocation=()` uansett."""

    def test_uten_kobling_er_flagget_av_og_posisjon_stengt(self):
        with override_settings(KART_URL='', KART_HMAC_NOKKEL=''):
            resp = self.bil.get('/oppdrag/')
        self.assertIn('window.OPPDRAG_KART_KOBLING = false;', resp.content.decode())
        self.assertIn('geolocation=()', resp['Permissions-Policy'])

    def test_med_kobling_aapnes_posisjon_bare_paa_bilskjermen(self):
        with override_settings(KART_URL='https://kart.example.no', KART_HMAC_NOKKEL='k' * 64):
            resp = self.bil.get('/oppdrag/')
            sentral = _klient(_bruker('sentral-pp', 'les')).get('/oppdrag/')
        self.assertIn('window.OPPDRAG_KART_KOBLING = true;', resp.content.decode())
        self.assertIn('geolocation=(self)', resp['Permissions-Policy'])
        self.assertIn('camera=()', resp['Permissions-Policy'])
        self.assertIn('geolocation=()', sentral['Permissions-Policy'])


# ── Klienten, i node ─────────────────────────────────────────────────────────

POS_FUNKSJONER = ('posisjonMaksAlderMs', 'posisjonForStempling', 'kartKoblingAktiv',
                  'delPosisjonNokkel', 'delerPosisjon', 'posisjonTilKo', 'posisjonLinjeTekst')

HARNESS = ((OPPDRAG_ENHET_JS, ('lagNokkel', 'koNokkel', 'koLes', 'koSkriv', 'koLeggTil',
                               'koFjern', 'projiser', 'synk', '_stemple', *POS_FUNKSJONER)),)

FORSPILL = """
const STEMPEL_LAAS_MS = 0;
globalThis.localStorage = (() => { const m = {}; return {
  getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
  removeItem: (k) => { delete m[k]; } }; })();
globalThis.OPPDRAG_NESTE = { venter: 'rykker_ut', rykker_ut: 'fremme' };
globalThis.OPPDRAG_STATUSNAVN = { rykker_ut: 'Rykker ut', fremme: 'Fremme' };
let mineOppdrag = [{ id: 7, status: 'venter', neste_overgang: 'rykker_ut', neste_navn: 'Rykker ut' }];
let stemplingPaagaar = false; let synkerNaa = false; let etagMine = null;
const kropper = [];
let nett = true;
function renderAlt() {} function visFeil() {} function skjulFeil() {} function visUsendt() {}
async function lastMine() {}
globalThis.apiFetch = async (url, opts) => {
  if (!nett) throw new Error('ingen dekning');
  kropper.push(JSON.parse(opts.body)); return { ok: true }; };
const NAA = Date.now();
const fix = (sekunderSiden) => ({ lat: 59.4136, lon: 5.2683,
  tid: new Date(NAA - sekunderSiden * 1000).toISOString() });
"""


def _kjor(kode):
    ut = run_node(build_harness(HARNESS), '(async () => {\n' + kode + '\n})();', preamble=FORSPILL)
    return [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class PosisjonForStemplingTests(unittest.TestCase):

    def test_fersk_gammel_og_manglende_fix(self):
        (ut,) = _kjor("""
            console.log(JSON.stringify([
              posisjonForStempling(fix(0), NAA),
              posisjonForStempling(fix(119), NAA) !== null,
              posisjonForStempling(fix(120), NAA),
              posisjonForStempling(fix(600), NAA),
              posisjonForStempling(fix(-30), NAA) !== null,
              posisjonForStempling(null, NAA),
              posisjonForStempling({ lat: NaN, lon: 5, tid: fix(0).tid }, NAA),
              posisjonMaksAlderMs(),
            ]));""")
        self.assertEqual(ut[0], {'lat': 59.4136, 'lon': 5.2683, 'tid': ut[0]['tid']})
        self.assertEqual(ut[1:], [True, None, None, True, None, None, 120000])

    def _stemple(self, oppsett):
        (ut,) = _kjor(oppsett + """
            await _stemple(7, 'rykker_ut', 'knapp');
            console.log(JSON.stringify(kropper));""")
        return ut

    def test_posisjonen_fra_trykket_bæres_gjennom_synk(self):
        kropper = self._stemple("globalThis.OPPDRAG_KART_KOBLING = true; globalThis.bilensPosisjon = fix(10);")
        self.assertEqual(len(kropper), 1)
        self.assertEqual((kropper[0]['posisjon']['lat'], kropper[0]['posisjon']['lon']),
                         (59.4136, 5.2683))

    def test_bryteren_av_gir_ingen_posisjon(self):
        kropper = self._stemple("""globalThis.OPPDRAG_KART_KOBLING = true;
            globalThis.bilensPosisjon = fix(10);
            localStorage.setItem(delPosisjonNokkel(), '0');""")
        self.assertNotIn('posisjon', kropper[0])

    def test_uten_kobling_ingen_posisjon(self):
        kropper = self._stemple("globalThis.OPPDRAG_KART_KOBLING = false; globalThis.bilensPosisjon = fix(10);")
        self.assertNotIn('posisjon', kropper[0])

    def test_gammel_fix_gir_stempling_uten_posisjon(self):
        kropper = self._stemple("globalThis.OPPDRAG_KART_KOBLING = true; globalThis.bilensPosisjon = fix(300);")
        self.assertEqual(len(kropper), 1, 'stemplingen venter aldri på GPS')
        self.assertNotIn('posisjon', kropper[0])

    def test_koraden_bærer_posisjonen_fra_trykket_ikke_fra_sendingen(self):
        """Uten dekning ved trykket: raden ligger i køen med fixen fra da. Når
        dekningen kommer, har bilen flyttet seg — men det er trykket som sendes."""
        (ut,) = _kjor("""
            globalThis.OPPDRAG_KART_KOBLING = true;
            globalThis.bilensPosisjon = { lat: 59.1, lon: 5.1, tid: new Date().toISOString() };
            nett = false;
            await _stemple(7, 'rykker_ut', 'knapp');
            const iKo = koLes()[0].posisjon;
            globalThis.bilensPosisjon = { lat: 60.0, lon: 6.0, tid: new Date().toISOString() };
            nett = true;
            await synk();
            console.log(JSON.stringify({ iKo, sendt: kropper[0].posisjon }));""")
        self.assertEqual((ut['iKo']['lat'], ut['sendt']['lat']), (59.1, 59.1))

    def test_linja_sier_hva_som_skjer(self):
        (ut,) = _kjor("""
            const t = [];
            globalThis.OPPDRAG_KART_KOBLING = false; t.push(posisjonLinjeTekst());
            globalThis.OPPDRAG_KART_KOBLING = true; t.push(posisjonLinjeTekst());
            globalThis.bilensPosisjonStatus = 'nektet'; t.push(posisjonLinjeTekst());
            localStorage.setItem(delPosisjonNokkel(), '0'); t.push(posisjonLinjeTekst());
            console.log(JSON.stringify(t));""")
        self.assertEqual(ut, ['', 'Posisjon sendes til kartet ved stempling',
                              'Nettleseren har ikke gitt tilgang til posisjon', 'Posisjon deles ikke'])
