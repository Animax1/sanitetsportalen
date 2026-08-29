"""Innlogging som tåler at brukernavnet skrives litt annerledes enn det lagres.

Brukernavnet velges av admin, ikke av brukeren selv — det er nøkkelen i
auditloggen og i koblingen til førstehjelper-/helsepersonellregisteret, og en
fast konvensjon (`fornavn.etternavn`) er det som gjør loggen lesbar. Men da må
brukeren gjette skrivemåten på et navn de ikke har valgt.

**To ting kan avvike uten at noen ser det:**

* **Store bokstaver.** Tastaturet på mobil setter automatisk stor forbokstav,
  så `kari.nordmann` blir `Kari.nordmann`. `iexact` dekker det på PostgreSQL,
  men **ikke på SQLite for annet enn ASCII** — der gir `Ø` mot lagret `ø` null
  treff. Offline-modus kjører SQLite.
* **Unicode-normalform.** `å` finnes som ett tegn (NFC) og som `a` pluss
  kombinerende ring (NFD). Limer man inn brukernavnet fra en melding, kan man
  få NFD der databasen har NFC. Strengene ser identiske ut på skjermen.
  (`æ` og `ø` dekomponerer ikke — de er egne bokstaver — så feilen rammer navn
  med `å`.)

**Tvetydighet slår aldri ut i feil konto.** Finnes det flere kontoer som kun
skiller seg på skrivemåte, faller oppslaget tilbake til nøyaktig treff. Da
oppfører systemet seg som før for akkurat de kontoene, i stedet for å gjette
hvem som mente hva. En bruker som må skrive navnet sitt nøyaktig er et
irritasjonsmoment; feil konto er et sikkerhetsbrudd.
"""
import logging

from django.contrib.auth.backends import ModelBackend

from .brukernavn import normaliser, oppslagsnokkel
from .models import CustomUser

logger = logging.getLogger(__name__)

#: Hvor mange kontoer siste utvei sammenligner i Python. Den kjører kun når
#: begge databaseoppslagene bommet — altså på et innloggingsforsøk som ellers
#: ville feilet — og portalen har et tosifret antall kontoer. Taket finnes
#: likevel, slik at steget ikke stille blir dyrt den dagen tallet vokser.
SKANN_TAK = 500


def finn_kandidater(username):
    """Kontoer som matcher brukernavnet, i tre stadig bredere steg.

    Rekkefølgen er billigst først: to indekserte oppslag, og først om begge
    bommer et Python-side sammenligning som tåler at *lagret* verdi har en
    annen normalform.

    **Modulfunksjon, ikke metode, fordi `login_view` må bruke den samme.**
    Viewet slo tidligere opp kontoen med nøyaktig treff for å avgjøre
    kontolås og telle feilede forsøk, mens `authenticate` brukte dette
    oppslaget. To regler for «hvilken konto er dette» ga en hullete lås:
    skrev man brukernavnet med annen skrivemåte, fant viewet ingen konto,
    telleren sto stille, og kontoen ble aldri låst — mens innlogging med
    riktig passord fortsatt gikk gjennom.
    """
    norm = normaliser(username)
    nokkel = oppslagsnokkel(username)

    # 1. Som før: databasens egen ufølsomhet. Dekker unicode på Postgres.
    treff = list(CustomUser.objects.filter(username__iexact=norm)[:2])
    if treff:
        return treff

    # 2. Nøyaktig treff på oppslagsformen. Dekker SQLite + unicode, og
    #    NFD-inndata mot NFC-lagret verdi, siden begge er normalisert her.
    treff = list(CustomUser.objects.filter(username=nokkel)[:2])
    if treff:
        return treff

    # 3. Siste utvei: lagret verdi kan selv være unormalisert, og da hjelper
    #    ingen spørring — normaliseringen må skje på begge sider. Kontoer
    #    opprettet før normaliseringen ble innført er nettopp det.
    antall = CustomUser.objects.count()
    if antall > SKANN_TAK:
        logger.warning(
            'Innlogging: hopper over normaliseringsskann, %s kontoer '
            'overstiger taket på %s.', antall, SKANN_TAK)
        return []
    return [
        bruker for bruker in CustomUser.objects.all()
        if oppslagsnokkel(bruker.username) == nokkel
    ][:2]


def finn_konto(username):
    """Den ene kontoen brukernavnet peker på, eller ``None``.

    Brukes av `login_view` til kontolås og telling av feilede forsøk. Er den
    tvetydig, returneres ``None`` — samme forsiktighet som i `authenticate`.
    """
    treff = finn_kandidater(username)
    return treff[0] if len(treff) == 1 else None


class CaseInsensitiveModelBackend(ModelBackend):
    """``ModelBackend``, men brukernavnet slås opp tolerant for skrivemåte."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(CustomUser.USERNAME_FIELD)
        if username is None or password is None:
            return None

        treff = finn_kandidater(username)

        if len(treff) == 1:
            user = treff[0]
        elif len(treff) > 1:
            # Flere kontoer skiller seg kun på skrivemåte. Krev nøyaktig
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
