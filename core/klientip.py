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
    """IP-en handlingen kom fra, eller None når ingen kan bekreftes.

    **Headeren leses bare bak proxyen** (`settings.KLIENTIP_BAK_PROXY`, 28. sep.
    2026). Uten en proxy foran er siste ledd like mye klientens påstand som det
    første, og da er `REMOTE_ADDR` svaret.
    """
    from django.conf import settings
    meta = getattr(request, 'META', None) or {}
    videresendt = meta.get('HTTP_X_FORWARDED_FOR', '') if getattr(
        settings, 'KLIENTIP_BAK_PROXY', False) else ''
    if videresendt:
        ip = _gyldig(videresendt.split(',')[-1])
        if ip:
            return ip
    return _gyldig(meta.get('REMOTE_ADDR'))


def ratelimit_nokkel(group, request):
    """`key=` for `is_ratelimited`: én bøtte per klient, ikke per proxy.

    **IPv6 telles per /64** (29. sep. 2026). Et hjem eller en VPS får et helt
    /64-nett, og med én bøtte per adresse var bremsen uten grense for den som
    bytter adresse innenfor det.
    """
    ip = klient_ip(request)
    if not ip:
        return 'ukjent'
    try:
        adresse = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if adresse.version == 6 and adresse.ipv4_mapped is None:
        return str(ipaddress.ip_network(f'{ip}/64', strict=False))
    return ip
