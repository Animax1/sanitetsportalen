"""Hvem får åpne en pasient for redigering — `openEdit()` i patients-forms.js.

Meldt fra staging og prod 28. sep. 2026: «Du får opprette pasienter men ikke
redigere når du trykker på dem» — i lista og på tavla, som begge kaller
`openEdit()`. Gaten spurte `=== 'skriv_full'`, og global admin har
`skriv_leder`. Serveren slapp admin inn; knappen gjorde det ikke.

**Nivået hentes fra serveren, ikke skrives av.** Testen spør `nivaa_for()` hva
en ekte admin og en ekte skriver får, og sender *det* gjennom gaten — slik
malen gjør med `MODUL_TILGANG`. Hadde testen skrevet `'skriv_full'` for admin,
ville den bestått med feilen i behold, og det var nettopp den antakelsen som
var feil.
"""
from __future__ import annotations

import json
import unittest

from django.test import TestCase

from accounts.models import CustomUser
from accounts.test_helpers import gi_standardtilgang
from core.auth_decorators import nivaa_for
from patients.js_test_utils import (FORMS_JS, PORTAL_UTILS_JS, build_harness,
                                    node_available, run_node)

#: Det `openEdit()` rører utenom gaten, stubbet. `aapnet` er målet: kom kallet
#: helt fram til `bsEdit.show()`?
PREAMBLE = '''
let currentEditId = null;
let aapnet = false;
const bsEdit = { show() { aapnet = true; } };
const _el = () => ({ value: '', textContent: '', style: {},
                     classList: { toggle() {} } });
globalThis.document = { getElementById: _el, querySelectorAll: () => [] };
function _ensurePlasseringOption() {}
function _populateForstehjelperDropdown() {}
function _populateHelsepersonellDropdown() {}
function updatePlasseringDropdownState() {}
function updateTotal() {}
'''


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class OpenEditGatenTests(TestCase):

    def setUp(self):
        self.harness = build_harness([
            (PORTAL_UTILS_JS, ('nivaaMinst',)),
            (FORMS_JS, ('openEdit',)),
        ])

    def _aapnes_for(self, nivaa):
        ut = run_node(self.harness, f'''
          globalThis.window = {{ MODUL_TILGANG: {{ patients: {json.dumps(nivaa or '')} }} }};
          openEdit({{ id: 7, patient_nr: 7 }});
          console.log(JSON.stringify(aapnet));
        ''', preamble=PREAMBLE)
        return json.loads(ut.splitlines()[0])

    def _bruker(self, navn, profil=None, **felt):
        bruker = CustomUser.objects.create_user(username=navn, password='x-Passord-123!', **felt)
        if profil:
            gi_standardtilgang(bruker, profil)
        return bruker

    def test_global_admin_aapner_pasienten(self):
        """Feilen: admin får `skriv_leder`, og det er mer enn `skriv_full`."""
        admin = self._bruker('admin', role='admin')
        self.assertEqual(nivaa_for(admin, 'patients'), 'skriv_leder')
        self.assertIs(self._aapnes_for(nivaa_for(admin, 'patients')), True)

    def test_skriver_aapner_pasienten(self):
        skriver = self._bruker('skriver', 'skriver')
        self.assertIs(self._aapnes_for(nivaa_for(skriver, 'patients')), True)

    def test_leser_aapner_ikke(self):
        """`les` fikk tidligere åpne skjemaet og møtte 403 først på lagre."""
        leser = self._bruker('leser', 'leser')
        self.assertEqual(nivaa_for(leser, 'patients'), 'les')
        self.assertIs(self._aapnes_for(nivaa_for(leser, 'patients')), False)

    def test_uten_tilgang_aapner_ikke(self):
        self.assertIs(self._aapnes_for(None), False)
