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
    # Hendelsene (pulje 5). Lesingen går med logg-pollen; skrivingen har
    # navngitte stier, som loggen — én regel per sti.
    path('api/hendelser/ny/', views.hendelse_ny_view, name='ko_api_hendelse_ny'),
    path('api/hendelser/<int:pk>/rediger/', views.hendelse_rediger_view,
         name='ko_api_hendelse_rediger'),
    path('api/hendelser/<int:pk>/lukk/', views.hendelse_lukk_view,
         name='ko_api_hendelse_lukk'),
    path('api/hendelser/<int:pk>/gjenapne/', views.hendelse_gjenapne_view,
         name='ko_api_hendelse_gjenapne'),
    # Grupperingen skrives her og ikke i `/oppdrag/api/`: `Oppdrag.hendelse`
    # er KOs peker, og oppdragsmodulen leser den bare.
    path('api/oppdrag/<int:pk>/hendelse/', views.oppdrag_hendelse_view,
         name='ko_api_oppdrag_hendelse'),
]
