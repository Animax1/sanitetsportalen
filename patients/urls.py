"""URL-konfigurasjon for patients-appen."""
from django.urls import path, re_path
from django.shortcuts import redirect
from . import views, admin_status

urlpatterns = [
    # Hoved-siden
    path('', views.index_view, name='index'),

    # Innstillinger
    path('api/settings/', views.settings_view, name='api_settings'),

    # Sesjonstimeout
    path('api/session-timeout/', views.session_timeout_view, name='api_session_timeout'),

    # Pasienter
    path('api/patients/', views.patients_list_view, name='api_patients_list'),
    path('api/patients/<int:pk>/', views.patient_detail_view, name='api_patient_detail'),

    # Forstehjelpere
    path('api/forstehjelpere/', views.forstehjelpere_view, name='api_forstehjelpere'),
    path('api/forstehjelpere/<int:pk>/', views.forstehjelper_detail_view, name='api_forstehjelper_detail'),
    path('api/helsepersonell/', views.helsepersonell_view, name='api_helsepersonell'),
    path('api/helsepersonell/<int:pk>/', views.helsepersonell_detail_view, name='api_helsepersonell_detail'),

    # Reset testdata (kun admin)
    path('api/reset-active-year/', views.reset_active_year_view, name='api_reset_active_year'),

    # Statistikk
    path('api/stats/', views.stats_view, name='api_stats'),
    path('api/full-stats/', views.full_stats_view, name='api_full_stats'),

    # Arkiver (gammel fil-basert)
    path('api/archives/', views.archives_view, name='api_archives'),

    # VaktArkiv (database-basert arkiv)
    path('api/innstillinger/arkiv/', views.arkiv_liste_view, name='api_arkiv_liste'),
    path('api/innstillinger/arkiv/lagre/', views.arkiv_lagre_view, name='api_arkiv_lagre'),
    path('api/innstillinger/arkiv/<int:pk>/', views.arkiv_detalj_view, name='api_arkiv_detalj'),
    path('api/innstillinger/arkiv/<int:pk>/full-stats/', views.arkiv_full_stats_view, name='api_arkiv_full_stats'),

    # Bakover-kompatibel redirect: /pasienter/admin/server-status/... → /portal-admin/server-status/...
    re_path(r'^admin/server-status/(?P<rest>.*)$',
            lambda req, rest='': redirect(f'/portal-admin/server-status/{rest}', permanent=True)),

    # Backup / Restore (kun admin)
    path('api/backup/',                   views.backup_list_view,       name='api_backup_list'),
    path('api/backup/config/',            views.backup_config_view,     name='api_backup_config'),
    path('api/backup/create/',            views.backup_create_now_view, name='api_backup_create'),
    path('api/backup/<int:pk>/restore/',  views.backup_restore_view,    name='api_backup_restore'),
    path('api/backup/<int:pk>/download/', views.backup_download_view,   name='api_backup_download'),
    path('api/backup/<int:pk>/',          views.backup_delete_view,     name='api_backup_delete'),
]
