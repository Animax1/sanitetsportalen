# Forslag: `/park/` — lagets utfallsregistrering

> **Pulje 1, 2 og 3 er bygget** (27.–28. sep. 2026; statistikkfanen «Lag» som pulje 3): modellen, parksiden uten innlogging,
> forhåndsvalget, angre, grensene, backup — og oppsettet på `/park/` med lenker, sletting,
> verdimengdene og bryterne på portalinnstillingene. Modulens regler står i
> `park/CLAUDE.md`, historien i `CHANGELOG.md`.

Status: **bygget — alle tre puljene; personverndokumentasjonen gjenstår før lansering (B23).** Første utkast 27. september 2026 fra staging `8327d8f`;
André svarte i fire runder samme dag, og svarene står som **besluttet** under (B1–B23). §9 er
tom — André: «Vi starter ikke kode før vi har alt av punkter på plass».
Arbeidslista er `TODO.md`.

Underlaget som allerede sto skrevet, og som dette notatet bygger på:

| Hvor | Hva det sa om park |
|---|---|
| `TODO.md`, «Skalering mot 2027» (13. aug. 2026) | Egen modell, ikke rader i `Patient`. Skriveendepunkt uten innlogging, rate-limit per token, kvittering — aldri data |
| `TODO.md`, KO-seksjonen | Problemstilling, lokasjon, utfall. Ingen stempling, ingen pålogging. Egen statistikk-kilde, ingen kobling til `/pasienter/`. Rutingflagget hører til her |
| `docs/RUNBOOK_VAKT.md` §3c | Lagene **poller ikke** — de registrerer uten å lese |
| `docs/FORSLAG_KO.md` §1, §3.2, §6, §8 | «Enheter produserer tid, lag produserer utfall.» Flagget på `Ressursgruppe`. Intet nummer i `H`/`O`-familien. Tallene heter «registreringer», ikke «pasienter» |

---

## 1. Hva park er, og hva det ikke er

Et lag går rundt på arrangementsområdet. Det plastrer en blemme, gir vann til en som er
varm, følger en beruset til samleplassen, eller tilkaller bil. **Ingenting av dette blir
registrert i dag**, med mindre personen havner i `/pasienter/` — og da er det sykestua som
registrerer, ikke laget. Statistikken ser de som kom inn, ikke de som ble tatt hånd om ute.

`/park/` er **en tellemaskin på én side**, ikke et journalsystem:

| Park er | Park er ikke |
|---|---|
| «Sandnes 2.1 hjalp tre med skrubbsår ved Parkscene, alle gikk videre selv» | En pasient. Ingen navn, ingen alder, intet nummer som sies høyt |
| Én side med nedtrekk, på en telefon | Et skjema man fyller ut etterpå |
| Skrive-bare for laget. Det ser en kvittering | En liste laget kan bla i |
| Tall til statistikken «Lag», for ledelsen | Et verktøy KO arbeider i, eller grunnlag for oppfølging av en enkeltperson |

**Den siste raden er premisset for resten.** Så lenge ingen enkeltregistrering skal kunne
følges opp, trenger raden ingen personopplysninger — og da trenger endepunktet ingen
pålogging. Glipper premisset («vi må kunne finne igjen han med hodeskaden»), er det
`/pasienter/` det gjelder.

---

## 2. Besluttet 27. sep. 2026 (André)

| # | Hva | Beslutning |
|---|---|---|
| B1 | Fritekst | **Ingen.** Bare nedtrekk og antall |
| B2 | Tilgangsnivåer | `les`, `skriv_leder` og global admin — som ellers i portalen |
| B3 | Lenken | **Én lenke**, lagt i et tiltakskort i Bliksund, der tilgangen allerede er avgrenset. Settes opp og fjernes av `skriv_leder` og admin, med **oppetid fra og til** |
| B4 | Lagvalget | Laget velger seg selv i et nedtrekk. **Valget huskes på telefonen** til neste gang siden åpnes |
| B5 | Tokenet | «Best practice går foran»: tilfeldig token, bare hashen lagres (§4.1) |
| B6 | Problemstillinger | Egen liste, satt opp av `skriv_leder` og admin, **startverdier fra `/pasienter/`** |
| B7 | Utfall | Egen liste, satt opp av **admin** |
| B8 | Personen | Ingen kjønn, ingen alder |
| B9 | Antall | En registrering kan gjelde **flere med samme problemstilling**. Etter registrering starter en ny, med lag og sted husket — stedet kan endres. **Alt av nedtrekk på én side** |
| B10 | Lokasjon | **Lista arves fra `oppdrag.Lokasjon`** — de samme stedene KO bruker. Laget kan alltid endre forhåndsvalget (§5) |
| B11 | Angre | Ja. **5 minutter** som standard, styrt av admin |
| B12 | Statistikk | En egen kilde, **«Lag»** |
| B13 | QR-koder | Ikke nå. Står i `TODO.md` som mulighet |
| B14 | Offline | **Ikke nødvendig** |
| B15 | KO | **KO gjør ingenting med registreringene** (andre runde): «Vi skal bare bruke det for /statistikk for ledelsen å se på.» Erstatter første rundes «KO-tilgang holder» (§7) |
| B16 | Tavla | Å vise stedet laget satte mot stedet KO plasserte det er en **mulighet i `TODO.md`**, ikke en del av denne leveransen — den krever at KO leser park, og B15 sier at KO ikke gjør det nå |
| B17 | Statistikk-tilgang | **Operatørene skal ikke nødvendigvis ha `/statistikk/`**, og tilgangen der kan bli delt opp. Den *er* delt per fane allerede (§7): fanen «Lag» krever `statistikk: les` **og** `park: les`. Ledelsen får `park: les`; operatørene får det ikke |
| B18 | Lenkens levetid | **På tvers av vakter** (spørsmål 2a). Tiltakskortet kan stå; oppetiden er grensen |
| B19 | Forhåndsvalg av sted | **Det nyeste vinner** (tredje runde): «Om KOs plassering er nyeste er det siste, om lagets valg er nyeste brukes det» (§5.1) |
| B20 | Feilregistreringer | `skriv_leder` og admin kan **slette** en registrering fra lista på `/park/`, med grunn, logget. Ikke rette |
| B21 | Måling | Hver registrering lagrer hvor forhåndsvalget kom fra og om laget endret det — så B19 kan vurderes med tall etter generalprøven |
| B22 | Risikovalg | **Alternativene står i §4.7, og det som bringer risiko kan byttes om.** Forhåndsvalget fra KO er en bryter, ikke kode som kommenteres ut |
| B23 | Personvern | `PERSONVERN_DOKUMENTASJON.md` oppdateres **når `/park/` er ferdig**, ikke underveis — men før lansering (`TODO.md`) |
| B24 | Steder skjult for lagene | `skriv_leder` i park kan skjule et sted fra lagenes nedtrekk; bilene ser det som før. Parks egen tabell (`SkjultSted`), ikke et felt i oppdrag. Nye steder vises til noen skjuler dem |
| B25 | Kopier lenken | Trykk i feltet eller på knappen kopierer hele lenken, og siden sier at den ble kopiert |

**Hva B3 og B4 endret fra første utkast.** Utkastet foreslo én lenke per lag, med
begrunnelsen at et nedtrekk ingen kontrollerer er en påstand. André: «det blir svært
komplisert for lagene». Tiltakskortet er stedet lagene allerede slår opp, og én lenke der
er én ting å vedlikeholde. **Prisen skal stå:** hvem som helst med tilgang til
tiltakskortet kan registrere som et hvilket som helst lag, og statistikken per lag er
akkurat så god som valget i nedtrekket. At valget huskes på telefonen (B4) reduserer den
feilen mer enn noe annet — det er det første valget som må være riktig, ikke hvert.

**Hva B14 endret.** Utkastet kalte offline en forutsetning, fordi dekningen er dårligst der
lagene er. André har vurdert det annerledes, og konsekvensen er ærlig: **uten nett feiler
registreringen, og siden sier det.** Den skal aldri late som den lagret. Idempotensnøkkelen
(§3.1) beholdes likevel, fordi en telefon med dårlig dekning sender samme forespørsel to
ganger også når den er på nett.

---

## 3. Datamodellen

### 3.1 `park.Registrering`

| Felt | Merknad |
|---|---|
| `vakt` | Scopet, som alt annet |
| `lenke` | FK til `Parklenke`, `SET_NULL`. Hvilken lenke som ble brukt |
| `ressurs` / `ressurs_navn` | FK til `vaktliste.Ressurs`, `SET_NULL`, **strippes i backupen**; navnet frosset, som `HendelseLag` |
| `problemstilling` | Tekst, validert mot `park.Problemstilling` (B6). Tekst og ikke FK, som `Oppdrag.problemstilling`: navnet er det som telles, og en omdøpt rad skal ikke skrive om historikken |
| `antall` | Heltall ≥ 1, standard 1 (B9). Øvre grense 99 — et tall det er lett å skrive feil |
| `utfall` | Tekst, validert mot `park.Utfall` (B7) |
| `lokasjon` / `lokasjon_navn` | FK til `oppdrag.Lokasjon` + frosset navn, som `Tavleplassering` |
| `registrert_at` | Når raden kom inn. Uten offline er det også når det skjedde — ingen klienttid, ingen `vurder_klienttid` |
| `idempotency_key` | Klientgenerert UUID, unik per lenke. Er også **angre-nøkkelen**, §4.4 |
| `forhandsvalg_kilde` | `ko` / `registrering` / `telefon` / `ingen` — hvor stedet i nedtrekket kom fra (B21) |
| `forhandsvalg_endret` | Om laget byttet sted før «Registrer» (B21). Sammen med feltet over svarer det på om «nyeste vinner» treffer |
| `slettet_at`, `slettet_av_navn`, `slettet_grunn` | B20. Raden står, og statistikken utelater den — en sletting som ikke synes er en statistikk ingen kan etterprøve. Lagets angring sletter raden helt |

**Ingen fritekst er sikkerhetsmodellen, ikke en forenkling** (B1). Et felt som tar imot hva
som helst fra et endepunkt uten innlogging er et felt der et navn havner en travel kveld,
skrevet av noen vi ikke vet hvem er. Med bare nedtrekk kan raden ikke inneholde et navn, og
da kan backupen og statistikken vise den uten pasientmodulens vern.

### 3.2 `park.Parklenke`

| Felt | Merknad |
|---|---|
| `navn` | «Tiltakskort Bliksund» — så den som ser lista vet hvor lenken ligger |
| `hemmelighet_hash` | SHA-256 av tokenet. Selve tokenet lagres ikke (§4.1) |
| `aapen_fra`, `aapen_til` | Oppetiden (B3). Begge påkrevd — en lenke uten slutt er en lenke noen glemmer |
| `opprettet_av` / `_navn`, `opprettet_at` | Hvem, og når |
| `fjernet_at`, `fjernet_av_navn` | «Fjernes» (B3) er en markering, ikke sletting: registreringene beholder sin peker, og lista viser at lenken fantes |
| `sist_brukt_at` | «Ingen registreringer på fire timer» kan bety en død lenke |

**Lenken er ikke bundet til en vakt** (B18). Registreringen havner på vakta som er aktiv når
den sendes, og er ingen vakt aktiv, er siden stengt — selv innenfor oppetiden.

### 3.3 Verdimengdene

| Tabell | Hvem setter opp | Startverdier |
|---|---|---|
| `park.Problemstilling` | `skriv_leder` og admin (B6) | De 21 i `patients.choices.PROBLEMSTILLING`, kopiert inn av migrasjonen |
| `park.Utfall` | Admin (B7) | **Behandlet på stedet** (øverst), Gikk videre selv, Fulgt til samleplass, Tilkalt bil, Avslo hjelp, Overlatt til andre (vakt/politi) |

Begge med `navn`, `rekkefolge`, `er_aktiv` — mønsteret fra `oppdrag.Lokasjon` og
`oppdrag.Problemstilling`. **Kopiert, ikke lest:** park importerer ikke pasientmodulen. Lista
er en startverdi, og fra første endring er den parks egen — to lister som delte kilde ville
endret seg sammen uten at noen ba om det.

### 3.4 Rutingflagget på `Ressursgruppe`

`FORSLAG_KO.md` §3.2 plasserte det her og utsatte det. Med B4 får det én virkning:

> **`registrerer_i_park`** (bool, standard `False`): ressursene i gruppa står i lagnedtrekket
> på `/park/r/`.

Bevisst **ikke** en `choices` med `oppdrag`/`park`/`ingen` — om en ressurs stempler i
`/oppdrag/` avgjøres allerede av `Ressurs.enhet`, og to kilder for samme sannhet er uenige
den dagen det teller.

---

## 4. Siden uten innlogging

### 4.1 Tokenet (B5)

**Tilfeldig token (`secrets.token_urlsafe(32)`), SHA-256 i basen.** Standardmønsteret for
API-nøkler, og bedre enn en signert streng her:

| | Signert (`django.core.signing`) | **Tilfeldig, hash i basen** |
|---|---|---|
| Fjerne én lenke | Krever en rad likevel | Sett `fjernet_at` |
| `SECRET_KEY` roteres | Lenken dør midt i vakta | Upåvirket |
| Basen lekker | — | Hash, ikke token: lenken kan ikke gjenskapes |

**Konsekvensen av best practice er at lenken vises én gang**, i det den lages. Står den ikke
i tiltakskortet da, lages en ny. Å kunne vise den igjen krever at tokenet lagres slik det
kan leses, og da er en lekket base en lekket lenke. Følger av B5 («best practice går
foran») — nevnt fordi det er den delen av valget som merkes i Bliksund.

**Tokenet står i fragmentet: `/park/r/#<token>`.** Alt etter `#` sendes aldri til serveren
— det havner ikke i Railways tilgangslogg, ikke i `Referer`. Siden leser det med JS og
sender det i headeren `X-Park-Lenke`.

### 4.2 Flatene

| Sti | Hvem | Hva |
|---|---|---|
| `/park/` | `skriv_leder`, admin | Oppsettet: lenker (lag, fjern, oppetid), problemstillinger; utfall bare for admin. Lista over registreringene med «Slett» (B20) |
| — | `les` | Ingen egen side. `les` er det som åpner fanen «Lag» i `/statistikk/` (B17) |
| `/park/r/` | **Ingen innlogging** | Skjemaet. Én statisk side |
| `/park/r/api/oppsett/` | Gyldig token | Vaktnavn, lagene, stedene og verdimengdene — ikke noe annet |
| `/park/r/api/sted/?lag=<id>` | Gyldig token | Forhåndsvalget for **ett** lag, med kilde og tid (§5.1) |
| `/park/r/api/registrer/` | Gyldig token | Lagrer, svarer med kvittering |
| `/park/r/api/angre/` | Gyldig token + angre-nøkkel | Sletter én rad innenfor fristen |

De tre under `/park/r/` står i unntakslista i `patients/tests_modul_dekorator.py` med
begrunnelse, som `vaktliste/sw.js`. `ModuleSettings.enabled=False` stenger dem også — det er
nødbryteren om lenken har lekket. Utenfor oppetiden, fjernet lenke og ugyldig token gir
**samme** svar, som `signert_lenke.les()`: forskjellen hjelper bare den som prøver seg.

### 4.3 Siden (B4, B9)

Én side, alt synlig, ovenfra og ned: **Lag · Sted · Problemstilling · Antall · Utfall ·
Registrer.**

- **Lag og sted huskes** i `localStorage`. Ressursene er nye rader for hver vaktliste, så
  valget huskes på **navn** («Sandnes 2.1»), ikke på ID — ellers er det glemt neste vakt.
- **Etter «Registrer»** tømmes problemstilling, antall (tilbake til 1) og utfall. Lag og sted
  står.
- **Kvitteringen** står øverst: «Registrert 21:14 · 3 × Skrubbsår · Parkscene · Gikk videre
  selv», med «Angre» og nedtelling. Pluss en teller: «Sandnes 2.1 har registrert 12 denne
  vakta» — et tall, ikke data, og det som forteller laget at det faktisk kommer fram.
- **Uten nett** sier siden «Ikke lagret — prøv igjen», og beholder valgene.

### 4.4 Angre (B11)

Angre-nøkkelen er `idempotency_key`: en UUID bare telefonen som sendte raden kjenner.
`angre` krever lenken **og** nøkkelen **og** at `registrert_at` er innenfor fristen. En
annen telefon med samme lenke kan ikke angre noe den ikke sendte selv.

Fristen er en `AppSetting`, satt av admin på `/portal-admin/innstillinger/` gjennom
`park/portalinnstillinger.py` — registeret finnes (`core/portalinnstillinger.py`).

### 4.5 Rate-limit og CSRF

- **Per telefon**, den strammeste: siden lager en tilfeldig telefon-ID første gang den åpnes
  (`localStorage`) og sender den i en header. Den identifiserer ingen person, og den er
  grunnen til at ett skript ikke kan bruke opp kvoten for alle lagene.
- **Per lenke**, et tak: `park:registrer`, høyt nok til at alle lagene samlet aldri når det.
  Det fanger misbruk i stor skala, ikke én telefon. Uten grensen per telefon *måtte* denne
  vært lav, og da kunne en lekket lenke stengt ute alle lagene (§4.6).
- **Per IP, bare for ugyldige tokens.** Ikke per IP på gyldige: telefoner på mobilnett deler
  IP-adresser bak operatørens NAT, og på en festival kan ti lag stå bak samme adresse.
- **CSRF**: `csrf_exempt`, begrunnet ved dekoratøren. CSRF verner en innlogget sesjon; her
  finnes ingen. Tokenet går i en egen header, og en egen header utløser en forespørsel om
  lov (CORS preflight) som serveren ikke besvarer — en fremmed side kommer ikke gjennom.

Telefon-ID-en er en påstand fra klienten: et skript kan lage en ny for hvert kall. Den
stopper derfor den ubevisste feilen og det enkle skriptet, ikke den som vet hva han gjør —
**det er taket per lenke, oppetiden og at lenken kan fjernes som stopper ham.**

### 4.6 Trusselbildet

Den første siden i portalen som svarer uten innlogging. **Det reelle hullet er en lenke på
avveie** — skjermbilde, videresending, nettleserloggen på en privat telefon. Tokenet selv
(256 bits) lar seg ikke gjette.

| Den som har lenken kan | Alvor | Det som demper |
|---|---|---|
| Legge inn falske registreringer | Middels — merkes kanskje ikke før sesongrapporten | Oppetiden, fjerning av lenken, taket per lenke, og **«slett alt fra denne lenken etter kl. X»** på `/park/` |
| Stenge ute lagene ved å tømme kvoten | Høy under vakt | Grensen per telefon (§4.5) gjør at taket per lenke kan stå høyt |
| Se hvor KO har plassert hvert lag, fortløpende | Lav til middels | **Risikovalg**, §4.7. Ett lag per kall, men alle kan hentes på under ett sekund |
| Se lagnavn, steder og verdimengder | Lav | — |
| Lese registreringer | Umulig — siden svarer aldri med dem | — |
| Angre andres registreringer | Umulig — krever angre-nøkkelen | — |

Og fire ting som *ikke* er hull, men som må holdes slik — hver med en test:

- **Tokenet fjernes fra adressefeltet** (`history.replaceState`) straks siden har lest det.
  Fragmentet holdes unna serverloggene, men *nettleserloggen* lagrer hele adressen.
- **Viewene under `/park/r/` leser aldri `request.user`.** En portalbruker som åpner siden i
  samme nettleser sender innloggingen sin med; den skal ikke bety noe.
- **Ingen fritekst inn** (B1) — ingen lagret XSS mulig. Navnene som tegnes (lag, steder) er
  satt av `skriv_leder` og escapes som ellers.
- **Ugyldig, fjernet og stengt lenke gir samme svar.**

### 4.7 Risikovalgene og alternativene (B22)

Hvert valg som bringer risiko, med alternativet ved siden av. **Merket i koden** med
`# RISIKOVALG(park-<navn>): … se FORSLAG_PARK.md §4.7` — så `grep RISIKOVALG` finner alle
stedene, og hvert merke peker hit.

| Valg | Nå | Alternativet | Hvordan byttes det |
|---|---|---|---|
| **`park-ko-posisjon`** — forhåndsvalg fra KO-tavla (B19) | **På** | Bare siste registrering og telefonens minne. Siden viser da bare lister, ingen posisjoner | **Bryter på `/portal-admin/innstillinger/`**, uten deploy. Av = endepunktet svarer aldri med KO-kilden, og registeret spørres ikke |
| `park-delt-lenke` — én lenke for alle lagene (B3) | Én lenke | Én lenke per lag: sikker identitet, fjernes per lag, men flere lenker å dele ut (første utkast, §4.1 der) | Modellen tåler det: `Parklenke` får en nullbar `ressurs`. Kode, ikke bryter |
| `park-lenke-en-gang` — lenken vises bare når den lages (B5) | Én gang | Lagret lesbart (kryptert), kan vises igjen — men en lekket base er da en lekket lenke | Kode + migrasjon. Frarådes |
| `park-uten-innlogging` — hele siden | Uten | Delt konto per lag, som bilene. Fjerner alle hullene over, men lagene må logge inn og kontoene forvaltes | Egen modul i praksis. Frarådes med mindre en lenke faktisk misbrukes |

**Hvorfor en bryter og ikke kode som kommenteres ut** for det første valget: kode i en
kommentar kjøres ikke av testene, og har den ligget der et halvt år, virker den ikke den dagen
noen tar den inn igjen. En bryter holder *begge* grenene prøvd hele tiden, og kan snus under
generalprøven eller midt i en vakt av den som ser et problem — ikke av den som har en
utviklermaskin. De tre andre er større valg der en bryter ville vært kompleksitet for et bytte
som neppe skjer; der er merket i koden og raden her nok.

**Å fjerne et valg for godt** er å slette koden bak merket og raden her — merkene står der det
er noe å slette, ikke der det bare er noe å lese.

---

## 5. Lokasjonen (B10)

**Lista er `oppdrag.Lokasjon`** — de samme stedene KO plasserer lag på, vedlikeholdt ett
sted. Park leser dem; `oppdrag` kjenner ikke park. Kanten `park → oppdrag` er ny og får sin
egen test på den importerte siden, som `OppdragImportererIkkeVaktlista`.

### 5.1 Forhåndsvalget: det nyeste vinner (B19)

To kilder, og den ferskeste gjelder:

| Kilde | Hva | Tid |
|---|---|---|
| **KO** | Lagets åpne plassering på tavla (`ko.Tavleplassering`, `til` tom) | `fra` |
| **Laget** | Stedet på lagets siste registrering — fra hvilken som helst telefon | `registrert_at` |

**Begge tidene er serverens.** Det er grunnen til at «lagets valg» er siste *registrering* og
ikke det telefonen husker: telefonens klokke kan stå hvor som helst, og en sammenligning med
en tid fra serveren ville da gitt feil vinner uten at noen så det. Telefonens eget minne
brukes bare når ingen av de to finnes — første registrering, og KO har ikke plassert laget.
Et nedtrekk laget endrer uten å registrere, står uansett på skjermen.

**Regelen løser innvendingen fra første runde.** Tavla som henger etter var et problem fordi
KO alltid ville vunnet. Med «nyeste vinner» taper en gammel plassering mot en ferskere
registrering: KO satte laget på Parkscene 21:00, laget registrerte fra Village 21:30 —
Village. KO flytter laget til Club 22:00 — Club.

**Og forhåndsvalget sier hvor det kom fra**, under nedtrekket: «Fra KO-tavla 22:00» eller
«Sist registrert 21:30». Et ferdig utfylt felt blir ikke lest; en linje som sier *hvorfor*
det står der, blir det oftere.

| Tilfelle | Forhåndsvalg |
|---|---|
| Laget er på en hendelse eller pause (ingen åpen plassering med sted) | Siste registrering |
| Stedet er deaktivert siden | Ingenting — laget velger |
| KO-modulen er slått av | Siste registrering |

**Retningen.** KO gjør fortsatt ingenting med registreringene (B15), og `ko` importerer ikke
park. Men park må lese tavla, og park får ikke importere `ko` — KO står øverst. Løsningen er
et lite register i `core` (`core/ressursplassering.py`), samme idiom som `core/kontokobling.py`:
KO melder inn «åpen plassering for ressurs X, med sted og tid», park spør registeret. Park vet
ikke at KO finnes.

**Endepunktet svarer for ett lag om gangen** (`?lag=<id>`), ikke for alle. Lista over hvor KO
har plassert hvert lag er mer enn siden trenger, selv om de som har lenken er få.

---

## 6. Resten av rammeverket

| Hva | Forslag |
|---|---|
| Modul | `park/module.py`, `nivaaer = ('les', 'skriv_leder')` (B2) |
| Backup | `park/backup.py`. `ressurs`, `lokasjon` og brukerpekerne strippes; navnene er frosset. Plass i `GJENOPPRETTINGSREKKEFOLGE` etter `vaktliste` |
| Arkiv | Ikke i første omgang. Park følger arkiveringen når den flytter til `/portal-admin/` (`TODO.md`), som KO |
| Statistikk | `park/statistikk.py`, fanen **«Lag»** (B12): per problemstilling, utfall, sted, lag, time. Summerer `antall`. Overskriften sier «kontakter», ikke «pasienter» (`FORSLAG_KO.md` §8). Gates på `park: les` — ingen endring i rammeverket (§7) |
| Audit | Lenke laget og fjernet, verdimengdene, og sletting (B20). Registreringene selv logges ikke — de er dataene, ikke en endring av dem |
| Personvern | Ny rad i `PERSONVERN_DOKUMENTASJON.md` A.6: tid, sted, problemstilling, antall — ingen identifikator |

---

## 7. KO og statistikken (B15, B17)

**KO rører ikke park.** Ingen import, ingen visning, ingen handling. Første utkast foreslo
en teller på lagkortet og sletting fra `/ko/`; André: «ingen av de». Det gjør modulen
mindre og fjerner den eneste kanten som ville gått *inn* i park.

**Statistikken trenger ingen endring i rammeverket.** `statistikk/views.py` krever
`statistikk: les` for siden og `har_tilgang(user, h.slug, h.nivaa)` for hver fane
(`lesbare_kilder`). Fanen «Lag» har `slug = 'park'`, `nivaa = 'les'`. Altså:

| Konto | `statistikk` | `park` | Ser «Lag» |
|---|---|---|---|
| Ledelsen | `les` | `les` | Ja |
| Operatør i KO | — | — | Nei, og ser ikke `/statistikk/` i det hele tatt |
| Operatør med statistikk for pasienter | `les` | — | Nei — bare fanene hun har kildetilgang til |
| `skriv_leder` i park | etter behov | `skriv_leder` | Ja, hvis hun også har `statistikk` |

Oppdelingen André nevner — hvem som ser hva i `/statistikk/` — finnes dermed allerede, per
kildemodul. Første utkast foreslo en «alternativ gate» (`ko: les` skulle åpne fanen); den
faller bort med B15 og B17, og det er bra: den ville vært en bakvei rundt nettopp den
oppdelingen.

---

## 8. Puljer

Frysingen er noen uker før vakta (`TODO.md`, «Veien til neste vakt»), og park skal være
prøvd på generalprøven.

| Pulje | Innhold |
|---|---|
| **1 — Modellen og siden** | App, modul, de fire tabellene, rutingflagget, `/park/r/` med lag husket og forhåndsvalg av sted (§5.1, registeret i `core`), angre, rate-limit, backup, modultestene |
| **2 — Oppsettet** | `/park/` (lenker med oppetid, verdimengdene, lista med sletting og «slett alt fra lenken etter kl. X»), angrefristen og `park-ko-posisjon`-bryteren i portalinnstillingene |
| **3 — Tallene** | Statistikk-kilden «Lag» |

**Anslag: 3 økter**, pluss litt for registeret i §5.1.

---

## 9. Det som gjenstår før koden

Ingenting. Tredje runde besvarte forhåndsvalget (B19) og feilregistreringene (B20); fjerde
runde målingen (B21), risikovalgene (B22) og personvernet (B23).
