"""Modul-deklarasjon for statistikk-appen.

Statistikk er samlestedet for tall på tvers av portalens moduler. I dag er
``patients`` den eneste leverandøren, og ``statistikk/views.py`` kaller derfor
``patients.services`` direkte. Når modul nummer to skal levere tall, erstattes
den direkte importen av et registry etter samme idiom som ``core.backup`` og
``core.arkiv`` — se TODO.md.

Tilgang styres av ``ModulTilgang('statistikk', ...)``. Modulen ble kort gatet
på et midlertidig ``Module.min_rolle``-felt mens den ventet på tabellen; det
feltet er borte nå.
"""
from core.modules import Module


StatistikkModule = Module(
    slug='statistikk',
    name='Statistikk',
    description=(
        'Samlet statistikk for portalen: fordelinger, tidsanalyse, '
        'krysstabeller og statistiske tester.'
    ),
    url='/statistikk/',
    icon='bar-chart-line',
    admin_only=False,
    is_core=False,
    order=110,
    show_in_nav=True,
    show_in_dashboard=True,
)
