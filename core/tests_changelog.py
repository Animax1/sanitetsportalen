"""Søkeordene i CHANGELOG må bety noe, ellers er de bare støy (17. sep. 2026).

Bakgrunnen er målt: arkivet er 11 651 linjer, og et temasøk drukner. «Rolle»
gir 84 entries som nevner ordet og seks som handler om det. Søkeordene finnes
for å gjøre det oppslaget mulig — og et søkeord som er skrevet feil, eller et
tema ingen bruker, gjør det motsatte: det får deg til å tro du har sett alt.

To regler, og de peker hver sin vei:

1. **Hvert søkeord i bruk er registrert.** Fanger `#vaktliste/planlegger` mot
   `#vaktliste/planlegging` — to temaer ingen ville lagt merke til at var ett,
   og det ene ville svart med halvparten av entriene.
2. **Hvert registrert søkeord er i bruk.** Speilet. Et tema ingen merker noe
   med er et tema som lover en oversikt det ikke finnes noe bak, og
   `--temaer` ville vist det med et tall som aldri ble annet enn null.

Samme arbeidsdeling som `KJENTE_UNNTAK` og sperrehakene rundt den: lista skal
kunne krympe av seg selv, ikke bli en samling gode intensjoner.
"""
from __future__ import annotations

import re

from django.test import SimpleTestCase

from core import changelog


class SokeordeneErRegistrerteTests(SimpleTestCase):

    def test_hvert_sokeord_i_bruk_staar_i_registeret(self) -> None:
        ukjente = changelog.ukjente()
        funn = [f'#{s}: {", ".join(t[:2])}' for s, t in sorted(ukjente.items())]
        self.assertEqual(funn, [], (
            'Søkeord brukt i CHANGELOG som ikke står i TEMAER:\n  '
            + '\n  '.join(funn)
            + '\n\nEr det en skrivefeil, rett den. Er det et nytt tema, før det '
              'opp i core/changelog.py med én linje om hva det dekker.'))

    def test_hvert_registrert_sokeord_er_i_bruk(self) -> None:
        """**Et tema uten entries lover en oversikt det ikke finnes noe bak.**

        Lista skal beskrive arkivet slik det er, ikke slik noen tenkte seg det.
        Feiler denne på et tema du nettopp la til, er svaret å merke entriene —
        ikke å stryke temaet.
        """
        self.assertEqual(changelog.ubrukte(), [], (
            'Registrerte søkeord ingen entry bruker:\n  '
            + '\n  '.join(f'#{s}' for s in changelog.ubrukte())
            + '\n\nMerk entriene som hører til, eller ta temaet ut av TEMAER.'))

    def test_appdelen_er_en_ekte_modul(self) -> None:
        """App-halvdelen utledes og skal ikke kunne finne på seg selv.

        Et `#vaktlister/roller` ville sett riktig ut i en overskrift og aldri
        blitt funnet av noen.
        """
        from django.apps import apps
        ekte = {a.label for a in apps.get_app_configs()}
        ukjente_apper = sorted(set(changelog.TEMAER) - ekte)
        self.assertEqual(ukjente_apper, [], (
            f'TEMAER navngir apper som ikke finnes: {ukjente_apper}'))


class OppslagetVirkerTests(SimpleTestCase):
    """Sperrehaker. Slutter parseren å treffe, går reglene over grønne på en
    tom liste — altså nøyaktig når arkivet er umulig å slå opp i."""

    def test_parseren_finner_entriene(self) -> None:
        entries = changelog.entries()
        self.assertGreater(len(entries), 200, 'fant nesten ingen entries')
        self.assertTrue(all(e['dato'] and e['tittel'] for e in entries))

    def test_titlene_er_unike(self) -> None:
        """Overskriften er den andre mekanismen — den man peker med. Er to
        titler like, er pekeren tvetydig akkurat når den brukes."""
        titler = [e['tittel'] for e in changelog.entries()]
        dubletter = sorted({t for t in titler if titler.count(t) > 1})
        self.assertEqual(dubletter, [], f'duplikate titler: {dubletter}')

    def test_parseren_leser_soekeordene_ut_av_overskriften(self) -> None:
        """Søkeordet står i overskriftslinja, ikke under den, slik at ett
        `grep` gir dato, tittel og tema på én gang. Leses ikke halen, er alle
        entries umerkede og regel 1 er grønn for alltid."""
        self.assertGreater(len(changelog.sokeord_i_bruk()), 0,
                           'ingen entry bærer søkeord — leser parseren halen?')
        m = changelog.OVERSKRIFT.match(
            '## 2026-09-16 — En tittel  `#vaktliste/roller` `#core/tilgang`')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), 'En tittel')
        self.assertEqual(
            [f'{a}/{t}' for a, t in changelog.SOKEORD.findall(m.group(3))],
            ['vaktliste/roller', 'core/tilgang'])

    def test_en_tittel_uten_soekeord_leses_som_hele_tittelen(self) -> None:
        """Vern mot at halen spiser tittelen: de 277 umerkede entriene skal
        fortsatt ha tittelen sin."""
        m = changelog.OVERSKRIFT.match('## 2026-09-16 — En tittel uten søkeord')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), 'En tittel uten søkeord')
        self.assertEqual(m.group(3), '')

    def test_finn_avgrenser_faktisk(self) -> None:
        alle = len(changelog.entries())
        ett = len(changelog.finn('ko/skallet'))
        self.assertGreater(ett, 0, 'fant ingen entries på et søkeord i bruk')
        self.assertLess(ett, alle, 'filteret slipper gjennom alt')
