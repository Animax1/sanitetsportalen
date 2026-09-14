"""Tall om portalen, regnet ut fra koden.

**Hvorfor dette er en modul og ikke en test.** Tallene brukes to steder: av
`core/tests_dokumentråte.py`, som krever at dokumentene stemmer med dem, og av
den som skal oppdatere et dokument og trenger å vite hva det riktige tallet er.
Ligger utregningen bare inne i testen, må man lese testen for å finne svaret.

```powershell
python manage.py tallfasit
```

**Dette er den halvdelen av dokumentråte som lar seg måle.** Et tall som «16 av
123 endepunkter er dokumentert» eller «178 tester totalt» er galt fra den dagen
noen legger til et endepunkt eller en test — uten at noe sier fra, og uten at
noen gjorde noe galt. Påstander om *innhold* må fortsatt leses av et menneske;
se `core/tests_dokumentråte.py` for hvor den grensen går.
"""
from __future__ import annotations

from pathlib import Path


def _alle_ruter() -> list[str]:
    """Hver rute i portalen, uten Django-admin.

    Django-admin holdes utenfor fordi den bare rutes under `DEBUG` (S1) og
    ikke er en brukerflate — å telle dens drøyt hundre autogenererte ruter
    ville gjort tallet meningsløst.
    """
    from django.urls import get_resolver

    def gaa(res, prefiks=''):
        for m in res.url_patterns:
            sti = prefiks + str(m.pattern)
            if hasattr(m, 'url_patterns'):
                yield from gaa(m, sti)
            else:
                yield '/' + sti.lstrip('^').replace('\\', '')

    return sorted({s for s in gaa(get_resolver())
                   if not s.startswith(('/admin/', '/django-admin/'))})


def ruter_per_prefiks() -> dict[str, int]:
    """{'/pasienter/': 17, ...} — og `'andre'` for alt som ikke har et av dem."""
    kjente = ('/pasienter/', '/oppdrag/', '/vaktliste/', '/portal-admin/',
              '/accounts/', '/statistikk/')
    ut = {p: 0 for p in kjente}
    ut['andre'] = 0
    for sti in _alle_ruter():
        for p in kjente:
            if sti.startswith(p):
                ut[p] += 1
                break
        else:
            ut['andre'] += 1
    return ut


def fasit() -> dict[str, int]:
    """Alle tallene dokumentene får lov til å påstå."""
    from core.backup import all_handlers, registrer_alle_moduler
    from core.modules import get_all_modules
    from core.stats import all_handlers as stats_handlers

    registrer_alle_moduler()
    backup = list(all_handlers())

    ut = {
        'ruter_totalt': len(_alle_ruter()),
        'backup_handlere': len(backup),
        'backup_modulfiler': len([h for h in backup if h.slug != 'full']),
        'moduler': len(get_all_modules()),
        'statistikk_kilder': len(list(stats_handlers())),
        'js_filer': len(list((Path(__file__).resolve().parent.parent
                              / 'static' / 'js').glob('*.js'))),
    }
    ut.update({f'ruter{p.rstrip("/")}'.replace('/', '_'): n
               for p, n in ruter_per_prefiks().items() if p != 'andre'})
    ut['ruter_andre'] = ruter_per_prefiks()['andre']
    return ut


#: Ordene dokumentene skriver tall med. `Sju handlere` er ikke `7 handlere`,
#: og en regex som bare ser sifre ville gått forbi den.
TALLORD = {
    'null': 0, 'én': 1, 'ett': 1, 'to': 2, 'tre': 3, 'fire': 4, 'fem': 5,
    'seks': 6, 'sju': 7, 'syv': 7, 'åtte': 8, 'ni': 9, 'ti': 10, 'elleve': 11,
    'tolv': 12, 'tretten': 13, 'fjorten': 14, 'femten': 15, 'seksten': 16,
    'sytten': 17, 'atten': 18, 'nitten': 19, 'tjue': 20,
}


def som_tall(ord_: str) -> int | None:
    """'Sju' -> 7, '123' -> 123, 'mange' -> None."""
    ord_ = ord_.strip().lower()
    if ord_.isdigit():
        return int(ord_)
    return TALLORD.get(ord_)
