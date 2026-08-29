"""URL-konfigurasjon for oppdragsmodulen.

Mountet på ``/oppdrag/`` i ``myproject/urls.py``. Må stå FØR core av samme
grunn som patients og statistikk: core inneholder legacy-redirects som ellers
ville fanget ``/api/...``.
"""
from django.urls import path

from . import views

urlpatterns = [
    # Én URL, to grensesnitt. Hvilket avgjøres av om kontoen er knyttet til en
    # Enhet — ikke av tilgangsnivået. Se views_common.er_enhetskonto.
    path('', views.index_view, name='oppdrag_index'),

    path('api/enheter/', views.enheter_view, name='oppdrag_api_enheter'),
    path('api/enheter/ny/', views.enhet_opprett_view, name='oppdrag_api_enhet_ny'),
    path('api/enheter/<int:pk>/', views.enhet_detalj_view, name='oppdrag_api_enhet_detalj'),
    path('api/kontoer/', views.kontoer_view, name='oppdrag_api_kontoer'),
    path('api/lokasjoner/', views.lokasjoner_view, name='oppdrag_api_lokasjoner'),
    path('api/lokasjoner/<int:pk>/', views.lokasjon_detalj_view,
         name='oppdrag_api_lokasjon_detalj'),
    path('api/oppdrag/', views.oppdrag_liste_view, name='oppdrag_api_liste'),
    path('api/oppdrag/<int:pk>/', views.oppdrag_detalj_view, name='oppdrag_api_detalj'),
    path('api/oppdrag/<int:pk>/flytt/', views.flytt_view, name='oppdrag_api_flytt'),
]
