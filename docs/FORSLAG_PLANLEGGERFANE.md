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

### 3.3 Midnatt er avgjort ett sted og uavgjort et annet

- **Oversikten og gruppefanene:** et skift hører til **startdagen** (`_dagnokkel()`).
- **Rapportmodulen:** timer **splittes ved midnatt** (`FORSLAG_RAPPORTMODUL.md` §2.2).

Planleggeren teller timer mot et tak. Da er spørsmålet hvilken av de to den følger — og
svaret bør være rapportmodulens, fordi det er *timer* som telles. Men da vil planleggerens
timetall kunne avvike fra tallet i ressursoverskriften, som teller hele skift på startdagen.

**To tall som ser like ut og ikke er det er verre enn ett upresist tall.** Dette må avklares
før noe bygges, og det som velges må stå skrevet ved siden av begge.

### 3.4 Overlapp blåser opp summen, og det er kjent

Målt 14. sep. 2026: skift 12:00–20:00 og 16:00–22:00 på samme person gir `timer = 14,0`,
mens personen var til stede i 10. Punktet står i `TODO.md`.

For planlegging mot et tak er dette ikke lenger harmløst: budsjettet brukes opp av timer
ingen jobber. **`overlapp`-punktet i TODO bør løses før eller sammen med planleggeren**,
ikke etter.

---

## 4. Skisse

Fanen ligger ved siden av «Oversikt» og «Mannskap», og har tre deler:

**1. Budsjettlinja.** «Tak: 400 t · Satt opp: 312 t · Igjen: 88 t». Gult merke når taket
passeres. Taket lagres på `Vaktliste` — det gjelder *denne* vakta, i motsetning til
`Belastningsgrenser`, som er organisasjonens og gjelder alle. Å sette det er `skriv_full`,
som alt annet oppsett på en vaktliste.

**2. Generatoren.** «Legg til N plasser på \<ressurs\>, fra–til, rolle». Oppretter ledige
`Vaktpost`-rader. Ikke noe mer intelligent enn det i første omgang: en generator som
gjetter er en generator man må kontrollere, og da er den ikke raskere enn å skrive radene.

**3. Bildet av vakta.** Bemanningskurven per gruppe, som i dag — men samlet på én flate, så
man ser hvor hullene og toppene er mens man legger inn. Kurven finnes (`mkGruppekurve`);
det nye er å vise flere ved siden av hverandre over samme spenn (`_vaktensSpenn()` sørger
alt for at spennet er felles).

---

## 5. Åpne spørsmål

- [ ] **Hvilken midnattsregel teller planleggerens timer?** (§3.3) Rapportmodulens, sier
      denne skissen — men da må forskjellen mot ressursoverskriftens tall stå skrevet.
- [ ] **Skal generatoren kunne fylle plassene, ikke bare lage dem?** Hvis ja, må den gå
      gjennom `kan_sette_vaktpost()`, og da er den ikke lenger bare `skriv_full`.
- [ ] **Hva skjer med plasser som alt finnes når man genererer på nytt?** Legges det til,
      eller erstattes? Å slette bemannede plasser automatisk er den slags handling som må
      bekreftes to ganger, som sletting av en ressurs.
- [ ] **Teller taket ledige plasser, eller bare bemannede?** Planlegging handler om
      behovet, så ledige bør telle — men da er «forbrukt» ikke det samme som «betalt», og
      rapportmodulen teller det andre.
- [ ] **Skal taket kopieres av `kopier_oppsett` til neste vakt?** Ressursene kopieres,
      personene ikke. Et budsjett ligger nærmere ressursene.
- [ ] **Overlapp-punktet i TODO** (§3.4) — før eller sammen med denne.

---

## 6. Anbefalt rekkefølge

1. **Løs `overlapp`-punktet i TODO først.** Et tak som telles feil er verre enn ikke noe tak.
2. **Avklar midnattsregelen** (§3.3) og skriv den ned begge steder.
3. **Budsjettlinja og bildet av vakta** — de leser bare det som finnes, og gir verdi uten
   generatoren.
4. **Generatoren til slutt**, som den enkleste formen: N plasser, fra–til, rolle. Den kan
   bli smartere senere; den kan ikke bli mindre farlig.
