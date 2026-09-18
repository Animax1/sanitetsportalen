"""Forretningslogikk for oppdragsmodulen.

Statusmaskinen ligger her som **data**, ikke som ``if``-er spredt i viewene.
Grensesnittet viser kun lovlige knapper, men det er ikke der regelen bor: en
knapp som ikke vises er ikke en knapp som ikke kan trykkes.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone

# **Én vei, og den går gjennom `core`.** `core.notifications` er rammeverket,
# ikke en annen modul — samme retning som `core.backup` og `core.arkiv`.
from core.notifications import notify

from . import choices
from .models import (Enhetsbytte, Enhetshendelse, Oppdrag, Oppdragsenhet,
                     Statusmelding, Vaktmodusperiode)

logger = logging.getLogger(__name__)

# ── Statusmaskinen ───────────────────────────────────────────────────────────
#
# `ledig` er utgang fra enhver status, ikke et ledd i kjeden. Den står derfor
# i hver rad, ikke bare til slutt.

OVERGANGER: dict[str, frozenset[str]] = {
    choices.VENTER:    frozenset({choices.RYKKER_UT, choices.LEDIG}),
    choices.RYKKER_UT: frozenset({choices.FREMME, choices.LEDIG}),
    # «Behandlet på sted» (12. sep. 2026): sidegrenen fra Fremme.
    choices.FREMME:    frozenset({choices.AVREIST, choices.BEHANDLET, choices.LEDIG}),
    choices.AVREIST:   frozenset({choices.LEVERER, choices.LEDIG}),
    choices.LEVERER:   frozenset({choices.LEDIG}),
    choices.BEHANDLET: frozenset({choices.LEDIG}),
    choices.LEDIG:     frozenset(),          # terminal
}

#: **Bilens** vei til `Ledig` (André, 12. sep. 2026): bare fra Leverer og
#: Behandlet. I Rykker ut heter utgangen «Avbryt», i Fremme «Behandlet på
#: sted», og mellom Avreist og Leverer finnes ingen — hun har en pasient i
#: bilen. Tabellen over er fortsatt fasit for *sentralen*, som retter og
#: fører alt; dette er hva stemplingsendepunktet slipper gjennom.
BILEN_KAN_LEDIG_FRA: frozenset[str] = frozenset({choices.LEVERER, choices.BEHANDLET})

#: Den andre knappen i bilen per status: `Avbryt` i Rykker ut, `Behandlet på
#: sted` i Fremme. Ellers ingen. Verdien er navnet i URL-en.
ALTERNATIV: dict[str, tuple[str, str]] = {
    choices.RYKKER_UT: (choices.AVBRYT, 'Avbryt'),
    choices.FREMME: (choices.BEHANDLET, 'Behandlet på sted'),
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
    # Utgangene til Ledig (12. sep. 2026): «neste» etter Leverer og etter
    # Behandlet er Ledig — bilen har ikke lenger en egen Ledig-knapp.
    if fra in BILEN_KAN_LEDIG_FRA:
        return choices.LEDIG
    try:
        i = choices.KJEDEN.index(fra)
    except ValueError:
        return None
    if i + 1 >= len(choices.KJEDEN):
        return None
    return choices.KJEDEN[i + 1]


def alternativ_for(fra: str):
    """``(overgang, navn)`` for den andre knappen i bilen, eller ``None``."""
    return ALTERNATIV.get(fra)


# ── Oppdragsnummer ───────────────────────────────────────────────────────────

#: Nøkkelen i `AppSetting` som holder neste ledige nummer for én vakt.
#: Per vakt siden deploy 2: nummeret restarter på 1 hver vakt slik at det
#: holder seg kort nok til å leses opp på samband, og «oppdrag 14» aldri er
#: tvetydig innenfor vakta.
def _nummer_nokkel(vakt) -> str:
    return f'next_oppdrag_nr_vakt_{vakt.pk}'


def oppdragsnr(nummer) -> str:
    """`O45` — oppdragsnummeret slik det skrives der plassen er trang (§6 i
    KO-notatet). Var `#45` til 18. sep. 2026; byttet samtidig som hendelsene
    fikk `H12`, fordi `#45` og `H12` på nabolinjer i KO-loggen ikke er
    utvetydige — og det er i loggen de møtes.

    **Formen står ett sted.** Alt som skriver nummeret som tekst kaller hit —
    `Enhetshendelse.detalj`, bjellevarselet, `__str__` og KO-loggens
    systemlinjer — og `oppdragsnr()` i `static/js/oppdrag-kort.js` er den
    samme regelen på klientsida.
    """
    return f'O{nummer}'


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
    from core.models import AppSetting  # noqa: WPS433

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
    status = utledet_av_statuser(statuser)
    # Alle ledige, men oppdraget er ikke ferdig: bilen rykket videre, og
    # tavla skal vise at det trengs en ny ressurs (12. sep. 2026).
    if status == choices.LEDIG and oppdrag.trenger_ressurs:
        return choices.VENTER
    return status


def utledet_av_statuser(statuser) -> str:
    """Regelen i `utledet_status`, på en liste statuser — delt med
    statistikken, som regner på arkivrader uten et oppdragsobjekt."""
    aktive = [s for s in statuser if s != choices.LEDIG]
    if not aktive:
        return choices.LEDIG
    return max(aktive, key=lambda s: choices.AKTIVITET.get(s, -1))


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


class ProblemstillingUdefinert(UlovligOvergang):
    """`Ledig` på et oppdrag som fortsatt står som «Udefinert». Egen klasse
    fordi svaret er et annet: ikke «skjermen er utdatert», men «sett
    problemstillingen først»."""



@transaction.atomic
def _aktivt_oppdrag_felter(rad) -> dict:
    """Feltene enhetskortet viser om det aktive oppdraget.

    Alle `None` når det ikke finnes noe, slik at kortet kan lese dem uten å
    spørre. `rad` er enhetens koblingsrad: statusen og tidspunktet er *hennes*.
    """
    from .models import Statusmelding

    if rad is None:
        return {'oppdragsnummer': None, 'hastegrad': None, 'grovsortering': None,
                'grovsortering_navn': None, 'problemstilling': None, 'antall': None,
                'status_tidspunkt': None, 'sted_navn': ''}
    oppdrag = rad.oppdrag
    melding = Statusmelding.objects.gjeldende_for_status(
        oppdrag, rad.status, oppdragsenhet=rad)
    return {
        'oppdragsnummer': oppdrag.oppdragsnummer,
        'hastegrad': oppdrag.hastegrad,
        'grovsortering': oppdrag.grovsortering,
        'grovsortering_navn': choices.GROVSORTERING_NAVN.get(oppdrag.grovsortering, ''),
        'problemstilling': oppdrag.problemstilling,
        'antall': oppdrag.antall,
        'status_tidspunkt': melding.tidspunkt.isoformat() if melding else None,
        'sted_navn': choices.AVREIST_TIL_NAVN.get(melding.sted, '') if melding else '',
    }


def enhetskort(enhet, vakt=None, ledig_siden=None) -> dict:
    """Alt et enhetskort viser — **den ene kilden, to lesere**.

    Sentralbordet (`oppdrag.views.enheter_view`) og KOs ressursoversikt
    (`ko.services.ressursbildet`) tegner samme kort, og skal derfor lese samme
    felter. Lå serialiseringen i viewet, ville KO fått en kopi — og kopien
    ville manglet neste felt noen la til her, uten at noe ble rødt. Feature
    parity som holder, er den som følger av konstruksjonen (André, 17. sep.
    2026: «Jeg vil ha det likt feature messig inn her i /ko»).

    `ledig_siden` sendes inn av den som henter mange kort: `ledig_siden_bulk()`
    svarer for hele lista i én spørring, og et oppslag per enhet ville vært N
    spørringer på en liste som polles hvert tiende sekund.
    """
    info = enhet_status(enhet, vakt)
    return {
        'id': enhet.pk,
        'navn': enhet.navn,
        'pa_vakt': enhet.pa_vakt,
        # Merket vises bare der det betyr noe: en ambulanse har ingen passiv
        # vakt, og «Aktiv» på henne ville vært støy.
        'kan_passiv_vakt': kan_passiv_vakt(enhet),
        'kan_avvente': kan_avvente(enhet),
        'passiv_vakt': enhet.passiv_vakt,
        'er_aktiv': enhet.er_aktiv,
        'username': getattr(enhet.user, 'username', '') or '',
        'type': enhet.enhetstype_id,
        'type_navn': enhet.enhetstype.navn if enhet.enhetstype else '',
        'type_rekkefolge': (enhet.enhetstype.rekkefolge
                            if enhet.enhetstype else None),
        'status': info['status'],
        'status_navn': info['status_navn'],
        'antall_ventende': info['antall_ventende'],
        'aktivt_oppdrag_id': (
            info['aktivt_oppdrag'].pk if info['aktivt_oppdrag'] else None),
        # **Bare for den som faktisk er ledig.** Står hun på et oppdrag, er
        # «ledig siden» forrige gang hun var det — et tall som ser ut som
        # nåtid og ikke er det.
        'ledig_siden': (
            ledig_siden.isoformat()
            if info['status'] == choices.LEDIG and ledig_siden else None),
        **_aktivt_oppdrag_felter(info['koblingsrad']),
    }


def sett_status(oppdrag, ny_status: str, *, bruker=None, tidspunkt=None,
                forsinket: bool = False, automatisk: bool = False,
                sted: str = '', enhet=None, manuell: bool = False,
                avbrutt: bool = False) -> Statusmelding:
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
    # «Udefinert» må bort før bilen slås ledig (André, 12. sep. 2026): et
    # ferdig oppdrag uten problemstilling er en statistikk som ikke svarer.
    # Den automatiske lukkingen slipper — den er ikke et valg bilen tar.
    if (ny_status == choices.LEDIG and not automatisk and not avbrutt
            and oppdrag.problemstilling == choices.UDEFINERT):
        raise ProblemstillingUdefinert(
            'Problemstillingen står som «Udefinert». Meld problemstillingen til KO, '
            'så setter sentralbordet den — først da kan enheten meldes ledig.')
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
        manuell=manuell,
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
        forrige = pagaende.oppdrag
        # **Det forrige oppdraget er ikke ferdig** (André, 12. sep. 2026):
        # bilen dro, men noen må fortsatt ta det. Var hun den siste som
        # ikke var ledig, blir det stående på tavla som «trenger ny
        # ressurs» i stedet for å ryddes til historikken. Flagget settes
        # *før* lukkingen, så `utledet_status` ser det.
        # **Samme regel som ved Avbryt** (15. sep. 2026): en bil som rykket
        # videre fra et oppdrag noen andre alt hadde løst, etterlater ikke et
        # oppdrag som trenger ny ressurs.
        if trenger_ny_ressurs(forrige, utenom_rad=pagaende):
            forrige.trenger_ressurs = True
            forrige.trenger_ressurs_siden = naa
            forrige.save(update_fields=['trenger_ressurs', 'trenger_ressurs_siden', 'updated_at'])
        sett_status(forrige, choices.LEDIG, bruker=bruker,
                    tidspunkt=naa, automatisk=True, enhet=rad.enhet)
        Enhetshendelse.objects.create(
            oppdrag=forrige, enhet=rad.enhet, type=Enhetshendelse.RYKKET_VIDERE,
            tidspunkt=naa, av=bruker, detalj=oppdragsnr(oppdrag.oppdragsnummer))

    les_bjellevarselet(oppdrag, rad)
    return sett_status(oppdrag, choices.RYKKER_UT, bruker=bruker,
                       tidspunkt=naa, forsinket=forsinket, enhet=rad.enhet)


def les_bjellevarselet(oppdrag, rad) -> None:
    """Merk bjelleraden lest når bilen rykker ut på oppdraget.

    **Uten dette hoper bjella seg opp gjennom vakta.** Varselet har gjort
    jobben sin i det hun trykker «Rykker ut» — hun har sett oppdraget — og
    et ulest-tall som bare vokser blir et tall ingen ser på.

    Kaster aldri, av samme grunn som `varsle_bjelle`: et ulest varsel er et
    savn, en utrykning som stopper er en feil."""
    from core.models import Notification

    bruker_id = getattr(rad.enhet, 'user_id', None)
    if bruker_id is None:
        return
    try:
        with transaction.atomic():
            (Notification.objects
             .filter(user_id=bruker_id, kind=bjellenokkel(oppdrag), is_read=False)
             .update(is_read=True, read_at=timezone.now()))
    except Exception:   # noqa: BLE001 — se docstringen
        logger.warning('oppdrag: kunne ikke merke bjellevarselet lest for %s',
                       rad.enhet_id, exc_info=True)


def ledig_siden_bulk(enheter, vakt=None) -> dict:
    """Når hver enhet sist ble meldt **Ledig** i denne vakta.

    André, 15. sep. 2026: «I /oppdrag/ kan vi se i ressurser-delen tidsstempel
    med når det ble slått ledig.» Operatøren som skal sende noen, vil vite hvem
    som har stått lengst — og det tallet finnes bare i statusmeldingene.

    **Bulk, som `avbrutt_av_bulk`:** ressurslista tegnes ved hver polling, og
    ett oppslag per enhet ville vært N spørringer hvert tiende sekund.

    **Korreksjoner teller.** Retter operatøren tidspunktet for `Ledig`, er det
    det rettede som gjelder — samme regel som `Statusmelding.gjeldende()`. De
    overstyrte radene hentes i sitt eget spørsmål framfor å utledes av
    utvalget: en korreksjon kan i prinsippet ligge utenfor det vi nettopp
    hentet, og en `overstyrte`-liste som bare kjenner sine egne rader ville
    lest det gamle tidspunktet uten å si fra.
    """
    ider = [getattr(e, 'pk', e) for e in enheter]
    if not ider:
        return {}
    qs = Statusmelding.objects.filter(
        status=choices.LEDIG, oppdragsenhet__enhet_id__in=ider)
    if vakt is not None:
        qs = qs.filter(oppdrag__vakt=vakt)
    rader = list(qs.values_list('pk', 'oppdragsenhet__enhet_id', 'tidspunkt'))
    if not rader:
        return {}
    overstyrte = set(
        Statusmelding.objects
        .filter(korrigerer_id__in=[pk for pk, _, _ in rader])
        .values_list('korrigerer_id', flat=True))
    ut: dict = {}
    for pk, enhet_id, tidspunkt in rader:
        if pk in overstyrte:
            continue
        if enhet_id not in ut or tidspunkt > ut[enhet_id]:
            ut[enhet_id] = tidspunkt
    return ut


def gjeldende_modus(enhet) -> str:
    """«aktiv», «passiv» eller tom streng.

    Tom for enheter uten passiv vakt i det hele tatt — som er de fleste. Da
    står det ingenting i merket, og `varslet_modus` sier «dette spørsmålet
    gjaldt ikke henne», ikke «hun var aktiv».
    """
    if not kan_passiv_vakt(enhet):
        return ''
    return (Vaktmodusperiode.PASSIV if enhet.passiv_vakt
            else Vaktmodusperiode.AKTIV)


def kan_passiv_vakt(enhet) -> bool:
    """Tillater enhetstypen passiv vakt?

    Flagget bor på typen, ikke på enheten (André, 16. sep. 2026), så «Lege 03»
    opprettet midt i arrangementet arver det av seg selv. En enhet **uten**
    type arver ingenting — det er riktig standard, men verdt å kjenne: en
    konto opprettet som «bil» får ingen type, og må få den satt.
    """
    return bool(enhet.enhetstype_id and enhet.enhetstype.kan_passiv_vakt)


def kan_avvente(enhet) -> bool:
    """Tillater enhetstypen at operatøren setter «avventer»?

    Eget flagg, ikke en avledning av `kan_passiv_vakt`: en frivillig enhet
    som alltid er aktiv kan godt ha lov til å si nei.
    """
    return bool(enhet.enhetstype_id and enhet.enhetstype.kan_avvente)


@transaction.atomic
def sett_vaktmodus(enhet, *, passiv: bool, vakt, bruker=None) -> bool:
    """Sett enheten i aktiv eller passiv vakt. True hvis noe endret seg.

    **Både tilstanden og perioden skrives, og det er hele poenget.**
    `Enhet.passiv_vakt` svarer på hva som gjelder nå; `Vaktmodusperiode`
    svarer på hvor lenge. Skrives bare det første, finnes ikke timene — og de
    kan ikke fylles inn med tilbakevirkende kraft.

    Idempotent: settes samme modus to ganger, skjer ingenting. Ellers ville
    to klikk på samme knapp delt perioden i to og sett ut som et vaktbytte.
    """
    if not kan_passiv_vakt(enhet):
        raise ValueError(f'«{enhet.navn}» har en enhetstype uten passiv vakt.')
    ny = Vaktmodusperiode.PASSIV if passiv else Vaktmodusperiode.AKTIV
    apen = (Vaktmodusperiode.objects
            .filter(enhet=enhet, vakt=vakt, til__isnull=True).first())
    if apen is not None and apen.modus == ny:
        return False
    naa = timezone.now()
    if apen is not None:
        apen.til = naa
        apen.save(update_fields=['til', 'updated_at'])
    Vaktmodusperiode.objects.create(
        enhet=enhet, vakt=vakt, modus=ny, fra=naa, satt_av=bruker)
    enhet.passiv_vakt = passiv
    enhet.save(update_fields=['passiv_vakt', 'updated_at'])
    return True


def avventende_enhet_ider(oppdrag) -> set:
    """Enhetene som står som «avventer» på oppdraget **nå**.

    Avventingen varer til hun rykker ut: har koblingsraden forlatt `Venter`,
    er hendelsen historikk. Det er derfor avvente ikke trenger en egen
    tilstand å nullstille — og en tilstand som må nullstilles er en tilstand
    som blir stående når noe feiler halvveis.
    """
    avventer = set(
        oppdrag.enhetshendelser.filter(type=Enhetshendelse.AVVENTER)
        .values_list('enhet_id', flat=True))
    if not avventer:
        return set()
    venter = set(oppdrag.enheter.filter(status=choices.VENTER)
                 .values_list('enhet_id', flat=True))
    return avventer & venter


@transaction.atomic
def avvent_oppdrag(oppdrag, enhet, *, bruker=None, tidspunkt=None) -> Enhetshendelse:
    """Operatøren setter enheten til «avventer» (André, 15. sep. 2026).

    «Ved utalarmering til spesialressurser kan operatøren trykke avvente hvis
    ressursen sier på nødnett at de ikke kan ta oppdraget.»

    **Hun blir stående varslet.** Koblingsraden røres ikke, så operatøren kan
    trykke «Rykk ut» på henne senere, og begge deler står i loggen. Det er
    forskjellen på dette og å ta henne av oppdraget.

    **Og oppdraget kan bli stående uten ressurs.** Avventer hun mens en bil er
    på vei, skjer ingenting; er hun alene, trengs en ny —
    `trenger_ny_ressurs()` svarer på begge, som den gjorde for «avbrutt».
    """
    if not kan_avvente(enhet):
        raise ValueError(f'«{enhet.navn}» har en enhetstype uten avventing.')
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise UlovligOvergang('Enheten er ikke varslet på oppdraget.')
    if rad.status != choices.VENTER:
        raise UlovligOvergang('Avvente finnes bare før enheten har rykket ut.')
    naa = tidspunkt or timezone.now()
    hendelse = Enhetshendelse.objects.create(
        oppdrag=oppdrag, enhet=enhet, type=Enhetshendelse.AVVENTER,
        tidspunkt=naa, av=bruker)
    if trenger_ny_ressurs(oppdrag, utenom_rad=rad):
        oppdrag.trenger_ressurs = True
        oppdrag.trenger_ressurs_siden = naa
        oppdrag.save(update_fields=['trenger_ressurs', 'trenger_ressurs_siden',
                                    'updated_at'])
    return hendelse


def avventer_av_bulk(oppdrag_ider) -> dict:
    """Hvem som avventer, for en hel liste — to spørsmål, ikke to per rad.

    Samme grunn som `avbrutt_av_bulk`: tavla tegnes ved hver polling, og
    `avventende_enhet_ider()` gjør to oppslag i seg selv. Kalt per rad ble det
    2N spørringer hvert tiende sekund — fanget av
    `OppdragslistaStatustidspunktTests`, som er nettopp den vakten.
    """
    ider = list(oppdrag_ider)
    if not ider:
        return {}
    hendelser = list(Enhetshendelse.objects
                     .filter(oppdrag_id__in=ider, type=Enhetshendelse.AVVENTER)
                     .values_list('oppdrag_id', 'enhet_id'))
    if not hendelser:
        return {}
    # Avventingen varer til hun rykker ut, så bare radene som fortsatt står i
    # `Venter` teller — se `avventende_enhet_ider`.
    navn = {
        (o, e): n for o, e, n in
        Oppdragsenhet.objects.filter(oppdrag_id__in=ider, status=choices.VENTER)
        .values_list('oppdrag_id', 'enhet_id', 'enhet__navn')
    }
    ut: dict = {}
    for oppdrag_id, enhet_id in hendelser:
        treff = navn.get((oppdrag_id, enhet_id))
        if treff is not None:
            ut.setdefault(oppdrag_id, []).append(treff)
    for rader in ut.values():
        rader.sort()
    return ut


def kvitter_avbrutt(oppdrag, *, bruker=None) -> int:
    """Merk oppdragets ukvitterte avbrytelser som besvart. Antall rader.

    To veier inn, og begge er «operatøren har tatt stilling»: hun sender en ny
    enhet (`varsle_enhet` kaller hit), eller hun kvitterer manuelt fordi ingen
    skal sendes.
    """
    return (oppdrag.enhetshendelser
            .filter(type=Enhetshendelse.AVBRUTT, kvittert_at__isnull=True)
            .update(kvittert_at=timezone.now(), kvittert_av=bruker))


def avbrutt_av(oppdrag) -> list[str]:
    """Navnene på enhetene som avbrøt og **ikke er kvittert**, i rekkefølge.

    Merket skal stå til noen har tatt stilling (André, 15. sep. 2026: «det må
    vises, og at det må løses av operatør»). Kvitteringen skjer enten ved at
    en ny enhet varsles, eller manuelt når ingen skal sendes — se
    `kvitter_avbrutt`.
    """
    return [h.enhet.navn for h in
            oppdrag.enhetshendelser.filter(type=Enhetshendelse.AVBRUTT,
                                           kvittert_at__isnull=True)
            .select_related('enhet').order_by('tidspunkt')]


def avbrutt_av_bulk(oppdrag_ider) -> dict:
    """Samme, for en hel liste — ett spørsmål, ikke ett per rad.

    Samme grunn som `Statusmelding.objects.gjeldende_bulk`: sentralbordet
    tegner tavla ved hver polling, og et oppslag per oppdrag blir N spørringer
    hvert tiende sekund.
    """
    ut: dict = {}
    rader = (Enhetshendelse.objects
             .filter(oppdrag_id__in=list(oppdrag_ider), type=Enhetshendelse.AVBRUTT,
                     kvittert_at__isnull=True)
             .select_related('enhet').order_by('tidspunkt'))
    for h in rader:
        ut.setdefault(h.oppdrag_id, []).append(h.enhet.navn)
    return ut


#: Statusene som betyr at en enhet **løste** oppdraget. Nås en av dem, trengs
#: ingen ny ressurs — uansett hva de andre bilene gjorde etterpå.
#:
#: `Ledig` står ikke her, og det er hele poenget: en bil er ledig både når hun
#: er ferdig og når hun avbrøt. Leses `Ledig` som «ferdig», blir de to det
#: samme — se `trenger_ny_ressurs()`.
LOSER_OPPDRAGET = (choices.BEHANDLET, choices.LEVERER)


def noen_loste_oppdraget(oppdrag) -> bool:
    """Har noen enhet nådd Behandlet eller Leverer på dette oppdraget?

    Leses av statusmeldingene og ikke av koblingsradene, fordi raden går
    videre til `Ledig` etterpå: `behandle_paa_sted` skriver Behandlet og Ledig
    med samme tidspunkt, så raden ender ledig selv om jobben ble gjort.

    En korreksjon erstatter tidspunktet, ikke hendelsen, så `.exists()` er
    riktig spørsmål — `gjeldende()` ville svart det samme og kostet mer.
    """
    return Statusmelding.objects.filter(
        oppdrag=oppdrag, status__in=LOSER_OPPDRAGET).exists()


def trenger_ny_ressurs(oppdrag, *, utenom_rad) -> bool:
    """Står oppdraget igjen uten noen som tar det?

    **Buggen dette retter** (André, 15. sep. 2026): «akutt oppdrag, to enheter
    varsles. Ene bilen behandler på stedet, andre bil slo avbrutt. Da står det
    trenger ressurs selv om oppdraget er løst.»

    Regelen var «finnes det andre enheter som ikke er ledige» — og den kan
    ikke skille en bil som ble ledig fordi hun *ble ferdig* fra en som ble
    ledig fordi hun *avbrøt*. Begge deler er `Ledig` på koblingsraden.

    To spørsmål må stilles, ikke ett: er noen fortsatt på vei, **og** var noen
    framme. Er svaret nei på begge, trengs en ny ressurs.
    """
    # **Den som avventer er ikke på vei** (16. sep. 2026). Hun står i
    # `Venter` som alle andre varslede, og uten dette leddet ville en
    # avventing skjult behovet i stedet for å vise det — altså det motsatte
    # av hva knappen finnes for.
    avventende = avventende_enhet_ider(oppdrag)
    andre_aktive = any(
        rad.enhet_id not in avventende
        for rad in oppdrag.enheter.exclude(pk=utenom_rad.pk)
                          .exclude(status=choices.LEDIG))
    return not andre_aktive and not noen_loste_oppdraget(oppdrag)


@transaction.atomic
def avbryt_oppdrag(oppdrag, *, bruker=None, tidspunkt=None,
                   forsinket: bool = False, enhet=None) -> Statusmelding:
    """Bilen trykker «Avbryt» i Rykker ut (André, 12. sep. 2026).

    Hun meldes ledig på oppdraget, og oppdraget går tilbake til Venter hos
    sentralen som «trenger ny ressurs» — samme spor som når hun rykker videre
    (`start_oppdrag`), men uten et nytt oppdrag å dra til. Bare fra Rykker ut:
    er hun framme, er svaret «Behandlet på sted» eller Avreist.

    `Ledig`-meldingen er ekte, ikke automatisk — tidspunktet er målt. Men
    «Udefinert» sperrer ikke: hun har ikke sett pasienten, og problemstillingen
    er sentralens sak når en ny bil sendes.
    """
    naa = tidspunkt or timezone.now()
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise UlovligOvergang('Enheten er ikke varslet på oppdraget.')
    if rad.status != choices.RYKKER_UT:
        raise UlovligOvergang('Avbryt finnes bare i Rykker ut.')
    if trenger_ny_ressurs(oppdrag, utenom_rad=rad):
        oppdrag.trenger_ressurs = True
        oppdrag.trenger_ressurs_siden = naa
        oppdrag.save(update_fields=['trenger_ressurs', 'trenger_ressurs_siden', 'updated_at'])
    melding = sett_status(oppdrag, choices.LEDIG, bruker=bruker, tidspunkt=naa,
                          forsinket=forsinket, enhet=rad.enhet, avbrutt=True)
    Enhetshendelse.objects.create(
        oppdrag=oppdrag, enhet=rad.enhet, type=Enhetshendelse.AVBRUTT,
        tidspunkt=naa, av=bruker)
    return melding


@transaction.atomic
def behandle_paa_sted(oppdrag, *, bruker=None, tidspunkt=None,
                      forsinket: bool = False, enhet=None) -> Statusmelding:
    """«Behandlet på sted så ledig» (André, 12. sep. 2026): ett trykk i bilen
    skriver Behandlet og Ledig med samme tidspunkt. Ledig-meldingen er
    **målt**, ikke avledet — det var da hun var ferdig — så den er ikke
    `automatisk`, og statistikken teller oppdragstiden.

    Udefinert sjekkes før noe skrives: ellers hadde raden stått i Behandlet
    med en avvist Ledig bak seg."""
    if oppdrag.problemstilling == choices.UDEFINERT:
        raise ProblemstillingUdefinert(
            'Problemstillingen står som «Udefinert». Meld problemstillingen til KO, '
            'så setter sentralbordet den — først da kan enheten meldes ledig.')
    naa = tidspunkt or timezone.now()
    melding = sett_status(oppdrag, choices.BEHANDLET, bruker=bruker, tidspunkt=naa,
                          forsinket=forsinket, enhet=enhet)
    sett_status(oppdrag, choices.LEDIG, bruker=bruker, tidspunkt=naa,
                forsinket=forsinket, enhet=enhet)
    return melding


def varsle_enhet(oppdrag, enhet, *, bruker=None) -> Oppdragsenhet:
    """Sett en enhet til på oppdraget — i `Venter`, sist i rekka.

    Et ferdig oppdrag som får en enhet til er ikke ferdig lenger: statusen
    utledes på nytt, og er det ryddet til historikken, hentes det tilbake.
    """
    if oppdrag.enheter.filter(enhet=enhet).exists():
        raise ValueError(f'«{enhet.navn}» er alt varslet på oppdraget.')
    neste = (oppdrag.enheter.aggregate(models.Max('rekkefolge'))['rekkefolge__max'] or 0) + 1
    rad = Oppdragsenhet.objects.create(
        oppdrag=oppdrag, enhet=enhet, varslet_av=bruker, rekkefolge=neste,
        # **Modusen fryses her.** Leses `Enhet.passiv_vakt` i ettertid, teller
        # man dagens tilstand — og merket på et gammelt oppdrag ville skiftet
        # tekst i det noen vipper bryteren.
        varslet_modus=gjeldende_modus(enhet))
    # **Ressursen er her, så avbrytelsen er besvart** (André, 15. sep. 2026:
    # «det må løses av operatør»). Å sende en ny enhet *er* å ta stilling;
    # å kreve et klikk i tillegg ville lært operatøren å klikke det bort.
    kvitter_avbrutt(oppdrag, bruker=bruker)
    felter = ['status', 'updated_at']
    if oppdrag.trenger_ressurs:
        # Ressursen er her. Flagget nullstilles før utledningen.
        oppdrag.trenger_ressurs = False
        oppdrag.trenger_ressurs_siden = None
        felter += ['trenger_ressurs', 'trenger_ressurs_siden']
    oppdrag.status = utledet_status(oppdrag)
    if oppdrag.historikk_fra is not None:
        oppdrag.historikk_fra = None
        oppdrag.historikk_av = None
        felter += ['historikk_fra', 'historikk_av']
    oppdrag.save(update_fields=felter)
    varsle_bjelle(oppdrag, rad)
    return rad


#: Varseltypen enhetskontoen får i bjella. **Oppdrags-ID-en er en del av
#: nøkkelen**, fordi `core.notifications.notify()` dedupliserer på `kind` i 24
#: timer: med en fast verdi ville oppdrag nummer to blitt svelget, og det er
#: nettopp det andre oppdraget hun trenger å se.
def bjellenokkel(oppdrag) -> str:
    return f'oppdrag_varslet:{oppdrag.pk}'


def varsle_bjelle(oppdrag, rad) -> None:
    """Varselbjella hos enhetskontoen når hun får et oppdrag.

    André, 15. sep. 2026: «En bruker som er koblet til en enhet i /oppdrag/ som
    får et oppdrag skal få varsel på varselbjella med tidsstempel og hastegrad,
    intet mer.» Teksten er derfor nummeret og hastegraden — ikke
    problemstillingen, som er helseopplysning og ikke hører hjemme i en
    varselrad som blir stående i 30 dager.

    **Kaster aldri.** En bil uten bjellerad er et savn; en varsling som velter
    utrykningen er en feil. Og `transaction.atomic()` rundt kallet er ikke
    pynt: `varsle_enhet` kan kjøre inne i en transaksjon, og en databasefeil
    fanget uten savepoint etterlater den ubrukelig — samme felle som
    unik-skrankene i vaktlista.
    """
    bruker = getattr(rad.enhet, 'user', None)
    if bruker is None:
        return
    try:
        with transaction.atomic():
            notify(
                bruker,
                module_slug='oppdrag',
                kind=bjellenokkel(oppdrag),
                title=f'Oppdrag {oppdragsnr(oppdrag.oppdragsnummer)}',
                message=f'{oppdrag.hastegrad} · {timezone.localtime(rad.varslet_at).strftime("%H:%M")}',
                url='/oppdrag/',
            )
    except Exception:   # noqa: BLE001 — se docstringen
        logger.warning('oppdrag: kunne ikke varsle bjella for %s', rad.enhet_id,
                       exc_info=True)


def ta_av_enhet(oppdrag, enhet, *, bruker=None) -> None:
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
    # Sporet i tidslinjen: raden er borte, hendelsen står.
    Enhetshendelse.objects.create(
        oppdrag=oppdrag, enhet=enhet, type=Enhetshendelse.TATT_AV, av=bruker)
    if oppdrag.enhet_id == enhet.pk:
        # Den gamle kolonnen (deploy 1) skal peke på en som fortsatt er der.
        oppdrag.enhet = oppdrag.primaer.enhet
    oppdrag.status = utledet_status(oppdrag)
    felter = ['status', 'enhet', 'updated_at']
    # Var den som ble tatt av den siste som ikke var ledig, er oppdraget
    # ferdig nå — og skal rydde seg som ellers (André, 12. sep. 2026: «da
    # må vi ha det at det går i historikken automatisk»).
    if oppdrag.status == choices.TERMINAL and oppdrag.historikk_fra is None:
        oppdrag.historikk_fra = timezone.now()
        felter.append('historikk_fra')
    oppdrag.save(update_fields=felter)


#: Skjemaene (`datetime-local`) har minuttoppløsning. «Nå» avrundet ned til
#: minuttet ligger før et oppdrag opprettet sekunder tidligere, og «før
#: oppdraget ble opprettet» ville da avvist en føring som var riktig.
#: Og mot framtiden: nettleserens klokke kan gå noen sekunder foran
#: serverens, og da lå «nå» rundet til minuttet i framtiden for serveren
#: (André, 12. sep. 2026: «kunne ikke ta det i fremtiden når jeg trykket
#: umiddelbart»). Slakken er én minuttgrense, begge veier.
MINUTTSLAKK = timedelta(minutes=1)


class KorreksjonUgyldig(Exception):
    """Tidspunktet lar seg ikke rette til den oppgitte verdien."""


#: Full rekkefølge for statusene, inkludert terminal. `KJEDEN` stopper før
#: `ledig` fordi den er utgang fra enhver status, ikke et ledd — men når vi
#: sjekker at tidspunktene står i rekkefølge, er den sist.
_REKKEFOLGE = {status: i for i, status in enumerate(choices.KJEDEN)}
_REKKEFOLGE[choices.BEHANDLET] = _REKKEFOLGE[choices.AVREIST]   # sidegren etter Fremme
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

    # Per koblingsrad (11. sep. 2026): naboene er *bilens* meldinger. Målte
    # vi mot hele oppdraget, ville den andre bilens «Rykker ut» stått i
    # veien for å rette denne bilens «Fremme».
    if melding.oppdragsenhet_id is not None:
        gjeldende = Statusmelding.objects.gjeldende_for_enhet(melding.oppdragsenhet)
    else:
        gjeldende = Statusmelding.objects.gjeldende(melding.oppdrag)
    forrige = neste = None
    for annen in gjeldende:
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

    if nytt_tidspunkt > naa + MINUTTSLAKK:
        raise KorreksjonUgyldig('Tidspunktet kan ikke ligge i framtiden.')

    if nytt_tidspunkt < melding.oppdrag.created_at - MINUTTSLAKK:
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


# ── Sentralbordet fører status (§9) ──────────────────────────────────────────

#: Hvor lenge etter `Ledig` sentralbordet kan gjenåpne en enhets oppdrag.
#: «Rimelig tid» (André, 11. sep. 2026) — dekker «vi oppdaget det dagen
#: etter», og er kort nok til at et arkiv tatt etter vakta ikke løper fra seg.
#: Etter dette er oppdraget arkivets, ikke tavlas.
KORRIGERBAR_ETTER_LEDIG = 48 * 3600   # sekunder


def valider_foering(rad, ny_status: str, tidspunkt, naa=None) -> None:
    """Kast hvis sentralbordet ikke kan føre ``ny_status`` for raden.

    Overgangsreglene gjelder også for operatøren (`UlovligOvergang`): å føre
    «Avreist» på en bil som står i «Venter» er en feil, ikke en korreksjon —
    mangler et ledd, føres det først. Tidspunktet (`KorreksjonUgyldig`) må
    være inntruffet, etter at oppdraget ble opprettet, og etter bilens
    siste gjeldende melding: en føring bakover i tid er hele poenget, men
    ikke bak det som alt står.
    """
    naa = naa or timezone.now()
    if not kan_gaa_til(rad.status, ny_status):
        raise UlovligOvergang(
            f'Kan ikke gå fra {rad.get_status_display()!r} til '
            f'{choices.STATUS_NAVN.get(ny_status, ny_status)!r}.')
    if tidspunkt > naa + MINUTTSLAKK:
        raise KorreksjonUgyldig('Tidspunktet kan ikke ligge i framtiden.')
    if tidspunkt < rad.oppdrag.created_at - MINUTTSLAKK:
        raise KorreksjonUgyldig('Tidspunktet er før oppdraget ble opprettet.')
    egne = Statusmelding.objects.gjeldende_for_enhet(rad)
    if egne:
        siste = max(egne, key=lambda m: m.tidspunkt)
        if tidspunkt < siste.tidspunkt:
            raise KorreksjonUgyldig(
                f'«{choices.STATUS_NAVN.get(ny_status, ny_status)}» kan ikke være før '
                f'«{siste.get_status_display()}» '
                f'({timezone.localtime(siste.tidspunkt).strftime("%H:%M")}).')


@transaction.atomic
def foer_status(oppdrag, enhet, ny_status: str, *, tidspunkt, bruker,
                sted: str = '') -> Statusmelding:
    """Sentralbordet fører en status for en enhet — et stempel bilen glemte.

    Ikke et stempel fra bilen: raden merkes ``manuell`` og ``meldt_av`` er
    operatøren, så tidslinjen viser «ført av sentralen». Lukker **ikke**
    bilens andre pågående oppdrag slik `start_oppdrag` gjør: tidspunktet er
    fortid, og hva bilen gjorde siden er operatørens sak å føre.
    """
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise UlovligOvergang('Enheten er ikke varslet på oppdraget.')
    valider_foering(rad, ny_status, tidspunkt)
    return sett_status(oppdrag, ny_status, bruker=bruker, tidspunkt=tidspunkt,
                       sted=sted, enhet=rad.enhet, manuell=True)


def _slett_meldinger(qs) -> int:
    """Slett statusmeldinger uten å gå på `korrigerer`s PROTECT: rader som
    peker på dem kobles fra først. Sporet av hva som sto der ligger i
    revisjonsloggen, som logger slettinger."""
    ider = list(qs.values_list('pk', flat=True))
    if not ider:
        return 0
    Statusmelding.objects.filter(korrigerer_id__in=ider).update(korrigerer=None)
    return Statusmelding.objects.filter(pk__in=ider).delete()[0]


@transaction.atomic
def angre_siste_status(oppdrag, enhet, *, bruker=None):
    """Ta enhetens nåværende status bort, tilbake til den forrige (André,
    12. sep. 2026: «fjerne nåværende status og ta den tilbake til forrige»).

    **Meldingene for statusen slettes**, med hele rettingshistorikken sin —
    en korreksjon som pekte på dem ville ellers gjort den gamle raden
    gjeldende igjen, og statusen sto der fortsatt. Slettingen logges i
    revisjonsloggen. Den forrige statusen er den høyeste i kjeden som står
    igjen; er ingen igjen, er det `Venter`. Returnerer meldingen bak den
    forrige statusen, eller ``None`` for `Venter`.
    `gjenaapne_enhet` er dette med «Ledig» som status, pluss 48-timersgrensen.
    """
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise UlovligOvergang('Enheten er ikke varslet på oppdraget.')
    if rad.status == choices.VENTER:
        raise KorreksjonUgyldig('Enheten har ingen status å angre — hun venter.')
    _slett_meldinger(Statusmelding.objects.filter(oppdragsenhet=rad, status=rad.status))
    igjen = Statusmelding.objects.gjeldende_for_enhet(rad)
    if igjen:
        forrige = max(igjen, key=lambda m: (_REKKEFOLGE.get(m.status, -1), m.tidspunkt))
        status, melding = forrige.status, forrige
    else:
        status, melding = choices.VENTER, None
    rad.status = status
    rad.save(update_fields=['status', 'updated_at'])
    oppdrag.status = utledet_status(oppdrag)
    felter = ['status', 'updated_at']
    if oppdrag.status != choices.TERMINAL and oppdrag.historikk_fra is not None:
        oppdrag.historikk_fra = None
        oppdrag.historikk_av = None
        felter += ['historikk_fra', 'historikk_av']
    oppdrag.save(update_fields=felter)
    return melding


@transaction.atomic
def gjenaapne_enhet(oppdrag, enhet, *, bruker, naa=None):
    """Ta en enhets «Ledig» tilbake — innen `KORRIGERBAR_ETTER_LEDIG`.

    `angre_siste_status` med «Ledig» som status, og en grense: etter 48
    timer er oppdraget arkivets, ikke tavlas. Oppdraget hentes tilbake fra
    historikken hvis det ikke lenger er ledig.
    """
    naa = naa or timezone.now()
    rad = koblingsrad(oppdrag, enhet)
    if rad is None:
        raise UlovligOvergang('Enheten er ikke varslet på oppdraget.')
    if rad.status != choices.LEDIG:
        raise KorreksjonUgyldig(
            f'«{rad.enhet.navn}» er ikke ledig ({rad.get_status_display()}).')
    egne = Statusmelding.objects.gjeldende_for_enhet(rad)
    ledig = next((m for m in reversed(egne) if m.status == choices.LEDIG), None)
    if ledig is None:
        raise KorreksjonUgyldig('Fant ingen «Ledig»-melding å ta tilbake.')
    if (naa - ledig.tidspunkt).total_seconds() > KORRIGERBAR_ETTER_LEDIG:
        timer = KORRIGERBAR_ETTER_LEDIG // 3600
        raise KorreksjonUgyldig(
            f'«Ledig» er eldre enn {timer} timer — oppdraget er arkivets nå.')
    return angre_siste_status(oppdrag, enhet, bruker=bruker)


@transaction.atomic
def slett_oppdrag(oppdrag) -> None:
    """Slett et oppdrag med meldingene sine. `korrigerer` er PROTECT, så
    meldingene kobles fra hverandre først — ellers stopper den første
    korreksjonen hele slettingen."""
    _slett_meldinger(Statusmelding.objects.filter(oppdrag=oppdrag))
    oppdrag.delete()


@transaction.atomic
def nullstill_vakt(vakt) -> int:
    """Slett **alle** oppdragene i vakta — tavla og historikken — og
    telleren, uten arkivering (KO-innstillinger «Nullstill», 18. sep. 2026).

    For test og utvikling; i prod er det global admin som står ansvarlig, og
    viewet krever `confirm`. Samme tømming som `arkiver_vakt(tomm=True)` gjør
    *etter* at radene er frosset — bare uten frysingen. Telleren slettes, ikke
    settes til 1: `neste_oppdragsnummer` gjenskaper den fra det som finnes.
    Enhetene, lokasjonene og verdimengdene røres ikke.
    """
    from core.models import AppSetting  # noqa: WPS433 — som i neste_oppdragsnummer

    antall = 0
    for oppdrag in Oppdrag.objects.filter(vakt=vakt):
        slett_oppdrag(oppdrag)
        antall += 1
    AppSetting.objects.filter(key=_nummer_nokkel(vakt)).delete()
    return antall


def kan_slettes(oppdrag, user) -> bool:
    """Hvem får slette et oppdrag (André, 12. sep. 2026).

    Sentralbordet (`skriv_full`) får slette så lenge **ingen** bil har rykket
    ut — alle rader i `Venter`. Er noen på vei, er det en hendelse, og da er
    svaret å føre statusen tilbake først. Global admin får i tillegg slette
    det som ligger i historikken, enkeltvis eller alt.
    """
    from core.auth_decorators import er_global_admin, har_tilgang
    if er_global_admin(user) and oppdrag.historikk_fra is not None:
        return True
    if not har_tilgang(user, 'oppdrag', 'skriv_full'):
        return False
    if oppdrag.trenger_ressurs:
        # Står og venter på en ny ressurs — ingen er på vei, og sentralbordet
        # skal kunne stryke det hvis det ikke lenger trengs.
        return True
    statuser = list(oppdrag.enheter.values_list('status', flat=True))
    return bool(statuser) and all(st == choices.VENTER for st in statuser)


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
