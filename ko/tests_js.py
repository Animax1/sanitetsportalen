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

from patients.js_test_utils import (JS_DIR, KO_JS, PORTAL_UTILS_JS, build_harness,
                                    extract_function, node_available, read_js, run_node)

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
    # ko.js: loggstrømmen og sidebaren.
    'koLinjeHtml',
    'koLinjeTekst',
    'koLinjeKnapper',
    'koFestetHtml',
    'koTilstedeRad',
    # De to setter sammen ferdige fragmenter til en liste. De bygger markup
    # like fullt, og står her og ikke i en unntaksliste: dagen noen limer et
    # felt rett inn i overskriften, skal skanneren se det.
    'koTegnLogg',
    'koTegnTilstede',
    # Vaktlistas ressurser (pulje 6): kortet, mannskapslinja og lista.
    'koRessurskort',
    'koRessursMannskap',
    'koTegnRessurser',
    # ko-hendelser.js (18. sep. 2026): tabellen, hendelsen åpnet i vinduet,
    # skjemaet, knytt/løsne i detaljmodalen og nedtrekket i «Nytt oppdrag».
    'koPrioMerke',
    'koHendelseRadHtml',
    'koTegnHendelser',
    'koDetaljLinjeHtml',
    'koHendelseOppdragHtml',
    'koPrioKnapperHtml',
    'koTegnDetalj',
    'koFyllLokasjoner',
    '_koFyllSkjema',
    'koHendelseValg',
    'koFyllHendelsevalg',
    'koLeggHendelsevalgINyttOppdrag',
    # «Nullstill»-fanen: ren markup uten data, men den bygger markup like fullt.
    'koTegnNullstill',
)

#: Uttrykk som interpoleres uten `escapeHtml`, med begrunnelse.
#: Samme form som `REVIEWED_INTERPOLATIONS` i `oppdrag/tests_xss.py`.
KO_GJENNOMGATT = {
    'rettet': 'fast markup fra en ternær, ingen data i',
    'hvem': 'markup bygget av en ternær; forfatternavnet escapet i den ene grenen',
    'av': 'markup bygget to linjer over, navnet escapet der',
    'merkeHtml': 'markup bygget rett over, merket selv escapet der',
    'hendelseHtml': 'markup bygget rett over, nummeret og id escapet der',
    'losne': 'knapp bygget rett over, id escapet der',
    'festetHtml': 'markup fra koFestetHtml(), som skannes for seg',
    # Hendelsene:
    'naa': 'markup bygget rett over, nummer og tittel escapet der',
    'valg': 'options bygget rett over, id og tekst escapet der',
    'under': 'markup bygget rett over, beskrivelsen escapet der',
    'melder': 'markup bygget rett over, melderen escapet der',
    'behovHtml': 'markup bygget rett over, navnene escapet i map-en',
    'behov': 'navnene escapet i map-en rett over',
    'oppdragHtml': 'markup bygget rett over, nummer og tall escapet der',
    'status': 'markup bygget rett over, klokkeslettet escapet der',
    'tekst': 'escapeHtml eller fast markup, fra en ternær rett over',
    'enheter': 'navnene escapet i map-en rett over',
    'knapper': 'markup bygget i map-en rett over, verdi og navn escapet der',
    'ikon': 'fast ikonmarkup fra en ternær',
    'aktiv': 'CSS-klasse med verdien escapet, rett over',
    'deltar': 'navnene escapet i map-en rett over',
    'knyttValg': 'markup bygget rett over, id og tekst escapet der',
    'nyttOppdrag': 'knapp bygget rett over, id escapet der',
    'hodeKnapper': 'markup bygget rett over, id escapet der',
    'bliMed': 'knapp bygget rett over, id escapet der',
    'lagFelt': 'markup bygget rett over, verdi og id escapet der',
    'skjema': 'markup bygget rett over, koden escapet der',
    'tall': 'escapeHtml over to tall og et fast ord, eller et fast ord',
    'hode': 'markup fra gruppehode() i oppdrag-kort.js, alt escapet der',
    'navn': 'mannskapsnavn escapet i map-en rett over',
    'nesteNavn': 'mannskapsnavn escapet i map-en rett over',
    'kort': 'markup fra koRessurskort(), som skannes for seg',
    'ansvarHtml': 'markup bygget rett over, området escapet der',
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
        kilde = read_js(KO_JS)
        kropp = extract_function(kilde, navn)
        # **Strip kommentarene først.** En test som leser sin egen prosa måler
        # at noen har skrevet om begrunnelsen, ikke at koden gjør det den sier
        # (CLAUDE.md, 16. sep. 2026).
        return '\n'.join(l for l in kropp.splitlines()
                         if not l.lstrip().startswith('//'))

    def test_hver_bygger_finnes(self):
        """Vern mot at testen blir tom fordi en funksjon er omdøpt."""
        kilde = read_js(KO_JS)
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
        kilde = read_js(KO_JS)
        funn = set()
        for navn in re.findall(r'^(?:async )?function (\w+)\(', kilde, re.M):
            kropp = self._kropp(navn)
            # En funksjon som limer noe inn i en streng med en tagg i.
            if re.search(r"'[^']*<\w[^']*'\s*\+", kropp):
                funn.add(navn)
        self.assertEqual(sorted(funn - set(KO_LOGG_BYGGERE)), [], (
            'Disse bygger markup i KO-filene uten å bli skannet. Legg dem i '
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
            'Datafelt limt rett inn i markup i KO-filene:\n  '
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
        (JS_DIR / 'oppdrag-kort.js', ('hendelsesnr',)),
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
            'festet_at': '', 'festet_av': '', 'hendelse_id': None, 'hendelse_nummer': None,
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
# Hendelsesloggen (18. sep. 2026): sortering, søk, raden — og nummerformene.
# ════════════════════════════════════════════════════════════════════════════

#: `koSorterHendelser` leser prioritetene fra `window.KO_PRIORITETER`, som
#: sida setter. Samme rekkefølge som `PRIORITET_VALG` på serveren.
PRIORITET_PREAMBLE = (
    "globalThis.window = { KO_PRIORITETER: [['viktig','Viktig'],['rod','Rød'],['gul','Gul'],"
    "['gronn','Grønn'],['drift','Drift']], MODUL_TILGANG: { ko: 'skriv_full' } };\n"
    "let koHendelser = new Map(); let koApenHendelseId = null; let koVisLukkede = true; let koSok = '';\n"
    'let koLinjer = new Map(); let oppdragsliste = [];\n'
)

HENDELSE_HARNESS = (
    (PORTAL_UTILS_JS, ('escapeHtml',)),
    (JS_DIR / 'oppdrag-kort.js', ('oppdragsnr', 'hendelsesnr', 'hastegradKlasse')),
    (KO_JS, ('koSorterHendelser', 'koHendelseTreffer', 'koSynligeHendelser', 'koApneHendelser',
             'koPrioriteter', 'koPrioritetNavn', 'koPrioritetRang', 'koPrioMerke', 'koPrioIkon',
             'koOppdragForHendelse', 'koHendelseRadHtml', 'koKlokke', 'koKanSkrive',
             'koIStrommen', 'koLinjeMerke')),
)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class SorteringsregelenTests(SimpleTestCase):
    """`koSorterHendelser()` avgjør hva som står øverst — **likt som
    oppdragslista** (André, 18. sep. 2026): lukkede nederst, så prioriteten,
    og innenfor den nummeret. Ren regel, og derfor prøvd som en."""

    def setUp(self):
        self.harness = build_harness(HENDELSE_HARNESS)

    def _sorter(self, liste):
        ut = run_node(self.harness,
                      f'console.log(JSON.stringify(koSorterHendelser({json.dumps(liste)}).map((h) => h.nummer)));',
                      preamble=PRIORITET_PREAMBLE)
        return json.loads(ut.splitlines()[0])

    def test_lukkede_nederst_saa_prioritet_saa_nummer(self):
        liste = [
            {'nummer': 1, 'status': 'apen', 'prioritet': 'gronn'},
            {'nummer': 2, 'status': 'lukket', 'prioritet': 'viktig'},
            {'nummer': 3, 'status': 'apen', 'prioritet': 'viktig'},
            {'nummer': 4, 'status': 'apen', 'prioritet': 'rod'},
            {'nummer': 5, 'status': 'apen', 'prioritet': 'gronn'},
            {'nummer': 6, 'status': 'apen', 'prioritet': 'drift'},
        ]
        self.assertEqual(self._sorter(liste), [3, 4, 1, 5, 6, 2])

    def test_ukjent_prioritet_loefter_ingenting(self):
        """En verdi fra en eldre klient skal ikke havne øverst."""
        liste = [{'nummer': 1, 'status': 'apen', 'prioritet': 'kritisk'},
                 {'nummer': 2, 'status': 'apen', 'prioritet': 'drift'}]
        self.assertEqual(self._sorter(liste), [2, 1])

    def test_soeket_treffer_nummer_tittel_sted_melder_og_lag(self):
        h = {'kode': 'H12', 'nummer': 12, 'tittel': 'Slagsmål', 'lokasjon_navn': 'Scene sør',
             'melder': 'Lag 1', 'beskrivelse': 'to personer', 'lagsressurser': 'Lag 3'}
        for sok, ventet in (('h12', True), ('12', True), ('slag', True), ('sør', True),
                            ('lag 1', True), ('personer', True), ('lag 3', True),
                            ('', True), ('  ', True), ('brann', False)):
            with self.subTest(sok=sok):
                ut = run_node(self.harness,
                              f'console.log(koHendelseTreffer({json.dumps(h)}, {json.dumps(sok)}));',
                              preamble=PRIORITET_PREAMBLE).splitlines()[0]
                self.assertEqual(ut, 'true' if ventet else 'false')

    def test_vis_lukkede_av_skjuler_bare_lukkede(self):
        kode = (
            "[{id: 1, nummer: 1, status: 'apen', prioritet: 'gronn'},"
            " {id: 2, nummer: 2, status: 'lukket', prioritet: 'gronn'}].forEach((h) => koHendelser.set(h.id, h));\n"
            'console.log(JSON.stringify(koSynligeHendelser().map((h) => h.id)));\n'
            'koVisLukkede = false;\n'
            'console.log(JSON.stringify(koSynligeHendelser().map((h) => h.id)));\n'
        )
        ut = run_node(self.harness, kode, preamble=PRIORITET_PREAMBLE).splitlines()
        self.assertEqual(json.loads(ut[0]), [1, 2])
        self.assertEqual(json.loads(ut[1]), [1])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class HendelsesradenTests(SimpleTestCase):
    """Raden i tabellen: prioriteten er en klasse *og* et merke med tekst,
    Viktig har utropstegnet, lukkede er merket, og alt brukerskrevet
    escapes."""

    def setUp(self):
        self.harness = build_harness(HENDELSE_HARNESS)

    def _rad(self, h, oppdrag=None):
        return run_node(self.harness,
                        f'oppdragsliste = {json.dumps(oppdrag or [])};\n'
                        f'console.log(koHendelseRadHtml({json.dumps(h)}));',
                        preamble=PRIORITET_PREAMBLE)

    H = {'id': 5, 'nummer': 14, 'kode': 'H14', 'tittel': 'Bevisstløs person', 'status': 'apen',
         'prioritet': 'viktig', 'lokasjon_navn': 'Hovedscene', 'melder': 'Lag 1',
         'beskrivelse': 'Mann ca. 40', 'lagsressurser': '', 'opprettet_at': '2026-09-18T21:42:00',
         'opprettet_av': 'kari', 'lukket_at': '', 'apne_oppdrag': 1,
         'ressursbehov': [{'id': 1, 'navn': 'Ambulanse'}], 'deltakere': ['kari']}

    def test_viktig_har_ramme_og_utropstegn(self):
        ut = self._rad(self.H)
        self.assertIn('h-viktig', ut)
        self.assertIn('bi-exclamation-triangle-fill', ut)
        self.assertIn('>Viktig<', ut)

    def test_de_andre_har_klasse_og_merke_men_ikke_ikon(self):
        for prio, navn in (('rod', 'Rød'), ('gul', 'Gul'), ('gronn', 'Grønn'), ('drift', 'Drift')):
            with self.subTest(prio=prio):
                ut = self._rad(dict(self.H, prioritet=prio))
                self.assertIn(f'h-{prio}', ut)
                self.assertIn(f'>{navn}<', ut)
                self.assertNotIn('bi-exclamation-triangle-fill', ut)

    def test_lukket_er_merket(self):
        ut = self._rad(dict(self.H, status='lukket', lukket_at='2026-09-18T22:00:00'))
        self.assertIn('h-lukket', ut)
        self.assertIn('Lukket', ut)

    def test_oppdragene_paa_hendelsen_leses_fra_tavla(self):
        ut = self._rad(self.H, [{'id': 9, 'nummer': 47, 'hendelse_id': 5}, {'id': 10, 'nummer': 48, 'hendelse_id': 6}])
        self.assertIn('O47', ut)
        self.assertNotIn('O48', ut)

    def test_escaper_tittel_sted_melder_beskrivelse_og_behov(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._rad(dict(self.H, tittel=ond, lokasjon_navn=ond, melder=ond, beskrivelse=ond,
                            opprettet_av=ond, ressursbehov=[{'id': 1, 'navn': ond}]))
        self.assertNotIn('<img', ut)
        self.assertIn('&lt;img', ut)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class StroemmenTests(SimpleTestCase):
    """`koIStrommen()` avgjør hva loggstrømmen viser: kommentarer i en
    hendelse står i hendelsen, systemlinjene om hendelsen står i strømmen med
    H-merket, og «System»-bryteren demper de andre systemlinjene — aldri
    hendelseslinjene."""

    def setUp(self):
        self.harness = build_harness(HENDELSE_HARNESS)

    def _i(self, linje, vis_system=True):
        ut = run_node(self.harness,
                      f'console.log(koIStrommen({json.dumps(linje)}));',
                      preamble=PRIORITET_PREAMBLE + f'let koVisSystem = {"true" if vis_system else "false"};\n')
        return ut.splitlines()[0] == 'true'

    def test_kommentar_i_hendelse_staar_i_hendelsen(self):
        self.assertFalse(self._i({'kilde': 'operator', 'hendelse_id': 5, 'systemkode': ''}))
        self.assertTrue(self._i({'kilde': 'operator', 'hendelse_id': None, 'systemkode': ''}))

    def test_systemlinja_om_hendelsen_staar_i_stroemmen(self):
        self.assertTrue(self._i({'kilde': 'system', 'hendelse_id': 5, 'systemkode': 'hendelse_opprettet'}))
        self.assertTrue(self._i({'kilde': 'system', 'hendelse_id': 5, 'systemkode': 'oppdrag_knyttet'}))

    def test_system_av_demper_stemplene_men_ikke_hendelsene(self):
        self.assertFalse(self._i({'kilde': 'system', 'hendelse_id': None, 'systemkode': 'oppdrag_status'}, False))
        self.assertTrue(self._i({'kilde': 'system', 'hendelse_id': 5, 'systemkode': 'hendelse_lukket'}, False))
        self.assertTrue(self._i({'kilde': 'operator', 'hendelse_id': None, 'systemkode': ''}, False))


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class OppsettetTests(SimpleTestCase):
    """Rutenettet (ko-layout.js): rammen holder fire vinduer. `koGyldigOppsett`
    avviser alt som mangler et vindu, `koBytt` bytter to, og gulvet klemmer
    en skillelinje før et vindu er borte."""

    def setUp(self):
        self.harness = build_harness(((KO_JS, ('koKlemProsent', 'koGyldigOppsett', 'koStandardOppsett',
                                                'koBytt', 'koProsentAv')),))

    PRE = ("const KO_VINDUER = ['hendelser', 'logg', 'ressurser', 'oppdrag'];\n"
           "const KO_OPPSETT_STANDARD = { rader: [['hendelser', 'logg'], ['ressurser', 'oppdrag']], bredde: [56, 34], hoyde: 56 };\n"
           'const KO_MIN_PROSENT = 20;\n')

    def _kjor(self, kode):
        return run_node(self.harness, kode, preamble=self.PRE).splitlines()

    def test_gulvet_klemmer_begge_veier(self):
        ut = self._kjor('console.log([koKlemProsent(5), koKlemProsent(50), koKlemProsent(99), koKlemProsent("x")].join(","));')
        self.assertEqual(ut[0], '20,50,80,50')

    def test_et_oppsett_som_mangler_et_vindu_avvises(self):
        ut = self._kjor(
            "console.log(koGyldigOppsett({rader: [['hendelser','logg'],['ressurser','ressurser']]}));\n"
            "console.log(koGyldigOppsett({rader: [['hendelser','logg','ressurser'],['oppdrag']]}));\n"
            'console.log(koGyldigOppsett(null));\n'
            "console.log(JSON.stringify(koGyldigOppsett({rader: [['oppdrag','logg'],['ressurser','hendelser']], bredde: [5, 95], hoyde: 200})));\n")
        self.assertEqual(ut[:3], ['null', 'null', 'null'])
        self.assertEqual(json.loads(ut[3]),
                         {'rader': [['oppdrag', 'logg'], ['ressurser', 'hendelser']], 'bredde': [20, 80], 'hoyde': 80})

    def test_bytt_bytter_to_og_roerer_ikke_resten(self):
        ut = self._kjor(
            'const o = koStandardOppsett();\n'
            "const ny = koBytt(o, 'oppdrag', 'hendelser');\n"
            'console.log(JSON.stringify(ny.rader));\n'
            'console.log(JSON.stringify(o.rader));\n'
            "console.log(JSON.stringify(koBytt(o, 'oppdrag', 'oppdrag').rader));\n"
            "console.log(JSON.stringify(koBytt(o, 'oppdrag', 'ukjent').rader));\n")
        self.assertEqual(json.loads(ut[0]), [['oppdrag', 'logg'], ['ressurser', 'hendelser']])
        self.assertEqual(json.loads(ut[1]), [['hendelser', 'logg'], ['ressurser', 'oppdrag']], 'det gamle er urørt')
        self.assertEqual(json.loads(ut[2]), [['hendelser', 'logg'], ['ressurser', 'oppdrag']])
        self.assertEqual(json.loads(ut[3]), [['hendelser', 'logg'], ['ressurser', 'oppdrag']])

    def test_prosent_av_beholderen(self):
        ut = self._kjor('console.log([koProsentAv(500, 0, 1000), koProsentAv(10, 0, 1000), koProsentAv(0, 0, 0)].join(","));')
        self.assertEqual(ut[0], '50,20,50')


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
class TavlaSierFraTilKoTests(SimpleTestCase):
    """**Kallstedet, ikke bare regelen.** `renderOppdrag()` i
    `oppdrag-sentral-oppdrag.js` skal kalle `koEtterOppdragTegnet()` når den
    finnes — hendelsesloggen leser oppdragene fra tavla, og uten kallet står
    den med gamle tall. Testene over kaller reglene selv, og da kunne tavla
    slutte å si fra uten at noe ble rødt — regel 3 om mutanter i `CLAUDE.md`.
    Og raden bærer lagene og prioritetsikonet fra hendelsen."""

    def setUp(self):
        from patients.js_test_utils import OPPDRAG_SENTRAL_JS
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
            (OPPDRAG_SENTRAL_JS, ('renderOppdrag', '_oppdragRadHtml', '_sorterOppdrag',
                                  'oppdragsnr', 'hendelsesnr', 'hastegradKlasse',
                                  'tidSiden', '_grovMerke', '_enhetsmatrise',
                                  '_problemMedAntall', '_medAntall', 'venterForbiTerskel',
                                  'lydTerskler', '_manglerTrinn', '_manglerMinutter')),
        ))

    SNIPPET = (
        "const HASTEGRAD_REKKEFOLGE = ['Akutt', 'Haster', 'Vanlig', 'Drift'];\n"
        "const MANGLER_TRINN = [[15, 'alvorlig'], [5, 'varsel'], [0, 'ny']];\n"
        "let oppdragsliste = [{id: 7, nummer: 7, status: 'fremme', status_navn: 'Fremme',\n"
        "  enhet_navn: 'HGSD 56', lokasjon_navn: 'Scene', problemstilling: 'Fall',\n"
        "  hastegrad: 'Akutt', opprettet: '2026-08-28T20:00:00Z', fritekst: '',\n"
        "  hendelse_id: 1, hendelse_nummer: 1, hendelse_tittel: 'Brann',\n"
        "  hendelse_prioritet: 'viktig', hendelse_lagsressurser: '<b>Lag 1</b>, Lag 3', enheter: []}];\n"
        "globalThis.window = { MODUL_TILGANG: { ko: 'skriv_full' } };\n"
        'let kalt = 0;\n'
        'function koEtterOppdragTegnet() { kalt += 1; }\n'
        "const el = { innerHTML: '' };\n"
        "globalThis.document = { getElementById: (id) => id === 'oppdragsliste' ? el : null };\n"
        'renderOppdrag();\n'
        'console.log(kalt);\n'
        'console.log(JSON.stringify(el.innerHTML));\n'
        'oppdragsliste = [];\n'
        'renderOppdrag();\n'
        'console.log(kalt);\n'
    )

    def test_tavla_sier_fra_og_raden_baerer_hendelsen(self):
        linjer = run_node(self.harness, self.SNIPPET).splitlines()
        self.assertEqual(linjer[0], '1', 'tavla sa ikke fra til KO etter tegningen')
        rad = json.loads(linjer[1])
        self.assertIn('H1</span>', rad, 'raden bærer H1-merket')
        self.assertIn('bi-exclamation-triangle-fill', rad, 'Viktig-ikonet på merket')
        self.assertIn('Lag: &lt;b&gt;Lag 1&lt;/b&gt;, Lag 3', rad, 'lagene, escapet')
        self.assertNotIn('hendelse-hode', rad, 'ingen gruppering på tavla lenger')
        self.assertEqual(linjer[2], '2', 'også en tom tavle sier fra')


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
