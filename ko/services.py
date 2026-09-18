"""Reglene for KO-loggen. Alt som skriver en linje går gjennom denne fila.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Viewene eier HTTP-en, signalene
eier løftet av systemhendelser, og **begge kaller hit** — en regel med to
lesere skrives én gang, ellers har loggen to sannheter om hva en gyldig linje
er.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import AppSetting
from core.vakt import hent_aktiv_vakt

from .models import (
    HENDELSE_APEN, HENDELSE_LUKKET, KILDE_OPERATOR, KILDE_SYSTEM, Ansvarsmerke,
    Hendelse, Logglinje,
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

#: Ansvarsområdene (§5.1). Fast liste i kode, ikke fritekst: «samband» og
#: «Samband» skal være samme merke. Utvides her når noen savner ett.
ANSVARSOMRAADER: tuple[str, ...] = ('samband', 'ressurser', 'logg', 'media')

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
    raa = AppSetting.get(CHAT_NOKKEL, None)
    return str(raa).strip().lower() in ('1', 'true', 'ja', 'on')


def ansvar_for(bruker) -> str:
    """Operatørens ansvarsmerke, eller tom streng."""
    if bruker is None or not getattr(bruker, 'is_authenticated', False):
        return ''
    merke = Ansvarsmerke.objects.filter(bruker=bruker).first()
    return merke.omraade if merke else ''


def sett_ansvar(bruker, omraade) -> str:
    """Sett (eller tøm) operatørens ansvarsmerke. Ukjent område avvises —
    lista er fast nettopp for at merket skal bety det samme hos alle."""
    omraade = (omraade or '').strip().lower()
    if omraade and omraade not in ANSVARSOMRAADER:
        raise Ugyldig('Ukjent ansvarsområde.')
    Ansvarsmerke.objects.update_or_create(bruker=bruker, defaults={'omraade': omraade})
    return omraade


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
                ansvarsomraade=None, uformell=False, naa=None) -> Logglinje:
    """En menneskeskrevet linje. Den vanlige veien inn i loggen.

    **Ansvarsområdet stemples fra operatørens merke** når kallet ikke oppgir
    et (§5.1): det er slik «ført av Kari, samband» kommer på linja uten at hun
    skriver det hver gang. Oppgitt verdi vinner — testene og API-et kan sette
    det eksplisitt.

    **`uformell` krever at chatten er slått på** (§4.5). Sperren står her og
    ikke bare i skjemaet: en klient som sender flagget når admin har slått
    chatten av, skal møte den samme døra.
    """
    tekst = rens_tekst(raa_tekst)
    tid = vurder_tidspunkt(tidspunkt, naa)
    if uformell and not chat_tillatt():
        raise Ugyldig('Chatten er slått av. Skriv linja som en vanlig logglinje.')
    if ansvarsomraade is None:
        ansvarsomraade = ansvar_for(bruker)
    linje = Logglinje(
        vakt=vakt,
        kilde=KILDE_OPERATOR,
        tidspunkt=tid,
        tekst=tekst,
        ansvarsomraade=(ansvarsomraade or '').strip()[:40],
        uformell=bool(uformell),
    )
    _frys_forfatter(linje, bruker)
    linje.save()
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
        # Merket arves: en retting av en chatlinje er fortsatt chat.
        uformell=linje.uformell,
        korrigerer=linje,
        rot=linje.rot or linje,
    )
    _frys_forfatter(ny, bruker)
    ny.save()
    return ny


def _kjeden_q(rot):
    """`Q` som treffer hele korreksjonskjeden til `rot`, roten inkludert.

    Hvert ledd etter det første bærer `rot`; det første bærer `NULL` og er
    seg selv. Derfor to ledd og ikke ett.
    """
    return Q(pk=rot.pk) | Q(rot=rot)


@transaction.atomic
def fjern(linje, *, bruker, naa=None):
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
    """
    kjeden = Logglinje.objects.filter(_kjeden_q(linje.rot or linje))
    tid = naa or timezone.now()
    navn = getattr(bruker, 'username', '') or ''
    antall = 0
    for rad in kjeden:
        if rad.kilde == KILDE_SYSTEM:
            # Systemlinjer bærer ingen fritekst — de er bygget av verdimengder
            # som alt er ikke-identifiserende. Det er ingenting å fjerne, og
            # en inngang som nådde dem ville vært en vei til å fjerne sporet
            # etter en overstyring.
            continue
        rad.tekst = ''
        rad.fjernet_at = tid
        rad.fjernet_av = bruker if bruker and bruker.is_authenticated else None
        rad.fjernet_av_navn = navn
        rad.save(update_fields=['tekst', 'fjernet_at', 'fjernet_av',
                                'fjernet_av_navn'])
        antall += 1
    return antall


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


def _hendelsesdata(hendelse) -> dict:
    return {'hendelsesnummer': hendelse.hendelsesnummer, 'tittel': hendelse.tittel,
            'lokasjon': hendelse.lokasjon_navn}


@transaction.atomic
def opprett_hendelse(vakt, raa_tittel, *, bruker, lokasjon=None,
                     fra_linje=None) -> Hendelse:
    """Ny hendelse. Fra en logglinje eller fra ingenting.

    **Linja blir stående** (§4.5): hendelsen peker tilbake på den, og linja
    får hendelsen som sin — den er den første linja i hendelsens filter. Å
    flytte linja inn ville gitt loggen et hull akkurat der det viktige skjedde.
    """
    tittel = rens_tittel(raa_tittel)
    if fra_linje is not None and fra_linje.vakt_id != vakt.pk:
        raise Ugyldig('Linja hører til en annen vakt.')
    hendelse = Hendelse(
        vakt=vakt,
        hendelsesnummer=neste_hendelsesnummer(vakt),
        tittel=tittel,
        lokasjon=lokasjon,
        lokasjon_navn=getattr(lokasjon, 'navn', '') or '',
        opprettet_av=bruker if bruker and bruker.is_authenticated else None,
        opprettet_av_navn=getattr(bruker, 'username', '') or '',
        opprettet_fra_linje=fra_linje,
    )
    hendelse.save()
    if fra_linje is not None and fra_linje.hendelse_id is None:
        fra_linje.hendelse = hendelse
        fra_linje.save(update_fields=['hendelse'])
    systemlinje(vakt, _kode('HENDELSE_OPPRETTET'), _hendelsesdata(hendelse),
                bruker=bruker, hendelse=hendelse)
    return hendelse


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
                     lokasjon=None, sett_lokasjon=False) -> Hendelse:
    """Tittel og lokasjon. Ingen systemlinje: det er en feltendring, og
    `audit/` fører dem — regel 2 i `ko/systemlinjer.py`.

    `sett_lokasjon=True` med `lokasjon=None` tømmer lokasjonen; uten flagget
    rører kallet den ikke. Et nullbart felt trenger tre tilstander i kallet.
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
    if not endret:
        raise Ugyldig('Ingenting er endret.')
    hendelse.versjon += 1
    hendelse.save(update_fields=endret + ['versjon'])
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
    return oppdrag


def hendelser_for(vakt):
    """Alle hendelsene i vakta med tellingene tavla trenger, nyeste først.

    Én spørring for tellingene, ikke én per hendelse: lista følger med hver
    logg-poll, hvert 15. sekund fra hver operatør.
    """
    from oppdrag import choices
    qs = (Hendelse.objects.filter(vakt=vakt)
          .annotate(
              antall_oppdrag=models.Count('oppdrag', distinct=True),
              apne_oppdrag=models.Count(
                  'oppdrag', distinct=True,
                  filter=~Q(oppdrag__status=choices.TERMINAL)))
          .order_by('-hendelsesnummer'))
    return list(qs)
