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

    # Statistikk
    path('api/stats/', views_stats.stats_view, name='api_stats'),
    path('api/full-stats/', views_stats.full_stats_view, name='api_full_stats'),

    # Arkiver (gammel fil-basert)

    # VaktArkiv (database-basert arkiv)
    path('api/innstillinger/arkiv/', views_arkiv.arkiv_liste_view, name='api_arkiv_liste'),
    path('api/innstillinger/arkiv/lagre/', views_arkiv.arkiv_lagre_view, name='api_arkiv_lagre'),
    path('api/innstillinger/arkiv/<int:pk>/', views_arkiv.arkiv_detalj_view, name='api_arkiv_detalj'),
    path('api/innstillinger/arkiv/<int:pk>/full-stats/', views_arkiv.arkiv_full_stats_view, name='api_arkiv_full_stats'),

    # Bakover-kompatibel redirect: /pasienter/admin/server-status/... → /portal-admin/server-status/...
    re_path(r'^admin/server-status/(?P<rest>.*)$',
            lambda req, rest='': redirect(f'/portal-admin/server-status/{rest}', permanent=True)),

    # Backup / Restore (kun admin)
    # Backup-endepunktene er fjernet (august 2026). Backup administreres samlet
    # på /portal-admin/backup/, med eget intervall og egen oppbevaring per modul.
]
