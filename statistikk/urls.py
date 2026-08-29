"""URL-konfigurasjon for statistikk-appen.

URL-navnene er globale (ingen ``app_name``), på samme måte som i
``patients.urls``.

**Stiene bærer kilden fra og med fase 6.** `api/full-stats/` og
`api/arkiv/<pk>/full-stats/` het det så lenge det fantes én kilde; nå står
slug-en i stien, og hvilke slugs som svarer avgjøres av
``core.stats``-registeret — ikke av denne fila.

De to gamle stiene står igjen som videresending til pasientkilden, av samme
grunn som pasientmodulen beholdt sine da endepunktene flyttet hit: en klient
med gammel JS i cache ville ellers sluttet å oppdatere seg uten å si fra —
`loadStats()` logger en advarsel og lar forrige visning bli stående. 302, ikke
301: en 301 caches for godt, og stien skal kunne tas i bruk igjen.

Videresendingen er transitorisk. Den kan fjernes når ingen klienter kan ha
den gamle fila lenger; da forsvinner også unntakene i
``patients/tests_modul_dekorator.py``.
"""
from django.shortcuts import redirect
from django.urls import path

from . import views

urlpatterns = [
    path('', views.statistikk_view, name='statistikk'),
    path(
        'api/kilde/<slug:slug>/full-stats/',
        views.kilde_full_stats_view,
        name='api_kilde_full_stats',
    ),
    path(
        'api/kilde/<slug:slug>/arkiv/<int:pk>/full-stats/',
        views.kilde_arkiv_full_stats_view,
        name='api_kilde_arkiv_full_stats',
    ),

    # ── Videresending fra én-kilde-tida ──────────────────────────────────
    path(
        'api/full-stats/',
        lambda req: redirect('/statistikk/api/kilde/patients/full-stats/'),
        name='api_full_stats_gammel_sti',
    ),
    path(
        'api/arkiv/<int:pk>/full-stats/',
        lambda req, pk: redirect(
            f'/statistikk/api/kilde/patients/arkiv/{pk}/full-stats/'),
        name='api_arkiv_full_stats_gammel_sti',
    ),
]
