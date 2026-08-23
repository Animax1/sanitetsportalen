"""Invitasjonslenker: signert, tidsbegrenset og enbruks — uten egen tabell.

Admin oppretter kontoen, systemet sender en lenke, brukeren setter sitt eget
passord. Fordelen framfor det midlertidige passordet er at **det ikke finnes
noe å formidle**: i dag genereres et 12-tegns passord som vises på skjermen én
gang og må videreformidles, typisk over en kanal man ikke vil ha passord i.

**Enbruks uten tilstand.** Tokenet inneholder et avtrykk av brukerens
passord-hash. Setter brukeren et passord, endres hashen, og avtrykket i
lenken slutter å stemme — lenken er død. Ingen tabell å rydde, ingen jobb som
må huske å utløpe noe. Samme mekanisme som Djangos egen
``PasswordResetTokenGenerator`` bygger på, uttrykt med den ``TimestampSigner``
kodebasen allerede bruker til MFA-trust-cookies.

**Levetid: 3 døgn.** Besluttet 23. aug. 2026. Kortere enn Djangos default på
tre døgn for reset er ikke poenget — poenget er at en invitasjon som ikke er
brukt innen tre døgn sannsynligvis ikke blir det, og at admin heller sender en
ny på forespørsel enn å la en gyldig lenke ligge i en innboks i ukevis.

**Avtrykket er ikke en hemmelighet, men det er heller ikke passordet.** Det er
en trunkert SHA-256 av passord-*hashen* (som allerede er en PBKDF2-avledning).
Signaturen er det som gjør tokenet uforfalskbart; avtrykket gjør det enbruks.
"""
import hashlib
import logging

from django.core import signing
from django.utils.crypto import constant_time_compare

logger = logging.getLogger(__name__)

# Egen salt slik at et token herfra aldri kan gjenbrukes i en annen
# signeringssammenheng — f.eks. MFA-trust-cookien, som bruker samme signer.
SALT = 'accounts.invitasjon'

LEVETID_SEKUNDER = 3 * 24 * 60 * 60


def _passordavtrykk(user):
    """Kort avtrykk av passord-hashen. Endres i det brukeren setter passord."""
    return hashlib.sha256(user.password.encode('utf-8')).hexdigest()[:16]


def lag_token(user):
    """Signert token for én invitasjon."""
    signer = signing.TimestampSigner(salt=SALT)
    return signer.sign(f'{user.pk}:{_passordavtrykk(user)}')


def les_token(token):
    """Returner brukeren tokenet gjelder, eller ``None``.

    ``None`` dekker alle feiltilfeller med vilje — ugyldig signatur, utløpt
    lenke, slettet eller frosset konto, og lenke som allerede er brukt. Siden
    kallstedet uansett skal vise samme melding uansett årsak, er det ingen
    grunn til å skille dem her. Det er samme resonnement som ligger bak at
    innloggingsskjemaet sier «feil brukernavn eller passord», aldri hvilken.
    """
    from .models import CustomUser

    signer = signing.TimestampSigner(salt=SALT)
    try:
        verdi = signer.unsign(token, max_age=LEVETID_SEKUNDER)
        pk_str, avtrykk = verdi.split(':', 1)
        user = CustomUser.objects.get(pk=int(pk_str), is_active=True)
    except (signing.BadSignature, signing.SignatureExpired, ValueError,
            TypeError, CustomUser.DoesNotExist):
        return None

    if not constant_time_compare(avtrykk, _passordavtrykk(user)):
        return None
    return user


def kan_inviteres(user):
    """En invitasjon krever en personlig konto med en innboks.

    Delte kontoer utelates på et **eksplisitt flagg**, ikke ved å utlede fra
    «har e-post». Utledningen ville slått feil den dagen noen la inn en
    kontakt-e-post på en bil-konto, og da er lenken en lateral vei inn.
    """
    return bool(user.email) and not user.er_delt_konto


def send_invitasjon(user, request):
    """Send invitasjonslenken. Returnerer True hvis den gikk ut.

    Feiler utsendingen, returneres False i stedet for at det kastes videre:
    kontoen **er** opprettet på det tidspunktet, og admin skal få vite at
    lenken ikke gikk ut — ikke møte en 500-side og lure på om brukeren finnes.
    Reserven er å sette et passord manuelt.
    """
    from django.conf import settings
    from django.core.mail import EmailMessage
    from django.urls import reverse

    if not kan_inviteres(user):
        return False

    lenke = request.build_absolute_uri(
        reverse('accounts:invitasjon', args=[lag_token(user)])
    )
    hilsen = user.fullt_navn or user.username

    kropp = (
        f'Hei {hilsen},\n\n'
        f'Du har fått en konto i Sanitetsportalen med brukernavnet '
        f'«{user.username}».\n\n'
        f'Velg ditt eget passord her:\n\n'
        f'{lenke}\n\n'
        f'Lenken er gyldig i 3 døgn og kan kun brukes én gang. '
        f'Har den gått ut, si fra så sender vi en ny.\n\n'
        f'Har du ikke ventet denne e-posten, kan du se bort fra den — '
        f'kontoen kan ikke tas i bruk uten lenken.\n'
    )

    try:
        EmailMessage(
            subject='Sett passordet ditt i Sanitetsportalen',
            body=kropp,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        ).send(fail_silently=False)
        return True
    except Exception:
        logger.warning('Kunne ikke sende invitasjon til bruker %s', user.pk,
                       exc_info=True)
        return False
