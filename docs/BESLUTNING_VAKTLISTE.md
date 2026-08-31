# Beslutningsnotat: vaktlistemodulen

Status: **besluttet 29. aug. 2026.** Bestilt av André, avklart i to runder samme dag.
Svarene er ført inn der de hører hjemme; §11 er fasit for hva som ble bestemt, og
lister de få detaljene som kan avgjøres underveis.

Fem av svarene endret notatet mer enn de bekreftet det:

1. **Korps er en badge, ikke en akse.** Den eksisterende stigen holder — se §4.
2. **Ressurser reserveres til korps**, og korps-brukeren bemanner det korpset har
   fått — se §4.2.
3. **Drift er kun en innsjekk-port, og den er reversibel.** Ingen kobling til
   portalens aktive vakt — se §5.
4. **Kostbehov lagres ikke i portalen i det hele tatt.** Hele §7 ble en annen tekst.
5. **Ingen kobling til pasientmodulens personregistre.** Se §9.

Og to bruksområder kom til: planleggingstall (§8b) og tilstedeoversikt av
brannsikkerhetshensyn (§8) — den siste er modulens mest alvorlige flate.

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
3. **Planlegging som blir drift** — lista settes opp på forhånd og settes i drift når
   vakta starter. Drift betyr én ting: innsjekk er åpen (*møtt* / *av vakt*). Lista må
   fortsatt kunne endres under drift; folk bytter og folk uteblir.
4. **Kobling til `/oppdrag`** — operatøren trykker på en enhet og ser hvem som er på
   bilen, og om de har sjekket seg inn.

Og to bruksområder som kom til i avklaringsrunden, og som begge former utformingen:

- **Planleggingstall** (§8b): lista skal hjelpe planleggeren å se belastningen — timer
  per person, hviletid mellom skift, skiftlengder, antall lag i et tidsrom.
- **Tilstedeoversikt av brannsikkerhetshensyn:** på et sted med overnatting brukes
  lista til å vite *hvem som er til stede akkurat nå*. Det gjør «Tilstede nå»-visningen
  til modulens mest alvorlige flate — den skal kunne leses i en evakuering, og den skal
  kunne skrives ut (§8).

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

Vaktliste        vakt→core.Vakt (1:1), status (planlegging/drift), satt_i_drift_at/av
Ressurs          vaktliste→Vaktliste, navn, type, rekkefolge,
                 korps→Korps (valgfri — reservasjonen, §4.2),
                 enhet→oppdrag.Enhet (valgfri, §6)
Vaktpost         ressurs→Ressurs, mannskap→Mannskap, rolle→VaktRolle,
                 fra_tid, til_tid, mott_at, av_vakt_at, avmeldt_at, merknad
```

**Et skift er en `Vaktpost`.** Går Per to skift på ambulansen, er det to rader med hver
sine tider — det er det som gjør timer, hviletid og skiftlengde (§8b) til enkle
spørringer i stedet for tolkning. `fra_tid`/`til_tid` er *plan*; `mott_at`/`av_vakt_at`
er *hva som skjedde*. De fire holdes atskilt med vilje: avviket mellom dem er selve
informasjonen.

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

**`Ressurs.korps` er reservasjonen** (§4.2): `skriv_full`/admin merker et lag, en
mannskapsbil eller en ambulanse med korpset som har fått den, og korps-brukeren bemanner
bare ressurser med sin egen badge. Tom = ureservert, og da er den `skriv_full`/admins
bord — KO og samleplass er typisk slike.

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
| `skriv_handling` | Fører **sitt eget korps**: legger til og redigerer mannskap med sin egen badge, og plasserer dem — med tider — på ressurser **reservert sitt korps** (§4.2). **Kan ikke** stemple møtt/av vakt |
| `skriv_full` | Alle korps, fritt blandet på tvers av badge. Reserverer ressurser til korps, setter lista i drift og ut av drift, og er — sammen med admin — den eneste som stempler møtt/av vakt |

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

### 4.2 Reservasjonen: korps-brukeren bemanner det korpset har fått

Plasseringen er ikke fri: `skriv_full`/admin **tildeler** ressurser til korps ved å
sette `Ressurs.korps`, og korps-brukeren bemanner bare ressurser med sin egen badge.
Lag, mannskapsbiler og ambulanser er typisk reservert til korpsene som har fått dem;
KO og samleplass står typisk ureservert og bemannes av `skriv_full`/admin direkte.

Regelen er dobbel, og begge halvdeler håndheves server-side per objekt:

1. **Mannskapet må ha korps-brukerens badge** — hun setter bare opp sine egne folk.
2. **Ressursen må være reservert hennes korps** — en ureservert ressurs er ikke et
   fristed, den er stengt for henne.

Det gir en pen arbeidsdeling som speiler hvordan planleggingen faktisk foregår:
vaktleder deler ut «dere har ambulansen lørdag», og korpset fyller den selv, med
tidene sine. `skriv_full`/admin står utenfor begge sjekkene og blander fritt.

### 4.3 Hvorfor `skriv_handling` og ikke et nytt nivå

Stigen er ordnet, og `skriv_full` inneholder `skriv_handling`. Det betyr at en
universell skriver automatisk kan alt korps-føreren kan, uten at noe må listes to
steder. Ingen ny verdi i `NIVAA_HIERARKI`, ingen migrasjon, og ingenting endres for de
to modulene som bruker stigen fra før.

Prisen står i §4.5.

### 4.4 To kanter, begge fail-closed

- **Konto med `skriv_handling` uten mannskapsrad** har ingen badge, altså intet korps,
  og kan dermed ikke skrive noe. Samme form som en enhetskonto uten enhet.
- **Én person hører til ett korps.** Skal noen føre to korps, er svaret `skriv_full`.
  Å legge inn flere korps per person nå ville vært å bygge for et tilfelle som ikke
  finnes — og bestillingen var eksplisitt på å ikke overkomplisere korpsbegrepet.

`les` gjelder hele lista med vilje: poenget med en vaktliste er samordning på tvers av
korps. Den som ikke skal se andre korps, skal ikke ha modulen.

### 4.5 Prisen: nivånavnet betyr noe annet her enn i oppdrag

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

## 5. Livsløp: planlegging ⇄ drift

```
planlegging ──(skriv_full/admin)──▶ drift
     ▲                                │
     └────────── ut av drift ─────────┘        arkivering skjer uavhengig (§10, fase 6)
```

**Drift betyr én ting: innsjekk er åpen.** Det var svaret, og det forenkler alt:

- **Planlegging.** Ressurser reserveres og bemannes. Innsjekk er stengt — et
  møtt-stempel før vakta finnes ikke.
- **Drift.** Innsjekk er åpen: `skriv_full`/admin stempler møtt og av vakt. Lista kan
  **fortsatt** endres — folk uteblir og bytter, og en liste som låser seg i det vakta
  starter er en liste som forlates til fordel for et ark.
- **Ut av drift.** Reversibel — en pause i arrangementet, eller et feilklikk. Stenger
  innsjekken igjen; stemplene som er satt består. Ikke en sletting, bare en dør.

**Drift rører ikke portalens aktive vakt.** Spørsmålet fra utkastet (om «Sett i drift»
skulle bytte scope for pasienter og oppdrag) falt bort med svaret: tilstanden er en
innsjekk-port og ingenting annet. Aktiv vakt byttes der den alltid byttes, i
vaktadministrasjonen.

**Planlegging krever en vakt som ennå ikke er aktiv.** I dag lages `Vakt`-rader på to
måter: lat opprettelse for inneværende år, og «Avslutt vakt» som lager den neste.
Ingen av dem lar deg planlegge oktobervakta i august. Modulen trenger derfor
«Ny planlagt vakt» — en `Vakt` med `er_aktiv=False` som ikke rører portalens peker.
Det er en liten utvidelse av vaktadministrasjonen, og den hører til fase 2.

**Kopiering fra forrige vakt** (besluttet): en ny vaktliste kan kopiere *oppsettet* —
ressursene med reservasjoner og roller — fra en tidligere. **Aldri personene**: å
kopiere folk ville satt dem opp på en vakt de ikke har sagt ja til.

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

**«Tilstede nå» er en egen visning, og den er modulens mest alvorlige.** På et sted
med overnatting brukes den til å vite hvem som er i bygget av brannsikkerhetshensyn.
Det stiller tre krav som resten av siden ikke har:

- Definisjonen er knivskarp: *møtt, og ikke gått av vakt* — utledet av stemplene,
  aldri en egen lagret status som kan komme i utakt.
- Tellingen står øverst, stor. I en evakuering teller man hoder mot et tall.
- Den skal kunne **skrives ut** — en ren utskriftsvisning uten faner og knapper.
  Strøm og nett er det første som ryker i nettopp situasjonen lista finnes for, så
  rutinen bør være å skrive den ut ved vaktstart og ved skiftbytte. (Portalen har
  ingen PDF-generering i dag, og trenger ikke få det for dette: en `@media print`-
  visning holder.)

## 8b. Planleggingstall

Lista skal hjelpe planleggeren å se belastningen før vakta, ikke bare bemanningen.
Bestilt: antall lag i et tidsrom, antall personell totalt, timer per person, hviletid
mellom skift og skiftlengde. Alle er enkle spørringer så lenge et skift er en
`Vaktpost` med tider (§3).

Visningen er en egen fane, «Planlegging», med:

- **Bemanningskurve:** antall på plan per time gjennom vakta, og antall lag i samme
  tidsrom. Hull i dekningen synes som daler.
- **Per person:** totaltimer, antall skift, lengste skift, korteste hvile. Sortert på
  totaltimer, slik at den som er i ferd med å bli brukt opp ligger øverst.
- **Varsler, ikke sperrer:** et skift over N timer eller en hvile under M timer merkes
  i lista. Grensene er admin-styrte verdier med fornuftige standarder (forslag: 12 t
  skift, 8 t hvile) — organisasjonens regler er ikke portalens å hardkode. En sperre
  ville vært feil: noen ganger *må* noen ta et langt skift, og da skal lista si det
  høyt, ikke nekte.
- **Kompetansedekning per ressurs** (senere, hvis ønsket): «har samleplassen
  helsepersonell hele åpningstiden» er samme spørring som bemanningskurven, filtrert
  på kompetanse. Står som mulig utvidelse, ikke i første leveranse.

Under drift får de samme tallene en tvilling regnet fra stemplene i stedet for planen
— da blir «planlagt mot faktisk» synlig: hvem gikk lengre enn planlagt, hvem møtte
ikke. Det er samme grep som oppdragsstatistikken bruker for plan/målt-skillet, og det
koster lite når feltene alt er atskilt.

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
| 1 | ✅ App, modulregistrering, `Korps`/`Kompetanse`/`VaktRolle`, `Mannskap` med admin. Personvernrader i A.6/A.9, audit-unntak for `notat` | levert |
| 2 | ✅ `Vaktliste`, `Ressurs` med reservasjon, `Vaktpost` med tider, planlegging med faner. «Ny planlagt vakt», kopiering av oppsett. Admin-only til fase 3 | levert |
| 2b | ✅ Registrene i portalen: mannskapsoversikt og admin for `Korps`/`Kompetanse`/`Ressursrolle`. Ikke planlagt — notatet forutsatte stilltiende Django-admin, som er av i prod (S1). Lå på `/vaktliste/registre/` til 30. aug. 2026; mannskapet er nå en fane på `/vaktliste/`, korps og kompetanser ligger i «Innstillinger» | levert |
| 3 | ✅ Tilgangsmodellen: badge- og reservasjonssjekk på objektnivå, per-modul-etikett i matrisen (§4.5). `admin_only` av | levert |
| 4 | ✅ Drift: i/ut av drift, møtt/av vakt (kun `skriv_full`), «Tilstede nå» med utskrift. Ingen migrasjon — feltene kom i fase 2. Ett avvik: én stempelknapp per rad framfor to, se CHANGELOG 30. aug. | levert |
| 5 | ✅ Planleggingstall (§8b): per person, varsler mot admin-styrte grenser, faktisk mot planlagt. Bemanningskurvene kom i fase 2 og står per ressursgruppe. Kompetansedekning ikke levert — den sto som mulig utvidelse | levert |
| 6 | ✅ Kobling til `/oppdrag`: besetningspanel på enheten, åpnes ved klikk. Retningen håndheves med AST-test. Ingen migrasjon | levert |
| 7 | Arkiv + statistikk via `core.arkiv` og `core.stats` | 4–6 t |

**Fram til fase 3 er modulen admin-only.** Det er fail-closed, og ingen andre slipper
inn i mellomtiden. Tilgangsreglene er lettere å skrive riktig når det finnes rader å
skrive dem om.

**Fase 4 før fase 5:** tilstedeoversikten er et sikkerhetsbehov og går foran
planleggingskomforten. Fase 5 og 6 er uavhengige av hverandre og kan bytte plass.

**Fase 7 blir tredje modul i begge registrene.** Det er den beste prøven `core.arkiv`
og `core.stats` kan få: mønstrene ble skrevet for to moduler, og en tredje viser om de
faktisk generaliserer eller bare ble beskrevet som om de gjorde det.

Totalt 37–49 timer.

## 11. Avklaringene — fasit

### Besvart 29. aug. 2026 (to runder)

| # | Spørsmål | Svar |
|---|---|---|
| 11.1 | Globalt mannskapsregister eller per vakt? | **Globalt.** Korps-brukeren fører inn folkene sine én gang |
| 11.2 | Hvordan utformes korps-skillet? | **Badge på personen, eksisterende stige.** `skriv_handling` = eget korps, `skriv_full` = alle. Ingen ny akse — §4 |
| 11.3 | Kan korps-brukeren sjekke folk inn/ut? | **Nei.** Innsjekk krever `skriv_full` |
| 11.4 | Kostbehov/matallergi i portalen? | **Nei.** Samles inn utenfor — §7 |
| 11.5 | Kobling til `Forstehjelper`/`Helsepersonell`? | **Nei.** De hører til `/pasienter` — §9 |
| 11.6 | Flere korps per bruker? | **Nei nå.** `skriv_full` er svaret inntil behovet er reelt |
| 11.7 | Bytter «Sett i drift» portalens aktive vakt? | **Nei — drift er kun en innsjekk-port, og den er reversibel** («ut av drift»). Aktiv vakt byttes i vaktadministrasjonen — §5 |
| 11.8 | Plasserer korps-brukeren sine folk selv? | **Ja, på ressurser reservert sitt korps.** `skriv_full`/admin reserverer lag/biler/ambulanser til korps og bemanner det ureserverte (KO, samleplass) selv, fritt på tvers av badge — §4.2. Skift har tider |
| 11.9 | Kopiere fra forrige vakt? | **Ja — oppsettet, aldri personene** — §5 |
| 11.10 | Mannskap slettes med vaktposter? | **`PROTECT`, pensjonering som normal vei ut** — samme mønster som `Enhet`. Arkivet fryser navn, ikke FK-en |

### Små restpunkter — avgjøres underveis, ikke blokkerende

- **Grensene for varslene i §8b** (skiftlengde, minstehvile): admin-styrte verdier;
  standardforslag 12 t / 8 t. Justeres når noen har brukt dem.
- **Lagringstid for oppmøtehistorikken** settes i A.9 når fase 7 bygges. Hvem som var
  på vakt er verdifullt ved skade- og avvikssak, og taler for samme 24-måneders
  radnivå som resten — men det skal *besluttes*, ikke arves stille.
- **Selvinnsjekk** (mannskap med konto stempler seg selv) er bevisst utenfor planen.
  Kommer den, er det med samme skille som oppdragsmodulen bruker: å stemple for seg
  selv er noe annet enn å stemple for andre.
