"""`select_for_update` må ha en transaksjon koden selv har åpnet — også under test (20. okt. 2026).

André: «Jeg har et lag jeg ikke får flytte og får feilmelding kan ikke flytte.» `ko.tavle.plasser()`
hadde mistet `@transaction.atomic`, og hver flytting på tavla ga 500 på staging med
`TransactionManagementError`. Hele suiten var grønn, av to grunner som begge alltid vil gjelde:

- **`TestCase` kjører hver test inne i en transaksjon.** Django sjekker bare at det *finnes* en,
  ikke hvem som åpnet den, så en manglende `atomic` i koden er usynlig i alle `TestCase`-er.
- **SQLite har ikke `select_for_update`**, og Django sjekker ingenting der i det hele tatt.

Vakten stiller spørsmålet Django ikke stiller: **er minst én av transaksjonene åpnet av noe annet
enn testrammeverket?** Django merker sine egne med `_from_testcase` — det samme merket
`atomic(durable=True)` bruker for å skille testens transaksjon fra kodens. Da blir hver test som
går gjennom en låsende sti, en prøve av at stien har sin egen transaksjon, på SQLite også.

**Slått på bare under `manage.py test`** (`TRANSAKSJONSVAKT` i `settings.py`), fra
`CoreConfig.ready()` — som kjører i hver prosess, også arbeiderne under `--parallel` på Windows.
I drift gjør Django den ekte sjekken selv, på PostgreSQL.

**En hjelper som skal låse inne i kallerens transaksjon** (`core.vakt.laas_aktiv_vakt`,
`program.folg`) skal *ikke* få sin egen `atomic` for å stilne vakten: da slipper låsen idet
hjelperen returnerer når noen kaller den bart, og feilen blir stille i stedet for høylytt. En test
som kaller en slik hjelper direkte, åpner transaksjonen selv — som kallerne gjør.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models.sql.compiler import SQLCompiler

_ORIGINAL = SQLCompiler.as_sql


def har_egen_transaksjon(connection) -> bool:
    """Er minst én åpen `atomic` åpnet av koden, og ikke av `TestCase`?"""
    return any(not blokk._from_testcase for blokk in connection.atomic_blocks)


def _as_sql(self, *args, **kwargs):
    if self.query.select_for_update and not har_egen_transaksjon(self.connection):
        raise transaction.TransactionManagementError(
            'select_for_update uten en transaksjon koden selv har åpnet. I drift er dette en '
            '500 — TestCase skjuler det med sin egen transaksjon. Se core/transaksjonsvakt.py.')
    return _ORIGINAL(self, *args, **kwargs)


def installer() -> None:
    SQLCompiler.as_sql = _as_sql
