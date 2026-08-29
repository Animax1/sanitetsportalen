"""XSS-vern for oppdragsmodulens JS.

Samme mekanikk som `patients/tests_xss_stats.py`, men for denne modulens
byggere. Testen ligger her og ikke der fordi modulen eier sine egne flater —
og fordi lista over byggere må oppdateres av den som legger til en ny.

**Fritekst er portalens første virkelig frie felt som ikke er en
nedtrekksliste.** Pasientmodulens kliniske felt er alle valgt fra en fast
verdimengde; her skriver en operatør hva som helst, og det settes inn i DOM-en
med `innerHTML`.
"""
import re

from django.test import SimpleTestCase

from patients.js_test_utils import (
    OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness, extract_function,
    node_available, read_js, run_node,
)

# Funksjonene som bygger HTML av data fra API-et.
HTML_BUILDERS = (
    'renderEnheter',
    'renderOppdrag',
    'tidslinjeHtml',
    'renderLokasjonsadmin',
    'renderEnhetsadmin',
)

ESCAPING_CALLS = ('escHtmlValue(', 'cellHtml(', '_escHtml(', 'escapeHtml(')

REVIEWED_INTERPOLATIONS = {
    'klasse': 'intern CSS-klasse valgt av en ternær i koden',
    'tidKlasse': 'intern CSS-klasse valgt av en ternær i koden',
    'tittel': 'hardkodet title-attributt fra en ternær',
    'dempet': 'hardkodet CSS-klasse fra en ternær',
    # `meta` er ren tekst, ikke markup, og escapes én gang ved innsetting.
    # Escapet vi her også, ville teksten blitt dobbeltescapet i visningen.
    'e.status_navn': 'bygger ren tekst i `meta`, som escapes ved innsetting',
    'e.antall_ventende': 'tall, i samme rene tekst som escapes ved innsetting',
    # Fragmentene bygges to linjer over interpolasjonen, med escapet innhold.
    # De er hoistet ut av mal-strengen nettopp for at denne testen skal kunne
    # lese dem: en nøstet mal-streng inne i en ${...} er usynlig for regexen.
    'fritekstBlokk': 'markup bygget lokalt, fritekst escapet inni',
    'notatBlokk': 'markup bygget lokalt, notatene escapet inni',
    'knapp': 'markup bygget lokalt, id escapet inni',
    'valg': 'options bygget lokalt, brukernavn escapet inni',
    'valgt': 'hardkodet selected-attributt fra en ternær',
}


def _uten_kommentarer(kilde: str) -> str:
    """Fjern `//`-kommentarer før skanningen.

    Uten dette leser gjennomgangen sine egne forklaringer: en kommentar som
    nevner `${...}` for å beskrive regelen ble selv rapportert som en
    uescapet interpolasjon. Samme grep som i `JsModulLastingTests`, der en
    kommentar om `toggleForstehjelper()` ellers hadde telt som et kall.
    """
    return '\n'.join(
        linje for linje in kilde.splitlines() if not linje.lstrip().startswith('//'))


class OppdragEscapingKildeTests(SimpleTestCase):
    """Statisk gjennomgang: hver `${...}` escapes, eller står oppført her."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = read_js(OPPDRAG_SENTRAL_JS)

    def test_byggerne_finnes(self):
        """Vern mot at testen blir tom fordi en funksjon er omdøpt."""
        for navn in HTML_BUILDERS:
            with self.subTest(navn=navn):
                self.assertIn(f'function {navn}(', self.src)

    def test_sida_laster_ikke_patients_utils(self):
        """`patients-utils.js` gjør arbeid på toppnivå og kaster her.

        Regelen står i CLAUDE.md. Den håndheves for pasientsiden og
        statistikksiden av `JsModulLastingTests`; denne dekker malen vår.
        """
        from pathlib import Path
        from django.conf import settings
        mal = (Path(settings.BASE_DIR) / 'templates' / 'oppdrag' / 'sentral.html').read_text()
        self.assertNotIn('patients-utils.js', mal)
        self.assertIn('portal-utils.js', mal)

    def test_alle_interpolasjoner_er_escapet_eller_gjennomgatt(self):
        uescapet = []
        for navn in HTML_BUILDERS:
            body = _uten_kommentarer(extract_function(self.src, navn))
            for uttrykk in re.findall(r'\$\{([^}]*)\}', body):
                uttrykk = uttrykk.strip()
                if uttrykk.startswith(ESCAPING_CALLS):
                    continue
                if uttrykk in REVIEWED_INTERPOLATIONS:
                    continue
                uescapet.append(f'{navn}(): ${{{uttrykk}}}')

        self.assertEqual(uescapet, [], (
            'Uescapede interpolasjoner i oppdrag-byggerne:\n  '
            + '\n  '.join(uescapet)
            + '\n\nPakk verdien i escapeHtml() (eller trustedHtml() hvis det er '
              'markup du har bygget selv), eller legg uttrykket i '
              'REVIEWED_INTERPOLATIONS i denne fila med en begrunnelse.'
        ))


class OppdragEscapingOppforselTests(SimpleTestCase):
    """Kjør byggerne i node og se at markup i data kommer ut som tekst."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml')),
        (OPPDRAG_SENTRAL_JS, ('renderOppdrag', 'renderEnheter', 'tidslinjeHtml',
                              'hastegradKlasse', 'klokke')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_fritekst_med_markup_kommer_ut_som_tekst(self):
        """Det farligste feltet i modulen: en operatør skriver fritt."""
        ut = run_node(self.harness, '''
            globalThis.oppdragsliste = [{
              id: 1, status: 'venter', status_navn: 'Venter',
              enhet_navn: 'E1', lokasjon_navn: 'Scene',
              problemstilling: 'Pustevansker', hastegrad: 'Akutt',
              opprettet: '2026-08-28T20:00:00Z',
              fritekst: '<img src=x onerror=alert(1)>'
            }];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            renderOppdrag();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)

    def test_enhetsnavn_escapes(self):
        ut = run_node(self.harness, '''
            globalThis.enheter = [{
              id: 1, navn: '<b>56</b>', status: 'ledig',
              status_navn: 'Ledig', antall_ventende: 0
            }];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            renderEnheter();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('<b>56</b>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_statusklassen_kommer_fra_data_og_escapes(self):
        """Statusen brukes i et class-attributt — et bruddpunkt for attributt-XSS."""
        ut = run_node(self.harness, '''
            globalThis.enheter = [{
              id: 1, navn: 'E1', status: '" onload="alert(1)',
              status_navn: 'Rar', antall_ventende: 0
            }];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            renderEnheter();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('onload="alert(1)"', ut)

    def test_meldt_av_i_tidslinjen_escapes(self):
        ut = run_node(self.harness, '''
            console.log(tidslinjeHtml({
              historikk: [],
              enhetsbytter: [{
                id: 1, fra_enhet: 'A', til_enhet: 'B',
                tidspunkt: '2026-08-28T20:00:00Z',
                byttet_av: '<script>x</script>'
              }]
            }));
        ''')
        self.assertNotIn('<script>x', ut)
