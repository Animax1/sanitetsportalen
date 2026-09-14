# Forslag: rapportmodul

> **Status: forslag, ikke besluttet. Ingen kode skrevet.** Skrevet 14. sep. 2026 og
> revidert samme dag etter at André utfordret den første versjonen — med rette; se §3.1.
>
> *Fila heter `FORSLAG_` og ikke `rapportmodul.md` for å følge navneskikken i `docs/`:
> `BESLUTNING_*` er avgjort, `FORSLAG_*` er ikke. Se `FORSLAG_DATTEROPPDRAG.md`.*

---

## 1. Hva som er avklart

André har besvart de fleste av spørsmålene som sto åpne i første utkast:

| Spørsmål | Svar |
|---|---|
| Fakturagrunnlag: plan eller faktisk? | **Plan.** `mott_at`/`av_vakt_at` er der av brann- og sikkerhetshensyn, ikke for økonomi |
| Sats per korps, rolle eller gruppe? | **Én sats for alle**, uavhengig av rolle, korps og ressursgruppe |
| Skal rapporter fryses? | **Ja**, med admin og leder som råderett |
| Hva når noen skifter korps etterpå? | **Frysingen løser det** — historikken blir stående slik den var |
| Timer per dag eller totalt? | **Begge deler** |
| Tilgang til `/rapport/` | Global admin, **og** de som har fått modultilgang `les` eller `skriv` |
| Tolkningen | Skal utløses av en **eksplisitt knapp**, aldri automatisk |

Den siste er verdt å sitere, fordi den er et designkrav og ikke bare en preferanse:

> «Jeg vil ikke bruke CPU-tid på dette fordi noen gikk inn på rapport av nysgjerrighet.»

Det betyr at tolkningen aldri skal ligge i sidelastingen. Rapporten tegnes med tall; prosa
kommer først når noen trykker **«Generer rapport»**.

---

## 2. Del 1: timeregnskap og betaling

### 2.1 Det meste finnes allerede

Se `vaktliste/services.py`:

| Finnes i dag | Hva den gjør |
|---|---|
| `belastning_per_person()` | Timer, skift, lengste skift, korteste hvile — per person |
| `_timer(fra, til)` | Timeberegningen |
| `Vaktpost.fra_tid` / `til_tid` | Planen, som nå er fakturagrunnlaget |
| `Mannskap.korps` | Aksen «per korps» |
| `Vaktpost.rolle` | Aksen «per rolle» |
| **`Vaktpost.probono`** | **Skiftet går, men telles ikke i timene** |

Kommentaren ved `probono` i `services.py` sier:

> «Probono telles ikke i timene, men i alt annet. **Summen er det organisasjonen betaler
> for**; lengste skift og korteste hvile er hva kroppen tåler.»

Betalingstanken lå altså i modellen før noen planla en rapportmodul. Det som mangler er et
kronebeløp, en aggregering og en frysing.

### 2.2 Timer per dag — midnatt må splittes

Rapporten skal vise **både per dag og totalt**. Da blir midnattsregelen bindende.

**I dag finnes ingen dagdimensjon.** `_timer()` er ren varighet:

```
fredag 20:00 → lørdag 04:00  =  8,0 timer
```

…uten at koden har noe begrep om hvilken dag de åtte timene tilhører. Spørsmålet var
ubesvart fordi ingenting hadde stilt det.

**Regelen (André, 14. sep. 2026):** «Fredag 23:59 er fortsatt fredag. Lørdag 00:00 er
lørdag.» Det er kalenderdøgn etter tidspunkt, og for et skift som krysser betyr det at
timene **splittes ved midnatt**: 4 timer på fredag, 4 på lørdag.

**Portalen har allerede presedensen.** Bemanningskurven bøtter per time og markerer
midnattsbøtta med `vl-dogn` (`_d(p.tid).getHours() === 0`). Kurven splitter altså
allerede; timeregnskapet må gjøre det samme, ellers viser to flater i samme portal ulike
tall for samme vakt.

Totalen er uansett den samme — splittingen påvirker bare dagsfordelingen.

### 2.3 Overlapp blåser opp summen

Dette er den viktigste enkeltfeilen å kjenne før noen fakturerer.

Målt 14. sep. 2026 med portalens egen `_timer()`:

```
skift A  12:00–20:00  =  8,0 t
skift B  16:00–22:00  =  6,0 t
SUM som portalen regner:     14,0 t
FAKTISK til stede 12:00–22:00: 10,0 t
→ overfakturering:            4,0 t
```

**Og overlappet vises ikke som et overlapp.** `korteste_hvile` blir `0.0`, og raden flagges
som «kort hvile». `_hviletider()` sin docstring lover at «overlappet i seg selv fanges av
`overlapp`-tellingen» — **den tellingen finnes ikke**.

Dagens oppførsel er bevisst, og dokumentert i
`test_overlapp_paa_tvers_av_ressurser_stoppes_ikke`: «noen ganger står man på to lister.»
Skranken er `UniqueConstraint(ressurs, mannskap, fra_tid)`, altså samme person på samme
ressurs til samme tid — to ulike ressurser er fritt fram.

**Hvor sperren hører hjemme:** ikke i databasen. En intervallskranke krever
`ExclusionConstraint`, som **ikke finnes i SQLite** — da ville suiten vært grønn lokalt
mens prod oppførte seg annerledes, nøyaktig fella som tok ned deployen 30. aug. 2026.

Riktig sted er **ved frysing**: en liste som skal bli fakturagrunnlag kan nekte å fryses
med uavklart overlapp — *«Kari har 4 timer overlapp — rett eller bekreft.»* Da stoppes
feilen der den koster penger, uten å stå i veien for planleggingen der overlappet bare er
informasjon.

Punktene ligger i `TODO.md` under «Vaktlista: overlappende skift», og er uavhengige av om
denne modulen bygges.

### 2.4 Frysing er kjernen, ikke et tillegg

I dag er vaktlistedata **operative**: de kan rettes fritt, og det skal de kunne. Som
**fakturagrunnlag** må de slutte å bevege seg.

Uten et frysepunkt: noen retter et skift i mars fordi tiden sto feil, og fjorårets faktura
stemmer ikke lenger med det portalen viser. Ingen har gjort noe galt, og likevel er
regnskapet ikke etterprøvbart.

André bekreftet at dette er ønsket, og at **admin og leder har råderett** over frysinga.
Han trakk også konsekvensen selv: skifter noen korps i etterkant, blir historikken stående.
Det løser den ene modellsvakheten jeg pekte på i første utkast — at korpset ligger på
personen (`Mannskap.korps`) og ikke på skiftet.

**Portalen har mønsteret to ganger:** `patients/arkiv.py` og `oppdrag/arkiv.py`, med
`core.arkiv` som eier kanonisering, SHA-256-signatur og kollaps. En frosset rapport bør:

- lagre **tallene**, ikke en peker til rader som kan endre seg
- lagre **satsen som ble brukt**, ikke en peker til en sats som kan endres
- **signeres**, slik at det er etterprøvbart at den ikke er rørt i etterkant
- lagre **hvem som frøs den, og når**

`AbstractArkiv` bærer allerede `tittel`, `vakt`/`vakt_navn`, `antall_rader`,
`importert_av` med frosset navn, `sha256`, `kollapset_at` og aggregatfeltene. En
`Rapportarkiv` kan arve den, slik `OppdragArkiv` gjør.

**Konsekvens for omfanget:** del 1 er ikke «en tabell med timer». Den er et lite arkiv med
en godkjenningsflyt. Mønsteret finnes, men det er ærlig å si det med én gang.

### 2.5 Satsen

Én sats for alle forenkler betydelig — ingen matrise, ingen datering per korps eller rolle.
Men satsen må fortsatt **fryses sammen med rapporten**, ellers endrer et gammelt
fakturagrunnlag seg når satsen justeres.

Naturlig plassering: én rad, som `Belastningsgrenser`. Begrunnelsen der gjelder like godt
her — «grensene er organisasjonens, ikke portalens, derfor data og ikke tall i en `if`».

Å endre satsen bør være **global admin**, og auditlogges på feltnivå. Det er en avtale, ikke
en driftsinnstilling.

### 2.6 Kanter som fortsatt må avklares

| Tilfelle | Status |
|---|---|
| Skift over midnatt | **Avklart** — splittes (§2.2) |
| Person skifter korps | **Avklart** — frysingen holder historikken (§2.4) |
| Overlappende skift | **Avklart hvor sperren hører hjemme** — ved frysing (§2.3) |
| Probono | Teller ikke i kroner. **Skal den vises som egen kolonne?** Sannsynligvis ja — det synliggjør hva korpset bidro med gratis |
| Ledig plass som aldri ble fylt | Teller ikke. `belastning_per_person()` hopper alt over dem |

### 2.7 Tilgang

| Flate | Krav |
|---|---|
| `/rapport/` | Global admin, **eller** `ModulTilgang(rapport, les)` |
| Fryse en rapport | Global admin, eller `skriv` |
| Endre satsen | Global admin |

Etter komposisjonsregelen (rollemodellen §5) bør modulen dessuten bare vise tall fra
kildemoduler brukeren har minst `les` på — samme regel som statistikkappen følger.

---

## 3. Del 2: vaktrapporten

### 3.1 Jeg tok feil i første utkast, og det er verdt å skrive ned

Første versjon av dette notatet frarådet LLM-tolkning med et eksempel: *«én rød pasient,
hjertestans, kl. 14:32 — ingen navn, men på et navngitt arrangement er det sannsynligvis
én bestemt person.»*

André ba meg se på hva statistikkmodulen faktisk sender. **Eksempelet finnes ikke i
dataene.** Jeg kjørte `_compute_full_stats_from_dicts()` og leste `_stats_fra_rader()`:

| Pasienter | Oppdrag |
|---|---|
| Antall: total, rød/gul/grønn, obs, utskrevet | Antall: total, aktive, fullførte |
| `prob_counts`: antall per problemstilling | `per_hastegrad`, `per_problemstilling`, `per_lokasjon`, `per_enhet` |
| `crosstab_*`: krysstabeller med khikvadrat | `responstid_per_hastegrad`, `-per_enhet` |
| `time_per_*`: `{n, mean, median, min, max}` | `ankomster`: antall per time i døgnet (24 bøtter) |

**Ingen radnivå. Ingen ID-er. Ingen klokkeslett per pasient.** Tid finnes kun som
aggregat over grupper. Og det jeg var mest bekymret for: `fritekst`, `notat` og `merknad`
går ingen steder — `rader_for_vakt()` tar oppdragsnummer, hastegrad, problemstilling,
enhet, lokasjon, status og tider, og stopper der. `problemstilling` er en verdi fra en
kontrollert liste, ikke fritekst.

**Det endrer jussen, ikke bare risikovurderingen.** GDPR gjelder ikke anonyme data
(fortalepunkt 26). Er payloaden virkelig anonym, er A.8 ikke i spill, og det er ingen
overføring av personopplysninger.

Jeg hoppet over det spørsmålet og gikk rett til «ny databehandler». Det var feil
rekkefølge, og det er skrevet ned her fordi neste person som leser notatet skal slippe å
gjøre samme feil.

### 3.2 Det som faktisk står igjen: små tall og skadelige kategorier

```
crosstab_prob_triage: {"Mistanke overgrep": {"Rød": 1}}
per_problemstilling:  {"Psykiatri": 1}
```

På et navngitt arrangement på en kjent dato er «én mistanke om overgrep» sannsynligvis én
bestemt person. Det er grensen mellom anonymt og pseudonymt.

**Men se på verdimengden i `patients/choices.py`:**

```
'Skade ankel/fot', 'Skade arm/håndledd', 'Brystsmerter', 'Magesmerter',
'Psykiatri', 'Mistanke overgrep', …
```

Kategoriene er ikke like. «Én ankelskade» og «én mistanke om overgrep» har samme
identifiserbarhet og **helt ulik skade** hvis noen kobler den til en person.

### 3.3 Den avklarende innsikten: filteret gjelder bare maskinen

Dette er det som gjør resten enkelt.

**I portalen trengs verken undertrykking eller ekskludering.** Den som ser rapporten har
allerede `les` på kildemodulen — hun kan åpne pasientlista og se radene enkeltvis. En
statistikkside som sier «1 psykiatri» forteller henne ingenting hun ikke kunne hentet
direkte.

**Filteret hører hjemme på payloaden som forlater portalen** — altså det som sendes til en
språkmodell, og det som eventuelt eksporteres til noen uten tilgang.

Det løser også regneproblemet: den menneskelesbare rapporten er komplett og korrekt, mens
maskinpayloaden er redusert. At de to har ulike summer spiller ingen rolle, fordi ingen
leser maskinpayloaden som en rapport.

### 3.4 Ekskludering framfor undertrykking — Andrés forslag, og min vurdering

André foreslo å **ekskludere risikoproblemstillinger** i stedet for å undertrykke små
celler. Jeg mener det er riktigere, og det er verdt å si hvorfor de to ikke løser samme
problem:

| | Undertrykking (`n < 5` → `"<5"`) | Ekskludering av kategorier |
|---|---|---|
| Retter seg mot | **Identifiserbarhet** | **Skade** |
| Forutsigbar? | Nei — avhenger av dataene | Ja — bestemt på forhånd |
| Liten vakt | Nesten alt undertrykkes; rapporten blir ubrukelig | Uendret nytte |
| Å forklare | «Vi skjuler tall under fem» | «Disse kategoriene forlater aldri portalen» |
| Svakhet | Sier likevel at *noe* skjedde i kategorien | Sier ikke at kategorien finnes i det hele tatt |

**Ekskludering er bedre tilpasset art. 9-tenkningen:** særlige kategorier får særlig vern
fordi konsekvensen av lekkasje er verre, ikke fordi de er lettere å identifisere.

Og den er bedre for små vakter, som er normaltilfellet her. En vakt med tolv pasienter
ville fått nesten alle celler undertrykt under en `n < 5`-regel — rapporten hadde vært
formelt trygg og praktisk verdiløs.

**Anbefaling: ekskludering som primærkontroll**, og undertrykking som en mulig tilleggsregel
senere hvis det viser seg å trengs.

### 3.5 Filteret må feile lukket

**Dette er det viktigste designvalget i hele del 2.**

Portalen har en etablert regel for unntakslister, formulert i `core/signals.py`:

> «Lista er en unntaksliste, ikke en inkluderingsliste. En ny nøkkel logges som standard.
> Det er riktig vei å feile: en teller for mye i loggen er støy, en innstilling for lite er
> et hull.»

**Her må det være motsatt, og av nøyaktig samme resonnement.** En personvernfilter må feile
mot *mindre* deling:

- Merkes kategorier som **skal ekskluderes**, og noen legger til «Selvmordsforsøk» uten å
  huske flagget → den sendes ut. **Feiler åpent.**
- Merkes kategorier som **er godkjent for utsending**, og noen legger til en ny → den
  ekskluderes til noen aktivt godkjenner den. **Feiler lukket.**

Kostnaden er at hver ny problemstilling må godkjennes eksplisitt. Det er riktig pris: å
godkjenne en kategori for utsending er en personvernbeslutning, og den skal tas av et
menneske som vet hva den betyr.

**Implementasjonsdetalj som må avklares:** `oppdrag.Problemstilling` er en **tabell** og
kan få et felt. `patients` sine problemstillinger ligger i `choices.py` som en **tuple**.
Enten får pasientmodulen en parallell liste i kode, eller så flyttes verdimengden til en
tabell slik oppdrag gjorde det i migrasjon `0019`–`0021`. Det siste er mer arbeid, men gir
admin samme kontroll begge steder.

### 3.6 Variant A: rapport uten LLM

**Dette er et komplett produkt alene**, og det er verdt å understreke: du trenger ikke
variant B for å ha en vaktrapport.

Hva den inneholder:

| Del | Innhold |
|---|---|
| Vakthodet | Navn, dato, varighet, antall korps og ressurser |
| Bemanning | Timer per dag og totalt, per korps, per rolle. Probono som egen kolonne |
| Økonomi | Timer × sats, per korps og totalt |
| Pasienter | Antall, triagefordeling, problemstillinger, tidsstatistikk — fra `core.stats` |
| Oppdrag | Antall, hastegrad, responstider, ankomster per time — fra `core.stats` |
| Avvik | Overlapp, uferdige stemplinger, ledige plasser som aldri ble fylt |
| Signatur | Hvem frøs den, når, SHA-256 |

**Ingen ny databehandler. Ingen endring i personvernprotokollen. Ingen filtrering
nødvendig**, siden rapporten vises i portalen til folk som allerede har tilgang.

Et strukturert sammendrag kan genereres uten modell: *«23 pasienter, hvorav 3 røde.
Median ventetid 12 minutter. Lengste responstid 19 minutter på Akutt.»* Setninger som
dette er rene maler over tall, og de er alltid sanne.

Min vurdering: **dette dekker det meste av behovet.** Bygg det først, og se om savnet
etter prosa faktisk melder seg.

### 3.7 Variant B: rapport med LLM-tolkning

Alt i variant A, pluss et tolkende avsnitt utløst av **«Generer rapport»**.

#### Hva som må være på plass

| Krav | Hvorfor |
|---|---|
| **Eksplisitt knapp** | Andrés krav. Ingen CPU på nysgjerrighet, og ingen utsending noen ikke ba om |
| **Kategorifilter som feiler lukket** (§3.5) | Primærkontrollen |
| **Aldri fritekst, navn eller kontoer** | `fritekst` er alt unntatt verdilogging og arkivering; å sende den ville uthult de beslutningene |
| **Forhåndsvisning av nøyaktig hva som sendes** | Den som trykker skal kunne se payloaden først |
| **EU-hostet modell med DPA og zero retention** | Se §3.8 |
| **Resultatet merket som maskingenerert** | §3.9 |
| **Hvert kall auditlogget** | Hvem, når, hvilken rapport, hvilken payload-hash. Uten det kan dere ikke svare på «hva ble sendt ut av huset» |
| **Tolkningen lagres med rapporten** | En frosset rapport skal ikke kunne gi et annet svar i morgen |

#### Payloaden

Kun aggregater fra `core.stats`, minus ekskluderte kategorier. Konkret utelates:
individuelle rader, tidsstempler per hendelse, enhetsnavn koblet til personer, og alt
fritekst.

Payloaden bør **hashes og lagres sammen med tolkningen**, slik at man i ettertid kan vise
nøyaktig hva modellen hadde å gå på.

### 3.8 Leverandør

**Anbefaling: Scaleway Generative APIs.**

Det avgjørende argumentet er avtalemessig, ikke teknisk: **Scaleway SAS står allerede i
`PERSONVERN_DOKUMENTASJON.md` A.2** som databehandler for offsite-backup, med signert DPA.
Å ta i bruk en ny tjeneste hos en leverandør dere alt har avtale med, er vesentlig mindre
arbeid enn å ta inn en ny leverandør — A.2 utvides med en rad, i stedet for et nytt forhold
fra bunnen.

| | Scaleway Generative APIs |
|---|---|
| Datalagring | Zero retention som **standard** |
| Hvor | Franske datasentre, Paris-regionen |
| Trening | Ikke brukt til trening av modellene |
| Eierskap | Iliad Group, fransk. **Ingen amerikansk enhet → ingen CLOUD Act-eksponering** |
| Modeller | Åpne modeller: Llama, Mistral, Mixtral m.fl. |

CLOUD Act-eksponeringen er den svakheten som ikke lar seg avtale bort — et amerikansk
morselskap kan pålegges å utlevere data uansett hvor serverne står. Det var samme
resonnement som lå bak valget av Scaleway til backupene.

**Nærmeste alternativ: Mistral La Plateforme.** Fransk, EU-infrastruktur, DPA tilgjengelig.
Men **zero data retention ligger bak Scale-planen**; standard er 30 rullerende dagers
lagring for misbruksovervåking. For en helseportal er det en materiell forskjell.

> **⚠ Ikke verifisert mot primærkilden.** Scaleways eget domene var blokkert av
> egress-proxyen da dette ble skrevet, så opplysningene over kommer fra søkeresultater og
> tredjepartskilder. **Verifiser mot Scaleways egen dokumentasjon før beslutning**, særlig
> zero retention-formuleringen i avtaleteksten og underbehandlerlista.

To ting gjelder uansett leverandør:

- **Krev zero retention skriftlig i DPA-en**, ikke i markedsføringen. Forskjellen mellom en
  påstand på en nettside og en avtalefestet forpliktelse er hele poenget når noen spør
- **Be om underbehandlerlista.** GPU-compute, CDN og lagring er alle underbehandlere etter
  art. 28. En EU-leverandør som bruker amerikansk GPU-kapasitet under har flyttet
  problemet, ikke løst det

### 3.9 Den innvendingen som består

Uavhengig av personvern: **tolkningen kan ikke etterprøves av den som leser den.**

Rapporten leses av noen som ikke var der — det er poenget med den. Men da kan de heller
ikke se at tolkningen er feil. Tallene er signert og kontrollerbare; setningen
«responstidene lå innenfor det normale» er det ikke, og den kan være gal på en måte som
ser helt rimelig ut.

Portalen har en linje her som er verdt å holde. Oppdragsstatistikken utelater varigheter
som slutter i en automatisk stempling, «fordi sluttiden da er avledet, ikke målt», og
rapporterer det i `summary['utelatt']`. En LLM-tolkning er avledet i mye sterkere forstand.

**Konsekvensen er ikke å la være, men å presentere den riktig:**

- Tolkningen står **ved siden av** tallene, aldri i stedet for
- Synlig merket som maskingenerert og ikke kvalitetssikret
- Tallene den bygger på står i samme rapport, slik at leseren kan sjekke

André har sagt seg enig i merking og logging.

---

## 4. Arkitektur

### 4.1 Retningen

Regelen er at **modulen som eier dataene regner ut tallene**, og at den som viser dem
henter gjennom et register i `core`. Statistikkappen er mønsteret:
`StatistikkappenNavngirIngenKilde` håndhever med AST at den ikke nevner en kildemodul.

- **Timeberegningen hører hjemme i `vaktliste`**, ikke i `rapport`. Utvid
  `belastning_per_person()` med aggregering per korps, rolle og dag, og la vaktlista melde
  inn en `BaseStatistikkHandler` — den har ingen i dag
- `rapport` komponerer gjennom `core.stats` og **navngir ingen modul**
- Samme AST-test som statistikkappen har

### 4.2 Egen modul, ikke en fane i statistikk

Vurdert begge veier. **Egen modul**, og hovedgrunnen er frysingen: statistikk er en
visning som alltid viser nåtid, en rapport er et dokument med en dato. To så ulike
livsløp i samme app ville gjort begge vanskeligere å forklare.

Tilgangsaksen trekker samme vei — penger er ikke statistikk, og André har alt bestemt at
`/rapport/` skal ha egen modultilgang.

### 4.3 Hva som må på plass uansett

- `rapport/module.py` og registrering i `core/modules.py`, med `nivaaer` og `nivaa_navn`
- **Backup-handler.** Vaktlistemodulen sto uten backup i det hele tatt fram til 13. sep.
  2026 — «korps, mannskap med telefon og ISSI, ressursene og vaktpostene lå utenfor alle
  filer siden appen gikk i prod». Et fakturaarkiv uten backup er verre:
  `core.arkiv.har_backup_etter()` er sperren foran kollaps
- **Arkiv-handler** for frosne rapporter, etter `core.arkiv`-mønsteret
- **Audit på feltnivå** for satsen, for frysing og for hvert LLM-kall

---

## 5. Anbefalt rekkefølge

1. **Rydd overlapp i vaktlista** (`TODO.md`). Uavhengig verdi, og en forutsetning for at
   timetallene skal kunne brukes til penger
2. **Timeregnskap uten frysing** — tabellen, dagsfordelingen, satsen. Verdi med én gang
3. **Frysing og signatur** — gjør det til et fakturagrunnlag
4. **Rapport variant A** — tall og tabeller fra `core.stats`. Fortsatt ingen ny
   databehandler
5. **Kategorifilteret** — bygges før variant B, og testes uten at noe sendes noe sted
6. **Variant B**, hvis savnet melder seg etter at 1–4 har vært i bruk en vakt eller to

Stegene 1–4 krever ingen personvernbeslutning. Det er en fordel: dere kan komme langt uten
å ta stilling til LLM-spørsmålet i det hele tatt.

---

## 6. Det som fortsatt er åpent

1. **Terskel eller ikke i tillegg til ekskludering?** Anbefalingen er ekskludering alene i
   første omgang (§3.4), men det bør sies eksplisitt at undertrykking er fravalgt og ikke
   glemt
2. **Hvilke kategorier godkjennes for utsending?** Ikke en teknisk avgjørelse. Listen bør
   settes én gang, av et menneske, og endres bevisst
3. **Skal pasientmodulens problemstillinger flyttes fra `choices.py` til en tabell?**
   (§3.5) Nødvendig for at admin skal kunne styre filteret begge steder
4. **Probono som egen kolonne i økonomirapporten?** (§2.6)
5. **Verifiser Scaleway mot primærkilden** (§3.8)

---

*Ingen kode er skrevet. Dette er grunnlag for en beslutning, ikke en plan.*
