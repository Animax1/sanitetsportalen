"""Slette en portal med alt som hører til den (18. okt. 2026).

André: «jeg må kunne slette portaler og ja med det all info i portalen. Det skal være forbeholdt
admin-rollen.» Det snur beslutningen i `docs/BESLUTNING_PORTALER.md` §4.1 («en portal med vakter
slettes ikke, den deaktiveres») — deaktivering står fortsatt for det som skal kunne komme tilbake.

**Bygget på «Slett tidligere vakt»** (`core/vaktsletting.py`): hver vakt i portalen slettes med
modulenes egne handlere, arkivene og den frosne statistikken (André: ja, de går også). Så det
portalen eier uten en vakt — det som peker på `Vaktportal` — og til slutt portalen selv.
Kontoene står; de mister bare medlemskapet.

| Sperre | Hvorfor |
|---|---|
| **Bare global admin** (`@admin_required` på viewet) | Det er det mest inngripende i portalen |
| **Portalens navn skrives inn** | En knapp alene er ett feilklikk unna å fjerne en hel portal |
| **Ikke den siste** | Portalen skal aldri stå uten en portal. Standard kan slettes som alle andre (André: ja) |
| **Ikke midt i noe** — sperrene fra «Avslutt vakt» på den aktive vakta | Et oppdrag på tavla ville blitt slettet halvveis |
| **Hel databasebackup først**, utenfor transaksjonen | Den eneste veien tilbake |
| **Alt i én transaksjon**, én auditrad med hva som gikk | Halvveis slettet er verre enn ingenting |
"""
from __future__ import annotations

import logging

from django.db import transaction

from core.vaktsletting import KanIkkeSlettes

logger = logging.getLogger(__name__)


def _portalmodeller() -> list[str]:
    """Modellene med fremmednøkkel til `Vaktportal` (unntatt `Vakt`, som går via vaktslettingen),
    i en rekkefølge der den som peker på en annen slettes først. Utledet, ikke listet: en ny
    modul som eier noe i portalen, skal være med fra dagen den finnes."""
    from django.apps import apps

    from core.backup.handlers import utled_restore_models
    from core.models import Vakt, Vaktportal

    etiketter = sorted({
        m._meta.label for m in apps.get_models()
        if m is not Vakt and any(
            f.is_relation and f.concrete and f.related_model is Vaktportal
            and (f.many_to_one or f.one_to_one)
            for f in m._meta.get_fields())
    })
    return utled_restore_models(etiketter, []) if etiketter else []


def _felt_til_portal(modell):
    from core.models import Vaktportal

    return [f.name for f in modell._meta.get_fields()
            if f.is_relation and getattr(f, 'concrete', False)
            and f.related_model is Vaktportal and (f.many_to_one or f.one_to_one)]


def oversikt(portal) -> dict:
    """Det admin skal se før det trykkes: vaktene, hva som går, og hva som sperrer."""
    from collections import Counter

    from django.apps import apps
    from django.db.models import Q

    from core import vaktslutt, vaktsletting

    vakter = list(portal.vakter.all().order_by('-pk'))
    sum_ = Counter()
    for vakt in vakter:
        for etikett, n in vaktsletting.oversikt(vakt):
            sum_[etikett] += n
    for label in _portalmodeller():
        modell = apps.get_model(label)
        q = Q()
        for felt in _felt_til_portal(modell):
            q |= Q(**{felt: portal})
        n = modell.objects.filter(q).count()
        if n:
            sum_[str(modell._meta.verbose_name_plural).lower()] += n
    aktiv = next((v for v in vakter if v.er_aktiv), None)
    sperrer = vaktslutt.oversikt(aktiv)['sperrer'] if aktiv else []
    from core.models import Vaktportal
    if Vaktportal.objects.exclude(pk=portal.pk).count() == 0:
        sperrer = ['Dette er den siste portalen. Portalen kan ikke stå uten.', *sperrer]
    return {'vakter': [v.navn for v in vakter], 'linjer': sorted(sum_.items()),
            'sperrer': sperrer}


def slett_portal(portal, *, bekreftelse: str, bruker, request=None) -> dict:
    """Slett portalen og alt i den. Kaster `KanIkkeSlettes` før noe er rørt."""
    from core.vaktsletting import _pagar

    if (bekreftelse or '').strip() != portal.navn:
        raise KanIkkeSlettes(f'Skriv portalens navn, «{portal.navn}», for å bekrefte.')
    o = oversikt(portal)
    if o['sperrer']:
        raise KanIkkeSlettes(' '.join(o['sperrer']))
    with _pagar(f'portal:{portal.pk}'):
        return _slett(portal, o, bruker=bruker, request=request)


def _slett(portal, o, *, bruker, request):
    from django.apps import apps
    from django.db.models import Q

    from audit.models import AuditLog
    from core.arkiv import logg_arkivhendelse
    from core.klientip import klient_ip
    from core.models import AppSetting, Vaktportal, VaktStatistikk
    from core.vaktsletting import _arkiver_for, _backup_foer, all_handlers

    if not Vaktportal.objects.filter(pk=portal.pk).exists():
        raise KanIkkeSlettes(f'«{portal.navn}» er allerede slettet.')
    _backup_foer('full', bruker, f'Før sletting av portalen «{portal.navn}»')

    with transaction.atomic():
        # Under låsen: en annen admin kan ha slettet de andre portalene mens backupen gikk.
        if Vaktportal.objects.select_for_update().exclude(pk=portal.pk).count() == 0:
            raise KanIkkeSlettes('Dette er den siste portalen. Portalen kan ikke stå uten.')
        for vakt in list(portal.vakter.all()):
            for handler in all_handlers():
                handler.slett(vakt)
            for _handler, arkiv in list(_arkiver_for(vakt)):
                pk, tittel = arkiv.pk, arkiv.tittel
                arkiv.delete()
                logg_arkivhendelse(type(arkiv), 'arkiv_slettet',
                                   f'arkiv_id={pk}, tittel={tittel}, med portalen',
                                   request=request, record_id=pk)
            VaktStatistikk.objects.filter(vakt=vakt).delete()
            vakt.delete()
        for label in _portalmodeller():
            modell = apps.get_model(label)
            q = Q()
            for felt in _felt_til_portal(modell):
                q |= Q(**{felt: portal})
            modell.objects.filter(q).delete()
        AppSetting.objects.filter(key__endswith=f'@p{portal.pk}').delete()
        pk, navn, slug = portal.pk, portal.navn, portal.slug
        portal.delete()
        brukeren = getattr(request, 'user', None) or bruker
        AuditLog.objects.create(
            table_name='core_vaktportal', record_id=pk, action='DELETE',
            field_name='portal_slettet',
            new_value=(f'«{navn}» ({slug}) — vakter: {len(o["vakter"])}; '
                       + ', '.join(f'{e}: {n}' for e, n in o['linjer']))[:2000],
            user=brukeren if getattr(brukeren, 'is_authenticated', False) else None,
            ip=klient_ip(request) if request is not None else None,
        )
    return o
