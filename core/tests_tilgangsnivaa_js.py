"""`nivaaMinst()` i portal-utils.js — tilgangsstigen i nettleseren.

**Minst, aldri lik** (28. sep. 2026). `openEdit()` på pasientsiden spurte
`=== 'skriv_full'`, og global admin — som får toppen av stigen, `skriv_leder`,
fra `nivaa_for` — fikk opprette pasienter, men ikke åpne dem. Serveren
sammenlignet riktig med rang (`har_tilgang`); bare nettleseren var feil.

Stigen står derfor to steder, i Python og i JS, og denne fila krever at de er
like: kommer et trinn til i `NIVAA_HIERARKI` uten å komme hit, ville det nye
nivået stille gitt «ingen tilgang» i hver knappegate.
"""
from __future__ import annotations

import itertools
import json
import unittest

from django.test import SimpleTestCase

from core.auth_decorators import NIVAA_HIERARKI
from patients.js_test_utils import PORTAL_UTILS_JS, build_harness, node_available, run_node


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class NivaaMinstTests(SimpleTestCase):

    def setUp(self):
        self.harness = build_harness([(PORTAL_UTILS_JS, ('nivaaMinst',))])

    def _kall(self, tilgang, modul, nivaa):
        ut = run_node(self.harness, f'''
          console.log(JSON.stringify(nivaaMinst({json.dumps(tilgang)}, {json.dumps(modul)}, {json.dumps(nivaa)})));
        ''')
        return json.loads(ut.splitlines()[0])

    def test_stigen_er_den_samme_som_serverens(self):
        """Hvert par (har, kreves) gir det `har_tilgang` ville gitt."""
        nivaaer = list(NIVAA_HIERARKI)
        par = list(itertools.product(nivaaer, repeat=2))
        # Ett node-kall for alle parene — 25 prosesser er seint.
        kall = ', '.join(
            f'nivaaMinst({{m: {json.dumps(har)}}}, "m", {json.dumps(kreves)})'
            for har, kreves in par)
        ut = run_node(self.harness, f'''
          console.log(JSON.stringify([{kall}]));
        ''')
        fasit = [NIVAA_HIERARKI[har] >= NIVAA_HIERARKI[kreves] for har, kreves in par]
        self.assertEqual(json.loads(ut.splitlines()[0]), fasit)

    def test_hoyere_niva_slipper_gjennom(self):
        """Feilen fra 28. sep.: `skriv_leder` er mer enn `skriv_full`, ikke noe annet."""
        self.assertIs(self._kall({'patients': 'skriv_leder'}, 'patients', 'skriv_full'), True)

    def test_ingen_rad_ukjent_niva_og_ukjent_krav_stenger(self):
        self.assertIs(self._kall({}, 'patients', 'les'), False)
        self.assertIs(self._kall({'patients': 'guru'}, 'patients', 'les'), False)
        self.assertIs(self._kall({'patients': 'skriv_leder'}, 'patients', 'skriv_alt'), False)

    def test_annen_moduls_niva_teller_ikke(self):
        self.assertIs(self._kall({'backlog': 'skriv_leder'}, 'patients', 'les'), False)

    def test_manglende_tilgang_stenger(self):
        """En side uten `MODUL_TILGANG` sender `undefined`."""
        ut = run_node(self.harness, 'console.log(JSON.stringify(nivaaMinst(undefined, "m", "les")));')
        self.assertEqual(ut.splitlines()[0], 'false')

    def test_admin_flagget_maa_vaere_literal_true(self):
        self.assertIs(self._kall({'admin': True}, 'patients', 'skriv_leder'), True)
        self.assertIs(self._kall({'admin': 'false'}, 'patients', 'les'), False)
