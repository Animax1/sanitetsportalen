"""Overnatting i vaktlista — hvem sover hvor, for brannsikkerhetens skyld
(André, 25. sep. 2026).

«Jeg vil ha en overnatting-del hvor vi registrerer hvilke mannskap som skal
sove der og hvor. Det må gå an å sette dette opp samt romnavn. Dens funksjon
er for brannsikkerhet.» Svarene som styrer konstruksjonen, samme dag:

- **Per natt**, ikke én plassering for hele vakta — på en flerdagsvakt sover
  ikke alle der alle netter, og lista skal være sann den natta alarmen går.
- **Bare mannskap fra registeret.** Ingen fritekstnavn: da ville regelen
  «én person, ett sted» ikke latt seg håndheve.
- **Tilgang:** lederen (`kan_lede`) setter opp rommene og brannrutinen;
  `skriv_full` plasserer alle, korps-føreren sitt eget korps
  (`kan_fore_korps`). **Alle med `les` ser alle rom og navn** — den som
  teller opp ved alarm trenger hele lista, ikke bare sitt korps. Telefonen
  følger korpsfilteret som ellers (`vis_telefon`).
- **Papiret er brannlista.** Opptelling på mobil står i TODO som en idé.

Egen fil og ikke i `services.py`, som `pauser.py`: overnattingen er én ting
med sine egne regler.

**Natta er en dato**: kvelden den begynner. Natt til lørdag er fredag — samme
regel som `_dagnokkel()`, at det som går over midnatt hører til dagen det
begynte. Et tidsrom per person (sover 02–08) kan ikke uttrykkes, og trengs
ikke for en brannliste.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import services
from .models import Overnatting, Overnattingsrom, Vaktpost

#: Natta, i lokal tid. Brukes til to ting: hvilke netter vakta har, og hvem som
#: står på et skift mens de andre sover («på vakt i natt»).
NATT_FRA = time(22, 0)
NATT_TIL = time(6, 0)

#: Tak på antall netter lista tilbyr. En vakt varer ikke i to måneder; et
#: spenn som gjør det, er en skrivefeil i årstallet, og da skal ikke fanen
#: tegne seksti dagsknapper.
MAKS_NETTER = 31

MAKS_BRANNRUTINE = 2000


class Ugyldig(ValueError):
    """Endringen lar seg ikke lagre. Meldingen går til brukeren."""


class Konflikt(Ugyldig):
    """Personen sover et annet sted en av nettene. `netter` bærer hvilke, så
    vinduet kan tilby å flytte henne i stedet for bare å si nei."""

    def __init__(self, melding, netter):
        super().__init__(melding)
        self.netter = netter


# ── Tilgangen ────────────────────────────────────────────────────────────────

def kan_sette_opp(user) -> bool:
    """Rom og brannrutine er oppsett, som ressursene: lederens."""
    return services.kan_lede(user)


def kan_plassere(user, mannskap) -> bool:
    """Å plassere er å føre personen: alle for `skriv_full`, eget korps for
    korps-føreren. Samme regel som mannskapsregisteret, ikke som skiftene —
    en seng har ingen reservasjon å sjekke."""
    return services.kan_fore_korps(user, mannskap.korps_id)


def vis_telefon(user):
    """Funksjon `mannskap -> bool`: får brukeren se telefonnummeret?

    Navnene ser alle — det er poenget med lista. Telefonen følger
    korpsfilteret som resten av modulen: en ren `les` skal ikke kunne lese ut
    alle korpsenes numre fra en brannliste (samme grunn som besetningen,
    13. sep. 2026). Regnes én gang, ikke per rad.
    """
    if services.ser_alle_korps(user):
        return lambda m: True
    korps = services.brukerens_korps(user)
    korps_id = korps.pk if korps else None
    return lambda m: korps_id is not None and m.korps_id == korps_id


# ── Nettene ──────────────────────────────────────────────────────────────────

def nattevindu(natt):
    """`(fra, til)` for natta som begynner kvelden `natt`, i lokal tid."""
    fra = timezone.make_aware(datetime.combine(natt, NATT_FRA))
    til = timezone.make_aware(datetime.combine(natt + timedelta(days=1), NATT_TIL))
    return fra, til


def netter_i_vakta(vaktliste) -> list:
    """Nettene vakta går over: de der `NATT_FRA`–`NATT_TIL` overlapper spennet.

    Fre. 18:00 – søn. 16:00 gir fredag og lørdag. En dagvakt gir ingen — fanen
    sier da at vakta må forlenges. **Uten planlagt slutt** er det bare natta
    vakta begynner i, fordi et spenn uten ende ellers ville tilbudt netter
    ingen har planlagt.
    """
    start = vaktliste.vakt.startet
    if start is None:
        return []
    slutt = vaktliste.planlagt_slutt
    lokal_start = timezone.localtime(start)
    if slutt is None or slutt <= start:
        natt = lokal_start.date()
        # Starter vakta 02:00, er det natta som begynte kvelden før.
        if lokal_start.time() < NATT_TIL:
            natt -= timedelta(days=1)
        return [natt]
    ut = []
    dag = lokal_start.date() - timedelta(days=1)
    siste = timezone.localtime(slutt).date()
    while dag <= siste and len(ut) < MAKS_NETTER:
        fra, til = nattevindu(dag)
        if fra < slutt and til > start:
            ut.append(dag)
        dag += timedelta(days=1)
    return ut


def netter(vaktliste) -> list:
    """Nettene fanen viser: vaktas, **og** de som alt har noen i seg.

    Kortes vakta ned etter at folk er plassert, skal de ikke forsvinne fra
    lista — da står de der ingen ser dem, og fjernes aldri.
    """
    brukt = (Overnatting.objects.filter(rom__vaktliste=vaktliste)
             .values_list('natt', flat=True).distinct())
    return sorted(set(netter_i_vakta(vaktliste)) | set(brukt))


# ── Rommene ──────────────────────────────────────────────────────────────────

def _tekst(data, felt, maks):
    return str(data.get(felt) or '').strip()[:maks]


def _kapasitet(raa):
    """Tomt er «ikke satt», ikke null — null senger er et rom ingen skal sove i,
    og da skal det ikke finnes på lista."""
    if raa in (None, ''):
        return None
    try:
        verdi = int(raa)
    except (TypeError, ValueError):
        raise Ugyldig('Kapasiteten må være et helt tall.') from None
    if not 1 <= verdi <= 500:
        raise Ugyldig('Kapasiteten må være mellom 1 og 500, eller stå tom.')
    return verdi


def lagre_rom(vaktliste, data, *, rom=None) -> Overnattingsrom:
    """Nytt rom, eller `rom` endret. Bare feltene i `data` røres ved endring."""
    ny = rom is None
    rom = rom or Overnattingsrom(vaktliste=vaktliste)
    if ny or 'navn' in data:
        navn = _tekst(data, 'navn', 80)
        if not navn:
            raise Ugyldig('Rommet må ha et navn.')
        rom.navn = navn
    if ny or 'plassering' in data:
        rom.plassering = _tekst(data, 'plassering', 120)
    if ny or 'merknad' in data:
        rom.merknad = _tekst(data, 'merknad', 200)
    if ny or 'kapasitet' in data:
        rom.kapasitet = _kapasitet(data.get('kapasitet'))
    if ny:
        siste = (Overnattingsrom.objects.filter(vaktliste=vaktliste)
                 .order_by('-rekkefolge').values_list('rekkefolge', flat=True).first())
        rom.rekkefolge = (siste or 0) + 10
    try:
        with transaction.atomic():
            rom.save()
    except IntegrityError:
        raise Ugyldig(f'Det finnes alt et rom som heter «{rom.navn}».') from None
    return rom


def slett_rom(rom) -> int:
    """Fjern rommet og plasseringene i det. Returnerer hvor mange som sto der."""
    antall = rom.overnattinger.count()
    rom.delete()
    return antall


# ── Plasseringene ────────────────────────────────────────────────────────────

def _natt(raa):
    from datetime import date
    try:
        return date.fromisoformat(str(raa))
    except (TypeError, ValueError):
        raise Ugyldig('Ugyldig natt.') from None


def plasser(rom, mannskap, netter_raa, *, flytt=False) -> list:
    """Legg `mannskap` i `rom` de gitte nettene. Returnerer radene.

    **Sover personen et annet sted en av nettene, kastes `Konflikt`** — med
    mindre `flytt` er satt, og da flyttes hun. Vinduet spør først: å flytte
    noen ut av et rom stille er å gjøre det andre rommets opptelling feil.

    Står hun alt i dette rommet, er det ingen endring. Og **en seng på en
    annen vakt flyttes aldri herfra** — den hører til en liste denne lederen
    ikke nødvendigvis ser.
    """
    if not mannskap.er_aktiv:
        raise Ugyldig(f'{mannskap.navn} er ikke aktiv i registeret.')
    if not isinstance(netter_raa, (list, tuple)) or not netter_raa:
        raise Ugyldig('Velg minst én natt.')
    lovlige = set(netter_i_vakta(rom.vaktliste))
    valgte = sorted({_natt(n) for n in netter_raa})
    for natt in valgte:
        if natt not in lovlige:
            raise Ugyldig(f'Vakta går ikke over natta fra {natt:%d.%m}.')

    with transaction.atomic():
        eksisterende = {
            o.natt: o for o in Overnatting.objects.select_for_update()
            .select_related('rom').filter(mannskap=mannskap, natt__in=valgte)}
        andre_vakter = [n for n, o in eksisterende.items()
                        if o.rom.vaktliste_id != rom.vaktliste_id]
        if andre_vakter:
            raise Ugyldig(f'{mannskap.navn} sover på en annen vakt natta fra '
                          f'{min(andre_vakter):%d.%m}.')
        andre_rom = sorted(n for n, o in eksisterende.items() if o.rom_id != rom.pk)
        if andre_rom and not flytt:
            o = eksisterende[andre_rom[0]]
            raise Konflikt(f'{mannskap.navn} sover i {o.rom.navn} natta fra '
                           f'{andre_rom[0]:%d.%m}.', [n.isoformat() for n in andre_rom])
        ut = []
        for natt in valgte:
            o = eksisterende.get(natt)
            if o is None:
                try:
                    with transaction.atomic():
                        o = Overnatting.objects.create(rom=rom, mannskap=mannskap, natt=natt)
                except IntegrityError:
                    # Noen andre plasserte henne i samme øyeblikk.
                    raise Ugyldig(f'{mannskap.navn} ble nettopp plassert et annet sted '
                                  f'natta fra {natt:%d.%m}. Last siden på nytt.') from None
            elif o.rom_id != rom.pk:
                o.rom = rom
                o.save(update_fields=['rom', 'updated_at'])
            ut.append(o)
    return ut


def fjern(overnatting) -> None:
    overnatting.delete()


# ── På vakt i natt ───────────────────────────────────────────────────────────

def paa_vakt(vaktliste, plasseringer) -> dict:
    """`{(mannskap_id, natt): [skift]}` for dem som står på et skift i natta.

    Den som kjører ambulansen 22–06 er ikke i rommet, og opptellingen skal si
    det: «4 i rommet, 1 på vakt» er noe annet enn «5 i rommet». **Avmeldte
    skift teller ikke** — hun kommer ikke, og sover altså der hun sover.
    Planen, ikke stemplene: lista skrives ut før natta.
    """
    if not plasseringer:
        return {}
    netter_brukt = {p.natt for p in plasseringer}
    personer = {p.mannskap_id for p in plasseringer}
    vinduer = {n: nattevindu(n) for n in netter_brukt}
    tidligst = min(fra for fra, _ in vinduer.values())
    senest = max(til for _, til in vinduer.values())
    skift = (Vaktpost.objects
             .filter(ressurs__vaktliste=vaktliste, mannskap_id__in=personer,
                     avmeldt_at__isnull=True, fra_tid__lt=senest, til_tid__gt=tidligst)
             .select_related('ressurs').order_by('fra_tid'))
    ut = {}
    for vp in skift:
        for natt, (fra, til) in vinduer.items():
            if vp.fra_tid < til and vp.til_tid > fra:
                ut.setdefault((vp.mannskap_id, natt), []).append(vp)
    return ut


# ── Serialiseringen ──────────────────────────────────────────────────────────

def rom_til_dict(rom) -> dict:
    return {
        'id': rom.pk,
        'navn': rom.navn,
        'plassering': rom.plassering,
        'kapasitet': rom.kapasitet,
        'merknad': rom.merknad,
        'rekkefolge': rom.rekkefolge,
    }


def _skift_til_dict(vp) -> dict:
    return {'ressurs': vp.ressurs.navn, 'fra': vp.fra_tid.isoformat(),
            'til': vp.til_tid.isoformat()}


def plassering_til_dict(o, skift=(), telefon=False) -> dict:
    m = o.mannskap
    return {
        'id': o.pk,
        'rom_id': o.rom_id,
        'mannskap_id': o.mannskap_id,
        'natt': o.natt.isoformat(),
        'navn': m.navn,
        'korps_id': m.korps_id,
        'korps_kort': m.korps.kortnavn or m.korps.navn,
        'telefon': m.telefon if telefon else '',
        'paa_vakt': [_skift_til_dict(vp) for vp in skift],
    }


def data_for(vaktliste, user) -> dict:
    """Alt fanen trenger, i ett. Står i vaktlistas hovedsvar, så det følger
    med i offline-kopien uten at service workeren må kjenne et nytt endepunkt
    — og det er i en brann uten nett den kopien trengs."""
    rom = list(Overnattingsrom.objects.filter(vaktliste=vaktliste))
    plasseringer = list(Overnatting.objects.filter(rom__vaktliste=vaktliste)
                        .select_related('mannskap', 'mannskap__korps'))
    vakt = paa_vakt(vaktliste, plasseringer)
    telefon = vis_telefon(user)
    plasseringer.sort(key=lambda o: (o.natt, o.mannskap.navn.lower()))
    return {
        'netter': [n.isoformat() for n in netter(vaktliste)],
        'netter_i_vakta': [n.isoformat() for n in netter_i_vakta(vaktliste)],
        'rom': [rom_til_dict(r) for r in rom],
        'plasseringer': [
            plassering_til_dict(o, vakt.get((o.mannskap_id, o.natt), ()), telefon(o.mannskap))
            for o in plasseringer],
        'brannrutine': vaktliste.brannrutine,
    }


# ── Fila på e-post ───────────────────────────────────────────────────────────

def brannliste(vaktliste) -> list:
    """Nettene med rommene med folkene — det fila bærer, som tekst.

    Tom liste når ingen er plassert: da skal fila ikke få en bolk som bare sier
    at den er tom. **Telefon er med**, som i resten av fila — den går til de
    faste mottakerne admin har satt, ikke til hvem som helst med `les`.
    """
    rom = list(Overnattingsrom.objects.filter(vaktliste=vaktliste))
    plasseringer = list(Overnatting.objects.filter(rom__vaktliste=vaktliste)
                        .select_related('mannskap', 'mannskap__korps'))
    if not plasseringer:
        return []
    vakt = paa_vakt(vaktliste, plasseringer)
    ut = []
    for natt in sorted({o.natt for o in plasseringer}):
        rombolker = []
        for r in rom:
            folk = sorted((o for o in plasseringer if o.natt == natt and o.rom_id == r.pk),
                          key=lambda o: o.mannskap.navn.lower())
            if not folk:
                continue
            rader = []
            for o in folk:
                skift = vakt.get((o.mannskap_id, natt), [])
                rader.append({
                    'navn': o.mannskap.navn,
                    'korps': o.mannskap.korps.kortnavn or o.mannskap.korps.navn,
                    'telefon': o.mannskap.telefon,
                    'paa_vakt': ', '.join(
                        f'{vp.ressurs.navn} {timezone.localtime(vp.fra_tid):%H:%M}–'
                        f'{timezone.localtime(vp.til_tid):%H:%M}' for vp in skift),
                })
            rombolker.append({'navn': r.navn, 'plassering': r.plassering,
                              'kapasitet': r.kapasitet, 'merknad': r.merknad,
                              'antall': len(rader),
                              'paa_vakt': sum(1 for x in rader if x['paa_vakt']),
                              'folk': rader})
            rombolker[-1]['inne'] = rombolker[-1]['antall'] - rombolker[-1]['paa_vakt']
        ut.append({'natt': natt.isoformat(), 'tittel': natt_tekst(natt), 'rom': rombolker,
                   'antall': sum(b['antall'] for b in rombolker),
                   'paa_vakt': sum(b['paa_vakt'] for b in rombolker),
                   'inne': sum(b['inne'] for b in rombolker)})
    return ut


UKEDAGER = ('mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag', 'lørdag', 'søndag')


def natt_tekst(natt) -> str:
    """«Natt til lørdag 13.09» — slik natta sies, med morgenens dato."""
    morgen = natt + timedelta(days=1)
    return f'Natt til {UKEDAGER[morgen.weekday()]} {morgen:%d.%m}'
