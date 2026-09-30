"""Klienten mot kart.sanitet.net: bilenes posisjon ved stempling og lagenes sted.

`docs/PLAN_KARTKOBLING.md` (30. sep. 2026). Retningen er **bare portal → kart**:
kartet svarer 204 og returnerer aldri data, og kartet kaller aldri portalen.
Ligger i `core` fordi både oppdrag (bilene) og KO (lagene) sender, og ingen av
dem får kjenne den andre.

Fem regler:

- **Inert uten oppsett.** Er `KART_URL` eller `KART_HMAC_NOKKEL` tom, gjør
  funksjonene ingenting — samme idiom som `core/offsite.py`. Staging-portalen
  har tom `KART_URL` til staging-kartet finnes (B14).
- **Kaster aldri.** Kartet er et hjelpemiddel; en stempling i en bil skal aldri
  feile fordi kartet er nede. Enhver feil blir én `warning` med navn og
  statuskode — **aldri kroppen**, som bærer posisjonen.
- **Pause etter feil.** Etter en feil hoppes sendinger over i `PAUSE_S`, så en
  bil som stempler mens kartet er nede ikke venter `TIMEOUT_S` per trykk.
- **Portalen lagrer ingenting** (B9). Ingen tabell, ingen auditrad. Siste
  utfall ligger i cachen for statuskortet på `/portal-admin/server-status/` —
  i `AppSetting` ville det gitt en auditrad per stempling.
- **Vet ingenting om transaksjoner.** Kallstedene pakker kallet i
  `transaction.on_commit`, så en stempling som rulles tilbake aldri sendes.

Signaturen er HMAC-SHA256 over `"<X-Portal-Tid>." + rå kropp`, som
`portal/signatur.py` i kartet sjekker. Ikke kryptering: TLS bærer
konfidensialiteten, HMAC bærer ekthet og integritet (B8).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from urllib import error, request
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

TIMEOUT_S = 3
#: Egen User-Agent, ikke urllibs «Python-urllib/3.x». Cloudflare foran kartet
#: avviser den med 403 og «error code: 1010» før appen ser forespørselen
#: (funnet på staging 30. sep. 2026). Kartet ser da aldri noe, og feilen er
#: ikke nøkkelen — derfor forklarer statuskortet 403 for seg.
USER_AGENT = 'sanitetsportalen-kartkobling/1.0'
PAUSE_S = 60
PAUSE_NOKKEL = 'kartkobling:pause'
SISTE_NOKKEL = 'kartkobling:siste'
#: Hvor lenge siste utfall står på statuskortet uten en ny sending.
SISTE_TTL_S = 7 * 24 * 3600


def er_konfigurert() -> bool:
    return bool(getattr(settings, 'KART_URL', '') and getattr(settings, 'KART_HMAC_NOKKEL', ''))


def signer(nokkel: str, tid: str, kropp: bytes) -> str:
    mac = hmac.new(nokkel.encode(), tid.encode() + b'.' + kropp, hashlib.sha256)
    return 'sha256=' + mac.hexdigest()


def _tidspunkt(tid: datetime) -> str:
    """ISO 8601 med sone — kartet avviser et tidspunkt uten, fordi «nyeste
    vinner» ikke kan avgjøres uten."""
    if timezone.is_naive(tid):
        tid = timezone.make_aware(tid)
    return timezone.localtime(tid).isoformat(timespec='seconds')


def send_enhet(navn: str, lat: float, lon: float, tidspunkt: datetime) -> None:
    """Bilens posisjon ved en stempling. Navnet skal være `Enhet.navn` fra
    databasen, aldri noe fra request-kroppen."""
    _send('enhet', navn, lambda: {
        'navn': navn, 'lat': lat, 'lon': lon, 'tidspunkt': _tidspunkt(tidspunkt),
    })


def send_lag(navn: str, sted: str, tidspunkt: datetime) -> None:
    """Hvor laget står nå. Tomt sted tar laget av kartet."""
    _send('lag', navn, lambda: {'navn': navn, 'sted': sted, 'tidspunkt': _tidspunkt(tidspunkt)})


def siste_utfall() -> dict | None:
    """``{'tid', 'ok', 'status', 'hva'}`` fra siste forsøk, eller None."""
    try:
        return cache.get(SISTE_NOKKEL)
    except Exception:
        return None


def status() -> dict:
    """Til kortet på `/portal-admin/server-status/`. Aldri nøkkelen."""
    return {
        'konfigurert': er_konfigurert(),
        'vert': urlsplit(getattr(settings, 'KART_URL', '')).netloc,
        'siste': siste_utfall(),
        'pause': _i_pause(),
    }


def _i_pause() -> bool:
    try:
        return bool(cache.get(PAUSE_NOKKEL))
    except Exception:
        return False


def _husk(hva: str, ok: bool, kode: int | None) -> None:
    try:
        cache.set(SISTE_NOKKEL, {
            'tid': timezone.now().isoformat(), 'ok': ok, 'status': kode, 'hva': hva,
        }, SISTE_TTL_S)
        if not ok:
            cache.set(PAUSE_NOKKEL, True, PAUSE_S)
    except Exception:
        pass  # en død cache skal ikke gjøre en vellykket sending til en feil


def _send(hva: str, navn: str, bygg) -> None:
    """`bygg` lager kroppen inne i `try`, så også et ugyldig tidspunkt svelges."""
    if not er_konfigurert():
        return
    if _i_pause():
        logger.info('Kartkobling: %s %r hoppet over, pause etter feil', hva, navn)
        return
    kode = None
    try:
        url = settings.KART_URL.rstrip('/') + f'/api/portal/{hva}'
        # urllib åpner også file:// og ftp://. Adressen kommer fra miljøet, men
        # en skrivefeil der skal ikke kunne lese en fil på serveren.
        if urlsplit(url).scheme not in ('https', 'http'):
            raise ValueError('KART_URL må være en http(s)-adresse')
        kropp = json.dumps(bygg(), separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        tid = str(int(time.time()))
        req = request.Request(url, data=kropp, method='POST', headers={
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
            'X-Portal-Tid': tid,
            'X-Portal-Signatur': signer(settings.KART_HMAC_NOKKEL, tid, kropp),
        })
        with request.urlopen(req, timeout=TIMEOUT_S) as svar:
            kode = svar.status
        if not 200 <= kode < 300:
            raise RuntimeError('uventet svar')
    except error.HTTPError as exc:
        kode = exc.code
        logger.warning('Kartkobling: %s %r avvist av kartet (%s)', hva, navn, kode)
        _husk(hva, False, kode)
        return
    except Exception as exc:
        # Bare typen: meldingen fra urllib kan i verste fall sitere adressen.
        logger.warning('Kartkobling: %s %r feilet (%s, %s)', hva, navn,
                       kode, type(exc).__name__)
        _husk(hva, False, kode)
        return
    _husk(hva, True, kode)
