# Sanitetsportal — Fase 4: Per-modul backup med admin-UI

## Sammendrag

Fase 4 erstatter den globale singleton-backupen med en **per-modul-backup**
der hver modul har egen av/på-bryter, intervall, max-antall og
restore-flyt. Patients-modulen er første konsumenten; rammeverket er
modul-agnostisk slik at vakter, utstyr og rapport kan kobles på i en
senere fase ved å registrere en `BaseBackupHandler`-subklasse.

Designvalg som er bevart fra forrige løsning:

- **Hash-skip**: Auto-backup hopper over lagring hvis innholdet er
  identisk med forrige auto-backup (sparer disk).
- **Cap**: Eldste backuper slettes automatisk når antallet overstiger
  `max_backups` (default 50). Pre-restore-snapshots er beskyttet og
  telles ikke.
- **Pre-restore-snapshot**: Før hver destruktive restore tas en ekstra
  backup som sikkerhetsnett.

Nytt i Fase 4:

- **`core.backup`-pakke**: handler-registry + sentral service som er
  helt uavhengig av patients.
- **`ModuleBackupConfig`-modell**: én rad per modul med eget intervall,
  max-antall og enabled-flag (data-migrert fra `patients.BackupConfig`).
- **Admin-UI** under `/portal-admin/backup/` med oversikt, modul-side,
  manuell start, restore med slug-bekreftelse, nedlasting og sletting.
- **Audit-log på restore**: hver gjenoppretting logges i `AuditLog`.

## Hva er nytt

### Admin-UI

| URL | Funksjon | Tilgang |
| --- | --- | --- |
| `/portal-admin/backup/` | Oversikt over alle moduler med backup-handler | admin |
| `/portal-admin/backup/<slug>/` | Per-modul: rediger config + se backup-liste | admin |
| `/portal-admin/backup/<slug>/run/` (POST) | Start manuell backup nå | admin |
| `/portal-admin/backup/<slug>/restore/<pk>/` (GET+POST) | Restore med slug-bekreftelse | admin |
| `/portal-admin/backup/<slug>/last-ned/<pk>/` | Last ned `.json.gz`-fila | admin |
| `/portal-admin/backup/<slug>/slett/<pk>/` (POST) | Slett enkelt-backup (fil + DB-rad) | admin |

«Backup»-lenke er lagt til både i admin-nav og i bruker-dropdownen
øverst til høyre.

### Per-modul-konfigurasjon

Admin kan styre per modul:

- **Backup aktivert** — av/på for automatisk backup
- **Intervall** — 5 / 15 / 30 / 60 / 360 / 1440 minutter (eller Av)
- **Maks antall backuper** — 1–1000 (default 50)

Manuell backup kan startes når som helst, uavhengig av om automatisk
backup er på.

### Restore-flyt

1. Admin velger en backup i listen og trykker **Gjenopprett**.
2. Bekreftelses-side viser hvilken backup, når den ble laget og en
   advarsel om at all data i modulen overskrives.
3. Admin må skrive modul-slug eksakt (f.eks. `patients`) i et tekstfelt
   for å aktivere knappen.
4. Når bekreftelsen er gyldig:
   - **Steg 1**: Pre-restore-snapshot lages av nåværende tilstand.
   - **Steg 2**: Modulens modeller slettes i FK-trygg rekkefølge.
   - **Steg 3**: `loaddata` laster den valgte backup-fila.
   - Steg 2 og 3 kjører i én atomisk transaksjon — feiler noe
     ruller alt tilbake. Pre-restore-snapshot fra steg 1 forblir på
     disk uansett.
5. En `AuditLog`-rad opprettes med
   `table_name='<slug>_backup_restore'`, `action='UPDATE'`,
   `app_label='core'` og brukernavn.

## Filendringer

### Nye filer

- `core/backup/__init__.py` — pakke-API (re-eksport av handler/service).
- `core/backup/handlers.py` — `BaseBackupHandler` + intern registry
  (`register`, `get_handler`, `all_handlers`, `clear_registry`).
- `core/backup/service.py` — `create_backup`, `restore_backup`,
  `enforce_cap`, `get_backup_dir` + konstanter
  (`KIND_AUTO/MANUAL/PRE_RESTORE/PRE_RESET`, `PROTECTED_KINDS`,
  `VALID_KINDS`).
- `core/migrations/0002_modulebackupconfig.py` — `ModuleBackupConfig`
  + RunPython-data-migrering fra `patients.BackupConfig` (kopierer
  `interval_minutes` til en ny rad med `module_slug='patients'`).
- `patients/migrations/0007_backup_module_slug.py` — `Backup.module_slug`
  + index `backup_module_created_idx`.
- `patients/backup.py` — `PatientsBackupHandler` + `register_handlers()`.
- `core/templates/core/backup_admin_overview.html`
- `core/templates/core/backup_admin_module.html`
- `core/templates/core/backup_admin_restore.html`
- `core/tests_backup.py` — 47 nye tester for Fase 4.

### Oppdaterte filer

- `core/models.py` — la til `ModuleBackupConfig` med `INTERVAL_CHOICES`,
  `module_slug` (unique), `enabled`, `interval_minutes`, `max_backups`,
  `last_run_at` og `get_or_default()`.
- `core/forms.py` — `ModuleBackupConfigForm` (validerer `max_backups`
  1–1000) og `BackupRestoreConfirmForm` (krever eksakt slug-match).
- `core/urls.py` — 6 nye routes under `portal-admin/backup/`.
- `core/views.py` — 6 nye admin-views.
- `core/templates/core/base_portal.html` — Backup-lenke i admin-nav
  + bruker-dropdown.
- `patients/models.py` — `Backup.module_slug` (default `'patients'`,
  db_index) + `backup_module_created_idx`-index.
- `patients/apps.py` — kaller `register_handlers()` fra `ready()`.
- `patients/backup_service.py` — tynn proxy mot `core.backup` for
  bakoverkompatibilitet (samme funksjonsnavn, samme adferd).
- `patients/backup_scheduler.py` — itererer alle aktive
  `ModuleBackupConfig` istedenfor singleton; én tråd håndterer alle
  moduler.

## Tekniske valg

### Modulær handler-registry

`BaseBackupHandler` har fire klassefelt som hver subklasse setter:

```python
slug = 'patients'
display_name = 'Pasientregistrering'
apps = ['patients']
exclude = ['patients.Backup', 'patients.BackupConfig', 'patients.VaktArkiv']
restore_models = [
    'patients.Patient',
    'patients.Behandler',
    'patients.Helsepersonell',
    'patients.AppSetting',
]
```

Sentral `create_backup(slug=...)` kjører `dumpdata` mot `apps`-listen
med `exclude`-listen, mens `restore_backup(...)` sletter `restore_models`
i rekkefølge før `loaddata`. Slik trenger ny modul kun å arve
`BaseBackupHandler` og kalle `register(MyHandler())` i `app.ready()`.

Registry holdes i et internt `_Registry`-objekt slik at testkode kan
kalle `clear_registry()` uten å påvirke modul-globale variabler.

### Hash-skip kun for auto

Auto-backup beregner SHA-256 av den ukomprimerte JSON-en. Hvis hashen
matcher siste auto-backup for samme modul, hoppes lagring over og
funksjonen returnerer `None`. Manual, pre_restore og pre_reset lagres
alltid — hash-skipping ville gjort dem upålitelige som
sikkerhetsnett-eksempler ("før jeg gjorde X").

### Cap beskytter pre_restore

`enforce_cap(slug, max_backups)` filtrerer bort `PROTECTED_KINDS`
(`{KIND_PRE_RESTORE}`) før den teller. Pre-restore-snapshots blir
liggende uavhengig av cap-størrelse — admin må slette dem manuelt om
ønsket. Det forhindrer at en uventet auto-backup-flom (f.eks.
massive endringer i pasientdata) sletter en livsviktig
pre-restore-snapshot.

### Mikrosekund-presisjon på filnavn

`_build_filename` bruker `%Y%m%d-%H%M%S-%f` (mikrosekunder) for å
unngå unique-filename-kollisjon når to backuper lages innen samme
sekund (f.eks. pre-restore + manual rett etter hverandre, eller flere
moduler i parallell-scheduler).

### Bakoverkompatibel proxy

`patients.backup_service` er ikke fjernet — den proxy-er nå mot
`core.backup` (`create_backup(slug='patients')`,
`restore_backup(...)`, `purge_old_backups()`). Dette holder eldre
kall-steder (management-kommando, eksisterende admin-views) i live
mens den nye admin-flaten ruller ut. `patients.tests_backup` kjører
fortsatt grønt mot proxy-en.

### Scheduler — én tråd, alle moduler

`patients.backup_scheduler.maybe_run_backup()` (kalt fra middleware
ved hver request) starter én bakgrunnstråd som itererer alle
`ModuleBackupConfig`-rader hvor:

- `enabled=True`
- en backup-handler er registrert
- intervallet er passert siden `last_run_at`

For hver modul tas en `select_for_update(nowait=True)`-lås før
`last_run_at` oppdateres — dermed unngår vi at to Gunicorn-arbeidere
lager backup samtidig for samme modul. Throttling sikrer at selve
sjekken ikke kjøres oftere enn én gang per 60 sekund per prosess.

### Slug-bekreftelse istedenfor passord

For å bekrefte en restore må admin skrive modul-slug eksakt — samme
mønster som GitHub bruker for sletting av repo. Det er friction nok
til å hindre tilfeldige klikk, men ikke så tungt at det fristes til
å gå rundt. `BackupRestoreConfirmForm.clean_confirm_slug` trim'er
whitespace og avviser alt annet enn eksakt match.

## Migrasjoner

Fase 4 har **to nye migrasjoner**:

| Migrasjon | Beskrivelse |
| --- | --- |
| `core/migrations/0002_modulebackupconfig.py` | Oppretter `ModuleBackupConfig` + RunPython som kopierer `BackupConfig.interval_minutes` til `module_slug='patients'`. |
| `patients/migrations/0007_backup_module_slug.py` | Legger til `Backup.module_slug` (default `'patients'`) + composite index `backup_module_created_idx`. |

Begge er idempotente — `python manage.py migrate` på en eksisterende
database vil kopiere den gjeldende intervall-innstillingen til en ny
rad uten å miste konfigurasjon. `BackupConfig`-modellen beholdes for
bakoverkompatibilitet (proxy bruker den ikke lenger).

## Tester

47 nye tester i `core/tests_backup.py`, alle grønne:

| Klasse | Antall | Dekker |
| --- | --- | --- |
| `HandlerRegistryTests` | 4 | register, get_handler, all_handlers, idempotens, ukjent slug |
| `CreateBackupTests` | 6 | hash-skip auto, manual ignorerer hash, ukjent slug/kind raiser, pre_restore-kind |
| `EnforceCapTests` | 4 | cap fjerner eldste, beskytter pre_restore, no-op under cap, kun egen modul |
| `RestoreBackupTests` | 5 | pre_restore-snapshot lages, roundtrip, erstatter endret data, ukjent handler raiser, manglende fil raiser |
| `ModuleBackupConfigFormTests` | 3 | gyldig form, max_backups < 1, max_backups > 1000 |
| `BackupRestoreConfirmFormTests` | 3 | korrekt slug, feil slug, whitespace-trim |
| `ModuleBackupConfigTests` | 2 | get_or_default lager defaults, idempotens |
| `BackupAdminViewTests` | 11 | admin-required på alle endepunkter, run, restore-flyt, audit-log, download, delete |
| `SchedulerTests` | 5 | enabled=False stopper, intervall=0 stopper, første gang true, intervall respekteres, ukjent handler hoppes over |
| `BackupConstantsTests` | 3 | VALID_KINDS, PROTECTED_KINDS, get_backup_dir |

Full testsuite: 460 tester (413 fra Fase 3b + 47 nye).
Kun de 4 pre-eksisterende Fase 1-failures består
(`PatientNumberGapTests`, `PabegyntNotBeforeInntidTests`,
`BlankInntidFallbackTests` — alle pga. manglende
`@override_settings(SECURE_SSL_REDIRECT=False)` i 301-redirects).

## Deploy-flyt på Windows

Fra `C:\Programmering\sanitetsportalen\`:

```powershell
# 1. Hent zip-en og pakk ut OPPÅ eksisterende repo
git checkout -b feat/sanitetsportal-fase-4
Expand-Archive -Path "$HOME\Downloads\sanitetsportalen_fase4.zip" `
    -DestinationPath . -Force

# 2. Kjør migrasjoner (NB: Fase 4 har migrasjoner!)
python manage.py migrate

# 3. Kjør tester — sjekk at de 47 nye er grønne
python manage.py test core.tests_backup
python manage.py test

# 4. Commit + push
git add -A
git commit -m "feat(fase-4): per-modul backup med admin-UI"
git push -u origin feat/sanitetsportal-fase-4
```

## Etter deploy

1. Logg inn som admin → sjekk at **Backup** dukker opp i nav-baren.
2. Åpne `/portal-admin/backup/` og verifiser at patients-modulen vises
   med riktig intervall (skal være kopiert fra gammel `BackupConfig`).
3. Klikk på patients → trykk **Start backup nå** og verifiser at en
   manuell backup vises i listen.
4. Last ned filen for å bekrefte at den åpnes som gyldig gzip+JSON.
5. Sett intervall til **Hvert 5. minutt** og vent — verifiser at
   `last_run_at` oppdateres når en request treffer portalen.
6. Last opp den valgte backupen i en restore-test (helst i et
   separat miljø) — skriv `patients` i bekreftelsesfeltet og verifiser
   at en pre_restore-backup dukker opp like før restoren.
7. Sjekk `/portal-admin/auditlog/` og verifiser at restore-handlingen
   logges med `table_name=patients_backup_restore`.

## Migreringsplan for andre moduler (fremtid)

For å koble vakter, utstyr eller rapport på backup-løsningen senere:

1. Lag `<modul>/backup.py` med en `BaseBackupHandler`-subklasse:
   ```python
   class VakterBackupHandler(BaseBackupHandler):
       slug = 'vakter'
       display_name = 'Vakter'
       apps = ['vakter']
       exclude = []  # ekskluder selvref-tabeller om nødvendig
       restore_models = ['vakter.Vakt', 'vakter.Vaktdeltaker']
   ```
2. Kall `register(VakterBackupHandler())` i `<modul>/apps.py`'s
   `ready()`.
3. Ferdig — admin-UI viser modulen automatisk på neste request,
   `ModuleBackupConfig.get_or_default('vakter')` lager en standard-rad
   med 60 min intervall + 50 max-backups.

Ingen endringer i scheduler eller admin-views er nødvendig.
