"""URL-konfigurasjon for vaktlistemodulen.

Mountet på ``/vaktliste/`` i ``myproject/urls.py``. Må stå FØR core av samme
grunn som patients, statistikk og oppdrag: core inneholder legacy-redirects
som ellers ville fanget ``/api/...``.

URL-navnene har `vaktliste_`-prefiks fordi navnerommet er globalt (ingen
``app_name``), som i de andre modulene.
"""
from django.urls import path

from . import views, views_registre

urlpatterns = [
    path('', views.index_view, name='vaktliste_index'),

    # **Registersiden er lagt ned (30. aug. 2026).** Mannskapet er en fane på
    # planleggingssiden, korps og kompetanser ligger i «Innstillinger». Et
    # klikk ut av planleggingen kostet plassen man sto på, og mannskap og
    # ressurser er nettopp de to man veksler mellom. Endepunktene under
    # `api/` står igjen — det var bare flata som flyttet.

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

    # Drift (fase 4). Retningen og overgangen står i URL-en, ikke i kroppen:
    # et veksle-endepunkt gir et kappløp når to trykk kommer tett, og den som
    # trykket sist vet ikke hva hun endte på. Samme grep som oppdragsmodulen.
    path('api/vaktlister/<int:pk>/drift/<str:tilstand>/', views.drift_view,
         name='vaktliste_api_drift'),
    path('api/vaktposter/<int:pk>/stempling/<str:handling>/',
         views.stempling_view, name='vaktliste_api_stempling'),

    # Registrene. Mannskapet er hovedlista; de tre verdimengdene bygges av
    # samme fabrikk — se views_registre.py.
    path('api/mannskap/', views_registre.mannskap_view,
         name='vaktliste_api_mannskap'),
    path('api/mannskap/<int:pk>/', views_registre.mannskap_detalj_view,
         name='vaktliste_api_mannskap_detalj'),
    path('api/korps/', views_registre.korps_view, name='vaktliste_api_korps'),
    path('api/korps/<int:pk>/', views_registre.korps_detalj_view,
         name='vaktliste_api_korps_detalj'),
    path('api/kompetanser/', views_registre.kompetanser_view,
         name='vaktliste_api_kompetanser'),
    path('api/kompetanser/<int:pk>/', views_registre.kompetanse_detalj_view,
         name='vaktliste_api_kompetanse_detalj'),
    # Ressursgruppene. Egen sti, ikke en av verdimengdene i views_registre:
    # gruppa har ikon og rekkefølge, og administreres på planleggingssiden.
    path('api/grupper/', views.grupper_view, name='vaktliste_api_grupper'),
    path('api/grupper/<int:pk>/', views.gruppe_detalj_view,
         name='vaktliste_api_gruppe_detalj'),
    path('api/roller/', views_registre.roller_view, name='vaktliste_api_roller'),
    path('api/roller/<int:pk>/', views_registre.rolle_detalj_view,
         name='vaktliste_api_rolle_detalj'),
]
