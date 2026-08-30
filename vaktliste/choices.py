"""Verdimengder for vaktlistemodulen.

**Én verdimengde igjen, og det er en tilstand.** Statusen er kort med vilje:
drift betyr **én ting** — at innsjekk er åpen (§5 i beslutningsnotatet).

Ressurstypene lå her til 30. aug. 2026, med den begrunnelsen at et nytt ikon
uansett krever en deploy. Den holdt ikke: et arrangement kan trenge et
førstehjelpstelt eller en MC-patrulje, og en vaktleder som trenger gruppa i
kveld kan ikke vente på en utrulling. De er nå tabellen `Ressursgruppe`, med
ikonet som et felt — feil ikon er en skjønnhetsfeil, en manglende gruppe er en
vaktliste man ikke får satt opp. Standardgruppene seedes av migrasjon `0007`.
"""
from __future__ import annotations

# ── Status på vaktlista ──────────────────────────────────────────────────────
#
# To verdier, ikke tre. «Avsluttet» finnes ikke: arkivering (fase 7) er en
# egen handling som fryser en kopi, og en liste som var i drift i går er
# fortsatt en liste — den skal ikke få en tilstand som ser ut som sletting.

PLANLEGGING = 'planlegging'
DRIFT = 'drift'

STATUS_VALG: tuple[tuple[str, str], ...] = (
    (PLANLEGGING, 'Planlegging'),
    (DRIFT, 'I drift'),
)

STATUS_NAVN: dict[str, str] = dict(STATUS_VALG)
