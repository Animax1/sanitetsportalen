"""«Send posisjon» under enhetsnavnet (André, 7. okt. 2026).

«Her er jeg, hvor skal jeg?» — én posisjon til kartet, med eller uten oppdrag.
Serversiden (`views.posisjon_view`): lukket kropp, navnet fra databasen,
ugyldig posisjon er 400 (ingen kø å stryke fra), og svaret sier om kartet tok
imot. Klientsiden kjøres i node gjennom den ekte inngangen, `sendPosisjon()`.
"""
import json
import unittest
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from oppdrag.models import Enhet
from patients.js_test_utils import OPPDRAG_ENHET_JS, build_harness, node_available, run_node

from .tests_views import StemplingBasis, _bruker, _klient

SEND = 'core.kartkobling.send_enhet'
OPPSATT = {'KART_URL': 'https://kart.example.no', 'KART_HMAC_NOKKEL': 'k' * 64}
URL = '/oppdrag/api/posisjon/'


def _pos(**felt):
    return {'lat': 59.4136, 'lon': 5.2683, 'tid': timezone.now().isoformat(), **felt}


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False, **OPPSATT)
class SendPosisjonTests(StemplingBasis):

    def _send(self, kropp, klient=None):
        return (klient or self.bil).post(URL, data=json.dumps(kropp),
                                         content_type='application/json')

    def test_sendes_med_navnet_fra_databasen_uten_oppdrag(self):
        """Ingen oppdrag på bilen — knappen står og virker likevel."""
        pos = _pos()
        with mock.patch(SEND, return_value=True) as send:
            resp = self._send({'posisjon': pos})
        self.assertEqual(resp.status_code, 200, resp.content)
        navn, lat, lon, tid = send.call_args.args
        self.assertEqual((navn, lat, lon), ('Haugesund 56', 59.4136, 5.2683))
        self.assertEqual(tid.isoformat(), pos['tid'])
        self.assertIn('sendt_at', resp.json()['data'])

    def test_kroppen_er_lukket(self):
        """Et navn i kroppen skal aldri kunne bli det som står i kartet."""
        with mock.patch(SEND, return_value=True) as send:
            for kropp in ({'posisjon': _pos(), 'navn': 'Falsk bil'}, {}, [], {'pos': _pos()}):
                with self.subTest(kropp=kropp):
                    self.assertEqual(self._send(kropp).status_code, 400)
            self.assertEqual(self.bil.post(URL, data='{x', content_type='application/json')
                             .status_code, 400)
        send.assert_not_called()

    def test_ugyldig_posisjon_er_400_og_sendes_ikke(self):
        """Ikke `None` som i stemplingen: her er det ingen kø som stryker noe,
        og mannskapet skal få vite at trykket ikke gikk."""
        fram = (timezone.now() + timedelta(minutes=10)).isoformat()
        with mock.patch(SEND, return_value=True) as send:
            for pos in (_pos(lat=91), _pos(lon='5'), _pos(tid='i går'), _pos(tid=fram),
                        _pos(lat=True), {'lat': 59, 'lon': 5}):
                with self.subTest(pos=pos):
                    self.assertEqual(self._send({'posisjon': pos}).status_code, 400)
        send.assert_not_called()

    def test_kartet_som_ikke_tar_imot_gir_424_ikke_5xx(self):
        """Et 5xx er en e-post til admin per trykk (staging, 7. okt. 2026)."""
        with mock.patch(SEND, return_value=False):
            resp = self._send({'posisjon': _pos()})
        self.assertEqual(resp.status_code, 424)
        self.assertIn('samband', resp.json()['message'])

    def test_av_vakt_sendes_ingenting(self):
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=False)
        with mock.patch(SEND, return_value=True) as send:
            self.assertEqual(self._send({'posisjon': _pos()}).status_code, 409)
        send.assert_not_called()

    def test_uten_kobling_sendes_ingenting(self):
        with override_settings(KART_URL='', KART_HMAC_NOKKEL=''), \
                mock.patch(SEND, return_value=True) as send:
            self.assertEqual(self._send({'posisjon': _pos()}).status_code, 409)
        send.assert_not_called()

    def test_bare_enhetskontoer(self):
        sentral = _klient(_bruker('sentral-sp', 'skriv_full'))
        with mock.patch(SEND, return_value=True) as send:
            self.assertEqual(self._send({'posisjon': _pos()}, klient=sentral).status_code, 403)
        send.assert_not_called()

    def test_kontoen_uten_oppdragstilgang_slipper_ikke_inn(self):
        from accounts.models import ModulTilgang
        ModulTilgang.objects.filter(bruker=self.bilbruker, modul_slug='oppdrag').delete()
        with mock.patch(SEND, return_value=True) as send:
            self.assertEqual(self._send({'posisjon': _pos()}).status_code, 403)
        send.assert_not_called()

    def test_knappen_er_i_malen_under_navnet(self):
        html = self.bil.get('/oppdrag/').content.decode()
        navn = html.index('Haugesund 56</h1>')
        knapp = html.index('id="send-posisjon"')
        self.assertLess(navn, knapp)
        self.assertLess(knapp, html.index('id="aktivt-oppdrag"'),
                        'knappen står over oppdragene, ikke inne i dem')


# ── Klienten, i node ─────────────────────────────────────────────────────────

HARNESS = ((OPPDRAG_ENHET_JS, ('kartKoblingAktiv', 'erPaVakt', 'paVaktNokkel',
                               'delPosisjonNokkel', 'delerPosisjon',
                               'sendPosisjonMaksAlderMs', 'posisjonForKnapp',
                               'sendPosisjonSperret', 'tegnSendPosisjon',
                               '_sendPosisjonStatus', '_hentPosisjonEnGang', 'sendPosisjon',
                               'posisjonLinjeTekst', 'bryterSperret', 'tegnPosisjonLinje',
                               'posisjonFristMs', 'medFrist', 'posisjonstilgang',
                               'sendPosisjonFeiltekst', 'posisjonMaksAlderMs',
                               'posisjonForStempling')),)

FORSPILL = """
globalThis.localStorage = (() => { const m = {}; return {
  getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
  removeItem: (k) => { delete m[k]; } }; })();
const el = {};
const lag = (id) => (el[id] = el[id] || { id, textContent: '', disabled: false, checked: true,
  klasser: new Set(['d-none']), classList: { toggle(k, v) { v ? el[id].klasser.add(k) : el[id].klasser.delete(k); } } });
globalThis.document = { getElementById: (id) => lag(id) };
function klokke(iso) { return iso ? 'KL' : ''; }
const kall = []; let svar = { ok: true, body: { data: { sendt_at: new Date().toISOString() } } };
globalThis.apiFetch = async (url, opts) => {
  kall.push({ url, body: JSON.parse(opts.body) });
  if (svar === 'nett') throw new Error('offline');
  return { ok: svar.ok, json: async () => svar.body };
};
let gpsKall = 0; let gps = { lat: 60.1, lon: 6.1 };
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { geolocation: { getCurrentPosition(ok, feil) {
  gpsKall += 1;
  if (gps === 'aldri') return;   // spørsmålet om lov vises aldri, eller lukkes uten svar
  if (gps.code) feil(gps); else ok({ coords: { latitude: gps.lat, longitude: gps.lon }, timestamp: Date.now() });
} }, permissions: { query: async () => { if (tilgang === null) throw new Error('ukjent'); return { state: tilgang }; } } } });
let tilgang = null;
// Fristen slår til med en gang: testen skal ikke vente 20 s.
const ekteSetTimeout = setTimeout;
const straks = () => { globalThis.setTimeout = (f) => { ekteSetTimeout(f, 0); return 0; }; };
const NAA = Date.now();
const fix = (s) => ({ lat: 59.4136, lon: 5.2683, tid: new Date(NAA - s * 1000).toISOString() });
globalThis.OPPDRAG_KART_KOBLING = true;
"""


def _kjor(kode):
    ut = run_node(build_harness(HARNESS), '(async () => {\n' + kode + '\n})();', preamble=FORSPILL)
    return [json.loads(linje) for linje in ut.splitlines() if linje != 'OK']


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class SendPosisjonKnappenTests(unittest.TestCase):

    def test_fersk_fix_i_minnet_brukes_ellers_spoerres_nettleseren(self):
        (ut,) = _kjor("""
            const r = [posisjonForKnapp(fix(5), NAA), posisjonForKnapp(fix(31), NAA),
                       posisjonForKnapp(fix(-5), NAA), posisjonForKnapp(null, NAA),
                       posisjonForKnapp({ lat: NaN, lon: 5, tid: fix(1).tid }, NAA)];
            console.log(JSON.stringify(r.map((p) => (p ? p.lat : null))));""")
        self.assertEqual(ut, [59.4136, None, 59.4136, None, None])

    def test_trykket_sender_fixen_i_minnet_uten_aa_spoerre(self):
        (ut,) = _kjor("""
            globalThis.bilensPosisjon = fix(3);
            await sendPosisjon();
            console.log(JSON.stringify({ kall, gpsKall, status: el['send-posisjon-status'].textContent,
                                         sperret: el['send-posisjon'].disabled }));""")
        self.assertEqual(ut['gpsKall'], 0)
        self.assertEqual(len(ut['kall']), 1)
        self.assertEqual(ut['kall'][0]['url'], '/oppdrag/api/posisjon/')
        self.assertEqual(set(ut['kall'][0]['body']), {'posisjon'})
        self.assertEqual(ut['kall'][0]['body']['posisjon']['lat'], 59.4136)
        self.assertEqual(ut['status'], 'Sendt til kartet kl. KL')
        self.assertFalse(ut['sperret'], 'knappen slippes igjen etter sendingen')

    def test_gammel_fix_spoerr_nettleseren_paa_nytt(self):
        (ut,) = _kjor("""
            globalThis.bilensPosisjon = fix(90);
            await sendPosisjon();
            console.log(JSON.stringify({ gpsKall, lat: kall[0].body.posisjon.lat }));""")
        self.assertEqual(ut, {'gpsKall': 1, 'lat': 60.1})

    def test_bryteren_av_stopper_ikke_knappen(self):
        """Bryteren gjelder det som rir på stemplingene; knappen er et
        uttrykkelig valg om å sende akkurat nå."""
        (ut,) = _kjor("""
            localStorage.setItem(delPosisjonNokkel(), '0');
            globalThis.bilensPosisjon = fix(1);
            await sendPosisjon();
            console.log(JSON.stringify(kall.length));""")
        self.assertEqual(ut, 1)

    def test_knappen_vises_gjennom_den_ekte_inngangen(self):
        """`tegnPosisjonLinje()` er det sidelastingen og vaktskiftet kaller —
        kallet derfra er det som tar knappen fram og gjør den grå. Prøvd
        gjennom den, ikke gjennom hjelperen (CLAUDE.md, mutasjonstesting 3)."""
        (ut,) = _kjor("""
            const r = [];
            tegnPosisjonLinje();
            r.push(el['send-posisjon-rad'].klasser.has('d-none'), el['send-posisjon'].disabled);
            localStorage.setItem(paVaktNokkel(), '0'); tegnPosisjonLinje();
            r.push(el['send-posisjon'].disabled);
            globalThis.OPPDRAG_KART_KOBLING = false; tegnPosisjonLinje();
            r.push(el['send-posisjon-rad'].klasser.has('d-none'));
            console.log(JSON.stringify(r));""")
        self.assertEqual(ut, [False, False, True, True])

    def test_av_vakt_og_uten_kobling_sendes_ingenting(self):
        (ut,) = _kjor("""
            globalThis.bilensPosisjon = fix(1);
            localStorage.setItem(paVaktNokkel(), '0');
            await sendPosisjon();
            const avVakt = [kall.length, sendPosisjonSperret()];
            localStorage.setItem(paVaktNokkel(), '1');
            globalThis.OPPDRAG_KART_KOBLING = false;
            await sendPosisjon();
            tegnSendPosisjon();
            console.log(JSON.stringify({ avVakt, uten: kall.length,
                                         skjult: el['send-posisjon-rad'].klasser.has('d-none') }));""")
        self.assertEqual(ut, {'avVakt': [0, True], 'uten': 0, 'skjult': True})

    def test_nektet_og_ingen_dekning_sier_fra(self):
        (ut,) = _kjor("""
            const t = [];
            gps = { code: 1 }; await sendPosisjon();
            t.push(el['send-posisjon-status'].textContent, globalThis.bilensPosisjonStatus);
            globalThis.bilensPosisjonStatus = 'ok';
            gps = { lat: 60, lon: 6 }; svar = 'nett'; await sendPosisjon();
            t.push(el['send-posisjon-status'].textContent);
            svar = { ok: false, body: { message: 'Kartet tok ikke imot posisjonen. Meld den på samband.' } };
            await sendPosisjon(); t.push(el['send-posisjon-status'].textContent);
            console.log(JSON.stringify(t));""")
        self.assertIn('ikke gitt tilgang', ut[0])
        self.assertEqual(ut[1], 'nektet', 'linja nederst får vite det også')
        self.assertIn('ingen dekning', ut[2])
        self.assertIn('samband', ut[3])

    def test_telefon_som_aldri_svarer_laaser_ikke_knappen(self):
        """André, 7. okt. 2026: «det fryses ved å sende posisjon, det står bare
        "Henter posisjon..."». `timeout` i `getCurrentPosition` teller først når
        tilgangen er gitt, så et spørsmål som aldri besvares, ga aldri svar."""
        (ut,) = _kjor("""
            gps = 'aldri'; straks();
            await sendPosisjon();
            console.log(JSON.stringify({ status: el['send-posisjon-status'].textContent,
                                         sperret: el['send-posisjon'].disabled, kall: kall.length }));""")
        self.assertIn('Fikk ikke svar fra telefonen', ut['status'])
        self.assertIn('samband', ut['status'])
        self.assertFalse(ut['sperret'], 'knappen kan trykkes igjen')
        self.assertEqual(ut['kall'], 0)

    def test_etter_fristen_brukes_en_fix_under_to_minutter(self):
        (ut,) = _kjor("""
            gps = 'aldri'; straks();
            globalThis.bilensPosisjon = fix(90);
            await sendPosisjon();
            console.log(JSON.stringify(kall.map((k) => k.body.posisjon.lat)));""")
        self.assertEqual(ut, [59.4136])

    def test_et_nei_som_alt_er_gitt_sies_med_en_gang(self):
        (ut,) = _kjor("""
            tilgang = 'denied';
            globalThis.bilensPosisjon = fix(90);
            await sendPosisjon();
            console.log(JSON.stringify({ gpsKall, kall: kall.length, linje: globalThis.bilensPosisjonStatus,
                                         status: el['send-posisjon-status'].textContent }));""")
        self.assertEqual((ut['gpsKall'], ut['kall'], ut['linje']), (0, 0, 'nektet'))
        self.assertIn('ikke gitt tilgang', ut['status'])

    def test_naar_telefonen_spoer_sier_knappen_det(self):
        (ut,) = _kjor("""
            const historikk = [];
            el['send-posisjon-status'] = { set textContent(t) { historikk.push(t); }, get textContent() { return historikk.at(-1); } };
            tilgang = 'prompt'; gps = 'aldri'; straks();
            await sendPosisjon();
            console.log(JSON.stringify(historikk));""")
        self.assertIn('svar «Tillat»', ut[0])
        self.assertIn('Fikk ikke svar fra telefonen', ut[-1])
