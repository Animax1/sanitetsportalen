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
    # 55 743 tegn (~17 000 tokens) 17. sep. 2026 — større enn `oppdrag`,
    # `patients`, `statistikk` og `ko` til sammen, ganger to. Fila er ikke
    # dårlig skrevet; den beskriver portalens største modul. Men den har vokst
    # uten tak siden den ble skilt ut, og den skal deles etter samme regel som
    # rota ble: planlegging, drift og registre er tre ting. Se `TODO.md`.
    'vaktliste/CLAUDE.md': 55_800,
}

#: En tabellrad i rota som navngir en moduls egen fil skal være et *oppslag*,
#: ikke en beskrivelse. Grensa er satt godt over dagens bredeste rad (122 tegn)
#: og godt under de to som utløste regelen (888 og 652).
RAD_TEGNGRENSE = 200

#: `patients-app.js` -> `patients`, `static/css/vaktliste.css` -> `vaktliste`.
#: Eierskapet **utledes**, det står ikke i en liste: en ny modul med en ny fil
#: skal dekkes fra dagen den finnes, og en håndholdt liste forfaller i stillhet.
FILNAVN = re.compile(r'`([A-Za-z0-9_./*-]+\.(?:js|css|py|html))`')

#: Raden i tabellen «Hvor dokumentasjonen bor».
TABELLRAD = re.compile(r'^\|\s*`([a-z_]+/CLAUDE\.md)`\s*\|', re.M)

#: `### Vaktlistemodulen (vaktliste/)` — et avsnitt som har en modul som subjekt.
MODULOVERSKRIFT = re.compile(r'^#{1,4} .*\(([a-z_]+)/\)', re.M)


def _modulfiler() -> list[str]:
    """Hver `<app>/CLAUDE.md` som finnes, som sti fra rota."""
    return sorted(f'{p.parent.name}/CLAUDE.md' for p in ROT.glob('*/CLAUDE.md'))


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
        har_egen_fil = {s.split('/')[0] for s in _modulfiler()}
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
        for app in (s.split('/')[0] for s in _modulfiler()):
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

    def test_ingen_modulfil_er_uten_tak(self) -> None:
        """Sperrehake: finner ikke oppdagelsen noen filer, måler klassen
        ingenting."""
        self.assertGreaterEqual(len(_modulfiler()), 4)
