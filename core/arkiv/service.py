"""Arkiv-tjenester: signatur, integritetssjekk og kollaps.

Modul-agnostisk. Alt som er spesifikt for hva som arkiveres, kommer fra
handleren — se ``core/arkiv/handlers.py`` for arbeidsdelingen.
"""
from __future__ import annotations

import hashlib
import json
import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _kanonisk_sha256(payload: dict) -> str:
    """SHA-256 over kanonisk JSON.

    ``sort_keys=True`` gjør at nøkkelrekkefølgen i dicten er irrelevant, og
    ``ensure_ascii=False`` at norske tegn hashes som seg selv i stedet for som
    escape-sekvenser. **Begge flaggene er del av signaturen** — endres ett av
    dem, kan ingen eksisterende arkiv verifiseres igjen.
    """
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def beregn_sha256(handler, arkiv, rader: list[dict] | None = None) -> str:
    """Signatur over radnivået. Handleren bestemmer payloaden."""
    if rader is None:
        rader = handler.rad_dicts(arkiv)
    return _kanonisk_sha256(handler.sha_payload(arkiv, rader))


def beregn_aggregat_sha256(handler, arkiv, aggregat: dict) -> str:
    """Signatur over det frosne aggregatet."""
    return _kanonisk_sha256(handler.aggregat_sha_payload(arkiv, aggregat))


def verifiser(handler, arkiv) -> bool:
    """Er arkivet tuklet med? Returnerer True hvis signaturen ikke stemmer.

    Velger riktig signatur ut fra tilstand: etter kollaps finnes ikke radene
    lenger, og ``sha256`` — som er beregnet over dem — kan aldri verifiseres
    igjen. Da sjekkes det frosne aggregatet i stedet.

    Et arkiv uten lagret signatur regnes som ikke-tuklet. Det gjelder arkiver
    fra før signaturen ble innført, og å melde tukling på dem ville vært
    misvisende.
    """
    if arkiv.er_kollapset:
        if not arkiv.aggregat_sha256:
            return False
        naa = beregn_aggregat_sha256(handler, arkiv, arkiv.aggregat or {})
        return naa != arkiv.aggregat_sha256

    if not arkiv.sha256:
        return False
    return beregn_sha256(handler, arkiv) != arkiv.sha256


def kollaps(handler, arkiv) -> int:
    """Frys statistikken og slett radnivået permanent.

    **Irreversibel.** Etter dette finnes ingen opplysninger om enkeltpersoner
    i arkivet — kun aggregerte tall som ikke lar seg føre tilbake.

    Idempotent: et allerede kollapset arkiv røres ikke, og funksjonen
    returnerer 0.

    Aggregatet beregnes *før* transaksjonen åpnes. Det er med vilje: går
    beregningen galt, har vi ikke slettet noe ennå.

    Returnerer antall slettede rader.
    """
    if arkiv.er_kollapset:
        return 0

    aggregat = handler.bygg_aggregat(arkiv)

    with transaction.atomic():
        antall = handler.slett_rader(arkiv)

        arkiv.aggregat = aggregat
        arkiv.aggregat_sha256 = beregn_aggregat_sha256(handler, arkiv, aggregat)
        arkiv.kollapset_at = timezone.now()
        arkiv.save(update_fields=['aggregat', 'aggregat_sha256', 'kollapset_at'])

    logger.info(
        'core.arkiv: kollapset modul=%s arkiv_id=%s, slettet %d rader',
        handler.slug, arkiv.pk, antall,
    )
    return antall


def har_backup_etter(handler, tidspunkt) -> bool:
    """Finnes det en backup av modulens arkiv tatt etter ``tidspunkt``?

    Sperre før kollaps: en backup laget etter at arkivet ble opprettet
    inneholder arkivet, og gjør den irreversible slettingen gjenopprettbar.

    Har handleren ingen ``backup_slug``, finnes ingen sperre — da returneres
    False, slik at kollaps må tvinges bevisst i stedet for å skje fritt.
    """
    if not handler.backup_slug:
        return False

    from patients.models import Backup
    return Backup.objects.filter(
        module_slug=handler.backup_slug,
        created_at__gt=tidspunkt,
    ).exists()
