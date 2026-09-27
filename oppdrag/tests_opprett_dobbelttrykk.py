"""«Opprett» på sentralbordet gir ett oppdrag, uansett antall trykk (27. sep. 2026).

André: «Når du trykker flere ganger på rad på opprett oppdrag så får du så flere
oppdrag lagd». `opprettOppdrag()` hadde verken lås eller nøkkel, og POST-en på
`/oppdrag/api/oppdrag/` var ikke idempotent. To lag nå, som i
pasientregistreringen: `withSubmitGuard` på knappen, og en nøkkel per åpning av
vinduet som serveren reserverer.
"""
import json
import unittest
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase

from core.idempotency import bygg_nokkel, reserver
from oppdrag.models import Oppdrag
from patients.js_test_utils import (
    OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, node_available, run_node,
)

from .tests_views import OppdragBasis, _bruker, _klient

NOKKEL = 'a1b2c3d4-e5f6-4711-8899-aabbccddeeff'


class ServerenOppretterEttPerNokkelTests(OppdragBasis):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.bruker = _bruker('sentral', 'skriv_full')
        self.c = _klient(self.bruker)

    def _post(self, klient=None, **ekstra):
        kropp = {'enhet_ider': [self.enhet.pk], 'lokasjon_id': self.lokasjon.pk,
                 'problemstilling': 'Pustevansker', 'hastegrad': 'Akutt', **ekstra}
        return (klient or self.c).post('/oppdrag/api/oppdrag/', content_type='application/json',
                                       data=kropp)

    def test_samme_nokkel_to_ganger_gir_ett_oppdrag(self):
        a = self._post(idempotency_key=NOKKEL)
        b = self._post(idempotency_key=NOKKEL)
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(Oppdrag.objects.count(), 1)
        self.assertEqual(a.json()['data']['id'], b.json()['data']['id'])

    def test_mens_den_forste_pagar_gir_409_duplikat(self):
        reserver(bygg_nokkel('oppdrag_create', self.bruker.pk, NOKKEL))
        svar = self._post(idempotency_key=NOKKEL)
        self.assertEqual(svar.status_code, 409)
        self.assertTrue(svar.json()['duplikat'])
        self.assertEqual(Oppdrag.objects.count(), 0)

    def test_ny_nokkel_er_et_nytt_oppdrag(self):
        self._post(idempotency_key=NOKKEL)
        self._post(idempotency_key='ffffffff-e5f6-4711-8899-aabbccddeeff')
        self.assertEqual(Oppdrag.objects.count(), 2)

    def test_uten_nokkel_som_for(self):
        """Eldre klienter og tester sender ingen nøkkel og skal ikke brekke."""
        self._post()
        self._post()
        self.assertEqual(Oppdrag.objects.count(), 2)

    def test_nokkelen_er_per_bruker(self):
        self._post(idempotency_key=NOKKEL)
        self._post(klient=_klient(_bruker('sentral2', 'skriv_full')), idempotency_key=NOKKEL)
        self.assertEqual(Oppdrag.objects.count(), 2)

    def test_avvist_innsending_brenner_ikke_nokkelen(self):
        self.assertEqual(self._post(idempotency_key=NOKKEL, hastegrad='Rød').status_code, 400)
        self.assertEqual(self._post(idempotency_key=NOKKEL).status_code, 200)
        self.assertEqual(Oppdrag.objects.count(), 1)

    def test_feil_under_opprettelsen_frigir_nokkelen(self):
        with mock.patch('oppdrag.services.varsle_enhet', side_effect=RuntimeError('borte')), \
                self.assertLogs('django.request', 'ERROR'):
            with self.assertRaises(RuntimeError):
                self._post(idempotency_key=NOKKEL)
        self.assertEqual(Oppdrag.objects.count(), 0)
        self.assertEqual(self._post(idempotency_key=NOKKEL).status_code, 200)
        self.assertEqual(Oppdrag.objects.count(), 1)


HARNESS = (
    (PORTAL_UTILS_JS, ('withSubmitGuard', 'nyIdempotensNokkel')),
    (OPPDRAG_SENTRAL_JS, ('opprettOppdrag', '_opprettOppdrag', 'nyttOppdragMangler',
                          'nullstillNyttOppdrag')),
)

FORSPILL = """
let nyttOppdragNokkel = null;
const felt = {
  'nytt-hastegrad': { value: 'Akutt', options: [] }, 'nytt-lokasjon': { value: '3', options: [] },
  'nytt-problemstilling': { value: 'Pustevansker', options: [] }, 'nytt-fritekst': { value: '' },
  'nytt-feil': { textContent: '', classList: { add() {}, remove() { feilVist = true; } } },
  'nytt-opprett': { dataset: {}, disabled: false, innerHTML: 'Opprett' },
  'nyttOppdragModal': {},
};
let feilVist = false;
globalThis.document = { getElementById: (id) => felt[id] || null, querySelectorAll: () => [] };
globalThis.bootstrap = { Modal: { getInstance: () => ({ hide() {} }) } };
function _valgteEnheter() { return [5]; }
function hastegradEndret() {} function oppdaterOpprettKnapp() {}
async function lastAlt() {}
const sendt = [];
let svar = { ok: true, status: 200, json: async () => ({ status: 'ok', data: { id: 1 } }) };
globalThis.apiFetch = (url, opts) => new Promise((ok) => {
  sendt.push(JSON.parse(opts.body)); setTimeout(() => ok(svar), 50); });
"""


def _kjor(kode):
    ut = run_node(build_harness(HARNESS), '(async () => {\n' + kode + '\n})();', preamble=FORSPILL)
    return json.loads([l for l in ut.splitlines() if l != 'OK'][0])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KnappenTests(SimpleTestCase):

    def test_tre_raske_trykk_gir_en_sending(self):
        ut = _kjor("""
            await Promise.all([opprettOppdrag(), opprettOppdrag(), opprettOppdrag()]);
            console.log(JSON.stringify(sendt.length));
        """)
        self.assertEqual(ut, 1)

    def test_sendingen_baerer_en_nokkel_og_neste_oppdrag_faar_en_ny(self):
        """Trykk to etter at det første er ferdig er et nytt oppdrag — vinduet er
        lukket og åpnet igjen i virkeligheten, men nøkkelen skal ikke hvile på det."""
        ut = _kjor("""
            nyttOppdragNokkel = 'forste-nokkel-123';
            await opprettOppdrag();
            await opprettOppdrag();
            console.log(JSON.stringify(sendt.map((k) => k.idempotency_key)));
        """)
        self.assertEqual(ut[0], 'forste-nokkel-123')
        self.assertTrue(ut[1])
        self.assertNotEqual(ut[0], ut[1])

    def test_feilet_sending_beholder_nokkelen(self):
        """Et nytt forsøk etter en feil er samme oppdrag — det er hele poenget."""
        ut = _kjor("""
            nyttOppdragNokkel = 'forste-nokkel-123';
            svar = { ok: false, status: 400, json: async () => ({ status: 'error', message: 'nei' }) };
            await opprettOppdrag();
            await opprettOppdrag();
            console.log(JSON.stringify(sendt.map((k) => k.idempotency_key)));
        """)
        self.assertEqual(ut, ['forste-nokkel-123', 'forste-nokkel-123'])

    def test_409_duplikat_er_ingen_feil(self):
        ut = _kjor("""
            svar = { ok: false, status: 409,
                     json: async () => ({ status: 'error', duplikat: true, message: 'x' }) };
            await opprettOppdrag();
            console.log(JSON.stringify(feilVist));
        """)
        self.assertFalse(ut)

    def test_hver_aapning_av_vinduet_faar_en_ny_nokkel(self):
        """Svaret kan gå tapt etter at oppdraget ble laget. Åpner operatøren
        vinduet på nytt og sender, er det et nytt oppdrag hun mener — med den
        gamle nøkkelen ville serveren svart med det forrige."""
        ut = _kjor("""
            nullstillNyttOppdrag();
            const a = nyttOppdragNokkel;
            nullstillNyttOppdrag();
            console.log(JSON.stringify([a, nyttOppdragNokkel]));
        """)
        self.assertTrue(ut[0])
        self.assertNotEqual(ut[0], ut[1])
