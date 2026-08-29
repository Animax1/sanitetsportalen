"""Verdimengder for vaktlistemodulen.

**Kun det strukturelle ligger her.** `Korps`, `Kompetanse` og `VaktRolle` er
tabeller (fase 1) fordi de er organisasjonsdata admin skal styre uten deploy.
Ressurstypene er noe annet: de avgjør hvordan grensesnittet grupperer og
ikonlegger, og et nytt ikon krever uansett en kodeendring. Samme skille som
mellom `PROBLEMSTILLING` og `Lokasjon` i oppdragsmodulen.

Statusen på vaktlista står også her, og den er kort med vilje: drift betyr
**én ting** — at innsjekk er åpen (§5 i beslutningsnotatet).
"""
from __future__ import annotations

# ── Ressurstyper ─────────────────────────────────────────────────────────────
#
# Navnet på ressursen er fritekst per vakt («Mannskapsbil 1», «Lag Nord»);
# typen sier hva slags ting det er. Ikonet følger typen.

SAMLEPLASS = 'samleplass'
MANNSKAPSBIL = 'mannskapsbil'
AMBULANSE = 'ambulanse'
LAG = 'lag'
KO = 'ko'
ANNET = 'annet'

RESSURSTYPE_VALG: tuple[tuple[str, str], ...] = (
    (SAMLEPLASS, 'Samleplass'),
    (MANNSKAPSBIL, 'Mannskapsbil'),
    (AMBULANSE, 'Ambulanse'),
    (LAG, 'Lag'),
    (KO, 'KO'),
    (ANNET, 'Annet'),
)

RESSURSTYPE_NAVN: dict[str, str] = dict(RESSURSTYPE_VALG)

#: Bootstrap-ikon per type, uten `bi-`-prefiks.
RESSURSTYPE_IKON: dict[str, str] = {
    SAMLEPLASS: 'hospital',
    MANNSKAPSBIL: 'truck-front',
    AMBULANSE: 'truck',
    LAG: 'people',
    KO: 'broadcast-pin',
    ANNET: 'box',
}


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
