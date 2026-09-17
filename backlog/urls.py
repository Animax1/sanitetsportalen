"""URL-konfigurasjon for backlog-modulen.

Mountet på ``/backlog/`` i ``myproject/urls.py``, og **før** ``core`` av samme
grunn som de andre modulene: core inneholder legacy-videresendinger som ellers
ville fanget ``/api/...``.

URL-navnene har `backlog_`-prefiks fordi navnerommet er globalt (ingen
``app_name``), som i de andre modulene.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_view, name='backlog_index'),
    path('api/innspill/', views.innspill_view, name='backlog_api_innspill'),

    # **To navngitte stier, ikke `<str:handling>`.** Et fritt ledd her ville
    # fanget `innspill/<pk>/` selv, og verdien ville måttet valideres et sted
    # til. Samme grep som vaktlistas `arkiver`/`gjenopprett` (12. sep. 2026).
    path('api/innspill/<int:pk>/lost/', views.lost_view, {'lost': True},
         name='backlog_api_innspill_lost'),
    path('api/innspill/<int:pk>/gjenapne/', views.lost_view, {'lost': False},
         name='backlog_api_innspill_gjenapne'),

    path('api/innspill/<int:pk>/', views.innspill_detalj_view,
         name='backlog_api_innspill_detalj'),

    # Kommentarer — tråden under én sak.
    path('api/innspill/<int:pk>/kommentarer/', views.kommentarer_view,
         name='backlog_api_kommentarer'),
    path('api/kommentarer/<int:pk>/', views.kommentar_detalj_view,
         name='backlog_api_kommentar_detalj'),

    # Backloginnstillinger: typene. Admin-styrt verdimengde, samme mønster som
    # oppdragsmodulens «Valglister».
    path('api/typer/', views.typer_view, name='backlog_api_typer'),
    path('api/typer/<int:pk>/', views.type_detalj_view,
         name='backlog_api_type_detalj'),
]
