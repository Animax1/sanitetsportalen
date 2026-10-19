# Plan: løpende posisjon fra bilene, og «Hent posisjon» fra KO

*Utkast 19. okt. 2026, oppdatert samme dag med Andrés svar (§6). **Steg 1–5 bygget samme dag** (§0); steg 6 (kartet) og DPIA-delen (§7) står igjen. Bestilt av André:*

> «Oppdatering posisjon: Ha løpende oppdatering fra bare stempling til regelmessig
> oppdateringer av posisjon. Fra en går inn på /oppdrag/ så skal oppdateres hver 5 min og på
> haste og akutt oppdrag så skal det være hver 30 sekund. Og så må KO kunne hente posisjon i
> kartet på enkelt ressurs og alle ressurser, nå snakker vi ikke lag bare de enheter som
> bruker /oppdrag. Det skal kunne endres av admin, både slå det helt av til slik det er nå og
> justere dem på individuelt nivå på akutt, haste, vanlig, plassering og drift, eller gruppere
> dem. Og endre den om de ikke er på noe heller. Ikke glem å oppdater personvern
> dokumentasjon, vi gjør dette på grunn av operativ hensyn med berettiget interesse.»

## 0. Bygget 19. okt. 2026 — og der det ble annerledes enn planen

Steg 1–5 i §5 er bygget, med **hovedbryteren av**. Regelen står i `oppdrag/posisjon.py`,
endepunktene i `oppdrag/views_posisjon.py`, klokka i `static/js/oppdrag-enhet.js`
(`lopendeTikk`), kortet i `static/js/oppdrag-kort.js` (`hentingTilstand`). Fem avvik fra
planen, hvert med grunnen:

| Planen sa | Bygget | Hvorfor |
|---|---|---|
| `intervallFor(oppdrag, innstillinger)` som egen funksjon i bilens JS | **Serveren regner ut intervallet** og sender det i header `X-Posisjon-Intervall` på pollen (også 304) | Serveren er bremsen og må ha regelen uansett. To kopier av samme regel glir fra hverandre — og da sender bilen enten oftere enn serveren tar imot, eller sjeldnere enn admin bestemte. Bonus: en endring i innstillingene, eller at 113 setter bilen i passiv, virker innen 15 s, ikke 5 min |
| Merket for «Hent posisjon» i cachen, TTL 2 min | **Tre felt på `Enhet`**: `posisjon_bedt_at`, `posisjon_bedt_av`, `posisjon_mottatt_at` (`oppdrag/0038`) | Prod kan gå med en cache per prosess (`LocMemCache`, `WEB_WORKERS`); da kunne KO ha bedt i én prosess og bilen pollet en annen. På enheten følger feltene ETag-en og endringsnummeret, så kortet i KO oppdateres av seg selv. Aldri koordinater |
| «Fra alle»: én linje med «hvor mange som svarte» | Linja skrives **når KO ber**: «Hent posisjon fra alle i Ambulanse: 4 av 5 biler kan svare» | Svarene kommer opptil 15 s senere og hver for seg; en linje som ventet på dem måtte vært rettet etterpå. Handlingen som logges er spørsmålet — svaret står på kortet. «Kan svare» er de som er på vakt med deling på |
| «Hent alle» i hodet på ressursoversikten | **«Hent posisjon fra alle» per gruppe** (enhetstype), som skisse A André valgte | Skissen viste den i gruppehodet. Med bare én gruppe står knappen alene øverst |
| Sendingen i `on_commit` eller som 202 | **Direkte**, med kartkoblingens 3 s tidsavbrudd og pause etter feil | Ingenting skrives før kartet har svart, og KO skal bare se «mottatt» når kartet tok imot. Et kart som er nede holder en tråd i høyst 3 s i minuttet (`PAUSE_S`) |

**Bremsen måler mot intervallet *nå*** (funnet under byggingen): planen sa «cache-nøkkel per
enhet», og en sperre med levetid ville stått i fire minutter etter en sending på «uten
oppdrag» — også etter at bilen rykket ut på akutt. Nøkkelen holder derfor tidspunktet.

**Ikke gjort ennå:** steg 6 (kartets `kilde` og «posisjon … siden»), og DPIA-delen for
posisjon (§7), som skal være skrevet **før hovedbryteren slås på i prod**.

## 1. Hva som fantes (lest i koden 19. okt.)

| Hva | Hvor | Merk |
|---|---|---|
| Bilskjermen holder en fix i minnet med `watchPosition` | `startPosisjon()` i `static/js/oppdrag-enhet.js` | Aldri i `localStorage`. Høy nøyaktighet, `maximumAge` 30 s |
| Posisjonen **rir på stemplingen** — under to minutter gammel, ellers ingen | `posisjonTilKo()`, `posisjonForStempling()` | Stemplingen venter aldri på GPS |
| «Send posisjon»-knappen: ett uttrykkelig trykk, går til kartets **delte** posisjoner (oransje, «OBS») | `posisjon_view` i `oppdrag/views.py`, `kartkobling.send_delt_posisjon` | Direkte, ikke `on_commit`; 424 når kartet ikke tok imot |
| Bryteren «Del posisjon» per skjerm, på som standard, nullstilles ved neste vakt | `delerPosisjon()`, `notePaVakt()` | For unntak, ikke et fritt valg under tjeneste (A.6) |
| KO ser **tilstanden** (deler / av / nektet / utilgjengelig), aldri koordinatene | `Enhet.posisjonsdeling`, `services.noter_posisjonsdeling` | Header `X-Posisjonsdeling` på pollet |
| Bilen poller **hvert 15. sekund** og får `X-Enhet-Pa-Vakt` også på 304 | `pollOgSynk`, `lastMine()` | Her kan en forespørsel fra KO ri — ingen ny forbindelse |
| Bilinnstillingene hentes hvert 5. minutt, redigeres av admin i «Valglister → Bilen» | `lastBilinnstillinger`, `oppdrag.verdier.bilinnstillinger()`, `bilinnstillinger_view` | Lydvarselets terskler per hastegrad bor her i dag |
| **Skjermen holdes alt våken** (Screen Wake Lock, 9. okt. 2026) — hentes på nytt ved hvert appbytte og hver samtale, og skjermen sier fra når iOS nekter | `startVaakenLaas()`, `skjermSkalHoldesVaaken()`; `oppdrag/tests_bilen_wakelock.py` | Første utkast av denne planen foreslo Wake Lock som noe nytt — det fantes. Rettet etter at André spurte |
| Kartet: **én rad per enhet som overskrives**, nyeste vinner, slettes 24 t etter siste melding | `portal/lagring.py` i kart-sanitet (`lagre`, `BEHOLD`) | Ingen historikk. Kartet poller hvert 30. s; en bil er «fersk» i 15 min og grå i 6 t |

**Det som mangler er altså tre ting, ingen ny mekanisme:** en klokke i bilskjermen som sender
uten en stempling, en vei for KO til å be om en fix, og et sted admin setter intervallene.

## 2. Hva som bygges

### 2.1 Løpende sending fra bilskjermen

- **Intervallet velges av bilens tilstand** — det høyeste av de påbegynte oppdragene hennes
  avgjør: Akutt, Haster, Vanlig, Plassering, Drift, eller **uten oppdrag** (på vakt, men ikke
  på noe). Standard: **Akutt og Haster 30 s, alt annet 5 min.**
- **Passiv vakt sender ikke løpende** (André, 19. okt.): «med mindre de har fått et oppdrag
  de har trykket rykker ut på som ikke er plassering. Det vil si Akutt, Haster, Drift.» Regelen:
  en bil i passiv vakt sender bare mens den har et **påbegynt** oppdrag (Rykker ut og videre,
  til Ledig) med hastegrad Akutt, Haster eller Drift — og da med det intervallet hastegraden
  har. Varslet, avventet eller på Plassering: ingenting. **Vanlig er med** (André, svar 5: «nei
  jeg glemte den ut») — altså Akutt, Haster, Vanlig og Drift.
  Modusen leses som i dag (`gjeldende_modus`), så det er den bilen *står* i nå som avgjør.
- **Bare når det allerede sendes i dag:** koblingen er satt opp, bilen er **på vakt**, og
  bryteren «Del posisjon» er på. Av vakt eller bryteren av: ingenting, som nå.
- **Ny sti, ikke «Send posisjon»:** `POST /oppdrag/api/posisjon/lopende/` (`skriv_handling`,
  bare enhetskonto, lukket kropp `{posisjon}`). Den går til kartets **vanlige** bilmarkør
  (`kartkobling.send_enhet`), ikke til «OBS: Posisjon delt» — en bil som oppdateres hvert
  30. sekund skal ikke stå oransje. «Send posisjon» blir som den er: et uttrykkelig «se meg».
- **Ingen kø uten nett.** En gammel posisjon er verdiløs; det neste intervallet sender den
  nye. Stemplingenes kø er urørt.
- **Ingen sending uten en fersk fix** (samme regel som stemplingen, men strammere: under
  intervallet, høyst 2 min). Er GPS-en død, sendes ingenting — tilstanden sier «utilgjengelig».
- **Serveren er bremsen, ikke klienten:** en enhet kan ikke sende oftere enn sitt intervall
  minus litt slakk (cache-nøkkel per enhet), og stien har egen rate-limit-gruppe. En skjerm
  med feil klokke eller to faner åpne skal ikke kunne fylle kartet.
- **Sendingen skjer etter svaret, ikke i det**: ingenting lagres i portalen, men kallet mot
  kartet kan ta opptil 3 s (`TIMEOUT_S`). Med 30 biler hvert 30. s er det én forespørsel i
  sekundet mot kartet — greit, men den skal ikke holde en web-worker. Samme `on_commit`-grep
  som stemplingen, eller svar 202 og send etterpå.

### 2.2 «Hent posisjon» fra KO — én enhet, eller alle

- **Knappene står i KO, ikke i kartet.** Koblingen går bare fra portalen til kartet, og kartet
  svarer aldri portalen med data (`CLAUDE.md` i kart-sanitet). En knapp i kartet ville vært en
  ny retning — et kall fra kartet inn i portalen — og det er en større beslutning enn denne.
  KO har kartet oppe ved siden av; knappen i ressursoversikten er der KO alt jobber.
- **Per bilkort** («Hent posisjon» i besetningspanelet eller som ikon) og **«Hent alle»** i
  hodet på ressursoversikten. Bare enheter på vakt med koblingen på; lagene er utenfor, som
  bestilt.
- **Mekanikken rir på pollet:** KO setter et merke per enhet (cache, TTL 2 min). Neste poll
  fra bilen — innen 15 s — får header `X-Posisjon-Onsket`, også på 304, og bilskjermen sender
  en fersk fix på den løpende stien. Ingen ny forbindelse, ingen push.
- **KO ser at det kom fram** gjennom kartet (markøren flytter seg). Kom det ikke fram innen
  tiden, viser kortet det samme ordet som i dag: «nektet», «utilgjengelig» eller «av».
- **Tilgang:** `skriv_full` i oppdragsmodulen, som resten av det operatøren gjør med en
  bil. «Hent alle» har egen rate-limit.

### 2.3 Innstillingene — admin

- **Plassering: «Valglister → Bilen»**, der lydvarselets innstillinger alt står, og som bilen
  alt henter hvert 5. minutt. Admin-only, som den fanen er i dag (`bilinnstillinger_view`, PUT).
- **Feltene:** en hovedbryter («Løpende posisjon» av = slik det er nå: bare stempling og
  knappen), og sekunder for **Akutt, Haster, Vanlig, Plassering, Drift og Uten oppdrag**.
  «Gruppere» er en hjelp i skjemaet: en avkrysning «samme for alle» som fyller feltene, og
  rader som kan settes like — lagringen er alltid én verdi per tilstand, så ingen regel
  gjemmer seg i grupperingen.
- **Lagring:** `AppSetting`, per portal (`get_i_portal`/`set_i_portal`), auditlogget av
  `core/signals.py` — hvem som endret sporingsfrekvensen er nøyaktig det man vil kunne svare
  på. Grenser: **15 s til 60 min** per felt; 0 eller tomt er «ikke løpende i denne tilstanden».
- **Klokka i bilen leser intervallet fra serveren**, så en endring virker innen 5 min uten at
  noen laster siden.

### 2.4 Kartet (kart-sanitet)

- Tipset sier i dag «stemplet 4 min siden». Med løpende posisjon er det feil ord: det blir
  «posisjon 30 s siden», og meldingen får et valgfritt felt `kilde` (`stempling`, `lopende`,
  `forespurt`) som kartet viser. Bakoverkompatibelt — mangler feltet, er det `stempling`.
- **Ingenting annet endres i kartet:** fortsatt én rad per enhet, nyeste vinner, 24 t. Kartet
  poller hvert 30. s, så en bil på akutt vises høyst ~45 s gammel. Grå etter 15 min passer
  med 5-minutters intervallet.

## 3. Begrensningen som må sies høyt

**Nettleseren sender bare mens `/oppdrag/` er åpen og skjermen er på.** iOS og Android
stanser JavaScript og GPS i en fane som ligger i bakgrunnen eller når skjermen låses. En bil
der telefonen ligger i lomma, sender ikke — den viser siste posisjon, og blir grå etter
15 minutter. Det er ikke en feil i planen, det er hva en nettside kan; en app er en annen sak.

**Skjermen holdes alt våken** (Wake Lock, 9. okt. — se §1), og det er det som gjør planen
gjennomførbar: klokka kjører så lenge låsen holder. Det som gjenstår er når den *ikke* holder
(iOS i strømsparing, telefonen lagt bort), og der hjelper:

- **Tilstanden «gammel»:** KO-kortet kan vise «sist 12 min siden» når en bil på akutt ikke har
  sendt på lenge — samme idé som tilstandsordene i dag, uten koordinater.

## 4. Personvern — det som må endres, og hvorfor

**A.6, «Posisjon og sted til kart.sanitet.net», må skrives om, ikke utvides.** Avveiningen der
bygger på at behandlingen er **«hendelsesstyrt (ved stempling, ingen løpende sending)»** — det
blir usant. Rettslig grunnlag er fortsatt **berettiget interesse, art. 6 nr. 1 f**: operativ
oversikt over egne ressurser og mannskapets sikkerhet. Men inngrepet er større, og avveiningen
må stå på egne bein:

- **Interessen** er sterkere enn før for akutt og haster: å sende nærmeste bil, og å finne en
  bil som ikke svarer på samband.
- **Nødvendigheten** er grunnen til at frekvensen følger hastegraden: 30 s der minuttene teller,
  5 min ellers, og admin kan slå det av. Fortsatt **bare siste posisjon**, ingen historikk,
  24 t i kartet, ingenting lagret i portalen.
- **Forventning og åpenhet:** bilskjermen må si det. Linja i bunnen blir «Posisjon sendes til
  KO hvert 30. sekund på akutt og haster, hvert 5. minutt ellers» — med tallene **hentet fra
  innstillingene**, ikke skrevet i malen — og «KO hentet posisjonen 21:14» etter en henting.
  Prosedyren for mannskapet må si det samme.
- **Bryteren** står som før — for unntak. KO ser fortsatt tilstanden, ikke koordinatene.
- **«Hent posisjon» fra KO** er en ny handling og vurderes for seg: den sender én fix uten at
  mannskapet trykker. Forsvarlig fordi den bare virker på vakt med bryteren på, og fordi
  posisjonen bare går dit de løpende alt går, **og fordi den er åpen begge veier**: skjermen
  sier «KO hentet posisjonen 21:14», og hver henting står i KO-loggen med hvem (§6).
- **Erklæringen på `/personvern/`** henter fristene fra koden (`core/personvern.py`) — de nye
  intervallene skal hentes derfra også, ikke skrives inn.
- **DPIA bør vurderes før dette går i drift.** Datatilsynets liste over behandlinger som krever
  vurdering av personvernkonsekvenser nevner systematisk overvåking og sporing av lokasjon.
  Frivillige er ikke ansatte, men løpende posisjon under tjeneste er nærmere den lista enn en
  posisjon ved stempling. `docs/NOTAT_DPIA_OG_FRITEKST.md` er stedet å ta det.

## 5. Rekkefølgen

| Steg | Hva | Merk |
|---|---|---|
| 1 | Innstillingene (`AppSetting` per portal), i bilinnstillingene, fanen «Bilen». Standard **av** til steg 5 er gjort | Ingenting skjer før admin slår det på |
| 2 | Den løpende stien på serveren, med bremsen per enhet | Tjenestelaget tungt mutert: intervall, på vakt, bryter, bremse |
| 3 | Klokka i bilskjermen: intervallet etter tilstanden, fersk fix, ingen kø, linja som sier det | Regelen `intervallFor(oppdrag, innstillinger)` som egen funksjon |
| 4 | «Hent posisjon» / «Hent alle» i KO, merket på pollet | Testes gjennom den ekte pollen |
| 5 | Personvern A.6, erklæringen, prosedyren — **før** hovedbryteren slås på i prod | |
| 6 | Kartet: `kilde` og «posisjon … siden» | Egen push i kart-sanitet |

## 6. Andrés svar (19. okt. 2026), og det som står igjen

| # | Spørsmål | Svar |
|---|---|---|
| 1 | Passiv vakt | **Ikke løpende**, med mindre bilen har trykket Rykker ut på et oppdrag som ikke er Plassering: Akutt, Haster, Drift — og Vanlig (svar 5) (§2.1) |
| 2 | Wake Lock | «Ja ideelt sett» — **finnes alt** på `/oppdrag/` fra 9. okt. (§1, §3) |
| 3 | Ser mannskapet at KO hentet, står det i loggen? | Valgt fra skissene (Artifact «Hent posisjon — skisser»): **A** (knappen per bil og «fra alle», svaret på kortet), **B2** (klokkeslett i bunnlinja på bilskjermen) og **C3** (hver henting logges) — se under |
| 4 | Knappene i KO, ikke i kartet | **Ja** |
| 5 | Vanlig i passiv vakt | **Med** — «nei jeg glemte den ut». Passiv vakt sender på påbegynt Akutt, Haster, Vanlig og Drift |
| 6 | «Hent posisjon» på en bil i passiv vakt | **Ja** — «men det er risiko at bilens mobil/nettbrett ikke er på nettsiden». Kortet sier da «Kom ikke fram — skjermen er trolig ikke åpen. Meld på samband» etter 45 s |

**Svaret på 3, slik det bygges:**

- **Bilskjermen (B2), med «KO» og ikke «kartet»** (André: «det skal stå KO. Det er lettere å
  forstå»). Bunnlinja blir «Posisjon sendes til KO hvert 30. sekund på akutt og haster, hvert
  5. minutt ellers», med tallene fra innstillingene, og etter en henting en linje til:
  «KO hentet posisjonen 21:14». Samme ordbruk i «Send posisjon» og i personverndokumentasjonen
  — mannskapet forholder seg til KO, ikke til hvilket system KO ser det i.
- **KO-loggen (C3): hver henting logges** (André: «Vi har jo laget funksjonalitet for å hente fra
  alle og hver enkelt, og jeg vil ha det logget»). En systemlinje med hvem i KO, aldri
  koordinatene. **I loggstrømmen alltid, og i hendelsen i tillegg** når bilen står på et oppdrag
  som hører til en — samme regel som «OBS: Posisjon delt» (`POSISJON_DELT`). «Fra alle» gir
  **én** linje, ikke én per bil. Ny kode i `ko/systemlinjer.py`, `POSISJON_HENTET`, med
  begrunnelse i `KODER`. *Bygget:* «Hent posisjon: Haugesund 56» og «Hent posisjon fra alle i
  Ambulanse: 4 av 5 biler kan svare», med operatøren som forfatter — antallet er de som *kan*
  svare, ikke de som svarte (§0).


## 7. DPIA

André, 19. okt.: «Vi skal skrive en DPIA, vi har personverndokumentasjonen som vi skal bygge
DPIA fra, det er vel lurt?» — **Ja.** `docs/NOTAT_DPIA_OG_FRITEKST.md` §1 sa det samme
14. sep.: dokumentasjonen er ikke en DPIA, men den er det meste av grunnlaget for en.

**Hva personverndokumentasjonen alt dekker av art. 35(7):**

| Art. 35(7) | Krav | Hvor det står i dag |
|---|---|---|
| a | Systematisk beskrivelse: behandlingene, formålene, den berettigede interessen | A.3–A.7, A.9 — protokollen etter art. 30 |
| b | Nødvendighet og forholdsmessighet | Spredt: avveiningene i A.4 og under kartkoblingen i A.6 |
| c | **Risiko for de registrertes rettigheter og friheter** | **A.12 er en risikovurdering for *systemet*** (sikkerhet, tilgjengelighet), ikke for *den registrerte*. Det er hovedgapet |
| d | Tiltak, garantier, sikkerhetsmekanismer | A.10, A.11, A.14, A.15 |

**Forslag til form:** én DPIA for portalen og kartet samlet, i `docs/DPIA.md`, med én del per
behandling — pasientregistreringen (helseopplysninger, art. 9), oppdrag og fritekst, KO-loggen,
mannskap og vaktliste, og **posisjonen** — fordi risikoen ligger i *sammenstillingen*: posisjon
alene er en bil, posisjon og vaktliste sammen er en navngitt person. Hver del: beskrivelse (lenke
til A.x, ikke kopi), nødvendighet, **risikoene sett fra den registrerte** (sannsynlighet ×
konsekvens), tiltakene, restrisiko, og om forhåndsdrøfting med Datatilsynet (art. 36) trengs.
Til slutt konklusjon, hvem som har vurdert, og når den skal revideres (C.4).

**Rekkefølge:** posisjonsdelen skrives før hovedbryteren slås på i prod (steg 5 i §5); resten
kan følge. A.12 får en lenke dit, og den gamle vurderingen «DPIA ikke påkrevd» erstattes.
