"""`static/js/backlog.js`, kjørt i node.

Tre funksjoner avgjør noe her, og det er dem som prøves:
`backlogNivaaMinst()` bestemmer hvilke knapper som finnes,
`backlogTellertekst()` bestemmer hva lista *påstår* om hva den viser, og
`backlogTidspunkt()` bestemmer hva den påstår om når. Resten er markup, der
øyet er raskere enn en mutant — unntatt escapingen, som har sin egen prøve.
"""
from __future__ import annotations

import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import (JS_DIR, PORTAL_UTILS_JS, build_harness,
                                    node_available, run_node)

BACKLOG_JS = JS_DIR / 'backlog.js'

HARNESS = (
    (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
    (BACKLOG_JS, ('backlogNivaaMinst', 'backlogKanMeldeInn', 'backlogKanLose',
                  'backlogTellertekst', 'backlogTidspunkt', 'backlogTypemerke',
                  'backlogModulnavn', 'backlogKort', 'backlogKommentarrad')),
)

#: Konstanten på toppnivå klippes ikke med av `build_harness`, og uten den er
#: hvert oppslag `undefined` — da ville testen bestått på tull.
PREAMBLE = ('const NIVAA_RANG = {les: 0, les_alle: 1, skriv_handling: 2, '
            'skriv_full: 3, skriv_leder: 4};\n')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class NivaagatenTests(SimpleTestCase):
    """**Grensesnittet gater på `MODUL_TILGANG`, ikke på rollen** (CLAUDE.md).
    En knapp som fører til 403 er verre enn ingen knapp."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _kall(self, tilgang, uttrykk):
        ut = run_node(self.harness, f'''
          globalThis.window = {{ MODUL_TILGANG: {tilgang} }};
          console.log(JSON.stringify({uttrykk}));
        ''', preamble=PREAMBLE)
        return ut.splitlines()[0]

    def test_les_melder_ikke_inn_og_loser_ikke(self):
        self.assertEqual(self._kall("{backlog: 'les'}", 'backlogKanMeldeInn()'), 'false')
        self.assertEqual(self._kall("{backlog: 'les'}", 'backlogKanLose()'), 'false')

    def test_skriv_full_melder_inn_men_loser_ikke(self):
        self.assertEqual(
            self._kall("{backlog: 'skriv_full'}", 'backlogKanMeldeInn()'), 'true')
        self.assertEqual(
            self._kall("{backlog: 'skriv_full'}", 'backlogKanLose()'), 'false')

    def test_skriv_leder_gjor_begge(self):
        self.assertEqual(
            self._kall("{backlog: 'skriv_leder'}", 'backlogKanMeldeInn()'), 'true')
        self.assertEqual(
            self._kall("{backlog: 'skriv_leder'}", 'backlogKanLose()'), 'true')

    def test_global_admin_gjor_begge_uten_rad(self):
        self.assertEqual(self._kall('{admin: true}', 'backlogKanLose()'), 'true')

    def test_uten_tilgang_er_alt_stengt(self):
        """En side som ikke fikk satt `MODUL_TILGANG` skal vise minst mulig,
        ikke mest mulig."""
        self.assertEqual(self._kall('{}', 'backlogKanMeldeInn()'), 'false')
        self.assertEqual(self._kall('{}', 'backlogKanLose()'), 'false')

    def test_ukjent_nivaanavn_stenger(self):
        """Ukjent nivå gir False, ikke True — en skrivefeil skal stenge døra,
        samme regel som `har_tilgang` på serveren."""
        self.assertEqual(self._kall("{backlog: 'tull'}", 'backlogKanLose()'), 'false')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TellerenTests(SimpleTestCase):
    """**Et filter skal aldri skjule noe stille.** Telleren er det ene som
    hindrer at et filter satt forrige gang skjuler det innspillet noen leter
    etter."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _kall(self, uttrykk):
        return run_node(self.harness, f'console.log(JSON.stringify({uttrykk}));',
                        preamble=PREAMBLE).splitlines()[0]

    def test_ufiltrert_sier_bare_antallet(self):
        self.assertNotIn('filtrert', self._kall('backlogTellertekst(7, false)'))
        self.assertIn('7', self._kall('backlogTellertekst(7, false)'))

    def test_filtrert_sier_fra(self):
        svar = self._kall('backlogTellertekst(2, true)')
        self.assertIn('filtrert', svar)
        self.assertIn('2', svar)

    def test_null_treff_sier_det_ogsaa(self):
        """Null med filter er den tilstanden der teksten betyr mest."""
        self.assertIn('filtrert', self._kall('backlogTellertekst(0, true)'))


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TidspunktTests(SimpleTestCase):
    """`klokke()` i portal-utils gir bare «14:32». Riktig for en vakt der alt
    skjedde i dag — misvisende i en backlog der et innspill kan være tre uker
    gammelt."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _kall(self, iso):
        return run_node(
            self.harness,
            f'console.log(JSON.stringify(backlogTidspunkt({iso!r})));',
            preamble=PREAMBLE).splitlines()[0]

    def test_datoen_er_med_og_nullpolstret(self):
        """Nullpolstret fordi kolonnen skal stå rett i en liste — og fordi
        formatet da er det samme i hver nettleser. `toLocaleDateString` med
        `2-digit` ga «17.9.» i node og «17.09» andre steder."""
        svar = self._kall('2026-09-17T14:32:00+02:00')
        self.assertIn('17.09', svar, f'dag og måned mangler: {svar}')
        self.assertIn(':', svar, f'klokkeslettet mangler: {svar}')

    def test_tom_og_ugyldig_gir_tom_streng(self):
        self.assertEqual(self._kall(''), '""')
        self.assertEqual(self._kall('ikke en dato'), '""')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KortetEscaperTests(SimpleTestCase):
    """Tittel og beskrivelse er fritekst skrevet av en bruker, og kortet settes
    inn med `innerHTML`."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _tegn(self, felt, verdi):
        return run_node(self.harness, f'''
          globalThis.window = {{ MODUL_TILGANG: {{ backlog: 'les' }},
                                 BACKLOG_MODULER: [] }};
          const rad = {{id: 1, type: 'bug', type_navn: 'Bug', tittel: 'T',
                        beskrivelse: '', modul_slug: '', opprettet_av: 'kari',
                        opprettet_at: '2026-09-17T10:00:00Z', lost: false,
                        lost_av: '', kan_endres: false}};
          rad[{felt!r}] = {verdi!r};
          const html = backlogKort(rad);
          assert(!html.includes('<img'), 'raa <img> i kortet: ' + html);
          assert(html.includes('&lt;img'), 'ble ikke escapet: ' + html);
        ''', preamble=PREAMBLE)

    def test_tittelen_escapes(self):
        self.assertIn('OK', self._tegn('tittel', '<img src=x onerror=alert(1)>'))

    def test_beskrivelsen_escapes(self):
        self.assertIn('OK', self._tegn('beskrivelse', '<img src=x onerror=alert(1)>'))

    def test_innsendernavnet_escapes(self):
        self.assertIn('OK', self._tegn('opprettet_av', '<img src=x onerror=alert(1)>'))

    def test_kortet_viser_det_det_skal(self):
        """Sperrehake: en bygger som returnerte tom streng ville bestått
        testene over."""
        ut = run_node(self.harness, '''
          globalThis.window = { MODUL_TILGANG: { backlog: 'skriv_leder' },
                                BACKLOG_MODULER: [{slug: 'ko', navn: 'KO'}] };
          const html = backlogKort({id: 3, type: 1, type_navn: 'Bug',
            tittel: 'Nedtrekket lukker seg', beskrivelse: 'Skjer hver gang',
            modul_slug: 'ko', opprettet_av: 'kari',
            opprettet_at: '2026-09-17T10:00:00Z', lost: false, lost_av: '',
            kan_endres: false, kan_slettes: false, antall_kommentarer: 2});
          assert(html.includes('Nedtrekket lukker seg'), 'tittel mangler');
          assert(html.includes('Skjer hver gang'), 'beskrivelse mangler');
          assert(html.includes('KO'), 'modulnavnet mangler');
          assert(html.includes('backlogSettLost'), 'skriv_leder mangler loes-knapp');
          assert(!html.includes('backlogSlett'), 'slett-knapp uten kan_slettes');
          assert(html.includes('backlogApneKommentarer'), 'kommentarknappen mangler');
          assert(html.includes('> 2<'), 'kommentartelleren mangler: ' + html);
        ''', preamble=PREAMBLE)
        self.assertIn('OK', ut)

    def test_knappene_folger_nivaaet_og_fristen(self):
        """Kortene tegnes på nytt ved hvert filterbytte, så gatene må stå i
        byggeren — `gateKnapper()` setter `.d-none` én gang ved sidelasting."""
        ut = run_node(self.harness, '''
          globalThis.window = { MODUL_TILGANG: { backlog: 'skriv_full' },
                                BACKLOG_MODULER: [] };
          const base = {id: 3, type: 1, type_navn: 'Bug', tittel: 'T',
            beskrivelse: '', modul_slug: '', opprettet_av: 'kari',
            opprettet_at: '2026-09-17T10:00:00Z', lost: false, lost_av: '',
            antall_kommentarer: 0};

          const utenFrist = backlogKort({...base, kan_endres: false, kan_slettes: false});
          assert(!utenFrist.includes('backlogSettLost'),
                 'skriv_full skal ikke se loes-knappen');
          assert(!utenFrist.includes('backlogSlett'),
                 'uten kan_slettes skal slett vaere borte');

          const medFrist = backlogKort({...base, kan_endres: true, kan_slettes: true});
          assert(medFrist.includes('backlogSlett'), 'kan_slettes mangler slett');
          assert(medFrist.includes('backlogApneRediger'), 'kan_endres mangler rediger');

          // **Den nye skillelinja:** kommentert av andre -> kan redigeres,
          // men ikke slettes. En slett-knapp her ville foert til 409.
          const kommentert = backlogKort({...base, kan_endres: true, kan_slettes: false});
          assert(kommentert.includes('backlogApneRediger'), 'rediger mangler');
          assert(!kommentert.includes('backlogSlett'),
                 'slett skal vaere borte naar andre har kommentert');
        ''', preamble=PREAMBLE)
        self.assertIn('OK', ut)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KommentarradTests(SimpleTestCase):
    """Kommentarteksten er fritekst skrevet av en bruker, og raden settes inn
    med `innerHTML`."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def test_teksten_og_navnet_escapes(self):
        ut = run_node(self.harness, """
          const html = backlogKommentarrad({
            id: 1, tekst: '<img src=x onerror=alert(1)>',
            opprettet_av: '<b>kari</b>',
            opprettet_at: '2026-09-17T10:00:00Z', kan_endres: false});
          assert(!html.includes('<img'), 'raa <img> i kommentaren: ' + html);
          assert(!html.includes('<b>kari'), 'raa markup i navnet: ' + html);
          assert(html.includes('&lt;img'), 'teksten ble ikke escapet');
        """, preamble=PREAMBLE)
        self.assertIn('OK', ut)

    def test_sletteknappen_folger_fristen(self):
        """Sperrehake mot testen over, og selve regelen: `kan_endres` kommer
        fra serveren, som eier tida."""
        ut = run_node(self.harness, """
          const base = {id: 1, tekst: 'Hei', opprettet_av: 'kari',
                        opprettet_at: '2026-09-17T10:00:00Z'};
          const min = backlogKommentarrad({...base, kan_endres: true});
          assert(min.includes('Hei'), 'teksten mangler');
          assert(min.includes('backlogSlettKommentar'), 'slett mangler innen fristen');

          const annens = backlogKommentarrad({...base, kan_endres: false});
          assert(annens.includes('Hei'), 'teksten mangler');
          assert(!annens.includes('backlogSlettKommentar'),
                 'slett skal vaere borte uten kan_endres');
        """, preamble=PREAMBLE)
        self.assertIn('OK', ut)
