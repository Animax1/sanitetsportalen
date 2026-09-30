"""«Del ut» i nettleseren (pulje 4, 30. sep. 2026).

Kortet, vinduet og planleggerens sluttsteg kjøres i node med den ekte markupen.
Serverdelen står i `tests_del_ut.py`.
"""
from __future__ import annotations

import json

from django.test import SimpleTestCase

from patients.js_test_utils import (
    PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness, node_available, run_node)

from .tests_xss import MND_OG_DAGER

KORPS = [{'id': 1, 'navn': 'Haugesund', 'kortnavn': 'HGSD'},
         {'id': 2, 'navn': 'Karmøy', 'kortnavn': ''}]


def _plass(id_, ressurs=1, **felt):
    vp = {'id': id_, 'ressurs_id': ressurs, 'ledig': True, 'mannskap_id': None,
          'navn': '', 'korps_id': None, 'korps_kort': '', 'korps_navn': '',
          'alle_korps': False, 'plass_korps_id': None, 'reservert_korps_id': None,
          'rolle': '', 'probono': False,
          'fra_tid': '2026-10-03T13:00:00Z', 'til_tid': '2026-10-04T01:00:00Z'}
    vp.update(felt)
    return vp


def _liste(poster, ressurs_korps=None):
    return {
        'vaktliste': {'id': 7, 'vakt_navn': 'Vakten', 'status_navn': 'Planlegging',
                      'i_drift': False, 'startet': '2026-10-03T13:00:00Z',
                      'planlagt_slutt': '2026-10-05T01:00:00Z'},
        'grupper': [{'id': 1, 'navn': 'Ambulanse', 'ikon': 'truck'}],
        'ressurser': [{'id': 1, 'navn': 'Karmøy 51', 'gruppe_id': 1,
                       'korps_id': ressurs_korps,
                       'korps_navn': 'Karmøy' if ressurs_korps else ''},
                      {'id': 2, 'navn': 'Sola 56', 'gruppe_id': 1, 'korps_id': None,
                       'korps_navn': ''}],
        'vaktposter': poster, 'alle_vaktposter': poster,
        'korps': KORPS, 'mannskap': [], 'roller': [], 'enheter': [],
    }


def _vindu(nivaa):
    return (f"globalThis.window = {{ MODUL_TILGANG: {{ vaktliste: '{nivaa}', "
            "admin: false } };\nglobalThis.window.MITT_KORPS_ID = 1;\n")


class KortetTests(SimpleTestCase):
    """Merket og knappen på enhetskortet, gjennom den ekte `mkRessurs()`."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        from .tests_xss import VaktlisteEscapingOppforselTests
        self.harness = MND_OG_DAGER + build_harness(VaktlisteEscapingOppforselTests.HARNESS)

    def _tegn(self, nivaa, poster, ressurs_korps=None):
        return run_node(self.harness, _vindu(nivaa) + (
            "globalThis.ressursApen = new Map();\n"
            "globalThis.utskriftDag = null; globalThis.korpsfilter = null;\n"
            f"globalThis.aktivListe = {json.dumps(_liste(poster, ressurs_korps))};\n"
            "console.log(mkRessurs(aktivListe.ressurser[0]));\n"))

    def test_kladden_telles_paa_kortet(self):
        ut = self._tegn('skriv_full', [_plass(1), _plass(2), _plass(3, ressurs=2)])
        self.assertIn('2 plasser ikke delt ut', ut)
        self.assertNotIn('Ureservert', ut)

    def test_det_som_er_delt_ut_telles_ikke(self):
        ut = self._tegn('skriv_full', [
            _plass(1), _plass(2, alle_korps=True),
            _plass(3, plass_korps_id=1, reservert_korps_id=1),
            _plass(4, ledig=False, mannskap_id=5, navn='Kari')])
        self.assertIn('1 plass ikke delt ut', ut)

    def test_del_ut_er_hovedknappen_mens_noe_ligger_igjen(self):
        ut = self._tegn('skriv_full', [_plass(1)])
        self.assertIn('data-action="apneDelUt"', ut)
        self.assertIn('btn-outline-primary', ut, '«Nytt skift» viker')

    def test_uten_kladd_ingen_knapp(self):
        ut = self._tegn('skriv_full', [_plass(1, alle_korps=True)])
        self.assertNotIn('apneDelUt', ut)
        self.assertIn('Åpen for alle', ut)

    def test_korpsforeren_faar_ingen_knapp(self):
        """Hun får aldri kladden fra serveren; knappen skal heller ikke stå der
        om den likevel kom — `kanSetteOppSkift()` er porten."""
        ut = self._tegn('skriv_handling', [_plass(1)])
        self.assertNotIn('apneDelUt', ut)

    def test_delt_ut_til_ett_korps_navngis(self):
        ut = self._tegn('skriv_full', [_plass(1, plass_korps_id=1, reservert_korps_id=1)])
        self.assertIn('HGSD', ut)

    def test_delt_ut_til_flere(self):
        ut = self._tegn('skriv_full', [
            _plass(1, plass_korps_id=1, reservert_korps_id=1),
            _plass(2, plass_korps_id=2, reservert_korps_id=2),
            _plass(3, alle_korps=True)])
        self.assertIn('Delt ut til 2 korps og alle', ut)

    def test_enhetens_eget_korps_vinner(self):
        ut = self._tegn('skriv_full', [_plass(1, reservert_korps_id=2)], ressurs_korps=2)
        self.assertIn('vl-korps', ut)
        self.assertNotIn('apneDelUt', ut)

    def test_korpsvelgeren_skjuler_ikke_kladden(self):
        """Kladden har ikke noe korps, og korpsvelgeren filtrerer `vaktposter`.
        Leste kortet den lista, forsvant tellingen når et korps var valgt."""
        liste = _liste([_plass(1)])
        liste['vaktposter'] = []
        ut = run_node(self.harness, _vindu('skriv_full') + (
            "globalThis.ressursApen = new Map();\n"
            "globalThis.utskriftDag = null; globalThis.korpsfilter = 1;\n"
            f"globalThis.aktivListe = {json.dumps(liste)};\n"
            "console.log(mkRessurs(aktivListe.ressurser[0]));\n"))
        self.assertIn('1 plass ikke delt ut', ut)


class VinduetTests(SimpleTestCase):
    """«Del ut»-vinduet sender det som ble valgt, til riktig adresse."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('apneDelUt', 'lagreDelUt', 'mkDelUtValg', '_delUtRad',
                        '_sendDelUt', 'ikkeDeltUt', '_allePoster', '_sumTimer',
                        '_skifttimer', '_tall', '_d')),
    )

    STUBB = """
        const el = {};
        const hent = (id) => (el[id] = el[id] || { dataset: {}, textContent: '',
                                                     innerHTML: '' });
        globalThis.valgt = null;
        globalThis.document = {
          getElementById: hent,
          querySelector: () => (valgt === null ? null : { value: valgt }),
        };
        globalThis.withSubmitGuard = async (id, fn) => fn();
        globalThis.sendt = [];
        globalThis.apiFetch = async (url, opts) => {
          sendt.push({ url, kropp: JSON.parse(opts.body) });
          return { ok: true, json: async () => ({ status: 'ok' }) };
        };
        globalThis._skjulFeil = () => {};
        globalThis._visFeil = (id, m) => { globalThis.feil = m; };
        globalThis._apneModal = () => {};
        globalThis._lukkModal = () => {};
        globalThis.lastListe = async () => {};
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, kode, poster=None):
        liste = _liste(poster if poster is not None else [_plass(1), _plass(2)])
        return run_node(self.harness, self.STUBB
                        + f"globalThis.aktivListe = {json.dumps(liste)};\n" + kode)

    def test_vinduet_sier_hvor_mye_som_ligger_igjen(self):
        ut = self._kjor("""
            apneDelUt(1);
            console.log(el['del-ut-tekst'].textContent);
            console.log(el['del-ut-knapp'].textContent);
            console.log(el['del-ut-tittel'].textContent);
        """)
        self.assertIn('2 plasser ligger på bordet ditt (24 t)', ut)
        self.assertIn('Del ut 2 plasser', ut)
        self.assertIn('Del ut Karmøy 51', ut)

    def test_et_korps_sendes_som_korps_id(self):
        ut = self._kjor("""
            apneDelUt(1); valgt = '2';
            await lagreDelUt();
            console.log(JSON.stringify(sendt));
        """)
        sendt = json.loads(ut.splitlines()[0])
        self.assertEqual(sendt, [{'url': '/vaktliste/api/vaktlister/7/del-ut/',
                                  'kropp': {'fordeling': [{'ressurs_id': 1, 'korps_id': 2}]}}])

    def test_alle_sendes_som_alle(self):
        ut = self._kjor("""
            apneDelUt(1); valgt = 'alle';
            await lagreDelUt();
            console.log(JSON.stringify(sendt[0].kropp));
        """)
        self.assertEqual(json.loads(ut.splitlines()[0]),
                         {'fordeling': [{'ressurs_id': 1, 'alle': True}]})

    def test_uten_valg_sendes_ingenting(self):
        ut = self._kjor("""
            apneDelUt(1);
            await lagreDelUt();
            console.log(sendt.length, feil);
        """)
        self.assertIn('0 Velg hvem som skal få plassene.', ut)

    def test_valgene_escapes(self):
        ut = run_node(self.harness, "console.log(mkDelUtValg("
                      "[{id: 1, navn: '<b>x</b>'}], null));")
        self.assertNotIn('<b>x</b>', ut)
        self.assertIn('Åpen for alle korps', ut)


class SluttstegetTests(SimpleTestCase):
    """Planleggerens tabell «Del ut»: én rad per enhet med kladd."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'hendelseArgumenter',
                           '_handlerArgument')),
        (VAKTLISTE_JS, ('mkDelUtTabell', 'planleggerDelUt', '_delUtRad',
                        '_delUtKnappTekst', 'velgDelUt', 'lagreDelUtAlle',
                        '_sendDelUt', 'planleggerTegnDelUt', 'ikkeDeltUt',
                        '_allePoster', 'kanSetteOppSkift', 'kanSkriveAlt',
                        '_nivaa', '_erAdmin')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, kode, nivaa='skriv_full'):
        poster = [_plass(1), _plass(2), _plass(3, ressurs=2),
                  _plass(4, ressurs=2, alle_korps=True)]
        return run_node(self.harness, _vindu(nivaa) + VinduetTests.STUBB
                        + "globalThis.delUtValg = {};\n"
                        + f"globalThis.aktivListe = {json.dumps(_liste(poster))};\n" + kode)

    def test_en_rad_per_enhet_med_kladd(self):
        ut = self._kjor("console.log(mkDelUtTabell());")
        self.assertIn('Karmøy 51', ut)
        self.assertIn('Sola 56', ut)
        self.assertIn('3 plasser ligger', ut)
        self.assertIn('— bestem senere —', ut)
        self.assertIn('disabled', ut, 'ingenting valgt, ingenting å sende')

    def test_ingen_kladd_ingen_tabell(self):
        ut = run_node(self.harness, _vindu('skriv_full') + (
            "globalThis.delUtValg = {};\n"
            f"globalThis.aktivListe = {json.dumps(_liste([_plass(1, alle_korps=True)]))};\n"
            "console.log(JSON.stringify(mkDelUtTabell()));"))
        self.assertIn('""', ut)

    def test_valget_gaar_gjennom_den_ekte_delegeringen(self):
        """`data-felt` må stå på nedtrekket, ellers får handleren bare id-en
        (CLAUDE.md i rota, «delegeringen sender (id, felt, verdi)»)."""
        ut = self._kjor("""
            const nedtrekk = { dataset: { id: '2', felt: 'hvem' }, value: 'alle' };
            velgDelUt(...hendelseArgumenter(nedtrekk));
            console.log(JSON.stringify(delUtValg));
            console.log(JSON.stringify(planleggerDelUt()));
        """)
        linjer = ut.splitlines()
        self.assertEqual(json.loads(linjer[0]), {'2': 'alle'})
        self.assertEqual(json.loads(linjer[1]),
                         {'fordeling': [{'ressurs_id': 2, 'alle': True}], 'plasser': 1})

    def test_markupen_baerer_det_delegeringen_trenger(self):
        ut = self._kjor("console.log(mkDelUtTabell());")
        self.assertIn('data-action="velgDelUt"', ut)
        self.assertIn('data-hendelse="change"', ut)
        self.assertIn('data-felt="hvem"', ut)

    def test_bestem_senere_tar_raden_ut(self):
        ut = self._kjor("""
            velgDelUt(1, 'hvem', '1');
            velgDelUt(1, 'hvem', '');
            console.log(JSON.stringify(planleggerDelUt()));
        """)
        self.assertEqual(json.loads(ut.splitlines()[0]), {'fordeling': [], 'plasser': 0})

    def test_alt_valgt_sendes_i_ett_kall_og_valgene_nullstilles(self):
        ut = self._kjor("""
            velgDelUt(1, 'hvem', '2');
            velgDelUt(2, 'hvem', 'alle');
            console.log(el['del-ut-alle-knapp'].innerHTML);
            await lagreDelUtAlle();
            console.log(JSON.stringify(sendt));
            console.log(JSON.stringify(delUtValg));
        """)
        linjer = ut.splitlines()
        self.assertIn('Del ut 3 plasser', linjer[0])
        self.assertEqual(json.loads(linjer[1]), [{
            'url': '/vaktliste/api/vaktlister/7/del-ut/',
            'kropp': {'fordeling': [{'ressurs_id': 1, 'korps_id': 2},
                                    {'ressurs_id': 2, 'alle': True}]}}])
        self.assertEqual(linjer[2], '{}')

    def test_et_valg_paa_en_enhet_uten_kladd_sendes_ikke(self):
        """Delt ut i en annen fane i mellomtiden: valget skal ikke gå med."""
        ut = self._kjor("""
            velgDelUt(1, 'hvem', '2');
            aktivListe.alle_vaktposter = aktivListe.alle_vaktposter.filter((vp) => vp.ressurs_id !== 1);
            console.log(JSON.stringify(planleggerDelUt()));
        """)
        self.assertEqual(json.loads(ut.splitlines()[0]), {'fordeling': [], 'plasser': 0})

    def test_korpsforeren_faar_ingen_tabell(self):
        ut = self._kjor("console.log(JSON.stringify(mkDelUtTabell()));", nivaa='skriv_handling')
        self.assertIn('""', ut)


class VaktkortetTests(SimpleTestCase):
    """Vakten øverst i planleggeren: lengden, og grensene som tekst."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkVaktramme', '_dag', '_kl', '_d', '_tall')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = MND_OG_DAGER + build_harness(self.HARNESS)

    def _tegn(self, vaktliste, grenser=None):
        return run_node(self.harness, (
            f"globalThis.aktivListe = {{ vaktliste: {json.dumps(vaktliste)} }};\n"
            f"globalThis.belastning = {json.dumps({'grenser': grenser} if grenser else None)};\n"
            "console.log(mkVaktramme());"))

    def test_spennet_og_knappen(self):
        ut = self._tegn({'startet': '2026-10-03T13:00:00Z',
                         'planlagt_slutt': '2026-10-05T01:00:00Z'})
        self.assertIn('lør 3. okt', ut)
        self.assertIn('data-action="apneVaktlengde"', ut)

    def test_uten_slutt_sier_det_fra(self):
        ut = self._tegn({'startet': '2026-10-03T13:00:00Z', 'planlagt_slutt': None})
        self.assertIn('ingen sluttid satt', ut)

    def test_grensene_nevnes_men_endres_ikke_her(self):
        ut = self._tegn({'startet': '2026-10-03T13:00:00Z', 'planlagt_slutt': None},
                        grenser={'maks_skift_timer': 12, 'min_hvile_timer': 8})
        self.assertIn('Grensene gjelder alle vaktlister', ut)
        self.assertIn('12 t skift', ut)
        self.assertNotIn('apneGrenser', ut)


class KallstedeneTests(SimpleTestCase):
    """**Muter kallstedet, ikke bare funksjonen** (CLAUDE.md, mutasjonstesting).
    Testene over kaller byggerne selv; disse går gjennom de ekte inngangene."""

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')

    def test_planleggeren_tegner_vakten_og_sluttsteget(self):
        from .tests_xss import PlanleggerfanenTests
        harness = MND_OG_DAGER + build_harness(PlanleggerfanenTests.HARNESS)
        liste = _liste([_plass(1)])
        liste['grupper'][0]['flere_enheter'] = True
        ut = run_node(harness, _vindu('skriv_leder') + (
            "globalThis.delUtValg = {};\nglobalThis.belastning = null;\n"
            "globalThis.planleggerNesteId = 1;\nglobalThis.planleggerlinjer = [];\n"
            f"globalThis.aktivListe = {json.dumps(liste)};\n"
            "console.log(mkPlanlegger());"))
        self.assertIn('data-action="apneVaktlengde"', ut)
        self.assertIn('data-action="lagreDelUtAlle"', ut)

    def test_rediger_enhet_aapner_reservasjonen_for_skriv_full(self):
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
            (VAKTLISTE_JS, ('apneRessurs', '_laasRessursoppsett', '_laasFelter',
                            '_settValg', 'kanLede', 'kanSetteOppSkift', 'kanSkriveAlt',
                            '_nivaa', '_erAdmin')),
        ))
        stubb = """
            const el = {};
            globalThis.document = { getElementById: (id) => (el[id] = el[id] || {
              dataset: {}, value: '', innerHTML: '', textContent: '', disabled: false,
              classList: { toggle: () => {} } }) };
            globalThis._skjulFeil = () => {};
            globalThis._posterFor = () => [];
            globalThis.bootstrap = { Modal: { getOrCreateInstance: () => ({ show() {} }) } };
        """
        for nivaa, korps_laast, type_laast in (('skriv_full', False, True),
                                               ('skriv_handling', True, True),
                                               ('skriv_leder', False, False)):
            with self.subTest(nivaa=nivaa):
                ut = run_node(harness, _vindu(nivaa) + stubb + (
                    f"globalThis.aktivListe = {json.dumps(_liste([]))};\n"
                    "apneRessurs(1);\n"
                    "console.log(JSON.stringify([el['ressurs-korps'].disabled,"
                    " el['ressurs-gruppe'].disabled]));"))
                self.assertEqual(json.loads(ut.splitlines()[0]), [korps_laast, type_laast])
