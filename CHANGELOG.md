# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

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
