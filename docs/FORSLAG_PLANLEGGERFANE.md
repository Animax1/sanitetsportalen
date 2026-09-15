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

**1. Budsjettlinja.** «Tak: 400 t · Satt opp: 312 t · Bemannet: 244 t · Igjen: 88 t ·
Probono: 16 t». Gult
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

De seks spørsmålene denne skissen åpnet med er besvart 15. sep. 2026, og **tre til kom til**
da koden ble lest før byggingen (beslutning 9–11 i §6). Svarene står som beslutninger i §6;
her er kartet fra spørsmål til svar:

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

### 9. Probono teller ikke mot taket, men vises for seg

Både `_sumTimer()` i JS og `belastning_per_person()` utelater probono fra
timesummene i dag. Budsjettlinja følger samme regel — taket er det
organisasjonen betaler for — og får en egen post: «Probono: N t».

**Hvorfor posten må stå der:** et tall som utelater noe uten å si det, er et
tall noen kommer til å bestride, og da har man ikke lenger et budsjett man kan
vise til. «Mitt korps» har alt løst det samme problemet på samme måte —
bemannet, å dekke, åpent for alle og probono ved siden av hverandre.

*Dette spørsmålet sto ikke i notatets første utgave i det hele tatt. Det ble
funnet ved å lese `_sumTimer()` før byggingen begynte, og det er grunnen til at
gjennomgangen var verdt en time: notatet beskrev et tall som allerede hadde en
regel jeg ikke hadde lest.*

### 10. Genererte plasser fødes som **planlagt** — lederens kladd

`services.er_planlagt()` er tilstanden: ikke reservert til et korps, ikke åpnet
for alle, og usynlig for korps-brukerne. Generatoren lager plassene der, og du
deler dem ut når oppsettet er ferdig.

**Hvorfor:** uten det ser et halvferdig oppsett ferdig ut for alle korps i det
øyeblikket generatoren kjører — samme feil som `kopier_oppsett` unngår ved aldri
å ta personene med. Og «planlagt går én vei» er alt håndhevet, så en plass du
har delt ut kan ikke falle tilbake til å bli generatorens bytte.

### 11. «Åpen for alle»-plasser overlever en ny generering

Beslutning 4 nevnte to tilstander. Koden har **fire**, og `alle_korps` er den
som falt utenfor:

| Tilstand | Ved ny generering |
|---|---|
| Planlagt (`er_planlagt()`) — generatorens kladd | **Erstattes** |
| Reservert til et korps | Beholdes |
| Åpen for alle (`alle_korps`) | Beholdes |
| Bemannet | Beholdes — alltid |

`alle_korps` er også en utdeling: korpsene ser plassen i «Mitt korps», den har
sin egen timekolonne der («åpent for alle»), og de planlegger mot den. Å slette
den er å trekke tilbake noe som er delt ut.

**Med beslutning 10 blir regelen én setning:** *generatoren rører bare det
`er_planlagt()` kaller kladd.* Alt som er delt ut — til ett korps eller til alle
— står. Det er den formen regelen skal skrives i, ikke som en tabell over fire
tilstander: en tabell må vedlikeholdes når tilstand fem kommer, en funksjon
trenger det ikke.

### 11b. Genereringen rører bare de ressursene oppsettet nevner

*Strammet 15. sep. 2026, da planleggeren ble en redigeringsflate (§18).*

Beslutning 4 og 11 svarte på **hvilke plasser** som kan erstattes. Da
planleggeren begynte å lese oppsettet tilbake, kom et annet spørsmål: **hvilke
ressurser?**

`erstatt_kladd` var en bryter i bekreftelsesdialogen som ryddet kladd på **hele
lista** — også på ressurser oppsettet ikke nevnte. Med tilbakelesingen står
alle ressursene i oppsettet som standard, så bryteren gjorde ingenting nytt; det
eneste den kunne gjøre, var å rydde bort kladd på en ressurs man hadde tatt
*ut* av oppsettet. Det er stikk i strid med hva «ta ut» betyr.

Regelen er derfor: **raden som peker på ressursen er den eneste som rører den.**
En ressurs utenfor oppsettet lar generatoren være i fred. Å fjerne en ressurs er
en sletting, og den ligger bak de to bekreftelsene i «Rediger ressurs» — ett
sted, ikke to.

### 12. Budsjettlinja bor i den fanen som alt finnes

*Tatt under byggingen 15. sep. 2026.*

Skissen sa «fanen ligger ved siden av «Oversikt» og «Mannskap»». Det finnes
**allerede** en slik fane, og den heter **«Planlegging»** (belastningsfanen, §8b).
Å legge en ny ved siden av ville gitt to faner som heter «Planlegging» og
«Planlegger» — en bokstavs forskjell, og den som leter etter tallene sine må prøve
begge.

Budsjettlinja og dagslinja står derfor **øverst i «Planlegging»**, over «Per person».
Rekkefølgen er ikke tilfeldig: vaktas tall først, den enkeltes under. Motsatt ville
begravet totalen under en persontabell som kan bli lang.

Kurvene (§7 steg 4) og generatoren (steg 5) hører hjemme samme sted.

### 13. Taket er `skriv_leder`, ikke `skriv_full`

*Rettelse av §4, tatt under byggingen 15. sep. 2026.*

Skissen sa «Å sette det er `skriv_full`, som alt annet oppsett på en vaktliste». Det
holdt ikke mot koden. Taket settes i **samme PUT** som vaktas start og planlagte
slutt (`vaktliste_detalj_view`), og den er `skriv_leder` med en begrunnelse som
gjelder ord for ord her også:

> spennet gjelder hele vakta, ikke ett korps' del av den

Tre grunner til at det skal følge spennet:

1. **Samme rekkevidde.** Taket er tallet *alle* varsler på lista måles mot.
2. **Samme feltfamilie.** Start, slutt og tak er vaktas rammer, og de settes sammen.
3. **Én forespørsel kan ikke ha to tilgangsnivåer inni seg.** En PUT der `startet`
   krever `skriv_leder` og `timetak` krever `skriv_full` er en regel ingen klarer å
   lese riktig — og den som skal håndheve den må skrive den to ganger.

Det gjør taket til per-vakt-søsteren av `Belastningsgrenser`, som også er
`skriv_leder`. Forskjellen mellom dem er rekkevidden, ikke hvem som bestemmer.

### 14. Budsjettallene sendes bare til den som ser alle korps

*Tatt under byggingen 15. sep. 2026.*

Tallene er **hele vaktas** og filtreres aldri på korps — taket gjelder lista, så et
«satt opp» som bare teller ett korps ville stått ved siden av et tak for alle, og de
to kan ikke sammenlignes.

Men da kan de heller ikke sendes til alle: for en `les` med badge ville summen vært et
**aggregat over skift hun ikke får se**. Det er samme regel statistikkmodulen bruker —
aggregater gir avledet innsyn, og skal gates der dataene bor. `belastning_view` sender
derfor `planlegging: null` til henne, og klienten tegner ingen linje.

**Ingen tom ramme.** Å tegne linja uten tall ville sagt «her er noe du ikke får se»,
som er en dårligere beskjed enn ingen beskjed. Hennes egne timer står i «Mitt korps».

Merk at `skriv_handling` og oppover **ser** alle korps (12. sep. 2026), så for
korps-føreren er summen ikke ny opplysning — hun får linja.

### 15. Planleggeren er en egen fane, og den lager grunnlaget

*André, 15. sep. 2026, etter å ha sett steg 2 på staging:*

> «Litt usikker på om vi har skjønt hverandre. Du har lagt det inn i «planlegging»-fanen.
> Jeg ba om en **planlegger**. Den skal bare admin og leder ha tilgang til. For den
> genererer grunnlaget på alt. Vi skal kunne legge inn skift f.eks. tre firemanns lag fra
> kl. 14–22 og en ambulanse fra 15–03 mens en ambulanse går 8 timer rotasjon. Den skal
> sette opp planen som lager grunnlaget for vaktlisten. Så skal vi kunne fordele vaktene
> og etterhvert spisse de inn slik som vi kan gjøre per i dag.»

**Beslutning 12 var feil, og feilen var min.** Hans opprinnelige melding nevnte generering
først og timetallet sist; dette notatet snudde det, gjorde taket til hovedsaken og
generatoren til «steg 5, i sin enkleste form». Da budsjettlinja kom på staging, lå den i
fanen «Planlegging» — som er noe annet:

| Fane | Spørsmål | Hvem |
|---|---|---|
| **Planlegging** | Hva koster lista dem som står i den? | `les` |
| **Planlegger** | Hva skal lista bestå av? | `kan_lede` |

Budsjettlinja og dagslinja er flyttet til «Planlegger»: «sette inn total timer og jobbe
overordnet» er lederens verktøy, og den som bemanner sitt eget korps har ikke bruk for
vaktas budsjett. Regnestykket (`planleggingstall`, `_dagbolker`, taket på `Vaktliste`) var
uavhengig av flata og fulgte med uendret — det var bare plasseringen som var feil.

### 16. Ressursen er subjektet, skiftvinduene hører til den

Andrés to ambulanser har ulik form, og det er formen som bestemmer datamodellen i
skjemaet:

| Enhet | Oppsett | Blir |
|---|---|---|
| **Haugesund 56** | 2 plasser, fre. 14 → søn. 14, skiftlengde 8 | 6 skift × 2 = 12 plasser, 96 t |
| **Sola 56** | 2 plasser, **to vinduer**: fre. og lør. 15–03 | 2 skift × 2 = 4 plasser, 48 t |
| **Lagene** | 3 ressurser, 4 plasser, fre. 14–22 | 12 plasser, 96 t |

Sola 56 er grunnen. Hennes to vakter er **adskilte** — det er ikke en periode som deles,
og det er ikke to biler. Var raden i skjemaet et skiftvindu framfor en ressurs, hadde hun
blitt «Ambulanse 1» og «Ambulanse 2».

**`skiftlengde` er det ene feltet som skiller de to formene.** Tom betyr ett skift som
dekker vinduet; et tall deler vinduet i bolker rygg mot rygg. Ett felt med to betydninger
er her enklere enn to kontroller som utelukker hverandre.

**Den siste bolken kortes av, den strekkes ikke.** 20 timer i åttetimersskift er 8 + 8 + 4.
Et skift som varer lenger enn vakta er noe ingen har bedt om — og det ville dukket opp som
et brudd på skiftlengdegrensa uten at noen satte det opp.

### 17. «Plasser per skift», ikke «antall folk»

André beskriver Haugesund 56 som «4 stk fordelt på 2 lag som går 8 timer på og 8 timer av».
Modellen trenger **2** — bilen har to seter, og de fire er bemanningspoolen som fyller
tolv skiftplasser over 48 timer.

Feltet heter derfor «plasser per skift», og **regnestykket står under raden**: «2 plasser ×
6 skift = 12 plasser, 96 t». Oversettelsen fra hvordan man snakker om bemanning til hva
modellen lagrer skal være synlig før man trykker, ikke etterpå.

### 18. Planleggeren leser oppsettet tilbake, den husker det ikke

*Tatt 15. sep. 2026, meldt fra staging.*

> «Når en har lagt grunnlag og vil redigere så er det ikke lenger i "planlegger"
> — det må vel gå ann å huske dem og la en redigere der?» (André)

Etter en generering tømte klienten oppsettet, med den begrunnelsen at et andre
trykk ellers ville laget «Lag 4, 5, 6» ved siden av «Lag 1, 2, 3». Begrunnelsen
var riktig; løsningen var feil sted å løse den.

**Å huske kladden er den dårligere av de to formene.** En husket kladd og
virkeligheten glir fra hverandre i det øyeblikket noen retter et skift i
regnearket — og da ville et trykk på «Lag grunnlaget» rullet den rettelsen
tilbake, uten at noen ba om det. Planleggeren leser derfor **hva som står**: én
rad per ressurs, vinduene gruppert på plassenes tider.

Raden bærer `ressurs_id`, og det gjør den til en **redigering** på serveren.
Gruppa og navnet følger ressursen og ikke linja: å flytte en bil til en annen
gruppe eller døpe den om hører hjemme i «Rediger ressurs», der sletting og
enhetskobling alt ligger. Den som er to steder kommer i utakt.

**«Plasser» er vinduets hele bemanning, ikke et påslag.** Står det fire 14–22,
skal det være fire etterpå — også når to av dem har navn på seg. De som står
telles fra, og bare differansen lages. Uten fratrekket ville en ressurs man
redigerte to ganger vokst for hver gang, og tallet i feltet sluttet å bety det
det sier.

**Panelet viser oppsettet, bekreftelsen viser endringen.** To ulike spørsmål, og
to steder å svare på dem: panelet sier hva lista skal *være*, dialogen hva som
*skjer* — hvor mange nye plasser som lages, og hvor mange planlagte som ryddes
bort. Å redigere et vindu fra seks plasser til fire sletter to, og det er det
eneste i hele planleggeren som fjerner noe; da skal det stå i setningen man
leser før man trykker.

---

## 7. Anbefalt rekkefølge

1. ✅ **Løs `overlapp`-punktet i TODO** (beslutning 8) *(gjort 15. sep. 2026)*. Et tak
   som telles feil er verre enn ikke noe tak.
2. ✅ **Budsjettlinja og dagslinja** *(gjort 15. sep. 2026)* — de leser bare det som
   finnes, og gir verdi uten generatoren. Her landet beslutning 2, 5, 7, 9, 12 og 14.
3. ✅ **Taket på `Vaktliste`**, med `kopier_oppsett` (beslutning 6) *(gjort samtidig med
   steg 2)*. Ett nullbart heltallsfelt, ren skjemamigrasjon, satt med **`skriv_leder`**
   (beslutning 13 — skissen sa `skriv_full`).

   *De to ble gjort i samme omgang med vilje: en «budsjettlinje» uten et budsjett er
   halve funksjonen, og taket er ett felt pluss én linje i `kopier_oppsett`. Å dele dem
   ville betydd å bygge linja to ganger.*
4. ✅ **Planleggeren** *(gjort 15. sep. 2026 — flyttet fram fra steg 5)*. Egen fane bak
   `kan_lede`, `services.generer_grunnlag`, `POST …/generer/` med `?forhaandsvis`.
   Beslutning 3, 4, 10, 11, 15, 16 og 17 landet her.

   *Rekkefølgen ble snudd med vilje: notatet hadde generatoren sist, «i sin enkleste
   form». Den er ikke en fotnote til budsjettlinja — den er funksjonen André bestilte,
   og budsjettlinja er et verktøy inne i den.*

   **Fire runder med tilbakemelding fra staging samme dag** formet den ferdig:
   feltene som ikke lot seg fylle ut, «antall» og «skiftlengde» som forvirret,
   knappens plassering, tastaturet i tidsfeltene — og til slutt beslutning 11b og
   18, som gjorde den om fra et engangsskjema til flaten grunnlaget redigeres i.
5. **Bildet av vakta** — kurvene ved siden av hverandre over felles spenn. Står igjen, og
   er verdt å vurdere på nytt nå: verdien var «se hull og topper mens du legger inn», og
   det er først med generatoren på plass at man vet hva man vil se etter.
