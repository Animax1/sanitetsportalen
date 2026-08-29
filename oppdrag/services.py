"""Forretningslogikk for oppdragsmodulen.

Statusmaskinen ligger her som **data**, ikke som ``if``-er spredt i viewene.
Grensesnittet viser kun lovlige knapper, men det er ikke der regelen bor: en
knapp som ikke vises er ikke en knapp som ikke kan trykkes.
"""
from __future__ import annotations

from django.db import models, transaction
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


#: Målstatusene et stemplingsendepunkt kan hete. Utledet fra tabellen, ikke
#: skrevet ned på nytt: står ikke navnet som mål i noen rad, finnes ikke
#: endepunktet. `venter` settes ved oppretting og stemples aldri — derfor er
#: settet fem, ikke seks, selv om statusene er seks.
STEMPLBARE: frozenset[str] = frozenset().union(*OVERGANGER.values())


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


# ── Oppdragsnummer ───────────────────────────────────────────────────────────

#: Nøkkelen i `AppSetting` som holder neste ledige nummer for ett år.
#: Per år, ikke global: nummeret restarter på 1 hver sesong slik at det holder
#: seg kort nok til å leses opp på samband.
def _nummer_nokkel(year: int) -> str:
    return f'next_oppdrag_nr_{year}'


def neste_oppdragsnummer(year: int) -> int:
    """Hent og inkrementer neste oppdragsnummer for året, atomisk.

    Samme mønster som `patients.services.next_patient_nr`: telleren står i
    `AppSetting` og låses med `select_for_update`, slik at to samtidige
    opprettelser ikke får samme nummer. Kalles inne i viewets transaksjon —
    feiler opprettelsen etterpå, rulles også telleren tilbake.

    Telleren gjenskapes fra dataene hvis raden mangler. Det gjør at en modul
    som får oppdrag før telleren finnes ikke starter på 1 og kolliderer med
    en eksisterende rad — og at en slettet AppSetting-rad ikke er en
    permanent feil.
    """
    from patients.models import AppSetting  # noqa: WPS433

    with transaction.atomic():
        nokkel = _nummer_nokkel(year)
        rad = AppSetting.objects.select_for_update().filter(key=nokkel).first()
        if rad is None:
            hoyeste = (Oppdrag.objects.filter(year=year)
                       .aggregate(models.Max('oppdragsnummer'))['oppdragsnummer__max'])
            start = (hoyeste or 0) + 1
            rad = AppSetting.objects.create(key=nokkel, value=str(start))
            # Les raden på nytt med lås: create() låser ikke, og to samtidige
            # kall kunne ellers passert hverandre her.
            rad = AppSetting.objects.select_for_update().get(key=nokkel)

        nr = int(rad.value)
        rad.value = str(nr + 1)
        rad.save(update_fields=['value'])
        return nr


# ── Historikk (rydding, ikke frysing) ────────────────────────────────────────
#
# **Ordet «arkiv» er bevisst unngått.** `core.arkiv` fryser, signerer og
# kollapser hele vakter, og oppdragsmodulen får sin egen `BaseArkivHandler` i
# fase 7. Her flyttes ett ferdigstilt oppdrag ut av den aktive tavla og inn i
# en søkbar historikk. Raden er urørt, og handlingen er reversibel.
#
# Derfor ligger den på `skriv_full`, ikke på global admin: §3.3 reserverer
# admin for det irreversible, og en knapp som bare rydder tavla hører til
# drift. Vaktarkivet i fase 7 er det som skal være admin.
#
# **Flyttingen skjer normalt av seg selv**, i `sett_status` når oppdraget blir
# `Ledig`. Funksjonene under er for hånd-tilfellene: `hent_tilbake` når noe må
# fram på tavla igjen, og `flytt_til_historikk` for å rydde det bort på nytt
# etterpå. Et oppdrag som er hentet tilbake blir *stående* — flyttingen henger
# på overgangen, ikke på statusen, så det finnes ingen ny overgang til `Ledig`
# som kunne fjernet det igjen.

class KanIkkeFlyttes(Exception):
    """Oppdraget er ikke ferdigstilt og kan ikke ryddes bort fra tavla."""


def flytt_til_historikk(oppdrag, *, bruker):
    """Flytt et ferdigstilt oppdrag ut av den aktive lista.

    **Kun `Ledig` kan flyttes.** Å rydde bort et pågående oppdrag ville
    skjult noe som fortsatt skjer — samme feilklasse som å ta en enhet av
    vakt midt i et oppdrag, og den er allerede stengt i `enhet_vakt_view`.

    Idempotent: et oppdrag som allerede ligger i historikken beholder sitt
    opprinnelige tidspunkt, slik at «når gikk den ut av tavla» ikke flyttes
    av et dobbelttrykk.

    Brukes i praksis til å rydde bort igjen et oppdrag som er hentet tilbake
    — den vanlige veien inn i historikken går gjennom `sett_status`.
    """
    if oppdrag.status != choices.TERMINAL:
        raise KanIkkeFlyttes(
            f'Oppdraget står i {oppdrag.get_status_display()} og er ikke ferdigstilt.')
    if oppdrag.historikk_fra is not None:
        return oppdrag

    oppdrag.historikk_fra = timezone.now()
    oppdrag.historikk_av = bruker
    oppdrag.save(update_fields=['historikk_fra', 'historikk_av', 'updated_at'])
    return oppdrag


def hent_tilbake(oppdrag):
    """Hent oppdraget tilbake til tavla.

    Ingenting ble fryst, så det er bare å nulle feltet.
    """
    if oppdrag.historikk_fra is None:
        return oppdrag
    oppdrag.historikk_fra = None
    oppdrag.historikk_av = None
    oppdrag.save(update_fields=['historikk_fra', 'historikk_av', 'updated_at'])
    return oppdrag


# ── Klienttid ────────────────────────────────────────────────────────────────
#
# Offline-kravet (§5.1) bryter «leser ikke kroppen» bokstavelig: en stempling
# utført uten dekning må kunne fortelle når den skjedde, ellers viser
# statistikken når nettet kom tilbake. Kroppen har derfor et lukket skjema på
# to nøkler, og `klienttid` er den ene.

#: Avviker klienttid mer enn dette fra ankomsttid, merkes meldingen
#: `forsinket=True` — da vet den som leser statistikken at tallet kommer fra
#: en bil som var uten dekning. To minutter skiller nettbrudd fra klokkeslark.
FORSINKET_TERSKEL_SEK = 120

#: Eldre klienttid enn dette forkastes til fordel for servertid. En kø som
#: har ligget over et døgn er ikke lenger en måling, det er arkeologi.
KLIENTTID_MAKS_ALDER_SEK = 24 * 3600


def vurder_klienttid(klienttid, oppdrag, naa=None):
    """Avgjør tidsstempel og forsinket-flagg for en stempling.

    Returnerer ``(tidspunkt, forsinket)``. Reglene fra beslutningsnotatet
    §5.1: klienttid brukes ikke hvis den ligger i framtiden, før oppdraget ble
    opprettet, eller er mer enn et døgn gammel — da brukes servertid.
    ``forsinket`` settes uansett når den *oppgitte* klienttiden avviker
    merkbart fra ankomsttid, også når den ble forkastet: avviket er
    informasjonen, ikke hvilket stempel som vant.
    """
    naa = naa or timezone.now()
    if klienttid is None:
        return naa, False

    avvik = abs((naa - klienttid).total_seconds())
    forsinket = avvik > FORSINKET_TERSKEL_SEK

    utenfor_vindu = (
        klienttid > naa
        or klienttid < oppdrag.created_at
        or (naa - klienttid).total_seconds() > KLIENTTID_MAKS_ALDER_SEK
    )
    return (naa if utenfor_vindu else klienttid), forsinket


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

    **En overgang til `Ledig` flytter oppdraget til historikken.** Regelen bor her og ikke i
    stemplingsviewet fordi ikke alle `Ledig`-overganger kommer derfra: den
    automatiske lukkingen i `start_oppdrag` (§4.3) går også gjennom denne
    funksjonen, og et oppdrag lukket av at enheten startet neste er like
    ferdig som ett noen trykket `Ledig` på. Lå regelen i viewet, ville tavla
    beholdt nettopp de oppdragene ingen trykket på.
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
    felter = ['status', 'updated_at']

    if ny_status == choices.TERMINAL and oppdrag.historikk_fra is None:
        # `historikk_av` står igjen som NULL, og det er informasjon, ikke en
        # mangel: NULL betyr «ryddet bort av seg selv», satt betyr «noen
        # trykket». Samme skille som `Statusmelding.automatisk`. Å føre opp
        # bilens konto her ville dessuten motsagt regelen om at enheter ikke
        # rydder tavla — den stempler, systemet rydder.
        oppdrag.historikk_fra = timezone.now()
        felter += ['historikk_fra']

    oppdrag.save(update_fields=felter)
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


class KorreksjonUgyldig(Exception):
    """Tidspunktet lar seg ikke rette til den oppgitte verdien."""


#: Full rekkefølge for statusene, inkludert terminal. `KJEDEN` stopper før
#: `ledig` fordi den er utgang fra enhver status, ikke et ledd — men når vi
#: sjekker at tidspunktene står i rekkefølge, er den sist.
_REKKEFOLGE = {status: i for i, status in enumerate(choices.KJEDEN)}
_REKKEFOLGE[choices.LEDIG] = len(choices.KJEDEN)


def _naboer(melding):
    """Gjeldende meldinger rett før og rett etter denne i statusrekkefølgen.

    Returnerer ``(forrige, neste)``, der hver kan være ``None``. Kun
    *gjeldende* rader teller: en overstyrt rad beskriver ikke lenger noe som
    gjelder, og å måle mot den ville låst rettingen til verdien man retter bort.
    """
    egen = _REKKEFOLGE.get(melding.status)
    if egen is None:
        return None, None

    forrige = neste = None
    for annen in Statusmelding.objects.gjeldende(melding.oppdrag):
        if annen.pk == melding.pk:
            continue
        plass = _REKKEFOLGE.get(annen.status)
        if plass is None:
            continue
        if plass < egen and (forrige is None or annen.tidspunkt > forrige.tidspunkt):
            forrige = annen
        elif plass > egen and (neste is None or annen.tidspunkt < neste.tidspunkt):
            neste = annen
    return forrige, neste


def valider_korreksjon(melding, nytt_tidspunkt, naa=None):
    """Kast ``KorreksjonUgyldig`` hvis rettingen ikke lar seg gjøre.

    Fire regler, og alle er fail-closed:

    1. **Raden må være gjeldende.** Å rette en rad som allerede er overstyrt
       ville gitt to korreksjoner av samme original, og «hvilken gjelder»
       hadde ikke lenger noe entydig svar.
    2. **Ikke i framtiden.** Et tidspunkt som ikke har inntruffet er ikke en
       observasjon.
    3. **Ikke før oppdraget ble opprettet.** Enheten kan ikke ha meldt noe om
       et oppdrag som ikke fantes.
    4. **Rekkefølgen må holde.** Settes `Fremme` før `Rykker ut`, blir
       responstiden negativ — og fase 6 ville regnet på den uten å vite at
       tallet er umulig. Skal begge rettes, rettes de én om gangen; feilmeldingen
       navngir hvilken nabo som er i veien.
    """
    naa = naa or timezone.now()

    if Statusmelding.objects.filter(korrigerer=melding).exists():
        raise KorreksjonUgyldig(
            'Denne meldingen er allerede rettet. Rett den nyeste i stedet.')

    if nytt_tidspunkt > naa:
        raise KorreksjonUgyldig('Tidspunktet kan ikke ligge i framtiden.')

    if nytt_tidspunkt < melding.oppdrag.created_at:
        raise KorreksjonUgyldig(
            'Tidspunktet er før oppdraget ble opprettet.')

    forrige, neste = _naboer(melding)
    if forrige is not None and nytt_tidspunkt < forrige.tidspunkt:
        raise KorreksjonUgyldig(
            f'«{melding.get_status_display()}» kan ikke være før '
            f'«{forrige.get_status_display()}» '
            f'({timezone.localtime(forrige.tidspunkt).strftime("%H:%M")}).')
    if neste is not None and nytt_tidspunkt > neste.tidspunkt:
        raise KorreksjonUgyldig(
            f'«{melding.get_status_display()}» kan ikke være etter '
            f'«{neste.get_status_display()}» '
            f'({timezone.localtime(neste.tidspunkt).strftime("%H:%M")}).')


@transaction.atomic
def korriger_tidspunkt(melding, nytt_tidspunkt, *, bruker) -> Statusmelding:
    """Rett tidspunktet på en statusmelding ved å skrive en **ny rad**.

    Begge blir stående i tidslinjen. ``Statusmelding`` er et spor av hva som
    faktisk ble meldt; redigerte man raden, kunne «hva sa bilen egentlig?»
    bare besvares fra ``AuditLog`` — en admin-flate som ikke er der oppdraget
    vises.

    Omfanget er **tidspunkt, ikke status**. Å rette hvilken status som skjedde
    ville flyttet oppdraget i kjeden, og da er det en ny hendelse.

    **Validerer ikke selv** — kall ``valider_korreksjon`` først. Skillet er
    med vilje: importflyten fra en offline-enhet (fase 5) kan ha grunner til
    å skrive rader utenfor reglene, og da skal den velge det eksplisitt.
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

    **Historikk-flyttingen påvirker ikke dette filteret.** De to reglene ser
    like ut, men tjener ulike formål: 30-minuttersvinduet er personvern (en bil
    kan bli stående ulåst), historikken er sentralbordets rydding av tavla si.
    Koblet man dem, kunne sentralbordet fjernet et oppdrag fra skjermen til et
    mannskap som fortsatt sto og så på det.
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
