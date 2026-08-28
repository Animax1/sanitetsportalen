"""Tilgangskontroll-dekoratorer (SHIM for bakoverkompatibilitet).

Selve implementasjonen ligger i ``core/auth_decorators.py``. Denne fila
re-eksporterer navnet slik at gammel kode
(``from accounts.decorators import admin_required``) fortsetter å virke.

Ny kode SKAL importere fra ``core.auth_decorators`` direkte:

    from core.auth_decorators import admin_required, har_tilgang, modul_kreves

**Lista krympet i deploy 2.** ``role_required``, ``write_required``,
``stats_required``, ``dataset_scope_all`` og ``has_role_at_least`` er borte:
de tok rolleverdier som ikke finnes lenger etter at ``role`` ble redusert til
``admin``/``bruker``. Ingen av dem sto på et view da de ble fjernet —
modultilgang hadde overtatt hver enkelt.
"""
# Re-eksport fra core. Holder eksisterende imports i drift.
from core.auth_decorators import admin_required  # noqa: F401
