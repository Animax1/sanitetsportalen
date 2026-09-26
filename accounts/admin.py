"""Django Admin-registrering for accounts-appen — **skrivebeskyttet**.

Django-admin rutes bare under `DEBUG` (S1), så dette er et utviklerverktøy for
å *se* kontoene lokalt. **Endringer skjer i portalens brukeradministrasjon**
(`/portal-admin/brukere/`), der sperrene og auditsporet er.

Fram til 26. sep. 2026 (B4) kunne panelet opprette og endre kontoer med egne
skjemaer som skrev `role` og `is_superuser` rett inn — altså lage en superbruker
nummer to, og degradere uten sperra «siste admin». Frysehandlingen her skrev
ingen auditrad. Ingen av veiene var åpne i prod, men en vei rundt sperrene er
en vei rundt dem, også lokalt. André valgte skrivebeskyttet framfor å fjerne:
å bla i kontoene er nyttig; å endre dem her er det ikke.

`RollenSettesBareGjennomSkjemaeneTests` holder at ingen skjema utenom
`accounts/forms.py` får `role` eller `is_superuser` i `Meta.fields` igjen.
"""
from django.contrib import admin

from .models import CustomUser, LoginEvent


class _BareLesing:
    """Se, ikke endre — heller ikke som superbruker."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomUser)
class CustomUserAdmin(_BareLesing, admin.ModelAdmin):
    list_display = ['username', 'email', 'role', 'is_active', 'is_staff', 'mfa_required',
                    'last_login_at']
    list_filter = ['role', 'is_active', 'is_staff', 'mfa_required']
    search_fields = ['username', 'email']
    ordering = ['username']
    # Passordhashen vises ikke, heller ikke lesbart.
    exclude = ['password']


@admin.register(LoginEvent)
class LoginEventAdmin(_BareLesing, admin.ModelAdmin):
    """Innloggingsloggen er et spor. Å kunne slette rader i den her var den
    samme veien rundt som skjemaene over."""

    list_display = ['username_attempt', 'user', 'success', 'event_type', 'ip', 'created_at']
    list_filter = ['success', 'event_type']
    search_fields = ['username_attempt', 'ip']
    date_hierarchy = 'created_at'
