"""Forretningslogikk for oppdragsmodulen.

Statusmaskinen ligger her som **data**, ikke som ``if``-er spredt i viewene.
Grensesnittet viser kun lovlige knapper, men det er ikke der regelen bor: en
knapp som ikke vises er ikke en knapp som ikke kan trykkes.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from . import choices
from .models import Enhetsbytte, Oppdrag, Statusmelding

# ── Statusmaskinen ───────────────────────────────────────────────────────────
#
# `ledig` er utgang fra enhver status, ikke et ledd i kjeden. Den står derfor
# i hver rad, ikke bare til slutt.

OVERGANGER: dict[str, frozenset[str]] = {
    choices.VENTER:    frozenset({choices.RYKKER_UT, choices.LEDIG}),
    choices.RYKKER_UT: frozenset({choices.FREMME, choices.LEDIG}),
    choices.FREMME:    frozenset({choices.AVREIST, choices.LEDIG}),
    choices.AVREIST:   frozenset({choices.LEVERER, choices.LEDIG}),
    choices.LEVERER:   frozenset({choices.LEDIG}),
    choices.LEDIG:     frozenset(),          # terminal
}


def kan_gaa_til(fra: str, til: str) -> bool:
    """True hvis overgangen er lovlig.

    Ukjent status gir **False**, ikke True — samme regel som ukjent nivånavn i
    `har_tilgang`. En skrivefeil i et endepunktnavn skal stenge døra.
    """
    return til in OVERGANGER.get(fra, frozenset())


def neste_i_kjeden(fra: str) -> str | None:
    """Statusen «neste»-knappen skal sende til, eller ``None``.

    Enhetsskjermen har én «neste»-knapp og én «Ledig»-knapp — fem knapper der
    fire alltid er ulovlige er fire måter å trykke feil på i en bil i
    bevegelse. Knappen slår opp her og poster til det **navngitte**
    endepunktet for den overgangen; serveren utleder ingenting.
    """
    try:
        i = choices.KJEDEN.index(fra)
    except ValueError:
        return None
    if i + 1 >= len(choices.KJEDEN):
        return None
    return choices.KJEDEN[i + 1]


# ── Enhetens tilstand ────────────────────────────────────────────────────────

def aktivt_oppdrag(enhet, year: int | None = None):
    """Enhetens påbegynte oppdrag, eller ``None``.

    Påbegynt betyr «har passert `venter` og er ikke avsluttet». Et oppdrag som
    ligger og venter teller ikke: enheten har ikke rykket ut, og kan fortsatt
    sendes et annet sted.
    """
    qs = enhet.oppdrag.exclude(status__in=(choices.VENTER, choices.LEDIG))
    if year is not None:
        qs = qs.filter(year=year)
    return qs.order_by('-created_at').first()


def ventende_oppdrag(enhet, year: int | None = None):
    """Oppdrag som er tildelt, men ikke påbegynt."""
    qs = enhet.oppdrag.filter(status=choices.VENTER)
    if year is not None:
        qs = qs.filter(year=year)
    return qs.order_by('created_at')


def enhet_status(enhet, year: int | None = None) -> dict:
    """Enhetens status til sentralbordet — **utledet, aldri lagret**.

    Ved vaktstart står alle enheter som `Ledig`, og det er ikke en verdi noen
    setter: det er hva «ingen påbegynte oppdrag» ser ut som. En lagret status
    måtte nullstilles ved vaktstart og holdes i takt med oppdragsradene resten
    av vakta, og to kilder til samme sannhet går i utakt første gang noe
    feiler halvveis. Da er det den lagrede som lyver — den ser autoritativ ut.

    ``Ledig (2 venter)`` er distinksjonen 113 trenger for å vite hvem som kan
    sendes: enheten har fått to oppdrag, men ikke rykket ut på noen av dem.
    """
    aktivt = aktivt_oppdrag(enhet, year)
    antall_ventende = ventende_oppdrag(enhet, year).count()
    return {
        'enhet': enhet,
        'status': aktivt.status if aktivt else choices.LEDIG,
        'status_navn': (
            aktivt.get_status_display() if aktivt else choices.STATUS_NAVN[choices.LEDIG]
        ),
        'aktivt_oppdrag': aktivt,
        'antall_ventende': antall_ventende,
    }


# ── Overganger ───────────────────────────────────────────────────────────────

class UlovligOvergang(Exception):
    """Overgangen finnes ikke i tabellen over."""


@transaction.atomic
def sett_status(oppdrag, ny_status: str, *, bruker=None, tidspunkt=None,
                forsinket: bool = False, automatisk: bool = False) -> Statusmelding:
    """Skriv en statusmelding og oppdater oppdragets cachede status.

    Kaster ``UlovligOvergang`` hvis overgangen ikke står i tabellen. Sjekken
    ligger her og ikke i viewet, slik at også management-kommandoer og
    framtidige endepunkter går gjennom den.
    """
    if not kan_gaa_til(oppdrag.status, ny_status):
        raise UlovligOvergang(
            f'Kan ikke gå fra {oppdrag.status!r} til {ny_status!r}.'
        )

    melding = Statusmelding.objects.create(
        oppdrag=oppdrag,
        status=ny_status,
        tidspunkt=tidspunkt or timezone.now(),
        meldt_av=bruker,
        forsinket=forsinket,
        automatisk=automatisk,
    )
    oppdrag.status = ny_status
    oppdrag.save(update_fields=['status', 'updated_at'])
    return melding


@transaction.atomic
def start_oppdrag(oppdrag, *, bruker=None, tidspunkt=None,
                  forsinket: bool = False) -> Statusmelding:
    """Enheten rykker ut. Lukker et eventuelt pågående oppdrag automatisk.

    En enhet kan ha flere tildelte oppdrag, men bare ett påbegynt. Trykkes
    `Rykker ut` mens et annet er i gang, settes det pågående til `Ledig` med
    **samme tidsstempel**, og meldingen merkes ``automatisk=True``.

    Kostnaden er notert i beslutningsnotatet §4.3: den `Ledig`-meldingen er
    avledet, ikke målt — sluttiden for det forrige oppdraget blir starttiden
    for det neste. Flagget gjør at statistikken kan skille dem.
    """
    naa = tidspunkt or timezone.now()

    pagaende = aktivt_oppdrag(oppdrag.enhet, oppdrag.year)
    if pagaende is not None and pagaende.pk != oppdrag.pk:
        sett_status(pagaende, choices.LEDIG, bruker=bruker,
                    tidspunkt=naa, automatisk=True)

    return sett_status(oppdrag, choices.RYKKER_UT, bruker=bruker,
                       tidspunkt=naa, forsinket=forsinket)


@transaction.atomic
def korriger_tidspunkt(melding, nytt_tidspunkt, *, bruker) -> Statusmelding:
    """Rett tidspunktet på en statusmelding ved å skrive en **ny rad**.

    Begge blir stående i tidslinjen. ``Statusmelding`` er et spor av hva som
    faktisk ble meldt; redigerte man raden, kunne «hva sa bilen egentlig?»
    bare besvares fra ``AuditLog`` — en admin-flate som ikke er der oppdraget
    vises.

    Omfanget er **tidspunkt, ikke status**. Å rette hvilken status som skjedde
    ville flyttet oppdraget i kjeden, og da er det en ny hendelse.
    """
    return Statusmelding.objects.create(
        oppdrag=melding.oppdrag,
        status=melding.status,
        tidspunkt=nytt_tidspunkt,
        meldt_av=bruker,
        # Rettingen er meldt av et menneske ved en tastatur, uansett hva den
        # retter. Flaggene beskriver denne raden, ikke den den erstatter.
        forsinket=False,
        automatisk=False,
        korrigerer=melding,
    )


@transaction.atomic
def flytt_til_enhet(oppdrag, ny_enhet, *, bruker) -> Enhetsbytte | None:
    """Flytt oppdraget til en annen enhet, og skriv det i oppdragets logg.

    Returnerer ``None`` hvis enheten er den samme — et bytte til seg selv er
    ikke en hendelse.

    Statusen står. Meldingene den første enheten rakk å sende blir stående med
    ``meldt_av`` intakt: de skjedde.
    """
    if oppdrag.enhet_id == ny_enhet.pk:
        return None

    bytte = Enhetsbytte.objects.create(
        oppdrag=oppdrag,
        fra_enhet=oppdrag.enhet,
        til_enhet=ny_enhet,
        byttet_av=bruker,
    )
    oppdrag.enhet = ny_enhet
    oppdrag.save(update_fields=['enhet', 'updated_at'])
    return bytte


# ── Synlighet for enheten ────────────────────────────────────────────────────

#: Hvor lenge et avsluttet oppdrag blir stående på enhetsskjermen.
SKJUL_ETTER_LEDIG = 30 * 60   # sekunder


def synlige_for_enhet(enhet, year: int | None = None):
    """Oppdragene enhetsskjermen skal få levert.

    To regler, og **begge håndheves i serverens svar**:

    * Fritekst utelates straks status blir `Ledig` (gjøres i serialiseringen,
      se `views`-laget når det kommer).
    * Hele oppdraget utelates 30 minutter etter `Ledig`.

    At dette er server-side er poenget. Skjules fritekst i JS, ligger teksten
    fortsatt i responsen — og en bil som blir stående ulåst er nettopp
    scenarioet regelen finnes for.

    Grensen måles mot den gjeldende `Ledig`-meldingens ``tidspunkt``, ikke mot
    ``updated_at``: en korreksjon skal ikke forlenge vinduet.
    """
    from datetime import timedelta

    qs = enhet.oppdrag.select_related('lokasjon', 'enhet')
    if year is not None:
        qs = qs.filter(year=year)

    grense = timezone.now() - timedelta(seconds=SKJUL_ETTER_LEDIG)
    ut = []
    for oppdrag in qs:
        if oppdrag.status != choices.LEDIG:
            ut.append(oppdrag)
            continue
        melding = Statusmelding.objects.gjeldende_for_status(oppdrag, choices.LEDIG)
        if melding is not None and melding.tidspunkt > grense:
            ut.append(oppdrag)
    return ut
