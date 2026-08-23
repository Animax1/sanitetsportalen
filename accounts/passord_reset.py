"""Selvbetjent passord-reset. De sju beslutningene fra §6 i beslutningsnotatet.

Django har flyten innebygd og godt testet. Det som er prosjektspesifikt er
hvem som får lov, hvor lenge lenken varer, og hva som skjer etterpå — og det
er nettopp de tingene som ikke kan arves fra en standardvisning.

**Levetid: 1 time.** Besluttet 23. aug. 2026. En reset er akutt til forskjell
fra en invitasjon; en lenke som blir liggende i en innboks over natta er en
lengre eksponering enn nytten forsvarer. Invitasjonen har tre døgn av motsatt
grunn: kontoer opprettes gjerne dagen før en vakt.

**§6.1 — delte kontoer utelates, på et eksplisitt flagg.** Bil-kontoene deler
enhet og har ingen personlig eier. En reset-lenke til en delt innboks er en
lateral vei inn i systemet. Utelukkelsen skjer på ``er_delt_konto``, aldri ved
å utlede fra «har e-post» — utledningen ville slått feil den dagen noen la inn
en kontakt-e-post på en bil.

**§6.2 — MFA kan ikke omgås.** Reset gir nytt passord, men MFA-steget gjelder
fortsatt ved innlogging. Det følger av at flyten ender på innloggingssiden og
ikke logger noen inn. Mistes MFA-enheten, er admin eneste vei — ``reset_mfa``
er og forblir admin-only. Ellers er MFA verdiløst.

**§6.7 — ingen kontoenumerering.** Svaret er identisk enten adressen finnes
eller ikke. For en frivillig organisasjon avslører «har konto» *hvem som er
medlem og har vakter* — en personopplysning i seg selv, uavhengig av om noen
kommer inn. Det gjelder også rate-limit-svaret: strupes kun eksisterende
adresser, er strupingen i seg selv et svar.
"""
import logging

from . import signert_lenke

logger = logging.getLogger(__name__)

# Egen salt: et reset-token kan aldri leses som et invitasjonstoken, og
# omvendt. Uten det ville en invitasjon med tre døgns levetid kunnet brukes
# der reset har én time.
SALT = 'accounts.passord-reset'

LEVETID_SEKUNDER = 60 * 60

SUPPORT_EPOST = 'support@sanitet.net'


def lag_token(user):
    return signert_lenke.lag(user, salt=SALT)


def les_token(token):
    return signert_lenke.les(token, salt=SALT, levetid=LEVETID_SEKUNDER)


def kan_resettes(user):
    """§6.1: personlig konto, med innboks, som ikke er frosset."""
    return bool(user.email) and not user.er_delt_konto and user.is_active


def finn_bruker(epost):
    """Slå opp mottakeren, eller ``None``.

    Oppslaget er ufølsomt for store bokstaver av samme grunn som innlogging
    er det: mobiltastatur setter stor forbokstav, og en adresse skrevet
    `Kari@…` skal treffe kontoen som er lagret som `kari@…`.

    Returnerer ``None`` også når kontoen finnes men ikke kan resettes. Det er
    med vilje: kallstedet skal oppføre seg likt uansett, ellers er forskjellen
    i oppførsel et svar på om adressen finnes.
    """
    from .models import CustomUser

    epost = (epost or '').strip()
    if not epost:
        return None

    treff = list(CustomUser.objects.filter(email__iexact=epost)[:2])
    if len(treff) != 1:
        # Ingen treff, eller flere kontoer på samme adresse. Det siste skal
        # ikke kunne skje — `unique_email_if_set` hindrer det — men å gjette
        # hvem som mente hva er uansett feil svar.
        return None

    user = treff[0]
    return user if kan_resettes(user) else None


def send_reset(user, request):
    """Send reset-lenken. Returnerer True hvis den gikk ut.

    Feiler utsendingen, logges det og False returneres — men kallstedet skal
    **ikke** vise noe annet svar til brukeren. Ellers er en feilmelding et
    signal om at adressen finnes.
    """
    from django.conf import settings
    from django.core.mail import EmailMessage
    from django.urls import reverse

    lenke = request.build_absolute_uri(
        reverse('accounts:passord_reset', args=[lag_token(user)])
    )
    hilsen = user.fullt_navn or user.username

    kropp = (
        f'Hei {hilsen},\n\n'
        f'Noen har bedt om nytt passord for brukeren «{user.username}» i '
        f'Sanitetsportalen.\n\n'
        f'Velg et nytt passord her:\n\n'
        f'{lenke}\n\n'
        f'Lenken er gyldig i 1 time og kan kun brukes én gang.\n\n'
        f'Var det ikke deg, kan du se bort fra denne e-posten — passordet '
        f'ditt er uendret, og lenken utløper av seg selv.\n\n'
        f'Bruker du to-faktor, gjelder den fortsatt ved innlogging.\n\n'
        f'Spørsmål? Svar på denne e-posten, eller skriv til {SUPPORT_EPOST}.\n'
    )

    try:
        EmailMessage(
            subject='Nytt passord i Sanitetsportalen',
            body=kropp,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
            reply_to=[SUPPORT_EPOST],
        ).send(fail_silently=False)
        return True
    except Exception:
        logger.warning('Kunne ikke sende reset-lenke til bruker %s', user.pk,
                       exc_info=True)
        return False
