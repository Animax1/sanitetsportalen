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
    OPPDRAG_ENHET_JS, OPPDRAG_SENTRAL_JS, PORTAL_UTILS_JS, build_harness,
    extract_function, node_available, read_js, run_node,
)

# Funksjonene som bygger HTML av data fra API-et, per fil. Den som legger til
# en bygger, legger den til her — ellers skanner testen forbi den.
HTML_BUILDERS_PER_FIL = {
    OPPDRAG_SENTRAL_JS: (
        'renderEnheter',
        # Vaktlistas data, lånt inn (§6 i vaktlistenotatet). Navn og rolle er
        # fritekst fra et annet moduls register, og escapes her som alt annet.
        'mkBesetning',
        'renderOppdrag',
        'tidslinjeHtml',
        'renderLokasjonsadmin',
        'renderEnhetsadmin',
        'renderHistorikk',
    ),
    OPPDRAG_ENHET_JS: (
        'tidslinjeEnhetHtml',
        'renderAktivt',
        'renderVentende',
        'renderAvsluttet',
    ),
}

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
    'e.username': 'bygger ren tekst i `koblingTekst`, som escapes ved innsetting',
    # Havner i `textContent`, ikke i markup — ingen parsing å bryte ut av.
    'antallAv': 'tall, settes med textContent',
    # Fragmentene bygges to linjer over interpolasjonen, med escapet innhold.
    # De er hoistet ut av mal-strengen nettopp for at denne testen skal kunne
    # lese dem: en nøstet mal-streng inne i en ${...} er usynlig for regexen.
    'fritekstBlokk': 'markup bygget lokalt, fritekst escapet inni',
    'notatBlokk': 'markup bygget lokalt, notatene escapet inni',
    'knapp': 'markup bygget lokalt, id escapet inni',
    # Besetningspanelet (vaktliste fase 6). Alle tre er hoistet ut av
    # mal-strengen av samme grunn som `fritekstBlokk` over.
    'klikkbar': 'hardkodet CSS-klasse fra en ternær',
    'apner': 'markup bygget lokalt, enhets-id escapet inni',
    'besetning': 'markup bygget lokalt av mkBesetning(), som selv skannes her',
    'merke': 'hardkodet markup fra en ternær, ingen data i seg',
    'rolle': 'markup bygget lokalt, rollenavnet escapet inni',
    'rader': 'markup bygget lokalt i samme funksjon',
    'status': 'bygget lokalt av tall som escapes inni',
    'valg': 'options bygget lokalt, brukernavn escapet inni',
    'vaktKlasse': 'hardkodet CSS-klasse fra en ternær',
    'vaktHandling': 'hardkodet handlingsnavn fra en ternær',
    'vaktTekst': 'hardkodet knappetekst fra en ternær',
    'vaktKnapp': 'markup bygget lokalt, id escapet inni',
    'adminKnapp': 'markup bygget lokalt, id escapet inni',
    'radKlasse': 'hardkodet CSS-klasse fra en ternær',
    'koblingKlasse': 'hardkodet CSS-klasse fra en ternær',
    'valgt': 'hardkodet selected-attributt fra en ternær',
    # Enhetsskjermens byggere (oppdrag-enhet.js):
    'historikkKnapp': 'markup bygget lokalt, id escapet inni',
    'rettKnapp': 'markup bygget lokalt, meldings-id escapet inni',
    'nesteKnapp': 'markup bygget lokalt, navn og id escapet inni',
    'ledigKnapp': 'markup bygget lokalt, id escapet inni',
    'startKnapp': 'markup bygget lokalt, navn og id escapet inni',
    'tidslinjeEnhetHtml(o)': 'markup fra en bygger som selv skannes her',
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

    def test_byggerne_finnes(self):
        """Vern mot at testen blir tom fordi en funksjon er omdøpt."""
        for fil, byggere in HTML_BUILDERS_PER_FIL.items():
            src = read_js(fil)
            for navn in byggere:
                with self.subTest(fil=fil.name, navn=navn):
                    self.assertIn(f'function {navn}(', src)

    def test_sidene_laster_ikke_patients_utils(self):
        """`patients-utils.js` gjør arbeid på toppnivå og kaster her.

        Regelen står i CLAUDE.md. Den håndheves for pasientsiden og
        statistikksiden av `JsModulLastingTests`; denne dekker malene våre.
        """
        from pathlib import Path
        from django.conf import settings
        for malnavn in ('sentral.html', 'enhet.html'):
            with self.subTest(mal=malnavn):
                mal = (Path(settings.BASE_DIR) / 'templates' / 'oppdrag' / malnavn).read_text()
                self.assertNotIn('patients-utils.js', mal)
                self.assertIn('portal-utils.js', mal)

    def test_alle_interpolasjoner_er_escapet_eller_gjennomgatt(self):
        uescapet = []
        for fil, byggere in HTML_BUILDERS_PER_FIL.items():
            src = read_js(fil)
            for navn in byggere:
                body = _uten_kommentarer(extract_function(src, navn))
                for uttrykk in re.findall(r'\$\{([^}]*)\}', body):
                    uttrykk = uttrykk.strip()
                    if uttrykk.startswith(ESCAPING_CALLS):
                        continue
                    if uttrykk in REVIEWED_INTERPOLATIONS:
                        continue
                    uescapet.append(f'{fil.name} {navn}(): ${{{uttrykk}}}')

        self.assertEqual(uescapet, [], (
            'Uescapede interpolasjoner i oppdrag-byggerne:\n  '
            + '\n  '.join(uescapet)
            + '\n\nPakk verdien i escapeHtml() (eller trustedHtml() hvis det er '
              'markup du har bygget selv), eller legg uttrykket i '
              'REVIEWED_INTERPOLATIONS i denne fila med en begrunnelse.'
        ))


class OppdragEscapingOppforselTests(SimpleTestCase):
    """Kjør byggerne i node og se at markup i data kommer ut som tekst."""

    # `klokke` bor i portal-utils.js nå — begge oppdragssidene bruker den.
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml',
                           'klokke')),
        (OPPDRAG_SENTRAL_JS, ('renderOppdrag', 'renderEnheter', 'tidslinjeHtml',
                              'hastegradKlasse', 'mkBesetning',
                              'kanSeBesetning')),
    )

    #: Besetningspanelet leser to globaler som ellers settes ved sidelasting.
    #: Ingen av testene her har panelet åpent — de skal fange escaping i
    #: enhetskortet, og et lukket panel er den vanlige tilstanden.
    BESETNING_STUBB = ("globalThis.apenBesetning = null;\n"
                       "globalThis.besetninger = {};\n"
                       "globalThis.window = { KAN_SE_BESETNING: true };\n")

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
        ut = run_node(self.harness, self.BESETNING_STUBB + '''
            globalThis.enheter = [{
              id: 1, navn: '<b>56</b>', status: 'ledig', pa_vakt: true,
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
        ut = run_node(self.harness, self.BESETNING_STUBB + '''
            globalThis.enheter = [{
              id: 1, navn: 'E1', status: '" onload="alert(1)', pa_vakt: true,
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


class EnhetEscapingOppforselTests(SimpleTestCase):
    """Kjør enhetsskjermens byggere i node — samme mekanikk som over.

    Eget harness: `hastegradKlasse` finnes i begge JS-filene (bevisst — den er
    domene, ikke primitiv), så de to filene kan ikke lastes i samme harness.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml',
                           'klokke')),
        (OPPDRAG_ENHET_JS, ('renderAktivt', 'renderVentende', 'renderAvsluttet',
                            'tidslinjeEnhetHtml', 'hastegradKlasse')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_fritekst_paa_aktivt_kort_kommer_ut_som_tekst(self):
        """Kortet bilen stirrer på — med feltet en operatør skriver fritt i."""
        ut = run_node(self.harness, '''
            globalThis.mineOppdrag = [{
              id: 1, status: 'fremme', status_navn: 'Fremme',
              problemstilling: 'Pustevansker', hastegrad: 'Akutt',
              lokasjon_navn: 'Scene', opprettet: '2026-08-29T20:00:00Z',
              fritekst: '<img src=x onerror=alert(1)>',
              neste_overgang: 'avreist', neste_navn: 'Avreist',
              statusmeldinger: []
            }];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            renderAktivt();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)

    def test_neste_navn_i_knappen_escapes(self):
        """Knappeteksten kommer fra serverens payload — den skal også escapes."""
        ut = run_node(self.harness, '''
            globalThis.mineOppdrag = [{
              id: 1, status: 'venter', status_navn: 'Venter',
              problemstilling: 'Transport', hastegrad: 'Vanlig',
              lokasjon_navn: 'Scene', opprettet: '2026-08-29T20:00:00Z',
              fritekst: '', neste_overgang: 'rykker_ut',
              neste_navn: '<b>Rykker ut</b>', statusmeldinger: []
            }];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            renderVentende();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('<b>Rykker ut</b>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_statusnavn_i_tidslinjen_escapes(self):
        ut = run_node(self.harness, '''
            console.log(tidslinjeEnhetHtml({ statusmeldinger: [{
              id: 1, status: 'fremme', status_navn: '<script>x</script>',
              tidspunkt: '2026-08-29T20:00:00Z',
              forsinket: false, automatisk: false
            }]}));
        ''')
        self.assertNotIn('<script>x', ut)
