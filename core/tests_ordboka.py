"""-en-formen i hele portalen, og leseren alle ordbok-vaktene står på (14. okt. 2026).

André, svar A: «vakten», «vaktlisten», «tavlen» — ikke bare i `/vaktliste/`. Hvert modul-
ord (ressurs, enhet, oppdragslisten) holdes av modulens egen `tests_ordboka.py`; denne
holder det som gjelder alle, og at leseren faktisk ser det den skal.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from core.ordboka import EN_FORM, ROT, funn, gamle_ord_i, modulfiler, synlig_tekst, tekst_js, tekst_py

APPER = ('accounts', 'audit', 'backlog', 'core', 'ko', 'oppdrag', 'park', 'patients',
         'statistikk', 'vaktliste')
FELLES = (
    [str(p.relative_to(ROT)) for p in sorted((ROT / 'templates').glob('*.html'))]
    + [str(p.relative_to(ROT)) for p in sorted((ROT / 'templates' / 'partials').glob('*.html'))]
    + ['static/js/portal-utils.js', 'static/js/ui-actions.js', 'static/js/notifications.js',
       'static/js/portal-status.js']
)


def alle_filer():
    return sorted({f for app in APPER for f in modulfiler(app)} | set(FELLES))


class EnFormenTests(SimpleTestCase):

    def test_ingen_a_form_i_teksten_brukeren_ser(self):
        f = funn(alle_filer(), EN_FORM)
        self.assertEqual(f, [], 'Ordboka, svar A (14. okt. 2026):\n' + '\n'.join(f))

    def test_leseren_ser_teksten(self):
        """Uten denne kunne leseren stille ha sluttet å finne noe, og vakten stått grønn."""
        alt = ' '.join(t for sti in alle_filer() for t in synlig_tekst(sti))
        for ventet in ('Kunne ikke hente listen', 'Tavlen fører det som har skjedd',
                       'er ikke den aktive vakten', 'Fra KO-tavlen',
                       'oppdrag står fortsatt i oppdragslisten'):
            self.assertIn(ventet, alt)


class LeserenTests(SimpleTestCase):
    """Blindsonene som ble funnet da leseren ble tatt i bruk utenfor vaktlista."""

    def test_f_strenger_leses(self):
        """Fra Python 3.12 er en f-streng ikke et `STRING`-token — leseren så dem ikke."""
        py = tekst_py("def f(n):\n    raise X(f'{n} oppdrag står på tavla.')\n")
        self.assertEqual([g for t in py for g, _ in gamle_ord_i(t, EN_FORM)], ['tavla'])

    def test_docstring_og_trippel_fstreng_er_utenfor(self):
        py = tekst_py('def f(n):\n    """Vakta i en docstring."""\n    y = f"""Vakta {n}"""\n')
        self.assertEqual([g for t in py for g, _ in gamle_ord_i(t, EN_FORM)], [])

    def test_regex_med_anforselstegn_velter_ikke_leseren(self):
        """`/"/g` i `notifications.js` lot `"` lete forbi slutten av fila (IndexError)."""
        js = tekst_js("s.replace(/\"/g, '&quot;');\nconst m = 'Kunne ikke hente lista nå';\n")
        self.assertEqual([g for t in js for g, _ in gamle_ord_i(t, EN_FORM)], ['lista'])

    def test_sammensetningen_ko_tavla_sees_men_ikke_et_attributtnavn(self):
        self.assertEqual([g for g, _ in gamle_ord_i('Fra KO-tavla nå', EN_FORM)], ['KO-tavla'])
        self.assertEqual(gamle_ord_i(' data-tavla-x=" ', EN_FORM), [])

    def test_sammensetninger_sees(self):
        """«oppdragslista» og «Nattevakta» sto igjen etter byttet: grensen krever at ordet står alene."""
        self.assertEqual([g for g, _ in gamle_ord_i('Nullstill oppdragslista, Nattevakta', EN_FORM)],
                         ['Nattevakta', 'oppdragslista'])
        self.assertEqual(gamle_ord_i('oppdragslisten og Nattevakten', EN_FORM), [])

    def test_tillatte_fraser_tas_ut_foer_sjekken(self):
        ord_ = {r'[Rr]essurs': 'enhet'}
        self.assertEqual(gamle_ord_i('Trenger ressurs, Ukjent ressurs', ord_, (r'Trenger ressurs',)),
                         [('ressurs', 'enhet')])
