# Forslag: rapportmodul

> **Status: forslag, ikke besluttet.** Ingen kode er skrevet. Skrevet 14. sep. 2026 på
> Andrés spørsmål: en `/rapport/`-modul som henter fra vaktlista og statistikken og gjør
> to ting — et timeregnskap med kroner per korps, og en generert vaktrapport.
>
> *Fila heter `FORSLAG_` og ikke `rapportmodul.md` for å følge navneskikken i `docs/`:
> `BESLUTNING_*` er avgjort, `FORSLAG_*` er ikke. Se `FORSLAG_DATTEROPPDRAG.md`.*

---

## 1. Kort svar

**Del 1 — timeregnskapet — er et godt forslag.** Dataene finnes allerede, beregningen
finnes delvis, og modellen er forberedt på tanken uten at noen planla det. Den løser et
konkret administrativt problem, og den kan bygges uten å røre noe følsomt.

**Del 2 — den genererte vaktrapporten — er den jeg vil be deg tenke nøye gjennom.**
Ikke fordi den er teknisk vanskelig, men fordi den flytter helseopplysninger til en ny
databehandler, og fordi den delen som er vanskeligst å stole på — tolkningen — er
nettopp den delen som skal leses av noen som ikke var der.

Begge deler er mulige. De har bare svært ulik pris.

---

## 2. Del 1: timeregnskap og betaling

### 2.1 Det meste finnes allerede

Dette er ikke et forslag om å bygge noe nytt fra bunnen. Se `vaktliste/services.py`:

| Finnes i dag | Hva den gjør |
|---|---|
| `belastning_per_person()` | Timer, skift, lengste skift, korteste hvile — per person |
| `_timer(fra, til)` | Timeberegningen |
| `Vaktpost.fra_tid` / `til_tid` | Planen |
| `Vaktpost.mott_at` / `av_vakt_at` | Hva som faktisk skjedde |
| `Mannskap.korps` | Aksen «per korps» |
| `Vaktpost.rolle` | Aksen «per rolle» |
| **`Vaktpost.probono`** | **Skiftet går, men telles ikke i timene** |

Det siste er verdt å stoppe ved. Feltet ble laget 11. sep. 2026, og kommentaren i
`services.py` sier:

> «Probono telles ikke i timene, men i alt annet. **Summen er det organisasjonen betaler
> for**; lengste skift og korteste hvile er hva kroppen tåler.»

Betalingstanken er altså allerede inne i modellen — den mangler bare et kronebeløp og en
aggregering. Det er et sterkt signal om at forslaget passer der det hører hjemme.

### 2.2 Det ene spørsmålet som må avgjøres først

**Betaler dere for planlagte timer eller for stemplede timer?**

Det er ikke et teknisk spørsmål. Modellen holder dem bevisst fra hverandre («Plan og
faktisk er fire felter, ikke to. Avviket er informasjonen»), så portalen kan svare på
begge — men et fakturagrunnlag må velge, og valget har konsekvenser:

| Grunnlag | Fordel | Problemet |
|---|---|---|
| **Plan** (`fra_tid`/`til_tid`) | Alltid komplett. Kjent på forhånd, så korpset vet hva de får | Betaler for noen som ikke møtte |
| **Faktisk** (`mott_at`/`av_vakt_at`) | Betaler for arbeid som ble gjort | **Ufullstendig.** Én som glemmer å stemple av gir null timer — eller uendelig |

`belastning_per_person()` regner allerede faktisk tid **bare for ferdige skift** (både
`mott_at` og `av_vakt_at` satt), nettopp fordi et pågående skift ville gitt et tall som
endrer seg mens man ser på det. Den regelen er riktig for et varsel. For en faktura er den
farlig: et uferdig skift blir stille borte fra summen.

**Min anbefaling:** plan som grunnlag, faktisk som **avvikskolonne** ved siden av. Da er
summen alltid komplett, og den som godkjenner ser hvilke rader som ikke stemmer og kan ta
dem opp før fakturering. Du fakturerer på det dere avtalte, ikke på hvor flink noen var
til å trykke på en knapp.

### 2.3 Kroner per time — hvor hører satsen hjemme?

Tre mulige akser, og de utelukker ikke hverandre:

| Sats per | Når det gir mening |
|---|---|
| **Korps** | Ulike avtaler med ulike korps |
| **Ressursrolle** | En lagleder koster mer enn en førstehjelper |
| **Ressursgruppe** | En ambulansetime koster noe annet enn en samleplasstime |

Portalen har et etablert mønster for slikt: **verdimengder er tabeller, ikke tall i en
`if`** — se `Ressursgruppe`, `Problemstilling`, `Belastningsgrenser`. Samme her. Og
`Belastningsgrenser` er den nærmeste parallellen: «Grensene er organisasjonens, ikke
portalens — derfor data og ikke tall i en `if`.»

**Satsen må dateres.** Endrer dere satsen i mars, skal ikke januarrapporten endre seg. Det
peker mot neste punkt, som er det viktigste i hele del 1.

### 2.4 Det viktigste: tall som brukes til penger må fryses

Dette er den arkitektoniske innsikten jeg vil at du tar med deg.

I dag er vaktlistedata **operative**: de beskriver hvem som er på vakt nå, og de kan
rettes fritt. I det øyeblikket de blir et **fakturagrunnlag**, endrer de karakter. Da må
det finnes et punkt der tallene slutter å bevege seg.

Uten det: noen retter et skift i mars fordi tiden sto feil, og fjorårets faktura
stemmer ikke lenger med det portalen viser. Ingen har gjort noe galt, og likevel er
regnskapet ikke etterprøvbart.

**Portalen har allerede mønsteret for dette**, to ganger: `patients/arkiv.py` og
`oppdrag/arkiv.py`. `core.arkiv` eier frysing, SHA-256-signatur og kollaps; modulen eier
hva som går inn i signaturen. En rapport som fryses ville:

- lagre tallene slik de var, ikke en peker til rader som kan endre seg
- lagre **satsen som ble brukt**, ikke en peker til en sats som kan endres
- signeres, slik at det er etterprøvbart at rapporten ikke er rørt i etterkant
- lagre hvem som godkjente den, og når

Det er samme resonnement som ligger bak at `VaktArkiv` ikke fikk arve `AbstractArkiv`:
signaturen er en del av dataene, og en signatur som kan regnes om er ingen signatur.

**Konsekvens for omfanget:** del 1 er ikke «en tabell med timer». Den er et
lite arkiv med en godkjenningsflyt. Det er fortsatt overkommelig — mønsteret finnes, og
`AbstractArkiv` bærer feltene — men det er ærlig å si det med én gang.

### 2.5 Kantene som koster penger

Disse er verdt å avklare før noen skriver kode, fordi de alle gir feil beløp:

| Tilfelle | Spørsmål |
|---|---|
| Skift over midnatt | Regnes til riktig dato? `_tidsspenn()` håndterer visningen, men hvilken dag «tilhører» timene? |
| Overlappende skift på samme person | Telles begge? `_hviletider()` gir hvile 0, men timene summeres i dag |
| Møtt, aldri av vakt | Med plan som grunnlag: uproblematisk. Med faktisk: et hull |
| Person flyttet mellom korps midt i sesongen | Hvilket korps får timene — `Mannskap.korps` er dagens verdi, ikke historisk |
| Ledig plass som aldri ble fylt | Skal ikke telle. `belastning_per_person()` hopper alt over dem |
| Probono | Teller ikke i kroner, men skal den vises? |

Den nest siste er en ekte modellsvakhet: **korpset ligger på personen, ikke på skiftet.**
Flytter noen korps, endrer historikken seg. Et frosset arkiv løser det for framtida, men
ikke bakover.

### 2.6 Tilgang

Timer og penger per korps er følsomt på en annen måte enn pasientdata — det handler om
organisasjoner og økonomi, ikke om enkeltpersoners helse. Men det er fortsatt
personopplysninger: «Kari gikk 47 timer» er en opplysning om Kari.

Forslag, etter komposisjonsregelen (rollemodellen §5):

- Modulen viser bare det brukeren har tilgang til i **kildemodulen**, som statistikken gjør
- Timeregnskap per korps: `skriv_leder` på vaktliste, eller global admin
- Beløp: global admin. Satsene er avtaler, ikke driftsdata
- En korps-fører bør kunne se **sitt eget korps'** timer — det er hennes folk

---

## 3. Del 2: den genererte vaktrapporten

Her vil jeg være tydelig, fordi du ba om ærlige tilbakemeldinger.

### 3.1 Det tekniske er den enkle delen

Å sette sammen tallene finnes nesten ferdig: `core.stats`-registeret har allerede
`patients/statistikk.py` og `oppdrag/statistikk.py`, og vaktlista kan melde inn en
handler på samme måte. En rapport som fletter dem er ren komposisjon.

**Det er tolkningen som er forslaget.** Og den er ikke et teknisk problem.

### 3.2 En LLM er en ny databehandler

I det øyeblikket portalen sender data til en språkmodell, har dere en ny underbehandler.
Det utløser konkret arbeid i `docs/PERSONVERN_DOKUMENTASJON.md`:

| Hvor | Hva som må endres |
|---|---|
| **A.2** | Ny databehandler med DPA, behandlingsregion og hva som sendes |
| **A.8** | Står i dag: **«Ingen behandling skjer utenfor EU/EØS.»** De fleste modellleverandører bryter den setningen |
| **A.7** | Ny mottaker av personopplysninger |
| **A.12** | Ny risikovurdering |
| **C.3** | DPA-sjekklista |

A.8 er den harde. Slik protokollen står i dag, er «ingen overføring utenfor EU/EØS» et
løfte dere har gitt skriftlig. Å bryte det for en rapportfunksjon er en avgjørelse som
hører hjemme hos den behandlingsansvarlige — altså deg — og ikke i en teknisk vurdering.

### 3.3 «Uten navn» er ikke det samme som anonymt

Du skriver at rapporten skal lages «uten å ta inn navn/mail og slikt». Det er riktig
instinkt, men det holder ikke som anonymisering.

Vurder: *«Landsskytterstevnet, 3. august, én rød pasient, hjertestans, kl. 14:32,
transportert.»* Ingen navn. Men på et navngitt arrangement, på en gitt dato, er det
sannsynligvis nøyaktig én person det kan være — og opplysningen er art. 9-data.

Det som beskytter er ikke fraværet av navn, men **små tall**. Én pasient i en kategori er
identifiserende; tretti er det ikke. Skal dette bygges, må rapporten ha en regel om
minste gruppestørrelse, og undertrykke kategorier under den.

**Og fritekstfeltene må aldri sendes.** `Oppdrag.fritekst`, `Mannskap.notat` og
`Vaktpost.merknad` er unntatt verdilogging i audit, og `fritekst` arkiveres ikke i det
hele tatt — begge deler fordi fritekst er *der helseopplysninger havner når det ikke
finnes et felt for dem*. Å sende dem til en ekstern modell ville gjøre de beslutningene
meningsløse.

### 3.4 En tolkning ingen kan etterprøve

Dette er den innvendingen jeg mener tyngst.

En generert vaktrapport leses av noen som **ikke var der**. Det er hele poenget med den.
Men det betyr også at leseren ikke kan se at tolkningen er feil.

Tallene er etterprøvbare — de kommer fra arkivet, og de er signert. Setningen «belastningen
var moderat, og responstidene lå innenfor det normale» er det ikke. Den kan være feil på
en måte som ser helt rimelig ut, og i en rapport om en sanitetsvakt kan det få
konsekvenser for hvordan neste vakt planlegges.

Portalen har en gjennomgående linje her, og den er verdt å holde: **utledede tall
markeres**. Oppdragsstatistikken utelater varigheter som slutter i en automatisk
stempling, «fordi sluttiden da er avledet, ikke målt», og rapporterer det i
`summary['utelatt']`. Det er samme slags omhu. En LLM-tolkning er avledet i mye sterkere
forstand.

### 3.5 Hva jeg ville gjort i stedet

**Skill rapporten fra tolkningen.**

1. **Portalen genererer rapporten** — tall, tabeller, kurver, og et *strukturert*
   sammendrag av formen «X oppdrag, Y pasienter, lengste responstid Z». Ingen LLM, ingen
   ny databehandler, ingen endring i personvernprotokollen. Dette dekker etter min
   vurdering det meste av behovet.
2. **Vil noen ha prosa**, kan de ta rapporten og be om det selv — utenfor portalen, under
   eget ansvar, med sin egen vurdering av hva som kan deles.

Da slipper portalen å stå i behandlerkjeden for noe den ikke trenger å stå i.

**Vil dere likevel ha det i portalen**, er dette minstekravene:

- Opt-in per rapport, aldri automatisk
- **Forhåndsvisning av nøyaktig hva som sendes**, før det sendes
- EU-hostet modell med DPA på plass, og A.2/A.7/A.8 oppdatert *før* første kall
- Aldri fritekst, aldri navn, aldri kontoer
- Minste gruppestørrelse håndhevet i koden, ikke i prompten
- Resultatet merket synlig som maskingenerert og ikke kvalitetssikret
- Hvert kall auditlogget: hvem, når, hvilken rapport

Det siste punktet er ikke byråkrati. Uten det kan dere ikke svare på «hva ble sendt ut av
huset» når noen spør.

---

## 4. Arkitektur — hvis dette bygges

### 4.1 Retningen

Regelen i portalen er at **modulen som eier dataene regner ut tallene**, og at den som
viser dem henter gjennom et register i `core`. Statistikkappen er mønsteret:
`StatistikkappenNavngirIngenKilde` håndhever med AST at den ikke nevner en kildemodul.

Det betyr:

- **Timeberegningen hører hjemme i `vaktliste`**, ikke i `rapport`. Utvid
  `belastning_per_person()` med aggregering per korps og rolle, og la vaktlista melde inn
  en `BaseStatistikkHandler` — den har ingen i dag
- `rapport` komponerer gjennom `core.stats`, og **navngir ingen modul**
- Samme AST-test som statistikkappen har

### 4.2 Egen modul, eller en fane i statistikk?

Verdt å stille spørsmålet før noen lager en app.

| For egen modul | For en fane i `statistikk` |
|---|---|
| Egen tilgangsakse — penger er ikke statistikk | Statistikkappen *er* allerede komposisjonslaget |
| Egen livssyklus: frys, godkjenn, arkiver | Én modul færre å vedlikeholde |
| `/rapport/` er lettere å finne for den som skal fakturere | Brukeren tenker kanskje «tall» og leter i statistikk |

**Min vurdering: egen modul**, men først og fremst på grunn av frysingen. En rapport som
skal godkjennes og arkiveres har en livssyklus statistikkappen ikke har — statistikk er en
visning som alltid viser nåtid, en rapport er et dokument med en dato. Å legge to så ulike
livsløp i samme app ville gjort begge vanskeligere å forklare.

### 4.3 Hva som må på plass uansett

- `<app>/module.py` og registrering i `core/modules.py`
- **Backup-handler.** Vaktlistemodulen sto uten backup i det hele tatt fram til 13. sep.
  2026 — «korps, mannskap med telefon og ISSI, ressursene og vaktpostene lå utenfor alle
  filer siden appen gikk i prod». Den feilen skal ikke gjentas, og et fakturaarkiv uten
  backup er verre: `core.arkiv.har_backup_etter()` er sperren foran kollaps
- Arkiv-handler hvis rapporter fryses
- Audit på feltnivå for satsene og for godkjenning

---

## 5. Åpne spørsmål til André

Disse endrer hva som bygges, og bør besvares før noen skriver kode:

1. **Plan eller faktisk som fakturagrunnlag?** (§2.2 — jeg anbefaler plan, med faktisk som
   avvikskolonne)
2. **Sats per korps, rolle eller ressursgruppe?** Eller flere samtidig? (§2.3)
3. **Skal rapporter fryses og godkjennes?** Hvis ja, er dette et arkiv og ikke en visning
   (§2.4). Hvis nei — hvordan skal en faktura kunne etterprøves et år senere?
4. **Hva skjer når noen flytter korps?** (§2.5) Skal timene følge personen eller korpset
   hun gikk for?
5. **Del 2: er en strukturert rapport uten LLM nok?** (§3.5) Og hvis ikke — er du som
   behandlingsansvarlig villig til å endre A.8?

---

## 6. Oppsummert

| Del | Vurdering | Hvorfor |
|---|---|---|
| **Timeregnskap** | **Anbefales.** Dataene finnes, `probono` viser at tanken alt er inne i modellen | Løser et konkret administrativt problem |
| **Kroner per korps** | **Anbefales, med frysing** | Uten et frosset arkiv er ikke fakturagrunnlaget etterprøvbart |
| **Rapport med tall og tabeller** | **Anbefales.** Ren komposisjon gjennom `core.stats` | Ingen ny databehandler, ingen endring i personvernprotokollen |
| **LLM-tolkning i portalen** | **Frarådes i første omgang** | Ny databehandler, A.8 må brytes, «uten navn» er ikke anonymt, og tolkningen er den delen leseren ikke kan etterprøve |

Del 1 kan begynne uten at del 2 er avgjort. Det er en fordel: timeregnskapet har verdi
alene, og det tvinger ikke fram en personvernbeslutning før dere er klare til å ta den.

---

*Ingen kode er skrevet. Dette dokumentet er et grunnlag for en beslutning, ikke en plan.*
