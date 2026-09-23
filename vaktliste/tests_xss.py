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
    # Grupperaden (16. sep. 2026, pulje 3 punkt 4): den bygger markup fra et
    # gruppenavn og et ikonnavn, begge fritekst fra basen, og sto utenfor
    # skanneren fram til knappene ble lagt til.
    'mkGruppeRad',
    '_fyll',
    'tegnFaner', 'kanPlanlegge', '_fanerad', '_mannskapsfane', 'iDrift', '_tilstede',
    'mkRessurs', '_planrad', '_plancellene', '_blokklinje', '_dagoverskrift', '_probonoMerke',
    # Dagbolkene i gruppefanen (15. sep. 2026). En ny bygger som skanneren
    # ikke leser er nøyaktig det hullet denne lista finnes for.
    '_gruppedagbolker',
    'mkMittKorps', '_plassKorps',
    '_stempelknapper',
    '_driftrad',
    'mkBelastning',
    # Budsjettlinja og dagslinja (15. sep. 2026). De sto én kjøring uten å
    # være her, og da var escaping-regelen stille av for dem — suiten var
    # grønn fordi skanneren ikke leste dem, ikke fordi de var riktige.
    'mkBudsjett', 'mkDagslinje', '_budsjettpost',
    # Planleggeren (15. sep. 2026). En ny bygger som skanneren ikke leser er
    # nøyaktig det hullet denne lista finnes for — det skjedde for
    # budsjettlinja samme dag.
    'mkPlanlegger', '_planleggerLinje', '_planleggerVindu', '_genererFasit',
    '_planleggerHode',
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
    # Fanerekka delt i bolker (16. sep. 2026, pulje 3 punkt 5).
    'slag': 'hardkodet CSS-klasse fra en ternær',
    # Rollerekkefølgen (16. sep. 2026, pulje 3 punkt 6). Begge er markup
    # bygget i funksjonen, med rolle-id escapet inni.
    'opp': 'markup bygget lokalt, rolle-id escapet inni',
    'ned': 'markup bygget lokalt, rolle-id escapet inni',
    "forste ? ' disabled' : ''": 'hardkodet attributt fra en ternær',
    "siste ? ' disabled' : ''": 'hardkodet attributt fra en ternær',
    # Grupperaden (16. sep. 2026, pulje 3 punkt 4). Alle tre er markup
    # bygget i funksjonen; gruppas navn og ikon escapes der de settes inn.
    'inaktivMerke': 'hardkodet merkelapp fra en ternær',
    'ett': 'hardkodet merkelapp fra en ternær',
    'endre': 'markup bygget lokalt, gruppe-id escapet inni',
    # Oversikten som talltabell (16. sep. 2026, pulje 3 punkt 2). Alle tre er
    # tall eller markup bygget i funksjonen; ingen brukerdata passerer.
    'ledigcelle': 'markup bygget lokalt, tallet escapet inni',
    "ledige ? escHtmlValue(ledige) : '—'": 'tall fra en ternær, escapet i den ene grenen',
    'sumrad(dag.poster)': 'markup fra sumrad(), som ligger inne i mkOversikt og skannes med den',
    # Planleggeren (15. sep. 2026).
    'vinduer': 'markup fra `_planleggerVindu`, som selv skannes her',
    'fasitklasse': 'hardkodet CSS-klasse fra en ternær',
    'antallFelt': 'markup bygget lokalt: antallsfeltet med id-en escapet inni, '
                  'eller en fast tekst for grupper i ett eksemplar',
    'fasit': 'markup bygget lokalt: escapet antall skift, eller en fast tekst',
    'slett': 'markup bygget lokalt, indeksene escapet inni',
    # Planleggeren leser oppsettet tilbake (15. sep. 2026).
    'staarTekst': 'markup bygget lokalt, antallet escapet inni — eller tom streng',
    '_planleggerHode(linje)':
        'markup fra en bygger som selv skannes her (radhodet: navn eller nedtrekk)',
    'fjernes': 'markup bygget lokalt, antallet escapet inni — eller tom streng',
    # Budsjettlinja og dagslinja (15. sep. 2026).
    'b': 'markup bygget lokalt i samme funksjon, tallet escapet inni',
    'tak': 'markup fra `_budsjettpost`, som selv skannes her — eller tom streng',
    'igjen': 'markup fra `_budsjettpost`, som selv skannes her — eller tom streng',
    'manglerPost': 'markup fra `_budsjettpost`, som selv skannes her — eller tom streng',
    'knapp': 'markup bygget lokalt, ingen data i seg',
    'celler': 'dagceller bygget lokalt, timer og dagtekst escapet inni',
    "_budsjettpost(p.satt_opp, 'satt opp')":
        'markup fra en bygger som selv skannes her',
    "_budsjettpost(p.bemannet, 'bemannet')":
        'markup fra en bygger som selv skannes her',
    'mkDagslinje(p.dager)': 'markup fra en bygger som selv skannes her',
    "harTak ? 'Endre tak' : 'Sett tak'": 'hardkodet knappetekst fra en ternær',
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
    # Overlappskolonnen (15. sep. 2026), samme form som Faktisk-kolonnen over.
    'overlappHode': 'hardkodet overskrift fra en ternær',
    'overlapp': 'tom streng eller <td> med `overlappTall`, som er escapet over',
    'overlappTall': 'markup bygget lokalt: escapet tall, eller streken',
    'overlappVarsel': 'markup fra varsel(), som escaper teksten den får',
    'bredder': '<col>-markup bygget lokalt, hver andel escapet inni',
    '_tall(s.overlapp)': 'går inn som ren tekst til varsel(), som escaper '
                         'hele strengen',
    'faktiskTall': 'tallet escapet, eller en hardkodet strek',
    'hvileklasse': 'hardkodet CSS-klasse fra en ternær',
    'lengsteklasse': 'hardkodet CSS-klasse fra en ternær',
    'tabellhode': 'markup bygget lokalt: to faste kolonneoppsett, ingen data',
    # Sammenslåtte ressurskort (15. sep. 2026): vippeknappen og tabellen —
    # eller sammendraget i stedet for den — bygges begge i `mkRessurs()`
    # rett over, med id, tilstand og tall escapet inni.
    'vippe': 'markup bygget lokalt, id og tilstand escapet inni',
    # Dagvelgeren over utskriftslista (15. sep. 2026): nedtrekket bygges rett
    # over, med dagnøkkel og dagtekst escapet inni. Tom streng på endagsvakt.
    'velger': 'markup bygget lokalt, dagnoekkel og dagtekst escapet inni',
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue', 'trustedHtml',
                           '_escHtml', 'klokke')),
        (VAKTLISTE_JS, ('mkRessurs', 'ressursErApen', '_radklasse', '_stempelknapper',
                        'kanStemple', 'iDrift', '_rolleValg',
                        'rollerForGruppe', '_fyllValgFor', 'opptattPaaPlassen', '_varighet',
                        'mkRolleRad', 'mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utskriftsdager', '_utvalgstekst', '_skiftrekkefolge',
                        '_planrad', '_plancellene', '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader', 'kanBemannePlass',
                        '_mittKorpsId', '_synligePoster',
                        '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke',
                        '_sumTimer', '_skifttimer', '_tall', '_telling',
                        '_mkEnKurve', 'mkGruppekurve', '_posterIGruppe',
                        'mkGruppe', '_gruppedagbolker', '_plassKorps', '_tegnforklaring',
                        '_timesteg', '_ressurserIGruppe',
                        '_grupperMedRessurser',
                        '_posterPerGruppe', '_vaktensSpenn',
                        'mkIkkePlassert', 'tegnFaner', 'kanPlanlegge', '_fanerad',
                        '_mannskapsfane', '_tilstede', '_posterFor',
                        '_ikkePlassert', '_tidsspenn', '_vaktspenn',
                        '_bemanningPerTime', '_iso16', '_d', '_kl', '_dag',
                        '_sammeDag', '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanSetteOppSkift',
                        'kanLede', 'kanBemanne', 'kanGiNyttNavn', 'kanRoreRad')),
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {self._liste()};
            console.log(mkRessurs({{
              id: 1, navn: 'Lag 1', ikon: '" onload="alert(1)',
              gruppe_navn: 'Lag', korps_navn: '', enhet_navn: ''
            }}));
        ''')
        self.assertNotIn('onload="alert(1)"', ut)

    def test_personnavn_naar_ikke_inn_i_oversikten(self):
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        # **To ting på én gang** (16. sep. 2026). Personnavn står ikke lenger
        # i oversikten — den teller plasser — så den farligste strengen i
        # datasettet skal ikke være der i det hele tatt. Skulle en personrad
        # snike seg inn igjen, fanger `assertNotIn('<script>x')` at den i det
        # minste ikke er uescapet. Ressursnavnet, som *er* der og også er
        # fritekst, dekkes av `test_ressursnavn_i_overskriften_escapes`.
        self.assertNotIn('<script>x', ut)
        self.assertNotIn('&lt;script&gt;', ut, 'navnet skal ikke med i det hele tatt')

    def test_ressursnavn_i_overskriften_escapes(self):
        """Overskriften er ressursens navn fra 30. aug. 2026 — lista er
        gruppert på ressurs, ikke korps. Navnet er fritekst fra basen."""
        ut = run_node(self.harness, self.VINDU + f'''
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.korpsfilter = null; globalThis.utskriftDag = null;
            globalThis.MANNSKAP = 'mannskap';
            globalThis.TILSTEDE = 'tilstede';
            globalThis.BELASTNING = 'belastning';
            globalThis.PLANLEGGER = 'planlegger';
            globalThis.belastning = null;
            globalThis.register = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.korpsfilter = null; globalThis.utskriftDag = null;
            globalThis.MANNSKAP = 'mannskap';
            globalThis.TILSTEDE = 'tilstede';
            globalThis.BELASTNING = 'belastning';
            globalThis.PLANLEGGER = 'planlegger';
            globalThis.belastning = null;
            globalThis.register = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue', 'klokke')),
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue', 'trustedHtml', '_escHtml')),
        (VAKTLISTE_JS, ('mkMannskap', 'mkVerdiliste', '_personKolonne',
                        '_passerPersonsok', '_sorterMannskap', '_nivaa',
                        '_erAdmin', 'kanSkriveAlt', 'kanSetteOppSkift', 'kanSkriveNoe',
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = { vaktposter: [] };
            assert(_bemanningPerTime().length === 0, 'tom liste');
        """)

    def test_urimelig_spenn_tegnes_ikke(self):
        """En feiltastet årstall ville ellers laget hundretusen søyler."""
        run_node(self.harness, """
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = { vaktposter: [
              {fra_tid: '2026-10-03T08:00:00', til_tid: '2099-10-03T08:00:00'},
            ]};
            assert(_bemanningPerTime().length === 0, 'skal gi opp, ikke henge');
        """)

    def test_for_langt_vaktspenn_faller_tilbake_paa_skiftene(self):
        """Kurven var «fullstendig vekke» på en vaktliste der vaktens start lå
        uker før slutten (André, 12. sep. 2026). Skiftene er fortsatt et spenn."""
        run_node(self.harness, """
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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

    #: **Hvitliste, ikke svarteliste** (16. sep. 2026). Lista sto som fem
    #: farlige verdier — `flex`, `grid`, `inline-flex`, `inline-grid`, `block`
    #: — og manglet `inline-block`. Det var nøyaktig den verdien `.vl-blokktid`
    #: hadde, og nøyaktig den som ga André symptomet testen er navngitt etter.
    #:
    #: Enhver `display` som ikke er `table-cell` tar cella ut av kolonnesporet.
    #: En svarteliste over det som bryter må derfor være komplett for å virke,
    #: og den var det ikke — mens hvitlista er komplett av seg selv.
    LOVLIGE = ('table-cell',)

    def _celleklasser(self):
        """Klassene som står på en `<td>` **hvor som helst** i vaktlistas JS.

        **Lista var håndholdt til 16. sep. 2026, og forfalt i stillhet.**
        Den nevnte seks byggere; `blokkrad` i den nye «Oversikt» sto utenfor,
        fikk `.vl-blokktid` på cella — en klasse laget for et `<span>`, med
        `display: inline-block` — og André meldte det samme symptomet som
        ga testen navnet sitt: «kolonnen tid viser seg annerledes enn de
        andre kolonnene, samt linjen er ujevn».

        Det er tredje gang på ett døgn at en håndholdt byggerliste er svaret
        på «hvorfor var ingenting rødt». Nå leses hele kilden, så en ny
        bygger er dekket i det den skrives.
        """
        return {klasse
                for treff in re.findall(r'<td class="([^"$]*)"',
                                        read_js(VAKTLISTE_JS))
                for klasse in treff.split()}

    def _css(self):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'static' / 'css'
                / 'vaktliste.css').read_text(encoding='utf-8')

    def _funn(self, css, klasser):
        """`[(klasse, display), ...]` for celler med ulovlig `display`.

        **Skilt ut som funksjon 16. sep. 2026** — mutasjonsprøven viste at
        regelen bare lot seg prøve mot den *ekte* CSS-en, og der er den grønn
        så snart koden er riktig. Tre mutanter på selve testen overlevde:
        hvitlista kunne slakkes, byggerlista snevres inn, og sperrehaken
        tømmes, uten at noe ble rødt. En vakt som ikke kan bli rød, vokter
        ingenting.
        """
        funn = []
        for klasse in sorted(klasser):
            # Regelblokka der klassen står *alene* som selektor — altså
            # regelen som treffer selve `<td>`-en, ikke `.klasse > .noe`.
            for m in re.finditer(
                    r'(?m)^\.' + re.escape(klasse) + r'\s*\{([^}]*)\}', css):
                display = re.search(r'display:\s*([\w-]+)', m.group(1))
                if display and display.group(1) not in self.LOVLIGE:
                    funn.append((klasse, display.group(1)))
        return funn

    def test_regelen_kjenner_igjen_sin_egen_feil(self):
        """**Sperrehaken.** Mates regelen en celle med `display: inline-block`
        — nøyaktig det `.vl-blokktid` hadde da André meldte «kolonnen tid
        viser seg annerledes enn de andre kolonnene» — skal den slå ut.

        Den prøver hele familien, ikke bare den ene verdien: en hvitliste som
        stille fikk et medlem til ville ellers gått grønn.
        """
        for verdi in ('inline-block', 'block', 'flex', 'grid', 'inline',
                      'contents', 'inline-flex'):
            with self.subTest(display=verdi):
                self.assertEqual(
                    self._funn('.vl-prove {\n  display: %s;\n}' % verdi,
                               {'vl-prove'}),
                    [('vl-prove', verdi)],
                    f'display: {verdi} på en <td> skal fanges')
        self.assertEqual(
            self._funn('.vl-prove {\n  display: table-cell;\n}', {'vl-prove'}), [],
            'table-cell er den ene lovlige')
        self.assertEqual(
            self._funn('.vl-prove {\n  color: red;\n}', {'vl-prove'}), [],
            'ingen display er også greit')

    def test_skanningen_dekker_byggere_den_gamle_lista_ikke_nevnte(self):
        """**Dekningen, ikke bare regelen.**

        Denne erstatter `test_celleklassene_finnes_i_stilarket`, som bare
        krevde at skanningen fant *noe*. To navngitte klasser er strengere —
        finner skanningen ingenting, blir denne rød først — og den gamle lot
        seg dessuten ikke mutere meningsfullt: en test med én assertion
        overlever alltid at assertionen fjernes, med mindre noe tester testen.

        Lista sto håndholdt med seks byggere til 16. sep. 2026, og `blokkrad`
        i «Oversikt» sto utenfor — derfor var ingenting rødt da cella der fikk
        `.vl-blokktid`. Klassene under bygges *bare* der, så snevres
        skanningen inn igjen, blir denne rød.
        """
        klasser = self._celleklasser()
        for klasse in ('vl-oversikt-tid', 'vl-ledigtall'):
            with self.subTest(klasse=klasse):
                self.assertIn(klasse, klasser)

    def test_ingen_celleklasse_bryter_tabellen(self):
        for klasse, verdi in self._funn(self._css(), self._celleklasser()):
                with self.subTest(klasse=klasse):
                    self.assertIn(
                        verdi, self.LOVLIGE,
                        f'.{klasse} står på en <td> og setter '
                        f'display: {verdi} — cella slutter da å '
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_rolleValg', 'rollerForGruppe')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    #: Gruppe 1 er «Ambulanse», gruppe 2 «Samleplass» i disse testene.
    ROLLER = """
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utskriftsdager', '_utvalgstekst', '_skiftrekkefolge', '_d', '_kl',
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
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
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
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
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('tegnFaner', 'kanPlanlegge', '_fanerad', '_mannskapsfane',
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
            "globalThis.PLANLEGGER = 'planlegger';\n"
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

    def test_planleggerfanen_er_ledernes(self):
        """André, 15. sep. 2026: «Den skal bare admin og leder ha tilgang
        til. For den genererer grunnlaget på alt.»

        Mutasjonsprøvd: porten i `tegnFaner()` lot seg fjerne uten at noe ble
        rødt — ingen test spurte om fanen var *borte* for de andre. En fane
        som fører til 403 er verre enn ingen fane."""
        for nivaa in ('les', 'skriv_handling', 'skriv_full'):
            with self.subTest(nivaa=nivaa):
                ut = self._tegn(nivaa)
                self.assertIn('Ambulanse', ut, 'resten av rekka står')
                self.assertNotIn('Planlegger', ut)
        for navn, kall in (('skriv_leder', lambda: self._tegn('skriv_leder')),
                           ('admin', lambda: self._tegn('', admin=True))):
            with self.subTest(konto=navn):
                self.assertIn('Planlegger', kall())


class FanenErGruppaTests(SimpleTestCase):
    """Fanen er ressursgruppa, ikke den enkelte ressursen.

    Andrés bestilling 30. aug. 2026: «når jeg lager ny ressurs så skal fanen
    være en oversikt — ambulanse er for alle ambulansene som skal være på
    vakt». Én fane per bil ga ti faner på en vakt med ti biler, og ingen
    plass der man kunne se dem i sammenheng — som er det man planlegger etter.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('tegnFaner', 'kanPlanlegge', '_fanerad', '_mannskapsfane', '_mittKorpsId',
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
                        '_dag', '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanSetteOppSkift', 'kanLede',
                        'kanBemanne', 'kanGiNyttNavn', 'gruppaHarPlass', 'kanRoreRad')),
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
            "globalThis.PLANLEGGER = 'planlegger';\n"
            "globalThis.belastning = null;\n"
            "globalThis.register = null;\n")

    #: To ambulanser i samme gruppe, én samleplass i en annen.
    LISTE = """
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utskriftsdager', '_utvalgstekst', '_skiftrekkefolge', '_d', '_kl',
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
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        """Ressursen er fortsatt aksen — men som **rad**, ikke overskrift
        (16. sep. 2026). Oversikten viste navn, korps, rolle og merknad per
        person, altså nøyaktig de kolonnene man alt hadde lest i gruppefanen;
        André: «Må være en faktisk oversikt.»"""
        ut = self._ut()
        for navn in ('Samleplass', 'Ambulanse 1', 'Ambulanse 2'):
            with self.subTest(ressurs=navn):
                self.assertIn(f'<td class="vl-navn">{navn}', ut)

    def test_ressursene_kommer_i_gruppenes_rekkefolge(self):
        """Samme rekkefølge som fanene, nå som radrekkefølge."""
        ut = self._ut()
        self.assertLess(ut.index('>Samleplass'), ut.index('>Ambulanse 1'))
        self.assertLess(ut.index('>Ambulanse 1'), ut.index('>Ambulanse 2'))

    def test_oversikten_teller_plasser_i_stedet_for_aa_liste_personer(self):
        """**Punkt 2 i pulje 3** (André, 16. sep. 2026): «Den viser mye av det
        som allerede er i de respektive ressursfanene. Må være en faktisk
        oversikt» — tid, timer, totalt, plasser, ledig og besatt.

        Korpskolonnen er derfor borte herfra. Den sto der fordi lista var en
        personliste, og korpset er et kjennetegn ved personen; i en tabell
        over *plasser* hører det ikke hjemme. Hvem som står hvor, med korps og
        rolle, leses i gruppefanen — og skrives ut derfra, for utskrifts-CSS-en
        er generisk.
        """
        ut = self._ut()
        for kolonne in ('Ressurs', 'Tid', 'Timer', 'Plasser', 'Besatt',
                        'Ledige', 'Totalt'):
            with self.subTest(kolonne=kolonne):
                self.assertIn(f'<th>{kolonne}</th>', ut)
        self.assertNotIn('<th>Korps</th>', ut)
        self.assertNotIn('<th>Merknad</th>', ut)
        self.assertNotIn('<h3>Haugesund', ut, 'korpset var aldri en overskrift')

    def test_ledige_plasser_telles_i_sin_egen_kolonne(self):
        """Den ledige plassen er nå et **tall**, ikke en rad.

        Reservasjonen — hvilket korps plassen er satt av til — sto her til
        16. sep. 2026, og er flyttet til gruppefanen sammen med resten av
        personopplysningene. Den prøves der av
        `ReservasjonenVisesIGruppefanenTests`; uten den flyttingen hadde
        `_plassKorps()` mistet sin eneste dekning, og en reservasjon ingen ser
        er en reservasjon som ikke virker.
        """
        ut = self._ut()
        self.assertIn('<th>Ledige</th>', ut)
        self.assertIn('vl-har-ledige', ut, 'raden med ledige plasser er merket')
        self.assertNotIn('— ledig —', ut, 'ingen personrader igjen')

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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
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
                        '_nivaa', '_erAdmin', 'kanSkriveAlt', 'kanSetteOppSkift', 'kanLede',
                        'kanBemanne', 'kanGiNyttNavn', 'gruppaHarPlass', 'kanRoreRad')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.DAGER = ['søn','man','tir','ons','tor','fre','lør'];\n"
             "globalThis.MND = ['jan','feb','mar','apr','mai','jun',"
             "'jul','aug','sep','okt','nov','des'];\n")
    LISTE = """
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
               (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')))

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


    def test_gruppa_er_paakrevd(self):
        """«Velg…» står først i nedtrekket (23. sep. 2026). Sendes den, er
        det en feilmelding ved knappen — ikke `gruppe_id: 0` til serveren."""
        self._kjor("""
          felter['ny-ressurs-gruppe'].value = '';
          await opprettRessurs();
          assert(sendtBody === null, 'en ressurs uten gruppe ble sendt til serveren');
          assert(globalThis.feilmelding === 'Velg hvilken gruppe ressursen hører til.',
                 'feil melding: ' + globalThis.feilmelding);
        """)

    def test_velg_staar_foerst_og_malgruppa_er_valgt(self):
        self._kjor(self.NEDTREKK + """
          apneNyRessurs(2);
          const valg = felter['ny-ressurs-gruppe'].innerHTML;
          assert(valg.startsWith('<option value="">Velg…</option>'), '«Velg…» står ikke først: ' + valg);
          assert(felter['ny-ressurs-gruppe'].value === '2', 'fanens gruppe ble ikke valgt');
        """)


class MannskapsfanenTests(SimpleTestCase):
    """Registeret er en fane på planleggingssiden (30. aug. 2026).

    Det lå på /vaktliste/registre/, og et klikk dit kostet deg plassen i
    planleggingen — mens mannskap og ressurser er nettopp de to man veksler
    mellom. Testene her dekker veiene *inn*: fanen, den tomme tilstanden, og
    vinduet som må åpne seg før den første vaktlista finnes.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkMannskap', '_personKolonne', '_passerPersonsok',
                        '_sorterMannskap', 'kanRedigerePerson',
                        'tegnPanel', 'apneVakt', '_apneModal',
                        '_skjulFeil', '_nivaa', 'visFane', '_erAdmin',
                        'faneTrengerBelastning', 'planleggerSikreLinjer',
                        'kanSkriveAlt', 'kanSetteOppSkift', 'kanSkriveNoe', 'kanLede')),
    )
    VINDU = ("globalThis.ressursApen = new Map();\n"
             "globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.MANNSKAP = 'mannskap';\n"
             "globalThis.TILSTEDE = 'tilstede';\n"
             "globalThis.BELASTNING = 'belastning';\n"
             "globalThis.PLANLEGGER = 'planlegger';\n"
            "globalThis.PLANLEGGER = 'planlegger';\n"
             "globalThis.belastning = null;\n"
            "globalThis.BELASTNING = 'belastning';\n"
            "globalThis.PLANLEGGER = 'planlegger';\n"
            "globalThis.belastning = null;\n"
            "globalThis.TILSTEDE = 'tilstede';\n"
            "globalThis.BELASTNING = 'belastning';\n"
            "globalThis.PLANLEGGER = 'planlegger';\n"
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('apneVaktpost', 'ressursErApen', '_settTid', '_iso16', '_d',
                        '_fyll', '_skjulFeil', '_vaktpostModusSkifte',
                        'rollerForGruppe', '_plussTimer')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    OPPSETT = """
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_stempelknapper', '_radklasse', 'kanStemple',
                        'iDrift', 'kanSkriveAlt', 'kanSetteOppSkift', '_nivaa', '_erAdmin',
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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


class PlanleggerfanenTests(SimpleTestCase):
    """Planleggeren: fanen som lager grunnlaget (15. sep. 2026).

    André: «Jeg ba om en planlegger. Den skal bare admin og leder ha tilgang
    til. For den genererer grunnlaget på alt … tre firemanns lag fra kl. 14–22
    og en ambulanse fra 15–03 mens en ambulanse går 8 timer rotasjon.»

    **Klientens tall er et anslag, serverens er fasit.** Regnestykket under
    hver rad tegnes mens man skriver; `apneGenerer()` henter serverens
    forhåndsvisning før bekreftelsen. Testene her måler at anslaget stemmer
    med serveren på Andrés egne eksempler — kommer de i utakt, er det her det
    skal vises.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (PORTAL_UTILS_JS, ('hendelseArgumenter', '_handlerArgument',
                           'klikkSkalKjore')),
        (VAKTLISTE_JS, ('mkPlanlegger', '_planleggerLinje', '_planleggerVindu',
                        '_planleggerHode', '_planleggerStaar',
                        'planleggerLesTilbake', 'planleggerSikreLinjer',
                        '_planleggerVindutall', '_planleggerLinjetall',
                        '_gruppeFor',
                        '_planleggerRegnestykke', 'planleggerTotal',
                        'planleggerSettLinje', 'planleggerSettVindu',
                        'planleggerNyLinje', 'planleggerNyttVindu',
                        'planleggerTegnTall', '_vindutallTekst',
                        'planleggerFjernLinje', 'planleggerFjernVindu',
                        '_planleggerFinnLinje', '_planleggerFinnVindu',
                        '_planleggerStandardvindu', 'visPanelfeil',
                        'mkBudsjett', 'mkDagslinje', '_budsjettpost',
                        '_dagtekst', '_d', '_iso16', '_tall', 'kanSetteTak',
                        'kanPlanlegge', 'kanLede', '_nivaa', '_erAdmin')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    LAG = 1
    AMBULANSE = 2
    SAMLEPLASS = 3

    def _vis(self, linjer, *, leder=True):
        import json
        vindu = ("globalThis.window = { MODUL_TILGANG: "
                 + ("{ vaktliste: 'skriv_leder', admin: false }" if leder
                    else "{ vaktliste: 'skriv_full', admin: false }")
                 + " };\n")
        liste = {
            'vaktliste': {'id': 1, 'startet': '2026-10-02T12:00:00+02:00',
                          'timetak': None},
            'grupper': [{'id': self.LAG, 'navn': 'Lag',
                         'flere_enheter': True},
                        {'id': self.AMBULANSE, 'navn': 'Ambulanse',
                         'flere_enheter': True},
                        {'id': self.SAMLEPLASS, 'navn': 'Samleplass',
                         'flere_enheter': False}],
        }
        return run_node(self.harness, vindu + f"""
            globalThis.aktivListe = {json.dumps(liste)};
            globalThis.belastning = null;
            globalThis.planleggerNesteId = 1;
            globalThis.planleggerlinjer = {json.dumps(linjer)};
            console.log(mkPlanlegger());
        """)

    def _linje(self, gruppe, antall, plasser, *vinduer):
        """Plassene ligger på **vinduet** (15. sep. 2026). Hjelperen tar dem
        som ett argument fordi de fleste oppsett har samme antall hele veien;
        `_ulikt()` er formen når de varierer."""
        return {'id': 900 + gruppe, 'gruppe_id': gruppe, 'antall': antall,
                'vinduer': [{'id': 950 + i, 'fra': f, 'til': t,
                             'plasser': plasser}
                            for i, (f, t) in enumerate(vinduer)]}

    def _ulikt(self, gruppe, *vinduer):
        return {'id': 901, 'gruppe_id': gruppe, 'antall': 1,
                'vinduer': [{'id': 960 + i, 'fra': f, 'til': t, 'plasser': pl}
                            for i, (f, t, pl) in enumerate(vinduer)]}

    # Andrés tre eksempler, som ISO-tider i norsk sommertid.
    FRE14 = '2026-10-02T14:00:00+02:00'
    FRE15 = '2026-10-02T15:00:00+02:00'
    FRE22 = '2026-10-02T22:00:00+02:00'
    LOR03 = '2026-10-03T03:00:00+02:00'
    LOR15 = '2026-10-03T15:00:00+02:00'
    SON03 = '2026-10-04T03:00:00+02:00'
    SON14 = '2026-10-04T14:00:00+02:00'

    # ── Feltene skal faktisk kunne fylles ut (meldt fra staging) ──────────

    def _skriv(self, oppsett):
        """Kjør et helt redigeringsforløp gjennom **delegeringens egen**
        argumentbygger.

        **Dette er testen som manglet.** De andre her kaller `mkPlanlegger()`
        og leser markupen — de så aldri at handlerne hadde feil signatur.
        André fra staging: «jeg får ikke fylt feltene, de gir meg blankt på
        alle». Årsaken var at `portal-utils.js` sender **ett** argument med
        mindre elementet bærer `data-felt`, og handlerne mine tok `(arg,
        verdi)`. `verdi` var alltid `undefined`.

        `oppsett` er JS som gjør redigeringene; testen plukker attributtene
        ut av den ekte markupen og sender dem gjennom `hendelseArgumenter()`,
        så argumentene bygges nøyaktig som i nettleseren.
        """
        import json
        liste = {
            'vaktliste': {'id': 1, 'startet': '2026-10-02T14:00:00+02:00',
                          'timetak': None},
            'grupper': [{'id': self.LAG, 'navn': 'Lag',
                         'flere_enheter': True},
                        {'id': self.AMBULANSE, 'navn': 'Ambulanse',
                         'flere_enheter': True},
                        {'id': self.SAMLEPLASS, 'navn': 'Samleplass',
                         'flere_enheter': False}],
        }
        return run_node(self.harness,
                        "globalThis.window = { MODUL_TILGANG: "
                        "{ vaktliste: 'skriv_leder', admin: false } };\n"
                        + f"""
            globalThis.aktivListe = {json.dumps(liste)};
            globalThis.belastning = null;
            globalThis.planleggerNesteId = 1;
            globalThis.planleggerlinjer = [];
            globalThis.planleggerfasit = null;
            // Telleren gjør regelen målbar: feltendringer skal *ikke*
            // tegne panelet på nytt, fordi `innerHTML` bytter ut feltet man
            // står i og fokus forsvinner med det.
            globalThis.omtegninger = 0;
            globalThis.tegnPanel = () => {{ globalThis.omtegninger += 1; }};
            globalThis.visPanelfeil = (m) => {{ throw new Error(m); }};

            // Plukk ut attributtene et felt faktisk bærer, og kall handleren
            // slik delegeringen ville gjort det.
            function felt(markup, handling, feltnavn) {{
                const m = markup.match(new RegExp(
                    '<(input|select)[^>]*data-action="' + handling +
                    '"[^>]*data-felt="' + feltnavn + '"[^>]*data-id="([0-9]+)"'));
                if (!m) throw new Error('fant ikke ' + handling + '/' + feltnavn);
                return {{ dataset: {{ action: handling, felt: feltnavn, id: m[2] }} }};
            }}
            // Oppslaget er en lokal tabell og ikke `globalThis`: i harnessen
            // er funksjonene modul-scopede, mens de i nettleseren er globale.
            // Det testen måler er **argumentene**, som bygges av delegeringens
            // egen `hendelseArgumenter()` — ikke hvordan navnet slås opp.
            const HANDLERE = {{ planleggerSettLinje, planleggerSettVindu }};
            function skriv(handling, feltnavn, verdi) {{
                const el = felt(mkPlanlegger(), handling, feltnavn);
                el.value = verdi;
                HANDLERE[handling](...hendelseArgumenter(el));
            }}
            {oppsett}
        """)

    def test_tidsfelt_tegner_ikke_panelet_paa_nytt(self):
        """André, 15. sep. 2026: «frustrerende vanskelig å redigere med
        tastatur på tidsrom, jeg kan bare ta inn ett tall om gangen».

        Hver `change` kalte `tegnPanel()`, som bygger panelet på nytt med
        `innerHTML` — da erstattes feltet man står i, og fokus og markør
        forsvinner. `datetime-local` melder `change` per segment, så feltet
        forsvant etter hvert tall."""
        self._skriv("""
            planleggerNyLinje();
            const foer = omtegninger;
            skriv('planleggerSettVindu', 'fra', '2026-10-03T15:00');
            skriv('planleggerSettVindu', 'til', '2026-10-04T03:00');
            skriv('planleggerSettVindu', 'plasser', '6');
            skriv('planleggerSettLinje', 'antall', '3');
            assert(omtegninger === foer,
                   'panelet ble tegnet ' + (omtegninger - foer) + ' gang(er)');
        """)

    def test_gruppevalget_tegner_panelet_paa_nytt(self):
        """Motprøven. Gruppa er en **strukturendring** — «Antall» finnes ikke
        for grupper i ett eksemplar, så raden skifter form. Et nedtrekk er man
        dessuten ferdig med når man har valgt, så omtegningen koster ingen
        markør."""
        self._skriv(f"""
            planleggerNyLinje();
            const foer = omtegninger;
            skriv('planleggerSettLinje', 'gruppe_id', '{self.SAMLEPLASS}');
            assert(omtegninger === foer + 1,
                   'gruppevalget skal tegne panelet, ble ' + (omtegninger - foer));
        """)

    def test_tallene_oppdateres_paa_plass(self):
        """Uten omtegning må tallene oppdateres av `planleggerTegnTall()`,
        ellers står de på det de var mens man skriver.

        **Alle tre nivåene måles**: tallet under vinduet, regnestykket under
        raden, og totalen nederst. Mutasjonsprøvd — en test som bare sjekket
        totalen lot vindutallet fryse uten at noe ble rødt."""
        self._skriv("""
            const noder = {};
            globalThis.document = { querySelector: (sel) => {
                if (!noder[sel]) noder[sel] = {
                    textContent: 'urørt', classList: { toggle: () => {} } };
                return noder[sel];
            } };
            planleggerNyLinje();
            const vid = planleggerlinjer[0].vinduer[0].id;
            const lid = planleggerlinjer[0].id;
            skriv('planleggerSettVindu', 'plasser', '6');

            const vindu = noder['[data-vindutall="' + vid + '"]'];
            assert(vindu && /48 t i alt/.test(vindu.textContent),
                   'vindutallet ble «' + (vindu && vindu.textContent) + '»');

            const rad = noder['[data-linjetall="' + lid + '"]'];
            assert(rad && /6 plasser/.test(rad.textContent),
                   'regnestykket ble «' + (rad && rad.textContent) + '»');

            const sum = noder['[data-plantall="plasser"]'];
            assert(sum && sum.textContent === '6',
                   'summen ble «' + (sum && sum.textContent) + '»');
        """)

    def test_ugyldig_tidsrom_merkes_uten_omtegning(self):
        """Advarselsklassen settes av `classList.toggle`, ikke av ny markup —
        ellers ville et bakvendt vindu krevd en omtegning for å vises."""
        self._skriv("""
            const vekslet = [];
            globalThis.document = { querySelector: () => ({
                textContent: '',
                classList: { toggle: (k, paa) => vekslet.push([k, paa]) },
            }) };
            planleggerNyLinje();
            skriv('planleggerSettVindu', 'til', '2020-01-01T00:00');
            const siste = vekslet[vekslet.length - 1];
            assert(siste && siste[0] === 'vl-advarsel' && siste[1] === true,
                   'ventet vl-advarsel=true, fikk ' + JSON.stringify(siste));
        """)

    def test_feltene_lar_seg_fylle_ut(self):
        """Regresjonen, målt gjennom delegeringens egen argumentbygger."""
        ut = self._skriv("""
            planleggerNyLinje();
            skriv('planleggerSettLinje', 'antall', '3');
            skriv('planleggerSettVindu', 'plasser', '4');
            const l = planleggerlinjer[0];
            assert(String(l.antall) === '3', 'antall ble ' + l.antall);
            assert(String(l.vinduer[0].plasser) === '4',
                   'plasser ble ' + l.vinduer[0].plasser);
            console.log(mkPlanlegger());
        """)
        self.assertIn('value="3"', ut)
        self.assertIn('value="4"', ut)

    def test_tidsfeltene_beholder_verdien_de_far(self):
        ut = self._skriv("""
            planleggerNyLinje();
            skriv('planleggerSettVindu', 'fra', '2026-10-03T15:00');
            skriv('planleggerSettVindu', 'til', '2026-10-04T03:00');
            skriv('planleggerSettVindu', 'plasser', '6');
            const v = planleggerlinjer[0].vinduer[0];
            assert(v.fra !== null, 'fra ble null');
            assert(v.til !== null, 'til ble null');
            assert(v.plasser === '6', 'plasser ble ' + v.plasser);
            console.log(mkPlanlegger());
        """)
        self.assertIn('value="2026-10-03T15:00"', ut)
        self.assertIn('value="2026-10-04T03:00"', ut)
        # 15:00–03:00 er tolv timer; seks plasser gir 72 t.
        self.assertIn('72 t', ut)

    def test_gruppevalget_lagres_som_tall(self):
        """FK-en må være et tall — serveren slår opp gruppa på den."""
        self._skriv(f"""
            planleggerNyLinje();
            skriv('planleggerSettLinje', 'gruppe_id', '{self.AMBULANSE}');
            assert(planleggerlinjer[0].gruppe_id === {self.AMBULANSE},
                   'gruppe_id ble ' + typeof planleggerlinjer[0].gruppe_id);
        """)

    def test_feltene_baerer_data_felt_saa_delegeringen_sender_verdien(self):
        """**Regelen, ikke bare virkningen.** `hendelseArgumenter()` sender
        `(id, felt, verdi)` kun når elementet har `data-felt`; ellers ett
        argument. Et felt som mister attributtet blir stille blankt igjen."""
        ut = self._skriv("planleggerNyLinje(); console.log(mkPlanlegger());")
        import re
        felter = re.findall(r'data-action="(planleggerSett\w+)"[^>]*', ut)
        self.assertTrue(felter, 'fant ingen redigeringsfelter')
        for treff in re.finditer(
                r'<(?:input|select)[^>]*data-action="planleggerSett\w+"[^>]*>', ut):
            with self.subTest(felt=treff.group(0)[:80]):
                self.assertIn('data-felt=', treff.group(0))
                self.assertIn('data-id=', treff.group(0))

    def test_aa_fjerne_en_rad_flytter_ikke_adressen_til_de_andre(self):
        """**ID-er, ikke indekser.** Med indekser pekte radene under den man
        fjernet plutselig på naboen, og neste tastetrykk skrev i feil rad."""
        self._skriv("""
            planleggerNyLinje();
            planleggerNyLinje();
            planleggerNyLinje();
            const foer = planleggerlinjer.map((l) => l.id);
            planleggerFjernLinje(foer[0]);
            const etter = planleggerlinjer.map((l) => l.id);
            // **Hele lista, ikke bare lengden og den siste.** Første utgave
            // av denne testen gikk grønn mot `const i = id`, fordi ID-ene
            // (1, 3, 5) og indeksene falt slik at «den siste» ble den samme
            // uansett hvilken rad som forsvant. Mutasjonsprøvd.
            assert(etter.join(',') === foer.slice(1).join(','),
                   'sto igjen ' + etter.join(',') + ', ventet ' + foer.slice(1).join(','));
        """)

    def test_uten_starttid_paa_vakta_sier_panelet_fra(self):
        """Standardvinduene faller tilbake til nå, og «dagens dato» ser ut
        som et valg noen har tatt framfor et fravær."""
        import json
        liste = {'vaktliste': {'id': 1, 'startet': None, 'timetak': None},
                 'grupper': [{'id': self.LAG, 'navn': 'Lag',
                              'flere_enheter': True}]}
        ut = run_node(self.harness,
                      "globalThis.window = { MODUL_TILGANG: "
                      "{ vaktliste: 'skriv_leder', admin: false } };\n"
                      + f"""
            globalThis.aktivListe = {json.dumps(liste)};
            globalThis.belastning = null;
            globalThis.planleggerNesteId = 1;
            globalThis.planleggerlinjer = [];
            console.log(mkPlanlegger());
        """)
        self.assertIn('ingen', ut)
        self.assertIn('starttid', ut)

    def test_med_starttid_staar_beskjeden_ikke(self):
        self.assertNotIn('starttid', self._vis([]))

    def test_standardvinduet_begynner_paa_vaktas_start(self):
        """Bug 1 fra staging: «når jeg har satt dato for vakten … begynner de
        på dagens dato». Standardvinduet var riktig; feltet ble tømt av
        bug 2, og en tom `datetime-local` åpner på dagens dato. Testen låser
        likevel regelen, siden den er lett å miste."""
        ut = self._skriv("""
            planleggerNyLinje();
            console.log(mkPlanlegger());
        """)
        self.assertIn('value="2026-10-02T14:00"', ut)

    def test_nytt_vindu_arver_forrige_vindus_antall_plasser(self):
        """Det vanlige er at vinduene har samme antall; det uvanlige er ett
        tastetrykk unna. Arvet ikke det nye vinduet, måtte man skrevet tallet
        på nytt for hvert skift i en rotasjon."""
        self._skriv("""
            planleggerNyLinje();
            skriv('planleggerSettVindu', 'plasser', '6');
            planleggerNyttVindu(planleggerlinjer[0].id);
            const v = planleggerlinjer[0].vinduer;
            assert(String(v[1].plasser) === '6',
                   'nytt vindu fikk ' + v[1].plasser + ', ventet 6');
        """)

    def test_nytt_vindu_begynner_der_det_forrige_sluttet(self):
        """Sola 56 har to vakter på ulike dager; «rett etter forrige» er det
        man som regel mener."""
        ut = self._skriv("""
            planleggerNyLinje();
            planleggerNyttVindu(planleggerlinjer[0].id);
            console.log(mkPlanlegger());
        """)
        self.assertIn('value="2026-10-02T22:00"', ut)

    def test_bare_leder_og_admin_ser_fanen(self):
        """`skriv_full` bemanner; planleggeren lager grunnlaget for hele
        lista, og det er lederens bord."""
        ut = self._vis([], leder=False)
        self.assertIn('for vaktledere og administratorer', ut)
        self.assertNotIn('Legg til ressurs', ut)

    def test_tom_planlegger_sier_hvordan_man_begynner(self):
        """En tom flate med bare en knapp forteller ikke hva knappen lager."""
        ut = self._vis([])
        self.assertIn('Legg til ressurs', ut)
        self.assertIn('to vinduer', ut)

    def test_tre_firemannslag_gir_tolv_plasser(self):
        ut = self._vis([self._linje(self.LAG, 3, 4,
                                    (self.FRE14, self.FRE22))])
        self.assertIn('12 plasser', ut)
        self.assertIn('96 t', ut)

    def test_rotasjonen_settes_opp_som_de_skiftene_den_er(self):
        """Haugesund 56, fre. 14 → søn. 14 i åttetimersskift: seks vinduer.

        `skiftlengde` er borte (André, 15. sep. 2026: «har vi noe behov for
        skiftlengde?» → nei). Den var en skjult multiplikator der alle de
        genererte skiftene fikk samme antall plasser — nettopp det som ikke
        lot seg uttrykke da plassene ble flyttet til vinduet."""
        vinduer = [(f'2026-10-{2 + (14 + 8 * i) // 24:02d}'
                    f'T{(14 + 8 * i) % 24:02d}:00:00+02:00',
                    f'2026-10-{2 + (14 + 8 * (i + 1)) // 24:02d}'
                    f'T{(14 + 8 * (i + 1)) % 24:02d}:00:00+02:00')
                   for i in range(6)]
        ut = self._vis([self._linje(self.AMBULANSE, 1, 2, *vinduer)])
        self.assertIn('6 skift', ut)
        self.assertIn('12 plasser', ut)
        self.assertIn('96 t', ut)

    def test_ulikt_antall_plasser_paa_ulike_vinduer(self):
        """André: «noen ganger ønsker man å ha mindre og mer plasser på
        enkelte skift visse deler av døgnet.» Seks 14–22 og to 22–06 er
        **én** samleplass."""
        ut = self._vis([self._ulikt(
            self.SAMLEPLASS,
            (self.FRE14, self.FRE22, 6),
            (self.FRE22, '2026-10-03T06:00:00+02:00', 2))])
        self.assertIn('8 plasser', ut)
        self.assertIn('64 t', ut, '6 × 8 t + 2 × 8 t')

    def test_antall_skjules_for_grupper_i_ett_eksemplar(self):
        """André: «for samleplass og KO ble antall forvirrende». Det kan bare
        være én, serveren avviser alt annet, og en kontroll som ikke gjør noe
        er en kontroll man lurer på."""
        ut = self._vis([self._linje(self.SAMLEPLASS, 1, 4,
                                    (self.FRE14, self.FRE22))])
        self.assertIn('ett eksemplar', ut)
        self.assertNotIn('data-felt="antall"', ut)

    def test_antall_staar_for_grupper_det_kan_vaere_flere_av(self):
        ut = self._vis([self._linje(self.LAG, 3, 4, (self.FRE14, self.FRE22))])
        self.assertIn('data-felt="antall"', ut)
        self.assertNotIn('ett eksemplar', ut)

    def test_skiftlengde_finnes_ikke_lenger(self):
        """Motprøven: feltet skal være borte, ikke bare omdøpt."""
        ut = self._vis([self._linje(self.LAG, 1, 4,
                                    (self.FRE14, self.FRE22))])
        self.assertNotIn('skiftlengde', ut)
        self.assertNotIn('Skiftlengde', ut)

    def test_to_adskilte_vinduer_er_en_ressurs(self):
        """Sola 56. Hadde raden vært vinduet, ville hun blitt to biler —
        og da hadde tallet sagt to ressurser."""
        ut = self._vis([self._linje(self.AMBULANSE, 1, 2,
                                    (self.FRE15, self.LOR03),
                                    (self.LOR15, self.SON03))])
        self.assertIn('4 plasser', ut)
        self.assertIn('48 t', ut)
        self.assertIn('>1<', ut, 'én ressurs')

    def test_hele_oppsettet_summeres(self):
        """Alle tre linjene sammen: 5 ressurser, 28 plasser, 240 t — samme
        tall som `GrunnlagTests.test_hele_oppsettet_i_en_omgang` måler på
        serversiden. Kommer de to i utakt, er det her det vises."""
        ut = self._vis([
            self._linje(self.LAG, 3, 4, (self.FRE14, self.FRE22)),
            self._linje(self.AMBULANSE, 1, 2,
                        *[(f'2026-10-{2 + (14 + 8 * i) // 24:02d}'
                           f'T{(14 + 8 * i) % 24:02d}:00:00+02:00',
                           f'2026-10-{2 + (14 + 8 * (i + 1)) // 24:02d}'
                           f'T{(14 + 8 * (i + 1)) % 24:02d}:00:00+02:00')
                          for i in range(6)]),
            self._linje(self.AMBULANSE, 1, 2,
                        (self.FRE15, self.LOR03),
                        (self.LOR15, self.SON03)),
        ])
        # Summen står **nederst**, i kortet med generer-knappen: man leser
        # radene, og så står totalen der man avslutter. Testen leser derfor
        # det kortet og ikke hele svaret — «5» og «28» finnes også i
        # regnestykkene over.
        sum_kort = ut[ut.rindex('vl-belastningshode'):]
        self.assertIn('>5<', sum_kort)
        self.assertIn('>28<', sum_kort)
        self.assertIn('240 t', sum_kort)

    def test_ett_vindu_er_ett_skift(self):
        ut = self._vis([self._linje(self.AMBULANSE, 1, 2,
                                    (self.FRE15, self.LOR03))])
        self.assertIn('1 skift', ut)

    def test_ugyldig_tidsrom_sier_fra_framfor_aa_vise_null(self):
        """Et bakvendt vindu skal si hva som er galt, ikke stå med «0
        plasser» som om det var et svar."""
        ut = self._vis([self._linje(self.LAG, 1, 4,
                                    (self.FRE22, self.FRE14))])
        self.assertIn('ugyldig tidsrom', ut)
        self.assertNotIn('Lag grunnlaget', ut.split('ugyldig tidsrom')[0])

    def test_regnestykket_viser_leddene_ikke_bare_summen(self):
        """Den som leser skal kunne se hvilket ledd som er feil når tallet
        ikke stemmer med det hun tenkte.

        **Plassene er ikke et ledd lenger**, fordi de kan være ulike fra
        vindu til vindu — hvert vindu viser sitt eget tall, raden summen."""
        ut = self._vis([self._linje(self.LAG, 3, 4,
                                    (self.FRE14, self.FRE22))])
        self.assertIn('1 skift × 3 ressurser = 12 plasser, 96 t', ut)

    def test_antall_paa_en_utelates_fra_regnestykket(self):
        """«× 1 ressurser» er et ledd som ikke gjør noe, og det er nettopp
        de leddene som gjør et regnestykke vanskelig å lese."""
        ut = self._vis([self._linje(self.AMBULANSE, 1, 2,
                                    (self.FRE15, self.LOR03))])
        self.assertIn('1 skift = 2 plasser, 24 t', ut)

    def test_legg_til_staar_mellom_siste_ressurs_og_generer(self):
        """André, 15. sep. 2026: «for nå er det lett å tro at man bare lager
        en ressurs og så er man ferdig».

        Knappen sto i hodet, over radene, og leste som «start her». Mellom
        radene og «Lag grunnlaget» leser den som «legg til én til», og
        rekkefølgen i panelet blir den man arbeider i."""
        ut = self._vis([self._linje(self.LAG, 1, 4,
                                    (self.FRE14, self.FRE22))])
        self.assertLess(ut.index('vl-pl-linje'), ut.index('planleggerNyLinje'),
                        'knappen skal stå etter ressursradene')
        self.assertLess(ut.index('planleggerNyLinje'), ut.index('apneGenerer'),
                        'og før «Lag grunnlaget»')

    def test_legg_til_staar_ogsaa_naar_oppsettet_er_tomt(self):
        """Uten den kommer man aldri i gang."""
        self.assertIn('planleggerNyLinje', self._vis([]))

    def test_genererknappen_staar_bare_naar_det_finnes_et_oppsett(self):
        self.assertNotIn('apneGenerer', self._vis([]))
        self.assertIn('apneGenerer', self._vis(
            [self._linje(self.LAG, 1, 4, (self.FRE14, self.FRE22))]))

    def test_forste_vindu_kan_ikke_fjernes(self):
        """En ressurs uten skiftvindu er ingenting. Serveren avviser det
        også, men en knapp som fører til en vegg er verre enn ingen knapp."""
        ut = self._vis([self._linje(self.LAG, 1, 4,
                                    (self.FRE14, self.FRE22))])
        self.assertNotIn('planleggerFjernVindu', ut)

    def test_andre_vindu_kan_fjernes(self):
        ut = self._vis([self._linje(self.AMBULANSE, 1, 2,
                                    (self.FRE15, self.LOR03),
                                    (self.LOR15, self.SON03))])
        self.assertIn('planleggerFjernVindu', ut)

    def test_budsjettlinja_staar_i_denne_fanen(self):
        """Flyttet hit fra «Planlegging» 15. sep. 2026: «sette inn total
        timer og jobbe overordnet» er planleggerens verktøy."""
        import json
        liste = {
            'vaktliste': {'id': 1, 'startet': '2026-10-02T12:00:00+02:00',
                          'timetak': 400},
            'grupper': [{'id': self.LAG, 'navn': 'Lag',
                         'flere_enheter': True}],
        }
        plan = {'timetak': 400, 'satt_opp': 312.0, 'bemannet': 244.0,
                'probono': 0.0, 'igjen': 88.0, 'over_taket': False,
                'dager': []}
        ut = run_node(self.harness,
                      "globalThis.window = { MODUL_TILGANG: "
                      "{ vaktliste: 'skriv_leder', admin: false } };\n"
                      + f"""
            globalThis.aktivListe = {json.dumps(liste)};
            globalThis.belastning = {json.dumps({'planlegging': plan, 'kan_sette_tak': True})};
            globalThis.planleggerNesteId = 1;
            globalThis.planleggerlinjer = [];
            console.log(mkPlanlegger());
        """)
        self.assertIn('satt opp', ut)
        self.assertLess(ut.index('satt opp'), ut.index('Oppsett'),
                        'budsjettet står over oppsettet')

    # ── Oppsettet leses tilbake fra lista ────────────────────────────────
    #
    # André, 15. sep. 2026: «når en har lagt grunnlag og vil redigere så er
    # det ikke lenger i planlegger — det må vel gå ann å huske dem og la en
    # redigere der?»
    #
    # **Planleggeren husker ikke det du skrev; den leser hva som står.** En
    # husket kladd og virkeligheten glir fra hverandre i det øyeblikket noen
    # retter et skift i regnearket, og da ville et trykk på «Lag grunnlaget»
    # rullet den rettelsen tilbake.

    def _tilbake(self, ressurser, vaktposter, *, linjer=None, marker=False):
        import json
        liste = {
            'vaktliste': {'id': 1, 'startet': '2026-10-02T12:00:00+02:00',
                          'timetak': None},
            'grupper': [{'id': self.LAG, 'navn': 'Lag', 'flere_enheter': True},
                        {'id': self.SAMLEPLASS, 'navn': 'Samleplass',
                         'flere_enheter': False}],
            'ressurser': ressurser,
            'vaktposter': vaktposter,
        }
        hale = ('console.log(mkPlanlegger());' if marker
                else 'console.log(JSON.stringify(planleggerlinjer));')
        return run_node(self.harness,
                        "globalThis.window = { MODUL_TILGANG: "
                        "{ vaktliste: 'skriv_leder', admin: false } };\n"
                        + f"""
            globalThis.aktivListe = {json.dumps(liste)};
            globalThis.belastning = null;
            globalThis.planleggerNesteId = 1;
            globalThis.planleggerlinjer = {json.dumps(linjer or [])};
            planleggerSikreLinjer();
            {hale}
        """)

    def _plass(self, ressurs_id, fra, til):
        return {'ressurs_id': ressurs_id, 'fra_tid': fra, 'til_tid': til}

    RES1 = {'id': 11, 'navn': 'Lag 1', 'gruppe_id': 1}

    def test_ressursen_blir_en_rad_som_peker_paa_den(self):
        """`ressurs_id` er hele forskjellen: uten den lager et andre trykk
        «Lag 2» ved siden av «Lag 1»."""
        import json
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE14, self.FRE22)])
        linjer = json.loads(ut.replace('OK', '').strip().splitlines()[0])
        self.assertEqual(1, len(linjer))
        self.assertEqual(11, linjer[0]['ressurs_id'])
        self.assertEqual('Lag 1', linjer[0]['navn'])
        self.assertEqual(self.LAG, linjer[0]['gruppe_id'])

    def test_like_plasser_samles_til_ett_vindu_med_antall(self):
        """Seks plasser 14–22 ble skrevet som ett vindu med seks, og leses
        tilbake som det. Var de seks vinduer, ville raden vært uleselig."""
        import json
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE14, self.FRE22) for _ in range(6)])
        vinduer = json.loads(ut.replace('OK', '').strip().splitlines()[0])[0]['vinduer']
        self.assertEqual(1, len(vinduer))
        self.assertEqual(6, vinduer[0]['plasser'])

    def test_ulike_tider_blir_ulike_vinduer_i_kronologisk_rekkefolge(self):
        """**Rekkefølgen er starttidas, ikke sluttidas.** Vinduene leses som en
        vakt man går gjennom ovenfra og ned, og «Nytt skiftvindu» begynner der
        det forrige sluttet — da må det forrige være det som begynte først.

        Mutasjonsprøvd 15. sep. 2026: dataene sorterte likt på begge felter, og
        en sortering på `til` gikk grønn. Det lange vinduet her begynner
        *først* og slutter *sist*, så de to reglene gir hver sin rekkefølge."""
        import json
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE15, self.LOR03),
            self._plass(11, self.FRE14, self.SON14),
            self._plass(11, self.FRE15, self.LOR03),
        ])
        vinduer = json.loads(ut.replace('OK', '').strip().splitlines()[0])[0]['vinduer']
        self.assertEqual([self.FRE14, self.FRE15],
                         [v['fra'] for v in vinduer],
                         'sortert på starttid, ikke sluttid')
        self.assertEqual([1, 2], [v['plasser'] for v in vinduer])

    def test_ressurs_uten_skift_far_et_standardvindu(self):
        """Ellers ville raden vært ugyldig for serveren i det øyeblikket den
        ble tegnet — og en bil man nettopp opprettet i ressursfanen kunne
        aldri fått skiftene sine herfra."""
        import json
        ut = self._tilbake([self.RES1], [])
        linjer = json.loads(ut.replace('OK', '').strip().splitlines()[0])
        self.assertEqual(1, len(linjer[0]['vinduer']))

    def test_et_paabegynt_oppsett_overskrives_ikke(self):
        """Har du skrevet noe, er det ditt til du trykker."""
        import json
        egen = [self._linje(self.LAG, 1, 4, (self.FRE14, self.FRE22))]
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE14, self.FRE22)], linjer=egen)
        linjer = json.loads(ut.replace('OK', '').strip().splitlines()[0])
        self.assertEqual(1, len(linjer))
        self.assertIsNone(linjer[0].get('ressurs_id'))

    def test_id_ene_er_unike_paa_tvers_av_rader_og_vinduer(self):
        """`data-id` er adressen delegeringen skriver til. Kolliderer to,
        skriver et tastetrykk i feil rad."""
        import json
        ut = self._tilbake(
            [self.RES1, {'id': 12, 'navn': 'Lag 2', 'gruppe_id': 1}],
            [self._plass(11, self.FRE14, self.FRE22),
             self._plass(12, self.FRE14, self.FRE22),
             self._plass(12, self.LOR15, self.SON03)])
        linjer = json.loads(ut.replace('OK', '').strip().splitlines()[0])
        ider = [l['id'] for l in linjer] + [v['id'] for l in linjer
                                            for v in l['vinduer']]
        self.assertEqual(len(ider), len(set(ider)), ider)

    # ── Raden som står ser annerledes ut enn raden som lages ─────────────

    def test_raden_som_staar_viser_navnet_og_ikke_gruppenedtrekket(self):
        """Formen er hele forklaringen på hva raden gjør. Med et gruppevalg
        ville man trodd man kunne flytte bilen herfra — og serveren leser
        gruppa fra ressursen, så valget hadde ikke gjort noe."""
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE14, self.FRE22)], marker=True)
        self.assertIn('Lag 1', ut)
        self.assertIn('står på lista', ut)
        self.assertNotIn('data-felt="gruppe_id"', ut)
        self.assertNotIn('data-felt="antall"', ut)

    def test_raden_som_staar_tas_ut_av_oppsettet_ikke_slettes(self):
        """Å fjerne en ressurs er en sletting, og den ligger bak de to
        bekreftelsene i «Rediger ressurs». Knappen her tar raden ut."""
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE14, self.FRE22)], marker=True)
        self.assertIn('Ta ut', ut)
        self.assertIn('blir stående', ut)

    def test_en_ny_rad_har_fortsatt_gruppe_og_antall(self):
        ut = self._vis([self._linje(self.LAG, 3, 4, (self.FRE14, self.FRE22))])
        self.assertIn('data-felt="gruppe_id"', ut)
        self.assertIn('data-felt="antall"', ut)
        self.assertNotIn('står på lista', ut)

    def test_panelet_sier_hvor_mange_rader_som_rettes(self):
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE14, self.FRE22)], marker=True)
        self.assertIn('blir <strong>rettet</strong>', ut)

    def test_uten_staaende_rader_staar_setningen_ikke(self):
        ut = self._vis([self._linje(self.LAG, 1, 4, (self.FRE14, self.FRE22))])
        self.assertNotIn('blir <strong>rettet</strong>', ut)

    def test_tidsfeltene_i_en_staaende_rad_kan_redigeres(self):
        """Raden skal være redigerbar, ikke bare synlig — det var hele
        bestillingen."""
        ut = self._tilbake([self.RES1], [
            self._plass(11, self.FRE14, self.FRE22)], marker=True)
        self.assertIn('data-felt="fra"', ut)
        self.assertIn('data-felt="til"', ut)
        self.assertIn('data-felt="plasser"', ut)



class GenererbekreftelsenTests(SimpleTestCase):
    """Dialogen viser **endringen**, panelet viser oppsettet.

    To ulike spørsmål: panelet sier hva lista skal *være*, dialogen hva som
    *skjer*. En generering over et oppsett som alt er laget rører de fleste
    radene lite eller ingenting, og en tabell der alle radene ser like ut ville
    skjult nettopp den ene som endrer seg.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('_genererFasit', '_genererRadmerke', '_tall')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _vis(self, fasit):
        import json
        return run_node(self.harness, f"""
            console.log(_genererFasit({json.dumps(fasit)}));
        """)

    def _rad(self, **felt):
        rad = {'navn': 'Lag 1', 'gruppe': 'Lag', 'finnes': False, 'skift': 1,
               'plasser': 4, 'fjernes': 0, 'timer': 32.0}
        rad.update(felt)
        return rad

    def _fasit(self, rader, **felt):
        fasit = {'ressurser': sum(1 for r in rader if not r['finnes']),
                 'plasser': sum(r['plasser'] for r in rader),
                 'fjernes': sum(r['fjernes'] for r in rader),
                 'timer': sum(r['timer'] for r in rader), 'linjer': rader}
        fasit.update(felt)
        return fasit

    def test_ny_ressurs_merkes_som_ny(self):
        ut = self._vis(self._fasit([self._rad()]))
        self.assertIn('ny ressurs', ut)

    def test_ressurs_som_rettes_merkes_som_det(self):
        ut = self._vis(self._fasit([self._rad(finnes=True, plasser=2)]))
        self.assertIn('rettes', ut)
        self.assertNotIn('ny ressurs', ut)

    def test_ressurs_uten_endring_merkes_uendret(self):
        """Den raden er det viktigste av de tre merkene: uten den ser en
        generering som ikke gjør noe ut som en generering som gjør alt."""
        ut = self._vis(self._fasit(
            [self._rad(finnes=True, plasser=0, fjernes=0, timer=0)]))
        self.assertIn('uendret', ut)
        self.assertNotIn('rettes', ut)

    def test_fjerningen_staar_i_setningen_man_leser(self):
        """Å redigere et vindu fra seks plasser til fire sletter to. Det er det
        eneste i hele planleggeren som fjerner noe, så det skal stå der man
        leser før man trykker — ikke i en fotnote."""
        ut = self._vis(self._fasit([self._rad(finnes=True, fjernes=6)]))
        self.assertIn('Ryddes bort', ut)
        self.assertIn('<strong>6</strong>', ut)

    def test_ingenting_fjernes_gir_ingen_setning_om_fjerning(self):
        ut = self._vis(self._fasit([self._rad()]))
        self.assertNotIn('Ryddes bort', ut)

    def test_navn_escapes(self):
        ut = self._vis(self._fasit(
            [self._rad(navn='<img src=x onerror=alert(1)>')]))
        self.assertNotIn('<img src=x', ut)
        self.assertIn('&lt;img', ut)


class PlanleggerenTegnesMedOppsettetTests(SimpleTestCase):
    """**Tilstanden settes på vei inn i panelet, ikke i byggeren.**

    `tegnPanel()` kaller `planleggerSikreLinjer()` før `mkPlanlegger()`, så
    oppsettet leses tilbake uansett hvilken vei man kom — fanevalg, listebytte
    eller omtegningen etter en generering.

    Mutasjonsprøvd 15. sep. 2026: de andre testene kaller
    `planleggerSikreLinjer()` selv, så `tegnPanel()` kunne slutte å kalle den
    uten at noe ble rødt — og da var planleggeren tom igjen etter en
    generering, som er nøyaktig det André meldte fra staging.

    Egen klasse fordi harnesset må ha den **ekte** `tegnPanel()`. De andre
    planleggertestene stubber den for å telle omtegninger, og en uttrukket
    funksjon skygger for `globalThis`.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('tegnPanel', 'mkPlanlegger', '_planleggerLinje',
                        '_planleggerVindu', '_planleggerHode',
                        '_planleggerStaar', 'planleggerLesTilbake',
                        'planleggerSikreLinjer', '_planleggerStandardvindu',
                        '_planleggerVindutall', '_planleggerLinjetall',
                        '_planleggerRegnestykke', 'planleggerTotal',
                        '_vindutallTekst', '_gruppeFor',
                        'mkBudsjett', 'mkDagslinje', '_budsjettpost',
                        '_dagtekst', '_d', '_iso16', '_tall', 'kanSetteTak',
                        'kanPlanlegge', 'kanLede', '_nivaa', '_erAdmin')),
    )

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def test_panelet_leser_tilbake_naar_det_tegnes(self):
        import json
        liste = {
            'vaktliste': {'id': 1, 'startet': '2026-10-02T12:00:00+02:00',
                          'timetak': None},
            'grupper': [{'id': 1, 'navn': 'Lag', 'flere_enheter': True}],
            'ressurser': [{'id': 11, 'navn': 'Lag 1', 'gruppe_id': 1}],
            'vaktposter': [{'ressurs_id': 11,
                            'fra_tid': '2026-10-02T14:00:00+02:00',
                            'til_tid': '2026-10-02T22:00:00+02:00'}],
        }
        ut = run_node(self.harness,
                      "globalThis.window = { MODUL_TILGANG: "
                      "{ vaktliste: 'skriv_leder', admin: false } };\n"
                      + f"""
            globalThis.aktivListe = {json.dumps(liste)};
            globalThis.belastning = null;
            globalThis.planleggerNesteId = 1;
            globalThis.planleggerlinjer = [];
            globalThis.aktivFane = 'planlegger';
            globalThis.MANNSKAP = 'mannskap';
            globalThis.OVERSIKT = 'oversikt';
            globalThis.BELASTNING = 'belastning';
            globalThis.PLANLEGGER = 'planlegger';
            globalThis.TILSTEDE = 'tilstede';
            globalThis.IKKE_PLASSERT = 'ikke-plassert';
            globalThis.MITT_KORPS = 'mitt-korps';
            const panel = {{ innerHTML: '' }};
            globalThis.document = {{ getElementById: (id) =>
                (id === 'vl-panel' ? panel : null) }};
            tegnPanel();
            assert(/Lag 1/.test(panel.innerHTML), 'ressursen sto ikke i panelet');
            assert(planleggerlinjer.length === 1, 'oppsettet ble ikke lest tilbake');
            assert(planleggerlinjer[0].ressurs_id === 11,
                   'raden peker ikke paa ressursen');
        """)
        self.assertIn('OK', ut)


class PlanleggingsfanenTests(SimpleTestCase):
    """Belastningstabellen (§8b).

    **Varsler, ikke sperrer** — og det skal *synes* at det er et varsel og
    ikke en feil. Fargen er gul, ikke rød: et langt skift er ikke galt, det
    er noe planleggeren skal se og ta stilling til.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkBelastning', 'mkBudsjett', 'mkDagslinje',
                        '_budsjettpost', '_dagtekst', '_d', 'kanSetteTak',
                        '_tall', '_kolonneandeler', 'kanLede',
                        '_nivaa', '_erAdmin', 'visFane', 'lastListe',
                        'faneTrengerBelastning', 'planleggerSikreLinjer',
                        'huskListe')),
    )
    # `huskListe` kalles av `lastListe` og trenger en butikk å skrive til.
    # Node har ingen `localStorage`; uten stubben kaster den, og funksjonen
    # svelger det — men da ville testene her målt en kodesti som feiler
    # stille, og det er ikke den de er til for.
    VINDU = ("globalThis.window = { MODUL_TILGANG: { admin: true } };\n"
             "globalThis.localStorage = { getItem: () => null, setItem: () => {} };\n"
             "const SISTE_LISTE_NOKKEL = 'vaktliste:siste';\n")

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    RAD = {'mannskap_id': 1, 'navn': 'Kari', 'korps_kort': 'HGSD',
           'antall_skift': 2, 'timer': 14.0, 'lengste_skift': 8.0,
           'korteste_hvile': 10.0, 'overlapp': 0.0, 'faktiske_timer': None,
           'langt_skift': False, 'kort_hvile': False, 'har_overlapp': False}
    SAM = {'personer': 1, 'skift': 2, 'timer': 14.0, 'ledige_plasser': 0,
           'lange_skift': 0, 'korte_hviler': 0,
           'overlapp': 0.0, 'overlappende_personer': 0}

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

    # ── Budsjettlinja og dagslinja (15. sep. 2026) ────────────────────────

    PLAN = {'timetak': None, 'satt_opp': 312.0, 'bemannet': 244.0,
            'probono': 0.0, 'igjen': None, 'over_taket': False, 'dager': []}

    def _budsjett(self, plan=None, *, kan_sette_tak=True):
        """Bare budsjettlinja, uten resten av fanen."""
        import json
        data = {'personer': [self.RAD], 'sammendrag': self.SAM,
                'planlegging': None if plan is None else {**self.PLAN, **plan},
                'kan_sette_tak': kan_sette_tak,
                'grenser': {'maks_skift_timer': 12, 'min_hvile_timer': 8}}
        return run_node(self.harness, self.VINDU + f"""
            globalThis.belastning = {json.dumps(data)};
            console.log(mkBudsjett());
        """)

    def test_uten_budsjettall_finnes_linja_ikke(self):
        """Serveren sender `planlegging: null` til den som ikke ser alle
        korps. En tom ramme ville sagt «her er noe du ikke får se», som er
        en dårligere beskjed enn ingen beskjed."""
        # `run_node` skriver alltid «OK» til slutt, så «ingenting tegnet»
        # er den linja alene — ikke en tom streng.
        self.assertEqual('OK', self._budsjett(None).strip())

    def test_satt_opp_og_bemannet_staar_side_om_side(self):
        """Beslutning 5. Hvert tall alene lyver litt: ingen betaler for en
        tom plass, og «bemannet» står på null når lista er halvt satt opp."""
        ut = self._budsjett({})
        self.assertIn('satt opp', ut)
        self.assertIn('bemannet', ut)
        self.assertIn('312 t', ut)
        self.assertIn('244 t', ut)

    def test_avstanden_mellom_dem_er_arbeidslista(self):
        """68 timer som mangler folk — en subtraksjon leseren ellers måtte
        gjøre i hodet."""
        ut = self._budsjett({})
        self.assertIn('mangler folk', ut)
        self.assertIn('68 t', ut)

    def test_ingenting_mangler_naar_alt_er_bemannet(self):
        ut = self._budsjett({'satt_opp': 244.0, 'bemannet': 244.0})
        self.assertNotIn('mangler folk', ut)

    def test_uten_tak_staar_verken_tak_eller_igjen(self):
        """«Igjen» uten et tak er meningsløst, og de to andre tallene står
        like godt alene."""
        ut = self._budsjett({})
        self.assertNotIn('>tak<', ut)
        self.assertNotIn('igjen', ut)

    def test_med_tak_staar_begge(self):
        ut = self._budsjett({'timetak': 400, 'igjen': 88.0})
        self.assertIn('400 t', ut)
        self.assertIn('88 t', ut)
        self.assertIn('igjen', ut)

    def test_over_taket_merkes_gult_og_sier_over_taket(self):
        """«Varsler, det sperrer ikke» — merket er gult (`vl-advarsel`),
        ikke rødt, og teksten bytter fra «igjen» til «over taket» så et
        negativt tall ikke leses som en regnefeil."""
        ut = self._budsjett({'timetak': 300, 'igjen': -12.0,
                             'over_taket': True})
        self.assertIn('vl-advarsel', ut)
        self.assertIn('over taket', ut)
        self.assertNotIn('>igjen<', ut)

    def test_probono_staar_bare_naar_det_finnes(self):
        """Posten finnes for at summen ikke skal utelate noe i stillhet
        (beslutning 9). Står den på null, utelater den ingenting."""
        self.assertNotIn('probono', self._budsjett({}))
        self.assertIn('probono', self._budsjett({'probono': 16.0}))

    def test_knappen_staar_bare_for_den_som_kan_sette_taket(self):
        """Serveren svarer `kan_sette_tak`; klienten regner den ikke ut av
        `MODUL_TILGANG`. Ellers kan knappen og endepunktet komme i utakt —
        og en knapp som fører til en vegg er verre enn ingen knapp."""
        self.assertIn('apneTimetak', self._budsjett({}))
        self.assertNotIn('apneTimetak',
                         self._budsjett({}, kan_sette_tak=False))

    def test_knappeteksten_sier_om_det_finnes_et_tak_fra_foer(self):
        self.assertIn('Sett tak', self._budsjett({}))
        self.assertIn('Endre tak', self._budsjett({'timetak': 400}))

    def test_dagslinja_staar_ikke_paa_en_endagsvakt(self):
        """Én dag er ingen nedbryting — bare totalen skrevet to ganger."""
        en_dag = [{'nokkel': '2026-10-02', 'fra_tid': '2026-10-02T08:00:00',
                   'timer': 312.0}]
        self.assertNotIn('vl-dagslinje', self._budsjett({'dager': en_dag}))

    def test_dagslinja_viser_en_celle_per_dag_i_serverens_rekkefoelge(self):
        """Dagene kommer sortert fra serveren, og byggeren skal ikke sortere
        på nytt — to steder å sortere er ett sted å komme i utakt.

        Cellene leses i den rekkefølgen de står i markupen, ikke bare som
        «finnes i svaret»: en bygger som snudde lista ville ellers gått
        grønn."""
        dager = [
            {'nokkel': '2026-10-02', 'fra_tid': '2026-10-02T08:00:00', 'timer': 128.0},
            {'nokkel': '2026-10-03', 'fra_tid': '2026-10-03T08:00:00', 'timer': 152.0},
            {'nokkel': '2026-10-04', 'fra_tid': '2026-10-04T08:00:00', 'timer': 32.0},
        ]
        ut = self._budsjett({'dager': dager})
        self.assertIn('vl-dagslinje', ut)
        self.assertEqual(3, ut.count('vl-dagtall'))
        self.assertEqual([ut.index('128 t'), ut.index('152 t'), ut.index('32 t')],
                         sorted([ut.index('128 t'), ut.index('152 t'),
                                 ut.index('32 t')]))

    def test_dagslinja_sier_hvilket_tall_den_bryter_ned(self):
        """Uten etiketten måtte leseren gjette om dagene summerer til «satt
        opp» eller til «bemannet»."""
        dager = [
            {'nokkel': '2026-10-02', 'fra_tid': '2026-10-02T08:00:00', 'timer': 160.0},
            {'nokkel': '2026-10-03', 'fra_tid': '2026-10-03T08:00:00', 'timer': 152.0},
        ]
        self.assertIn('Satt opp per dag', self._budsjett({'dager': dager}))

    def test_budsjettlinja_staar_ikke_i_denne_fanen(self):
        """**Flyttet til «Planlegger» 15. sep. 2026.** Den sto først her;
        André: «Jeg ba om en planlegger … Den skal bare admin og leder ha
        tilgang til.» Vaktas budsjett er lederens verktøy, og denne fanen er
        `les` — lista regnet sammen, for alle som ser den.

        Testen står igjen som en **motprøve**: kommer linja tilbake hit ved
        en refaktorering, er den synlig for et nivå den ikke skal være
        synlig for."""
        import json
        data = {'personer': [self.RAD], 'sammendrag': self.SAM,
                'planlegging': self.PLAN, 'kan_sette_tak': True,
                'grenser': {'maks_skift_timer': 12, 'min_hvile_timer': 8}}
        ut = run_node(self.harness, self.VINDU + f"""
            globalThis.belastning = {json.dumps(data)};
            console.log(mkBelastning());
        """)
        self.assertNotIn('satt opp', ut)
        self.assertIn('Per person', ut, 'resten av fanen står som før')

    def test_overlappskolonnen_staar_ikke_naar_ingen_er_dobbeltbooket(self):
        """Samme regel som Faktisk-kolonnen: i den normale lista er
        overlappet null for alle, og en kolonne full av nuller stjeler
        bredde fra dem som betyr noe."""
        ut = self._vis()
        self.assertNotIn('<th>Overlapp</th>', ut)

    def test_overlappskolonnen_kommer_naar_noen_er_dobbeltbooket(self):
        """**Tallet leses ut av `<tbody>`, ikke ut av hele svaret.**
        Mutasjonsprøvd 15. sep. 2026: en `overlappTall` som alltid ga streken
        overlevde, fordi «4 t» også står i varselet i hodet. En assertion som
        treffer et annet sted enn den mener, måler ikke det den sier."""
        ut = self._vis([{**self.RAD, 'overlapp': 4.0, 'har_overlapp': True}],
                       {'overlapp': 4.0, 'overlappende_personer': 1})
        self.assertIn('<th>Overlapp</th>', ut)
        kropp = ut[ut.index('<tbody>'):ut.index('</tbody>')]
        self.assertIn('4 t', kropp, 'tallet skal stå i raden, ikke bare i varselet')
        self.assertIn('vl-advarsel', kropp)

    def test_overlappsvarselet_sier_timer_og_ikke_en_grense(self):
        """Et langt skift måles mot organisasjonens grense; et overlapp er
        en planleggingsfeil uansett hva grensene sier. Teksten sier derfor
        timene, ikke en terskel."""
        ut = self._vis([{**self.RAD, 'overlapp': 4.0, 'har_overlapp': True}],
                       {'overlapp': 4.0, 'overlappende_personer': 1})
        self.assertNotIn('Ingen varsler', ut)
        # Leses ut av varselblokka, ikke ut av hele svaret: «4 t» står i
        # raden også, og en assertion mot hele strengen ville gått grønn
        # selv om varselet mistet tallet sitt. (Mutasjonsprøvd.)
        varsler = ut[ut.index('vl-varsler'):ut.index('vl-tabell-belastning')]
        self.assertIn('dobbeltbooket', varsler)
        self.assertIn('4 t', varsler, 'varselet sier timene, ikke en terskel')
        self.assertNotIn('over 12 t', varsler.split('dobbeltbooket')[-1])

    def test_raden_uten_overlapp_faar_strek_naar_kolonnen_staar(self):
        """Null er det normale her, og en kolonne full av nuller drukner
        den ene raden som faktisk har et tall."""
        ut = self._vis([{**self.RAD, 'overlapp': 4.0, 'har_overlapp': True},
                        {**self.RAD, 'mannskap_id': 2, 'navn': 'Ola'}],
                       {'personer': 2, 'overlapp': 4.0,
                        'overlappende_personer': 1})
        olas_rad = ut[ut.index('Ola'):]
        self.assertIn('—', olas_rad)

    def test_kolonneandelene_summerer_til_hundre_i_alle_fire_former(self):
        """To valgfrie kolonner gir fire former. Med `table-layout: fixed`
        gir en `<colgroup>` med feil antall `<col>` ingen feilmelding —
        nettleseren deler bare resten likt — så regelen må måles.

        Teller `<th>`-ene i stedet for å skrive av et forventet tall:
        skrives tallet av, går testen grønn den dagen en kolonne legges til
        i hodet og glemmes i andelene."""
        import re
        for faktisk in (False, True):
            for overlapp in (False, True):
                with self.subTest(faktisk=faktisk, overlapp=overlapp):
                    rad = {**self.RAD,
                           'faktiske_timer': 12.0 if faktisk else None,
                           'overlapp': 4.0 if overlapp else 0.0,
                           'har_overlapp': overlapp}
                    ut = self._vis([rad], {'overlappende_personer':
                                           1 if overlapp else 0})
                    tabell = ut[ut.index('vl-tabell-belastning'):]
                    andeler = [int(a) for a in
                               re.findall(r'width:\s*(\d+)%', tabell)]
                    kolonner = tabell.count('<th>')
                    self.assertEqual(kolonner, len(andeler),
                                     f'én andel per kolonne, fikk {andeler}')
                    self.assertEqual(100, sum(andeler),
                                     f'andelene skal summere til 100, fikk {andeler}')

    def test_navnekolonnen_er_fortsatt_den_bredeste(self):
        """Andelene regnes nå ut, og en normalisering som gikk galt ville
        gitt seks like kolonner uten å feile. Navnet trenger mest plass."""
        import re
        ut = self._vis()
        tabell = ut[ut.index('vl-tabell-belastning'):]
        andeler = [int(a) for a in re.findall(r'width:\s*(\d+)%', tabell)]
        self.assertEqual(andeler[0], max(andeler))
        self.assertGreater(andeler[0], min(andeler) * 2)

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
            globalThis.PLANLEGGER = 'planlegger';
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

    def test_planleggeren_henter_de_samme_tallene(self):
        """**Budsjettlinja står øverst i planleggeren**, og tegnes av
        `mkBudsjett()` — som gir tom streng uten `belastning`.

        Den sto utenfor denne regelen én kjøring, og da var taket og timene
        usynlige på en ny vaktliste (André, 15. sep. 2026: «tak på vaktene og
        timene er ikke synlige når du oppretter ny vaktliste og går inn i
        planlegger»). Ingenting feilet — linja bare manglet."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.belastning = null;
            globalThis.register = null;
            globalThis.aktivListe = null;
            globalThis.MANNSKAP = 'mannskap';
            globalThis.BELASTNING = 'belastning';
            globalThis.PLANLEGGER = 'planlegger';
            globalThis.aktivFane = 'oversikt';
            let hentet = 0;
            globalThis.lastBelastning = () => { hentet += 1; };
            globalThis.lastRegister = () => {};
            globalThis.tegnFaner = () => {};
            globalThis.tegnPanel = () => {};

            visFane('planlegger');
            assert(hentet === 1, 'planleggeren hentet ikke tallene: ' + hentet);
        """)
        self.assertIn('OK', ut)

    # `aktivListe` og `belastning` er `let` på toppnivå i kjernefila. En
    # uttrukket funksjon som skriver til dem trenger derfor en binding i
    # modulen — `globalThis.aktivListe` er *ikke* den bindingen, og en naken
    # tilordning i en ESM-modul gir `ReferenceError`. `var` i preamblet
    # heises til toppen og er det nærmeste vi kommer skriptets eget scope.
    LASTLISTE_PREAMBLE = (
        'var aktivListe, belastning, aktivFane, korpsfilter;\n'
        "globalThis.BELASTNING = 'belastning';\n"
        "globalThis.PLANLEGGER = 'planlegger';\n")

    def _lastListe(self, fane):
        return run_node(self.harness, f"""
            aktivFane = '{fane}';
            belastning = {{personer: []}};
            globalThis.offlineTilstand = {{}};
            globalThis.apiFetch = async () => ({{
                ok: true, status: 200,
                headers: {{ get: () => null }},
                json: async () => ({{ data: {{ vaktliste: {{ id: 1 }},
                                              vaktposter: [] }} }}),
            }});
            globalThis.document = {{ getElementById: () => null }};
            let hentet = 0;
            globalThis.lastBelastning = () => {{ hentet += 1; }};
            for (const n of ['_sesjonUtgaatt', '_projiserKo', 'fyllKorpsvelger',
                             'brukKorpsfilter', 'tegnManglerMannskap',
                             'fyllNedtrekk', 'tegn', 'tegnOffline',
                             'planleggerSikreLinjer']) {{
                globalThis[n] = () => {{}};
            }}

            await lastListe(1);
            console.log('HENTET=' + hentet);
        """, preamble=self.VINDU + self.LASTLISTE_PREAMBLE)

    def test_tallene_hentes_paa_nytt_naar_lista_lastes(self):
        """`lastListe()` nullstiller `belastning` fordi tallene er utdaterte i
        det et skift endres. Uten hentingen etterpå står belastningsfanen på
        «Regner…» og budsjettlinja i planleggeren forsvinner — helt til man
        bytter fane og tilbake. Og det er nettopp etter en lagring man ser
        etter det nye tallet."""
        for fane in ('belastning', 'planlegger'):
            with self.subTest(fane=fane):
                self.assertIn('HENTET=1', self._lastListe(fane))

    def test_lista_henter_ikke_tallene_for_en_fane_som_ikke_bruker_dem(self):
        self.assertIn('HENTET=0', self._lastListe('oversikt'))

    def test_regelen_dekker_begge_fanene_og_ikke_de_andre(self):
        """Regelen står som én funksjon fordi den har to lesere: fanevalget og
        korpsvelgeren, som nullstiller tallene og henter dem på nytt."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.BELASTNING = 'belastning';
            globalThis.PLANLEGGER = 'planlegger';
            assert(faneTrengerBelastning('belastning'), 'belastning');
            assert(faneTrengerBelastning('planlegger'), 'planlegger');
            assert(!faneTrengerBelastning('oversikt'), 'oversikt');
            assert(!faneTrengerBelastning('mannskap'), 'mannskap');
            assert(!faneTrengerBelastning(7), 'en gruppefane');
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkOversikt', '_grupperPaaDag', 'mkUtskriftsverktoy', '_utskriftsdager', '_utvalgstekst', '_tidsblokker', '_blokklinje', '_blokkerMedDager', '_blokkrader', 'kanBemannePlass', '_mittKorpsId', '_synligePoster', '_dagnokkel', '_dagoverskrift', '_dagtekst', '_probonoMerke', '_telling', '_driftrad', '_plancellene', '_planrad', '_rolleValg', '_fyllValgFor', 'opptattPaaPlassen', '_plassKorps', '_varighet', '_skifttimer', '_tall', '_iso16', '_radklasse', '_stempelknapper', 'kanStemple', 'iDrift', 'kanSkriveAlt', 'kanSetteOppSkift', '_nivaa', '_erAdmin', '_skiftrekkefolge', '_sumTimer', '_d', '_kl', '_dag', '_sammeDag', '_tidsspenn', '_vaktspenn', '_ressurserIGruppe', '_grupperMedRessurser', 'kanRoreRad')),
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
    def test_oversikten_har_tidskolonnen_tilbake(self):
        """**Regelen snudde, og det er verdt å skrive ned hvorfor.**

        Til 16. sep. 2026 sto det motsatte her: «Oversikten har ingen
        tidskolonne lenger», fordi kolonnen gjentok samme verdi på hver
        personrad og tiden hørte hjemme på blokklinja over dem.

        Personradene er borte (André: «Må være en faktisk oversikt»), og da er
        raden *selv* blokken. Tiden er ikke lenger en gjentakelse — den er det
        raden handler om. Blokklinja finnes fortsatt, men i gruppefanen, der
        personradene bor.
        """
        ut = self._oversikt()
        self.assertIn('<th>Tid</th>', ut)
        self.assertNotIn('vl-blokk"', ut, 'ingen blokklinje over personrader her')

    def test_en_rad_per_spenn_per_ressurs(self):
        """Samleplassen har to spenn, hver ambulanse ett: fire rader.

        Dette er den samme regelen som før — ett spenn, én linje — bare at
        linja nå *er* raden i stedet for en overskrift over flere rader.
        """
        ut = self._oversikt()
        self.assertEqual(ut.count('class="vl-oversikt-tid"'), 4)

    def test_tiden_skrives_en_gang_per_blokk(self):
        """Tre skift på samleplassen begynner 17:00 — men 17:00 står to
        ganger, én per blokk, ikke tre. Poenget overlevde omskrivingen:
        blokken er fortsatt enheten, den er bare blitt en rad."""
        ut = self._oversikt()
        samleplass = ut[ut.index('>Samleplass'):ut.index('>Ambulanse 1')]
        self.assertEqual(samleplass.count('17:00'), 2)

    def test_sumraden_er_dagens_fasit(self):
        """**Sumraden var udekket til 16. sep. 2026** — funnet ved
        mutasjonstesting: den lot seg endre til å summere bare de *besatte*
        timene uten at noe ble rødt.

        Det er nettopp den feilen som ikke ville blitt oppdaget i bruk. Et
        budsjettall som stille utelater de ledige plassene ser helt rimelig
        ut — det er bare for lavt, og man planlegger etter det.

        Andrés fredag: samleplassen har 1 + 2 ledige plasser (5,3 t og 20 t),
        de to ambulansene én besatt hver (10 t). Fem plasser, to besatte, tre
        ledige, 45,3 timer i alt.
        """
        ut = self._oversikt()
        sumrad = ut[ut.index('vl-sumrad'):]
        self.assertIn('>5<', sumrad, 'plasser')
        self.assertIn('>2<', sumrad, 'besatt')
        self.assertIn('>3<', sumrad, 'ledige')
        self.assertIn('>45,3 t<', sumrad,
                      'timene teller de ledige plassene med — de er planlagt')

    def test_totalkolonnen_summerer_blokkens_timer(self):
        """10 + 10 på den lange blokka, 5,25 på den korte — summert per rad i
        «Totalt», ikke i en overskrift. Og formatet er fortsatt komma:
        «20 t» og «5,3 t»."""
        ut = self._oversikt()
        samleplass = ut[ut.index('>Samleplass'):ut.index('>Ambulanse 1')]
        self.assertIn('>5,3 t<', samleplass, 'den korte blokka')
        self.assertIn('>20 t<', samleplass, 'den lange: to plasser à 10 t')

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

    def test_ledige_plasser_telles_og_merkes(self):
        """Ledige plasser hadde hver sin rad til 16. sep. 2026. Nå er de et
        tall i sin egen kolonne, og raden merkes — for det er de radene man
        leter etter i en oversikt.

        Samleplassen har tre ledige fordelt på to blokker: 1 + 2.
        """
        ut = self._oversikt()
        samleplass = ut[ut.index('>Samleplass'):ut.index('>Ambulanse 1')]
        self.assertEqual(samleplass.count('vl-ledigtall'), 2, 'begge blokkene har ledige')
        self.assertIn('vl-har-ledige', samleplass)

    # ── Driftraden ───────────────────────────────────────────────────────
    def test_driftraden_er_regnearket_med_stempelet_foran(self):
        """Snudd 12. sep. 2026: driftraden var uten tidsfelt («fire like
        tider under hverandre»), men André ville redigere under drift som i
        planlegging. Blokklinja bærer fortsatt tiden; raden bærer feltene."""
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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


class NyVaktlisteTidsfelteneTests(SimpleTestCase):
    """Tidsfeltene i «Ny vaktliste» oppfører seg som planleggerens.

    André, 15. sep. 2026: «lik tidsfelt som vi har i planleggeren når en skal
    lage ny vaktliste. Der er det mismatch og den i ny vaktliste er litt
    knotete.»

    **`type` og `step` var like fra før.** Det som manglet var alt det andre
    som gjør planleggerens felter behagelige: de står aldri tomme, det ene
    følger det andre, og spennet leses tilbake mens man skriver. Et tomt
    `datetime-local` må tastes inn segment for segment uten noe å nudge på —
    det er det «knotete» betyr.
    """

    HARNESS = (
        (VAKTLISTE_JS, ('apneNyVaktliste', '_nesteHeleTime', '_settTidsfelt',
                        '_varighetstekst', 'nyVaktSpenntekst',
                        'nyVaktTegnSpenn', 'nyVaktStartEndret',
                        'nyVaktSluttEndret', '_tidFraFelt', '_skjulFeil',
                        '_iso16', '_d', '_tall')),
    )
    # `nyVaktSluttRort` er `let` på toppnivå. En uttrukket funksjon som
    # skriver til den trenger en binding i modulen — `globalThis.…` er ikke
    # den bindingen, og en naken tilordning i ESM gir `ReferenceError`.
    PREAMBLE = ('var nyVaktSluttRort;\n'
                'globalThis.NY_VAKT_SPENN_MS = 8 * 3600000;\n')

    DOM = """
        const felter = {
          'ny-vakt-navn': {value: 'noe gammelt'},
          'ny-vakt-start': {value: ''},
          'ny-vakt-slutt': {value: ''},
          'ny-vakt-spenn': {textContent: '', classList: {toggle() {}}},
          'ny-vakt-feil': {classList: {add() {}, remove() {}}, textContent: ''},
        };
        globalThis.document = {getElementById: (id) => felter[id] || null};
        let apnet = null;
        globalThis._apneModal = (id) => { apnet = id; };
    """

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _kjor(self, snippet):
        return run_node(self.harness, self.DOM + snippet,
                        preamble=self.PREAMBLE)

    # ── Feltene står aldri tomme ─────────────────────────────────────────

    def test_begge_feltene_er_fylt_ut_naar_vinduet_apnes(self):
        ut = self._kjor("""
            apneNyVaktliste();
            assert(apnet === 'nyVaktlisteModal', 'vinduet ble ikke åpnet');
            assert(/^\\d{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$/
                     .test(felter['ny-vakt-start'].value),
                   'start: «' + felter['ny-vakt-start'].value + '»');
            assert(/^\\d{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$/
                     .test(felter['ny-vakt-slutt'].value),
                   'slutt: «' + felter['ny-vakt-slutt'].value + '»');
        """)
        self.assertIn('OK', ut)

    def test_starten_settes_til_en_hel_time(self):
        """`new Date()` gir 21:37, og med `step="300"` er nærmeste lovlige
        verdi 21:35 — et tall ingen har ment, og som må rettes først."""
        ut = self._kjor("""
            apneNyVaktliste();
            const minutter = felter['ny-vakt-start'].value.slice(-2);
            assert(minutter === '00', 'minutter: ' + minutter);
        """)
        self.assertIn('OK', ut)

    def test_hele_timen_er_den_neste_ikke_den_inneverende(self):
        """Et tidspunkt som alt er passert leser som noe man har glemt å
        rette."""
        ut = self._kjor("""
            const naa = new Date(2026, 9, 3, 21, 37, 12);
            const t = _nesteHeleTime(naa);
            assert(t.getHours() === 22, 'time: ' + t.getHours());
            assert(t.getMinutes() === 0 && t.getSeconds() === 0, 'ikke hel');
            assert(t.getTime() > naa.getTime(), 'ligger bakover i tid');
        """)
        self.assertIn('OK', ut)

    def test_vinduet_tommer_navnet_ved_apning(self):
        ut = self._kjor("""
            apneNyVaktliste();
            assert(felter['ny-vakt-navn'].value === '',
                   'navn: «' + felter['ny-vakt-navn'].value + '»');
        """)
        self.assertIn('OK', ut)

    # ── Slutten følger starten, til noen rører den ───────────────────────

    def test_slutten_folger_starten(self):
        """Samme idé som at et nytt skiftvindu begynner der det forrige
        sluttet: det vanlige er å flytte hele vakta."""
        ut = self._kjor("""
            apneNyVaktliste();
            felter['ny-vakt-start'].value = '2026-10-03T14:00';
            nyVaktStartEndret();
            assert(felter['ny-vakt-slutt'].value === '2026-10-03T22:00',
                   'slutt: ' + felter['ny-vakt-slutt'].value);
        """)
        self.assertIn('OK', ut)

    def test_slutten_slutter_aa_folge_naar_noen_har_rort_den(self):
        """Har du skrevet «søndag 14:00», skal en rettelse av startdatoen
        ikke dra sluttiden med seg — da hadde feltet spist det du skrev."""
        ut = self._kjor("""
            apneNyVaktliste();
            felter['ny-vakt-slutt'].value = '2026-10-05T14:00';
            nyVaktSluttEndret();
            felter['ny-vakt-start'].value = '2026-10-03T14:00';
            nyVaktStartEndret();
            assert(felter['ny-vakt-slutt'].value === '2026-10-05T14:00',
                   'slutten ble overskrevet: ' + felter['ny-vakt-slutt'].value);
        """)
        self.assertIn('OK', ut)

    def test_tomt_sluttfelt_teller_ikke_som_rort(self):
        """Rydder man feltet, skal følgingen begynne å virke igjen framfor å
        la det stå tomt for godt."""
        ut = self._kjor("""
            apneNyVaktliste();
            felter['ny-vakt-slutt'].value = '2026-10-05T14:00';
            nyVaktSluttEndret();
            felter['ny-vakt-slutt'].value = '';
            nyVaktSluttEndret();
            felter['ny-vakt-start'].value = '2026-10-03T14:00';
            nyVaktStartEndret();
            assert(felter['ny-vakt-slutt'].value === '2026-10-03T22:00',
                   'slutt: ' + felter['ny-vakt-slutt'].value);
        """)
        self.assertIn('OK', ut)

    def test_en_ny_apning_glemmer_at_slutten_var_rort(self):
        """Flagget hører til vinduet man står i, ikke til sida."""
        ut = self._kjor("""
            apneNyVaktliste();
            felter['ny-vakt-slutt'].value = '2026-10-05T14:00';
            nyVaktSluttEndret();
            apneNyVaktliste();
            felter['ny-vakt-start'].value = '2026-10-03T14:00';
            nyVaktStartEndret();
            assert(felter['ny-vakt-slutt'].value === '2026-10-03T22:00',
                   'slutt: ' + felter['ny-vakt-slutt'].value);
        """)
        self.assertIn('OK', ut)

    def test_en_halvskrevet_start_flytter_ingenting(self):
        """`datetime-local` melder `change` per segment og gir tom verdi til
        alle er fylt ut. Uten sjekken ville sluttfeltet blitt tømt mens man
        skrev."""
        ut = self._kjor("""
            apneNyVaktliste();
            const foer = felter['ny-vakt-slutt'].value;
            felter['ny-vakt-start'].value = '';
            nyVaktStartEndret();
            assert(felter['ny-vakt-slutt'].value === foer,
                   'slutten ble rørt: ' + felter['ny-vakt-slutt'].value);
        """)
        self.assertIn('OK', ut)

    # ── Spennet leses tilbake ────────────────────────────────────────────

    def test_spennet_staar_under_feltene(self):
        ut = self._kjor("""
            apneNyVaktliste();
            felter['ny-vakt-start'].value = '2026-10-02T14:00';
            felter['ny-vakt-slutt'].value = '2026-10-04T20:00';
            nyVaktTegnSpenn();
            assert(/2 d 6 t/.test(felter['ny-vakt-spenn'].textContent),
                   'spenn: ' + felter['ny-vakt-spenn'].textContent);
        """)
        self.assertIn('OK', ut)

    def test_korte_vakter_skrives_i_timer(self):
        ut = self._kjor("""
            assert(_varighetstekst(8 * 3600000) === '8 t', _varighetstekst(8 * 3600000));
            assert(_varighetstekst(8.5 * 3600000) === '8,5 t',
                   _varighetstekst(8.5 * 3600000));
        """)
        self.assertIn('OK', ut)

    def test_hele_dogn_skrives_uten_timerest(self):
        """«2 d 0 t» leser som om noe mangler."""
        ut = self._kjor("""
            assert(_varighetstekst(48 * 3600000) === '2 d', _varighetstekst(48 * 3600000));
        """)
        self.assertIn('OK', ut)

    def test_bakvendt_spenn_sier_fra_framfor_aa_vise_et_tall(self):
        """Serveren avviser det uansett; dette er beskjeden om at man ikke er
        ferdig. Gult, ikke rødt — som et ugyldig skiftvindu."""
        ut = self._kjor("""
            felter['ny-vakt-start'].value = '2026-10-04T20:00';
            felter['ny-vakt-slutt'].value = '2026-10-02T14:00';
            assert(/må slutte etter/.test(nyVaktSpenntekst()), nyVaktSpenntekst());
            let merket = null;
            felter['ny-vakt-spenn'].classList.toggle = (k, paa) => { merket = [k, paa]; };
            nyVaktTegnSpenn();
            assert(merket && merket[0] === 'vl-advarsel' && merket[1] === true,
                   'ikke merket: ' + JSON.stringify(merket));
        """)
        self.assertIn('OK', ut)

    def test_uferdig_utfylling_ber_om_resten(self):
        ut = self._kjor("""
            felter['ny-vakt-start'].value = '2026-10-04T20:00';
            felter['ny-vakt-slutt'].value = '';
            assert(/Fyll ut/.test(nyVaktSpenntekst()), nyVaktSpenntekst());
        """)
        self.assertIn('OK', ut)

    # ── Malen ────────────────────────────────────────────────────────────

    def test_vinduet_apnes_av_js_ikke_av_bootstrap(self):
        """Feltene skal fylles ut før vinduet vises — et skjema som fyller
        seg selv etter at man ser det, ser ut som om noe rettet det man
        skrev."""
        from pathlib import Path
        from django.conf import settings
        mal = (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
               / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('data-bs-target="#nyVaktlisteModal"', mal)
        self.assertIn('data-action="apneNyVaktliste"', mal)

    def test_feltene_melder_sin_egen_hendelse(self):
        """`data-hendelse="change"` er den andre lytteren i
        `portal-utils.js`; uten den ville klikkdelegeringen kalt handleren
        når man åpner velgeren."""
        from pathlib import Path
        from django.conf import settings
        mal = (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
               / 'index.html').read_text(encoding='utf-8')
        import re
        for felt, handling in (('ny-vakt-start', 'nyVaktStartEndret'),
                               ('ny-vakt-slutt', 'nyVaktSluttEndret')):
            with self.subTest(felt=felt):
                tagg = re.search(r'<input[^>]*id="%s"[^>]*>' % felt, mal)
                self.assertIsNotNone(tagg, f'fant ikke feltet {felt}')
                self.assertIn(f'data-action="{handling}"', tagg.group(0))
                self.assertIn('data-hendelse="change"', tagg.group(0))

    def test_steget_er_fem_minutter_som_i_planleggeren(self):
        """Det ene som *var* likt fra før, og som skal forbli det: piltasten
        og velgeren hopper fem minutter, ikke ett."""
        import re
        from pathlib import Path
        from django.conf import settings
        mal = (Path(settings.BASE_DIR) / 'templates' / 'vaktliste'
               / 'index.html').read_text(encoding='utf-8')
        for felt in ('ny-vakt-start', 'ny-vakt-slutt'):
            with self.subTest(felt=felt):
                tagg = re.search(r'<input[^>]*id="%s"[^>]*>' % felt, mal)
                self.assertIsNotNone(tagg, f'fant ikke feltet {felt}')
                self.assertIn('step="300"', tagg.group(0))
                self.assertIn('type="datetime-local"', tagg.group(0))


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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkBelastning', 'mkBudsjett', 'mkDagslinje',
                        '_budsjettpost', '_dagtekst', '_d', 'kanSetteTak',
                        '_tall', '_kolonneandeler', 'kanLede',
                        '_nivaa', '_erAdmin')),
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.korpsfilter = null; globalThis.utskriftDag = null;
            brukKorpsfilter();
            assert(aktivListe.vaktposter.length === 4, 'tilbake til alle');
            assert(register.mannskap.length === 2, 'registeret tilbake');
        """)

    def test_velgeren_faller_tilbake_naar_korpset_er_borte(self):
        """Et valg som ikke finnes i lista er et filter man ikke ser."""
        ut = run_node(self.harness, """
            const el = {innerHTML: '', value: ''};
            globalThis.document = {getElementById: (id) => (id === 'vl-korpsvalg' ? el : null)};
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
            globalThis.aktivListe = {korps: [{id: 1, navn: '<img src=x onerror=alert(1)>', kortnavn: ''}]};
            globalThis.korpsfilter = null; globalThis.utskriftDag = null;
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

    def test_merkelappen_staar_ikke_i_oversikten_lenger(self):
        """Merkelappen hører til personen, og personene er ute av oversikten
        (16. sep. 2026). Den prøves fortsatt der den bor — i ressursraden,
        av `test_probonomerket_staar_i_raden` — så regelen har ikke mistet
        dekning; den har flyttet dit den gjelder.

        Her er det **timene** som bærer probono, gjennom `Totalt` (testen
        over). Denne står igjen for å holde de to fra hverandre: sniker en
        personrad seg inn i oversikten igjen, er punkt 2 i pulje 3 reversert.
        """
        ut = self._oversikt("aktivListe.vaktposter[3].probono = true;\n")
        self.assertNotIn('vl-merkelapp', ut)
        self.assertNotIn('>Kari<', ut, 'ingen personnavn i en talloversikt')

    def test_totalkolonnen_hopper_over_probono(self):
        """Ambulanse 1: Karis skift på 10 t er probono → «0 t» i «Totalt».

        **Den viktigste av de omskrevne testene** (16. sep. 2026): regelen —
        probono-timer er ikke organisasjonens (11. sep.) — måtte følge med da
        summen flyttet fra en overskrift til en kolonne. En totalsum som
        stille begynte å telle probono ville ingen oppdaget, og den skal
        stemme med budsjettlinja og med `belastning_per_person`.
        """
        ut = self._oversikt("aktivListe.vaktposter[3].probono = true;\n")
        amb1 = ut[ut.index('>Ambulanse 1'):ut.index('>Ambulanse 2')]
        self.assertIn('>0 t<', amb1)

    def test_driftraden_baerer_merket(self):
        ut = run_node(self.harness, self.VINDU + """
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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

    @staticmethod
    def _tittel(tekst):
        """Dagoverskriften i arket. Den bare teksten duger ikke: dagnavnene
        står også i dagvelgeren over lista, og den kommer først i markupen —
        et søk på «Lørdag 5. sep» traff velgeren og målte hele arket."""
        return f'<h2 class="vl-dagtittel">{tekst}'

    def test_dagen_staar_over_ressursen(self):
        """Kjernen i snuingen (14. sep. 2026): dagtittelen kommer før
        ressursen. Regelen overlevde omskrivingen til en talloversikt
        16. sep. — ressursen er en rad nå, men dagen er fortsatt ytterst."""
        ut = self._oversikt()
        self.assertLess(ut.index('class="vl-dagtittel"'), ut.index('>Samleplass'),
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
        # **Tittelen, ikke den bare teksten**: dagnavnene står nå også i
        # dagvelgeren over lista, og den kommer først i markupen.
        self.assertIn(self._tittel('Fredag 4. sep'), ut)
        self.assertIn(self._tittel('Lørdag 5. sep'), ut)
        self.assertLess(ut.index(self._tittel('Fredag 4. sep')),
                        ut.index(self._tittel('Lørdag 5. sep')))

    def test_ressursen_gjentas_under_hver_dag_den_har_skift(self):
        """Samleplassen har skift begge dager og skal stå i begge bolkene —
        det er nettopp det snuingen koster, og det er riktig her. Ressursen
        er en rad fra 16. sep. 2026, men regelen er den samme."""
        ut = self._oversikt(self.LORDAG)
        skille = ut.index(self._tittel('Lørdag 5. sep'))
        # **Per bolk, ikke totalt.** Samleplassen har *to* blokker fredag, så
        # et samlet radtall ville vært tre og sagt ingenting om hvilke dager
        # den står under. Det er tilstedeværelsen i hver bolk som er regelen.
        self.assertIn('<td class="vl-navn">Samleplass', ut[:skille])
        self.assertIn('<td class="vl-navn">Samleplass', ut[skille:])

    def test_dagbolken_viser_bare_sin_egen_dags_skift(self):
        """Ninas skift står lørdag. Det skal ikke telle med i fredagsbolken.

        Navnene er ute av oversikten (16. sep. 2026), så regelen prøves på
        **ressursen hennes**: Ambulanse 2 har bare lørdagens skift, og skal
        derfor bare stå i lørdagsbolken.
        """
        ut = self._oversikt(self.LORDAG)
        skille = ut.index(self._tittel('Lørdag 5. sep'))
        fredag, lordag = ut[:skille], ut[skille:]
        # Ninas skift er 08:00–16:00 på samleplassen lørdag. Blokka hennes
        # skal bare finnes i lørdagsbolken — fredag har sine egne to spenn.
        self.assertNotIn('08:00', fredag)
        self.assertIn('08:00', lordag)

    def test_skift_over_midnatt_staar_bare_under_startdagen(self):
        """Andrés samleplass-skift går 17:00 fredag til 03:00 lørdag. Det
        står under fredag, **ikke** under begge og ikke splittet (André,
        15. sep. 2026). Merk at rapportmodulen har landet motsatt for timer;
        forskjellen er bevisst."""
        ut = self._oversikt(self.LORDAG)
        lordag = ut[ut.index(self._tittel('Lørdag 5. sep')):]
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('mkMittKorps', '_mittKorpsId', '_synligePoster',
                        'kanBemannePlass', 'kanSkriveAlt', 'kanSetteOppSkift', '_nivaa', '_erAdmin',
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
        globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
            globalThis.utskriftDag = null; globalThis.korpsfilter = null;
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
    """Utskrift per korps eller **per dag** (André, 12. og 15. sep. 2026).

    Velgeren tilbød ressursene fram til 15. sep. Det ga mening da arket var
    gruppert på ressurs; etter at dagen ble ytterste nivå ville «Ambulanse 1»
    vært et snitt på tvers av det arket er bygget rundt. André: *«vi beholder
    hele vakten, men fjerner ressursene og bytter med dag. Går vakta én dag får
    du ikke flere valg; går den over flere dager får du den enkelte dag.»*

    Korpset kommer fortsatt fra korpsvelgeren (alt filtrert i
    `aktivListe.vaktposter`). Arket sier selv hva det er avgrenset til —
    velgeren kommer ikke med på papiret.
    """

    HARNESS = TidsblokkerTests.HARNESS
    VINDU = TidsblokkerTests.VINDU
    LISTE = UtskriftslistaTests.LISTE

    #: Andrés rader er alle 4. sep. Nina gjør vakta til to dager.
    LORDAG = """
        aktivListe.vaktposter.push({id: 9, ressurs_id: 10, ledig: false, navn: 'Nina',
          korps_kort: 'HGSD', rolle: '', merknad: '',
          fra_tid: '2026-09-05T08:00:00', til_tid: '2026-09-05T16:00:00'});
    """
    #: Nøkkelen `_dagnokkel()` gir for lørdagen — nullpolstret.
    LORDAGSNOKKEL = '2026-09-05'

    def setUp(self):
        if not node_available():
            self.skipTest('node er ikke tilgjengelig')
        self.harness = build_harness(self.HARNESS)

    def _oversikt(self, ekstra=''):
        return run_node(self.harness, self.VINDU + self.LISTE + ekstra
                        + "console.log(mkOversikt());")

    # ── Endagsvakt: ingen velger ─────────────────────────────────────────
    def test_endagsvakt_har_ingen_velger(self):
        """**«Går vakta én dag får du ikke flere valg.»** Ett valg i et
        nedtrekk er en kontroll som ikke gjør noe — knappen står igjen alene."""
        ut = self._oversikt()
        self.assertNotIn('vl-utskriftsvalg', ut)
        self.assertNotIn('Hele vakten', ut)
        self.assertIn('data-action="skrivUt"', ut, 'utskriftsknappen skal staa igjen')

    def test_flerdagsvakt_faar_en_velger_med_en_rad_per_dag(self):
        ut = self._oversikt(self.LORDAG)
        self.assertIn('<option value="">Hele vakten</option>', ut)
        self.assertIn('<option value="2026-09-04">Fredag 4. sep</option>', ut)
        self.assertIn(f'<option value="{self.LORDAGSNOKKEL}">Lørdag 5. sep</option>', ut)
        self.assertIn('data-action="velgUtskrift" data-hendelse="change"', ut)

    def test_ingen_ressurser_i_velgeren(self):
        """Selve endringen: ressursene skal være borte, ikke stå ved siden av."""
        ut = self._oversikt(self.LORDAG)
        velger = ut[ut.index('vl-utskriftsvalg'):ut.index('</select>')]
        self.assertNotIn('optgroup', velger)
        self.assertNotIn('Ambulanse', velger)
        self.assertNotIn('Samleplass', velger)

    def test_den_valgte_dagen_merkes(self):
        """Merket leses av `utskriftDag`, ikke av hva `<select>` husker —
        panelet tegnes på nytt ved hvert faneskift."""
        ut = self._oversikt(self.LORDAG
                            + f"globalThis.utskriftDag = '{self.LORDAGSNOKKEL}';\n")
        self.assertIn(f'<option value="{self.LORDAGSNOKKEL}" selected>Lørdag 5. sep</option>', ut)
        self.assertIn('<option value="2026-09-04">Fredag 4. sep</option>', ut)

    # ── Hva arket blir ───────────────────────────────────────────────────
    def test_valgt_dag_gir_bare_den_dagen(self):
        """Dagutvalget siler skiftene før tabellen bygges, så tallene i
        arkhodet følger utvalget. Personnavnene er ute av oversikten
        (16. sep. 2026), så det som telles er **bolkene** — én dag, én
        dagbolk — og fredagens skift skal være silt bort."""
        ut = self._oversikt(self.LORDAG
                            + f"globalThis.utskriftDag = '{self.LORDAGSNOKKEL}';\n")
        self.assertEqual(ut.count('class="vl-dagbolk"'), 1)
        self.assertNotIn('Kari', ut, 'fredagens skift er silt bort')

    def test_summene_i_arkhodet_foelger_utvalget(self):
        """Skriver man ut lørdag, skal hodet si lørdagens timer — ikke hele
        vaktas. Derfor filtreres postene før tallene regnes, ikke i bolkene."""
        hele = self._oversikt(self.LORDAG)
        lordag = self._oversikt(self.LORDAG
                                + f"globalThis.utskriftDag = '{self.LORDAGSNOKKEL}';\n")
        arkhode = lordag[lordag.index('vl-arkhode'):lordag.index('class="vl-dagbolk"')]
        self.assertIn('1 skift · 1 mannskap · 8 t', arkhode)
        self.assertIn('53,3 t', hele[hele.index('vl-arkhode'):hele.index('class="vl-dagbolk"')])

    def test_arket_sier_hva_det_er_avgrenset_til(self):
        hele = self._oversikt(self.LORDAG)
        self.assertNotIn('vl-utvalg"', hele)
        dag = self._oversikt(self.LORDAG
                             + f"globalThis.utskriftDag = '{self.LORDAGSNOKKEL}';\n")
        self.assertIn('<div class="vl-utvalg">Lørdag 5. sep</div>', dag)
        begge = self._oversikt(self.LORDAG
                               + f"globalThis.utskriftDag = '{self.LORDAGSNOKKEL}';\n"
                               + "globalThis.korpsfilter = 1;\n")
        self.assertIn('<div class="vl-utvalg">Haugesund · Lørdag 5. sep</div>', begge)

    def test_ukjent_dag_gir_tomt_ark_og_ikke_en_krasj(self):
        """Et valg som ikke finnes lenger — lista ble lastet på nytt og dagen
        forsvant — skal gi «ingen er satt opp», ikke en feil."""
        ut = self._oversikt("globalThis.utskriftDag = '1999-01-01';\n")
        self.assertIn('Ingen er satt opp', ut)


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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
        (VAKTLISTE_JS, ('kanRoreRad', 'kanBemannePlass', 'kanSkriveAlt', 'kanSetteOppSkift', '_nivaa', '_erAdmin')),
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
        (PORTAL_UTILS_JS, ('velgTekst', 'velgValg', 'escapeHtml', 'escHtmlValue')),
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
