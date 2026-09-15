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
            og leser databasen riktig. `docs/OPPSETT_KOLLAPS_CRON.md` ble arkivert
            13. sep. 2026 (`docs/archived/`) — jobben har gått siden 22. aug.

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

- [ ] **Avklar hvem som er behandlingsansvarlig** (14. sep. 2026). A.1 legger ansvaret på
      André som privatperson, ikke på organisasjonen som gjennomfører vaktene. Det er en
      avgjørelse utenfor kodebasen, og den påvirker DPIA-vurderingen, hjemmelen i
      art. 9(2)(h) og hvem som håndterer innsynskrav og avviksmelding. Behandlingsansvar
      følger virkeligheten, ikke papiret: bestemmer foreningen formål og midler, er de
      ansvarlig uansett hva dokumentet sier. Begrunnelsen står i
      [`docs/NOTAT_DPIA_OG_FRITEKST.md`](./docs/NOTAT_DPIA_OG_FRITEKST.md) §5.
      Dokumentet flagger det selv som noe for den årlige revisjonen; vurderingen er at
      det bør opp før adresse legges inn i oppdragsmodulen

- [x] **Merget til prod 29. aug. 2026** (`eb79e9d`). Ni commits: vakt-scopingens
      deploy 2, oppdragsmodulens fase 6 og 7, backup-scheduler-fiksen og
      vaktlistenotatet. Backup av prod tatt av André før pushen — migrasjonene
      `patients.0016` og `oppdrag.0007` er enveis, og gjenoppretting fra backup er
      eneste vei tilbake.
      - [x] **`verifiser_vakt` kjørt i prod etter deployen: «Ingen funn»**
            (André, 29. aug. 2026). Deploy 2 landet rent — vakta er fasit i prod.

- [x] **Merget til prod 11. sep. 2026** (`567ee11`). 33 commits, 66 filer:
      vaktlistemodulen fase 1–6, det nye nivået `skriv_leder`, lesbare cron-feil
      og migrasjonsprøvene mot ekte PostgreSQL. **Hele `vaktliste`-appen var ny
      for prod** — elleve migrasjoner gikk ut (`vaktliste.0001`–`0010` og
      `accounts.0015`). Backup av prod tatt av André før pushen.
      Verifisert før merge: 1931 tester grønne, `verifiser_migrasjoner` OK, full
      migrasjon fra tom base mot PostgreSQL 16, og en oppgraderingssimulering der
      en base ble migrert til `main`, seedet med prod-lignende rader, og deretter
      migrert med den nye koden — elleve migrasjoner OK, alle rader intakt.
      - [x] **Kontroller deployen i Railway.** `vaktliste.0007` er migrasjonen
            som tok ned release-fasen sist (pending trigger events); den har
            mønsteret nå, og prøven i `core/migrasjonsprover.py` dekker den, men
            det er første gang den kjøres mot prod-data.
      - [x] **Åpne `/vaktliste/` i prod og sjekk at de seks ressursgruppene er
            seedet.** Migrasjon `0007` seeder dem; en tom gruppeliste er en
            vaktliste man ikke får satt opp.
      - [x] **Kontrollert av André 11. sep. 2026: «alt så bra ut».**

- [x] **Tidsblokker, slutt-tid i «Ny vaktliste» og «8,5 t» (11. sep. 2026).**
      Tre punkter etter første bruk i prod. Skift med samme fra–til samles
      under én blokklinje i ressursfanene og utskriftslista; «Ny vaktliste»
      spør om slutten; timeformatet er det samme overalt. Se CHANGELOG.
      - [x] **Ordene (samme dag):** skift = vakttid, mannskap = folk, i alle
            tellingene på siden. Belastningsfanen uendret.
      - [x] **Ingen sticky kolonne under 768 px** (samme dag). André så
            merknadskolonnen følge med på mobilen; ikke gjenskapt i Chromium,
            der bare blyantcella er sticky. Slått av for telefonen uansett.
            - [ ] **Sjekk på Andrés telefon** at ingenting følger nå. Gjør det
                  fortsatt det, er det ikke sticky som er årsaken, og da
                  trengs et skjermbilde.
      - [x] **Bygg og dato i footeren** (samme dag). `core/versjon.py`,
            byggstempel fra `nixpacks.toml` → `core/skriv_bygg.py`.
            - [x] **Første deploy med `nixpacks.toml` gikk:** footeren
                  viste «8447399 · 11.09.2026 12:34» — byggtiden i norsk
                  tid. Byggsteget kjørte.
      - [x] **Planleggingstabellen klemmes ikke på mobil** (samme dag).
      - [x] **Korpsfilteret** (samme dag): `les` og `skriv_handling` ser eget
            korps på `/vaktliste/`, nytt trinn `les_alle` ser alle. `accounts/0016`.
      - [x] **Korpsvelgeren** for den som ser alle (samme dag) — nedtrekk i
            vaktlinja, `?korps=` på planleggingstallene.
            - [ ] **Etter deploy til prod: gå gjennom matrisen.** Alle som hadde
                  `les` ser nå bare sitt eget korps — den som skal samordne må
                  få `les_alle`. Og kontoer med `les`/`skriv_handling` uten
                  mannskapsrad ser ingenting til de er koblet.
      - [x] **Prosjektleders runde 1** (samme dag): kompetanse-cella,
            kurven ned i drift, «Oppdragsliste», enhetskortet med oppdrag og
            tidsstempel, «tid siden» på oppdragslista.

- [ ] **Prosjektleders tilbakemeldinger — resten** (planlagt 11. sep. 2026,
      rekkefølgen er avtalt med André):
      - [x] **Avreist til** (11. sep. 2026): `status/avreist/<sted>/`, lagret på
            statusmeldingen, følger offline-køen. Tidslinjene sier «→ Sykehus».
      - [x] **Grovsortering Rød/Gul/Grønn** (11. sep. 2026): `Oppdrag.grovsortering`,
            satt av bilen via `grovsortering/<verdi>/`. Hastegrad venstre,
            «Bil: Rød» høyre, «Bil: —» til bilen har vurdert. `oppdrag/0009`.
            - [ ] **Skal grovsortering og sted inn i arkivet?** Payloaden er
                  signaturlåst; nye felt krever en versjonert payload (nye
                  arkiver får dem, gamle verifiserer som før). Egen beslutning.
      - [x] **Probono-skift** (11. sep. 2026): `Vaktpost.probono`, `0011`.
            Ute av timesummene, med i lengste skift og hvile.
      - [x] **Dagoverskrifter** (11. sep. 2026): `_blokkerMedDager()`, bare
            på flerdagsvakter.
      - [x] **«Mitt korps»-fane** (11. sep. 2026): `Vaktpost.alle_korps`,
            `0012`. Tre tilstander på plassen; fanen viser tildelte og
            universale, ledige først, med «N plasser å dekke».
      - [ ] **Flere enheter på ett oppdrag** — besluttet 11. sep. 2026:
            `docs/BESLUTNING_FLERE_ENHETER_PER_OPPDRAG.md`. §7 besvart, §9 kom
            til: sentralbordet fører status manuelt, også på ferdige oppdrag
            innen 48 t (forslag). Fire trinn; backup før deploy.
            - [x] Trinn 1 (11. sep. 2026): `Oppdragsenhet`, `0010`–`0011`, prøve,
                  services per koblingsrad, utledet oppdragsstatus, bilen ser
                  sin egen kjede og de andres navn. `0012` (NOT NULL) flyttet
                  til deploy 2 — nullbarheten *er* broen.
            - [x] Trinn 2 (11. sep. 2026): `enhet_ider` ved opprettelse,
                  varsle/ta av, flytt av én rad, sentralbordets føring med
                  tidspunkt (`Statusmelding.manuell`, `0012`) og gjenåpning
                  av «Ledig» innen 48 t. Bilen ser «Også varslet: …».
            - [x] Trinn 3 (11. sep. 2026): avkryssing i «Nytt oppdrag»,
                  matrisen i lista, enhetsradene i detaljen med «Før status»,
                  «Gjenåpne», «Ta av» og «Varsle enhet til», flytt av én rad.
                  Fant og rettet «Rett tid», som viste «[object Object]».
            - [x] Trinn 4 (11. sep. 2026): én arkivrad per oppdrag × enhet
                  (`0013`, unik på enhet_navn), samme signaturform;
                  statistikken teller oppdrag distinkt og varigheter per bil,
                  `summary.enhetsinnsatser`.
            - [x] **Deploy 1 til prod 12. sep. 2026** (`4c6017b`), backup tatt først.
            - [x] Hotfix samme dag: detaljvinduet frøs sida etter «Ta av»/«Varsle»
                  (én Bootstrap-modalinstans for mye; `getOrCreateInstance` overalt).
            - [x] Andrés testrapport runde 1 (12. sep.): sted/grov-knappene i bilen
                  (`data-arg`), grov fra Fremme, historikk med alle biler, «Endre
                  status» med sted bare ved Avreist, «Opprettet» først i tidslinjen,
                  arkivstatistikk på /statistikk/, KPI-boksen, «vakten».
            - [x] Andrés testrapport runde 2 (12. sep., vaktliste): egne folk på
                  andres plass, probono-merke på ledig plass, til-tid = fra + 8 t,
                  «Mitt korps» med timer, «Korps»-etiketten, arkivering av vaktliste
                  (`0013`), admin-kobling bare av admin.
            - [x] Planlagt/utildelt (12. sep.): utildelt = alle ser, planlagt = lederens
                  kladd, én vei. Bare navn og regel — ingen skjemaendring.
            - [x] Andrés rapport 2, oppdrag (12. sep.): framtidsslakk, ta av → historikk,
                  varslet/tatt av i tidslinjen (`0014`), angre siste status, sletting
                  (sentral mens alle venter, admin i historikken), rediger oppdrag,
                  sted i sentralbordet, «Endre», «endret av KO», notat i arkivlista.
            - [x] Andrés rapport 2, vaktliste og statistikk (12. sep.): nedtrekkene
                  tilbyr bare dem brukeren får sette, «Mitt korps» med bemannet/å
                  dekke/probono, kurven lister ledige skift, «Dupliser som ledig
                  plass», «Slett vaktlisten» for admin, arkiverte bak én knapp,
                  registeret hentes ved sidelasting, lesbar tidstekst på /statistikk/.
            - [x] Navnet «utildelt» ble «Åpen for alle» (12. sep.). «Ledig korps»
                  ble forkastet: «ledig» er alt plassen uten person.
            - [x] Hjem-skjerm-ikonet (12. sep.): full flate på PNG-ene, kortnavn
                  «Sanitetsportalen», `scripts/lag_ikoner.py` + piksel-test.
            - [x] Andrés rapport 4 (12. sep.): arkivering lukker vakta (tømmer tavla,
                  nummer fra #1), bilen ser de andres stempler også i Venter, kurven
                  faller tilbake på skiftene, «personell på det meste», ny logo.
            - [x] Andrés rapport 3 (12. sep.): bilen ser de andres stempler, arkivtittel
                  uten vaktnavn, «Mitt korps» skiller korpsets fra åpent for alle, kurvens
                  hode med tre tall, «Arkiv» i eget vindu, manifest og logo.
            - [ ] **Andrés forbedringsliste 12. sep. (staging først):**
                  - [x] G: «Sett i drift» i Innstillinger, tydelig statusmerke, redigering i
                        drift, drift i auditloggen, knappefarger, én innlogging per konto
                        (fantes; nå testet).
                  - [x] H: «Behandlet på sted» fra Fremme (→ Ledig), «Avbryt» i Rykker ut
                        (enheten ledig, oppdraget trenger ressurs), ingen Ledig mellom
                        Avreist og Leverer (`0022`). Sentralen redigerer som før.
                  - [x] Prodtest G–I (12. sep.): dempeikon med lyd på som standard, admin
                        kan slå lyden av, iOS-omvei for stillebryteren, grovsortering
                        kreves før Behandlet/Ledig etter Leverer (+ valgfritt før Avreist),
                        «Behandlet på stedet» i statistikken, gruppeoverskrifter på iPhone.
                  - [x] ISSI (12. sep.): `Mannskap.issi` (`vaktliste/0015`), etter
                        telefon og e-post; besetningen i `/oppdrag/` viser telefon
                        og ISSI per person.
                  - [x] Statistikk (12. sep.): chi²-merket bryter på iPhone.
                  - [x] Audit i vaktlista (12. sep.): skift, ressurser og stemplene
                        logges på feltnivå; `merknad` uten verdier.
                  - [x] Prodtest G–I, del 3 (12. sep.): alt OK. Pasientstatistikkens
                        tabeller ruller på iPhone (`stats-rull`), vaktlinja bryter i tre
                        linjer under 992 px.
                  - [x] Prodtest G–I, del 2 (12. sep.): lydvarsel av/på per hastegrad
                        (`0025`), «Behandlet på sted» sender Ledig i samme trykk, Drift
                        uten grovsortering i bil og hos operatør, rullbare
                        statistikktabeller på iPhone.
                  - [x] I: lyd alltid på (ingen av/på), lengre varsel, admin justerer terskler
                        per hastegrad og lyd ved nytt oppdrag (`0023`–`0024`), utheving hos
                        operatør.
            - [x] Railway-variabler (André, 12. sep.): `testportal.sanitet.net` inn i
                  staging sine `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`, og skrivefeilen
                  `/ https://*.railway.app` rettet begge steder.
            - [x] Feilvarsel (12. sep.): `django`-loggeren bruker vår dempede, slanke
                  e-posthandler; `DisallowedHost` går bare til konsollen.
            - [x] **Deploy til prod 12. sep. 2026** (`39ece18`, fra `49406fd`), backup tatt
                  først. Migrasjoner: `vaktliste/0014`, `oppdrag/0015`–`0021`.
            - [x] Prodtest c8ab831 (12. sep.): alt OK. «Verdier» ble «Valglister», og
                  fanene i vinduet fikk mørke flater.
            - [x] Andrés runde på staging, del F (12. sep.): lydvarsel i bilen for
                  ventende oppdrag — Akutt 1 min/10 s, Haster 5 min/60 s, Vanlig og
                  Drift 15 min/60 s, «Lyd»-knapp som vekker lyden og husker valget,
                  gul puls på raden.
            - [x] Andrés runde på staging, del E (12. sep.): problemstillinger og
                  enhetstyper som tabeller med rekkefølge (`0019`–`0021`), «Verdier»-vinduet
                  med tre faner, `skriv_leder` i oppdragsmodulen, enheter alfabetisk i
                  gruppa, antall pasienter satt av bilen.
            - [x] Andrés runde på staging, del D (12. sep.): fanikon og «vis passord»
                  synlige på innloggingssiden, avkryssingen i «Nytt oppdrag» overlever
                  pollingen, nedtrekkene starter øverst, lista sortert på hastegrad og
                  nummer, «trenger ny ressurs» trappes opp med tida og skjuler bilen
                  som dro (`0018`), nummer i «nylig avsluttet», «Udefinert»-meldingen
                  når fram til bilen, adminkontoer er aldri mannskap.
            - [x] Andrés runde på staging, del C (12. sep.): bilen rykker videre →
                  oppdraget står som «trenger ny ressurs» på tavla (`0016`).
            - [x] Andrés runde på staging, del B (12. sep.): hastegraden Drift med egne
                  problemstillinger, rekkefølge i skjemaet, «Udefinert» som sperrer
                  ledig, antall på transport, enhetstyper med gruppering, lokasjoner
                  for skriv_full og sletting for admin (`0015`).
            - [x] Andrés runde på staging, del A (12. sep.): besetning følger lista i
                  drift og viser neste skift, `Mannskap.epost` med automatisk
                  kontokobling, konto for hånd bare admin, skriv_handling ser alle
                  korps, probono i kurven.
            - [ ] **Å tenke på (André, 12. sep.):** bilen ser nå de andres stempler
                  (avgjort 12. sep.). Sentralbordets besetning følger lista i drift
                  (avgjort 12. sep.). Skal bil 2, som ikke tar med
                  pasienten, få sette/se grovsorteringen? Adminkontoer er aldri
                  mannskap (avgjort 12. sep.: «Den er utenfor.»).
            - [ ] Deploy 2, senere: fjern `Oppdrag.enhet`, `Statusmelding.oppdragsenhet`
                  NOT NULL (med `SET CONSTRAINTS ALL IMMEDIATE` om et dataskritt går
                  foran), og broene i `Oppdrag.save()`/`Statusmelding.save()` bort.
                  Backup før — og la prod gå noen vakter med broene først.
      - [x] **Utskrift per korps eller ressurs** (12. sep. 2026): velger over
            «Oversikt», arkhodet sier utvalget. Fant og rettet at korpsvelgeren
            aldri var koblet til `change` — delegeringen ligger nå i
            `portal-utils.js` ved siden av klikk.
      - [ ] **Stripe på blokklinja** (mini-Gantt over vaktas spenn) — alternativ
            «Begge deler» i spørsmålet 11. sep.; valgt bort for nå, lett å
            legge til siden blokka alt bærer spennet.

- [ ] **Første skarpe vakt med oppdragsmodulen.** Modulen er ferdig og testet, men
      aldri brukt under en reell vakt — og det er den prøven som finner det ingen
      testsuite gjør: samband, dekning i felt, og om knappene sitter der hendene
      forventer dem. Ha `docs/RUNBOOK_VAKT.md` framme; §10a har nå **to**
      arkivknapper å krysse av ved vaktslutt.

## Pågående / neste

*De tre vaktlisteønskene under henger sammen — to av dem trenger samme dagruppering.
Sammenhengen, rekkefølgen og de åpne valgene står i
[`docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md`](./docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md).*

### Vaktlista: minimerbare ressurser i gruppefanene — ønsket 14. sep. 2026

**André:** «i hver ressursfane skal en kunne minimere lag/ambulanse osv. Og at det også der
siles på samme måte som oversikt. Og at alle ressursene i ressursgruppen er minimert som
standard.»

Tre ting, og de henger sammen: en fane med ti ambulanser er i dag ti regneark under
hverandre, og man scroller forbi ni for å komme til den tiende.

- [x] **Dagen ytterst i gruppefanen også** (André, 15. sep. 2026, etter staging: «i
      ressursgruppene må det være likt som oversikt — ressurser per dag»). De to
      planleggingsflatene leses nå likt. Ressurser uten skift får bolken «Uten skift», så
      «Opprett vakt» fortsatt finnes et sted.
- [x] **Minimerbart kort per ressurs.** `mkRessurs()` bygger kortet; overskriften har alt
      navn, korpsmerke, enhetsmerke og redigeringsknapp. Sammenslått viser den de samme
      merkene pluss en telling — antall skift, antall bemannede, ledige — så man ser hva
      som er der uten å åpne.
- [x] **Minimert som standard — men bare når gruppa har mer enn én** (avklart
      15. sep. 2026). Opprinnelig ordlyd og begrunnelse: Gruppefanen har bemanningskurven øverst
      (`mkGruppekurve`), og den *er* oversikten over gruppa. Kortene under er detaljen.
      Med alt sammenslått blir fanen «kurve + hvilke biler finnes», som er den riktige
      første visningen.
- [x] **Dagruppering i planleggingstabellen.** ⚠️ **Punktet var feil da det ble skrevet:**
      `mkRessurs()` har kalt `_blokkerMedDager()` hele tiden, og
      `test_planleggingstabellen_har_dagrader_der_oversikten_har_titler` håndhever det —
      planleggingstabellen *hadde* dagoverskrifter. Det som faktisk manglet var at de bare
      sto på flerdagsvakter. Rettet 15. sep. 2026: overskriften vises nå alltid.

#### Tre ting som må avklares

- [x] **Hvor lever sammenslått/utvidet?** `ressursApen` (Map) i `vaktliste-kjerne.js`,
      ikke `localStorage` — begrunnelsene står i CHANGELOG 15. sep. 2026. Vurderingen var: `tegnFaner()` og `mkRessurs()` bygger markupen på
      nytt ved hvert panelbytte — det er samme grunn til at `gateKnapper()` ikke kan gate
      dem (`CLAUDE.md`). Tilstanden må derfor ligge utenfor markupen: et sett på
      modulnivå, eller `localStorage` hvis den skal overleve en sidelasting.
      Presedensen finnes i `erDempet` i `oppdrag-enhet.js`, som husker per enhet.
- [x] **Alltid minimert, eller bare når det er mer enn én?** Avklart 15. sep. 2026:
      bare når gruppa har mer enn én. Vurderingen var: En vakt med **én** ambulanse
      gir et klikk hver gang for å se det eneste som er der. `_blokkerMedDager()` har
      presedensen for det motsatte valget: dagoverskrifter vises «bare når vakten faktisk
      har mer enn én dag — en endagsvakt ser ut som før». Samme resonnement kunne gjelde
      her. **Andrés ordlyd er «alle … minimert som standard», så dette er et spørsmål, ikke
      en innvending.**
- [x] **Åpnes kortet automatisk når man må inn i det?** Løst ved design: knappene blir
      stående i hodet på et sammenslått kort, så «Rediger» og «Roller» virker uten å åpne
      det først. `apneVaktpost()` åpner kortet — ellers lagrer man et skift og ser
      ingenting skje.

*Utskrift er ikke berørt: `vl-utskrift` og `@media print` hører til Oversikt, ikke til
gruppefanene.*

### Vaktlista: snu «Oversikt» til dag først, ressurs etterpå — ønsket 14. sep. 2026

**André:** «oversikten [skal] bare vise hvem som er på vakt og hvilken ressurs de er på på
dag … ikke silt etter ressurs først og så dag, men faktisk silt etter dag så ressurs».

**Dagen finnes allerede som begrep**, den er bare på feil nivå. `_blokkerMedDager()` i
`static/js/vaktliste-tegning.js` setter en dagoverskrift *inne i* hver ressurs, og bare
når vakta har mer enn én dag. Nøkkelen er `_dagnokkel(blokk.fra_tid)` — altså **skiftets
starttidspunkt**.

Dagens struktur:

```
Ambulanse A          ← ressurs
  fredag             ← dag
    fre 20:00–04:00  ← tidsblokk
      Kari, Per      ← mannskap
Ambulanse B
  fredag
    ...
```

Ønsket struktur:

```
fredag               ← dag
  Ambulanse A        ← ressurs
    Kari, Per
  Ambulanse B
    ...
lørdag
  ...
```

**Hvorfor det er riktig:** lesemodellen endrer seg. I dag svarer lista på «hvem står på
denne bilen, og når» — det var begrunnelsen som sto i `CLAUDE.md`: «den som leser den står
ved bilen». Snudd svarer den på **«hvem er på vakt i dag, og hvor»**, som er spørsmålet den
som møter om morgenen faktisk stiller.

#### Ett spørsmål som må avgjøres

- [x] **Hvor havner et skift som krysser midnatt?** Avklart 15. sep. 2026: **bare
      startdagen**, som `_dagnokkel()` alltid har gjort. Vurderingen var: I dag filer `_dagnokkel(fra_tid)` det
      under **startdagen** — «fre. 20:00 – lør. 04:00» står bare under fredag. Med dagen
      som ytterste nivå blir det et reelt valg:
      - **Bare startdagen:** Den som ser på lørdag morgen ser ikke Kari, selv om hun *er*
        på vakt da. Lista svarer da ikke på spørsmålet den er snudd for å svare på.
      - **Begge dager:** Kari står under både fredag og lørdag. Riktigere for «hvem er på
        vakt nå», men samme person telles to ganger hvis noen summerer radene.

      Merk spenningen mot rapportmodulen: for **timer** er det avklart at skift splittes
      ved midnatt (`FORSLAG_RAPPORTMODUL.md` §2.2). For **oversikten** er splitting ikke
      like opplagt — der er spørsmålet hvem som er til stede, ikke hvor mange timer som
      skal faktureres. De to kan lande ulikt, men da skal det være bevisst.

- [x] **Beholdes summene per ressurs?** Ja — de er nå per dag per ressurs, og totalen for
      hele vakta står fortsatt i arkhodet.

- [x] **Ressursfilteret er byttet ut med et dagfilter** (André, 15. sep. 2026, etter
      staging): «vi beholder hele vakten, men fjerner ressursene og bytter med dag». En
      endagsvakt får ingen velger. Punktet under er derfor foreldet:
- [x] ~~**Ressursfilteret** (`utskriftRessurs`) beholdt;~~ det silter på ressurs og
      er uavhengig av nivårekkefølgen.

*`@media print`-reglene i `vaktliste.css` må gås gjennom med den nye strukturen — en
dagoverskrift som havner nederst på et ark uten radene under seg er en utskrift ingen kan
bruke.*

### Vaktlista: fjern «Sett i drift», la drift følge vakta — ønsket 14. sep. 2026

**André:** «fjern i drift-knappen og heller ha det slik at når vaktlisten starter så er den
automatisk i drift».

**Problemet den løser er ekte:** glemmer noen å trykke, kan ingen stemple møtt ved
vaktstart — altså nøyaktig når det betyr noe, og nøyaktig når alle har mest å gjøre.
Innsjekken er stengt fordi noen glemte en knapp, ikke fordi noen bestemte det.

**Men knappen gjør fire ting, ikke én** (`vaktliste/views.drift_view`), og alle fire må
ha et nytt hjem:

| I dag | Hva som skjer hvis drift utledes |
|---|---|
| `status = DRIFT` | Utledes av om «nå» er innenfor vaktas spenn — se under |
| `satt_i_drift_at` | Blir vaktas starttidspunkt. Uproblematisk |
| **`satt_i_drift_av`** | **Mister mening.** I dag kan man svare på «hvem åpnet innsjekken». Ingen åpner den lenger |
| **Sender vaktlista på e-post** (`fil.sendes_ved_drift()`) | **Utløseren forsvinner.** Må flyttes til en klokke |

#### Designspørsmålet: utledet eller klokkesatt?

- [ ] **Utledet er mest i portalens ånd.** Presedensen er `Vaktpost.er_tilstede`:
      «utledes, aldri lagres — to kilder til samme sannhet går i utakt første gang noe
      feiler halvveis». `i_drift` kunne på samme vis regnes av `Vakt.startet` og
      `Vaktliste.planlagt_slutt`. Ingen ny klokke, ingen ny tilstand.
- [ ] **Klokkesatt** ville beholdt `status` som felt, satt av
      `vaktliste.middleware.FilutsendingMiddleware` eller en søster til den — trafikken
      som tidtaker, som backupklokka. Beholder auditsporet og e-postutløseren, men
      innfører en tredje klokke.

#### Kantene som må avklares før noe bygges

- [ ] **Hva med den som møter tidlig?** Utledes drift strengt av klokka, kan ingen stemple
      møtt 30 minutter før vaktstart. Det skjer ofte.
- [ ] **Og den som glemte å stemple av?** Stenger innsjekken automatisk ved
      `planlagt_slutt`, mister man muligheten til å rette etterpå.
- [ ] **Overstyring bør trolig beholdes**, selv om knappen fjernes fra normalflyten: en
      vakt som starter sent, eller en liste som må åpnes for en rettelse. Da er
      spørsmålet om det blir «automatisk med unntak» framfor «manuelt».
- [ ] **E-postutsendingen ved drift** må flyttes, ellers slutter reserven å bli sendt.
      `fil.send_planlagte()` og `FilutsendingMiddleware` finnes alt og er riktig sted.
- [ ] **Auditsporet.** Drift inn og ut logges på feltnivå i dag (`vaktliste/signals.py`).
      Utledes tilstanden, er det ingenting å logge — og det er riktig, for da har ingen
      gjort noe. Men det skal være et bevisst fravalg, ikke et tap man oppdager senere.

*Verdt å merke: dagens design er begrunnet i notatet — «drift er en innsjekk-port, ikke en
livssyklus … lista kan fortsatt endres, for folk uteblir og bytter». Endringen rører ikke
den begrunnelsen; den rører bare hvem som åpner døra.*

### Vaktlista: nedtrekket i «Rediger skift» — bevisst ufiltrert (14. sep. 2026)

*Ingen oppgave, men et notat så ingen «retter» det uten å lese begrunnelsen.*

Radens nedtrekk filtrerer nå bort dem som alt står på ressursen til samme starttid
(`opptattPaaPlassen()`, se CHANGELOG). Vinduet «Rediger skift» gjør det **ikke**, fordi
det kan endre `fra_tid` i samme lagring: et filter regnet ut da vinduet ble åpnet gjelder
den gamle tiden, og ville skjult et lovlig valg. Veggen er skiltet der i stedet —
`lagreVaktpost()` viser avslaget inne i vinduet.

- [ ] **Skal det filtreres når tiden ikke er endret?** Krever at nedtrekket tegnes på nytt
      når `vaktpost-fra` endres. Billig, men det er en ny kobling mellom to felter i samme
      skjema, og den må testes for seg. Ikke gjort — ført som spørsmål.

### Planleggerfane i vaktlista — se [`docs/FORSLAG_PLANLEGGERFANE.md`](./docs/FORSLAG_PLANLEGGERFANE.md)

**André, 15. sep. 2026:** «En planlegger-fane i /vaktlisten … generere skift og sette de opp
på enheter/ressurser. En kan sette inn total timer og da jobbe overordnet med hvor mange en
kan ha på vakt.»

**Alle åtte spørsmålene er avklart** i gjennomgangen 15. sep. 2026 (notatets §6). Kort:
timetallet er et **tak som varsler**; **ett tak for hele vakta**, med en dagslinje uten egne
tak; timer føres på **startdagen**, ikke splittet ved midnatt (det er rapportmodulens regel,
og forskjellen er bevisst); generatoren lager **bare tomme plasser**; ny generering
**erstatter tomme plasser, men beholder de korpsreserverte og alle bemannede**;
budsjettlinja viser **satt opp og bemannet side om side**; taket **kopieres** av
`kopier_oppsett`; og **overlapp-punktet løses først**.

Rekkefølgen under er notatets §7. Ingenting er bygget.

- [ ] **Løs overlapp-punktet under først.** Et tak som telles feil er verre enn ikke noe
      tak: overlappende skift blåser opp timesummen, og budsjettet brukes da opp av timer
      ingen jobber.
- [ ] **Budsjettlinja og dagslinja.** «Tak: 400 t · Satt opp: 312 t · Bemannet: 244 t ·
      Igjen: 88 t», og under den «fre. 128 t · lør. 152 t · søn. 32 t». Begge leser bare
      det som finnes (`_sumTimer()`, `_grupperPaaDag()`), og gir verdi uten generatoren.
      Avstanden mellom «satt opp» og «bemannet» er selve arbeidslista.
- [ ] **Taket som felt på `Vaktliste`**, satt med `skriv_full`, og kopiert av
      `kopier_oppsett` til neste vakt. Det gjelder *denne* vakta — `Belastningsgrenser` er
      organisasjonens og gjelder alle.
- [ ] **Bildet av vakta:** bemanningskurvene per gruppe ved siden av hverandre over
      `_vaktensSpenn()`, så hull og topper er synlige mens man legger inn.
- [ ] **Generatoren til slutt**, i sin enkleste form: N **tomme** plasser, fra–til, rolle.
      Ved ny generering erstattes tomme plasser uten reservasjon; tomme plasser reservert
      til et korps og **alle** bemannede beholdes — reservasjonen leses av
      `services.reservert_korps()`, ikke av feltet. **Ingen `bulk_create`** — den hopper
      over auditsignalene; `kopier_oppsett` gikk i den fella.
- [ ] **Skriv midnattsregelen inn i `docs/FORSLAG_RAPPORTMODUL.md` §2.2 også.** Den står i
      `CLAUDE.md` for `_dagnokkel()` og i planleggernotatets §3.3; rapportmodulen er det
      tredje stedet noen leser den, og den som leser bare der må se at forskjellen er
      bevisst.

### Vaktlista: overlappende skift — funnet 14. sep. 2026

*Funnet mens vi diskuterte rapportmodulen, men punktene hører hjemme i vaktlista og er
uavhengige av om rapporten noen gang bygges.*

- [ ] **`overlapp`-tellingen finnes ikke, men docstringen lover den.**
      `vaktliste/services._hviletider()` sier «Overlappet i seg selv fanges av
      `overlapp`-tellingen». Det er ingen `overlapp`-nøkkel i belastningsraden. Det som
      faktisk skjer er at `korteste_hvile` blir `0.0` og raden flagges som **kort hvile** —
      altså vises et overlapp som et hvileproblem, og planleggeren får ikke vite hva det
      egentlig er. Enten skriv tellingen, eller rett docstringen; den kan ikke bli stående
      som den er.
- [ ] **Legg `overlapp` i `belastning_per_person()`.** Antall overlappende timer per
      person, ved siden av `korteste_hvile`. Billig, og det er den opplysningen
      vaktlederen trenger for å rette før lista låses.
- [ ] **Vurder en sperre, men ikke i databasen.** `test_overlapp_paa_tvers_av_ressurser_stoppes_ikke`
      dokumenterer at dette er bevisst: «noen ganger står man på to lister». Å sperre det
      i basen krever `ExclusionConstraint`, som **ikke finnes i SQLite** — da er suiten
      grønn lokalt mens prod oppfører seg annerledes, nøyaktig fella fra 30. aug. 2026.
      Riktig sted å nekte er ved **frysing** av en liste som skal bli fakturagrunnlag, ikke
      ved planlegging der overlappet bare er informasjon.

**Hvorfor dette betyr noe utover planleggingen:** et overlapp blåser opp timesummen.
Målt 14. sep. 2026 — skift 12:00–20:00 (8 t) og 16:00–22:00 (6 t) på samme person gir
`timer = 14.0`, mens personen var til stede i 10 timer. I dag er det harmløst, fordi
ingen betaler etter tallet. Se `docs/FORSLAG_RAPPORTMODUL.md`.

- [ ] **Timer har ingen dagdimensjon.** `_timer()` er ren varighet; fredag 20:00 → lørdag
      04:00 gir 8,0 timer uten at koden har noe begrep om hvilken dag de tilhører.
      Spørsmålet er ubesvart i koden fordi ingenting har stilt det. Bemanningskurven har
      presedensen — den bøtter per time og markerer midnatt (`vl-dogn`) — så regelen
      «fredag 23:59 er fredag, lørdag 00:00 er lørdag» (André, 14. sep. 2026) betyr at et
      skift **splittes ved midnatt**. Trengs først hvis noe skal vise timer *per dag*.

### Funn fra staging-verifiseringen 14. sep. 2026

- [x] **CSP blokkerte den stille lydbæreren.** `media-src 'self' blob:` lagt til i
      `core/middleware.py`. Meldte seg som en konsolladvarsel på en side som ellers
      virket — men på iOS betyr den at bilen ikke piper med ringebryteren på lydløs,
      altså akkurat det `_stilleLydbaerer()` finnes for. Se CHANGELOG.
- [x] **Modalene holdt på fokus når de ble skjult.** `slippFokusFoerSkjul()` i
      `portal-utils.js`, én lytter på `hide.bs.modal` for hele portalen.
- [x] **Testkommandoen i CLAUDE.md utelot `myproject`** — 32 tester på
      databasevalg, cache, `_env_bool`, statiske filer og migrasjoner ble aldri
      kjørt av den som fulgte dokumentasjonen. Rettet.
- [x] **`myproject/tests_cache_config.py`: opprydningen sto inne i `with`-blokken**,
      så settings-modulen ble lastet tilbake med `REDIS_URL` fortsatt satt.
      Nå `addCleanup`.
- [x] **Gjerde rundt testkommandoen** (`core/tests_testkommandoen.py`). Hver
      toppnivåpakke med `test*.py` må stå i kommandoen i CLAUDE.md, og kommandoen
      må ikke navngi noe som ikke finnes. Den utelot `myproject` i lang tid, og
      feilen ble funnet fordi et testtall ikke stemte — flaks, ikke mekanisme.
- [x] **`SignalerFyrerIkkeUnderLoaddataTests` finner appene selv.** Den scannet
      tre apper skrevet for hånd og ville ikke sett `core/signals.py`. Globber nå
      `*/signals.py`, med `VAKTEN_UNNTATT` for det ene bevisste unntaket.
- [x] **Service workeren bumpet til `vl-sw-5`** foran prod-deployen, så den
      gamle udelte `vaktliste.js` ryddes fra skallcachen. Utkastingen fikk
      samtidig sin første test (`skalKastes()`).
#### Åpne punkter

*Gjennomgått 14. sep. 2026 på Andrés spørsmål om hva vi tjener på å løse dem. De to
første er **bevisst latt stå** — begrunnelsene i `docs/TEKNISK_DOKUMENTASJON.md` kap. 15.7
og 15.6. Det tredje er delvis løst.*

- [ ] **`accounts` → `oppdrag.Enhet`.** Vurdert og utsatt: kroken må bidra med et felt i
      opprettelsesskjemaet *og* kroke seg på både oppretting og sletting, og
      brukeropprettelsen er den mest sikkerhetsfølsomme flyten i portalen. Men det
      avgjørende argumentet er et annet: **du kan ikke tegne et godt grensesnitt fra ett
      eksempel.** Ta den den dagen en modul nummer to trenger en kontotype — da er det to
      tilfeller å abstrahere fra, og jobben gjøres én gang riktig.
- [ ] **`style-src 'unsafe-inline'`.** 271 inline stiler (176 i maler, 95 i JS-bygget
      markup). **Nonce hjelper ikke** — et CSP-nonce dekker `<style>`-elementer, men ikke
      `style=`-attributter; det er derfor CSP 3 måtte innføre `style-src-attr`.
      Restrisikoen er lavere enn den ser ut: CSS-eksfiltrasjon går gjennom
      `background-image`, fonter eller `@import`, og **alle tre er allerede låst til
      `'self'`** av `img-src`, `font-src` og `style-src`. Det som står igjen er
      defacement. Ryddes gradvis: fjern inline-stilene i en mal når den likevel skrives om.
- [x] **Tallgjerdet i dokumentasjonen** *(levert 14. sep. 2026)* — `core/tallfasit.py` og
      `TallpaastanderTests`. Fanget en feil i kap. 5 før det var ferdig skrevet.
      At gjerdet ikke kan lese *mening* består, og er dokumentert i kap. 15.8 med en
      tabell over hvor lite det ville fanget av dokumentrunden.

*Samlet her med vilje: begge lå opprinnelig som uavkryssede barn under avkryssede
foreldre, og et punkt som står under noe ferdig er et punkt ingen leser igjen.*

- [ ] **Kontoopprettelsen lager en `oppdrag.Enhet`.** Funnet 14. sep. 2026, ikke i
      gjeldskartet. Kontotypen «bil» validerer enhetsnavnet i `accounts/forms.py` og
      oppretter/gjenoppliver raden i `accounts/views.py`. Samme slags kobling som 3.1,
      men en annen form: det er *selve opprettelsen* som får en sideeffekt i en modul,
      ikke et skjema ved siden av. Hører hjemme i `core/kontokobling.py` med en
      lagringskrok — men det er kirurgi i brukeropprettelsen, og den skal ikke gjøres
      i forbifarten. Står i `KJENTE_UNNTAK_RAMMEVERK`, som ikke skal vokse.
- [x] **Uforklart enkeltfeil i suiten — LØST 14. sep. 2026.** Den het
      `core.tests_ratelimit.RateLimitEndepunktTests.test_opprett_pasient_strupes`, og
      fanget seg selv da en full PostgreSQL-kjøring ble tatt vare på med `tee` i stedet
      for grep-et bort. Årsak: vinduskanten i `django_ratelimit`, samme som den jeg
      rettet tidligere samme dag — 65 forsøk mot `60/m` deles i to bøtter der ingen når
      60. **Den var brutt tre steder**, ikke ett; regelen er nå funksjonen
      `nok_til_a_bryte(grense)`. Bekreftet med 30 kjøringer på PostgreSQL uten feil.
- [x] **Portalinnstillingene og modulbryteren auditlogges ikke.** *Levert 14. sep. 2026* — `core/signals.py`. Funnet mens
      André spurte om «logges ingenting fra core?». Svaret er nesten nei, og det
      er ikke nytt av flyttingen — det har vært slik hele tiden:

      | Hva | Logges? |
      |---|---|
      | `core.AppSetting` — sesjonstimeout, e-postmottakere, lydbrytere, `oppdrag_krev_grov_avreist` | **Nei** |
      | `core.ModuleSettings` — modul av/på for alle | **Nei** |
      | `core.Vakt` — navn, start, avsluttet | **Nei** |
      | `core.Backupplan` | Ja (`core_backupplan`) |
      | Backup tatt / gjenopprettet | Ja (`backup`, `<slug>_backup_restore`) |

      Ingen app utenom `audit` har signal på en `core`-modell — det finnes ingen
      `core/signals.py`. Å slå av en modul for alle, flytte sesjonstimeouten eller
      endre hvem som får vaktlista på e-post etterlater altså ingen spor.
      Mekanismen finnes ferdig (`vaktliste/signals.py` er mønsteret, med
      `@ikke_under_loaddata`); dette er å ta den i bruk, ikke å bygge noe.

      Merk samtidig at `EKSPLISITT_MAPPING`-radene for `patients_appsetting` og
      `patients_backup` er **inerte i dag**: ingen kode skriver de tabellnavnene.
      De er satt på forhånd, som `GAMLE_MODELLNAVN`, og blir først virksomme når
      punktet over gjøres. Det er verdt å vite før man leter etter radene i loggen.


### Teknisk gjeld — kartlagt 13. sep. 2026

Underlaget er `docs/TEKNISK_GJELD.md`; det forklarer hvorfor. Rekkefølgen her er
bindende: 1 før 2, fordi backupen speiler hvor modellene bor.

> **Rekkefølgen foreslått justert 13. sep. 2026** — se
> `docs/PLAN_REKKEFOLGE_2026-09.md`: det av punkt 2 som *ikke* rører `AppSetting`
> (`vaktliste`-handler, `core.Vakt` i egen portalfil, gjenopprettingstesten i tom base,
> 3.4 og omdøpingen) tas **før** flyttingen, så prod har en gjenopprettbar backup foran
> tilstandsmigrasjonen. Hel backup og `AppSetting` i portalfila tas etter. Datteroppdrag
> og statistikk-utvidelsen står etter dokumentrunden og etter første skarpe vakt med
> oppdragsmodulen.

- [x] **1. Flytt det portalvide ut av `patients` og inn i `core`** (§2 i notatet). *Levert 14. sep. 2026 — alle fire faser.*
      **Planen er skrevet ut i
      [`docs/PLAN_FLYTTING_TIL_CORE.md`](./docs/PLAN_FLYTTING_TIL_CORE.md)**
      (14. sep. 2026, fire faser). **Alt avklart** (notatets §7): audit-loggens
      `app_label` mappes til `core` for de flyttede tabellene, faserekkefølgen står, og
      deploy-takten er som i backupomleggingen. `accounts/decorators.py` (3.3) tas med i
      fase 4.
      - [x] **Fase 1 — navnetabellen** (14. sep. 2026). `oversett_modellnavn()` og
            `GAMLE_MODELLNAVN` i `core/backup/service.py`, tom i dag. En backupfil bærer
            modellnavnet, så en fil tatt før en flytting lastes ikke etterpå — og
            modulfilene ligger 730 dager offsite. Røret settes på plass før fase 2 fyller
            det, så oversettelsen er prøvd i prod før den trengs. Testene kjører den mot
            en oppdiktet flytting, med motprøve.
      - [x] **Fase 2 — `AppSetting` og `Backup` til `core`** (14. sep. 2026,
            `core/0011` + `patients/0018`). `SeparateDatabaseAndState` med tom
            `database_operations` — ingen SQL. `db_table` beholdt; en omdøping ville gitt
            500 i vinduet mellom `migrate` og containerbyttet, fordi `AppSetting` bærer
            pekeren til aktiv vakt. Navnetabellen fikk sine to rader, og
            `EKSPLISITT_MAPPING` i `audit/signals.py` fikk tabellene sine.
            - [x] **Flyttet fram fra fase 4:** `core.AppSetting` inn i portalfila.
                  Pasienthandleren dumper `apps = ['patients']` og fikk modellen med på
                  kjøpet; portalfila lister sine ved navn. Ventet vi, ville
                  portalinnstillingene ligget utenfor **alle** backupfiler mellom de to
                  deployene, uten at noe sa fra.
            - [x] **Prøvd mot ekte PostgreSQL:** oppgraderingssimulering fra prod-koden
                  (alle rader intakt, ingen tom tabell ved siden av), og en fil tatt med
                  prod-koden gjenopprettet med den nye (navnetabellen oversatte 2 rader).
            2647 tester grønne på SQLite og PostgreSQL, 3 migrasjonsprøver OK.
      - [x] **Fase 3 — `hent_aktiv_vakt`, middleware, `healthz`, server-status**
            (14. sep. 2026). Ingen migrasjon. `core/vakt.py`, `core/middleware.py`,
            `core/health.py`, `core/admin_status.py`. `core` importerer nå en modul på
            fem steder i produksjonskode mot rundt tjue før runden, og fire av dem er
            modulregisteret. `core/tests_avhengighetsretning.py` låser det med AST.
      - [x] **CLAUDE.md rettet** (14. sep. 2026): «Tilgangskontroll»-bolken beskrev
            fortsatt `accounts/decorators.py` som et skim som beholdes. Fila er slettet.
      - [x] **3.1 — kontoappen kjenner ingen modul ved navn** (14. sep. 2026).
            `core/kontokobling.py`; `PasientRolleForm` og malbiten bor i
            pasientmodulen. `handling` må være unik, og registeret avviser to handlere
            som deler den. Avhengighetstesten dekker nå `accounts` og `audit` også.
      - [→] **Kontoopprettelsen lager en `oppdrag.Enhet`** — *flyttet opp til
            «Åpne punkter» øverst i seksjonen, 14. sep. 2026.* Den lå her som et
            uavkrysset barn under et avkrysset punkt, og det er et punkt som
            forsvinner.
      - [x] **Rammeverket henter ikke lenger noe fra modulene** (14. sep. 2026).
            `core/driftstatus.py` og `core/portalinnstillinger.py`, begge etter idiomet
            fra `core/stats.py`. `KJENTE_UNNTAK` er tom, og `core` importerer en modul
            kun i modulregisteret — som skal navngi dem. Payloaden på server-status er
            bit for bit den samme, og JS-en er ikke rørt. `core/tests_registre.py`
            prøver de to egenskapene som ikke vises i den glade stien: at én død modul
            ikke tar med seg dashbordet, og at en modul som nekter stopper hele
            innsendingen av portalinnstillingene.
      - [x] **Fase 4 — ryddingen** (14. sep. 2026). `/portal-admin/` samlet i
            `core/urls_admin.py` med navnerommet `portaladmin` (3.2 — 21 ruter fra tre
            filer, 131 referanser skiftet prefiks), `core/views.py` delt i
            `views_portal`/`views_admin`/`views_backup`/`views_varsler` (3.7), og
            `accounts/decorators.py` slettet (3.3).
            - [x] **`core/tests_malenes_urler.py`:** hver `{% url %}` i hver mal skal la
                  seg slå opp. Django feiler på en ukjent rute først når malen *rendres*,
                  så en tagg i en gren ingen test rendrer kan være død i måneder.
                  Fant fem med det samme.
            - [x] **`core/tests_urls_admin.py`:** hele kartet låst til literale verdier
                  **med navnerom**, og hver GET-side rendret. Snapshotet mitt sammenlignet
                  `pattern.name` — altså uten navnerom — og sa «identisk» mens hver
                  `{% url 'accounts:…' %}` var død.
            - [x] **Funn:** testen som håndhevet «ingen importerer fra skimet» lette bare
                  etter den absolutte formen. `accounts/views.py` brukte den relative og
                  slapp unna i et år, med testen grønn.
            2691 tester grønne på SQLite og PostgreSQL.
      Kortversjonen av det gamle punktet under står igjen som underlag:
      `AppSetting`, `Backup`, `hent_aktiv_vakt`, CSP-/metrikk-/backup-
      middlewaren, `healthz` og server-status. Tabellnavnene beholdes (tilstandsmigrasjon,
      ingen datamigrasjon). Backupfilene bærer modellnavn — lasteren får en navnetabell
      med test som laster en fil i gammel form. *`patients/backup_service.py`,
      `RETENTION_HOURS` og `patients.BackupConfig` er alt borte (fase 8, 14. sep. 2026),
      så denne runden er blitt mindre.*
- [x] **2. Backupene på nytt grunnlag** (§4 i notatet). *Levert 14. sep. 2026 — alle åtte faser.* **Planen er skrevet ut i
      [`docs/PLAN_BACKUP_OMLEGGING.md`](./docs/PLAN_BACKUP_OMLEGGING.md)** — versjon 2,
      13. sep. 2026, med Andrés fem svar innarbeidet. Fase 1–6 kan kjøres **før** punkt 1
      over, jf. `PLAN_REKKEFOLGE_2026-09.md`.
      - [x] **Fase 1 — plan og klokke (13. sep. 2026).** `core.Backupplan`
            erstatter `ModuleBackupConfig`: tre moduser (av / ved endring /
            alltid), **intervall satt fritt i minutter, timer eller døgn**, cap
            på antall filer, og en standardplan modulene arver. `sist_sjekket_at`
            ved siden av `sist_fil_at`, så stille skilles fra stoppet.
            **Klokka er en tråd i web-prosessen** (`core/backup/klokke.py`), ikke
            en cron-tjeneste: Railway-volumet kan bare henge på én tjeneste, og
            en cron-tjeneste uten `/data` ville laget `Backup`-rader uten filer —
            som `har_backup_etter()` ikke skiller fra ekte, så kollapssperra
            ville åpnet seg på dem. `backup_kjor` er manuell inngang,
            `db_backup` ute av `CRON_JOBBER`, `CLAUDE.md` rettet til to
            cron-jobber. Vakthund i `klokke.vakthund()` (flate i fase 2).
            2557 tester grønne på SQLite **og** PostgreSQL, og en
            oppgraderingssimulering med rader i historisk form mot ekte
            PostgreSQL — migrasjonene er delt i tre (skjema, data, skjema), så
            triggerkø-fella ikke kan oppstå.
            - [x] **Bekreftet av André 13. sep.:** ett volum per tjeneste.
                  Klokkevalget står.
      - [x] **Fase 2 — én side (13. sep. 2026).** `/portal-admin/backup/` er nå
            hele flaten: standardplan øverst, «verste tilfelle nå» målt mot siste
            *vellykkede offsite-kopi*, diskbruk mot volumet, og én utfoldbar rad
            per modul med plan, knapper og filliste i samme boks. Modulsidene og
            oversikten er lagt ned. «Ta backup av alle nå» erstatter fire runder;
            «Gjenopprett siste» dekker det vanlige tilfellet.
            Gjenopprettingen har fortsatt egen bekreftelsesside — den er den ene
            handlingen her som sletter rader — men den sier nå **hvor mange rader
            i hvor mange tabeller** som forsvinner.
            **Nedlastingsknappene er fjernet helt**, også for modulfilene.
            Vakthunden vises på siden og på `/portal-admin/server-status/`, og
            varsler global admin — men bare fra reservenettet i middlewaren, for
            et varsel om at klokka er død, sendt av klokka, kommer aldri fram.
            2563 tester grønne på SQLite og PostgreSQL, og siden er kjørt i
            Chromium: lagring, avvist intervall, «ta backup av alle» og
            gjenopprettingsbekreftelsen virker.
            - Fant og rettet underveis: flerlinjes `{# … #}` er ikke en
              kommentar i Django og rendres som tekst på siden. Den sto både i
              den nye malen og i `user_form.html` fra før.
              `FlerlinjesMalkommentarTests` skanner nå alle maler.
      - [x] **Fase 3 — handlerne og utledet slettelista (13. sep. 2026).**
            `vaktliste`-handler (modulen sto **helt uten dekning** siden appen
            gikk i prod 11. sep. — korps, mannskap med telefon, e-post og ISSI,
            ressurser og vaktposter) og `portal`-handler med `core.Vakt` og
            `ModuleSettings`. `get_restore_models()` utledes nå topologisk fra
            `apps` minus `exclude`, og de fire håndskrevne listene er slettet.
            Utledningen traff alle fire og fant den ene kjente feilen:
            **`Lydvarsel` (gjeldspunkt 3.4) er dekket, uten at noen måtte huske
            den.** `SlettelistaDekkerDumpenTests` håndhever at hver modell som
            dumpes også tømmes. Modulen `arkiv` heter nå
            «Pasientregistreringsarkiv».
            **Gjenoppretting i tom base er bevist**, ikke påstått: alle seks
            filene lastet i rekkefølge i en fersk PostgreSQL-base, alle rader
            tilbake. Og motprøven — uten portalfila feiler alle tre modulfilene
            med «Key (vakt_id)=(1) is not present in table core_vakt», som er
            nøyaktig hullet `TEKNISK_GJELD.md` §4 beskrev.
            `AlleFileneGjenopprettesTests` gjør den samme øvelsen i suiten.
            2582 tester grønne på SQLite og PostgreSQL.
      - [x] **Fase 4 — hel backup (13. sep. 2026).** `core/backup/full.py`:
            alt i databasen unntatt sesjoner, contenttypes, permissions,
            `admin.LogEntry` og backup-metadata. Brukere med passordhasher,
            MFA-enheter, tilganger og logg er med — fila er **selvbærende**, og
            FK-er til kontoer strippes derfor ikke. Appene **regnes ut** av
            app-registeret ved hvert kall, ikke listet for hånd: en
            katastrofekopi som stille mangler en app er verre enn ingen.
            Eget prefiks `full/` offsite, så 90 dager kan skilles fra 730.
            Eget kort på backup-siden, og gjenopprettingsbekreftelsen sier at
            kontoen du er logget inn med byttes ut underveis.
            Standard: alltid, hver 24. time, behold 7.
            **Bevist i tom PostgreSQL-base:** hele basen tilbake fra den ene
            fila, og innlogging med det opprinnelige passordet virker etterpå.
            - [x] **Funn som stoppet den første kjøringen, og som var en
                  eksisterende feil:** ingen av de atten lagringssignalene så
                  etter `raw=True`. `loaddata` fyrte dermed audit-signalene,
                  som leser relaterte objekter — og i den hele fila kommer et
                  `Vaktpost` før sitt `Mannskap`, så gjenopprettingen stoppet
                  med «Mannskap matching query does not exist». Det skrev også
                  én auditrad per lastet rad ved **hver** gjenoppretting, også
                  modulenes. `audit.utils.ikke_under_loaddata` er vakten, og
                  `SignalerFyrerIkkeUnderLoaddataTests` krever den på alle
                  mottakere.
            - [x] **Krever Andre før dette er i prod:** livssyklusregelen på
                  `full/` (fase 7). Satt av André 14. sep. 2026 — se fase 7.
      - [x] **Fase 5 — `gjenopprett`-kommandoen (13. sep. 2026).** `--list`,
            `--siste <modul>` (hopper over pre-restore-øyeblikksbildene),
            `--hent <objekt>` som henter fra Scaleway og gjenoppretter i ett,
            `--full` som **kreves** for hele basen, og `--ja`. Flagget er
            nødvendig og ikke bekvemt: `railway ssh -- <kommando>` har ingen
            interaktiv terminal, så et spørsmål ville hengt til noe ga opp —
            i en katastrofe. Kommandoen sier det i stedet for å vente.
            **Auditraden er flyttet fra viewet inn i `restore_backup`**, med en
            `kilde`-tekst: sto den i viewet, ville katastrofeveien vært den
            eneste som ikke etterlot seg et spor. Begge inngangene gir nøyaktig
            én rad. `slug_fra_filnavn` bor nå ved siden av `_build_filename`,
            så formen på filnavnet har ett sted å endres.
            Runbooken §8b har fått hele katastrofeprosedyren, inkludert at
            `purge_old_logs` og `kollaps_arkiv` skal kjøres rett etterpå.
            2608 tester grønne på SQLite og PostgreSQL.
      - [x] **Fase 6 — `verifiser_backup` (13. sep. 2026).** Laster filene
            som faktisk ligger på volumet inn i en engangs-SQLite-base og
            sammenligner radene mot det filene inneholder, modell for modell.
            Rører ingenting: basen og mappa slettes etterpå, og filene kopieres
            dit først så pre-restore-øyeblikksbildene ikke havner blant de ekte
            backupene. `--full`, `--modul`, `--behold`.
            Kaller `gjenopprett`, ikke `restore_backup` — da er det veien man
            faktisk ville brukt i en katastrofe som er prøvd.
            **En tom fil gir advarsel**, ikke grønt: «alt kom tilbake» skal
            ikke stå for en modul som ikke hadde noe å komme tilbake med.
            Auditraden gjenopprettingen selv skriver telles ikke som avvik.
            `PORTAL_ENGANGSBASE=1` er en navngitt åpning i `settings.py`-sjekken
            som ellers krever PostgreSQL på Railway — så kommandoen kan kjøres
            der filene er. Runbooken §8b sier når den skal kjøres.
            2618 tester grønne på SQLite og PostgreSQL.
      - [x] **Fase 7 — oppbevaringstidene i bucketen `sanitetsportalen`**
            (14. sep. 2026, `PLAN_BACKUP_OMLEGGING.md` §7). Regelen sto på **730 dager
            med scope «alle objekter i bucketen»**, og ble snevret inn til prefikset
            `backups/` **før** regelen på `full/` med 90 dager ble lagt til — to regler
            som treffer samme objekt er et sted å gjette. Satt av André i konsollen:
            portalens IAM-nøkkel kan lese bucket-oppsettet, men ikke skrive det, og en
            portal som kunne forkorte sin egen oppbevaringsregel ville ikke vært en sperre.
            - [x] **Kortet leser reglene tilbake fra bucketen**
                  (`core.offsite.livssyklus()`, `FORVENTET_DAGER`), ikke fra det vi tror
                  vi satte. Fristene håndheves av Scaleway — portalen har ikke sletterett,
                  og `enforce_cap` rører bare volumet — så livssyklusreglene er den
                  **eneste** mekanismen som sletter en offsite-kopi. Sammenligningen er på
                  **nøyaktig** prefiks, fordi feilen man faktisk gjør er `/full` i stedet
                  for `full/`: en regel som ser riktig ut i konsollen og treffer
                  ingenting. Avvik står i rødt ved siden av backupene — mangler, feil
                  prefiks, slått av, feil antall dager, eller ingen regler i det hele tatt.
                  `livssyklus()` kaster aldri og cacher i fem minutter.
            2627 tester grønne på SQLite og PostgreSQL.
      - [x] **Fase 8 — rydding (14. sep. 2026).** `db_backup`,
            `patients/backup_service.py`, `patients.BackupConfig` og `RETENTION_HOURS` er
            **slettet**; migrasjonen er `patients/0017`. Dermed finnes det én vei inn til
            backup, og den krever en slug: `core.backup.create_backup(slug=...)`.
            Proxyen var ikke bare død kode — den lot et kallsted ta backup uten å nevne
            hvilken modul, og slugen er hele forskjellen på en pasientfil og en hel
            database. `db_backup` het som om den tok hele databasen og tok pasientmodulen.
            `RETENTION_HOURS = 72` ble aldri lest; oppryddingen er antallsbasert
            (`Backupplan.behold`), og oppbevaringen offsite er bucketens livssyklusregel.
            `LegacyBackupErBorteTests` håndhever at de tre ikke kommer tilbake — hver av
            dem ville kommet tilbake som en bekvemmelighet, ikke som en feil noen så.
            Migrasjonen avhenger av `core/0002`, som leser den gamle tabellen i et
            `RunPython`-steg. *Prøvd uten avhengigheten: Django la dem i riktig rekkefølge
            likevel, fordi `core/0002` selv peker på `patients/0005`. Kanten står der for
            at rekkefølgen skal være skrevet i stedet for et sammentreff i grafen.*
            2630 tester grønne på SQLite og PostgreSQL. **Backupomleggingen er dermed
            ferdig — alle åtte fasene er levert.**
      - [x] **Prefiksrutingen låst** (14. sep. 2026, etter Andrés spørsmål om
            filnavnene). `prefiks_for()` sammenligner mot strengen `'full'`, ikke mot
            `Backupplan.FULL_SLUG` — greit nok (slipper modellimport i `offsite.py`),
            men slugen står da to steder. Et navnebytte ett sted ville ikke feilet:
            den hele fila hadde bare havnet under `backups/` og fått 730 dagers
            oppbevaring i stedet for 90, uten at noe sa fra. `PrefiksRutingTests`
            låser konstanten, hele registeret, rundturen filnavn → slug → prefiks,
            og at de to prefiksene ikke er forstavelser av hverandre. Prøvd mot
            begge mutasjonene.
      - [x] **Migrasjonsprøve for `core/0008`–`0010`** (14. sep. 2026, før prod).
            `0009` skriver data, og et dataskritt mot en tom base skriver ingenting —
            suiten kunne derfor ikke si om release-fasen overlever prods rader. Prøven
            seeder den historiske formen, inkludert begge måtene å si «av» på, og krever
            at ingen eksisterende rad arver standardplanen: gjorde de det, ville
            oppgraderingen endret hvor ofte prod tar backup uten at noen ba om det.
            3 av 3 prøver grønne.
      **Alt er avklart** (13. sep. 2026, to runder — se notatets §11). Bucketen heter
      `sanitetsportalen`. Planen kan iverksettes fra fase 1.

- [ ] **3. Dokumentrunden — når 1 og 2 er levert.** Én runde, ikke stykkevis, og den tar
      med seg **alt fra 11.–13. september** (sikkerhetsrundene, server-status, reserve og
      offline, offsite, flere enheter per oppdrag, ISSI og besetning, audit i vaktlista,
      lyd og bilens utganger). Lista over hva som mangler hvor står i `docs/BACKUP.md` §5:
      - [x] `docs/TEKNISK_DOKUMENTASJON.md` *(14. sep. 2026, to runder)* — **hele dokumentet**
            gjennomgått. Kap. 5 dokumenterte 16 av 123 endepunkter; 8B hadde en signatur som
            ville gitt `TypeError`; 14 oppga «178 tester». Ingen «ikke gjennomgått»-markører igjen
      - [x] `README.md` *(14. sep. 2026)* — skrevet om som inngangsdør. Beskrev en rollemodell som ikke finnes
      - [x] `docs/RUNBOOK_VAKT.md` — §8b var alt gjort; nytt §8c (rollback) lagt til
      - [ ] ~~§8b med hel backup og gjenoppretting i tom base~~
            (`BACKUP.md` §4), inkludert `purge_old_logs` + `kollaps_arkiv` rett etterpå
      - [ ] `docs/PERSONVERN_DOKUMENTASJON.md` — A.2 (Scaleway: hele databasen), A.9 (hel
            backup 90 dager, modulfilene 730 dager offsite), A.10, A.11/A.6 (fil på e-post,
            offline drift)
      - [ ] `CLAUDE.md` — backup-avsnittet og hvor modellene bor
      - [x] `docs/DEPLOY_GUIDE.md` *(14. sep. 2026)* — nytt navn, AHASend, offsite, cron, hasher, rollback. ~~heter fortsatt «Pasientregistreringssystem»; portal-~~
            domenet, AHASend-variablene, offsite-variablene, `requirements.txt` med hasher.
            Punktet lenger ned under dokumentgjennomgangen slås sammen med dette
- [ ] **4. De mindre** (§3 i notatet), når man er i nærheten: brukeradmin importerer
      pasientregistrene (3.1), `/portal-admin/` samlet i én URL-fil (3.2), skimene
      (3.3), `core/views.py` delt (3.7). 3.5 (`VaktArkiv`) skal **ikke** ryddes —
      signaturen. 3.6 og 3.8 tas underveis, ikke som egne runder.

### Reserve og offline — besluttet 12. sep. 2026

Bakgrunn: ingen deploy under vakt. Da dekker et speil til staging nesten ingenting
(plattformbortfall tar begge, en datafeil kopieres innen minutter), og det er tatt ut.
Pasienter har Excel, oppdrag går på nødnett. Det som skal overleve at Railway faller er
**dataene** (utenfor Railway) og **vaktlista i drift** (på drifts-PC-en, uten server).

- [x] **1. Vaktlista som fil, på e-post** (12. sep. 2026, `vaktliste/fil.py`,
      `Utsending`, `vaktliste/0016`). Ukryptert etter vurdering (§12 i notatet):
      telefon og ISSI med, ikke e-post/notat/merknad; fast mottakerliste hos admin;
      ved «Sett i drift» og på knapp; hver utsending logget. AHASend fikk vedlegg.
      - [x] **Bekreftet på staging 13. sep.:** vedlegget kommer fram, fila åpner på
            iPhone og PC, automatikken kan slås av.
      - [x] **Intervallsending** (13. sep., `0017`): hvert N. minutt i drift, bare ved
            endring, via `FilutsendingMiddleware`.
      - [ ] **Personverndokumentasjonen:** utleveringen inn i A.2/A.6, formål
            «reserve ved bortfall av portalen».
- [x] **2. Offline drift på `/vaktliste/`** (13. sep. 2026): service worker
      (`vaktliste-sw.js`), kø for møtt/av vakt i `localStorage` med klienttid,
      `services.vurder_klienttid`, banner og «Klar for offline». Testes i Chrome/Edge på
      PC på staging.
      - [x] **Bekreftet på staging 13. sep.:** kopi med nettet av, kø sendt når nettet
            kom tilbake, tida fra trykket, avvist trykk fjernet med beskjed, utgått
            innlogging håndtert, /django-admin/ borte.
- [x] **3. Backupene ut av Railway, til Scaleway Object Storage** (13. sep. 2026,
      `core/offsite.py`, `OffsiteKopi`, `core/0007`, `hent_offsite`). Kryptert før
      opplasting (AES-256-GCM), henger på ny fil fra `create_backup`, kaster aldri, status
      på /portal-admin/backup/. Bucket i Amsterdam, One Zone, SSE på, versjonering av,
      lifecycle 730 dager / multipart 7 dager — satt av André; delt i to prefikser
      14. sep. 2026 (`backups/` 730, `full/` 90), se fase 7 over. DPA:
      https://www-uploads.scaleway.com/DPA_2024_ENG_b0abb5cc26.pdf
      - [ ] **André:** IAM-applikasjon med policy (ObjectStorageObjectsWrite/Read,
            BucketsRead, ikke delete), API-nøkkel, `OFFSITE_BACKUP_KEY` i passordbehandler,
            de seks variablene på prod-tjenesten.
      - [x] Runbook §8b (13. sep.): oppsett, kontroll, gjenoppretting.
      - [ ] **Prøv gjenopprettingen én gang** i prod-containeren når variablene står:
            `railway ssh --service web -- python manage.py hent_offsite --list`, hent én
            fil, og se at den dukker opp under /portal-admin/backup/.
- [x] **4. Den gamle offline-arkitekturen er fjernet** (13. sep. 2026, samtidig med 2
      etter Andrés valg): `OFFLINE_MODE`, CSRF for LAN, Django-admin under offline,
      `create_offline_users`, `.env.offline.example`, `OFFLINE_PASSORD.md`, USB-pakken.
      `import_offline_data` beholdt som dataimport fra gammel prod.

Rekkefølgen er 1, 2, 3, 4. Speiling til staging er **tatt ut** — den ble vurdert og
forkastet fordi det ikke deployes under vakt.

### GDPR-gjennomgang

Fase 0–5 er gjennomført. Begrunnelsene og de varige beslutningene ligger i
[`docs/PERSONVERN_DOKUMENTASJON.md`](./docs/PERSONVERN_DOKUMENTASJON.md); hva som ble gjort
står i [`CHANGELOG.md`](./CHANGELOG.md). Tre punkter gjenstår:

- [ ] Fyll inn organisasjonsnavn i A.4 — se «Krever Andre» øverst
- [x] Cron-jobb for `kollaps_arkiv` satt opp — se «Krever Andre» øverst
- [x] **Skriftlig DPIA-vurdering.** Den står i A.12, «DPIA (art. 35) – vurdert som ikke
      påkrevd». **Men punktet under er ikke det samme, og erstatter det ikke.**

#### DPIA, fritekst og adresse — se [`docs/NOTAT_DPIA_OG_FRITEKST.md`](./docs/NOTAT_DPIA_OG_FRITEKST.md)

*Utløst 14. sep. 2026 av spørsmålet om AMK-adresse kan legges i `Oppdrag.fritekst`.
Notatet bærer begrunnelsene; her står bare arbeidet.*

**Premisset som måtte rettes:** dokumentasjon fritar ikke for DPIA. A.12 bygger ikke på at
vi har dokumentasjon, men på tre andre ben — ingen direkte identifikatorer, ikke stor
skala, ingen profilering. Det tyngste (skala) holder. Det første gjør ikke det hvis adresse
legges inn, og **A.12 har selv skrevet utløseren**: «særlig dersom nye moduler tar inn
direkte identifikatorer».

- [ ] **Avklar behandlingsansvaret.** A.1 legger det på André som privatperson, ikke på
      organisasjonen. Behandlingsansvar følger virkeligheten, ikke papiret — bestemmer
      foreningen formål og midler, er de ansvarlig uansett hva dokumentet sier. Påvirker
      alle svarene under, og bør derfor tas først. Se «Krever Andre» øverst
- [ ] **Slettefrist på `Oppdrag.fritekst`.** Feltet slettes aldri fra historikken hos KO i
      dag; beskyttelsen som finnes er bygget helt mot bilen. A.12 har det som åpen
      restrisiko. To deler: serveren utelater teksten når fristen er passert, og en feiing
      (i `purge_old_logs`) tømmer feltet for alvor. Frist som `AppSetting`, nedtelling i
      historikkraden — og bare når det faktisk står tekst der
- [ ] **Avgjør: klokka fra `historikk_fra`, eller fra siste `Ledig`?** Et oppdrag med
      `trenger_ressurs` når aldri historikken og beholder fritekst for alltid
- [ ] **Adressefeltet: eget felt, ikke i fritekst — og aldri i `Lokasjon`.**
      `Lokasjon.navn` fryses i `ArkivertOppdrag.lokasjon_navn`, som inngår i
      SHA-signaturen: en adresse lagt der er låst i 24 måneder ved konstruksjon
- [ ] **Skriv om A.6-argumentet** hvis adressen kommer inn. «Oppdraget har ingenting, og
      re-identifisering krever kunnskap utenfra» holder ikke når kunnskapen utenfra ligger
      i raden
- [ ] **Skriv art. 35(7)(c) — risiko for de registrertes rettigheter.** A.12 er en
      *sikkerhets*risikovurdering: den måler sannsynlighet og konsekvens av brudd, altså
      risiko sett fra systemets side. Hva som skjer med pasienten hvis det går galt, er
      ikke spurt om noe sted. Nyttig i seg selv, og halve jobben hvis en DPIA senere kreves
- [ ] **Sjekk mot primærkilde:** Datatilsynets liste over behandlinger som alltid krever
      DPIA, og WP248-kriteriene i gjeldende form. Notatet gjetter ikke på dem

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

### Rapportmodul — se [`docs/FORSLAG_RAPPORTMODUL.md`](./docs/FORSLAG_RAPPORTMODUL.md)

**Forslag, ikke besluttet** (14. sep. 2026). En `/rapport/`-modul med to deler:

- [ ] **Del 1: timeregnskap og betaling.** *Anbefales.* Timer per mannskap, korps og
      rolle, med kr/time og sum per korps. Mye finnes alt —
      `vaktliste.services.belastning_per_person()` regner timene, og `Vaktpost.probono`
      bærer allerede skillet «går, men telles ikke i timene».
      **Krever en avgjørelse først:** plan eller faktisk som fakturagrunnlag (§2.2), og om
      rapporter skal **fryses** (§2.4). Uten frysing er ikke et fakturagrunnlag
      etterprøvbart et år senere — da er dette et arkiv, ikke en visning.
- [ ] **Del 2A: rapport uten LLM.** *Anbefales, og er et komplett produkt alene.* Tall,
      tabeller og et malbasert sammendrag fra `core.stats`. Ingen ny databehandler, ingen
      endring i personvernprotokollen, ingen filtrering nødvendig — den som ser rapporten
      har allerede tilgang til kildedataene.
- [ ] **Del 2B: LLM-tolkning.** *Gjennomførbart.* Første utkast frarådet det på feil
      grunnlag; payloaden fra `core.stats` er aggregater uten radnivå, ID-er, klokkeslett
      eller fritekst, så GDPR er trolig ikke i spill (fortalepunkt 26). Krever:
      **kategorifilter som feiler lukket**, «Generer rapport»-knapp, forhåndsvisning av
      payload, EU-hostet modell med DPA og zero retention, merking som maskingenerert, og
      audit av hvert kall.
- [ ] **Kategorifilteret.** Ekskluder risikoproblemstillinger (Andrés forslag, bedre enn
      undertrykking av små celler — se §3.4). Må merke hva som er **godkjent for
      utsending**, ikke hva som skal ekskluderes: en glemt ny kategori skal falle ut, ikke
      slippe ut. Forutsetter at pasientmodulens problemstillinger flyttes fra
      `choices.py` til en tabell, slik oppdrag gjorde i `0019`–`0021`.
- [ ] **Verifiser Scaleway Generative APIs mot primærkilden** før beslutning — zero
      retention i avtaleteksten, og underbehandlerlista. Anbefalt fordi Scaleway SAS
      allerede står i A.2 med signert DPA.

Fem åpne spørsmål til André står i §6 i notatet.

### Datteroppdrag — én hendelse, flere pasienter — se `docs/FORSLAG_DATTEROPPDRAG.md`

- [ ] **Idé, ikke besluttet** (13. sep. 2026). Et oppdrag kan deles i datteroppdrag, ett
      per pasient, med egen bil, grovsortering og tidslinje; `Oppdrag.forelder`, dybde
      låst til ett nivå, pasientantall bare på bladene, arkivet får `forelder_nummer` bare
      når satt. Gir hendelsestidslinje, ressursbruk og spredning per hendelse i
      statistikken. To–tre kvelder.
      - [ ] **Krever Andre — før koden:** hva skjer med morens bil når den første
            datteren lages — blir den på moren, eller flyttes den? (§7 i notatet)

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

- [ ] **Vis hvilket miljø portalen kjører i.** Utløst 29. aug. 2026: en arbeidsøkt gikk
      med til å feilsøke en innlogging som feilet fordi forsøkene gikk mot prod mens
      kontoen lå på staging. Ingenting i grensesnittet skiller de to.

      Under en vakt er innsatsen høyere enn en tapt time: forskjellen er om en pasient
      registreres i den ekte basen eller i en testbase. En liten, tydelig markør på
      **ikke-prod** (miljønavnet i toppen, gjerne farget) koster lite. Prod skal være den
      nøytrale tilstanden — en markør der ville blitt visuell støy man slutter å se.

      Miljønavnet finnes allerede som Railway-variabel; det trengs ingen ny innstilling.

- [ ] **VURDER: skal innlogging normalisere passordet?** Funnet 29. aug. 2026.
      `set_password` kaller `make_password` rett på råstrengen, så Django normaliserer
      ikke passord. Et passord med `å` satt i én Unicode-normalform og skrevet i en
      annen gir ulik hash — usynlig for både bruker og admin. (`æ` og `ø` dekomponerer
      ikke og rammes ikke.)

      En fallback som prøver den NFC-normaliserte formen i tillegg til råstrengen ville
      rettet det uten å bryte eksisterende passord. Men den utvider hva som godtas som
      gyldig passord, og bør derfor besluttes bevisst. **NFC, ikke NFKC** om det gjøres:
      NFKC folder også kompatibilitetstegn, slik at «ﬁsk» ville åpnet en konto med
      passordet «fisk».

      `sjekk_brukernavn` nevner muligheten når ingenting annet blokkerer innlogging.

### Vakt som scope, ikke år — se `docs/BESLUTNING_VAKT_SOM_SCOPE.md`

- [ ] **Premiss fastslått av André 29. aug. 2026: portalen tenker i *vakter*, ikke i år.**
      Den skal brukes på forskjellige arrangementer, ikke på det samme én gang i året.
      Ingenting er bygget på dette ennå — punktet står her for at premisset ikke skal
      gå tapt, og fordi et docs-punkt som ikke står i TODO ikke blir gjort.

      **Dagens scope er `year`, og det stikker dypt.** Kartlagt 29. aug.:
      `Patient.year`, `Oppdrag.year`, `VaktArkiv.year_snapshot`, 73 kallesteder på
      `get_active_year`/`active_year` i 8 filer, tellerne `next_patient_nr` og
      `next_oppdrag_nr_<år>`, og statistikkens gruppering.

      **Konsekvensen er allerede synlig i kode som nettopp ble skrevet.**
      `oppdragsnummer` restarter per *år*. Kjøres tre vakter i 2026, teller numrene
      1–40 tvers gjennom alle tre — «oppdrag 14» blir da tvetydig neste gang, som er
      nettopp det nummeret skulle løse. Under vakt-scoping skal det restarte per vakt.

      **Vaktnavnet finnes allerede halvveis:** `AppSetting['event_name']`, og
      `VaktArkiv` fryser `arrangement_navn` på seg selv. `patients/services.py` noterer
      dessuten at en `event_name_<år>`-mekanisme fantes og ble slettet 13. aug. som
      ubrukt — den ble skrevet for et behov som nå har meldt seg på ordentlig.

      **Spørsmål som må avgjøres før kode:**
      - Blir `Vakt` en modell, eller er det `event_name` som får bære det?
      - Hva skjer med data som allerede er scopet på år? Prod har 273 importerte
        pasienter på 2026, og staging har oppdrag.
      - Kan to vakter være åpne samtidig, eller er det én aktiv om gangen som i dag?
      - Har en vakt start og slutt, eller lukkes den ved arkivering?
      - Hvordan spiller det mot fase 7, som allerede fryser `arrangement_navn`?
      - Skal statistikken sammenligne vakter i stedet for år?

      - [x] **Notatet er skrevet (29. aug. 2026):**
            `docs/BESLUTNING_VAKT_SOM_SCOPE.md`. Foreslår `Vakt` som modell i `core`,
            to deployer, og backfill fra `year`. **Ikke besluttet** — fem åpne
            avklaringer står nederst i notatet og trenger svar fra André før
            migrasjonen skrives.
      - [x] **De fem avklaringene besvart, forslaget vedtatt (29. aug. 2026).**
            Fritekst-navn (unikt), gjenåpning til kollaps, pasientnummer per vakt
            (sperren flyttes i deploy 2), manuell sletting av tomme vakter, ingen
            gruppering nå. Alle med notatets anbefaling.
      - [x] **Deploy 1 — kodet 29. aug. 2026.** `core.Vakt`, backfill per år
            (navn = årstallet; `event_name` er global og ville påstått noe vi
            ikke vet), nullbare FK-er på `Patient`/`Oppdrag`/`VaktArkiv`, alle
            fire skrivestiene setter vakta, `hent_aktiv_vakt()` med lat
            opprettelse og pekerreparasjon, og `verifiser_vakt` som også
            forhåndssjekker deploy 2-sperrene. Backfill, full rollback og ny
            kjøring bevist mot en base med data i tre år.
      - [x] **Deploy 1 verifisert i prod 29. aug. 2026** — `verifiser_vakt`: «Ingen funn».
      - [x] **Deploy 2 — kodet 29. aug. 2026.** All lesing på vakt, FK-ene
            `NOT NULL`, `(vakt, pasientnummer)`- og `(vakt, oppdragsnummer)`-sperrer
            i basen, `year` fjernet fra radene, tellere per vakt
            (`next_patient_nr_vakt_<id>`), `event_name`/`active_year`/`next_patient_nr`
            flyttet fra `AppSetting` til vakta, «Avslutt vakt» erstatter «Nullstill år»,
            «Gjenåpne» fram til kollaps, «Tidligere vakter»-liste. Migrasjonene
            (`patients.0016`, `oppdrag.0007`) har sperre mot rader uten vakt og
            nekter revers — rollback er gjenoppretting fra backup.
      - **Fase 6 og 7 er ikke lenger blokkert** — scopet er levert; de grupperer
        og arkiverer på `Vakt`.

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

### Dataimport fra gammel prod — se `docs/archived/DATAIMPORT_FRA_GAMMEL_PROD.md`

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
  - [x] **`AbstractArkiv`-basemodell (29. aug. 2026).** Bygget i fase 7 av
        oppdragsmodulen, som lovet — `OppdragArkiv` var modell nummer to, og da var
        det ikke lenger gjetning hva som er felles. Basemodellen bærer `tittel`,
        `vakt`/`vakt_navn`, `antall_rader`, `importert_av` med frosset navn, `sha256`,
        `kollapset_at`, `aggregat` og `aggregat_sha256`. `VaktArkiv` er som planlagt
        *ikke* migrert: `year_snapshot` og `arrangement_navn` inngår i SHA-payloaden
        til hvert arkiv i prod. Park arver basemodellen når den skrives.
- [ ] Park-registreringer blir **egen modell**, ikke rader i `Patient`. Holder sykestuas
      liste på ~250 rader i stedet for 1000, og matcher at dataene er enklere.
- [ ] Park-appen er et skriveendepunkt **uten innlogging**: signert lenke via
      `django.core.signing` (ikke gjettbar URL, kan tilbakekalles), rate-limit per token,
      og responsen returnerer kvittering — aldri data.
- [x] **Oppdragsmodulen — se `docs/BESLUTNING_OPPDRAGSMODULEN.md`.** Besluttet 28. aug.
      2026, **alle sju fasene levert 29. aug. 2026.** Modulen er den første som tar
      `skriv_handling` i bruk. Den står i staging og venter på merge til prod og på
      første skarpe vakt; §12.1 (sammenslåing av arkiveringen) er utsatt som egen sak,
      se punktet lenger ned. Punktene under lå her løst fra før og ble plassert i planen:
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
      - [x] **Fase 2, resten — protokollen presisert (29. aug. 2026).**
            `PERSONVERN_DOKUMENTASJON.md` v1.7: oppdragsmodulens datakategorier og
            hjemler i A.6 med fritekst-tiltakene samlet, lagringsrad og merknad i A.9,
            sårbarhet med restrisiko i A.12, unntaket ført inn i audit-tabellen, og
            B.2-merknad om at utrykningsoppdrag registreres uten identifikator.
            Rekkefølgekravet («før feltet er i prod med logging på») holdt: modulen
            finnes kun på staging, og verdilogging av fritekst har aldri vært aktiv.
            - **Funn underveis, ført inn i A.9:** oppdragsdata står utenfor
              applikasjonens modulbackup — ingen handler er registrert, så Railways
              databasebackup (aktiv ca. én måned i året) er eneste dekning fram til
              fase 7. Bør få en handler senest sammen med arkiveringen.
      - [x] **Fase 3 — sentralbordet (29. aug. 2026).** Enhetsliste med utledet
            status (`Ledig (2 venter)`), oppdragsliste, oppretting, flytting, tidslinje
            og lokasjonsadmin. ETag på pollingen. Modulen er synlig nå som den har en
            side. To grensesnitt bak én URL, valgt på enhetskoblingen — en test setter
            `skriv_full` på en enhetskonto og krever at den fortsatt får enhetsskjermen.
      - [x] **Enhetsadmin (29. aug. 2026).** Enheter kunne bare lages fra
            `manage.py shell` — en glipp, ikke en avgrensning. Opprettelse, aktivering og
            kontokobling ligger i sentralbordets admin-panel nå, med regelen skrevet rett
            i panelet: koblingen gir ingen tilgang.
      - [x] **Enheten følger kontoen, også ut (29. aug. 2026).** «Legg til enhet»
            fjernet med endepunkt og URL — enheter fødes med kontoen. Sletting av
            kontoen sletter enheten, eller pensjonerer den hvis den har oppdrag
            (`Oppdrag.enhet` er PROTECT). Frysing tar den av vakt.
      - [x] **«Pensjoner» fjernet (29. aug. 2026).** Opptellingen på staging ga
            `Enheter uten konto: 0 av 2`, så knappen hadde ingen jobb igjen. Fjernet
            sammen med Gjenopprett, `PUT /api/enheter/<pk>/`, `/api/kontoer/` og
            `OPPDRAG_TILGANG.erAdmin`. Et pensjonert, ukoblet enhetsnavn regnes nå
            som ledig, og raden gjenbrukes når kontoen opprettes på nytt — ellers
            ville navnet vært brent for godt.
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
      - [x] **Fase 4 — enhetsskjermen (29. aug. 2026).** Mellomtilstanden fra fase 3
            er borte; `enhet.html` + `oppdrag-enhet.js` viser egne oppdrag med to
            knapper — «neste» og «Ledig» — mot **fem** navngitte stemplingsendepunkter
            (`status/<overgang>/`, første faktiske bruk av `skriv_handling`). Planen sa
            seks, men talte statusene: `venter` settes ved oppretting og stemples aldri,
            og settet utledes nå av `services.STEMPLBARE` fra overgangstabellen.
            - Lukket kroppsskjema (`klienttid`, `idempotency_key`) testet ved
              uttømming; klienttid valideres per §5.1 med `forsinket`-flagg;
              `idempotency_key` godtas men kobles først i fase 5 — statusmaskinen gjør
              en ren avspilling ufarlig (409 uten ny rad).
            - To porter: `skriv_handling` + eierskaps-objektsjekk. `skriv_full` uten
              enhetskobling får 403 — stemplingen er en måling fra bilen, og en
              operatør som stempler «for» en enhet ville forfalsket den.
            - JS-en kjenner ikke kjeden: serveren sender `neste_overgang`/`neste_navn`
              per rad. Dobbelttrykk gir 409, og skjermen svarer med å hente ferskt.
            - `automatisk` vises per §4.5: markør på klokkeslettet, gråtoner, ingen
              badge. Skjulereglene var server-side fra fase 3 og står urørt.
      - [x] **Fase 4b — korreksjoner (29. aug. 2026).** `POST
            /oppdrag/api/statusmelding/<pk>/korriger/` skriver en **ny rad som peker på
            den gamle**; originalen er uendret, og begge står i tidslinjen. Maskineriet
            kom i fase 1 (`korriger_tidspunkt`, `gjeldende()`) — det som manglet var
            endepunktet, reglene og grensesnittet.
            - **Fire regler, alle fail-closed:** raden må være gjeldende (ellers fantes
              to korreksjoner av samme original), ikke i framtiden, ikke før oppdraget
              ble opprettet, og **rekkefølgen må holde**. Den siste er den som betyr
              noe for fase 6: `Fremme` før `Rykker ut` gir negativ responstid, og
              statistikken ville regnet på den uten å vite at tallet er umulig.
              Feilmeldingen navngir naboen som er i veien, så operatøren vet om hun må
              rette en annen rad først.
            - **Ikke et handling-endepunkt.** Det tar en feltverdi, så det ligger på
              `skriv_full` med vanlig kroppsvalidering — å presse det under
              `skriv_handling` ville uthult det lukkede skjemaet i §5.1 med én gang.
              Enheter får 403 uansett nivå: en bil som kunne rette sine egne tidspunkt
              ville gjort stemplingen til en påstand i stedet for en måling.
            - Bilen *ser* rettingen («rettet av sentralen», §4.5), men kan ikke gjøre
              den.
      - [x] **Oppdragsnummer og arkivknapp (29. aug. 2026)** — bestilt av André
            under uttesting av fase 4, utenom faseplanen. Løpenummer per år
            (`unikt_oppdragsnummer_per_aar`, migrasjon `0003` med backfill), og en
            «Arkiver»-knapp som rydder ferdigstilte oppdrag ut av tavla og inn i en
            søkbar «Ferdigstilte»-visning.
            - **Arkiveringen er rydding, ikke frysing.** Raden er urørt, handlingen
              reversibel, og den ligger derfor på `skriv_full` — §3.3 reserverer admin
              for det irreversible. Vaktarkivet i fase 7 er fortsatt uendret på planen,
              og de to kan leve side om side: drift under vakt mot dokumentasjon etter.
            - [x] **Arkiveringen er automatisk ved `Ledig` (29. aug. 2026).** Den
                  manuelle knappen løste ikke problemet: krever ryddingen et trykk per
                  oppdrag under vakt, blir den ikke gjort. Regelen ligger i
                  `sett_status`, ikke i viewet, slik at også den automatiske lukkingen
                  i `start_oppdrag` treffes — ellers beholdt tavla nettopp de
                  oppdragene ingen trykket på. `arkivert_av` er NULL ved automatikk.
                  Knappen står igjen for «hent tilbake» og «rydd bort igjen».
            - Kun ferdigstilte kan arkiveres. Å rydde bort et pågående oppdrag er samme
              feilklasse som å ta en enhet av vakt midt i et oppdrag.
            - **Arkivering rører ikke enhetens 30-minuttersvindu.** De to reglene ser
              like ut, men vinduet er personvern og arkiveringen er tavlerydding;
              koblet ville sentralbordet kunnet fjerne et oppdrag fra en skjerm noen
              fortsatt så på.
      - [x] **Fase 5 — offline-kø (29. aug. 2026).** Stemplingen skrives til
            `localStorage` først, skjermen oppdaterer seg med en gang, og synkingen
            skjer i bakgrunnen. Utløsere: neste trykk, neste poll, og `online`.
            - **Nøkkelen lages ved trykket og beholdes gjennom hvert forsøk.** Det er
              den som gjør avspilling trygg: serveren svarer `ok` med den opprinnelige
              meldingen i stedet for 409, og køen kan stryke raden. Uten den kunne
              køen ikke skille «allerede levert» fra «avvist fordi skjermen har
              sakket akterut».
            - **Reservert etter all validering** — et avvist forsøk brenner ikke
              nøkkelen, og `forkast()` frigir den når overgangen avvises.
            - **Serielt og i rekkefølge.** To parallelle sendinger kunne landet
              «Avreist» før «Fremme», og `Statusmelding` er et spor av hva som skjedde.
            - **Kjeden sendes til skjermen som data**, kun for å regne ut hva neste
              knapp skal hete mens noe ligger usendt. Uten den dør knappen ved første
              trykk uten dekning. §4.2-invarianten er urørt: det er fortsatt ikke
              *serveren* som utleder handlingen av tilstanden.
            - Usendte stemplinger vises i et eget banner — §6: en knapp som ser ut til
              å ha virket, men ikke har det, er verre enn en som feiler synlig.
      - [x] **Fase 6 — statistikkregisteret + oppdragsfanen (29. aug. 2026).**
            `core/stats.py` med `BaseStatistikkHandler`; `patients/statistikk.py` og
            `oppdrag/statistikk.py` melder seg inn fra `apps.ready()`. Statistikkappen
            navngir ingen kildemodul lenger — endepunktene bærer slug-en
            (`/statistikk/api/kilde/<slug>/full-stats/`), de gamle stiene videresender,
            og cache-nøkkelen bærer både slug og vakt-ID. Pasientfanen ser lik ut.
            - **Tilgangsregelen måtte endres i samme slengen.** §5 sa «vis kun kilder
              brukeren kan lese», men koden ga 403 på hele siden om én kilde manglet.
              Med kilde nummer to ville det tatt statistikken fra alle som leser
              pasienter uten å ha oppdrag. Nå vises de kildene kontoen har, og 403 er
              forbeholdt «ingen kilder i det hele tatt».
            - **§12.2 besvart:** en varighet som slutter i en automatisk stempling
              telles ikke — sluttiden er avledet, ikke målt. Oppdraget telles i antall
              og fordelinger, og både automatiske og negative utelatelser vises på
              siden. Mutasjonstestet: fjernes sperren, blir testene røde.
            - `Statusmelding.objects.gjeldende_bulk()` kom til fordi statistikken går
              gjennom hele vaktas oppdrag. Regelen «nyeste ikke-korrigerte rad vinner»
              står fortsatt bare i manageren; `gjeldende()` er nå ett oppslag i
              bulk-resultatet.
            - **`hent_aktiv_vakt` står igjen som eneste import fra en modul.** Den er
              portalens scope, ikke en kildes tall, og hører til ryddejobben under.
      - [x] **Fase 7 — arkivering (29. aug. 2026).** `AbstractArkiv` i
            `core/arkiv/models.py`, `OppdragArkiv` + `ArkivertOppdrag`, handler,
            egen arkivknapp under `/oppdrag/` og fire endepunkter bak global admin.
            Statistikkendepunktet fra fase 6 virker nå uten at statistikkappen ble
            rørt, akkurat som lovet.
            - **Tidspunktene fryses i flate kolonner**, én per status, og hvilke
              stemplinger som var automatiske ligger som data (`automatiske_statuser`).
              Da gjelder §12.2-regelen i arkivet også — uten flagget ville en avledet
              sluttid blitt telt som målt så snart vakta var arkivert.
            - **`fritekst` arkiveres ikke.** Feltet er unntatt verdilogging i audit
              nettopp fordi det kan inneholde noe en operatør skrev og angret på; å
              fryse det i 24 måneder ville gjort unntaket meningsløst.
            - **Én utregning, to kilder.** `_stats_fra_rader()` regner på nøytrale
              dicter, og både vakta og arkivet bygger slike. En egen arkiv-utregning
              ville drevet fra live-tallene, og forskjellen ville dukket opp først når
              noen sammenlignet i fjor med i år.
            - **To mangler kom for en dag:** modulen hadde ingen backup i det hele
              tatt (nå `oppdrag` + `oppdrag_arkiv`), og `kollaps_arkiv` kjente bare
              pasientarkivet (går nå gjennom registeret, `--modul` avgrenser).
            - Mutasjonstestet: fjernes automatisk-flagget fra arkivet, admin-gaten fra
              endepunktene eller backup-sperren foran kollaps, blir testene røde.

- [ ] **Vaktlistemodulen — se `docs/BESLUTNING_VAKTLISTE.md`.** Bestilt av André
      29. aug. 2026, **besluttet samme dag** i to avklaringsrunder — alle ti
      avklaringene er besvart, kun små restpunkter avgjøres underveis (§11).
      Personelloversikt sortert på korps med kompetanse og rolle; ressurser
      (samleplass, biler, lag, KO) som reserveres til korps og bemannes av korpsene
      selv, med skifttider; drift som reversibel innsjekk-port med møtt/av vakt;
      «Tilstede nå» med utskrift (brukes av brannsikkerhetshensyn ved overnatting);
      planleggingstall (timer, hviletid, bemanningskurve, varsler); besetningspanel i
      `/oppdrag`. Sju faser, 37–49 t.
      - [x] **Fase 1 — registre og mannskap (29. aug. 2026).** App, `Korps`/
            `Kompetanse`/`VaktRolle` som admin-styrte tabeller, `Mannskap` med
            badge (`korps`, PROTECT), kompetanser, valgfri kontokobling
            (SET_NULL) og navn unikt per korps. Django-admin for alle fire.
            Audit for `Mannskap` med `notat` unntatt verdilogging —
            mutasjonstestet begge veier (lekkasje og falske rader).
            Personvernprotokollen hevet til v1.10 med A.6-seksjon og
            A.9-rader. Modulen registrert med `url=None` og flaggene av til
            fase 2. 15 tester.
      - [x] **Fase 2 — oppsettet og planleggingssiden (29. aug. 2026).**
            `Vaktliste` (1:1 med `core.Vakt`), `Ressurs` med reservasjon
            (`korps`, tom = vaktlederens bord) og kobling til `oppdrag.Enhet`,
            `Vaktpost` som **ett skift** med plan (`fra_tid`/`til_tid`) og
            faktisk (`mott_at`/`av_vakt_at`) atskilt. Side på `/vaktliste/`
            med faner bygget av ressursene, «Oversikt» gruppert på korps og
            «Ikke plassert». «Ny planlagt vakt» lager en `core.Vakt` med
            `er_aktiv=False` og **rører ikke** `aktiv_vakt_id`; kopiering tar
            ressursene, aldri personene. Den doble tilgangsregelen står i
            `services.kan_sette_vaktpost()` som én funksjon. Admin-only til
            fase 3. 68 nye tester, åtte mutasjoner prøvd og alle røde.
      - [x] **Registersiden `/vaktliste/registre/` (29. aug. 2026).** Funnet av
            André: registrene kunne bare fylles fra Django-admin, og den flaten
            er av i produksjon (S1) — modulen var i praksis ubrukelig i prod
            uten at én test var rød, fordi alle testene laget radene sine med
            ORM-en. Mannskapsoversikt gruppert på korps med kompetanser, og
            admin for `Korps`/`Kompetanse`/`VaktRolle` gjennom én fabrikk.
            Sletting blokkeres når raden er i bruk (også for `Kompetanse`, der
            M2M-en ikke ville protestert); antall bruk vises i lista.
            `SjekkAtIngenPekerPaaDjangoAdminTests` skanner alle maler for at
            det ikke skal gjenta seg. 43 nye tester.
      - [x] **`rekkefolge` fjernet fra verdimengdene (30. aug. 2026).** Andrés
            innvending, og den var riktig: feltet ga allerede alfabetisk, siden
            hver rad sto på standardverdien. `Ressurs` beholder sitt (styrer
            fanerekkefølgen) men setter det automatisk. Migrasjon `0003`.
      - [x] **Registersiden ryddet (30. aug. 2026).** Fra Andrés bruk av
            modulen: mannskapslista er en tabell med faste kolonner, søk og
            sortering (merkelappene brøt om og skjøv telefonnummeret ut av
            syne), og `Kompetanse.bygger_paa` skjuler impliserte trinn — har du
            AFØR trengs ikke VFØR. Migrasjon `0004`.
      - [x] **Planleggingssiden ryddet (30. aug. 2026).** Ressursen er et
            regneark med rolle, kompetanse, dag og tider som kolonner, redigert
            i raden. Dato + ukedag i tidsvisningen (skift over midnatt var
            tvetydige). «Oversikt» er utskriftslista med knapp og print-CSS, og
            bemanningskurven står over den.
      - [x] **Vaktlengde og ledige plasser (30. aug. 2026).** `Vaktpost.mannskap`
            nullbar — en ledig plass er et skift som mangler en person, og
            planlegging begynner med behovet. Vakta har fått `planlagt_slutt` og
            redigerbar start, og kurven tegnes over hele spennet med fylte mot
            planlagte plasser. Migrasjon `0005`.
            - **Lærdom å ta med til neste modul:** en modul er ikke ferdig før
              dataene den trenger kan opprettes *gjennom portalen*. Django-admin
              teller ikke, og en testsuite som bare bruker ORM-en ser det ikke.
      - [x] **Veien inn i gruppa (30. aug. 2026).** Tiende runde, og den
            handlet ikke om modellen: én `Ressurs` per bil inne i gruppa var
            riktig hele tiden, men det fantes ingen synlig vei dit.
            Gruppefanen har nå eget hode med antall enheter og en
            «Ny <gruppe>»-knapp, tomme grupper forklarer hva de rommer,
            ukoblede enheter viser «Ikke koblet», og ressursgruppene har fått
            en flate i Innstillinger (endepunktet fantes uten UI).
            - **Lærdom:** «det er ikke synlig» er en feilmelding om
              grensesnittet, ikke en uenighet om arkitektur.
      - [x] **Reservasjonen ned på plassen (30. aug. 2026).** Niende runde.
            `Vaktpost.korps` (migrasjon `0008`, additiv): en samleplass kan ha
            plasser satt av til ulike korps. Tom verdi arver ressursens.
            Å reservere krever `skriv_full`. «Sett på vakt» → «Opprett vakt».
            Kurven tegnes også før gruppa har skift.
      - [x] **Fanen er gruppa (30. aug. 2026).** Åttende runde. Én fane per
            ressursgruppe i stedet for per ressurs: «Ambulanse» er alle
            ambulansene, med hver bil som sitt eget kort inni og gruppekurven
            øverst. Enhetskobling, reservasjon og roller blir stående på den
            enkelte ressursen. «Ny ressurs» forhåndsvelger gruppa du står i.
            Innstillinger flyttet til vaktlinja ved «Ny vaktliste», Mannskap
            inn i fanerekka etter «Oversikt» — som lenke med pil, siden den
            forlater sida.
      - [x] **Tidsfeltene på desktop (30. aug. 2026).** `step="300"` på alle
            sju `datetime-local`-feltene: fem minutters steg, ikke ett. Og
            «Opprett vakt» står på vaktas startdato framfor tomt, så bare
            klokkeslettet tastes. Feltet er ellers uendret — native velger og
            visning som før.
      - [x] **«Ingen biler oppkoblet» forklares (30. aug. 2026).** Meldt av
            André. Bilene var koblet i en *planlagt* vakt, og sentralbordet
            scoper til den aktive — scopingen er riktig, men meldingen sa
            bare «ikke koblet». Den navngir nå vakta koblingen ligger i, og
            skiller den fra «ikke koblet noe sted».
      - [x] **Fase 6 — besetning i sentralbordet (30. aug. 2026).**
            `/vaktliste/api/enhet/<pk>/besetning/`, hentet fra nettleseren av
            `oppdrag-sentral.js`. Avhengighetsretningen håndheves med AST
            (`OppdragImportererIkkeVaktlista`). Gatet på `les` i vaktliste.
            Navn, rolle og innsjekkstatus — ikke telefon, kompetanse eller
            notat. Ingen migrasjon. 16 nye tester, ni mutasjoner prøvd.
      - [x] **Fase 5 — planleggingstall (30. aug. 2026).** Fanen
            «Planlegging»: timer, skift, lengste skift og korteste hvile per
            person, sortert på timer. Varsler mot admin-styrte grenser
            (`Belastningsgrenser`, migrasjon `0010`, 12 t / 8 t som standard,
            `skriv_leder` flytter dem). Faktisk-kolonne når stemplene finnes.
            Varsler, ikke sperrer. 45 nye tester, sytten mutasjoner prøvd.
            - Kompetansedekning per ressurs står fortsatt som mulig utvidelse
              i §8b, ikke levert.
      - [x] **Drifttabellen bytter form (30. aug. 2026).** Meldt av André:
            stempelet satt feil. Det var 45×21 px på x=1092 mens navnet sto på
            x=41, bak en sidescroll. Under drift legges planleggingsfeltene
            bort — tidene blir tekst, kompetanse og merknad tas ut — og
            stempelet står først som en 44 px høy knapp. Tabellen ruller ikke
            lenger.
      - [x] **Fase 4 — drift (30. aug. 2026).** Innsjekk-porten
            (`drift/start|stopp`), møtt og av vakt som navngitte overganger
            med reglene som data i `services.STEMPLINGER`, og «Tilstede nå»
            med tellingen stort øverst og utskrift. Korps-føreren stempler
            ikke (avklaring 11.3). Ingen migrasjon — feltene kom i fase 2.
            45 nye tester, sytten mutasjoner prøvd.
      - [x] **Mannskapet flytter inn i planleggingen (30. aug. 2026).**
            Registersiden `/vaktliste/registre/` lagt ned: mannskapet er en
            fane på `/vaktliste/`, korps og kompetanser ligger i
            «Innstillinger» sammen med ressursgruppene. Fanen og vinduet står
            også uten vaktliste — korps må inn før mannskap, og mannskap før
            noen kan settes på vakt. `vaktliste-registre.js` og
            `registre.html` slettet.
      - [x] **«Ny ressurs» spør bare om navn og gruppe (30. aug. 2026).**
            Niende runde. Reservert korps og enhetskobling ute av
            opprettelsesskjemaet — de hører til den enkelte enheten, og settes
            i «Rediger». Nytt felt `Ressursgruppe.flere_enheter` (migrasjon
            `0009`): Samleplass og KO finnes i ett eksemplar, så «Ny
            Samleplass» forsvinner når den ene står der — både knappen i fanen
            og valget i nedtrekket, gjennom `gruppaHarPlass()`, og serveren
            avviser nummer to per vaktliste. Verifisert i nettleseren at en ny
            gruppe ikke oppretter noe i oppdragsmodulen.
      - [x] **Toppen ryddet, tabellen krympet (30. aug. 2026).** Sjuende
            runde. Ressurstabellen ned fra 82rem til 66rem, så den ikke
            ruller over 1280 px, og handlingskolonnen festet til høyre så
            rediger-knappen ikke forsvinner når den likevel ruller. Toppen
            delt i tre: sida, vakta (velger + «Ny vaktliste»), fanene
            («Ny ressurs»). «Vakta» → «Innstillinger». Kurven fjernet fra
            «Oversikt», som nå bare er utskriftslista.
      - [x] **Rediger skift, og kurve per fane (30. aug. 2026).** Sjette
            runde fra Andrés bruk. Blyanten i raden åpner et vindu der
            mannskap, rolle, tider og merknad endres i ett kall — før måtte
            man slette raden og sette den opp på nytt for å bytte person.
            Sletting ligger inne i vinduet med bekreftelse. Bemanningskurven
            står i fanen den gjelder, med klokkeslett under søylene og toppen
            oppgitt med tidspunkt. Døgnskillet står i tegnforklaringen.
      - [x] **Ressursgrupper, ledernivå og rollene inn i ressursen
            (30. aug. 2026).** Femte runde fra Andrés bruk. `Ressurs.type` ble
            tabellen `Ressursgruppe` (migrasjon `0007`), så et førstehjelpstelt
            kan legges til uten deploy; rollene hører til gruppa, ikke til
            portalen, og administreres inne i ressursen. Nytt nivå
            `skriv_leder` (migrasjon `accounts.0015`): `skriv_full` bemanner,
            `skriv_leder` setter opp — oppretter og fjerner ressurser og
            vaktlister, endrer vaktas lengde, lager roller og grupper.
            Sletting av ressurs ligger bak «Rediger» med bekreftelse begge
            veier. Kolonnene: dag inn i tidsfeltene, ny «Timer», kompetansen
            sist. Bemanningskurve per gruppe. Og buggen André meldte:
            klikkdelegeringen fyrte på celler som melder sin egen hendelse,
            så nedtrekket ble revet bort idet det åpnet seg.
            - **Lærdom:** en delt klikkdelegering må vite om elementer som
              melder sin egen hendelse. Feilen så ut som en visningsbug, men
              sendte en tom skriving ved hvert klikk i tabellen.
      - [x] **Ressursroller, og kolonner som blir stående (30. aug. 2026).**
            `VaktRolle` → `Ressursrolle` (migrasjon `0006`, ren `RenameModel`):
            rollen gjelder plassen på ressursen, ikke vakta. Administrasjonen
            flyttet fra registersiden til «Roller» på planleggingssiden, der
            ressursene settes opp, med «i bruk»-telling i lista. Nedtrekket i
            raden tilbyr bare aktive roller pluss den raden alt står på.
            Kolonnebredden målt i nettleseren og rettet: `min-width: 82rem`,
            rebalansert `<colgroup>` og `box-sizing` på feltene.
      - [x] **Alle ti avklaringene besvart 29. aug. 2026** (§11 i notatet er fasit).
            De som endret utformingen: korps er en badge og ikke en ny akse; ressurser
            reserveres til korps og korpsene bemanner sine egne, med tider; drift er en
            reversibel innsjekk-port uten kobling til aktiv vakt; kostbehov utgikk;
            personregistrene i pasientmodulen forblir urørt; kopiering tar oppsettet,
            aldri personene.
      - [x] **Fase 3 — tilgangsmodellen tatt i bruk (29. aug. 2026).**
            `admin_only` av. Badge- og reservasjonssjekk per objekt på hvert
            endepunkt; verdimengdene og utdeling av ressurser er `skriv_full`;
            sletting av en vaktliste er global admin. `korps_id` sjekkes mot
            **begge** korps, og `user_id` er `skriv_full` fordi koblingen
            flytter en badge. Grensesnittet gater på `window.MODUL_TILGANG` +
            badgen, og JS-gatingen kjøres i node. 48 nye tester, tolv
            mutasjoner prøvd.
      - [x] **Korps er en badge, ikke en akse.** `skriv_handling` = fører sitt eget
            korps, `skriv_full` = alle korps **og** den eneste som stempler møtt/av
            vakt (fase 4). Korpset arves fra `Mannskap.korps` via `Mannskap.user`,
            som `Enhet.user` i oppdragsmodulen. Ingen ny verdi i `NIVAA_HIERARKI`.
            - [x] **Prisen betalt: `Module.nivaa_navn`.** Matrisen og «Min profil»
                  viser nå «Skrive: eget korps» på vaktlista og «Skrive: stempling»
                  på oppdrag, der begge før het «Skrive: handling». Nivået er det
                  samme; betydningen er det ikke.
      - [ ] **Matallergi lagres ikke i portalen.** Besluttet fordi det er en
            helseopplysning (art. 9) og ville krevd fem mekanismer for én kolonne.
            Samles inn utenfor. Konsekvensen er ærlig: lista kan ikke brukes til
            matbestilling.
      - [ ] **`notat` på `Mannskap` er fritekst**, og fritekst er der
            helseopplysninger havner når det ikke finnes et felt for dem. Unntas
            verdilogging i audit, som `Oppdrag.fritekst`.
      - [ ] **Registeret blir portalens tredje personregister**, uten kobling til de
            to i pasientmodulen (§9). De svarer på «hvem behandlet pasienten», ikke
            «hvem er på vakt». Prisen: et navn kan stå to steder. En nullbar FK er en
            additiv migrasjon den dagen behovet melder seg.

- [x] **Cron-jobbene sier hva som gikk galt (30. aug. 2026).** To jobber i
      staging falt på feil `DATABASE_URL`; André rettet variabelen i Railway.
      `core/kommando.py::lesbar_dbfeil()` gir nå én lesbar linje framfor fire
      stablede tracebacks, i alle tre jobbene. Og den stille SQLite-fallbacken
      er stengt på Railway: uten den ville `purge_old_logs` rapportert suksess
      mot en tom base og aldri håndhevet lagringstidene i A.9. Seks mutasjoner
      prøvd, alle røde.

- [x] **Migrasjonsprøver mot ekte PostgreSQL (30. aug. 2026).** Punktet het
      «kjør suiten mot PostgreSQL», og den formuleringen var feil: Djangos
      testbase lages mot en *tom* base, så dataskrittet skriver ingenting og
      feilen viser seg ikke. Løst med `core/migrasjonsprover.py` og
      `python manage.py verifiser_migrasjoner` — engangsbase, rader i den
      historiske formen, og påstander om hva migrasjonen gjorde med dem.
      Fem mutasjoner prøvd, alle røde.
      - [ ] **Kjør dem før du pusher en migrasjon som rører data.** De er
            ikke med i den vanlige testkjøringen, fordi de trenger en
            PostgreSQL å lage baser på — lokal installasjon eller en egen
            Postgres-tjeneste i Railway. Se CLAUDE.md.
      - [ ] **Vurder GitHub Actions.** Prosjektet har ingen CI, så «husk å
            kjøre prøvene» er fortsatt hukommelse. En workflow med en
            postgres-service ville kjørt dem ved hver push, uten at noe måtte
            installeres lokalt. Det er den eneste veien som tar disiplinen
            helt ut av hodet.

- [ ] **Norsk sortering av æ/ø/å i vaktlisteregistrene.** Ikke hastverk, og
      kanskje aldri. Sorteringen bruker `Lower(...)`, så store/små bokstaver er
      deterministiske — men Æ/Ø/Å følger databasens kollasjon, og den er ulik i
      SQLite (dev) og PostgreSQL (prod). Merkes først den dagen noen legger inn
      et korps som begynner på Æ, Ø eller Å. Fikses med `db_collation` på
      kolonnen eller en egen sorteringsnøkkel; begge er større enn problemet er
      i dag, med en håndfull korps.

- [ ] **Flytt `hent_aktiv_vakt` ut av pasientmodulen.** Funksjonen er portalens scope —
      `Vakt` bor i `core`, og både oppdrag og statistikk importerer den fra
      `patients.services`. Den ble liggende fordi `AppSetting` (pekeren `aktiv_vakt_id`)
      gjør det, så flyttingen henger sammen med hvor `AppSetting` hører hjemme. Ikke
      hastverk: én import fra én modul, og `StatistikkappenNavngirIngenKilde` har den
      oppført som det ene tillatte unntaket, så den kan ikke gli i glemmeboka.

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
      - [x] **Punkt i runbooken (29. aug. 2026).** §10a navngir begge knappene og
            krever at begge er krysset av før vakta veksles tilbake til
            lavkostnad-modus. Risikoen består til arkiveringene slås sammen, men den
            står nå der den leses.
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

- [x] **`docs/TEKNISK_DOKUMENTASJON.md` — LEVERT 14. sep. 2026**, i to runder. Alle
      punktene under er gjort, og funnene var verre enn kartlagt:
      - [x] Heter nå Sanitetsportalen, og kap. 1 beskriver fire moduler i stedet for én app
      - [x] Alle døde stier rettet (ti stykker), inkludert `core/views.py` og modulene som
            flyttet til `core`
      - [x] `core/backup/`, `core/arkiv/` og de sju registrene er beskrevet (kap. 3.4, 8)
      - [x] Modulregisteret og den ekte nivåstigen står i kap. 4.2 og 6.3
      - **Ikke kartlagt på forhånd, funnet underveis:** kap. 5 dokumenterte 16 av 123
        endepunkter med slettede roller som tilgangskrav; 8B viste en dekoratørsignatur som
        ville gitt `TypeError` og løy om cache-nøkkelen; `_scrub_secrets` var gjengitt med
        feil regex; 8A hadde en hengende tabellrest fra en halvgjort sletting; 13 pekte på
        to endepunkter som ikke finnes; 14 oppga «178 tester».
      - **Alternativet — å merke dokumentet ærlig og la CLAUDE.md være den levende
        oversikten — ble prøvd og forkastet.** Markørene ble satt i første runde, og André
        avviste dem: halvveis verifisert dokumentasjon er verre enn tydelig uverifisert,
        fordi merket forsvinner ved neste redigering. De tiet dessuten
        `core/tests_dokumentråte.py` for hele kapitler.
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

- [ ] **Rate-limit arkivstatistikken.** Tre endepunkter kjører nå samme tunge beregning
      som live-statistikken uten å ha fått en bøtte i S3:
      `/statistikk/api/kilde/<slug>/arkiv/<pk>/full-stats/` (flyttet dit i fase 6),
      `/pasienter/api/innstillinger/arkiv/<pk>/` og — fra fase 7 —
      `/oppdrag/api/arkiv/<pk>/`. Alle er admin-only, uten auto-refresh, og leser rader
      som ikke endres, så eksponeringen er lav. Én linje per view når noen er i filene
      uansett.
- [x] Rydd bort død backup-legacy — gjort 14. sep. 2026 som fase 8 i
      `docs/PLAN_BACKUP_OMLEGGING.md`. Se punktet der.
- [x] **3.6 — de to store JS-filene delt** (14. sep. 2026). `vaktliste.js` 3 801 → fem
      filer, `oppdrag-sentral.js` 1 991 → fire, langs seksjonsmarkørene som alt sto der.
      Fasit over funksjoner og bindinger tatt **før** flyttingen; ingen mangler, ingen
      dubletter. `core/tests_js_splitt.py` håndhever at det holder.
      - [x] **Regelen for rekkefølgen er «alt som kjører på toppnivå står sist»**, ikke
            «all tilstand først» — `let`/`const` er skript-scopede og deles mellom filene.
            Jeg skrev først det siste i malen, og det var feil.
      - [x] Prøvd mot tre mutasjoner: duplisert funksjon, toppnivåkall i kjernen, og
            ombyttede `<script>`-tagger. Alle faller.
- [x] **3.8 — tester som målte kode, ikke oppførsel** (14. sep. 2026). Fem skrevet om;
      resten av treffene var legitime (XSS-skannere som *finner* en bygger, regler uten
      kjøretid). Tre ble bedre, ikke bare mindre skjøre. Mønsteret står i `CLAUDE.md`.
      - [x] **Ekte flake funnet og rettet:** `test_sletting_strupes` feilet én gang av
            mange. `django_ratelimit._get_window` legger vinduskanten et fast antall
            sekunder inn i hvert minutt, jittret per nøkkel — tolv forsøk mot `10/m` som
            straddler den, deles i to bøtter der ingen når ti. Forsøkene er nå
            2 × grensen + 1.
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

- [x] **Sikkerhetssjekk utenfra (13. sep. 2026).** `scripts/sikkerhetssjekk.py`, runbook §14.
      - [ ] **Krever Andre:** kjør scriptet mot staging med admin-, leser- og enhetskonto og lim
            inn rapporten.
- [x] **Statisk sikkerhetsgjennomgang (13. sep. 2026)** — `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.
      - [x] Runde 1 (H1, H2, H4, M1–M11, L2, L3, L5, L10, L11) — 13. sep. 2026, se CHANGELOG
            - [x] `SECRET_KEY` i Railway er minst 50 tegn (L10) — André sjekket prod 13. sep. (prodtest 8.1 OK).
      - [x] Runde 2 (H3 vendor CDN + CSP, M12–M16, L1, L13, L14) — 13. sep. 2026, se CHANGELOG.
            M14: brukernavn-røpingen er tettet; låsen er fortsatt global per konto (bevisst — den
            er vernet som ikke hviler på cachen). Utestengelse av andre ved å gjette mot navnet
            deres står under «senere».
      - [x] Prodtest av runde 1 og 2 på staging (13. sep. 2026): scriptet 39 OK / 0 FEIL.
            Fire funn på sidene rettet samme kveld — fanikonet tilbake på blått, sentralbordets
            oppstart, 3 s før «venter på dekning», korps-føreren uten badge — og
            e-postkoblingen snevret til leder og admin. Se CHANGELOG.
            - [ ] **Krever Andre:** test de fem på staging (artifacten), så «Backup tatt — push til
                  main», og prodtest 8.2/8.3 etter deployen.
      - [ ] Senere: L6, L8, L12, L17, L18, L22
- [x] **Server-status utvidet (13. sep. 2026).** Minne nå + topp, offsite, disk,
      database (svartid, tilkoblinger), vaktbildet, tregeste stier, konfigsjekk,
      innlogging siste time, cron-jobbenes siste kjøring, e-posttransport. Feature-flagg-kortet
      og flagg-endepunktet er fjernet. Se CHANGELOG.
      - [x] Første funn: `RATELIMIT_ENABLE=true` ble lest som False (13. sep. 2026, se CHANGELOG).
      - [ ] **Krever Andre:** etter deploy, åpne `/portal-admin/server-status/` i prod
            og se at konfigsjekk-kortet sier «alt OK» og at offsite står grønt. Cron-radene
            står «Aldri» til hver jobb har kjørt én gang etter deployen — sjekk igjen
            dagen etter at de tre viser ✓.
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
