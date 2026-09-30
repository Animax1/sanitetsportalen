"""Pulje 1 av vaktlistegjennomgangen (30. sep. 2026): flaten for korps-føreren.

Fire regler, prøvd i node gjennom de ekte funksjonene:

1. **«Ikke plassert»** regner «plassert» mot hele lista, og korpsvelgeren
   filtrerer personene. Før sto folk fra et annet korps som faktisk var satt
   opp, som uplassert så snart vaktlederen valgte et korps.
2. **Startfanen**: korps-føreren med badge lander på «Mitt korps».
3. **E-posthintet** lover bare det `_koble_paa_epost` faktisk gjør.
4. **Kompetansene** er avkryssinger, og skjemaet viser hele det lagrede settet
   — også det stigen impliserer, ellers fjerner en lagring det.

Der det lar seg gjøre går testen gjennom kallstedet (`byttVaktliste`,
`_fyllPersonskjema`), ikke bare regelfunksjonen: regel 3 om mutasjoner i
`CLAUDE.md`.
"""
from __future__ import annotations

import json

from django.test import SimpleTestCase

from patients.js_test_utils import (
    PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness, node_available, run_node,
)

KONSTANTER = """
const OVERSIKT = 'oversikt';
const MITT_KORPS = 'mitt-korps';
"""


class _Node(SimpleTestCase):
    FUNKSJONER: tuple = ()

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = KONSTANTER + build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
            (VAKTLISTE_JS, self.FUNKSJONER),
        ))

    def _kjor(self, kode, preamble=''):
        return run_node(self.harness, kode, preamble=preamble)


class IkkePlassertTests(_Node):
    FUNKSJONER = ('_ikkePlassert',)

    LISTE = """
      globalThis.aktivListe = {
        mannskap: [
          {id: 1, navn: 'Kari', korps_id: 10},   // A, plassert
          {id: 2, navn: 'Ola', korps_id: 10},    // A, ikke plassert
          {id: 3, navn: 'Per', korps_id: 20},    // B, plassert
          {id: 4, navn: 'Siv', korps_id: 20},    // B, ikke plassert
        ],
        alle_vaktposter: [{id: 7, mannskap_id: 1, korps_id: 10},
                          {id: 8, mannskap_id: 3, korps_id: 20}],
      };
    """

    def _navn(self, korpsfilter):
        # `vaktposter` er det korpsvelgeren har filtrert — slik
        # `brukKorpsfilter()` gjør det i nettleseren.
        ut = self._kjor(self.LISTE + f"""
            globalThis.korpsfilter = {json.dumps(korpsfilter)};
            aktivListe.vaktposter = korpsfilter == null ? aktivListe.alle_vaktposter
              : aktivListe.alle_vaktposter.filter((vp) => vp.korps_id === korpsfilter);
            console.log(_ikkePlassert().map((m) => m.navn).join(','));
        """)
        return ut.splitlines()[0]

    def test_uten_korpsvalg_er_det_alle_som_ikke_staar_noe_sted(self):
        self.assertEqual(self._navn(None), 'Ola,Siv')

    def test_plassert_fra_et_annet_korps_er_ikke_uplassert(self):
        """Feilen: med korps A valgt sto Per (B, satt opp) som uplassert."""
        self.assertNotIn('Per', self._navn(10))

    def test_korpsvalget_filtrerer_personene(self):
        self.assertEqual(self._navn(10), 'Ola')
        self.assertEqual(self._navn(20), 'Siv')


class StartfaneTests(_Node):
    FUNKSJONER = ('startfane', '_nivaa', '_erAdmin', 'byttVaktliste')

    def _fane(self, *, nivaa, admin=False, badge=5):
        ut = self._kjor(f"""
            globalThis.window = {{
              MODUL_TILGANG: {{ vaktliste: {json.dumps(nivaa)}, admin: {json.dumps(admin)} }},
              MITT_KORPS_ID: {json.dumps(badge)},
            }};
            globalThis.aktivFane = 'noe-annet';
            globalThis.lastListe = () => {{}};
            globalThis.document = {{ getElementById: () => ({{ value: '3' }}) }};
            byttVaktliste();
            console.log(aktivFane);
        """)
        return ut.splitlines()[0]

    def test_korpsforeren_lander_paa_mitt_korps(self):
        self.assertEqual(self._fane(nivaa='skriv_handling'), 'mitt-korps')

    def test_uten_badge_er_det_oversikt(self):
        """Uten badge finnes ikke fanen — da skal hun ikke lande på den."""
        self.assertEqual(self._fane(nivaa='skriv_handling', badge=None), 'oversikt')

    def test_de_som_ser_alle_starter_paa_oversikt(self):
        for nivaa in ('les', 'les_alle', 'skriv_full', 'skriv_leder'):
            with self.subTest(nivaa=nivaa):
                self.assertEqual(self._fane(nivaa=nivaa), 'oversikt')
        self.assertEqual(self._fane(nivaa='skriv_handling', admin=True), 'oversikt')


class PersonskjemaTests(_Node):
    FUNKSJONER = ('_fyllPersonskjema', 'mkKompetansevalg', 'epostHint', 'kanLede',
                  '_nivaa', '_erAdmin')

    DOM = """
      const _el = {};
      globalThis.document = { getElementById: (id) => (_el[id] ||= {
        id, innerHTML: '', textContent: '', value: '', checked: false,
        classList: { toggle() {} },
      }) };
      globalThis._fyll = () => {};
      globalThis._settVerdi = () => {};
      globalThis.velgTekst = () => 'Velg';
    """

    def _fyll(self, nivaa, person='null'):
        ut = self._kjor(f"""
            globalThis.window = {{ MODUL_TILGANG: {{ vaktliste: {json.dumps(nivaa)} }} }};
            globalThis.register = {{
              korps: [], kontoer: [],
              kompetanser: [
                {{id: 1, navn: 'AFØR', er_aktiv: true}},
                {{id: 2, navn: 'VFØR', er_aktiv: true}},
                {{id: 3, navn: '<b>Lege</b>', er_aktiv: true}},
              ],
            }};
            _fyllPersonskjema({person});
            console.log(JSON.stringify({{
              valg: document.getElementById('person-kompetanser').innerHTML,
              hint: document.getElementById('person-epost-hint').textContent,
            }}));
        """, preamble=self.DOM)
        return json.loads(ut.splitlines()[0])

    def test_hintet_lover_ikke_korpsforeren_en_kobling(self):
        hint = self._fyll('skriv_handling')['hint']
        self.assertIn('vaktleder', hint)
        self.assertNotIn('av seg selv', hint)

    def test_hintet_til_lederen_sier_naar_det_skjer(self):
        self.assertIn('når du lagrer', self._fyll('skriv_leder')['hint'])

    def test_kompetansene_er_avkryssinger_og_escapes(self):
        valg = self._fyll('skriv_leder')['valg']
        self.assertEqual(valg.count('type="checkbox"'), 3)
        self.assertNotIn('<b>Lege</b>', valg)
        self.assertIn('&lt;b&gt;Lege', valg)

    def test_skjemaet_viser_hele_det_lagrede_settet(self):
        """VFØR er implisert av AFØR og utelatt fra `kompetanser`, men står i
        `alle_kompetanser`. Vises den ikke avkrysset, fjerner neste lagring den."""
        person = json.dumps({
            'id': 9, 'navn': 'Kari', 'korps_id': 1, 'telefon': '', 'epost': '',
            'issi': '', 'user_id': None, 'notat': '', 'er_aktiv': True,
            'kompetanser': [{'id': 1, 'navn': 'AFØR'}],
            'alle_kompetanser': [{'id': 1, 'navn': 'AFØR'}, {'id': 2, 'navn': 'VFØR'}],
        })
        valg = self._fyll('skriv_leder', person)['valg']
        self.assertEqual(valg.count(' checked'), 2)
        self.assertRegex(valg, r'id="person-komp-2"[^>]*\schecked')
