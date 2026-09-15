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

Størrelsesgrensa nederst er den svakeste regelen her, og det er med vilje at
det står: den måler linjer og ikke innhold, og den kan tilfredsstilles ved å
slette noe nyttig. Den er en røykvarsler for at delingen er i ferd med å
oppheve seg selv, ikke et budsjett.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.tests_dokumentråte import DOKUMENTER

ROT = Path(settings.BASE_DIR)

#: Rota skal ikke vokse tilbake til det den kom fra. Tallet er ikke hellig —
#: det er satt med rom over dagens fil, slik at en ny rammeverksregel får
#: plass mens et helt modulavsnitt ikke gjør det.
ROT_GRENSE = 1000

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
        linjer = len((ROT / 'CLAUDE.md').read_text(encoding='utf-8').split('\n'))
        self.assertLess(
            linjer, ROT_GRENSE,
            f'CLAUDE.md er {linjer} linjer. Hører det nye til én modul, flytt det '
            f'til modulfila; gjelder det alle, hev grensa bevisst.')
