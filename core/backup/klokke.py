"""Klokka som utløser automatisk backup — en tråd, ikke en cron-tjeneste.

Erstatter `patients/backup_scheduler.py` (13. sep. 2026).

## Hvorfor ikke en cron-tjeneste

Det nærliggende svaret på «hva utløser backup?» er en Railway Cron-tjeneste,
slik `purge_old_logs` og `kollaps_arkiv` er satt opp. Det virker ikke her, og
grunnen er volumet:

**Et Railway-volum kan bare henge på én tjeneste.** `/data` henger på
web-tjenesten, og det er dit `BACKUP_DIR` peker. En cron-tjeneste som kjørte
backup ville serialisert riktig, skrevet `.json.gz`-fila til sitt eget
flyktige containerfilsystem, opprettet `Backup`-raden i databasen, og
forsvunnet med fila da containeren avsluttet. Raden ville blitt stående og
påstått at det finnes en backup.

Og det er verre enn en tom påstand: `core.arkiv.har_backup_etter()` — sperra
som skal hindre at et arkiv kollapser uten at slettingen er gjenopprettbar —
spør bare etter raden, ikke etter fila. En cron-tjeneste uten volum ville
altså produsert spøkelsesbackuper som **åpner kollapssperra**, og kollaps er
den ene operasjonen i portalen som ikke kan gjøres om.

De to jobbene som faktisk står i Railway rører bare databasen. De skriver
ingen filer, og trenger derfor ikke volumet. Det er hele forskjellen.

Klokka ligger derfor i prosessen som eier volumet. `backup_kjor`-kommandoen
finnes fortsatt som manuell inngang, og middlewaren er beholdt som reservenett
— begge går gjennom `kjor_forfalte()` her, så det finnes én oppførsel og ikke
tre.

## Hvordan vi vet at den lever

En cron-tjeneste er synlig i Railways grensesnitt; en tråd er ikke synlig noe
sted. Svaret er at dataene sier det selv: `sist_sjekket_at` settes hver gang en
plan faktisk vurderes, og `vakthund()` melder fra når en plan ikke er vurdert på
tre ganger intervallet. Tre ganger, ikke én, fordi en deploy eller en restart
legitimt hopper over et tikk eller to.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from datetime import timedelta

from django.db import OperationalError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Hvor ofte tråden våkner. Dette er ikke backup-intervallet — det ligger i
#: `Backupplan` — men det er oppløsningen: en plan satt til 3 minutter kjører
#: reelt hvert 3. minutt bare fordi tikken er tettere enn den.
TIKK_SEKUNDER = 60

#: Maks tilfeldig forsinkelse før tråden begynner å tikke. Med flere
#: gunicorn-arbeidere får hver sin tråd, og radlåsen avgjør uansett hvem som
#: får kjøre — men uten spredning banker de på samme sekund hvert minutt.
JITTER_SEKUNDER = 30

#: En fil uten `Backup`-rad som er eldre enn dette, er en rest etter en
#: prosess som ble drept midt i en skriving. Ryddes ved oppstart.
FORELDRELOS_ALDER_SEK = 3600

#: Hvor mange ganger intervallet en plan kan stå uvurdert før vakthunden slår.
VAKTHUND_FAKTOR = 3

_startet = False
_start_las = threading.Lock()

# Middlewaren kaller inn ved hver forespørsel; throttle så databasen ikke
# spørres oftere enn tråden ville gjort det.
_siste_sjekk_ts = 0.0
_sjekk_las = threading.Lock()
_kjorer = False
_kjorer_las = threading.Lock()


# ── Hva som er forfalt ───────────────────────────────────────────────────────

def forfalt(plan) -> bool:
    """Skal denne planen kjøre nå?

    Leser modus og intervall gjennom `gjeldende()`, så en modul som følger
    standardplanen vurderes mot standardens tall. Tidsstempelet er alltid
    planens eget — når den sist ble vurdert er ikke noe man arver.

    **Målt mot `sist_sjekket_at`, ikke `sist_fil_at`.** I modus «ved endring»
    er det normale utfallet at innholdet står stille og ingen fil skrives.
    Målte vi mot siste fil, ville planen vært forfalt ved hvert eneste tikk
    etter det — altså serialisert hele modulen hvert minutt for å bekrefte
    stillstand, i stedet for hvert intervall. Intervallet sier hvor ofte vi
    *ser etter*, ikke hvor ofte vi lykkes.
    """
    from core.models import Backupplan

    if plan.modus_effektiv == Backupplan.MODUS_AV:
        return False
    if plan.sist_sjekket_at is None:
        return True
    return timezone.now() - plan.sist_sjekket_at >= timedelta(
        minutes=plan.intervall_min_effektiv)


def planer():
    """``(slug, plan)`` for hver registrerte handler, rad opprettet ved behov.

    **Registeret er fasit, ikke tabellen.** Leste vi plantabellen direkte,
    ville en modul uten rad vært usynlig for klokka til noen tilfeldigvis åpnet
    adminsiden — og for et arkiv betyr manglende backup at kollapsen nekter å
    kjøre, altså en feil som først viser seg to år senere. Planrader uten
    handler hoppes over: de er rester etter en modul som er tatt ut av koden,
    og skal ikke holde liv i en backup ingen kan gjenopprette.
    """
    from core.backup import all_handlers
    from core.models import Backupplan

    kjente = {p.slug: p for p in Backupplan.objects.all()}
    ut = []
    for handler in all_handlers():
        plan = kjente.get(handler.slug) or Backupplan.hent(handler.slug)
        ut.append((handler.slug, plan))
    return ut


# ── Kjøring ──────────────────────────────────────────────────────────────────

def kjor_plan(slug: str, *, tving: bool = False) -> bool:
    """Kjør backup for én plan, med radlås mot andre arbeidere.

    Låsen tas med `nowait`, og `sist_sjekket_at` settes **før** selve backupen,
    så en arbeider som kommer like etter ser det oppdaterte tidspunktet og
    hopper over. Får vi ikke låsen, gjør en annen prosess jobben akkurat nå.

    Returnerer True hvis det ble skrevet en fil.
    """
    from core.backup import KIND_AUTO, create_backup, enforce_cap, get_handler
    from core.models import Backupplan

    if get_handler(slug) is None:
        logger.debug('backup-klokka: ingen handler for %s, hopper over', slug)
        return False

    try:
        with transaction.atomic():
            try:
                plan = (Backupplan.objects
                        .select_for_update(nowait=True)
                        .get(slug=slug))
            except OperationalError:
                logger.debug('backup-klokka: låst av en annen, hopper over %s', slug)
                return False
            except Backupplan.DoesNotExist:
                return False

            if not tving and not forfalt(plan):
                return False

            # Reserver plassen før arbeidet: en arbeider som kommer like
            # etter ser det oppdaterte tidspunktet og lar denne runden være.
            na = timezone.now()
            plan.sist_sjekket_at = na
            plan.save(update_fields=['sist_sjekket_at'])

            # «Alltid» slår av hash-skippet: en fil hvert intervall, også når
            # innholdet står stille, fordi det er selve pulsen man er ute etter.
            backup = create_backup(
                slug=slug, kind=KIND_AUTO, note='Automatisk (klokka)',
                hopp_over_like=not plan.skriver_alltid,
            )
            slettet = enforce_cap(slug, plan.behold_effektiv)

            if backup is None:
                # Innholdet var identisk med forrige fil. `sist_fil_at` blir
                # stående der den var — den skal si når vi sist *fikk* noe,
                # ikke når vi sist så etter. Det er nettopp de to spørsmålene
                # som ikke lot seg skille før 13. sep. 2026.
                plan.sist_resultat = 'uendret'
                plan.save(update_fields=['sist_resultat'])
                logger.info('backup-klokka[%s]: uendret. Slettet %d gamle.',
                            slug, slettet)
                return False

            plan.sist_fil_at = na
            plan.sist_resultat = 'ny'
            plan.save(update_fields=['sist_fil_at', 'sist_resultat'])
            logger.info('backup-klokka[%s]: %s (%d bytes). Slettet %d gamle.',
                        slug, backup.filename, backup.size_bytes, slettet)
            return True
    except Exception as exc:   # noqa: BLE001 — en feil her skal aldri ta ned appen
        logger.exception('backup-klokka[%s]: feil under automatisk backup', slug)
        _skriv_feil(slug, exc)
        return False


def _skriv_feil(slug: str, exc: Exception) -> None:
    """Legg feilen på planraden. Skal aldri kaste — den kalles fra en
    except-blokk, og en feil her ville skjult den egentlige."""
    from core.models import Backupplan
    try:
        Backupplan.objects.filter(slug=slug).update(
            sist_resultat=f'feil: {exc.__class__.__name__}: {exc}'[:200])
    except Exception:   # noqa: BLE001
        logger.exception('backup-klokka: kunne ikke skrive feilen for %s', slug)


def kjor_forfalte() -> int:
    """Ett tikk: kjør planene som er forfalt. Returnerer antall skrevne filer.

    Et tikk der ingenting er forfalt koster én spørring — planradene — og
    ingen skriving. Det er derfor tikken kan være tett (60 sekunder) uten at
    intervallene trenger å være det.
    """
    skrevet = 0
    for slug, plan in planer():
        if forfalt(plan):
            skrevet += 1 if kjor_plan(slug) else 0
    return skrevet


# ── Vakthund ─────────────────────────────────────────────────────────────────

def vakthund(*, krev_tidligere_kjoring: bool = False) -> list[dict]:
    """Planer som ikke er vurdert på `VAKTHUND_FAKTOR` ganger intervallet.

    Dette er hele svaret på at en tråd ikke er synlig noe sted: er lista tom,
    lever klokka. Planer i modus «av» er ikke med — de skal ikke vurderes, og
    et varsel om dem ville vært støy. Tre ganger intervallet, ikke én, fordi en
    deploy eller en restart legitimt hopper over et tikk eller to.

    ``krev_tidligere_kjoring`` utelater planer som aldri er vurdert. Visningen
    vil ha dem med — «aldri» er verdt å se — men et *varsel* om dem ville
    fyrt ved hver eneste førstegangsoppstart, før klokka rakk sitt første
    tikk. «Har aldri kjørt» og «har sluttet å kjøre» er to forskjellige
    tilstander, og bare den andre er en feil.
    """
    from core.models import Backupplan

    na = timezone.now()
    ut = []
    for plan in Backupplan.objects.all():
        if plan.slug == Backupplan.STANDARD_SLUG:
            continue
        if plan.modus_effektiv == Backupplan.MODUS_AV:
            continue
        if plan.sist_sjekket_at is None and krev_tidligere_kjoring:
            continue
        grense = timedelta(minutes=plan.intervall_min_effektiv * VAKTHUND_FAKTOR)
        if plan.sist_sjekket_at is None or na - plan.sist_sjekket_at > grense:
            ut.append({
                'slug': plan.slug,
                'sist_sjekket_at': plan.sist_sjekket_at,
                'grense_min': int(grense.total_seconds() // 60),
            })
    return ut


def varsle_stoppet_klokke() -> int:
    """Varsle global admin om at klokketråden har sluttet å tikke.

    **Dette kan bare kalles fra reservenettet, ikke fra tråden selv.** Et
    varsel om at klokka er død, sendt av klokka, er et varsel som aldri kommer.
    Reservenettet i middlewaren kjører i en forespørsel, altså i live — og
    oppdager derfor nettopp det tråden ikke kan melde om seg selv.

    `notify()` dedupliserer mot siste døgn, så et stoppet tikk gir ett varsel,
    ikke ett per forespørsel. Returnerer antall varsler som ble opprettet.
    """
    from django.contrib.auth import get_user_model

    from core.notifications import notify

    forsinket = vakthund(krev_tidligere_kjoring=True)
    if not forsinket:
        return 0

    slugger = ', '.join(r['slug'] for r in forsinket)
    antall = 0
    try:
        for bruker in get_user_model().objects.filter(role='admin', is_active=True):
            if notify(
                bruker,
                module_slug='core',
                kind='backup_klokke_stoppet',
                title='Backup-klokka har stoppet',
                message=(f'Disse planene er ikke vurdert på lenge: {slugger}. '
                         'Backup tas nå av reservenettet i stedet, som bare '
                         'virker så lenge portalen får trafikk.'),
                url='/portal-admin/backup/',
                level='critical',
            ) is not None:
                antall += 1
    except Exception:   # noqa: BLE001 — et varsel som feiler skal ikke stoppe backupen
        logger.exception('backup-klokka: kunne ikke varsle om stoppet klokke')
    return antall


# ── Opprydding ───────────────────────────────────────────────────────────────

def rydd_foreldrelose() -> int:
    """Slett backupfiler uten `Backup`-rad som er eldre enn en time.

    `create_backup` skriver fila først og raden etterpå. Blir prosessen drept
    imellom — en deploy midt i en skriving — ligger det igjen en halv fil som
    ingen kommer til å lese. Aldersgrensen finnes for at en skriving som pågår
    akkurat nå ikke skal ryddes bort under føttene på seg selv.
    """
    from core.backup import get_backup_dir
    from patients.models import Backup

    try:
        mappe = get_backup_dir()
        kjente = set(Backup.objects.values_list('filename', flat=True))
        grense = time.time() - FORELDRELOS_ALDER_SEK
        slettet = 0
        for sti in mappe.iterdir():
            if not sti.is_file() or sti.name in kjente:
                continue
            if not sti.name.startswith('backup-'):
                continue
            if sti.stat().st_mtime > grense:
                continue
            sti.unlink()
            slettet += 1
            logger.info('backup-klokka: ryddet foreldreløs fil %s', sti.name)
        return slettet
    except Exception:   # noqa: BLE001 — opprydding skal aldri hindre oppstart
        logger.exception('backup-klokka: opprydding feilet')
        return 0


# ── Tråden ───────────────────────────────────────────────────────────────────

def _lokke() -> None:
    time.sleep(random.uniform(0, JITTER_SEKUNDER))
    rydd_foreldrelose()
    while True:
        try:
            kjor_forfalte()
        except Exception:   # noqa: BLE001 — tråden skal aldri dø
            logger.exception('backup-klokka: feil i tikk')
        time.sleep(TIKK_SEKUNDER)


def skal_starte() -> bool:
    """Om klokka skal starte i denne prosessen.

    **Tillatelsesliste, ikke blokkliste.** Første utkast listet opp
    kommandoene klokka *ikke* skulle starte under, og `manage.py check` startet
    den allerede dagen den ble skrevet. Med en blokkliste er hver nye
    management-kommando en ny sjanse til å etterlate seg en tråd som skriver
    backupfiler fra en engangsprosess.

    Klokka skal kjøre i den prosessen som serverer portalen, og bare der:
    gunicorn i prod, `runserver` lokalt. Alt annet — test, `migrate`,
    `collectstatic`, `shell`, `backup_kjor` selv — er engangsprosesser.
    """
    import sys

    from django.conf import settings

    if getattr(settings, 'BACKUP_KLOKKE_AV', False):
        return False
    if os.environ.get('BACKUP_KLOKKE') == 'av':
        return False

    argv = sys.argv
    if not argv:
        return False

    # `runserver` starter seg selv på nytt i en underprosess; bare den har
    # RUN_MAIN satt. Uten sjekken får utviklingsserveren to tråder.
    if len(argv) > 1 and argv[1] == 'runserver':
        return os.environ.get('RUN_MAIN') == 'true'

    # Kjørt av en WSGI/ASGI-server: da er argv[0] serveren, ikke manage.py.
    navn = os.path.basename(argv[0])
    return navn in {'gunicorn', 'uvicorn', 'daphne'}


def start_klokke() -> bool:
    """Start klokketråden én gang per prosess. Returnerer True hvis den startet.

    Kalles fra `CoreConfig.ready()`. Med flere gunicorn-arbeidere får hver sin
    tråd; radlåsen i `kjor_plan` avgjør hvem som faktisk skriver.
    """
    global _startet
    if not skal_starte():
        return False
    with _start_las:
        if _startet:
            return False
        _startet = True
    threading.Thread(target=_lokke, name='backup-klokka', daemon=True).start()
    logger.info('backup-klokka: startet (tikk hvert %d. sekund)', TIKK_SEKUNDER)
    return True


# ── Reservenettet: middlewaren ───────────────────────────────────────────────

def kanskje_kjor() -> None:
    """Kalles fra middlewaren etter hver forespørsel.

    Beholdt som reservenett for det tilfellet at tråden ikke kom opp — en
    feilet `ready()`, en kjøremåte vi ikke har tenkt på. Går gjennom den samme
    `kjor_forfalte()`, så oppførselen er identisk; det eneste den legger til er
    en throttle, slik at trafikk ikke spør databasen oftere enn tråden ville.
    """
    global _siste_sjekk_ts, _kjorer

    na = time.monotonic()
    with _sjekk_las:
        if na - _siste_sjekk_ts < TIKK_SEKUNDER:
            return
        _siste_sjekk_ts = na

    with _kjorer_las:
        if _kjorer:
            return
        _kjorer = True

    def _arbeid():
        global _kjorer
        try:
            # Kommer vi hit og noe er forsinket, tikker ikke tråden. Varselet
            # må sendes før vi retter opp, ellers forsvinner beviset.
            varsle_stoppet_klokke()
            kjor_forfalte()
        except Exception:   # noqa: BLE001
            logger.exception('backup-klokka: feil i reservenettet')
        finally:
            with _kjorer_las:
                _kjorer = False

    threading.Thread(target=_arbeid, daemon=True).start()
