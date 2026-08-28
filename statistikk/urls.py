"""URL-konfigurasjon for statistikk-appen.

URL-navnene er globale (ingen ``app_name``), på samme måte som i
``patients.urls``. Navnene ``api_full_stats`` og ``api_arkiv_full_stats`` er
uendret fra da endepunktene lå i pasientmodulen, slik at ``reverse()`` i
tester og maler fortsatt treffer. Stiene endret seg; navnene gjorde det ikke.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('', views.statistikk_view, name='statistikk'),
    path('api/full-stats/', views.full_stats_view, name='api_full_stats'),
    path(
        'api/arkiv/<int:pk>/full-stats/',
        views.arkiv_full_stats_view,
        name='api_arkiv_full_stats',
    ),
]
