"""`static/js/park-lag.js`, kjørt i node.

Reglene som avgjør noe på siden lagene bruker: hvilket token som gjelder,
hvilket lag som huskes, hvilket sted som forhåndsvelges og hva linja under
sier, hva som tømmes etter en registrering, hva målingen sender, og hvor lenge
«Angre» står. Markupen bygges med `textContent`, så det finnes ingen escaping å
prøve — `test_ingen_markup_i_mal_strenger` holder det slik.
"""
from __future__ import annotations

import json
import re
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import JS_DIR, build_harness, node_available, read_js, run_node

PARK_JS = JS_DIR / 'park-lag.js'
OPPSETT_JS = JS_DIR / 'park-oppsett.js'

HARNESS = ((PARK_JS, ('parkLesToken', 'parkVelgLag', 'parkVelgSted', 'parkKildeTekst',
                      'parkKlokke', 'parkKanRegistrere', 'parkNesteSkjema', 'parkKropp',
                      'parkAngreSekunder', 'parkAktiveAngre', 'parkKvitteringstekst')),)

STEDER = [{'id': 1, 'navn': 'Parkscene'}, {'id': 2, 'navn': 'Club'}]


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class ParkReglerTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _j(self, uttrykk):
        return json.loads(run_node(self.harness, f'console.log(JSON.stringify({uttrykk}));')
                          .splitlines()[0])

    def test_fragmentet_vinner_over_det_lagrede(self):
        self.assertEqual(self._j("parkLesToken('#ny', 'gammel')"), 'ny')
        self.assertEqual(self._j("parkLesToken('', 'gammel')"), 'gammel')
        self.assertEqual(self._j("parkLesToken('#', null)"), '')

    def test_laget_huskes_paa_navn(self):
        lag = json.dumps([{'id': 7, 'navn': 'Sandnes 2.1'}, {'id': 8, 'navn': 'Sandnes 2.2'}])
        self.assertEqual(self._j(f"parkVelgLag({lag}, 'Sandnes 2.2')"), 8)
        self.assertIsNone(self._j(f"parkVelgLag({lag}, 'Borte')"))
        self.assertIsNone(self._j(f"parkVelgLag({lag}, null)"))

    def test_serverens_forhaandsvalg_vinner_over_telefonens_minne(self):
        s = json.dumps(STEDER)
        v = self._j(f"parkVelgSted({{sted: 1, kilde: 'ko', tid: 'x'}}, 'Club', {s})")
        self.assertEqual((v['id'], v['kilde']), (1, 'ko'))

    def test_telefonens_minne_bare_naar_serveren_ikke_har_noe(self):
        s = json.dumps(STEDER)
        v = self._j(f"parkVelgSted({{sted: null, kilde: 'ingen'}}, 'Club', {s})")
        self.assertEqual((v['id'], v['kilde']), (2, 'telefon'))
        v = self._j(f"parkVelgSted(null, 'Club', {s})")
        self.assertEqual((v['id'], v['kilde']), (2, 'telefon'), 'uten svar fra serveren også')

    def test_et_sted_som_ikke_er_i_lista_velges_ikke(self):
        s = json.dumps(STEDER)
        v = self._j(f"parkVelgSted({{sted: 9, kilde: 'ko'}}, 'Borte', {s})")
        self.assertEqual((v['id'], v['kilde']), (None, 'ingen'))

    def test_kildelinja(self):
        tid = "'2026-10-01T20:00:00+00:00'"
        self.assertEqual(self._j(f"parkKildeTekst('ko', {tid})"), 'Fra KO-tavla 22:00')
        self.assertEqual(self._j(f"parkKildeTekst('registrering', {tid})"), 'Sist registrert 22:00')
        self.assertEqual(self._j("parkKildeTekst('telefon', null)"), 'Sist valgt på denne telefonen')
        self.assertEqual(self._j("parkKildeTekst('ingen', null)"), '')

    def test_alt_maa_vaere_valgt(self):
        full = "{lag: 1, sted: 2, problemstilling: 3, utfall: 4, antall: 1}"
        self.assertTrue(self._j(f'parkKanRegistrere({full})'))
        for felt in ('lag', 'sted', 'problemstilling', 'utfall'):
            self.assertFalse(self._j(f'parkKanRegistrere(Object.assign({full}, {{{felt}: null}}))'),
                             felt)
        for antall in (0, 100, 1.5):
            self.assertFalse(self._j(f'parkKanRegistrere(Object.assign({full}, {{antall: {antall}}}))'))
        self.assertTrue(self._j(f'parkKanRegistrere(Object.assign({full}, {{antall: 99}}))'))

    def test_neste_skjema_beholder_lag_og_sted(self):
        v = self._j("parkNesteSkjema({lag: 1, sted: 2, problemstilling: 3, utfall: 4, antall: 5})")
        self.assertEqual(v, {'lag': 1, 'sted': 2, 'problemstilling': None, 'antall': 1, 'utfall': None})

    def test_maalingen_i_kroppen(self):
        v = "{lag: 1, sted: 2, problemstilling: 3, utfall: 4, antall: '3'}"
        k = self._j(f"parkKropp({v}, {{id: 2, kilde: 'ko'}}, 'n')")
        self.assertEqual((k['forhandsvalg_kilde'], k['forhandsvalg_endret'], k['antall']), ('ko', False, 3))
        k = self._j(f"parkKropp({v}, {{id: 1, kilde: 'registrering'}}, 'n')")
        self.assertEqual((k['forhandsvalg_kilde'], k['forhandsvalg_endret']), ('registrering', True))
        k = self._j(f"parkKropp({v}, {{id: null, kilde: 'ingen'}}, 'n')")
        self.assertEqual((k['forhandsvalg_kilde'], k['forhandsvalg_endret']), ('ingen', False))

    def test_angrefristen(self):
        til = "'2026-10-01T20:05:00Z'"
        naa = "Date.parse('2026-10-01T20:04:30Z')"
        self.assertEqual(self._j(f'parkAngreSekunder({til}, {naa})'), 30)
        self.assertEqual(self._j(f"parkAngreSekunder({til}, Date.parse('2026-10-01T20:06:00Z'))"), 0)
        liste = f"[{{angre_til: {til}}}, {{angre_til: '2026-10-01T20:00:00Z'}}]"
        self.assertEqual(len(self._j(f'parkAktiveAngre({liste}, {naa})')), 1)

    def test_kvitteringen_viser_antall_bare_over_en(self):
        k = "{registrert_at: '2026-10-01T20:00:00Z', problemstilling: 'Skade', sted: 'Club', utfall: 'OK'}"
        self.assertEqual(self._j(f'parkKvitteringstekst(Object.assign({k}, {{antall: 3}}))'),
                         '22:00 · 3 × Skade · Club · OK')
        self.assertEqual(self._j(f'parkKvitteringstekst(Object.assign({k}, {{antall: 1}}))'),
                         '22:00 · Skade · Club · OK')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class OppsettReglerTests(SimpleTestCase):
    """`park-oppsett.js`: hvem som får knappene, hva en lenke er nå, og
    tidspunktene mellom skjemaet og serveren."""

    def setUp(self):
        self.harness = build_harness(((OPPSETT_JS, (
            'parkKanSetteOppUtfall', 'parkKanSletteVerdi', 'parkLenkeStatus',
            'parkLokalFelt', 'parkStandardOppetid')),))

    def _j(self, uttrykk):
        return json.loads(run_node(self.harness, f'console.log(JSON.stringify({uttrykk}));')
                          .splitlines()[0])

    def test_utfall_og_sletting_er_bare_admin(self):
        for fn in ('parkKanSetteOppUtfall', 'parkKanSletteVerdi'):
            self.assertTrue(self._j(f'{fn}({{park: "les", admin: true}})'), fn)
            self.assertFalse(self._j(f'{fn}({{park: "skriv_leder", admin: false}})'), fn)
            self.assertFalse(self._j(f'{fn}({{}})'), fn)
            self.assertFalse(self._j(f'{fn}(undefined)'), fn)

    def test_lenkens_status(self):
        l = "{fjernet: false, aapen_fra: '2026-10-01T08:00:00Z', aapen_til: '2026-10-02T08:00:00Z'}"
        self.assertEqual(self._j(f"parkLenkeStatus({l}, Date.parse('2026-10-01T07:59:00Z'))"), 'Ikke åpnet ennå')
        self.assertEqual(self._j(f"parkLenkeStatus({l}, Date.parse('2026-10-01T08:00:00Z'))"), 'Åpen')
        self.assertEqual(self._j(f"parkLenkeStatus({l}, Date.parse('2026-10-02T08:00:00Z'))"), 'Stengt')
        self.assertEqual(self._j(f"parkLenkeStatus(Object.assign({l}, {{fjernet: true}}), "
                                 f"Date.parse('2026-10-01T09:00:00Z'))"), 'Fjernet')

    def test_standardoppetiden_er_tre_dogn_i_lokal_tid(self):
        ut = run_node(self.harness, '''
          const ms = new Date(2026, 9, 1, 8, 5).getTime();
          console.log(JSON.stringify(parkStandardOppetid(ms)));''')
        self.assertEqual(json.loads(ut.splitlines()[0]),
                         {'fra': '2026-10-01T08:05', 'til': '2026-10-04T08:05'})


class ParkMarkupTests(SimpleTestCase):

    def test_ingen_markup_i_oppsettet_heller(self):
        kilde = read_js(OPPSETT_JS)
        kilde = re.sub(r'/\*.*?\*/', '', kilde, flags=re.S)
        kilde = re.sub(r'//[^\n]*', '', kilde)
        self.assertNotIn('innerHTML', kilde)
        self.assertEqual(re.findall(r'`[^`]*<[a-z][^`]*`', kilde), [])

    def test_ingen_markup_i_mal_strenger(self):
        """Navn fra serveren går gjennom `textContent`. En mal-streng med en
        tagg ville vært det første stedet et navn kunne bli til markup — og
        fila står ikke i noen XSS-skanner, nettopp fordi den ikke har noen."""
        kilde = read_js(PARK_JS)
        kilde = re.sub(r'/\*.*?\*/', '', kilde, flags=re.S)
        kilde = re.sub(r'//[^\n]*', '', kilde)
        self.assertNotIn('innerHTML', kilde)
        self.assertEqual(re.findall(r'`[^`]*<[a-z][^`]*`', kilde), [])
