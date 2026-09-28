"""MFA-stegene i innloggingen, og nullstillingen av dem.

**Den halvinnloggede sesjonen er bundet til passordet** (28. sep. 2026,
sikkerhetsgjennomgangen). Mellom passordsteget og MFA-steget er sesjonen
anonym — `login()` er ikke kalt — og det eneste den bar var brukerens ID. Den
som hadde passordet til en konto uten bekreftet enhet, kunne stoppe på
QR-koden, vente på at admin byttet passordet, og så fullføre oppsettet med sin
egen enhet: steget sjekket bare at kontoen var aktiv, og passordresetten
slettet bare sesjoner som var innlogget. Med `must_change_password` satt av
resetten slapp angriperen i tillegg å oppgi det gamle passordet.

Tre ting holder det nå, og hver dekker sin vei:

| Hva | Hvor | Stopper |
|---|---|---|
| Passordavtrykket i sesjonen | `hent_steg_bruker()` | Alle veier passordet kan byttes på — adminflaten, reset-lenken, invitasjonen, `sett_passord` |
| Levetiden, `STEG_LEVETID` | `hent_steg_bruker()` | En tilstand som ellers lever så lenge sesjonen fornyes |
| Halvinnloggede sesjoner slettes | `core.sesjoner.gjelder_bruker` | Frys og «Nullstill MFA», der passordet står |

Avtrykket er den samme formen som trust-cookien og de signerte lenkene bruker:
16 tegn av SHA-256 over hashen, aldri passordet.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.sesjoner import HALVINNLOGGET_NOKLER

#: Hvor lenge passordsteget holder. Oppsettet er det lange: man skal rekke å
#: installere en autentiseringsapp mellom QR-koden og koden.
STEG_LEVETID = timedelta(minutes=15)

OPPSETT, VERIFISERING = HALVINNLOGGET_NOKLER

_AVTRYKK = 'mfa_steg_avtrykk'
_STARTET = 'mfa_steg_startet'

#: Alt steget legger i sesjonen. Ryddes samlet, så en halv tilstand ikke blir
#: liggende og blandes med neste forsøk.
_ALLE_NOKLER = (
    OPPSETT, VERIFISERING, 'mfa_next_url', 'mfa_setup_device_id',
    'mfa_setup_backup_codes', _AVTRYKK, _STARTET,
)


def passordavtrykk(bruker) -> str:
    """Endres når passordet gjør det. Bærer ikke passordet, og ikke hele hashen."""
    return hashlib.sha256((bruker.password or '').encode('utf-8')).hexdigest()[:16]


def start_steg(request, bruker, steg, next_url) -> None:
    """Passordet er bestått: legg brukeren i `steg` (`OPPSETT` eller `VERIFISERING`)."""
    avslutt_steg(request)
    request.session[steg] = bruker.pk
    request.session['mfa_next_url'] = next_url
    request.session[_AVTRYKK] = passordavtrykk(bruker)
    request.session[_STARTET] = timezone.now().timestamp()


def avslutt_steg(request) -> None:
    for nokkel in _ALLE_NOKLER:
        request.session.pop(nokkel, None)


def hent_steg_bruker(request, steg):
    """Brukeren steget gjelder — eller `None`, og da er tilstanden ryddet.

    `None` betyr at innloggingen må begynne på nytt med passordet: kontoen er
    borte eller frosset, passordet er byttet, steget er for gammelt, eller
    sesjonen er fra før bindingen fantes.
    """
    from .models import CustomUser

    try:
        bruker = CustomUser.objects.get(pk=request.session.get(steg), is_active=True)
    except (CustomUser.DoesNotExist, TypeError, ValueError):
        bruker = None
    if bruker is None or not _steget_holder(request.session, bruker):
        avslutt_steg(request)
        return None
    return bruker


def _steget_holder(sesjon, bruker) -> bool:
    avtrykk = sesjon.get(_AVTRYKK)
    startet = sesjon.get(_STARTET)
    if not isinstance(avtrykk, str) or not isinstance(startet, (int, float)):
        return False
    if not hmac.compare_digest(avtrykk, passordavtrykk(bruker)):
        return False
    alder = timezone.now().timestamp() - startet
    # Litt slark bakover: to arbeidere kan ha klokker som står et øyeblikk fra
    # hverandre. Et steg «fra framtida» ut over det er ikke noe vi har laget.
    return -60 <= alder <= STEG_LEVETID.total_seconds()


def nullstill_mfa(bruker, *, kilde, utfort_av=None, ip=None, user_agent='') -> None:
    """Slett enhetene og reservekodene, krev nytt oppsett, og logg alle ut.

    **Én funksjon for knappen og kommandoen** (28. sep. 2026). Handlingen sto
    inne i `user_detail_view`; da `manage.py nullstill_mfa` kom, ville en kopi
    der vært to utgaver av en sikkerhetshandling som glir fra hverandre.
    `kilde` havner i auditraden, slik at det går an å se hvilken vei den kom.

    `mfa_required` settes, også om den sto av: den som mistet enheten skal
    møte oppsettet ved neste innlogging, ikke gå rett inn.
    """
    from django_otp.plugins.otp_static.models import StaticDevice
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from audit.models import AuditLog

    from .models import LoginEvent
    from .sesjoner import avslutt_alle_sesjoner

    with transaction.atomic():
        TOTPDevice.objects.filter(user=bruker).delete()
        StaticDevice.objects.filter(user=bruker).delete()
        bruker.mfa_required = True
        bruker.save(update_fields=['mfa_required'])
        LoginEvent.objects.create(
            user=bruker, username_attempt=bruker.username, success=True,
            ip=ip, user_agent=user_agent, event_type=LoginEvent.EVENT_MFA_RESET_BY_ADMIN,
        )
        # Innloggingsloggen sier at det skjedde, men ikke *hvem* som gjorde
        # det: raden står på brukeren. Auditloggen bærer den som gjorde det.
        AuditLog.objects.create(
            table_name='accounts_customuser', record_id=bruker.pk, action='UPDATE',
            field_name='mfa', new_value=f'nullstilt {kilde}',
            user=utfort_av, ip=ip,
        )
    avslutt_alle_sesjoner(bruker)
