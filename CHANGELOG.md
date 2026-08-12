# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

---

## 2026-08-12 — Kodegjennomgang: ny forbedringsbacklog

Full gjennomgang av kodebasen for å finne hva som bør forbedres. **Ingen kode er endret** —
dette er kun kartlegging og dokumentasjon.

Nytt dokument `docs/FORBEDRINGER_2026-08.md` er den aktive backloggen. Den inneholder 13
nye funn (N1–N13), 6 funn fra et eget sikkerhetspass (S1–S6) og de 9 punktene fra
mai-runden som fortsatt sto åpne (F1–F9).
`docs/FORBEDRINGER.md` er konvertert til et historisk arkiv over det som ble gjennomført,
med en peker til den nye fila.

To punkter i mai-dokumentet var merket som åpne, men viste seg å være ferdig implementert
— hash-skip for identiske auto-backups (`core/backup/service.py`) og `/healthz/`
(`patients/health.py`). Begge er nå dokumentert som gjennomført.

### De mest konkrete nye funnene

- **N1** `next`-parameteren i innloggingen valideres ikke — åpen redirect til vilkårlig
  host rett etter vellykket innlogging
- **N2** `helsepersonell_ref` mangler i `felt_to_track` i audit-signalet. Endring av
  oppfølgingsansvarlig etterlater ingen spor, i strid med det personvernprotokollen lover
- **N3** `LOGGING` har ingen rot-handler. All INFO-logging — inkludert hver eneste
  vellykkede backup — forsvinner i stillhet, selv om RUNBOOK ber deg lete etter den
- **N4** MFA-skjemaene sender ingen `username`, så `key='post:username'` samler alle
  MFA-forsøk fra alle brukere i én bøtte: 10 per 5 minutter globalt. Ved vaktstart kan
  det låse ute folk som ikke har gjort noe galt
- **N5** `get_active_year()` og `Patient.save()` bruker fortsatt `datetime.now().year`.
  Samme feilklasse som ble ryddet i #20 — en nyttårsvakt etter midnatt lagrer pasienter i
  feil år
- **N9** De tre testene som skal beskytte dobbeltklikk-fixen leser `static/js/script.js`,
  som ingen mal laster lenger. De ville vært grønne selv om guarden forsvant fra den
  levende koden

### Sikkerhetspasset

- **S1** `/django-admin/` er en parallell innloggingsflate som omgår samtlige sikringer
  appen bygger rundt `accounts.views.login_view`: rate-limiting, kontosperre, MFA-tvang,
  tvungent passordbytte og `LoginEvent`-logging. Bak den ligger `Patient`, `CustomUser`
  og `AuditLog`. `OTPMiddleware` hjelper ikke — den setter `request.user.otp_device`, den
  håndhever ingenting
- **S2** `create_superuser` setter `must_change_password=False`, så bootstrap-adminen kan
  gå i årevis på deploy-passordet. Henger sammen med S1 og bør tas samtidig
- **S3** Rate-limiting finnes kun på innlogging — ingen struping på skriveendepunktene
- **S4** Lagret open redirect i varsel-visningen (`core/views.py:612`). Ikke utnyttbar i
  dag, men `notify()` er designet som generisk API for framtidige moduler
- **S5** Utlogging skjer via GET — en tredjepartsside kan tvinge utlogging
- **S6** MFA trust-cookie settes med `secure=True` i offline-modus, så nettleseren kaster
  den og «stol på denne enheten» virker ikke i felt

Dokumentet noterer også hva som ble kontrollert og funnet i orden, så det ikke revideres
på nytt: endepunktdekning, path traversal via backup-filnavn, audit-logging fra Django
admin, offline-modusens bevisste unntak og invalidering av MFA trust-cookien.

---

## 2026-08-12 — Backup samlet på én flate

Pasientmodulen hadde sitt eget backup-panel under Innstillinger, med egne
`/pasienter/api/backup/`-endepunkter. Det var to UI-er over samme backend: samme
`Backup`-tabell, samme filer på disk, samme `core.backup.restore_backup`.

**Det var ikke bare duplisering.** Panelets intervall-innstilling skrev til
`patients.BackupConfig` — den gamle singleton-modellen — mens scheduleren utelukkende
leser `core.ModuleBackupConfig`. Endret du intervallet der, skjedde ingenting. «Siste
automatiske backup» ble heller aldri oppdatert. Listen viste dessuten backuper fra alle
moduler blandet, uten å si hvilken modul de tilhørte.

- Fjernet de seks `/pasienter/api/backup/`-endepunktene med tilhørende URL-er
- Fjernet backup-panelet og ~130 linjer JS fra pasientmodulen
- Innstillinger lenker nå til `/portal-admin/backup/` i stedet
- `BackupAPITests` fjernet; portal-admin-flaten har allerede bedre dekning. Lagt til
  `test_run_view_requires_admin` for full paritet

536 tester, alle grønne.

Gjenstår som egne oppgaver (se TODO): den døde modellen `patients.BackupConfig` med
kommandoen `db_backup`, og `static/js/script.js` som ingen mal laster.

---

## 2026-08-12 — GDPR fase 3.1: arkiv kollapser til aggregat etter 24 måneder

Siste fase i GDPR-gjennomgangen. Arkiverte pasientrader slettes permanent etter 24
måneder og erstattes av den ferdig beregnede statistikken. Formålet — evaluering og
planlegging — er da uttømt, og art. 5(1)(e) tillater ikke at helseopplysninger på
radnivå blir liggende på ubestemt tid.

**Alt som vises i arkivvisningen bevares:** sammendrag, triagefordeling, ankomstkurve,
tidsstatistikk per gruppe, krysstabeller, kji-kvadrat og Kruskal-Wallis. Det som
forsvinner er enhver opplysning om enkeltpasienter. Etter kollaps kan ingenting i
arkivet føres tilbake til en person.

- Nye felt på `VaktArkiv`: `kollapset_at`, `aggregat` (JSON), `aggregat_sha256`
- `compute_arkiv_stats` / `compute_arkiv_full_stats` leser frosset aggregat når radene
  er borte — samme returstruktur, så grensesnittet er uendret
- Ny kommando `kollaps_arkiv` med `--dry-run`. Migrasjon `patients.0013`

### Integritetssjekk

`sha256` er beregnet over pasientradene og kan ikke verifiseres etter kollaps. Ved
kollaps beregnes en ny sjekksum over aggregatet, som overtar tuklingsdeteksjonen. Den
opprinnelige beholdes som historisk fingeravtrykk, men er ikke lenger etterprøvbar.
Arkiv-API-et eksponerer `kollapset` slik at grensesnittet kan skille tilstandene — et
arkiv som melder «ingen tukling» uten at noe faktisk sjekkes ville vært verre enn
ingen sjekk.

### Sikkerhetssperrer for en irreversibel operasjon

- Kommandoen nekter å kollapse med mindre det finnes en `arkiv`-backup tatt etter at
  arkivet ble opprettet. Fase 3.2 gjorde denne sperren mulig
- `--dry-run` viser nøyaktig hva som ville blitt slettet
- Hver kollaps loggføres i `AuditLog`
- Egen cron-jobb, ikke del av `purge_old_logs`: irreversibel sletting av helsedata skal
  ikke fyre som bieffekt av en loggopprydding

20 nye tester. 545 tester totalt, alle grønne.

Oppsettsinstruks for cron-jobben: `docs/OPPSETT_KOLLAPS_CRON.md` (midlertidig, slettes
når jobben er satt opp).

---

## 2026-08-12 — GDPR fase 3.2: arkivet som egen backup-modul

Tidligere var `VaktArkiv` ekskludert fra pasient-backupen mens `ArkivertPasient` ble tatt
med — barna uten forelderen. Det ga to problemer: en restore av pasientdata **feilet** på
fremmednøkkel dersom arkivet var slettet i mellomtiden, og arkivet kunne uansett ikke
gjenopprettes fra den backupen siden forelderen manglet. Null gjenopprettingsevne, bare
nedside.

- Ny `ArkivBackupHandler` (slug `arkiv`) med `VaktArkiv` + `ArkivertPasient` samlet
- Begge arkivmodellene ekskludert fra `PatientsBackupHandler`
- Egen `ModuleBackupConfig` via migrasjon `core.0005`: døgnintervall, cap 20.
  Arkivet endres bare når en vakt arkiveres, og innholds-hashen hindrer duplikater
- Vises som egen modul i `/portal-admin/backup/` med egen konfigurasjonsside

Motivasjonen er at Railways databasebackup kun er aktiv den måneden abonnementet er
oppgradert. Resten av året er dette den eneste dekningen arkivet har.

### Fallgruve avdekket underveis

Serialiseringen kjører med `natural_foreign=True`, så `VaktArkiv.importert_av` ble lagret
som brukernavnet. Var kontoen slettet, feilet **hele** gjenopprettingen med
`DeserializationError` — altså nøyaktig i scenarioet fase 4.1 nettopp gjorde mulig.

Løst med ny deklarativ `strip_fields` på `BaseBackupHandler`: angitte felter fjernes fra
dumpen før lagring. Arkiv-handleren utelater `importert_av`, siden brukernavnet uansett
ligger frosset i `importert_av_navn`. Mekanismen er generell og tilgjengelig for
framtidige moduler med FK-er som peker ut av eget datasett.

16 nye tester, blant annet at en pasient-restore nå går gjennom selv om et arkiv er
slettet, og at arkiv-restore virker etter at brukeren er borte. 525 tester, alle grønne.

---

## 2026-08-12 — GDPR fase 4.1: brukere kan slettes etter arkivering

`VaktArkiv.importert_av` hadde `on_delete=PROTECT`. En bruker som hadde arkivert en vakt
kunne dermed ikke slettes — databasen avviste med `ProtectedError`, og sletterett etter
GDPR art. 17 var blokkert på databasenivå. Med få admin-brukere merkes det ikke, men det
ville truffet ved første sletteforespørsel når frivillige får egen konto.

- Nytt felt `VaktArkiv.importert_av_navn`: frosset brukernavn som overlever brukersletting.
  Samme mønster som `ArkivertPasient.forstehjelper_navn` allerede brukte
- `importert_av` endret til `on_delete=SET_NULL, null=True`
- Migrasjon `0012` med datamigrasjon som fyller navnet på eksisterende arkiver
- Ny `VaktArkiv.importert_av_visning` brukes av `arkiv_liste_view` og `arkiv_detalj_view`.
  Begge leste tidligere `importert_av.username` direkte og ville fått `AttributeError`
  på `None` etter en sletting
- 8 nye tester: sletting fungerer, arkiv og pasientrader består, begge API-visningene
  overlever, og SHA-256-integritetssjekken påvirkes ikke

509 tester, alle grønne.

---

## 2026-08-12 — Testsuiten: 500 s → 15 s

Suiten brukte 8 minutter på 501 tester, noe som gjorde det upraktisk å kjøre den
under utvikling.

**Årsak:** Django-standarden PBKDF2 med 1 000 000 iterasjoner koster ~630 ms per hashing,
og suiten oppretter brukere og logger inn hundrevis av ganger. Alene stod dette for
mesteparten av kjøretiden — `accounts` brukte 141 s på 36 tester.

**Fiks:** `PASSWORD_HASHERS` settes til MD5 når — og bare når — `manage.py test` kjører
(`sys.argv[1] == 'test'`). Verifisert at gunicorn og `runserver` fortsatt bruker PBKDF2.

| | Før | Etter |
|---|---|---|
| `accounts` | 141 s | 0,9 s |
| Hele suiten | 504 s | 15,5 s |

Alle 501 tester fortsatt grønne.

**Dokumentasjonsfeil oppdaget underveis:** README og personvernprotokollen oppga
passord-hashing som «argon2 / pbkdf2». `argon2-cffi` er ikke i `requirements.txt`, så det
er PBKDF2 alene. Rettet begge steder. Argon2 kan aktiveres senere ved å legge til pakken.

---

## 2026-08-12 — GDPR fase 2: kodefikser

### Serverside-validering av kliniske felt (2.1)

- Ny `patients/choices.py` med kanonisk verdimengde for `problemstilling`, `arsak`,
  `transport`, `grovsortering`, `plassering`, `utskrevet_til`, `lege`, `medisiner` og `journal`
- `patient_create` og `patient_detail_view` avviser nå verdier utenfor mengden med HTTP 400.
  Tidligere ble verdiene skrevet rett inn fra request-body, slik at en klient som gikk utenom
  grensesnittet kunne lagre fritekst — i verste fall navn — i felt som skal være
  ikke-identifiserende
- Ny `patients/tests_choices.py` (15 tester), inkludert drift-vakt som leser `index.html` og
  feiler hvis skjemaet og hvitelisten kommer i utakt
- Testdata oppdatert: 48 plassholderverdier (`'A'`, `'Test'`, `'Båre 1'`, `'Hjem'`) byttet til
  reelle verdier. `journal='Oppfølging'` var en rest fra da feltet var en kategori

### Øvrige fikser

- **2.2:** `SECRET_KEY` hard-feiler ved oppstart med `DEBUG=False` hvis nøkkelen mangler eller er
  en kjent eksempelverdi. Tidligere falt den stilltiende tilbake på en hardkodet utviklingsnøkkel
- **2.3:** `purge_old_logs` sletter nå også varsler eldre enn 30 dager, med egen
  `--notification-days`. 5 nye tester
- **2.4:** Fjernet dødt `GET /api/archives/` med tilhørende UI-seksjon og JS. Endepunktet listet
  JSON-filer i `arkiv/`, men ingenting skrev slike filer; mappa lå dessuten på containerens
  flyktige disk på Railway. Rest fra Flask-tiden

### Windows-fiks (nødvendig for å kunne kjøre testene lokalt)

- `core/middleware.py` importerte `resource` ubetinget — en Unix-modul. Siden middlewaren står i
  `MIDDLEWARE`, feilet **hver eneste HTTP-test** på Windows. Importen er nå betinget, og
  minnelogging degraderer til ren responstid-logging der modulen mangler. Linux-oppførselen
  er uendret

Hele suiten: 501 tester, alle grønne.

---

## 2026-08-12 — GDPR-gjennomgang: protokoll v1.5

### Rettslig grunnlag omskrevet

- Avklart at systemet **ikke** er et behandlingsrettet helseregister. Journalføring skjer i eksternt
  system; feltet `journal` er kun et Ja/Nei-flagg som registrerer om journal er ført der
- Helsepersonelloven §§ 39–40 og pasientjournalloven fjernet som rettslig grunnlag
- Art. 6(1)(d) + art. 9(2)(h) står igjen, med taushetspliktvilkåret i art. 9(3) dokumentert

### Lagringstider korrigert som følge av bortfalt journalplikt

- Audit-logg: 10 år → **2 år**. Dokumentet samsvarer nå med det `purge_old_logs` faktisk håndhever
- Arkiverte pasientrader: **24 måneder**, deretter kollaps til aggregert statistikk *(planlagt)*
- Varsler: **30 dager** *(planlagt)*
- Backup: «72 timer» var feil — oppryddingen er antallsbasert (`max_backups`, standard 50).
  `RETENTION_HOURS` er død kode

### Nye kategorier og behandlinger dokumentert

- `VaktArkiv`, `ArkivertPasient` og `core.Notification` lagt inn i A.6
- Railway databasebackup lagt inn som egen behandling i A.2, med presisering av at den omfatter
  hele databasen — i motsetning til modul-backupen

### Vurderinger dokumentert (art. 5(2))

- Fravalg av innsynslogg, med begrunnelse
- Fravalg av begrenset lesetilgang («Mine pasienter» som tilgangsgrense)
- DPIA vurdert som ikke påkrevd
- Korrigert påstanden om at fritekst-risiko er «eliminert» — verdimengden håndheves foreløpig
  kun i grensesnittet, ikke i API-et

### Øvrig

- Ny **Del B.8**: informasjon til appbrukere (frivillige og helsepersonell), som manglet helt
- Merknad i A.1 om at behandlingsansvaret ligger hos privatperson
- Kjent begrensning dokumentert: `VaktArkiv.importert_av` (`PROTECT`) blokkerer sletting av brukere
- Dokumentasjonen konsolidert: `PERSONVERN_DOKUMENTASJON.md`, `TEKNISK_DOKUMENTASJON.md` og
  `RUNBOOK_VAKT.md` bor nå kun i `docs/`. Kopiene i rot var nyest og er flyttet dit; de utdaterte
  `docs/`-versjonene er overskrevet
- Ny `docs/GDPR_TILTAKSPLAN.md` med gjenstående faser

---

## 2026-06-23 — Python 3.13 + arbeidsflyt-regel

### Oppgradering til Python 3.13

- `runtime.txt` satt tilbake til `python-3.13` (var utilsiktet flippet til `3.12` i fase-3a-commit `75258f8`)
- Matcher miljøet pasientregistrering kjører på Railway — én færre variabel ved kommende repo-bytte på Railway
- Ingen avhengigheter er pinnet til 3.12; `requirements.txt` uendret

### Ny arbeidsflyt-regel

- `CLAUDE.md`: alle endringer som skal commites/pushes skal oppdatere CHANGELOG og TODO i forkant (samme commit)

---

## 2026-05-25 — Behandler → Førstehjelper + Mine pasienter

### Rename: Behandler → Førstehjelper (Fase 6)

- `Behandler`-modellen omdøpt til `Forstehjelper` i kode, database og UI
- Django-migrasjon med `RenameModel` + `RenameField` — ingen tap av data
- API-endepunkt `/api/behandlere/` → `/api/forstehjelpere/`
- `UserPatientLinkForm` erstattet av `PasientRolleForm` — enkel radio (Ingen / Førstehjelper / Helsepersonell) i brukeradmin
- Alle JS-moduler, templates, tester og admin oppdatert (~250 forekomster)
- 475 tester, alle grønne

### «Mine pasienter» — listevisning

- Endret fra checkbox/toggle til filterknapp i rekken med Alle / Rød / Gul / osv.
- Eksklusivt filter (ikke kombinerbart); klikker man en annen — nullstilles «mine»
- Server-side filtrering via `?mine=1` bevart; localStorage-persistering fungerer

### «Mine pasienter» — tavle

- Ny knapp ved siden av «Ny pasient» i tavle-visningen
- Viser alle pasienter, men dimmer (opacity + desaturate) pasienter som ikke er dine
- Ledige plasser («Ledig») påvirkes ikke

### Diverse UI

- Spacing-fix: «Ny pasient»-knappen har nå riktig avstand ned til sonene i tavlen

---

## 2026-05-16 — Mørkt tema konsolidert

### Designstrategi

Portalen bruker nå et konsistent mørkt tema på alle sider — i harmoni med pasientregistrerings-appen. Prinsipp fremover: `portal.css` styrer all theming globalt; templates bruker bare Bootstrap-klasser og `--portal-*`-variabler, ingen inline `background:` eller `color:` for standard innholdsbokser.

### `portal.css` — utvidet til komplett dark-theme grunnmur

- **`.card`**: mørk bakgrunn (`--portal-surface`), synlig border (`--portal-border`), lys tekst
- **`.card-header/.card-footer`**: mørkere bakgrunn (`--portal-surface-2`)
- **`.table td, .table th`**: eksplisitt `color: var(--portal-text)` — fikser svart tekst i alle tabellceller inkl. `<strong>`-elementer
- **`code`**: lyseblå farge (`--portal-accent`) med svak blå bakgrunn — erstatter Bootstrap sin knallrosa standard (`#d63384`)
- **`.pagination`**: dark-theme for alle fremtidige pagineringselementer
- **Kommentar**: oppdatert til å reflektere faktisk innhold

### `base_portal.html` `:root` — Bootstrap-tokens

- `--bs-body-bg`, `--bs-body-color`, `--bs-border-color` lagt til — gir Bootstrap-utilities korrekte mørke verdier og synlig kortkant mot mørk sidefarge

### Global dato/klokkeslett

- **`portal-clock.js`**: Ny dedikert fil med `updateClock()` — viser norsk dag, dato og tid (oppdateres hvert sekund)
- **`base_portal.html`**: `#header-dt`-element lagt til i headeren (mellom varselbjelle og avatar) — klokken vises nå på alle portal-sider
- **`script.js`**: `DAYS_NO` og `updateClock()` fjernet — dekkes nå globalt av `portal-clock.js`

### Template-opprydding

- **`module_admin_list.html`**: redundante inline-stiler på `<table>` og `<thead>` fjernet — portal.css håndterer dette globalt
- **`audit_log_list.html`**: 5 duplikate CSS-regler fjernet fra `{% block extra_head %}`; `.pagination`-regler flyttet til portal.css; audit-spesifikke regler beholdt

---

## 2026-05-15 (sesjon 2)

### CSS-gjennomgang og fremtidssikring

- **Bootstrap dark-theme tokens**: `--bs-body-color`, `--bs-body-bg` m.fl. overstyrt i `:root` slik at alle Bootstrap text-/bg-utilities automatisk fungerer mot portalens mørke bakgrunn
- **`portal.css`**: Ny fil for Bootstrap dark-theme overrides (`.text-muted`, `.card`, `.table`, `.form-control`, `.alert-*`). Erstatter inline CSS-blokk i `base_portal.html`
- **CSS-variabel-aliaser**: `--surface-1`, `--border-color` m.fl. aliasert til `--portal-*` for bakoverkompatibilitet
- **4 accounts-templates migrert**: `change_password.html`, `user_form.html`, `user_detail.html`, `ratelimited.html` byttet fra `base.html` til `base_portal.html`
- **Kortbakgrunn-fix**: `--bs-table-bg: transparent` lagt til i `.table`-regel — forhindrer at Bootstrap tildekker kortets bakgrunnsfarge med sidefarge

### Prosjektstruktur

- 14 historiske `.md`-filer flyttet til `docs/`-mappe
- `CHANGELOG.md` og `TODO.md` opprettet i roten

481 tester, alle grønne.

---

## 2026-05-15 (sesjon 1)

### URL-rydding: server-status flyttet

- Kanonisk URL endret fra `/pasienter/admin/server-status/` → `/portal-admin/server-status/`
- Bakover-kompatible redirects (301) bevarer gamle URL-er
- 4 hardkodede `fetch()`-URL-er i `admin_status.html` erstattet med Django `{% url %}`-tags via `ADMIN_URLS`-objekt
- Middleware-skiplist, tester (~30 referanser) og legacy-redirect i `core/urls.py` oppdatert

### Visuell konsistens

- **Server-status**: CSS-variabler (`--surface-1` etc.) byttet til `--portal-*`-varianter etter template-bytte
- **Portal-header**: Brukernavn og rolle-badge fjernet fra headeren, vises nå kompakt øverst i dropdown
- **Admin-nav**: «Brukere»-lenke lagt til for admin-brukere
- **Pasientmodul-dropdown**: «Min profil»-lenke lagt til

### Testresultat

481 tester, alle grønne.

---

## 2026-05-14 (tidligere sesjon)

### Fase 5: Bruker-behandler-kobling + varselbjelle

- Behandlere og helsepersonell kan kobles til brukerkonto
- Generisk varsel-bjelle implementert med deduplisering (24t-vindu)
- `script.js` delt opp i 4 moduler: `patients-utils.js`, `patients-table.js`, `patients-forms.js`, `patients-stats.js`
- `accounts/users/` og `admin_status.html` byttet fra `base.html` til `base_portal.html`
