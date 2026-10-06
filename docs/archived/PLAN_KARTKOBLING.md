> **Arkivert 6. okt. 2026 (André: «den er nytteløs nå»).** Puljene A–F ble levert 30. sep.
> 2026 og koblingen går i prod. Dokumentet beskriver planen slik den var før leveransen og
> oppdateres ikke; **B12 er alt utdatert** — kartet matcher lagets sted mot både teiger og
> veipunkter siden 2. okt. 2026 (`portal/lagring.steder_for` i `kart-sanitet`). Det som
> gjelder står i koden (`core/kartkobling.py`, `ko/kartkobling.py`, `oppdrag/views._posisjon`)
> og i kartets egen `docs/PLAN.md`. Beslutningstabellen i §1 (B1–B14) er grunnen til at fila
> er arkivert og ikke slettet.

# Plan: kobling fra portalen til kart.sanitet.net

Status: **pulje A–F utført 30. september 2026** (se CHANGELOG i begge repoene); gjenstår
Railway-variablene i §9 og den ekte prøven fra en bil. Opprinnelig status: besluttet, ikke påbegynt. Skrevet 30. september 2026 etter en samtale med
André samme dag; beslutningene i §1 er hans, og de skal ikke tas opp igjen av den som
bygger. Planen utføres i en **egen sesjon**, i begge repoene (`sanitetsportalen` og
`kart.sanitet`). Arbeidslista er `TODO.md` i hvert repo, historien `CHANGELOG.md`.

Underlaget som allerede finnes, og som planen bygger på:

| Hvor | Hva det sier |
|---|---|
| `kart.sanitet/docs/PLAN.md` §1 (29.09) | «Egen posisjon: sendes ikke til serveren» og «Lokasjoner: kartet eier sine egne steder, ingen kobling til portalen». **Begge snus delvis av denne planen**, og skal føres som nye rader med dato |
| `kart.sanitet/docs/PLAN.md` §9 | «Å dele sin posisjon live med andre» og «kobling til portalens lokasjoner» er bevisst utelatt. Live-deling er *fortsatt* utelatt: dette er posisjon ved hendelser |
| `kart.sanitet/docs/PROSJEKTNOTAT.md` §5 | Hvorfor kartet er et eget prosjekt. Planen holder det slik; grensen for når det bør tas opp igjen står i §1 under |
| `docs/FORSLAG_KARTMODUL.md` §5 | «Enhetenes GPS-posisjon på kartet: nærliggende, men et personvernspørsmål». Besvart i §1 og §8 |
| `core/ressursplassering.py`, `ko/tavle.py` | KO vet allerede hvor et lag står, som et frosset lokasjonsnavn. Lagdelen er en flate over det, ikke en ny mekanisme |

---

## 0. Til sesjonen som utfører

**Les før du rører noe:** `CLAUDE.md` i rota av begge repoene, `oppdrag/CLAUDE.md`,
`ko/CLAUDE.md`, `templates/oppdrag/CLAUDE.md`, og `kart.sanitet/CLAUDE.md`. Reglene der
gjelder, også der denne planen er taus.

**En annen sesjon arbeider samtidig i `/vaktliste/`.** Derfor:

- Arbeid på en egen gren fra `staging` i portalen (foreslått navn `kartkobling`). Rør
  **ikke** `vaktliste/`, `templates/vaktliste/`, `static/js/vaktliste-*.js` eller
  `static/css/vaktliste.css`. Trenger du noe derfra, les det; skriv det ikke.
- `CHANGELOG.md` og `TODO.md` er de to filene begge sesjonene skriver i. Legg din
  CHANGELOG-seksjon som en **egen** `## 2026-MM-DD`-blokk og regn med en konflikt når du
  fletter `staging` inn før push. Løs den ved å beholde begge blokkene.
- Flett `staging` inn i grenen **før** hver push til `staging`, kjør suiten mot lokal
  PostgreSQL, og vent på grønn CI. **Aldri til `main`** uten at André har sagt fra.
- I `kart.sanitet` går commit og push rett til `main` (regelen der), og hver push
  deployer. Kjør `ruff` og `pytest` i et miljø bygd fra `requirements-dev.txt` først.
- **Oppgi commit-SHA for hver gren du pusher**, i begge repoene.

**Rekkefølgen er A → B → C → D → E → F.** Kartet bygges først, fordi det kan prøves med
`curl` før portalen sender noe, og fordi en portal som sender til et endepunkt som ikke
finnes bare fyller loggen med feil.

**Ferdig betyr:** alle seks puljene pushet med grønn CI, Railway-variablene i §9 satt av
André, og én ekte stempling fra en bil på staging som viser en markør i kartet.

---

## 1. Besluttet (André, 30. sep. 2026)

| # | Spørsmål | Beslutning |
|---|---|---|
| B1 | To apper eller én | **To apper, som i dag.** Grensen for å ta det opp igjen: den dagen kartet trenger å *lese* fra portalen (oppdrag, koordinater på lokasjoner, hendelser). Skrives inn i kartets `PLAN.md` §1 |
| B2 | Retning | **Bare portal → kart.** Kartet svarer 204 og returnerer aldri data. Ingen kall fra kartet til portalen, noen gang |
| B3 | Hva som sendes for biler | **Enhetsnavn, posisjon, tidspunkt.** Ikke status, ikke oppdragsnummer, ikke nøyaktighet. Tidspunktet er meldingens eget og trengs for «nyeste vinner» |
| B4 | Når biler sender | **Ved stempling**, som del av samme forespørsel bilen alt sender. Ingen løpende sending, ingen puls. Sist kjente posisjon, ikke live |
| B5 | Hva som sendes for lag | **Lagnavn og stedsnavn.** Ved plassering på tavla, og når laget går på en hendelse (da hendelsens lokasjonsnavn). Tomt sted når laget tas av tavla eller settes i pause |
| B6 | Bilen sender via | **Portalen.** Bilen kjenner ikke kartet. Nøkkelen finnes bare på de to serverne |
| B7 | Stemplingen og GPS | **Stemplingen venter aldri på GPS.** Finnes ingen fersk posisjon, sendes stemplingen uten. En ugyldig posisjon avvises ikke, den droppes |
| B8 | Autentisering | **HMAC-SHA256** over tidsstempel og kropp med delt nøkkel i Railway-variabler. Ikke kryptering: TLS bærer konfidensialiteten, HMAC bærer ekthet og integritet |
| B9 | Lagring i portalen | **Ingen.** Portalen videresender og glemmer. Ingen ny tabell, ingen auditrad |
| B10 | Lagring i kartet | **Én rad per enhet og én per lag, som overskrives.** Ingen historikk. Rader slettes etter 24 timer uten oppdatering |
| B11 | Hvem ser det i kartet | **Grupper med et flagg** («viser enheter og lag fra portalen»), satt av kartets admin på gruppa. `synlige_for` forblir det ene stedet |
| B12 | Teigmatching | **Eksakt navn** (trimmet, uten hensyn til store og små bokstaver) mot aktive teiger i gruppa. Treffer navnet ingen teig, vises laget under «Ukjent sted» i lista, ikke stille borte |
| B13 | Behandlingsansvarlig | Korpset, for begge appene; André er systemansvarlig. Kartets «privat prosjekt» i `PLAN.md` §1 rettes. Grunnlaget er berettiget interesse; avveiningen skrives i portalens personverndokumentasjon (§8) |
| B14 | Miljøer | **Egne nøkler og egen kartadresse per Railway-miljø.** Staging-portalen skal aldri kunne tegne i prod-kartet |

---

## 2. Meldingene

To endepunkter i kartet, begge `POST`, JSON-kropp, svar `204` uten kropp:

```
POST /api/portal/enhet
{"navn": "Haugesund 56", "lat": 59.4136, "lon": 5.2683, "tidspunkt": "2026-09-30T19:04:11+02:00"}

POST /api/portal/lag
{"navn": "Lag 3", "sted": "Parkscene", "tidspunkt": "2026-09-30T19:04:11+02:00"}
{"navn": "Lag 3", "sted": "", "tidspunkt": "..."}        ← tomt sted = ta laget av kartet
```

Headere:

```
Content-Type: application/json
X-Portal-Tid: 1790000000                       ← unix-sekunder på avsender
X-Portal-Signatur: sha256=<hex>                ← HMAC-SHA256(nøkkel, "<X-Portal-Tid>." + rå kropp)
```

Regler for mottak, i denne rekkefølgen, og **alle avvisninger er `401` uten forklaring i
kroppen** (angriperen skal ikke få vite hvilken sjekk som stoppet):

1. Kroppen er over 4 KB → avvis.
2. `X-Portal-Tid` mangler, er ikke et heltall, eller avviker mer enn **300 sekunder** fra
   serverens klokke → avvis.
3. Signaturen stemmer ikke mot nøkkelen, og heller ikke mot forrige nøkkel
   (`PORTAL_HMAC_NOKKEL_FORRIGE`, for rotasjon) → avvis. Sammenlign med
   `hmac.compare_digest`.
4. Kroppen validerer ikke (navn 1–120 tegn, lat i [-90, 90], lon i [-180, 180],
   `tidspunkt` ISO 8601 med sone, sted 0–255 tegn) → `400` med feltnavn. Her er avsenderen
   alt autentisert.
5. Finnes en rad for navnet med **nyere eller lik** `tidspunkt` → ignorer, svar `204`.
   Offline-køen i bilen kan levere en gammel stempling etter en ny; dette er hele grunnen
   til at tidspunktet er med.

**Replay innenfor vinduet er ufarlig med vilje**: samme melding to ganger gir samme rad.
Derfor trengs ingen nonce-tabell. En angriper med en oppsnappet melding kan bare gjenta
det portalen alt sa, i fem minutter.

**Koordinater går aldri i URL-en**, i noen av appene. Railway logger forespørselslinja.
Loggene skal heller ikke inneholde kroppen; logg navnet og utfallet, ikke posisjonen.

---

## 3. Pulje A — kartet tar imot (`kart.sanitet`)

Ny app `portal/` (INSTALLED_APPS), fordi dette verken er kartobjekter eller konto:

- **Modeller:** `Enhetsposisjon(navn unique, lat, lon, tidspunkt, mottatt)` og
  `Lagplassering(navn unique, sted, tidspunkt, mottatt)`. `mottatt` er `auto_now`;
  oppryddingen bruker den. Ingen `Endring`-rader, ingen historikk.
- **`konto.Gruppe.viser_portalen`** (BooleanField, default False) med migrasjon, og feltet
  inn i `GruppeSkjema` i `konto/forms.py` med etikett «Viser enheter og lag fra portalen».
  Det er hele tilgangsmodellen (B11).
- **Endepunktene** i `portal/api.py`, rutet under `/api/portal/` fra `config/urls.py`.
  `@csrf_exempt` (avsenderen er en server, ikke en nettleser), `@require_POST`, og
  signatursjekken som første linje etter størrelsestaket. Stien må åpnes i
  `konto/middleware.py` (`APNE_PREFIKSER`) med en kommentar om at HMAC er porten, og
  unntaket må inn i `konto/tests/test_tilgang.py` med samme begrunnelse.
- **`GET /api/portal/markorer`** for innloggede brukere: `{"enheter": [...], "lag": [...]}`
  hvis brukeren er med i minst én gruppe med `viser_portalen`, ellers tomme lister. Hver
  lagrad får `teig_id` når stedet matcher en aktiv teig som er synlig for brukeren
  (B12), ellers `null`. Matchingen gjøres på serveren, slik at regelen har én
  implementasjon og kan prøves i pytest.
- **Nøkler** fra miljøet i `config/settings.py`: `PORTAL_HMAC_NOKKEL` og
  `PORTAL_HMAC_NOKKEL_FORRIGE` (tom som standard). Er hovednøkkelen tom, svarer
  endepunktene `401` på alt. `README.md` får de to variablene.
- **Opprydding:** rader med `mottatt` eldre enn 24 timer slettes. Bruk samme mekanisme
  radarbildene ryddes med (se `kart/radar.py`); ikke en ny cron.
- **Service workeren** (`kart/templates/kart/sw.js`) skal **ikke** mellomlagre
  `/api/portal/`. Posisjoner er flyktige og skal ikke ligge i IndexedDB.

Tester (`portal/tests/`): riktig signatur → 204 og rad; feil nøkkel, gammel `X-Portal-Tid`,
endret kropp, manglende header → 401 uten kropp; forrige nøkkel godtas; kropp over 4 KB →
401; eldre `tidspunkt` overskriver ikke nyere; ugyldig lat → 400; tom hovednøkkel → 401;
`GET` krever innlogging og MFA; bruker uten flagg får tomme lister; teigmatching med
trimming og store/små bokstaver; ukjent sted gir `teig_id: null`.

---

## 4. Pulje B — kartet viser (`kart.sanitet`)

- Ny ES-modul `kart/static/kart/js/portal.js`, lastet fra `kart.js` bare når `oppsett`
  sier at brukeren har tilgang (så en bruker uten flagg aldri poller).
- **Kartlag «Portalen»** i lagpanelet, på som standard. Poller `/api/portal/markorer`
  hvert 30. sekund når fanen er synlig, og ved `visibilitychange`, som `objekter.js`.
- **Enheter:** markør med navnet som etikett (tekst med glorie, som teignavnene) og
  «for 4 min siden» i tooltip. All tekst med `textContent`. Regelen for alder er en egen
  eksportert funksjon `markorTilstand(tidspunkt, naa)` → `'fersk' | 'gammel' | 'skjult'`
  (under 30 min, under 6 timer, eldre), og den prøves i `tester_js/`. Gammel tegnes grå.
- **Lag:** et lite tall på teigen («2 lag») og en liste. Lista er et panel i arket
  (`ark.js`) med én seksjon per teig som har lag, og til slutt «Ukjent sted» for lag
  hvis sted ikke traff (B12). Klikk på en teig i lista flyr kartet dit.
- Ingen endring i CSP eller `Permissions-Policy`.

---

## 5. Pulje C — klienten i portalen (`core/kartkobling.py`)

Én modul i `core`, fordi både oppdrag og KO skal sende og ingen av dem får kjenne den
andre. Modul → `core` er lovlig retning; `core/tests_avhengighetsretning.py` skal forbli
grønn uten nye unntak.

```python
send_enhet(navn: str, lat: float, lon: float, tidspunkt: datetime) -> None
send_lag(navn: str, sted: str, tidspunkt: datetime) -> None
```

- **Inert uten oppsett:** `KART_URL` og `KART_HMAC_NOKKEL` i `settings.py` fra miljøet,
  begge tomme som standard. Er én tom, returnerer funksjonene uten å gjøre noe. Samme
  idiom som `core/offsite.py`.
- **`urllib` fra standardbiblioteket**, som `core/mail_backends.py`. Ingen ny pakke i
  `requirements.in`.
- **Kaster aldri.** Timeout 3 sekunder. Enhver feil logges som én `warning` med navn og
  statuskode, aldri kroppen, og svelges.
- **Pause etter feil:** etter en feil settes en cache-nøkkel i 60 sekunder, og sendinger
  i det vinduet hoppes over. En bil som stempler mens kartet er nede, skal ikke vente tre
  sekunder per trykk. Samme tanke som `KildePause` i kartet.
- **Sendes etter commit.** Kallstedene pakker kallet i `transaction.on_commit`, så en
  rullet tilbake stempling aldri sender. Klienten selv vet ingenting om transaksjoner.
- **Siste utfall** (tid, ok/feil, statuskode) legges i cache under én nøkkel og vises som
  et kort på `/portal-admin/server-status/` gjennom `core/admin_status.py`, med «–» når
  koblingen ikke er satt opp. Ikke i `AppSetting`: det ville gitt en auditrad per
  stempling. Uten kortet er «hvorfor vises ikke bilen» umulig å svare på.
- `.env.example` og `docs/DEPLOY_GUIDE.md` får de to variablene, og tabellen
  «Miljøvariabler» i `CLAUDE.md` får to rader.

Tester (`core/tests_kartkobling.py`, mock `urllib.request.urlopen`): signaturen er
HMAC-SHA256 over `"<tid>.<kropp>"` og lar seg verifisere med kartets regel; inert uten
oppsett; en `URLError` og en `HTTPError` kaster ikke; pausen etter feil hopper over neste
kall og slipper etter 60 s; kroppen inneholder nøyaktig feltene i §2 og ingen andre.

**Mutasjoner som skal være røde:** signaturen regnet over kroppen alene; pausen fjernet;
`try/except` fjernet; ett felt lagt til i kroppen.

---

## 6. Pulje D — bilens posisjon ved stempling (`oppdrag/`)

**Ingen ny rute i portalen.** Posisjonen rir på stemplingen bilen alt sender, og
`tallfasit` skal gi samme tall som før.

Serversiden, `oppdrag/views.py`:

- `STEMPLING_TILLATTE_NOKLER` får `posisjon`: et objekt `{"lat", "lon", "tid"}`.
- Ny hjelper `_posisjon(data) -> tuple | None` validerer (tall i gyldig område, `tid`
  som ISO 8601). **Ugyldig eller manglende posisjon gir `None`, aldri 400** (B7): køen i
  bilen stryker raden på 4xx, og en stempling som forsvinner på grunn av GPS-søppel er
  verre enn en manglende markør. Én `warning` i loggen.
- Etter at meldingen er skrevet (alle fire grenene: rykker ut, avbryt, behandlet, øvrige),
  og **ikke** ved avspilling (`idem_status == 'ferdig'`): `transaction.on_commit(lambda:
  kartkobling.send_enhet(request.user.enhet.navn, lat, lon, tid))`. Navnet er
  `Enhet.navn` fra databasen, aldri noe fra kroppen.
- Docstringen til `stempling_view` og `oppdrag/CLAUDE.md` skal si eksplisitt at
  `posisjon` **ikke er et domenefelt**: det lagres aldri, det videresendes. Regelen om at
  `skriv_handling` ikke leser kroppen står i rota, og dette er et navngitt unntak ved
  siden av `sted_tekst`.

Bilskjermen, `static/js/oppdrag-enhet.js` og malen under `templates/oppdrag/`:

- Malen får `kart_kobling_aktiv` (True når `KART_URL` og nøkkelen er satt) gjennom
  `js_json()`. Er den False, spørres nettleseren **aldri** om posisjon.
- Når aktiv: `navigator.geolocation.watchPosition` startes ved lasting, siste fix holdes
  i minnet med tidspunkt. Ingen lagring i `localStorage`.
- `posisjonForStempling(siste, naa)` er en **egen funksjon** som returnerer fixen hvis den
  er under 120 sekunder gammel, ellers `null`. Den avgjør noe, og skal kjøres i node.
- Ved trykk legges resultatet i **køraden** (`rad.posisjon`), så en stempling som sendes
  senere bærer posisjonen fra trykket, ikke fra sendingen. `synk()` sender feltet i
  kroppen når det finnes.
- Én linje i bunnen av skjermen: «Posisjon sendes til kartet ved stempling», og en
  bryter «Del posisjon» (på som standard, lagret i `localStorage` per skjerm). Av → ingen
  posisjon i køraden, og linjen sier «Posisjon deles ikke».
- Nettleseren nekter posisjon → linjen sier det, ingenting annet endres.

Tester: `oppdrag/tests_posisjon.py` (stempling med gyldig posisjon kaller klienten med
navnet fra databasen; ugyldig posisjon → stemplingen går, klienten kalles ikke; uten
posisjon → går; avspilling kaller ikke klienten; 409 og 400 fra statusmaskinen kaller ikke
klienten; sentralens føring sender aldri). I node: `posisjonForStempling` for fersk,
gammel og manglende fix, og at køraden bærer posisjonen gjennom `synk()` med bryteren på
og av. Bruk `patients/js_test_utils.py`, ikke grep etter kodelinjer.

**Mutasjoner som skal være røde:** aldersgrensen fjernet; `on_commit` byttet mot direkte
kall (test med en rullet tilbake transaksjon); navnet lest fra kroppen; sending ved
avspilling.

---

## 7. Pulje E — lagene fra KO (`ko/`)

**Send tilstand, ikke hendelser.** Ny modul `ko/kartkobling.py` med én inngang:

```python
meld_lag(ressurs) -> None
```

Den regner ut hvor laget står **nå**: åpen `Tavleplassering` med lokasjon → dens
`lokasjon_navn`; laget står på en åpen hendelse (`HendelseLag` på en hendelse som ikke er
lukket) → hendelsens `lokasjon_navn`; pause, tatt av tavla eller ingenting → `""`. Så
kaller den `core.kartkobling.send_lag(ressurs.navn, sted, now())` i `on_commit`.

Fordi den sender tilstand, kan den kalles fra **alle** stedene som endrer den, uten at
hvert sted må vite hva som skal sendes:

| Kallsted | Hvorfor |
|---|---|
| `ko/tavle.py`: `plasser`, `avslutt`, `rett`, `fjern` | Plassering, pause, og rettinger som kan gjelde den åpne raden |
| `ko/tavle.py`: `avslutt_for_hendelse` | Laget gikk på en hendelse; den nye tilstanden er hendelsens sted |
| `ko/services.py`: `sett_lag` | Lag lagt til eller fjernet fra en hendelse; også lukking av hendelsen hvis lagene da står uten sted |

**Bare lag, ikke biler.** En ressurs med `vaktliste.Ressurs.enhet` satt er en bil og
sendes av oppdragsmodulen (pulje D); sendes den også herfra, står den to ganger i kartet
med to ulike former. `meld_lag` returnerer uten å sende når `ressurs.enhet_id` er satt.

**Modulen er slått av → ingen sending.** Sjekk `ModuleSettings` som
`core/ressursplassering.py` gjør.

Tester (`ko/tests_kartkobling.py`, mock klienten): plassering sender navn og sted; pause
sender tomt; av tavla sender tomt; på hendelse sender hendelsens lokasjonsnavn; fjernet fra
hendelsen sender tomt; en bil på tavla sender ingenting; retting av en lukket rad sender
den åpne tilstanden, ikke den rettede; KO slått av sender ingenting.

**Mutasjoner som skal være røde:** bilfilteret fjernet; hendelsesgrenen fjernet;
kallstedet i `avslutt_for_hendelse` fjernet (muter kallstedet, ikke bare funksjonen).

---

## 8. Pulje F — dokumentasjon og personvern

Portalen:

- `docs/PERSONVERN_DOKUMENTASJON.md`: ny behandling «Enhetenes posisjon ved stempling»
  med formål (koordinering og mannskapets sikkerhet), grunnlag (berettiget interesse,
  art. 6 nr. 1 f) og avveiningen: hendelsesstyrt, siste posisjon, ingen historikk,
  synlig for mannskapet, mottaker er korpsets eget kart. Lagene nevnes som lagnavn og
  stedsnavn uten koordinater. Sett inn setningen: **historikk over posisjoner er en ny
  behandling og krever ny vurdering.**
- `CLAUDE.md` (rota): et kort avsnitt under «Avhengighetsretningen» om
  `core/kartkobling.py`, siden det gjelder to moduler. Kort: `core/tests_claude_md.py`
  vokter at modulstoff ikke vokser i rota.
- `oppdrag/CLAUDE.md`, `templates/oppdrag/CLAUDE.md`, `ko/CLAUDE.md`: hver sin del.
- `CHANGELOG.md` og `TODO.md` i samme commit som koden, som alltid.

Kartet:

- `docs/PLAN.md` §1: nye rader datert 30.09 for B1, B2, B10, B11, B13 og at posisjon fra
  portalen er ved hendelser, ikke live. Rett «Prosjektet: privat og ikke-kommersielt» til
  korpsets system med André som systemansvarlig.
- `docs/PLAN.md` §3.2: de tre nye endepunktene.
- `README.md`: variablene. `CLAUDE.md`: én regel, «`/api/portal/` er åpent for innlogging
  fordi HMAC er porten; ingen annen sti åpnes slik».

---

## 9. Railway (André, når pulje A og C er pushet)

Generér én nøkkel per miljø (32 tilfeldige byte som hex) og legg den i **begge** appene i
**samme** miljø:

| App | Variabel | Verdi |
|---|---|---|
| kart, prod | `PORTAL_HMAC_NOKKEL` | nøkkel P |
| portal, prod | `KART_HMAC_NOKKEL` | nøkkel P |
| portal, prod | `KART_URL` | `https://kart.sanitet.net` |
| kart, staging | `PORTAL_HMAC_NOKKEL` | nøkkel S |
| portal, staging | `KART_HMAC_NOKKEL` | nøkkel S |
| portal, staging | `KART_URL` | staging-kartets adresse |

Nøklene skal også i korpsets passordbehandler. Rotasjon: sett den gamle i
`PORTAL_HMAC_NOKKEL_FORRIGE` i kartet, ny i begge, og tøm `_FORRIGE` etter en dag.
Staging-kartet finnes fra 30. september 2026: `testkart.sanitet.net`, eget Railway-miljø med
egen nøkkel S. Staging-portalen peker dit, og prøven i §0 tas der; prod får nøkkel P først når
koblingen går til `main`. Cloudflare står foran kartet og avviser `urllib`s standard-User-Agent
med 403 («error code: 1010»); klienten sender derfor sin egen (`core/kartkobling.py`).

---

## 10. Ikke gjør

- Ikke send status, oppdragsnummer, hendelsesnummer eller fritekst. Ikke «bare ett felt
  til».
- Ikke lagre posisjoner i portalen, og ikke lag en historikk i kartet.
- Ikke la bilskjermen kjenne kartets adresse eller nøkkel.
- Ikke legg nøkkelen som hash: HMAC trenger nøkkelen i klartekst, derfor miljøvariabel.
- Ikke åpne CSP i noen av appene.
- Ikke lag en ny rute i portalen for posisjon; den rir på stemplingen.
- Ikke rør `vaktliste/` (§0).
- Ikke push til `main` i portalen.

## 11. Små valg som er tatt her, så de ikke må tas igjen

| Valg | Verdi | Kan endres senere uten å rive noe |
|---|---|---|
| Fersk fix ved stempling | 120 s | ja, én konstant |
| Grå markør / skjult markør | 30 min / 6 t | ja, i `markorTilstand` |
| Sletting i kartet | 24 t etter `mottatt` | ja |
| Tidsvindu for signatur | 300 s | ja, én konstant i kartet |
| Poll i kartet | 30 s, bare synlig fane | ja |
| Pause etter sendefeil | 60 s | ja |
| Bryteren «Del posisjon» | på som standard | ja |
