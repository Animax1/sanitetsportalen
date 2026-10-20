"""URL-konfigurasjon for KO-modulen.

Mountet på ``/ko/`` i ``myproject/urls.py``, og **før** ``core`` av samme grunn
som patients, statistikk, oppdrag og vaktliste: core inneholder
legacy-videresendinger som ellers ville fanget ``/api/...``.

URL-navnene har `ko_`-prefiks fordi navnerommet er globalt (ingen
``app_name``), som i de andre modulene.
"""
from django.urls import path

from . import (views, views_hendelser, views_innstillinger, views_program, views_tavle,
               views_utskrift)

urlpatterns = [
    path('', views.index_view, name='ko_index'),
    # Utskriften av loggen (13. okt. 2026): en side, ikke et API — den
    # rendres på serveren fra de samme radene som skjermen.
    path('utskrift/', views_utskrift.utskrift_view, name='ko_utskrift'),
    # Service workeren som holder utskriften uten nett. Ingen innlogging —
    # se `sw_view`.
    path('sw.js', views_utskrift.sw_view, name='ko_sw'),
    # «Åpne kartet» (19. okt. 2026): billett til kart.sanitet.net, postet videre.
    path('kart/', views.kart_view, name='ko_kart'),
    path('api/tilstede/', views.tilstede_view, name='ko_api_tilstede'),
    # «Lagre oppsettet» (20. okt. 2026): vinduenes oppsett på kontoen.
    path('api/oppsett/', views.oppsett_view, name='ko_api_oppsett'),
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
    path('api/logg/<int:pk>/krever-haandtering/', views.logg_krever_haandtering_view,
         name='ko_api_logg_krever_haandtering'),
    path('api/logg/<int:pk>/haandtert/', views.logg_haandtert_view, name='ko_api_logg_haandtert'),
    # Deling med enhetene (19. sep. 2026) — samme form: én regel per sti.
    path('api/logg/<int:pk>/del/', views.logg_del_view, name='ko_api_logg_del'),
    path('api/logg/<int:pk>/angre-deling/', views.logg_angre_deling_view,
         name='ko_api_logg_angre_deling'),
    # Hendelsene (pulje 5). Lesingen går med logg-pollen; skrivingen har
    # navngitte stier, som loggen — én regel per sti.
    path('api/hendelser/ny/', views_hendelser.hendelse_ny_view, name='ko_api_hendelse_ny'),
    path('api/hendelser/<int:pk>/rediger/', views_hendelser.hendelse_rediger_view,
         name='ko_api_hendelse_rediger'),
    path('api/hendelser/<int:pk>/lukk/', views_hendelser.hendelse_lukk_view,
         name='ko_api_hendelse_lukk'),
    path('api/hendelser/<int:pk>/gjenapne/', views_hendelser.hendelse_gjenapne_view,
         name='ko_api_hendelse_gjenapne'),
    path('api/hendelser/<int:pk>/prioritet/', views_hendelser.hendelse_prioritet_view,
         name='ko_api_hendelse_prioritet'),
    path('api/hendelser/<int:pk>/bli-med/', views_hendelser.hendelse_bli_med_view,
         name='ko_api_hendelse_bli_med'),
    # Lesemerket (27. sep. 2026): «nytt siden sist du åpnet hendelsen».
    path('api/hendelser/<int:pk>/lest/', views_hendelser.hendelse_lest_view,
         name='ko_api_hendelse_lest'),
    # Lagene på hendelsen (19. sep. 2026): hele lista, differansen logges.
    path('api/hendelser/<int:pk>/beskrivelse/', views_hendelser.hendelse_beskrivelse_view,
         name='ko_api_hendelse_beskrivelse'),
    path('api/hendelser/<int:pk>/varsling/', views_hendelser.hendelse_varsling_view,
         name='ko_api_hendelse_varsling'),
    path('api/hendelser/<int:pk>/talegruppe/', views_hendelser.hendelse_talegruppe_view,
         name='ko_api_hendelse_talegruppe'),
    path('api/hendelser/<int:pk>/lag/', views_hendelser.hendelse_lag_view,
         name='ko_api_hendelse_lag'),
    # KO-innstillingene: ansvarsområdene (18. sep. 2026).
    path('api/ansvarsomraader/', views_innstillinger.ansvarsomraader_view, name='ko_api_ansvarsomraader'),
    path('api/ansvarsomraader/rekkefolge/', views_innstillinger.ansvarsomraader_rekkefolge_view,
         name='ko_api_ansvarsomraader_rekkefolge'),
    path('api/ansvarsomraader/<int:pk>/', views_innstillinger.ansvarsomraade_detalj_view,
         name='ko_api_ansvarsomraade_detalj'),
    # Nullstilling (18. sep. 2026): global admin, `confirm`, aktiv vakt.
    path('api/nullstill/<str:hva>/', views_innstillinger.nullstill_view, name='ko_api_nullstill'),
    # Tavla (22. sep. 2026): lesingen i ett svar, skrivingen i navngitte stier.
    path('api/tavle/', views_tavle.tavle_view, name='ko_api_tavle'),
    path('api/tavle/plasser/', views_tavle.tavle_plasser_view, name='ko_api_tavle_plasser'),
    path('api/tavle/uten-plass/', views_tavle.tavle_uten_plass_view, name='ko_api_tavle_uten_plass'),
    path('api/tavle/plasseringer/<int:pk>/', views_tavle.tavle_plassering_view,
         name='ko_api_tavle_plassering'),
    path('api/tavle/pauser/', views_tavle.tavle_pauser_view, name='ko_api_tavle_pauser'),
    path('api/tavle/pauser/<str:ref>/', views_tavle.tavle_pause_view, name='ko_api_tavle_pause'),
    path('api/tavle/pauser/<str:ref>/start/', views_tavle.tavle_pause_start_view,
         name='ko_api_tavle_pause_start'),
    path('api/tavle/oppsett/', views_tavle.tavle_oppsett_view, name='ko_api_tavle_oppsett'),
    # Programmet (tavleplanleggeren, steg 2 — 23. sep. 2026).
    path('api/program/', views_program.program_view, name='ko_api_program'),
    path('api/program/dekning/', views_program.program_dekning_view, name='ko_api_program_dekning'),
    path('api/program/etterpaa/', views_program.program_etterpaa_view, name='ko_api_program_etterpaa'),
    path('api/program/kopier/', views_program.program_kopier_view, name='ko_api_program_kopier'),
    path('api/program/<int:pk>/', views_program.program_post_view, name='ko_api_program_post'),
    path('api/konserttyper/', views_innstillinger.konserttyper_view, name='ko_api_konserttyper'),
    path('api/konserttyper/rekkefolge/', views_innstillinger.konserttyper_rekkefolge_view,
         name='ko_api_konserttyper_rekkefolge'),
    path('api/konserttyper/<int:pk>/', views_innstillinger.konserttype_detalj_view, name='ko_api_konserttype_detalj'),
    path('api/kjennetegn/', views_innstillinger.kjennetegn_view, name='ko_api_kjennetegn'),
    path('api/kjennetegn/rekkefolge/', views_innstillinger.kjennetegn_rekkefolge_view,
         name='ko_api_kjennetegn_rekkefolge'),
    path('api/kjennetegn/<int:pk>/', views_innstillinger.kjennetegn_detalj_view, name='ko_api_kjennetegn_detalj'),
    path('api/eksterne/', views_innstillinger.eksterne_view, name='ko_api_eksterne'),
    path('api/eksterne/rekkefolge/', views_innstillinger.eksterne_rekkefolge_view,
         name='ko_api_eksterne_rekkefolge'),
    path('api/eksterne/<int:pk>/', views_innstillinger.ekstern_detalj_view, name='ko_api_ekstern_detalj'),
    path('api/talegrupper/', views_innstillinger.talegrupper_view, name='ko_api_talegrupper'),
    path('api/talegrupper/rekkefolge/', views_innstillinger.talegrupper_rekkefolge_view,
         name='ko_api_talegrupper_rekkefolge'),
    path('api/talegrupper/<int:pk>/', views_innstillinger.talegruppe_detalj_view,
         name='ko_api_talegruppe_detalj'),
    # Grupperingen skrives her og ikke i `/oppdrag/api/`: `Oppdrag.hendelse`
    # er KOs peker, og oppdragsmodulen leser den bare.
    path('api/oppdrag/<int:pk>/hendelse/', views_hendelser.oppdrag_hendelse_view,
         name='ko_api_oppdrag_hendelse'),
]
