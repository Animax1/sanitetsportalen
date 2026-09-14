# Forslag: utbedringer i vaktlista

**Skrevet 14. september 2026.** Fire ting kom inn samme dag — én feilretting som er levert,
og tre ønsker fra André som ennå ikke er bygget. Punktvis står ønskene i `TODO.md`; dette
notatet finnes fordi **de henger sammen på måter som ikke synes når de leses hver for seg**,
og fordi rekkefølgen man bygger dem i avgjør om vi ender med én regel eller tre.

Ingenting her er besluttet. Notatet skal gjøre valgene synlige, ikke ta dem.

---

## 1. Levert samme dag: nedtrekket tilbød et umulig valg

Meldt fra staging: `PUT /vaktliste/api/vaktposter/88/ → 400`.

`_fyllValgFor()` listet hele mannskapsregisteret i nedtrekket for en ledig plass, mens
`Vaktpost` har en unik-skranke på `(ressurs, mannskap, fra_tid)`. Serveren svarte riktig;
grensesnittet spurte om noe umulig. `opptattPaaPlassen()` filtrerer nå nedtrekket.

Andre halvdel av meldingen var viktigere: *«Jeg fikk feilen i konsoll på f12, så ingenting i
nettleseren ellers.»* Banneret `#vl-feil` ligger øverst på sida, mens raden som ble avvist
kan stå tretti rader ned i et regneark som ruller. Meldingen ble skrevet der ingen så den.
`rullTilFeil()` bringer den fram.

**Prinsippet som ble gjenopprettet, og som de tre ønskene under skal måles mot:** en knapp
som fører til en vegg er verre enn ingen knapp — og en melding ingen ser er verre enn ingen
melding. Se `CHANGELOG.md`, 14. sep. 2026.

---

## 2. Den viktigste observasjonen: dagen er én regel, ikke to

To av de tre ønskene handler om dagruppering, og de ber om den **på hvert sitt sted**:

| Ønske | Hva som kreves | Hvor |
|---|---|---|
| Snu «Oversikt» | Dag som **ytterste** nivå, ressurs under | Utskriftslista |
| Minimerbare ressurser | Dagoverskrifter **inne i** planleggingstabellen | Gruppefanene |

I dag finnes dagen bare ett sted: `_blokkerMedDager()` i `static/js/vaktliste-tegning.js`,
som setter en dagoverskrift inne i hver ressurs i Oversikt, og bare når vakta har mer enn én
dag. Planleggingstabellen har ingenting — `_posterFor()` gir radene i serverens rekkefølge
(`Vaktpost.Meta.ordering = ['fra_tid', 'mannskap__navn']`), altså sortert, men uten
dagskille.

**Bygges de to hver for seg, får portalen to dagrupperinger som kan komme i utakt.** Det er
samme klasse feil som `reservert_korps()` finnes for å hindre i tilgangsmodellen: leses en
regel to steder, vil ett av stedene før eller siden huske halvparten. Og det er en
*stillegående* utakt — to lister som grupperer dagen ulikt ser begge riktige ut hver for seg.

**Anbefaling: én funksjon, to kallsteder.** `_blokkerMedDager()` generaliseres først, og de
to ønskene bygges på den. Det er også billigere, fordi den ene vanskelige avgjørelsen —
midnatt — da tas én gang.

### Midnatt er den avgjørelsen, og den er allerede i spill to steder

`_dagnokkel(blokk.fra_tid)` filer i dag et skift under **startdagen**. «fre. 20:00 – lør.
04:00» står bare under fredag.

Med dagen som ytterste nivå blir det et reelt valg:

- **Bare startdagen:** den som ser på lørdag morgen ser ikke Kari, selv om hun *er* på vakt
  da. Lista svarer da ikke på spørsmålet den er snudd for å svare på.
- **Begge dager:** Kari står under både fredag og lørdag. Riktigere for «hvem er på vakt
  nå», men samme person telles to ganger hvis noen summerer radene.

**Spenningen mot rapportmodulen må være bevisst.** For *timer* er det avklart at skift
splittes ved midnatt (`docs/FORSLAG_RAPPORTMODUL.md` §2.2 — «fredag 23:59 er fredag, lørdag
00:00 er lørdag»). For *oversikten* er splitting ikke like opplagt: der er spørsmålet hvem
som er til stede, ikke hvor mange timer som skal faktureres. De to kan lande ulikt — men da
skal det stå skrevet hvorfor, ellers leses forskjellen som en feil av den neste som ser den.

---

## 3. De tre ønskene, og hva som skiller dem

Punktlistene står i `TODO.md`. Her er det som ikke kommer fram der: **to av dem er
tegning, én er tilstand på serveren.**

| Ønske | Berører | Kan bygges uavhengig? |
|---|---|---|
| Snu «Oversikt» til dag først | Kun JS-tegning + `@media print` | Etter dagfunksjonen |
| Minimerbare ressurser i gruppefanene | Kun JS-tegning + klienttilstand | Etter dagfunksjonen |
| Fjern «Sett i drift» | Modell, view, audit, e-postutløser | **Ja — deler ingenting med de to** |

### 3.1 Minimerbare ressurser: tilstanden må ligge utenfor markupen

`tegnFaner()` og `mkRessurs()` bygger markupen på nytt ved hvert panelbytte. Det er samme
grunn til at `gateKnapper()` ikke kan gate dem (`CLAUDE.md`: «markup som tegnes på nytt kan
ikke gates av `gateKnapper()`»). Sammenslått/utvidet kan derfor ikke bo i DOM-en.

Presedensen er `erDempet` i `oppdrag-enhet.js`, som husker per enhet. Spørsmålet som må
avgjøres er om tilstanden skal overleve en sidelasting — `localStorage` — eller bare et
panelbytte.

**Det åpne spørsmålet er «alle minimert som standard».** Andrés ordlyd er entydig, så dette
er et spørsmål og ikke en innvending: en vakt med **én** ambulanse gir da et klikk hver gang
for å se det eneste som er der. `_blokkerMedDager()` har presedensen for det motsatte valget
— dagoverskrifter vises bare når vakta faktisk har mer enn én dag, så en endagsvakt ser ut
som før.

### 3.2 Snu «Oversikt»: lesemodellen endrer seg, og begrunnelsen i CLAUDE.md må skrives om

I dag svarer lista på «hvem står på denne bilen, og når». Begrunnelsen står i `CLAUDE.md`:
*«den som leser den står ved bilen og spør hvem er her, og når?»*

Snudd svarer den på **«hvem er på vakt i dag, og hvor»** — spørsmålet den som møter om
morgenen faktisk stiller. Begge er gyldige; det er et valg om hvem lista er for.
**`CLAUDE.md` må oppdateres i samme commit som endringen**, ellers står begrunnelsen der og
beskriver noe annet enn koden.

To ting til som må avklares: om summene per ressurs (`_telling`, `_sumTimer`) beholdes per
dag per ressurs eller forsvinner, og hvordan `@media print` oppfører seg med den nye
strukturen — en dagoverskrift som havner nederst på et ark uten radene under seg er en
utskrift ingen kan bruke.

### 3.3 Fjern «Sett i drift»: knappen gjør fire ting

Problemet den løser er ekte: glemmer noen å trykke, kan ingen stemple møtt ved vaktstart —
altså nøyaktig når det betyr noe, og når alle har mest å gjøre. Innsjekken er stengt fordi
noen glemte en knapp, ikke fordi noen bestemte det.

Men `vaktliste/views.drift_view` gjør fire ting, og alle fire trenger et nytt hjem:

| I dag | Hvis drift utledes |
|---|---|
| `status = DRIFT` | Utledes av om «nå» er innenfor vaktas spenn |
| `satt_i_drift_at` | Blir vaktas starttidspunkt. Uproblematisk |
| **`satt_i_drift_av`** | **Mister mening** — ingen åpner innsjekken lenger |
| **Sender vaktlista på e-post** (`fil.sendes_ved_drift()`) | **Utløseren forsvinner.** Må flyttes til en klokke |

**Utledet er mest i portalens ånd.** Presedensen er `Vaktpost.er_tilstede`: «utledes, aldri
lagres — to kilder til samme sannhet går i utakt første gang noe feiler halvveis». Men
utledningen innfører to kanter som ikke finnes i dag: den som møter 30 minutter før
vaktstart kan ikke stemple, og den som glemte å stemple av kan ikke rette etterpå.

Det peker mot **«automatisk med unntak»** framfor rent utledet: drift følger vakta, men en
overstyring beholdes for vakter som starter sent og for rettelser. Da er `satt_i_drift_av`
fortsatt meningsfull i de tilfellene den brukes, og auditsporet overlever.

E-postutsendingen har allerede et riktig sted å flytte til: `fil.send_planlagte()` og
`vaktliste.middleware.FilutsendingMiddleware`.

---

## 4. Anbefalt rekkefølge

1. **Generaliser dagrupperingen først** (§2), og avgjør midnatt i samme runde. To av tre
   ønsker hviler på den, og bygges de før den, får vi to regler å holde i takt.
2. **Snu «Oversikt»** — bruker dagfunksjonen, og er den minste av de to tegneoppgavene.
   Oppdater `CLAUDE.md` i samme commit.
3. **Minimerbare ressurser** — bruker samme dagfunksjon, pluss klienttilstanden i §3.1.
4. **Drift-automatikken** — kan tas når som helst, også parallelt, siden den ikke deler kode
   med de tre andre. Men den trenger en beslutning om «utledet» versus «automatisk med
   unntak» før noen skriver linje én.

---

## 5. Åpne punkter samlet

Alle står også i `TODO.md`, der arbeidet krysses av. Samlet her for å kunne besvares i én
omgang:

- [ ] **Midnatt i oversikten:** startdagen, eller begge dager? (§2)
- [ ] **Skal dagrupperingen vises på endagsvakter?** `_blokkerMedDager()` sier nei i dag.
- [ ] **Minimert som standard også når gruppa har én ressurs?** (§3.1)
- [ ] **Overlever sammenslått/utvidet en sidelasting?** (§3.1)
- [ ] **Åpnes et sammenslått kort automatisk når man må inn i det** — «Rediger ressurs»?
- [ ] **Beholdes summene per ressurs i snudd Oversikt?** (§3.2)
- [ ] **Drift: utledet, eller automatisk med unntak?** (§3.3)
- [ ] **Hva skjer med `satt_i_drift_av` og auditsporet** hvis drift utledes? Et bevisst
      fravalg, ikke et tap man oppdager senere.
