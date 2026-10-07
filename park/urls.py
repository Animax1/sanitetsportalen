"""URL-konfigurasjon for park-modulen.

Mountet på ``/lag/`` i ``myproject/urls.py``, før ``core``. Navnene har
`park_`-prefiks fordi navnerommet er globalt, som i de andre modulene.

**To slags ruter, og testen skiller dem** (`park/tests.py`):

- under ``/lag/`` for innloggede, gatet med ``@modul_kreves('park', …)``
- under ``/lag/r/`` uten innlogging, gatet med ``@park_lenke_kreves`` — tokenet
  fra tiltakskortet (``docs/FORSLAG_PARK.md`` §4). Selve siden er statisk og
  står i unntakslista i ``patients/tests_modul_dekorator.py``.
"""
from django.urls import path

from . import views, views_lag

urlpatterns = [
    path('', views.index_view, name='park_index'),

    # Oppsettet (pulje 2). Navngitte stier for handlingene, som backlog og KO:
    # et fritt ledd i kroppen er et sted å ta feil.
    path('api/lenker/', views.lenker_view, name='park_api_lenker'),
    path('api/lenker/<int:pk>/fjern/', views.lenke_fjern_view, name='park_api_lenke_fjern'),
    path('api/lenker/<int:pk>/slett-etter/', views.lenke_slett_etter_view,
         name='park_api_lenke_slett_etter'),
    path('api/steder/', views.steder_view, name='park_api_steder'),
    path('api/steder/<int:pk>/skjul/', views.sted_skjul_view, name='park_api_sted_skjul'),
    path('api/registreringer/', views.registreringer_view, name='park_api_registreringer'),
    path('api/registreringer/<int:pk>/slett/', views.registrering_slett_view,
         name='park_api_registrering_slett'),
    path('api/problemstillinger/', views.problemstillinger_view,
         name='park_api_problemstillinger'),
    path('api/problemstillinger/rekkefolge/', views.problemstillinger_rekkefolge_view,
         name='park_api_problemstillinger_rekkefolge'),
    path('api/problemstillinger/<int:pk>/', views.problemstilling_detalj_view,
         name='park_api_problemstilling_detalj'),
    path('api/utfall/', views.utfall_view, name='park_api_utfall'),
    path('api/utfall/rekkefolge/', views.utfall_rekkefolge_view, name='park_api_utfall_rekkefolge'),
    path('api/utfall/<int:pk>/', views.utfall_detalj_view, name='park_api_utfall_detalj'),

    # Siden lagene bruker. Uten innlogging; tokenet står i fragmentet.
    path('r/', views_lag.side_view, name='park_lag_side'),
    path('r/api/oppsett/', views_lag.oppsett_view, name='park_lag_oppsett'),
    path('r/api/sted/', views_lag.sted_view, name='park_lag_sted'),
    path('r/api/registrer/', views_lag.registrer_view, name='park_lag_registrer'),
    path('r/api/angre/', views_lag.angre_view, name='park_lag_angre'),
    # «Vi finner ikke fram» (7. okt. 2026) — posisjonen til kartet, lagres ikke.
    path('r/api/hjelp/', views_lag.hjelp_view, name='park_lag_hjelp'),
]
