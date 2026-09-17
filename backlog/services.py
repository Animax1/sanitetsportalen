"""Reglene i backlog-modulen, skilt ut fra viewene.

Én regel avgjør noe her, og den har en grense: **forfatteren kan rette og
slette sitt eget innspill i én time.** Den ligger som egen funksjon av samme
grunn som `kan_sette_vaktpost()` og `klikkSkalKjore()` gjør det — en regel som
ikke lar seg kalle, lar seg ikke prøve, og en grense av med én er usynlig i en
`if` inne i et view.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from core.modules import get_all_modules

#: Angrefristen (André, 17. sep. 2026: «Forfatteren kan rette og slette sitt
#: innlegg innen 1 time etter den kom»).
#:
#: **Målt fra `opprettet_at`, ikke fra siste endring.** Fra endringstidspunktet
#: ville hver retting forlenget fristen, og et innspill kunne holdes redigerbart
#: i det uendelige ved å røre det hver time — da er ikke fristen en frist.
ANGREFRIST = timedelta(hours=1)


def kan_endres(innspill, bruker, naa=None) -> bool:
    """Får denne brukeren redigere eller slette innspillet nå?

    Tre vilkår, og alle tre må holde:

    1. **Kontoen er forfatteren.** Ikke «samme navn» — FK-en, fordi det frosne
       navnet er visning og kan gjentas.
    2. **Innen fristen**, målt fra opprettelsen.
    3. **Innspillet er ikke løst.** En løst sak er et svar noen har gitt, og å
       la forfatteren skrive om spørsmålet etterpå gjør svaret uforståelig.
       Dette vilkåret sto ikke i bestillingen; det er en konsekvens av at løst
       er et flagg og ikke en sletting, og det er billigere å ha det fra start
       enn å oppdage at en løst sak endret seg under føttene på den som løste.

    **Global admin er ikke unntatt.** Fristen verner ikke mot forfatteren, den
    verner *loggen* — «blir som en logg» var hele bestillingen. Skal en rad bort
    etter fristen, er det en avgjørelse noen tar i basen, ikke en knapp.
    """
    if innspill is None or bruker is None:
        return False
    if not getattr(bruker, 'is_authenticated', False):
        return False
    if innspill.opprettet_av_id != bruker.pk:
        return False
    if innspill.lost:
        return False
    if innspill.opprettet_at is None:
        # Ulagret rad. Ingen frist å måle mot, og ingenting å rette.
        return False
    naa = naa or timezone.now()
    return naa - innspill.opprettet_at <= ANGREFRIST


def gyldig_modul_slug(slug: str) -> bool:
    """Er dette en modul som finnes? Tom streng er gyldig — «ingen bestemt».

    **Utledet av registeret, ikke en liste her.** En ny modul er dekket fra
    dagen den registreres, og en håndholdt liste ville forfalt i stillhet.
    """
    if not slug:
        return True
    return any(m.slug == slug for m in get_all_modules())


def valgbare_moduler():
    """[(slug, navn)] til nedtrekket, i registerets egen rekkefølge.

    `backlog` selv er med: en bug i backloggen er også en bug.
    """
    return [(m.slug, m.name) for m in get_all_modules()]
