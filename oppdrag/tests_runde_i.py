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
from .models import Oppdrag
from .tests_views import OppdragBasis, StemplingBasis, _bruker, _klient


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
        d = self.leser.get('/oppdrag/api/bilinnstillinger/').json()['data']
        self.assertEqual(d['terskler']['Akutt'], [60, 10])
        self.assertTrue(d['nytt_oppdrag'])
        self.assertTrue(d['lyd_aktiv'])
        self.assertFalse(d['krev_grov_avreist'])

    def test_bare_admin_endrer(self):
        kropp = {'terskler': {'Akutt': [30, 5]}, 'nytt_oppdrag': False, 'lyd_aktiv': False, 'krev_grov_avreist': True}
        self.assertEqual(_json(self.leder, 'put', '/oppdrag/api/bilinnstillinger/', kropp).status_code, 403)
        res = _json(self.admin, 'put', '/oppdrag/api/bilinnstillinger/', kropp)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Lydvarsel.objects.get(hastegrad='Akutt').gjenta_sekunder, 5)
        self.assertEqual(verdier.lydvarsel()['Haster'], [300, 60], 'de andre står')
        self.assertFalse(verdier.lyd_ved_nytt_oppdrag())
        self.assertFalse(verdier.lyd_aktiv())
        self.assertTrue(verdier.krev_grov_for_avreist())

    def test_ventevarselet_kan_slaas_av_per_hastegrad(self):
        """«En ting vi må kunne deaktivere lydvarsel per hastegrad (påvirker
        ikke lyd ved nytt oppdrag i listen).» (André, 12. sep. 2026)"""
        d = self.leser.get('/oppdrag/api/bilinnstillinger/').json()['data']
        self.assertEqual(d['aktive'], {'Akutt': True, 'Haster': True, 'Vanlig': True, 'Drift': True})
        res = _json(self.admin, 'put', '/oppdrag/api/bilinnstillinger/', {'aktive': {'Drift': False}})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(verdier.lydvarsel_aktive(), {'Akutt': True, 'Haster': True, 'Vanlig': True, 'Drift': False})
        self.assertEqual(verdier.lydvarsel()['Drift'], [900, 60], 'tersklene står')
        self.assertTrue(verdier.lyd_ved_nytt_oppdrag(), 'pipet ved nytt oppdrag rører den ikke')
        for kropp in ({'aktive': {'Tull': False}}, {'aktive': [True]}):
            self.assertEqual(_json(self.admin, 'put', '/oppdrag/api/bilinnstillinger/', kropp).status_code, 400, kropp)
        d = self.leser.get('/oppdrag/api/bilinnstillinger/').json()['data']
        self.assertFalse(d['aktive']['Drift'])

    def test_ugyldige_tall_avvises(self):
        for kropp in ({'terskler': {'Tull': [1, 5]}}, {'terskler': {'Akutt': [1]}},
                      {'terskler': {'Akutt': [10, 1]}}, {'terskler': 'x'}):
            with self.subTest(kropp=kropp):
                self.assertEqual(_json(self.admin, 'put', '/oppdrag/api/bilinnstillinger/', kropp).status_code, 400)

    def test_sidene_baerer_tersklene(self):
        Lydvarsel.objects.filter(hastegrad='Akutt').update(forste_sekunder=45)
        res = self.leder.get('/oppdrag/')
        self.assertContains(res, 'OPPDRAG_LYDVARSEL')
        self.assertContains(res, '"Akutt": [45, 10]')
        self.assertNotContains(res, 'data-verdifane="bilinnstillinger"', msg_prefix='fanen er admin')
        self.assertContains(self.admin.get('/oppdrag/'), 'data-verdifane="bilinnstillinger"')


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class GrovsorteringKrevesTests(StemplingBasis):
    def _til(self, o, *statuser):
        for st in statuser:
            self.assertEqual(self._stemple(o, st).status_code, 200, st)

    def test_behandlet_og_ledig_etter_leverer_krever_grovsortering(self):
        o = self._oppdrag()
        self._til(o, 'rykker_ut', 'fremme')
        res = self._stemple(o, 'behandlet')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('grovsortering', res.json()['message'])
        self.assertEqual(self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/grovsortering/gul/').status_code, 200)
        self._til(o, 'behandlet')   # lukker med Ledig i samme trykk
        o2 = self._oppdrag()
        self._til(o2, 'rykker_ut', 'fremme', 'avreist', 'leverer')
        self.assertEqual(self._stemple(o2, 'ledig').status_code, 400, 'ikke uten grovsortering')
        self.bil.post(f'/oppdrag/api/oppdrag/{o2.pk}/grovsortering/gronn/')
        self.assertEqual(self._stemple(o2, 'ledig').status_code, 200)

    def test_avreist_krever_bare_naar_admin_sier_det(self):
        from core.models import AppSetting
        o = self._oppdrag()
        self._til(o, 'rykker_ut', 'fremme', 'avreist')
        AppSetting.set(verdier.KREV_GROV_AVREIST_NOKKEL, '1')
        o2 = self._oppdrag()
        self._til(o2, 'rykker_ut', 'fremme')
        self.assertEqual(self._stemple(o2, 'avreist').status_code, 400)

    def test_drift_krever_aldri(self):
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(hastegrad='Drift', problemstilling='Utstyr')
        self._til(o, 'rykker_ut', 'fremme', 'behandlet')
        o.refresh_from_db()
        self.assertEqual(o.status, 'ledig')
        self.assertEqual(verdier.grov_kreves_for(o, 'ledig', 'leverer'), False)


class LydAlltidPaaJsTests(SimpleTestCase):
    LAGER = ("globalThis.localStorage = (() => { const m = {}; return {"
             "getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },"
             "removeItem: (k) => { delete m[k]; } }; })();\n")
    HARNESS = (
        (OPPDRAG_ENHET_JS, ('lydTerskler', '_lydTerskler', 'lydErKlar', 'nyeOppdrag', 'pipNytt', '_tone',
                            'bilinnstillinger', 'erDempet', 'dempNokkel', 'lydSkalSpille', 'grovKrevesFor',
                            'skalPipe', 'ventetSekunder')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = ('globalThis.lydKontekst = null; globalThis.kjenteOppdrag = null;\n'
                        + build_harness(self.HARNESS))

    def test_tersklene_kommer_fra_siden_med_fall_tilbake(self):
        ut = run_node(self.harness, """
            console.log(JSON.stringify(_lydTerskler('Akutt')));
            globalThis.OPPDRAG_BILINNSTILLINGER = { terskler: { Akutt: [30, 5], Haster: [120, 30], Vanlig: [600, 60], Drift: [600, 60] } };
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

    def test_paa_som_standard_dempes_lokalt_og_slaas_av_av_admin(self):
        ut = run_node(self.harness, self.LAGER + """
            globalThis.lydKontekst = { state: 'running' };
            console.log(lydSkalSpille());                                  // på som standard
            localStorage.setItem(dempNokkel(), '1'); console.log(lydSkalSpille());
            localStorage.setItem(dempNokkel(), '0'); console.log(lydSkalSpille());
            globalThis.OPPDRAG_BILINNSTILLINGER = { lyd_aktiv: false }; console.log(lydSkalSpille());
        """)
        self.assertEqual(ut.strip().splitlines()[:4], ['true', 'false', 'true', 'false'])

    def test_ventevarselet_tier_for_hastegrader_admin_har_slaatt_av(self):
        ut = run_node(self.harness, """
            const t0 = Date.UTC(2026, 8, 12, 10, 0, 0);
            const o = (h) => ({ status: 'venter', hastegrad: h, varslet_at: new Date(t0).toISOString() });
            globalThis.OPPDRAG_BILINNSTILLINGER = { terskler: { Akutt: [60, 10], Drift: [60, 10] }, aktive: { Drift: false } };
            console.log(JSON.stringify([skalPipe(o('Akutt'), t0 + 61000, null), skalPipe(o('Drift'), t0 + 61000, null)]));
            globalThis.OPPDRAG_BILINNSTILLINGER = { terskler: { Akutt: [60, 10], Drift: [60, 10] } };
            console.log(JSON.stringify([skalPipe(o('Drift'), t0 + 61000, null)]));
        """)
        l = ut.strip().splitlines()
        self.assertEqual(json.loads(l[0]), [True, False])
        self.assertEqual(json.loads(l[1]), [True], 'uten nøkkel: på')

    def test_grovsortering_kreves_der_serveren_krever_den(self):
        ut = run_node(self.harness, """
            const o = (status, h) => ({ status, hastegrad: h || 'Akutt' });
            globalThis.OPPDRAG_BILINNSTILLINGER = { krev_grov_avreist: false };
            console.log(JSON.stringify([
              grovKrevesFor(o('fremme'), 'behandlet'), grovKrevesFor(o('leverer'), 'ledig'),
              grovKrevesFor(o('fremme'), 'avreist'), grovKrevesFor(o('behandlet'), 'ledig'),
              grovKrevesFor(o('fremme', 'Drift'), 'behandlet')]));
            globalThis.OPPDRAG_BILINNSTILLINGER = { krev_grov_avreist: true };
            console.log(JSON.stringify([grovKrevesFor(o('fremme'), 'avreist'), grovKrevesFor(o('fremme', 'Drift'), 'avreist')]));
        """)
        l = ut.strip().splitlines()
        self.assertEqual(json.loads(l[0]), [True, True, False, False, False])
        self.assertEqual(json.loads(l[1]), [True, False])


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
        for h in ('Akutt', 'Haster', 'Vanlig', 'Drift'):
            self.assertIn(f'id="lyd-aktiv-{h}" checked', ut, 'på når nøkkelen mangler')
        ut = run_node(self.harness, """
            console.log(_lydvarselSkjema({ terskler: {}, aktive: { Drift: false, Akutt: true } }));
        """)
        self.assertIn('id="lyd-aktiv-Akutt" checked', ut)
        self.assertIn('id="lyd-aktiv-Drift"', ut)
        self.assertNotIn('id="lyd-aktiv-Drift" checked', ut)
