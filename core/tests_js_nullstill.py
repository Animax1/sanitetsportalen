"""`nullstillFelter()` i portal-utils.js (19. sep. 2026): skjemaer som åpnes med
`data-bs-toggle` skal ikke huske et avvist forsøk. Regelen prøves mot et
minimalt DOM, ikke ved å lese kildelinjer (CLAUDE.md, «Frontend»)."""
from __future__ import annotations

import unittest

from django.test import SimpleTestCase

from patients.js_test_utils import PORTAL_UTILS_JS, build_harness, node_available, run_node


@unittest.skipUnless(node_available(), 'node er ikke tilgjengelig')
class NullstillFelterTests(SimpleTestCase):

    STUBB = """
        const felter = {
          navn: { tagName: 'INPUT', type: 'text', value: 'forsøk', defaultValue: '', classList: { remove(k) { this.fjernet = k; } } },
          notat: { tagName: 'TEXTAREA', type: 'textarea', value: 'forsøk', defaultValue: 'standard' },
          valg: { tagName: 'SELECT', selectedIndex: 2 },
          kryss: { tagName: 'INPUT', type: 'checkbox', checked: false, defaultChecked: true },
          feil: { textContent: 'Navn kan ikke være tomt.', classList: { add(k) { this.lagt = k; } } },
        };
        globalThis.document = { getElementById: (id) => felter[id] || null };
        nullstillFelter(['navn', 'notat', 'valg', 'kryss', 'finnes-ikke'], 'feil');
        console.log(JSON.stringify([felter.navn.value, felter.navn.classList.fjernet, felter.notat.value,
          felter.valg.selectedIndex, felter.kryss.checked, felter.feil.textContent, felter.feil.classList.lagt]));
    """

    def test_feltene_gaar_tilbake_til_standard_og_feilen_skjules(self):
        harness = build_harness(((PORTAL_UTILS_JS, ('nullstillFelter',)),))
        ut = run_node(harness, self.STUBB).splitlines()[0]
        self.assertEqual(ut, '["","is-invalid","standard",0,true,"","d-none"]')

    def test_uten_feilboks_og_uten_felter_er_ingen_feil(self):
        harness = build_harness(((PORTAL_UTILS_JS, ('nullstillFelter',)),))
        ut = run_node(harness, "globalThis.document = { getElementById: () => null };\n"
                               "nullstillFelter(['x'], 'y'); nullstillFelter([], null); console.log('ok');").splitlines()[0]
        self.assertEqual(ut, 'ok')
