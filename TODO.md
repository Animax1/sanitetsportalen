# TODO – Sanitetsportalen

**Dette er arbeidslista.** Skal noe gjøres, står det her. Dokumentene i `docs/` er
underlaget — de forklarer bakgrunn, vurderinger og framgangsmåte, men de er ikke lista over
hva som står for tur. Er et punkt i et docs-dokument ikke representert her, blir det ikke
gjort.

| Hvor | Hva |
|---|---|
| `TODO.md` (denne) | Hva som skal gjøres |
| [`CHANGELOG.md`](./CHANGELOG.md) | Hva som er gjort |
| [`docs/README.md`](./docs/README.md) | Kart over all dokumentasjon, aktiv og arkivert |
| [`CLAUDE.md`](./CLAUDE.md) | Kort arkitekturoversikt for utvikling |

Ferdige punkter krysses av her og beskrives i CHANGELOG — i samme commit som endringen,
jf. arbeidsflyten i `CLAUDE.md`.

---

## ⚠️ Krever Andre — kan ikke gjøres fra kodebasen

Disse tre står ikke i kode. De krever Railway-innlogging eller en avgjørelse
utenfor prosjektet, og blir liggende til du gjør dem. Ingen av dem oppdages av
testsuiten, og ingen av dem gir feilmelding — de er bare stille inaktive.

- [ ] **Sett `ADMINS` og `EMAIL_*` i Railway.** Uten dem er e-postvarslingen ved
      uhåndterte feil (F1) helt inert — den skriver til konsoll, og du får aldri
      beskjed når noe kræsjer i prod.
      - `ADMINS` har formatet `Navn:epost`, komma-separert
      - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
        `EMAIL_USE_TLS`
      - **Verifiser med en framprovosert 500**, ellers vet du ikke om det virker
      - Se `docs/FORBEDRINGER_2026-08.md` → F1

- [ ] **Sett opp cron-jobb for `kollaps_arkiv` på Railway.** Uten den kollapser
      ikke arkiverte pasientrader til aggregat etter 24 måneder, og lagringstiden
      i personvernprotokollen (del A, punkt A.9) håndheves ikke i praksis. Det er
      en slettepraksis vi har beskrevet overfor både de registrerte og
      tilsynsmyndighet.
      - Framgangsmåte: `docs/OPPSETT_KOLLAPS_CRON.md`. **Dokumentet er ditt** — det
        beskriver en oppgave bare du kan utføre, og du sletter det selv når jobben står.
        Det skal ikke foldes inn i TODO eller ryddes bort av en opprydding

- [ ] **Fyll inn organisasjonsnavn i A.4** i `docs/PERSONVERN_DOKUMENTASJON.md`.
      Står fortsatt som `[fyll inn organisasjonsnavn]`. Dokumentet er
      behandlingsprotokollen overfor tilsynsmyndighet.

## Pågående / neste

### GDPR-gjennomgang — se `docs/GDPR_TILTAKSPLAN.md`

- [x] Fase 0: taushetsplikt avklart (signert erklæring via organisasjonen)
- [x] Fase 1: personvernprotokoll omskrevet til v1.5 — journalplikt ute, lagringstider korrigert
- [ ] Fyll inn organisasjonsnavn i A.4 — se «Krever Andre» øverst
- [x] Fase 2.1: serverside-whitelist på kliniske felt (inkl. `lege`)
- [x] Fase 2.2: `SECRET_KEY` hard-fail når `DEBUG=False`
- [x] Fase 2.3: slett varsler eldre enn 30 dager
- [x] Fase 2.4: fjern død «Arkiv (filer)»-seksjon (`archives_view`)
- [x] Fase 3.1: arkiverte pasientrader kollapser til aggregat etter 24 mnd
- [ ] Sett opp cron-jobb for `kollaps_arkiv` — se «Krever Andre» øverst
- [x] Fase 3.2: arkiv som egen backup-modul
- [x] Fase 4.1: `VaktArkiv.importert_av` → `SET_NULL` + frosset navn
- [x] Fase 5: doc-konsolidering og sammenslåing av backup-flatene
- [ ] Fase 5: **skriftlig DPIA-vurdering.** Uten journalplikt, med pseudonymiserte data og
      begrenset omfang er art. 35 trolig ikke utløst. Det som trengs er en kort skriftlig
      begrunnelse for *at* den ikke er nødvendig — ikke en full DPIA. Ikke påbegynt

Når disse tre er lukket, har `GDPR_TILTAKSPLAN.md` gjort jobben sin og kan slettes.
De varige beslutningene ligger allerede i `PERSONVERN_DOKUMENTASJON.md`.


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
  - [ ] Driftsoppgave: sett `ADMINS` og `EMAIL_*` i Railway — se «Krever Andre» øverst
- [x] **F2** Var allerede på plass — `purge_old_logs` kjører som Railway Cron Job.
      Gjennomgangens premiss var feil; se rettelse i FORBEDRINGER og S7
- [x] **N5** `current_local_year()` brukes begge steder — nyttårsvakter havner i riktig år
- [x] **N7** Delt Redis-klient per prosess (var én TCP-handshake per request)
- [x] **N8** Audit-signalet skriver med `bulk_create` — konstant antall spørringer
- [x] **N12** `GET /api/settings/` har whitelist som speiler PUT-ens. En ny
      `AppSetting`-nøkkel lekker ikke ut før noen legger den til bevisst.
- [x] **N11** CLAUDE.md i samsvar med koden. Tre påstander rettet i dokumentet
      (stats-caching, backup, frontend), én i koden: de tre produksjonsfilene importerer nå
      fra `core.auth_decorators`, og en test hindrer at shimen tas i bruk igjen.
      `invalidate_stats_cache()` er slettet — ingen kalte den, og TTL er hele mekanismen.
- [x] **N9** `script.js` slettet, dobbeltklikk-vernet testet ved å kjøre guarden i node.
      Tiltakspunkt 3 besvart: grep-i-JS-tester er ikke nok alene.
- [x] **F5** CSP-stramming — `script-src` har ikke lenger `unsafe-inline`
  - [x] Trinn 1: alle inline event-handlere ute av markup (30 `onclick` i templaten,
        6 generert fra JS, 2 `oninput`, 7 `onsubmit`-bekreftelser). Verifisert manuelt
        i prod før trinn 2. `InlineHandlerTests` vokter det.
  - [x] Trinn 2: nonce per request på de fire inline `<script>`-blokkene, og
        `unsafe-inline` fjernet. `CspNonceTests` vokter at markup og header er i takt.
- [ ] `unsafe-inline` for `style-src` gjenstår. Utenfor F5s akseptansekriterium, men
      ~50 inline `style=` i markup pluss JS-genererte stiler i statistikk-tabellene må
      flyttes til CSS-klasser først. Ikke påbegynt.
- [x] **F7** Betinget lasting av `patients-stats.js`. Bootstrappen måtte flyttes ut
      først (ny `patients-app.js`) — å laste stats-fila betinget uten det ville tatt ned
      appen for `read_only` og `read_write`. read_only laster nå 49 % av admin-bundlen.
      **Ikke målt:** første-paint på mobil 4G.
- [x] **F8** PgBouncer — avklart som ikke aktuell. Ved 4 workers × 4 threads bruker
      appen 16 forbindelser mot grensen på 100, og flaskehalsen var spørringer og
      båndbredde, ikke forbindelser. Målte tall i `docs/RUNBOOK_VAKT.md` §3c.
- [x] **N13** Duplisert kode i `views.py`/`services.py` — alle tre delpunktene
  - [x] Feltlista: `ARKIVERT_PASIENT_FELTER` brukes alle tre stedene. Frosset med vilje,
        *ikke* utledet fra modellen — utledning ville fått alle eksisterende arkiver til å
        melde falsk «tukling». `ArkivFeltlisteTests` vokter utakt mot modellen.
  - [x] `_navneliste_views()` bygger begge navneregistrene. Feilmeldingene er pinnet i
        `NavneregisterFeilmeldingTests` — de var det eneste ingen test dekket.
  - [x] `views.py` (797 linjer) delt i fem moduler og slettet. Ingen shim; `urls.py` og
        testene peker direkte på `views_patients`, `views_registre`, `views_stats`,
        `views_arkiv` og `views_common`.
- [x] **N6** Statistikk-tabellene escaper feltverdier (`escHtmlValue()`), og markup koden
      bygger selv må merkes med `trustedHtml()`. Personell-listene escaper også navn —
      fritekst uten whitelist, ikke nevnt i punktet. `import_offline_data` validerer nå mot
      `choices.py` med `--force` som utvei. Vaktpost mot nye uescapede tabeller i
      `patients/tests_xss_stats.py`.
      **NB:** F5 (CSP `unsafe-inline`) ble ikke tatt med, tross anbefalingen i dokumentet.
      Backup-restore er også dekket nå — se punktet under.
- [x] **N10** `CustomUser.current_session_key` gjør innlogging til ett indeksert oppslag.
      Sikkerhetsstiene (passordbytte, admin-reset, frys, sletting) beholder full
      gjennomgang. **NB: krever migrasjon** — `accounts/0008_customuser_current_session_key`
      (kun AddField; se hendelsesnotatet i CHANGELOG for hvorfor den er håndskrevet)

#### Fortsatt åpne i FORBEDRINGER_2026-08

Disse sto i backloggen uten å være løftet hit. Rekkefølgen er dokumentets egen rangering.

- [ ] **S3** Rate-limiting finnes kun på innlogging. `@ratelimit` står to steder, begge på
      `login_view`. Ubeskyttet: `POST /pasienter/api/patients/` (en løpsk klient eller
      stjålet sesjon kan opprette i løkke), `POST /accounts/change-password/` (ingen
      struping på gjetting av gammelt passord), cache-miss-stien til `/api/full-stats/`, og
      `auditlog/eksport.csv` med 5000 rader per kall. Alt krever innlogging, derfor lavere
      prioritet — men `django-ratelimit` og nødbryteren `RATELIMIT_ENABLE` finnes allerede,
      så kostnaden er lav. ~2 t
- [ ] **F3** Server-side idempotency ved pasient-opprettelse. `withSubmitGuard()` (Fix A) er
      på plass, men beskytter ikke API-klienter, to faner med samme skjema eller automatisk
      nettverks-retry. Fix B: `idempotency_key` fra `crypto.randomUUID()` i POST-body, slått
      opp i cache før opprettelse. Utløst av en reell dobbeltregistrering 30. april 2026. ~2–3 t
- [ ] **F4** Lasttest-script før stor vakt. 20 samtidige brukere mot staging, verifiser at
      Redis + 2 workers × 4 tråder holder. **Ta N4 med i testplanen** — den delte
      MFA-rate-limit-bøtta er nettopp den feiltypen en lasttest fanger, og som ellers først
      merkes ved en reell vaktstart. ~3–4 t
- [ ] **F6** Statistikk-utvidelse: live-dashbord for alle innloggede + utvidet
      evalueringsstatistikk for admin/lead, som to uavhengige leveranser med ulik
      personvernprofil. Største enkeltpunkt i backloggen. **Underlaget mangler** — de to
      dokumentene seksjonen bygger på ligger i den gamle Pasientregistreringsappen, ikke
      her. ~25–35 t
- [ ] **F9** Kolonne-kryptering av følsomme felter. **Nedprioritert, ikke planlagt.** Verdien
      falt da GDPR fase 3.1 kom — kollaps til aggregat etter 24 mnd er det som bærer
      dataminimeringen nå, ikke kryptering. Tas kun ved skjerpet trusselbilde

## Ideer / backlog

### Brukere, e-post og roller — se `docs/BESLUTNING_BRUKERE_OG_EPOST.md`

Besluttet 14. aug. 2026: invitasjon som registreringsvei, selvbetjent passord-reset for
personlige kontoer, admin-reset beholdt for alle. Ingenting bygget ennå.

- [ ] **Blokkerer alt annet:** SMTP verifisert, inkludert SPF/DKIM og at mailen lander i
      innboksen. Uten det er reset-funksjonen inert og verre enn ingen funksjon.
      Se «Krever Andre» øverst.
- [ ] Databehandleravtale med e-postleverandør + oppføring i personvernprotokollen
- [ ] Migrasjon: `fullt_navn` og `er_delt_konto` på `CustomUser`. **Kun AddField, alene.**
      `CustomUser` arver `AbstractBaseUser`, så `first_name`/`last_name` finnes ikke.
- [ ] Invitasjonsflyt med signert lenke — brukeren setter sitt eget passord, admin
      formidler ingenting
- [ ] Passord-reset, med de sju punktene i notatet (delte kontoer utelatt, MFA ikke
      omgåelig, sesjoner drepes, `must_change_password` nullstilles, egen rate-limit-bøtte,
      kortere token-levetid, ingen kontoenumerering)

### Rollemodellen — trenger beslutning

Dagens modell er ett globalt `role`-felt pluss fem `kan_redigere_*`-flagg. Flaggene er
feilnavngitt: `help_text` sier at de styrer *synlighet* i dashboard og nav-meny, ikke
redigering. Med fire moduler til holder ikke modellen — en bruker kan trenge les/skriv i én
modul og les i en annen.

- [ ] Skill **tilgangsnivå per modul** (autorisasjon) fra **funksjon i felt**
      (førstehjelper/helsepersonell/bil). Det siste er domenedata og finnes allerede som
      FK fra `Forstehjelper.user`/`Helsepersonell.user` — det er ikke en rettighet.
- [ ] Vurder gjennomgangsmodell `ModulTilgang(bruker, modul_slug, nivå)` som erstatter de
      fem boolske flaggene. `admin` forblir global, ikke per modul.
- [ ] **Migrasjonen må deles i to deployer:** legg til tabellen og fyll den fra flaggene i
      én, fjern flaggene i en senere. Slås de sammen, mister en rollback dataene.

### Dataimport fra gammel prod — se `docs/DATAIMPORT_FRA_GAMMEL_PROD.md`

- [ ] Importer årets pasientdata fra den gamle Pasientregistreringsappen.
      `import_offline_data` leser den gamle appens skjema direkte — ingen ny kode trengs.
      Tre steg: `dumpdata` fra prod (read-only), bygg SQLite lokalt, importer med
      `--dry-run` først. Kjør mot staging før prod.

### Pasientmodulen — småting

- [ ] «Mine pasienter» er tydelig markert i pasientlista, men ikke i tavla.
      **Årsak funnet:** CSS-regelen er `.filter-btn.active-mine`
      (`static/css/style.css:275`), men `#btn-board-mine` har klassene
      `btn btn-outline-info btn-sm` — uten `filter-btn`. `toggleBoardMine()`
      legger på `active-mine`, men regelen matcher aldri.
      Fiks: legg `filter-btn` på knappen i `index.html:148`, og sjekk at den
      ikke arver uønsket bredde/marg fra klassen. Vurder samtidig om tavla og
      lista skal dele filtertilstand — i dag er `mineOnly` og `boardMineFilter`
      to uavhengige variabler, så filteret følger deg ikke mellom fanene.

### Skalering mot 2027 — se `docs/RUNBOOK_VAKT.md` §3c

Gjennomgang 13. aug. 2026, med 1000 pasienter og peak 100 brukere som premiss.

- [x] `select_related` + ETag på `/api/patients/` — 515 → 15 spørringer, og 304 uten
      kropp når ingenting er endret
- [x] **Generaliser arkivmønsteret** — `core/arkiv/` med `BaseArkivHandler` og registry,
      samme idiom som `core/backup/`. Core eier kanonisering, hashing og kollaps-
      orkestrering; handleren eier payloadens form. Signaturene er bit-identiske,
      låst av `ArkivSignaturLaastTests`. Ingen migrasjon.
  - [ ] **Gjenstår:** `AbstractArkiv`-basemodell for nye moduler. `VaktArkiv` har
        feltene i dag (`sha256`, `kollapset_at`, `aggregat`, `aggregat_sha256`,
        frosset `importert_av_navn`); park og oppdrag må ellers gjenta dem. Bevisst
        utsatt til modell nummer to faktisk skrives — da ser man hva som er felles,
        i stedet for å gjette. `VaktArkiv` skal *ikke* migreres til basemodellen.
- [ ] Park-registreringer blir **egen modell**, ikke rader i `Patient`. Holder sykestuas
      liste på ~250 rader i stedet for 1000, og matcher at dataene er enklere.
- [ ] Park-appen er et skriveendepunkt **uten innlogging**: signert lenke via
      `django.core.signing` (ikke gjettbar URL, kan tilbakekalles), rate-limit per token,
      og responsen returnerer kvittering — aldri data.
- [ ] **Oppdragsmodulen: unnta fritekstfeltet fra audit-verdilogging.** `AuditLog.old_value`
      og `new_value` er `TextField` med 730 dagers lagring, og feltlista utledes fra
      modellen (N2) — et nytt fritekstfelt havner der automatisk. Skriver en 113-operatør
      noe sensitivt og retter det, ligger begge versjonene i loggen i to år.
- [ ] Oppdragets «fjernes fra bilen etter 1–2 timer» er et **server-side visningsfilter**,
      ikke sletting. 113 og statistikken skal beholde raden.
- [ ] Protokollen må presiseres når fritekst innføres: A.6/A.12 begrunner i dag whitelisten
      med at kliniske felt ikke kan inneholde navn. Oppdragsdata («kvinne, pustevansker,
      sted, tidspunkt») er dessuten mer identifiserende enn pasientraden den knytter seg til.
- [ ] Vurder `cached_db`-sesjoner. `SESSION_SAVE_EVERY_REQUEST=True` med DB-sesjoner gir
      én UPDATE per request. Krever Redis, altså vakt-modus.

### Framtidige moduler

Portalrammeverket er bygget for flere moduler enn `patients` — modulregistry, per-modul
backup, per-modul arkiv og permission-flagg står allerede klare. De fem opprinnelige
faseleveransene som la det på plass er beskrevet i
[`docs/archived/`](./docs/archived/README.md).

De fem `kan_redigere_*`-flaggene på `CustomUser` ble pre-registrert i én migrasjon nettopp
for å slippe én migrasjon per ny modul. Se også «Rollemodellen» over — den beslutningen bør
tas før modul nummer to skrives, ikke etterpå.

- [ ] Vaktliste
- [ ] KO-tavle
- [ ] Integrasjon med produksjonsdatabase
- [ ] Lage Locus-klone, hente sted via enhetens GPS

**Uavklart før noen av dem bygges** (spørsmålene sto ubesvart i den opprinnelige
høynivå-skissen, `docs/archived/SANITETSPORTAL_PLAN.md` §7):

- [ ] Skal en «vakt» være ett enkelt arrangement, eller også dekke faste
      beredskapsperioder som ukentlig lagvakt? Avgjør feltene på modellen
- [ ] Skal en beredskaps-/oppdragsmodul brukes underveis i felt (mobilt, dårlig nett) eller
      i etterkant? Avgjør om offline-strategi og synk må bygges
- [ ] Skal rapportmodulen kun være intern (admin/lead), eller også gi tilgang til
      styre/oppdragsgivere? Avgjør rolle-flagg og eksportformat

> **Merk:** skissen antok modulene `vakter`, `utstyr`, `rapport` og `beredskap`. Retningen
> siden er blitt park og oppdrag (se «Skalering mot 2027» over). Arkitekturvalgene i
> skissen står seg — modullista gjør det ikke.

### Eget domene — portal.sanitet.net

- [x] Crawler-sperre på plass: `/robots.txt` + `X-Robots-Tag` på alle responser.
      Kun `/accounts/login/` og `/healthz/` er offentlige; alt annet krever innlogging
- [ ] **Koble domenet i Railway** og legg inn DNS-oppføringen. Krever Andre
- [ ] Sett `ALLOWED_HOSTS=portal.sanitet.net,<dagens>.railway.app` og
      `CSRF_TRUSTED_ORIGINS=https://portal.sanitet.net,https://<dagens>.railway.app`.
      Uten den første svarer appen 400 på det nye domenet, uten den andre feiler
      **hver POST**, innlogging inkludert. Merk formatet: `ALLOWED_HOSTS` uten
      `https://`, `CSRF_TRUSTED_ORIGINS` med
- [ ] Fjern det genererte `.up.railway.app`-domenet når portal-domenet er verifisert,
      så appen kun svarer på én adresse
- [ ] Rydd Railway-domenet ut av `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` etterpå

### Dokumentgjennomgang — når funksjonaliteten nærmer seg ferdig

Fire dokumenter beholdes fordi de ikke er arbeidslister: de er referanse, formelle
dokumenter eller prosedyrer man følger under press. Nettopp derfor koster det å la dem
drive fra koden. Gjennomgangen tas **når funksjonaliteten vi bygger nå er på plass** —
ikke før, for da ville den bare måttet gjøres om igjen.

Funnene under er allerede kartlagt, så jobben er avgrenset når den skal gjøres.

- [ ] **`docs/TEKNISK_DOKUMENTASJON.md`** (1776 linjer) — merket «April 2026», og har ikke
      fulgt med på fire måneders refaktorering. Målgruppen er en teknisk etterfølger som
      overtar drift, så feil her koster mest når den koster.
      - Heter fortsatt «Pasientregistreringssystemet», ikke Sanitetsportalen
      - `patients/views.py` er delt i fem moduler (N13.3) — alle henvisninger dit er døde
      - `core/backup/` med handler-registry og `core/arkiv/` er ikke beskrevet
      - Modulregistryet (`core/modules.py`, `ModuleSettings`) mangler
      - **Alternativet er å merke den ærlig** som «beskriver systemet per april 2026» og
        la CLAUDE.md være den levende oversikten. Å la den stå som oppdatert uten å være
        det er det dårligste valget

- [ ] **`docs/RUNBOOK_VAKT.md`** (469 linjer) — leses under vakt, på papir eller egen
      skjerm. En feil URL her oppdages i verste øyeblikk.
      - Seks forekomster av `https://<din-app>.railway.app/...` (linje 10, 61, 400, 403,
        404) må bli `portal.sanitet.net` når domenet står
      - Sjekk at tersklene i §3 stemmer med ytelsesarbeidet fra 13. aug. (1000 pasienter,
        100 brukere)

- [ ] **`docs/DEPLOY_GUIDE.md`** (205 linjer) — prosedyre for nytt miljø.
      - `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`-eksemplene (linje 43–44, 81) viser
        `.up.railway.app`. Oppdater til portal-domenet
      - Legg inn `EMAIL_*`-variablene for AHASend i variabeltabellen — de mangler helt

- [ ] **`docs/PERSONVERN_DOKUMENTASJON.md`** (809 linjer) — formelt art. 30-dokument som
      kan fremlegges for Datatilsynet. **Skal ikke slankes eller foldes inn i TODO.**
      Gjennomgangen her er en annen øvelse enn for de tre andre: verifiser at hver
      påstådte kontroll faktisk er reell i koden.
      - Organisasjonsnavn i A.4 — se «Krever Andre» øverst
      - A.9 lagringstider forutsetter at `purge_old_logs` og `kollaps_arkiv` faktisk
        kjører som cron. Står de ikke, beskriver dokumentet en slettepraksis som ikke
        finner sted — se S7 i CHANGELOG for hvorfor det er det alvorligste avviket
      - Nye behandlinger siden v1.5? E-post via AHASend er en databehandler som skal inn
      - Bump versjonsnummer og dato når noe endres

### Løse punkter

- [ ] Rydd bort død backup-legacy: modellen `patients.BackupConfig` (singleton som
      ingenting leser lenger) og management-kommandoen `db_backup` som gater på den.
      Krever migrasjon, derfor egen oppgave.
- [ ] Flytte sesjonsdelen til en admin-side
- [ ] Testene er massive, kan vi komprimere dem? (kjøretiden er løst: 500 s → 15 s via
      PASSWORD_HASHERS under test. Gjenstår evt. å redusere *antall* tester)
- [ ] Vurder `argon2-cffi` for sterkere passord-hashing i produksjon (i dag PBKDF2)
- [x] Fjerne varsler eldre enn 30 dager — gjort som GDPR fase 2.3, lagt i `purge_old_logs`
- [x] Slå sammen de to backup-flatene — kun `/portal-admin/backup/` gjenstår
- [x] Ryddet bort det ubrukte per-år-arrangementsnavnet — `set_event_name()`,
      `get_event_name()` og `get_event_name_or_legacy()` er slettet, sammen med
      `event_name_<år>` i `SETTINGS_READ_WHITELIST`. Ingen kalte dem.
- [x] Kliniske felt kontrolleres ved backup-restore. `BaseBackupHandler.inspect_restore_payload()`
      ser over fixturen før `loaddata`, og `PatientsBackupHandler` sjekker mot
      `patients/choices.py`. **Kontrollen advarer, den blokkerer ikke** — restore er
      nødstien og skal aldri kunne stoppes av en verdi som var lovlig da den ble lagret.
      Motsatt av `import_offline_data`, som avbryter og krever `--force`; forskjellen er
      tilsiktet og begrunnet i docstringen.
- [x] Slett `static/js/script.js` (N9). Testene er pekt om, og dobbeltklikk-vernet kjøres
      nå faktisk i node i stedet for å bli grep-et etter. `patients/js_test_utils.py` er
      felles plumbing for JS-tester.

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
