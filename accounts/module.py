"""Modul-deklarasjon for accounts-appen.

Accounts er en kjerne-modul: brukeradministrasjon, MFA og login. Vises ikke
som modul-kort på dashboardet (admin når brukeradministrasjon via dropdown-
menyen i header), men er registrert for AuditLog-filtrering og fremtidig
bruk i system-panel.
"""
from core.modules import Module


AccountsModule = Module(
    slug='accounts',
    name='Brukeradministrasjon',
    description='Brukere, roller, MFA og passord.',
    url='/accounts/users/',
    icon='people-fill',
    permission_flag=None,
    admin_only=True,
    is_core=True,
    order=10,
    show_in_nav=False,
    show_in_dashboard=False,
)
