"""Klientens IP-adresse, ett sted (13. sep. 2026, sikkerhetsgjennomgangen H2).

Fram til da ble den lest på tre måter: rate-limit-bøtta per IP telte på
`REMOTE_ADDR`, som bak Railways proxy er proxyens adresse — hele
organisasjonen delte én bøtte, og ingen angriper ble bremset. Innloggingsloggen
og pasient-/oppdragsaudit tok *første* ledd i `X-Forwarded-For`, som klienten
selv kan sette — revisjonssporets IP var forfalskbart. Vaktliste-audit og
arkivene logget proxyen.

Regelen: **siste** ledd i `X-Forwarded-For` er det proxyen selv la til, og
Railway er én betrodd proxy foran appen. Alt foran det er klientens påstand.
Leddet valideres som IP; er det ikke en, faller vi til `REMOTE_ADDR`. Utenfor
en proxy (lokalt) finnes ingen header, og `REMOTE_ADDR` er klienten.
"""
import ipaddress


def _gyldig(verdi):
    verdi = (verdi or '').strip()
    if not verdi:
        return None
    # `[::1]:1234`/`1.2.3.4:1234` forekommer hos enkelte proxyer.
    if verdi.startswith('['):
        verdi = verdi[1:].split(']')[0]
    try:
        return str(ipaddress.ip_address(verdi))
    except ValueError:
        pass
    if verdi.count(':') == 1:
        try:
            return str(ipaddress.ip_address(verdi.rsplit(':', 1)[0]))
        except ValueError:
            return None
    return None


def klient_ip(request):
    """IP-en handlingen kom fra, eller None når ingen kan bekreftes."""
    meta = getattr(request, 'META', None) or {}
    videresendt = meta.get('HTTP_X_FORWARDED_FOR', '')
    if videresendt:
        ip = _gyldig(videresendt.split(',')[-1])
        if ip:
            return ip
    return _gyldig(meta.get('REMOTE_ADDR'))


def ratelimit_nokkel(group, request):
    """`key=` for `is_ratelimited`: én bøtte per klient, ikke per proxy."""
    return klient_ip(request) or 'ukjent'
