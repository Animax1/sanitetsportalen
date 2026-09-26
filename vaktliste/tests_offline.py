"""Offline drift på /vaktliste/ (13. sep. 2026) — reserve 2.

Service workeren holder siden og siste liste lokalt; møtt/av vakt legges i
kø når serveren ikke svarer og sendes når den svarer igjen, med tida
trykket skjedde. Workeren testes som ren funksjon (`avgjor`), køen som
node-harness, og serverens tidsregel direkte.
"""
import json
from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from patients.js_test_utils import (
    JS_DIR, PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness, node_available,
    read_js, run_node,
)

from . import services
from .models import Vaktpost
from .tests_tilgang import TilgangsBasis

SW_JS = JS_DIR / 'vaktliste-sw.js'


class KlienttidTests(SimpleTestCase):
    def test_rimelig_klienttid_brukes_ellers_servertid(self):
        naa = timezone.now()
        self.assertEqual(services.vurder_klienttid(None, naa), naa)
        for_en_time_siden = naa - timedelta(hours=1)
        self.assertEqual(services.vurder_klienttid(for_en_time_siden, naa), for_en_time_siden)
        self.assertEqual(services.vurder_klienttid(naa + timedelta(seconds=30), naa), naa,
                         'litt fram i tid: klokkeslingring, ikke framtid — klippes til nå')
        self.assertEqual(services.vurder_klienttid(naa + timedelta(minutes=10), naa), naa,
                         'framtid: servertid')
        self.assertEqual(services.vurder_klienttid(naa - timedelta(days=2), naa), naa,
                         'eldre enn et døgn: servertid')


class StemplingMedTidspunktTests(TilgangsBasis):
    def setUp(self):
        super().setUp()
        self.vl.status = 'drift'
        self.vl.save()
        self.vp = Vaktpost.objects.create(
            ressurs=self.res_hgsd, mannskap=self.p_hgsd,
            fra_tid=self.na, til_tid=self.na + timedelta(hours=8))

    def _stemple(self, handling, kropp=None):
        return self.c_vl.post(f'/vaktliste/api/vaktposter/{self.vp.pk}/stempling/{handling}/',
                              data=json.dumps(kropp) if kropp is not None else None,
                              content_type='application/json')

    def test_tidspunktet_fra_koen_blir_stempelet(self):
        da = timezone.now() - timedelta(minutes=40)
        res = self._stemple('mott', {'tidspunkt': da.isoformat()})
        self.assertEqual(res.status_code, 200, res.content)
        self.vp.refresh_from_db()
        self.assertEqual(self.vp.mott_at, da.replace(microsecond=self.vp.mott_at.microsecond))
        self.assertLess(abs((self.vp.mott_at - da).total_seconds()), 1)

    def test_uten_kropp_som_for(self):
        res = self._stemple('mott')
        self.assertEqual(res.status_code, 200, res.content)
        self.vp.refresh_from_db()
        self.assertLess(abs((timezone.now() - self.vp.mott_at).total_seconds()), 5)

    def test_ugyldig_tidspunkt_avvises(self):
        res = self._stemple('mott', {'tidspunkt': 'i går'})
        self.assertEqual(res.status_code, 400)

    def test_gammelt_tidspunkt_gir_servertid(self):
        res = self._stemple('mott', {'tidspunkt': (timezone.now() - timedelta(days=3)).isoformat()})
        self.assertEqual(res.status_code, 200)
        self.vp.refresh_from_db()
        self.assertLess(abs((timezone.now() - self.vp.mott_at).total_seconds()), 5)


class ServiceWorkerViewTests(TilgangsBasis):
    def test_serveres_under_vaktliste_uten_innlogging(self):
        from django.test import Client
        res = Client().get('/vaktliste/sw.js')
        self.assertEqual(res.status_code, 200)
        self.assertIn('application/javascript', res['Content-Type'])
        self.assertEqual(res['Cache-Control'], 'no-cache')
        self.assertEqual(res['Service-Worker-Allowed'], '/vaktliste/')
        self.assertNotIn('https://', res['Content-Security-Policy'],
                         'bibliotekene ligger under /static/ — ingen CDN (H3)')
        self.assertIn("addEventListener('fetch'", res.content.decode())

    def test_siden_registrerer_workeren(self):
        html = self.c_vl.get('/vaktliste/').content.decode()
        self.assertIn('id="vl-offline"', html)
        self.assertIn('id="vl-offline-klar"', html)
        js = read_js(VAKTLISTE_JS)
        self.assertIn("serviceWorker.register('/vaktliste/sw.js')", js)


class WorkerensRegelJsTests(SimpleTestCase):
    HARNESS = ((SW_JS, ('avgjor', 'kanLagres')),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        # `build_harness` tar bare toppnivå-funksjoner; konstanten hentes fra fila.
        from oppdrag.tests_runde_d import _konst
        self.harness = ("globalThis.self = { addEventListener: () => {} };\n"
                        + _konst(SW_JS, 'CDN') + build_harness(self.HARNESS))

    def test_avgjor(self):
        ut = run_node(self.harness, """
            const o = 'https://portal.example';
            const a = (u, m, mode) => avgjor(u, m || 'GET', mode || 'cors', o);
            console.log(JSON.stringify([
              a(o + '/vaktliste/api/vaktlister/3/'),
              a(o + '/vaktliste/api/vaktlister/3/', 'POST'),
              a(o + '/vaktliste/api/vaktlister/3/fil/'),
              a(o + '/vaktliste/', 'GET', 'navigate'),
              a(o + '/oppdrag/', 'GET', 'navigate'),
              a(o + '/vaktliste/sw.js'),
              a(o + '/static/js/vaktliste.abc123.js'),
              a('https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css'),   // ikke lenger vår
              a('https://evil.example/x.js'),
              a(o + '/accounts/login/', 'GET', 'navigate'),
            ]));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]),
                         ['api', None, None, 'side', None, None, 'statisk', None, None, None])

    def test_omdirigering_og_feil_lagres_ikke(self):
        ut = run_node(self.harness, """
            console.log(JSON.stringify([
              kanLagres({ ok: true, redirected: false, status: 200 }),
              kanLagres({ ok: true, redirected: true, status: 200 }),   // innloggingssiden
              kanLagres({ ok: false, redirected: false, status: 500 }),
              kanLagres({ ok: true, redirected: false, status: 206 }),
              kanLagres(null),
            ]));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [True, False, False, False, False])

    def test_workeren_rorer_ingenting_som_ikke_er_get(self):
        """Regelen kjøres, ikke leses (14. sep. 2026, gjeldspunkt 3.8).

        Testen sammenlignet før mot den literale linja `if (metode !== 'GET')
        return null;`. Den ville gått i stykker av en omskriving som gjorde
        nøyaktig det samme — og, verre, gått **grønn** hvis noen skrev
        `metode === 'POST'` et annet sted i fila og latt PUT slippe gjennom.

        Her prøves hver metode som ikke er GET. Det er den regelen som betyr
        noe: en stempling som havner i cachen og spilles av igjen, er en
        dobbeltføring på en vaktliste.
        """
        ut = run_node(self.harness, """
            const o = 'https://portal.example';
            const m = ['POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];
            console.log(JSON.stringify(
              m.map(x => avgjor(o + '/vaktliste/api/vaktlister/3/', x, 'cors', o))));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [None] * 6)


class KoenJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('koNokkel', 'koLes', 'koSkriv', '_leggIKo', '_brukLokalt', '_projiserKo',
                        '_sesjonUtgaatt', 'tegnOffline', '_tegnOfflineKlar', '_dag', '_kl', '_d')),
    )
    LAGER = ("globalThis.localStorage = (() => { const m = {}; return {"
             "getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); },"
             "removeItem: (k) => { delete m[k]; } }; })();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun','jul','aug','sep','okt','nov','des'];\n"
             "globalThis.offlineTilstand = { frakoblet: false, kopiFra: null, sesjonUtgaatt: false, sistFeil: '' };\n"
             "globalThis.tegn = () => {};\n"
             "const banner = { className: '', textContent: '', classList: { toggle: () => {} } };\n"
             "globalThis.document = { getElementById: (id) => id === 'vl-offline' ? banner : null };\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = self.LAGER + build_harness(self.HARNESS)

    def test_koen_leses_og_skrives_og_taaler_rot(self):
        ut = run_node(self.harness, """
            console.log(JSON.stringify(koLes()));
            localStorage.setItem(koNokkel(), '{"ikke": "en liste"}');
            console.log(JSON.stringify(koLes()));
            koSkriv([{ vaktpostId: 1, handling: 'mott' }]);
            console.log(JSON.stringify(koLes().map((k) => k.handling)));
        """)
        l = ut.strip().splitlines()
        self.assertEqual(json.loads(l[0]), [])
        self.assertEqual(json.loads(l[1]), [], 'rot i lageret er en tom kø')
        self.assertEqual(json.loads(l[2]), ['mott'])

    def test_projeksjonen_legger_koen_paa_lista(self):
        ut = run_node(self.harness, """
            globalThis.aktivListe = { vaktliste: { id: 5 }, vaktposter: [
              { id: 1, mott_at: null, av_vakt_at: null, er_tilstede: false },
              { id: 2, mott_at: '2026-09-13T06:00:00Z', av_vakt_at: null, er_tilstede: true },
              { id: 3, mott_at: '2026-09-13T06:00:00Z', av_vakt_at: null, er_tilstede: true }] };
            aktivListe.alle_vaktposter = aktivListe.vaktposter;
            _leggIKo(1, 'mott', '2026-09-13T08:04:00Z');
            _leggIKo(2, 'av_vakt', '2026-09-13T08:05:00Z');
            _leggIKo(3, 'angre_mott', '2026-09-13T08:06:00Z');
            const v = aktivListe.vaktposter;
            console.log(JSON.stringify([v[0].mott_at, v[0].er_tilstede, v[0].i_ko,
                                        v[1].av_vakt_at, v[1].er_tilstede,
                                        v[2].mott_at, v[2].er_tilstede, koLes().length,
                                        koLes()[0].vaktlisteId]));
            // Lista lastes på nytt fra serveren uten trykkene: projeksjonen legger dem på igjen.
            aktivListe.vaktposter = [{ id: 1, mott_at: null, av_vakt_at: null, er_tilstede: false }];
            aktivListe.alle_vaktposter = aktivListe.vaktposter;
            _projiserKo();
            console.log(JSON.stringify([aktivListe.vaktposter[0].mott_at, aktivListe.vaktposter[0].i_ko]));
        """)
        l = ut.strip().splitlines()
        self.assertEqual(json.loads(l[0]), ['2026-09-13T08:04:00Z', True, True,
                                            '2026-09-13T08:05:00Z', False,
                                            None, False, 3, 5])
        self.assertEqual(json.loads(l[1]), ['2026-09-13T08:04:00Z', True])

    def test_utgaatt_innlogging_gjenkjennes(self):
        ut = run_node(self.harness, """
            console.log(JSON.stringify([
              _sesjonUtgaatt({ status: 200, redirected: true, url: 'https://p/accounts/login/?next=/vaktliste/' }),
              _sesjonUtgaatt({ status: 200, redirected: false, url: 'https://p/vaktliste/api/x/' }),
              _sesjonUtgaatt({ status: 403 }),
              _sesjonUtgaatt({ status: 400 }),
              _sesjonUtgaatt(null),
            ]));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]), [True, False, True, False, False])

    def test_banneret_sier_det_som_gjelder(self):
        ut = run_node(self.harness, """
            const les = () => banner.className + ' | ' + banner.textContent;
            tegnOffline(); console.log(les());
            koSkriv([{ vaktpostId: 1, handling: 'mott' }, { vaktpostId: 2, handling: 'mott' }]);
            tegnOffline(); console.log(les());
            offlineTilstand.frakoblet = true; offlineTilstand.kopiFra = '2026-09-13T10:04:00Z';
            tegnOffline(); console.log(les());
            offlineTilstand.sesjonUtgaatt = true;
            tegnOffline(); console.log(les());
            offlineTilstand = { frakoblet: false, kopiFra: null, sesjonUtgaatt: false, sistFeil: 'Personen står ikke som møtt.' };
            koSkriv([]);
            tegnOffline(); console.log(les());
        """)
        l = ut.strip().splitlines()
        self.assertIn('d-none', l[0])
        self.assertIn('Sender… 2 stemplinger venter', l[1])
        self.assertIn('Serveren svarer ikke.', l[2])
        self.assertIn('slik den var', l[2])
        self.assertIn('2 stemplinger venter', l[2])
        self.assertIn('Innloggingen har gått ut', l[3])
        self.assertIn('alert-danger', l[4])
        self.assertIn('Personen står ikke som møtt', l[4])


class SwUtkastingTests(SimpleTestCase):
    """`activate` skal kaste de gamle cachene når `VERSJON` bumpes.

    Bumpen er **grunnen** til at versjonen finnes — `vl-sw-5` ble satt 14. sep.
    2026 fordi `vaktliste.js` ble delt i fem filer, og samlefila lå igjen som
    død vekt i skallcachen på hver drifts-PC som hadde vært innom. Fram til da
    var utkastingen udekket, altså den ene oppførselen bumpen hviler på.

    **Regelen er skilt ut som `skalKastes()`** og ikke en anonym `filter` inne
    i lytteren, av samme grunn som `avgjor()` og `klikkSkalKjore()`: en regel
    som ikke lar seg kalle, lar seg ikke prøve. Mitt første forsøk her kopierte
    kroppen inn i testen som en streng — da måler testen kopien sin, og går
    grønn uansett hva workeren gjør.
    """

    HARNESS = ((SW_JS, ('skalKastes',)),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        # `VERSJON` er en toppnivåkonstant og må med i harnessen.
        versjon = [l for l in read_js(SW_JS).splitlines()
                   if l.startswith('const VERSJON')][0]
        self.harness = versjon + '\n' + build_harness(self.HARNESS)

    def _kastes(self, *navn):
        ut = run_node(self.harness, 'console.log(JSON.stringify([%s].filter(skalKastes)));'
                      % ', '.join(repr(n) for n in navn))
        # Svaret står først; harnessen skriver «OK» på siste linje.
        return json.loads(ut.strip().splitlines()[0])

    def test_forrige_versjon_kastes(self):
        self.assertEqual(
            self._kastes('vl-sw-4-skall', 'vl-sw-4-data'),
            ['vl-sw-4-skall', 'vl-sw-4-data'])

    def test_gjeldende_versjon_staar(self):
        """Kastes den gjeldende, tømmer workeren seg selv ved hver oppstart —
        og offline-drift slutter å virke uten at noe feiler."""
        self.assertEqual(self._kastes('vl-sw-5-skall', 'vl-sw-5-data'), [])

    def test_fremmede_cacher_rores_ikke(self):
        """Workeren deler origin med resten av portalen; `caches.keys()` kan
        inneholde noe den ikke eier."""
        self.assertEqual(self._kastes('noe-helt-annet', 'django-cache'), [])

    def test_tosifret_versjon_forveksles_ikke(self):
        """`startsWith` er et prefiks. `vl-sw-40` er ikke `vl-sw-4`, og en
        cache fra en helt annen versjon skal kastes, ikke bli stående."""
        self.assertEqual(self._kastes('vl-sw-40-skall'), ['vl-sw-40-skall'])

    def test_versjonen_leses_fra_fila_og_ikke_fra_testen(self):
        """Sperrehake: forsvinner `VERSJON` i en refaktorering, måler prøvene
        over en streng testen selv fant på."""
        self.assertIn("const VERSJON = 'vl-sw-", read_js(SW_JS))


class SkallcachenVokserIkkeTests(SimpleTestCase):
    """En ny hash av en fil kaster de eldre utgavene (26. sep. 2026, G5).

    Går gjennom `kopiForst` — den ekte inngangen — med en falsk `caches` og
    `fetch`, så kallstedet ikke kan forsvinne mens hjelperen står og består.
    """

    HARNESS = ((SW_JS, ('filnokkel', 'ryddEldreUtgaver', 'kopiForst')),)

    FORSPANN = """
const lager = new Map();
const cacheObj = {
  match: async (req) => lager.get(req.url),
  put: async (req, svar) => { lager.set(req.url, svar); },
  keys: async () => [...lager.keys()].map((url) => ({ url })),
  delete: async (req) => lager.delete(req.url),
};
globalThis.caches = { open: async () => cacheObj };
globalThis.fetch = async (req) => ({ ok: true, clone() { return this; } });
const R = (sti) => ({ url: 'https://portal.test' + sti });
"""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, kropp):
        return run_node(self.harness, '(async () => {' + kropp + '})().catch((e) => {'
                        ' console.error(e); process.exit(1); });', preamble=self.FORSPANN)

    def test_filnokkelen(self):
        self._kjor("""
assert(filnokkel('https://p.t/static/js/a.1a2b3c4d5e6f.js') === 'https://p.t/static/js/a.js', 'js');
assert(filnokkel('https://p.t/static/css/b.min.0123456789ab.css') === 'https://p.t/static/css/b.min.css', 'min.css');
assert(filnokkel('https://p.t/static/js/a.js') === 'https://p.t/static/js/a.js', 'uten hash');
assert(filnokkel('https://p.t/static/js/a.1a2b3c.js') === 'https://p.t/static/js/a.1a2b3c.js', 'for kort hash');
""")

    def test_ny_hash_kaster_den_gamle_og_rorer_ikke_andre_filer(self):
        self._kjor("""
await kopiForst(R('/static/js/a.111111111111.js'), 'skall');
await kopiForst(R('/static/js/b.222222222222.js'), 'skall');
await kopiForst(R('/static/js/a.333333333333.js'), 'skall');
await new Promise((r) => setTimeout(r, 0));
const urls = [...lager.keys()].sort();
assert(JSON.stringify(urls) === JSON.stringify([
  'https://portal.test/static/js/a.333333333333.js',
  'https://portal.test/static/js/b.222222222222.js']), JSON.stringify(urls));
""")
