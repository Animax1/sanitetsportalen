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
      - [x] **`kollaps_arkiv --dry-run` kjørt manuelt i containeren 23. aug. 2026.**
            Svar: «Ingen arkiv eldre enn 730 dager som ikke allerede er kollapset.»
            Ventet — arkivene er fra 2026. Første skarpe kjøring 1. sept. har dermed
            ingenting å slette, og tørrkjøringen har bekreftet at kommandoen starter
            og leser databasen riktig. `docs/OPPSETT_KOLLAPS_CRON.md` **er ditt** — du
            sletter det selv når du er trygg på jobben

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
**25 er gjennomført** — hva som ble gjort og hvorfor står i `CHANGELOG.md` under
13.–23. august. Det som står igjen er listet under, i dokumentets egen rangering.

- [x] **S3 — Rate-limiting utover innlogging (23. aug. 2026).** `core/ratelimit.py` med
      `rate_limit`-dekorator og `er_rate_limited`. Én bøtte per endepunkt, nøkkel per
      bruker:
      | Endepunkt | Metode | Grense |
      |---|---|---|
      | `POST /pasienter/api/patients/` | POST | 60/min |
      | `PUT`/`DELETE /pasienter/api/patients/<pk>/` | PUT, DELETE | 120/min |
      | `GET /pasienter/api/full-stats/` | GET | 30/min |
      | `POST /accounts/change-password/` | POST | 10/5 min, kun feilede gjett |
      | `GET /portal-admin/auditlog/eksport.csv` | GET | 10/min |

      Pasient-redigering sto ikke i den opprinnelige lista, men er tatt med: akseptansen
      handler om skrivelast mot databasen, og `PUT` er skrivelast.
      `accounts/views.py::_er_rate_limited` delegerer nå til kjernen, så innlogging får
      samme feilhåndtering.
      - **Funn underveis:** kommentaren i `settings.py` påsto at django-ratelimit «faller
        åpen av seg selv ved cache-feil». Det stemte ikke i noen av de to retningene —
        `RATELIMIT_FAIL_OPEN` er `False` som default (429 på alt når cachen svarer uten
        verdi), og `cache.add()` mot en død Redis kaster `ConnectionError` som pakken
        ikke fanger (500). Begge er nå håndtert, og kommentaren er rettet
      - **Frontend:** skjemaet håndterte kun 400, så en strupet registrering ville sett ut
        som ingenting — modalen åpen, ingen melding, pasienten ikke lagret. 429 vises nå,
        og statistikkfanen lar forrige visning stå i stedet for å rendre feilkroppen
      - Rate-limiting deler ikke teller mellom workers uten Redis. I dag kjører appen
        1 worker × 4 tråder, så telleren er felles. Avviket ved flere workers gjør bremsen
        mildere, aldri strengere — dokumentert i modulens docstring
      - **Rettet samme dag:** passordbytte hadde dekoratøren på hele viewet, som telte
        hver avvist skjemainnsending. `MustChangePasswordMiddleware` sperrer alt annet,
        så en ny bruker som fomlet med passordreglene ved vaktstart ville blitt stengt
        ute av hele portalen i fem minutter — og bøtta beskyttet ingenting, siden
        `old_password` ikke sjekkes i den stien. Telles nå kun ved feilet gjett på
        nåværende passord, i bøtta `password:old-guess`
      *Akseptanse innfridd:* 17 nye tester, 829 totalt, alle grønne.

- [x] **F3 — Server-side idempotens ved pasient-opprettelse (23. aug. 2026).**
      `core/idempotency.py`. Klienten lager en nøkkel når registreringsskjemaet åpnes
      (`nyIdempotensNokkel()`) og sender den som `idempotency_key`. Serveren reserverer
      nøkkelen med `cache.add()` — atomisk, ikke `get()`+`set()` — rett før opprettelsen.
      | Tilstand | Svar |
      |---|---|
      | Nøkkelen ledig | Oppretter, `201` |
      | Første forespørsel pågår | `409` med `duplikat: true` |
      | Nøkkelen brukt opp | Samme pasient, `200` (ikke `201`) |
      | Ingen/ugyldig nøkkel | Som før F3, `201` |

      **Reservasjonen skjer etter all validering.** Ellers ville en avvist innsending
      brent nøkkelen, og brukeren som rettet feilen fått «allerede sendt inn» på det
      korrigerte forsøket. Feiler `save()`, frigis nøkkelen med `forkast()`.
      - **`crypto.randomUUID()` kunne ikke brukes alene.** Den finnes kun i «secure
        context», altså ikke over ren HTTP — og `OFFLINE_MODE` kjører nettopp uten TLS.
        Uten fallback ville feltbruk kastet `TypeError` ved hver registrering.
        `crypto.getRandomValues` er tilgjengelig også uten TLS og brukes der
      - **To faner er ikke dekket, med vilje.** Nøkkelen lages når skjemaet åpnes, så to
        faner har hver sin — det er to reelle registreringer. Dekket er
        dobbeltinnsending fra samme skjema, automatisk nettverks-retry og API-klienter
        som prøver på nytt
      - **409 vises ikke som feil i grensesnittet.** Pasienten blir opprettet, så
        modalen lukkes og lista lastes — samme utfall som suksess. En rød boks ville
        bedt brukeren rette noe som ikke er galt
      - Beskyttelsen er per prosess uten Redis, som rate-limiting. I dag én worker, så
        den er reell nå
      *Akseptanse innfridd:* to raske POST-er med samme nøkkel gir én pasient.
      14 nye tester, 843 totalt, alle grønne.

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
- [x] **Databehandleravtalen med AHASend er allerede inngått (avklart 23. aug. 2026).**
      https://ahasend.com/dpa. Den krever **ingen signatur**: avtalen er inkorporert i
      Terms of Use, og «By using the Services, Controller accepts this DPA.» Den har altså
      vært i kraft siden portalen begynte å sende. Enterprise-kunder kan be om en
      motsignert utgave, men det endrer ikke rettsvirkningen.
      Nøkkelpunktene, til bruk i A.2:
      | Punkt | Innhold |
      |---|---|
      | Underbehandlere | Hetzner Online GmbH (DE/FI, US kun på forespørsel), DA International Group (BG), Blix Solutions AS (NO) |
      | Databehandling | «primarily within the European Economic Area» som standard |
      | Tredjelandsoverføring | Kun hvis kunden aktivt velger US-infrastruktur. SCC modul 2, nederlandsk rett |
      | Sletting | Innen 90 dager etter oppsigelse |
      | Revisjon | Innsyn og inspeksjon, evt. dekket av ISO 27001 / SOC 2-rapport |
      | Brudd | Varsling «without undue delay», med innhold som dekker art. 33(3) |
      | Datakategorier | E-postadresser, navn hvis oppgitt, innhold hvis lagring er på, leveringslogg, IP og user agent ved sporing |
      - [ ] **Bekreft at kontoen ikke står på US-infrastruktur.** Standard er EØS, men
            Hetzner US er tilgjengelig «upon request». Er den valgt, utløses SCC-sporet
            og A.2 må beskrive en tredjelandsoverføring. Krever Andre — ett blikk i
            AHASend-konsollen
      - [ ] **Vurder å slå av lagring av e-postinnhold** hos AHASend. Avtalen sier det
            kan deaktiveres. Feilvarslene våre inneholder brukernavn, rolle, klient-IP,
            URL og traceback — mindre som ligger lagret hos databehandleren, jo bedre
      - **Merk til A.12:** avtalen sier «Controller agrees not to use the Services to
        send or store Sensitive Data». Feilvarselet inneholder personopplysninger, men
        ingen helseopplysninger — skjemadata, cookies og lokale variabler ble slanket
        bort 22. aug., og `core/tests_error_reporting.py` vokter det. Den testen er
        dermed ikke bare en personvernfinesse lenger; den holder oss innenfor en
        kontraktsforpliktelse
- [ ] **AHASend og Google inn i `PERSONVERN_DOKUMENTASJON.md` A.2.** Selve avtalen er på
      plass (over), men dataflyten er fortsatt ikke dokumentert. Tas i
      dokumentgjennomgangen. Merk at C.3 linje 711 sier «Ingen andre databehandlere er
      for øyeblikket i bruk» — det er direkte feil i dag.
- [x] **Migrasjonsavvikene ryddet (23. aug. 2026).** `makemigrations --check` er nå ren,
      og `myproject/tests_migrations.py` håndhever det. Prod-tilstanden ble lest, ikke
      antatt: indeksen het `audit_audit_created_2c1626_idx` i databasen hele tiden —
      altså det modellen genererer — mens Djangos tilstand sto på `a3c1b8`. Rettet med
      `audit/0004` (`SeparateDatabaseAndState`, ingen SQL) og `accounts/0009`
      (`help_text` er en `non_db_attr`, `sqlmigrate` sier `-- (no-op)`).
      **Dette var en forutsetning for `fullt_navn`-migrasjonen**, som ville fått samme
      nummer som `is_superuser`-forslaget og dratt det med seg.
- [x] **Migrasjon: `fullt_navn` og `er_delt_konto` lagt til (23. aug. 2026).**
      `accounts/0010`, nøyaktig to `AddField` og ingenting mer — gevinsten fra
      opprydningen rett før. Ingen håndhevingslogikk for `er_delt_konto` i denne
      leveransen; de fire reglene hører til invitasjons- og reset-arbeidet.
- [x] **Invitasjonsflyt med signert lenke (23. aug. 2026).** `accounts/invitasjon.py`.
      Enbruks uten tabell: tokenet bærer et avtrykk av passord-hashen, så lenken dør i
      det passordet settes. Levetid 3 døgn, brukeren sendes til innlogging etterpå, og
      midlertidig passord beholdes som reserve for delte kontoer og for når e-post
      feiler. `er_delt_konto` fikk sine to første regler: valideringen nekter e-post og
      navn, og MFA kan ikke kreves.
      - [x] **Begge feltene lagt til i `AdminUserEditForm` også.** Uten dem kunne
            eksisterende kontoer aldri få navn — og alle kontoer er eksisterende.
            Samme kontotype-regler håndheves ved redigering: en personlig konto kan
            ikke gjøres delt med e-posten i behold, og MFA kan ikke slås på samtidig
            som «delt konto».
      - [x] **Admin-kontoen har e-post (23. aug. 2026).** Forutsetningen for at
            passord-reset skal virke for den ene kontoen ingen annen admin kan
            nullstille.
      - [x] **Ingen eksisterende konto er en delt bil-innlogging (bekreftet 23. aug.
            2026).** Migrasjonens `er_delt_konto=False` er dermed korrekt for alle
            eksisterende kontoer, og ingen av dem vil feilaktig få selvbetjent reset.
- [x] **Passord-reset med alle sju punktene (23. aug. 2026).**
      `accounts/passord_reset.py`. Levetid 1 time, egen salt, egen rate-limit-bøtte
      (3/10 min per adresse, 20/10 min per IP). Sesjoner avsluttes, MFA gjelder fortsatt
      fordi flyten ikke logger noen inn, og svaret er identisk enten adressen finnes
      eller ikke — verifisert ved å sammenligne `response.content`.
      Token-maskineriet er generalisert til `accounts/signert_lenke.py`, delt med
      invitasjonen. `PASSWORD_RESET_TIMEOUT` er bevisst ikke satt: den leses kun av
      Djangos egen generator, som ikke er i bruk.

### Rollemodellen — se `docs/BESLUTNING_ROLLEMODELLEN.md`

- [x] **Besluttet 24. aug. 2026.** Global admin, pluss ett nivå per modul:
      `ingen → les → skriv:handling → skriv:full`. `ModulTilgang(bruker, modul_slug, nivå)`
      erstatter de fem `kan_redigere_*`-flaggene, og `role` krymper til `admin`/`bruker`.
      Alle valg er tatt; dokumentet er fasit.
      - **Flaggene var aldri tilgangskontroll (verifisert).** `read_write` med
        `kan_redigere_pasienter=False` får 200 på `/pasienter/` og **201 på
        `POST /api/patients/`**. `permission_flag` leses kun av dashboard og nav.
      - **`ModuleSettings.enabled=False` stenger ikke URL-en (verifisert)** — 200 med
        modulen deaktivert.
      - **To-akse-modellen kollapset til én** da statistikk ble besluttet skilt ut:
        `lead_view` gir bare statistikk, og `dataset_scope_all` er død kode.


**Stigen står som opprinnelig besluttet:** `ingen → les → skriv:handling → skriv:full`.

- [ ] **VURDER: `leder`-nivå («admin light»).** Utsatt 28. aug. 2026 — bruken finnes,
      behovet gjør ikke. En vaktleder som skal kunne arkivere en vakt, se arkivet og
      redigere navneregistrene, uten å være global admin. Det irreversible (nullstilling,
      kollaps, brukeradmin, backup) forblir admin per §3.3. Se §3.1 i notatet.

      Å legge til verdien er en `-- (no-op)`-migrasjon; kostnaden ligger i å bestemme
      innholdet. **Tas opp igjen når noen faktisk skal ha nivået** — et tomt nivå er lett
      å dele ut i god tro, og gir automatisk mer den dagen det fylles.
Et femte trinn `leder` ble lagt til 28. aug. og reversert samme dag — begrunnelsen var at
et nytt nivå senere ville koste en migrasjon, og det stemmer ikke (`choices` er en
`non_db_attr`, migrasjonen er `-- (no-op)`). Se §3.1 i notatet. Innføres når noe faktisk
skal ligge der.

**Leveranse 1 er levert (28. aug. 2026):**

- [x] **Statistikk skilt ut som egen modul.** `statistikk/`-appen, `/statistikk/`-siden,
      `full_stats_view` og `arkiv_full_stats_view` flyttet, `stats_cache` til `core/`,
      `patients-stats.js` delt i `statistikk.js` og `patients-admin.js`, primitivene ut i
      `portal-utils.js`, statistikkreglene i eget stilark. Ingen migrasjon, ingen
      tilgangsendring. 911 tester grønne.
      - [ ] **Gjenstår fra §5: modulen komponerer ikke tilgang ennå.** Den gates på
            `stats_required` alene, så den viser pasienttall til alle med
            statistikktilgang — også en bruker som senere ikke har `patients: les`.
            Kravet «viser kun kilder brukeren har minst `les` på i kildemodulen» kan
            først innføres når `ModulTilgang` finnes. **Gjøres i deploy 1**, ellers er
            statistikkmodulen en bakvei rundt modultilgangen.
      - [ ] Tilgangstabellen i `docs/BESLUTNING_STATISTIKK.md` må skrives om til
            modulnivåer.

- [ ] **Forutsetning før migrasjonen skrives — kontrolleres i prod:** hvor mange kontoer
      har `role` ≥ `read_write` men `kan_redigere_pasienter=False`? Det er kontoene som i
      dag har en tilgang de ikke var ment å ha. Tallet avgjør hvor stor oppryddingen blir
      etter deploy 1.

- [x] **Statistikkmodulen skilt ut, og komponerer tilgang (28. aug. 2026).**
      - [x] Tilgangstabellen i `docs/BESLUTNING_STATISTIKK.md` skrevet om til
            modulnivåer (28. aug. 2026).

- [x] **Deploy 1 — ferdig 28. aug. 2026.**
      - [x] `ModulTilgang` lagt til og fylt fra `role` alene (28. aug. 2026).
            Synlighet og håndhevelse leser nå samme kilde. `ModuleSettings.enabled=False`
            stenger URL-en. `@modul_kreves` finnes, med markør URL-testen kan lese.
      - [x] `@modul_kreves(...)` satt på alle endepunkter (28. aug. 2026), med
            URL-gjennomgangstest og unntaksliste med begrunnelse. Hullet fra §2.1 er
            lukket og målt: `POST /api/patients/` uten modultilgang gir 403, ikke 201.
      - [x] §5-komposisjonen: statistikk viser kun kilder brukeren har `les` på
### ⚠️ Kontoopprydding i prod — MÅ gjøres før deploy til prod

- [ ] **Slett alle kontoer unntatt admin-kontoen(e) og én les/skriv-konto.**
      Bestemt av André 28. aug. 2026. Kollegaen som skal bruke les/skriv-kontoen videre
      beholder den; resten er testkontoer og gamle kontoer som ikke skal med over.
      - [ ] **Noter hvilken konto som beholdes, og hvilket nivå den skal ha**, før noe
            slettes. Etter slettingen finnes ikke fasiten noe sted.
      - [ ] **Ta backup først.** `CustomUser` er bevisst utelatt fra begge
            backup-handlerne (se CLAUDE.md), så en slettet konto er *ikke* i noen
            portal-backup. Ta en `dumpdata accounts` manuelt, eller aksepter at
            slettingen er endelig.
      - [ ] **Sletting av en bruker fjerner `ModulTilgang`-radene** (CASCADE) og setter
            `Forstehjelper.user`/`Helsepersonell.user` til NULL (SET_NULL). Navnene
            beholdes på historiske pasienter — det er meningen — men koblingen må settes
            opp på nytt for kontoen som beholdes.
      - [ ] **Auditloggen beholder radene.** `AuditLog.record_id` er en ren integer uten
            FK nettopp for at sporet skal overleve slettingen. `AuditLog.user` blir NULL,
            så «hvem gjorde dette» går tapt for de slettede — det er en bevisst
            avveining, men verdt å vite før man sletter.
      - [ ] **Kontroller etterpå at minst én admin står igjen og kan logge inn.**
            Sletter du deg selv ut, finnes det ingen vei inn utenom `create_admin` på
            Railway-konsollen.
      - [x] **Oppryddingen er gjort (28. aug. 2026).** Prod har nå én ikke-admin-konto
            (kollegaens, midlertidig redusert til lesing) pluss admin.
      - [x] **Kollegaens nivå satt (28. aug. 2026):** `patients: skriv_full`,
            `statistikk: les`, og Helsepersonell-koblingen på plass.

- [x] **Testkontoen i prod — avklart 28. aug. 2026.** Den er Andrés egen konto uten
      admin, ikke en anonym testbruker, og André håndterer den selv. Bekymringen i
      forrige punkt var at et ukjent navn kunne skrive i pasientlista under vakt; det
      premisset holdt ikke. Kontoen kan slettes eller settes `is_active=False` fra
      brukeradmin — sletting fjerner `ModulTilgang`-radene (CASCADE) og nuller
      `Helsepersonell.user` (SET_NULL), auditradene består, men `AuditLog.user` blir NULL.
      - [x] **Kontrollen kjørt mot prod etter deploy 1 (28. aug. 2026).** §10.1: «Antall: 0
            av 2». Ingen kontoer uten rader, ingen avvik fra backfillen. Det var siste
            gang det tallet kunne tas — deploy 2 fjerner grunnlaget.

- [x] **Deploy 2 — kodet 28. aug. 2026, ikke deployet.** `role` krympet til
      `admin`/`bruker` (migrasjon `0013_krymp_role`), og all kode som leste de fire andre
      verdiene er borte.
      - [x] **JS-delen ble framskyndet (28. aug. 2026):** `window.USER_ROLE` →
            `window.MODUL_TILGANG`. Måtte fram tidlig fordi grensesnittet ellers viste
            «Ny pasient» til en bruker med bare `les`, som så møtte 403 på lagre.
      - [x] `has_role_at_least`, `role_required`, `write_required`, `stats_required` og
            `dataset_scope_all` fjernet fra `core.auth_decorators`. `ARKIV_VIEW_MIN_ROLE`
            og `ARKIV_WRITE_ROLE` fjernet fra `patients.services` — de var
            «konfigurerbare» til verdier som ikke finnes lenger.
      - [x] Rollebadgene i `user_list.html`/`user_detail.html` viser admin mot bruker.
            Rollefeltet har fått hjelpetekst: «Bruker» betyr ikke «vanlig tilgang».
      - [x] De to bulk-knappene på brukerlista er fjernet. De skrev til
            `kan_redigere_pasienter` og meldte suksess uten at noen mistet noe.
      - [x] `verifiser_modultilgang` krympet til det den fortsatt kan svare på:
            kontoer uten rader, rader på ukjent modul eller nivå, ukjente rolleverdier.
            §10.1-tellingen og sammenligningen mot `role` er fjernet, ikke deaktivert —
            begge ville svart grønt uansett database.
      - [ ] **Deploy til prod. Krever avgjørelse fra André.** Etter migrasjonen er
            `ModulTilgang` eneste fasit: en rollback av deploy 1 kan ikke lenger bygge
            matrisen på nytt fra `role`.

- [x] **Deploy 3 — kodet 28. aug. 2026, ikke deployet.** De fem `kan_redigere_*`-flaggene
      er fjernet (`accounts.0014_fjern_modulflagg`).
      - [x] **Kortet «Modul-tilganger» på `/min-profil/` skrevet om.** Det leste flaggene og
            viste «Nei» til brukere som faktisk hadde tilgang — backfillen rørte flagget med
            vilje (§8.1). Kortet leser nå `ModulTilgang`, følger modulregisteret i stedet
            for fem hardkodede etiketter, viser nivånavn i stedet for Ja/Nei, og skiller
            «modulen er slått av» fra «du har ikke tilgang».
      - [x] `test_flagget_paavirker_ingenting` fjernet: uten feltet kunne den ikke feile.
            `CustomUserPermissionFlagsTests` snudd til å kreve at feltene er borte.
      - [ ] **Deploy til prod.** Kan gå rett etter deploy 2 — de to rører ikke samme kolonne,
            og flaggene er tomme uansett.

- [x] **Sletting åpnet for `skriv: full` (28. aug. 2026)**, kun på pasienter brukeren selv opprettet
      siste 30 min. «Egen pasient» avgjøres fra `AuditLog`s CREATE-rad — indeksert på
      `(table_name, record_id)`, ingen ny kolonne. Mangler raden, nektes slettingen.
      **Merk:** DELETE-loggingen lagrer bare pasientnummeret, ikke innholdet
      (`patients/signals.py:266`). Åpnes sletting bredere senere, må den utvides først.
- [ ] **`skriv: handling` for bil-/ambulansekontoer.** Nivået er definert; bruken er
      planlagt i `docs/BESLUTNING_OPPDRAGSMODULEN.md` §5.1. Invarianten fra §3.2 er
      **skjerpet, ikke slakket**, for å tåle offline: kroppen har et lukket skjema på to
      nøkler (`klienttid`, `idempotency_key`), og alt annet gir 400. Det er testbart ved
      uttømming, i motsetning til «husk å utelate fritekst».
- [x] **`session_timeout` og `event_name` flyttet til `/portal-admin/innstillinger/`
      (28. aug. 2026).** `saveEventName` er ute av pasientmodulens JS.
- [x] **`PasientRolleForm` splittet (28. aug. 2026).** Radioen setter kun
      førstehjelper/helsepersonell-koblingen; tilgang settes i matrisen.
- [x] **Matrisen ligger på opprettingsskjemaet (28. aug. 2026).** Meldt fra staging: en
      ny konto med «Pasientregistrering» avkrysset så ingen modul på dashboardet. Boksene
      er erstattet av en matrise modul × nivå, generert fra `get_all_modules()`, på både
      opprettings- og redigeringsskjemaet.
- [x] **`notify()` sjekker modultilgang (28. aug. 2026).** Sjekken ligger i `notify()`,
      ikke hos hver kaller. En ukjent `module_slug` logges høyt, så en skrivefeil ikke gir
      samme stille utfall som manglende tilgang.
- [x] **§9-oppryddingen er gjort (28. aug. 2026):** `accounts/mixins.py` og
      `dataset_scope_all` fjernet, `docs/TEKNISK_DOKUMENTASJON.md` §6.3 skrevet om til
      tilgangsmodellen.
- [x] **Rolle- og tilgangsendringer auditeres (28. aug. 2026).** Én rad per modul som
      endres, med `table_name='accounts_modultilgang'`.
- [x] **`create_offline_users` setter modultilgang (28. aug. 2026).** `create_admin`
      trenger ingenting: global admin bruker ikke `ModulTilgang`.
- [x] **Verifiseringskommando (28. aug. 2026):** `python manage.py verifiser_modultilgang`.
      Les-only. Kjøres mot prod mellom deploy 1 og 2 — staging har egen, tom database, så
      backfillen kan ikke verifiseres mot ekte rollefordeling der.
- [x] **`/pasienter/api/stats/` slettet (28. aug. 2026).** Avgjørelsen var «gate eller
      slett»; det ble slett. Ingen kjent konsument — header-chipsene regnes ut i
      `patients-table.js` fra pasientlista, og ingen JS-fil har noen gang kalt det. Rest
      fra Flask-porten. `basic_stats()` i services står igjen: den er live-siden av
      invarianten `StatsMatcher` måler.
      - Ingen redirect satt opp. En videresending finnes for klienter som *pleide* å
        kalle noe; her fantes ingen.
      - `docs/BESLUTNING_STATISTIKK.md` forutsatte at stien fantes. Den planlagte
        `/pasienter/api/stats/live/` er upåvirket — den er et nytt endepunkt med et
        faktisk formål, ikke en videreføring av det slettede.

### Dataimport fra gammel prod — se `docs/DATAIMPORT_FRA_GAMMEL_PROD.md`

- [x] **Importert 22. aug. 2026: 273 pasienter, 12 nye førstehjelpere, 6 nye
      helsepersonell.** Alle kontroller grønne — antall, triage-fordeling, koblinger,
      `journal`, `lege` og tegnsett stemmer mot gammel prod. 273 `IMPORT`-rader i
      auditloggen. `enja` og `morten` ble gjenbrukt, ikke duplisert.
      - [x] **Manuell backup tatt 23. aug. 2026 — 270 pasienter, ikke 273.**
            Tre av de importerte var testpasienter og ble slettet før backupen.
            **Slettingen er permanent:** `DELETE /api/patients/<pk>/` er en hard-delete
            som fjerner raden og resirkulerer pasientnummeret. De tre finnes altså
            ikke i noen backup tatt etter 23. aug. Det er greit — de var duds — men
            270 er det tallet en framtidig restore skal gi. Ser du 273, er du på en
            eldre backup
      - [x] **Statistikkfanen sett over 23. aug. 2026 — viser 270.** Stemmer med
            backupen og med de tre slettede testpasientene. Tallene er dermed
            verifisert både mot kilden programmatisk og i grensesnittet

### Pasientmodulen — småting

- [x] **«Mine pasienter» markeres nå på tavla (23. aug. 2026).** Regelen var
      `.filter-btn.active-mine`, men `#btn-board-mine` har ikke `filter-btn` — så
      `toggleBoardMine()` satte en klasse ingen regel matchet.
      **Fikset ved å utvide selektoren, ikke ved å legge `filter-btn` på knappen**, som
      TODO opprinnelig foreslo: den klassen gir pille-form og 0.78rem skrift, og knappen
      står ved siden av en `btn-sm` i tavle-verktøylinja — ikke i filterraden. Å arve
      pille-stilen der ville byttet én visuell feil mot en annen.
      `AktivMineMarkeringTests` låser koblingen mellom de tre filene. Verifisert ved å
      reversere fiksen: da feiler den.
      **Etterspill:** av-tilstanden så mer påslått ut enn på-tilstanden, fordi Bootstraps
      `:hover` fyller knappen med full cyan og svart tekst og ingen hover-regel fantes.
      På touch henger `:hover` igjen etter et trykk, så den ble stående fylt. Av-tilstanden
      er nå dempet til et hint; på-tilstanden trengte ingen fiks.
- [ ] **Skal tavla og lista dele «mine»-tilstand?** `mineOnly` og `boardMineFilter` er
      to uavhengige variabler, så valget følger deg ikke mellom fanene. Merk at de gjør
      forskjellige ting: lista *filtrerer bort* andre, tavla *dimmer* dem. Det taler for
      å la dem være uavhengige. Krever en avgjørelse, ikke en fiks.
- [x] **Uleselig hjelpetekst på mørk bakgrunn rettet (23. aug. 2026).** Bootstraps
      `.form-text` er `#6c757d`, laget for lys bakgrunn, og var aldri overstyrt. Traff
      passordreglene på `/accounts/change-password/` og begge hjelpetekstene på
      `/portal-admin/backup/patients/` og `/arkiv/`. Én regel i `style.css` med samme
      verdi som `.text-muted`, så all sekundærtekst har én farge.
      **Første forsøk traff feil fil:** regelen ble lagt i `style.css`, som ingen av de
      tre sidene laster. `portal.css` er den som gjelder for alt som arver
      `base_portal.html`. Begge har regelen nå — `index.html` bruker `.form-text` selv.
      `MorkTekstPaaMorkBakgrunnTests` løser nå `{% extends %}` og `{% static %}` og
      krever overstyringen i det stilarket malen faktisk ser. Den avdekket fire
      uleselige tekster til, på `403.html`, `mfa_setup.html`, `mfa_verify.html` og
      `backup_admin_restore.html` — alle rettet.

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
        i stedet for å gjette. `VaktArkiv` skal *ikke* migreres til basemodellen:
        SHA-signaturene er låst til dagens payload-form, og hvert arkiv i prod ville
        meldt tukling. **Bygges i fase 7 av oppdragsmodulen** — den er modell nummer to.
- [ ] Park-registreringer blir **egen modell**, ikke rader i `Patient`. Holder sykestuas
      liste på ~250 rader i stedet for 1000, og matcher at dataene er enklere.
- [ ] Park-appen er et skriveendepunkt **uten innlogging**: signert lenke via
      `django.core.signing` (ikke gjettbar URL, kan tilbakekalles), rate-limit per token,
      og responsen returnerer kvittering — aldri data.
- [ ] **Oppdragsmodulen — se `docs/BESLUTNING_OPPDRAGSMODULEN.md`.** Besluttet 28. aug.
      2026, ikke bygget. Modulen er den første som tar `skriv: handling` i bruk. Sju
      faser, 35–50 t. Punktene under lå her løst fra før og er nå plassert i planen:
      - [x] **Fase 1 — modeller og regler (28. aug. 2026).** App, modulregistrering,
            fem modeller, `choices.py`, statusmaskin, utledet enhetsstatus,
            korreksjonsregel og audit med skjult fritekst. 46 tester. Modulen står med
            `url=None` og begge `show_*`-flagg av til fase 3.
            - [x] Lokasjoner vedlikeholdes med `python manage.py lokasjon` inntil
                  fase 3. Admin-siden ble utsatt fordi modulen ikke har en URL ennå —
                  en admin-side uten vei inn er samme feil som et modulkort som fører
                  til 404. Følger `appsetting`-presedensen. **Fase 1 er ferdig.**
      
      - [x] **Fase 2, kodedelen (28. aug. 2026):** fritekst er unntatt
            verdilogging fra første lagring — `oppdrag/signals.py` er ny kode, ikke en
            retrofit av `audit/`, så vinduet planen advarte mot oppsto aldri.
      - [ ] **Fase 2, resten** (~1 t): presiser
            protokollen. `AuditLog.old_value`/`new_value` er `TextField` med 730 dagers
            lagring, og feltlista utledes fra modellen (N2) — et nytt fritekstfelt havner
            der av seg selv. **Må stå før fase 3** — ellers er feltet i prod med logging
            på, og de radene kan ikke fjernes uten å røre auditsporet. Halvert fordi
            lokasjon ble nedtrekksliste: da holder A.6/A.12 for det feltet, og fritekst
            står alene igjen.
      - [x] **Fase 3 — sentralbordet (29. aug. 2026).** Enhetsliste med utledet
            status (`Ledig (2 venter)`), oppdragsliste, oppretting, flytting, tidslinje
            og lokasjonsadmin. ETag på pollingen. Modulen er synlig nå som den har en
            side. To grensesnitt bak én URL, valgt på enhetskoblingen — en test setter
            `skriv_full` på en enhetskonto og krever at den fortsatt får enhetsskjermen.
      - [x] **Enhetsadmin (29. aug. 2026).** Enheter kunne bare lages fra
            `manage.py shell` — en glipp, ikke en avgrensning. Opprettelse, aktivering og
            kontokobling ligger i sentralbordets admin-panel nå, med regelen skrevet rett
            i panelet: koblingen gir ingen tilgang.
      - [x] **Modaler i portalgrenen er mørke (29. aug. 2026).** `portal.css` hadde
            ingen modalregler, så modalen arvet sidebakgrunnen og det svarte
            lukkekrysset forsvant i den. Rettet i `portal.css`, ikke `oppdrag.css` —
            det gjelder hele grenen, og `base_portal` hadde selv et svart kryss på
            meldingsalertene. Guard i `MorkTekstPaaMorkBakgrunnTests`.
      - [x] **Sperra på enhetsadmin er testet (29. aug. 2026).** `PUT
            /oppdrag/api/enheter/<pk>/` (navn, pensjonering, kobling) krevde global
            admin hele tiden, men bare `enheter/ny/` hadde en 403-test. Da panelet ble
            åpnet for `skriv_full`, ble den luka verdt å lukke: to tester krever nå 403
            på både lesing og pensjonering for `skriv_full` uten admin.
      - [ ] **Fase 3 arver til fase 4:** enhetskontoer får i dag en mellomtilstand som
            sier at skjermen ikke er bygget. Å sende dem til sentralbordet ville vist
            dem alle oppdrag i vakta.
      - [ ] **Fase 4** (6–8 t): enhetsskjermen — statusmaskin med `Venter` som
            startstatus, to knapper mot seks navngitte endepunkter, lukket kroppsskjema,
            objektsjekk på eierskap, og de to skjulereglene (fritekst ved `Ledig`, hele
            oppdraget 30 min etter) som **server-side filter**, aldri sletting.
            Inkluderer visning av `automatisk` (§4.5): markøren sitter på klokkeslettet,
            ikke på statusordet — det er tidspunktet som er avledet. Ingen badge, ingen ny
            farge, må stå i gråtoner (WCAG 1.4.1).
      - [ ] **Fase 4b** (2–3 t): korreksjoner. 113 retter tidspunkt ved å skrive en **ny
            rad som peker på den gamle**, ikke ved å endre den — `Statusmelding` er et spor
            av hva som ble meldt. «Nyeste ikke-korrigerte rad per status vinner» bor i en
            manager-metode, ikke i en `if` per view. Kun tidspunkt, ikke status. Kun
            `skriv_full`.
      - [ ] **Fase 5** (4–6 t): offline-kø for stemplinger, med `core.idempotency`.
      - [ ] **Fase 6** (5–7 t): **statistikkregisteret** + oppdragsfanen. Her rives den
            direkte importen fra `statistikk` til `patients.services` ut, og erstattes av
            et registry etter samme idiom som `core.backup` og `core.arkiv` — det CLAUDE.md
            har varslet siden statistikkmodulen ble skilt ut. Pasientfanen skal se lik ut
            etterpå.
      - [ ] **Fase 7** (5–7 t): arkivering. **Her bygges `AbstractArkiv`** — dette er
            modell nummer to, som punktet under har ventet på. Oppdrag får **egen
            arkivknapp** under `/oppdrag/`; sammenslåingen med pasientarkivet er utsatt,
            se punktet under.

- [ ] **Flytt arkiveringen til `/portal-admin/` og grupper den.** Utsatt 28. aug. 2026 —
      se §12.1 i `docs/BESLUTNING_OPPDRAGSMODULEN.md`. `core/arkiv/` er modul-agnostisk
      for frysing, verifisering og kollaps, men **opprettelsen** (`arkiver_aktiv_vakt()` i
      `patients/services.py` — handler-kontrakten har ingen `opprett_arkiv`) og **knappen**
      ligger fortsatt i pasientmodulen. En vakt er ikke en pasientting.
      - [ ] Krever en `Vaktarkivering`-rad i `core` som grupperer modulenes arkiver. Én
            knapp som lager to urelaterte arkivrader er verre enn to knapper — da tror man
            de hører sammen.
      - [ ] Signaturene overlever: handleren bestemmer selv hva som går inn i
            `sha_payload()`, så en nullbar FK den ikke nevner endrer ingenting.
            `ArkivSignaturLaastTests` beviser det. Eksisterende arkiver får `NULL`.
      - [ ] **I mellomtiden kan noen arkivere pasienter og glemme oppdrag.** Det er en
            operativ risiko, ikke en teknisk. Legg et punkt i `docs/RUNBOOK_VAKT.md`, som
            faktisk leses ved vaktslutt — gjøres samtidig med fase 7.
- [ ] Vurder `cached_db`-sesjoner. `SESSION_SAVE_EVERY_REQUEST=True` med DB-sesjoner gir
      én UPDATE per request. Krever Redis, altså vakt-modus.

### Frontend — småting

- [x] **`.admin-only` og `.write-only` rendres server-side (28. aug. 2026).**
      `applyRoleVisibility()` er fjernet, og `er_global_admin` er en context processor.
      `ServerSideSynlighetTests` krever fravær fra HTML-en, ikke at noe er skjult.

### Framtidige moduler

Portalrammeverket er bygget for flere moduler enn `patients` — modulregistry, per-modul
backup, per-modul arkiv og permission-flagg står allerede klare. De fem opprinnelige
faseleveransene som la det på plass er beskrevet i
[`docs/archived/`](./docs/archived/README.md).

`statistikk` er modul nummer to og den første som er skrevet mot rammeverket i praksis
(28. aug. 2026). Den avdekket to ting rammeverket ikke hadde tenkt på, og som modul nummer
tre vil treffe på nytt: **stilarket** (`style.css` lastes kun av pasientmodulen, og fire av
variablene dens finnes ikke i `base_portal.html`) og **JS-primitivene**
(`patients-utils.js` kaster på en side uten pasientskjemaene). Begge er løst — `portal-utils.js`
og et stilark per modul — men de var usynlige til noen faktisk skrev modul nummer to.

De fem `kan_redigere_*`-flaggene på `CustomUser` ble pre-registrert i én migrasjon nettopp
for å slippe én migrasjon per ny modul. **De fjernes nå** — se «Rollemodellen» over;
beslutningen ble tatt 24. aug. 2026, og `ModulTilgang` erstatter dem. `statistikk` bruker
derfor ingen av dem: den gates midlertidig på `Module.min_rolle` inntil `ModulTilgang`
finnes.

- [ ] Vaktliste
- [ ] KO-tavle
- [ ] Integrasjon med produksjonsdatabase
- [ ] Lage Locus-klone, hente sted via enhetens GPS

**Uavklart før noen av dem bygges** (spørsmålene sto ubesvart i den opprinnelige
høynivå-skissen, `docs/archived/SANITETSPORTAL_PLAN.md` §7):

- [ ] Skal en «vakt» være ett enkelt arrangement, eller også dekke faste
      beredskapsperioder som ukentlig lagvakt? Avgjør feltene på modellen
- [x] ~~Skal en beredskaps-/oppdragsmodul brukes underveis i felt (mobilt, dårlig nett)
      eller i etterkant?~~ **Besvart 28. aug. 2026: underveis, og den må tåle dårlig
      dekning.** Avgrenset til enhetens stemplinger — sykestua krever nett. Se
      `docs/BESLUTNING_OPPDRAGSMODULEN.md` §6.
- [ ] Skal rapportmodulen kun være intern, eller også gi tilgang til
      styre/oppdragsgivere? Tilgangssiden er nå `ModulTilgang` (se «Rollemodellen»);
      det som gjenstår er eksportformat, og om eksterne mottakere skal ha konto i det
      hele tatt

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
      - **Soft-delete av pasientdata er beskrevet, men finnes ikke.** A.6 (linje 142)
        beskriver `is_active=False` som «logisk slettet / soft-delete», og A-delens
        rettighetstabell (linje 445) sier «Pasientdata soft-slettes; permanent sletting
        på forespørsel». **Ingen produksjonskode setter `Patient.is_active = False`.**
        `DELETE /api/patients/<pk>/` er en hard-delete: raden fjernes og
        pasientnummeret resirkuleres. Feltet leses av `?include_archived`, men kan bare
        settes via Django-admin — og den flaten er av i produksjon (S1).
        Avviket går i registrertes favør: sletting er *mer* endelig enn dokumentert,
        ikke mindre. Men dokumentet er art. 30-protokollen, og skal beskrive det som
        faktisk skjer. Funnet 23. aug. 2026 da tre testpasienter ble slettet.
        Docstringen i `views_patients.py` som påsto det samme er allerede rettet
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

- [ ] **Rate-limit arkivstatistikken.** `/pasienter/api/innstillinger/arkiv/<pk>/full-stats/`
      (`views_arkiv.arkiv_full_stats_view`) kjører samme tunge beregning som
      `/api/full-stats/` — chi², Kruskal-Wallis, krysstabeller — men fikk ingen bøtte i S3.
      Mindre eksponert: admin-only, ingen auto-refresh, og den leser arkiverte rader som
      ikke endres. Én linje når noen er i filen uansett.
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
