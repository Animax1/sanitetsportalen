"""Django-admin for vaktlistemodulen.

Fase 1 leverer registrene og mannskapet med admin her; portalens egen side
kommer i fase 2. Django-admin er uansett riktig hjem for `Korps`,
`Kompetanse` og `VaktRolle` — de er organisasjonsoppsett som endres sjelden,
av global admin.
"""
from django.contrib import admin

from .models import Kompetanse, Korps, Mannskap, VaktRolle


@admin.register(Korps)
class KorpsAdmin(admin.ModelAdmin):
    list_display = ('navn', 'kortnavn', 'er_aktiv', 'rekkefolge', 'antall_mannskap')
    list_filter = ('er_aktiv',)
    search_fields = ('navn', 'kortnavn')
    ordering = ('rekkefolge', 'navn')

    @admin.display(description='Mannskap')
    def antall_mannskap(self, obj):
        return obj.mannskap.count()


@admin.register(Kompetanse)
class KompetanseAdmin(admin.ModelAdmin):
    list_display = ('navn', 'er_aktiv', 'rekkefolge')
    list_filter = ('er_aktiv',)
    search_fields = ('navn',)
    ordering = ('rekkefolge', 'navn')


@admin.register(VaktRolle)
class VaktRolleAdmin(admin.ModelAdmin):
    list_display = ('navn', 'er_aktiv', 'rekkefolge')
    list_filter = ('er_aktiv',)
    search_fields = ('navn',)
    ordering = ('rekkefolge', 'navn')


@admin.register(Mannskap)
class MannskapAdmin(admin.ModelAdmin):
    list_display = ('navn', 'korps', 'telefon', 'er_aktiv', 'har_konto')
    list_filter = ('korps', 'er_aktiv', 'kompetanser')
    search_fields = ('navn', 'telefon')
    list_select_related = ('korps',)
    filter_horizontal = ('kompetanser',)
    autocomplete_fields = ('user',)
    ordering = ('korps__rekkefolge', 'korps__navn', 'navn')

    @admin.display(boolean=True, description='Konto')
    def har_konto(self, obj):
        return obj.user_id is not None
