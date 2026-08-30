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
    'mkOversikt',
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
        (VAKTLISTE_JS, ('mkRessurs', 'mkOversikt', 'mkIkkePlassert',
                        'tegnFaner', '_posterFor', '_ikkePlassert',
                        '_tidsspenn', '_nivaa', 'kanSkriveAlt', 'kanBemanne')),
    )

    #: Byggerne spør om tilgang fra fase 3. Node har ingen `window`, så den
    #: stubbes — og med admin, slik at *alle* knappene bygges. Escaping-testene
    #: skal se mest mulig markup; hvem som får se hva er `tests_tilgang.py`
    #: sitt bord.
    VINDU = "globalThis.window = { MODUL_TILGANG: { admin: true } };"

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _liste(self, **overstyr):
        """JS-litteral for `aktivListe`, med felter testen vil overstyre."""
        import json
        grunn = {'vaktliste': {'id': 1, 'status_navn': 'Planlegging',
                               'i_drift': False},
                 'ressurser': [], 'vaktposter': [], 'mannskap': []}
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

REGISTER_BUILDERS = ('mkMannskap', 'mkVerdier')

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
        (VAKTLISTE_REGISTRE_JS, ('mkMannskap', 'mkVerdier', '_nivaa',
                                 'kanSkriveAlt', 'kanRedigerePerson')),
    )

    VINDU = "globalThis.window = { MODUL_TILGANG: { admin: true } };"

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
