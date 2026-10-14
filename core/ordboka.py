"""Leseren bak ordbok-vaktene: teksten brukeren ser, og ingenting annet (14. okt. 2026).

Bodde i `vaktliste/tests_ordboka.py` fra 30. sep. 2026. Med `/oppdrag/` og `/ko/`
er den en regel for tre moduler, og en regel som gjelder flere moduler hører hjemme i
rota. Hver modul beholder sin egen liste over gamle ord og sin egen test.

**Hva som leses:** tekstnoder og `title`/`placeholder`/`aria-label` i malene, strenger
med mellomrom og mal-strenger i JS (ikke `${...}` og ikke innmaten i en tagg), og
meldingsstrenger i Python (ikke docstrings, ikke `{...}` i f-strenger). Kommentarer og
kode — `ressurs.navn`, `/api/ressurser/` — er utenfor, og skal være det.

**Ordboka** (André, 30. sep. og 14. okt. 2026):

| Ord | Betyr | Eksempel |
|---|---|---|
| ressurser | samlingen, alt vi har å sette inn | «Ressursoversikt», «Ressurser» |
| ressurs / ressurstype | hva slags | ambulanse, mannskapsbil, lag |
| enhet | én konkret | Ambulanse A, Karmøy 51, Lag 3 |

-en-form i hele portalen: vakten, vaktlisten, listen, filen, natten, tavlen, gruppen.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

from django.conf import settings

ROT = Path(settings.BASE_DIR)

#: -en-formen i hele portalen (svar A, 14. okt. 2026). Modulene legger sine egne ord til.
#: **Sammensetningene med** (`_SAMMEN`): «oppdragslista», «Nattevakta» og «modulfila» sto
#: igjen etter byttet 14. okt. 2026, fordi grensen krever at ordet står alene.
_SAMMEN = r'[\wæøåÆØÅ]*'
EN_FORM = {
    _SAMMEN + r'(?:[Vv]akta|[Vv]aktas)': 'vakten, vaktens',
    _SAMMEN + r'(?:[Ll]ista|[Ll]istas)': 'listen',
    _SAMMEN + r'(?:[Ff]ila|[Ff]ilas)': 'filen',
    _SAMMEN + r'[Nn]atta': 'natten',
    _SAMMEN + r'(?:[Tt]avla|[Tt]avlas)|KO-tavla': 'tavlen (i /oppdrag/: oppdragslisten)',
    _SAMMEN + r'(?:[Gg]ruppa|[Gg]ruppas)': 'gruppen',
}

#: Et ord inntil `/` er en sti (`/vaktliste/api/ressurser/`), ikke tekst — den blindsonen
#: ga byttet 30. sep. 2026 404 på hvert kall mot en enhet før gjennomgangen fanget det.
#: **En bindestrek foran er ikke tekst** — `data-tavle-ressurs="` i en mal-streng delt av
#: `${...}` er et attributtnavn. Prisen er at en sammensetning som «KO-tavla» ikke sees av
#: grensen, så den står som eget mønster i `EN_FORM` (14. okt. 2026: den sto i park, i
#: KO-innstillingene og som valgetikett).
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
            # En streng i ' eller " kan ikke gå over linjeskift. Finnes ingen slutt før
            # det, var tegnet noe annet — `/"/g` i en regex (notifications.js, 14. okt.).
            j = i + 1
            while j < n and src[j] != c and src[j] != '\n':
                j += 2 if src[j] == '\\' else 1
            if j >= n or src[j] != c:
                i += 1
                continue
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


#: Fra Python 3.12 er en f-streng ikke ett `STRING`-token, men START/MIDDLE/END —
#: og leseren så dem ikke i det hele tatt. «… står fortsatt på tavla» i
#: `oppdrag/vaktslutt.py` var usynlig for vakten (14. okt. 2026).
_FSTART = getattr(tokenize, 'FSTRING_START', None)
_FMIDT = getattr(tokenize, 'FSTRING_MIDDLE', None)
_FSLUTT = getattr(tokenize, 'FSTRING_END', None)


def tekst_py(src):
    ut = []
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    fdeler, fdybde = [], 0
    for idx, t in enumerate(toks):
        if _FSTART is not None and t.type == _FSTART:
            if fdybde == 0:
                fdeler = []
                tre = t.string.lstrip('rbfuRBFU').startswith(('"""', "'''"))
            fdybde += 1
            continue
        if fdybde and t.type == _FMIDT:
            fdeler.append(t.string)
            continue
        if fdybde and t.type == _FSLUTT:
            fdybde -= 1
            if fdybde == 0 and not tre:
                kropp = ' '.join(fdeler)
                if ' ' in kropp:
                    ut.append(kropp)
            continue
        if fdybde or t.type != tokenize.STRING:
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


def gamle_ord_i(tekst, gamle_ord, tillatt=()):
    """[(ordet, hva det heter nå)] — etter at de tillatte frasene er tatt ut av teksten."""
    for frase in tillatt:
        tekst = re.sub(frase, ' ', tekst)
    return [(m.group(0), ny) for monster, ny in gamle_ord.items()
            for m in re.finditer(GRENSE.format(f'(?:{monster})'), tekst)]


def funn(filer, gamle_ord, tillatt=()):
    return [f'{sti}: «{gammelt}» → {ny}   … {t.strip()[:70]}'
            for sti in filer for t in synlig_tekst(sti)
            for gammelt, ny in gamle_ord_i(t, gamle_ord, tillatt)]


def modulfiler(app, *, ekstra=()):
    """Malene, JS-filene og Python-filene til en modul — uten tester og `models.py`.

    `models.py` er utenfor fordi `help_text` bare vises i Django-admin, som er av i prod.
    Valgetikettene står i `choices.py`, som er med.
    """
    ut = []
    for d in (ROT / 'templates' / app, ROT / app / 'templates'):
        if d.exists():
            ut += [str(p.relative_to(ROT)) for p in sorted(d.rglob('*.html'))]
    ut += [str(p.relative_to(ROT)) for p in sorted((ROT / 'static/js').glob(f'{app}-*.js'))]
    ut += [str(p.relative_to(ROT)) for p in sorted((ROT / app).rglob('*.py'))
           if 'migrations' not in p.parts and 'management' not in p.parts
           and not p.name.startswith(('tests', 'test_')) and p.name != 'models.py']
    return ut + list(ekstra)
