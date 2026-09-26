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
import unittest

from django.test import SimpleTestCase

from oppdrag.tests_runde_d import _konst
from patients.js_test_utils import (JS_DIR, KO_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, read_js, run_node)

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

# **Skanningen av byggerne står i `core/tests_js_konkatenering.py`** (26. sep.
# 2026, D3), for alle JS-filene og med byggerne utledet av kilden. Her sto en
# egen kopi med to lister: `KO_LOGG_BYGGERE`, som en ny bygger måtte føres inn
# i, og `KO_GJENNOMGATT` med 32 lokale variabelnavn — som regexen aldri kunne
# treffe, fordi den krevde et punktum. Oppførselsprøven under er det som dekker
# de lokale variablene.


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
    "['gronn','Grønn'],['drift','Drift'],['plassering','Plassering']], MODUL_TILGANG: { ko: 'skriv_full' } };\n"
    "let koHendelser = new Map(); let koApenHendelseId = null; let koVisLukkede = true; let koSok = '';\n"
    'let koLinjer = new Map(); let oppdragsliste = [];\n'
    # Loggfilteret (21. sep. 2026): `koLoggHodeTekst()` teller det filtrerte.
    "let koLoggfilter = 'alle';\n"
    # Skjerm 2 (24. sep. 2026): raden som er merket, er den skjerm 2 viser.
    'let koFolgerSett = 0; let koFolgerViser = null; let koHendelseKanal = null;\n'
    + _konst(KO_JS[1], 'KO_FOLGER_FRIST_MS')
)

HENDELSE_HARNESS = (
    (PORTAL_UTILS_JS, ('escapeHtml',)),
    (JS_DIR / 'oppdrag-kort.js', ('oppdragsnr', 'hendelsesnr', 'hastegradKlasse')),
    (KO_JS, ('koSorterHendelser', 'koHendelseTreffer', 'koSynligeHendelser', 'koApneHendelser',
             'koPrioriteter', 'koPrioritetNavn', 'koPrioritetRang', 'koPrioMerke', 'koPrioIkon',
             'koOppdragForHendelse', 'koHendelseRadHtml', 'koKlokke', 'koKanSkrive',
             'koIStrommen', 'koLinjeMerke', 'koHendelseLinjer', 'koOperatorlinjer',
             'koMerketHendelse', 'koFolgerTilstede', 'koErFolger')),
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

    def test_soeket_treffer_nummer_tittel_sted_melder_loggen_og_lag(self):
        h = {'id': 4, 'kode': 'H12', 'nummer': 12, 'tittel': 'Slagsmål', 'lokasjon_navn': 'Scene sør',
             'melder_typer': ['andre'], 'melder': 'kiosken', 'melder_tekst': 'Andre (kiosken)',
             'lag': [{'ressurs_id': 3, 'navn': 'Lag 3'}]}
        # Loggen i hendelsen søkes — men ikke systemlinjene, ikke fjernede
        # linjer, og ikke linjer i en annen hendelse.
        linjer = ("koLinjer = new Map([[1, {id: 1, rot: 1, hendelse_id: 4, kilde: 'operator', tekst: 'to personer'}],"
                  "[2, {id: 2, rot: 2, hendelse_id: 4, kilde: 'operator', tekst: 'én pågrepet'}],"
                  "[3, {id: 3, rot: 3, hendelse_id: 4, kilde: 'system', tekst: 'Hendelse opprettet'}],"
                  "[5, {id: 5, rot: 5, hendelse_id: 4, kilde: 'operator', tekst: 'kniv', fjernet: true}],"
                  "[6, {id: 6, rot: 6, hendelse_id: 9, kilde: 'operator', tekst: 'brann'}]]);\n")
        for sok, ventet in (('h12', True), ('12', True), ('slag', True), ('sør', True),
                            ('kiosk', True), ('andre', True), ('personer', True), ('pågrepet', True),
                            ('lag 3', True), ('', True), ('  ', True), ('brann', False),
                            ('opprettet', False), ('kniv', False)):
            with self.subTest(sok=sok):
                ut = run_node(self.harness,
                              linjer + f'console.log(koHendelseTreffer({json.dumps(h)}, {json.dumps(sok)}));',
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

    def _rad(self, h, oppdrag=None, linjer=None):
        rader = [dict({'id': i + 1, 'rot': i + 1, 'hendelse_id': 5, 'kilde': 'operator'}, **l)
                 for i, l in enumerate(linjer if linjer is not None
                                       else [{'tekst': 'Mann ca. 40', 'forfatter': 'kari'}])]
        return run_node(self.harness,
                        f'oppdragsliste = {json.dumps(oppdrag or [])};\n'
                        f'koLinjer = new Map({json.dumps([[l["id"], l] for l in rader])});\n'
                        f'console.log(koHendelseRadHtml({json.dumps(h)}));',
                        preamble=PRIORITET_PREAMBLE)

    H = {'id': 5, 'nummer': 14, 'kode': 'H14', 'tittel': 'Bevisstløs person', 'status': 'apen',
         'prioritet': 'viktig', 'lokasjon_navn': 'Hovedscene', 'melder_typer': ['egen'],
         'melder': '', 'melder_tekst': 'Egen ressurs',
         'opprettet_at': '2026-09-18T21:42:00',
         'opprettet_av': 'kari', 'lukket_at': '', 'apne_oppdrag': 1,
         'lag': [{'id': 1, 'ressurs_id': 7, 'navn': 'Lag 1', 'fra': '2026-09-18T21:42:00', 'av': 'kari'}],
         'deltakere': ['kari']}

    def test_viktig_har_ramme_og_utropstegn(self):
        ut = self._rad(self.H)
        self.assertIn('h-viktig', ut)
        self.assertIn('bi-exclamation-triangle-fill', ut)
        self.assertIn('>Viktig<', ut)

    def test_de_andre_har_klasse_og_merke_men_ikke_ikon(self):
        for prio, navn in (('rod', 'Rød'), ('gul', 'Gul'), ('gronn', 'Grønn'), ('drift', 'Drift'), ('plassering', 'Plassering')):
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

    def test_raden_baerer_siste_logglinje_melder_og_lag(self):
        ut = self._rad(self.H, linjer=[{'tekst': 'første'}, {'tekst': 'siste'},
                                       {'tekst': 'Lag 1 på', 'kilde': 'system'},
                                       {'tekst': 'feil', 'fjernet': True}])
        self.assertIn('siste', ut)
        self.assertNotIn('første', ut, 'bare den nyeste linja står under tittelen')
        self.assertNotIn('Lag 1 på', ut, 'systemlinjer og fjernede linjer teller ikke')
        self.assertNotIn('feil', ut)
        self.assertIn('Meldt av Egen ressurs', ut)
        self.assertIn('Lag 1', ut)

    def test_escaper_tittel_sted_melder_logglinje_og_lag(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._rad(dict(self.H, tittel=ond, lokasjon_navn=ond, melder_tekst=ond, opprettet_av=ond,
                            lag=[{'id': 1, 'ressurs_id': 7, 'navn': ond, 'fra': '', 'av': ''}]),
                       linjer=[{'tekst': ond}])
        self.assertNotIn('<img', ut)
        self.assertIn('&lt;img', ut)


#: Et DOM-stubb for vinduene: `getElementById` lager elementet første gang
#: det spørres etter, med `classList` og `innerHTML`, så synligheten lar seg
#: lese etterpå. Bare det `koTegnHendelser`, `koVisDetaljen`, `koTegnHSide` og
#: `koTegnDetalj` rører.
VINDU_DOM = """
    const elementer = new Map();
    function el(id) {
      if (!elementer.has(id)) {
        const e = { id, innerHTML: '', textContent: '', value: '', klasser: new Set(), scrollTop: 0, scrollHeight: 0,
                    addEventListener() {}, querySelector: () => null, querySelectorAll: () => [] };
        e.classList = { add: (k) => e.klasser.add(k), remove: (k) => e.klasser.delete(k),
                        contains: (k) => e.klasser.has(k), toggle: (k, v) => { v ? e.klasser.add(k) : e.klasser.delete(k); } };
        elementer.set(id, e);
      }
      return elementer.get(id);
    }
    globalThis.document = { getElementById: el, activeElement: null, querySelectorAll: () => [], title: '' };
    const skjult = (id) => el(id).klasser.has('d-none');
    let koEgetVinduAktivt = null;
    function koTegnRessurser() {}
    function withSubmitGuard() {}
    function koBevarFelter() { return () => {}; }
    const sendt = [];
    function kanal() { koHendelseKanal = { postMessage: (m) => sendt.push(m) }; }
"""

VINDU_HARNESS = HENDELSE_HARNESS + (
    (PORTAL_UTILS_JS, ('fmtMin',)),
    (KO_JS, ('koLoggfilterTreffer', 'koEgetVinduUrl',
             'koTegnHendelser', 'koVisDetaljen', 'koTegnHendelseTittel', 'koHendelseVinduTittel',
             'koLoggHodeTekst', 'koTegnLoggHode', 'koTegnDetalj', 'koTegnHSide', 'koHSideRadHtml',
             'koApneHendelse', 'koVelgHendelse', 'koFramHendelsesvinduet', 'koRullTilHendelsesvinduet',
             'koLukkDetalj', 'koHendelseIEgetVindu', 'koSkjerm2Tekst', 'koMeldTilstede',
             'koHendelseMelding', 'koHendelseKanalMottak',
             'koDetaljLinjeHtml', 'koHendelseOppdragHtml', 'koPrioKnapperHtml', 'koLagBrikkeHtml',
             'koLagVelgerHtml', 'koLagKandidater', 'koLagPaa', 'koMittBrukernavn', 'koSiden',
             'koRettFjernKnapper', 'koDelingKnapper', 'koDeltMerke', 'koErDelt', 'koLinjeTekst', 'koKanFjerne', 'koDeltEtikett')),
)


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class HendelsenIHendelsesvinduetTests(SimpleTestCase):
    """Hendelsen åpnes i **hendelsesloggens** vindu, med de pågående i en
    sidebar (André, 24. sep. 2026, skisse v2). Loggstrømmen viser aldri en
    hendelse («3. nei»). Finnes et hendelsesvindu for seg, går klikkene dit
    («når en trykker på en hendelse i hendelsesloggen så oppdateres den
    hendelses vinduet»)."""

    H5 = dict(HendelsesradenTests.H, id=5, nummer=5, kode='H5', tittel='Bevisstløs person')
    H6 = dict(HendelsesradenTests.H, id=6, nummer=6, kode='H6', tittel='Slagsmål', prioritet='rod')
    H7 = dict(HendelsesradenTests.H, id=7, nummer=7, kode='H7', tittel='Ferdig', status='lukket',
              lukket_at='2026-09-18T22:00:00')

    def _kjor(self, script, nivaa='skriv_full'):
        preamble = (PRIORITET_PREAMBLE.replace("ko: 'skriv_full'", f"ko: '{nivaa}'")
                    + _konst(KO_JS[0], 'KO_VINDUER'))
        ut = run_node(build_harness(VINDU_HARNESS), VINDU_DOM
                      + 'koHendelser = new Map('
                      + json.dumps([[5, self.H5], [6, self.H6], [7, self.H7]]) + ');\n'
                      + "koLinjer = new Map([[1, {id: 1, rot: 1, kilde: 'operator', hendelse_id: null, systemkode: ''}],"
                      + " [2, {id: 2, rot: 2, kilde: 'operator', hendelse_id: 5, systemkode: ''}]]);\n"
                      + script, preamble=preamble).splitlines()
        return ut[:-1] if ut and ut[-1] == 'OK' else ut

    def test_hendelsen_erstatter_tabellen_og_loggen_blir_staaende(self):
        ut = self._kjor("""
            koTegnHendelser();
            const logg = () => [skjult('ko-logg-liste'), skjult('ko-logg-skjema'), el('ko-logg-antall').textContent].join(' ');
            koTegnLoggHode();
            console.log(skjult('ko-hendelser-liste'), skjult('ko-hendelse-visning'), logg());
            koApneHendelse('5');
            console.log(skjult('ko-hendelser-liste'), skjult('ko-hendelse-visning'),
                        el('ko-vindu-hendelser').klasser.has('ko-h-detaljmodus'), logg());
            const d = el('ko-hendelse-detalj').innerHTML;
            console.log(d.includes('Bevisstløs person'), d.includes('data-action="koLukkDetalj"'),
                        d.includes('Alle hendelser'), d.includes('data-action="koHendelseIEgetVindu" data-id="5"'));
            koLukkDetalj();
            console.log(koApenHendelseId, skjult('ko-hendelser-liste'), skjult('ko-hendelse-visning'),
                        el('ko-vindu-hendelser').klasser.has('ko-h-detaljmodus'), logg());
            console.log(JSON.stringify(document.title));
        """)
        self.assertEqual(ut[0], 'false true false false · 1 linjer', 'før: tabellen')
        self.assertEqual(ut[1], 'true false true false false · 1 linjer',
                         'åpen: hendelsen i hendelsesvinduet — strømmen, feltet og hodet der er urørt')
        self.assertEqual(ut[2], 'true true true true')
        self.assertEqual(ut[3], 'null false true false false false · 1 linjer', 'tilbake til tabellen')
        self.assertEqual(ut[4], '""', 'hovedvinduets fanetittel er sidens, ikke hendelsens')

    def test_sidebaren_har_bare_de_paagaaende_i_tabellens_rekkefolge(self):
        ut = self._kjor("""
            koApneHendelse('5');
            const s = el('ko-hendelse-sidebar').innerHTML;
            console.log(JSON.stringify((s.match(/data-id="\\d+"/g) || [])));
            console.log((s.match(/ aktiv"/g) || []).length, s.includes('aria-current'), s.includes('data-action="koVelgHendelse"'));
        """)
        self.assertEqual(json.loads(ut[0]), ['data-id="5"', 'data-id="6"'], 'Viktig før Rød, og H7 (lukket) er ikke med')
        self.assertEqual(ut[1], '1 true true', 'nøyaktig én rad er den åpne')

    def test_sidebaren_bytter_paa_stedet(self):
        ut = self._kjor("""
            koApneHendelse('5');
            koVelgHendelse('6');
            console.log(koApenHendelseId, el('ko-hendelse-detalj').innerHTML.includes('Slagsmål'), skjult('ko-hendelser-liste'));
        """)
        self.assertEqual(ut[0], '6 true true')

    def test_lukket_av_en_annen_blir_staaende_merket_og_gaar_ut_av_sidebaren(self):
        """André: «Noen skal kanskje registrere noe etterpå.»"""
        ut = self._kjor("""
            koApneHendelse('6');
            koHendelser.set(6, Object.assign({}, koHendelser.get(6), {status: 'lukket', lukket_at: '2026-09-18T22:10:00', lukket_av: 'per'}));
            koTegnHendelser();
            console.log(koApenHendelseId, skjult('ko-hendelse-visning'),
                        el('ko-hendelse-detalj').innerHTML.includes('Lukket'),
                        el('ko-hendelse-detalj').innerHTML.includes('av per'),
                        el('ko-hendelse-sidebar').innerHTML.includes('data-id="6"'));
        """)
        self.assertEqual(ut[0], '6 false true true false')

    def test_hendelse_som_forsvinner_gir_tabellen_tilbake(self):
        """Pollen sender hele lista; er den åpne borte (nullstilt), står
        tabellen der igjen — ikke et tomt vindu."""
        ut = self._kjor("""
            koApneHendelse('5'); koHendelser.delete(5); koTegnHendelser();
            console.log(koApenHendelseId, skjult('ko-hendelse-visning'), skjult('ko-hendelser-liste'));
        """)
        self.assertEqual(ut[0], 'null true false')

    def test_skjult_hendelseslogg_hentes_fram(self):
        """«En hendelse åpnes i loggvinduet — også når det er skjult» (TODO):
        H-merket og lagkortet går gjennom `koApneHendelse`."""
        ut = self._kjor("""
            let koOppsett = {skjult: ['hendelser']}; const vist = [];
            function koErSkjult(o, navn) { return o.skjult.includes(navn); }
            function koVisVindu(navn) { vist.push(navn); koOppsett = {skjult: []}; }
            koApneHendelse('5'); koApneHendelse('6');
            console.log(JSON.stringify(vist), koApenHendelseId);
            koEgetVinduAktivt = 'hendelser'; koOppsett = {skjult: ['hendelser']};
            koApneHendelse('5');
            console.log(JSON.stringify(vist));
        """)
        self.assertEqual(ut[0], '["hendelser"] 6', 'hentet fram én gang, ikke ved hvert klikk')
        self.assertEqual(ut[1], '["hendelser"]', 'et vindu for seg har ingenting å hente fram')

    def test_rullingen_gjelder_bare_smal_skjerm(self):
        ut = self._kjor("""
            let rullet = 0; el('ko-vindu-hendelser').scrollIntoView = () => { rullet += 1; };
            window.matchMedia = (q) => ({ matches: q.includes('1199.98px') && globalThis.smal });
            globalThis.smal = false; koApneHendelse('5'); console.log(rullet);
            globalThis.smal = true; koApneHendelse('6'); console.log(rullet);
        """)
        self.assertEqual(ut[:2], ['0', '1'])

    def test_med_skjerm_2_gaar_klikket_dit_og_tabellen_staar(self):
        ut = self._kjor("""
            kanal(); koFolgerSett = Date.now(); koFolgerViser = null;
            koTegnHendelser();
            console.log(el('ko-hendelser-skjerm2').textContent);
            koApneHendelse('6');
            console.log(JSON.stringify(sendt), koApenHendelseId, skjult('ko-hendelser-liste'),
                        (el('ko-hendelser-liste').innerHTML.match(/h-apen/g) || []).length,
                        el('ko-hendelser-liste').innerHTML.includes('h-rod h-apen'),
                        el('ko-hendelser-skjerm2').textContent);
            // Livstegnet stopper: etter fristen åpner klikket seg her igjen.
            koFolgerSett = Date.now() - KO_FOLGER_FRIST_MS - 1;
            koApneHendelse('5');
            console.log(sendt.length, koApenHendelseId, el('ko-hendelser-skjerm2').textContent === '',
                        (el('ko-hendelser-liste').innerHTML.match(/h-apen/g) || []).length);
        """)
        self.assertEqual(ut[0], '· skjerm 2 følger')
        self.assertEqual(ut[1], '[{"vis":6}] null false 1 true · H6 vises på skjerm 2')
        self.assertEqual(ut[2], '1 5 true 0', 'skjerm 2 borte: klikket åpner her, og merket er borte')

    def test_eget_vindu_fra_hendelsen(self):
        ut = self._kjor("""
            const aapnet = []; let blokkert = false;
            window.open = (url, navn) => { aapnet.push([url, navn]); return blokkert ? null : {}; };
            koApneHendelse('5');
            koHendelseIEgetVindu('5');
            console.log(JSON.stringify(aapnet), koApenHendelseId, skjult('ko-hendelser-liste'),
                        el('ko-hendelser-liste').innerHTML.includes('h-viktig h-apen'));
            blokkert = true; koFolgerSett = 0;
            koApneHendelse('6'); koHendelseIEgetVindu('6');
            console.log(koApenHendelseId, skjult('ko-hendelser-liste'));
        """)
        self.assertEqual(json.loads(ut[0].split(' ')[0]), [['/ko/?vindu=hendelser&hendelse=5', 'ko-hendelser']])
        self.assertEqual(ut[0].split(' ', 1)[1], 'null false true', 'tabellen står, med raden merket')
        self.assertEqual(ut[1], '6 true', 'et blokkert vindu lar hendelsen bli stående her')

    def test_meldingene_leses_som_data(self):
        ut = self._kjor("""
            console.log(JSON.stringify([{sporr: true}, {borte: true}, {tilstede: true, viser: 5},
              {tilstede: true, viser: '5'}, {tilstede: true}, {vis: 7}, {vis: '7'}, {vis: 0}, {vis: -1},
              {vis: 1.5}, null, 'vis', {}].map(koHendelseMelding)));
        """)
        self.assertEqual(json.loads(ut[0]), [
            {'sporr': True}, {'borte': True}, {'tilstede': True, 'viser': 5},
            {'tilstede': True, 'viser': None}, {'tilstede': True, 'viser': None}, {'vis': 7},
            None, None, None, None, None, None, None])

    def test_hovedvinduet_folger_livstegnet(self):
        ut = self._kjor("""
            kanal();
            koHendelseKanalMottak({tilstede: true, viser: 5}, 1000);
            console.log(koFolgerSett, koFolgerViser);
            koHendelseKanalMottak({vis: 6}, 2000);
            console.log(koApenHendelseId, 'hovedvinduet tar ikke imot vis');
            koHendelseKanalMottak({borte: true}, 3000);
            console.log(koFolgerSett, koFolgerViser);
        """)
        self.assertEqual(ut, ['1000 5', 'null hovedvinduet tar ikke imot vis', '0 null'])

    def test_vinduet_for_seg_folger_klikkene_og_svarer(self):
        ut = self._kjor("""
            kanal(); koEgetVinduAktivt = 'hendelser';
            koHendelseKanalMottak({vis: 6});
            console.log(koApenHendelseId, skjult('ko-hendelse-visning'), document.title);
            koHendelseKanalMottak({sporr: true});
            koHendelseKanalMottak({tilstede: true, viser: 5});
            console.log(JSON.stringify(sendt), koFolgerSett);
            koLukkDetalj();
            console.log(JSON.stringify(sendt[sendt.length - 1]), document.title);
        """)
        self.assertEqual(ut[0], '6 false H6 · Slagsmål · KO')
        self.assertEqual(ut[1], '[{"tilstede":true,"viser":6},{"tilstede":true,"viser":6}] 0',
                         'svarer på vis og på spørsmålet; bryr seg ikke om andre vinduer for seg')
        self.assertEqual(ut[2], '{"tilstede":true,"viser":null} Hendelseslogg · KO')

    def test_sidebarraden_escaper_og_baerer_alle_fire(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._kjor('console.log(koHSideRadHtml(' + json.dumps(dict(
            self.H5, tittel=ond, lokasjon_navn=ond, opprettet_at='2026-09-18T21:00:00')) + ', '
            'new Date("2026-09-18T21:23:00").getTime()));')
        self.assertNotIn('<img', ut[0])
        for klasse in ('ko-hs-nr', 'ko-hs-tittel', 'ko-hs-sted', 'ko-hs-tid'):
            self.assertIn(klasse, ut[0])
        self.assertIn('>23 min<', ut[0])
        self.assertIn('h-viktig', ut[0])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class SidebarBreddenTests(SimpleTestCase):
    """`koHSideBredde()`: aldri smalere enn nummeret, aldri over 60 % av
    vinduet — hendelsen er det man jobber i."""

    def test_grensene(self):
        pre = _konst(KO_JS[1], 'KO_HSIDE_MIN')
        ut = run_node(build_harness(((KO_JS, ('koHSideBredde',)),)),
                      'console.log(JSON.stringify([koHSideBredde(10, 1000), koHSideBredde(200, 1000),'
                      ' koHSideBredde(900, 1000), koHSideBredde(200.4, 1000), koHSideBredde("x", 1000),'
                      ' koHSideBredde(200, 50)]));', preamble=pre).splitlines()
        self.assertEqual(json.loads(ut[0]), [56, 200, 600, 200, None, 56])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class HendelseKanalenStarterTests(SimpleTestCase):
    """Kallstedet i ko.js og det `koHendelseVinduStart()` gjør: vinduet for
    seg melder seg og pulserer, hovedvinduet spør."""

    def test_ko_js_starter_den_etter_oppsettet(self):
        """Den ekte kroken kjøres, med hvert navn den kaller byttet mot en
        opptaker (`with` over en Proxy). Rekkefølgen teller: `koErFolger()`
        leser `koEgetVinduAktivt`, som `koOppsettStart()` setter."""
        kilde = read_js(KO_JS)
        start = kilde.index("document.addEventListener('DOMContentLoaded', ")
        krok = kilde[start + len("document.addEventListener('DOMContentLoaded', "):kilde.rindex(');')]
        ut = run_node('', 'const kall = [];\n'
                      'const stub = new Proxy({}, { has: (t, k) => k !== "kall",'
                      ' get: (t, k) => k === "document" ? { getElementById: () => null }'
                      ' : (...a) => { kall.push(String(k)); return null; } });\n'
                      'new Function("stub", "with (stub) { (" + ' + json.dumps(krok) + ' + ")(); }")(stub);\n'
                      'console.log(JSON.stringify(kall.slice(0, 2)));').splitlines()
        self.assertEqual(json.loads(ut[0]), ['koOppsettStart', 'koHendelseVinduStart'])

    def _kjor(self, eget):
        pre = (_konst(KO_JS[1], 'KO_HENDELSE_KANAL') + _konst(KO_JS[1], 'KO_FOLGER_PULS_MS')
               + f"let koHendelseKanal = null; let koApenHendelseId = 4; let koEgetVinduAktivt = {json.dumps(eget)};\n"
               + """
            const sendt = []; const pulser = []; const lyttere = [];
            globalThis.BroadcastChannel = function (navn) { this.navn = navn; this.postMessage = (m) => sendt.push([navn, m]); };
            globalThis.setInterval = (f, ms) => pulser.push(ms);
            globalThis.window = { addEventListener: (h) => lyttere.push(h) };
            globalThis.document = { getElementById: () => null, addEventListener() {} };
            function koHSideLyttere() {}
            function koHendelseKanalMottak() {}
        """)
        ut = run_node(build_harness(((KO_JS, ('koHendelseVinduStart', 'koErFolger', 'koMeldTilstede')),)),
                      'koHendelseVinduStart(); console.log(JSON.stringify([sendt, pulser, lyttere]));',
                      preamble=pre).splitlines()
        return json.loads(ut[0])

    def test_vinduet_for_seg_melder_seg_pulserer_og_sier_fra_ved_lukking(self):
        self.assertEqual(self._kjor('hendelser'),
                         [[['ko-hendelse', {'tilstede': True, 'viser': 4}]], [5000], ['pagehide']])

    def test_hovedvinduet_spor(self):
        self.assertEqual(self._kjor(None), [[['ko-hendelse', {'sporr': True}]], [], []])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class StroemmenTests(SimpleTestCase):
    """`koIStrommen()` avgjør hva loggstrømmen viser: kommentarer i en
    hendelse står i hendelsen, systemlinjene om hendelsen står i strømmen med
    H-merket — og oppdragenes stempler står **ikke** der (André, 19. sep.
    2026: «statuser fra oppdrag fjernes fra loggstrøm og med det system
    knappen»)."""

    def setUp(self):
        self.harness = build_harness(HENDELSE_HARNESS)

    def _i(self, linje):
        ut = run_node(self.harness,
                      f'console.log(koIStrommen({json.dumps(linje)}));',
                      preamble=PRIORITET_PREAMBLE)
        return ut.splitlines()[0] == 'true'

    def test_kommentar_i_hendelse_staar_i_hendelsen(self):
        self.assertFalse(self._i({'kilde': 'operator', 'hendelse_id': 5, 'systemkode': ''}))
        self.assertTrue(self._i({'kilde': 'operator', 'hendelse_id': None, 'systemkode': ''}))

    def test_systemlinja_om_hendelsen_staar_i_stroemmen(self):
        self.assertTrue(self._i({'kilde': 'system', 'hendelse_id': 5, 'systemkode': 'hendelse_opprettet'}))
        self.assertTrue(self._i({'kilde': 'system', 'hendelse_id': 5, 'systemkode': 'oppdrag_knyttet'}))

    def test_oppdragenes_stempler_staar_aldri_i_stroemmen(self):
        for kode in ('oppdrag_status', 'oppdrag_opprettet', 'enhet_varslet', 'enhet_avbrot', 'vaktmodus'):
            with self.subTest(kode=kode):
                self.assertFalse(self._i({'kilde': 'system', 'hendelse_id': None, 'systemkode': kode}))
                self.assertFalse(self._i({'kilde': 'system', 'hendelse_id': 5, 'systemkode': kode}),
                                 'heller ikke når oppdraget hører til en hendelse')
        self.assertTrue(self._i({'kilde': 'system', 'hendelse_id': 5, 'systemkode': 'hendelse_lag_paa'}))
        self.assertTrue(self._i({'kilde': 'operator', 'hendelse_id': None, 'systemkode': ''}))


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class LoggfilteretTests(SimpleTestCase):
    """Alle | Meldinger | System i loggstrømmen (André, 21. sep. 2026:
    «loggstrømmen må filtreres mellom system meldinger og bruker sendte
    meldinger»). Valget huskes per nettleser, som Alle | Biler | Lag."""

    def _kjor(self, kode, forspill=''):
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koLoggfilterTreffer', 'koLesLoggfilter', 'koLagreLoggfilter',
                     'koVelgLoggfilter', 'koMerkLoggfilter', 'koStartLoggfilter',
                     'koLoggTomMelding')),
        ))
        pre = ("const KO_LOGGFILTER_NOKKEL = 'ko.loggfilter';\n"
               "const KO_LOGGFILTRE = ['alle', 'meldinger', 'system'];\n"
               "let koLoggfilter = 'alle';\n"
               'function koTegnLogg() { globalThis.tegnet = (globalThis.tegnet || 0) + 1; }\n')
        return run_node(harness, forspill + kode, preamble=pre).splitlines()

    def test_regelen_skiller_system_fra_meldinger(self):
        ut = self._kjor("""
            const sys = {kilde: 'system'}, folk = {kilde: 'operator'};
            console.log(koLoggfilterTreffer(sys, 'alle'), koLoggfilterTreffer(folk, 'alle'));
            console.log(koLoggfilterTreffer(sys, 'system'), koLoggfilterTreffer(folk, 'system'));
            console.log(koLoggfilterTreffer(sys, 'meldinger'), koLoggfilterTreffer(folk, 'meldinger'));
        """)
        self.assertEqual(ut[:3], ['true true', 'true false', 'false true'])

    def test_valget_huskes_og_et_ukjent_valg_gjor_ingenting(self):
        ut = self._kjor("""
            koVelgLoggfilter('system');
            console.log(koLoggfilter, lager[KO_LOGGFILTER_NOKKEL], globalThis.tegnet);
            koVelgLoggfilter('tull');
            console.log(koLoggfilter, globalThis.tegnet, 'ukjent valg tegner ikke på nytt');
            koLoggfilter = 'alle';
            koStartLoggfilter();
            console.log(koLoggfilter, 'lest tilbake');
            // Lagret verdi er brukerdata fra en annen versjon av sida, som
            // oppsettet: et navn vi ikke kjenner skal gi «alle», ikke et
            // filter som slipper gjennom ingenting.
            lager[KO_LOGGFILTER_NOKKEL] = 'bare_viktige';
            koStartLoggfilter();
            console.log(koLoggfilter, 'ukjent lagret verdi');
            lager[KO_LOGGFILTER_NOKKEL] = '';
            koStartLoggfilter();
            console.log(koLoggfilter, 'tom lagret verdi');
        """, forspill="""
            const lager = {};
            globalThis.window = { localStorage: { getItem: (k) => lager[k] ?? null,
                                                  setItem: (k, v) => { lager[k] = v; } } };
            globalThis.document = { getElementById: () => null };
        """)
        self.assertEqual(ut[0], 'system system 1')
        self.assertEqual(ut[1], 'system 1 ukjent valg tegner ikke på nytt')
        self.assertEqual(ut[2], 'system lest tilbake')
        self.assertEqual(ut[3], 'alle ukjent lagret verdi')
        self.assertEqual(ut[4], 'alle tom lagret verdi')

    def test_en_privat_fane_faller_tilbake_paa_alle(self):
        """localStorage kaster i en privat fane. Filteret skal da gjelde til
        sida lastes på nytt, ikke ta ned strømmen."""
        ut = self._kjor("""
            console.log(koLesLoggfilter());
            koLagreLoggfilter('system');
            koVelgLoggfilter('meldinger');
            console.log(koLoggfilter, 'valget virker likevel');
        """, forspill="""
            globalThis.window = { localStorage: { getItem() { throw new Error('privat'); },
                                                  setItem() { throw new Error('privat'); } } };
            globalThis.document = { getElementById: () => null };
        """)
        self.assertEqual(ut[0], 'alle')
        self.assertEqual(ut[1], 'meldinger valget virker likevel')

    def test_knappene_merkes_med_det_som_gjelder(self):
        ut = self._kjor("""
            koVelgLoggfilter('meldinger');
            console.log(knapper.map((k) => k.dataset.arg + '=' + k.klasser.has('active') + '/' + k.attr['aria-pressed']).join(' '));
        """, forspill="""
            const lager = {};
            globalThis.window = { localStorage: { getItem: (k) => lager[k] ?? null, setItem: (k, v) => { lager[k] = v; } } };
            const knapper = ['alle', 'meldinger', 'system'].map((arg) => {
              const k = { dataset: { arg }, klasser: new Set(), attr: {} };
              k.classList = { toggle: (c, v) => { v ? k.klasser.add(c) : k.klasser.delete(c); } };
              k.setAttribute = (n, v) => { k.attr[n] = v; };
              return k;
            });
            const boks = { querySelectorAll: () => knapper, classList: { toggle() {} } };
            globalThis.document = { getElementById: (id) => (id === 'ko-loggfilter' ? boks : null) };
        """)
        self.assertEqual(ut[0], 'alle=false/false meldinger=true/true system=false/false')

    def test_tom_stroem_sier_om_det_er_filteret(self):
        """Samme regel som `koOppdragTomMelding()`: teksten skal si om lista
        er tom fordi filteret tok alt, eller fordi det ikke står noe der."""
        ut = self._kjor("""
            koLoggfilter = 'system'; console.log(koLoggTomMelding(true));
            koLoggfilter = 'meldinger'; console.log(koLoggTomMelding(true));
            koLoggfilter = 'alle'; console.log(koLoggTomMelding(true));
            koLoggfilter = 'system'; console.log(koLoggTomMelding(false));
        """, forspill='globalThis.document = { getElementById: () => null };')
        self.assertEqual(ut[0], 'Ingen systemlinjer i strømmen.')
        self.assertEqual(ut[1], 'Ingen meldinger i strømmen.')
        self.assertEqual(ut[2], 'Ingen linjer ennå.')
        self.assertEqual(ut[3], 'Ingen linjer ennå.', 'tom strøm er ikke filterets skyld')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class DelingOgLagTests(SimpleTestCase):
    """Deling av logglinjer med enhetene og lagene på hendelsen (19. sep.
    2026): «Delt»-merket og Del/Angre etter nivå, «Fra loggen i H14» i
    oppdragets detaljmodal, «siden»-teksten — og at tekst, navn og lagnavn escapes."""

    DELING = ('koErDelt', 'koDeltEtikett', 'koDeltMerke', 'koDelingKnapper', 'koRettFjernKnapper',
              'koKlokke', 'koKanSkrive', 'koKanFjerne', 'koDetaljLinjeHtml')

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'fmtMin')),
            (OPPDRAG_KORT_JS, ('oppdragsnr',)),
            (KO_JS, self.DELING + ('koSiden', 'koLagBrikkeHtml', 'koDelteLinjerHtml',
                                   'koHendelseLinjer', 'koOperatorlinjer')),
        ))

    PRE = ("globalThis.window = { MODUL_TILGANG: { ko: 'skriv_full' } };\n"
           "let koLinjer = new Map(); let koHendelser = new Map(); let oppdragsliste = [];\n")

    #: Et rutenett av stubber: de to radene med hver sin skillelinje, de fire
    #: vinduene, den vannrette skillelinja og stripa. `skjult` leses av
    #: `d-none`, som er det `koTegnOppsett` faktisk setter.
    DOM = """
        function lagEl(id) {
          const e = { id, innerHTML: '', style: {}, klasser: new Set(), barn: [] };
          e.classList = { add: (k) => e.klasser.add(k), remove: (k) => e.klasser.delete(k),
                          contains: (k) => e.klasser.has(k),
                          toggle: (k, v) => { v ? e.klasser.add(k) : e.klasser.delete(k); } };
          Object.defineProperty(e, 'skjult', { get: () => e.klasser.has('d-none') });
          e.insertBefore = () => {}; e.appendChild = () => {};
          return e;
        }
        const rad1Splitter = lagEl('splitter-1');
        const rad2Splitter = lagEl('splitter-2');
        const vannrett = lagEl('splitter-h');
        const elementer = new Map();
        for (const id of ['ko-rad-1', 'ko-rad-2', 'ko-skjulte', 'ko-vindu-hendelser',
                          'ko-vindu-logg', 'ko-vindu-ressurser', 'ko-vindu-oppdrag',
                          'ko-vindu-tavle']) {
          elementer.set(id, lagEl(id));
        }
        elementer.get('ko-rad-1').querySelector = () => rad1Splitter;
        elementer.get('ko-rad-2').querySelector = () => rad2Splitter;
        const el = (id) => elementer.get(id);
        globalThis.document = {
          getElementById: (id) => elementer.get(id) || null,
          querySelector: (v) => (v === '.ko-splitter-h' ? vannrett
            : elementer.get('ko-vindu-' + (v.match(/data-vindu="(\\w+)"/) || [])[1]) || null),
          querySelectorAll: () => [],
        };
    """

    def _kjor(self, kode):
        return run_node(self.harness, kode, preamble=self.PRE).splitlines()

    def test_siden_i_minutter_og_timer(self):
        ut = self._kjor(
            "const naa = Date.parse('2026-09-19T22:00:00Z');\n"
            "console.log([koSiden('2026-09-19T21:37:00Z', naa), koSiden('2026-09-19T20:55:00Z', naa),"
            " koSiden('2026-09-19T22:30:00Z', naa), koSiden('x', naa)].join('|'));")
        self.assertEqual(ut[0], '23 min|1t 5m|0 min|')

    def test_delt_etiketten_sier_alle_eller_hvilke(self):
        ut = self._kjor(
            "oppdragsliste = [{id: 9, nummer: 47}, {id: 10, nummer: 48}];\n"
            "console.log(JSON.stringify([koDeltEtikett({delt_at: '2026-09-19T10:00:00Z', delt_med: [9]}),"
            " koDeltEtikett({delt_at: null, delt_med: [9, 10]}), koDeltEtikett({delt_at: null, delt_med: [11]}),"
            " koDeltEtikett({delt_at: null, delt_med: []}), koDeltEtikett({})]));\n"
            "console.log(JSON.stringify([koErDelt({delt_at: 'x'}), koErDelt({delt_med: [1]}), koErDelt({delt_med: []}), koErDelt({})]));")
        self.assertEqual(ut[0], '["Delt","Delt · O47, O48","Delt · #11","",""]')
        self.assertEqual(ut[1], '[true,true,false,false]')

    def test_linja_i_hendelsen_baerer_merke_og_knapper_etter_nivaa(self):
        """Del for `skriv_full` (samme nivå som å skrive), Angre når den er
        delt, rediger for `skriv_full`, fjern for `skriv_leder`; ingenting
        for `les`. Systemlinjer og fjernede linjer får ingen av delene."""
        def kjor(nivaa):
            return run_node(self.harness, self.PRE + f"globalThis.window = {{ MODUL_TILGANG: {{ ko: '{nivaa}' }} }};\n"
                "console.log(koDetaljLinjeHtml({id: 42, kilde: 'operator', tekst: 'k', forfatter: 'kari', delt_at: null, delt_med: []}));\n"
                "console.log(koDetaljLinjeHtml({id: 43, kilde: 'operator', tekst: 'd', forfatter: 'kari', delt_at: '2026-09-19T10:00:00Z', delt_av: 'ola', delt_med: []}));\n"
                "console.log(koDetaljLinjeHtml({id: 44, kilde: 'system', tekst: 'H3 lukket'}));\n"
                "console.log(koDetaljLinjeHtml({id: 45, kilde: 'operator', fjernet: true, delt_at: '2026-09-19T10:00:00Z'}));\n").splitlines()
        les, skriv, leder = kjor('les'), kjor('skriv_full'), kjor('skriv_leder')
        self.assertNotIn('data-action', les[0]); self.assertNotIn('data-action', les[1])
        self.assertIn('>Delt</span>', les[1], 'merket vises for alle')
        self.assertIn('data-action="koDelLinje" data-id="42"', skriv[0])
        self.assertIn('data-action="koRett" data-id="42"', skriv[0]); self.assertNotIn('koFjern', skriv[0])
        self.assertNotIn('class="badge delt"', skriv[0], 'intern linje har ikke merket')
        self.assertIn('data-action="koAngreDeling" data-id="43"', skriv[1])
        self.assertNotIn('koDelLinje', skriv[1])
        self.assertIn('title="Delt av ola"', skriv[1]); self.assertIn(' delt">', skriv[1])
        self.assertIn('data-action="koFjern" data-id="42"', leder[0])
        for linje in (skriv[2], skriv[3]):
            self.assertNotIn('data-action', linje, 'systemlinjer og fjernede: ingen verktøy')
            self.assertNotIn('badge delt', linje)

    def test_fra_loggen_i_oppdraget_uten_merker_med_del_og_angre(self):
        """Bilde 3 er fasit (André, 19. sep. 2026): ingen grønne merker på
        tekstene. Delt med alle: «alle». Delt med dette: «Angre». Intern:
        «Del med <enhet>», dempet."""
        kode = """
            koHendelser = new Map([[5, {id: 5, kode: 'H14'}]]);
            koLinjer = new Map([
              [1, {id: 1, rot: 1, hendelse_id: 5, kilde: 'operator', tekst: 'Mann ca. 40', forfatter: 'kari', tidspunkt: '2026-09-19T10:00:00Z', delt_at: '2026-09-19T10:01:00Z', delt_med: []}],
              [2, {id: 2, rot: 2, hendelse_id: 5, kilde: 'operator', tekst: 'Bare dere', forfatter: 'kari', tidspunkt: '2026-09-19T10:02:00Z', delt_at: null, delt_med: [9]}],
              [3, {id: 3, rot: 3, hendelse_id: 5, kilde: 'operator', tekst: 'Intern <b>note</b>', forfatter: 'ola', tidspunkt: '2026-09-19T10:03:00Z', delt_at: null, delt_med: [10]}],
              [4, {id: 4, rot: 4, hendelse_id: 5, kilde: 'system', tekst: 'Lag 1 på'}],
            ]);
            console.log(koDelteLinjerHtml({id: 9, hendelse_id: 5, enhet_navn: 'Mannskapsbil <2>'}));
            console.log(JSON.stringify(koDelteLinjerHtml({id: 9, hendelse_id: 7})));
            globalThis.window = { MODUL_TILGANG: { ko: 'les' } };
            console.log(koDelteLinjerHtml({id: 9, hendelse_id: 5, enhet_navn: 'Mannskapsbil 2'}));
        """
        ut = self._kjor(kode)
        self.assertIn('Fra loggen i <span class="hendelse-merke">H14</span>', ut[0])
        self.assertNotIn('badge', ut[0], 'ingen merker på tekstene i oppdraget')
        self.assertNotIn('Lag 1 på', ut[0], 'systemlinjer står ikke der')
        self.assertIn('<span class="hvem">alle</span>', ut[0])
        self.assertIn('data-action="koAngreDelingMedOppdrag" data-id="2" data-arg="9"', ut[0])
        self.assertIn('data-action="koDelMedOppdrag" data-id="3" data-arg="9"', ut[0])
        self.assertIn('Del med Mannskapsbil &lt;2&gt;', ut[0])
        self.assertIn('b-tillegg intern">Intern &lt;b&gt;note', ut[0], 'delt med et annet oppdrag er intern her')
        self.assertNotIn('<b>note', ut[0])
        self.assertEqual(ut[1], '""', 'ukjent hendelse: ingenting')
        self.assertNotIn('data-action', ut[2], 'den som bare leser får ingen knapper')
        self.assertIn('Mann ca. 40', ut[2])

    def test_hendelsene_tegner_lagkortene_paa_nytt(self):
        """**Kallstedet, ikke bare regelen.** «På H14 · 23 min» leses av
        kortet fra hendelsene, så `koTaImotHendelser()` må tegne kortene om
        igjen — ellers står et lag som ledig til neste ressurs-poll."""
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koTaImotHendelser', 'koTegnHendelser', 'koFyllHendelsevalg',
                     'koSorterHendelser', 'koSynligeHendelser', 'koApneHendelser',
                     'koHendelseTreffer', 'koPrioriteter', 'koPrioritetRang')),
        ))
        ut = run_node(harness,
                      'let kalt = 0; function koTegnRessurser() { kalt += 1; }\n'
                      "globalThis.document = { getElementById: () => null, querySelectorAll: () => [] };\n"
                      "koTaImotHendelser([{id: 1, status: 'apen'}]);\n"
                      'console.log(kalt);', preamble=PRIORITET_PREAMBLE)
        self.assertEqual(ut.splitlines()[0], '1')

    def test_pollen_setter_delingstilstanden_paa_alle_linjene(self):
        """`delte` er hele lista: det som står der er delt, resten er intern
        — også en linje som *var* delt og ikke står der lenger."""
        harness = build_harness(((KO_JS, ('koTaImotDelte',)),))
        ut = run_node(harness, """
            let koLinjer = new Map([[1, {id: 1, delt_at: '2026-09-19T10:00:00Z', delt_av: 'kari', delt_med: []}],
                                    [2, {id: 2, delt_at: null, delt_med: []}], [3, {id: 3}]]);
            koTaImotDelte([{id: 2, delt_at: null, delt_av: '', delt_med: [9]}, {id: 3, delt_at: '2026-09-19T11:00:00Z', delt_av: 'ola', delt_med: []}]);
            console.log(JSON.stringify([...koLinjer.values()]));
        """).splitlines()[0]
        self.assertEqual(json.loads(ut), [
            {'id': 1, 'delt_at': None, 'delt_av': '', 'delt_med': []},
            {'id': 2, 'delt_at': None, 'delt_av': '', 'delt_med': [9]},
            {'id': 3, 'delt_at': '2026-09-19T11:00:00Z', 'delt_av': 'ola', 'delt_med': []},
        ])

    def test_kolonnene_huskes_og_settes_paa_vinduet(self):
        """Én eller to kolonner (André, 19. sep. 2026), huskes per nettleser."""
        harness = build_harness(((KO_JS, ('koLesKolonner', 'koLagreKolonner', 'koBrukKolonner', 'koVippKolonner')),))
        ut = run_node(harness, '''
            const KO_KOLONNER_NOKKEL = 'ko.ressurskolonner';
            const lager = {};
            globalThis.window = { localStorage: { getItem: (k) => lager[k] ?? null, setItem: (k, v) => { lager[k] = v; } } };
            const kropp = { klasser: new Set(), classList: { toggle(k, v) { v ? kropp.klasser.add(k) : kropp.klasser.delete(k); } } };
            const knapp = { klasser: new Set(), attr: {}, classList: { toggle(k, v) { v ? knapp.klasser.add(k) : knapp.klasser.delete(k); } }, setAttribute(n, v) { this.attr[n] = v; } };
            globalThis.document = { querySelector: () => kropp, getElementById: (id) => id === 'ko-kolonner-knapp' ? knapp : null };
            koBrukKolonner(); console.log(koLesKolonner(), kropp.klasser.has('ko-to-kolonner'));
            koVippKolonner(); console.log(koLesKolonner(), kropp.klasser.has('ko-to-kolonner'), knapp.attr['aria-pressed'], lager[KO_KOLONNER_NOKKEL]);
            koVippKolonner(); console.log(koLesKolonner(), kropp.klasser.has('ko-to-kolonner'));
        ''').splitlines()
        self.assertEqual(ut[:3], ['1 false', '2 true true 2', '1 false'])

    def test_telling_og_de_to_filtrene(self):
        """Uten ressurs, tildelt, ferdig — og ferdige i historikken teller med
        (André, 21. sep. 2026: «vises ikke som ferdig i tallstatistikken»)."""
        harness = build_harness(((KO_JS, ('koOppdragTelling', 'koOppdragFilter', 'koVippFilter',
                                          'koOppdragTomMelding')),))
        ut = run_node(harness, '''
            let koOppdragFilterValg = null;
            const liste = [{ id: 1, status: 'venter', trenger_ressurs: true }, { id: 2, status: 'fremme', trenger_ressurs: false },
                           { id: 3, status: 'ledig', trenger_ressurs: false }, { id: 4, status: 'venter', trenger_ressurs: false }];
            console.log(JSON.stringify(koOppdragTelling(liste)));
            console.log(JSON.stringify(koOppdragTelling(liste, 5)));
            console.log(koOppdragFilter(liste).length, koOppdragTomMelding());
            let tegnet = 0; globalThis.renderOppdrag = () => { tegnet += 1; };
            koVippFilter('uten_ressurs'); console.log(koOppdragFilterValg, tegnet, JSON.stringify(koOppdragFilter(liste).map((o) => o.id)), koOppdragTomMelding());
            koVippFilter('tildelt'); console.log(koOppdragFilterValg, JSON.stringify(koOppdragFilter(liste).map((o) => o.id)), koOppdragTomMelding());
            koVippFilter('tildelt'); console.log(koOppdragFilterValg, koOppdragFilter(liste).length);
        ''').splitlines()
        self.assertEqual(ut[:6], [
            '{"aktive":2,"uten_ressurs":1,"tildelt":1,"ferdig":1}',
            '{"aktive":2,"uten_ressurs":1,"tildelt":1,"ferdig":6}',
            '4 Ingen oppdrag på tavla.',
            'uten_ressurs 1 [1] Ingen oppdrag uten ressurs.',
            'tildelt [4] Ingen tildelte oppdrag som venter.',
            'null 4'])

    def test_hendelsevalget_bygges_ikke_om_under_operatoren(self):
        """Nedtrekket «Hendelse» fylles ved hver poll; står fokus i det, eller
        er lista uendret, røres det ikke (19. sep. 2026)."""
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koFyllHendelsevalg', 'koApneHendelser', 'koSorterHendelser', 'koPrioritetRang', 'koPrioriteter')),
        ))
        ut = run_node(harness, PRIORITET_PREAMBLE + '''
            let skrevet = 0; let kalt = 0;
            globalThis.koHendelsevalgEndret = () => { kalt += 1; };
            const sel = { _html: '', value: '' };
            Object.defineProperty(sel, 'innerHTML', { get() { return this._html; }, set(v) { this._html = v; skrevet += 1; } });
            let aktiv = null;
            globalThis.document = { getElementById: (id) => id === 'nytt-hendelse' ? sel : null, get activeElement() { return aktiv; } };
            koHendelser = new Map([[5, { id: 5, kode: 'H5', tittel: 'A', status: 'apen', prioritet: 'gul' }]]);
            koFyllHendelsevalg(); koFyllHendelsevalg(); console.log(skrevet, kalt);
            aktiv = sel; koHendelser.set(6, { id: 6, kode: 'H6', tittel: 'B', status: 'apen', prioritet: 'gul' });
            koFyllHendelsevalg(); console.log(skrevet, sel.innerHTML.includes('H6'));
            aktiv = null; koFyllHendelsevalg(); console.log(skrevet, sel.innerHTML.includes('H6'));
        ''').splitlines()
        self.assertEqual(ut[:3], ['1 2', '1 false', '2 true'])

    def test_fargeforklaringen_folder_ut_og_huskes(self):
        """«i» i ressursoversiktens hode (André, 19. sep. 2026, variant E1):
        av som standard, huskes per nettleser, og markupen tegnes først når
        den vises. Alle prikkene er med, «Tildelt» inkludert."""
        harness = build_harness(((KO_JS, ('koLesLegende', 'koLagreLegende', 'koLegendeHtml',
                                          'koTegnLegende', 'koVippLegende')),))
        ut = run_node(harness, '''
            const KO_LEGENDE_NOKKEL = 'ko.legende';
            const lager = {};
            globalThis.window = { localStorage: { getItem: (k) => lager[k] ?? null, setItem: (k, v) => { lager[k] = v; } } };
            const boks = { innerHTML: '', klasser: new Set(['d-none']), classList: { toggle(k, v) { v ? boks.klasser.add(k) : boks.klasser.delete(k); } } };
            const knapp = { klasser: new Set(), attr: {}, classList: { toggle(k, v) { v ? knapp.klasser.add(k) : knapp.klasser.delete(k); } }, setAttribute(n, v) { this.attr[n] = v; } };
            globalThis.document = { getElementById: (id) => ({ 'ko-legende': boks, 'ko-legende-knapp': knapp })[id] || null };
            koTegnLegende(); console.log(boks.klasser.has('d-none'), boks.innerHTML === '', knapp.attr['aria-expanded']);
            koVippLegende(); console.log(boks.klasser.has('d-none'), boks.innerHTML.includes('status-tildelt'), knapp.klasser.has('aktiv'), lager[KO_LEGENDE_NOKKEL]);
            koVippLegende(); console.log(boks.klasser.has('d-none'), koLesLegende());
            globalThis.window.localStorage = { getItem() { throw new Error('privat'); }, setItem() { throw new Error('privat'); } };
            koVippLegende(); console.log(koLesLegende());
            const html = koLegendeHtml();
            console.log(['ledig','tildelt','rykker_ut','fremme','behandlet','avreist','leverer','av_vakt'].every((s) => html.includes('status-' + s)), html.includes('Trenger ressurs'), html.includes('passiv vakt'));
        ''').splitlines()
        self.assertEqual(ut[:5], ['true true false', 'false true true ja', 'true false', 'false', 'true true true'])

    def _oppdragsrad(self, o):
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'fmtMin')),
            (OPPDRAG_KORT_JS, ('oppdragsnr', 'hastegradKlasse', 'tidSiden')),
            (KO_JS, ('koHendelseOppdragHtml', 'koHendelseOppdragEnheterHtml')),
        ))
        return run_node(harness, f'console.log(koHendelseOppdragHtml({o}));').splitlines()[0]

    def test_oppdraget_i_hendelsen_viser_trenger_ressurs(self):
        """Opprettet uten enhet (19. sep. 2026): samme merke som på tavla."""
        ut = self._oppdragsrad(
            "{id: 1, nummer: 49, hastegrad: 'Haster', problemstilling: 'Vold/slag',"
            " status: 'venter', status_navn: 'Venter', enheter: [], trenger_ressurs: true}")
        self.assertIn('enhet-brikke-mangler', ut)
        self.assertIn('Trenger ressurs', ut)
        self.assertNotIn('ingen enhet', ut)

    def test_hver_enhet_med_sin_egen_status_og_tid(self):
        """André, 21. sep. 2026: «det må og stå tidspunkt for nåværende status
        … må og skille mellom flere enheters ulike statuser».

        Sto som ett navnedrag med *oppdragets* utledede status, og da var
        «Ambulanse 1, Lag 3 · Fremme» usant for begge: den ene var fremme, den
        andre rykket ut."""
        ut = self._oppdragsrad(
            "{id: 2, nummer: 50, hastegrad: 'Akutt', problemstilling: 'Fall',"
            " status: 'fremme', status_navn: 'Fremme', trenger_ressurs: false,"
            " avventer_av: [], enheter: ["
            "  {enhet_navn: 'Bil <1>', status: 'fremme', status_navn: 'Fremme',"
            "   status_tidspunkt: new Date(Date.now() - 12 * 60000).toISOString()},"
            "  {enhet_navn: 'Lag 3', status: 'rykker_ut', status_navn: 'Rykker ut',"
            "   status_tidspunkt: new Date(Date.now() - 3 * 60000).toISOString()}]}")
        self.assertIn('Bil &lt;1&gt;', ut); self.assertNotIn('Bil <1>', ut)
        self.assertIn('status-fremme', ut); self.assertIn('status-rykker_ut', ut)
        self.assertIn('Fremme · 12 min', ut)
        self.assertIn('Rykker ut · 3 min', ut)
        self.assertEqual(ut.count('enhet-brikke'), 2, 'én brikke per enhet')

    def test_uten_stempling_teller_varslingstida(self):
        """En enhet i «Venter» har ingen `Statusmelding` — statusen kom av
        varslingen. Feltet sto da tomt på nøyaktig den raden man lurer på:
        hvor lenge har hun visst om dette uten å rykke ut?"""
        ut = self._oppdragsrad(
            "{id: 3, nummer: 51, hastegrad: 'Plassering', problemstilling: 'Utstyr',"
            " status: 'venter', status_navn: 'Venter', trenger_ressurs: false,"
            " enheter: [{enhet_navn: 'Bil 1', status: 'venter', status_navn: 'Venter',"
            "            status_tidspunkt: null,"
            "            varslet_at: new Date(Date.now() - 7 * 60000).toISOString()}]}")
        self.assertIn('Venter · 7 min', ut)
        self.assertIn('hastegrad-plassering', ut)

    def test_uten_noe_tidspunkt_staar_statusen_alene(self):
        """Og uten begge deler skal det stå «Venter», ikke «Venter · »."""
        ut = self._oppdragsrad(
            "{id: 3, nummer: 51, hastegrad: 'Akutt', problemstilling: 'Utstyr',"
            " status: 'venter', status_navn: 'Venter', trenger_ressurs: false,"
            " enheter: [{enhet_navn: 'Bil 1', status: 'venter', status_navn: 'Venter',"
            "            status_tidspunkt: null, varslet_at: null}]}")
        self.assertIn('>Venter</span>', ut)

    def test_den_avventende_merkes_paa_sin_egen_brikke(self):
        """Samme form som tavla: avventingen er et merke på enhetens brikke,
        ikke en brikke til (klonen, 21. sep. 2026)."""
        ut = self._oppdragsrad(
            "{id: 4, nummer: 52, hastegrad: 'Akutt', problemstilling: 'Fall',"
            " status: 'venter', status_navn: 'Venter', trenger_ressurs: false,"
            " avventer_av: ['Lege 02'], enheter: ["
            "  {enhet_navn: 'Lege 02', status: 'venter', status_navn: 'Venter', status_tidspunkt: null},"
            "  {enhet_navn: 'Bil 1', status: 'venter', status_navn: 'Venter', status_tidspunkt: null}]}")
        self.assertEqual(ut.count('Lege 02'), 1)
        hennes = [b for b in ut.split('<span class="enhet-brikke') if 'Lege 02' in b][0]
        self.assertIn('enhet-brikke-avventer', hennes)
        self.assertIn('avventer', hennes)
        hans = [b for b in ut.split('<span class="enhet-brikke') if 'Bil 1' in b][0]
        self.assertNotIn('avventer', hans)

    def test_trenger_ressurs_staar_foran_enhetene_som_er_igjen(self):
        """Begge kan være sanne samtidig: en bil rykket videre, en annen er på
        vei. Merket sto tidligere *i stedet for* enhetene."""
        ut = self._oppdragsrad(
            "{id: 5, nummer: 53, hastegrad: 'Akutt', problemstilling: 'Fall',"
            " status: 'venter', status_navn: 'Venter', trenger_ressurs: true,"
            " avventer_av: [], enheter: [{enhet_navn: 'Bil 1', status: 'venter',"
            "   status_navn: 'Venter', status_tidspunkt: null}]}")
        self.assertIn('Trenger ressurs', ut)
        self.assertIn('Bil 1', ut)
        self.assertLess(ut.index('Trenger ressurs'), ut.index('Bil 1'))

    def test_vis_lukkede_huskes_per_nettleser_og_er_av_som_standard(self):
        """André, 19. sep. 2026: «Når en refresher siden vises også avsluttede
        hendelser, selv om vis lukkede er trykt av.» Bryteren leses fra
        localStorage ved oppstart; uten noe lagret er den av."""
        harness = build_harness(((KO_JS, ('koLesVisLukkede', 'koLagreVisLukkede', 'koStartVisLukkede')),))
        ut = run_node(harness, '''
            const KO_VIS_LUKKEDE_NOKKEL = 'ko.vis_lukkede';
            let koVisLukkede = true;
            const lager = {};
            globalThis.localStorage = { getItem: (k) => lager[k] ?? null, setItem: (k, v) => { lager[k] = v; } };
            const boks = { checked: true };
            globalThis.document = { getElementById: (id) => id === 'ko-vis-lukkede' ? boks : null };
            koStartVisLukkede(); console.log(koVisLukkede, boks.checked);
            koLagreVisLukkede(true); koStartVisLukkede(); console.log(koVisLukkede, boks.checked, lager[KO_VIS_LUKKEDE_NOKKEL]);
            koLagreVisLukkede(false); console.log(koLesVisLukkede());
            globalThis.localStorage = { getItem() { throw new Error('privat'); }, setItem() { throw new Error('privat'); } };
            koLagreVisLukkede(true); console.log(koLesVisLukkede());
        ''').splitlines()
        self.assertEqual(ut[:4], ['false false', 'true true ja', 'false', 'false'])

    def test_lagvelgeren_starter_paa_ledeteksten_og_knappen_heter_legg_til(self):
        """André, 19. sep. 2026: «står automatisk på et lag — misvisende»."""
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'fmtMin')),
            (KO_JS, ('koLagVelgerHtml', 'koLagKandidater', 'koLagPaa', 'koSiden')),
        ))
        ut = run_node(harness, "let koRessurser = [{id: 7, navn: 'Lag 1'}, {id: 8, navn: 'Lag 2'}]; let koHendelser = new Map();\n"
                               "console.log(koLagVelgerHtml({id: 3, lag: [{ressurs_id: 8}]}));").splitlines()[0]
        self.assertIn('<option value="">Legg til lag …</option><option value="7">', ut)
        self.assertNotIn('value="8"', ut, 'lag som alt står på hendelsen tilbys ikke')
        self.assertIn('>Legg til</button>', ut)

    def test_feltene_overlever_en_omtegning(self):
        """Operatøren «datt ut av» skrivefeltet ved hver poll (André, 19. sep.
        2026): verdien, markøren og fokuset skal tilbake etter `innerHTML`."""
        harness = build_harness(((KO_JS, ('koBevarFelter',)),))
        ut = run_node(harness, '''
            let felt = { value: 'halv setn', selectionStart: 4, selectionEnd: 4, fokusert: false,
                         focus() { this.fokusert = true; }, setSelectionRange(a, b) { this.omraade = [a, b]; } };
            globalThis.document = { activeElement: felt, getElementById: (id) => id === 'a' ? felt : null };
            const tilbake = koBevarFelter(['a', 'finnes-ikke']);
            felt = { value: '', selectionStart: 0, selectionEnd: 0, fokusert: false,
                     focus() { this.fokusert = true; }, setSelectionRange(a, b) { this.omraade = [a, b]; } };
            document.activeElement = null;
            tilbake();
            console.log(JSON.stringify([felt.value, felt.fokusert, felt.omraade]));
        ''').splitlines()[0]
        self.assertEqual(ut, '["halv setn",true,[4,4]]')

    def test_prioriteten_maa_velges(self):
        """Ingen forhåndsvalgt prioritet (André, 19. sep. 2026: «litt
        misvisende»). Regelen skjemaet nekter på."""
        harness = build_harness(((KO_JS, ('koPrioritetValgt',)),))
        ut = run_node(harness, "let koValgtPrioritet = ''; console.log(koPrioritetValgt());"
                               " koValgtPrioritet = 'rod'; console.log(koPrioritetValgt());").splitlines()
        self.assertEqual(ut[:2], ['false', 'true'])

    def test_hastegraden_arver_prioriteten(self):
        """«Hvis viktig prioritering i hendelse så er det akutt hastegrad»
        (André, 19. sep. 2026). Tabellen, og tom for alt annet."""
        harness = build_harness(((KO_JS, ('koHastegradForHendelse',)),))
        ut = run_node(harness, "console.log(JSON.stringify(['viktig','rod','gul','gronn','drift','plassering','tull',''].map((p) => koHastegradForHendelse({prioritet: p}))"
                               " .concat([koHastegradForHendelse(null), koHastegradForHendelse(undefined)])));").splitlines()[0]
        self.assertEqual(json.loads(ut), ['Akutt', 'Akutt', 'Haster', 'Vanlig', 'Drift', 'Plassering', '', '', '', ''])

    def test_nytt_oppdrag_arver_hastegrad_og_notat_bare_naar_valget_byttet(self):
        """Hastegraden settes fra prioriteten og notatet fra den første linja,
        og begge kan endres (André, 19. sep. 2026). Kjøres kallet igjen med
        samme valg — som `koFyllHendelsevalg` gjør ved hver poll — røres
        ingenting; operatørens hastegrad og tekst står. Uten hendelse: tom
        hastegrad, og et arvet notat tas bort, et selvskrevet står."""
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koHendelsevalgEndret', 'koHastegradForHendelse', 'koNotatForHendelse',
                     'koOperatorlinjer', 'koHendelseLinjer', 'koNullstillHendelsevalg')),
        ))
        ut = run_node(harness, self.PRE + '''
            koHendelser = new Map([[5, {id: 5, kode: 'H5', prioritet: 'gul'}], [6, {id: 6, kode: 'H6', prioritet: 'viktig'}]]);
            koLinjer = new Map([[1, {id: 1, rot: 1, hendelse_id: 5, kilde: 'operator', tekst: 'Mann ca. 40'}],
                                [2, {id: 2, rot: 2, hendelse_id: 5, kilde: 'operator', tekst: 'senere'}]]);
            const valgt = [];
            globalThis.velgHastegrad = (v) => valgt.push(v);
            const felter = {
              'nytt-hendelse': { value: '5', dataset: {} }, 'nytt-hendelse-info': { innerHTML: '' },
              'nytt-fritekst': { value: '', dataset: {} },
            };
            globalThis.document = { getElementById: (id) => felter[id] || null };
            const les = () => JSON.stringify([valgt.join(','), felter['nytt-fritekst'].value, felter['nytt-hendelse-info'].innerHTML.includes('H5')]);
            koHendelsevalgEndret(); console.log(les());
            felter['nytt-fritekst'].value = 'Mann ca. 40, våken';
            koHendelsevalgEndret(); console.log(les());
            felter['nytt-hendelse'].value = '6';
            koHendelsevalgEndret(); console.log(les());
            felter['nytt-hendelse'].value = '';
            koHendelsevalgEndret(); console.log(les());
            felter['nytt-fritekst'].value = '';
            felter['nytt-hendelse'].value = '5'; koHendelsevalgEndret();
            felter['nytt-hendelse'].value = ''; koHendelsevalgEndret(); console.log(les());
            koNullstillHendelsevalg(); felter['nytt-hendelse'].value = '5'; koHendelsevalgEndret(); console.log(les());
        ''').splitlines()
        self.assertEqual(json.loads(ut[0]), ['Haster', 'Mann ca. 40', True])
        self.assertEqual(json.loads(ut[1]), ['Haster', 'Mann ca. 40, våken', True], 'samme valg igjen rører ingenting')
        self.assertEqual(json.loads(ut[2]), ['Haster,Akutt', 'Mann ca. 40, våken', False], 'ny hendelse: hastegrad arves, egen tekst står')
        # Uten hendelse er det ingenting å arve, og hastegraden står (23. sep.
        # 2026) — før ble den tømt, og det var halve feilen «mister
        # hastegraden sin».
        self.assertEqual(json.loads(ut[3]), ['Haster,Akutt', 'Mann ca. 40, våken', False], 'uten hendelse: hastegraden står, egen tekst står')
        self.assertEqual(json.loads(ut[4]), ['Haster,Akutt,Haster', '', False], 'et arvet notat tas bort igjen med hendelsen')
        self.assertEqual(json.loads(ut[5]), ['Haster,Akutt,Haster,Haster', 'Mann ca. 40', True], 'etter nullstilling arves det på nytt')

    def test_pollen_etter_aapning_tommer_ikke_hastegraden(self):
        """**Feilen André meldte 23. sep. 2026:** «hender det at når du
        trykker at opprett så mister en hastegraden sin». Skjemaet åpnes
        (`koNullstillHendelsevalg`), operatøren velger hastegrad, og pollen
        (`koFyllHendelsevalg` → `koHendelsevalgEndret`) kommer før «Opprett».
        Sto «uten hendelse» som et nytt valg, arvet den ingenting — og tømte
        hastegraden."""
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koHendelsevalgEndret', 'koHastegradForHendelse', 'koNotatForHendelse',
                     'koOperatorlinjer', 'koHendelseLinjer', 'koNullstillHendelsevalg')),
        ))
        ut = run_node(harness, self.PRE + '''
            koHendelser = new Map(); koLinjer = new Map();
            const kall = [];
            globalThis.velgHastegrad = (v) => kall.push(v);
            const felter = {
              'nytt-hendelse': { value: '', dataset: {} }, 'nytt-hendelse-info': { innerHTML: '' },
              'nytt-fritekst': { value: '', dataset: {} },
            };
            globalThis.document = { getElementById: (id) => felter[id] || null };
            koNullstillHendelsevalg();
            koHendelsevalgEndret(); koHendelsevalgEndret();
            console.log(JSON.stringify(kall));
        ''').splitlines()
        self.assertEqual(json.loads(ut[0]), [], 'pollen rørte hastegraden')

    def test_knytt_uten_valgt_oppdrag_sier_fra(self):
        """«Velg…» står først i «Knytt eksisterende oppdrag» (23. sep. 2026).
        Et klikk uten valg sier fra, og ingenting sendes."""
        harness = build_harness(((KO_JS, ('koKnyttEksisterende',)),))
        ut = run_node(harness, '''
            const kall = [], varsler = [];
            globalThis._koSettHendelsePaaOppdrag = async (o, h) => kall.push([o, h]);
            globalThis.window = { alert: (m) => varsler.push(m) };
            const sel = { value: '' };
            globalThis.document = { getElementById: (id) => id === 'ko-knytt-valg' ? sel : null };
            await koKnyttEksisterende('3');
            sel.value = '12';
            await koKnyttEksisterende('3');
            console.log(JSON.stringify([varsler, kall]));
        ''').splitlines()
        self.assertEqual(json.loads(ut[0]), [['Velg oppdraget som skal knyttes til hendelsen.'], [[12, 3]]])

    def test_escaper_tekst_navn_og_lagnavn(self):
        ond = '<img src=x onerror=alert(1)>'
        ut = self._kjor(
            f"console.log(koDetaljLinjeHtml({{id: 1, kilde: 'operator', tekst: {json.dumps(ond)}, forfatter: {json.dumps(ond)}, delt_at: '2026-09-19T10:00:00Z', delt_av: {json.dumps(ond)}, delt_med: []}}));\n"
            f"console.log(koLagBrikkeHtml({{id: 3}}, {{ressurs_id: 9, navn: {json.dumps(ond)}, fra: ''}}, true));\n")
        for linje in ut[:2]:
            self.assertNotIn('<img', linje)
            self.assertIn('&lt;img', linje)
        self.assertIn('data-arg="3:9"', ut[1], 'ta av-knappen for den som kan')


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class OppsettetTests(SimpleTestCase):
    """Rutenettet (ko-layout.js): rammen holder fire vinduer. `koGyldigOppsett`
    avviser alt som mangler et vindu, `koBytt` bytter to, og gulvet klemmer
    en skillelinje før et vindu er borte."""

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml',)),
            (KO_JS, ('koKlemProsent', 'koGyldigOppsett', 'koStandardOppsett',
                     'koBytt', 'koProsentAv', 'koGyldigSkjult', 'koErSkjult',
                     'koKanSkjule', 'koSkjul', 'koVisIgjen', 'koSkjulteHtml',
                     'koTegnOppsett', 'koTegnSkjulte', 'koVinduElement',
                     'koGyldigePlasser', 'koIRutenettet', 'koParkerte')),
        ))
        # Konstantene leses fra fila, ikke skrives av (22. sep. 2026). Kopien
        # som sto her hadde fire vinduer og ville fortsatt vært grønn den dagen
        # tavla kom — mot en side som ikke fantes lenger.
        from oppdrag.tests_runde_d import _konst
        self.pre = ''.join(_konst(KO_JS[0], n) for n in (
            'KO_VINDUER', 'KO_PLASSER', 'KO_PAR', 'KO_OPPSETT_STANDARD',
            'KO_VINDUSNAVN', 'KO_MIN_PROSENT'))

    #: Et rutenett av stubber: de to radene med hver sin skillelinje, de fire
    #: vinduene, den vannrette skillelinja og stripa. `skjult` leses av
    #: `d-none`, som er det `koTegnOppsett` faktisk setter.
    DOM = """
        function lagEl(id) {
          const e = { id, innerHTML: '', style: {}, klasser: new Set(), barn: [] };
          e.classList = { add: (k) => e.klasser.add(k), remove: (k) => e.klasser.delete(k),
                          contains: (k) => e.klasser.has(k),
                          toggle: (k, v) => { v ? e.klasser.add(k) : e.klasser.delete(k); } };
          Object.defineProperty(e, 'skjult', { get: () => e.klasser.has('d-none') });
          e.insertBefore = () => {}; e.appendChild = () => {};
          return e;
        }
        const rad1Splitter = lagEl('splitter-1');
        const rad2Splitter = lagEl('splitter-2');
        const vannrett = lagEl('splitter-h');
        const elementer = new Map();
        for (const id of ['ko-rad-1', 'ko-rad-2', 'ko-skjulte', 'ko-vindu-hendelser',
                          'ko-vindu-logg', 'ko-vindu-ressurser', 'ko-vindu-oppdrag',
                          'ko-vindu-tavle']) {
          elementer.set(id, lagEl(id));
        }
        elementer.get('ko-rad-1').querySelector = () => rad1Splitter;
        elementer.get('ko-rad-2').querySelector = () => rad2Splitter;
        const el = (id) => elementer.get(id);
        globalThis.document = {
          getElementById: (id) => elementer.get(id) || null,
          querySelector: (v) => (v === '.ko-splitter-h' ? vannrett
            : elementer.get('ko-vindu-' + (v.match(/data-vindu="(\\w+)"/) || [])[1]) || null),
          querySelectorAll: () => [],
        };
    """

    def _kjor(self, kode):
        return run_node(self.harness, kode, preamble=self.pre).splitlines()

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
                         {'rader': [['oppdrag', 'logg'], ['ressurser', 'hendelser']],
                          'bredde': [20, 80], 'hoyde': 80, 'skjult': []})

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


    # ── Skjuling (André, 21. sep. 2026) ────────────────────────────────────

    def test_det_siste_synlige_lar_seg_ikke_skjule(self):
        """Uten regelen kunne konsollen bli tom, og da er det ingenting igjen
        å hente noe tilbake fra utenom stripa."""
        ut = self._kjor(
            'let o = koStandardOppsett();\n'
            "for (const v of ['hendelser', 'logg', 'ressurser']) o = koSkjul(o, v);\n"
            'console.log(JSON.stringify(o.skjult));\n'
            "console.log(koKanSkjule(o, 'oppdrag'));\n"
            "console.log(JSON.stringify(koSkjul(o, 'oppdrag').skjult), 'urørt');\n")
        self.assertEqual(json.loads(ut[0]), ['hendelser', 'logg', 'ressurser'])
        self.assertEqual(ut[1], 'false')
        self.assertEqual(ut[2], '["hendelser","logg","ressurser"] urørt')

    def test_skjul_og_hent_tilbake_er_rene_regler(self):
        ut = self._kjor(
            'const o = koStandardOppsett();\n'
            "const ett = koSkjul(o, 'ressurser');\n"
            "console.log(JSON.stringify(ett.skjult), JSON.stringify(o.skjult), 'det gamle er urørt');\n"
            "console.log(koErSkjult(ett, 'ressurser'), koErSkjult(ett, 'logg'));\n"
            "console.log(JSON.stringify(koVisIgjen(ett, 'ressurser').skjult));\n"
            "console.log(JSON.stringify(koSkjul(ett, 'ukjent').skjult), 'ukjent navn gjør ingenting');\n"
            "console.log(JSON.stringify(koSkjul(ett, 'ressurser').skjult), 'to ganger er én');\n")
        self.assertEqual(ut[0], '["ressurser"] [] det gamle er urørt')
        self.assertEqual(ut[1], 'true false')
        self.assertEqual(json.loads(ut[2]), [])
        self.assertEqual(ut[3], '["ressurser"] ukjent navn gjør ingenting')
        self.assertEqual(ut[4], '["ressurser"] to ganger er én')

    def test_lagret_skjultliste_leses_som_brukerdata(self):
        """Alle fire skjult gir ingen: lagringen skal ikke kunne bære tilbake
        en tilstand `koKanSkjule()` har nektet i grensesnittet."""
        ut = self._kjor(
            "console.log(JSON.stringify(koGyldigSkjult(['logg', 'tull', 'logg'])));\n"
            "console.log(JSON.stringify(koGyldigSkjult(['hendelser','logg','ressurser','oppdrag'])));\n"
            "console.log(JSON.stringify(koGyldigSkjult('logg')), JSON.stringify(koGyldigSkjult(undefined)));\n")
        self.assertEqual(json.loads(ut[0]), ['logg'])
        self.assertEqual(json.loads(ut[1]), [])
        self.assertEqual(ut[2], '[] []')

    def test_stripa_navngir_vinduet_og_escaper(self):
        ut = self._kjor(
            "console.log(koSkjulteHtml({...koStandardOppsett(), skjult: ['ressurser', 'logg']}));\n"
            "KO_VINDUSNAVN.logg = '<b>x</b>';\n"
            "console.log(koSkjulteHtml({...koStandardOppsett(), skjult: ['logg']}));\n")
        self.assertIn('Ressursoversikt', ut[0])
        self.assertIn('Loggstrøm', ut[0])
        self.assertIn('data-action="koVisVindu" data-arg="ressurser"', ut[0])
        self.assertIn('&lt;b&gt;x&lt;/b&gt;', ut[1]); self.assertNotIn('<b>x</b>', ut[1])

    def test_naboen_tar_plassen_og_en_tom_rad_forsvinner(self):
        """Et skjult vindu gir plassen sin til naboen, ikke til et hull — og
        er begge i en rad skjult, forsvinner raden."""
        ut = self._kjor(self.DOM + """
            koTegnOppsett(koSkjul(koStandardOppsett(), 'logg'));
            console.log(el('ko-vindu-logg').skjult, el('ko-vindu-hendelser').skjult,
                        el('ko-vindu-hendelser').style.flex, el('ko-rad-1').skjult,
                        rad1Splitter.skjult, vannrett.skjult);
            let o = koSkjul(koStandardOppsett(), 'hendelser');
            koTegnOppsett(koSkjul(o, 'logg'));
            console.log(el('ko-rad-1').skjult, vannrett.skjult, el('ko-rad-2').style.flex);
            koTegnOppsett(koStandardOppsett());
            console.log(el('ko-vindu-logg').skjult, el('ko-rad-1').skjult, vannrett.skjult,
                        el('ko-rad-1').style.flex);
        """)
        self.assertEqual(ut[0], 'true false 1 1 100% false true false',
                         'naboen tar hele raden, skillelinja mellom dem er borte')
        self.assertEqual(ut[1], 'true true 1 1 100%', 'tom rad borte, den andre tar høyden')
        self.assertEqual(ut[2], 'false false false 1 1 56%', 'alt tilbake')

    def test_stripa_viser_det_parkerte_og_det_skjulte(self):
        """Tavla står i stripa fra første stund: en flate man ikke ser, skal
        være en tilstand man ser — samme grunn som for de skjulte."""
        ut = self._kjor(self.DOM + """
            koTegnOppsett(koStandardOppsett());
            console.log(el('ko-skjulte').skjult, el('ko-skjulte').innerHTML.includes('Tavle'),
                        el('ko-vindu-tavle').skjult);
            koTegnOppsett(koSkjul(koStandardOppsett(), 'oppdrag'));
            console.log(el('ko-skjulte').skjult, el('ko-skjulte').innerHTML.includes('Oppdragsliste'),
                        el('ko-skjulte').innerHTML.includes('Tavle'));
        """)
        self.assertEqual(ut[0], 'false true true')
        self.assertEqual(ut[1], 'false true true')

    # ── Tavla og ressursoversikten deler plass (22. sep. 2026) ─────────────

    def test_et_oppsett_fra_foer_tavla_er_gyldig_som_det_er(self):
        """Ingen KO-PC skal miste oppsettet sitt av en oppdatering."""
        ut = self._kjor(
            "console.log(JSON.stringify(koGyldigOppsett({rader: [['oppdrag','logg'],['ressurser','hendelser']], skjult: ['logg']})));\n"
            "console.log(JSON.stringify(koGyldigOppsett({rader: [['oppdrag','logg'],['tavle','hendelser']]}).rader));\n")
        self.assertEqual(json.loads(ut[0])['rader'], [['oppdrag', 'logg'], ['ressurser', 'hendelser']])
        self.assertEqual(json.loads(ut[0])['skjult'], ['logg'])
        self.assertEqual(json.loads(ut[1]), [['oppdrag', 'logg'], ['tavle', 'hendelser']])

    def test_begge_i_paret_eller_ingen_av_dem_avvises(self):
        """Nøyaktig én av paret står i rutenettet. Begge ville skjøvet ut et
        vindu uten partner — og det har ingen vei tilbake."""
        ut = self._kjor(
            "console.log(koGyldigOppsett({rader: [['tavle','logg'],['ressurser','hendelser']]}));\n"
            "console.log(koGyldigOppsett({rader: [['oppdrag','logg'],['hendelser','hendelser']]}));\n"
            "console.log(koGyldigOppsett({rader: [['oppdrag','logg'],['tull','hendelser']]}));\n")
        self.assertEqual(ut[:3], ['null', 'null', 'null'])

    def test_hent_tavla_tar_ressursoversiktens_plass(self):
        ut = self._kjor(
            'const o = koStandardOppsett();\n'
            "const t = koVisIgjen(o, 'tavle');\n"
            'console.log(JSON.stringify(t.rader), JSON.stringify(koParkerte(t)));\n'
            'console.log(JSON.stringify(o.rader), "det gamle er urørt");\n'
            "console.log(JSON.stringify(koVisIgjen(t, 'ressurser').rader));\n"
            "console.log(JSON.stringify(koVisIgjen(koSkjul(o, 'ressurser'), 'tavle').skjult),"
            " 'den skjulte partneren slippes med');\n")
        # Planleggeren står parkert også — den deler plass med oppdragslista.
        self.assertEqual(ut[0], '[["hendelser","logg"],["tavle","oppdrag"]] ["ressurser","plan"]')
        self.assertEqual(ut[1], '[["hendelser","logg"],["ressurser","oppdrag"]] det gamle er urørt')
        self.assertEqual(json.loads(ut[2]), [['hendelser', 'logg'], ['ressurser', 'oppdrag']])
        self.assertEqual(ut[3], '[] den skjulte partneren slippes med')

    def test_det_parkerte_kan_ikke_skjules_eller_byttes(self):
        """Det står ikke i rutenettet; å «skjule» det ville lagt et navn i
        skjultlista som ingen plass bærer."""
        ut = self._kjor(
            'const o = koStandardOppsett();\n'
            "console.log(koKanSkjule(o, 'tavle'), JSON.stringify(koSkjul(o, 'tavle').skjult));\n"
            "console.log(JSON.stringify(koBytt(o, 'tavle', 'logg').rader));\n")
        self.assertEqual(ut[0], 'false []')
        self.assertEqual(json.loads(ut[1]), [['hendelser', 'logg'], ['ressurser', 'oppdrag']])

    def test_den_parkerte_tegnes_ikke(self):
        ut = self._kjor(self.DOM + """
            koTegnOppsett(koVisIgjen(koStandardOppsett(), 'tavle'));
            console.log(el('ko-vindu-tavle').skjult, el('ko-vindu-ressurser').skjult);
        """)
        self.assertEqual(ut[0], 'false true')


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
                                  'tidSiden', '_grovMerke', '_enhetsmatrise', 'enhetAvventer',
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
        "  hendelse_prioritet: 'viktig', hendelse_lag: ['<b>Lag 1</b>', 'Lag 3'], enheter: []}];\n"
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
class SynlighetsmenyTests(SimpleTestCase):
    """«Vis»-menyen (André, 23. sep. 2026: «istedenfor minimer som tar plass at
    vi har en synlighetsknapp»). Erstatter de minimerbare gruppene og
    Alle | Biler | Lag. **Det skjulte skal fortsatt synes** (§7.2): knappen
    bærer antallet. Tilstanden huskes i `localStorage`, stubbet her.

    Testene går gjennom de ekte inngangene — `tegnEnhetsliste` og
    `koTegnRessurser` for lista, `oppdaterSynlighetsmeny` for menyen, og
    handlingene menyen kaller — ikke bare hjelperne."""

    LAGER = '''
      const _lager = {};
      globalThis.localStorage = {
        getItem: (k) => (k in _lager ? _lager[k] : null),
        setItem: (k, v) => { _lager[k] = String(v); },
      };
      globalThis.window = { OPPDRAG_ENHETSTYPER: [[1, 'Ambulanse'], [2, 'Mannskapsbil']], MODUL_TILGANG: {} };
      let sisteEnhetsliste = []; let enhetslisteKilde = null;
      let besetninger = {}; let apenBesetning = null;
      let koRessurser = []; let koApenRessurs = null;
      const GRUPPER_SKJULT_NOKKEL = 'tavle.grupper.skjult';
      function mkBesetning() { return ''; }
      function kanSeBesetning() { return false; }
      function koRessursOpptattHtml() { return ''; }
      const el = (id) => { const e = { id, innerHTML: '', textContent: '', klasser: new Set() };
        e.classList = { toggle: (k, v) => { v ? e.klasser.add(k) : e.klasser.delete(k); } }; return e; };
      const dom = { 'enhetsliste': el('enhetsliste'), 'vaktliste-ressurser': el('vaktliste-ressurser'),
                    'ressurs-vis-meny': el('ressurs-vis-meny'), 'ressurs-vis-tall': el('ressurs-vis-tall'),
                    'ressurs-vis-knapp': el('ressurs-vis-knapp') };
      globalThis.document = { getElementById: (id) => dom[id] || null, activeElement: null };
      const LISTE = [
        {id: 1, navn: 'HGSD 56', pa_vakt: true, type: 1, status: 'ledig', status_navn: 'Ledig'},
        {id: 2, navn: 'KARM 12', pa_vakt: true, type: 1, status: 'fremme', status_navn: 'Fremme'},
        {id: 3, navn: 'MB 3', pa_vakt: true, type: 2, status: 'ledig', status_navn: 'Ledig'},
        {id: 4, navn: 'Av', pa_vakt: false, type: 2, status: 'ledig', status_navn: 'Ledig'},
      ];
      koRessurser = [
        {id: 7, navn: 'Lag 1', gruppe_id: 5, gruppe_navn: 'Lag', antall: 3, tilstede: 2},
        {id: 8, navn: 'Lag 2', gruppe_id: 5, gruppe_navn: 'Lag', antall: 0, tilstede: 0},
        {id: 9, navn: 'Samleplass A', gruppe_id: 6, gruppe_navn: 'Samleplass', antall: 2, tilstede: 2}];
      // Som i sentralbordet: en ny tegning av lista tegner også lagene.
      function tegnEnhetslistePaaNytt() { tegnEnhetsliste(LISTE); }
      function koTegnRessurserPaaNytt() { koTegnRessurser(); koOppdaterSynlighet(); }
      const vis = () => JSON.stringify({ biler: dom['enhetsliste'].innerHTML, lag: dom['vaktliste-ressurser'].innerHTML,
        meny: dom['ressurs-vis-meny'].innerHTML, tall: dom['ressurs-vis-tall'].textContent,
        aktiv: dom['ressurs-vis-knapp'].klasser.has('aktiv') });
    '''

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
            (OPPDRAG_KORT_JS, self.OPPDRAG_KORT),
            (KO_JS, ('koTegnRessurser', 'koSynlighetsgrupper', 'koOppdaterSynlighet', 'koGruppenokkel',
                     'koGrupperRessurser', 'koRessurskort')),
        ))

    OPPDRAG_KORT = ('_skjulteGrupper', 'gruppeErSkjult', '_lagreSkjulte', 'vippSynlighet',
                    'vippSeksjon', 'visAlleGrupper', 'synlighetsSeksjoner', 'skjultTall',
                    '_synlighetsvalg', 'synlighetsmenyHtml', 'oppdaterSynlighetsmeny',
                    'gruppehode', 'tegnEnhetsliste', '_grupperEnheter',
                    '_typeRekkefolge', '_enhetskort', 'enhetskortInnmat',
                    'tidSiden', 'hastegradKlasse', '_grovMerke', '_problemMedAntall',
                    '_medAntall', 'oppdragsnr')

    def _steg(self, *handlinger):
        """Tegn lista, kjør handlingene i rekkefølge, og returner tilstanden
        etter hver av dem (den første er før noe er gjort)."""
        kode = 'tegnEnhetslistePaaNytt(); koTegnRessurserPaaNytt(); console.log(vis());\n' + ''.join(
            f'{h}; console.log(vis());\n' for h in handlinger)
        return [json.loads(linje) for linje in run_node(self.harness, self.LAGER + kode).splitlines()[:len(handlinger) + 1]]

    def test_alt_vises_fra_start_og_menyen_har_begge_seksjonene(self):
        [start] = self._steg()
        self.assertIn('HGSD 56', start['biler'])
        self.assertIn('MB 3', start['biler'])
        self.assertIn('Lag 1', start['lag'])
        self.assertEqual(start['tall'], '')
        self.assertFalse(start['aktiv'])
        for arg in ('biler', 'type:1', 'type:2', 'lag', 'gruppe:5', 'gruppe:6'):
            self.assertIn(f'data-arg="{arg}"', start['meny'])
        self.assertNotIn('visAlleGrupper', start['meny'], '«Vis alle» bare når noe er skjult')
        self.assertIn('Ambulanse</span><span class="synlighet-antall">2<', start['meny'],
                      'antallet på vakt — ikke den av vakt')

    def test_en_skjult_gruppe_tar_null_plass_og_telles_paa_knappen(self):
        start, skjult, tilbake = self._steg("vippSynlighet('type:1')", "vippSynlighet('type:1')")
        self.assertNotIn('HGSD 56', skjult['biler'])
        self.assertNotIn('Ambulanse', skjult['biler'], 'heller ikke overskriften står igjen')
        self.assertIn('MB 3', skjult['biler'])
        self.assertEqual(skjult['tall'], ' · 2 skjult', 'antallet ressurser, ikke grupper')
        self.assertTrue(skjult['aktiv'])
        self.assertIn('aria-checked="false" data-action="vippSynlighet" data-arg="type:1"', skjult['meny'])
        self.assertIn('visAlleGrupper', skjult['meny'])
        self.assertEqual(tilbake, start, 'et klikk til gir alt tilbake')

    def test_seksjonen_er_det_alle_biler_lag_var(self):
        _, bare_biler, begge, delvis, lag_av = self._steg(
            "vippSeksjon('lag')", "vippSeksjon('lag')", "vippSynlighet('gruppe:6')", "vippSeksjon('lag')")
        self.assertEqual(bare_biler['lag'], '', 'Lag av: ingen av vaktlistas grupper')
        self.assertIn('HGSD 56', bare_biler['biler'])
        self.assertEqual(bare_biler['tall'], ' · 3 skjult')
        self.assertIn('Lag 1', begge['lag'])
        self.assertIn('Lag 1', delvis['lag'])
        self.assertNotIn('Samleplass A', delvis['lag'])
        self.assertEqual(lag_av['lag'], '', 'er noe i seksjonen synlig, skjuler klikket alt')

    def test_alle_bilene_skjult_sier_det_og_vis_alle_gir_alt_tilbake(self):
        start, _, alle_av, _, tilbake = self._steg(
            "vippSeksjon('biler')", "vippSeksjon('lag')", "visAlleGrupper()", "void 0")
        self.assertIn('Alle bilene er skjult', alle_av['biler'])
        self.assertEqual(alle_av['tall'], ' · 6 skjult')
        self.assertEqual(tilbake, start)

    def test_husket_noekkel_for_en_gruppe_som_ikke_er_paa_vakt_teller_ikke(self):
        [start] = self._steg()
        ut = json.loads(run_node(self.harness, self.LAGER + '''
            _lager['tavle.grupper.skjult'] = JSON.stringify(['type:99', 'gruppe:42']);
            tegnEnhetslistePaaNytt(); console.log(vis());
        ''').splitlines()[0])
        self.assertEqual(ut['tall'], '')
        self.assertEqual(ut['biler'], start['biler'])

    def test_valget_huskes_i_nettleseren(self):
        ut = run_node(self.harness, self.LAGER + '''
            vippSynlighet('type:2'); console.log(localStorage.getItem('tavle.grupper.skjult'));
        ''').splitlines()
        self.assertEqual(ut[0], '["type:2"]')

    def test_i_oppdrag_tegner_lista_menyen_selv_og_uten_lag(self):
        """`/oppdrag/` laster ikke `ko.js`: der er kallet i `tegnEnhetsliste`
        det eneste som tegner menyen, og det finnes ingen Lag-seksjon."""
        harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'klokke')),
            (OPPDRAG_KORT_JS, self.OPPDRAG_KORT),
        ))
        ut = json.loads(run_node(harness, self.LAGER.replace(
            'function koTegnRessurserPaaNytt() { koTegnRessurser(); koOppdaterSynlighet(); }', '') + '''
            tegnEnhetsliste(LISTE); vippSynlighet('type:2'); console.log(vis());
        ''').splitlines()[0])
        self.assertIn('data-arg="type:1"', ut['meny'])
        self.assertNotIn('data-arg="lag"', ut['meny'])
        self.assertEqual(ut['tall'], ' · 1 skjult')

    def test_lagene_kommer_inn_i_menyen_naar_de_er_hentet(self):
        """Lagene hentes for seg (`koHentRessurser`), ofte etter at lista er
        tegnet. Da må menyen få dem — ellers kan de ikke skjules."""
        harness = self.harness + build_harness(((KO_JS, ('koHentRessurser',)),))
        ut = json.loads(run_node(harness, self.LAGER + '''
            const hentet = koRessurser; koRessurser = [];
            tegnEnhetslistePaaNytt();
            globalThis.apiFetch = async () => ({ ok: true, json: async () => ({ data: hentet }) });
            await koHentRessurser();
            console.log(vis());
        ''').splitlines()[0])
        self.assertIn('data-arg="gruppe:5"', ut['meny'])

    def test_menyen_og_overskriften_escaper_navnet(self):
        ut = run_node(self.harness, self.LAGER + '''
            koRessurser[0].gruppe_navn = '<b>x</b>'; koRessurser[0].gruppe_id = '"><img src=x>';
            tegnEnhetslistePaaNytt(); koTegnRessurserPaaNytt(); console.log(vis());
            console.log(gruppehode('<b>y</b>'));
        ''').splitlines()
        self.assertNotIn('<b>', ut[0] + ut[1])
        self.assertNotIn('<img', ut[0])
        self.assertIn('&lt;b&gt;y&lt;/b&gt;', ut[1])


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class RessurskorteneTests(SimpleTestCase):
    """Vaktlistas ressurser på tavla: kortet sier hvor mange som er møtt og
    om laget er på en hendelse; **besetningen — navn, møtt, telefon, ISSI —
    står bak et klikk** (André, 19. sep. 2026: «da sparer vi plass»). Alt
    brukerskrevet escapes, det er fritekst fra et annet register."""

    PRE = 'let koApenRessurs = null; let koHendelser = new Map();\n'

    def setUp(self):
        self.harness = build_harness((
            (PORTAL_UTILS_JS, ('escapeHtml', 'escHtmlValue', 'fmtMin')),
            (JS_DIR / 'oppdrag-kort.js', ('_besetningKontakt',)),
            (KO_JS, ('koRessurskort', 'koRessursMannskap', 'koGrupperRessurser', 'koKlokke',
                     'koRessursBesetningHtml', 'koRessursOpptattHtml', 'koSiden', 'koLagPaa')),
        ))

    R = {'id': 1, 'navn': 'Lag 3', 'gruppe_ikon': 'people', 'antall': 2, 'tilstede': 1,
         'mannskap': [{'navn': 'Kari', 'rolle': 'Lagleder', 'telefon': '911 22 333', 'issi': '2401234', 'tilstede': True},
                      {'navn': 'Ola', 'rolle': '', 'telefon': '', 'issi': '', 'tilstede': False}],
         }

    def _kort(self, r, pre=''):
        return run_node(self.harness, f'console.log(koRessurskort({json.dumps(r)}));', preamble=self.PRE + pre)

    def test_lukket_kort_sier_tallet_men_ikke_hvem(self):
        ut = self._kort(self.R)
        self.assertIn('1 av 2 møtt', ut)
        self.assertIn('bi-people', ut)
        self.assertIn('enhet-kort-klikkbar', ut)
        self.assertIn('data-action="koVippRessurs"', ut)
        self.assertNotIn('Kari', ut, 'navnene står bak klikket')
        self.assertNotIn('911', ut)

    def test_klikket_kort_viser_navn_moett_telefon_og_issi(self):
        ut = self._kort(self.R, 'koApenRessurs = 1;\n')
        self.assertIn('ko-ressurskort-apen', ut)
        self.assertIn('<span>Kari</span>', ut)
        self.assertIn('Lagleder', ut)
        self.assertIn('href="tel:91122333"', ut)
        self.assertIn('2401234', ut)
        self.assertIn('title="Møtt">●', ut)
        self.assertIn('title="Ikke møtt">○', ut)

    def test_paa_hendelse_leses_fra_de_aapne_hendelsene(self):
        pre = ("koHendelser.set(5, {id: 5, kode: 'H14', tittel: 'Bevisstløs', status: 'apen', lokasjon_navn: 'Hovedscene',"
               " lag: [{ressurs_id: 1, fra: new Date(Date.now() - 23 * 60000).toISOString()}]});\n"
               "koHendelser.set(6, {id: 6, kode: 'H9', tittel: 'Lukket', status: 'lukket',"
               " lag: [{ressurs_id: 1, fra: new Date().toISOString()}]});\n"
               "koHendelser.set(7, {id: 7, kode: 'H15', tittel: 'Uten sted', status: 'apen', lokasjon_navn: '',"
               " lag: [{ressurs_id: 1, fra: new Date(Date.now() - 5 * 60000).toISOString()}]});\n")
        ut = self._kort(self.R, pre)
        self.assertIn('På H14 · Hovedscene · 23 min', ut, 'stedet står på kortet (19. sep. 2026)')
        self.assertIn('På H15 · 5 min', ut, 'uten sted: ingen tom ledd')
        self.assertIn('Bevisstløs', ut)
        self.assertNotIn('H9', ut, 'en lukket hendelse holder ingen')
        self.assertNotIn('På H', self._kort(dict(self.R, id=2), pre), 'et annet lag er ledig')

    def test_escaper_navn_og_ikon(self):
        ond = '<img src=x onerror=alert(1)>'
        r = dict(self.R, navn=ond, gruppe_ikon='x" onload="alert(1)',
                 mannskap=[{'navn': ond, 'rolle': ond, 'telefon': ond, 'issi': ond, 'tilstede': True}])
        pre = ("koHendelser.set(5, {id: 5, kode: 'H14', tittel: '" + ond.replace("'", "\\'")
               + "', status: 'apen', lag: [{ressurs_id: 1, fra: new Date().toISOString()}]});\n")
        ut = self._kort(r, 'koApenRessurs = 1;\n' + pre)
        self.assertNotIn('<img', ut)
        self.assertNotIn('" onload="', ut)
        self.assertIn('&lt;img', ut)

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
