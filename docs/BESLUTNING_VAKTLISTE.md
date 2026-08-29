# Beslutningsnotat: vaktlistemodulen

Status: **utkast 29. aug. 2026, fire avklaringer besvart samme dag.** Bestilt av André.
Svarene er ført inn der de hører hjemme; §11 viser hva som står igjen.

Tre av svarene endret notatet mer enn de bekreftet det:

1. **Korps er en badge, ikke en akse.** Den eksisterende stigen holder — se §4.
2. **Kostbehov lagres ikke i portalen i det hele tatt.** Hele §7 ble en annen tekst.
3. **Ingen kobling til pasientmodulens personregistre.** Se §9.

Modulen er den mest sentrale som er foreslått så langt: den beskriver *hvem som er på
vakt*, og både pasientmodulen og oppdragsmodulen har hittil måttet gjette på det.
Notatet må ligge før første linje kode, av samme grunn som oppdragsnotatet måtte:
tilgangsmodellen og personvernet er ikke ting man setter på etterpå.

---

## 1. Hva modulen skal løse

Fire ting, slik de ble bestilt:

1. **Oversikt over personellet** — sortert på korps, med kompetanse og rolle under
   vakt. Korps, kompetanse og rolle vedlikeholdes av admin, ikke i kode.
   *Matallergi sto i bestillingen, men er tatt ut — se §7.*
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
   skrivetilgang redigerer alle. Global admin har alt. Og — presisert i svaret —
   **den som bare fører sitt eget korps skal ikke kunne sjekke folk inn og ut av
   vakta.**

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

Mannskap         navn, korps→Korps, kompetanser M2M,
                 telefon, user→CustomUser (valgfri), er_aktiv, notat

Vaktliste        vakt→core.Vakt (1:1), status, satt_i_drift_at/av
Ressurs          vaktliste→Vaktliste, navn, type, rekkefolge,
                 enhet→oppdrag.Enhet (valgfri, §6)
Vaktpost         ressurs→Ressurs, mannskap→Mannskap, rolle→VaktRolle,
                 fra_tid, til_tid, mott_at, av_vakt_at, avmeldt_at, merknad
```

Fire ting er verdt å begrunne:

**`Korps`, `Kompetanse` og `VaktRolle` er tabeller, ikke `choices.py`.**
Motsatt av oppdragsmodulen, der problemstilling og hastegrad ligger i kode. Skillet
er det samme som mellom `PROBLEMSTILLING` og `Lokasjon`: faglige verdimengder som
endres sjelden hører i kode, arrangements- og organisasjonsdata i basen. Korpsene og
kompetansenivåene er organisasjonens, ikke portalens — og bestillingen sier eksplisitt
at admin skal styre dem.

**`Mannskap` er et personregister, og det er nytt for portalen.** Se §9 om forholdet
til `Forstehjelper` og `Helsepersonell` — de forblir urørt.

**`Mannskap.korps` er badgen hele tilgangsmodellen hviler på.** Feltet har ingen annen
funksjon enn å si hvor personen hører hjemme — men fordi en konto kan knyttes til et
mannskap, er det også det som avgjør hvilke rader kontoen får redigere (§4).

**`Vaktliste` er 1:1 med `Vakt`.** Én vakt, én liste. Alternativet — flere lister per
vakt — løser ingenting bestillingen beskriver, og gjør «hvem er på vakt nå» til et
spørsmål med flere svar.

**`Vaktpost` bærer tidene, ikke `Mannskap`.** Møtt og av vakt gjelder *denne* vakta.
Legges de på personen, kan hun bare være på vakt ett sted, én gang.

---

## 4. Tilgangsmodellen — korps som badge, ikke som ny akse

Utkastet foreslo et nytt nivå `skriv_korps` i den delte stigen. **Det er forkastet.**
Svaret var at korps skal være *en badge på personen og ingenting annet*, og at det ikke
skal påvirke stort utenfor vaktlista — og da holder stigen portalen allerede har.

### 4.1 Nivåene

| Nivå | Betyr i denne modulen |
|---|---|
| `les` | Ser hele lista, alle korps |
| `skriv_handling` | Fører **sitt eget korps**: legger til og redigerer mannskap med samme korps som seg selv, og setter dem på lista. **Kan ikke** stemple møtt/av vakt |
| `skriv_full` | Alle korps, og **den eneste** som stempler møtt/av vakt og setter lista i drift |

Korpset kommer fra brukerens egen `Mannskap.korps` — badgen. En konto blir knyttet til
et mannskap (`Mannskap.user`), og arver korpset derfra. Koblingen gir i seg selv ingen
tilgang; den sier bare *hvem du er*. Det er samme idiom som `Enhet.user` i
oppdragsmodulen, der koblingen avgjør hvilket grensesnitt kontoen får uten å være
autorisasjon i seg selv.

**Skillet mellom de to skrivenivåene er ikke bredde, det er art.** Å føre inn sine egne
folk er planlegging — noe hvert korps gjør for seg. Å stemple noen inn på vakt er en
observasjon om hva som faktisk skjedde, og den hører til den som står med lista på
vakta. At `skriv_handling` ikke rekker over innsjekk er derfor ikke en begrensning i
mengde, men i hva slags utsagn nivået får lov å avgi.

### 4.2 Hvorfor `skriv_handling` og ikke et nytt nivå

Stigen er ordnet, og `skriv_full` inneholder `skriv_handling`. Det betyr at en
universell skriver automatisk kan alt korps-føreren kan, uten at noe må listes to
steder. Ingen ny verdi i `NIVAA_HIERARKI`, ingen migrasjon, og ingenting endres for de
to modulene som bruker stigen fra før.

Prisen står i §4.4.

### 4.3 To kanter, begge fail-closed

- **Konto med `skriv_handling` uten mannskapsrad** har ingen badge, altså intet korps,
  og kan dermed ikke skrive noe. Samme form som en enhetskonto uten enhet.
- **Én person hører til ett korps.** Skal noen føre to korps, er svaret `skriv_full`.
  Å legge inn flere korps per person nå ville vært å bygge for et tilfelle som ikke
  finnes — og bestillingen var eksplisitt på å ikke overkomplisere korpsbegrepet.

`les` gjelder hele lista med vilje: poenget med en vaktliste er samordning på tvers av
korps. Den som ikke skal se andre korps, skal ikke ha modulen.

### 4.4 Prisen: nivånavnet betyr noe annet her enn i oppdrag

I oppdragsmodulen betyr `skriv_handling` «navngitte stemplinger, leser ikke
request-kroppen». Her betyr det nesten det motsatte: *redigering, men bare eget korps,
og ingen stempling*. Nivåets navn er generisk nok til å bære begge, men
**tilgangsmatrisen viser i dag en global etikett** — «Skrive: handling» — hentet fra
`TilgangsNivaa.choices`. En admin som deler ut nivået på vaktlista vil ikke se hva det
betyr der.

Det må derfor følge med en liten utvidelse: **en valgfri etikett per modul per nivå**,
f.eks. `Module.nivaa_navn = {'skriv_handling': 'Skrive: eget korps'}`, som matrisen
bruker når den finnes. Uten den deles nivået ut i god tro med feil forventning — og det
er nøyaktig feilen rollemodellnotatet allerede har kalt ut én gang.

Det er én liten endring i `accounts/forms.py` og `core/modules.py`, og den hører til
fase 4.

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

Svaret inneholder navn, rolle og innsjekkstatus — det operatøren trenger for å vite
om bilen er bemannet. Ikke telefonnummer, ikke kompetanseliste, ikke `notat`:
sentralbordet skal se om ressursen er klar, ikke lese personalmapper.

---

## 7. Personvern — matallergi lagres ikke i portalen

Utkastet foreslo et `kostbehov`-felt med fem tiltak rundt seg. **Beslutningen ble å
ikke lagre det i portalen i det hele tatt.**

Grunnen tiltakene var nødvendige, er også grunnen til at det er et godt valg: en
matallergi er en **helseopplysning**, altså en særlig kategori etter GDPR art. 9. Det
ville vært første gang portalen lagret slikt om *egne frivillige* framfor om pasienter,
og det krever eget behandlingsgrunnlag, egen synlighetsregel, eget unntak fra
verdilogging og egen lagringstid. Fem mekanismer, for én kolonne som bare skal brukes
til å bestille mat.

**Kostbehov samles derfor inn utenfor portalen** — påmeldingsskjema, eller lista til
den som bestiller maten. Konsekvensen er ærlig og verdt å vite: vaktlista kan ikke
brukes til matbestilling, og den som lager mat må ha sin egen kilde.

Det som *blir* liggende i modulen — navn, telefon, korps, kompetanse, og hvem som var
på vakt når — er alminnelige personopplysninger om frivillige. De trenger likevel sitt:

- **En egen rad i `PERSONVERN_DOKUMENTASJON.md` A.6** (hva som lagres og hvorfor) og
  **A.9** (hvor lenge). Et mannskapsregister uten lagringstid er et arkiv over folks
  organisasjonstilhørighet, og det blir bare mer bevaringsverdig jo lenger det står.
- **En ryddeplikt.** Registeret er globalt (§11.1) og lever mellom vakter. Inaktive
  mannskaper skal kunne pensjoneres, og pensjonerte skal kunne slettes når ingen
  vaktposter peker på dem.
- **Ingen sensitive felter smugler seg inn.** `notat` på `Mannskap` er fritekst, og
  fritekst er der helseopplysninger havner når det ikke finnes et felt for dem.
  Feltet unntas verdilogging i audit, som `Oppdrag.fritekst` — at det ble endret
  logges, hva som sto der gjør det ikke.

Dette er en langt mindre jobb enn utkastets fase 2, og den forsvinner ikke: den er nå
en del av fase 1.

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

Portalen har allerede to personregistre, begge i pasientmodulen. `Mannskap` blir det
tredje. Utkastet foreslo en valgfri kobling mellom dem, slik at en sammenslåing senere
skulle bli lettere.

**Beslutningen ble å la dem være helt i fred.** De to registrene finnes for dem som
bruker `/pasienter` — de svarer på «hvem behandlet denne pasienten», ikke «hvem er på
vakt». Vaktlista trenger dem ikke, og en kobling som ingen bruker er et felt som må
vedlikeholdes uten å gi noe.

Prisen er kjent og akseptert: **et navn kan stå to steder.** Den som er førstehjelper
på samleplassen kan finnes både som `Mannskap` og som `Forstehjelper`, og de to vet
ikke om hverandre. Det er ikke en feil så lenge de svarer på hvert sitt spørsmål.

Skulle behovet melde seg — «vis meg pasientene mannskapet mitt behandlet» — er en
nullbar FK en additiv migrasjon som kan legges til når som helst. Ingenting i
utformingen her stenger for det.

## 10. Faser

| Fase | Innhold | Estimat |
|---|---|---|
| 1 | App, modulregistrering, `Korps`/`Kompetanse`/`VaktRolle`, `Mannskap` med admin. Personvernrader i A.6/A.9, audit-unntak for `notat` | 7–9 t |
| 2 | `Vaktliste`, `Ressurs`, `Vaktpost`, planlegging med faner. «Ny planlagt vakt» | 8–10 t |
| 3 | Tilgangsmodellen: korps-sjekk på objektnivå, per-modul-etikett i matrisen (§4.4) | 4–6 t |
| 4 | Drift: sett i drift, møtt/av vakt (kun `skriv_full`), endring under drift | 5–7 t |
| 5 | Kobling til `/oppdrag`: besetningspanel på enheten | 3–4 t |
| 6 | Arkiv + statistikk via `core.arkiv` og `core.stats` | 4–6 t |

Utkastets fase 2 — personverntillegget for kostbehov — **utgår** med beslutningen i §7.
Det som blir igjen av personvernarbeid (rader i protokollen, audit-unntak for `notat`)
er lite nok til å ligge i fase 1, og har ikke lenger et rekkefølgekrav foran seg: uten
helseopplysninger er det ingen rader som ikke kan ryddes i ettertid.

**Fram til fase 3 er modulen admin-only.** Det er fail-closed, og ingen andre slipper
inn i mellomtiden. Tilgangsreglene er lettere å skrive riktig når det finnes rader å
skrive dem om.

**Fase 6 blir tredje modul i begge registrene.** Det er den beste prøven `core.arkiv`
og `core.stats` kan få: mønstrene ble skrevet for to moduler, og en tredje viser om de
faktisk generaliserer eller bare ble beskrevet som om de gjorde det.

Totalt 31–42 timer.

## 11. Avklaringer

### Besvart 29. aug. 2026

| # | Spørsmål | Svar |
|---|---|---|
| 11.1 | Globalt mannskapsregister eller per vakt? | **Globalt.** Følger av at korps-brukeren «legger til korps Z-medlemmer» én gang, ikke per vakt |
| 11.2 | Hvordan skal korps-skillet utformes? | **Badge på personen, eksisterende stige.** `skriv_handling` = eget korps, `skriv_full` = alle. Ingen ny akse, ingen ny verdi i stigen — §4 |
| 11.3 | Kan korps-brukeren sjekke folk inn og ut? | **Nei.** Innsjekk og avregistrering krever `skriv_full`. Korps-brukeren fører inn sine folk, men avgir ikke utsagn om hva som skjedde på vakta |
| 11.4 | Kostbehov/matallergi i portalen? | **Nei.** Samles inn utenfor — §7 |
| 11.5 | Kobling til `Forstehjelper`/`Helsepersonell`? | **Nei.** De hører til `/pasienter` og forblir urørt — §9 |
| 11.6 | Flere korps per bruker? | **Nei nå.** Svaret er `skriv_full` inntil behovet er reelt |

### Står igjen

**11.7 Skal «Sett i drift» også bytte portalens aktive vakt?**

Å sette lista i drift og å gjøre vakta til portalens aktive vakt er to ting i dag. Ved
vaktstart skjer de samtidig.

*Anbefaling: hold dem atskilt, men la «Sett i drift» tilby byttet i samme dialog* — med
en avkryssing som sier hva den gjør. Å slå dem sammen ville gjort en vaktlistehandling
til noe som flytter scopet for pasienter og oppdrag, og det er en bieffekt ingen
oppdager før tallene ser rare ut.

**11.8 Hvor langt rekker korps-brukeren inn i selve oppsettet?**

At hun fører inn sine egne folk er avklart. Uklart er om hun også plasserer dem på
ressursene — altså setter Per på ambulansen og Kari på samleplassen.

*Anbefaling: ja, hun plasserer sine egne folk fritt.* Alternativet er at hvert korps
melder inn en haug med navn som noen andre må fordele, og da er «Ikke plassert»-fanen
hele jobben til én person. Vaktleder med `skriv_full` kan uansett flytte alle.

Det motsatte er også forsvarlig — at plassering er vaktleders jobb alene — men da bør
det sies nå, for det endrer hva korps-brukeren ser når hun logger inn.

**11.9 Skal vaktlista kunne kopieres fra forrige vakt?**

Samme korps, samme biler, ofte mye av det samme mannskapet.

*Anbefaling: ja, men først i fase 2 som «kopier oppsett fra …»* — ressursene og rollene,
ikke personene. Å kopiere personer ville satt folk opp på en vakt de ikke har sagt ja
til.

**11.10 Hva skjer med en vaktpost når mannskapet slettes?**

*Anbefaling: `PROTECT` på `Mannskap`, med pensjonering (`er_aktiv=False`) som den
normale veien ut* — samme mønster som `Enhet` i oppdragsmodulen. Historikken om hvem
som var på vakt skal ikke kunne rives bort under en sletting. Sletterett etter art. 17
løses ved at arkivet fryser *navn*, ikke FK-en (fase 6).
