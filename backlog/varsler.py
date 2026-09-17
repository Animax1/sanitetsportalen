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

#: Varseltypene. Brukes til dedup og et framtidig filter i bjella.
KIND = 'backlog_nytt_innspill'
KIND_KOMMENTAR = 'backlog_ny_kommentar'


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


def _tradens_folk(innspill, unntatt):
    """Kontoene som har skrevet i tråden — forfatteren og de som har kommentert.

    **Ikke «alle som kan lese», og ikke «alle som kan løse».** En kommentar er
    en replikk i en samtale, og den angår dem som er i samtalen. Varsler man
    bredere, blir tråden til støy for folk som ikke har spurt om noe; varsler
    man smalere — bare forfatteren — går et svar fra forfatteren aldri tilbake
    til den som spurte.
    """
    from accounts.models import CustomUser

    ider = {innspill.opprettet_av_id}
    ider |= set(innspill.kommentarer.values_list('opprettet_av_id', flat=True))
    ider -= {None, getattr(unntatt, 'pk', None)}
    return CustomUser.objects.filter(pk__in=ider)


def meld_ny_kommentar(kommentar) -> int:
    """Varsle dem som er i tråden. Returnerer antall varsler som ble opprettet.

    Kaster aldri, av samme grunn som `meld_nytt_innspill`: kommentaren er
    skrevet, og den skal ikke gå tapt fordi bjella feilet.
    """
    try:
        innspill = kommentar.innspill
        antall = 0
        for bruker in _tradens_folk(innspill, kommentar.opprettet_av):
            varsel = notify(
                bruker,
                module_slug='backlog',
                kind=KIND_KOMMENTAR,
                title=f'Ny kommentar: {innspill.tittel}'[:120],
                # Teksten er med fordi den ofte *er* hele varselet — «hvilken
                # nettleser?» besvares uten å åpne siden. `notify()`
                # dedupliserer på meldingen, så to ulike kommentarer gir to
                # varsler mens et dobbelttrykk gir ett.
                message=f'{kommentar.opprettet_av_navn or "ukjent"}: '
                        f'{kommentar.tekst}'[:500],
                url='/backlog/',
            )
            if varsel is not None:
                antall += 1
        return antall
    except Exception:
        logger.exception('backlog: kunne ikke varsle om kommentar %s', kommentar.pk)
        return 0
