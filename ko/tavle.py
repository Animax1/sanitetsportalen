"""KO-tavla — hvor lagene står, og hvor de har vært (André, 22. sep. 2026).

Tavla på veggen i KO digitalt: lokasjonene som rader, tida som kolonner, og
lagene plassert i rutene. Skissene ble avtalt før koden (Artifact «KO-tavla —
skisser»); svarene står i `TODO.md` og CHANGELOG.

**Hva tavla eier, og hva den bare viser.** Den eier én ting: plasseringene
(`Tavleplassering`) — hvor en *ledig* ressurs står. Alt annet er projeksjon:

| Hva | Kilde |
|---|---|
| Hvem som er på vakt | Vaktlista — `ressurser_paa_vakt_naa` for lagene, `Ressurs.enhet` + `pa_vakt` for bilene |
| Hvem som er opptatt, og hvor | Hendelsene (`HendelseLag` på en åpen hendelse) og oppdragene (`enhet_status`) |
| Radene | Oppdragsmodulens lokasjoner, pluss den faste Pause-raden |
| Filteret | Vaktlistas ressursgrupper |

**Opptatt har forrang** (André: «hendelser og oppdrag tar prioritet»). En
ressurs på en hendelse eller et oppdrag kan ikke plasseres, og når laget går
på en hendelse, lukkes plasseringen. Tida på hendelsen skrives som en lukket
rad med `hendelse_nummer` når laget går av eller hendelsen lukkes — så
«Besøk» teller den — og laget står **uten plass**.

`ko` → `vaktliste` og `ko` → `oppdrag` er de tillatte retningene; ingen av
dem kjenner tavla.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

import json
from datetime import timedelta

from .models import HENDELSE_APEN, HendelseLag, PlanlagtPause, Tavleplassering
from .services import Ugyldig, systemlinje

#: Statusene der en bil er **opptatt** på et oppdrag. `Venter` (tildelt) er
#: ikke med: bilen står der den står til den rykker ut, og kan fortsatt
#: flyttes på tavla.
OPPTATT_STATUSER = frozenset({'rykker_ut', 'fremme', 'avreist', 'leverer', 'behandlet'})

#: Statusene der bilen hører hjemme **på oppdragets lokasjon** på tavla. Fra
#: Avreist er hun på vei bort med en pasient, og oppdragets lokasjon er ikke
#: lenger der hun er — da står hun blant de opptatte uten rad.
PAA_OPPDRAGETS_STED = frozenset({'rykker_ut', 'fremme', 'behandlet'})


def _navn(bruker) -> str:
    return getattr(bruker, 'username', '') or ''


def _bruker(bruker):
    return bruker if bruker is not None and getattr(bruker, 'is_authenticated', False) else None


# ── Hvem som er på tavla ──────────────────────────────────────────────────────

def ressurser_paa_tavla(naa=None, *, med_biler=True):
    """Ressursene tavla viser: lagene med et skift som dekker nå, og bilene som
    er på vakt. Samme regel som ressursoversikten — en ressurs man kan se der,
    skal man kunne se her.

    Bilene er vaktlistas ressurser **med** oppdragsenhet, og de er på vakt når
    enheten er det (`Enhet.pa_vakt`): «bilene styres ikke herfra; de skrus av
    og på av KO» (`vaktliste.services.ressurser_paa_vakt_naa`). En bil uten
    ressurs i vaktlista har ingen gruppe å filtrere på, og står ikke på tavla.
    """
    from django.db.models import Q

    from vaktliste.models import Ressurs
    from vaktliste.services import ressurser_paa_vakt_naa, vaktliste_i_bruk

    liste = vaktliste_i_bruk()
    if liste is None:
        return []
    utvalg = Q(pk__in=ressurser_paa_vakt_naa(liste, naa).values('pk'))
    if med_biler:
        utvalg |= Q(vaktliste=liste, enhet__isnull=False, enhet__pa_vakt=True,
                    enhet__er_aktiv=True)
    return list(Ressurs.objects.filter(utvalg)
                .select_related('gruppe', 'enhet')
                .order_by('gruppe__rekkefolge', 'gruppe__navn', 'rekkefolge', 'navn'))


def opptatt(ressurser, vakt) -> dict:
    """``{ressurs_id: {merke, tekst, lokasjon_id, fra}}`` for ressursene som er
    opptatt — på en åpen hendelse, eller på et oppdrag.

    **Utledet ved hver lesing, aldri lagret**: hendelsen og oppdraget er
    kildene, og en kopi her ville gått i utakt første gang noe feilet halvveis
    (samme regel som `oppdrag.services.enhet_status`).
    """
    from oppdrag.models import Statusmelding
    from oppdrag.services import enhet_status

    ut: dict = {}
    lag_ider = [r.pk for r in ressurser if r.enhet_id is None]
    for rad in (HendelseLag.objects
                .filter(ressurs_id__in=lag_ider, hendelse__vakt=vakt,
                        hendelse__status=HENDELSE_APEN)
                .select_related('hendelse')):
        h = rad.hendelse
        merke = f'På H{h.hendelsesnummer}'
        ut[rad.ressurs_id] = {
            'merke': merke,
            'tekst': ' · '.join(d for d in (merke, h.lokasjon_navn) if d),
            'lokasjon_id': h.lokasjon_id,
            'fra': rad.fra,
            'hendelse_id': h.pk,
        }
    # Bilene er med når de er blant `ressurser` — det er `ressurser_paa_tavla`
    # sin `med_biler` som bestemmer, ett sted.
    for r in ressurser:
        if r.enhet_id is None or r.pk in ut:
            continue
        info = enhet_status(r.enhet, vakt)
        kobling = info['koblingsrad']
        if kobling is None or info['status'] not in OPPTATT_STATUSER:
            continue
        o = info['aktivt_oppdrag']
        merke = f'O{o.oppdragsnummer} {info["status_navn"]}'
        # Fra da hun rykket ut, ikke fra siste status: det er da hun forlot
        # plassen på tavla.
        ut_melding = Statusmelding.objects.gjeldende_for_status(o, 'rykker_ut', oppdragsenhet=kobling)
        ut[r.pk] = {
            'merke': merke,
            'tekst': ' · '.join(d for d in (merke, getattr(o.lokasjon, 'navn', '')) if d),
            'lokasjon_id': o.lokasjon_id if info['status'] in PAA_OPPDRAGETS_STED else None,
            'fra': ut_melding.tidspunkt if ut_melding else kobling.updated_at,
            'oppdrag_id': o.pk,
        }
    return ut


def aapen(ressurs):
    """Plasseringen ressursen står på nå, eller ``None``."""
    return Tavleplassering.objects.filter(ressurs=ressurs, til__isnull=True).first()


# ── Å flytte ──────────────────────────────────────────────────────────────────

def _stedsnavn(plassering) -> str:
    if plassering is None:
        return ''
    return 'Pause' if plassering.pause else plassering.lokasjon_navn


@transaction.atomic
def plasser(vakt, ressurs, *, bruker, lokasjon=None, pause=False, naa=None) -> Tavleplassering:
    """Sett en **ledig** ressurs på en lokasjon, eller i pause, fra **nå**.

    Den forrige plasseringen lukkes i samme transaksjon — tavla får aldri et
    lag på to steder, og basen sier det samme (`en_aapen_tavleplassering_per_
    ressurs`). Til samme sted igjen er en feil og ikke en ny rad: ellers
    teller «Besøk» ett besøk som to.
    """
    naa = naa or timezone.now()
    if (lokasjon is None) == (not pause):
        raise Ugyldig('Velg én lokasjon, eller pause.')
    if lokasjon is not None and not lokasjon.er_aktiv:
        raise Ugyldig('Lokasjonen er ikke aktiv.')
    if ressurs.pk not in {r.pk for r in ressurser_paa_tavla(naa)}:
        raise Ugyldig(f'{ressurs.navn} er ikke på vakt nå.')
    if ressurs.pk in opptatt([ressurs], vakt):
        raise Ugyldig(f'{ressurs.navn} er på en hendelse eller et oppdrag, og kan ikke '
                      'plasseres før det er ferdig.')
    forrige = (Tavleplassering.objects.select_for_update()
               .filter(ressurs=ressurs, til__isnull=True).first())
    if forrige is not None and forrige.pause == pause and forrige.lokasjon_id == getattr(lokasjon, 'pk', None):
        raise Ugyldig(f'{ressurs.navn} står der alt.')
    if forrige is not None:
        forrige.til = naa
        forrige.save(update_fields=['til'])
    try:
        with transaction.atomic():
            ny = Tavleplassering.objects.create(
                vakt=vakt, ressurs=ressurs, ressurs_navn=ressurs.navn,
                lokasjon=lokasjon, lokasjon_navn=getattr(lokasjon, 'navn', '') or '',
                pause=pause, fra=naa, av=_bruker(bruker), av_navn=_navn(bruker))
    except IntegrityError:
        # En annen operatør flyttet det samme laget i samme øyeblikk.
        raise Ugyldig(f'{ressurs.navn} ble flyttet av noen andre. Prøv igjen.')
    _logg(vakt, ressurs.navn, til=_stedsnavn(ny), fra=_stedsnavn(forrige),
          naa=naa, bruker=bruker)
    return ny


@transaction.atomic
def avslutt(vakt, ressurs, *, bruker, naa=None) -> Tavleplassering:
    """Ta ressursen av tavla: plasseringen lukkes nå, og den står **uten
    plass**. Det er det «Uten plass»-kolonnen er når man drar et lag dit."""
    naa = naa or timezone.now()
    forrige = (Tavleplassering.objects.select_for_update()
               .filter(ressurs=ressurs, til__isnull=True).first())
    if forrige is None:
        raise Ugyldig(f'{ressurs.navn} står alt uten plass.')
    forrige.til = naa
    forrige.save(update_fields=['til'])
    _logg(vakt, ressurs.navn, til='', fra=_stedsnavn(forrige), naa=naa, bruker=bruker)
    return forrige


def _logg(vakt, navn, *, til, fra, naa, bruker):
    from . import systemlinjer
    systemlinje(vakt, systemlinjer.TAVLE_FLYTTET,
                {'ressurs': navn, 'til': til, 'fra': fra}, tidspunkt=naa, bruker=bruker)


# ── Hendelsene har forrang ────────────────────────────────────────────────────

def avslutt_for_hendelse(ressurs_id, naa) -> None:
    """Laget gikk på en hendelse: plasseringen lukkes, uten egen logglinje —
    «Lag 3 registrert på H14» står alt. Kalles fra `services.sett_lag`."""
    Tavleplassering.objects.filter(
        ressurs_id=ressurs_id, til__isnull=True).update(til=naa)


def skriv_hendelsestid(rad: HendelseLag, til) -> None:
    """Tida laget sto på hendelsen, som en lukket rad på tavla — så «Besøk»
    teller den, og tavla viser den som historikk. Kalles når laget går av
    hendelsen og når hendelsen lukkes. Uten lokasjon på hendelsen finnes ingen
    rad å skrive den i, og da skrives den ikke."""
    h = rad.hendelse
    if h.lokasjon_id is None or til is None:
        return
    # En hendelse som ble lukket, åpnet igjen og lukket på nytt har alt en
    # rad for første del. Den nye begynner der den forrige sluttet.
    fra = rad.fra
    tidligere = (Tavleplassering.objects
                 .filter(vakt=h.vakt, ressurs_id=rad.ressurs_id,
                         hendelse_nummer=h.hendelsesnummer, til__isnull=False)
                 .order_by('-til').first())
    if tidligere is not None and tidligere.til > fra:
        fra = tidligere.til
    if til <= fra:
        return
    Tavleplassering.objects.create(
        vakt=h.vakt, ressurs_id=rad.ressurs_id, ressurs_navn=rad.ressurs_navn,
        lokasjon_id=h.lokasjon_id, lokasjon_navn=h.lokasjon_navn,
        hendelse_nummer=h.hendelsesnummer, fra=fra, til=til,
        av=rad.av, av_navn=rad.av_navn)


# ── Retting (steg 2) ──────────────────────────────────────────────────────────

def _klokke(t) -> str:
    from .systemlinjer import klokkeslett
    return klokkeslett(t)


def _laas_ressursens(plassering):
    """Alle radene til samme ressurs i vakta, låst, i rekkefølge."""
    qs = Tavleplassering.objects.select_for_update().filter(vakt_id=plassering.vakt_id)
    if plassering.ressurs_id is None:
        return list(qs.filter(pk=plassering.pk))
    return list(qs.filter(ressurs_id=plassering.ressurs_id).order_by('fra', 'id'))


@transaction.atomic
def rett(plassering, *, fra, til=None, bruker, naa=None) -> Tavleplassering:
    """«Lag 3 var egentlig på Parkscene fra 20:00» (skisse 3).

    **Et skjema, ikke et dra i kanten**: et feildrag på en travel tavle skal
    ikke flytte historikken stille. Naboene tilpasses i samme lagring — den
    forrige kortes, den neste begynner senere — så laget aldri står to steder
    samtidig. **Men en nabo forsvinner aldri**: en retting som ville spist en
    hel plassering, eller gått inn i tida på en hendelse, er en feil. Den åpne
    plasseringen forblir åpen; «til» er da nå.
    """
    naa = naa or timezone.now()
    if plassering.hendelse_nummer:
        raise Ugyldig('Tida på en hendelse følger hendelsen, og rettes ikke på tavla.')
    rader = _laas_ressursens(plassering)
    plassering = next(r for r in rader if r.pk == plassering.pk)
    aapen_rad = plassering.til is None
    if aapen_rad:
        til = None
    elif til is None:
        raise Ugyldig('Oppgi når plasseringen sluttet.')
    if fra > naa or (til is not None and til > naa):
        raise Ugyldig('Tavla fører det som har skjedd — tida kan ikke være fram i tid.')
    if til is not None and til <= fra:
        raise Ugyldig('«Til» må være etter «fra».')
    i = rader.index(plassering)
    forrige = rader[i - 1] if i > 0 else None
    neste = rader[i + 1] if i + 1 < len(rader) else None
    endret = []
    if forrige is not None and forrige.til is not None and forrige.til > fra:
        if forrige.hendelse_nummer or fra <= forrige.fra:
            raise Ugyldig(f'Går inn i {_stedsnavn(forrige) or "forrige"} '
                          f'{_klokke(forrige.fra)}–{_klokke(forrige.til)}. Rett den først.')
        forrige.til = fra
        endret.append(forrige)
    if neste is not None and til is not None and neste.fra < til:
        if neste.hendelse_nummer or (neste.til is not None and til >= neste.til):
            raise Ugyldig(f'Går inn i {_stedsnavn(neste) or "neste"} fra '
                          f'{_klokke(neste.fra)}. Rett den først.')
        neste.fra = til
        endret.append(neste)
    if plassering.fra == fra and plassering.til == til:
        return plassering
    data = {'ressurs': plassering.ressurs_navn, 'sted': _stedsnavn(plassering),
            'fra_foer': _klokke(plassering.fra), 'til_foer': _klokke(plassering.til),
            'fra': _klokke(fra), 'til': _klokke(til)}
    for rad in endret:
        rad.save(update_fields=['fra', 'til'])
    plassering.fra, plassering.til = fra, til
    plassering.save(update_fields=['fra', 'til'])
    from . import systemlinjer
    systemlinje(plassering.vakt, systemlinjer.TAVLE_RETTET, data, tidspunkt=naa, bruker=bruker)
    return plassering


@transaction.atomic
def fjern(plassering, *, bruker, naa=None) -> None:
    """Fjern en plassering som aldri skjedde. Var den åpen, står laget uten
    plass. Tida på en hendelse fjernes ikke herfra."""
    naa = naa or timezone.now()
    if plassering.hendelse_nummer:
        raise Ugyldig('Tida på en hendelse følger hendelsen, og fjernes ikke fra tavla.')
    data = {'ressurs': plassering.ressurs_navn, 'sted': _stedsnavn(plassering),
            'fra_foer': _klokke(plassering.fra), 'til_foer': _klokke(plassering.til),
            'fjernet': True}
    vakt = plassering.vakt
    plassering.delete()
    from . import systemlinjer
    systemlinje(vakt, systemlinjer.TAVLE_RETTET, data, tidspunkt=naa, bruker=bruker)


# ── Planlagte pauser (steg 2) ─────────────────────────────────────────────────

#: En pause er ikke et skift. Lengre enn dette er nesten sikkert en
#: skrivefeil i klokkeslettet — 14:30–16:00 ment som 14:30–15:00.
MAKS_PAUSE = timedelta(hours=4)


@transaction.atomic
def planlegg_pause(vakt, ressurs, *, fra, til, bruker, naa=None, pause=None) -> PlanlagtPause:
    """Ny planlagt pause, eller `pause` endret. **Flytter ingen** — se
    `PlanlagtPause`."""
    naa = naa or timezone.now()
    if pause is not None and pause.startet_id:
        raise Ugyldig('Pausen er startet. Rett plasseringen i Pause-raden i stedet.')
    if pause is None and ressurs.pk not in {r.pk for r in ressurser_paa_tavla(naa)}:
        raise Ugyldig(f'{ressurs.navn} er ikke på vakt nå.')
    if til <= fra:
        raise Ugyldig('«Til» må være etter «fra».')
    if til - fra > MAKS_PAUSE:
        raise Ugyldig('En pause kan ikke være lengre enn fire timer.')
    if til <= naa:
        raise Ugyldig('Pausen er alt over — en plan gjelder det som kommer.')
    andre = (PlanlagtPause.objects.select_for_update()
             .filter(vakt=vakt, ressurs=ressurs, fra__lt=til, til__gt=fra))
    if pause is not None:
        andre = andre.exclude(pk=pause.pk)
    kollisjon = andre.first()
    if kollisjon is not None:
        raise Ugyldig(f'{ressurs.navn} har alt en pause {_klokke(kollisjon.fra)}–'
                      f'{_klokke(kollisjon.til)}.')
    if pause is None:
        return PlanlagtPause.objects.create(
            vakt=vakt, ressurs=ressurs, ressurs_navn=ressurs.navn, fra=fra, til=til,
            av=_bruker(bruker), av_navn=_navn(bruker))
    pause.fra, pause.til = fra, til
    pause.save(update_fields=['fra', 'til'])
    return pause


def slett_pause(pause) -> None:
    if pause.startet_id:
        raise Ugyldig('Pausen er startet, og står som en plassering i Pause-raden.')
    pause.delete()


@transaction.atomic
def start_pause(pause, *, bruker, naa=None) -> Tavleplassering:
    """«Pause nå»: laget går i Pause-raden, og planen peker på plasseringen.

    **Står laget alt i pause**, knyttes planen til den — KO dro det dit før
    hun så knappen, og det er samme pause.
    """
    naa = naa or timezone.now()
    pause = PlanlagtPause.objects.select_for_update().get(pk=pause.pk)
    if pause.startet_id:
        raise Ugyldig('Pausen er alt startet.')
    if pause.ressurs is None:
        raise Ugyldig('Ressursen finnes ikke lenger i vaktlista.')
    naavaerende = aapen(pause.ressurs)
    if naavaerende is not None and naavaerende.pause:
        plassering = naavaerende
    else:
        plassering = plasser(pause.vakt, pause.ressurs, bruker=bruker, pause=True, naa=naa)
    pause.startet = plassering
    pause.save(update_fields=['startet'])
    return plassering


# ── Innstillingene (steg 2) ───────────────────────────────────────────────────

#: Tidsvinduet og døgnstarten er portalinnstillinger (global admin, André:
#: «la oss kunne styre det selv som en admin innstilling fra 12 timer til 24»).
TIMER_NOKKEL = 'ko.tavle_timer'
TIMER_MIN = 12
TIMER_MAKS = 24
STANDARD_TIMER = 12

#: Døgnet «Besøk» teller per. En konsert kl. 01 hører til fredagen — som
#: tavla på veggen, 06–05.
DOGNSTART_NOKKEL = 'ko.tavle_dognstart'
STANDARD_DOGNSTART = '06:00'

#: Lokasjonene KO-lederen har tatt av tavla, og dem hun følger (★). KO eier
#: avkryssingene, ikke lokasjonene: to ID-lister i `AppSetting`, auditlogget
#: som alt annet et menneske har bestemt.
SKJULTE_NOKKEL = 'ko.tavle_skjulte'
FULGTE_NOKKEL = 'ko.tavle_fulgte'


def timer() -> int:
    """Tidsvinduet, klemt ved lesing — en verdi skrevet for hånd skal ikke gi
    en tavle på null timer."""
    from core.models import AppSetting
    try:
        verdi = int(AppSetting.get(TIMER_NOKKEL, STANDARD_TIMER))
    except (TypeError, ValueError):
        return STANDARD_TIMER
    return max(TIMER_MIN, min(TIMER_MAKS, verdi))


def gyldig_klokke(raa) -> str | None:
    """`HH:MM`, eller `None`."""
    try:
        t, m = str(raa).strip().split(':')
        t, m = int(t), int(m)
    except (TypeError, ValueError):
        return None
    if not (0 <= t <= 23 and 0 <= m <= 59):
        return None
    return f'{t:02d}:{m:02d}'


def dognstart() -> str:
    from core.models import AppSetting
    return gyldig_klokke(AppSetting.get(DOGNSTART_NOKKEL, STANDARD_DOGNSTART)) or STANDARD_DOGNSTART


def _idliste(nokkel) -> list[int]:
    from core.models import AppSetting
    try:
        raa = json.loads(AppSetting.get(nokkel, '[]'))
    except (TypeError, ValueError):
        return []
    return sorted({int(i) for i in raa if isinstance(i, int)}) if isinstance(raa, list) else []


def skjulte() -> list[int]:
    return _idliste(SKJULTE_NOKKEL)


def fulgte() -> list[int]:
    return _idliste(FULGTE_NOKKEL)


def lagre_oppsett(*, skjulte_ider, fulgte_ider) -> None:
    """Lagre avkryssingene. Ukjente lokasjoner avvises, ikke stille droppet:
    en liste som ikke ble lagret slik hun sendte den, er en innstilling hun
    tror hun har."""
    from core.models import AppSetting
    from oppdrag.models import Lokasjon

    ider = set()
    for liste in (skjulte_ider, fulgte_ider):
        if not isinstance(liste, list) or not all(isinstance(i, int) for i in liste):
            raise Ugyldig('Send lokasjonene som lister med tall.')
        ider |= set(liste)
    if Lokasjon.objects.filter(pk__in=ider).count() != len(ider):
        raise Ugyldig('Lista inneholder ukjente lokasjoner — hent den på nytt.')
    AppSetting.set(SKJULTE_NOKKEL, json.dumps(sorted(set(skjulte_ider))))
    AppSetting.set(FULGTE_NOKKEL, json.dumps(sorted(set(fulgte_ider))))


# ── Det klienten får ──────────────────────────────────────────────────────────


def _iso(t):
    return t.isoformat() if t else None


def tavle_data(vakt, naa=None, *, med_biler=True) -> dict:
    """Alt tavla trenger, i ett svar som polles.

    **Hele vaktas plasseringer følger med**, ikke bare vinduets: «Ikke vært på
    Parkscene» og «Besøk» teller hele vakta, og det er noen hundre rader.
    """
    from oppdrag.models import Lokasjon

    naa = naa or timezone.now()
    ressurser = ressurser_paa_tavla(naa, med_biler=med_biler)
    travle = opptatt(ressurser, vakt)
    grupper = {}
    for r in ressurser:
        if r.gruppe_id not in grupper:
            grupper[r.gruppe_id] = {'id': r.gruppe_id, 'navn': r.gruppe.navn,
                                    'ikon': r.gruppe.ikon or ''}
    plasseringer = list(Tavleplassering.objects.filter(vakt=vakt).order_by('fra', 'id'))
    ute = set(skjulte())
    return {
        'naa': naa.isoformat(),
        'timer': timer(),
        'dognstart': dognstart(),
        'vakt_start': _iso(vakt.startet),
        'fulgte': fulgte(),
        'rader': [{'id': l.pk, 'navn': l.navn}
                  for l in Lokasjon.objects.filter(er_aktiv=True).order_by('rekkefolge', 'navn')
                  if l.pk not in ute],
        'pauser': [{
            'id': q.pk,
            'ressurs_id': q.ressurs_id,
            'ressurs_navn': q.ressurs_navn,
            'fra': _iso(q.fra),
            'til': _iso(q.til),
            'startet': q.startet_id is not None,
            'av_navn': q.av_navn,
        } for q in PlanlagtPause.objects.filter(vakt=vakt).order_by('fra', 'id')],
        'grupper': list(grupper.values()),
        'ressurser': [{
            'id': r.pk,
            'navn': r.navn,
            'gruppe_id': r.gruppe_id,
            'bil': r.enhet_id is not None,
            'opptatt': ({k: (_iso(v) if k == 'fra' else v) for k, v in travle[r.pk].items()}
                        if r.pk in travle else None),
        } for r in ressurser],
        'plasseringer': [{
            'id': p.pk,
            'ressurs_id': p.ressurs_id,
            'ressurs_navn': p.ressurs_navn,
            'lokasjon_id': p.lokasjon_id,
            'lokasjon_navn': p.lokasjon_navn,
            'pause': p.pause,
            'hendelse_nummer': p.hendelse_nummer,
            'fra': _iso(p.fra),
            'til': _iso(p.til),
        } for p in plasseringer],
    }

