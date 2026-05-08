"""Modul-deklarasjon for patients-appen.

Pasientregistrering er den første brukervendte modulen i Sanitetsportalen.
Vises som modul-kort på dashboardet og som lenke i nav-menyen for brukere
som har ``kan_redigere_pasienter=True`` (admins ser den uansett).
"""
from core.modules import Module


PatientsModule = Module(
    slug='patients',
    name='Pasientregistrering',
    description=(
        'Registrering, statusoppfølging og statistikk for sanitetsvakt. '
        'Triagering, obspost og ut-tider.'
    ),
    url='/pasienter/',
    icon='clipboard-pulse',
    permission_flag='kan_redigere_pasienter',
    admin_only=False,
    is_core=False,
    order=100,
    show_in_nav=True,
    show_in_dashboard=True,
)
