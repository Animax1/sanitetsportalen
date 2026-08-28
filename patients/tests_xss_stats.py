"""Tester for escaping i statistikkfanen (N6).

Bakgrunn: statistikk-tabellene bygde HTML-strenger og satte dem inn med
``innerHTML`` uten å escape verdiene. Rad- og kolonnenøklene i krysstabellene
*er* pasientdata (problemstilling, transport, grovsortering, utskrevet_til),
og CSP-en tillater fortsatt ``unsafe-inline`` for ``script-src`` (F5), så et
injisert ``<img onerror=...>`` ville kjørt.

To lag med tester:

1. ``StatsEscapingBehaviourTests`` kjører tabell-byggerne i node og
   verifiserer akseptansekriteriet direkte: en feltverdi med HTML skal vises
   som tekst. Hoppes over hvis node ikke finnes.
2. ``StatsEscapingSourceGuardTests`` leser JS-kilden og krever at *hver*
   interpolasjon i byggerne er escapet eller står på en gjennomgått liste.
   Det er lag to som fanger opp nye tabeller – F6 legger til sju nye
   krysstabeller, og de skal ikke kunne gli inn uescapet.

Kjør med: python manage.py test patients.tests_xss_stats
"""
import re
import shutil
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import (
    ADMIN_JS, PORTAL_UTILS_JS, STATISTIKK_JS,
    build_harness, extract_function, read_js, run_node,
)

# Funksjonene som bygger HTML fra pasientdata. Endres denne lista, må
# gjennomgangen under (REVIEWED_INTERPOLATIONS) oppdateres i samme runde.
HTML_BUILDERS = (
    'mkStatsTable',
    'mkCrosstab',
    'mkObsTable',
    'mkInterpretation',
    'renderForstehjelperAdmin',
    'renderHelsepersonellAdmin',
)

# Funksjoner som escaper – en interpolasjon som starter med én av disse er OK.
ESCAPING_CALLS = ('escHtmlValue(', 'cellHtml(', '_escHtml(', 'escapeHtml(')

# Interpolasjoner som er gjennomgått manuelt og ikke trenger escaping, med
# begrunnelse. Alt utenfor denne lista og ESCAPING_CALLS gjør testen rød.
REVIEWED_INTERPOLATIONS = {
    # Interne, kodebestemte strenger – ingen data fra basen
    'cls': 'intern CSS-klasse valgt av en ternær i koden',
    'barColor': 'hardkodet hex-farge fra en ternær',
    's': 'resultatet av cellHtml() – allerede escapet eller klarert',
    'pctStr': 'bygget lokalt av Math.round() på et tall',

    # Tall utledet i JS, ikke strenger fra basen
    'Math.round(pct)': 'tall',
    'Math.min(100,pct)': 'tall (pct går gjennom Number() over)',
    'pct.toFixed(1)': 'tall',
    'rowTotal': 'sum av tall',
    'b.id': 'primærnøkkel (tall) fra API-et',
    'h.id': 'primærnøkkel (tall) fra API-et',

    # fmtMin() returnerer alltid en tallformatert streng
    'fmtMin(tt.mean)': 'fmtMin() bygger strengen av tall',
    'fmtMin(tt.median)': 'fmtMin() bygger strengen av tall',
    'fmtMin(ot.mean)': 'fmtMin() bygger strengen av tall',
    'fmtMin(ot.median)': 'fmtMin() bygger strengen av tall',
    "row.avg != null ? fmtMin(row.avg) : '–'": 'fmtMin() eller en bindestrek',

    # Ternærer med hardkodede alternativer på begge sider
    "b.is_active ? '' : 'text-muted'": 'hardkodet CSS-klasse',
    "h.is_active ? '' : 'text-muted'": 'hardkodet CSS-klasse',
    "b.is_active ? '' : ' <em>(inaktiv)</em>'": 'hardkodet markup',
    "h.is_active ? '' : ' <em>(inaktiv)</em>'": 'hardkodet markup',
    "b.is_active ? 'Deaktiver' : 'Aktiver'": 'hardkodet tekst',
    "h.is_active ? 'Deaktiver' : 'Aktiver'": 'hardkodet tekst',
    "b.is_active ? 'toggle-on' : 'toggle-off'": 'hardkodet ikonnavn',
    "h.is_active ? 'toggle-on' : 'toggle-off'": 'hardkodet ikonnavn',

    # Testnavnene escapes der listene bygges, ikke der de settes inn.
    # test_testnavn_escapes_ved_konstruksjon under vokter det.
    "sigTests.join(', ')": 'elementene escapes med escHtmlValue() i map()',
    "nsTests.join(', ')": 'elementene escapes med escHtmlValue() i map()',
    "kwSig.join(', ')": 'hardkodede strenger i koden',
}


class StatsEscapingSourceGuardTests(SimpleTestCase):
    """Statisk gjennomgang av interpolasjonene i HTML-byggerne."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Byggerne ligger i to filer etter at statistikk ble egen modul:
        # tabellene og tolkningen i statistikk.js, personellregistrene i
        # patients-admin.js. Begge setter markup med innerHTML, så
        # gjennomgangen må dekke begge — leste vi bare den ene, ville
        # halve vernet forsvunnet uten at noen test ble rød.
        cls.stats_src = read_js(STATISTIKK_JS) + '\n' + read_js(ADMIN_JS)
        cls.utils_src = read_js(PORTAL_UTILS_JS)

    def test_escape_hjelperne_finnes_i_utils(self):
        """Byggerne er avhengige av hjelperne i portal-utils.js.

        Hjelperne lå i patients-utils.js fram til statistikk ble egen modul.
        Statistikksiden laster ikke den fila, så escapingen måtte flytte med
        — ellers ville byggerne kalt noe som ikke fantes, og innsettingen
        skjedd uten escaping.
        """
        for helper in ('function escHtmlValue(', 'function trustedHtml(',
                       'function cellHtml('):
            self.assertIn(helper, self.utils_src,
                          f'{helper} mangler i portal-utils.js')

    def test_alle_interpolasjoner_er_escapet_eller_gjennomgatt(self):
        """Hver ${...} i byggerne må escapes eller stå på den gjennomgåtte lista.

        Dette er regresjonsvernet: legger noen til en ny tabell eller kolonne
        uten escaping, feiler testen med navnet på uttrykket.
        """
        uescapet = []
        for name in HTML_BUILDERS:
            body = extract_function(self.stats_src, name)
            for expr in re.findall(r'\$\{([^}]*)\}', body):
                expr = expr.strip()
                if expr.startswith(ESCAPING_CALLS):
                    continue
                if expr in REVIEWED_INTERPOLATIONS:
                    continue
                uescapet.append(f'{name}(): ${{{expr}}}')

        self.assertEqual(uescapet, [], (
            'Uescapede interpolasjoner i statistikk-byggerne:\n  '
            + '\n  '.join(uescapet)
            + '\n\nPakk verdien i escHtmlValue() (eller trustedHtml() hvis det '
              'er markup du har bygget selv), eller legg uttrykket i '
              'REVIEWED_INTERPOLATIONS i denne fila med en begrunnelse.'
        ))

    def test_testnavn_escapes_ved_konstruksjon(self):
        """sigTests/nsTests slipper join() uescapet fordi map() escaper.

        Fjernes escHtmlValue() fra map-kallene, forsvinner escapingen uten at
        interpolasjonstesten over merker det. Derfor sjekkes det eksplisitt.
        """
        body = extract_function(self.stats_src, 'mkInterpretation')
        self.assertIn('.map(t => escHtmlValue(t.test))', body,
                      'sigTests/nsTests må escapes der de bygges')
        self.assertEqual(body.count('.map(t => escHtmlValue(t.test))'), 2,
                         'Både sigTests og nsTests må escapes')

    def test_signifikans_markup_er_merket_som_klarert(self):
        """De bevisste <span>-ene i renderTester må gå via trustedHtml()."""
        body = extract_function(self.stats_src, 'renderTester')
        self.assertEqual(body.count('trustedHtml('), 2,
                         'Både khi-kvadrat- og Kruskal-Wallis-tabellen må '
                         'merke signifikans-markupen som klarert')

    def test_personellnavn_escapes(self):
        """Førstehjelper- og helsepersonellnavn er fritekst uten whitelist."""
        for name, felt in (('renderForstehjelperAdmin', 'b.name'),
                           ('renderHelsepersonellAdmin', 'h.name')):
            body = extract_function(self.stats_src, name)
            self.assertIn(f'escHtmlValue({felt})', body,
                          f'{felt} settes inn uescapet i {name}()')


@unittest.skipUnless(shutil.which('node'), 'node er ikke tilgjengelig')
class StatsEscapingBehaviourTests(SimpleTestCase):
    """Kjører byggerne i node og verifiserer akseptansekriteriet for N6."""

    # Funksjonene som trengs for å kjøre byggerne isolert, uten DOM.
    HARNESS_FUNCTIONS = (
        (PORTAL_UTILS_JS, ('escHtmlValue', 'trustedHtml', 'cellHtml', 'fmtMin')),
        (STATISTIKK_JS, ('mkStatsTable', 'mkCrosstab', 'mkObsTable',
                         'mkInterpretation')),
    )

    XSS = '<img src=x onerror=alert(1)>'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.harness = build_harness(cls.HARNESS_FUNCTIONS)

    def _run_js(self, snippet):
        """Kjør snippet med byggerne i scope. Returnerer stdout."""
        return run_node(self.harness, snippet)

    def test_escHtmlValue_beholder_tallet_null(self):
        """0 er en gyldig celleverdi og skal vises, ikke bli tom streng.

        escapeHtml()/_escHtml() returnerer '' for alt falsy. I tabellceller
        er det feil, og grunnen til at escHtmlValue() finnes.
        """
        self._run_js(
            'assert(escHtmlValue(0) === "0", "0 ble borte: " + escHtmlValue(0));\n'
            'assert(escHtmlValue(null) === "", "null skal bli tom streng");\n'
            'assert(escHtmlValue(undefined) === "", "undefined skal bli tom streng");\n'
            'assert(escHtmlValue("<b>") === "&lt;b&gt;", "escaping mangler");\n'
        )

    def test_krysstabell_viser_html_i_feltverdi_som_tekst(self):
        """Akseptansekriteriet: radnøkkel med HTML skal vises som tekst."""
        self._run_js(f'''
const ct = {{
  rows: [{self.XSS!r}],
  cols: ['Rød'],
  counts: {{ {self.XSS!r}: {{ 'Rød': 2 }} }},
}};
const html = mkCrosstab(ct);
assert(!html.includes('<img'), 'radnøkkelen ble satt inn som markup: ' + html);
assert(html.includes('&lt;img'), 'radnøkkelen er ikke escapet: ' + html);
assert(html.includes('onerror=alert(1)&gt;'), 'teksten skal fortsatt vises');
''')

    def test_krysstabell_escaper_kolonnenokkel(self):
        """Kolonnenøklene er også pasientdata (transport, utskrevet_til)."""
        self._run_js(f'''
const ct = {{
  rows: ['Brystsmerter'],
  cols: [{self.XSS!r}],
  counts: {{ 'Brystsmerter': {{ {self.XSS!r}: 1 }} }},
}};
const html = mkCrosstab(ct);
assert(!html.includes('<img'), 'kolonnenøkkelen ble satt inn som markup: ' + html);
assert(html.includes('&lt;img'), 'kolonnenøkkelen er ikke escapet');
''')

    def test_krysstabell_viser_nullceller(self):
        """Escapingen skal ikke gjøre 0-celler tomme."""
        out = self._run_js('''
const ct = {
  rows: ['Brystsmerter'],
  cols: ['Rød', 'Gul'],
  counts: { 'Brystsmerter': { 'Rød': 3, 'Gul': 0 } },
};
const html = mkCrosstab(ct);
assert(html.includes('heat-zero'), 'null-cellen mangler heat-zero');
assert(/>0</.test(html) || />0<br/.test(html), 'tallet 0 vises ikke: ' + html);
''')
        self.assertIn('OK', out)

    def test_statstabell_escaper_celler_og_overskrifter(self):
        """Både overskrifter og celleverdier skal escapes."""
        self._run_js(f'''
const html = mkStatsTable([{self.XSS!r}], [[{self.XSS!r}, 0]]);
assert(!html.includes('<img'), 'markup slapp gjennom: ' + html);
assert((html.match(/&lt;img/g) || []).length === 2,
       'både overskrift og celle skal escapes: ' + html);
assert(html.includes('>0<'), 'tallet 0 mangler i cellen: ' + html);
''')

    def test_statstabell_slipper_gjennom_klarert_markup(self):
        """trustedHtml() er utveien for formatering vi har bygget selv."""
        self._run_js('''
const html = mkStatsTable(
  ['Test', 'Signifikant'],
  [['Khi-kvadrat', trustedHtml('<span style="color:#22c55e;">&#10004; Ja</span>')]],
  { sigCol: 1 }
);
assert(html.includes('<span style="color:#22c55e;">'),
       'klarert markup ble escapet: ' + html);
assert(html.includes('sig-yes'),
       'sigCol-logikken fungerer ikke på klarerte celler: ' + html);
''')

    def test_statstabell_setter_sig_no_uten_hake(self):
        """sigCol-klassen leses av den ferdige cellen, ikke rådataen."""
        self._run_js('''
const html = mkStatsTable(
  ['Test', 'Signifikant'],
  [['Khi-kvadrat', trustedHtml('<span>&#10007; Nei</span>')]],
  { sigCol: 1 }
);
assert(html.includes('sig-no'), 'forventet sig-no: ' + html);
assert(!html.includes('sig-yes'), 'skal ikke være sig-yes: ' + html);
''')

    def test_obstabell_escaper_gruppenavn(self):
        """Gruppenavnet i obspost-tabellen er problemstilling."""
        self._run_js(f'''
const html = mkObsTable([
  {{ name: {self.XSS!r}, n: 5, med_obs: 0, pct: 0, avg: null }}
]);
assert(!html.includes('<img'), 'markup slapp gjennom: ' + html);
assert(html.includes('&lt;img'), 'gruppenavnet er ikke escapet');
assert(html.includes('>0<'), 'med_obs = 0 skal vises: ' + html);
''')

    def test_tolkning_escaper_testnavn(self):
        """mkInterpretation setter testnavn inn i en <span>."""
        self._run_js(f'''
const s = {{
  summary: {{ total: 3, utskrevet: 1, total_obs_count: 0 }},
  chi2_table: [{{ test: {self.XSS!r}, result: {{ sig: true }} }}],
}};
const html = mkInterpretation(s);
assert(!html.includes('<img'), 'testnavnet ble satt inn som markup: ' + html);
assert(html.includes('&lt;img'), 'testnavnet er ikke escapet: ' + html);
''')
