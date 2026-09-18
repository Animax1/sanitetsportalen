"""Sidene uten bundler er delt i flere filer — og delingen må holde.

`vaktliste.js` var 3 801 linjer og `oppdrag-sentral.js` 1 991 da de ble delt
14. sep. 2026 (gjeldspunkt 3.6). Det finnes ingen bundler: filene lastes med
hver sin `<script>`-tagg og deler **ett globalt navnerom**, akkurat som før.

Det gjør delingen billig — og gjør tre feil mulige som ikke fantes før:

1. **En funksjon faller mellom to filer** ved neste flytting, og siden feiler
   først når noen klikker på akkurat den knappen.
2. **En funksjon dupliseres**, og den sist lastede vinner i stillhet.
3. **Rekkefølgen i malen kommer i utakt** med det koden forutsetter.

Alle tre er usynlige for resten av suiten: den kjører funksjonene gjennom
`build_harness`, som klipper dem ut av kilden uansett hvilken fil de ligger i.

## Om rekkefølgen

Regelen er ikke «all tilstand i den første fila» — det er ikke sant, og et
krav ingen holder er verre enn ingen. `let`/`const` på toppnivå er
*skript-scopede*, altså delt mellom filene, og en temporal dead zone treffes
bare hvis noe **kjører** før bindingen er nådd.

Den ekte regelen er derfor: **alt som kjører på toppnivå står i den siste
fila.** I praksis er det `DOMContentLoaded`-krokene. Testen håndhever det.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

from core import maltekst
from django.test import SimpleTestCase

from patients.js_test_utils import KO_JS, OPPDRAG_SENTRAL_JS, VAKTLISTE_JS

#: (konstant, malen som laster dem). Rekkefølgen i konstanten er
#: lasterekkefølgen, og malen må si det samme.
SIDER = [
    (VAKTLISTE_JS, 'templates/vaktliste/index.html'),
    (OPPDRAG_SENTRAL_JS, 'templates/oppdrag/sentral.html'),
    (KO_JS, 'templates/ko/index.html'),
]

FUNKSJON = re.compile(r'^(?:async\s+)?function\s+(\w+)', re.M)
BINDING = re.compile(r'^(let|const|var)\s+\w+')


def _toppnivaa_som_kjorer(kilde: str) -> list[str]:
    """Linjer som faktisk kjører på toppnivå.

    Dybden teller **alle tre** parentestyper. Med bare klammeparenteser ble
    fortsetteselslinjene i en flerlinjes array-literal lest som toppnivåkode —
    en `const X = [\n  ['a', 'b'],\n];` ga falskt utslag på den midterste
    linja. Erklæringen står jo i en `const`, og den er ikke kode som kjører.
    """
    ut, dybde = [], 0
    for linje in kilde.split('\n'):
        s = linje.strip()
        if (dybde == 0 and s
                and not s.startswith(('//', '*', '/*', '}', ')', ']', "'", '"'))
                and not re.match(r'^(let|const|var|function|async function)\b', s)):
            ut.append(s)
        for aapen, lukk in (('{', '}'), ('[', ']'), ('(', ')')):
            dybde += linje.count(aapen) - linje.count(lukk)
    return ut


class JsSplittenErKompletTests(SimpleTestCase):

    def test_ingen_funksjon_er_duplisert(self) -> None:
        """Den sist lastede ville vunnet, uten at noe feilet."""
        for filer, _ in SIDER:
            navn = []
            for sti in filer:
                navn += FUNKSJON.findall(Path(sti).read_text(encoding='utf-8'))
            dubletter = sorted({n for n in navn if navn.count(n) > 1})
            with self.subTest(side=Path(filer[0]).name):
                self.assertEqual(dubletter, [])

    def test_malen_laster_alle_filene_i_riktig_rekkefolge(self) -> None:
        """Rekkefølgen i `js_test_utils` er den testene bruker; rekkefølgen i
        malen er den nettleseren bruker. Går de i utakt, prøver vi én
        rekkefølge og leverer en annen."""
        rot = Path(settings.BASE_DIR)
        for filer, mal in SIDER:
            with self.subTest(mal=mal):
                # **Med det malen inkluderer.** Sentralbordets skript ligger
                # i `oppdrag/_sentralbord_skript.html` fra 18. sep. 2026, og
                # en vakt som bare leser sidefila ble blind uten å bli rød.
                tekst = maltekst.les(Path(rot, mal))
                i_malen = re.findall(r"\{%\s*static\s*'js/([\w.-]+\.js)'\s*%\}", tekst)
                forventet = [Path(f).name for f in filer]
                # Malen laster også `portal-utils.js` m.fl.; vi ser bare på våre.
                self.assertEqual([n for n in i_malen if n in set(forventet)],
                                 forventet)

    def test_bare_den_siste_fila_kjorer_noe_paa_toppnivaa(self) -> None:
        """Regelen som holder rekkefølgen trygg — se modulens docstring.

        Kjører en tidlig fil noe på toppnivå, kan den lese en binding som
        ikke er nådd ennå, og siden dør på en `ReferenceError` før noe er
        tegnet. Erklæringer er derimot fritt fram: de er skript-scopede og
        deles mellom filene.
        """
        for filer, _ in SIDER:
            for sti in filer[:-1]:
                with self.subTest(fil=Path(sti).name):
                    kjorer = _toppnivaa_som_kjorer(
                        Path(sti).read_text(encoding='utf-8'))
                    # Fortsettelseslinjer i array-literaler er ikke kode som
                    # kjører; de begynner med en apostrof eller klammeparentes
                    # og er filtrert i `_toppnivaa_som_kjorer`.
                    self.assertEqual(
                        kjorer, [],
                        f'{Path(sti).name} kjører noe på toppnivå. Flytt det '
                        f'til {Path(filer[-1]).name}, som lastes sist.')

    def test_de_gamle_samlefilene_er_borte(self) -> None:
        """Blir en av dem liggende, laster malen den nye mens noen leser den
        gamle — og de to driver fra hverandre i stillhet."""
        rot = Path(settings.BASE_DIR, 'static', 'js')
        for navn in ('vaktliste.js', 'oppdrag-sentral.js'):
            with self.subTest(fil=navn):
                self.assertFalse((rot / navn).exists())

    def test_hver_del_er_mindre_enn_den_var(self) -> None:
        """Hele poenget med delingen. Uten dette kunne én fil vokse tilbake
        til 3 800 linjer mens de andre står tomme, og testene over ville
        fortsatt vært grønne."""
        for filer, _ in SIDER:
            for sti in filer:
                with self.subTest(fil=Path(sti).name):
                    linjer = len(Path(sti).read_text(encoding='utf-8').splitlines())
                    self.assertLess(linjer, 1800,
                                    'del fila videre langs seksjonsmarkørene')
