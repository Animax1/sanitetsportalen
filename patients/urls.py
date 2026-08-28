"""URL-konfigurasjon for patients-appen."""
from django.urls import path, re_path
from django.shortcuts import redirect
from . import admin_status
from . import views_arkiv, views_patients, views_registre, views_stats

urlpatterns = [
    # Hoved-siden
    path('', views_patients.index_view, name='index'),

    # Innstillinger
    path('api/settings/', views_patients.settings_view, name='api_settings'),

    # Sesjonstimeout
    path('api/session-timeout/', views_patients.session_timeout_view, name='api_session_timeout'),

    # Pasienter
    path('api/patients/', views_patients.patients_list_view, name='api_patients_list'),
    path('api/patients/<int:pk>/', views_patients.patient_detail_view, name='api_patient_detail'),

    # Forstehjelpere
    path('api/forstehjelpere/', views_registre.forstehjelpere_view, name='api_forstehjelpere'),
    path('api/forstehjelpere/<int:pk>/', views_registre.forstehjelper_detail_view, name='api_forstehjelper_detail'),
    path('api/helsepersonell/', views_registre.helsepersonell_view, name='api_helsepersonell'),
    path('api/helsepersonell/<int:pk>/', views_registre.helsepersonell_detail_view, name='api_helsepersonell_detail'),

    # Reset testdata (kun admin)
    path('api/reset-active-year/', views_patients.reset_active_year_view, name='api_reset_active_year'),

    # Statistikk. Kun header-chipsene ligger igjen her; full statistikk
    # flyttet til statistikk-appen (/statistikk/api/full-stats/).
    path('api/stats/', views_stats.stats_view, name='api_stats'),

    # Videresending for klienter med gammel JS i cache. Uten den slutter
    # statistikken å oppdatere seg for alle som har siden åpen når deployen
    # treffer — og den feiler stille: loadStats() logger en advarsel og lar
    # forrige visning bli stående, så brukeren ser gamle tall uten beskjed.
    # 302, ikke 301: en 301 caches av nettleseren for godt, og stien bør
    # kunne tas i bruk igjen uten at gamle klienter sitter fast.
    path('api/full-stats/',
         lambda req: redirect('/statistikk/api/full-stats/'),
         name='api_full_stats_flyttet'),

    # Arkiver (gammel fil-basert)

    # VaktArkiv (database-basert arkiv)
    path('api/innstillinger/arkiv/', views_arkiv.arkiv_liste_view, name='api_arkiv_liste'),
    path('api/innstillinger/arkiv/lagre/', views_arkiv.arkiv_lagre_view, name='api_arkiv_lagre'),
    path('api/innstillinger/arkiv/<int:pk>/', views_arkiv.arkiv_detalj_view, name='api_arkiv_detalj'),
    path('api/innstillinger/arkiv/<int:pk>/full-stats/',
         lambda req, pk: redirect(f'/statistikk/api/arkiv/{pk}/full-stats/'),
         name='api_arkiv_full_stats_flyttet'),

    # Bakover-kompatibel redirect: /pasienter/admin/server-status/... → /portal-admin/server-status/...
    re_path(r'^admin/server-status/(?P<rest>.*)$',
            lambda req, rest='': redirect(f'/portal-admin/server-status/{rest}', permanent=True)),

    # Backup / Restore (kun admin)
    # Backup-endepunktene er fjernet (august 2026). Backup administreres samlet
    # på /portal-admin/backup/, med eget intervall og egen oppbevaring per modul.
]
