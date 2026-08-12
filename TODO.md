# TODO – Sanitetsportalen

## Pågående / neste

### GDPR-gjennomgang — se `docs/GDPR_TILTAKSPLAN.md`

- [x] Fase 0: taushetsplikt avklart (signert erklæring via organisasjonen)
- [x] Fase 1: personvernprotokoll omskrevet til v1.5 — journalplikt ute, lagringstider korrigert
- [ ] **Fyll inn organisasjonsnavn i A.4** (står som `[fyll inn organisasjonsnavn]`)
- [x] Fase 2.1: serverside-whitelist på kliniske felt (inkl. `lege`)
- [x] Fase 2.2: `SECRET_KEY` hard-fail når `DEBUG=False`
- [x] Fase 2.3: slett varsler eldre enn 30 dager
- [x] Fase 2.4: fjern død «Arkiv (filer)»-seksjon (`archives_view`)
- [x] Fase 3.1: arkiverte pasientrader kollapser til aggregat etter 24 mnd
- [ ] **Sett opp cron-jobb for `kollaps_arkiv`** — se `docs/OPPSETT_KOLLAPS_CRON.md`,
      slett den fila når jobben er på plass
- [x] Fase 3.2: arkiv som egen backup-modul
- [x] Fase 4.1: `VaktArkiv.importert_av` → `SET_NULL` + frosset navn


## Ideer / backlog

- [ ] Vaktliste
- [ ] KO-tavle.
- [ ] Fytte sesjons delen til en admin side.
- [ ] Integrasjon med produksjons database.
- [ ] Testene er massive, kan vi komprimere den? (kjøretiden er løst: 500 s → 15 s via
      PASSWORD_HASHERS under test. Gjenstår evt. å redusere *antall* tester)
- [ ] Vurder `argon2-cffi` for sterkere passord-hashing i produksjon (i dag PBKDF2)
- [ ] Fjerne varsler eldre enn 30 dager.s
- [ ] Lage locus klone, hente sted via enhet gps.
- [ ] Slå sammen de to backup-flatene. Pasientmodulens egen backup-side og
      `/portal-admin/backup/` er to UI-er over samme backend (samme `Backup`-tabell,
      samme filer, samme `core.backup.restore_backup`). Forvirrende at det ser ut som
      to systemer. Behold kun `/portal-admin/backup/` på overordnet nivå.

## Ferdig ✓

- [x] Sett `runtime.txt` tilbake til Python 3.13 (var utilsiktet 3.12) før Railway-repo-bytte
- [x] Rydde opp i CSS filene, det er flere plasser hvor tekst farger er for mørke, det må vi se litt på. Dette krever nok en del arbeid.
- [x] Del opp `script.js` i separate moduler (patients-utils, patients-table, patients-forms, patients-stats)
- [x] Visuell konsistens: `accounts/users/` og `admin_status.html` bruker nå `base_portal.html`
- [x] Flytt server-status URL: `/pasienter/admin/server-status/` → `/portal-admin/server-status/`
- [x] Fjern brukernavn/rolle fra portal-header, vis i dropdown i stedet
- [x] Legg «Brukere» til i admin-navigasjonen i portalen
- [x] «Min profil»-lenke lagt til i pasientmodul-dropdown
- [x] Global dato/klokkeslett i portal-headeren (alle sider, identisk med pasientregistreringen)
- [x] Faktisk kobling mellom brukere og behandler/helsepersonell.
- [x] "Mine pasienter" skal være lik de andre filtrene.
- [x] Vurder å endre behandler til førstehjelper?
