"""XSS-vern for vaktlistas JS.

Samme mekanikk som `oppdrag/tests_xss.py`: modulen eier sine egne flater, og
lista over byggere må oppdateres av den som legger til en ny.

Feltet som gjør dette nødvendig her er **ressursnavnet**. Det er fritekst satt
av admin («Mannskapsbil 1», «Lag Nord»), og det havner både i en fane, i en
overskrift og i en `title`. Mannskapsnavn og korpsnavn er også fritekst, og
alt tre settes med `innerHTML`.
"""
import re

from django.test import SimpleTestCase

from patients.js_test_utils import (
    PORTAL_UTILS_JS, VAKTLISTE_JS, VAKTLISTE_REGISTRE_JS, build_harness,
    extract_function, node_available, read_js, run_node,
)

HTML_BUILDERS = (
    'fyllVelger',
    'mkRolleRad',
    '_fyll',
    'tegnFaner',
    'mkRessurs',
    '_rolleValg',
    '_fyllValgFor',
    'mkOversikt',
    'mkGruppekurve',
    '_mkEnKurve',
    'mkIkkePlassert',
)

ESCAPING_CALLS = ('escHtmlValue(', 'cellHtml(', '_escHtml(', 'escapeHtml(')

REVIEWED_INTERPOLATIONS = {
    'aktiv': 'hardkodet CSS-klasse fra en ternær',
    'antall': 'markup bygget lokalt, tallet escapet inni',
    'korpsmerke': 'markup bygget lokalt, korpsnavnet escapet inni',
    'enhetsmerke': 'markup bygget lokalt, enhetsnavnet escapet inni',
    'rader': 'markup bygget lokalt av byggere som selv skannes her',
    "vp.rolle ? ' · ' + escapeHtml(vp.rolle) : ''":
        'ternær der den ene grenen er escapet og den andre er tom streng',
    "deler.join('')": 'markup bygget lokalt i samme funksjon',
    # Fase 3: knappene bygges lokalt og bare når tilgangen tillater dem.
    'knapper': 'markup bygget lokalt, id-ene escapet inni',
    'fjernPost': 'markup bygget lokalt, vaktpost-id escapet inni',
    # Regnearket (30. aug.): cellene bygges lokalt, med escapet innhold.
    'komp': 'markup bygget lokalt, kompetansenavnene escapet inni',
    'merknad': 'input bygget lokalt, verdien escapet i attributtet',
    'dager': 'escapet i begge grener av ternæren',
    'kropp': 'tabellrader bygget lokalt i samme funksjon',
    "tid('fra_tid')": 'input bygget lokalt av en hjelper som escaper',
    "tid('til_tid')": 'input bygget lokalt av en hjelper som escaper',
    '_rolleValg(vp, r, kanRore)':
        'nedtrekk fra en bygger som selv skannes her',
    'valg': 'options bygget lokalt, navn og id escapet inni',
    'valgt': 'hardkodet selected-attributt fra en ternær',
    'settKnapp': 'markup bygget lokalt, id escapet inni',
    'fjernKnapp': 'markup bygget lokalt, id escapet inni',
    'soyler': 'søyler bygget lokalt i samme funksjon',
    'skille': 'hardkodet CSS-klasse fra en ternær',
    'bunn': 'markup bygget lokalt, datoene escapet inni',
    "deler.join('')": 'markup bygget lokalt i samme funksjon',
    'rader': 'markup bygget lokalt av byggere som selv skannes her',
    # `_dag()` bygger «lør 3. okt» av tall fra et Date-objekt og to
    # hardkodede lister. Ingen brukerdata passerer gjennom den — en ugyldig
    # dato gir tom streng, ikke uescapet innhold.
    '_dag(vl.startet)': 'datostreng fra en Date, ingen brukerdata',
    '_dag(vp.fra_tid)': 'datostreng fra en Date, ingen brukerdata',
    '_dag(vp.til_tid)': 'datostreng fra en Date, ingen brukerdata',
    # Ledige plasser og den todelte kurven (30. aug.):
    'navnCelle': 'markup fra `_fyllValgFor`, som selv skannes her',
    'rest': 'markup bygget lokalt, tallet escapet inni',
    '_dag(punkter[0].tid)': 'datostreng fra en Date, ingen brukerdata',
    # Kolonner, grupper og roller (30. aug., andre runde):
    'merkelapper': 'markup bygget lokalt, hvert kompetansenavn escapet inni',
    'redigerPost': 'markup bygget lokalt, vaktpost-id escapet inni',
    'mkGruppekurve(r)': 'kurve fra en bygger som selv skannes her',
    '_tegnforklaring()': 'hardkodet markup uten data',
    'timeakse': 'celler bygget lokalt, klokkeslettene escapet inni',
    'kurve': 'kurve fra `_mkEnKurve`, som selv skannes her',
    "naar ? ' ' + escapeHtml(naar) : ''":
        'ternær der den ene grenen er escapet og den andre er tom streng',
    "vis ? escapeHtml(_kl(p.tid)) : ''":
        'ternær der den ene grenen er escapet og den andre er tom streng',
    'innhold': 'input eller escapet tekst, bygget lokalt i samme hjelper',
    'merke': 'markup bygget lokalt, ukedagen escapet inni',
    'kurver': 'kurver fra `_mkEnKurve`, som selv skannes her',
    # `tittel` er ren tekst som escapes én gang ved innsetting i `title=`.
    # Escapet vi her også, ville teksten blitt dobbeltescapet i tooltipen —
    # samme mønster som `meta` i oppdrag-sentral.js.
    '_dag(p.tid)': 'bygger ren tekst i `tittel`, som escapes ved innsetting',
    '_kl(p.tid)': 'bygger ren tekst i `tittel`, som escapes ved innsetting',
    'p.antall': 'tall, i samme rene tekst som escapes ved innsetting',
    'p.planlagt': 'tall, i samme rene tekst som escapes ved innsetting',
    'bruk': 'markup bygget lokalt, tallet escapet inni',
}


def _uten_kommentarer(kilde: str) -> str:
    return '\n'.join(
        linje for linje in kilde.splitlines() if not linje.lstrip().startswith('//'))


class VaktlisteEscapingKildeTests(SimpleTestCase):
    def test_byggerne_finnes(self):
        """Vern mot at testen blir tom fordi en funksjon er omdøpt."""
        src = read_js(VAKTLISTE_JS)
        for navn in HTML_BUILDERS:
            with self.subTest(navn=navn):
                self.assertIn(f'function {navn}(', src)

    def test_siden_laster_ikke_patients_utils(self):
        """`patients-utils.js` gjør arbeid på toppnivå og kaster her.

        Testen leser `<script>`-taggene, ikke rå maltekst: malen forklarer
        regelen i en `{% comment %}` og nevner derfor filnavnet. Et tekstsøk
        ville lest sin egen begrunnelse som et brudd.
        """
        from pathlib import Path
        from django.conf import settings
        mal = (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
               / 'index.html').read_text(encoding='utf-8')
        lastet = re.findall(r"<script\b[^>]*js/([A-Za-z0-9_.-]+\.js)", mal)
        self.assertNotIn('patients-utils.js', lastet)
        self.assertIn('portal-utils.js', lastet)
        self.assertIn('vaktliste.js', lastet)

    def test_alle_interpolasjoner_er_escapet_eller_gjennomgatt(self):
        src = read_js(VAKTLISTE_JS)
        uescapet = []
        for navn in HTML_BUILDERS:
            body = _uten_kommentarer(extract_function(src, navn))
            for uttrykk in re.findall(r'\$\{([^}]*)\}', body):
                uttrykk = uttrykk.strip()
                if uttrykk.startswith(ESCAPING_CALLS):
                    continue
                if uttrykk in REVIEWED_INTERPOLATIONS:
                    continue
                uescapet.append(f'{navn}(): ${{{uttrykk}}}')

        self.assertEqual(uescapet, [], (
            'Uescapede interpolasjoner i vaktliste.js:\n  '
            + '\n  '.join(uescapet)
            + '\n\nPakk verdien i escapeHtml() (eller trustedHtml() hvis det er '
              'markup du har bygget selv), eller legg uttrykket i '
              'REVIEWED_INTERPOLATIONS i denne fila med en begrunnelse.'
        ))


class VaktlisteEscapingOppforselTests(SimpleTestCase):
    """Kjør byggerne i node og se at markup i data kommer ut som tekst."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml',
                           '_escHtml', 'klokke')),
        (VAKTLISTE_JS, ('mkRessurs', '_rolleValg', 'rollerForGruppe',
                        '_fyllValgFor', '_varighet',
                        'mkRolleRad', 'mkOversikt', '_mkEnKurve',
                        'mkGruppekurve', '_tegnforklaring', '_timesteg',
                        '_toppunkt', '_posterPerGruppe', '_vaktensSpenn',
                        'mkIkkePlassert', 'tegnFaner', '_posterFor',
                        '_ikkePlassert', '_tidsspenn', '_vaktspenn',
                        '_bemanningPerTime', '_iso16', '_d', '_kl', '_dag',
                        '_sammeDag', '_nivaa', '_erAdmin', 'kanSkriveAlt',
                        'kanLede', 'kanBemanne')),
    )

    #: Byggerne spør om tilgang fra fase 3. Node har ingen `window`, så den
    #: stubbes — og med admin, slik at *alle* knappene bygges. Escaping-testene
    #: skal se mest mulig markup; hvem som får se hva er `tests_tilgang.py`
    #: sitt bord.
    VINDU = ("globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _liste(self, **overstyr):
        """JS-litteral for `aktivListe`, med felter testen vil overstyre."""
        import json
        grunn = {'vaktliste': {'id': 1, 'vakt_navn': 'Vakta',
                               'status_navn': 'Planlegging', 'i_drift': False},
                 'ressurser': [], 'vaktposter': [], 'mannskap': [],
                 'roller': [], 'grupper': [], 'korps': [], 'enheter': []}
        grunn.update(overstyr)
        return json.dumps(grunn)

    def test_ressursnavn_med_markup_kommer_ut_som_tekst(self):
        """Fritekstfeltet i modulen — admin skriver hva som helst her."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivListe = {self._liste()};
            console.log(mkRessurs({{
              id: 1, navn: '<img src=x onerror=alert(1)>', ikon: 'people',
              gruppe_navn: 'Lag', korps_navn: '', enhet_navn: ''
            }}));
        ''')
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)

    def test_ikonet_kommer_fra_data_og_escapes(self):
        """Ikonet står i et class-attributt — et bruddpunkt for attributt-XSS."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivListe = {self._liste()};
            console.log(mkRessurs({{
              id: 1, navn: 'Lag 1', ikon: '" onload="alert(1)',
              gruppe_navn: 'Lag', korps_navn: '', enhet_navn: ''
            }}));
        ''')
        self.assertNotIn('onload="alert(1)"', ut)

    def test_mannskapsnavn_i_oversikten_escapes(self):
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivListe = {self._liste(
                ressurser=[{'id': 1, 'navn': 'Lag 1'}],
                vaktposter=[{
                    'id': 1, 'ressurs_id': 1, 'mannskap_id': 1,
                    'navn': '<script>x</script>', 'korps_navn': 'HGSD',
                    'korps_kort': 'HGSD', 'rolle': '',
                    'fra_tid': '2026-10-03T08:00:00Z',
                    'til_tid': '2026-10-03T16:00:00Z'}])};
            console.log(mkOversikt());
        ''')
        self.assertNotIn('<script>x', ut)
        self.assertIn('&lt;script&gt;', ut)

    def test_korpsnavn_i_gruppeoverskriften_escapes(self):
        """Overskriften bygges av en nøkkel i en gruppering — verdien kommer
        fortsatt fra basen, og går gjennom samme escaping."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivListe = {self._liste(
                ressurser=[{'id': 1, 'navn': 'Lag 1'}],
                vaktposter=[{
                    'id': 1, 'ressurs_id': 1, 'mannskap_id': 1,
                    'navn': 'Kari', 'korps_navn': '<b>HGSD</b>',
                    'korps_kort': 'HGSD', 'rolle': '',
                    'fra_tid': '2026-10-03T08:00:00Z',
                    'til_tid': '2026-10-03T16:00:00Z'}])};
            console.log(mkOversikt());
        ''')
        self.assertNotIn('<b>HGSD</b>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_fanenavn_escapes(self):
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivFane = 'oversikt';
            globalThis.OVERSIKT = 'oversikt';
            globalThis.IKKE_PLASSERT = 'ikke-plassert';
            globalThis.aktivListe = {self._liste(
                ressurser=[{'id': 1, 'navn': '<b>Lag 1</b>', 'ikon': 'people'}])};
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => el }};
            tegnFaner();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('<b>Lag 1</b>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_ikke_plassert_escapes(self):
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivListe = {self._liste(
                mannskap=[{'id': 1, 'navn': '<i>Kari</i>',
                           'korps_navn': '<i>HGSD</i>'}])};
            console.log(mkIkkePlassert());
        ''')
        self.assertNotIn('<i>Kari</i>', ut)
        self.assertIn('&lt;i&gt;', ut)


class VaktlisteLogikkTests(SimpleTestCase):
    """Utvalgsfunksjonene, kjørt i node — de avgjør hva fanene teller."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
        (VAKTLISTE_JS, ('_posterFor', '_ikkePlassert')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_ikke_plassert_er_de_som_ikke_staar_noe_sted(self):
        """Fanen finnes for at ingen skal bli glemt: en person som er meldt på
        og ikke satt opp er usynlig ellers."""
        run_node(self.harness, '''
            globalThis.aktivListe = {
              mannskap: [{id: 1, navn: 'Kari'}, {id: 2, navn: 'Ola'}],
              vaktposter: [{id: 9, ressurs_id: 1, mannskap_id: 1}]
            };
            assert(_ikkePlassert().map(m => m.navn).join(',') === 'Ola',
                   'kun Ola staar uplassert');
        ''')

    def test_poster_for_filtrerer_paa_ressurs(self):
        """Fanetallene hviler på dette utvalget — treffer det feil ressurs,
        viser fanen et antall som ikke stemmer med panelet under."""
        run_node(self.harness, '''
            globalThis.aktivListe = { vaktposter: [
              {id: 1, ressurs_id: 1}, {id: 2, ressurs_id: 2},
              {id: 3, ressurs_id: 1}
            ]};
            assert(_posterFor(1).map(v => v.id).join(',') === '1,3',
                   'kun ressurs 1 sine poster');
            assert(_posterFor(3).length === 0, 'ukjent ressurs gir tom liste');
        ''')


# ── Registersiden ────────────────────────────────────────────────────────────
#
# Egen bygger-liste og eget harness: `_visFeil`, `_lukkModal` og vennene deres
# finnes i begge filene (bevisst — de er sidespesifikke), så de to kan ikke
# lastes i samme harness.

REGISTER_BUILDERS = ('mkMannskap', 'mkVerdier', '_kolonneHode')

REGISTER_REVIEWED = {
    'inaktiv': 'hardkodet CSS-klasse fra en ternær',
    'inaktivMerke': 'markup bygget lokalt, ingen data i seg',
    'merker': 'markup bygget lokalt, kompetansenavnene escapet inni',
    'konto': 'markup bygget lokalt, brukernavnet escapet inni',
    'tlf': 'markup bygget lokalt, telefonnummeret escapet inni',
    'kort': 'markup bygget lokalt, kortnavnet escapet inni',
    'bruk': 'markup bygget lokalt, tallet escapet inni',
    'rader': 'markup bygget lokalt i samme funksjon',
    'innhold': 'markup bygget lokalt i samme funksjon',
    "deler.join('')": 'markup bygget lokalt i samme funksjon',
    # Fase 3: knappene bygges lokalt og bare når tilgangen tillater dem.
    'knapper': 'markup bygget lokalt, mannskaps-id escapet inni',
    'verdiKnapper': 'markup bygget lokalt, rad-id escapet inni',
    'nyKnapp': 'markup bygget lokalt, etiketten escapet inni',
    # Mannskapstabellen. `inaktivMerke`, `merker` og `konto` sto allerede over
    # med samme begrunnelse — tabellen gjenbruker dem.
    'stige': 'markup bygget lokalt, «bygger på»-navnet escapet inni',
    'kropp': 'tabellrader bygget lokalt i samme funksjon',
    # Treff-telleren settes med textContent, ikke innerHTML — ingen parsing
    # å bryte ut av, og tallene kommer uansett fra `.length`.
    'rader.length': 'tall, settes med textContent',
    'data.mannskap.length': 'tall, settes med textContent',
    "_kolonneHode('navn', 'Navn')": 'bygger med escapet innhold, se funksjonen',
    "_kolonneHode('korps', 'Korps')": 'bygger med escapet innhold, se funksjonen',
    "_kolonneHode('telefon', 'Telefon')": 'bygger med escapet innhold, se funksjonen',
}


class RegistersidenEscapingKildeTests(SimpleTestCase):
    def test_byggerne_finnes(self):
        src = read_js(VAKTLISTE_REGISTRE_JS)
        for navn in REGISTER_BUILDERS:
            with self.subTest(navn=navn):
                self.assertIn(f'function {navn}(', src)

    def test_siden_laster_ikke_patients_utils(self):
        from pathlib import Path
        from django.conf import settings
        mal = (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
               / 'registre.html').read_text(encoding='utf-8')
        lastet = re.findall(r"<script\b[^>]*js/([A-Za-z0-9_.-]+\.js)", mal)
        self.assertNotIn('patients-utils.js', lastet)
        self.assertIn('portal-utils.js', lastet)
        self.assertIn('vaktliste-registre.js', lastet)

    def test_alle_interpolasjoner_er_escapet_eller_gjennomgatt(self):
        src = read_js(VAKTLISTE_REGISTRE_JS)
        uescapet = []
        for navn in REGISTER_BUILDERS:
            body = _uten_kommentarer(extract_function(src, navn))
            for uttrykk in re.findall(r'\$\{([^}]*)\}', body):
                uttrykk = uttrykk.strip()
                if uttrykk.startswith(ESCAPING_CALLS):
                    continue
                if uttrykk in REGISTER_REVIEWED:
                    continue
                uescapet.append(f'{navn}(): ${{{uttrykk}}}')

        self.assertEqual(uescapet, [], (
            'Uescapede interpolasjoner i vaktliste-registre.js:\n  '
            + '\n  '.join(uescapet)))


class RegistersidenEscapingOppforselTests(SimpleTestCase):
    """Registersiden er den eneste flaten der notatfeltet skrives.

    Feltet er unntatt verdilogging i audit nettopp fordi det er helt fritt —
    og et helt fritt felt er også det farligste å sette inn i DOM-en.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml')),
        (VAKTLISTE_REGISTRE_JS, ('mkMannskap', 'mkVerdier', '_kolonneHode',
                                 '_passerSok', '_sorterMannskap', '_nivaa',
                                 'kanSkriveAlt', 'kanRedigerePerson')),
    )

    #: Tabellen skriver treff-telleren i DOM-en og leser sorteringstilstanden,
    #: så begge stubbes. Node har verken `window` eller `document`.
    VINDU = ("globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.document = { getElementById: () => null };\n"
             "globalThis.sok = ''; globalThis.sortKol = 'korps';\n"
             "globalThis.sortStigende = true;\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_personnavn_og_kompetanse_escapes(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.data = { mannskap: [{
              id: 1, navn: '<img src=x onerror=alert(1)>',
              korps_navn: 'HGSD', korps_kort: 'HGSD',
              kompetanser: [{id: 1, navn: '<b>Sykepleier</b>'}],
              telefon: '', brukernavn: '', er_aktiv: true, i_bruk: 0
            }]};
            console.log(mkMannskap());
        """)
        self.assertNotIn('<img src=x', ut)
        self.assertNotIn('<b>Sykepleier</b>', ut)
        self.assertIn('&lt;img', ut)

    def test_brukernavn_og_telefon_escapes(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.data = { mannskap: [{
              id: 1, navn: 'Kari', korps_navn: 'HGSD', korps_kort: 'HGSD',
              kompetanser: [], telefon: '<i>90</i>',
              brukernavn: '<script>x</script>', er_aktiv: true, i_bruk: 0
            }]};
            console.log(mkMannskap());
        """)
        self.assertNotIn('<script>x', ut)
        self.assertNotIn('<i>90</i>', ut)

    def test_verdinavn_og_kortnavn_escapes(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.aktivRegisterFane = 'korps';
            globalThis.REGISTRE = { korps: {sti:'korps', ental:'korps',
                                            tittel:'Korps', kortnavn:true} };
            globalThis.data = { korps: [{
              id: 1, navn: '<b>Haugesund</b>', kortnavn: '<i>HGSD</i>',
              er_aktiv: true, i_bruk: 0
            }]};
            console.log(mkVerdier('korps'));
        """)
        self.assertNotIn('<b>Haugesund</b>', ut)
        self.assertNotIn('<i>HGSD</i>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_inaktiv_rad_merkes(self):
        """Pensjonering er den normale veien ut — raden skal fortsatt vises,
        men tydelig nedtonet. Kontrollen ligger i JS-assertene."""
        run_node(self.harness, self.VINDU + """
            globalThis.data = { mannskap: [{
              id: 1, navn: 'Kari', korps_navn: 'HGSD', korps_kort: 'HGSD',
              kompetanser: [], telefon: '', brukernavn: '',
              er_aktiv: false, i_bruk: 0
            }]};
            const ut = mkMannskap();
            assert(ut.includes('vl-inaktiv'), 'inaktiv rad skal merkes');
            assert(ut.includes('Kari'), 'og fortsatt vises');
        """)


class MannskapstabellensLayoutTests(SimpleTestCase):
    """Kolonnene skal ikke kunne flyte inn i hverandre igjen.

    Feilen André meldte: en person med mange kompetanser blåste opp
    kompetansekolonnen og skjøv telefon og konto ut av linje med radene over.
    Årsaken var `table-layout: auto`, der `max-width` på en `td` bare er et
    forslag — nettleseren sizer kolonnene etter innhold.

    De to tingene som holder det i sjakk testes her fordi de er lette å
    fjerne i god tro: `table-layout: fixed` ser overflødig ut ved siden av
    `<colgroup>`, og `<colgroup>` ser overflødig ut ved siden av `fixed`.
    Begge trengs — den første slår av innholdsbasert sizing, den andre sier
    hva andelene skal være.
    """

    def _css(self):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'static' / 'css'
                / 'vaktliste.css').read_text(encoding='utf-8')

    def test_tabellen_har_fast_kolonnelayout(self):
        css = self._css()
        blokk = css[css.index('.vlr-tabell {'):css.index('.vlr-tabell th')]
        self.assertIn('table-layout: fixed', blokk)
        self.assertIn('min-width:', blokk,
                      'uten min-width klemmes kolonnene i stedet for å rulle')

    def test_rammen_ruller_framfor_sida(self):
        css = self._css()
        blokk = css[css.index('.vlr-tabellramme {'):css.index('.vlr-tabell {')]
        self.assertIn('overflow-x: auto', blokk)

    def test_byggeren_setter_kolonnebredder(self):
        """`fixed` uten `<colgroup>` gir like brede kolonner, som er feil
        fordelig: kompetanse trenger mest, korps minst."""
        src = read_js(VAKTLISTE_REGISTRE_JS)
        kropp = extract_function(src, 'mkMannskap')
        self.assertIn('<colgroup>', kropp)
        andeler = re.findall(r'width:\s*(\d+)%', kropp)
        self.assertEqual(len(andeler), 6, 'én bredde per kolonne')
        self.assertEqual(sum(int(a) for a in andeler), 100,
                         f'andelene skal summere til 100, fikk {andeler}')

    def test_kompetansecella_bryter_framfor_aa_flyte_ut(self):
        css = self._css()
        blokk = css[css.index('.vlr-komp {'):css.index('.vlr-handling {')]
        self.assertIn('flex-wrap: wrap', blokk)


class TidsvisningTests(SimpleTestCase):
    """Dato og dag, ikke bare klokkeslett.

    Feilen André meldte: et skift fra lørdag 20:00 til søndag 04:00 sto som
    «20:00–04:00», uten at noe sa at det krysset midnatt. Arrangementer varer
    flere dager, og da er klokkeslettet alene tvetydig.
    """

    HARNESS = (
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_sammeDag', '_tidsspenn',
                        '_vaktspenn', '_iso16', '_bemanningPerTime',
                        '_vaktensSpenn', '_varighet')),
    )
    VINDU = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, kode):
        return run_node(self.harness, self.VINDU + kode)

    def test_endagsskift_nevner_dagen_en_gang(self):
        self._kjor("""
            const ut = _tidsspenn({fra_tid: '2026-10-03T08:00:00',
                                   til_tid: '2026-10-03T16:00:00'});
            assert(ut === 'lør 3. okt 08:00–16:00', 'fikk: ' + ut);
        """)

    def test_skift_over_midnatt_nevner_begge_dagene(self):
        """Selve feilen: «20:00–04:00» sa ikke at det krysset et døgnskille."""
        self._kjor("""
            const ut = _tidsspenn({fra_tid: '2026-10-03T20:00:00',
                                   til_tid: '2026-10-04T04:00:00'});
            assert(ut.includes('lør 3. okt'), 'startdagen mangler: ' + ut);
            assert(ut.includes('søn 4. okt'), 'sluttdagen mangler: ' + ut);
        """)

    def test_vaktspennet_utledes_av_skiftene(self):
        """Spennet er ikke et felt noen fyller ut — da holder det seg riktig
        av seg selv når lista endrer seg."""
        self._kjor("""
            globalThis.aktivListe = { vaktposter: [
              {fra_tid: '2026-10-03T12:00:00', til_tid: '2026-10-03T20:00:00'},
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-04T02:00:00'},
            ]};
            const ut = _vaktspenn();
            assert(ut.includes('lør 3. okt 08:00'), 'tidligste start: ' + ut);
            assert(ut.includes('søn 4. okt 02:00'), 'seneste slutt: ' + ut);
        """)

    def test_tomt_spenn_gir_tom_streng(self):
        self._kjor("""
            globalThis.aktivListe = { vaktposter: [] };
            assert(_vaktspenn() === '', 'ingen skift gir ingen tekst');
        """)

    def test_ugyldig_dato_gir_tom_streng_ikke_krasj(self):
        self._kjor("""
            assert(_dag('ikke en dato') === '', 'skal svare tomt');
            assert(_kl(null) === '', 'skal svare tomt');
        """)

    def test_datetime_local_bruker_lokal_tid_ikke_utc(self):
        """`toISOString()` ville gitt UTC og flyttet skiftet to timer om
        sommeren — feltet ville vist noe annet enn det som er lagret."""
        self._kjor("""
            const ut = _iso16('2026-07-03T08:30:00');
            assert(ut === '2026-07-03T08:30', 'fikk: ' + ut);
        """)


class BemanningskurveTests(SimpleTestCase):
    """Kurven svarer på ett spørsmål: hvor er hullene."""

    HARNESS = (
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_bemanningPerTime',
                        '_vaktensSpenn')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_teller_overlappende_skift_per_time(self):
        run_node(self.harness, """
            globalThis.aktivListe = { vaktposter: [
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
              {fra_tid: '2026-10-03T10:00:00', til_tid: '2026-10-03T14:00:00'},
            ]};
            const p = _bemanningPerTime();
            assert(p.length === 6, 'seks timer, fikk ' + p.length);
            assert(p[0].antall === 1, 'kl 08: en');
            assert(p[2].antall === 2, 'kl 10: to overlapper');
            assert(p[4].antall === 1, 'kl 12: en igjen');
        """)

    def test_hull_i_bemanningen_telles_som_null(self):
        """Hullet er det planleggeren leter etter — det må synes."""
        run_node(self.harness, """
            globalThis.aktivListe = { vaktposter: [
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00'},
              {fra_tid: '2026-10-03T12:00:00', til_tid: '2026-10-03T14:00:00'},
            ]};
            const p = _bemanningPerTime();
            assert(p[2].antall === 0, 'kl 10 skal vaere tom');
            assert(p[3].antall === 0, 'kl 11 skal vaere tom');
            assert(p[4].antall === 1, 'kl 12 er bemannet igjen');
        """)

    def test_ingen_skift_gir_ingen_kurve(self):
        run_node(self.harness, """
            globalThis.aktivListe = { vaktposter: [] };
            assert(_bemanningPerTime().length === 0, 'tom liste');
        """)

    def test_urimelig_spenn_tegnes_ikke(self):
        """En feiltastet årstall ville ellers laget hundretusen søyler."""
        run_node(self.harness, """
            globalThis.aktivListe = { vaktposter: [
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2099-10-03T08:00:00'},
            ]};
            assert(_bemanningPerTime().length === 0, 'skal gi opp, ikke henge');
        """)


class KurveOverHeleVaktaTests(SimpleTestCase):
    """Kurven skal dekke vaktas lengde, ikke bare skiftene.

    Meldt av André: leste den bare skiftene, ville hullet i begynnelsen vært
    usynlig nettopp fordi ingen er satt opp der ennå — og det er det hullet
    planleggeren leter etter.
    """

    HARNESS = (
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_bemanningPerTime',
                        '_vaktensSpenn')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_spennet_kommer_fra_vakta_ikke_fra_skiftene(self):
        run_node(self.harness, """
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T20:00:00'},
              vaktposter: [
                {fra_tid: '2026-10-03T12:00:00', til_tid: '2026-10-03T14:00:00',
                 ledig: false},
              ]};
            const p = _bemanningPerTime();
            assert(p.length === 12, 'tolv timer fra vakta, fikk ' + p.length);
            assert(p[0].antall === 0, 'hullet kl 08 skal synes');
            assert(p[4].antall === 1, 'kl 12 er bemannet');
            assert(p[11].antall === 0, 'hullet paa slutten skal ogsaa synes');
        """)

    def test_ledige_plasser_telles_som_behov_ikke_bemanning(self):
        """Avstanden mellom de to tallene er det som gjenstår å bemanne."""
        run_node(self.harness, """
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T10:00:00'},
              vaktposter: [
                {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00',
                 ledig: false},
                {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00',
                 ledig: true},
              ]};
            const p = _bemanningPerTime();
            assert(p[0].antall === 1, 'en person, fikk ' + p[0].antall);
            assert(p[0].planlagt === 2, 'to plasser, fikk ' + p[0].planlagt);
        """)

    def test_uten_sluttid_faller_den_tilbake_paa_skiftene(self):
        """Bedre en kurve som dekker for lite enn ingen kurve mens vakta
        ennå ikke har fått en slutt."""
        run_node(self.harness, """
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00', planlagt_slutt: null},
              vaktposter: [
                {fra_tid: '2026-10-03T12:00:00', til_tid: '2026-10-03T14:00:00',
                 ledig: false},
              ]};
            const p = _bemanningPerTime();
            assert(p.length === 2, 'faller tilbake paa skiftene, fikk ' + p.length);
        """)

    def test_ugyldig_spenn_faller_tilbake_ogsaa(self):
        run_node(self.harness, """
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T20:00:00',
                          planlagt_slutt: '2026-10-03T08:00:00'},
              vaktposter: [
                {fra_tid: '2026-10-03T12:00:00', til_tid: '2026-10-03T14:00:00',
                 ledig: false},
              ]};
            assert(_bemanningPerTime().length === 2, 'slutt foer start ignoreres');
        """)

    def test_verken_spenn_eller_skift_gir_ingen_kurve(self):
        run_node(self.harness, """
            globalThis.aktivListe = { vaktliste: {}, vaktposter: [] };
            assert(_bemanningPerTime().length === 0, 'ingenting aa tegne');
        """)


class RessurstabellensBreddeTests(SimpleTestCase):
    """Tidsfeltene må få plass i kolonnene sine.

    Meldt av André: kolonnene i ressursoversikten overlappet. Årsaken var at
    et `datetime-local` har en minstebredde fra nettleseren (~190 px) som
    `width: 100%` ikke overstyrer — med for trange kolonner flyter feltet ut
    over nabocella.

    Testen regner ut hva kolonnene faktisk blir ved `min-width`, framfor å
    slå fast at tallene er akkurat 82rem og 15 %. Da er det *regelen* som er
    låst, ikke verdiene: justerer noen andelene, holder testen så lenge
    tidsfeltene fortsatt får plass.
    """

    #: Chrome trenger omtrent dette til et `datetime-local` med innrykk.
    MIN_TIDSFELT_PX = 185
    #: Overskriftene på kolonnene som inneholder et tidsfelt. Slås opp på
    #: navn, ikke på indeks: kolonnerekkefølgen er endret to ganger på to
    #: dager, og en test som teller kolonner måler da rekkefølgen framfor
    #: regelen — og går grønn på feil kolonne.
    TIDSKOLONNER = ('Fra', 'Til')

    def _min_width_rem(self):
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css'
               / 'vaktliste.css').read_text(encoding='utf-8')
        blokk = css[css.index('.vl-tabell {'):css.index('.vl-tabell th')]
        m = re.search(r'min-width:\s*([\d.]+)rem', blokk)
        self.assertIsNotNone(m, '.vl-tabell mangler min-width')
        return float(m.group(1))

    def _andeler(self):
        src = read_js(VAKTLISTE_JS)
        kropp = extract_function(src, 'mkRessurs')
        return [int(a) for a in re.findall(r'width:\s*(\d+)%', kropp)]

    def _overskrifter(self):
        src = read_js(VAKTLISTE_JS)
        kropp = extract_function(src, 'mkRessurs')
        blokk = kropp[kropp.index('<thead>'):kropp.index('</thead>')]
        return re.findall(r'<th>(.*?)</th>', blokk)

    def test_andelene_summerer_til_hundre(self):
        andeler = self._andeler()
        self.assertEqual(len(andeler), len(self._overskrifter()),
                         'én andel per kolonne')
        self.assertEqual(sum(andeler), 100, f'fikk {andeler}')

    def test_tidskolonnene_rommer_et_datetime_felt(self):
        piksler = self._min_width_rem() * 16
        andeler = self._andeler()
        overskrifter = self._overskrifter()
        for navn in self.TIDSKOLONNER:
            with self.subTest(kolonne=navn):
                self.assertIn(navn, overskrifter)
                bredde = piksler * andeler[overskrifter.index(navn)] / 100
                self.assertGreaterEqual(
                    round(bredde), self.MIN_TIDSFELT_PX,
                    f'kolonnen «{navn}» blir {bredde:.0f} px ved min-width — '
                    f'for smal til et datetime-felt, og feltet flyter da ut '
                    f'over nabocella.')

    def test_feltene_kan_ikke_vokse_forbi_cella(self):
        """Beltet ved siden av bukseselene: selv med feil andeler skal et
        felt aldri stikke ut av cella si."""
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css'
               / 'vaktliste.css').read_text(encoding='utf-8')
        blokk = css[css.index('.vl-celle {'):css.index('.vl-celle:hover')]
        for regel in ('box-sizing: border-box', 'min-width: 0', 'max-width: 100%'):
            with self.subTest(regel=regel):
                self.assertIn(regel, blokk)


class TabellcellersLayoutTests(SimpleTestCase):
    """En `<td>` må forbli en tabellcelle.

    **Buggen André meldte:** «inne i ressursvinduet flytter kompetansekolonnen
    seg slik at de ikke er likt med resten». Årsaken var `display: flex`
    direkte på `.vl-kompcelle`, som er en `<td>`: da slutter cella å være en
    `table-cell`, faller ut av kolonnesporet, og alt etter den forskyves i
    forhold til overskriftene. `table-layout: fixed` hjelper ikke — regelen
    gjelder cellene som *er* i tabellen.

    Testen leser hvilke klasser som faktisk står på `<td>`-ene i tabellen og
    krever at ingen av dem får en `display` som bryter tabellen. Da er
    *regelen* låst og ikke navnet på én klasse: neste cellemerkelapp fanges
    av samme test.
    """

    #: Verdier som tar elementet ut av tabellens boksmodell.
    FARLIGE = ('flex', 'grid', 'inline-flex', 'inline-grid', 'block')

    def _celleklasser(self):
        """Klassene som står på `<td>` i ressurstabellen."""
        kropp = extract_function(read_js(VAKTLISTE_JS), 'mkRessurs')
        klasser = set()
        for treff in re.findall(r'<td class="([^"$]*)"', kropp):
            klasser.update(treff.split())
        return klasser

    def _css(self):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'static' / 'css'
                / 'vaktliste.css').read_text(encoding='utf-8')

    def test_celleklassene_finnes_i_stilarket(self):
        """Grunnlaget for testen under: finner den ingen klasser, måler den
        ingenting og går grønn på tom luft."""
        self.assertTrue(self._celleklasser(), 'fant ingen td-klasser')

    def test_ingen_celleklasse_bryter_tabellen(self):
        css = self._css()
        for klasse in sorted(self._celleklasser()):
            # Regelblokka der klassen står *alene* som selektor — altså
            # regelen som treffer selve `<td>`-en, ikke `.klasse > .noe`.
            for m in re.finditer(
                    r'(?m)^\.' + re.escape(klasse) + r'\s*\{([^}]*)\}', css):
                display = re.search(r'display:\s*([\w-]+)', m.group(1))
                if not display:
                    continue
                with self.subTest(klasse=klasse):
                    self.assertNotIn(
                        display.group(1), self.FARLIGE,
                        f'.{klasse} står på en <td> og setter '
                        f'display: {display.group(1)} — cella slutter da å '
                        f'være en table-cell, og kolonnene etter den '
                        f'forskyves i forhold til overskriftene. Legg '
                        f'layouten på et element inne i cella i stedet.')


class RollenedtrekketTests(SimpleTestCase):
    """Nedtrekket tilbyr aktive roller — og den raden allerede har.

    Alle rollene sendes til siden fordi manageren skal vise dem. Ble de tilbudt
    i nedtrekket også, kunne en utgått rolle deles ut på nytt; ble den *bare*
    filtrert bort, ville raden som allerede har den vist tomt.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_rolleValg', 'rollerForGruppe')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    #: Gruppe 1 er «Ambulanse», gruppe 2 «Samleplass» i disse testene.
    ROLLER = """
        globalThis.aktivListe = { roller: [
          {id: 1, navn: 'Lagleder', er_aktiv: true, gruppe_id: 1},
          {id: 2, navn: 'Utgaatt', er_aktiv: false, gruppe_id: 1},
          {id: 3, navn: 'Innsatsleder', er_aktiv: true, gruppe_id: 2},
        ]};
        globalThis.AMBULANSE = {id: 5, gruppe_id: 1};
        globalThis.SAMLEPLASS = {id: 6, gruppe_id: 2};
    """

    def test_inaktiv_rolle_tilbys_ikke(self):
        ut = run_node(self.harness, self.ROLLER + """
            console.log(_rolleValg({id: 9, rolle_id: null}, AMBULANSE, true));
        """)
        self.assertIn('Lagleder', ut)
        self.assertNotIn('Utgaatt', ut)

    def test_en_annen_gruppes_rolle_tilbys_ikke(self):
        """«Sjåfør» hører hjemme på ambulansen, ikke på samleplassen. Uten
        dette leddet er gruppa bare en etikett, og nedtrekket like langt som
        et globalt register."""
        ut = run_node(self.harness, self.ROLLER + """
            console.log(_rolleValg({id: 9, rolle_id: null}, AMBULANSE, true));
        """)
        self.assertNotIn('Innsatsleder', ut)

    def test_gruppa_far_sine_egne(self):
        ut = run_node(self.harness, self.ROLLER + """
            console.log(_rolleValg({id: 9, rolle_id: null}, SAMLEPLASS, true));
        """)
        self.assertIn('Innsatsleder', ut)
        self.assertNotIn('Lagleder', ut)

    def test_raden_beholder_rollen_den_alt_har(self):
        """Ellers ville et skift med en utgått rolle sett ut som om rollen
        var fjernet, og neste lagring hadde fjernet den på ordentlig."""
        ut = run_node(self.harness, self.ROLLER + """
            console.log(_rolleValg({id: 9, rolle_id: 2}, AMBULANSE, true));
        """)
        self.assertIn('Utgaatt', ut)
        self.assertIn('selected', ut)

    def test_raden_beholder_rollen_selv_fra_en_annen_gruppe(self):
        """Flyttes en ressurs til en annen gruppe, står skiftene igjen med
        roller fra den gamle. De skal fortsatt vises — ellers byttes de
        stilltiende bort ved neste tegning."""
        ut = run_node(self.harness, self.ROLLER + """
            console.log(_rolleValg({id: 9, rolle_id: 3}, AMBULANSE, true));
        """)
        self.assertIn('Innsatsleder', ut)
        self.assertIn('selected', ut)

    def test_uten_skrivetilgang_vises_rollen_som_tekst(self):
        ut = run_node(self.harness, self.ROLLER + """
            console.log(_rolleValg({id: 9, rolle_id: 1, rolle: 'Lagleder'},
                                   AMBULANSE, false));
        """)
        self.assertNotIn('<select', ut)
        self.assertIn('Lagleder', ut)


class CelleklikkTests(SimpleTestCase):
    """Et element som melder sin egen hendelse skal ikke også fyre på klikk.

    **Buggen André meldte:** «trykker jeg på ledig plass får jeg en kort popup
    som forsvinner». Nedtrekket i navnekolonnen er `<select data-action=
    "endreVaktpost" data-hendelse="change">`, og klikkdelegeringen i
    `portal-utils.js` traff det også. Klikket som åpnet lista kalte altså
    `endreVaktpost(id)` uten felt og verdi, sendte en tom PUT, og tegnet
    panelet på nytt — så den åpne lista ble revet bort i det øyeblikket den
    kom.

    Regelen ligger i `klikkSkalKjore()` og ikke som en anonym `if` inne i
    lytteren, nettopp for at den skal kunne kjøres her.
    """

    HARNESS = ((PORTAL_UTILS_JS, ('klikkSkalKjore',)),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_element_med_egen_hendelse_hopper_over_klikk(self):
        run_node(self.harness, """
            const cella = { dataset: { action: 'endreVaktpost',
                                       hendelse: 'change', felt: 'rolle_id' } };
            assert(klikkSkalKjore(cella) === false,
                   'nedtrekket melder change og skal ikke fyre paa klikk');
        """)

    def test_vanlig_knapp_fyrer_som_for(self):
        """Regelen må ikke slå av delegeringen for alle andre — den er
        hele mekanismen bak `data-action` i portalen."""
        run_node(self.harness, """
            const knapp = { dataset: { action: 'apneVaktpost', id: '3' } };
            assert(klikkSkalKjore(knapp) === true, 'knapper fyrer som for');
        """)


class VarighetTests(SimpleTestCase):
    """Timer per skift — kolonnen André ba om.

    Det er det ene tallet man ellers regner ut i hodet for hver rad, og
    «20:00 til 04:30» er ikke åtte timer.
    """

    HARNESS = ((VAKTLISTE_JS, ('_d', '_varighet')),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_helt_antall_timer_vises_uten_desimal(self):
        run_node(self.harness, """
            const ut = _varighet({fra_tid: '2026-10-03T08:00:00',
                                  til_tid: '2026-10-03T16:00:00'});
            assert(ut === '8 t', 'fikk ' + ut);
        """)

    def test_skift_over_midnatt_regnes_riktig(self):
        """Klokkeslettene alene sier 20 til 04; det er åtte timer, ikke seksten
        og ikke minus seksten."""
        run_node(self.harness, """
            const ut = _varighet({fra_tid: '2026-10-03T20:00:00',
                                  til_tid: '2026-10-04T04:00:00'});
            assert(ut === '8 t', 'fikk ' + ut);
        """)

    def test_halvtime_far_en_desimal(self):
        run_node(self.harness, """
            const ut = _varighet({fra_tid: '2026-10-03T20:00:00',
                                  til_tid: '2026-10-04T04:30:00'});
            assert(ut === '8,5 t', 'fikk ' + ut);
        """)

    def test_manglende_eller_negativ_tid_gir_strek(self):
        """Et skift under oppsett kan mangle den ene tida, og serveren
        avviser et negativt spenn — men raden tegnes før svaret kommer."""
        run_node(self.harness, """
            assert(_varighet({fra_tid: null, til_tid: '2026-10-03T16:00:00'})
                   === '—', 'mangler fra');
            assert(_varighet({fra_tid: '2026-10-03T16:00:00',
                              til_tid: '2026-10-03T08:00:00'}) === '—',
                   'negativt spenn');
        """)


class OversiktUtenKurveTests(SimpleTestCase):
    """«Oversikt» er utskriftslista, og bare det.

    Kurven sto samlet der før hver gruppe fikk sin i sin egen fane. To steder
    å lese den samme kurven er ett for mye, og på papiret var den uansett
    skjult.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkOversikt', '_d', '_kl', '_dag', '_sammeDag',
                        '_tidsspenn', '_vaktspenn')),
    )
    VINDU = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_oversikten_tegner_ingen_kurve(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = {
              vaktliste: {vakt_navn: 'Vakta', startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T12:00:00'},
              grupper: [{id: 1, navn: 'Samleplass'}],
              ressurser: [{id: 10, navn: 'Samleplass', gruppe_id: 1}],
              vaktposter: [{id: 1, ressurs_id: 10, ledig: false, navn: 'Kari',
                            korps_navn: 'HGSD', rolle: '', merknad: '',
                            fra_tid: '2026-10-03T08:00:00',
                            til_tid: '2026-10-03T12:00:00'}]};
            console.log(mkOversikt());
        """)
        self.assertIn('Vakta', ut, 'utskriftslista skal fortsatt tegnes')
        self.assertNotIn('vl-kurve', ut)
        self.assertNotIn('vl-stolpe', ut)


class KurvePerGruppeTests(SimpleTestCase):
    """Bemanningskurven følger grupperingen.

    Én samlet kurve summerte samleplassen, ambulansene og KO til ett tall, og
    det tallet svarer ikke på noe: fire på samleplassen og null på ambulansen
    ser likt ut som to og to.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_vaktensSpenn',
                        '_bemanningPerTime', '_posterPerGruppe',
                        '_mkEnKurve', 'mkGruppekurve',
                        '_tegnforklaring', '_timesteg', '_toppunkt')),
    )
    VINDU = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    #: To grupper, to ressurser, tre skift. Ambulansen har én ledig plass.
    LISTE = """
        globalThis.aktivListe = {
          vaktliste: {startet: '2026-10-03T08:00:00',
                      planlagt_slutt: '2026-10-03T12:00:00'},
          grupper: [{id: 1, navn: 'Samleplass'}, {id: 2, navn: 'Ambulanse'},
                    {id: 3, navn: 'Ubrukt'}],
          ressurser: [{id: 10, gruppe_id: 1}, {id: 20, gruppe_id: 2}],
          vaktposter: [
            {id: 1, ressurs_id: 10, ledig: false,
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
            {id: 2, ressurs_id: 10, ledig: false,
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
            {id: 3, ressurs_id: 20, ledig: true,
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'}
          ]};
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_hver_gruppe_teller_bare_sine_egne(self):
        run_node(self.harness, self.VINDU + self.LISTE + """
            const bunker = _posterPerGruppe();
            assert(bunker.length === 2, 'to grupper med skift, fikk ' + bunker.length);
            assert(bunker[0].gruppe.navn === 'Samleplass', 'rekkefolgen fra serveren');
            assert(bunker[0].poster.length === 2, 'samleplassen har to');
            assert(bunker[1].poster.length === 1, 'ambulansen har ett');
        """)

    def test_gruppe_uten_skift_tegnes_ikke(self):
        """Seks tomme kurver på en vakt med to ressurser er verre enn ingen."""
        run_node(self.harness, self.VINDU + self.LISTE + """
            const navn = _posterPerGruppe().map((b) => b.gruppe.navn);
            assert(navn.indexOf('Ubrukt') === -1, 'fikk ' + navn.join(', '));
        """)

    def test_kurvene_deler_spenn(self):
        """Ellers ligger ikke søylene under hverandre, og to kurver man ikke
        kan sammenligne er verre enn én samlet."""
        run_node(self.harness, self.VINDU + self.LISTE + """
            const bunker = _posterPerGruppe();
            const a = _bemanningPerTime(bunker[0].poster);
            const b = _bemanningPerTime(bunker[1].poster);
            assert(a.length === b.length, 'like mange timer');
            assert(a[0].tid === b[0].tid, 'samme starttime');
        """)

    def test_hver_kurve_far_sin_egen_topp(self):
        """Samleplassen har to på vakt, ambulansen en ledig plass. Delte de
        skala, ville ambulansens hull sett halvfullt ut."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 10, gruppe_id: 1}));
            console.log(mkGruppekurve({id: 20, gruppe_id: 2}));
        """)
        self.assertIn('Samleplass', ut)
        self.assertIn('Ambulanse', ut)
        self.assertIn('topp 2 plasser', ut)
        self.assertIn('topp 1 plasser', ut)

    def test_ledige_plasser_telles_per_gruppe(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 10, gruppe_id: 1}));
            console.log(mkGruppekurve({id: 20, gruppe_id: 2}));
        """)
        self.assertIn('Alle plasser fylt', ut)        # samleplassen
        self.assertIn('4 ubesatte plasstimer', ut)    # ambulansen, fire timer

    def test_ingen_grupper_gir_ingen_kurve(self):
        run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = {vaktliste: {}, grupper: [],
                                     ressurser: [], vaktposter: []};
            assert(mkGruppekurve({id: 1, gruppe_id: 1}) === '',
                   'ingenting aa tegne');
        """)


class TimeaksenTests(SimpleTestCase):
    """Klokkeslett under søylene, og toppunktet med tidspunkt.

    Andrés bestilling: «kjekt med timevisning slik at en lett kan se hvilke
    klokkeslett bemanningen er høyest». Å lese det av søylehøyder er å gjette.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_vaktensSpenn',
                        '_bemanningPerTime', '_mkEnKurve', '_timesteg',
                        '_toppunkt')),
    )
    VINDU = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_steget_glisner_naar_vakta_er_lang(self):
        """Alle timer på en kort vakt; sjeldnere når spennet er langt —
        ellers står tallene oppå hverandre, og kurven blir uleselig av å
        være «mer informativ»."""
        run_node(self.harness, """
            assert(_timesteg(8) === 1, 'kort vakt: hver time');
            assert(_timesteg(24) === 2, 'et doegn: annenhver');
            assert(_timesteg(48) === 4, 'to doegn: hver fjerde');
            assert(_timesteg(200) === 6, 'urimelig lang: hver sjette');
        """)

    def test_ett_klokkeslett_per_soyle_saa_de_staar_under_hverandre(self):
        """Cellene i timeaksen må være like mange som søylene. Færre, og
        tallet glir bort fra timen det gjelder."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T14:00:00'},
              vaktposter: []};
            const kurve = _mkEnKurve('Test', [
              {ledig: false, fra_tid: '2026-10-03T08:00:00',
               til_tid: '2026-10-03T14:00:00'}]);
            const soyler = (kurve.match(/vl-stolpe/g) || []).length;
            // «vl-time"» med hermetegn: `vl-timeakse` er beholderen, og
            // ville ellers telt med som en celle.
            const timer = (kurve.match(/vl-time"/g) || []).length;
            const utfylte = (kurve.match(/vl-time">\d\d:\d\d</g) || []).length;
            console.log(soyler + ' ' + timer + ' ' + utfylte);
        """)
        soyler, timer, utfylte = ut.strip().splitlines()[0].split()
        self.assertEqual(soyler, timer, 'én timecelle per søyle')
        # Og cellene må faktisk ha et klokkeslett i seg. Seks tomme celler
        # står like pent under søylene som seks utfylte, og sier ingenting.
        self.assertEqual(utfylte, soyler,
                         'på en kort vakt skal hver time være skrevet ut')

    def test_toppunktet_oppgis_med_klokkeslett(self):
        """Selve spørsmålet kurven skal svare på: når er det flest på vakt?"""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T12:00:00'},
              vaktposter: []};
            // Én person hele veien, to ekstra fra 10 til 12.
            console.log(_mkEnKurve('Test', [
              {ledig: false, fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
              {ledig: false, fra_tid: '2026-10-03T10:00:00', til_tid: '2026-10-03T12:00:00'},
              {ledig: false, fra_tid: '2026-10-03T10:00:00', til_tid: '2026-10-03T12:00:00'}
            ]));
        """)
        self.assertIn('topp 3 plasser', ut)
        self.assertIn('10:00', ut, 'toppen begynner kl. 10')
        self.assertIn('12:00', ut, 'og varer ut den siste timen')

    def test_ett_enkelt_topptidspunkt_vises_uten_spenn(self):
        run_node(self.harness, self.VINDU + """
            const punkter = [
              {tid: '2026-10-03T08:00:00.000Z', antall: 1, planlagt: 1},
              {tid: '2026-10-03T09:00:00.000Z', antall: 3, planlagt: 3},
              {tid: '2026-10-03T10:00:00.000Z', antall: 1, planlagt: 1}];
            const ut = _toppunkt(punkter, 3);
            assert(ut.indexOf('–') === -1, 'en enkelt time er ikke et spenn: ' + ut);
        """)

    def test_topper_som_ikke_henger_sammen_gir_bare_forste(self):
        """To adskilte topper er ikke ett spenn — å skrive «kl. 08–20» når
        det er stille imellom, er å lyve med et bindestrek."""
        run_node(self.harness, self.VINDU + """
            const punkter = [
              {tid: '2026-10-03T08:00:00.000Z', antall: 3, planlagt: 3},
              {tid: '2026-10-03T09:00:00.000Z', antall: 1, planlagt: 1},
              {tid: '2026-10-03T10:00:00.000Z', antall: 3, planlagt: 3}];
            const ut = _toppunkt(punkter, 3);
            assert(ut.indexOf('–') === -1, 'ikke sammenhengende: ' + ut);
        """)


class GruppekurveIFanenTests(SimpleTestCase):
    """Kurven står i fanen den gjelder.

    Å lete etter samleplassens bemanning under «Oversikt» mens man bemanner
    samleplassen, er ett skifte for mye.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_vaktensSpenn',
                        '_bemanningPerTime', '_posterPerGruppe', '_mkEnKurve',
                        '_timesteg', '_toppunkt', '_tegnforklaring',
                        'mkGruppekurve')),
    )
    VINDU = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")
    LISTE = """
        globalThis.aktivListe = {
          vaktliste: {startet: '2026-10-03T08:00:00',
                      planlagt_slutt: '2026-10-03T12:00:00'},
          grupper: [{id: 1, navn: 'Samleplass'}, {id: 2, navn: 'Ambulanse'}],
          ressurser: [{id: 10, gruppe_id: 1}, {id: 20, gruppe_id: 2}],
          vaktposter: [
            {id: 1, ressurs_id: 10, ledig: false,
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
            {id: 2, ressurs_id: 10, ledig: false,
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
            {id: 3, ressurs_id: 20, ledig: true,
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'}
          ]};
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_fanen_viser_sin_egen_gruppes_kurve(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 10, gruppe_id: 1}));
        """)
        self.assertIn('Samleplass', ut)
        self.assertNotIn('Ambulanse', ut, 'nabogruppa hører ikke hjemme her')
        self.assertIn('topp 2 plasser', ut)

    def test_ambulansefanen_viser_ambulansen(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 20, gruppe_id: 2}));
        """)
        self.assertIn('Ambulanse', ut)
        self.assertNotIn('Samleplass', ut)
        self.assertIn('4 ubesatte plasstimer', ut)

    def test_ressurs_uten_skift_i_gruppa_gir_ingen_kurve(self):
        """En tom kurve over en fane man nettopp har laget, sier ingenting."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log('[' + mkGruppekurve({id: 30, gruppe_id: 99}) + ']');
        """)
        self.assertIn('[]', ut)

    def test_dogn_staar_i_tegnforklaringen(self):
        """Den hvite streken i kurven er midnatt, ikke nåværende tidspunkt.
        André måtte spørre hva den var — en strek man må spørre om, er en
        strek som ikke forklarer noe."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 10, gruppe_id: 1}));
        """)
        self.assertIn('Midnatt', ut)


class NyRessursIFanerekkaTests(SimpleTestCase):
    """«Ny ressurs» er sist i fanerekka, og bare for `skriv_leder`.

    Knappen lå i malen og ble skjult av `gateKnapper()`. Da den flyttet inn i
    rekka — en ressurs *er* en fane — måtte tilgangen flytte med: `tegnFaner()`
    tegner på nytt ved hvert panelbytte, og en klasse satt én gang ved
    sidelasting rekker ikke over markup som lages på nytt.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('tegnFaner', '_posterFor', '_ikkePlassert',
                        '_nivaa', '_erAdmin', 'kanLede')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    @staticmethod
    def _vindu(nivaa='', *, admin=False):
        return (
            f"globalThis.window = {{ MODUL_TILGANG: "
            f"{{ vaktliste: '{nivaa}', admin: {str(admin).lower()} }} }};\n"
            "globalThis.aktivFane = 'oversikt';\n"
            "globalThis.OVERSIKT = 'oversikt';\n"
            "globalThis.IKKE_PLASSERT = 'ikke-plassert';\n"
            "globalThis.aktivListe = {ressurser: [{id: 7, navn: 'Ambulanse 1',"
            " ikon: 'truck'}], vaktposter: [], mannskap: []};\n"
            "let lagret = '';\n"
            "globalThis.document = { getElementById: () => ("
            "{ set innerHTML(v) { lagret = v; }, get innerHTML() { return lagret; } }) };\n"
        )

    def _tegn(self, nivaa='', *, admin=False):
        return run_node(self.harness, self._vindu(nivaa, admin=admin) + """
            const el = document.getElementById('vl-faner');
            tegnFaner();
            console.log(el.innerHTML);
        """)

    def test_lederen_ser_knappen_sist_i_rekka(self):
        ut = self._tegn('skriv_leder')
        self.assertIn('Ny ressurs', ut)
        self.assertLess(ut.index('Ambulanse 1'), ut.index('Ny ressurs'),
                        'knappen skal stå etter fanene, ikke foran dem')
        self.assertIn('#nyRessursModal', ut)

    def test_admin_ser_den_ogsaa(self):
        self.assertIn('Ny ressurs', self._tegn('', admin=True))

    def test_bemanneren_ser_den_ikke(self):
        """`skriv_full` bemanner; hva vakta består av er vaktlederens
        beslutning. Knappen ville gitt 403."""
        ut = self._tegn('skriv_full')
        self.assertIn('Ambulanse 1', ut, 'fanene skal fortsatt tegnes')
        self.assertNotIn('Ny ressurs', ut)

    def test_leseren_ser_den_ikke(self):
        self.assertNotIn('Ny ressurs', self._tegn('les'))
