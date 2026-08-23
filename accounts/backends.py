"""Innlogging som ikke bryr seg om store og små bokstaver i brukernavnet.

Brukernavnet velges av admin, ikke av brukeren selv — det er nøkkelen i
auditloggen og i koblingen til førstehjelper-/helsepersonellregisteret, og en
fast konvensjon (`fornavn.etternavn`) er det som gjør loggen lesbar. Men da må
brukeren gjette skrivemåten på et navn de ikke har valgt.

Verre på mobil: tastaturet setter automatisk stor forbokstav i tekstfelt. En
konto som heter `kari.nordmann` blir da `Kari.nordmann` ved innlogging, og
Postgres skiller på det. Brukeren får «feil brukernavn eller passord» — uten
noen antydning om hva som er galt, fordi meldingen med vilje ikke røper
hvilket av de to som feilet.

**Tvetydighet slår aldri ut i feil konto.** Finnes det flere kontoer som kun
skiller seg på store bokstaver, faller oppslaget tilbake til nøyaktig treff.
Da oppfører systemet seg som før for akkurat de kontoene, i stedet for å gjette
hvem som mente hva. Det er den trygge retningen: en bruker som må skrive navnet
sitt nøyaktig er et irritasjonsmoment, mens feil konto er et sikkerhetsbrudd.
"""
from django.contrib.auth.backends import ModelBackend

from .models import CustomUser


class CaseInsensitiveModelBackend(ModelBackend):
    """``ModelBackend``, men brukernavnet slås opp uten hensyn til store bokstaver."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(CustomUser.USERNAME_FIELD)
        if username is None or password is None:
            return None

        treff = list(CustomUser.objects.filter(username__iexact=username)[:2])

        if len(treff) == 1:
            user = treff[0]
        elif len(treff) > 1:
            # Flere kontoer skiller seg kun på store bokstaver. Krev nøyaktig
            # treff heller enn å velge en av dem.
            user = CustomUser.objects.filter(username=username).first()
            if user is None:
                return None
        else:
            # Ingen treff. Kjør likevel hasheren én gang, slik at svartiden
            # ikke røper om brukernavnet finnes — samme grunn som at
            # feilmeldingen ikke gjør det.
            CustomUser().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
