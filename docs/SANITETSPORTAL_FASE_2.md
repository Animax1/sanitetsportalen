# Sanitetsportal — Fase 2: Portal-skall (Vei 1)

## Oppsummering

Fase 2 introduserer **portal-skallet**: Et dashboard på `/` som blir den nye landingsidet for hele Sanitetsportalen. Pasientregistrering-appen er flyttet fra `/` til `/pasienter/` med 301-redirects fra gamle URL-er, slik at bokmerker, integrasjoner og søkemotor-resultater fortsetter å fungere.

Dette er **Vei 1** — den robuste, langsiktige løsningen — der alle hardkodede URL-er er oppdatert i kode, tester, JavaScript og templates. Ingen midlertidige hacks.

## Mål for fasen

- Etablere et felles portal-layout (`base_portal.html`) som alle framtidige moduler kan extende
- Lage et dashboard på `/` med modulkort (Fase 2: kun pasientregistrering aktiv)
- Flytte pasient-appen fra rot-URL til `/pasienter/` uten å bryte eksisterende funksjonalitet
- Opprettholde tilbakekompatibilitet via 301-redirects fra gamle URL-er
- Bevare all eksisterende funksjonalitet og testdekning

## Arkitekturbeslutninger

### Vei 1: Full URL-flytting valgt
Vi kunne valgt en hybrid der pasient-appen forble på `/` og dashboardet lå på `/portal/`. Vi gikk i stedet for **Vei 1** fordi:

- **Renere mental modell**: Portalen er produktet, pasientregistrering er én av flere moduler.
- **Skalerbart**: Når vakter, utstyr og rapporter kommer som nye moduler, vil de naturlig leve under `/vakter/`, `/utstyr/`, etc. — sammen med `/pasienter/`.
- **Engangskostnad**: 94 hardkodede URL-er måtte oppdateres, men dette gjøres én gang. Hvis vi valgte hybrid ville vi måttet flytte uansett senere.
- **301-redirects beskytter eksisterende brukere**: Bokmerker, integrasjoner og delte lenker fortsetter å virke.

### URL-rekkefølge i `myproject/urls.py`
```python
urlpatterns = [
    path("healthz/", ...),               # uendret
    path("admin/", admin.site.urls),     # Django admin (uendret)
    path("accounts/", ...),              # auth (uendret)
    path("pasienter/", include("patients.urls")),  # NY mounting
    path("", include("core.urls")),      # MÅ stå sist (har catch-all redirects)
]
```
Rekkefølgen er kritisk: `core` har `re_path`-baserte legacy-redirects som ellers ville fanget `/pasienter/api/...`-URL-er.

### 301 (permanent) vs 302 (temporary) redirects
Vi bruker `HttpResponsePermanentRedirect` (ekte 301) fordi:
- Nettlesere cacher 301-redirects og vil oppdatere bokmerker automatisk
- Søkemotorer overfører ranking til den nye URL-en
- Klienter (apper, scripts) som bruker gamle endepunkter får tydelig signal om permanent flytting

### Permissions og AuditLog `app_label` — utsatt til Fase 3
Disse ble vurdert for Fase 2, men vi venter:
- **Permissions**: Designes best fra konkrete behov i en faktisk ny modul (Fase 3)
- **AuditLog `app_label`**: Migrasjon kan introdusere risiko — utsetter til vi har en andre app som faktisk skriver til loggen

## Endringer i detalj

### Nye filer

| Fil | Funksjon |
|-----|----------|
| `core/templates/core/base_portal.html` | Felles portal-layout: header med modulnavigasjon, footer, CSS-variabler |
| `core/templates/core/dashboard.html` | Dashboard-side med modulkort (Fase 2: kun pasientregistrering) |
| `core/views.py` | `portal_dashboard_view` (login_required, GET) + `legacy_root_redirect` (301) |
| `core/urls.py` | Dashboard på `''`, `re_path`-baserte legacy-redirects for `/api/.*` og `/admin/server-status/.*` |

### Endrede filer

| Fil | Endringstype |
|-----|--------------|
| `myproject/urls.py` | URL-mapping: `pasienter/` lagt til, `core` på `''` |
| `patients/middleware.py` | `_SKIP_EXACT` oppdatert til `/pasienter/admin/server-status/` |
| `templates/patients/index.html` | Lagt til "Tilbake til portal"-lenke i bruker-dropdown |
| `templates/patients/admin_status.html` | 4 fetch-URLs oppdatert til `/pasienter/admin/server-status/...` |
| `static/js/script.js` | 31 fetch-kall: `/api/...` → `/pasienter/api/...` |
| `patients/tests.py` | 29 URL-er oppdatert til `/pasienter/`-prefiks |
| `patients/tests_admin_status.py` | 39 URL-er oppdatert |
| `patients/tests_arkiv.py` | 10 URL-er oppdatert |
| `patients/tests_backup.py` | 11 URL-er oppdatert |
| `patients/tests_patient_delete.py` | 2 URL-er oppdatert |
| `myproject/tests_cache_config.py` | 1 URL oppdatert |
| `core/tests.py` | +24 nye tester: `PortalDashboardViewTests`, `LegacyRedirectTests`, `PasientAppPaaNyURLTests` |

## Testdekning

### Nye tester i `core/tests.py`
- **PortalDashboardViewTests**: Verifiserer at dashboard krever innlogging, returnerer 200 for innlogget bruker, viser pasient-modulkortet, og inneholder lenke til `/pasienter/`.
- **LegacyRedirectTests**: Verifiserer at gamle URL-er (`/api/patients/`, `/admin/server-status/`, etc.) returnerer 301 til de nye `/pasienter/`-prefiksede URL-ene.
- **PasientAppPaaNyURLTests**: Verifiserer at pasient-appen er korrekt mounted på `/pasienter/` og at gamle root-URL-er ikke lenger serveres direkte.

### Test-resultater
- **Core-tester**: 56/56 OK (24 nye Fase 2 + 32 fra Fase 1)
- **Full suite**: 342/346 OK
- **4 pre-existing failures** (eksisterte allerede i Fase 1, ikke introdusert her): Tre tester i `patients/tests.py` mangler `@override_settings(SECURE_SSL_REDIRECT=False)`, slik at SSL-middleware redirecter HTTP til HTTPS (301) istedenfor å gi forventet 400-respons. Disse fikses i en egen, isolert oppgave.

## Bevarte sider og endepunkter

Disse er IKKE endret i Fase 2:
- `/healthz/` — uendret
- `/admin/` — Django admin uendret
- `/accounts/login/`, `/accounts/logout/`, etc. — uendret
- `templates/base.html` — fortsatt brukt av accounts og admin_status
- `templates/patients/index.html` — fortsatt en standalone single-page-app (1021 linjer). Den extender IKKE `base_portal.html`. Eneste endring er en "Tilbake til portal"-lenke i header-dropdown.

## Brukerflyt etter Fase 2

1. Bruker logger inn på `/accounts/login/`
2. Etter innlogging redirectes til `/` (portal-dashboard)
3. Dashboard viser modulkort for pasientregistrering
4. Klikk på kort → `/pasienter/` (pasient-app starter som før)
5. Inne i pasient-appen: "Tilbake til portal"-lenke i header-dropdown går til `/`

## Tilbakekompatibilitet

Alle gamle URL-er fungerer fortsatt via 301-redirects:
- `/api/patients/` → `/pasienter/api/patients/`
- `/admin/server-status/` → `/pasienter/admin/server-status/`
- Alle JS-/integrasjonsfetch-kall fortsetter å virke (men bør oppdateres for å unngå redirect-runde)

## Deploy-prosedyre (Windows)

```powershell
cd C:\Programmering\sanitetsportalen
git checkout main
git pull origin main
git checkout -b feat/sanitetsportal-fase-2-portal-skall
# Plasser alle 17 filer (5 NY, 12 OVERSKRIV)
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py test core -v 2          # forventer 56 OK
python manage.py test                    # forventer 342 OK + 4 pre-existing failures
git add .
git commit -m "Fase 2: Portal-skall med dashboard på / og pasienter på /pasienter/"
git push -u origin feat/sanitetsportal-fase-2-portal-skall
# Åpne PR på GitHub, verifiser Railway PR-environment, merge til main
```

## Veien videre — Fase 3 (foreslått)

- Ny modul som faktisk skriver til AuditLog → da designer vi `app_label`-felt for å skille mellom moduler
- Permission-flagg på modulkortene (skjul kort bruker ikke har tilgang til)
- Enklere modulregistrering (auto-discovery basert på en `Module`-klasse i hver app)
- Felles søk på tvers av moduler (når vi har minst to)
