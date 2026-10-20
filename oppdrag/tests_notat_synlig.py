"""Oppdragsnotatet i detaljvinduet: i en boks over hendelsen (20. okt. 2026).

André: «Oppdragsnotat på et oppdrag må være mer synlig. Nå kommer det etter mye tekst og innhold
fra loggen til knyttet hendelse. Oppdragsnotatet er viktig å lett få øye på og lese kjapt. Bør
plasseres over hendelse, og gjerne rammet inn i en liten boks.» Skisse B (boksen over hendelsen)
og E (en tynn stiplet linje uten notat) ble valgt.

Rekkefølgen prøves gjennom den ekte `visOppdrag()`, der den bestemmes — ikke ved å lese malen.
"""
from __future__ import annotations

import json

from django.test import SimpleTestCase

from patients.js_test_utils import OPPDRAG_SENTRAL_JS, build_harness, run_node

from .tests_flere_enheter import DetaljvinduetTegnesPaaNyttTests as _Detalj


class NotatetOverHendelsenTests(SimpleTestCase):
    """Harnessen og stubbene er de samme som prøven av at vinduet tegnes på nytt — lånt, ikke
    arvet, så den prøven ikke kjøres to ganger."""

    STUBB = _Detalj.STUBB

    def setUp(self):
        laant = _Detalj()
        laant.setUp()
        self.harness = laant.harness + '\n\n' + build_harness(
            ((OPPDRAG_SENTRAL_JS, ('notatSlettesHtml', 'notatSlettesTekst')),))

    def _innhold(self, fritekst, kan_skrive=True):
        kode = self.STUBB.replace("fritekst: ''", f"fritekst: {json.dumps(fritekst)}, hendelse_id: 4") + f"""
            globalThis.OPPDRAG_TILGANG = {{ kanSkrive: {str(kan_skrive).lower()} }};
            globalThis.koHendelseValg = () => '<div id="stubb-hendelsevalg"></div>';
            await visOppdrag(1);
            console.log(JSON.stringify(document.getElementById('detalj-innhold').innerHTML));
        """
        return json.loads([linje for linje in run_node(self.harness, kode).splitlines() if linje != 'OK'][-1])

    def test_notatet_staar_foer_hendelsen_og_etter_verdiene(self):
        html = self._innhold('Pasient ved inngang B')
        notat, hendelse, verdier = (html.index('id="oppdrag-notat"'), html.index('stubb-hendelsevalg'),
                                    html.index('id="oppdrag-verdier"'))
        self.assertLess(verdier, notat)
        self.assertLess(notat, hendelse)

    def test_boks_med_notat_og_stiplet_linje_uten(self):
        med = self._innhold('Pasient ved inngang B')
        self.assertIn('oppdrag-notat-boks', med)
        self.assertIn('Pasient ved inngang B', med)
        self.assertIn('data-action="visNotat">Endre', med)
        uten = self._innhold('')
        self.assertNotIn('oppdrag-notat-boks', uten, 'en tom boks skal ikke ta plassen')
        self.assertIn('oppdrag-notat-tom', uten)
        self.assertIn('Ingen oppdragsnotat', uten)
        self.assertIn('data-action="visNotat">Legg til', uten)

    def test_leser_faar_ingen_knapp_i_noen_av_dem(self):
        for tekst in ('Pasient ved inngang B', ''):
            with self.subTest(tekst=tekst):
                self.assertNotIn('visNotat', self._innhold(tekst, kan_skrive=False))
