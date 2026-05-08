"""Django-admin for core-appen.

Registrerer ``ModuleSettings`` med følgende sikkerhetslogikk:
- Kjernemoduler (``Module.is_core=True``) kan ikke deaktiveres via UI.
  ``enabled``-feltet vises som readonly for slike rader.
- ``slug`` og ``updated_at`` er readonly — slug må matche en registrert
  modul (settes av ``ensure_defaults_exist``), updated_at oppdateres
  automatisk av Django.
- ``updated_by`` settes automatisk fra ``request.user`` ved lagring.
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import ModuleSettings
from .modules import get_module


@admin.register(ModuleSettings)
class ModuleSettingsAdmin(admin.ModelAdmin):
    list_display = [
        'slug',
        'visningsnavn',
        'enabled',
        'kjerne_status',
        'backup_enabled',
        'updated_at',
        'updated_by',
    ]
    list_filter = ['enabled', 'backup_enabled']
    search_fields = ['slug', 'note']
    readonly_fields = ['slug', 'updated_at', 'updated_by', 'kjerne_status']
    fieldsets = (
        ('Modul', {
            'fields': ('slug', 'kjerne_status'),
        }),
        ('Status', {
            'fields': ('enabled', 'backup_enabled', 'note'),
        }),
        ('Audit', {
            'fields': ('updated_at', 'updated_by'),
        }),
    )

    @admin.display(description='Visningsnavn')
    def visningsnavn(self, obj: ModuleSettings) -> str:
        module = get_module(obj.slug)
        return module.name if module else f'(ukjent: {obj.slug})'

    @admin.display(description='Kjernemodul', boolean=False)
    def kjerne_status(self, obj: ModuleSettings) -> str:
        module = get_module(obj.slug)
        if module is None:
            return format_html('<span style="color:#dc3545">Ukjent slug</span>')
        if module.is_core:
            return format_html(
                '<span style="color:#0c63e4">Ja — kan ikke deaktiveres</span>'
            )
        return 'Nei'

    def has_add_permission(self, request):
        # Rader opprettes automatisk av ensure_defaults_exist via post_migrate.
        # Manuell oppretting fra admin er forvirrende og kan gi inkonsistens.
        return False

    def has_delete_permission(self, request, obj=None):
        # Sletting bryter dashboard-/nav-rendring frem til neste post_migrate.
        # Anbefaling: deaktiver i stedet for å slette.
        return False

    def get_readonly_fields(self, request, obj=None):
        """Gjør 'enabled' readonly for kjernemoduler."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            module = get_module(obj.slug)
            if module is not None and module.is_core:
                readonly.append('enabled')
        return readonly

    def save_model(self, request, obj, form, change):
        """Sett updated_by automatisk og blokker deaktivering av kjernemoduler."""
        module = get_module(obj.slug)
        if module is not None and module.is_core and not obj.enabled:
            # Defensiv guard: hvis noen omgår readonly_fields (f.eks. via API)
            # tvinger vi enabled tilbake til True for kjernemoduler.
            obj.enabled = True
        if request.user.is_authenticated:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)
