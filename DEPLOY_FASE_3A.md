# Sanitetsportalen Fase 3a — Deploy-guide (clean clone)

Denne guiden er for situasjonen der du startar med ein FRISK clone av repoet
(`git clone https://github.com/Animax1/sanitetsportalen.git`) og pakkar denne
zipen oppå.

## Steg-for-steg (Windows + PowerShell)

### 1) Slett gammal lokal mappe og clone på nytt

```powershell
# Naviger eitt nivå opp frå sanitetsportalen
cd C:\Programmering
# Sikker sletting (krev bekreftelse)
Remove-Item -Recurse -Force sanitetsportalen
# Frisk clone frå main
git clone https://github.com/Animax1/sanitetsportalen.git
cd sanitetsportalen
```

### 2) Lag ny feature-branch

```powershell
git checkout -b feat/sanitetsportal-fase-3a
```

### 3) Pakk ut zipen oppå repoet

Pakk ut `sanitetsportalen-fase-3a.zip`. Inni er det éi mappe `sanitetsportalen/`.
Kopier ALT innhaldet i den mappa inn i `C:\Programmering\sanitetsportalen\`
slik at filer som `manage.py`, `accounts\`, `audit\` osv. ligg i rota.

PowerShell-kommando hvis du har pakka ut til `C:\Temp\sanitetsportalen-fase-3a\sanitetsportalen\`:

```powershell
Copy-Item -Recurse -Force C:\Temp\sanitetsportalen-fase-3a\sanitetsportalen\* C:\Programmering\sanitetsportalen\
```

### 4) Sett opp virtuelt miljø og avhengigheiter

```powershell
cd C:\Programmering\sanitetsportalen
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5) Verifiser migrasjons-grafen

```powershell
python manage.py showmigrations accounts audit core
```

Forventa output (umigrert lokalt — alle med `[ ]`):

```
accounts
 [ ] 0001_initial
 [ ] 0002_add_lead_role
 [ ] 0003_email_optional
 [ ] 0004_add_lead_view_role
 [ ] 0005_add_mfa_required
 [ ] 0006_alter_customuser_groups_and_more
 [ ] 0007_module_permission_flags
audit
 [ ] 0001_initial
 [ ] 0002_rename_audit_auditlog_table_rec_idx_audit_audit_table_n_dc0494_idx_and_more
 [ ] 0003_auditlog_app_label
core
 [ ] 0001_modulesettings
```

### 6) Kjør migrasjonar

```powershell
python manage.py migrate
```

### 7) Køyr testar

```powershell
python manage.py test core.tests
python manage.py test
```

Forventa: 86/86 i core, 372/376 i full suite (4 pre-eksisterande Fase 1-failures
i patients som er urelaterte til Fase 3a).

### 8) Commit og push

```powershell
git add -A
git status   # verifiser at det berre er Fase 3a-filer som er endra
git commit -m "feat(fase-3a): modul-registry, permissions, AuditLog app_label"
git push -u origin feat/sanitetsportal-fase-3a
```

### 9) Deploy til Railway test-miljø

Railway vil køyra `python manage.py migrate` automatisk under release-fasa
(`Procfile`). Følg deployment-loggane i Railway-dashboard og verifiser at
dei tre nye migrasjonane går igjennom.

## Kva som er nytt i denne fasen

| Område | Nye filer |
|--------|-----------|
| Modul-registry | `core/modules.py`, `core/module.py` |
| Modul-instansar | `accounts/module.py`, `patients/module.py` |
| ModuleSettings | `core/models.py` (utvida), `core/migrations/0001_modulesettings.py` |
| Permission-flagg | `accounts/models.py` (utvida), `accounts/migrations/0007_module_permission_flags.py` |
| AuditLog app_label | `audit/models.py` (utvida), `audit/migrations/0003_auditlog_app_label.py`, `audit/signals.py` |
| Admin-konfig | `core/admin.py`, `audit/admin.py` (utvida) |
| Template-context | `core/context_processors.py` |
| UI | `templates/core/dashboard.html`, `templates/core/base_portal.html` |

## Når noko går gale

- **`Conflicting migrations detected`**: Du har ikkje teke clean clone først.
  Slett mappa og start på nytt frå steg 1.
- **`No module named 'core.modules'`**: Zipen er ikkje pakka ut riktig.
  Verifiser at `C:\Programmering\sanitetsportalen\core\modules.py` finst.
- **`OperationalError: no such column: app_label`**: Migrasjonane er ikkje
  køyrde. Køyr `python manage.py migrate` på nytt.
