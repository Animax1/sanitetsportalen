"""Tjenester for vaktlistemodulen.

Reglene som ikke hører hjemme i et view: å lage en planlagt vakt, å kopiere
et oppsett, og å avgjøre hvem som får røre hva.

**Korps-sjekkene bor her, ikke i viewene.** Regelen er skrevet én gang, på
ett sted, og viewene tar den i bruk — det er derfor et endepunkt ikke kan
huske badgen og glemme reservasjonen.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.auth_decorators import er_global_admin, har_tilgang

from .models import Mannskap, Ressurs, Vaktliste


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


def neste_rekkefolge(vaktliste) -> int:
    """Neste ledige fanerekkefølge på lista — altså «sist».

    `Ressurs.rekkefolge` er det ene stedet i modulen der rekkefølgen *betyr*
    noe: den styrer fanene på planleggingssiden, og alfabetisk ville stokket
    om på den operative rekkefølgen (samleplass, biler, lag, KO blir
    «Ambulanse, KO, Lag 1, Mannskapsbil 1»).

    Men brukeren skal ikke skrive et tall. Den som bygger vakta legger inn
    ressursene i den rekkefølgen hun tenker på dem, og det er den rekkefølgen
    fanene skal ha. Steget på 10 gir plass til å skyte inn en ressurs mellom
    to andre den dagen noen vil kunne omorganisere.
    """
    fra_for = (vaktliste.ressurser
               .order_by('-rekkefolge')
               .values_list('rekkefolge', flat=True)
               .first())
    return (fra_for or 0) + 10


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


# ── Kompetansestigen ─────────────────────────────────────────────────────────
#
# `Kompetanse.bygger_paa` peker på det kurset denne overordner: AFØR bygger på
# VFØR, som bygger på GFØR. Reglene under er de to som trengs for at pekeren
# skal bety noe — én for visning, én for å hindre at stigen blir en ring.


def _foreldrekjede(kompetanse_id, foreldre, _sett=None):
    """Alle IDene over `kompetanse_id` i stigen, transitivt.

    `foreldre` er ``{id: bygger_paa_id}`` for hele registeret, slått opp én
    gang av kalleren — en spørring per kompetanse ville gitt N+1 på en liste
    med hundre mannskaper.

    `_sett` stopper en ring. Ringer skal ikke kunne oppstå (`lager_sykel`
    hindrer dem ved skriving), men en gammel rad eller en manuell endring i
    basen skal gi en avkortet kjede, ikke en evig løkke.
    """
    _sett = _sett if _sett is not None else set()
    forelder = foreldre.get(kompetanse_id)
    if forelder is None or forelder in _sett:
        return _sett
    _sett.add(forelder)
    return _foreldrekjede(forelder, foreldre, _sett)


def synlige_kompetanser(kompetanser, foreldre):
    """De kompetansene som ikke overordnes av en annen personen har.

    Har hun AFØR, VFØR og Sykepleier, står hun igjen med AFØR og Sykepleier:
    VFØR er implisert, og Sykepleier er ikke i den stigen i det hele tatt.

    `kompetanser` er radene personen har; `foreldre` er kartet fra
    `foreldrekart()`. Rekkefølgen bevares.
    """
    holdt = {k.pk for k in kompetanser}
    implisert = set()
    for pk in holdt:
        implisert |= _foreldrekjede(pk, foreldre)
    return [k for k in kompetanser if k.pk not in implisert]


def foreldrekart():
    """``{id: bygger_paa_id}`` for hele kompetanseregisteret.

    Slås opp én gang per forespørsel og sendes med til `synlige_kompetanser`.
    """
    from .models import Kompetanse
    return dict(Kompetanse.objects.values_list('pk', 'bygger_paa_id'))


def lager_sykel(kompetanse_id, nytt_forelder_id) -> bool:
    """True hvis pekeren ville laget en ring i stigen.

    «A bygger på B, B bygger på A» har ikke noe svar på hvilken som er
    øverst, og ville gjort `synlige_kompetanser` til en smakssak. Det stoppes
    ved skriving framfor å håndteres ved lesing: en ring i basen er en feil
    som ikke skal kunne oppstå, ikke en tilstand koden skal tåle.
    """
    if nytt_forelder_id is None:
        return False
    if nytt_forelder_id == kompetanse_id:
        return True
    return kompetanse_id in _foreldrekjede(nytt_forelder_id, foreldrekart())


# ── Hvem får røre hva ────────────────────────────────────────────────────────
#
# Håndheves fra fase 3, på hvert endepunkt. Tre nivåer av «hvem»:
#
#   kan_skrive_alt      — `skriv_full`/admin. Blander korps fritt, deler ut
#                         ressurser, styrer verdimengdene.
#   kan_*_korps/…       — `skriv_handling` avgrenset av badgen.
#   (ingenting)         — `les` skriver ikke.
#
# **`les` gjelder hele lista med vilje.** Poenget med en vaktliste er
# samordning på tvers av korps; den som ikke skal se andre korps, skal ikke ha
# modulen (§4.4).

def kan_skrive_alt(user) -> bool:
    """`skriv_full` eller global admin — står utenfor badge og reservasjon.

    Samlet her framfor å gjentas i hvert view: det er terskelen for alt som
    gjelder *vakta* framfor *et korps* — å dele ut ressurser, å planlegge en ny
    vakt, og å styre `Korps`/`Kompetanse`/`Ressursrolle`.
    """
    return er_global_admin(user) or har_tilgang(user, 'vaktliste', 'skriv_full')


def brukerens_korps(user):
    """Korpset kontoen arver fra mannskapsraden sin, eller ``None``.

    Badgen (§4). Koblingen `Mannskap.user` gir i seg selv ingen tilgang —
    den sier bare hvem du er, som `Enhet.user` i oppdragsmodulen.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    mannskap = Mannskap.objects.filter(user=user).select_related('korps').first()
    return mannskap.korps if mannskap else None


def kan_fore_korps(user, korps_id) -> bool:
    """Får brukeren føre folk i dette korpset?

    Grunnregelen begge mannskapssjekkene hviler på. `skriv_full` og global
    admin: alle korps. `skriv_handling`: kun sitt eget. Uten mannskapsrad har
    kontoen ingen badge og kan ikke skrive noe — fail-closed, samme form som
    en enhetskonto uten enhet.
    """
    if kan_skrive_alt(user):
        return True
    if not har_tilgang(user, 'vaktliste', 'skriv_handling'):
        return False
    korps = brukerens_korps(user)
    return korps is not None and korps_id == korps.pk


def kan_redigere_mannskap(user, mannskap) -> bool:
    """Får brukeren redigere denne personen? Avgjøres av personens korps."""
    return kan_fore_korps(user, mannskap.korps_id)


def kan_flytte_mannskap(user, mannskap, nytt_korps_id) -> bool:
    """Får brukeren flytte personen til et annet korps?

    **Begge korpsene teller.** Sjekket vi bare det personen har i dag, kunne
    korps-brukeren flytte sine egne folk ut i et hvilket som helst annet
    korps; sjekket vi bare målet, kunne hun hente inn andres. Det er samme
    feilform som den doble regelen i `kan_sette_vaktpost` — og siden
    `skriv_handling` per definisjon bare har ett korps, betyr det i praksis at
    hun ikke flytter noen i det hele tatt. Flytting er `skriv_full`.
    """
    return (kan_fore_korps(user, mannskap.korps_id)
            and kan_fore_korps(user, nytt_korps_id))


def kan_bemanne_ressurs(user, ressurs) -> bool:
    """Får brukeren sette folk på denne ressursen?

    Regelen er dobbel (§4.2), og dette er den ene halvdelen: ressursen må
    være reservert brukerens korps. En **ureservert** ressurs er ikke et
    fristed — den er `skriv_full`/admins bord, typisk KO og samleplass.
    """
    if kan_skrive_alt(user):
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

    **`mannskap=None` er en ledig plass, og den er `skriv_full`.** Å opprette
    et behov — «Lag 1 trenger fire, én av dem lagleder» — er å planlegge
    vakta, ikke å føre sitt eget korps. Korps-brukeren *fyller* plassene som
    er satt av til henne; hun bestemmer ikke hvor mange det skal være. Uten
    dette unntaket ville badge-halvdelen ikke hatt noe å sjekke mot, og
    regelen falt åpen på nøyaktig det tilfellet som er nytt.
    """
    if mannskap is None:
        return kan_skrive_alt(user)
    return (kan_bemanne_ressurs(user, ressurs)
            and kan_redigere_mannskap(user, mannskap))


def kan_rore_vaktpost(user, vaktpost) -> bool:
    """Får brukeren redigere denne raden slik den står?

    **Et annet spørsmål enn `kan_sette_vaktpost`,** og det er verdt å holde
    dem fra hverandre:

    - `kan_sette_vaktpost(bruker, ressurs, person)` spør om *paret* kan
      opprettes. Med `person=None` er det å opprette et behov — `skriv_full`.
    - `kan_rore_vaktpost(bruker, rad)` spør om brukeren i det hele tatt får
      ta i raden. En **ledig** plass på hennes egen ressurs skal hun få ta i,
      for det er nettopp den hun skal fylle.

    Ble den første brukt til begge, låste den korps-brukeren ute av akkurat
    de plassene som var satt av til henne — funnet av
    `LedigPlassTilgangTests`.
    """
    if not kan_bemanne_ressurs(user, vaktpost.ressurs):
        return False
    if vaktpost.mannskap_id is None:
        return True
    return kan_redigere_mannskap(user, vaktpost.mannskap)


def vaktspenn(vaktliste):
    """(start, slutt) for vakta — eller ``(None, None)`` hvis den mangler.

    Starten er `Vakt.startet`; slutten er `Vaktliste.planlagt_slutt`. Se
    modellkommentaren for hvorfor de to ikke bor samme sted.

    Brukes av bemanningskurven, som skal tegnes over **hele** vakta: leste
    den bare skiftene, ville hullet i begynnelsen vært usynlig nettopp fordi
    ingen er satt opp der ennå.
    """
    start = vaktliste.vakt.startet
    slutt = vaktliste.planlagt_slutt
    if start is None or slutt is None or slutt <= start:
        return (None, None)
    return (start, slutt)
