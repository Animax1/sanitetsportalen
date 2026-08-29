# Beslutningsnotat: vaktlistemodulen

Status: **utkast 29. aug. 2026.** Bestilt av André samme dag. Avklaringene i §11 er
ikke besvart ennå — notatet er skrevet for å gjøre dem mulige å svare på.

Modulen er den mest sentrale som er foreslått så langt: den beskriver *hvem som er på
vakt*, og både pasientmodulen og oppdragsmodulen har hittil måttet gjette på det.
Notatet må ligge før første linje kode, av samme grunn som oppdragsnotatet måtte:
tilgangsmodellen og personvernet er ikke ting man setter på etterpå.

---

## 1. Hva modulen skal løse

Fire ting, slik de ble bestilt:

1. **Oversikt over personellet** — sortert på korps, med kompetanse, rolle under vakt
   og kostbehov. Korps, kompetanse, rolle og kostbehov skal vedlikeholdes av admin,
   ikke ligge i kode.
2. **Bemanning av vaktas ressurser** — samleplass (sykestua), mannskapsbil,
   ambulanse, lag, KO, og det vakta ellers måtte kreve. Faner i grensesnittet.
3. **Planlegging som blir drift** — lista settes opp på forhånd, settes i drift når
   vakta starter, og brukes da til å registrere *møtt* og *av vakt*. Den må fortsatt
   kunne endres under drift; folk bytter og folk uteblir.
4. **Kobling til `/oppdrag`** — operatøren trykker på en enhet og ser hvem som er på
   bilen, og om de har sjekket seg inn.

Og én ting til, som er den som styrer mest av utformingen:

5. **To skiller i skrivetilgangen.** En bruker fra korps Z skal kunne redigere korps
   Z og legge til folk der, men ikke røre andre korps. En bruker med universell
   skrivetilgang redigerer alle. Global admin har alt.

---

## 2. Ordbok — fire ord som ligner på hverandre

Dette er notatets viktigste avsnitt. Portalen har allerede et `Vakt`-begrep, og
oppdragsmodulen har allerede en `Enhet`. Uten en fast ordbok kommer vi til å skrive
kode der «vakt» betyr tre ting i tre filer.

| Ord | Betyr | Hvor |
|---|---|---|
| **Vakt** | Arrangementet/perioden. Portalens scope siden deploy 2 | `core.Vakt` — finnes |
| **Vaktliste** | Personelloppsettet for **én** vakt | ny: `vaktliste.Vaktliste` |
| **Ressurs** | Det som bemannes: samleplass, bil, lag, KO | ny: `vaktliste.Ressurs` |
| **Vaktpost** | Én person på én ressurs, med rolle og tider | ny: `vaktliste.Vaktpost` |
| **Mannskap** | Personen i registeret | ny: `vaktliste.Mannskap` |
| **Enhet** | Bilen slik oppdragsmodulen kjenner den | `oppdrag.Enhet` — finnes |

En **Ressurs** og en **Enhet** kan være samme fysiske bil. De er likevel to rader,
fordi de svarer på ulike spørsmål: enheten er *noe 113 tildeler oppdrag til*,
ressursen er *noe som bemannes*. Koblingen mellom dem er §6.

---

## 3. Modellene

```
Korps            navn, kortnavn, er_aktiv, rekkefolge
Kompetanse       navn, er_aktiv, rekkefolge          # «Sanitetsvakt», «Ambulansearbeider», «Sykepleier», «Lege», «Sjåfør kode 160» …
VaktRolle        navn, er_aktiv, rekkefolge          # «Lagleder», «Fagleder helse», «KO-operatør», «Sjåfør» …
Kostbehov        navn, er_aktiv                      # se §7 — dette feltet er ikke som de andre

Mannskap         navn, korps→Korps, kompetanser M2M, kostbehov M2M,
                 telefon, user→CustomUser (valgfri), er_aktiv, notat

Vaktliste        vakt→core.Vakt (1:1), status, satt_i_drift_at/av
Ressurs          vaktliste→Vaktliste, navn, type, rekkefolge,
                 enhet→oppdrag.Enhet (valgfri, §6)
Vaktpost         ressurs→Ressurs, mannskap→Mannskap, rolle→VaktRolle,
                 fra_tid, til_tid, mott_at, av_vakt_at, avmeldt_at, merknad
```

Fire ting er verdt å begrunne:

**`Korps`, `Kompetanse`, `VaktRolle` og `Kostbehov` er tabeller, ikke `choices.py`.**
Motsatt av oppdragsmodulen, der problemstilling og hastegrad ligger i kode. Skillet
er det samme som mellom `PROBLEMSTILLING` og `Lokasjon`: faglige verdimengder som
endres sjelden hører i kode, arrangements- og organisasjonsdata i basen. Korpsene og
kompetansenivåene er organisasjonens, ikke portalens — og bestillingen sier eksplisitt
at admin skal styre dem.

**`Mannskap` er et personregister, og det er nytt for portalen.** Se §9 om forholdet
til `Forstehjelper` og `Helsepersonell`.

**`Vaktliste` er 1:1 med `Vakt`.** Én vakt, én liste. Alternativet — flere lister per
vakt — løser ingenting bestillingen beskriver, og gjør «hvem er på vakt nå» til et
spørsmål med flere svar.

**`Vaktpost` bærer tidene, ikke `Mannskap`.** Møtt og av vakt gjelder *denne* vakta.
Legges de på personen, kan hun bare være på vakt ett sted, én gang.

---

## 4. Tilgangsmodellen — den ene virkelig nye mekanismen

Portalens rollemodell har **én akse**: en ordnet stige per modul
(`les < skriv_handling < skriv_full`). Bestillingen her introduserer en **andre akse**:
*hvilke rader* du får skrive til, ikke bare *hva* du får gjøre.

Det er nettopp den sammenblandingen `docs/BESLUTNING_ROLLEMODELLEN.md` advarte mot —
statistikk ble skilt ut som egen modul for å slippe å ha to akser i én. Så dette må
gjøres bevisst, ikke ved å presse et scope inn i et nivånavn.

### 4.1 Anbefalt: scopet utledes av hvem du er

Stigen for denne modulen blir:

| Nivå | Betyr |
|---|---|
| `les` | Ser hele lista, alle korps |
| `skriv_korps` | Kan redigere mannskap og vaktposter **i sitt eget korps** |
| `skriv_full` | Kan redigere alle korps |

Korpset kommer fra brukerens egen `Mannskap.korps` — altså fra domenedata, ikke fra
en tilgangsrad. Det er **samme idiom som oppdragsmodulen allerede bruker**: der
avgjøres det av `Enhet.user` om kontoen får enhetsskjermen eller sentralbordet, og den
koblingen gir i seg selv ingen tilgang.

Fordelen er at nivået betyr noe alene. `skriv_korps` er en fullstendig setning: «du kan
redigere ditt eget korps». Ingen ekstra tabell å glemme å fylle ut.

Prisen er to kanter som må stå i koden, begge fail-closed:

- En konto med `skriv_korps` som **ikke** er koblet til et mannskap har intet korps, og
  kan dermed ikke skrive noe. Samme form som en enhetskonto uten enhet.
- Skal noen administrere **to** korps, holder ikke modellen. Da er svaret `skriv_full`,
  eller et eksplisitt tillegg senere (§11.3).

`les` gjelder hele lista med vilje: poenget med en vaktliste er samordning på tvers av
korps. Den som ikke skal se andre korps, skal ikke ha modulen.

### 4.2 Alternativet: en egen tildelingstabell

`Skrivetilgang(bruker, korps)` der en rad uten korps betyr «alle». Mer fleksibel — den
løser to-korps-tilfellet gratis — men den innfører et nivå (`skriv_full`) som ikke gir
noe uten en rad ved siden av. Modulnotatet for rollemodellen kaller nettopp det ut:
*«et nivå som ikke gir noe er lett å dele ut i god tro»*.

**Anbefaling: 4.1.** Den er enklere å forklare, og to-korps-tilfellet kan løses den
dagen det faktisk finnes.

### 4.3 Ny verdi i den delte stigen

`skriv_korps` må inn i `NIVAA_HIERARKI` i `core/auth_decorators.py`, mellom `les` og
`skriv_full`. Det er en delt konstant, men `Module.nivaaer` styrer hva som *tilbys* per
modul, så ingen annen modul påvirkes. Samme grep som da `skriv_handling` kom.

---

## 5. Livsløp: planlegging → drift

```
planlegging ──(admin/skriv_full)──▶ drift ──▶ avsluttet
```

- **Planlegging.** Ressurser opprettes, folk plasseres. Ingen møtt/av vakt-felter er i
  bruk. Lista kan endres fritt.
- **Drift.** Møtt og av vakt registreres. Lista kan **fortsatt** endres — folk uteblir
  og bytter, og en liste som låser seg i det vakta starter er en liste som forlates til
  fordel for et ark.
- **Avsluttet.** Settes ved arkivering (§10, fase 6).

**Overgangen er én vei, og den er en handling, ikke en dato.** Et klokkeslett som
utløser drift ville truffet feil den dagen vakta starter to timer forsinket.

**Planlegging krever en vakt som ennå ikke er aktiv.** I dag lages `Vakt`-rader på to
måter: lat opprettelse for inneværende år, og «Avslutt vakt» som lager den neste.
Ingen av dem lar deg planlegge oktobervakta i august. Modulen trenger derfor
«Ny planlagt vakt» — en `Vakt` med `er_aktiv=False` som ikke rører portalens peker.
Det er en liten utvidelse av vaktadministrasjonen, og den hører til fase 2.

Hvorvidt «Sett i drift» også skal **bytte portalens aktive vakt** er §11.2.

---

## 6. Koblingen til `/oppdrag`

`Ressurs.enhet` er en nullbar FK til `oppdrag.Enhet`. Er den satt, er ressursen den
bilen — og da kan sentralbordet vise besetningen.

**Avhengighetsretningen går én vei: `vaktliste` → `oppdrag`.** Oppdragsmodulen skal
ikke importere vaktlista. Sentralbordet henter i stedet
`/vaktliste/api/enhet/<pk>/besetning/`, som vaktlistemodulen eier, og rendrer svaret.
Koblingen ligger dermed i nettleseren, ikke i Python — samme grep som gjorde at
statistikkappen kunne slutte å importere pasientmodulen.

Endepunktet gates på `les` i **vaktliste**, ikke i oppdrag. Har ikke operatøren
vaktlistetilgang, vises panelet ikke i det hele tatt — samme komposisjonsregel som
statistikksiden bruker (§5 i rollemodellen): en modul viser bare kilder brukeren har
tilgang til, framfor å gi avledet innsyn.

Svaret inneholder navn, rolle og innsjekkstatus. **Ikke kostbehov** — operatøren
trenger ikke vite hva sjåføren tåler for å tildele et oppdrag.

---

## 7. Personvern — kostbehov er ikke som de andre feltene

**Matallergi er en helseopplysning.** Det er ikke en detalj: helseopplysninger er en
særlig kategori etter GDPR art. 9, og alminnelig behandlingsgrunnlag etter art. 6
holder ikke alene. Portalen behandler allerede helseopplysninger om *pasienter*, med
et dokumentert grunnlag. Dette er noe annet: helseopplysninger om **egne
frivillige**, lagret i et register de ikke selv kontrollerer.

Fem tiltak, som til sammen gjør feltet forsvarlig — og som må være på plass **før
feltet tas i bruk**, ikke etterpå. Samme rekkefølgekrav som fase 2 i oppdragsmodulen,
og av samme grunn: rader som er skrevet feil kan ikke fjernes i ettertid uten å røre
sporet.

1. **Feltet heter `kostbehov`, ikke `allergi`.** Verdimengden er admin-styrt
   («Vegetar», «Glutenfri», «Nøtteallergi», «Laktose» …). Det matbestillingen trenger
   er hva personen skal ha, ikke en diagnose. Datamengden blir minimal, og formålet
   står i navnet.
2. **Grunnlaget er samtykke** (art. 9(2)(a)), innhentet ved påmelding til vakt, og
   dokumentert i protokollen. Feltet må derfor kunne stå tomt uten at noe klager —
   et påkrevd samtykke er ikke et samtykke.
3. **Synligheten er smalere enn resten av lista.** Kostbehov vises for `skriv_korps`,
   `skriv_full` og admin — de som faktisk bestiller mat. `les` ser lista uten den
   kolonnen, og `/oppdrag`-panelet ser den aldri.
4. **Unntatt verdilogging i audit**, som `Oppdrag.fritekst`. At feltet ble endret
   logges; hva det ble endret fra og til gjør det ikke.
5. **Kortere lagringstid enn resten.** Arkivet skal dokumentere *hvem som var på
   vakt* — det er verdifullt ved skade- og avvikssak. Det skal ikke dokumentere hva de
   tålte. Kostbehov arkiveres derfor ikke, og slettes med lista.

Resten av registeret — navn, telefon, korps, kompetanse — er alminnelige
personopplysninger om frivillige, med berettiget interesse eller avtale som grunnlag.
De trenger likevel en egen rad i `PERSONVERN_DOKUMENTASJON.md` A.6 og A.9, og en
lagringstid: et mannskapsregister som aldri ryddes er et arkiv over folks
organisasjonstilhørighet.

---

## 8. Frontend

Én side, `/vaktliste/`, med to nivåer av faner:

- **Øverst:** ressursene — «Samleplass», «Mannskapsbil 1», «Ambulanse», «Lag 1», «KO».
  De er data, ikke kode, så fanene bygges av lista og tilpasser seg vaktas art av seg
  selv. Én fane til for «Ikke plassert» — folk som er meldt på men ikke satt opp ennå.
- **En oversiktsfane** som viser alt samlet, gruppert på korps. Det er den som skrives
  ut og henges opp.

Reglene fra CLAUDE.md gjelder: eget stilark som definerer de fire variablene
`base_portal` ikke aliaser, ingen lasting av `patients-utils.js`, og escaping av alt
som settes med `innerHTML` — navn og merknad er fritekst fra basen.

Under drift er møtt/av vakt **to store knapper per rad**, ikke et redigeringsskjema.
KO står med en telefon i hånda og skal treffe riktig rad første gang.

---

## 9. Forholdet til `Forstehjelper` og `Helsepersonell`

Portalen har allerede to personregistre, begge i pasientmodulen, begge med valgfri
kobling til en konto. `Mannskap` blir det tredje.

**Det er én for mye, og det vet vi allerede nå.** Den som er førstehjelper på
samleplassen skal skrives inn to steder, og et navn som staves ulikt de to stedene er
to personer i statistikken.

Likevel: **ikke slå dem sammen i denne runden.** `Forstehjelper` er referert av 273
pasienter i produksjon og av arkivrader med frosne navn, og en sammenslåing er en
migrasjon med reell risiko — midt i en modul som ellers er ny og isolert. Samme
avveining som §12.1 i oppdragsnotatet.

Det som *skal* gjøres nå, er å gjøre sammenslåingen mulig senere:

- `Mannskap.forstehjelper` — nullbar OneToOne til `patients.Forstehjelper`, satt av
  admin når det er samme person. Da kan «mine pasienter» og vaktlista snakke sammen
  uten at noe må skrives to ganger.
- Ingen kopiering av navn mellom registrene automatisk. Magi som holder to registre i
  synk er verre enn to registre.

Sammenslåingen føres opp som eget punkt i TODO, med prisen notert: to steder å
vedlikeholde navn til den er gjort.

---

## 10. Faser

| Fase | Innhold | Estimat |
|---|---|---|
| 1 | App, modulregistrering, `Korps`/`Kompetanse`/`VaktRolle`, `Mannskap` med admin. **Uten kostbehov** | 6–8 t |
| 2 | Personverntillegget for kostbehov (§7) + feltet. **Før fase 3** | 3–4 t |
| 3 | `Vaktliste`, `Ressurs`, `Vaktpost`, planlegging med faner. «Ny planlagt vakt» | 8–10 t |
| 4 | Tilgangsmodellen: `skriv_korps`, objektsjekk per korps, matrisen | 4–6 t |
| 5 | Drift: sett i drift, møtt/av vakt, endring under drift | 5–7 t |
| 6 | Kobling til `/oppdrag`: besetningspanel på enheten | 3–4 t |
| 7 | Arkiv + statistikk via `core.arkiv` og `core.stats` | 4–6 t |

**Fase 2 står før fase 3** av samme grunn som i oppdragsmodulen: feltet skal ikke være
i produksjon med full verdilogging én eneste dag.

**Fase 4 kunne ligget først**, men gjør det ikke: tilgangsreglene er lettere å skrive
riktig når det finnes rader å skrive dem om. Fram til fase 4 er modulen admin-only —
det er fail-closed, og ingen andre slipper inn i mellomtiden.

**Fase 7 blir tredje modul i begge registrene.** Det er den beste prøven `core.arkiv`
og `core.stats` kan få: mønstrene ble skrevet for to moduler, og en tredje viser om de
faktisk generaliserer eller bare ble beskrevet som om de gjorde det.

Totalt 33–45 timer.

---

## 11. Åpne avklaringer

Disse må besvares før fase 1. Anbefalingene står, men valget er ditt.

### 11.1 Skal mannskapsregisteret være globalt eller per vakt?

Et **globalt** register (anbefalt) er personellet organisasjonen har, og hver vakt
plukker fra det. Et **per vakt**-register ville betydd å skrive inn alle på nytt hver
gang.

Konsekvensen av globalt: registeret er personopplysninger som lever mellom vakter, og
trenger en ryddeplikt (§7 siste avsnitt). Anbefalt likevel — alternativet er at ingen
gidder å vedlikeholde det.

### 11.2 Skal «Sett i drift» også gjøre vakta aktiv i portalen?

Å sette lista i drift og å gjøre vakta til portalens aktive vakt er to ting i dag.
Ved vaktstart skjer de samtidig.

**Anbefaling: hold dem atskilt, men la «Sett i drift» tilby byttet i samme dialog** —
med en avkryssing som sier hva den gjør. Å slå dem sammen ville gjort en
vaktlistehandling til noe som flytter scopet for pasienter og oppdrag, og det er en
bieffekt ingen vil oppdage før tallene ser rare ut.

### 11.3 Kan én bruker administrere flere korps?

Modellen i §4.1 gir én korpstilhørighet per person. **Anbefaling: nei nå.** Trengs det,
er svaret `skriv_full` inntil videre, og et eksplisitt tillegg den dagen behovet er
reelt — ikke et felt som gjetter på det.

### 11.4 Hvem registrerer møtt og av vakt?

**Anbefaling: den som fører lista** (`skriv_korps`/`skriv_full`/admin). De fleste
frivillige har ikke portalkonto, og en innsjekk som krever innlogging blir ikke brukt.

Har mannskapet en konto, kan selvinnsjekk komme senere som et tillegg — men da med
det samme skillet som oppdragsmodulen bruker: å stemple for seg selv er noe annet enn
å stemple for andre.

### 11.5 Skal vaktlista kunne kopieres fra forrige vakt?

Samme korps, samme biler, ofte mye av det samme mannskapet. **Anbefaling: ja, men
først i fase 3 som «kopier oppsett fra …»** — ressursene og rollene, ikke personene.
Å kopiere personer ville satt folk opp på en vakt de ikke har sagt ja til.

### 11.6 Hva skjer med en vaktpost når mannskapet slettes?

**Anbefaling: `PROTECT` på `Mannskap`, med «pensjonering» (`er_aktiv=False`) som den
normale veien ut** — samme mønster som `Enhet` i oppdragsmodulen. Historikken om hvem
som var på vakt skal ikke kunne rives bort under en sletting. Sletterett etter art. 17
løses ved at arkivet fryser *navn*, ikke FK-en (§10, fase 7).
