"""URL-konfigurasjon for oppdragsmodulen.

Mountet på ``/oppdrag/`` i ``myproject/urls.py``. Må stå FØR core av samme
grunn som patients og statistikk: core inneholder legacy-redirects som ellers
ville fanget ``/api/...``.
"""
from django.urls import path

from . import views, views_arkiv

urlpatterns = [
    # Én URL, to grensesnitt. Hvilket avgjøres av om kontoen er knyttet til en
    # Enhet — ikke av tilgangsnivået. Se views_common.er_enhetskonto.
    path('', views.index_view, name='oppdrag_index'),

    path('api/enheter/', views.enheter_view, name='oppdrag_api_enheter'),
    path('api/enheter/<int:pk>/', views.enhet_detalj_view, name='oppdrag_api_enhet_detalj'),
    path('api/enheter/<int:pk>/vakt/', views.enhet_vakt_view, name='oppdrag_api_enhet_vakt'),
    path('api/lokasjoner/', views.lokasjoner_view, name='oppdrag_api_lokasjoner'),
    path('api/lokasjoner/<int:pk>/', views.lokasjon_detalj_view,
         name='oppdrag_api_lokasjon_detalj'),
    path('api/oppdrag/', views.oppdrag_liste_view, name='oppdrag_api_liste'),
    path('api/oppdrag/<int:pk>/', views.oppdrag_detalj_view, name='oppdrag_api_detalj'),
    path('api/oppdrag/<int:pk>/flytt/', views.flytt_view, name='oppdrag_api_flytt'),
    # Enhetene på oppdraget (flere enheter, 11. sep. 2026). POST varsler en
    # til, DELETE tar henne av mens hun venter. Under den: sentralbordets
    # føring av *hennes* status (§9) — samme form som bilens stempling, men
    # med enheten i URL-en og tidspunktet i kroppen — og gjenåpning av «Ledig».
    path('api/oppdrag/<int:pk>/enheter/<int:enhet_pk>/', views.oppdragsenhet_view,
         name='oppdrag_api_oppdragsenhet'),
    path('api/oppdrag/<int:pk>/enheter/<int:enhet_pk>/status/<str:overgang>/<str:sted>/',
         views.foering_view, name='oppdrag_api_foering_sted'),
    path('api/oppdrag/<int:pk>/enheter/<int:enhet_pk>/status/<str:overgang>/',
         views.foering_view, name='oppdrag_api_foering'),
    path('api/oppdrag/<int:pk>/enheter/<int:enhet_pk>/gjenaapne/', views.gjenaapne_view,
         name='oppdrag_api_gjenaapne'),
    path('api/oppdrag/<int:pk>/enheter/<int:enhet_pk>/angre/', views.angre_view,
         name='oppdrag_api_angre'),
    # Ett navngitt endepunkt per overgang. Navnene er statusverdiene selv,
    # og settet håndheves i viewet mot `services.STEMPLBARE` — utledet fra
    # overgangstabellen, ikke skrevet ned på nytt her.
    # Stedet i URL-en, ikke i kroppen: stemplingsendepunktet leser ingen
    # domenefelt fra kroppen (rollemodellen §3.2), og «Avreist til Sykehus»
    # er ett navngitt endepunkt til, ikke et felt.
    path('api/oppdrag/<int:pk>/status/<str:overgang>/<str:sted>/', views.stempling_view,
         name='oppdrag_api_stempling_sted'),
    path('api/oppdrag/<int:pk>/grovsortering/<str:verdi>/', views.grovsortering_view,
         name='oppdrag_api_grovsortering'),
    path('api/oppdrag/<int:pk>/status/<str:overgang>/', views.stempling_view,
         name='oppdrag_api_stempling'),
    # Arkivering = rydding av tavla, ikke vaktarkivet. POST arkiverer,
    # DELETE henter tilbake — den er reversibel, og URL-en sier det.
    path('api/oppdrag/<int:pk>/historikk/', views.historikk_view,
         name='oppdrag_api_historikker'),
    path('api/historikk/', views.historikk_liste_view, name='oppdrag_api_historikk'),
    # Vaktarkivet (fase 7). Merk forskjellen fra `api/historikk/` rett over:
    # den er rydding av tavla og reversibel, dette er frysing med signatur.
    path('api/arkiv/', views_arkiv.arkiv_liste_view, name='oppdrag_api_arkiv_liste'),
    path('api/arkiv/<int:pk>/', views_arkiv.arkiv_detalj_view,
         name='oppdrag_api_arkiv_detalj'),
    # Korreksjon av tidspunkt. Ligger på statusmeldingen og ikke på oppdraget:
    # det er én rad som rettes, og rettingen blir en ny rad ved siden av den.
    path('api/statusmelding/<int:pk>/korriger/', views.korriger_view,
         name='oppdrag_api_korriger'),
]
