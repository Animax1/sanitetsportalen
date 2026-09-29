"""Slette en tidligere vakt med alt som hører til den (28. sep. 2026).

André: «jeg vil ha en slett knapp. Noen er test vakter som kan og skal slettes.»

**Hvorfor et register og ikke én `delete()`:** nesten alt som peker på en vakt
har `on_delete=PROTECT` — databasen nekter å slette en vakt med data, og det er
vernet som gjør at en vakt ikke forsvinner ved et uhell. Da må hver modul slette
sitt eget, på sin egen måte (oppdragene har korreksjoner som må løses opp før de
kan slettes, se `oppdrag.services.slett_oppdrag`). Samme idiom som
`core/vaktslutt.py`; `core` kjenner ingen modul ved navn.

**Dekningen håndheves, den huskes ikke.** Hver handler lister modellene den
sletter i `modeller`, og `core/tests_vaktsletting.py` utleder alle fremmednøkler
til `core.Vakt` og krever at hver `PROTECT`/`CASCADE`-peker er dekket. En ny modul
som peker på vakta uten å melde seg inn her, gjør testen rød — ellers ville
slettingen feilet med `ProtectedError` første gang noen prøvde.

Rekkefølgen i `slett_vakt()`:

1. Sperrer: den aktive vakta slettes ikke — portalen skal aldri stå uten.
2. En **hel databasebackup** (`full`, `pre_slett`), *før* transaksjonen. Den er
   eneste vei tilbake, og den dekker alle modulene, også de uten egen arkiv.
3. I én transaksjon: hver modul sletter sitt (lavest `order` først), så
   arkivene og de frosne tallene, så vakta. Én auditrad med hva som gikk.
"""
from __future__ import annotations

import contextlib
import logging
from typing import ClassVar

from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)


class BaseVaktslettHandler:
    """Subklasses per modul som har data knyttet til en vakt."""

    slug: ClassVar[str] = ''
    #: Rekkefølgen slettingen skjer i. Den som peker på en annens rader,
    #: slettes først: lag før vaktlista, oppdrag før KO-hendelsene.
    order: ClassVar[int] = 100
    #: Modellene (`app.Modell`) med fremmednøkkel til `core.Vakt` som handleren
    #: sletter. `core/tests_vaktsletting.py` krever at alle er dekket.
    modeller: ClassVar[tuple[str, ...]] = ()

    def antall(self, vakt) -> list[tuple[str, int]]:
        """Hva som slettes, som (etikett, antall) — vist før noen trykker."""
        raise NotImplementedError

    def slett(self, vakt) -> None:
        """Slett modulens data for vakta. Kalles inne i transaksjonen."""
        raise NotImplementedError


_REGISTER: dict[str, BaseVaktslettHandler] = {}


def register(handler: BaseVaktslettHandler) -> None:
    """Registrer fra `apps.ready()`. Idempotent på slug."""
    if not handler.slug:
        raise ValueError(f'{handler.__class__.__name__} mangler slug.')
    _REGISTER[handler.slug] = handler


def all_handlers() -> list[BaseVaktslettHandler]:
    return sorted(_REGISTER.values(), key=lambda h: (h.order, h.slug))


class KanIkkeSlettes(Exception):
    pass


@contextlib.contextmanager
def _pagar(nokkel):
    """Én sletting av samme ting om gangen — ellers er dobbeltklikket to hele dumper.

    Sikkerhetsgjennomgangen 28. sep. 2026: to innsendinger av vaktslettingen tok
    hver sin hele databasebackup *før* transaksjonen, og la to auditrader. Backupen
    må stå utenfor transaksjonen (en fil ruller ikke tilbake), så en databaselås
    rekker ikke; sperren står i cachen, som `add()` gjør atomisk i både
    LocMem og Redis. Cachefeil gir åpen sperre — samme valg som rate-limiten;
    kontrollen av at raden fortsatt finnes står uansett.
    """
    nokkel = f'vaktsletting:{nokkel}'
    try:
        fikk = cache.add(nokkel, 1, 600)
    except Exception:  # noqa: BLE001
        logger.warning('vaktsletting: cachen svarte ikke', exc_info=True)
        fikk = None
    if fikk is False:
        raise KanIkkeSlettes('Slettingen pågår allerede. Last siden på nytt om litt.')
    try:
        yield
    finally:
        if fikk:
            try:
                cache.delete(nokkel)
            except Exception:  # noqa: BLE001
                logger.warning('vaktsletting: cachen svarte ikke', exc_info=True)


def _backup_foer(slug, bruker, note):
    """`pre_slett`-backupen. Feiler den, slettes ingenting — og brukeren får en
    melding, ikke en 500 (andre gjennomgang 29. sep. 2026: full disk eller en
    serialiseringsfeil ga HTML-500 også fra JSON-endepunktene)."""
    from core.backup import create_backup, rydd_pre_slett
    try:
        create_backup(slug=slug, kind='pre_slett', user=bruker, note=note)
    except Exception as feil:  # noqa: BLE001
        logger.exception('vaktsletting: backupen før slettingen feilet')
        raise KanIkkeSlettes('Backupen før slettingen feilet, så ingenting er slettet. '
                             'Se backup-siden.') from feil
    rydd_pre_slett(slug)


def _arkiver_for(vakt):
    """(handler, arkiv) for hvert arkiv som peker på vakta, gjennom arkivregisteret."""
    from core.arkiv import all_handlers as arkivhandlere

    for handler in arkivhandlere():
        modell = getattr(handler, 'arkiv_model', None)
        if modell is not None:
            for arkiv in modell.objects.filter(vakt=vakt):
                yield handler, arkiv


def oversikt(vakt) -> list[tuple[str, int]]:
    """Alt som forsvinner, som (etikett, antall). Tomme linjer er utelatt."""
    from core.models import VaktStatistikk

    linjer = [linje for h in all_handlers() for linje in h.antall(vakt)]
    linjer.append(('arkiver', sum(1 for _ in _arkiver_for(vakt))))
    linjer.append(('frosne statistikkfaner', VaktStatistikk.objects.filter(vakt=vakt).count()))
    return [(etikett, n) for etikett, n in linjer if n]


def slett_vakt(vakt, *, bruker, request=None) -> list[tuple[str, int]]:
    """Slett `vakt` og alt som hører til. Returnerer det som ble slettet.

    Kaster `KanIkkeSlettes` for den aktive vakta — før noe er rørt.
    """
    if vakt.pk == _aktiv_pk() or vakt.er_aktiv:
        raise KanIkkeSlettes(f'«{vakt.navn}» er den aktive vakta og kan ikke slettes. '
                             f'Avslutt den først.')
    with _pagar(f'vakt:{vakt.pk}'):
        return _slett_vakt(vakt, bruker=bruker, request=request)


def _aktiv_pk():
    from core.vakt import hent_aktiv_vakt
    return hent_aktiv_vakt().pk


def _slett_vakt(vakt, *, bruker, request):
    from audit.models import AuditLog
    from core.arkiv import logg_arkivhendelse
    from core.klientip import klient_ip
    from core.models import Vakt, VaktStatistikk

    # Innenfor sperren: den andre av to innsendinger kom hit med en vakt den
    # leste før den første slettet den.
    if not Vakt.objects.filter(pk=vakt.pk).exists():
        raise KanIkkeSlettes(f'«{vakt.navn}» er allerede slettet.')

    slettet = oversikt(vakt)
    _backup_foer('full', bruker, f'Før sletting av vakta «{vakt.navn}»')

    with transaction.atomic():
        # **Spør igjen, under låsen** (andre gjennomgang 29. sep. 2026). Backupen
        # over tar sekunder, og en annen admin kan ha gjenåpnet vakta imens —
        # sjekken i `slett_vakt` gjaldt vakta slik den var før backupen.
        from core.vakt import laas_aktiv_vakt
        aktiv = laas_aktiv_vakt()
        if vakt.pk == aktiv.pk or Vakt.objects.filter(pk=vakt.pk, er_aktiv=True).exists():
            raise KanIkkeSlettes(f'«{vakt.navn}» ble gjort aktiv mens slettingen pågikk, '
                                 f'og er ikke slettet.')
        for handler in all_handlers():
            handler.slett(vakt)
        for handler, arkiv in list(_arkiver_for(vakt)):
            pk, tittel = arkiv.pk, arkiv.tittel
            arkiv.delete()   # CASCADE tar de arkiverte radene
            logg_arkivhendelse(type(arkiv), 'arkiv_slettet',
                               f'arkiv_id={pk}, tittel={tittel}, med vakta',
                               request=request, record_id=pk)
        VaktStatistikk.objects.filter(vakt=vakt).delete()
        pk, navn = vakt.pk, vakt.navn
        vakt.delete()
        brukeren = getattr(request, 'user', None) or bruker
        AuditLog.objects.create(
            table_name='core_vakt', record_id=pk, action='DELETE', field_name='vakt_slettet',
            new_value=f'«{navn}» — ' + ', '.join(f'{etikett}: {n}' for etikett, n in slettet),
            user=brukeren if getattr(brukeren, 'is_authenticated', False) else None,
            ip=klient_ip(request) if request is not None else None,
        )
    return slettet


def finn_arkiv(slug: str, pk: int):
    """`(handler, arkiv)` gjennom arkivregisteret. `LookupError`/`DoesNotExist` ellers."""
    from core.arkiv import get_handler

    handler = get_handler(slug)
    modell = getattr(handler, 'arkiv_model', None) if handler else None
    if modell is None:
        raise LookupError(f'Ukjent arkiv: «{slug}».')
    return handler, modell.objects.get(pk=pk)


def slett_arkiv(slug: str, pk: int, *, bruker=None, request=None) -> str:
    """Slett ett arkiv gjennom arkivregisteret. Returnerer tittelen.

    **Den ene veien** (sikkerhetsgjennomgangen 28. sep. 2026): vakt-siden og
    modulenes egne sletteknapper — pasientarkivet og oppdragsarkivet — kalte
    hver sin `delete()`, og ingen av dem tok backup. Et arkiv er ofte det eneste
    som står igjen av en vakt: etter «Avslutt vakt» er radene borte, og etter
    kollaps finnes bare aggregatet. Nå tas en `pre_slett`-backup av arkivets
    egen backupfil først (`handler.backup_slug`, den hele basen om modulen ikke
    har en), og én auditrad på arkivets tabell.
    """
    from core.arkiv import logg_arkivhendelse

    with _pagar(f'arkiv:{slug}:{pk}'):
        handler, arkiv = finn_arkiv(slug, pk)
        tittel = arkiv.tittel
        backup_slug = getattr(handler, 'backup_slug', '') or 'full'
        _backup_foer(backup_slug, bruker, f'Før sletting av arkivet «{tittel}»')
        with transaction.atomic():
            arkiv.delete()   # CASCADE tar de arkiverte radene
            logg_arkivhendelse(type(arkiv), 'arkiv_slettet', f'arkiv_id={pk}, tittel={tittel}',
                               request=request, record_id=pk)
    return tittel
