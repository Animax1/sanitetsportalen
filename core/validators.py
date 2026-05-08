"""Felles validatorer for tids- og datofelter i sanitetsportalen.

Norsk standard: dd.mm.åååå tt:mm (f.eks. 19.04.2026 14:30)

Disse validatorene flyttes ut fra patients/services.py i fase 1 av
sanitetsportal-migreringen. patients/services.py re-eksporterer fortsatt
de samme navnene for bakoverkompatibilitet — ingen eksisterende kode må
endre imports før vi rydder opp i en senere fase.
"""
import re
from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone as djtz


# ── Tidsformat ───────────────────────────────────────────────────────────────

# Kun ett gyldig tidsformat aksepteres i hele portalen: dd.mm.åååå tt:mm
TIME_FORMAT = '%d.%m.%Y %H:%M'
TIME_FORMAT_HUMAN = 'dd.mm.åååå tt:mm'
_TIME_REGEX = re.compile(r'^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$')

# Tidsfelter på Patient som må valideres når de kommer inn fra klient.
# Beholdes her for bakoverkompatibilitet — patients re-eksporterer.
TIME_FIELDS = ('inntid', 'pabegynt', 'inn_obspost', 'ut_obspost', 'utskrevet')


# ── Lokal tid-helper ─────────────────────────────────────────────────────────
#
# Containere på Railway kjører i UTC. `datetime.now()` returnerer naiv
# server-lokaltid (UTC) og ignorerer Djangos TIME_ZONE-innstilling.
#
# Alle pasient-tidsstempler skal være i Europe/Oslo (samme TZ som frontend),
# så vi konverterer bevisst via Djangos timezone-API.

def now_local_str():
    """Returner naiv 'dd.mm.YYYY HH:MM'-streng i Djangos TIME_ZONE (Europe/Oslo).

    Brukes for ALLE auto-tidsstempler i portalen. Erstatter
    `datetime.now().strftime(...)` som tidligere ga UTC i produksjon.
    """
    return djtz.localtime(djtz.now()).strftime(TIME_FORMAT)


# ── Validatorer ──────────────────────────────────────────────────────────────

def validate_time_string(value, field_name=''):
    """Valider at tidsstreng er nettopp formatet dd.mm.åååå tt:mm.

    Tom streng / None er OK (feltet er ikke satt enda).
    Kaster ValidationError ved ugyldig format eller ugyldig dato.
    Returnerer en normalisert streng (trimmet) eller '' hvis input var tom.
    """
    if value is None:
        return ''
    s = str(value).strip()
    if s == '':
        return ''
    if not _TIME_REGEX.match(s):
        label = f'{field_name}: ' if field_name else ''
        raise ValidationError(
            f'{label}Ugyldig tidsformat. Forventet {TIME_FORMAT_HUMAN} '
            f'(f.eks. 19.04.2026 14:30). Fikk: «{s}»'
        )
    try:
        datetime.strptime(s, TIME_FORMAT)
    except ValueError as exc:
        label = f'{field_name}: ' if field_name else ''
        raise ValidationError(
            f'{label}Ugyldig dato/tid «{s}» ({exc}). '
            f'Forventet {TIME_FORMAT_HUMAN}.'
        )
    return s


def validate_patient_time_fields(data):
    """Valider alle kjente tidsfelter i en dict av innkommende data.

    Muterer data in-place (normaliserer strenger). Kaster ValidationError
    hvis noen av feltene er ugyldige.

    NB: Funksjonen heter "validate_patient_time_fields" av historiske
    grunner — den er generisk og brukes også av andre apps med samme
    tidsfelt-konvensjon. Beholdes uendret for bakoverkompatibilitet.
    """
    for field in TIME_FIELDS:
        if field in data:
            data[field] = validate_time_string(data[field], field_name=field)
    return data


def parse_minutes(t1_str, t2_str):
    """Returner varighet i minutter mellom to 'dd.mm.YYYY HH:MM'-strenger.

    Aksepterer også ISO-formatene 'YYYY-MM-DDTHH:MM' og 'YYYY-MM-DD HH:MM'
    for inngående data. Returnerer None ved ugyldig input eller hvis
    differansen er negativ / urimelig stor (> 48 timer).
    """
    for fmt in ('%d.%m.%Y %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            t1 = datetime.strptime(t1_str.strip(), fmt)
            t2 = datetime.strptime(t2_str.strip(), fmt)
            diff = (t2 - t1).total_seconds() / 60
            if 0 <= diff <= 2880:
                return diff
            break
        except (ValueError, AttributeError):
            continue
    return None
