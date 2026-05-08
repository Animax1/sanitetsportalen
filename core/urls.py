"""URL-konfigurasjon for core-appen.

Inneholder:
- Portal-dashboardet på `/`
- Legacy-redirects fra gamle root-URL-er til /pasienter/-prefiks

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

    # ── Legacy-redirects ────────────────────────────────────────────────────
    # Gamle URL-er som flyttet til /pasienter/ i Fase 2.
    # Bruker re_path med ettykke regex for å matche alle subpaths under hver
    # legacy-prefiks. View-funksjonen leser request.path direkte, så
    # path-converteren trenger bare å AKSEPTERE matchet — ikke gi parameter.
    #
    # OBS: Disse må stå ETTER alle vanlige routes for å unngå at de "stjeler"
    # nye dashboard-routes. I praksis fanger de kun root-prefiks som ikke
    # lenger har en aktiv route.

    # /api/<alt> → /pasienter/api/<alt>
    re_path(r'^api/.*$', views.legacy_root_redirect, name='legacy_api'),

    # /admin/server-status/<alt> → /pasienter/admin/server-status/<alt>
    # OBS: matcher KUN /admin/server-status/, ikke Django-admin på /django-admin/
    re_path(
        r'^admin/server-status/.*$',
        views.legacy_root_redirect,
        name='legacy_admin_server_status',
    ),
    # /admin/server-status/ uten subpath
    path(
        'admin/server-status/',
        views.legacy_root_redirect,
        name='legacy_admin_server_status_root',
    ),
]
