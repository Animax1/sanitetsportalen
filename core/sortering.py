"""Norsk alfabetisk rekkefølge — ett sted for hele portalen (26. sep. 2026).

**Hvorfor:** «alfabetisk» var databasens svar, og det er ikke norsk. Staging
(PostgreSQL 18, `en_US.utf8`) leste Æ som AE, Ø som O og Å som A: i
korps-nedtrekket sto «Ærø» øverst og «Ørsta» mellom «Haugesund» og «Oslo».
SQLite (dev) og en C-kollasjon legger dem sist, men som Å, Æ, Ø. Tre
rekkefølger for samme liste, og testene målte den maskinen de kjørte på —
CI var rød 26. sep. av nøyaktig det.

**Tre innganger, én regel:**

| Hvor | Bruk |
|---|---|
| `Meta.ordering` / `order_by()` | `Norsk('navn')` |
| Rå SQL | `norsk_sql(connection, 'navn')` |
| Python | `sorted(..., key=norsk_nokkel)` |

`Norsk` er **bare navnenøkkelen**. Regler som «lagleder før hospitant» og
fanerekkefølgen ligger i nøklene foran den (`rekkefolge`, `fra_tid`), og de
røres ikke — `Norsk` avgjør bare uavgjort.

**PostgreSQL:** `LOWER(x) COLLATE "nb-NO-x-icu"`. ICU-kollasjonene legges inn
av `initdb` når Postgres er bygd med ICU, som de offisielle imagene er. Mangler
den likevel, faller uttrykket tilbake til `LOWER(x)` — dagens sortering, ikke
en 500 på hver liste. Raden «Sortering av Æ Ø Å» på server-status viser hvilken
av dem portalen faktisk bruker.

**SQLite:** en egen kollasjon, `norsk`, registrert på hver ny tilkobling
(`registrer_sqlite_kollasjon`, koblet i `core.apps`). Den sammenligner med
`norsk_nokkel`, så dev sorterer nøyaktig som Python — og CI, som kjører
PostgreSQL, prøver at ICU og `norsk_nokkel` er enige.

**«Aa» er Å** (CLDR, som ICU og nettleserens `localeCompare(…, 'nb')`):
«Aasen» står etter «Ålesund», som i telefonkatalogen. Nøkkelen gjør det samme,
ellers ville dev og prod vært uenige.
"""
from __future__ import annotations

import unicodedata

from django.db.models import Func, TextField

#: ICU-kollasjonen for bokmål. Finnes i `pg_collation` når Postgres har ICU.
NORSK_KOLLASJON = 'nb-NO-x-icu'
#: Navnet på SQLite-kollasjonen `registrer_sqlite_kollasjon` legger inn.
SQLITE_KOLLASJON = 'norsk'

# Æ, Ø og Å etter z; ä/ö/ü er varianter av æ/ø/y (CLDR nb).
_ETTER_Z = {'æ': 1, 'ø': 2, 'å': 3}
_VARIANT = {'ä': 'æ', 'ö': 'ø', 'ü': 'y', 'ǿ': 'ø'}


def _primaer(tegn: str) -> tuple[int, ...]:
    if tegn in _ETTER_Z:
        return (ord('z'), _ETTER_Z[tegn])
    # Andre aksenter (é, è, ñ …) er grunnbokstaven på første nivå.
    grunn = unicodedata.normalize('NFD', tegn)[0]
    return (ord(grunn), 0)


def norsk_nokkel(tekst) -> tuple:
    """Sorteringsnøkkel for norsk alfabetisk rekkefølge.

    Første nivå: bokstavene uten store/små og aksenter, med Æ Ø Å sist og
    «aa» som Å. Uavgjort avgjøres av teksten i små bokstaver og så av at liten
    bokstav kommer før stor — samme retning som ICU. `None` sorteres som tom.
    """
    tekst = '' if tekst is None else str(tekst)
    smaa = tekst.lower()
    grunn = ''.join(_VARIANT.get(t, t) for t in smaa).replace('aa', 'å')
    primaer = tuple(_primaer(t) for t in grunn)
    return (primaer, smaa, tekst.swapcase())


def _sammenlign(a: str, b: str) -> int:
    ka, kb = norsk_nokkel(a), norsk_nokkel(b)
    return (ka > kb) - (ka < kb)


def registrer_sqlite_kollasjon(sender, connection, **kwargs):
    """`connection_created`-mottaker: legger `norsk` inn på SQLite-tilkoblingen."""
    if connection.vendor == 'sqlite':
        connection.connection.create_collation(SQLITE_KOLLASJON, _sammenlign)


def norsk_tilgjengelig(connection) -> bool:
    """Har denne databasen en norsk kollasjon? Svaret caches på tilkoblingen —
    det endrer seg ikke mens prosessen lever."""
    if connection.vendor == 'sqlite':
        return True
    if connection.vendor != 'postgresql':
        return False
    svar = getattr(connection, '_norsk_kollasjon', None)
    if svar is None:
        try:
            with connection.cursor() as cur:
                cur.execute('SELECT 1 FROM pg_collation WHERE collname = %s', [NORSK_KOLLASJON])
                svar = cur.fetchone() is not None
        except Exception:   # noqa: BLE001 — da sorterer vi som før, ikke 500
            return False
        connection._norsk_kollasjon = svar
    return svar


def norsk_sql(connection, uttrykk: str) -> str:
    """SQL-fragmentet som sorterer `uttrykk` norsk på denne tilkoblingen."""
    if not norsk_tilgjengelig(connection):
        return f'LOWER({uttrykk})'
    if connection.vendor == 'sqlite':
        return f'{uttrykk} COLLATE {SQLITE_KOLLASJON}'
    return f'LOWER({uttrykk}) COLLATE "{NORSK_KOLLASJON}"'


class Norsk(Func):
    """`order_by(Norsk('navn'))` — navnet i norsk alfabetisk rekkefølge."""

    function = 'LOWER'
    output_field = TextField()

    def as_sql(self, compiler, connection, **extra):
        sql, params = compiler.compile(self.source_expressions[0])
        return norsk_sql(connection, sql), params
