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

**Et ferdig punkt krysses ikke av — det fjernes** (André, 16. sep. 2026): «vi sletter.
Du skal jo legge inn hva du gjorde i CHANGELOG, og det som står i TODO og det som ble gjort
kan bli to ting med forskjellig vri. **CHANGELOG blir arkivets sannhet.**» Historien
skrives i CHANGELOG i samme commit som endringen, jf. arbeidsflyten i `CLAUDE.md`, og
punktet forsvinner herfra. Fila beskriver bare det som gjenstår.

Grunnen står i tallene fra ryddingen: **1 316 av 2 495 linjer — 53 % — beskrev arbeid som
var gjort.** Jeg lette etter 858 linjer inne i 2 495. Og 23 åpne punkter hadde havnet under
avkryssede foreldre, seks av dem ting som ventet på André. To regler i
`core/tests_todo.py` holder nå begge deler.

**Toppseksjonen er sann.** Alt som venter på André står der, og bare det som blokkerer *nå*
— et åpent valg inne i en upåbegynt idé hører ikke hjemme i en liste han skal kunne handle
på.

---

## ⚠️ Krever Andre — kan ikke gjøres fra kodebasen

Disse står ikke i kode. De krever Railway-innlogging eller en avgjørelse utenfor
prosjektet, og blir liggende til du gjør dem. Ingen av dem oppdages av testsuiten, og
ingen av dem gir feilmelding — de er bare stille inaktive.

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

- [ ] **Prosjektleders tilbakemeldinger — resten** (planlagt 11. sep. 2026,
      rekkefølgen er avtalt med André):
      - [ ] **Flere enheter på ett oppdrag** — besluttet 11. sep. 2026:
            `docs/BESLUTNING_FLERE_ENHETER_PER_OPPDRAG.md`. §7 besvart, §9 kom
            til: sentralbordet fører status manuelt, også på ferdige oppdrag
            innen 48 t (forslag). Fire trinn; backup før deploy.
            - [ ] **Andrés forbedringsliste 12. sep. (staging først):**
            - [ ] **Å tenke på (André, 12. sep.):** bilen ser nå de andres stempler
                  (avgjort 12. sep.). Sentralbordets besetning følger lista i drift
                  (avgjort 12. sep.). Skal bil 2, som ikke tar med
                  pasienten, få sette/se grovsorteringen? Adminkontoer er aldri
                  mannskap (avgjort 12. sep.: «Den er utenfor.»).
            - [ ] Deploy 2, senere: fjern `Oppdrag.enhet`, `Statusmelding.oppdragsenhet`
                  NOT NULL (med `SET CONSTRAINTS ALL IMMEDIATE` om et dataskritt går
                  foran), og broene i `Oppdrag.save()`/`Statusmelding.save()` bort.
                  Backup før — og la prod gå noen vakter med broene først.
      - [ ] **Stripe på blokklinja** (mini-Gantt over vaktas spenn) — alternativ
            «Begge deler» i spørsmålet 11. sep.; valgt bort for nå, lett å
            legge til siden blokka alt bærer spennet.

- [ ] **Første skarpe vakt med oppdragsmodulen.** Modulen er ferdig og testet, men
      aldri brukt under en reell vakt — og det er den prøven som finner det ingen
      testsuite gjør: samband, dekning i felt, og om knappene sitter der hendene
      forventer dem. Ha `docs/RUNBOOK_VAKT.md` framme; §10a har nå **to**
      arkivknapper å krysse av ved vaktslutt.

- [ ] **Scaleway-kortet på `/portal-admin/backup/` skal stå grønt i prod.**
      `_prefiks()` leste ikke `Filter.And.Prefix`, og meldte «filene blir liggende for
      alltid» om en livssyklusregel som sto helt riktig (rettet 15.–16. sep. 2026).
      Er kortet fortsatt rødt, bærer meldinga nå **koden Scaleway faktisk svarte** — og
      den avgjør om det er rettigheter eller vår kode.

- [ ] **Verifiser pulje 2 i prod** (bygg `a7239c5`, deployet 16. sep. 2026). Sju punkter,
      i CHANGELOG under «Pulje 2, andre halvdel» — kort versjon: sett flaggene på
      «Spesialressurs» i Valglister, sett en lege passiv, varsle henne, og se at brikka
      sier «(passiv vakt)» også etter at hun er satt aktiv igjen. Og: at hver enhet i
      ressurslista viser rent navn, uten `[object Object]`.
      Migrasjon `0026` er rene tillegg — to felter på `Enhetstype`, ett på `Enhet`,
      `Oppdragsenhet` og `ArkivertOppdrag`, og tabellen `Vaktmodusperiode`. Ingen
      eksisterende rad endres, og ingenting av det vises før flaggene er krysset av.

- [ ] **André: Scaleway IAM-applikasjon.** Policy med
      ObjectStorageObjectsWrite/Read og BucketsRead — **ikke delete**, fristene skal
      håndheves av bucketens livssyklusregel og ikke av oss. API-nøkkel,
      `OFFSITE_BACKUP_KEY` i en passordbehandler *utenfor* Railway, og de seks
      variablene på prod-tjenesten.

- [ ] **Prøv gjenopprettingen fra Scaleway én gang** når variablene står:
      `railway ssh --service web -- python manage.py hent_offsite --list`, hent én fil,
      og se at den dukker opp under `/portal-admin/backup/`. En backup som aldri er
      hentet tilbake er en antakelse, ikke en backup.

- [ ] **André: bekreft at AHASend-kontoen ikke står på US-infrastruktur.** Standard er
      EØS, men Hetzner US er tilgjengelig «upon request». Er den valgt, utløses
      SCC-sporet og A.2 i personverndokumentasjonen må beskrive en tredjelands­overføring.
      Ett blikk i AHASend-konsollen.

- [ ] **Vurder å slå av lagring av e-postinnhold hos AHASend.** Avtalen sier det kan
      deaktiveres. Feilvarslene inneholder brukernavn, rolle, klient-IP, URL og
      traceback — jo mindre som ligger lagret hos databehandleren, jo bedre.
      **Merk til A.12:** avtalen sier «Controller agrees not to use the Services to send
      or store Sensitive Data». Feilvarselet inneholder personopplysninger, men ingen
      helseopplysninger — skjemadata, cookies og lokale variabler ble slanket bort
      22. aug. 2026, og `core/tests_error_reporting.py` vokter det. Den testen er dermed
      ikke bare en personvernfinesse; den holder oss innenfor en kontraktsforpliktelse.

- [ ] **Deploy 2 til prod — krever din avgjørelse.** `role` krympet til `admin`/`bruker`.
      Etter migrasjonen er `ModulTilgang` eneste fasit: en rollback av deploy 1 kan da
      ikke lenger bygge matrisen på nytt fra `role`.

- [ ] **Deploy 3 til prod.** De fem `kan_redigere_*`-flaggene fjernes. Kan gå rett etter
      deploy 2 — de to rører ikke samme kolonne, og flaggene er tomme uansett.

- [ ] **Etter deploy til prod: gå gjennom tilgangsmatrisen.** Alle som hadde `les` ser nå
      bare sitt eget korps — den som skal samordne må få `les_alle`. Og kontoer med
      `les`/`skriv_handling` uten mannskapsrad ser ingenting før de er koblet.

- [ ] **Etter deploy: åpne `/portal-admin/server-status/` i prod** og se at
      konfigsjekk-kortet sier «alt OK» og at offsite står grønt. Cron-radene står «Aldri»
      til hver jobb har kjørt én gang etter deployen — sjekk igjen dagen etter at de tre
      viser ✓.

- [ ] **Backup: test de fem handlerne på staging**, så «Backup tatt — push til main», og
      prodtest 8.2/8.3 etter deployen.

- [ ] **Bekreft cron-radnivået med egne øyne ved anledning:**
      `railway ssh --service web -- python manage.py shell -c "from core.models import Notification; print(Notification.objects.count())"`
      → forventet `1`. Loggen fra containeren er allerede beviset; dette er et ekstra
      blikk, ikke et krav.

- [ ] **Databasen før og etter neste vakt — runbook §8a.** Før: kjør `railway status`
      (bekreft *production*), så `SELECT pg_stat_reset();` i psql (§1c steg 6). Etter,
      før arkiveringen: steg 3 og 4 i §8a, og send utskriften til Claude. Første
      avlesning 25. sep. 2026 var fra **staging** og viste ingen manglende indekser;
      bruken i prod er ikke sett — derfor en runde der, med ekte vakttall.

## Pågående / neste

### Kodegjennomgangen 25. sep. 2026 — se [`docs/PLAN_TEKNISK_GJELD_2026-09-25.md`](./docs/PLAN_TEKNISK_GJELD_2026-09-25.md)

*Hele appen lest på staging `7c21318`. Alt unntatt C1 finnes også i prod (`main`
`636e1f2`). Funnene, begrunnelsene og «ferdig når» står i notatet; her står bare puljene,
i den rekkefølgen de skal tas. A1 må tas før deploy 2 i oppdragsmodulen.*

- [ ] **KO-loggen får ingen «varslet»-linje for den nye bilen ved flytt i Venter.** Raden
      pekes om (A4, 26. sep. 2026), og `enhet_varslet` i `ko/signals.py` fyrer bare på en ny
      rad. Var slik før også. Enten et eget signal på `Enhetsbytte`, eller at KO leser
      byttet — KOs sak, ikke oppdragsmodulens.
- [ ] **Pulje B — spor, tilgang og lekkasjer.** B1, B2, B6, B7 og B8 levert 26. sep.
      Igjen: vaktlistas audithull (B3); `accounts/admin.py` (B4); `sikkerhetssjekk.py`
      mangler KO og backlog (B5).
- [ ] **Pulje C — avgjørelser.** C1 og C2 levert 26. sep. Igjen: C3: `Patient.is_active` inn eller ut. C4: `Vaktpost.avmeldt_at` — ett
      predikat for «på vakt», eller fjern feltet.
- [ ] **Pulje D — verifiseringen.** CI med PostgreSQL og node, og manglende node skal feile,
      ikke hoppe over ~160 tester (D1, erstatter «Vurder GitHub Actions»); død kode som
      testene holder i live (D2); XSS-skanner for `backlog.js` og `+`-uttrykk (D3);
      `backup_enabled`, `/api/`-fanger-alt og `createcachetable` (D4).
- [ ] **Pulje E — duplisering som alt har glidd.** Pasientstatistikken regnet to ganger
      med ulike svar (E1); verdilistefabrikken i KO og oppdrag (E2); arkivverifiseringen i
      `patients/views_arkiv.py` (E3); tilgangsgatene (E4); småhjelperne (E5); vasking og
      helseprober (E6).
- [ ] **Pulje F — dokumentasjon som motsier koden.** Tilgangsdocstrings i vaktlista og
      `accounts` (F1); audit-avsnittet i rot-`CLAUDE.md` er feil (F2); TODO-punkter som er
      gjort eller dobbelt (F3); ~40 utdaterte kommentarer, tas i forbifarten (F4).
- [ ] **Pulje G — struktur, når man er i filene.** Rammeverket i `patients` til `core` (G1);
      store filer (G2); pasientsidens eget skall (G3); N+1 i pollede endepunkter (G4);
      `requirements.txt` kompilert for 3.11, SW-cachen, polling i skjulte faner (G5).

*De tre vaktlisteønskene under henger sammen — to av dem trenger samme dagruppering.
Sammenhengen, rekkefølgen og de åpne valgene står i
[`docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md`](./docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md).*

### KO med fem operatører — flyten André beskrev 24. sep. 2026

*Kjernetid: 2 på utalarm (ressursoversikt, oppdragsliste, hendelseslogg), 2 på tavla
(hendelseslogg, tavle), 1 KO-leder som rullerer mellom hendelseslogg, tavle og
konsertplanlegger. Utenom kjernetid 2 som dekker alt. Minst to skjermer per plass.*

- [ ] **Endringsnummeret videre, når det trengs.** Tavla, loggen og sentralbordet følger det
      (24. sep. 2026). Tre ting står utenfor med vilje: bilens skjerm (egen polling hvert
      15. s — å følge `oppdrag` ville hentet ved hver endring i hele vakta), konsert-
      planleggeren (60 s) og pasientene (bare hvis sykestua ber om det).
      Kollisjonssperren på tavla (409 «Per flyttet Lag 3 for 4 s siden») venter til dere
      har sett om «Per · nå»-merket er nok.
- [ ] **Oppsett per rolle** under «Oppsett»: Utalarm, Tavle, KO-leder, Liten bemanning —
      per skjerm, siden hver plass får to. Mulig kobling til Ansvar-nedtrekket
      (`ko.Ansvarsomraade`). To ting er ikke avklart og avgjør oppsettene: hvem fører
      loggstrømmen i kjernetid, og hvem trykker «Flytt nå».
- [ ] **Mål KO-trafikken på staging** og før tallene inn i runbook §3c — i dag står KO
      der som «ikke målt ennå». KO-endepunktene har ingen ETag.

### KO: hvem som planlegger på tavla — kan strammes inn (André, 23. sep. 2026)

- [ ] **«+ Planlegg» er `skriv_full` i KO i dag** — André: «Alle i første omgang, kan være vi
      strammer inn på det». Porten sitter i `tavle_pauser_view` og `tavle_pause_view`
      (`ko/views.py`); skal den bli KO-lederens, er det `_kan_lede_ko(request)` der og
      `koKanFjerne()` for knappen i `koTavleRadHtml`. «Flytt nå» bør da fortsatt være
      `skriv_full` — å trykke er å føre tavla, ikke å planlegge.

### Oppdragslista: endre verdier rett i lista — venter (André, 23. sep. 2026)

- [ ] **Hastegrad, problemstilling, lokasjon og tildelt ressurs rett i oppdragslista**,
      som det nå gjøres inne i oppdraget (levert 23. sep. 2026, se CHANGELOG). André:
      «avvent litt». Tre feller oppdragsvinduet ikke har: lista tegnes på nytt ved hver
      polling (et åpent nedtrekk forsvinner), hele raden er en knapp som åpner oppdraget,
      og et feilklikk på en travel liste endrer et oppdrag uten at noen ser det. Brikkene
      og reglene i `oppdrag-sentral-oppdrag.js` (`_verdiKanEndres`, `_verdiForesporsel`)
      kan gjenbrukes; det som mangler er en tegning som tåler pollingen.

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

**Fjorten avklarte spørsmål** (notatets §6): åtte fra gjennomgangen 15. sep. 2026, tre til
da koden ble lest før byggingen begynte, og tre under byggingen selv. Kort:
timetallet er et **tak som varsler**; **ett tak for hele vakta**, med en dagslinje uten egne
tak; timer føres på **startdagen**, ikke splittet ved midnatt (det er rapportmodulens regel,
og forskjellen er bevisst); generatoren lager **bare tomme plasser**; ny generering
**erstatter tomme plasser, men beholder de korpsreserverte og alle bemannede**;
budsjettlinja viser **satt opp og bemannet side om side**; taket **kopieres** av
`kopier_oppsett`; og **overlapp-punktet løses først**. Og de tre siste: **probono teller
ikke mot taket, men vises for seg**; genererte plasser **fødes som planlagt kladd**; og
**«åpen for alle»-plasser overlever** en ny generering — regelen blir da at generatoren
bare rører det `services.er_planlagt()` kaller kladd. Og de tre siste, tatt under
byggingen: budsjettlinja bor i fanen **«Planlegging»** som alt finnes; taket er
**`skriv_leder`**; og budsjettallene sendes **bare til den som ser alle korps**, fordi de er
hele vaktas og ellers ville vært et aggregat over skift man ikke får se.

Rekkefølgen under er notatets §7. **Steg 1–4 er gjort** (15. sep. 2026); bare kurvene
side om side står igjen.

**Rekkefølgen ble snudd underveis.** Notatet hadde generatoren sist, «i sin enkleste
form» — men den er ikke en fotnote til budsjettlinja, den er funksjonen som ble bestilt.
Se beslutning 15–17 i notatet.

- [ ] **Bildet av vakta:** bemanningskurvene per gruppe ved siden av hverandre over
      `_vaktensSpenn()`, så hull og topper er synlige mens man legger inn.
      **Verdt å vurdere på nytt:** kurvene finnes alt per gruppefane, og verdien var «se
      hull og topper mens du legger inn» — det er først nå, med generatoren på plass, man
      vet hva man vil se etter.
- [ ] **XSS-skanneren ser bare `${…}` inne i template-literaler, ikke `+`-konkatenering.**
      Funnet 15. sep. 2026 mens planleggerbyggerne ble registrert: `mkPlanlegger()` og
      `mkBelastning()` avslutter begge med `hode + \`…\` + linjer + tomt`, og de
      konkatenerte leddene går forbi `REVIEWED_INTERPOLATIONS` uten et ord. Verdiene der
      er lokalt bygget markup i begge tilfeller, så det er ikke et hull i dag — men
      regelen dekker mindre enn den ser ut til å gjøre, og det er nøyaktig sorten feil
      `accounts/decorators.py` hadde (en test som bare dekket halve syntaksen, grønn i et
      år). Utvid skanneren til å følge `+`-uttrykk, eller skriv byggerne om til ett
      template-literal.

- [ ] **Skriv midnattsregelen inn i `docs/FORSLAG_RAPPORTMODUL.md` §2.2 også.** Den står i
      `CLAUDE.md` for `_dagnokkel()` og i planleggernotatets §3.3; rapportmodulen er det
      tredje stedet noen leser den, og den som leser bare der må se at forskjellen er
      bevisst.

### Vaktlista: overlappende skift — funnet 14. sep. 2026

*Funnet mens vi diskuterte rapportmodulen, men punktene hører hjemme i vaktlista og er
uavhengige av om rapporten noen gang bygges.*

- [ ] **Vurder en sperre, men ikke i databasen.** `test_overlapp_paa_tvers_av_ressurser_stoppes_ikke`
      dokumenterer at dette er bevisst: «noen ganger står man på to lister». Å sperre det
      i basen krever `ExclusionConstraint`, som **ikke finnes i SQLite** — da er suiten
      grønn lokalt mens prod oppfører seg annerledes, nøyaktig fella fra 30. aug. 2026.
      Riktig sted å nekte er ved **frysing** av en liste som skal bli fakturagrunnlag, ikke
      ved planlegging der overlappet bare er informasjon.

**Hvorfor dette betyr noe utover planleggingen:** et overlapp blåser opp timesummen.
Målt 14. sep. 2026 — skift 12:00–20:00 (8 t) og 16:00–22:00 (6 t) på samme person gir
`timer = 14.0`, mens personen var til stede i 10 timer. Tallet er fortsatt 14 — summen
er ikke endret, den er **navngitt**: `overlapp` sier at fire av dem er dobbeltbooket, og
planleggeren retter det framfor at tallet stille korrigerer seg selv. «Varsler, de sperrer
ikke» gjelder her også. Se `docs/FORSLAG_RAPPORTMODUL.md`.

- [ ] **Timer har ingen dagdimensjon.** `_timer()` er ren varighet; fredag 20:00 → lørdag
      04:00 gir 8,0 timer uten at koden har noe begrep om hvilken dag de tilhører.
      Trengs først når noe skal vise timer *per dag* — og det gjør planleggerens dagslinje.

      **Svaret er ikke ett, og det er avklart 15. sep. 2026** (planleggernotatet §3.3,
      beslutning 7). Dette punktet sto tidligere som «altså splittes skiftet ved midnatt»,
      og det var for kjapt:

      | Spørsmål | Regel |
      |---|---|
      | Hvem er på vakt den dagen? (vaktlista, planleggerens dagslinje) | **Startdagen** — `_dagnokkel()` |
      | Hvor mange timer skal betales for det døgnet? (rapportmodulen) | **Splittes ved midnatt** |

      Forskjellen er bevisst. Splitting endrer ikke en totalsum — fredag 20:00 til lørdag
      04:00 er åtte timer uansett — den endrer bare hvilken dag de føres på, og da må
      valget følge hva tallet skal svare på. Trenger man time-for-time-bildet, er svaret
      bemanningskurven, som bøtter per time og tegner midnatt som egen strek (`vl-dogn`).

### Funn fra staging-verifiseringen 14. sep. 2026

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

*Samlet her med vilje: begge lå opprinnelig som uavkryssede barn under avkryssede
foreldre, og et punkt som står under noe ferdig er et punkt ingen leser igjen.*

- [ ] **Kontoopprettelsen lager en `oppdrag.Enhet`.** Funnet 14. sep. 2026, ikke i
      gjeldskartet. Kontotypen «bil» validerer enhetsnavnet i `accounts/forms.py` og
      oppretter/gjenoppliver raden i `accounts/views.py`. Samme slags kobling som 3.1,
      men en annen form: det er *selve opprettelsen* som får en sideeffekt i en modul,
      ikke et skjema ved siden av. Hører hjemme i `core/kontokobling.py` med en
      lagringskrok — men det er kirurgi i brukeropprettelsen, og den skal ikke gjøres
      i forbifarten. Står i `KJENTE_UNNTAK_RAMMEVERK`, som ikke skal vokse.

### Manuell testgjennomgang av `/ko` og `/vaktliste` — 19. sep. 2026

Sjekklistene finnes; de er ikke kjørt. Suiten svarer på om reglene holder, sjekklistene på
om flata gjør det — markup, låser, telefon, offline og sammensetningen av tre moduler i én
nettleser.

- [ ] **Kjør [`docs/TESTSJEKKLISTE_KO.md`](./docs/TESTSJEKKLISTE_KO.md) på staging**, med de
      fem kontoene §0 beskriver. Nivåene er halve lista, og de kan ikke prøves med én
      konto: global admin er nettopp den brukeren som aldri møter en sperre. Funn føres i
      CHANGELOG med byggnummer.
- [ ] **Kjør [`docs/TESTSJEKKLISTE_VAKTLISTE.md`](./docs/TESTSJEKKLISTE_VAKTLISTE.md) på
      staging**, og ta §6 (låste felter) og §13 fra en iPhone eller iPad. De punktene
      finnes bare der — `readonly` er uten virkning på `datetime-local`, og Safari
      ignorerer `color` på et deaktivert felt. Funn føres i CHANGELOG med byggnummer.

### Teknisk gjeld — kartlagt 13. sep. 2026

Underlaget er `docs/TEKNISK_GJELD.md`; det forklarer hvorfor. Rekkefølgen her er
bindende: 1 før 2, fordi backupen speiler hvor modellene bor.

> **Rekkefølgen foreslått justert 13. sep. 2026** — se
> `docs/PLAN_REKKEFOLGE_2026-09.md`: det av punkt 2 som *ikke* rører `AppSetting`
> (`vaktliste`-handler, `core.Vakt` i egen portalfil, gjenopprettingstesten i tom base,
> 3.4 og omdøpingen) tas **før** flyttingen, så prod har en gjenopprettbar backup foran
> tilstandsmigrasjonen. Hel backup og `AppSetting` i portalfila tas etter. KO-modulen
> (som erstattet datteroppdrag, 17. sep. 2026) og statistikk-utvidelsen står etter
> dokumentrunden og etter første skarpe vakt med oppdragsmodulen.

- [ ] **3. Dokumentrunden — når 1 og 2 er levert.** Én runde, ikke stykkevis, og den tar
      med seg **alt fra 11.–13. september** (sikkerhetsrundene, server-status, reserve og
      offline, offsite, flere enheter per oppdrag, ISSI og besetning, audit i vaktlista,
      lyd og bilens utganger). Lista over hva som mangler hvor står i `docs/BACKUP.md` §5:
      - [ ] ~~§8b med hel backup og gjenoppretting i tom base~~
            (`BACKUP.md` §4), inkludert `purge_old_logs` + `kollaps_arkiv` rett etterpå
      - [ ] `docs/PERSONVERN_DOKUMENTASJON.md` — A.2 (Scaleway: hele databasen), A.9 (hel
            backup 90 dager, modulfilene 730 dager offsite), A.10, A.11/A.6 (fil på e-post,
            offline drift)
      - [ ] `CLAUDE.md` — backup-avsnittet og hvor modellene bor
- [ ] **Merk resten av CHANGELOG — 182 av 280 entries står uten søkeord.**
      13.–17. sep. er gjort (97 entries, 15 temaer); halen er 29. aug. og bakover.
      `python manage.py changelog --umerkede` viser hva som gjenstår.

      **Det haster ikke, og det er verdt å si hvorfor:** de merkede er de siste fem
      dagene, som er der oppslagene faktisk gjøres. For halen duger `manage.py changelog`
      alene — 280 titler mot 11 651 linjer. Ta den når du likevel er inne i en gammel
      entry.

      **Merk med en eksplisitt tittel-til-tema-tabell, ikke nøkkelordsgjetting**, og la
      skriptet kreve at hver tittel i tabellen finnes — ellers blir en skrivefeil en
      stille ikke-merking. Mønsteret ligger i CHANGELOG 17. sep.

      Temaer som ennå ikke finnes, og som halen trolig trenger: `patients/registrering`,
      `patients/arkiv`, `patients/registre`, `statistikk/kilder`, `oppdrag/verdimengder`,
      `oppdrag/arkiv`, `vaktliste/besetning`. **Registrer dem i `TEMAER` i samme commit
      som du merker entriene**, aldri foran — testen håndhever rekkefølgen.

- [ ] **Rota har ~170 tegn igjen av taket på 65 500.** Den traff taket 17. sep. under
      konsollayouten og ble komprimert på stedet — det holdt denne gangen, men neste
      avsnitt gjør det ikke. `CLAUDE.md` er 64 843 tegn etter
      Neste modul som trenger et avsnitt i rota sprenger den, og da står man med valget
      midt i en annen oppgave. Det som skal
      flyttes er avsnitt som beskriver **én** modul — regelen fila selv setter — og den
      eneste kandidaten som er igjen er backup-tabellen med ni rader, der hver rad
      forklarer sin egen modul. Vurderes før neste pulje, ikke under den.

- [ ] **Samme feilklasse som gjenopprettingsrekkefølgen, andre steder.** Rekkefølgen sto
      skrevet ut fire steder og tre gikk i utakt uten at noe ble rødt, fordi
      `core/tallfasit.py` dekker tall og ikke ordnede påstander. Gå gjennom dokumentene
      etter andre påstander som er **utledbare men ikke utledet**: nivåstigen (`les` <
      `les_alle` < …) står i rota, i matrisen og i minst to modulfiler; lasterekkefølgen
      for de delte JS-filene står i både rota og malene. Mønsteret er
      `core/backup/rekkefolge.py`: fasit i kode, og en test som leter etter setningen i
      stedet for å ha en liste over hvor den står.

- [ ] **Strukturér `oppdrag/CLAUDE.md`.** 17 275 tegn under **én** overskrift — samme
      flate vegg vaktlista hadde, bare mindre, og den eneste fila som står i
      `UTEN_SEKSJONER_I_DAG` i `core/tests_claude_md.py`. Statusmaskinen, verdimengdene,
      bilens utganger og historikk-mot-arkiv er fire ting.

      **Gjør det som med vaktlista: flytt, ikke skriv om.** Skriptet som gjorde det
      beviste at hver setning var bevart ved å sammenligne mengden av linjer før og
      etter. Det er den eneste måten å gjøre en slik omstokking uten å risikere at en
      regel forsvinner i redigeringen.

- [ ] **Vurder om `vaktliste/CLAUDE.md` kan krympes — seksjon for seksjon.** Fila er
      strukturert (17. sep. 2026) og delt (23. sep.: flaten til
      `templates/vaktliste/CLAUDE.md`), men ikke kortet ned; den er 44 641 tegn og står
      fortsatt pinnet i `FOR_STORE_I_DAG` — taket ble hevet 800 tegn 25. sep. for
      overnattingen, med begrunnelsen i testen. Kutt var **ikke** riktig den dagen, og grunnen bør
      stå: hvert avsnitt bærer en regel *og* feilen som lærte oss den, og det er
      begrunnelsen som får reglene til å feste seg. En kortere fil med dårligere
      dokumentasjon er ikke en forbedring.

      Det som *nå* er mulig, og som ikke var det før, er å vurdere én seksjon om gangen
      mot CHANGELOG: står hele hendelsesforløpet der, kan modulfila nøye seg med regelen
      og den ene setningen som gjør den huskbar. De tre største er «Plassen og skiftet»
      (7 802), «Planleggeren» (6 229) og «Belastning, budsjett og timeoversikt» (5 736).

- [ ] **4. De mindre** (§3 i notatet), når man er i nærheten: brukeradmin importerer
      pasientregistrene (3.1), `/portal-admin/` samlet i én URL-fil (3.2), skimene
      (3.3), `core/views.py` delt (3.7). 3.5 (`VaktArkiv`) skal **ikke** ryddes —
      signaturen. 3.6 og 3.8 tas underveis, ikke som egne runder.

### GDPR-gjennomgang

Fase 0–5 er gjennomført. Begrunnelsene og de varige beslutningene ligger i
[`docs/PERSONVERN_DOKUMENTASJON.md`](./docs/PERSONVERN_DOKUMENTASJON.md); hva som ble gjort
står i [`CHANGELOG.md`](./CHANGELOG.md). Tre punkter gjenstår:

- [ ] Fyll inn organisasjonsnavn i A.4 — se «Krever Andre» øverst

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

- [ ] **Personverndokumentasjonen: vaktlista på e-post inn i A.2/A.6.** Utsendingen av
      vaktlista som fil (`vaktliste/fil.py`, 12. sep. 2026) er en dataflyt ut av
      systemet som ikke er beskrevet. Formål: «reserve ved bortfall av portalen».

### Forbedringsbacklog

Kodegjennomgangen fra 12.–13. august 2026 fant 28 punkter (N1–N13, S1–S7, F1–F9).
**25 er gjennomført** — hva som ble gjort og hvorfor står i `CHANGELOG.md` under
13.–23. august. Det som står igjen er listet under, i dokumentets egen rangering.

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

### Vaktlista: overnatting — videre (25. sep. 2026)

Overnattingen og brannlista er levert (se CHANGELOG 25. sep. 2026 og
[`vaktliste/CLAUDE.md`](./vaktliste/CLAUDE.md)). To ting er bevisst holdt utenfor:

- [ ] **Opptelling på mobil under alarm.** Avhuking per person på telefonen, med tall
      som går ned mot null. Valgt bort for nå — André: «vi printer ut», og papiret er ofte
      raskere enn en skjerm i et trappeoppgang. Tas opp igjen hvis en ekte vakt ber om
      det; da må den virke offline, og køen i `vaktliste-offline.js` er stedet å starte.
- [ ] **«Kopier rom fra forrige vakt».** Rommene er per vaktliste, så samme skole hvert
      år betyr at rommene skrives inn på nytt. `services.kopier_oppsett()` kopierer alt
      ressursene; rommene kan følge samme vei — **aldri** plasseringene, av samme grunn
      som den aldri tar personene.

### Kartmodul med værlag — se [`docs/FORSLAG_KARTMODUL.md`](./docs/FORSLAG_KARTMODUL.md)

**Forslag, ikke besluttet — og ikke i år** (23. sep. 2026). Kilder og arkitektur er
utredet, så arbeidet ikke gjøres på nytt. André har valgt **MET, Kartverket og
NVE/Varsom** — 0 kr i data. Nødfall uten nett er utenfor første versjon.

- [ ] **Modulen `kart/`** med Leaflet vendret under `static/vendor/`, topografisk og
      gråtone bakgrunnskart fra Kartverket, og kildehenvisning som vannmerke nede til
      høyre. Krever ett smalt tillegg i CSP-ens `img-src` (`cache.kartverket.no`) —
      uten det er kartet grått uten feilmelding (§4.1).
- [ ] **Værdata hentes av serveren, med cache** — MET krever identifiserende
      `User-Agent`, som JavaScript ikke kan sette. Vindpil per lokasjon (husk at
      `wind_from_direction` er *fra*-retningen, pila roteres 180°), nedbørsmengde fra
      Locationforecast og neste 90 minutter fra Nowcast (§3.1, §4.3).
- [ ] **Farevarsler som polygoner** fra MetAlerts (maks én henting per 10 min) og
      Varsom (flom, jordskred, snøskred).
- [ ] **Flyfoto: finn en kilde.** Norge i bilder er ikke lenger åpent — det krever tilgang
      gjennom en Norge digitalt-part. Sjekk om korpset har det via en samarbeidspartner;
      ellers Sentinel-2 (10 m, sjekk lisensen) (§6.1).
- [ ] **Koordinater på `oppdrag.Lokasjon`**, meldt inn til kartet gjennom et register i
      `core` framfor at kartet importerer oppdrag — én sannhet om hvor stedene er (§6.2).

### Backlog-modulen (`/backlog/`)

Levert 17. sep. 2026: innspill klassifisert som bug eller ønske, løst-flagg, filter på type,
status og modul. Modulens egne regler står i [`backlog/CLAUDE.md`](./backlog/CLAUDE.md).

- [ ] **Del ut tilgang til de som skal bruke den.** Ingen har en `ModulTilgang`-rad på
      `backlog` i dag, så bare global admin ser modulen. Tre nivåer i matrisen: «ser
      backloggen», «melder inn, retter sitt eget», «leder backloggen, setter løst».

- [ ] **Fire brukerpekere i backup er ikke vurdert** (funnet 17. sep. 2026, ved
      mutasjonstesting av backlog-modulen): `patients.Forstehjelper.user`,
      `patients.Helsepersonell.user`, `oppdrag.Vaktmodusperiode.satt_av` og
      `oppdrag.Enhetshendelse.kvittert_av` står i `IKKE_STRIPPET` i
      `core/tests_backup.py`.

      **Hva det betyr:** serialiseringen kjører med `natural_foreign`, så en FK til en
      konto lagres som brukernavnet. Er kontoen slettet i mellomtiden, feiler **hele**
      gjenopprettingen av den fila med `DeserializationError` — ikke bare den ene raden,
      og akkurat den dagen man trenger backupen.

      **Det er ikke gitt at de skal strippes.** Å beholde pekeren er et gyldig valg når
      koblingen er verdt mer enn gjenopprettbarheten. Alle fire er `null=True` med
      `SET_NULL`, altså teknisk strippbare. `Forstehjelper.user` og `Helsepersonell.user`
      er kontokoblinger av samme slag som `Mannskap.user`, som vaktlista **valgte** å
      stryke — der settes koblingen på nytt via e-postadressen. Finnes den veien i
      pasientmodulen også, er svaret sannsynligvis det samme.

      Valget hører til den som eier modulen, og skal stå skrevet enten i `strip_fields`
      eller i `IKKE_STRIPPET` med en begrunnelse.

- [ ] **VURDER: skal typene kunne omsorteres?** `rekkefolge` finnes på `Innspilltype` og
      settes automatisk til opprettelsesrekkefølgen, men det er ingen flate for å endre
      den. Gjøres det, skal hele lista sendes i én PUT (`oppdrag`-mønsteret) og ikke «flytt
      opp» per rad: to trykk som krysser hverandre i nettet gir en rekkefølge ingen ba om.

### KO-modulen — se [`docs/FORSLAG_KO.md`](./docs/FORSLAG_KO.md)

**Notatet er fortsatt et forslag** (17. sep. 2026), men **pulje 1 er bygget**: modulen er
registrert, `/ko/` finnes med sidebaren, og `ModulTilgang('ko')` virker. **Siden har ingen
faner** — fra 18. sep. 2026 står fire flater i 2×2, og hendelsesloggen er en egen flate
(André; se CHANGELOG 18. sep. og `ko/CLAUDE.md`).
Modulens egne regler står i [`ko/CLAUDE.md`](./ko/CLAUDE.md). `/oppdrag/` snevres inn til
enhetens egen skjerm, og **sentralbordet flytter til KO** — en flytting av
`oppdrag-sentral-*.js`, ikke en kopi. Puljene står i §10.

- [ ] **Pulje 7d — tidslinje og vaktrapport.** Det siste av pulje 7; 7a, 7b og 7c ble
      bygget 21. sep. 2026 etter [`docs/FORSLAG_KO_STATISTIKK.md`](./docs/FORSLAG_KO_STATISTIKK.md).
      «Vi skal ikke ta noe fra 7d enda» (André, 21. sep.) — men det som *er* bestemt, står
      her, så det ikke må tas opp igjen:
      - **Skissene er valgt:** S6, en tidslinje i KO-fanen med rader for hendelser, oppdrag
        og lag, tegnet som SVG uten nytt bibliotek; og S7, vaktrapporten som en
        server-rendret side med seks seksjoner og loggen inne i rapporten. Bare aktiv vakt.
      - **Rapporten lastes ned via en knapp** (André), som en selvbærende HTML-fil — ikke
        PDF, som hadde krevd et bibliotek for en side nettleseren alt kan skrive ut.
      - **«Minst mulig personopplysninger»** (André): ingen mannskapsnavn, telefon eller
        ISSI; problemstilling bare som kategori; ingen «generert av» eller «lukket av»;
        operatørnavnene i loggen bak en avkryssing som er av som standard.
      - **Tilgangen er åpen, og besvares når 7d tas opp:** André foreslo et nytt trinn
        `les_leder`. Anbefalingen er å gjenbruke `les_alle` med modulens egen etikett
        («Lese: vaktrapport», `Module.nivaa_navn`) — et nytt trinn i stigen er additivt,
        men det er én matrise, én profil og én dekoratør til å holde i live for ett
        endepunkt. Sammenligning mellom vakter er «ikke per nå».
      - Åpent: skal rapporten kunne lages for en arkivert vakt (KO-loggen arkiveres aldri)?
      - `HendelseLag.til` ble ikke lagt til: lagene leses av systemlinjene, og et
        `til`-felt rører hvem tavla viser som «på hendelsen nå».

- [ ] **Pause KOs polling når fana er skjult** (`document.hidden`). Tilbudt 21. sep. 2026
      da André spurte hvor ofte vinduene polles: loggstrømmen hvert 15. sekund, ressursene
      og tavla hvert 30., sidebaren hvert 30. når den er åpen. En fane i bakgrunnen holder
      fire pollere gående for ingen; `visibilitychange` kan stanse dem og hente alt idet
      fana kommer tilbake. Liten jobb, men rører alle fire klokkene — og `koSisteId`
      gjør at loggen tar igjen det tapte av seg selv.

- [ ] **«Til» i «Flytt oppdrag» tilbyr også opptatte biler.** Vurdert 21. sep. 2026 og
      *ikke* gjort: André ba bare om «Fra». I dag kan et oppdrag flyttes til en bil som
      står Fremme på et annet, uten at noe sier fra til den andre tavla. Svar når det
      dukker opp på en vakt — filteret er én linje i `_flyttValg`, `e.status === 'ledig'`.

- [ ] **Fjerne sentralbordet fra `/oppdrag/`** — «avvente inntil videre, men noe å se på»
      (André, 19. sep. 2026), og fra 18. sep.: «når KO er prøvd på en ekte vakt». Notatet §7
      sier «en flytting, ikke en kopi», og det siste steget er å la `/oppdrag/` bli
      enhetsskjermen alene. Risikoen ved å vente er lav: begge sidene kjører samme kode mot
      samme endepunkter og kan ikke bli uenige. `/ko/` har alt sentralbordet har (samme
      malbiter, samme modaler). Det som henger på `/oppdrag/` for kontoer uten enhet, kartlagt 19. sep.:
      tavla på `/ko/` krever `les` i KO, så brukere med bare oppdragstilgang mister den —
      `/oppdrag/` må sende dem videre til `/ko/`, og den som mangler KO-tilgang skal få en
      side som sier det, ikke 403; menyen «Oppdrag» bør skjules for kontoer uten enhet;
      rundt tretti steder i ti testfiler laster `/oppdrag/` som sentralbord og må pekes om;
      bjella til bilen lenker til `/oppdrag/` og røres ikke. Bilene beholder sida. Sjekk
      før avslagning: ingen bokmerker på `/oppdrag/` for sentralbordarbeid, og alle som
      skal ha KO har begge modulradene.

Forslaget erstatter datteroppdrag, som er arkivert: grupperingen hører hjemme i en
`Hendelse` som finnes *før* oppdraget og også dekker lag. Begrunnelsen står i §9.3.

*Pulje 2 (loggen) er levert 17. sep. 2026 — se CHANGELOG. De to valgene som blokkerte
er besvart: 730 dager som en `AppSetting` (ikke en Railway-variabel), ingen SHA-signatur,
og ni kuraterte systemhendelser i `ko/systemlinjer.py`.*

- [ ] **Historikkflate: lese tidligere vakters logg.** Nivået finnes alt
      (`skriv_leder`, `ko/module.py`) og linjene overlever vaktarkiveringen, så dette er
      en flate og ikke en datamodell. Den kan tas alene når som helst; billigst sammen
      med den puljen som uansett trenger en «velg vakt»-kontroll, og det er nå pulje 5
      (hendelser) etter omstokkingen 17. sep. 2026.

      **Vinduet som betyr noe er de tre ukene etter vakta**, ikke året etter: §4.2 sier
      loggen er «i praksis et dokument man leser etter et arrangement der noe gikk galt»,
      og det leses dager til uker etter. Årsgamle logger er sekundærbruken.

      `les` gir aktiv vakt og skal fortsette å gjøre det — en ny operatør på vakt i kveld
      har ingen operativ grunn til å lese fjorårets helseopplysninger (André, 17. sep.).

- [ ] **Utskrift av loggen.** §4.2 sier den skal være «utskrivbar», og det er ikke bygget.
      Det er ikke pynt: skal loggen leses i en gjennomgang etter et arrangement, leses den
      av flere samtidig rundt et bord. Rendres server-side fra de samme `_til_dict`-radene,
      slik at papiret og skjermen sier det samme. **Og med alt, kronologisk** (18. sep.
      2026): loggstrømmen på skjermen viser ikke kommentarene inne i hendelsene, og
      utskriften er stedet der ingenting «bare ble sagt inne i hendelsen».

*Pulje 3 (ressursoversikten) er levert 17. sep. 2026 — se CHANGELOG. Projeksjonen, den
tredje kilden (`ko.Ressursstatus`) og tavla i venstre kolonne. Rutingflagget er **ikke**
bygget; det flyttet til `/park/`-punktet nederst, der det hører hjemme.*

- [ ] **Vaktlistas stemplinger inn i loggen — vurderes nå, lag-begrepet har fått et hjem.**
      Utelatt bevisst i pulje 2 (`ko/systemlinjer.py`): «Lag 3 gikk av vakt» er ekte
      situasjonsinformasjon, men per-person-stempling på hver vaktpost ville druknet
      loggen ved hvert vaktskifte. Løftes det, skal det være **ressursen** som går av og
      på vakt, ikke personen — og ressursen er nå noe tavla kjenner.

- [ ] **KO på smal skjerm er akseptert, ikke løst.** Under `xl` stables de tre kolonnene,
      loggen først, og sida ruller normalt. Det duger til en som kikker, ikke til en som
      fører. Blir mobil et ekte krav, er det en egen oppgave — og svaret er **ikke** faner:
      da er det heller loggen alene, med tavla som et nedtrekk ved siden av sidebaren.

- [ ] **Skal lagene ha en egen status utover «på hendelse»?** Fra 19. sep. 2026 står et lag
      som «På H14 · 23 min» når det er registrert på en åpen hendelse (`ko.HendelseLag`),
      og ellers som ledig med hvem som er møtt. Det dekker det André ba om («det viktige er
      å vise om laget er opptatt på hendelse»). Det som *ikke* finnes er pause, ute av
      drift og lignende — et forsøk på fire slike 17. sep. ble rullet tilbake («Jeg hadde
      aldri noe pause og ute av drift på de i /oppdrag»). Tas opp bare om det meldes et
      behov fra en ekte vakt; ikke merket «Krever Andre», for det blokkerer ingenting.

*Pulje 4 (sentralbordet) er levert 18. sep. 2026 — se CHANGELOG. `/ko/` kjører
sentralbordet fra oppdragsmodulens egen kode, og oppdragsflata gates av `oppdrag`-modulen
(André). En KO-operatør trenger derfor to rader: `ko` og `oppdrag`.*

- [ ] **Visuell kontroll av `/ko/` mot `/oppdrag/` er fortsatt manuell.** Tre forsøk på
      «lik den i /oppdrag» gikk grønne i suiten og feilet i nettleseren, fordi `/ko/`
      ikke lastet `oppdrag.css` (18. sep. 2026). Suiten holder nå stilarkene like, men
      en layoutfeil (klemt kort, liste som ikke ruller) ser bare et øye. Et
      Playwright-skjermbilde av begge sidene mot en seedet base — som
      `scripts/lag_ikoner.py` alt gjør for ikonene — ville gjort kontrollen til en
      kommando. Verdt å ta før sentralbordet i `/oppdrag/` slås av.


- [ ] **Delt konto og enhetskontoer må fortsatt til `/oppdrag/`.** `er_enhetskonto` får
      enhetsskjermen, og den flytter ikke. Verdt å ha skrevet ned før noen slår av noe.

- [ ] **`oppdrag-enhet.js` deler ikke det delte enhetskortet.** Bilens egen skjerm har
      egne kopier av `hastegradKlasse`, `_medAntall` og `_problemMedAntall`. Kopiene sto
      igjen i pulje 4 med vilje: enhetsskjermen laster ikke `oppdrag-kort.js`, og den er
      den ene flata som *ikke* flytter. Tas hvis den noen gang skal dele mer.

*Pulje 5 (hendelser) er levert 18. sep. 2026 — se CHANGELOG. `ko.Hendelse`, `Oppdrag.hendelse`,
`H12`/`O45`, gruppering av tavla med bryter, lukking med 409 og `confirm`, gjenåpning logget.*

- [ ] **Linje i loggstrømmen → hendelse i etterkant.** §4.1 sier «en linje kan knyttes
      til en hendelse i etterkant», og datamodellen har det (`Logglinje.hendelse`,
      `SET_NULL`). Fra 18. sep. 2026 kan man skrive *i* hendelsen og lage en hendelse *av*
      en linje; det som mangler er å flytte en eksisterende linje inn i en hendelse. Ett
      endepunkt (`logg/<pk>/hendelse/`) og en handling på linja når noen savner det.

- [ ] **Oppsettet i `/ko/` huskes per nettleser, ikke per bruker** (18. sep. 2026). Valgt
      med vilje — KO-PC-en beholder sitt — men følger ikke operatøren til en annen maskin.
      Per bruker på serveren når noen savner det; da som en `AppSetting`-lignende rad per
      konto, ikke en ny tabell.

*Pulje 6 (chat, ansvarsmerke, minimerbare grupper, vaktlistas ressurser på tavla) er
levert 18. sep. 2026 — se CHANGELOG. Filteret ble til minimering etter André.*

- [ ] **KO-ført status for lag er fortsatt ubesvart, og nå står lagene på tavla.** Kortet
      sier bare det vaktlista vet: hvem, og om de er møtt. Spørsmålet om hva en status skal
      hete (punktet over) er blitt mer synlig, ikke mindre — når noen ser «Lag 3 · 2 av 3
      møtt» og vil skrive «sendt til H12», er det dette som mangler.

- [ ] **Delt konto skal bare kunne ha `ModulTilgang` til `oppdrag`.** `er_delt_konto` finnes
      og styrer e-post, MFA og selvbetjent reset; den avgrenser ikke modultilgang. Håndheves
      i skjemaet, i datalaget og med en test — sperrer som bare dekker dagens veier, ser ikke
      en ny vei. Kan gjøres uavhengig av KO.

- [ ] **`/park/` — eget notat skrives etter KO.** Lagets utfallsregistrering: problemstilling,
      lokasjon, utfall, ingen stempling, ingen pålogging. Egen modell, egen kilde i
      statistikken, ingen kobling til `/pasienter/`. Vaktnøkkel som admin kan generere og
      trekke tilbake, og endepunktet er **skrive-bare**. Rutingflagget på `Ressursgruppe`
      (`FORSLAG_KO.md` §3.2) hører til her, og ble bevisst **ikke** bygget i pulje 3:
      uten `/park/` er det en bryter med én stilling, og at det korrelerer med «hvem
      stempler selv» er tilfeldig — den utledes av `Ressurs.enhet`.

### Brukere, e-post og roller — se `docs/BESLUTNING_BRUKERE_OG_EPOST.md`

Besluttet 14. aug. 2026: invitasjon som registreringsvei, selvbetjent passord-reset for
personlige kontoer, admin-reset beholdt for alle. Ingenting bygget ennå.

- [ ] **AHASend og Google inn i `PERSONVERN_DOKUMENTASJON.md` A.2.** Selve avtalen er på
      plass (over), men dataflyten er fortsatt ikke dokumentert. Tas i
      dokumentgjennomgangen. Merk at C.3 linje 711 sier «Ingen andre databehandlere er
      for øyeblikket i bruk» — det er direkte feil i dag.

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

      - **Fase 6 og 7 er ikke lenger blokkert** — scopet er levert; de grupperer
        og arkiverer på `Vakt`.

### Rollemodellen — se `docs/BESLUTNING_ROLLEMODELLEN.md`

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

- [ ] **Forutsetning før migrasjonen skrives — kontrolleres i prod:** hvor mange kontoer
      har `role` ≥ `read_write` men `kan_redigere_pasienter=False`? Det er kontoene som i
      dag har en tilgang de ikke var ment å ha. Tallet avgjør hvor stor oppryddingen blir
      etter deploy 1.

- [ ] **Statistikkmodulen komponerer ikke tilgang (§5).** Den gates på statistikktilgang
      alene, så den viser pasienttall til alle som har den — også en bruker uten
      `patients: les`. Kravet «viser kun kilder brukeren har minst `les` på i
      kildemodulen» er ikke innført. Uten det er statistikk en bakvei rundt
      modultilgangen, og det er den eneste grunnen til at punktet ikke er en detalj.
- [ ] **Tilgangstabellen i `docs/BESLUTNING_STATISTIKK.md` må skrives om til
      modulnivåer.** Den beskriver fortsatt `role`-verdier som ikke finnes.

### Oppdragsmodulen: `skriv_handling` for bilkontoer

- [ ] **`skriv: handling` for bil-/ambulansekontoer.** Nivået er definert; bruken er
      planlagt i `docs/BESLUTNING_OPPDRAGSMODULEN.md` §5.1. Invarianten fra §3.2 er
      **skjerpet, ikke slakket**, for å tåle offline: kroppen har et lukket skjema på to
      nøkler (`klienttid`, `idempotency_key`), og alt annet gir 400. Det er testbart ved
      uttømming, i motsetning til «husk å utelate fritekst».

### Pasientmodulen — småting

- [ ] **Skal tavla og lista dele «mine»-tilstand?** `mineOnly` og `boardMineFilter` er
      to uavhengige variabler, så valget følger deg ikke mellom fanene. Merk at de gjør
      forskjellige ting: lista *filtrerer bort* andre, tavla *dimmer* dem. Det taler for
      å la dem være uavhengige. Krever en avgjørelse, ikke en fiks.

### Skalering mot 2027 — se `docs/RUNBOOK_VAKT.md` §3c

Gjennomgang 13. aug. 2026, med 1000 pasienter og peak 100 brukere som premiss.

- [ ] Park-registreringer blir **egen modell**, ikke rader i `Patient`. Holder sykestuas
      liste på ~250 rader i stedet for 1000, og matcher at dataene er enklere.
- [ ] Park-appen er et skriveendepunkt **uten innlogging**: signert lenke via
      `django.core.signing` (ikke gjettbar URL, kan tilbakekalles), rate-limit per token,
      og responsen returnerer kvittering — aldri data.

- [ ] **Vaktlistemodulen — se `docs/BESLUTNING_VAKTLISTE.md`.** Bestilt av André
      29. aug. 2026, **besluttet samme dag** i to avklaringsrunder — alle ti
      avklaringene er besvart, kun små restpunkter avgjøres underveis (§11).
      Personelloversikt sortert på korps med kompetanse og rolle; ressurser
      (samleplass, biler, lag, KO) som reserveres til korps og bemannes av korpsene
      selv, med skifttider; drift som reversibel innsjekk-port med møtt/av vakt;
      «Tilstede nå» med utskrift (brukes av brannsikkerhetshensyn ved overnatting);
      planleggingstall (timer, hviletid, bemanningskurve, varsler); besetningspanel i
      `/oppdrag`. Sju faser, 37–49 t.
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
- [ ] Vurder `cached_db`-sesjoner. `SESSION_SAVE_EVERY_REQUEST=True` med DB-sesjoner gir
      én UPDATE per request. Krever Redis, altså vakt-modus.

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

- [ ] Integrasjon med produksjonsdatabase
- [ ] Lage Locus-klone, hente sted via enhetens GPS

**Uavklart før noen av dem bygges** (spørsmålene sto ubesvart i den opprinnelige
høynivå-skissen, `docs/archived/SANITETSPORTAL_PLAN.md` §7):

- [ ] Skal en «vakt» være ett enkelt arrangement, eller også dekke faste
      beredskapsperioder som ukentlig lagvakt? Avgjør feltene på modellen
- [ ] Skal rapportmodulen kun være intern, eller også gi tilgang til
      styre/oppdragsgivere? Tilgangssiden er nå `ModulTilgang` (se «Rollemodellen»);
      det som gjenstår er eksportformat, og om eksterne mottakere skal ha konto i det
      hele tatt

> **Merk:** skissen antok modulene `vakter`, `utstyr`, `rapport` og `beredskap`. Retningen
> siden er blitt park og oppdrag (se «Skalering mot 2027» over). Arkitekturvalgene i
> skissen står seg — modullista gjør det ikke.

### Eget domene — portal.sanitet.net

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

### Puljene fra Andrés gjennomgang 16. sep. 2026

**Lista på sytten punkter ble prioritert i fire puljer, og sto ingen steder før 16. sep.**
Det var feil: den levde bare i samtalen, og `TODO.md` sier selv i toppen at et punkt som
ikke står her, ikke blir gjort. Nå står den her, og puljer som er levert krysses av med
dato som alt annet.

Rekkefølgen er valgt etter **hva en feil koster**, ikke etter hvor lett punktet er:
tilgangshull og data først, funksjonalitet i midten, utseende sist.

- [ ] **Pulje 3 — vaktlista, bruk og utseende.** Fem av seks levert 16. sep. 2026
      (se CHANGELOG): Timeoversikt, «Oversikt» som talltabell, redigerbare ressursgrupper,
      fanerekka i to bolker og rollerangeringen. Det ene som står igjen er lagt bort til
      vurdering:
      - [ ] **Sett rolle på flere skift samtidig — til vurdering, ikke bestilt**
            (brutt 16. sep. 2026: «Det fungerer forsåvidt når det gjelder korps og du går
            inn på rediger ressurs og setter korps der»).
            - **Korps er alt løst, og det var halve punktet.** `Ressurs.korps` er
              standarden for *alle* plassene på ressursen (`services.reservert_korps`), så
              «Rediger ressurs» er bulkoperasjonen. `Vaktpost.korps` overstyrer per plass
              og brukes der en samleplass deles mellom korps — det er unntaket, ikke
              normalen.
            - **Det som gjenstår er rollen.** Den finnes bare per plass; det er ingen
              standardrolle på ressursen å arve. Tjue like skift betyr fortsatt tjue valg
              i nedtrekket.
            - **Tre spørsmål hvis det tas opp igjen**, så tenkningen ikke gjøres på nytt:
              hvordan velges radene (avkryssing per rad, avkryssing på blokklinja, eller
              begge — blokken er bare «huk av disse» med ett klikk); skal «Sett» være én
              forespørsel eller én per rad (én er atomisk, men feiler helt hvis én rad er
              utenfor tilgangen din); og korps-føreren når bare radene hun kan røre, så
              utvalget må sile *før* innsending, ikke svare 403 etterpå.
            - **Vurder først om en standardrolle på ressursen løser det billigere.** Er
              «Lag 1» alltid én lagleder og tre lagsmedlemmer, er det oppsettet som
              gjentar seg — ikke en handling man gjør om igjen. Planleggeren lager alt
              plassene; den kunne gitt dem roller.

### Løse punkter

- [ ] **`core/tests_verifiser_backup.py` er 47 sekunder — en firedel av hele suiten**
      (målt 16. sep. 2026). Den starter `migrate` i en underprosess per test, som er
      riktig for det den prøver, men prisen betales av hver eneste kjøring. Vurder et
      tag-skille så den bare kjøres når backupkoden endres. **Ikke bare slett den:** den
      er den ene testen som svarer på om *innholdet* i backupfilene duger.
- [ ] **`core/tests_backup.py` tåler ikke `--parallel`.** Testene skriver ekte filer til
      én backupmappe og rører det globale handlerregisteret. Feilen kommer ut som
      «cannot pickle 'traceback' object», som ikke ligner det den er. Så lenge den står,
      må `core` kjøres serielt for seg — se kommandoblokka i `CLAUDE.md`.
- [ ] **Rate-limit arkivstatistikken.** Tre endepunkter kjører nå samme tunge beregning
      som live-statistikken uten å ha fått en bøtte i S3:
      `/statistikk/api/kilde/<slug>/arkiv/<pk>/full-stats/` (flyttet dit i fase 6),
      `/pasienter/api/innstillinger/arkiv/<pk>/` og — fra fase 7 —
      `/oppdrag/api/arkiv/<pk>/`. Alle er admin-only, uten auto-refresh, og leser rader
      som ikke endres, så eksponeringen er lav. Én linje per view når noen er i filene
      uansett.
- [ ] Flytte sesjonsdelen til en admin-side
- [ ] Testene er massive, kan vi komprimere dem? (kjøretiden er løst: 500 s → 15 s via
      PASSWORD_HASHERS under test. Gjenstår evt. å redusere *antall* tester)
- [ ] Vurder `argon2-cffi` for sterkere passord-hashing i produksjon (i dag PBKDF2)

- [ ] **Skal grovsortering og sted inn i oppdragsarkivet?** Payloaden er signaturlåst, så
      nye felt krever en versjonert payload — nye arkiver får dem, gamle verifiserer som
      før. Mønsteret finnes allerede (`varslet_modus` og `behandlet_at` står i payloaden
      bare når de er satt). Egen beslutning, ikke en oppgave som bare kan gjøres.
- [ ] **Sikkerhetsgjennomgangen: L6, L8, L12, L17, L18, L22 gjenstår.** Lavpunktene fra
      `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md` som ble satt til «senere». De er
      navngitt der, med begrunnelse for hvorfor de ikke hastet.
