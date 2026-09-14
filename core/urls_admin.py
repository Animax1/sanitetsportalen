"""Alt under `/portal-admin/`, på ett sted (14. sep. 2026).

Rutene lå spredt på tre filer — `myproject/urls.py` (server-status),
`core/urls.py` (innstillinger, moduler, auditlogg, backup) og
`accounts/urls.py` (brukere, innloggingslogg). Ingen kunne se hele
adminflaten uten å lete tre steder, og `PortalAdminRuteneErStengtTests` måtte
gå gjennom `urlpatterns` for å være sikker på at den dekket alt.
Se `docs/TEKNISK_GJELD.md` §3.2.

**Stiene og navnene er nøyaktig de samme som før.** `PortalAdminKartetTests`
låser hele kartet til literale verdier: en `{% url %}` i en mal som slutter å
virke, eller en bokmerket adresse som dør, er en feil brukeren møter og ikke
en testen fanger — med mindre kartet står skrevet.

At dette er en `include`, og ikke ruter i tre filer, er også grunnen til at
`accounts` og `core` kan eie hver sine views uten at flaten deles opp: fila
her bestemmer *adressen*, appene bestemmer *oppførselen*.
"""
from django.urls import path

from accounts import views as accounts_views
from core import admin_status, views_admin, views_backup

#: **Ett navnerom for hele adminflaten.**
#:
#: Rutene lå i to apper med hver sin `app_name`, så navnene var
#: `portaladmin:user_list` og `portaladmin:backup_admin` — to prefikser for det samme
#: skjermbildet, avhengig av hvilken app som tilfeldigvis eide viewet. Nå
#: heter de `portaladmin:...` uansett, fordi det er flaten og ikke appen som
#: er det brukeren og malene forholder seg til.
#:
#: `accounts` og `core` beholder sine navnerom for alt annet — innlogging,
#: min profil, varsler.
app_name = 'portaladmin'

urlpatterns = [
    # ── Portalinnstillinger, moduler og logg ────────────────────────────────
    path('innstillinger/', views_admin.portal_settings_view,
         name='portal_settings'),
    path('moduler/', views_admin.module_admin_list_view,
         name='module_admin_list'),
    path('moduler/<slug:slug>/', views_admin.module_admin_edit_view,
         name='module_admin_edit'),
    path('auditlog/', views_admin.audit_log_list_view,
         name='audit_log_list'),
    path('auditlog/eksport.csv', views_admin.audit_log_csv_export_view,
         name='audit_log_csv_export'),

    # ── Backup ──────────────────────────────────────────────────────────────
    # De spesifikke stiene står FØR `<slug>`-stiene, ellers ville «plan» og
    # «kjor» blitt lest som modul-slugger.
    path('backup/', views_backup.backup_admin_view,
         name='backup_admin'),
    path('backup/plan/<slug:slug>/', views_backup.backup_admin_plan_view,
         name='backup_admin_plan'),
    path('backup/kjor/', views_backup.backup_admin_run_view,
         name='backup_admin_run_alle'),
    path('backup/kjor/<slug:slug>/', views_backup.backup_admin_run_view,
         name='backup_admin_run'),
    path('backup/<slug:slug>/restore/<int:pk>/', views_backup.backup_admin_restore_view,
         name='backup_admin_restore'),
    path('backup/<slug:slug>/slett/<int:pk>/', views_backup.backup_admin_delete_view,
         name='backup_admin_delete'),

    # ── Brukere og innlogginger ─────────────────────────────────────────────
    path('brukere/', accounts_views.user_list_view, name='user_list'),
    path('brukere/ny/', accounts_views.user_create_view, name='user_create'),
    path('brukere/<int:pk>/', accounts_views.user_detail_view, name='user_detail'),
    path('brukere/<int:pk>/slett/', accounts_views.user_delete_view,
         name='user_delete'),
    path('innloggingslogg/', accounts_views.login_event_list_view,
         name='login_event_list'),

    # ── Drift ───────────────────────────────────────────────────────────────
    path('server-status/', admin_status.admin_status_view,
         name='admin_server_status'),
    path('server-status/json/', admin_status.admin_status_json,
         name='admin_server_status_json'),
    path('server-status/sessions/', admin_status.admin_sessions_list,
         name='admin_sessions_list'),
    path('server-status/sessions/kill/', admin_status.admin_session_kill,
         name='admin_session_kill'),
    path('server-status/sessions/kill-all/', admin_status.admin_session_kill_all,
         name='admin_session_kill_all'),
]
