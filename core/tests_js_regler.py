"""Portalvide JS-regler som ikke hører til én modul.

Filene i `static/js/` deler ett globalt navnerom og ett sett hjelpere fra
`portal-utils.js`. Reglene her gjelder alle sammen, og hver av dem står her
fordi den er brutt minst én gang i prod.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from patients.js_test_utils import uten_js_kommentarer as _uten_kommentarer

JS_MAPPE = Path(settings.BASE_DIR) / 'static' / 'js'

#: Navnet står **ett** sted. Mønstrene under bygges av det, og
#: `test_regelen_peker_paa_en_hjelper_som_finnes` krever at det finnes i
#: `portal-utils.js`. Uten den koblingen kunne mønsteret lete etter et navn
#: som ikke er der: regelen ville vært grønn for alltid, og voktet ingenting.
#: (Mutanten «regelen leter etter feil navn» overlevde til dette var på
#: plass — 16. sep. 2026.)
HJELPER = 'trustedHtml'
I_MALSTRENG = re.compile(r'\$\{[^}]*\b' + HJELPER + r'\(')
MED_PLUSS = re.compile(r'(\+\s*' + HJELPER + r'\(|' + HJELPER + r'\([^;]*?\)\s*\+)')

class KommentarfjerningenTests(SimpleTestCase):
    """`uten_js_kommentarer()` er den ene alle JS-skannerne bruker. Faller den
    tilbake til «bare linjer som begynner med `//`», ser ingen skanner det."""

    def test_kommentar_bak_kode_fjernes(self):
        self.assertEqual(_uten_kommentarer("let a = 1;  // kall('x')"), 'let a = 1;  ')

    def test_blokkommentar_fjernes_og_linjene_blir(self):
        ut = _uten_kommentarer("a();\n/* kall('x')\n   og mer */\nb();")
        self.assertNotIn('kall', ut)
        self.assertEqual(ut.count('\n'), 3, 'linjenumrene i funnene skal stemme')

    def test_url_og_strek_i_blokk(self):
        self.assertEqual(_uten_kommentarer("fetch('https://x.no/a');"), "fetch('https://x.no/a');")
        self.assertEqual(_uten_kommentarer('/* a // b */c();'), 'c();')


class TrustedHtmlBrukesIkkeIMalstrengTests(SimpleTestCase):
    """**`trustedHtml()` er ikke en escaper — den er et merkelapp-objekt.**

    Den returnerer `{__trustedHtml: '…'}`, som `cellHtml()` pakker ut når en
    Tabulator-celle skal ta imot markup vi har bygget selv. I en mal-streng
    blir objektet til `[object Object]`, og — dette er det lumske —
    `trustedHtml('')` er et objekt like fullt, så **den tomme grenen viser det
    også**. Feilen rammer da hver rad, ikke bare den ene som skulle hatt
    merket, og ser derfor ut som noe helt annet enn den er.

    To ganger i prod:

    - «Rett tid» viste ingenting fra fase 3 til 11. sep. 2026.
    - Hver enhet i ressurslista sto som «Haugesund 56[object Object]»
      16. sep. 2026, meldt fra staging av André.

    Etter den første ble advarselen skrevet som en kommentar ved det ene
    kallstedet. Fem dager senere gikk jeg i den samme fella 500 linjer unna, i
    en annen fil. **En advarsel som bare finnes der feilen alt er rettet,
    advarer ingen** — derfor står regelen her, der den gjelder alle filene.

    Skal markup du har bygget selv inn i en mal-streng, interpolér strengen
    rått og før uttrykket opp i `REVIEWED_INTERPOLATIONS` i modulens
    XSS-skanner med en begrunnelse. Det er der noen faktisk leser den.
    """

    def _filer(self):
        return sorted(JS_MAPPE.glob('*.js'))

    def test_ingen_fil_interpolerer_trustedhtml_i_en_malstreng(self):
        funn = []
        for fil in self._filer():
            kilde = _uten_kommentarer(fil.read_text(encoding='utf-8'))
            for treff in I_MALSTRENG.finditer(kilde):
                linje = kilde[:treff.start()].count('\n') + 1
                funn.append(f'{fil.name}:{linje}')
        self.assertEqual(funn, [], (
            'trustedHtml() interpolert i en mal-streng:\n  ' + '\n  '.join(funn)
            + '\n\nDen returnerer et objekt for cellHtml(), ikke en streng, og '
              'blir til «[object Object]» — også i den tomme grenen. '
              'Interpolér strengen rått og før uttrykket opp i '
              'REVIEWED_INTERPOLATIONS i modulens XSS-skanner.'))

    def test_ingen_fil_skjoter_trustedhtml_med_pluss(self):
        """Samme feil, annen syntaks. Uten denne flytter den bare på seg."""
        funn = []
        for fil in self._filer():
            kilde = _uten_kommentarer(fil.read_text(encoding='utf-8'))
            for treff in MED_PLUSS.finditer(kilde):
                linje = kilde[:treff.start()].count('\n') + 1
                funn.append(f'{fil.name}:{linje}')
        self.assertEqual(funn, [], (
            'trustedHtml() skjøtet med + :\n  ' + '\n  '.join(funn)))

    def test_regelen_peker_paa_en_hjelper_som_finnes(self):
        """**Sperrehaken, og den var ikke sterk nok først.**

        En regel som leter etter et navn som ikke finnes, er grønn for alltid.
        Mutanten som byttet `trustedHtml` mot `trustedHtmlXX` *inne i mønsteret*
        overlevde den første utgaven: den sjekket at helperen fantes, men ikke
        at mønsteret var rettet mot den.

        Nå bygges begge mønstrene av `HJELPER`, og denne krever at navnet
        finnes i `portal-utils.js` **og** at mønstrene faktisk slår ut på en
        kjent-dårlig bit kode. Da er det ingen vei til en grønn regel som ikke
        vokter noe.
        """
        utils = (JS_MAPPE / 'portal-utils.js').read_text(encoding='utf-8')
        self.assertIn(f'function {HJELPER}(', utils)
        self.assertIn('__trustedHtml', utils, 'cellHtml() pakker den ut på dette feltet')
        self.assertTrue(I_MALSTRENG.search('`<b>${%s(x)}</b>`' % HJELPER),
                        'mønsteret kjenner ikke igjen sin egen feil')
        self.assertTrue(MED_PLUSS.search("'<b>' + %s(x)" % HJELPER),
                        'pluss-mønsteret kjenner ikke igjen sin egen feil')
        self.assertIsNone(I_MALSTRENG.search('`<b>${escapeHtml(x)}</b>`'),
                          'mønsteret slår ut på riktig kode')
        brukere = [f.name for f in self._filer()
                   if f.name != 'portal-utils.js'
                   and 'trustedHtml(' in _uten_kommentarer(f.read_text(encoding='utf-8'))]
        self.assertTrue(brukere, 'ingen bruker helperen — da måler reglene over ingenting')


class GlobalTilstandSkyggerIkkeEnFunksjonTests(SimpleTestCase):
    """`globalThis.navn = …` der `navn` er en funksjon på toppnivå (19. okt. 2026).

    **I nettleseren er en toppnivåfunksjon en egenskap på `globalThis`**, så
    tilordningen overskriver funksjonen — og neste kall kaster «is not a function».
    `posisjonIntervallS` gjorde nøyaktig det: første poll la tallet der funksjonen
    sto, `lastMine()` døde før den tegnet, og bilen sto på «Laster…» uten oppdrag.
    Harnessene i node la ikke funksjonene på `globalThis`, så alle testene var
    grønne. Regelen leser alle filene samlet, fordi filene på en side deler ett
    navnerom.
    """

    def test_ingen_tilordning_paa_globalThis_treffer_en_funksjon(self):
        rot = Path(settings.BASE_DIR, 'static', 'js')
        filer = {f.name: _uten_kommentarer(f.read_text(encoding='utf-8'))
                 for f in sorted(rot.glob('*.js'))}
        funksjoner = {}
        for navn, kilde in filer.items():
            for fn in re.findall(r'^(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)', kilde, re.M):
                funksjoner.setdefault(fn, []).append(navn)
        funn = [f'{navn}: globalThis.{felt} = … (funksjon i {", ".join(funksjoner[felt])})'
                for navn, kilde in filer.items()
                for felt in sorted(set(re.findall(r'globalThis\.([A-Za-z_$][\w$]*)\s*=(?!=)', kilde)))
                if felt in funksjoner]
        self.assertEqual(funn, [], 'Gi tilstanden et eget navn — tilordningen overskriver funksjonen i nettleseren')
