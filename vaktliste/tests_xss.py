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
    PORTAL_UTILS_JS, VAKTLISTE_JS, build_harness,
    extract_function, node_available, read_js, run_node,
)

HTML_BUILDERS = (
    'fyllVelger',
    'mkRolleRad',
    '_fyll',
    'tegnFaner', '_fanerad', '_mannskapsfane', 'iDrift', '_tilstede',
    'mkRessurs',
    '_stempelknapper',
    'mkTilstede',
    '_rolleValg',
    '_fyllValgFor',
    'mkOversikt',
    'mkGruppekurve',
    '_mkEnKurve',
    'mkIkkePlassert',
)

ESCAPING_CALLS = ('escHtmlValue(', 'cellHtml(', '_escHtml(', 'escapeHtml(')

REVIEWED_INTERPOLATIONS = {
    # Drift (fase 4). Knappene bygges lokalt, og bare når tilgangen og
    # tilstanden tillater dem — id-en er escapet inne i `_stempelknapper`.
    'stempler': 'markup bygget lokalt av _stempelknapper(), id-en escapet inni',
    'stil': 'hardkodet Bootstrap-klasse fra kallstedet, ingen data i seg',
    'linjer': 'tabellrader bygget lokalt i samme funksjon',
    'bolker': 'markup bygget lokalt i samme funksjon',
    'aktiv': 'hardkodet CSS-klasse fra en ternær',
    'antall': 'markup bygget lokalt, tallet escapet inni',
    'korpsmerke': 'markup bygget lokalt, korpsnavnet escapet inni',
    'enhetsmerke': 'markup bygget lokalt, enhetsnavnet escapet inni',
    'rader': 'markup bygget lokalt av byggere som selv skannes her',
    'rest': 'markup bygget lokalt, tallet escapet inni',
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
    'korpsCelle': 'nedtrekk eller escapet tekst, bygget lokalt',
    'mkGruppekurve(r)': 'kurve fra en bygger som selv skannes her',
    '_tegnforklaring()': 'hardkodet markup uten data',
    'timeakse': 'celler bygget lokalt, klokkeslettene escapet inni',
    'kurve': 'kurve fra `_mkEnKurve`, som selv skannes her',
    "naar ? ' ' + escapeHtml(naar) : ''":
        'ternær der den ene grenen er escapet og den andre er tom streng',
    "vis ? escapeHtml(_kl(p.tid)) : ''":
        'ternær der den ene grenen er escapet og den andre er tom streng',
    'innhold': 'to bruk, begge bygget lokalt: input eller escapet tekst i '
               'tidscella, og ressursbolkene i «Tilstede nå»',
    'merke': 'to bruk, begge trygge: selected-attributtet fra en ternær i nedtrekkene, og ukedagsmerket der dagen escapes inni',
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
        (VAKTLISTE_JS, ('mkRessurs', '_radklasse', '_stempelknapper',
                        'kanStemple', 'iDrift', '_rolleValg',
                        'rollerForGruppe', '_fyllValgFor', '_varighet',
                        'mkRolleRad', 'mkOversikt', '_skiftrekkefolge',
                        '_mkEnKurve', 'mkGruppekurve', '_posterIGruppe',
                        'mkGruppe', '_plassKorps', '_tegnforklaring',
                        '_timesteg', '_ressurserIGruppe',
                        '_grupperMedRessurser', '_toppunkt',
                        '_posterPerGruppe', '_vaktensSpenn',
                        'mkIkkePlassert', 'tegnFaner', '_fanerad',
                        '_mannskapsfane', '_tilstede', '_posterFor',
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
                grupper=[{'id': 1, 'navn': 'Lag', 'ikon': 'people'}],
                ressurser=[{'id': 1, 'navn': 'Lag 1', 'gruppe_id': 1}],
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

    def test_ressursnavn_i_overskriften_escapes(self):
        """Overskriften er ressursens navn fra 30. aug. 2026 — lista er
        gruppert på ressurs, ikke korps. Navnet er fritekst fra basen."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivListe = {self._liste(
                grupper=[{'id': 1, 'navn': 'Lag', 'ikon': 'people'}],
                ressurser=[{'id': 1, 'navn': '<b>Lag 1</b>', 'gruppe_id': 1}],
                vaktposter=[{
                    'id': 1, 'ressurs_id': 1, 'mannskap_id': 1,
                    'navn': 'Kari', 'korps_navn': 'HGSD',
                    'korps_kort': 'HGSD', 'rolle': '',
                    'fra_tid': '2026-10-03T08:00:00Z',
                    'til_tid': '2026-10-03T16:00:00Z'}])};
            console.log(mkOversikt());
        ''')
        self.assertNotIn('<b>Lag 1</b>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_fanenavn_escapes(self):
        """Fanenavnet er gruppas navn fra 30. aug. 2026, og gruppenavn er
        fritekst satt av vaktleder."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivFane = 'oversikt';
            globalThis.OVERSIKT = 'oversikt';
            globalThis.IKKE_PLASSERT = 'ikke-plassert';
            globalThis.MANNSKAP = 'mannskap';
            globalThis.TILSTEDE = 'tilstede';
            globalThis.register = null;
            globalThis.aktivListe = {self._liste(
                grupper=[{'id': 1, 'navn': '<b>Lag</b>', 'ikon': 'people'}],
                ressurser=[{'id': 1, 'navn': 'Lag 1', 'gruppe_id': 1,
                            'ikon': 'people'}])};
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => el }};
            tegnFaner();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('<b>Lag</b>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_gruppeikonet_escapes_i_fanen(self):
        """Ikonet står i et class-attributt — attributt-XSS."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.aktivFane = 'oversikt';
            globalThis.OVERSIKT = 'oversikt';
            globalThis.IKKE_PLASSERT = 'ikke-plassert';
            globalThis.MANNSKAP = 'mannskap';
            globalThis.TILSTEDE = 'tilstede';
            globalThis.register = null;
            globalThis.aktivListe = {self._liste(
                grupper=[{'id': 1, 'navn': 'Lag',
                          'ikon': '" onload="alert(1)'}],
                ressurser=[{'id': 1, 'navn': 'Lag 1', 'gruppe_id': 1,
                            'ikon': 'people'}])};
            const el = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: () => el }};
            tegnFaner();
            console.log(el.innerHTML);
        ''')
        self.assertNotIn('onload="alert(1)"', ut)

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


# ── Mannskapsregisteret ──────────────────────────────────────────────────────
#
# Byggerne lå i vaktliste-registre.js til 30. aug. 2026, da registersiden ble
# lagt ned og fanen flyttet inn i planleggingssiden. Egen bygger-liste fordi
# escaping-kravene er de samme, men byggerne er andre enn tabellens.

REGISTER_BUILDERS = ('mkMannskap', 'mkVerdiliste', '_personKolonne')

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
    'stempler': 'markup bygget lokalt av _stempelknapper(), id-en escapet inni',
    'bolker': 'markup bygget lokalt i samme funksjon',
    'linjer': 'tabellrader bygget lokalt i samme funksjon',
    'verdiKnapper': 'markup bygget lokalt, rad-id escapet inni',
    'nyKnapp': 'markup bygget lokalt, etiketten escapet inni',
    'tilKorps': 'markup bygget lokalt, ingen data i seg',
    # Mannskapstabellen. `inaktivMerke`, `merker` og `konto` sto allerede over
    # med samme begrunnelse — tabellen gjenbruker dem.
    'stige': 'markup bygget lokalt, «bygger på»-navnet escapet inni',
    'kropp': 'tabellrader bygget lokalt i samme funksjon',
    # Treff-telleren settes med textContent, ikke innerHTML — ingen parsing
    # å bryte ut av, og tallene kommer uansett fra `.length`.
    'rader.length': 'tall, settes med textContent',
    'register.mannskap.length': 'tall, settes med textContent',
    'hode': 'markup bygget lokalt i samme funksjon',
    "_personKolonne('navn', 'Navn')": 'bygger med escapet innhold, se funksjonen',
    "_personKolonne('korps', 'Korps')": 'bygger med escapet innhold, se funksjonen',
    "_personKolonne('telefon', 'Telefon')": 'bygger med escapet innhold, se funksjonen',
}


class RegistersidenEscapingKildeTests(SimpleTestCase):
    def test_byggerne_finnes(self):
        src = read_js(VAKTLISTE_JS)
        for navn in REGISTER_BUILDERS:
            with self.subTest(navn=navn):
                self.assertIn(f'function {navn}(', src)

    def test_registersiden_finnes_ikke_lenger(self):
        """Flata flyttet inn i planleggingssiden 30. aug. 2026. Blir malen
        eller JS-fila liggende igjen, laster ingen dem — og en fil ingen
        laster er en fil som råtner uten at noe feiler."""
        from pathlib import Path
        from django.conf import settings
        rot = Path(settings.BASE_DIR)
        self.assertFalse((rot / 'templates' / 'vaktliste' / 'registre.html').exists())
        self.assertFalse((rot / 'static' / 'js' / 'vaktliste-registre.js').exists())

    def test_siden_laster_ikke_patients_utils(self):
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
            'Uescapede interpolasjoner i mannskapsbyggerne:\n  '
            + '\n  '.join(uescapet)))


class RegistersidenEscapingOppforselTests(SimpleTestCase):
    """Registersiden er den eneste flaten der notatfeltet skrives.

    Feltet er unntatt verdilogging i audit nettopp fordi det er helt fritt —
    og et helt fritt felt er også det farligste å sette inn i DOM-en.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml')),
        (VAKTLISTE_JS, ('mkMannskap', 'mkVerdiliste', '_personKolonne',
                        '_passerPersonsok', '_sorterMannskap', '_nivaa',
                        '_erAdmin', 'kanSkriveAlt', 'kanSkriveNoe',
                        'kanRedigerePerson')),
    )

    #: Tabellen skriver treff-telleren i DOM-en og leser sorteringstilstanden,
    #: så begge stubbes. Node har verken `window` eller `document`.
    VINDU = ("globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.document = { getElementById: () => null };\n"
             "globalThis.personsok = ''; globalThis.personSortKol = 'korps';\n"
             "globalThis.personSortStigende = true;\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_personnavn_og_kompetanse_escapes(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.register = { korps: [{id: 1, navn: 'HGSD'}], mannskap: [{
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
            globalThis.register = { korps: [{id: 1, navn: 'HGSD'}], mannskap: [{
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
            globalThis.aktivVerdiregister = 'korps';
            globalThis.REGISTRE = { korps: {sti:'korps', nyEtikett:'Nytt korps',
                                            tittel:'Korps', kortnavn:true} };
            globalThis.register = { korps: [{
              id: 1, navn: '<b>Haugesund</b>', kortnavn: '<i>HGSD</i>',
              er_aktiv: true, i_bruk: 0
            }]};
            console.log(mkVerdiliste('korps'));
        """)
        self.assertNotIn('<b>Haugesund</b>', ut)
        self.assertNotIn('<i>HGSD</i>', ut)
        self.assertIn('&lt;b&gt;', ut)

    def test_inaktiv_rad_merkes(self):
        """Pensjonering er den normale veien ut — raden skal fortsatt vises,
        men tydelig nedtonet. Kontrollen ligger i JS-assertene."""
        run_node(self.harness, self.VINDU + """
            globalThis.register = { korps: [{id: 1, navn: 'HGSD'}], mannskap: [{
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
        src = read_js(VAKTLISTE_JS)
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
        (VAKTLISTE_JS, ('mkOversikt', '_skiftrekkefolge', '_d', '_kl',
                        '_dag', '_sammeDag', '_tidsspenn', '_vaktspenn',
                        '_ressurserIGruppe', '_grupperMedRessurser')),
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
                        '_mkEnKurve', 'mkGruppekurve', '_posterIGruppe',
                        '_ressurserIGruppe', '_tegnforklaring',
                        '_timesteg', '_toppunkt')),
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
            console.log(mkGruppekurve({id: 1, navn: 'Samleplass'}));
            console.log(mkGruppekurve({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('Samleplass', ut)
        self.assertIn('Ambulanse', ut)
        self.assertIn('topp 2 plasser', ut)
        self.assertIn('topp 1 plasser', ut)

    def test_ledige_plasser_telles_per_gruppe(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 1, navn: 'Samleplass'}));
            console.log(mkGruppekurve({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('Alle plasser fylt', ut)        # samleplassen
        self.assertIn('4 ubesatte plasstimer', ut)    # ambulansen, fire timer

    def test_ingen_grupper_gir_ingen_kurve(self):
        run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = {vaktliste: {}, grupper: [],
                                     ressurser: [], vaktposter: []};
            assert(mkGruppekurve({id: 1, navn: 'X'}) === '',
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
                        '_bemanningPerTime', '_posterPerGruppe',
                        '_mkEnKurve', '_timesteg', '_toppunkt',
                        '_tegnforklaring', '_posterIGruppe',
                        '_ressurserIGruppe', 'mkGruppekurve')),
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
            console.log(mkGruppekurve({id: 1, navn: 'Samleplass'}));
        """)
        self.assertIn('Samleplass', ut)
        self.assertNotIn('Ambulanse', ut, 'nabogruppa hører ikke hjemme her')
        self.assertIn('topp 2 plasser', ut)

    def test_ambulansefanen_viser_ambulansen(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('Ambulanse', ut)
        self.assertNotIn('Samleplass', ut)
        self.assertIn('4 ubesatte plasstimer', ut)

    def test_gruppe_uten_skift_faar_kurven_likevel(self):
        """**Endret 30. aug. 2026.** Kurven falt bort når gruppa ikke hadde et
        eneste skift — altså akkurat mens man setter opp. Det var feil på samme
        måte som at kurven en gang bare dekket skiftene: hullet man planlegger
        for å tette er størst når ingen er satt opp, og da forsvant hele
        kurven. Nå står den flat på null over vaktas spenn.

        Gruppa må ha ressurser; en gruppe uten ressurser er ingen fane.
        """
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            globalThis.aktivListe.grupper.push({id: 9, navn: 'Tom'});
            globalThis.aktivListe.ressurser.push({id: 90, gruppe_id: 9});
            console.log(mkGruppekurve({id: 9, navn: 'Tom'}));
        """)
        self.assertIn('Tom', ut)
        self.assertIn('vl-stolpe', ut, 'spennet tegnes selv uten skift')
        self.assertIn('topp 1 plasser', ut, 'flat null skaleres mot 1')

    def test_dogn_staar_i_tegnforklaringen(self):
        """Den hvite streken i kurven er midnatt, ikke nåværende tidspunkt.
        André måtte spørre hva den var — en strek man må spørre om, er en
        strek som ikke forklarer noe."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 1, navn: 'Samleplass'}));
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
        (VAKTLISTE_JS, ('tegnFaner', '_fanerad', '_mannskapsfane',
                        'iDrift', '_tilstede', '_posterFor',
                        '_ikkePlassert', '_ressurserIGruppe',
                        '_grupperMedRessurser', '_nivaa', '_erAdmin',
                        'kanLede')),
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
            "globalThis.MANNSKAP = 'mannskap';\n"
            "globalThis.TILSTEDE = 'tilstede';\n"
            "globalThis.register = null;\n"
            "globalThis.aktivListe = {grupper: [{id: 3, navn: 'Ambulanse',"
            " ikon: 'truck'}], ressurser: [{id: 7, navn: 'Ambulanse 1',"
            " gruppe_id: 3, ikon: 'truck'}], vaktposter: [], mannskap: []};\n"
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
        self.assertLess(ut.index('Ambulanse'), ut.index('Ny ressurs'),
                        'knappen skal stå etter fanene, ikke foran dem')
        self.assertIn('apneNyRessurs', ut)

    def test_admin_ser_den_ogsaa(self):
        self.assertIn('Ny ressurs', self._tegn('', admin=True))

    def test_bemanneren_ser_den_ikke(self):
        """`skriv_full` bemanner; hva vakta består av er vaktlederens
        beslutning. Knappen ville gitt 403."""
        ut = self._tegn('skriv_full')
        self.assertIn('Ambulanse', ut, 'fanene skal fortsatt tegnes')
        self.assertNotIn('Ny ressurs', ut)

    def test_leseren_ser_den_ikke(self):
        self.assertNotIn('Ny ressurs', self._tegn('les'))


class FanenErGruppaTests(SimpleTestCase):
    """Fanen er ressursgruppa, ikke den enkelte ressursen.

    Andrés bestilling 30. aug. 2026: «når jeg lager ny ressurs så skal fanen
    være en oversikt — ambulanse er for alle ambulansene som skal være på
    vakt». Én fane per bil ga ti faner på en vakt med ti biler, og ingen
    plass der man kunne se dem i sammenheng — som er det man planlegger etter.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('tegnFaner', '_fanerad', '_mannskapsfane',
                        'iDrift', '_tilstede', 'mkGruppe', 'mkRessurs',
                        '_radklasse', '_stempelknapper', 'kanStemple',
                        '_rolleValg', '_skiftrekkefolge', '_fyllValgFor',
                        '_varighet', 'mkGruppekurve', '_mkEnKurve',
                        '_tegnforklaring', '_timesteg', '_toppunkt',
                        '_posterPerGruppe', '_vaktensSpenn',
                        '_posterIGruppe', '_plassKorps',
                        '_bemanningPerTime', 'rollerForGruppe', '_iso16',
                        '_posterFor', '_ikkePlassert', '_ressurserIGruppe',
                        '_grupperMedRessurser', '_d', '_kl', '_dag',
                        '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanLede',
                        'kanBemanne', 'gruppaHarPlass')),
    )
    VINDU = ("globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n"
             "globalThis.aktivFane = 'oversikt';\n"
             "globalThis.OVERSIKT = 'oversikt';\n"
             "globalThis.IKKE_PLASSERT = 'ikke-plassert';\n"
            "globalThis.MANNSKAP = 'mannskap';\n"
            "globalThis.TILSTEDE = 'tilstede';\n"
            "globalThis.register = null;\n")

    #: To ambulanser i samme gruppe, én samleplass i en annen.
    LISTE = """
        globalThis.aktivListe = {
          vaktliste: {startet: '2026-10-03T08:00:00',
                      planlagt_slutt: '2026-10-03T12:00:00'},
          grupper: [{id: 1, navn: 'Samleplass', ikon: 'hospital'},
                    {id: 2, navn: 'Ambulanse', ikon: 'truck'},
                    {id: 3, navn: 'Ubrukt', ikon: 'box'}],
          ressurser: [
            {id: 10, navn: 'Samleplass', gruppe_id: 1, gruppe_navn: 'Samleplass',
             ikon: 'hospital', korps_navn: '', enhet_navn: ''},
            {id: 20, navn: 'Ambulanse 1', gruppe_id: 2, gruppe_navn: 'Ambulanse',
             ikon: 'truck', korps_navn: '', enhet_navn: 'A-101'},
            {id: 21, navn: 'Ambulanse 2', gruppe_id: 2, gruppe_navn: 'Ambulanse',
             ikon: 'truck', korps_navn: '', enhet_navn: ''}],
          roller: [], mannskap: [],
          vaktposter: [
            {id: 1, ressurs_id: 20, ledig: false, navn: 'Kari', korps_kort: 'HG',
             kompetanser: [], rolle_id: null, merknad: '',
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
            {id: 2, ressurs_id: 21, ledig: true, navn: '', korps_kort: '',
             kompetanser: [], rolle_id: null, merknad: '',
             fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'}]};
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _faner(self):
        return run_node(self.harness, self.VINDU + self.LISTE + """
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            tegnFaner();
            console.log(el.innerHTML);
        """)

    def test_en_fane_per_gruppe_ikke_per_ressurs(self):
        ut = self._faner()
        self.assertIn('>Ambulanse<', ut, 'gruppa er fanen')
        self.assertNotIn('Ambulanse 1', ut, 'den enkelte bilen er ikke en fane')
        self.assertNotIn('Ambulanse 2', ut)

    def test_gruppe_uten_ressurser_blir_ingen_fane(self):
        """En tom fane per ubrukt gruppe er seks faner på en vakt med to
        ressurser."""
        self.assertNotIn('Ubrukt', self._faner())

    def test_fanen_teller_skiftene_i_hele_gruppa(self):
        """Tallet på fanen er gruppas, ikke én ressurs' — ellers svarer det
        på et spørsmål ingen stilte."""
        ut = self._faner()
        # Ambulansegruppa har to skift til sammen, ett på hver bil.
        self.assertRegex(ut, r'Ambulanse<span class="vl-antall">2</span>')

    def test_mannskap_staar_rett_etter_oversikt(self):
        ut = self._faner()
        self.assertLess(ut.index('Oversikt'), ut.index('Mannskap'))
        self.assertLess(ut.index('Mannskap'), ut.index('>Ambulanse<'))

    def test_tilstede_fanen_finnes_bare_i_drift(self):
        """I planlegging er den tom per definisjon — ingen er stemplet — og
        en fane som alltid sier null er en fane man slutter å se."""
        self.assertNotIn('Tilstede nå', self._faner())

    def test_tilstede_fanen_kommer_med_drift(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            aktivListe.vaktliste.i_drift = true;
            aktivListe.vaktposter = [
              {id: 1, ressurs_id: 10, ledig: false, tilstede: true},
              {id: 2, ressurs_id: 10, ledig: false, tilstede: false}];
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: () => el };
            tegnFaner();
            console.log(el.innerHTML);
        """)
        self.assertIn('Tilstede nå', ut)
        self.assertIn('data-arg="tilstede"', ut)
        self.assertIn('>1<', ut, 'fanen teller de tilstedeværende')

    def test_mannskap_er_en_ekte_fane(self):
        """Den var en lenke ut til /vaktliste/registre/, og et klikk kostet
        deg plassen i planleggingen — mens mannskap og ressurser er nettopp de
        to man veksler mellom (30. aug. 2026)."""
        ut = self._faner()
        self.assertIn('data-action="visFane" data-arg="mannskap"', ut)
        self.assertNotIn('/vaktliste/registre/', ut,
                         'registersiden finnes ikke lenger')

    def test_mannskapsfanen_staar_ogsaa_uten_vaktliste(self):
        """Korps må inn før mannskap, og mannskap før noen kan settes på
        vakt. Var fanen borte til den første vaktlista fantes, sto man fast
        på skritt én."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = null;
            globalThis.register = {mannskap: [{id: 1}, {id: 2}]};
            const el = {innerHTML: ''};
            globalThis.document = {getElementById: () => el};
            tegnFaner();
            console.log(el.innerHTML);
        """)
        self.assertIn('data-arg="mannskap"', ut)
        self.assertNotIn('Oversikt', ut, 'det finnes ingen liste å vise')
        self.assertIn('>2<', ut, 'antallet er registerets, ikke vaktas')

    def test_gruppepanelet_viser_alle_ressursene_i_gruppa(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppe({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('Ambulanse 1', ut)
        self.assertIn('Ambulanse 2', ut)
        self.assertNotIn('>Samleplass<', ut, 'nabogruppa hører ikke hjemme her')

    def test_gruppepanelet_har_kurven_over_ressursene(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppe({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('vl-kurve', ut)
        self.assertLess(ut.index('vl-kurve'), ut.index('Ambulanse 1'),
                        'kurven summerer ressursene under seg')

    def test_enhetskoblingen_staar_paa_ressursen_i_fanen(self):
        """Koblingen til oppdragsmodulen er per bil, ikke per gruppe — den
        må derfor stå på ressurskortet inne i fanen."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppe({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('A-101', ut)

    def test_tom_gruppe_sier_fra_og_viser_veien_videre(self):
        """Tomteksten skal forklare hva gruppa rommer — at hver bil er sin
        egen rad — og bære knappen som lager den første. En tom fane uten vei
        videre er der André sto fast."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppe({id: 3, navn: 'Ubrukt', ikon: 'box'}));
        """)
        self.assertIn('Ingen Ubrukt satt opp', ut)
        self.assertIn('Ny Ubrukt', ut, 'knappen som lager den første')
        self.assertIn('sin egen', ut, 'og forklaringen på hva en rad er')

    def test_gruppehodet_teller_enhetene(self):
        """Fanen «Ambulanse» rommer bil A, bil B og bil C — hodet sier hvor
        mange, så det ikke ser ut som gruppa *er* bilen."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppe({id: 2, navn: 'Ambulanse', ikon: 'truck'}));
        """)
        self.assertIn('2 enheter', ut)

    def test_knappen_i_gruppa_baerer_gruppas_id(self):
        """Uten `data-arg` ville den falt tilbake på `aktivFane`, og en knapp
        trykket fra et annet sted enn fanen hadde lagt bilen i feil gruppe."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppe({id: 2, navn: 'Ambulanse', ikon: 'truck'}));
        """)
        self.assertIn('data-arg="2"', ut)

    def test_ukoblet_enhet_vises_som_en_tom_plass(self):
        """Merkelappen sto bare der bilen *var* koblet, så den som ikke hadde
        koblet noe så ingenting — og kunne ikke vite at koblingen finnes per
        bil. Det var halve forvirringen."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppe({id: 2, navn: 'Ambulanse', ikon: 'truck'}));
        """)
        self.assertIn('A-101', ut, 'den koblede bilen viser enheten')
        self.assertIn('Ikke koblet', ut, 'og den ukoblede viser at den kan kobles')


class UtskriftslistaTests(SimpleTestCase):
    """Utskriftslista: gruppert på ressurs, og sortert så rekkefølgen sier noe.

    **To ting André så i bruk 30. aug. 2026.** Lista var gruppert på korps,
    og han spurte hvordan man ser hvem som er på hvilken bil. Og innenfor en
    gruppe lå et skift som slutter 22:15 midt blant skift som slutter 03:00
    neste dag — fordi sorteringen stoppet på `fra_tid` og lot resten stå i
    innsettingsrekkefølge.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkOversikt', '_skiftrekkefolge', '_d', '_kl',
                        '_dag', '_sammeDag', '_tidsspenn', '_vaktspenn',
                        '_ressurserIGruppe', '_grupperMedRessurser')),
    )
    VINDU = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    #: Andrés egne rader: tre skift som begynner 17:00, ett av dem kort.
    LISTE = """
        globalThis.aktivListe = {
          vaktliste: {vakt_navn: 'Vakta', startet: '2026-09-04T17:00:00',
                      planlagt_slutt: '2026-09-05T15:00:00'},
          korps: [{id: 1, navn: 'Haugesund', kortnavn: 'HGSD'},
                  {id: 2, navn: 'Karmøy', kortnavn: 'KARM'}],
          grupper: [{id: 1, navn: 'Samleplass', ikon: 'hospital'},
                    {id: 2, navn: 'Ambulanse', ikon: 'truck'}],
          ressurser: [{id: 10, navn: 'Samleplass', gruppe_id: 1},
                      {id: 20, navn: 'Ambulanse 1', gruppe_id: 2},
                      {id: 21, navn: 'Ambulanse 2', gruppe_id: 2}],
          vaktposter: [
            {id: 1, ressurs_id: 10, ledig: true, navn: '', korps_kort: '',
             reservert_korps_id: 2, rolle: 'Førstehjelper', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'},
            {id: 2, ressurs_id: 10, ledig: true, navn: '', korps_kort: '',
             reservert_korps_id: 2, rolle: 'Førstehjelper', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'},
            {id: 3, ressurs_id: 10, ledig: true, navn: '', korps_kort: '',
             reservert_korps_id: 2, rolle: 'Førstehjelper', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-04T22:15:00'},
            {id: 4, ressurs_id: 20, ledig: false, navn: 'Kari',
             korps_kort: 'HGSD', rolle: 'Sjåfør', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'},
            {id: 5, ressurs_id: 21, ledig: false, navn: 'Ola',
             korps_kort: 'HGSD', rolle: 'Sjåfør', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'}]};
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _ut(self):
        return run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkOversikt());
        """)

    def test_det_korteste_skiftet_kommer_forst_naar_de_begynner_samtidig(self):
        """Rad 3 hos André: begynner 17:00 som de andre, men slutter 22:15 —
        og lå likevel som nummer tre. `til_tid` er andre sorteringsledd."""
        run_node(self.harness, self.VINDU + """
            const a = {fra_tid: '2026-09-04T17:00:00',
                       til_tid: '2026-09-05T03:00:00', navn: ''};
            const kort = {fra_tid: '2026-09-04T17:00:00',
                          til_tid: '2026-09-04T22:15:00', navn: ''};
            assert(_skiftrekkefolge(kort, a) < 0,
                   'det som slutter foerst skal staa foerst');
            assert(_skiftrekkefolge(a, kort) > 0, 'og motsatt vei');
        """)

    def test_sorteringen_er_stabil_paa_navn_til_slutt(self):
        run_node(self.harness, self.VINDU + """
            const b = {fra_tid: '2026-09-04T17:00:00',
                       til_tid: '2026-09-05T03:00:00', navn: 'Bodil'};
            const a = {fra_tid: '2026-09-04T17:00:00',
                       til_tid: '2026-09-05T03:00:00', navn: 'Anne'};
            assert(_skiftrekkefolge(a, b) < 0, 'navn avgjoer uavgjort');
        """)

    def test_lista_er_gruppert_paa_ressurs(self):
        """Den som leser lista står ved bilen og spør «hvem er her?».
        Korpset er et kjennetegn ved personen, ikke et sted."""
        ut = self._ut()
        for navn in ('Samleplass', 'Ambulanse 1', 'Ambulanse 2'):
            with self.subTest(ressurs=navn):
                self.assertIn(f'<h3>{navn}', ut)

    def test_ressursene_kommer_i_gruppenes_rekkefolge(self):
        ut = self._ut()
        self.assertLess(ut.index('<h3>Samleplass'), ut.index('<h3>Ambulanse 1'))
        self.assertLess(ut.index('<h3>Ambulanse 1'), ut.index('<h3>Ambulanse 2'))

    def test_korpset_er_en_kolonne_ikke_en_overskrift(self):
        ut = self._ut()
        self.assertIn('<th>Korps</th>', ut)
        self.assertNotIn('<h3>Haugesund', ut)

    def test_ledig_plass_viser_korpset_den_er_satt_av_til(self):
        """En ledig plass har ingen person, men kan være reservert. Uten dette
        står de reserverte plassene som «—» og reservasjonen er usynlig der
        den skal brukes.

        **KARM finnes bare på de ledige plassene** — de bemannede radene er
        HGSD. Det er med vilje: en test som lette etter HGSD ville vært grønn
        uansett, siden de bemannede radene bærer det. Funnet ved
        mutasjonstesting.
        """
        ut = self._ut()
        self.assertIn('KARM', ut)
        self.assertIn('HGSD', ut, 'og personens eget korps står der fortsatt')

    def test_ressurs_uten_skift_tas_ikke_med(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            globalThis.aktivListe.ressurser.push(
              {id: 30, navn: 'Tomjenta', gruppe_id: 2});
            console.log(mkOversikt());
        """)
        self.assertNotIn('Tomjenta', ut)

    def test_arkhodet_teller_ledige_plasser(self):
        """Tallet man planlegger etter, øverst på arket."""
        self.assertIn('3 ledige plasser', self._ut())


class EnkeltgruppeTests(SimpleTestCase):
    """Noen grupper finnes i ett eksemplar.

    Andrés poeng 30. aug. 2026: samleplassen og KO er samlingspunkt for flere
    korps, ikke flåter. En «Ny samleplass»-knapp inviterer til å lage noe som
    ikke finnes.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkGruppe', 'mkRessurs', '_radklasse',
                        '_stempelknapper', 'kanStemple', 'iDrift',
                        '_rolleValg', '_plassKorps', '_skiftrekkefolge',
                        '_fyllValgFor', '_varighet', 'mkGruppekurve',
                        '_posterIGruppe', '_mkEnKurve', '_tegnforklaring',
                        '_timesteg', '_toppunkt', '_vaktensSpenn',
                        '_bemanningPerTime', 'rollerForGruppe', '_iso16',
                        '_posterFor', '_ressurserIGruppe',
                        '_grupperMedRessurser', '_d', '_kl', '_dag',
                        '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanLede',
                        'kanBemanne', 'gruppaHarPlass')),
    )
    VINDU = ("globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")
    LISTE = """
        globalThis.aktivListe = {
          vaktliste: {startet: '2026-10-03T08:00:00',
                      planlagt_slutt: '2026-10-03T12:00:00'},
          grupper: [{id: 1, navn: 'Samleplass', ikon: 'hospital',
                     flere_enheter: false},
                    {id: 2, navn: 'Ambulanse', ikon: 'truck',
                     flere_enheter: true}],
          ressurser: [], roller: [], mannskap: [], korps: [], vaktposter: []};
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _gruppe(self, gruppe, ressurser=''):
        import json
        return run_node(self.harness, self.VINDU + self.LISTE + f"""
            globalThis.aktivListe.ressurser = {ressurser or '[]'};
            console.log(mkGruppe({json.dumps(gruppe)}));
        """)

    RESSURS = ("[{id: 10, navn: 'Samleplass', gruppe_id: 1, "
               "gruppe_navn: 'Samleplass', ikon: 'hospital', korps_navn: '', "
               "enhet_navn: ''}]")

    def _harPlass(self, gruppe, ressurser=''):
        import json
        return run_node(self.harness, self.VINDU + self.LISTE + f"""
            globalThis.aktivListe.ressurser = {ressurser or '[]'};
            console.log(gruppaHarPlass({json.dumps(gruppe)}) ? 'JA' : 'NEI');
        """).splitlines()[0]

    def test_den_forste_enheten_kan_alltid_opprettes(self):
        """Uten dette ville en tom enkeltgruppe vært en blindvei.

        Fanen finnes ikke før gruppa har en ressurs, så veien inn til den
        første går gjennom nedtrekket i «Ny ressurs» — og det er
        `gruppaHarPlass()` som avgjør om gruppa står der.
        """
        self.assertEqual('JA', self._harPlass(
            {'id': 1, 'navn': 'Samleplass', 'flere_enheter': False}))

    def test_enkeltgruppa_forsvinner_fra_nedtrekket(self):
        """Skjulte vi bare knappen i fanen, kunne man fortsatt velge gruppa
        i nedtrekket — og da var regelen halvveis."""
        self.assertEqual('NEI', self._harPlass(
            {'id': 1, 'navn': 'Samleplass', 'flere_enheter': False},
            self.RESSURS))

    def test_flaaten_blir_staaende_i_nedtrekket(self):
        ressurs = ("[{id: 20, navn: 'Bil A', gruppe_id: 2, "
                   "gruppe_navn: 'Ambulanse', ikon: 'truck', korps_navn: '', "
                   "enhet_navn: ''}]")
        self.assertEqual('JA', self._harPlass(
            {'id': 2, 'navn': 'Ambulanse', 'flere_enheter': True}, ressurs))

    def test_knappen_forsvinner_naar_den_ene_staar_der(self):
        ut = self._gruppe({'id': 1, 'navn': 'Samleplass', 'ikon': 'hospital',
                           'flere_enheter': False}, self.RESSURS)
        self.assertIn('Samleplass', ut, 'enheten vises fortsatt')
        self.assertNotIn('Ny Samleplass', ut)

    def test_flaater_beholder_knappen(self):
        """«Ambulanse» rommer bil A, bil B og bil C — der gir knappen mening
        uansett hvor mange som alt står der."""
        ressurs = ("[{id: 20, navn: 'Bil A', gruppe_id: 2, "
                   "gruppe_navn: 'Ambulanse', ikon: 'truck', korps_navn: '', "
                   "enhet_navn: ''}]")
        ut = self._gruppe({'id': 2, 'navn': 'Ambulanse', 'ikon': 'truck',
                           'flere_enheter': True}, ressurs)
        self.assertIn('Ny Ambulanse', ut)

    def test_gruppe_uten_flagget_regnes_som_flaate(self):
        """Eldre data og nye grupper står uten feltet i klienten før neste
        lasting. Standarden må være «flere» — ellers forsvinner knappen på en
        ambulansegruppe fordi et felt manglet."""
        ressurs = ("[{id: 20, navn: 'Bil A', gruppe_id: 2, "
                   "gruppe_navn: 'Ambulanse', ikon: 'truck', korps_navn: '', "
                   "enhet_navn: ''}]")
        ut = self._gruppe({'id': 2, 'navn': 'Ambulanse', 'ikon': 'truck'},
                          ressurs)
        self.assertIn('Ny Ambulanse', ut)


class NyRessursSkjemaetTests(SimpleTestCase):
    """«Ny ressurs» spør bare om navn og gruppe.

    Reservert korps og enhetskobling sto i opprettelsesskjemaet, men hører
    hjemme ett nivå lavere: reservasjonen ligger på plassen, koblingen på den
    enkelte enheten. Å spørre om dem her ga et skjema man måtte fylle ut før
    man visste svaret — og verre: det så ut som gruppa *var* enheten.
    """

    HARNESS = ((VAKTLISTE_JS, ('opprettRessurs', 'apneNyRessurs', '_fyll',
                              'gruppaHarPlass', '_ressurserIGruppe')),
               (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')))

    PREAMBLE = """
      globalThis.sendtBody = null;
      globalThis.felter = {
        'ny-ressurs-navn': {value: ' Bil A '},
        'ny-ressurs-gruppe': {value: '2'},
        'ny-ressurs-korps': {value: '7'},
        'ny-ressurs-enhet': {value: '9'},
      };
      globalThis.document = {
        getElementById: (id) => felter[id] || null,
      };
      globalThis.bootstrap = {Modal: class { constructor() {} show() {} }};
      globalThis.aktivListe = {vaktliste: {id: 3}};
      globalThis.aktivFane = '';
      globalThis.withSubmitGuard = async (id, fn) => { await fn(); };
      globalThis._skjulFeil = () => {};
      globalThis._visFeil = (id, m) => { globalThis.feilmelding = m; };
      globalThis._lukkModal = () => {};
      globalThis.lastListe = async () => {};
      globalThis.apiFetch = async (url, opts) => {
        globalThis.sendtUrl = url;
        globalThis.sendtBody = JSON.parse(opts.body);
        return {ok: true, json: async () => ({status: 'ok', data: {gruppe_id: 2}})};
      };
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, snippet):
        return run_node(self.harness, snippet, preamble=self.PREAMBLE)

    def test_kroppen_baerer_bare_navn_og_gruppe(self):
        """Feltene finnes i stubben, så en kode som leser dem ville tatt dem
        med. Testen sier at ingen gjør det."""
        self._kjor("""
          await opprettRessurs();
          assert(sendtBody !== null, 'ingen forespørsel ble sendt');
          const nokler = Object.keys(sendtBody).sort().join(',');
          assert(nokler === 'gruppe_id,navn',
                 'skjemaet sendte mer enn navn og gruppe: ' + nokler);
          assert(sendtBody.navn === 'Bil A',
                 'navnet ble ikke trimmet: ' + JSON.stringify(sendtBody.navn));
        """)

    NEDTREKK = """
      felter['ny-ressurs-gruppe'].innerHTML = '';
      felter['ny-ressurs-tittel'] = {textContent: ''};
      felter['nyRessursModal'] = {};
      globalThis.aktivFane = '2';
      globalThis.aktivListe.grupper = [
        {id: 1, navn: 'Samleplass', er_aktiv: true, flere_enheter: false},
        {id: 2, navn: 'Ambulanse', er_aktiv: true, flere_enheter: true},
        {id: 3, navn: 'Utgatt', er_aktiv: false, flere_enheter: true}];
      globalThis.aktivListe.ressurser = [];
    """

    def test_enkeltgruppa_staar_i_nedtrekket_for_den_forste(self):
        self._kjor(self.NEDTREKK + """
          apneNyRessurs(2);
          const valg = felter['ny-ressurs-gruppe'].innerHTML;
          assert(/Samleplass/.test(valg),
                 'den forste samleplassen hadde ingen vei inn: ' + valg);
        """)

    def test_enkeltgruppa_forsvinner_naar_den_ene_staar_der(self):
        """M11: skjulte vi bare knappen i fanen, kunne man fortsatt velge
        gruppa her — og serveren var det eneste som sa nei."""
        self._kjor(self.NEDTREKK + """
          aktivListe.ressurser = [{id: 9, gruppe_id: 1}];
          apneNyRessurs(2);
          const valg = felter['ny-ressurs-gruppe'].innerHTML;
          assert(!/Samleplass/.test(valg),
                 'samleplassen sto igjen i nedtrekket: ' + valg);
          assert(/Ambulanse/.test(valg),
                 'flaaten forsvant ogsaa: ' + valg);
        """)

    def test_utgaatt_gruppe_er_fortsatt_ute(self):
        self._kjor(self.NEDTREKK + """
          apneNyRessurs(2);
          assert(!/Utgatt/.test(felter['ny-ressurs-gruppe'].innerHTML),
                 'en deaktivert gruppe kunne velges');
        """)

    def test_navnet_er_fortsatt_paakrevd(self):
        self._kjor("""
          felter['ny-ressurs-navn'].value = '   ';
          await opprettRessurs();
          assert(sendtBody === null, 'en navnløs ressurs ble sendt til serveren');
          assert(/navn/i.test(globalThis.feilmelding || ''),
                 'brukeren fikk ingen forklaring: ' + globalThis.feilmelding);
        """)


class MannskapsfanenTests(SimpleTestCase):
    """Registeret er en fane på planleggingssiden (30. aug. 2026).

    Det lå på /vaktliste/registre/, og et klikk dit kostet deg plassen i
    planleggingen — mens mannskap og ressurser er nettopp de to man veksler
    mellom. Testene her dekker veiene *inn*: fanen, den tomme tilstanden, og
    vinduet som må åpne seg før den første vaktlista finnes.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkMannskap', '_personKolonne', '_passerPersonsok',
                        '_sorterMannskap', 'kanRedigerePerson',
                        'tegnPanel', 'apneVakt', '_apneModal',
                        '_skjulFeil', '_nivaa', 'visFane', '_erAdmin',
                        'kanSkriveAlt', 'kanSkriveNoe', 'kanLede')),
    )
    VINDU = ("globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.MANNSKAP = 'mannskap';\n"
             "globalThis.TILSTEDE = 'tilstede';\n"
            "globalThis.TILSTEDE = 'tilstede';\n"
             "globalThis.OVERSIKT = 'oversikt';\n"
             "globalThis.IKKE_PLASSERT = 'ikke-plassert';\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    KARI = ("{id: 1, navn: 'Kari', korps_id: 1, korps_navn: 'Haugesund', "
            "korps_kort: 'HGSD', kompetanser: [], alle_kompetanser: [], "
            "telefon: '', brukernavn: '', er_aktiv: true, i_bruk: 0}")

    def _mannskap(self, register):
        return run_node(self.harness, self.VINDU + f"""
            globalThis.personsok = '';
            globalThis.personSortKol = 'korps';
            globalThis.personSortStigende = true;
            globalThis.document = {{ getElementById: () => null }};
            globalThis.register = {register};
            console.log(mkMannskap());
        """)

    def test_uten_korps_peker_knappen_paa_korps(self):
        """Korpset er badgen, og uten ett kan ingen person opprettes. En
        «Nytt mannskap»-knapp som i stedet åpner korpsvinduet er en knapp man
        klikker på én gang og aldri stoler på igjen."""
        ut = self._mannskap("{korps: [], mannskap: []}")
        self.assertIn('data-action="apneVerdier" data-arg="korps"', ut)
        self.assertNotIn('apneNyPerson', ut)
        self.assertIn('Ingen korps', ut)

    def test_med_korps_men_uten_folk_ber_om_folk(self):
        ut = self._mannskap("{korps: [{id: 1, navn: 'HGSD'}], mannskap: []}")
        self.assertIn('apneNyPerson', ut)
        self.assertNotIn('data-arg="korps"', ut)

    def test_registeret_som_ikke_er_hentet_enda_sier_fra(self):
        """Fanen tegnes før svaret er inne. Uten dette kastet byggeren på
        `register.mannskap` og panelet ble stående tomt uten forklaring."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.register = null;
            console.log(mkMannskap());
        """)
        self.assertIn('Henter', ut)

    def test_soekefeltet_vises_bare_i_mannskapsfanen(self):
        """Det ligger utenfor panelet (ellers mister det fokus ved hvert
        tastetrykk), så det er `tegnPanel()` som må skjule det."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.register = null;
            globalThis.aktivListe = null;
            const felter = {
              'vl-verktoy': {klasser: [], classList: {
                toggle(k, paa) { felter['vl-verktoy'].klasser.push(paa); }}},
              'vl-panel': {innerHTML: ''},
            };
            globalThis.document = { getElementById: (id) => felter[id] || null };

            globalThis.aktivFane = 'mannskap';
            tegnPanel();
            globalThis.aktivFane = 'oversikt';
            tegnPanel();
            console.log(JSON.stringify(felter['vl-verktoy'].klasser));
        """)
        self.assertIn('[false,true]', ut,
                      'skjult i mannskapsfanen, eller synlig i de andre')

    def test_fanen_henter_registeret_forste_gang(self):
        """M14: uten hentingen står fanen på «Henter registeret…» for alltid.
        Den er lat med vilje — registeret er globalt og koster ingenting å
        utsette til noen faktisk ber om det."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.register = null;
            globalThis.aktivListe = null;
            globalThis.aktivFane = 'oversikt';
            let hentet = 0;
            globalThis.lastRegister = () => { hentet += 1; };
            globalThis.tegnFaner = () => {};
            // `tegnPanel` er den ekte i dette harnesset og tegner seg tom mot
            // en DOM som ikke finnes.
            globalThis.document = { getElementById: () => null };
            globalThis.register = null;
            globalThis.personsok = '';
            globalThis.personSortKol = 'korps';
            globalThis.personSortStigende = true;

            visFane('mannskap');
            assert(hentet === 1, 'registeret ble ikke hentet: ' + hentet);

            globalThis.register = {korps: [], mannskap: []};
            visFane('mannskap');
            assert(hentet === 1, 'hentet paa nytt selv om det alt laa der');
        """)
        self.assertIn('OK', ut)

    def test_mannskapsfanen_tegnes_uten_vaktliste(self):
        """M15: sto sjekken på `aktivListe` først, var panelet tomt til den
        første vaktlista fantes — altså akkurat når man skal legge inn folk."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = null;
            globalThis.aktivFane = 'mannskap';
            globalThis.register = {korps: [{id: 1, navn: 'HGSD'}],
                                   mannskap: []};
            globalThis.personsok = '';
            globalThis.personSortKol = 'korps';
            globalThis.personSortStigende = true;
            const felter = {'vl-panel': {innerHTML: ''}};
            globalThis.document = { getElementById: (id) => felter[id] || null };
            tegnPanel();
            console.log(felter['vl-panel'].innerHTML);
        """)
        self.assertIn('apneNyPerson', ut,
                      'panelet sto tomt uten vaktliste')

    def test_innstillinger_apner_uten_vaktliste(self):
        """Korps og kompetanser bor i vinduet, og de er nettopp det man
        legger inn før den første vaktlista finnes. Sto vinduet stengt til
        da, var registrene uten vei inn."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.aktivListe = null;
            const felter = {
              'vakt-for-lista': {skjult: null, classList: {
                toggle(k, paa) { felter['vakt-for-lista'].skjult = paa; }}},
              'vakt-lengde-bolk': {skjult: null, classList: {
                add() { felter['vakt-lengde-bolk'].skjult = true; },
                toggle(k, paa) { felter['vakt-lengde-bolk'].skjult = paa; }}},
              'vakt-tittel': {textContent: ''},
              'vaktModal': {},
            };
            globalThis.document = { getElementById: (id) => felter[id] || null };
            let apnet = false;
            globalThis.bootstrap = {Modal: class { constructor() { apnet = true; }
                                                  show() {} }};
            apneVakt();
            assert(apnet === true, 'vinduet aapnet seg ikke uten vaktliste');
            assert(felter['vakt-for-lista'].skjult === true,
                   'vaktbolken ble staaende med tomme felter');
            assert(felter['vakt-lengde-bolk'].skjult === true,
                   'vaktas lengde uten en vakt aa sette den paa');
            assert(felter['vakt-tittel'].textContent === 'Innstillinger',
                   'tittelen sto igjen med forrige vakts navn');
        """)
        self.assertIn('OK', ut)


class TidsfeltenesSteglengdeTests(SimpleTestCase):
    """Fem minutter, ikke ett (30. aug. 2026).

    Andrés punkt: `datetime-local` steger ett minutt som standard, så
    piltastene trengte tolv trykk for et kvarter. En vakt planlegges ikke på
    minuttet. `step="300"` er et multiplum av 60, så nettleseren legger *ikke*
    til et sekundsegment — hadde steget vært under et minutt, hadde feltet
    fått en kolonne til.

    Regelen, ikke tallet: *hvert* `datetime-local` på sida skal ha steget. Et
    nytt felt uten det er ett felt som oppfører seg annerledes enn de andre.
    """

    def _mal(self):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
                / 'index.html').read_text(encoding='utf-8')

    def test_hvert_tidsfelt_i_malen_steger_fem_minutter(self):
        felt = re.findall(r'<input[^>]*type="datetime-local"[^>]*>', self._mal())
        self.assertTrue(felt, 'fant ingen tidsfelt — leser testen riktig mal?')
        uten = [f for f in felt if 'step="300"' not in f]
        self.assertEqual(uten, [], f'{len(uten)} tidsfelt uten femminutterssteg')

    def test_cella_i_ressurstabellen_steger_ogsaa(self):
        """Den bygges i JS og fanges ikke av malsøket over — og det er den
        man taster flest ganger."""
        kropp = extract_function(read_js(VAKTLISTE_JS), 'mkRessurs')
        self.assertIn('type="datetime-local" step="300"', kropp)

    def test_steget_er_et_helt_minutt(self):
        """Et steg under 60 sekunder gir feltet et sekundsegment, altså en
        kolonne til å tabbe seg gjennom."""
        for kilde in (self._mal(), read_js(VAKTLISTE_JS)):
            for verdi in re.findall(r'step="(\d+)"', kilde):
                with self.subTest(step=verdi):
                    self.assertEqual(int(verdi) % 60, 0)


class NyVaktpostFyllerDatoenTests(SimpleTestCase):
    """Datoen står der på forhånd, hentet fra **vaktas start**.

    Andrés punkt 30. aug. 2026: feltet skal være som før — samme native
    velger, samme visning — men aldri tomt, så man taster fire siffer for
    klokkeslettet i stedet for tolv for hele datoen.

    **Vaktas start, ikke klokka nå.** En oktobervakt planlegges i august, og
    «i dag» er da et årstall på avveie.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('apneVaktpost', '_settTid', '_iso16', '_d',
                        '_fyll', '_skjulFeil', '_vaktpostModusSkifte',
                        'rollerForGruppe')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    OPPSETT = """
        globalThis.aktivListe = {
          vaktliste: {id: 3, startet: '2026-10-03T08:00:00'},
          ressurser: [{id: 10, navn: 'Bil A', gruppe_id: 2}],
          roller: [], vaktposter: [],
        };
        const felter = {};
        ['ny-vaktpost-tittel', 'ny-vaktpost-mannskap', 'ny-vaktpost-antall',
         'ny-vaktpost-fra', 'ny-vaktpost-til', 'ny-vaktpost-rolle',
         'ny-vaktpost-antall-rad', 'ny-vaktpost-feil'].forEach((id) => {
          felter[id] = {value: '', innerHTML: '', textContent: '',
                        classList: {toggle() {}, add() {}, remove() {}}};
        });
        felter.nyVaktpostModal = {dataset: {}};
        globalThis.document = {getElementById: (id) => felter[id] || null};
        globalThis.bootstrap = {Modal: class { constructor() {} show() {} }};
    """

    def test_begge_feltene_baerer_vaktas_startdato(self):
        run_node(self.harness, self.OPPSETT + """
            apneVaktpost(10);
            assert(felter['ny-vaktpost-fra'].value === '2026-10-03T08:00',
                   'fra: ' + felter['ny-vaktpost-fra'].value);
            assert(felter['ny-vaktpost-til'].value === '2026-10-03T08:00',
                   'til: ' + felter['ny-vaktpost-til'].value);
        """)

    def test_datoen_er_vaktas_og_ikke_dagens(self):
        """Den skarpe kanten: en vakt planlegges måneder i forveien, så
        `new Date()` ville satt feil år i hvert eneste skift."""
        run_node(self.harness, self.OPPSETT + """
            apneVaktpost(10);
            // Vakta starter 3. oktober. Kjoerer testen en annen dag — og det
            // gjoer den alltid, med mindre man er uheldig — vil et felt som
            // foelger klokka ha en annen dato enn denne.
            const idag = new Date().toISOString().slice(0, 10);
            assert(idag !== '2026-10-03', 'testen kan ikke skille i dag');
            assert(felter['ny-vaktpost-fra'].value.startsWith('2026-10-03'),
                   'fra fulgte ikke vakta: ' + felter['ny-vaktpost-fra'].value);
        """)

    def test_vinduet_baerer_ikke_forrige_ressurs_tider(self):
        """Feltene sto urørt ved åpning, så de bar tidene fra forrige gang
        vinduet var åpent — på en annen bil, i en annen gruppe."""
        run_node(self.harness, self.OPPSETT + """
            felter['ny-vaktpost-fra'].value = '2026-10-04T22:15';
            felter['ny-vaktpost-til'].value = '2026-10-05T03:00';
            apneVaktpost(10);
            assert(felter['ny-vaktpost-fra'].value === '2026-10-03T08:00',
                   'gammel fra-tid ble staaende: '
                   + felter['ny-vaktpost-fra'].value);
            assert(felter['ny-vaktpost-til'].value === '2026-10-03T08:00',
                   'gammel til-tid ble staaende: '
                   + felter['ny-vaktpost-til'].value);
        """)

    def test_vakt_uten_starttid_gir_tomme_felter(self):
        """Ingen dato er bedre enn en gjettet dato."""
        run_node(self.harness, self.OPPSETT + """
            aktivListe.vaktliste.startet = null;
            apneVaktpost(10);
            assert(felter['ny-vaktpost-fra'].value === '',
                   'fikk en dato fra ingenting: '
                   + felter['ny-vaktpost-fra'].value);
        """)


class StemplingsnavnTests(SimpleTestCase):
    """De fire knappene og de fire endepunktene skal ikke kunne gli fra
    hverandre.

    Klienten har én `data-action` per overgang, ikke én generisk med
    overgangen i et attributt — klikkdelegeringen i `portal-utils.js` sender
    ett argument, og å utvide den for én sides skyld ville rørt hver side i
    portalen. Prisen er to lister med samme innhold, og den prisen betales
    her.
    """

    def _klientkart(self):
        """`STEMPLINGER`-objektet i vaktliste.js, som Python-dict."""
        src = read_js(VAKTLISTE_JS)
        blokk = src[src.index('const STEMPLINGER = {'):]
        blokk = blokk[:blokk.index('};')]
        return dict(re.findall(r"(\w+):\s*'([^']+)'", blokk))

    def test_klienten_kjenner_alle_serverens_overganger(self):
        from . import services
        self.assertEqual(
            set(self._klientkart().values()), set(services.STEMPLINGER),
            'klientens stemplinger og serverens er ikke de samme')

    def test_hver_klienthandling_finnes_som_funksjon(self):
        """En `data-action` uten funksjon er en knapp som ikke gjør noe —
        klikkdelegeringen returnerer stille når navnet ikke finnes."""
        src = read_js(VAKTLISTE_JS)
        for navn in self._klientkart():
            with self.subTest(handling=navn):
                self.assertIn(f'function {navn}(', src)

    def test_knappene_bruker_de_navnene(self):
        kropp = extract_function(read_js(VAKTLISTE_JS), '_stempelknapper')
        for navn in self._klientkart():
            with self.subTest(handling=navn):
                self.assertIn(f"'{navn}'", kropp)


class DriftflatenTests(SimpleTestCase):
    """Stemplene i raden, og «Tilstede nå»."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_stempelknapper', '_radklasse', 'kanStemple',
                        'iDrift', 'kanSkriveAlt', '_nivaa', '_erAdmin',
                        'mkTilstede', '_tilstede', '_kl', '_d', '_dag',
                        '_tidsspenn', '_sammeDag')),
    )
    DAGER = ("globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _knapper(self, vp, *, drift=True, nivaa='skriv_full', admin=False):
        import json
        ut = run_node(self.harness, self.DAGER + f"""
            globalThis.window = {{ MODUL_TILGANG: {{
              vaktliste: '{nivaa}', admin: {str(admin).lower()} }} }};
            globalThis.aktivListe = {{vaktliste: {{i_drift: {str(drift).lower()}}}}};
            console.log('[' + _stempelknapper({json.dumps(vp)}) + ']');
        """)
        # `run_node` skriver «OK» til slutt. Klammene rundt gjør at en tom
        # streng er noe man kan se, framfor en linje som mangler.
        return ut[ut.index('['):ut.rindex(']') + 1]

    POST = {'id': 5, 'ledig': False, 'navn': 'Kari',
            'mott_at': None, 'av_vakt_at': None, 'tilstede': False}

    def test_uten_stempel_tilbys_bare_mott(self):
        """Raden er i nøyaktig én tilstand. «Av vakt» på en som ikke har møtt
        er en knapp som bare kan gi en feilmelding."""
        ut = self._knapper(self.POST)
        self.assertIn('stemplMott', ut)
        self.assertNotIn('stemplAvVakt', ut)
        self.assertIn('Møtt', ut)

    def test_etter_mott_tilbys_av_vakt_og_angre(self):
        ut = self._knapper({**self.POST, 'mott_at': '2026-10-03T08:00:00',
                            'tilstede': True})
        self.assertIn('stemplAvVakt', ut)
        self.assertIn('angreMott', ut)
        self.assertNotIn('stemplMott"', ut)

    def test_etter_av_vakt_staar_tidspunktet_og_en_angre(self):
        ut = self._knapper({**self.POST, 'mott_at': '2026-10-03T08:00:00',
                            'av_vakt_at': '2026-10-03T16:00:00'})
        self.assertIn('angreAvVakt', ut)
        self.assertIn('16:00', ut)

    def test_utenfor_drift_finnes_ingen_stempler(self):
        """Innsjekk er stengt i planlegging — knappen ville ført til 409."""
        self.assertEqual('[]', self._knapper(self.POST, drift=False))

    def test_korpsforeren_ser_ingen_stempler(self):
        """Avklaring 11.3, speilet i grensesnittet. Serveren nekter uansett,
        men en knapp som fører til en vegg er verre enn ingen knapp."""
        self.assertEqual(
            '[]', self._knapper(self.POST, nivaa='skriv_handling'))

    def test_ledig_plass_har_ingen_aa_stemple(self):
        self.assertEqual(
            '[]', self._knapper({**self.POST, 'ledig': True}))

    def _radklasse(self, vp, drift=True):
        import json
        return run_node(self.harness, f"""
            globalThis.aktivListe = {{vaktliste: {{i_drift: {str(drift).lower()}}}}};
            console.log('[' + _radklasse({json.dumps(vp)}) + ']');
        """).splitlines()[0]

    def test_tilstede_merkes_paa_raden(self):
        self.assertIn('vl-tilstede', self._radklasse(
            {**self.POST, 'tilstede': True}))

    def test_avgatt_merkes_annerledes(self):
        ut = self._radklasse({**self.POST, 'av_vakt_at': '2026-10-03T16:00:00'})
        self.assertIn('vl-avgatt', ut)

    def test_ledig_plass_beholder_sin_egen_klasse(self):
        """Bakgrunnen bærer allerede «ledig plass». To fargekoder i samme
        flate blir til ingen."""
        self.assertIn('vl-ledig', self._radklasse({**self.POST, 'ledig': True}))

    def test_planlegging_farger_ingenting(self):
        self.assertEqual('[]', self._radklasse(
            {**self.POST, 'tilstede': True}, drift=False))

    # ── «Tilstede nå» ────────────────────────────────────────────────────
    def _tilstede(self, poster, ressurser=None):
        import json
        return run_node(self.harness, self.DAGER + f"""
            globalThis.window = {{ MODUL_TILGANG: {{ admin: true }} }};
            globalThis.document = {{ getElementById: () => null }};
            globalThis.aktivListe = {{
              vaktliste: {{i_drift: true}},
              vaktposter: {json.dumps(poster)},
              ressurser: {json.dumps(ressurser or [
                  {'id': 1, 'navn': 'Bil A', 'ikon': 'truck'}])}}};
            console.log(mkTilstede());
        """)

    RAD = {'id': 1, 'ressurs_id': 1, 'ledig': False, 'navn': 'Kari',
           'korps_kort': 'HGSD', 'rolle': 'Sjåfør',
           'mott_at': '2026-10-03T08:04:00', 'av_vakt_at': None,
           'tilstede': True, 'fra_tid': '2026-10-03T08:00:00',
           'til_tid': '2026-10-03T16:00:00'}

    def test_tellingen_staar_over_lista(self):
        """I en evakuering teller man hoder mot et tall, og da skal tallet
        være det første man ser."""
        ut = self._tilstede([self.RAD, {**self.RAD, 'id': 2, 'navn': 'Ola'}])
        self.assertIn('vl-tilstedetall', ut)
        self.assertIn('>2</div>', ut)
        self.assertLess(ut.index('vl-tilstedetall'), ut.index('Kari'))

    def test_bare_de_som_er_tilstede(self):
        """Definisjonen er knivskarp: møtt, og ikke gått av vakt."""
        ut = self._tilstede([
            self.RAD,
            {**self.RAD, 'id': 2, 'navn': 'Avgått', 'tilstede': False,
             'av_vakt_at': '2026-10-03T12:00:00'},
            {**self.RAD, 'id': 3, 'navn': 'Ikkemøtt', 'tilstede': False,
             'mott_at': None},
        ])
        self.assertIn('Kari', ut)
        self.assertNotIn('Avgått', ut)
        self.assertNotIn('Ikkemøtt', ut)

    def test_de_som_mangler_telles_ogsaa(self):
        """«3 satt opp, 1 tilstede» er tallet man handler på — hvor mange
        som gjenstår er halve spørsmålet ved et skiftbytte."""
        ut = self._tilstede([
            self.RAD,
            {**self.RAD, 'id': 2, 'navn': 'Ola', 'tilstede': False,
             'mott_at': None},
        ])
        self.assertIn('2 satt opp', ut)
        self.assertIn('1 ikke møtt', ut)

    def test_tom_liste_forklarer_veien_videre(self):
        ut = self._tilstede([])
        self.assertIn('ressursfanene', ut)
        self.assertIn('>0</div>', ut)

    def test_navn_escapes(self):
        ut = self._tilstede([{**self.RAD, 'navn': '<img src=x onerror=alert(1)>'}])
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)
