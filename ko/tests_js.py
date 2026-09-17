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
    # Ressursbildet (pulje 3). Tavla viser mannskapsnavn og ressursnavn —
    # data ført av mennesker i vaktlista, altså nøyaktig det escapingen
    # finnes for.
    'koRessursHtml',
    'koRessursKnapper',
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
    # Ressursbildet
    'mannskap': 'liste bygget to linjer over; hvert navn escapet der',
    'kilde': 'markup fra en ternær; navnet escapet i den ene grenen',
    'venter': 'markup bygget to linjer over, tallet escapet der',
    's.klasse': 'Bootstrap-klasse fra KO_STATUSER, en konstant i fila — ikke '
                'data. Kommer den en dag fra serveren, skal denne raden bort',
    'g.ressurser': 'ferdig markup fra koRessursHtml, som skannes for seg',
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


# ════════════════════════════════════════════════════════════════════════════
# RESSURSBILDET (pulje 3)
# ════════════════════════════════════════════════════════════════════════════

RESSURS_PREAMBLE = (
    'const KO_STATUSER = ['
    '{verdi: "ledig", navn: "Ledig", klasse: "success"},'
    '{verdi: "opptatt", navn: "Opptatt", klasse: "warning"},'
    '{verdi: "pause", navn: "Pause", klasse: "info"},'
    '{verdi: "ute_av_drift", navn: "Ute av drift", klasse: "danger"}];\n'
)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class RessursreglerTests(SimpleTestCase):
    """De to funksjonene på tavla som **avgjør** noe.

    `CLAUDE.md` plasserer JS-regler på middels: regelen invertert, ett ledd i
    `&&` fjernet, kallstedet fjernet. Byggerne rundt dem er lett lag og dekkes
    av skanneren og escaping-prøven.
    """

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml',)),
        (KO_JS, ('koKanSkrive', 'koKanStyreRessurs', 'koStatusklasse',
                 'koBemanningstekst')),
    )

    def setUp(self):
        self.harness = build_harness(self.HARNESS)

    def _kall(self, uttrykk, nivaa='skriv_full'):
        return run_node(
            self.harness, f'console.log(JSON.stringify({uttrykk}));',
            preamble=f'const window = {{MODUL_TILGANG: {{ko: "{nivaa}"}}}};\n'
                     + RESSURS_PREAMBLE).splitlines()[0]

    def test_begge_ledd_maa_holde(self):
        """**Ett ledd i `&&` fjernet er hele feilen.** Tegner vi knapper på en
        koblet bil, avviser serveren dem — og en knapp som fører til en vegg er
        verre enn ingen knapp (`CLAUDE.md`)."""
        lag = '{fort_av_ko: true}'
        bil = '{fort_av_ko: false}'
        self.assertEqual(self._kall(f'koKanStyreRessurs({lag})'), 'true')
        self.assertEqual(self._kall(f'koKanStyreRessurs({bil})'), 'false',
                         'bilen melder selv og skal ikke ha knapper')
        self.assertEqual(self._kall(f'koKanStyreRessurs({lag})', nivaa='les'),
                         'false', 'les skal se tavla, ikke føre på den')

    def test_uten_ressurs_er_svaret_nei(self):
        for tomt in ('null', 'undefined'):
            with self.subTest(verdi=tomt):
                self.assertEqual(self._kall(f'koKanStyreRessurs({tomt})'), 'false')

    def test_ukjent_status_ser_aldri_ledig_ut(self):
        """Fargen bærer en påstand om hvem som kan sendes. En verdi vi ikke
        kjenner skal være grå, ikke grønn."""
        self.assertEqual(
            self._kall('koStatusklasse({fort_av_ko: true, status: "tull"})'),
            '"secondary"')
        self.assertEqual(
            self._kall('koStatusklasse({fort_av_ko: true, status: ""})'),
            '"secondary"')
        self.assertEqual(
            self._kall('koStatusklasse({fort_av_ko: true, status: "ledig"})'),
            '"success"')
        self.assertEqual(
            self._kall('koStatusklasse({fort_av_ko: true, status: "ute_av_drift"})'),
            '"danger"')

    def test_bilens_farge_kommer_fra_oppdragsstatusen(self):
        """Den andre kilden har sin egen verdimengde — `ledig` er den eneste
        som betyr «kan sendes»."""
        self.assertEqual(
            self._kall('koStatusklasse({fort_av_ko: false, status: "ledig"})'),
            '"success"')
        self.assertEqual(
            self._kall('koStatusklasse({fort_av_ko: false, status: "rykker_ut"})'),
            '"warning"')

    def test_ingen_paa_skift_er_ikke_null_av_null(self):
        """«0 av 0 møtt» leses som en bemanningssvikt. Ingen skift er noe
        annet, og skal si noe annet."""
        self.assertEqual(
            self._kall('koBemanningstekst({antall: 0, tilstede: 0})'),
            '"ingen på skift nå"')
        self.assertEqual(
            self._kall('koBemanningstekst({antall: 3, tilstede: 1})'),
            '"1 av 3 møtt"')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class RessursEscapingTests(SimpleTestCase):
    """Mannskapsnavn og ressursnavn er brukerdata ført i vaktlista."""

    HARNESS = (
        (PORTAL_UTILS_JS, ('escapeHtml',)),
        (KO_JS, ('koKanSkrive', 'koKanStyreRessurs', 'koStatusklasse',
                 'koBemanningstekst', 'koRessursKnapper', 'koRessursHtml')),
    )

    ONDSKAP = '<img src=x onerror=alert(1)>'

    def setUp(self):
        self.harness = build_harness(self.HARNESS)

    def _ressurs(self, **overstyr):
        base = {
            'id': 1, 'navn': 'Lag 3', 'korps': 'HGSD', 'fort_av_ko': True,
            'mannskap': [], 'antall': 0, 'tilstede': 0,
            'status': 'ledig', 'status_navn': 'Ledig',
            'status_satt_av': '', 'status_satt_at': None,
        }
        base.update(overstyr)
        return json.dumps(base)

    def _tegn(self, **overstyr):
        return run_node(
            self.harness,
            f'console.log(koRessursHtml({self._ressurs(**overstyr)}));',
            preamble='const window = {MODUL_TILGANG: {ko: "skriv_full"}};\n'
                     + RESSURS_PREAMBLE)

    def test_ressursnavnet_escapes(self):
        ut = self._tegn(navn=self.ONDSKAP)
        self.assertNotIn('<img', ut)
        self.assertIn('&lt;img', ut)

    def test_mannskapsnavnet_escapes(self):
        ut = self._tegn(mannskap=[{'navn': self.ONDSKAP, 'rolle': '',
                                   'tilstede': True}], antall=1, tilstede=1)
        self.assertNotIn('<img', ut)
        self.assertIn('&lt;img', ut)

    def test_den_som_satte_statusen_escapes(self):
        """Brukernavnet er data admin skriver, og det fryses på raden."""
        ut = self._tegn(status_satt_av=self.ONDSKAP)
        self.assertNotIn('<img', ut)
        self.assertIn('&lt;img', ut)

    def test_bilen_faar_ingen_knapper_gjennom_den_ekte_inngangen(self):
        """**Muter kallstedet, ikke bare funksjonen** (`CLAUDE.md`): testene
        over kaller `koKanStyreRessurs` direkte, og da kunne `koRessursHtml`
        sluttet å kalle den uten at noe ble rødt."""
        ut = self._tegn(fort_av_ko=False, status='rykker_ut',
                        status_navn='Rykker ut')
        self.assertNotIn('koSettRessursstatus', ut)
        self.assertIn('melder selv', ut)

    def test_laget_faar_knapper_gjennom_den_ekte_inngangen(self):
        ut = self._tegn(fort_av_ko=True)
        self.assertIn('koSettRessursstatus', ut)
        self.assertIn('ført av KO', ut)
