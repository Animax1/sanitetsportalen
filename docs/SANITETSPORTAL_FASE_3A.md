# Sanitetsportalen — Fase 3a

**Status:** Implementert. Alle nye tester (26) passerer. Fullt testresultat: 372/376 OK (samme 4 pre-eksisterende failures fra Fase 1).

**Branch (anbefalt):** `feat/sanitetsportal-fase-3a`
**Django:** 5.1.15
**Migrasjoner som legges til:** `core.0001_modulesettings`, `accounts.0006_module_permission_flags`, `audit.0002_auditlog_app_label`, `accounts.0007_alter_customuser_groups_and_more`, `audit.0003_rename_…`

---

## 1. Mål og scope

Fase 3a er ren infrastruktur — "huset før rommene":

| Område | Hva som leveres |
|--------|-----------------|
| **Modul-registry** | `core/modules.py` med `Module`-dataklasse og eksplisitt registrering. Hver app deklarerer sin modul i `<app>/module.py`. |
| **ModuleSettings** | DB-rad per modul (slug, enabled, backup_enabled, note, updated_at, updated_by). Admin kan toggle moduler i sanntid uten deploy. |
| **Permission-flagg** | 5 BooleanField på `CustomUser`: `kan_redigere_pasienter`, `kan_redigere_vakter`, `kan_redigere_utstyr`, `kan_se_rapport`, `kan_redigere_beredskap`. |
| **AuditLog.app_label** | Nytt felt som auto-fylles fra `table_name` via `pre_save`-signal. Filtreres i Django-admin. |

Brukervendte features (vakt, utstyr, rapport, beredskap) kommer i senere faser. Permission-flaggene er pre-registrert nå slik at vi slipper én migrasjon per modul senere.

## 2. Designvalg (med begrunnelse)

| # | Valg | Begrunnelse |
|---|------|-------------|
| 1B | Eksplisitt modul-registry i `core/modules.py` | Bedre oversikt og enklere å disable enn auto-discovery. Vi har 5–7 moduler totalt — auto-discovery er overkill. |
| 2A | DB-styrt enabled-toggle (`ModuleSettings`) | Sanntids-toggle uten deploy. Trengs uansett for backup-per-modul-UI senere. |
| 3A | `backup_enabled`-felt nå, kobling senere | Billig å legge til feltet nå, dyrt å lage ny migrasjon senere. Frem til Fase 3b/4 bruker `BackupSchedulerMiddleware` fortsatt `BACKUP_APPS`-konstanten. |
| 4B | Alle 5 permission-flagg i én migrasjon | Én migrasjon vs. fem fragmenterte når moduler aktiveres. Default `False` pluss data-migrering som setter alle `True` for `role='admin'`. |
| 5B | 3a alene først | Brukeren ønsket å validere infrastruktur før vi bygger system-panel og profil-UI (3b). |

## 3. Arkitektur

### 3.1 Datamodell

```
core_modulesettings
├── id (PK)
├── slug (unique)        ← matcher Module.slug
├── enabled (bool)
├── backup_enabled (bool, reservert)
├── note (varchar 255)
├── updated_at (auto_now)
└── updated_by_id (FK → CustomUser, nullable)

accounts_customuser  (utvidet)
├── … eksisterende felter
├── kan_redigere_pasienter (bool, default False)
├── kan_redigere_vakter (bool, default False)
├── kan_redigere_utstyr (bool, default False)
├── kan_se_rapport (bool, default False)
└── kan_redigere_beredskap (bool, default False)

audit_auditlog  (utvidet)
├── … eksisterende felter
└── app_label (varchar 64, indeksert, default '')
    + index (app_label, created_at)
```

### 3.2 Synlighetslogikk (`core.modules.is_visible_for`)

```
1. Uautentisert eller ikke-bruker  → False
2. role == 'admin'                  → True   (admin ser alt)
3. admin_only=True                  → False  (ikke-admin)
4. permission_flag is None          → True   (åpen modul)
5. ellers                           → bool(getattr(user, permission_flag, False))
```

`get_visible_modules` legger på et ekstra filter:
```
6. is_core=True                     → alltid synlig (defensiv)
7. ModuleSettings.enabled=False     → False
```

### 3.3 AuditLog app_label-fylling

`audit/signals.py:fyll_app_label` (pre_save-handler):
```
1. Hvis instance.app_label er satt → behold (caller har overstyrt).
2. Slå opp i EKSPLISITT_MAPPING ({'backup': 'patients'}).
3. Hvis '_' i table_name → første del.
4. Ellers → hele table_name.
```

**Hvorfor signal i stedet for å overstyre `save()`?**
- Holder modellen ren (datadefinisjon, ingen logikk).
- Fanger også `AuditLog.objects.create(...)` som er pattern brukt 5 steder i koden.
- Ingen endring av eksisterende callsites kreves.

**Hvorfor ikke en helper-funksjon i alle callsites?**
- 5 steder i dag, men flere kommer (vakt, utstyr, beredskap). Unngår vedlikeholdsbyrde.
- Risiko for at noen glemmer å bruke helperen.

## 4. Filer endret/lagt til

### Nye filer
| Fil | Linjer | Formål |
|-----|--------|--------|
| `django_project/core/modules.py` | 188 | `Module` dataklasse + registry-funksjoner |
| `django_project/core/module.py` | 23 | `CoreModule` (is_core, ikke synlig) |
| `django_project/core/admin.py` | 91 | `ModuleSettingsAdmin` med readonly-guard for kjerne |
| `django_project/core/context_processors.py` | 24 | `portal_modules` for nav-meny |
| `django_project/core/migrations/0001_modulesettings.py` | – | Initial migrasjon for core |
| `django_project/accounts/module.py` | 24 | `AccountsModule` (is_core) |
| `django_project/accounts/migrations/0006_module_permission_flags.py` | 100 | 5 permission-flagg + admin-data-migrering |
| `django_project/accounts/migrations/0007_alter_customuser_groups_and_more.py` | – | Auto-generert (Django 5 internas) |
| `django_project/audit/signals.py` | 53 | Pre-save-handler `fyll_app_label` |
| `django_project/audit/migrations/0002_auditlog_app_label.py` | 85 | Felt + backfill av eksisterende rader |
| `django_project/audit/migrations/0003_rename_…idx.py` | – | Auto-generert (Django 5 internas) |
| `django_project/patients/module.py` | 26 | `PatientsModule` (slug='patients', perm=`kan_redigere_pasienter`) |
| `SANITETSPORTAL_FASE_3A.md` | denne fila | Dokumentasjon |

### Endrede filer
| Fil | Endring |
|-----|---------|
| `django_project/core/models.py` | Lagt til `ModuleSettings` med `get_enabled_slugs` og `ensure_defaults_exist` |
| `django_project/core/apps.py` | `ready()` kobler `post_migrate` til `ensure_defaults_exist` |
| `django_project/core/views.py` | `portal_dashboard_view` sender `modules=get_dashboard_modules(user)` |
| `django_project/core/templates/core/dashboard.html` | Loop over `modules` i stedet for hardkodet kort |
| `django_project/core/templates/core/base_portal.html` | Nav-loop over `nav_modules` (fra context-processor) |
| `django_project/core/tests.py` | +26 tester for Fase 3a |
| `django_project/accounts/models.py` | 5 BooleanFields lagt til `CustomUser` |
| `django_project/audit/models.py` | `app_label`-felt + composite index |
| `django_project/audit/admin.py` | `app_label` i list_display, list_filter, search_fields, date_hierarchy |
| `django_project/audit/apps.py` | `ready()` importerer `audit.signals` |
| `django_project/myproject/settings.py` | `core.context_processors.portal_modules` lagt i `TEMPLATES.context_processors` |

## 5. Test-dekning

26 nye tester fordelt på 7 testklasser:

| Testklasse | Antall | Dekker |
|------------|--------|--------|
| `ModuleRegistryTests` | 5 | Unike slugs, modul-oppslag, sortering, kjerne-flagg |
| `ModuleVisibilityTests` | 6 | Anonym, admin, permission-flagg, deaktivert modul, kjerne-bypass |
| `ModuleSettingsModelTests` | 4 | `ensure_defaults_exist` idempotent, `get_enabled_slugs`, `__str__` |
| `DashboardRendringTests` | 3 | Admin ser pasient-kort, ingen permission gir empty-state, deaktivert skjules |
| `NavMenuTests` | 2 | Admin ser nav-lenke, manglende permission skjuler den |
| `AuditLogAppLabelTests` | 5 | Auto-fyll for patients/backup, eksplisitt overstyrer auto, helper-funksjon, index finnes |
| `CustomUserPermissionFlagsTests` | 1 | Alle 5 flagg eksisterer med default False |

Fullt resultat:
```
Ran 376 tests in 120s
FAILED (failures=3, errors=1)
```
De 4 feilende er **pre-eksisterende fra Fase 1** (`PatientNumberGapTests`, `PabegyntNotBeforeInntidTests`, `BlankInntidFallbackTests` — manglende `@override_settings(SECURE_SSL_REDIRECT=False)`). Ingen regresjoner fra Fase 3a.

## 6. Migrasjonsrekkefølge

```
core.0001_modulesettings                    ← oppretter tabellen
accounts.0006_module_permission_flags       ← 5 flagg + aktivere for admins
accounts.0007_alter_customuser_groups…      ← Django 5-intern (groups m2m)
audit.0002_auditlog_app_label               ← felt + backfill
audit.0003_rename_…_idx                     ← Django 5-intern (index-navn)
```

**Rekkefølgen er trygg:** Ingen FK-avhengigheter mellom dem. `post_migrate` på core kjører `ensure_defaults_exist` etter at *alle* migrasjoner er ferdige.

## 7. Hvordan legge til en ny modul (eksempel: vakt)

1. Lag `<app>/module.py`:
   ```python
   from core.modules import Module
   VaktModule = Module(
       slug='vakt',
       name='Vakt-administrasjon',
       description='Planlegging og oversikt over sanitetsvakter.',
       url='/vakt/',
       icon='calendar-event',
       permission_flag='kan_redigere_vakter',
       order=110,
   )
   ```
2. Importer i `core/modules.py:_build_registry()` og legg til i return-tuple.
3. Kjør `python manage.py migrate` — `ensure_defaults_exist` oppretter ModuleSettings-rad.
4. (Permission-flagget `kan_redigere_vakter` finnes allerede fra Fase 3a.)

## 8. Sikkerhet og GDPR

- **Defensiv kjernemodul-bypass:** `get_visible_modules` ignorerer `enabled=False` for `is_core=True`. Selv om noen redigerer ModuleSettings direkte i SQL, kan ikke admin låses ute fra kjernefunksjoner.
- **Ingen permission-eskalering:** Synlighet av modul-kort er IKKE en autorisasjonssjekk. App-views beholder sine egne `@login_required` + role-decorators. Permission-flaggene styrer kun hva som *vises* — backend-views må fortsatt sjekke selv (gjøres allerede via `core.auth_decorators`).
- **Audit-logging:** `app_label` gir bedre filtrering ved GDPR-spørringer ("hvilke endringer ble gjort på pasient-data forrige uke?"). Eksisterende audit-rader får `app_label` backfilled.

## 9. Kjente begrensninger / framtidig arbeid

- **Backup-flagget er ikke koblet på.** `patients/middleware.py:BackupSchedulerMiddleware` leser fortsatt `BACKUP_APPS`-konstanten. Kobling i Fase 3b/4.
- **Ingen system-panel-UI.** Admin må gå til `/django-admin/core/modulesettings/` for å toggle moduler. Eget panel kommer i Fase 3b.
- **Profil-side med flagg.** Fase 3b utvider `accounts/templates/accounts/user_form.html` med checkbox-grupper for de 5 flaggene.
- **Ny modul = kode-deploy.** Eksplisitt registrering i `_build_registry()` betyr at en helt ny modul kreves Python-endring + deploy. Akseptert kompromiss for tydelighet.
