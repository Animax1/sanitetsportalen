"""Park-modulens regler — se `docs/FORSLAG_PARK.md`.

Viewene eier HTTP-en; her ligger det som avgjør noe: hvilken lenke som er
åpen, hvilke lag som kan velges, hva som forhåndsvelges, hva som er en gyldig
registrering, og hva som kan angres. Hver regel er en egen funksjon, så den lar
seg prøve uten en forespørsel.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from core.models import AppSetting, ModuleSettings
from core.sortering import Norsk
from core.vakt import hent_aktiv_vakt

from .models import Parklenke, Problemstilling, Registrering, SkjultSted, Utfall

ANTALL_MAKS = 99

#: Angrefristen (B11): fem minutter, styrt av admin på portalinnstillingene.
ANGREFRIST_NOKKEL = 'park_angrefrist_min'
ANGREFRIST_STANDARD = 5
ANGREFRIST_MIN = 1
ANGREFRIST_MAKS = 30

# RISIKOVALG(park-ko-posisjon): forhåndsvalg av sted fra KO-tavla viser, til
# alle med lenken, hvor KO har plassert hvert lag. Bryteren står på
# portalinnstillingene; av = bare lagets siste registrering. FORSLAG_PARK.md §4.7.
KO_POSISJON_NOKKEL = 'park_ko_posisjon'


class Ugyldig(Exception):
    """En registrering eller angring som ikke lar seg gjøre. Meldingen vises."""


# ── Innstillingene ───────────────────────────────────────────────────────────

def angrefrist_min() -> int:
    """Minutter laget kan angre. Klemt til [MIN, MAKS]; standard ved søppel."""
    try:
        verdi = int(str(AppSetting.get(ANGREFRIST_NOKKEL, ANGREFRIST_STANDARD)).strip())
    except (TypeError, ValueError):
        return ANGREFRIST_STANDARD
    return min(max(verdi, ANGREFRIST_MIN), ANGREFRIST_MAKS)


def ko_posisjon_paa() -> bool:
    """Skal forhåndsvalget bruke KO-tavla? **På** til noen slår den av."""
    raa = AppSetting.get(KO_POSISJON_NOKKEL, None)
    if raa is None:
        return True
    return str(raa).strip().lower() in ('1', 'true', 'ja', 'on')


# ── Lenken ───────────────────────────────────────────────────────────────────

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def lag_lenke(*, navn, aapen_fra, aapen_til, bruker=None, ip=None) -> tuple[Parklenke, str]:
    """Ny lenke. **Tokenet returneres én gang og lagres aldri** (§4.1).

    Logges her og ikke i et signal: det er en handling, ikke en feltendring
    (CLAUDE.md, «Audit-logging»). Hashen står ikke i auditraden — navnet og
    oppetiden gjør.
    """
    if not str(navn or '').strip():
        raise Ugyldig('Lenken må ha et navn — hvor den skal ligge.')
    if aapen_fra is None or aapen_til is None or aapen_til <= aapen_fra:
        raise Ugyldig('«Åpen til» må være etter «Åpen fra».')
    token = secrets.token_urlsafe(32)
    lenke = Parklenke.objects.create(
        navn=str(navn).strip()[:120], hemmelighet_hash=hash_token(token),
        aapen_fra=aapen_fra, aapen_til=aapen_til,
        opprettet_av=bruker if getattr(bruker, 'is_authenticated', False) else None,
        opprettet_av_navn=_navn(bruker))
    _audit(lenke, 'CREATE', 'lenke',
           f'{lenke.navn}, åpen {tid_tekst(aapen_fra)}–{tid_tekst(aapen_til)}', bruker, ip)
    return lenke, token


def fjern_lenke(lenke, *, bruker=None, ip=None, naa=None) -> None:
    """Lenken slutter å virke. Raden står — registreringene peker på den."""
    if lenke.fjernet_at is not None:
        return
    lenke.fjernet_at = naa or timezone.now()
    lenke.fjernet_av = bruker if getattr(bruker, 'is_authenticated', False) else None
    lenke.fjernet_av_navn = _navn(bruker)
    lenke.save(update_fields=['fjernet_at', 'fjernet_av', 'fjernet_av_navn'])
    _audit(lenke, 'UPDATE', 'fjernet', lenke.navn, bruker, ip)


def aapen_lenke(token, naa=None) -> Parklenke | None:
    """Lenken tokenet åpner, eller ``None``.

    ``None`` dekker alt med vilje — ukjent token, fjernet lenke, utenfor
    oppetiden, modulen slått av, ingen vakt åpen. Laget skal se samme svar
    uansett; forskjellen hjelper bare den som prøver seg (§4.2).
    """
    if not token or not isinstance(token, str) or len(token) > 200:
        return None
    naa = naa or timezone.now()
    lenke = (Parklenke.objects
             .filter(hemmelighet_hash=hash_token(token), fjernet_at__isnull=True,
                     aapen_fra__lte=naa, aapen_til__gt=naa)
             .first())
    if lenke is None:
        return None
    if 'park' not in ModuleSettings.get_enabled_slugs():
        return None
    if aapen_vakt() is None:
        return None
    return lenke


def aapen_vakt():
    """Vakta registreringene havner på, eller ``None`` når den er avsluttet."""
    vakt = hent_aktiv_vakt()
    return None if vakt.avsluttet is not None else vakt


# ── Lagene og verdimengdene ──────────────────────────────────────────────────

def lagene():
    """Ressursene laget kan velge seg selv blant (B4).

    Vaktlista som gjelder nå — samme regel som KOs tavle
    (`vaktliste_i_bruk`) — og bare grupper med rutingflagget (§3.4).
    """
    from vaktliste.models import Ressurs
    from vaktliste.services import vaktliste_i_bruk

    liste = vaktliste_i_bruk()
    if liste is None:
        return Ressurs.objects.none()
    return (Ressurs.objects
            .filter(vaktliste=liste, gruppe__registrerer_i_park=True, gruppe__er_aktiv=True)
            .select_related('gruppe')
            .order_by('gruppe__rekkefolge', Norsk('gruppe__navn'), 'rekkefolge', Norsk('navn')))


def steder():
    """Stedene i nedtrekket: oppdragsmodulens aktive lokasjoner (B10), minus
    dem `skriv_leder` har skjult for lagene (`SkjultSted`).

    **Den ene lista alt går gjennom** — nedtrekket, valideringen i
    `registrer()` og forhåndsvalget. Derfor blir et skjult sted heller ikke
    forhåndsvalgt fra KO-tavla, og en innsending som peker på det avvises.
    """
    from oppdrag.models import Lokasjon

    return Lokasjon.objects.filter(er_aktiv=True, park_skjult__isnull=True)


def alle_steder_med_synlighet() -> list[dict]:
    """Oppsettet på `/lag/`: hver aktive lokasjon, og om lagene ser den."""
    from oppdrag.models import Lokasjon

    return [{'id': lok.pk, 'navn': lok.navn, 'skjult': lok.skjult}
            for lok in Lokasjon.objects.filter(er_aktiv=True).annotate(
                skjult=models.Exists(SkjultSted.objects.filter(lokasjon=models.OuterRef('pk'))))]


def sett_skjult(lokasjon, skjult: bool, *, bruker=None, ip=None) -> bool:
    """Skjul eller vis ett sted for lagene. Returnerer om noe ble endret.

    Idempotent: to klikk på «Skjul» gir én rad og én auditrad.
    """
    if skjult:
        _, ny = SkjultSted.objects.get_or_create(lokasjon=lokasjon, defaults={
            'skjult_av': bruker if getattr(bruker, 'is_authenticated', False) else None,
            'skjult_av_navn': _navn(bruker)})
        endret = ny
    else:
        endret = SkjultSted.objects.filter(lokasjon=lokasjon).delete()[0] > 0
    if endret:
        _audit_rad('park_skjultsted', lokasjon.pk, 'skjult' if skjult else 'vist',
                   lokasjon.navn, bruker, ip)
    return endret


def problemstillinger():
    return Problemstilling.objects.filter(er_aktiv=True)


def utfall():
    return Utfall.objects.filter(er_aktiv=True)


# ── Forhåndsvalget (B19) ─────────────────────────────────────────────────────

def forhandsvalg(vakt, ressurs_id: int) -> dict:
    """Stedet nedtrekket skal stå på for dette laget: **det nyeste vinner**.

    To kilder, begge med **serverens** tid (§5.1): KOs åpne plassering
    (`fra`) og lagets siste registrering (`registrert_at`). Telefonens eget
    minne er ikke med her — telefonklokka kan stå hvor som helst, og en
    sammenligning med den ville gitt feil vinner i stillhet. Klienten bruker
    minnet bare når svaret er ``'ingen'``.

    Et sted som er deaktivert siden, er ingen kandidat. Står de to på samme
    tid, vinner registreringen: den er et faktum, plasseringen en beslutning.
    """
    aktive = set(steder().values_list('pk', flat=True))
    kandidater = []

    siste = (Registrering.objects
             .filter(vakt=vakt, ressurs_id=ressurs_id, slettet_at__isnull=True,
                     lokasjon__isnull=False)
             .order_by('-registrert_at', '-id')
             .values('lokasjon_id', 'registrert_at').first())
    if siste and siste['lokasjon_id'] in aktive:
        kandidater.append((siste['registrert_at'], 1, Registrering.FORHANDSVALG_REGISTRERING,
                           siste['lokasjon_id']))

    # RISIKOVALG(park-ko-posisjon): KO-kilden. Av på portalinnstillingene
    # fjerner den fra svaret uten at noe annet endres. FORSLAG_PARK.md §4.7.
    if ko_posisjon_paa():
        from core.ressursplassering import aapen_plassering

        ko = aapen_plassering(ressurs_id)
        if ko and ko.get('lokasjon_id') in aktive and ko.get('fra') is not None:
            kandidater.append((ko['fra'], 0, Registrering.FORHANDSVALG_KO, ko['lokasjon_id']))

    if not kandidater:
        return {'lokasjon_id': None, 'kilde': Registrering.FORHANDSVALG_INGEN, 'tid': None}
    tid, _, kilde, lokasjon_id = max(kandidater)
    return {'lokasjon_id': lokasjon_id, 'kilde': kilde, 'tid': tid}


# ── Registrering og angring ──────────────────────────────────────────────────

def _heltall(verdi, feltnavn):
    if isinstance(verdi, bool):
        raise Ugyldig(f'Ugyldig {feltnavn}.')
    try:
        return int(verdi)
    except (TypeError, ValueError):
        raise Ugyldig(f'Ugyldig {feltnavn}.') from None


def gyldig_nokkel(raa) -> str:
    """Idempotensnøkkelen som kanonisk UUID-streng, eller `Ugyldig`.

    Den er også angre-nøkkelen (§4.4), så den må være en ekte tilfeldig UUID
    fra klienten — ikke hva som helst.
    """
    try:
        return str(uuid.UUID(str(raa)))
    except (TypeError, ValueError, AttributeError):
        raise Ugyldig('Registreringen mangler nøkkel. Last siden på nytt.') from None


def registrer(lenke, vakt, data: dict) -> tuple[Registrering, bool]:
    """Lagre én registrering. ``(rad, ny)`` — ``ny`` er False ved gjentatt nøkkel.

    Alt valideres mot det siden selv tilbyr: laget mot `lagene()`, stedet mot
    `steder()`, verdiene mot de aktive radene. En ID som ikke står i nedtrekket
    er ikke en gyldig registrering, uansett hvor den kom fra.
    """
    nokkel = gyldig_nokkel(data.get('idempotency_key'))
    gammel = Registrering.objects.filter(lenke=lenke, idempotency_key=nokkel).first()
    if gammel is not None:
        return gammel, False

    ressurs = lagene().filter(pk=_heltall(data.get('lag'), 'lag')).first()
    if ressurs is None:
        raise Ugyldig('Laget finnes ikke på vaktlista. Last siden på nytt.')
    sted = steder().filter(pk=_heltall(data.get('sted'), 'sted')).first()
    if sted is None:
        raise Ugyldig('Stedet finnes ikke lenger. Velg et annet.')
    ps = problemstillinger().filter(pk=_heltall(data.get('problemstilling'), 'problemstilling')).first()
    if ps is None:
        raise Ugyldig('Velg en problemstilling.')
    utf = utfall().filter(pk=_heltall(data.get('utfall'), 'utfall')).first()
    if utf is None:
        raise Ugyldig('Velg et utfall.')
    antall = _heltall(data.get('antall', 1), 'antall')
    if not 1 <= antall <= ANTALL_MAKS:
        raise Ugyldig(f'Antall må være mellom 1 og {ANTALL_MAKS}.')

    kilde = data.get('forhandsvalg_kilde')
    if kilde not in dict(Registrering.FORHANDSVALG):
        kilde = Registrering.FORHANDSVALG_INGEN

    try:
        with transaction.atomic():
            rad = Registrering.objects.create(
                vakt=vakt, lenke=lenke, ressurs=ressurs, ressurs_navn=ressurs.navn,
                problemstilling=ps.navn, antall=antall, utfall=utf.navn,
                lokasjon=sted, lokasjon_navn=sted.navn, idempotency_key=nokkel,
                forhandsvalg_kilde=kilde,
                forhandsvalg_endret=data.get('forhandsvalg_endret') is True)
    except IntegrityError:
        # To like sendinger samtidig: den andre fant ingen rad over, men traff
        # den unike nøkkelen. Den første vant; svar med den.
        rad = Registrering.objects.filter(lenke=lenke, idempotency_key=nokkel).first()
        if rad is None:
            raise
        return rad, False
    Parklenke.objects.filter(pk=lenke.pk).update(sist_brukt_at=rad.registrert_at)
    return rad, True


def kan_angres(rad: Registrering, naa=None) -> bool:
    """Innenfor fristen, og ikke slettet av `skriv_leder` i mellomtiden."""
    naa = naa or timezone.now()
    return (rad.slettet_at is None
            and naa - rad.registrert_at <= timedelta(minutes=angrefrist_min()))


def angre(lenke, raa_nokkel, naa=None) -> None:
    """Slett raden helt (§4.4) — eller `Ugyldig`.

    Krever lenken **og** nøkkelen bare telefonen som sendte kjenner. Ukjent
    nøkkel og utløpt frist gir samme melding.
    """
    nokkel = gyldig_nokkel(raa_nokkel)
    rad = Registrering.objects.filter(lenke=lenke, idempotency_key=nokkel).first()
    if rad is None or not kan_angres(rad, naa):
        raise Ugyldig('Registreringen kan ikke angres lenger.')
    rad.delete()


# ── Sletting av feilregistreringer (B20) ─────────────────────────────────────

GRUNN_MAKS = 200


def _grunn(raa) -> str:
    grunn = str(raa or '').strip()
    if not grunn:
        raise Ugyldig('Skriv hvorfor registreringen slettes.')
    if len(grunn) > GRUNN_MAKS:
        raise Ugyldig(f'Grunnen er for lang (maks {GRUNN_MAKS} tegn).')
    return grunn


def slett_registrering(rad, *, bruker, grunn, ip=None, naa=None) -> None:
    """`skriv_leder` sletter én feilregistrering (B20).

    **Raden står**, merket slettet, og statistikken utelater den — en sletting
    som ikke synes, er en statistikk ingen kan etterprøve. Ikke rette: en
    sletting og en ny registrering fra laget er ærligere enn at noen andre
    skriver om det laget sa.
    """
    grunn = _grunn(grunn)
    if rad.slettet_at is not None:
        raise Ugyldig('Registreringen er allerede slettet.')
    rad.slettet_at = naa or timezone.now()
    rad.slettet_av = bruker if getattr(bruker, 'is_authenticated', False) else None
    rad.slettet_av_navn = _navn(bruker)
    rad.slettet_grunn = grunn
    rad.save(update_fields=['slettet_at', 'slettet_av', 'slettet_av_navn', 'slettet_grunn'])
    _audit_rad('park_registrering', rad.pk, 'slettet', grunn, bruker, ip)


def fra_lenke_etter(lenke, etter, vakt):
    """Registreringene en lenke har levert siden `etter`, på denne vakta —
    de som ikke alt er slettet. Det «slett alt fra lenken» treffer (§4.6)."""
    return Registrering.objects.filter(
        lenke=lenke, vakt=vakt, registrert_at__gte=etter, slettet_at__isnull=True)


def slett_fra_lenke(lenke, *, etter, vakt, bruker, grunn, ip=None, naa=None) -> int:
    """Opprydding etter en lekket lenke: alt den har levert siden `etter`.

    Samme merking som én og én, og **én** auditrad med antallet — hundre
    auditrader for én beslutning ville druknet det som skjedde.
    """
    grunn = _grunn(grunn)
    naa = naa or timezone.now()
    with transaction.atomic():
        antall = fra_lenke_etter(lenke, etter, vakt).update(
            slettet_at=naa,
            slettet_av=bruker if getattr(bruker, 'is_authenticated', False) else None,
            slettet_av_navn=_navn(bruker), slettet_grunn=grunn)
        _audit_rad('park_parklenke', lenke.pk, 'slettet_etter',
                   f'{antall} registrering(er) fra {tid_tekst(etter)}: {grunn}', bruker, ip)
    return antall


def antall_for_laget(vakt, ressurs_id) -> int:
    """Hvor mange registreringer laget har denne vakta — kvitteringens teller."""
    return Registrering.objects.filter(
        vakt=vakt, ressurs_id=ressurs_id, slettet_at__isnull=True).count()


def kvittering(rad: Registrering, vakt) -> dict:
    """Det laget får tilbake: det det sendte, pluss fristen og telleren.

    **Aldri andre registreringer** (§4.3) — heller ikke lagets egne.
    """
    return {
        'registrert_at': rad.registrert_at.isoformat(),
        'angre_til': (rad.registrert_at + timedelta(minutes=angrefrist_min())).isoformat(),
        'lag': rad.ressurs_navn,
        'antall': rad.antall,
        'problemstilling': rad.problemstilling,
        'sted': rad.lokasjon_navn,
        'utfall': rad.utfall,
        'antall_for_laget': antall_for_laget(vakt, rad.ressurs_id),
    }


# ── Hjelpere ─────────────────────────────────────────────────────────────────

def tid_tekst(t) -> str:
    return timezone.localtime(t).strftime('%d.%m.%Y %H:%M')


def _audit(lenke, handling, felt, tekst, bruker, ip) -> None:
    _audit_rad('park_parklenke', lenke.pk, felt, tekst, bruker, ip, handling=handling)


def _audit_rad(tabell, pk, felt, tekst, bruker, ip, *, handling='UPDATE') -> None:
    """En handling, ikke en feltendring — logges der den skjer (CLAUDE.md)."""
    from audit.models import AuditLog

    AuditLog.objects.create(
        table_name=tabell, record_id=pk, action=handling, field_name=felt,
        new_value=tekst,
        user=bruker if getattr(bruker, 'is_authenticated', False) else None, ip=ip)


def _navn(bruker) -> str:
    if bruker is None or not getattr(bruker, 'is_authenticated', False):
        return ''
    # Brukernavnet, som KO fryser på sine rader: visningsnavn endres.
    return (getattr(bruker, 'username', '') or '')[:150]


