# Forslag: `/park/` — lagets utfallsregistrering

Status: **forslag, ikke besluttet.** Skrevet 27. september 2026 fra staging `8327d8f`.
Ingen kode er skrevet; §9 er spørsmålene som må besvares først. Arbeidslista er `TODO.md`.

Underlaget som allerede sto skrevet, og som dette notatet bygger på i stedet for å gjenta:

| Hvor | Hva det sier om park |
|---|---|
| `TODO.md`, «Skalering mot 2027» (13. aug. 2026) | Egen modell, ikke rader i `Patient`. Skriveendepunkt uten innlogging, signert lenke, rate-limit per token, kvittering — aldri data |
| `TODO.md`, KO-seksjonen | Problemstilling, lokasjon, utfall. Ingen stempling, ingen pålogging. Egen statistikk-kilde, ingen kobling til `/pasienter/`. Vaktnøkkel som admin genererer og trekker tilbake. Rutingflagget hører til her |
| `docs/RUNBOOK_VAKT.md` §3c | Lagene **poller ikke** — de registrerer uten å lese. Kapasiteten regnes på lesere, og park skal ikke endre det |
| `docs/FORSLAG_KO.md` §1, §3.2, §6, §8 | «Enheter produserer tid, lag produserer utfall.» Flagget på `Ressursgruppe`. Intet nummer i `H`/`O`-familien. Tallene heter «registreringer», ikke «pasienter» |

---

## 1. Hva park er, og hva det ikke er

Et lag går rundt på arrangementsområdet. Det plastrer en blemme, gir vann til en som er
varm, følger en beruset til samleplassen, eller tilkaller bil. **Ingenting av dette blir
registrert i dag**, med mindre personen havner i `/pasienter/` — og da er det sykestua som
registrerer, ikke laget. Resultatet er at statistikken ser toppen av isfjellet: de 250 som
kom inn, ikke de 750 som ble tatt hånd om ute.

`/park/` er **en tellemaskin med tre knapper**, ikke et journalsystem:

| Park er | Park er ikke |
|---|---|
| «Lag 3 hjalp noen med en fotskade ved Parkscene, som gikk videre selv» | En pasient. Ingen navn, ingen alder, intet nummer som sies høyt |
| Skrevet på en telefon med én hånd, på tre trykk | Et skjema man fyller ut etterpå |
| Skrive-bare. Laget ser en kvittering | En liste laget kan bla i |
| Tall til statistikken og til KO | Grunnlag for oppfølging av en enkeltperson |

**Den siste raden er premisset for resten.** Så lenge ingen enkeltregistrering skal kunne
følges opp, trenger raden ingen personopplysninger — og da trenger endepunktet heller ingen
pålogging. Glipper premisset («vi må kunne finne igjen han med hodeskaden»), er det
`/pasienter/` det gjelder, og den har innlogging av en grunn.

---

## 2. Det som allerede finnes

Arbeidsmønsteret fra KO-notatet §2: sjekk begrepet før det designes. Kontrollert mot koden
27. sep. 2026.

| Det park trenger | Det som finnes | Hva som gjenstår |
|---|---|---|
| Hvem laget er | `vaktliste.Ressurs` i en `Ressursgruppe` («Lag») — per vaktliste | Ingenting. Nøkkelen peker på ressursen |
| Et flagg for «hvem bruker `/park/`» | `Ressursgruppe` har `flere_enheter` og `er_aktiv` | Flagget, §5 |
| Stedene | `oppdrag.Lokasjon`, admin-styrt, `er_aktiv` + `rekkefolge` | Ingenting — men se §4.2 om retningen |
| Hvor laget står nå | `ko.Tavleplassering`, én åpen rad per ressurs | Ikke brukbar uten å snu en avhengighet, §4.2 |
| Signert, tidsbegrenset token | `accounts/signert_lenke.py` — `TimestampSigner` med egen salt per bruk | Mønsteret, ikke modulen: den er knyttet til `CustomUser` |
| Rate-limit | `core.ratelimit.rate_limit(group=..., key=...)` | En nøkkelfunksjon per token, ikke per bruker (`key='user'` forutsetter innlogging) |
| Idempotens | `core.idempotency` — `bygg_nokkel`, `reserver`, `fullfor` | `bygg_nokkel` tar en bruker-ID; her er det nøkkel-ID-en |
| Offline-kø | Vaktlistas stemplinger og bilens kø: `koLes`/`koSkriv`/`synkKo`, `vurder_klienttid` | Samme mønster, tredje gang |
| Klienttid som klippes | `vurder_klienttid` — **to** kopier allerede, i `vaktliste/services.py` og `oppdrag/services.py` (den siste tar også oppdraget) | En tredje kopi, eller løftes til `core` — §7 |
| Statistikk-kilde | `core/stats.py`, fire handlere i dag | Handler nummer fem |
| Lagringsfrist | `core/opprydding.py` | En handler hvis park skal ha frist |
| Backup | `core.backup`-registeret | Handler + plass i `GJENOPPRETTINGSREKKEFOLGE` |
| Problemstillinger | **To** lister: `patients.choices.PROBLEMSTILLING` (21, i kode) og `oppdrag.Problemstilling` (tabell, admin-styrt) | Et valg, §9 spørsmål 2 |
| Utfall | `patients.choices.UTSKREVET_TIL` har «Hjem/park» — *sykestuas* utfall | Parks egen liste. Finnes ikke |

Det nye er altså lite: **én registreringstabell, én nøkkeltabell, ett flagg, og to
verdimengder.** Resten er mønstre som finnes tre ganger fra før.

---

## 3. Datamodellen

### 3.1 `park.Registrering`

| Felt | Merknad |
|---|---|
| `vakt` | Scopet, som alt annet |
| `nokkel` | FK til `Parknokkel`, `SET_NULL`. Hvilken lenke som ble brukt |
| `ressurs` | FK til `vaktliste.Ressurs`, `SET_NULL`, **strippes i backupen** |
| `ressurs_navn` | Frosset, som `HendelseLag.ressurs_navn` — overlever at vaktlista ryddes |
| `problemstilling` | Tekst, validert mot verdimengden (§9.2) |
| `lokasjon` / `lokasjon_navn` | FK til `oppdrag.Lokasjon` + frosset navn, som `Tavleplassering` |
| `utfall` | Tekst, validert mot verdimengden (§9.3) |
| `tidspunkt` | Når det skjedde — klientens tid, klippet (§7) |
| `registrert_at` | Når raden kom inn. Aldri korrigerbar. Samme skille som `Logglinje` |
| `idempotency_key` | Unik per nøkkel. Offline-køen sender samme rad to ganger, og det skal bli én |

**Ingen fritekst, og det er ikke en forenkling — det er sikkerhetsmodellen.** Et felt som
tar imot hva som helst fra et endepunkt uten innlogging er et felt der «Ola Nordmann,
f. 1990, epileptisk anfall» havner en travel kveld, skrevet av noen vi ikke vet hvem er.
Med bare nedtrekk kan raden ikke inneholde et navn, og da kan backupen, statistikken og
KO vise den uten å arve pasientmodulens vern. Samme argument som `Lokasjon` i
`oppdrag/models.py`.

**Ingen kjønn og ingen alder** — med mindre §9 spørsmål 4 sier noe annet. Hver kolonne
som beskriver *personen* flytter raden nærmere en personopplysning, og ingen av dem
trengs for å svare på «hvor mye gjorde lagene».

### 3.2 `park.Parknokkel`

| Felt | Merknad |
|---|---|
| `vakt` | Nøkkelen virker bare mens **denne** vakta er aktiv. Avsluttes vakta, dør alle lenkene uten at noen må huske det |
| `ressurs` / `ressurs_navn` | Hvilket lag lenken tilhører (§4.1) |
| `hemmelighet_hash` | SHA-256 av tokenet. Selve tokenet lagres ikke |
| `opprettet_av` / `_navn`, `opprettet_at` | Hvem, og når |
| `trukket_at`, `trukket_av` | Tilbaketrekking. Raden står, så registreringene beholder sin peker |
| `sist_brukt_at` | Så nøkkeladministrasjonen kan vise «Lag 3 har ikke registrert noe på fire timer» — kanskje fordi lenken ikke virker |

**Hvorfor en tabell og ikke bare en signert streng.** TODO-punktet sier «signert lenke via
`django.core.signing`». En signatur alene er **tilstandsløs**, og da kan den ikke trekkes
tilbake enkeltvis — bare alle på én gang, ved å bytte salt. `signert_lenke.py` løser det
med passord-avtrykket, men et lag har ikke noe passord. Så det trengs en rad uansett, og
med en rad er det raden som er fasit:

| | Signert (`TimestampSigner`) | Tilfeldig token, hash i basen |
|---|---|---|
| Tilbakekalling per lag | Krever en rad likevel | Sett `trukket_at` |
| Forfalsket token | Avvist uten databaseoppslag | Ett indeksert oppslag |
| `SECRET_KEY` roteres | Alle lenker dør midt i vakta | Upåvirket |
| Lekker basen | — | Hash, ikke token: lenkene kan ikke gjenskapes |

**Anbefaling: tilfeldig token (`secrets.token_urlsafe(24)`), SHA-256 i basen.** Det er
standardmønsteret for API-nøkler. Gevinsten ved signering — å slippe et oppslag for
forfalskede tokens — er verdiløs når rate-limiten uansett står foran, og ulempen ved
rotasjon er reell. Det er et avvik fra ordlyden i TODO, og derfor spørsmål 1 i §9.

---

## 4. De to valgene som former modulen

### 4.1 Én lenke per lag, ikke én per vakt

| | Én vaktnøkkel, laget velger seg selv | **Én nøkkel per lag** |
|---|---|---|
| Hvem registrerte | Det laget sier | Det lenken sier |
| Tilbaketrekking | Alle lag mister lenken samtidig | Bare det ene laget |
| Utdeling | Én QR-kode på et ark | Én QR-kode per lag |
| Trykk per registrering | Fire (lag + tre) | Tre |
| Feilkilde | Lag 3 velger «Lag 8» i farten, og statistikken per lag er feil uten at noen ser det | En lenke delt i feil gruppechat |

**Anbefaling: per lag.** Et nedtrekk som ingen kontrollerer er en påstand, og statistikk
per lag er noe av det mest interessante park kan gi. Utdelingen er lett å gjøre billig:
**én knapp som lager nøkler til alle lag i vaktlista** og et utskriftsark med én QR per
lag. Dette er også der rutingflagget får en ekte jobb (§5).

### 4.2 Retningen: park → vaktliste og park → oppdrag, og KO leser park

Park må kjenne lagene (`vaktliste.Ressurs`) og stedene (`oppdrag.Lokasjon`). Begge som
strengreferanser i FK-er med frosset navn ved siden av — samme form som `Tavleplassering`
og `HendelseLag`. Ingen Python-import av noen av dem trengs for å *lagre*; nedtrekket med
stedene må derimot lese `Lokasjon`.

**KO står over park, ikke under.** KO er øverste lag (`FORSLAG_KO.md` §3.3), og det er KO
som vil *vise* registreringene. Det har en konsekvens som er fristende å gå rundt:

> Lokasjonen kunne vært forhåndsvalgt fra `ko.Tavleplassering` — KO vet jo hvor laget står.
> Men da importerer park `ko`, og KO importerer park for å vise tallene: en sirkel.

**Anbefaling: laget velger stedet selv i første omgang.** Forhåndsutfylling kan komme
senere gjennom et register i `core` (samme idiom som `core/kontokobling.py`), der KO melder
inn «hvor står denne ressursen nå» — da går pila riktig vei. Men det er en ny mekanisme for
å spare ett trykk, og det bør vente til generalprøven viser om trykket faktisk koster.

---

## 5. Rutingflagget på `Ressursgruppe`

`FORSLAG_KO.md` §3.2 plasserte flagget her og utsatte det, med begrunnelsen at det var «en
bryter med én stilling» så lenge `/park/` ikke fantes. Med per-lag-nøkler (§4.1) får det
én konkret virkning:

> **`registrerer_i_park`** (bool, standard `False`): ressursene i gruppa får en parknøkkel
> når nøkkeladministrasjonen lager nøkler «til alle».

Bevisst **ikke** en `choices` med `oppdrag`/`park`/`ingen`. At en ressurs stempler i
`/oppdrag/` avgjøres allerede av `Ressurs.enhet`, og KO-notatet sier selv at de to
spørsmålene bare korrelerer. Et flagg med tre stillinger ville gjort `enhet` og flagget til
to kilder for samme sannhet, og den dagen de er uenige vet ingen hvilken som gjelder.

Konsekvens å ta bevisst: en ressurs *kan* ha både enhet og parknøkkel. Det er ikke en feil —
en mannskapsbil som også plastrer folk ute er tenkelig — men nøkkeladministrasjonen bør
vise det.

---

## 6. Endepunktet uten innlogging

### 6.1 Flatene

| Sti | Hvem | Hva |
|---|---|---|
| `/park/` | Innlogget, `ModulTilgang('park')` | Oversikten: registreringer denne vakta, per lag og per sted |
| `/park/nokler/` | `skriv_leder` i park (eller global admin, §9.6) | Lag, trekk tilbake, skriv ut QR-arket |
| `/park/r/` | **Ingen innlogging** | Skjemaet. Én statisk side |
| `/park/r/api/oppsett/` | Token i header | Lagets navn, vaktnavnet og verdimengdene — ikke noe annet |
| `/park/r/api/registrer/` | Token i header | Lagrer, svarer med en kvittering |

De tre under `/park/r/` står i unntakslista i `patients/tests_modul_dekorator.py`, med
begrunnelse — slik `vaktliste/sw.js` gjør i dag. `ModuleSettings.enabled=False` skal stenge
dem også; det er nødbryteren om en lenke har lekket.

### 6.2 Tokenet i fragmentet, ikke i stien

QR-koden peker på **`/park/r/#<token>`**. Alt etter `#` sendes aldri til serveren: det
havner ikke i Railways tilgangslogg, ikke i `Referer`, og ikke i proxyens logger. Siden
leser fragmentet med JS, legger tokenet i `localStorage`, og sender det i en header
(`X-Park-Nokkel`) på de to API-kallene.

| Token i stien (`/park/r/<token>/`) | **Token i fragmentet** |
|---|---|
| Virker uten JS | Krever JS — men offline-køen krever det uansett |
| Står i tilgangsloggen hos Railway | Gjør det ikke |
| Serveren kan avvise en død lenke før siden tegnes | Siden tegnes, og sier fra etter første kall |

Et token i en logg er et token noen andre kan bruke, og tilgangsloggen er ikke noe portalen
styrer. **Anbefaling: fragmentet.**

### 6.3 Hva et gyldig token gir

**Skrive-bare betyr at svaret aldri inneholder registreringer** — heller ikke lagets egne.
Kvitteringen er «Registrert 21:14 · Skade fot · Parkscene · Gikk videre selv», bygget av det
klienten sendte, pluss en teller: «Lag 3 har registrert 12 denne vakta.» Telleren er et
tall, ikke data, og den er det som forteller laget at registreringene faktisk kommer fram.

Ugyldig, trukket og utløpt token gir **samme** svar, slik `signert_lenke.les()` gjør det av
samme grunn: forskjellen hjelper bare den som prøver seg.

### 6.4 Rate-limit og CSRF

- **Per token**: `rate_limit(group='park:registrer', key=<nøkkel-ID>, rate='30/m')`. Tretti i
  minuttet er langt over det et lag rekker, men lavt nok til at et skript med en lekket
  lenke ikke fyller statistikken før noen ser det.
- **Per IP, for ugyldige tokens**: en egen, strengere bøtte som bare telles når tokenet
  *ikke* stemmer — CLAUDE.md, «Tell riktig hendelse, ikke bare riktig endepunkt».
- **CSRF**: endepunktet er `csrf_exempt`. CSRF beskytter en innlogget sesjon mot at en annen
  side bruker den; her finnes ingen sesjon, og tokenet i headeren er noe en fremmed side
  ikke kan sette. Det må stå begrunnet ved dekoratøren, fordi det ellers ser ut som en glipp.

---

## 7. Offline

**Dekningen i et parkområde med tjue tusen telefoner er dårlig, og det er der lagene er.**
Et skjema som feiler uten nett blir ikke brukt to ganger. Offline er derfor ikke en
forbedring til senere — uten den er modulen en idé som ble prøvd.

Mønsteret finnes to ganger (bilen og vaktlista), og park er det enkleste tilfellet:

- **Kø i `localStorage`**, `idempotency_key` per rad, samme rekkefølgeregel: står noe i kø,
  går alt i kø.
- **Service worker på `/park/r/sw.js`** som cacher siden og `oppsett`-svaret. Aldri POST.
- **`tidspunkt` fra klienten**, klippet på serveren. `vurder_klienttid` finnes allerede i
  to kopier, `vaktliste/services.py` og `oppdrag/services.py` — tredje bruker er grunnen til
  å løfte kjernen til `core`, ikke til å skrive kopi nummer tre.
- **Kvitteringen skiller «lagret» fra «i kø»** synlig. «3 venter på nett» er informasjon laget
  trenger; en grønn hake som ikke er sann er verre enn ingen.

`localStorage` på en privat telefon holder bare nedtrekksverdier og tokenet. Det er ingen
helseopplysning i køen, og det er §3.1s fraværende fritekst som gjør det sant.

---

## 8. Resten av rammeverket

| Hva | Forslag |
|---|---|
| Modul | `park/module.py`, `nivaaer = ('les', 'skriv_leder')`. `skriv_handling`/`skriv_full` betyr ingenting her — registreringen skjer uten konto |
| Backup | `park/backup.py`. `ressurs`, `lokasjon`, `nokkel.opprettet_av` strippes; navnene er frosset. Plass i `GJENOPPRETTINGSREKKEFOLGE` etter `vaktliste` |
| Arkiv | **Ikke i første omgang.** Radene har ingen fritekst og kunne vært signert, men arkiveringen er fortsatt pasientmodulens knapp (TODO: «Flytt arkiveringen til `/portal-admin/`»). Park følger den flyttingen, slik KO gjør |
| Lagringsfrist | `park/opprydding.py` hvis §9.8 sier det. Nøklene ryddes uansett når vakta er avsluttet |
| Statistikk | `park/statistikk.py`. Per problemstilling, utfall, sted, lag, time. **Overskriften sier «registreringer»** (`FORSLAG_KO.md` §8) |
| Audit | Nøkkel laget og trukket logges der det skjer. Registreringer auditlogges **ikke** — de er selve dataene, ikke en endring av dem, og hver rad har allerede `registrert_at` og nøkkelen |
| Endringsnummer | `park/endringer.py`, slik at KO og `/park/` kan følge med uten å polle tabellen |
| `NOKLER_UTEN_AUDIT` | Ikke berørt — park har ingen teller i `AppSetting` |
| Personvern | Ny rad i `PERSONVERN_DOKUMENTASJON.md` A.6. Argumentet er det samme som for `Oppdrag` før fritekst: tid, sted og problemstilling, ingen identifikator |

### 8.1 KO

Tre ting KO kan få, i stigende kostnad. **Ingen av dem hører til første pulje**; de er
nevnt for at modellen skal tåle dem.

1. **Tall på lagkortet i ressursoversikten**: «Lag 3 · 12 reg.» Billig, og svarer på «er
   laget i gang».
2. **En systemlinje i loggen per registrering.** Frarådes: med hundrevis av registreringer
   drukner loggen, nøyaktig argumentet mot vaktlistas stemplinger i KO-seksjonen i `TODO.md`.
3. **Utfallet «Tilkalt bil» som varsel i KO.** Fristende, men farlig: et lag som trenger
   bil *sier det på samband*. Blir parkregistreringen en kanal for å be om ressurser, har
   portalen to kanaler for samme bestilling, og den ene har ingen som svarer.

---

## 9. Åpne spørsmål — besvares før koden

1. **Tokenet: tilfeldig med hash i basen, eller signert som TODO sier?** Anbefaling i §3.2:
   tilfeldig. Avviket fra ordlyden er bevisst, men det er ditt valg.
2. **Problemstillingene — hvilken liste?** Tre muligheter:
   - `patients.choices.PROBLEMSTILLING` (21 stk.) — sammenlignbar med sykestua, men lang på
     en telefon, og mangler det laget faktisk gjør mest av (plaster, vann, ørepropper?).
     Krever dessuten at park leser pasientmodulens kode, som det ikke er noen god grunn til.
   - `oppdrag.Problemstilling` — admin-styrt tabell, men laget for biler og hastegrader.
   - **En egen, kort, admin-styrt liste i park** (anbefalt), med `rekkefolge` og `er_aktiv`
     som `Lokasjon`. Hvilke 6–10 verdier skal stå der første gang?
3. **Utfallene — hvilke ord?** Et utkast til å skyte på: «Gikk videre selv», «Fulgt til
   samleplass», «Tilkalt bil», «Avslo hjelp», «Overlatt til andre (vakt/politi)». Det er
   operativt språk, og KO-erfaringen (`FORSLAG_KO.md` §3.1, «Pause» og «Ute av drift» som
   aldri ble sagt) er at jeg ikke skal gjette det.
4. **Skal noe om personen med — kjønn, aldersgruppe?** Anbefaling: nei (§3.1). Men hvis
   sesongrapporten trenger det, er det nå det må bestemmes, ikke etter vakta.
5. **Én kontakt per registrering, eller et antall?** «Delte ut ørepropper til 15» er én
   registrering med antall 15, eller 15 trykk. `oppdrag.Problemstilling.med_antall` er et
   mønster som finnes. Anbefaling: ett trykk er én kontakt, uten antall — med mindre du vet
   at masseutdeling er noe lagene gjør.
6. **Hvem lager og trekker tilbake nøkler?** TODO sier admin. Forslaget er `skriv_leder` i
   park, fordi det er vaktlederen som setter opp lagene i vaktlista og står nærmest når en
   lenke har havnet feil. Global admin får det uansett.
7. **Kan laget angre?** Skrive-bare betyr at laget ikke kan *se* registreringene. Men «jeg
   trykket feil» kommer til å skje. Forslag: kvitteringen har en «Angre»-knapp i to minutter,
   som sletter akkurat den raden (ID-en er bare i klientens minne). Backlog har en angrefrist
   fra før. Eller: ingen angring, og feilen er støy i et stort tall.
8. **Lagringsfrist.** Radene er ikke personopplysninger slik de er foreslått, og da er det
   ingen plikt til en frist. Skal de likevel slettes etter en tid, eller leve som
   sesongstatistikk?
9. **QR-koder.** Utskriftsarket trenger en QR-generator. Enten en Python-pakke (`segno`,
   ren Python, ingen avhengigheter; ny linje i `requirements.in`) som tegner SVG
   server-side, eller et JS-bibliotek i `static/vendor/`. Anbefaling: `segno` — SVG-en er
   ferdig når siden kommer, og utskrift virker uten JS.
10. **Hvem ser `/park/`-oversikten?** Forslag: `les` i park til KO-operatørene og
    vaktledelsen. Den viser bare tall og nedtrekksverdier, så det er ikke samme vern som
    pasientdata — men den er fortsatt en modul du deler ut bevisst.

---

## 10. Foreslåtte puljer

Frysingen er noen uker før vakta (`TODO.md`, «Veien til neste vakt»), og park skal være
prøvd på generalprøven. Rekkefølgen er valgt så hver pulje kan prøves alene.

| Pulje | Innhold | Hvorfor her |
|---|---|---|
| **1 — Modellen og skjemaet** | App, modul, `Registrering`, `Parknokkel`, verdimengdene, `/park/r/` online, rate-limit, backup, modultestene | Alt annet skriver inn i dette. Kan prøves med én nøkkel laget i Django-shell |
| **2 — Nøklene** | Rutingflagget, «lag nøkler til alle», tilbaketrekking, QR-arket | Uten dette er pulje 1 ikke brukbar av noen andre enn meg |
| **3 — Offline** | Service worker, kø, `vurder_klienttid` løftet til `core` | Egen pulje fordi den er den mest feilutsatte, og fordi mønsteret skal *løftes*, ikke kopieres |
| **4 — Tallene** | `/park/`-oversikten, statistikk-kilden, telleren på KO-kortet (§8.1 punkt 1) | Trenger data, og generalprøven gir dem |

**Anslag: 2–3 økter for pulje 1–2, én for 3, én for 4.** Det usikre er pulje 3 — ikke
koden, men å prøve den på en ekte telefon uten dekning.
