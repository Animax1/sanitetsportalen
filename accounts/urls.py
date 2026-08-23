"""URL-konfigurasjon for accounts-appen.

Modulen mountes på **root** i ``myproject/urls.py``, ikke under et prefiks.
Grunnen er at appen har to typer flater som hører hjemme på hver sin sti:

- **Innlogging, utlogging og passordbytte** ligger under ``/accounts/``. De
  brukes av alle innloggede og er ikke administrasjon.
- **Brukeradministrasjon og innloggingslogg** ligger under ``/portal-admin/``,
  sammen med moduler, revisjonslogg, backup og server-status.

Samlingen under ett prefiks er ikke kosmetikk. ``MustChangePasswordMiddleware``
matcher stier med ``startswith``, og framtidige regler (rate-limiting,
ekstra rollesjekk) vil naturlig skrives på samme form. Lå brukeradministrasjonen
fortsatt under ``/accounts/``, ville en regel for ``/portal-admin/*`` stille
gått utenom nettopp den flaten som oppretter kontoer og deler ut admin-rollen.

URL-*navnene* er uendret (``accounts:user_list`` osv.) slik at maler og tester
ikke berøres av flyttingen.
"""
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'accounts'

urlpatterns = [
    # ── Innlogging og konto (alle brukere) ───────────────────────────────
    path('accounts/login/', views.login_view, name='login'),
    path('accounts/logout/', views.logout_view, name='logout'),
    path('accounts/change-password/', views.change_password_view, name='change_password'),
    # Invitasjonslenke. Åpen uten innlogging — sikkerheten ligger i at
    # tokenet er signert, utløper etter 3 døgn og dør når passordet settes.
    # Passord-reset. Begge er aapne uten innlogging; sikkerheten ligger i
    # at tokenet er signert, utloeper etter 1 time og doer naar passordet
    # settes. Se accounts/passord_reset.py.
    path('accounts/glemt-passord/', views.glemt_passord_view,
         name='glemt_passord'),
    path('accounts/reset/<str:token>/', views.passord_reset_view,
         name='passord_reset'),
    path('accounts/invitasjon/<str:token>/', views.invitasjon_view,
         name='invitasjon'),

    # ── Administrasjon (admin) ───────────────────────────────────────────
    path('portal-admin/brukere/', views.user_list_view, name='user_list'),
    path('portal-admin/brukere/ny/', views.user_create_view, name='user_create'),
    path('portal-admin/brukere/<int:pk>/', views.user_detail_view, name='user_detail'),
    path('portal-admin/brukere/<int:pk>/slett/', views.user_delete_view, name='user_delete'),
    path('portal-admin/innloggingslogg/', views.login_event_list_view, name='login_event_list'),

    # ── Permanente redirects fra de gamle stiene ─────────────────────────
    # Bokmerker og lenker i eldre dokumentasjon skal fortsatt virke.
    path(
        'accounts/users/',
        RedirectView.as_view(url='/portal-admin/brukere/', permanent=True),
    ),
    path(
        'accounts/users/ny/',
        RedirectView.as_view(url='/portal-admin/brukere/ny/', permanent=True),
    ),
    path(
        'accounts/users/<int:pk>/',
        RedirectView.as_view(url='/portal-admin/brukere/%(pk)s/', permanent=True),
    ),
]
