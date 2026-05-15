"""URL-konfigurasjon for core-appen.

Inneholder:
- Portal-dashboard på ``/`` (Fase 2)
- Min profil på ``/min-profil/`` (Fase 3b)
- Admin-UI for moduler og auditlogg på ``/portal-admin/...`` (Fase 3b)
- Legacy-redirects fra gamle root-URL-er til /pasienter/-prefiks (Fase 2)

Legacy-redirects gjelder kun URL-er som tidligere ble servert direkte fra root
(`/api/...`, `/admin/server-status/...`). Andre root-URL-er som `/healthz/`,
`/django-admin/`, `/accounts/...` er IKKE påvirket — de håndteres uendret av
myproject/urls.py.
"""
from django.shortcuts import redirect
from django.urls import path, re_path

from . import views

app_name = 'core'

urlpatterns = [
    # Portal-forside (krever innlogging)
    path('', views.portal_dashboard_view, name='portal_dashboard'),

    # Min profil (alle innloggede brukere)
    path('min-profil/', views.profile_view, name='profile'),

    # ── Admin-UI (Fase 3b) ──────────────────────────────────────────────────
    # Plasseres under /portal-admin/ for å skille tydelig fra /django-admin/.
    path(
        'portal-admin/moduler/',
        views.module_admin_list_view,
        name='module_admin_list',
    ),
    path(
        'portal-admin/moduler/<slug:slug>/',
        views.module_admin_edit_view,
        name='module_admin_edit',
    ),
    path(
        'portal-admin/auditlog/',
        views.audit_log_list_view,
        name='audit_log_list',
    ),
    path(
        'portal-admin/auditlog/eksport.csv',
        views.audit_log_csv_export_view,
        name='audit_log_csv_export',
    ),

    # ── Backup-admin (Fase 4) ────────────────────────────────────────
    path(
        'portal-admin/backup/',
        views.backup_admin_overview_view,
        name='backup_admin_overview',
    ),
    path(
        'portal-admin/backup/<slug:slug>/',
        views.backup_admin_module_view,
        name='backup_admin_module',
    ),
    path(
        'portal-admin/backup/<slug:slug>/run/',
        views.backup_admin_run_view,
        name='backup_admin_run',
    ),
    path(
        'portal-admin/backup/<slug:slug>/restore/<int:pk>/',
        views.backup_admin_restore_view,
        name='backup_admin_restore',
    ),
    path(
        'portal-admin/backup/<slug:slug>/last-ned/<int:pk>/',
        views.backup_admin_download_view,
        name='backup_admin_download',
    ),
    path(
        'portal-admin/backup/<slug:slug>/slett/<int:pk>/',
        views.backup_admin_delete_view,
        name='backup_admin_delete',
    ),

    # ── Fase 5: Varsler ─────────────────────────────────────────────────────
    path(
        'varsler/',
        views.notification_list_view,
        name='notification_list',
    ),
    path(
        'varsler/<int:pk>/lest/',
        views.notification_mark_read_view,
        name='notification_mark_read',
    ),
    path(
        'varsler/marker-alle-lest/',
        views.notification_mark_all_read_view,
        name='notification_mark_all_read',
    ),
    path(
        'api/varsler/ulest-antall/',
        views.notification_unread_count_view,
        name='notification_unread_count',
    ),
    path(
        'api/varsler/',
        views.notification_api_list_view,
        name='notification_api_list',
    ),
    path(
        'api/varsler/<int:pk>/lest/',
        views.notification_api_mark_read_view,
        name='notification_api_mark_read',
    ),
    path(
        'api/varsler/marker-alle-lest/',
        views.notification_api_mark_all_read_view,
        name='notification_api_mark_all_read',
    ),

    # ── Legacy-redirects ───────────────────────────────────────────────
    # Gamle URL-er som flyttet til /pasienter/ i Fase 2.
    # OBS: Disse må stå ETTER alle vanlige routes for å unngå at de "stjeler"
    # nye dashboard-routes. I praksis fanger de kun root-prefiks som ikke
    # lenger har en aktiv route.

    # /api/<alt> → /pasienter/api/<alt>
    re_path(r'^api/.*$', views.legacy_root_redirect, name='legacy_api'),

    # /admin/server-status/<alt> → /portal-admin/server-status/<alt>
    re_path(
        r'^admin/server-status/(?P<rest>.*)$',
        lambda req, rest='': redirect(f'/portal-admin/server-status/{rest}', permanent=True),
        name='legacy_admin_server_status',
    ),
]
