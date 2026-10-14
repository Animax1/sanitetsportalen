"""Testhjelpere for oppdragsmodulen.

`lag_oppdrag` (14. okt. 2026, G6b-forarbeidet): testene opprettet oppdrag med
`enhet=` og lot broen i `Oppdrag.save()` lage koblingsraden — en vei drift ikke
har gått siden 26. sep. 2026 (A1). Broen kaster nå under test
(`oppdrag/bro.py`), og denne gjør det broen gjorde, **i klartekst og i samme
rekkefølge**: oppdraget, så koblingsraden med oppdragets status, opphavsperson,
`rekkefolge=0` og modusen frosset, så den gamle kolonnen.

Kolonnen settes med `update()`, ikke `save()`: i broen sto den i selve
`INSERT`-en, og en `save()` etterpå ville gitt en auditrad («enhet: – →
Bil 1») som ingen test har sett før. Ingen mottaker av `post_save` leser
`enhet` ved opprettelse, så det at den er tom et øyeblikk, synes ikke.

**I G6b** forsvinner feltet, og de to siste linjene med det. Testene står.
"""
from __future__ import annotations

from .models import Enhet, Oppdrag, Oppdragsenhet


def lag_oppdrag(**felter) -> Oppdrag:
    """Som `Oppdrag.objects.create(**felter)`, uten broen."""
    from .services import gjeldende_modus

    enhet = felter.pop('enhet', None)
    enhet_id = felter.pop('enhet_id', None)
    oppdrag = Oppdrag.objects.create(**felter)
    if enhet is None and enhet_id is not None:
        enhet = Enhet.objects.get(pk=enhet_id)
    if enhet is not None:
        Oppdragsenhet.objects.create(
            oppdrag=oppdrag, enhet=enhet, status=oppdrag.status,
            varslet_av=oppdrag.opprettet_av, rekkefolge=0,
            varslet_modus=gjeldende_modus(enhet))
        Oppdrag.objects.filter(pk=oppdrag.pk).update(enhet=enhet)
        oppdrag.enhet = enhet
    return oppdrag
