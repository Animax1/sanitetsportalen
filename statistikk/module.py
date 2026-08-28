"""Modul-deklarasjon for statistikk-appen.

Statistikk er samlestedet for tall på tvers av portalens moduler. I dag er
``patients`` den eneste leverandøren, og ``statistikk/views.py`` kaller derfor
``patients.services`` direkte. Når modul nummer to skal levere tall, erstattes
den direkte importen av et registry etter samme idiom som ``core.backup`` og
``core.arkiv`` — se TODO.md.

``min_rolle`` er midlertidig. Den styrer synligheten fram til ``ModulTilgang``
finnes, slik at denne modulen kunne leveres uten å innføre et
``kan_se_statistikk``-flagg vi ville kastet igjen to uker senere. Feltet
fjernes i samme leveranse som tar bort ``permission_flag``.
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
    permission_flag=None,
    min_rolle='lead_view',
    admin_only=False,
    is_core=False,
    order=110,
    show_in_nav=True,
    show_in_dashboard=True,
)
