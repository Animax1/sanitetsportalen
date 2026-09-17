"""Varsel til dem som kan gjøre noe med et nytt innspill (André, 17. sep. 2026).

**Hvem som varsles er ikke «admin», det er «de som kan løse».** Å varsle alle
med lesetilgang ville gjort bjella til støy for dem som bare melder inn — og en
bjelle man slår av, varsler ikke den gangen det haster. Mottakerne er derfor
kontoene med `skriv_leder` på `backlog`, pluss global admin, som står utenfor
modulaksen og har toppen av stigen uansett.

**Innsenderen varsles ikke om sitt eget.** Et varsel om noe man nettopp skrev
er den korteste veien til å slutte å lese varsler.

`notify()` er den ene porten: den sjekker modultilgang selv, dedupliserer på
(bruker, kind, melding) siste 24 timer, og **kaster aldri videre til kalleren**
— et innspill skal ikke gå tapt fordi varselet feilet. Denne fila fanger derfor
også bredt rundt hele utsendingen: den er en sideeffekt av innmeldingen, ikke
en del av den.
"""
from __future__ import annotations

import logging

from core.notifications import notify

logger = logging.getLogger(__name__)

#: Varseltypen. Brukes til dedup og et framtidig filter i bjella.
KIND = 'backlog_nytt_innspill'


def _mottakere(unntatt):
    """Kontoene som kan løse et innspill, minus den som meldte det inn."""
    from accounts.models import CustomUser, ModulTilgang

    ider = set(
        ModulTilgang.objects
        .filter(modul_slug='backlog', nivaa='skriv_leder')
        .values_list('bruker_id', flat=True)
    )
    admin_ider = set(
        CustomUser.objects.filter(role='admin', is_active=True)
        .values_list('pk', flat=True)
    )
    alle = (ider | admin_ider) - {getattr(unntatt, 'pk', None)}
    return CustomUser.objects.filter(pk__in=alle)


def meld_nytt_innspill(innspill) -> int:
    """Varsle dem som kan løse. Returnerer antall varsler som ble opprettet.

    Kaster aldri. Teksten bærer **tittelen**, ikke bare «nytt innspill»: det er
    tittelen som avgjør om man går og ser nå eller i morgen — og `notify()`
    deduplikerer på meldingen, så to ulike innspill gir to varsler mens et
    dobbelttrykk gir ett.
    """
    try:
        antall = 0
        for bruker in _mottakere(innspill.opprettet_av):
            varsel = notify(
                bruker,
                module_slug='backlog',
                kind=KIND,
                title=f'Nytt innspill: {innspill.type}',
                message=f'{innspill.tittel} — meldt inn av '
                        f'{innspill.opprettet_av_navn or "ukjent"}',
                url='/backlog/',
            )
            if varsel is not None:
                antall += 1
        return antall
    except Exception:
        logger.exception('backlog: kunne ikke varsle om innspill %s', innspill.pk)
        return 0
