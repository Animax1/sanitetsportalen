"""Hjelpere for tester av rammeverket, delt av modulene.

**`skrivinger_utenom_signalene`** (24. sep. 2026): endringsnummeret
(`core/endringer.py`) økes av signaler, og `.update()` og `bulk_*` sender
ingen. Hver modul som melder inn et område, finner slike skrivinger på sine
modeller med denne og krever at hver er vurdert. Én leser, ikke én per
modul: en kopi ville mistet neste skrivemåte noen lærte den første.
"""
from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings

UTENOM = frozenset({'update', 'bulk_create', 'bulk_update'})

APPER = ('ko', 'vaktliste', 'oppdrag', 'core', 'patients', 'statistikk', 'backlog', 'accounts', 'audit')


def skrivinger_utenom_signalene(modeller) -> set[str]:
    """`{'<fil>: <Modell>.<metode>'}` for hver `Modell.objects….update()` og
    `bulk_*` på en av `modeller` (klassenavn), utenom tester og migrasjoner.
    `.delete()` på et queryset sender `post_delete` per rad, og er ikke med."""
    sporet = set(modeller)
    funn = set()
    for app in APPER:
        for fil in sorted((Path(settings.BASE_DIR) / app).rglob('*.py')):
            if 'migrations' in fil.parts or fil.name.startswith(('tests', 'test_')):
                continue
            for n in ast.walk(ast.parse(fil.read_text(encoding='utf-8'))):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr in UTENOM):
                    continue
                k, modell = n.func.value, None
                while isinstance(k, (ast.Call, ast.Attribute)):
                    if isinstance(k, ast.Attribute) and k.attr == 'objects' and isinstance(k.value, ast.Name):
                        modell = k.value.id
                        break
                    k = k.func if isinstance(k, ast.Call) else k.value
                if modell in sporet:
                    rel = fil.relative_to(settings.BASE_DIR).as_posix()
                    funn.add(f'{rel}: {modell}.{n.func.attr}')
    return funn


def koblet(signal, etikett, mottaker) -> bool:
    """Er `mottaker` blant de synkrone mottakerne av `signal` for modellen
    `etikett` («app.Modell»)? Django 5 gir `(synkrone, asynkrone)`."""
    from django.apps import apps
    synkrone, _asynkrone = signal._live_receivers(apps.get_model(etikett))
    return any(r is mottaker for r in synkrone)
