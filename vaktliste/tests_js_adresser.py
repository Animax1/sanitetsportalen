"""Hver `/vaktliste/`-adresse i JS-filene må finnes i `urls.py` (30. sep. 2026).

Ordbok-byttet i pulje 3 gjorde `/vaktliste/api/ressurser/…` til `/api/enheter/…` i
seks kall, og **ingen test ble rød**: node-testene stubber `apiFetch`, og ingenting
sammenlignet adressene med rutene. På staging ville hvert kall mot en enhet gitt
404 — lagre, fjerne, sette opp skift, pauser. Feilen ble fanget ved å lese diffen.

Testen tar hver streng- og mal-litteral som begynner med `/vaktliste/`, setter `1`
for hvert `${...}`, og slår adressen opp med `resolve()`. En adresse bygget med `+`
leses bare til første skjøt — den delen må likevel finnes som prefiks til en rute.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

ROT = Path(settings.BASE_DIR)
LITTERAL = re.compile(r"""(['"`])(/vaktliste/[^'"`]*)\1""")

#: Litteraler som er prefikser og ikke adresser, med grunnen.
PREFIKSER = {
    '/vaktliste/api/': 'vaktliste-sw.js kjenner igjen API-kall på prefikset (`avgjor()`)',
}


def _registerstier(kilde):
    """`${reg.sti}` er navnet på et register — `korps` eller `kompetanser` i
    `VERDIREGISTRE`. Settes inn med de ekte verdiene, ikke med `1`."""
    return re.findall(r"\bsti:\s*'([a-z_]+)'", kilde)


def adresser():
    kilde = {f.name: f.read_text(encoding='utf-8')
             for f in sorted((ROT / 'static/js').glob('vaktliste-*.js'))}
    stier = _registerstier(''.join(kilde.values()))
    ut = []
    for navn, src in kilde.items():
        for m in LITTERAL.finditer(src):
            rå = m.group(2).split('?')[0]
            varianter = [rå.replace('${reg.sti}', s) for s in stier] if '${reg.sti}' in rå else [rå]
            # Et `${...}` helt til slutt, etter siste `/`, er et tillegg — i praksis en
            # spørrestreng bygget for seg (`${korps}` = `?korps=3` i `lastBelastning`).
            varianter = [re.sub(r'(?<=/)\$\{[^}]*\}$', '', v) for v in varianter]
            ut.extend((navn, re.sub(r'\$\{[^}]*\}', '1', v)) for v in varianter)
    return ut


def finnes(sti):
    if sti in PREFIKSER:
        return True
    try:
        resolve(sti)
        return True
    except Resolver404:
        return False


class JsAdresseneFinnesTests(SimpleTestCase):

    def test_hver_adresse_finnes(self):
        mangler = [f'{fil}: {sti}' for fil, sti in adresser() if not finnes(sti)]
        self.assertEqual(mangler, [], 'Adresser i JS som ingen rute svarer på:\n'
                         + '\n'.join(mangler))

    def test_testen_ser_adressene(self):
        """Finner den ingen, er det regexen som har sluttet å lese — ikke koden som er ren."""
        stier = {sti for _, sti in adresser()}
        self.assertIn('/vaktliste/api/ressurser/1/', stier)
        self.assertIn('/vaktliste/api/kompetanser/1/', stier, 'registerstiene settes inn')
        self.assertGreaterEqual(len(stier), 15)

    def test_en_feil_adresse_blir_fanget(self):
        self.assertFalse(finnes('/vaktliste/api/enheter/1/'))
