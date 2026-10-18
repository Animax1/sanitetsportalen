"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 1 — vaktlista.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
import json

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from vaktliste.test_helpers import lag_korps
from accounts.models import CustomUser
from patients.js_test_utils import JS_DIR, build_harness, node_available, run_node
from vaktliste.models import Korps, Mannskap
from vaktliste.tests_tilgang import _bruker, _klient
from core.jsonkropp import json_body

SW_JS = JS_DIR / 'vaktliste-sw.js'


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class AutokoblingKreverUtdelerTests(TestCase):
    """M5: e-postkoblingen flytter en badge, og bare den som kan dele ut
    badger utløser den. Først `skriv_full`+; snevret til leder og admin
    samme kveld (`tests_prodtest_13sep.py`)."""

    def setUp(self):
        self.korps = lag_korps(navn='Haugesund', kortnavn='HGSD')
        self.kari = CustomUser.objects.create_user(
            username='kari', password='x', email='kari@example.org', must_change_password=False)
        self.korpsbruker = _bruker('kb_s', 'skriv_handling')
        Mannskap.objects.create(navn='Fører', korps=self.korps, user=self.korpsbruker)
        self.c_kb = _klient(self.korpsbruker)
        self.c_vl = _klient(_bruker('vl_s', 'skriv_leder'))

    def _opprett(self, klient, navn):
        return klient.post('/vaktliste/api/mannskap/', content_type='application/json',
                           data={'navn': navn, 'korps_id': self.korps.pk, 'epost': 'kari@example.org'})

    def test_korpsforeren_lagrer_eposten_uten_aa_koble(self):
        res = self._opprett(self.c_kb, 'Kari via fører')
        self.assertEqual(res.status_code, 201, res.content)
        d = res.json()['data']
        self.assertEqual(d['epost'], 'kari@example.org')
        self.assertIsNone(d['user_id'])
        # Merket er lederens fra 28. sep. 2026 (André, punkt D).
        self.assertFalse(d['konto_finnes'], 'merket vises bare for den som kan lede')

    def test_lederen_kobler_som_foer(self):
        d = self._opprett(self.c_vl, 'Kari via leder').json()['data']
        self.assertEqual(d['user_id'], self.kari.pk)

    def test_redigering_kobler_heller_ikke_for_korpsforeren(self):
        person = Mannskap.objects.create(navn='Kari', korps=self.korps)
        res = self.c_kb.put(f'/vaktliste/api/mannskap/{person.pk}/', content_type='application/json',
                            data={'epost': 'kari@example.org'})
        self.assertEqual(res.status_code, 200, res.content)
        person.refresh_from_db()
        self.assertIsNone(person.user_id)


class PlantetEpostKoblesIkkeTests(TestCase):
    """Sikkerhetsgjennomgangen 28. sep. 2026: korps-føreren skrev en annens e-post
    inn på sin egen rad, og neste gang en leder lagret raden for noe helt annet,
    ble den kontoen koblet til korpset i stillhet — og arvet badgen."""

    def setUp(self):
        self.korps = lag_korps(navn='Haugesund', kortnavn='HGSD')
        self.kari = CustomUser.objects.create_user(
            username='kari_pl', password='x', email='kari.pl@example.org',
            must_change_password=False)
        self.korpsbruker = _bruker('kb_pl', 'skriv_handling')
        self.forer = Mannskap.objects.create(navn='Fører', korps=self.korps, user=self.korpsbruker)
        self.person = Mannskap.objects.create(navn='Tom rad', korps=self.korps)
        self.c_kb = _klient(self.korpsbruker)
        self.c_vl = _klient(_bruker('vl_pl', 'skriv_leder'))

    def _put(self, klient, **data):
        return klient.put(f'/vaktliste/api/mannskap/{self.person.pk}/',
                          content_type='application/json', data=data)

    def test_lederens_lagring_kobler_ikke_en_plantet_adresse(self):
        self.assertEqual(self._put(self.c_kb, epost='kari.pl@example.org').status_code, 200)
        # Lederens skjema sender alle feltene, e-posten med, uendret.
        res = self._put(self.c_vl, notat='sjekket', epost='kari.pl@example.org')
        self.assertEqual(res.status_code, 200, res.content)
        self.person.refresh_from_db()
        self.assertIsNone(self.person.user_id)

    def test_lederens_egen_adresse_kobles_ogsaa_senere(self):
        """Motprøven — «e-post først, konto senere» (André, 12. sep. 2026)."""
        CustomUser.objects.filter(pk=self.kari.pk).update(email='ny@example.org')
        self._put(self.c_vl, epost='kari.pl@example.org')
        self.person.refresh_from_db()
        self.assertIsNone(self.person.user_id, 'kontoen finnes ikke ennå med adressen')
        CustomUser.objects.filter(pk=self.kari.pk).update(email='kari.pl@example.org')
        self._put(self.c_vl, notat='lagret igjen', epost='kari.pl@example.org')
        self.person.refresh_from_db()
        self.assertEqual(self.person.user_id, self.kari.pk)

    def test_lederen_som_skriver_adressen_selv_kobler(self):
        self._put(self.c_kb, epost='annen@example.org')
        self._put(self.c_vl, epost='kari.pl@example.org')
        self.person.refresh_from_db()
        self.assertEqual(self.person.user_id, self.kari.pk)

    def test_plantet_ved_opprettelse_kobles_heller_ikke(self):
        """Samme vei, men gjennom POST: raden er født med den plantede adressen."""
        res = self.c_kb.post('/vaktliste/api/mannskap/', content_type='application/json',
                             data={'navn': 'Ny rad', 'korps_id': self.korps.pk,
                                   'epost': 'kari.pl@example.org'})
        self.assertIn(res.status_code, (200, 201), res.content)
        ny = Mannskap.objects.get(navn='Ny rad')
        self.assertIsNone(ny.user_id)
        res = self.c_vl.put(f'/vaktliste/api/mannskap/{ny.pk}/', content_type='application/json',
                            data={'notat': 'sjekket', 'epost': 'kari.pl@example.org'})
        self.assertEqual(res.status_code, 200, res.content)
        ny.refresh_from_db()
        self.assertIsNone(ny.user_id)

    def test_korpsforeren_ser_ikke_om_adressen_har_konto(self):
        d = self._put(self.c_kb, epost='kari.pl@example.org').json()['data']
        self.assertFalse(d['konto_finnes'])
        liste = self.c_kb.get('/vaktliste/api/mannskap/').json()['data']['mannskap']
        self.assertFalse(any(m['konto_finnes'] for m in liste))
        d = self._put(self.c_vl, notat='x').json()['data']
        self.assertTrue(d['konto_finnes'], 'lederen ser merket')


class JsonKroppTests(SimpleTestCase):
    """M8."""

    def test_liste_gir_tom_dict(self):
        req = RequestFactory().post('/', data=b'[1, 2]', content_type='application/json')
        self.assertEqual(json_body(req), {})


class KopiensAlderJsTests(SimpleTestCase):
    """H4: en datakopi eldre enn ett døgn serveres ikke."""

    HARNESS = ((SW_JS, ('erForGammel',)),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        from oppdrag.tests_runde_d import _konst
        self.harness = ("globalThis.self = { addEventListener: () => {} };\n"
                        + _konst(SW_JS, 'MAKS_ALDER_MS') + build_harness(self.HARNESS))

    def test_grensen(self):
        ut = run_node(self.harness, """
            const naa = Date.parse('2026-09-13T20:00:00Z');
            console.log(JSON.stringify([
              erForGammel('2026-09-13T10:00:00Z', naa),
              erForGammel('2026-09-12T19:00:00Z', naa),
              erForGammel('2026-09-01T10:00:00Z', naa),
              erForGammel('', naa),
              erForGammel(null, naa),
            ]));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [False, True, True, True, True])

    def test_nettforst_serverer_ikke_en_gammel_kopi(self):
        """Nettet nede, kopien for gammel: workeren kaster og sletter kopien —
        i stedet for å servere mannskapsregisteret fra i fjor."""
        harness = (self.harness
                   + build_harness(((SW_JS, ('nettForst', 'somKopi', 'kanLagres', 'medLagretTid')),)))
        ut = run_node(harness, """
            (async () => {
              const lagret = { hits: [], slettet: [] };
              const lagKopi = (iso) => new Response('{"a":1}', { status: 200, headers: { 'X-Vl-Lagret': iso } });
              let kopi = lagKopi('2020-01-01T00:00:00Z');
              globalThis.caches = { open: async () => ({
                match: async () => kopi,
                put: async () => { lagret.hits.push('put'); },
                delete: async (req) => { lagret.slettet.push(req); kopi = undefined; },
              }) };
              globalThis.fetch = async () => { throw new Error('nede'); };
              let feil = null;
              try { await nettForst('/vaktliste/api/mannskap/', 'data'); } catch (e) { feil = e.message; }
              const gammelt = [feil, lagret.slettet.length];
              kopi = lagKopi(new Date().toISOString());
              const svar = await nettForst('/vaktliste/api/mannskap/', 'data');
              console.log(JSON.stringify([gammelt, svar.status, svar.headers.get('X-Vl-Kopi') !== '']));
            })();
        """)
        # Harnessens «OK» skrives synkront, før det asynkrone svaret: les siste linje.
        self.assertEqual(json.loads(ut.strip().splitlines()[-1]), [['nede', 1], 200, True])


class KopienSlettesEtterEttDoegnTests(SimpleTestCase):
    """André, 18. okt. 2026: «stram det inn om det kan slettes etter 24 t». Workeren sletter
    for gamle kopier når den starter og ved trafikk — ikke bare når noen ber om akkurat dem.
    Kjører hele fila med falske `self` og `caches`, så kallstedene er med."""

    def test_aktivering_og_trafikk_sletter_de_for_gamle(self):
        from patients.js_test_utils import read_js
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        forspill = """
            const lyttere = {};
            globalThis.self = { addEventListener: (n, fn) => { lyttere[n] = fn; },
                                skipWaiting: async () => {}, clients: { claim: async () => {} },
                                location: { origin: 'https://p' } };
            const lagre = {};
            const svar = (lagret) => ({ headers: { get: (h) => (h === 'X-Vl-Lagret' ? lagret : null) } });
            globalThis.caches = {
              keys: async () => Object.keys(lagre),
              delete: async (n) => { delete lagre[n]; },
              open: async (n) => {
                lagre[n] = lagre[n] || new Map();
                const m = lagre[n];
                return { keys: async () => [...m.keys()], match: async (k) => m.get(k),
                         delete: async (k) => m.delete(k), put: async (k, v) => m.set(k, v) };
              },
            };
        """
        ut = run_node(read_js(SW_JS), """
            (async () => {
              const gammel = new Date(Date.now() - 25 * 3600e3).toISOString();
              const fersk = new Date().toISOString();
              const data = await caches.open(DATA); const skall = await caches.open(SKALL);
              data.put('/vaktliste/api/mannskap/', svar(gammel));
              data.put('/vaktliste/api/ressurser/', svar(fersk));
              skall.put('/vaktliste/', svar(gammel));
              skall.put('/static/js/a.js', svar(null));
              const venter = [];
              await lyttere.activate({ waitUntil: (p) => venter.push(p) }); await Promise.all(venter);
              console.log(JSON.stringify([[...lagre[DATA].keys()], [...lagre[SKALL].keys()]]));
              lagre[DATA].set('/vaktliste/api/ressurser/', svar(gammel));
              sistRyddet = 0;
              lyttere.fetch({ request: { url: 'https://p/x', method: 'GET', mode: 'cors' },
                              waitUntil: (p) => venter.push(p), respondWith: () => {} });
              await Promise.all(venter);
              console.log(JSON.stringify([...lagre[DATA].keys()]));
            })();
        """, preamble=forspill).strip().splitlines()
        ut = [linje for linje in ut if linje != 'OK']
        self.assertEqual(ut[0], '[["/vaktliste/api/ressurser/"],["/static/js/a.js"]]')
        self.assertEqual(ut[1], '[]', 'ved trafikk også')
