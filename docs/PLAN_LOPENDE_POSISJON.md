# Plan: løpende posisjon fra bilene, og «Hent posisjon» fra KO

*Utkast 19. okt. 2026. Ikke bygget. Bestilt av André samme dag:*

> «Oppdatering posisjon: Ha løpende oppdatering fra bare stempling til regelmessig
> oppdateringer av posisjon. Fra en går inn på /oppdrag/ så skal oppdateres hver 5 min og på
> haste og akutt oppdrag så skal det være hver 30 sekund. Og så må KO kunne hente posisjon i
> kartet på enkelt ressurs og alle ressurser, nå snakker vi ikke lag bare de enheter som
> bruker /oppdrag. Det skal kunne endres av admin, både slå det helt av til slik det er nå og
> justere dem på individuelt nivå på akutt, haste, vanlig, plassering og drift, eller gruppere
> dem. Og endre den om de ikke er på noe heller. Ikke glem å oppdater personvern
> dokumentasjon, vi gjør dette på grunn av operativ hensyn med berettiget interesse.»

## 1. Hva som finnes i dag (lest i koden 19. okt.)

| Hva | Hvor | Merk |
|---|---|---|
| Bilskjermen holder en fix i minnet med `watchPosition` | `startPosisjon()` i `static/js/oppdrag-enhet.js` | Aldri i `localStorage`. Høy nøyaktighet, `maximumAge` 30 s |
| Posisjonen **rir på stemplingen** — under to minutter gammel, ellers ingen | `posisjonTilKo()`, `posisjonForStempling()` | Stemplingen venter aldri på GPS |
| «Send posisjon»-knappen: ett uttrykkelig trykk, går til kartets **delte** posisjoner (oransje, «OBS») | `posisjon_view` i `oppdrag/views.py`, `kartkobling.send_delt_posisjon` | Direkte, ikke `on_commit`; 424 når kartet ikke tok imot |
| Bryteren «Del posisjon» per skjerm, på som standard, nullstilles ved neste vakt | `delerPosisjon()`, `notePaVakt()` | For unntak, ikke et fritt valg under tjeneste (A.6) |
| KO ser **tilstanden** (deler / av / nektet / utilgjengelig), aldri koordinatene | `Enhet.posisjonsdeling`, `services.noter_posisjonsdeling` | Header `X-Posisjonsdeling` på pollet |
| Bilen poller **hvert 15. sekund** og får `X-Enhet-Pa-Vakt` også på 304 | `pollOgSynk`, `lastMine()` | Her kan en forespørsel fra KO ri — ingen ny forbindelse |
| Bilinnstillingene hentes hvert 5. minutt, redigeres av admin i «Valglister → Bilen» | `lastBilinnstillinger`, `oppdrag.verdier.bilinnstillinger()`, `bilinnstillinger_view` | Lydvarselets terskler per hastegrad bor her i dag |
| Kartet: **én rad per enhet som overskrives**, nyeste vinner, slettes 24 t etter siste melding | `portal/lagring.py` i kart-sanitet (`lagre`, `BEHOLD`) | Ingen historikk. Kartet poller hvert 30. s; en bil er «fersk» i 15 min og grå i 6 t |

**Det som mangler er altså tre ting, ingen ny mekanisme:** en klokke i bilskjermen som sender
uten en stempling, en vei for KO til å be om en fix, og et sted admin setter intervallene.

## 2. Hva som bygges

### 2.1 Løpende sending fra bilskjermen

- **Intervallet velges av bilens tilstand** — det høyeste av de påbegynte oppdragene hennes
  avgjør: Akutt, Haster, Vanlig, Plassering, Drift, eller **uten oppdrag** (på vakt, men ikke
  på noe). Standard: **Akutt og Haster 30 s, alt annet 5 min.**
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

To ting kan hjelpe og bør vurderes:

- **Screen Wake Lock** (`navigator.wakeLock`, iOS 16.4+, Chrome): holder skjermen på mens
  bilen er på vakt og har et påbegynt oppdrag. Koster batteri; bilene står ofte i lader.
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
  kartet hvert 30. sekund på akutt og haster, hvert 5. minutt ellers. KO ser at den deles.» —
  med tallene **hentet fra innstillingene**, ikke skrevet i malen. Prosedyren for mannskapet
  må si det samme.
- **Bryteren** står som før — for unntak. KO ser fortsatt tilstanden, ikke koordinatene.
- **«Hent posisjon» fra KO** er en ny handling og vurderes for seg: den sender én fix uten at
  mannskapet trykker. Forsvarlig fordi den bare virker på vakt med bryteren på, og fordi
  posisjonen bare går dit de løpende alt går. Bør skjermen vise «KO hentet posisjon 21:14»?
  (Spørsmål 3.)
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

## 6. Spørsmål til André før steg 1

1. **Uten oppdrag og passiv vakt:** skal en bil i passiv vakt (bakvakt, sover) sende hvert
   5. minutt, eller ikke løpende i det hele tatt? Forslag: egen rad «passiv vakt», standard av.
2. **Wake Lock:** skal bilskjermen holde skjermen på mens bilen har et påbegynt oppdrag?
3. **«Hent posisjon»:** skal mannskapet se at KO hentet posisjonen, og skal det stå i
   KO-loggen («KO hentet posisjon fra Haugesund 56»)?
4. **Knappene i KO, ikke i kartet** — greit, eller er en knapp i kartet viktig nok til å åpne
   en vei fra kartet til portalen?
