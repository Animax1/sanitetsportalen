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

from . import views_admin, views_portal, views_varsler

app_name = 'core'

urlpatterns = [
    # Portal-forside (krever innlogging)
    path('', views_portal.portal_dashboard_view, name='portal_dashboard'),

    # Min profil (alle innloggede brukere)
    path('min-profil/', views_portal.profile_view, name='profile'),

    # ── Admin-UI ────────────────────────────────────────────────────────────
    # Rutene under /portal-admin/ flyttet til `core/urls_admin.py` 14. sep.
    # 2026, og inkluderes derfra i `myproject/urls.py`. Se gjeldspunkt 3.2.

    # ── Fase 5: Varsler ─────────────────────────────────────────────────────
    path(
        'varsler/',
        views_varsler.notification_list_view,
        name='notification_list',
    ),
    path(
        'varsler/<int:pk>/lest/',
        views_varsler.notification_mark_read_view,
        name='notification_mark_read',
    ),
    path(
        'varsler/marker-alle-lest/',
        views_varsler.notification_mark_all_read_view,
        name='notification_mark_all_read',
    ),
    path(
        'api/varsler/ulest-antall/',
        views_varsler.notification_unread_count_view,
        name='notification_unread_count',
    ),
    path(
        'api/varsler/',
        views_varsler.notification_api_list_view,
        name='notification_api_list',
    ),
    path(
        'api/varsler/<int:pk>/lest/',
        views_varsler.notification_api_mark_read_view,
        name='notification_api_mark_read',
    ),
    path(
        'api/varsler/marker-alle-lest/',
        views_varsler.notification_api_mark_all_read_view,
        name='notification_api_mark_all_read',
    ),

    # Endringsnumrene (24. sep. 2026, `core/endringer.py`). Før legacy-
    # redirecten under, som ellers ville sendt `/api/…` til `/pasienter/`.
    path('api/endringer/', views_portal.endringer_view, name='endringer'),

    # ── Legacy-redirects ───────────────────────────────────────────────
    # Gamle URL-er som flyttet til /pasienter/ i Fase 2.
    # OBS: Disse må stå ETTER alle vanlige routes for å unngå at de "stjeler"
    # nye dashboard-routes. I praksis fanger de kun root-prefiks som ikke
    # lenger har en aktiv route.

    # /api/<alt> → /pasienter/api/<alt>
    re_path(r'^api/.*$', views_admin.legacy_root_redirect, name='legacy_api'),

    # /admin/server-status/<alt> → /portal-admin/server-status/<alt>
    re_path(
        r'^admin/server-status/(?P<rest>.*)$',
        lambda req, rest='': redirect(f'/portal-admin/server-status/{rest}', permanent=True),
        name='legacy_admin_server_status',
    ),
]
