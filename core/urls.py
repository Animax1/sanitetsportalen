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

    # ── Legacy-redirects ────────────────────────────────────────────────────
    # Gamle URL-er som flyttet til /pasienter/ i Fase 2.
    # OBS: Disse må stå ETTER alle vanlige routes for å unngå at de "stjeler"
    # nye dashboard-routes. I praksis fanger de kun root-prefiks som ikke
    # lenger har en aktiv route.

    # /api/<alt> → /pasienter/api/<alt>
    re_path(r'^api/.*$', views.legacy_root_redirect, name='legacy_api'),

    # /admin/server-status/<alt> → /pasienter/admin/server-status/<alt>
    re_path(
        r'^admin/server-status/.*$',
        views.legacy_root_redirect,
        name='legacy_admin_server_status',
    ),
    path(
        'admin/server-status/',
        views.legacy_root_redirect,
        name='legacy_admin_server_status_root',
    ),
]
