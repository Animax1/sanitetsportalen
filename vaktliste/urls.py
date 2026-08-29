"""URL-konfigurasjon for vaktlistemodulen.

Mountet på ``/vaktliste/`` i ``myproject/urls.py``. Må stå FØR core av samme
grunn som patients, statistikk og oppdrag: core inneholder legacy-redirects
som ellers ville fanget ``/api/...``.

URL-navnene har `vaktliste_`-prefiks fordi navnerommet er globalt (ingen
``app_name``), som i de andre modulene.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('', views.index_view, name='vaktliste_index'),

    # Vaktlistene. POST her planlegger en ny vakt — den lager både
    # `core.Vakt` og lista, og rører ikke portalens aktive vakt.
    path('api/vaktlister/', views.vaktlister_view, name='vaktliste_api_vaktlister'),
    path('api/vaktlister/<int:pk>/', views.vaktliste_detalj_view,
         name='vaktliste_api_vaktliste_detalj'),

    # Ressurser henger under én vaktliste; vaktposter under én ressurs.
    # Stiene speiler eierskapet, slik at et feilkoblet id ikke kan treffe
    # noe i en annen liste.
    path('api/vaktlister/<int:pk>/ressurser/', views.ressurser_view,
         name='vaktliste_api_ressurser'),
    path('api/ressurser/<int:pk>/', views.ressurs_detalj_view,
         name='vaktliste_api_ressurs_detalj'),
    path('api/ressurser/<int:pk>/vaktposter/', views.vaktposter_view,
         name='vaktliste_api_vaktposter'),
    path('api/vaktposter/<int:pk>/', views.vaktpost_detalj_view,
         name='vaktliste_api_vaktpost_detalj'),
]
