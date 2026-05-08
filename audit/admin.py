"""Django Admin-registrering for audit-appen."""
from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog (kun lesing)."""
    list_display = ['action', 'table_name', 'record_id', 'field_name', 'user', 'ip', 'created_at']
    list_filter = ['action', 'table_name']
    search_fields = ['table_name', 'field_name', 'old_value', 'new_value']
    readonly_fields = [f.name for f in AuditLog._meta.get_fields()]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
