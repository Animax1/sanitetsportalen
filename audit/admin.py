"""Django Admin-registrering for audit-appen."""
from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog (kun lesing).

    Fase 3a: ``app_label`` lagt til i list_display og list_filter slik at admin
    kan filtrere logg per modul (pasienter, accounts, framtidige moduler).
    """
    list_display = [
        'created_at',
        'app_label',
        'action',
        'table_name',
        'record_id',
        'field_name',
        'user',
        'ip',
    ]
    list_filter = ['app_label', 'action', 'table_name']
    search_fields = ['app_label', 'table_name', 'field_name', 'old_value', 'new_value']
    readonly_fields = [f.name for f in AuditLog._meta.get_fields()]
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
