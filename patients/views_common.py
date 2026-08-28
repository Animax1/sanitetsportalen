"""Delte hjelpere for view-modulene i patients-appen.

``views.py`` ble delt opp i views_patients, views_registre, views_stats og
views_arkiv (N13.3). Det som brukes på tvers ligger her, slik at modulene
ikke trenger å importere fra hverandre.
"""
import json
from datetime import datetime

# Roller med skrivetilgang til pasienter
# `WRITE_ROLES` sto her fram til 28. aug. 2026. Den var én av fem kopier av
# rollelista (§2.6 i beslutningsnotatet), og skrivetilgang avgjøres nå av
# `har_tilgang(user, 'patients', 'skriv_full')` — ikke av hvilken rolle
# brukeren har.


def _json_body(request):
    """Parse JSON-body fra request, returner tom dict ved feil."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


def _ensure_pabegynt_not_before_inntid(patient):
    """Sikkerhetsnett: hvis pabegynt < inntid, juster pabegynt opp til inntid.

    Bakgrunn: `inntid` settes ofte fra klient-tid (nettleserens klokke) ved
    opprettelse, mens `pabegynt` stemples av server. Klient-klokker kan
    drive 1-5 min fra NTP-synkronisert server. Resultat: pabegynt < inntid,
    som gir negative ventetider i statistikken.

    Funksjonen muterer `patient` in-place og kaller ikke save().
    Returnerer True hvis pabegynt ble justert.
    """
    inntid = (patient.inntid or '').strip()
    pabegynt = (patient.pabegynt or '').strip()
    if not inntid or not pabegynt:
        return False
    fmt = '%d.%m.%Y %H:%M'
    try:
        t_inn = datetime.strptime(inntid, fmt)
        t_pab = datetime.strptime(pabegynt, fmt)
    except (ValueError, TypeError):
        return False  # Ugyldig format – latt valideringen ta det
    if t_pab < t_inn:
        patient.pabegynt = inntid
        return True
    return False


def _patient_to_dict(p, slettbare=None):
    """Konverter Patient-objekt til dict for JSON-respons.

    ``slettbare`` er pk-ene mottakeren kan hard-slette, ``None`` for «alle»
    (global admin). Flagget må komme fra serveren: om en pasient kan slettes
    avhenger av *hvem som opprettet den* og *når*, og ingen av delene finnes
    i klienten. Uten det kunne grensesnittet bare gjette — og en sletteknapp
    som gir 403 er samme feil som «Ny pasient» for en `les`-bruker.
    """
    return {
        'kan_slettes': slettbare is None or p.id in slettbare,
        'id': p.id,
        'patient_nr': p.pasientnummer,
        'pasientnummer': p.pasientnummer,
        'year': p.year,
        'problemstilling': p.problemstilling,
        'arsak': p.arsak,
        'transport': p.transport,
        'inntid': p.inntid,
        'grovsortering': p.grovsortering,
        'pabegynt': p.pabegynt,
        'plassering': p.plassering,
        'forstehjelper': (
            {'id': p.forstehjelper.id, 'name': p.forstehjelper.name}
            if p.forstehjelper else None
        ),
        'helsepersonell_ref': (
            {'id': p.helsepersonell_ref.id, 'name': p.helsepersonell_ref.name}
            if p.helsepersonell_ref else None
        ),
        'lege': p.lege,
        'medisiner': p.medisiner,
        'inn_obspost': p.inn_obspost,
        'ut_obspost': p.ut_obspost,
        'utskrevet': p.utskrevet,
        'utskrevet_til': p.utskrevet_til,
        'journal': p.journal,
        'created_at': p.created_at.strftime('%d.%m.%Y %H:%M') if p.created_at else '',
        'is_active': p.is_active,
    }


