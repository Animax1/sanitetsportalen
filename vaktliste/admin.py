"""Django-admin for vaktlistemodulen — **utviklerverktøy, ikke portalens flate.**

Fase 1 la registrene her og skrev at Django-admin var «riktig hjem» for dem.
Det var feil: `/django-admin/` er kun rutet når `DEBUG` eller `OFFLINE_MODE`
er på (S1 — den omgår rate-limiting, kontosperre, MFA-tvang og `LoginEvent`).
I produksjon fantes det dermed ingen vei til å opprette et korps eller et
mannskap i det hele tatt.

Portalens flate er mannskapsfanen på `/vaktliste/`, med endepunktene i
`views_registre.py`. Denne
fila blir stående fordi den er nyttig lokalt — men et register som *bare*
finnes her, finnes ikke for brukeren.
"""
from django.contrib import admin

from .models import (Kompetanse, Korps, Mannskap, Ressursgruppe,
                     Ressursrolle)


@admin.register(Korps)
class KorpsAdmin(admin.ModelAdmin):
    list_display = ('navn', 'kortnavn', 'er_aktiv', 'antall_mannskap')
    list_filter = ('er_aktiv',)
    search_fields = ('navn', 'kortnavn')
    ordering = ('navn',)

    @admin.display(description='Mannskap')
    def antall_mannskap(self, obj):
        return obj.mannskap.count()


@admin.register(Kompetanse)
class KompetanseAdmin(admin.ModelAdmin):
    list_display = ('navn', 'er_aktiv')
    list_filter = ('er_aktiv',)
    search_fields = ('navn',)
    ordering = ('navn',)


@admin.register(Ressursgruppe)
class RessursgruppeAdmin(admin.ModelAdmin):
    list_display = ('navn', 'ikon', 'rekkefolge', 'er_aktiv')
    list_filter = ('er_aktiv',)
    search_fields = ('navn',)
    ordering = ('rekkefolge', 'navn')


@admin.register(Ressursrolle)
class RessursrolleAdmin(admin.ModelAdmin):
    list_display = ('navn', 'gruppe', 'er_aktiv')
    list_filter = ('gruppe', 'er_aktiv')
    search_fields = ('navn',)
    list_select_related = ('gruppe',)
    ordering = ('gruppe__rekkefolge', 'navn')


@admin.register(Mannskap)
class MannskapAdmin(admin.ModelAdmin):
    list_display = ('navn', 'korps', 'telefon', 'er_aktiv', 'har_konto')
    list_filter = ('korps', 'er_aktiv', 'kompetanser')
    search_fields = ('navn', 'telefon')
    list_select_related = ('korps',)
    filter_horizontal = ('kompetanser',)
    autocomplete_fields = ('user',)
    ordering = ('korps__navn', 'navn')

    @admin.display(boolean=True, description='Konto')
    def har_konto(self, obj):
        return obj.user_id is not None
