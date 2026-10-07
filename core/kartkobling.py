"""Klienten mot kart.sanitet.net: bilenes posisjon, lagenes sted, og lag som har gått seg bort.

`docs/archived/PLAN_KARTKOBLING.md` (30. sep. 2026). Retningen er **bare portal → kart**:
kartet svarer 204 og returnerer aldri data, og kartet kaller aldri portalen.
Ligger i `core` fordi både oppdrag (bilene) og KO (lagene) sender, og ingen av
dem får kjenne den andre.

Fem regler:

- **Inert uten oppsett.** Er `KART_URL` eller `KART_HMAC_NOKKEL` tom, gjør
  funksjonene ingenting — samme idiom som `core/offsite.py`. Hvert Railway-miljø
  har sitt eget kart og sin egen nøkkel (B14): staging sender til testkart.sanitet.net.
- **Kaster aldri.** Kartet er et hjelpemiddel; en stempling i en bil skal aldri
  feile fordi kartet er nede. Enhver feil blir én `warning` med navn og
  statuskode — **aldri kroppen**, som bærer posisjonen.
- **Pause etter feil.** Etter en feil hoppes sendinger over i `PAUSE_S`, så en
  bil som stempler mens kartet er nede ikke venter `TIMEOUT_S` per trykk.
  Ikke etter et 4xx — det er et raskt nei, se `_raskt_avslag`.
- **Portalen lagrer ingenting** (B9). Ingen tabell, ingen auditrad. Siste
  utfall ligger i cachen for statuskortet på `/portal-admin/server-status/` —
  i `AppSetting` ville det gitt en auditrad per stempling.
- **Vet ingenting om transaksjoner.** Kallstedene pakker kallet i
  `transaction.on_commit`, så en stempling som rulles tilbake aldri sendes.

**Sendingen svarer om kartet tok imot** (7. okt. 2026). Stemplingene og KO
lar svaret ligge — de sender i `on_commit` og har ingen å fortelle det til.
De to knappene («Send posisjon» i bilen, «Vi finner ikke fram» hos lagene)
har noen som venter på svaret, og en knapp som sier «sendt» om noe som aldri
kom fram, er verre enn en som sier fra.

Signaturen er HMAC-SHA256 over `"<X-Portal-Tid>." + rå kropp`, som
`portal/signatur.py` i kartet sjekker. Ikke kryptering: TLS bærer
konfidensialiteten, HMAC bærer ekthet og integritet (B8).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import time
from datetime import datetime, timedelta
from urllib import error, request
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

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


#: En posisjon med tidspunkt lenger fram enn dette avvises. Kartet lar nyeste
#: tidspunkt vinne, så én telefon med klokka et døgn fram ville ellers frosset
#: sin egen markør til raden ble ryddet.
POSISJON_MAKS_FRAM = timedelta(minutes=5)


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


def les_posisjon(pos) -> tuple[float, float, datetime]:
    """``(lat, lon, tid)`` fra ``{"lat", "lon", "tid"}`` — eller `ValueError`.

    Den ene valideringen av en posisjon fra en telefon, brukt av bilens
    stempling, bilens posisjonsknapp og lagenes «Vi finner ikke fram». Hva
    en ugyldig posisjon *fører til*, er kallstedets sak: stemplingen dropper
    den (B7), knappene svarer 400. Feilmeldingen bærer aldri verdiene.
    """
    if not isinstance(pos, dict) or set(pos) != {'lat', 'lon', 'tid'}:
        raise ValueError('formen')
    lat, lon = pos['lat'], pos['lon']
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (lat, lon)):
        raise ValueError('ikke tall')
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('utenfor')
    try:
        tid = parse_datetime(str(pos['tid']))
    except ValueError:
        tid = None
    if tid is None:
        raise ValueError('tid')
    if timezone.is_naive(tid):
        tid = timezone.make_aware(tid)
    if tid > timezone.now() + POSISJON_MAKS_FRAM:
        raise ValueError('tid fram i tid')
    return lat, lon, tid


def send_enhet(navn: str, lat: float, lon: float, tidspunkt: datetime) -> bool:
    """Bilens posisjon — ved en stempling, eller fra knappen «Send posisjon».
    Navnet skal være `Enhet.navn` fra databasen, aldri noe fra request-kroppen."""
    return _send('enhet', navn, lambda: {
        'navn': navn, 'lat': lat, 'lon': lon, 'tidspunkt': _tidspunkt(tidspunkt),
    })


def send_lag(navn: str, sted: str, tidspunkt: datetime) -> bool:
    """Hvor laget står nå. Tomt sted tar laget av kartet."""
    return _send('lag', navn, lambda: {'navn': navn, 'sted': sted,
                                       'tidspunkt': _tidspunkt(tidspunkt)})


def send_lag_posisjon(navn: str, lat: float, lon: float, tidspunkt: datetime,
                      utloper: datetime) -> bool:
    """«Vi finner ikke fram» fra lagregistreringen (7. okt. 2026).

    **Et eget endepunkt, ikke et felt på `lag`.** `lag` er hvor KO har
    *plassert* laget — tilstand, sendt av KO. Dette er hvor laget *står* og
    ber om hjelp — en midlertidig markør, oransje i kartet, som forsvinner av
    seg selv ved `utloper`. Sto de på samme rad, ville den ene skrevet over den
    andre, og kartet kunne ikke tegnet dem ulikt.

    `utloper` er et **tidspunkt**, ikke en varighet: varigheten er en
    portalinnstilling, og kartet skal ikke trenge å vite hva den var — bare
    når markøren skal bort.
    """
    return _send('lag-posisjon', navn, lambda: {
        'navn': navn, 'lat': lat, 'lon': lon, 'tidspunkt': _tidspunkt(tidspunkt),
        'utloper': _tidspunkt(utloper),
    })


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
        if not ok and not _raskt_avslag(kode):
            cache.set(PAUSE_NOKKEL, True, PAUSE_S)
    except Exception:
        pass  # en død cache skal ikke gjøre en vellykket sending til en feil


def _raskt_avslag(kode: int | None) -> bool:
    """Et 4xx-svar er et **raskt** nei, og gir ingen pause (7. okt. 2026).

    Pausen finnes for at en bil ikke skal vente `TIMEOUT_S` per trykk mens
    kartet er nede — den verner mot det *trege*. Et 4xx kom fram og ble
    besvart med en gang. Og det er sendingens eget problem: kartet som ennå
    ikke kjenner `lag-posisjon` svarer 404, og uten dette unntaket ville ett
    trykk på «Vi finner ikke fram» stoppet bilenes posisjon i et minutt.
    """
    return kode is not None and 400 <= kode < 500


def _send(hva: str, navn: str, bygg) -> bool:
    """`bygg` lager kroppen inne i `try`, så også et ugyldig tidspunkt svelges.
    True bare når kartet svarte 2xx."""
    if not er_konfigurert():
        return False
    if _i_pause():
        logger.info('Kartkobling: %s %r hoppet over, pause etter feil', hva, navn)
        return False
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
        return False
    except Exception as exc:
        # Bare typen: meldingen fra urllib kan i verste fall sitere adressen.
        logger.warning('Kartkobling: %s %r feilet (%s, %s)', hva, navn,
                       kode, type(exc).__name__)
        _husk(hva, False, kode)
        return False
    _husk(hva, True, kode)
    return True
