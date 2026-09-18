"""URL-konfigurasjon for KO-modulen.

Mountet på ``/ko/`` i ``myproject/urls.py``, og **før** ``core`` av samme grunn
som patients, statistikk, oppdrag og vaktliste: core inneholder
legacy-videresendinger som ellers ville fanget ``/api/...``.

URL-navnene har `ko_`-prefiks fordi navnerommet er globalt (ingen
``app_name``), som i de andre modulene.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_view, name='ko_index'),
    path('api/tilstede/', views.tilstede_view, name='ko_api_tilstede'),
    # Loggen (pulje 2). **Retting og fjerning er navngitte stier**, ikke et
    # felt i kroppen på skriveendepunktet: de to krever hvert sitt
    # tilgangsnivå, og et fritt ledd i kroppen ville flyttet den forskjellen
    # inn i en `if` der ingen dekoratørtest ser den.
    path('api/logg/', views.logg_view, name='ko_api_logg'),
    path('api/logg/ny/', views.logg_skriv_view, name='ko_api_logg_ny'),
    path('api/logg/<int:pk>/rett/', views.logg_rett_view, name='ko_api_logg_rett'),
    path('api/logg/<int:pk>/fjern/', views.logg_fjern_view, name='ko_api_logg_fjern'),
    # Ressurslista (pulje 3). **Bare lesing.** Å sette en enhet av vakt eller
    # i passiv vakt er oppdragsmodulens endepunkter, og de blir KOs når
    # sentralbordet flytter (pulje 4) — et eget her ville vært en andre vei
    # inn til samme tilstand.
    path('api/ressurser/', views.ressurser_view, name='ko_api_ressurser'),
]
