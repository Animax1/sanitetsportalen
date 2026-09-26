"""Sikkerhetsgjennomgangen 13. sep. 2026, runde 1 — vaktlista.

Hvert testnavn peker på funnet i `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
"""
import json

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

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
        self.korps = Korps.objects.create(navn='Haugesund', kortnavn='HGSD')
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
        self.assertTrue(d['konto_finnes'], 'merket sier at kontoen finnes — admin kobler')

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
