"""Modul-agnostisk arkivmønster: frysing, integritet og kollaps.

Offentlig API:

- ``BaseArkivHandler`` — subklasses per modul
- ``register(handler)`` / ``get_handler(slug)`` / ``all_handlers()``
- ``beregn_sha256(handler, arkiv)`` — signatur over radnivået
- ``beregn_aggregat_sha256(handler, arkiv, aggregat)``
- ``verifiser(handler, arkiv)`` — True hvis signaturen ikke stemmer
- ``kollaps(handler, arkiv)`` — irreversibel; frys aggregat, slett rader
- ``har_backup_etter(handler, tidspunkt)`` — sperre før kollaps

Se ``core/arkiv/handlers.py`` for arbeidsdelingen mellom core og handler, og
``patients/arkiv.py`` for et ferdig eksempel.
"""
from .handlers import (  # noqa: F401
    BaseArkivHandler,
    all_handlers,
    get_handler,
    register,
)
from .service import (  # noqa: F401
    beregn_aggregat_sha256,
    beregn_sha256,
    har_backup_etter,
    kollaps,
    verifiser,
)

__all__ = [
    'BaseArkivHandler',
    'all_handlers',
    'get_handler',
    'register',
    'beregn_aggregat_sha256',
    'beregn_sha256',
    'har_backup_etter',
    'kollaps',
    'verifiser',
]
