"""Signerte, tidsbegrensede engangslenker — delt maskineri.

Både invitasjon og passord-reset trenger det samme: en lenke som er
uforfalskbar, utløper av seg selv, og slutter å virke i det den er brukt.
Forskjellen er levetiden og hvem som ber om den.

**Enbruks uten tilstand.** Tokenet bærer et avtrykk av brukerens passord-hash.
Settes et passord, endres hashen, og avtrykket slutter å stemme. Ingen tabell
å rydde, ingen jobb som må huske å utløpe noe. Det er mekanismen Djangos egen
``PasswordResetTokenGenerator`` bygger på, uttrykt med den ``TimestampSigner``
kodebasen allerede bruker til MFA-trust-cookies.

**Hver bruk har sin egen salt.** Et invitasjonstoken kan dermed aldri leses som
et reset-token, selv om formatet er identisk. Uten det ville en invitasjon med
tre døgns levetid kunnet brukes der reset har én time.
"""
import hashlib

from django.core import signing
from django.utils.crypto import constant_time_compare


def _passordavtrykk(user):
    """Kort avtrykk av passord-hashen. Endres i det brukeren setter passord.

    Avtrykket er ikke en hemmelighet, men det er heller ikke passordet: det er
    en trunkert SHA-256 av passord-*hashen*, som allerede er en PBKDF2-
    avledning. Signaturen gjør tokenet uforfalskbart; avtrykket gjør det
    enbruks.
    """
    return hashlib.sha256(user.password.encode('utf-8')).hexdigest()[:16]


def lag(user, *, salt):
    """Signert token for én bruk, knyttet til brukerens nåværende passord."""
    signer = signing.TimestampSigner(salt=salt)
    return signer.sign(f'{user.pk}:{_passordavtrykk(user)}')


def les(token, *, salt, levetid):
    """Returner brukeren tokenet gjelder, eller ``None``.

    ``None`` dekker alle feiltilfeller med vilje — ugyldig signatur, utløpt
    lenke, slettet eller frosset konto, og lenke som allerede er brukt. Siden
    kallstedet skal vise samme melding uansett årsak, er det ingen grunn til å
    skille dem her. Samme resonnement som at innloggingsskjemaet sier «feil
    brukernavn eller passord», aldri hvilken av dem.
    """
    from .models import CustomUser

    signer = signing.TimestampSigner(salt=salt)
    try:
        verdi = signer.unsign(token, max_age=levetid)
        pk_str, avtrykk = verdi.split(':', 1)
        user = CustomUser.objects.get(pk=int(pk_str), is_active=True)
    except (signing.BadSignature, signing.SignatureExpired, ValueError,
            TypeError, CustomUser.DoesNotExist):
        return None

    if not constant_time_compare(avtrykk, _passordavtrykk(user)):
        return None
    return user
