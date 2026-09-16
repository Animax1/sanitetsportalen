"""`TODO.md` er arbeidslista, og den forfaller på to måter som ikke synes.

Begge reglene her sto som prosa i `CLAUDE.md` før de sto som tester, og begge
ble brutt mens prosaen var grønn. Det er samme lærdom som
`core/tests_avhengighetsretning.py`: en regel ingen kan bryte uten at noe blir
rødt, er det eneste slaget regel som holder.

**Arbeidsdelingen mot CHANGELOG er avgjort** (André, 16. sep. 2026): «vi
sletter. Du skal jo legge inn hva du gjorde i CHANGELOG, og det som står i TODO
og det som ble gjort kan bli to ting med forskjellig vri. **CHANGELOG blir
arkivets sannhet.**» Derfor beskriver `TODO.md` bare det som gjenstår; et punkt
krysses ikke av, det fjernes når CHANGELOG har historien.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TODO = Path(settings.BASE_DIR) / 'TODO.md'

#: Seksjonen som er sann liste over hva som venter på André.
ANDRE_SEKSJON = '## ⚠️ Krever Andre — kan ikke gjøres fra kodebasen'

#: Et punkt som venter på André. Begge formene er i bruk i fila.
VENTER_PAA_ANDRE = re.compile(r'\*\*(Krever Andre|André)\b', re.I)

_PUNKT = re.compile(r'^(\s*)- \[([ x])\]')


def _punkter():
    """`[(linjenr, innrykk, merke, seksjon, tekst), ...]` for hvert punkt."""
    ut, seksjon = [], ''
    for nr, linje in enumerate(TODO.read_text(encoding='utf-8').split('\n'), 1):
        if linje.startswith('## '):
            seksjon = linje.strip()
        m = _PUNKT.match(linje)
        if m:
            ut.append((nr, len(m.group(1)), m.group(2), seksjon, linje.strip()))
    return ut


class TodoForfallerIkkeTests(SimpleTestCase):

    def test_ingen_aapne_punkter_under_et_avkrysset(self):
        """**Regelen sto i `CLAUDE.md` fra 14. sep. 2026, da det var to.**

        16. sep. var det **23** — og seks av dem var punkter som ventet på
        André. De sto altså usynlige i den ene fila som skal fortelle ham hva
        han må gjøre. To av de 23 ble lagt der dagen før, av meg, i en fil jeg
        leser hver økt.

        Det er hele poenget: prosaen hindret ingenting, fordi ingenting ble
        rødt. Krysses en forelder av, skal de uavkryssede barna løftes ut —
        og **skrives om så de står på egne bein**, for et barn henter ofte
        meningen sin fra forelderen.
        """
        stabel, funn = [], []
        for nr, inn, merke, _seksjon, tekst in _punkter():
            while stabel and stabel[-1][0] >= inn:
                stabel.pop()
            if merke == ' ' and stabel and stabel[-1][1] == 'x':
                funn.append(f'  linje {nr}: {tekst[:70]}')
            stabel.append((inn, merke))
        self.assertEqual(funn, [], (
            'Åpne punkter står under et avkrysset punkt i TODO.md:\n'
            + '\n'.join(funn)
            + '\n\nLøft dem ut til en synlig bolk, og skriv dem om så de gir '
              'mening uten forelderen.'))

    def test_alt_som_venter_paa_andre_staar_i_andre_seksjonen(self):
        """**Den ene lista han skal kunne stole på.**

        Seks punkter merket «Krever Andre» lå spredt i fila 16. sep. 2026,
        blant dem verifiseringen av Scaleway-kortet og staging-lista fra
        samme dag — altså nøyaktig det han var bedt om å gjøre, plassert der
        han ikke ser det.

        Et punkt som venter på et menneske er verdiløst om mennesket ikke
        finner det. Står det i seksjonen øverst, er toppen av fila et svar på
        «hva venter på meg?».

        **Og «Krever Andre» betyr «blokkerer nå».** Et åpent valg inne i en
        upåbegynt idé er ikke det — det besvares når ideen tas opp. Merkes slikt
        likevel, fylles toppen av fila med ting han ikke kan gjøre noe med, og
        da slutter han å stole på den. Formuler det som «Åpent valg» i stedet;
        datteroppdrag-punktet er mønsteret.
        """
        feil = [f'  linje {nr}: [{seksjon[:40]}] {tekst[:60]}'
                for nr, _inn, merke, seksjon, tekst in _punkter()
                if merke == ' ' and VENTER_PAA_ANDRE.search(tekst)
                and seksjon != ANDRE_SEKSJON]
        self.assertEqual(feil, [], (
            'Punkter som venter på André står utenfor «Krever Andre»:\n'
            + '\n'.join(feil)
            + f'\n\nFlytt dem til «{ANDRE_SEKSJON}».'))

    def test_regelen_kjenner_igjen_sin_egen_feil(self):
        """**Sperrehaken.** Begge reglene over er grønne av seg selv hvis
        mønstrene deres slutter å treffe noe — og en vakt som ikke kan bli
        rød, vokter ingenting. Samme grep som `core/tests_js_regler.py`.
        """
        self.assertTrue(_PUNKT.match('  - [ ] noe'))
        self.assertTrue(_PUNKT.match('- [x] noe'))
        self.assertTrue(VENTER_PAA_ANDRE.search('- [ ] **Krever Andre:** gjør X'))
        self.assertTrue(VENTER_PAA_ANDRE.search('- [ ] **André:** gjør X'))
        self.assertIsNone(VENTER_PAA_ANDRE.search('- [ ] rett en bug'))
        self.assertIn(ANDRE_SEKSJON, TODO.read_text(encoding='utf-8'),
                      'seksjonen den andre testen peker på må finnes')

    def test_ingen_avkryssede_punkter_i_det_hele_tatt(self):
        """**Konsekvensen av at CHANGELOG er arkivets sannhet.**

        Er et punkt gjort, står historien i CHANGELOG og punktet skal bort.
        Et `[x]` her er derfor alltid feil — og det er dessuten forutsetningen
        for regelen over: finnes ingen avkryssede foreldre, kan ingenting
        begraves under dem.

        Den fanget meg innen timen. Punkt 1 i pulje 3 ble levert 16. sep. 2026,
        og jeg krysset det av — i en fil hvis egen topp sier at ferdige punkter
        slettes, i en regel jeg hadde skrevet samme dag. Vanen sitter i
        fingrene lenge etter at regelen er bestemt; det er nettopp det tester er
        til for.
        """
        funn = [f'  linje {nr}: {tekst[:70]}'
                for nr, _inn, merke, _seksjon, tekst in _punkter() if merke == 'x']
        self.assertEqual(funn, [], (
            'Avkryssede punkter i TODO.md:\n' + '\n'.join(funn)
            + '\n\nSlett dem. Historien hører hjemme i CHANGELOG.'))

    def test_ingen_ferdig_seksjon(self):
        """CHANGELOG er arkivets sannhet (André, 16. sep. 2026). En
        «Ferdig»-seksjon i arbeidslista er en andre sannhet med en annen vri —
        og da er det to kilder som glir fra hverandre. Den som sto der hadde
        i tillegg fire *åpne* punkter i seg, under en overskrift som het
        «Ferdig»."""
        self.assertNotIn('\n## Ferdig', TODO.read_text(encoding='utf-8'))
