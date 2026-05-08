"""Modul-deklarasjon for core-appen.

Core er en kjerne-modul: den har ingen UI-modul-kort på dashboardet, men er
med i registret slik at AuditLog-rader med ``app_label='core'`` har en
tilhørende ``ModuleSettings``-rad og kan filtreres pent i admin.
"""
from core.modules import Module


CoreModule = Module(
    slug='core',
    name='Sanitetsportal (kjerne)',
    description='Felles primitiver, validatorer og auth-helpers.',
    url=None,
    icon='shield-plus-fill',
    permission_flag=None,
    admin_only=True,
    is_core=True,
    order=0,
    show_in_nav=False,
    show_in_dashboard=False,
)
