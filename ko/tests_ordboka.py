"""Ordboka i `/ko/` (André, 14. okt. 2026) — `docs/FORSLAG_ORDBOK_OPPDRAG_KO.md` §4.

**Samlingen heter «ressurser», én konkret heter «enhet»** — «innenfor ressursen ambulanse
så har du enheter hvor Ambulanse A er én enhet og Ambulanse B er en annen enhet».
«Ressursoversikt» står derfor, og skal ikke «rettes»: flertallet og sammensetningene
fanges ikke av mønsteret under. Entall om én ting — «Ukjent ressurs», en kolonne der hver
rad er en bil eller et lag — er det som byttes. **«Trenger ressurs» står** (svar C).

-en-formen holdes for hele portalen av `core/tests_ordboka.py`.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from core.ordboka import funn, modulfiler, synlig_tekst

FILER = modulfiler('ko')

GAMLE_ORD = {
    r'[Rr]essurs(?:en|ens)?': 'enhet (én konkret)',
    r'[Rr]essursgrupp\w*': 'ressurstype',
    r'uten oppdragsenhet': 'uten delt konto',
}
#: Svar C: statusen og frasene som hører til den.
TILLATT = (r'[Tt]renger (?:en )?(?:ny )?ressurs', r'uten ressurs', r'Ingen ressurs')


class OrdbokaTests(SimpleTestCase):

    def test_ingen_gamle_ord_i_teksten_brukeren_ser(self):
        f = funn(FILER, GAMLE_ORD, TILLATT)
        self.assertEqual(f, [], 'Ordboka for /ko/ (14. okt. 2026):\n' + '\n'.join(f))

    def test_leseren_ser_teksten(self):
        alt = ' '.join(t for sti in FILER for t in synlig_tekst(sti))
        for ventet in ('Ressursoversikt', 'Ukjent enhet.', 'Enheten finnes ikke lenger i vaktlisten.',
                       'Vaktlistens enheter uten delt konto', 'Trenger ressurs: pasient',
                       'Samme ressurstype står to ganger i behovet.'):
            self.assertIn(ventet, alt)
