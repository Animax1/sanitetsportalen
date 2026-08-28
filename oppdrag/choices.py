"""Kanoniske verdimengder for oppdragsmodulen.

Samme rolle som ``patients/choices.py``: verdimengden håndheves server-side,
ikke bare i nettleseren, slik at en klient som går utenom grensesnittet ikke
kan legge fritekst i felt som skal ha et fast, ikke-identifiserende verdisett.

**Listene er bevisst ikke delt med pasientmodulen.** Problemstillingene tar
utgangspunkt i den lista, men et oppdrag er ikke en pasient. Den dagen den ene
skal endres uten den andre, er en delt konstant det som står i veien — og
sammenblandingen ville dessuten koblet to moduler som ellers ikke kjenner
hverandre.

``lokasjon`` står ikke her. Den er en egen tabell fordi den beskriver stedene
på *dette* arrangementet og skal kunne endres av admin uten deploy. Skillet er
det samme som mellom `PROBLEMSTILLING` og navneregistrene i pasientmodulen:
faglige verdimengder i kode, arrangementsdata i databasen.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

# ── Verdimengder ─────────────────────────────────────────────────────────────

PROBLEMSTILLING = (
    'Stor ytre blødning',
    'Bevisstløs',
    'Nedsatt bevissthet',
    'Pustevansker',
    'Brystsmerter',
    'Magesmerter',
    'Blodsukker forstyrrelse',
    'Kramper',
    'Temperatur forstyrrelse',
    'Brannskade',
    'Skade bein/fot',
    'Skade arm/håndledd',
    'Skade skulder/kragebein',
    'Skade overkropp',
    'Skade nakke',
    'Skade hode',
    'Skade øye/nese/øre/tann',
    'Psykiatri',
    'Annen sykdom',
    'Annen skade',
    'Mistanke overgrep',
    'Transport',
)

#: AMK-inndelingen, ikke fargenavn. Fargekoding i grensesnittet er en
#: presentasjonsdetalj; navnet skal være det personellet faktisk sier.
HASTEGRAD = (
    'Akutt',
    'Haster',
    'Vanlig',
)


# ── Statuser ─────────────────────────────────────────────────────────────────
#
# `venter` er ikke en status noen ba om — den følger av at en enhet skal kunne
# ha ventende oppdrag. Skal et oppdrag kunne være tildelt uten å være
# påbegynt, kan ikke 113 sette `rykker_ut` ved oppretting; da ville
# responstiden løpt fra et tidspunkt ingen i bilen hadde sett oppdraget.

VENTER = 'venter'
RYKKER_UT = 'rykker_ut'
FREMME = 'fremme'
AVREIST = 'avreist'
LEVERER = 'leverer'
LEDIG = 'ledig'

STATUS_VALG: tuple[tuple[str, str], ...] = (
    (VENTER, 'Venter'),
    (RYKKER_UT, 'Rykker ut'),
    (FREMME, 'Fremme'),
    (AVREIST, 'Avreist'),
    (LEVERER, 'Leverer'),
    (LEDIG, 'Ledig'),
)

STATUS_NAVN: dict[str, str] = dict(STATUS_VALG)

#: Statusen som avslutter et oppdrag. Enheten er ledig når den ikke har et
#: oppdrag i en ikke-terminal status — det utledes, det lagres ikke.
TERMINAL = LEDIG

#: Rekkefølgen «neste»-knappen følger. `ledig` står ikke her: den er utgang
#: fra enhver status, ikke et ledd i kjeden.
KJEDEN: tuple[str, ...] = (VENTER, RYKKER_UT, FREMME, AVREIST, LEVERER)


CHOICE_FIELDS: dict[str, tuple[str, ...]] = {
    'problemstilling': PROBLEMSTILLING,
    'hastegrad': HASTEGRAD,
}

_ALLOWED: dict[str, frozenset[str]] = {
    felt: frozenset(verdier) for felt, verdier in CHOICE_FIELDS.items()
}


def validate_oppdrag_choice_fields(data):
    """Valider nedtrekksfeltene mot verdimengdene. Muterer ``data`` in-place.

    Felt som ikke er med i payloaden røres ikke, slik at delvise oppdateringer
    er trygge. **Tom streng godtas ikke her**, i motsetning til
    pasientmodulen: der er et tomt felt normalt tidlig i forløpet, mens et
    oppdrag uten problemstilling eller hastegrad ikke er et oppdrag noen kan
    rykke ut på.

    Kaster ``ValidationError`` med samtlige feil samlet, slik at klienten får
    vite om alle problemene i én runde.
    """
    feil = []

    for felt, tillatt in _ALLOWED.items():
        if felt not in data:
            continue

        raa = data[felt]
        verdi = '' if raa is None else str(raa).strip()
        data[felt] = verdi

        if verdi not in tillatt:
            feil.append(
                f'Ugyldig verdi for «{felt}»: {verdi!r}. '
                f'Tillatt: {", ".join(tillatt)}'
            )

    if feil:
        raise ValidationError(feil)

    return data
