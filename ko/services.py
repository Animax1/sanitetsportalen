"""Reglene for KO-loggen. Alt som skriver en linje går gjennom denne fila.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Viewene eier HTTP-en, signalene
eier løftet av systemhendelser, og **begge kaller hit** — en regel med to
lesere skrives én gang, ellers har loggen to sannheter om hva en gyldig linje
er.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import AppSetting
from core.vakt import hent_aktiv_vakt

from .kartkobling import meld_lag
from .models import (
    HENDELSE_APEN, HENDELSE_LUKKET, KILDE_OPERATOR, KILDE_SYSTEM, MELDER_ANDRE,
    MELDER_NAVN, MELDER_VALG, PRIORITET_NAVN, PRIORITET_STANDARD, Ansvarsmerke,
    Ansvarsomraade, Hendelse, HendelseDeltaker, HendelseLag, HendelseLest, HendelseVarsling,
    KoOppsett, Linjedeling, Logglinje, Talegruppe,
)


#: Lengste linje. Rundhåndet — loggen skal være fullstendig og kjedelig, ikke
#: knapp — men ikke ubegrenset: et felt uten tak er et felt noen limer en hel
#: e-posttråd inn i, og da er linja ikke lenger en linje.
MAKS_TEKST = 2000

#: Hvor langt fram og tilbake et oppgitt `tidspunkt` får ligge.
#:
#: **Framover er slakken liten og bakover stor**, og det er ikke symmetri det
#: mangler. Framover er det bare klokkeslingring som skal slippe gjennom —
#: nettleserens klokke kan gå noen sekunder foran serverens, og samme
#: minuttslakk som `oppdrag.services.MINUTTSLAKK` dekker det. Bakover er det
#: den ekte bruken: operatøren skriver 21:14 klokka 21:40 fordi det var da hun
#: fikk tid. Et døgn er vaktas lengde med margin.
MAKS_FRAMTID = timedelta(minutes=1)
MAKS_ALDER = timedelta(days=1)

#: Oppbevaringstiden, i dager. **`AppSetting` og ikke en Railway-variabel**
#: (André, 17. sep. 2026): en Railway-variabel har ingen auditspor, må settes
#: likt på både web- og cron-tjenesten, og er usynlig i portalen. Samme
#: begrunnelse som `purge_old_logs` sin egen docstring gir for at grensene
#: ikke er cron-flagg — «en endring av lagringstid skjer i kode som kan
#: revideres, ikke i en skjult jobbkonfigurasjon» — bare ett hakk videre: i
#: data som *også* kan revideres, fordi `core/signals.py` auditlogger den.
#:
#: Nøkkelen skal derfor **aldri** inn i `NOKLER_UTEN_AUDIT`. Den er noe et
#: menneske har bestemt, ikke noe maskinen har talt.
DAGER_NOKKEL = 'ko.logg_dager'

#: 730 dager = 2 år. Samme frist som audit-loggen, arkivkollapsen og
#: `backups/`-prefikset offsite — ett tall å forklare i A.9 i stedet for fire.
DAGER_STANDARD = 730

#: **Chat-bryteren** (§4.5, pulje 6). `AppSetting`, auditlogget som fristen
#: over — noe et menneske har bestemt. Betyr «har operatørene lov til å
#: skrive uformelle linjer», ikke «skjul en funksjon»: linjer som alt er
#: skrevet vises uansett, ellers etterlater bryteren et hull i loggen.
#: **Av som standard**: en chat ingen har bedt om er støy i det dokumentet
#: man leser etter et arrangement der noe gikk galt.
CHAT_NOKKEL = 'ko.chat_tillatt'

#: Ansvarsområdene (§5.1) var en fast tuppel til 18. sep. 2026; nå er de en
#: liste admin og KO-leder redigerer (`Ansvarsomraade`). Disse fire seedes av
#: `ko/0007`, og er fortsatt det `sett_ansvar` faller tilbake til i en base
#: uten rader.
ANSVARSOMRAADER_STANDARD: tuple[str, ...] = ('samband', 'ressurser', 'logg', 'media')


def ansvarsomraader_aktive() -> list[str]:
    """Navnene operatøren kan velge mellom, i rekkefølge."""
    return list(Ansvarsomraade.objects.i_portal().filter(er_aktiv=True)
                .values_list('navn', flat=True))

#: Grensene for hva fristen kan settes til. `0` er ikke lov: en logg som
#: slettes samme døgn er ikke en logg, og «skru av oppbevaring» er ikke en
#: innstilling noen skal kunne velge ved et uhell.
DAGER_MIN = 30
DAGER_MAKS = 3650


class LoggfeilBase(Exception):
    """Felles base, så viewet kan fange én ting og svare 400."""


class Ugyldig(LoggfeilBase):
    """Linja lar seg ikke skrive slik den ble sendt inn."""


class AlleredeKorrigert(LoggfeilBase):
    """Noen andre rettet den samme linja først (409)."""


class Konflikt(LoggfeilBase):
    """Hendelsens hode er endret av noen andre siden du leste det (409, §7.1)."""


class HarApneOppdrag(LoggfeilBase):
    """Lukking uten `confirm` mens hendelsen har åpne oppdrag (409, §4.6).

    Bærer antallet, fordi svaret skal si det: «Hendelsen har 2 åpne oppdrag»
    er døra operatøren skal åpne bevisst, og en 409 uten tall er en vegg.
    """

    def __init__(self, antall):
        super().__init__(
            f'Hendelsen har {antall} åpne oppdrag.' if antall != 1
            else 'Hendelsen har 1 åpent oppdrag.')
        self.antall = antall


def oppbevaringsdager() -> int:
    """Fristen, lest fra `AppSetting` med kodedefault.

    Klemmes inn i [`DAGER_MIN`, `DAGER_MAKS`] ved lesing og ikke bare ved
    lagring: en verdi skrevet av en eldre versjon, eller for hånd i shellet,
    skal ikke kunne tømme loggen. Sperren hører hjemme der verdien *brukes*,
    fordi det er den veien `purge_old_logs` går.
    """
    raa = AppSetting.get(DAGER_NOKKEL, None)
    try:
        dager = int(raa)
    except (TypeError, ValueError):
        return DAGER_STANDARD
    return max(DAGER_MIN, min(DAGER_MAKS, dager))


def chat_tillatt() -> bool:
    """Får operatørene skrive uformelle linjer? Lest fra `AppSetting`."""
    raa = AppSetting.get_i_portal(CHAT_NOKKEL, None)
    return str(raa).strip().lower() in ('1', 'true', 'ja', 'on')


def ansvar_for(bruker, portal=None) -> str:
    """Operatørens ansvarsmerke **i portalen**, eller tom streng. `portal` når
    kalleren har den fra dataene (`skriv_linje` har vakta), ellers konteksten."""
    if bruker is None or not getattr(bruker, 'is_authenticated', False):
        return ''
    merke = Ansvarsmerke.objects.i_portal(portal).filter(bruker=bruker).first()
    return merke.omraade if merke else ''


def sett_ansvar(bruker, omraade) -> str:
    """Sett (eller tøm) operatørens ansvarsmerke. Ukjent eller deaktivert
    område avvises — lista finnes nettopp for at merket skal bety det samme
    hos alle. Sammenligningen er uten hensyn til store og små bokstaver, og
    det lagrede navnet er listas."""
    onsket = (omraade or '').strip().lower()
    omraade = ''
    if onsket:
        treff = [n for n in ansvarsomraader_aktive() if n.lower() == onsket]
        if not treff:
            raise Ugyldig('Ukjent ansvarsområde.')
        omraade = treff[0]
    Ansvarsmerke.objects.i_portal().update_or_create(bruker=bruker, defaults={'omraade': omraade})
    return omraade


#: Oppsettet (20. okt. 2026): de seks vinduene og fire tall er noen hundre byte. Taket står for
#: at et skript ikke skal kunne legge en megabyte på en konto.
OPPSETT_MAKS_BYTE = 2000
OPPSETT_FELT = frozenset({'rader', 'bredde', 'hoyde', 'skjult'})


def lagret_oppsett(bruker):
    """Oppsettet kontoen har lagret i portalen, eller None."""
    return KoOppsett.objects.i_portal().filter(bruker=bruker).first()


def lagre_oppsett(bruker, oppsett) -> KoOppsett:
    """Lagre KO-oppsettet på kontoen. **Form og størrelse sjekkes her, innholdet i klienten.**

    `koGyldigOppsett()` i ko-layout.js avviser alt den ikke kjenner når oppsettet leses, og den
    kjenner vinduene; en kopi av den lista her ville glidd fra den. Det serveren må hindre, er
    noe annet enn et oppsett i raden: ikke et objekt, felter som ikke hører hjemme, for stort.
    """
    if not isinstance(oppsett, dict) or set(oppsett) != OPPSETT_FELT:
        raise Ugyldig('Oppsettet har feil form.')
    if len(json.dumps(oppsett, separators=(',', ':'))) > OPPSETT_MAKS_BYTE:
        raise Ugyldig('Oppsettet er for stort.')
    rad, _ = KoOppsett.objects.i_portal().update_or_create(
        bruker=bruker, defaults={'oppsett': oppsett})
    return rad


def vurder_tidspunkt(oppgitt, naa=None):
    """Tidspunktet linja skal få. Kaster `Ugyldig` hvis det ikke går an.

    **Kaster, i motsetning til `vaktliste.services.vurder_klienttid` som
    faller tilbake til servertid.** Forskjellen er hvem som oppgir verdien:
    der er det en offline-kø som spiller av et trykk, og en stille korreksjon
    er bedre enn en tapt stempling. Her har et menneske skrevet et
    klokkeslett, og å lagre noe annet enn det hun skrev — uten å si fra — er
    nøyaktig den stille feilen loggen finnes for å unngå.
    """
    naa = naa or timezone.now()
    if oppgitt is None:
        return naa
    if timezone.is_naive(oppgitt):
        oppgitt = timezone.make_aware(oppgitt)
    if oppgitt - naa > MAKS_FRAMTID:
        raise Ugyldig('Tidspunktet ligger fram i tid.')
    if naa - oppgitt > MAKS_ALDER:
        raise Ugyldig('Tidspunktet ligger mer enn et døgn tilbake.')
    return oppgitt


def rens_tekst(raa) -> str:
    """Teksten, prøvd. Kaster `Ugyldig` på tom eller for lang linje.

    Ingen HTML-vasking her: teksten lagres som den ble skrevet, og escapes
    når den *vises* (`escapeHtml` i `static/js/ko.js`). Å vaske ved lagring
    ville ødelagt en linje som lovlig inneholder `<` — «BT < 90» — og fortsatt
    ikke vært et forsvar, fordi forsvaret hører hjemme ved utskriften.
    """
    tekst = (raa or '').strip()
    if not tekst:
        raise Ugyldig('Linja kan ikke være tom.')
    if len(tekst) > MAKS_TEKST:
        raise Ugyldig(f'Linja er for lang (maks {MAKS_TEKST} tegn).')
    return tekst


def _frys_forfatter(linje, bruker) -> None:
    """Navn og kontotype fryses på linja (§4.5).

    Visningsnavn endres og kontoer slettes; en logg der avsenderen forsvinner
    er verdiløs akkurat når den leses. Og **en delt konto må se ut som en delt
    konto**: «Enhet 2» er to til tre personer man må slå opp i vaktlista for å
    finne, «Kari Nordmann» er én. Kontoen kan ha byttet type siden, så
    spørsmålet kan ikke stilles på nytt i ettertid — det må stå på linja.
    """
    linje.forfatter = bruker if bruker and bruker.is_authenticated else None
    linje.forfatter_navn = getattr(bruker, 'username', '') or ''
    linje.forfatter_delt_konto = bool(getattr(bruker, 'er_delt_konto', False))


def skriv_linje(vakt, raa_tekst, *, bruker, tidspunkt=None,
                ansvarsomraade=None, uformell=False, hendelse=None,
                krever_haandtering=False, naa=None) -> Logglinje:
    """En menneskeskrevet linje. Den vanlige veien inn i loggen.

    **`hendelse` gjør linja til en kommentar i hendelsen** (18. sep. 2026).
    Samme tabell, samme regler — §4.1 sa «én logg, ikke to» nettopp for at
    dette skulle være en peker og ikke en flytting. Og den som skriver i
    hendelsen er *på* den: `bli_med` kalles her, ikke i viewet, så en klient
    som går utenom skjermen får samme regel.

    **Ansvarsområdet stemples fra operatørens merke** når kallet ikke oppgir
    et (§5.1): det er slik «ført av Kari, samband» kommer på linja uten at hun
    skriver det hver gang. Oppgitt verdi vinner — testene og API-et kan sette
    det eksplisitt.

    **`uformell` krever at chatten er slått på** (§4.5). Sperren står her og
    ikke bare i skjemaet: en klient som sender flagget når admin har slått
    chatten av, skal møte den samme døra.

    **Linja er intern til den deles** (19. sep. 2026): `delt_at` står tom, og
    enhetene ser den ikke før `del_linje()` er kalt. Standarden er intern
    fordi loggen er KOs arbeidsnotat, og det som skal ut til en bil er et
    bevisst valg — se `del_linje`.

    **`krever_haandtering`** (20. okt. 2026) merker linja fra start: den som
    skriver vet best at noe skal gjøres. Se `krev_haandtering`.
    """
    tekst = rens_tekst(raa_tekst)
    tid = vurder_tidspunkt(tidspunkt, naa)
    if uformell and not chat_tillatt():
        raise Ugyldig('Chatten er slått av. Skriv linja som en vanlig logglinje.')
    if hendelse is not None and hendelse.vakt_id != vakt.pk:
        raise Ugyldig('Hendelsen hører til en annen vakt.')
    if ansvarsomraade is None:
        ansvarsomraade = ansvar_for(bruker, vakt.portal)
    linje = Logglinje(
        vakt=vakt,
        kilde=KILDE_OPERATOR,
        tidspunkt=tid,
        tekst=tekst,
        ansvarsomraade=(ansvarsomraade or '').strip()[:40],
        uformell=bool(uformell),
        hendelse=hendelse,
    )
    if krever_haandtering:
        linje.haandtering_krevd_at = naa or timezone.now()
        linje.haandtering_krevd_av_navn = getattr(bruker, 'username', '') or ''
    _frys_forfatter(linje, bruker)
    linje.save()
    if hendelse is not None:
        bli_med(hendelse, bruker)
    return linje


def fest_linje(linje, *, bruker, naa=None) -> Logglinje:
    """Fest linja øverst i loggstrømmen. Idempotent: en linje som alt er
    festet blir stående med den første festingen — to operatører som trykker
    samtidig skal ikke bytte navn på hverandre. Systemlinjer og fjernede
    linjer festes ikke: den ene er ikke en beskjed, den andre har ingen."""
    if linje.kilde == KILDE_SYSTEM:
        raise Ugyldig('Systemlinjer kan ikke festes.')
    if linje.er_fjernet:
        raise Ugyldig('Linja er fjernet og kan ikke festes.')
    if linje.er_festet:
        return linje
    linje.festet_at = naa or timezone.now()
    linje.festet_av = bruker if bruker and bruker.is_authenticated else None
    linje.festet_av_navn = getattr(bruker, 'username', '') or ''
    linje.save(update_fields=['festet_at', 'festet_av', 'festet_av_navn'])
    return linje


def losne_linje(linje, *, bruker) -> Logglinje:
    """Ta linja ned igjen. Idempotent, og hvem som helst med `skriv_full`
    kan løsne det en annen festet — det er en beskjed på en felles tavle,
    ikke en eiendel."""
    if not linje.er_festet:
        return linje
    linje.festet_at = None
    linje.festet_av = None
    linje.festet_av_navn = ''
    linje.save(update_fields=['festet_at', 'festet_av', 'festet_av_navn'])
    return linje


# ── «Krever håndtering» og «Håndtert» (20. okt. 2026) ────────────────────────
#
# André: en linje fra LSKO «som er til info for oss, som kanskje ikke haster og
# heller ikke er en hendelse» — og et merke som sier «her må ha en kvittering».
# Tre måter å løfte en linje på, og de skal ikke flyte sammen: **festet** er
# «alle bør se dette», **krever håndtering** er «én ting skal gjøres», og en
# **hendelse** er en situasjon med flere linjer, oppdrag og lag.
#
# Tilstand på linja, ikke en hendelse i loggen: ingen systemlinje. Merket med
# navn og klokkeslett *er* sporet, og en linje til i strømmen per kvittering ville
# druknet nettopp det merket skal få fram.

_HAANDTERING_FELT = ['haandtering_krevd_at', 'haandtering_krevd_av_navn']
_HAANDTERT_FELT = ['haandtert_at', 'haandtert_av_navn']


def _kan_haandteres(linje):
    """Bare manuelle, gjeldende linjer med innhold. En rettet linje er ikke den
    gjeldende — skjermen viser rettingen, og den har arvet merket."""
    if linje.kilde == KILDE_SYSTEM:
        raise Ugyldig('Systemlinjer kvitteres ikke; de sier hva som skjedde.')
    if linje.er_fjernet:
        raise Ugyldig('Linja er fjernet.')
    if Logglinje.objects.filter(korrigerer=linje).exists():
        raise Ugyldig('Linja er rettet; bruk den gjeldende linja.')


def krev_haandtering(linje, *, bruker, naa=None) -> Logglinje:
    """Merk linja «Krever håndtering». Idempotent: første merking står, som
    festingen — to som trykker samtidig skal ikke bytte navn på hverandre."""
    _kan_haandteres(linje)
    if linje.krever_haandtering:
        return linje
    linje.haandtering_krevd_at = naa or timezone.now()
    linje.haandtering_krevd_av_navn = getattr(bruker, 'username', '') or ''
    linje.save(update_fields=_HAANDTERING_FELT)
    return linje


def fjern_krav(linje, *, bruker) -> Logglinje:
    """Ta merket av — feiltrykk, eller det viste seg å være til info. Rører
    ikke «Håndtert»."""
    _kan_haandteres(linje)
    if not linje.krever_haandtering:
        return linje
    linje.haandtering_krevd_at = None
    linje.haandtering_krevd_av_navn = ''
    linje.save(update_fields=_HAANDTERING_FELT)
    return linje


@transaction.atomic
def haandter(linje, *, bruker, naa=None) -> Logglinje:
    """Merk linja håndtert — mottatt og utført. **En festet linje løsnes i samme
    lagring**: ellers blir de festede stående og hope seg opp, og en topp som
    aldri ryddes er en topp ingen ser på. Idempotent: første kvittering står."""
    _kan_haandteres(linje)
    if linje.er_haandtert:
        return linje
    linje.haandtert_at = naa or timezone.now()
    linje.haandtert_av_navn = getattr(bruker, 'username', '') or ''
    felt = list(_HAANDTERT_FELT)
    if linje.er_festet:
        linje.festet_at = None
        linje.festet_av = None
        linje.festet_av_navn = ''
        felt += ['festet_at', 'festet_av', 'festet_av_navn']
    linje.save(update_fields=felt)
    return linje


def angre_haandtert(linje, *, bruker) -> Logglinje:
    """Angre kvitteringen. Linja står åpen igjen om den krever håndtering, men
    **festes ikke på nytt** — festingen var et eget valg, og den som angrer vet
    ikke om det fortsatt gjelder."""
    _kan_haandteres(linje)
    if not linje.er_haandtert:
        return linje
    linje.haandtert_at = None
    linje.haandtert_av_navn = ''
    linje.save(update_fields=_HAANDTERT_FELT)
    return linje


@transaction.atomic
def korriger(linje, *, bruker, tekst=None, tidspunkt=None, naa=None) -> Logglinje:
    """Rett en linje — som **en ny rad som peker på den gamle** (§4.3).

    Aldri ved å endre. Mønsteret er `Statusmelding.objects.gjeldende()`, og
    grunnen er den samme: den gamle verdien skal være lesbar etterpå, og en
    retting av en retting skal kunne kjedes.

    Den nye linja arver plassen sin i fortellingen fra kjedens første ledd
    (`rot`) og ikke fra sin egen `registrert_at`. Uten det ville en rettet
    linje hoppet til bunnen av loggen, og §4.3 sier hvorfor det er galt: det
    er som fortelling loggen har verdi.

    En systemlinje kan ikke rettes her. Den er en projeksjon av noe som
    skjedde i oppdragsmodulen, og rettes *der* — `korriger_tidspunkt()` gir da
    en `tidspunkt_korrigert`-linje av seg selv. Gikk veien om KO, ville de to
    modulene sagt hver sin ting om samme tidspunkt.
    """
    if linje.kilde == KILDE_SYSTEM:
        raise Ugyldig('Systemlinjer rettes i oppdragsmodulen, ikke i loggen.')
    if linje.er_fjernet:
        raise Ugyldig('Linja er fjernet og kan ikke rettes.')

    ny_tekst = rens_tekst(tekst) if tekst is not None else linje.tekst
    ny_tid = vurder_tidspunkt(tidspunkt, naa) if tidspunkt is not None else linje.tidspunkt
    if ny_tekst == linje.tekst and ny_tid == linje.tidspunkt:
        raise Ugyldig('Ingenting er endret.')

    # `korrigerer` er en OneToOne, så databasen selv nekter to rettinger av
    # samme linje. Sjekken her finnes for feilmeldingens skyld; sperren er
    # unikhetskravet, og den holder også når to operatører trykker samtidig.
    if Logglinje.objects.filter(korrigerer=linje).exists():
        raise AlleredeKorrigert('Linja er allerede rettet av noen andre.')

    ny = Logglinje(
        vakt=linje.vakt,
        kilde=KILDE_OPERATOR,
        tidspunkt=ny_tid,
        tekst=ny_tekst,
        ansvarsomraade=linje.ansvarsomraade,
        # Merkene arves: en retting av en chatlinje er fortsatt chat, og en
        # retting av en delt linje er fortsatt delt — bilen skal se rettingen,
        # ikke miste linja. Delingene per oppdrag følger med av samme grunn.
        uformell=linje.uformell,
        hendelse=linje.hendelse,
        delt_at=linje.delt_at,
        delt_av=linje.delt_av,
        delt_av_navn=linje.delt_av_navn,
        # Festingen og håndteringen også (20. okt. 2026). Klienten finner dem på
        # den gjeldende linjas id, så uten dette ble en festet linje stille
        # løsnet av en retting — og en retting av «krever håndtering» ville
        # lukket oppgaven uten at noen hadde gjort den.
        festet_at=linje.festet_at,
        festet_av=linje.festet_av,
        festet_av_navn=linje.festet_av_navn,
        haandtering_krevd_at=linje.haandtering_krevd_at,
        haandtering_krevd_av_navn=linje.haandtering_krevd_av_navn,
        haandtert_at=linje.haandtert_at,
        haandtert_av_navn=linje.haandtert_av_navn,
        korrigerer=linje,
        rot=linje.rot or linje,
    )
    _frys_forfatter(ny, bruker)
    ny.save()
    Linjedeling.objects.bulk_create([
        Linjedeling(linje=ny, oppdrag_id=d.oppdrag_id, delt_at=d.delt_at,
                    delt_av=d.delt_av, delt_av_navn=d.delt_av_navn)
        for d in linje.delinger.all()])
    return ny


# ── Deling med enhetene (19. sep. 2026) ──────────────────────────────────────
#
# «Det skal kunne sendes internt som vil si ikke til ressurser som standard.
# Men meldinger kan ettersendes til ressurs, alle som har oppdrag fra
# hendelsen. Individuelle settes inne i oppdraget.» (André). To former, én
# leser: `Hendelse.delte_linjer_for(oppdrag)` er det oppdragsmodulen og bilen
# spør, og den ser både `delt_at` på linja (alle oppdrag fra hendelsen, også
# de som opprettes *etter* delingen) og `Linjedeling`-radene (ett oppdrag).
# Begge angres. Ingen linje skrives — deling er en tilstand på linja, ikke en
# hendelse i loggen, og det er derfor det ikke blir en systemlinje av det.


def _kan_deles(linje):
    if linje.kilde == KILDE_SYSTEM:
        raise Ugyldig('Systemlinjer deles ikke; enhetene ser statusene selv.')
    if linje.er_fjernet:
        raise Ugyldig('Linja er fjernet og kan ikke deles.')
    if Logglinje.objects.filter(korrigerer=linje).exists():
        raise Ugyldig('Linja er rettet; del den gjeldende linja.')
    if linje.hendelse_id is None:
        raise Ugyldig('Bare linjer i en hendelse kan deles med enhetene.')


def _oppdrag_i_hendelsen(linje, oppdrag):
    if oppdrag.hendelse_id != linje.hendelse_id:
        raise Ugyldig('Oppdraget hører ikke til linjas hendelse.')


@transaction.atomic
def del_linje(linje, *, bruker, oppdrag=None, naa=None) -> bool:
    """Del linja med enhetene. Uten `oppdrag`: med alle oppdrag fra
    hendelsen, nå og senere. Med: bare det ene. Idempotent — å dele en delt
    linje er ikke en feil, det er «ja, fortsatt». Returnerer om noe ble gjort.
    """
    _kan_deles(linje)
    tid = naa or timezone.now()
    navn = getattr(bruker, 'username', '') or ''
    konto = bruker if bruker and bruker.is_authenticated else None
    if oppdrag is None:
        if linje.delt_at is not None:
            return False
        linje.delt_at = tid
        linje.delt_av = konto
        linje.delt_av_navn = navn
        linje.save(update_fields=['delt_at', 'delt_av', 'delt_av_navn'])
        return True
    _oppdrag_i_hendelsen(linje, oppdrag)
    _, ny = Linjedeling.objects.get_or_create(
        linje=linje, oppdrag=oppdrag,
        defaults={'delt_at': tid, 'delt_av': konto, 'delt_av_navn': navn})
    return ny


@transaction.atomic
def angre_deling(linje, *, bruker, oppdrag=None) -> bool:
    """Motstykket. Uten `oppdrag` tas delingen med alle bort — delingene med
    enkeltoppdrag står, de var egne valg. Med `oppdrag` tas bare den ene bort;
    er linja delt med alle, ser oppdraget den fortsatt, og kallet sier fra.
    """
    if oppdrag is None:
        if linje.delt_at is None:
            return False
        linje.delt_at = None
        linje.delt_av = None
        linje.delt_av_navn = ''
        linje.save(update_fields=['delt_at', 'delt_av', 'delt_av_navn'])
        return True
    if linje.delt_at is not None:
        raise Ugyldig('Linja er delt med alle oppdrag i hendelsen; '
                      'angre den delingen i loggen.')
    slettet, _ = Linjedeling.objects.filter(linje=linje, oppdrag=oppdrag).delete()
    return slettet > 0


def delte_for_vakt(vakt) -> list[dict]:
    """Delingstilstanden for hele vakta, i den formen pollen sender hver
    gang (`delte` i `logg_view`): én rad per gjeldende linje som er delt med
    alle eller med minst ett oppdrag. Hele lista, ikke en diff — samme grunn
    som `fjernede` og `festede`: en angret deling er fravær, og fravær kan
    ikke sendes som en endring siden sist.
    """
    qs = (Logglinje.objects.filter(vakt=vakt, korrigert_av__isnull=True,
                                   fjernet_at__isnull=True)
          .filter(Q(delt_at__isnull=False) | Q(delinger__isnull=False))
          .distinct().prefetch_related('delinger'))
    return [{
        'id': l.pk,
        'delt_at': l.delt_at.isoformat() if l.delt_at else None,
        'delt_av': l.delt_av_navn,
        'delt_med': sorted(d.oppdrag_id for d in l.delinger.all()),
    } for l in qs]


def _kjeden_q(rot):
    """`Q` som treffer hele korreksjonskjeden til `rot`, roten inkludert.

    Hvert ledd etter det første bærer `rot`; det første bærer `NULL` og er
    seg selv. Derfor to ledd og ikke ett.
    """
    return Q(pk=rot.pk) | Q(rot=rot)


#: Grunnen KOs egen sletteinngang fører i sladderegisteret (`core/sladding.py`).
FJERN_GRUNN = 'Fjernet fra KO-loggen'


@transaction.atomic
def fjern(linje, *, bruker, naa=None, grunn=FJERN_GRUNN):
    """Sletteinngangen (§4.4) — **tøm innholdet, la rada stå**.

    Unntaket fra append-only, og det er én navngitt vei og ikke en generell
    redigering. Grunnen står i §4.4 og er verdt å gjenta: opplæringen er at
    direkte identifiserende opplysninger ikke skrives i feltet, og det
    reduserer risikoen reelt — men **opplæring forvitrer under press**. En
    travel kveld skriver noen et navn. Designet må anta det, og inngangen er
    billig å bygge inn fra start og vond å ettermontere i en append-only
    modell.

    Rada blir stående med «fjernet av André, 22:10». Et hull i loggen ville
    vært verre enn en tømt linje: da vet ingen at det sto noe der.

    **Hele kjeden tømmes.** Rettes en linje og *deretter* fjernes den, ville
    den opprinnelige teksten blitt stående i den overstyrte raden — usynlig i
    loggen, men fullt lesbar i basen og i backupen. En sletteinngang som lar
    en kopi ligge igjen, er ikke en sletteinngang.

    **Og hver fjernet rad føres i sladderegisteret** (18. okt. 2026, `core/sladding.py`):
    en gjenoppretting av KO-fila tar ellers teksten tilbake. Registeret har aldri teksten.
    Den frosne vaktstatistikken (siste linje på en hendelse) sladdes med.
    """
    from core import sladding

    kjeden = Logglinje.objects.filter(_kjeden_q(linje.rot or linje))
    tid = naa or timezone.now()
    navn = getattr(bruker, 'username', '') or ''
    rader = []
    for rad in kjeden:
        if rad.kilde == KILDE_SYSTEM:
            # Systemlinjer bærer ingen fritekst — de er bygget av verdimengder
            # som alt er ikke-identifiserende. Det er ingenting å fjerne, og
            # en inngang som nådde dem ville vært en vei til å fjerne sporet
            # etter en overstyring.
            continue
        tom_linje(rad, tid=tid, bruker=bruker, navn=navn)
        rader.append((LOGGLINJE, rad.pk, 'tekst'))
    sladding.registrer(rader, grunn=grunn, bruker=bruker, naa=tid)
    return len(rader)


#: Modellnavnet i sladderegisteret.
LOGGLINJE = 'ko.logglinje'


def tom_linje(rad, *, tid, bruker, navn) -> None:
    """Tøm én linje, og kopiene av teksten i vaktens frosne statistikk. Brukt av `fjern` og
    av sladdingen etter en gjenoppretting (`ko/sladding.py`)."""
    from core import sladding

    if rad.tekst:
        # `_siste_operatorlinje` i ko/statistikk.py kapper ved 160 tegn.
        sladding.skrubb_frosne(rad.vakt_id, {rad.tekst, rad.tekst[:160]})
    rad.tekst = ''
    rad.fjernet_at = tid
    rad.fjernet_av = bruker if bruker and bruker.is_authenticated else None
    rad.fjernet_av_navn = navn
    rad.save(update_fields=['tekst', 'fjernet_at', 'fjernet_av', 'fjernet_av_navn'])


def systemlinje(vakt, kode, data, *, tidspunkt=None, bruker=None,
                hendelse=None) -> Logglinje:
    """Skriv en løftet systemhendelse. Kalles fra `ko/signals.py` og fra
    hendelsesreglene under.

    **Ingen forfatter fryses for det som *skjedde*** — en status meldt i en
    bil er ikke ført av noen; hvem som utløste den står i `systemdata` når det
    betyr noe («ført av KO», §3.1, §4.6). **Hendelseslinjene fryser derimot
    operatøren** (`bruker`): «H12 lukket» er en handling, og en handling uten
    hvem svarer ikke på det man leser loggen for.
    """
    from .systemlinjer import KODER

    if kode not in KODER:
        raise Ugyldig(f'Ukjent systemkode «{kode}».')
    linje = Logglinje(
        vakt=vakt,
        kilde=KILDE_SYSTEM,
        systemkode=kode,
        systemdata=data or {},
        tidspunkt=tidspunkt or timezone.now(),
        hendelse=hendelse,
    )
    if bruker is not None:
        _frys_forfatter(linje, bruker)
    linje.save()
    return linje


def slett_utlopte(naa=None, *, dager=None) -> int:
    """Slett linjer eldre enn fristen. Returnerer antallet.

    Kalt av `purge_old_logs`, som kjøres av Railway Cron. **Ekte sletting, ikke
    tømming**: sletteinngangen over fjerner innhold fra en linje som skal bli
    stående i en logg noen leser; dette er lagringstiden som løper ut, og da
    skal rada bort.

    Klokka går fra `registrert_at` og ikke `tidspunkt`: `tidspunkt` er
    korrigerbart, og en frist som lar seg flytte ved å rette et klokkeslett er
    ingen frist.
    """
    naa = naa or timezone.now()
    grense = naa - timedelta(days=dager if dager is not None else oppbevaringsdager())
    qs = Logglinje.objects.filter(registrert_at__lt=grense)
    antall = qs.count()
    if antall:
        # `korrigerer`/`rot` peker innad i settet, og `SET_NULL` gjør
        # slettingen trygg uansett rekkefølge.
        qs.delete()
    # Hendelsene følger samme frist. `Oppdrag.hendelse` og `Logglinje.hendelse`
    # er `SET_NULL`, så en gruppering som forsvinner tar ikke noe med seg —
    # og oppdragene er uansett arkivert og slettet lenge før 730 dager.
    Hendelse.objects.filter(opprettet_at__lt=grense).delete()
    return antall


# ── Hendelser (pulje 5) ──────────────────────────────────────────────────────
#
# Se `docs/FORSLAG_KO.md` §3.3, §4.6 og §6. Hendelsen er grupperingen av
# oppdragslista og filteret i loggen; reglene her er de fire tingene som kan
# gjøres med en, pluss nummereringen. Alt skriver en systemlinje med
# operatøren frosset — det er loggen som er fasit, hendelsen er en visning.

#: Lengste tittel. Det man kaller hendelsen på samband — kort.
MAKS_TITTEL = 120
#: Beskrivelsen har samme tak som en logglinje: fullstendig, ikke ubegrenset.
MAKS_BESKRIVELSE = MAKS_TEKST
MAKS_MELDER = 120


def hendelsesnr(nummer) -> str:
    """`H12`. Formen bor i `systemlinjer`; dette er den samme, eksportert der
    viewene og testene leter etter den."""
    from .systemlinjer import hendelsesnr as _h
    return _h(nummer)


def _hendelsesnokkel(vakt) -> str:
    """Tvillingen av `oppdrag.services._nummer_nokkel` (§6). Prefikset står i
    `NOKLER_UTEN_AUDIT` — telleren er noe maskinen har talt, og uten unntaket
    får du én auditrad per hendelse midt blant de ekte radene."""
    return f'next_hendelse_nr_vakt_{vakt.pk}'


def neste_hendelsesnummer(vakt) -> int:
    """Hent og inkrementer neste hendelsesnummer for vakta, atomisk.

    Samme mønster som `oppdrag.services.neste_oppdragsnummer`: raden i
    `AppSetting` låses med `select_for_update`, og gjenskapes fra dataene om
    den mangler — en slettet rad skal ikke gi nummer 1 om igjen og kollidere
    med `unikt_hendelsesnummer_per_vakt`. Serien er **uavhengig** av
    oppdragsserien og nullstilles ikke av vaktarkivet: hendelsene arkiveres
    ikke, de blir stående til fristen løper ut.
    """
    with transaction.atomic():
        nokkel = _hendelsesnokkel(vakt)
        rad = AppSetting.objects.select_for_update().filter(key=nokkel).first()
        if rad is None:
            hoyeste = (Hendelse.objects.filter(vakt=vakt)
                       .aggregate(models.Max('hendelsesnummer'))['hendelsesnummer__max'])
            AppSetting.objects.create(key=nokkel, value=str((hoyeste or 0) + 1))
            rad = AppSetting.objects.select_for_update().get(key=nokkel)
        nr = int(rad.value)
        rad.value = str(nr + 1)
        rad.save(update_fields=['value'])
        return nr


def rens_tittel(raa) -> str:
    tittel = (raa or '').strip()
    if not tittel:
        raise Ugyldig('Hendelsen må ha en tittel.')
    if len(tittel) > MAKS_TITTEL:
        raise Ugyldig(f'Tittelen er for lang (maks {MAKS_TITTEL} tegn).')
    return tittel


def rens_prioritet(raa) -> str:
    """Én av `PRIORITET_VALG`. `None`/tom gir standarden — skjemaet kan
    utelate feltet — men en ukjent verdi avvises, ikke rettes: «Kritisk» fra
    en gammel klient skal ikke stille bli «Grønn»."""
    verdi = (raa or '').strip().lower()
    if not verdi:
        return PRIORITET_STANDARD
    if verdi not in PRIORITET_NAVN:
        raise Ugyldig('Ukjent prioritet.')
    return verdi


def _rens_kort(raa, maks, hva) -> str:
    tekst = (raa or '').strip()
    if len(tekst) > maks:
        raise Ugyldig(f'{hva} er for lang (maks {maks} tegn).')
    return tekst


def rens_melder(typer, tekst) -> tuple[list[str], str]:
    """Melderen: kodene fra `MELDER_VALG` i fast rekkefølge, og teksten bak
    «Andre». `None` for typene betyr «ikke oppgitt».

    Ukjent kode er 400, ikke stille utelatt — en avkryssing som forsvinner
    uten å si fra er en feil man ser i loggen et døgn senere. **Teksten
    kreves når «Andre» er valgt, og tømmes når den ikke er:** «Andre» uten å
    si hvem er ingen melder, og en tekst uten «Andre» er en melder ingen ser.
    """
    if typer is None:
        return None, _rens_kort(tekst, MAKS_MELDER, 'Melder')
    if not isinstance(typer, (list, tuple)):
        raise Ugyldig('Melder må være en liste.')
    onsket = {str(t).strip().lower() for t in typer}
    ukjente = onsket - set(MELDER_NAVN)
    if ukjente:
        raise Ugyldig('Ukjent melder.')
    valgte = [kode for kode, _ in MELDER_VALG if kode in onsket]
    tekst = _rens_kort(tekst, MAKS_MELDER, 'Melder')
    if MELDER_ANDRE in valgte and not tekst:
        raise Ugyldig('Skriv hvem melderen er når «Andre» er valgt.')
    if MELDER_ANDRE not in valgte:
        tekst = ''
    return valgte, tekst


def melder_tekst(hendelse) -> str:
    """«Egen ressurs, Andre (arrangørvakt)». Regelen står på modellen
    (`Hendelse.melder_tekst`) fra 19. okt. 2026, så oppdraget leser den samme."""
    return hendelse.melder_tekst()


def lag_som_kan_velges(vakt, hendelse=None):
    """Ressursene et lag på hendelsen kan være: vaktlistas ressurser **uten**
    oppdragsenhet, i lista som er i bruk, **med et skift som dekker nå**
    (`ressurser_paa_vakt_naa`, André 19. sep. 2026: «bare de som er på vakt
    nå»). `ko` → `vaktliste` er den tillatte retningen. Samme scope som
    `ressurser_uten_enhet()`, som tegner kortene — et lag man kan velge skal
    være et lag man kan se.

    **Lagene som alt står på `hendelse` er lov uansett skift.** Skjemaet og
    brikkene sender hele lista, og et lag hvis skift gikk ut mens det sto på
    hendelsen skal ikke gjøre lista umulig å lagre — det tas av ved å utelates,
    ikke ved at alt annet nektes."""
    from vaktliste.models import Ressurs
    from vaktliste.vaktdrift import ressurser_paa_vakt_naa, vaktliste_i_bruk

    liste = vaktliste_i_bruk()
    if liste is None:
        return Ressurs.objects.none()
    paa_vakt = ressurser_paa_vakt_naa(liste)
    if hendelse is None:
        return paa_vakt
    allerede = [l.ressurs_id for l in hendelse.lag.all() if l.ressurs_id]
    return Ressurs.objects.filter(
        Q(pk__in=paa_vakt.values('pk')) | Q(pk__in=allerede),
        vaktliste=liste, enhet__isnull=True)


def _lag_fra(vakt, ider, hendelse=None):
    """Ressursene bak en liste med id-er. Ukjent id er 400. `None` betyr
    «ikke oppgitt»; `[]` betyr «ingen»."""
    if ider is None:
        return None
    if not isinstance(ider, (list, tuple)):
        raise Ugyldig('Lag må være en liste.')
    try:
        onsket = {int(i) for i in ider}
    except (TypeError, ValueError):
        raise Ugyldig('Lag må være tall.')
    rader = list(lag_som_kan_velges(vakt, hendelse).filter(pk__in=onsket))
    if len(rader) != len(onsket):
        raise Ugyldig('Ukjent lag.')
    return rader


def _hendelsesdata(hendelse) -> dict:
    return {'hendelsesnummer': hendelse.hendelsesnummer, 'tittel': hendelse.tittel,
            'lokasjon': hendelse.lokasjon_navn,
            'prioritet': PRIORITET_NAVN.get(hendelse.prioritet, '')}


def bli_med(hendelse, bruker) -> bool:
    """Meld operatøren på hendelsen. Idempotent; `True` når raden var ny.

    Kalles av **hver skriving på hendelsen** — kommentar, oppdrag, prioritet,
    redigering — og av «Bli med»-knappen (André, 18. sep. 2026). Ikke av
    lesing: å åpne H14 for å se hva som skjer er ikke å jobbe med den.
    Anonyme og systemkall melder ingen inn.
    """
    if bruker is None or not getattr(bruker, 'is_authenticated', False):
        return False
    navn = getattr(bruker, 'username', '') or ''
    if not navn:
        return False
    _, ny = HendelseDeltaker.objects.get_or_create(
        hendelse=hendelse, brukernavn=navn, defaults={'bruker': bruker})
    return ny


@transaction.atomic
def opprett_hendelse(vakt, raa_tittel, *, bruker, lokasjon=None,
                     fra_linje=None, prioritet=None, beskrivelse=None,
                     melder_typer=None, melder=None, lag=None) -> Hendelse:
    """Ny hendelse. Fra en logglinje eller fra ingenting.

    **Linja blir stående** (§4.5): hendelsen peker tilbake på den, og linja
    får hendelsen som sin — den er den første linja i hendelsens filter. Å
    flytte linja inn ville gitt loggen et hull akkurat der det viktige skjedde.

    **Alt valideres før nummeret trekkes.** Telleren er atomisk og lar seg
    ikke rulle tilbake av en 400 — en avvist innsending som alt hadde hentet
    H14 ville etterlatt et hull i serien, og hull i en serie folk sier høyt
    er spørsmål i etterkant.

    Den som oppretter er på hendelsen fra første sekund (`bli_med`).

    **Beskrivelsen blir den første linja i hendelsens logg** (19. sep. 2026),
    ført av den som oppretter — én mekanisme, ikke et felt pluss en logg. Den
    er intern som alle andre linjer; «Nytt oppdrag» kopierer den inn i
    oppdragsnotatet, og der redigerer operatøren fritt. Lagene som
    velges i skjemaet står på opprettelseslinja, ikke som én linje hver: de
    kom med hendelsen, og fem linjer for én handling leser som fem ting.
    """
    tittel = rens_tittel(raa_tittel)
    prio = rens_prioritet(prioritet)
    beskrivelse = _rens_kort(beskrivelse, MAKS_BESKRIVELSE, 'Beskrivelsen')
    typer, melder = rens_melder(melder_typer, melder)
    lagene = _lag_fra(vakt, lag) or []
    if fra_linje is not None and fra_linje.vakt_id != vakt.pk:
        raise Ugyldig('Linja hører til en annen vakt.')
    hendelse = Hendelse(
        vakt=vakt,
        hendelsesnummer=neste_hendelsesnummer(vakt),
        tittel=tittel,
        lokasjon=lokasjon,
        lokasjon_navn=getattr(lokasjon, 'navn', '') or '',
        prioritet=prio,
        melder_typer=typer or [],
        melder=melder,
        opprettet_av=bruker if bruker and bruker.is_authenticated else None,
        opprettet_av_navn=getattr(bruker, 'username', '') or '',
        opprettet_fra_linje=fra_linje,
    )
    hendelse.save()
    if fra_linje is not None and fra_linje.hendelse_id is None:
        fra_linje.hendelse = hendelse
        fra_linje.save(update_fields=['hendelse'])
    data = _hendelsesdata(hendelse)
    if lagene:
        data['lag'] = [r.navn for r in lagene]
    systemlinje(vakt, _kode('HENDELSE_OPPRETTET'), data,
                bruker=bruker, hendelse=hendelse)
    if lagene:
        sett_lag(hendelse, [r.pk for r in lagene], bruker=bruker, logg=False)
    if beskrivelse:
        hendelse.beskrivelse_linje = skriv_linje(vakt, beskrivelse, bruker=bruker, hendelse=hendelse)
        hendelse.save(update_fields=['beskrivelse_linje'])
    bli_med(hendelse, bruker)
    return hendelse


# ── Beskrivelsen i hodet (19. okt. 2026) ─────────────────────────────────────
#
# «Kunne oppdatere … beskrivelsen står som fast oversikt i hendelsen.
# Tidskritisk informasjon» (André). Beskrivelsen er fortsatt en logglinje —
# valget fra 19. sep. står, og André bekreftet det 19. okt.: en oppdatering er
# en **retting** i kjeden, så hvem som endret hva og når kan leses etterpå, og
# en delt beskrivelse forblir delt (rettingen arver delingen).

def gjeldende_i_kjeden(rot):
    """Kjedens gjeldende ledd: det som ikke er rettet. `None` uten rot."""
    if rot is None:
        return None
    return (Logglinje.objects.filter(_kjeden_q(rot), korrigert_av__isnull=True)
            .order_by('-id').first())


@transaction.atomic
def sett_beskrivelse(hendelse, raa_tekst, *, bruker, sett_linje=None, naa=None) -> Logglinje:
    """Skriv eller oppdater beskrivelsen. Returnerer linja slik den nå står.

    Har hendelsen ingen (eller er den fjernet med sletteinngangen), blir det
    en ny linje som hodet peker på. Ellers rettes det gjeldende leddet.

    **Den deles med enhetene, og det står i loggen hvem som gjorde det**
    (André, 19. okt. 2026: «når du oppdaterer beskrivelse så må det og komme
    frem til bil enheter … Det bør og oppdateres i hendelsesloggen hvem som
    oppdaterte»). Beskrivelsen fra «Ny hendelse» er fortsatt intern til den
    deles; det er *oppdateringen* — her, fra hodet eller «Rediger» — som går
    ut. Systemlinja (`HENDELSE_BESKRIVELSE`) sier hvem, uten teksten.

    **`sett_linje` er linja klienten så**, som `versjon` i hodet: er
    beskrivelsen oppdatert av noen andre siden, er det 409 og ikke en stille
    overskriving — tidskritisk tekst er nøyaktig den som ikke skal forsvinne.
    Utelatt betyr «rett det som står», som API-et ellers.
    """
    tekst = _rens_kort(raa_tekst, MAKS_BESKRIVELSE, 'Beskrivelsen')
    if not tekst:
        raise Ugyldig('Beskrivelsen kan ikke være tom.')
    gjeldende = gjeldende_i_kjeden(hendelse.beskrivelse_linje)
    if gjeldende is None or gjeldende.er_fjernet:
        ny = skriv_linje(hendelse.vakt, tekst, bruker=bruker, hendelse=hendelse, naa=naa)
        hendelse.beskrivelse_linje = ny
        hendelse.save(update_fields=['beskrivelse_linje'])
    else:
        if sett_linje not in (None, '') and str(sett_linje) != str(gjeldende.pk):
            raise AlleredeKorrigert('Beskrivelsen er oppdatert av noen andre — '
                                    'les den nye før du endrer.')
        ny = korriger(gjeldende, bruker=bruker, tekst=tekst, naa=naa)
    del_linje(ny, bruker=bruker, naa=naa)
    data = _hendelsesdata(hendelse)
    data.update(av=getattr(bruker, 'username', '') or '', ny=gjeldende is None or gjeldende.er_fjernet)
    systemlinje(hendelse.vakt, _kode('HENDELSE_BESKRIVELSE'), data,
                tidspunkt=naa, bruker=bruker, hendelse=hendelse)
    bli_med(hendelse, bruker)
    return ny


# ── Eksterne ressurser: varslet eller ikke (19. okt. 2026) ───────────────────
#
# «Legge inn andre eksterne ressurser, samt avkryssing på om og når de er
# varslet … Automatisk loggføres og deles til aktuelle ressurser» (André).
# Raden er tilstanden; linja er det loggen og bilene ser. Linja er en
# **operatørlinje** i hennes navn og ikke en systemlinje: det er det hun ville
# skrevet selv, den skal kunne deles (systemlinjer deles ikke — bilene ser
# statusene sine selv, mens «Brann varslet» ser de ellers aldri), og den kan
# rettes som alt annet hun skriver.

def _varslingstekst(navn) -> str:
    return f'Varslet {navn}'


def _angretekst(navn) -> str:
    return f'Varsling av {navn} angret'


@transaction.atomic
def varsle(hendelse, ressurs, *, bruker, tidspunkt=None, naa=None) -> HendelseVarsling:
    """Kryss av at `ressurs` er varslet. Idempotent: er den alt varslet,
    står den første avkryssingen — to operatører som trykker samtidig skal
    ikke få to linjer i loggen."""
    if hendelse.er_lukket:
        raise Ugyldig('Hendelsen er lukket — åpne den igjen først.')
    if ressurs is None or not ressurs.er_aktiv:
        raise Ugyldig('Ukjent eller inaktiv ekstern aktør.')
    finnes = hendelse.varslinger.filter(ressurs=ressurs).first()
    if finnes is not None:
        return finnes
    # Tida prøves av `skriv_linje` (`vurder_tidspunkt`), og raden får linjas:
    # én regel for hva som er lov, og raden og loggen sier det samme.
    linje = skriv_linje(hendelse.vakt, _varslingstekst(ressurs.navn), bruker=bruker,
                        tidspunkt=tidspunkt, hendelse=hendelse, naa=naa)
    del_linje(linje, bruker=bruker, naa=naa)
    return HendelseVarsling.objects.create(
        hendelse=hendelse, ressurs=ressurs, navn=ressurs.navn, varslet_at=linje.tidspunkt,
        av=bruker if bruker and getattr(bruker, 'is_authenticated', False) else None,
        av_navn=getattr(bruker, 'username', '') or '', linje=linje)


# ── Talegruppa (TG) i Nødnett (19. okt. 2026) ───────────────────────────────
#
# «TG er talegruppe som vi bruker i nødnett … Når den settes bør de kunne
# velge å om å dele til bil enheter» (André). Hver endring er en operatørlinje
# i hendelsen — «TG: SAMVIRKE 2» — så loggen viser når hendelsen byttet
# talegruppe; delt når hun valgte det, og da ser bilene både linja og TG-en
# fast på oppdraget (`hendelse_talegruppe`).

MAKS_TALEGRUPPE = 40


@transaction.atomic
def sett_talegruppe(hendelse, raa, *, bruker, del_med_enhetene=False, naa=None) -> Hendelse:
    """Sett, bytt eller fjern TG. Navnet må stå i portalens liste og være
    aktivt — med ett unntak: det hendelsen alt står på, kan beholdes når bare
    delingen endres. Tom tekst fjerner. Uendret (samme TG, samme deling) er
    ingen endring og gir ingen linje."""
    if hendelse.er_lukket:
        raise Ugyldig('Hendelsen er lukket — åpne den igjen først.')
    navn = (raa or '').strip()
    delt = bool(del_med_enhetene) and bool(navn)
    if navn and navn != hendelse.talegruppe and not Talegruppe.objects.i_portal(
            hendelse.vakt.portal).filter(navn=navn, er_aktiv=True).exists():
        raise Ugyldig('Ukjent talegruppe — den settes opp under KO-innstillinger.')
    if navn == hendelse.talegruppe and delt == hendelse.talegruppe_delt:
        return hendelse
    # Var den delt, ser bilene at den fjernes — ellers står de med en TG som
    # ikke gjelder.
    del_linja = delt or (not navn and hendelse.talegruppe_delt)
    hendelse.talegruppe = navn
    hendelse.talegruppe_delt = delt
    hendelse.save(update_fields=['talegruppe', 'talegruppe_delt'])
    linje = skriv_linje(hendelse.vakt, f'TG: {navn}' if navn else 'TG fjernet',
                        bruker=bruker, hendelse=hendelse, naa=naa)
    if del_linja:
        del_linje(linje, bruker=bruker, naa=naa)
    return hendelse


@transaction.atomic
def angre_varsling(hendelse, ressurs_id, *, bruker) -> bool:
    """Ta avkryssingen bort. Raden slettes, og linja **rettes** til «…
    angret»: rettingen arver delingen, så bilen som så «Varslet Brann» ser at
    det ikke stemmer lenger — en slettet linje ville bare forsvunnet fra
    skjermen hennes. Returnerer om noe ble gjort."""
    if hendelse.er_lukket:
        raise Ugyldig('Hendelsen er lukket — åpne den igjen først.')
    rad = hendelse.varslinger.filter(ressurs_id=ressurs_id).first()
    if rad is None:
        return False
    gjeldende = gjeldende_i_kjeden(rad.linje)
    if gjeldende is not None and not gjeldende.er_fjernet \
            and gjeldende.tekst != _angretekst(rad.navn):
        korriger(gjeldende, bruker=bruker, tekst=_angretekst(rad.navn))
    rad.delete()
    bli_med(hendelse, bruker)
    return True


@transaction.atomic
def sett_lag(hendelse, ressurs_ider, *, bruker, naa=None, logg=True):
    """Sett hvilke lag som er på hendelsen. Returnerer `(lagt_til, tatt_av)`
    som navn.

    **Mengde, ikke handling**, fordi skjemaet og brikkene i hendelsen begge
    sender hele lista — og differansen regnes ut her, ett sted. Hvert lag som
    kommer til eller går får sin egen systemlinje (`logg=True`); ved
    opprettelse står de på opprettelseslinja i stedet. En lukket hendelse tar
    ikke imot — som `knytt_oppdrag`: ellers betyr «lukket» ingenting.
    """
    from . import tavle

    if hendelse.er_lukket:
        raise Ugyldig('Hendelsen er lukket — åpne den igjen først.')
    onsket = _lag_fra(hendelse.vakt, ressurs_ider, hendelse)
    if onsket is None:
        raise Ugyldig('Lag må være en liste.')
    naa = naa or timezone.now()
    naa_rader = {l.ressurs_id: l for l in hendelse.lag.all() if l.ressurs_id}
    onsket_ider = {r.pk for r in onsket}
    lagt_til, tatt_av = [], []
    for r in onsket:
        if r.pk in naa_rader:
            continue
        HendelseLag.objects.create(
            hendelse=hendelse, ressurs=r, ressurs_navn=r.navn, fra=naa,
            av=bruker if bruker and getattr(bruker, 'is_authenticated', False) else None,
            av_navn=getattr(bruker, 'username', '') or '')
        # Hendelsen har forrang på tavla (22. sep. 2026): plassen laget sto
        # på, lukkes nå.
        tavle.avslutt_for_hendelse(r.pk, naa)
        lagt_til.append(r.navn)
    for ressurs_id, rad in naa_rader.items():
        if ressurs_id not in onsket_ider:
            tatt_av.append(rad.ressurs_navn)
            # Tida på hendelsen blir historikk på tavla, og laget står uten plass.
            tavle.skriv_hendelsestid(rad, naa)
            rad.delete()
            # Laget står uten plass nå; kartet skal vite det.
            meld_lag(ressurs_id)
    if logg:
        for navn in lagt_til:
            data = _hendelsesdata(hendelse)
            data['lag'] = navn
            systemlinje(hendelse.vakt, _kode('HENDELSE_LAG_PAA'), data,
                        tidspunkt=naa, bruker=bruker, hendelse=hendelse)
        for navn in tatt_av:
            data = _hendelsesdata(hendelse)
            data['lag'] = navn
            systemlinje(hendelse.vakt, _kode('HENDELSE_LAG_AV'), data,
                        tidspunkt=naa, bruker=bruker, hendelse=hendelse)
    if lagt_til or tatt_av:
        bli_med(hendelse, bruker)
    return lagt_til, tatt_av


def _kode(navn):
    from . import systemlinjer
    return getattr(systemlinjer, navn)


def _krev_versjon(hendelse, versjon):
    """§7.1: hodet er det ene delte redigerbare, og siste skriver skal ikke
    spise den andres tekst i stillhet. `None` betyr «klienten oppga ingen» —
    og det avvises også: en klient som ikke sier hva den så, kan ikke vite at
    den skriver over noe."""
    try:
        oppgitt = int(versjon)
    except (TypeError, ValueError):
        raise Konflikt('Oppgi versjonen du redigerte fra.')
    if oppgitt != hendelse.versjon:
        raise Konflikt('Hendelsen er endret av noen andre. Last den på nytt.')


@transaction.atomic
def rediger_hendelse(hendelse, *, bruker, versjon, tittel=None,
                     lokasjon=None, sett_lokasjon=False, melder_typer=None,
                     melder=None, lag=None) -> Hendelse:
    """Hodet: tittel, lokasjon, melder — og lagene, som går gjennom
    `sett_lag` og logges der. Ingen systemlinje for feltene: det er
    feltendringer, og `audit/` fører dem — regel 2 i `ko/systemlinjer.py`.
    Prioriteten har sin egen inngang (`sett_prioritet`), fordi *den* er en
    handling og skal stå i loggen. Beskrivelsen redigeres ikke her: den er
    den første linja i loggen, og en linje rettes med `korriger`.

    `sett_lokasjon=True` med `lokasjon=None` tømmer lokasjonen; uten flagget
    rører kallet den ikke. Et nullbart felt trenger tre tilstander i kallet.
    Tekstfeltene bruker `None` som «ikke oppgitt» og tom streng som «tøm».
    Den som redigerer er på hendelsen.
    """
    _krev_versjon(hendelse, versjon)
    endret = []
    if tittel is not None:
        ny = rens_tittel(tittel)
        if ny != hendelse.tittel:
            hendelse.tittel = ny
            endret.append('tittel')
    if sett_lokasjon:
        hendelse.lokasjon = lokasjon
        hendelse.lokasjon_navn = getattr(lokasjon, 'navn', '') or ''
        endret += ['lokasjon', 'lokasjon_navn']
    if melder_typer is not None or melder is not None:
        typer, tekst = rens_melder(
            melder_typer if melder_typer is not None else hendelse.melder_typer,
            melder if melder is not None else hendelse.melder)
        if typer != (hendelse.melder_typer or []):
            hendelse.melder_typer = typer
            endret.append('melder_typer')
        if tekst != hendelse.melder:
            hendelse.melder = tekst
            endret.append('melder')
    lag_endret = False
    if lag is not None:
        onsket = {r.pk for r in _lag_fra(hendelse.vakt, lag, hendelse)}
        naa_ider = {l.ressurs_id for l in hendelse.lag.all() if l.ressurs_id}
        lag_endret = onsket != naa_ider
    if not endret and not lag_endret:
        raise Ugyldig('Ingenting er endret.')
    if lag_endret:
        sett_lag(hendelse, lag, bruker=bruker)
    hendelse.versjon += 1
    hendelse.save(update_fields=endret + ['versjon'])
    if sett_lokasjon and not hendelse.er_lukket:
        # Nytt sted på hendelsen flytter lagene som står på den.
        for rad in hendelse.lag.all():
            meld_lag(rad.ressurs_id)
    bli_med(hendelse, bruker)
    return hendelse


@transaction.atomic
def sett_prioritet(hendelse, raa, *, bruker, naa=None) -> Hendelse:
    """Sett prioriteten — **med en systemlinje**, aldri stille. «H14 satt
    til Viktig» er en avgjørelse noen tok, og den skal stå i loggen med hvem
    (André, 18. sep. 2026). Ingen versjon: feltet er ett valg av fem, og
    siste trykk vinner uten at noen tekst går tapt. Versjonen telles likevel
    opp, så en som redigerer hodet samtidig får vite at noe skjedde."""
    ny = rens_prioritet(raa)
    if ny == hendelse.prioritet:
        raise Ugyldig('Prioriteten er alt satt.')
    fra = hendelse.prioritet
    hendelse.prioritet = ny
    hendelse.versjon += 1
    hendelse.save(update_fields=['prioritet', 'versjon'])
    data = _hendelsesdata(hendelse)
    data['fra_prioritet'] = PRIORITET_NAVN.get(fra, '')
    systemlinje(hendelse.vakt, _kode('HENDELSE_PRIORITET'), data,
                tidspunkt=naa or timezone.now(), bruker=bruker, hendelse=hendelse)
    bli_med(hendelse, bruker)
    return hendelse


def apne_oppdrag_i(hendelse) -> int:
    """Oppdragene på hendelsen som ikke er ferdige. `ko` → `oppdrag` er den
    tillatte retningen; her leses `related_name='oppdrag'` på FK-en."""
    from oppdrag import choices
    return hendelse.oppdrag.exclude(status=choices.TERMINAL).count()


@transaction.atomic
def lukk_hendelse(hendelse, *, bruker, confirm=False, naa=None) -> Hendelse:
    """Lukk. **409 når hendelsen har åpne oppdrag, og gjennom med `confirm`**
    (§4.6): en lukket hendelse med kjørende biler er nøyaktig tilstanden der en
    enhet blir glemt. Operatøren skal aldri møte en vegg, bare en dør hun må
    åpne bevisst — og at hun åpnet den står på linja."""
    from . import tavle

    if hendelse.er_lukket:
        raise Ugyldig('Hendelsen er allerede lukket.')
    apne = apne_oppdrag_i(hendelse)
    if apne and not confirm:
        raise HarApneOppdrag(apne)
    tid = naa or timezone.now()
    hendelse.status = HENDELSE_LUKKET
    hendelse.lukket_at = tid
    hendelse.lukket_av = bruker if bruker and bruker.is_authenticated else None
    hendelse.lukket_av_navn = getattr(bruker, 'username', '') or ''
    hendelse.versjon += 1
    hendelse.save(update_fields=['status', 'lukket_at', 'lukket_av',
                                 'lukket_av_navn', 'versjon'])
    # Lagene går til «Uten plass» på tavla (André, 22. sep. 2026), og tida
    # de sto på hendelsen blir historikk der.
    for rad in hendelse.lag.all():
        tavle.skriv_hendelsestid(rad, tid)
        # Lagene står uten sted når hendelsen lukkes.
        meld_lag(rad.ressurs_id)
    data = _hendelsesdata(hendelse)
    data['apne_oppdrag'] = apne
    systemlinje(hendelse.vakt, _kode('HENDELSE_LUKKET'), data, tidspunkt=tid,
                bruker=bruker, hendelse=hendelse)
    return hendelse


@transaction.atomic
def gjenapne_hendelse(hendelse, *, bruker, naa=None) -> Hendelse:
    """Åpne igjen. Lukkingen var en misforståelse eller et feilklikk (André,
    18. sep. 2026) — og **det logges**, som egen linje. `lukket_*` tømmes:
    feltene sier når den *er* lukket, og loggen bærer historien."""
    if not hendelse.er_lukket:
        raise Ugyldig('Hendelsen er ikke lukket.')
    hendelse.status = HENDELSE_APEN
    hendelse.lukket_at = None
    hendelse.lukket_av = None
    hendelse.lukket_av_navn = ''
    hendelse.versjon += 1
    hendelse.save(update_fields=['status', 'lukket_at', 'lukket_av',
                                 'lukket_av_navn', 'versjon'])
    # Lagene som sto på den, står på den igjen — og dermed på stedet.
    for rad in hendelse.lag.all():
        meld_lag(rad.ressurs_id)
    systemlinje(hendelse.vakt, _kode('HENDELSE_GJENAPNET'), _hendelsesdata(hendelse),
                tidspunkt=naa or timezone.now(), bruker=bruker, hendelse=hendelse)
    return hendelse


@transaction.atomic
def knytt_oppdrag(oppdrag, hendelse, *, bruker, naa=None):
    """Knytt et oppdrag til en hendelse, flytt det, eller løsne det (`None`).

    **Den ene skriveren av `Oppdrag.hendelse`.** Oppdragsmodulen leser feltet
    og skriver det aldri — grupperingen er KOs, og retningen `ko` → `oppdrag`
    holder. Nummeret på oppdraget rører ingen: nummeret identifiserer, FK-en
    relaterer (§6).

    En lukket hendelse tar ikke imot nye oppdrag: åpne den igjen først. Ellers
    ville «lukket» betydd ingenting, og 409-sperra i `lukk_hendelse` vært
    omgått bakveien.
    """
    if hendelse is not None:
        if hendelse.vakt_id != oppdrag.vakt_id:
            raise Ugyldig('Hendelsen hører til en annen vakt.')
        if hendelse.er_lukket:
            raise Ugyldig('Hendelsen er lukket — åpne den igjen først.')
    fra = oppdrag.hendelse
    if (hendelse.pk if hendelse else None) == oppdrag.hendelse_id:
        raise Ugyldig('Ingenting er endret.')
    oppdrag.hendelse = hendelse
    oppdrag.save(update_fields=['hendelse', 'updated_at'])
    systemlinje(
        oppdrag.vakt, _kode('OPPDRAG_KNYTTET'),
        {'oppdragsnummer': oppdrag.oppdragsnummer,
         'hendelsesnummer': hendelse.hendelsesnummer if hendelse else None,
         'fra_hendelsesnummer': fra.hendelsesnummer if fra else None},
        tidspunkt=naa or timezone.now(), bruker=bruker,
        hendelse=hendelse or fra)
    if hendelse is not None:
        bli_med(hendelse, bruker)
    return oppdrag


def nye_for(bruker, vakt) -> dict[int, int]:
    """`{hendelse_id: antall}` — linjer i hver hendelse som er nye for `bruker`
    (27. sep. 2026, André: «nytt siden sist du åpnet hendelsen»).

    **Nytt** er en gjeldende, ikke fjernet linje i hendelsen, skrevet av
    *noen andre*, med høyere id enn brukerens lesemerke. Egne linjer er aldri
    nye: den som skrev dem har sett dem. Systemlinjene teller — «H14 satt til
    Viktig av Kari» er nettopp det man skal legge merke til. En retting er en
    ny rad og teller som ny; det er den også.

    Én spørring for hele vakta, som `hendelser_for`: lista følger hver poll.
    Hendelser uten noe nytt står ikke i svaret.
    """
    merke = (HendelseLest.objects
             .filter(hendelse=models.OuterRef('hendelse'), bruker=bruker)
             .values('til_linje')[:1])
    rader = (Logglinje.objects.gjeldende(vakt)
             .filter(hendelse__isnull=False, fjernet_at__isnull=True)
             .exclude(forfatter=bruker)
             .annotate(merke=Coalesce(models.Subquery(merke), models.Value(0)))
             .filter(pk__gt=models.F('merke'))
             .order_by()
             .values('hendelse_id')
             .annotate(n=models.Count('pk')))
    return {r['hendelse_id']: r['n'] for r in rader}


def merk_lest(bruker, hendelse, til_linje) -> int:
    """Flytt brukerens lesemerke i `hendelse` fram til `til_linje`.

    **Bare framover**: to faner eller skjerm 2 kan melde i ulik rekkefølge, og
    et eldre merke skal ikke gjøre linjer nye igjen. **Aldri forbi siste
    linje** i hendelsen: et merke lenger fram ville stille lest linjer som
    ennå ikke er skrevet. Returnerer merket slik det står.
    """
    siste = (Logglinje.objects.filter(hendelse=hendelse)
             .aggregate(m=models.Max('pk'))['m'] or 0)
    til = max(0, min(int(til_linje), siste))
    with transaction.atomic():
        rad, _ = HendelseLest.objects.select_for_update().get_or_create(
            hendelse=hendelse, bruker=bruker)
        if til > rad.til_linje:
            rad.til_linje = til
            rad.save(update_fields=['til_linje', 'oppdatert_at'])
    return rad.til_linje


def hendelser_for(vakt):
    """Alle hendelsene i vakta med tellingene tavla trenger, nyeste først.

    Én spørring for tellingene, ikke én per hendelse: lista følger med hver
    logg-henting, fra hver operatør — ved hver endring, og ellers hvert 30. s.
    """
    from oppdrag import choices
    qs = (Hendelse.objects.filter(vakt=vakt)
          .annotate(
              antall_oppdrag=models.Count('oppdrag', distinct=True),
              apne_oppdrag=models.Count(
                  'oppdrag', distinct=True,
                  filter=~Q(oppdrag__status=choices.TERMINAL)))
          .prefetch_related('deltakere', 'lag', 'varslinger')
          .order_by('-hendelsesnummer'))
    return list(qs)


def hendelse_med_telling(hendelse):
    """Samme rad som `hendelser_for` gir, for én hendelse: viewet som
    nettopp opprettet den skal svare med den formen tavla leser."""
    from oppdrag import choices
    return (Hendelse.objects.filter(pk=hendelse.pk)
            .annotate(
                antall_oppdrag=models.Count('oppdrag', distinct=True),
                apne_oppdrag=models.Count(
                    'oppdrag', distinct=True,
                    filter=~Q(oppdrag__status=choices.TERMINAL)))
            .prefetch_related('deltakere', 'lag', 'varslinger')
            .get())


# ── Nullstilling (18. sep. 2026) ─────────────────────────────────────────────
#
# «Det skal gå an for test og utvikling. På prod så står admin ansvarlig for
# databehandlingen» (André). Tre navngitte inngangene, **global admin**,
# bekreftelse server-side, én auditrad hver — og alle scopet til **aktiv
# vakt**: en nullstilling skal aldri kunne ta med seg fjorårets logg. Oppdragene
# nullstilles av oppdragsmodulens egen `nullstill_vakt`; retningen `ko` →
# `oppdrag` holder.

@transaction.atomic
def nullstill_hendelser(vakt) -> int:
    """Slett alle hendelsene i vakta og telleren. Linjene og oppdragene blir
    stående — begge pekerne er `SET_NULL` — så loggen mister bare H-merkene,
    ikke fortellingen. Returnerer antallet."""
    antall = Hendelse.objects.filter(vakt=vakt).count()
    Hendelse.objects.filter(vakt=vakt).delete()
    AppSetting.objects.filter(key=_hendelsesnokkel(vakt)).delete()
    return antall


@transaction.atomic
def nullstill_logg(vakt) -> int:
    """Slett alle logglinjene i vakta, systemlinjer inkludert. `korrigerer` og
    `rot` peker innad i settet og er `SET_NULL`, så rekkefølgen er trygg.
    Hendelsene blir stående (uten linjer)."""
    qs = Logglinje.objects.filter(vakt=vakt)
    antall = qs.count()
    qs.delete()
    return antall
