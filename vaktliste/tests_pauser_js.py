# -*- coding: utf-8 -*-
"""Pausene i nettleseren (23. sep. 2026): linja på ressurskortet, Oversikt,
og regelen i planleggeren. Kjøres i node gjennom de ekte byggerne."""
import json
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import (PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness,
                                    node_available, run_node)

RESSURS = ('mkRessurs', '_pauselinje', '_pauserFor', '_pausetekst', '_pauserPaaUtskrift',
           'ressursErApen', '_radklasse', '_stempelknapper', 'kanStemple', 'iDrift', '_rolleValg',
           'rollerForGruppe', '_fyllValgFor', 'opptattPaaPlassen', '_varighet',
           '_planrad', '_plancellene', '_driftrad', 'kanBemannePlass', '_mittKorpsId',
           '_synligePoster', '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke',
           '_blokklinje', '_tidsblokker', '_blokkerMedDager', '_blokkrader', '_posterFor',
           '_tilstede', '_sumTimer', '_skifttimer', '_tall', '_telling', '_utvalgstekst',
           '_skiftrekkefolge', '_tidsspenn', '_iso16', '_d', '_kl', '_dag', '_sammeDag',
           '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanSetteOppSkift', 'kanLede', 'kanBemanne',
           'kanGiNyttNavn', 'kanRoreRad', '_plassKorps')
OVERSIKT = ('mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utskriftsdager',
            '_ressurserIGruppe', '_grupperMedRessurser', '_vaktspenn')
PLANLEGGER = ('_planleggerPause', '_planleggerLinjeverdi', 'planleggerLesTilbake',
              '_planleggerStandardvindu')

FORSPILL = """
globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];
globalThis.MND = ['jan','feb','mar','apr','mai','jun','jul','aug','sep','okt','nov','des'];
globalThis.utskriftDag = null; globalThis.korpsfilter = null; globalThis.planleggerNesteId = 1;
const L = (d, t, m = 0) => new Date(2026, 9, d, t, m).toISOString();
const R = {id: 1, navn: 'Lag 1', ikon: 'people', gruppe_id: 5, gruppe_navn: 'Lag',
           korps_navn: '', enhet_navn: '', pause_min: 30, pause_etter_min: 240, pause_forskyv: false};
const VP = (id, ressurs_id, fra, til) => ({id, ressurs_id, fra_tid: fra, til_tid: til, ledig: true,
  navn: '', korps_navn: '', rolle: '', kompetanser: [], merknad: ''});
globalThis.aktivListe = {
  vaktliste: {id: 1, vakt_navn: 'Vakta', status_navn: 'Planlegging', i_drift: false,
              pauser_paa_utskrift: true, startet: L(2, 14)},
  ressurser: [R], mannskap: [], roller: [], korps: [], enheter: [],
  grupper: [{id: 5, navn: 'Lag', flere_enheter: true}],
  vaktposter: [VP(1, 1, L(2, 14), L(2, 22)), VP(2, 1, L(3, 14), L(3, 22))],
  pauser: [{id: 7, ressurs_id: 1, fra: L(2, 18), til: L(2, 18, 30), fra_regel: true},
           {id: 8, ressurs_id: 1, fra: L(3, 18), til: L(3, 18, 30), fra_regel: false},
           {id: 9, ressurs_id: 2, fra: L(2, 18), til: L(2, 18, 30), fra_regel: false}],
};
globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_leder' } };
"""


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class PauseneIVaktlistaJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml', 'klokke')),
            (VAKTLISTE_JS, RESSURS + OVERSIKT + PLANLEGGER),
        ))

    def _kjor(self, kode):
        ut = run_node(self.harness, kode, preamble=FORSPILL).splitlines()
        return ut[:-1] if ut and ut[-1] == 'OK' else ut

    def test_pausene_for_dagen_og_bare_ressursens(self):
        ut = self._kjor("""
            console.log(JSON.stringify(_pauserFor(1).map((p) => p.id)));
            console.log(JSON.stringify(_pauserFor(1, [aktivListe.vaktposter[0]]).map((p) => p.id)));
            console.log(JSON.stringify(_pauserFor(1, []).map((p) => p.id)));
            console.log(_pausetekst(aktivListe.pauser[0]));
        """)
        self.assertEqual(ut[:3], ['[7,8]', '[7]', '[]'])
        self.assertRegex(ut[3], r'^\d\d:\d\d–\d\d:\d\d$')

    def test_en_pause_over_skiftbyttet_vises(self):
        ut = self._kjor("""
            aktivListe.pauser = [{id: 1, ressurs_id: 1, fra: L(2, 21, 45), til: L(2, 22, 15)}];
            console.log(_pauserFor(1, [VP(1, 1, L(2, 14), L(2, 22))]).length);
            console.log(_pauserFor(1, [VP(1, 1, L(2, 22), L(3, 6))]).length);
            console.log(_pauserFor(1, [VP(1, 1, L(2, 22, 15), L(3, 6))]).length);
        """)
        self.assertEqual(ut, ['1', '1', '0'])

    def test_lederen_faar_knapper_andre_ser_tekst_og_uten_pauser_ingen_linje(self):
        ut = self._kjor("""
            const kort = () => mkRessurs(R, true, [aktivListe.vaktposter[0]]);
            console.log(/data-action="apnePause"\s+data-id="7"/.test(kort()));
            console.log(kort().includes('apneNyPause'));
            window.MODUL_TILGANG = { vaktliste: 'skriv_full' };
            console.log(kort().includes('apnePause') || kort().includes('apneNyPause'));
            console.log(kort().includes('vl-pauselinje'));
            aktivListe.pauser = [];
            console.log(kort().includes('vl-pauselinje'));
            window.MODUL_TILGANG = { admin: true };
            console.log(kort().includes('apneNyPause'));
        """)
        self.assertEqual(ut, ['true', 'true', 'false', 'true', 'false', 'true'])

    def test_admin_kan_skjule_dem_paa_papiret(self):
        ut = self._kjor("""
            const linje = () => _pauselinje(R, [aktivListe.vaktposter[0]]);
            console.log(linje().includes('vl-skjul-utskrift'));
            aktivListe.vaktliste.pauser_paa_utskrift = false;
            console.log(linje().includes('vl-skjul-utskrift'));
            console.log(mkOversikt().includes('vl-skjul-utskrift'));
            aktivListe.vaktliste.pauser_paa_utskrift = true;
            console.log(mkOversikt().includes('vl-skjul-utskrift'));
            console.log(mkOversikt().includes('pause '));
            aktivListe.pauser = [];
            console.log(_pauselinje(R, [aktivListe.vaktposter[0]]).includes('vl-skjul-utskrift'));
        """)
        self.assertEqual(ut, ['false', 'true', 'true', 'false', 'true', 'true'],
                         'en tom linje skal heller ikke ut på papiret')

    def test_planleggeren_leser_regelen_tilbake_og_sender_minutter(self):
        ut = self._kjor("""
            const [linje] = planleggerLesTilbake();
            console.log(JSON.stringify([linje.pause_min, linje.pause_etter_min, linje.pause_forskyv]));
            console.log(JSON.stringify([_planleggerLinjeverdi('pause_etter_min', '4'),
              _planleggerLinjeverdi('pause_etter_min', '3,5'), _planleggerLinjeverdi('pause_etter_min', ''),
              _planleggerLinjeverdi('pause_etter_min', 'x'), _planleggerLinjeverdi('pause_forskyv', '0'),
              _planleggerLinjeverdi('pause_forskyv', '1'), _planleggerLinjeverdi('gruppe_id', '5'),
              _planleggerLinjeverdi('pause_min', '30')]));
            aktivListe.ressurser = [Object.assign({}, R, {pause_min: null, pause_etter_min: null, pause_forskyv: true})];
            const [tom] = planleggerLesTilbake();
            console.log(JSON.stringify([tom.pause_min, tom.pause_etter_min, tom.pause_forskyv]));
        """)
        self.assertEqual(json.loads(ut[0]), [30, 240, False])
        self.assertEqual(json.loads(ut[1]), [240, 210, '', 'x', False, True, 5, '30'])
        self.assertEqual(json.loads(ut[2]), ['', '', True])

    def test_regelfeltene_viser_timer_og_valget(self):
        ut = self._kjor("""
            const html = _planleggerPause({id: 3, pause_min: 30, pause_etter_min: 270, pause_forskyv: false});
            console.log(html.includes('value="4.5"'));
            console.log(/value="0" selected/.test(html));
            console.log(_planleggerPause({id: 3, pause_min: '', pause_etter_min: '', pause_forskyv: true})
              .includes('value="1" selected'));
            console.log(html.includes('data-felt="pause_etter_min" data-id="3"'));
        """)
        self.assertEqual(ut, ['true', 'true', 'true', 'true'])

    def test_escaping(self):
        ond = '"><img src=x onerror=alert(1)>'
        ut = self._kjor(f"""
            const ond = {json.dumps(ond)};
            aktivListe.pauser = [{{id: ond, ressurs_id: 1, fra: L(2, 18), til: L(2, 18, 30)}}];
            console.log(_pauselinje(Object.assign({{}}, R, {{id: 1}}), null)
              + _planleggerPause({{id: ond, pause_min: ond, pause_etter_min: '', pause_forskyv: true}}));
        """)
        self.assertNotIn('<img', ut[0])
