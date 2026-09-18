"""Reglene for KO-loggen. Alt som skriver en linje går gjennom denne fila.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Viewene eier HTTP-en, signalene
eier løftet av systemhendelser, og **begge kaller hit** — en regel med to
lesere skrives én gang, ellers har loggen to sannheter om hva en gyldig linje
er.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import AppSetting
from core.vakt import hent_aktiv_vakt

from .models import KILDE_OPERATOR, KILDE_SYSTEM, Logglinje


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
                ansvarsomraade='', naa=None) -> Logglinje:
    """En menneskeskrevet linje. Den vanlige veien inn i loggen."""
    tekst = rens_tekst(raa_tekst)
    tid = vurder_tidspunkt(tidspunkt, naa)
    linje = Logglinje(
        vakt=vakt,
        kilde=KILDE_OPERATOR,
        tidspunkt=tid,
        tekst=tekst,
        ansvarsomraade=(ansvarsomraade or '').strip()[:40],
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


def systemlinje(vakt, kode, data, *, tidspunkt=None) -> Logglinje:
    """Skriv en løftet systemhendelse. Kalles bare fra `ko/signals.py`.

    Ingen forfatter fryses: linja er ikke ført av noen, den *skjedde*. Hvem
    som utløste den står i `systemdata` når det betyr noe — «ført av KO» på en
    status meldt av andre enn bilen selv (§3.1, §4.6).
    """
    from .systemlinjer import KODER

    if kode not in KODER:
        raise Ugyldig(f'Ukjent systemkode «{kode}».')
    return Logglinje.objects.create(
        vakt=vakt,
        kilde=KILDE_SYSTEM,
        systemkode=kode,
        systemdata=data or {},
        tidspunkt=tidspunkt or timezone.now(),
    )


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
    return antall


# ── Ressurslista (§7) ────────────────────────────────────────────────────────


def ressursbildet(vakt=None) -> list:
    """Enhetene, i nøyaktig samme form som sentralbordets egen liste.

    **Ikke en egen projeksjon.** Et tidligere forsøk (17. sep. 2026) bygget et
    eget bilde over `vaktliste.Ressurs` med en KO-ført status i fire verdier —
    «Ledig», «Opptatt», «Pause», «Ute av drift». Verdimengden var **funnet på**:
    `docs/FORSLAG_KO.md` §3.1 sier at KO skal føre status for dem som ikke
    stempler selv, men ikke med hvilke ord, og `/oppdrag/` har aldri hatt
    «Pause» eller «Ute av drift» (André, 18. sep. 2026: «Her har du tatt deg
    grove friheter utenfor rammene som er satt»).

    KO viser derfor det `/oppdrag/` viste: `oppdrag.Enhet` gjennom
    `oppdrag.services.enhetskort()`, med enhetsmodulens egne statuser. Den
    tredje kilden i §3.1 er utsatt til noen har bestemt hva den skal hete —
    se `TODO.md`.

    `ledig_siden_bulk()` spørres for hele lista i én runde: lista polles
    gjennom hele vakta, og ett oppslag per enhet ville vært N spørringer.
    """
    from django.db.models.functions import Lower

    from oppdrag.models import Enhet
    from oppdrag.services import enhetskort, ledig_siden_bulk

    vakt = vakt or hent_aktiv_vakt()
    # Samme spørring som `oppdrag.views.enheter_view`: pensjonerte enheter er
    # ute, og `Lower` fordi «alfabetisk» ellers er databasens alfabet — SQLite
    # og PostgreSQL svarer ulikt.
    enheter = list(Enhet.objects
                   .select_related('user', 'enhetstype')
                   .filter(er_aktiv=True)
                   .order_by(Lower('navn')))
    ledig = ledig_siden_bulk(enheter, vakt)
    return [enhetskort(e, vakt, ledig.get(e.pk)) for e in enheter]
