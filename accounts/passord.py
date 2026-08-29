"""Generering av midlertidige passord.

Ligger her og ikke inline i viewene fordi det skjer to steder — ved
opprettelse av en konto uten invitasjon, og ved «tilbakestill passord» i
brukeradmin — og de to må gi samme kvalitet.

**Alfabetet utelater tegn som ligner hverandre.** Et midlertidig passord blir
lest av en skjerm og tastet inn et annet sted, ofte på en telefon: `0` mot `O`,
`1` mot `l` mot `I`. Feiltastingen er umulig å skille fra «feil passord», og
kontoen låses etter fem forsøk mens brukeren tror hen skriver riktig.

Kostnaden er ubetydelig: 56 tegn i stedet for 62 gir 69,7 bit i stedet for
71,4 over tolv tegn. Passordet skal uansett byttes ved første innlogging.
"""
import secrets
import string

#: Tegn som ligner et annet tegn i vanlige skrifttyper.
FORVEKSLINGSTEGN = '0O1lI'

ALFABET = ''.join(
    ch for ch in (string.ascii_letters + string.digits)
    if ch not in FORVEKSLINGSTEGN
)

LENGDE = 12


def lag_midlertidig_passord() -> str:
    """Et tilfeldig passord uten tegn som kan feillesest."""
    return ''.join(secrets.choice(ALFABET) for _ in range(LENGDE))
