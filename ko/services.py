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


# ── Ressursbildet (§3.1) ─────────────────────────────────────────────────────
#
# **KO eier ikke ressursene.** Tavla settes sammen av tre kilder, og denne
# modulen legger bare til den tredje. Retningen er `ko` → `vaktliste` og
# `ko` → `oppdrag`; ingen av dem kjenner `ko` (`ko/tests_avhengighet.py`).


def _fort_av_ko(ressurs) -> bool:
    """Fører KO statusen for denne ressursen?

    **Utledet av `Ressurs.enhet`, ikke av et flagg** (se `Ressursstatus` sin
    docstring). Er enheten satt, melder ressursen sin egen status gjennom
    oppdragsmodulen; er den `NULL`, finnes det ingen som kan melde, og da er
    det operatøren.
    """
    return ressurs.enhet_id is None


def sett_ressursstatus(ressurs, ny_status: str, *, bruker, naa=None):
    """Før en status på en ressurs som ikke stempler selv.

    Avviser en ressurs som **har** en enhet: den statusen eies av
    oppdragsmodulen, og to kilder til samme sannhet går i utakt første gang
    noe feiler halvveis. Feilen er en egen, navngitt en — svaret er ikke
    «ugyldig verdi», det er «denne bilen melder selv».

    Skriver en systemlinje i samme transaksjon som raden. Rekkefølgen er ikke
    likegyldig: linja *er* historikken (tabellen bærer bare nåtilstanden), så
    en status som lagres uten sin linje er en endring som aldri skjedde.
    """
    from .models import Ressursstatus
    from . import choices as ko_choices
    from . import systemlinjer

    if not ko_choices.er_gyldig(ny_status):
        raise Ugyldig(f'Ukjent status «{ny_status}».')
    if not _fort_av_ko(ressurs):
        raise Ugyldig(
            f'{ressurs.navn} er koblet til en enhet og melder sin egen status. '
            f'Før den i oppdragsmodulen.')

    naa = naa or timezone.now()
    vakt = ressurs.vaktliste.vakt
    with transaction.atomic():
        rad, _ = Ressursstatus.objects.update_or_create(
            ressurs=ressurs,
            defaults={
                'status': ny_status,
                'satt_at': naa,
                'satt_av': bruker,
                'satt_av_navn': getattr(bruker, 'username', '') or '',
            })
        systemlinje(
            vakt, systemlinjer.RESSURS_STATUS,
            {
                # Frosset: ressursen forsvinner med vaktlista si, linja står
                # i 730 dager.
                'ressurs': ressurs.navn,
                'gruppe': ressurs.gruppe.navn if ressurs.gruppe_id else '',
                'status': ny_status,
                'status_navn': ko_choices.STATUS_NAVN[ny_status],
            },
            tidspunkt=naa)
    return rad


def ressursbildet(naa=None) -> dict:
    """Tavla: hvem er på vakt, hvor står de, og hvem kan sendes.

    **En projeksjon, ikke et register.** Ingenting her lagres av KO utenom den
    tredje kilden; de to andre leses hos den som eier dem.

    Returnerer `{'vaktliste': ..., 'grupper': [...]}`, eller `vaktliste: None`
    når ingen liste er i drift og den aktive vakta ikke har noen. **Tomt er ikke det
    samme som ukoblet**, og de to skal ikke se like ut — samme skille
    `vaktliste.services.besetning()` gjør mellom «ingen på vakt» og «ikke
    koblet».
    """
    from django.db.models import Prefetch

    from vaktliste.models import Ressurs, Vaktpost
    from vaktliste.services import vaktliste_i_bruk
    from . import choices as ko_choices
    from .models import Ressursstatus

    naa = naa or timezone.now()
    liste = vaktliste_i_bruk()
    if liste is None:
        return {'vaktliste': None, 'grupper': []}

    # Skiftene som dekker **nå**, ikke hele døgnet. Samme spørsmål som
    # `besetning()` stiller: «er ressursen bemannet», ikke «hvem har vakt i
    # løpet av helga».
    naavaerende = (Vaktpost.objects
                   .filter(mannskap__isnull=False, fra_tid__lte=naa, til_tid__gte=naa)
                   .select_related('mannskap', 'rolle')
                   .order_by('mannskap__navn'))
    ressurser = (Ressurs.objects
                 .filter(vaktliste=liste)
                 .select_related('gruppe', 'korps', 'enhet', 'ko_status')
                 .prefetch_related(Prefetch('vaktposter', queryset=naavaerende,
                                            to_attr='naa_poster'))
                 .order_by('gruppe__rekkefolge', 'gruppe__navn',
                           'rekkefolge', 'navn'))

    # Statusen for dem som melder selv hentes i **én** spørring for alle
    # enhetene, ikke én per ressurs: tavla polles gjennom hele vakta, og en
    # N+1 her er 30 spørringer hvert tiende sekund.
    enhet_status = _enhetsstatuser([r.enhet_id for r in ressurser if r.enhet_id],
                                   liste.vakt)

    grupper: list[dict] = []
    for r in ressurser:
        rad = {
            'id': r.pk,
            'navn': r.navn,
            'korps': r.korps.kortnavn or r.korps.navn if r.korps_id else '',
            'fort_av_ko': _fort_av_ko(r),
            'mannskap': [{'navn': vp.mannskap.navn,
                          'rolle': vp.rolle.navn if vp.rolle_id else '',
                          'tilstede': vp.er_tilstede}
                         for vp in r.naa_poster],
        }
        rad['antall'] = len(rad['mannskap'])
        rad['tilstede'] = sum(1 for m in rad['mannskap'] if m['tilstede'])
        if rad['fort_av_ko']:
            ko_rad = getattr(r, 'ko_status', None)
            rad['status'] = ko_rad.status if ko_rad else ko_choices.STANDARD
            rad['status_navn'] = ko_choices.STATUS_NAVN[rad['status']]
            rad['status_satt_av'] = ko_rad.satt_av_navn if ko_rad else ''
            rad['status_satt_at'] = (ko_rad.satt_at.isoformat()
                                     if ko_rad else None)
        else:
            oppl = enhet_status.get(r.enhet_id) or {}
            rad['status'] = oppl.get('status', '')
            rad['status_navn'] = oppl.get('status_navn', '')
            rad['status_satt_av'] = ''
            rad['status_satt_at'] = None
            rad['antall_ventende'] = oppl.get('antall_ventende', 0)

        gruppenavn = r.gruppe.navn if r.gruppe_id else 'Uten gruppe'
        if not grupper or grupper[-1]['navn'] != gruppenavn:
            grupper.append({'navn': gruppenavn,
                            'ikon': r.gruppe.ikon if r.gruppe_id else '',
                            'ressurser': []})
        grupper[-1]['ressurser'].append(rad)

    return {
        'vaktliste': {'vakt_navn': liste.vakt.navn, 'i_drift': liste.i_drift},
        'grupper': grupper,
    }


def _enhetsstatuser(enhet_ider, vakt) -> dict:
    """`{enhet_id: {...}}` for dem som melder selv.

    Ligger i en egen funksjon fordi den er **den ene kanten mot
    oppdragsmodulen** i ressursbildet. Står den for seg, er den både lett å
    finne og lett å bytte ut den dagen pulje 4 flytter sentralbordet.
    """
    if not enhet_ider:
        return {}
    from oppdrag.models import Enhet
    from oppdrag.services import enhet_status

    ut = {}
    for enhet in Enhet.objects.filter(pk__in=set(enhet_ider)):
        oppl = enhet_status(enhet, vakt)
        ut[enhet.pk] = {'status': oppl['status'],
                        'status_navn': oppl['status_navn'],
                        'antall_ventende': oppl['antall_ventende']}
    return ut
