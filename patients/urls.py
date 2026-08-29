"""URL-konfigurasjon for patients-appen."""
from django.urls import path, re_path
from django.shortcuts import redirect
from . import admin_status
from . import views_arkiv, views_patients, views_registre

urlpatterns = [
    # Hoved-siden
    path('', views_patients.index_view, name='index'),

    # Innstillinger — kun lesing. Skriving flyttet til
    # /portal-admin/innstillinger/ (§4.1).
    path('api/settings/', views_patients.settings_view, name='api_settings'),

    # Pasienter
    path('api/patients/', views_patients.patients_list_view, name='api_patients_list'),
    path('api/patients/<int:pk>/', views_patients.patient_detail_view, name='api_patient_detail'),

    # Forstehjelpere
    path('api/forstehjelpere/', views_registre.forstehjelpere_view, name='api_forstehjelpere'),
    path('api/forstehjelpere/<int:pk>/', views_registre.forstehjelper_detail_view, name='api_forstehjelper_detail'),
    path('api/helsepersonell/', views_registre.helsepersonell_view, name='api_helsepersonell'),
    path('api/helsepersonell/<int:pk>/', views_registre.helsepersonell_detail_view, name='api_helsepersonell_detail'),

    # «Nullstill år» ble «Avslutt vakt» i deploy 2 av vakt-scopingen:
    # operasjonen gjelder én vakt, og navnet sier det. Ingen redirect fra den
    # gamle stien — eneste konsument var admin-JS-en, som følger med.
    path('api/vakter/', views_patients.vakter_view, name='api_vakter'),
    path('api/avslutt-vakt/', views_patients.avslutt_vakt_view, name='api_avslutt_vakt'),
    path('api/gjenaapne-vakt/', views_patients.gjenaapne_vakt_view, name='api_gjenaapne_vakt'),

    # Statistikk. Ingenting ligger igjen her.
    #
    # `api/stats/` ble slettet 28. aug. 2026. Det var en rest fra
    # Flask-porten, der header-chipsene ble hentet fra serveren; i dag regnes
    # de ut i `patients-table.js` fra pasientlista. Ingen JS-fil i repoet har
    # noen gang kalt det. Ingen redirect settes opp: en videresending finnes
    # for klienter som *pleide* å kalle noe, og her fantes ingen.
    # `basic_stats()` i services står igjen: den er live-siden av invarianten
    # `StatsMatcher` måler, at arkivering ikke endrer tallene.

    # Videresending for klienter med gammel JS i cache. Uten den slutter
    # statistikken å oppdatere seg for alle som har siden åpen når deployen
    # treffer — og den feiler stille: loadStats() logger en advarsel og lar
    # forrige visning bli stående, så brukeren ser gamle tall uten beskjed.
    # 302, ikke 301: en 301 caches av nettleseren for godt, og stien bør
    # kunne tas i bruk igjen uten at gamle klienter sitter fast.
    path('api/full-stats/',
         lambda req: redirect('/statistikk/api/kilde/patients/full-stats/'),
         name='api_full_stats_flyttet'),

    # Arkiver (gammel fil-basert)

    # VaktArkiv (database-basert arkiv)
    path('api/innstillinger/arkiv/', views_arkiv.arkiv_liste_view, name='api_arkiv_liste'),
    path('api/innstillinger/arkiv/lagre/', views_arkiv.arkiv_lagre_view, name='api_arkiv_lagre'),
    path('api/innstillinger/arkiv/<int:pk>/', views_arkiv.arkiv_detalj_view, name='api_arkiv_detalj'),
    path('api/innstillinger/arkiv/<int:pk>/full-stats/',
         lambda req, pk: redirect(
             f'/statistikk/api/kilde/patients/arkiv/{pk}/full-stats/'),
         name='api_arkiv_full_stats_flyttet'),

    # Bakover-kompatibel redirect: /pasienter/admin/server-status/... → /portal-admin/server-status/...
    re_path(r'^admin/server-status/(?P<rest>.*)$',
            lambda req, rest='': redirect(f'/portal-admin/server-status/{rest}', permanent=True),
            name='legacy_server_status_redirect'),

    # Backup / Restore (kun admin)
    # Backup-endepunktene er fjernet (august 2026). Backup administreres samlet
    # på /portal-admin/backup/, med eget intervall og egen oppbevaring per modul.
]
