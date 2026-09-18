"""`static/js/ko.js`, kjørt i node.

To funksjoner her *avgjør* noe, og det er dem som prøves: `koInaktivTekst()`
bestemmer hva lista påstår om en person, og `koKontomerke()` bestemmer om en
delt konto ser ut som en delt konto. Resten er markup, og der er øyet raskere
enn en mutant — unntatt escapingen, som har en egen prøve fordi brukernavn er
brukerdata.

JS-oppførsel testes ved å kjøre funksjonene, ikke ved å grep-e etter kodelinjer
(CLAUDE.md).
"""
from __future__ import annotations

import json
import re
import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import (JS_DIR, PORTAL_UTILS_JS, build_harness,
                                    extract_function, node_available, run_node)

KO_JS = JS_DIR / 'ko.js'

#: Enhetskortets innmat, delt med sentralbordet (17. sep. 2026). `/ko/` laster
#: den, så testene her må lese den — ellers kjører de mot en side som ikke
#: finnes. Skanningen av *den* fila hører til `oppdrag/tests_xss.py`, som eier
#: den; her brukes den bare som avhengighet, på samme måte som portal-utils.
OPPDRAG_KORT_JS = JS_DIR / 'oppdrag-kort.js'

HARNESS = (
    (PORTAL_UTILS_JS, ('escapeHtml',)),
    (KO_JS, ('koInaktivTekst', 'koKontomerke', 'koTilstedeRad')),
)

#: `koInaktivTekst` leser konstantene på toppnivå i fila. De er ikke funksjoner,
#: så `build_harness` klipper dem ikke med — og uten dem er `KO_AKTIV_GRENSE_S`
#: `undefined`, og hver sammenligning mot den blir `false`. Det ville gitt en
#: test som består på tull.
PREAMBLE = 'const KO_AKTIV_GRENSE_S = 120;\n'


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class InaktivTekstTests(SimpleTestCase):
    """**`null` er «vet ikke», og skal aldri bli «0».**

    En sesjon fra før aktivitetsmålingen fantes, eller en klient som aldri har
    kalt `apiFetch`, har ingen verdi. Skrev vi «aktiv», ville hver gammel
    sesjon sett ut som om noen satt der — og lista finnes nettopp for å skille
    de to. Serveren tar det samme valget i `core/sesjoner.py`.
    """

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _kall(self, uttrykk):
        ut = run_node(self.harness, f'console.log(JSON.stringify({uttrykk}));',
                      preamble=PREAMBLE)
        return ut.splitlines()[0]

    def test_ukjent_er_ikke_aktiv(self):
        self.assertEqual(self._kall('koInaktivTekst(null)'), '"ukjent"')
        self.assertEqual(self._kall('koInaktivTekst(undefined)'), '"ukjent"')

    def test_null_sekunder_er_aktiv(self):
        """Grensa den andre veien: 0 er et ekte tall, ikke fravær."""
        self.assertEqual(self._kall('koInaktivTekst(0)'), '"aktiv"')

    def test_grensa_gaar_der_den_staar(self):
        """119 er innenfor, 120 er utenfor. En grense av med én her er ikke
        farlig, men den er usynlig — derfor prøves begge sidene."""
        self.assertEqual(self._kall('koInaktivTekst(119)'), '"aktiv"')
        self.assertEqual(self._kall('koInaktivTekst(120)'), '"2 min"')

    def test_minutter_og_timer(self):
        self.assertEqual(self._kall('koInaktivTekst(600)'), '"10 min"')
        self.assertEqual(self._kall('koInaktivTekst(3540)'), '"59 min"')
        self.assertEqual(self._kall('koInaktivTekst(3600)'), '"1 t"')
        self.assertEqual(self._kall('koInaktivTekst(7300)'), '"2 t"')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KontomerkeTests(SimpleTestCase):
    """§4.5: «Enhet 2» og «Kari Nordmann» betyr fundamentalt ulike ting."""

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def _kall(self, uttrykk):
        return run_node(self.harness, f'console.log(JSON.stringify({uttrykk}));',
                        preamble=PREAMBLE).splitlines()[0]

    def test_delt_konto_vinner_over_admin(self):
        """En delt admin-konto skal merkes som **delt**. Det er den
        opplysningen som endrer hva linja betyr; at kontoen også er admin er
        en detalj ved siden av."""
        self.assertEqual(
            self._kall('koKontomerke({er_delt_konto: true, er_global_admin: true})'),
            '"delt"')

    def test_vanlig_konto_faar_ikke_merke(self):
        self.assertEqual(
            self._kall('koKontomerke({er_delt_konto: false, er_global_admin: false})'),
            '""')

    def test_admin_merkes(self):
        self.assertEqual(
            self._kall('koKontomerke({er_delt_konto: false, er_global_admin: true})'),
            '"admin"')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class RadenEscaperBrukernavnTests(SimpleTestCase):
    """Brukernavn er brukerdata, og raden settes inn med `innerHTML`.

    Admin bestemmer brukernavnet, så veien hit er kort — men den er ikke
    stengt, og en logg over hvem som sitter i KO skal ikke være stedet der
    markup slipper gjennom.
    """

    def setUp(self):
        self.harness = build_harness(HARNESS)

    def test_markup_i_brukernavnet_blir_tekst(self):
        ut = run_node(self.harness, '''
          const html = koTilstedeRad({
            brukernavn: '<img src=x onerror=alert(1)>',
            er_delt_konto: false, er_global_admin: false, inaktiv_s: 5});
          assert(!html.includes('<img'), 'rå <img> i raden: ' + html);
          assert(html.includes('&lt;img'), 'brukernavnet ble ikke escapet: ' + html);
        ''', preamble=PREAMBLE)
        self.assertIn('OK', ut)

    def test_raden_viser_det_den_skal(self):
        """Sperrehake mot testen over: en builder som returnerer tom streng
        ville bestått den."""
        ut = run_node(self.harness, '''
          const html = koTilstedeRad({
            brukernavn: 'kari', er_delt_konto: true,
            er_global_admin: false, inaktiv_s: null});
          assert(html.includes('kari'), 'brukernavnet mangler: ' + html);
          assert(html.includes('delt'), 'merket mangler: ' + html);
          assert(html.includes('ukjent'), 'inaktivkolonnen mangler: ' + html);
        ''', preamble=PREAMBLE)
        self.assertIn('OK', ut)


# ════════════════════════════════════════════════════════════════════════════
# LOGGEN (pulje 2)
# ════════════════════════════════════════════════════════════════════════════

KO_LOGG_BYGGERE = (
    'koLinjeHtml',
    'koLinjeTekst',
    'koLinjeKnapper',
    'koTilstedeRad',
    # De to setter sammen ferdige fragmenter til en liste. De bygger markup
    # like fullt, og står her og ikke i en unntaksliste: dagen noen limer et
    # felt rett inn i overskriften, skal skanneren se det.
    'koTegnLogg',
    'koTegnTilstede',
    # Hendelsene (pulje 5). Overskriften på tavla, knappene i den,
    # knytt/løsne i detaljmodalen og nedtrekket i «Nytt oppdrag».
    'koHendelseHode',
    'koHendelseKnapper',
    'koHendelseValg',
    'koFyllHendelsevalg',
    'koLeggHendelsevalgINyttOppdrag',
    # Vaktlistas ressurser (pulje 6): kortet, mannskapslinja og lista.
    'koRessurskort',
    'koRessursMannskap',
    'koTegnRessurser',
)

#: Uttrykk som interpoleres uten `escapeHtml`, med begrunnelse.
#: Samme form som `REVIEWED_INTERPOLATIONS` i `oppdrag/tests_xss.py`.
KO_GJENNOMGATT = {
    'merkeHtml': 'markup bygget to linjer over, merket selv escapet der',
    'rettet': 'fast markup fra en ternær, ingen data i',
    'omraade': 'markup bygget to linjer over, ansvarsområdet escapet der',
    'hvem': 'markup bygget av en ternær; forfatternavnet escapet i den ene grenen',
    'av': 'markup bygget to linjer over, navnet escapet der',
    # Hendelsene (pulje 5):
    'hendelseHtml': 'markup bygget rett over, nummeret escapet der',
    'antallTekst': 'tall og et fast ord, escapet ved innsetting',
    'sted': 'markup bygget rett over, lokasjonsnavnet escapet der',
    'apne': 'markup bygget rett over, tallet escapet der',
    'knapper': 'markup fra koHendelseKnapper(), som skannes for seg',
    'id': 'escapeHtml over h.id, satt rett over',
    'naa': 'markup bygget rett over, nummer og tittel escapet der',
    'valg': 'options bygget rett over, id og tekst escapet der',
    'losne': 'knapp bygget rett over, id escapet der',
    # Pulje 6:
    'linjeKlasse': 'hardkodet CSS-klasse fra en ternær',
    'merkeKlasse': 'hardkodet CSS-klasse fra en ternær',
    'ansvarHtml': 'markup bygget rett over, området escapet der',
    'tall': 'escapeHtml over to tall og et fast ord, eller et fast ord',
    'hode': 'markup fra gruppehode() i oppdrag-kort.js, alt escapet der',
    'navn': 'mannskapsnavn escapet i map-en rett over',
    'nesteNavn': 'mannskapsnavn escapet i map-en rett over',
    'kort': 'markup fra koRessurskort(), som skannes for seg',
}


class LoggByggerneEscaperTests(SimpleTestCase):
    """Statisk gjennomgang av byggerne i `ko.js`.

    **Skanneren her leser konkatenering, ikke mal-strenger.** `ko.js` bygger
    markup med `'...' + x + '...'`, mens `oppdrag/tests_xss.py` leser
    `` `...${x}...` ``. En kopi av den skanneren ville funnet null byggere her
    og meldt grønt — og en skanner som melder grønt om en dekning den ikke
    har, er verre enn ingen skanner (`CLAUDE.md`).

    **Grensen for hva den ser**, skrevet ned så den ikke må gjettes: den finner
    et **datafelt** (`noe.felt`) limt rett inn i en konkatenering. En lokal
    variabel bygget lenger oppe fanges *ikke* — derfor står de fem i
    `KO_GJENNOMGATT`, og derfor finnes oppførselsprøven under, som kjører
    byggerne med fiendtlige data gjennom den ekte inngangen.
    """

    def _kropp(self, navn):
        kilde = KO_JS.read_text(encoding='utf-8')
        kropp = extract_function(kilde, navn)
        # **Strip kommentarene først.** En test som leser sin egen prosa måler
        # at noen har skrevet om begrunnelsen, ikke at koden gjør det den sier
        # (CLAUDE.md, 16. sep. 2026).
        return '\n'.join(l for l in kropp.splitlines()
                         if not l.lstrip().startswith('//'))

    def test_hver_bygger_finnes(self):
        """Vern mot at testen blir tom fordi en funksjon er omdøpt."""
        kilde = KO_JS.read_text(encoding='utf-8')
        for navn in KO_LOGG_BYGGERE:
            with self.subTest(navn=navn):
                self.assertIn(f'function {navn}(', kilde)

    def test_ingen_bygger_staar_utenfor_skanningen(self):
        """En håndholdt liste forfaller i stillhet.

        `_enhetskort` i oppdragsmodulen ble hoistet ut av sin bygger og falt
        ut av skanningen med det samme — ni byggere sto utenfor uten at noe
        var rødt. Denne sammenligner lista med kilden, så neste utklipping
        sier fra selv.
        """
        kilde = KO_JS.read_text(encoding='utf-8')
        funn = set()
        for navn in re.findall(r'^function (\w+)\(', kilde, re.M):
            kropp = self._kropp(navn)
            # En funksjon som limer noe inn i en streng med en tagg i.
            if re.search(r"'[^']*<\w[^']*'\s*\+", kropp):
                funn.add(navn)
        self.assertEqual(sorted(funn - set(KO_LOGG_BYGGERE)), [], (
            'Disse bygger markup i ko.js uten å bli skannet. Legg dem i '
            'KO_LOGG_BYGGERE.'))

    def test_hvert_datafelt_er_escapet_eller_gjennomgaatt(self):
        uescapet = []
        for navn in KO_LOGG_BYGGERE:
            kropp = self._kropp(navn)
            # `(?![\w(])` holder metodekall utenfor: `rader.map(...)` er en
            # kjede, ikke et datafelt limt inn i markup. **`\w` må med i
            # klassen** — uten den backtracker `\w+` til «ma» for å tilfredsstille
            # lookaheaden, og treffet rapporteres som et halvt feltnavn i
            # stedet for å forsvinne. En regel som melder «rader.ma» er en
            # regel ingen forstår.
            for uttrykk in re.findall(
                    r'\+\s*([a-z]\w*(?:\.\w+)+)(?![\w(])', kropp):
                if uttrykk in KO_GJENNOMGATT:
                    continue
                uescapet.append(f'{navn}(): + {uttrykk}')
        self.assertEqual(uescapet, [], (
            'Datafelt limt rett inn i markup i ko.js:\n  '
            + '\n  '.join(uescapet)
            + '\n\nPakk verdien i escapeHtml(). trustedHtml() er IKKE svaret: '
              'den returnerer et objekt, og blir «[object Object]» når den '
              'konkateneres. Se core/tests_js_regler.py.'))


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class LoggEscapingOppforselTests(SimpleTestCase):
    """Kjør byggerne med fiendtlige data og se at markup kommer ut som tekst.

    **KO-loggen er portalens frieste felt.** Pasientmodulens kliniske felter er
    valgt fra en fast verdimengde; her skriver en operatør hva som helst, og
    det settes inn i DOM-en med `innerHTML`.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml',)),
        (KO_JS, ('koKlokke', 'koLinjeMerke', 'koLinjeTekst', 'koLinjeKnapper',
                 'koLinjeHtml', 'koKanSkrive', 'koKanFjerne')),
    )

    ONDSKAP = '<img src=x onerror=alert(1)>'

    def setUp(self):
        self.harness = build_harness(self.HARNESS)

    def _kall(self, uttrykk, preamble=''):
        ut = run_node(self.harness, f'console.log({uttrykk});',
                      preamble='const window = {MODUL_TILGANG: '
                               '{ko: "skriv_leder"}};\n' + preamble)
        return ut

    def _linje(self, **overstyr):
        base = {
            'id': 1, 'rot': 1, 'kilde': 'operator',
            'tidspunkt': '2026-09-17T21:14:00', 'registrert_at': '2026-09-17T21:14:00',
            'tekst': 'ok', 'systemkode': '', 'forfatter': 'kari',
            'delt_konto': False, 'ansvarsomraade': '', 'korrigerer': None,
            'fjernet': False, 'fjernet_av': '', 'fjernet_at': '',
        }
        base.update(overstyr)
        return json.dumps(base)

    def test_teksten_escapes(self):
        ut = self._kall(f'koLinjeHtml({self._linje(tekst=self.ONDSKAP)})')
        self.assertNotIn('<img', ut)
        self.assertIn('&lt;img', ut)

    def test_forfatteren_escapes(self):
        """Brukernavnet er brukerdata: admin skriver det, og det fryses på
        linja."""
        ut = self._kall(f'koLinjeHtml({self._linje(forfatter=self.ONDSKAP)})')
        self.assertNotIn('<img', ut)

    def test_ansvarsomraadet_escapes(self):
        ut = self._kall(f'koLinjeHtml({self._linje(ansvarsomraade=self.ONDSKAP)})')
        self.assertNotIn('<img', ut)

    def test_fjernet_av_escapes(self):
        """Den fjernede linja tegner et *annet* navn enn forfatteren, og den
        grenen kjøres bare når noen har fjernet noe — altså sjelden, og
        derfor lett å glemme."""
        ut = self._kall(f'koLinjeHtml({self._linje(fjernet=True, fjernet_av=self.ONDSKAP)})')
        self.assertNotIn('<img', ut)

    def test_fjernet_linje_viser_at_den_er_fjernet(self):
        """**Et hull i loggen er verre enn en tømt linje**: da vet ingen at
        det sto noe der (§4.4)."""
        ut = self._kall(f'koLinjeHtml({self._linje(fjernet=True, tekst="", fjernet_av="andre")})')
        self.assertIn('fjernet', ut)
        self.assertIn('andre', ut)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class LoggReglerTests(SimpleTestCase):
    """De tre funksjonene i loggen som *avgjør* noe.

    Middels tyngde (`CLAUDE.md`): de er regler som tilfeldigvis kjører i en
    nettleser, og de er grunnen til at slike regler skilles ut som egne
    funksjoner i stedet for å ligge som en `if` inne i en bygger.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml',)),
        (KO_JS, ('koLinjeMerke', 'koKanSkrive', 'koKanFjerne', 'koLinjeKnapper')),
    )

    def setUp(self):
        self.harness = build_harness(self.HARNESS)

    def _kall(self, uttrykk, tilgang):
        ut = run_node(
            self.harness, f'console.log(JSON.stringify({uttrykk}));',
            preamble=f'const window = {{MODUL_TILGANG: {json.dumps(tilgang)}}};\n')
        return ut.splitlines()[0]

    def test_les_kan_verken_skrive_eller_fjerne(self):
        self.assertEqual(self._kall('koKanSkrive()', {'ko': 'les'}), 'false')
        self.assertEqual(self._kall('koKanFjerne()', {'ko': 'les'}), 'false')

    def test_skriv_full_kan_skrive_men_ikke_fjerne(self):
        """**Hele skillet mellom de to nivåene, målt.** Tegnes «Fjern» for
        `skriv_full`, fører knappen til 403 — og en knapp som fører til en
        vegg er verre enn ingen knapp."""
        self.assertEqual(self._kall('koKanSkrive()', {'ko': 'skriv_full'}), 'true')
        self.assertEqual(self._kall('koKanFjerne()', {'ko': 'skriv_full'}), 'false')

    def test_skriv_leder_kan_begge(self):
        self.assertEqual(self._kall('koKanSkrive()', {'ko': 'skriv_leder'}), 'true')
        self.assertEqual(self._kall('koKanFjerne()', {'ko': 'skriv_leder'}), 'true')

    def test_global_admin_kan_begge_uten_rad(self):
        """Global admin har ingen `ModulTilgang`-rad og likevel full tilgang.
        Samme felle som sidebaren gikk i: et filter på raden alene utelater
        nettopp den som sitter i KO og administrerer portalen."""
        self.assertEqual(self._kall('koKanSkrive()', {'admin': True}), 'true')
        self.assertEqual(self._kall('koKanFjerne()', {'admin': True}), 'true')

    def test_knappene_forsvinner_for_en_systemlinje(self):
        """Systemlinjer kan verken rettes eller fjernes — de er en projeksjon
        av noe som skjedde i oppdragsmodulen, og bærer ingen fritekst."""
        linje = json.dumps({'id': 1, 'kilde': 'system', 'fjernet': False})
        self.assertEqual(self._kall(f'koLinjeKnapper({linje})',
                                    {'ko': 'skriv_leder'}), '""')

    def test_knappene_forsvinner_for_en_fjernet_linje(self):
        linje = json.dumps({'id': 1, 'kilde': 'operator', 'fjernet': True})
        self.assertEqual(self._kall(f'koLinjeKnapper({linje})',
                                    {'ko': 'skriv_leder'}), '""')

    def test_merket_setter_fjernet_foran_delt(self):
        """Rekkefølgen i `koLinjeMerke` er en avgjørelse: en fjernet linje fra
        en delt konto skal merkes «fjernet», fordi det er den opplysningen som
        forklarer hvorfor det ikke står noe der."""
        linje = json.dumps({'fjernet': True, 'kilde': 'operator', 'delt_konto': True})
        self.assertEqual(self._kall(f'koLinjeMerke({linje})', {'ko': 'les'}),
                         '"fjernet"')



@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class KonsollhoydenTests(SimpleTestCase):
    """Høyden på konsollen er en **regel**, ikke formatering.

    Den avgjør om sida ruller eller kolonnene gjør det, og gulvet avgjør om en
    kort skjerm gir tre ubrukelige rullefelt eller en side som ruller. Begge
    deler er usynlige i en test som bare leser CSS-en.
    """

    HARNESS = ((KO_JS, ('koKonsollhoyde',)),)
    PREAMBLE = 'const KO_BUNNMARG = 16;\nconst KO_MIN_HOYDE = 360;\n'

    def setUp(self):
        self.harness = build_harness(self.HARNESS)

    def _kall(self, topp, vindu):
        return int(run_node(
            self.harness, f'console.log(koKonsollhoyde({topp}, {vindu}));',
            preamble=self.PREAMBLE).splitlines()[0])

    def test_fyller_resten_av_vinduet(self):
        """1080 px skjerm, konsollen begynner 240 px ned: 1080 - 240 - 16."""
        self.assertEqual(self._kall(240, 1080), 824)

    def test_en_hoeyere_header_gir_lavere_konsoll(self):
        """Det er hele grunnen til at høyden måles og ikke regnes ut av et
        fast tall: headeren, navigasjonen og meldingene kan alle brekke."""
        self.assertEqual(self._kall(300, 1080), 764)

    def test_gulvet_holder_naar_vinduet_er_kort(self):
        """Uten gulvet gir et kort vindu en konsoll på nitti piksler, og da er
        alle tre kolonnene ubrukelige samtidig. Da er det bedre at sida ruller:
        det ser rart ut, men alt er lesbart."""
        self.assertEqual(self._kall(300, 400), 360)

    def test_gulvet_holder_ogsaa_naar_regnestykket_blir_negativt(self):
        self.assertEqual(self._kall(900, 500), 360)


# ════════════════════════════════════════════════════════════════════════════
# Hendelsene (pulje 5): regelen for grupperingen, og nummerformene.
# ════════════════════════════════════════════════════════════════════════════

GRUPPERING_HARNESS = (
    (PORTAL_UTILS_JS, ('escapeHtml',)),
    (OPPDRAG_KORT_JS, ('oppdragsnr', 'hendelsesnr')),
    (KO_JS, ('koGrupperOppdrag', 'koHendelseHode', 'koHendelseKnapper', 'koKanSkrive')),
)

#: `koGrupperOppdrag` leser to toppnivåbindinger, som `build_harness` ikke
#: klipper med. Uten `koHendelser` er hver `.values()` et krasj.
GRUPPERING_PREAMBLE = (
    'let koHendelser = new Map();\n'
    'let koGruppert = true;\n'
    "globalThis.window = { MODUL_TILGANG: { ko: 'skriv_full' } };\n"
)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class GrupperingsregelenTests(SimpleTestCase):
    """`koGrupperOppdrag()` avgjør hva tavla viser, og prøves som en regel.

    §7: hendelsene er en gruppering av oppdragslista. Tre ting regelen skal
    holde: **av** betyr flat liste (`null`), en åpen hendelse uten oppdrag
    skal likevel stå der (det er hendelsen som «lever i tjue minutter før en
    ressurs sendes»), og «Uten hendelse» står sist — og skjuler ingenting.
    """

    def setUp(self):
        self.harness = build_harness(GRUPPERING_HARNESS)

    def _grupper(self, hendelser, rader, gruppert=True):
        snippet = f'''
            {json.dumps(hendelser)}.forEach((h) => koHendelser.set(h.id, h));
            koGruppert = {'true' if gruppert else 'false'};
            const ut = koGrupperOppdrag({json.dumps(rader)});
            console.log(JSON.stringify(ut === null ? null : ut.map((g) => ({{
              hendelse: g.hendelse ? g.hendelse.id : null,
              rader: g.rader.map((o) => o.id),
              hode: g.hode,
            }}))));
        '''
        return json.loads(run_node(self.harness, snippet, preamble=GRUPPERING_PREAMBLE).splitlines()[0])

    H1 = {'id': 1, 'nummer': 1, 'kode': 'H1', 'tittel': 'Brann', 'status': 'apen',
          'lokasjon_navn': '', 'apne_oppdrag': 0}
    H2 = {'id': 2, 'nummer': 2, 'kode': 'H2', 'tittel': 'Slagsmål', 'status': 'apen',
          'lokasjon_navn': 'Scene sør', 'apne_oppdrag': 1}
    H3 = {'id': 3, 'nummer': 3, 'kode': 'H3', 'tittel': 'Gammel', 'status': 'lukket',
          'lokasjon_navn': '', 'apne_oppdrag': 0}

    def test_av_gir_flat_liste(self):
        self.assertIsNone(self._grupper([self.H1], [{'id': 10, 'hendelse_id': 1}], gruppert=False))

    def test_aapen_hendelse_uten_oppdrag_staar_der(self):
        ut = self._grupper([self.H1, self.H2], [{'id': 10, 'hendelse_id': 2}])
        self.assertEqual([g['hendelse'] for g in ut], [2, 1])
        self.assertEqual([g['rader'] for g in ut], [[10], []])

    def test_tom_uten_hendelse_vises_bare_naar_den_er_alene(self):
        """En overskrift over ingenting er støy — men er den hele lista, er
        den lista, og skal stå."""
        ut = self._grupper([], [])
        self.assertEqual([g['hendelse'] for g in ut], [None])
        ut = self._grupper([self.H1], [])
        self.assertEqual([g['hendelse'] for g in ut], [1])

    def test_lukket_hendelse_vises_bare_med_rader(self):
        """Ellers ville oppdragene forsvunnet fra tavla idet hendelsen ble
        lukket — og en lukket hendelse uten rader hører hjemme i loggen."""
        ut = self._grupper([self.H1, self.H3], [{'id': 10, 'hendelse_id': 3}])
        self.assertEqual([g['hendelse'] for g in ut], [1, 3])
        ut = self._grupper([self.H1, self.H3], [{'id': 10, 'hendelse_id': None}])
        self.assertEqual([g['hendelse'] for g in ut], [1, None])

    def test_uten_hendelse_staar_sist_og_faar_alt_ukjent(self):
        """Et oppdrag som peker på en hendelse tavla ikke har fått ennå (to
        pollere, to klokker) skal ikke forsvinne."""
        ut = self._grupper([self.H1], [
            {'id': 10, 'hendelse_id': None}, {'id': 11, 'hendelse_id': 99}, {'id': 12, 'hendelse_id': 1}])
        self.assertEqual(ut[-1]['hendelse'], None)
        self.assertEqual(ut[-1]['rader'], [10, 11])
        self.assertEqual(ut[0]['rader'], [12])

    def test_ingenting_skjules(self):
        """§7.2 for grupperingen: summen av radene er lista."""
        rader = [{'id': i, 'hendelse_id': h} for i, h in ((1, 1), (2, 2), (3, None), (4, 3), (5, 7))]
        ut = self._grupper([self.H1, self.H2, self.H3], rader)
        self.assertEqual(sorted(sum((g['rader'] for g in ut), [])), [1, 2, 3, 4, 5])

    def test_hodet_escaper_og_baerer_sted_og_tall(self):
        h = dict(self.H2, tittel='<b>x</b>')
        ut = self._grupper([h], [{'id': 10, 'hendelse_id': 2}, {'id': 11, 'hendelse_id': 2}])
        hode = ut[0]['hode']
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', hode)
        self.assertNotIn('<b>x</b>', hode)
        self.assertIn('Scene sør', hode)
        self.assertIn('2 oppdrag', hode)
        self.assertIn('data-action="koLukkHendelse"', hode)
        self.assertNotIn('data-action="koGjenapneHendelse"', hode)
        ut = self._grupper([self.H3], [{'id': 10, 'hendelse_id': 3}, {'id': 11, 'hendelse_id': None}])
        self.assertIn('data-action="koGjenapneHendelse"', ut[0]['hode'])
        self.assertIn('Uten hendelse', ut[-1]['hode'])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class NummerformeneTests(SimpleTestCase):
    """`O45` og `H12` (§6) — samme regel som `oppdrag.services.oppdragsnr` og
    `ko.services.hendelsesnr` på serveren. Enhetsskjermen har sin egen kopi av
    `oppdragsnr`, og den skal si det samme."""

    def test_delte_formene(self):
        harness = build_harness(((OPPDRAG_KORT_JS, ('oppdragsnr', 'hendelsesnr')),))
        ut = run_node(harness, "console.log(oppdragsnr(45) + ' ' + hendelsesnr(12));")
        self.assertEqual(ut.splitlines()[0], 'O45 H12')

    def test_enhetsskjermens_kopi_sier_det_samme(self):
        harness = build_harness(((JS_DIR / 'oppdrag-enhet.js', ('oppdragsnr',)),))
        self.assertEqual(run_node(harness, 'console.log(oppdragsnr(45));').splitlines()[0], 'O45')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class TavlaSpoerEtterGrupperingenTests(SimpleTestCase):
    """**Kallstedet, ikke bare regelen.** `renderOppdrag()` i
    `oppdrag-sentral-oppdrag.js` skal spørre `koGrupperOppdrag()` når den
    finnes. Testene over kaller regelen selv, og da kunne tavla slutte å
    kalle den uten at noe ble rødt — regel 3 om mutanter i `CLAUDE.md`."""

    def setUp(self):
        from patients.js_test_utils import OPPDRAG_SENTRAL_JS
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
            (OPPDRAG_SENTRAL_JS, ('renderOppdrag', '_oppdragRadHtml', '_sorterOppdrag',
                                  'oppdragsnr', 'hendelsesnr', 'hastegradKlasse',
                                  'tidSiden', '_grovMerke', '_enhetsmatrise',
                                  '_problemMedAntall', '_medAntall', 'venterForbiTerskel',
                                  'lydTerskler', '_manglerTrinn', '_manglerMinutter')),
            (KO_JS, ('koGrupperOppdrag', 'koHendelseHode', 'koHendelseKnapper', 'koKanSkrive')),
        ))

    def test_tavla_tegner_overskriften(self):
        snippet = '''
            const HASTEGRAD_REKKEFOLGE = ['Akutt', 'Haster', 'Vanlig', 'Drift'];
            const MANGLER_TRINN = [[15, 'alvorlig'], [5, 'varsel'], [0, 'ny']];
            let koHendelser = new Map([[1, {id: 1, nummer: 1, kode: 'H1', tittel: 'Brann',
              status: 'apen', lokasjon_navn: '', apne_oppdrag: 1}]]);
            let koGruppert = true;
            let oppdragsliste = [{id: 7, nummer: 7, status: 'fremme', status_navn: 'Fremme',
              enhet_navn: 'HGSD 56', lokasjon_navn: 'Scene', problemstilling: 'Fall',
              hastegrad: 'Akutt', opprettet: '2026-08-28T20:00:00Z', fritekst: '',
              hendelse_id: 1, hendelse_nummer: 1, hendelse_tittel: 'Brann', enheter: []}];
            globalThis.window = { MODUL_TILGANG: { ko: 'skriv_full' } };
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: (id) => id === 'oppdragsliste' ? el : null };
            renderOppdrag();
            console.log(JSON.stringify(el.innerHTML));
            console.log(JSON.stringify(_oppdragRadHtml(oppdragsliste[0])));
        '''
        linjer = run_node(self.harness, snippet).splitlines()
        ut, rad = json.loads(linjer[0]), json.loads(linjer[1])
        self.assertIn('hendelse-hode', ut, 'tavla spurte ikke etter grupperingen')
        self.assertIn('Brann', ut)
        self.assertIn('O7', ut)
        # Raden alene: overskriften bærer også et `hendelse-merke`, så et
        # søk i hele tavla ser ikke om *raden* mistet sitt (mutant som
        # overlevde 18. sep. 2026).
        self.assertIn('hendelse-merke', rad, 'raden bærer H1-merket')
        self.assertIn('>H1<', rad)


# ════════════════════════════════════════════════════════════════════════════
# Pulje 6: merkene, minimerbare grupper og vaktlistas ressurskort.
# ════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class MerkeneTests(SimpleTestCase):
    """`koLinjeMerke()` avgjør hva linja *påstår* om seg selv. Rekkefølgen
    er en avgjørelse: fjernet slår alt, en hendelseslinje er «hendelse» og
    ikke «system» (André, 18. sep. 2026: «Hendelse må vises tydelig»), og
    chat vises selv om kontoen er delt."""

    def setUp(self):
        self.harness = build_harness(((PORTAL_UTILS_JS, ('escapeHtml',)),
                                      (KO_JS, ('koLinjeMerke',))))

    def _merke(self, **linje):
        base = {'fjernet': False, 'kilde': 'operator', 'systemkode': '',
                'uformell': False, 'delt_konto': False}
        base.update(linje)
        return run_node(self.harness,
                        f'console.log(JSON.stringify(koLinjeMerke({json.dumps(base)})));'
                        ).splitlines()[0]

    def test_hendelseslinja_er_hendelse_ikke_system(self):
        self.assertEqual(self._merke(kilde='system', systemkode='hendelse_lukket'), '"hendelse"')
        self.assertEqual(self._merke(kilde='system', systemkode='oppdrag_status'), '"system"')

    def test_chat_foran_delt(self):
        self.assertEqual(self._merke(uformell=True, delt_konto=True), '"chat"')
        self.assertEqual(self._merke(delt_konto=True), '"delt"')
        self.assertEqual(self._merke(), '""')

    def test_fjernet_slaar_alt(self):
        self.assertEqual(self._merke(fjernet=True, uformell=True,
                                     kilde='system', systemkode='hendelse_opprettet'), '"fjernet"')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class MinimerbareGrupperTests(SimpleTestCase):
    """Gruppeoverskriften er en knapp, og **en lukket gruppe skjuler ingenting
    stille** (§7.2): antallet står i overskriften. Tilstanden huskes i
    `localStorage`, stubbet her."""

    LAGER = '''
      const _lager = {};
      globalThis.localStorage = {
        getItem: (k) => (k in _lager ? _lager[k] : null),
        setItem: (k, v) => { _lager[k] = String(v); },
      };
      globalThis.window = { OPPDRAG_ENHETSTYPER: [[1, 'Ambulanse'], [2, 'Lag']], MODUL_TILGANG: {} };
      let sisteEnhetsliste = []; let enhetslisteKilde = null;
      let besetninger = {}; let apenBesetning = null;
      const GRUPPER_LUKKET_NOKKEL = 'tavle.grupper.lukket';
      function tegnEnhetslistePaaNytt() {}
      function mkBesetning() { return ''; }
      function kanSeBesetning() { return false; }
    '''

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
            (OPPDRAG_KORT_JS, ('_lukkedeGrupper', 'gruppeErLukket', 'vippGruppe', 'gruppehode',
                               '_ledigSammendrag', 'tegnEnhetsliste', '_grupperEnheter',
                               '_typeRekkefolge', '_enhetskort', 'enhetskortInnmat',
                               'tidSiden', 'hastegradKlasse', '_grovMerke', '_problemMedAntall',
                               '_medAntall', 'oppdragsnr')),
        ))

    def _kjor(self, kode):
        return run_node(self.harness, self.LAGER + kode)

    def test_vipp_lukker_og_aapner_og_huskes(self):
        ut = self._kjor('''
            console.log(gruppeErLukket('type:1'));
            vippGruppe('type:1');
            console.log(gruppeErLukket('type:1'));
            console.log(localStorage.getItem('tavle.grupper.lukket'));
            vippGruppe('type:1');
            console.log(gruppeErLukket('type:1'));
        ''').splitlines()
        self.assertEqual(ut[:4], ['false', 'true', '["type:1"]', 'false'])

    def test_lukket_gruppe_viser_antall_og_skjuler_kortene(self):
        ut = self._kjor('''
            const el = { innerHTML: '' };
            globalThis.document = { getElementById: (id) => id === 'enhetsliste' ? el : null };
            const liste = [
              {id: 1, navn: 'HGSD 56', pa_vakt: true, type: 1, status: 'ledig', status_navn: 'Ledig'},
              {id: 2, navn: 'KARM 12', pa_vakt: true, type: 1, status: 'fremme', status_navn: 'Fremme'},
              {id: 3, navn: 'Lag 3', pa_vakt: true, type: 2, status: 'ledig', status_navn: 'Ledig'},
            ];
            tegnEnhetsliste(liste);
            console.log(JSON.stringify(el.innerHTML));
            vippGruppe('type:1');
            tegnEnhetsliste(liste);
            console.log(JSON.stringify(el.innerHTML));
        ''').splitlines()
        aapen, lukket = json.loads(ut[0]), json.loads(ut[1])
        self.assertIn('HGSD 56', aapen)
        self.assertIn('data-action="vippGruppe"', aapen)
        self.assertNotIn('HGSD 56', lukket, 'kortene i den lukkede gruppa er borte')
        self.assertIn('Lag 3', lukket, 'den andre gruppa står')
        self.assertIn('enhet-gruppe-lukket', lukket)
        self.assertIn('2 · 1 ledig', lukket, 'antallet og sammendraget står i overskriften')

    def test_overskriften_escaper_navnet(self):
        ut = self._kjor('''console.log(gruppehode('type:1', '<b>x</b>', 2, ''));''')
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', ut)
        self.assertNotIn('<b>x</b>', ut)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class RessurskorteneTests(SimpleTestCase):
    """Vaktlistas ressurser på tavla: kortet sier hvem og om de er møtt —
    ingen status — og escaper navnene, som er fritekst fra et annet register."""

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koRessurskort', 'koRessursMannskap', 'koGrupperRessurser', 'koKlokke')),
        ))

    def _kort(self, r):
        return run_node(self.harness, f'console.log(koRessurskort({json.dumps(r)}));')

    def test_bemannet_kort(self):
        ut = self._kort({'id': 1, 'navn': 'Lag 3', 'gruppe_ikon': 'people', 'antall': 2, 'tilstede': 1,
                         'mannskap': [{'navn': 'Kari', 'tilstede': True}, {'navn': 'Ola', 'tilstede': False}],
                         'neste': [], 'neste_fra': None})
        self.assertIn('1 av 2 møtt', ut)
        self.assertIn('Kari', ut)
        self.assertIn('Ola <span class="text-muted">(ikke møtt)</span>', ut)
        self.assertIn('bi-people', ut)

    def test_ubemannet_med_neste(self):
        ut = self._kort({'id': 1, 'navn': 'KO', 'gruppe_ikon': '', 'antall': 0, 'tilstede': 0,
                         'mannskap': [], 'neste': [{'navn': 'Per', 'tilstede': False}],
                         'neste_fra': '2026-09-18T16:00:00+02:00'})
        self.assertIn('ubemannet', ut)
        self.assertIn('Ingen nå', ut)
        self.assertIn('Per', ut)

    def test_escaper_navn_og_ikon(self):
        ut = self._kort({'id': 1, 'navn': '<img src=x>', 'gruppe_ikon': '"><script>', 'antall': 1, 'tilstede': 1,
                         'mannskap': [{'navn': '<b>Kari</b>', 'tilstede': True}], 'neste': [], 'neste_fra': None})
        self.assertNotIn('<img src=x>', ut)
        self.assertNotIn('<script>', ut)
        self.assertNotIn('<b>Kari</b>', ut)

    def test_grupperer_paa_ressursgruppe_i_rekkefoelge(self):
        ut = run_node(self.harness, '''
            const g = koGrupperRessurser([
              {id: 1, navn: 'Lag 1', gruppe_id: 5, gruppe_navn: 'Lag'},
              {id: 2, navn: 'KO', gruppe_id: 7, gruppe_navn: 'KO'},
              {id: 3, navn: 'Lag 2', gruppe_id: 5, gruppe_navn: 'Lag'},
            ]);
            console.log(JSON.stringify(g.map((x) => [x.navn, x.ressurser.map((r) => r.navn)])));
        ''').splitlines()[0]
        self.assertEqual(json.loads(ut), [['Lag', ['Lag 1', 'Lag 2']], ['KO', ['KO']]])
