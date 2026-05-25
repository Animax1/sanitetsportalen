"""Django Admin-registrering for patients-appen."""
from django.contrib import admin

from .models import Patient, AppSetting, Forstehjelper


@admin.register(Forstehjelper)
class ForstehjelperAdmin(admin.ModelAdmin):
    """Admin for Forstehjelper-modellen."""

    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    """Admin for Patient-modellen."""

    list_display = [
        'pasientnummer', 'year', 'problemstilling',
        'grovsortering', 'forstehjelper', 'is_active', 'created_at',
    ]
    list_filter = ['year', 'grovsortering', 'is_active']
    search_fields = ['pasientnummer', 'problemstilling']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-year', 'pasientnummer']
    autocomplete_fields = ['forstehjelper']


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    """Admin for AppSetting (nøkkel-verdi-par)."""

    list_display = ['key', 'value']
    search_fields = ['key']
