"""Tilgangskontroll-mixins for klassebaserte views."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


class RoleRequiredMixin(LoginRequiredMixin):
    """Krev spesifikke roller for klassebaserte views."""

    required_roles = ()

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        # Hvis super() returnerte redirect (ikke autentisert), la det gå gjennom
        if hasattr(response, 'status_code') and response.status_code in (301, 302):
            return response
        if self.required_roles and request.user.role not in self.required_roles:
            raise PermissionDenied
        return response


class AdminRequiredMixin(RoleRequiredMixin):
    """Krev admin-rolle."""
    required_roles = ('admin',)


class WriteRequiredMixin(RoleRequiredMixin):
    """Krev skrivetilgang (admin, lead eller read_write)."""
    required_roles = ('admin', 'lead', 'read_write')


class StatsRequiredMixin(RoleRequiredMixin):
    """Krev tilgang til statistikk-dashboard (admin, lead eller lead_view)."""
    required_roles = ('admin', 'lead', 'lead_view')


class DatasetScopeAllMixin(RoleRequiredMixin):
    """Krev rett til å se alle datasett/år (admin, lead eller lead_view)."""
    required_roles = ('admin', 'lead', 'lead_view')


class PasswordChangeRequiredMixin:
    """
    Redirect til passordbytte hvis must_change_password er satt.
    Brukes i kombinasjon med LoginRequiredMixin.
    """
    def dispatch(self, request, *args, **kwargs):
        if (request.user.is_authenticated
                and request.user.must_change_password):
            return redirect('accounts:change_password')
        return super().dispatch(request, *args, **kwargs)
