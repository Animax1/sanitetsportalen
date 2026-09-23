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
    # Eget ansvarsmerke (§5.1, pulje 6). Vises, styrer ingenting.
    path('api/ansvar/', views.ansvar_view, name='ko_api_ansvar'),
    # Loggen (pulje 2). **Retting og fjerning er navngitte stier**, ikke et
    # felt i kroppen på skriveendepunktet: de to krever hvert sitt
    # tilgangsnivå, og et fritt ledd i kroppen ville flyttet den forskjellen
    # inn i en `if` der ingen dekoratørtest ser den.
    path('api/logg/', views.logg_view, name='ko_api_logg'),
    path('api/logg/ny/', views.logg_skriv_view, name='ko_api_logg_ny'),
    path('api/logg/<int:pk>/rett/', views.logg_rett_view, name='ko_api_logg_rett'),
    path('api/logg/<int:pk>/fjern/', views.logg_fjern_view, name='ko_api_logg_fjern'),
    # Festing (18. sep. 2026) — to stier, som rett/fjern: én regel per sti.
    path('api/logg/<int:pk>/fest/', views.logg_fest_view, name='ko_api_logg_fest'),
    path('api/logg/<int:pk>/losne/', views.logg_losne_view, name='ko_api_logg_losne'),
    # Deling med enhetene (19. sep. 2026) — samme form: én regel per sti.
    path('api/logg/<int:pk>/del/', views.logg_del_view, name='ko_api_logg_del'),
    path('api/logg/<int:pk>/angre-deling/', views.logg_angre_deling_view,
         name='ko_api_logg_angre_deling'),
    # Hendelsene (pulje 5). Lesingen går med logg-pollen; skrivingen har
    # navngitte stier, som loggen — én regel per sti.
    path('api/hendelser/ny/', views.hendelse_ny_view, name='ko_api_hendelse_ny'),
    path('api/hendelser/<int:pk>/rediger/', views.hendelse_rediger_view,
         name='ko_api_hendelse_rediger'),
    path('api/hendelser/<int:pk>/lukk/', views.hendelse_lukk_view,
         name='ko_api_hendelse_lukk'),
    path('api/hendelser/<int:pk>/gjenapne/', views.hendelse_gjenapne_view,
         name='ko_api_hendelse_gjenapne'),
    path('api/hendelser/<int:pk>/prioritet/', views.hendelse_prioritet_view,
         name='ko_api_hendelse_prioritet'),
    path('api/hendelser/<int:pk>/bli-med/', views.hendelse_bli_med_view,
         name='ko_api_hendelse_bli_med'),
    # Lagene på hendelsen (19. sep. 2026): hele lista, differansen logges.
    path('api/hendelser/<int:pk>/lag/', views.hendelse_lag_view,
         name='ko_api_hendelse_lag'),
    # KO-innstillingene: ansvarsområdene (18. sep. 2026).
    path('api/ansvarsomraader/', views.ansvarsomraader_view, name='ko_api_ansvarsomraader'),
    path('api/ansvarsomraader/rekkefolge/', views.ansvarsomraader_rekkefolge_view,
         name='ko_api_ansvarsomraader_rekkefolge'),
    path('api/ansvarsomraader/<int:pk>/', views.ansvarsomraade_detalj_view,
         name='ko_api_ansvarsomraade_detalj'),
    # Nullstilling (18. sep. 2026): global admin, `confirm`, aktiv vakt.
    path('api/nullstill/<str:hva>/', views.nullstill_view, name='ko_api_nullstill'),
    # Tavla (22. sep. 2026): lesingen i ett svar, skrivingen i navngitte stier.
    path('api/tavle/', views.tavle_view, name='ko_api_tavle'),
    path('api/tavle/plasser/', views.tavle_plasser_view, name='ko_api_tavle_plasser'),
    path('api/tavle/uten-plass/', views.tavle_uten_plass_view, name='ko_api_tavle_uten_plass'),
    path('api/tavle/plasseringer/<int:pk>/', views.tavle_plassering_view,
         name='ko_api_tavle_plassering'),
    path('api/tavle/pauser/', views.tavle_pauser_view, name='ko_api_tavle_pauser'),
    path('api/tavle/pauser/<int:pk>/', views.tavle_pause_view, name='ko_api_tavle_pause'),
    path('api/tavle/pauser/<int:pk>/start/', views.tavle_pause_start_view,
         name='ko_api_tavle_pause_start'),
    path('api/tavle/oppsett/', views.tavle_oppsett_view, name='ko_api_tavle_oppsett'),
    # Programmet (tavleplanleggeren, steg 2 — 23. sep. 2026).
    path('api/program/', views.program_view, name='ko_api_program'),
    path('api/program/<int:pk>/', views.program_post_view, name='ko_api_program_post'),
    path('api/konserttyper/', views.konserttyper_view, name='ko_api_konserttyper'),
    path('api/konserttyper/rekkefolge/', views.konserttyper_rekkefolge_view,
         name='ko_api_konserttyper_rekkefolge'),
    path('api/konserttyper/<int:pk>/', views.konserttype_detalj_view, name='ko_api_konserttype_detalj'),
    path('api/kjennetegn/', views.kjennetegn_view, name='ko_api_kjennetegn'),
    path('api/kjennetegn/rekkefolge/', views.kjennetegn_rekkefolge_view,
         name='ko_api_kjennetegn_rekkefolge'),
    path('api/kjennetegn/<int:pk>/', views.kjennetegn_detalj_view, name='ko_api_kjennetegn_detalj'),
    # Grupperingen skrives her og ikke i `/oppdrag/api/`: `Oppdrag.hendelse`
    # er KOs peker, og oppdragsmodulen leser den bare.
    path('api/oppdrag/<int:pk>/hendelse/', views.oppdrag_hendelse_view,
         name='ko_api_oppdrag_hendelse'),
]
