# Sanitetsportal — Fase 3b: Admin-UI og Min profil

## Sammendrag

Fase 3b lukker gapet mellom modellene fra Fase 3a (`ModuleSettings`,
permission-flagg på `CustomUser`, `AuditLog.app_label`) og daglig drift
ved å gi admin et visuelt grensesnitt og hver bruker en egen profilside.

Ingen migrasjoner — kun nye views, templates, forms og tester.

## Hva er nytt

### Admin-UI

| URL | Funksjon | Tilgang |
| --- | --- | --- |
| `/portal-admin/moduler/` | Liste med togglestatus per modul | admin |
| `/portal-admin/moduler/<slug>/` | Rediger `enabled`, `backup_enabled`, `note` | admin |
| `/portal-admin/auditlog/` | Filtrert revisjonslogg med pagination | admin |
| `/portal-admin/auditlog/eksport.csv` | CSV-eksport av filtrert logg (maks 5000 rader) | admin |

Administratorlenker er lagt til både i den blå nav-baren under
**Server-status** og i bruker-dropdownen øverst til høyre.

### Min profil

| URL | Funksjon | Tilgang |
| --- | --- | --- |
| `/min-profil/` | Viser konto, modul-tilganger, aktivitet | innlogget bruker |

Sider som vises:

- **Konto**: brukernavn, e-post, rolle, MFA-status, sist logget inn,
  konto opprettet
- **Modul-tilganger**: alle 5 permission-flagg som ja/nei. For
  administrator vises et info-banner som forklarer at flaggene ikke
  brukes (admin har bypass).
- **Mine moduler**: pill-formede lenker til alle moduler brukeren har
  tilgang til.
- **Statistikk**: antall innlogginger siste 7 dager + antall
  tilgjengelige moduler.
- **Siste 10 hendelser**: `LoginEvent`-rader (login OK/feilet,
  MFA-hendelser).
- **Handlinger**: Endre passord.

### Bulk-aksjoner i brukerlisten

To nye knapper øverst på `/accounts/users/`:

- **Gi ledere pasienttilgang**: setter `kan_redigere_pasienter=True`
  for alle brukere med rolle `lead` eller `lead_view`.
- **Fjern pasienttilgang**: nullstiller `kan_redigere_pasienter=False`
  for alle ikke-admin-brukere. Begge knappene har JS-bekreftelse.

### Bruker-detalj utvidet

`/accounts/users/<id>/` viser nå alle 5 modul-permission-checkboxer i
redigeringsskjemaet, med info-tekst om at admin uansett har bypass.

## Filendringer

### Nye filer

- `core/forms.py` — `ModuleSettingsForm` (validerer at kjernemoduler
  ikke kan deaktiveres).
- `core/templates/core/module_admin_list.html`
- `core/templates/core/module_admin_edit.html`
- `core/templates/core/audit_log_list.html`
- `core/templates/core/profile.html`

### Oppdaterte filer

- `core/views.py` — la til 5 nye views: `profile_view`,
  `module_admin_list_view`, `module_admin_edit_view`,
  `audit_log_list_view`, `audit_log_csv_export_view`.
- `core/urls.py` — la til 5 nye URL-routes.
- `core/templates/core/base_portal.html` — Min profil i dropdown,
  Moduler + Revisjonslogg som admin-lenker i nav.
- `accounts/forms.py` — `AdminUserEditForm` utvidet med 5
  permission-felt + ny robust `clean_email`.
- `accounts/views.py` — `user_list_view` håndterer POST med
  `action='grant_pasienter_to_leads'` og
  `action='revoke_pasienter_from_all'`.
- `templates/accounts/user_list.html` — to nye bulk-aksjon-knapper.
- `templates/accounts/user_detail.html` — viser de 5
  permission-feltene i redigeringsskjemaet.
- `core/tests.py` — 28 nye tester (modul-admin, audit-filter, min profil, nav).
- `accounts/tests.py` — 9 nye tester (bulk-aksjoner, permission-redigering).

## Tekniske valg

- **Filterhjelper**: `_filter_audit_queryset(request)` returnerer
  `(queryset, filters_dict)` slik at både listevisning og CSV-eksport
  bruker eksakt samme filter-logikk.
- **CSV-eksport**: hardkodet `MAX_ROWS = 5000` for å hindre at admin
  ved et uhell laster ned millioner av rader. Filteret må snevres inn
  hvis treffmengden overstiger grensen — admin får da en
  feilmelding og redirect tilbake til listen med GET-parametrene
  bevart.
- **Excel-kompatibel CSV**: UTF-8 BOM (`\ufeff`) + semikolon som
  delimiter. Excel åpner filen med riktig tegnsett uten manuell import.
- **Pagination**: 50 rader per side. Filter-verdier bevares når
  brukeren navigerer mellom sider.
- **Kjernemodul-vern**: `ModuleSettingsForm.clean_enabled` slår opp
  `core.modules.get_module(slug)` og avviser deaktivering når
  `module.is_core` er `True`. Lazy-importert for å unngå sirkulær
  import.
- **Idempotente bulk-aksjoner**: `qs.update(...)` returnerer antallet
  påvirkede rader, som vises i success-message. Aksjoner kan kjøres
  flere ganger uten utilsiktede effekter.
- **Defensiv user-id-parsing**: `_filter_audit_queryset` håndterer
  ugyldig `user`-param ved å ignorere filteret i stedet for å krasje.

## Tester

37 nye tester, alle grønne:

| Klasse | Antall | Dekker |
| --- | --- | --- |
| `ModuleAdminUITests` | 6 | Tilgang, listing, redigering, kjernemodul-vern, 404 |
| `AuditLogListViewTests` | 12 | Filter (app/action/user/q), pagination, CSV-eksport, BOM |
| `ProfileViewTests` | 7 | URL, krav, innhold, context, admin-banner |
| `NavMenuFase3bTests` | 3 | Min profil i dropdown, admin-lenker synlig/skjult |
| `BulkPermissionActionsTests` | 5 | Grant/revoke, idempotens, admin-bypass |
| `AdminUserEditFormPermissionTests` | 3 | Form-felter, lagring, template-rendering |

Full testsuite: 413 tester, kun de 4 pre-eksisterende
Fase 1-failures (PatientNumberGapTests, PabegyntNotBeforeInntidTests,
BlankInntidFallbackTests — alle pga. manglende
`@override_settings(SECURE_SSL_REDIRECT=False)` i 301-redirects).

## Deploy-flyt på Windows

Fra `C:\Programmering\sanitetsportalen\`:

```powershell
# 1. Hent zip-en og pakk ut OPPÅ eksisterende repo
git checkout -b feat/sanitetsportal-fase-3b
Expand-Archive -Path "$HOME\Downloads\sanitetsportalen_fase3b.zip" `
    -DestinationPath . -Force

# 2. Verifiser at det ikke er nye migrasjoner
python manage.py showmigrations | Select-String "\[ \]"

# 3. Kjør tester
python manage.py test

# 4. Commit + push
git add -A
git commit -m "feat(fase-3b): admin-UI for moduler, audit, brukere + Min profil"
git push -u origin feat/sanitetsportal-fase-3b
```

Ingen `migrate` nødvendig på server — Fase 3b inneholder kun views,
templates og forms.

## Etter deploy

1. Logg inn som admin → sjekk at **Moduler** og **Revisjonslogg**
   dukker opp i nav-baren.
2. Åpne `/portal-admin/moduler/` og verifiser at alle moduler vises.
3. Åpne `/portal-admin/auditlog/` og prøv et filter +
   CSV-eksport.
4. Klikk på avatar → **Min profil** og verifiser permissions-listen.
5. På `/accounts/users/<id>/` skal de 5 permission-checkboxene være
   synlige.
