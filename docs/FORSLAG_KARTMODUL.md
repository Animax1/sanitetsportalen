# Forslag: kartmodul med værlag

> **Status: forslag, ikke besluttet. Ingen kode skrevet.** Skrevet 23. sep. 2026 etter en
> samtale med André. **Ikke noe som skal gjøres i år** — notatet finnes for at arbeidet med
> kildene og arkitekturen ikke skal måtte gjøres på nytt den dagen det tas opp.
>
> *Navnet følger skikken i `docs/`: `BESLUTNING_*` er avgjort, `FORSLAG_*` er ikke.*

---

## 1. Hva André har bestemt

| Spørsmål | Svar |
|---|---|
| Datakilder | **MET, Kartverket og NVE/Varsom.** Ingen kommersielle (Windy, OpenWeatherMap) |
| Bakgrunnskart | **Topografi og flyfoto/satellitt**, valgbart |
| Innhold | **Farevarsler** og lignende, **vindretningspiler**, **nedbørsmengde** |
| Nødfall når nettet er borte | **Ikke i første omgang** |
| Kildehenvisning | **Som vannmerke** i kartets nedre høyre hjørne |

---

## 2. Hva som finnes i dag (kontrollert 23. sep. 2026)

- **Intet kartbibliotek.** `static/vendor/` har bootstrap, bootstrap-icons, chartjs og
  tabulator.
- **Ingen værintegrasjon.** Ingen kall mot `api.met.no` eller NVE i kodebasen.
- **`oppdrag.Lokasjon` har ingen koordinater** — bare `navn` og `er_aktiv`.
- **CSP-en stenger alt eksternt** (`core/middleware.py`, `_CSP_DIRECTIVES`):
  `img-src 'self' data:` og `connect-src 'self'`. Kartfliser fra en annen vert blir
  blokkert i stillhet — siden laster, kartet er grått, bare konsollen sier fra. Samme
  felle som `media-src blob:` 14. sep. 2026.

---

## 3. Kildene

**Kostnad: 0 kr.** Alle tre er åpne data. For en helg med ti lokasjoner og
halvtimesoppdatering blir det rundt 1 000 kall mot MET — langt under grensen.

### 3.1 MET (`api.met.no`) — lisens NLOD / CC BY 4.0

| Produkt | Gir oss | Merk |
|---|---|---|
| **Locationforecast 2.0** | Punktvarsel: `wind_speed`, `wind_speed_of_gust`, `wind_from_direction`, `precipitation_amount` (neste 1/6/12 t), temperatur | Hovedkilden for pilene og nedbørsmengden |
| **Nowcast 2.0** | Nedbørsintensitet i 5-minutterssteg de neste ~90 min, radarbasert | Bare innenfor radardekningen i Norden. «Regn om 15 min ved scenen» |
| **MetAlerts 2.0** | Farevarsler (CAP) med polygon | **Maks én henting per 10 min** |
| **Radar 2.0** | Radarbilder per region | Ferdige bilder, ikke fliser — ikke første versjon, se §5 |

**Vilkårene som styrer arkitekturen:**
- Hver forespørsel **må** ha en identifiserende `User-Agent` (app/domene + kontakt).
  Mangler den, blokkerer Locationforecast 2.0 i stedet for å strupe. Falsk eller tilfeldig
  UA gir permanent utestengelse.
- Over **20 forespørsler/sekund totalt for applikasjonen** krever avtale.
- Svarene skal mellomlagres og `Expires`/`If-Modified-Since` respekteres.

### 3.2 Kartverket (`cache.kartverket.no`) — CC BY 4.0

- **Topografi:** WMTS-lagene `topo` og `topograatone` i Web Mercator. Den gamle
  `opencache.statkart.no` er stengt; alt er flyttet til `cache.kartverket.no`.
- **Flyfoto (Norge i bilder): ikke åpent.** De åpne WMTS-tjenestene er lagt ned, og
  `services.norgeibilder.no` krever GeoID-token. Utvidet bruk i egne fagsystemer er
  forbeholdt parter i **Norge digitalt** (kommuner, fylker, statlige etater). Se §6.1.

### 3.3 NVE / Varsom — NLOD

Farevarsler for **flom, jordskred og snøskred** via Varsoms åpne API. Gir oss det MET ikke
dekker, og er relevant for et sanitetskorps.

---

## 4. Arkitektur

### 4.1 Serveren henter værdata — nettleseren henter bare fliser

```
Nettleser ── /kart/api/vaer/ ──> portalen ── (cache) ──> api.met.no / NVE
Nettleser ── fliser ──────────────────────────────────> cache.kartverket.no
```

**Værdata går gjennom portalen**, fordi:
- JavaScript kan ikke sette `User-Agent`, og MET krever den.
- Ti åpne skjermer blir **ett** kall mot MET, ikke ti. Cachen følger `Expires` fra svaret.
- `connect-src 'self'` står urørt.
- Mønsteret finnes: cache med TTL og `try/except` rundt alt, som `core/stats_cache.py`.

**Kartflisene hentes direkte**, med ett smalt, navngitt tillegg i CSP:
`img-src 'self' data: https://cache.kartverket.no`. Å proxye flisene ville kostet
Railway-trafikk uten å gi noe tilbake — flisene er offentlige og nettleseren cacher dem.
Tillegget skal begrunnes i en kommentar ved direktivet, slik `media-src` er.

### 4.2 Kartbibliotek: Leaflet, vendret

**Leaflet** under `static/vendor/leaflet/`, jf. H3 — aldri CDN.

| | Leaflet | MapLibre GL |
|---|---|---|
| Størrelse | ~40 kB | ~800 kB |
| CSP | Ingen endring i `script-src` | Web workers fra `blob:` → må utvide `worker-src` |
| WMTS-rasterfliser | Rett fram | Rett fram |
| Vektorkart, 3D | Nei | Ja |

Vi trenger rasterfliser og markører. MapLibre ville kjøpt oss ting vi ikke skal bruke,
mot en utvidelse av CSP.

### 4.3 Lagene

| Lag | Kilde | Tegnes som |
|---|---|---|
| Bakgrunn: topografi | Kartverket `topo` | Flisgrunnlag (standard) |
| Bakgrunn: gråtone | Kartverket `topograatone` | Flisgrunnlag — gjør værlagene lettere å lese |
| Bakgrunn: flyfoto | Avhenger av §6.1 | Flisgrunnlag |
| Vind | Locationforecast per lokasjon | **Pil per lokasjon**, farget etter styrke, kast i etiketten |
| Nedbørsmengde | Locationforecast + Nowcast | Tall/søyle per lokasjon; Nowcast som «neste 90 min» |
| Farevarsler | MetAlerts + Varsom | Polygoner, farget etter nivå (gult/oransje/rødt) |
| Vannmerke | — | «© Kartverket · Data: MET Norway · NVE/Varsom», nedre høyre hjørne |

**Pilretningen er en klassisk felle:** MET oppgir `wind_from_direction` — *hvor vinden
kommer fra*. En pil som skal vise hvor vinden blåser, må roteres `+180°`. Regelen skal stå
som en egen funksjon med test, jf. «JS-funksjoner som avgjør noe» i `CLAUDE.md`.

**Vannmerket er en Leaflet-kontroll** (`L.control.attribution`, eller en egen) — ikke
tekst lagt oppå kartet med CSS. Da følger den kartet ved endret størrelse og fullskjerm.

### 4.4 Modulen

- Egen app `kart/`, registrert i `core/modules.py`, rute `/kart/`.
- `Module.nivaaer`: sannsynligvis bare `les` (se kartet) og `skriv_leder` (plassere
  lokasjoner og sette kartets utsnitt). Hvert view dekorert med `@modul_kreves`.
- Utsnitt og startzoom per vakt — en innstilling, meldt inn gjennom
  `core/portalinnstillinger.py`.
- **Ingen backup-handler og ingen arkiv** i første versjon: modulen lagrer ingen data av
  betydning, bare cache. Får den koordinater, se §6.2.
- Eget stilark `static/css/kart.css`, som definerer de fire variablene `base_portal` ikke
  aliaser (`statistikk.css` er mønsteret).

---

## 5. Utenfor første versjon, med vilje

- **Animert vindfelt over hele kartet.** Krever gridded data (MEPS 2,5 km som NetCDF fra
  THREDDS) og en prosesseringsjobb. For tungt for web-prosessen. Pilene per lokasjon
  svarer på det en vaktleder faktisk spør om.
- **Radarbilde som lag.** MET leverer radaren som ferdige bilder per region, ikke som
  fliser. Georeferering er mer arbeid enn det ser ut som.
- **Nødfall uten nett** (André, 23. sep. 2026).
- **Enhetenes GPS-posisjon på kartet.** Nærliggende, men et personvernspørsmål. Står
  allerede i TODO som «Locus-klone».

---

## 6. Åpne spørsmål — besvares når modulen tas opp

### 6.1 Flyfoto: hvor fra?

| Alternativ | Fordel | Ulempe |
|---|---|---|
| **Norge i bilder via en Norge digitalt-part** | Beste bilder i Norge, oppdatert | Krever at korpset får tilgang gjennom f.eks. kommunen. GeoID-token må ligge på serveren, og da må flisene proxyes |
| **Sentinel-2 cloudless (EOX)** | Åpent, hele Norge | 10 m oppløsning — ser landskapet, ikke parkeringsplassen. Lisensen varierer mellom årgangene og må sjekkes (noen er CC BY-NC-SA) |
| **Droppe flyfoto** | Ingen avhengighet | André ønsket det |

Sjekkes først: om korpset allerede har tilgang til Norge i bilder gjennom en
samarbeidspartner.

### 6.2 Hvor bor koordinatene?

`oppdrag.Lokasjon` er lokasjonene, og de trenger bredde- og lengdegrad. Men kartmodulen
får ikke importere `oppdrag` fritt (avhengighetsretningen, `core/tests_avhengighetsretning.py`).
To veier:

1. **Koordinatene på `oppdrag.Lokasjon`**, og oppdrag melder lokasjonene inn gjennom et
   register i `core` — samme idiom som `core/driftstatus.py`. Én sannhet om hvor
   lokasjonene er.
2. **Egne kartpunkter i `kart/`.** Enklere avhengighetsmessig, men da har portalen to
   lister over steder — nøyaktig det `CLAUDE.md` advarer mot i «Før du designer noe nytt».

Anbefaling: **1.** Da får oppdrag og KO koordinatene gratis den dagen de trenger dem.

### 6.3 Egen side, eller også et vindu i KO?

KO-konsollen har vinduer som kan skjules. Et kartvindu der er nærliggende, men KO-sida har
eget stilark og egen lasterekkefølge. Avgjøres når første versjon står.
