"""Backupene ut av Railway — til Scaleway Object Storage (13. sep. 2026).

Det som skal overleve at Railway faller, er dataene. `core.backup` skriver
per-modul-filer til volumet; dette modulen laster hver ny fil opp til en
S3-bucket i Amsterdam, **kryptert før den forlater Railway** — pasientfilene
er helseopplysninger, og Scaleways egen kryptering (SSE) beskytter bare mot
at noen leser diskene hos dem, ikke mot en lekket bucket-nøkkel.

Tre regler:

- **Frekvens = når noe har endret seg.** Opplastingen henger på at
  `create_backup` faktisk skrev en ny fil (hash-skip gjør at en kjøring uten
  endringer ikke skriver noe). Ingen egen klokke, ingen egen cron.
- **Kaster aldri.** En bucket som ikke svarer skal ikke stoppe backupen på
  volumet, som er det første sikkerhetsnettet. Feilen skrives i
  `OffsiteKopi.feil` og logges; oversikten på /portal-admin/backup/ viser den.
- **Inert uten variablene.** Uten `OFFSITE_S3_BUCKET` og `OFFSITE_BACKUP_KEY`
  gjør `meld_ny_backup` ingenting — staging og lokal utvikling har ingen
  offsite-backup, med vilje.

Fila komprimeres før den krypteres — chiffertekst lar seg ikke komprimere, mens
gzip på dumpdata-JSON gir 5–15 % av rå størrelse.

Kryptering: AES-256-GCM med nøkkel avledet av `OFFSITE_BACKUP_KEY` (SHA-256).
Formatet er `SPBK2` + 12 byte nonce + chiffertekst med tag, og **objektnavnet
er autentisert sammen med innholdet** (29. sep. 2026). Nøkkelen må finnes
*utenfor* Railway også (passordbehandler): uten den er bucketen uleselig, og
det er hele poenget.

**Hvorfor navnet må være med** (sikkerhetsgjennomgangen 28. sep. 2026): i
`SPBK1` var den autentiserte tilleggsdataen bare `SPBK1`. Den som hadde
skrivenøkkelen til bucketen — men ikke `OFFSITE_BACKUP_KEY` — kunne kopiere en
gammel hel dump til `backups/backup-patients-…`, og den dekrypterte feilfritt.
Med navnet i tilleggsdataen avvises en fil som er flyttet.

**`SPBK1` leses fortsatt**, fordi filene ligger 730 dager, og kan dermed
fortsatt gis nytt navn. Det egentlige vernet er derfor sperrene i
`core.backup.service.restore_backup` — en modulfil laster bare modulens
modeller, og en «hel database» må ha brukere — mens `SPBK2` gjør at nye filer
ikke engang kommer så langt.

Gjenoppretting: `python manage.py hent_offsite --list` og
`python manage.py hent_offsite <objektnavn>` henter, dekrypterer og legger
fila der `restore_backup` finner den, med en `Backup`-rad.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from core.vask import vask

logger = logging.getLogger(__name__)

MAGI = b'SPBK2'
#: Formatet fra 13. til 29. sep. 2026. Leses, skrives aldri. Se modulens docstring.
MAGI_V1 = b'SPBK1'
SUFFIKS = '.enc'

#: Under dette er nøkkelen en passfrase, og en bucket med helseopplysninger lar
#: seg knekke offline — `_avledet_nokkel` er én runde SHA-256. En hard sjekk i
#: `settings.py` kunne stoppet deployen på en nøkkel ingen vet lengden på, så det
#: vises som et avvik på /portal-admin/backup/ i stedet. Å bytte nøkkel gjør de
#: gamle filene uleselige med den nye: den gamle må da ligge i passordbehandleren
#: i 730 dager.
NOKKEL_MINSTE_LENGDE = 32

#: **Ett prefiks per oppbevaringstid** (13. sep. 2026). Fristene kan bare
#: skilles i bucketen hvis filene ligger på hver sin sti, og livssyklusreglene
#: filtrerer på prefiks: `backups/` i 730 dager, `full/` i 90. Se
#: `docs/PLAN_BACKUP_OMLEGGING.md` §6.2 og §7.
PREFIKS = 'backups/'
PREFIKS_FULL = 'full/'
ALLE_PREFIKS = (PREFIKS, PREFIKS_FULL)


def prefiks_for(module_slug: str) -> str:
    """Hvor i bucketen filene til denne modulen skal ligge.

    Den hele basen ligger for seg selv fordi den har en annen frist — ikke
    fordi den er en annen slags fil.
    """
    return PREFIKS_FULL if module_slug == 'full' else PREFIKS


# ── Konfigurasjon ────────────────────────────────────────────────────────────

def konfig() -> dict:
    return {
        'bucket': getattr(settings, 'OFFSITE_S3_BUCKET', ''),
        'region': getattr(settings, 'OFFSITE_S3_REGION', 'nl-ams'),
        'endpoint': getattr(settings, 'OFFSITE_S3_ENDPOINT', 'https://s3.nl-ams.scw.cloud'),
        'access_key': getattr(settings, 'OFFSITE_S3_ACCESS_KEY', ''),
        'secret_key': getattr(settings, 'OFFSITE_S3_SECRET_KEY', ''),
        'nokkel': getattr(settings, 'OFFSITE_BACKUP_KEY', ''),
    }


def er_konfigurert() -> bool:
    k = konfig()
    return bool(k['bucket'] and k['access_key'] and k['secret_key'] and k['nokkel'])


def oppsettfeil() -> str:
    """Hva som er galt med endepunktet og bucketnavnet, eller tom streng.

    **Funnet i prod 1. okt. 2026:** `OFFSITE_S3_ENDPOINT` sto som bucketens egen
    adresse, `https://sanitetsportalen.s3.nl-ams.scw.cloud/` — det Scaleway viser
    på bucketsiden. boto3 setter selv bucketnavnet på, så Scaleway leste det ene
    som bucket og det andre som objekt. Opplastingen *virket* — filene havnet
    under `sanitetsportalen/backups/…` — mens `hent_offsite --list` svarte
    `NoSuchKey` og oppbevaringsreglene på `backups/` og `full/` traff ingenting.

    Det er den verste formen for feil: det ser ut som det virker, og det som
    ikke virker er det man først trenger den dagen Railway er borte. Derfor
    nekter `_klient()` å lage en klient så lenge dette ikke er tomt, og feilen
    havner i `OffsiteKopi.feil`, på `/portal-admin/backup/` og i konfigsjekken.
    """
    from urllib.parse import urlsplit
    k = konfig()
    bucket, endepunkt = k['bucket'].strip(), (k['endpoint'] or '').strip()
    if not bucket:
        return ''
    if '/' in bucket or ':' in bucket:
        return (f'OFFSITE_S3_BUCKET er «{bucket}» — bare navnet skal stå der, uten '
                f'adresse og uten skråstrek.')
    if not endepunkt:
        return ''
    deler = urlsplit(endepunkt)
    if deler.scheme not in ('http', 'https'):
        return (f'OFFSITE_S3_ENDPOINT er «{endepunkt}» — den må begynne med https://, '
                f'for eksempel https://s3.nl-ams.scw.cloud.')
    vert = deler.hostname or ''   # `hostname` er alltid små bokstaver
    if vert == bucket.lower() or vert.startswith(bucket.lower() + '.'):
        rett = vert[len(bucket) + 1:] or 's3.<region>.scw.cloud'
        return (f'OFFSITE_S3_ENDPOINT er bucketens egen adresse ({endepunkt}). Sett den til '
                f'https://{rett} — bucketnavnet legges på av klienten, og står det i '
                f'adressen også, havner filene under feil navn.')
    if deler.path.strip('/'):
        return (f'OFFSITE_S3_ENDPOINT har en sti ({deler.path}). Bare adressen til '
                f'tjenesten skal stå der, for eksempel https://s3.nl-ams.scw.cloud.')
    return ''


def mangler() -> list[str]:
    """Hvilke variabler som mangler — for oversikten og for kommandoen."""
    k = konfig()
    navn = {'bucket': 'OFFSITE_S3_BUCKET', 'access_key': 'OFFSITE_S3_ACCESS_KEY',
            'secret_key': 'OFFSITE_S3_SECRET_KEY', 'nokkel': 'OFFSITE_BACKUP_KEY'}
    return [navn[felt] for felt in navn if not k[felt]]


# ── Kryptering ───────────────────────────────────────────────────────────────

def _avledet_nokkel(hemmelighet: str) -> bytes:
    if not hemmelighet:
        raise ValueError('OFFSITE_BACKUP_KEY mangler.')
    return hashlib.sha256(hemmelighet.encode('utf-8')).digest()


def nokkel_advarsel() -> str:
    """Tekst til oversikten når nøkkelen er satt, men for kort. Ellers tom."""
    nokkel = konfig()['nokkel']
    if nokkel and len(nokkel) < NOKKEL_MINSTE_LENGDE:
        return (f'OFFSITE_BACKUP_KEY er {len(nokkel)} tegn. Bruk minst '
                f'{NOKKEL_MINSTE_LENGDE} tilfeldige tegn — en kortere nøkkel lar '
                f'seg knekke offline av den som får tak i bucketen.')
    return ''


def _tillegg(magi: bytes, objekt: str) -> bytes:
    """Den autentiserte tilleggsdataen: formatet, og for `SPBK2` navnet."""
    if magi == MAGI_V1:
        return MAGI_V1
    if not objekt:
        raise ValueError('Objektnavnet mangler — det er en del av signaturen.')
    return MAGI + objekt.encode('utf-8')


def krypter(data: bytes, hemmelighet: str, *, objekt: str) -> bytes:
    """`SPBK2` for objektet `objekt` — navnet det skal ligge under i bucketen."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    tillegg = _tillegg(MAGI, objekt)
    nonce = secrets.token_bytes(12)
    return MAGI + nonce + AESGCM(_avledet_nokkel(hemmelighet)).encrypt(nonce, data, tillegg)


def dekrypter(blob: bytes, hemmelighet: str, *, objekt: str) -> bytes:
    """Klarteksten, eller `ValueError`. `SPBK2` avvises under et annet navn."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    magi = next((m for m in (MAGI, MAGI_V1) if blob.startswith(m)), None)
    if magi is None or len(blob) < len(magi) + 12 + 16:
        raise ValueError('Fila er ikke en kryptert backup fra portalen.')
    tillegg = _tillegg(magi, objekt)
    nonce = blob[len(magi):len(magi) + 12]
    try:
        return AESGCM(_avledet_nokkel(hemmelighet)).decrypt(nonce, blob[len(magi) + 12:], tillegg)
    except Exception as exc:   # InvalidTag — feil nøkkel, tuklet fil, eller flyttet fil
        raise ValueError('Kunne ikke dekryptere: feil OFFSITE_BACKUP_KEY, eller fila er '
                         'endret eller flyttet til et annet navn.') from exc


# ── S3 ───────────────────────────────────────────────────────────────────────

def _klient():
    feil = oppsettfeil()
    if feil:
        raise ValueError(feil)
    import boto3
    from botocore.config import Config
    k = konfig()
    return boto3.client(
        's3',
        region_name=k['region'],
        endpoint_url=k['endpoint'],
        aws_access_key_id=k['access_key'],
        aws_secret_access_key=k['secret_key'],
        config=Config(connect_timeout=10, read_timeout=60, retries={'max_attempts': 2}),
    )


def objektnavn(filnavn: str, module_slug: str = '') -> str:
    return f'{prefiks_for(module_slug)}{filnavn}{SUFFIKS}'


def last_opp(backup, sti) -> 'OffsiteKopi':
    """Krypter og last opp én backup-fil. Returnerer raden, med `feil` satt
    hvis det ikke gikk. Kaster aldri."""
    from core.models import OffsiteKopi
    k = konfig()
    rad = OffsiteKopi(backup_filnavn=backup.filename, module_slug=backup.module_slug,
                      objektnavn=objektnavn(backup.filename, backup.module_slug))
    try:
        raa = open(sti, 'rb').read()
        blob = krypter(raa, k['nokkel'], objekt=rad.objektnavn)
        rad.bytes = len(blob)
        _klient().put_object(
            Bucket=k['bucket'], Key=rad.objektnavn, Body=blob,
            ContentType='application/octet-stream',
            Metadata={'modul': backup.module_slug, 'kind': backup.kind,
                      'sha256': hashlib.sha256(raa).hexdigest()})
        rad.sendt_at = timezone.now()
        logger.info('core.offsite: lastet opp %s (%d bytes)', rad.objektnavn, rad.bytes)
    except Exception as exc:   # noqa: BLE001 — sporet skal ha årsaken
        rad.feil = _vask(f'{exc.__class__.__name__}: {exc}', 500)
        logger.exception('core.offsite: opplasting av %s feilet', backup.filename)
    rad.save()
    return rad


def meld_ny_backup(backup, sti) -> None:
    """Kalles av `create_backup` etter at fila er skrevet. Inert uten
    konfigurasjon; kaster aldri."""
    if backup is None or not er_konfigurert():
        return
    try:
        last_opp(backup, sti)
    except Exception:   # noqa: BLE001
        logger.exception('core.offsite: uventet feil ved opplasting')


def list_objekter() -> list[dict]:
    """[{navn, bytes, endret}] for alt under begge prefiksene, nyeste først."""
    k = konfig()
    ut = []
    for prefiks in ALLE_PREFIKS:
        token = None
        while True:
            args = {'Bucket': k['bucket'], 'Prefix': prefiks}
            if token:
                args['ContinuationToken'] = token
            svar = _klient().list_objects_v2(**args)
            for o in svar.get('Contents', []) or []:
                ut.append({'navn': o['Key'], 'bytes': o.get('Size', 0),
                           'endret': o.get('LastModified')})
            if not svar.get('IsTruncated'):
                break
            token = svar.get('NextContinuationToken')
    ut.sort(key=lambda o: (o['endret'] is None, o['endret']), reverse=True)
    return ut


def hent(objekt: str):
    """Hent, dekrypter og legg fila der `restore_backup` finner den. Lager en
    `Backup`-rad hvis den mangler (fila kan komme fra en annen Railway-base).
    Returnerer (Backup, sti).

    **Modulen og typen leses av filnavnet, ikke av S3-metadata** (29. sep.
    2026): metadataen settes av den som laster opp, og ingenting sjekket den.
    Navnet er autentisert i `SPBK2`. Og en fil som finnes på volumet med et
    annet innhold, **skrives ikke over** — den kan være den eneste kopien.
    """
    from core.backup import get_backup_dir, get_handler
    from core.backup.service import kind_fra_filnavn
    from core.models import Backup
    k = konfig()
    # Filnavnet alene holder: prefikset utledes av slugen i navnet, så
    # `hent_offsite backup-full-...` finner fila under `full/` uten at man må
    # vite hvor den ligger.
    if not objekt.startswith(ALLE_PREFIKS):
        objekt = prefiks_for(_slug_fra_filnavn(objekt)) + objekt
    if not objekt.endswith(SUFFIKS):
        objekt += SUFFIKS
    brukt_prefiks = next(p for p in ALLE_PREFIKS if objekt.startswith(p))
    filnavn = objekt[len(brukt_prefiks):-len(SUFFIKS)]
    # Objektnavnet bestemmer stien fila skrives til (13. sep. 2026, L3): en
    # kompromittert bucket skal ikke være en vei ut av BACKUP_DIR.
    if not filnavn or '/' in filnavn or '\\' in filnavn or filnavn != Path(filnavn).name:
        raise ValueError(f'Objektnavnet «{objekt}» er ikke et filnavn.')
    slug, kind = _slug_fra_filnavn(filnavn), kind_fra_filnavn(filnavn)
    if not slug or not kind or get_handler(slug) is None:
        raise ValueError(f'«{filnavn}» er ikke navnet på en backupfil fra portalen — '
                         f'modulen og typen kan ikke leses av det.')
    if prefiks_for(slug) != brukt_prefiks:
        raise ValueError(f'«{objekt}» ligger under feil prefiks for modulen «{slug}».')
    svar = _klient().get_object(Bucket=k['bucket'], Key=objekt)
    blob = svar['Body'].read()
    gammelt = blob.startswith(MAGI_V1)
    raa = dekrypter(blob, k['nokkel'], objekt=objekt)
    meta = svar.get('Metadata') or {}
    if meta.get('modul') and meta.get('modul') != slug:
        logger.warning('core.offsite: %s har metadata modul=%r, men navnet sier %r — '
                       'navnet gjelder', objekt, meta.get('modul'), slug)
    sti = get_backup_dir() / filnavn
    if sti.exists():
        if sti.read_bytes() != raa:
            raise ValueError(f'{filnavn} finnes allerede på volumet med et annet innhold, '
                             f'og skrives ikke over. Flytt eller slett den lokale fila først.')
    else:
        with open(sti, 'wb') as f:
            f.write(raa)
    note = f'Hentet fra offsite {timezone.localtime():%d.%m.%Y %H:%M}'
    if gammelt:
        note += ' — SPBK1: navnet er ikke autentisert i dette formatet'
    backup, _ = Backup.objects.get_or_create(
        filename=filnavn,
        defaults={'kind': kind, 'size_bytes': len(raa), 'module_slug': slug, 'note': note})
    return backup, sti


def _slug_fra_filnavn(filnavn: str) -> str:
    """Modulen en fil hører til. Parseren bor ved siden av `_build_filename` i
    `core.backup.service`, så formen på filnavnet har ett sted å endres."""
    from core.backup.service import slug_fra_filnavn
    return slug_fra_filnavn(filnavn)


# ── Oppbevaring i bucketen ───────────────────────────────────────────────────
#
# Fristene håndheves av Scaleway, ikke av oss: portalens IAM-nøkkel har ikke
# sletterett, og `enforce_cap` rører bare volumet. Det betyr at
# livssyklusreglene er den *eneste* mekanismen som sletter en offsite-kopi — og
# at en regel som stille slutter å treffe, er en oppbevaringstid som stille blir
# uendelig.

#: Det beslutningen sier (`docs/BACKUP.md` §1). Avvik fra dette vises på
#: `/portal-admin/backup/`, for en dokumentert frist som ikke er reell er det
#: alvorligste avviket vi kan ha.
FORVENTET_DAGER = {PREFIKS: 730, PREFIKS_FULL: 90}

_LIVSSYKLUS_CACHE = 'offsite:livssyklus'
_LIVSSYKLUS_TTL = 300


def livssyklus(bruk_cache: bool = True) -> dict:
    """Oppbevaringsreglene slik **bucketen** rapporterer dem.

    Ikke slik vi tror de er satt: hele poenget er at svaret kommer fra Scaleway.
    En regel med feil prefiks — `/full` i stedet for `full/` — ser riktig ut i
    konsollen og treffer ingenting, og filene blir liggende for alltid uten at
    noe sier fra.

    Leses med `ObjectStorageBucketsRead`, som portalens nøkkel har. Den kan
    ikke *skrive* bucket-oppsettet, og det er riktig slik: en portal som kunne
    forkorte sin egen oppbevaringsregel, ville ikke vært en sperre.

    Kaster aldri. Et kort som selv gir feil er borte akkurat når man trenger
    det, så alt som går galt havner i `feil` og vises som «ukjent».
    """
    from django.core.cache import cache

    if bruk_cache:
        try:
            lagret = cache.get(_LIVSSYKLUS_CACHE)
            if lagret is not None:
                return lagret
        except Exception:   # noqa: BLE001 — død cache skal ikke ta ned kortet
            pass

    svar = _les_livssyklus()

    if bruk_cache:
        try:
            cache.set(_LIVSSYKLUS_CACHE, svar, _LIVSSYKLUS_TTL)
        except Exception:   # noqa: BLE001
            pass
    return svar


def _les_livssyklus() -> dict:
    if not er_konfigurert():
        return {'kjent': False, 'feil': '', 'regler': [], 'avvik': []}

    k = konfig()
    try:
        raa = _klient().get_bucket_lifecycle_configuration(
            Bucket=k['bucket']).get('Rules', []) or []
    except Exception as exc:   # noqa: BLE001
        navn = exc.__class__.__name__
        kode = getattr(exc, 'response', {}).get('Error', {}).get('Code', '')
        if kode == 'NoSuchLifecycleConfiguration':
            # Ikke en lesefeil: bucketen har ingen regler. Da slettes ingenting
            # noen gang, og det er en oppbevaringstid ingen har bestemt.
            return {'kjent': True, 'feil': '', 'regler': [],
                    'avvik': [f'Ingen livssyklusregel for «{p}» — filene der '
                              f'blir liggende for alltid.'
                              for p in FORVENTET_DAGER]}
        if kode in ('AccessDenied', 'Forbidden'):
            # **Koden står i meldinga, ikke bare tolkningen av den**
            # (15. sep. 2026). Teksten sa «nøkkelen mangler
            # ObjectStorageBucketsRead» uansett hva Scaleway faktisk svarte, og
            # da er en riktig satt nøkkel og en feil i vår egen kode umulig å
            # skille fra hverandre: begge ser ut som et rettighetsproblem.
            # Kortet skal si hva som ble spurt om og hva som kom tilbake.
            return {'kjent': False, 'regler': [], 'avvik': [],
                    'feil': f'Scaleway svarte «{kode}» på lesing av '
                            f'livssyklusreglene. Har nøkkelen '
                            f'ObjectStorageBucketsRead? '
                            f'({_vask(str(exc), 160)})'}
        logger.warning('core.offsite: kunne ikke lese livssyklusreglene: %s', exc)
        return {'kjent': False, 'regler': [], 'avvik': [],
                'feil': _vask(f'{navn}: {exc}', 200)}

    regler = []
    for rad in raa:
        prefiks = _prefiks(rad)
        regler.append({
            'id': rad.get('ID', ''),
            'prefiks': prefiks,
            'dager': (rad.get('Expiration') or {}).get('Days'),
            'aktiv': rad.get('Status') == 'Enabled',
        })

    return {'kjent': True, 'feil': '', 'regler': regler,
            'avvik': _avvik(regler)}


def vask_feil(melding: str, maks: int = 300) -> str:
    """Offentlig: feiltekst fra backup og offsite uten nøkler, til nettleseren."""
    return _vask(melding, maks)


def _vask(melding: str, maks: int) -> str:
    """Feilteksten uten nøkler og URL-legitimasjon. Den vises i nettleseren."""
    k = konfig()
    return vask(melding, hemmeligheter=(k.get('access_key'), k.get('secret_key'),
                                        k.get('nokkel')), maks=maks)


def _prefiks(rad: dict) -> str:
    """Prefikset regelen filtrerer på, uansett hvilken form S3 sender det i.

    **Tre former, og vi leste to** (15. sep. 2026). En regel med *bare* et
    prefiks kommer som `Filter.Prefix`; den gamle API-versjonen la det på
    toppnivå; men en regel som kombinerer prefiks med noe annet — en tag, en
    størrelsesgrense — pakker alt i `Filter.And`, og da er `Filter.Prefix`
    fraværende.

    Uten den tredje formen leste vi tomt prefiks, og `_avvik()` meldte «ingen
    livssyklusregel for backups/ — filene der blir liggende for alltid» om en
    regel som sto helt riktig i bucketen. Det er den verste sorten feilmelding:
    den peker på en ekte fare, på et tidspunkt der faren ikke finnes, og lærer
    den som leser den å overse kortet.
    """
    f = rad.get('Filter') or {}
    for kandidat in (f.get('Prefix'), (f.get('And') or {}).get('Prefix'),
                     rad.get('Prefix')):
        if kandidat is not None:
            return kandidat
    return ''


def _avvik(regler: list[dict]) -> list[str]:
    """Hva som ikke stemmer med beslutningen, i klartekst.

    Sammenligningen er på **nøyaktig** prefiks. `/full` og `full` er ikke
    `full/`, og forskjellen er at regelen treffer alt eller ingenting.
    """
    ut = []
    for prefiks, dager in FORVENTET_DAGER.items():
        treff = [r for r in regler
                 if r['prefiks'] == prefiks and r['dager'] is not None]
        if not treff:
            nesten = [r['prefiks'] for r in regler
                      if r['prefiks'] and r['prefiks'].strip('/') == prefiks.strip('/')
                      and r['prefiks'] != prefiks]
            if nesten:
                ut.append(f'Regelen for «{prefiks}» står som «{nesten[0]}» og '
                          f'treffer ingenting. Prefikset må være nøyaktig '
                          f'«{prefiks}».')
            else:
                ut.append(f'Ingen livssyklusregel for «{prefiks}» — filene der '
                          f'blir liggende for alltid.')
            continue
        regel = treff[0]
        if not regel['aktiv']:
            ut.append(f'Regelen for «{prefiks}» er slått av.')
        elif regel['dager'] != dager:
            ut.append(f'«{prefiks}» står på {regel["dager"]} dager, '
                      f'men skal være {dager}.')
    return ut


def status() -> dict:
    """Til oversikten: konfigurert, siste opplasting, siste feil, antall."""
    from core.models import OffsiteKopi
    siste = OffsiteKopi.objects.order_by('-created_at').first()
    siste_ok = OffsiteKopi.objects.filter(feil='').order_by('-created_at').first()
    return {
        'konfigurert': er_konfigurert(),
        'mangler': mangler(),
        'bucket': konfig()['bucket'],
        'antall': OffsiteKopi.objects.filter(feil='').count(),
        'nokkel_advarsel': nokkel_advarsel(),
        'oppsettfeil': oppsettfeil(),
        'siste_ok': siste_ok,
        'siste_feil': siste if siste is not None and siste.feil else None,
        'livssyklus': livssyklus(),
    }
