"""Ordboka i `/vaktliste/` (pulje 3, 30. sep. 2026) håndheves på teksten brukeren ser.

André: ressurs er typen (ambulanse, lag, mannskapsbil), enhet er den konkrete
(Karmøy 51) — og «vakten», ikke «vakta», med -en-form også for vaktlisten, filen,
natten og gruppen. Skjermen brukte portalens egne ord: «Ny ressurs» for en enhet,
«Ressursgrupper» for typene, «Opprett vakt» for et skift. Bare etikettene ble
byttet; modellene heter det samme (`Ressursgruppe`, `Ressurs`, `Vaktpost`).

**Vakten leser bare tekst brukeren ser**, med samme avgrensning som byttet ble gjort
med: tekstnoder og `title`/`placeholder`/`aria-label` i malene, strenger med
mellomrom og mal-strenger i JS (ikke `${...}` og ikke innmaten i en tagg), og
meldingsstrenger i Python (ikke docstrings, ikke `{...}` i f-strenger). Kommentarer
og kode — `ressurs.navn`, `/api/ressurser/` — er utenfor, og skal være det.

Leseren bor i `core/ordboka.py` fra 14. okt. 2026 — `/oppdrag/` og `/ko/` bruker den også.

`test_leseren_ser_teksten` holder vakten ærlig: finner den ikke de nye ordene, leser
den ikke det den tror, og da ville den stått grønn om ingenting.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from core.ordboka import ROT, synlig_tekst, tekst_js, tekst_py
from core.ordboka import gamle_ord_i as _gamle_ord_i

FILER = (
    ['templates/vaktliste/index.html', 'templates/vaktliste/fil.html',
     'templates/vaktliste/veiledning.html', 'templates/vaktliste/kontokobling.html',
     'vaktliste/templates/vaktliste/portalinnstillinger.html']
    + sorted(str(p.relative_to(ROT)) for p in (ROT / 'static/js').glob('vaktliste-*.js'))
    + sorted(str(p.relative_to(ROT)) for p in (ROT / 'vaktliste').glob('*.py')
             if not p.name.startswith(('tests', 'test_')) and p.name != 'models.py')
)

#: Ord som ikke skal stå i teksten brukeren ser, og hva det heter nå.
#: `models.py` er utenfor: `help_text` vises bare i Django-admin, som er av i prod.
GAMLE_ORD = {
    r'[Vv]akta|[Vv]aktas': 'vakten, vaktens',
    r'[Vv]aktlista|[Vv]aktlistas': 'vaktlisten, vaktlistens',
    r'[Ll]ista|[Ll]istas': 'listen',
    r'[Ff]ila|[Ff]ilas': 'filen',
    r'[Nn]atta': 'natten',
    r'[Gg]ruppa|[Gg]ruppas': 'ressurstypen (eller gruppen)',
    r'[Tt]avla': 'tavlen',
    r'[Rr]essursgrupp\w*': 'ressurstype',
    r'[Rr]essurs(?:en|ene|ens|er)?': 'enhet (den konkrete)',
    r'Opprett vakt': 'Nytt skift',
    r'Vaktnavn': 'Navn på vakten',
    r'Enhet i oppdragsmodulen': 'Koble til delt konto',
    # Pulje 4: «Ureservert» leste som «ledig for alle» og betydde lederens kladd.
    r'[Uu]reservert': 'ikke delt ut',
}
def gamle_ord_i(tekst):
    return _gamle_ord_i(tekst, GAMLE_ORD)


class OrdbokaTests(SimpleTestCase):

    def test_ingen_gamle_ord_i_teksten_brukeren_ser(self):
        funn = [f'{sti}: «{gammelt}» → {ny}   … {t.strip()[:70]}'
                for sti in FILER for t in synlig_tekst(sti)
                for gammelt, ny in gamle_ord_i(t)]
        self.assertEqual(funn, [], 'Ordboka for /vaktliste/ (CHANGELOG 30. sep. 2026):\n'
                         + '\n'.join(funn))

    def test_leseren_ser_teksten(self):
        """Uten denne kunne leseren stille ha sluttet å finne noe, og vakten stått grønn."""
        alt = ' '.join(t for sti in FILER for t in synlig_tekst(sti))
        for ventet in ('Ny enhet', 'Rediger enhet', 'Ressurstyper', 'Nytt skift',
                       'Koble til delt konto', 'Navn på vakten', 'Enheten må ha et navn.',
                       'Vakten må slutte etter at den begynner.'):
            self.assertIn(ventet, alt)

    def test_koden_er_utenfor(self):
        """API-adressene og variablene heter fortsatt `ressurs` — og skal gjøre det."""
        js = tekst_js("const r = aktivListe.ressurser; apiFetch(`/vaktliste/api/ressurser/${id}/`);"
                      " // Ressursen i en kommentar\n'Ressursen må ha et navn.'")
        self.assertEqual([('Ressursen', 'enhet (den konkrete)')],
                         [f for t in js for f in gamle_ord_i(t)])

    def test_docstring_er_utenfor_men_meldingen_er_ikke(self):
        py = tekst_py('def f():\n    """Ressursen i en docstring."""\n'
                      "    raise X('Vakta må slutte etter at den begynner.',\n"
                      "            'og ressurs(er) i en fortsettelse.')\n")
        self.assertEqual(['Vakta', 'ressurs'], [g for t in py for g, _ in gamle_ord_i(t)])
