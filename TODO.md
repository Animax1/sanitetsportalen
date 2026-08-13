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


### Forbedringsbacklog — se `docs/FORBEDRINGER_2026-08.md`

Kodegjennomgang 12. august 2026. Full liste med begrunnelse og tiltak ligger i dokumentet.
Sikkerhetspunktene rundt innlogging er ferdige; det som står igjen er drift, sporbarhet og
dokumentasjon.

- [x] **S1** `/django-admin/` er slått av i prod (kun bak `DEBUG`/`OFFLINE_MODE`).
      Paritetsarbeidet som måtte til først:
  - [x] 500-feil ved opprettelse av bruker uten e-post
  - [x] «Krev MFA» kan slås av og på fra brukeradmin
  - [x] Frys/tø konto med sesjonssletting
  - [x] Permanent sletting av brukerkonto (sperrer: ikke deg selv, ikke siste admin)
  - [x] Global `LoginEvent`-visning: `/portal-admin/innloggingslogg/`
  - [x] `AppSetting` redigeres med `python manage.py appsetting --set NØKKEL VERDI`
  - [x] Brukeradmin flyttet til `/portal-admin/brukere/`, 301 fra `/accounts/users/`
- [x] **S2** `create_superuser` arver `must_change_password=True`
  - [x] Bekreftet 13. aug. 2026: bootstrap-adminen i prod har byttet passord
- [x] **N1** `next`-parameteren valideres — `core/url_safety.py::safe_redirect_url()`
- [x] **S4** Samme validering på `Notification.url` i varsel-redirecten
- [x] **N4** MFA-stegene har egne rate-limit-bøtter, og kontosperren gjelder også der
- [x] **S5** Utlogging krever POST
- [x] **S6** MFA trust-cookie følger `request.is_secure()` — virker nå i offline-modus
- [x] **S7** Alle fire dokumentasjonspunkter lukket (audit-dekning via N2, lagringstider var
      ikke et avvik, escapeHtml-dekning og Argon2 rettet i teksten)
- [x] **N2** Audit-feltlista utledes nå fra modellen — et nytt felt kan ikke falle utenfor
- [x] **N3** `LOGGING` har rot-handler med formatering + `LOG_LEVEL`-variabel
- [x] **F1** E-postvarsel ved uhåndterte feil, med demping per feiltype
  - [ ] **Driftsoppgave:** sett `ADMINS` og `EMAIL_*` i Railway, og verifiser med en
        framprovosert 500. Uten dem er varslingen inert (skriver til konsoll)
- [x] **F2** Var allerede på plass — `purge_old_logs` kjører som Railway Cron Job.
      Gjennomgangens premiss var feil; se rettelse i FORBEDRINGER og S7
- [ ] **N4** MFA-steget deler én rate-limit-bøtte for alle brukere — kan gi 429 ved vaktstart
      (`accounts/views.py:141`)

- [x] **N5** `current_local_year()` brukes begge steder — nyttårsvakter havner i riktig år
- [x] **N7** Delt Redis-klient per prosess (var én TCP-handshake per request)
- [x] **N8** Audit-signalet skriver med `bulk_create` — konstant antall spørringer
- [x] **N10** `CustomUser.current_session_key` gjør innlogging til ett indeksert oppslag.
      Sikkerhetsstiene (passordbytte, admin-reset, frys, sletting) beholder full
      gjennomgang. **NB: krever migrasjon** — `accounts/0008`

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
- [x] Slå sammen de to backup-flatene — kun `/portal-admin/backup/` gjenstår
- [ ] Rydd bort død backup-legacy: modellen `patients.BackupConfig` (singleton som
      ingenting leser lenger) og management-kommandoen `db_backup` som gater på den.
      Krever migrasjon, derfor egen oppgave.
- [ ] Slett `static/js/script.js`. Den er den gamle monolitten fra før oppdelingen i
      moduler, lastes ikke av noen mal, og inneholder nå en død kopi av backup-panelet.
      **NB:** `DoubleClickGuardTests` i `patients/tests.py:965` leser denne fila — pek
      testene mot `patients-utils.js`/`patients-forms.js` i samme commit, ellers blir
      suiten rød. Se N9.

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
