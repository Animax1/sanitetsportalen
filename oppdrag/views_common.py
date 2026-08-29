"""Delte hjelpere for oppdragsmodulens views."""
from __future__ import annotations

import hashlib
import json

from django.utils import timezone

from . import choices, services


def json_body(request):
    """Parse JSON-kroppen, eller returner tom dict."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


def etag_for(rader) -> str:
    """ETag over en liste av sammenlignbare tupler.

    Samme mønster som navneregistrene: sha256 brukes kun til identitet, ikke
    sikkerhet, og kortes til 16 tegn for å holde headeren kompakt.
    """
    raa = str(sorted(rader))
    return '"v1:' + hashlib.sha256(raa.encode('utf-8')).hexdigest()[:16] + '"'


def er_enhetskonto(user) -> bool:
    """True hvis kontoen er knyttet til en `Enhet`.

    **Dette, og ikke tilgangsnivået, avgjør hvilket grensesnitt kontoen får.**
    Å velge skjerm på «er nivået nøyaktig `skriv_handling`» ville brukt et
    ordnet nivå som en identitet — samme feil som §2.3 i rollemodellnotatet
    beskriver. Stigen sier at `skriv_full` dekker `skriv_handling`, så det
    oppslaget ville vært galt i det noen fikk begge.

    Koblingen gir ingen tilgang i seg selv; den avgjør bare hva som er nyttig
    å vise.
    """
    return getattr(user, 'enhet', None) is not None


def oppdrag_til_dict(oppdrag, *, for_enhet: bool = False) -> dict:
    """Serialiser ett oppdrag.

    ``for_enhet=True`` **utelater fritekst når oppdraget er avsluttet**. Det er
    en av de to skjulereglene, og den håndheves her — i serverens svar — ikke i
    nettleseren. Skjules teksten i JS, ligger den fortsatt i responsen, og en
    bil som blir stående ulåst er nettopp scenarioet regelen finnes for.
    """
    data = {
        'id': oppdrag.pk,
        # Nummeret man sier på samband. `id` er databasenøkkelen og skal ikke
        # vises — den er global og hopper mellom år.
        'nummer': oppdrag.oppdragsnummer,
        'enhet_id': oppdrag.enhet_id,
        'enhet_navn': oppdrag.enhet.navn,
        'problemstilling': oppdrag.problemstilling,
        'hastegrad': oppdrag.hastegrad,
        'lokasjon_id': oppdrag.lokasjon_id,
        'lokasjon_navn': oppdrag.lokasjon.navn,
        'status': oppdrag.status,
        'status_navn': oppdrag.get_status_display(),
        'opprettet': oppdrag.created_at.isoformat(),
        'historikk_fra': (oppdrag.historikk_fra.isoformat()
                          if oppdrag.historikk_fra else None),
    }
    skjul_fritekst = for_enhet and oppdrag.status == choices.TERMINAL
    data['fritekst'] = '' if skjul_fritekst else oppdrag.fritekst
    if for_enhet:
        # «Neste»-knappen vet hvilken overgang den utfører fordi serveren sier
        # det her — JS-en har ingen egen kopi av kjeden å komme i utakt med.
        neste = services.neste_i_kjeden(oppdrag.status)
        data['neste_overgang'] = neste
        data['neste_navn'] = choices.STATUS_NAVN.get(neste) if neste else None
    return data


def melding_til_dict(melding) -> dict:
    return {
        'id': melding.pk,
        'status': melding.status,
        'status_navn': melding.get_status_display(),
        'tidspunkt': melding.tidspunkt.isoformat(),
        'meldt_av': getattr(melding.meldt_av, 'username', '') or '',
        'forsinket': melding.forsinket,
        'automatisk': melding.automatisk,
        'korrigerer': melding.korrigerer_id,
    }


def bytte_til_dict(bytte) -> dict:
    return {
        'id': bytte.pk,
        'fra_enhet': bytte.fra_enhet.navn,
        'til_enhet': bytte.til_enhet.navn,
        'tidspunkt': bytte.created_at.isoformat(),
        'byttet_av': getattr(bytte.byttet_av, 'username', '') or '',
    }


def naa():
    return timezone.now()
