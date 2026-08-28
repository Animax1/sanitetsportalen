"""Modul-deklarasjon for patients-appen.

Pasientregistrering er den første brukervendte modulen i Sanitetsportalen.
Vises som modul-kort på dashboardet og som lenke i nav-menyen for brukere som
har en ``ModulTilgang``-rad på ``patients`` (global admin ser den uansett).
Synligheten leser samme kilde som håndhevelsen — se ``Module.is_visible_for``.
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
    admin_only=False,
    is_core=False,
    order=100,
    show_in_nav=True,
    show_in_dashboard=True,
)
