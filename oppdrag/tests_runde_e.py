"""Andrés runde på staging 12. sep. 2026, del E — verdimengdene som tabeller.

«Admin må kunne redigere listen over problemstillinger blant annet hvor de
skal stå i rekkefølgen i nedtrekksvinduet. Samme gjelder med rekkefølge på
lokasjoner og grupperinger.» Og: «bilen må sette antall pasienter ikke
operatøren … hvis den er blank så må det stå 1 pasient».
"""
import json
import re

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from patients.js_test_utils import (
    OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
    node_available, run_node)

from . import choices, verdier
from .models import Enhet, Enhetstype, Lokasjon, Oppdrag, Problemstilling
from .tests_runde_d import _konst
from .tests_views import OppdragBasis, StemplingBasis, _bruker, _klient


def _json(klient, metode, url, data=None):
    return getattr(klient, metode)(url, data=json.dumps(data) if data is not None else None,
                                   content_type='application/json')


class VerdimengdeApiTests(OppdragBasis):
    """Tre tabeller, samme tre endepunkter. `les` leser, `skriv_leder`
    setter opp, global admin sletter."""

    SLUGS = ('lokasjoner', 'enhetstyper', 'problemstillinger')

    def setUp(self):
        super().setUp()
        self.leser = _klient(_bruker('leser_e', 'les'))
        self.sentral = _klient(_bruker('sentral_e', 'skriv_full'))
        self.leder = _klient(_bruker('leder_e', 'skriv_leder'))
        self.admin = _klient(_bruker('adm_e', admin=True))

    def test_les_ser_alle_tre_listene(self):
        for slug in self.SLUGS:
            with self.subTest(slug=slug):
                res = self.leser.get(f'/oppdrag/api/{slug}/')
                self.assertEqual(res.status_code, 200)
                self.assertTrue(res.json()['data'], 'seedet, eller lokasjonen fra oppsettet')
                self.assertIn('ETag', res)

    def test_skriv_full_setter_ikke_opp_men_skriv_leder_og_admin_gjor(self):
        for slug in self.SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(_json(self.sentral, 'post', f'/oppdrag/api/{slug}/', {'navn': 'Ny'}).status_code, 403)
                res = _json(self.leder, 'post', f'/oppdrag/api/{slug}/', {'navn': 'Ny ' + slug})
                self.assertEqual(res.status_code, 200, res.content)
                pk = res.json()['data']['id']
                self.assertEqual(_json(self.sentral, 'put', f'/oppdrag/api/{slug}/{pk}/', {'navn': 'X'}).status_code, 403)
                self.assertEqual(_json(self.leder, 'put', f'/oppdrag/api/{slug}/{pk}/', {'navn': 'Endret'}).status_code, 200)
                self.assertEqual(_json(self.admin, 'put', f'/oppdrag/api/{slug}/{pk}/', {'er_aktiv': False}).status_code, 200)
                self.assertEqual(_json(self.leder, 'delete', f'/oppdrag/api/{slug}/{pk}/', {'confirm': True}).status_code, 403)
                self.assertEqual(_json(self.admin, 'delete', f'/oppdrag/api/{slug}/{pk}/', {}).status_code, 400, 'bekreftelse')
                self.assertEqual(_json(self.admin, 'delete', f'/oppdrag/api/{slug}/{pk}/', {'confirm': True}).status_code, 200)

    def test_ny_rad_havner_sist_og_rekkefolgen_settes_med_hele_lista(self):
        res = _json(self.leder, 'post', '/oppdrag/api/lokasjoner/', {'navn': 'Sist'})
        ider = [r['id'] for r in self.leder.get('/oppdrag/api/lokasjoner/').json()['data']]
        self.assertEqual(ider[-1], res.json()['data']['id'])
        snudd = list(reversed(ider))
        res = _json(self.leder, 'put', '/oppdrag/api/lokasjoner/rekkefolge/', {'ider': snudd})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual([r['id'] for r in res.json()['data']], snudd)
        self.assertEqual([r['id'] for r in self.leser.get('/oppdrag/api/lokasjoner/').json()['data']], snudd)
        self.assertEqual(_json(self.sentral, 'put', '/oppdrag/api/lokasjoner/rekkefolge/', {'ider': ider}).status_code, 403)
        self.assertEqual(_json(self.leder, 'put', '/oppdrag/api/lokasjoner/rekkefolge/', {'ider': [999999]}).status_code, 400)
        self.assertEqual(_json(self.leder, 'put', '/oppdrag/api/lokasjoner/rekkefolge/', {'ider': 'x'}).status_code, 400)

    def test_duplikat_og_tomt_navn_avvises(self):
        self.assertEqual(_json(self.leder, 'post', '/oppdrag/api/lokasjoner/', {'navn': ' '}).status_code, 400)
        self.assertEqual(_json(self.leder, 'post', '/oppdrag/api/lokasjoner/', {'navn': 'Hovedscene'}).status_code, 400)

    def test_enhetstype_med_biler_kan_ikke_slettes(self):
        typ = Enhetstype.objects.get(navn='Ambulanse')
        self.enhet.enhetstype = typ
        self.enhet.save()
        res = _json(self.admin, 'delete', f'/oppdrag/api/enhetstyper/{typ.pk}/', {'confirm': True})
        self.assertEqual(res.status_code, 409, res.content)
        self.assertIn('enheter', res.json()['message'])
        rad = next(r for r in self.leser.get('/oppdrag/api/enhetstyper/').json()['data'] if r['id'] == typ.pk)
        self.assertEqual(rad['i_bruk'], 1)

    def test_udefinert_er_fast(self):
        pk = Problemstilling.objects.get(navn=choices.UDEFINERT).pk
        for kropp in ({'navn': 'Ukjent'}, {'er_aktiv': False}, {'kategori': 'drift'}):
            with self.subTest(kropp=kropp):
                res = _json(self.leder, 'put', f'/oppdrag/api/problemstillinger/{pk}/', kropp)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn('fast', res.json()['message'])
        self.assertEqual(_json(self.admin, 'delete', f'/oppdrag/api/problemstillinger/{pk}/', {'confirm': True}).status_code, 400)
        rad = self.leser.get('/oppdrag/api/problemstillinger/').json()['data'][0]
        self.assertEqual((rad['navn'], rad['fast']), (choices.UDEFINERT, True), 'og står først')

    def test_problemstilling_baerer_kategori_og_antall(self):
        res = _json(self.leder, 'post', '/oppdrag/api/problemstillinger/',
                    {'navn': 'Båretransport', 'kategori': 'begge', 'med_antall': True})
        self.assertEqual(res.status_code, 200, res.content)
        d = res.json()['data']
        self.assertEqual((d['kategori'], d['med_antall']), ('begge', True))
        self.assertIn('Båretransport', verdier.problemstillinger_for('Akutt'))
        self.assertIn('Båretransport', verdier.problemstillinger_for('Drift'))
        self.assertIn('Båretransport', verdier.med_antall())
        self.assertEqual(_json(self.leder, 'put', f'/oppdrag/api/problemstillinger/{d["id"]}/',
                               {'kategori': 'tull'}).status_code, 400)
        _json(self.leder, 'put', f'/oppdrag/api/problemstillinger/{d["id"]}/', {'kategori': 'drift'})
        self.assertNotIn('Båretransport', verdier.problemstillinger_for('Akutt'))

    def test_ny_problemstilling_kan_brukes_og_deaktivert_kan_ikke(self):
        _json(self.leder, 'post', '/oppdrag/api/problemstillinger/', {'navn': 'Solstikk', 'kategori': 'medisinsk'})
        data = {'enhet_ider': [self.enhet.pk], 'lokasjon_id': self.lokasjon.pk,
                'hastegrad': 'Akutt', 'problemstilling': 'Solstikk'}
        res = _json(self.sentral, 'post', '/oppdrag/api/oppdrag/', data)
        self.assertEqual(res.status_code, 200, res.content)
        o = Oppdrag.objects.get(pk=res.json()['data']['id'])
        Problemstilling.objects.filter(navn='Solstikk').update(er_aktiv=False)
        self.assertEqual(_json(self.sentral, 'post', '/oppdrag/api/oppdrag/', data).status_code, 400,
                         'deaktivert: kan ikke velges på nytt')
        res = _json(self.sentral, 'put', f'/oppdrag/api/oppdrag/{o.pk}/', {'fritekst': 'rettet'})
        self.assertEqual(res.status_code, 200, 'men oppdraget som har den kan fortsatt redigeres')
        res = _json(self.sentral, 'put', f'/oppdrag/api/oppdrag/{o.pk}/', {'hastegrad': 'Haster'})
        self.assertEqual(res.status_code, 200, 'også hastegraden, så lenge paret passer')
        self.assertEqual(_json(self.sentral, 'post', '/oppdrag/api/oppdrag/',
                               {**data, 'problemstilling': 'Finnes ikke'}).status_code, 400)

    def test_enhetslista_er_alfabetisk_uten_hensyn_til_store_bokstaver(self):
        """Og norsk (26. sep. 2026). Testen sto med «ålesund 1» og var grønn
        lokalt og rød i CI: C.UTF-8 la den sist, en_US først (å leses som a).
        Den prøvde maskinen. Med `Norsk('navn')` er rekkefølgen lik overalt,
        og «ålesund» kunne komme tilbake."""
        Enhet.objects.create(navn='voss 1')
        Enhet.objects.create(navn='bergen 2')
        Enhet.objects.create(navn='ålesund 1')
        navn = [e['navn'] for e in self.leser.get('/oppdrag/api/enheter/').json()['data']]
        # Bytealfabetet ville satt de små bokstavene sist; en_US «ålesund» først.
        self.assertEqual(navn, ['bergen 2', 'Haugesund 56', 'Karmøy 12', 'voss 1', 'ålesund 1'])


class AntallFraBilenTests(StemplingBasis):
    def _transport(self):
        o = self._oppdrag()
        Oppdrag.objects.filter(pk=o.pk).update(problemstilling='Transport', hastegrad='Drift')
        o.refresh_from_db()
        return o

    def test_bilen_setter_antallet(self):
        o = self._transport()
        res = self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/antall/3/')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['data']['antall'], 3)
        o.refresh_from_db()
        self.assertEqual(o.antall, 3)
        self.assertEqual(self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/antall/0/').status_code, 400)
        self.assertEqual(self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/antall/1000/').status_code, 400)

    def test_bare_der_problemstillingen_baerer_antall(self):
        o = self._oppdrag()   # Pustevansker
        res = self.bil.post(f'/oppdrag/api/oppdrag/{o.pk}/antall/2/')
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn('bærer ikke', res.json()['message'])

    def test_bare_bilen_paa_oppdraget(self):
        o = self._transport()
        annen = _bruker('karmoy12', 'skriv_handling', delt=True)
        Enhet.objects.filter(pk=self.annen_enhet.pk).update(user=annen)
        self.assertEqual(_klient(annen).post(f'/oppdrag/api/oppdrag/{o.pk}/antall/2/').status_code, 403)
        sentral = _klient(_bruker('sentral_a', 'skriv_full'))
        self.assertEqual(sentral.post(f'/oppdrag/api/oppdrag/{o.pk}/antall/2/').status_code, 403,
                         'sentralbordet setter ikke antallet')

    def test_bilens_side_baerer_hvilke_som_har_antall(self):
        res = self.bil.get('/oppdrag/')
        self.assertContains(res, 'OPPDRAG_MED_ANTALL')
        self.assertContains(res, 'Transport')


class SeedMigrasjonTests(TransactionTestCase):
    """`0020` seeder tabellene og oversetter `Enhet.type` (slug) til FK-en.
    Kjøres mot skjemaet slik det var før `0019`, med rader i den gamle
    formen — som en migrasjonsprøve, men på testbasen."""

    def _migrer(self, navn):
        executor = MigrationExecutor(connection)
        executor.migrate([('oppdrag', navn)])
        return executor.loader.project_state([('oppdrag', navn)]).apps

    def test_typen_oversettes_og_listene_seedes(self):
        gamle = self._migrer('0018_trenger_ressurs_siden')
        GammelEnhet = gamle.get_model('oppdrag', 'Enhet')
        GammelEnhet.objects.create(navn='Lag 3', type='lag')
        GammelEnhet.objects.create(navn='Bil 1', type='ambulanse')
        GammelEnhet.objects.create(navn='Rar', type='drone')
        try:
            nye = self._migrer('0021_fjern_enhet_type')
            NyEnhet = nye.get_model('oppdrag', 'Enhet')
            NyProblem = nye.get_model('oppdrag', 'Problemstilling')
            typer = {e.navn: (e.enhetstype.navn if e.enhetstype else None)
                     for e in NyEnhet.objects.select_related('enhetstype')}
            self.assertEqual(typer, {'Lag 3': 'Lag til fots', 'Bil 1': 'Ambulanse', 'Rar': None})
            navn = set(NyProblem.objects.values_list('navn', flat=True))
            self.assertEqual(navn, set(choices.PROBLEMSTILLING))
            transport = NyProblem.objects.get(navn='Transport')
            self.assertEqual((transport.kategori, transport.med_antall), ('begge', True))
            self.assertEqual(NyProblem.objects.get(navn='Udefinert').rekkefolge, 0)
            self.assertEqual(NyProblem.objects.get(navn='Matutlevering').kategori, 'drift')
        finally:
            # Tilbake til toppen, så neste test får skjemaet den venter.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())


class VerdiadminJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (OPPDRAG_SENTRAL_JS, ('_verdirad', 'renderVerdiadmin', '_byggProblemkart', 'flyttVerdi',
                              '_verdiUrl', '_registrerEkstraVerdifaner',
                              '_verdiArg', '_verdiKall')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = (_konst(OPPDRAG_SENTRAL_JS, 'HASTEGRAD_REKKEFOLGE')
                        + _konst(OPPDRAG_SENTRAL_JS, 'VERDIMENGDER')
                        + _konst(OPPDRAG_SENTRAL_JS, 'PROBLEM_KATEGORIER')
                        + build_harness(self.HARNESS))

    def test_problemkartet_speiler_serveren(self):
        ut = run_node(self.harness, """
            const { kart, medAntall } = _byggProblemkart([
              {navn: 'Udefinert', kategori: 'begge', er_aktiv: true, med_antall: false, fast: true},
              {navn: 'Pustevansker', kategori: 'medisinsk', er_aktiv: true, med_antall: false},
              {navn: 'Transport', kategori: 'begge', er_aktiv: true, med_antall: true},
              {navn: 'Utstyr', kategori: 'drift', er_aktiv: true, med_antall: false},
              {navn: 'Borte', kategori: 'drift', er_aktiv: false, med_antall: true}]);
            console.log(JSON.stringify(kart));
            console.log(JSON.stringify(medAntall));
        """)
        kart, med = ut.strip().splitlines()[:2]
        self.assertEqual(json.loads(kart), {
            'Akutt': ['Udefinert', 'Pustevansker', 'Transport'],
            'Haster': ['Udefinert', 'Pustevansker', 'Transport'],
            'Vanlig': ['Udefinert', 'Pustevansker', 'Transport'],
            'Drift': ['Udefinert', 'Transport', 'Utstyr'],
            # Plassering (19. sep. 2026) tilbyr driftens problemstillinger.
            'Plassering': ['Udefinert', 'Transport', 'Utstyr']})
        self.assertEqual(json.loads(med), ['Transport'])

    def test_raden_har_flytt_og_den_faste_har_verken_slett_eller_endring(self):
        ut = run_node(self.harness, """
            globalThis.window = { OPPDRAG_TILGANG: { erAdmin: true } };
            console.log(_verdirad('problemstillinger',
              {id: 1, navn: 'Udefinert', er_aktiv: true, fast: true, kategori: 'begge', med_antall: false, i_bruk: 0}, true, false));
            console.log('---');
            console.log(_verdirad('lokasjoner',
              {id: 7, navn: '<b>Scene</b>', er_aktiv: true, fast: false, i_bruk: 2}, false, true));
        """)
        fast, vanlig = ut.split('---')
        self.assertNotIn('slettVerdi', fast)
        self.assertNotIn('endreVerdinavn', fast)
        self.assertNotIn('settVerdifelt', fast, 'kategori og antall er låst på den faste')
        self.assertIn('· fast', fast)
        self.assertIn('data-arg="lokasjoner:7:opp"', vanlig)
        self.assertIn('data-arg="lokasjoner:7:ned" title="Flytt ned" disabled', vanlig, 'sist: ned er av')
        self.assertIn('&lt;b&gt;Scene&lt;/b&gt;', vanlig)
        self.assertIn('2 i bruk', vanlig)
        self.assertIn('slettVerdi', vanlig)

    def test_enhetstyperaden_har_de_to_flaggene_og_lokasjonsraden_ikke(self):
        """Flaggene bor på typen (16. sep. 2026), og «Valglister» er det ene
        stedet de kan krysses av. Tegnes de ikke, finnes funksjonen ikke for
        den som skal bruke den — uansett hvor riktig serveren svarer."""
        ut = run_node(self.harness, """
            globalThis.window = { OPPDRAG_TILGANG: { erAdmin: true } };
            console.log(_verdirad('enhetstyper',
              {id: 4, navn: 'Spesialressurs', er_aktiv: true, fast: false, i_bruk: 2,
               kan_passiv_vakt: true, kan_avvente: false}, false, false));
            console.log('---');
            console.log(_verdirad('lokasjoner',
              {id: 7, navn: 'Scene', er_aktiv: true, fast: false, i_bruk: 0}, false, false));
        """)
        type_, lokasjon = ut.split('---')
        self.assertIn('data-felt="kan_passiv_vakt"', type_)
        self.assertIn('data-felt="kan_avvente"', type_)
        self.assertIn('<option value="1" selected>Kan gå passiv', type_)
        self.assertIn('<option value="0" selected>Rykker ut', type_,
                      'det avslåtte flagget står avslått, ikke tomt')
        self.assertNotIn('settTypeflagg', lokasjon, 'en lokasjon går ikke passiv vakt')

    def test_hvert_nedtrekk_i_verdiraden_melder_sin_egen_hendelse(self):
        """**Regelen, ikke ett treff.** Første utgave av testen over krevde
        strengen `data-action=… data-hendelse="change"` ett sted i markupen, og
        den sto i begge nedtrekkene — så flagget kunne miste hendelsen sin uten
        at noe ble rødt (funnet ved mutasjonstesting 16. sep. 2026).

        Uten hendelsen fyrer `klikkSkalKjore()` handlingen på *klikket* som
        åpner nedtrekket, med den gamle verdien. Nøyaktig feilen som gjorde
        vaktlistevelgeren «treg» dagen før.
        """
        ut = run_node(self.harness, """
            globalThis.window = { OPPDRAG_TILGANG: { erAdmin: true } };
            console.log(_verdirad('enhetstyper',
              {id: 4, navn: 'Spesialressurs', er_aktiv: true, fast: false, i_bruk: 0,
               kan_passiv_vakt: true, kan_avvente: true}, false, false));
            console.log(_verdirad('problemstillinger',
              {id: 5, navn: 'Transport', er_aktiv: true, fast: false, i_bruk: 0,
               kategori: 'begge', med_antall: true}, false, false));
        """)
        tagger = re.findall(r'<select\b[^>]*>', ut)
        self.assertGreaterEqual(len(tagger), 4, 'to flagg og to problemstillingsfelt')
        for tag in tagger:
            with self.subTest(tag=tag):
                if 'data-action' not in tag:
                    continue
                self.assertIn('data-hendelse="change"', tag)
                self.assertIn('data-felt="', tag,
                              'uten `data-felt` sender delegeringen ett argument, ikke tre')

    def test_typeflagget_sendes_som_boolsk_til_enhetstypen(self):
        """«1» og «0» er nedtrekkets verdier; serveren normaliserer med
        `bool`, og `bool('0')` er True. Oversettelsen må skje her."""
        ut = run_node(self.harness + build_harness(
            ((OPPDRAG_SENTRAL_JS, ('settTypeflagg',)),)), """
            const kall = [];
            globalThis.apiFetch = async (url, valg) => { kall.push([url, JSON.parse(valg.body)]);
              return { ok: true, json: async () => ({ status: 'ok', data: [] }) }; };
            globalThis.lastVerdier = async () => {};
            globalThis.lastEnheter = async () => { kall.push(['enheter', null]); };
            globalThis.document = { getElementById: () => null, querySelectorAll: () => [] };
            await settTypeflagg(4, 'kan_avvente', '1');
            await settTypeflagg(4, 'kan_passiv_vakt', '0');
            console.log(JSON.stringify(kall));
        """)
        kall = json.loads(ut.strip().splitlines()[0])
        self.assertEqual(kall[0], ['/oppdrag/api/enhetstyper/4/', {'kan_avvente': True}])
        self.assertEqual(kall[2], ['/oppdrag/api/enhetstyper/4/', {'kan_passiv_vakt': False}])
        self.assertEqual([k[0] for k in kall].count('enheter'), 2,
                         'tavla grupperer på type og viser passivmerket')

    def test_flytt_sender_hele_lista_med_de_to_byttet(self):
        ut = run_node(self.harness, """
            globalThis.verdier = { lokasjoner: [{id: 1}, {id: 2}, {id: 3}] };
            const kall = [];
            globalThis.apiFetch = async (url, valg) => { kall.push([url, JSON.parse(valg.body)]);
              return { ok: true, json: async () => ({ status: 'ok', data: [] }) }; };
            globalThis.lastVerdier = async () => {};
            globalThis.document = { getElementById: () => null, querySelectorAll: () => [] };
            await flyttVerdi('lokasjoner:3:opp');
            await flyttVerdi('lokasjoner:1:opp');   // først: ingenting sendes
            console.log(JSON.stringify(kall));
        """)
        self.assertEqual(json.loads(ut.strip().splitlines()[0]),
                         [['/oppdrag/api/lokasjoner/rekkefolge/', {'ider': [1, 3, 2]}]])


class AntallJsTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (OPPDRAG_ENHET_JS, ('_antallRad', '_problemMedAntall', '_medAntall', 'settAntall')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_stepperen_viser_en_som_standard_og_sender_tallet(self):
        ut = run_node(self.harness, """
            globalThis.window = { OPPDRAG_MED_ANTALL: ['Transport'] };
            console.log(_antallRad({problemstilling: 'Transport', antall: null}));
            console.log('---');
            console.log(JSON.stringify(_antallRad({problemstilling: 'Pustevansker', antall: null})));
            console.log('---');
            globalThis.mineOppdrag = [{id: 9, status: 'fremme', problemstilling: 'Transport', antall: 2}];
            const kall = [];
            globalThis.apiFetch = async (url) => { kall.push(url); return { ok: true, json: async () => ({ status: 'ok' }) }; };
            globalThis.withSubmitGuard = async (id, fn) => fn();
            globalThis.lastMine = async () => {};
            globalThis.etagMine = null;
            await settAntall('3');
            await settAntall('0');
            console.log(JSON.stringify(kall));
        """)
        med, uten, kall = ut.split('---')
        self.assertIn('antall-tall">1<', med)
        self.assertIn('data-arg="0" disabled', med, 'ned er av på én')
        self.assertIn('data-arg="2"', med)
        self.assertEqual(uten.strip().splitlines()[0], '""')
        self.assertEqual(json.loads(kall.strip().splitlines()[0]), ['/oppdrag/api/oppdrag/9/antall/3/'])
