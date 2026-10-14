"""Ordboka i `/oppdrag/` (André, 14. okt. 2026) — `docs/FORSLAG_ORDBOK_OPPDRAG_KO.md` §4.

**D:** «tavla» i `/oppdrag/` var oppdragslista, mens KOs tavle er plasseringene — og
sentralbordet står inne i `/ko/`, så begge sto på samme skjerm. Her heter den
**oppdragslisten**; «tavlen» finnes bare i KO.

**B og C:** samlingen heter «ressurser» («Ressurser» over lista står), én konkret heter
«enhet». **«Trenger ressurs» står som fagord** — det operatøren sier på samband — og er
derfor tillatt, med de frasene som hører til samme status.

-en-formen holdes for hele portalen av `core/tests_ordboka.py`.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from core.ordboka import funn, modulfiler, synlig_tekst

FILER = modulfiler('oppdrag', ekstra=['static/js/oppdrag-kort.js'])

GAMLE_ORD = {
    r'[Tt]avla|[Tt]avlas|[Tt]avlen|[Tt]avlens': 'oppdragslisten (tavlen er KOs)',
    r'[Rr]essurs(?:en|ens)?': 'enhet (én konkret)',
    r'[Rr]essursgrupp\w*': 'ressurstype',
}
#: Svar C: statusen og frasene som hører til den.
TILLATT = (r'[Tt]renger (?:en )?(?:ny )?ressurs', r'uten ressurs', r'Ingen ressurs', r'Tildelt ressurs')


class OrdbokaTests(SimpleTestCase):

    def test_ingen_gamle_ord_i_teksten_brukeren_ser(self):
        f = funn(sorted(set(FILER)), GAMLE_ORD, TILLATT)
        self.assertEqual(f, [], 'Ordboka for /oppdrag/ (14. okt. 2026):\n' + '\n'.join(f))

    def test_leseren_ser_teksten(self):
        alt = ' '.join(t for sti in set(FILER) for t in synlig_tekst(sti))
        for ventet in ('Hent tilbake til oppdragslisten', 'står gult i oppdragslisten',
                       'Enheter rydder ikke oppdragslisten.', 'Trenger ressurs', 'Ressurser'):
            self.assertIn(ventet, alt)
