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
    'mkRessurs', '_planrad', '_plancellene', '_blokklinje', '_dagoverskrift', '_probonoMerke',
    # Dagbolkene i gruppefanen (15. sep. 2026). En ny bygger som skanneren
    # ikke leser er nøyaktig det hullet denne lista finnes for.
    '_gruppedagbolker',
    'mkMittKorps', '_plassKorps',
    '_stempelknapper',
    '_driftrad',
    'mkBelastning',
    'mkTilstede',
    '_rolleValg',
    '_fyllValgFor',
    'mkOversikt', 'mkUtskriftsverktoy', '_utvalgstekst',
    'mkGruppekurve',
    '_mkEnKurve',
    'mkIkkePlassert',
)

ESCAPING_CALLS = ('escHtmlValue(', 'cellHtml(', '_escHtml(', 'escapeHtml(')

REVIEWED_INTERPOLATIONS = {
    '_plancellene(vp, r, kanRore)': 'markup fra en bygger som selv skannes her (regnearkradens celler, 12. sep. 2026)',
    'probono': 'tall utledet i JS',
    'probonoDel': 'markup bygget rett over, tallene escapet inni',
    # Utskriftsutvalget (12. sep. 2026): verktøylinja og utvalgslinja bygges
    # lokalt av byggere som selv skannes her, med navnene escapet inni.
    'verktoy': 'markup fra `mkUtskriftsverktoy`, som selv skannes her',
    'utvalgslinje': 'markup bygget lokalt, utvalgsteksten escapet inni',
    'grupper': 'optgroups bygget lokalt i samme funksjon, navn escapet inni',
    # Drift (fase 4). Knappene bygges lokalt, og bare når tilgangen og
    # tilstanden tillater dem — id-en er escapet inne i `_stempelknapper`.
    'rediger': 'markup bygget lokalt, skift-id-en escapet inni',
    '_stempelknapper(vp)': 'markup bygget lokalt av en bygger som selv skannes her',
    'naar(vp.av_vakt_at)': 'markup bygget lokalt, klokkeslettet escapet inni',
    'naar(vp.mott_at)': 'markup bygget lokalt, klokkeslettet escapet inni',
    # Offline drift (13. sep. 2026): kø-merket på stempeltida.
    'koKlasse': 'hardkodet CSS-klasse fra en ternær på `vp.i_ko`',
    "vp.i_ko ? ' title=\"Venter på å bli sendt\"' : ''": 'hardkodet attributt fra en ternær',
    "angre('angreMott', 'Angre møtt')":
        'markup bygget lokalt, id-en escapet inni',
    "angre('angreAvVakt', 'Angre av vakt')":
        'markup bygget lokalt, id-en escapet inni',
    "knapp('stemplAvVakt', 'Av vakt', 'btn-outline-warning', 'box-arrow-right')":
        'markup bygget lokalt, id-en escapet inni',
    # Tidsblokker (11. sep. 2026): summene bygges lokalt av `_tall`, som
    # bare kan gi sifre og komma — og escapes uansett inni.
    'timer': 'markup bygget lokalt, tallet escapet inni',
    '_probonoMerke(vp)': 'hardkodet merke fra en ternær, ingen data i seg',
    'hvem': 'nedtrekk fra `_fyllValgFor` (skannes her) eller escapet navn med merke',
    'alleMerke': 'hardkodet selected-attributt fra en ternær',
    # Dagoverskriften bygger ren tekst i `tekst`, som escapes ved innsetting:
    'DAGER_LANGE[d.getDay()]': 'ukedag fra en lokal, hardkodet liste',
    'd.getDate()': 'tall fra en Date',
    'mnd': 'månedsnavn fra `MND`, en hardkodet liste på sida',
    'sumTimer': 'markup bygget lokalt, tallet escapet inni',
    'tabellklasse': 'hardkodet CSS-klasse fra en ternær',
    # Planleggingstall (fase 5). Tallene kommer fra serverens beregning og
    # settes med escHtmlValue; markupen bygges lokalt i samme funksjon.
    'hode': 'markup bygget lokalt i samme funksjon',
    'lengste': 'markup bygget lokalt, tallet escapet inni',
    'hvile': 'markup bygget lokalt, tallet escapet inni',
    'faktisk': 'markup bygget lokalt, tallet escapet inni',
    'g.maks_skift_timer': 'går inn som ren tekst til varsel(), som escaper '
                          'hele strengen ved innsetting — og er uansett et '
                          'PositiveSmallIntegerField',
    'g.min_hvile_timer': 'samme som over',
    'langeSkift': 'markup bygget lokalt av varsel(), tallene escapet inni',
    'korteHviler': 'markup bygget lokalt av varsel(), tallene escapet inni',
    'ingenVarsler': 'hardkodet tekst fra en ternær',
    'grenseknapp': 'markup bygget lokalt, ingen data i seg',
    'faktiskHode': 'hardkodet overskrift fra en ternær',
    'faktiskTall': 'tallet escapet, eller en hardkodet strek',
    'hvileklasse': 'hardkodet CSS-klasse fra en ternær',
    'lengsteklasse': 'hardkodet CSS-klasse fra en ternær',
    'tabellhode': 'markup bygget lokalt: to faste kolonneoppsett, ingen data',
    # Sammenslåtte ressurskort (15. sep. 2026): vippeknappen og tabellen —
    # eller sammendraget i stedet for den — bygges begge i `mkRessurs()`
    # rett over, med id, tilstand og tall escapet inni.
    'vippe': 'markup bygget lokalt, id og tilstand escapet inni',
    # Gruppefanens dagbolker: kortene er `mkRessurs()`, som selv skannes her,
    # og dagtittelen ved siden av er escapet med `escapeHtml(_dagtekst(...))`.
    'kort': 'markup fra `mkRessurs()`, som selv skannes her',
    "tomme.map((r) => mkRessurs(r, ressursErApen(r), [])).join('')":
        'markup fra `mkRessurs()`, som selv skannes her',
    'tabell': 'markup bygget lokalt: tabellen, eller sammendraget som escapes inni',
    'kolonner': 'to bruk, begge uten data: colspan-tallet i mkRessurs og '
                'colgroup-markupen i mkBelastning, begge bygget lokalt',
    'navn': 'ternær: escapet personnavn, eller «Ledig plass» som markup',
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
    # Dagbolkene i «Oversikt» (15. sep. 2026): ressurstabellene for én dag,
    # bygget av `ressursdeler()` i samme funksjon. Radene inni går gjennom
    # `rad()` og `_blokkrader`, som begge skannes her; dagtittelen ved siden
    # av er escapet med `escapeHtml(_dagtekst(...))`.
    "ressursdeler(perRessursDag(dag.poster)).join('')":
        'markup bygget lokalt i samme funksjon',
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
        self.assertIn('vaktliste-kjerne.js', lastet,
                      'sidens JS er delt i fem siden 14. sep. 2026 — kjernen først')

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
        (VAKTLISTE_JS, ('mkRessurs', 'ressursErApen', '_radklasse', '_stempelknapper',
                        'kanStemple', 'iDrift', '_rolleValg',
                        'rollerForGruppe', '_fyllValgFor', 'opptattPaaPlassen', '_varighet',
                        'mkRolleRad', 'mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utvalgstekst', '_skiftrekkefolge',
                        '_planrad', '_plancellene', '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader', 'kanBemannePlass',
                        '_mittKorpsId', '_synligePoster',
                        '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke',
                        '_sumTimer', '_skifttimer', '_tall', '_telling',
                        '_mkEnKurve', 'mkGruppekurve', '_posterIGruppe',
                        'mkGruppe', '_gruppedagbolker', '_plassKorps', '_tegnforklaring',
                        '_timesteg', '_ressurserIGruppe',
                        '_grupperMedRessurser',
                        '_posterPerGruppe', '_vaktensSpenn',
                        'mkIkkePlassert', 'tegnFaner', '_fanerad',
                        '_mannskapsfane', '_tilstede', '_posterFor',
                        '_ikkePlassert', '_tidsspenn', '_vaktspenn',
                        '_bemanningPerTime', '_iso16', '_d', '_kl', '_dag',
                        '_sammeDag', '_nivaa', '_erAdmin', 'kanSkriveAlt',
                        'kanLede', 'kanBemanne', 'kanRoreRad')),
    )

    #: Byggerne spør om tilgang fra fase 3. Node har ingen `window`, så den
    #: stubbes — og med admin, slik at *alle* knappene bygges. Escaping-testene
    #: skal se mest mulig markup; hvem som får se hva er `tests_tilgang.py`
    #: sitt bord.
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {self._liste()};
            console.log(mkRessurs({{
              id: 1, navn: 'Lag 1', ikon: '" onload="alert(1)',
              gruppe_navn: 'Lag', korps_navn: '', enhet_navn: ''
            }}));
        ''')
        self.assertNotIn('onload="alert(1)"', ut)

    def test_mannskapsnavn_i_oversikten_escapes(self):
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.MITT_KORPS = 'mitt-korps';
            globalThis.korpsfilter = null; globalThis.utskriftRessurs = null;
            globalThis.MANNSKAP = 'mannskap';
            globalThis.TILSTEDE = 'tilstede';
            globalThis.BELASTNING = 'belastning';
            globalThis.belastning = null;
            globalThis.register = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.MITT_KORPS = 'mitt-korps';
            globalThis.korpsfilter = null; globalThis.utskriftRessurs = null;
            globalThis.MANNSKAP = 'mannskap';
            globalThis.TILSTEDE = 'tilstede';
            globalThis.BELASTNING = 'belastning';
            globalThis.belastning = null;
            globalThis.register = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
    'merkelapper': 'markup bygget lokalt, hvert kompetansenavn escapet inni',
    'konto': 'markup bygget lokalt, brukernavnet escapet inni',
    'epost': 'markup bygget lokalt, adressen escapet inni og et ikon',
    'kontoCelle': 'tom streng eller <td> med `konto`, som er escapet over',
    '_erAdmin() ? 8 : 7': 'tall fra en ternær',
    '_erAdmin() ? \'<col style="width: 9%">\' : \'\'': 'intern markup fra en ternær',
    "_erAdmin() ? '<th>Konto</th>' : ''": 'intern markup fra en ternær',
    'kolonner': 'intern <colgroup>-markup valgt av en ternær',
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
        self.assertIn('vaktliste-kjerne.js', lastet,
                      'sidens JS er delt i fem siden 14. sep. 2026 — kjernen først')

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
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
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
        fordeling: kompetanse trenger mest, korps minst. Kontokolonnen finnes
        bare for global admin (12. sep. 2026), så andelene må summere til 100
        i begge utgaver."""
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        harness = build_harness(RegistersidenEscapingOppforselTests.HARNESS)
        for admin in (True, False):
            with self.subTest(admin=admin):
                ut = run_node(harness, RegistersidenEscapingOppforselTests.VINDU + f"""
                    globalThis.window = {{ MODUL_TILGANG: {{ vaktliste: 'skriv_full', admin: {str(admin).lower()} }} }};
                    globalThis.document = {{ getElementById: () => null }};
                    globalThis.register = {{ mannskap: [{{id: 1, navn: 'Kari', korps_id: 1, korps_navn: 'H', korps_kort: 'H',
                        kompetanser: [], alle_kompetanser: [], telefon: '', epost: '', user_id: null,
                        brukernavn: '', er_aktiv: true, notat: '', i_bruk: 0}}],
                        korps: [{{id: 1, navn: 'H', er_aktiv: true}}], kompetanser: [], kontoer: [] }};
                    console.log(mkMannskap());
                """)
                self.assertIn('<colgroup>', ut)
                andeler = [int(a) for a in re.findall(r'width:\s*(\d+)%', ut)]
                self.assertEqual(len(andeler), 8 if admin else 7, 'én bredde per kolonne')
                self.assertEqual(sum(andeler), 100, f'andelene skal summere til 100, fikk {andeler}')
                self.assertEqual('<th>Konto</th>' in ut, admin, 'kontokolonnen er admin sin')

    def test_kompetansecella_bryter_framfor_aa_flyte_ut(self):
        """Brytningen ligger på wrapperen *inne* i cella (11. sep. 2026) —
        `display: flex` rett på `<td>`-en var det som tok kompetansekolonnen
        ut av kolonnesporet. `TabellcellersLayoutTests` vokter det siste."""
        css = self._css()
        blokk = css[css.index('.vlr-kompliste {'):css.index('.vlr-handling {')]
        self.assertIn('flex-wrap: wrap', blokk)
        kropp = extract_function(read_js(VAKTLISTE_JS), 'mkMannskap')
        self.assertIn('<div class="vlr-kompliste">', kropp)


class TidsvisningTests(SimpleTestCase):
    """Dato og dag, ikke bare klokkeslett.

    Feilen André meldte: et skift fra lørdag 20:00 til søndag 04:00 sto som
    «20:00–04:00», uten at noe sa at det krysset midnatt. Arrangementer varer
    flere dager, og da er klokkeslettet alene tvetydig.
    """

    HARNESS = (
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_sammeDag', '_tidsspenn',
                        '_vaktspenn', '_iso16', '_bemanningPerTime',
                        '_vaktensSpenn', '_varighet', '_skifttimer',
                        '_tall')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = { vaktposter: [] };
            assert(_bemanningPerTime().length === 0, 'tom liste');
        """)

    def test_urimelig_spenn_tegnes_ikke(self):
        """En feiltastet årstall ville ellers laget hundretusen søyler."""
        run_node(self.harness, """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = { vaktposter: [
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2099-10-03T08:00:00'},
            ]};
            assert(_bemanningPerTime().length === 0, 'skal gi opp, ikke henge');
        """)

    def test_for_langt_vaktspenn_faller_tilbake_paa_skiftene(self):
        """Kurven var «fullstendig vekke» på en vaktliste der vaktens start lå
        uker før slutten (André, 12. sep. 2026). Skiftene er fortsatt et spenn."""
        run_node(self.harness, """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-09-12T10:00:00', planlagt_slutt: '2026-10-04T02:00:00'},
              vaktposter: [
                {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T16:00:00'},
              ]};
            const p = _bemanningPerTime();
            assert(p.length === 8, 'åtte timer fra skiftet, fikk ' + p.length);
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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

    #: Tabellen har **to former** fra 30. aug. 2026: regnearket i planlegging
    #: og innsjekklista i drift. Byggeren har dermed to `<colgroup>` og to
    #: `<thead>`, i den rekkefølgen — drift først i ternæren.
    FORMER = ('drift', 'plan')

    def _blokker(self, monster):
        kropp = extract_function(read_js(VAKTLISTE_JS), 'mkRessurs')
        funn = re.findall(monster, kropp, re.S)
        self.assertEqual(len(funn), len(self.FORMER),
                         f'ventet én {monster} per form, fant {len(funn)}')
        return dict(zip(self.FORMER, funn))

    def _andeler(self, form='plan'):
        blokk = self._blokker(r'<colgroup>(.*?)</colgroup>')[form]
        return [int(a) for a in re.findall(r'width:\s*(\d+)%', blokk)]

    def _overskrifter(self, form='plan'):
        blokk = self._blokker(r'<thead>(.*?)</thead>')[form]
        return re.findall(r'<th>(.*?)</th>', blokk)

    def test_driftraden_er_planraden_med_stempelet_foran(self):
        """Snudd 12. sep. 2026 (André: «Kunne redigere mannskaper selv om vi
        er i drift modus»). Driftraden var en egen, smal form uten tidsfelt;
        nå er den planleggingsradens celler med innsjekken først, så raden
        kan rettes der den står også under drift."""
        kropp = _uten_kommentarer(
            extract_function(read_js(VAKTLISTE_JS), '_driftrad'))
        self.assertIn('_plancellene(', kropp)
        self.assertIn('_stempelknapper(', kropp)
        self.assertEqual(self._overskrifter('drift'),
                         ['Innsjekk'] + self._overskrifter('plan'))

    def test_drifttabellen_har_gulv_for_stempelet_i_tillegg(self):
        """Regnearkets `min-width` er satt for ni kolonner; drift har ti.
        Arver drifttabellen bare regnearkets gulv, klemmes tidsfeltene."""
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css'
               / 'vaktliste.css').read_text(encoding='utf-8')
        m = re.search(r'\.vl-tabell-drift\s*\{([^}]*)\}', css)
        self.assertIsNotNone(m, '.vl-tabell-drift mangler i stilarket')
        d = re.search(r'min-width:\s*([\d.]+)rem', m.group(1))
        self.assertIsNotNone(d, 'drifttabellen mangler egen min-width')
        self.assertGreater(float(d.group(1)), self._min_width_rem())

    def _drift_min_width_rem(self):
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css'
               / 'vaktliste.css').read_text(encoding='utf-8')
        blokk = re.search(r'\.vl-tabell-drift\s*\{([^}]*)\}', css).group(1)
        return float(re.search(r'min-width:\s*([\d.]+)rem', blokk).group(1))

    def test_tidskolonnene_rommer_feltet_ogsaa_i_drift(self):
        piksler = self._drift_min_width_rem() * 16
        andeler = self._andeler('drift')
        overskrifter = self._overskrifter('drift')
        for navn in self.TIDSKOLONNER:
            with self.subTest(kolonne=navn):
                bredde = piksler * andeler[overskrifter.index(navn)] / 100
                self.assertGreaterEqual(round(bredde), self.MIN_TIDSFELT_PX,
                                        f'«{navn}» blir {bredde:.0f} px i drift')

    def test_stempelet_staar_forst_i_drift(self):
        """Første utgave la det ytterst til høyre: 45 × 21 px, tusen piksler
        fra navnet, bak en sidescroll. Rekkefølgen er halve rettelsen."""
        self.assertEqual('Innsjekk', self._overskrifter('drift')[0])
        kropp = extract_function(read_js(VAKTLISTE_JS), '_driftrad')
        self.assertLess(kropp.index('vl-stempelcelle'), kropp.index('_plancellene('))

    def test_stempelknappen_er_stor_nok_til_en_tommel(self):
        """44 px er gulvet for et trykkmål man skal treffe mens man holder
        en telefon i den andre hånda."""
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css'
               / 'vaktliste.css').read_text(encoding='utf-8')
        blokk = css[css.index('.vl-stempel {'):css.index('.vl-stempelcelle')]
        m = re.search(r'min-height:\s*([\d.]+)rem', blokk)
        self.assertIsNotNone(m, '.vl-stempel mangler min-height')
        self.assertGreaterEqual(float(m.group(1)) * 16, 44,
                                'knappen er under gulvet for et trykkmål')
        self.assertIn('width: 100%', blokk, 'knappen skal fylle cella')

    def test_andelene_summerer_til_hundre(self):
        for form in self.FORMER:
            with self.subTest(form=form):
                andeler = self._andeler(form)
                self.assertEqual(
                    len(andeler), len(self._overskrifter(form)),
                    f'{form}: én bredde per kolonne')
                self.assertEqual(sum(andeler), 100, f'{form}: {andeler}')

    def test_planformens_andeler(self):
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
        """Klassene som står på `<td>` i ressurstabellen — radene bygges av
        tre byggere siden 11. sep. 2026, og alle tre leses."""
        src = read_js(VAKTLISTE_JS)
        klasser = set()
        # `mkMannskap` er med fra 11. sep. 2026: `.vlr-komp` hadde nettopp
        # denne feilen, og testen fant den ikke fordi den bare leste
        # ressurstabellen.
        for navn in ('mkRessurs', '_planrad', '_plancellene', '_driftrad', '_blokklinje',
                     'mkMannskap'):
            for treff in re.findall(r'<td class="([^"$]*)"',
                                    extract_function(src, navn)):
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


class IngentingHengerFastPaaTelefonenTests(SimpleTestCase):
    """På en telefon henger ingen kolonne fast (11. sep. 2026).

    André: merknadskolonnen fulgte med når tabellen rullet på mobilen, mens
    knappene ikke gjorde det — og han ville ikke ha noe som fulgte.
    Sticky-kolonnen ble laget for laptopen. Testen leser regelblokka for
    smale skjermer og krever at *begge* sticky-reglene slås av der — cella
    og hodet — så de ikke kan glippe hver for seg.
    """

    def _smal(self):
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css'
               / 'vaktliste.css').read_text(encoding='utf-8')
        m = re.search(r'@media \(max-width: 768px\) \{(.*?)\n\}', css, re.S)
        self.assertIsNotNone(m, 'fant ingen regelblokk for smale skjermer')
        return m.group(1)

    def test_cella_og_hodet_slippes_paa_smal_skjerm(self):
        blokk = self._smal()
        self.assertIn('.vl-handling', blokk)
        self.assertIn('thead th:last-child', blokk)
        self.assertIn('position: static', blokk)

    def test_paa_bred_skjerm_henger_den_fortsatt(self):
        """Regelen er for telefonen — laptopen beholder blyanten i syne."""
        from pathlib import Path
        from django.conf import settings
        css = (Path(settings.BASE_DIR) / 'static' / 'css'
               / 'vaktliste.css').read_text(encoding='utf-8')
        m = re.search(r'(?m)^\.vl-handling \{([^}]*)\}', css)
        self.assertIn('position: sticky', m.group(1))


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
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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

    HARNESS = ((VAKTLISTE_JS, ('_d', '_varighet', '_skifttimer', '_tall')),)

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
        (VAKTLISTE_JS, ('mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utvalgstekst', '_skiftrekkefolge', '_d', '_kl',
                        '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader', 'kanBemannePlass',
                        '_mittKorpsId', '_synligePoster',
                        '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke', '_sumTimer',
                        '_varighet', '_skifttimer', '_tall', '_telling',
                        '_dag', '_sammeDag', '_tidsspenn', '_vaktspenn',
                        '_ressurserIGruppe', '_grupperMedRessurser')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_oversikten_tegner_ingen_kurve(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
                        '_timesteg', '_tidsblokker', '_tidsspenn', '_sammeDag', '_skiftrekkefolge')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    #: To grupper, to ressurser, tre skift. Ambulansen har én ledig plass.
    LISTE = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
        self.assertIn('2 personell på det meste', ut)
        self.assertIn('0 personell på det meste', ut, 'ambulansen står tom')

    def test_ledige_plasser_telles_per_gruppe(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 1, navn: 'Samleplass'}));
            console.log(mkGruppekurve({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('Alle plasser fylt · 2 plasser dekket', ut)        # samleplassen
        self.assertIn('Ledige plasser: 1 · 0 plasser dekket', ut)    # ambulansen

    def test_ingen_grupper_gir_ingen_kurve(self):
        run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {vaktliste: {}, grupper: [],
                                     ressurser: [], vaktposter: []};
            const ut = mkGruppekurve({id: 1, navn: 'X'});
            // Ingen søyler — men heller ingen tom flate: kortet sier hva som
            // mangler (André, 12. sep. 2026: kurven var «fullstendig vekke»).
            assert(ut.indexOf('vl-stolpe') === -1, 'ingen søyler');
            assert(ut.indexOf('Kurven trenger vaktens start og slutt') !== -1, 'forklaring: ' + ut);
        """)


class TimeaksenTests(SimpleTestCase):
    """Klokkeslett under søylene, og toppunktet med tidspunkt.

    Andrés bestilling: «kjekt med timevisning slik at en lett kan se hvilke
    klokkeslett bemanningen er høyest». Å lese det av søylehøyder er å gjette.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_vaktensSpenn',
                        '_bemanningPerTime', '_mkEnKurve', '_timesteg', '_tidsblokker', '_tidsspenn', '_sammeDag', '_skiftrekkefolge')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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

    def test_bunnlinja_sier_hvor_mange_plasser_paa_det_meste(self):
        """«3 plasser på det meste» — ikke «topp 3 plasser kl. 10:00–12:00»,
        som André leste som noe han ikke forsto (12. sep. 2026)."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T12:00:00'},
              vaktposter: []};
            console.log(_mkEnKurve('Test', [
              {ledig: false, fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
              {ledig: false, fra_tid: '2026-10-03T10:00:00', til_tid: '2026-10-03T12:00:00'},
              {ledig: false, fra_tid: '2026-10-03T10:00:00', til_tid: '2026-10-03T12:00:00'}
            ]));
        """)
        self.assertIn('3 personell på det meste', ut)
        self.assertNotIn('topp 3', ut)
        self.assertIn('Alle plasser fylt', ut)

    def test_probono_tegnes_som_egen_del_av_soylen(self):
        """Probono i annen farge (André, 12. sep. 2026). Den er med i
        `antall` — søylen er like høy — men den øverste delen er grønn."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T10:00:00'},
              vaktposter: []};
            const p = _bemanningPerTime([
              {ledig: false, navn: 'Kari', fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00'},
              {ledig: false, navn: 'Ola', probono: true, fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00'},
              {ledig: true, navn: '', fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00'}]);
            assert(p[0].antall === 2 && p[0].probono === 1 && p[0].planlagt === 3, JSON.stringify(p[0]));
            console.log(_mkEnKurve('Test', [
              {ledig: false, navn: 'Kari', fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00'},
              {ledig: false, navn: 'Ola', probono: true, fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00'},
              {ledig: true, navn: '', fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T10:00:00'}]));
        """)
        # 2 av 3 bemannet: bemannet-delen 67 %, probono-delen 33 % som starter på 33 %.
        self.assertIn('class="vl-bemannet" style="height: 67%"', ut)
        self.assertIn('class="vl-probonodel" style="height: 33%; bottom: 33%"', ut)
        self.assertIn('(1 probono)', ut)
        self.assertIn('Probono</span>', ut, 'tegnforklaringen') if '_tegnforklaring' in ''.join(n for h in self.HARNESS for n in h[1]) else None

    def test_hodet_har_tre_tall_og_ikke_mer(self):
        """André, 12. sep. 2026: «Holder med ledige plasser: N og N plasser på
        det meste og N plasser dekket. Blir for mye clutter hvis ikke.»"""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {
              vaktliste: {startet: '2026-10-03T08:00:00',
                          planlagt_slutt: '2026-10-03T12:00:00'},
              vaktposter: []};
            console.log(_mkEnKurve('Test', [
              {ledig: false, navn: 'Kari', fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
              {ledig: true, navn: '', fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
              {ledig: true, navn: '', fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T12:00:00'},
              {ledig: true, navn: '', fra_tid: '2026-10-03T10:00:00', til_tid: '2026-10-03T12:00:00'}
            ]));
        """)
        self.assertIn('Ledige plasser: 3 · 1 plass dekket', ut)
        self.assertIn('1 personell på det meste', ut, 'folk, ikke plasser')
        self.assertNotIn('plasstimer', ut)
        self.assertNotIn('×', ut, 'ingen liste over skiftene')


class GruppekurveIFanenTests(SimpleTestCase):
    """Kurven står i fanen den gjelder.

    Å lete etter samleplassens bemanning under «Oversikt» mens man bemanner
    samleplassen, er ett skifte for mye.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_d', '_kl', '_dag', '_vaktensSpenn',
                        '_bemanningPerTime', '_posterPerGruppe',
                        '_mkEnKurve', '_timesteg',
                        '_tegnforklaring', '_posterIGruppe',
                        '_ressurserIGruppe', 'mkGruppekurve', '_tidsblokker', '_tidsspenn', '_sammeDag', '_skiftrekkefolge')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")
    LISTE = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
        self.assertIn('2 personell på det meste', ut)

    def test_ambulansefanen_viser_ambulansen(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            console.log(mkGruppekurve({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('Ambulanse', ut)
        self.assertNotIn('Samleplass', ut)
        self.assertIn('Ledige plasser: 1 · 0 plasser dekket', ut)

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
        self.assertIn('0 personell på det meste', ut, 'flat null')

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
                        '_mittKorpsId', '_synligePoster',
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
             "globalThis.MITT_KORPS = 'mitt-korps';\n"
             "globalThis.korpsfilter = null;\n"
            "globalThis.MANNSKAP = 'mannskap';\n"
            "globalThis.TILSTEDE = 'tilstede';\n"
            "globalThis.BELASTNING = 'belastning';\n"
            "globalThis.belastning = null;\n"
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
        (VAKTLISTE_JS, ('tegnFaner', '_fanerad', '_mannskapsfane', '_mittKorpsId',
                        '_synligePoster', 'iDrift', '_tilstede', 'mkGruppe', '_gruppedagbolker', '_grupperPaaDag', 'ressursErApen',
                        'mkRessurs', '_sumTimer', '_radklasse', '_stempelknapper', 'kanStemple',
                        '_rolleValg', '_skiftrekkefolge', '_fyllValgFor', 'opptattPaaPlassen',
                        '_varighet', '_skifttimer', '_tall', '_planrad', '_plancellene',
                        '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader',
                        'kanBemannePlass', '_dagnokkel', '_dagoverskrift', '_dagtekst',
                        '_probonoMerke', '_tidsspenn', '_telling', '_sammeDag',
                        '_driftrad', 'mkGruppekurve', '_mkEnKurve',
                        '_tegnforklaring', '_timesteg',
                        '_posterPerGruppe', '_vaktensSpenn', '_posterIGruppe',
                        '_plassKorps', '_bemanningPerTime', 'rollerForGruppe',
                        '_iso16', '_posterFor', '_ikkePlassert',
                        '_ressurserIGruppe', '_grupperMedRessurser', '_d', '_kl',
                        '_dag', '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanLede',
                        'kanBemanne', 'gruppaHarPlass', 'kanRoreRad')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n"
             "globalThis.aktivFane = 'oversikt';\n"
             "globalThis.OVERSIKT = 'oversikt';\n"
             "globalThis.IKKE_PLASSERT = 'ikke-plassert';\n"
             "globalThis.MITT_KORPS = 'mitt-korps';\n"
             "globalThis.korpsfilter = null;\n"
            "globalThis.MANNSKAP = 'mannskap';\n"
            "globalThis.TILSTEDE = 'tilstede';\n"
            "globalThis.BELASTNING = 'belastning';\n"
            "globalThis.belastning = null;\n"
            "globalThis.register = null;\n")

    #: To ambulanser i samme gruppe, én samleplass i en annen.
    LISTE = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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

    def test_i_drift_staar_kurven_under_ressursene(self):
        """Prosjektleder, 11. sep. 2026: «ved driftsmodus skal
        bemanningskurver til bunn». Stemplene er jobben da; kurven er
        fortsatt der, men under."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            aktivListe.vaktliste.i_drift = true;
            console.log(mkGruppe({id: 2, navn: 'Ambulanse'}));
        """)
        self.assertIn('vl-kurve', ut, 'kurven skal fortsatt tegnes')
        self.assertGreater(ut.index('vl-kurve'), ut.index('Ambulanse 2'),
                           'i drift står kurven under den siste ressursen')

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
        (VAKTLISTE_JS, ('mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utvalgstekst', '_skiftrekkefolge', '_d', '_kl',
                        '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader', 'kanBemannePlass',
                        '_mittKorpsId', '_synligePoster',
                        '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke', '_sumTimer',
                        '_varighet', '_skifttimer', '_tall', '_telling',
                        '_dag', '_sammeDag', '_tidsspenn', '_vaktspenn',
                        '_ressurserIGruppe', '_grupperMedRessurser')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")

    #: Andrés egne rader: tre skift som begynner 17:00, ett av dem kort.
    LISTE = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
        (VAKTLISTE_JS, ('mkGruppe', '_gruppedagbolker', '_grupperPaaDag', 'ressursErApen', 'mkRessurs', '_sumTimer', '_radklasse',
                        '_stempelknapper', 'kanStemple', 'iDrift',
                        '_rolleValg', '_plassKorps', '_skiftrekkefolge',
                        '_fyllValgFor', 'opptattPaaPlassen', '_varighet', '_skifttimer', '_tall',
                        '_planrad', '_plancellene', '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader', 'kanBemannePlass',
                        '_mittKorpsId', '_synligePoster',
                        '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke',
                        '_tidsspenn', '_sammeDag', 'mkGruppekurve', '_telling',
                        '_posterIGruppe', '_mkEnKurve', '_tegnforklaring',
                        '_timesteg', '_vaktensSpenn',
                        '_bemanningPerTime', 'rollerForGruppe', '_iso16',
                        '_posterFor', '_ressurserIGruppe',
                        '_grupperMedRessurser', '_d', '_kl', '_dag',
                        '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanLede',
                        'kanBemanne', 'gruppaHarPlass', 'kanRoreRad')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")
    LISTE = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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


class SammenslaatteRessurserTests(SimpleTestCase):
    """Ressurskortene kan slås sammen i gruppefanen (André, 14. sep. 2026).

    *«i hver ressursfane skal en kunne minimere lag/ambulanse osv. Og at alle
    ressursene i ressursgruppen er minimert som standard.»* — snevret
    15. sep. 2026 til **bare når gruppa har mer enn én**: en vakt med én
    ambulanse ville ellers kostet et klikk hver gang for å se det eneste som
    er der.

    En fane med ti ambulanser var ti regneark under hverandre. Gruppefanen har
    bemanningskurven øverst, og den *er* oversikten over gruppa — kortene under
    er detaljen.
    """

    HARNESS = EnkeltgruppeTests.HARNESS
    VINDU = EnkeltgruppeTests.VINDU

    #: To ambulanser og én samleplass, med skift på Bil A.
    LISTE = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
        globalThis.ressursApen = new Map();
        globalThis.rollerForGruppe = () => [];
        globalThis.aktivListe = {
          vaktliste: {startet: '2026-10-03T08:00:00',
                      planlagt_slutt: '2026-10-03T20:00:00', i_drift: false},
          grupper: [{id: 1, navn: 'Samleplass', ikon: 'hospital', flere_enheter: false},
                    {id: 2, navn: 'Ambulanse', ikon: 'truck', flere_enheter: true}],
          ressurser: [
            {id: 10, navn: 'Samleplass', gruppe_id: 1, gruppe_navn: 'Samleplass', ikon: 'hospital'},
            {id: 20, navn: 'Bil A', gruppe_id: 2, gruppe_navn: 'Ambulanse', ikon: 'truck'},
            {id: 21, navn: 'Bil B', gruppe_id: 2, gruppe_navn: 'Ambulanse', ikon: 'truck'}],
          roller: [], mannskap: [], korps: [],
          vaktposter: [
            {id: 1, ressurs_id: 20, ledig: false, navn: 'Kari', korps_kort: 'HGSD',
             rolle: '', merknad: '', fra_tid: '2026-10-03T08:00:00',
             til_tid: '2026-10-03T16:00:00'},
            {id: 2, ressurs_id: 20, ledig: true, navn: '', korps_kort: '',
             rolle: '', merknad: '', fra_tid: '2026-10-03T08:00:00',
             til_tid: '2026-10-03T16:00:00'}]};
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, snippet):
        return run_node(self.harness, self.VINDU + self.LISTE + snippet)

    # ── Standarden ───────────────────────────────────────────────────────
    def test_gruppe_med_en_ressurs_staar_apen(self):
        """Samleplassen er alene i gruppa si — ingenting å bla forbi."""
        self._kjor("""
            const r = aktivListe.ressurser.find((x) => x.id === 10);
            assert(ressursErApen(r) === true, 'den ene skal staa aapen');
        """)

    def test_gruppe_med_flere_ressurser_staar_sammenslaatt(self):
        self._kjor("""
            const a = aktivListe.ressurser.find((x) => x.id === 20);
            const b = aktivListe.ressurser.find((x) => x.id === 21);
            assert(ressursErApen(a) === false, 'Bil A skal vaere sammenslaatt');
            assert(ressursErApen(b) === false, 'Bil B skal vaere sammenslaatt');
        """)

    def test_valget_vinner_over_standarden_begge_veier(self):
        """**Map, ikke Set.** Fraværende nøkkel betyr «som standarden»; et Set
        kunne ikke skilt «ikke rørt» fra «utvidet for hånd», og et kort man
        åpnet ville slått seg sammen igjen når noen la til en bil i gruppa."""
        self._kjor("""
            const a = aktivListe.ressurser.find((x) => x.id === 20);
            const alene = aktivListe.ressurser.find((x) => x.id === 10);
            ressursApen.set(20, true);
            assert(ressursErApen(a) === true, 'aapnet for haand skal staa aapent');
            ressursApen.set(10, false);
            assert(ressursErApen(alene) === false, 'lukket for haand skal staa lukket');
        """)

    # ── Hva kortet viser ─────────────────────────────────────────────────
    def test_sammenslaatt_kort_har_ingen_tabell(self):
        ut = self._kjor("""
            console.log(mkRessurs(aktivListe.ressurser.find((x) => x.id === 20), false));
        """)
        self.assertNotIn('<table', ut)
        self.assertNotIn('Kari', ut)

    def test_sammenslaatt_kort_sier_hva_som_er_der(self):
        """Et sammenslått kort uten tall er bare en skjult rad. Skiftene,
        mannskapet, de ledige plassene og timene skal stå i hodet."""
        ut = self._kjor("""
            console.log(mkRessurs(aktivListe.ressurser.find((x) => x.id === 20), false));
        """)
        self.assertIn('1 skift', ut)
        self.assertIn('1 mannskap', ut)
        self.assertIn('1 ledig', ut)
        # 16 t, ikke 8: begge plassene på blokka teller, også den ledige.
        # Det er samme sum som ressursoverskriften i «Oversikt» viser.
        self.assertIn('16 t', ut)

    def test_tomt_kort_sier_at_det_er_tomt(self):
        ut = self._kjor("""
            console.log(mkRessurs(aktivListe.ressurser.find((x) => x.id === 21), false));
        """)
        self.assertIn('Ingen satt opp', ut)

    def test_sammenslaatt_kort_er_ingen_blindvei(self):
        """**Knappene blir stående.** «Rediger», «Roller» og «Opprett vakt»
        skal virke uten å åpne kortet først — ellers er sammenslåingen et
        ekstra klikk foran alt man skulle gjøre."""
        ut = self._kjor("""
            console.log(mkRessurs(aktivListe.ressurser.find((x) => x.id === 20), false));
        """)
        self.assertIn('apneVaktpost', ut)
        self.assertIn('apneRessurs', ut)
        self.assertIn('apneRoller', ut)

    def test_apent_kort_tegner_tabellen(self):
        ut = self._kjor("""
            console.log(mkRessurs(aktivListe.ressurser.find((x) => x.id === 20), true));
        """)
        self.assertIn('<table', ut)
        self.assertIn('Kari', ut)

    def test_vippa_sier_hvilken_vei_den_gaar(self):
        """`aria-expanded` og pila skal følge tilstanden — en pil som peker
        samme vei uansett er en pil man slutter å lese."""
        apen = self._kjor("console.log(mkRessurs(aktivListe.ressurser[1], true));")
        lukket = self._kjor("console.log(mkRessurs(aktivListe.ressurser[1], false));")
        self.assertIn('aria-expanded="true"', apen)
        self.assertIn('bi-chevron-down', apen)
        self.assertIn('aria-expanded="false"', lukket)
        self.assertIn('bi-chevron-right', lukket)

    # ── Dagen ytterst også i gruppefanen ─────────────────────────────────
    #: Bil A får et skift dagen etter, så to dager finnes i gruppa.
    DAG_TO = """
        aktivListe.vaktposter.push({id: 3, ressurs_id: 20, ledig: false, navn: 'Nina',
          korps_kort: 'HGSD', rolle: '', merknad: '',
          fra_tid: '2026-10-04T08:00:00', til_tid: '2026-10-04T16:00:00'});
    """

    def _ambulansefanen(self, ekstra=''):
        return self._kjor(ekstra + "console.log(mkGruppe(aktivListe.grupper[1]));")

    def test_dagen_staar_over_ressurskortene(self):
        """**André, 15. sep. 2026:** «i ressursgruppene må det være likt som
        oversikt — ressurser per dag». Fanen var en stabel ressurskort med
        dagrader inni; nå er den en stabel dager med ressurskort inni."""
        ut = self._ambulansefanen()
        self.assertIn('class="vl-dagtittel"', ut)
        self.assertLess(ut.index('class="vl-dagtittel"'), ut.index('Bil A'),
                        'dagen skal staa over kortene')

    def test_ressursen_gjentas_under_hver_dag_den_har_skift(self):
        ut = self._ambulansefanen(self.DAG_TO)
        # Tre seksjoner: to dager pluss «Uten skift» for Bil B, som ikke har noen.
        self.assertEqual(ut.count('class="vl-dagbolk"'), 3)
        self.assertEqual(ut.count('class="vl-dagtittel vl-utenskift"'), 1)
        self.assertEqual(ut.count('>Bil A'), 2, 'Bil A har skift begge dager')
        self.assertEqual(ut.count('>Bil B'), 1, 'Bil B staar bare under «Uten skift»')

    def test_dagbolken_viser_bare_sin_egen_dags_skift(self):
        ut = self._kjor(self.DAG_TO + """
            ressursApen.set(20, true);
            console.log(mkGruppe(aktivListe.grupper[1]));
        """)
        forste = ut[:ut.index('Søndag 4. okt')]
        self.assertIn('Kari', forste)
        self.assertNotIn('Nina', forste)
        self.assertIn('Nina', ut[ut.index('Søndag 4. okt'):])

    def test_ressurs_uten_skift_naas_fortsatt(self):
        """**Bil B har ingen skift og hører til ingen dag.** Uten en egen bolk
        ville kortet med «Opprett vakt» ikke finnes noe sted, og ingen kunne
        satt opp den første vakta på en ny bil."""
        ut = self._ambulansefanen()
        self.assertIn('Uten skift', ut)
        uten = ut[ut.index('Uten skift'):]
        self.assertIn('Bil B', uten)
        self.assertIn('apneVaktpost', uten)

    def test_ingen_bolk_naar_alle_har_skift(self):
        """«Uten skift» skal ikke stå tom — en overskrift uten noe under seg er
        en linje man leser for å se at det ikke står noe der."""
        ut = self._kjor("""
            aktivListe.vaktposter.push({id: 3, ressurs_id: 21, ledig: false, navn: 'Ola',
              korps_kort: 'HGSD', rolle: '', merknad: '',
              fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T16:00:00'});
            console.log(mkGruppe(aktivListe.grupper[1]));
        """)
        self.assertNotIn('Uten skift', ut)

    def test_sammenslaaingen_gjelder_ressursen_paa_tvers_av_dagene(self):
        """Vippa sitter på bilen, ikke på bilen-den-dagen. Å slå sammen Bil A
        under fredag og se den åpen under lørdag ville vært to tilstander for
        én ting."""
        ut = self._kjor(self.DAG_TO + """
            ressursApen.set(20, false);
            console.log(mkGruppe(aktivListe.grupper[1]));
        """)
        self.assertEqual(ut.count('<table'), 0)
        apen = self._kjor(self.DAG_TO + """
            ressursApen.set(20, true);
            console.log(mkGruppe(aktivListe.grupper[1]));
        """)
        self.assertEqual(apen.count('<table'), 2, 'aapen i begge dagbolkene')

    def test_rekkefolgen_er_ressursenes_ikke_postenes(self):
        """Fanerekka skal ikke hoppe fra dag til dag etter hvem som
        tilfeldigvis har det første skiftet den dagen."""
        # `unshift`: Bil Bs skift skal ligge **først** i lista serveren sendte,
        # ellers er rekkefølgen garantert av innsettingen og ikke av regelen.
        ut = self._kjor("""
            aktivListe.vaktposter.unshift({id: 3, ressurs_id: 21, ledig: false, navn: 'Ola',
              korps_kort: 'HGSD', rolle: '', merknad: '',
              fra_tid: '2026-10-03T06:00:00', til_tid: '2026-10-03T12:00:00'});
            console.log(mkGruppe(aktivListe.grupper[1]));
        """)
        self.assertLess(ut.index('>Bil A'), ut.index('>Bil B'),
                        'Bil B har det tidligste skiftet, men Bil A staar foerst')

    # ── Gruppa avgjør, ikke kortet ───────────────────────────────────────
    def test_gruppa_slaar_sammen_kortene_sine(self):
        """**`map(mkRessurs)` ville sendt indeksen som `apen`** — bil nummer
        null hadde stått lukket og resten åpne. Formen sto her og var harmløs
        så lenge byggeren tok ett argument."""
        ut = self._kjor("console.log(mkGruppe(aktivListe.grupper[1]));")
        self.assertEqual(ut.count('<table'), 0, 'begge ambulansene skal vaere sammenslaatt')
        self.assertIn('Bil A', ut)
        self.assertIn('Bil B', ut)

    def test_gruppa_med_en_ressurs_tegner_tabellen(self):
        ut = self._kjor("console.log(mkGruppe(aktivListe.grupper[0]));")
        self.assertIn('<table', ut)


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
      globalThis.bootstrap = {Modal: class { static getOrCreateInstance(el) { return new this(el); } constructor() {} show() {} }};
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
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.MANNSKAP = 'mannskap';\n"
             "globalThis.TILSTEDE = 'tilstede';\n"
             "globalThis.BELASTNING = 'belastning';\n"
             "globalThis.belastning = null;\n"
            "globalThis.BELASTNING = 'belastning';\n"
            "globalThis.belastning = null;\n"
            "globalThis.TILSTEDE = 'tilstede';\n"
            "globalThis.BELASTNING = 'belastning';\n"
            "globalThis.belastning = null;\n"
             "globalThis.OVERSIKT = 'oversikt';\n"
             "globalThis.IKKE_PLASSERT = 'ikke-plassert';\n"
             "globalThis.MITT_KORPS = 'mitt-korps';\n"
             "globalThis.korpsfilter = null;\n")

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
            globalThis.bootstrap = {Modal: class { static getOrCreateInstance(el) { return new this(el); } constructor() { apnet = true; }
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
        kropp = extract_function(read_js(VAKTLISTE_JS), '_plancellene')
        self.assertIn('type="datetime-local" step="300"', kropp)

    def test_steget_er_et_helt_minutt(self):
        """Et steg under 60 sekunder gir feltet et sekundsegment, altså en
        kolonne til å tabbe seg gjennom.

        **Bare tidsfeltene.** Første utgave leste *alle* `step="…"` på sida,
        og ble rød den dagen et `<input type="number">` fikk `step="1"` —
        som er riktig for et tall og meningsløst for et klokkeslett. En test
        som måler feil felt måler ikke regelen sin.
        """
        felt = []
        for kilde in (self._mal(), read_js(VAKTLISTE_JS)):
            felt += re.findall(r'<input[^>]*type="datetime-local"[^>]*>', kilde)
        self.assertTrue(felt, 'fant ingen tidsfelt')
        for f in felt:
            for verdi in re.findall(r'step="(\d+)"', f):
                with self.subTest(felt=f[:60], step=verdi):
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
        (VAKTLISTE_JS, ('apneVaktpost', 'ressursErApen', '_settTid', '_iso16', '_d',
                        '_fyll', '_skjulFeil', '_vaktpostModusSkifte',
                        'rollerForGruppe', '_plussTimer')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    OPPSETT = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
        // `ressursApen` er en toppnivå-const, ikke en funksjon, så
        // `build_harness` kan ikke klippe den ut — den stubbes som de andre
        // modulglobalene. `apneVaktpost` åpner kortet den legger et skift i.
        globalThis.ressursApen = new Map();
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
        globalThis.bootstrap = {Modal: class { static getOrCreateInstance(el) { return new this(el); } constructor() {} show() {} }};
    """

    def test_begge_feltene_baerer_vaktas_startdato(self):
        run_node(self.harness, self.OPPSETT + """
            apneVaktpost(10);
            assert(felter['ny-vaktpost-fra'].value === '2026-10-03T08:00',
                   'fra: ' + felter['ny-vaktpost-fra'].value);
            // Til står åtte timer etter fra (André, 12. sep. 2026).
            assert(felter['ny-vaktpost-til'].value === '2026-10-03T16:00',
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
            assert(felter['ny-vaktpost-til'].value === '2026-10-03T16:00',
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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

    def test_utenfor_drift_bygges_raden_aldri(self):
        """Innsjekk er stengt i planlegging, og porten står i `mkRessurs`:
        drifttabellen bygges bare når lista er i drift. Cella selv spør ikke
        — den kalles ikke."""
        kropp = _uten_kommentarer(
            extract_function(read_js(VAKTLISTE_JS), 'mkRessurs'))
        self.assertIn('const drift = iDrift();', kropp)
        self.assertIn('drift ? _driftrad(vp, r, kanRoreRad(vp, r, kanRore))', kropp)

    def test_korpsforeren_ser_status_men_ingen_knapp(self):
        """Avklaring 11.3, speilet i grensesnittet. En knapp som fører til
        en vegg er verre enn ingen knapp — men *statusen* er det samme
        spørsmålet enten man kan svare på det eller ikke, og `les` ser hele
        lista."""
        ut = self._knapper(self.POST, nivaa='skriv_handling')
        self.assertNotIn('data-action', ut, 'ingen knapp for korps-føreren')
        self.assertIn('Ikke møtt', ut, 'men statusen skal hun se')

    def test_korpsforeren_ser_naar_noen_har_mott(self):
        ut = self._knapper({**self.POST, 'mott_at': '2026-10-03T08:04:00',
                            'tilstede': True}, nivaa='skriv_handling')
        self.assertNotIn('data-action', ut)
        self.assertIn('08:04', ut)

    def test_ledig_plass_har_ingen_aa_stemple(self):
        ut = self._knapper({**self.POST, 'ledig': True})
        self.assertNotIn('data-action', ut)

    def _radklasse(self, vp, drift=True):
        import json
        return run_node(self.harness, f"""
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
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


class PlanleggingsfanenTests(SimpleTestCase):
    """Belastningstabellen (§8b).

    **Varsler, ikke sperrer** — og det skal *synes* at det er et varsel og
    ikke en feil. Fargen er gul, ikke rød: et langt skift er ikke galt, det
    er noe planleggeren skal se og ta stilling til.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkBelastning', '_tall', 'kanLede', '_nivaa',
                        '_erAdmin', 'visFane')),
    )
    VINDU = "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    RAD = {'mannskap_id': 1, 'navn': 'Kari', 'korps_kort': 'HGSD',
           'antall_skift': 2, 'timer': 14.0, 'lengste_skift': 8.0,
           'korteste_hvile': 10.0, 'faktiske_timer': None,
           'langt_skift': False, 'kort_hvile': False}
    SAM = {'personer': 1, 'skift': 2, 'timer': 14.0, 'ledige_plasser': 0,
           'lange_skift': 0, 'korte_hviler': 0}

    def _vis(self, personer=None, sammendrag=None, *, nivaa='admin'):
        import json
        data = {
            'personer': personer if personer is not None else [self.RAD],
            'sammendrag': {**self.SAM, **(sammendrag or {})},
            'grenser': {'maks_skift_timer': 12, 'min_hvile_timer': 8},
        }
        vindu = ("globalThis.window = { MODUL_TILGANG: "
                 + ("{ admin: true }" if nivaa == 'admin'
                    else f"{{ vaktliste: '{nivaa}', admin: false }}")
                 + " };\n")
        return run_node(self.harness, vindu + f"""
            globalThis.belastning = {json.dumps(data)};
            console.log(mkBelastning());
        """)

    def test_uhentet_sier_fra_framfor_aa_kaste(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.belastning = null;
            console.log(mkBelastning());
        """)
        self.assertIn('Regner', ut)

    def test_noekkeltallene_staar_over_lista(self):
        ut = self._vis()
        self.assertIn('vl-noekkeltall', ut)
        self.assertLess(ut.index('vl-noekkeltall'), ut.index('Kari'))

    def test_hele_timer_vises_uten_desimal(self):
        """«14 t» leses raskere enn «14.0 t» i en kolonne man skummer."""
        ut = self._vis()
        self.assertIn('>14 t<', ut)
        self.assertNotIn('14.0', ut)

    def test_halve_timer_beholder_desimalen_med_komma(self):
        """«7,5 t», ikke «7.5 t» — Andrés format, og det samme som
        ressurstabellen alt skrev (11. sep. 2026)."""
        ut = self._vis([{**self.RAD, 'timer': 7.5}])
        self.assertIn('7,5 t', ut)
        self.assertNotIn('7.5', ut)

    def test_langt_skift_merkes_men_sperrer_ingenting(self):
        ut = self._vis([{**self.RAD, 'lengste_skift': 14.0,
                         'langt_skift': True}],
                       {'lange_skift': 1})
        self.assertIn('vl-advarsel', ut)
        self.assertIn('skift over 12 t', ut, 'varselet sier hva grensa er')
        self.assertIn('Kari', ut, 'raden står der som før')

    def test_kort_hvile_merkes(self):
        ut = self._vis([{**self.RAD, 'korteste_hvile': 4.0,
                         'kort_hvile': True}], {'korte_hviler': 1})
        self.assertIn('vl-advarsel', ut)
        self.assertIn('hviler under 8 t', ut)

    def test_uten_varsler_sies_det(self):
        """En tom boks der varslene ellers står ser ut som noe som ikke er
        lastet."""
        self.assertIn('Ingen varsler', self._vis())

    def test_manglende_hvile_er_en_strek_ikke_en_null(self):
        """Null timers hvile er en beskjed om noe galt; «ingen hvile å måle»
        er fraværet av et tall."""
        ut = self._vis([{**self.RAD, 'korteste_hvile': None}])
        self.assertIn('—', ut)
        self.assertNotIn('0 t</span>', ut)

    def test_faktisk_kolonne_bare_naar_noe_er_stemplet(self):
        """En kolonne med bare streker stjeler bredde fra dem som betyr noe."""
        self.assertNotIn('Faktisk', self._vis())
        ut = self._vis([{**self.RAD, 'faktiske_timer': 9.5}])
        self.assertIn('Faktisk', ut)
        self.assertIn('9,5 t', ut)

    def test_tom_liste_forklarer_hvorfor(self):
        ut = self._vis([], {'personer': 0, 'skift': 0, 'timer': 0})
        self.assertIn('Ingen er satt', ut)

    def test_grenseknappen_er_ledernivaa(self):
        """Å flytte grensa endrer hva *alle* vaktlister varsler om."""
        self.assertIn('apneGrenser', self._vis())
        self.assertNotIn('apneGrenser', self._vis(nivaa='skriv_full'))
        self.assertNotIn('apneGrenser', self._vis(nivaa='les'))

    def test_fanen_henter_tallene_forste_gang(self):
        """M70: uten hentingen står fanen på «Regner…» for alltid. Den er lat
        med vilje — en fane som ikke er åpnet skal ikke koste en spørring."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.belastning = null;
            globalThis.register = null;
            globalThis.MANNSKAP = 'mannskap';
            globalThis.BELASTNING = 'belastning';
            globalThis.aktivFane = 'oversikt';
            let hentet = 0;
            globalThis.lastBelastning = () => { hentet += 1; };
            globalThis.lastRegister = () => {};
            globalThis.tegnFaner = () => {};
            globalThis.tegnPanel = () => {};

            visFane('belastning');
            assert(hentet === 1, 'tallene ble ikke hentet: ' + hentet);

            globalThis.belastning = {personer: [], sammendrag: {}, grenser: {}};
            visFane('belastning');
            assert(hentet === 1, 'hentet paa nytt selv om de alt laa der');
        """)
        self.assertIn('OK', ut)

    def test_navn_escapes(self):
        ut = self._vis([{**self.RAD, 'navn': '<img src=x onerror=alert(1)>'}])
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)


class TidsblokkerTests(SimpleTestCase):
    """Skift med samme fra–til samles under én blokklinje (11. sep. 2026).

    Andrés punkt: mange på en vakt deler tid, og en liste der samme spenn
    står på fire rader under hverandre er lang og lik — man ser ikke
    skiftbyttet før man har lest hver rad. Tiden skrives én gang, på
    blokklinja, sammen med timene og hvor mange som står der.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utvalgstekst', '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader', 'kanBemannePlass', '_mittKorpsId', '_synligePoster', '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke', '_telling', '_driftrad', '_plancellene', '_planrad', '_rolleValg', '_fyllValgFor', 'opptattPaaPlassen', '_plassKorps', '_varighet', '_skifttimer', '_tall', '_iso16', '_radklasse', '_stempelknapper', 'kanStemple', 'iDrift', 'kanSkriveAlt', '_nivaa', '_erAdmin', '_skiftrekkefolge', '_sumTimer', '_d', '_kl', '_dag', '_sammeDag', '_tidsspenn', '_vaktspenn', '_ressurserIGruppe', '_grupperMedRessurser', 'kanRoreRad')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")
    LISTE = UtskriftslistaTests.LISTE

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _oversikt(self):
        return run_node(self.harness, self.VINDU + self.LISTE
                        + "console.log(mkOversikt());")

    # ── _tidsblokker ─────────────────────────────────────────────────────
    def test_like_spenn_blir_en_blokk_og_ulike_blir_hver_sin(self):
        """Andrés tre rader på samleplassen: to som slutter 03:00, én som
        slutter 22:15. Det er to blokker — og den korte kommer først, fordi
        blokkene arver `_skiftrekkefolge`."""
        run_node(self.harness, self.LISTE + """
            const poster = aktivListe.vaktposter.filter((v) => v.ressurs_id === 10);
            const b = _tidsblokker(poster);
            assert(b.length === 2, 'fikk ' + b.length + ' blokker');
            assert(b[0].til_tid === '2026-09-04T22:15:00', 'den korte foerst');
            assert(b[0].poster.length === 1, 'kort blokk: ' + b[0].poster.length);
            assert(b[1].poster.length === 2, 'lang blokk: ' + b[1].poster.length);
        """)

    def test_blokka_krever_likhet_ikke_overlapp(self):
        """Et skift som begynner samtidig men slutter en time før de andre er
        sitt eget — ellers hadde blokklinja løyet om når folk går av."""
        run_node(self.harness, """
            const b = _tidsblokker([
              {fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00', navn: 'A'},
              {fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T02:00:00', navn: 'B'},
            ]);
            assert(b.length === 2, 'overlapp er ikke likhet: ' + b.length);
        """)

    def test_radene_i_blokka_er_sortert_paa_navn(self):
        run_node(self.harness, """
            const b = _tidsblokker([
              {fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00', navn: 'Ola'},
              {fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00', navn: 'Anne'},
            ]);
            assert(b[0].poster[0].navn === 'Anne', 'fikk ' + b[0].poster[0].navn);
        """)

    def test_tom_liste_gir_ingen_blokker(self):
        run_node(self.harness, "assert(_tidsblokker([]).length === 0, 'tom');")

    # ── _blokklinje ──────────────────────────────────────────────────────
    def _linje(self, poster, kolonner=9):
        import json
        return run_node(self.harness, self.VINDU + f"""
            console.log(_blokklinje({{fra_tid: '2026-09-04T20:00:00',
                                      til_tid: '2026-09-05T04:30:00',
                                      poster: {json.dumps(poster)}}}, {kolonner}));
        """)

    def test_linja_baerer_tid_timer_og_antall(self):
        ut = self._linje([{'ledig': False}, {'ledig': False}, {'ledig': True}])
        self.assertIn('20:00', ut)
        self.assertIn('04:30', ut)
        self.assertIn('8,5 t', ut)
        self.assertIn('2 mannskap · 1 ledig', ut)

    def test_linja_spenner_over_alle_kolonnene(self):
        """Én celle over hele bredden — ellers faller den ut av
        `table-layout: fixed` og forskyver kolonnene under."""
        self.assertIn('colspan="9"', self._linje([{'ledig': False}], 9))
        self.assertIn('colspan="4"', self._linje([{'ledig': False}], 4))

    def test_flertall_naar_flere_er_ledige(self):
        ut = self._linje([{'ledig': True}, {'ledig': True}])
        self.assertIn('2 ledige', ut)
        self.assertNotIn('mannskap', ut, 'ingen er satt opp, så det står ikke')

    def test_linja_krysser_dogn_med_dagen_nevnt_to_ganger(self):
        """Samme regel som `_tidsspenn`: dagen én gang innenfor et døgn, to
        ganger ellers."""
        ut = self._linje([{'ledig': False}])
        self.assertEqual(ut.count('fre'), 1)
        self.assertEqual(ut.count('lør'), 1)

    # ── Oversikten ───────────────────────────────────────────────────────
    def test_oversikten_har_ingen_tidskolonne_lenger(self):
        """Kolonnen sto med samme verdi fire ganger. Tiden står på blokklinja."""
        ut = self._oversikt()
        self.assertNotIn('<th>Tid</th>', ut)
        self.assertIn('vl-blokk', ut)

    def test_en_blokklinje_per_spenn_per_ressurs(self):
        """Samleplassen har to spenn, hver ambulanse ett: fire linjer."""
        self.assertEqual(self._oversikt().count('class="vl-blokk"'), 4)

    def test_tiden_skrives_en_gang_per_blokk(self):
        """Tre rader på samleplassen begynner 17:00 — men 17:00 står to
        ganger der, én per blokk, ikke tre. Det er hele poenget."""
        ut = self._oversikt()
        samleplass = ut[ut.index('<h3>Samleplass'):ut.index('<h3>Ambulanse 1')]
        self.assertEqual(samleplass.count('17:00'), 2)

    def test_ressursen_summerer_timene(self):
        """10 + 10 + 5,25 på samleplassen: «25,3 t» i overskriften, med komma.
        To *skift* — vakttidene — ikke tre rader; og ingen mannskap, siden
        alle tre plassene er ledige."""
        ut = self._oversikt()
        samleplass = ut[ut.index('<h3>Samleplass'):ut.index('<h3>Ambulanse 1')]
        self.assertIn('2 skift · 25,3 t', samleplass)
        self.assertNotIn('0 mannskap', samleplass)
        self.assertIn('3 ledige', samleplass)

    def test_arkhodet_summerer_hele_vakta(self):
        """25,25 + 10 + 10 = 45,25 → «45,3 t». Skiftene er de ulike vakttidene
        over hele vakta: 17–03 og 17–22:15 er to, selv om 17–03 går på tre
        ressurser. Mannskap er Kari og Ola."""
        self.assertIn('2 skift · 2 mannskap · 45,3 t', self._oversikt())

    def test_skift_er_vakttider_og_mannskap_er_folk(self):
        """Andrés ord (11. sep. 2026): «skift må vel tolkes som ulike
        vakttider, og personell som mannskap». Fem rader på to spenn er to
        skift og fire mannskap."""
        ut = run_node(self.harness, """
            const poster = [
              {ledig: false, fra_tid: 'a', til_tid: 'b'},
              {ledig: false, fra_tid: 'a', til_tid: 'b'},
              {ledig: true,  fra_tid: 'a', til_tid: 'b'},
              {ledig: false, fra_tid: 'c', til_tid: 'd'},
              {ledig: false, fra_tid: 'c', til_tid: 'd'},
            ];
            console.log('[' + _telling(poster, 2) + ']');
            console.log('[' + _telling([{ledig: true, fra_tid: 'a', til_tid: 'b'}], 1) + ']');
        """)
        self.assertIn('[2 skift · 4 mannskap]', ut)
        self.assertIn('[1 skift]', ut, 'bare ledige: mannskap utelates')

    def test_ledige_plasser_beholder_sin_rad(self):
        ut = self._oversikt()
        self.assertIn('— ledig —', ut)
        self.assertIn('KARM', ut, 'reservasjonen står fortsatt på raden')

    # ── Driftraden ───────────────────────────────────────────────────────
    def test_driftraden_er_regnearket_med_stempelet_foran(self):
        """Snudd 12. sep. 2026: driftraden var uten tidsfelt («fire like
        tider under hverandre»), men André ville redigere under drift som i
        planlegging. Blokklinja bærer fortsatt tiden; raden bærer feltene."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.rollerForGruppe = () => []; globalThis.kanStemple = () => true;
            globalThis.aktivListe = {vaktliste: {i_drift: true}};
            console.log(_driftrad({id: 5, ledig: false, navn: 'Kari',
                                   korps_kort: 'HGSD', rolle: 'Sjåfør',
                                   mott_at: null, av_vakt_at: null, tilstede: false,
                                   fra_tid: '2026-10-03T08:00:00',
                                   til_tid: '2026-10-03T16:00:00'}, {id: 1, gruppe_id: 1}, true));
        """)
        self.assertEqual(ut.count('<td'), 10, 'innsjekk + regnearkets ni')
        self.assertLess(ut.index('vl-stempelcelle'), ut.index('vl-navn'))
        self.assertIn('type="datetime-local"', ut, 'tidene redigeres i raden også i drift')
        self.assertIn('stemplMott', ut)

    # ── Timeformatet ─────────────────────────────────────────────────────
    def test_tall_bruker_komma_og_dropper_null_desimal(self):
        run_node(self.harness, """
            assert(_tall(8.5) === '8,5', _tall(8.5));
            assert(_tall(14) === '14', _tall(14));
            assert(_tall(14.0) === '14', _tall(14.0));
            assert(_tall(8.25) === '8,3', _tall(8.25));
            assert(_tall(0) === '0', _tall(0));
        """)

    def test_sum_hopper_over_skift_uten_spenn(self):
        """Et skift som mangler den ene tida vises som «—», og en strek har
        ingen timer å legge til."""
        run_node(self.harness, """
            const sum = _sumTimer([
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T16:30:00'},
              {fra_tid: null, til_tid: '2026-10-03T16:00:00'},
              {fra_tid: '2026-10-03T16:00:00', til_tid: '2026-10-03T08:00:00'},
            ]);
            assert(sum === 8.5, 'fikk ' + sum);
            assert(_sumTimer([]) === 0, 'tom liste');
        """)


class NyVaktlisteSporOmSluttenTests(SimpleTestCase):
    """«Ny vaktliste» spør om slutten, ikke bare starten (11. sep. 2026).

    Feltet fantes, men bare bak «Vaktas lengde» inne i innstillingsvinduet —
    André fant det ikke. Uten slutt tegnes kurvene bare fra første til siste
    skift, og hullet i begynnelsen er usynlig.
    """

    HARNESS = (
        (VAKTLISTE_JS, ('opprettVaktliste', '_skjulFeil', '_visFeil',
                        '_tidFraFelt')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_malen_har_feltet_i_opprettelsesvinduet(self):
        from pathlib import Path
        from django.conf import settings
        mal = (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
               / 'index.html').read_text(encoding='utf-8')
        vindu = mal[mal.index('id="nyVaktlisteModal"'):]
        vindu = vindu[:vindu.index('</div>\n</div>')]
        self.assertIn('id="ny-vakt-slutt"', vindu)
        self.assertIn('id="ny-vakt-start"', vindu, 'starten står der fortsatt')

    def test_opprettelsen_sender_slutten_med(self):
        ut = run_node(self.harness, """
            const felter = {
              'ny-vakt-navn': {value: 'Oktobervakta'},
              'ny-vakt-start': {value: '2026-10-03T08:00'},
              'ny-vakt-slutt': {value: '2026-10-03T18:00'},
              'ny-vakt-kopier': {value: ''},
              'ny-vakt-feil': {classList: {add() {}, remove() {}}, textContent: ''},
            };
            globalThis.document = {getElementById: (id) => felter[id] || null};
            globalThis.withSubmitGuard = async (_id, fn) => fn();
            let sendt = null;
            globalThis.apiFetch = async (_url, opts) => {
              sendt = JSON.parse(opts.body);
              return {ok: false, json: async () => ({})};
            };
            await opprettVaktliste();
            assert(sendt !== null, 'ingenting ble sendt');
            assert(sendt.planlagt_slutt === '2026-10-03T18:00',
                   'slutt: ' + sendt.planlagt_slutt);
            assert(sendt.startet === '2026-10-03T08:00', 'start: ' + sendt.startet);
        """)
        self.assertIn('OK', ut)

    def test_tomt_sluttfelt_sendes_som_null(self):
        """Slutten er valgfri ved opprettelsen — en tom streng ville serveren
        lest som «ugyldig tid» og ikke som «ingen»."""
        ut = run_node(self.harness, """
            const felter = {
              'ny-vakt-navn': {value: 'Uten slutt'},
              'ny-vakt-start': {value: ''},
              'ny-vakt-slutt': {value: ''},
              'ny-vakt-kopier': {value: ''},
              'ny-vakt-feil': {classList: {add() {}, remove() {}}, textContent: ''},
            };
            globalThis.document = {getElementById: (id) => felter[id] || null};
            globalThis.withSubmitGuard = async (_id, fn) => fn();
            let sendt = null;
            globalThis.apiFetch = async (_url, opts) => {
              sendt = JSON.parse(opts.body);
              return {ok: false, json: async () => ({})};
            };
            await opprettVaktliste();
            assert(sendt.planlagt_slutt === null, 'slutt: ' + sendt.planlagt_slutt);
        """)
        self.assertIn('OK', ut)


class BelastningstabellensBreddeTests(SimpleTestCase):
    """«Veldig tett på mobil» (André, 11. sep. 2026).

    Tabellen arvet `min-width: 0` fra drifttabellen, og `table-layout: fixed`
    delte 308 px likt på seks kolonner. Regelen: tabellen har en gulvbredde
    og kolonnene har andeler, så den ruller i ramma framfor å klemmes.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkBelastning', '_tall', 'kanLede', '_nivaa',
                        '_erAdmin')),
    )
    RAD = PlanleggingsfanenTests.RAD
    SAM = PlanleggingsfanenTests.SAM

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _vis(self, rad):
        import json
        data = {'personer': [rad], 'sammendrag': self.SAM,
                'grenser': {'maks_skift_timer': 12, 'min_hvile_timer': 8}}
        return run_node(self.harness, "globalThis.window = { MODUL_TILGANG: { admin: true } };\n" + f"""
            globalThis.belastning = {json.dumps(data)};
            console.log(mkBelastning());
        """)

    def _css(self):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'static' / 'css'
                / 'vaktliste.css').read_text(encoding='utf-8')

    def test_tabellen_har_egen_klasse_med_gulvbredde(self):
        ut = self._vis(self.RAD)
        self.assertIn('vl-tabell-belastning', ut)
        self.assertNotIn('vl-tabell-drift', ut, 'drifttabellens min-width: 0 er feil her')
        m = re.search(r'(?m)^\.vl-tabell-belastning \{([^}]*)\}', self._css())
        self.assertIsNotNone(m, 'regelen finnes ikke i stilarket')
        bredde = re.search(r'min-width:\s*(\d+)rem', m.group(1))
        self.assertIsNotNone(bredde)
        self.assertGreaterEqual(int(bredde.group(1)), 30)

    def test_overskriftene_faar_bryte(self):
        """«Korteste hvile» trenger 123 px; med `nowrap` fra `.vl-tabell thead
        th` skrev den seg inn over nabocella (André: «fortsatt litt
        overlapp»). Regelen for denne tabellen slår brytningen på igjen."""
        m = re.search(r'(?m)^\.vl-tabell-belastning thead th \{([^}]*)\}', self._css())
        self.assertIsNotNone(m, 'ingen egen regel for tabellhodet')
        self.assertIn('white-space: normal', m.group(1))

    def test_kolonnene_har_andeler_som_summerer_til_hundre(self):
        """Med og uten «Faktisk» — begge oppsettene skal fylle tabellen."""
        for rad in (self.RAD, {**self.RAD, 'faktiske_timer': 9.5}):
            ut = self._vis(rad)
            andeler = [int(a) for a in re.findall(r'<col style="width: (\d+)%">', ut)]
            with self.subTest(faktisk=rad['faktiske_timer'] is not None):
                self.assertEqual(sum(andeler), 100, andeler)
                self.assertEqual(len(andeler), ut.count('<th>'), 'én andel per kolonne')


class KorpsvelgerenTests(SimpleTestCase):
    """Korpsvelgeren i nettleseren (11. sep. 2026).

    Regelen `_synligePoster()` speiler serverens `poster_for_korps()`: en
    person vises når badgen er korpset, en ledig plass når reservasjonen er
    det. `brukKorpsfilter()` legger den på `aktivListe.vaktposter` og
    `register.mannskap`, så alle byggerne følger med uten å vite om den.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_synligePoster', 'brukKorpsfilter', 'fyllKorpsvelger',
                        '_fyll')),
    )
    POSTER = """
        const poster = [
          {id: 1, ledig: false, navn: 'Kari', korps_id: 1, reservert_korps_id: 1},
          {id: 2, ledig: false, navn: 'Ola', korps_id: 2, reservert_korps_id: 2},
          {id: 3, ledig: true, navn: '', korps_id: null, reservert_korps_id: 1},
          {id: 4, ledig: true, navn: '', korps_id: null, reservert_korps_id: null},
        ];
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_uten_valg_vises_alt(self):
        run_node(self.harness, self.POSTER + """
            assert(_synligePoster(poster, null).length === 4, 'null = alle');
            assert(_synligePoster(poster, undefined).length === 4, 'undefined = alle');
        """)

    def test_personen_paa_badgen_plassen_paa_reservasjonen(self):
        run_node(self.harness, self.POSTER + """
            const ids = _synligePoster(poster, 1).map((v) => v.id);
            assert(JSON.stringify(ids) === '[1,3]', 'fikk ' + ids);
            const karmoy = _synligePoster(poster, 2).map((v) => v.id);
            assert(JSON.stringify(karmoy) === '[2]', 'fikk ' + karmoy);
        """)

    def test_ureservert_ledig_plass_er_ingens(self):
        """Vaktlederens bord vises ikke under noe korps — den er ikke satt av
        til noen, og under HGSD ville den sett ut som HGSDs å fylle."""
        run_node(self.harness, self.POSTER + """
            assert(!_synligePoster(poster, 1).some((v) => v.id === 4), 'ikke under HGSD');
            assert(!_synligePoster(poster, 2).some((v) => v.id === 4), 'ikke under Karmoy');
        """)

    def test_filteret_legges_paa_lista_og_registeret(self):
        run_node(self.harness, self.POSTER + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {alle_vaktposter: poster, vaktposter: poster};
            globalThis.register = {
              alle_mannskap: [{id: 1, navn: 'Kari', korps_id: 1}, {id: 2, navn: 'Ola', korps_id: 2}],
              mannskap: [],
            };
            globalThis.korpsfilter = 2;
            brukKorpsfilter();
            assert(aktivListe.vaktposter.length === 1, 'skift: ' + aktivListe.vaktposter.length);
            assert(register.mannskap.length === 1 && register.mannskap[0].navn === 'Ola',
                   'register: ' + JSON.stringify(register.mannskap));
            globalThis.korpsfilter = null; globalThis.utskriftRessurs = null;
            brukKorpsfilter();
            assert(aktivListe.vaktposter.length === 4, 'tilbake til alle');
            assert(register.mannskap.length === 2, 'registeret tilbake');
        """)

    def test_velgeren_faller_tilbake_naar_korpset_er_borte(self):
        """Et valg som ikke finnes i lista er et filter man ikke ser."""
        ut = run_node(self.harness, """
            const el = {innerHTML: '', value: ''};
            globalThis.document = {getElementById: (id) => (id === 'vl-korpsvalg' ? el : null)};
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {korps: [{id: 1, navn: 'Haugesund', kortnavn: 'HGSD'}]};
            globalThis.korpsfilter = 99;
            fyllKorpsvelger();
            assert(el.innerHTML.includes('Alle korps'), 'tomt valg mangler');
            assert(el.innerHTML.includes('HGSD — Haugesund'), 'korpset mangler');
            assert(korpsfilter === null, 'valget skulle falt tilbake: ' + korpsfilter);
        """)
        self.assertIn('OK', ut)

    def test_korpsnavn_escapes_i_velgeren(self):
        ut = run_node(self.harness, """
            const el = {innerHTML: '', value: ''};
            globalThis.document = {getElementById: () => el};
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {korps: [{id: 1, navn: '<img src=x onerror=alert(1)>', kortnavn: ''}]};
            globalThis.korpsfilter = null; globalThis.utskriftRessurs = null;
            fyllKorpsvelger();
            console.log(el.innerHTML);
        """)
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)


class ProbonoOgDagoverskrifterTests(SimpleTestCase):
    """Runde 2b fra prosjektleder (11. sep. 2026).

    Probono: skiftet går, men telles ikke i timesummene — merket står ved
    navnet, timene i raden står som før. Dagoverskrifter: «Fredag 2. okt»
    over blokkene når vakta spenner over flere dager; starttiden bestemmer
    dagen; en endagsvakt ser ut som før.
    """

    HARNESS = TidsblokkerTests.HARNESS
    VINDU = TidsblokkerTests.VINDU
    LISTE = TidsblokkerTests.LISTE

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _oversikt(self, ekstra=''):
        return run_node(self.harness, self.VINDU + self.LISTE + ekstra
                        + "console.log(mkOversikt());")

    # ── Probono ──────────────────────────────────────────────────────────
    def test_summen_hopper_over_probono(self):
        run_node(self.harness, """
            const sum = _sumTimer([
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2026-10-03T16:00:00'},
              {fra_tid: '2026-10-03T16:00:00', til_tid: '2026-10-04T00:00:00', probono: true},
            ]);
            assert(sum === 8, 'fikk ' + sum);
        """)

    def test_blokklinja_viser_skiftets_lengde_uansett(self):
        """Blokkas timer er skiftets lengde — det er summene som hopper over
        probono, ikke raden."""
        ut = run_node(self.harness, self.VINDU + """
            console.log(_blokklinje({fra_tid: '2026-10-03T08:00:00',
                                     til_tid: '2026-10-03T16:00:00',
                                     poster: [{ledig: false, probono: true}]}, 4));
        """)
        self.assertIn('8 t', ut)

    def test_merket_staar_ved_navnet_i_oversikten(self):
        ut = self._oversikt("aktivListe.vaktposter[3].probono = true;\n")
        self.assertIn('Kari <span class="vl-merkelapp vl-probono">Probono</span>', ut)
        self.assertNotIn('Ola <span', ut)

    def test_ressursens_sum_hopper_over_probono(self):
        """Ambulanse 1: Karis skift på 10 t er probono → «0 t» i overskriften."""
        ut = self._oversikt("aktivListe.vaktposter[3].probono = true;\n")
        amb1 = ut[ut.index('<h3>Ambulanse 1'):ut.index('<h3>Ambulanse 2')]
        self.assertIn('1 mannskap · 0 t', amb1)

    def test_driftraden_baerer_merket(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.rollerForGruppe = () => []; globalThis.kanStemple = () => true;
            globalThis.aktivListe = {vaktliste: {i_drift: true}};
            console.log(_driftrad({id: 5, ledig: false, navn: 'Kari', probono: true,
                                   korps_kort: 'HGSD', rolle: '', mott_at: null,
                                   av_vakt_at: null, tilstede: false,
                                   fra_tid: '2026-10-03T08:00:00',
                                   til_tid: '2026-10-03T16:00:00'}, {id: 1, gruppe_id: 1}, true));
        """)
        self.assertIn('vl-probono', ut)

    # ── Dagen som nøkkel ─────────────────────────────────────────────────
    def test_starttiden_bestemmer_dagen(self):
        """Et skift 17:00–03:00 er fredagens, selv om det slutter lørdag —
        og et som begynner 00:30 lørdag er lørdagens. **Bekreftet på nytt
        15. sep. 2026**, da «Oversikt» fikk dagen ytterst: André valgte
        startdagen framfor begge dager og framfor splitting ved midnatt."""
        run_node(self.harness, """
            assert(_dagnokkel('2026-09-04T17:00:00') === _dagnokkel('2026-09-04T23:59:00'),
                   'samme dag');
            assert(_dagnokkel('2026-09-04T17:00:00') !== _dagnokkel('2026-09-05T00:30:00'),
                   'over midnatt er neste dag');
            assert(_dagnokkel(null) === '', 'ugyldig gir tom noekkel');
        """)

    def test_noekkelen_sorterer_som_dato(self):
        """Nøkkelen sorteres av `_grupperPaaDag`, så den må være nullpolstret:
        `2026-9-15` < `2026-9-4` som tekst, og da kom 15. før 4."""
        run_node(self.harness, """
            const fjerde = _dagnokkel('2026-09-04T17:00:00');
            const femtende = _dagnokkel('2026-09-15T17:00:00');
            assert(fjerde < femtende, fjerde + ' skal sortere foer ' + femtende);
            assert(_dagnokkel('2026-09-04T00:00:00') < _dagnokkel('2026-10-01T00:00:00'),
                   'september foer oktober');
        """)

    def test_overskriften_bare_der_dagen_skifter(self):
        """To blokker på samme dag deler én overskrift."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {vaktliste: {i_drift: false}};
            const rad = () => '';
            const blokker = _tidsblokker([
              {fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-04T22:00:00', navn: 'A'},
              {fra_tid: '2026-09-04T22:00:00', til_tid: '2026-09-05T03:00:00', navn: 'B'},
              {fra_tid: '2026-09-05T08:00:00', til_tid: '2026-09-05T16:00:00', navn: 'C'},
            ]);
            console.log(_blokkerMedDager(blokker, 4, rad));
        """)
        self.assertEqual(ut.count('class="vl-dag"'), 2)
        self.assertEqual(ut.count('class="vl-blokk"'), 3)

    def test_endagsvakt_faar_ogsaa_dagoverskrift(self):
        """**Snudd 15. sep. 2026** (André: «alltid»). Fram til da sto
        overskriften bare på flerdagsvakter, og da måtte planleggeren vite at
        *fraværet* av en dagrad betydde noe."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {vaktliste: {i_drift: false}};
            const rad = () => '';
            const blokker = _tidsblokker([
              {fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-04T22:00:00', navn: 'A'},
              {fra_tid: '2026-09-04T22:00:00', til_tid: '2026-09-04T23:00:00', navn: 'B'},
            ]);
            console.log(_blokkerMedDager(blokker, 4, rad));
        """)
        self.assertEqual(ut.count('class="vl-dag"'), 1)
        self.assertIn('Fredag 4. sep', ut)


class DagenErYtterstTests(SimpleTestCase):
    """«Oversikt» snudd: dag ytterst, ressurs under (André, 14.–15. sep. 2026).

    *«oversikten [skal] bare vise hvem som er på vakt og hvilken ressurs de er
    på på dag … ikke silt etter ressurs først og så dag, men faktisk silt etter
    dag så ressurs.»*

    **Lesemodellen er en annen.** Før svarte lista på «hvem står på denne
    bilen, og når» — den som leste sto ved bilen. Nå svarer den på «hvem er på
    vakt i dag, og hvor», som er det den som møter om morgenen spør om.
    """

    HARNESS = VaktlisteEscapingOppforselTests.HARNESS
    VINDU = TidsblokkerTests.VINDU
    LISTE = TidsblokkerTests.LISTE

    #: Nina står på samleplassen lørdag; resten av Andrés rader er fredag.
    LORDAG = """
        aktivListe.vaktposter.push({id: 9, ressurs_id: 10, ledig: false, navn: 'Nina',
          korps_kort: 'HGSD', rolle: '', merknad: '',
          fra_tid: '2026-09-05T08:00:00', til_tid: '2026-09-05T16:00:00'});
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _oversikt(self, ekstra=''):
        return run_node(self.harness, self.VINDU + self.LISTE + ekstra
                        + "console.log(mkOversikt());")

    def test_dagen_staar_over_ressursen(self):
        """Kjernen i snuingen: dagtittelen kommer før ressursoverskriften."""
        ut = self._oversikt()
        self.assertLess(ut.index('class="vl-dagtittel"'), ut.index('<h3>Samleplass'),
                        'dagen skal staa ytterst, ressursen under')

    def test_endagsvakt_faar_ogsaa_en_dagtittel(self):
        """Andrés rader er alle 4. sep. Overskriften står likevel — André,
        15. sep. 2026: «alltid»."""
        ut = self._oversikt()
        self.assertEqual(ut.count('class="vl-dagtittel"'), 1)
        self.assertIn('Fredag 4. sep', ut)

    def test_hver_dag_faar_sin_bolk_i_kronologisk_rekkefolge(self):
        ut = self._oversikt(self.LORDAG)
        self.assertEqual(ut.count('class="vl-dagbolk"'), 2)
        self.assertIn('Fredag 4. sep', ut)
        self.assertIn('Lørdag 5. sep', ut)
        self.assertLess(ut.index('Fredag 4. sep'), ut.index('Lørdag 5. sep'))

    def test_ressursen_gjentas_under_hver_dag_den_har_skift(self):
        """Samleplassen har skift begge dager og skal stå i begge bolkene —
        det er nettopp det snuingen koster, og det er riktig her."""
        ut = self._oversikt(self.LORDAG)
        self.assertEqual(ut.count('<h3>Samleplass'), 2)

    def test_dagbolken_viser_bare_sin_egen_dags_skift(self):
        """Nina står lørdag. Hun skal ikke dukke opp i fredagsbolken."""
        ut = self._oversikt(self.LORDAG)
        fredag = ut[ut.index('Fredag 4. sep'):ut.index('Lørdag 5. sep')]
        self.assertNotIn('Nina', fredag)
        self.assertIn('Nina', ut[ut.index('Lørdag 5. sep'):])

    def test_skift_over_midnatt_staar_bare_under_startdagen(self):
        """Andrés samleplass-skift går 17:00 fredag til 03:00 lørdag. Det
        står under fredag, **ikke** under begge og ikke splittet (André,
        15. sep. 2026). Merk at rapportmodulen har landet motsatt for timer;
        forskjellen er bevisst."""
        ut = self._oversikt(self.LORDAG)
        lordag = ut[ut.index('Lørdag 5. sep'):]
        self.assertNotIn('17:00', lordag)

    def test_ingen_dagrader_inne_i_tabellen(self):
        """Dagen står i overskriften over tabellen. En `vl-dag`-rad inni ville
        sagt det samme to ganger på rad — derfor `_blokkrader` her."""
        self.assertNotIn('class="vl-dag"', self._oversikt(self.LORDAG))

    def test_arkhodet_summerer_fortsatt_hele_vakta(self):
        """Summene per ressurs er per dag etter snuingen; totalen er ikke."""
        ut = self._oversikt(self.LORDAG)
        arkhode = ut[ut.index('vl-arkhode'):ut.index('class="vl-dagbolk"')]
        self.assertIn('t', arkhode)
        self.assertIn('skift', arkhode)

    def test_grupperingen_sorterer_selv(self):
        """**Hjelperen skal ikke hvile på at den som kaller har sortert.**
        Serveren sender `fra_tid` stigende i dag, men `mkOversikt` filtrerer
        og korpsvelgeren kan gripe inn — og uten den egne sorteringen målte
        testen bare serverens rekkefølge. Samme grunn som `_hviletider()`
        sorterer selv (`CLAUDE.md`)."""
        run_node(self.harness, """
            const dager = _grupperPaaDag([
              {id: 1, fra_tid: '2026-09-15T08:00:00'},
              {id: 2, fra_tid: '2026-09-04T08:00:00'},
              {id: 3, fra_tid: '2026-10-01T08:00:00'},
              {id: 4, fra_tid: '2026-09-04T20:00:00'},
            ]);
            assert(dager.length === 3, 'tre dager, fikk ' + dager.length);
            const rekke = dager.map((d) => d.nokkel).join(' ');
            assert(rekke === '2026-09-04 2026-09-15 2026-10-01', 'rekkefolge: ' + rekke);
            assert(dager[0].poster.length === 2, 'de to 4. sep. samles');
        """)

    def test_ressurskortet_har_ingen_dagrader(self):
        """**Snudd 15. sep. 2026** (André: «i ressursgruppene må det være likt
        som oversikt — ressurser per dag»).

        Fram til da var gruppefanen en stabel ressurskort med dagrader inni,
        mens «Oversikt» hadde dagen som nivå over. Nå er dagen ytterste nivå
        begge steder, og kortet tegner den ene dagens skift. En `vl-dag`-rad
        inni ville gjentatt seksjonstittelen rett over.

        «Mitt korps» er den tredje flaten og beholder dagrader — den har én
        tabell på tvers av ressursene, så dagen har ingen seksjon å stå i."""
        ut = run_node(self.harness, self.VINDU + self.LISTE + self.LORDAG + """
            globalThis.rollerForGruppe = () => [];
            console.log(mkRessurs({id: 10, navn: 'Samleplass', gruppe_id: 1,
                                   gruppe_navn: 'Samleplass', ikon: 'hospital'}));
        """)
        self.assertNotIn('class="vl-dag"', ut)


class MittKorpsTests(SimpleTestCase):
    """«Mitt korps»-fanen (11. sep. 2026): plassene korpset har ansvar for,
    på tvers av ressursene — tildelte og universale, ledige først."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkMittKorps', '_mittKorpsId', '_synligePoster',
                        'kanBemannePlass', 'kanSkriveAlt', '_nivaa', '_erAdmin',
                        '_fyllValgFor', 'opptattPaaPlassen', '_probonoMerke', '_tidsblokker',
                        '_blokkerMedDager', '_blokkrader', '_dagnokkel', '_dagoverskrift', '_dagtekst',
                        '_blokklinje', '_telling', '_skiftrekkefolge',
                        '_varighet', '_skifttimer', '_tall', '_d', '_kl',
                        '_dag', '_sammeDag', '_tidsspenn', '_korpsKropp',
                        '_plassKorps', '_sumTimer')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n"
             "globalThis.korpsfilter = null;\n")
    LISTE = """
        globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
        globalThis.aktivListe = {
          vaktliste: {i_drift: false},
          korps: [{id: 1, navn: 'Haugesund', kortnavn: 'HGSD'},
                  {id: 2, navn: 'Karmøy', kortnavn: 'KARM'}],
          ressurser: [{id: 10, navn: 'Samleplass', gruppe_id: 1, korps_id: null},
                      {id: 20, navn: 'Ambulanse 1', gruppe_id: 2, korps_id: 1}],
          mannskap: [{id: 1, navn: 'Kari', korps_navn: 'Haugesund'}],
          vaktposter: [
            {id: 1, ressurs_id: 10, ledig: true, navn: '', korps_id: null, korps_kort: '',
             reservert_korps_id: null, alle_korps: true, rolle: '', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'},
            {id: 2, ressurs_id: 10, ledig: true, navn: '', korps_id: null, korps_kort: '',
             reservert_korps_id: 2, alle_korps: false, rolle: '', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'},
            {id: 3, ressurs_id: 10, ledig: true, navn: '', korps_id: null, korps_kort: '',
             reservert_korps_id: null, alle_korps: false, rolle: '', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'},
            {id: 4, ressurs_id: 20, ledig: false, navn: 'Kari', korps_id: 1, korps_kort: 'HGSD',
             reservert_korps_id: 1, alle_korps: false, rolle: 'Sjåfør', merknad: '',
             fra_tid: '2026-09-04T17:00:00', til_tid: '2026-09-05T03:00:00'}]};
        aktivListe.alle_vaktposter = aktivListe.vaktposter;
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _som(self, nivaa, mitt, ekstra=''):
        vindu = (f"globalThis.window = {{ MODUL_TILGANG: {{ vaktliste: '{nivaa}', admin: false }},"
                 f" MITT_KORPS_ID: {mitt} }};\n")
        return run_node(self.harness, self.VINDU + vindu + self.LISTE + ekstra
                        + "console.log(mkMittKorps());")

    def test_korpsbrukeren_ser_sine_og_de_universale(self):
        ut = self._som('skriv_handling', 1)
        self.assertIn('<b>1</b><span class="vl-meta">plass å dekke</span>', ut,
                      'én universal plass å dekke')
        self.assertIn('Kari', ut, 'og sitt eget mannskap')
        self.assertNotIn('KARM', ut, 'Karmøys plass er ikke hennes')

    def test_planlagt_plass_vises_ikke(self):
        """Plass 3 er vaktlederens bord."""
        run_node(self.harness, self.VINDU + self.LISTE + """
            const mine = _synligePoster(aktivListe.vaktposter, 1);
            assert(JSON.stringify(mine.map((v) => v.id)) === '[1,4]', JSON.stringify(mine.map((v) => v.id)));
        """)

    def test_universal_plass_kan_fylles_av_korpsbrukeren(self):
        ut = self._som('skriv_handling', 1)
        self.assertIn('vl-fyll', ut, 'nedtrekket for å fylle plassen')

    def test_uten_korps_finnes_ingen_fane(self):
        run_node(self.harness, self.VINDU + """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'les', admin: false }, MITT_KORPS_ID: null };
            assert(_mittKorpsId() === null, 'ingen badge, ingen velger: null');
            globalThis.korpsfilter = 2;
            assert(_mittKorpsId() === 2, 'korpsvelgeren vinner');
        """)

    def test_korpsvelgeren_styrer_fanen_for_den_som_ser_alle(self):
        ut = self._som('skriv_full', 'null', "globalThis.korpsfilter = 2;\n")
        self.assertIn('Karmøy', ut)
        self.assertIn('2</b>', ut, 'to plasser å dekke: Karmøys og den universale')

    def test_kanBemannePlass_speiler_serveren(self):
        run_node(self.harness, self.VINDU + """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_handling', admin: false }, MITT_KORPS_ID: 1 };
            const r = {korps_id: null};
            assert(kanBemannePlass({alle_korps: true, reservert_korps_id: null}, r), 'universal');
            assert(kanBemannePlass({alle_korps: false, reservert_korps_id: 1}, r), 'egen');
            assert(!kanBemannePlass({alle_korps: false, reservert_korps_id: 2}, r), 'andres');
            assert(!kanBemannePlass({alle_korps: false, reservert_korps_id: null}, r), 'planlagt');
            globalThis.window.MITT_KORPS_ID = null;
            assert(!kanBemannePlass({alle_korps: true, reservert_korps_id: null}, r), 'uten badge');
        """)

    def test_korpsKropp_oversetter_de_tre_tilstandene(self):
        run_node(self.harness, """
            assert(JSON.stringify(_korpsKropp('korps_id', 'alle')) === '{"alle_korps":true,"korps_id":null}', 'alle');
            assert(JSON.stringify(_korpsKropp('korps_id', '2')) === '{"alle_korps":false,"korps_id":"2"}', 'ett korps');
            assert(JSON.stringify(_korpsKropp('korps_id', '')) === '{"alle_korps":false,"korps_id":null}', 'planlagt');
            assert(JSON.stringify(_korpsKropp('merknad', 'x')) === '{"merknad":"x"}', 'andre felt uroert');
        """)

    def test_plassKorps_viser_alle_korps(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_full', admin: false }, MITT_KORPS_ID: null };
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {korps: [{id: 1, navn: 'Haugesund', kortnavn: 'HGSD'}]};
            console.log(_plassKorps({id: 9, alle_korps: true, plass_korps_id: null, reservert_korps_id: null}));
            globalThis.window.MODUL_TILGANG.vaktliste = 'les';
            console.log(_plassKorps({id: 9, alle_korps: true, plass_korps_id: null, reservert_korps_id: null}));
        """)
        self.assertIn('value="alle" selected', ut)
        # Delt ut: «Planlagt» tilbys ikke lenger — veien går én vei.
        self.assertNotIn('>Planlagt</option>', ut)
        self.assertIn('>Åpen for alle</span>', ut)
        planlagt = run_node(self.harness, self.VINDU + """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_full', admin: false }, MITT_KORPS_ID: null };
            globalThis.utskriftRessurs = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {korps: [{id: 1, navn: 'Haugesund', kortnavn: 'HGSD'}]};
            console.log(_plassKorps({id: 9, alle_korps: false, plass_korps_id: null, reservert_korps_id: null}));
        """)
        self.assertIn('<option value="" selected>Planlagt</option>', planlagt)

    def test_ressursnavn_escapes(self):
        ut = self._som('skriv_handling', 1,
                       "aktivListe.ressurser[0].navn = '<img src=x onerror=alert(1)>';\n")
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)


class UtskriftsutvalgTests(SimpleTestCase):
    """Utskrift per korps eller per ressurs (André, 12. sep. 2026).

    Korpset kommer fra korpsvelgeren (alt filtrert i `aktivListe.vaktposter`),
    ressursen fra velgeren over lista. Arket sier selv hva det er avgrenset
    til — velgeren kommer ikke med på papiret.
    """

    HARNESS = TidsblokkerTests.HARNESS
    VINDU = TidsblokkerTests.VINDU
    LISTE = UtskriftslistaTests.LISTE

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _oversikt(self, ekstra=''):
        return run_node(self.harness, self.VINDU + self.LISTE + ekstra
                        + "console.log(mkOversikt());")

    def test_valgt_ressurs_gir_bare_den_ressursen(self):
        ut = self._oversikt("globalThis.utskriftRessurs = 20;\n")
        self.assertEqual(ut.count('vl-korpsgruppe'), 1)
        self.assertIn('<h3>Ambulanse 1', ut)
        self.assertNotIn('<h3>Ambulanse 2', ut)
        self.assertNotIn('<h3>Samleplass', ut)
        # Summene i arkhodet er utvalgets, ikke hele vaktas.
        self.assertIn('1 skift · 1 mannskap · 10 t', ut)

    def test_arket_sier_hva_det_er_avgrenset_til(self):
        hele = self._oversikt()
        self.assertNotIn('vl-utvalg"', hele)
        ressurs = self._oversikt("globalThis.utskriftRessurs = 20;\n")
        self.assertIn('<div class="vl-utvalg">Ambulanse 1</div>', ressurs)
        begge = self._oversikt("globalThis.utskriftRessurs = 20; globalThis.korpsfilter = 1;\n")
        self.assertIn('<div class="vl-utvalg">Haugesund · Ambulanse 1</div>', begge)

    def test_velgeren_lister_ressursene_med_skift_og_merker_den_valgte(self):
        ut = self._oversikt("globalThis.utskriftRessurs = 21;\n")
        self.assertIn('<option value="">Hele vakten</option>', ut)
        self.assertIn('<optgroup label="Ambulanse">', ut)
        self.assertIn('<option value="21" selected>Ambulanse 2</option>', ut)
        self.assertIn('<option value="20">Ambulanse 1</option>', ut)
        self.assertIn('data-action="velgUtskrift" data-hendelse="change"', ut)
        self.assertIn('data-action="skrivUt"', ut)

    def test_ressursnavn_i_velgeren_escapes(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            aktivListe.ressurser[1].navn = '<b>Bil</b>';
            console.log(mkUtskriftsverktoy());
        """)
        self.assertNotIn('<b>Bil</b>', ut)
        self.assertIn('&lt;b&gt;Bil&lt;/b&gt;', ut)


class HendelsedelegeringTests(SimpleTestCase):
    """`data-hendelse="change"` har sin egen delegering (12. sep. 2026).

    Klikkdelegeringen hopper over slike elementer med vilje
    (`klikkSkalKjore`), og fram til nå fantes det ingen lytter for `change`
    utenfor vaktlistas ressurspanel. Korpsvelgeren i vaktlinja hadde riktig
    markup og en handling som virket når den ble kalt — og ingen kalte den.
    André: «Når vi setter til et korps i nedtrekksvinduet så vises fortsatt
    alt i oversikt.»
    """

    HARNESS = ((PORTAL_UTILS_JS, ('hendelseArgumenter', 'haandterHendelse',
                                  '_handlerArgument')),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_korpsvelgeren_kaller_handlingen_sin(self):
        run_node(self.harness, """
            let kalt = [];
            globalThis.velgKorps = (...a) => kalt.push(a);
            const el = { dataset: { action: 'velgKorps', hendelse: 'change' }, value: '2' };
            haandterHendelse({ target: { closest: () => el } });
            assert(kalt.length === 1, 'handlingen ble kalt ' + kalt.length + ' ganger');
            assert(kalt[0].length === 1 && kalt[0][0] === undefined, 'ett argument, uten id: ' + JSON.stringify(kalt[0]));
        """)

    def test_cellene_i_ressurstabellen_faar_id_felt_og_verdi(self):
        run_node(self.harness, """
            let kalt = null;
            globalThis.endreVaktpost = (...a) => { kalt = a; };
            const el = { dataset: { action: 'endreVaktpost', hendelse: 'change',
                                    felt: 'rolle_id', id: '7' }, value: '3' };
            haandterHendelse({ target: { closest: () => el } });
            assert(JSON.stringify(kalt) === '[7,"rolle_id","3"]', 'fikk ' + JSON.stringify(kalt));
        """)

    def test_uten_treff_eller_uten_handling_skjer_ingenting(self):
        run_node(self.harness, """
            haandterHendelse({ target: { closest: () => null } });
            const el = { dataset: { action: 'finnesIkke', hendelse: 'change' }, value: '' };
            haandterHendelse({ target: { closest: () => el } });
        """)


class EgenPersonPaaAndresPlassJsTests(SimpleTestCase):
    """`kanRoreRad` speiler `services.kan_rore_vaktpost` (12. sep. 2026)."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('kanRoreRad', 'kanBemannePlass', 'kanSkriveAlt', '_nivaa', '_erAdmin')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_egen_person_paa_karmoys_plass_er_egen_rad(self):
        run_node(self.harness, """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_handling' }, MITT_KORPS_ID: 1 };
            const karmoy = { id: 20, korps_id: 2 };
            assert(kanRoreRad({ledig: false, korps_id: 1, reservert_korps_id: 2}, karmoy, false), 'egen person: egen rad');
            assert(!kanRoreRad({ledig: false, korps_id: 2, reservert_korps_id: 2}, karmoy, false), 'deres person: deres rad');
            assert(!kanRoreRad({ledig: true, korps_id: null, reservert_korps_id: 2}, karmoy, false), 'tom plass hos dem: deres');
            assert(kanRoreRad({ledig: true, korps_id: null, reservert_korps_id: 1}, karmoy, false), 'tom plass satt av til meg');
            assert(kanRoreRad({ledig: true, korps_id: null, reservert_korps_id: 2}, karmoy, true), 'ressursen min: tom plass');
            assert(!kanRoreRad({ledig: false, korps_id: 2, reservert_korps_id: 1}, {id: 10, korps_id: 1}, true), 'deres person på min ressurs: deres rad');
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_full' }, MITT_KORPS_ID: null };
            assert(kanRoreRad({ledig: false, korps_id: 2, reservert_korps_id: 1}, {id: 10, korps_id: 1}, true), 'skriv_full: alt');
        """)


class ForeslaaTilTests(SimpleTestCase):
    """Til-tiden foreslås som fra + 8 t når den er tom eller før fra
    (André, 12. sep. 2026). Et til som alt står etter fra røres ikke."""

    HARNESS = ((VAKTLISTE_JS, ('foreslaaTil', '_plussTimer', '_iso16', '_d')),)

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    DOM = """
        const felter = { fra: { value: '2026-10-03T08:00' }, til: { value: '' } };
        globalThis.document = { getElementById: (id) => felter[id] };
    """

    def test_tom_til_blir_fra_pluss_aatte(self):
        run_node(self.harness, self.DOM + """
            foreslaaTil('fra', 'til');
            assert(felter.til.value === '2026-10-03T16:00', 'fikk ' + felter.til.value);
        """)

    def test_til_foer_fra_flyttes_men_til_etter_fra_staar(self):
        run_node(self.harness, self.DOM + """
            felter.til.value = '2026-10-03T06:00';
            foreslaaTil('fra', 'til');
            assert(felter.til.value === '2026-10-03T16:00', 'før fra: ' + felter.til.value);
            felter.til.value = '2026-10-03T12:00';
            foreslaaTil('fra', 'til');
            assert(felter.til.value === '2026-10-03T12:00', 'etter fra skal stå: ' + felter.til.value);
        """)

    def test_over_midnatt(self):
        run_node(self.harness, self.DOM + """
            felter.fra.value = '2026-10-03T20:00';
            foreslaaTil('fra', 'til');
            assert(felter.til.value === '2026-10-04T04:00', 'fikk ' + felter.til.value);
        """)


class MittKorpsTimerTests(SimpleTestCase):
    """Timene i «Mitt korps»: bemannet, å dekke for korpset, åpent for alle og
    probono hver for seg."""

    HARNESS = MittKorpsTests.HARNESS
    VINDU = MittKorpsTests.VINDU
    LISTE = MittKorpsTests.LISTE

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_avsatt_og_probono_summeres_hver_for_seg(self):
        ut = run_node(self.harness, self.VINDU + self.LISTE + """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_handling' }, MITT_KORPS_ID: 1 };
            aktivListe.vaktposter[3].probono = true;
            console.log(mkMittKorps());
        """)
        # HGSD ser plass 1 (alle korps, 10 t) og Kari (10 t, probono).
        # Bemannet teller organisasjonens timer — Kari er probono, så 0 t.
        # Å dekke er den ledige plassen. Ett samlet «avsatt» blandet de to.
        self.assertIn('<b>0 t</b><span class="vl-meta">bemannet</span>', ut)
        # Plass 1 er åpen for alle — ikke korpsets å dekke (André, 12. sep.
        # 2026: «32 t å dekke som strengt tatt er åpent for alle»).
        self.assertIn('<b>0 t</b><span class="vl-meta">å dekke for korpset</span>', ut)
        self.assertIn('<b>10 t</b><span class="vl-meta">åpent for alle</span>', ut)
        self.assertIn('<b>10 t</b><span class="vl-meta">probono</span>', ut)
        self.assertNotIn('avsatt', ut)
        # Og en ledig plass med probono viser merket (André: «ser ingen merke der»).
        ut2 = run_node(self.harness, self.VINDU + self.LISTE + """
            globalThis.window = { MODUL_TILGANG: { vaktliste: 'skriv_handling' }, MITT_KORPS_ID: 1 };
            aktivListe.vaktposter[0].probono = true;
            console.log(mkMittKorps());
        """)
        self.assertIn('vl-probono', ut2)


class ArkiverteVaktlisterTests(SimpleTestCase):
    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkArkiverteVaktlister', '_dag', '_kl', '_d')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_lista_med_hent_tilbake_og_escaping(self):
        ut = run_node(self.harness, MittKorpsTests.VINDU + """
            console.log(mkArkiverteVaktlister([{id: 4, vakt_navn: '<b>TEST</b>', arkivert_at: '2026-09-12T10:00:00'}]));
            console.log(mkArkiverteVaktlister([]));
        """)
        self.assertIn('&lt;b&gt;TEST&lt;/b&gt;', ut)
        self.assertIn('data-action="gjenopprettVaktliste" data-id="4"', ut)
        self.assertIn('Ingen arkiverte vaktlister', ut)


class DupliserVaktpostTests(SimpleTestCase):
    """«Dupliser som ledig plass» (André, 12. sep. 2026): en plass til med
    samme spenn, rolle og reservasjon — men uten personen."""

    HARNESS = ((VAKTLISTE_JS, ('dupliserVaktpost', '_tidFraFelt', '_korpsKropp')),)

    PREAMBLE = """
      globalThis.sendt = null;
      globalThis.felter = {
        'vaktpostModal': {dataset: {vaktpost: '7'}},
        'vaktpost-fra': {value: '2026-10-03T08:00'},
        'vaktpost-til': {value: '2026-10-03T16:00'},
        'vaktpost-rolle': {value: '3'},
        'vaktpost-korps': {value: '2'},
        'vaktpost-probono': {checked: true},
        'vaktpost-mannskap': {value: '11'},
      };
      globalThis.document = { getElementById: (id) => felter[id] || null };
      globalThis.aktivListe = {vaktliste: {id: 3},
        vaktposter: [{id: 7, ressurs_id: 20, mannskap_id: 11, navn: 'Kari'}]};
      globalThis._skjulFeil = () => {};
      globalThis._visFeil = (id, m) => { globalThis.feilmelding = m; };
      globalThis.lukket = false;
      globalThis._lukkModal = () => { globalThis.lukket = true; };
      globalThis.lastet = null;
      globalThis.lastListe = async (id) => { globalThis.lastet = id; };
      globalThis.apiFetch = async (url, opts) => {
        globalThis.sendt = {url, method: opts.method, body: JSON.parse(opts.body)};
        return {ok: true, json: async () => ({status: 'ok', data: {id: 8}})};
      };
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_oppretter_en_ledig_plass_paa_samme_ressurs(self):
        run_node(self.harness, """
          await dupliserVaktpost();
          assert(sendt, 'ingen forespørsel');
          assert(sendt.url === '/vaktliste/api/ressurser/20/vaktposter/', sendt.url);
          assert(sendt.method === 'POST', sendt.method);
          assert(sendt.body.fra_tid === '2026-10-03T08:00', 'fra');
          assert(sendt.body.til_tid === '2026-10-03T16:00', 'til');
          assert(sendt.body.rolle_id === '3', 'rolle');
          assert(sendt.body.korps_id === '2' && sendt.body.alle_korps === false, 'korps');
          assert(sendt.body.probono === true, 'probono');
          assert(!('mannskap_id' in sendt.body), 'personen skal ikke kopieres');
          assert(lukket && lastet === 3, 'vinduet lukkes og lista lastes');
        """, preamble=self.PREAMBLE)

    def test_feil_vises_i_vinduet(self):
        run_node(self.harness, """
          globalThis.apiFetch = async () => ({ok: false, json: async () => ({status: 'error', message: 'Nei'})});
          await dupliserVaktpost();
          assert(feilmelding === 'Nei', feilmelding);
          assert(!lukket, 'vinduet står');
        """, preamble=self.PREAMBLE)


class ArkivbolkenTests(SimpleTestCase):
    """«Arkiv» ved siden av «Arkiver vaktlisten» åpner sitt eget vindu (André,
    12. sep. 2026), og «Slett vaktlisten» krever to bekreftelser."""

    HARNESS = ((VAKTLISTE_JS, ('visArkiverteVaktlister', 'slettVaktliste', '_byttModal')),)

    PREAMBLE = """
      const klasser = (init) => {
        const s = new Set(init);
        return {contains: (c) => s.has(c), add: (c) => s.add(c), remove: (c) => s.delete(c)};
      };
      globalThis.felter = {
        'vakt-arkiverte': {classList: klasser([]), innerHTML: ''},
        'vaktModal': {classList: klasser(['show']), lyttere: {},
                      addEventListener(navn, fn) { this.lyttere[navn] = fn; }},
      };
      globalThis.document = { getElementById: (id) => felter[id] || null };
      globalThis.hentet = 0;
      globalThis.lastArkiverteVaktlister = async () => { globalThis.hentet += 1; };
      globalThis.aapnet = []; globalThis.lukket = [];
      globalThis._apneModal = (id) => aapnet.push(id);
      globalThis._lukkModal = (id) => {
        lukket.push(id);
        const el = felter[id];
        if (el && el.lyttere && el.lyttere['hidden.bs.modal']) {
          el.classList.remove('show'); el.lyttere['hidden.bs.modal']();
        }
      };
      globalThis._skjulFeil = () => {};
      globalThis.aktivListe = {vaktliste: {id: 5, vakt_navn: 'Høstvakten'}};
      globalThis.sendt = null;
      globalThis.apiFetch = async (url, opts) => {
        globalThis.sendt = {url, method: opts.method, body: JSON.parse(opts.body)};
        return {ok: true, json: async () => ({status: 'ok'})};
      };
      globalThis._visFeil = (id, m) => { globalThis.feilmelding = m; };
      globalThis.lastVaktlister = async () => { globalThis.lastetLister = true; };
      globalThis.svar = [];
      globalThis.confirm = () => svar.shift();
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_arkivet_aapnes_i_eget_vindu_etter_at_vaktvinduet_er_lukket(self):
        run_node(self.harness, """
          await visArkiverteVaktlister();
          assert(lukket.join() === 'vaktModal', 'vaktvinduet lukkes først: ' + lukket);
          assert(aapnet.join() === 'vaktArkivModal', 'arkivvinduet åpnes: ' + aapnet);
          assert(hentet === 1, 'lista hentes');
        """, preamble=self.PREAMBLE)

    def test_er_vaktvinduet_alt_lukket_aapnes_arkivet_direkte(self):
        run_node(self.harness, """
          felter['vaktModal'].classList.remove('show');
          await visArkiverteVaktlister();
          assert(lukket.length === 0, 'ingenting å lukke');
          assert(aapnet.join() === 'vaktArkivModal', aapnet);
        """, preamble=self.PREAMBLE)

    def test_sletting_krever_to_ja(self):
        run_node(self.harness, """
          svar = [true, false];
          await slettVaktliste();
          assert(sendt === null, 'ett ja er ikke nok');
          svar = [true, true];
          await slettVaktliste();
          assert(sendt.method === 'DELETE' && sendt.url === '/vaktliste/api/vaktlister/5/', JSON.stringify(sendt));
          assert(sendt.body.confirm === true, 'confirm i kroppen');
          assert(lukket.includes('vaktModal') && lastetLister, 'vinduet lukkes og velgeren lastes');
        """, preamble=self.PREAMBLE)

    def test_nei_paa_forste_sender_ingenting(self):
        run_node(self.harness, """
          svar = [false, true];
          await slettVaktliste();
          assert(sendt === null, 'nei er nei');
        """, preamble=self.PREAMBLE)
