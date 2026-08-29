"""Tjenester for vaktlistemodulen.

Reglene som ikke hører hjemme i et view: å lage en planlagt vakt, å kopiere
et oppsett, og å avgjøre hvem som får røre hva.

**Korps-sjekkene bor her, ikke i viewene.** De håndheves først fra fase 3 —
modulen er admin-only fram til da — men regelen skrives én gang, på ett sted,
slik at fase 3 blir å ta den i bruk framfor å finne den opp per endepunkt.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.auth_decorators import er_global_admin, har_tilgang

from . import choices
from .models import Mannskap, Ressurs, Vaktliste, Vaktpost


# ── Vakter som ennå ikke er aktive ───────────────────────────────────────────

def opprett_planlagt_vakt(navn, startet=None):
    """Lag en `core.Vakt` som ikke er aktiv, og en tom vaktliste for den.

    **Rører ikke portalens peker.** `AppSetting['aktiv_vakt_id']` står som
    den står — oktobervakta skal kunne planlegges i august uten at pasienter
    og oppdrag plutselig scopes til den. Aktiv vakt byttes der den alltid
    byttes, i vaktadministrasjonen.

    Dette er det andre stedet i portalen som lager `Vakt`-rader (det første
    er «Avslutt vakt» i pasientmodulen). Det er notert som en ryddejobb i
    TODO sammen med `hent_aktiv_vakt` — vaktas livssyklus bør samles i
    `core` når noen er i den koden uansett.

    Returnerer den nye vaktlista.
    """
    from core.models import Vakt
    from core.validators import current_local_year

    navn = (navn or '').strip()
    if not navn:
        raise ValueError('Vakta må ha et navn.')
    if Vakt.objects.filter(navn=navn).exists():
        raise ValueError(
            f'En vakt med navnet «{navn}» finnes allerede. '
            f'Legg på en dato eller velg et annet navn.')

    startet = startet or timezone.now()
    with transaction.atomic():
        vakt = Vakt.objects.create(
            navn=navn,
            year=timezone.localtime(startet).year,
            startet=startet,
            er_aktiv=False,
        )
        return Vaktliste.objects.create(vakt=vakt)


def kopier_oppsett(fra_vaktliste, til_vaktliste):
    """Kopier ressursene — med type, reservasjon, enhet og rekkefølge.

    **Aldri personene.** Å kopiere folk ville satt dem opp på en vakt de ikke
    har sagt ja til, og en liste ingen har sagt ja til er verre enn en tom
    liste: den ser ferdig ut.

    Returnerer antall kopierte ressurser.
    """
    kopier = [
        Ressurs(
            vaktliste=til_vaktliste,
            navn=r.navn,
            type=r.type,
            korps=r.korps,
            enhet=r.enhet,
            rekkefolge=r.rekkefolge,
        )
        for r in fra_vaktliste.ressurser.all()
    ]
    Ressurs.objects.bulk_create(kopier)
    return len(kopier)


# ── Hvem får røre hva (håndheves fra fase 3) ─────────────────────────────────

def brukerens_korps(user):
    """Korpset kontoen arver fra mannskapsraden sin, eller ``None``.

    Badgen (§4). Koblingen `Mannskap.user` gir i seg selv ingen tilgang —
    den sier bare hvem du er, som `Enhet.user` i oppdragsmodulen.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    mannskap = Mannskap.objects.filter(user=user).select_related('korps').first()
    return mannskap.korps if mannskap else None


def kan_redigere_mannskap(user, mannskap) -> bool:
    """Får brukeren redigere denne personen?

    `skriv_full` og global admin: alle. `skriv_handling`: kun sitt eget
    korps. Uten mannskapsrad har kontoen ingen badge og kan ikke skrive noe —
    fail-closed, samme form som en enhetskonto uten enhet.
    """
    if er_global_admin(user) or har_tilgang(user, 'vaktliste', 'skriv_full'):
        return True
    if not har_tilgang(user, 'vaktliste', 'skriv_handling'):
        return False
    korps = brukerens_korps(user)
    return korps is not None and mannskap.korps_id == korps.pk


def kan_bemanne_ressurs(user, ressurs) -> bool:
    """Får brukeren sette folk på denne ressursen?

    Regelen er dobbel (§4.2), og dette er den ene halvdelen: ressursen må
    være reservert brukerens korps. En **ureservert** ressurs er ikke et
    fristed — den er `skriv_full`/admins bord, typisk KO og samleplass.
    """
    if er_global_admin(user) or har_tilgang(user, 'vaktliste', 'skriv_full'):
        return True
    if not har_tilgang(user, 'vaktliste', 'skriv_handling'):
        return False
    korps = brukerens_korps(user)
    return (korps is not None
            and ressurs.korps_id is not None
            and ressurs.korps_id == korps.pk)


def kan_sette_vaktpost(user, ressurs, mannskap) -> bool:
    """Begge halvdelene av regelen: badgen på personen, og reservasjonen.

    Skrevet som én funksjon slik at et endepunkt ikke kan huske den ene og
    glemme den andre.
    """
    return (kan_bemanne_ressurs(user, ressurs)
            and kan_redigere_mannskap(user, mannskap))
