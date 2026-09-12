"""Andrés forbedringsliste 12. sep. 2026, lydvarselet.

«Nå er det slik at vi får en knapp med lyd av/på. Det skal ikke være et
alternativ. Og så må vi endre på varslingen til noe som er litt lengre i
varighet. Uthevingen er fin. Det bør og komme en utheving hos operatør.
Admin kan justere frekvens på lydvarsler, både første gangs og repeterende,
på de ulike hastegradene. Samt om lydvarsel skal gis når enheten får nytt
oppdrag.»
"""
import json

from django.test import SimpleTestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
    node_available, run_node)

from . import verdier
from .models import Lydvarsel
from .tests_runde_d import _konst
from .tests_views import OppdragBasis, _bruker, _klient


def _json(klient, metode, url, data=None):
    return getattr(klient, metode)(url, data=json.dumps(data) if data is not None else None,
                                   content_type='application/json')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class LydvarselApiTests(OppdragBasis):
    def setUp(self):
        super().setUp()
        self.leser = _klient(_bruker('leser_i', 'les'))
        self.leder = _klient(_bruker('leder_i', 'skriv_leder'))
        self.admin = _klient(_bruker('adm_i', admin=True))

    def test_seedet_med_forste_utgaves_tall(self):
        self.assertEqual(verdier.lydvarsel(), {
            'Akutt': [60, 10], 'Haster': [300, 60], 'Vanlig': [900, 60], 'Drift': [900, 60]})
        self.assertTrue(verdier.lyd_ved_nytt_oppdrag())
        d = self.leser.get('/oppdrag/api/lydvarsel/').json()['data']
        self.assertEqual(d['terskler']['Akutt'], [60, 10])
        self.assertTrue(d['nytt_oppdrag'])

    def test_bare_admin_endrer(self):
        kropp = {'terskler': {'Akutt': [30, 5]}, 'nytt_oppdrag': False}
        self.assertEqual(_json(self.leder, 'put', '/oppdrag/api/lydvarsel/', kropp).status_code, 403)
        res = _json(self.admin, 'put', '/oppdrag/api/lydvarsel/', kropp)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Lydvarsel.objects.get(hastegrad='Akutt').gjenta_sekunder, 5)
        self.assertEqual(verdier.lydvarsel()['Haster'], [300, 60], 'de andre står')
        self.assertFalse(verdier.lyd_ved_nytt_oppdrag())

    def test_ugyldige_tall_avvises(self):
        for kropp in ({'terskler': {'Tull': [1, 5]}}, {'terskler': {'Akutt': [1]}},
                      {'terskler': {'Akutt': [10, 1]}}, {'terskler': 'x'}):
            with self.subTest(kropp=kropp):
                self.assertEqual(_json(self.admin, 'put', '/oppdrag/api/lydvarsel/', kropp).status_code, 400)

    def test_sidene_baerer_tersklene(self):
        Lydvarsel.objects.filter(hastegrad='Akutt').update(forste_sekunder=45)
        res = self.leder.get('/oppdrag/')
        self.assertContains(res, 'OPPDRAG_LYDVARSEL')
        self.assertContains(res, '"Akutt": [45, 10]')
        self.assertNotContains(res, 'data-verdifane="lydvarsel"', msg_prefix='fanen er admin')
        self.assertContains(self.admin.get('/oppdrag/'), 'data-verdifane="lydvarsel"')


class LydAlltidPaaJsTests(SimpleTestCase):
    HARNESS = (
        (OPPDRAG_ENHET_JS, ('lydTerskler', '_lydTerskler', 'lydErKlar', 'nyeOppdrag', 'pipNytt', '_tone')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = ('globalThis.lydKontekst = null; globalThis.kjenteOppdrag = null;\n'
                        + build_harness(self.HARNESS))

    def test_tersklene_kommer_fra_siden_med_fall_tilbake(self):
        ut = run_node(self.harness, """
            console.log(JSON.stringify(_lydTerskler('Akutt')));
            globalThis.OPPDRAG_LYDVARSEL = { Akutt: [30, 5], Haster: [120, 30], Vanlig: [600, 60], Drift: [600, 60] };
            console.log(JSON.stringify(_lydTerskler('Akutt')));
            console.log(JSON.stringify(_lydTerskler('Ukjent')));
        """)
        l = ut.strip().splitlines()
        self.assertEqual(json.loads(l[0]), [60, 10])
        self.assertEqual(json.loads(l[1]), [30, 5])
        self.assertEqual(json.loads(l[2]), [600, 60], 'ukjent hastegrad følger Vanlig')

    def test_nytt_oppdrag_piper_bare_for_det_som_kom_etter_forste_lasting(self):
        ut = run_node(self.harness, """
            console.log(JSON.stringify(nyeOppdrag([{id: 1}, {id: 2}])));
            console.log(JSON.stringify(nyeOppdrag([{id: 1}, {id: 2}, {id: 3}])));
            console.log(JSON.stringify(nyeOppdrag([{id: 3}])));
            console.log(JSON.stringify(nyeOppdrag([{id: 1}])));
        """)
        l = [json.loads(x) for x in ut.strip().splitlines()[:4]]
        self.assertEqual(l, [[], [3], [], []])

    def test_lyden_er_klar_bare_naar_nettleseren_har_sluppet_den(self):
        ut = run_node(self.harness, """
            console.log(lydErKlar());
            globalThis.lydKontekst = { state: 'suspended' }; console.log(lydErKlar());
            globalThis.lydKontekst = { state: 'running' }; console.log(lydErKlar());
        """)
        self.assertEqual(ut.strip().splitlines()[:3], ['false', 'false', 'true'])


class UthevingHosOperatorJsTests(SimpleTestCase):
    HARNESS = ((OPPDRAG_SENTRAL_JS, ('venterForbiTerskel', 'lydTerskler')),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_raden_uthevs_forbi_forste_terskel(self):
        ut = run_node(self.harness, """
            globalThis.window = { OPPDRAG_LYDVARSEL: { Akutt: [60, 10], Haster: [300, 60], Vanlig: [900, 60], Drift: [900, 60] } };
            const t0 = Date.UTC(2026, 8, 12, 10, 0, 0);
            const o = (h, sek, status) => ({ status: status || 'venter', hastegrad: h, trenger_ressurs: false,
              enheter: [{ status: 'venter', varslet_at: new Date(t0).toISOString() },
                        { status: 'ledig', varslet_at: new Date(t0 - 3600000).toISOString() }] });
            console.log(JSON.stringify([
              venterForbiTerskel(o('Akutt'), t0 + 59000), venterForbiTerskel(o('Akutt'), t0 + 60000),
              venterForbiTerskel(o('Haster'), t0 + 60000), venterForbiTerskel(o('Haster'), t0 + 300000),
              venterForbiTerskel(o('Akutt', 0, 'rykker_ut'), t0 + 999000),
              venterForbiTerskel({ ...o('Akutt'), trenger_ressurs: true }, t0 + 999000),
              venterForbiTerskel({ status: 'venter', hastegrad: 'Akutt', enheter: [] }, t0 + 999000),
            ]));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]),
                         [False, True, False, True, False, False, False])


class LydvarselSkjemaJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (OPPDRAG_SENTRAL_JS, ('_lydvarselSkjema',)),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = _konst(OPPDRAG_SENTRAL_JS, 'HASTEGRAD_REKKEFOLGE') + build_harness(self.HARNESS)

    def test_en_rad_per_hastegrad_og_bryteren(self):
        ut = run_node(self.harness, """
            console.log(_lydvarselSkjema({ terskler: { Akutt: [60, 10], Haster: [300, 60], Vanlig: [900, 60], Drift: [900, 60] },
                                           nytt_oppdrag: true }));
        """)
        for h in ('Akutt', 'Haster', 'Vanlig', 'Drift'):
            self.assertIn(f'id="lyd-forste-{h}"', ut)
            self.assertIn(f'id="lyd-gjenta-{h}"', ut)
        self.assertIn('value="60"', ut)
        self.assertIn('id="lyd-nytt" checked', ut)
        self.assertIn('lagreLydvarsel', ut)
