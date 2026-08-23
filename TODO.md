# TODO – Sanitetsportalen

**Dette er arbeidslista.** Skal noe gjøres, står det her. Dokumentene i `docs/` er
underlaget — de forklarer bakgrunn, vurderinger og framgangsmåte, men de er ikke lista over
hva som står for tur. Er et punkt i et docs-dokument ikke representert her, blir det ikke
gjort.

| Hvor | Hva |
|---|---|
| `TODO.md` (denne) | Hva som skal gjøres |
| [`CHANGELOG.md`](./CHANGELOG.md) | Hva som er gjort |
| [`docs/`](./docs/) | Referansedokumenter og prosedyrer — ikke arbeidsliste |
| [`CLAUDE.md`](./CLAUDE.md) | Kort arkitekturoversikt for utvikling |

Ferdige punkter krysses av her og beskrives i CHANGELOG — i samme commit som endringen,
jf. arbeidsflyten i `CLAUDE.md`.

---

## ⚠️ Krever Andre — kan ikke gjøres fra kodebasen

Disse står ikke i kode. De krever Railway-innlogging eller en avgjørelse utenfor
prosjektet, og blir liggende til du gjør dem. Ingen av dem oppdages av testsuiten, og
ingen av dem gir feilmelding — de er bare stille inaktive.

- [x] **`ADMINS` og `EMAIL_*` satt i Railway, og verifisert.** AHASend via
      `send.ahasend.com:587`, avsender `noreply@mail.sanitet.net`. Bekreftet 22. aug. 2026
      med `python manage.py verifiser_feilvarsel` kjørt i containeren: melding sendt og
      godtatt over AHASends HTTP-API v2, `AdminEmailHandler` koblet på `django.request`,
      og en ekte exception gjennom hele kjeden. Begge e-postene bekreftet i innboksen.
      - [x] **Variablene står i `production`.** Miljøet ble ikke flyttet — det gamle
            `production` (den gamle appen) ble slettet, og portalens miljø døpt om.
            Variablene fulgte dermed med av seg selv. Nøklene som betyr noe er `ADMINS`,
            `DEFAULT_FROM_EMAIL`, `AHASEND_API_KEY` og `AHASEND_ACCOUNT_ID`
      - [x] **Railway sperrer utgående SMTP.** Målt fra containeren 22. aug. 2026:
            portene 587, 2525, 465 og 25 er alle stengt, 443 er åpen. Løst med en
            egen backend mot AHASends HTTP-API (`core/mail_backends.py`). Å bytte
            SMTP-leverandør ville truffet samme vegg — det er en plattformpolicy,
            ikke noe ved AHASend

- [x] **Cron-jobbene står i Railway (22. aug. 2026).** Begge i `production`-miljøet,
      bygget fra portal-repoet, med `restartPolicy: NEVER`:
      | Tjeneste | Start Command | Plan |
      |---|---|---|
      | `purge_old_logs` | `python manage.py purge_old_logs` | `0 0 * * SUN` |
      | `kollaps_arkiv` | `python manage.py kollaps_arkiv` | `0 4 1 * *` |

      Begge tørrkjørt mot produksjonsdatabasen: `kollaps_arkiv` har ingenting å kollapse
      (arkivene er fra 2026, grensen er 730 dager), `purge_old_logs` fant 3 varsler eldre
      enn 30 dager.
      - **`startCommand` må settes eksplisitt.** Uten den arver tjenesten `Procfile`-ens
        `web:`-linje og starter gunicorn i stedet for kommandoen — jobben gjør da ingenting
        og feiler ikke. Begge manglet den i første oppsett
      - **`OFFLINE_MODE` må ikke stå på en cron-tjeneste.** `settings.py` kaster
        `ImproperlyConfigured` ved oppstart på Railway, med vilje. `kollaps_arkiv` hadde
        den, og ville krasjet stille én gang i måneden
      - [ ] **Kjør `kollaps_arkiv --dry-run` manuelt før første skarpe kjøring 1. sept.**
            Den sletter helseopplysninger permanent. `docs/OPPSETT_KOLLAPS_CRON.md`
            beskriver framgangsmåten. **Dokumentet er ditt** — du sletter det selv når du
            er trygg på jobben

- [x] **Portalen står i `production` (22. aug. 2026).** Gjennomført i denne rekkefølgen:
  1. Dataimporten fra den gamle appen — 273 pasienter, se CHANGELOG
  2. Det gamle `production`-miljøet (den gamle Pasientregistreringsappen) slettet, og
     portalens miljø døpt om fra `staging` til `production`. **Ingenting ble flyttet** —
     alternativet var å migrere hele produksjonsdatabasen mellom to Postgres-instanser,
     for å vinne et navn
  3. `purge_old_logs` og `kollaps_arkiv` satt opp som cron — se «Krever Andre» øverst

      Miljøet har nå tre tjenester som alle bygger fra `Animax1/sanitetsportalen`.
      Navneforvirringen som traff oss tre ganger 22. august er dermed borte.

      **Den gamle appens database er slettet.** Din manuelle backup i portalen er eneste
      gjenopprettingspunkt for de 273 importerte pasientene.

      - [x] **Cron er verifisert i drift (23. aug. 2026).** `purge_old_logs` fyrte natt til
            søndag 23. august og slettet de 3 varslene fra 12. mai. Cron-tjenestens logg
            viser `Slettet 3 varsler eldre enn 30 dager` — den skarpe varianten, ikke
            tørrkjøringens `Ville slettet`. Mekanismen er dermed bevist ende-til-ende: cron
            utløser, `startCommand` treffer riktig kommando, og slettingen rammer de
            riktige radene. Ført inn i `PERSONVERN_DOKUMENTASJON.md` A.9 (v1.6), og
            backloggens F2 regnes nå som reell for portalen.
            **Sjekklistepunktet i C.4 er bevisst ikke krysset av** — C.4 er malen for
            *årlig* revisjon og skal stå tom, ellers ville avkryssingen stått der i 2027
            også og påstått noe den ikke har dekning for. Verifiseringen hører hjemme som
            datert merknad ved A.9, der lagringstidene faktisk står.
            - [ ] Bekreft gjerne radnivået med egne øyne ved anledning:
                  `railway ssh --service web -- python manage.py shell -c "from core.models import Notification; print(Notification.objects.count())"`
                  → forventet `1`. Ikke et krav for avkryssingen over; loggen fra
                  containeren er beviset

- [ ] **Fyll inn organisasjonsnavn i A.4** i `docs/PERSONVERN_DOKUMENTASJON.md`.
      Står fortsatt som `[fyll inn organisasjonsnavn]`. Dokumentet er
      behandlingsprotokollen overfor tilsynsmyndighet.

## Pågående / neste

### GDPR-gjennomgang

Fase 0–5 er gjennomført. Begrunnelsene og de varige beslutningene ligger i
[`docs/PERSONVERN_DOKUMENTASJON.md`](./docs/PERSONVERN_DOKUMENTASJON.md); hva som ble gjort
står i [`CHANGELOG.md`](./CHANGELOG.md). Tre punkter gjenstår:

- [ ] Fyll inn organisasjonsnavn i A.4 — se «Krever Andre» øverst
- [x] Cron-jobb for `kollaps_arkiv` satt opp — se «Krever Andre» øverst
- [ ] **Skriftlig DPIA-vurdering.** Uten journalplikt, med pseudonymiserte data og
      begrenset omfang er art. 35 trolig ikke utløst. Det som trengs er en kort skriftlig
      begrunnelse for *at* en DPIA ikke er nødvendig — ikke en full DPIA. Vurderingen hører
      hjemme i personverndokumentasjonen når den er skrevet. Ikke påbegynt

### Forbedringsbacklog

Kodegjennomgangen fra 12.–13. august 2026 fant 28 punkter (N1–N13, S1–S7, F1–F9).
**23 er gjennomført** — hva som ble gjort og hvorfor står i `CHANGELOG.md` under
13.–22. august. Det som står igjen er listet under, i dokumentets egen rangering.

- [ ] **S3 — Rate-limiting finnes kun på innlogging.** ~2 t. `@ratelimit` forekommer
      nøyaktig to steder i kodebasen, begge på `login_view`. Ubeskyttet i dag:
  - `POST /pasienter/api/patients/` — en `read_write`-bruker eller en stjålet sesjonscookie
    kan opprette pasienter i løkke så fort serveren rekker. Uten F3 finnes ingen bremse
  - `POST /accounts/change-password/` — ingen struping på gjetting av `old_password`
  - `GET /pasienter/api/full-stats/` — appens dyreste spørring. Cachet 60 s, men
    cache-miss-stien er ubeskyttet
  - `GET /portal-admin/auditlog/eksport.csv` — 5000 rader per kall, ubegrenset antall kall

      Lavere prioritet fordi alt krever innlogging og brukergruppen er liten og kjent. Men
      `django-ratelimit` og nødbryteren `RATELIMIT_ENABLE` finnes allerede, så kostnaden er
      lav. Foreslått: `@ratelimit(key='user', rate='60/m', method='POST', block=True)` på
      skriveendepunktene, strengere (`10/5m`) på passordbytte. **Merk:** rate-limiting med
      LocMemCache er per prosess — i lavkostnad-modus (1 worker) er det riktig, i vakt-modus
      deles telleren via Redis.
      *Akseptanse:* ingen autentisert bruker kan generere ubegrenset skrivelast mot databasen.

- [ ] **F3 — Server-side idempotency ved pasient-opprettelse.** ~2–3 t. Utløst av en reell
      hendelse: 30. april 2026 ble en pasient registrert dobbelt på Grønn sone i prod fordi
      brukeren dobbeltklikket før serveren rakk å svare. På delte soner finnes ingen
      unik-sjekk, så begge requests gikk gjennom.
      Fix A (`withSubmitGuard()` i `patients-utils.js:41`) er på plass, men beskytter ikke
      API-klienter, to faner med samme skjema, eller automatisk nettverks-retry.
      Fix B: frontend genererer `crypto.randomUUID()` når skjemaet åpnes og sender den som
      `idempotency_key`. Backend slår opp `patient_create:{user.id}:{key}` før opprettelse;
      treff gir samme respons som første gang (status 200, ikke 201), lagret i 5 min.
      **Bruk `cache.add()`, ikke `get()`+`set()`** — sistnevnte er ikke atomisk.
      **Risiko:** krever Redis. I lavkostnad-modus er cachen per prosess, så beskyttelsen
      gjelder kun innen én worker. Cache-feil må falle tilbake til «opprett uansett» —
      bedre dobbel registrering enn ingen registrering.
      *Akseptanse:* to raske POST-er med samme nøkkel gir én pasient.

- [ ] **F4 — Lasttest før stor vakt.** ~3–4 t. `locust` eller enklere script: 20 samtidige
      innloggede brukere, polling av pasientlista hvert 30. sek, 5 brukere oppretter pasient
      hvert 2. min, 2 endrer en eksisterende hvert min. Kjør mot staging.
      Sjekk: gj.snitt responstid < 500 ms, ingen 5xx, cache-hit-ratio i admin-dashbordet,
      minne og CPU i Railway-metrics.
      **Ta MFA-rate-limit med i testplanen** — den delte bøtta (N4) var nettopp den
      feiltypen en lasttest fanger, og som ellers først merkes ved en reell vaktstart.
      *Akseptanse:* rapport som viser at konfigurasjonen tåler 25 samtidige uten degradering.

- [ ] **`style-src`-delen av CSP-strammingen.** Utenfor F5s akseptansekriterium, men
      `unsafe-inline` står fortsatt for stiler. ~50 inline `style=` i markup pluss
      JS-genererte stiler i statistikk-tabellene må flyttes til CSS-klasser først.
      Ikke påbegynt. Nevnt som kjent avvik i personverndokumentasjonen (§ sikkerhetstiltak).

- [ ] **Statistikk-utvidelse (tidligere F6).** ~25–35 t, faseinndelt. Flyttet ut som eget
      beslutningsnotat: [`docs/BESLUTNING_STATISTIKK.md`](./docs/BESLUTNING_STATISTIKK.md).
      **Fem spørsmål må besvares før noen skriver kode** — de står nederst i notatet.
      Underlaget mangler i dette repoet; det ligger i den gamle Pasientregistreringsappen.

- [ ] **F9 — Kolonne-kryptering av følsomme felter.** **Nedprioritert, ikke planlagt.**
      Verdien falt da GDPR fase 3.1 kom: arkiverte rader kollapser til aggregat etter 24
      måneder, så mengden helsedata som faktisk ligger lagret over tid er kraftig redusert.
      Det er den mekanismen som bærer dataminimeringen nå, ikke kryptering. Feltnivå-
      kryptering kompliserer spørringer, indekser og nøkkelrotasjon. Tas kun ved skjerpet
      trusselbilde eller eksplisitt krav.

- [ ] **Løs tråd fra F7:** første-paint på mobil 4G ble aldri målt. `read_only` laster nå
      49 % av admin-bundlen, men gevinsten i faktisk oppstartstid er udokumentert.

**F8 (PgBouncer) er avklart som ikke aktuell** og står ikke som oppgave: ved 4 workers ×
4 tråder bruker appen 16 forbindelser mot Railway Postgres' grense på ~100, og
`conn_max_age=600` demper ytterligere. Flaskehalsen var spørringer og båndbredde, ikke
forbindelser. Tas opp igjen kun hvis `WEB_WORKERS` settes til 4 eller mer.

## Ideer / backlog

### Brukere, e-post og roller — se `docs/BESLUTNING_BRUKERE_OG_EPOST.md`

Besluttet 14. aug. 2026: invitasjon som registreringsvei, selvbetjent passord-reset for
personlige kontoer, admin-reset beholdt for alle. Ingenting bygget ennå.

- [x] **Blokkeringen er opphevet.** Utsending verifisert 22. aug. 2026 via AHASends
      HTTP-API v2, med SPF/DKIM på plass og testmeldinger bekreftet i innboksen.
      Reset-funksjonen er ikke lenger inert av mangel på e-post.
- [ ] **Databehandleravtale med AHASend**, og AHASend + Google inn i
      `PERSONVERN_DOKUMENTASJON.md` A.2. **Forfalt** — leverandøren er allerede i bruk for
      feilvarsling, ikke bare planlagt. Se `docs/BESLUTNING_BRUKERE_OG_EPOST.md` §4.
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

- [x] **Importert 22. aug. 2026: 273 pasienter, 12 nye førstehjelpere, 6 nye
      helsepersonell.** Alle kontroller grønne — antall, triage-fordeling, koblinger,
      `journal`, `lege` og tegnsett stemmer mot gammel prod. 273 `IMPORT`-rader i
      auditloggen. `enja` og `morten` ble gjenbrukt, ikke duplisert.
      - [ ] **Ta en manuell backup i portalen** (`/portal-admin/backup/`) som
            gjenopprettingspunkt for importen. Må gjøres fra containeren eller
            nettsiden — `BACKUP_DIR` er Railways volum, så en lokal `db_backup`
            skriver til feil sted
      - [ ] Åpne statistikkfanen og se over nøkkeltallene med egne øyne. Tallene er
            verifisert mot kilden programmatisk, men ikke sett i grensesnittet

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
      - A.9 lagringstider: `purge_old_logs` er **verifisert i drift 23. aug. 2026** og
        dokumentert med datert merknad (v1.6). `kollaps_arkiv` gjenstår — den har ennå
        ikke hatt noe å kollapse, så påstanden om 24-måneders-grensen er foreløpig
        udekket av en faktisk kjøring. Se S7 i CHANGELOG for hvorfor en dokumentert,
        men ikke-reell kontroll er det alvorligste avviket
      - **E-postvarsling ved feil er ikke omtalt i dokumentet i det hele tatt.** Det er
        en dataflyt ut av systemet til to tredjeparter — AHASend (utsending) og Google
        (mottakerens innboks) — og begge er databehandlere som hører hjemme i A.2.
        Varselet inneholder, etter slankingen 22. aug.: brukernavn og rolle på den som
        opplevde feilen, klient-IP, forespurt URL og traceback. **Ingen kliniske
        opplysninger** — skjemadata, cookies, settings og lokale variabler er utelatt,
        og `core/tests_error_reporting.py` vokter det. Lagringstid styres av Gmail,
        ikke av applikasjonen, på samme måte som Railway-backupen i A.2
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
