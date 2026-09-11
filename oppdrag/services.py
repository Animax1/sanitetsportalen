"""Forretningslogikk for oppdragsmodulen.

Statusmaskinen ligger her som **data**, ikke som ``if``-er spredt i viewene.
Grensesnittet viser kun lovlige knapper, men det er ikke der regelen bor: en
knapp som ikke vises er ikke en knapp som ikke kan trykkes.
"""
from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone

from . import choices
from .models import Enhetsbytte, Oppdrag, Oppdragsenhet, Statusmelding

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

#: Nøkkelen i `AppSetting` som holder neste ledige nummer for én vakt.
#: Per vakt siden deploy 2: nummeret restarter på 1 hver vakt slik at det
#: holder seg kort nok til å leses opp på samband, og «oppdrag 14» aldri er
#: tvetydig innenfor vakta.
def _nummer_nokkel(vakt) -> str:
    return f'next_oppdrag_nr_vakt_{vakt.pk}'


def neste_oppdragsnummer(vakt) -> int:
    """Hent og inkrementer neste oppdragsnummer for vakta, atomisk.

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
        nokkel = _nummer_nokkel(vakt)
        rad = AppSetting.objects.select_for_update().filter(key=nokkel).first()
        if rad is None:
            hoyeste = (Oppdrag.objects.filter(vakt=vakt)
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

def koblingsrad(oppdrag, enhet=None):
    """Enhetens rad på oppdraget — eller den primære når ingen enhet oppgis.

    ``None`` hvis enheten ikke er varslet på oppdraget. Det er svaret på
    «eier bilen dette oppdraget?», og alle eierskapssjekkene går her.
    """
    if enhet is None:
        return oppdrag.primaer
    return oppdrag.enheter.filter(enhet=enhet).select_related('enhet').first()


def utledet_status(oppdrag) -> str:
    """Oppdragets status, lest av enhetenes (§2.2 i notatet).

    Den mest aktive vinner: står én bil i `Fremme` og én i `Ledig`, er
    oppdraget i `Fremme`. `Ledig` bare når alle er ledige — det er da tavla
    kan ryddes. Uten koblingsrader (kan ikke skje etter `0011`, men
    `Oppdrag.save` kjører før raden finnes) står cachen som den er.
    """
    statuser = list(oppdrag.enheter.values_list('status', flat=True))
    if not statuser:
        return oppdrag.status
    aktive = [s for s in statuser if s != choices.LEDIG]
    if not aktive:
        return choices.LEDIG
    return max(aktive, key=choices.KJEDEN.index)


def aktiv_koblingsrad(enhet, vakt=None):
    """Enhetens påbegynte koblingsrad, eller ``None``.

    Påbegynt betyr «har passert `venter` og er ikke avsluttet». En rad som
    ligger og venter teller ikke: enheten har ikke rykket ut, og kan fortsatt
    sendes et annet sted.
    """
    qs = (Oppdragsenhet.objects
          .filter(enhet=enhet)
          .exclude(status__in=(choices.VENTER, choices.LEDIG))
          .select_related('oppdrag', 'oppdrag__enhet', 'oppdrag__lokasjon'))
    if vakt is not None:
        qs = qs.filter(oppdrag__vakt=vakt)
    return qs.order_by('-oppdrag__created_at').first()


def aktivt_oppdrag(enhet, vakt=None):
    """Enhetens påbegynte oppdrag, eller ``None``. Se `aktiv_koblingsrad`."""
    rad = aktiv_koblingsrad(enhet, vakt)
    return rad.oppdrag if rad is not None else None


def ventende_oppdrag(enhet, vakt=None):
    """Oppdrag enheten er varslet på, men ikke har påbegynt."""
    qs = Oppdrag.objects.filter(enheter__enhet=enhet, enheter__status=choices.VENTER)
    if vakt is not None:
        qs = qs.filter(vakt=vakt)
    return qs.order_by('created_at').distinct()


def enhet_status(enhet, vakt=None) -> dict:
    """Enhetens status til sentralbordet — **utledet, aldri lagret**.

    Ved vaktstart står alle enheter som `Ledig`, og det er ikke en verdi noen
    setter: det er hva «ingen påbegynte oppdrag» ser ut som. En lagret status
    måtte nullstilles ved vaktstart og holdes i takt med oppdragsradene resten
    av vakta, og to kilder til samme sannhet går i utakt første gang noe
    feiler halvveis. Da er det den lagrede som lyver — den ser autoritativ ut.

    ``Ledig (2 venter)`` er distinksjonen 113 trenger for å vite hvem som kan
    sendes: enheten har fått to oppdrag, men ikke rykket ut på noen av dem.
    """
    rad = aktiv_koblingsrad(enhet, vakt)
    aktivt = rad.oppdrag if rad is not None else None
    antall_ventende = ventende_oppdrag(enhet, vakt).count()
    return {
        # Koblingsraden er *enhetens* status på oppdraget — med flere enheter
        # er ikke oppdragets status hennes.
        'koblingsrad': rad,
        'enhet': enhet,
        'status': rad.status if rad else choices.LEDIG,
        'status_navn': (
            rad.get_status_display() if rad else choices.STATUS_NAVN[choices.LEDIG]
        ),
        'aktivt_oppdrag': aktivt,
        'antall_ventende': antall_ventende,
    }


# ── Overganger ───────────────────────────────────────────────────────────────

class UlovligOvergang(Exception):
    """Overgangen finnes ikke i tabellen over."""


@transaction.atomic
def sett_status(oppdrag, ny_status: str, *, bruker=None, tidspunkt=None,
                forsinket: bool = False, automatisk: bool = False,
                sted: str = '', enhet=None) -> Statusmelding:
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
    # **Per enhet fra 11. sep. 2026.** Uten `enhet` er det den primære —
    # slik all eldre kode og alle eldre tester mener det.
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise UlovligOvergang('Enheten er ikke varslet på oppdraget.')
    if not kan_gaa_til(rad.status, ny_status):
        raise UlovligOvergang(
            f'Kan ikke gå fra {rad.status!r} til {ny_status!r}.'
        )
    # Stedet hører til «Avreist» og ingen annen status. Sjekken ligger her og
    # ikke bare i viewet, av samme grunn som overgangssjekken: alle veier inn
    # skal gjennom den.
    if sted and (ny_status != choices.AVREIST or sted not in choices.AVREIST_TIL_NAVN):
        raise ValueError(f'Ugyldig sted {sted!r} for status {ny_status!r}.')

    melding = Statusmelding.objects.create(
        oppdrag=oppdrag,
        oppdragsenhet=rad,
        status=ny_status,
        tidspunkt=tidspunkt or timezone.now(),
        meldt_av=bruker,
        forsinket=forsinket,
        automatisk=automatisk,
        sted=sted or '',
    )
    rad.status = ny_status
    rad.save(update_fields=['status', 'updated_at'])
    # Oppdragets status er utledet: den mest aktive enheten, `Ledig` når
    # alle er det. Én enhet gir samme svar som før.
    oppdrag.status = utledet_status(oppdrag)
    felter = ['status', 'updated_at']

    if oppdrag.status == choices.TERMINAL and oppdrag.historikk_fra is None:
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
                  forsinket: bool = False, enhet=None) -> Statusmelding:
    """Enheten rykker ut. Lukker et eventuelt pågående oppdrag automatisk.

    En enhet kan ha flere tildelte oppdrag, men bare ett påbegynt. Trykkes
    `Rykker ut` mens et annet er i gang, settes det pågående til `Ledig` med
    **samme tidsstempel**, og meldingen merkes ``automatisk=True``.

    Kostnaden er notert i beslutningsnotatet §4.3: den `Ledig`-meldingen er
    avledet, ikke målt — sluttiden for det forrige oppdraget blir starttiden
    for det neste. Flagget gjør at statistikken kan skille dem.
    """
    naa = tidspunkt or timezone.now()
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise UlovligOvergang('Enheten er ikke varslet på oppdraget.')

    # Per enhet: det er *hennes* pågående som lukkes, ikke oppdragets.
    pagaende = aktiv_koblingsrad(rad.enhet, oppdrag.vakt)
    if pagaende is not None and pagaende.oppdrag_id != oppdrag.pk:
        sett_status(pagaende.oppdrag, choices.LEDIG, bruker=bruker,
                    tidspunkt=naa, automatisk=True, enhet=rad.enhet)

    return sett_status(oppdrag, choices.RYKKER_UT, bruker=bruker,
                       tidspunkt=naa, forsinket=forsinket, enhet=rad.enhet)


def varsle_enhet(oppdrag, enhet, *, bruker=None) -> Oppdragsenhet:
    """Sett en enhet til på oppdraget — i `Venter`, sist i rekka.

    Et ferdig oppdrag som får en enhet til er ikke ferdig lenger: statusen
    utledes på nytt, og er det ryddet til historikken, hentes det tilbake.
    """
    if oppdrag.enheter.filter(enhet=enhet).exists():
        raise ValueError(f'«{enhet.navn}» er alt varslet på oppdraget.')
    neste = (oppdrag.enheter.aggregate(models.Max('rekkefolge'))['rekkefolge__max'] or 0) + 1
    rad = Oppdragsenhet.objects.create(
        oppdrag=oppdrag, enhet=enhet, varslet_av=bruker, rekkefolge=neste)
    oppdrag.status = utledet_status(oppdrag)
    felter = ['status', 'updated_at']
    if oppdrag.historikk_fra is not None:
        oppdrag.historikk_fra = None
        oppdrag.historikk_av = None
        felter += ['historikk_fra', 'historikk_av']
    oppdrag.save(update_fields=felter)
    return rad


def ta_av_enhet(oppdrag, enhet) -> None:
    """Ta en enhet av oppdraget — bare mens den venter, og aldri den siste.

    Har bilen rykket ut, er det en hendelse: da er svaret `Ledig` fra bilen
    eller en føring fra sentralbordet (§9), ikke å late som den aldri var der.
    """
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise ValueError(f'«{enhet.navn}» er ikke varslet på oppdraget.')
    if rad.status != choices.VENTER:
        raise ValueError(
            f'«{enhet.navn}» har rykket ut ({rad.get_status_display()}) — '
            'meld ledig i stedet.')
    if oppdrag.enheter.count() == 1:
        raise ValueError('Oppdraget må ha minst én enhet.')
    rad.delete()
    if oppdrag.enhet_id == enhet.pk:
        # Den gamle kolonnen (deploy 1) skal peke på en som fortsatt er der.
        oppdrag.enhet = oppdrag.primaer.enhet
    oppdrag.status = utledet_status(oppdrag)
    oppdrag.save(update_fields=['status', 'enhet', 'updated_at'])


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
        oppdragsenhet=melding.oppdragsenhet,
        status=melding.status,
        tidspunkt=nytt_tidspunkt,
        meldt_av=bruker,
        # Rettingen er meldt av et menneske ved en tastatur, uansett hva den
        # retter. Flaggene beskriver denne raden, ikke den den erstatter.
        forsinket=False,
        automatisk=False,
        korrigerer=melding,
        # Stedet følger med: en retting av klokkeslettet er ikke en retting
        # av hvor bilen dro, og en rad uten sted ville lest som «ukjent».
        sted=melding.sted,
    )


@transaction.atomic
def flytt_til_enhet(oppdrag, ny_enhet, *, bruker, fra_enhet=None) -> Enhetsbytte | None:
    """Flytt oppdraget til en annen enhet, og skriv det i oppdragets logg.

    Returnerer ``None`` hvis enheten er den samme — et bytte til seg selv er
    ikke en hendelse.

    Statusen står. Meldingene den første enheten rakk å sende blir stående med
    ``meldt_av`` intakt: de skjedde.
    """
    rad = koblingsrad(oppdrag, fra_enhet)
    if rad is None:
        raise ValueError('Enheten er ikke varslet på oppdraget.')
    if rad.enhet_id == ny_enhet.pk:
        return None
    if oppdrag.enheter.filter(enhet=ny_enhet).exists():
        raise ValueError(f'«{ny_enhet.navn}» er alt varslet på oppdraget.')

    bytte = Enhetsbytte.objects.create(
        oppdrag=oppdrag,
        fra_enhet=rad.enhet,
        til_enhet=ny_enhet,
        byttet_av=bruker,
    )
    gammel = rad.enhet_id
    rad.enhet = ny_enhet
    rad.save(update_fields=['enhet', 'updated_at'])
    if oppdrag.enhet_id == gammel:
        # Den gamle kolonnen følger den primære til deploy 2 fjerner den.
        oppdrag.enhet = ny_enhet
        oppdrag.save(update_fields=['enhet', 'updated_at'])
    return bytte


# ── Synlighet for enheten ────────────────────────────────────────────────────

#: Hvor lenge et avsluttet oppdrag blir stående på enhetsskjermen.
SKJUL_ETTER_LEDIG = 30 * 60   # sekunder


def synlige_for_enhet(enhet, vakt=None):
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

    # Per koblingsrad (11. sep. 2026): det er *bilens* ledig-melding vinduet
    # måles mot, ikke oppdragets — den andre bilen kan fortsatt kjøre.
    rader = (Oppdragsenhet.objects.filter(enhet=enhet)
             .select_related('oppdrag', 'oppdrag__lokasjon', 'oppdrag__enhet'))
    if vakt is not None:
        rader = rader.filter(oppdrag__vakt=vakt)

    grense = timezone.now() - timedelta(seconds=SKJUL_ETTER_LEDIG)
    ut = []
    for rad in rader.order_by('oppdrag__created_at'):
        if rad.status != choices.LEDIG:
            ut.append(rad.oppdrag)
            continue
        melding = Statusmelding.objects.gjeldende_for_status(
            rad.oppdrag, choices.LEDIG, oppdragsenhet=rad)
        if melding is not None and melding.tidspunkt > grense:
            ut.append(rad.oppdrag)
    return ut
