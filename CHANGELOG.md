# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

---

## 2026-09-16 — «Endret en rolle til hospitant og nå står den øverst»

**Meldt fra staging (André).** Symptomet er ekte, og årsaken er den alfabetiske
sorteringen: «Hospitant» går foran «Lagleder», «Lagsmedlem» og «Sjåfør». Det er nøyaktig
det punkt 6 avskaffer — meldingen kom mens staging fortsatt kjørte `3325c8d`, bygget før
rangeringen. Rettelsen ligger i `55c5fb8`.

**Reprodusert før noe ble sagt**, i stedet for å anta: en omdøping i dagens kode lar
`rekkefolge` stå urørt, og rollen blir der den er.

### Men symptomet fortjente sine egne tester

Det er to måter rangeringen kan velte tilbake til alfabetet, og begge ville sett ut som
nøyaktig denne meldingen:

- **`Meta.ordering` mister `rekkefolge`,** eller får navnet foran den. Testen døper om en
  rolle til noe som sorterer først alfabetisk, og krever at den blir stående.
- **Klienten sorterer selv.** `rollerForGruppe()` *filtrerer* bare, og alt annet i modulen
  sorterer alfabetisk — en `.sort()` lagt til i god tro ville gitt riktig rekkefølge i
  basen og feil på skjermen, uten at én servertest ble rød. Testen kjører funksjonen mot
  serverens faktiske svar.

Tre mutanter, alle røde.

**Endret:** `vaktliste/tests_registre.py` (+2). Ingen kodeendring — rettelsen var alt
pushet.

---

## 2026-09-16 — Pulje 3B: ressursgruppene kan endres, og rollene rangeres

To punkter fra pulje 3. Begge viste seg å være **manglende flate over en mekanisme som
alt virket** — den sorten hull der ingenting feiler, fordi funksjonen bare er uoppnåelig.

### Punkt 4: gruppene

André: «de som er i bruk på vaktlister nå må jo få bli.» Databasen var enig fra før —
`Ressurs.gruppe` er `PROTECT` — så halve svaret sto der. Det som manglet:

- **Redigering i det hele tatt.** Serveren har støttet `PUT` siden gruppene ble en tabell;
  klienten kunne bare opprette og slette. En gruppe kunne altså ikke omdøpes.
- **`er_aktiv` hadde ingen vei inn.** Feltet fantes fra 30. aug. 2026, nedtrekkene
  respekterte det, og ingen skjerm kunne sette det. En gruppe i bruk kunne derfor verken
  slettes eller skjules.
- **`Ressursrolle.gruppe` er `CASCADE`.** En gruppe *uten* ressurser lar seg slette — og
  tok rollene sine med seg **uten et ord**. «Lagleder» og «Sjåfør» er oppsett noen har
  skrevet inn. Funnet ved å lese `on_delete` på begge sidene, ikke ved at noe feilet.
  Nå: 409 med antallet, og `{"confirm": true}` for å fortsette — men bare når det
  *finnes* roller. Et ekstra klikk på en tom gruppe er en vane man slutter å lese, og da
  er bekreftelsen verdiløs den gangen den betyr noe.

De seks seedede gruppene har aldri vært vernet, så «også de seks» krevde ingen endring.

### Punkt 6: rollene rangeres

«Leder øverst, hospitant nederst.» Alfabetisk satte «Hospitant» over «Lagleder», og et
nedtrekk der den vanligste rollen ligger midt i lista koster et blikk hver gang.

**Rangeringen er data, ikke en liste i koden.** Rollene seedes ikke med faste navn — de kom
fra det som fantes ved migrasjon `0007` — så en hardkodet rangering ville truffet noen
installasjoner og ikke andre. Migrasjon `0019` legger til `rekkefolge` og sprer dagens
alfabetiske rekkefølge utover med ti, så ingenting *flytter* seg; den gjør bare rekkefølgen
til noe som kan endres.

**Migrasjonen er skjema først, data etterpå** — den trygge retningen. Regelen om
PostgreSQLs triggerkø gjelder migrasjoner som skriver rader og *deretter* endrer skjema;
her kommer `AddField` først og skrivingen sist, så verken `SET CONSTRAINTS ALL IMMEDIATE`
eller `atomic = False` trengs. Det står i migrasjonens egen docstring.

To detaljer verdt å nevne:

- **«Ny rolle havner sist» ligger i `Ressursrolle.save()`**, ikke i et view. Rollene
  opprettes av den generiske registerfabrikken, som bare kjenner *tekstfelter*
  (`ekstra_felt` gjør `.strip()` på vei inn) — et heltall måtte fått et unntak inni
  fabrikken, og da sto regelen der for alle tre verdimengdene mens bare én har den.
- **Omsorteringen sender hele lista**, ikke «opp» per rad. To kall som krysser hverandre
  bytter to par og etterlater en rekkefølge ingen ba om. Serveren krever **nøyaktig**
  gruppas roller: et delvis sett ville gitt noen rader nye tall og latt resten stå.

### Tolv mutanter, og den ene som «overlevde» var min egen feil

Mutanten for tilgangsporten på gruppene satte `pass` rett etter `def` — som ikke gjør noe
i det hele tatt, siden kroppen fortsetter under. **Felle nummer to i lista over måter en
mutant lyver på**, og den ga et falskt «OK» på nøyaktig den sjekken jeg ville prøve.
Skrevet om til å slå ut selve `if`-en: rød.

Alle tolv røde. Én test måtte skrives om — `test_verdimengdene_sorteres_alfabetisk` var
sann for `Ressursrolle` til i dag, og er nå delt i to: de to andre registrene sorterer
fortsatt alfabetisk, rollen sorterer på rangering med navnet som uavgjort.

**Endret:** `vaktliste/models.py`, `vaktliste/migrations/0019_rollerekkefolge.py` (ny),
`vaktliste/views.py`, `vaktliste/views_registre.py`, `vaktliste/urls.py`,
`static/js/vaktliste-handlinger.js`, `vaktliste/tests_registre.py` (+18),
`vaktliste/tests.py`, `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Pulje 3A: «Oversikt» ble en faktisk oversikt

**André, pulje 3 punkt 2:** «Ressursfanen som heter Oversikt viser mye av det som allerede
er i de respektive ressursfanene. Må være en faktisk oversikt. Derfor nevnte jeg de ordene
som tid, timer, totalt, plasser ledig og besatt.»

### Hva den var, og hva den er

Fanen listet **hver person** med navn, korps, rolle og merknad, gruppert på ressurs under
hver dag — nøyaktig de fire kolonnene man alt hadde lest i gruppefanen. Arket ble langt, og
det svarte ikke på det en oversikt skal svare på.

Nå: én rad per **ressurs per tidsblokk**, med Ressurs, Tid, Timer, Plasser, Besatt, Ledige
og Totalt — og en sumrad per dag. Rader med ledige plasser er dempet merket, fordi en
oversikt leses for å finne hullene.

### Tre regler tabellen bærer

- **`Totalt` bruker `_sumTimer`, ikke `timer × plasser`.** Probono-skift teller null
  (11. sep. 2026: timene går, men de er ikke organisasjonens). Regner man lengden ganger
  antallet, blir totalen et annet tall enn budsjettlinja og enn `belastning_per_person`.
- **Sumraden teller de ledige plassenes timer med.** De er planlagt.
- **Dagen er fortsatt ytterst** (14. sep. 2026), og et skift over midnatt står under
  startdagen. Snuingen overlevde omskrivingen.

### Nitten tester bar den gamle formen — og ble skrevet om, ikke slettet

Det er den tyngste delen av jobben og den viktigste. Hver test beholdt poenget sitt:

| Testen sa | Nå |
|---|---|
| «Oversikten har **ingen** tidskolonne» | «Oversikten **har** tidskolonnen tilbake» — med begrunnelsen for at regelen snudde: kolonnen gjentok seg på hver personrad, nå *er* raden blokken |
| Ressursen er en `<h3>` | Ressursen er en rad, og rekkefølgen er fortsatt gruppas |
| Probono-merket står ved navnet | Probono bæres av `Totalt`; merkelappen prøves der personene bor |
| Ledig plass viser reservert korps | Ledige er et tall; reservasjonen prøves i gruppefanen, så `_plassKorps()` ikke mister sin eneste dekning |
| Mannskapsnavnet escapes | Navnet skal ikke være der **i det hele tatt** — og ressursnavnet, som er der, dekkes av sin egen test |

To av dem tok jeg først feil på, fordi jeg gjettet på fiksturen i stedet for å lese den:
Nina står på samleplassen, ikke på Ambulanse 2, og samleplassen har *to* blokker fredag, så
et samlet radtall sier ingenting om hvilke dager den står under. Begge er nå skrevet mot det
fiksturen faktisk inneholder.

### Ti mutanter, og den ene som overlevde var sumraden

Sumraden lot seg endre til å summere bare de **besatte** timene uten at noe ble rødt — den
var tabellens fasit og helt udekket. Det er nettopp den feilen som ikke ville blitt oppdaget
i bruk: et budsjettall som stille utelater de ledige plassene ser rimelig ut, det er bare
for lavt, og man planlegger etter det.

Etter at testen kom: alle ti røde, inkludert begge de to stedene `ledige` regnes ut (de sto
med identisk kode i rad og sumrad, så mutanten måtte gjøres entydig først — fella «den traff
et annet sted enn du tror»).

**Endret:** `static/js/vaktliste-oversikt.js`, `static/css/vaktliste.css`,
`vaktliste/tests_xss.py` (19 omskrevet, +1), `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Pulje 3A: «Planlegging»-fanen heter «Timeoversikt»

**André, pulje 3 punkt 1:** fanen skal hete «Timeoversikt», og siles på korps for den som
ikke er leder.

### Halve punktet var alt gjort

`belastning_per_person()` kaller `synlige_vaktposter(poster, user)`, og
`KorpsvelgerTests.test_parameteret_er_ingen_dor_for_korps_brukeren` viser at en `les` med
badge bare ser sitt eget korps — også når hun sender `?korps=` for et annet. Silingen var
altså på plass og dekket. Det som gjensto var navnet.

Verdt å si høyt: jeg fant det ved å **lese testen**, ikke bare koden. At kallet står i fila
sier ikke at det virker — det er samme skille som mellom en statisk regel og en
migrasjonsprøve.

### Og navnet var opptatt

`Vaktliste.status` har verdien «Planlegging» ved siden av «I drift», og den står som et
merke øverst på siden. Fanen og merket sa samme ord om to ulike begreper: hva lista *koster
i timer*, og om innsjekk er *åpen*. «Timeoversikt» sier hva fanen viser, og «Planlegging»
betyr nå bare status.

**Et søk-og-erstatt over ordet ville vært feil.** «Planlegging» står i `choices.py` som
statusverdi, i `0002_oppsett` som migrert choice, og i fem tester som `status_navn`. Bare
fanens ene linje skulle endres — samme familie som mutantfella «den traff et annet sted enn
du tror», bare på forhånd.

### Testen manglet, og det var derfor kollisjonen kunne oppstå

Omdøpingen var **grønn før testen ble skrevet**: ingen test sa noe om fanenavnet, så det
kunne vært hva som helst. `FanenHeterTimeoversiktTests` prøver nå **regelen** og ikke ordet
— *et fanenavn kan ikke være en statusetikett* — så en framtidig omdøping som gjeninnfører
kollisjonen blir rød uansett hvilket ord det er.

Fire mutanter, alle røde, deriblant den som tømmer `STATUS_NAVN` så regelen ikke lenger har
noe å måle mot.

### Og en regel som fanget meg innen timen

Punktet ble levert, og jeg **krysset det av** i TODO — i en fil hvis egen topp sier at
ferdige punkter slettes, etter en regel jeg skrev samme formiddag. Testen fanget det ikke,
fordi den bare forbød åpne punkter *under* avkryssede.

Den forbyr nå `[x]` i det hele tatt. Det er den riktige formen på beslutningen — er
historien i CHANGELOG, er et avkrysset punkt en andre kilde — og det er dessuten
forutsetningen for den første regelen: finnes ingen avkryssede foreldre, kan ingenting
begraves under dem.

Vanen sitter i fingrene lenge etter at regelen er bestemt. Det er nøyaktig det tester er
til for, og det er tredje gang på to dager at svaret har vært å gjøre en intensjon til noe
som kan bli rødt.

**Endret:** `static/js/vaktliste-tegning.js`, `vaktliste/tests_belastning.py` (+2),
`core/tests_todo.py` (+1), `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Pulje 2 og de tre rundene etter ut i prod

André: «Kan vi pushe det vi har gjort til main?» Seks commits, `11c068b` → `a7239c5`:

| Bygg | Hva |
|---|---|
| `38f32cc` | Pulje 2, første halvdel — «ledig siden» og varselbjella |
| `031ac97` | Pulje 2, andre halvdel — passiv vakt, «avvente», kvittert avbrytelse |
| `5ef0aa7` | Typeflaggene kan krysses av i «Valglister» |
| `e4369f2` | Puljene skrevet ned, målrettet mutasjonskjøring, delt testsuite |
| `b6f66df` | «[object Object]» på hver enhet — og de tre lagene under |
| `a7239c5` | TODO ryddet, to vakter som holder den ryddig |

**Én migrasjon, `oppdrag/0026`, og den er rene tillegg** — to felter på `Enhetstype`, ett
på `Enhet`, `Oppdragsenhet` og `ArkivertOppdrag`, pluss tabellen `Vaktmodusperiode`. **Null
`RunPython`/`RunSQL`**, så regelen om PostgreSQLs triggerkø er ikke i spill og release-fasen
er trygg. Ingen eksisterende rad endres.

Og funksjonen er **inert til noen slår den på**: passiv vakt og «avvente» krever at flagget
settes på enhetstypen i «Valglister». Gjøres ikke det, oppfører oppdragsmodulen seg nøyaktig
som før deployen. Det er den beste formen en prod-endring kan ha — den kan verifiseres i ro,
og den kan ikke overraske noen som ikke har bedt om den.

Suiten grønn på `a7239c5`: 3 184 tester.

---

## 2026-09-16 — TODO var mer arkiv enn arbeidsliste

**André:** «Hva kan vi gjøre med TODO for å optimalisere?» Målt først, ryddet etterpå.

### Diagnosen

| Funn | Tall |
|---|---|
| Linjer som beskrev **ferdig** arbeid | **1 316 av 2 495 (53 %)** |
| Linjer som beskrev åpent arbeid | 858 |
| Åpne punkter begravd under et avkrysset punkt | **23** |
| — av dem: punkter som ventet på André | **6** |
| Tester som håndhevet noe i TODO | **0** |

Regelen mot begravde punkter sto i `CLAUDE.md` fra 14. sep. 2026, skrevet da det var
**to**. To dager senere var det 23 — og **to av dem la jeg der dagen før**, i en fil jeg
leser hver økt. Prosaen hindret ingenting, fordi ingenting ble rødt. Det er samme lærdom som
avhengighetsretningen: en intensjon er ikke en regel.

De seks som ventet på André er det som gjorde det dyrt. Blant dem verifiseringen av
Scaleway-kortet og staging-lista fra 16. sep. — altså nøyaktig det han var bedt om å gjøre,
plassert der han ikke ser det.

### Avgjørelsen: ferdige punkter slettes

André: «Vi sletter. Du skal jo legge inn hva du gjorde i CHANGELOG, og det som står i TODO
og det som ble gjort kan bli to ting med forskjellig vri. **CHANGELOG blir arkivets
sannhet.**»

Det er den riktige delingen, og den avvikler en dobbeltføring vi ikke hadde lagt merke til:
et TODO-punkt beskriver *hva som skal gjøres*, en CHANGELOG-oppføring *hva som ble gjort og
hvorfor*. Å beholde begge er to kilder som glir fra hverandre.

**2 495 → 869 linjer.** 206 avkryssede blokker slettet.

### De 23 er skrevet om, ikke flyttet

Et begravd barn henter ofte meningen sin fra forelderen som ble avkrysset. «Prøv
gjenopprettingen én gang» sier ingenting uten at man vet at det handler om Scaleway. Hvert
av dem er derfor skrevet om til å stå alene. To forsvant underveis:

- **Ett var utdatert.** «Gjenstår: ut i prod — `main` står på `7435dec`» hadde vært sant til
  superbruker-runden gikk ut. `main` står på `11c068b` og har den. Punktet var både usynlig
  og feil, og det er ingen tilfeldighet at de to henger sammen.
- **To var duplikater** av hverandre — begge ba om verifisering av Scaleway-kortet, fra hver
  sin runde. Slått sammen.

### To vakter, og en presisering av hva «Krever Andre» betyr

`core/tests_todo.py`: ingen åpne punkter under avkryssede, og alt merket «Krever Andre» skal
stå i toppseksjonen.

Den andre regelen tvang fram en avklaring med én gang. Et punkt under datteroppdrag-ideen —
«hva skjer med morens bil når den første datteren lages?» — var merket «Krever Andre», men
blokkerer ingenting: ideen er ikke påbegynt. **«Krever Andre» må bety «blokkerer nå»**,
ellers fylles toppen av fila med ting han ikke kan handle på, og da slutter han å stole på
den. Punktet heter nå «Åpent valg, besvares når ideen tas opp», med begrunnelsen i teksten.

Og som i `core/tests_js_regler.py`: en sperrehake som krever at mønstrene kjenner igjen sin
egen feil. En vakt som ikke kan bli rød, vokter ingenting.

**Endret:** `TODO.md` (2 495 → 869 linjer), `core/tests_todo.py` (ny, 4 tester),
`CLAUDE.md` (sletting framfor avkryssing, og at CHANGELOG skrives for `grep`).

---

## 2026-09-16 — «[object Object]» på hver enhet: én linje, tre lag

**Meldt fra staging (André):** «I /oppdrag i «ressurser»-listen vises enhver enhet med
navnet på enheten og `[object Object]` — på alle enhetene, uavhengig av hva flagget sier.»

### Feilen

```js
<div class="enhet-navn">${escapeHtml(e.navn)}${trustedHtml(passiv)}</div>
```

`trustedHtml()` er **ikke en escaper**. Den returnerer `{__trustedHtml: '…'}`, en merkelapp
`cellHtml()` pakker ut når en Tabulator-celle skal ta imot markup vi har bygget selv. I en
mal-streng blir objektet til `[object Object]`.

Og det forklarer «uavhengig av flagget»: `trustedHtml('')` er et objekt like fullt, så den
*tomme* grenen viste det også. Passivmerket var borte og teksten sto på hvert eneste kort —
altså så feilen ut som noe helt annet enn den var.

Reprodusert i node før noe ble rørt, som fire røde tester.

### Lag 2: ingen test så kortet

`_enhetskort` var ikke i `HTML_BUILDERS_PER_FIL`. Den ble hoistet ut av `renderEnheter` en
gang i fjor, og **lista fulgte ikke med** — fra da av var hvert enhetskort på tavla
uskannet. Åtte andre byggere sto utenfor på samme vis. Ingen av dem hadde uescapet
brukerdata, så ingenting smalt; men skanneren meldte grønt om en dekning den ikke hadde, og
det er verre enn en rød test.

En håndholdt liste forfaller i stillhet. `test_ingen_bygger_staar_utenfor_skanningen`
sammenligner den nå med kilden, så neste utklipping sier fra selv.

### Lag 3: skanneren anbefalte fella

Feilmeldingen sa: «Pakk verdien i escapeHtml() **eller trustedHtml() hvis det er markup du
har bygget selv**». Det er riktig for en Tabulator-celle og galt for en mal-streng, og det
er råd jeg fulgte. Teksten sier nå det motsatte, med grunnen.

Samme felle tok «Rett tid» fra fase 3 til 11. sep. 2026. Advarselen ble den gang skrevet som
en kommentar ved det ene kallstedet — 500 linjer unna, i en annen fil. Fem dager senere gikk
jeg i den samme. **En advarsel som bare finnes der feilen alt er rettet, advarer ingen.**
Regelen står nå i `core/tests_js_regler.py`, der den gjelder alle filene i `static/js/`.

### Ti mutanter — og to overlevde først

- **Å ta escapingen ut av `data-id="${escHtmlValue(meldingId)}"` overlevde.**
  `REVIEWED_INTERPOLATIONS` er nøklet på uttrykkets *tekst*, så `meldingId` godkjent fordi
  den står i en `getElementById`-streng var samtidig godkjent i en ekte attributt.
  Godkjenningen smittet fra en selektor over på markup. Skanneren leser nå bare mal-strenger
  **med en tagg i** (`_markuplitteraler()`) — og da trenger ingen av DOM-id-ene å stå i lista
  i det hele tatt.
- **Å peke regelen mot et navn som ikke finnes overlevde.** `trustedHtml` → `trustedHtmlXX`
  *inne i mønsteret* ga en regel som er grønn for alltid. Navnet står nå ett sted
  (`HJELPER`), begge mønstrene bygges av det, og sperrehaken krever at de slår ut på en
  kjent-dårlig bit kode. **En vakt som ikke kan bli rød, vokter ingenting.**

**Endret:** `static/js/oppdrag-sentral-kjerne.js` (feilen), `-oppdrag.js` (én id escapet),
`-lasting.js` (nøstet mal-streng hoistet ut), `oppdrag/tests_xss.py` (ni byggere inn,
markup-skillet, to nye vakter), `core/tests_js_regler.py` (ny),
`oppdrag/tests_passiv_avvente.py` (+3), `CLAUDE.md`. Suiten: 3 180 grønne på 109 sekunder
med den delte kommandoen.

---

## 2026-09-16 — Puljene skrives ned, og to testregler som koster en time i uka

**André:** «Ligger puljene som vi har planlagt i noe notat? For jeg syns hver arbeid du
gjør tar enormt lang tid.»

Svaret på det første var **nei**, og det er en feil i seg selv. Lista på sytten punkter var
prioritert i fire puljer som bare fantes i samtalen — mens `TODO.md` sier i sin egen topp at
et punkt som ikke står der, ikke blir gjort. Pulje 1 og 2 var levert og krysset av; pulje 3
og 4 ville forsvunnet med sesjonen. Alle fire står nå under «Puljene fra Andrés gjennomgang
16. sep. 2026», med det som gjenstår og de to avklaringene pulje 4 venter på.

### Og så det andre spørsmålet, som var det viktigere

Tidsstemplene på mutasjonsskriptene lot seg lese som en logg, og den forteller dette:

| Hva | Målt |
|---|---|
| `manage.py test oppdrag` | **38 s** |
| `oppdrag.tests_passiv_avvente` (som dekker mutantene) | **5 s** |
| Mutanter kjørt over økta | **~100** |

Nesten alle kjørte **hele appen**. Ett skript alene — 21 mutanter mot `oppdrag` — brukte
tretten minutter på å gi et svar 42 tester kunne gitt på to. Over hundre mutanter er
forskjellen i størrelsesorden **en klokketime**, brukt på å kjøre tester som ikke kunne bli
røde av mutasjonen uansett.

Begrunnelsen jeg hadde for det var fella «mutanten traff et annet sted enn du tror» — som
står i denne fila. Men den fella løses ved å **lese diffen til mutanten**, ikke ved å kjøre
560 urelaterte tester. Regelen står nå i mutasjonsavsnittet.

### Suiten kan deles

190 sekunder serielt, **~106 delt** på fire kjerner. `core` må stå for seg:
`core/tests_backup.py` skriver ekte backupfiler til én mappe og rører det globale
handlerregisteret, så fire arbeidere kolliderer. Feilen kommer ut som «cannot pickle
'traceback' object», som ikke ligner det den er — derfor er den skrevet ned, både i
kommandoblokka og som et punkt.

Og mens jeg målte: **`core/tests_verifiser_backup.py` er 47 sekunder alene** — en firedel av
hele suiten, fordi den starter `migrate` i en underprosess per test. Det er riktig for det
den prøver, og den skal ikke slettes; den er den ene testen som svarer på om *innholdet* i
backupfilene duger. Men prisen betales av hver kjøring, og et tag-skille er ført opp.

**Endret:** `TODO.md` (puljene + to målte punkter), `CLAUDE.md` (målrettet mutasjonskjøring,
delt suite). Ingen kodeendring.

---

## 2026-09-16 — Pulje 2, andre halvdel: passiv vakt, «avvente» og kvittert avbrytelse

Resten av pulje 2 i én runde, etter spesifikasjonen André ga samme dag. Tre ting som
henger sammen, og én migrasjon — `oppdrag/0026`, **rene tillegg, null `RunPython`**, så
release-fasen er trygg.

### Flaggene står på enhetstypen, ikke på enheten

«Kan gå passiv vakt» og «kan avvente» er egenskaper ved *slaget* ressurs — spesialressurser
går bakvakt, ambulanser gjør det ikke — så de er to felter på `Enhetstype`
(`kan_passiv_vakt`, `kan_avvente`). Sto de på hver enhet, måtte de settes på nytt for hver
bil som opprettes, og en glemt avkryssing ville sett ut som en bevisst beslutning.

**To separate flagg, ikke ett.** Å avvente et oppdrag og å sove i bakvakt er to ulike ting,
og en ressurs kan gjøre det ene uten det andre. Ett felles flagg ville koblet dem for alltid
og vært umulig å skille i ettertid uten en datamigrasjon.

### Passiv vakt er ikke «av vakt»

Hun kan varsles, og hun teller i beredskapen — hun holder en 24/7-vakt gjennom hele
arrangementet. Poenget med moduset er å **dokumentere** hvor mange timer og hvor mange
oppdrag som falt i tida hun helst skulle sovet. Derfor er grensesnittet dempet: et merke på
ressurskortet, og `Lege 02 (passiv vakt)` på brikka når hun står på et oppdrag. Er hun
aktiv, står det ingenting ekstra — en merking av det normale er en merking ingen leser.

Svaret ligger to steder, og begge trengs:

- **`Oppdragsenhet.varslet_modus`** — modusen **frosset** i det hun ble varslet. Leste vi
  enhetens `passiv_vakt` når statistikken ble regnet ut, ville et oppdrag hun kjørte i
  passiv vakt hoppet over til «aktiv» i det hun gikk aktiv neste morgen, og dokumentasjonen
  vært verdiløs.
- **`Vaktmodusperiode`** — hvor lenge hun sto slik, inkludert timene ingenting skjedde. Som
  er akkurat de timene man vil dokumentere. `sett_vaktmodus()` lukker den åpne perioden og
  åpner en ny, er idempotent, og en databasesperre (`en_apen_vaktmodus_per_enhet`) holder
  at det aldri finnes to åpne perioder for samme enhet i samme vakt. En åpen periode
  summeres **fram til nå** — ellers viste vakta som pågår null.

### «Avvente» er en beskjed, ikke en status

En varslet spesialressurs kan svare at hun ikke rykker ut nå. Hun **blir stående varslet**
på oppdraget, og operatøren kan trykke «Rykk ut» senere; begge deler står i loggen
(`Enhetshendelse.AVVENTER`). Derfor teller hun **ikke** som «noen er på vei» i
`trenger_ny_ressurs`: står hun avventende alene, skal det stå «trenger ny ressurs» — som er
hele grunnen til at spørsmålet stilles. Det var André sitt svar på spørsmål 2, og det er
den eneste lesningen som gir mening for en ressurs som vanligvis rykker ut som ekstra enhet.

### Avbrutt-merket kvitteres nå

Det forsvant aldri av seg selv, og et merke som blir stående gjennom vakta er et merke man
slutter å se. To veier ut: operatøren trykker «Kvitter» i merket, eller **en ny enhet
varsles** — `varsle_enhet` kvitterer, fordi det å sende noen ny *er* svaret på
avbrytelsen. (`kvittert_at`/`kvittert_av` på `Enhetshendelse`; `avbrutt_av` og
`avbrutt_av_bulk` filtrerer på ukvittert.)

### Arkivet og statistikken

`ArkivertOppdrag.varslet_modus` står i SHA-payloaden **bare når den er satt**, nøyaktig som
`behandlet_at`: rader for enheter uten passiv vakt — de fleste — får samme payload som før,
og eldre signaturer verifiserer uendret. Statistikken har `enheter_passiv`, `passiv_timer`
og `oppdrag_i_passiv`. De to første er live-tall og finnes ikke i arkivet (som
`enheter_pa_vakt`); det tredje overlever arkiveringen, fordi stempelet ligger på radene.

### 21 mutanter — og én av dem var en ekte feil

Alle 21 røde. Én av dem fant en **kodefeil, ikke et testhull**, og det er verdt å skrive
ned hvordan:

> **Broen i `Oppdrag.save()` stemplet ikke modusen.** Den lager den *første* koblingsraden
> for et oppdrag opprettet med `enhet` satt — `varsle_enhet` lager de neste. Uten stempelet
> der talte `oppdrag_i_passiv` bare enheter som ble lagt til *etterpå*, altså aldri det
> vanlige tilfellet. Mutanten «broen stempler ikke modusen» var grønn da jeg skrev den, og
> det var svaret: koden gjorde allerede det mutanten skulle gjøre.

Det er nettopp den sorten feil mutasjonstesting finnes for. Regelen sto riktig ett sted og
manglet i det andre, begge stiene var dekket av tester, og begge testene var grønne — fordi
ingen av dem gikk gjennom den ene inngangen der feltet manglet.

### Og flaggene måtte kunne krysses av

Flaggene sto på `Enhetstype` med riktig standard og riktig lesing, alle 21 mutantene var
røde — og **ingen skjerm kunne sette dem**. En funksjon som bare lar seg skru på fra et
skall er ikke levert; den er skrevet. De ligger nå i «Valglister» → Enhetstyper, gjennom
`Verdimengde.ekstra`, som er den samme mekanismen `kategori` og `med_antall` bruker.

Ni mutanter til på den veien. Åtte røde med det samme; den niende avslørte en assertion jeg
hadde skrevet for løst:

> Testen krevde strengen `data-action="settTypeflagg" data-hendelse="change"` *ett sted* i
> markupen — og den sto i begge nedtrekkene. Fjernet man hendelsen fra det ene, fant
> assertionen den fortsatt i det andre og gikk grønn. Uten hendelsen fyrer handlingen på
> *klikket* som åpner nedtrekket, med den gamle verdien: nøyaktig feilen som gjorde
> vaktlistevelgeren «treg» dagen før.

Rettelsen var å skrive **regelen** i stedet for treffet: hvert `<select>` i en verdirad som
bærer `data-action` må også bære `data-hendelse="change"` og `data-felt`. Den dekker
problemstillingsfeltene på kjøpet, og den neste som legges til.

**Endret:** `oppdrag/models.py` (+`Vaktmodusperiode`, fem felter),
`oppdrag/migrations/0026_…` (rene tillegg), `oppdrag/services.py`, `oppdrag/views.py`,
`oppdrag/views_common.py`, `oppdrag/urls.py` (+3 ruter), `oppdrag/arkiv.py`,
`oppdrag/statistikk.py`, `static/js/oppdrag-sentral-{kjerne,oppdrag,admin}.js`,
`static/css/oppdrag.css`, `oppdrag/views_verdier.py`,
`oppdrag/tests_passiv_avvente.py` (ny, 42 tester), `oppdrag/tests_runde_e.py` (+3),
`oppdrag/tests_xss.py`, `oppdrag/CLAUDE.md`, `docs/TEKNISK_DOKUMENTASJON.md` (rutetallene).
Hele suiten (3 172 tester) grønn.

---

## 2026-09-16 — Pulje 2, første halvdel: «ledig siden» og varselbjella

To av de tre små i oppdragsmodulen. Ingen av dem rører statusmaskinen eller skjemaet;
avbrutt-kvitteringen kommer for seg, fordi den trenger en migrasjon.

### «Ledig siden» i ressursdelen

En ledig enhet har ingen aktiv koblingsrad, så `status_tidspunkt` er tomt og statusen sto
som et ord uten tid. Operatøren som skal sende noen vil vite hvem som har stått lengst.

`services.ledig_siden_bulk()` leser siste **gjeldende** `Ledig`-melding per enhet i denne
vakta. Tre ting er verdt å nevne, og alle tre ble funnet av mutasjonstesting:

- **Korreksjoner teller.** Retter operatøren tidspunktet, er det det rettede som gjelder.
- **Vakta er scope.** Uten filteret ville fjorårets arrangement stått der som om det var
  i dag.
- **Feltet sendes bare når hun faktisk er ledig.** Står hun på et oppdrag, er «ledig siden»
  forrige gang — et tall som ser ut som nåtid og ikke er det.

Klienten viser det gjennom samme uttrykk som alle de andre statusene
(`status_tidspunkt || ledig_siden`), med klokkeslett og tid siden. To måter å vise «siden
når» ville vært én for mye.

### Varselbjella

Nummer, hastegrad og klokkeslett — **ikke problemstillingen**. «Intet mer» er ikke bare
knapphet: varselraden blir stående i 30 dager, og problemstillingen er en helseopplysning.

**Nøkkelen bærer oppdrags-ID-en**, fordi `notify()` dedupliserer på `kind` i 24 timer. Med
en fast verdi ville oppdrag nummer to blitt svelget, og det er nettopp det andre oppdraget
hun trenger å se. Varselet merkes lest når hun rykker ut — ellers hoper bjella seg opp
gjennom vakta, og et ulest-tall som bare vokser er et tall ingen ser på.

Begge kaster aldri: en bil uten bjellerad er et savn, en varsling som velter utrykningen er
en feil. Og begge har `transaction.atomic()` rundt seg — `varsle_enhet` kan kjøre inne i en
transaksjon, og en databasefeil fanget uten savepoint etterlater den ubrukelig.

### Tolv mutanter, og tre overlevde først

Alle tre var testhull, ikke kodefeil — og **to av dem var fikstureringen igjen**:

- **Korreksjonen flyttet tidspunktet framover.** Da vinner den korrigerte raden uansett,
  fordi den er nyest, og testen kunne ikke skille «vi hoppet over den overstyrte» fra «vi
  tok den seneste». Rettelsen flytter nå bakover.
- **Enheten hadde aldri vært ledig** før hun rykket ut, så feltet var tomt uansett hva
  regelen gjorde. Nå kjøres hun gjennom ett oppdrag først, med en sperrehake som krever at
  hun har et tidspunkt å miste.
- **Ingen test hadde en enhet som var ledig i en annen vakt**, så vaktfilteret lot seg
  fjerne.

Det er tredje gang denne uka at «fikstureringen bar ikke prod-formen» er svaret. Regelen
står i `CLAUDE.md`; den fortjener å bli lest før neste test skrives, ikke etter.

**Endret:** `oppdrag/services.py`, `oppdrag/views.py`,
`static/js/oppdrag-sentral-kjerne.js`, `oppdrag/tests_flere_enheter.py` (+19 tester),
`oppdrag/CLAUDE.md`. Ingen migrasjon. Hele suiten (3 127 tester) grønn.

---

## 2026-09-16 — Velgeren var ikke treg, den fyrte på feil hendelse

**Meldt fra staging (André):** «Når jeg skifter vaktliste tar det lang tid før fanene og
vaktene oppdateres. Det er og forvirrende at om jeg er på en vaktliste og går ut av
/vaktliste/, så går jeg tilbake til den som er øverst på listen.»

### Det var ikke treghet — det skjedde ingenting

`<select id="vaktliste-velger" data-action="byttVaktliste">` manglet
`data-hendelse="change"`. Klikkdelegeringen i `portal-utils.js` treffer *alle*
`[data-action]`, mens `change`-lytteren bare treffer dem som oppgir hendelsen sin. To ting
skjedde derfor samtidig:

- **Klikket som åpnet nedtrekket** kalte `byttVaktliste()` med verdien som alt sto der —
  altså en full henting og omtegning av lista man allerede så, hver gang man åpnet
  velgeren. Det er stutteren man kjenner mens man prøver å velge.
- **Selve valget gjorde ingenting.** Lista byttet først ved *neste* klikk på velgeren.

Regelen sto allerede i `CLAUDE.md`, og `klikkSkalKjore()` finnes nettopp for den. Markupen
ble bare skrevet som om den ikke gjorde det — samme sort feil som planleggerfeltene 15.
sep. `VelgerenFyrerPaaEndringTests` skanner nå alle maler: et `<select>` eller `<textarea>`
med `data-action` skal oppgi hendelsen sin. `<input>` er utenfor med vilje — en knapp er et
`<input>` også, og der *er* klikk riktig hendelse. Én synder i dag, og det var denne; de to
andre nedtrekkene hadde det riktig.

### Og sida husker hvilken liste du sto på

`lastVaktlister()` tok `vaktlister[0].id`, hver gang. Nå leser `forsteListe()` den siste
fra `localStorage` og **sjekker den mot lista serveren faktisk sendte** — en vaktliste kan
være slettet, eller tilgangen borte, siden sist, og da er øverst riktig, som første gang.
Uten den sjekken ville sida bedt om en ID serveren svarer 404 på, og stått tom uten å si
hvorfor.

Minnet er **per nettleser, ikke per konto**: det er en bekvemmelighet, ikke en innstilling,
og «Logg ut» sender `Clear-Site-Data`, som rydder den på en delt drifts-PC. Lagringen
kaster i privat modus, så begge kallene står i `try/catch`.

### Sju mutanter, og de to som overlevde var kallstedene

`forsteListe()` og `huskListe()` var prøvd for seg. Det holdt ikke: **begge kallene lot seg
fjerne uten at én test ble rød** — `lastVaktlister()` kunne gå tilbake til `vaktlister[0]`,
og `lastListe()` kunne slutte å lagre. Da husker sida ingenting mens testene bekrefter en
dekning som ikke finnes. Felle nummer tre fra mutasjonsbolken, igjen.

`MinnetBrukesFraDeEkteInngangeneTests` kjører nå de ekte inngangene mot stubbet `apiFetch`
og `localStorage`, og leser hvilken ID oppstarten ba om og hva lastingen lagret. Etter
rettingen: **sju mutanter, ingen overlevende.**

**Og en testfelle til, verdt å kjenne:** `try/catch`-en rundt `localStorage` svelger
`ReferenceError` like villig som en blokkert butikk. `build_harness` klipper ut funksjoner,
ikke konstanter, så `SISTE_LISTE_NOKKEL` fantes ikke i node — og testen falt tilbake på
«øverst» og *så ut* som om funksjonen ikke husket noe, mens den i virkeligheten ikke fant
navnet sitt. Nøkkelen leses nå ut av kilden.

**Endret:** `templates/vaktliste/index.html`, `static/js/vaktliste-kjerne.js`,
`vaktliste/tests_tilgang.py` (+9 tester), `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.
Ingen migrasjon. Hele suiten (3 108 tester) grønn.

---

## 2026-09-16 — Porten gjaldt innsendingen, ikke endringen

**Meldt fra staging (André):** «Kan rapportere bug at de med les alle / skriv eget korps
ikke kan skrive merknad hvis det står ledig plass. Bør de ha tilgang der når det står ledig
plass for å skrive merknad?»

**Ja** — og dagens oppførsel var ikke engang et bevisst nei. Den var en regel som fyrte på
en endring som ikke skjedde.

### Mekanismen

Skiftvinduet sender hele skjemaet, så `mannskap_id` står i kroppen også når ingen har rørt
nedtrekket. På en ledig plass betyr det **`null` over `null`** — og
`kan_sette_vaktpost(..., mannskap=None)` er `skriv_full`, med god grunn: *å la en plass stå
tom* er å sette opp et behov, og korps-føreren bestemmer ikke hvor mange plasser det skal
være.

Regelen er riktig. Den sto bare på feil side av spørsmålet: den sjekket **innsendingen**
framfor **overgangen**. Viewet sammenligner nå `ny_id != vaktpost.mannskap_id` først. **En
skriving som ikke endrer noe, trenger ingen tillatelse til å endre det.**

### Og svaret på spørsmålet er ja

«Mangler sjåfør, ringer rundt» hører hjemme nettopp på en tom plass, og korps-føreren er den
som vet det. Plassen er alt hennes å *fylle* — reservasjonen sier så — og merknaden følger
raden etter gårsdagens avklaring. Da er den hennes å skrive på.

Det hun fortsatt ikke kan: opprette plassen, fjerne den, flytte tidene eller endre hvem den
er satt av til. Hun kan altså **merke et behov, ikke finne på eller fjerne ett.**

### Fire mutanter, tre røde — og den fjerde er ekvivalent

Den fjerde byttet `ny_id != vaktpost.mannskap_id` med `ny_id is not None`, altså «sjekk bare
når noen settes inn». Den overlevde, og **det betyr ingenting**: de to er
oppførselsmessig like her. Forskjellen kan bare oppstå når noen tømmes ut av en rad, og
inngangsporten for en fylt rad er `kan_redigere_mannskap(user, vaktpost.mannskap)` — nøyaktig
det samme uttrykket `egen_staar_der` leser. Slipper hun inn i raden, passerer hun også
`kan_sette_vaktpost`.

Det er felle nummer to fra mutasjonsbolken i `CLAUDE.md`: *den var en no-op*. Ført opp her
framfor å skrives en test rundt — en test som «fanger» en ekvivalent mutant, fanger
ingenting og ser ut som dekning.

**Endret:** `vaktliste/views.py`, `vaktliste/tests_tilgang.py` (+3 tester),
`vaktliste/CLAUDE.md`. Ingen migrasjon. Hele suiten (3 099 tester) grønn.

---

## 2026-09-16 — Et låst felt skal se låst ut, og fortsatt kunne leses

**André:** «De feltene i rediger skift og rediger ressurs som korps-fører ikke kan endre bør
endre farge i feltet til noe som tydeliggjør at den er låst. Fortsatt lesbar.»

Enig — og `disabled` alene gjorde det motsatte av begge deler. Bootstrap demper deaktiverte
felter, nettleseren demper dem én gang til, og **Safari ignorerer `color` på et deaktivert
felt** og leser `-webkit-text-fill-color` i stedet. Resultatet var et felt som verken så
låst ut eller var godt å lese — særlig på iPhone, som er der dette ble meldt begge ganger.

`.vl-laast` gir stiplet kant, dempet flate og **full tekstkontrast tilbake**. Stiplet
framfor en ny farge, av to grunner: fargene i modulen betyr alt noe (gult varsler, grønt er
tilstede), og en strek man ser forskjell på i gråtoner fungerer også for den som ikke
skiller farger.

**Fargen sier at feltet er låst, ikke hvorfor.** En stiplet kant uten forklaring leser som
en feil, så hvert vindu har nå én linje som sier hvem som setter feltene — og den vises av
*samme funksjon* som låser dem. `_laasFelter()` i `vaktliste-kjerne.js` gjør alle tre
tingene: `disabled`, klassen, hintet. Et vindu som husket to av dem ville sett ut som om det
virket.

### Mutasjonstesting: åtte mutanter, og den siste var en test som leste sin egen prosa

Sju bet med én gang. Den åttende — «Safari-regelen fjernet fra stilarket» — overlevde, og
grunnen er verdt å skrive ned: testen krevde `-webkit-text-fill-color` i regelen, og den
strengen står **også i kommentaren** som forklarer hvorfor den trengs. Fjernet man
deklarasjonen, sto prosaen igjen og testen gikk grønn.

Det er en ny variant av «skillet går på hva assertionen påstår»: en regel som leser sin egen
begrunnelse måler at noen har skrevet om kommentaren, ikke at koden gjør det den sier.
Testen stripper nå kommentarer før den søker, og krever deklarasjonen med kolon. Regelen
står i `CLAUDE.md` ved siden av de fem andre mønstrene. Etter rettingen: **åtte mutanter,
ingen overlevende.**

**Endret:** `static/css/vaktliste.css`, `static/js/vaktliste-{kjerne,offline,handlinger}.js`,
`templates/vaktliste/index.html`, `vaktliste/tests_tilgang.py` (+6 tester),
`vaktliste/CLAUDE.md`, `CLAUDE.md`. Ingen migrasjon. Hele suiten (3 096 tester) grønn.

---

## 2026-09-16 — Merknaden følger raden, ikke oppsettet

**André:** «Merknad skal ikke låses for korps-føreren.»

15. sep. låste jeg den sammen med tidene, fordi «det eneste de skal få lov til er å legge
inn folk, rolle» ble lest strengt. Det var feil sted å trekke grensen. **Merknaden er en
beskjed om raden** — «Kommer 17:30», «kjører selv» — og den som setter personen på plassen
er den som vet det. Tidene er vaktas rammer; merknaden er ikke det.

Den følger derfor samme port som person og rolle, `kan_rore_vaktpost`, og hun når bare
radene som er hennes. **`probono` ble stående**, og det er et annet spørsmål: det sier hva
vakta *koster*, og tallet leses av budsjettlinja for hele lista — den som fører sitt eget
korps skal ikke kunne flytte totalen for alle.

Sju tester bar den gamle regelen og er snudd tilbake. At grensen flyttet seg to ganger på
ett døgn står i `services.SKIFT_OPPSETTFELTER` med begge begrunnelsene: hvorfor merknaden
gikk inn, og hvorfor den kom ut. En liste uten den historikken inviterer til at noen
flytter den tredje gang.

### Mutasjonstesting fant et hull merknaden avslørte

Seks mutanter, og **den sjette overlevde**: `const merknad = kanRore` lot seg bytte med
`true` uten at noe ble rødt. Ingen test spurte hva den som *ikke* får røre raden ser — og
svaret hadde da blitt et skrivbart felt som avvises ved lagring, altså nøyaktig feilen
`readOnly`-glippen dagen før handlet om.

Hullet fantes fordi alle testene av regnearket sto på hennes egen rad. Nå tegnes også en rad
som tilhører et annet korps, med en sperrehake ved siden av: er raden uredigerbar av en
annen grunn, måler «ingen felter» ingenting. Etter rettingen: **seks mutanter, ingen
overlevende.**

**Endret:** `vaktliste/services.py`, `static/js/vaktliste-{kjerne,tegning,offline}.js`,
`vaktliste/tests_tilgang.py` (+4 tester, 7 snudd), `vaktliste/CLAUDE.md`. Ingen migrasjon.

---

## 2026-09-16 — En lås som ikke låste, og en navnerett som var stengt

To glipper i gårsdagens tilgangsrunde, meldt fra staging.

### `readOnly` virker ikke på `datetime-local`

**André:** «Når en per skift trykker på rediger, så ser jeg at i det minste på iPhone kan
man trykke på tid/datoen og justere den. Men får ingen tilgang når man prøver å få det
gjennom. Ikke mulighet til å bare ikke la det i det hele tatt få trykke på den?»

Jeg låste tidsfeltene i skiftvinduet med `readOnly`. **Det attributtet har ingen virkning på
`datetime-local`** — HTML-standarden lar `readonly` gjelde felter man taster fritt i, og på
`date`, `time`, `datetime-local`, `color`, `file` og avkryssinger gjør det ingenting.
Velgeren åpnet seg, segmentene lot seg dra, tallet endret seg på skjermen — og ble så
filtrert bort av `bareTillatteFelter()` ved lagring.

**Det er verre enn å ikke kunne røre feltet.** Man tror man har gjort noe, og oppdager
etterpå at man ikke har. En lås som *ser ut* som en lås, men ikke er det, er den dårligste
av de tre tilstandene — dårligere enn et åpent felt og dårligere enn et stengt.

`disabled` er det ene attributtet som virker på alle feltformene, og gjør nøyaktig det som
ble bedt om: feltet lar seg ikke trykke på. Verdien leses fortsatt av JS, så visningen står.

`LaaseneVirkerPaaAlleFeltformeneTests` håndhever regelen for begge vinduene. **Testen leser
attributtet vi setter, ikke nettleserens oppførsel** — den kan ingen enhetstest måle. Det
den håndhever er derfor regelen som følger av den: *på et felt vi låser, bruker vi
`disabled`.*

### Navneretten var stengt av en detalj i «Ny ressurs»

**André:** «Og så må de få endre navn på ressursen, det ble fjernet ser jeg.»

Den ble ikke fjernet — den ble aldri nåbar. Porten sto på `kan_bemanne_ressurs`, altså
ressursens egen reservasjon. Men **«Ny ressurs» spør bare om navn og gruppe**, med den
begrunnelsen at reservasjonen hører til plassen og koblingen til enheten, og begge settes i
«Rediger». En fersk ressurs er derfor **ureservert** — og «Rediger» er lederens.

Resultatet: regelen slapp bare gjennom de bilene lederen alt hadde reservert til korpset, og
knappen var borte akkurat der korps-føreren står. Et hull som ikke slipper noen inn, men som
ser ferdig ut i koden.

`services.kan_gi_nytt_navn()` spør nå om hun kan bemanne ressursen **eller noen av plassene
på den** — samme to nivåer som `reservert_korps()` alltid har hatt: en samleplass kan stå
ureservert og likevel ha fire plasser som er Haugesunds. Navneretten er dermed bredere enn
bemanningsretten på ressursnivå, og det er med vilje. **Den drar ikke oppsettet med seg:**
gruppe, reservasjon, enhetskobling og sletting leser `kan_lede` hver for seg, og en test
krever at hun fortsatt ikke kan reservere ressursen hun nettopp fikk navngi.

**Ni mutanter, alle røde.** Den som er verdt å nevne: «navneretten teller plasser, ikke
korps» — leses regelen som «har ressursen plasser i det hele tatt», er enhver bemannet
ressurs fritt vilt.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-{kjerne,tegning,offline}.js`, `vaktliste/tests_tilgang.py`
(+9 tester), `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`. Ingen migrasjon.

---

## 2026-09-15 — Superbrukeren er én konto, ikke en kategori

**André, etter forrige runde:** «`is_superuser` skal ikke kunne demotes fra sin
`role = admin`, siden is superuser er og skal være eksklusivt til bootstrap-kontoen.»

Sperren mot degradering kom noen timer tidligere, men den var lagt i viewet alene — og
kravet er strengere enn det. **«Eksklusivt til bootstrap-kontoen» er en invariant, ikke en
sperre på ett endepunkt.** Tre hull sto igjen, og de er ulike:

| Hull | Hva som sto galt |
|---|---|
| Nedtrekket lot seg velge i | Skjemaet tegnet «Bruker» som et gyldig valg på superbrukeren, og viewet avviste innsendingen etterpå. Det er en kontroll som fører til en vegg — regelen fra CLAUDE.md, brutt av rettelsen på forrige punkt |
| `create_admin` laget superbruker nummer to | Kommandoen er idempotent på *brukernavn*. Kjørt med et nytt navn laget den én superbruker til, og da verner sperrene mot degradering og sletting en nødutgang det finnes flere av — altså ingenting |
| Ingenting stoppet en ny kodesti | Sperrene lå i skjemaet og i viewet. `bruker.role = 'bruker'` i et framtidig endepunkt går utenom begge, uten at én test blir rød |

**Rollen låses nå med Djangos `disabled`**, som gjør to ting i én: feltet tegnes grått, og
innsendt verdi forkastes til fordel for instansens. `_kan_degraderes()` og `_kan_slettes()`
står igjen som andre lag — forsvinner låsen, skal noe fortsatt stoppe det.

**`create_admin` avviser en superbruker til**, og sier hvem som har plassen. Den er fortsatt
idempotent på samme brukernavn: blir andre kjøring en feil, knekker den deployen den skulle
hjelpe. Sperra leser `is_superuser`, ikke `role` — leste den rollen, kunne bootstrap aldri
kjørt på en portal som alt hadde en administrator.

**Og `RollenSettesBareGjennomSkjemaeneTests` leter etter nye veier** i stedet for å vedlikeholde
en liste noen må huske. Den går gjennom kodebasen med AST og krever at ingen skriver `.role`
direkte; i dag finnes ingen slik skriving, og unntakslista er tom. Det er den samme sorten
regel som vakten mot `loaddata`: den som kommer til å bryte invarianten neste gang, har ikke
lest denne changeloggen.

**Sju mutanter, alle røde** — blant dem «en ny kodesti skriver `role` direkte», som er den
eneste av dem som beskriver en feil ingen har gjort ennå.

**Endret:** `accounts/forms.py`, `accounts/management/commands/create_admin.py`,
`accounts/tests_sikkerhet_runde1.py` (+10 tester), `CLAUDE.md`. Ingen migrasjon.
Hele suiten (3 077 tester) grønn.

**NB — dette ligger på `rollemodell`, ikke på `main`.** Prod (`7435dec`) har ingen av de to
rundene, og der kan en administrator fortsatt degradere superbrukeren.

---

## 2026-09-15 — Superbrukeren er nødutgangen, og Scaleway-kortet løy

To korte punkter fra samme runde som vaktliste-porten over.

### `is_superuser` kan ikke fratas admin-rollen

**André:** «`is_superuser` må være immun mot å bli nedgradert fra administrator. Ser at når
noen blir gjort administrator så blir de ikke gjort til `is_superuser`, som er slik det skal
være.»

Observasjonen er riktig, og den er verdt å skrive ned: **`is_superuser` og `is_staff` betyr
ingenting for portalen.** De gater `/django-admin/`, som er rutet av i produksjon (S1).
Portaltilgang er `role == 'admin'` og `ModulTilgang`. Flaggene settes bare av
`manage.py create_admin`, og skal ikke følge med når noen forfremmes.

Nettopp derfor er kontoen noe annet enn «en administrator til»: den er den ene man kommer
tilbake inn med. **Og «siste admin»-sperra dekket den ikke** — er det tre administratorer,
kunne superbrukeren degraderes uten at noe protesterte, og da var nødutgangen borte mens
portalen så helt normal ut.

`_kan_degraderes()` sperrer nå på `target.is_superuser`. **Og `_kan_slettes()` gjør det
samme,** selv om det ikke sto i bestillingen: en regel som sperrer degradering, men slipper
sletting, verner ingenting — sletting tar kontoen og ikke bare rollen, og er i tillegg
endelig. **Frysing står igjen med vilje.** Grensen går ved om handlingen lar seg reversere,
og «Tø konto» står ved siden av.

Fire mutanter, alle røde — blant dem «sperra treffer alle admins», som ville gjort hver
administrator udegraderbar. Den retningen er like gal, bare stillere.

### Scaleway-kortet meldte avvik som ikke fantes

**André:** «Bug med lifecycle-tilbakemeldingen fra Scaleway. Permissions skal være korrekt,
er feilen i koden?»

Ja, i hvert fall delvis. `_les_livssyklus()` leste prefikset fra `Filter.Prefix` og det
gamle `Prefix` på toppnivå — men **ikke fra `Filter.And.Prefix`**, som er formen S3 sender
når en regel kombinerer prefiks med en tag eller en størrelsesgrense. Da leste vi tomt
prefiks, og `_avvik()` meldte «ingen livssyklusregel for `backups/` — filene der blir
liggende for alltid» om en regel som sto helt riktig i bucketen.

**Det er den verste sorten feilmelding:** den peker på en ekte fare, på et tidspunkt der
faren ikke finnes, og lærer den som leser den å overse kortet. De tre formene leses nå av
`_prefiks()`, med en sperrehake som krever at «ingen prefiks» fortsatt er et avvik — leses
det som «treffer alt», ville enhver regel sett riktig ut og kortet sluttet å måle noe.

**Og feilteksten sier nå hva Scaleway faktisk svarte.** Den sa «nøkkelen mangler
ObjectStorageBucketsRead» uansett hvilken kode som kom tilbake, og da er en riktig satt
nøkkel og en feil i vår egen kode umulig å skille fra hverandre — begge ser ut som et
rettighetsproblem, og man leter på feil sted. Koden og meldinga står nå i teksten, vasket
for nøkler.

**Er det fortsatt galt på staging, er det nå mulig å se hvorfor** — kortet sier koden.

**Én test ble degenerert underveis, og det er verdt å merke seg:** vaskingen prøves mot
klassens fikstur, der `secret_key` er `'b'`. Da består testen — eller feiler — på om
bokstaven «b» tilfeldigvis står i feilteksten («Object»), ikke på om vaskingen virker. Den
har nå en realistisk nøkkel. En sannhet om ett tegn er ikke en sannhet om en nøkkel.

**Endret:** `accounts/views.py`, `core/offsite.py`,
`accounts/tests_sikkerhet_runde1.py` (+6 tester), `core/tests_offsite.py` (+5 tester),
`CLAUDE.md`. Ingen migrasjon. Hele suiten (3 067 tester) grønn.

---

## 2026-09-15 — Korps-føreren bemanner, hun setter ikke opp

**Meldt fra staging (André):**

> «På /vaktliste/ så kan skrive: eget korps, ser alle — opprette vakter og redigere tider.
> Det må de ikke få lov til. Det eneste de skal få lov til er å legge inn folk, rolle, og
> redigere ressursens navn, men ikke gruppe, reservering, enhet i oppdragsmodulen og
> sletting.»

### Hullet sto i dokumentasjonen som lukket

`CLAUDE.md` sa det allerede: «å *opprette* en ledig plass er `skriv_full`, å *fylle* den
krever badge og reservasjon». Koden sjekket bare badgen. `vaktposter_view` gikk rett på
`kan_sette_vaktpost()`, så `skriv_handling` kunne opprette skift med frie tidspunkt — og
med `antall` inntil femti tomme plasser — på hver ressurs reservert til korpset hennes.
`vaktpost_detalj_view` hadde egne `if`-er for `korps_id` og `alle_korps`, mens
`fra_tid`/`til_tid`, `merknad` og `probono` gikk rett gjennom.

**Det er den typen hull som overlever lengst:** ingen får en feilmelding, dokumentasjonen
leser riktig, og regelen står tre steder som hver dekker sin del av den.

### Regelen er to lister, ikke en `if` per felt

| Nytt | Hva det er |
|---|---|
| `services.SKIFT_OPPSETTFELTER` | `fra_tid`, `til_tid`, `korps_id`, `alle_korps`, `probono`, `merknad`, `antall` |
| `services.RESSURS_OPPSETTFELTER` | `gruppe_id`, `korps_id`, `enhet_id`, `rekkefolge` — **navnet står bevisst ikke der** |
| `services.oppsettfelter(data, felter)` | Hvilke av dem står i kroppen |
| `services.kan_sette_opp_skift(user)` | Kall videre til `kan_skrive_alt`, som `kan_stemple`. Beslutningen skal ha et sted |

Listene er konstanter fordi de har **to lesere hver** — opprettelsen og redigeringen av et
skift, PUT og DELETE på en ressurs. Med en `if` per felt i hvert view ville det ene før
eller siden husket tidene og glemt `probono`; det var akkurat det som hadde skjedd.

**`ressurs_detalj_view` har nå to terskler i ett endepunkt:** navnet krever badge og
reservasjon, alt annet krever `kan_lede`. Bilen heter «Sola 56», ikke «Ambulanse 2», og den
som står ved bilen er den som vet det — mens gruppe, reservasjon og enhetskobling er
beslutninger om *hvem ressursen er til for*, og de flytter tilgangen til seg selv.

**Sletting av et skift ble strengere, også for fylte rader.** Sperren sto bare på de ledige,
fordi et hull i bemanningen ikke skal kunne skjules ved å slette raden som viste det. Det
argumentet gjelder ordrett på en fylt rad: sletter korps-føreren skiftet framfor å melde
forfall, forsvinner plassen og ikke bare personen. Hun tømmer raden i stedet, og da står
behovet.

### Klienten måtte siles, ikke bare gates

**Ett felt hun ikke får sette, velter hele forespørselen** — med vilje, så en halvlagret rad
ikke finnes. Vinduene sendte alltid alle feltene, så uten siling ville et personbytte hun
har lov til gitt 403. `bareTillatteFelter()` i `vaktliste-kjerne.js` siler før sending, med
listene speilet fra `services` og holdt like av `SkiftetsOppsettfelterTests`.

Og markupen måtte si det samme: «Opprett vakt» og tidsfeltene i regnearket sto på
`kanBemanne()` — badgen — så de førte til en vegg. **Tidene vises fortsatt, som tekst:** et
felt man kan skrive i og ikke lagre er verre enn en tekst, for det ser ut som om endringen
gikk igjennom.

### Seks tester sa det gamle, og ble skrevet om framfor slettet

Policyen endret seg, så testene som håndhevet den var ikke feil — de var utdaterte. Hver
enkelt er snudd og har beholdt sitt poeng: `test_korpsbruker_bemanner_sin_egen_ressurs` ble
`test_korpsbruker_oppretter_ikke_skift_men_fyller_dem`, med begge halvdelene i samme test,
fordi hver for seg leser de som om hun enten har alt eller ingenting.

### Mutasjonstesting: 28 mutanter, og fire overlevde først

Etter regelen fra i dag: tungt lag, så hver gren og hver sperre. Seksten på serveren, alle
røde med én gang. Tolv på klienten, der fire overlevde — og alle fire var kjente feller fra
bolken vi skrev noen timer tidligere:

- **To var fikstureringens feil.** Testraden manglet `korps_id`, og `kanRoreRad()` leser
  personens korps på en fylt rad. Raden var altså uredigerbar av en helt annen grunn enn
  den testen målte, og cellene ble tegnet som tekst uansett hva mutanten gjorde. En
  sperrehake står nå ved siden av og krever at raden faktisk *er* hennes.
- **To var kallstedet, ikke funksjonen.** `bareTillatteFelter()` var prøvd for seg, så
  kallet lot seg fjerne fra begge lagrefunksjonene uten at noe ble rødt — altså nøyaktig
  feilen silingen fantes for. `VinduetSenderBareDetHunFaarSetteTests` kjører nå
  `lagreVaktpost()` og `lagreRessurs()` mot en stubbet DOM og leser hva som faktisk ble
  lagt i forespørselen.

Etter rettingene: **28 mutanter, ingen overlevende.**

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-{kjerne,tegning,handlinger,offline}.js`,
`templates/vaktliste/index.html`, `vaktliste/tests_tilgang.py` (+25 tester),
`vaktliste/tests_belastning.py`, `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.
Ingen migrasjon. Hele suiten (3 057 tester) grønn.

---

## 2026-09-15 — CLAUDE.md delt, og mutasjonstestingen har fått et budsjett

**Bedt om (André), to punkter fra forrige økt:** «CLAUDE.md skal splittes i rot +
per-modul-filer» og «hold mutasjonstesting proporsjonal — tungt på services, lett på UI».

### 1. Fila var blitt en modulhåndbok med et rammeverk foran

1 433 linjer, og 651 av dem — nær halvparten — gjaldt én modul om gangen: vaktlista
alene 489, oppdrag 105, statistikk 44. Alt sammen ble lest inn hver gang, også når arbeidet gjaldt en
skrivefeil i `accounts/`.

| Fil | Linjer | Innhold |
|---|---|---|
| `CLAUDE.md` | 1 433 → 859 | Arbeidsflyt, rammeverk, tilgangsmodell, backup, arkiv, audit, frontend, migrasjoner, drift |
| `patients/CLAUDE.md` | 17 | API-mønsteret og viewdelingen |
| `oppdrag/CLAUDE.md` | 109 | Statusmaskinen, verdimengdene, bilens utganger |
| `vaktliste/CLAUDE.md` | 493 | Korps, skift, drift, planleggeren, offline |
| `statistikk/CLAUDE.md` | 48 | Kilderegisteret og de to gatene |

**Regelen for hva som står hvor følger koden:** ligger den i `core/` eller gjelder den
alle, står den i rota; ligger den i en app, står den i appens fil. Teksten er flyttet
ordrett — dette er en deling, ikke en omskriving.

**Det som *må* vites før man rører en modul, ble værende i rota.** Modulfilene lastes når
noen arbeider i mappa, ikke alltid, så avhengighetsretningen, tilgangsnivåene og «hvert
view under en modul skal være dekorert» kan ikke bo hos modulen. Avhengighetsavsnittet har
derfor fått ett nytt avsnitt: at modul-til-modul går én vei, at `oppdrag` ikke importerer
vaktlista, og at statistikkappen ikke navngir noen kilde — med detaljene hos modulene.

### Den farligste feilen var stille, og den er det testen er til for

`core/tests_dokumentråte.py` leser en liste over dokumenter og kontrollerer at hver filsti,
hver `manage.py`-kommando og hvert slettet symbol i dem fortsatt stemmer. Lista inneholdt
`CLAUDE.md`. **I det øyeblikket nær halvparten av innholdet flyttet ut, ville kontrollen
stilltiende ha sluttet å gjelde for dem** — og det er nettopp modulbeskrivelsene som råtner
fortest, fordi de nevner flest navn. Modulfilene står nå i `DOKUMENTER`.

`core/tests_claude_md.py` (ny) håndhever de tre feilene delingen gjør mulige, etter samme
mønster som `core/tests_js_splitt.py` gjorde for JS-delingen:

| Regel | Hva den fanger |
|---|---|
| Hver `*/CLAUDE.md` står i `DOKUMENTER` | At en ny modulfil slipper unna dokumentråte-kontrollen |
| Tabellen «Hvor dokumentasjonen bor» og filene på disk stemmer begge veier | En modulfil ingen peker på, og en rad som peker på ingenting |
| Ingen modul med egen fil har et avsnitt i rota | At avsnittet vokser tilbake, og regelen finnes to steder |
| Rota under 1 000 linjer | Røykvarsler for at delingen opphever seg selv |

**Fem mutasjoner prøvd, alle røde** — men den femte overlevde først, og på en måte som er
verdt å skrive ned: jeg hadde endret ingressen i `vaktliste/CLAUDE.md` uten å fjerne ordet
regelen faktisk ser etter. Mutanten traff ikke regelen, og et «OK» fra den ville ha
bekreftet en dekning som ikke fantes. Rettet mutant: rød.

**Grensen testen ikke ser:** at fila er delt, ikke at innholdet står riktig sted. En
vaktlisteregel skrevet i rota fanges bare hvis den får en overskrift med `(vaktliste/)` i.
Det er samme grense som resten av dokumentverktøyet har — tall og navn lar seg måle, mening
ikke.

### 2. Mutasjonstesting: budsjettet følger hva en overlevende mutant koster

Anledningen var tretten mutanter på et `datetime-local`-felt og to på en tilgangsport.
Regelen står nå i `CLAUDE.md`, som en stige fra tungt til ingenting: tjenestelaget og
rammeverket (tilgang, arkiv, backup, offsite, migrasjoner) tungt, views og de
JS-funksjonene som *avgjør* noe — `avgjor()`, `kanBemannePlass()`, `lydSkalSpille()`,
`klikkSkalKjore()` — middels, byggere og tegning lett, CSS og tekst ingenting.
**Målestokken er hva brukeren ville sett:** ser hun feilen med det samme, holder én mutant
på regelen som avgjør; ser hun den aldri, hører innsatsen hjemme der.

Med regelen følger **de tre måtene en mutant lyver på**, alle tre sett i dette prosjektet
og alle tre spredt i eldre CHANGELOG-oppføringer der ingen leter: at søk-og-erstatt traff
et annet sted enn du tror, at mutanten var en no-op, og at testen kaller hjelperen selv så
kallstedet kan fjernes. Pluss den fjerde, som ikke er mutantens feil — at fikstureringen
ikke bar prod-formen, slik `_dagbolker()` overlevde fordi testskiftene sto i norsk tid og
ORM-en gir UTC.

**Endret:** `CLAUDE.md`, `patients/CLAUDE.md`, `oppdrag/CLAUDE.md`, `vaktliste/CLAUDE.md`,
`statistikk/CLAUDE.md` (alle fire nye), `core/tests_claude_md.py` (ny, 6 tester),
`core/tests_dokumentråte.py`, `README.md`, `TODO.md`. Ingen kodeendring — hele suiten
(3 024 tester) grønn.

---

## 2026-09-15 — «Ny vaktliste»: tidsfeltene som i planleggeren

**Bedt om (André):**

> «Etterpå når det er i orden så vil jeg ha lik tidsfelt som vi har i planleggeren når en
> skal lage ny vaktliste. Der er det mismatch og den i ny vaktliste er litt knotete.»

**`type` og `step` var like fra før** — begge er `datetime-local` med `step="300"`. Det som
manglet, var alt det andre som gjør planleggerens felter behagelige. Et tomt
`datetime-local` må tastes inn segment for segment uten noe å nudge på, og det er det
«knotete» betyr.

| Regel | Hvorfor |
|---|---|
| **Feltene står aldri tomme** | `apneNyVaktliste()` fyller dem ut *før* vinduet vises. Derfor åpnes vinduet nå av JS og ikke av `data-bs-toggle`: et skjema som fyller seg selv etter at man ser det, ser ut som om noe rettet det man skrev |
| **Starten settes til neste hele time** | `new Date()` gir 21:37, og med `step="300"` er nærmeste lovlige verdi 21:35 — et tall ingen har ment. Planleggeren slipper spørsmålet fordi den har vaktas start å bygge på; her *er* feltet vaktas start |
| **Slutten følger starten, til noen rører den** | Samme idé som at et nytt skiftvindu begynner der det forrige sluttet. Har du skrevet «søndag 14:00», skal en rettelse av startdatoen ikke dra sluttiden med seg — da hadde feltet spist det du nettopp skrev. Et tomt sluttfelt teller ikke som rørt |
| **Spennet leses tilbake under feltene** | «Vakten varer 2 d 6 t.» Som tallet under et skiftvindu i planleggeren, og den ene tilbakemeldingen som fanger den vanligste tastefeilen her: riktig klokkeslett på feil dato |

`_varighetstekst()` skriver «2 d 6 t», ikke «54 t»: planleggeren skriver bare timer fordi
et skift er kort nok til at tallet leses, men en vakt går over dager, og et tosifret
timetall sier ikke om man traff riktig dato. Hele døgn skrives uten timerest — «2 d 0 t»
leser som om noe mangler.

Et bakvendt spenn merkes **gult, ikke rødt**, som et ugyldig skiftvindu: serveren avviser
det uansett (`opprett_planlagt_vakt` hadde regelen fra før), så dette er en beskjed om at
man ikke er ferdig.

**Mutasjonsprøvd** — tretten mutanter på de fire reglene.

**Endret:** `static/js/vaktliste-handlinger.js`, `templates/vaktliste/index.html`,
`vaktliste/tests_xss.py` (+17 tester), `vaktliste/tests_tilgang.py`, `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: budsjettet manglet, og oppsettet ble glemt

**Meldt fra staging (André):**

> «1. tak på vaktene og timene er ikke synlige når du oppretter ny vaktliste og går inn i
> planlegger.
> 2. når en har lagt grunnlag og vil redigere så er det ikke lenger i "planlegger" det må
> vel gå ann å huske dem og la en redigere der?»

### 1. Budsjettlinja ble aldri hentet

`mkBudsjett()` gir tom streng uten `belastning`, og `visFane()` hentet den bare for
belastningsfanen. Planleggeren sto utenfor regelen, så taket og timene var **usynlige
nettopp der de skal styre arbeidet** — og synlige bare i fanen som rapporterer i etterkant.
Ingenting feilet; linja bare manglet.

Regelen står nå som **én funksjon**, `faneTrengerBelastning(id)`, fordi den har to lesere:
fanevalget i `visFane()` og korpsvelgeren i `velgKorps()`, som nullstiller tallene og
henter dem på nytt.

### 2. Planleggeren leser oppsettet tilbake fra vaktlista

Etter en generering tømte klienten `planleggerlinjer`, med den begrunnelsen at et andre
trykk ellers ville laget «Lag 4, 5, 6» ved siden av «Lag 1, 2, 3». Begrunnelsen var riktig;
løsningen var feil sted å løse den.

**Planleggeren husker ikke det du skrev — den leser hva som står.** Det er en viktigere
forskjell enn den ser ut: en husket kladd og virkeligheten glir fra hverandre i det
øyeblikket noen retter et skift i regnearket, og da ville et trykk på «Lag grunnlaget»
rullet den rettelsen tilbake.

| Nytt | Hva det gjør |
|---|---|
| `planleggerLesTilbake()` | Én rad per ressurs, vinduene gruppert på plassenes tider. Seks plasser 14–22 leses tilbake som ett vindu med seks |
| `planleggerSikreLinjer()` | Står det ingenting i oppsettet, leses det tilbake. Har du skrevet noe, røres det ikke |
| `linje.ressurs_id` | Gjør raden til en **redigering** på serveren |
| `services._beholdt_og_kladd()` | Ressursens plasser delt i to: de som står, og kladden som lages på nytt |
| `services._nye_plasser()` | Hvor mange hvert vindu faktisk oppretter |

**«Plasser» er vinduets hele bemanning, ikke et påslag.** Står det fire 14–22, skal det
være fire etterpå — også når to av dem har navn på seg. De som står telles fra, og bare
differansen lages. Uten fratrekket ville en ressurs man redigerte to ganger vokst for hver
gang, og tallet i feltet sluttet å bety det det sier. Beholdningen forbrukes **per vindu**,
ellers ville to like vinduer i samme rad begge trukket fra de samme plassene.

**Gruppa og navnet følger ressursen, ikke linja.** Raden som står viser navnet der
nedtrekket ellers står, og knappen heter «Ta ut» — å fjerne en ressurs er en sletting, og
den ligger bak de to bekreftelsene i «Rediger ressurs».

**`erstatt_kladd` er fjernet.** Bryteren ryddet kladd på hele lista, også på ressurser
oppsettet ikke nevnte. Nå er raden som peker på ressursen den eneste som rører den, og en
ressurs utenfor oppsettet lar generatoren være i fred.

**Bekreftelsen viser endringen, panelet viser oppsettet.** Sammendraget teller bare nye
ressurser og nye plasser, og har fått `fjernes` ved siden: å redigere et vindu fra seks
plasser til fire sletter to, og det er det eneste i hele planleggeren som fjerner noe.

### Mutasjonsprøvd

Atten mutanter. Den ene som overlevde første runde er verdt å merke seg: testene kalte
`planleggerSikreLinjer()` selv, så `tegnPanel()` kunne slutte å kalle den uten at noe ble
rødt — altså nøyaktig feilen André meldte. `PlanleggerenTegnesMedOppsettetTests` tegner nå
panelet med den ekte `tegnPanel()`.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-kjerne.js`, `-tegning.js`, `-oversikt.js`, `-handlinger.js`,
`templates/vaktliste/index.html`, `static/css/vaktliste.css`,
`vaktliste/tests_planlegger.py`, `vaktliste/tests_xss.py`, `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: tidsfeltene lot seg ikke skrive i

**Meldt fra staging (André):**

> «Her er det frustrerende vanskelig å redigere med tastatur på tidsrom, jeg kan bare ta
> inn ett tall om gangen.»

Årsaken var min egen: hver `change` kalte `tegnPanel()`, som bygger hele panelet på nytt
med `innerHTML`. Da **erstattes feltet man står i**, og fokus og markør forsvinner med det.
`datetime-local` melder `change` per segment, så feltet forsvant etter hvert tall man skrev.

### Regelen som mangler

**Feltendringer oppdaterer tallene på plass; strukturendringer tegner på nytt.**

`planleggerTegnTall()` setter `textContent` på `[data-vindutall]`, `[data-linjetall]` og
`[data-plantall]` — tallet under vinduet, regnestykket under raden, og totalen nederst.
Advarselen for et bakvendt tidsrom settes med `classList.toggle`, ikke med ny markup.

**Gruppevalget er unntaket** og tegner fortsatt på nytt: «Antall» finnes ikke for grupper i
ett eksemplar, så raden skifter form — og et nedtrekk er man ferdig med når man har valgt,
så omtegningen koster ingen markør.

Teksten under vinduet bygges av `_vindutallTekst()`, som er **ren tekst uten markup**:
samme funksjon brukes av byggeren og av oppdateringen, så de to formene ikke kan komme i
utakt.

### Mutasjonsprøvd

Fem mutanter, og den ene som overlevde er verdt å merke seg: testen min sjekket bare
*totalen*, så et vindutall som frøs gikk grønn. Den måler nå alle tre nivåene, og at
advarselsklassen faktisk settes.

**Endret:** `static/js/vaktliste-oversikt.js`, `static/js/vaktliste-handlinger.js`,
`vaktliste/tests_xss.py` (+4 tester), `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: «Legg til ressurs» flyttet ned

**Meldt fra staging (André):**

> «Legg til ressurs bør ligge mellom sist opprettet ressurs og lag grunnlag for
> forståelsen skyld. For nå er det lett å tro at man bare lager en ressurs og så er man
> ferdig.»

Knappen sto i hodet, over radene. Der leser den som **«start her»** — og har du laget den
ene raden, er det neste du ser generer-knappen. Mellom radene og «Lag grunnlaget» leser den
som **«legg til én til»**, og rekkefølgen i panelet blir den man arbeider i: sett opp, legg
til flere, lag grunnlaget.

Den står også når oppsettet er tomt; ellers kommer man aldri i gang.

Tre mutanter prøvd: knappen tilbake i hodet, knappen etter generer-knappen, og knappen
borte på et tomt oppsett. Alle fanges — plasseringen er en regel nå, ikke en tilfeldighet i
markupen.

**Endret:** `static/js/vaktliste-oversikt.js`, `static/css/vaktliste.css`,
`vaktliste/tests_xss.py` (+2 tester), `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: plassene flyttet til vinduet, skiftlengde fjernet

**Meldt fra staging (André):**

> «Fungerte veldig fint for ressurser som deler like tider. For samleplass og KO ble
> «antall» forvirrende, «skiftlengde» er og forvirrende. Noen ganger ønsker man å ha
> mindre og mer plasser på enkelte skift visse deler av døgnet.» … «Har vi noe behov for
> skiftlengde?»

### Tre tilbakemeldinger som viste seg å være én

**Plassene hører til vinduet, ikke til ressursen.** Samleplassen kan ha seks plasser
14–22 og to 22–06 — det er **én** samleplass med to vinduer, ikke to samleplasser. Linja
sier nå *hva* (gruppe, hvor mange enheter), vinduet sier *når og hvor mange*.

**Og det er grunnen til at `skiftlengde` måtte gå.** Den var en *skjult multiplikator*:
den lagde seks skift ut av ett vindu, du så dem aldri, og alle seks fikk samme antall
plasser — altså nøyaktig det som ikke lot seg uttrykke etter flyttingen. En rotasjon settes
nå opp som de skiftene den er, og «Nytt skiftvindu» begynner der det forrige sluttet og
arver antallet, så Haugesund 56 er seks klikk. André valgte å fjerne den helt framfor å
erstatte den med en «del opp»-knapp.

**«Antall» finnes ikke for Samleplass og KO.** `flere_enheter=False` betyr at det bare kan
være én; serveren avviste alt annet fra før, men feltet sto der og lot som om det var et
valg. Nå står det «Finnes i ett eksemplar» i stedet.

### En feil funnet på veien

`plasser: 0` ble stille til `1`. Viewet gjorde `_int(...) or 1` **før** services fikk se
verdien, så regelen «hvert skiftvindu må ha minst én plass» kunne aldri fyre på et
eksplisitt null. Parsingen er flyttet til `services._linjens_skift()`, som eier regelen;
viewet sender råverdien videre.

### Mutasjonsprøvd

Åtte mutanter, sju drept med en gang: plassene lest fra linja igjen, null stille til én,
alle vinduer med første vindus antall, timesummen uten plasser, antallsfeltet vist/skjult
for alle, og klienten som teller per linje i stedet for per vindu.

Den ene som overlevde var «nytt vindu arver ikke forrige vindus antall» — en oppførsel jeg
valgte bevisst og ikke testet. Den har en test nå.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-oversikt.js`, `static/js/vaktliste-handlinger.js`,
`static/css/vaktliste.css`, `vaktliste/tests_planlegger.py`, `vaktliste/tests_xss.py`,
`CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: feltene lot seg ikke fylle ut

**Meldt fra staging (André):**

> «1) Når jeg har satt dato for vakten og åpner tidsrom skiftene skal starte, så begynner
> de på dagens dato og ikke vaktens starttidspunkt. 2) Og den er mer kritisk: jeg får ikke
> fylt feltene, de gir meg blankt på alle — antall, plasser per skift, fra, til.»

### Én feil, ikke to

Delegeringen i `portal-utils.js` sender **ett** argument — med mindre elementet bærer
`data-felt`, og da sender `hendelseArgumenter()` `(id, felt, verdi)`. Planleggerfeltene
ble skrevet med `data-arg="0:1:fra"` og handlere som tok `(arg, verdi)`. `verdi` var
derfor alltid `undefined`: hvert tastetrykk skrev `undefined` inn i tilstanden, og feltet
ble blankt ved neste tegning.

**Bug 1 var en følge av bug 2.** Standardvinduet var riktig hele tiden — målt: med vaktas
start 2. okt. 14:00 fylles feltet med `2026-10-02T14:00`. Men bug 2 tømte feltet ved første
berøring, og en tom `datetime-local` åpner på dagens dato.

**Regelen sto allerede i `CLAUDE.md`**, i avsnittet om `data-action` + `data-hendelse`.
Jeg skrev koden som om den ikke gjorde det.

### Fikset

Feltene bruker nå samme idiom som cellene i ressurstabellen — `data-felt` + `data-id` — og
adressen er en **stabil klient-ID**, ikke en indeks: `splice()` ville ellers flyttet
adressen til hver rad under den man fjernet, og neste tastetrykk skrevet i feil rad.

I tillegg: har vakta **ingen starttid**, faller standardvinduene tilbake til nå, og da sier
panelet fra. «Dagens dato» uten forklaring ser ut som et valg noen har tatt framfor et
fravær.

### Testen som manglet, og hvorfor de gamle ikke så det

De fjorten testene fra i dag kalte `mkPlanlegger()` og leste markupen. Ingen av dem rørte
handlerne, så en feil signatur var usynlig.

`PlanleggerfanenTests._skriv()` plukker nå attributtene ut av den **ekte** markupen og
sender dem gjennom delegeringens egen `hendelseArgumenter()` — argumentene bygges nøyaktig
som i nettleseren. Fire mutanter prøvd mot den: den opprinnelige signaturen, et felt uten
`data-felt`, indeks i stedet for ID, og `new Date()` i standardvinduet. Alle fanges.

**Og én av de nye testene gikk grønn ved flaks.** «Å fjerne en rad flytter ikke adressen
til de andre» sjekket bare lengden og den siste ID-en — med ID-ene 1, 3, 5 falt indeksene
slik at den siste ble den samme uansett hvilken rad som forsvant. Den krever nå hele
ID-lista.

**Endret:** `static/js/vaktliste-oversikt.js`, `static/js/vaktliste-handlinger.js`,
`vaktliste/tests_xss.py` (+10 tester), `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: fanen som lager grunnlaget

**Meldt fra staging (André):**

> «Litt usikker på om vi har skjønt hverandre. Du har lagt det inn i «planlegging»-fanen.
> Jeg ba om en **planlegger**. Den skal bare admin og leder ha tilgang til. For den
> genererer grunnlaget på alt. Vi skal kunne legge inn skift f.eks. tre firemanns lag fra
> kl. 14–22 og en ambulanse fra 15–03 mens en ambulanse går 8 timer rotasjon.»

### Misforståelsen, og hvor den kom fra

Hans opprinnelige melding nevnte generering først og timetallet sist. Notatet jeg skrev på
grunnlag av den snudde rekkefølgen: taket ble hovedsaken, og generatoren ble «steg 5, i sin
enkleste form — N plasser på én ressurs». Det er ikke det han ba om.

**«Planlegging» og «Planlegger» er to ulike fanér med to ulike spørsmål:**

| Fane | Spørsmål | Hvem |
|---|---|---|
| Planlegging | Hva koster lista dem som står i den? | `les` |
| **Planlegger** | Hva skal lista bestå av? | `kan_lede` |

Budsjettlinja og dagslinja er flyttet til «Planlegger» — «sette inn total timer og jobbe
overordnet» er lederens verktøy. Regnestykket var uavhengig av flata og fulgte med
uendret; det var bare plasseringen som var feil.

### Ressursen er subjektet, skiftvinduene hører til den

Andrés to ambulanser har ulik form, og Sola 56 bestemte datamodellen i skjemaet:

| Enhet | Oppsett | Blir |
|---|---|---|
| Haugesund 56 | 2 plasser, fre. 14 → søn. 14, skiftlengde 8 | 6 skift × 2 = **12 plasser, 96 t** |
| Sola 56 | 2 plasser, **to vinduer**: fre. og lør. 15–03 | 2 skift × 2 = **4 plasser, 48 t** |
| Lagene | 3 ressurser, 4 plasser, fre. 14–22 | **12 plasser, 96 t** |

Sola 56 er grunnen: hennes to vakter er **adskilte** — ikke en periode som deles, og ikke
to biler. Var raden i skjemaet et skiftvindu framfor en ressurs, hadde hun blitt til
«Ambulanse 1» og «Ambulanse 2».

**`skiftlengde` er det ene feltet som skiller formene.** Tom = ett skift som dekker
vinduet; et tall deler vinduet rygg mot rygg. Den siste bolken **kortes av, den strekkes
ikke**: 20 timer i åttetimersskift er 8 + 8 + 4, og et skift som varer lenger enn vakta
ville dukket opp som et brudd på skiftlengdegrensa uten at noen satte det opp.

### «Plasser per skift», ikke «antall folk»

André beskriver Haugesund 56 som «4 stk fordelt på 2 lag som går 8 på og 8 av». Modellen
trenger **2** — bilen har to seter, og de fire er bemanningspoolen som fyller tolv
skiftplasser over 48 timer. Feltet heter derfor «plasser per skift», og regnestykket står
under raden: «2 plasser × 6 skift = 12 plasser, 96 t». Oversettelsen fra hvordan man
snakker om bemanning til hva modellen lagrer skal være synlig **før** man trykker.

### Det som holder genereringen trygg

- **Plassene fødes som planlagt kladd** — usynlige for korpsene til lederen deler dem ut.
  Uten det ser et halvferdig oppsett ferdig ut i det øyeblikket knappen trykkes.
- **`erstatt_kladd` rører bare kladden.** Korpsreserverte, `alle_korps` og **alle**
  bemannede står. Reservasjonen leses av `reservert_korps()`, ikke av feltet — leses
  feltet direkte, slettes en hel bils plasser fordi ressursen bærer korpset.
- **Ingen `bulk_create`, alt i én `transaction.atomic()`.** Ikke bare for signalenes
  skyld: `erstatt_kladd` sletter før den skriver, så en feil halvveis ville etterlatt
  lista tommere enn før man trykket.
- **`?forhaandsvis` regnes av samme kode** (`_planlegg` + `_sammendrag`), på samme
  endepunkt. En forhåndsvisning som regner på egen hånd viser før eller siden noe annet
  enn det som skjer.
- **Grupper i ett eksemplar** (`flere_enheter`) avvises også her. En generator som lager
  «Samleplass 2» er akkurat den feilen flagget finnes for.

### Mutasjonstesting: 24 mutanter, og tre bommer verdt å skrive ned

**En mutasjon traff feil funksjon.** `if not services.kan_lede(request.user):` står også i
`vaktliste_detalj_view`, og `replace(..., 1)` tok den første — så porten jeg trodde jeg
prøvde var en annen. Et «OK» fra en mutasjon som ikke traff er verre enn ingen mutasjon:
den *bekrefter* en dekning som ikke finnes.

**To mutanter var no-ops.** `start = start + steg if False else slutt` er identisk med
`start = slutt`. Overlevelse betyr ingenting da.

**To fant ekte hull:**
- `erstatt_kladd` uten scope til vaktlista overlevde, fordi testen la «plassen på den
  andre lista» på en ressurs som var reservert til Haugesund — altså beholdt uansett. Den
  ligger nå på en ureservert ressurs, med en assertion om at den faktisk *er* kladd.
- `transaction.atomic()` lot seg fjerne, fordi all validering skjer i `_planlegg` *før*
  skrivingen. Det som manglet var en feil underveis: en test patcher nå
  `Ressurs.objects.create` til å feile på andre kall, og krever at den slettede kladden
  står der etterpå.

På klientsiden overlevde `Math.ceil` → `Math.floor`, fordi alle eksemplene mine gikk opp i
hele skift (48/8, 8/8). Og porten på selve fanen lot seg fjerne — ingen test spurte om
fanen var *borte* for `skriv_full`. Begge har tester nå.

### Ellers

**Skanneren leste ikke de nye byggerne** — igjen. `mkPlanlegger`, `_planleggerLinje`,
`_planleggerVindu` og `_genererFasit` sto én kjøring uten å være i `HTML_BUILDERS`. Det er
andre gang på én dag.

**Og skanneren har et hull som er verdt å kjenne:** den ser bare `${…}` inne i
template-literaler. `mkPlanlegger()` og `mkBelastning()` avslutter begge med
`hode + \`…\` + linjer + tomt`, og de konkatenerte leddene går forbi registeret uten et
ord. Verdiene er lokalt bygget markup i begge tilfeller, så det er ikke et hull i dag —
men regelen dekker mindre enn den ser ut til. Ført opp i TODO; det er samme sort feil som
`accounts/decorators.py` hadde, der en test som bare dekket halve syntaksen sto grønn i
et år.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`, `vaktliste/urls.py`,
`static/js/vaktliste-{kjerne,tegning,oversikt,handlinger}.js`,
`static/css/vaktliste.css`, `templates/vaktliste/index.html`,
`vaktliste/tests_planlegger.py` (ny, 42 tester), `vaktliste/tests_xss.py` (+16 tester),
`docs/FORSLAG_PLANLEGGERFANE.md`, `docs/TEKNISK_DOKUMENTASJON.md`, `CLAUDE.md`, `TODO.md`.

---

## 2026-09-15 — Vaktas budsjett: steg 2 og 3 mot planleggerfanen

`docs/FORSLAG_PLANLEGGERFANE.md` §7, steg 2 og 3. **Gjort i samme omgang med vilje:** en
«budsjettlinje» uten et budsjett er halve funksjonen, og taket er ett felt pluss én linje i
`kopier_oppsett`. Å dele dem ville betydd å bygge linja to ganger.

### Tre beslutninger til, tatt fordi koden sa noe annet enn notatet

**12. Linja bor i fanen som alt finnes.** Skissen sa «fanen ligger ved siden av «Oversikt»
og «Mannskap»» — men det finnes allerede en slik fane, og den heter **«Planlegging»**. En
ny ved siden av ville gitt to faner med én bokstavs forskjell, og den som leter etter
tallene sine måtte prøve begge. Budsjettlinja står derfor øverst i «Planlegging», over «Per
person»: vaktas tall først, den enkeltes under — motsatt ville begravet totalen under en
persontabell som kan bli lang.

**13. Taket er `skriv_leder`, ikke `skriv_full`.** Notatets §4 sa `skriv_full`. Det holdt
ikke mot koden: taket settes i **samme PUT** som vaktas start og planlagte slutt, og den er
`skriv_leder` med en begrunnelse som gjelder ord for ord her også — «spennet gjelder hele
vakta, ikke ett korps' del av den». Taket er tallet *alle* varsler på lista måles mot. Og
en PUT der `startet` krever ett nivå og `timetak` et annet er en regel ingen klarer å lese
riktig. Det gjør taket til per-vakt-søsteren av `Belastningsgrenser`, som også er
`skriv_leder`; forskjellen er rekkevidden, ikke hvem som bestemmer.

**14. Tallene sendes bare til den som ser alle korps.** De er hele vaktas og filtreres
aldri — taket gjelder lista, så et «satt opp» for ett korps kunne ikke sammenlignes med
det. Men da kan de heller ikke sendes til alle: for en `les` med badge ville summen vært et
aggregat over skift hun ikke får se. Samme regel som statistikkmodulen bruker.
`belastning_view` sender `planlegging: null`, og klienten tegner ingen linje — **ingen tom
ramme**, for den ville sagt «her er noe du ikke får se», som er en dårligere beskjed enn
ingen beskjed. Hennes egne timer står i «Mitt korps».

### Tallene

`services.planleggingstall()` gir **tre tall side om side**, fordi hvert av dem alene lyver
litt: «satt opp» er behovet, men ingen betaler for en tom plass; «bemannet» er nærmest
kostnad, men står på null når lista er halvt satt opp; «probono» vises for seg så summen
ikke utelater noe i stillhet (beslutning 9), og bare når det finnes noe å vise.

Avstanden mellom de to første er **selve arbeidslista**, så den regnes ut og står der:
312 satt opp mot 244 bemannet er 68 timer som mangler folk.

**`igjen` måles mot «satt opp»**, ikke mot «bemannet»: planlegging handler om behovet, og
et budsjett som først fylles når navnene er på plass sier «du har alt igjen» på en liste
som er ferdig satt opp. Går man over, blir tallet gult og etiketten bytter fra «igjen» til
«over taket» — et negativt tall under «igjen» leses som en regnefeil. **Ingenting avvises.**

**Dagslinja** bryter ned «satt opp» per dag, uten egne tak (beslutning 2), og sier det i
overskriften: «Satt opp per dag». Uten etiketten måtte leseren gjette hvilket av de to
tallene over den dagene summerer til. Den står ikke på en endagsvakt — én dag er ingen
nedbryting, bare totalen skrevet to ganger.

### To mutanter som fant ekte hull

**Rekkefølgen var garantert av modellen, ikke av regelen** — nøyaktig samme felle som
`_hviletider()` dokumenterer, og som traff oss 14. sep. også. `sorted()` lot seg fjerne
uten at noe ble rødt, fordi `Vaktpost.Meta.ordering` alt sorterer på `fra_tid`, så testene
gjennom basen målte modellens ordering. Dagbolkene er nå en egen funksjon, `_dagbolker()`,
prøvd med lister kalleren *ikke* har sortert.

**`timezone.localtime()` lot seg fjerne**, og testen min kunne ikke se det: de falske
skiftene bar norsk tid, mens ORM-en leverer UTC — da var `.date()` alt riktig. Rettet i
testen, ikke i koden. Feilen den vokter er verdt å kjenne: et skift som begynner 00:30
norsk tid er 22:30 UTC dagen før, så uten `localtime()` havner hver eneste nattevakt på
feil dag. Usynlig for alt som begynner på dagtid.

### Ellers

**Skanneren leste ikke de nye byggerne.** `mkBudsjett`, `mkDagslinje` og `_budsjettpost`
sto én kjøring uten å være i `HTML_BUILDERS`, og da var escaping-regelen stille av for dem
— suiten var grønn fordi ingen så etter, ikke fordi koden var riktig. En ny bygger som
skanneren ikke leser er nøyaktig det hullet den lista finnes for.

`kanSetteTak()` leser **serverens** `kan_sette_tak`, ikke `MODUL_TILGANG`: regnet klienten
den ut selv, kunne knappen og endepunktet komme i utakt, og en knapp som fører til en vegg
er verre enn ingen knapp.

Migrasjonen (`vaktliste/0018`) er ren skjemaendring uten `RunPython`, så den har ingen
triggerkø å tømme.

**Endret:** `vaktliste/models.py` + `migrations/0018_vaktliste_timetak.py`,
`vaktliste/services.py`, `vaktliste/views.py`, `static/js/vaktliste-oversikt.js`,
`static/js/vaktliste-kjerne.js`, `static/js/vaktliste-handlinger.js`,
`static/css/vaktliste.css`, `templates/vaktliste/index.html`,
`vaktliste/tests_belastning.py` (+29 tester), `vaktliste/tests_xss.py` (+14 tester),
`docs/FORSLAG_PLANLEGGERFANE.md`, `TODO.md`, `CLAUDE.md`.

---

## 2026-09-15 — Overlappet har fått et navn: steg 1 mot planleggerfanen

Første kodesteg fra `docs/FORSLAG_PLANLEGGERFANE.md` §7. Punktet sto i TODO fra
14. sep. 2026 og var ført opp som det som måtte løses **før** planleggeren: et tak som
telles feil er verre enn ikke noe tak.

### Docstringen lovet en telling som ikke fantes

`vaktliste/services._hviletider()` sa «Overlappet i seg selv fanges av
`overlapp`-tellingen». Det var ingen `overlapp`-nøkkel i belastningsraden. Det som
faktisk skjedde var at `korteste_hvile` ble `0.0` og raden ble flagget som **kort
hvile** — altså ble et dobbeltbooket mannskap vist som et hvileproblem, og planleggeren
fikk aldri vite hva det egentlig var.

### `_overlappstimer()`: sum minus union

12:00–20:00 og 16:00–22:00 er 8 + 6 = 14 timer skift, mens personen er til stede fra 12
til 22 — ti timer. Differansen, fire, er overlappet. Definisjonen er valgt fordi den gir
invarianten `timer - overlapp = faktisk tilstedeværelse`, og den er målt i en test framfor
antatt i en kommentar.

**Summen står fortsatt på 14.** Den er ikke korrigert, den er **navngitt**: raden sier at
fire av timene er dobbeltbooket, og vaktlederen retter det. Et tall som stille korrigerer
seg selv ville skjult nettopp den feilen vi ville vise — «varsler, de sperrer ikke».

**Probono teller med her, i motsetning til i `timer`.** Summen er det organisasjonen
betaler for; et overlapp er at én person står to steder, og kroppen skiller ikke på lønn.
Samme resonnement som `lengste_skift` og `korteste_hvile` alt sto på.

**Rundet én gang, til slutt.** Summeres avrundede timetall hver for seg, kommer
differansen ut som 0.01 for skift som ikke overlapper — og et varsel som fyrer på en
avrundingsfeil er et varsel man slår av. Testen bruker et **funnet** tilfelle
(02:53–07:27, 07:27–14:40, 16:56–21:01), søkt fram blant tilfeldige oppsett, fordi den
første varianten jeg skrev ned ga −0,03 og altså ikke viste det jeg påsto den viste.

### I grensesnittet

Ny **Overlapp**-kolonne i belastningstabellen, som bare står når noen faktisk er
dobbeltbooket — samme regel som Faktisk-kolonnen: en kolonne full av nuller stjeler bredde
fra dem som betyr noe. Pluss et varsel i hodet: «1 dobbeltbooket — 4 t».

**Varselet sier timene, ikke en terskel.** Et langt skift måles mot organisasjonens
grense, fordi det er en vurdering noen har gjort. To skift på samme person samtidig er en
planleggingsfeil uansett hva grensene sier, så det har ingen grense å måle mot.

**`<colgroup>` regnes nå ut.** To valgfrie kolonner gir fire former, og fire håndskrevne
blokker er fire steder å glemme når kolonne nummer ni kommer — med `table-layout: fixed`
gir feil antall `<col>` ingen feilmelding, bare en tabell som er litt gal.
`_kolonneandeler()` normaliserer vektene til hele prosenter og fordeler resten etter
størrelse, ikke etter rekkefølge. Testen teller `<th>`-ene framfor å skrive av et
forventet tall.

### Mutasjonsprøvd

Ni mutanter, sju drept med en gang. To overlevde og var **ekvivalente** (`len(spenn) < 1`
og `fra >= slutt` gir samme svar) — begge er nå notert i koden, slik at neste leser ikke
leter etter et hull som ikke finnes.

To mutanter avslørte ekte svake assertions, og begge av samme sort: testen traff et annet
sted i svaret enn den mente. «4 t» står både i varselet og i raden, så en `assertIn` mot
hele utdata gikk grønn når cella alltid ga streken, og når varselet mistet tallet sitt.
Begge leser nå ut av sin egen blokk (`<tbody>`, `vl-varsler`).

### Beslutning 9–11 i planleggernotatet

Tre spørsmål notatet ikke stilte, funnet ved å lese koden før byggingen begynte:

- **Probono teller ikke mot taket, men vises for seg.** `_sumTimer()` utelot dem allerede;
  en budsjettlinje som utelater noe uten å si det er et tall noen vil bestride.
- **Genererte plasser fødes som planlagt kladd** (`services.er_planlagt()`), usynlig for
  korps-brukerne til de deles ut.
- **«Åpen for alle»-plasser overlever en ny generering**, som de korpsreserverte. Med
  beslutning 10 blir regelen én setning: generatoren rører bare det `er_planlagt()` kaller
  kladd.

### Og en fil som måtte deles

De nye linjene dyttet `vaktliste-tegning.js` over 1 800, og
`test_hver_del_er_mindre_enn_den_var` sa fra. Det er nettopp den regelen som gjør
JS-delingen fra 14. sep. verdt noe: uten den kunne én fil vokst tilbake til 3 800 linjer
mens de andre sto tomme, og alle de andre reglene vært grønne hele veien.

`vaktliste-oversikt.js` er skilt ut, og skjøten er ikke vilkårlig: **alt over den tegner
regnearket** — fanene, ressurskortene og radene man redigerer i — og **alt under leser de
samme skiftene og svarer på noe annet**: bemanningskurvene, utskriftslista, belastningen,
«Tilstede nå», «Mitt korps». De to sidene deler `_posterFor()`, `_sumTimer()` og
`_skifttimer()`, som blir stående i tegningsfila.

941 og 921 linjer. `VAKTLISTE_JS` og `<script>`-taggene i malen holdes like av
`VaktlisteFileneDekkerAltTests`, og ingenting i den nye fila kjører på toppnivå.

**CLAUDE.md sa «Sytten filer i `static/js/`».** Det var 23. Tallet sto ikke i
`PAASTANDER`, så `TallpaastanderTests` kunne ikke se det — den vokter
`TEKNISK_DOKUMENTASJON.md`, som var riktig helt til denne delingen og ble rettet av testen
med en gang. Et tall ingen test leser, råtner; begge er rettet nå.

**Endret:** `vaktliste/services.py`, `static/js/vaktliste-tegning.js`,
`static/js/vaktliste-oversikt.js` (ny), `templates/vaktliste/index.html`,
`patients/js_test_utils.py`, `vaktliste/tests_belastning.py` (+19 tester),
`vaktliste/tests_xss.py` (+6 tester), `docs/FORSLAG_PLANLEGGERFANE.md`,
`docs/TEKNISK_DOKUMENTASJON.md`, `CLAUDE.md`, `TODO.md`.

---

## 2026-09-15 — Planleggerfanen: åtte beslutninger, og en rettelse av mitt eget notat

Gjennomgang av `docs/FORSLAG_PLANLEGGERFANE.md` med André. Ingenting er bygget — dette er
underlaget som gjør at det *kan* bygges uten å ta de samme avgjørelsene om igjen.

### Rettelsen først

Notatets §3.3 hevdet at planleggeren «bør følge rapportmodulens midnattsregel, fordi det er
*timer* som telles», og at de to reglene derfor sto i konflikt. **Det var feil.** Splitting
ved midnatt endrer ikke en totalsum — fredag 20:00 til lørdag 04:00 er åtte timer uansett
hvilken dag de føres på. Regelen betyr bare noe når timene **brytes ned per dag**.

Det gjorde spørsmålet i §5 feilstilt: det fantes ingen konflikt å løse, bare et valg om
hvilken dag dagslinja fører timene på. Avsnittet er skrevet om, med feilen stående, fordi
et notat som stille retter seg selv ikke lærer den neste leseren noe.

### Beslutningene (André)

| # | Spørsmål | Svar |
|---|---|---|
| 1 | Hva er timetallet? | **Tak som varsler**, ikke inngangsverdi (avgjort tidligere) |
| 2 | Tak per dag? | **Nei — ett tak for hele vakta**, pluss en dagslinje uten egne tak |
| 3 | Skal generatoren fylle plassene? | **Nei, bare tomme plasser** |
| 4 | Ny generering over eksisterende? | **Erstatt tomme — behold de korpsreserverte og alle bemannede** |
| 5 | Teller taket ledige eller bemannede? | **Begge, side om side** |
| 6 | Kopieres taket av `kopier_oppsett`? | **Ja** |
| 7 | Hvilken midnattsregel? | **Startdagen**, som resten av vaktlisteflaten |
| 8 | Overlapp-punktet? | **Først** |

Tre av dem er verdt begrunnelsen sin:

**Beslutning 3 holder tilgangsmodellen utenfor en løkke.** En generator som bare lager
tomme plasser er `skriv_full` og ferdig med det; en som fyller må bære
`kan_sette_vaktpost()` — badge *og* reservasjon — inn i hver eneste rad den lager. Og den
holder linja fra `kopier_oppsett`: en liste ingen har sagt ja til ser ferdig ut.

**Beslutning 4 skiller utkast fra løfte.** En tom plass uten reservasjon er generatorens
eget utkast, og å skrive over det koster ingenting. En tom plass reservert til et korps er
noe noen har sagt «denne er deres» om — korpset ser den i «Mitt korps» og planlegger mot
den. Reservasjonen leses av `services.reservert_korps()`, ikke av feltet, fordi plassens
`korps` overstyrer ressursens og tom verdi betyr «som ressursen».

**Beslutning 5, fordi hvert tall alene lyver litt.** «Satt opp» er behovet — det
planleggingen handler om — men ingen betaler for en tom plass. «Bemannet» er nærmest
kostnad, men står på null når lista er halvt satt opp. Avstanden mellom dem er dessuten
selve arbeidslista: 312 mot 244 er 68 timer som mangler folk.

### Regelen som nå skal stå tre steder

**Planlegging fører skiftet på startdagen; fakturering splitter ved midnatt.** Den står i
`CLAUDE.md` (for `_dagnokkel()`) og i planleggernotatet; `docs/FORSLAG_RAPPORTMODUL.md`
§2.2 er det tredje stedet, og er ført opp i TODO. Forskjellen er bevisst og skal ikke
«rettes» — spørsmålene er ulike: «hvem er på vakt den dagen» mot «hvor mange timer skal
betales for det døgnet».

**Endret:** `docs/FORSLAG_PLANLEGGERFANE.md` (§3.2–§3.4 og §4 skrevet om, §5 er nå
avklarte spørsmål, ny §6 med beslutningene, §7 er rekkefølgen), `TODO.md`.

---

## 2026-09-15 — «Avbrutt» og «trenger ny ressurs» var ett spørsmål, og måtte være to

**Meldt fra staging (André):**

> «Akutt oppdrag opprettes, to enheter varsles. Ene bilen behandler på stedet, andre bil
> slo avbrutt. Da står det trenger ressurs selv om oppdraget er løst — og trykker en bil
> avbryt så må det vises.»

### Feilen

Regelen sto som ett spørsmål: *finnes det andre enheter som ikke er ledige?* Den kan ikke
skille en bil som ble ledig fordi hun **ble ferdig** fra en som ble ledig fordi hun
**avbrøt** — begge deler er `Ledig` på koblingsraden.

Så: Bil A behandlet på stedet og ble ledig. Bil B avbrøt. Ingen andre var «aktive», og
oppdraget ble merket «trenger ny ressurs» — et krav om handling på et ferdig oppdrag.
Reprodusert som test før noe ble rørt.

`trenger_ny_ressurs()` stiller nå **begge** spørsmålene: er noen fortsatt på vei, *og* var
noen framme. `LOSER_OPPDRAGET` er `(Behandlet, Leverer)` — og `Ledig` står bevisst ikke
der, siden det er nettopp den statusen som er tvetydig.

Svaret leses av **statusmeldingene, ikke koblingsradene**: `behandle_paa_sted` sender raden
videre til `Ledig` med samme tidspunkt, så raden bærer ikke lenger spor av at jobben ble
gjort.

**Samme feil sto i `start_oppdrag`** — en bil som rykker videre fra et oppdrag noen andre
alt hadde løst, etterlot det samme feilmerket. Begge kallsteder bruker nå funksjonen.

### Andre halvdel: avbrytelsen må vises

Feilrettingen gjør dette *viktigere*, ikke mindre viktig: før ble et slikt oppdrag stående
på tavla (med feil merke); nå ryddes det bort av seg selv. Uten et merke ville rettingen
gjort avbrytelsen usynlig i stedet for feilmerket.

`avbrutt_av` står nå i svaret — på tavla, i detaljen og i historikken — og tegnes som et
eget merke i enhetsmatrisen. **Dempet, ikke alarmerende:** en avbrytelse er en opplysning
om hva som skjedde, mens «trenger ny ressurs» er et krav om handling nå. Fikk de samme
farge, ville den ene lært operatøren å overse den andre. Begge kan stå samtidig, og da er
de to opplysninger.

Merket er med i **ETag-en**. En bil som avbryter på et oppdrag noen alt har løst endrer
verken status eller tidspunkt, så uten det ville merket druknet i en 304.

*Valgt form: merke i lista, ingen sperre (André). Restrisikoen er at et løst oppdrag ryddes
til historikken med det samme, så operatøren kan gå glipp av merket live — det står i
historikklista, men ikke på tavla.*

### Tester

`oppdrag/tests_avbrutt.py` — 22 tester. **Ni mutasjoner prøvd, alle fanget** etter at to av
mine egne tester ble rettet:

- Bulk-testen hadde bare **én** avbrytelse, så rekkefølgen kunne ikke vises — en bulk som
  sorterte feil vei gikk grønn.
- ETag-testen avbrøt siste bil, og da endret oppdragets *status* seg uansett. Den målte
  altså ikke det den påsto. Isolert nå: en annen bil står fortsatt i Fremme, så status og
  tidspunkt er like før og etter, og merket er det eneste som skiller svarene.

En tredje test hadde dødkode (`... if False else None`) fra en halvferdig formulering og
påsto dermed nesten ingenting. Skrevet om til Andrés scenario helt ut.

### Notat: planleggerfane — `docs/FORSLAG_PLANLEGGERFANE.md`

Andrés andre punkt. Timetallet er avklart som **et tak som varsler**, ikke en inngangsverdi
generatoren regner fra — samme linje som `Belastningsgrenser`.

Notatet peker på at det meste finnes: `_sumTimer`, `mkGruppekurve`, `_vaktensSpenn`,
`belastning_per_person`, og — viktigst — at «å generere et skift» er å opprette `Vaktpost`
uten `mannskap`, som modellen alt er bygget for. Tre feller er navngitt: `bulk_create`
ville tømt auditsporet (`kopier_oppsett` gikk i den fella), den doble regelen må gjelde
også når maskinen setter plasser, og **overlapp-punktet i TODO bør løses først** — et tak
som telles feil er verre enn ikke noe tak.

---

## 2026-09-15 — Vaktlista: dagen ytterst i «Oversikt», og sammenslåtte ressurskort

To av de tre ønskene fra 14. sep. er levert. Drift-automatikken står igjen og tas for seg.

### Først: en feil i mitt eget notat

TODO sa at planleggingstabellen «viser radene i serverens rekkefølge, sortert men **uten
dagskille**», og at dagrupperingen derfor måtte bygges der. Det var galt — `mkRessurs()`
har kalt `_blokkerMedDager()` hele tiden, og en test håndhevet det. Feilen betydde at
arbeidet så større ut enn det var; den er rettet i TODO.

### Dagen er én regel, to visninger

`_dagnokkel()` er det ene stedet som avgjør hvilken dag et skift hører til, og svaret er
**startdagen**: «fre. 20:00 – lør. 04:00» står under fredag. Ikke under begge dager, ikke
splittet ved midnatt (André, 15. sep. 2026).

**Merk spenningen mot rapportmodulen, som er bevisst:** der splittes skift ved midnatt
(`FORSLAG_RAPPORTMODUL.md` §2.2), fordi spørsmålet er hvor mange timer som skal betales.
Her er spørsmålet hvem som er til stede. De to skal ikke «rettes» mot hverandre.

Nøkkelen er nå **nullpolstret** (`2026-09-04`), fordi `_grupperPaaDag()` sorterer på den og
`2026-9-15 < 2026-9-4` som tekst. Hjelperen sorterer selv framfor å hvile på at den som
kaller har sortert — samme grunn som `_hviletider()`.

### «Oversikt» snudd: dag ytterst, ressurs under

Før svarte arket på «hvem står på denne bilen, og når» — begrunnelsen i `CLAUDE.md` var at
den som leser står ved bilen. Nå svarer det på **«hvem er på vakt i dag, og hvor»**, som er
det den som møter om morgenen spør om. Begge er gyldige; dette er et valg om hvem arket er
for, og `CLAUDE.md` er skrevet om i samme commit.

En ressurs med skift to dager står nå i begge dagbolkene. Det er prisen for snuingen, og
den er riktig her. Summene per ressurs er dermed **per dag**; totalen i arkhodet er
fortsatt for hele vakta.

`_blokkrader()` er skilt ut av `_blokkerMedDager()`: «Oversikt» har dagen som overskrift
over tabellen, og en dagrad inni ville sagt det samme to ganger på rad.

**Utskrift:** `.vl-dagtittel` har `break-after: avoid` — en dagoverskrift alene nederst på
et ark er en side ingen kan bruke. Hele dagbolken får *ikke* `break-inside: avoid`: en dag
med tolv ressurser er lengre enn et ark, og regelen ville enten blitt ignorert eller
skjøvet en halv tom side foran seg.

### Dagoverskriften vises nå alltid

Også på en endagsvakt (André: «alltid»). Den gamle regelen — bare på flerdagsvakter — hadde
en reell kostnad: planleggeren måtte vite at *fraværet* av en dagrad betydde noe, og
tabellen skiftet form når vakta ble forlenget.

### Sammenslåtte ressurskort

En fane med ti ambulanser var ti regneark under hverandre. Kortene er nå sammenslåtte som
standard — men **bare når gruppa har mer enn én ressurs** (André snevret det 15. sep.): en
vakt med én ambulanse ville ellers kostet et klikk hver gang for å se det eneste som er der.

Tre valg det er verdt å kunne begrunne:

- **Tilstanden ligger i `ressursApen` i `vaktliste-kjerne.js`, ikke i DOM-en.** `mkRessurs()`
  bygges på nytt ved hvert panelbytte — samme grunn til at `gateKnapper()` ikke kan gate den.
- **Map, ikke Set.** Fraværende nøkkel betyr «som standarden». Et Set kunne ikke skilt «ikke
  rørt» fra «utvidet for hånd», og et kort man åpnet ville slått seg sammen igjen neste gang
  noen la til en bil i gruppa.
- **Ikke `localStorage`.** En sidelasting er et nytt blikk på vakta; et kort man slo sammen i
  går skal ikke være skjult når man kommer tilbake for å planlegge.

**Et sammenslått kort er ingen blindvei:** «Rediger», «Roller» og «Opprett vakt» blir
stående i hodet, og sammendraget sier hva som er der — «1 skift · 1 mannskap · 1 ledig ·
16 t». `apneVaktpost()` åpner kortet, ellers lagrer man et skift og ser ingenting skje.

**En latent feil ble synlig:** `ressurser.map(mkRessurs)` sendte indeksen som andre
argument. Det var harmløst så lenge byggeren tok ett argument, og sluttet å være det i det
øyeblikket den tok to — bil nummer null hadde stått lukket og resten åpne.

### Samme dag, etter tilbakemelding fra staging

**André:** *«Ser initielt greit ut på oversikt, men i ressursgruppene så må det være likt
som oversikt — ressurser per dag. Minimer-knappen er fin.»*

Gruppefanen var fortsatt en stabel ressurskort med dagrader inni, mens «Oversikt» hadde
fått dagen som nivå over. Nå er dagen ytterste nivå **begge steder**:

```
Fane «Ambulanse»
  bemanningskurven
  Fredag 3. okt
    Bil A   (kort, minimerbart)
    Bil B
  Lørdag 4. okt
    Bil A
  Uten skift
    Bil C
```

Tre ting fulgte av snuingen:

- **`mkRessurs(r, apen, egne)` tegner de skiftene den får.** Dagbolken sender sin egen dags
  skift, så ett kort dekker én dag — og kortet bruker `_blokkrader`, siden en dagrad inni
  ville gjentatt tittelen rett over. `_blokkerMedDager()` er dermed bare «Mitt korps» igjen;
  den flata har én tabell på tvers av ressursene og altså ingen seksjon å legge dagen i.
- **«Uten skift» er en egen bolk.** En ressurs uten skift hører til ingen dag, og uten
  bolken ville kortet med «Opprett vakt» ikke funnes noe sted — ingen kunne satt opp den
  første vakta på en ny bil. Bolken vises bare når noen faktisk står der.
- **Vippa sitter på ressursen, ikke på ressursen-den-dagen.** En bil som står i to
  dagbolker slås sammen begge steder; to tilstander for én ting ville vært verre enn ingen.

**En mutasjon avslørte at en garanti var en tilfeldighet.** Rekkefølgen i dagbolken skal
være ressursenes, ikke skiftenes — men skiftene ble samlet per ressurs først, så
rekkefølgen fulgte av *hvordan lista ble bygget* og ikke av regelen. Å fjerne regelen
endret ingenting, og testen gikk grønn. `_gruppedagbolker()` leser nå skiftene i serverens
rekkefølge og filtrerer ressurslista, slik at regelen faktisk bærer — og mutasjonen
feiler. Testen måtte også legge skiftet **først** i lista (`unshift`), ellers var det
innsettingsrekkefølgen som ble målt.

Den nye byggeren er lagt i `HTML_BUILDERS`: en markup-bygger XSS-skanneren ikke leser er
nøyaktig det hullet den lista finnes for.

Sju nye tester, fire mutasjoner prøvd — alle fanget etter at kilden ble rettet.

### Og én gang til: velgeren over utskriftslista

**André:** *«Vi beholder «hele vakten» men fjerner ressursene fra det nedtrekksvinduet og
bytter med dag. Så går vakten 1 dag så får du ikke flere valg; går den over flere dager får
du den enkelte dag.»*

Ressursvalget var riktig da arket var gruppert på ressurs. Etter snuingen var «Ambulanse 1»
et snitt på tvers av det arket er bygget rundt — man valgte én akse i en liste sortert på en
annen. `utskriftRessurs` er erstattet av `utskriftDag` (en `_dagnokkel()`-streng, eller
`null` for hele vakta).

- **En endagsvakt får ingen velger.** Ett valg i et nedtrekk er en kontroll som ikke gjør
  noe — «hele vakten» og «den ene dagen» er samme ark. Utskriftsknappen står igjen alene.
- **Filtreringen skjer før tallene regnes.** Skriver man ut lørdag, sier arkhodet lørdagens
  timer og ikke hele vaktas. Ligger filteret i dagbolkene i stedet, blir hodet stående og
  beskrive noe annet enn arket under det.
- **Et valg som ikke finnes lenger gir et tomt ark**, ikke en feil — lista kan ha blitt
  lastet på nytt siden man valgte.

**To av mine egne tester målte feil etter endringen**, og det er verdt å merke seg hvorfor:
dagnavnene står nå *også* i velgeren, som kommer først i markupen. Et søk på «Lørdag 5. sep»
traff da verktøylinja, og sliced hele arket i stedet for lørdagsbolken — testen var fortsatt
grønn, men målte noe annet enn den påsto. Assertionene slicer nå på `<h2 class="vl-dagtittel">`.

Fire mutasjoner prøvd, alle fanget.

### Tester

Elleve nye i to klasser (`DagenErYtterstTests`, `SammenslaatteRessurserTests`), og den
gamle dagoverskrift-bolken er skrevet om mot den nye strukturen. **Elleve mutasjoner
prøvd, alle fanget.**

En av dem avslørte en svak assertion hos meg: `ut.count('vl-dagbolk')` teller også
`vl-dagbolk-x`, så en omdøpt klasse slapp gjennom. Assertionene teller nå `class="..."`
eksakt.

To ting ble rettet underveis fordi eksisterende gjerder fanget dem: escaping-skanneren
avviste sammendraget bygget som template-literal (skrevet om med `+`, som `_blokklinje()`
gjør), og et søk-og-erstatt i testfilene traff en JS-streng i stedet for en harness-liste.

---

## 2026-09-14 — To notater: DPIA-vurderingen og vaktlisteutbedringene (ingen kode)

To samtaler skrevet ned. Ingen kodeendring — begge notatene finnes for at beslutningene
skal kunne tas med åpne øyne, og TODO peker til dem.

### `docs/NOTAT_DPIA_OG_FRITEKST.md`

Utløst av Andrés spørsmål om AMK-adresse kan legges i `Oppdrag.fritekst`, og av at
fritekst aldri slettes fra historikken.

**Ett premiss måtte rettes:** «vi slipper DPIA fordi vi har personverndokumentasjon» er
ikke det A.12 sier, og ville heller ikke holdt — da kunne enhver behandling dokumentert seg
ut av art. 35. A.12 bygger på tre andre ben: ingen direkte identifikatorer, ikke stor skala,
ingen profilering. **Skalaen holder, og en adresse endrer den ikke.** Men A.12 har selv
skrevet utløseren — «særlig dersom nye moduler tar inn direkte identifikatorer» — så
vurderingen er allerede forpliktet til å tas opp igjen i akkurat dette tilfellet.

**Og luken er større enn DPIA-spørsmålet:** A.12 er en *sikkerhets*risikovurdering. Den
måler sannsynlighet for og konsekvens av brudd — risiko sett fra systemets side. Art.
35(7)(c) spør noe annet: hva skjer med pasienten hvis det går galt? Det spørsmålet stilles
ikke noe sted i dokumentet. Samme slags feil som `rullTilFeil()` rettet samme dag:
vurderingen er gjort, bare ikke fra det ståstedet den skulle.

Kartlagt i samme slengen — **hvor fritekst faktisk lever**: skjult for bilen straks
oppdraget er `Ledig`, hele oppdraget borte etter 30 min, aldri arkivert, aldri verdilogget
— og **stående for alltid i KOs historikk**, pluss 730/90 dager i backupfilene. Beskyttelsen
er bygget helt og holdent mot bilen. En slettefrist er derfor reell beskyttelse mot at noen
leser historikken tre måneder senere, men den er **ikke** en sletterett; det skal stå
skrevet, ikke oppdages senere.

**Den viktigste enkeltadvarselen:** adressen må ikke legges i `Lokasjon`. `Lokasjon.navn`
fryses som `ArkivertOppdrag.lokasjon_navn` og inngår i **SHA-signaturen** — en adresse lagt
der er låst i 24 måneder ved konstruksjon og kan ikke fjernes uten at arkivet melder
tukling. Det tilsynelatende ryddige nedtrekket er den farligste plasseringen.

To ting er merket for **primærkildesjekk** framfor å gjettes på: Datatilsynets liste over
behandlinger som alltid krever DPIA, og WP248-kriteriene i gjeldende form.

### `docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md`

De tre ønskene fra 14. sep. sto punktvis i TODO, hver for seg. Notatet finnes fordi de
henger sammen på en måte som ikke synes da:

**To av tre trenger dagruppering, og de ber om den på hvert sitt sted** — «Oversikt» vil ha
dagen ytterst, gruppefanene vil ha dagoverskrifter i planleggingstabellen. I dag finnes
dagen bare i `_blokkerMedDager()`. Bygges de hver for seg, får portalen to dagrupperinger
som kan komme i utakt — og det er en stillegående utakt: to lister som grupperer dagen ulikt
ser begge riktige ut hver for seg. Anbefalingen er én funksjon, to kallsteder, og at
midnattsvalget dermed tas én gang.

Midnatt er også allerede i spill: rapportmodulen har avklart at **timer** splittes ved
midnatt, mens oversikten spør om *tilstedeværelse*, ikke timer. De to kan lande ulikt — men
da skal det stå hvorfor, ellers leses forskjellen som en feil.

Den tredje, «fjern Sett i drift», deler ingen kode med de to andre og kan tas parallelt.
Men knappen gjør **fire** ting, og to av dem mister hjemmet sitt hvis drift bare utledes:
`satt_i_drift_av` mister mening, og e-postutløseren forsvinner. Det peker mot «automatisk
med unntak» framfor rent utledet — den som møter 30 minutter før vaktstart skal fortsatt
kunne stemple.

---

## 2026-09-14 — 400 ved bemanning av ledig plass: nedtrekket tilbød et umulig valg

**Meldt fra staging (André):**

```
PUT https://testportal.sanitet.net/vaktliste/api/vaktposter/88/  →  400 (Bad Request)
endreVaktpost @ vaktliste-offline.js
```

…og etterpå: *«Jeg fikk feilen i konsoll på f12, så ingenting i nettleseren ellers.»*

Det er **to feil i én melding**, og de er verdt å skille:

### 1. Serveren gjorde riktig; grensesnittet spurte om noe umulig

`Vaktpost` har `UniqueConstraint(ressurs, mannskap, fra_tid)`. Nedtrekket for en ledig
plass ble bygget av `_fyllValgFor()`, som listet **hele** mannskapsregisteret uten å se på
hvem som alt sto på den ressursen til den starttiden. Valgte man en av dem, avviste
viewet med «Personen står allerede på denne ressursen fra dette tidspunktet» — riktig
svar på et spørsmål som aldri skulle vært stilt.

Det bryter portalens egen regel: **«en knapp som fører til en vegg er verre enn ingen
knapp.»** Regelen sto skrevet om `window.MODUL_TILGANG` og gjelder like fullt her.

`opptattPaaPlassen(vp, poster)` er ny og filtrerer nedtrekket. Den ligger som **egen
funksjon**, ikke som en `filter` inne i byggeren, av samme grunn som `klikkSkalKjore()`:
en regel som ikke lar seg kalle, lar seg ikke prøve. Fire ledd, og hvert av dem er en
egen feil å gjøre — raden selv teller ikke, ledige plasser (`mannskap_id === null`)
sperrer ingen, annen ressurs er fritt fram, annen starttid er en annen rad. Alle fire er
mutasjonsprøvd.

Kilden er `alle_vaktposter` — alt serveren sendte — ikke `vaktposter`, som er det
korpsfilteret slapp gjennom. Skranken er en databasekjensgjerning uavhengig av hvem som
ser raden. Det lekker ingenting: filteret kan bare *fjerne* valg, aldri vise et navn.
**Restrisikoen står igjen** — serveren filtrerer i tillegg sitt eget svar, så en
korps-bruker kan fortsatt treffe veggen. Da vises meldingen, og den rulles nå fram.

**Merk hva den *ikke* gjør:** den sperrer ikke overlapp på tvers av ressurser. Å stå på
KO og på bilen samtidig er bevisst tillatt (`test_overlapp_paa_tvers_av_ressurser_stoppes_ikke`),
og er ført opp for seg i TODO.

### 2. Feilmeldingen ble skrevet utenfor skjermen

`endreVaktpost()` kalte `visPanelfeil()` som den skulle, og `#vl-feil` sto i malen. Men
banneret ligger rett over `#vl-panel`, altså **øverst på sida**, mens nedtrekket som ble
avvist kan stå tretti rader ned i et regneark som ruller. Meldingen ble skrevet — bare
der ingen så den.

En feilmelding ingen ser er verre enn ingen feilmelding: brukeren tror lagringen gikk
igjennom, mens raden ruller tilbake til lagret verdi uten forklaring. `rullTilFeil()`
bringer banneret fram med `block: 'nearest'` — ruller minst mulig, så et banner som alt
står i bildet ikke får sida til å hoppe. Uten `scrollIntoView` (eldre nettleser) vises
meldingen som før; rullingen er en forbedring, ikke en forutsetning.

*Dette punktet ble ikke funnet av en test — det ble funnet fordi André sa hva han
**ikke** så. Verdt å merke seg: suiten kan bekrefte at en melding skrives, men ikke at
noen leser den.*

### Hva som med vilje **ikke** ble rørt

`apneRedigerVaktpost()` fyller sitt nedtrekk fra hele registeret på samme måte, og kan
derfor treffe samme skranke. Det ble stående, av to grunner:

- **Vinduet kan endre `fra_tid` i samme lagring.** Et filter regnet ut da vinduet ble
  åpnet gjelder den *gamle* starttiden; flytter man skiftet til et tidspunkt der plassen
  er ledig, ville en gyldig person vært borte fra lista. Å skjule et lovlig valg er en
  vanskeligere feil å oppdage enn en 400 med melding.
- **Veggen er skiltet der.** `lagreVaktpost()` viser avslaget med `_visFeil(...)` inne i
  vinduet, altså der brukeren ser. Det var nettopp dét som manglet i raden.

### Nye tester

`vaktliste/tests_dobbeltbooking.py` — ti tester i to klasser. Seks mot filtreringsregelen
(fire mutasjoner fanget), fire mot banneret (tre mutasjoner fanget: fjernet kall,
`'nearest'` → `'start'`, fjernet `typeof`-vakt).

De seks eksisterende harness-listene som når `_fyllValgFor` fikk `opptattPaaPlassen` lagt
til. **Det er prisen for at harnessene navngir funksjoner eksplisitt** — en ny hjelper
brukt av en testet funksjon gir `ReferenceError` i tolv tester før noen har skrevet en
linje ny test. Prisen er bevisst: alternativet er å laste hele fila, som har
toppnivå-avhengigheter til DOM-en.

---

## 2026-09-14 — Minimerbare ressurser ført i TODO (ingen kode)

**André:** minimerbare lag/ambulanser i gruppefanene, dagruppering som i Oversikt, og alle
minimert som standard.

Problemet er konkret: en fane med ti ambulanser er i dag ti regneark under hverandre.
Gruppefanen har allerede bemanningskurven øverst, og den *er* oversikten over gruppa —
kortene under er detaljen. Med alt sammenslått blir fanen «kurve + hvilke biler finnes»,
som er den riktige første visningen.

**Dagrupperingen avdekket en reell forskjell mellom de to flatene.** Oversikt har
`_blokkerMedDager()` og setter dagoverskrifter; planleggingstabellen har ingen — den
viser radene i serverens rekkefølge (`Vaktpost.Meta.ordering = ['fra_tid',
'mannskap__navn']`), altså sortert men uten dagskille. Samme funksjon bør kunne brukes
begge steder.

Tre ting ført opp som må avklares før noen bygger:

- **Hvor lever sammenslått/utvidet?** `tegnFaner()` og `mkRessurs()` bygger markupen på
  nytt ved hvert panelbytte — samme grunn til at `gateKnapper()` ikke kan gate dem.
  Tilstanden må ligge utenfor markupen; `erDempet` i `oppdrag-enhet.js` er presedensen.
- **Alltid minimert, eller bare når det er mer enn én?** En vakt med én ambulanse gir et
  klikk hver gang for å se det eneste som er der. `_blokkerMedDager()` har presedensen for
  det motsatte valget — dagoverskrifter vises bare når vakta har mer enn én dag. Ført som
  spørsmål, ikke som innvending: Andrés ordlyd er «alle minimert som standard».
- **Åpnes kortet automatisk når man må inn i det?** Ellers leder «Rediger ressurs» til noe
  man ikke ser.

---

## 2026-09-14 — To vaktlisteønsker ført i TODO (ingen kode)

**«Sett i drift» skal bort — drift skal følge vakta** (André). Problemet den løser er
ekte: glemmer noen å trykke, kan ingen stemple møtt ved vaktstart, altså nøyaktig når det
betyr noe og når alle har mest å gjøre.

Men knappen gjør **fire ting, ikke én** (`drift_view`): setter status, setter
`satt_i_drift_at`, setter `satt_i_drift_av`, og **sender vaktlista på e-post** når admin
har slått det på. To av dem mister sitt hjem hvis knappen forsvinner — `satt_i_drift_av`
mister mening, og e-postutløseren må flyttes til en klokke. Begge er ført opp.

Designspørsmålet er om drift skal **utledes** eller **klokkesettes**. Utledet er mest i
portalens ånd — presedensen er `Vaktpost.er_tilstede`, «utledes, aldri lagres; to kilder
til samme sannhet går i utakt første gang noe feiler halvveis». Og kantene som må avklares:
den som møter tidlig, og den som glemte å stemple av.

**«Oversikt» skal siles etter dag først, så ressurs** (André). Dagen finnes allerede som
begrep — `_blokkerMedDager()` setter en dagoverskrift *inne i* hver ressurs — så dette er
en omstrukturering, ikke et nytt begrep.

Lesemodellen er det som endrer seg. I dag svarer lista på «hvem står på denne bilen, og
når»; begrunnelsen i `CLAUDE.md` var «den som leser den står ved bilen». Snudd svarer den
på **«hvem er på vakt i dag, og hvor»** — spørsmålet den som møter om morgenen faktisk
stiller.

Ett spørsmål må avgjøres: **hvor havner et skift som krysser midnatt?** I dag files det
under startdagen (`_dagnokkel(fra_tid)`). Med dag ytterst blir det et reelt valg — bare
startdagen betyr at den som ser på lørdag morgen ikke ser Kari, selv om hun er på vakt.
Merk spenningen mot rapportmodulen: for **timer** er det avklart at skift splittes ved
midnatt, men for **oversikten** er spørsmålet hvem som er til stede, ikke hvor mange timer
som skal faktureres. De to kan lande ulikt — men da bevisst.

---

## 2026-09-14 — Rapportnotatet skrevet ferdig (ingen kode)

`docs/FORSLAG_RAPPORTMODUL.md` er revidert etter diskusjonen med André. Fortsatt et
forslag — ingen kode skrevet.

**Jeg tok feil i første utkast, og det står nå i notatet.** Jeg frarådet LLM-tolkning med
eksempelet «én rød pasient, hjertestans, kl. 14:32». André ba meg se på hva
statistikkmodulen faktisk sender. **Eksempelet finnes ikke i dataene** — payloaden er
aggregater, uten radnivå, uten ID-er, uten klokkeslett per hendelse, og `fritekst`,
`notat` og `merknad` går ingen steder.

Det endrer jussen, ikke bare risikovurderingen: GDPR gjelder ikke anonyme data
(fortalepunkt 26), så A.8 er ikke i spill. Jeg hoppet over det spørsmålet og gikk rett til
«ny databehandler». Feil rekkefølge, og skrevet ned så neste leser slipper å gjøre samme
feil.

**Andrés forslag om å ekskludere risikoproblemstillinger framfor å undertrykke små celler
er bedre**, og notatet forklarer hvorfor de ikke løser samme problem: undertrykking retter
seg mot *identifiserbarhet*, ekskludering mot *skade*. Verdimengden i `patients/choices.py`
avgjør saken — «Mistanke overgrep» og «Psykiatri» står side om side med «Skade ankel/fot».
Én av hver har samme identifiserbarhet og helt ulik konsekvens.

Ekskludering er dessuten bedre for små vakter, som er normaltilfellet: en vakt med tolv
pasienter ville fått nesten alle celler undertrykt under en `n < 5`-regel — formelt trygt
og praktisk verdiløst.

**Den avklarende innsikten: filteret gjelder bare maskinen.** I portalen trengs verken
undertrykking eller ekskludering — den som ser rapporten har allerede `les` på
kildemodulen og kan åpne pasientlista. Filteret hører hjemme på payloaden som *forlater*
portalen. Det løser også regneproblemet: menneskerapporten er komplett, maskinpayloaden er
redusert, og ingen leser maskinpayloaden som en rapport.

**Filteret må feile lukket**, og det er motsatt av `NOKLER_UTEN_AUDIT` i `core/signals.py`
— av nøyaktig samme resonnement. Merkes kategorier som skal *ekskluderes*, slipper en
glemt ny kategori ut. Merkes de som er *godkjent for utsending*, ekskluderes en glemt ny
til noen aktivt godkjenner den. En auditliste skal feile mot mer logging; et
personvernfilter mot mindre deling.

**Notatet er skrevet med to varianter**, etter Andrés ønske: variant A uten LLM er et
komplett produkt alene, variant B legger tolkningen på toppen. Stegene 1–4 i anbefalt
rekkefølge krever ingen personvernbeslutning i det hele tatt.

**Midnatt er avklart:** rapporten skal vise både per dag og totalt, så skift som krysser
splittes — 4 timer på fredag, 4 på lørdag. Bemanningskurven gjør det allerede
(`vl-dogn`), så alternativet ville gitt to flater i samme portal med ulike tall.

**Leverandør: Scaleway Generative APIs anbefales**, først og fremst fordi Scaleway SAS
allerede står i A.2 med signert DPA. Zero retention som standard, franske datasentre, ingen
amerikansk morselskap og dermed ingen CLOUD Act-eksponering. Mistral er nærmeste
alternativ, men zero retention ligger bak Scale-planen. **Merket i notatet som ikke
verifisert mot primærkilden** — Scaleways domene var blokkert av egress-proxyen.

---

## 2026-09-14 — Vaktlista: overlappende skift ført i TODO (ingen kode)

Funnet mens rapportmodulen ble diskutert, men punktene hører hjemme i vaktlista og er
uavhengige av om rapporten noen gang bygges.

**Docstringen lover en telling som ikke finnes.** `vaktliste/services._hviletider()` sier
«Overlappet i seg selv fanges av `overlapp`-tellingen». Det er ingen `overlapp`-nøkkel i
belastningsraden. Det som faktisk skjer er at `korteste_hvile` blir `0.0` og raden flagges
som **kort hvile** — altså vises et overlapp som et hvileproblem, og planleggeren får ikke
vite hva det egentlig er.

**Og et overlapp blåser opp timesummen.** Målt: skift 12:00–20:00 (8 t) og 16:00–22:00
(6 t) på samme person gir `timer = 14.0`, mens personen var til stede i 10 timer. I dag er
det harmløst fordi ingen betaler etter tallet — det er et planleggingsvarsel. Som
fakturagrunnlag er det fire timer noen betaler for uten at noen var der.

**Timer har ingen dagdimensjon.** `_timer()` er ren varighet; fredag 20:00 → lørdag 04:00
gir 8,0 timer uten at koden har noe begrep om hvilken dag de tilhører. Spørsmålet var
ubesvart i koden fordi ingenting hadde stilt det. Bemanningskurven har presedensen — den
bøtter per time og markerer midnatt (`vl-dogn`) — så Andrés regel «fredag 23:59 er fredag,
lørdag 00:00 er lørdag» betyr at et skift **splittes ved midnatt**.

**En sperre hører ikke hjemme i databasen.**
`test_overlapp_paa_tvers_av_ressurser_stoppes_ikke` dokumenterer at dagens oppførsel er
bevisst: «noen ganger står man på to lister». Å sperre det i basen krever
`ExclusionConstraint`, som **ikke finnes i SQLite** — da ville suiten vært grønn lokalt
mens prod oppførte seg annerledes, nøyaktig fella fra 30. aug. 2026. Riktig sted å nekte er
ved **frysing** av en liste som skal bli fakturagrunnlag, ikke ved planlegging der
overlappet bare er informasjon.

Ingen kode skrevet. `docs/FORSLAG_RAPPORTMODUL.md` er ikke oppdatert ennå — diskusjonen
pågår.

---

## 2026-09-14 — Forslag: rapportmodul (ingen kode)

`docs/FORSLAG_RAPPORTMODUL.md`, skrevet på Andrés spørsmål om en `/rapport/`-modul som
henter fra vaktlista og statistikken. **Ingen kode er skrevet** — dette er grunnlag for
en beslutning.

**Del 1, timeregnskap med kroner per korps: anbefales.** Mye finnes allerede —
`belastning_per_person()` regner timene, og `Vaktpost.probono` bærer skillet «går, men
telles ikke i timene», med kommentaren «summen er det organisasjonen betaler for».
Betalingstanken var altså inne i modellen før noen planla den.

Den viktigste innsikten i notatet: **tall som brukes til penger må fryses.** I dag er
vaktlistedata operative og kan rettes fritt. Som fakturagrunnlag må de slutte å bevege
seg — ellers retter noen et skift i mars, og fjorårets faktura stemmer ikke lenger med
det portalen viser. Portalen har mønsteret to ganger (`core.arkiv`), så dette er ikke nytt
arbeid, men det gjør del 1 større enn «en tabell med timer».

**Del 2, LLM-tolkning: frarådes i første omgang**, og begrunnelsen er ikke teknisk:

- En språkmodell er en **ny databehandler**. `PERSONVERN_DOKUMENTASJON.md` A.8 sier i dag
  «ingen overføring av personopplysninger til land utenfor EU/EØS» — verifisert mot
  dokumentet, ikke husket
- **«Uten navn» er ikke anonymt.** Én rød pasient med hjertestans kl. 14:32 på et navngitt
  arrangement er sannsynligvis nøyaktig én person. Det som beskytter er små tall, ikke
  fravær av navn
- **Tolkningen er den delen leseren ikke kan etterprøve.** Rapporten leses av noen som
  ikke var der — det er poenget med den — og da kan de heller ikke se at tolkningen er
  feil. Tallene er signert; en setning er det ikke

Forslaget er å skille rapporten fra tolkningen: portalen lager tallene, og den som vil ha
prosa tar det utenfor portalen under eget ansvar. Da slipper portalen å stå i
behandlerkjeden for noe den ikke trenger å stå i.

Fem åpne spørsmål står i §5. Del 1 kan begynne uten at del 2 er avgjort, og det er en
fordel: timeregnskapet har verdi alene og tvinger ikke fram en personvernbeslutning før
dere er klare til å ta den.

Hver påstand i notatet er verifisert mot koden — funksjonsnavn, felter, filstier og
A.8-formuleringen.

---

## 2026-09-14 — Tallgjerdet: dokumentene kan ikke lenger lyve om antall

Det ene av tre åpne punkter som var verdt å lukke. De to andre —
`accounts` → `oppdrag.Enhet` og `style-src 'unsafe-inline'` — ble gjennomgått og
**bevisst latt stå**; begrunnelsene står i `docs/TEKNISK_DOKUMENTASJON.md` kap. 15.

**`core/tallfasit.py` (ny)** regner ut antall ruter (totalt og per prefiks), backup-
handlere, moduler, statistikk-kilder og JS-filer fra koden.
`python manage.py tallfasit` skriver dem ut — den som skal oppdatere et dokument
trenger å vite hva det riktige tallet er, og da må utregningen finnes utenfor testen.

**`TallpaastanderTests` krever at dokumentene stemmer.** Tretten påstander er registrert
i README, CLAUDE.md, deploy-guiden og teknisk dokumentasjon.

Dette dekker den halvdelen av dokumentråte som oppstår **uten at noen gjør noe galt**:
«178 tester totalt» var sant da det ble skrevet, og «16 endepunkter» var sant da det var
alt som fantes. Legger noen til en rute, feiler testen til dokumentet følger etter.

**Påstandene registreres eksplisitt, ikke gjettes ut av prosaen.** Et mønster som lette
etter «\<tall\> endepunkter» hvor som helst ville truffet setninger som ikke er påstander
om totalen — og en test med falske funn blir slått av, ikke fulgt. Regexen må dessuten
treffe nøyaktig ett sted; flere treff er enten duplisert påstand eller et for løst
mønster, og testen skiller de to feilene i meldingen.

**Gjerdet fant en feil før det var ferdig skrevet, og den var min:** kapittel 5 oppga 8
ruter under «`/varsler/`, `/api/`, m.fl.» Det riktige er 13 — jeg hadde glemt `/healthz/`,
`robots.txt`, manifestet, «min profil» og videresendingen fra `/api/`. Nøyaktig den sorten
feil tallgjerdet finnes for.

Tre mutasjoner prøvd, alle fanget:

| Mutasjon | Meldingen |
|---|---|
| Dokumentet påstår feil tall | «totalt antall ruter står som '99', men koden har 123» |
| Koden får en ny rute, dokumentet står stille | «står som '123', men koden har 124» |
| Fasiten går i stykker | Sperrehaken sier «fant nesten ingen ruter» — i stedet for at alle rader feiler og leses som «dokumentene er gale» |

Den midterste er poenget: **drift fanges av seg selv**, uten at noen må huske å telle.

`docs/TEKNISK_DOKUMENTASJON.md` kap. 15.8 er skrevet om og viser nå åpent hvor lite
gjerdet ville fanget av dokumentrunden: to av fem funn. De tre andre — nedlastings-
oppskriften, `TypeError`-signaturen og feil regex — er påstander om *innhold*, og de
løses av at noen leser diffen.

---

## 2026-09-14 — Dokumentrunden del 3: resten av teknisk dokumentasjon

André: «Hvis teknisk dokumentasjon ikke er ferdig gjennomgått så må vi gjøre det.» Riktig
innvending — **halvveis verifisert dokumentasjon er verre enn tydelig uverifisert**, fordi
merket forsvinner ved neste redigering og det uetterprøvde da ser ut som resten. Kapittel
5, 8A–8E og 13–16 er nå gjennomgått, og alle markørene er borte.

**Kapittel 5 dokumenterte 16 av 123 endepunkter**, med tilgangskrav oppgitt som `admin`,
`lead`, `read_write`. Strukturen er endret med vilje: en håndskrevet liste over 123
endepunkter råtner fra dagen den skrives. Nå står **konvensjonene og tilgangsmønsteret**
fullstendig, med et kart over hvor endepunktene bor og en kodesnutt som skriver ut den
autoritative lista — **verifisert ved å kjøre den ordrett**.

Det viktigste som manglet: **dekoratøren gater lesing, viewet gater skriving.** Det er
grunnen til at et skriveendepunkt kan se ut til å kreve bare `les`, og uten den
forklaringen leser tabellen som et hull i sikkerheten.

**Kapittel 8B dokumenterte en signatur som ikke finnes.**
`@cached_stats_response(ttl=15, key_prefix=...)` ville gitt `TypeError` — parameteren
heter `cache_key` og kommer først. Verre: påstanden om at nøkkelen bygges av «aktivt år og
rollen som ber om dataene» var feil i begge retninger. Den lovet en isolasjon per rolle
som ikke finnes, og skjulte kravet som faktisk gjelder — at **kallstedet** må legge slug
og vakt-ID i nøkkelen selv.

**`_scrub_secrets` var gjengitt feil.** Den dokumenterte regexen krevde `bruker:passord@`;
den ekte krever ikke kolon, og treffer derfor også `redis://token@host`. Fem kodelinjer
er nå verifisert ordrett mot kilden.

**8A hadde en hengende tabellrest** fra en sletting som ble gjort i overskriften og ikke i
kroppen: avsnittet sa «fjernet 13. sep.» og beskrev deretter flagget som om det fantes,
med en `is_feature_enabled()` som ikke er skrevet. Det er den vanligste formen for
dokumentråte.

**Kapittel 13 viste til `PUT /api/backup-config/` og `POST /api/reset-active-year/`** —
ingen av dem finnes, og den siste beskrev en nullstilling av «aktivt år» som
vakt-modellen erstattet.

**Kapittel 14 oppga «178 tester».** Nå er det 2 751. Kapittelet er skrevet om til
prinsipper som holder — hvorfor `myproject` skal med, hvorfor migrasjonsprøver mot ekte
PostgreSQL ikke kan erstattes av suiten, skillet mellom å lese kildekode og å påstå at en
kodelinje står der, vinduskanten i rate-limit — pluss **tretten testklasser som håndhever
regler om kodebasen**. Alle tretten er verifisert å eksistere.

**Kapittel 15 fikk tre nye kjente begrensninger**, alle ærlige: `style-src` tillater
fortsatt `unsafe-inline`, `accounts` → `oppdrag.Enhet` står igjen i
`KJENTE_UNNTAK_RAMMEVERK`, og gjerdet mot dokumentråte har en luke som ikke kan lukkes
uten å gjøre historiske avsnitt umulige.

**Gjerdet er utvidet til å lese stier uten backticks.** `patients/middleware._MetricsStore`
sto i en tabellcelle og slapp forbi da modulen flyttet — stier uten backticks er like døde
som stier med.

**Og gjerdet tok meg selv, to ganger.** Først på `manage.py show_urls`, som jeg skrev inn
med et forbehold om django-extensions — men et forbehold i teksten er ikke godt nok når
kommandoen ikke virker. Så avdekket det at **mine egne «ikke gjennomgått»-markører tiet
regelen for hele kapitler**, fordi en seksjonsmarkør gjelder til neste overskrift. Det er
et argument mot slike markører i seg selv, og de er nå borte.

*To av mine egne mutasjonsforsøk traff ingenting fordi jeg muterte tekst som ikke sto der
— feilen var i mutasjonen, ikke i testen. Det står her fordi «mutasjonen ble ikke fanget»
og «mutasjonen ble aldri utført» ser helt like ut i en logg.*

---

## 2026-09-14 — Dokumentrunden del 2, og den uforklarte feilen fikk et navn

Gjeldspunkt 3 er ferdig: alle seks dokumenter gjennomgått mot koden, pluss et gjerde
som gjør mekanisk dokumentråte til en rød test.

**Personvernprotokollen dokumenterte en annen tilgangsmekanisme enn den som finnes.**
A.10 listet `read_only`, `read_write`, `lead_view`, `lead` og `admin` med hver sine
rettigheter i en matrise. **De fire første ble slettet i deploy 2.** Det er alvorligere
her enn i README: dette er dokumentet man legger fram ved en DPA-gjennomgang. Samme feil
sto i A.6 (`role` som «tilgangsnivå») og i sjekklista C.1, der man ble bedt om å
verifisere roller som ikke finnes. Den ekte modellen er dessuten *strengere* — en konto
uten `ModulTilgang`-rader ser ingenting — så fortellingen var også unødig svak.

**A.2: bucketen hos Scaleway inneholder nå autentiseringsdata.** Da hel databasebackup
ble lagt til, endret innholdet seg materielt: passord-hasher, TOTP-hemmeligheter og
audit-logg. Protokollen sa fortsatt «modulenes data». Ført inn med de tre tiltakene
risikoen håndteres med — kryptering med en nøkkel Scaleway ikke har, 90 dagers frist mot
modulfilenes 730, og en IAM-nøkkel uten sletterett. Den korte fristen var en riktig
avgjørelse som ikke var dokumentert som en avgjørelse.

Endringsloggen hoppet fra 29. august til i dag, og versjonshodet sto på «1.8» mens siste
oppføring var v1.10. **Hullet er beskrevet framfor etterdatert** — en endringslogg som
fylles inn i ettertid er verdiløs nettopp som endringslogg.

**Teknisk dokumentasjon:** tittelen sa «Pasientregistreringssystemet» og kapittel 3
beskrev tre apper. Portalen har seks. Kapittel 3, 4, 6, 7, 8, 9 og 10 er skrevet om —
registrene, den ekte nivåstigen, CSP slik den er i dag, backup i to lag, og JS-en etter
delingen. **Ti døde filstier** rettet. Kapitler som *ikke* er gjennomgått er merket der
de står, i stedet for å se like ferske ut som resten.

**`core/tests_dokumentråte.py` (ny).** Dokumentasjon har ingen testsuite, og det er
dagens feilmodus. Testen krever at hver filsti, hver `manage.py`-kommando og hvert
slettet symbol dokumentene navngir, stemmer med koden. Den fant umiddelbart tre ting jeg
hadde oversett — blant dem en rad i personvernprotokollens A.13 som fortsatt påsto at
«backup ekskluderer sensitive data» fordi `BACKUP_APPS` var satt til `['patients']`.

Fire mutasjoner prøvd, tre fanget. **Den fjerde slapp gjennom og står skrevet i testen:**
skriver man `> **Historisk**` over en påstand, tier regelen til neste kapittel. Det er en
bevisst luke som er lett å misbruke, og den løses av at noen leser diffen — ikke av at
testen blir strengere.

**Og den uforklarte enkeltfeilen fikk endelig et navn.** Den het
`core.tests_ratelimit.RateLimitEndepunktTests.test_opprett_pasient_strupes`, og fanget
seg selv i det øyeblikket en full PostgreSQL-kjøring ble tatt vare på med `tee` i stedet
for grep-et bort — nøyaktig det jeg skrev i evalueringen at jeg skulle gjøre annerledes.

Årsaken er vinduskanten i `django_ratelimit`, altså samme rotårsak jeg rettet tidligere
samme dag: 65 forsøk mot `60/m` deles i to bøtter der ingen når 60. **Den var brutt tre
steder, ikke ett** — også `test_full_stats_strupes` (35 mot 30) og
`test_auditlog_eksport_strupes` (15 mot 10). Regelen er derfor nå funksjonen
`nok_til_a_bryte(grense)` med begrunnelsen i docstringen, ikke tre tall man skriver av.
Bekreftet med 30 kjøringer på PostgreSQL uten én feil.

---

## 2026-09-14 — Dokumentrunden, del 1: deploy-guide, runbook og README

Gjeldspunkt 3. Tre av seks dokumenter; de to store og gjerdet står igjen.

**`docs/DEPLOY_GUIDE.md` var verre enn utdatert — den motsa en sikkerhetsbeslutning.**
Kapittel 5 sa «en backup skal kun inneholde pasientdata – aldri brukere, passord eller
audit-logg», og ga så en oppskrift på å **laste ned backupfila** for å kontrollere det.
Begge deler er feil: den hele databasebackupen inneholder brukere, MFA-hemmeligheter og
logg med vilje, og backupfiler skal ikke lastes ned i det hele tatt. Hadde noen fulgt
oppskriften, hadde de lagt en helseopplysningsdump i nedlastingsmappa mens de trodde de
gjorde en sikkerhetskontroll. Erstattet med `verifiser_backup`.

Den beskrev også `BACKUP_APPS` og `BackupConfig.interval_minutes` — begreper som ikke
finnes — og manglet AHASend, offsite, cron-tjenestene, hash-låste avhengigheter og
staging-flyten. Nytt **kapittel 10, rollback**, sto ikke på lista: en redeploy i Railway
ruller ikke tilbake databasen, så release-loggen må leses først.

**`docs/RUNBOOK_VAKT.md`: to av tre punkter på lista var alt gjort.** §8b dekket allerede
hel backup, tom base og den bindende rekkefølgen, og §14 med `scripts/sikkerhetssjekk.py`
fantes. Lista var utdatert, ikke dokumentet. Det som manglet var **§8c, «Deployen knakk —
rull tilbake»**, som ingen hadde ført opp. §1 har fått et punkt om ingen deploy fra
sjekklista til vakta er over, med byggnummeret notert.

**`README.md` var den mest villedende av dem alle.** Den beskrev rollemodellen
`read_only`/`read_write`/`lead_view`/`lead` og fem `kan_redigere_*`-flagg på
`CustomUser` — **ingen av delene finnes**, de ble slettet i deploy 2 og 3. En leser bygget
altså feil mental modell av hele tilgangsstyringen. Den påsto også «178 tester totalt»
(nå 2 744) og at backup «inneholder kun pasientdata (`BACKUP_APPS=['patients']`)».

Skrevet om som **inngangsdør, ikke kopi**: en tabell over hvor ting står, korrekt
arkitektur med de sju registrene, den ekte tilgangsmodellen, og pekere til deploy-guiden i
stedet for en duplisert Railway-oppskrift som ville drevet fra hverandre. Testtallet er
tatt ut — et tall der råtner fra dagen det skrives.

Hver påstand i deploy-guiden og README er maskinelt verifisert mot koden: kommandoer,
filstier, miljøvariabler, interne lenker, og `Procfile`-linjene ordrett.

---

## 2026-09-14 — Arbeidsflyt: byggnummer ved push, og åpne punkter som ikke får gjemme seg

To regler i `CLAUDE.md`, begge fra ting som gikk galt i dag.

**Commit-SHA ved hver push.** André: «når du pusher ting så vil jeg ha bygg nr
jeg kommer til å se på staging/prod». Sju tegn, for hver gren som ble pushet.
Det er nummeret som står i Railway-deployen, og uten det må den som verifiserer
gjette om det hun ser på er det som nettopp gikk ut.

**Et åpent punkt skal aldri stå som barn under et avkrysset punkt.** Da jeg
krysset av gjeldspunkt 1 og 2, ble to uavkryssede barn stående under dem —
`accounts` → `oppdrag.Enhet`, og den uforklarte enkeltfeilen. De var «i TODO» i
bokstavelig forstand og usynlige i praksis. Løftet til en egen bolk øverst, med
en peker igjen der de lå.

---

## 2026-09-14 — Service workeren til `vl-sw-5`, og utkastingen fikk en test

Bumpet foran prod-deployen. `activate` sletter alle `vl-sw-`-cacher som ikke
bærer gjeldende versjon, og fram til nå lå den gamle, udelte `vaktliste.js`
igjen i skallcachen på hver drifts-PC som hadde vært innom — død vekt, ikke
feil versjon, siden WhiteNoise hasher filnavnene og sida hentes nett-først.

**Prisen står i koden**: datakopien slettes med, så en PC som mister nettet
rett etter en bump står uten offline-liste til den har lastet én gang online.
Derfor ikke ved hver endring — en ny fil hentes uansett uten at versjonen røres.

**Utkastingen var udekket, altså den ene oppførselen bumpen hviler på.**
Regelen er nå `skalKastes()`, skilt ut som navngitt funksjon ved siden av
`avgjor()` og `erForGammel()`.

*Mitt første forsøk var feil, og det står i testens docstring:* jeg kopierte
`filter`-kroppen inn i testen som en streng. Da måler testen sin egen kopi og
går grønn uansett hva workeren gjør — nøyaktig synden gjeldspunkt 3.8 handlet
om, begått samme dag som jeg ryddet den. Funksjonen ble skilt ut i stedet.

Fem tester, tre mutasjoner fanget: likhet i stedet for prefiks (da overlever
både `-skall` og `-data`), `vl-sw-`-sjekken droppet (da slettes cacher
workeren ikke eier), og versjonen ikke bumpet.

---

## 2026-09-14 — Portalens egne tabeller auditlogges, og to lister som måtte finne selv

**`core/signals.py`: `AppSetting`, `ModuleSettings` og `Vakt`.** Hullet André
fant ved å spørre «logges ingenting fra core?». Svaret var nesten nei, og det
var ikke nytt av flyttingen — det hadde stått slik hele tiden. Portalen logget
hvert feltbytte på en pasient minutiøst, mens «noen slo av pasientmodulen for
alle» og «noen flyttet sesjonstimeouten fra 8 til 720 timer» ikke etterlot noe.
Feil vei rundt: jo mer inngripende handlingen var, jo mindre spor satte den.

**Den vanskelige halvdelen var å la være å logge.** `AppSetting` er
nøkkel/verdi og blander innstillinger et menneske har bestemt med tellere
maskinen har talt.

Jeg ga først André cron-linjene som eksempel. Det var det svakeste — fem rader
i måneden, knapt et problem. Da jeg gikk etter tallene i stedet for min egen
påstand, fant jeg det som faktisk betyr noe: `next_patient_nr_vakt_<id>`
telles opp ved **hver pasientregistrering**, og `next_oppdrag_nr_vakt_<id>` per
oppdrag. Uten unntaket gir en vakt med hundre pasienter hundre auditrader som
ingen har gjort, blandet inn mellom de ekte pasientradene — på nøyaktig de
vaktene der loggen betyr mest.

Regelen står som én navngitt funksjon, `nokkel_logges()`: **logg det et
menneske har bestemt, ikke det maskinen har talt.** Prefikser og ikke eksakte
navn, fordi tellerne bærer vakt-ID — en eksakt liste ville virket i test og
lekket ved neste vakt. Og det er en **unntaksliste**: en ny nøkkel logges som
standard, fordi en teller for mye er støy mens en innstilling for lite er et
hull man oppdager et år senere.

Verdiene logges, e-postmottakerne inkludert (Andrés avgjørelse): «hvem ble lagt
til» er hele spørsmålet man stiller, og oppbevaringen er den `purge_old_logs`
alt håndhever — ingen ny mekanisme, ingen ny frist.

`EKSPLISITT_MAPPING` i `audit/signals.py` blir virksom for første gang her.
Fram til nå merket den ingen rader, fordi ingen skrev tabellnavnene — noe jeg
skrev i TODO da jeg oppdaget det, framfor å la den se ut som den gjorde jobb.

**To lister som lette på steder i stedet for å finne dem — samme lærdom, samme dag.**

`SignalerFyrerIkkeUnderLoaddataTests` håndhever at hvert lagringssignal har
`@ikke_under_loaddata`. Den scannet `('oppdrag', 'patients', 'vaktliste')`
skrevet for hånd — så `core/signals.py` ville gått rett forbi den dagen den ble
skrevet, mens testen sa «alle lagringssignaler» og målte tre apper. Den globber
nå `*/signals.py`, med `VAKTEN_UNNTATT` for det ene tilfellet som med vilje står
uten (`audit.fyll_app_label` kortslutter på tomt felt).

Og `core/tests_testkommandoen.py` (ny) gjør det samme for testkommandoen i
CLAUDE.md: hver toppnivåpakke med `test*.py` må stå i den, og kommandoen må ikke
navngi noe som ikke finnes. Den utelot `myproject` i lang tid uten at noe sa
fra, og feilen ble funnet fordi et testtall ikke stemte — det er flaks, ikke en
mekanisme, og flaks kan man ikke planlegge to ganger.

Begge testene har en sperrehake mot seg selv: finner oppdagelsen nesten
ingenting, feiler den framfor å gå grønn mens den måler tomhet.

Tester: `core/tests_signaler.py` (16) og `core/tests_testkommandoen.py` (4).
Fem mutasjoner prøvd, alle fanget — tellerne fjernet fra unntakslista,
unntakslista snudd til inkluderingsliste, `pre_save` som ikke spør basen om
raden finnes, `myproject` fjernet fra kommandoen igjen, og en app som ikke
finnes lagt til.

---

## 2026-09-14 — To funn fra staging: CSP blokkerte lydbæreren, modaler holdt på fokus

Begge meldt av André ved verifisering på staging, og begge var ekte feil bak en
melding som så ut som støy.

**`media-src 'self' blob:` lagt til i CSP** (`core/middleware.py`). Konsollen sa:

    Loading media from 'blob:…' violates … "default-src 'self'". Note that
    'media-src' was not explicitly set, so 'default-src' is used as a fallback.

Det som ble blokkert er `_stilleLydbaerer()` i `oppdrag-enhet.js` — den stumme,
loopende WAV-en som finnes fordi iOS ellers regner Web Audio som «ambient» og
demper lydvarselet med ringebryteren. `default-src 'self'` dekker ikke `blob:`.

**Symptomet skjulte alvoret.** Oppdraget lastet, siden virket, og feilen sto
bare i konsollen — men på iOS betyr den at bilen ikke piper når telefonen står
på lydløs, altså nøyaktig det tilfellet lydbæreren er bygd for. En advarsel på
en side som ellers oppfører seg er ikke det samme som en advarsel uten
konsekvens.

Direktivet er smalt med vilje: `'self' blob:`, ingen verter, og `default-src`
er **ikke** slakket. En blob-URL kan bare lages av skript på vårt eget origin,
så den som kan lage en har allerede skriptkjøring — utvidelsen flytter ingen
grense som betyr noe. Å svare med `default-src 'self' blob:` ville derimot
sluppet blob-er inn i hvert direktiv som arver.

**`slippFokusFoerSkjul()` i `portal-utils.js`.** Bootstrap 5.3 setter
`aria-hidden="true"` på modalen når den lukkes, men flytter ikke fokus ut
først; lukker du med krysset, står fokus igjen på `.btn-close` inne i det som
nettopp ble skjult, og nettleseren **nekter** å sette attributtet:

    Blocked aria-hidden on an element because its descendant retained focus.

Konsekvensen er reell i begge ender: modalen blir liggende eksponert for
skjermlesere etter at den visuelt er borte, og den som navigerer med tastatur
mister fokuspunktet sitt i samme øyeblikk.

`hide.bs.modal` bobler, så **én** lytter i fila alle sidene laster dekker hver
modal i portalen. Alternativet Bootstrap selv peker på, `inert`, måtte vært
satt og fjernet per vindu — samme feil gjentatt ett sted per modal. Funksjonen
er navngitt og ikke anonym av samme grunn som `klikkSkalKjore()`: en `if` inne
i en lytter lar seg ikke kjøre i en test.

Tester: `patients/tests_security_headers.MediaSrcSlipperLydbaerenTests` (fem,
inkludert én som krever at kilden *fortsatt* lager blob-en — et direktiv som
verner om ingenting er verre enn ingen regel) og `core/tests_modalfokus.py`
(seks). Tre mutasjoner prøvd, alle fanget: media-src fjernet, `hide` byttet til
`hidden`, og `contains`-sjekken fjernet slik at fokus rives vekk uansett hvor
det står.

---

**Og et tredje funn, som kom av å telle testene:** kjøringen ga 2 687 der
forrige fulle kjøring ga 2 709. Differansen var ikke tester som forsvant —
**testkommandoen i CLAUDE.md utelot appen `myproject`**, 32 tester på
databasevalg, cache, `_env_bool`, statiske filer og migrasjoner. Det er vaktene
rundt «`DATABASE_URL` må være PostgreSQL på Railway» og rundt den `_env_bool`
som hadde rate-limitingen av i prod til 13. sep. Den som fulgte dokumentasjonen
kjørte dem aldri. Kommandoen er rettet.

At alt annet *er* med, er verifisert og ikke antatt: en AST-telling av
testmetoder per app stemmer eksakt med det kjøreren rapporterer for seks av
sju apper (`vaktliste` avviker med 54, som er arv fra basisklasser), og alle
98 testfiler samles inn.

**`myproject/tests_cache_config.py` hadde en ekte feil i opprydningen.**
`finally: importlib.reload(...)` sto *inne* i `with mock.patch.dict(...)`, med
kommentaren «Reload tilbake uten REDIS_URL så andre tester ikke påvirkes» — men
inne i blokken er `REDIS_URL` fortsatt satt, så modulen ble lastet tilbake med
den oppdiktede Redis-verten. Koden gjorde det motsatte av det kommentaren sa,
og det er den verste sorten: den som leser slutter å se etter.

Nå `addCleanup`, som kjører uansett utfall og etter at `with` er ute. Å bare
flytte `finally` utenfor ville vært verre enn før — en feilende assertion ville
hoppet over opprydningen helt.

**To mutasjoner mot den nye påstanden slapp gjennom**, og det står i koden:
opprydningen i *neste* test i klassen reparerer modulen før noen ser den gal,
så bare den siste testen alfabetisk kan lekke ut av klassen. Påstanden er
beholdt fordi den er gratis og sier at opprydningen gjorde jobben — men den er
ikke et gjerde rundt mønsteret, og kommentaren sier nå det i stedet for å la
den se sterkere ut enn den er.

**Én ting står uløst.** Den kjøringen som først tok med `myproject` endte
`FAILED (failures=1)`. Jeg fanget ikke hvilken test det var, og den har ikke
kommet tilbake på fire fulle kjøringer etterpå. Den er *ikke* forklart av
opprydningsfeilen over — det er en hypotese jeg ikke har bevist. Se TODO.


## 2026-09-14 — Gjeldspunkt 3.6: de to store JS-filene delt

`vaktliste.js` var 3 801 linjer, `oppdrag-sentral.js` 1 991. Nå fem og fire.

**Jeg rådet fra denne**, og står ved begrunnelsen: uten bundler er en deling
ren flytting av tekst, og refaktorering uten anledning innfører feil uten å
løse noe. André ba om den likevel, og da er den hans avgjørelse. Så den er
gjort med et sikkerhetsnett foran, ikke etter.

**Sikkerhetsnettet først.** Før en linje ble flyttet, tok jeg en fasit over de
182 + 95 toppnivåfunksjonene og de 25 + 22 toppnivåbindingene. Etter delingen:
samme antall, ingen mangler, ingen dubletter.

Delingen følger seksjonsmarkørene som alt sto i filene:

| Fil | Innhold |
|---|---|
| `vaktliste-kjerne.js` | Tilstand, tilgang, tid, henting, korpsvelger, nedtrekk |
| `vaktliste-tegning.js` | Tegning og byggere |
| `vaktliste-handlinger.js` | Handlinger og ressursroller |
| `vaktliste-offline.js` | Offline-køen |
| `vaktliste-register.js` | Mannskapsregisteret, korps og kompetanser |

**Den viktigste innsikten gjelder rekkefølgen, og jeg tok først feil om den.**
Jeg skrev i malen at «all toppnivå-tilstand står i kjernen». Det stemte ikke —
`STEMPLINGER`, `offlineTilstand` og ni andre lå i senere filer — og et krav
ingen holder er verre enn ingen. `let`/`const` på toppnivå er *skript-scopede*,
altså delt mellom filene, og en temporal dead zone treffes bare hvis noe
**kjører** før bindingen er nådd.

Den ekte regelen er derfor: **alt som kjører på toppnivå står i den siste
fila** — i praksis `DOMContentLoaded`-krokene. `core/tests_js_splitt.py`
håndhever den, sammen med at ingen funksjon er duplisert, at malens
`<script>`-rekkefølge stemmer med testenes, at de gamle samlefilene er borte,
og at ingen del er over 1 800 linjer. Uten den siste kunne én fil vokst tilbake
til 3 800 mens de andre sto tomme, med alt annet grønt.

Alle tre feilklassene er **prøvd mot mutasjoner**: en duplisert funksjon, et
kall lagt på toppnivå i kjernen, og to `<script>`-tagger byttet om. Alle tre
faller.

`VAKTLISTE_JS` og `OPPDRAG_SENTRAL_JS` i `js_test_utils` er nå **tupler**, og
`read_js()` skjøter dem. Det var grepet som holdt 62 testreferanser uendret —
for alt som leser kilden er de fortsatt én fil, som de er i nettleseren.

2709 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Gjeldspunkt 3.8: fem tester som målte kode, ikke oppførsel

Gjeldskartet sa «en del eldre tester grep-er etter kodelinjer». Da jeg gikk
gjennom dem, var de fleste treffene **legitime**: XSS-skannerne leser kilden
for å *finne* en bygger før de kjører den, CSP-testene måler rendret utdata, og
regler som «ingen mal peker på et CDN» har ingen kjøretid å måle. Skillet går
på hva assertionen påstår, ikke på om fila leses.

Fem påsto implementasjonstekst, og de er skrevet om:

| Var | Er nå |
|---|---|
| `assertIn("if (metode !== 'GET')", sw.js)` | `avgjor()` kjøres for POST, PUT, PATCH, DELETE, HEAD, OPTIONS |
| `assertIn('mannskap.sort(', kilde)` | Rekkefølgen i svaret, med rader uten rolle og navn i motsatt rekkefølge inn |
| `assertIn("classList.toggle('active-mine'", js)` | `toggleBoardMine()` kalles mot et minimalt DOM, to ganger |
| `assertNotIn('fjernRessurs', kilde)` | `mkRessurs()` tegnes, og markupen spørres |
| `assertIn("'…Middleware',\n", settings_py)` | `settings.MIDDLEWARE_I_DRIFT` |

Tre av dem ble **bedre**, ikke bare mindre skjøre. Service worker-testen dekket
før bare POST — nå PUT, PATCH og DELETE også, som den literale linja aldri
sjekket. Sorteringstesten kjører nå mot begge databasene og ville fanget et
databasealfabet som slapp gjennom. Og `fjernRessurs`-sjekken var en
*omdøpingssjekk*: den ville gått grønn om noen la en `data-action="slettRessurs"`
rett i kortet.

Hver av dem er prøvd mot feilen den skal fange, ikke bare kjørt grønn.

**Og så fant suiten en ekte flake — den jeg noterte som uavklart i går.**
`RateLimitPaaBrukeradminTests.test_sletting_strupes` feilet én gang av mange og
gikk grønt ved neste kjøring. Årsaken er ikke «flaky test» som forklaring, men
`django_ratelimit._get_window`: den legger vinduskanten et fast antall sekunder
inn i hvert minutt, jittret per nøkkel med `crc32`. Tolv forsøk mot `10/m` som
straddler den kanten deles i to bøtter der ingen når ti — altså ingen 429, og
testen faller.

Forsøkene er nå **2 × grensen + 1**. Da må den ene siden av en hvilken som helst
oppdeling bryte grensa, uansett når i minuttet testen kjører. Naboen i
`core/tests_ratelimit.py` hadde samme svakhet mot `10/5m` og er rettet likt.
Regelen står i `CLAUDE.md`.

---

## 2026-09-14 — Gjeldspunkt 3.1: kontoappen kjenner ingen modul ved navn

`accounts/forms.py` importerte `patients.models` for å tegne kortet
«Pasientregistrering» på brukersiden — kontoappen kjente altså én modul ved
navn. `core/kontokobling.py` er det tredje registeret på like mange timer, og
`PasientRolleForm` med malbiten sin bor nå i pasientmodulen.

**Koblingen er domenedata, ikke tilgang.** Den setningen står i kodetreet nå,
der den hører hjemme. Radioen satte en gang også `kan_redigere_pasienter`, og
sammenblandingen gjorde det umulig å være koblet som førstehjelper uten å ha
skrivetilgang. Samme skille som `Mannskap.user` i vaktlista.

`handling` — verdien i skjemaets skjulte `action` — må være **unik**, og
registeret avviser to handlere som deler den: viewet finner handleren på det
navnet, så to moduler med samme handling ville latt den ene lagre den andres
skjema, med «lagret» over noe helt annet.

**Et funn gjeldskartet ikke hadde:** `accounts` har en kobling til i samme
klasse. Velger admin kontotypen «bil», valideres enhetsnavnet i `forms.py` og
`oppdrag.Enhet`-raden opprettes — eller hentes fram igjen, om den er
pensjonert — i `views.py`. Det er samme slags avhengighet, men en annen form:
her er det *selve kontoopprettelsen* som får en sideeffekt i en modul, ikke et
skjema ved siden av kontoen. Å flytte den er kirurgi i brukeropprettelsen, og
hører ikke hjemme i samme runde som alt annet.

Avhengighetstesten dekker derfor nå **`accounts` og `audit` også** — de er
rammeverk de også (`TEKNISK_GJELD.md` §1) — med `KJENTE_UNNTAK_RAMMEVERK` som
sperrehake på de to `Enhet`-importene. `core`s egen liste står fortsatt tom.

2704 tester grønne.

---

## 2026-09-14 — To registre til: `core` kjenner ingen modul ved navn lenger

`KJENTE_UNNTAK` er tom. Den sto med fem rader i går kveld — de eneste stedene
rammeverket fortsatt importerte en modul — og begge er nå registre etter samme
idiom som `core/stats.py` fra i fjor.

**`core/driftstatus.py`.** Server-status viste hvilke vaktlister som var i
drift og hvor mange oppdrag som sto på tavla, ved å importere `vaktliste.models`
og `oppdrag.models`. Nå melder modulene seg inn fra `apps.ready()`.

Payloaden er **bit for bit den samme** — nøklene klienten leser er uendret, og
JS-en er ikke rørt. Det som endret seg er hvem som regner dem ut.

To egenskaper det var verdt å skrive tester for:

- **Én død modul tar ikke med seg dashbordet.** `samle()` fanger hver handler
  for seg; feilen havner i `error` med modulnavnet foran, vasket med
  `_scrub_secrets`, og de andre kortene tegnes. Et dashbord som selv gir 500
  fordi vaktlista har en treg spørring, er borte akkurat når man trenger det.
- **Standardnøklene settes i `core`, ikke i handlerne.** Er en modul av eller
  ikke registrert, skal kortet vise «–» og ikke forsvinne fra siden.

**`core/portalinnstillinger.py`.** Den vanskeligere av de to: portalens
innstillingsside hadde vaktlistas fire e-postfelter — markup, validering og
lagring — midt inne i rammeverkets view og mal. Nå registrerer modulen
`mal`, `kontekst()`, `valider()` og `lagre()`, og malbiten bor i
`vaktliste/templates/`.

`valider()` og `lagre()` er **delt i to med vilje**. Vaktas navn skrives på
`Vakt`, resten i `AppSetting`, og ingen transaksjon binder dem — todelingen er
det eneste som hindrer at en avvist innsending lagrer halve skjemaet. Viewet
validerer alle handlere *og* portalens egne felter før én eneste skriving skjer.
`core/tests_registre.py` prøver det med en handler som alltid nekter, og krever
at vaktas navn står urørt etterpå.

*Én test måtte rettes underveis, og det var testen som tok feil:* jeg antok at
`_scrub_secrets` vasker vilkårlige ord. Den vasker credentials i URL-er, som er
det den er til for. Prøven bruker nå en ekte connection-streng og krever
`[scrubbed]@` i svaret.

2699 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Flytting fase 4: adminflaten samlet, `core/views.py` delt, skimet slettet

Siste fase i flytterunden. Ingen migrasjon.

**`/portal-admin/` er ett sted** (gjeldspunkt 3.2). De 21 rutene lå i tre
filer — `myproject/urls.py`, `core/urls.py` og `accounts/urls.py` — og ingen
kunne se hele adminflaten uten å lete tre steder. Nå: `core/urls_admin.py`,
inkludert fra prosjektet.

**Og her var det en felle jeg gikk i.** Jeg tok et snapshot av rutekartet før
samlingen og sammenlignet etterpå: 21 ruter, identiske stier, identiske navn.
Men `pattern.name` er navnet **uten navnerom**, og `accounts` og `core` har
hver sin `app_name`. Kartet var «identisk» mens hver
`{% url 'accounts:user_list' %}` i malene var død. Viewtestene fanget det —
tre tester som tilfeldigvis rendret de riktige sidene.

To ting kom ut av det:

- **Adminflaten har nå ett navnerom, `portaladmin`.** 131 referanser i 25
  filer skiftet prefiks. Det samme skjermbildet het `accounts:user_list` eller
  `core:backup_admin` avhengig av hvilken app som tilfeldigvis eide viewet;
  nå er det flaten som bestemmer navnet.
- **`core/tests_malenes_urler.py`** leser hver `{% url %}` i hver mal og
  krever at navnet lar seg slå opp. Django feiler på en ukjent rute først når
  malen *rendres*, så en tagg inne i en `{% if %}` som bare vises for én rolle
  kan være død i måneder med suiten grønn. Testen fant fem med det samme:
  server-status-rutene hadde aldri hatt navnerom, så omskrivingen min traff
  dem ikke.
- **`core/tests_urls_admin.py`** låser hele kartet til literale verdier *med*
  navnerom, og rendrer hver GET-side under `/portal-admin/`. Lista er utledet
  av kartet, så en ny adminside dekkes i det øyeblikket ruta legges inn.

**`core/views.py` er delt i fire** (gjeldspunkt 3.7): `views_portal`
(dashbord, min profil), `views_admin` (innstillinger, moduler, auditlogg),
`views_backup` og `views_varsler`. 830 linjer og 24 views om alt fra backup til
varsler — samme grep `patients/views.py` fikk i N13.3.

**`accounts/decorators.py` er slettet** (gjeldspunkt 3.3). Den var en ren
re-eksport av `admin_required`, og den eneste leseren var testen som
verifiserte at den virket.

*Og slettingen avdekket at regelen sto brutt:* testen som skulle håndheve
«ingen produksjonskode importerer fra skimet» lette bare etter den absolutte
formen `from accounts.decorators import`. `accounts/views.py` brukte den
relative, `from .decorators import`, og slapp unna i et år med testen grønn.
En regel som bare dekker halve syntaksen måler noe annet enn den later som.

**Etterslep rettet samme dag:** «Tilgangskontroll»-bolken i `CLAUDE.md` beskrev
fortsatt `accounts/decorators.py` som et skim som beholdes fordi en test
verifiserer det. Fila er slettet. En arkitekturbeskrivelse som peker på noe som
ikke finnes, er verre enn ingen beskrivelse — den neste leter etter fila.

2691 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Flytting fase 3: scopet, middlewaren, helsesjekken og dashbordet

Ingen migrasjon — ren kodeflytting.

- **`core/vakt.py`**: `hent_aktiv_vakt` og `vakt_for_year`. De lå i
  `patients/services.py` fordi `AppSetting`-pekeren gjorde det, og da måtte
  oppdragsmodulen, vaktlista og statistikken importere *pasientmodulen* for å
  vite hvilken vakt de var i. Ingen av de to rører pasientdata.
- **`core/middleware.py`**: CSP-headerne, metrikkene og backupklokka. Ingen av
  dem er pasientspesifikke, og `settings.MIDDLEWARE` pekte dermed på en modul
  som kunne tas ut.
- **`core/health.py`** og **`core/admin_status.py`** med testene sine.

**Gevinsten, målt:** `core` importerer nå en modul på **fem** steder i
produksjonskode, mot rundt tjue før runden. Fire av dem er modulregisteret, som
skal navngi modulene sine — det er det et register er.

`core/tests_avhengighetsretning.py` låser det med AST, samme idiom som
`OppdragImportererIkkeVaktlista`. Uten en test er dette en intensjon, og
retningen snek seg feil vei én gang før.

**Et funn flyttingen gjorde synlig, og som er ekte gjeld:** `admin_status.py`
og portalinnstillingene importerer `vaktliste` og `oppdrag` — dashbordet viser
tall per modul, og innstillingene skriver vaktlistas e-postmottakere.
Koblingen fantes før flyttingen også, men da lå filene i `patients`, så den
leste som «modul → modul» og ikke som «rammeverk → modul». Riktig løsning er
den statistikkappen alt bruker: et register modulene melder seg inn i. Det er
en egen jobb med egen risiko og skal ikke ri på en flytterunde, så de fem
importene står i `KJENTE_UNNTAK` — en **sperrehake**: lista skal aldri vokse,
og en test krever at en importvei som ryddes tas ut av den.

2652 tester grønne på SQLite og PostgreSQL 16 (2684 med `myproject`).

---

## 2026-09-14 — Flytting fase 2: `AppSetting` og `Backup` til `core`

De to portalvide modellene har aldri vært pasientdata. De lå i `patients` fordi
den var første app og det ikke fantes noe annet sted — og resultatet var at
**rammeverket avhang av modulen**: `core.backup`, `core.arkiv` og `core.offsite`
importerte alle `patients.models`.

`core/0011` + `patients/0018`, begge `SeparateDatabaseAndState` med tom
`database_operations`. **Ingen SQL i det hele tatt.** `db_table` er bundet til
`patients_appsetting` og `patients_backup`, og det er et valg: Railway kjører
release-fasen *før* den bytter container, så en omdøpt tabell ville gitt 500 på
tilnærmet hver forespørsel i vinduet mellom `migrate` og byttet — `AppSetting`
bærer pekeren til aktiv vakt.

**En felle planen hadde plassert feil.** `AppSetting` lå i pasientbackupen fordi
pasienthandleren dumper `apps = ['patients']` og fikk modellen med på kjøpet.
Portalfila lister modellene sine ved navn, og planen la den raden i fase 4. Det
ville latt portalinnstillingene — aktiv vakt, lydvarslene, e-postmottakerne —
ligge utenfor **alle** backupfiler mellom de to deployene, uten at noe sa fra.
`core.AppSetting` er derfor lagt i portalfila i samme commit som flyttingen.

**Audit-loggen** (Andrés valg, vei 2): `EKSPLISITT_MAPPING` får
`patients_appsetting` og `patients_backup` → `core`. Uten dem ville utledningen
lest «patients» av tabellnavnet og merket hver framtidig rad med feil modul —
forvirringen flyttet fra kodetreet til loggen. Gamle rader endres ikke; bruddet
er datert.

Navnetabellen fra fase 1 fikk sine to rader, og **hele kjeden er prøvd mot ekte
PostgreSQL**, ikke bare i suiten:

- **Oppgraderingssimulering:** en base migrert med koden som står i prod i dag,
  seedet med innstillinger, backuprader og pasienter, så migrert med den nye.
  Alle rader intakt, FK-en til brukeren intakt, tabellnavnene uendret — og
  ingen tom `core_appsetting` ved siden av den fulle.
- **Gammel fil, ny kode:** en backup tatt med prod-koden bærer
  `patients.appsetting`. Gjenopprettet med den nye logger den «oversatte 2
  modellnavn fra en eldre fil», og radene kommer tilbake som `core.AppSetting`.
  Det er den prøven som svarer på om de 730 dagene med offsite-filer fortsatt er
  gjenopprettbare.

39 filer fikk nye importlinjer. To former skriptet ikke fanget, og som testene
gjorde: en flerlinjes import i parentes, og ett `apps.get_model('patients',
'AppSetting')` i `verifiser_vakt`. De samme oppslagene i *historiske*
migrasjoner står urørt med vilje — de løses mot tilstanden der modellen fortsatt
bodde i `patients`.

2647 tester grønne på SQLite og PostgreSQL 16, 3 migrasjonsprøver OK.

---

## 2026-09-14 — Flytting fase 1: navnetabellen, satt på plass før den trengs

`core.backup.oversett_modellnavn()` og `GAMLE_MODELLNAVN`. Tabellen er **tom**,
så fasen endrer ingenting i dag. Det er hele poenget.

En backupfil bærer modellnavnet — `{"model": "patients.appsetting", …}` — og
`loaddata` slår det opp i app-registeret. Flytter modellen til `core`, svarer en
fil tatt før flyttingen «Invalid model identifier» i stedet for å laste. Og
modulfilene ligger 730 dager hos Scaleway. Uten tabellen ville hver flytting
gjort hele arkivet av eldre filer ubrukelig i det øyeblikket koden ble deployet,
uten at noe sa fra: filene lastes jo opp som før.

Røret settes derfor på plass nå, før fase 2 fyller det. Gjøres de sammen, er
deployen som flytter modellene også den som først prøver oversettelsen — og
feiler den, viser det seg den dagen noen gjenoppretter.

Oversettelsen står **før** `_inspect_payload`, ikke rett før `loaddata`, slik at
kontrollen ser dagens modellnavn og slipper å kjenne begge.

**Rask vei:** er ingen av navnene å finne i bytene, returneres fila *identisk*
uten at JSON-en parses — testet med `assertIs`, ikke `assertEqual`, fordi en hel
databasefil ikke skal serialiseres fram og tilbake for en tabell som ikke har
noe å si.

Testene kjører mekanismen mot en **oppdiktet** flytting (`gammelapp.patient` →
`patients.patient`), siden den ekte ikke har skjedd ennå — med motprøven: uten
tabellen feiler nøyaktig samme fil med «Invalid model identifier:
gammelapp.patient», og gjenopprettingen rulles tilbake.

*Testen fant én inkonsistens i første utkast:* oppslaget var ufølsomt for store
bokstaver, men den raske veien var det ikke — et navn med store bokstaver ville
sluppet forbi uoversatt og feilet i `loaddata`, altså nøyaktig det tabellen
finnes for å hindre. Porten er nå like ufølsom, og prisen (én `bytes.lower()`)
betales bare når tabellen har rader.

Avklart samtidig: audit-loggens `app_label` mappes til `core` for de flyttede
tabellene i fase 2, rekkefølgen på fasene står, og `accounts/decorators.py`
slettes i fase 4.

2644 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Neste post planlagt: det portalvide ut av `patients`

`docs/PLAN_FLYTTING_TIL_CORE.md`. Trinn 2 i `PLAN_REKKEFOLGE_2026-09.md`, nå
som backupomleggingen er ferdig og prod har en gjenopprettbar backup foran den
migrasjonen som rører modellene.

**Lista har krympet siden kartleggingen 13. sep.** `BackupConfig`,
`backup_service.py` og `RETENTION_HOURS` er slettet i fase 8, `Lydvarsel`-hullet
falt ut da slettelista ble utledet, og `core.Vakt` fikk sin portalfil i fase 3.
Igjen står `AppSetting`, `Backup`, `hent_aktiv_vakt`, tre middlewarer,
`/healthz/` og server-status — 34 produksjonsfiler og 30 testfiler, nesten alt
importlinjer.

To funn planleggingen ga, som ikke sto i kartleggingen:

- **Tabellnavnene skal beholdes, og argumentet er nedetid.** Railway kjører
  release-fasen *før* den bytter container, så mellom `migrate` og byttet står
  gammel kode og serverer mot nytt skjema. En omdøpt `patients_appsetting` ville
  gitt 500 på tilnærmet hver forespørsel i det vinduet — tabellen bærer pekeren
  til aktiv vakt. Kartleggingen anbefalte også å beholde, men på kosmetisk
  grunnlag.
- **Audit-loggens `app_label` utledes av tabellnavnet** (`split('_', 1)[0]`).
  Beholder vi navnene, står hver framtidig auditrad for portalinnstillingene som
  «patients» selv når modellen bor i `core` — forvirringen flyttet fra kodetreet
  til loggen. Tre veier ut, anbefaling i notatets §3.2, og valget er Andrés fordi
  det handler om hva han ser i filteret.

**Fella som styrer faserekkefølgen:** backupfilene bærer modellnavnet
(`"model": "patients.appsetting"`), og en fil tatt før flyttingen lar seg ikke
laste etterpå — `loaddata` svarer «Unknown model». Filene lever 730 dager
offsite. Navnetabellen bygges derfor i **fase 1**, der den er en no-op, slik at
den er i prod og prøvd før fase 2 fyller den. Gjøres de sammen, oppdages en feil
i tabellen den dagen noen gjenoppretter.

---

## 2026-09-14 — Prefiksrutingen låst: `full/` kan ikke bli `backups/` i stillhet

André, etter deployen: «Hele databasen heter `backup-full-auto-…`, mens modulene
heter `backup-<modul>-…`. Vil det fungere med `full/` og `backups/`?»

Ja — det er to ulike prefikser. `backup-` er del av *filnavnet*, og bærer slugen
så `slug_fra_filnavn()` kan lese den tilbake når man henter. `full/` og
`backups/` er *objektnavnet*, altså mappa, og det er den livssyklusreglene
filtrerer på. De to har ingenting med hverandre å gjøre.

Men spørsmålet pekte på noe ekte: `prefiks_for()` sammenligner mot strengen
`'full'` direkte, ikke mot `Backupplan.FULL_SLUG`. Avveiningen er grei — den
slipper å importere modeller inn i `offsite.py` — men den etterlater slugen
skrevet to steder som må endres samtidig.

**Og de to feiler ulikt.** Døper noen om den hele fila i modellen uten å røre
`offsite.py`, går ingenting i stykker med det samme: filene lastes opp som før,
bare til `backups/`. Da lever hele databasen — med passordhasher og
TOTP-hemmeligheter — i 730 dager i stedet for 90. Ingenting feiler, ingen logg
sier fra, og kortet på backup-siden ser riktig ut: reglene *står* jo som de
skal, det er filene som ligger feil sted. En personvernbeslutning endret av en
navneendring.

`PrefiksRutingTests` låser fire ting: at `prefiks_for(FULL_SLUG)` gir `full/`,
at hver **registrert** handler (registeret er fasit, ikke en liste i testen)
ruter dit den skal, at filnavnet leser tilbake til samme prefiks som
opplastingen brukte — opplastingen får slugen som argument, hentingen leser den
av navnet, og blir de uenige lastes fila opp ett sted og letes etter et annet —
og at de to prefiksene ikke er forstavelser av hverandre, for da ville én regel
truffet begge og fristene ikke latt seg skille.

*Prøvd mot feilen de påstår å fange*, ikke bare kjørt grønne: med slugen endret
i `offsite.py` faller to av dem med «filene ville havnet under backups/ og fått
730 dagers oppbevaring i stedet for 90», og med `PREFIKS_FULL` satt til
`backups/full/` faller overlapp-testen.

2634 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Migrasjonsprøve for Backupplan, før prod

Før omleggingen går til prod: en prøve som kjører `core/0008`–`0010` mot ekte
PostgreSQL **med rader i basen**, i den historiske formen.

Det er den ene tingen verken suiten eller `makemigrations --check` svarer på.
Djangos testbase lages ved å kjøre migrasjonene mot en *tom* base, så
dataskrittet i `0009` finner ingenting å oversette, skriver ingenting, og går
grønt uten å ha gjort noe. Feilen som tok ned release-fasen 30. august krevde
PostgreSQL **og** rader — og en backup-omlegging som crash-looper release-fasen
er den verst tenkelige tida å oppdage det på.

Prøven seeder de seks tilstandene som betyr noe: en modul som er på, en som
står av via `enabled=False`, en som står av via `interval_minutes=0` (to måter
å si det samme, og begge finnes), og intervaller som går opp i timer, døgn og
ikke i det hele tatt. Den sjekker oversettelsen, at ingen rad forsvant, at
`behold` overlevde omdøpingen, at standardplanen ble opprettet, og at de gamle
kolonnene faktisk er borte etter steg 3.

**Og den viktigste påstanden: ingen eksisterende rad arver standardplanen.**
Gjorde de det, ville oppgraderingen endret hvor ofte prod tar backup uten at
noen ba om det — og det ville vist seg som en fil som ikke kom.

*Funn underveis, om prod snarere enn om koden:* første utkast av prøven
kolliderte på `patients`, fordi `core/0002` og `0005` selv oppretter de radene.
Prod har dem altså allerede — seedet av migrasjoner, noen av dem siden redigert
i grensesnittet — og seeden bruker nå `ON CONFLICT DO UPDATE` for å ligne på
det.

3 av 3 prøver grønne mot PostgreSQL 16.

---

## 2026-09-14 — Backup fase 8: den gamle veien er stengt

Siste fase i backupomleggingen, og den eneste som bare fjerner ting. Tre
levninger fra før `core.backup` er slettet, og migrasjonen er `patients/0017`.

**`patients/backup_service.py`** var en tynn proxy som het seg å være
bakoverkompatibilitet. Problemet var ikke at den var død kode — den ble brukt,
av vaktavslutningen og av testene. Problemet var signaturen: `create_backup()`
uten slug, med «patients» bakt inn. Etter fase 4 er slugen hele forskjellen på
en pasientfil og en hel database, og et kall som ikke nevner den har ingen måte
å ta feil på synlig vis. `core.backup.create_backup(slug=...)` krever den som
førsteargument, og det er nå den eneste veien inn.

**`db_backup`** het som om den tok hele databasen og tok pasientmodulen. Den
sto i `CRON_JOBBER` til 13. sep. uten noen gang å ha vært satt opp i Railway —
og det var flaks, for et volum kan bare henge på én tjeneste, så en
cron-tjeneste uten `/data` ville skrevet fila til et flyktig filsystem og
etterlatt en `Backup`-rad uten fil. Klokka er en tråd i web-prosessen
(`core/backup/klokke.py`), og `backup_kjor` er den manuelle inngangen.

**`patients.BackupConfig`** var én singleton for hele portalen: ett intervall,
valgt fra fem faste verdier. `core.Backupplan` er per modul, med tre moduser og
fritt intervall. Verdiene ble kopiert over allerede 13. sep. av
`core/0002_modulebackupconfig`, så det er ingen data å ta vare på her.

**`RETENTION_HOURS = 72`** ble aldri lest av noe. Oppryddingen er
antallsbasert (`Backupplan.behold`, cap på filer *på volumet*), og hvor lenge
kopien lever offsite er bucketens livssyklusregel — to helt forskjellige ting.
En konstant som beskriver en tredje, ikke-eksisterende regel er verre enn ingen.

`LegacyBackupErBorteTests` håndhever at ingen av de tre kommer tilbake, og at
`create_backup` fortsatt krever slug. Testen finnes fordi hver av dem ville
kommet tilbake som en bekvemmelighet, ikke som en feil noen la merke til.

**Om migrasjonen:** den avhenger av `core/0002`, som gjør
`apps.get_model('patients', 'BackupConfig')` i et `RunPython`-steg. Prøvd uten
avhengigheten: Django la dem i riktig rekkefølge likevel, fordi `core/0002`
selv peker på `patients/0005`. Kanten står der for at rekkefølgen skal være
skrevet i stedet for et sammentreff i grafen. Ren skjemaendring — ingen
`RunPython`, ingen triggerkø, ingen prøve i `core/migrasjonsprover.py`.

2630 tester grønne på SQLite og PostgreSQL 16. **Backupomleggingen er ferdig:
alle åtte fasene er levert.**

---

## 2026-09-14 — Backup fase 7: oppbevaringstidene, og et kort som leser dem tilbake

Fristene offsite håndheves av **Scaleway, ikke av oss**. Portalens IAM-nøkkel
har ikke sletterett, og `enforce_cap` rører bare volumet — livssyklusreglene i
bucketen er dermed den eneste mekanismen som noen gang sletter en offsite-kopi.

André satte reglene i konsollen 14. sep. 2026: `backups/` 730 dager for
modulfilene, `full/` 90 dager for den hele databasen. Regelen sto til da på
«alle objekter i bucketen», og måtte snevres inn til `backups/` **før** regelen
på `full/` ble lagt til: to regler som treffer samme objekt er et sted å gjette.

**Kortet på `/portal-admin/backup/` leser nå reglene tilbake fra bucketen** og
sammenligner dem med beslutningen (`core.offsite.livssyklus()`,
`FORVENTET_DAGER`). Det er ikke pynt. Sammenligningen er på **nøyaktig**
prefiks, fordi den feilen man faktisk gjør er `/full` i stedet for `full/` — en
regel som ser riktig ut i konsollen og treffer ingenting. Da blir filene
liggende for alltid, og det eneste som sier fra er at noen leser
`get-bucket-lifecycle-configuration` for hånd. Nå står avviket i rødt ved siden
av backupene, hver gang noen er på siden.

Fem tilstander kortet skiller mellom, fordi de har ulik årsak og ulikt svar:
regelen mangler, regelen står på feil prefiks, regelen er slått av, regelen har
feil antall dager, og bucketen har ingen regler i det hele tatt
(`NoSuchLifecycleConfiguration` — «filene blir liggende for alltid», ikke en
lesefeil). Mangler nøkkelen `ObjectStorageBucketsRead`, står det «ukjent» med
årsaken, ikke et falskt grønt.

`livssyklus()` **kaster aldri**, og cacher svaret i fem minutter: et kort som
selv gir feil når nettverket er nede, er borte akkurat når man trenger det, og
et S3-kall per sidelasting er et kall for mye.

2627 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-13 — Backup fase 6: `verifiser_backup`

En backup ingen har gjenopprettet er en hypotese. Suiten har hatt en test som
gjenoppretter alle filene i rekkefølge siden fase 3, men den bruker syntetiske
data og svarer på om *koden* virker. `verifiser_backup` tar **filene som
faktisk ligger på volumet**, laster dem inn i en engangsbase, og sammenligner
radene mot det filene inneholder — modell for modell.

Den rører ingenting. Alt skjer i en flyktig SQLite-fil i en midlertidig mappe
som slettes etterpå, og backupfilene kopieres dit først, så
pre-restore-øyeblikksbildene gjenopprettingen lager havner i søpla og ikke
blant de ekte backupene.

**Den kaller `gjenopprett`, ikke `restore_backup`.** Da er det kommandoen man
faktisk ville kjørt i en katastrofe som er prøvd, ikke en nabo til den.

To ting den lærte underveis, begge om å ikke lyve:

- **En tom fil er ikke en bestått prøve.** Første kjøring sa «6 modeller kom
  tilbake» om et sett der arkivfilene ikke inneholdt en eneste rad. Nå står det
  hvor mange objekter hver fil har, og en tom fil får en egen advarsel: enten er
  modulen tom, eller så ble fila tatt før dataene fantes.
- **Gjenopprettingen skriver sin egen auditrad**, og i den hele fila er
  `audit.AuditLog` med i slettelista. Basen skal altså ha én rad *mer* enn fila,
  og det er riktig. Sammenlignet strengt meldte prøven avvik på noe som
  fungerte akkurat som det skulle — og en prøve som roper ulv blir ikke lest
  neste gang.

`PORTAL_ENGANGSBASE=1` er en ny, navngitt åpning i `settings.py`: sjekken som
ellers nekter SQLite på Railway slipper engangsbasen gjennom, så kommandoen kan
kjøres **der filene er**, uten en ekstra databaseserver og uten å lage baser ved
siden av produksjonsdata. Flagget settes av den ene kommandoen og skal aldri stå
på en tjeneste.

Testene kjører ekte underprosesser mot en ekte engangsbase — tregere enn resten
av suiten, og det er poenget: det er nettopp underprosessen og filstien som skal
prøves. Én av dem ødelegger en fil med vilje og krever at prøven ser det; uten
den ville «alt kom tilbake» bare betydd «noe kom tilbake».

Runbooken §8b sier når kommandoen skal kjøres: etter første backup i en ny vakt.

Verifisert: 2618 tester grønne på SQLite og PostgreSQL 16, og kommandoen kjørt
mot ekte filer — normalveien, den hele fila, en ødelagt fil og en tom.

---

## 2026-09-13 — Backup fase 5: gjenoppretting fra kommandolinja

`manage.py gjenopprett` finnes nå. Veien fantes ikke før: `hent_offsite` henter
og dekrypterer fila, men rører ikke databasen — siste linje den skrev var
«gjenopprett fra /portal-admin/backup/». I en tom base, som er akkurat der man
er når man trenger den, er det ingen å logge inn som. Katastrofeveien gikk
altså gjennom en nettleser uten bruker.

`--list` viser filene på volumet, `--siste <modul>` tar den nyeste og hopper
over pre-restore-øyeblikksbildene (de er tilstanden man nettopp gikk bort fra),
og `--hent <objekt>` henter fra Scaleway og gjenoppretter i ett. Samme funksjon
som knappen kaller: samme pre-restore-øyeblikksbilde, samme auditrad.

**`--ja` er nødvendig, ikke bekvemt.** `railway ssh -- <kommando>` kjører uten
interaktiv terminal, så et `input()` ville hengt til noe ga opp — uten at det
sto hvorfor, i en katastrofe. Kommandoen ser etter terminalen og sier hva som
mangler i stedet for å vente. **`--full` kreves** når fila er hele databasen:
slugen leses av filnavnet, så flagget er teknisk overflødig, men brukere,
passord og MFA skal ikke kunne erstattes av en skrivefeil.

**Auditraden er flyttet fra viewet inn i `restore_backup`**, med en kilde-tekst
(«grensesnittet» / «kommandolinja»). Sto den i viewet, ville katastrofeveien
vært den eneste gjenopprettingen som ikke etterlot seg et spor. Begge
inngangene gir nå nøyaktig én rad — verifisert av en test som ville fanget både
den manglende og en dobbel.

`slug_fra_filnavn` er flyttet til `core.backup.service`, ved siden av
`_build_filename` som bygger navnet. Den sto i `core/offsite.py` og leste en
form som defineres et annet sted; nå blir begge feil samtidig om formen endres,
i stedet for hver for seg.

Runbooken §8b har fått hele katastrofeprosedyren: den korte veien gjennom den
hele fila, den lange gjennom modulfilene i bindende rekkefølge (portal først,
fordi alt peker på vakta), og at `purge_old_logs` og `kollaps_arkiv` skal kjøres
rett etterpå — backupen har egen slettefrist, og det som var slettet i basen
skal ikke komme tilbake.

Verifisert: 2608 tester grønne på SQLite og PostgreSQL 16, og kommandoen er
kjørt mot en ekte base: sperrene slår ut som de skal, gjenopprettingen henter
dataene tilbake, og auditraden står med kilde.

---

## 2026-09-13 — Backup fase 4: hele databasen i én fil

Katastrofekopien finnes nå. `core/backup/full.py` dumper alt i databasen unntatt
sesjoner, contenttypes, permissions, `admin.LogEntry` og backup-metadata.
Brukere med passordhasher, MFA-enheter, tilganger, audit- og innloggingslogg,
vakta og alle modulenes data er med — fila er **selvbærende**, og
fremmednøkler til kontoer strippes derfor ikke slik modulfilene gjør.

**Appene listes ikke opp for hånd.** `collect_apps()` regner dem ut fra
app-registeret ved hvert kall, så en ny modul er med fra dagen den finnes. En
hardkodet liste ville vært en ny sjanse til å glemme noe, og en katastrofekopi
som stille mangler en app er verre enn ingen — fordi man tror man har den.

**Eget prefiks offsite.** `full/` ved siden av `backups/`, fordi
livssyklusreglene i bucketen filtrerer på sti og 90 dager ikke kan skilles fra
730 uten. `hent_offsite` utleder prefikset av slugen i filnavnet, så man trenger
ikke vite hvor fila ligger.

**Bevist i en tom PostgreSQL-base:** hele basen tilbake fra den ene fila —
brukere, MFA-enheter, audit, vakt, pasienter, oppdrag, mannskap og vaktposter,
alle tall like — og innlogging med det opprinnelige passordet virker etterpå.
En gjenoppretting man ikke kan logge inn etter, er ingen gjenoppretting.

**Funnet som stoppet den første kjøringen var en eksisterende feil.** Ingen av
de atten lagringssignalene i portalen så etter `raw=True`. Django sender det når
`loaddata` skriver en rad, og det betyr «denne raden kommer fra en fil, ikke fra
noen som gjorde noe». Uten vakten fyrte audit-signalene under hver eneste
gjenoppretting, og de leser relaterte objekter for å skrive hva som ble endret.
I den hele fila kommer et `Vaktpost` før sitt `Mannskap`, og gjenopprettingen
stoppet med «Mannskap matching query does not exist». Modulenes gjenopprettinger
feilet ikke, men skrev **én auditrad per lastet rad** — tusen pasienter tilbake
ga tusen «endret»-rader uten en bruker som hadde endret noe.
`audit.utils.ikke_under_loaddata` er vakten nå, lagt på alle atten,
og `SignalerFyrerIkkeUnderLoaddataTests` krever den også av neste mottaker.
Selve gjenopprettingen logges fortsatt, av viewet, med hvem som gjorde den.

Gjenopprettingsbekreftelsen sier hva som skjer: brukere, passord, MFA, tilganger
og logger erstattes, kontoer opprettet etter backupen forsvinner, og **kontoen
du er logget inn med byttes ut underveis** — var passordet et annet da backupen
ble tatt, blir du logget ut med det samme.

`CLAUDE.md`-avsnittet om backup er skrevet om: sju handlere,
gjenopprettingsrekkefølgen, den utledede slettelista, `raw`-vakten, de to
prefiksene og at det ikke finnes nedlasting.

Verifisert: 2592 tester grønne på SQLite og PostgreSQL 16.

**Krever André før dette er i prod:** livssyklusregelen på `full/` (fase 7).
Uten den lander de første hele backupene under 730-dagersregelen.

---

## 2026-09-13 — Backup fase 3: vaktlista dekket, og slettelista utledes

**Vaktlistemodulen hadde ingen backup i det hele tatt.** Korps, mannskap med
telefon, e-post og ISSI, kompetanser, ressursgrupper og -roller, ressursene,
vaktpostene, vaktlistene og belastningsgrensene lå utenfor alle fire filer siden
appen gikk i prod 11. september. Det er samme feil oppdragsmodulen hadde fram
til sin fase 7, og den er ikke synlig noe sted før dagen man trenger filene.
`vaktliste/backup.py` dekker den nå, med bruker-FK-ene strippet — `Mannskap.user`
er domenedata lederen setter på nytt, mens en slettet konto ville tatt hele
gjenopprettingen med seg.

**Portalfila er ny og er den de andre hviler på.** `core.Vakt` og
`ModuleSettings` i én fil, først i rekkefølgen. `Backupplan`, `OffsiteKopi` og
`Notification` er utelatt: de to første er metadata *om* backup, og å laste dem
tilbake ville gjenopplive rader for filer som ikke finnes.

**Slettelista utledes nå topologisk** fra `apps` minus `exclude`, barn før
foreldre, og de fire håndskrevne listene er slettet. Utledningen traff alle fire
og fant den ene kjente feilen: **`Lydvarsel` — gjeldspunkt 3.4 — er dekket uten
at noen måtte huske den.** `SlettelistaDekkerDumpenTests` håndhever at hver
modell som dumpes også tømmes, så feilen ikke kan komme tilbake gjennom en ny
modell eller en ny modul. Én ting måtte håndteres underveis: `apps`-lista kan
peke på enkeltmodeller og ikke bare apper, slik arkivhandlerne gjør, og
utledningen må lese lista på samme måte som `dumpdata` gjør.

**Gjenoppretting i tom base er bevist, ikke påstått.** Alle seks filene lastet i
rekkefølge i en fersk PostgreSQL-base — portal → patients → arkiv → oppdrag →
oppdrag_arkiv → vaktliste — og hver rad kom tilbake. Motprøven er like viktig:
uten portalfila feiler alle tre modulfilene med «Key (vakt_id)=(1) is not present
in table core_vakt», som er nøyaktig hullet `docs/TEKNISK_GJELD.md` §4 beskrev.
`AlleFileneGjenopprettesTests` gjør den samme øvelsen i suiten, så den blir
stående.

Modulen `arkiv` heter nå **«Pasientregistreringsarkiv»**. «Vaktarkiv» sa ikke
hva den er, og oppdrag har sitt eget arkiv ved siden av.

Verifisert: 2582 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-13 — Backup fase 2: alt på én side

`/portal-admin/backup/` er nå hele backup-flaten. Oversikten, én side per modul
og veien mellom dem er lagt ned.

**Det som var tungvint, målt:** å ta backup av alt kostet fire runder gjennom
tre sider; å gjenopprette kostet fem steg. Nå står standardplanen øverst, og
hver modul er en rad som folder seg ut der den står med plan, knapper og
filliste i samme boks. «Ta backup av alle nå» er én knapp. «Gjenopprett siste»
dekker det man vil i ni av ti tilfeller.

**Gjenopprettingen beholdt sin egen bekreftelsesside.** Den er ikke det som var
tungvint — den er den ene handlingen her som sletter rader, og skal koste et
bevisst klikk. Men den sier nå **hvor mange rader i hvor mange tabeller** som
forsvinner. «Slett og erstatt» er et annet svar når man ser at det gjelder 1 240
rader i ni tabeller.

**Nedlastingsknappene er fjernet helt**, også for modulfilene: backupfilene skal
ikke finnes andre steder enn hos Scaleway eller på Railway. Argumentet mot å
laste ned den hele fila — passordhasher og TOTP-hemmeligheter til en laptop — er
like gyldig for pasientfila, som er en helseopplysningsdump utenfor portalens
kontroll.

**«Verste tilfelle nå»** står øverst, per modul, og er målt mot siste
*vellykkede opplasting til Scaleway* — ikke mot siste fil på volumet. Er volumet
borte, er det bare bucketen som teller, og en linje som leste volumet ville vist
fire minutter mens den virkelige avstanden var to dager. Uten offsite
konfigurert sier kortet det selv framfor å påstå noe det ikke vet.

**Vakthunden har fått flate:** rødt på backup-siden, egen linje på
`/portal-admin/server-status/` ved siden av cron-jobbene (ikke blant dem — klokka
er ingen cron-jobb), og et varsel til global admin. Varselet sendes **bare fra
reservenettet i middlewaren**, aldri fra tråden: et varsel om at klokka er død,
sendt av klokka, er et varsel som aldri kommer. Reservenettet kjører i en
forespørsel, altså i live, og oppdager derfor nettopp det tråden ikke kan melde
om seg selv. Det varsler heller ikke om planer som aldri er vurdert — «har aldri
kjørt» og «har sluttet å kjøre» er to tilstander, og bare den andre er en feil.

**Funn underveis, fanget av et skjermbilde og ikke av suiten:** `{# … #}` er en
**enlinjes** kommentar i Django. Strekker den seg over flere linjer, rendres den
som tekst midt i grensesnittet — malen er gyldig, testene passerer, ingenting
logges. Den sto både i den nye malen og i `templates/accounts/user_form.html`
fra før. Begge rettet til `{% comment %}`, og
`patients.tests.FlerlinjesMalkommentarTests` skanner nå alle maler så den ikke
kan komme tilbake.

Verifisert: 2563 tester grønne på SQLite og PostgreSQL 16, og siden er kjørt i
Chromium — lagring av standardplan og modulplan, et avvist intervall med lesbar
melding, «ta backup av alle» og gjenopprettingsbekreftelsen.

---

## 2026-09-13 — Backup fase 1: `Backupplan`, og klokka ut av trafikken

Første kode i omleggingen (`docs/PLAN_BACKUP_OMLEGGING.md` fase 1).

**`core.Backupplan` erstatter `ModuleBackupConfig`.** Tre moduser — av, ved
endring, alltid — og intervallet settes **fritt i minutter, timer eller døgn**,
der det før var et nedtrekk med sju faste valg. Enheten lagres slik den ble
valgt: «3 døgn» skal ikke leses tilbake som «4320 minutter». `behold` er cap på
filer på volumet, og gjelder like mye for moduler som for hele basen når den
kommer. En standardplan modulene arver gjør tre tall av atten.

**Modusen «alltid» er ny og er poenget med runden.** «Ved endring» skriver ikke
når innholdet står stille, og er dermed *stum*: ingen ny fil kan bety «ingenting
har endret seg» eller «jobben er død». `create_backup` fikk `hopp_over_like`, så
«alltid» skriver uansett og et hull i rekka er en synlig feil. I tillegg bærer
planen nå **to** tidsstempler — `sist_sjekket_at` ved hver vurdering,
`sist_fil_at` bare når noe faktisk ble skrevet — og det er de to som gjør at
«stille» og «stoppet» kan skilles i alle moduser.

**Klokka er flyttet ut av trafikken og inn i en tråd.** Fram til nå var
`BackupSchedulerMiddleware` den eneste utløseren, så uten forespørsler ble det
ingen backup — og mellom vaktene står portalen stille. Tråden starter fra
`CoreConfig.ready()` og tikker hvert minutt uavhengig av trafikk, med jitter så
gunicorn-arbeiderne ikke banker samtidig, samme radlås som før, og opprydding av
foreldreløse filer ved oppstart. Middlewaren står igjen som reservenett gjennom
samme funksjon.

**Og den er en tråd, ikke en cron-tjeneste, fordi volumet bare kan henge på én
tjeneste.** En cron-tjeneste som tok backup ville skrevet fila til sitt eget
flyktige containerfilsystem og etterlatt en `Backup`-rad uten fil — og
`core.arkiv.har_backup_etter()` spør bare etter raden, så **kollapssperra ville
åpnet seg på spøkelsesbackuper**. Det var flaks at `db_backup` aldri ble satt
opp i Railway (bekreftet av André: bare `purge_old_logs` og `kollaps_arkiv`
kjører). `db_backup` er tatt ut av `CRON_JOBBER` uten erstatning — server-status
viste «Aldri» for en jobb som aldri kom, og et varsel som alltid står rødt lærer
deg å ikke se på dashbordet. `CLAUDE.md` er rettet fra tre cron-jobber til to.

**Én regel til det gikk å ta feil av:** forfall måles mot `sist_sjekket_at`, ikke
mot `sist_fil_at`. Målt mot siste fil ville en plan i «ved endring» vært forfalt
ved hvert eneste tikk etter første «uendret» — altså serialisert hele modulen
hvert minutt for å bekrefte stillstand. Intervallet sier hvor ofte vi ser etter,
ikke hvor ofte vi lykkes.

`backup_kjor` er ny manuell inngang (`--status`, `--alle`, `--modul`), og
`klokke.vakthund()` melder planer som ikke er vurdert på tre ganger intervallet
— svaret på at en tråd ikke er synlig i Railways grensesnitt slik en cron-jobb
er. Flata for den kommer i fase 2.

Migrasjonen er delt i **tre** (skjema, data, skjema) framfor å tømme triggerkøen,
så `cannot ALTER TABLE … because it has pending trigger events` ikke kan oppstå.
Eksisterende rader settes til «egen plan» og beholder oppførselen sin: å la dem
arve standarden ville endret hvor ofte prod tar backup uten at noen ba om det.

Verifisert: 2557 tester grønne på SQLite og på PostgreSQL 16,
`verifiser_migrasjoner` OK, og en oppgraderingssimulering mot ekte PostgreSQL
der fire rader i historisk form — inkludert en modul admin hadde slått av — ble
migrert fram og kom ut med oppførselen i behold.

---

## 2026-09-13 — Backup-planen versjon 3: klokka blir en tråd, ikke en cron-jobb

Ingen kodeendring. På spørsmål om cron er den ideelle klokka ble fire alternativer veid,
og svaret er nei — av en grunn som først ble synlig da filene ble fulgt til der de
skrives.

**Et Railway-volum kan bare henge på én tjeneste.** `/data` henger på web-tjenesten. En
cron-tjeneste som kjørte `backup_kjor` ville serialisert riktig, skrevet fila til sitt eget
flyktige containerfilsystem, opprettet `Backup`-raden, og forsvunnet med fila. Raden ville
blitt stående og påstått at det finnes en backup. Og `core.arkiv.har_backup_etter()` —
sperra som skal hindre at et arkiv kollapser uten at slettingen er gjenopprettbar — spør
bare etter raden, ikke etter fila. **Kollapssperra ville altså åpnet seg på
spøkelsesbackuper.** Det var flaks at `db_backup` aldri ble satt opp i Railway.

De to jobbene som faktisk står der, rører bare databasen og trenger ikke volumet. Det er
hele forskjellen.

Klokka blir derfor en daemon-tråd startet fra `CoreConfig.ready()`, i prosessen som
faktisk eier volumet: ett tikk i minuttet, jitter så workerne ikke banker samtidig, samme
radlås som før, og den starter ikke under test eller `migrate`. Web-tjenesten står oppe
mellom vaktene — lavkostnad-modus er én worker uten Redis, ikke en pauset tjeneste — så
klokka går hele året. `backup_kjor` beholdes som manuell inngang, `db_backup` går ut av
`CRON_JOBBER` uten erstatning, og `CLAUDE.md` rettes fra tre cron-jobber til to.

Innvendingen mot en tråd er at den ikke er synlig noe sted. Svaret er en vakthund: er en
plan ikke sjekket på tre ganger intervallet, står det rødt på begge adminsidene og det
opprettes et varsel. Cron er riktig verktøy for å *sjekke* og feil verktøy for å *gjøre* —
en ren vakthund-cron kan komme senere, siden den bare leser databasen og dermed overlever
at web-tjenesten ligger nede.

**Nedlasting fjernes helt**, også for modulfilene: filene skal ikke finnes andre steder enn
hos Scaleway eller på Railway. Knappen ble bare brukt til å se hva som er inni en fil, og
den jobben gjør `verifiser_backup` bedre, på serveren. Argumentet mot å laste ned den hele
fila — passordhasher og TOTP-hemmeligheter til en laptop — er like gyldig for pasientfila,
som er en helseopplysningsdump utenfor portalens kontroll.

Bucketen heter `sanitetsportalen`, og står nå i instruksen og runbooken. Planen har ingen
åpne punkter.

---

## 2026-09-13 — Backup-planen versjon 2: svarene innarbeidet

Ingen kodeendring. André svarte på de fem spørsmålene, og planen er skrevet om.

**Intervallet settes fritt i minutter, timer eller døgn**, med enheten lagret slik den ble
valgt — «3 døgn» skal ikke leses tilbake som «4320 minutter». Cap på antall filer gjelder
både moduler og hel database, med standard: moduler ved endring hvert 10. minutt og cap
50, arkivene hver 6. time, hel base alltid hver 24. time og cap 7.

**Tilpasning til den enkelte vakt løses med modusen, ikke med to intervaller.** «Ved
endring» med kort intervall er vaktadaptiv av seg selv: under vakt endres dataene hele
tiden og det skrives en fil hvert intervall, mellom vaktene skrives ingenting. To
intervaller med automatisk omslag ble vurdert og lagt bort — `Vakt.er_aktiv` står på til
noen avslutter vakta, vaktlistas driftsflagg ville vært feil vei i avhengighetene, og en
manuell vaktbryter er den man glemmer å slå av.

**Siden viser hva som faktisk står på spill:** «verste tilfelle nå» per modul, målt mot
siste *vellykkede offsite-kopi* og ikke mot siste fil på volumet. Er volumet borte, er det
bare bucketen som teller, og en linje som leser volumet ville vist fire minutter mens den
virkelige avstanden var to dager.

**Gjenoppretting får en CLI-vei.** Den finnes ikke i dag: `hent_offsite` henter og
dekrypterer, men skriver «gjenopprett fra /portal-admin/backup/». Ny `gjenopprett`-kommando
med `--list`, `--full`, `--hent` og `--ja` — flagget er nødvendig, ikke bekvemt, fordi
`railway ssh` kjører uten interaktiv terminal.

**To fakta fra André som endrer planen:** `db_backup` står **ikke** i Railway, så prod har
aldri hatt en klokkedrevet backup — alt som er tatt, er utløst av web-trafikk. Og
livssyklusregelen i bucketen står på 730 dager med scope «alle objekter», så den må
snevres inn til `backups/` før 90-dagersregelen på `full/` legges til, og det må skje før
den første hele backupen lastes opp.

Ett spørsmål står igjen: skal den hele fila kunne lastes ned fra nettleseren. Anbefaling
nei — nedlasting og gjenoppretting er ulike ting, og bare den ene flytter portalens
legitimasjon til en laptop.

---

## 2026-09-13 — Backup-omleggingen planlagt: `docs/PLAN_BACKUP_OMLEGGING.md`

Ingen kodeendring. Bestillingen var at modulenes backup og gjenoppretting er tungvint, at
intervallet skal kunne settes fritt med valget mellom konsekvent lagring og lagring ved
endring, at det samme skal gjelde en hel databasebackup, og at oppbevaringstidene i
Scaleway skal skilles: 90 dager for hele basen, 730 for modulene.

Planen i sju faser: `core.Backupplan` med tre moduser og fritt intervall erstatter
nedtrekket med sju valg, en standardplan modulene arver, og `backup_kjor` som
Railway-cron blir klokka. Én side i stedet for en side per modul. `get_restore_models()`
utledes topologisk, med test som krever dekning. Hel backup med `flush` + `loaddata` og
eget prefiks `full/`. `verifiser_backup` laster de nyeste filene i en engangsbase, fordi
en backup ingen har gjenopprettet er en hypotese.

Tre funn under lesingen av koden: **klokka er trafikk** — uten forespørsler tas ingen
backup, så «konsekvent lagring hvert tidsintervall» er ikke mulig med dagens mekanisme;
**`db_backup` er en felle** — den står i `CRON_JOBBER` og `CLAUDE.md` sier den er én av
tre Railway-jobber, men tabellen i TODO lister to, og kommandoen går uansett gjennom det
nedlagte `patients/backup_service.py` og tar bare pasientmodulen; og **`restore_models`
vedlikeholdes for hånd**, som er sykdommen bak gjeldspunkt 3.4.

Rekkefølgen komprimering → kryptering står fast, mot bestillingens «kryptering og så
komprimering»: chiffertekst lar seg ikke komprimere, mens gzip på dumpdata-JSON typisk
gir 5–15 % av rå størrelse. Dagens kode gjør det riktig allerede.

---

## 2026-09-13 — Strategisk plan for rekkefølgen: `docs/PLAN_REKKEFOLGE_2026-09.md`

Ingen kodeendring. På spørsmål om hva som bør tas først av teknisk gjeld, backup,
datteroppdrag og statistikk-utvidelsen: **backuphullene først** (vaktlista er udekket og
offsite-kopiene kan ikke gjenopprettes i tom base), **så flyttingen ut av `patients`**
(med gjenopprettbar backup foran migrasjonen), så hel backup og dokumentrunden. De to
funksjonene står etter: begge er blokkert på avgjørelser fra André, og oppdragsmodulen
har ikke hatt sin første skarpe vakt. Notatet begrunner avviket fra `BACKUP.md` §3 (det
som ikke rører `AppSetting` kan bygges før flyttingen), anbefaler å beholde tabellnavnene
ved flyttingen, og at statistikk-utvidelsen bygges som A- og B-nivå med F4-lasttest før,
og lar C/D vente. TODO har fått en henvisning under «Teknisk gjeld».

---

## 2026-09-13 — Forslag: datteroppdrag, og `docs/` ryddet

Ingen kodeendring. `docs/FORSLAG_DATTEROPPDRAG.md` er et idénotat (ikke besluttet):
ett oppdrag deles i datteroppdrag, ett per pasient — `Oppdrag.forelder` med dybde låst
til ett nivå, pasientantall bare på bladene, `forelder_nummer` i arkivet bare når satt.
Hva det gir i loggen og statistikken, hva det koster, og det ene spørsmålet
sentralbordet må svare på først. Står i TODO under «Ideer».

`docs/` gjennomgått: `DATAIMPORT_FRA_GAMMEL_PROD.md` (utført 22. aug.) og
`OPPSETT_KOLLAPS_CRON.md` (jobben har gått siden 22. aug.) er flyttet til
`docs/archived/` med indekslinjer, og lenkene til dem oppdatert. Beslutningsnotatene
blir stående — de forklarer hvorfor. `DEPLOY_GUIDE.md` og `TEKNISK_DOKUMENTASJON.md` er
utdaterte, men aktive, og står i dokumentrunden i TODO.

## 2026-09-13 — Backup-planen: `docs/BACKUP.md`

Ingen kodeendring. Besluttet: **to lag med hver sin frist** — en hel backup (alt unntatt
sesjoner, kryptert, 90 dager, få filer) som katastrofekopi, og modulfilene som i dag med
730 dager, fordi kollapsen krever dem. Portalfil med `Vakt` og innstillingene,
`vaktliste`-handler, og en test som gjenoppretter alle filene i en tom database.
Slettefristene er begrunnet mot A.9 (egen kategori, forholdsmessig, slettingen kjøres
på nytt etter gjenoppretting). Rekkefølgen er bindende: flyttingen ut av `patients`
først. Dokumentrunden etterpå tar med alt fra 11.–13. september — lista over hva som
mangler hvor står i §5, og i `TODO.md`.

## 2026-09-13 — Teknisk gjeld kartlagt: `docs/TEKNISK_GJELD.md`

Ingen kodeendring. På spørsmål om hva backupene faktisk inneholder, og hvordan appen
henger sammen, ble appene, modellene, importene på kryss, middlewaren og rutene gått
gjennom. Notatet beskriver rammeverk-pluss-moduler-tanken, den store gjelden —
`patients` er den gamle monolitten, og `core` avhenger av den (`AppSetting`, `Backup`,
`hent_aktiv_vakt`, CSP, `healthz`, server-status) — åtte mindre punkter, og hullene i
backupen: `core.Vakt` ligger ikke i noen fil (gjenoppretting i tom base feiler),
vaktlista har ingen handler, og «Vaktarkiv» skal hete «Pasientregistreringsarkiv».
Arbeidslista står i `TODO.md` under «Teknisk gjeld», med bindende rekkefølge:
flyttingen først, backupene etterpå.

## 2026-09-13 — Prodtest av sikkerhetsrundene: fire funn rettet

Ingen migrasjon. Andrés prodtest på staging av runde 1 og 2 ga 39 OK og 0 FEIL i
scriptet, og fire ting på sidene:

- **Fanikonet er merket på blått igjen** (`logo.svg`, samme fil som PWA-ikonet).
  Den lyse utgaven uten bakgrunn fra 12. sep. er tatt bort («Jeg bruker mørk modus
  og det er en mørk blå bakgrunn som var der før. Jeg vil ha det slik det var.»).
  `Clear-Site-Data` står på 302-svaret fra «Logg ut» og var riktig — det er
  innloggingssiden DevTools viser etterpå.
- **Sentralbordet ved første besøk** (3.1): «Laster…» sto tomt. Oppstarten var fire
  kall på rad uten feilhåndtering — feilet ett, tegnet ingen noe, og pollingen ble
  aldri satt. `oppstart()` tegner nå listene uansett («Kunne ikke hente lista —
  prøver igjen om 30 sekunder» til første henting lykkes; tom og ikke hentet er to
  ulike ting), og `setInterval` står i `finally`.
- **Bilen: «venter på dekning» først etter 3 sekunder** (3.4). Trykket legges i
  køen før det sendes, og meldingen kom opp i det halve sekundet sendingen tok —
  også med full dekning. `visUsendt()` venter til eldste rad i køen er
  `USENDT_VENTETID_MS` gammel, og kommer tilbake av seg selv når fristen er ute.
- **Korps-føreren uten badge** (4.1): admin koblet fra hennes egen mannskapsrad, og
  sida sa «Mannskapsregisteret er tomt» — meldingen leste lista over dem hun får
  *sette* (tom uten badge), ikke registeret hun *ser* (alle korps). Nå leser den
  registeret (`registeretErTomt`), og sida sier hvorfor hun ikke får redigere:
  «Kontoen din er ikke knyttet til et korps. Du ser alle korps, men kan bare føre
  ditt eget» (`mangler_badge`). Varselet fantes bare for `les`.
- **E-postkoblingen er leder og global admin** (M5, snevret): `skriv_full` lagrer
  e-posten uten å koble, som korps-føreren. Den som bemanner skal ikke velge
  hvilken konto som blir hvem; merket sier at kontoen finnes, og lederen kobler.
  `tests_registre` og `tests_sikkerhet_runde1` bruker `skriv_leder` der de
  forutsatte kobling.

Tester: `oppdrag/tests_prodtest_13sep.py` (oppstarten og fristen, i node) og
`vaktliste/tests_prodtest_13sep.py` (badge-varselet, koblingen, `registeretErTomt`).

## 2026-09-13 — Sikkerhetsgjennomgangen, runde 2: 9 funn rettet

Ingen migrasjon. Numrene viser til `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.

- **H3 — bibliotekene inn i repoet.** Bootstrap 5.3.2, Bootstrap Icons 1.11.3,
  Tabulator 6.2.5 og Chart.js 4.4.2 ligger under `static/vendor/` (fra npm,
  uten kartreferanser, med lisens og `README.md` om oppdatering) og serveres av
  WhiteNoise. Alle tretten malene peker dit. CSP-en har ingen verter lenger:
  `script-src 'self' 'nonce-…'`, `style-src 'self' 'unsafe-inline'`,
  `font-src 'self' data:`. Service-workerens CSP er `'self'`, `CDN`-lista er tom
  og `VERSJON` bumpet til `vl-sw-4`. `tests_security_headers` krever at ingen mal
  laster fra et CDN.
- **M12 — trust-cookien** signeres med egen `salt` og bærer et passordavtrykk:
  bytter eller nullstilles passordet, må enheten godkjennes på nytt. Cookies
  fra før i dag avvises, så alle med «stol på denne enheten» tar MFA én gang til.
- **M13** — passordskjemaene får brukeren, så «kan ikke ligne brukernavnet»
  håndheves. **M14** — hasheren kjøres også for låste kontoer, og «kontoen er
  låst» vises bare for den som har riktig passord; alle andre får «feil
  brukernavn eller passord». Låsen i seg selv er uendret (5 feil, 15 min) — den
  er det ene vernet som ikke hviler på cachen.
- **M15** — `LocMemCache` går fra 200 til 5000 poster. **L1** —
  `SlankReporterFilter` skjuler alle cookies i Djangos reserve-feilrapport
  (`DEFAULT_EXCEPTION_REPORTER_FILTER`).
- **M16 — avhengighetene er låst.** `requirements.in` bærer ønskene,
  `requirements.txt` er `pip-compile --generate-hashes --strip-extras` (25
  pakker, 471 hasher). `pip-audit`: ingen kjente sårbarheter. Railway
  installerer nå nøyaktig det som er testet.
- **L13** — `@rate_limit` på resten av skriveendepunktene: verdimengdene,
  bilinnstillinger, arkivering og sletting i begge arkiver, vaktlistas detalj-
  PUT/DELETE (vaktliste, gruppe, ressurs, vaktpost, mannskap, registre),
  pasientregistrene, backup run/restore, arkiv-statistikk, brukeradmin.
  Eksisterende bremser dekker nå også DELETE der den fantes.
- **L14** — `admin_required` merker viewet, og `core/tests_sikkerhet_runde2.py`
  går gjennom alt under `/portal-admin/`, `/varsler/`, `/api/varsler/` og
  `/min-profil/` med anonym og vanlig bruker.
- 19 nye tester i `*/tests_sikkerhet_runde2.py`.
- **Rettelse samme dag:** `.gitignore` hadde `vendor/`, så bibliotekfilene ble aldri
  commitet, og første deploy til staging ga 500 på alle sider («Missing staticfiles
  manifest entry»). `!static/vendor/` i `.gitignore`, og en test som krever at filene
  er sporet av git.

## 2026-09-13 — Sikkerhetsgjennomgangen, runde 1: 19 funn rettet

Ingen migrasjon. Numrene viser til `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.

- **H1 — data inn i `<script>` escapes.** `core/jsdata.js_json()` bytter `<`, `>`
  og `&` med `\u003c`/`\u003e`/`\u0026` som Djangos `json_script`; de fjorten
  variablene på `/oppdrag/` går gjennom den, og malene har ikke lenger `|safe`.
  Et problemstillingsnavn kan ikke lukke skriptet.
- **H2 — klient-IP ett sted.** `core/klientip.klient_ip()` tar *siste* ledd i
  `X-Forwarded-For` (Railway er én betrodd proxy), validerer det, og faller
  tilbake til `REMOTE_ADDR`. Brukt av innloggingsloggen, alle tre audit-signalene,
  begge arkivviewene, sesjonsverktøyet og — som `ratelimit_nokkel` — bøttene
  `login:ip` og `reset:ip`, som fram til nå talte på proxyens adresse.
- **H4 — «Logg ut» rydder drifts-PC-en.** `logout_view` sender
  `Clear-Site-Data: "cache", "storage"` (Cache Storage, localStorage og
  service-workeren i ett; cookies røres ikke). Workeren serverer heller ikke en
  datakopi eldre enn 24 timer (`erForGammel`), og sletter den.
- **M1** — riktig passord nullstiller ikke kontolåsen for kontoer med MFA; det
  skjer først når koden er bestått. **M2** — innloggingsskjemaet valideres før
  noe skrives (et brukernavn over 64 tegn ga 500 på PostgreSQL). **L5** —
  MFA-stegene krever aktiv konto. **M11** — `current_session_key` skrives etter
  at passordbyttet har rotert sesjonen. **L11** — sidene med midlertidig passord
  har `never_cache`.
- **M7** — «Rediger» kan ikke ta admin-rollen fra deg selv (`_kan_degraderes`),
  og `is_active` er ute av skjemaet: frys/tø er veien som logges og dreper
  sesjoner.
- **M3** — besetningsendepunktet krever at man ser alle korps eller har
  `oppdrag:les`; en ren `vaktliste:les` får 403. **M5** — e-postkoblingen
  utløses bare av admin og `skriv_full`+; korps-føreren lagrer e-posten, og
  merket sier at kontoen finnes.
- **M4** — bilens detalj-, stemplings-, grovsorterings- og antall-endepunkt
  følger 30-minuttersvinduet (`_synlig_for_bilen`). **M6** — enhetskontoer får
  403 på enhetslista, flytting og verdimengdene.
- **M8** — de tre JSON-parserne gir tom dict for gyldig JSON som ikke er et
  objekt. **M9** — audit-CSV prefikser `=`, `+`, `-`, `@`, tab og CR med `'`.
  **M10** — `nivaa_for(admin)` er toppen av stigen (`skriv_leder`), ikke
  `skriv_full`. **L2** — `patient_detail_view` er scopet til aktiv vakt.
  **L3** — `offsite.hent` avviser objektnavn med katalogskilletegn før S3
  kalles. **L10** — `ALLOWED_HOSTS` strippes, og `SECRET_KEY` under 50 tegn
  stopper oppstarten når `DEBUG=False`.
- 46 nye tester i `*/tests_sikkerhet_runde1.py`; `tests_besetning` oppdatert
  til den nye regelen.

## 2026-09-13 — Sikkerhetsgjennomgang: rapport

`docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`. Statisk gjennomgang i fire deler, hvert
funn verifisert mot koden. Ingen kritiske. Fire høye: lagret JS-injeksjon gjennom
verdimengdene i oppdrag (`json.dumps` + `|safe`, og CSP-vertslista slipper det gjennom),
klient-IP lest på tre ulike måter (rate-limit per IP teller på proxyen, auditsporets IP
er klientstyrt), CDN uten SRI, og service-workerens kopi av mannskapsregisteret som
ingenting rydder ved utlogging. Seksten middels, 22 lave, og en foreslått rekkefølge i
tre runder. Ingen kode er endret i denne commiten.

## 2026-09-13 — Sikkerhetssjekk utenfra: `scripts/sikkerhetssjekk.py`

**Rettelse etter første kjøring mot staging:** Cloudflare sender hodenavn med små
bokstaver (`location`), og WhiteNoise hasher `oppdrag-enhet.js` — scriptet meldte 65
falske FEIL. Hodene normaliseres nå, og enhetsskjermen gjenkjennes på navnet uten hash.

Et script som kjøres fra en PC mot staging (runbook §14). Bare standardbiblioteket.
Anonymt: HTTPS-omdirigering, HSTS, CSP, X-Content-Type-Options, rammesperre,
Referrer-Policy, cookieflagg, 64 sider og API-er som skal være stengt uten
innlogging, 14 skriveendepunkter uten CSRF, rate-limiting på innlogging, egen
404, Django-admin og kjente filer. Med `--admin/--leser/--enhet`: rollegrensene,
sesjonsfiksering, utlogging med POST, at gammel sesjons-ID dør, og konfigsjekken
fra server-status. Kjørt lokalt mot en dev-server som kontroll av selve scriptet.

## 2026-09-13 — Rate-limiting var av i prod: `RATELIMIT_ENABLE=true` ble lest som False

Funnet av konfigsjekken på server-status, første kvelden den var oppe: kortet sa
`RATELIMIT_ENABLE: False`, Railway sa `true`. `settings.py` leste variabelen med
`== 'True'` — stor T — mens README, runbook og Railway skrev `true`. Dermed har
rate-limitingen på innlogging, MFA og API-ene vært **av** i prod så lenge
variabelen har stått slik.

- `_env_bool(navn, default)` i `settings.py` leser boolske variabler uavhengig
  av store og små bokstaver (`1/true/yes/on/ja` er ja, alt annet nei, tom eller
  manglende gir default). Brukes for `DEBUG`, `RATELIMIT_ENABLE` og
  `EMAIL_USE_TLS` — alle tre hadde samme feil. `DEBUG=true` ga False, som var
  ufarlig; `EMAIL_USE_TLS=true` ga False, som ville skrudd av TLS mot SMTP
  (brukes bare lokalt).
- `myproject/tests_env_bool.py` låser regelen.
- Ingen migrasjon. Etter deploy skal konfigsjekken vise `RATELIMIT_ENABLE: True`
  uten at noe endres i Railway.

## 2026-09-13 — Server-status: ni nye mål på /portal-admin/server-status/

Ingen migrasjon. Gjennomgangen av dashbordet etter reserve 3 fant at det målte
serveren, men ikke det serveren er til for, og at ett tall var galt.

- **Minne viste toppen, ikke nå.** `ru_maxrss` går aldri ned, så kortet kunne
  bare stige. Nå leses RSS fra `/proc/self/status`, med toppen som egen rad.
- **Offsite-kopien** står i backup-kortet: konfigurert/ikke, antall filer, sist
  lastet opp, siste feil. Rødt når siste opplasting feilet, gult over ett døgn.
- **Disk på volumet** (`BACKUP_DIR`): brukt/ledig og hvor mye backupfilene tar.
- **Database:** svartid på `SELECT 1`, og på PostgreSQL tilkoblinger mot
  `max_connections` — feilen som kommer først når `WEB_WORKERS` skrus opp.
- **Vaktbildet:** aktiv vakt, vaktlister i drift, oppdrag på tavla, ventende,
  «trenger ressurs» med eldste ventende i minutter, og siste vaktlistefil.
- **Tregeste stier siste 5 min** — P95 per sti, under tre treff utelatt
  (`metrics_store.tregeste_stier()`), så «P95 er høy» blir «det er den siden».
- **Konfigsjekk:** DEBUG, RATELIMIT_ENABLE, HTTPS, ALLOWED_HOSTS,
  CSRF_TRUSTED_ORIGINS, cache, e-posttransport, ADMINS, offsite — hver rad ✓/✗,
  pluss versjon. Reglene er prods; lokalt står DEBUG og HTTPS rødt med vilje.
- **Innlogging siste time:** feilede forsøk, hvor mange brukernavn og IP-er de
  kom fra, avviste MFA-koder. Én IP bak fem feil markeres rødt.
- **Cron-jobbenes siste kjøring** — jobbene registrerer seg selv via
  `lesbar_dbfeil(..., navn=...)` → `AppSetting['cron.<navn>']`, ok eller feil
  med melding (`core.kommando.registrer_kjoring`/`siste_kjoringer`). Gult når
  `db_backup`/`purge_old_logs` er over 26 timer gamle, `kollaps_arkiv` over 8
  døgn. «Aldri» til jobben har kjørt én gang etter denne deployen.
- **E-post:** transporten (AHASend/SMTP/konsoll) og siste vellykkede og feilede
  utsending av vaktlistefila. Ingen prøvesending fra et kort som polles hvert
  10. sekund.
- Hver innhenter tåler at delen den leser er nede — kortet viser feilen, siden
  viser resten. Payloadnøkkelen `memory_mb` er byttet ut med `memory.naa/topp`.
- **Feature-flagg-kortet er fjernet**, med `feature.live_stats_enabled`,
  endepunktet `/portal-admin/server-status/flag/` og testene (André: «Den
  trenger vi ikke»). Funksjonen det skulle styre ble aldri bygget. Runbook §6
  står som «utgått» så §7 og oppover peker riktig.
- Verdiene i konfigsjekken brekker inne i kortet (`overflow-wrap: anywhere`,
  høyrestilt) i stedet for å gå utenfor — gjelder alle `status-row`-verdier.

## 2026-09-13 — Runbook §8b: offsite-backup — oppsett, kontroll og gjenoppretting

Dokumentasjon. Oppsettet hos Scaleway og i Railway, kontrollen før hver vakt,
og gjenopprettingen med `hent_offsite`, inn i `docs/RUNBOOK_VAKT.md` som §8b.
10a og lenketabellen peker dit.

## 2026-09-13 — Reserve 3: backupene ut av Railway, til Scaleway

Én migrasjon, `core/0007` (`OffsiteKopi`). To nye avhengigheter: `boto3` og
`cryptography`. Inert uten variablene — bare prod skal ha dem.

- **Hver ny backup-fil lastes opp til Scaleway Object Storage**, kryptert
  før den forlater Railway (AES-256-GCM, nøkkel avledet av
  `OFFSITE_BACKUP_KEY`). Henger på at `create_backup` faktisk skrev en ny fil;
  hash-skip gir ingen opplasting. Ingen egen klokke.
- **Kaster aldri:** feiler bucketen, står backupen på volumet som før, og
  raden `OffsiteKopi` bærer feilen. Kortet «Offsite-kopi (Scaleway)» øverst på
  /portal-admin/backup/ viser status, siste opplasting og siste feil.
- **Gjenoppretting:** `python manage.py hent_offsite --list` og
  `hent_offsite <filnavn>` henter, dekrypterer og legger fila i `BACKUP_DIR`
  med en `Backup`-rad, så den kan gjenopprettes fra backup-siden.
- Variabler: `OFFSITE_S3_BUCKET`, `OFFSITE_S3_REGION`, `OFFSITE_S3_ENDPOINT`,
  `OFFSITE_S3_ACCESS_KEY`, `OFFSITE_S3_SECRET_KEY`, `OFFSITE_BACKUP_KEY`.
- Scaleway inn i personverndokumentasjonen A.2 som databehandler, med DPA.

## 2026-09-13 — Reserve 2 og 4: offline drift på /vaktliste/, gammel offline-modus lagt ned

Ingen migrasjon. Deployes til staging først; testes i Chrome/Edge på PC.

- **Service worker for `/vaktliste/`** (`static/js/vaktliste-sw.js`, servert av
  `/vaktliste/sw.js`): holder siden, stilene, skriptene og siste svar fra
  vaktliste-API-et lokalt. Svarer ikke serveren, vises kopien, med banner «viser
  lista slik den var kl …». Innloggingssiden lagres aldri som kopi.
- **Møtt/av vakt i kø** når serveren ikke svarer: stemplingen vises som satt
  (merket), legges i `localStorage` med tida trykket skjedde, og sendes i
  rekkefølge hvert 15. sekund og når nettet kommer tilbake. Serveren tar
  tidspunktet fra køen (`stempling/` leser `tidspunkt` i kroppen;
  `services.vurder_klienttid` klipper urimelige). Et trykk serveren avviser
  fjernes med beskjed.
- **Utgått innlogging** stopper køen og sier fra i banneret; den sendes etter
  ny innlogging i en annen fane.
- **«Klar for offline»** i vaktlinja når workeren styrer siden og lista ligger i
  kopi — sjekket, ikke antatt.
- **Den gamle offline-modusen er lagt ned:** `OFFLINE_MODE`, CSRF åpen for LAN,
  `ALLOWED_HOSTS=*`, Django-admin under offline, `create_offline_users`,
  `.env.offline.example`, `OFFLINE_PASSORD.md` og USB-pakken. Django-admin
  rutes nå bare under `DEBUG`. `import_offline_data` står igjen som
  importverktøy for den gamle appens SQLite. Dokumentasjonen (teknisk §11,
  personvern A.11, runbook) er skrevet om til den nye reserven.

## 2026-09-13 — Reserve 1b: intervallsending mens lista er i drift

Én migrasjon, `vaktliste/0017` (`Utsending.innhold_sha256`, ny utløser
«intervall»). Deployes til staging først.

- **Send på nytt hvert N. minutt mens lista er i drift**, satt under
  Portalinnstillinger → «Vaktlista på e-post». 0 = av. Klokka går fra forrige
  utsending uansett hva som utløste den, så et feilet forsøk gir ikke ett nytt
  per minutt mens e-posten er nede.
- **«Bare hvis vaktlista er endret siden forrige utsending»**: fila får en
  signatur over innholdet, og en uendret liste går ikke ut igjen. Stemplene
  (møtt/av vakt) står ikke i fila og teller ikke som endring.
- Kjøres av `vaktliste.middleware.FilutsendingMiddleware` etter trafikk, maks
  én sjekk i minuttet per prosess, i bakgrunnstråd — samme klokke som
  backup-planleggeren. Tas ut under test, som den.

## 2026-09-12 — Reserve 1: vaktlista som fil på e-post

Én migrasjon, `vaktliste/0016` (`Utsending`). Deployes til staging først.

- **Vaktlista som selvstendig HTML-fil**: grupper, ressurser og skift med korps,
  rolle, telefon og ISSI. Ikke e-post, notat eller merknad. Åpner uten nett og
  skrives ut fra nettleseren. «Last ned som fil» og «Send på e-post» i
  «Innstillinger» på vaktlista, for `skriv_full`.
- **Sendes automatisk ved «Sett i drift»** når admin har slått det på og satt
  mottakere. Feiler e-posten, åpner innsjekken likevel, og vaktleder får feilen.
- **Mottakere og bryteren** settes av global admin under Portalinnstillinger →
  «Vaktlista på e-post». Adressene valideres før noe lagres.
- **Hver utsending logges**: `Utsending`-rad og auditrad med hvem, når, hvilke
  adresser og antall skift. Teksten i «Innstillinger» sier hva som skjedde sist.
- AHASend-transporten sender vedlegg (base64, v2-formatet). Første vedlegg som
  går gjennom den — bekreftes på staging.
- Vurderingen av ukryptert sending står i vaktlistenotatet §12.

## 2026-09-12 — ISSI på mannskapet, telefon og ISSI i sentralbordets besetning

Én migrasjon, `vaktliste/0015` (`Mannskap.issi`). Deployes til staging først.

- **ISSI** (nødnettsterminalens nummer) på hver person i mannskapsregisteret,
  etter telefon og e-post: kolonne i tabellen, felt i skjemaet, søkbart.
  Tekst, så ledende nuller overlever.
- **Sentralbordets besetning viser telefon og ISSI per person** på koblede
  enheter. Telefonen er en `tel:`-lenke. §6 i vaktlistenotatet er snudd
  for telefon: operatøren skal kunne ringe bilen uten å åpne vaktlista.
  Kompetanse, notat, e-post og konto er fortsatt ikke med.

## 2026-09-12 — Statistikk: chi²-merket bryter på iPhone

Ingen migrasjon. «✗ N.S. (χ²=12.0, p=0,062)» gikk utenfor kortet i
krysstabellene og på obspost; merket får nå bryte, og tittel og merke står
på hver sin linje når det ikke er plass til begge.

## 2026-09-12 — Vaktliste: skift, ressurser og stemplene i auditloggen

Ingen migrasjon. Deployes til staging først.

- **Skift logges på feltnivå** (`vaktliste_vaktpost`): opprettet, hver
  feltendring med gammel og ny verdi, og slettet — med hvem og når.
  Møtt/av vakt og angringene er feltendringer på `mott_at`/`av_vakt_at`, og
  får dermed sitt spor. `merknad` logges som endret, uten verdier, som
  `Mannskap.notat`.
- **Ressurser logges** (`vaktliste_ressurs`): opprettet, endret, slettet.
  Slettes en ressurs, får hvert skift som ryker med sin egen rad.
  Kopiert oppsett går nå én rad om gangen, så kopiene logges.

## 2026-09-12 — Prodtest runde G–I, del 3: iPhone-rettelser

Ingen migrasjon. Deployes til staging først.

- **Alle statistikktabellene ruller sidelengs** på en smal skjerm, i
  pasientfanen som i oppdragsfanen. Beholderne bærer klassen `stats-rull`
  i malen; ingen inline-stiler lenger.
- **Vaktlinja på telefonen:** statusmerket («Planlegging · 12.09 08:00 –
  13.09 20:00») gikk utenfor kortet — spennet bryter nå til linja under
  formen. Vaktvelgeren tar bredden, og «Innstillinger»/«Ny vaktliste» står
  alltid sist på egen linje, så korpsvelgeren ikke havner et sært sted i
  liggende visning.

## 2026-09-12 — Prodtest runde G–I, del 2: lyd per hastegrad, ett trykk, Drift

Én migrasjon, `oppdrag/0025` (`Lydvarsel.aktiv`). Deployes til staging først.

- **Ventevarselet kan slås av per hastegrad** i fanen «Bilen»: en avkryssing
  per rad. Rører ikke pipet ved nytt oppdrag, som ikke er per hastegrad.
- **«Behandlet på sted» lukker med Ledig i samme trykk.** Serveren skriver
  Behandlet og Ledig med samme tidspunkt (`services.behandle_paa_sted`);
  Ledig-meldingen er målt, ikke automatisk, så statistikken teller
  oppdragstiden. Udefinert stopper alt før noe skrives.
- **Drift har ingen grovsortering:** raden i bilen og merket hos operatøren
  er borte for Drift. Serveren krevde den aldri der.
- Statistikk: tabellene ruller sidelengs på iPhone i stedet for å gå ut av
  kortet.

## 2026-09-12 — Prodtest runde G–I: lyd, grovsortering, iPhone

Ingen migrasjon. Deployes til staging først.

- **Lyd på som standard, med dempeikon** i bilen (per enhet, husket lokalt)
  i stedet for «alltid på uten valg». Linja «trykk hvor som helst» er
  dempet tekst, ikke en gul boks, og forsvinner etter første trykk.
- **Admin kan slå lydvarselet av** for alle biler, i fanen «Bilen» i
  «Valglister» (het «Lydvarsel»). Endepunktet heter `api/bilinnstillinger/`.
- **iOS med lydbryteren på stille:** Web Audio dempes av bryteren; bilen
  starter en stum, loopende lydfil ved første trykk og ber om
  «playback»-lydøkt, som er omveien som finnes. Ingen garanti fra Apple.
- **Grovsortering kreves** før «Behandlet på sted» og før Ledig etter
  Leverer — alltid, unntatt på Drift. Før Avreist bare når admin har slått
  det på («Krev grovsortering også før Avreist»). Bilen får beskjeden idet
  hun trykker; serveren avviser uansett.
- Statistikk: «På stedet» heter «Behandlet på stedet».
- iPhone: gruppeoverskriftene i «Nytt oppdrag» tar hele linja igjen.

## 2026-09-12 — Andrés forbedringsliste, del I: lydvarselet

To migrasjoner, `oppdrag/0023` (tabellen `Lydvarsel`) og `0024` (seed med
første utgaves tall). Data og skjema hver for seg. Deployes til staging
først.

- **Lyden er alltid på.** «Lyd av/på»-knappen er borte. Nettleseren krever
  fortsatt et trykk før lyd får spille; en gul linje øverst sier «trykk hvor
  som helst» til det første trykket har vekket den, og et ikon ved klokka
  viser tilstanden.
- **Lengre varsel:** Akutt seks toner på tre sekunder, Haster fire, Vanlig
  og Drift tre rolige. Aldri over tre sekunder.
- **Admin justerer tersklene** per hastegrad — første varsel og gjentakelse
  i sekunder — i ny fane «Lydvarsel» i «Valglister» (bare global admin), og
  om bilen skal pipe når den får et nytt oppdrag. Bilen henter tallene hvert
  femte minutt.
- **Pip ved nytt oppdrag:** to stigende toner når et ventende oppdrag dukker
  opp i bilens liste, ikke for det som lå der da siden åpnet.
- **Utheving hos operatør:** på sentralbordet pulserer raden i gult når et
  oppdrag har ventet forbi første terskel på at bilen skal rykke ut, regnet
  fra da den første ventende bilen ble varslet.

## 2026-09-12 — Andrés forbedringsliste, del H: bilens utganger

Én migrasjon, `oppdrag/0022`: statusvalg og hendelsestyper, og kolonnen
`behandlet_at` på arkivrader. Ren skjemaendring. Deployes til staging først.

- **«Behandlet på sted»** er en ny status fra Fremme: pasienten ble ferdig
  der bilen sto, ingen transport. Neste er Ledig. Statistikken regner tid på
  stedet fram til behandlet, og arkivet får kolonnen — i signaturen bare når
  den er satt, så eldre arkiv verifiserer som før.
- **«Avbryt» i Rykker ut** der Ledig sto: enheten meldes ledig, og oppdraget
  går tilbake til Venter hos sentralen som «trenger ny ressurs», med
  «Avbrutt: HGSD 56» i tidslinjen. Bilen spør om bekreftelse først.
- **Ingen Ledig mellom Avreist og Leverer.** Bilen melder Ledig bare fra
  Leverer og Behandlet, og den egne Ledig-knappen er borte: Ledig er «neste»
  der. Sentralen fører og retter som før, fra alle statuser.

## 2026-09-12 — Andrés forbedringsliste, del G: vaktlista

Ingen migrasjon. Deployes til staging først.

- **«Sett i drift» ligger i «Innstillinger»**, i bolken for lista, med en
  linje som sier hva knappen gjør. Statusmerket i vaktlinja er større:
  ikon, «Planlegging»/«I drift» i fet, og i drift en pulserende grønn prikk.
- **Redigering under drift som i planlegging.** Driftraden er regnearket
  med innsjekken foran — tider, rolle, kompetanse og merknad rettes der de
  står. Tabellen ruller sidelengs på en laptop; stempelet står først.
- **Drift inn og ut står i auditloggen**, på feltnivå med hvem som gjorde
  det (`vaktliste_vaktliste`: status, satt i drift når/av, planlagt slutt,
  arkivert).
- **Knappene med grå kant** (`btn-outline-secondary`, «Innstillinger» m.fl.)
  har lys tekst og portalens kantfarge på alle portalsider.
- **Én innlogging per konto** har stått siden N10 — logger kontoen inn et
  nytt sted, ryker den forrige økta. Nå låst av tester fra utsiden.

## 2026-09-12 — Feilvarsel: `django`-loggeren bruker vår e-posthandler

En skanner (leakix) prøvde `testportal.sanitet.net` mot staging, fikk 400
på hver forespørsel — og hver forespørsel ble en e-post med **full
Settings- og META-dump**, rundt hundre på fem minutter.

- **Årsak:** Django konfigurerer sin egen `DEFAULT_LOGGING` før vår, og en
  logger vi ikke nevner beholder handlerne derfra. `django.request` var
  vår, men `django.security.DisallowedHost` propagerte til `django`, som
  fortsatt hadde Djangos AdminEmailHandler — uten demping og uten den slanke
  rapportøren. Den slanke rapporten var altså bare i bruk for uhåndterte
  exceptions i views.
- **Rettet:** `django` står nå i LOGGING med vår handler,
  `django.security.DisallowedHost` går bare til konsollen (Djangos egen
  anbefaling — feil Host-header er skannere, ikke feil hos oss), og
  e-posthandleren har `require_debug_false` som Djangos.
- Ikke rettet i kode: staging-tjenesten har prods `ALLOWED_HOSTS` og en
  `CSRF_TRUSTED_ORIGINS` med en skrivefeil (`/ https://*.railway.app`). Se
  TODO.

## 2026-09-12 — «Valglister», og fanene i mørkt

- Knappen og vinduet «Verdier» heter **«Valglister»** (André: «noe annet
  bedre beskrivende»), med undertittelen lokasjoner, enhetstyper og
  problemstillinger.
- Fanene i vinduet var Bootstraps lyse: hvit aktiv fane med mørk tekst. De
  følger nå sidens mørke flater.

## 2026-09-12 — Andrés runde på staging, del F: lydvarsel i bilen

Ingen migrasjon.

- **Et ventende oppdrag bilen ikke har rykket ut på, piper.** Akutt etter
  ett minutt og så hvert tiende sekund; Haster etter fem minutter og så
  hvert minutt; Vanlig og Drift etter et kvarter og så hvert minutt. Tida
  regnes fra da *bilen* ble varslet. Lyden lages i nettleseren (ingen fil,
  ingen dekning) og varer under tre sekunder; Akutt har tre toner, Haster
  to, resten én.
- **«Lyd»-knappen øverst på bilskjermen** slår varselet på og av og husker
  valget. Nettleseren krever et trykk før den får spille lyd — er lyden på
  fra før, holder det første trykket hvor som helst på skjermen, og en
  linje under knappen sier det til lyden er vekket.
- Raden pulserer i gult når terskelen er passert, uansett om lyden er på:
  lyd alene overhøres i en bil med sirene.
- Et trykk som ligger usendt i køen teller som svart — da piper det ikke.

## 2026-09-12 — Andrés runde på staging, del E: verdimengdene som tabeller

Tre migrasjoner, `oppdrag/0019`–`0021`: tabellene `Enhetstype` og
`Problemstilling`, seeding fra listene i `choices.py` med oversetting av
`Enhet.type` til FK, og fjerning av det gamle feltet. Delt i tre så
dataskrittet ikke står i samme transaksjon som en skjemaendring
(PostgreSQLs triggerkø). **Kjør `verifiser_migrasjoner` ikke — mønsteret
finnes ikke her — men ta backup før `main`, som alltid.** Eksisterende
enheter beholder typen sin; nye står som «Uten type» til noen setter den.

- **Problemstillinger, enhetstyper og lokasjoner redigeres og sorteres på
  sentralbordet**, i ett vindu med tre faner («Verdier»). Opp/ned flytter
  raden, og rekkefølgen er rekkefølgen i nedtrekkene. Problemstillingene har
  kategori (medisinsk, drift, begge) og om de bærer antall. «Udefinert» er
  fast og står alltid øverst.
- **Oppsettet er `skriv_leder`** — nytt trinn i oppdragsmodulen («Skrive:
  leder (verdimengdene)»). Lokasjonene var `skriv_full` én dag. Sletting er
  fortsatt global admin, og bare for verdier ingenting bruker.
- **Enhetene står alfabetisk innenfor gruppa**, i enhetslista, tavla og
  «Nytt oppdrag».
- **Antall pasienter settes av bilen**, ikke av operatøren: to store knapper
  på det påbegynte oppdraget der problemstillingen bærer et antall. Tomt
  vises som «1 pasient», ellers «N pasienter». Feltet er borte fra
  operatørens skjemaer.
- Et oppdrag beholder problemstillingen sin om noen deaktiverer den — KO kan
  fortsatt rette fritekst og hastegrad på det.

## 2026-09-12 — Andrés runde på staging, del D: småfeil og visning

Én migrasjon, `oppdrag/0018`: `Oppdrag.trenger_ressurs_siden`. Ren
skjemaendring.

- **Innloggingssiden:** fanikonet er en lys utgave av merket uten bakgrunn
  (`static/img/favicon.svg`) — merket på blått ble en mørk flekk i en mørk
  fanelinje. PWA-ikonene er som før. «Vis passord» er portalens egen, lyse
  knapp; nettleserens svarte øye (Edge) skjules.
- **«Nytt oppdrag»:** avkryssingen av enheter og valgt lokasjon overlever at
  pollingen tegner lista på nytt — det var derfor krysset forsvant. Alle
  nedtrekkene starter øverst hver gang vinduet åpnes, og fritekst og antall
  tømmes.
- **Oppdragslista på sentralbordet sorteres på hastegraden operatøren satte**
  (Akutt, Haster, Vanlig, Drift) og innenfor den på nummer. Ferdige nederst.
- **«Trenger ny ressurs» trappes opp med tida:** gul kant de første fem
  minuttene, oransje rad til et kvarter, så rødt med puls. Merket har egen
  trekant, ikke statusprikken bilene har, og sier hvor lenge det har stått.
  Bilen som rykket videre står i loggen, ikke lenger i enhetsraden på lista.
- **Bilen:** «Nylig avsluttet» viser oppdragsnummeret. Står problemstillingen
  som «Udefinert», sier kortet fra *før* hun trykker «Ledig»: meld
  problemstillingen til KO. Avvisningen fra serveren ble tidligere skjult i
  samme åndedrag som køen ble tom — bilen så bare «venter på dekning».
- **Adminkontoer er aldri mannskap** («Den er utenfor.»): de kobles ikke på
  e-post, tilbys ikke i kontolista, og avvises ved kobling for hånd.

## 2026-09-12 — «Teknisk» heter «Drift»

Migrasjon `oppdrag/0017`: nye hastegradvalg, og rader som sto som «Teknisk»
på staging rettes til «Drift». «Udefinert» står øverst i alle fire listene,
og `choices` håndhever det.

## 2026-09-12 — Andrés runde på staging, del C: «trenger ny ressurs»

Én migrasjon, `oppdrag/0016`: `Oppdrag.trenger_ressurs` og
`Enhetshendelse.detalj`. Rene skjemaendringer.

- **Rykker bilen ut på et nytt oppdrag mens hun står på et annet, blir det
  forrige stående på tavla som «Trenger ny ressurs»** i stedet for å ryddes
  til historikken. Hennes rad lukkes automatisk som før (§4.3); oppdraget
  gjør det ikke. Merket står først i enhetsmatrisen, tidslinjen sier «Rykket
  videre til #12», og sentralbordet varsler en ny enhet — det nullstiller
  flagget — eller sletter oppdraget hvis det ikke lenger trengs.
- Var en annen bil fortsatt på oppdraget, endres ingenting: hun kjører
  videre, og oppdraget følger henne.

## 2026-09-12 — Andrés runde på staging, del B: oppdragsmodulen

Én migrasjon, `oppdrag/0015`: `Enhet.type`, `Oppdrag.antall` og de nye
hastegradvalgene. Rene skjemaendringer; eksisterende enheter får «Annet».

- **Hastegrad «Teknisk», i blått**, med egne problemstillinger
  (matutlevering, transport, utstyr, forsyning, annet teknisk). «Vanlig» er
  grønn, som i statistikken. Problemstillingen må høre til hastegraden —
  serveren avviser paret, og skjemaet bygger nedtrekket om når hastegraden
  endres.
- **Rekkefølgen i skjemaet er hastegrad → lokasjon → problemstilling**, i
  «Nytt oppdrag» og i «Rediger».
- **«Udefinert»** som problemstilling i alle listene. Bilen får ikke melde
  ledig før sentralbordet har satt en ekte problemstilling; meldingen står på
  enhetsskjermen.
- **Transport har antall**, et helt tall, vist som «Transport · 3» på tavla,
  i bilen og på enhetskortet.
- **Enhetstyper.** Ambulanse, mannskapsbil, lag til fots, annet — settes i
  enhetspanelet, og grupperer ressursoversikten og avkryssingen i «Nytt
  oppdrag» med ambulansene først.
- **Lokasjoner:** sentralbordet (`skriv_full`) legger til og endrer navn;
  global admin sletter ubrukte, med bekreftelse. Brukte kan bare deaktiveres.

## 2026-09-12 — Andrés runde på staging, del A: vaktlisten

Én migrasjon, `vaktliste/0014`: `Mannskap.epost`, ingen data flyttes.

- **Rettet: besetningen i sentralbordet fant ikke bilen.** Scopet var portalens
  aktive vakt alene; nå vinner vaktlista som er **i drift**, og den aktive
  vakta er reserven. Dekker ingen skift nå, står neste skift i svaret («Neste
  skift 16:00: Kari, Ola») i stedet for bare «ingen».
- **E-post på mannskapet, og kontoen kobles av seg selv.** Finnes en aktiv,
  ledig portalkonto med samme e-post, kobles den ved lagring. Et merke ved
  adressen sier at en bruker finnes. Adminkontoer kobles bare av global admin.
- **Kontokobling for hånd er global admin.** Konto-feltet og -kolonnen finnes
  bare for admin; vaktlederen kobler gjennom e-posten.
- **«Skrive: eget korps» ser alle korps.** Korps-føreren ser hele lista og
  registeret, får korpsvelgeren, og redigerer fortsatt bare sitt eget.
  Etiketten i matrisen heter «Skrive: eget korps, ser alle».
- **Probono i bemanningskurven** som den øverste delen av søylen, i grønt,
  med egen post i tegnforklaringen.
- Registeret annoterer «i bruk» i stedet for én spørring per rad.

## 2026-09-12 — Plan: reserve og offline

Ingen kode. Planen for reserve og offline står i `TODO.md` under «Pågående / neste»:
vaktlista som fil på e-post, offline drift på drifts-PC-en, backupene kryptert og
komprimert til Scaleway Object Storage, og fjerning av den gamle offline-arkitekturen.
Speiling til staging ble vurdert og tatt ut, fordi det ikke deployes under vakt.

## 2026-09-12 — Hjem-skjerm-ikonet: full flate, og kortnavnet

- **Rettet: ikonet på hjem-skjermen hadde blå flekk øverst til venstre og
  gjennomsiktig resten.** Rendringen skalerte bakgrunnsrektangelet sammen
  med `<svg>`-taggen, så flaten dekket 180 av 512 enheter. Generatoren
  ligger nå i `scripts/lag_ikoner.py` og skalerer bare rot-elementet;
  `IkonfileneTests` leser hjørnepikslene i PNG-ene (egen liten PNG-leser,
  Pillow er ikke i requirements) og stopper det.
- **Kortnavnet er «Sanitetsportalen»**, som navnet (André: «Vi har
  sanitetsportalen på begge»).

## 2026-09-12 — Andrés rapport 4: arkivering lukker vakta, ny logo

Ingen migrasjon.

- **Arkivering av oppdragsvakta lukker den.** Radene fryses med signatur
  som før, og deretter tømmes tavla og historikken og telleren nullstilles,
  så neste oppdrag får #1 (André: «tallene må resettes … historikklisten
  tømmes»). Avvises med 400 mens noe står på tavla — et pågående oppdrag
  slettet halvveis er en hendelse uten slutt. `arkiver_vakt(..., tomm=False)`
  fryser uten å rydde, for testene som sammenligner arkiv med live. Vaktarkivet
  var alt global admin i alle fire endepunkter.
- **Bilen ser de andres stempler også mens hun venter.** Tidslinjen sto
  bare på det aktive kortet; nå står den på det ventende når andre biler har
  stemplet.
- **Bemanningskurven forsvant** på en vaktliste der vaktens start lå uker
  før slutten: spennet over 14 dager ga stille opp. Nå faller den tilbake på
  skiftene, og uten spenn sier kortet hva som mangler i stedet for å stå tomt.
  Bunnlinja heter «N personell på det meste» og teller folk, ikke plasser.
- **Ny logo:** et skjold med en person i, to farger på portalens blå. Den
  første leste som EKG («trenger bare noe subtilt»).

## 2026-09-12 — Andrés rapport 3, manifest og logo

Ingen migrasjon. Nye arkiv får tittelen «Arkivert dd.mm.åååå hh:mm»; eldre
arkiv står som før i basen, og klienten klipper vaktnavnet av tittelen.

- **Bilen ser de andre bilenes stempler i tidslinjen** (§7.3 snudd: «nyttig
  for de å vite historikken der»). `andre_meldinger` i lista og detaljen,
  tegnet dempet med bilens navn på raden. Egen kjede og knappene bygger
  fortsatt bare på `statusmeldinger`, og de andres ID-er er med i ETag-en.
- **Vaktarkivets tittel uten vaktnavnet.** Det sto på raden under alt, og
  leste dobbelt («Test — arkivert … / Test · arkivert av»).
- **«Mitt korps» skiller å dekke for korpset fra åpent for alle.** 32 t «å
  dekke» der det meste var åpent for alle, leste som korpsets gjeld.
- **Bemanningskurvens hode har tre tall og ikke mer:** «Ledige plasser: N ·
  M plasser dekket» og «K plasser på det meste». Lista over ledige skift er
  borte («for mye clutter»).
- **«Arkiv» ved siden av «Arkiver vaktlisten», i sitt eget vindu.**
  Vaktvinduet lukkes først (`_byttModal`), så to modaler aldri står oppå
  hverandre — det var den feilen som frøs oppdragsvinduet.
- **Manifest og logo.** `/manifest.webmanifest` (`core/manifest.py`, uten
  innlogging, med `{% static %}`-stier fordi WhiteNoise hasher navnene) og
  `static/img/logo.svg` med PNG-er i 192, 512, maskable og apple-touch.
  Merket er en ring — portalen — med en pulslinje — sanitet; bevisst uten
  kors, som er Røde Kors-emblemet. `partials/_ikoner.html` tas med i hver
  mal med eget `<head>`, og logoen står i portalheaderen og på innloggingen.
  `core/tests_manifest.py` håndhever alt tre.

## 2026-09-12 — Andrés rapport 2, runde 2: vaktlisten og statistikken

Ingen migrasjon.

- **«Utildelt» heter «Åpen for alle».** André foreslo «ledig korps»; «ledig»
  er alt plassen uten person, og to «ledig» i samme rad leser som ett. Bare
  navnet — nedtrekket, oversikten og «Mitt korps». Feltet er fortsatt
  `alle_korps`.

- **Nedtrekkene tilbyr bare dem brukeren får sette inn.** Korps-føreren
  kunne velge hvem som helst; serveren avviste, men lista lot som.
  `services.mannskap_brukeren_kan_sette` speiler `kan_redigere_mannskap`:
  alle for den som skriver alt, eget korps med badge, ellers ingen.
- **«Mitt korps» teller bemannet, å dekke og probono hver for seg.** Ett
  samlet «avsatt» blandet korpsets egne timer med de ledige plassene og
  leste som feil (24 t der André ventet 16).
- **Bemanningskurven lister ledige skift, ikke plasstimer.** «20 ubesatte
  plasstimer» ble «Ledige plasser: 2 × fre 17:00 – lør 03:00». Bunnlinja
  sier «3 plasser på det meste»; «topp 3 plasser kl. 11–15» er borte.
- **«Dupliser som ledig plass»** i skiftvinduet: samme spenn, rolle,
  reservasjon og probono, uten personen. `skriv_full`, som å opprette.
- **«Slett vaktlisten»** for global admin ved siden av «Arkiver», med to
  bekreftelser og `{"confirm": true}` (endepunktet fantes). **Arkiverte
  vaktlister ligger bak én knapp** og vises først når man ber om det.
- **Registeret hentes ved sidelasting**, så «Korps» i innstillingene åpner
  uten ventetid første gang.
- **Lesbar tidstekst på /statistikk/.** Ventetid, tid på obspost, total
  behandlingstid og krysstabellens radsum sto med `color:#1e293b` rett i
  markupen — mørk tekst for lys bakgrunn. Nå `.kpi-tid` og `.xt-total` i
  stilarket. **«Til pasientregistrering»-knappen er fjernet.**

## 2026-09-12 — Andrés rapport 2, runde 1: oppdragsmodulen

Én migrasjon, `oppdrag/0014`: ny tabell `Enhetshendelse`, ingen data flyttes.

- **Rettet: «kan ikke ligge i framtiden» når man trykket med én gang.**
  Nettleserens klokke kan gå sekunder foran serverens, og «nå» rundet ned
  til minuttet lå da i framtiden for serveren. `MINUTTSLAKK` gjelder nå
  begge veier, i føring og «Rett tid».
- **Rettet: oppdraget ble stående på tavla** når én bil meldte ledig og en
  annen ble tatt av etterpå. `ta_av_enhet` rydder til historikken når den
  som ble tatt av var den siste som ikke var ledig.
- **Tidslinjen viser hvem som ble varslet og hvem som ble tatt av.**
  Varslingen leses av koblingsradens `varslet_at`; fjerningen får et eget
  spor, `Enhetshendelse` — raden er borte, hendelsen står. Flytting sto der
  fra før.
- **«Angre» på enhetens siste status** (`angre_siste_status`, `POST
  …/enheter/<pk>/angre/`): meldingene for statusen slettes med
  rettingshistorikken sin, og raden går tilbake til den forrige.
  Slettingen logges i revisjonsloggen. **«Gjenåpne» gjør nå det samme** for
  «Ledig», med 48-timersgrensen — den la før en korreksjonsrad med forrige
  status, og da sto forrige status dobbelt og et nytt angre landet på den
  samme. Knappen står ved «Rett tid» på enhetens siste melding.
- **Sletting av oppdrag** (`DELETE api/oppdrag/<pk>/`, `{"confirm": true}`):
  sentralbordet mens alle biler venter — er noen på vei, angres statusen
  først — og global admin i historikken, enkeltvis eller «Slett alle i
  historikken» (`DELETE api/historikk/`). Korreksjonsradene kobles fra før
  slettingen (`korrigerer` er PROTECT, og stoppet ellers alt).
- **Sentralbordet redigerer oppdraget**: «Rediger» i detaljvinduet gir
  problemstilling, hastegrad, lokasjon og fritekst (PUT-endepunktet fantes).
- **«Avreist → Sykehus» synes i sentralbordet**: på enhetskortet, i
  oppdragslistas brikker og i enhetsradene (`sted_navn`).
- **«Endre»** heter knappen i skjemaet (var «Før»), og radens «Endre
  status» låses mens skjemaet står. «endret av KO» i tidslinjene (var «ført
  av sentralen»), i bilen og i sentralbordet.
- **Arkivlista viser notatet.**

## 2026-09-12 — Planlagt og utildelt: navnene, og én vei

André: «Utildelte vakter må vises til alle, og så må vi ha en annen som heter
planlagt. En kan ikke bytte tilbake til planlagt etter den er satt til
utildelt eller er tildelt et korps.» Avklart: utildelt = alle ser; planlagt =
synlig for lederne før de deler ut.

Ingen skjemaendring: dagens skjulte «utildelt» *er* planlagt, og dagens
«alle korps» *er* utildelt. Det som manglet var navnene og énveisregelen.

- **Navnene.** Nedtrekket på plassen sier «Planlagt», «Utildelt» og korpsene;
  oversikten og «Mitt korps» skriver «Utildelt» der det sto «Alle korps», og
  «Planlagt» der kolonnen sto tom. Korpsvelgeren i vaktlinja heter fortsatt
  «Alle korps» — den er et filter, ikke en tildeling.
- **Planlagt går én vei.** `services.er_planlagt` (ingen reservasjon, ikke
  utildelt). PUT som ville gjort en delt-ut plass planlagt igjen får 400 med
  forklaring; nedtrekket tilbyr «Planlagt» bare så lenge plassen står der.
  «Som ressursen» på en ressurs med korps er ikke planlagt — den veien er åpen.
  `PlanlagtGaarEnVeiTests` på server, `_plassKorps` i node.

## 2026-09-12 — Andrés testrapport, runde 2: vaktlisten

Én migrasjon, `vaktliste/0013`: `Vaktliste.arkivert_at`, rent `AddField`.

- **Egne folk på andres plass.** «En ressurs som er tildelt et annet korps
  men har fått et personell fra et annet korps kan ikke den med skriv eget
  korps redigere.» Nå: **en fylt rad følger personen, en tom følger
  reservasjonen** (`kan_rore_vaktpost`, `kan_sette_vaktpost`, og
  `kanRoreRad` i JS). Står en av korpsets egne på Karmøys plass, kan
  korps-føreren rette raden, bytte til en annen av egne, eller ta henne ut
  så plassen blir ledig — men ikke fylle den med et annet korps, og er
  raden først tom, er den Karmøys igjen. Andres person på egen ressurs er
  deres rad. `EgenPersonPaaAndresPlassTests` på server, speilet i JS.
- **Arkivering av vaktliste i stedet for sletting.** «Vi må kunne
  lagre/arkivere vaktlista for å hente den igjen ved feil.» Global admin
  får «Arkiver vaktlisten» i vaktvinduet: lista går ut av velgeren, alt
  står, og «Arkiverte vaktlister» under har «Hent tilbake».
  `POST api/vaktlister/<pk>/arkiver/` og `gjenopprett/` — to navngitte stier,
  ikke `<str:retning>`, som ville fanget `ressurser/` og `belastning/`
  (testen fant det). `DELETE` finnes fortsatt, uten knapp.
- **Til-tiden foreslås som fra + 8 t** i «Opprett vakt» og «Rediger skift»
  når den er tom eller ligger før fra (`foreslaaTil`); et til som alt står
  etter fra røres ikke.
- **«Mitt korps» viser timer**: avsatt (uten probono) og probono for seg.
- **Probono-merket vises også på en ledig plass**, i ressurstabellen og i
  «Mitt korps».
- **Bare global admin kan koble en adminkonto til et korps**
  (`_kobler_til_admin` i registerviewet): badgen avgjør hva kontoen får
  redigere, og en vaktleder skal ikke kunne gi eller ta administratorens
  korps.
- **«Korps»-etiketten ved korpsvelgeren er borte.** Den leste som en knapp
  som ikke gjorde noe; nedtrekkets «Alle korps» sier hva det er.

## 2026-09-12 — Andrés testrapport, runde 1: oppdrag og statistikk

Fra prodtesten på staging (rapporten i chatten). Ingen migrasjon.

- **Rettet: sted- og grovsorteringsknappene i bilen gjorde ingenting.**
  «Jeg får trykke knappen men kommer ikke videre.» Knappene bar nøkkelen i
  `data-id`, og klikkdelegeringen gjør `data-id` om til tall — `Number('sykehus')`
  er NaN, og handlingen avviste den stille. Nå `data-arg`.
  `StedOgGrovKnappeneTests` kjører delegeringens argumentregel mot knappenes
  markup, og røyktesten i Chromium går hele kjeden: Rykker ut, Fremme, Gul,
  Avreist → Sykehus, Leverer, Ledig. Node-testene som fantes så bare på
  markupen; ingen klikket.
- **Grovsorteringen finnes fra Fremme**, ikke fra Rykker ut: den er en
  vurdering av pasienten, og den finnes ikke før bilen er framme.
  Knappene har fått fargen sin også før de er valgt — tre grå knapper med
  ordene Rød/Gul/Grønn var en lesejobb i en bil i bevegelse.
- **Rettet: historikken viste bare den primære bilen.** Alle enhetene står
  der nå.
- **«Nytt oppdrag» nullstilles ved hver åpning** (`show.bs.modal`), uansett
  hvilken vei forrige forsøk gikk. Kunne ikke reproduseres, men regelen er
  nå uavhengig av stien dit.
- **«Før status» heter «Endre status».** «Før» leste som fortid. Stedet vises
  bare når «Avreist» er valgt i nedtrekket (`foerStatusEndret`). Mens ett
  skjema står åpent, skjules knappene på de andre radene — ett om gangen. Et
  avvist klokkeslett settes tilbake til nå.
- **Tidslinjen begynner med «Oppdrag opprettet».** Uten «Rett tid»: den er
  ikke et stempel, og ingen melding kan rettes til før den.
- **Oppdragsarkivets tall vises på /statistikk/**, som pasientarkivet, via
  `?kilde=oppdrag&arkiv=<id>` (`lastOppdragArkivStatistikk`) med banner og
  «Tilbake». «Vis tall» i vaktarkivet viste én linje ren tekst; knappen heter
  «Vis statistikk» nå, og «Signatur» viser det den viste før.
- **KPI-boksen «Oppdrag»** viser tallet alene, og «N enhetsinnsatser» som
  undertekst når det skiller — «(15 enhetsinnsatser)» i selve tallet fikk
  ikke plass. Underteksten «i vakta» er borte.
- **«vakta» → «vakten»** i alle brukervendte tekster i maler og JS (46 steder).

## 2026-09-12 — Rettet: sida frøs etter «Ta av» eller «Varsle» i detaljvinduet

Funnet av André i prod rett etter deployen: «fjerner en bil eller gir en annen
bil et oppdrag og du går ut av det vinduet så fryser appen.»

**Årsaken var en modalinstans for mye.** Handlingene per enhet tegner
detaljvinduet på nytt mens det står åpent, og `visOppdrag()` gjorde
`new bootstrap.Modal(el).show()` hver gang. Bootstrap 5 lar ett element ha
én instans: den nye overtok, `.show()` på den la en bakgrunn til, og
lukkingen fjernet bare den sistes. De andre ble liggende over hele sida.
«Rett tid» og «Før status» hadde samme feil, og alle modalene i vaktlista
og pasientarkivet gikk samme vei ved gjentatte åpninger.

Reprodusert med ekte Bootstrap 5.3.2 i Chromium: to bakgrunner igjen etter
lukking, null med rettelsen, og «Nytt oppdrag»-knappen klikkbar igjen.
`bootstrap.Modal.getOrCreateInstance(el).show()` overalt der et vindu åpnes
— ni steder — og `DetaljvinduetTegnesPaaNyttTests` kjører `visOppdrag()`
tre ganger mot en Modal-stubb med Bootstraps regler og krever én instans.
Ingen migrasjon. **Pushet til `main` som `9437986`** samme kveld.

## 2026-09-12 — Merget til prod: flere enheter, korpsfilter, utskrift

`rollemodell` → `main` (`4c6017b`), fast-forward. 19 commits: 59 files changed, 7288 insertions(+), 403 deletions(-).
Åtte migrasjoner gikk ut — `accounts.0016` (nivået `les_alle`),
`vaktliste.0011`–`0012` (probono, plass tildelt alle korps), `oppdrag.0009`–`0013`
(avreist til/grovsortering, koblingsraden `Oppdragsenhet`, backfill, `manuell`,
arkivrad per enhet). **Én av dem skriver data**, `oppdrag.0011`: én koblingsrad per
eksisterende oppdrag. Backup av prod bekreftet tatt før pushen (André, «Backup
tatt — push»).

Innholdet er alt siden forrige merge: tidsblokker og «8,5 t», korpsfilteret med
`les_alle` og korpsvelgeren, bygg og dato i footeren, prosjektleders tre runder,
flere enheter på ett oppdrag i fire trinn, og utskrift per korps eller ressurs
med korpsvelgeren rettet.

**Verifisert før merge:** 2186 tester grønne, `verifiser_migrasjoner` OK mot
PostgreSQL 16 for begge prøvene (`vaktliste.0007` og `oppdrag.0011` med rader i
den historiske formen), og røyktester i Chromium av sentralbordet med to biler
og av korpsvelgeren. Ingen oppgraderingssimulering av hele basen denne gangen —
den ene datamigrasjonen er dekket av prøven, og de sju andre er rene
skjemaendringer.

**Deploy 2 står igjen** (eget punkt i TODO): fjerne `Oppdrag.enhet` og gjøre
`Statusmelding.oppdragsenhet` NOT NULL, når koden har gått en stund med broene.

## 2026-09-12 — Korpsvelgeren virket ikke, og utskrift per korps eller ressurs

**2186 tester grønne** (7 nye), og en røyktest i Chromium: velg korps, velg
ressurs, begge samtidig, og velgeren borte i utskrift. Ingen migrasjon.

- **Rettet: korpsvelgeren i vaktlinja filtrerte ingenting.** André: «Når vi
  setter til et korps i nedtrekksvinduet så vises fortsatt alt i oversikt.»
  Markupen var riktig (`data-action="velgKorps" data-hendelse="change"`), og
  `velgKorps()` virket når den ble kalt — men ingen kalte den. Klikkdelegeringen
  i `portal-utils.js` hopper over `data-hendelse`-elementer med vilje
  (`klikkSkalKjore`), og den eneste `change`-lytteren var scopet til
  ressurspanelet og hardkodet til `endreVaktpost`. Korpsvelgeren står utenfor
  panelet. Nå har `change` sin egen delegering ved siden av klikk,
  `haandterHendelse`, og `hendelseArgumenter` gir cellene (id, felt, verdi) og
  alt annet ett argument. Panellytteren er borte. `HendelsedelegeringTests`
  kjører delegeringen mot falske elementer — testene som fantes kalte
  `velgKorps()` direkte og så aldri at knappen ikke var koblet.
- **Utskrift per korps eller per ressurs.** «Oversikt» har fått en velger over
  lista: «Hele vakta» eller én ressurs, gruppert på ressursgruppe og bare
  ressurser med skift (`mkUtskriftsverktoy`, `velgUtskrift`, `utskriftRessurs`).
  Korpset er korpsvelgerens — de to kombineres — og for korps-brukeren er lista
  alt hennes korps. **Arket sier selv hva det er avgrenset til**
  (`_utvalgstekst`, «Haugesund · Ambulanse 1» i arkhodet), for velgeren
  kommer ikke med på papiret. Summene i arkhodet er utvalgets. En
  «Skriv ut»-knapp står ved velgeren.

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 4: arkiv og statistikk

**2179 tester grønne** (5 nye). Én migrasjon, `oppdrag/0013`: unikhet og
rekkefølge på `ArkivertOppdrag` — ren skjemaendring, ingen data flyttes.
Alle fire trinn er levert; deploy 2 (fjerne `Oppdrag.enhet`, stramme
`Statusmelding.oppdragsenhet`) står igjen som eget punkt.

- **Én arkivrad per oppdrag × enhet** (§5 A). Nummeret gjentas per bil, og
  hver rad bærer *hennes* tidsstempler og sluttstatus. Samme radform og samme
  signaturform: `sha_payload` sorterer nå på `(oppdragsnummer, enhet_navn)`,
  som for unike nummer er den gamle rekkefølgen — `SignaturLaastTests` står
  urørt, og eksisterende arkiver verifiserer som før. `arkiv._per_enhet()` er
  det ene stedet som sier hva en rad er.
- **Statistikken teller oppdrag distinkt og varigheter per bil.** Det som er
  bilens — responstid, ventetid, utrykning, tid på stedet, oppdragstid,
  `per_enhet` — per rad; det som er oppdragets — antall, hastegrad,
  problemstilling, lokasjon, status nå, ankomster — én gang per nummer, med
  status utledet som på tavla (`services.utledet_av_statuser`, delt). Et
  arkiv med én bil per oppdrag gir nøyaktig de gamle tallene, og
  `ArkivStatsMatcherTests` er utvidet til to biler: arkivet gir det live gir.
- **`summary.enhetsinnsatser`** er radtallet; statistikksiden viser
  «12 (15 enhetsinnsatser)» når de skiller. Arkivlista viser `antall_oppdrag`
  distinkt og `antall_enhetsrader` ved siden av.
- Koblingsradene hentes med én `Prefetch` med enheten joinet inn —
  `GjeldendeBulkTests` holder statistikken på fire spørringer uansett antall
  oppdrag.

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 3: sentralbordets knapper

**2174 tester grønne** (15 nye), og en røyktest i Chromium mot hele flyten:
opprett med to biler, før status for den ene, ta den andre av, varsle henne
igjen. Ingen migrasjon.

- **«Nytt oppdrag» krysser av enheter** (`mkEnhetsvalg`), ikke velger én. Den
  første i lista blir primær; ingen avkrysset gir «Kryss av minst én enhet» før
  noe sendes.
- **Oppdragslista viser én brikke per enhet** (`_enhetsmatrise`): prikk, navn,
  status og tid siden. Samme brikke med én enhet — lista skal lese likt.
  Oppdragets utledede status står fortsatt til høyre.
- **Detaljvisningen har fått «Enheter»** (`mkEnhetsrader`): én rad per enhet
  med status, klokkeslett og tid siden, og bare knappene som kan brukes —
  «Før status» (ikke når hun er ledig), «Gjenåpne» (bare da), «Ta av» (bare
  mens hun venter, og ikke den siste). «Varsle enhet til» under, med enhetene
  på vakt som ikke alt står på oppdraget. Feil fra handlingene står under
  innholdet, så de overlever at det tegnes på nytt.
- **«Før status» er et skjema i raden**, som «Rett tid»: nedtrekket tilbyr
  neste ledd og «Ledig» (`_lovligeOverganger` speiler `services.OVERGANGER`),
  sted ved «Avreist», og klokkeslett med nå som utgangspunkt. Stedet sendes
  bare når statusen er «Avreist».
- **Tidslinjen sier hvem sin melding** når oppdraget har flere enheter
  («KARM 12: Fremme»), og «ført av sentralen (adm)» på det operatøren førte.
  `melding_til_dict` bærer `enhet_navn`; `gjeldende_bulk` henter enheten med,
  så det ikke koster en spørring per rad.
- **Flytt av én rad:** med flere enheter får «Flytt til enhet» et «fra»-valg.
- **Rettet: «Rett tid» viste «[object Object]».** Skjemaet ble satt med
  `trustedHtml(...)` som innerHTML — den pakker inn i et objekt for
  `cellHtml()`. Det har stått slik siden fase 3; ingen test kjørte funksjonen.
  `InnlinjeskjemaeneTests` kjører begge skjemaene mot en DOM-stubb nå.
- **Ett minutts slakk mot `created_at`** (`services.MINUTTSLAKK`) i føring og
  «Rett tid»: `datetime-local` har minuttoppløsning, og «nå» rundet ned lå før
  et oppdrag opprettet sekunder tidligere. Røyktesten fant det.

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 2: endepunktene og §9

**2159 tester grønne** (30 nye). Én migrasjon, `oppdrag/0012`: ett `AddField`,
`Statusmelding.manuell`, standard `False`.

Endepunktene fra notatets §4, og sentralbordets føring fra §9 — data og API;
knappene kommer i trinn 3.

- **`POST api/oppdrag/` tar `enhet_ider`** — den første er primær, dubletter
  strykes, og én enhet som ikke er på vakt avviser hele opprettelsen: operatøren
  mente å sende flere, og skal ikke få ett oppdrag med færre enn hun krysset av.
  `enhet_id` godtas fortsatt og betyr én.
- **`POST`/`DELETE api/oppdrag/<pk>/enheter/<enhet_pk>/`** varsler en enhet til
  og tar henne av. Ta av bare mens hun venter, og aldri den siste. `skriv_full`,
  og enhetskontoer stengt ute uansett nivå — som «Rett tid».
- **`POST api/oppdrag/<pk>/enheter/<enhet_pk>/status/<overgang>/[<sted>/]`** er
  sentralbordets føring av en status bilen glemte (§9). `tidspunkt` i kroppen er
  **påkrevd** — poenget er å føre bakover i tid — og derfor `skriv_full`, ikke
  `skriv_handling`: bilens stemplingsendepunkt leser ingen domenefelt, og dette er
  en annen aktør. Overgangsreglene gjelder operatøren også; tidspunktet må være
  inntruffet, etter oppdraget og etter bilens siste melding. Raden merkes
  `manuell`, og tidslinjen sier «ført av sentralen».
- **`POST api/oppdrag/<pk>/enheter/<enhet_pk>/gjenaapne/`** tar «Ledig» tilbake
  innen `KORRIGERBAR_ETTER_LEDIG` (48 t, André: «innenfor en rimelig
  tidsperiode»). En korreksjon, ikke en sletting: `Ledig`-meldingen blir stående,
  og en ny rad peker på den med statusen som gjaldt før — med *dens* tidspunkt,
  så ingen varighet flytter seg. Oppdraget hentes tilbake fra historikken.
- **`flytt/` tar `fra_enhet_id`**: med flere enheter er flytt flytt av én rad.
  Uten er det den primære, som før.
- **Rettet fra trinn 1:** `_naboer` målte korreksjoner mot hele oppdragets
  meldinger, så den andre bilens «Rykker ut» sto i veien for å rette denne bilens
  «Fremme». Nå per koblingsrad.
- **`enheter[]` bærer `status_tidspunkt`** per enhet, uten en spørring per rad —
  lista gjenbruker `gjeldende_bulk`, og en test holder spørringstallet flatt.
- **Bilen ser «Også varslet: KARM 12»** på aktivt og ventende kort — navn, ikke
  status (§7.3).

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 1: koblingsraden

**2129 tester grønne** (32 nye i `oppdrag/tests_flere_enheter.py`). To migrasjoner,
`oppdrag/0010` (skjema) og `0011` (bare data, med prøve i `core/migrasjonsprover.py`).
**Backup av prod før deploy** — `0011` skriver én rad per oppdrag.

**`Oppdragsenhet` er nå det en statusmelding hører til.** Én melding er *én enhets*
utsagn om *ett* oppdrag, og kjeden Venter → Rykker ut → … → Ledig går per koblingsrad
(`services.sett_status(..., enhet=)`, `start_oppdrag(..., enhet=)`). `Oppdrag.status`
er fra nå **utledet** (`services.utledet_status`): den mest aktive enheten vinner,
`Ledig` bare når alle er ledige — og det er da oppdraget flyttes til historikken. Med
én enhet gir det samme svar som før; 305 eksisterende oppdragstester gikk uendret,
bortsett fra én hjelper som satte statuscachen for hånd og nå setter den der den bor.

- **Broene i deploy 1.** `Oppdrag.enhet` lever til deploy 2, og `Oppdrag.save()` lager
  koblingsraden ved opprettelse; `Statusmelding.save()` fyller `oppdragsenhet` fra
  oppdragets primære rad når en melding lages med bare `oppdrag`. Ingen eldre kode
  trenger å vite at raden finnes. `0012` (NOT NULL) er derfor flyttet til deploy 2 —
  notatets §6 er oppdatert.
- **Per enhet, ikke per oppdrag:** den automatiske lukkingen (§4.3) lukker *hennes*
  pågående, 30-minuttersvinduet på enhetsskjermen måles mot *hennes* ledig-melding,
  `enhet_status` og `ventende_oppdrag` leser radene, og `flytt_til_enhet` flytter én
  rad (og holder den gamle kolonnen i takt når den primære flyttes).
- **`varsle_enhet` / `ta_av_enhet`** (§4): varsle legger raden sist i `Venter`, og
  henter et ferdig oppdrag tilbake fra historikken; ta av bare mens hun venter, og
  aldri den siste. Endepunktene kommer i trinn 2.
- **Bilen ser sin egen kjede og de andres navn** (§7.3). `oppdrag_til_dict(...,
  koblingsrad=)` gir `status`/`neste_overgang` fra *hennes* rad og `varslede` som
  navneliste uten status; liste og detalj sender bare hennes meldinger. Eierskapet i
  detalj, stempling og grovsortering er «har enheten en rad», så bil nummer to kan
  stemple på et oppdrag som ble opprettet med bil én.
- **Sentralbordet får matrisen** som `enheter` på hvert oppdrag — data først, UI i
  trinn 3. Lista prefetcher radene.
- **Backup** tar koblingsraden med, mellom meldingen og oppdraget i
  gjenopprettingsrekkefølgen; `varslet_av` strippes som de andre kontopekerne.
  `BackupTests` gjenoppretter to enheter med hver sin status.

## 2026-09-11 — Beslutningsnotat: flere enheter på ett oppdrag

`docs/BESLUTNING_FLERE_ENHETER_PER_OPPDRAG.md` — utkast, ikke besluttet. Det siste
punktet fra prosjektleders runde, og det eneste som snur en antakelse som ligger i ni
steder: at et oppdrag er tildelt én enhet. Notatet foreslår `Oppdragsenhet` som
koblingsrad med egen statuskjede, oppdragsstatus utledet som «mest aktive», ferdig
når alle er ledige, én arkivrad per oppdrag × enhet (samme payload-form — gamle
arkiver verifiserer som før), og deploy i to trinn som `year` → `vakt`. Fire
spørsmål til André i §7 før kode; §7.1 (arkivformen) lar seg ikke gjøre om etterpå.
**Besvart samme dag** — alle fire som anbefalt, med én presisering på §7.2: enhetens
oppdrag er ferdig når hun melder ledig, oppdraget forlater tavla når alle er det. Og
ett krav til, §9: sentralbordet skal kunne føre status manuelt for enhver enhet, også
på ferdige oppdrag innenfor en rimelig tid (forslag: 48 t). Kode starter.


**2097 tester grønne** (18 nye, to mutasjoner satt rødt først). Én migrasjon,
`vaktliste/0012`, ett `AddField` med `False` som standard — ingen eksisterende
plass blir universal ved oppgraderingen.

**Tre tilstander på en ledig plass.** Prosjektleder: «Dine tildelte vakter og
de vakter som er satt universal tildelt. Utildelte vakter skal ikke deles ut.»
Det er ett nytt flagg, `Vaktpost.alle_korps`, og én regelendring:
- **Tildelt ett korps** — som før (`Vaktpost.korps`, eller ressursens).
- **Tildelt alle korps** — `alle_korps`. Enhver korps-bruker med badge får
  fylle den (`kan_bemanne_plass`); badgen kreves fortsatt, uten korps finnes
  ingen å sette inn. Flagget vinner over `korps`: en plass alle kan fylle er
  ikke satt av til én.
- **Utildelt** — vaktlederens bord, deles ikke ut. Som før.
Å tildele er å dele ut: `skriv_full`, samme port som reservasjonen.
Korpsfilteret tar de universale med — hennes å fylle, altså hennes å se.

**Reservasjonsnedtrekket** i ressursraden og i begge skiftvinduene har fått
«Alle korps», og «— alle —» heter nå «— utildelt —»: det var feil ord for en
plass som ikke deles ut til noen. `_korpsKropp()` oversetter de tre
tilstandene til serverens to felt.

**Fanen «Mitt korps».** Plassene korpset har ansvar for, på tvers av alle
ressursene: «N plasser å dekke» øverst, så blokkene med dagoverskrifter,
ledige først i hver blokk, med nedtrekket for å fylle dem. For korps-brukeren
er det hennes korps; for den som ser alle, det korpsvelgeren står på — uten
korps finnes ikke fanen. Tallet på fanen er det som gjenstår.

**Rettet på veien:** korps-brukeren så ikke nedtrekket på en plass satt av til
henne på en *ureservert* ressurs — klienten spurte bare ressursen. `kanBemannePlass()`
speiler nå `services.kan_bemanne_plass` plass for plass.


**2079 tester grønne** (19 nye, tre mutasjoner satt rødt først). Én
migrasjon, `vaktliste/0011`, ett `AddField` med `False` som standard.

**Probono-skift telles ikke i timene — men i alt annet.** `Vaktpost.probono`,
en avkryssing i «Opprett vakt» og «Rediger skift», redigerbar av alle som kan
redigere raden (samme port som merknaden — det er ikke å dele ut noe, det er å
si hva skiftet er). Timesummene hopper over det: blokklinja (nei — blokkas
timer er skiftets lengde), ressursoverskriften, arkhodet, planleggingstallenes
«timer» per person og i sammendraget, og faktiske timer. **Lengste skift og
korteste hvile teller det fortsatt**: et probono-skift sliter like mye, og
varslene handler om sliting, ikke om lønn. Merket «Probono» står ved navnet,
ikke i timekolonnen — timene i raden står som før, det er summene som hopper
over dem, og det skal man kunne se hvorfor. `probono_skift` per person følger
med i planleggingstallene.

**Dagoverskrifter over blokkene.** «Fredag 4. sep» / «Lørdag 5. sep» i
ressursfanene og utskriftslista, der dagen skifter — men bare når vakta
faktisk spenner over mer enn én dag; en endagsvakt ser ut som før.
Starttiden bestemmer dagen (prosjektleder): et skift 17:00–03:00 er fredagens.
`_dagnokkel()` bruker lokal dato, `_blokkerMedDager()` er det ene stedet som
setter overskriftene, og begge tabellene går gjennom den.


**2060 tester grønne** (27 nye, to mutasjoner satt rødt først). Én migrasjon,
`oppdrag/0009`, to `AddField` med tom streng som standard — intet dataskritt.

**«Avreist» spør hvor.** Samleplass, Skadepol, Legevakt, Sykehus, Annen
ambulanse, Annet sted — forkortet, som prosjektleder ba om. Stedet er et
URL-ledd, `status/avreist/<sted>/`, ikke et felt i kroppen: stemplings-
endepunktet leser ingen domenefelt derfra (rollemodellen §3.2), og «Avreist
til Sykehus» er ett navngitt endepunkt til. Lagres på **statusmeldingen**
(`Statusmelding.sted`) — meldingen er det som ble meldt, og en korreksjon
av klokkeslettet arver stedet. `sett_status` avviser et sted på enhver annen
status; viewet gir 404 før det. Uten sted virker «Avreist» som før, så gamle
køer ikke feiler.
- **Bilen:** «Avreist»-knappen åpner seks store knapper og «Avbryt» *i
  stedet for* knapperaden — midt i valget skal det ikke finnes en feil knapp
  å treffe. Valget følger «Avreist» gjennom offline-køen (`rad.sted`), og
  `synk` legger det i URL-en.
- **Tidslinjene** sier «Avreist → Sykehus», på begge skjermene.

**Bilens grovsortering: Rød/Gul/Grønn, ved siden av hastegraden.** To
vurderinger fra to ståsteder: KO/AMK setter hastegrad ved opprettelsen,
bilen setter grovsortering underveis — og begge skal synes. Hastegrad står
til venstre, «Bil: Rød» til høyre, med fargeprikk og tekst (fargen alene
bærer ikke informasjonen). Tom vises som «Bil: —»: «ikke vurdert ennå» er
informasjon. `Oppdrag.grovsortering`, satt av bilen via
`grovsortering/<rod|gul|gronn>/` — samme form som stemplingene, men ikke
gjennom `sett_status` (det er en vurdering som kan endres, ikke et ledd i
kjeden) og ikke i køen (uten dekning sier skjermen fra). Sentralbordet
setter den ikke. Vises på det aktive kortet i bilen (tre knapper, den
valgte fylt), i oppdragslista og på enhetskortet.

**Arkivet er urørt.** Ingen av feltene inngår i `ArkivertOppdrag` eller i
SHA-payloaden — signaturene i prod verifiserer som før. Skal de arkiveres,
er det en egen beslutning (payloadens form er låst).


**2033 tester grønne** (15 nye). Fem av elleve punkter fra prosjektleder —
de som var klare og små. Resten står i TODO med plan.

- **Kompetansekolonnen i Mannskap «detter fra kolonne–rad-matchingen».**
  Bekreftet: `.vlr-komp` satte `display: flex` rett på `<td>`-en — samme feil
  som ressurstabellen hadde 30. aug. Layouten ligger nå på en wrapper inne i
  cella, og `TabellcellersLayoutTests` leser mannskapstabellen også; den
  hadde funnet feilen om den hadde lest den.
- **Bemanningskurven står nederst i drift.** I planlegging er hullene jobben
  og kurven det første man ser; i drift er spørsmålet «hvem har møtt», og
  stemplene står øverst.
- **«Oppdrag i vakta» heter «Oppdragsliste».**
- **Enhetskortet i sentralbordet viser oppdraget i ett blikk**: nummer,
  hastegrad, problemstilling — og statusen med klokkeslett og tid siden,
  «Fremme 14:32 · 12 min». Enhetslista bærer feltene fra serveren
  (`_aktivt_oppdrag_felter`), og statustidspunktet er med i ETag-en: «Rett
  tid» endrer det uten å røre statusen.
- **«Tid siden» på oppdragslista**: «Fremme · 12 min» og «14:20 · 31 min
  siden». `status_tidspunkt_for()` finner den gjeldende meldingen bak hvert
  oppdrags status i én spørring for hele lista (`gjeldende_bulk`) — testen
  krever at antall spørringer ikke vokser med radene. Klienten tegner lista
  på nytt én gang i minuttet, siden serveren svarer 304 når ingenting er
  endret og «12 min» ellers ville stått stille.


André: «de med rollen skrive eget korps ser bare de som er med i sitt eget
korps, og samme med de som bare har lesetilgang — gjelder bare /vaktliste/».
Og om leseren uten korps: «to lesetilganger, en for eget korps og en for
alle korps».

**Nytt trinn `les_alle`** mellom `les` og `skriv_handling` i `NIVAA_HIERARKI`
(`accounts/0016`, ren `AlterField`). Vaktlista er den eneste som deklarerer
det: `les` = «Lese: eget korps», `les_alle` = «Lese: alle korps».
**Eksisterende `les`-rader ble smalere**, ikke videre — den trygge retningen;
den som skal samordne får `les_alle` i matrisen.

**Synligheten følger ikke stigen.** `skriv_handling` ligger over `les_alle`
og ser likevel bare sitt eget korps; `skriv_full` og oppover ser alle.
`services.ser_alle_korps()` er det ene stedet. `synlige_vaktposter()` og
`synlig_mannskap()` filtrerer i svaret sida bygges av — `vaktliste_detalj_view`,
`belastning_view`, `mannskap_view` — så oversikt, ressursfaner, tilstede,
kurver, planleggingstall og registeret følger med på én gang. Ledige plasser
satt av til eget korps vises (via plassen eller ressursen, samme
sammenslåing som `reservert_korps()`). Uten badge er lista tom, og malen
sier hvorfor. Sentralbordets besetning i `/oppdrag/` er **ikke** filtrert.

Notatets §4.4 («`les` ser hele lista — poenget er samordning») er strøket
med dato og begrunnelse; CLAUDE.md oppdatert.

**Korpsvelgeren for den som ser alle** (samme dag): «Det må og være en måte
for de med full tilgang å sortere på korps.» Et nedtrekk i vaktlinja — «Alle
korps / HGSD — Haugesund / …» — som gjør i nettleseren det serveren gjør for
korps-brukeren: `_synligePoster()` speiler `poster_for_korps()`, og
`brukKorpsfilter()` legger den på `aktivListe.vaktposter` og
`register.mannskap`, så oversikt, ressursfaner, tilstede, kurver og registeret
følger med uten å vite om den. Planleggingstallene regnes på serveren og får
`?korps=<id>` — honorert bare for den som ser alle. Velgeren finnes ikke for
korps-brukeren: hun er alt avgrenset, og et nedtrekk med ett valg ser
ødelagt ut. Skiftet bærer nå `korps_id` (personens), ved siden av
`reservert_korps_id` (plassens).

**Footeren viser datoen alene** — klokkeslettet står i tooltipen.

---

## 2026-09-11 — Bygg og dato i footeren, og en planleggingstabell som ikke klemmes

**1972 tester grønne** (13 nye). To punkter fra André.

**Footeren viser bygg og dato** — «Sanitetsportalen · adm · a03b5e5 ·
11.09.2026 10:15». Det er svaret på «er dette den nye koden, eller cachen?».
`core/versjon.py` prøver tre kilder i rekkefølge: `bygg.json` skrevet i
byggfasen på Railway (`nixpacks.toml` kjører `core/skriv_bygg.py`, som bare
bruker standardbiblioteket — et Django-oppsett i bygget ville gjort footeren
til en grunn til at deployen feiler), så `git` i arbeidskatalogen, så
`RAILWAY_GIT_COMMIT_SHA` alene med `manage.py` sin mtime som dato. Ingen
kilde gir «ukjent», ikke tomt. Regnes ut én gang per prosess.
- **Første deploy med `nixpacks.toml` må ses på.** Fila legger bare til ett
  byggsteg etter «install», og Python-provideren oppdages som før — men det
  er første gang bygget har en egen fase. Feiler steget, står footeren
  likevel med SHA fra miljøet.

**Planleggingstabellen på mobil.** «Veldig tett»: den arvet `min-width: 0`
fra drifttabellen, og `table-layout: fixed` delte 308 px likt på seks
kolonner — 51 px hver, «Korteste hvile» i tre linjer over et tall. Nå har
den egen klasse med gulvbredde og kolonneandeler, så den ruller i ramma på
en telefon i stedet for å klemmes, som ressurstabellen gjør.
- **«Fortsatt litt overlapp»** etter første runde: målt i iPhone-viewport
  var det overskriftene «Lengste skift» (114 px) og «Korteste hvile»
  (123 px) som skrev seg over nabocella — `thead th` er `nowrap`. Denne
  tabellen får bryte i hodet, gulvbredden er 38rem, og de to kolonnene fikk
  19 % hver. Målt etterpå: ingen celle flyter over.

**Footeren første gang på staging:** «8447399 · 11.09.2026 12:34» — det
er byggtiden i norsk tid (pushen gikk 10:34 UTC), altså riktig, og det
viser at byggsteget i `nixpacks.toml` kjørte.

---

## 2026-09-11 — Tidsblokker, slutt-tid i «Ny vaktliste», og «8,5 t» overalt

**1956 tester grønne** (25 nye, fem mutasjoner satt rødt først). Tre punkter
fra André etter at han hadde brukt modulen i prod.

**«Ny vaktliste» spør om slutten.** Feltet fantes, men bare bak «Vaktas
lengde» inne i innstillingsvinduet — og han fant det ikke. Dialogen har nå
«Slutter (planlagt)» rett under «Starter»; `opprett_planlagt_vakt` tar det
imot og håndhever samme regel som endringsendepunktet: slutten må komme etter
starten.

**Skift med samme fra–til samles i tidsblokker.** Mange på en vakt deler tid,
og en liste der «fre. 20:00 – lør. 04:00» sto på fire rader under hverandre
var lang og lik — man så ikke skiftbyttet før man hadde lest hver rad.
`_tidsblokker()` grupperer på *likhet* (ikke overlapp — et skift som slutter
en time før de andre er sitt eget), og `_blokklinje()` skriver tiden, timene
og antallet én gang over blokka: «Fre 2. okt 20:00 – lør 3. okt 04:00 · 8 t ·
4 satt opp · 1 ledig». Gjelder ressursfanene i planlegging og drift, og
utskriftslista. Radene under er hvem.
- Driftraden mistet «Skift» og «Timer» — de står på blokklinja — og
  drifttabellen ble fem kolonner. Planleggingsraden ble hevet ut til
  `_planrad()`; den er uendret, men står ikke lenger inne i `mkRessurs()`.
- Utskriftslista mistet kolonnen «Tid» av samme grunn, og fikk sum timer
  per ressurs i overskriften og for hele vakta i arkhodet.

**Ett timeformat: «8,5 t».** Ressurstabellen skrev komma, planleggingsfanen
skrev «8.5». `_tall()` er nå det ene stedet, og `_varighet()` går gjennom den.

**Rettet på veien:** «1 ledige» og «1 ledige plasser» i oversikten.

**Ordene, samme dag:** «Skift må vel tolkes som ulike vakttider, og
personell som mannskap.» Tellingene skrev «9 skift» om ni rader. Nå er et
skift en blokk — én vakttid — og mannskap er de bemannede radene:
«2 skift · 5 mannskap · 70,8 t · 1 ledig». Over hele vakta er skiftene de
*ulike* vakttidene, så samme spenn på samleplassen og bilen er ett skift.
`_telling()` er det ene stedet; gruppehodet, ressursoverskriften, arkhodet,
blokklinja og innstillingsvinduet bruker den. Belastningsfanen står som
før — der er «skift» per person nettopp skift.

**På en telefon henger ingen kolonne fast.** André så merknadskolonnen følge
med når tabellen rullet på mobilen, og ville ikke ha noe som fulgte. I
Chromium med iPhone-viewport er det bare blyantcella som er sticky, så det
han ser er trolig en WebKit-forskjell jeg ikke kan gjenskape her — men
sticky-kolonnen ble laget for laptopen, og på 390 px tar den en sjettedel
av det synlige. Under 768 px slås begge sticky-reglene av, cella og hodet.

---

## 2026-09-11 — Vaktlistemodulen merget til prod

`rollemodell` → `main` (`567ee11`). 33 commits, 66 filer, 18551 linjer.
Hele `vaktliste`-appen var **ny for prod** — den fantes ikke på `main` i det
hele tatt. Elleve migrasjoner gikk ut: `vaktliste.0001`–`0010` og
`accounts.0015` (det nye nivået `skriv_leder`, rent additivt).

Innholdet er vaktliste fase 1–6 — registre og planleggingsside, tilgangsmodellen
med badge og reservasjon, drift med stemplingsregler som data, planleggingstall
som varsler uten å sperre, og besetning i sentralbordet. Med på lasset:
lesbare cron-feil (`core/kommando.py`), sperren mot stille SQLite-tilbakefall i
`settings.py`, og migrasjonsprøvene mot ekte PostgreSQL.

**Verifisert før merge**, fordi `vaktliste.0007` tok ned release-fasen én gang:
1931 tester grønne, `verifiser_migrasjoner` OK, full migrasjon fra tom base mot
PostgreSQL 16, og en oppgraderingssimulering — en base migrert til `main`,
seedet med prod-lignende rader (brukere, tilganger, vakt, pasienter), deretter
migrert med den nye koden. Elleve migrasjoner OK, alle rader intakt, de seks
ressursgruppene seedet riktig.

Backup av prod tatt av André før pushen. Pushen ble holdt igjen til den var
bekreftet: push til `main` *er* deployen, og elleve migrasjoner er ikke noe man
angrer på uten backup.

---

## 2026-08-30 — «Ingen biler oppkoblet» var feil vakt, ikke feil oppsett

**1931 tester grønne** (13 nye, fire mutasjoner satt rødt først). Meldt av
André: han hadde koblet bilene, men sentralbordet sa at ingen var koblet.
Hans egen mistanke — at det hang sammen med at han hadde planlagt en vakt
fram i tid — var riktig.

**Reprodusert:** vakta han planla er `er_aktiv=False`, og sentralbordet scoper
til portalens **aktive** vakt. Koblingen lå i den planlagte vaktlista og var
derfor usynlig.

**Scopingen er riktig og beholdes.** Å vise oktobers besetning på tavla mens
man kjører i kveld ville vært verre enn å vise ingenting.

**Meldingen løy ved å tie.** «Ikke koblet til en ressurs i denne vakta» leses
som «koblingen din er ødelagt», og sendte André ut på jakt etter en feil som
ikke fantes. Endepunktet skiller nå mellom to helt ulike problemer:

- **Koblet i en annen vakt:** navngir vakta og sier hva som må gjøres — «bytt
  den aktive vakta i vaktadministrasjonen, eller koble enheten i vaktlista for
  vakta som går nå».
- **Ikke koblet noe sted:** et oppsett som mangler, som før.

Klienten viser serverens tekst uendret. Skrev den sin egen generiske, forsvant
nettopp forklaringen som gjør forskjellen.

**Ryddet på veien:** `koblet_i_annen_vakt()` hadde en `exclude()` på den aktive
vakta som ikke lot seg sette rød — kallstedet garanterer allerede at den aktive
vakta ikke har ressursen. En gren ingen test kan nå er en gren man ikke kan
begrunne, så den er borte.

---

## 2026-08-30 — Vaktliste fase 6: besetning i sentralbordet

**1918 tester grønne** (16 nye, ni mutasjoner satt rødt først). Ingen migrasjon
— `Ressurs.enhet` har pekt på `oppdrag.Enhet` siden fase 2.

113 klikker på en enhet i sentralbordet og ser hvem som er i bilen: navn,
rolle og innsjekkstatus, med de som faktisk er der øverst.

- **Avhengighetsretningen går én vei: `vaktliste` → `oppdrag`** (§6).
  Oppdragsmodulen importerer ikke vaktlista; sentralbordet henter
  `/vaktliste/api/enhet/<pk>/besetning/` og rendrer svaret. Koblingen ligger i
  nettleseren, ikke i Python — samme grep som lot statistikkappen slutte å
  importere pasientmodulen. `OppdragImportererIkkeVaktlista` leser importene
  med AST og håndhever det.
- **Gaten er `les` i vaktliste, ikke i oppdrag.** Komposisjonsregelen fra
  rollemodellen §5: en operatør med oppdragstilgang men uten vaktlistetilgang
  får ikke avledet innsyn i hvem som går vakt — panelet finnes ikke for henne.
- **Svaret er innskrenket med vilje.** Navn, rolle og innsjekkstatus. Ikke
  telefonnummer, ikke kompetanseliste, ikke `notat`: sentralbordet skal se om
  bilen er klar, ikke lese personalmapper. En test leser rå-svaret og krever
  at ingen av feltene er der.
- **Bare skiftene som dekker nå.** «Er bilen bemannet» er et annet spørsmål
  enn «hvem har vakt i helga», og en liste med tretti rader over to døgn
  svarer ikke på noe man kan handle på.
- **Ukoblet er ikke ubemannet.** 404 mot 200-med-null: ubemannet er et problem
  her og nå, ukoblet er et oppsett som mangler, og de to skal ikke se like ut.
- **Hentes når operatøren spør**, ikke ved hver polling — enhetslista pollet
  hvert par sekund ville gitt ett kall per bil per runde. Bufferet tømmes når
  lista faktisk endret seg, *etter* 304-sjekken; tømte vi det på hver runde,
  ville et åpent panel stått på «Henter…» for alltid.

**Rettet før det rakk ut:** første utgave sorterte besetningen på
`rolle__navn`, som er nullbar — og **SQLite (dev) og PostgreSQL (prod)
plasserer NULL i hver sin ende**. Lista ville stått i ulik rekkefølge lokalt og
i drift, en feil man aldri ser før den betyr noe. Sorteres nå i Python: de som
er i bilen først, så alfabetisk.

**Og en test som ikke målte noe:** «ressurs i en annen vakt teller ikke» ga
begge ressursene samme navn, så den gikk grønt uansett hvilken endepunktet
fant. Funnet ved mutasjonstesting, to ganger — andre forsøk trengte også
`rekkefolge=0` på den andre raden for at den skulle vinne uten vaktfilteret.

---

## 2026-08-30 — Vaktliste fase 5: planleggingstall

**1902 tester grønne** (45 nye, sytten mutasjoner satt rødt først). Ny fane
«Planlegging»: hva vakta koster dem som går den.

- **Per person: timer, skift, lengste skift, korteste hvile.** Sortert på
  timer synkende — den som er i ferd med å bli brukt opp skal ligge øverst,
  ikke på rad tolv i en alfabetisk liste.
- **Varsler, ikke sperrer.** Et skift over grensa eller en hvile under den
  merkes, og det er alt. Ingenting avvises: noen ganger *må* noen ta et langt
  skift, og da skal lista si det høyt framfor å tvinge planleggeren til å lyve
  om tidene for å komme videre. Fargen er **gul, ikke rød** — et langt skift
  er ikke galt, det er noe man skal se og ta stilling til.
- **Grensene er organisasjonens, ikke portalens.** Ny modell
  `Belastningsgrenser` (migrasjon `0010`), én rad, standard 12 t skift og 8 t
  hvile. `skriv_leder` flytter dem: det endrer hva *alle* vaktlister varsler
  om, og er en beslutning om hvordan organisasjonen bemanner.
- **Faktisk mot planlagt.** Har noen stemplet både møtt og av vakt, kommer en
  «Faktisk»-kolonne opp ved siden av planen. Et *pågående* skift får ingen
  faktisk tid — et anslag som endrer seg mens man ser på det er ikke et tall.
  Kolonnen står bare når det finnes noe å vise; en kolonne med bare streker
  stjeler bredde fra dem som betyr noe.
- **Ledige plasser telles i sammendraget, ikke i persontabellen.** De er et
  behov, ikke en belastning, og en rad uten navn i en persontabell ser ut som
  en feil.
- **Overlapp gir hvile 0, ikke et negativt tall.** To lister på samme tid er
  noe planleggeren skal se, men et negativt tall i en «korteste hvile»-kolonne
  ser ut som en regnefeil framfor et varsel.

**To lærdommer, begge fra mutasjonstesting:**

- Sorteringen inne i `_hviletider()` lot seg fjerne uten at noe ble rødt,
  fordi `Vaktpost.Meta.ordering` alt sorterer på `fra_tid` — testene gjennom
  basen målte *modellens* ordering, ikke hjelperens. Nå prøves hjelperen
  direkte, med usortert inndata.
- `test_steget_er_et_helt_minutt` leste *alle* `step="…"` på sida, og ble rød
  den dagen et `<input type="number">` fikk `step="1"` — riktig for et tall,
  meningsløst for et klokkeslett. Den leser nå bare `datetime-local`-felt.

**Ikke levert, og det står i notatet:** kompetansedekning per ressurs («har
samleplassen helsepersonell hele åpningstiden») er merket som mulig utvidelse,
ikke første leveranse.

---

## 2026-08-30 — Drifttabellen bytter form

**1857 tester grønne** (6 nye, fem mutasjoner satt rødt først). André: «Møtt-
knappen er ikke helt på plass ennå.» Han hadde rett, og målingene sa hvorfor.

**Slik den var:** 45 × 21 px — den *minste* kontrollen på raden — på x=1092,
mens navnet sto på x=41. Tusen piksler fra navnet du leser til knappen du skal
treffe, og bak en sidescroll, siden tabellen er 1377 px og ruller på både 1440
og 1180 px. På skjermen leste den som enda en liten grå knapp etter
Timer/Kompetanse/Merknad.

**Slik den er:** 171 × 44 px på x=49, først i raden, og tabellen får plass
uten sidescroll.

- **Tabellen har to former, og drift er den andre.** Under drift legges
  planleggingsfeltene bort: tidene vises som tekst i stedet for
  `datetime-local`, og kompetanse og merknad tas ut. Det er de tre som gjør
  raden 1377 px bred, og ingen av dem røres mens man sjekker folk inn. Uten
  dem er det plass til at stempelet kan være stort.
- **Lista kan fortsatt endres** — folk uteblir og bytter — men gjennom
  blyanten, som åpner redigeringsvinduet.
- **Uten stemplerett vises statusen** i stedet for en knapp. `les` ser hele
  lista, og «hvem har møtt» er samme spørsmål enten man kan svare på det eller
  ikke.

**Lærdom:** jeg leste notatet for tynt. Det sto «to store knapper per rad,
**ikke et redigeringsskjema**», og jeg behandlet den andre halvdelen som en
omskrivning av den første. Den var en egen instruksjon om *raden*. Da jeg i
forrige runde begrunnet én knapp med at «to knapper i en kolonne på 5 % blir
to små knapper», var den riktige slutningen at kolonnen var feil — ikke at
knappen skulle bli én.

---

## 2026-08-30 — Vaktliste fase 4: drift

**1851 tester grønne** (45 nye, sytten mutasjoner satt rødt først). Modellen
bar feltene fra fase 2, så fasen er endepunkter og flate — **ingen migrasjon**.

- **Drift er en innsjekk-port, ikke en livssyklus** (§5). `POST
  .../drift/start/` og `.../drift/stopp/` — retningen står i URL-en, ikke i
  kroppen: et veksle-endepunkt gir et kappløp når to trykk kommer tett, og den
  som trykket sist vet ikke hva hun endte på. Ut av drift er reversibel og
  **rører ingen stempler**; det er en dør, ikke en sletting.
  - Knappen står ved statuslinja den endrer. Lå den i «Innstillinger», måtte
    man åpne et vindu for å se om innsjekken var åpen — og det er det første
    man vil vite når vakta begynner.
- **Møtt og av vakt, som navngitte overganger.** Ett endepunkt per overgang,
  og kroppen leses ikke — samme grep som oppdragsmodulens stemplinger.
  Reglene er **data** i `services.STEMPLINGER`, ikke `if`-er i viewet.
  - Forutsetningene er ikke pedanteri: «av vakt» uten «møtt» gir en rad som
    sier at noen gikk av en vakt hun aldri kom til, og `er_tilstede` leser
    nettopp de to feltene sammen. Å angre «møtt» mens «av vakt» står gir
    samme rad. Begge stenges ett sted.
  - To trykk på samme knapp gir samme rad, ikke en rød boks — men det første
    tidspunktet er det som skjedde, og det flytter seg ikke.
- **Korps-føreren stempler ikke** (avklaring 11.3). Hun setter opp sine egne
  folk, men «Tilstede nå» er brannsikkerhet, og det tallet skal ha én
  ansvarlig — ikke ett per korps. Verifisert i nettleseren: hun ser hverken
  drift-knappen eller stemplene.
  - Tilgangsporten svares **før** driftporten, med vilje: en korps-fører som
    trykker skal få vite at hun ikke har lov, ikke at lista ikke er i drift —
    et råd som fører henne til en knapp hun heller ikke har.
- **«Tilstede nå» — modulens mest alvorlige visning.** Tellingen står øverst,
  stor: i en evakuering teller man hoder mot et tall. Definisjonen er
  knivskarp — møtt, og ikke gått av vakt — og utledet av stemplene, aldri
  lagret. Lista er gruppert på ressurs og kan skrives ut; strøm og nett er det
  første som ryker i nettopp situasjonen den finnes for.
  - Fanen finnes bare i drift. I planlegging er den tom per definisjon, og en
    fane som alltid sier null er en fane man slutter å se.
  - Den er lesbar for alle med `les`. I en evakuering er flere lesere bedre
    enn færre, og det er samme data lista alt viser.

**Ett avvik fra notatet, med vilje.** Det ba om «to store knapper per rad».
Det ble **én** — den som gjelder nå — pluss en liten angre. Raden er i
nøyaktig én tilstand: «Møtt» på en som alt har møtt gjør enten ingenting eller
noe hun ikke ba om, og to knapper i en kolonne på 5 % blir to *små* knapper,
altså det motsatte av bestillingen. Stemplene står i handlingskolonnen, som er
`sticky` og den ene som aldri ruller bort.

---

## 2026-08-30 — Cron-jobbene skal si hva som gikk galt

**1806 tester grønne** (12 nye). To cron-jobber i staging — `purge_old_logs` og
`kollaps_arkiv` — falt på `FATAL: password authentication failed for user
"postgres"`. Årsaken var en feil `DATABASE_URL` på cron-tjenestene, og André
rettet den i Railway. Det som er gjort her, er å sørge for at neste gang blir
lettere å se.

- **Én lesbar linje i stedet for fire stablede tracebacks.**
  `core/kommando.py::lesbar_dbfeil()` gjør en `OperationalError` om til en
  `CommandError`: jobben avslutter fortsatt med kode 1 og meldes fortsatt som
  feilet, men loggen sier hva som ikke ble gjort, hvorfor, og hva man skal se
  på. Psycopg2 gjentar seg selv — den gjentakelsen klippes bort, og
  `raise … from` beholder hele sporet for den som vil ha det.
  - **Alle tre jobbene bruker den**: `purge_old_logs`, `kollaps_arkiv` og
    `db_backup`. Den som blir glemt er den som feiler uleselig den dagen det
    haster, og for backupen er «den dagen» per definisjon en dag noe alt har
    gått galt.
- **Den stille SQLite-fallbacken er stengt.** `dj_database_url.config()`
  faller tilbake til en fil i containeren når `DATABASE_URL` mangler. På
  Railway er den filen tom og flyktig — og fallbacken er *stille*.
  `purge_old_logs` ville talt null rader i en tom base, skrevet «Slettet 0
  audit-logger» og avsluttet med kode 0: **en grønn jobb som aldri håndhever
  lagringstidene i A.9.** Det er en verre feil enn krasjen, fordi den ikke
  oppdages før noen spør hvorfor det ligger fire år med logger i basen.
  Oppstarten stopper nå høylytt, som ved manglende `SECRET_KEY`.
  - Sjekken henger på `RAILWAY_ENVIRONMENT`, ikke på `DEBUG`: offline-modus
    kjører `DEBUG=False` på en laptop og *skal* bruke SQLite.

**Lærdom, funnet ved mutasjonstesting:** offline-testen gikk grønt uansett
hvordan sjekken var skrudd sammen, fordi utviklermiljøet kjører `DEBUG=True`.
Den beviste ingenting før den satte `DEBUG=False` eksplisitt. Samme feil som
sist runde: en test kan gå grønt uten å teste formen den beskriver.

**Merk at `ALLOWED_HOSTS` ikke var årsaken** — den leses av request-håndteringen,
og en cron-container betjener aldri en forespørsel. Det står fortsatt et eget
punkt i TODO om å ha både `portal.sanitet.net` og Railway-domenet der til
domenet er verifisert.

---

## 2026-08-30 — Tidsfeltene: fem minutter, og datoen står der

**1794 tester grønne** (7 nye). Andrés punkt: `datetime-local` er fin på mobil
og knotete på desktop. Feltet er beholdt som det er — samme native velger,
samme visning — men to ting rundt det er endret.

- **`step="300"` på alle sju tidsfeltene.** Piltastene og velgeren hopper fem
  minutter, ikke ett. En vakt planlegges ikke på minuttet, og standardsteget
  gjorde et kvarter til tolv piltrykk. Steget er et multiplum av 60, så feltet
  får *ikke* et sekundsegment i tillegg. Verifisert i nettleseren:
  `08:00 → 08:05 → 08:20`.
- **«Opprett vakt» står på vaktas startdato**, ikke på klokka nå. Feltet var
  tomt, så hele datoen måtte tastes for hvert eneste skift — tolv siffer der
  fire holder. Vaktas start og ikke `new Date()`: en oktobervakt planlegges i
  august, og «i dag» er da et årstall på avveie.
  - Fikset på veien: feltene sto helt urørt ved åpning, så de bar tidene fra
    forrige gang vinduet var åpent — på en annen bil, i en annen gruppe.
- **Et eldre skift på 08:03 blir ikke rørt.** `step` styrer bare hva
  piltasten og velgeren *tilbyr*; verdien vises og leses tilbake som før.
  Nettleseren regner feltet som ugyldig, men ingenting leser
  `checkValidity()` og ingen CSS farger `:invalid`. Notert i malen, fordi en
  framtidig `was-validated` ville gjort de radene røde uten grunn.

Vaktas egen start og slutt er fortsatt `datetime-local` med full dato: de
settes én gang per vakt, og der *er* datoen informasjonen.

---

## 2026-08-30 — Mannskapet flytter inn i planleggingen

**1787 tester grønne** (7 nye, og en håndfull skrevet om). Registersiden
`/vaktliste/registre/` er **lagt ned**; mannskapet er en fane på `/vaktliste/`,
korps og kompetanser ligger i «Innstillinger».

Argumentet for en egen side holdt ikke i bruk: registrene er globale og fanene
gjelder én vakt, men et klikk til registeret kostet deg plassen i
planleggingen — og mannskap og ressurser er nettopp de to man veksler mellom.

- **«Mannskap» er en ekte fane**, ikke en lenke med pil ut av sida. Fanen bærer
  antallet i registeret, tabellen har søk og sortering som før, og skjemaet er
  det samme.
- **Fanen står også når det ikke finnes noen vaktliste**, og velges automatisk
  da. Korps må inn før mannskap, og mannskap før noen kan settes på vakt — lå
  registeret bak en vaktliste, sto man fast på skritt én. Av samme grunn åpner
  «Innstillinger» seg uten en liste; bolkene som gjelder én vakt skjules.
- **Korps og kompetanser ligger i «Innstillinger»**, sammen med
  ressursgruppene. De røres sjelden, og de er portalens oppsett — ikke denne
  vaktas. Lista og skjemaet står i **samme vindu**: vinduet åpnes selv fra
  «Innstillinger», og et tredje lag er ett lag man ikke finner tilbake fra.
- **Tomt register uten korps sier «Legg inn korps»**, ikke «Nytt mannskap».
  Knappen åpnet korpsvinduet uansett — en knapp som gjør noe annet enn det den
  heter, klikker man på én gang og stoler aldri på igjen.
- **En lagret person henter både registeret og vaktlista.** Navn, korps og
  aktiv-flagget står i nedtrekkene på planleggingssiden også; uten begge
  bemannet man fra en liste som var utdatert.
- `vaktliste-registre.js` og `registre.html` er **slettet**, ikke bare koblet
  fra. En fil ingen laster er en fil som råtner uten at noe feiler — en test
  krever nå at de er borte.

Verifisert i nettleseren hele veien: tom portal → korps → kompetanse →
mannskap → fanen ved siden av «Ambulanse», med nedtrekket i planleggingen
oppdatert av lagringen.

---

## 2026-08-30 — Ny ressurs spør bare om det man vet

**1777 tester grønne** (18 nye). Niende runde fra Andrés bruk, og tre punkter
som alle handler om det samme: skjemaet skal ikke be om svar man ikke har ennå,
og knappen skal ikke tilby noe som ikke finnes.

- **«Ny ressurs» spør bare om navn og gruppe.** Reservert korps og enhet i
  oppdragsmodulen sto i opprettelsesskjemaet, men hører hjemme ett nivå lavere
  etter at reservasjonen flyttet til plassen: koblingen settes på den enkelte
  bilen, i «Rediger». Å spørre om dem ved opprettelsen ga et skjema man måtte
  fylle ut før man visste svaret — og det leste som om gruppa *var* enheten.
- **Ingenting opprettes i oppdragsmodulen på veien.** André mistenkte at en ny
  gruppe også lagde en enhet. Verifisert i nettleseren at den ikke gjør det:
  `grupper: 6 → 7`, `ressurser: 0`, `enheter: 0`. Det som *så* slik ut var
  skjemaet over, som ba om en enhet man ikke hadde.
- **Samleplass og KO finnes i ett eksemplar.** Nytt felt
  `Ressursgruppe.flere_enheter` (migrasjon `0009`), av for de to gruppene
  migrasjon `0007` seeder som samlingspunkt for flere korps. «Samleplass 2» er
  ikke en ny samleplass, det er en delt vaktliste ingen leser riktig. Den
  *første* må man fortsatt kunne opprette, så plassen tar slutt først når den
  ene står der. Nye grupper er flåter som standard — huket av i
  gruppevinduet gjør dem til ett eksemplar.
  - Regelen står som **én funksjon** (`gruppaHarPlass()`) fordi den har to
    lesere: knappen inne i fanen og nedtrekket i «Ny ressurs». Første runde
    skjulte bare knappen — og da kunne man fortsatt velge gruppa i nedtrekket,
    altså en regel som var halvveis. Serveren avviser den også: en regel som
    bare finnes i klienten er ingen regel.
  - Sperren er **per vaktliste**. Var den global, kunne neste vakt ikke hatt
    samleplass i det hele tatt.
- **Migrasjon `0009` har dataskrittet sist**, etter `AddField`. Da er det ingen
  skjemaendring igjen som triggerkøen kan avvise — motsatt av `0007`, som måtte
  tømme køen. Kjørt fra bunnen mot ekte PostgreSQL, og
  `verifiser_migrasjoner` går grønt.

**Lærdom:** en test som går grønt kan likevel teste en vei brukeren ikke har.
Første utgave av «den første enheten kan alltid opprettes» leste `mkGruppe()` —
men en tom gruppe har ingen fane, så den koden tegnes aldri. Veien inn til den
første går gjennom nedtrekket, og det var det som måtte testes.

---

## 2026-08-30 — Bil A, bil B, bil C: veien inn var usynlig

**1759 tester grønne** (11 nye). Bare grensesnitt — men det som manglet var det
André satt fast på i flere runder, og det var min feil å ikke se det.

**Modellen var riktig hele tiden: én `Ressurs` per bil, inne i gruppa, hver med
sin egen enhetskobling.** Det var *veien dit* som ikke fantes.

- **Gruppefanen har nå sitt eget hode med «Ny Ambulanse»-knapp.** Den eneste
  måten å legge til en bil på lå sist i fanerekka og het «Ny ressurs». Fra
  inne i «Ambulanse»-fanen så man én rad med knapper og ingen antydning om at
  fanen rommer bil A, bil B og bil C — man trodde gruppa *var* bilen. Hodet
  sier nå «Ambulanse · 3 enheter · 12 skift», og knappen ved siden av lager
  den fjerde.
- **Tomme grupper forklarer hva de rommer.** «Ingen Ambulanse satt opp ennå.
  Hver enhet er sin egen rad her — én per bil, lag eller post — med egne skift
  og egen kobling mot oppdragsmodulen.» Med knappen ved siden av.
- **Enhetskoblingen vises også når den mangler.** Merkelappen sto bare der
  bilen *var* koblet, så den som ikke hadde koblet noe så ingenting — og kunne
  ikke vite at koblingen finnes per bil i det hele tatt. Nå står «Ikke koblet»
  som en stiplet plass som åpner redigeringsvinduet.
- **Ressursgrupper har fått en flate.** `/api/grupper/` fantes fra i går uten
  noe som brukte det — nøyaktig feilen Django-admin ga oss én gang før: et
  register som bare finnes i API-et, finnes ikke for brukeren. Man kunne ikke
  lage «Førstehjelpstelt», bare velge blant de seks migrasjonen seedet.
  Manageren ligger i Innstillinger, med «i bruk»-telling og sletting sperret
  for grupper som er i bruk.
- Tre mutasjoner prøvd, alle røde.

**Lærdom.** Tre runder gikk med til at jeg forsvarte en modell som var riktig,
mens brukeren beskrev at han ikke fant veien inn i den. «Det er ikke synlig»
er ikke en uenighet om arkitektur — det er en feilmelding om grensesnittet, og
den skulle vært lest som det med én gang.

## 2026-08-30 — Utskriftslista sorterer og grupperer på noe som betyr noe

**1756 tester grønne** (8 nye). Bare grensesnitt.

- **Sorteringen stoppet på `fra_tid`.** André så det i sine egne rader: et
  skift som slutter 22:15 lå som nummer tre blant skift som slutter 03:00
  neste dag. Alle begynte 17:00, så de var uavgjort — og resten var
  innsettingsrekkefølge forkledd som sortering. `_skiftrekkefolge()` sorterer
  nå på fra, så til, så navn, og brukes både på arket og i ressurstabellen.
- **Utskriftslista er gruppert på ressurs, ikke på korps.** Den som leser
  lista står ved bilen eller på samleplassen og spør «hvem er her, og når?».
  Korpset er et kjennetegn ved personen, ikke et sted — det er en kolonne nå,
  ikke en overskrift. Overskriften er ressursen, med gruppa og antallet ved
  siden av.
- **En ledig plass viser korpset den er satt av til.** Ellers sto de
  reserverte plassene som «—» på arket, og reservasjonen var usynlig akkurat
  der den skal brukes.
- **Ressurser uten skift tas ikke med på arket.** En tom tabell på papiret er
  en linje man må lese for å se at det ikke står noe der.
- Arkhodet teller ledige plasser — tallet man planlegger etter.
- Tre mutasjoner prøvd. Én overlevde: testen på reservasjonen i lista lette
  etter et korps som også sto på de bemannede radene, så den ville vært grønn
  uansett. Den bruker nå et korps som *bare* finnes på de ledige plassene.

## 2026-08-30 — Reservasjonen ned på plassen

**1748 tester grønne** (10 nye). Migrasjon `vaktliste.0008`, rent additiv.

- **`Vaktpost.korps`: en plass kan settes av til ett korps.** Andrés
  innvending, og den var riktig: `Ressurs.korps` reserverer *hele* ressursen
  til ett korps, men en samleplass bemannes av flere. Uten dette måtte
  samleplassen deles i én ressurs per korps — og da er den ikke lenger én
  samleplass. Nå kan den ha to plasser til Haugesund og én til Karmøy, i
  samme tabell.
- **De to nivåene slås sammen ett sted**, `services.reservert_korps()`. Tom
  verdi på plassen betyr «som ressursen», ikke «ingen» — ellers ville alle
  eksisterende plasser blitt fritt vilt ved oppgraderingen. Migrasjonen er
  derfor ren `AddField`: oppførselen er uendret til noen faktisk setter et
  korps på en plass.
- **Å reservere er å dele ut, og krever `skriv_full`.** Korps-brukeren fyller
  plassene som er satt av til henne; hun bestemmer ikke hvilke. Mutasjonstesting
  avslørte at den første testen min ikke prøvde regelen i det hele tatt —
  plassen tilhørte et annet korps, så inngangsporten stoppet henne før
  reservasjonssjekken. Testen som faktisk biter bruker en plass hun *får* ta
  i, og viser at hun likevel ikke kan skrive om hvem den tilhører.
- **Korpskolonnen svarer nå på to ulike spørsmål.** Står det en person der, er
  det *hennes* korps — et faktum. Er plassen ledig, er det korpset plassen er
  *satt av til* — en beslutning, redigerbar i raden for den som deler ut.
- **«Sett på vakt» heter nå «Opprett vakt».** Knappen lager en plass, som ofte
  er tom; «sett på vakt» lovet en person.
- **Kurven tegnes selv når gruppa ennå ikke har et eneste skift.** Den falt
  bort i akkurat den tilstanden man setter opp i, og det var feil på samme
  måte som at kurven en gang bare dekket skiftene: hullet man planlegger for å
  tette er størst når ingen er satt opp, og da forsvant hele kurven.
- Tre mutasjoner prøvd. Én overlevde og fikk testen beskrevet over.

## 2026-08-30 — Fanen er gruppa, ikke bilen

**1737 tester grønne** (23 nye). Bare grensesnitt.

- **Én fane per ressursgruppe, ikke per ressurs.** «Ambulanse» er nå alle
  ambulansene som skal på vakt, med hver bil som sitt eget kort inni. Én fane
  per bil ga ti faner på en vakt med ti biler, og ingen plass der man kunne se
  dem i sammenheng — som er nettopp det man planlegger etter. Gruppekurven
  ligger øverst i fanen, over de ressursene den summerer, og tallet på fanen
  teller skiftene i hele gruppa.
- **Det som er per ressurs blir stående på ressursen.** Enhetskoblingen mot
  oppdragsmodulen, korpsreservasjonen, rollene og «Sett på vakt» hører til den
  enkelte bilen, og ligger derfor på kortet inne i fanen — ikke på gruppa.
- **«Ny ressurs» forhåndsvelger gruppa du står i.** Står du i
  «Ambulanse»-fanen er det oftest en ambulanse til du skal lage. Det er
  fortsatt et nedtrekk, så den første ressursen i en ny gruppe har også en vei
  inn. Etter opprettelsen åpnes gruppas fane; sletter du den siste ressursen i
  en gruppe, forsvinner fanen og «Oversikt» tar over.
- **Innstillinger står nå til venstre for «Ny vaktliste».** Begge handler om
  vakta som helhet, og hører derfor på vaktlinja.
- **Mannskap er flyttet inn i fanerekka, rett etter «Oversikt»** — dit man
  veksler oftest. Den er fortsatt en lenke og ikke en fane, og bærer en liten
  pil: fanene bytter innhold i panelet under, denne forlater sida. Uten pila
  koster et klikk deg plassen din uten å ha spurt.
- Fem mutasjoner prøvd, alle røde: bare første ressurs vist i fanen, tomme
  grupper som faner, fanetallet som bare teller én ressurs, Mannskap flyttet
  ut av posisjon, og pila fjernet.
- **En feil jeg gjorde underveis, verdt å notere:** da jeg byttet ut hele
  regionen mellom to funksjoner, forsvant `visFane`, `_ikkePlassert` og
  `skrivUt` med den. Testene fanget det umiddelbart — men et
  `git diff | grep '^-function'` før commit er billigere enn å lete i en rød
  suite.

## 2026-08-30 — «Ny ressurs» inn i fanerekka, Mannskap ned til fanene

**1728 tester grønne** (5 nye). Bare grensesnitt.

- **«Ny ressurs» står sist i fanerekka**, som pluss-fanen i en nettleser. Den
  lå til høyre for hele rekka og leste som enda en handling på sida; en
  ressurs *er* en fane, så knappen hører hjemme der fanene slutter. Stiplet
  kant skiller den fra fanene som faktisk er noe.
- **Tilgangen måtte flytte med.** Knappen lå i malen og ble skjult av
  `gateKnapper()` ved sidelasting. `tegnFaner()` tegner på nytt ved hvert
  panelbytte, så en klasse satt én gang rekker ikke over den — `kanLede()`
  sjekkes nå rett i byggeren. Mutasjonstestet: uten sjekken ser bemanneren en
  knapp som gir 403.
- **Mannskap er flyttet ned til fanene, men står utenfor rekka.** Fanene
  bytter innhold i panelet under; Mannskap forlater sida. En knapp som ser ut
  som en fane og navigerer bort er en felle — den har derfor skillelinje foran
  og beholder knappeformen. Nærheten er poenget: fanene og
  mannskapsregisteret er de to stedene man veksler mellom.

## 2026-08-30 — Rediger-knappen innenfor skjermen, og en topp som er ryddet

**1723 tester grønne** (2 nye). Bare grensesnitt.

- **Ressurstabellen krympet fra 82rem til 66rem.** Den første verdien hadde
  slark: tidsfeltene fikk 210 px der de trenger 185, og prisen var at
  rediger-knappen i siste kolonne lå utenfor skjermen selv på en stor laptop.
  Målt i nettleseren nå: tabellen ruller ikke i det hele tatt fra 1280 px og
  opp, mot 1600 px før.
- **Og handlingskolonnen henger fast til høyre.** Under 1280 px ruller
  tabellen fortsatt, og da var rediger-knappen det første som forsvant — altså
  den ene knappen raden finnes for. `position: sticky` holder den i syne;
  bakgrunnen settes eksplisitt, ellers ruller innholdet synlig under den.
  Verifisert med tabellen rullet helt til venstre på 1000 px.
- **Toppen av siden er tre nivåer i den rekkefølgen man tenker.** Før lå alt
  på én linje: hvilken vakt man planla, hvem man er, hva man vil lage — og
  vaktas navn sto midt inne i en knapperad og leste som en innstilling. Nå:
  sida øverst (Mannskap, Innstillinger), så en egen linje for vakta med
  velgeren, statusen og «Ny vaktliste», og til slutt fanene med «Ny ressurs»
  ved siden av seg. «Ny ressurs» hører til fanene fordi en ressurs *er* en
  fane; «Ny vaktliste» hører til velgeren fordi den lager noe velgeren skal
  peke på.
- **«Vakta» heter nå «Innstillinger».** Et substantiv blant handlinger, og
  det sa ikke hva som lå bak.
- **Kurven er ute av «Oversikt».** Den sto samlet der før hver gruppe fikk sin
  i sin egen fane, og to steder å lese den samme kurven er ett for mye. På
  papiret var den uansett skjult, så «Oversikt» er nå utskriftslista og bare
  det. `mkKurve()` er slettet framfor å bli stående ubrukt.
- Tre mutasjoner prøvd, alle røde — for smal tabell, tidskolonner krympet på
  bekostning av «Timer», og kurven snek tilbake inn i «Oversikt».

## 2026-08-30 — Rediger skiftet, og en kurve som sier når

**1722 tester grønne** (15 nye). Ingen migrasjon — alt ligger i grensesnittet;
serveren tok allerede alt redigeringsvinduet trenger i én PUT.

- **Skiftet redigeres, det slettes ikke og settes opp på nytt.** Å bytte
  person på en rad krevde før å fjerne den og begynne forfra — og da mistet
  man tidene og rollen som allerede sto der. Blyanten i raden åpner et vindu
  med mannskap, rolle, tider og merknad; alt går i ett kall, og serveren
  sjekker den doble regelen på nytt mot den som skal inn. Å velge «— ledig
  plass —» tar personen av uten å miste plassen i oppsettet.
- **Sletting av et skift ligger inne i vinduet, bak en bekreftelse.** Samme
  grep som på ressursen: den nakne søppelbøtta i raden var ett feilklikk fra
  å fjerne noe.
- **Bemanningskurven står i fanen den gjelder.** Ambulansefanen viser
  ambulansenes kurve, samleplassen sin. Å lete etter samleplassens bemanning
  under «Oversikt» mens man bemanner samleplassen er ett skifte for mye.
  «Oversikt» viser fortsatt alle gruppene samlet, til den som vil sammenligne
  dem.
- **Klokkeslett under søylene, og toppen oppgitt med tidspunkt.** «topp 4
  plasser kl. 14:00–18:00» svarer på spørsmålet kurven finnes for; å lese det
  av søylehøyder er å gjette. Timeaksen har én celle per søyle med samme
  flex-bredde, så tallet står under den timen det gjelder — målt i nettleseren
  på tvers av alle søylene. Tettheten glisner med lengden (hver time opp til
  14, deretter hver andre, fjerde, sjette): tall som står oppå hverandre gjør
  kurven uleselig av å være «mer informativ».
- **Den hvite streken er midnatt, ikke nåværende tidspunkt.** André måtte
  spørre, og en strek man må spørre om forklarer ingenting — den står nå i
  tegnforklaringen. Den er beholdt: arrangementer varer flere døgn, og
  døgnskillet er det man orienterer seg etter.
- Fem mutasjoner prøvd. Én overlevde — at bare første klokkeslett ble skrevet
  ut — fordi testen talte celler og ikke hvor mange som hadde tall i seg. Den
  teller nå begge deler.

## 2026-08-30 — Migrasjonsprøver mot ekte PostgreSQL

**1713 tester grønne** (4 nye, én hoppes over uten PostgreSQL). Lukker hullet
den statiske regelen fra forrige runde ikke nådde.

- **`core/migrasjonsprover.py` + `python manage.py verifiser_migrasjoner`.**
  Hver migrasjon som skriver rader og deretter endrer skjema må ha en prøve:
  `foregaaende` sier hvor basen settes, `seed` legger inn rader i den
  *historiske* formen med rå SQL, `sjekk` leser hva migrasjonen gjorde med
  dem. Kommandoen lager sin egen engangsbase, kjører prøven, og sletter den —
  den rører aldri basen URL-en peker på.
- **Å kjøre testsuiten mot PostgreSQL ville ikke fanget feilen.** Det var det
  TODO-punktet sa, og det var feil. Djangos testbase lages ved å kjøre
  migrasjonene mot en *tom* base: dataskrittet finner ingenting å flytte,
  skriver ingenting, og fyller ingen triggerkø. Feilen krever tre ting
  samtidig — PostgreSQL, rader, og en skjemaendring etter skrivingen — og det
  er nettopp de tre prøven setter opp.
- **Prøven kjører `migrate` i en underprosess mot `default`**, ikke som et
  andre databasealias. Atten migrasjoner i prosjektet gjør ORM-kall i
  `RunPython` uten `schema_editor.connection.alias`, altså mot `default`; med
  et alias ville de skrevet til utviklerens egen base i stedet for prøvebasen,
  og prøven ville målt noe annet enn den later som. Underprosessen kjører
  dessuten nøyaktig den stien release-fasen kjører.
- **Fem mutasjoner, alle røde.** To fanges ved at migrasjonen kræsjer —
  deriblant «hjelperen står, men kallstedet er fjernet», som er akkurat det
  den statiske regelen *ikke* ser. Tre fanges av påstandene: ukjent
  ressurstype som faller til feil gruppe, en pensjonert rolle som blir aktiv
  i kopien, og roller som ikke viftes ut til alle grupper. De tre migrerer
  helt fint og gir bare gale data — den slags feil finnes det ellers ingen
  sperre mot.
- **Testsuiten håndhever registeret**, ikke bare regelen: en ny migrasjon med
  mønsteret må ha en prøve, en prøve må peke på en migrasjon som finnes, og
  `foregaaende` må finnes. Uten det tredje feiler prøven på sitt eget oppsett
  og ser ut som dekning man ikke har.
- Kjøres med `MIGRASJONSPROVE_DATABASE_URL` satt; hoppes over ellers.
  Serveren kan være en lokal PostgreSQL eller en egen Postgres-tjeneste i
  Railway — se CLAUDE.md.

## 2026-08-30 — Deployfiks: migrasjonen som kræsjet på PostgreSQL

**1709 tester grønne** (3 nye). Ingen ny migrasjon — `vaktliste.0007` er rettet
på plass, og den har aldri blitt anvendt noe sted.

- **`vaktliste.0007` tok ned deployen i crash-loop.** PostgreSQL svarte
  `cannot ALTER TABLE "vaktliste_ressursrolle" because it has pending trigger
  events`. Årsaken: Djangos fremmednøkler er `DEFERRABLE INITIALLY DEFERRED`,
  så hver skriving i dataskrittet legger en triggerhendelse i kø som først
  fyres ved commit — og migrasjonen er én transaksjon. `ALTER TABLE` på en
  tabell med hendelser i køen avvises. Løst med `SET CONSTRAINTS ALL
  IMMEDIATE` mellom dataskrittet og skjemaskrittene, i begge retninger.
- **Reprodusert før den ble rettet.** En lokal PostgreSQL 16 ble satt opp,
  basen rullet tilbake til `0006`, ekte rader lagt inn — ressurser, en rolle,
  vaktposter — og `0007` kjørt: samme feil, ord for ord. Etter rettelsen går
  den gjennom, dataene står riktig (rollene viftet ut per gruppe, hver
  vaktpost på sin egen gruppes kopi, `gruppe_id` NOT NULL, `type`-kolonnen
  borte), og veien tilbake til `0006` virker også. Hele historikken kjører
  dessuten rent fra tom base.
- **Databasen trengte ingen opprydding.** Migrasjonen er atomisk, så den
  rullet helt tilbake ved hver feilede oppstart; basen sto på `0006`.
- **Testsuiten kunne ikke se feilen, og det er det egentlige problemet.**
  SQLite har ingen utsatte triggere — en migrasjon som rører rader og deretter
  endrer skjema er noe dev-basen ikke kan si noe om i det hele tatt.
  `DataOgSkjemaISammeTransaksjonTests` flytter regelen inn i suiten: skriver en
  migrasjon rader og gjør noe som blir til `ALTER TABLE` etterpå, må den enten
  tømme køen, sette `atomic = False`, eller deles i to. Åtte eldre migrasjoner
  har mønsteret og står i `KJENTE_UNNTAK` — alle er anvendt i produksjon, og
  hele historikken er kjørt fra null mot PostgreSQL for å bekrefte at de ikke
  feller på en tom base.
- **Mutasjonstesting fant en svakhet i sperren.** Første versjon lette etter
  strengen i fila, og gikk grønn når kallet ble fjernet mens docstringen som
  *forklarer* regelen sto igjen. En migrasjon som omtaler sperren er ikke en
  migrasjon som har den. Nå leses fila med AST, og strengen må stå som
  argument i et kall. Grensen som står igjen er notert i testen: den ser at
  kallet finnes, ikke at det kjøres — det krever å kjøre suiten mot
  PostgreSQL, som nå står i TODO.

## 2026-08-30 — Ressursgrupper, et ledernivå, og en popup som blinket bort

**1706 tester grønne** (49 nye). Migrasjoner `vaktliste.0007` og
`accounts.0015`. Femte runde på Andrés tilbakemelding, og den største:
tilgangsmodellen fikk et trinn til, og ressurstypen ble en tabell.

- **Ressurstypen er nå tabellen `Ressursgruppe`.** Den lå i `choices.py` med
  den begrunnelsen at et nytt ikon uansett krever deploy. Den holdt ikke: et
  arrangement kan ha et førstehjelpstelt eller en MC-patrulje, og en vaktleder
  som trenger gruppa i kveld kan ikke vente på en utrulling. Ikonet ble et
  felt — feil ikon er en skjønnhetsfeil, en manglende gruppe er en vaktliste
  man ikke får satt opp. Gruppa gjør tre ting samtidig, og det er derfor den
  er én ting: den ikonlegger fanen, den samler bemanningskurven, og den
  avgrenser rollene.
- **Rollen hører til gruppa, ikke til portalen.** «Sjåfør» gir mening på hver
  ambulanse og ikke på samleplassen. Gruppa er riktig nivå og ikke den enkelte
  ressursen: har du tre ambulanser vil du lage rollen én gang, ikke tre.
  Manageren åpnes derfor inne i ressursen — «Roller»-knappen i kortets topp —
  og navnet er unikt *per gruppe*. Migrasjonen vifter hver eksisterende rolle
  ut til alle seks gruppene og peker vaktpostene på kopien som hører til sin
  egen ressurs' gruppe. Å gjette hvilken gruppe «Lagleder» *egentlig* hørte
  til ville tatt rollen bort fra rader som lovlig brukte den; noen ubrukte
  rader man kan slette er den billige feilen.
- **Nytt nivå: `skriv_leder` («Skrive: leder — setter opp vakta»).** Det
  fjerde trinnet i `NIVAA_HIERARKI`, og det første siden stigen ble laget.
  Skillet mot `skriv_full` er hva slags skade en feil gjør: bemanneren setter
  folk på plasser og kan rette tilbake; lederen oppretter og fjerner ressurser
  og vaktlister, endrer vaktas lengde og lager roller og grupper — og en
  fjernet ressurs tar bemanningen med seg. `skriv_full` beholder alt som
  handler om å bemanne, inkludert utskriften. Terskelen er ikke global admin,
  og det er hele poenget: en vaktleder skal kunne sette opp sin egen vaktliste
  uten å få brukeradministrasjon, backup og arkiv på kjøpet. Vaktlista er den
  eneste modulen som deklarerer nivået, så det er additivt for de andre.
- **«Fjern ressurs» ligger bak «Rediger ressurs», og krever bekreftelse to
  ganger.** Knappen sto naken ved siden av «Sett på vakt», og CASCADE tar
  skiftene: ett feilklikk kostet hele bemanningen på bilen. Nå må man inn i
  vinduet, bekrefte i dialogen, og serveren krever i tillegg
  `{"confirm": true}` — dialogen stopper feilklikket, kroppen stopper et kall
  som treffer URL-en uten å mene det.
- **Vaktas lengde og utskriften er samlet i ett vindu for vakta.** To løse
  knapper i toppen konkurrerte med «Ny ressurs» om plassen uten å høre til
  samme spørsmål. Utskriften er åpen for alle som ser lista — den er hele
  grunnen til at bemanneren har den; lengden inne i vinduet krever
  `skriv_leder`.
- **Kolonnene i ressurstabellen leser nå som ett strekk:** Navn, Korps, Rolle,
  Fra, Til, Timer, Kompetanse, Merknad. «Dag» er borte som egen kolonne — den
  var et tredje sted å lese for å forstå én rad, og `datetime-local` bærer
  datoen selv; det manglet bare ukedagen, som nå står under feltet den hører
  til. «Timer» er nytt, og er det ene tallet man ellers regner ut i hodet for
  hver rad: «20:00 til 04:30» er ikke åtte timer.
- **Kompetansekolonnen flyttet seg fordi cella var `display: flex`.** En
  `<td>` med flex slutter å være en `table-cell` og faller ut av kolonnesporet,
  så alt etter den forskyves i forhold til overskriftene — `table-layout:
  fixed` hjelper ikke mot det. Layouten ligger nå på et element *inne* i cella.
  `TabellcellersLayoutTests` leser hvilke klasser som står på `<td>`-ene og
  krever at ingen av dem får en `display` som bryter tabellen, så neste
  cellemerkelapp fanges av samme test.
- **Bemanningskurven følger grupperingen.** Én samlet kurve summerte
  samleplassen, ambulansene og KO til ett tall, og det tallet svarer ikke på
  noe: fire på samleplassen og null på ambulansen ser likt ut som to og to.
  Kurvene deler spenn, så søylene ligger under hverandre — to kurver man ikke
  kan sammenligne er verre enn én samlet. Grupper uten et eneste skift tegnes
  ikke.
- **«En kort popup som forsvinner» var to lyttere på samme element.**
  Nedtrekkene i ressurstabellen er `<select data-action="…"
  data-hendelse="change">`, og klikkdelegeringen i `portal-utils.js` traff dem
  også: klikket som åpnet lista kalte handlingen uten felt og verdi, sendte en
  tom PUT, og tegnet panelet på nytt — så lista ble revet bort i det øyeblikket
  den kom. Regelen er nå `klikkSkalKjore()`: et element som melder sin egen
  hendelse fyrer ikke på klikk. Den traff hver celle i tabellen, ikke bare
  nedtrekket, så hvert klikk i et tekstfelt kostet en tom skriving og en full
  ny-tegning.
- Elleve mutasjoner prøvd. Én overlevde — kompetansecellas layout — og fikk
  testen over. Verifisert i nettleser: kolonnene står på linje med
  overskriftene på 1600, 1280 og 1000 px, og klikk på nedtrekket gir null kall
  og null ny-tegninger.

## 2026-08-30 — Ressursroller, og kolonner som blir stående

**1659 tester grønne** (12 nye). Migrasjon `vaktliste.0006`. Fjerde runde på
Andrés tilbakemelding, og den korteste: to ting han pekte på etter å ha brukt
planleggingssiden.

- **`VaktRolle` heter nå `Ressursrolle`.** Navnet var misvisende på den måten
  navn er farlige: rollen gjelder plassen på ressursen — lagleder *på bilen*,
  sjåfør *på bilen* — ikke vakta. «Vaktrolle» leste som noe man har på hele
  vakta, og en modul der to begreper heter nesten det samme får de to
  forvekslet før den får dem forklart. Migrasjonen er en ren `RenameModel`;
  ingen rad flyttes.
- **Rolleadministrasjonen flyttet fra registersiden til planleggingssiden.**
  Rollene brukes der ressursene settes opp, og de var det eneste registeret man
  måtte forlate siden for å endre. Nå ligger de bak «Roller» i toppen av
  `/vaktliste/`, med «i bruk»-tellingen i lista — en rolle man kan slette uten å
  se hvor mange skift som peker på den, sletter man for lett. Registersiden har
  tre faner igjen: mannskap, korps og kompetanser.
- **Nedtrekket i raden tilbyr bare aktive roller — pluss den raden alt står
  på.** Uten det siste ville en deaktivert rolle forsvunnet fra sin egen rad ved
  første tegning, og en tilfeldig annen rolle blitt valgt neste gang noen rørte
  cella.
- **Kolonnene i ressurstabellen flyter ikke lenger inn i hverandre.** Årsaken
  ble målt i nettleseren, ikke gjettet: `datetime-local`- og tekstfeltene var
  bredere enn cellene sine på alle skjermbredder. `min-width` opp til `82rem`,
  `<colgroup>`-andelene rebalansert, og `box-sizing: border-box; min-width: 0`
  på feltene. Målt igjen på 1600, 1280 og 1000 px: ingen kolonne beveger seg,
  ingen felt stikker ut.
- **To mutasjoner overlevde første runde, og fikk hver sin test.**
  `RessurstabellensBreddeTests` regner ut hva tidskolonnene faktisk blir i
  piksler av `min-width` og `<colgroup>`-andelene, og krever at de rommer et
  datetime-felt — den låser *regelen*, ikke tallene, så en rebalansering som
  fortsatt holder er lov. `RollenedtrekketTests` kjører filteret i node.

## 2026-08-30 — Vaktlengde, ledige plasser og en kurve over hele vakta

**1647 tester grønne** (33 nye). Migrasjon `vaktliste.0005`. Tredje runde på
Andrés tilbakemelding, og den som endret modellen mest.

- **`Vaktpost.mannskap` er nullbar: en ledig plass er et skift som mangler en
  person.** Planlegging begynner med behovet — «Lag 1 trenger fire, én av dem
  lagleder» — og personene fylles inn etter hvert. En egen plassholder-modell
  ville duplisert tider, rolle og ressurs, og gjort «å fylle plassen» til en
  flytting mellom to tabeller i stedet for én feltendring. `antall` lager flere
  like plasser i ett kall; NULL er ikke lik NULL i unik-skranken, så fire tomme
  plasser til samme tid går fint.
- **Vakta kan få og endre en lengde.** Starten redigeres på `Vakt.startet` — den
  *er* starten — mens planlagt slutt er et nytt felt på `Vaktliste`.
  `Vakt.avsluttet` betyr «vakta ble avsluttet», en hendelse noen utløste, og kan
  ikke bære et anslag man flytter på mens man planlegger. Året følger starten,
  fordi vakta kan flyttes over et årsskifte og `year` er portalens scope-nøkkel.
- **Kurven dekker hele vakta, ikke bare skiftene**, og viser to tall per time:
  fylte plasser i mettet farge, alle plasser i lys. Avstanden mellom dem er det
  som gjenstår å bemanne. Uten vaktas spenn var hullet i begynnelsen usynlig
  nettopp fordi ingen er satt opp der ennå. Mangler sluttiden, faller den
  tilbake på skiftene — bedre en kurve som dekker for lite enn ingen kurve.
- **Utskriftslista holdes i sin egen ramme.** Tabellene arvet `min-width` fra
  `.vl-tabell` uten en ramme rundt seg og stakk ut av kortet; på papiret
  nullstilles begge deler. Ledige plasser samles i sin egen gruppe til slutt —
  de hører ikke til noe korps ennå.
- **Regelen måtte deles i to, funnet av en ny test.** `kan_sette_vaktpost` spør
  om et *par* kan opprettes (og `mannskap=None` er å planlegge, altså
  `skriv_full`). `kan_rore_vaktpost` spør om brukeren får ta i en rad som
  finnes. Brukt den første til begge, låste den korps-brukeren ute av akkurat de
  plassene som var satt av til henne. Og å *avlyse* en ledig plass er
  `skriv_full`: korpset fyller plasser, det skjuler ikke hull ved å slette raden
  som viste dem.
- Mutasjonstestet åtte veier, alle røde.

---

## 2026-08-30 — Planleggingssiden: regneark, datoer, utskrift og bemanningskurve

**1614 tester grønne** (15 nye). Kun frontend og serialisering — ingen migrasjon.
Andre runde på Andrés tilbakemelding.

- **Ressursen er et regneark.** Rader er skift, kolonner er det man
  sammenligner på tvers av dem: Navn · Korps · Kompetanse · Rolle · Dag · Fra ·
  Til · Merknad. Rolle, tider og merknad redigeres **der de står** — cellene ser
  ut som celler til man er i ferd med å endre dem. Avviser serveren endringen
  (et skift som slutter før det begynner), rulles raden tilbake til det som
  faktisk er lagret, og meldingen står over tabellen.
- **Rollen flyttet dit arbeidet skjer.** Den lå allerede riktig i modellen — på
  vaktposten, ikke på personen — men i grensesnittet kunne den bare settes i
  «Sett på vakt»-modalen. Å endre den krevde å fjerne skiftet og sette det opp
  på nytt. Samme person er sjåfør på bilen én vakt og lagleder på samleplass
  neste.
- **Kompetansekolonnen** følger vaktposten, så et lags sammensetning kan
  vurderes uten å bla til registeret. Stigen gjelder også her: AFØR skjuler GFØR.
- **Dato og dag, ikke bare klokkeslett.** Et skift lørdag 20:00 til søndag 04:00
  sto som «20:00–04:00», uten at noe sa at det krysset midnatt. Dagen nevnes én
  gang når skiftet holder seg innenfor et døgn og to ganger når det ikke gjør
  det; vaktvelgeren viser datoen; vaktas spenn utledes av skiftene framfor å
  være et felt noen må vedlikeholde.
- **«Oversikt» er utskriftslista.** Hele vakta på ett ark, gruppert på korps,
  med en «Skriv ut»-knapp. `@media print` fjerner nav, faner, knapper og kurve —
  en knapp på et ark er bare blekk — og en korpsgruppe brytes ikke over to sider.
- **Bemanningskurven** står over lista: én søyle per time, døgnskillet markert,
  hullene synlige. Rene CSS-søyler framfor Chart.js, som kun lastes på
  `/statistikk/`.
- **To kanter funnet av de nye testene.** `new Date(null)` gir epoken (1970), ikke
  en ugyldig dato — et tomt tidsfelt ville vist «01:00» i stedet for ingenting.
  Og `toISOString()` i `datetime-local`-feltene ville gitt UTC og flyttet hvert
  skift to timer om sommeren.
- Mutasjonstestet ni veier, alle røde til slutt. Den ene som ikke bet med én
  gang — kompetansene fjernet fra vaktpost-svaret — avdekket at
  ressurstabellens data var utestet; fem nye tester dekker den nå, inkludert at
  PUT-svaret har samme form som lesestien (ellers ville kolonnen tømt seg selv
  i det man endret rollen).

---

## 2026-08-30 — Mannskapstabellen: kolonnene flyter ikke lenger inn i hverandre

**1599 tester grønne** (4 nye). Kun frontend.

Meldt av André: en person med mange kompetanser blåste opp kompetansekolonnen
og skjøv telefon og konto ut av linje med radene over — nøyaktig det tabellen
skulle løse.

- **Årsaken var `table-layout: auto`.** Der sizer nettleseren kolonnene etter
  innhold, og `max-width` på en `td` er bare et forslag. Nå `table-layout:
  fixed` med et `<colgroup>` som setter andelene, så innholdet brytes inni cella
  i stedet for å dytte naboene. Målt i nettleser på 1400, 1000 og 780 px: alle
  radene har identiske kolonneposisjoner, og ingenting flyter ut av cella.
- **Handlingsknappene ble ikoner.** «Rediger» + «Slett» som tekst trenger
  ~150 px og sprengte sin egen kolonne på smal skjerm. `title` og `aria-label`
  bærer betydningen, og knappene har fast bredde så kolonnen ikke hopper mens
  ikonfonten laster.
- **Fire regresjonstester**, fordi hver av bitene ser overflødig ut ved siden av
  de andre: `table-layout: fixed` ser unødvendig ut når det står et `<colgroup>`
  der, og omvendt. Begge trengs — den ene slår av innholdsbasert sizing, den
  andre sier hva andelene skal være.

Sidevis vannrett rulling på 780 px kommer fra portalens header, ikke fra
tabellen, og bare i testmiljøet: Bootstrap-CSS er CDN-sperret der, så
brukermenyen står åpen i stedet for skjult.

---

## 2026-08-30 — Registersiden: kompetansestige og mannskapstabell

**1595 tester grønne** (15 nye). Migrasjon `vaktliste.0004`. Første runde på
Andrés tilbakemelding fra å faktisk bruke modulen.

- **Mannskapslista er en tabell.** Med én kompetanse så den gamle
  merkelapp-raden fin ut; med åtte brøt den om og skjøv telefonnummeret ut av
  syne. Faste kolonner — Navn · Korps · Kompetanse · Telefon · Konto — gjør at
  det du leter etter alltid står samme sted. Sticky kolonnehode, sortering på
  navn/korps/telefon, og et søkefelt som filtrerer på alt inkludert kompetanse.
  Søkefeltet ligger **utenfor** panelet som tegnes på nytt; lå det inni, mistet
  det fokus etter første bokstav.
- **`Kompetanse.bygger_paa`: en stige, ikke en rangering.** AFØR bygger på VFØR,
  som bygger på GFØR. Har personen AFØR, er de to under implisert og vises ikke
  — hele settet ligger i `title` på cellen, så «har hun egentlig VFØR?» kan
  besvares uten å åpne skjemaet. En peker framfor et rangtall fordi et tall
  måtte være globalt, og da ville «Sykepleier» og «Sjåfør kode 160» fått en
  innbyrdes rekkefølge de ikke har. Ringer stoppes ved skriving; en ring som
  likevel finnes i basen gir en avkortet kjede, ikke en evig løkke. SET_NULL:
  fjernes VFØR, står AFØR igjen frittstående.
- **Funn i nettleseren, ikke i testene: registerfanene viste «ubrukt» på et
  korps med mannskap.** Siden tegner dem fra mannskapsendepunktets nyttelast,
  ikke fra `/api/korps/`, og de to formene var skrevet hver for seg — så
  `i_bruk` og `bygger_paa_navn` nådde aldri fram. Hver test spurte det
  endepunktet den selv beskrev, og så det ikke. Nå deler begge veier én
  `verdi_til_dict()`, og `SammeFormBeggeVeierTests` sammenligner dem direkte.
- Mutasjonstestet seks veier på stigen, alle røde: stigen ignorert, kjeden
  avkortet til ett trinn, sykkelvernet fjernet, «bygge på seg selv» sluppet
  gjennom, ringvernet i kjeden fjernet, og CASCADE i stedet for SET_NULL.

---

## 2026-08-30 — `rekkefolge` ut av verdimengdene: alfabetisk holder

**1580 tester grønne** (6 nye). Migrasjon `vaktliste.0003`.

**Andrés innvending, og den var riktig.** Feltet ga allerede alfabetisk: hver
rad sto på standardverdien 100, så `ordering = ['rekkefolge', 'navn']` falt
uansett tilbake på navnet. Det vi hadde var altså alfabetisk sortering med et
tallfelt i skjemaet som pris — et felt du måtte se på og lure på hva «100»
betyr mens du skrev «Sykepleier».

- **Fjernet fra `Korps`, `Kompetanse` og `VaktRolle`.** Ingen tallfelt igjen i
  grensesnittet. Trygt å droppe kolonnene: modulen har aldri vært i prod.
- **Beholdt på `Ressurs`, men brukeren skriver ikke tallet.** Der *betyr*
  rekkefølgen noe — den styrer fanene på planleggingssiden — og alfabetisk ville
  stokket om på den operative rekkefølgen («Ambulanse, KO, Lag 1, Mannskapsbil
  1» framfor samleplass, biler, lag, KO). `services.neste_rekkefolge()` setter
  den til «sist», så fanene følger den rekkefølgen du la ressursene inn i.
  Steget på 10 gir plass til å skyte inn en ressurs den dagen noen vil
  omorganisere.
- **Funn fra den nye testen: «alfabetisk» er databasens alfabet.** SQLite
  sorterte «Åsen» før «Ærlig» og ville sortert «karmøy» etter begge; PostgreSQL
  svarer annerledes på begge. Sorteringen bruker derfor `Lower(...)`, som gjør
  store/små bokstaver deterministisk i enhver base. **Æ/Ø/Å står vi igjen med
  databasens svar på** — en ekte norsk kollasjon krever en sorteringsnøkkel eller
  `db_collation`, og for en håndfull korps er det ikke verdt det. Notert i TODO.
  Testen sier det samme: den prøver store/små bokstaver, ikke æ/ø/å, fordi en
  test på det siste ville målt hvilken base som kjørte den.
- Mutasjonstestet fire veier, alle røde: `Lower()` fjernet, `neste_rekkefolge`
  som alltid gir 10 (kolliderende faner), telling på tvers av vaktlister, og
  ressursen tilbake på fast 100.

---

## 2026-08-29 — Vaktlistemodulen fase 3: tilgangsmodellen tas i bruk

**1574 tester grønne** (48 nye). Ingen migrasjon. `admin_only` er av — modulen
er åpen for nivåene.

Fase 2 skrev reglene og lot dem stå ubrukte bak en admin-gate; fase 3 håndhever
dem, per objekt, på hvert endepunkt. Tre terskler, og skillet mellom dem er
*hva slags utsagn* nivået får avgi:

| Handling | Krav |
|---|---|
| Lese lista og registeret | `les` — hele lista, **alle** korps (§4.4) |
| Bemanne en ressurs, føre eget mannskap | badge **og** reservasjon (§4.2) |
| Dele ut ressurser, planlegge vakt, styre verdimengdene | `skriv_full` |
| Slette en vaktliste | global admin — irreversibelt |

- **Den doble regelen håndheves nå der den står i veien for noen.** Badgen på
  personen *og* reservasjonen på ressursen, som én funksjon
  (`services.kan_sette_vaktpost`). En ureservert ressurs er fortsatt ikke et
  fristed.
- **Verdimengdene er `skriv_full`.** Kunne korps-brukeren opprette korps, kunne
  hun lage seg et nytt å føre — og badgen hennes ville sluttet å avgrense noe.
  Samme resonnement stengte «endre reservasjonen på en ressurs»: den korteste
  veien rundt hele regelen er å sette `korps` på KO til sitt eget og bemanne den
  etterpå.
- **To felter på `Mannskap` er unntatt badgen.** `korps_id` sjekkes mot *begge*
  korps — sjekket vi bare det personen har i dag, kunne hun eksporteres ut av
  rekkevidde; bare målet, og andres kunne hentes inn. `user_id` er `skriv_full`
  fordi koblingen flytter en badge: kontoen arver korpset, og dermed hva *den*
  kontoen får redigere. Sperren står både på POST og PUT — ellers er den ene
  bare en omvei rundt den andre.
- **§4.5 løst: etikett per modul per nivå.** `Module.nivaa_navn` er par framfor
  `dict` fordi dataklassen er frosset og hashable. Matrisen og «Min profil»
  viser nå «Skrive: eget korps» på vaktlista og «Skrive: stempling» på oppdrag,
  der begge før het «Skrive: handling». Nivået er det samme; betydningen er det
  ikke, og den som deler ut skal se hvilken.
- **Grensesnittet gater på `window.MODUL_TILGANG`**, og badgen sendes med slik
  at nettleseren kan regne ut det samme som `kan_bemanne_ressurs()`.
  Verifisert i nettleser som korps-bruker: «Sett på vakt» vises kun på egen
  ressurs, «Ny vaktliste»/«Ny ressurs» og kontofeltet er borte, og Rediger/Slett
  står bare på eget korps sine folk.
- **Kontolista sendes bare til den som kan bruke den.** `user_id` er
  `skriv_full`-felt, og en liste over portalens brukernavn er ikke noe en
  korps-fører trenger for å føre lista si.
- Mutasjonstestet tolv veier. Elleve bet; den tolvte — reservasjonssjekken
  fjernet fra JS-ens `kanBemanne()` — gjorde det **ikke**: serveren stoppet
  kallet uansett, så hullet var kosmetisk. Men det er nettopp den slags hull som
  overlever til noen stoler på grensesnittet, så JS-gatingen kjøres nå i node
  (`GrensesnittetsGatingTests`), og de tre JS-mutasjonene bet etterpå.

---

## 2026-08-29 — Registersiden: portalen får tilbake det Django-admin gjorde

**1534 tester grønne** (43 nye). Ingen migrasjon. Ny side på `/vaktliste/registre/`.

**Funnet av André, og det er et hull fase 1 og 2 begge gikk forbi.** Registrene
kunne bare fylles fra Django-admin, og den flaten er kun rutet under `DEBUG` og
`OFFLINE_MODE` (S1). I produksjon fantes det altså ingen vei til å opprette et
korps eller et mannskap i det hele tatt — planleggingssiden hadde en
nedtrekksliste som aldri kunne fylles, og banneret på den pekte brukeren mot en
dør som ikke finnes. Fase 1 skrev til og med i `admin.py` at Django-admin var
«riktig hjem» for registrene.

**Ingen test var rød.** Alle testene laget radene sine med ORM-en, så ingen av
dem gikk den veien en bruker må gå. Testene på registersiden går derfor gjennom
HTTP hele veien — fra tom base til bemannet vakt — og
`SjekkAtIngenPekerPaaDjangoAdminTests` skanner alle maler for at det ikke skal
skje igjen.

- **Mannskapslista er gruppert på korps med kompetansene synlige**, ikke en flat
  admin-tabell: det var slik bestillingen beskrev den. Inaktive rader vises
  nedtonet framfor å forsvinne — pensjonering er den normale veien ut, ikke en
  feiltilstand, og raden må kunne leses av den som skal aktivere den igjen.
- **Egen side, ikke en fane på planleggingssiden.** Registrene er globale;
  fanene på `/vaktliste/` er ressursene i én vakt. To omfang i samme faneliste
  ville sagt at «Mannskap» hører til oktobervakta.
- **De tre verdimengdene deler fabrikk** (`_register_views`), som
  `patients/views_registre.py` gjør for navneregistrene. Korps har ett felt til,
  og fabrikken tar derfor en liste over valgfrie tekstfelter framfor å bli to
  fabrikker.
- **Sletting er ikke veien ut av et register.** `Korps`, `VaktRolle` og
  `Mannskap` er PROTECT-et, og `Kompetanse` blokkeres eksplisitt selv om M2M-en
  ikke ville protestert — å slette den ville stilltiende strippet kompetansen fra
  alle som har den. Antall bruk vises i lista, ikke bare i feilmeldingen: en
  verdimengde man kan slette uten å vite hva som henger i den, sletter man for
  lett.
- **Funn underveis, fanget av en av de nye testene:** et HTML-nedtrekk med «Ingen
  valgt» sender `''`, ikke `null`. Sendt rett inn i et FK-filter kaster Django
  `ValueError`, og brukeren fikk 500 der hun skulle fått «velg korps». Alle
  ID-er fra klienten går nå gjennom `_int()` — også i planleggingsviewene, der
  `or None` dekket den tomme strengen, men ikke en ikke-numerisk.
- Mutasjonstestet seks veier. Fem bet med én gang; den sjette — korps som teller
  bare mannskap og ikke reserverte ressurser — gjorde det **ikke**, fordi
  `ProtectedError`-fallbacken ga 409 uansett. Testen sjekket bare statuskoden.
  Den leser nå `i_bruk`-tallet, som er det eneste telle-sjekken faktisk styrer:
  uten den står et korps som eier et lag oppført som «ubrukt», og da trykker man
  slett i god tro.

---

## 2026-08-29 — Vaktlistemodulen fase 2: oppsettet og planleggingssiden

**1491 tester grønne** (68 nye). Migrasjon `vaktliste.0002`. Siden ligger på
`/vaktliste/`, og modulen er synlig for global admin.

Tre modeller til: `Vaktliste` (1:1 med `core.Vakt`), `Ressurs` og `Vaktpost`.

- **Reservasjonen er `Ressurs.korps`** (§4.2 i notatet). `skriv_full`/admin deler ut
  et lag eller en bil til et korps; korps-brukeren bemanner bare det som bærer hennes
  egen badge. **Tom er ikke fritt fram** — det er vaktlederens bord, typisk KO og
  samleplass. Motsatt tolkning ville gitt enhver korps-bruker de to ressursene ingen
  hadde tenkt å dele ut.
- **Den doble regelen er én funksjon.** `services.kan_sette_vaktpost()` sjekker både
  badgen på personen og reservasjonen på ressursen, slik at et endepunkt ikke kan huske
  den ene og glemme den andre. Reglene håndheves først i fase 3 — modulen er admin-only
  til da, fordi et nivå som slipper inn uten korps-regelen ville gitt korps-brukeren
  *alle* korps.
- **«Ny planlagt vakt» rører ikke portalens peker.** `opprett_planlagt_vakt` lager en
  `core.Vakt` med `er_aktiv=False` og lar `aktiv_vakt_id` stå: oktobervakta skal kunne
  planlegges i august uten at pasienter og oppdrag registrert i dag scopes til den.
  Dette er portalens andre sted som lager `Vakt`-rader, og det er notert i TODO sammen
  med `hent_aktiv_vakt`.
- **Kopiering tar oppsettet, aldri personene.** En liste ingen har sagt ja til er verre
  enn en tom liste — den ser ferdig ut.
- **Plan og faktisk er fire felter, ikke to.** `fra_tid`/`til_tid` er planen,
  `mott_at`/`av_vakt_at` hva som skjedde. Avviket mellom dem er selve informasjonen.
  Feltene finnes fra denne fasen, men ingen sti setter dem før fase 4.
- **Et skift er én rad.** Går Per to skift på bilen, er det to `Vaktpost`-rader. Det er
  det som gjør timer, hviletid og skiftlengde (§8b) til spørringer i stedet for tolkning.
  Overlapp *på tvers av* ressurser stoppes bevisst ikke — planleggingstallene flagger det.
- **Funn underveis: `IntegrityError` må fanges rundt et savepoint.** Uten
  `transaction.atomic()` rundt skrivingen er transaksjonen ubrukelig etter at skranken
  slår til, og sesjonslagringen på vei ut av forespørselen river feilmeldingen bort og
  etterlater en naken 400-side. Feilen var usynlig for en test som bare leste
  statuskoden; testene leser nå `message`.
- **Ryddet en stale import**: `myproject/tests_cache_config.py` importerte fortsatt
  `patients.stats_cache`, som flyttet til `core` da statistikk ble sin egen app. Testen
  hadde vært rød siden da, men ligger utenfor den daglige testkommandoen.
- Mutasjonstestet åtte veier, alle røde: ureservert ressurs som fristed, `and` → `or` i
  den doble regelen, kopiering som tar personene, planlagt vakt som blir aktiv,
  opprettelse som flytter pekeren, `<=` → `<` på skifttidene, savepointet fjernet, og
  admin-gaten fjernet fra ett endepunkt.

---

## 2026-08-29 — Vaktlistemodulen fase 1: registrene og mannskapet

**1404 tester grønne** (15 nye). Migrasjon `vaktliste.0001`.

Ny app `vaktliste/` med fire modeller: `Korps`, `Kompetanse` og `VaktRolle` som
admin-styrte tabeller — motsatt av oppdragsmodulens `choices.py`, fordi dette er
organisasjonsdata, ikke faglige verdimengder — og `Mannskap`, portalens tredje
personregister og det første over **egne frivillige**.

- **`Mannskap.korps` er badgen** tilgangsmodellen hviler på fra fase 3. PROTECT:
  korpset skal ikke kunne rives bort under folkene. Navn er unikt per korps, ikke
  globalt — to korps kan ha hver sin Ola Hansen. Kontokoblingen er SET_NULL og gir i
  seg selv ingen tilgang, som `Enhet.user`.
- **`notat` er unntatt verdilogging i audit fra første lagring**, etter mønster av
  `Oppdrag.fritekst` og med samme rekkefølgekrav: kostbehov skal ikke inn i portalen
  (§7 i notatet), og fritekst er der helseopplysninger havner når det ikke finnes et
  felt for dem. Mutasjonstestet begge veier: fjernes unntaket, lekker verdiene til
  loggen og en test blir rød; fjernes rå-sammenligningen, gir hver lagring en falsk
  «notat endret»-rad og en annen test blir rød.
- **Personvernprotokollen hevet til v1.10**: ny A.6-seksjon for mannskapsdata
  (berettiget interesse, art. 6(1)(f) — en annen registrertgruppe enn pasientene) og
  A.9-rader med pensjonering som normal vei ut av registeret.
- **Modulen er registrert, men usynlig**: `url=None` og begge `show_*`-flagg av, som
  oppdragsmodulen i sin fase 1 — den får side i fase 2. Nivåene er deklarert som
  besluttet, med merknad om at `skriv_handling` her betyr «fører sitt eget korps».

---

## 2026-08-29 — Beslutningsnotat: vaktlistemodulen

Ingen kode. `docs/BESLUTNING_VAKTLISTE.md` er skrevet for å gjøre de seks
avklaringene i §11 mulige å svare på, og for å få de to tunge tingene på bordet før
første linje kode — slik oppdragsnotatet gjorde.

**Den ene er tilgangsmodellen.** Bestillingen innfører portalens andre akse: en bruker
fra korps Z skal kunne redigere korps Z og ingen andre. Rollemodellen har hittil hatt
én akse — en ordnet stige per modul — og statistikk ble i sin tid skilt ut som egen
modul nettopp for å slippe to akser i én. Notatet anbefaler å utlede scopet fra
`Mannskap.korps`, altså fra domenedata, framfor å legge det i en tildelingstabell:
da betyr `skriv_korps` noe alene, og det finnes ingen ekstra rad å glemme. Idiomet er
det samme som `Enhet.user` i oppdragsmodulen, der koblingen avgjør hvilket
grensesnitt kontoen får uten selv å gi tilgang.

**Den andre er kostbehov.** Matallergi er en helseopplysning, altså en særlig
kategori etter GDPR art. 9, og dette er første gang portalen ville lagret slikt om
*egne frivillige* framfor om pasienter. Notatet foreslår fem tiltak som må stå før
feltet tas i bruk — smal verdimengde, samtykke som grunnlag, snevrere synlighet enn
resten av lista, unntak fra verdilogging, og ingen arkivering — og legger dem i en
egen fase 2 som står **før** feltet ships. Samme rekkefølgekrav som audit-unntaket i
oppdragsmodulen, av samme grunn: rader skrevet feil kan ikke fjernes i ettertid uten
å røre sporet.

Notatet dekker ellers ordboken (fire ord som ligner: vakt, vaktliste, ressurs,
vaktpost), modellene, livsløpet planlegging → drift, koblingen til `/oppdrag` — som
går én vei, `vaktliste` → `oppdrag`, med panelet hentet i nettleseren slik
statistikkappen gjør — og forholdet til de to personregistrene som finnes fra før.

**Seks avklaringer besvart samme dag, og tre av dem endret utformingen:**

- **Korps er en badge, ikke en ny akse.** Forslaget om nivået `skriv_korps` er
  forkastet: stigen portalen har holder. `skriv_handling` betyr «fører sitt eget
  korps», `skriv_full` «alle korps» — og `skriv_full` er dessuten den eneste som
  stempler møtt og av vakt. Skillet mellom de to skrivenivåene er ikke bredde, men
  art: å føre inn sine egne folk er planlegging, å stemple noen inn er et utsagn om
  hva som faktisk skjedde. Ingen ny verdi i `NIVAA_HIERARKI`, ingen migrasjon.
  Prisen er notert: nivånavnet betyr noe annet her enn i oppdragsmodulen, og matrisen
  viser en global etikett — så det trengs en valgfri etikett per modul per nivå,
  ellers deles nivået ut i god tro med feil forventning.
- **Matallergi lagres ikke i portalen.** Grunnen til at utkastet trengte fem tiltak
  rundt feltet, er også grunnen til at det ble tatt ut: det er en helseopplysning
  etter art. 9, og fem mekanismer for én kolonne som skal brukes til å bestille mat er
  feil pris. Samles inn utenfor portalen. Konsekvensen står i notatet: lista kan ikke
  brukes til matbestilling. Utkastets fase 2 utgår, og personvernarbeidet som blir
  igjen — rader i protokollen, audit-unntak for `notat` — flyttes inn i fase 1.
- **Pasientmodulens to personregistre forblir urørt.** Heller ingen valgfri kobling:
  de svarer på «hvem behandlet pasienten», ikke «hvem er på vakt». Prisen er at et
  navn kan stå to steder, og den er akseptert — en nullbar FK er en additiv migrasjon
  den dagen behovet melder seg.

**Andre runde samme dag besvarte resten, og notatet står som besluttet:**

- **Ressurser reserveres til korps.** `skriv_full`/admin tildeler lag, mannskapsbiler
  og ambulanser til korpsene; korps-brukeren bemanner bare ressurser med sin egen
  badge, med skifttider. KO og samleplass står typisk ureservert og er
  `skriv_full`/admins bord. Regelen er dobbel og håndheves per objekt: personen må ha
  badgen, ressursen må være reservert korpset.
- **Drift er kun en innsjekk-port, og den er reversibel.** «Sett i drift» åpner
  møtt/av vakt, «ut av drift» stenger den igjen; stemplene består. Ingen kobling til
  portalens aktive vakt — spørsmålet fra utkastet falt bort med svaret.
- **To bruksområder kom til:** planleggingstall (timer per person, hviletid mellom
  skift, skiftlengder, bemanningskurve, admin-styrte varselgrenser — varsler, ikke
  sperrer) og en tilstedeoversikt som brukes av brannsikkerhetshensyn ved overnatting.
  Den siste er modulens mest alvorlige flate: definisjonen er «møtt og ikke gått av»,
  utledet av stemplene, med telling øverst og en ren utskriftsvisning — papir er
  reserven når strøm og nett ryker.
- **Kopiering fra forrige vakt:** oppsettet (ressurser, reservasjoner, roller), aldri
  personene.

Et skift er en `Vaktpost` med `fra_tid`/`til_tid`; `mott_at`/`av_vakt_at` er hva som
skjedde. Plan og faktisk holdes atskilt fordi avviket mellom dem er selve
informasjonen. Sju faser, 37–49 timer. Ingen kode er skrevet.

---

## 2026-08-29 — Oppdragsmodulen fase 7: vaktarkiv for oppdrag

**1383 tester grønne** (41 nye). Migrasjon `oppdrag.0008`. Med denne er alle sju fasene
i `docs/BESLUTNING_OPPDRAGSMODULEN.md` levert.

**`AbstractArkiv` er endelig bygget.** TODO har utsatt basemodellen til «modell nummer
to faktisk skrives» — `OppdragArkiv` er modell nummer to, og da var det ikke lenger
gjetning hva som er felles: tittel, vakt med frosset navn, antall rader, hvem som
arkiverte med frosset brukernavn, signatur, kollapstidspunkt og aggregat med egen
signatur. `VaktArkiv` er som planlagt **ikke** migrert dit: `year_snapshot` og
`arrangement_navn` inngår i SHA-payloaden til hvert arkiv i prod, og et arkiv som byttet
feltnavn ville meldt tukling. Duplikatet mellom de to modellene er prisen for at
signaturene fortsatt verifiserer.

- **Arkivet fryser vakta, historikken rydder tavla.** To knapper, fordi det er to
  handlinger: historikk flytter ett oppdrag ut av den aktive lista og er reversibel,
  arkivering fryser hele vakta med signatur og starter klokka mot en kollaps som sletter
  radnivået etter 24 måneder. Oppdrag som ligger i historikken arkiveres selvsagt med —
  de er en del av vakta.
- **Tidspunktene fryses i flate kolonner**, én per status, og hvilke stemplinger som var
  automatiske ligger som data ved siden av. Da gjelder §12.2-regelen også i arkivet:
  uten flagget ville en avledet sluttid blitt telt som målt straks vakta var arkivert.
  En test går gjennom statuskjeden og krever en kolonne for hver — legges en status til,
  må arkivet følge med.
- **`fritekst` arkiveres ikke.** Feltet er unntatt verdilogging i audit nettopp fordi det
  kan inneholde noe en operatør skrev og angret på. Å fryse det i et arkiv med 24
  måneders lagringstid ville gjort unntaket meningsløst.
- **Én utregning, to kilder.** `_stats_fra_rader()` regner på nøytrale dicter, og både
  den aktive vakta og arkivet bygger slike — samme grep som pasientmodulens
  `_compute_full_stats_from_dicts`. En test sammenligner arkivets tall mot live rad for
  rad: arkivering skal ikke endre et eneste tall.
- **Statistikkendepunktet fra fase 6 virker nå**, uten at statistikkappen ble rørt.
  Kollapset arkiv leverer det frosne aggregatet — å regne på ingenting ville gitt nuller
  som så ut som målinger.
- **To mangler kom for en dag underveis**, begge reelle:
  - **Modulen hadde ingen backup i det hele tatt.** Arkivet gjorde det synlig (sperren
    foran kollaps krever en backup av modulens arkiv), men mangelen gjaldt hele modulen:
    en vakts oppdrag lå utenfor all dekning utenom Railways databasebackup, som er aktiv
    én måned i året. Nå finnes `oppdrag` og `oppdrag_arkiv`.
  - **`kollaps_arkiv` kjente bare pasientarkivet.** Kommandoen går nå gjennom
    `core.arkiv`-registeret, kjører sperren per modul og navngir modulen som mangler
    backup. `--modul <slug>` avgrenser. Cron-jobben trenger ingen endring.
- **Scheduleren finner moduler gjennom registeret nå.** Den leste
  `ModuleBackupConfig`-radene direkte, og radene ble opprettet først når en admin åpnet
  `/portal-admin/backup/` — så de to nye modulene hadde ingen automatisk backup før noen
  tilfeldigvis besøkte den siden. For `oppdrag_arkiv` var det verre enn en manglende
  fil: uten backup nekter `kollaps_arkiv` å kjøre, så mangelen ville vist seg som en
  blokkert sletting to år senere. Registeret er fasit for hvilke moduler som finnes;
  konfigraden lages med standardverdier første gang scheduleren ser en handler uten en,
  og admin bestemmer fortsatt intervall og av/på. Mutasjonstestet.
- **En testisolasjonsfeil ble avdekket av de nye testene:** `clear_registry()` i
  backup-testene ble ryddet opp med pasientmodulens `register_handlers()`, så
  oppdragsmodulens handlere forsvant for resten av kjøringen — og feilen dukket opp i en
  helt annen fil. `core.backup.registrer_alle_moduler()` går veien om app-registeret, så
  modul nummer tre ikke må huskes.
- **Dokumentasjonen fulgte med:** personvernnotatet er hevet til v1.9 med reviderte
  A.9-rader (merknaden ba selv om revisjon når fasen var levert), og runbookens §10a har
  fått et punkt som navngir begge arkivknappene. Risikoen for å arkivere det ene og
  glemme det andre står nå der den leses, ikke bare i et beslutningsnotat.
- **Verifisert i nettleser:** arkivering, liste, tallene og signaturen, uten JS-feil.
  Mutasjonstestet: fjernes automatisk-flagget fra arkivet, admin-gaten fra endepunktene
  eller backup-sperren foran kollaps, blir testene røde.

---

## 2026-08-29 — Oppdragsmodulen fase 6: statistikkregisteret og oppdragsfanen

**1342 tester grønne** (46 nye). Ingen migrasjoner.

**Statistikkappen navngir ingen kildemodul lenger.** Den importerte `patients.services`
direkte — det virket så lenge det fantes én kilde, og var samtidig hele grunnen til at
kilde nummer to ikke kunne legges til uten å endre appen. `core/stats.py` er registeret,
samme idiom som `core.backup` og `core.arkiv`: hver modul melder inn en
`BaseStatistikkHandler` fra `apps.ready()`, og handleren eier både utregningen og formen
på payloaden. Pasienttallene flyttet ikke en linje — `full_stats()` ligger fortsatt i
`patients/services.py`, og handleren er koblingen.

- **Endepunktene bærer kilden:** `/statistikk/api/kilde/<slug>/full-stats/` og
  `.../arkiv/<pk>/full-stats/`. Ett endepunkt per kilde, ikke ett samlet: en fane som
  ikke er åpnet skal ikke koste noe, og cache-nøkkelen bærer både slug og vakt-ID — delte
  de nøkkel, ville kilde nummer to servert kilde éns tall i 60 sekunder. De gamle stiene
  videresender (302), av samme grunn som pasientmodulens gjorde da endepunktene flyttet:
  en fane som sto åpen da deployen traff feiler ellers stille.
- **Arkivoppslaget gjør handleren**, ikke statistikkappen — `VaktArkiv` er
  pasientmodulens modell, og det var nettopp den importen som skulle bort. Oppdrag
  arkiverer først i fase 7; basisklassen svarer `None`, som blir 404.
- **Tilgangsregelen måtte endres i samme slengen.** §5 sa «vis kun kilder brukeren kan
  lese», men koden ga 403 på hele siden om én kilde manglet. Det var det samme så lenge
  det fantes én kilde; med to ville det tatt statistikken fra alle som leser pasienter
  uten å ha oppdrag. Nå vises kildene kontoen har, og 403 er forbeholdt «ingen kilder».
  En modul som er slått av i `ModuleSettings` forsvinner fra fanene — `har_tilgang`
  svarer nei for den.
- **Oppdragsfanen** viser responstid (opprettet → fremme), ventetid, utrykningstid, tid
  på stedet og hele oppdraget, fordelinger per hastegrad, problemstilling, lokasjon og
  enhet, status akkurat nå, og oppdrag per klokketime. Egen mal og egen JS-fil, lastet
  kun for kontoer med oppdragstilgang; kall fra `statistikk.js` går gjennom
  `_kallOppdrag()`, samme vern som `_kall()` på pasientsiden.
- **§12.2 er besvart (André): den avledede varigheten utelates, ikke oppdraget.** Trykker
  en enhet «Rykker ut» på et nytt oppdrag mens et annet pågår, lukkes det gamle med samme
  tidsstempel og merkes `automatisk`. Sluttiden er da avledet — mannskapet kan ha vært
  ferdig et kvarter før — så varigheter som *slutter* i en slik stempling telles ikke.
  Oppdraget telles i alle antall og fordelinger, og responstiden fram til «Fremme» teller
  som vanlig. Negative varigheter (en klokke som gikk feil offline) telles heller ikke.
  Begge utelatelsene står på siden: et tall som er utelatt uten at noen får vite det, er
  verre enn et tall som mangler.
- **`Statusmelding.objects.gjeldende_bulk()`** kom til fordi statistikken går gjennom
  hele vaktas oppdrag — ett kall per oppdrag ga én spørring per rad. Regelen «nyeste
  ikke-korrigerte rad vinner» står fortsatt bare i manageren, og `gjeldende()` er nå ett
  oppslag i bulk-resultatet. Låst av en test på manageren selv: statistikken ville
  bestått uten regelen, fordi «siste rad per status» tilfeldigvis sammenfaller med den.
- **Verifisert i nettleser**, ikke bare i testene: fanebytte begge veier, tallene mot
  seedede oppdrag, og at et enhetsnavn med markup vises som tekst.

---

## 2026-08-29 — Vakt som scope, deploy 2: vakta er fasit

**1296 tester grønne** (13 nye/omskrevne rundt vakt-semantikken). Migrasjoner
`patients.0016` og `oppdrag.0007`. Forutsetter «Ingen funn» fra `verifiser_vakt` i prod
— det kom samme dag, og deployen er den lesende halvdelen deploy 1 forberedte.

**Migrasjonene er enveis, med vilje.** Begge starter med en sperre som teller rader uten
vakt og stopper med henvisning til `verifiser_vakt` — kjøres deploy 2 mot en base deploy
1 ikke har fylt, skal den nekte, ikke gjette. Revers rammer `RuntimeError`: etter at
`year` er borte fra radene kan koblingen ikke bygges opp igjen når flere vakter deler år.
Rollback er gjenoppretting fra backup, og det står i feilmeldingen.

- **All lesing går på vakta.** `get_active_year`/`set_active_year` er slettet;
  `hent_aktiv_vakt()` er eneste scope-kilde. Pasientliste, statistikk (cache-nøkkel
  bærer vakt-ID), oppdragsvisninger, arkivering og offline-import filtrerer på
  `vakt`-FK-en.
- **`year` er fjernet fra `Patient` og `Oppdrag`.** `VaktArkiv.year_snapshot` står —
  frosset, fordi den inngår i SHA-payloaden til eksisterende arkiver i prod.
  `verifiser_vakt` er krympet tilsvarende: year-sammenligningene mistet grunnlaget og er
  fjernet (ikke gjemt); igjen står arkiv-mot-vakt, pekersjekken og per-vakt-oppsummering.
- **Sperrene bor i basen:** `UniqueConstraint (vakt, pasientnummer)` og
  `(vakt, oppdragsnummer)` erstatter global `unique=True` og per-år-sperren. Numrene
  restarter per vakt; tellerne heter `next_patient_nr_vakt_<id>` /
  `next_oppdrag_nr_vakt_<id>` og selvrepareres fra `Max()` om nøkkelen mangler.
  Migrasjonene flytter driftsverdiene og sletter `active_year`, `next_patient_nr` og
  `event_name` — arrangementsnavnet ER vaktas navn nå, og skrives via
  portalinnstillingene (som validerer unikhet ved omdøping).
- **«Avslutt vakt» erstatter «Nullstill år»** (`/api/avslutt-vakt/`): pre-reset-backup,
  slett vaktas pasienter, merk avsluttet — og ny vakt med påkrevd, unikt fritekstnavn i
  samme flyt, så portalen aldri står uten aktiv vakt. Oppdragene røres ikke (fase 7 sitt
  ansvar). **«Gjenåpne»** (`/api/gjenaapne-vakt/`) bytter aktiv vakt fram til vaktas
  arkiv er kollapset — da finnes ikke radnivået, og døra er låst (mutasjonstestet).
  Gjenåpning henter ikke slettede rader tilbake; de bor i backupen. «Tidligere
  vakter»-lista (`/api/vakter/`, kun admin) viser status og kollaps per vakt.
- **JS-kontrakten består:** `GET /api/settings/` svarer fortsatt `event_name` og
  `active_year`, nå beregnet fra vakta — klienten skal ikke vite at kilden byttet.
- **Testkulturen fulgte med:** `patients.test_helpers.sett_aktiv_vakt(år)` er den ene
  måten tester setter scope på; `year=`-fixturer og `AppSetting['active_year']`-oppsett
  er skrevet om i alle appene.

---

## 2026-08-29 — Vakt som scope: besluttet, og deploy 1 kodet

**1288 tester grønne** (16 nye). Migrasjoner `core.0006`, `patients.0014–0015`,
`oppdrag.0005–0006`.

**Beslutningen er tatt.** André besvarte de fem avklaringene i §7 — alle med notatets
anbefaling: fritekst-vaktnavn (unikt), gjenåpning fram til kollaps, pasientnummer per
vakt (sperren flyttes i deploy 2), manuell sletting av tomme vakter, ingen gruppering nå.
`docs/BESLUTNING_VAKT_SOM_SCOPE.md` står som besluttet.

**Deploy 1 er den additive halvdelen, og den er bevisst kjedelig:** `Vakt` finnes,
FK-ene skrives — og *ingenting* leser dem ennå. All lesing går fortsatt fra `year`.
Kontrakten i mellomtiden er at `year` og vakta aldri er uenige, og den kontrolleres av
`verifiser_vakt` — som også forhåndssjekker deploy 2-sperrene `(vakt, pasientnummer)` og
`(vakt, oppdragsnummer)`, slik at den migrasjonen ikke kan overraske.

Det som ligger i deployen:

- **`core.Vakt`**: navn (unikt, fritekst), `year` (utledet, men lagret — sesongstatistikk
  skal slippe å regne det ut per spørring), `startet`/`avsluttet`, `er_aktiv`. Bevisst
  ikke `BaseTimeStampedModel`: `startet` er vaktas egen tid, og `created_at` ville løyet
  for backfillede vakter. Bærer ingen personopplysninger.
- **Backfill i to migrasjoner som følger kodens avhengighetsretning**: `patients.0015`
  lager vaktene og kobler pasienter + arkiv, `oppdrag.0006` kobler oppdragene og avhenger
  av den — oppdrag avhenger av patients i kode, og migrasjonsgrafen går samme vei. Navnet
  blir årstallet, ikke `event_name`: den er én global verdi som beskriver vakta som var
  aktiv da noen sist skrev den, og å fryse den inn på historiske vakter ville påstått noe
  vi ikke vet. `startet`/`avsluttet` er estimater fra radenes tidsstempler, redigerbare.
- **Reverseringen nuller FK-ene før vaktene slettes** — `PROTECT` nekter ellers, også i
  en rollback. Bevist mot en base med data i tre år (ett av dem kun som arkiv): backfill,
  full rollback med alle rader intakt, og ny kjøring.
- **Fire skrivestier setter vakta**: pasientoppretting, offline-import (vakta for radens
  *eget* år, ikke den aktive — en import kan bære et annet år), arkivering og
  oppdragsoppretting. Mutasjonstestet: fjernes tildelingen, blir testene røde.
- **`hent_aktiv_vakt()`** i `patients.services`, ved siden av `get_active_year` — flyttes
  til core i deploy 2. Lat opprettelse på fersk base (samme mønster som `get_active_year`
  sin egen AppSetting-rad), og en død `aktiv_vakt_id`-peker repareres i stedet for å
  stoppe registrering: en pasient som ikke lar seg registrere fordi en peker er borte, er
  verre enn en peker som må repareres.
- **`verifiser_vakt`** slår opp modellene via `apps.get_model` i stedet for å importere
  `patients` og `oppdrag` fra `core` — en driftskommando skal ikke snu
  avhengighetsretningen for hele appen. Arkiver uten vakt er info, ikke feil: NULL der
  betyr «fra før grupperingen fantes».

Kjøreplanen står i notatet: deploy 1 ut, `verifiser_vakt` mot prod, og først da deploy 2
— der lesingen bytter kilde, tellerne blir per vakt, «Nullstill år» blir «Avslutt vakt»,
og `year` forsvinner fra radene.

---

## 2026-08-29 — Fase 5: stemplingen overlever at dekningen ryker

**1272 tester grønne** (23 nye). Ingen migrasjon.

Ved knappetrykk skrives stemplingen til `localStorage` **først**, skjermen oppdaterer seg
med en gang, og synkingen skjer i bakgrunnen. Feiler den, blir raden liggende og forsøkes
på nytt — ved neste trykk, ved neste poll, og ved `online`-hendelsen.

**Nøkkelen er det som gjør avspilling trygg.** Den lages ved trykket og beholdes gjennom
hvert forsøk. Serveren kobler den nå til `core.idempotency`, og svarer en avspilling med
`ok` og den **opprinnelige** meldingen i stedet for 409. Uten det kunne køen ikke skille
«allerede levert» fra «avvist fordi skjermen har sakket akterut» — den ville enten hengt
fast, eller kastet en stempling som faktisk kom fram.

**Reservert etter all validering**, aldri før. Et avvist forsøk skal ikke brenne nøkkelen:
køen som retter seg og prøver igjen ville ellers fått «allerede levert» på noe som aldri
kom fram. `forkast()` frigir den når statusmaskinen avviser overgangen. Egen test som
sender en ulovlig overgang først og krever at den lovlige etterpå går gjennom.

**Synkingen er seriell og stopper på første feil.** To parallelle sendinger kunne landet
«Avreist» før «Fremme», og `Statusmelding` er et spor av hva som faktisk skjedde. En 4xx
som ikke er `duplikat` stryker raden og melder fra — serveren vil avvise den igjen, og å
beholde den ville låst køen for alt bak.

**Klienttiden fryses ved trykket**, ikke ved sendingen. Uten det ville statistikken vist
når dekningen kom tilbake i stedet for når mannskapet meldte. `forsinket`-flagget fra
§5.1 gjør at tallet kan leses for det det er.

**Skjermen viser hva som ligger usendt** — §6: en knapp som ser ut til å ha virket, men
ikke har det, er verre enn en som feiler synlig. Eget banner, roligere tone enn
feilbanneret: dette er en ventetilstand, ikke en feil.

### Kjeden måtte til klienten, og det er verdt å si hvorfor

Skjermen kjente ikke statuskjeden — serveren sendte `neste_overgang` per rad. Det holder
online, men ikke i en bil uten dekning: første trykk ville drept knappen, og køen vært
halvveis. Kjeden følger nå med siden som data, og brukes **kun** til å regne ut hva neste
knapp skal hete mens noe ligger usendt.

§4.2-invarianten er urørt. Den handler om at *serveren* ikke skal utlede handlingen av
tilstanden — `POST .../status/neste/` ville gitt kappløpet når to trykk kommer tett.
Klienten måtte uansett vite hvilket navngitt endepunkt den poster til. En test låser
kjeden som sendes mot `services.neste_i_kjeden`, så de to ikke kan komme i utakt: sendes
en annen kjede enn serveren håndhever, viser knappen ett steg og endepunktet godtar et
annet. Sentralbordet får den ikke — det har ingen kø.

### To feller i testoppsettet, begge verdt å notere

`build_harness` klipper ut **funksjoner og ingenting annet**, så `const KO_NOKKEL` var
udefinert i node — og `koLes()` sin try/catch svelget `ReferenceError` og meldte «tom kø».
Alle tolv testene bestod i den forstand at de ikke krasjet, men målte ingenting. Nøkkelen
er nå `koNokkel()`, altså en funksjon harnesset kan se, og det står i koden hvorfor.

Og `crypto` er skrivebeskyttet global fra node 19 — stubben kastet. Node har
`randomUUID` innebygd, så den er droppet; testene sammenligner aldri nøkler mot faste
verdier.

Seks av kø-testene er sett røde ved å slå av projeksjonen.

---

## 2026-08-29 — Oppklart: innloggingen feilet i feil miljø

**Ingen kodeendring.** Kontoen `karmøy56` kom ikke inn fordi innloggingsforsøkene gikk mot
**prod**, mens kontoen ligger på **staging**. André fant det selv.

Det forklarer alt som ikke stemte: `last_login_at` sto stille fordi forespørslene aldri
nådde den databasen diagnosen leste, og `sjekk_brukernavn` — som bare finnes i koden på
`rollemodell` — beskrev hele tiden en annen base enn den innloggingen traff.

**De tre foregående oppføringene står, men ikke som løsningen på dette.** Ingen av
funnene var årsaken; alle er ekte feil som lå der uansett, og som ble funnet fordi noen
lette:

| Funn | Står på egne bein fordi |
|---|---|
| Hullet i kontolåsen | `login_view` slo opp kontoen eksakt mens `authenticate` var tolerant. Passordgjetting kunne kjøres i det uendelige ved å variere store bokstaver. Reell sårbarhet, uavhengig av denne saken |
| Unicode-normalisering | `å` limt inn i NFD-form fant ingen konto. `Ø` mot `ø` bommet på SQLite, altså i offline-modus |
| Forvekslingstegn i midlertidig passord | `0`/`O` og `1`/`l`/`I` i et passord som leses av en skjerm og tastes på en telefon |

**Lærdommen er operativ, ikke teknisk.** To miljøer som ser helt like ut i nettleseren, og
ingenting på siden sier hvilket man står i. Det kostet en arbeidsøkt her, og vil koste mer
under en vakt — der forskjellen er om en pasient registreres i ekte journal eller i en
testbase. Ført opp i TODO.

---

## 2026-08-29 — En vei inn når passordet ikke lar seg gjette

**1249 tester grønne** (12 nye). Ingen migrasjon.

Kontoen kom fortsatt ikke inn med det midlertidige passordet. Diagnosen sto klar:
brukernavnet lagret rent, ingenting i kontotilstanden blokkerte, ingen lås — og
**`last_login_at` sto stille på 07:07**. Siden feltet settes ved *hver* vellykket
innlogging, betyr det at forsøkene ikke lyktes. Passordet traff ikke hashen.

**En sannsynlig grunn lå i genereringen.** Det midlertidige passordet ble trukket fra
`string.ascii_letters + string.digits` — tolv tegn som kan inneholde `0` mot `O`, og `1`
mot `l` mot `I`. Det leses av en skjerm og tastes inn et annet sted, ofte på en telefon.
Feiltastingen er umulig å skille fra «feil passord», og etter fem forsøk låses kontoen
mens brukeren tror hen skriver riktig.

Alfabetet utelater nå `0 O 1 l I`. Kostnaden er 69,7 bit i stedet for 71,4 over tolv tegn
— uvesentlig for et passord som uansett skal byttes. Genereringen lå duplisert to steder,
ved opprettelse og ved «tilbakestill passord»; den er nå én funksjon i `accounts/passord.py`.

**Og en vei inn:** `python manage.py sett_passord <navn>`. Den slår opp brukernavnet med
samme tolerante regel som innlogging, godtar `\uXXXX`-rømming for kanaler uten norske
tegn, validerer det nye passordet mot de samme reglene som skjemaet, nullstiller
kontolåsen, og **fjerner kravet om passordbytte som standard** — det er som regel hele
poenget med å kjøre den. Uten `--passord` genereres ett og skrives ut én gang.

At låsen nullstilles er ikke en detalj: har noen prøvd seg fram på den gamle verdien,
skal ikke den nye møte en sperre satt av de forsøkene. Egen test.

### En blindvei, notert fordi den kostet tid

Første reproduksjon viste `GET /accounts/change-password/` med **400**, og det så ut som
selve forklaringen. Det var **testoppsettet mitt**: backup-planleggeren kjørte mot en
in-memory SQLite og feilet med «database table is locked». Med planleggeren av svarer
siden 200. Feilen lå aldri i appen, og påstanden ble trukket tilbake med en gang den lot
seg etterprøve.

---

## 2026-08-29 — Kontolåsen hadde et hull, funnet mens vi lette etter noe annet

**1237 tester grønne** (5 nye). Ingen migrasjon.

Utskriften fra `sjekk_brukernavn` mot prod viste `karmøy56` med **`feilede forsøk: 0`** og
**`sist innlogget: 07:07 i dag`**. Kontoen hadde altså logget inn, og telleren sto på null.
Det siste tallet viste seg å ikke bety noe.

**`login_view` slo opp kontoen med nøyaktig treff:**

```python
user_obj = CustomUser.objects.get(username=username)
```

mens `authenticate()` bruker det tolerante oppslaget. To ulike svar på «hvilken konto er
dette», og konsekvensen er en **hullete kontolås**: skriver man `Karmøy56` med stor K, blir
`user_obj` `None`, `_registrer_mislykket_forsok` hoppes over, telleren står stille — og
kontoen låses aldri. Riktig passord slipper fortsatt gjennom, siden `authenticate` finner
kontoen. Gjettingen kan altså kjøres i det uendelige ved å variere store bokstaver.

Ironien er at kommentaren fem linjer over forklarer hvorfor *rate-limit-nøkkelen* er
normalisert, med nøyaktig samme argument. Oppslaget under fikk ikke samme behandling.

Oppslaget er nå løftet ut som `backends.finn_kandidater` / `finn_konto`, og både viewet og
`authenticate` kaller den. Én regel for «hvilken konto er dette». Tre av de fem nye testene
er sett røde mot det gamle oppslaget.

**Rate-limit-taket sto uansett** (10 forsøk / 5 min per brukernavn, 50 per IP, begge på
normalisert nøkkel), så hullet var i den per-konto låsen, ikke i bremsen foran den.

**Et første testforsøk målte feil ting.** Det krevde `failed_login_attempts == 5` etter fem
forsøk og feilet med `0 != 5`. Koden hadde rett: `_registrer_mislykket_forsok` nullstiller
telleren når den setter `locked_until`. `is_locked()` er invarianten, ikke tallet — det står
nå i testen.

**For kontoen som utløste dette:** ingenting i tilstanden blokkerer innlogging, men
`må bytte passord: True` står fortsatt etter innloggingen 07:07. `MustChangePasswordMiddleware`
sender da hver forespørsel til `/accounts/change-password/` i stedet for til portalen — og
utenfra ser det ut som at man «ikke kommer inn». Verktøyet sier nå fra om nettopp den
kombinasjonen, med tidspunktet for siste innlogging som bevis på at byttet ikke ble fullført.

---

## 2026-08-29 — `ø` var ikke feilen, og verktøyet sier nå hva som er det

**1232 tester grønne** (6 nye). Ingen migrasjon.

Kontoen som ikke kom inn heter `karmøy56`. Utskriften fra `sjekk_brukernavn` viste den
lagret **helt rent** — `karm[ø U+00F8]y56`, riktig prekomponert, ingen lookalike, ingen
NFD, ingen mellomrom. **Brukernavnet var altså ikke feilen**, og hypotesen forrige
oppføring bygget på traff ikke dette tilfellet.

Da sto man uten neste steg, og det var mangelen: verktøyet svarte på ett spørsmål og
stoppet der. Det viser nå kontoens tilstand når navnet stemmer, og navngir det som
faktisk blokkerer:

| Tilstand | Hvorfor den stopper innlogging |
|---|---|
| `is_active=False` | Kontoen er deaktivert |
| Ingen brukbar passord-hash | Opprettet med invitasjon, lenken aldri brukt. **Ingen** passord virker |
| `locked_until` i framtiden | Fem feilede forsøk låser i 15 min |
| `mfa_required` uten bekreftet TOTP-enhet | Innlogging går til MFA-oppsett, ikke til portalen |

Den midterste er den lumske: feilmeldingen ved innlogging er identisk med «feil passord»,
med vilje, så utenfra er de to umulige å skille. En utløpt `locked_until` regnes ikke som
blokkering — det er en gammel hendelse, ikke en sperre. Egen test.

**Verdt å kjenne for enhetskontoer:** invitasjonsflyten krever `not er_delt_konto` *og* en
e-postadresse. En bilkonto er en delt konto uten e-post, så den får alltid et **generert
12-tegns midlertidig passord** og `must_change_password=True` — ikke et passord man velger
selv ved opprettelsen. Skriver man inn passordet man *trodde* man satte, feiler det, og
brukernavnet med `ø` i er en nærliggende, men uskyldig, mistenkt.

**Et funn til, som ikke forklarer dette tilfellet men er ekte:** `set_password` kaller
`make_password` rett på råstrengen — **Django normaliserer ikke passord**. Et passord med
`å` satt i én Unicode-normalform og skrevet i en annen gir ulik hash, uten at noe kan ses.
`æ` og `ø` dekomponerer ikke og rammes ikke, så det forklarer ikke `karmøy56`. Verktøyet
sier fra om det når ingenting annet blokkerer. **Ikke rettet** — en fallback som også
prøver den normaliserte formen ville utvidet hva som godtas som passord, og det er en
avgjørelse som fortjener å tas bevisst, ikke i forbifarten.

---

## 2026-08-29 — Innlogging med æøå, og en grønn prikk for ledig

**1220 tester grønne** (7 nye). Ingen migrasjon.

### Brukernavn med norske tegn

Meldt fra prod: en konto med `ø` i navnet kom ikke inn, selv med brukernavn og passord
limt inn. **Det tilfellet lot seg ikke reprodusere** — `bjørn.rød` logger inn på første
forsøk her. Men to ekte feil i samme mekanikk ble funnet på veien, og begge er rettet.

**1. Unicode-normalform.** `å` finnes som ett tegn (U+00E5, NFC) og som `a` pluss
kombinerende ring (U+0061 U+030A, NFD). macOS produserer NFD i flere sammenhenger, så
«kopier brukernavnet og lim det inn» er nok til å bomme — de to strengene er pikselidentiske
på skjermen og forskjellige for databasen. Verken oppretting eller innlogging normaliserte.

Målt underveis, og verdt å vite: **`æ` og `ø` dekomponerer ikke.** De er egne bokstaver,
ikke bokstav pluss aksent. `å` og `Å` gjør. Feilen rammer altså navn med `å` — noe som
svekker normalisering som forklaring på nettopp `ø`-tilfellet, og det står i koden.

**2. `iexact` case-folder ikke unicode på SQLite.** `Ø` mot lagret `ø` gir null treff.
På PostgreSQL virker det, fordi `UPPER()` der håndterer unicode. **Offline-modus kjører
SQLite**, så det er ikke en teoretisk forskjell — det er feltbruk uten nett.

Oppslaget går nå i tre stadig bredere steg, billigst først: `iexact` som før, deretter
nøyaktig treff på en NFKC-normalisert og casefoldet nøkkel, og først om begge bommer en
Python-side sammenligning som tåler at *lagret* verdi selv er unormalisert. Det siste
steget kjører kun på et forsøk som ellers ville feilet, og har et tak på 500 kontoer med
logglinje om det passeres — det skal ikke stille bli dyrt om tallet vokser.
`clean_username` normaliserer også ved oppretting, så nye kontoer har én form.

**Tvetydighet slår fortsatt aldri ut i feil konto:** matcher flere kontoer, kreves
nøyaktig treff. De fire nye testene er sett røde mot den gamle backenden.

**For `ø`-tilfellet i prod finnes nå et verktøy:** `python manage.py sjekk_brukernavn
[navn]`. Les-only. Den skriver hvert brukernavn tegn for tegn med kodepunkt og
Unicode-navn, flagger unormaliserte og kontoer med mellomrom i enden, og sier om et gitt
oppslag ville truffet. Den finnes fordi «brukernavnet ser riktig ut» ikke lar seg
feilsøke ved å se på det — en kyrillisk `е` ser ut som en latinsk `e`, og den fella traff
dette prosjektet i et dokument tidligere samme dag.

**Og kanalen selv var en felle.** Railways `ssh` bærer ikke `ø` inn på kommandolinja, så
verktøyet var i praksis ubrukelig for nettopp det tegnet det skulle undersøke. To ting
retter det: **uten argument lister kommandoen alle kontoer** — man trenger ikke skrive
navnet i det hele tatt — og argumentet godtar `\uXXXX`-rømming, mens utskriften viser
hvert navn i samme form. Første forsøk skrev ascii-formen med Pythons egen
`backslashreplace`, som gir `\xf8` for tegn under U+0100; den formen tolkes ikke tilbake,
så rundturen var brutt og utskriften ubrukelig i den kanalen den var laget for. Nå skrives
alltid `\uXXXX`, og en test limer hver form tilbake og krever samme streng.

### Grønn prikk for ledig enhet

`.status-ledig` var grå, som `.status-venter`. Grått leste som «av», og 113 skal se hvem
som kan sendes uten å lese teksten først. Nå grønn (`#22c55e`). `Venter` beholder grått —
det er nettopp forskjellen mellom «tildelt, men ikke rykket ut» og «klar» som skal være
synlig. Fargen bærer fortsatt ikke informasjonen alene; statusteksten står ved siden av
(WCAG 1.4.1).

---

## 2026-08-29 — Fase 4b: 113 kan rette et tidspunkt, uten å viske ut det som ble meldt

**1213 tester grønne** (18 nye). Ingen migrasjon.

Maskineriet kom i fase 1 og var ubrukt: `services.korriger_tidspunkt` og
`Statusmelding.objects.gjeldende()` har ligget der siden 28. aug. Det som manglet var
endepunktet, reglene og en vei inn fra grensesnittet.

**Rettingen er en ny rad som peker på den gamle.** Originalen røres ikke, og begge står i
tidslinjen — den erstattede gjennomstreket, rettingen merket «rettet av sentralen».
`Statusmelding` er et spor av hva som *ble meldt*; redigerte man raden, kunne «hva sa
bilen egentlig?» bare besvares fra `AuditLog`, en admin-flate som ikke er der oppdraget
vises. Testen som holder det ærlig setter `melding.tidspunkt` direkte i tillegg til å
skrive den nye raden — og blir rød.

**Fire regler, alle fail-closed:**

1. **Raden må være gjeldende.** Retter man en allerede overstyrt rad, finnes to
   korreksjoner av samme original og «hvilken gjelder» har ikke lenger noe entydig svar.
   Korreksjoner *kan* kjedes — man retter den nyeste.
2. **Ikke i framtiden.** Et tidspunkt som ikke har inntruffet er ikke en observasjon.
3. **Ikke før oppdraget ble opprettet.**
4. **Rekkefølgen må holde.** Dette er den som betyr noe. Settes `Fremme` før
   `Rykker ut`, blir responstiden negativ — og fase 6 ville regnet på den uten å vite at
   tallet er umulig. Sjekken måler mot de *gjeldende* naboene, ikke mot alle rader: en
   overstyrt rad beskriver ikke lenger noe som gjelder, og å måle mot den ville låst
   rettingen til verdien man retter bort. Feilmeldingen navngir naboen som er i veien
   («`Fremme` kan ikke være før `Rykker ut` (14:36)»), så operatøren vet om hun må rette
   en annen rad først.

**Endepunktet er bevisst ikke et handling-endepunkt.** Det tar et tidspunkt, altså en
feltverdi, og ligger derfor på `skriv_full` med vanlig kroppsvalidering. Å presse det inn
under `skriv_handling` ville uthult det lukkede skjemaet i §5.1 med én gang — da hadde
stemplingskroppen fått et domenefelt. Enhetskontoer får 403 uansett nivå: en bil som kunne
rette sine egne tidspunkt ville gjort stemplingen til en påstand i stedet for en måling.
Bilen *ser* rettingen (§4.5), den gjør den ikke.

**To fikstur som målte feil regel.** Begge ble funnet ved at testene feilet, ikke ved
gjennomlesing. Det første stemplet oppdraget i samme millisekund som det ble opprettet, så
enhver retting bakover traff «før oppdraget ble opprettet» — fiksturet har nå realistisk
tidsspenn. Det andre stemplet `Avreist` med servertid og rettet `Fremme` til fem minutter
etter; det havnet i framtiden, så framtidsregelen svarte først og testen ville bestått også
uten rekkefølgesjekken. Begge er notert i koden, siden mønsteret kommer tilbake.

**Én feil verdt å notere:** `@transaction.atomic` sto over `korriger_tidspunkt`, og den nye
`KorreksjonUgyldig`-klassen ble satt inn *under* dekoratoren. Da var ikke unntaket lenger
en klasse, og `except` kastet `TypeError: catching classes that do not inherit from
BaseException`. Fanget av testene med en gang. Verdt å huske når noe settes inn rett foran
en dekorert funksjon.

---

## 2026-08-29 — «Arkiv» heter Historikk i oppdragsmodulen

**1195 tester grønne** (ingen nye). Migrasjon `oppdrag.0004_historikk_ikke_arkiv` —
ren `RenameField`, ingen data endres.

Knappen het «Ferdigstilte» og handlingen «Arkiver». Begge er borte: flaten heter
**Historikk**.

**Grunnen er en navnekollisjon som ville blitt verre, ikke bedre.** `core.arkiv` fryser,
signerer og kollapser hele vakter, og oppdragsmodulen får sin *egen* `BaseArkivHandler` i
fase 7. Hadde begge hett «arkiv», ville `arkiver_view` og `ArkivHandler` stått i samme app
og betydd hver sin ting — den ene rydder en liste, den andre skriver en SHA-256-signatur
som ikke kan angres. Den som leste feil av de to ville trodd raden var fryst.

Derfor er omdøpingen ført hele veien inn, ikke bare på knappen:

| Før | Nå |
|---|---|
| `arkivert_at` / `arkivert_av` | `historikk_fra` / `historikk_av` |
| `bruker.arkiverte_oppdrag` | `bruker.oppdrag_lagt_i_historikk` |
| `arkiver_oppdrag()` | `flytt_til_historikk()` |
| `KanIkkeArkiveres` | `KanIkkeFlyttes` |
| `POST /api/oppdrag/<pk>/arkiver/` | `POST /api/oppdrag/<pk>/historikk/` |
| `GET /api/arkiv/` | `GET /api/historikk/` |
| `arkivert` i JSON-svaret | `historikk_fra` |

`related_name` er den som betyr mest i kode: `bruker.arkiverte_oppdrag` ville fortsatt
lovet arkivering fra et helt annet sted i kodebasen. Testklassene og testnavnene er også
byttet — det er der neste utvikler leter etter hva ordene betyr.

De to gjenværende treffene på «arkiv» i modulens tester er selve forklaringen på hvorfor
navnet ble byttet, og skal stå.

---

## 2026-08-29 — Ferdigstilte oppdrag rydder seg selv bort

**1195 tester grønne** (7 nye). Ingen migrasjon. Oppfølging samme dag: den manuelle
arkivknappen løste ikke problemet den var laget for.

**Innvendingen var god.** Krever ryddingen et trykk per oppdrag under en travel vakt, blir
den ikke gjort — og da fylles tavla opp likevel, med en knapp ingen rakk å bruke. Et
oppdrag arkiveres nå i det øyeblikket det blir `Ledig`.

**Regelen ligger i `sett_status`, ikke i stemplingsviewet**, og det er ikke en
smaksdetalj: ikke alle `Ledig`-overganger kommer fra et knappetrykk. Starter en enhet
neste oppdrag, lukkes det pågående automatisk (§4.3) gjennom samme funksjon. Lå regelen i
viewet, ville tavla beholdt nettopp de oppdragene ingen trykket på — de som ble lukket av
seg selv. Testen som dekker det er sett rød ved å unnta `automatisk=True` fra regelen.

**`arkivert_av` står som NULL ved automatisk arkivering, og det er informasjon.** NULL
betyr «ryddet bort av seg selv», satt betyr «noen trykket». Samme skille som
`Statusmelding.automatisk`. Å føre opp bilens konto der ville dessuten motsagt regelen om
at enheter ikke arkiverer — den stempler, systemet rydder.

**Arkiveringen henger på overgangen, ikke på statusen.** Forskjellen merkes i «Hent
tilbake»: et oppdrag hentet fram igjen blir *stående* på tavla, fordi det ikke finnes noen
ny overgang til `Ledig` som kunne fjernet det. Var arkiveringen i stedet et statusfilter,
ville raden forsvunnet igjen ved neste poll, og knappen vært uten virkning. Egen test.

**Bilens 30-minuttersvindu er urørt**, og det er verdt å gjenta fordi de to nå ser enda
likere ut. Mannskapet ser fortsatt oppdraget sitt i en halvtime etter at de meldte seg
ledige; det er sentralbordets tavle som ryddes. Koblet dem, ville oppdraget forsvunnet fra
skjermen i bilen i samme øyeblikk knappen ble trykket — mens de fortsatt sto og så på det.
Egen test som krever begge deler samtidig.

Den manuelle knappen står igjen for hånd-tilfellene: hent tilbake til tavla, og rydd bort
igjen etterpå. Hjelpeteksten i «Ferdigstilte» sier nå at oppdrag havner der av seg selv —
den beskrev en knapp som i praksis ikke lenger er hovedveien inn.

---

## 2026-08-29 — Oppdragsnummer, og en arkivknapp som rydder tavla

**1188 tester grønne** (22 nye). Migrasjon `oppdrag.0003_oppdragsnummer_og_arkivering`.
Bestilt under uttesting av fase 4, utenom faseplanen.

**Nummeret er per år, ikke globalt.** `pasientnummer` er globalt unikt fordi
nullstillingen der sletter radene; oppdrag har ingen slik nullstilling, så uniktheten
bæres av `(year, oppdragsnummer)` med en databasesperre. Nummeret restarter på 1 hver
sesong — «oppdrag 14» skal være kort nok til å leses opp på samband, og i år tre ville en
global teller gitt tresifrede numre uten grunn. Telleren står i `AppSetting` per år og
låses med `select_for_update`, som `next_patient_nr`, og gjenskapes fra dataene hvis raden
mangler, slik at en slettet innstilling ikke gir kollisjon.

**Migrasjonen backfiller før den strammer inn.** Tre steg i rekkefølge: nullbar kolonne,
backfill per år i `created_at`-rekkefølge, deretter `NOT NULL` og unikhetskravet. Legges
kolonnen til med en default i ett steg, får alle eksisterende rader samme nummer og
sperren feiler. Backfillen setter også `AppSetting`-telleren for hvert år den fant — uten
det ville neste opprettelse startet på 1 og kollidert med rad nummer 1. Kjørt mot en
testbase med rader i to år og blandet innsettingsrekkefølge: nummereringen følger
`created_at`, ikke innsettingen.

**«Arkiver» rydder tavla. Den fryser ingenting.** Dette er *ikke* vaktarkivet i
`core.arkiv`-forstand — ingen SHA-signatur, ingen kollaps, ingen backup-sperre. Et
ferdigstilt oppdrag flyttes ut av den aktive lista og inn i en «Ferdigstilte»-visning som
kan søkes på nummer, problemstilling, lokasjon eller enhet. Raden er urørt og kan hentes
tilbake. Fase 7 bygger fortsatt det ekte vaktarkivet; de to er ikke i veien for hverandre
— den ene er drift under vakt, den andre dokumentasjon etter vakt.

Fordi handlingen er reversibel ligger den på `skriv_full`, ikke på global admin: §3.3
reserverer admin for det irreversible, og en knapp som bare rydder en liste hører til
drift. Enhetskontoer stenges ute selv med `skriv_full` — rydding er sentralbordets jobb.

**Kun ferdigstilte kan arkiveres.** Å rydde bort et pågående oppdrag ville skjult noe som
fortsatt skjer, og det er samme feilklasse som å ta en enhet av vakt midt i et oppdrag —
allerede stengt i `enhet_vakt_view`. Knappen vises bare når den kan brukes.

**Arkivering rører ikke enhetens 30-minuttersvindu**, og det er verdt å si eksplisitt
fordi de to reglene ser like ut. Vinduet er personvern — en bil kan bli stående ulåst.
Arkiveringen er sentralbordets rydding av sin egen tavle. Koblet dem, kunne sentralbordet
fjernet et oppdrag fra skjermen til et mannskap som fortsatt sto og så på det.

**Et fikstur som påsto mer enn det viste.** Søket på nummer treffer eksakt, ikke som
delstreng — søker man «1» skal man ikke få 1, 10 og 11. Testen sa nettopp det, men
fiksturet hadde bare numrene 1, 2 og 3, så den bestod også da søket ble byttet til
`__icontains`. Numrene er nå 1, 10 og 11, og mutasjonen gjør testen rød. De øvrige nye
vernene er også sett røde: sperra mot å arkivere pågående (5 feil) og ekskluderingen fra
den aktive lista (1 feil).

Personvernprotokollen er ført til v1.8: begge feltene inn i A.6-tabellen, med presisering
av at `oppdragsnummer` identifiserer *oppdraget* og ikke personen, og en merknad i A.9 om
at arkivflagget ikke påvirker noen lagringstid.

---

## 2026-08-29 — Fase 4: enhetsskjermen, og første faktiske bruk av `skriv_handling`

**1166 tester grønne** (29 nye). Ingen migrasjon. Mellomtilstanden fra fase 3
(`enhet_kommer.html`) er slettet — enhetskontoer får nå en ekte skjerm.

**Stemplingsendepunktene: fem, ikke seks.** Planen sa «seks navngitte endepunkter», men
talte statusene: `venter` settes ved oppretting og stemples aldri. Settet skrives ikke ned
noe sted — `services.STEMPLBARE` utledes av overgangstabellen (`frozenset().union(*OVERGANGER.values())`),
så et endepunkt finnes hvis og bare hvis en rad peker på det. URL-en er
`POST /oppdrag/api/oppdrag/<pk>/status/<overgang>/` med statusverdien som navn; ukjent navn
gir 404, ulovlig overgang 409.

**Det lukkede kroppsskjemaet fra §5.1 er testbart ved uttømming, og testes slik.** To
nøkler — `klienttid` og `idempotency_key` — og alt annet gir 400 uten sideeffekt; testen
sender domenefelt og krever at ingenting endret seg. `klienttid` valideres etter §5.1:
framtid, før oppdragets opprettelse eller eldre enn et døgn gir servertid, og avvik over to
minutter fra ankomsttid setter `forsinket=True` uansett hvilket stempel som vant — avviket
er informasjonen. Uleselig klienttid gir 400, ikke stille servertid: det er en klientfeil,
ikke et gammelt stempel.

**`idempotency_key` godtas, men kobles først i fase 5.** Statusmaskinen gjør en ren
avspilling ufarlig allerede: samme overgang to ganger er ulovlig andre gang og gir 409 uten
ny rad. Verdien av `core.idempotency` her er å svare «ok» på en replay i stedet for 409, og
det svaret hører til offline-køen som skal tolke det.

**To porter, og nivå er ikke nok.** `skriv_handling` i dekoratøren, eierskap i viewet — og
`skriv_full` *uten* enhetskobling får 403. Sentralbordet stempler ikke; det korrigerer
(fase 4b). Stemplingen er en måling fra bilen, og en operatør som stempler «for» en enhet
ville forfalsket den. Testene dekker også kombinasjonen enhetskobling uten
`ModulTilgang`-rad: koblingen gir ingen tilgang, samme regel som `Forstehjelper.user`.

**Skjermen kjenner ikke statuskjeden.** Serveren sender `neste_overgang` og `neste_navn`
på hver rad (kun i enhetens payload), og «neste»-knappen poster dit den blir fortalt. En
kopi av kjeden i JS ville vært enda et sted å komme i utakt — §2.6 i rollemodellnotatet i
miniatyr. Dobbelttrykk møter 409 og besvares med å hente ferskt, uten feilbanner.

Resten av skjermen: to knapper med 64px trykkflater (en tommel i en bil i bevegelse, ikke
en musepeker), ventende sortert på hastegrad men valgt av mannskapet, tidslinje på det
aktive kortet, `automatisk`-markøren i gråtoner på klokkeslettet (§4.5), og et feilbanner
som blir stående til noe lykkes — med beskjed om å melde over nødnett, som er det ærlige
svaret til offline-køen finnes (fase 5). Polling hvert 15. sekund med ETag; enhetens ETag
inkluderer meldings-ID-ene, slik at en korreksjon (fase 4b) ikke drukner i en 304.

**`klokke()` flyttet til `portal-utils.js`** — begge oppdragssidene bruker den, og helpere
flyttes, de kopieres ikke. `hastegradKlasse()` er duplisert med vilje: den er domene, ikke
primitiv, og de to filene lastes aldri sammen. XSS-vernet i `tests_xss.py` skanner nå
byggerne i begge filene, og kjører enhetsskjermens byggere i node med markup i fritekst,
knappenavn og statusnavn.

---

## 2026-08-29 — Fase 2 lukket: protokollen dekker oppdragsmodulen

Kun dokumentasjon — `PERSONVERN_DOKUMENTASJON.md` går fra v1.6 til v1.7. Ingen kodeendring,
ingen migrasjon. **1137 tester grønne.**

Dette var resten av fase 2 i `docs/BESLUTNING_OPPDRAGSMODULEN.md`. Kodedelen — at fritekst
logges som *endret* i audit, men aldri med verdier — har vært på plass fra feltets første
lagring (28. aug.); det som sto igjen var at behandlingsprotokollen faktisk beskriver
behandlingen. Rekkefølgekravet var «før feltet er i prod med logging på», og det holdt:
modulen finnes kun på staging, så verdilogging av fritekst har aldri vært aktiv noe sted.

Hva som kom inn, og hvorfor det ligger der det ligger:

- **A.6, ny seksjon «Oppdragsdata».** Feltene med kategori og hjemmel, etter samme lest som
  pasienttabellen. Det bærende poenget står først: personen oppdraget gjelder registreres
  **uten noen identifikator** — ikke pasientnummer, ikke navn, ingen kobling til
  pasientmodulen. Fritekst-tiltakene er samlet her som nummerert liste: audit-unntaket,
  de to server-side skjulereglene mot enhetskontoer, hjelpeteksten i skjemaet, og at
  oppdragsdata ikke caches. `Leverer`-uten-leveringssted er ført som det bevisste valget
  det er.
- **A.6, audit-tabellen.** Raden som lover «gammel verdi, ny verdi» på feltnivå har fått
  unntaket ført inn. Uten den linja motsier protokollen seg selv fra to seksjoner.
- **A.9, rad + merknad.** Ærlig svar på lagringstid: **ingen automatisk sletting ennå.**
  Radene er årsscopet som pasientdata, men blir stående til fase 7 leverer arkivering med
  24-måneders kollaps. Merknaden sier eksplisitt at raden skal revideres da — samme grep
  som kollaps-verifiseringsmerknaden fra v1.6: dokumentet skal si hva som er bevist, ikke
  hva som er planlagt.
- **A.12, ny sårbarhet.** Fritekst er portalens første frie tekstfelt, og en operatør *kan*
  skrive identifikatorer der. Tiltakene henvises, og restrisikoen står: selve feltverdien
  ligger i oppdragstabellen til oppdraget slettes eller arkiveres.
- **B.2, merknad.** Personvernerklæringen henvender seg til pasienten, og en utrykning
  gjelder samme person — da skal erklæringen også dekke den. Kort avsnitt: oppdraget
  registreres uten identifikator, og fritekst skjules for enheten ved avslutning.

**Funn underveis, ført inn i A.9 og TODO:** oppdragsdata står utenfor applikasjonens
modulbackup. Ingen handler er registrert i `core.backup`-registryet, så fram til fase 7 er
Railways databasebackup — aktiv omtrent én måned i året — eneste dekning. Ikke akutt så
lenge modulen er på staging, men det må få en handler senest sammen med arkiveringen.

Fasetabellen i beslutningsnotatet er samtidig ført ajour: fase 2 og fase 3 står nå som
levert (fase 3 ble levert 29. aug. uten at tabellen ble oppdatert), og §9 har fått en
gjennomført-note etter samme mønster som rollemodellnotatets §7.

---

## 2026-08-29 — «Pensjoner» er borte, og et pensjonert navn er ledig igjen

**1137 tester grønne** (2 nye, 7 fjernet). Ingen migrasjon.

Målt på staging: `Enheter uten konto: 0 av 2`. Dermed hadde Pensjoner-knappen ingen jobb
igjen — alle enheter har en konto, og kontoen er veien inn og ut. Knappen, Gjenopprett,
`_settAktiv`, `PUT /oppdrag/api/enheter/<pk>/`, `GET /oppdrag/api/kontoer/` og
`_enhet_admin_dict` er slettet. Det samme er `OPPDRAG_TILGANG.erAdmin`, som ikke hadde noen
leser igjen.

**Men å fjerne knappen alene ville satt en felle.** Sletter du kontoen til en bil som har
kjørt, pensjoneres enheten i stedet for å slettes — historikken er `PROTECT`. `Enhet.navn`
er `unique`, så «Haugesund 56» ville vært brent for godt: skjemaet ville sagt «finnes
allerede», og uten Pensjoner-knappen fantes ingen vei tilbake utenom `manage.py shell`.

Et pensjonert, ukoblet navn regnes derfor som ledig. Oppretter du kontoen på nytt, tas den
gamle raden i tjeneste igjen i stedet for at det lages en ny — bilen kommer tilbake med
oppdragene sine. En ny rad ville gitt to «Haugesund 56» i statistikken, én med historikk og
én uten. Navn som holdes av en enhet i tjeneste, eller av en med konto, er fortsatt opptatt.

Enhetens livssyklus har dermed én kilde: kontoen. Opprett den, og bilen finnes; slett den,
og bilen forsvinner eller pensjoneres; opprett den igjen, og bilen er tilbake.

**Under arbeidet slettet jeg `enheter_view` ved et uhell** — den lå mellom to funksjoner som
skulle vekk, og utsnittet tok den med. Fanget med en gang fordi skriptet skrev ut hvilke
funksjoner det faktisk fjernet; gjenopprettet fra `git show HEAD`. Verdt å merke seg som
argument for å la slike skript rapportere, ikke bare gjøre.

---

## 2026-08-29 — Enheten følger kontoen, også ut

**1142 tester grønne** (5 nye, 1 fjernet). Ingen migrasjon.

André: «Fjern legg til enhet-knappen i enheter-vinduet. Den skal ikke brukes av noen og er
bare forvirrende. Vi trenger heller ikke pensjoner? Jeg kan jo bare slette brukeren?»

**«Legg til enhet» er borte** — knappen, JS-funksjonen, `POST /oppdrag/api/enheter/ny/` og
URL-en. Enheter fødes med kontoen («Bil eller ambulanse» i kontoskjemaet), og to veier inn
til samme rad er én for mye. Malen sa det selv med «vanligvis trengs ikke denne», som er en
knapp som ber om unnskyldning for å finnes. Testen som krevde at endepunktet fantes er
snudd: nå kreves 404.

**Premisset om sletting stemte ikke — nå gjør det det.** `Enhet.user` er `SET_NULL`, så å
slette bilkontoen etterlot enheten som en rad uten kobling: fortsatt på ressursoversikten,
merket rødt, og hvis den hadde kjørt oppdrag, umulig å bli kvitt — `Oppdrag.enhet` er
`PROTECT`. Sletting av kontoen tar nå enheten med seg, og pensjonerer den i stedet når den
har oppdrag i historikken. Samme skille som ellers i portalen: data uten spor slettes, data
med spor fryses.

**Frysing tar enheten av vakt.** En frosset konto kan ikke logge inn, så bilen kan ikke
melde. Å la den stå som ledig ville sendt 113 etter en bil ingen kan kvittere for. Frysing
er reversibel, så enheten pensjoneres ikke — den settes inn igjen manuelt ved opptining.

**«Pensjoner» blir stående.** Den er nå nødutgangen for enheter uten konto — rader som ble
til før koblingen fantes, eller fra `manage.py shell`. De kan ikke fjernes ved å slette en
konto, for det finnes ingen. Etter denne endringen er det den eneste jobben knappen har.

---

## 2026-08-29 — Lukkekrysset var svart på mørk modal

**1139 tester grønne** (1 ny). Ingen migrasjon.

André meldte at X-en i Nytt oppdrag, Enheter og Lokasjoner er svart og ikke passer vinduet.

`portal.css` hadde **ingen** modalregler. Bootstraps `--bs-modal-bg` arver `--bs-body-bg`,
som `base_portal` setter til sidebakgrunnen — så modalen fikk nøyaktig samme farge som siden
bak seg, og `.btn-close`, som er en svart SVG, forsvant i den. Ingenting feilet; det så bare
ut som en tom flate med et kryss som ikke var der.

Pasientsiden har aldri hatt problemet: den er frittstående, laster `style.css`, og hver
knapp der har `btn-close-white`. Feilen bodde kun i portalgrenen, og derfor hører fiksen
hjemme i `portal.css` — ikke i `oppdrag.css`. Alle modulsider som kommer etter, arver den.

Modalen får nå `--portal-surface` og en kant, så den løfter seg fra siden bak, og krysset
inverteres.

Testen fant et sted til jeg ikke hadde sett etter: **`base_portal.html` har selv en
`.btn-close`** — lukkeknappen på Django-meldingene. Den sto svart på `.alert-danger`s
mørkerøde bakgrunn på hver eneste portalside. Samme linje løser begge.

Guarden ligger i `MorkTekstPaaMorkBakgrunnTests`, som allerede løser `{% extends %}` og
`{% static %}`: en mal med `.btn-close` må ha overstyringen i et stilark den faktisk laster.
Samme feilklasse som dempet tekst — en Bootstrap-standard laget for lys bakgrunn, som er
usynlig i stedet for å feile.

---

## 2026-08-29 — Sperra på Pensjoner er testet, ikke bare tegnet

**1138 tester grønne** (2 nye). Ingen migrasjon.

André spurte hvem som når Pensjoner-knappen. Svaret var riktig — global admin, både i
tegningen og på serveren — men bare halvparten av det var testet.

Da Enheter-panelet ble åpnet for `skriv_full` i forrige økt, fikk den gruppa et panel som
også nevner `PUT /oppdrag/api/enheter/<pk>/`. Endepunktet krevde global admin hele veien;
testene dekket bare `enheter/ny/`. En knapp som ikke tegnes er ingen sperre — sperra er
serveren, og den skal ha en test som går rød når noen fjerner den.

To tester lagt til: `skriv_full` uten admin får 403 på både lesing og pensjonering av en
enhet, og enheten er fortsatt aktiv etterpå.

---

## 2026-08-29 — Tavla viser ressurser og oppdrag, resten ligger bak knappen

**1136 tester grønne** (2 nye). Ingen migrasjon.

André: «for nå så er det dårlig UI med på vakt, av vakt og oppdragslisten nederst. De to
viktigste er, hvilke ressurser er tilgjengelige og oppdrag.»

Tavla har derfor to ting: **Ressurser** — enhetene som er på vakt, med status — og
**Oppdrag**. Enheter av vakt vises ikke der lenger; tavla svarer på ett spørsmål, og det er
«hvem kan sendes nå».

Antallet av vakt står på Enheter-knappen («Enheter (1 av vakt)»), der hele lista ligger.

Første utgave hadde *to* signaler om det samme — også en linje under ressurslista. André tok
det bort: «jeg gir jo folk opplæring, de som skal bruke det er godt informerte. Nå dummer vi
det veldig ned.» Han har rett. Vernet mot at en bil forsvinner ubemerket er ett tall, ikke
to plasseringer av det, og et grensesnitt som gjentar seg for brukere som er lært opp er
støy — ikke omtanke.

**Enheter-knappen er ikke lenger et koblingspanel.** Den viser hele lista: på vakt, av vakt
og pensjonerte, med vaktbryteren der. Kontokoblingen vises som tekst, men redigeres ikke —
nye biler får den ved oppretting av kontoen, så nedtrekket var en tredje vei til noe som
allerede var gjort. Verre: det inviterte til å tro at koblingen *er* tilgangen. Mangler
koblingen, står det med rød tekst; det er en ekte feiltilstand og verdt å se.

`?alle=1` på enhetsendepunktet tar med pensjonerte. Ressursoversikten skal ikke se dem —
de er borte for godt — men panelet er stedet man gjenoppretter dem fra, og da må de være
synlige et sted. En probe som droppet filteret gjorde begge testene røde.

Panelet er åpnet for `skriv_full`: å ta biler på og av vakt er drift. Oppretting og
pensjonering står fortsatt på global admin.

Verifisert i nettleser, ikke bare i tester: ressurslista viser én enhet, notisen og
knappetelleren viser den andre, nedtrekket i «Nytt oppdrag» har bare den som er på vakt, og
panelet lister begge med riktig bryter.

---

## 2026-08-29 — Biler tas på og av vakt

**1134 tester grønne** (9 nye). Migrasjon `oppdrag.0002_enhet_pa_vakt`.

André ville at `skriv_full` skal kunne ta biler ut av tilgjengelige enheter — «det er jo en
ressursoversikt».

**Det ble et nytt felt, ikke gjenbruk av `er_aktiv`.** De to svarer på forskjellige
spørsmål, og forskjellen er hvem som endrer dem og hvor ofte. `er_aktiv` er oppsett: admin
pensjonerer en bil, og da skal den bort for godt. `pa_vakt` er drift: 113 tar biler på og av
gjennom vakta. Ett felt for begge ville gjort «pensjonert» og «hjemme i kveld» til samme
tilstand, og den som skulle skru bilen på igjen ville ikke funnet den. Det er den samme
sammenblandingen deploy 1–3 brukte tre runder på å rydde bort.

To regler holder oversikten ærlig, begge testet:

- **En enhet av vakt skjules ikke** — den vises i en egen gruppe på sentralbordet. En bil
  som forsvinner fra tavla er en bil ingen husker å sette inn igjen, og da mangler den neste
  vakt uten at noen vet hvorfor. En probe som filtrerte dem bort i API-et gjorde testen rød.
- **En enhet med påbegynt oppdrag kan ikke tas av vakt.** Den er ute akkurat nå. Et ventende
  oppdrag hindrer derimot ikke — bilen har ikke rykket ut, og motstykket er testet så
  sperren ikke kan bli en som alltid slår til.

Flytting er ingen bakvei: et oppdrag kan ikke flyttes til en enhet som er av vakt.

Endepunktet er skilt fra `enhet_detalj_view`, som er admin-flaten for navn, kobling og
pensjonering. Drift og oppsett har ulike brukere og ulik frekvens, og bør ikke dele dør.

---

## 2026-08-29 — Nivåene tilbys per modul, og bilnivået forhåndsvelges

**1125 tester grønne** (5 nye). Ingen migrasjon.

André: «det står ingenting på oppdrag om skrive:handling. Bare lese eller skrive: full.»

`ModulTilgangForm` hadde én global liste over valgbare nivåer, og `skriv_handling` sto ikke
i den. Begrunnelsen var at ingen modul brukte nivået ennå, og at et nivå som ikke gir noe er
lett å dele ut i god tro. **Den begrunnelsen sluttet å gjelde da oppdragsmodulen ble
skrevet** — nivået var bygget for akkurat den — og ingenting fanget det opp, fordi lista lå
i skjemaet og modulen ikke hadde noe å si om saken.

Samme liste hadde motsatt feil samtidig: den tilbød `skriv_full` på `statistikk`, som ikke
har et eneste skriveendepunkt.

**Hver modul deklarerer nå sine egne nivåer** i `Module.nivaaer`. Patients: `les`,
`skriv_full`. Oppdrag: hele stigen. Statistikk: bare `les`. Et nivå brukeren allerede har
står fortsatt i lista selv om modulen ikke tilbyr det — ellers ville et lagre-trykk stille
fjernet det.

### «Hvorfor settes ikke tilgangen automatisk?»

Fordi en usynlig tilgangsendring er nøyaktig fella §7.3 delte `PasientRolleForm` for å
unngå: der satte én radio både funksjonen i felt og tilgangen, så en domenehandling endret
autorisasjon uten at noen så det.

Men innvendingen har et poeng — en bil uten `skriv_handling` kan ikke gjøre det biler gjør.
Løsningen er **forhåndsvalgt, ikke satt i bakgrunnen**: velger man «Bil eller ambulanse»,
settes Oppdrag-raden i matrisen til «Skrive: handling», med en forklaring ved siden av.
Admin ser verdien i det samme skjemaet hun sender inn, og kan endre den. Valget forblir
hennes, og auditraden viser hva som faktisk ble sendt.

---

## 2026-08-29 — Kontotypen velges, og bilen opprettes i ett steg

**1120 tester grønne** (9 nye). Ingen migrasjon.

André: «jeg er sterkt kritisk til å måtte koble en delt konto. Å koble slikt er tullete.»
Han har rett. Å sette opp én bil krevde tre handlinger — opprett konto, opprett `Enhet`
inne i oppdragsmodulen, koble dem — med to av dem på en helt annen side enn den første, og
ingenting som forklarte hvorfor de hang sammen.

`AdminUserCreateForm` har nå ett valg med tre verdier: **Person**, **Delt konto**, **Bil
eller ambulanse**. Velger man den siste, blir enheten opprettet og knyttet til kontoen i
samme innsending.

**Ett valg, ikke avkrysningsboks pluss navnefelt.** `er_delt_konto` er ikke lenger en boks
på opprettingsskjemaet — den utledes av valget. To kontroller som overlapper er nettopp det
som gjorde `role` til et rot: man kunne krysse av for delt konto og *likevel* skrive et
enhetsnavn, eller la være, og skjemaet måtte gjette hva som var ment. Redigeringsskjemaet
beholder boksen; der endrer man en konto som finnes, og det er noe annet enn å bestemme hva
som skal lages.

**Det som ble slått sammen er to opprettelser — ikke tilgang og domenedata.** §7.3-skillet
står uendret, og en test holder det: en bil opprettet slik får 403 på `/oppdrag/` helt til
noen gir den en `ModulTilgang`-rad. Prøvd motsatt vei også — en probe som lot
enhetsopprettingen dele ut `skriv_handling` gjorde testen rød.

Enhetsnavnet sjekkes som ledig i `clean()`, ikke i viewet. En unik-feil fra databasen ville
kommet etter at kontoen var lagret, og etterlatt en konto uten enhet.

Retningen `accounts` → `oppdrag` er verdt å merke seg. Importen er lokal i funksjonen, som
`core.views` gjør mot `patients.models`. Skal en modul nummer to også kunne opprettes fra
brukerskjemaet, er det der et registry hører hjemme — etter samme idiom som `core.backup`
og `core.arkiv`. Med én modul ville registeret vært mer maskineri enn nytte.

---

## 2026-08-29 — CSRF: hver skriving fra en modulside var brutt

**1111 tester grønne** (8 nye). Ingen migrasjon. `static/js/portal-utils.js` og
`core/tests_csrf_flater.py`.

André meldte at han ikke fikk opprettet et oppdrag som **admin**. Første diagnose var feil —
jeg antok at kontoen manglet `skriv_full`, fordi det forklarte symptomet og passet med
oppsettet han beskrev. Det gjorde det ikke: han var admin hele tiden. Sida ble derfor kjørt
i en ekte nettleser, og da kom svaret på ett forsøk:

```
Forbidden (CSRF token from the 'X-Csrftoken' HTTP header has incorrect length.)
POST /oppdrag/api/oppdrag/ 403
```

**`CSRF_COOKIE_HTTPONLY = True`, så JS kan aldri lese `csrftoken`-cookien.**
`getCsrfToken()` prøvde cookien først og falt tilbake på `#csrf-token-holder` — et element
bare pasientsiden har. Oppdragssiden hadde ingen av delene, så tokenet ble tom streng, hver
POST/PUT/DELETE fikk en HTML-403, og `res.json()` kastet på `<!DOCTYPE` *før*
feilmeldingsboksen ble fylt. Brukeren så at ingenting skjedde.

`base_portal.html` har hatt `<meta name="csrf-token">` på hver eneste side hele tiden — lagt
inn for akkurat dette formålet, og aldri lest. **Fiksen er å lese den**, ikke å legge en
holder i hver mal: da ville neste modul gjort samme feil.

### Hvorfor 37 view-tester ikke så det

`Client()` settes opp med `enforce_csrf_checks=False`. Hele API-et var testet og grønt mens
hver eneste skriving fra nettleseren var brutt. Det er en feilklasse vanlige view-tester er
blinde for, og den må testes eksplisitt.

### Første testforsøk var også grønt på feil grunnlag

Testen jeg skrev lette etter `csrf_token` hvor som helst i malens arvekjede. Den passerte
med feilen intakt, fordi `base_portal.html` har en utloggingsknapp med `{% csrf_token %}`
inne i et skjema: tokenet *var* på sida, bare ikke et sted `getCsrfToken()` så etter. Testen
måler nå kildene hjelperen faktisk leser — meta-taggen eller holderen — og cookien står
uttrykkelig ikke i lista.

Tre vern, alle sett røde: hjelperen kjørt i node mot en stubbet DOM, et strukturelt vern
over alle maler som laster skrivende JS, og et oppførselsvern med `enforce_csrf_checks=True`
som henter tokenet fra meta-taggen slik nettleseren gjør.

---

## 2026-08-29 — Enhetsadmin, og et oppsett som sier fra før det feiler

**1103 tester grønne** (11 nye). Ingen migrasjon.

André prøvde å ta modulen i bruk på staging og meldte at det var «litt knotete». Det var
det, og det var to feil i fase 3 — ikke i oppsettet hans.

**Enheter kunne bare lages fra `manage.py shell`.** Det var ikke en bevisst avgrensning som
`lokasjon`-kommandoen, det var en glipp: sentralbordet fikk lokasjonsadmin, men enheter ble
aldri gitt en flate. En modul som ikke kan tas i bruk uten Railway-konsollen er ikke ferdig.
Enheter opprettes, aktiveres og knyttes til kontoer i et eget admin-panel nå.

Koblingspanelet sier det rett ut, fordi det er stedet feilen ville blitt gjort: **å knytte en
konto til en enhet gir ingen tilgang.** Koblingen avgjør hvilket grensesnitt kontoen får;
hva den har lov til står i modulmatrisen. En test setter en enhet på en konto uten
`ModulTilgang`-rad og krever 403.

At en konto ikke kan være to biler samtidig håndheves nå med en setning admin kan lese.
`OneToOneField` ville avvist det uansett — med en 500.

**Skjemaet lot deg fylle ut alt og feilet ved lagring.** Uten enheter eller lokasjoner ga
«Nytt oppdrag» en «Ukjent eller inaktiv enhet» først etter at du hadde valgt problemstilling,
hastegrad og skrevet fritekst. Det er den verste rekkefølgen: arbeidet gjøres først,
beskjeden kommer etterpå. Siden viser nå hva som mangler, og knappen er avslått til det er
på plass.

### Det som *ikke* var feil

Brukernavn lagres med små bokstaver — `clean_username()` gjør `.strip().lower()`, og
`test_brukernavn_lagres_med_smaa_bokstaver` låser det. `Enhet.navn` er et visningsnavn uten
noen kobling til brukernavnet; «Haugesund 56» og `haugesund56` er to uavhengige strenger.
At de ligner er en felle verdt å kjenne, ikke en sammenheng.

Det som stoppet André var at kontoen hadde **`les`**, og at oppretting krever `skriv_full`.
Siden gjorde akkurat det den skulle — den viste ingen «Nytt oppdrag»-knapp — men den sa ikke
hvorfor. Reprodusert i en diagnose før noe ble endret, så fiksen traff riktig sted.

---

## 2026-08-29 — Oppdragsmodulen fase 3: sentralbordet

**1092 tester grønne** (33 nye). Ingen migrasjon. Modulen er synlig i meny og
dashboard nå som den har en side.

Sentralbordet: enhetsliste med utledet status, oppdragslista for vakta, oppretting,
flytting mellom enheter, tidslinje per oppdrag, og lokasjonsadmin. Polling hvert 30. sekund
med ETag, så et poll uten endring koster en 304 uten kropp.

**To grensesnitt bak én URL.** `/oppdrag/` velger skjerm på om kontoen er knyttet til en
`Enhet` — ikke på nivået. En test setter `skriv_full` på en enhetskonto og krever at den
*fortsatt* får enhetsskjermen: hadde valget stått på «er nivået nøyaktig `skriv_handling`»,
ville den testen vært rød, og feilen §2.3 beskriver ville vært tilbake.

Enhetsskjermen kommer i fase 4. Fram til da får en enhetskonto en mellomtilstand som sier
det rett ut. Alternativet — å sende henne til sentralbordet — ville vist henne alle oppdrag
i vakta, altså nettopp det hun ikke skal se.

**Skjulereglene håndheves i serverens svar.** Testene leser den rå responskroppen, ikke det
serialiserte objektet: `assertNotIn('sensitivt notat', raa)`. Det er den eneste formen som
faktisk beviser at teksten ikke ble sendt. To motstykker holder dem ærlige — fritekst
*vises* mens oppdraget pågår, og sentralbordet beholder den etter `Ledig`.

### To feil testene fant

**`trustedHtml()` ble brukt feil, og hele rendringen var ødelagt.** Funksjonen returnerer en
markør-*objekt* for `cellHtml()`, ikke en streng. `el.innerHTML = trustedHtml(...)` gir
`[object Object]`. Det så riktig ut i koden, og ville vist en tom side i nettleseren. Fanget
av node-testen som kjører byggerne og leser resultatet.

**XSS-gjennomgangen kunne ikke lese sin egen kode.** Regexen som finner `${...}` stopper på
første `}`, så en nøstet mal-streng inne i en interpolasjon ble usynlig — og en uescapet
verdi der ville passert stille. Fragmentene er derfor hoistet ut til variabler over
mal-strengen. Det er bedre kode uansett, men her er det også det som gjør vernet virksomt.

Gjennomgangen leste dessuten sine egne kommentarer: en kommentar som *nevner* `${...}` for å
forklare regelen ble rapportert som et funn. Den stripper `//`-linjer nå, samme grep som
`JsModulLastingTests` gjør for kall.

### Verifisert ved å bryte

Alle vernene er sett røde: radfilteret fjernet (3 feil), fritekstregelen slått av (1),
`@modul_kreves` tatt av flytt-endepunktet (URL-gjennomgangen fanget det og navnga ruta).

Første forsøk på den siste proben **matchet ikke teksten** — `@rate_limit` sto mellom
dekoratørene — så testen «bestod» uten at noe var endret. Verdt å merke seg: en probe som
ikke treffer ser ut som et vern som virker.

Én test til fortjener plassen sin: `test_url_en_svarer` henter modulens URL og krever 200.
Den fanget en 500 som bare oppstår med `ManifestStaticFilesStorage` — altså i prod — fordi
et nytt stilark ikke lå i manifestet.

---

## 2026-08-28 — Oppdragsmodulen fase 1: modeller og regler

**1048 tester grønne** (46 nye). Migrasjon `oppdrag.0001_initial`. Ingen brukervendte
flater — modulen er registrert, men står med `url=None` og begge `show_*`-flagg av.

Fem modeller: `Enhet`, `Lokasjon`, `Oppdrag`, `Statusmelding`, `Enhetsbytte`. Ingen av dem
rører `patients`.

**Fase 2 ble delvis overflødig, og det er en god nyhet.** Planen forutsatte at
audit-logging var noe man måtte melde seg *av*, siden feltlista utledes fra modellen (N2).
Det stemmer per modell: `patients/signals.py` kobler seg på `sender=Patient`, og en ny app
får ingenting automatisk. Audit-signalet for oppdrag er derfor nyskrevet kode, og
skjulingen av `fritekst` er bygget inn fra første lagring i stedet for ettermontert. Det
fjerner vinduet der feltet kunne stått i prod med verdilogging på — og de radene kan ikke
fjernes uten å røre auditsporet.

Skjulingen er en **tredje kategori**, ikke bare et unntak til: `FELT_UTEN_AUDIT` gir ingen
rad i det hele tatt, mens `FELT_UTEN_VERDILOGGING` gir en rad som sier at feltet ble
endret, av hvem og når — men ikke hva som sto der. Sammenligningen gjøres på råverdien;
ellers ville `(skjult) == (skjult)` gjort enhver endring i fritekst usynlig.

Fire invarianter er kodet og testet, alle sett røde først:

- **Statusmaskinen er data**, ikke `if`-er i views. Ukjent status gir `False`, ikke `True` —
  samme regel som ukjent nivånavn i `har_tilgang`.
- **Enhetens status utledes.** Én test krever at `Enhet` *ikke* har en `status`-kolonne, som
  vern mot at noen legger den til «for enkelhets skyld». Et ventende oppdrag gjør ikke
  enheten opptatt: den har ikke rykket ut, og kan fortsatt sendes.
- **Korreksjoner er nye rader** som peker på den gamle, og kan kjedes. Regelen «nyeste
  ikke-korrigerte rad per status vinner» bor i en manager-metode, ikke i en `if` per
  spørring.
- **Fritekst logges uten verdier.** Testen leser den faktiske auditraden og krever at
  teksten ikke er i den.

Å starte et oppdrag mens et annet er i gang lukker det pågående med samme tidsstempel og
`automatisk=True`. En test krever at en manuelt meldt `Ledig` *ikke* får flagget — ellers
ville skillet vært verdiløst.

**Modulen er registrert, men skjult.** En test binder `url`, `show_in_nav` og
`show_in_dashboard` sammen: slås flaggene på uten at URL-en settes, feiler den. Da kan ikke
fase 3 glemme halve jobben.

To tester holder rollemodellen på plass: en konto knyttet til en `Enhet` ser **ikke**
modulen uten en `ModulTilgang`-rad, og en konto med raden ser den. Koblingen er domenedata,
som `Forstehjelper.user` — §7.3 delte `PasientRolleForm` nettopp for å holde kobling og
autorisasjon fra hverandre.

**Lokasjonene vedlikeholdes med `python manage.py lokasjon` inntil fase 3**, ikke med en
admin-side. Planen sa admin-side i fase 1, og den beslutningen ble snudd av en grunn som
først ble tydelig da siden skulle plasseres: modulen har ingen URL ennå, med vilje. En
admin-side uten vei inn er den samme feilen som et modulkort som fører til 404, med et
ekstra steg — og portalen har allerede hatt én slik, oppdaget ved at noen måtte skrive
URL-en for hånd.

Å gi modulen en URL bare for å ha et sted å henge siden ville løst plasseringen ved å
innføre problemet. Kommandoen følger `appsetting`-presedensen — samme rolle, samme
begrunnelse — og gjør staging mulig å fylle med testdata før fase 3 skrives. Den permanente
flaten kommer i modulens eget admin-område, sammen med sentralbordet.

`--deaktiver` framfor sletting: FK-en fra `Oppdrag` er `PROTECT`, så en lokasjon i bruk kan
ikke forsvinne uten å ta historikken med seg. En test sjekker begge deler.

Med det er fase 1 ferdig.

---

## 2026-08-28 — Oppdragsmodulen er planlagt

Kun dokumentasjon. Ingen kodeendring. `docs/BESLUTNING_OPPDRAGSMODULEN.md`.

Modulen blir den første som tar `skriv: handling` i bruk. Nivået ble definert i deploy 1 med
akkurat denne bruken i tankene (§3.2 i rollemodellnotatet) og har stått tomt siden.

**Det André kalte kinkig — to grensesnitt avhengig av tilgang — er ikke et tilgangsproblem.**
Fristelsen er å la nivået velge skjerm: «har du `skriv_handling`, får du bilskjermen». Det er
samme feil som §2.3 beskrev, å bruke et *ordnet* nivå som en *identitet*. Stigen sier at
`skriv_full` dekker `skriv_handling`, og et oppslag på «er nivået nøyaktig `skriv_handling`»
bryter den regelen stille.

Skillet er i stedet rolle i felt: **er kontoen knyttet til en `Enhet`?** Da får den
enhetsskjermen. Ellers sentralbordet, redigerbart med `skriv_full` og skrivebeskyttet med
`les`. Mønsteret finnes allerede — `Forstehjelper.user` er domenedata, ikke autorisasjon, og
§7.3 delte `PasientRolleForm` nettopp for å holde de to fra hverandre. Samme regel her: å
knytte en konto til en enhet gir ingen tilgang.

**Én invariant måtte skjerpes for å overleve offline-kravet.** §3.2 slo fast at et
handling-endepunkt ikke skal lese request-kroppen. En stempling utført uten dekning må kunne
fortelle når den skjedde, ellers viser statistikken når nettet kom tilbake. Regelen er derfor
skrevet om strengere, ikke svakere: kroppen har et lukket skjema på to nøkler — `klienttid`
og `idempotency_key` — og alt annet gir 400. Det er testbart ved uttømming, i motsetning til
en feltwhitelist inne i en generell PUT, der settet av felter vokser med modellen.

**To ting fulgte av kravene uten å være bestilt.** At en enhet skal kunne ha ventende
oppdrag betyr at et oppdrag må kunne være tildelt uten å være påbegynt — altså en status
`Venter` før `Rykker ut`, og at det er enheten som setter `Rykker ut`, ikke 113 ved
oppretting. Gjorde 113 det, ville responstiden løpe fra et tidspunkt ingen i bilen hadde sett
oppdraget. Og at lokasjon ble en admin-vedlikeholdt nedtrekksliste flyttet personvernrisikoen:
feltet er ikke lenger fritekst, A.6/A.12 holder for det, og **fritekst står alene igjen** som
det som må unntas verdilogging. Det halverte fase 2.

Andre avgjørelser verdt å notere:

- **Offline gjelder kun enhetens stemplinger.** Skulle begge sider virke frakoblet, kunne to
  klienter endret samme oppdrag uten å vite om hverandre. Med kun stemplinger finnes ikke den
  konflikten: hver melding er en ny rad.
- **To knapper i grensesnittet, seks navngitte endepunkter på serveren.** Én «neste»-knapp og
  én «Ledig» er nok i en bil i bevegelse; fem knapper der fire alltid er ulovlige er fire
  måter å trykke feil på. Men `POST .../status/neste/` ville latt serveren utlede handlingen
  av gjeldende tilstand, med det kappløpet som følger når to trykk kommer tett.
- **Å starte neste oppdrag lukker det pågående automatisk.** Valgt for farten i felt.
  Kostnaden er at den `Ledig`-meldingen er avledet, ikke målt — derfor lagres et
  `automatisk`-flagg på raden, selv om ingenting viser det. Skillet kan ikke gjenskapes i
  ettertid, og en boolean koster ingenting.
- **«Ledig» er enhetens tilstand, ikke oppdragets, og den lagres ikke.** Ved vaktstart står
  alle enheter som `Ledig` — ikke fordi noe setter verdien, men fordi det er hva «ingen
  påbegynte oppdrag» ser ut som. En lagret status måtte nullstilles ved vaktstart og holdes
  i takt med oppdragsradene resten av vakta; to kilder til samme sannhet går i utakt første
  gang noe feiler halvveis, og da er det den lagrede som lyver. Sentralbordet viser
  `Ledig (2 venter)` — utledet av oppdragene.
- **Enhetsbytte er egen modell**, ikke en radtype i `Statusmelding`. Et bytte er ikke en
  status, og statistikken måler statusene — blandes de, må hver spørring huske å filtrere.
  Statusen står når et oppdrag flyttes: meldingene den første enheten rakk å sende skjedde.
- **To skjuleregler for enheten, begge server-side.** Fritekst utelates fra svaret straks
  status blir `Ledig`; hele oppdraget utelates 30 minutter etter. Skjules fritekst i JS,
  ligger teksten fortsatt i responsen — og en bil som blir stående ulåst er nettopp
  scenarioet regelen finnes for.
- **`Leverer` registrerer ikke hvor det leveres.** Bevisst, for å holde helseopplysninger og
  posisjon fra hverandre.
- **Ingen kobling til `patients`.** «Leveranse oppretter pasient» er notert som noe å vurdere
  senere; i dag ville det latt en `skriv_handling`-konto skrive indirekte inn i
  pasientmodulen.

**Fase 6 utløser registeret CLAUDE.md har varslet.** `/statistikk/` skal få én fane per
kildemodul — pasienter fra samleplass/skadestue, oppdrag fra bil/ambulanse, senere lag. I dag
importerer statistikkappen `patients.services` direkte, og CLAUDE.md sier hva som skjer når
modul nummer to skal levere tall: importen erstattes av et registry etter samme idiom som
`core.backup` og `core.arkiv`. Dette er modul nummer to. §5 gjelder uendret — en fane vises
kun hvis brukeren har `les` på kildemodulen, ellers gir aggregatene avledet innsyn.

Fase 2 står før fase 3: ellers er fritekstfeltet i prod med verdilogging på, og de radene kan
ikke fjernes uten å røre auditsporet. Fase 7 er stedet `AbstractArkiv` bygges — TODO har
utsatt den til modell nummer to faktisk skrives.

Sju faser, 31–44 t. To avklaringer står åpne nederst i notatet; ingen blokkerer fase 1.

---

## 2026-08-28 — `/pasienter/api/stats/` er slettet

**1002 tester grønne.** Ingen migrasjon.

Endepunktet var en rest fra Flask-porten, der header-chipsene ble hentet fra serveren. I dag
regnes de ut i `patients-table.js` fra pasientlista `/api/patients/` allerede har hentet, og
ingen JS-fil i repoet har noen gang kalt stien. Det var gatet på `patients: les` siden
deploy 1, så dette er opprydding, ikke en tetting.

**Det hadde allerede kostet noe.** Da statistikken ble skilt ut, ble det først skrevet at
endepunktet mater chipsene. Det stemte ikke, og forklaringen sto i docstringen til den ble
funnet. Et endepunkt uten konsument tiltrekker seg forklaringer ingen kan falsifisere.

Borte: `patients/views_stats.py` og URL-en. **Ingen redirect satt opp** — en videresending
finnes for klienter som *pleide* å kalle noe, og her fantes ingen.

**`basic_stats()` står igjen**, i motsetning til det jeg først la opp til. Den så ut til å
ha én kaller, endepunktet, men har to: `StatsMatcher` i `patients/tests_arkiv.py` arkiverer
en vakt og krever at `compute_arkiv_stats` gir nøyaktig samme tall. Skulle testen bygget
spørringen selv, ville den speilet produksjonskoden i stedet for å måle den — og sluttet å
fange en endring i hvilke pasienter som teller. Funksjonen er live-siden av den invarianten,
og det står nå i docstringen dens.

Testene i `core/tests_stats_cache.py` brukte endepunktet som prøveklut for
cache-dekoratoren, og kjører nå mot full statistikk. Kontrasten mellom 15 s og 60 s forsvant
med det — den var det eneste stedet 15-sekunders-TTL-en ble brukt — men at dekoratoren
respekterer den TTL-en den får, dekkes av lavnivåtestene som setter den eksplisitt.

Grensetesten i `statistikk/tests.py` er **snudd, ikke slettet**: den låste før at
endepunktet sto igjen, med et notat om at den skulle endres bevisst når rollemodell-arbeidet
avgjorde saken. Nå krever den 404. Neste som lurer på hvor stien ble av finner svaret i en
test i stedet for i git-historikken. Sett rød: la jeg URL-en tilbake, feilet den.

Fulgt opp i dokumentasjonen: `README.md`, `CLAUDE.md`, `core/stats_cache.py`,
`statistikk/views.py`, `docs/TEKNISK_DOKUMENTASJON.md` og `docs/BESLUTNING_STATISTIKK.md`.
Sistnevnte forutsatte at stien fantes og lot spørsmålet stå åpent til
`/pasienter/api/stats/live/` skulle bygges; svaret er nå gitt, og live-endepunktet er
upåvirket — det er et nytt endepunkt med et faktisk formål, og stien er ledig.

---

## 2026-08-28 — To avklaringer: testkontoen og `leder`-nivået

Kun dokumentasjon. Ingen kodeendring.

**Testkontoen i prod er Andrés egen konto uten admin.** Forrige oppføring førte den opp som
en åpen oppgave med den begrunnelsen at «den kan opprette og redigere ekte pasienter under
et navn som ikke tilhører noen på vakt». Det premisset holdt ikke — navnet tilhører noen, og
André håndterer kontoen selv. Punktet er lukket, med mekanikken (CASCADE på `ModulTilgang`,
SET_NULL på `Helsepersonell.user`, `AuditLog.user` blir NULL) beholdt for den dagen den
faktisk slettes.

**`leder`-nivået er merket «VURDER», ikke «skal gjøres».** Bruken er skrevet ned og
begrunnelsen står i §3.1, men behovet er ikke aktuelt. Det tas opp igjen når noen faktisk
skal ha nivået — et tomt nivå er lett å dele ut i god tro, og gir automatisk mer den dagen
det fylles.

---

## 2026-08-28 — Deploy 3: de fem flaggene er borte, og profilkortet sluttet å lyve

**1003 tester grønne** (6 nye). Migrasjon `accounts.0014_fjern_modulflagg`.

Siste steg av de tre i §8. `kan_redigere_pasienter`, `kan_redigere_vakter`,
`kan_redigere_utstyr`, `kan_se_rapport` og `kan_redigere_beredskap` er slettet fra
`CustomUser`. De sto igjen gjennom deploy 1 og 2 fordi en rollback måtte kunne bygge
matrisen fra `role`; da deploy 2 krympet feltet, lukket det vinduet uansett.

**Én ting leste dem fortsatt, og den viste feil svar til brukeren.** Kortet «Modul-tilganger»
på `/min-profil/` bygde på de fem flaggene. Backfillen i deploy 1 utledet fra `role` og rørte
flagget med vilje (§8.1), så en konto med `patients: skriv_full` fikk «Nei» på
pasientregistrering — over teksten «Ta kontakt om du trenger flere tilganger». Siden ba altså
brukeren melde fra om noe hen allerede hadde. Målt før endringen, med kollegaens matrise:

```
  Pasientregistrering    Nei
  Vakter                 Nei
  Utstyr                 Nei
  Rapport                Nei
  Beredskap              Nei
```

Etterpå:

```
  Pasientregistrering    Skrive: full
  Statistikk             Lese
```

To ting endret seg. Kortet **leser `ModulTilgang`** — samme kilde som håndhevelsen — og det
**følger modulregisteret** i stedet for fem hardkodede etiketter. «Vakter», «Utstyr» og
«Beredskap» er ikke moduler; de var plassholdere for apper som aldri ble skrevet, og kortet
lovet tilgang til noe som ikke finnes. Statistikk sto ikke i lista i det hele tatt.

Nivået vises nå med navn (`Lese`, `Skrive: full`) i stedet for Ja/Nei — kortet kan ikke si
«Ja» til en stige med tre trinn uten å skjule hvilket trinn du står på.

**«Slått av» og «ingen tilgang» holdes fra hverandre.** En deaktivert modul får merket «Av»
ved siden av nivået. Slås de sammen, leser brukeren et driftsvalg som et tilgangsvalg og ber
om noe hen allerede har fått.

Testen som fantes krevde bare at de fem etikettene sto i HTML-en, og var grønn hele veien
gjennom feilen. Den er erstattet av seks som måler innholdet, hver med et motstykke som
viser at funnet kan utebli. Alle tre er sett røde: jeg gjeninnførte flagg-oppførselen og
fjernet «Av»-skillet, og fikk henholdsvis tre og én feil.

`test_flagget_paavirker_ingenting` i `BackfillTests` er fjernet, ikke omskrevet. Den lagde to
brukere med samme rolle og ulikt flagg og krevde identiske rader. Uten feltet er de to
brukerne identiske, og testen kunne ikke lenger feile — en test som ikke kan feile er verre
enn ingen test, fordi den ser ut som et vern. Regelen står fortsatt i §8.1, og kartleggingen
låses av testen ved siden av.

`CustomUserPermissionFlagsTests` er snudd i stedet for slettet: den krevde før at de fem
feltene *fantes*, og krever nå at de er borte og at et forsøk på å sette dem feiler høylytt.

---

## 2026-08-28 — Kollegaens nivå satt i prod, og en testkonto som må vekk

Kun dokumentasjon. Ingen kodeendring.

Kollegaens konto står nå på `patients: skriv_full` + `statistikk: les`, med
Helsepersonell-koblingen på plass. Det er den kombinasjonen backfillen ville gitt en `lead`,
satt for hånd i matrisen etter §7.3-splitten — koblingen og tilgangen er to steg nå, med
vilje.

André opprettet i tillegg en testkonto i prod for å kontrollere de samme nivåene selv.
**Den står oppført som en oppgave, ikke som en ferdig ting.** En konto med `skriv_full` i
prod er ikke et testmiljø: den kan opprette og redigere ekte pasienter, og gjør det under et
navn som ikke tilhører noen på vakt. Den må slettes eller deaktiveres før neste vakt, og den
har nøyaktig samme nivåer som kollegaens — det er navnet som skiller dem.

---

## 2026-08-28 — Deploy 2: `role` krympet til `admin`/`bruker`

**997 tester grønne.** Migrasjon `accounts.0013_krymp_role`. **Ikke deployet til prod** —
det krever en egen avgjørelse, se under.

`role` hadde fem verdier. Fire av dem — `lead`, `lead_view`, `read_write`, `read_only` —
beskrev *hva brukeren fikk lov til*, og ingen view leste dem etter at `@modul_kreves` ble
håndhevet i deploy 1. En verdi som ser ut som tilgangskontroll uten å være det er verre enn
ingen verdi: den inviterer neste utvikler til å gate på den. De er nå `bruker`.

**Rekkefølgen var poenget.** Først ble koden gjort uavhengig av de fire verdiene, så krympet
feltet. Motsatt vei ville gitt et vindu der en `has_role_at_least(user, 'read_write')`
sammenlignet mot en verdi som ikke lenger fantes — og den sammenligningen feiler ikke, den
svarer bare feil.

Det som forsvant med koden:

- `has_role_at_least`, `role_required`, `write_required`, `stats_required` og
  `dataset_scope_all` fra `core.auth_decorators`. Igjen står `er_global_admin`,
  `admin_required`, `har_tilgang` og `modul_kreves`.
- `ARKIV_VIEW_MIN_ROLE` og `ARKIV_WRITE_ROLE` fra `patients.services`. De var
  «konfigurerbare» — kommentaren foreslo `lead_view` eller `lead` — til verdier som ikke
  finnes lenger. Arkivet er global admin, og sier det nå rett ut.
- **De to bulk-knappene på brukerlista.** De skrev `kan_redigere_pasienter` på en gruppe
  kontoer og meldte «Fjernet pasientregistrering fra N bruker(e)» uten at noen mistet noe.
  Den meldingen er farligere enn ingen knapp: neste gang tilgang faktisk skal trekkes
  tilbake, tror admin at jobben er gjort.
- **Halve `verifiser_modultilgang`.** Sammenligningen mot `role` og §10.1-tellingen er
  fjernet, ikke gjemt bak en sjekk. Begge krevde at de fire verdiene fantes; etter
  krympingen ville de svart «ingen avvik» og «Antall: 0» om hver eneste database. Et svar
  som alltid er grønt er verre enn ingen kontroll. Igjen står kontroller som holder seg
  like sanne om ti moduler: kontoer uten rader, rader på en modul som ikke finnes, rader
  med et nivå stigen ikke kjenner, og rolleverdier feltet ikke lenger har.

Grensesnittet: rollebadgene i `user_list.html` og `user_detail.html` viser admin mot bruker,
og rollefeltet har fått hjelpetekst. «Bruker» skal ikke leses som «vanlig tilgang» — kontoen
ser ingenting før matrisen sier noe annet.

**Testene sier nå hva kontoen kan, ikke hva den het.** `gi_standardtilgang(bruker)` leste
`bruker.role` og slo opp radene backfillen ville gitt. Det gikk så lenge rollen *var* en
tilgangsverdi; nå ville oppslaget gitt alle testbrukere det samme, nemlig ingenting.
Hjelperen tar en profil eksplisitt — `leser`, `skriver`, `leder_les`, `leder`, `admin` — og
et ukjent profilnavn kaster i stedet for å gi tom tilgang. Det siste er ikke pedanteri: en
test som forventer 403 ville bestått uten å teste noe.

`BackfillTests` skriver fortsatt `read_write` og `lead` med vilje. Migrasjon 0012 kjørte mot
en database der de verdiene fantes, og det er den kjøringen som avgjorde hva kontoene i prod
fikk. Skrev testen `bruker`, ville den bekreftet at backfillen ikke gjør noe.

**Migrasjonen er reverserbar, men vinduet er ikke.** `bruker` → `read_only` ved reversering:
den laveste av de gamle verdiene, fordi reverseringen ikke kan vite hvem som var `lead`.
Matrisen står urørt begge veier — verifisert ved å kjøre migrasjonen fram og tilbake mot en
prod-lignende database. Men etter deploy 2 kan **ikke** en rollback av deploy 1 bygge
matrisen på nytt fra `role`. `ModulTilgang` er eneste fasit fra da av.

På PostgreSQL kjører `AlterField` ingen SQL: `choices` er ikke et databaseattributt. SQLite
bygger tabellen om uansett, men det gjelder bare lokalt og i offline-modus.

---

## 2026-08-28 — `leder`-nivået har fått en begrunnelse, men bygges ikke

Kun dokumentasjon. Ingen kodeendring.

Da `leder` ble tatt ut igjen tidligere samme dag, var argumentet at nivået **ikke hadde
noen definert bruk**, og at et tomt nivå er lett å dele ut i god tro. Det premisset holder
ikke lenger: André har navngitt bruken — **«admin light»**, en vaktleder som skal kunne mer
enn `skriv: full` uten å være global admin.

Sannsynlig innhold, ut fra hva som i dag er admin og som *ikke* er irreversibelt:
arkivere en vakt, se arkivet, redigere navneregistrene. §3.3 gjelder fortsatt for resten —
nullstilling, kollaps, brukeradmin og backup er irreversible eller konto-nære og skal ikke
desentraliseres. «Admin light» er ikke «admin med færre klikk».

**Nivået bygges ikke nå**, fordi behovet ikke er aktuelt. Men begrunnelsen er skrevet ned
så neste runde slipper å utlede den på nytt — og fordi den motsier argumentet som ble brukt
for å ta nivået ut. Å legge til verdien er en `-- (no-op)`-migrasjon; kostnaden ligger i å
bestemme innholdet.

**Kontoen i prod beholdes.** Spørsmålet var om den skulle slettes. Den er den eneste
ikke-admin-kontoen i produksjon, og admin har bypass på hele den nye tilgangsmodellen — uten
den er modulsynlighet, `les` mot `skriv_full` og den server-side gatingen av knapper
utestet i prod til noen får en konto. Da oppdages en feil av en som skal jobbe.

---

## 2026-08-28 — Forhåndsvisning av backfillen, før den kjøres

**1002 tester grønne** (5 nye). Ingen migrasjon.

`verifiser_modultilgang` kunne bare kjøres *etter* deploy 1 — den leser `ModulTilgang`, og
tabellen finnes ikke i prod før migrasjonen har kjørt. `--forhandsvis` viser hva backfillen
**vil** gi hver konto, lest fra `role` alene, uten å røre tabellen. En test teller
spørringer mot den for å håndheve det: går det én, ville kommandoen krasjet i prod.

Den advarer særskilt om én felle: **å «redusere» en konto ved å fjerne
`kan_redigere_pasienter` gjør ingenting.** Flagget stengte aldri et endepunkt (§2.1), og
backfillen utleder fra `role` alene (§8.1) — så kontoen får `skriv_full` likevel. Uten
advarselen ville noen tro de hadde tatt bort skrivetilgang, og oppdaget det motsatte etter
deploy.

Skal en konto ha mindre: endre `role` **før** deploy, eller sett nivået i matrisen
**etter**.

---

## 2026-08-28 — `.admin-only` og `.write-only` rendres server-side

**997 tester grønne.** Ingen migrasjon, ingen endring i hvem som har tilgang.

Klassene skjulte markup i nettleseren med `display:none`. Elementene lå i HTML-en uansett
rolle — inkludert URL-ene til alle admin-sidene. Endepunktene var gatet, så det var ingen
tilgangsgrense, men det er ingen grunn til å sende noe vi vet mottakeren ikke skal ha.

Seks admin-kort og tre skriveknapper rendres nå bak `{% if er_global_admin %}` og
`{% if kan_skrive %}`. Målt i nettleser:

| Konto | «Ny pasient» | Admin-kort | `/portal-admin/` i HTML |
|---|---|---|---|
| `les` | nei | nei | nei |
| `skriv_full` | ja | nei | nei |
| admin | ja | ja | ja |

**`applyRoleVisibility()` er borte.** Den gatet nøyaktig disse tre klassene, og hadde
ingenting igjen å gjøre. `.list-only` var dessuten allerede dødt: `les` er terskelen for å
nå siden i det hele tatt, så betingelsen var alltid sann.

**`er_global_admin` er en context processor** i stedet for noe hvert view sender.
Malene gatet på `request.user.role == 'admin'` direkte — det virker fortsatt, siden `admin`
overlever krympingen i deploy 2, men det er rollefeltet, og hele poenget med rollemodellen
er at maler ikke skal spørre om rollen. Én kilde, med samme navn som helperen i
`core.auth_decorators`.

Testene som kjørte `applyRoleVisibility()` i node er erstattet av tester på riktig lag, og
de er **strengere**: de krever fravær fra HTML-en, ikke at noe er skjult. Verifisert ved å
bytte begge gatene til `{% if True %}` og se seks tester bli røde.

---

## 2026-08-28 — Kontrollkommandoen før deploy 2, og dokumentasjonen ajour

**997 tester grønne** (6 nye). Ingen migrasjon, ingen atferdsendring.

**`python manage.py verifiser_modultilgang`** svarer på §10.1, som deploy 2 ikke kan
kjøres uten. Den skriver ingenting, og har en test som håndhever det: deploy 2 krymper
`role`, og etter det er `ModulTilgang` eneste fasit — feil i denne kontrollen oppdages
først når det ikke lenger går an å regne seg tilbake.

Tre spørsmål den svarer på: hvor mange kontoer hadde skrivetilgang uten flagget (altså en
tilgang de ikke var ment å ha), hvem har ingen rader i det hele tatt (ser en tom portal),
og hvor avviker matrisen fra det backfillen ga.

**Admin er utelatt fra §10.1-tallet**, selv om notatet skriver «role >= read_write».
Formålet er «kontoer som hadde en tilgang de ikke var ment å ha», og global admin var ment
å ha den — de har alltid hatt bypass. Tas de med, teller tallet kontoer som aldri var et
problem, og signalet drukner. På staging var forskjellen 6 mot 4.

**`WRITE_ROLES` er fjernet.** Den var én av de fem kopiene av rollelista (§2.6), og sto
igjen som en ubrukt import etter at skrivesjekkene byttet til `har_tilgang`.

**Dokumentasjonen er ajour:** `CLAUDE.md` beskrev fortsatt rollehierarkiet og
`permission_flag` som gjeldende, og `docs/BESLUTNING_STATISTIKK.md` hadde en tilgangstabell
med `admin/lead/lead_view`. Den siste sier nå eksplisitt at full-stats krever **både**
`statistikk: les` og `patients: les` — modulen komponerer tilgang, den eier den ikke.

---

## 2026-08-28 — To mangler i deploy 1, meldt fra staging

**991 tester grønne** (4 nye). Ingen migrasjon. Begge var funksjonalitet som var *bygget*
men ikke *nåbar* — endepunktet var riktig, veien dit fantes ikke.

**Portalinnstillingene hadde ingen lenke.** `/portal-admin/innstillinger/` var kun
tilgjengelig ved å skrive stien. En side ingen finner er i praksis ikke levert. Lenken
ligger nå i admin-navigasjonen, og `PortalAdminNavTests` går gjennom **hele** nav-blokka —
ikke bare den nye siden — så neste admin-side ikke kan få samme mangel.

**Sletteknappen manglet for `skriv_full`.** Endepunktet var riktig fra §4.2, men knappen i
redigeringsskjemaet var `.admin-only`, så bare admin så den. Rollemodellen var ny; knappen
var gammel.

Den kunne ikke bare bytte klasse: **om en pasient kan slettes avhenger av hvem som
opprettet den og når**, og ingen av delene finnes i klienten. Serveren sender derfor
`kan_slettes` per pasient, og knappen følger det feltet. Standarden er skjult — mangler
feltet, forsvinner knappen.

Flagget koster **én spørring for hele lista**, ikke én per pasient: oppslaget er filtrert på
både bruker og 30-minutters-vinduet, så resultatet er lite uansett listestørrelse. Et
oppslag per rad ville gitt N+1 på endepunktet som pollet hvert 30. sekund av hver klient —
nettopp det `select_related` ble innført for å fjerne.

### Notert, ikke fikset

`.admin-only` og `.write-only` skjules i nettleseren, ikke på serveren — markupen ligger i
HTML-en uansett rolle. Endepunktene er gatet, så det er ikke en tilgangsgrense, men det
røper URL-strukturen for admin-sidene. Husets etablerte mønster, og eldre enn dette
arbeidet. Lagt i TODO; `PortalAdminNavTests` beskriver skillet mellom nav-blokka (gatet
server-side, og testet) og resten.

---

## 2026-08-28 — Deploy 1 ferdig: §4.1 og §4.2

**989 tester grønne** (18 nye). Ingen migrasjon. Deploy 1 er dermed komplett.

### §4.1 — portalinnstillingene flyttet

Arrangementsnavn og sesjonstimeout lå under `/pasienter/` fordi pasientmodulen var den
eneste som fantes. Ingen av dem hører til der: navnet gjelder vakten, som med flere moduler
dekker mer enn pasientregistreringen, og timeouten gjelder innloggingen. Begge krevde
dessuten global admin — og **et admin-endepunkt inne i en modul sier at modulgrensen ikke
betyr noe**, som er nettopp den sammenblandingen `ModulTilgang` skal fjerne.

Begge ligger nå på `/portal-admin/innstillinger/`. `PUT /pasienter/api/settings/` og hele
`api/session-timeout/` er borte; `GET /api/settings/` blir igjen, fordi headeren og
årsfiltreringen trenger verdiene og de er ufarlige for alle som kan lese modulen.
Innstillingsfanen har en lenke i stedet for feltene, og `saveEventName` er ute av
pasientmodulens JS — som F7-notatet i §4.1 forutså.

Validering flyttet med: `AppSetting` er en generisk nøkkel/verdi-tabell uten den, og en
timeout på 0 timer ville logget ut alle umiddelbart. Arrangementsnavnet skrives **etter** at
timeouten er validert, så en avvist innsending ikke lagrer halve skjemaet — det har egen
test.

### §4.2 — slettevindu på 30 minutter

`skriv_full` kan hard-slette **egne** pasienter opprettet siste 30 minutter. Eldre
sletting, og andres, forblir global admin.

Treffer feilregistrering — en duplikat eller et feiltrykk som blokkerer et pasientnummer og
forstyrrer statistikken — uten å gjøre sletting til et hverdagsverktøy. Den som oppdager
feilen er den som registrerte, ikke en admin som kanskje ikke er på vakt.

**«Egen pasient» avgjøres fra auditloggen, ikke fra et nytt felt.** `Patient` har
`created_at`, men ingen `opprettet_av`. `AuditLog` har CREATE-raden med `user`, og
`(table_name, record_id)` er indeksert — billig oppslag, ingen migrasjon.

**Fail-closed:** mangler CREATE-raden, eller har den ingen `user` (importerte rader),
nektes slettingen. «Vet ikke hvem som opprettet den» skal ikke bety «hvem som helst».

Forbeholdet fra §4.2 følger med: DELETE-loggingen lagrer bare pasientnummeret, ikke
innholdet. Etter en sletting vet man *at* pasient #14 ble slettet av Kari 14:32, ikke hva
som sto der. Innenfor et 30-minutters vindu på egne rader er det akseptabelt. Åpnes
sletting bredere senere, må DELETE-loggingen utvides først.

### Verifisert i nettleser

Hele innstillingsflyten: lagring i portal-admin slår gjennom i pasientmodulens header.
Underveis så det ut som lagring logget admin ut — det var probens egen selektor som traff
utloggingsknappen i headeren, ikke skjemaets. Verdt å notere fordi konklusjonen «lagring
dreper sesjonen» ville vært en alvorlig feilmelding å sende videre.

---

## 2026-08-28 — Deploy 1, del 5: varsler, og §9-oppryddingen

**971 tester grønne** (5 nye). Ingen migrasjon. Siste del av deploy 1 utenom §4.1 og §4.2.

**`notify()` sjekker modultilgang** (§10.4). Tilstanden var umulig før `PasientRolleForm`
ble splittet: radioen satte koblingen og tilgangsflagget samtidig, så den som var koblet
hadde per definisjon tilgang. Etter splitten er de uavhengige — og da kunne
`_notify_assignment` sendt et varsel som inneholder et **pasientnummer** og lenker til en
side brukeren får 403 på. Både en lekkasje og en blindvei.

Sjekken ligger i `notify()`, ikke hos hver kaller: en kaller som glemmer den feiler stille,
og `notify()` er den ene porten alle varsler går gjennom.

**En ukjent `module_slug` logges høyt.** Uten det skillet ville en skrivefeil («patient» for
«patients») fått alle varsler til å forsvinne — samme utfall som manglende tilgang, men en
helt annen årsak, og den ene er en feil ingen ville oppdaget. Testene brukte selv
`module_slug='p'`, som ikke er en registrert modul; det ble funnet av nettopp denne sjekken.

### §9-oppryddingen

**`accounts/mixins.py` er fjernet.** Ingenting importerte den, og den var feil:
`RoleRequiredMixin.dispatch()` kalte `super().dispatch()` *først* — altså kjørte viewet —
og reiste `PermissionDenied` etterpå. En POST ville blitt utført og deretter fått 403.
Første klassebaserte view som grep etter `WriteRequiredMixin` ville arvet det.

**`dataset_scope_all` er fjernet.** Definert, re-eksportert i shimen og testet, men sto
aldri på et view.

`accounts/decorators.py` beholdes som shim så lenge `core/tests.py` verifiserer den (N11).

**`docs/TEKNISK_DOKUMENTASJON.md` §6.3 er skrevet om.** Den beskrev et rollehierarki
håndhevet via shimen, med en rollematrise som ikke lenger stemmer og en rad som kalte
hard-deleten «soft». Seksjonen beskriver nå de tre kategoriene, nivåstigen, og at
`CustomUser.role` er under avvikling.

---

## 2026-08-28 — Deploy 1, del 4: grensesnittet gater på det samme som døra

**966 tester grønne** (8 nye). Ingen migrasjon. Meldt fra staging: en konto ble satt ned
fra `skriv_full` til `les`, og «Ny pasient» ble stående. Brukeren fikk opp
registreringsskjemaet, fylte det ut, og møtte 403 på lagre.

Serveren var riktig hele tiden. `applyRoleVisibility()` gatet på `window.USER_ROLE` — og
rollen sier ikke lenger noe om hva du får gjøre i en modul. En `read_write`-konto med bare
`les` fikk `canWrite = true` i nettleseren.

**En knapp som fører til en vegg er verre enn ingen knapp:** brukeren rekker å gjøre
arbeidet før hen får vite at det ikke gikk.

§7.4 er dermed framskyndet fra deploy 2. `window.USER_ROLE` er borte; malen sender
`window.MODUL_TILGANG = {patients: <nivå>, admin: <bool>}`. `admin` er eget felt fordi
global admin står utenfor modulaksen. Redigeringsskjemaet gates på samme kilde — det kunne
også åpnes av en `les`-bruker, med 403 først på lagre.

**Standarden er ingen tilgang.** Mangler globalen, skjules alt som krever noe. Feiler
malen, skal knappene forsvinne — ikke dukke opp.

**Ett skille forsvant med rollene.** `les` dekker både gamle `read_only` og `lead_view`,
som var uenige om pasientlista: den ene fikk den, den andre ikke. Skillet lå aldri i
dataene — `/api/patients/` returnerer det samme til begge, og tavla viser de samme
pasientene. Lista gis derfor til alle som kan lese.

Testene kjører `applyRoleVisibility()` i node med et stubbet DOM, ikke som grep etter
kodelinjer. Verifisert ved å sette `canWrite = true` og se dem bli røde.

---

## 2026-08-28 — Deploy 1, del 3: hullet fra §2.1 er lukket

**958 tester grønne** (9 nye). Ingen migrasjon. Meldt fra staging: en konto uten
modultilgang kom fortsatt inn ved å skrive `/pasienter/` i adressefeltet.

Riktig observert. Synligheten var strammet i del 1, men døra sto åpen — og det er den
kombinasjonen §2.1 beskriver som verst: menyen sier nei, endepunktet sier ja.

**`@modul_kreves` står nå på alle ruter under `/pasienter/` og `/statistikk/`.**
Skrivesjekkene inne i viewene har byttet fra `WRITE_ROLES` til
`har_tilgang(user, 'patients', 'skriv_full')` — rollelista var én av fem kopier (§2.6).

Målt før og etter, med de samme tre kallene notatet brukte:

| | Før | Nå |
|---|---|---|
| `GET /pasienter/` | 200 | **403** |
| `GET /pasienter/api/patients/` | 200 | **403** |
| `POST /pasienter/api/patients/` | 201 (pasient opprettet) | **403**, ingenting opprettet |

Verifisert i nettleser, ikke bare i testklienten.

**URL-gjennomgangstesten er vernet §6 etterlyste.** Den går gjennom `urlpatterns` for
modulens prefiks og krever at hvert view bærer markøren dekoratøren setter — den gjetter
ikke, for en gjetning som tar feil den ene veien slipper et udekorert endepunkt gjennom.
To ruter står i en unntaksliste med begrunnelse; begge er rene videresendinger til
endepunkter som har sin egen gate. Testen sjekker også at unntakene fortsatt finnes, og at
den i det hele tatt finner ruter — en URL-gjennomgang som ikke finner noe passerer
trivielt, og det skjedde i denne kodebasen samme dag med en annen test.

Den fant to hull med en gang: en navnløs legacy-videresending, og statistikkmodulen, som
fortsatt gikk på `stats_required`.

**§5-komposisjonen er på plass.** Statistikkmodulen viser kun kilder brukeren har minst
`les` på i kildemodulen. Uten den er statistikk en bakvei rundt modultilgangen — aggregater
gir avledet innsyn i data man ikke har tilgang til. I dag er `patients` eneste kilde, så
sjekken er én linje; når kilde nummer to kommer, blir det en løkke over registeret.

**Én reell svakhet funnet underveis:** en POST som utelot matrisefeltene fjernet all
modultilgang. Nettleseren sender alltid alle `<select>`-ene, men et delvis skjema, et
skript eller en integrasjon ville stille tilbakekalt tilgang. Fravær av nøkkel er nå ikke
det samme som «velg ingen». Å trekke tilbake tilgang skal være et valg noen tar.

**~90 testbrukere fikk radene backfillen ville gitt dem**, via `gi_standardtilgang()` i
`accounts/test_helpers.py`. En bruker uten rader er en kanttilstand i produksjon, ikke
normalen — de som fantes fikk rader av migrasjonen, nye får dem av matrisen. Testene som
handler om *fravær* av tilgang har bevisst ikke kallet, og sier det i en kommentar.

---

## 2026-08-28 — Deploy 1, del 2: matrisen som faktisk setter tilgang

**946 tester grønne.** Ingen migrasjon. Meldt fra staging: en ny testkonto fikk
«Pasientregistrering» og «Førstehjelper» satt, men så ingen modul på dashboardet.

Det var forutsigbart og forutsagt — §10.3 i beslutningsnotatet — men det gjorde
grensesnittet direkte villedende: avkrysningsboksen «Pasientregistrering» satte
`kan_redigere_pasienter`, og synligheten sluttet å lese det flagget i forrige commit.
Boksen lovet noe den ikke gjorde.

**De fem boksene er erstattet av en matrise modul × nivå**, generert fra
`get_all_modules()`. Boksene var hardkodet i malen, så hver ny modul krevde en redigering
der i tillegg til et nytt felt på `CustomUser`. `admin_only`-moduler er utelatt: de gates
av global admin og bruker ikke `ModulTilgang`, og å vise dem ville antydet at nivået betyr
noe for dem.

**Matrisen ligger på opprettingsskjemaet også** (§10.3), ikke bare på redigering. Uten det
lander den nyopprettede i en tom portal og må redigeres etterpå — og den som oppretter
kontoen er den som vet hva den skal ha.

**`skriv_handling` tilbys ikke i grensesnittet ennå.** Nivået finnes i modellen, og det er
nettopp derfor det ikke trengs en migrasjon den dagen det tas i bruk. Men det er tomt
inntil en modul har et handling-endepunkt, og et nivå som ikke gir noe er lett å dele ut i
god tro. Samme resonnement som `leder` ble tatt ut på. Har en bruker likevel nivået, står
det i lista — ellers ville et lagre-trykk stille fjernet det.

**`PasientRolleForm` er splittet** (§7.3). Radioen satte både FK-en og
`kan_redigere_pasienter`; det er funksjon i felt og autorisasjon i samme kontroll.
Sammenblandingen gjorde det umulig å være koblet som førstehjelper uten å ha tilgang, og
omvendt. To steg i stedet for ett, bevisst.

**Tilgangsendringer auditeres nå**, én rad per modul som endres, med
`table_name='accounts_modultilgang'` slik at de ikke ser ut som endringer på selve kontoen.
**Rolleendring auditeres også** — frysing og sletting skrev auditrad, men det å gi noen
admin gjorde det ikke. Et lagre-trykk uten endring skriver ingenting.

`create_offline_users` gir `vakt-offline` sin rad. Den hadde `role='read_write'` og ingen
tilgang; med håndhevelse ville feltmaskinen møtt en tom portal, og det oppdages i det den
skal brukes — på en vakt uten nett.

En egen test sjekker at matrisen ligger **inne i** riktig `<form>`. POST-testene hadde
bestått uansett hvor i malen feltene havnet.

---

## 2026-08-28 — Deploy 1, del 1: `ModulTilgang` og håndhevelsen

**937 tester grønne** (23 nye). To migrasjoner, begge rullbare. Første del av deploy 1 i
`docs/BESLUTNING_ROLLEMODELLEN.md`; håndhevelsen på endepunktene kommer i neste commit.

`accounts.ModulTilgang(bruker, modul_slug, nivaa)` erstatter de fem
`kan_redigere_*`-flaggene. Nivåene er `les < skriv_handling < skriv_full`; **ingen rad er
ingen tilgang**, og det finnes ingen `'ingen'`-verdi å lagre — to måter å uttrykke det
samme på kommer før eller siden i utakt.

`modul_slug` er bevisst ikke en FK: modulregisteret ligger i kode, ikke i basen, og en rad
for en modul som fjernes fra registeret skal bli liggende ubrukt i stedet for å forsvinne
stille med en CASCADE.

**Backfillen utleder fra `role` alene, ikke fra flagget** (§8.1). Flagget har aldri stengt
et endepunkt, så en bruker som i dag *kan* nå modulen via URL-en ville mistet den i det
håndhevelsen slås på — og en migrasjon som stille trekker tilbake tilgang oppdager du
midt i en vakt. Radene som oppstår bekrefter tilgang folk allerede hadde; ingen
privilegier oppstår, de blir bare synlige. Innstrammingen gjøres etterpå, for hånd.

**Synligheten leser nå samme kilde som håndhevelsen.** `Module.is_visible_for()` leste de
fem flaggene, som ingen view sjekket — menyen og døra var uenige, og det var døra som sto
åpen. `Module.permission_flag` og det midlertidige `min_rolle` er fjernet fra dataklassen;
modellfeltene på `CustomUser` står til deploy 3, ellers har en rollback ingenting å bygge
radene fra.

**`ModuleSettings.enabled=False` stenger nå URL-en** (§2.2). Toggelen var en menybryter —
`GET /pasienter/` ga 200 med modulen deaktivert. Global admin slipper fortsatt inn, ellers
kan man deaktivere seg selv ut av å kunne reaktivere.

`@modul_kreves('patients', 'skriv_full')` er dekoratør, ikke middleware (§6): middleware er
ett sted å glemme, men også ett sted å ta feil av `/pasienter/api/...`. Ukjent nivånavn gir
**False**, ikke True — en skrivefeil i en dekoratør skal stenge døra. Dekoratøren setter en
markør URL-gjennomgangstesten leser, slik at testen ikke trenger å gjette på om et view er
dekorert.

Radene caches per brukerobjekt: nav-menyen kaller `is_visible_for` én gang per modul, og
uten cachen ble det én spørring per modul per sidevisning.

**Backfillen testes ved å kalle migrasjonens egen funksjon**, ikke ved å gjenta
kartleggingen — en test som gjentar logikken består selv om migrasjonen gjør noe annet.
Verifisert ved å forfalske kartleggingen og se testen bli rød.

---

## 2026-08-28 — To feil på staging, og testene som ikke fanget dem

**913 tester grønne** (2 nye). Begge feilene ble meldt fra staging, og begge var samme
klasse: **kode flyttet til en side som ikke gir den det den trenger.** Ingen av dem ga
syntaksfeil, og ingen ble fanget av testsuiten — som er serverside, eller som
sammenligner navn og ikke oppslag.

**«Ny pasient» sluttet å virke.** `patients-utils.js` hadde fortsatt `Chart.defaults` på
toppnivå. Blokken ble kopiert til `statistikk.js`, men aldri fjernet her — og pasientsiden
laster ikke lenger Chart.js. `ReferenceError` drepte resten av fila, så `allPatients`,
klokka og `bsNew`/`bsEdit` aldri ble opprettet. Alt under den linja var borte.
`patients-admin.js` erklærte i tillegg `forstehjelpere` og `helsepersonellListe` på nytt;
to `let` med samme navn i global scope er en `SyntaxError` som drepte hele den fila.

**Statistikkfanene byttet ikke.** `loadStats()` begynte med en rollesjekk på
`window.USER_ROLE` — en global bare pasientmalen setter. På `/statistikk/` falt den til
`'read_only'` og returnerte før første hent. Statistikken var permanent tom, uten én
feilmelding. Kommentaren jeg selv skrev i toppen av fila sa at sjekken var fjernet; den
var ikke det. Endepunktet den kalte var dessuten den gamle stien.

Begge er funnet ved å kjøre sidene i headless Chromium og lese konsollen, ikke ved å lese
koden. Klikkbanen er verifisert samme vei.

**Fanen bytter nå før hentingen, ikke etter.** `loadStats()` returnerer uten å rendre hvis
hentingen feiler (403, 429) — så en bruker som trykket på «Tidsanalyse» ble stående på
forrige fane uten forklaring, også når koden ellers virket.

### To nye tester, begge verifisert ved å gjeninnføre feilen

- **`window.X` må settes av malen** som laster fila. En global malen ikke setter er
  `undefined`, ikke en feil — og det er nettopp derfor den er farlig: koden tar en stille
  default og gjør noe annet enn den skal.
- **`Chart`/`Tabulator`/`bootstrap` må lastes av siden** som laster fila.

**Første utgave av den andre testen var falsk grønn, to ganger.** Den leste rå malmarkup,
og `{% comment %}`-blokken som forklarer at Chart.js *ikke* lastes lenger inneholder
strengen «Chart.js». Rettet til å lese `<script>`-tagger — hvorpå
`src=["\']([^"\']+)["\']` stoppet på den første fnutten inne i
`src="{% static 'js/x.js' %}"`, JS-lista ble tom, og **begge** testene passerte uten å
sammenligne noe. Begge gangene ble det oppdaget ved å gjeninnføre feilen og se at testen
ikke merket det. En test som ikke er sett rød er ikke en test.

### `leder`-nivået reversert

Lagt til tidligere samme dag, tatt ut igjen. Begrunnelsen var at et nytt nivå senere ville
koste en migrasjon på en tabell med produksjonsdata. Det stemmer ikke: `choices` ligger i
Djangos `Field.non_db_attrs`, og `sqlmigrate` sier `-- (no-op)`. Uten den kostnaden står
bare ulempene igjen — nivået har ingen definert bruk, og et tomt nivå i matrisen er lett å
gi bort i god tro. `skriv: handling` beholdes: det er også tomt i dag, men har en navngitt
bruker og en testbar invariant. Se §3.1 i beslutningsnotatet.

---

## 2026-08-28 — Statistikk er sin egen modul

**Etterord samme dag:** denne leveransen ble planlagt uten at
`docs/BESLUTNING_ROLLEMODELLEN.md` var lest — notatet lå på branchen `rollemodell`, ikke
på `main`, og jeg lette ikke etter andre brancher før jeg la planen. Beslutningen fra
24. aug. sier allerede det meste av det som ble utledet på nytt her, og sier det bedre:
statistikk først (§5), backfill fra `role` alene (§8.1), eksplisitt dekoratør (§6), tre
deployer (§8). To ting ble utledet annerledes og er nå rettet mot notatet:

- **Nivåstigen.** Notatet har `ingen → les → skriv:handling → skriv:full`; her ble det
  utledet `les → skriv → leder`. Besluttet 28. aug.: begge, altså
  `ingen → les → skriv:handling → skriv:full → leder`. Se §3.1.
- **Statistikkmodulen komponerer ikke tilgang ennå.** §5 krever at modulen kun viser
  kilder brukeren har minst `les` på i kildemodulen — ellers er den en bakvei rundt
  modultilgangen. Det kan først bygges når `ModulTilgang` finnes, og er lagt til deploy 1.

Koden under står som levert; ingenting av den er feil. Men flere av begrunnelsene er
gjenoppdagelser, og notatet er fasit der de spriker.


**911 tester, alle grønne** (17 nye i `statistikk/tests.py`, 3 nye i
`JsModulLastingTests`). Ingen migrasjon, ingen modellendring, ingen tilgangsendring.

Første av tre leveranser mot rollemodellen. Rekkefølgen ble snudd underveis, og grunnen er
verdt å skrive ned: **statistikk måtte ut av pasientmodulen før `ModulTilgang` kunne
utformes.**

Så lenge «ser statistikk» og «kan skrive» var to akser i samme modul, trengte et
tilgangsnivå per modul fire trinn — det er nettopp derfor `lead_view` (2) står over
`read_write` (1) i `ROLE_HIERARKI` uten å ha skrivetilgang, og derfor `write_required` er
en eksplisitt liste og ikke et `has_role_at_least`-kall. Med statistikk som egen modul blir
den aksen en rad til i tilgangstabellen, og stigen per modul blir `les < skriv < leder`:
en ekte stige. Bygget vi rollemodellen først, ville vi migrert inn en firetrinns kolonne og
måttet migrere den om igjen.

Backfillen hadde fått samme problem. `lead_view` skal ha en `statistikk`-rad, og finnes
ikke slug-en i `get_all_modules()`, er raden foreldreløs: admin-matrisen genereres fra
registeret, så ingen kunne sett eller rettet den.

**`lead_view` sin eneste forskjell fra `read_only` var statistikk.** Tre steder, alle tre
statistikk: `full_stats_view`, nav-elementet `.stats-only` og lastingen av
`patients-stats.js`. Sammenslåingen i den kommende backfillen er derfor tapsfri, ikke en
forenkling.

### Hva som flyttet

| Fra | Til |
|---|---|
| `patients/views_stats.py: full_stats_view` | `statistikk/views.py` |
| `patients/views_arkiv.py: arkiv_full_stats_view` | `statistikk/views.py` |
| `patients/stats_cache.py` | `core/stats_cache.py` |
| statistikkfanen i `templates/patients/index.html` | `templates/statistikk/index.html` |
| statistikkreglene i `static/css/style.css` | `static/css/statistikk.css` |
| ~600 linjer rendering i `patients-stats.js` | `static/js/statistikk.js` |
| ~370 linjer admin i `patients-stats.js` | `static/js/patients-admin.js` |
| primitivene i `patients-utils.js` | `static/js/portal-utils.js` |

`/pasienter/api/stats/` ble **ikke** flyttet.

**Rettelse, samme dag:** begrunnelsen som først sto her — «header-chipsene er for alle
innloggede og hører til siden de står på» — var feil. Chipsene regnes ut i nettleseren, i
`patients-table.js`, fra pasientlista `/api/patients/` allerede har hentet. Ingen JS-fil i
dette repoet har noen gang kalt `/api/stats/`; endepunktet er en rest fra Flask-porten, og
`basic_stats`-docstringen sa det hele tiden. Feilen var å gjøre en foreldet docstring til
bærende begrunnelse uten å sjekke hvem som faktisk kaller endepunktet.

Konsekvensen for denne leveransen er ingen — endepunktet ble uansett stående urørt. Men det
står nå uten kjent konsument, og valget mellom å gate det på pasientmodulen og å slette det
er lagt til rollemodell-arbeidet. `basic_stats()` som *funksjon* blir uansett stående: den
deler aggregeringen med `compute_arkiv_stats`.

### Fire ting som ikke var åpenbare

**Stilarket måtte deles.** `style.css` lastes kun av `patients/index.html`, så hver eneste
statistikkregel ville vært virkningsløs på den nye siden — en endring som ser ut som
ingenting, ikke som en feil. Verre: fire av variablene reglene bruker
(`--text-muted`, `--text-soft`, `--surface-3`, `--header-bg`) er definert i `style.css` og
er *ikke* blant aliasene `base_portal.html` setter. En udefinert custom property gjør ikke
regelen ugyldig — den gjør fargen arvet. Tabelltekst ville altså blitt lesbar eller
uleselig tilfeldig, uten at noe feilet. De fire er derfor definert i `statistikk.css` med
verdiene de hadde; de fire portalen faktisk aliaser er ikke gjentatt, så temaene ikke kan
komme i utakt.

**`patients-utils.js` kunne ikke bare lastes av den nye siden.** Den gjør arbeid på
toppnivå: setter `Chart.defaults` og kaller
`new bootstrap.Modal(document.getElementById('newModal'))`. Uten `#newModal` kaster fila
ved lasting. Primitivene begge sidene trenger — CSRF-fetch, escaping, submit-guard,
`data-action`-delegeringen og `fmtMin` — ligger nå i `portal-utils.js`, som ikke rører
DOM-en før den kalles. `fmtMin` ble faktisk glemt i første forsøk, og statistikksiden ville
kastet `ReferenceError` på hver varighet. `JsModulLastingTests` har fått en test som
sammenligner hva `statistikk.js` kaller mot hva den faktisk laster.

**Arkivstatistikken arvet nesten feil gate.** Endepunktet fulgte med til statistikk-appen,
men tilgangen skulle ikke: arkivet er strengere beskyttet enn live-statistikken
(`ARKIV_VIEW_MIN_ROLE`, i dag `admin`). Hadde det arvet statistikkmodulens gate, ville
`lead_view` fått innsyn i arkiverte vakter uten at noen bestemte det. Viewet har derfor to
gates, og `test_arkiv_full_stats_krever_riktig_rolle` dekker `lead_view` og `lead`.

**De gamle stiene videresender (302).** En deploy midt i en vakt treffer klienter med
gammel JS i cache, og `loadStats()` feiler stille: den logger en advarsel og lar forrige
visning bli stående. Brukeren ville sett gamle tall uten beskjed. 302 og ikke 301, så en
nettleser ikke sitter fast på videresendingen for godt.

### Tilgang: uendret, men strammere JS-lasting

`stats_required` gjelder fortsatt, nå på både siden og endepunktet. Modulsynligheten går
gjennom et nytt, **midlertidig** `min_rolle`-felt på `Module` — alternativet var et
`kan_se_statistikk`-flagg med migrasjon som uansett skulle kastes når `ModulTilgang` kommer.
Feltet fjernes sammen med `permission_flag`.

`patients-admin.js` lastes nå kun for `admin`, ikke for `lead`/`lead_view` som før. Alt som
ble igjen i fila krever `role='admin'` server-side, så de to rollene lastet ~370 linjer de
aldri kunne bruke — hvert endepunkt avviste dem.
---

## 2026-08-24 — Rollemodellen besluttet: modultilgang som faktisk håndheves

Ingen kodeendring. `docs/BESLUTNING_ROLLEMODELLEN.md` erstatter TODO-punktet
«Rollemodellen — trenger beslutning», som sto ubesvart siden 22. aug. Beslutningen måtte
tas før modul nummer to skrives.

**Flaggene var aldri tilgangskontroll.** Verifisert ved å kjøre koden: en `read_write`-bruker
med `kan_redigere_pasienter=False` får 200 på `/pasienter/`, 200 på `GET /api/patients/`
og **201 på POST** — altså full skrivetilgang til en modul hun ikke ser i menyen.
`permission_flag` leses kun av `Module.is_visible_for()`, som bare kalles fra dashboard og
nav. Fire endepunkt-grupper i `patients` er i dag beskyttet av `@login_required` alene.

**`ModuleSettings.enabled=False` stenger heller ikke URL-en** — `GET /pasienter/` gir 200
med modulen deaktivert. Toggelen er en menybryter, ikke nødbryteren navnet lover. Begge
deler rettes: modultilgang håndheves server-side med `@modul_kreves(...)`, og deaktivert
modul gir 403 for alle utenom global admin.

**Hierarkiet var ikke et hierarki av rettigheter.** `lead_view` ligger over `read_write`
(2 mot 1), men har ikke skrivetilgang — så `has_role_at_least(user, 'read_write')` er
`True` for en bruker som ikke står i `WRITE_ROLES`. Ingen live-bug: den hierarkiske
hjelperen brukes kun med `'admin'`, i `views_arkiv.py`. Men den er en felle for neste
modul, og forsvinner med den nye modellen.

**Modellen blir: global admin, pluss ett nivå per modul.** Utgangspunktet var to akser
(les × skriv), fordi dagens fem roller er nettopp det. Den ene aksen kollapset da
statistikk ble besluttet skilt ut som egen modul: `lead_view` gir nemlig *bare*
statistikk — `stats_required` beskytter to endepunkter, `.stats-only` dekker ett nav-punkt
og én fane, og `dataset_scope_all` er død kode som aldri har vært brukt. «Større leserett»
var «tilgang til statistikkmodulen» hele tiden. Igjen står
`ingen → les → skriv:handling → skriv:full`.

**`skriv: handling` finnes fordi en bil-konto skal kunne stemple, men ikke skrive fritekst.**
Det lar seg ikke løse med en rollesjekk: `stamp_pabegynt_if_needed()` og de to andre kalles
fra innsiden av den generelle `PUT`-en, med hele request-kroppen som argument — et
tidsstempel er i dag en bivirkning av en redigering. En feltwhitelist inne i viewet ville
sviktet stille første gang noen la til et felt. Regelen er derfor at en innskrenket aktør
får et *smalt endepunkt*, ikke et filtrert bredt et, og at et `handling`-endepunkt ikke
leser request-kroppen. Det siste er en invariant en test kan håndheve.

**Sletting åpnes forsiktig.** Hard-delete er admin-only i dag, ikke tilgjengelig for
skrivetilgang som antatt. Den åpnes for `skriv: full`, men bare på pasienter brukeren selv
opprettet siste 30 minutter — nok til å rydde en feilregistrering, ikke nok til å bli et
hverdagsverktøy. «Egen pasient» avgjøres fra `AuditLog`s CREATE-rad, som allerede har
bruker og er indeksert på `(table_name, record_id)`; ingen ny kolonne trengs. Forbeholdet
som følger med: DELETE-loggingen lagrer bare pasientnummeret, ikke innholdet — åpnes
sletting bredere senere, må den utvides først.

**Statistikkmodulen komponerer tilgang, den eier den ikke.** Den skal kun vise kilder
brukeren har minst `les` på i kildemodulen. Ellers er den en bakvei rundt modultilgangen.
Rekkefølgen følger av det: statistikk skilles ut før eller sammen med rollemodellen, ellers
bygges en les-akse som umiddelbart rives ned igjen.

**Tre deployer, ikke to.** TODO sa minimum to. Rollekrympingen (`role` → `admin`/`bruker`)
er destruktiv og må ligge mellom «legg til og fyll `ModulTilgang`» og «fjern flaggene».
Defaulten utledes fra `role` alene, ikke fra flagget: en migrasjon som stille trekker
tilbake tilgang oppdager du midt i en vakt.

Ryddes med på veien: `accounts/mixins.py` (død kode, og feil — `dispatch()` kjører viewet
*før* rollesjekken, så en POST ville blitt utført og deretter fått 403), `dataset_scope_all`,
og §6.3 i den tekniske dokumentasjonen, som peker på shimen og kaller hard-deleten «soft».
`session_timeout` og `event_name` flytter til portal-admin — de er portalinnstillinger som
tilfeldigvis bor under `/pasienter/`.

**Én forutsetning gjenstår, og den må kontrolleres i prod:** hvor mange kontoer har `role`
≥ `read_write` men `kan_redigere_pasienter=False`? Det er kontoene som i dag har en tilgang
de ikke var ment å ha, og tallet avgjør hvor stor oppryddingen blir etter deploy 1.

---

## 2026-08-23 — `/accounts/glemt-passord/` var en blank side i produksjon

**910 tester, alle grønne** (3 nye). Rettelse av forrige punkt, meldt av André minutter
etter deploy.

Alle fire reset-malene ble satt sammen ved å ta `head -22` av `invitasjon.html` som felles
hode. Det linjetallet stemte da jeg først så på fila — men jeg hadde selv lagt til
`::placeholder`-regelen der tidligere samme dag, og linjene hadde flyttet seg. `head -22`
kuttet dermed **midt i `<style>`-blokken**: ingen `</style>`, ingen `</head>`, ingen
`<body>`. Nettleseren leste resten av dokumentet som CSS og viste ingenting.

Rettet ved å klippe til og med `<body>` i stedet for til et gjettet linjetall.

**Testene fanget det ikke, og grunnen er verdt å skrive ned.** De sjekket at responsen var
`200`, og at innholdet var **identisk** mellom en adresse som finnes og en som ikke gjør
det. Begge var like ødelagte, så likhetstesten passerte med glans.

En test på at to ting er like sier ingenting om at noen av dem er riktige. Det er en
annen feilmodus enn den vanlige — testen var ikke for svak i seg selv, den var svar på et
annet spørsmål enn det som avgjorde om siden virket.

`SidestrukturTests` sjekker nå at hvert åpnet `<style>`, `<head>` og `<html>` også lukkes,
at `<body>` finnes, og at skjemaet faktisk har et e-postfelt og en submit-knapp. Verifisert
ved å gjenskape feilen: da feiler den, med en melding som forklarer at resten av dokumentet
tolkes som innholdet i det uavsluttede elementet.

Det er tredje gang i dag en test måtte skrives om fordi den bekreftet antakelsen min i
stedet for oppførselen.

## 2026-08-23 — Passord-reset: de sju beslutningene, bygget

**907 tester, alle grønne** (21 nye). Punkt 5 og siste i `BESLUTNING_BRUKERE_OG_EPOST.md` §8.

| § | Beslutning | Hvordan |
|---|---|---|
| 6.1 | Delte kontoer utelates | På `er_delt_konto`, aldri utledet fra «har e-post» |
| 6.2 | MFA kan ikke omgås | Flyten logger ingen inn — den ender på innloggingssiden |
| 6.3 | Sesjoner drepes | `_invalidate_all_sessions()` ved fullført reset |
| 6.4 | `must_change_password` nullstilles | Brukeren velger selv; flagget ville krevd to passord på rad |
| 6.5 | Egen rate-limit-bøtte | `reset:epost` 3/10 min og `reset:ip` 20/10 min |
| 6.6 | Kortere token-levetid | **1 time** |
| 6.7 | Ingen kontoenumerering | Identisk svar, verifisert ved sammenligning |

**Token-maskineriet er generalisert, ikke duplisert.** `accounts/signert_lenke.py` er ny og
eier den delte kjernen; `invitasjon.py` og `passord_reset.py` er tynne lag over den. De 27
invitasjonstestene passerte uendret gjennom refaktoreringen — det var hele poenget med å
gjøre den slik.

**Hver bruk har sin egen salt**, og det er testet begge veier: et invitasjonstoken kan ikke
leses som reset, og omvendt. Uten det ville en invitasjon med tre døgns levetid kunnet
brukes der reset har én time.

**§6.7 kan ikke testes på én respons.** «Ingen kontoenumerering» er en påstand om at to
tilfeller ser like ut, så testene sammenligner faktisk `response.content` mellom en adresse
som finnes og en som ikke gjør det. Tre varianter dekkes: ukjent adresse, delt konto, og en
utsending som feilet — den siste fordi en feilmelding også ville vært et svar.

Rate-limit-svaret er med i samme resonnement. Strupes kun eksisterende adresser, er
strupingen i seg selv et signal. Derfor telles forsøket **før** oppslaget.

**`PASSWORD_RESET_TIMEOUT` er fortsatt ikke satt, og det er riktig.** Notatets §6.6 pekte på
den, men innstillingen leses kun av Djangos egen `PasswordResetTokenGenerator`, som vi ikke
bruker. Å sette den ville antydet en kontroll som ikke er i spill.

**E-posten sier eksplisitt at to-faktor fortsatt gjelder**, og at et passord er uendret hvis
man ikke ba om noe. Begge deler for å unngå at en frivillig som får en uventet e-post tror
kontoen er kompromittert eller at MFA er borte.

## 2026-08-23 — Tvungen utlogging, og MFA som gjelder med det samme

**886 tester, alle grønne** (7 nye).

**«Logg ut brukeren» på brukersiden.** Avslutter sesjonene uten å røre kontoen. Til
forskjell fra «frys» kan brukeren logge inn igjen med det samme — poenget er at de må
*gjennom* innloggingen på nytt. `_invalidate_all_sessions()` fantes allerede fra frys og
admin-reset, så jobben var å koble den til en knapp.

**Og det som faktisk løser problemet: å slå på «Krev MFA» avslutter sesjonene automatisk.**

Behovet kom fra en reell situasjon: glemmer admin å sette MFA ved oppretting og retter det
etterpå, har brukeren kanskje sju timer igjen av sesjonen sin. Kravet gjelder da ikke for
den personen før cookien dør av seg selv. **En sikkerhetsinnstilling som venter på en cookie
er valgfri i praksis** — og den som slo den på tror den gjelder.

Kun overgangen av→på utløser det. En ren navneendring på brukersiden skal ikke kaste noen ut
midt i en vakt, og egen test vokter det.

**«Krev MFA» mangler ikke lenger i opprettingsskjemaet.** Den lå bare i redigeringsskjemaet,
så MFA måtte settes i to steg — akkurat det som skapte behovet over. Samme regel som ellers:
kan ikke kombineres med delt konto, håndhevet i valideringen.

Admin kan ikke logge ut seg selv herfra. Ikke fordi det er farlig, men fordi knappen står
blant handlinger man utfører *på noen andre*, og en admin som mister sin egen sesjon midt i
en vaktstart har et større problem enn den som skulle vært logget ut.

## 2026-08-23 — Placeholder-teksten, og en mal ingen brukte

**879 tester, alle grønne** (1 ny). Meldt inn fra mobil etter at invitasjonsflyten ble
testet ende-til-ende: e-posten kom fram, stor forbokstav i brukernavnet ble håndtert,
og passordet ble satt. To ting igjen.

**`::placeholder` var aldri overstyrt i `portal.css`.** «Fornavn Etternavn» og «Valgfritt» i
brukerskjemaet sto praktisk talt i bakgrunnsfargen. `style.css` har hatt regelen hele tiden,
så pasientmodulen var upåvirket — **nok en gang gjaldt en fiks kun den halvparten av
portalen som laster den fila.** Det er tredje gang i dag den delingen biter.

Regelen er lagt i `portal.css` og i de fire frittstående mørke sidene. Egen tone, dimmere
enn `--portal-text-muted`: en placeholder skal ikke kunne forveksles med utfylt innhold.

Passordsiden i invitasjonen var **ikke** rammet — `SettPassordForm` setter ingen
placeholder. Sjekket fordi det var det naturlige neste spørsmålet, ikke fordi det var meldt.

**Testen er utvidet til å dekke pseudo-elementet, ikke bare klassene.** Regelen den
håndhever nå: farger en mal `.form-control` mørkt, må den også overstyre
`.form-control::placeholder`. Feltet ser riktig ut uten den, og bare innholdet forsvinner —
lettere å glemme enn å oppdage.

**Og den fant `templates/base.html`.** 102 linjer som overstyrte `.form-control` uten
placeholder — men ingenting arver fra den, ingenting rendrer den, og eneste henvisning var
en utdatert docstring i `core/tests.py`. Slettet, jf. prosjektets egen regel om at død kode
skal vekk og ikke få en merknad om at den er ubrukt. Docstringen er rettet til å peke på
`base_portal.html`, som er malen testene faktisk treffer.

**Invitasjons-e-posten har fått `Reply-To: support@sanitet.net`.** Avsenderen er en no-reply
på et domene som ikke tar imot post. Uten dette ville et svar fra en frivillig som lurer på
noe forsvunnet i stillhet — og det er nettopp de som trenger å nå fram, siden de akkurat har
fått en lenke de ikke ba om.

## 2026-08-23 — Innlogging bryr seg ikke lenger om store bokstaver

**878 tester, alle grønne** (9 nye). Utløst av en observasjon fra felt: mobiltastatur setter
automatisk stor forbokstav i tekstfelt.

En konto som heter `kari.nordmann` blir `Kari.nordmann` når den skrives på telefon, og
Postgres skiller på det. Brukeren får «feil brukernavn eller passord» — uten noen antydning
om hva som er galt, fordi meldingen med vilje ikke røper hvilket av de to som feilet.

Det rammer nettopp de som **ikke valgte brukernavnet sitt selv**. Brukernavnet velges av
admin, fordi det er nøkkelen i auditloggen og i koblingen til førstehjelper- og
helsepersonellregisteret — en fast konvensjon er det som gjør loggen lesbar. Prisen er at
brukeren må gjette skrivemåten, og den prisen skal ikke betales ved vaktstart.

Tre lag, som alle trengs:

| Lag | Hva |
|---|---|
| `accounts/backends.py` | Oppslag med `iexact` ved innlogging |
| Innloggingsskjemaet | `autocapitalize="none"`, `autocorrect="off"`, `spellcheck="false"` |
| Oppretting | Brukernavn normaliseres til små bokstaver |

Skjema-attributtene er ikke pynt: de stopper problemet før det oppstår, slik at brukeren
ser det de faktisk skrev.

**Tvetydighet slår aldri ut i feil konto.** Finnes det flere kontoer som kun skiller seg på
store bokstaver — mulig i data som er eldre enn normaliseringen — faller oppslaget tilbake
til nøyaktig treff. En bruker som må skrive navnet sitt nøyaktig er et irritasjonsmoment;
feil konto er et sikkerhetsbrudd.

**En følgefeil måtte lukkes i samme slengen.** Rate-limit-bøtta for innlogging brukte
`post:username` på den rå verdien. Med ufølsom innlogging ville «kari», «Kari» og «KARI»
fått hver sin teller mot én og samme konto, og en angriper kunne mangedoblet
forsøksbudsjettet sitt ved å variere store bokstaver. Nøkkelen normaliseres nå på samme måte
som oppslaget. Egen test som feiler hvis den slutter å gjøre det.

## 2026-08-23 — Testsuiten var flaky, og årsaken var en ekte backup per test

Oppdaget mens brukernavn-testene ble skrevet: samme suite ga syv `ERROR` i én kjøring og
null i den neste, med `sqlite3.OperationalError: database table is locked` fra
`backup_scheduler` — i tester som ikke har noe med backup å gjøre.

`_should_run_now()` returnerer True når `last_run_at` er null, og i en fersk testdatabase er
den alltid det. **Første request i enhver test som gikk gjennom middleware-stacken utløste
derfor en ekte backup**, som skrev filer og rader og av og til låste SQLite-tabellen.

Planleggeren tas nå ut av stacken under test, ved siden av den eksisterende
`_RUNNING_TESTS`-bryteren for passord-hashing. Den testes fortsatt direkte i
patients-testene, så ingen dekning går tapt.

Verifisert med tre kjøringer på rad: 878 grønne hver gang, og låsemeldingene borte fra
tester som ikke er backup-tester.

Dette er verdt mer enn de ni nye testene. En flaky suite lærer deg å kjøre om igjen i stedet
for å lese — og hele dagens arbeidsmåte har hvilt på at «alle grønne» faktisk betyr noe.

## 2026-08-23 — Invitasjonsflyt: det midlertidige passordet finnes ikke lenger

**864 tester, alle grønne** (15 nye). Punkt 4 i `BESLUTNING_BRUKERE_OG_EPOST.md` §8.

Admin oppretter kontoen, systemet sender en signert lenke, brukeren setter sitt eget
passord. Gevinsten er ikke bekvemmelighet: **det finnes ingenting å formidle.** Fram til nå
genererte `user_create_view` et 12-tegns passord som ble vist på skjermen én gang og måtte
sendes videre — typisk over en kanal man ikke vil ha passord i.

**Enbruks uten tabell.** Tokenet inneholder et avtrykk av brukerens passord-hash. Setter
brukeren et passord, endres hashen, og avtrykket i lenken slutter å stemme. Ingen tabell å
rydde, ingen jobb som må huske å utløpe noe. Samme mekanisme Djangos egen
`PasswordResetTokenGenerator` bygger på, uttrykt med den `TimestampSigner` kodebasen
allerede bruker til MFA-trust-cookies — med egen salt, så et token herfra aldri kan
gjenbrukes der.

Kontoen opprettes med `set_unusable_password()`. Den kan altså ikke logges inn på før
lenken er brukt, og `must_change_password` settes **ikke** — brukeren velger passordet selv,
og flagget ville tvunget dem gjennom et nytt passordbytte rett etterpå.

**Tre valg avklart 23. aug. 2026:**

| Valg | Avgjørelse | Begrunnelse |
|---|---|---|
| Levetid | 3 døgn | Er den ikke brukt innen da, blir den sannsynligvis ikke det. Admin sender heller en ny |
| Etter passordsetting | Til innloggingssiden | Brukeren møter MFA-oppsettet på vanlig måte, og får bekreftet at innloggingen virker mens de fortsatt har hjelp tilgjengelig |
| Midlertidig passord | Beholdes som reserve | Delte kontoer har ingen innboks, og e-post kan feile midt i en vaktstart |

**Én melding for alle avvisningsgrunner.** Utløpt, brukt, ugyldig signatur eller frosset
konto gir samme side. Å skille dem ville fortalt en tilfeldig besøkende at en konto finnes —
samme resonnement som ligger bak at innlogging sier «feil brukernavn eller passord», aldri
hvilken. For en frivillig organisasjon er medlemskap en personopplysning i seg selv.

**`er_delt_konto` fikk sine to første regler.** Valideringen *nekter* e-post og navn på en
delt konto i stedet for å la dem stå tomme, og MFA kan ikke kreves — en bil-konto deler
enhet mellom folk som kommer og går, så MFA ville betydd én delt TOTP-enhet eller ingen vei
inn. Begge håndheves i skjemaet, ikke bare i grensesnittet, så de ikke kan omgås ved å poste
direkte.

Utelukkelsen skjer på **flagget**, aldri på «har e-post». Utledningen ville slått feil den
dagen noen la inn en kontakt-e-post på en bil-konto, og da er reset-lenken en lateral vei
inn i systemet.

**Feiler utsendingen, blir kontoen stående.** Admin får en advarsel og en «send på nytt»-knapp
på brukersiden, i stedet for en 500-side og tvil om brukeren i det hele tatt ble opprettet.

En eksisterende test måtte endres: oppretting med e-post gir nå 302 i stedet for 200, fordi
personlige kontoer går invitasjonsveien. Testens egentlige poeng — at adressen trimmes — er
uendret, og den sjekker nå i tillegg at invitasjonen faktisk gikk ut.

**Feltene måtte også inn i redigeringsskjemaet.** Første utgave la dem kun i
opprettingsskjemaet, og da var funksjonen halvferdig for alle kontoer som allerede fantes —
altså alle. De kunne ikke få navn i det hele tatt. Begge felter er nå redigerbare, med de
samme kontotype-reglene: en personlig konto kan ikke gjøres delt med e-posten i behold, og
MFA kan ikke slås på i samme lagring som «delt konto».

**Kontoer uten e-post og navn er upåvirket.** Migrasjonen ga alle eksisterende
`fullt_navn=''` og `er_delt_konto=False`, som begge er gyldige. De logger inn med passordet
sitt som før; invitasjon gjelder kun nye kontoer. `EksisterendeKontoerTests` låser det.

**Men admin-kontoen bør få en e-post.** `create_admin` har `--email` som valgfritt, og
oppsettet i CLAUDE.md kaller den uten. Det er uproblematisk i dag, men når passord-reset
bygges blir admin den ene kontoen som ikke kan bruke den — og det finnes ingen annen admin
til å nullstille den. Ført i TODO.

## 2026-08-23 — `fullt_navn` og `er_delt_konto` på `CustomUser`

**849 tester, alle grønne.** Punkt 3 i `BESLUTNING_BRUKERE_OG_EPOST.md` §8. Kun `AddField`.

| Felt | Type | Formål |
|---|---|---|
| `fullt_navn` | `CharField(max_length=150, blank=True, default='')` | Kjenne igjen personen bak et brukernavn som `superman64` |
| `er_delt_konto` | `BooleanField(default=False)` | Bil-innlogginger og andre ikke-personlige kontoer |

Ett fritekstfelt for navnet, ikke for- og etternavn: det håndterer mellomnavn, doble
etternavn og folk som skriver navnet sitt annerledes enn en skjemadesigner forventer.
`CustomUser` arver `AbstractBaseUser`, så `first_name`/`last_name` finnes ikke å arve.

**Ingen håndhevingslogikk i denne leveransen.** `er_delt_konto` er en kontotype med fire
regler — nekter e-post og navn, MFA kan ikke kreves, selvbetjent reset avvises, passord
settes direkte av admin — men de hører til invitasjons- og reset-arbeidet. Migrasjonen
legger til to kolonner. Det er alt den gjør.

Migrasjonen fikk nummer `0010` og inneholder nøyaktig to `AddField`. Det er gevinsten fra
oppryddingen rett før: uten den ville forslaget fått nummer `0009` og dratt
`is_superuser`-endringen med seg.

**Hva som er verifisert, og hva som ikke er det.** `sqlmigrate` lokalt kjører mot SQLite,
som bygger hele tabellen på nytt for en `AddField` — det er en SQLite-egenskap og sier
ingenting om Postgres. Den utskriften er derfor ikke lagt til grunn.

Grunnlaget for at dette regnes som trygt er i stedet formen på endringen: to kolonner med
default, ingen indekser, ingen constraints, ingen datamigrering, og en brukertabell med en
håndfull rader. På Postgres 11+ er `ADD COLUMN` med default en ren metadataoperasjon.
Skulle databasen være eldre, koster en omskriving av den tabellen uansett millisekunder.

## 2026-08-23 — Migrasjonsavvikene var ikke det vi trodde. Begge er ryddet

**849 tester, alle grønne** (1 ny). To no-op-migrasjoner, ingen SQL mot databasen.

Siden Django 5-oppgraderingen har `makemigrations` foreslått to migrasjoner ved hver
kjøring. Begge ble latt ligge, og disiplinen «husk å strippe det Django foreslår» bodde i
en docstring og i hodet til den som deployet. Etter et spørsmål om vi egentlig var sikre på
årsaken, ble prod-tilstanden lest i stedet for antatt.

**Indeksen: databasen hadde rett hele tiden.**

| | Navn |
|---|---|
| Prod (`pg_indexes`) | `audit_audit_created_2c1626_idx` |
| Djangos tilstand etter `0002` | `audit_audit_created_a3c1b8_idx` |
| Modellen | `audit_audit_created_2c1626_idx` |

Databasen og modellen var enige. Kun bokføringen avvek. Og `a3c1b8` er ikke et navn Django
genererer for den indeksen — verken for `['created_at']` (`2c1626`) eller `['-created_at']`
(`6e540c`). De to andre navnene `0002` satte er eksakt riktige. `0002` skrev altså ett navn
som aldri har hatt dekning i modellen.

**Det forklarer nedetiden 13. august presist.** Den gamle `0004` prøvde
`ALTER INDEX audit_audit_created_a3c1b8_idx RENAME TO ...`, og den indeksen fantes ikke —
databasen sto allerede på målnavnet. Migrasjonen var ikke farlig fordi den gjorde noe
drastisk; den var umulig fordi den beskrev en fortid som ikke hadde skjedd.

Rettet med `audit/0004`, en `SeparateDatabaseAndState` med tom `database_operations`.
Release-fasen er det siste stedet man vil ha en betinget kodesti, så den retter bokføringen
og rører ingenting.

**`is_superuser` var aldri farlig.** Eneste forskjell mot `0001_initial` er `help_text`,
som står i Djangos `Field.non_db_attrs`. Da returnerer `_field_should_be_altered()` False
og `alter_field()` returnerer før den rører databasen — uansett backend. `sqlmigrate`
bekrefter: `-- (no-op)`. Den ble strippet ut av `0008` i august fordi indeks-omdøpingen
crash-loopet samme dag. Riktig forsiktighet under en hendelse, men de to var ikke i samme
klasse.

**Å la dem ligge hadde en pris som var i ferd med å forfalle.** Forslaget for `is_superuser`
fikk nummer `0009` — samme nummer som neste ekte migrasjon. Migrasjonen for `fullt_navn` og
`er_delt_konto`, som står som neste oppgave, ville fått nøyaktig det nummeret. Den som kjørte
`makemigrations accounts && git add -A` uten å lese resultatet, ville fått
indeks-omdøpingens tvillingsøster med på lasset i en helt annen leveranse.

**Disiplinen er flyttet fra hukommelse til testsuite.** `MigrasjonerErISyncTests` kjører
`makemigrations --check`. Er det avvik mellom modellene og migrasjonene, feiler den der —
ikke i release-fasen. Verifisert ved å fjerne `audit/0004`: da feiler den, med Djangos eget
forslag i meldingen.

Testens docstring sier eksplisitt at man **ikke** skal kjøre `makemigrations` for å gjøre
den grønn, men lese forslaget og verifisere med `sqlmigrate` først. Det er den vanen som
manglet.

## 2026-08-23 — «Mine pasienter» så mer påslått ut når den var av

**848 tester, alle grønne.** Kun CSS.

Knappen hadde tre tilstander som ikke rangerte riktig:

| Tilstand | Utseende | Kilde |
|---|---|---|
| Av | Lyseblå ramme, lyseblå tekst | Bootstrap `.btn-outline-info` |
| På | Blek blå fyll, mørk turkis tekst | `.active-mine` |
| Av, med markør/fokus på knappen | **Full cyan fyll, svart tekst** | Bootstrap `:hover` |

Den siste er kraftigst av de tre, og den betyr «av». Etter et klikk blir markøren stående
på knappen, så det er nettopp den tilstanden man ser rett etter å ha slått filteret av.

**På touch er det verre.** `:hover` henger igjen etter et trykk til man treffer noe annet,
så på iPhone ble knappen stående fylt — ikke bare et øyeblikk.

Det fantes ingen hover-regel for knappen i det hele tatt; Bootstraps egen tok over.
På-tilstanden trengte ingen fiks — `#btn-board-mine.active-mine` har ID-spesifisitet og
`!important`, og slår Bootstraps hover allerede. Det var kun av-tilstanden som måtte
dempes, til et svakt hint i stedet for en fylling. `:focus` er med i selektoren fordi
fokus blir liggende igjen etter et trykk.

**Filterknappene i lista er urørt.** Der er den sist trykkede alltid den aktive, så den
etterslepende hover-tilstanden treffer en knapp som uansett har sin egen farge fra en
`!important`-regel. Problemet er spesifikt for en av/på-bryter.

Ingen test på dette. En regel-eksisterer-test ville gitt samme falske trygghet som den
gjorde tidligere i dag — invarianten er visuell, og bekreftes i grensesnittet.

## 2026-08-23 — Fargen var riktig i prod hele tiden. Nettleseren fikk den bare aldri

**848 tester, alle grønne** (2 nye). Årsaken til to runder med «ingenting har endret seg».

Begge CSS-fiksene lå ute i produksjon. `curl` mot `/static/css/portal.css` ga det nye
innholdet. Likevel så André den gamle fargen.

`STATICFILES_STORAGE` **ble fjernet i Django 5.1.** Prosjektet kjører 5.2, så linja sto
igjen som død konfigurasjon og ble ignorert — uten sjekk, advarsel eller feilmelding.
Django falt tilbake til `StaticFilesStorage`:

* ingen hashing av filnavn, altså **ingen cache-busting**
* WhiteNoise serverte fila under samme navn med `Cache-Control: public, max-age=14400`
* enhver CSS- eller JS-endring var dermed usynlig for en bruker som hadde besøkt siden,
  i inntil **fire timer** etter deploy

Sporet lå i release-loggen hele tiden: «138 static files copied to '/app/staticfiles'» —
uten det etterfølgende «post-processed», som er manifest-steget. Etter fiksen sier den
«414 post-processed».

Rettet ved å flytte til `STORAGES`-innstillingen, som er den Django 5 faktisk leser.

**Dette har gjeldt hver frontend-endring siden oppgraderingen til Django 5.1.** Ingen av
dem var feil; de nådde bare ikke fram til en nettleser som allerede hadde vært innom.
CSS-arbeidet i sommer, F7-oppdelingen av JS-modulene, dagens tekstfarger — alle har hatt
opptil fire timers forsinkelse ut til brukeren, uten at noe sa fra.

**Testen sjekker oppførsel, ikke innstillingsnavn.** En test på
`settings.STORAGES['staticfiles']['BACKEND']` ville gått god for nøyaktig samme feil neste
gang Django flytter en innstilling: navnet ville stått der, og ingenting ville brukt det.
`StatiskLagringTests` slår i stedet opp lagringen som faktisk er i bruk og krever at den
hasher.

**En stille testsvekkelse fulgte med.** `JsModulLastingTests` sjekket `assertIn` og
`assertNotIn` på `'patients-stats.js'` ordrett. Med hashing heter fila
`patients-stats.<hash>.js`, så den positive testen feilet — synlig og greit. Men den
negative ville **bestått uansett**, også om `read_only` faktisk lastet statistikkbundlen.
Det er hele F7-vernet. Begge er gjort hash-tolerante.

**Fellesnevneren med resten av dagen:** verifiseringen ble gjort på feil sted. `curl` mot
serveren svarte riktig, men beviset som trengtes var hva nettleseren faktisk lastet.

## 2026-08-23 — Hjelpeteksten var fortsatt uleselig: fiksen lå i feil fil

**846 tester, alle grønne.** Rettelse av forrige punkt.

Regelen for `.form-text` ble lagt i `style.css`. **Ingen av de tre meldte sidene laster den
fila.** `style.css` lastes kun av pasientmodulens `index.html`; alt som arver
`base_portal.html` — passordbytte, begge backup-sidene — får `portal.css`. To mørke temaer,
to filer. Regelen er nå lagt i `portal.css` også.

Den i `style.css` blir stående: `index.html` bruker `.form-text` to steder selv.

**Testen hadde samme blindsone som fiksen.** Den hentet markup fra begge malkatalogene, men
sjekket kun `style.css` — og bestod dermed mens sidene var like uleselige som før. At jeg
verifiserte at den feilet uten fiksen hjalp ikke: den fulgte endringen min trofast, den
fulgte bare ikke lastekjeden.

Testen løser nå `{% extends %}` og `{% static %}` for hver mal, og krever overstyringen i
det stilarket malen faktisk kan se — inkludert arvede `<style>`-blokker.

**Da dukket fire til opp**, ingen av dem meldt inn:

| Mal | Klasse |
|---|---|
| `templates/403.html` | `.text-muted` |
| `templates/accounts/mfa_setup.html` | `.text-muted` |
| `templates/accounts/mfa_verify.html` | `.text-muted`, `.form-text` |
| `core/templates/core/backup_admin_restore.html` | `.form-text` |

De tre første er frittstående sider med egen `<style>`-blokk og `background: #0f172a`, uten
noen overstyring. De har vært like uleselige hele tiden — bare på sider man sjelden er på.
Alle er rettet med samme verdi, `#94a3b8`.

**Lærdommen er ikke «skriv en test».** Det gjorde jeg. Den var like avgrenset som fiksen,
fordi jeg utledet den fra endringen i stedet for fra kravet. En test som speiler antakelsen
din bekrefter antakelsen, ikke oppførselen.

Caching var forresten aldri involvert: `CompressedManifestStaticFilesStorage` hasher
filnavnene, så den nye `style.css` ble servert med det samme. Den var bare aldri lastet av
de sidene det gjaldt.

## 2026-08-23 — AHASend-avtalen var aldri en mangel

Kun dokumentasjon. Ingen kodeendring.

TODO har ført «Databehandleravtale med AHASend» som **forfalt** siden 22. august, med den
begrunnelsen at leverandøren er i bruk i produksjon uten avtale på plass. Den premissen
var feil.

AHASends DPA (https://ahasend.com/dpa) krever ingen signatur. Den er inkorporert i Terms
of Use, og teksten er utvetydig: *«By using the Services, Controller accepts this DPA.»*
Avtalen har dermed vært i kraft siden portalen sendte sin første melding. En motsignert
utgave kan bes om, men endrer ikke rettsvirkningen.

Det som faktisk mangler er derfor mindre enn antatt, men ikke ingenting: **dataflyten er
fremdeles ikke dokumentert i A.2**, og C.3 påstår fortsatt «Ingen andre databehandlere er
for øyeblikket i bruk». Det står som eget punkt til dokumentgjennomgangen.

Nøkkelpunktene er notert i TODO for den gjennomgangen. To ting er verdt å trekke fram:

**Underbehandlerne er alle i EØS som standard** — Hetzner (Tyskland/Finland), DA
International Group (Bulgaria) og Blix Solutions (Norge) — og behandlingen skjer
*«primarily within the European Economic Area»*. US-infrastruktur hos Hetzner er
tilgjengelig «upon request». Er den valgt, utløses SCC-sporet og A.2 må beskrive en
tredjelandsoverføring. Det er ett blikk i konsollen, og står som eget punkt.

**Avtalen forbyr sensitive data:** *«Controller agrees not to use the Services to send or
store Sensitive Data.»* Feilvarselet vårt inneholder brukernavn, rolle, klient-IP, URL og
traceback — personopplysninger, men ingen helseopplysninger. Slankingen 22. august fjernet
skjemadata, cookies, settings og lokale variabler, og `core/tests_error_reporting.py`
vokter det.

Den testen er dermed ikke lenger bare en personvernfinesse. Den holder oss innenfor en
kontraktsforpliktelse overfor databehandleren, og bør leses som det neste gang noen
vurderer å utvide varselet.

## 2026-08-23 — To synlige feil: umarkert filter og uleselig hjelpetekst

**846 tester, alle grønne** (3 nye). Ingen backend-endring.

**Hjelpetekst forsvant i bakgrunnen.** Bootstraps `.form-text` er `#6c757d` — laget for
lys bakgrunn — og var aldri overstyrt for portalens mørke tema (`--app-bg: #0f172a`).
`.text-muted` og `.text-secondary` var overstyrt for lenge siden; `.form-text` ble aldri
med. Rammet passordreglene på `/accounts/change-password/` og begge hjelpetekstene på
`/portal-admin/backup/patients/` og `/arkiv/`.

Én regel med samme verdi som `.text-muted`, så all sekundærtekst i portalen har én farge.

Testen er skrevet bredere enn de tre tilfellene: den finner hvilke Bootstrap-klasser for
dempet tekst som faktisk brukes i malene, og krever en overstyring for hver. Neste gang
noen tar i bruk en ny slik klasse, sier suiten fra — i stedet for at noen må lese teksten
for å oppdage det.

**«Mine pasienter» var umarkert på tavla.** `toggleBoardMine()` satte `.active-mine` på
`#btn-board-mine`, men eneste regel var `.filter-btn.active-mine`, og den knappen har
ikke `filter-btn`. Klassen ble satt hver gang og traff aldri noe. Filteret virket —
markeringen var usynlig.

TODO foreslo å legge `filter-btn` på knappen. **Det ble ikke gjort.** Klassen gir
pille-form og 0.78rem skrift, og tavleknappen står ved siden av «Ny pasient» i
verktøylinja, ikke i filterraden. Den ville blitt visuelt ulik naboen — én visuell feil
byttet mot en annen. Selektoren er utvidet i stedet.

**Testen bestod først uten at fiksen var der.** `re.findall` på CSS-en matchet prosaen i
kommentaren jeg nettopp hadde skrevet over regelen, med tom prefiks-gruppe, og
`treffer`-sjekken godtok den. Testen ble rettet til å stripe kommentarer først, og
deretter verifisert ved å reversere fiksen: da feiler den, slik den skal.

Det er verdt å notere som mønster, ikke bare som en rettelse. En test som bare kjøres
etter at fiksen er på plass, forteller ingenting om at den ville fanget feilen.

## 2026-08-23 — F3: dobbeltregistreringen fra 30. april kan ikke skje igjen

**843 tester, alle grønne** (14 nye).

30. april 2026 ble en pasient registrert dobbelt på Grønn sone i prod fordi brukeren
dobbeltklikket før serveren rakk å svare. Delte soner har ingen unik-sjekk, så begge
forespørslene gikk gjennom. `withSubmitGuard()` kom som svar på klikket. F3 dekker
tilfellene guarden ikke ser, fordi de skjer utenfor knappen.

`core/idempotency.py` er ny. Klienten lager en nøkkel når registreringsskjemaet åpnes og
sender den som `idempotency_key`. Serveren reserverer den med `cache.add()` — atomisk;
`get()` etterfulgt av `set()` ville sluppet begge gjennom i nettopp det vinduet mekanismen
finnes for å lukke.

| Tilstand | Svar |
|---|---|
| Nøkkelen ledig | Oppretter, `201` |
| Første forespørsel pågår fortsatt | `409` med `duplikat: true` |
| Nøkkelen brukt opp | Samme pasient, `200` — ikke `201`, for ingenting ble opprettet nå |
| Ingen eller ugyldig nøkkel | Nøyaktig som før F3 |

**Rekkefølgen er hele poenget: reserver etter all validering, aldri før.** Brenner en
avvist innsending nøkkelen, får brukeren som retter feilen «allerede sendt inn» på det
korrigerte forsøket — og kommer ikke videre uten å lukke og åpne skjemaet på nytt. Feiler
`save()` etter reservasjonen, frigis nøkkelen. Begge stiene har egen test.

**`crypto.randomUUID()` alene ville brukket feltbruk.** Den finnes kun i «secure context»,
altså ikke over ren HTTP — og `OFFLINE_MODE` kjører nettopp uten TLS, med vilje. Uten
fallback ville hver registrering i felt kastet `TypeError` på en linje som ser triviell ut.
`crypto.getRandomValues` er tilgjengelig også uten TLS og bærer fallbacken.

**To faner er ikke dekket, og skal ikke være det.** Nøkkelen lages når skjemaet åpnes, så
to faner har hver sin. Det kan være to reelle pasienter, og å slå dem sammen ville vært en
verre feil enn den vi retter. Dekket er dobbeltinnsending fra samme skjema, automatisk
nettverks-retry, og API-klienter som prøver på nytt etter tidsavbrudd.

**409 vises ikke som en feil.** Pasienten blir opprettet uansett, så modalen lukkes og
lista lastes — samme utfall som suksess. En rød boks ville bedt brukeren rette noe som
ikke er galt, og er den typen melding som fører til at noen registrerer på nytt.

Cache-feil betyr «opprett uansett», som i `core/ratelimit.py`. Under vakt er en
dobbeltregistrering et irritasjonsmoment; en pasient som ikke lar seg registrere fordi en
cache er nede er det ikke.

## 2026-08-23 — Verifisert i prod: cron, backup og passordbytte. Og en slettemekanisme som ikke finnes

**829 tester, alle grønne.** Én docstring rettet, ellers bokføring.

Tre punkter bekreftet i produksjon, alle tre kjørt av André der de faktisk hører hjemme:

- **`kollaps_arkiv --dry-run` i containeren:** «Ingen arkiv eldre enn 730 dager som ikke
  allerede er kollapset.» Ventet — arkivene er fra 2026. Første skarpe kjøring 1. september
  har dermed ingenting å slette
- **Manuell backup tatt:** 270 pasienter
- **Passordbytte:** feil nåværende passord gir «Nåværende passord er feil», ikke 429.
  Rettelsen tidligere i dag virker i prod

**270, ikke 273.** Tre av de importerte var testpasienter og ble slettet før backupen.
Det er tallet en framtidig restore skal gi — ser man 273, er man på en eldre backup.

**Og der dukket et dokumentasjonsavvik opp.** For å si hva «270» betyr for backupen måtte
jeg vite om de tre var soft-slettet eller borte. Svaret: borte.
`DELETE /api/patients/<pk>/` er en hard-delete som fjerner raden og resirkulerer
pasientnummeret.

Docstringen på viewet påsto det motsatte — «Oppdater eller slett (soft-delete) en pasient».
Den er rettet, og sier nå eksplisitt at eneste vei tilbake er en backup tatt før slettingen.
Det er ikke en detalj å ta feil av i en docstring over en destruktiv operasjon.

Mer alvorlig: **ingen produksjonskode setter noen gang `Patient.is_active = False`.** Feltet
finnes på modellen og leses av `?include_archived`, men kan bare settes via Django-admin —
og den flaten er av i produksjon siden S1. Soft-delete av pasientdata er altså en mekanisme
som er beskrevet, men som ingenting utløser.

`PERSONVERN_DOKUMENTASJON.md` beskriver den likevel to steder: A.6 kaller `is_active=False`
«logisk slettet / soft-delete», og rettighetstabellen sier «Pasientdata soft-slettes;
permanent sletting på forespørsel». Avviket går i registrertes favør — sletting er *mer*
endelig enn dokumentert, ikke mindre — men dokumentet er art. 30-protokollen og skal
beskrive det som faktisk skjer. **Ikke rettet her**, fordi en endring i det formelle
dokumentet hører sammen med de andre punktene som venter på gjennomgang. Lagt i TODO.

Det er samme sjekk som S7 handlet om, med motsatt fortegn: forrige gang beskrev dokumentet
en sletting som ikke fant sted. Denne gangen beskriver det en bevaring som ikke finner sted.

## 2026-08-23 — Passordbytte kunne stenge en ny bruker ute av portalen

**829 tester, alle grønne** (2 nye). Rettelse av S3, samme dag som den ble deployet.

En gjennomgang av om takene var realistisk satt fant at fire av fem var det, og at ett var
satt på feil hendelse.

`accounts:change-password` lå som dekoratør på hele viewet med `10/5m`, og telte dermed
**hver** POST — også de som ble avvist av skjemavalidering. Django avviser for kort passord,
passord som ligner brukernavnet, vanlige passord og rene tall, i tillegg til bekreftelse som
ikke stemmer.

Det som gjorde dette alvorlig er hva som ligger rundt endepunktet.
`MustChangePasswordMiddleware` sperrer hver eneste URL unntatt passordbytte, utlogging,
innlogging og static. En bruker med `must_change_password=True` kommer altså ikke inn i
portalen i det hele tatt før byttet lykkes. En ny frivillig som fomlet med passordreglene
på mobiltastatur ved vaktstart kunne bruke opp ti forsøk på fem minutter, og var da stengt
ute av **hele portalen** til vinduet løp ut.

Og bøtta beskyttet ingenting i den tilstanden: `old_password` sjekkes kun når
`must_change_password` er `False`. I tvungen-bytte-stien finnes det ikke noe gammelt passord
å gjette.

Det er samme feil som N4, i ny drakt — **telleren telte feil hendelse.** Der var det MFA-
forsøk som havnet i samme bøtte fordi nøkkelen slo opp et felt skjemaet ikke sendte. Her var
det skjemafeil som ble talt som om de var angrep.

**Fiksen:** tellingen er flyttet fra dekoratøren inn i viewet, til punktet der gjettet
allerede er slått fast som feil. Bøtta heter nå `password:old-guess` — navnet sier hvilken
hendelse den teller, ikke hvilket endepunkt den henger på. Konsekvensene:

- Tvungent passordbytte rører aldri bøtta. En ny bruker kan ikke låse seg ute
- Et **riktig** nåværende passord koster ikke kvote
- Avviste skjemaer koster ikke kvote
- Ti feilede gjett på nåværende passord gir fortsatt 429, som før

To nye tester dekker nettopp de to første punktene, siden det er dem en refaktorering vil
miste først.

**De fire andre takene ble stående.** Målt mot hva appen faktisk gjør: `doAutoRefresh`
kaller `loadStats` kun mens statistikkfanen er aktiv, altså rundt 2/min mot en grense på 30.
`PUT`/`DELETE` mot en pasient har to kallsteder, begge modal-lagringer bak
`withSubmitGuard`. Pasientregistrering krever fem utfylte felt, så 1–3/min er realistisk
peak mot en grense på 60. Marginene er store med vilje: takene skal skille et menneske fra
en løkke, ikke bremse noen.

**Én luke notert, ikke lukket:** `/api/innstillinger/arkiv/<pk>/full-stats/` kjører samme
tunge beregning som `/api/full-stats/`, men fikk ingen bøtte. Admin-only og uten
auto-refresh, så eksponeringen er lav. Ligger i TODO.

## 2026-08-23 — S3: rate-limiting utover innlogging, og en kommentar som løy

**812 tester, alle grønne** (15 nye).

Innlogging har hatt rate-limiting siden N4. Alt annet var ubeskyttet: en
`read_write`-bruker — eller en stjålet sesjonscookie — kunne opprette pasienter i løkke så
fort serveren rakk å svare, og en admin kunne hente 5000 auditrader per kall uten grense på
antall kall.

`core/ratelimit.py` er ny og eier mønsteret. Grensene:

| Endepunkt | Metode | Grense | Bøtte |
|---|---|---|---|
| `POST /pasienter/api/patients/` | POST | 60/min | `patients:create` |
| `PUT`/`DELETE /pasienter/api/patients/<pk>/` | PUT, DELETE | 120/min | `patients:detail-write` |
| `GET /pasienter/api/full-stats/` | GET | 30/min | `patients:full-stats` |
| `POST /accounts/change-password/` | POST | 10/5 min | `accounts:change-password` |

> Bøtta over ble omdøpt til `password:old-guess` samme dag, og teller nå kun feilede
> gjett — se rettelsen øverst i denne fila.
| `GET /portal-admin/auditlog/eksport.csv` | GET | 10/min | `audit:csv-export` |

Nøkkelen er per bruker, og gruppen oppgis eksplisitt på hvert kallsted. Det er lærdommen
fra N4 gjort til regel: der havnet alle MFA-forsøk fra alle brukere i samme bøtte, og ved
vaktstart fikk bruker nummer elleve 429 uten at noe var galt med kontoen. Utledes gruppen
av funksjonsnavnet, kan en flytting mellom moduler slå to bøtter sammen igjen — stille.

Pasient-redigering sto ikke i S3s opprinnelige liste. Den er tatt med fordi akseptansen
handler om skrivelast mot databasen, og `PUT` er skrivelast. Bøtta er romsligere enn ved
opprettelse: obs-tider stemples, sonen endres, pasienten skrives ut — redigering skjer
oftere enn registrering.

**Kommentaren i `settings.py` løy, og det betydde noe.** Den påsto at django-ratelimit
«failopener av seg selv ved cache-feil». Pakken gjør det motsatte, i begge retninger:

- `RATELIMIT_FAIL_OPEN` er `False` som default. Svarer cachen uten verdi, settes
  `should_limit=True` — altså 429 på **alt**.
- Kaster cachen i stedet — som `cache.add()` gjør mot en død Redis — fanges det ikke.
  `socket.gaierror` er eneste unntak pakken tar. Endepunktet ville svart 500.

Uten S3 gjaldt dette bare innlogging, der det er ubehagelig. Med S3 ville det gjeldt
pasientregistrering under vakt, der det er uakseptabelt. Begge stier er nå lukket: flagget
settes `True`, og `er_rate_limited` fanger exceptions og slipper forespørselen gjennom med
en `WARNING` i loggen.

Prioriteringen er den samme som F3 formulerer for idempotens, og som `stats_cache.py`
allerede gjør for statistikken: **bedre en manglende bremse enn en pasient som ikke kan
registreres.** Innlogging mister ikke noe reelt på dette — kontolåsingen (5 feilede forsøk
= 15 min) ligger i databasen og er uavhengig av cachen. `accounts/views.py::_er_rate_limited`
delegerer nå til kjernen, så den stien får samme håndtering.

**429 måtte bli synlig, ellers var strupingen farligere enn problemet.** Skjemaet i
`patients-forms.js` håndterte kun 400. En strupet registrering ville derfor sett ut som
ingenting: modalen ble stående åpen, uten feilmelding, mens pasienten ikke var lagret.
Både registrerings- og redigeringsskjemaet viser nå serverens tekst ved 429.
Statistikkfanen leste tidligere svarkroppen uansett status utenom 403; den lar nå forrige
visning stå i stedet for å rendre tomme grafer over en feilmelding. To nye node-tester
kjører `_saveNewImpl()` med stubbet DOM og verifiserer begge deler — ingen grep etter
kodelinjer, jf. N9.

**Grensene er bare så delte som cachen er.** Appen kjører i dag én gunicorn-worker med
fire tråder mot LocMemCache, så telleren er felles for all trafikk. Settes `WEB_WORKERS`
høyere uten `REDIS_URL`, får hver worker sin egen teller og den reelle grensen blir
grensen ganger antall workers; `--max-requests 1000` resirkulerer i tillegg workeren
jevnlig og nullstiller tellerne. Begge avvikene går samme vei — bremsen blir mildere enn
konfigurert, aldri strengere. Det er den ufarlige retningen.

Nød-bryteren `RATELIMIT_ENABLE=False` slår av alt uten deploy, som før.

## 2026-08-23 — Cron er bevist i drift: 3 varsler faktisk slettet

Kun dokumentasjon. Ingen kodeendring.

`purge_old_logs` fyrte som Railway Cron natt til søndag 23. august, og slettet de 3
varslene fra 12. mai. Cron-tjenestens logg:

```
Starting Container
Slettet 0 login-events eldre enn 730 dager.
Slettet 0 audit-logger eldre enn 730 dager.
Slettet 3 varsler eldre enn 30 dager.
```

**Hvorfor dette er beviset og tørrkjøringen ikke var det.** Teksten er den skarpe
varianten — en tørrkjøring hadde skrevet «Ville slettet», med `[Tørrkjøring]` foran.
Tallet 3 er nøyaktig det tørrkjøringen dagen før identifiserte. Og den kjørte i
containeren, mot produksjonsdatabasen, utløst av cron. Alle tre leddene som kunne
sviktet stille — at cron fyrer, at `startCommand` treffer riktig kommando i stedet for
gunicorn, og at slettingen rammer de riktige radene — er dermed dekket av samme
observasjon.

Det er forskjellen S7 handlet om: en kontroll som står dokumentert er ikke det samme som
en kontroll som finner sted.

**`PERSONVERN_DOKUMENTASJON.md` v1.6.** Ny datert merknad under retensjonstabellen i A.9.
Ingen lagringstid er endret — det som er endret er grunnlaget for å påstå at de
etterleves.

**Sjekklistepunktet i C.4 er bevisst ikke krysset av.** TODO pekte på det, men C.4 er
malen for *årlig* revisjon. Krysses den av nå, står avkryssingen der i 2027 også og
påstår en verifisering som ikke er gjort det året. En datert merknad ved A.9, der
lagringstidene faktisk står, sier det samme uten å råtne.

**`kollaps_arkiv` er ikke verifisert på samme måte**, og skal ikke regnes som det. Den
har ennå ingenting å kollapse — arkivene er fra 2026, grensen er 24 måneder — så en
kjøring beviser foreløpig bare at kommandoen starter. Første skarpe kjøring er 1.
september, og `--dry-run` bør kjøres manuelt før den.

## 2026-08-22 — Portalen står i `production`, med cron. Dokumentasjonen i takt

Kun dokumentasjon og Railway-oppsett. **797 tester, alle grønne.** Ingen kodeendring.

**Portalen ble ikke flyttet.** Det opprinnelige `production`-miljøet — den gamle
Pasientregistreringsappen — er slettet, og portalens miljø døpt om fra `staging` til
`production`. Alternativet, å faktisk flytte portalen, ville betydd å migrere hele
produksjonsdatabasen mellom to Postgres-instanser: 273 pasienter, brukerkontoer,
MFA-hemmeligheter, auditspor og arkiver. Samme klasse operasjon som dataimporten, men uten
`--dry-run` som sikkerhetsnett — for å vinne et navn.

Miljøet har nå tre tjenester som alle bygger fra `Animax1/sanitetsportalen`:

| Tjeneste | Start Command | Plan |
|---|---|---|
| `web` | (Procfile) | — |
| `purge_old_logs` | `python manage.py purge_old_logs` | `0 0 * * SUN` |
| `kollaps_arkiv` | `python manage.py kollaps_arkiv` | `0 4 1 * *` |

**To feil i cron-oppsettet, begge stille:**

- **`startCommand` manglet på begge.** Uten den arver tjenesten `Procfile`-ens `web:`-linje
  og starter gunicorn i stedet for kommandoen. Jobben ville gjort ingenting, uten å feile —
  og med `restartPolicy: NEVER` bare stått til Railway rev den ned
- **`kollaps_arkiv` hadde `OFFLINE_MODE=True`.** `settings.py` kaster `ImproperlyConfigured`
  ved oppstart når den står på Railway, med vilje. Tjenesten ville krasjet før Django lastet,
  én gang i måneden, uten at noen merket det

Sperren mot `OFFLINE_MODE` ble skrevet for web-tjenesten, men fanget dette like godt.

Begge kommandoene tørrkjørt mot produksjonsdatabasen: `kollaps_arkiv` har ingenting å
kollapse (arkivene er fra 2026, grensen er 730 dager), `purge_old_logs` fant 3 varsler eldre
enn 30 dager.

**Verifiseringen er ikke ferdig, og det står som eget punkt.** En tørrkjøring beviser at
kommandoen kjører, ikke at cron utløser den. `purge_old_logs` fyrer førstkommende søndag og
skal slette varsel `id` 1, 2 og 3 fra 12. mai. Er de borte etterpå, er mekanismen bevist —
og **først da** kan sjekklistepunktet i `PERSONVERN_DOKUMENTASJON.md` linje 724 krysses av.
Å krysse av på grunnlag av en tørrkjøring ville vært nøyaktig den dokumenterte-men-ikke-reelle
kontrollen S7 handlet om.

**Dokumentasjonen sier nå at e-post går over HTTP-API, ikke SMTP.**
`BESLUTNING_BRUKERE_OG_EPOST.md` var bygget rundt SMTP fra ende til annen: den påsto at
`EMAIL_HOST` ikke var satt i produksjon, at all e-post havnet i Railway-loggen, og listet
fire SMTP-leverandører å velge mellom. Seksjon 1–3 er skrevet om — transporten er AHASends
HTTP-API v2, leverandørvalget er tatt, og kravet til en framtidig erstatter er at den har et
HTTP-API, ikke bare SMTP.

**Databehandleren er nå en forfalt mangel, ikke et framtidig valg.** Notatet behandlet
e-postleverandøren som noe som skulle avklares før invitasjonsflyten bygges. Men AHASend er
i bruk *allerede*, til feilvarsling, og er dermed databehandler i dag. Varselet inneholder
brukernavn, rolle, klient-IP, URL og traceback — ingen kliniske opplysninger, men
personopplysninger — og de går gjennom to tredjeparter: AHASend ved utsending og Google som
mottakerens innboks. Begge skal inn i A.2.

**Den gamle appens database er slettet.** Den manuelle backupen i portalen er eneste
gjenopprettingspunkt for de 273 importerte pasientene.

## 2026-08-22 — Dataimport fra gammel prod: 273 pasienter inn i portalen

Årets pasientdata er hentet fra den gamle Pasientregistreringsappen og ligger nå i
portalen. **797 tester, alle grønne** (1 ny).

**Resultatet, verifisert mot kilden felt for felt:**

| Kontroll | Portal | Gammel prod |
|---|---|---|
| Pasienter 2026 | 273 | 273 |
| Med førstehjelper | 216 | 216 |
| Med helsepersonell | 108 | 108 |
| Grønn / Gul / Rød | 163 / 91 / 19 | 163 / 91 / 19 |
| `journal=Ja` | 48 | 48 |
| `utskrevet` utfylt | 270 | 270 |
| `lege` utfylt | 29 | 29 |

Triage-fordelingen er den som betyr noe: statistikken er beregnet, ikke importert, så like
tall der betyr at grunnlaget faktisk er identisk. 273 `IMPORT`-rader i auditloggen, én per
pasient. `enja` og `morten` fantes allerede i førstehjelperregisteret og ble gjenbrukt, ikke
duplisert — registrene endte på 15 og 9.

### `import_offline_data` var ødelagt mot Postgres

Tørrkjøringen stoppet med `DataError: value too long for type character varying(10)`.
Kommandoen skrev `action='imported_offline'` til `AuditLog.action`, som er `max_length=10`.
Verdien er 16 tegn.

**Hele testsuiten var grønn.** Testene kjører på SQLite, som ikke håndhever varchar-lengde;
Postgres gjør det. `patients/tests_offline.py` filtrerte til og med på
`action='imported_offline'` og bekreftet dermed feilen som riktig oppførsel.

Verdien er nå `IMPORT` — seks tegn, som får plass i kolonnen som den er.

**Den står bevisst ikke i `AuditLog.ACTION_CHOICES`.** Å legge den til krever en migrasjon i
`audit`-appen, og `makemigrations` viser hvorfor det ikke er greit:

```
~ Rename index audit_audit_created_a3c1b8_idx on auditlog
                        to audit_audit_created_2c1626_idx
~ Alter field action on auditlog
```

Indeks-omdøpingen er den som tok ned produksjon i 30 minutter 13. august, og indeksen finnes
ikke i Postgres under det navnet. Enhver migrasjon i `audit` drar den med seg. Choices
håndheves ikke av databasen og `objects.create()` validerer ikke mot dem, så `IMPORT`
virker. Den kan normaliseres den dagen noen tar indeks-avviket bevisst — det er en egen jobb
med egne avveininger.

**Ny test, backend-uavhengig:** `test_import_offline_data_audit_action_passer_i_kolonnen`
leser `max_length` fra modellen og sammenligner med verdiene som faktisk skrives. Verifisert
ved å gjeninnføre feilen med vilje:

```
AssertionError: 16 not less than or equal to 10 : action='imported_offline'
er 16 tegn, men kolonnen tar 10. Dette feiler mot Postgres, ikke mot SQLite.
```

Det var hullet som lot feilen leve: en grense definert i modellen, håndhevet av én database
og ignorert av den andre.

### Fire feil i prosedyredokumentet

`docs/DATAIMPORT_FRA_GAMMEL_PROD.md` ble skrevet 14. august og hadde drevet:

- **`DATABASE_URL` når ikke fram utenfra.** Den peker på `postgres.railway.internal`, som
  kun er nåbar innenfra Railways nettverk. Begge miljøene har en `DATABASE_PUBLIC_URL` over
  TCP-proxy, men det sto ingen steder
- **`PYTHONUTF8=1` mangler.** Uten den skriver `dumpdata -o` fila i Windows' lokale kodesett,
  ikke UTF-8, og neste steg feiler med `UnicodeDecodeError ... byte 0xf8` — som er `ø`.
  Fanget på første forsøk; 468 norske tegn ville blitt ødelagt
- **Rådet om å øve mot staging er tomt.** Dokumentet ble skrevet da portalen sto i staging og
  produksjon var den gamle appen. Nå betjener staging-miljøet `portal.sanitet.net`.
  `--dry-run` er hele sikkerhetsnettet
- **`action`-verdien** var oppgitt som `imported_offline` to steder

### Verdt å vite for neste import

Den gamle appens `migrate` sår ti generiske `Behandler 1`–`Behandler 10`-rader, så
SQLite-fila får 25 behandlere der prod har 15. Ingen pasient peker på dem, og importen leser
gjennom en join — derfor kom kun de 14 faktisk brukte navnene med. Verdt å vite hvis noen
teller rader og lurer.

Importen matcher navn **case-sensitivt**, mens `0009_link_behandlere_to_users` matchet
`iexact`. Her var alt små bokstaver, men et avvik i store/små bokstaver ville gitt to rader
med pasientene fordelt mellom seg — uten feilmelding.

## 2026-08-22 — `verifiser_feilvarsel` sier hvor den kjører

**796 tester, alle grønne** (2 nye).

Tre ganger på én dag traff en variabel eller en test feil miljø: API-nøklene ble satt i
`production` (den gamle appen) i stedet for `staging` (portalen), to ganger, og
verifiseringen ble til slutt kjørt lokalt i PowerShell i stedet for i containeren — fordi
SSH-økta var avsluttet uten at det var synlig i utskriften.

Ingen av gangene var det uoppmerksomhet. Miljønavnene er arvet og inverterte, og
kommandoens utskrift så helt lik ut uansett hvor den kjørte. Et lokalt «grønt» og et
container-«grønt» betyr helt forskjellige ting: lokalt er utgående SMTP åpent, i containeren
er det sperret.

Kommandoen begynner nå med å si hvor den er:

```
Kjorer i Railway: miljo "staging", tjeneste "web", vert 57329c3660a9
   Svaret under gjelder dette miljoet. Merk at miljonavnene er arvet:
   portalen kjorer i "staging", mens "production" er den gamle appen.
```

Kjørt lokalt sier den i stedet, med advarselsfarge, at svaret **ikke** gjelder produksjon,
og hvordan man kjører den riktig. Testene krever begge deler — inkludert at
container-varianten nevner inverteringen, siden en utskrift som bare sier «staging» like
gjerne kan feilleses som «ikke produksjon».

## 2026-08-22 — Railway sperrer SMTP: e-post går nå over HTTPS

**794 tester, alle grønne** (21 nye).

Feilvarslingen så ferdig ut, men virket ikke i produksjon. Den ble testet med
`railway run`, som henter Railways miljøvariabler og kjører koden **på utviklingsmaskinen**.
Først da kommandoen ble kjørt inne i containeren, via `railway ssh`, kom sannheten fram:
den hang i `sock.connect()`.

**Målt fra containeren:**

| Port | |
|---|---|
| 587, 2525, 465, 25 | **alle stengt** |
| 443 mot `send.ahasend.com` | åpen |
| 443 mot `1.1.1.1` (kontroll) | åpen |

Utgående trafikk virker. Railway sperrer SMTP spesifikt — en vanlig plattformpolicy mot
spam-misbruk. **Å bytte SMTP-leverandør ville truffet samme vegg.**

**`core/mail_backends.py`** sender derfor over AHASends HTTP-API i stedet:
`POST https://api.ahasend.com/v2/accounts/{konto}/messages`. Backenden bytter kun
*transporten* — `mail_admins()`, `AdminEmailHandler`, `send_mail()` og den slanke
feilrapporten fungerer uendret.

Valg som er tatt bevisst:

- **`urllib` fra standardbiblioteket, ikke `requests`.** Én HTTP-POST rettferdiggjør ikke en
  ny avhengighet, og dette er stien som skal virke når alt annet feiler
- **`fail_silently` respekteres strengt** — `AdminEmailHandler` kaller alltid slik. Men
  feilen logges alltid: en stille feil uten loggspor er umulig å feilsøke
- **`Idempotency-Key` per melding**, siden dempingsfilteret er per prosess og to
  Gunicorn-arbeidere kan sende samme varsel
- **Ikke støttet:** vedlegg, egendefinerte headere, `cc`/`bcc` som egne felter. Portalen
  sender kun til `ADMINS`. Et bevisst utvidelsespunkt, ikke en glemt detalj

Backend velges etter hva som er konfigurert: HTTP-API-et først fordi det er det eneste som
kommer ut av containeren, så SMTP (som virker lokalt og i offline-modus), så konsoll.

### `EMAIL_TIMEOUT` — den viktigste enkeltendringen

Hendelsen avslørte noe verre enn manglende tilkobling. `EMAIL_TIMEOUT` var ikke satt, og
Djangos standard er `None`. Da arver `smtplib` Pythons globale socket-timeout, som også er
`None`. Tracebacken fra containeren viste det presist:

```
smtplib.py:320   socket.create_connection((host, port), timeout, ...)
socket.py:853    sock.connect(sa)      <- sto her til Ctrl+C
```

`AdminEmailHandler` sender **synkront, i requestens egen tråd**. Gunicorn kjører med fire
tråder per worker. Fire uhåndterte feil mens SMTP henger, og hele worker-poolen er låst —
appen slutter å svare for alle, også de som ikke opplevde noen feil. En feil som skulle gitt
én e-post ville i stedet tatt ned portalen, og det ville skjedd under vakt.

`EMAIL_TIMEOUT = 10` er nå satt, og en test krever at den er ≤ 30. Dempingsfilteret
begrenser skaden ytterligere, men det er tidsgrensen som gjør varslingen ufarlig for driften.

### `verifiser_feilvarsel` ga nesten falsk grønt

Steg 2 åpnet en SMTP-forbindelse. For HTTP-backenden er `open()` en arvet no-op fra
`BaseEmailBackend` — kommandoen ville meldt «Åpnet og autentisert» uten å ha kontaktet noe.
Falsk grønt på nøyaktig det spørsmålet kommandoen finnes for å svare på.

Steg 2 prøver nå den transporten som faktisk er i bruk: SMTP-forbindelse for SMTP, en ekte
sendt melding for HTTP-API-et — det eneste som prøver DNS, TLS, autentisering og om
avsenderdomenet er godkjent. Backender uten transport (konsoll, locmem) hopper over steget
og sier fra at de gjør det, i stedet for å rapportere suksess.

Kommandoen har også fått `--timeout` (standard 15 s) og en feilmelding som skiller
**droppet** fra **avvist** — det er den forskjellen som leder deg mot brannmur i stedet for
at du bruker en time på å sjekke passordet. En test krever at `EMAIL_HOST_PASSWORD` ikke
nevnes i tidsavbrudds-meldingen.

## 2026-08-22 — Feilvarselet slanket: 14 810 → 673 tegn

**769 tester, alle grønne** (14 nye).

Spørsmålet som utløste dette: *er det nødvendig å sende settings?* Nei. Django gjenbruker
feilsidens mal (`technical_500.txt`) til varslings-e-posten, og den malen er skrevet for en
utvikler med DEBUG på som trenger å se alt. Den dumper hele `Settings:`-tabellen og hele
`META:`-tabellen. I en e-post er det rundt 13 av 14 KB støy — og et ganske detaljert bilde
av systemet som forlot serveren hver gang noe kræsjet.

`core/error_reporting.py` erstatter den med det varselet faktisk trenger: hva som skjedde,
hvor, hvem det traff, og når. Målt på samme feil: **14 810 → 673 tegn, altså 4 %.**

**Fravalgene er sikkerhetsegenskapen**, og testene vokter dem — innhold er lett å se at
stemmer, mens en gjeninnført Settings-dump ville gått upåaktet hen:

| Utelatt | Hvorfor |
|---|---|
| `Settings:` | Hemmelighetene var maskert, men resten er en konfigurasjonsoversikt varselet ikke trenger |
| `META:` | Hele WSGI-miljøet. Vi plukker ut IP, nettleser og referer |
| `GET`/`POST`/`COOKIES` | **Det viktigste.** En POST mot pasient-API-et har kliniske opplysninger i kroppen |
| Lokale variabler | Var aldri med i tekstmalen, og legges ikke til. En stackramme i en pasientvisning har pasientdata i minnet |

Rapportøren settes via `reporter_class` på selve handleren, ikke via
`DEFAULT_EXCEPTION_REPORTER`. Feilsiden i DEBUG beholder dermed full detalj — det er kun
e-posten som slankes. Ved enhver feil i rapportøren selv faller den tilbake til Djangos
egen: en loggehandler som kaster, tar med seg varslingen den skulle levere.

**`include_html=False` har fått en kommentar som sier hvorfor den står der.** Det er ikke
en formateringssak: `technical_500.html` tar med lokale variabler for hver stackramme.
Skal den noen gang settes til `True`, må personvernkonsekvensen vurderes på nytt først.

**Verifisert med ekte produksjonsverdier** at ingenting lekker: `SECRET_KEY`,
`EMAIL_HOST_PASSWORD`, databasepassord, databasevert, POST-data og sesjonscookie er alle
fraværende i rapporten. Djangos egen maskering (`API|AUTH|TOKEN|KEY|SECRET|PASS|SIGNATURE|HTTP_COOKIE`)
dekket hemmelighetene allerede, men databaseverten slapp gjennom fordi `DATABASES` og
`HOST` ikke matcher mønsteret. Nå er hele seksjonen borte, så spørsmålet er uaktuelt.

**Et hull notert i TODO:** personverndokumentasjonen omtaler ikke e-postvarsling i det hele
tatt. Det er en dataflyt til to tredjeparter — AHASend og Google — som hører hjemme i A.2.
Varselet inneholder brukernavn, rolle, klient-IP, URL og traceback; ingen kliniske
opplysninger.

## 2026-08-22 — E-postvarsling verifisert, og en kommando som gjør det etterprøvbart

**755 tester, alle grønne** (5 nye).

E-postvarslingen ved uhåndterte feil (F1) har stått ferdig i koden siden 13. august, men
aldri vært bekreftet mot en faktisk SMTP-tjener. Nå er den det: AHASend via
`send.ahasend.com:587`, med `noreply@mail.sanitet.net` som avsender.

**`python manage.py verifiser_feilvarsel`** er lagt til fordi denne stien er stille når
den er ødelagt. Djangos `AdminEmailHandler` kaller `mail_admins(..., fail_silently=True)`,
og en loggehandler som feiler river aldri ned requesten som utløste den. Det er riktig
oppførsel — men konsekvensen er at feil SMTP-oppsett ser nøyaktig ut som et system uten
feil. Tom `ADMINS` er verre: da har varselet null mottakere, og ingenting protesterer.

Kommandoen skiller de tre tingene som kan svikte, og sier hvilken det er:

1. **Oppsettet** — backend, mottakere, avsender. Tom `ADMINS` gir `CommandError`, ikke et
   grønt svar på et spørsmål ingen stilte
2. **SMTP-forbindelsen** — åpnes eksplisitt med `fail_silently=False`, så feil legitimasjon
   eller avvist avsenderadresse gir et unntak i stedet for stillhet
3. **Varslingskjeden** — en ekte exception logges til `django.request` med `exc_info` og et
   syntetisk request-objekt, altså slik Django selv gjør det ved en uhåndtert feil. Den går
   gjennom dempingsfilteret og `AdminEmailHandler`

Steg 2 er det som roper. Steg 3 beviser at kjeden er koblet, men kan ikke rapportere
leveranse — handleren svelger sine egne feil. Derfor kjøres begge: steg 2 utelukker at
steg 3 feilet stille. `--dry-run` kontrollerer oppsettet uten å sende.

Verifisert mot Railway-variablene: SMTP åpnet og autentisert, og
`django.request` har `['StreamHandler', 'AdminEmailHandler']`.

`audit/tests_verifiser_feilvarsel.py` vokter at kommandoen selv ikke er stille når noe er
galt — en verifiseringskommando som feiler stille er verre enn ingen kommando. Fila heter
`verifiser_feilvarsel.py`, ikke `test_*`, nettopp for at testoppdageren ikke skal plukke
opp en management-kommando som testmodul.

**Et lokalt funn underveis, uten betydning for drift:** første forsøk feilet med
`CERTIFICATE_VERIFY_FAILED: certificate has expired`. Sertifikatet til AHASend er gyldig
(Let's Encrypt, 1. aug → 30. okt 2026, `openssl` verifiserer kjeden med kode 0). Det er
Windows-sertifikatlageret på utviklingsmaskinen som har et utløpt sertifikat i
Let's Encrypt-stien — `letsencrypt.org` feiler også, mens `pypi.org` går fint.
Railway-containeren har sin egen, oppdaterte `ca-certificates` og er ikke berørt.

## 2026-08-22 — `docs/` konsolidert: TODO er arbeidslista, tre dokumenter slettet

Kun dokumentasjon. **750 tester, alle grønne.** Ingen brutte relative lenker i repoet.

`docs/` er nede fra ti aktive dokumenter til åtte — tre slettet, ett nytt.
`FORBEDRINGER_2026-08.md` (1836 linjer),
`GDPR_TILTAKSPLAN.md` (260) og `docs/README.md` (56) er slettet. Alt som fortsatt er åpent
står nå i `TODO.md`, med begrunnelsen med seg — ikke som peker til et dokument.

**Hvorfor sletting og ikke arkivering.** Backlog-dokumentet var 23 av 28 punkter ferdige.
De 23 er allerede fortalt i denne fila under 13.–22. august, med mer detalj enn matrisen
hadde. Å beholde dokumentet ville gitt to steder å lese status fra, og de ville drevet fra
hverandre. GDPR-tiltaksplanen sa det samme om seg selv i toppteksten: «Når alle faser er
ferdige, har dokumentet gjort jobben sin og kan slettes.» Den hadde ett åpent punkt igjen.
`docs/README.md` var en indeks som kun fantes fordi det var mange filer.

**Statistikk-utvidelsen (F6) ble reddet ut, ikke komprimert.** 96 linjer med tilgangsmodell,
faseinndeling, statistiske metoder (Dunn post-hoc, Wilson-KI, Cramér's V) og fem ubesvarte
spørsmål lar seg ikke koke ned til en kulepunkt-linje uten at det som gjør den brukbar
forsvinner. Den ligger nå som `docs/BESLUTNING_STATISTIKK.md`, etter samme mønster som de
to andre beslutningsnotatene. Den er en plan som venter på avgjørelser, ikke et punkt på
en liste — samme skille som avgjorde at runbook, deploy-guide og dataimport beholdes.

**F8 (PgBouncer) står ikke lenger som oppgave.** Den var markert «bevisst utsatt», ikke
åpen. Begrunnelsen — 16 forbindelser mot en grense på ~100, og `conn_max_age=600` som
demper ytterligere — er beholdt i TODO som en note om *hvorfor det ikke er en oppgave*, med
terskelen for å ta den opp igjen (`WEB_WORKERS` ≥ 4).

**En løs tråd ble funnet under flyttingen:** F7 er merket ferdig, men første-paint på mobil
4G ble aldri målt. `read_only` laster 49 % av admin-bundlen, og gevinsten i faktisk
oppstartstid er udokumentert. Den står nå som eget punkt i stedet for som en parentes under
et avkrysset punkt.

**Migrasjonssekvensen skrevet ned.** Railway-prosjektet har to miljøer, og navnene er
arvet fra forgjengeren: `production` er den *gamle* Pasientregistreringsappen
(`pasientregistrering.up.railway.app`), mens `staging` er Sanitetsportalen — det er den
som betjener `portal.sanitet.net`. Portalen skal over på `production` når dataimporten er
kjørt, og `purge_old_logs`- og `kollaps_arkiv`-jobbene kobles på der. Rekkefølgen står nå
i TODO fordi den ikke kan tas i vilkårlig orden: `production` må stå urørt til importen er
ferdig, siden det er der årets pasientdata ligger.

Konsekvensen i mellomtiden er notert samme sted: portalens miljø har ingen cron-tjeneste,
så verken audit-logger, innloggingshendelser eller varsler slettes ennå.
`PERSONVERN_DOKUMENTASJON.md` A.9 oppgir 730/30 dager med «`purge_old_logs` via Railway
Cron» som mekanisme — den påstanden blir sann etter migrasjonen, ikke før, og
sjekklistepunktet i samme dokument kan krysses av da. Backloggens F2 ble avkrysset som
«allerede på plass»; det stemte for den gamle appen, ikke for portalen.

**Ni referanser til de slettede filene rettet** i `accounts/tests_user_admin.py`,
`patients/js_test_utils.py`, `PERSONVERN_DOKUMENTASJON.md`, `RUNBOOK_VAKT.md`,
`TEKNISK_DOKUMENTASJON.md` og de to arkivindeksene. To av dem avslørte utdaterte påstander:
den tekniske dokumentasjonen omtalte arkiv-kollaps som «planlagt endring» selv om GDPR
fase 3.1 leverte den i august, og personverndokumentasjonen pekte på et dokument som ikke
lenger fantes for et avvik som fortsatt er reelt.

**`.env.example` pekte på SendGrid** og `sanitetsportalen@dittdomene.no`. Prod bruker
AHASend med `mail.sanitet.net` som avsenderdomene. Kommentaren forklarer nå hvorfor
`DEFAULT_FROM_EMAIL` må ligge på et autorisert domene: gjør den ikke det, avvises
feilvarselet ved innsending, og da får man aldri vite at noe kræsjet.

### Kontrollert og funnet i orden (fra gjennomgangen i august)

Bevart her fordi det er verdt å slippe å revidere på nytt neste gang:

- **Endepunktdekning.** Alle views i `patients`, `core`, `accounts` og `admin_status` har
  `@login_required` eller en rolledekoratør. Ingen ubeskyttede endepunkter funnet. Den
  eneste `@csrf_exempt` er `/healthz/`, som er `@require_safe` og ikke rører data.
- **Path traversal via backup-filnavn er lukket.** `backup_admin_download_view` og
  `backup_admin_delete_view` bygger stier fra `Backup.filename`, men modellen er eksplisitt
  ekskludert fra sin egen dump (`patients/backup.py:31`), så en restore kan ikke injisere
  rader med `../` i filnavnet. Filnavn genereres kun av `_build_filename()`.
- **Django admin-endringer på pasienter blir audit-logget.** Signalet er
  entry-point-agnostisk.
- **Offline-modus** (`ALLOWED_HOSTS=['*']`, CSRF-wildcards for private subnett) er et
  bevisst dokumentert valg, med hard sperre mot at `OFFLINE_MODE` aktiveres på Railway
  (`settings.py:58–62`).
- **MFA trust-cookien invalideres korrekt** når admin nullstiller MFA: `_check_mfa_trust`
  slår opp TOTP-enheten, og `reset_mfa` sletter den.
- **`SECRET_KEY`** hard-feiler ved oppstart når `DEBUG=False`, både på tom verdi og på de
  kjente eksempelverdiene.

## 2026-08-22 — Dokumentstrukturen strammet: TODO som arbeidsliste, docs som referanse

Kun dokumentasjon. **750 tester, alle grønne** — ingen kodeendring.

**Skillelinjen er skjerpet.** Den forrige oppryddingen delte `docs/` i «levende» og
«aktive planer». Det holdt ikke som kriterium — det sa noe om alder, ikke om funksjon. Den
nye regelen er: *en prosedyre du utfører beholdes som fil, en arbeidsliste foldes inn i
`TODO.md`.* Runbooken leses under vakt, deploy-guiden følges steg for steg, dataimporten
kjøres én gang med tre forbehold om datakvalitet — ingen av dem tåler å ligge spredt i en
liste man scroller i. Backlog-dokumenter gjør det motsatte: de duplisere TODO og drifter.

**To arkiverte filer slettet i stedet.** `DEPLOY_FASE_3A.md` beskrev hvordan man pakket en
zip oppå en frisk clone — indeksen sa selv at den etterlot seg «ingenting» i koden.
`ENDRINGSLOGG_2026-05-15.md` var et endringsnotat fra før CHANGELOG fantes, og innholdet
står her under `2026-05-15 (sesjon 1)`. Begge fikk en indekslinje som forklarte at de var
tomme; nå er de borte i stedet. Poenget med å arkivere er å bevare *begrunnelser* — et
dokument uten begrunnelse å bevare skal slettes. Historikken ligger i git.

**Dokumentgjennomgang lagt inn i TODO**, med funnene ferdig kartlagt så jobben er avgrenset
når den skal gjøres. Den tas når funksjonaliteten vi bygger nå er på plass, ikke før:

- `TEKNISK_DOKUMENTASJON.md` er merket «April 2026» og har ikke fulgt med på fire måneders
  refaktorering — `views.py` delt i fem, `core/backup/`, `core/arkiv/` og modulregistryet
  mangler. Alternativet til å oppdatere den er å merke den ærlig som et øyeblikksbilde
- `RUNBOOK_VAKT.md` og `DEPLOY_GUIDE.md` har `<din-app>.railway.app` seks steder til sammen
- `PERSONVERN_DOKUMENTASJON.md` er en annen øvelse: den er art. 30-protokollen og skal
  verifiseres mot koden, ikke slankes. AHASend er en ny databehandler som skal inn

**`OPPSETT_KOLLAPS_CRON.md` er Andres.** Den beskriver en oppgave bare han kan utføre, og
han sletter den selv når jobben står i Railway. Merket i både TODO og `docs/README.md` slik
at en senere opprydding ikke rydder den bort.

**Rettelser:** den arkiverte `FORBEDRINGER.md` ba fortsatt om å bli oppdatert når et punkt
ble ferdig — stikk i strid med at arkivet ikke skal endres. `README.md` oppga Django 5.1
der `requirements.txt` krever `>=5.2.1`. Crawler-seksjonen under var datert 15. august og
skrevet den 22.

## 2026-08-22 — Crawler-sperre: robots.txt og X-Robots-Tag

Portalen får eget domene (`portal.sanitet.net`), og skal ikke kunne finnes via
søk eller havne i et treningsdatasett. **750 tester, alle grønne** (8 nye).

**Utgangspunktet er bedre enn antatt.** En gjennomgang av hele URL-treet uten
innlogging viser at kun to endepunkter svarer 200: `/accounts/login/` og
`/healthz/`. Alt annet — dashboard, pasient-API, statistikk, admin — redirecter
til innlogging. En crawler kan altså aldri nå pasientdata, uavhengig av
tiltakene under. Det som faktisk sto på spill var at innloggingssiden kunne bli
indeksert, ikke at data kunne høstes.

**`core/robots.py`** serverer `/robots.txt` med `Disallow: /` for alle, pluss 22
navngitte AI-crawlere (GPTBot, ClaudeBot, CCBot, Google-Extended, PerplexityBot,
Bytespider m.fl.). Botene navngis eksplisitt fordi flere av dem kun leser regler
adressert til sitt eget agent-navn, og dermed går rett forbi `User-agent: *`.
Endepunktet er bevisst uten auth — en regel ingen får lese, virker ikke.

**`X-Robots-Tag: noindex, nofollow, noarchive, nosnippet, noimageindex`** settes
nå i `SecurityHeadersMiddleware` på *alle* responser, ikke bare de to offentlige
sidene. Grunnen er at et endepunkt som en gang gjøres åpent ellers ville blitt
indekserbart uten at noen la merke til det.

De to mekanismene løser ulike problemer og trengs begge: robots.txt ber
crawleren la være å *hente* siden, headeren ber om at den ikke *vises*. Det
siste dekker også sider som havner i indeksen via en ekstern lenke. Rekkefølgen
mellom dem har en felle som er dokumentert i `core/robots.py`: en URL blokkert i
robots.txt kan ikke leses, så headeren ses aldri — skal noe allerede indeksert
*ut*, må det midlertidig tillates i robots.txt. Ikke et problem for et nytt
domene, men verdt å vite før noen feilsøker det senere.

`core/tests_robots.py` vokter begge: at robots.txt er offentlig og `text/plain`,
at hver `User-agent`-linje faktisk følges av `Disallow: /` (en User-agent uten
Disallow under seg blokkerer ingenting), at alle navngitte boter er med, og at
headeren står på både offentlige og innloggede sider.

**Grensen for hva dette er verdt:** robots.txt er frivillig, og headeren
respekteres kun av crawlere som velger å respektere den. Mot en scraper som
ignorerer begge, er innloggingskravet den eneste reelle beskyttelsen — og det er
også det som faktisk beskytter pasientdataene.

## 2026-08-15 — Dokumentasjonsopprydding: `docs/archived/`, og TODO som eneste arbeidsliste

Kun dokumentasjon. Ingen kodeendring. Suiten kjørt for sikkerhets skyld: **742 tester, alle
grønne.**

Planleggingen hadde spredt seg over ti dokumenter i `docs/`, uten at det gikk an å se hvilke
som fortsatt gjaldt. Ti av dem beskrev arbeid som var ferdig for flere måneder siden, og et
par av de aktive hadde avkryssinger som ikke stemte med koden lenger. Ingenting er slettet.

**Ny mappe `docs/archived/`** — ti dokumenter flyttet dit med `git mv`, historikken intakt:

| Fil | Hvorfor |
|---|---|
| `SANITETSPORTAL_PLAN.md` | Høynivå-skisse v0.1 fra 6. mai. Alle fem faser er levert |
| `SANITETSPORTAL_FASE_1..5.md` (6 filer) | Leveransenotater for faser som er i prod |
| `DEPLOY_FASE_3A.md` | Engangsprosedyre for å pakke en zip oppå en frisk clone |
| `ENDRINGSLOGG_2026-05-15.md` | Duplikat — innholdet står ordrett i CHANGELOG under `2026-05-15 (sesjon 1)` |
| `FORBEDRINGER.md` | Erklærte seg selv som historisk arkiv allerede i toppteksten |

De ni resterende dokumentene i `docs/` er beholdt uendret i innhold. `docs/README.md` skiller
dem i **levende dokumenter** (teknisk, personvern, runbook, deploy — skal holdes oppdatert)
og **aktive planer** (har et sluttpunkt, arkiveres eller slettes når jobben er gjort), med
en tabell over hvor ny dokumentasjon hører hjemme. `docs/archived/README.md` forklarer hva
hver arkiverte fil etterlot seg i koden, og advarer om de to tingene som går igjen der:
`patients/views.py` finnes ikke lenger, og `Behandler` heter `Forstehjelper`.

**`TODO.md` er nå eneste arbeidsliste.** Ny topptekst med kart over hvor ting hører hjemme.
Fem punkter fra forbedringsbacklogen sto åpne uten å være løftet hit — **S3** (rate-limiting
kun på innlogging), **F3** (server-side idempotency), **F4** (lasttest), **F6**
(statistikk-utvidelse) og **F9** (kolonne-kryptering, nedprioritert) — de står nå i TODO med
begrunnelse. Det samme gjelder DPIA-vurderingen fra GDPR fase 5.

De løse punktene nederst er gruppert i «Framtidige moduler» og «Løse punkter». De tre
ubesvarte spørsmålene fra §7 i den arkiverte skissen er tatt vare på under framtidige
moduler — de må avklares før modul nummer to skrives. Med en merknad om at skissens
modulliste (`vakter`/`utstyr`/`rapport`/`beredskap`) er utdatert, mens arkitekturvalgene
står seg. «Fjerne varsler eldre enn 30 dager» var oppført som åpent, men ble gjort som GDPR
fase 2.3 — krysset av.

**Rettelser i aktive dokumenter:**

- `GDPR_TILTAKSPLAN.md`: fase 1 og 2 var merket ✅ FERDIG i overskriften mens samtlige
  underpunkter sto uavkrysset. Avkryssingene stemmer nå med koden. Ny statustabell øverst
  viser de tre punktene som faktisk gjenstår. Fire døde lenker til `patients/views.py`
  (delt i fem moduler ved N13.3) er avlenket — linjenumrene beholdt som historisk kontekst,
  med en merknad om hvorfor
- `FORBEDRINGER_2026-08.md`: vedlikeholdsnotisen ba om at ferdige punkter flyttes til
  `FORBEDRINGER.md`, som nå er arkivert og ikke skal endres. Rutinen er skrevet om.
  F6 viser til to statistikkdokumenter som aldri har ligget i dette repoet — de er fra den
  gamle Pasientregistreringsappen, og det står nå i seksjonen
- `README.md` pekte på `../SANITETSPORTAL_FASE_3A.md`, en sti som aldri traff noe fra
  rotmappa. Rettet til den arkiverte plasseringen
- `accounts/migrations/0007_module_permission_flags.py`: docstringen viser til
  `SANITETSPORTAL_PLAN.md` — stien er oppdatert. Eneste endring utenfor dokumentasjon,
  og den er en kommentar

Alle relative markdown-lenker i repoet er verifisert til å peke på noe som finnes.

## 2026-08-14 — Beslutningsnotater: brukere/e-post og dataimport fra gammel prod

Kun dokumentasjon. Ingen kodeendring.

**`docs/BESLUTNING_BRUKERE_OG_EPOST.md`** — hvordan e-post fungerer i dag (kort: den gjør
det ikke, `EMAIL_HOST` er ikke satt så alt går til Railway-loggen), hva som kreves for at
SMTP skal virke inkludert SPF/DKIM, tre konkrete leverandøralternativer med
miljøvariabler, og de sju beslutningene rundt passord-reset.

Besluttet: invitasjon med signert lenke som registreringsvei, ikke invitasjonskode — koden
er den eneste av alternativene som kan misbrukes, og bulk-onboarding er ikke vist å være et
reelt problem ennå.

To modellendringer spesifisert men ikke kjørt: `fullt_navn` (ett fritekstfelt, ikke
for-/etternavn) og `er_delt_konto` for bil-innlogginger. `CustomUser` arver
`AbstractBaseUser`, så `first_name`/`last_name` finnes ikke i dag.

To ting notatet fremhever som ellers oppdages sent: en e-postleverandør blir
**databehandler** og må inn i personvernprotokollen med avtale, og
**leveringsevne avgjør om funksjonen er brukbar** — en reset-lenke i spam midt i en vakt
betyr at brukeren ringer admin likevel, men nå i tro på at selvbetjening finnes.

**`docs/DATAIMPORT_FRA_GAMMEL_PROD.md`** — årets pasientdata skal fra den gamle
Pasientregistreringsappen inn i portalen.

Funnet ved gjennomgang av `C:\Programmering\pasientregistrering`: **verktøyet finnes
allerede.** `import_offline_data` leser nøyaktig det gamle skjemaet — kolonne for kolonne,
inkludert `behandler_id` og `journal` — fordi kommandoen ble skrevet for
offline-SQLite-filer, og de filene *er* den gamle appen. Ingen ny kode trengs.

Prosedyren er tre standardoperasjoner: `dumpdata` fra prod (read-only), bygg en lokal
SQLite med gammelt skjema, importer med `--dry-run` først.

Tre forbehold dokumentert: `created_at` blir importdatoen (statistikken påvirkes ikke, den
regner på tekstfeltene), det gamle `helsepersonell`-tekstfeltet importeres ikke siden
portalen fjernet det i migrasjon 0010, og whitelisten kan avvise verdier fra før
`choices.py` ble innført.

**Arkiverte vakter importeres ikke, og bør ikke.** SHA-256-signaturen er beregnet over
`arkiv_id`, altså primærnøkkelen — får arkivet ny pk i portalen, melder det tukling. Å
skrive om signaturen for å passe ville undergravd hele poenget. Anbefalingen er å importere
pasientradene og arkivere vakten på nytt fra portalen.

**Rollemodellen er lagt inn som eget TODO-punkt.** Dagens ene globale `role` pluss fem
`kan_redigere_*`-flagg holder ikke med fire moduler til. Flaggene er dessuten feilnavngitt
— `help_text` sier de styrer synlighet i nav-menyen, ikke redigering.

---

## 2026-08-13 — Arkivmønsteret generalisert til `core/arkiv/`

Forberedelse til park-, oppdrags- og rapportmodulen. Frysing, integritetssjekk og kollaps
lå i `patients/services.py` og måtte ellers kopieres tre ganger.

`core/arkiv/` følger samme idiom som `core/backup/`: `BaseArkivHandler` med registry,
registrert fra `apps.ready()`. Core eier kanonisering (`sort_keys=True`,
`ensure_ascii=False`), hashing, valg av signatur ut fra kollaps-tilstand, og
orkestreringen av kollaps. Handleren eier *hva* som går inn i payloaden.

**Den arbeidsdelingen er hele poenget.** SHA-256-signaturen ligger lagret på hvert
`VaktArkiv` i produksjon, og payloadens form er del av den — nøkkelen `'pasienter'`,
sorteringen på `pasientnummer`, feltutvalget. Hadde core bestemt formen, ville samtlige
eksisterende arkiver meldt tukling ved neste visning. `patients/arkiv.py` bygger derfor
payloaden ordrett som før.

**Rekkefølgen var viktig:** signaturene ble først låst til to literale hex-verdier
(`ArkivSignaturLaastTests`), *før* koden ble flyttet. En test som regner ut fasit på nytt
ville ikke fanget dette, siden begge sider endret seg samtidig. Testene passerte etter
flyttingen, altså er hashene bit-identiske.

Nytt i det generiske laget, som pasientmodulen ikke hadde eksplisitt:

- `verifiser()` returnerer `False` for arkiver uten lagret signatur. Det gjelder arkiver
  fra før signaturen ble innført, og å melde tukling på dem ville vært misvisende.
- `har_backup_etter()` returnerer `False` når handleren mangler `backup_slug` — ingen
  sperre betyr at kollaps må tvinges bevisst, ikke at den er fri.
- Aggregatet beregnes *før* transaksjonen åpnes, slik at en feilende beregning ikke
  etterlater slettede rader. Egen test verifiserer rekkefølgen ved å sjekke at aggregatet
  inneholder radantallet fra før slettingen.

19 nye tester i `core/tests_arkiv.py`, med en dummy-handler slik at det generiske laget
dekkes uavhengig av pasientmodulen.

**Ingen migrasjon, ingen modellendring.** `makemigrations --check` rapporterer fortsatt
indeks-omdøpingen i `audit` — det er det kjente avviket som tok prod ned 13. august, og
det skal stå i fred. Det har ingen sammenheng med denne endringen.

**Nesten-ulykke verdt å notere:** `.gitignore` hadde `arkiv/` uten anker. Mønsteret
matcher på alle nivåer, så hele `core/arkiv/`-pakken var usynlig for git. Ble den pushet
slik, ville `patients/apps.py` importert en modul som ikke fantes i repoet — `ready()`
kaster ved oppstart, containeren crash-looper, 502. Samme feilmodus som
migrasjonshendelsen samme dag, med en helt annen årsak.

Linja er endret til `/arkiv/`, som fortsatt dekker den tomme filmappa i rota (rest etter
GDPR fase 2.4). De øvrige uankrede mønstrene er gjennomgått: bare `__pycache__/`, som
skal være uankret, og `vendor/` inne i den allerede ignorerte `staticfiles/`.

Lærdommen er at `git status` må sjekkes for nye *pakker*, ikke bare nye filer. En fil som
mangler gir en importfeil i test; en hel pakke som mangler gir grønne tester lokalt, fordi
fila ligger på disk.

**Utsatt med vilje:** `AbstractArkiv`-basemodell for felt (`sha256`, `kollapset_at`,
`aggregat`, frosset `importert_av_navn`). Den bør skrives når modell nummer to faktisk
finnes, ikke gjettes fram nå — og `VaktArkiv` skal ikke migreres til den.

757 tester grønne.

---

## 2026-08-13 — Ytelse: pasientlista tåler 1000 pasienter og 100 brukere

Foranlediget av en skaleringsgjennomgang: portalen skal ta 10–20 brukere døgnkontinuerlig
med peak rundt 100, og rundt 1000 pasienter per arrangement.

**N+1 på det mest pollede endepunktet.** `_patient_to_dict()` leser navnet på både
førstehjelper og helsepersonell, men `patients_list_view` hadde ikke `select_related`.
Målt på 1000 pasienter (250 med full data fra samleplass, 750 enklere fra park):

| | Før | Etter |
|---|---|---|
| Spørringer per kall | **515** | **15** |
| Ved 25 pollende lesere | ~430/sek | ~12/sek |

Konstant, ikke lineært med radantallet. `PasientlisteYtelseTests` sammenligner
spørringsantallet ved 5 og 60 pasienter i stedet for å låse et absolutt tall — da tåler
testen at annen middleware endrer grunnkostnaden, men fanger fortsatt at kostnaden
begynner å følge radantallet. Verifisert ved å fjerne `select_related` midlertidig.

**ETag på `/api/patients/`.** Svaret er 454 kB ved 1000 pasienter, hentet av hver klient
hvert 30. sekund. Nå returneres 304 uten kropp når ingenting er endret. Kroppen
serialiseres én gang og hashes, i stedet for å hashe feltverdier separat — da kan ETag-en
per definisjon ikke komme i utakt med det som sendes, og den varierer riktig med
`?filter`, `?mine` og `?include_archived` uten at de må håndteres eksplisitt.

Merk hva det sparer: båndbredden, ikke databasearbeidet. Spørringen og serialiseringen
kjører uansett for å regne ut hashen.

**To feller underveis:**

`setFilter()` stoler på at `loadPatients()` kaller `applyFilter()`. En rå tidlig retur på
304 ville latt griden stå med forrige filter når «Mine pasienter» slås av — knappen ville
byttet utseende, men innholdet ikke. 304-grenen kjører derfor `applyFilter()` før den
returnerer.

`renderBoard()` hentet hele lista på nytt ved hver auto-refresh, i tillegg til
`loadPatients()`. Tavlefanen doblet altså trafikken. Den har nå sin egen ETag — den
henter en annen URL (alltid ufiltrert), så den kan ikke dele etag med lista.

**Bakgrunn som ikke ble til kode:** F8 (PgBouncer) er avklart som ikke aktuell. Ved 4
workers × 4 threads bruker appen 16 forbindelser mot grensen på 100, og flaskehalsen var
spørringer og båndbredde — ikke forbindelser. Railways edge-grenser (10 000 samtidige
forbindelser, 11 000 req/s) er heller ikke i nærheten. Målte tall og
`pg_stat_activity`-spørringen er lagt inn i `docs/RUNBOOK_VAKT.md` §3c, siden §2-tersklene
sier hva man skal gjøre når P95 stiger, men ikke hva som ryker først.

735 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — F5, trinn 2: `unsafe-inline` fjernet fra script-src

Trinn 1 er verifisert manuelt i prod — filterknapper, registreringsskjema med
tidsstempler, bekreftelsesdialoger i brukeradministrasjonen og arkivet. Da kunne headeren
flippes.

Hver request får nå et nonce fra `secrets.token_urlsafe(16)`, satt på `request.csp_nonce`
i `SecurityHeadersMiddleware` *før* viewet kjører, og lest i templates via en ny
context-prosessor. `script-src` er
`'self' 'nonce-…' https://cdn.jsdelivr.net https://unpkg.com`.

**Det som er verdt å vite om nonce:** så snart CSP inneholder et, ignorerer nettleseren
`unsafe-inline` for samme direktiv. Det finnes ingen gradvis overgang — enten har hver
eneste inline `<script>` riktig nonce, eller så kjører den ikke. Fire blokker fantes, i
`index.html`, `mfa_verify.html` og `admin_status.html` (to).

CDN-bibliotekene er upåvirket. Tabulator, Chart.js og Bootstrap lastes som eksterne
`<script src=...>`, og vertsnavnene i direktivet gjelder fortsatt — nonce slår ikke ut
allowlisten slik `strict-dynamic` ville gjort. Det besvarer tiltakspunktet «Sjekk om
Tabulator og Chart.js krever `unsafe-inline`»: nei.

**`style-src` beholder `unsafe-inline`.** Akseptansekriteriet for F5 gjelder kun
`script-src`. Markup har rundt 50 inline `style=`-attributter pluss stilsetting bygget i
statistikk-tabellene; det er et eget stykke arbeid, lagt inn som eget TODO-punkt.

`CspNonceTests` sjekker at direktivet mangler `unsafe-inline`, at nonce er unikt per
request, at hver inline `<script>` i alle maler har nonce, og — viktigst — at nonce i
markup er **identisk** med det i headeren. Den siste er den som ville fanget et nonce
generert på feil sted i request-syklusen. Verifisert ved å fjerne nonce fra `index.html`
midlertidig: to tester ble røde, både fil-skanningen og den rendrede siden.

Med dette er `unsafe-inline` og den manglende escapingen i statistikk-tabellene lukket
samme dag. Fram til i dag manglet vi begge lagene samtidig.

730 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — F5, trinn 1: inline event-handlere ut av markup

Forberedelse til å fjerne `unsafe-inline` fra CSP-ens `script-src`. **CSP-headeren er
ikke rørt i denne commiten** — den flippes i trinn 2, slik at hvis noe brekker, vet vi
hvilken halvdel det var.

**Omfanget var større enn punktet beskrev.** F5 nevner «rundt 30 inline `onclick=` i
`index.html`». Det stemte, men i tillegg fantes:

- 6 `onclick=` som *genereres* av `patients-stats.js` (arkivlista og admin-registrene).
  CSP ser det ferdige DOM-et, så attributter satt fra JS blokkeres på samme måte.
- 2 `oninput=` i `index.html`.
- 7 `onsubmit="return confirm(...)"` fordelt på brukeradministrasjonen og
  backup-flaten. Disse var de alvorligste: bekreftelsen foran sletting av bruker,
  frysing av konto og MFA-nullstilling ville forsvunnet stille. Ikke handlingen — bare
  spørsmålet om man var sikker.

Alt går nå gjennom `data-action` (+ `data-arg`/`data-id`), delegert fra `document` i
`patients-app.js`, og `data-confirm` i en ny `static/js/ui-actions.js` som lastes fra
`base_portal.html`.

**Fellen med argumenter:** `toggleForstehjelper(id)` slår opp med `x.id === id`, streng
likhet. Et data-attributt kommer inn som streng, så `x.id === "3"` er usant og funksjonen
ville returnert uten å gjøre noe — og uten feilmelding. Derfor skilles `data-arg`
(streng) fra `data-id` (tall), og delegeringen kjører `Number()` på den siste.

Én sammensatt handler lot seg ikke uttrykke med ett `data-action`:
`onclick="stamp('e-utskrevet');updateTotal()"` er nå `stampUtskrevet()` i
`patients-utils.js`. En annen viste seg overflødig —
`onclick="document.getElementById('n-inntid').value=nowStr()"` er nøyaktig det `stamp()`
gjør.

`InlineHandlerTests` går gjennom alle maler i alle app-mapper og alle JS-moduler, og
feiler med fil og linjenummer hvis en inline handler dukker opp igjen.

**Ikke rørt:** `unsafe-inline` for `style-src`. Akseptansekriteriet i F5 gjelder kun
`script-src`, og markup har 48 inline `style=`-attributter pluss JS-genererte
stilsettinger i statistikk-tabellene.

**Krever manuell QA.** Alle knapper i pasientmodulen og brukeradministrasjonen går nå
gjennom ny kode. Testene ser at attributtene er borte og at delegeringen finnes — de
klikker ikke.

724 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — F7: betinget lasting av statistikkmodulen. F8 utsatt

**Tiltaket slik det var beskrevet ville tatt ned appen.** F7 sa «last
`patients-stats.js` kun for roller som har statistikktilgang», og forutsatte at fila bare
inneholder statistikk. Det gjorde den ikke: `DOMContentLoaded`-bootstrappen lå der —
`initTable()`, `loadPatients()`, `startRefreshInterval()` — sammen med faneskiftet,
auto-refresh og lasterne for navneregistrene, som `patients-forms.js` trenger for
nedtrekkslistene. En `read_only`-bruker ville fått en side uten tabell, uten data og uten
fungerende faner.

Bootstrappen er derfor flyttet til en ny `patients-app.js` (5,9 kB) som lastes for alle
roller. `patients-stats.js` beholder statistikk, arkiv og admin-handlinger, og lastes kun
for `admin`, `lead` og `lead_view`.

**Rollefellen som ikke er åpenbar:** `read_write` har skrivetilgang uten
statistikktilgang. Lagre-knappen for arrangementsnavn er `write-only` og dermed synlig for
den rollen, så `saveEventName` måtte til `patients-app.js`. Samme resonnement flyttet
`renderForstehjelperAdmin`/`renderHelsepersonellAdmin` motsatt vei — de bygger knapper med
`onclick` mot toggle/delete-funksjoner som bare finnes i statistikkmodulen. Det fant ikke
jeg; det fant testen, etter at jeg først hadde plassert dem feil.

Kall fra alltid-lastet kode til den betingede modulen går nå gjennom `_kall('navn')`.
`JsModulLastingTests` leser funksjonsnavnene i `patients-stats.js` og feiler hvis en
alltid-lastet modul kaller noen av dem direkte. Verifisert ved å sette inn et direkte
`loadStats()`-kall midlertidig.

**Måling:** alltid lastet 41 161 bytes, statistikkmodulen 41 516 bytes, admin-bundle
82 677 bytes. En `read_only`-bruker laster **49 %** av admin-bundlen; akseptansekriteriet
var < 50 %.

**Ikke verifisert:** «Første-paint på mobil 4G < 1,5 s». Det krever måling på enhet.
Halvert nedlasting er en forutsetning, ikke et bevis.

**F8 (PgBouncer) er bevisst utsatt.** Punktet sier selv «Kun relevant ved 4+ workers».
Driftsmodusen er 1 worker mellom vakter og 2 under vakt, altså maks 8 forbindelser mot
~100 tilgjengelige, og `conn_max_age=600` demper det ytterligere. Tiltaket er dessuten i
hovedsak en Railway-operasjon, ikke en kodeendring. Tas opp igjen hvis `WEB_WORKERS` økes.

721 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N13.2 og N13.3: navneliste-fabrikk, og `views.py` delt i fem

**N13.2.** `forstehjelpere_view`, `forstehjelper_detail_view`, `helsepersonell_view` og
`helsepersonell_detail_view` var ord for ord like bortsett fra modellnavnet og ordlyden i
feilmeldingene — inkludert hele ETag-blokken og `ProtectedError`-håndteringen.
`_navneliste_views(model, etikett, etikett_bestemt)` bygger nå begge par.

Hele testsuiten passerte uendret etter sammenslåingen, uten at én test måtte røres. Det er
den beste indikasjonen på at oppførselen er bevart. Feilmeldingene vises direkte i
grensesnittet og var det eneste ingen test dekket, så de er pinnet i
`NavneregisterFeilmeldingTests` — inkludert skillet mellom ubestemt og bestemt form
(«Førstehjelper ikke funnet» vs. «Førstehjelperen er knyttet til pasienter»).

**N13.3.** `views.py` (797 linjer) er delt i fem moduler og slettet:

| Modul | Linjer | Ansvar |
|---|---|---|
| `views_common.py` | 82 | `_json_body`, `_patient_to_dict`, `_ensure_pabegynt_not_before_inntid` |
| `views_patients.py` | 382 | Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD, nullstilling |
| `views_registre.py` | 136 | Navneregistrene |
| `views_stats.py` | 47 | `/api/stats/` og `/api/full-stats/` |
| `views_arkiv.py` | 198 | Vaktarkivet |

**Ingen shim.** `urls.py` og de fire testimportene peker direkte på de nye modulene. Å
legge igjen en `views.py` som re-eksporterte alt ville vært å innføre nøyaktig den typen
bakoverkompatibilitets-lag N11 nettopp ryddet bort — og som viste seg å drive fra hverandre.

Testene fanget den ene reelle feilen underveis: `Forstehjelper` og `Helsepersonell` ble
ikke importert i `views_patients.py`, og fem tester på FK-tilordning feilet med `NameError`
på `/api/patients/`. Det er en feil som ville nådd prod uten testdekning på de stiene.

`CLAUDE.md` og teknisk dokumentasjon er oppdatert — begge pekte på `patients/views.py`.

716 tester grønne. Ingen databaseendringer, ingen endring i API-oppførsel.

---

## 2026-08-13 — Restore-kontroll, dødt per-år-navn fjernet, driftsoppgaver løftet i TODO

**Kliniske felt kontrolleres ved backup-restore.** `loaddata` går utenom all
applikasjonsvalidering, og var etter N6 den siste veien inn i databasen der en verdi
utenfor whitelisten kunne lande usett. Ny hook `BaseBackupHandler.inspect_restore_payload()`
kalles fra `restore_backup()` med de deserialiserte objektene;
`PatientsBackupHandler` sjekker mot `patients/choices.py` og rapporterer per felt og verdi,
med antall rader.

**Kontrollen advarer, den blokkerer ikke.** Det er et bevisst valg og motsatt av
`import_offline_data`, som avbryter og krever `--force`. Forskjellen: importen tar inn
fremmed data i en rolig stund, mens restore henter tilbake våre egne data i en stresset
situasjon. En backup fra før whitelisten ble innført må kunne gjenopprettes — å nekte det
ville gjort verktøyet ubrukelig akkurat når man trenger det. `_inspect_payload()` svelger
dessuten alle feil, slik at ødelagt JSON eller en handler som kaster aldri kan bli grunnen
til at en gjenoppretting feiler.

Ni tester, inkludert at en restore med ugyldig verdi fullfører, logger advarsel, og gir
raden tilbake uendret.

**Dødt per-år-arrangementsnavn fjernet.** `set_event_name()`, `get_event_name()` og
`get_event_name_or_legacy()` ble aldri kalt fra noe sted — mekanismen med `event_name_<år>`
er aldri tatt i bruk. Slettet, sammen med whitelist-oppføringen i
`SETTINGS_READ_WHITELIST` fra N12, som dermed beskyttet en nøkkel ingenting skriver.

En test avslørte underveis at den passerte på en bivirkning: `_readable_settings_keys()`
kalte `get_active_year()`, som *oppretter* `active_year`-raden. Uten det kallet fantes ikke
raden i testen. Testen oppretter den nå eksplisitt.

**TODO-en er omstrukturert.** De tre oppgavene som krever Railway-tilgang eller en
avgjørelse utenfor prosjektet ligger nå i en egen seksjon øverst, med konsekvens beskrevet
for hver. Felles for dem: ingen oppdages av testsuiten, ingen gir feilmelding — de er bare
stille inaktive, som er nettopp derfor de har blitt liggende.

712 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — Fiks: template-kommentar rendret som synlig tekst

Kommentaren som ble lagt inn i forrige commit sto synlig i headeren for brukerne.

**Årsak:** `{# ... #}` er **enlinjes** i Djangos template-språk. En kommentar over to
linjer parses ikke som kommentar — den rendres som ren tekst. Flerlinjes kommentarer må
bruke `{% comment %}`/`{% endcomment %}`.

Testene fanget det ikke: de sjekket at `LS26` var borte og at arrangementsnavnet kom med,
ikke at responsen var fri for uparset template-syntaks. Ny test
`test_ingen_uparsede_template_kommentarer_lekker_ut` ser etter `{#`, `#}`,
`{% comment %}` og kommentarteksten i den ferdige responsen. Verifisert mot forrige
versjon av templaten, der teksten faktisk lå i utdataen.

705 tester grønne.

---

## 2026-08-13 — Fiks: gammelt arrangementsnavn sto synlig i headeren ved sidelasting

Meldt fra manuell testing: går man fra portalforsiden inn i `/pasienter/`, vises `LS26` et
kort øyeblikk før det riktige arrangementsnavnet kommer.

**Årsak:** `LS26` var hardkodet som innhold i `#event-name-display` i templaten.
`loadSettings()` byttet det ut, men kalles i `DOMContentLoaded` *etter* tre awaitede
fetch-er — førstehjelpere, helsepersonell og pasienter. Et gammelt arrangementsnavn sto
altså synlig så lenge de tre rundturene tok.

**Fiks:** arrangementsnavnet sendes med i konteksten fra `index_view` og rendres
server-side. Da er headeren riktig i første render, og det finnes ingenting å bytte ut.
`loadSettings()` er beholdt — den henter samme nøkkel, så den kan ikke lenger vise noe
annet, og den fanger fortsatt opp at en annen admin har endret navnet.

**Funnet underveis, og verre enn det som ble meldt:** samme `LS26` var hardkodet i
`value`-attributtet på innstillingsfeltet (`#setting-event-name`). Var `event_name` tom i
databasen, sto plassholderen i feltet uten at noe overskrev den — og et lagre ville skrevet
`LS26` inn som arrangementsnavn. Rettet på samme måte.

Fem tester, hvorav den viktigste sjekker at `LS26` ikke finnes noe sted i responsen når
`event_name` er tom. Et hardkodet navn vises for alle brukere uansett hvilket arrangement
som faktisk er registrert, så det er verdt en vakt.

704 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N12: whitelist på GET /api/settings/, og `invalidate_stats_cache` slettet

**N12.** Endepunktet returnerte hele `AppSetting`-tabellen til enhver innlogget bruker,
også `read_only`. Ingenting der er sensitivt i dag — `event_name`, `active_year`,
`next_patient_nr`, `session_timeout_hours`, `feature.live_stats_enabled` — men tabellen er
generisk nøkkel/verdi-lagring. Neste driftsverdi noen lagret der ville havnet i responsen
automatisk. PUT hadde whitelist fra før; GET hadde ikke, og den asymmetrien er den typen
som blir et problem lenge etter at den ble innført.

`SETTINGS_READ_WHITELIST` speiler nå PUT-lista, og `SETTINGS_WRITE_WHITELIST` gjør
PUT-siden til en navngitt konstant i stedet for en lokal variabel — begge listene ligger
ved siden av hverandre, med kommentar om at utvidelse skal være et bevisst valg.
`event_name_<aktivt år>` beregnes i `_readable_settings_keys()`, siden nøkkelen er
årsavhengig. Spørringen er samtidig blitt `filter(key__in=...)` i stedet for
`objects.all()`.

Sju tester, inkludert akseptansekriteriet: en ny nøkkel er usynlig via API-et til noen
legger den til bevisst.

**Oppfølging fra N11:** `invalidate_stats_cache()` er slettet. Den ble beholdt tidligere i
dag med en docstring om at den var ubrukt; beslutningen er omgjort. En funksjon ingen
kaller er dødkode uansett hvor godt den er dokumentert, og `cache.delete()` er tre linjer
å skrive på nytt den dagen F6 trenger den. De to testene som dekket den er fjernet.
Failsafe-dekningen for cache-utfall er urørt — den ligger på lese-stien
(`test_stats_cache_overlever_redis_feil`), ikke på invalideringen.

699 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N11: CLAUDE.md i samsvar med koden

Fire påstander i «Arkitektur»-seksjonen stemte ikke. Tre av dem var dokumentet som var
utdatert, én var koden.

**Statistikk-caching** — dokumentet lovet invalidering ved pasientendringer via signal.
Det har aldri vært koblet opp; `invalidate_stats_cache()` kalles kun fra tester. Teksten
beskriver nå den reelle mekanismen: TTL på 15/60 sekunder, og try/except rundt alle
cache-operasjoner slik at en død cache degraderer til vanlig beregning.

**Backup** — beskrivelsen («kun `patients`-appen», «logikk i `patients/backup_service.py`»)
var fra før per-modul-omleggingen. Erstattet med en tabell over de to registrerte
handlerne, `patients` og `arkiv`, og en presisering av at logikken ligger i `core/backup/`
mens `backup_service.py` er en proxy som beholdes for `db_backup`, `views.py` og eldre
tester.

**Dekorator-importene** — her var det koden som var feil. `patients/views.py`,
`core/views.py` og `patients/admin_status.py` importerte fra
bakoverkompatibilitets-shimen `accounts/decorators.py`, mens CLAUDE.md sa at man alltid
skal importere fra `core.auth_decorators`. Alle tre er byttet — samme objekter, ren
søk-og-erstatt. Shimen er beholdt, siden `core/tests.py` verifiserer at den fortsatt
virker.

Ny test `test_produksjonskode_importerer_ikke_fra_shimen` går gjennom produksjonsfilene i
alle fem appene og feiler med filnavn hvis noen tar shimen i bruk igjen. Verifisert ved å
sette `core/views.py` tilbake midlertidig. Uten den vakten driver regelen på nytt så snart
noen kopierer en importlinje fra en eldre fil — som er nøyaktig slik de tre oppsto.

**Avvik fra tiltaket:** `invalidate_stats_cache()` er beholdt, ikke slettet. Den er
triviell, testet, og F6 (live-dashbord) vil trenge den. Docstringen sier nå eksplisitt at
den er ubrukt i dag, og at den bør slettes hvis den fortsatt er det ved neste
gjennomgang. Å slette den ville ikke gjort noen påstand i CLAUDE.md mer sann.

693 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N9: `script.js` slettet, dobbeltklikk-vernet faktisk testet

`static/js/script.js` (2159 linjer) er borte. Ingen mal lastet den — monolitten ble delt
i fire moduler i mai, og fila har ligget død siden. Den bar også en kopi av den uescapede
statistikk-koden fra N6, som dermed forsvinner helt.

Det som gjorde punktet verdt mer enn en sletting: `DoubleClickGuardTests` leste nettopp
den døde fila. Testene var grønne, og ville vært grønne også om `withSubmitGuard`
forsvant fra den levende koden. Vernet mot dobbel pasientregistrering — innført etter en
reell hendelse 30. april — var i praksis utestet.

**Tiltakspunkt 3 i N9 spurte om «grep i JS-fil» i det hele tatt er riktig verktøy.
Svaret er nei, ikke alene.** Testene kjører nå guarden i node i stedet for å lete etter
den. Fire nye oppførselstester dekker det vernet skal gjøre:

- to raske klikk gir én registrering
- knappen låses umiddelbart, ikke først når svaret kommer
- låsen holdes i minst 250 ms selv om serveren svarer raskt
- en mislykket lagring frigir låsen, og feilen når fortsatt kalleren

Verdien er målt, ikke antatt: deaktiverer man in-flight-sjekken i `withSubmitGuard`,
feiler den nye testen med `forventet 1 registrering, fikk 2`. Hendelsen fra 30. april,
gjenskapt. De gamle testene var grønne gjennom nøyaktig den endringen.

Tekstsøkene er beholdt der de fortsatt gir mening — at `saveNew`/`saveEdit` bruker
guarden, og at malen har knappe-id-ene — men supplert med en test på at malen faktisk
laster modulene testene leser. Det var den manglende koblingen som gjorde hele problemet
mulig.

Node-plumbingen er trukket ut i `patients/js_test_utils.py` og delt med
`tests_xss_stats.py` fra N6. Modulen heter bevisst ikke `tests_*`, så den ikke plukkes
opp av testoppdagelsen.

**Dokumentasjon:** `CLAUDE.md` og teknisk dokumentasjon beskrev fortsatt frontend som «én
stor `script.js`». Begge er rettet til de fire modulene, med escaping-reglene fra N6 og
en merknad om at nye JS-tester skal kjøre koden, ikke grep-e etter den. Historiske
referanser i eldre dokumenter er latt stå.

677 tester grønne. Ingen databaseendringer. `staticfiles/` er gitignorert og regenereres
av `collectstatic` ved deploy.

---

## 2026-08-13 — N13 delpunkt 1: én feltliste for arkiv-signaturen

De samme 17 feltnavnene var skrevet ut tre steder: ved arkivering
(`arkiver_aktiv_vakt`), ved statistikk (`_arkiv_pasienter_dicts`) og ved
integritetsverifikasjon (`arkiv_detalj_view`). Ble ett av stedene glemt når et felt kom
til, beregnet verifikasjonen SHA-256 over et annet feltsett enn arkiveringen gjorde — og
arkivet meldte «tukling» uten at noe var rørt. En falsk integritetsalarm på GDPR-arkivet
er verre enn en ekte feil, fordi den undergraver tilliten til hele mekanismen.

Nå ligger `ARKIVERT_PASIENT_FELTER` i `patients/services.py`, og alle tre stedene går via
`_arkiv_pasienter_dicts()`.

**Lista er frosset med vilje, ikke utledet fra modellen.** Den nærliggende løsningen — å
utlede feltene fra `ArkivertPasient._meta`, slik N2 gjorde for audit-lista — ville vært
aktivt skadelig her: signaturen lagres på `VaktArkiv.sha256` ved arkivering, så et nytt
felt ville endret signaturen for *alle eksisterende* arkiver samtidig og fått hvert eneste
av dem til å melde tukling. Nøyaktig den feilmoden punktet skulle forhindre.

I stedet: eksplisitt tuple, `ARKIVERT_PASIENT_FELTER_UNNTATT` for `id`/`arkiv`, og
`ArkivFeltlisteTests` som feiler hvis modellen og lista kommer i utakt. Testen tvinger
fram et bevisst valg — «med i signaturen» eller «unntatt» — i stedet for at et nytt felt
havner utenfor stilltiende. Feilmeldingen sier eksplisitt at gamle arkiver får en signatur
som ikke lenger kan reproduseres hvis lista utvides.

Fire nye tester, verifisert ved å fjerne `journal` fra konstanten midlertidig og bekrefte
at vakten peker på riktig felt. Hele suiten: 672 grønne.

Delpunkt 2 (navneliste-fabrikk for de fire førstehjelper/helsepersonell-viewene) og 3
(splitting av `views.py`) står igjen som ren opprydding.

Ingen databaseendringer, ingen endring i beregnet signatur for eksisterende arkiver.

---

## 2026-08-13 — N6: escaping i statistikk-tabellene

Statistikkfanen bygde HTML-strenger og satte dem inn med `innerHTML` uten å escape
verdiene. Rad- og kolonnenøklene i krysstabellene *er* pasientdata (`problemstilling`,
`transport`, `grovsortering`, `utskrevet_til`), og CSP-en tillater fortsatt
`unsafe-inline` for `script-src`, så et injisert `<img onerror=...>` ville kjørt.

**Escaping.** Ny hjelper `escHtmlValue()` i `patients-utils.js`, brukt i `mkStatsTable`,
`mkCrosstab`, `mkObsTable` og `mkInterpretation`. Den finnes ved siden av `escapeHtml()`
og `_escHtml()` fordi de to eldre returnerer tom streng for alt falsy — `escapeHtml(0)`
gir `''`. I tabellceller er det feil: 0 er en gyldig verdi som skal vises.

**Klarert markup.** Å escape alle celler blindt var ikke mulig. `renderTester` sender
bevisst `<span style="color:#22c55e">&#10004; Ja</span>` inn i `mkStatsTable`, og
`sigCol`-logikken leter etter `&#10004;` i strengen. `trustedHtml()` markerer markup koden
har bygget selv, `cellHtml()` slipper den gjennom og escaper alt annet. Unntaket er dermed
et bevisst valg per celle, ikke en generell åpning — to celler bruker det i dag.

**Funn utenfor punktet:** `renderForstehjelperAdmin` og `renderHelsepersonellAdmin` satte
også navnene uescapet i `innerHTML`. Det er verre enn N6 selv, siden
`Forstehjelper.name`/`Helsepersonell.name` er fritekst uten `choices` — whitelisten som
demper resten gjelder ikke der i det hele tatt. Rettet i samme runde.

**Import-validering.** `import_offline_data` bygde `Patient`-objekter direkte og gikk
utenom whitelisten. Den kaller nå `validate_patient_choice_fields` per rad, før noe
skrives. Ugyldige verdier avbryter importen med en rapport som dekker alle radene på én
gang; nytt `--force` importerer dem likevel, for bevisst import av gamle data.

**Tester.** `patients/tests_xss_stats.py`, to lag:

- Node kjører tabell-byggerne mot HTML-holdige feltverdier og verifiserer
  akseptansekriteriet direkte. Hoppes over hvis `node` ikke finnes.
- En statisk vaktpost krever at hver `${...}` i byggerne er escapet eller står i
  `REVIEWED_INTERPOLATIONS` med begrunnelse. Verifisert ved å fjerne escapingen
  midlertidig og bekrefte at testen peker på riktig uttrykk. Det er dette laget som
  betyr noe for F6 senere: de sju nye krysstabellene der kan ikke gli inn uescapet.

Fire nye tester i `patients/tests_offline.py` dekker import-valideringen. Hele suiten:
668 tester grønne.

**Ikke gjort:** F5 (CSP-stramming) ble *ikke* tatt i samme runde, slik
FORBEDRINGER-dokumentet foreslo. Den krever at ~30 inline `onclick=`-handlere i
`index.html` flyttes til `addEventListener`, som er mesteparten av arbeidet der.
`unsafe-inline` står fortsatt. Escapingen er på plass uavhengig av det, så vi mangler ikke
lenger begge lagene samtidig.

**Gjenstår som uvalidert vei inn i basen:** backup-restore via `loaddata`. Den går utenom
all validering, og er nå den eneste igjen. `static/js/script.js` har samme uescapede kode
i den døde kopien sin, men fila skal slettes (N9) og ble derfor stående.

Ingen databaseendringer.

---

## 2026-08-13 — Fiks: uregistrerte sesjoner overlevde innlogging på ny enhet

Funnet ved manuell testing i prod. Innlogging på enhet 2 kastet ikke ut enhet 1 —
én-sesjon-per-bruker-policyen var brutt.

**Årsak:** `current_session_key` ble innført tom for alle brukere. En sesjon opprettet før
feltet fantes er ikke registrert, så innloggingen fant ingen nøkkel å slette.
`_registrer_aktiv_sesjon` behandlet tom nøkkel som «ingen sesjoner finnes», mens den i
virkeligheten betyr «vi vet ikke om det finnes noen».

**Fiks:** Er feltet tomt, faller vi tilbake til den fullstendige gjennomgangen av
sesjonstabellen. Det koster ett fullt gjennomløp per bruker, første gang de logger inn
etter at feltet ble innført; deretter gjelder den raske stien og ytelsesgevinsten fra N10
består.

Passordbytte fjernet sesjonen korrekt hele tiden — den stien har alltid hatt den grundige
gjennomgangen, og skillet fungerte som designet.

Regresjonstesten ble verifisert ved å reversere fiksen midlertidig og bekrefte at den
feiler med nøyaktig det observerte symptomet.

**Merk:** Fiksen rydder ikke opp i sesjoner som allerede har overlevd. De forsvinner når de
utløper (maks 8 timer), ved passordbytte, eller ved at admin dreper dem fra
`/portal-admin/server-status/`.

Full suite: 650 tester, grønn. Ingen migrasjon.

---

## 2026-08-13 — Ytelse: N7, N8, N10

Tre steder der kostnaden lå i requestens kritiske vei.

**Redis-klienten ble bygget på nytt for hver request (N7).**
`_MetricsStore._get_redis_client()` kalte `redis.Redis.from_url()` ved hvert kall, og den
lager en ny `ConnectionPool` hver gang — verken pool eller TCP-forbindelse ble gjenbrukt.
`_record_to_redis()` kalles for hver eneste request i vakt-modus, så vi betalte en
TCP-handshake per request for å skrive én metrikk-linje. I koden som finnes for å måle
ytelse.

Nå én delt klient per prosess med dobbeltsjekket låsing. `redis.Redis`-instanser er
trådtrygge og har egen intern pool, så det er riktig mønster. Metoden er beholdt som
delegat, slik at de eksisterende testene som patcher den virker uendret.

**Audit-signalet gjorde én INSERT per endret felt (N8).** En typisk PUT der behandler
settes utløser samtidig `pabegynt`-stempling og plasseringsendring — 1 SELECT + 3 INSERT +
selve UPDATE for én brukerhandling. Nå samles radene og skrives med `bulk_create`.
`app_label` settes eksplisitt, siden `bulk_create` hopper over `pre_save`-signalet som
ellers fyller feltet; uten det ville radene vist seg som «Ukjent» i modulfilteret.
Verifisert med `CaptureQueriesContext`: tre endrede felt gir én INSERT.

**Sesjonsinvalidering dekodet hele sesjonstabellen ved hver innlogging (N10).**
`get_decoded()` er signaturverifisering og JSON-parsing per rad, og kallet lå i
innloggingsstien — de ti minuttene ved vaktstart der alle logger på samtidig.

**Her fulgte vi ikke backloggens anbefaling.** Alternativ A var å droppe kallet ved ordinær
innlogging, beskrevet som «en policy-avgjørelse, ikke en sikkerhetsnødvendighet». Men
policyen er reell og bevisst: portalen har én-sesjon-per-bruker, og `SingleSessionTests`
vokter den eksplisitt. Å droppe kallet ville stille endret produktoppførsel — innlogget på
mobil og laptop samtidig — under dekke av en ytelsesforbedring.

I stedet: `CustomUser.current_session_key`, ett nullbart felt (ingen ny tabell, som svarer
på innvendingen mot alternativ B om foreldreløse rader). Innlogging sletter forrige sesjon
med ett indeksert oppslag. Feltet er en cache av policyen, ikke fasit for hvilke sesjoner
som finnes — derfor beholder passordbytte, admin-reset, frys og sletting den fullstendige
gjennomgangen, der garantien er hele poenget og operasjonen er sjelden. En test verifiserer
at passordbytte også fjerner en uregistrert sesjon.

Verifisert: antall spørringer ved innlogging er identisk med 0 og med 30 fremmede sesjoner
i tabellen.

**Re-landet etter rollback.** Første forsøk (`48d861c`) tok ned produksjon — men ikke på
grunn av ytelsesarbeidet. Den commiten inneholdt også `audit/0004`, en uetterspurt
indeks-omdøping som viste seg umulig å kjøre mot den faktiske databasen. Se hendelsesnotatet
under.

Denne gangen følger kun `accounts/0008`, håndskrevet til å gjøre én ting: legge til én
nullbar kolonne. `makemigrations` ville tatt med en `AlterField` på `is_superuser` i samme
slengen — samme slags kosmetiske opprydding som forårsaket nedetiden, og derfor utelatt.
Drift-advarselen ved oppstart består, og er ufarlig.

**Andre nedetid samme dag, og hva den lærte oss:** første forsøk på å re-lande feilet med
`DuplicateColumn: column "current_session_key" already exists`. Årsaken var at
`accounts/0008` **hadde** blitt anvendt under den opprinnelige deployen — hver migrasjon
kjører i egen transaksjon, så den commitet før `audit/0004` feilet. Analysen av den første
loggen konkluderte feilaktig med at ingen av migrasjonene hadde gått gjennom.

Da migrasjonen ble skrevet om for hånd, fikk fila samtidig et nytt, mer beskrivende navn.
**Django matcher migrasjoner på app + navn, ikke på innhold.** Databasen hadde
`0008_customuser_current_session_key_and_more` registrert; repoet hadde
`0008_customuser_current_session_key`. Django så en ukjent migrasjon og prøvde å legge til
kolonnen på nytt.

Fila heter derfor fortsatt `..._and_more` selv om innholdet ikke lenger inneholder «more».
Det står som en advarsel øverst i migrasjonens docstring. Fiksen ble verifisert mot en
lokal database satt i nøyaktig samme tilstand som produksjon — kolonne til stede,
migrasjon registrert under det gamle navnet — der `migrate` svarer «No migrations to
apply».

15 nye tester i `patients/tests_ytelse.py`. Full suite: 648 tester, grønn.

---

## 2026-08-13 — HENDELSE: produksjon nede ~30 min. Ytelses-commiten rullet tilbake

**Symptom:** 502 på portalen. Railway crash-loopet release-kommandoen, med nytt forsøk
hvert par sekund fra 09:42:50 UTC.

**Rotårsak:**

```
django.db.utils.ProgrammingError:
relation "audit_audit_created_a3c1b8_idx" does not exist
```

`audit/0004` forsøkte å døpe om en indeks som ikke finnes i produksjonsdatabasen. Django
trodde den fantes fordi `audit/0002` står registrert som anvendt og er migrasjonen som ga
indeksen det navnet — men den fysiske indeksen i Postgres heter noe annet. Djangos
migrasjonshistorikk og databasen har vært ute av takt hele tiden. Advarselen «*models in
app(s) 'accounts', 'audit' have changes that are not yet reflected*», som står i samtlige
deploy-logger langt tilbake, var symptomet på nettopp det.

Release-kommandoen avbrøt ved første feilende migrasjon, så `accounts/0008` ble aldri
forsøkt. **Ingen av de to migrasjonene ble anvendt** — databaseskjemaet er uendret.

**Hvorfor det skjedde:** `audit/0004` var ikke en del av ytelsesarbeidet. Den ble generert
på eget initiativ som opprydding av et kosmetisk avvik, og lagt inn i samme deploy. Det
gjorde en uetterspurt skjemaendring til en del av en leveranse — på nettopp den tabellen
`FORBEDRINGER.md` #1 dokumenterer at har hatt rotete migrasjonshistorikk før. Selve
ytelsesarbeidet (N7, N8, N10) er ikke det som brakk noe.

**Tiltak:** Hele ytelses-commiten `48d861c` er revertert, inkludert `audit/0004`. Koden er
tilbake på `32f417d`, som deploy-loggen viser at kjørte normalt og registrerte en pasient
(`POST /pasienter/api/patients/ status=201`) kl. 11:16.

N7, N8 og N10 er satt tilbake til ⏳ i backloggen og re-landes som egen, verifisert
leveranse — uten indeks-migrasjonen.

**Indeks-avviket i `audit` lar vi stå.** Indeksen fungerer uansett hva den heter; det er
kun Djangos bokføring som er skjev. Skal det ryddes, må det gjøres ved å lese det faktiske
indeksnavnet i Postgres først — ikke ved å la `makemigrations` gjette.

**Lærdom:**

1. Ikke bland uetterspurt skjemarydding inn i en funksjonell leveranse.
2. `makemigrations` genererer mot Djangos *modellstatus*, ikke mot databasen. Der de to har
   drevet fra hverandre, produserer den migrasjoner som feiler i prod og går grønt lokalt.
3. Deploy én pulje av gangen og verifiser i prod før neste. Tre uverifiserte deploys på rad
   gjorde at feilsøkingen måtte starte med å finne ut hvilken av dem som brakk noe — og to
   av tre var uskyldige.

---

## 2026-08-13 — Sporbarhet og korrekthet: N2, N5, S7

**Audit-loggen var ufullstendig (N2).** `felt_to_track` var en håndholdt liste, og
`helsepersonell_ref_id` hadde falt ut av den. Endret man hvem som var oppfølgingsansvarlig
for en pasient, ble det ikke skrevet noen `AuditLog`-rad — samtidig som
`PERSONVERN_DOKUMENTASJON.md` A.10 lover at alle pasientendringer logges på feltnivå.

Løst med det grundige alternativet: lista utledes nå fra modellen. `FELT_UTEN_AUDIT`
inneholder de fire feltene som bevisst ikke logges (`id`, `pasientnummer`, `created_at`,
`updated_at`), og `felt_som_spores()` returnerer alt annet. Vendingen er poenget —
glemsomhet gir nå for mye logging i stedet for for lite. En test itererer modellens felter
og feiler hvis noe verken spores eller er eksplisitt unntatt.

**Sidefunn i samme funksjon:** `str(getattr(obj, felt, '') or '')` kollapset alle falsy
verdier til tom streng, også `False`. Deaktivering av en pasient ble derfor logget med
`new_value=''`, og DELETE-grenen — som sammenlikner mot `'False'` — kunne aldri slå til.
Alle deaktiveringer har stått som UPDATE i loggen. Rettet med `_audit_verdi()`, som kun
gjør `None` til tom streng.

Begge fixene virker kun fremover. Historiske endringer av helsepersonell er tapt.

**Container-tid (N5).** `get_active_year()` og `Patient.save()` brukte
`datetime.now().year`, som gir naiv container-lokaltid — UTC på Railway, uavhengig av
`TIME_ZONE='Europe/Oslo'`. Mellom midnatt og kl. 01:00 norsk vintertid er UTC-året fortsatt
det forrige, så en nyttårsvakt ville lagret pasienter på året som nettopp gikk.
Listevisningen filtrerer på samme funksjon og ville vært konsistent med seg selv — feilen
ville ikke blitt sett før noen så på statistikken i ettertid.

Ny `core.validators.current_local_year()` ved siden av `now_local_str()`, brukt begge
steder. Akseptansekriteriet er automatisert: en test parser `patients/` og `core/` med AST
og feiler hvis noe kaller `datetime.now()`. AST og ikke tekstsøk, så omtale i docstrings
ikke gir falske treff. Testet med frosset tid 31.12 kl. 23:30 UTC → 2027, kl. 22:00 UTC →
2026.

**Personverndokumentasjonen (S7).** Fire punkter, lukket på tre ulike måter:

1. **Audit-dekning** — rettet i koden (N2). Påstanden i A.10 er sann igjen uten tekstendring.
2. **Lagringstider** — var aldri et avvik; `purge_old_logs` kjører som cron. Se gårsdagens
   rettelse.
3. **`escapeHtml()`-dekning** — rettet i dokumentet, siden N6 fortsatt står åpen. A.10 og
   teknisk dokumentasjon sier nå eksplisitt at dekningen gjelder pasientskjemaet og
   arkivvisningen, ikke statistikk-tabellene, med henvisning til N6 og en merknad om at
   serverside-whitelisten demper risikoen.
4. **Argon2** — rettet i teknisk dokumentasjon, som sa at Argon2 var i bruk. Den er ikke
   installert. A.10 hadde det riktig hele tiden; de to dokumentene motsa hverandre.

12 nye tester i `patients/tests_audit_og_tid.py`. Full suite: 633 tester, grønn.

---

## 2026-08-13 — Drift: logging som når fram (N3) og e-postvarsel ved feil (F1)

**Applikasjonsloggene har aldri nådd fram (N3).** `LOGGING` hadde én logger (`memory`) og
ingen rot-logger. Alt `patients`, `core` og `accounts` logget propagerte opp til en rot uten
handler, og havnet i Pythons `lastResort` — som skriver til stderr først fra WARNING. All
INFO-logging var altså slått av i produksjon, inkludert nettopp de linjene RUNBOOK-en ber
deg lete etter for å verifisere at backup kjører.

Nå: rot-logger med handler, `standard`-formatter med tidsstempel, loggernavn og nivå, og
`LOG_LEVEL` som miljøvariabel (default `INFO`) slik at man kan skru til DEBUG på Railway
uten deploy. Verifisert at INFO fra alle tre appene faktisk når stdout formatert.

**E-postvarsel ved kritiske feil (F1).** Tatt i samme runde som N3, slik backloggen
anbefalte — `LOGGING` måtte uansett bygges om. `django.request` logger nå til både konsoll
og `mail_admins`. Dempingen ligger i `core/log_filters.py::ThrottleByMessageFilter`: maks
én mail per feiltype per 15 minutter, der feiltype er (logger, nivå, fil, linje) og ikke
meldingsteksten — samme kodefeil gir ofte varierende tekst (ulike pasient-ID-er), og en
tekstbasert nøkkel ville sluppet gjennom hver variant som om den var ny.

Filterets state er per prosess, så med to arbeidere kan man i verste fall få to mailer per
vindu. Bevisst valg: delt state i Redis ville gjort varslingsstien avhengig av at Redis er
oppe, nøyaktig det man ikke vil når man varsler om at noe er galt.

Uten SMTP-variabler er alt inert — `EMAIL_BACKEND` faller tilbake til konsoll. Variablene
er dokumentert i `.env.example` og `CLAUDE.md`.

**Rettelse av F2 og S7 — et funn som ikke var et funn.** Augustgjennomgangen skrev at
`purge_old_logs` aldri var satt opp som cron-jobb, og at lagringstidene på 730/30 dager i
`PERSONVERN_DOKUMENTASJON.md` A.9 dermed var en dokumentert, men ikke reell kontroll. S7
beskrev dette som det mest alvorlige av fire dokumentasjonsavvik, siden det gjaldt en
slettepraksis oppgitt overfor både de registrerte og tilsynsmyndighet.

**Det stemte ikke.** Jobben kjører som aktiv Railway Cron Job. Feilen oppsto fordi
cron-jobber lever i Railway-dashbordet og ikke er synlige i repoet — gjennomgangen leste
fravær i koden som fravær i drift. En in-process scheduler ble bygget og deretter rullet
tilbake da dette kom fram; to mekanismer som sletter de samme radene, hvorav den ene er
usynlig inne i web-prosessen, er verre enn én eksplisitt cron-jobb.

F2 og den ene raden i S7 er rettet i backloggen, med lærdommen notert: infrastruktur
utenfor repoet må verifiseres med den som eier driften før den skrives ned som funn. En
gjennomgang som påstår et GDPR-avvik som ikke finnes, er ikke ufarlig.

10 nye tester i `core/tests_drift.py`. Full suite: 621 tester, grønn.

---

## 2026-08-13 — To feil funnet ved manuell testing av innloggingsflyten

Begge forhåndseksisterende, begge avdekket fordi `?next=` ble testet manuelt i prod.

**`?next=` har aldri virket.** Skjemaet i `login.html` poster til
`action="{% url 'accounts:login' %}"`, som ikke tar med query-strengen. Verdien gikk
dermed tapt i det brukeren trykket «Logg inn», og man havnet alltid på forsiden — også når
`@login_required` hadde sendt en dit fra en bestemt side. Fikset med et skjult `next`-felt,
og viewet leser nå fra POST først og query-strengen som fallback. Samme mønster som Django
sin egen `LoginView`.

Verdt å merke: dette betydde at den åpne redirecten i N1 ikke var utnyttbar i praksis via
skjemaet — verdien nådde aldri fram til `redirect()`. Valideringen fra N1 er like fullt
riktig, og er nå det som holder når parameteren faktisk virker.

**Innloggingssiden manglet `@never_cache`.** Uten den kan nettleseren servere en lagret
kopi av skjemaet, og CSRF-tokenet i den kopien er knyttet til en cookie som er rotert
siden — både `login()` og `logout()` kaller `rotate_token()`. Resultatet er «CSRF-
verifisering feilet. Forespørsel avbrutt.» ved innsending, observert på iOS. Django sin
egen `LoginView` er dekorert på samme måte, av samme grunn.

**Testhullet som slapp begge gjennom:** de eksisterende testene poster direkte til
`/accounts/login/?next=...` og treffer dermed viewet, ikke nettleserflyten. Ny testklasse
`NextGjennomSkjemaTests` henter siden, leser feltene ut av HTML-en og poster til skjemaets
faktiske action med `Client(enforce_csrf_checks=True)` — altså det nettleseren gjør.

5 nye tester. Full suite: 611 tester, grønn.

---

## 2026-08-13 — Herding av innloggingsflyten: N1, S4, N4, S5, S6

Siste pulje på innloggingsflaten. Med denne er alle sikkerhetspunktene rundt innlogging fra
augustgjennomgangen lukket.

**Åpen redirect (N1 + S4).** `login_view` sendte `?next=` rett til `redirect()`, som godtar
absolutte URL-er. En lenke som `?next=https://falsk-sanitetsportal.example/` sendte altså
brukeren til angriperens side *rett etter en vellykket innlogging* — i det øyeblikket de
har mest tillit til at de er på riktig sted. Ny felles helper
`core/url_safety.py::safe_redirect_url()` bygger på `url_has_allowed_host_and_scheme` og
brukes begge steder: `next` valideres ett sted, der den leses, så MFA-stegene arver den
validerte verdien via sesjonen (og validerer den på nytt ved lesing, i tilfelle sesjonen
stammer fra en eldre release). Samme helper på `Notification.url` i
`notification_mark_read_view` (S4) — i dag settes den kun med hardkodede relative stier,
men `notify()` er designet som et generisk API for framtidige moduler.

**MFA-rate-limiting (N4).** MFA-stegene håndteres inne i `login_view`, men skjemaene sender
ingen `username` — bare koden. Dekoratoren med `key='post:username'` slo derfor opp en tom
verdi, og **alle MFA-forsøk fra alle brukere delte én bøtte**: 10 MFA-innlogginger per 5
minutter totalt for hele appen. Ved vaktstart, når alle logger på samtidig, ville bruker
nummer 11 fått 429 uten at noe var galt med kontoen.

Løst ved å flytte rate-limitingen fra dekoratorer til eksplisitte `is_ratelimited`-kall per
steg. Steg 1 beholder sine to bøtter (brukernavn og IP); MFA-stegene får hver sin bøtte
nøklet på bruker-ID fra sesjonen. Ingen URL-endring, og ingen brukernavn i POST-body.

Kontosperren er utvidet til å gjelde MFA-steget: `_registrer_mislykket_forsok()` deles nå
av begge steg, og `is_locked()` sjekkes ved inngangen til verifiseringen. Tidligere kunne
man gjette TOTP-koder i det uendelige uten at telleren ble rørt. Rate-limit-sjekken ligger
bevisst før sperresjekken, ellers ville den låste kontoen vært den ubegrensede stien.

**Utlogging krever POST (S5).** `logout_view` hadde ingen metode-restriksjon, og malene
lenket til den med `<a href>`. Enhver side på internett kunne logge ut brukeren vår med en
`<img src=".../accounts/logout/">`. De tre malene bruker nå skjema med CSRF-token.

**Trust-cookie i offline-modus (S6).** `is_secure = not DEBUG` ga `Secure`-flagget i
offline-modus, som kjører bevisst uten TLS — nettleseren kastet cookien, og «stol på denne
enheten» virket aldri i felt. Nå `request.is_secure()`, som tar hensyn til
`SECURE_PROXY_SSL_HEADER` og er riktig både på Railway og offline.

**Bemerket underveis:** `django_otp` throttler i tillegg selve TOTP-enheten etter feilede
`verify_token()`-kall (`ThrottlingMixin`, eksponentiell backoff). Et uavhengig lag som
allerede virket — verdt å kjenne til, siden det gjør at en korrekt kode rett etter flere
feilforsøk avvises en kort stund.

23 nye tester i `accounts/tests_innlogging_herding.py`. Full suite: 606 tester, grønn.

---

## 2026-08-13 — S1 + S2: én innloggingsflate, all administrasjon under /portal-admin/

**`/django-admin/` er slått av i produksjon.** Django sin innebygde admin var en parallell
innloggingsflate som omgikk samtlige sikringer appen har på innlogging: rate-limiting per
brukernavn og IP, kontosperre etter 5 feilede forsøk, MFA-tvang for brukere med
`mfa_required`, tvungent passordbytte og `LoginEvent`-logging. Alt dette ligger på
`accounts.views.login_view`; `django_otp` sin `OTPMiddleware` håndhever ingenting, den
setter kun `request.user.otp_device`. Bak flaten lå `Patient`, `CustomUser`, `AuditLog` og
`AppSetting`.

`admin.site.urls` monteres nå kun bak `if settings.DEBUG or settings.OFFLINE_MODE`, altså
som lokalt utviklerverktøy. Begge retninger er verifisert: med `DEBUG=False` gir
`/django-admin/` 404 og `reverse('admin:index')` kaster `NoReverseMatch`; med `DEBUG=True`
monteres den som før. `/django-admin/` er også fjernet fra
`MustChangePasswordMiddleware.ALLOWED_PATHS` — unntaket gjorde passordbytte-påbudet
valgfritt for alle med `is_staff`.

**`create_superuser` arver `must_change_password=True`** (S2). Modellens default er `True`,
men manageren overstyrte den til `False`, så bootstrap-adminen — kontoen med mest tilgang,
opprettet med passord fra en miljøvariabel ved hver deploy — aldri ble bedt om å bytte.
Tre eksisterende tester feilet på endringen fordi de opprettet en superbruker og forventet
å nå vanlige sider. Det var beviset på at sikringen virker.

**Paritet før fjerning.** To hull måtte lukkes først:

- **`/portal-admin/innloggingslogg/`** — global, paginert `LoginEvent`-visning med filter på
  brukernavn/IP, hendelsestype, resultat og datoperiode. Brukerdetaljsiden viser kun siste
  20 for én bruker og svarer ikke på spørsmål som går på tvers («kom det en serie feilede
  forsøk fra én IP i natt»).
- **`python manage.py appsetting`** — `--list`, `--get`, `--set`, `--delete`.
  `PUT /api/settings/` skriver kun `event_name`, så `active_year`, `next_patient_nr` og
  feature-flagg hadde ingen annen vei inn enn django-admin. Bevisst en CLI og ikke en
  UI-flate: verdiene endres sjelden og har konsekvenser for nummerserie og årshåndtering.

**Brukeradmin flyttet til `/portal-admin/brukere/`.** `/accounts/users/*` svarer med 301.
Begrunnelsen er ikke kosmetisk: `MustChangePasswordMiddleware` matcher stier med
`startswith`, og framtidige regler (rate-limiting, ekstra rollesjekk) vil naturlig skrives
på samme form. Lå brukeradministrasjonen igjen under `/accounts/`, ville en regel for
`/portal-admin/*` stille gått utenom nettopp den flaten som oppretter kontoer og deler ut
admin-rollen. `accounts/urls.py` mountes derfor på root og fordeler selv mellom
`/accounts/` (innlogging, utlogging, passordbytte) og `/portal-admin/` (administrasjon).
URL-*navnene* er uendret, så maler og tester var upåvirket av flyttingen.

25 nye tester i `accounts/tests_admin_flate.py`. Full suite: 583 tester, grønn.

---

## 2026-08-13 — Brukeradministrasjon i portalen: 500-feil, MFA-toggle, frys og sletting

Forarbeid til **S1** (fjerne `/django-admin/`). Portalens egen brukeradministrasjon på
`/accounts/users/` manglet funksjonalitet som kun fantes i Django admin — den kan ikke
fjernes før paritet er på plass.

**Rettet 500-feil ved opprettelse av bruker.** `AdminUserCreateForm.clean_email` kalte
`.strip()` på `None`. Modellfeltet er `null=True`, så ModelForm setter `empty_value=None`
på skjemafeltet: lot man e-post stå tom ble `cleaned_data['email']` `None`, ikke `''`, og
defaultverdien i `.get('email', '')` slo aldri inn. Feilen traff kun brukere uten e-post,
som er grunnen til at den så tilfeldig ut. `AdminUserEditForm` hadde allerede riktig
mønster.

**«Krev MFA» kan nå styres fra portalen.** `mfa_required` var ikke med i
`AdminUserEditForm.Meta.fields` og hadde ingen avkrysning i malen. Eneste vei til feltet
var «Nullstill MFA», som tvinger det til `True` — altså kunne MFA slås på, men aldri av
igjen uten Django admin. Feltet vises nå både i redigeringsskjemaet og som kolonne i
brukerlista.

**Frys/tø konto** (paritet med bulk-aksjonen i `CustomUserAdmin`): deaktiverer kontoen og
sletter aktive sesjoner i samme operasjon, slik at en allerede innlogget bruker ikke kan
fortsette til cookien utløper. Sperre mot å fryse egen konto.

**Permanent sletting av brukerkonto** — `POST /accounts/users/<pk>/slett/`. Sletting er
trygt fordi alle referanser til brukeren er `SET_NULL` (`LoginEvent`, `AuditLog`,
`Forstehjelper.user`, `Helsepersonell.user`, `Backup.created_by`,
`ModuleSettings.updated_by`, og `VaktArkiv.importert_av` siden GDPR fase 4.1, som fryser
navnet i `importert_av_navn`). Navn bevares altså på historiske pasienter og i arkivet.
`core.Notification` er `CASCADE` — varsler til en slettet bruker skal bort.

To sperrer: man kan ikke slette sin egen konto, og ikke den siste aktive administratoren.
Den siste blir kritisk når `/django-admin/` fjernes, siden det da ikke finnes noen
nødutgang tilbake inn i brukeradministrasjonen. I tillegg må admin skrive brukernavnet
ordrett som bekreftelse.

Frys og sletting skrives til `AuditLog` (`table_name='accounts_customuser'`) og er dermed
synlige i `/portal-admin/auditlog/`. Revisjonsraden har ingen FK til brukeren og overlever
derfor slettingen.

22 nye tester i `accounts/tests_user_admin.py`. Full suite: 558 tester, grønn.

**Gjenstår før S1 kan lukkes:** `LoginEvent` har ingen global visning i portalen (kun
siste 20 per bruker), og `AppSetting` kan ikke redigeres utenom `event_name`.

---

## 2026-08-13 — Sikkerhetsvurdering: dokumentasjonsavvik (S7)

Etter en samlet sikkerhetsvurdering av kodebasen mot `TEKNISK_DOKUMENTASJON.md` og
`PERSONVERN_DOKUMENTASJON.md` er fire punkter der dokumentasjonen påstår kontroller som
ikke er reelle i dag lagt til som **S7** i `docs/FORBEDRINGER_2026-08.md`. Fortsatt ingen
kodeendringer.

`PERSONVERN_DOKUMENTASJON.md` er behandlingsprotokollen etter GDPR art. 30 — et avvik der
er ikke bare unøyaktighet, det er dokumentasjon som ikke stemmer med behandlingen:

- A.10 sier «alle pasient-endringer logges på felt-nivå» — `helsepersonell_ref_id`
  mangler i sporingen (N2)
- A.9 sier lagringstid 730/30 dager — `purge_old_logs` er aldri satt opp som cron, så
  fristene håndheves ikke i praksis (F2)
- A.10/§7.9 viser til `escapeHtml()` som generell XSS-beskyttelse — statistikk-tabellene
  er ikke dekket (N6)
- §7.1 i teknisk dokumentasjon sier Argon2 er i bruk; A.10 sier korrekt at den ikke er
  installert — de to dokumentene motsier hverandre

Mest alvorlig er lagringstidene, siden det er en slettepraksis beskrevet overfor både de
registrerte (del B) og tilsynsmyndighet (del A) som ikke finner sted.

---

## 2026-08-12 — Kodegjennomgang: ny forbedringsbacklog

Full gjennomgang av kodebasen for å finne hva som bør forbedres. **Ingen kode er endret** —
dette er kun kartlegging og dokumentasjon.

Nytt dokument `docs/FORBEDRINGER_2026-08.md` er den aktive backloggen. Den inneholder 13
nye funn (N1–N13), 6 funn fra et eget sikkerhetspass (S1–S6) og de 9 punktene fra
mai-runden som fortsatt sto åpne (F1–F9).
`docs/FORBEDRINGER.md` er konvertert til et historisk arkiv over det som ble gjennomført,
med en peker til den nye fila.

To punkter i mai-dokumentet var merket som åpne, men viste seg å være ferdig implementert
— hash-skip for identiske auto-backups (`core/backup/service.py`) og `/healthz/`
(`patients/health.py`). Begge er nå dokumentert som gjennomført.

### De mest konkrete nye funnene

- **N1** `next`-parameteren i innloggingen valideres ikke — åpen redirect til vilkårlig
  host rett etter vellykket innlogging
- **N2** `helsepersonell_ref` mangler i `felt_to_track` i audit-signalet. Endring av
  oppfølgingsansvarlig etterlater ingen spor, i strid med det personvernprotokollen lover
- **N3** `LOGGING` har ingen rot-handler. All INFO-logging — inkludert hver eneste
  vellykkede backup — forsvinner i stillhet, selv om RUNBOOK ber deg lete etter den
- **N4** MFA-skjemaene sender ingen `username`, så `key='post:username'` samler alle
  MFA-forsøk fra alle brukere i én bøtte: 10 per 5 minutter globalt. Ved vaktstart kan
  det låse ute folk som ikke har gjort noe galt
- **N5** `get_active_year()` og `Patient.save()` bruker fortsatt `datetime.now().year`.
  Samme feilklasse som ble ryddet i #20 — en nyttårsvakt etter midnatt lagrer pasienter i
  feil år
- **N9** De tre testene som skal beskytte dobbeltklikk-fixen leser `static/js/script.js`,
  som ingen mal laster lenger. De ville vært grønne selv om guarden forsvant fra den
  levende koden

### Sikkerhetspasset

- **S1** `/django-admin/` er en parallell innloggingsflate som omgår samtlige sikringer
  appen bygger rundt `accounts.views.login_view`: rate-limiting, kontosperre, MFA-tvang,
  tvungent passordbytte og `LoginEvent`-logging. Bak den ligger `Patient`, `CustomUser`
  og `AuditLog`. `OTPMiddleware` hjelper ikke — den setter `request.user.otp_device`, den
  håndhever ingenting
- **S2** `create_superuser` setter `must_change_password=False`, så bootstrap-adminen kan
  gå i årevis på deploy-passordet. Henger sammen med S1 og bør tas samtidig
- **S3** Rate-limiting finnes kun på innlogging — ingen struping på skriveendepunktene
- **S4** Lagret open redirect i varsel-visningen (`core/views.py:612`). Ikke utnyttbar i
  dag, men `notify()` er designet som generisk API for framtidige moduler
- **S5** Utlogging skjer via GET — en tredjepartsside kan tvinge utlogging
- **S6** MFA trust-cookie settes med `secure=True` i offline-modus, så nettleseren kaster
  den og «stol på denne enheten» virker ikke i felt

Dokumentet noterer også hva som ble kontrollert og funnet i orden, så det ikke revideres
på nytt: endepunktdekning, path traversal via backup-filnavn, audit-logging fra Django
admin, offline-modusens bevisste unntak og invalidering av MFA trust-cookien.

---

## 2026-08-12 — Backup samlet på én flate

Pasientmodulen hadde sitt eget backup-panel under Innstillinger, med egne
`/pasienter/api/backup/`-endepunkter. Det var to UI-er over samme backend: samme
`Backup`-tabell, samme filer på disk, samme `core.backup.restore_backup`.

**Det var ikke bare duplisering.** Panelets intervall-innstilling skrev til
`patients.BackupConfig` — den gamle singleton-modellen — mens scheduleren utelukkende
leser `core.ModuleBackupConfig`. Endret du intervallet der, skjedde ingenting. «Siste
automatiske backup» ble heller aldri oppdatert. Listen viste dessuten backuper fra alle
moduler blandet, uten å si hvilken modul de tilhørte.

- Fjernet de seks `/pasienter/api/backup/`-endepunktene med tilhørende URL-er
- Fjernet backup-panelet og ~130 linjer JS fra pasientmodulen
- Innstillinger lenker nå til `/portal-admin/backup/` i stedet
- `BackupAPITests` fjernet; portal-admin-flaten har allerede bedre dekning. Lagt til
  `test_run_view_requires_admin` for full paritet

536 tester, alle grønne.

Gjenstår som egne oppgaver (se TODO): den døde modellen `patients.BackupConfig` med
kommandoen `db_backup`, og `static/js/script.js` som ingen mal laster.

---

## 2026-08-12 — GDPR fase 3.1: arkiv kollapser til aggregat etter 24 måneder

Siste fase i GDPR-gjennomgangen. Arkiverte pasientrader slettes permanent etter 24
måneder og erstattes av den ferdig beregnede statistikken. Formålet — evaluering og
planlegging — er da uttømt, og art. 5(1)(e) tillater ikke at helseopplysninger på
radnivå blir liggende på ubestemt tid.

**Alt som vises i arkivvisningen bevares:** sammendrag, triagefordeling, ankomstkurve,
tidsstatistikk per gruppe, krysstabeller, kji-kvadrat og Kruskal-Wallis. Det som
forsvinner er enhver opplysning om enkeltpasienter. Etter kollaps kan ingenting i
arkivet føres tilbake til en person.

- Nye felt på `VaktArkiv`: `kollapset_at`, `aggregat` (JSON), `aggregat_sha256`
- `compute_arkiv_stats` / `compute_arkiv_full_stats` leser frosset aggregat når radene
  er borte — samme returstruktur, så grensesnittet er uendret
- Ny kommando `kollaps_arkiv` med `--dry-run`. Migrasjon `patients.0013`

### Integritetssjekk

`sha256` er beregnet over pasientradene og kan ikke verifiseres etter kollaps. Ved
kollaps beregnes en ny sjekksum over aggregatet, som overtar tuklingsdeteksjonen. Den
opprinnelige beholdes som historisk fingeravtrykk, men er ikke lenger etterprøvbar.
Arkiv-API-et eksponerer `kollapset` slik at grensesnittet kan skille tilstandene — et
arkiv som melder «ingen tukling» uten at noe faktisk sjekkes ville vært verre enn
ingen sjekk.

### Sikkerhetssperrer for en irreversibel operasjon

- Kommandoen nekter å kollapse med mindre det finnes en `arkiv`-backup tatt etter at
  arkivet ble opprettet. Fase 3.2 gjorde denne sperren mulig
- `--dry-run` viser nøyaktig hva som ville blitt slettet
- Hver kollaps loggføres i `AuditLog`
- Egen cron-jobb, ikke del av `purge_old_logs`: irreversibel sletting av helsedata skal
  ikke fyre som bieffekt av en loggopprydding

20 nye tester. 545 tester totalt, alle grønne.

Oppsettsinstruks for cron-jobben: `docs/OPPSETT_KOLLAPS_CRON.md` (midlertidig, slettes
når jobben er satt opp).

---

## 2026-08-12 — GDPR fase 3.2: arkivet som egen backup-modul

Tidligere var `VaktArkiv` ekskludert fra pasient-backupen mens `ArkivertPasient` ble tatt
med — barna uten forelderen. Det ga to problemer: en restore av pasientdata **feilet** på
fremmednøkkel dersom arkivet var slettet i mellomtiden, og arkivet kunne uansett ikke
gjenopprettes fra den backupen siden forelderen manglet. Null gjenopprettingsevne, bare
nedside.

- Ny `ArkivBackupHandler` (slug `arkiv`) med `VaktArkiv` + `ArkivertPasient` samlet
- Begge arkivmodellene ekskludert fra `PatientsBackupHandler`
- Egen `ModuleBackupConfig` via migrasjon `core.0005`: døgnintervall, cap 20.
  Arkivet endres bare når en vakt arkiveres, og innholds-hashen hindrer duplikater
- Vises som egen modul i `/portal-admin/backup/` med egen konfigurasjonsside

Motivasjonen er at Railways databasebackup kun er aktiv den måneden abonnementet er
oppgradert. Resten av året er dette den eneste dekningen arkivet har.

### Fallgruve avdekket underveis

Serialiseringen kjører med `natural_foreign=True`, så `VaktArkiv.importert_av` ble lagret
som brukernavnet. Var kontoen slettet, feilet **hele** gjenopprettingen med
`DeserializationError` — altså nøyaktig i scenarioet fase 4.1 nettopp gjorde mulig.

Løst med ny deklarativ `strip_fields` på `BaseBackupHandler`: angitte felter fjernes fra
dumpen før lagring. Arkiv-handleren utelater `importert_av`, siden brukernavnet uansett
ligger frosset i `importert_av_navn`. Mekanismen er generell og tilgjengelig for
framtidige moduler med FK-er som peker ut av eget datasett.

16 nye tester, blant annet at en pasient-restore nå går gjennom selv om et arkiv er
slettet, og at arkiv-restore virker etter at brukeren er borte. 525 tester, alle grønne.

---

## 2026-08-12 — GDPR fase 4.1: brukere kan slettes etter arkivering

`VaktArkiv.importert_av` hadde `on_delete=PROTECT`. En bruker som hadde arkivert en vakt
kunne dermed ikke slettes — databasen avviste med `ProtectedError`, og sletterett etter
GDPR art. 17 var blokkert på databasenivå. Med få admin-brukere merkes det ikke, men det
ville truffet ved første sletteforespørsel når frivillige får egen konto.

- Nytt felt `VaktArkiv.importert_av_navn`: frosset brukernavn som overlever brukersletting.
  Samme mønster som `ArkivertPasient.forstehjelper_navn` allerede brukte
- `importert_av` endret til `on_delete=SET_NULL, null=True`
- Migrasjon `0012` med datamigrasjon som fyller navnet på eksisterende arkiver
- Ny `VaktArkiv.importert_av_visning` brukes av `arkiv_liste_view` og `arkiv_detalj_view`.
  Begge leste tidligere `importert_av.username` direkte og ville fått `AttributeError`
  på `None` etter en sletting
- 8 nye tester: sletting fungerer, arkiv og pasientrader består, begge API-visningene
  overlever, og SHA-256-integritetssjekken påvirkes ikke

509 tester, alle grønne.

---

## 2026-08-12 — Testsuiten: 500 s → 15 s

Suiten brukte 8 minutter på 501 tester, noe som gjorde det upraktisk å kjøre den
under utvikling.

**Årsak:** Django-standarden PBKDF2 med 1 000 000 iterasjoner koster ~630 ms per hashing,
og suiten oppretter brukere og logger inn hundrevis av ganger. Alene stod dette for
mesteparten av kjøretiden — `accounts` brukte 141 s på 36 tester.

**Fiks:** `PASSWORD_HASHERS` settes til MD5 når — og bare når — `manage.py test` kjører
(`sys.argv[1] == 'test'`). Verifisert at gunicorn og `runserver` fortsatt bruker PBKDF2.

| | Før | Etter |
|---|---|---|
| `accounts` | 141 s | 0,9 s |
| Hele suiten | 504 s | 15,5 s |

Alle 501 tester fortsatt grønne.

**Dokumentasjonsfeil oppdaget underveis:** README og personvernprotokollen oppga
passord-hashing som «argon2 / pbkdf2». `argon2-cffi` er ikke i `requirements.txt`, så det
er PBKDF2 alene. Rettet begge steder. Argon2 kan aktiveres senere ved å legge til pakken.

---

## 2026-08-12 — GDPR fase 2: kodefikser

### Serverside-validering av kliniske felt (2.1)

- Ny `patients/choices.py` med kanonisk verdimengde for `problemstilling`, `arsak`,
  `transport`, `grovsortering`, `plassering`, `utskrevet_til`, `lege`, `medisiner` og `journal`
- `patient_create` og `patient_detail_view` avviser nå verdier utenfor mengden med HTTP 400.
  Tidligere ble verdiene skrevet rett inn fra request-body, slik at en klient som gikk utenom
  grensesnittet kunne lagre fritekst — i verste fall navn — i felt som skal være
  ikke-identifiserende
- Ny `patients/tests_choices.py` (15 tester), inkludert drift-vakt som leser `index.html` og
  feiler hvis skjemaet og hvitelisten kommer i utakt
- Testdata oppdatert: 48 plassholderverdier (`'A'`, `'Test'`, `'Båre 1'`, `'Hjem'`) byttet til
  reelle verdier. `journal='Oppfølging'` var en rest fra da feltet var en kategori

### Øvrige fikser

- **2.2:** `SECRET_KEY` hard-feiler ved oppstart med `DEBUG=False` hvis nøkkelen mangler eller er
  en kjent eksempelverdi. Tidligere falt den stilltiende tilbake på en hardkodet utviklingsnøkkel
- **2.3:** `purge_old_logs` sletter nå også varsler eldre enn 30 dager, med egen
  `--notification-days`. 5 nye tester
- **2.4:** Fjernet dødt `GET /api/archives/` med tilhørende UI-seksjon og JS. Endepunktet listet
  JSON-filer i `arkiv/`, men ingenting skrev slike filer; mappa lå dessuten på containerens
  flyktige disk på Railway. Rest fra Flask-tiden

### Windows-fiks (nødvendig for å kunne kjøre testene lokalt)

- `core/middleware.py` importerte `resource` ubetinget — en Unix-modul. Siden middlewaren står i
  `MIDDLEWARE`, feilet **hver eneste HTTP-test** på Windows. Importen er nå betinget, og
  minnelogging degraderer til ren responstid-logging der modulen mangler. Linux-oppførselen
  er uendret

Hele suiten: 501 tester, alle grønne.

---

## 2026-08-12 — GDPR-gjennomgang: protokoll v1.5

### Rettslig grunnlag omskrevet

- Avklart at systemet **ikke** er et behandlingsrettet helseregister. Journalføring skjer i eksternt
  system; feltet `journal` er kun et Ja/Nei-flagg som registrerer om journal er ført der
- Helsepersonelloven §§ 39–40 og pasientjournalloven fjernet som rettslig grunnlag
- Art. 6(1)(d) + art. 9(2)(h) står igjen, med taushetspliktvilkåret i art. 9(3) dokumentert

### Lagringstider korrigert som følge av bortfalt journalplikt

- Audit-logg: 10 år → **2 år**. Dokumentet samsvarer nå med det `purge_old_logs` faktisk håndhever
- Arkiverte pasientrader: **24 måneder**, deretter kollaps til aggregert statistikk *(planlagt)*
- Varsler: **30 dager** *(planlagt)*
- Backup: «72 timer» var feil — oppryddingen er antallsbasert (`max_backups`, standard 50).
  `RETENTION_HOURS` er død kode

### Nye kategorier og behandlinger dokumentert

- `VaktArkiv`, `ArkivertPasient` og `core.Notification` lagt inn i A.6
- Railway databasebackup lagt inn som egen behandling i A.2, med presisering av at den omfatter
  hele databasen — i motsetning til modul-backupen

### Vurderinger dokumentert (art. 5(2))

- Fravalg av innsynslogg, med begrunnelse
- Fravalg av begrenset lesetilgang («Mine pasienter» som tilgangsgrense)
- DPIA vurdert som ikke påkrevd
- Korrigert påstanden om at fritekst-risiko er «eliminert» — verdimengden håndheves foreløpig
  kun i grensesnittet, ikke i API-et

### Øvrig

- Ny **Del B.8**: informasjon til appbrukere (frivillige og helsepersonell), som manglet helt
- Merknad i A.1 om at behandlingsansvaret ligger hos privatperson
- Kjent begrensning dokumentert: `VaktArkiv.importert_av` (`PROTECT`) blokkerer sletting av brukere
- Dokumentasjonen konsolidert: `PERSONVERN_DOKUMENTASJON.md`, `TEKNISK_DOKUMENTASJON.md` og
  `RUNBOOK_VAKT.md` bor nå kun i `docs/`. Kopiene i rot var nyest og er flyttet dit; de utdaterte
  `docs/`-versjonene er overskrevet
- Ny `docs/GDPR_TILTAKSPLAN.md` med gjenstående faser

---

## 2026-06-23 — Python 3.13 + arbeidsflyt-regel

### Oppgradering til Python 3.13

- `runtime.txt` satt tilbake til `python-3.13` (var utilsiktet flippet til `3.12` i fase-3a-commit `75258f8`)
- Matcher miljøet pasientregistrering kjører på Railway — én færre variabel ved kommende repo-bytte på Railway
- Ingen avhengigheter er pinnet til 3.12; `requirements.txt` uendret

### Ny arbeidsflyt-regel

- `CLAUDE.md`: alle endringer som skal commites/pushes skal oppdatere CHANGELOG og TODO i forkant (samme commit)

---

## 2026-05-25 — Behandler → Førstehjelper + Mine pasienter

### Rename: Behandler → Førstehjelper (Fase 6)

- `Behandler`-modellen omdøpt til `Forstehjelper` i kode, database og UI
- Django-migrasjon med `RenameModel` + `RenameField` — ingen tap av data
- API-endepunkt `/api/behandlere/` → `/api/forstehjelpere/`
- `UserPatientLinkForm` erstattet av `PasientRolleForm` — enkel radio (Ingen / Førstehjelper / Helsepersonell) i brukeradmin
- Alle JS-moduler, templates, tester og admin oppdatert (~250 forekomster)
- 475 tester, alle grønne

### «Mine pasienter» — listevisning

- Endret fra checkbox/toggle til filterknapp i rekken med Alle / Rød / Gul / osv.
- Eksklusivt filter (ikke kombinerbart); klikker man en annen — nullstilles «mine»
- Server-side filtrering via `?mine=1` bevart; localStorage-persistering fungerer

### «Mine pasienter» — tavle

- Ny knapp ved siden av «Ny pasient» i tavle-visningen
- Viser alle pasienter, men dimmer (opacity + desaturate) pasienter som ikke er dine
- Ledige plasser («Ledig») påvirkes ikke

### Diverse UI

- Spacing-fix: «Ny pasient»-knappen har nå riktig avstand ned til sonene i tavlen

---

## 2026-05-16 — Mørkt tema konsolidert

### Designstrategi

Portalen bruker nå et konsistent mørkt tema på alle sider — i harmoni med pasientregistrerings-appen. Prinsipp fremover: `portal.css` styrer all theming globalt; templates bruker bare Bootstrap-klasser og `--portal-*`-variabler, ingen inline `background:` eller `color:` for standard innholdsbokser.

### `portal.css` — utvidet til komplett dark-theme grunnmur

- **`.card`**: mørk bakgrunn (`--portal-surface`), synlig border (`--portal-border`), lys tekst
- **`.card-header/.card-footer`**: mørkere bakgrunn (`--portal-surface-2`)
- **`.table td, .table th`**: eksplisitt `color: var(--portal-text)` — fikser svart tekst i alle tabellceller inkl. `<strong>`-elementer
- **`code`**: lyseblå farge (`--portal-accent`) med svak blå bakgrunn — erstatter Bootstrap sin knallrosa standard (`#d63384`)
- **`.pagination`**: dark-theme for alle fremtidige pagineringselementer
- **Kommentar**: oppdatert til å reflektere faktisk innhold

### `base_portal.html` `:root` — Bootstrap-tokens

- `--bs-body-bg`, `--bs-body-color`, `--bs-border-color` lagt til — gir Bootstrap-utilities korrekte mørke verdier og synlig kortkant mot mørk sidefarge

### Global dato/klokkeslett

- **`portal-clock.js`**: Ny dedikert fil med `updateClock()` — viser norsk dag, dato og tid (oppdateres hvert sekund)
- **`base_portal.html`**: `#header-dt`-element lagt til i headeren (mellom varselbjelle og avatar) — klokken vises nå på alle portal-sider
- **`script.js`**: `DAYS_NO` og `updateClock()` fjernet — dekkes nå globalt av `portal-clock.js`

### Template-opprydding

- **`module_admin_list.html`**: redundante inline-stiler på `<table>` og `<thead>` fjernet — portal.css håndterer dette globalt
- **`audit_log_list.html`**: 5 duplikate CSS-regler fjernet fra `{% block extra_head %}`; `.pagination`-regler flyttet til portal.css; audit-spesifikke regler beholdt

---

## 2026-05-15 (sesjon 2)

### CSS-gjennomgang og fremtidssikring

- **Bootstrap dark-theme tokens**: `--bs-body-color`, `--bs-body-bg` m.fl. overstyrt i `:root` slik at alle Bootstrap text-/bg-utilities automatisk fungerer mot portalens mørke bakgrunn
- **`portal.css`**: Ny fil for Bootstrap dark-theme overrides (`.text-muted`, `.card`, `.table`, `.form-control`, `.alert-*`). Erstatter inline CSS-blokk i `base_portal.html`
- **CSS-variabel-aliaser**: `--surface-1`, `--border-color` m.fl. aliasert til `--portal-*` for bakoverkompatibilitet
- **4 accounts-templates migrert**: `change_password.html`, `user_form.html`, `user_detail.html`, `ratelimited.html` byttet fra `base.html` til `base_portal.html`
- **Kortbakgrunn-fix**: `--bs-table-bg: transparent` lagt til i `.table`-regel — forhindrer at Bootstrap tildekker kortets bakgrunnsfarge med sidefarge

### Prosjektstruktur

- 14 historiske `.md`-filer flyttet til `docs/`-mappe
- `CHANGELOG.md` og `TODO.md` opprettet i roten

481 tester, alle grønne.

---

## 2026-05-15 (sesjon 1)

### URL-rydding: server-status flyttet

- Kanonisk URL endret fra `/pasienter/admin/server-status/` → `/portal-admin/server-status/`
- Bakover-kompatible redirects (301) bevarer gamle URL-er
- 4 hardkodede `fetch()`-URL-er i `admin_status.html` erstattet med Django `{% url %}`-tags via `ADMIN_URLS`-objekt
- Middleware-skiplist, tester (~30 referanser) og legacy-redirect i `core/urls.py` oppdatert

### Visuell konsistens

- **Server-status**: CSS-variabler (`--surface-1` etc.) byttet til `--portal-*`-varianter etter template-bytte
- **Portal-header**: Brukernavn og rolle-badge fjernet fra headeren, vises nå kompakt øverst i dropdown
- **Admin-nav**: «Brukere»-lenke lagt til for admin-brukere
- **Pasientmodul-dropdown**: «Min profil»-lenke lagt til

### Testresultat

481 tester, alle grønne.

---

## 2026-05-14 (tidligere sesjon)

### Fase 5: Bruker-behandler-kobling + varselbjelle

- Behandlere og helsepersonell kan kobles til brukerkonto
- Generisk varsel-bjelle implementert med deduplisering (24t-vindu)
- `script.js` delt opp i 4 moduler: `patients-utils.js`, `patients-table.js`, `patients-forms.js`, `patients-stats.js`
- `accounts/users/` og `admin_status.html` byttet fra `base.html` til `base_portal.html`
