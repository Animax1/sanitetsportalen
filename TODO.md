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

- [ ] **Test flere portaler på staging før `main`** (fase 0–7, 17.–18. okt. 2026). Moderator­
      flyten på `/moderator/brukere/` (legg til flere, «Rediger tilgang», ny konto med tilgang i
      samme skjema, gjør til moderator), tilhørighetene på `/admin/tilhorigheter/` og på
      brukersiden, «Hent inn fra tidligere» i vaktlistas mannskapsregister, personsøket på
      `/admin/personsok/` og sladdingen på `/admin/sladding/`. **Kartet** (gikk ut i prod
      18. okt., kart-sanitet `519c975`): gruppen din skal stå med «standard» under
      Administrasjon → Grupper, og bilene og lagene skal vises som før.
- [ ] **Se over ordboka på staging før `main`** (bygget 14. okt. 2026). Sentralbordet
      («Ressurser» står, «Hent tilbake til oppdragslisten»), KO (vinduet «Ressursoversikt»
      står, «Vaktlistens enheter uten delt konto» i innstillingene, kolonnen «Enhet» i
      utskriften), og -en-formen der du ser den — «Tavlen», «vakten». Er et ord feil i
      sammenhengen, si hvilket; reglene står i `docs/FORSLAG_ORDBOK_OPPDRAG_KO.md` §4.
- [ ] **Feltprøv Wake Lock på bilskjermen** (på staging fra 9. okt. 2026 — kan ikke prøves i
      node). En iPhone og en Android i en bil, bilkonto innlogget, 20 minutter uten berøring —
      én gang med strømsparing av, én gang på. Trykk på skjermen først (låsen hentes ved
      trykk). Linja under lydhintet skal si «Skjermen holdes våken»; med strømsparing på
      skal den si «Skjermen kan sovne — slå av strømsparing». Bytt app eller ta en samtale midt
      i, og kom tilbake: skjermen skal fortsatt holdes våken. **Bilrutinen:** telefonen står i
      lader — skjerm på hele vakta tømmer batteriet og gjør telefonen varm.

- [ ] **Les `/personvern/` på staging, og få teksten godkjent for Kverneland Røde Kors før
      den går til `main`** (12. okt. 2026). Det er korpset som er behandlingsansvarlig, og
      siden taler på korpsets vegne. Siden lover svar innen en måned på
      **personvern@sanitet.net** (egen innboks hos Proton fra 14. okt.). Teksten står i
      `core/templates/core/personvern.html`; tallene hentes fra koden.

- [ ] **Databehandleravtale mellom Kverneland Røde Kors og deg** (art. 28). Du eier og drifter
      portalen og kart.sanitet.net, korpset er behandlingsansvarlig — da er du databehandler,
      og forholdet skal stå i en skriftlig avtale: hva du behandler, at du bare gjør det etter
      korpsets instruks, taushetsplikt, sikkerhet, avvik, sletting når samarbeidet slutter, og
      at korpset godkjenner leverandørene (Railway, Scaleway, AhaSend, Proton) som
      underdatabehandlere. **Utkast:** [`docs/DATABEHANDLERAVTALE_UTKAST.md`](./docs/DATABEHANDLERAVTALE_UTKAST.md)
      (13. okt. 2026), dekker begge appene; de åpne punktene står nederst i den. Før den inn i A.1/A.2 når den er signert.
      **Den viktigste av de tre:** uten den er det uklart hva korpset faktisk har ansvar for.

- [ ] **Bestem med korpset: DPIA eller dokumentert begrunnelse** (15. okt. 2026). Kontrollert
      mot Datatilsynet er **to av de ni kriteriene oppfylt** — helseopplysninger og sårbare
      registrerte (pasienter er nevnt uttrykkelig) — og da er utgangspunktet at DPIA *skal*
      gjøres. Vurderingen i protokollen sa «ikke påkrevd», men drøftet bare art. 35(3).
      **Anbefaling: gjennomfør den.** Det meste finnes alt i protokollen, og risikoen for de
      registrerte er skrevet (A.12, v1.28). Sjekk om korpset eller Røde Kors har et
      personvernombud — da skal det spørres (art. 35(2)).

- [ ] **Før inn databehandleravtalene for AhaSend og Proton** (14. okt. 2026): referansen
      (URL eller dato) for kontoene dine. Står som «[fylles inn]» i protokollen A.2.

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
            - [ ] Deploy 2 (planens G6), i tre steg. **G6a levert 26. sep.:** ingen kode
                  leser `Oppdrag.enhet`. **G6b, etter neste vakt:** skrivingene
                  og broene i `Oppdrag.save()` bort, Django glemmer feltet (kolonnen
                  står). Betingelsen var «la prod gå noen vakter med broene først», og det
                  har ikke vært en vakt siden flere enheter kom — neste vakt er den
                  første. Kolonnen er nødutgangen til modellen har vært i ekte bruk.
                  **Forarbeidet er levert 14. okt.:** ingen test går gjennom broene, og
                  i drift telles de (`oppdrag/bro.py`). **Før G6b:** se på
                  `/admin/server-status/` at «Broer i oppdrag (G6b)» står
                  «Aldri brukt» etter vakta. Står det et tall, er det et funn — G6b venter.
                  **G6c, i en senere `main`-push enn G6b:** `DROP COLUMN`, og
                  `Statusmelding.oppdragsenhet` NOT NULL (med `SET CONSTRAINTS ALL
                  IMMEDIATE` om et dataskritt går foran). Backup før.
      - [ ] **Stripe på blokklinja** (mini-Gantt over vaktas spenn) — alternativ
            «Begge deler» i spørsmålet 11. sep.; valgt bort for nå, lett å
            legge til siden blokka alt bærer spennet.

- [ ] **Første skarpe vakt med oppdragsmodulen.** Modulen er ferdig og testet, men
      aldri brukt under en reell vakt — og det er den prøven som finner det ingen
      testsuite gjør: samband, dekning i felt, og om knappene sitter der hendene
      forventer dem. Ha `docs/RUNBOOK_VAKT.md` framme; §10a har nå **to**
      arkivknapper å krysse av ved vaktslutt.

- [ ] **Vurder å slå av lagring av e-postinnhold hos AHASend.** Avtalen sier det kan
      deaktiveres. Feilvarslene inneholder brukernavn, rolle, klient-IP, URL og
      traceback — jo mindre som ligger lagret hos databehandleren, jo bedre.
      **Merk til A.12:** avtalen sier «Controller agrees not to use the Services to send
      or store Sensitive Data». Feilvarselet inneholder personopplysninger, men ingen
      helseopplysninger — skjemadata, cookies og lokale variabler ble slanket bort
      22. aug. 2026, og `core/tests_error_reporting.py` vokter det. Den testen er dermed
      ikke bare en personvernfinesse; den holder oss innenfor en kontraktsforpliktelse.

- [ ] **Når vaktlistetilgang deles ut i prod: gi hver konto riktig nivå og korps.** `les` ser
      bare sitt eget korps — den som skal samordne må ha `les_alle`. En konto med `les` eller
      `skriv_handling` uten korps ser eller fører ingenting: sett korpset i kortet
      «Vaktlisten: korps» på brukersiden (fra 1. okt. 2026, krever at `staging` har gått til
      `main`), eller koble kontoen til en mannskapsrad.

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

- [ ] **«Åpne kartet» til prod, når du sier fra om `main`** (prøvd på staging 19. okt. 2026).
      En **ny** nøkkel for prod — ikke stagingens og ikke kartkoblingens — i
      `KART_INNLOGGING_NOKKEL` i prod-portalen og `PORTAL_INNLOGGING_NOKKEL` i kart.sanitet
      production, en gruppe med portalens slug i kartet, og bryteren på `/admin/innstillinger/`.
      Kartets side er alt i prod og står inert til nøkkelen er satt

## Pågående / neste

### «Åpne kartet» fra KO — neste steg (19. okt. 2026)

- [ ] Bryter per portal i stedet for én global, hvis en portal skal ha kartet og en annen ikke

### Flere portaler i én installasjon — se [`docs/BESLUTNING_PORTALER.md`](./docs/BESLUTNING_PORTALER.md)

Besluttet 17. okt. 2026, ikke påbegynt. Andre i organisasjonen skal kunne kjøre egne vakter
(«Brann», kamp 1–15) uten å se hverandres mannskap, pasienter eller oppdrag. Rollene er
global admin, moderator og medlem — ingen portaladmin. Hver fase deployes for seg, og
**portal nummer to opprettes ikke i prod før fase 4 er levert** (notatet §6).

- [ ] **Rydd pekeren og gjør `Vakt.portal` påkrevd** (etter fase 1, 17. okt. 2026).
      `AppSetting['aktiv_vakt_id']` leses ikke lenger, men står for en eventuell
      tilbakerulling — slett den i en migrasjon når fase 1 har stått i prod en stund.
      `Vakt.portal` er nullbar fordi backupfiler fra før portalene ikke har feltet: en
      gjenoppretting av en slik fil må fylle det inn (som `GAMLE_MODELLNAVN`) før kolonnen
      kan bli `NOT NULL`.
- [ ] **Gjør `ModulTilgang.portaltilgang` påkrevd i basen** (etter fase 2, 17. okt. 2026). Den er
      nullbar bare for release-vinduet og migrasjonen som fylte den; `save()` krever den alt.
      Neste migrasjon på `accounts` kan sette `NOT NULL` når fase 2 har stått i prod.
- [ ] **Skal førstehjelperens og helsepersonellets navn i pasientarkivet kunne sladdes?** De
      står frosset på `ArkivertPasient` og inngår i arkivets signatur (`sha_payload()`), i 730
      dager. Det er frivillige, ikke pasienter — en sletting etter art. 17 fra en frivillig
      stopper der. Å sladde dem krever ny signering av arkivet («signert på nytt etter
      sladding», med den gamle signaturen som historikk). Resten av fase 7 er levert: de
      kliniske feltene er verdimengder, ikke fritekst (18. okt. 2026, `patients/sladding.py`).
- [ ] **Den frosne KO-statistikken bærer fritekst uten frist.** `ko/statistikk.py` fryser
      hendelsens `tittel` og `siste_linje` (operatørens siste linje, 160 tegn) i «verken»-lista,
      og `core.VaktStatistikk` har ingen lagringstid (A.9, raden om lagregistreringene). Funnet
      18. okt. 2026 da sladdingen måtte skrubbe kopiene. To veier: ta feltene ut av den frosne
      formen (ny `statistikk_versjon`; nummeret er nok til gjennomgangen), eller gi de frosne
      tallene en frist. Den første fjerner kopien; den andre bare forkorter den.

### Sikkerhetsgjennomgangen 28. sep. 2026 — alle fire puljer levert, se [`docs/SIKKERHETSGJENNOMGANG_2026-09-28.md`](./docs/SIKKERHETSGJENNOMGANG_2026-09-28.md)

Pulje 1 (kontoovertakelse), 2 (det som blokkerte `main`), 3 (backup og offsite) og 4
(opprydding og drift) er levert, se CHANGELOG 28.–29. sep. 2026. Beslutningene står i dokumentet. Hver pulje går på egen gren med tester som
gjennomfører angrepet, og mutasjoner på nivået i `CLAUDE.md`. Puljene gjøres ferdig før
`staging` går til `main` (André: «vi har tid til å gjøre oss ferdig med disse puljene først»).

- [ ] **Bekreft at standardplanen for modulene står på «Ved endring»** på `/admin/backup/`.
      Modulfilene i prod sto stille fra 16. sep. 2026, og KO, Lag og backlog hadde aldri hatt en
      fil — klokka lager den første fila for en modul uansett, så planen sto trolig på «Av».
      1. okt. fikk alle ni en fil (manuelt og av klokka). Står den fortsatt på «Av», blir det
      ingen nye filer før noen trykker.

### Avslutt vakt, arkiv og tidligere vakter i statistikken — steg 1–3 levert 28. sep. 2026

André: «etter hver vakt [...] arkiveres modulene samtlige som admin trykker [...] og statistikk
lagres og er tilgjengelig i /statistikk som tidligere vakt.» Frysingen, den felles avslutningen
og vaktvelgeren er levert (CHANGELOG 28. sep. 2026). Beslutningen som gjenstår å bygge:
**sensitive problemstillinger** merkes av admin når som helst — før, under eller etter vakta —
og slås sammen til «Sensitivt» først når radene slettes etter 24 måneder. Et merke per liste
(pasienter, oppdrag og lag har hver sin). **Ingen automatisk skjuling av små tall**
(«Hjertestans blir jo fort merket [...] Men det vil jeg ha kontroll på selv»).

- [ ] **4. Sensitiv-merket, og de frosne tallene gjøres grovere når radene slettes.** Gjelder to
      steder, ikke ett: arkivenes aggregat (`core/arkiv`, `kollaps`; pasientarkivet fryser i dag
      hele statistikken med krysstabellene, `patients/services.py`, `bygg_aggregat`) **og de
      frosne settene i `core.VaktStatistikk`**, som fra 28. sep. holder vaktas tall i detalj uten
      frist. Når radene slettes, regnes settet ut på nytt med sammenslåingen — for pasienter og
      oppdrag fra arkivradene før kollapsen, for KO og Lag fra radene før `purge_old_logs`
      tar dem. Bemanning bærer ingen helseopplysninger. Arkivet tar vare på hvilke
      problemstillinger som var merket da det ble laget, så et navnebytte ikke glipper.
- [ ] **MULIGHET: arkivenes rader og signatur også på `/admin/vakt/`.** Siden viser
      arkivene, lenker til tallene og sletter dem (28. sep. 2026), men radene og
      signatursjekken står fortsatt i pasientmodulens og oppdragsmodulens egne vinduer. Å samle
      dem krever en visning gjennom `core.arkiv`-registeret, ikke to modul-API-er kalt fra `core`.

### Offline og papir som reserve — avklart 27. sep. 2026; KO levert 13. okt. 2026

André meldte at merknader ikke kan redigeres offline i vaktlista («virker ut som bare
stemplingen fungerer»). Etter en gjennomgang av alternativene (siste vinner, versjonsnummer,
felt for felt, hendelser, CRDT) var konklusjonen hans: **konfliktene er usannsynlige, og det
som trengs offline er å *ha* dataene og kunne skrive dem ut — redigeringen kan gjøres på
papiret og føres inn når nettet er tilbake.** Full redigering offline bygges derfor ikke.

**Skillet som styrer hva som hjelper:** en kopi i nettleseren finnes bare der den ble lagt.
Vaktlista henter sin når noen åpner den; **KO henter utskriften hvert femte minutt**
(`ko/utskrift.py`), så KO-PC-en har den også når portalen eller Railway er nede — så lenge
den er under et døgn gammel. Alle andre steder er det som alt er skrevet ut eller sendt på
e-post reserven.

- [ ] **Vaktlista:** les og utskrift offline er i hovedsak på plass (service workeren, 24 t;
      utskriftsstilen; fila på e-post fra `vaktliste/fil.py`). Vurder om **merknadene** skal
      med i fila på e-post — i dag har den telefon og ISSI, men ikke merknad, med vilje.
- [ ] **`/pasienter/`: papirskjema som reserve, ingen offline-kopi av lista.** Det er
      helseopplysninger på delte PC-er — samme grunn som at backupen ikke kan lastes ned.
      Utskrift av pasientlister krever en rutine (hvem har arket, destruksjon) og hører
      hjemme i DPIA-notatet. Registrering offline er teknisk enkel (idempotensnøklene
      finnes), men **pasientnummeret** deles ut av serveren — offline ville gitt et annet
      nummer på papiret enn i systemet.

### Veien til neste vakt (om ~240 dager, fra 26. sep. 2026)

*Planen fra 26. sep. 2026. Neste vakt er den første der flere biler per oppdrag brukes i
virkeligheten, og rekkefølgen under følger av det.*

- [ ] **Fastfrysing noen uker før vakta:** ingen skjemaendringer, flyttinger eller nye
      moduler — bare feilrettinger. Det som kjører på vakta skal være det generalprøven
      prøvde. Det som skal være med på vakta — `/lag/`, puss av `/ko/` og `/vaktliste/` —
      må derfor være ferdig før frysingen, ikke under.
- [ ] **Generalprøve på staging, 3–4 uker før vakta** —
      [`docs/GENERALPROVE.md`](./docs/GENERALPROVE.md). Ekte folk og telefoner, hovedvekt
      på flere biler per oppdrag. Testsjekklistene for KO og vaktlista kjøres i forkant.
      Funn går i `/backlog/`. **Og lastmålingen i §8** (4. okt. 2026): det reelle antallet
      faner i en time, og tallene inn i `docs/RUNBOOK_VAKT.md` der det står «Mål på
      staging» — se «Skalering mot 2027» under Ideer. **Og «Broer i oppdrag» på
      server-status i §9** (14. okt. 2026), før staging gjenopprettes.
- [ ] **Etter vakta:** arkivering, «Broer i oppdrag» på server-status, deretter G6b — og G6c i
      en *senere* `main`-push (se under).
- [ ] **G2 (store filer): `oppdrag/services.py` gjenstår — men ikke før G6b**, ellers
      skrives samme fil om to ganger med vakta imellom. Metoden fra `accounts/views.py` og
      `ko/views.py` (CHANGELOG 13. okt. 2026): AST per toppnivånavn og rutekart før og
      etter, og en differensialtest mot den gamle fila.

### Kodegjennomgangen 25. sep. 2026 — se [`docs/PLAN_TEKNISK_GJELD_2026-09-25.md`](./docs/PLAN_TEKNISK_GJELD_2026-09-25.md)

*Hele appen lest på staging `7c21318`. Alt unntatt C1 finnes også i prod (`main`
`636e1f2`). Funnene, begrunnelsene og «ferdig når» står i notatet; her står bare puljene,
i den rekkefølgen de skal tas. A1 må tas før deploy 2 i oppdragsmodulen.*

- [ ] **Pulje C — avgjørelser, venter med vilje.** C1 og C2 levert 26. sep. C3 og C4
      står der de står til utviklingen er kommet dit (André, 26. sep.: «vi er ikke ferdig
      med å utvikle og kan holde de der de er inntil videre»):
      - **C3: `Patient.is_active` inn eller ut.** Ingen kode setter feltet til `False`,
        ingen JS sender `?include_archived`, og DELETE-grenen i `patients/signals.py` kan
        ikke nås. Anbefaling: ut, med egen migrasjon.
      - **C4: `Vaktpost.avmeldt_at` — ett predikat for «på vakt», eller fjern feltet.**
        Feltet har ingen skrivevei, og fire lesere utelater avmeldte mens fire tar dem
        med. Avgjøres **før** noen bygger en avmeldingsknapp.
- [ ] **Pulje G — struktur, når man er i filene.** G4 og G5 levert 26. sep., og av G1 server-status,
      `AppSetting`-adminen, `appsetting` og `kollaps_arkiv`. Vaktas livssyklus er flyttet inn i
      punktet om arkiveringen under — den trenger et register, ikke en flytting.
      Testinfrastrukturen (`js_test_utils`, `tests_modul_dekorator`) blir stående: rundt hundre
      testfiler importerer den, og en flytting fanger ingen feil — tas når noen er der uansett. Store filer (G2);
      pasientsidens eget skall (G3 — klokka er felles fra 26. sep.; å arve `base_portal` venter
      til pasientsiden redesignes uansett).
- [ ] **scipy og numpy (~160 MB) — valgfrie?** Vurdert under G5, ikke endret. Koden tåler
      alt at de mangler (`HAS_SCIPY` i `patients/services.py`): da står χ²- og
      Kruskal-Wallis-merkene som «Ingen data», og resten av statistikken virker. Å ta dem ut
      av `requirements.txt` er altså å **fjerne en funksjon**, ikke å rydde — og gevinsten er
      byggetid, bildestørrelse og minnet hver worker holder etter første statistikkall. Et
      tredje valg er å skrive de to testene i ren Python; χ² trenger den ufullstendige
      gammafunksjonen, og det er numerikk som må prøves mot scipy før den erstatter den.

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
      (`ko/views_tavle.py`); skal den bli KO-lederens, er det `_kan_lede_ko(request)` der og
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

### Vaktlista: gjennomgangen 30. sep. 2026 — staging-sjekken som gjenstår

*En ekstern gjennomgang av `/vaktliste/` (Fable), kontrollert mot koden 30. sep. 2026. Dommen:
mekanikken er solid; det som svikter er **begrepene** og **inngangen** for hver rolle. Pulje
1 (rettinger uten avgjørelser), 2 (drift automatisk ved vaktens start), 3 (ordboka på
skjermen), 4 («Del ut») og 5 (veiledningen) er levert — CHANGELOG 30. sep. og 1. okt.*

- [ ] **Staging-sjekken for hele gjennomgangen — til slutt, etter siste pulje** (André,
      30. sep.: «ta med disse sjekkene til slutten av hele økten av puljer»). Punktene står
      i `docs/TESTSJEKKLISTE_VAKTLISTE.md` og vokser med hver pulje:
      - **Pulje 1** (`902f918`): §3 — `test-vl-fore` lander på «Mitt korps»; §7 —
        kompetansene som avkryssinger (prøv på telefon, AFØR + VFØR overlever en lagring),
        e-posthintet per nivå, «Ikke plassert» med korpsvelgeren.
      - **Pulje 2** (`d0c6439`): §10 — lista går i drift av seg selv ved start, én gang,
        audit uten bruker, fila én gang; en liste uten start går ikke i drift av seg selv.
      - **Pulje 3** (`7c35f33`): §3/§4/§5 og punktet «Ordboka» — de nye ordene overalt på
        `/vaktliste/`, «Koble til delt konto» med hint, og at lagring, fjerning, skift og
        pauser på en enhet fortsatt virker (adressene ble rørt av byttet og rettet).
      - **Pulje 4** (`6cec714`): §4 «Del ut» og §8 «Vakten»/«Del ut» — merket og knappen på kortet,
        vinduet, `test-vl-full` som deler ut, tømming som gjør plassene åpne for alle, og
        sluttsteget i planleggeren. Tilgangsmatrisen §16 har en ny rad.
      - **Pulje 5**: §1 «Veiledningen» — lenken i vaktlinjen, egen del pekt ut per rolle,
        og at den leses på telefon.

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
- [ ] **Lokale variabler limt inn med `+` skannes ikke for escaping.** Datafeltene gjør
      det fra 26. sep. 2026 (`core/tests_js_konkatenering.py`, alle JS-filene), men
      `+ merke` der `merke` er bygget lenger oppe, fanges ikke — 131 slike, flest i KO.
      Motmiddelet er oppførselsprøver med fiendtlige data gjennom den ekte inngangen, som
      KO og backlog har. Vaktlistas `mkPlanlegger()`/`mkBelastning()` (`hode + \`…\` +
      linjer`, funnet 15. sep.) er av denne sorten; verdiene er lokalt bygget markup, så
      det er ikke et hull i dag. Skal det lukkes helt: en oppførselsprøve per bygger som
      mangler en, heller enn en liste over 131 navn — KO hadde en slik liste med 32 navn,
      og ingen av dem ble noen gang lest.
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
- [ ] **`style-src-attr 'unsafe-inline'` — attributtene.** Elementene er stengt 14. okt. 2026
      (`style-src-elem` med nonce). Igjen: **216 `style="…"` i malene og 104 i JS-bygget
      markup** (header, brukermeny, bjelle og personvernlenka er tatt) — `core/tests_inline_stiler.py` er sperrehaken og ber om at taket senkes når
      tallet går ned. Malene: klasser i stilarket. JS: klasser, eller `el.style.x = …` etter
      innsetting der verdien er dynamisk (tavla, planleggeren) — CSSOM rammes ikke av CSP.
      **Pass på `display:none`**: JS som viser med `el.style.display = ''` virker ikke mot en
      klasse som skjuler. **Mål før og etter** med `getComputedStyle`, også ved `:hover` —
      et attributt vinner over Bootstraps hover, en klasse gjør det ikke uten to klasser.
      Og start `runserver` på nytt mellom målingene: med `--noreload` er malene bufret,
      og «etter» måler da de gamle (14. okt.). Når tallet er null: `style-src-attr 'none'`, og fjern
      `'unsafe-inline'` fra reserven `style-src`. Største filer: `patients/index.html` (33),
      `server_status.html` (23), `statistikk.js` (24).

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
      - [ ] `docs/PERSONVERN_DOKUMENTASJON.md` — A.2 (Scaleway: hele databasen), A.9 (hel
            backup 90 dager, modulfilene 730 dager offsite), A.10, A.11/A.6 (fil på e-post,
            offline drift)
      - [ ] `CLAUDE.md` — backup-avsnittet og hvor modellene bor
- [ ] **Merk resten av CHANGELOG — 182 av 505 entries står uten søkeord.**
      13. sep.–14. okt. er gjort (36 temaer); halen er 12. sep. og bakover, 140 av dem
      fra august.
      `python manage.py changelog --umerkede` viser hva som gjenstår.

      **Det haster ikke, og det er verdt å si hvorfor:** de merkede er de siste fem
      dagene, som er der oppslagene faktisk gjøres. For halen duger `manage.py changelog`
      alene — 505 titler mot 10 000+ linjer. Ta den når du likevel er inne i en gammel
      entry.

      **Merk med en eksplisitt tittel-til-tema-tabell, ikke nøkkelordsgjetting**, og la
      skriptet kreve at hver tittel i tabellen finnes — ellers blir en skrivefeil en
      stille ikke-merking. Mønsteret ligger i CHANGELOG 17. sep.

      Temaer som ennå ikke finnes, og som halen trolig trenger: `patients/registrering`,
      `patients/arkiv`, `patients/registre`, `statistikk/kilder`, `oppdrag/verdimengder`,
      `oppdrag/arkiv`, `vaktliste/besetning`. **Registrer dem i `TEMAER` i samme commit
      som du merker entriene**, aldri foran — testen håndhever rekkefølgen.

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

- [ ] **Vurder om `vaktliste/CLAUDE.md` kan krympes videre — seksjon for seksjon.** 1. okt.
      2026 (pulje 5) ble «Plassen og skiftet» og «Belastning» skrevet om til reglene, og fila
      gikk fra 44 733 til 37 624 tegn; taket i `FOR_STORE_I_DAG` fulgte ned. Kontroller først
      at hendelsesforløpet står i CHANGELOG, og behold regelen og den ene setningen som gjør
      den huskbar. Den største igjen er «Planleggeren» (6 229), men den er for det meste
      tabeller som allerede er korte. Målet er under `MODUL_TEGNGRENSE` (22 000), og det er
      ikke sikkert det er verdt det — en fil med dårligere begrunnelser er ikke en forbedring.

- [ ] **4. De mindre** (§3 i notatet), når man er i nærheten: brukeradmin importerer
      pasientregistrene (3.1), `/admin/` samlet i én URL-fil (3.2), skimene
      (3.3), `core/views.py` delt (3.7). 3.5 (`VaktArkiv`) skal **ikke** ryddes —
      signaturen. 3.6 og 3.8 tas underveis, ikke som egne runder.

### GDPR-gjennomgang

Fase 0–5 er gjennomført. Begrunnelsene og de varige beslutningene ligger i
[`docs/PERSONVERN_DOKUMENTASJON.md`](./docs/PERSONVERN_DOKUMENTASJON.md); hva som ble gjort
står i [`CHANGELOG.md`](./CHANGELOG.md). Behandlingsansvarlig er Kverneland Røde Kors, med
André som systemansvarlig (A.1, v1.19, 8. okt. 2026).

#### DPIA, fritekst og adresse — se [`docs/NOTAT_DPIA_OG_FRITEKST.md`](./docs/NOTAT_DPIA_OG_FRITEKST.md)

*Utløst 14. sep. 2026 av spørsmålet om AMK-adresse kan legges i `Oppdrag.fritekst`.
Notatet bærer begrunnelsene; her står bare arbeidet.*

**Premisset som måtte rettes:** dokumentasjon fritar ikke for DPIA. A.12 bygger ikke på at
vi har dokumentasjon, men på tre andre ben — ingen direkte identifikatorer, ikke stor
skala, ingen profilering. Det tyngste (skala) holder. Det første gjør ikke det hvis adresse
legges inn, og **A.12 har selv skrevet utløseren**: «særlig dersom nye moduler tar inn
direkte identifikatorer».

- [ ] **Adressefeltet: eget felt, ikke i fritekst — og aldri i `Lokasjon`.**
      `Lokasjon.navn` fryses i `ArkivertOppdrag.lokasjon_navn`, som inngår i
      SHA-signaturen: en adresse lagt der er låst i 24 måneder ved konstruksjon
- [ ] **Skriv om A.6-argumentet** hvis adressen kommer inn. «Oppdraget har ingenting, og
      re-identifisering krever kunnskap utenfra» holder ikke når kunnskapen utenfra ligger
      i raden

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
      **Kjør gjennom `testportal.sanitet.net`, ikke Railway direkte**, med klienter som sender
      `Accept-Encoding: gzip, br` og `If-None-Match` som en nettleser: andelen 304 er halve
      lasten (`core/etag.py`). Cloudflare-proxyen er av fra 14. okt. 2026, så DNS-navnet og
      Railway direkte gir nå samme vei — men kjør gjennom navnet likevel, det er det brukerne gjør.
      *Akseptanse:* rapport som viser at konfigurasjonen tåler 25 samtidige uten degradering.

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
forbindelser. Tas opp igjen kun hvis `WEB_WORKERS` settes til 4 eller mer. Gjennomgått
på nytt 17. okt. 2026 med samme svar: PgBouncer gjør veien *inn* til databasen billigere,
ikke arbeidet den gjør der inne — og det som koster på vakt er spørringene per poll
(«Skalering mot 2027»). Blir tilkoblingstallet problemet en dag, er Djangos egen pool
med psycopg 3 det lettere alternativet, uten en ny tjeneste — eget punkt samme sted.


## Ideer / backlog

### Rapportmodul — se [`docs/FORSLAG_RAPPORTMODUL.md`](./docs/FORSLAG_RAPPORTMODUL.md)

**Forslag, ikke besluttet** (14. sep. 2026). En `/rapport/`-modul med to deler:

- [ ] **Del 1: timeregnskap og betaling.** *Anbefales.* Timer per mannskap, korps og
      rolle, med kr/time og sum per korps. Mye finnes alt —
      `vaktliste.belastning.belastning_per_person()` regner timene, og `Vaktpost.probono`
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

### Backlog-modulen (`/backlog/`)

Levert 17. sep. 2026: innspill klassifisert som bug eller ønske, løst-flagg, filter på type,
status og modul. Modulens egne regler står i [`backlog/CLAUDE.md`](./backlog/CLAUDE.md).

- [ ] **Del ut tilgang til de som skal bruke den.** Ingen har en `ModulTilgang`-rad på
      `backlog` i dag, så bare global admin ser modulen. Tre nivåer i matrisen: «ser
      backloggen», «melder inn, retter sitt eget», «leder backloggen, setter løst».

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

- [ ] **Løpende posisjon: kartet viser kilden** — steg 6 i
      [`docs/PLAN_LOPENDE_POSISJON.md`](./docs/PLAN_LOPENDE_POSISJON.md). Portalen sender
      løpende posisjon og svar på «Hent posisjon» til kartets vanlige bilmarkør, og tipset i
      kartet sier fortsatt «stemplet 4 min siden». Kartet (kart-sanitet) får et valgfritt felt
      `kilde` (`stempling`, `lopende`, `forespurt`) og ordet «posisjon … siden»; portalen
      sender feltet først når kartet tar imot det — sjekk hvor streng valideringen der er.
- [ ] **Løpende posisjon: DPIA-delen før hovedbryteren slås på i prod** — §7 i planen, og
      A.12 i personverndokumentasjonen sier at punkt 7 på Datatilsynets liste trolig utløses
      når den er på. Bygget 19. okt. 2026 med bryteren **av**. Prosedyren for mannskapet skal
      si det samme som bilskjermen («Posisjon sendes til KO hvert …», «KO hentet posisjonen»).
- [ ] **Eksterne aktører i «Ny hendelse»-skjemaet?** I dag krysses de av i hodet etter at
      hendelsen er opprettet. Er det vanlig at Brann alt er varslet når hendelsen føres, kan
      avkryssingen også stå i skjemaet — samme `services.varsle`, kalt etter opprettelsen.
      Tas når noen savner det.
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
      en flate og ikke en datamodell. Utskriften (`/ko/utskrift/`) dekket den én dag, til
      André 13. okt. 2026 gjorde papiret til et øyeblikksbilde av aktiv vakt (siste 8 t).
      Tas den opp: helst i `/ko/`, med samme vaktvelger som konsertplanleggerens «Etterpå».

*Pulje 3 (ressursoversikten) er levert 17. sep. 2026 — se CHANGELOG. Projeksjonen, den
tredje kilden (`ko.Ressursstatus`) og tavla i venstre kolonne. Rutingflagget er **ikke**
bygget; det flyttet til `/lag/`-punktet nederst, der det hører hjemme.*

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

- [ ] **`/lag/` — se [`docs/FORSLAG_PARK.md`](./docs/FORSLAG_PARK.md)** (27. sep. 2026).
      Lagenes utfallsregistrering uten innlogging, via én lenke i tiltakskortet i Bliksund.
      Avklart i fire runder (§2, B1–B23). **Alle tre puljene er levert** (27.–28. sep. 2026, se CHANGELOG);
      modulens regler står i `park/CLAUDE.md`. Igjen:
      - [ ] **Personvern for `/lag/` når modulen er ferdig — før lansering** (André, 27. sep.
            2026, B23). `PERSONVERN_DOKUMENTASJON.md` A.6 får en rad for registreringene, og
            risikobildet i `FORSLAG_PARK.md` §4.6–4.7 skrives inn: portalens første side uten
            innlogging, og at den kan vise KOs plassering av lagene så lenge
            `park-ko-posisjon` er på. Skrives mot det som faktisk ble bygget, ikke mot
            forslaget. **Lagringstiden er alt skrevet inn i A.9** (730 dager, 28. sep. 2026).
      - [ ] **Lansering, når personvernet over er skrevet:** (1) `staging` → `main` — /lag er
            ikke i produksjon, og det venter på Andrés klarsignal; (2) lag en ny lenke på
            `/lag/` i prod og legg den inn i tiltakskortet i Bliksund. Den gamle `/park/`-lenka
            er borte med omdøpingen, og tokenet vises bare én gang (`park-lenke-en-gang`),
            så lenka må lages og limes inn i samme økt; (3) gi `park: skriv_leder` til den
            som skal sette opp og rydde, og `park: les` + `statistikk: les` til dem som skal
            se fanen «Lag».
      - [ ] **Frosne statistikktall for Lag har ingen frist ennå.** Registreringene slettes
            etter 730 dager, men settet i `core.VaktStatistikk` står i detalj. Løses av punkt 4
            (sensitiv-merket) under vaktavslutningen — står her så /lag ikke regnes som ferdig
            på personvernsiden før det er gjort.

- [ ] **MULIGHET: KO-tavla viser stedet laget registrerer fra ved siden av der KO plasserte
      det** (André, 27. sep. 2026, `FORSLAG_PARK.md` B16). Står laget på Parkscene på tavla og
      registrerer fra Village, vet laget noe KO ikke vet. **Ikke i park-leveransen:** André
      besluttet samme dag at KO ikke gjør noe med registreringene (B15), og dette krever at KO
      leser park (`ko` → `park`, riktig retning). Tas det opp: vis avviket, flytt aldri laget
      — tavla er KO sin plassering.
- [ ] **MULIGHET: QR-kode for parklenka** (André, 27. sep. 2026: «ikke noe QR-kode nå»).
      Lenka ligger i et tiltakskort i Bliksund. Blir QR aktuelt: `segno` (ren Python, SVG
      server-side, utskrift uten JS) framfor et JS-bibliotek i `static/vendor/`. Merk at
      lenka bare vises én gang (`FORSLAG_PARK.md` §4.1), så QR-en må lages i samme øyeblikk.

### Brukere, e-post og roller — se `docs/BESLUTNING_BRUKERE_OG_EPOST.md`

Besluttet 14. aug. 2026: invitasjon som registreringsvei, selvbetjent passord-reset for
personlige kontoer, admin-reset beholdt for alle. Ingenting bygget ennå.

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

### Rollemodellen — se `docs/BESLUTNING_ROLLEMODELLEN.md`

**Stigen** er `les` < `les_alle` < `skriv_handling` < `skriv_full` < `skriv_leder` — se
«Tilgangskontroll» i `CLAUDE.md`, som er fasiten.

- [ ] **VURDER: `leder`-nivå («admin light»).** Utsatt 28. aug. 2026 — bruken finnes,
      behovet gjør ikke. En vaktleder som skal kunne arkivere en vakt, se arkivet og
      redigere navneregistrene, uten å være global admin. Det irreversible (nullstilling,
      kollaps, brukeradmin, backup) forblir admin per §3.3. Se §3.1 i notatet.

      **Tas opp igjen når noen faktisk skal ha nivået** — et tomt nivå er lett å dele ut i
      god tro, og gir automatisk mer den dagen det fylles. Nivået ble lagt til 28. aug. og
      reversert samme dag, fordi grunnen («senere koster det en migrasjon») ikke holdt:
      `choices` er en `non_db_attr`, så migrasjonen er `-- (no-op)`. Kostnaden ligger i å
      bestemme innholdet, ikke i skjemaet.

### Oppdragsmodulen: `skriv_handling` for bilkontoer

- [ ] **`skriv: handling` for bil-/ambulansekontoer.** Nivået er definert; bruken er
      planlagt i `docs/BESLUTNING_OPPDRAGSMODULEN.md` §5.1. Invarianten fra §3.2 er
      **skjerpet, ikke slakket**, for å tåle offline: kroppen har et lukket skjema på to
      nøkler (`klienttid`, `idempotency_key`), og alt annet gir 400. Det er testbart ved
      uttømming, i motsetning til «husk å utelate fritekst».

### Kartkoblingen — videre

- [ ] **Skal kartet også få posisjonsdelingen?** Portalen vet nå om en bil deler, har slått
      av, er nektet eller ikke har meldt seg (4. okt. 2026, `Enhet.posisjonsdeling`), og
      kartet kunne tegnet markøren grå for «av» i stedet for å la den bli stående på siste
      kjente sted. Det er én melding til (`core/kartkobling.py`), og kartet er et eget repo
      med egen plan. Tas opp når flaten i KO er prøvd på en vakt — generalprøven §1.

### Pasientmodulen — småting

- [ ] **Skal tavla og lista dele «mine»-tilstand?** `mineOnly` og `boardMineFilter` er
      to uavhengige variabler, så valget følger deg ikke mellom fanene. Merk at de gjør
      forskjellige ting: lista *filtrerer bort* andre, tavla *dimmer* dem. Det taler for
      å la dem være uavhengige. Krever en avgjørelse, ikke en fiks.

### Skalering mot 2027 — se `docs/RUNBOOK_VAKT.md` §3c

Gjennomgang 13. aug. 2026, med 1000 pasienter og peak 100 brukere som premiss.

- [ ] **Vurder: sesjonsskrivingen ved hvert poll — databasen er den første flaskehalsen,
      ikke gunicorn** (André, 4. okt. 2026: «usikkerhet igjen på om vi har nailet planen
      for skalering»; gjennomgang av lasten på en 48-timers vakt. Talt opp lag for lag
      17. okt. 2026, på spørsmålet «konkret hva kan vi gjøre for å hjelpe med databasen»).
      Sesjonene ligger i databasen (ingen `SESSION_ENGINE` er satt), og
      `SESSION_SAVE_EVERY_REQUEST=True` gjør at **hvert** `/api/endringer/`-kall hvert
      2,5 s skriver en rad til `django_session`. Ett poll er **sju lesinger og én
      skriving** mot Postgres: `SELECT 1` fra `conn_health_checks`, sesjonsraden, brukeren,
      `session_timeout_hours` (`AppSetting.get`, én spørring hver gang), kontoens portaler
      (`PortalMiddleware`), aktive moduler og tilgangsradene (begge cachet per brukerobjekt,
      så **én** `ModulTilgang`-spørring uansett antall områder — notatet fra 4. okt. sa én
      per område), og `UPDATE django_session`. **Skrivingen er den som koster:** Postgres
      skriver aldri over en rad, den lager en ny versjon og lar den gamle ligge til
      autovacuum, og `expire_date` er indeksert, så hver oppdatering går i indeksen også.
      Med ~20 KO- og sentralbordfaner er det ~8 sesjonsskrivinger i sekundet i 48 timer,
      over en million radversjoner på én liten tabell. Runbooken §2 sier selv at flere
      workers ikke hjelper når basen er treg — de styrer hvor mange som kan *vente*
      samtidig, ikke hvor fort det ventes på svarer — og dette er der den blir det først.
      Redis (vakt-modus) tar endringsnummeret og cachen, men **ikke sesjonene**.
      Web-laget har stor margin (~10 forespørsler/s i ro mot 2 × 4).
      - **Mål før du velger** — generalprøven §8 (`docs/GENERALPROVE.md`): døde rader på
        `django_session`, tilkoblinger og svartid med det reelle antallet faner åpne i en
        time. Er tallene friske der, er dette en forbedring og ikke en forutsetning.
      - **Tiltak 1, hovedtiltaket: forny sesjonen sjeldnere, ikke ved hvert poll.** Slå av
        `SESSION_SAVE_EVERY_REQUEST` og flytt fornyelsen inn i egen middleware — Django
        lagrer da bare når noe i sesjonen er endret. `DynamicSessionTimeoutMiddleware` må
        skrives om uansett: `set_expiry` markerer sesjonen endret ved hvert kall.
        `BrukerAktivitetMiddleware` har alt 60 s oppløsning av akkurat den grunnen. To
        regler er mulige, og valget tas når punktet tas opp: *strupe* — forny utløpet bare
        når det er over ti minutter siden sist; ingen endret oppførsel, skrivingene per
        fane går fra 1 440 i timen til 6, anbefalt først. *Bare mennesker* — forny bare på
        handlinger, eller når pollet bærer `X-Portal-Inaktiv` under ett minutt; da er
        «8 timer» åtte timer uten at noen rørte fana, men headeren teller ikke
        musebevegelser, så en operatør som bare *ser* på skjermen i åtte timer blir logget
        ut. `cached_db` alene er ikke nok — `SESSION_SAVE_EVERY_REQUEST` skriver til basen
        uansett backend.
      - **Tiltak 2: `SESSION_ENGINE = cached_db`.** Fjerner sesjonslesingen når Redis er
        på; databasen er fortsatt sannheten, så en tømt Redis mister ingenting, og i
        lavkostnad-modus med én worker og LocMemCache virker det like godt. Én linje i
        settings.
      - **Tiltak 3: cache `session_timeout_hours`** med ett minutts TTL — én spørring per
        forespørsel i hele portalen for et tall admin endrer kanskje én gang i året. Samme
        mønster som `core/stats_cache.py`.
      - **Tiltak 4: autovacuum-terskel per tabell på `django_session`** (`ALTER TABLE …
        SET (autovacuum_vacuum_scale_factor …)`, én `RunSQL`-migrasjon) — *etter* tiltak 1,
        ikke i stedet for: med skrivingen på plass er det å moppe gulvet mens krana står på.
      - **Tiltak 5, det eneste før generalprøven: tell spørringer per sti.** «Tregeste
        stier» viser P95, ikke antall spørringer; tallene over er talt for hånd gjennom
        koden. Et tellefelt i metrikkene (`core/middleware.py`), eller `pg_stat_statements`
        om Railway lar oss slå den på. Det er målingen de fire andre avgjøres på.
      - **Etter 1–3:** fem lesinger og ~0 skrivinger per poll — ~0,03 skrivinger/s med 20
        faner mot ~8 i dag. Portaloppslaget i `PortalMiddleware` kunne også caches, men det
        er en sikkerhetssjekk: fjernes kontoen fra portalen, skal det virke med én gang.
        Står til målingen sier noe annet.
      - Ikke før vakta om målingen er grønn: fastfrysingen gjelder. Men tiltak 1–3 er små
        nok til å ligge ferdig på en gren, testet på staging, *før* generalprøven — da er
        målingen «skal vi slå sammen det som ligger der», ikke «skal vi bygge noe».

- [ ] **Se på: én fane poller på vegne av alle i samme nettleser** (André, 17. okt. 2026:
      «noe å se på, ikke nødvendigvis implementere»). En KO-operatør med to skjermer har to
      faner som spør `/api/endringer/` om det samme hvert 2,5 s, og KO har alt en kanal
      mellom vinduene (`koMeldTilstede`, `KO_FOLGER_PULS_MS` i `ko-hendelser.js`). Med en
      leder valgt per nettleser (`BroadcastChannel`, eller en lås i `localStorage`) spør
      én fane og deler svaret, og KOs poll halveres. Det løser ikke databaseproblemet over
      — det deler det på to — og det er klientkode med egne feilmoder: lederen som lukkes
      eller sovner på mobil, en følger som aldri får svar, to nettlesere på samme PC som
      ikke ser hverandre. Vurder først etter tiltak 1–3 over, og bare om målingen sier at
      antall faner er det som teller.

- [ ] **Vurder: psycopg 3 i stedet for psycopg2, med Djangos innebygde tilkoblingspool**
      (17. okt. 2026, «hva har vi å hente på psycopg 3?»). Gir ingen fart — begge går
      gjennom libpq, og det som koster er spørringene, ikke driveren — men tre ting:
      (1) `OPTIONS['pool']` erstatter `conn_max_age=600`. I dag holder hver tråd sin egen
      tilkobling i ti minutter uansett last (~12 i vakt-modus); med poolen låner tråden for
      forespørselen, og tallet følger lasten med et tak du setter. Det er det lettere
      alternativet til PgBouncer (F8 over), uten en ny tjeneste. Poolen og `conn_max_age`
      kan ikke stå sammen — Django nekter å starte. Standard i `psycopg_pool` åpner fire per
      prosess fra start, så sett `min_size`/`max_size` selv; backupklokka låner fra samme
      pool hvert minutt, så ikke sett taket til to. (2) psycopg2 vedlikeholdes, men får
      ingen nye funksjoner. (3) `kart-sanitet` kjører alt `psycopg[binary]` 3.3 på samme
      Django 5.2 — én driver å kjenne. **Kostnaden er liten,** gjennomgått 17. okt.:
      `requirements.in` (`psycopg[binary,pool]`, `pip-compile` med hasher — Django velger
      psycopg 3 selv når den er installert), settings, det ene direkte `psycopg2`-kallet i
      `verifiser_migrasjoner._kobling` (samme nøkkelord til `connect`), testfiksturen
      `PSYCOPG_TEKST` i `core/tests_kommando.py` (gjentakelsen kommer fra libpq og finnes i
      begge, ordlyden er litt annerledes), og README-punktet «psycopg2-binary feiler ved
      installasjon» kan trolig strykes — psycopg 3 har hjul for Windows og 3.13. Rå SQL
      finnes seks steder utenom tester, alle med `%s`; ingen bruk av `psycopg2.extras`.
      Hele suiten mot PostgreSQL i CI og migrasjonsprøvene lokalt. **Etter generalprøven,**
      som egen rolig endring — et driverbytte er akkurat det man ikke vil feilsøke på en
      vakt.

- [ ] **Rett runbooken §4: backupklokka bruker ikke en «advisory lock»** (funnet 17. okt.
      2026). `docs/RUNBOOK_VAKT.md` §4 sier «Backup-scheduler (advisory lock i DB sørger
      for at kun én worker kjører)»; `core/backup/klokke.py` bruker en radlås,
      `select_for_update(nowait=True)` på planraden. Radlåsen er transaksjonsbundet og
      dermed trygg også bak en pooler i transaksjonsmodus — en sesjonsbundet advisory lock
      hadde ikke vært det. Ikke farlig, men nøyaktig den typen påstand som gjør noen usikre
      på om en pooler er trygg.

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

### Fra gjennomgangen mot 48-timersvakta — 6. okt. 2026, til vurdering

*Gjennomgang av modulene og kartkoblingen mot en vakt på to døgn med mange ledd. Fem av
elleve forslag ble lagt hit som «vurder», og overleveringen kom til 6. okt. etter en skisse;
resten ble avvist eller finnes alt (depotet er et eksternt system; vær er i kartet;
sektorer/flere KO: nei). Ingen av dem er bestilt.*

- [ ] **VURDER: stillingsbilde i KO — innlesingsside, ikke rapport.** André, 6. okt. 2026:
      «vi skal kanskje eksperimentere litt med den. Men er usikker.» Ikke selve vaktskiftet —
      det løses muntlig, med overlapp, i rolige perioder. Vinklingen er byttene *inne i*
      skiftene over to døgn: KO-leder tilbake fra pause, utalarm fra to til én kl. 03,
      bilskjermen som bytter hender, den som åpner KO kl. 04 og skal lese seg opp. Det som
      går tapt da er ikke hendelsene og oppdragene (de står i loggen og på tavla), men
      **forventningene**: «arrangøren ringer om gjerdet rundt 03», «bil 56 lader til 02:30».
      Tre av fire bolker er lesing av det som finnes; den fjerde er en festet linje med frist:

      ```
      ┌─ Stillingsbilde ───────────────────────────── lør 01:52 ─┐
      │ ÅPNE HENDELSER   H12 Rød Parkscene  Lag 4, Lag 1  siste 01:40 │
      │ VENTER PÅ        ⏳ 02:30 Bil 56 ferdig ladet        — Kari   │
      │                  ⏳ 03:00 Arrangør ringer om gjerdet  — Ola    │
      │                  ⏳ 06:00 Lag 4 avløses (planlagt slutt)       │
      │ RESSURSER        56 Ledig · 57 Fremme H12 · Lag 3 Hovedpost   │
      │ NESTE I PROGRAM  02:00 Club, behov 2 lag · 03:00 stengt        │
      │                     [ Jeg har lest meg opp — overtar KO ]      │
      └───────────────────────────────────────────────────────────────┘
      01:53 ⚙ Vaktskifte KO: Per overtok. 2 åpne hendelser, 3 venter-på.
      ```

      Nytt er bare fristen på en festet linje (`Logglinje.festet_*` finnes) og systemlinja
      ved kvittering — den svarer tre uker senere på «hvem satt i KO da H14 eskalerte»;
      sidebaren sier bare hvem som har KO oppe *nå*. Ingen ny modul, ingen ny tabell.
      **Fella:** et «Venter på» ingen fyller ut kl. 03 er verre enn ingenting, fordi den
      påtroppende stoler på en tom liste — samme felle som park-registreringen. Første prøve
      er derfor om operatørene fester linjer med frist på en generalprøve, før vinduet tegnes.
- [ ] **VURDER: pasientflyten gjennom leddene — lag → bil → post → ut.** `Patient` har
      ingen peker til oppdrag, enhet eller hendelse, og ingen rad i park, oppdrag eller
      pasientregistreringen peker på en annen. Den smaleste formen er ett nedtrekksfelt på
      pasienten («innlevert fra oppdrag»), aldri pasientnummer i KO-loggen eller på
      oppdraget, så art. 9-dataene blir værende hos posten. **Åpent valg:** André ser
      personvern- og helseopplysningsrisiko ved å ha med hele flyten for en pasient
      (6. okt. 2026), og pekere mellom KO, oppdrag og pasienter er alt utsatt med vilje i
      KO-forslaget. Tas opp sammen med DPIA-gjennomgangen, ikke før.
- [ ] **VURDER: hviletid mellom to skift for samme person.** Timetak og belastningsgrenser
      finnes, og overlapp er sitt eget punkt over — men ingen regel sier noe om *mellomrommet*
      mellom to skift. Over to døgn med nattskift er det der tretthet oppstår. Formen ville
      vært som overlappsperren: en advarsel i planleggeren og en sperre ved frysing, ikke i
      databasen.
- [ ] **VURDER: forpleining — hvor mange spiser når.** Avledet av skiftene: antall til stede
      per måltidstidspunkt, per ressurs eller korps, som en visning i vaktlista. Ingen
      allergi- eller kostdata i portalen — det er helseopplysninger (art. 9) og hører ikke
      hjemme her; kjøkkenet får tallet, ikke navnene.
- [ ] **VURDER: masseutsending til mannskapet (SMS eller push).** I dag går lista på e-post
      (`vaktliste/fil.py`) og lydvarselet til bilene; nødnett dekker det operative. SMS krever
      en ny leverandør og en ny transport ut av Railway, og `Mannskap.telefon` ville fått et
      nytt formål som må inn i personverndokumentasjonen. Nytten er mobilisering av reserve
      og «møt opp»/«evakuer» til de som sover — vurder om nødnett og telefonkjeden alt dekker
      det.
- [ ] **VURDER: tiltakskort og sjekklister i portalen.** Utgangspunktet er nei: tiltakskortene
      ligger i Bliksund (arrangørens system, lenken til `/lag/` går derfra), og en kopi i
      portalen er utdatert ved første revisjon. **Bonusen med et separat system er at
      tiltakskortene står om portalen går ned** (André, 6. okt. 2026) — det argumentet gjelder
      uansett hvor gode kortene i portalen hadde vært.

### Dokumentgjennomgang — når funksjonaliteten nærmer seg ferdig

Fire dokumenter beholdes fordi de ikke er arbeidslister: de er referanse, formelle
dokumenter eller prosedyrer man følger under press. Nettopp derfor koster det å la dem
drive fra koden. Gjennomgangen tas **når funksjonaliteten vi bygger nå er på plass** —
ikke før, for da ville den bare måttet gjøres om igjen.

Funnene under er allerede kartlagt, så jobben er avgrenset når den skal gjøres.

- [ ] **`docs/RUNBOOK_VAKT.md`** (469 linjer) — leses under vakt, på papir eller egen
      skjerm. En feil URL her oppdages i verste øyeblikk.
      - Sjekk at tersklene i §3 stemmer med ytelsesarbeidet fra 13. aug. (1000 pasienter,
        100 brukere)

- [ ] **`docs/DEPLOY_GUIDE.md`** (205 linjer) — prosedyre for nytt miljø.
      - Legg inn `EMAIL_*`-variablene for AHASend i variabeltabellen — de mangler helt

- [ ] **`docs/PERSONVERN_DOKUMENTASJON.md`** (809 linjer) — formelt art. 30-dokument som
      kan fremlegges for Datatilsynet. **Skal ikke slankes eller foldes inn i TODO.**
      Gjennomgangen her er en annen øvelse enn for de tre andre: verifiser at hver
      påstådte kontroll faktisk er reell i koden.
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

- [ ] **Testene som påstår ordlyden i kildekoden: om lag 40–50 igjen** (talt 19. okt. 2026).
      CLAUDE.md sier «påstå ikke at en literal kodelinje står der» — men
      `assertIn('const drift = iDrift();', kropp)` i `vaktliste/tests_xss.py`,
      `'async function withSubmitGuard('` i `patients/tests.py` og
      `"addEventListener('hide.bs.modal'"` i `core/tests_modalfokus.py` gjør det. Skriv dem om
      til oppførsel (tabellen i CLAUDE.md) **én modul om gangen, når modulen likevel røres** —
      ikke som en egen pulje, der hver omskriving er en ny test uten en endring å prøve den mot.
- [ ] **`vaktliste/tests_xss.py` er 6 400 linjer, og om lag 90 % er ikke XSS.** Rundt 55 klasser
      prøver tegning og oppførsel (`BemanningskurveTests`, `PlanleggerfanenTests` …). Navnet
      skjuler hva fila dekker, og den som leter etter planleggerens tester finner dem ikke.
      Del etter fane når fila røres neste gang; XSS-skanningen blir igjen.
- [ ] **XSS-skanneren og URL-gjennomgangen finnes i flere kopier.** Skanneren av mal-strenger
      står i `vaktliste/tests_xss.py`, `oppdrag/tests_xss.py` og `patients/tests_xss_stats.py`
      med samme `ESCAPING_CALLS`; bare oppdrag utleder byggerne (`_byggerkandidater`). Den
      rekursive `get_resolver()`-gjennomgangen står fem steder (`tests_modul_dekorator`,
      `tests_sikkerhet_runde2`, `tests_sikkerhet_pulje4`, `tests_moderator`, `tests_urls_admin`).
      Påstandene er ulike og skal være det; motoren bør være én, som `uten_js_kommentarer()`
      ble 19. okt. 2026. Utledningen fra oppdrag er den som skal vinne.
- [ ] **Ugyldige escape-sekvenser i fire testfiler** (`'\`'`, `'\d'`, `'\s'` i vanlige strenger):
      `ko/tests_plan_js.py`, `oppdrag/tests_xss.py`, `vaktliste/tests_pauser_js.py`, `vaktliste/tests_xss.py`.
      Python 3.12 gir `SyntaxWarning`, en senere versjon `SyntaxError` — da faller hele fila
      ut av suiten som én importfeil. `r''`-strenger gir samme mønster; `core/tests_skyggede_tester.py`
      viser hvor (den demper advarselen for å kunne lese filene).
- [ ] **Flere tunge `setUp` kan bli `setUpTestData`.** `TilgangsBasis` ga −27 % på 689 tester
      19. okt. 2026. Neste i køen: `KoOgParkTests` og `HjelperneOgStedeneTests` i
      `core/tests_portalisolasjon.py`, og `OppdragBasis` i `oppdrag/tests_views.py` (arvet av 29
      klasser). **Ikke** det som rører filer, cache eller `ModuleSettings` — det må stå i `setUp`.
- [ ] **Noe å se på: en ukentlig kjøring med falsk klokke.** Suiten kjører alltid «nå», så en
      test som bare feiler på sommertidsdagen, 29. februar eller kl. 23:59 sees først den dagen.
      Fire slike ble rettet 19. okt. 2026. En planlagt CI-jobb med `libfaketime` på de datoene
      ville funnet resten — men vil gi støy først, og den støyen må noen rydde.

- [ ] **Rate-limit GET på pasient- og oppdragsarkivet.** `arkiv_detalj_view` i
      `patients/views_arkiv.py` og `oppdrag/views_arkiv.py` regner full statistikk ved
      GET, men bøtta der gjelder bare DELETE. Statistikkens arkivendepunkt fikk sin
      (`statistikk:arkiv-full-stats`). Begge er admin-only og leser rader som ikke endres,
      så eksponeringen er lav — én linje per view.
- [ ] Flytte sesjonsdelen til en admin-side
- [ ] Testene er massive, kan vi komprimere dem? (kjøretiden er løst: 500 s → 15 s via
      PASSWORD_HASHERS under test. Gjenstår evt. å redusere *antall* tester)
- [ ] Vurder `argon2-cffi` for sterkere passord-hashing i produksjon (i dag PBKDF2)

- [ ] **Skal grovsortering og sted inn i oppdragsarkivet?** Payloaden er signaturlåst, så
      nye felt krever en versjonert payload — nye arkiver får dem, gamle verifiserer som
      før. Mønsteret finnes allerede (`varslet_modus` og `behandlet_at` står i payloaden
      bare når de er satt). Egen beslutning, ikke en oppgave som bare kan gjøres.
- [ ] **Sikkerhetsgjennomgangen: L6, L8, L12, L18, L22 gjenstår.** Lavpunktene fra
      `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md` som ble satt til «senere». De er
      navngitt der, med begrunnelse for hvorfor de ikke hastet.
