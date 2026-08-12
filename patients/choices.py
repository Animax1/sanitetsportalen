"""Kanoniske verdimengder for pasientregistreringens kliniske felt.

Feltene er nedtrekkslister (og radioknapper for ``grovsortering``) i
``templates/patients/index.html``. Fram til nå ble verdimengden håndhevet
**kun** i nettleseren: API-et tok imot og lagret hva som helst. En klient som
gikk utenom grensesnittet kunne dermed legge fritekst — i verste fall navn
eller fødselsnummer — inn i felt som skal ha et fast, ikke-identifiserende
verdisett.

Denne modulen er sannheten om hvilke verdier som er lov. ``views.py``
validerer mot den ved både opprettelse og oppdatering.

Verdiene speiles i skjemaet i ``index.html``. ``tests_choices.py`` leser
malen og feiler hvis de to kommer i utakt, slik at en endring i skjemaet
ikke stilltiende gjør data uvaliderbare (eller motsatt: gjør at et lovlig
valg i grensesnittet blir avvist av API-et).

Se ``docs/PERSONVERN_DOKUMENTASJON.md`` A.6 og A.12 for personvernbegrunnelsen.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

# ── Verdimengder ─────────────────────────────────────────────────────────────
# Rekkefølgen speiler skjemaet, slik at diffing mot malen er lesbar.

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
)

ARSAK = (
    'Rus',
    'Fall',
    'Vold',
    'Moshpit',
    'Underliggende sykdom',
    'Ulykke',
    'Brann',
    'Annet',
    'Ukjent',
)

TRANSPORT = (
    'Gående',
    'Lag',
    'Mannskapsbil',
    'Beredskapsambulanse',
)

# Radioknapper i skjemaet, ikke <select>.
GROVSORTERING = (
    'Grønn',
    'Gul',
    'Rød',
)

PLASSERING = (
    'Grønn sone',
    'Gul sone',
    'Behandling 1',
    'Behandling 2',
    'Behandling 3',
    'Behandling 4',
    'Behandling 5',
    'Akutt 1',
    'Akutt 2',
    'Akutt 3',
    'Akutt 4',
    'Obs 1',
    'Obs 2',
    'Obs 3',
    'Obs 4',
    'Obs 5',
    'Obs 6',
    'Obs 7',
    'Obs 8',
    'Obs 9',
    'Obs 10',
    'Obs 11',
    'Obs 12',
    'Obs 13',
    'Obs 14',
    'Obs 15',
    'Obs 16',
    'Obs 17',
    'Obs 18',
    'Obs 19',
    'Obs 20',
)

UTSKREVET_TIL = (
    'Hjem/park',
    'Forlatt stedet',
    'LV',
    'Sykehus',
    'Skadepol',
)

# Ja/Nei-flagg. ``journal`` registrerer om det er ført journal i helse-
# tjenestens ordinære journalsystem — feltet inneholder ikke journalinnhold.
# ``lege`` registrerer om lege var involvert, ikke hvilken lege.
JA_NEI = ('Ja', 'Nei')

LEGE = JA_NEI
MEDISINER = JA_NEI
JOURNAL = JA_NEI


#: Felt som valideres mot fast verdimengde. Tom streng er alltid tillatt —
#: feltet er da ikke satt ennå, hvilket er normalt tidlig i et pasientforløp.
CHOICE_FIELDS: dict[str, tuple[str, ...]] = {
    'problemstilling': PROBLEMSTILLING,
    'arsak': ARSAK,
    'transport': TRANSPORT,
    'grovsortering': GROVSORTERING,
    'plassering': PLASSERING,
    'utskrevet_til': UTSKREVET_TIL,
    'lege': LEGE,
    'medisiner': MEDISINER,
    'journal': JOURNAL,
}

# Oppslag som sett gir O(1)-sjekk og unngår å bygge settet på nytt per request.
_ALLOWED: dict[str, frozenset[str]] = {
    field: frozenset(values) for field, values in CHOICE_FIELDS.items()
}


def validate_patient_choice_fields(data):
    """Valider at kliniske dropdown-felt kun inneholder tillatte verdier.

    Muterer ``data`` in-place (trimmer whitespace), på samme måte som
    ``validate_patient_time_fields``. Felt som ikke er med i payloaden røres
    ikke — det gjør delvise oppdateringer (PATCH-lignende PUT) trygge.

    Tom streng og ``None`` normaliseres til ``''`` og godtas: feltet er da
    ikke utfylt ennå.

    Kaster ``ValidationError`` med samtlige feil samlet, slik at klienten får
    vite om alle problemene i én runde i stedet for én om gangen.
    """
    feil = []

    for field, allowed in _ALLOWED.items():
        if field not in data:
            continue

        raw = data[field]
        value = '' if raw is None else str(raw).strip()

        if value == '':
            data[field] = ''
            continue

        if value not in allowed:
            feil.append(
                f'{field}: «{value}» er ikke en gyldig verdi. '
                f'Tillatte verdier: {", ".join(CHOICE_FIELDS[field])}.'
            )
            continue

        data[field] = value

    if feil:
        raise ValidationError(feil)

    return data
