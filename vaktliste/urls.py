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

    # Registersiden. Egen side, ikke en fane på planleggingssiden: registrene
    # er globale, fanene der er ressursene i én vakt.
    path('registre/', views_registre.registre_view, name='vaktliste_registre'),

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
    path('api/roller/', views_registre.roller_view, name='vaktliste_api_roller'),
    path('api/roller/<int:pk>/', views_registre.rolle_detalj_view,
         name='vaktliste_api_rolle_detalj'),
]
