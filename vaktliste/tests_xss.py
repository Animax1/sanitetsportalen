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
    '_fyll',
    'tegnFaner',
    'mkRessurs',
    '_rolleValg',
    '_fyllValgFor',
    'mkOversikt',
    'mkKurve',
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
    '_rolleValg(vp, kanRore)': 'nedtrekk fra en bygger som selv skannes her',
    'valg': 'options bygget lokalt, navn og id escapet inni',
    'valgt': 'hardkodet selected-attributt fra en ternær',
    'settKnapp': 'markup bygget lokalt, id escapet inni',
    'fjernKnapp': 'markup bygget lokalt, id escapet inni',
    'soyler': 'søyler bygget lokalt i samme funksjon',
    'skille': 'hardkodet CSS-klasse fra en ternær',
    'bunn': 'markup bygget lokalt, datoene escapet inni',
    'mkKurve()': 'markup fra en bygger som selv skannes her',
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
    # `tittel` er ren tekst som escapes én gang ved innsetting i `title=`.
    # Escapet vi her også, ville teksten blitt dobbeltescapet i tooltipen —
    # samme mønster som `meta` i oppdrag-sentral.js.
    '_dag(p.tid)': 'bygger ren tekst i `tittel`, som escapes ved innsetting',
    '_kl(p.tid)': 'bygger ren tekst i `tittel`, som escapes ved innsetting',
    'p.antall': 'tall, i samme rene tekst som escapes ved innsetting',
    'p.planlagt': 'tall, i samme rene tekst som escapes ved innsetting',
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
        (VAKTLISTE_JS, ('mkRessurs', '_rolleValg', '_fyllValgFor',
                        'mkOversikt', 'mkKurve',
                        'mkIkkePlassert', 'tegnFaner', '_posterFor',
                        '_ikkePlassert', '_tidsspenn', '_vaktspenn',
                        '_bemanningPerTime', '_iso16', '_d', '_kl', '_dag',
                        '_sammeDag', '_nivaa', 'kanSkriveAlt', 'kanBemanne')),
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
                 'roller': []}
        grunn.update(overstyr)
        return json.dumps(grunn)

    def test_ressursnavn_med_markup_kommer_ut_som_tekst(self):
        """Fritekstfeltet i modulen — admin skriver hva som helst her."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivListe = {self._liste()};
            console.log(mkRessurs({{
              id: 1, navn: '<img src=x onerror=alert(1)>', ikon: 'people',
              type_navn: 'Lag', korps_navn: '', enhet_navn: ''
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
              type_navn: 'Lag', korps_navn: '', enhet_navn: ''
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
                        '_vaktspenn', '_iso16', '_bemanningPerTime')),
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
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_bemanningPerTime')),
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
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_bemanningPerTime')),
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
