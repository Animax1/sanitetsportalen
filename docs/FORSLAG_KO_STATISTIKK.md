# Forslag: statistikk fra KO — pulje 7

*Skrevet 21. sep. 2026 på bestilling fra André: «Ut ifra alt vi genererer av data i /ko, hva
er interessant å få hentet ut? Det blir brukt til sanitetsvakter av stor profesjonell
karakter med våre egne ambulanser og lege.» Kontrollert mot koden samme dag — hver rad under
peker på feltet eller systemlinja tallet regnes av. Et **forslag**; ingenting er bygget.*

## 1. Hva vi faktisk sitter på

Det som finnes i dag, og som ingen statistikk leser ennå:

| Kilde | Felt som bærer et tall |
|---|---|
| `ko.Hendelse` | prioritet (6), lokasjon, melder (flere), `opprettet_at`, `lukket_at`, deltakere |
| `ko.HendelseLag` + systemlinjene `hendelse_lag_paa`/`_av` | hvilket lag, fra når, til når |
| Systemlinjene `hendelse_prioritet`, `hendelse_gjenapnet`, `oppdrag_knyttet` | eskaleringer, gjenåpninger, når et oppdrag kom til hendelsen |
| `ko.Logglinje` (operatør) | tidspunkt, ansvarsområde, chat/formell, rettet (`korrigerer`), fjernet, festet, **delt** (`delt_at`, `Linjedeling`) |
| `oppdrag.Oppdrag` | `hendelse`, `trenger_ressurs_siden`, grovsortering (4 verdier), hastegrad (5), problemstilling, antall |
| `oppdrag.Statusmelding` | tidspunkt per status, `sted` + `sted_tekst` ved Avreist, `forsinket` (offline), `manuell` (KO-ført), `automatisk` |
| `oppdrag.Enhetshendelse` | avbrutt, avventer, tatt av, rykket videre |
| `oppdrag.Oppdragsenhet` | `varslet_at`, `varslet_modus` (passiv) per enhet |
| `vaktliste.Vaktpost` | hvem var på vakt når, møtt/ikke møtt, lag på vakt |

Oppdragsfanen har alt responstid, ventetid, utrykningstid, tid på stedet, oppdragstid,
fordelinger per hastegrad/problemstilling/lokasjon/enhet og ankomster per time. Det står
ikke to ganger her — forslaget legger til det den ikke svarer på.

## 2. Forslaget, i fire lag

### A. Hendelsesbildet (ny fane «KO»)

Dette er det bare KO kan svare på, og det notatet §8 lovte.

| # | Tall | Regnes av | Hvorfor det er interessant |
|---|---|---|---|
| A1 | Hendelser per vakt: antall, per prioritet, per lokasjon, per melder | `Hendelse` | Grunnlaget. «Hvor mange Viktig hadde vi, og hvor kom de fra» |
| A2 | Varighet per hendelse (opprettet → lukket), median og p90 per prioritet | `opprettet_at`, `lukket_at` | Hvor lenge binder en Rød hendelse KO |
| A3 | **Tid til første ressurs**: hendelse opprettet → første oppdrag på hendelsen → første «Rykker ut» → første lag satt på | `oppdrag_knyttet`, `Statusmelding`, `HendelseLag.fra` | Den ene KO-responstiden som ikke finnes i oppdragsfanen: oppdragets klokke starter når oppdraget lages, hendelsens når KO hørte om det |
| A4 | Ressursbruk per hendelse: oppdrag, enheter, **lagtimer** (sum fra → av) | `Oppdrag.hendelse`, `HendelseLag`, `hendelse_lag_av` | Hva en hendelse *kostet* i ressurser, ikke bare hvor lenge den sto |
| A5 | **Hvem løste hendelsen** (André, 21. sep.): hver lukkede hendelse legges i én av fire ruter — *lag og oppdrag*, *bare lag*, *bare oppdrag*, *verken* — per prioritet, **uten Drift og Plassering** (de er bestillinger, ikke hendelser som «løses») | `Oppdrag.hendelse`, systemlinja `hendelse_lag_paa` (raden i `HendelseLag` slettes når laget tas av, loggen står) | «Bare lag» er argumentet for lag på vakt. «Verken» er de KO løste fra bordet — telefon, vakter, publikum selv — og en **Rød eller Viktig i den ruta listes med navn**, ikke bare telles: enten var prioriteten for høy, eller så gjorde noen andre jobben. «Lag og oppdrag» får med tida fra lag på til oppdrag knyttet — eskaleringskjeden |
| A6 | Eskaleringer: fra → til-matrise, og hvor lang tid etter opprettelse | `hendelse_prioritet` (`fra`/`til` i `systemdata`) | «Startet som Gul, ble Rød etter 12 min» er læring til neste vakt |
| A7 | Gjenåpninger | `hendelse_gjenapnet` | Få, men hver er et spørsmål |
| A8 | **Samtidighet**: åpne hendelser per klokketime, og toppen | `opprettet_at`/`lukket_at` | Belastningskurven for KO. Sammen med D1 sier den om bemanningen traff |

### B. Loggen og KO-arbeidet

Tall om *hvordan* KO jobbet, ikke om pasientene. Nyttig i gjennomgangen etterpå.

| # | Tall | Regnes av | Hvorfor |
|---|---|---|---|
| B1 | Linjer per time (operatør og system hver for seg), per ansvarsområde | `Logglinje` | Tempoet i KO over døgnet, og hvem som hadde trykket |
| B2 | Rettinger og fjerninger: antall, og tid fra registrering til retting | `korrigerer`, `fjernet_at`, `registrert_at` | Kvalitet på føringen. Mange rettinger sent er et tegn på at noe ble ført i etterkant |
| B3 | Deling: andel av hendelseslinjer som ble delt, og tid fra skrevet til delt | `delt_at`, `Linjedeling` | Hvor mye av det KO visste nådde bilene, og hvor fort |
| B4 | **Stillhet**: lengste hull uten operatørlinje mens minst én hendelse var åpen | `Logglinje.tidspunkt` × A8 | Det hullet er der spørsmålene kommer i en gjennomgang. Vises som liste, ikke bare et tall |
| B5 | KO-førte og forsinkede stemplinger | `Statusmelding.manuell`, `.forsinket` | Datakvalitet på responstidene: hvor mange av dem ble ført av KO i etterkant, og hvor mange kom fra en bil uten dekning |

**Ikke per operatør, per ansvarsområde.** Linjer per person er et arbeidsmiljøspørsmål og
ikke et driftsspørsmål; tallene vises per ansvarsområde og per time. Navnene står i loggen
om noen trenger dem.

### C. Oppdragsfanen utvidet

Data som finnes i oppdragsmodulen, men som ingen leser. Hører hjemme i den fanen som alt
finnes, ikke i KO-fanen.

| # | Tall | Regnes av | Hvorfor |
|---|---|---|---|
| C1 | **Avreist til**: fordeling per sted, kryss mot hastegrad; «Annet sted»-tekstene listet | `Statusmelding.sted`, `sted_tekst` | Transportmønsteret — hvor mange gikk til sykehus mot legevakt mot samleplass. Med egen lege er andelen som *ikke* går videre selve poenget |
| C2 | **Triagekonkordans**: KOs hastegrad × bilens grovsortering | `hastegrad`, `grovsortering` | Hvor ofte var bilens vurdering høyere eller lavere enn meldingen KO fikk. Ikke en fasit — to vurderinger fra to ståsteder — men avviket over mange vakter sier noe om meldekvaliteten |
| C3 | Behandlet på sted / Utført / transportert, per problemstilling | sluttstatus-veien (`behandlet_at` mot `leverer_at`) | Andelen løst på stedet er tallet legen vil ha |
| C4 | **Ventetida delt i to** (André, 21. sep.). Dagens «ventetid» er opprettet → Rykker ut, og blander to ting: **KO-ventetid** — fra oppdraget står uten ressurs til en enhet varsles — og **reaksjonstid** — fra enheten er varslet til hun stempler Rykker ut. Begge som median/p90 per hastegrad; reaksjonstid også per enhet, med passiv vakt for seg (`varslet_modus`) | `created_at` / `Enhetshendelse.rykket_videre` → første `Oppdragsenhet.varslet_at` (KO-ventetid); `varslet_at` → `RYKKER_UT` på samme koblingsrad (reaksjonstid) | Den ene er KOs tall, den andre er bilens. Summert blir de dagens ventetid, så ingenting går tapt — men «vi ventet 9 min» blir til «KO brukte 6 på å finne bil, bilen 3 på å rykke». `trenger_ressurs_siden` tømmes når en ny enhet varsles, så historikken rekonstrueres fra `rykket_videre`-hendelsen, ikke fra flagget |
| C4b | **Køen**: oppdrag uten ressurs *og* tildelte som fortsatt venter, per klokketime — antall og lengste ståtid akkurat da | C4 × tidsaksen | Kurven som sier om det var for få biler, og *når*. D1 legger bemanningen under den |
| C4c | **Tildelt, men rykket aldri ut**: koblingsrader som gikk fra Venter rett til avbrutt/tatt av, og hvor lenge de sto | `Enhetshendelse` uten `RYKKER_UT` på raden | Hver er en bil som ble bundet uten å gjøre noe — enten en feiltildeling eller en bil som ikke svarte |
| C5 | Avbrytelser, avventinger, rykket videre, tatt av: antall og per enhet | `Enhetshendelse` | Hvor ofte måtte et oppdrag bemannes på nytt |
| C6 | **p90** ved siden av median på alle varigheter | eksisterende `_sd` | «90 % av akutte hadde bil fremme innen 7 min» er setningen som kan stå i en rapport; snittet dras av ett utlegg |
| C7 | Enhetsutnyttelse: oppdragstid som andel av bemannet tid, og lengste ledigtid, per enhet | `Statusmelding` × `Vaktpost` på enhetens ressurs | Var det for få biler, eller for mange |
| C8 | **Alle fem hastegradene** i fanen (André, 21. sep.: «det mangler en hastegrad»). Kontrollert: `per_hastegrad` sorteres på antall, ikke i AMK-rekkefølge, og fargekartet i `statistikk-oppdrag.js` kjenner fire — «Plassering» faller til grå | `choices.HASTEGRAD` er fasit | Rekkefølgen og fargene skal komme fra én liste, ikke stå på nytt i JS-en. Tas først i 7b |

### D. Belastning mot bemanning (KO + vaktlista)

| # | Tall | Regnes av | Hvorfor |
|---|---|---|---|
| D1 | Per klokketime: personer på vakt (møtt), lag på vakt, åpne hendelser, oppdrag opprettet | `Vaktpost` × A8 × `Oppdrag.created_at` | Én graf som svarer på «var vi bemannet der trykket kom» |
| D2 | Oppdrag per bemannet time | D1 | Det eneste normaliserte tallet vi kan lage uten publikumstall |
| D3 | Lag: hendelser per lag, tid på hendelser per lag | `HendelseLag` | Hvilke lag som sto i det, og hvor lenge |

Retningen er `ko` → `vaktliste` (lov) og `ko` → `oppdrag` (lov). Statistikkappen navngir
ingen kilde; KO-handleren regner, og henter vaktlistas tall gjennom `vaktliste.services`.

## 3. Statistiske analyser som er verdt det — og de som ikke er

**Verdt det:**

- **Median, p90 og IQR framfor snitt** på alle varigheter. Varigheter er skjeve; ett oppdrag
  som sto to timer gjør snittet meningsløst. `_sd` utvides med `p90` og `p25`/`p75`; samme
  form på begge fanene.
- **Krysstabeller** der to vurderinger møtes: hastegrad × grovsortering (C2), prioritet ×
  «løst uten utrykning» (A5), sted × hastegrad (C1). Tallet er andelene i cellene, ikke en
  test.
- **Tidsserier per klokketime** (A8, B1, D1) som stolper med samme tidsakse, så de kan
  legges over hverandre.
- **Sammenligning mellom vakter**: én tabell med nøkkeltallene per vakt (A1, A2-median,
  A3-median, C4, C6, D2). KO-loggen og hendelsene ligger i 730 dager, så det trengs ikke
  noe arkiv — `full_stats(vakt)` for hvilken som helst vakt.

**Ikke verdt det nå:**

- Signifikanstester og konfidensintervall. Én vakt er 20–60 oppdrag; tallene beskriver, de
  beviser ikke. Det bør stå i fanen: «Tallene beskriver denne vakta.»
- Prognoser («forventet antall oppdrag kl. 22»). Krever et titalls sammenlignbare vakter.
  Kan komme av sammenligningstabellen den dagen den har ti rader.
- Normalisering per publikum. Vi har ikke tallet. **Spørsmål til André:** skal vakta få et
  felt «forventet publikum» i portalinnstillingene? Da får D2 selskap av «oppdrag per 1 000».

## 4. Det som bærer regelen fra §8

**Tre registre teller kontakter, ikke personer.** Pasientmodulen, oppdragene og hendelsene
er tre målinger av tre ting; summert blir 210 mennesker til 340 rader. Overskriftene i
KO-fanen skal si «hendelser», «oppdrag» og «registreringer», aldri «pasienter», og det
skal stå én setning øverst som sier hvorfor. Det er det eneste som hindrer feilen.

## 5. Andre nyttige visninger

- **Vaktas tidslinje** (Gantt): hendelsene som stolper i prioritetsfarge, oppdragene som
  stolper inni, lag som striper. Ett bilde av hele vakta — det man vil ha på veggen i
  gjennomgangen. Regnes av A4 og A8; tegnes i Chart.js, som alt lastes på siden.
- **Varmekart lokasjon × time** for hendelser og oppdrag. Ingen kart, lokasjonene har ikke
  koordinater — men et rutenett med lokasjonene som rader er nok.
- **Vaktrapport**: KPI-ene fra A, C og D pluss topplistene, server-rendret for utskrift.
  Samme rader som utskriften av loggen (TODO) trenger — de to bør bygges sammen.
- **Live-stripe på `/ko/`**: «nå: 3 åpne hendelser · 1 oppdrag uten ressurs · median
  responstid i kveld 6 min». Leser samme handler, cachet 60 s som resten.

## 6. Hull i dataene, sagt nå og ikke etterpå

- **Lag av hendelse**: `HendelseLag`-raden slettes når laget tas av; tidspunktet står i
  systemlinja `hendelse_lag_av`. A4 og D3 leser derfor loggen. Holdbart, men skjørt — et
  `til`-felt på raden (soft delete) er en liten migrasjon og bør tas i pulje 7.
- **Enhet på/av vakt** er ikke tidsstemplet i oppdragsmodulen (bare `passiv` er). C7 bruker
  vaktlistas skift på enhetens ressurs; en bil uten kobling til vaktlista får ingen
  utnyttelsesgrad, og det skal stå «ukjent», ikke 0.
- **Ingen kobling person ↔ oppdrag ↔ hendelse**, med vilje (§8). Ingen tall krysser
  registergrensene.
- **Publikumstall** finnes ikke (§3).

## 7. Puljer

| Pulje | Innhold | Avhenger av |
|---|---|---|
| 7a | `ko/statistikk.py`: A1–A8, B1–B5; fanen «KO» med `statistikk-ko.js`; p90 i `_sd` | `HendelseLag.til` (liten migrasjon) |
| 7b | **Bygget 21. sep. 2026.** Oppdragsfanen utvidet: C8, C1–C6 med C4/C4b/C4c. C7 venter på 7c | ingenting |
| 7c | D1–D3 og C7: vaktlista inn | at vaktlistas ressurser er koblet til enhetene |
| 7d | Sammenligning mellom vakter, tidslinja og vaktrapporten | 7a–7c, og utskriften i TODO |

Hver pulje gir én fane eller én blokk som kan leses alene. 7a og 7b er uavhengige og kan gå
i hver sin økt.

## 8. Spørsmål til André før koden

1. Er det noe i A–D som **ikke** er interessant? Det billigste er å la det være.
2. **Per ansvarsområde, ikke per person** i B — enig?
3. Skal vakta få et felt for **forventet publikum**, så vi får «per 1 000»?
4. C2 heter «triagekonkordans» her — hva vil dere kalle det på skjermen? Ordet skal ikke
   lyde som en karakter på bilen.
5. Sammenligning mellom vakter: er det de siste *n* vaktene, eller velger man selv?
6. ~~Hastegraden som mangler (C8)~~ — begge fikk alle fem (21. sep.).

**Valgt 21. sep. 2026, fra skissene:** ventetida som både stolper og tabell (S1 A+B), «hvem
løste hendelsen» som tabell (S4 A), navnet «Meldt hastegrad (KO) × bilens grovsortering».
Spørsmål 2, 3 og 5 står åpne.
