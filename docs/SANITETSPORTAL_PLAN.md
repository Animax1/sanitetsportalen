# Sanitetsportal – høynivå-skisse

**Versjon:** 0.1 (utkast for diskusjon)
**Dato:** 6. mai 2026
**Forfatter:** André Eritsland (utvikler/systemansvarlig)

> Dette er en høynivå-skisse, ikke en implementeringsplan. Målet er å forankre arkitektur, navnekonvensjoner, sikkerhet og migrasjonsvei før vi skriver kode. Detaljer pr. modul kommer i egne dokumenter.

---

## 1. Mål og omfang

Pasientregistrering utvides til en **sanitetsportal** med flere samvirkende moduler. Dagens app blir én av flere apper i samme prosjekt. Felles brukerkonto, MFA og audit-logg på tvers av portalen.

### Moduler i scope

| Modul | Kortbeskrivelse | Status |
|---|---|---|
| `patients` (eksisterende) | Pasientregistrering for sanitetsvakt (event/arrangement) | I prod |
| `accounts` (eksisterende) | Brukerkontoer, roller, MFA, login | I prod |
| `vakter` (ny) | Vakt-administrasjon: planlegging, oppmøte, deltagerlister, kontaktinfo | Planlagt |
| `utstyr` (ny) | Utstyr og logistikk: sjekklister, medikamentlager, forbruksvarer, kjøretøy | Planlagt |
| `rapport` (ny) | Rapportering og sammenstilling av statistikk på tvers av vakter og år | Planlagt |
| `beredskap` (ny) | Variant av pasientregistrering for lag/beredskapsambulanser. Annen flyt, men deler kjerneprimitiver med `patients` | Planlagt |

> **Beredskap vs. patients:** To selvstendige apper med felles delte komponenter (modeller for behandler/helsepersonell, validatorer for tidsfelt, audit-logg-helper). Vi unngår en "én tabell for alt"-løsning som gjør GDPR-vurderingene uoversiktlige.

---

## 2. Arkitektur-anbefaling: modulær monolitt

### Anbefaling

**Behold ett Django-prosjekt med flere apps, men håndhev tydelige modul-grenser.**

Begrunnelse:

- **Du jobber alene.** Microservices/separat-deploy gir kun overhead og fler-prosjekt-kompleksitet uten fordeler.
- **Du har allerede en stabil monolitt** (Django 5.2 + Postgres + Railway). Re-bruk all infrastruktur.
- **Felles brukermodell og audit-logg** er et must (du valgte "fullt felles"). Det fungerer bedre i én prosess.
- **Driftsmodus-paradigmet** (lavkostnad/vakt) virker fortsatt fordi alt er ett deploy-target.
- **Lav grad av frikobling** — kun det som virkelig trenger isolasjon (f.eks. `beredskap` sine pasientdata) skilles ut, ikke alt.

### Hva "modulær monolitt" betyr i praksis

1. **Hver modul er én Django-app** med eget URL-prefiks, egne models, egne templates, egne tester.
2. **Eksplisitte avhengigheter mellom apper.** En app importerer aldri direkte fra en annen apps `models.py` eller `views.py` for å gjøre forretningslogikk. I stedet eksponerer hver app et klart API (en `services.py` eller `api.py`) som andre apper kaller.
3. **Felles primitiver i `core/`-app** (ny). Modeller og helpers som flere apper trenger:
   - `BaseAuditLog` (utvides av app-spesifikke audit-modeller hvis nødvendig)
   - `BaseTimeStampedModel` (created_at, updated_at)
   - Validatorer for `dd.mm.åååå tt:mm`
   - Felles RBAC-decorator
4. **Ingen sirkulære avhengigheter.** Avhengighetsgrafen er ensrettet:
   ```
   accounts ← core ← patients
                    ← beredskap
                    ← vakter
                    ← utstyr
                    ← rapport (leser fra patients/beredskap/vakter)
   ```

### Foldermal

```
django_project/
├── myproject/                 # settings, root urls, wsgi
├── core/                      # ny — felles primitiver
│   ├── models.py              # BaseTimeStampedModel m.m.
│   ├── validators.py          # dd.mm.åååå tt:mm
│   ├── auth_decorators.py     # RBAC-helpers
│   └── tests.py
├── accounts/                  # eksisterende — kun mindre justering
├── patients/                  # eksisterende — uendret som modul
├── beredskap/                 # ny
├── vakter/                    # ny
├── utstyr/                    # ny
├── rapport/                   # ny
├── templates/
│   ├── base_portal.html       # ny portal-base med nav-menyen
│   └── ...
└── static/
```

### URL-struktur

| Prefiks | App |
|---|---|
| `/` | Portal-dashbord (visning av valgte moduler ut fra rolle) |
| `/pasienter/` | `patients` (eksisterende — evt. flyttes hit fra dagens root) |
| `/beredskap/` | `beredskap` |
| `/vakter/` | `vakter` |
| `/utstyr/` | `utstyr` |
| `/rapport/` | `rapport` |
| `/konto/` | `accounts` (login/profil/MFA) |
| `/admin/` | Django admin (kun superbruker) |
| `/admin-dashbord/` | Eksisterende drifts-dashbord (admin_status) |

> **Bakoverkompatibilitet:** Dagens URL-er for pasientregistrering må fortsatt fungere etter migrering. Vi løser det med Django-redirects fra gamle paths til `/pasienter/...` i en overgangsfase, eller beholder root-mounting hvis det er tryggest.

---

## 3. Felles brukermodell, MFA og audit

Du valgte "fullt felles". Konkret:

### Brukerkonto (`accounts.CustomUser`)
- Eksisterende modell beholdes.
- Roller utvides med portal-spesifikke tilganger via et **permission-flag system** i stedet for å lage 20 nye roller:
  - Eksisterende: `read_only`, `read_write`, `lead_view`, `lead`, `admin`
  - Nye boolske flag på `CustomUser`: `kan_redigere_vakter`, `kan_redigere_utstyr`, `kan_se_rapport`, `kan_redigere_beredskap`, `kan_redigere_pasienter`
- Admin krysser av flag pr. bruker. Roller styrer fortsatt overordnet tilgang i hver app, flag styrer modul-tilgang.

### MFA
- Eksisterende TOTP + backup-koder gjelder portal-vidt. Én gang innlogget, alle apper er tilgjengelige (subject to flag/role).

### Audit-logg
- Eksisterende `AuditLog` utvides med kolonne `app_label` (Django gir denne gratis via `ContentType`-rammeverket).
- Hver app som muterer data, bruker `core.audit.log_change(user, instance, before, after, request)` — én helper, alle apper.
- Beholder felt-nivå granularitet og 10-års retention (jf. PERSONVERN_DOKUMENTASJON).

### Login-events
- `accounts.LoginEvent` er allerede portal-vidt (én login per bruker, ikke per app). Ingen endring.

---

## 4. Database og GDPR

### Én database, separate tabeller pr. app
Postgres-skjemaet får tabeller med app-prefiks (Django gjør dette automatisk):
- `patients_patient`, `patients_behandler`, `patients_helsepersonell`, `patients_auditlog`
- `beredskap_oppdrag`, `beredskap_pasient`
- `vakter_arrangement`, `vakter_deltager`
- `utstyr_artikkel`, `utstyr_lager`
- `rapport_*` — sannsynligvis ingen egne tabeller; rapport leser fra de andre appene

### GDPR-konsekvenser
Behandlingsprotokollen i PERSONVERN_DOKUMENTASJON.md må utvides med:
- Egne avsnitt under A.6 for `beredskap`-pasientdata (samme prinsipp som A.6 i dag, men separat tabell)
- A.6 for `vakter` (deltager-info: navn, telefon, kompetansenivå — vanlige personopplysninger, ikke art. 9)
- A.6 for `utstyr` (ingen personopplysninger)
- A.6 for `rapport` (kun aggregater, ingen nye personopplysninger)

> **Viktig prinsipp:** `beredskap` skal ikke dele tabell med `patients` selv om feltene ligner. Ulike kontekster, ulike rettslige grunnlag og ulike retention-regler tilsier separate tabeller.

### Backup
- Eksisterende `BackupSchedulerMiddleware` har `BACKUP_APPS=['patients']`. Denne utvides til å også backupere `['beredskap', 'vakter']`.
- `utstyr` og `rapport` trenger ikke backup på samme måte (utstyr-data kan re-genereres fra inventarliste; rapport er avledet).

---

## 5. Sikkerhet og driftsmodus

### Driftsmodus-paradigmet beholdes
- Lavkostnad-modus (default): 1 worker, LocMemCache, ingen Redis. Egnet for skrivebordsbruk og admin-arbeid.
- Vakt-modus: flere workers, Redis aktiv, økt cache-effektivitet.

### Konsekvens for nye apper
- Nye apper må ikke anta delt cache. Hvis en modul trenger delt state mellom workers (f.eks. live-statusoppdatering), må den **degradere gracefully** når Redis mangler — samme prinsipp som `metrics`-aggregeringen (#15).
- Rate-limiting på sensitive endepunkter (login, lookup) gjøres med samme cache-baserte mekanisme som i dag, og fortsetter å fungere i begge moduser.

### Security headers
- Dagens `SecurityHeadersMiddleware` (CSP, HSTS, X-Frame-Options m.m.) gjelder portal-vidt. Ingen endring nødvendig.

---

## 6. Migrasjonsstrategi (fra dagens app til portal)

Foreslått 5-fase plan, hver fase kan deployes uavhengig:

| Fase | Innhold | Risiko |
|---|---|---|
| 1. **`core`-app opprettes** | Flytt `BaseTimeStampedModel`, validatorer, RBAC-decorator inn i `core/`. Refaktorer `patients` og `accounts` til å bruke `core`. Ingen UI-endring. | Lav — ren refaktor |
| 2. **Portal-skall** | Lag `base_portal.html` + portal-dashbord på `/`. Pasientregistrering flyttes til `/pasienter/` med redirect fra root. Audit utvides med `app_label`. | Middels — URL-endring krever testing |
| 3. **Første ny modul: `vakter`** | Enklest modul (planlegging, ikke pasientdata). Skal validere portal-mønsteret. | Lav — isolert |
| 4. **`utstyr` + `rapport`** | Ingen pasientdata i utstyr; rapport er read-only på tvers av apper. Bygger på `vakter`-erfaring. | Lav |
| 5. **`beredskap`** | Mest sensitiv ny modul. Krever GDPR-oppdatering, backup-utvidelse og egne tester. | Høy — skal ha grundig review |

> Hver fase ender med en deploy + verifikasjon i prod (lavkostnad-modus). Vakt-modus testes minst én gang per fase med en kort "tørrgåing" før reelle vakter.

---

## 7. Spørsmål jeg vil forankre med deg før neste steg

1. **Datamodell `vakter`:** Skal "vakt" referere til ett enkelt arrangement (event-basert), eller skal vakter også dekke faste beredskaps-perioder (f.eks. ukentlig lag-vakt)? Dette påvirker felter på `Arrangement`/`Vakt`-modellen.
2. **`beredskap` brukstype:** Skal beredskap-pasientregistrering brukes underveis (mobilt, dårlig nett) eller hovedsakelig i ettertid? Påvirker offline-strategi og synk.
3. **`rapport` målgruppe:** Skal rapport være kun intern (admin/lead) eller også gi tilgang til styre/oppdragsgivere? Påvirker rolle-flag og eksport-format.
4. **Migrasjon av URL-er:** Greit å flytte pasientregistrering fra root til `/pasienter/` med 301-redirect, eller skal pasienter beholde root for å minimere brukerforvirring?
5. **Tidsplan:** Vil du jobbe en fase i gangen til den er ferdig deployet, eller parallellisere `core` + `vakter`?

---

## 8. Hva jeg ikke har gjort i denne skissen

- Ikke detaljerte modeller for nye apper — det blir egne dokumenter pr. modul
- Ikke konkrete URL-paths utover prefiks
- Ikke endelig permission-matrise for portalen — utarbeides etter pkt. 7-svar
- Ikke estimat på tid eller scope — vi tar én fase om gangen

---

**Neste skritt:** Diskuter pkt. 7. Når vi er enige om svarene, lager jeg detaljert plan for fase 1 (`core`-app) som vi kan kjøre på.
