"""CLAUDE.md er delt i rot + én fil per modul — og delingen må holde (15. sep. 2026).

Fila var 1 433 linjer, og 651 av dem gjaldt én modul om gangen. Nå leser
Claude Code rota hver gang og en modulfil når noen arbeider i mappa, slik at
vaktlistas 489 linjer ikke lenger følger med når man retter en skrivefeil i
`accounts/`.

Delingen er billig, men den gjør tre feil mulige som ikke fantes før — og alle
tre er stille:

1. **Modulfila står ikke i `DOKUMENTER`**, og da slutter dokumentråte-testen å
   kontrollere stiene, kommandoene og de slettede symbolene i den. Det er den
   verste av de tre: delingen ville da ha slått av regelen for nettopp den
   dokumentasjonen som råtner fortest, uten at noe ble rødt.
2. **Ingen peker på fila.** En modulfil ingen vet om, er en fil ingen leser —
   samme feil som `/api/grupper/` uten flate.
3. **Modulavsnittet vokser tilbake i rota**, og da finnes regelen to steder.
   To kopier er to kilder som glir fra hverandre, og den som leser den ene vet
   ikke at den andre finnes.
4. **Modulstoffet vokser tilbake i en tabell** i stedet for under en
   overskrift, og da ser regel 3 det ikke. `MODULOVERSKRIFT` leter etter
   `### Noe (oppdrag/)`; en tabellrad har ingen overskrift. Frontend-tabellen
   hadde 17. sep. 2026 to rader på 888 og 652 tegn med lydvarselets terskler og
   vaktlistas faneoppsett — altså to hele modulavsnitt, skrevet som to linjer.

**Grensene måler tegn, ikke linjer** (17. sep. 2026). De gjorde det motsatte
til den dagen, og de to radene over er grunnen til at det ikke duger: 1 540
tegn på 2 linjer er usynlig for en linjetelling, mens det er nøyaktig det
konteksten betaler for. Da modulstoffet ble flyttet ut, gikk rota **opp** to
linjer og **ned** 1 751 tegn — under den gamle grensa så oppryddingen ut som
en forverring.

Grensene er fortsatt den svakeste regelen her, og det står med vilje: de måler
omfang og ikke innhold, og de kan tilfredsstilles ved å slette noe nyttig. De
er røykvarslere for at delingen er i ferd med å oppheve seg selv, ikke
budsjetter.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.tests_dokumentråte import DOKUMENTER

ROT = Path(settings.BASE_DIR)

#: Rota skal ikke vokse tilbake til det den kom fra. Tallet er ikke hellig —
#: det er satt med rom over dagens fil (62 338), slik at en ny rammeverksregel
#: får plass mens et helt modulavsnitt ikke gjør det. Et avsnitt med én regel og
#: begrunnelsen sin er 400–600 tegn; et modulavsnitt er noen tusen.
#:
#: **Tallene her er tegn, ikke bytes.** `wc -c` teller bytes, og æ, ø og å er to
#: hver i UTF-8 — differansen er 1 297 tegn på rota og 1 441 på vaktlistefila.
#: Settes et tak fra `wc -c`, er det slakt fra fødselen, og det ble det: den
#: første pinnen under sto 1 450 for høyt og lot fila vokse. Funnet ved
#: mutasjonstesting 17. sep. 2026.
ROT_TEGNGRENSE = 65_500

#: Modulfilene har sin egen grense. De lastes bare av den som arbeider i mappa,
#: så de er billigere enn rota — men delingen 15. sep. 2026 flyttet 574 linjer
#: ut av rota uten å sette noe tak på der de havnet, og da er «flytt det til
#: modulfila» et svar som virker helt til modulfila er den nye monolitten.
MODUL_TEGNGRENSE = 22_000

#: Modulfiler som er over grensa i dag, med begrunnelse og dagens størrelse.
#:
#: **Unntaksliste, ikke en tillatelse.** Tallet er et tak som bare skal ned:
#: fila kan krympe, ikke vokse. Å heve det er å bestemme at modulfila skal bli
#: større, og det skal være en avgjørelse noen tar i en diff — ikke noe som
#: skjer fordi testen ble rød en travel kveld.
FOR_STORE_I_DAG: dict[str, int] = {
    # 56 799 tegn 17. sep. 2026. Fila ble **strukturert** samme dag — 13
    # seksjoner der det var én — og vokste 1 056 tegn av overskriftene og
    # ingressene. Det er en bevisst byttehandel: en fil man kan lete i, og en
    # vakt som kan si *hvilken* del som vokser, for prisen av tusen tegn.
    #
    # Den ble ikke kuttet, og det er også et valg. Hvert avsnitt bærer en regel
    # **og** feilen som lærte oss den, og det er begrunnelsen som får reglene
    # til å feste seg. Å hente tusen tegn ved å stryke «hvorfor» ville gjort
    # fila kortere og dokumentasjonen dårligere. Se `TODO.md` for hva som
    # faktisk kan gjøres: seksjonene er nå små nok til å vurderes hver for seg.
    'vaktliste/CLAUDE.md': 56_900,
    # 22 615 tegn 21. sep. 2026, og `ko/CLAUDE.md` 22 249. **Begge var på
    # taket, og det er taket som gjorde jobben sin:** `ko/CLAUDE.md` sto 12 tegn under 22 000
    # og `oppdrag/CLAUDE.md` 11, så kvelden med sju punkter fra André kostet
    # fire runder med å barbere prosa andre steder i filene for å få plass til
    # tre nye regler.
    #
    # Det er den vekslingen regelen over advarer mot fra den andre siden: å
    # hente tegn ved å stryke «hvorfor» gjør fila kortere og dokumentasjonen
    # dårligere. Dubletter ble slått sammen — «bare når satt» sto to steder i
    # oppdragsfila, «feature parity» hadde egen overskrift over det samme
    # poenget som åpnet sentralbordseksjonen i KO-fila, og leveranselista i
    # KO-innledningen gjentok CHANGELOG. Det holdt ikke.
    #
    # **Taket heves derfor her, med det som er den ekte rettingen skrevet ned:
    # begge filene skal deles, som rota ble 15. sep. 2026.** Se `TODO.md`.
    # Tallene er dagens størrelse pluss den samme slakken vaktlistefila har,
    # så de kan krympe og ikke vokse — den neste som trenger plass møter
    # samme vegg, og da er delingen svaret.
    #
    # **Begge er delt**: KO-fila 22. sep. 2026 (flaten til
    # `templates/ko/CLAUDE.md`) og oppdragsfila 23. sep. (frontendseksjonen til
    # `templates/oppdrag/CLAUDE.md`, fra 22 636 til under 18 000 tegn). Radene er
    # borte herfra, og begge står under `MODUL_TEGNGRENSE` som de andre.
}

#: Over denne størrelsen må en modulfil ha seksjoner. Tallet er der en fil
#: slutter å være noe man leser og blir noe man leter i.
#:
#: **Dette er regelen som ville fanget vaktlista i august.** Fila vokste til
#: 707 linjer under **én** overskrift, og et flatt punktlista på den lengden har
#: ingen steder ting «hører hjemme» — så alt havner nederst, og ingen kan se
#: hvilken del som vokser. Størrelsen var symptomet; fraværet av struktur var
#: årsaken.
SEKSJONSKRAV_TEGN = 8_000
MIN_SEKSJONER = 3

#: Ingen enkeltseksjon i en modulfil skal passere denne. Største i dag er
#: «Planleggingsflatene» på 8 003 tegn, og den er nettopp den som ikke skal
#: vokse mer — da er den en monolitt inni fila som nettopp ble delt.
SEKSJON_TEGNGRENSE = 9_000

#: Modulfiler som mangler seksjoner i dag, med begrunnelse.
#: Samme slags unntaksliste som `FOR_STORE_I_DAG`, og den skal krympe.
UTEN_SEKSJONER_I_DAG: dict[str, str] = {
    # 17 275 tegn under én overskrift 17. sep. 2026 — samme flate vegg som
    # vaktlista hadde, bare mindre. Statusmaskinen, verdimengdene, bilens
    # utganger og historikken er fire ting. Se `TODO.md`.
    'oppdrag/CLAUDE.md': 'flat punktliste, skal struktureres — se TODO.md',
}

#: En tabellrad i rota som navngir en moduls egen fil skal være et *oppslag*,
#: ikke en beskrivelse. Grensa er satt godt over dagens bredeste rad (122 tegn)
#: og godt under de to som utløste regelen (888 og 652).
RAD_TEGNGRENSE = 200

#: `patients-app.js` -> `patients`, `static/css/vaktliste.css` -> `vaktliste`.
#: Eierskapet **utledes**, det står ikke i en liste: en ny modul med en ny fil
#: skal dekkes fra dagen den finnes, og en håndholdt liste forfaller i stillhet.
FILNAVN = re.compile(r'`([A-Za-z0-9_./*-]+\.(?:js|css|py|html))`')

#: Raden i tabellen «Hvor dokumentasjonen bor». `templates/ko/CLAUDE.md` er
#: modulens *flatefil* (22. sep. 2026), og står i tabellen som de andre.
TABELLRAD = re.compile(r'^\|\s*`((?:templates/)?[a-z_]+/CLAUDE\.md)`\s*\|', re.M)

#: `### Vaktlistemodulen (vaktliste/)` — et avsnitt som har en modul som subjekt.
MODULOVERSKRIFT = re.compile(r'^#{1,4} .*\(([a-z_]+)/\)', re.M)


def _modulfiler() -> list[str]:
    """Hver `<app>/CLAUDE.md` og `templates/<app>/CLAUDE.md` som finnes, som
    sti fra rota.

    Den andre formen er **flatefila** (22. sep. 2026, da `ko/CLAUDE.md` ble
    delt): Claude Code laster en CLAUDE.md når noen arbeider i mappa den står
    i, og vinduene, knappene og rutenettet endres i `templates/<app>/`. Den
    skal kontrolleres, føres opp og holdes under taket som modulfilene — ellers
    var delingen en vei rundt alle tre reglene.
    """
    moduler = [f'{p.parent.name}/CLAUDE.md' for p in ROT.glob('*/CLAUDE.md')]
    flater = [f'templates/{p.parent.name}/CLAUDE.md' for p in ROT.glob('templates/*/CLAUDE.md')]
    return sorted(moduler + flater)


def _app(sti: str) -> str:
    """Hvilken app en modul- eller flatefil hører til."""
    deler = sti.split('/')
    return deler[1] if deler[0] == 'templates' else deler[0]


class ModulfileneErMedTests(SimpleTestCase):

    def test_det_finnes_modulfiler_i_det_hele_tatt(self) -> None:
        """Sperrehake. Uten den går resten av klassen grønn på en tom liste —
        altså nøyaktig i det tilfellet der delingen er borte."""
        self.assertGreaterEqual(len(_modulfiler()), 4, _modulfiler())

    def test_hver_modulfil_kontrolleres_av_dokumentraate(self) -> None:
        mangler = [f for f in _modulfiler() if f not in DOKUMENTER]
        self.assertEqual(
            mangler, [],
            'Disse modulfilene kontrolleres ikke av core/tests_dokumentråte.py:\n  '
            + '\n  '.join(mangler)
            + '\n\nLegg dem i DOKUMENTER der. Uten det står stiene og symbolene '
              'i dem ukontrollert.')

    def test_hver_modulfil_staar_i_tabellen_i_rota(self) -> None:
        """Og omvendt: tabellen skal ikke peke på en fil som ikke finnes."""
        i_tabellen = set(TABELLRAD.findall((ROT / 'CLAUDE.md').read_text(encoding='utf-8')))
        paa_disk = set(_modulfiler())
        self.assertEqual(
            sorted(paa_disk - i_tabellen), [],
            'Modulfiler som ingen peker på — før dem opp i «Hvor dokumentasjonen bor».')
        self.assertEqual(
            sorted(i_tabellen - paa_disk), [],
            'Tabellen i CLAUDE.md peker på modulfiler som ikke finnes.')

    def test_modulfila_begynner_med_en_overskrift_og_peker_hjem(self) -> None:
        """En modulfil uten veien tilbake leses som om den var alt som gjelder."""
        for sti in _modulfiler():
            with self.subTest(fil=sti):
                tekst = (ROT / sti).read_text(encoding='utf-8')
                self.assertTrue(tekst.startswith('# '), 'mangler overskrift øverst')
                self.assertIn('CLAUDE.md', tekst.split('\n\n', 2)[1],
                              'ingressen peker ikke tilbake på rota')


class RotaBeskriverRammeverketTests(SimpleTestCase):

    def test_ingen_modul_har_sitt_eget_avsnitt_i_rota(self) -> None:
        """`### Vaktlistemodulen (vaktliste/)` i rota betyr at avsnittet er
        skrevet to steder — eller flyttet tilbake."""
        rot = (ROT / 'CLAUDE.md').read_text(encoding='utf-8')
        har_egen_fil = {_app(s) for s in _modulfiler()}
        funn = sorted({a for a in MODULOVERSKRIFT.findall(rot) if a in har_egen_fil})
        self.assertEqual(
            funn, [],
            'Disse modulene har et avsnitt i rota **og** en egen fil: '
            + ', '.join(funn)
            + '\n\nModulens egne regler hører hjemme i modulfila. Gjelder regelen '
              'flere moduler, skriv den som en rammeverksregel uten modulen i '
              'overskriften.')

    def test_rota_har_ikke_vokst_tilbake(self) -> None:
        tekst = (ROT / 'CLAUDE.md').read_text(encoding='utf-8')
        tegn = len(tekst)
        self.assertLess(
            tegn, ROT_TEGNGRENSE,
            f'CLAUDE.md er {tegn} tegn ({len(tekst.splitlines())} linjer). '
            f'Hører det nye til én modul, flytt det til modulfila; gjelder det '
            f'alle, hev grensa bevisst — og skriv hvorfor det som står igjen er '
            f'rammeverk.')


class RotaKartleggerBareTests(SimpleTestCase):
    """**Rota kartlegger, modulfila forklarer.**

    `test_ingen_modul_har_sitt_eget_avsnitt_i_rota` leter etter overskrifter, og
    en tabellrad har ingen. Frontend-tabellen i rota hadde derfor 17. sep. 2026
    to rader på 888 og 652 tegn — lydvarselets terskler, offline-køens
    ventetid, vaktlistas faneoppsett og skjøten mellom `tegning` og `oversikt`.
    Det er to modulavsnitt, skrevet slik at regelen over ikke kunne se dem.

    Regelen her er ikke «ingen modulnavn i rota». Det ville vært en test med
    falske funn, og en test med falske funn blir slått av: rota **må** kunne
    skrive `patients/tests_modul_dekorator.py` når den forklarer at hvert view
    skal være dekorert, og `oppdrag.Enhet` når den forklarer unntakslista i
    avhengighetsretningen. En gjennomgang 17. sep. fant femten slike, og alle
    femten var riktige.

    Regelen er smalere og treffer bare det som faktisk gikk galt: **navngir
    første celle i en tabellrad en fil modulen eier, skal raden være et oppslag
    og ikke en beskrivelse.** *Når* en fil lastes er en grense mellom moduler og
    hører hjemme i rota; hva den gjør innvendig hører hjemme hos modulen.
    """

    def _eier(self, navn: str) -> str | None:
        """Hvilken modul eier fila, utledet av navnet?

        `patients-app.js` og `static/css/vaktliste.css` eies; `portal-utils.js`
        og `base_portal.html` gjør ikke. Utledet og ikke slått opp i en liste,
        slik at en ny modul er dekket fra dagen den har en fil.
        """
        stamme = navn.split('/')[-1].rsplit('.', 1)[0]
        for app in {_app(s) for s in _modulfiler()}:
            if stamme == app or stamme.startswith(app + '-'):
                return app
        return None

    def _rader(self):
        """[(linjenr, rad, eiere)] for hver tabellrad i rota som nevner en
        moduleid fil i første celle."""
        ut = []
        tekst = (ROT / 'CLAUDE.md').read_text(encoding='utf-8')
        for nr, linje in enumerate(tekst.split('\n'), 1):
            if not linje.startswith('|'):
                continue
            celler = linje.split('|')
            if len(celler) < 3:
                continue
            eiere = {self._eier(n) for n in FILNAVN.findall(celler[1])} - {None}
            if eiere:
                ut.append((nr, linje, sorted(eiere)))
        return ut

    def test_en_modulfils_rad_i_rota_er_et_oppslag(self) -> None:
        funn = [f'linje {nr} ({", ".join(eiere)}): {len(rad)} tegn — '
                f'{rad.split("|")[1].strip()[:40]}'
                for nr, rad, eiere in self._rader() if len(rad) > RAD_TEGNGRENSE]
        self.assertEqual(funn, [], (
            f'Tabellrader i CLAUDE.md som beskriver en moduls fil i stedet for å '
            f'peke på den (over {RAD_TEGNGRENSE} tegn):\n  ' + '\n  '.join(funn)
            + '\n\nRota svarer på *når* fila lastes; hva den gjør står i '
              'modulfila. Flytt beskrivelsen dit og la raden peke.'))

    def test_regelen_finner_faktisk_rader(self) -> None:
        """Sperrehake. Treffer ikke `FILNAVN`, eller endrer tabellen form, er
        testen over grønn for alltid og vokter ingenting — samme grep som
        `core/tests_js_regler.py`."""
        rader = self._rader()
        self.assertGreaterEqual(len(rader), 5, [r[1][:60] for r in rader])
        self.assertEqual(self._eier('patients-app.js'), 'patients')
        self.assertEqual(self._eier('static/css/vaktliste.css'), 'vaktliste')
        self.assertIsNone(self._eier('portal-utils.js'),
                          'portal-utils.js eies av ingen modul og skal kunne '
                          'beskrives i rota')


class ModulfileneHarOgsaaEtTakTests(SimpleTestCase):
    """Delingen flyttet 574 linjer ut av rota og satte ikke noe tak på der de
    havnet.

    «Flytt det til modulfila» er et svar som virker helt til modulfila er den
    nye monolitten, og `vaktliste/CLAUDE.md` er 57 000 tegn — nesten like stor
    som rota var da den ble delt. Røykvarsleren hang i ett rom.
    """

    def _tegn(self, sti: str) -> int:
        return len((ROT / sti).read_text(encoding='utf-8'))

    def test_hver_modulfil_er_under_grensa(self) -> None:
        funn = []
        for sti in _modulfiler():
            tak = FOR_STORE_I_DAG.get(sti, MODUL_TEGNGRENSE)
            tegn = self._tegn(sti)
            if tegn >= tak:
                funn.append(f'{sti}: {tegn} tegn, taket er {tak}')
        self.assertEqual(funn, [], (
            'Modulfiler over taket:\n  ' + '\n  '.join(funn)
            + '\n\nEn modulfil som vokser uten grense er den gamle monolitten '
              'med en ny adresse. Del den, eller ta avgjørelsen om å heve taket '
              'i diffen.'))

    def test_unntakene_finnes_fortsatt(self) -> None:
        """En begrunnelse for en fil som er borte er bare støy."""
        forsvunnet = sorted(set(FOR_STORE_I_DAG) - set(_modulfiler()))
        self.assertEqual(forsvunnet, [],
                         f'FOR_STORE_I_DAG viser til filer som ikke finnes: {forsvunnet}')

    def test_unntakene_blir_ikke_slakke(self) -> None:
        """**Sperrehaken.** Et tak satt over dagens størrelse og glemt der, er
        et unntak som slutter å bety noe i det øyeblikket fila krymper. Taket
        skal følge fila nedover — ellers er «vi rydder i vaktlista» en jobb som
        kan gjøres halvveis uten at noe merker det."""
        slakke = []
        for sti, tak in sorted(FOR_STORE_I_DAG.items()):
            if sti not in _modulfiler():
                continue
            tegn = self._tegn(sti)
            if tegn < tak * 0.9:
                slakke.append(f'{sti}: {tegn} tegn, men taket står på {tak}')
        self.assertEqual(slakke, [], (
            'Disse takene er blitt slakke — senk dem til dagens størrelse, '
            'eller ta fila helt under MODUL_TEGNGRENSE og stryk unntaket:\n  '
            + '\n  '.join(slakke)))

    def _seksjoner(self, sti: str) -> list[tuple[str, int]]:
        """[(overskrift, tegn), ...] for hver `## `-seksjon i fila."""
        ut, naa = [], None
        for linje in (ROT / sti).read_text(encoding='utf-8').split('\n'):
            if linje.startswith('## '):
                naa = [linje[3:].strip(), 0]
                ut.append(naa)
            elif naa is not None:
                naa[1] += len(linje) + 1
        return [(navn, n) for navn, n in ut]

    def test_en_stor_modulfil_maa_ha_seksjoner(self) -> None:
        """**Regelen som ville fanget vaktlista i august.**

        Fila vokste til 707 linjer under én overskrift. Et flatt punktliste på
        den lengden har ingen steder ting «hører hjemme», så alt havner
        nederst — og ingen kan se hvilken del som vokser. Størrelsen var
        symptomet; fraværet av struktur var årsaken, og det er årsaken en vakt
        skal måle.
        """
        funn = []
        for sti in _modulfiler():
            if sti in UTEN_SEKSJONER_I_DAG:
                continue
            tegn = self._tegn(sti)
            if tegn < SEKSJONSKRAV_TEGN:
                continue
            antall = len(self._seksjoner(sti))
            if antall < MIN_SEKSJONER:
                funn.append(f'{sti}: {tegn} tegn, men {antall} seksjoner')
        self.assertEqual(funn, [], (
            f'Modulfiler over {SEKSJONSKRAV_TEGN} tegn uten minst '
            f'{MIN_SEKSJONER} `## `-seksjoner:\n  ' + '\n  '.join(funn)
            + '\n\nEn fil man ikke kan lete i, er en fil ingen finner regelen '
              'sin i — og uten seksjoner kan ingen se hvilken del som vokser.'))

    def test_ingen_enkeltseksjon_blir_en_monolitt(self) -> None:
        """Seksjoner uten tak er den forrige feilen med et hakk mer struktur:
        én seksjon som eter resten er en monolitt inni fila som nettopp ble
        delt."""
        funn = [f'{sti} → «{navn}»: {tegn} tegn'
                for sti in _modulfiler()
                for navn, tegn in self._seksjoner(sti)
                if tegn > SEKSJON_TEGNGRENSE]
        self.assertEqual(funn, [], (
            f'Seksjoner over {SEKSJON_TEGNGRENSE} tegn:\n  ' + '\n  '.join(funn)
            + '\n\nDel seksjonen, eller flytt det som egentlig er et eget tema.'))

    def test_unntakene_uten_seksjoner_finnes_fortsatt(self) -> None:
        """En begrunnelse for en fil som er borte — eller som *har* fått
        seksjoner — er bare støy, og skjuler at jobben er gjort."""
        feil = []
        for sti in sorted(UTEN_SEKSJONER_I_DAG):
            if sti not in _modulfiler():
                feil.append(f'{sti}: finnes ikke')
            elif len(self._seksjoner(sti)) >= MIN_SEKSJONER:
                feil.append(f'{sti}: har seksjoner nå — stryk unntaket')
        self.assertEqual(feil, [], '\n  '.join(feil))

    def test_regelen_finner_faktisk_seksjoner(self) -> None:
        """Sperrehake: leser `_seksjoner` feil, er begge reglene over grønne
        for alltid."""
        vaktliste = self._seksjoner('vaktliste/CLAUDE.md')
        self.assertGreaterEqual(len(vaktliste), MIN_SEKSJONER, vaktliste)
        self.assertTrue(all(tegn > 0 for _, tegn in vaktliste), vaktliste)

    def test_ingen_modulfil_er_uten_tak(self) -> None:
        """Sperrehake: finner ikke oppdagelsen noen filer, måler klassen
        ingenting."""
        self.assertGreaterEqual(len(_modulfiler()), 4)
