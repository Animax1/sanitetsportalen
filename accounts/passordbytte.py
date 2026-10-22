"""Admin krever at en bruker bytter passordet sitt (22. okt. 2026).

André, etter Railway-hendelsen 22. okt.: «Jeg må kunne tvinge passordbytte hos brukere av
portalen». Mekanismen fantes: ``must_change_password`` håndheves av
``accounts.middleware`` på hver forespørsel, og ``change_password_view`` er døra ut. Det som
manglet var en flate som satte flagget uten å lage et nytt passord — «Generer nytt
midlertidig passord» gjør begge deler, og da må admin dele ut et passord.

**Flagget alene er ikke nok.** Middlewaren slipper ingen videre, men en sesjon som alt er
innlogget lever til neste forespørsel — og en økt i kartet lever helt uavhengig. Derfor
``avslutt_alle_sesjoner``: brukeren logges ut overalt, og møter skjemaet ved neste innlogging.
Er passordet kjent av noen andre, er det nettopp den andre økten man vil ha borte.
"""
from __future__ import annotations

from .models import CustomUser
from .sesjoner import avslutt_alle_sesjoner


def krev(user) -> bool:
    """Sett ``must_change_password`` og logg brukeren ut. False uten passord å bytte.

    En konto uten brukbart passord er en invitasjon som ikke er tatt i bruk: brukeren
    setter sitt første passord gjennom lenken, og skjemaet for passordbytte krever det
    gamle — det finnes ikke. Å sette flagget ville låst kontoen i en dør uten håndtak.
    """
    if not user.has_usable_password():
        return False
    user.must_change_password = True
    user.save(update_fields=['must_change_password'])
    avslutt_alle_sesjoner(user)
    return True


def kontoer_for_alle(utenom):
    """Kontoene «Krev passordbytte for alle» gjelder — se ``_krev_passordbytte_alle``.

    Aktive, personlige kontoer. Frosne er utelatt fordi de alt er logget ut og ikke kommer
    inn; får de flagget, møter de skjemaet den dagen frysingen oppheves, uten at noen husker
    hvorfor. Kontoer uten passord filtreres av ``krev``, ikke her: ``has_usable_password``
    er en metode, ikke et felt.
    """
    return (CustomUser.objects
            .filter(is_active=True, er_delt_konto=False)
            .exclude(pk=utenom.pk)
            .order_by('pk'))
