"""Tilgangskontroll-dekoratorer (SHIM for bakoverkompatibilitet).

Selve implementasjonen er flyttet til core/auth_decorators.py i fase 1
av sanitetsportal-migreringen. Denne filen re-eksporterer de samme
navnene slik at all eksisterende kode (`from accounts.decorators import
admin_required` osv.) fortsetter å fungere uten endring.

Nye apps SKAL importere fra core.auth_decorators direkte:

    from core.auth_decorators import admin_required, has_role_at_least
"""
# Re-eksport fra core. Holder alle eksisterende imports i drift.
from core.auth_decorators import (  # noqa: F401
    admin_required,
    dataset_scope_all,
    role_required,
    stats_required,
    write_required,
)
