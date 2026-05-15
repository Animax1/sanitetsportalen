# Sanitetsportal – Fase 1: core-appen

**Dato:** 6. mai 2026
**Status:** Klar for review og merge
**Branch:** `feat/sanitetsportal-fase-1-core` (foreslått navn)

---

## Hva er gjort

Fase 1 er en **ren refaktor** uten DB-endring og uten UI-endring. Vi har opprettet en ny Django-app `core/` som inneholder felles primitiver, og flyttet de relevante symbolene inn dit fra `patients/services.py` og `accounts/decorators.py`. Begge stedene re-eksporterer fortsatt navnene for full bakoverkompatibilitet.

### Nye filer (i `core/`)

| Fil | Innhold |
|---|---|
| `core/__init__.py` | Modul-docstring som beskriver core-appens rolle |
| `core/apps.py` | `CoreConfig` (Django AppConfig) |
| `core/migrations/__init__.py` | Tom (ingen migrations i fase 1) |
| `core/models.py` | `BaseTimeStampedModel` (abstrakt — for fremtidige apps) |
| `core/validators.py` | `validate_time_string`, `validate_patient_time_fields`, `parse_minutes`, `now_local_str`, `TIME_FORMAT`, `TIME_FIELDS` m.m. |
| `core/auth_decorators.py` | `ROLE_HIERARKI`, `has_role_at_least`, `role_required`, `admin_required`, `write_required`, `stats_required`, `dataset_scope_all` |
| `core/tests.py` | 31 nye tester for alt det ovennevnte |

### Endrede filer

| Fil | Endring |
|---|---|
| `myproject/settings.py` | `'core'` lagt til i `INSTALLED_APPS` (før `accounts`) |
| `accounts/decorators.py` | Erstattet med shim som re-eksporterer fra `core.auth_decorators` |
| `patients/services.py` | Toppen refaktorert: importerer nå validatorer og rolle-helpers fra `core`. Lokale duplikater er fjernet. Re-eksporterer alt så ingen eksisterende import brekker. |

### Avhengighetsgrafen er ren

```
accounts ← core ← patients
```

`core` har ingen avhengigheter til andre prosjekt-apper. Det er fundamentet alle nye moduler kan bygge på (vakter, oppdragsregistrering, utstyr, rapport).

---

## Hva er IKKE gjort i fase 1 (bevisste valg)

- **Ingen DB-migrations.** `BaseTimeStampedModel` er abstrakt — bestående `created_at`/`updated_at`-felter på Patient/Behandler/etc. er urørt.
- **Ingen URL-endring.** Pasientregistrering ligger fortsatt på root (`/`). Flytting til `/pasienter/` kommer i fase 2.
- **Ingen audit-helper i core.** Vi venter til vi har en andre app som trenger audit, så vi kan abstrahere fra to konkrete bruksmønstre i stedet for ett.
- **Ingen permission-flag på CustomUser.** Disse legges til i fase 2 eller 3 når `vakter`-modulen kommer og faktisk bruker dem.

---

## Verifikasjon

### Lokalt (Windows / PowerShell)

```powershell
cd C:\Programmering\pasientregistrering
.\.venv\Scripts\Activate.ps1

# Kun core-tester
python manage.py test core -v 2

# Full suite
python manage.py test
```

### Forventede tall

- **Core-tester:** 31 / 31 OK
- **Full suite:** 317 / 321 OK
  - 4 pre-eksisterende failures er SSL-redirect-relaterte (`301 != 201/400`) og er ikke knyttet til denne refaktoren.

### Test-output-bekreftelse fra sandbox

```
Ran 31 tests in 0.011s
OK  (core)

Ran 321 tests in 113.678s
FAILED (failures=3, errors=1)  ← samme 4 SSL-redirect som før
```

---

## Deploy-strategi

1. **Branch:** `git checkout -b feat/sanitetsportal-fase-1-core`
2. **Commit:** Alle filer under `core/` + de tre endrede filene.
3. **Push og PR:** Railway oppretter PR-environment automatisk basert på din konfig.
4. **Verifikasjon i PR-env:**
   - `migrate` skal kjøre uten feil (ingen nye migrations).
   - Healthcheck: `/healthz/` skal returnere 200 OK.
   - Manuell røyktest: logg inn, opprett pasient, åpne statistikk, bekreft at alt fungerer som før.
5. **Merge til main** når PR-env er bekreftet OK.

Husk å verifisere at `ALLOWED_HOSTS` i PR-environment inkluderer Railway sin PR-domene-pattern (typisk `*.up.railway.app`).

---

## Hva blir fase 2

Når fase 1 er merged kommer fase 2: **Portal-skall**.

- Ny `base_portal.html` med portal-navigasjon
- Tomt portal-dashbord på `/` som viser modul-kort basert på rolle
- Pasientregistrering flyttes til `/pasienter/` med 301-redirect fra root
- `AuditLog` får `app_label`-felt
- Permission-flag på `CustomUser` (`kan_redigere_vakter` osv.) — forberedt for fase 3

---

## Filer å oppdatere lokalt (Windows-stier)

| Type | Fil | Sti |
|---|---|---|
| **NY** | `__init__.py` | `C:\Programmering\pasientregistrering\core\__init__.py` |
| **NY** | `apps.py` | `C:\Programmering\pasientregistrering\core\apps.py` |
| **NY** | `migrations/__init__.py` | `C:\Programmering\pasientregistrering\core\migrations\__init__.py` |
| **NY** | `models.py` | `C:\Programmering\pasientregistrering\core\models.py` |
| **NY** | `validators.py` | `C:\Programmering\pasientregistrering\core\validators.py` |
| **NY** | `auth_decorators.py` | `C:\Programmering\pasientregistrering\core\auth_decorators.py` |
| **NY** | `tests.py` | `C:\Programmering\pasientregistrering\core\tests.py` |
| OVERSKRIV | `settings.py` | `C:\Programmering\pasientregistrering\myproject\settings.py` |
| OVERSKRIV | `accounts/decorators.py` | `C:\Programmering\pasientregistrering\accounts\decorators.py` |
| OVERSKRIV | `patients/services.py` | `C:\Programmering\pasientregistrering\patients\services.py` |
