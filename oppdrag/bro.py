"""Broene fra deploy 1 av flere enheter — telt, så G6b kan fjerne dem på bevis.

To steder fyller inn det gamle formatet for kode som ikke oppgir koblingsraden
selv (§2.3 i `docs/BESLUTNING_FLERE_ENHETER_PER_OPPDRAG.md`):

| Bro | Hvor | Fyller inn |
|---|---|---|
| `oppdrag` | `Oppdrag.save()` | Den første koblingsraden fra `Oppdrag.enhet` |
| `statusmelding` | `Statusmelding.save()` | `oppdragsenhet` fra oppdragets primære |
| `statusmelding_oppdrag` | `Statusmelding.save()` | `oppdrag` fra koblingsraden |

**Ingen kode i drift skal nå dem** (A1, 26. sep. 2026: «Nytt oppdrag» oppretter
med `enhet=None` og varsler gjennom `varsle_enhet`; begge stedene i
`services` som lager en `Statusmelding`, oppgir koblingsraden). G6b fjerner dem
etter neste vakt — og den slettingen skal stå på at de **ikke ble brukt**, ikke
på at vi tror det (André, 14. okt. 2026: «Hvordan ser vi advarselen?»).

Derfor tre ting, hver for sin leser:

- **En teller i `AppSetting`** (`oppdrag.bro.<navn>`: antall, første, siste,
  oppdraget) — overlever omstart og loggrotering, og vises på
  `/admin/server-status/` (`oppdrag/driftstatus.py`). Unntatt audit:
  det er maskinen som teller (`core.signals.NOKLER_UTEN_AUDIT`).
- **En `warning` i loggen**, for tidspunktet og oppdraget om vi må grave.
- **Et unntak under `manage.py test`** (`settings.OPPDRAG_BRO_KASTER`). En test
  som går gjennom en bro, blir rød med det samme, så suiten prøver den veien
  drift faktisk går. Testene av broene selv slår det av eksplisitt.

**Kaster aldri i drift.** Telleren skrives i et eget savepoint: broene kjører
inne i `save()`, ofte i en transaksjon, og en feilet telling uten savepoint
ville etterlatt transaksjonen ubrukelig — en stempling i en bil skal ikke
feile fordi telleren gjorde det.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

BROER = ('oppdrag', 'statusmelding', 'statusmelding_oppdrag')
PREFIKS = 'oppdrag.bro.'


class BroBrukt(AssertionError):
    """En test gikk gjennom en bro. Opprett slik drift gjør — se
    `oppdrag.test_helpers.lag_oppdrag` — eller, om testen gjelder selve broen,
    `@override_settings(OPPDRAG_BRO_KASTER=False)`."""


def bro_brukt(navn: str, oppdrag_id=None) -> None:
    """Meld at broen `navn` ble brukt. Kalles fra modellene."""
    if getattr(settings, 'OPPDRAG_BRO_KASTER', False):
        raise BroBrukt(f'Broen «{navn}» ble brukt (oppdrag {oppdrag_id}). {BroBrukt.__doc__}')
    logger.warning('G6b: broen «%s» ble brukt i drift (oppdrag %s).', navn, oppdrag_id)
    try:
        with transaction.atomic():
            _tell(navn, oppdrag_id)
    except Exception:   # noqa: BLE001 — se docstringen: telleren kaster aldri
        logger.exception('G6b: kunne ikke telle broen «%s».', navn)


def _tell(navn: str, oppdrag_id) -> None:
    from core.models import AppSetting

    naa = timezone.now().isoformat()
    rad, ny = AppSetting.objects.select_for_update().get_or_create(
        key=PREFIKS + navn, defaults={'value': ''})
    try:
        forrige = json.loads(rad.value) if rad.value else {}
    except (TypeError, ValueError):
        forrige = {}
    rad.value = json.dumps({
        'antall': int(forrige.get('antall') or 0) + 1,
        'forste': forrige.get('forste') or naa,
        'siste': naa,
        'oppdrag': oppdrag_id,
    })
    rad.save(update_fields=['value'])


def status() -> dict:
    """{navn: {antall, forste, siste, oppdrag} | None} — `None` er «aldri brukt»."""
    from core.models import AppSetting

    raa = dict(AppSetting.objects.filter(key__startswith=PREFIKS).values_list('key', 'value'))
    ut = {}
    for navn in BROER:
        try:
            ut[navn] = json.loads(raa[PREFIKS + navn]) if raa.get(PREFIKS + navn) else None
        except (TypeError, ValueError):
            ut[navn] = None
    return ut
