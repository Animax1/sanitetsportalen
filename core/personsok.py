"""Søk etter én person på tvers av portalene — for innsyn og sletting (18. okt. 2026).

`docs/BESLUTNING_PORTALER.md` §4.5: «retting og sletting av én person skjer i flere
rader. Innsyn og sletting krever derfor et søk på tvers av portalene, på e-post og navn,
for admin.» Ola som går vakt i to portaler er to mannskapsrader, og en innsynsbegjæring
fra ham skal besvares med begge.

**Et register, som de andre** (`core/driftstatus.py`, `core/opprydding.py`): `core`
kjenner ingen modul ved navn. Hver modul melder inn sine personregistre fra
`<app>/personsok.py`; kontoene står her, fordi `accounts` er rammeverk.

| Regel | Hvorfor |
|---|---|
| **Bare global admin, og hvert søk logges** (`SOK` i auditen, med søkeordet) | Det er det ene stedet som ser på tvers av alle portaler. Et søk etter et navn er en lesing av personopplysninger, og det skal kunne etterprøves hvem som gjorde det |
| **Minst to tegn** | Ett tegn er hele registeret, og det er ikke et søk |
| **Hver kilde fanges for seg** | En modul som feiler, skal ikke ta søket ned — da er innsynet borte når man trenger det. Feilen står i kilden |
| **«Slett» bare der ingenting peker på raden** | En person med historikk (skift, pasienter) slettes ikke herfra: historikken er dokumentasjon. Fritekst i den er fase 7, sladding (§4.9) |
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)

MIN_TEGN = 2
MAKS_TREFF = 50


@dataclass
class Treff:
    pk: int
    navn: str
    portal: str = ''
    felter: list = field(default_factory=list)      # [(etikett, verdi)]
    bruk: list = field(default_factory=list)        # ['12 skift', ...]
    sperre: str = ''                                 # tom = kan slettes herfra
    lenke: str = ''                                  # en side som eier raden, om den finnes


class BasePersonsokHandler:
    """Ett personregister. Subklasses per modul."""

    slug: ClassVar[str] = ''
    etikett: ClassVar[str] = ''
    #: Kan raden slettes herfra i det hele tatt? Kontoene har sin egen side med
    #: sine egne sperrer, og slettes der.
    kan_slette: ClassVar[bool] = True

    def sok(self, q: str) -> list[Treff]:
        raise NotImplementedError

    def slett(self, pk: int) -> str:
        """Slett raden, eller kast `ValidationError` med grunnen. Returnerer navnet."""
        raise NotImplementedError


_REGISTER: dict[str, BasePersonsokHandler] = {}


def register(handler: BasePersonsokHandler) -> None:
    if not handler.slug:
        raise ValueError('Personsøkhandler uten slug.')
    _REGISTER[handler.slug] = handler


def all_handlers() -> list[BasePersonsokHandler]:
    """Kontoene først, så modulene i slug-rekkefølge."""
    return sorted(_REGISTER.values(), key=lambda h: (h.slug != 'kontoer', h.slug))


def for_slug(slug: str):
    return _REGISTER.get(slug)


def clear_registry() -> None:
    """Bare for tester."""
    _REGISTER.clear()


def sok(q: str) -> list[dict]:
    """`[{'handler', 'treff', 'feil'}]` for hver kilde. Kaster aldri."""
    from core.admin_status import _scrub_secrets

    q = (q or '').strip()
    if len(q) < MIN_TEGN:
        return []
    ut = []
    for h in all_handlers():
        try:
            ut.append({'handler': h, 'treff': h.sok(q)[:MAKS_TREFF], 'feil': ''})
        except Exception as exc:  # noqa: BLE001 — én kilde skal ikke ta ned søket
            logger.exception('personsøk: %s feilet', h.slug)
            ut.append({'handler': h, 'treff': [], 'feil': _scrub_secrets(str(exc))})
    return ut


# ── Kontoene ─────────────────────────────────────────────────────────────────

class KontoHandler(BasePersonsokHandler):
    slug = 'kontoer'
    etikett = 'Kontoer'
    kan_slette = False

    def sok(self, q):
        from django.db.models import Q
        from django.urls import reverse

        from accounts.models import CustomUser

        qs = (CustomUser.objects.filter(Q(username__icontains=q) | Q(fullt_navn__icontains=q)
                                        | Q(email__icontains=q))
              .prefetch_related('portaltilganger__portal', 'tilhorigheter__tilhorighet')
              .order_by('username'))
        return [Treff(
            pk=u.pk, navn=u.fullt_navn or u.username,
            portal=', '.join(t.portal.navn for t in u.portaltilganger.all()) or (
                'Alle (admin)' if u.role == 'admin' else 'Ingen'),
            felter=[('Brukernavn', u.username), ('E-post', u.email or '–'),
                    ('Tilhørigheter', ', '.join(k.tilhorighet.navn for k in u.tilhorigheter.all())
                     or '–'),
                    ('Sist innlogget', u.last_login_at.strftime('%d.%m.%Y') if u.last_login_at
                     else 'Aldri')],
            sperre='Kontoer slettes fra brukersiden, med sperrene der.',
            lenke=reverse('portaladmin:user_detail', args=[u.pk]),
        ) for u in qs]



def register_handlers() -> None:
    """Kalles fra `CoreConfig.ready()`."""
    register(KontoHandler())
