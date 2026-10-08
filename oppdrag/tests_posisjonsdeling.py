"""Hvem deler posisjon (André, 4. okt. 2026).

«/ko har vel ingen oversikt over hvem som har slått av sporing? Det er vel noe
som kan være nyttig å vite for å skille mellom bevisst valg, teknisk funksjon
og neglekt på å følge prosedyre.» Bilskjermen kjente tilstanden sin — bryter
av, nettleser nektet, ingen GPS, gammel fix — og viste den bare for seg selv.
Fra KO så alle likt ut: ingen markør i kartet.

Tre beslutninger prøves her: deling er forventet på vakt og KO ser tilstanden;
**nåtilstand, ikke historikk** (ett felt, overskrives, skrives bare ved
endring); og tilstanden **følger `pa_vakt`** — av vakt melder bilen ingenting,
serveren skriver ingenting, og kortet vises ikke.

Serversiden: `services.noter_posisjonsdeling`, headeren på pollet,
`posisjonsdeling` i stemplingskroppen, nullstillingen i `sett_pa_vakt`, og
feltene på enhetskortet. Klienten kjøres i node gjennom de ekte inngangene —
`lastMine` med headeren, `_stemple` → køraden → `synk()`, `posisjonsdelingIkon`
på kortet og `koLegendeHtml` i KO.
"""
import json
import unittest
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from oppdrag import choices
from oppdrag.models import Enhet
from patients.js_test_utils import INNLOGGET, INNLOGGET_STUBB
from patients.js_test_utils import (
    KO_JS, OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available,
    run_node)

from .tests_views import StemplingBasis, _bruker, _klient

KART_PAA = dict(KART_URL='https://kart.example.no', KART_HMAC_NOKKEL='k' * 64)


class NoterPosisjonsdelingTests(StemplingBasis):
    """Tjenesten: skriv bare ved endring, aldri av vakt, ukjent for søppel."""

    def test_forste_melding_skriver_verdi_og_tidspunkt(self):
        self.assertEqual(self.enhet.posisjonsdeling, 'ukjent')
        self.assertIsNone(self.enhet.posisjonsdeling_at)
        from oppdrag import services
        self.assertTrue(services.noter_posisjonsdeling(self.enhet, 'deler'))
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'deler')
        self.assertIsNotNone(self.enhet.posisjonsdeling_at)

    def test_samme_verdi_igjen_skriver_ingenting(self):
        """Hvert poll bærer verdien. En skriving per poll er lasten
        «Skalering mot 2027» advarer mot, og `_at` skal si «siden når»."""
        from oppdrag import services
        services.noter_posisjonsdeling(self.enhet, 'av')
        self.enhet.refresh_from_db()
        foerste = self.enhet.posisjonsdeling_at
        with self.assertNumQueries(0):
            self.assertFalse(services.noter_posisjonsdeling(self.enhet, 'av'))
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling_at, foerste)

    def test_ukjent_verdi_lagres_som_ukjent_aldri_feil(self):
        """Samme regel som `_posisjon()`: en gammel bilskjerm mot en ny
        server skal fortsatt kunne stemple."""
        from oppdrag import services
        services.noter_posisjonsdeling(self.enhet, 'deler')
        services.noter_posisjonsdeling(self.enhet, 'tull<script>')
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'ukjent')

    def test_av_vakt_skriver_ingenting(self):
        from oppdrag import services
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=False)
        self.enhet.refresh_from_db()
        self.assertFalse(services.noter_posisjonsdeling(self.enhet, 'deler'))
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'ukjent')

    def test_none_skriver_ingenting(self):
        from oppdrag import services
        services.noter_posisjonsdeling(self.enhet, 'deler')
        self.assertFalse(services.noter_posisjonsdeling(self.enhet, None))
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'deler')

    def test_alle_verdiene_i_mengden_godtas(self):
        from oppdrag import services
        for verdi in ('deler', 'av', 'nektet', 'utilgjengelig', 'ukjent'):
            with self.subTest(verdi=verdi):
                services.noter_posisjonsdeling(self.enhet, ' ' + verdi.upper() + ' ')
                self.enhet.refresh_from_db()
                self.assertEqual(self.enhet.posisjonsdeling, verdi)


class HeaderenPaaPolletTests(StemplingBasis):
    """`X-Posisjonsdeling` inn, `X-Enhet-Pa-Vakt` ut — også på 304."""

    def _poll(self, tilstand=None, etag=None, klient=None):
        ekstra = {}
        if tilstand is not None:
            ekstra['HTTP_X_POSISJONSDELING'] = tilstand
        if etag:
            ekstra['HTTP_IF_NONE_MATCH'] = etag
        return (klient or self.bil).get('/oppdrag/api/oppdrag/', **ekstra)

    def test_headeren_skriver_tilstanden(self):
        resp = self._poll('av')
        self.assertEqual(resp.status_code, 200)
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'av')

    def test_leses_ogsaa_naar_svaret_er_304(self):
        """Tilstanden er uavhengig av om lista har endret seg, og 304 er det
        vanlige svaret. Leses den etter ETag-sjekken, står kortet feil til et
        oppdrag kommer."""
        etag = self._poll('deler')['ETag']
        resp = self._poll('nektet', etag=etag)
        self.assertEqual(resp.status_code, 304)
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'nektet')

    def test_uten_header_endres_ingenting(self):
        self._poll('deler')
        self._poll()
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'deler')

    def test_pa_vakt_svares_i_header_paa_200_og_304(self):
        resp = self._poll()
        self.assertEqual(resp['X-Enhet-Pa-Vakt'], '1')
        resp304 = self._poll(etag=resp['ETag'])
        self.assertEqual(resp304.status_code, 304)
        self.assertEqual(resp304['X-Enhet-Pa-Vakt'], '1')
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=False)
        self.assertEqual(self._poll()['X-Enhet-Pa-Vakt'], '0')

    def test_sentralbordet_faar_ingen_vakt_header_og_skriver_ingen_tilstand(self):
        sentral = _klient(_bruker('sentral-pd', 'les'))
        resp = self._poll('av', klient=sentral)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.has_header('X-Enhet-Pa-Vakt'))
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'ukjent')

    def test_av_vakt_skriver_ingenting_fra_pollet(self):
        Enhet.objects.filter(pk=self.enhet.pk).update(pa_vakt=False)
        self._poll('deler')
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'ukjent')


class StemplingenBaererTilstandenTests(StemplingBasis):

    def test_posisjonsdeling_i_kroppen_skrives_paa_enheten(self):
        o = self._oppdrag()
        resp = self._stemple(o, 'rykker_ut', body={'posisjonsdeling': 'av'})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'av')

    def test_skrives_ogsaa_naar_stemplingen_faar_409(self):
        """Bilen har sagt hva den gjør med posisjonen, uansett hvordan
        stemplingen går."""
        o = self._oppdrag()
        self._stemple(o, 'rykker_ut')
        resp = self._stemple(o, 'rykker_ut', body={'posisjonsdeling': 'nektet'})
        self.assertEqual(resp.status_code, 409, resp.content)
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'nektet')

    def test_skjemaet_er_fortsatt_lukket(self):
        o = self._oppdrag()
        resp = self._stemple(o, 'rykker_ut', body={'posisjonsdeling': 'av', 'navn': 'x'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('posisjonsdeling', resp.json()['message'])

    def test_sentralens_foering_skriver_aldri(self):
        o = self._oppdrag()
        sentral = _klient(_bruker('sentral-pf', 'skriv_full'))
        sentral.post(f'/oppdrag/api/oppdrag/{o.pk}/enheter/{self.enhet.pk}/status/rykker_ut/',
                     data={'posisjonsdeling': 'av'}, content_type='application/json')
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'ukjent')


class PaaOgAvVaktNullstillerTests(StemplingBasis):
    """«Nå» begynner på nytt når 113 setter bilen på vakt."""

    def setUp(self):
        super().setUp()
        self.sentral = _klient(_bruker('sentral-pv', 'skriv_full'))
        from oppdrag import services
        services.noter_posisjonsdeling(self.enhet, 'av')

    def _sett(self, pa_vakt):
        return self.sentral.post(f'/oppdrag/api/enheter/{self.enhet.pk}/vakt/',
                                 data={'pa_vakt': pa_vakt}, content_type='application/json')

    def test_av_vakt_nullstiller(self):
        self.assertEqual(self._sett(False).status_code, 200)
        self.enhet.refresh_from_db()
        self.assertEqual((self.enhet.pa_vakt, self.enhet.posisjonsdeling, self.enhet.posisjonsdeling_at),
                         (False, 'ukjent', None))

    def test_paa_vakt_igjen_nullstiller(self):
        self._sett(False)
        Enhet.objects.filter(pk=self.enhet.pk).update(posisjonsdeling='av', posisjonsdeling_at=timezone.now())
        self._sett(True)
        self.enhet.refresh_from_db()
        self.assertEqual((self.enhet.pa_vakt, self.enhet.posisjonsdeling), (True, 'ukjent'))

    def test_samme_verdi_igjen_roerer_ikke_tilstanden(self):
        """Idempotent: «på vakt» på en som alt er på vakt skal ikke glemme
        det bilen har meldt."""
        self._sett(True)
        self.enhet.refresh_from_db()
        self.assertEqual(self.enhet.posisjonsdeling, 'av')


class EnhetskortetBaererTilstandenTests(StemplingBasis):

    def test_feltene_er_med_i_lista(self):
        from oppdrag import services
        services.noter_posisjonsdeling(self.enhet, 'nektet')
        c = _klient(_bruker('sentral-pk', 'les'))
        rad = next(r for r in c.get('/oppdrag/api/enheter/').json()['data'] if r['id'] == self.enhet.pk)
        self.assertEqual(rad['posisjonsdeling'], 'nektet')
        self.assertIsNotNone(rad['posisjonsdeling_at'])

    def test_sidene_faar_flagget_for_kartkoblingen(self):
        """Kortet gater på `OPPDRAG_KART_KOBLING` — både /oppdrag/ og /ko/."""
        from accounts.models import ModulTilgang
        b = _bruker('sentral-pg', 'les')
        ModulTilgang.objects.create(bruker=b, modul_slug='ko', nivaa='les')
        ModulTilgang.objects.create(bruker=b, modul_slug='vaktliste', nivaa='les')
        c = _klient(b)
        with override_settings(**KART_PAA):
            self.assertIn('window.OPPDRAG_KART_KOBLING = true;', c.get('/oppdrag/').content.decode())
            self.assertIn('window.OPPDRAG_KART_KOBLING = true;', c.get('/ko/').content.decode())
        with override_settings(KART_URL='', KART_HMAC_NOKKEL=''):
            self.assertIn('window.OPPDRAG_KART_KOBLING = false;', c.get('/oppdrag/').content.decode())


# ── Klienten, i node ─────────────────────────────────────────────────────────

POS = ('posisjonMaksAlderMs', 'posisjonForStempling', 'kartKoblingAktiv', 'delPosisjonNokkel',
       'delerPosisjon', 'posisjonTilKo', 'posisjonLinjeTekst', 'posisjonsdelingTilstand',
       'erPaVakt', 'paVaktNokkel', 'notePaVakt', 'bryterSperret', 'tegnPosisjonLinje',
       'tegnSendPosisjon', 'sendPosisjonSperret')

BIL_HARNESS = (INNLOGGET, (OPPDRAG_ENHET_JS, ('lagNokkel', 'koNokkel', 'koLes', 'koSkriv', 'koLeggTil', 'koFjern',
                                   'projiser', 'synk', '_stemple', 'lastMine', 'harNyDelt', 'erNyDelt',
                                   'nyeOppdrag', *POS)),)

BIL_FORSPILL = """
const STEMPEL_LAAS_MS = 0; const NY_DELT_MS = 60000;
globalThis.localStorage = (() => { const m = {}; return {
  getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },
  removeItem: (k) => { delete m[k]; } }; })();
globalThis.OPPDRAG_NESTE = { venter: 'rykker_ut', rykker_ut: 'fremme' };
globalThis.OPPDRAG_STATUSNAVN = { rykker_ut: 'Rykker ut', fremme: 'Fremme' };
let mineOppdrag = [{ id: 7, status: 'venter', neste_overgang: 'rykker_ut', neste_navn: 'Rykker ut' }];
let stemplingPaagaar = false; let synkerNaa = false; let etagMine = null;
const kropper = []; const sendteHeadere = [];
let svarHeadere = {};
function renderAlt() {} function visFeil() {} function skjulFeil() {} function visUsendt() {}
function bilinnstillinger() { return {}; } function lydSkalSpille() { return false; } function pipNytt() {}
let kjenteOppdrag = new Set();
const linje = { klasser: new Set(['d-none']), classList: { toggle(k, v) { v ? linje.klasser.add(k) : linje.klasser.delete(k); } } };
const tekst = { textContent: '' }; const bryter = { checked: true, disabled: false };
globalThis.document = { getElementById: (id) => ({ 'posisjon-linje': linje, 'posisjon-tekst': tekst, 'del-posisjon': bryter })[id] || null };
globalThis.apiFetch = async (url, opts) => {
  if (opts && opts.body) { kropper.push(JSON.parse(opts.body)); return { ok: true }; }
  sendteHeadere.push((opts && opts.headers) || {});
  return { ok: true, status: 200, headers: { get: (n) => svarHeadere[n] ?? null },
           json: async () => ({ data: mineOppdrag }) };
};
const NAA = Date.now();
const fix = (s) => ({ lat: 59.4136, lon: 5.2683, tid: new Date(NAA - s * 1000).toISOString() });
"""


def _kjor_bil(kode):
    ut = run_node(INNLOGGET_STUBB + build_harness(BIL_HARNESS), '(async () => {\n' + kode + '\n})();', preamble=BIL_FORSPILL)
    return [json.loads(l) for l in ut.splitlines() if l != 'OK']


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class BilskjermensTilstandTests(unittest.TestCase):

    def test_tilstanden_for_hver_kombinasjon(self):
        (ut,) = _kjor_bil("""
            const t = [];
            globalThis.OPPDRAG_KART_KOBLING = false; t.push(posisjonsdelingTilstand());
            globalThis.OPPDRAG_KART_KOBLING = true; t.push(posisjonsdelingTilstand());
            globalThis.bilensPosisjon = fix(600); t.push(posisjonsdelingTilstand());
            globalThis.bilensPosisjonStatus = 'nektet'; t.push(posisjonsdelingTilstand());
            globalThis.bilensPosisjonStatus = 'utilgjengelig'; t.push(posisjonsdelingTilstand());
            globalThis.bilensPosisjonStatus = 'ok';
            localStorage.setItem(delPosisjonNokkel(), '0'); t.push(posisjonsdelingTilstand());
            localStorage.setItem(delPosisjonNokkel(), '1');
            localStorage.setItem(paVaktNokkel(), '0'); t.push(posisjonsdelingTilstand());
            console.log(JSON.stringify(t));""")
        # Uten kobling: ingenting. Gammel fix er fortsatt «deler». Bryteren
        # vinner over nettleserens status. Av vakt: ingenting.
        self.assertEqual(ut, [None, 'deler', 'deler', 'nektet', 'utilgjengelig', 'av', None])

    def test_pollet_baerer_tilstanden_som_header(self):
        (ut,) = _kjor_bil("""
            globalThis.OPPDRAG_KART_KOBLING = true;
            await lastMine();
            localStorage.setItem(delPosisjonNokkel(), '0');
            await lastMine();
            globalThis.OPPDRAG_KART_KOBLING = false;
            await lastMine();
            console.log(JSON.stringify(sendteHeadere.map((h) => h['X-Posisjonsdeling'] ?? null)));""")
        self.assertEqual(ut, ['deler', 'av', None])

    def test_koraden_baerer_tilstanden_fra_trykket(self):
        """Uten dekning ved trykket: raden ligger i køen med tilstanden fra
        da. Slår mannskapet bryteren på før dekningen kommer, er det fortsatt
        «av» som sendes — som for posisjonen."""
        (ut,) = _kjor_bil("""
            globalThis.OPPDRAG_KART_KOBLING = true;
            localStorage.setItem(delPosisjonNokkel(), '0');
            const ekte = globalThis.apiFetch;
            globalThis.apiFetch = async () => { throw new Error('ingen dekning'); };
            await _stemple(7, 'rykker_ut', 'knapp');
            const iKo = koLes()[0].posisjonsdeling;
            localStorage.setItem(delPosisjonNokkel(), '1');
            globalThis.apiFetch = ekte;
            await synk();
            console.log(JSON.stringify({ iKo, sendt: kropper[0].posisjonsdeling, posisjon: kropper[0].posisjon ?? null }));""")
        self.assertEqual(ut, {'iKo': 'av', 'sendt': 'av', 'posisjon': None})

    def test_av_vakt_ingen_posisjon_og_ingen_tilstand_i_koraden(self):
        (ut,) = _kjor_bil("""
            globalThis.OPPDRAG_KART_KOBLING = true; globalThis.bilensPosisjon = fix(5);
            localStorage.setItem(paVaktNokkel(), '0');
            await _stemple(7, 'rykker_ut', 'knapp');
            console.log(JSON.stringify([kropper[0].posisjon ?? null, kropper[0].posisjonsdeling ?? null, kropper.length]));""")
        self.assertEqual(ut, [None, None, 1], 'stemplingen går; posisjon og tilstand gjør det ikke')

    def test_overgangen_av_til_paa_vakt_nullstiller_bryteren(self):
        """Bryteren overlever fra forrige vakt i `localStorage`. En delt iPad
        slått av i mai skal ikke stå av i september og se ut som neglekt."""
        (ut,) = _kjor_bil("""
            globalThis.OPPDRAG_KART_KOBLING = true;
            localStorage.setItem(delPosisjonNokkel(), '0');
            svarHeadere = { 'X-Enhet-Pa-Vakt': '0' }; await lastMine();
            const avVakt = [erPaVakt(), delerPosisjon(), posisjonLinjeTekst().startsWith('Av vakt'), bryter.disabled];
            svarHeadere = { 'X-Enhet-Pa-Vakt': '1' }; await lastMine();
            const paaVakt = [erPaVakt(), delerPosisjon(), bryter.disabled];
            // Samme svar igjen rører ikke et valg tatt på denne vakta.
            localStorage.setItem(delPosisjonNokkel(), '0'); await lastMine();
            const uendret = delerPosisjon();
            // Uten header (en gammel server): ingenting skjer.
            svarHeadere = {}; await lastMine();
            console.log(JSON.stringify({ avVakt, paaVakt, uendret, tilSlutt: erPaVakt() }));""")
        self.assertEqual(ut, {'avVakt': [False, False, True, True], 'paaVakt': [True, True, False],
                              'uendret': False, 'tilSlutt': True})

    def test_bryteren_er_graa_uten_gps_og_av_vakt(self):
        (ut,) = _kjor_bil("""
            globalThis.OPPDRAG_KART_KOBLING = true;
            tegnPosisjonLinje(); const a = bryter.disabled;
            globalThis.bilensPosisjonStatus = 'utilgjengelig'; tegnPosisjonLinje(); const b = bryter.disabled;
            globalThis.bilensPosisjonStatus = 'ok'; localStorage.setItem(paVaktNokkel(), '0'); tegnPosisjonLinje();
            console.log(JSON.stringify([a, b, bryter.disabled, tekst.textContent]));""")
        self.assertEqual(ut[:3], [False, True, True])
        self.assertTrue(ut[3].startswith('Av vakt'))


KORT_HARNESS = (
    (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', 'klokke')),
    (OPPDRAG_SENTRAL_JS, ('_enhetskort', 'enhetskortInnmat', 'posisjonsdelingIkon', 'mkBesetning',
                          'kanSeBesetning', '_grovMerke', '_problemMedAntall', 'hastegradKlasse', 'tidSiden')),
)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class EnhetskortetsIkonTests(unittest.TestCase):

    def _kort(self, kobling=True, **felter):
        data = {'id': 1, 'navn': 'Haugesund 56', 'status': 'ledig', 'status_navn': 'Ledig',
                'kan_passiv_vakt': False, 'passiv_vakt': False, 'posisjonsdeling': 'ukjent',
                'posisjonsdeling_at': None}
        data.update(felter)
        return run_node(build_harness(KORT_HARNESS), f"""
            globalThis.window = {{}}; globalThis.OPPDRAG_KART_KOBLING = {json.dumps(kobling)};
            globalThis.besetninger = {{}}; globalThis.apenBesetning = null;
            console.log(_enhetskort({json.dumps(data)}));
        """)

    def test_uten_kobling_ingen_ikon(self):
        self.assertNotIn('posdeling', self._kort(kobling=False, posisjonsdeling='av'))

    def test_fire_tilstander_fire_klasser(self):
        for verdi, klasse in (('deler', 'posdeling-deler'), ('av', 'posdeling-av'),
                              ('nektet', 'posdeling-kan-ikke'), ('utilgjengelig', 'posdeling-kan-ikke'),
                              ('ukjent', 'posdeling-ukjent'), ('noe-nytt', 'posdeling-ukjent')):
            with self.subTest(verdi=verdi):
                kort = self._kort(posisjonsdeling=verdi)
                self.assertIn(f'class="posdeling {klasse}"', kort)
                self.assertNotIn('[object Object]', kort)

    def test_nektet_og_utilgjengelig_har_ulik_tekst(self):
        self.assertIn('nettleseren har nektet', self._kort(posisjonsdeling='nektet'))
        self.assertIn('ingen GPS', self._kort(posisjonsdeling='utilgjengelig'))

    def test_siden_naar_staar_i_tittelen(self):
        kort = self._kort(posisjonsdeling='av', posisjonsdeling_at='2026-10-04T11:51:00+02:00')
        self.assertIn('siden ', kort)
        self.assertNotIn('siden ', self._kort(posisjonsdeling='ukjent'))

    def test_ikonet_staar_sist_og_navnet_escapes_fortsatt(self):
        kort = self._kort(navn='<img src=x>', posisjonsdeling='deler')
        self.assertNotIn('<img', kort)
        self.assertLess(kort.index('enhet-navn'), kort.index('posdeling-deler'))


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class LegendenTests(unittest.TestCase):

    def test_radene_staar_bare_med_kobling(self):
        harness = build_harness(((KO_JS, ('koLegendeHtml', 'posisjonsdelingLegende')),))
        ut = run_node(harness, """
            globalThis.OPPDRAG_KART_KOBLING = false; const uten = koLegendeHtml();
            globalThis.OPPDRAG_KART_KOBLING = true; const med = koLegendeHtml();
            console.log(JSON.stringify([uten.includes('posdeling'),
              ['posdeling-deler', 'posdeling-av', 'posdeling-kan-ikke', 'posdeling-ukjent'].every((k) => med.includes(k)),
              med.includes('status-ledig')]));
        """).splitlines()[0]
        self.assertEqual(json.loads(ut), [False, True, True])


class MigrasjonenTests(StemplingBasis):

    def test_standardverdien_er_ukjent(self):
        e = Enhet.objects.create(navn='Ny bil')
        self.assertEqual(e.posisjonsdeling, choices.POSISJONSDELING_UKJENT)
        self.assertIsNone(e.posisjonsdeling_at)
