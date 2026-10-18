"""Sladding av fritekst i etterkant — og registeret som holder den sladdet (18. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.9 (fase 7): admin skal kunne fjerne fritekst når en
helseopplysning eller et navn har havnet der det ikke skal. **KO først, så oppdrag og pasient.**

**Et register, som de andre** (`core/personsok.py`, `core/opprydding.py`): `core` kjenner ingen
modul ved navn. Hver modul melder inn sine frie felt fra `<app>/sladding.py` — hvilke modeller og
felt, hvordan man søker i dem, og hva «sladdet» betyr hos den. KO har alt begrepet «en linje som
er fjernet» (`ko.services.fjern`), og sladdingen der *er* den.

| Regel | Hvorfor |
|---|---|
| **Sladderegisteret (`core.Sladding`) har hva, hvem, når og hvorfor — aldri teksten** | Backupene beholder teksten: de er krypterte, ligger opptil 730 dager offsite og kan ikke redigeres. **En gjenoppretting tar teksten tilbake** — registeret er det som tar den bort igjen |
| **Gjenopprettingen kjører registeret før den melder ferdig**, i samme transaksjon | `core.backup.service.restore_backup`. Teksten skal aldri stå lesbar i basen etter en gjenoppretting, heller ikke et øyeblikk |
| **Registeret leses *før* gjenopprettingen og flettes inn etter** | En hel gjenoppretting erstatter også registeret. Uten flettingen ville en backup fra før sladdingen tatt med seg både teksten og sporet etter at den skulle bort |
| **Bare global admin, og hvert søk logges** (`SOK`, som personsøket) | Søket leser fritekst på tvers av alle portaler og vakter |
| **En grunn er påkrevd** | Sladding fjerner dokumentasjon. Hvorfor skal stå, og står i registeret — teksten gjør det ikke |
| **Kopiene sladdes med originalen** | En tekst som står frosset et annet sted (KOs vaktstatistikk, systemlinjene) er ikke borte fordi originalen er det. Handleren vet hvor dens kopier står |

Avviket mot backupene føres i personverndokumentet (A.14): kopien der forsvinner når
lagringstiden løper ut, ikke før.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MIN_TEGN = 2
MAKS_TREFF = 100
MAKS_GRUNN = 255
#: Det som står igjen der et felt ikke kan være tomt (en hendelse må ha en tittel).
SLADDET = '[Sladdet]'


@dataclass
class Funn:
    modell: str          # 'ko.logglinje'
    pk: int
    felt: str
    felt_navn: str
    tekst: str           # vises på siden, lagres aldri
    hvor: str = ''       # «H14 · Kamp 7 · Brann»
    tid: datetime | None = None


class BaseSladdHandler:
    """De frie feltene i én modul. Subklasses per modul."""

    slug: ClassVar[str] = ''
    etikett: ClassVar[str] = ''
    #: ``{'ko.logglinje': ('tekst',)}`` — modellene og feltene handleren eier. Registeret
    #: rutes på modellen, og et felt som ikke står her kan ikke sladdes.
    felt: ClassVar[dict[str, tuple[str, ...]]] = {}

    def sok(self, q: str) -> list[Funn]:
        raise NotImplementedError

    def sladd(self, modell: str, pk: int, felt: str, *, bruker) -> list[tuple[str, int, str]]:
        """Sladd feltet, med kopiene. Returnerer ``(modell, pk, felt)`` for hver rad som ble
        rørt — de havner i registeret. Kaster `ValidationError` om raden ikke finnes."""
        raise NotImplementedError

    def gjenta(self, rad) -> bool:
        """Sladd igjen etter en gjenoppretting (`rad` er `core.Sladding`). Idempotent.
        False når raden ikke finnes — da er det ingenting å sladde."""
        raise NotImplementedError


_REGISTER: dict[str, BaseSladdHandler] = {}


def register(handler: BaseSladdHandler) -> None:
    if not handler.slug:
        raise ValueError('Sladdehandler uten slug.')
    for modell in handler.felt:
        eier = for_modell(modell)
        if eier is not None and eier.slug != handler.slug:
            raise ValueError(f'{modell} er alt meldt inn av {eier.slug}.')
    _REGISTER[handler.slug] = handler


def all_handlers() -> list[BaseSladdHandler]:
    return sorted(_REGISTER.values(), key=lambda h: h.slug)


def for_slug(slug: str):
    return _REGISTER.get(slug)


def for_modell(modell: str):
    return next((h for h in _REGISTER.values() if modell in h.felt), None)


def clear_registry() -> None:
    """Bare for tester."""
    _REGISTER.clear()


def sok(q: str) -> list[dict]:
    """`[{'handler', 'funn', 'feil'}]` for hver kilde. Kaster aldri — som personsøket."""
    from core.admin_status import _scrub_secrets

    q = (q or '').strip()
    if len(q) < MIN_TEGN:
        return []
    ut = []
    for h in all_handlers():
        try:
            ut.append({'handler': h, 'funn': h.sok(q)[:MAKS_TREFF], 'feil': ''})
        except Exception as exc:  # noqa: BLE001 — én kilde skal ikke ta ned søket
            logger.exception('sladding: søket i %s feilet', h.slug)
            ut.append({'handler': h, 'funn': [], 'feil': _scrub_secrets(str(exc))})
    return ut


def registrer(rader, *, grunn: str, bruker, naa=None) -> None:
    """Før radene i registeret. Brukes av `sladd()` og av modulenes egne sletteinnganger
    (KOs «Fjern»), som har samme problem: en gjenoppretting tar teksten tilbake."""
    from core.models import Sladding

    naa = naa or timezone.now()
    av = bruker if bruker is not None and getattr(bruker, 'is_authenticated', False) else None
    for modell, pk, felt in rader:
        Sladding.objects.update_or_create(
            modell=modell, rad_id=pk, felt=felt,
            defaults={'grunn': grunn[:MAKS_GRUNN], 'av': av,
                      'av_navn': getattr(av, 'username', '') or '', 'sladdet_at': naa})


def sladd(kilde: str, modell: str, pk: int, felt: str, *, grunn: str, bruker, ip=None) -> int:
    """Sladd ett felt i én rad, med kopiene, og før det i registeret. Antall rader rørt."""
    from audit.models import AuditLog

    handler = for_slug(kilde)
    if handler is None or felt not in handler.felt.get(modell, ()):
        raise ValidationError('Feltet kan ikke sladdes herfra.')
    grunn = (grunn or '').strip()
    if not grunn:
        raise ValidationError('Skriv hvorfor teksten sladdes.')
    if len(grunn) > MAKS_GRUNN:
        raise ValidationError(f'Grunnen kan være høyst {MAKS_GRUNN} tegn.')
    with transaction.atomic():
        rader = handler.sladd(modell, pk, felt, bruker=bruker)
        registrer(rader, grunn=grunn, bruker=bruker)
        AuditLog.objects.create(
            table_name='core_sladding', record_id=pk, action='UPDATE',
            field_name=f'{modell}.{felt}'[:64], new_value=grunn, user=bruker, ip=ip)
    return len(rader)


# ── Gjenopprettingen ─────────────────────────────────────────────────────────

FELTENE = ('modell', 'rad_id', 'felt', 'grunn', 'av_id', 'av_navn', 'sladdet_at')


def les_registeret() -> list[dict]:
    """Registeret som det står nå, før en gjenoppretting rører det. Kaster aldri: i en tom
    base finnes ikke tabellen ennå, og da er det heller ingenting å huske."""
    from core.models import Sladding

    try:
        return list(Sladding.objects.values(*FELTENE))
    except Exception:  # noqa: BLE001
        logger.warning('sladding: registeret kunne ikke leses før gjenopprettingen',
                       exc_info=True)
        return []


def etter_gjenoppretting(for_gjenoppretting: list[dict]) -> int:
    """Flett inn registeret fra før gjenopprettingen, og sladd alt i det på nytt.

    Kalles av `restore_backup` inne i transaksjonen, etter `loaddata`. En rad som finnes i
    begge, beholdes som den sto før — den er nyest. En bruker som ikke finnes etter en hel
    gjenoppretting, blir `None`; navnet står.
    """
    from accounts.models import CustomUser
    from core.models import Sladding

    brukere = set(CustomUser.objects.filter(
        pk__in={r['av_id'] for r in for_gjenoppretting if r['av_id']}).values_list('pk', flat=True))
    for r in for_gjenoppretting:
        Sladding.objects.update_or_create(
            modell=r['modell'], rad_id=r['rad_id'], felt=r['felt'],
            defaults={'grunn': r['grunn'], 'av_id': r['av_id'] if r['av_id'] in brukere else None,
                      'av_navn': r['av_navn'], 'sladdet_at': r['sladdet_at']})
    return kjor_registeret()


def kjor_registeret() -> int:
    """Sladd hver rad i registeret på nytt. Antall rader som fantes og ble sladdet.

    En modell uten handler (modulen er fjernet) hoppes over med en advarsel — den kan ikke
    ha rader som noen leser. Alt annet kaster, og gjenopprettingen rulles tilbake: en
    gjenoppretting som stille tok teksten tilbake, er verre enn en som stoppet.
    """
    from core.models import Sladding

    antall = 0
    for rad in Sladding.objects.all().order_by('pk'):
        handler = for_modell(rad.modell)
        if handler is None or rad.felt not in handler.felt.get(rad.modell, ()):
            logger.warning('sladding: ingen handler for %s.%s', rad.modell, rad.felt)
            continue
        antall += bool(handler.gjenta(rad))
    return antall


def skrubb_frosne(vakt_id, tekster) -> int:
    """Erstatt kopier av teksten i vaktens frosne statistikk (`core.VaktStatistikk`).

    En streng i dataene som er *lik* en av `tekster` blir `SLADDET`. Lik, ikke «inneholder»:
    tallene er bygget av hele felt, og en delstreng kunne vært et ord i noe annet. Handleren
    sier hvilke former kopien har (KO kapper siste linje ved 160 tegn). Antall rader endret.
    """
    from core.models import VaktStatistikk

    tekster = {t for t in tekster if t}
    if not tekster or vakt_id is None:
        return 0

    def bytt(verdi):
        if isinstance(verdi, str):
            return SLADDET if verdi in tekster else verdi
        if isinstance(verdi, list):
            return [bytt(v) for v in verdi]
        if isinstance(verdi, dict):
            return {k: bytt(v) for k, v in verdi.items()}
        return verdi

    endret = 0
    for rad in VaktStatistikk.objects.filter(vakt_id=vakt_id):
        ny = bytt(rad.data)
        if ny != rad.data:
            rad.data = ny
            rad.save(update_fields=['data'])
            endret += 1
    return endret
