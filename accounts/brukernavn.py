"""Normalisering av brukernavn, delt mellom oppretting og innlogging.

**Hvorfor dette finnes.** Brukernavnet velges av admin og skrives inn igjen av
brukeren — ofte limt inn fra en melding, ikke tastet. Da kan de to strengene se
helt like ut på skjermen og likevel være forskjellige for databasen:

* **Ulik Unicode-normalform.** `å` finnes både som ett tegn (U+00E5, NFC) og
  som `a` + kombinerende ring (U+0061 U+030A, NFD). macOS produserer NFD i en
  del sammenhenger, så «kopier brukernavnet og lim det inn» er nok til å bomme.
  Målt: `å` og `Å` dekomponerer, `æ` og `ø` gjør det ikke — de er egne
  bokstaver, ikke bokstav pluss aksent. Feilen rammer altså navn med `å`, og
  ikke navn med bare `æ` eller `ø`.
* **Ulik skrivemåte på store bokstaver.** Dekket av `iexact` på PostgreSQL,
  men **ikke på SQLite** for annet enn ASCII: der gir `Ø` mot lagret `ø` null
  treff. Offline-modus kjører SQLite, så det er ikke en teoretisk forskjell.

Normalformen er NFKC, samme som Djangos egen ``AbstractBaseUser.normalize_username``.
Den kalles ikke i denne kodebasen — brukere opprettes gjennom skjemaer, ikke
gjennom ``UserManager.create_user`` — så normaliseringen må skje her.
"""
from __future__ import annotations

import unicodedata


def normaliser(navn: str | None) -> str:
    """NFKC-normaliser og trim. Beholder store bokstaver.

    Brukes ved lagring, slik at det som står i databasen har én form.
    """
    return unicodedata.normalize('NFKC', navn or '').strip()


def oppslagsnokkel(navn: str | None) -> str:
    """Formen to brukernavn skal sammenlignes på.

    ``casefold()`` framfor ``lower()``: den er laget for nettopp dette, og
    håndterer tilfeller ``lower()`` ikke gjør. For norsk er de like, men det
    koster ingenting å bruke den riktige.
    """
    return normaliser(navn).casefold()
