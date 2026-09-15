# Forslag: planleggerfane i vaktlista

**Skrevet 15. september 2026.** André:

> «En planlegger-fane i /vaktlisten. Planleggerfanen lar en generere skift og sette de opp
> på enheter/ressurser. En kan sette inn total timer og da jobbe overordnet med hvor mange
> en kan ha på vakt.»

Notatet finnes fordi dette er den første funksjonen i vaktlista som **lager rader for deg**
i stedet for å la deg skrive dem — og fordi det meste den trenger allerede finnes, spredt
på fire steder. Ingenting her er bygget.

---

## 1. Avgjort allerede

**Timetallet er et tak som varsler, ikke en inngangsverdi generatoren regner fra**
(André, 15. sep. 2026). Du setter for eksempel 400 timer; planleggeren viser forbrukte og
gjenværende timer mens du legger inn skift, og sier fra når summen passerer taket.

Det er samme linje som `Belastningsgrenser`: **«varsler, de sperrer ikke»**. Noen ganger må
en vakt bemannes over budsjett, og da skal lista si det høyt framfor å tvinge planleggeren
til å lyve om tidene for å komme videre. Fargen er gul (`--vl-varsel`), ikke rød.

Valget betyr også at generatoren *ikke* skal gjette skiftlengde, overlapp eller antall per
ressurs ut fra et timetall. **En generert liste ingen har sagt ja til ser ferdig ut** — den
samme grunnen til at `kopier_oppsett` tar ressursene og aldri personene.

---

## 2. Det meste finnes allerede — spredt

Planleggeren skal i stor grad *samle* ting som er bygget, ikke finne dem opp:

| Trengs | Finnes som | Hvor |
|---|---|---|
| Timesum for et utvalg skift | `_sumTimer()` | `vaktliste-tegning.js` |
| «Hvor mange er på vakt time for time» | `mkGruppekurve()` / `_bemanningPerTime()` | samme fil |
| Vaktas spenn | `_vaktensSpenn()` | samme fil |
| Belastning per person | `services.belastning_per_person()` | `vaktliste/services.py` |
| Å kopiere et oppsett til en ny vakt | `services.kopier_oppsett()` | samme |
| En ledig plass | `Vaktpost` uten `mannskap` | `vaktliste/models.py` |

**Den siste raden er den viktigste.** «Å generere et skift» er ikke en ny modell — det er å
opprette `Vaktpost`-rader uten `mannskap`. Modellen er allerede bygget for det: *«en ledig
plass er en `Vaktpost` uten mannskap. Planlegging begynner med behovet, og å fylle plassen
er én feltendring.»*

Planleggeren er derfor **en ny flate over eksisterende modeller**, ikke et nytt datalag.
Det er den billigste og den farligste sorten funksjon: billig å bygge, lett å la duplisere
regler som alt finnes.

---

## 3. Fellene, i rekkefølge etter hvor stille de er

### 3.1 `bulk_create` vil ødelegge auditsporet

`CLAUDE.md`, om vaktlista:

> Skift og ressurser auditlogges på feltnivå … Derfor **ingen `bulk_create` på disse
> modellene** — den hopper over signalene; `kopier_oppsett` gikk i den fella.

En generator som lager tretti plasser er nettopp stedet noen vil gripe etter `bulk_create`.
Gjør man det, forsvinner tretti auditrader uten at noe feiler. Plassene skal opprettes én
og én, i én `transaction.atomic()`.

### 3.2 Den doble regelen må gjelde også når maskinen setter plassene

`services.kan_sette_vaktpost()` slår sammen badgen og reservasjonen, og finnes som **én**
funksjon nettopp for at et endepunkt ikke skal kunne huske den ene og glemme den andre.

Generatoren lager *ledige* plasser, og å opprette en ledig plass er `skriv_full` —
vaktleder setter behovet. Så lenge den ikke fyller dem, er `kan_sette_vaktpost()` ikke i
spill. **Men i det øyeblikket noen ber generatoren også sette folk på plassene, er den
det** — og da må den gå gjennom samme funksjon som alt annet, ikke rundt den.

*Avgjort 15. sep. 2026 (§6, beslutning 3): generatoren lager **bare tomme plasser**.* Det
holder regelen utenfor spill, og det er derfor beslutningen er verdt noe: ikke fordi
fylling er vanskelig, men fordi en generator som fyller må bære hele tilgangsmodellen inn
i en løkke.

### 3.3 Midnatt: avgjort begge steder, og de er *ment* å være ulike

*Skrevet om 15. sep. 2026. Den første utgaven av dette avsnittet var upresis, og
upresisheten pekte mot feil beslutning.*

- **Oversikten og gruppefanene:** et skift hører til **startdagen** (`_dagnokkel()`).
- **Rapportmodulen:** timer **splittes ved midnatt** (`FORSLAG_RAPPORTMODUL.md` §2.2).

Den første utgaven sa at planleggeren «bør følge rapportmodulens regel, fordi det er
*timer* som telles». **Det er galt, og feilen er verdt å skrive ned:** splitting ved
midnatt endrer ikke en *totalsum*. Fredag 20:00 – lørdag 04:00 er åtte timer uansett
hvilken dag man fører dem på. Regelen betyr bare noe når timene **brytes ned per dag** —
altså for rapportmodulen, som fakturerer per døgn, og ikke for et tak over hele vakta.

Så det finnes ingen konflikt å løse, bare et valg om hvilken dag *dagslinja* fører timene
på. **Avgjort: startdagen** (André, 15. sep. 2026), av tre grunner:

1. **Ett tall per skift, ett sted.** Splitter dagslinja, står «fre. 20:00 – lør. 04:00» med
   4 timer under fredag og 4 under lørdag, mens ressursoverskriften rett over viser 8 på
   fredag. To tall som ser like ut og ikke er det — nøyaktig den fella avsnittet advarte mot.
2. **Dagslinja svarer på «hvor mye har jeg lagt på denne dagen», ikke «hvor mange er på
   vakt kl. 02».** Det siste spørsmålet har allerede et bedre svar: bemanningskurven, som
   bøtter per time og tegner midnatt som en egen strek (`vl-dogn`).
3. **Hele vaktlisteflaten bruker allerede startdagen.** En planleggerfane som teller
   annerledes enn fanen ved siden av, lærer brukeren at tallene ikke kan sammenlignes.

Regelen, skrevet så den kan stå begge steder: **planlegging fører skiftet på startdagen;
fakturering splitter ved midnatt.** Forskjellen er bevisst, fordi spørsmålene er ulike —
«hvem er på vakt den dagen» mot «hvor mange timer skal betales for det døgnet». Den står
allerede i `CLAUDE.md` for `_dagnokkel()`, og skal stå i rapportmodulens notat også.

### 3.4 Overlapp blåser opp summen, og det er kjent

Målt 14. sep. 2026: skift 12:00–20:00 og 16:00–22:00 på samme person gir `timer = 14,0`,
mens personen var til stede i 10. Punktet står i `TODO.md`.

For planlegging mot et tak er dette ikke lenger harmløst: budsjettet brukes opp av timer
ingen jobber. **`overlapp`-punktet i TODO bør løses før eller sammen med planleggeren**,
ikke etter. *Avgjort 15. sep. 2026 (beslutning 8): først.*

---

## 4. Skisse

Fanen ligger ved siden av «Oversikt» og «Mannskap», og har fire deler:

**1. Budsjettlinja.** «Tak: 400 t · Satt opp: 312 t · Bemannet: 244 t · Igjen: 88 t». Gult
merke når taket passeres. Taket lagres på `Vaktliste` — det gjelder *denne* vakta, i
motsetning til `Belastningsgrenser`, som er organisasjonens og gjelder alle. Å sette det er
`skriv_full`, som alt annet oppsett på en vaktliste.

**2. Dagslinja.** «fre. 128 t · lør. 152 t · søn. 32 t». Ingen tak per dag — bare tallet,
så man ser hvilken dag som bærer vekten. Timene føres på skiftets startdag (§3.3).

**3. Generatoren.** «Legg til N plasser på \<ressurs\>, fra–til, rolle». Oppretter ledige
`Vaktpost`-rader og ingenting mer. Ikke noe mer intelligent enn det: en generator som
gjetter er en generator man må kontrollere, og da er den ikke raskere enn å skrive radene.

**4. Bildet av vakta.** Bemanningskurven per gruppe, som i dag — men samlet på én flate, så
man ser hvor hullene og toppene er mens man legger inn. Kurven finnes (`mkGruppekurve`);
det nye er å vise flere ved siden av hverandre over samme spenn (`_vaktensSpenn()` sørger
alt for at spennet er felles).

---

## 5. Avklarte spørsmål

De seks spørsmålene denne skissen åpnet med er besvart 15. sep. 2026. Svarene står som
beslutninger i §6; her er kartet fra spørsmål til svar:

| Spørsmål (opprinnelig §5) | Svar |
|---|---|
| Hvilken midnattsregel teller planleggerens timer? | **Startdagen.** Spørsmålet var feilstilt — se §3.3. Beslutning 2 |
| Skal generatoren kunne fylle plassene? | **Nei, bare tomme plasser.** Beslutning 3 |
| Hva skjer med plasser som alt finnes ved ny generering? | **Tomme erstattes, korpsreserverte tomme og alle bemannede beholdes.** Beslutning 4 |
| Teller taket ledige plasser eller bare bemannede? | **Begge, side om side.** Beslutning 5 |
| Skal taket kopieres av `kopier_oppsett`? | **Ja.** Beslutning 6 |
| Overlapp-punktet i TODO — før eller etter? | **Før.** Beslutning 8 |

---

## 6. Beslutninger (15. september 2026)

Alle åtte er Andrés, tatt i gjennomgangen av dette notatet. De står her fordi en beslutning
som bare finnes i en samtale blir tatt om igjen neste gang noen leser koden.

### 1. Timetallet er et tak som varsler, ikke en inngangsverdi

Står i §1 fra før. Generatoren regner *ikke* skiftlengde, overlapp eller antall ut av et
timetall; du setter taket, og planleggeren sier fra når du passerer det. Gult, ikke rødt.

### 2. Ett tak for hele vakta — og en dagslinje uten egne tak

> «Egentlig valg 1. men gjerne at det vises hvor mange timer er satt på dag1 dag 2 osv.
> trenger ikke tak på de individuelle dagene.»

Taket er **ett tall for hele vaktlista**. Dagslinja viser hvor mange timer som er lagt på
hver dag, men har ingen egen grense.

**Hvorfor det er riktig:** et tak per dag er en ny sperre å vedlikeholde, og den ville
sperret det man faktisk gjør — flytte timer mellom dagene mens totalen står. Dagstallene
gir oversikten uten å innføre en regel som må overstyres.

Timene føres på skiftets **startdag** (§3.3). Vil man vite hvor mange som er på vakt klokka
02, er svaret bemanningskurven, ikke dagslinja.

### 3. Generatoren lager bare tomme plasser

> «Bare tomme plasser»

Generatoren oppretter `Vaktpost`-rader uten `mannskap`, aldri med.

**Hvorfor:** det holder generatoren på `skriv_full`-siden av tilgangsmodellen og
`kan_sette_vaktpost()` utenfor spill (§3.2). Og det holder linja fra `kopier_oppsett`:
**en liste ingen har sagt ja til ser ferdig ut.** Plassene er et behov noen skal fylle;
navnene settes av et menneske som vet hvem som kan.

### 4. Ny generering erstatter tomme plasser — unntatt de korpsreserverte

> «Erstatt tomme men tomme plasser som er reservert til korps beholdes.»

Kjører man generatoren på nytt over samme ressurs og spenn:

| Plass | Hva skjer |
|---|---|
| Tom, uten reservasjon | **Erstattes** |
| Tom, reservert til et korps (`Vaktpost.korps` eller ressursens) | **Beholdes** |
| Bemannet | **Beholdes** — alltid |

**Hvorfor unntaket finnes:** en tom plass uten reservasjon er generatorens eget utkast, og
å skrive over sitt eget utkast koster ingenting. En **reservert** tom plass er derimot et
løfte til et korps — noen har sagt «denne er deres» — og korpset ser den i «Mitt korps» og
planlegger mot den. Å slette den er å trekke tilbake en tildeling uten at noen ba om det.

Merk at `services.reservert_korps()` er det ene stedet som avgjør om en plass er reservert:
plassens egen `korps` overstyrer ressursens, og tom verdi betyr «som ressursen». Generatoren
skal spørre den funksjonen, ikke lese feltet.

**Bemannede plasser slettes aldri automatisk**, uansett. Det er den slags handling som må
bekreftes to ganger, som sletting av en ressurs — og da hører den ikke hjemme i en
generator.

### 5. Taket viser begge tall side om side

> «Begge tall, side om side»

Budsjettlinja viser **satt opp** (alle plasser, ledige inkludert) *og* **bemannet** (bare
plasser med `mannskap`).

**Hvorfor begge:** de svarer på hvert sitt spørsmål, og hvert av dem alene lyver litt.
«Satt opp» er behovet — det planleggingen handler om — men det er ikke det noen betaler
for. «Bemannet» er det nærmeste vi kommer kostnad, men tidlig i planleggingen er det null,
og et budsjett som står på null når lista er halvt satt opp forteller ingenting.

Avstanden mellom dem er dessuten selve arbeidslista: 312 satt opp og 244 bemannet betyr
68 timer som mangler folk.

### 6. Taket kopieres av `kopier_oppsett`

Ressursene kopieres til neste vakt, personene ikke. Taket ligger nærmere ressursene: det er
en egenskap ved *arrangementet* man setter opp på nytt, ikke ved menneskene.

Det er heller ikke farlig å ta feil her, i motsetning til personene: et tak som følger med
og ikke stemmer, gir et gult varsel man retter på fem sekunder.

### 7. Dagslinja følger startdagen, ikke midnattssplittingen

Se §3.3 for hele begrunnelsen. Kort: splitting endrer ikke en totalsum, bare en
nedbryting — og en planleggerfane som bryter ned annerledes enn fanen ved siden av, lærer
brukeren at tallene ikke kan sammenlignes.

**Regelen som skal stå begge steder:** planlegging fører skiftet på startdagen, fakturering
splitter ved midnatt.

### 8. Overlapp-punktet løses først

Et tak som telles feil er verre enn ikke noe tak. Så lenge to overlappende skift på samme
person gir 14 timer der personen sto 10, spiser budsjettet timer ingen jobber — og
planleggeren er den første funksjonen som *bruker* det tallet til noe.

---

## 7. Anbefalt rekkefølge

1. **Løs `overlapp`-punktet i TODO** (beslutning 8). Et tak som telles feil er verre enn
   ikke noe tak.
2. **Budsjettlinja og dagslinja** — de leser bare det som finnes, og gir verdi uten
   generatoren. Her lander beslutning 2, 5 og 7.
3. **Taket på `Vaktliste`**, med `kopier_oppsett` (beslutning 6). Én migrasjon, ett felt,
   `skriv_full`.
4. **Bildet av vakta** — kurvene ved siden av hverandre over felles spenn.
5. **Generatoren til slutt**, i sin enkleste form: N tomme plasser, fra–til, rolle
   (beslutning 3), med erstatningsregelen fra beslutning 4. Den kan bli smartere senere;
   den kan ikke bli mindre farlig.
