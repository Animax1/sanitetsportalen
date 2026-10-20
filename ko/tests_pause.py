"""Pause synlig i ressursoversikten, tildelingen og hendelsene (20. okt. 2026).

André: «Når et lag eller bil settes på pause, er det ønskelig at det vises at den/de er på
pause på ressursoversikt, og ved oppdragstildeling/hendelser.» Pausen står på tavla
(`ko.tavle.paa_pause`) og følger med logg-pollen (`pauser`).
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.test import Client, SimpleTestCase, override_settings
from django.utils import timezone

from ko import tavle
from ko.models import Tavleplassering
from patients.js_test_utils import KO_JS, PORTAL_UTILS_JS, build_harness, run_node

from .tests_hendelseslogg import _bruker, _gi
from .tests_tavle import _Grunnlag


class PaaPauseTests(_Grunnlag):
    """Tjenestelaget: hvem står i Pause-raden nå."""

    def test_lag_og_bil_i_pause(self):
        self._plasser(self.lag1, pause=True)
        self._plasser(self.bil, pause=True)
        rader = {p['ressurs_id']: p for p in tavle.paa_pause(self.vakt)}
        self.assertEqual(set(rader), {self.lag1.pk, self.bil.pk})
        self.assertIsNone(rader[self.lag1.pk]['enhet_id'], 'et lag har ingen enhet')
        self.assertEqual(rader[self.bil.pk]['enhet_id'], self.enhet.pk, 'bilen finnes på enheten')
        self.assertEqual(rader[self.lag1.pk]['navn'], 'Lag 1')

    def test_paa_et_sted_er_ikke_pause(self):
        self._plasser(self.lag1, self.park)
        self.assertEqual(tavle.paa_pause(self.vakt), [])

    def test_flyttet_videre_er_pausen_over(self):
        self._plasser(self.lag1, pause=True)
        self._plasser(self.lag1, self.park)
        self.assertEqual(tavle.paa_pause(self.vakt), [])

    def test_tatt_av_tavla_er_pausen_over(self):
        self._plasser(self.lag1, pause=True)
        tavle.avslutt(self.vakt, self.lag1, bruker=self.operator)
        self.assertEqual(tavle.paa_pause(self.vakt), [])

    def test_planlagt_slutt_folger_med(self):
        p = self._plasser(self.lag1, pause=True)
        slutt = timezone.now() + timedelta(minutes=20)
        Tavleplassering.objects.filter(pk=p.pk).update(planlagt_til=slutt)
        self.assertEqual(tavle.paa_pause(self.vakt)[0]['planlagt_til'], slutt.isoformat())

    def test_en_annen_vakts_pause_teller_ikke(self):
        from core.models import Vakt
        annen = Vakt.objects.create(navn='i fjor', year=2025, startet=timezone.now())
        Tavleplassering.objects.create(vakt=annen, ressurs=self.lag2, ressurs_navn='Lag 2',
                                       pause=True, fra=timezone.now())
        self.assertEqual(tavle.paa_pause(self.vakt), [])


@override_settings(SECURE_SSL_REDIRECT=False, RATELIMIT_ENABLE=False)
class PausenILoggpollenTests(_Grunnlag):
    """Logg-pollen bærer pausene, med hver kildes gate: et lag er vaktlistas, en bil oppdragets."""

    def setUp(self):
        super().setUp()
        self._plasser(self.lag1, pause=True)
        self._plasser(self.bil, pause=True)

    def _pauser(self, **moduler):
        self._nr = getattr(self, '_nr', 0) + 1
        b = _bruker(f'p{self._nr}')
        _gi(b, 'ko', 'les')
        for modul, nivaa in moduler.items():
            _gi(b, modul, nivaa)
        c = Client()
        c.force_login(b)
        return {p['ressurs_id'] for p in c.get('/ko/api/logg/').json()['pauser']}

    def test_begge_kilder_gir_begge(self):
        self.assertEqual(self._pauser(vaktliste='les', oppdrag='les'), {self.lag1.pk, self.bil.pk})

    def test_bare_vaktlista_gir_lagene(self):
        self.assertEqual(self._pauser(vaktliste='les'), {self.lag1.pk})

    def test_bare_oppdrag_gir_bilene(self):
        self.assertEqual(self._pauser(oppdrag='les'), {self.bil.pk})

    def test_ko_alene_gir_ingenting(self):
        self.assertEqual(self._pauser(), set())

    def test_pause_naa_fra_en_plan_vises(self):
        """Den ekte veien inn: «Pause nå» på en planlagt pause plasserer laget i Pause-raden."""
        naa = timezone.now()
        plan = tavle.planlegg_pause(self.vakt, self.lag2, fra=naa + timedelta(minutes=5),
                                    til=naa + timedelta(minutes=30), bruker=self.operator, naa=naa)
        tavle.start_pause(plan, bruker=self.operator, naa=naa + timedelta(minutes=5))
        self.assertIn(self.lag2.pk, self._pauser(vaktliste='les'))


class PausemerketJsTests(SimpleTestCase):
    """Reglene i ko.js: hvem som er på pause, teksten, og at lagkortet viser det."""

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'fmtMin')),
            (KO_JS, ('koPauseFor', 'koPauseTekst', 'koPauseMerke', 'koRessursPauseHtml',
                     'enhetPauseMerke', 'enhetPauseTekst', 'lagPauseTekst', 'koTaImotPauser',
                     'koKlokke', 'koSiden', 'koRessurskort', 'koRessursMannskap',
                     'koRessursBesetningHtml', 'koRessursOpptattHtml', 'koLagPaa',
                     'koLagVelgerHtml', 'koLagKandidater')),
        ))

    def _kjor(self, kode, pauser):
        forspill = (
            f'globalThis.koPauser = {json.dumps(pauser)};\n'
            "globalThis.koPauserJson = JSON.stringify(globalThis.koPauser);\n"
            'globalThis.koHendelser = new Map();\n'
            'globalThis.koApenRessurs = null;\n'
        )
        return run_node(self.harness, forspill + kode).splitlines()[0]

    LAG = {'ressurs_id': 7, 'enhet_id': None, 'navn': 'Lag 7', 'fra': '2026-10-20T12:00:00Z',
           'planlagt_til': None}
    BIL = {'ressurs_id': 9, 'enhet_id': 3, 'navn': 'Amb 3', 'fra': '2026-10-20T12:00:00Z',
           'planlagt_til': '2026-10-20T12:30:00Z'}

    def test_lag_paa_ressurs_bil_paa_enhet(self):
        ut = self._kjor("console.log(JSON.stringify([koPauseFor(7, null)?.navn, koPauseFor(null, 3)?.navn,"
                        " koPauseFor(null, 7), koPauseFor(3, null), koPauseFor(null, null)]));",
                        [self.LAG, self.BIL])
        self.assertEqual(json.loads(ut), ['Lag 7', 'Amb 3', None, None, None])

    def test_teksten_og_over_tida(self):
        naa = "Date.parse('2026-10-20T12:12:00Z')"
        sent = "Date.parse('2026-10-20T12:45:00Z')"
        ut = self._kjor(f"console.log(JSON.stringify([koPauseTekst(koPauser[1], {naa}),"
                        f" koPauseTekst(koPauser[1], {sent}), koPauseMerke(koPauser[1], {sent})]));",
                        [self.LAG, self.BIL])
        foer, etter, merke = json.loads(ut)
        self.assertIn('12 min', foer)
        self.assertIn('→', foer)
        self.assertNotIn('over tida', foer)
        self.assertIn('over tida', etter)
        self.assertIn('ko-pause-over', merke)

    def test_lagkortet_viser_pausen_gjennom_den_ekte_byggeren(self):
        kort = "{id: 7, navn: 'Lag 7', antall: 0, tilstede: 0, gruppe_ikon: 'people'}"
        med = self._kjor(f'console.log(koRessurskort({kort}));', [self.LAG])
        uten = self._kjor(f'console.log(koRessurskort({kort}));', [])
        self.assertIn('ko-pause-merke', med)
        self.assertIn('Pause', med)
        self.assertNotIn('ko-pause-merke', uten)

    def test_teksten_til_nedtrekkene(self):
        ut = self._kjor("console.log(JSON.stringify([enhetPauseTekst(3), enhetPauseTekst(4),"
                        " lagPauseTekst(7), lagPauseTekst(8)]));", [self.LAG, self.BIL])
        self.assertEqual(json.loads(ut), [' · pause', '', ' · pause', ''])

    def test_lagvelgeren_i_hendelsen(self):
        ut = self._kjor("globalThis.koRessurser = [{id: 7, navn: 'Lag 7'}, {id: 8, navn: 'Lag 8'}];\n"
                        "console.log(koLagVelgerHtml({lag: []}));", [self.LAG])
        self.assertIn('>Lag 7 · pause<', ut)
        self.assertIn('>Lag 8<', ut)

    def test_ny_liste_tegner_paa_nytt_lik_liste_gjor_ikke(self):
        kode = ("let tegnet = 0, enheter = 0;\n"
                "globalThis.koTegnRessurser = () => { tegnet++; };\n"
                "globalThis.renderEnheter = () => { enheter++; };\n"
                f"koTaImotPauser([]); koTaImotPauser({json.dumps([self.LAG])});"
                f" koTaImotPauser({json.dumps([self.LAG])});\n"
                "console.log(JSON.stringify([tegnet, enheter, koPauser.length]));")
        self.assertEqual(json.loads(self._kjor(kode, [])), [1, 1, 1])


class LoggpollenTarImotPauseneTests(SimpleTestCase):
    """Kallstedet: `koHentLogg()` gir pausene videre. Testene over kaller `koTaImotPauser`
    direkte, og da kunne pollen sluttet å kalle den uten at noe ble rødt (`CLAUDE.md`)."""

    def test_pollen_setter_pausene(self):
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koHentLogg', 'koTaImotPauser', 'koPauseFor')),
        ))
        kode = """
            globalThis.koLinjer = new Map(); globalThis.koSisteId = 0;
            globalThis.koPauser = []; globalThis.koPauserJson = '[]';
            globalThis.koTegnLogg = () => {}; globalThis.koTaImotDelte = () => {};
            globalThis.koTaImotHendelser = () => {}; globalThis.koTegnRessurser = () => {};
            globalThis.document = { getElementById: () => null };
            globalThis.apiFetch = async () => ({ json: async () => ({ data: [], pauser: [
              { ressurs_id: 7, enhet_id: null, navn: 'Lag 7', fra: '2026-10-20T12:00:00Z', planlagt_til: null }] }) });
            await koHentLogg();
            console.log(JSON.stringify(koPauseFor(7, null)?.navn ?? null));
        """
        self.assertEqual(json.loads(run_node(harness, kode).splitlines()[0]), 'Lag 7')


class PausenIOppdragsfileneTests(SimpleTestCase):
    """Bilkortet og «Nytt oppdrag» er oppdragsmodulens, og kaller KO gjennom en `typeof`-vakt:
    i `/ko/` viser de pausen, i `/oppdrag/` er funksjonen borte og ingenting endres."""

    def test_bilkortet(self):
        from oppdrag.tests_xss import EnhetskortetTests
        t = EnhetskortetTests()
        t.setUp()
        enhet = {'id': 3, 'navn': 'Amb 3', 'status': 'ledig', 'status_navn': 'Ledig', 'pa_vakt': True}
        med = run_node(t.harness, t.STUBB + f"""
            globalThis.enhetPauseMerke = (id) => id === 3 ? '<span class="ko-pause-merke">Pause</span>' : '';
            globalThis.enheter = [{json.dumps(enhet)}];
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => el }};
            renderEnheter();
            console.log(el.innerHTML);
        """)
        self.assertIn('ko-pause-merke', med)
        uten = t._kort(enhet)
        self.assertNotIn('ko-pause-merke', uten, 'uten KO (i /oppdrag/) står ingenting')

    def test_nytt_oppdrag(self):
        from oppdrag.tests_velg import _harness
        h = _harness('mkEnhetsvalg', '_grupperEnheter', '_typeRekkefolge')
        enheter = ("globalThis.enheter = ["
                   "{id: 1, navn: 'Amb 1', type: 1, pa_vakt: true, status: 'ledig', status_navn: 'Ledig'},"
                   "{id: 2, navn: 'Amb 2', type: 1, pa_vakt: true, status: 'ledig', status_navn: 'Ledig'}];")
        med = run_node(h, enheter + "globalThis.enhetPauseTekst = (id) => id === 1 ? ' · pause' : '';"
                       " console.log(mkEnhetsvalg());")
        rad1, rad2 = med.split('</label>')[:2]
        self.assertIn('er-pause', rad1)
        self.assertNotIn('er-ledig', rad1, 'en ledig på pause er ikke grønn')
        self.assertIn('Ledig · pause', rad1)
        self.assertIn('er-ledig', rad2)
        uten = run_node(h, enheter + ' console.log(mkEnhetsvalg());')
        self.assertNotIn('pause', uten)


class BilenKanFaaPauseTests(_Grunnlag):
    """André: «vi får ikke sett ambulansene, vi må kunne gi dem pause og» (20. okt. 2026)."""

    def test_bilen_planlegges_og_startes_i_pause(self):
        naa = timezone.now()
        plan = tavle.planlegg_pause(self.vakt, self.bil, fra=naa + timedelta(minutes=5),
                                    til=naa + timedelta(minutes=35), bruker=self.operator, naa=naa)
        tavle.start_pause(plan, bruker=self.operator, naa=naa + timedelta(minutes=5))
        (p,) = tavle.paa_pause(self.vakt)
        self.assertEqual((p['ressurs_id'], p['enhet_id']), (self.bil.pk, self.enhet.pk))

    def test_ukoblet_bil_paa_vakt_meldes(self):
        from oppdrag.models import Enhet
        Enhet.objects.create(navn='Ambulanse 9', pa_vakt=True)
        Enhet.objects.create(navn='Ambulanse 8', pa_vakt=False)
        Enhet.objects.create(navn='Ambulanse 7', pa_vakt=True, er_aktiv=False)
        self.assertEqual(tavle.ukoblede_enheter(), ['Ambulanse 9'],
                         'koblet (HGSD 56), av vakt og pensjonert meldes ikke')

    def test_tavla_bærer_lista_bare_med_oppdragstilgang(self):
        from oppdrag.models import Enhet
        Enhet.objects.create(navn='Ambulanse 9', pa_vakt=True)
        self.assertEqual(tavle.tavle_data(self.vakt)['ukoblede_enheter'], ['Ambulanse 9'])
        self.assertEqual(tavle.tavle_data(self.vakt, med_biler=False)['ukoblede_enheter'], [])


class UkobledeJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koTavleUkobledeHtml',)),
        ))

    def test_navnene_og_veien_til_koblingen(self):
        ut = run_node(self.harness, "console.log(JSON.stringify([koTavleUkobledeHtml(['Amb <9>']),"
                                    " koTavleUkobledeHtml([]), koTavleUkobledeHtml(undefined)]));")
        med, tom, mangler = json.loads(ut.splitlines()[0])
        self.assertIn('Amb &lt;9&gt;', med)
        self.assertIn('Koble til delt konto', med)
        self.assertEqual((tom, mangler), ('', ''))
