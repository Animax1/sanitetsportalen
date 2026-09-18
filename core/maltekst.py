"""Les en mal med alt den inkluderer — én gang, for alle vaktene.

**Hvorfor dette finnes.** Flere regler leses av *malteksten*: at hver JS-fil
lastes i riktig rekkefølge, at en skrivende flate gir JS en CSRF-token, at
ingen mal peker på et CDN. De leste fila direkte, og da sentralbordets skript
og modaler ble skilt ut i `{% include %}`-biter 18. sep. 2026, ble to av dem
blinde på samme commit — uten å bli røde, som er det verste utfallet.

Regelen er den samme som `MorkTekstPaaMorkBakgrunnTests` alt følger for
`{% extends %}`: **følg lastekjeden, ikke én fil.** En vakt som bare ser på
den ene fila måler noe annet enn det nettleseren får.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

INCLUDE = re.compile(r'\{%\s*include\s+["\']([^"\']+)["\']')
EXTENDS = re.compile(r'\{%\s*extends\s+["\']([^"\']+)["\']')


def _finn(navn: str) -> Path | None:
    """Malnavnet slik Django ville løst det, mot mappene i TEMPLATES."""
    rot = Path(settings.BASE_DIR)
    kandidater = [Path(d, navn) for t in settings.TEMPLATES
                  for d in t.get('DIRS', [])]
    kandidater += [Path(rot, app, 'templates', navn)
                   for app in ('core', 'ko', 'oppdrag', 'patients', 'vaktliste',
                               'statistikk', 'backlog', 'accounts', 'audit')]
    kandidater.append(Path(rot, 'templates', navn))
    for sti in kandidater:
        if sti.exists():
            return sti
    return None


def les(navn_eller_sti, *, arv: bool = False, _sett=None) -> str:
    """Malteksten pluss alt den inkluderer, skjøtet sammen.

    `arv=True` tar med `{% extends %}`-forelderen også. Standard er av: de
    fleste reglene gjelder sidas egen markup, og basemalen ville lagt inn
    portalens felles skript i hver eneste måling.
    """
    _sett = _sett if _sett is not None else set()
    sti = (Path(navn_eller_sti) if Path(navn_eller_sti).exists()
           else _finn(str(navn_eller_sti)))
    if sti is None or str(sti) in _sett:
        return ''
    _sett.add(str(sti))
    tekst = sti.read_text(encoding='utf-8')
    deler = [tekst]
    if arv:
        for forelder in EXTENDS.findall(tekst):
            deler.append(les(forelder, arv=arv, _sett=_sett))
    for barn in INCLUDE.findall(tekst):
        deler.append(les(barn, arv=arv, _sett=_sett))
    return '\n'.join(deler)
