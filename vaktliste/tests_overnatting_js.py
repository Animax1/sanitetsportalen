# -*- coding: utf-8 -*-
"""Overnatting i nettleseren (25. sep. 2026): natta fanen åpner på, hvem som
får plassere, kapasitetsvarselet, escapingen og at panelet faktisk tegner
fanen. Kjøres i node gjennom de ekte byggerne."""
import json
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import (PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness,
                                    node_available, run_node)

FUNKSJONER = (
    '_overnatting', '_nattIso', 'overnattingStandardnatt', '_valgtNatt',
    'overnattingNattTekst', '_overnattingsfane', '_folkIRom', 'overnattingFyll',
    'kanPlassereKorps', 'kanPlassereNoen', '_paaVaktTekst', '_overnattingTelling',
    'overnattingUtenSeng', '_nattvelger', '_brannrutineboks', '_sengerad', '_romkort',
    '_utenSengBolk', 'mkBrannliste', 'mkOvernatting', 'overnattingHvorSover',
    'tegnPanel', '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanLede', '_d', '_kl')

FORSPILL = """
globalThis.OVERNATTING = 'overnatting'; globalThis.overnattingNatt = null;
globalThis.overnattingUtskrift = 'natt';
globalThis.MANNSKAP = 'mannskap'; globalThis.OVERSIKT = 'oversikt';
globalThis.BELASTNING = 'belastning'; globalThis.PLANLEGGER = 'planlegger';
globalThis.TILSTEDE = 'tilstede'; globalThis.IKKE_PLASSERT = 'ikke-plassert';
globalThis.MITT_KORPS = 'mitt-korps';
const L = (d, t, m = 0) => new Date(2026, 9, d, t, m).toISOString();
const P = (id, rom_id, mannskap_id, natt, navn, korps_id, paa_vakt = []) => ({
  id, rom_id, mannskap_id, natt, navn, korps_id, korps_kort: korps_id === 1 ? 'HGSD' : 'KAR',
  telefon: '900', paa_vakt, er_paa_vakt: paa_vakt.length > 0});
globalThis.aktivListe = {
  vaktliste: {id: 1, vakt_navn: 'Vakta'},
  mannskap: [], vaktposter: [],
  overnatting: {
    netter: ['2026-10-02', '2026-10-03'], netter_i_vakta: ['2026-10-02', '2026-10-03'],
    rom: [{id: 1, navn: 'Klasserom 2B', plassering: 'Skolen', kapasitet: 2, merknad: ''},
          {id: 2, navn: 'Gymsal', plassering: '', kapasitet: null, merknad: ''}],
    plasseringer: [
      P(1, 1, 10, '2026-10-02', 'Kari', 1,
        [{ressurs: 'Lag 1', fra: L(2, 22), til: L(3, 6)}]),
      P(2, 1, 11, '2026-10-02', 'Ola', 2),
      P(3, 2, 10, '2026-10-03', 'Kari', 1)],
    brannrutine: 'Samleplass nord'},
};
globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_leder' }, MITT_KORPS_ID: null };
"""


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class OvernattingJsTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
            (VAKTLISTE_JS, FUNKSJONER),
        ))

    def _kjor(self, kode):
        ut = run_node(self.harness, kode, preamble=FORSPILL).splitlines()
        return ut[:-1] if ut and ut[-1] == 'OK' else ut

    def _markup(self, kode='', nivaa='skriv_leder', korps='null'):
        ut = self._kjor(f"""
            window.MODUL_TILGANG = {{ vaktliste: '{nivaa}' }};
            window.MITT_KORPS_ID = {korps};
            overnattingNatt = '2026-10-02';
            {kode}
            console.log(JSON.stringify(mkOvernatting()));
        """)
        return json.loads(ut[0])

    # ── Reglene ──────────────────────────────────────────────────────────

    def test_standardnatta(self):
        """I natta under vakta; før klokka tolv er det natta fra kvelden før;
        før vakta den første; etter vakta den siste."""
        ut = self._kjor("""
            const n = ['2026-10-02', '2026-10-03'];
            console.log(overnattingStandardnatt(n, new Date(2026, 9, 2, 23)));
            console.log(overnattingStandardnatt(n, new Date(2026, 9, 3, 3)));
            console.log(overnattingStandardnatt(n, new Date(2026, 9, 3, 11, 59)));
            console.log(overnattingStandardnatt(n, new Date(2026, 9, 3, 12)));
            console.log(overnattingStandardnatt(n, new Date(2026, 8, 20, 12)));
            console.log(overnattingStandardnatt(n, new Date(2026, 9, 9, 12)));
            console.log(overnattingStandardnatt([], new Date(2026, 9, 2, 23)));
        """)
        self.assertEqual(ut, ['2026-10-02', '2026-10-02', '2026-10-02', '2026-10-03',
                              '2026-10-02', '2026-10-03', 'null'])

    def test_valgt_natt_som_ikke_finnes_faller_tilbake(self):
        ut = self._kjor("""
            overnattingNatt = '2026-10-03'; console.log(_valgtNatt());
            overnattingNatt = '2030-01-01'; console.log(_valgtNatt() !== '2030-01-01');
        """)
        self.assertEqual(ut, ['2026-10-03', 'true'])

    def test_natt_tekst_bruker_morgenens_dag(self):
        ut = self._kjor("""
            console.log(overnattingNattTekst('2026-10-02'));
            console.log(overnattingNattTekst('2026-10-31'));
        """)
        self.assertEqual(ut, ['Natt til lørdag 03.10', 'Natt til søndag 01.11'])

    def test_kapasiteten_varsler(self):
        ut = self._kjor("""
            const r = {kapasitet: 2};
            console.log([1, 2, 3].map((n) => overnattingFyll(r, n)).join('|'));
            console.log(overnattingFyll({kapasitet: null}, 99) === '');
        """)
        self.assertEqual(ut, ['|full|over', 'true'])

    def test_hvem_som_faar_plassere(self):
        """Speiler `kan_fore_korps`: alle for `skriv_full`+, eget korps for
        korps-føreren, ingen for `les` — og ingen uten badge."""
        ut = self._kjor("""
            const svar = (nivaa, badge) => {
              window.MODUL_TILGANG = { vaktliste: nivaa }; window.MITT_KORPS_ID = badge;
              return [kanPlassereKorps(1), kanPlassereKorps(2), kanPlassereNoen()].join(',');
            };
            console.log(svar('skriv_full', null));
            console.log(svar('skriv_handling', 1));
            console.log(svar('skriv_handling', null));
            console.log(svar('les_alle', 1));
            window.MODUL_TILGANG = { admin: true }; window.MITT_KORPS_ID = null;
            console.log(kanPlassereKorps(2));
        """)
        self.assertEqual(ut, ['true,true,true', 'true,false,true', 'false,false,false',
                              'false,false,false', 'true'])

    def test_uten_seng_er_bare_de_med_vakt_i_doegnet_og_ikke_avmeldt(self):
        ut = self._kjor("""
            const VP = (mannskap_id, navn, fra, til, avmeldt_at = null) => ({
              mannskap_id, navn, fra_tid: fra, til_tid: til, avmeldt_at, korps_kort: ''});
            aktivListe.vaktposter = [
              VP(10, 'Kari', L(2, 14), L(2, 22)),     // sover i 2B — ikke med
              VP(12, 'Per', L(2, 14), L(2, 22)),      // med
              VP(12, 'Per', L(2, 22), L(3, 6)),       // samme person, én gang
              VP(13, 'Anne', L(2, 8), L(2, 11)),      // før tolv — ikke med
              VP(14, 'Bo', L(2, 20), L(3, 2), L(1, 9)),  // avmeldt — ikke med
              VP(null, '', L(2, 14), L(2, 22)),       // ledig plass
            ];
            console.log(overnattingUtenSeng('2026-10-02').map((v) => v.navn).join(','));
        """)
        self.assertEqual(ut, ['Per'])

    # ── Byggerne ─────────────────────────────────────────────────────────

    def test_rommet_viser_folkene_natta_og_telleren(self):
        m = self._markup()
        self.assertIn('Klasserom 2B', m)
        self.assertIn('Kari', m)
        self.assertIn('Ola', m)
        self.assertIn('Fullt', m)
        self.assertIn('På vakt Lag 1', m)
        # To overnatter, én på vakt, én skal være inne.
        self.assertRegex(m, r'<strong>2</strong> overnatter')
        self.assertRegex(m, r'<strong>1</strong> skal være inne')
        self.assertIn('Samleplass nord', m)

    def test_paa_vakt_uten_detaljer_telles_og_merkes(self):
        """**C1:** en ren `les` får `er_paa_vakt` for et annet korps, men ikke
        skiftene. Tellingen og merket skal stå likevel — uten dem sier
        brannlista at Ola skal være inne mens han kjører ambulansen."""
        m = self._markup("""
            const ola = aktivListe.overnatting.plasseringer[1];
            ola.er_paa_vakt = true; ola.paa_vakt = [];""", nivaa='les', korps='1')
        self.assertRegex(m, r'<strong>0</strong> skal være inne')
        rad_ola = m.split('Ola')[1].split('</tr>')[0]
        self.assertIn('På vakt', rad_ola)

    def test_en_annen_natt_viser_sine_egne(self):
        m = self._markup("overnattingNatt = '2026-10-03';").split('vl-brannliste')[0]
        self.assertNotIn('Ola', m)
        self.assertIn('Ingen sover her denne natta', m)

    def test_markup_i_data_kommer_ut_som_tekst(self):
        m = self._markup("""
            aktivListe.overnatting.rom[0].navn = '<img src=x onerror=alert(1)>';
            aktivListe.overnatting.rom[0].merknad = '<b>nød</b>';
            aktivListe.overnatting.rom[0].plassering = '<i>etg</i>';
            aktivListe.overnatting.plasseringer[1].navn = '<script>x</script>';
            aktivListe.overnatting.plasseringer[0].paa_vakt[0].ressurs = '<u>bil</u>';
            aktivListe.overnatting.brannrutine = '<svg onload=alert(1)>';
            aktivListe.vaktliste.vakt_navn = '<em>vakt</em>';
        """)
        for rå in ('<img', '<script>', '<b>nød', '<i>etg', '<u>bil', '<svg', '<em>vakt'):
            with self.subTest(rå=rå):
                self.assertNotIn(rå, m)
        self.assertIn('&lt;script&gt;', m)
        self.assertIn('&lt;svg', m)

    def test_leseren_ser_lista_uten_knapper(self):
        m = self._markup(nivaa='les')
        self.assertIn('Kari', m)
        for knapp in ('apnePlasser', 'apneRedigerRom', 'apneNyttRom', 'fjernOvernatting',
                      'apneBrannrutine'):
            with self.subTest(knapp=knapp):
                self.assertNotIn(knapp, m)
        self.assertIn('skrivUtBrannliste', m)

    def test_korpsfoereren_fjerner_bare_sine_egne(self):
        m = self._markup(nivaa='skriv_handling', korps='1')
        self.assertIn('data-action="apnePlasser"', m)
        self.assertEqual(m.count('data-action="fjernOvernatting"'), 1)
        self.assertIn('data-id="1"', m)            # Kari, HGSD
        self.assertNotIn('apneRedigerRom', m)
        self.assertNotIn('apneNyttRom', m)

    def test_lederen_faar_oppsettknappene(self):
        m = self._markup()
        for knapp in ('apneNyttRom', 'apneRedigerRom', 'apneBrannrutine', 'apnePlasser'):
            with self.subTest(knapp=knapp):
                self.assertIn(knapp, m)

    def test_brannlista_er_valgt_natt_eller_alle(self):
        en = self._markup().split('class="vl-brannliste"')[1]
        self.assertEqual(en.count('vl-brannliste-ark'), 1)
        self.assertIn('Natt til lørdag 03.10', en)
        self.assertIn('PÅ VAKT Lag 1', en)
        alle = self._markup("overnattingUtskrift = 'alle';").split('class="vl-brannliste"')[1]
        self.assertEqual(alle.count('vl-brannliste-ark'), 2)

    def test_et_tomt_rom_kommer_ikke_paa_papiret(self):
        """Lørdagsnatta har bare Gymsalen; et tomt 2B på arket er en tabell
        nattevakta må lese for å se at den er tom."""
        ark = self._markup("overnattingNatt = '2026-10-03';").split('class="vl-brannliste"')[1]
        self.assertIn('Gymsal', ark)
        self.assertNotIn('Klasserom 2B', ark)

    def test_brannlista_uten_rutine_har_en_linje_aa_skrive_paa(self):
        m = self._markup("aktivListe.overnatting.brannrutine = '';")
        self.assertIn('Samleplass ved alarm: ____', m)

    def test_vakt_uten_netter_sier_hva_som_maa_gjoeres(self):
        m = self._markup("aktivListe.overnatting.netter = [];")
        self.assertIn('Vakta går ikke over noen natt', m)

    # ── Fanen og panelet ─────────────────────────────────────────────────

    def test_fanen_finnes_for_lederen_og_for_leseren_bare_naar_det_er_rom(self):
        ut = self._kjor("""
            const fane = () => JSON.stringify(_overnattingsfane());
            overnattingNatt = '2026-10-02';
            window.MODUL_TILGANG = { vaktliste: 'les' };
            console.log(fane());
            aktivListe.overnatting.rom = [];
            console.log(fane());
            window.MODUL_TILGANG = { vaktliste: 'skriv_leder' };
            console.log(fane() !== 'null');
        """)
        self.assertEqual(json.loads(ut[0])['antall'], 2)
        self.assertEqual(ut[1:], ['null', 'true'])

    def test_panelet_tegner_fanen(self):
        """Kallstedet i `tegnPanel()`, ikke bare byggeren."""
        ut = self._kjor("""
            const el = { innerHTML: '', classList: { toggle() {} } };
            globalThis.document = { getElementById: () => el };
            globalThis.aktivFane = OVERNATTING;
            tegnPanel();
            console.log(el.innerHTML.includes('Klasserom 2B'));
        """)
        self.assertEqual(ut, ['true'])
