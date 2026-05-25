# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

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
