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

# `//`-kommentarer og `/* */`. Samme grep som `oppdrag/tests_xss.py`: en regel
# som leser sin egen prosa måler at noen har skrevet om begrunnelsen.
_LINJE = re.compile(r'(?<!:)//[^\n]*')
_BLOKK = re.compile(r'/\*.*?\*/', re.S)


def _uten_kommentarer(kilde: str) -> str:
    return _LINJE.sub('', _BLOKK.sub('', kilde))


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
