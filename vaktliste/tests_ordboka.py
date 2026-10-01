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

`test_leseren_ser_teksten` holder vakten ærlig: finner den ikke de nye ordene, leser
den ikke det den tror, og da ville den stått grønn om ingenting.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROT = Path(settings.BASE_DIR)
FILER = (
    ['templates/vaktliste/index.html', 'templates/vaktliste/fil.html',
     'templates/vaktliste/veiledning.html',
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
#: Et ord inntil `/` er en sti (`/vaktliste/api/ressurser/`), ikke tekst — den blindsonen
#: ga byttet 30. sep. 2026 404 på hvert kall mot en enhet før gjennomgangen fanget det.
GRENSE = r'(?<![\wæøåÆØÅ/-]){}(?![\wæøåÆØÅ/])'
ATTR = re.compile(r'''(?:title|placeholder|aria-label)=(["'])(.*?)\1''', re.S)


def _markup(s):
    ut, i = [], 0
    for m in re.finditer(r'<[^<>]*>', s):
        ut.append(s[i:m.start()])
        ut.extend(a.group(2) for a in ATTR.finditer(m.group(0)))
        i = m.end()
    ut.append(s[i:])
    return ut


def tekst_html(src):
    deler = re.split(r'({%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}|<!--.*?-->|'
                     r'<script\b.*?</script>|<style\b.*?</style>|{%.*?%}|{{.*?}})', src, flags=re.S)
    return [t for i, d in enumerate(deler) if not i % 2 for t in _markup(d)]


def tekst_js(src):
    ut, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
        elif src.startswith('/*', i):
            i = src.find('*/', i) + 2
        elif c in '\'"':
            j = i + 1
            while src[j] != c:
                j += 2 if src[j] == '\\' else 1
            if ' ' in src[i + 1:j]:
                ut.extend(_markup(src[i + 1:j]))
            i = j + 1
        elif c == '`':
            j, del_ = i + 1, []
            while src[j] != '`':
                if src[j] == '\\':
                    del_.append(src[j:j + 2]); j += 2
                elif src.startswith('${', j):
                    ut.extend(_markup(''.join(del_))); del_ = []
                    dybde, j = 1, j + 2
                    while dybde:
                        dybde += {'{': 1, '}': -1}.get(src[j], 0); j += 1
                else:
                    del_.append(src[j]); j += 1
            ut.extend(_markup(''.join(del_)))
            i = j + 1
        else:
            i += 1
    return ut


def tekst_py(src):
    ut = []
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    for idx, t in enumerate(toks):
        if t.type != tokenize.STRING:
            continue
        forrige = toks[idx - 1].type if idx else None
        neste = toks[idx + 1].type if idx + 1 < len(toks) else None
        if forrige in (tokenize.INDENT, tokenize.NEWLINE, tokenize.DEDENT, None) \
                and neste == tokenize.NEWLINE:
            continue
        s = t.string
        prefiks = re.match(r'[rbfuRBFU]*', s).group(0)
        if s[len(prefiks):].startswith(('"""', "'''")) or ' ' not in s:
            continue
        kropp = s[len(prefiks):]
        if 'f' in prefiks.lower():
            kropp = re.sub(r'\{[^{}]*\}', ' ', kropp)
        ut.append(kropp)
    return ut


def synlig_tekst(sti):
    src = (ROT / sti).read_text(encoding='utf-8')
    return {'html': tekst_html, 'js': tekst_js, 'py': tekst_py}[sti.rsplit('.', 1)[1]](src)


def gamle_ord_i(tekst):
    return [(m.group(0), ny) for monster, ny in GAMLE_ORD.items()
            for m in re.finditer(GRENSE.format(f'(?:{monster})'), tekst)]


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
