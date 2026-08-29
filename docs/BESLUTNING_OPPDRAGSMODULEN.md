# Beslutningsnotat: oppdragsmodulen

Status: **besluttet 28. aug. 2026, ikke bygget.** To åpne avklaringer nederst; ingen av
dem blokkerer fase 1.

Modulen er den første som tar `skriv: handling` i bruk. Nivået ble definert i deploy 1 av
rollemodellen nettopp med denne bruken i tankene (§3.2 i
`docs/BESLUTNING_ROLLEMODELLEN.md`), og har stått tomt siden — «tomt i dag» i CLAUDE.md
peker hit.

Den er også den første modulen som skal **levere tall til `/statistikk/`**. Det utløser
registeret CLAUDE.md har varslet siden statistikkmodulen ble skilt ut.

**Slettes** når modulen er levert. Da er begrunnelsen CHANGELOG sin.

---

## 1. Hva modulen er

Oppdragshåndtering for bil og beredskapsambulanse under vakt. En operatør på sykestua —
rollen som tilsvarer 113 — oppretter et oppdrag, tildeler det en enhet, og følger enhetens
statusmeldinger. Enheten melder status fra bilen.

Bilen kjører hovedsakelig transportoppdrag; beredskapsambulansen rykker ut. Begge er samme
modell, og forskjellen viser seg i hvilke statuser som faktisk brukes.

## 2. Det som gjør modulen «kinkig», og hvorfor den likevel ikke er det

Utfordringen André formulerte: **to grensesnitt avhengig av tilgang.** Bilen skal se ett
bilde, sykestua et annet.

Fristelsen er å la nivået velge skjerm — «har du `skriv_handling`, får du bilskjermen».
Det er samme feil som §2.3 i rollemodellnotatet beskriver: å bruke et *ordnet* nivå som en
*identitet*. Stigen sier at `skriv_full` dekker `skriv_handling`; et oppslag på «er nivået
nøyaktig `skriv_handling`» bryter den regelen, og bryter den stille.

**Skillet er derfor ikke tilgang, men rolle i felt:** er kontoen en enhet eller ikke?

| Kontoen | Ser | Fordi |
|---|---|---|
| Knyttet til en `Enhet` | Enhetsskjermen | Den *er* en bil. Skjermen viser dens egne oppdrag og statusknappene |
| Ikke knyttet, `skriv_full` | Sentralbordet, redigerbart | Oppretter, tildeler og retter |
| Ikke knyttet, `les` | Sentralbordet, skrivebeskyttet | Vaktleder som vil ha oversikt |

Dette er ikke et nytt mønster. Pasientmodulen har allerede `Forstehjelper.user` og
`Helsepersonell.user`: en kobling mellom konto og funksjon i felt, som er *domenedata*,
ikke autorisasjon. §7.3 i rollemodellnotatet delte `PasientRolleForm` nettopp for å skille
de to — radioen setter koblingen, matrisen setter tilgangen.

**Samme regel gjelder her: å knytte en konto til en `Enhet` gir ingen tilgang.** Uten en
`ModulTilgang('oppdrag', ...)`-rad ser kontoen ingenting, enhet eller ei. Blandes de,
gjenoppstår feilen deploy 1–3 nettopp fjernet.

### 2.1 Bilkontoene opprettes som biler

`haugesund56` er ikke en person. `CustomUser.er_delt_konto` finnes allerede for akkurat
dette: ingen e-post, ingen MFA, ingen selvbetjent passord-reset — admin setter passordet.

**Kontotypen velges ved oppretting, og enheten lages i samme steg.** Første utgave krevde
tre handlinger for én bil: opprett konto, opprett `Enhet` inne i oppdragsmodulen, koble dem.
André kalte det tullete, og han hadde rett — to av de tre lå på en helt annen side enn den
første, og ingenting forklarte hvorfor de hang sammen.

`AdminUserCreateForm` har derfor ett valg med tre verdier:

| Kontotype | Hva som lages |
|---|---|
| Person | Personlig konto. E-post og navn, kan inviteres |
| Delt konto | Ingen personlig eier. F.eks. en felles PC på sykestua |
| Bil eller ambulanse | Delt konto **og** en `Enhet`, i samme innsending |

Ett valg framfor «avkrysningsboks pluss et navnefelt» er med vilje: to kontroller som
overlapper er nettopp det som gjorde `role` til et rot. Da kunne man krysse av for delt
konto og likevel skrive et enhetsnavn, eller la være, og skjemaet måtte gjette.

**Det som ble slått sammen er to opprettelser, ikke tilgang og domenedata.** §7.3-skillet
står uendret: enheten avgjør hvilket grensesnitt kontoen får, matrisen avgjør hva den har
lov til — og matrisen ligger på det samme skjemaet. En test oppretter en bil og krever 403
på `/oppdrag/` så lenge den ikke har en `ModulTilgang`-rad.

Enhetspanelet i oppdragsmodulen beholder koblingsredigeringen. Den er for reparasjoner: en
bilkonto fra før dette fantes, eller en enhet som skal over på en annen konto.

## 3. Datamodellen

Fire modeller. Ingen av dem rører `patients`.

### 3.1 `Enhet`

Bilen eller ambulansen. Har et visningsnavn («Haugesund 56») atskilt fra brukernavnet,
fordi et brukernavn er en innloggingsdetalj og et enhetsnavn er noe man sier på samband.

```python
class Enhet(BaseTimeStampedModel):
    navn = models.CharField(max_length=64, unique=True)      # «Haugesund 56»
    user = models.OneToOneField(CustomUser, null=True, on_delete=models.SET_NULL)
    er_aktiv = models.BooleanField(default=True)   # oppsett: finnes enheten
    pa_vakt = models.BooleanField(default=True)    # drift: er den i tjeneste nå
```

**To felter, ikke ett, og forskjellen er hvem som endrer dem og hvor ofte.**
`er_aktiv` er oppsett: admin pensjonerer en bil, og da skal den bort fra alle lister for
godt. `pa_vakt` er ressursoversikten: 113 tar biler på og av gjennom vakta, og trenger ikke
være global admin for det.

Slås de sammen, ser «pensjonert» likt ut som «hjemme i kveld» — og den som skulle skru
bilen på igjen finner den ikke.

To regler holder oversikten ærlig:

* **En enhet som ikke er på vakt skjules ikke.** Sentralbordet viser den i en egen gruppe.
  En bil som forsvinner fra tavla er en bil ingen husker å sette inn igjen, og da mangler
  den neste vakt uten at noen vet hvorfor.
* **En enhet med et påbegynt oppdrag kan ikke tas av vakt.** Den er ute akkurat nå; å
  fjerne den fra tavla ville skjult et pågående oppdrag for den som har ansvaret. Flytting
  er heller ingen bakvei: et oppdrag kan ikke flyttes til en enhet som er av vakt.

`SET_NULL`, ikke `CASCADE`: slettes kontoen, skal enheten og dens oppdragshistorikk bestå.
Samme valg som `Forstehjelper.user`, og av samme grunn.

**Enheten har ingen statuskolonne.** Ved vaktstart står alle enheter som `Ledig`, og det er
ikke en verdi noen setter — det er hva «ingen påbegynte oppdrag» ser ut som. Lagret status
ville krevd at noe nullstilte den ved vaktstart, og at den holdt seg i takt med
oppdragsradene resten av vakta. To kilder til samme sannhet går i utakt første gang noe
feiler halvveis, og da er det den lagrede som lyver — den ser autoritativ ut.

Sentralbordet viser derfor en **enhetsliste med utledet status**: enhetens påbegynte
oppdrag hvis det finnes, ellers `Ledig`, med antall ventende ved siden av. En enhet med to
tildelte, men ingen påbegynte oppdrag er `Ledig (2 venter)` — den har ikke rykket ut ennå,
og det er den distinksjonen 113 trenger for å vite hvem som kan sendes.

### 3.2 `Lokasjon`

Admin vedlikeholder lista; oppdraget peker på en rad.

```python
class Lokasjon(BaseTimeStampedModel):
    navn = models.CharField(max_length=120, unique=True)
    er_aktiv = models.BooleanField(default=True)
    rekkefolge = models.IntegerField(default=100)
```

**Egen tabell, ikke en tuple i `choices.py`.** Problemstilling og hastegrad er faglige
verdimengder som endres sjelden og bør ligge i kode, der en endring blir en commit. Lokasjon
er stedene på *dette* arrangementet — de skifter fra vakt til vakt, og skal kunne endres av
admin uten deploy. Det er samme skille som mellom `PROBLEMSTILLING` og navneregistrene i
pasientmodulen, og administrasjonen følger `views_registre.py`-mønsteret.

`er_aktiv` framfor sletting: en lokasjon som er brukt på et oppdrag kan ikke forsvinne uten
å ta historikken med seg. Deaktivering fjerner den fra nedtrekkslista og lar radene bestå.

**Dette flytter personvernrisikoen, til det bedre.** Med en nedtrekksliste er lokasjon ikke
fritekst, og argumentet i A.6/A.12 — at feltet ikke kan inneholde navn — holder igjen. Da
står `fritekst` alene som feltet som må unntas verdilogging (§8).

### 3.3 `Oppdrag`

```python
class Oppdrag(BaseTimeStampedModel):
    year = models.IntegerField(db_index=True)         # aktiv vakt, som Patient.year
    enhet = models.ForeignKey(Enhet, on_delete=models.PROTECT, related_name='oppdrag')
    problemstilling = models.CharField(max_length=255)   # fra oppdrag/choices.py
    hastegrad = models.CharField(max_length=16)          # Akutt | Haster | Vanlig
    lokasjon = models.ForeignKey(Lokasjon, on_delete=models.PROTECT)
    fritekst = models.TextField(blank=True, default='')
    status = models.CharField(max_length=16, default='venter')
    opprettet_av = models.ForeignKey(CustomUser, null=True, on_delete=models.SET_NULL)
```

`PROTECT` på begge FK-ene: et oppdrag uten enhet eller lokasjon gir ingen mening, og
historikken skal ikke kunne forsvinne under den.

Verdimengdene for problemstilling og hastegrad håndheves server-side i `oppdrag/choices.py`,
etter mønsteret fra `patients/choices.py`. Problemstillingene tar utgangspunkt i
pasientmodulens liste. **De to listene skal ikke dele modul:** et oppdrag er ikke en pasient,
og den dagen den ene skal endres uten den andre, er en delt konstant det som står i veien.

Hastegradene er AMK-inndelingen — `Akutt`, `Haster`, `Vanlig` — ikke fargenavn. Fargekoding
i grensesnittet er presentasjon; navnet skal være det personellet faktisk sier.

### 3.4 `Statusmelding`

Én rad per overgang. Oppdraget bærer gjeldende status som et felt for raske oppslag;
sannheten om *når* noe skjedde ligger her.

```python
class Statusmelding(BaseTimeStampedModel):
    oppdrag = models.ForeignKey(Oppdrag, related_name='statusmeldinger', on_delete=models.CASCADE)
    status = models.CharField(max_length=16)
    tidspunkt = models.DateTimeField()               # hendelsestid, ikke lagringstid
    meldt_av = models.ForeignKey(CustomUser, null=True, on_delete=models.SET_NULL)
    forsinket = models.BooleanField(default=False)   # klienten var frakoblet
    automatisk = models.BooleanField(default=False)  # lukket av systemet, ikke meldt
    korrigerer = models.ForeignKey('self', null=True, blank=True,
                                   on_delete=models.PROTECT, related_name='korreksjoner')
```

Egen tabell framfor fem tidsstempelkolonner på `Oppdrag`. Kolonner ville låst modellen til
akkurat disse statusene, og en korreksjon fra 113 ville overskrevet historikken i stedet for
å legge seg ved siden av den.

`automatisk` settes når et pågående oppdrag lukkes fordi enheten startet det neste (§4.3).
Flagget **vises** — se §4.5 for hvordan, og hvorfor markøren sitter på klokkeslettet og
ikke på statusordet.

### 3.5 `Enhetsbytte`

113 kan flytte et oppdrag til en annen enhet. Det skal stå i oppdragets egen logg, ikke
bare i `AuditLog` — auditsporet er admin-flate, og den som leser oppdraget skal se det der.

```python
class Enhetsbytte(BaseTimeStampedModel):
    oppdrag = models.ForeignKey(Oppdrag, related_name='enhetsbytter', on_delete=models.CASCADE)
    fra_enhet = models.ForeignKey(Enhet, on_delete=models.PROTECT, related_name='+')
    til_enhet = models.ForeignKey(Enhet, on_delete=models.PROTECT, related_name='+')
    tidspunkt = models.DateTimeField(auto_now_add=True)
    byttet_av = models.ForeignKey(CustomUser, null=True, on_delete=models.SET_NULL)
```

Egen modell framfor en radtype i `Statusmelding`. Et enhetsbytte er ikke en status, og
statistikken måler statusene — blandes de, må hver eneste spørring huske å filtrere bort
den ene typen. Tidslinjen i grensesnittet er unionen av de to, og det er en visningsjobb.

**Statusen står når et oppdrag flyttes.** Meldingene den første enheten rakk å sende blir
stående, med `meldt_av` intakt: de skjedde. Et oppdrag som var `Fremme` er fortsatt
`Fremme` når den nye enheten overtar — å nullstille til `Venter` ville slettet en
responstid som faktisk ble målt.

## 4. Statusmaskinen

```
Venter ──→ Rykker ut ──→ Fremme ──→ Avreist ──→ Leverer ──→ Ledig
  │            │            │           │           │          ▲
  └────────────┴────────────┴───────────┴───────────┴──────────┘
                    Ledig er utgang fra enhver status
```

| Fra | Til |
|---|---|
| *(oppretting)* | `Venter` |
| `Venter` | `Rykker ut`, `Ledig` |
| `Rykker ut` | `Fremme`, `Ledig` |
| `Fremme` | `Avreist`, `Ledig` |
| `Avreist` | `Leverer`, `Ledig` |
| `Leverer` | `Ledig` |
| `Ledig` | *(ingen — terminal)* |

Overgangstabellen ligger i `oppdrag/services.py` som data, ikke som `if`-er spredt i
viewene, og håndheves server-side. Grensesnittet viser kun lovlige knapper, men det er ikke
der regelen bor: en knapp som ikke vises er ikke en knapp som ikke kan trykkes.

### 4.1 `Venter` er en konsekvens av køen, ikke en ekstra status noen ba om

Skal en enhet kunne ha ventende oppdrag, må et oppdrag kunne være tildelt uten å være
påbegynt. Da kan ikke 113 sette `Rykker ut` ved oppretting — det er enhetens første trykk.
Gjorde 113 det, ville responstiden løpe fra et tidspunkt ingen i bilen hadde sett oppdraget.

### 4.2 To knapper, seks endepunkter

Enhetsskjermen har **én «neste»-knapp** som går ett ledd fram i kjeden, og **én
«Ledig»-knapp** som alltid er tilgjengelig. Fem knapper der fire alltid er ulovlige er fire
måter å trykke feil på i en bil i bevegelse.

Serveren har likevel **ett navngitt endepunkt per overgang**. `POST .../status/neste/`
ville latt serveren utlede handlingen av gjeldende tilstand, og da er det ikke lenger en
navngitt handling — det er en tilstandsmaskin styrt utenfra, med det kappløpet som følger
når to trykk kommer tett. Knappen vet hvilken overgang den utfører og poster til den.

### 4.3 Å starte neste oppdrag lukker det pågående

En enhet kan ha flere tildelte oppdrag, men bare ett påbegynt. Trykker mannskapet
`Rykker ut` på et ventende oppdrag mens et annet er i gang, settes det pågående til `Ledig`
med samme tidsstempel, og statusmeldingen merkes `automatisk=True`.

Hvilket ventende oppdrag som startes velger mannskapet selv. De ser hastegrad og lokasjon,
og vet hva som er nærmest — en FIFO-kø ville tatt den avgjørelsen fra dem uten å vite noe
de ikke vet.

**Kostnaden er notert:** den automatiske `Ledig`-meldingen er avledet, ikke målt. Sluttiden
for det forrige oppdraget blir starttiden for det neste. Det er en bevisst avveining for
farten i felt, og `automatisk`-flagget gjør at statistikken kan skille dem senere.

### 4.4 Korreksjoner er nye rader, ikke redigeringer

113 kan rette tidspunktet på en statusmelding — typisk en `Ledig` som ble satt automatisk,
eller en stempling som kom inn med feil klienttid etter et nettbrudd.

**Rettingen er en ny rad som peker på den gamle**, ikke en endring av den. Begge blir
stående i tidslinjen. Grunnen er at `Statusmelding` er et spor av hva som faktisk ble meldt:
redigerer man raden, forsvinner det sporet, og «hva sa bilen egentlig?» kan bare besvares
ved å lese `AuditLog` — en admin-flate som ikke er der oppdraget vises.

Regelen er **nyeste ikke-korrigerte rad per status vinner**. Den finnes ett sted:

```python
Statusmelding.objects.gjeldende(oppdrag)   # manager-metode, ikke en if i hvert view
```

**Kostnaden er reell og ligger i statistikken.** Hver spørring som måler tid mellom
statuser må bruke gjeldende rader, ikke alle rader. Glemmes det ett sted, teller det
korrigerte tidspunktet dobbelt eller det gamle med. Derfor bor regelen i en manager-metode,
og derfor skal en test skrive en korreksjon og kreve at tallene endrer seg — en test som
bare sjekker at raden ble opprettet ville bestått uten at statistikken så den.

Omfanget er **tidspunkt, ikke status**. Å rette *hvilken* status som skjedde er noe annet:
det ville flyttet oppdraget i kjeden, og da er det en ny hendelse, ikke en korreksjon.
Kun `skriv_full` kan korrigere; en enhet stempler, den retter ikke.

### 4.5 Hvordan `automatisk` vises

Det er **tidspunktet** som er avledet, ikke at oppdraget ble ledig. Markøren sitter derfor
på klokkeslettet, ikke på statusordet.

| Flate | Visning |
|---|---|
| Tidslinjen, begge sider | `Ledig 22:41 · avsluttet automatisk` — dempet tekst |
| Sentralbordet, tett liste | Klokkeslettet med stiplet understrek og `title`-forklaring |
| Enhetsskjermen | Samme dempede linje. Bilen kan ikke rette den uansett |

Ingen badge: den ville konkurrert visuelt med statusen og blitt lest som «en annen slags
Ledig». Ingen egen farge heller — **markøren må stå i gråtoner** (WCAG 1.4.1), og en ny
statusfarge ville gjort metadata om til en tilstand.

En korrigert rad merkes etter samme prinsipp: `Ledig 22:35 · rettet av sentralen`, med den
opprinnelige verdien synlig under i tidslinjen.

## 5. Endepunktene

`@modul_kreves` gater modulen. Det er ikke nok her: en enhet skal bare kunne stemple på
*sine egne* oppdrag, og det er en objektsjekk dekoratoren ikke gjør. **To porter, ikke én**
— samme konstruksjon som arkivstatistikken, der statistikkgaten og `er_global_admin` ligger
oppå hverandre.

| Endepunkt | Nivå | Objektsjekk |
|---|---|---|
| `GET /oppdrag/` | `les` | Enhetskonto får kun egne rader |
| `GET /oppdrag/api/oppdrag/` | `les` | Samme filter |
| `POST /oppdrag/api/oppdrag/` | `skriv_full` | — |
| `PUT /oppdrag/api/oppdrag/<pk>/` | `skriv_full` | — |
| `POST /oppdrag/api/oppdrag/<pk>/flytt/` | `skriv_full` | — |
| `POST /oppdrag/api/oppdrag/<pk>/status/<overgang>/` | `skriv_handling` | Enhet må eie oppdraget |
| `POST /oppdrag/api/statusmelding/<pk>/korriger/` | `skriv_full` | — |
| `GET/POST/PUT/DELETE /oppdrag/api/lokasjoner/` | admin | — |

### 5.1 Stemplingsendepunktet leser (nesten) ingenting

§3.2 slo fast at et `handling`-endepunkt ikke skal lese request-kroppen, og at invarianten
er testbar. Offline-kravet bryter den bokstavelig: en stempling utført uten nett må kunne
fortelle *når* den skjedde, ellers viser statistikken når dekningen kom tilbake.

Invarianten skrives derfor om, strengere formulert i stedet for svakere:

> Kroppen har et **lukket skjema på to nøkler** — `klienttid` og `idempotency_key`. Alt
> annet avvises med 400. Ingen domenefelt kan noensinne komme inn denne veien.

Det er sterkere enn «leser ikke kroppen», fordi det er noe en test kan uttømme: send et
felt som ikke står i settet, og krev 400. En feltwhitelist inne i en generell `PUT` — det
§3.2 advarte mot — kan ikke testes slik, fordi settet av felter der vokser med modellen.

`klienttid` valideres server-side: ikke i framtiden, ikke før oppdraget ble opprettet, og
ikke mer enn ett døgn gammel. Utenfor vinduet brukes servertid, og `forsinket=True` settes
uansett når klienttid avviker merkbart fra ankomsttid. Da vet den som leser statistikken at
tallet kommer fra en bil som var uten dekning.

**Korreksjonsendepunktet er ikke et handling-endepunkt.** Det tar et tidspunkt, altså en
feltverdi, og ligger derfor på `skriv_full` med vanlig kroppsvalidering. Å presse det inn
under `skriv_handling` ville uthult det lukkede skjemaet i 5.1 med én gang.

### 5.2 Idempotens

En offline-kø som spilles av igjen er per definisjon en nettverks-retry, og
`core/idempotency.py` finnes for akkurat det. Køen genererer nøkkelen én gang, ved
knappetrykket, og beholder den gjennom hvert forsøk. To avspillinger av samme trykk gir da
én statusmelding, ikke to.

Reserver etter validering, aldri før — ellers brenner et avvist forsøk nøkkelen.

## 6. Offline

**Kun enhetens stemplinger.** Sykestua sitter med greit nett og må ha dekning for å
opprette oppdrag. Det er en bevisst avgrensning: skulle begge sider virke frakoblet, kunne
to klienter endret samme oppdrag uten å vite om hverandre, og noen måtte avgjort hvem som
vant. Med kun stemplinger finnes ikke den konflikten — hver melding er en ny rad, og
rekkefølgen avgjøres av `tidspunkt`.

Køen ligger i `localStorage`. Ved knappetrykk skrives den lokalt *først*, grensesnittet
oppdaterer seg umiddelbart, og synkingen skjer i bakgrunnen. Feiler den, blir raden
liggende og forsøkes på nytt — ved neste trykk, ved neste poll, og ved `online`-hendelsen.

Enhetsskjermen må vise at noe ligger usendt. En knapp som ser ut til å ha virket, men ikke
har det, er verre enn en som feiler synlig.

## 7. Hva enheten ser

Egne oppdrag, ingenting annet. Filteret er server-side — enheten får aldri andre rader
levert, den skjuler dem ikke i nettleseren.

To regler, ikke én, og begge håndheves i serverens svar:

| Når | Hva |
|---|---|
| Straks status blir `Ledig` | **`fritekst` utelates fra svaret.** Feltet sendes ikke lenger |
| 30 minutter etter `Ledig` | **Hele oppdraget utelates.** Raden består for sentralbord og statistikk |

Vinduet er kort med vilje — en bil kan stå ulåst — og feil kan korrigeres av 113 i
etterkant, over nødnett eller ansikt til ansikt.

At dette er server-side er poenget. Skjules fritekst i JS, ligger teksten fortsatt i
responsen, og en bil som blir stående ulåst er nettopp scenarioet regelen finnes for.

**Ingen varsling.** Et nytt oppdrag dukker opp i lista ved neste poll, tydelig markert som
ventende. Mannskapet får uansett beskjed over nødnett; en lyd i en nettleser som kanskje er
blokkert er ikke noe å bygge en operativ rutine på.

## 8. Statistikk: registeret CLAUDE.md har varslet

`/statistikk/` skal få **én fane per kildemodul** — pasientmodulen (samleplass/skadestue),
oppdragsmodulen (bil/ambulanse), og senere lagmodulen.

I dag importerer statistikkappen `patients.services` direkte. CLAUDE.md sier hva som skjer
når modul nummer to skal levere tall: den direkte importen erstattes av et registry etter
samme idiom som `core.backup` og `core.arkiv`. **Dette er modul nummer to.**

Formen er kjent fra de to andre registrene: hver modul registrerer en handler fra
`apps.ready()`, og statistikkappen spør registeret i stedet for å kjenne modulene.

**§5 i rollemodellnotatet gjelder uendret: modulen komponerer tilgang, den eier den ikke.**
En fane vises kun hvis brukeren har minst `les` på kildemodulen. Uten det ville aggregatene
gitt avledet innsyn i data brukeren ikke har tilgang til. Sjekken er én linje i dag fordi
`patients` er eneste kilde; med to blir den løkka §5 forutså.

Merk konsekvensen for enhetskontoene: en bil med `skriv_handling` på `oppdrag`, men ingen
rad på `statistikk`, ser ingen statistikk i det hele tatt. Det er riktig.

**Oppdragshandleren må regne på gjeldende statusmeldinger** (§4.4), ikke på alle rader. En
korreksjon som ikke slår gjennom i tallene er verre enn ingen korreksjon: operatøren ser at
rettingen står i tidslinjen og tror den er tatt hensyn til. Testen som håndhever det skriver
en korreksjon og krever at responstiden endrer seg.

## 9. Personvern

**Ett punkt, ikke to** — lokasjon ble en nedtrekksliste (§3.2), og da holder A.6/A.12 for
det feltet.

**Fritekst skal unntas verdilogging i audit**, og det må være på plass før feltet ships.
`AuditLog.old_value`/`new_value` er `TextField` med 730 dagers lagring, og feltlista utledes
fra modellen (N2) — et nytt fritekstfelt havner der av seg selv. Skriver en operatør noe
sensitivt og retter det, ligger begge versjonene i loggen i to år. Signalet trenger en
opt-out per felt: at *feltet ble endret* logges, verdiene gjør det ikke.

Protokollen trenger fortsatt et tillegg, men et mindre et enn planlagt: oppdragsdata er
strukturert (problemstilling, hastegrad, lokasjon fra faste lister), og det eneste frie
feltet er unntatt logging. `Leverer` registrerer ikke hvor det leveres — bevisst, for å
holde helseopplysninger og posisjon fra hverandre.

> **Gjennomført.** Audit-unntaket har vært aktivt fra feltets første lagring
> (`oppdrag/signals.py`, låst av `AuditFritekstTests`; 28. aug. 2026), og
> protokolltillegget er levert 29. aug. 2026 som `PERSONVERN_DOKUMENTASJON.md`
> v1.7: ny seksjon i A.6, rad og merknad i A.9, sårbarhet i A.12, merknad i
> B.2. Rekkefølgekravet holdt — begge deler står før modulen når produksjon.

## 10. Frontend

Egen side, egne filer. Reglene i CLAUDE.md gjelder og håndheves av eksisterende tester:

- **`patients-utils.js` kan ikke lastes.** Den gjør arbeid på toppnivå og kaster på en side
  uten pasientskjemaene. Trengs en helper derfra, flyttes den til `portal-utils.js`.
  `JsModulLastingTests` sammenligner hva en side kaller mot hva den laster.
- **Eget stilark** som definerer de fire variablene `base_portal` ikke aliaser
  (`--text-muted`, `--text-soft`, `--surface-3`, `--header-bg`), og ikke gjentar de fire
  den faktisk setter. `statistikk.css` er mønsteret.
- **Brukerdata som settes inn med `innerHTML` escapes.** Fritekst er portalens første
  virkelige XSS-flate som ikke er en nedtrekksliste.

To maler, ikke én med `{% if %}` gjennom hele: `oppdrag/enhet.html` og
`oppdrag/sentral.html`. De deler nesten ingen markup, og en sammenslått mal ville vært to
layouter i én fil for å spare en `render`-linje.

Enhetsskjermen bygges for en telefon i en bil: store trykkflater, høy kontrast, og
statusknappen som det eneste elementet som ikke krever presisjon.

## 11. Faser

| Fase | Innhold | Estimat |
|---|---|---|
| 1 | ✅ App, modulregistrering, fem modeller, `choices.py`, regler, `lokasjon`-kommando | levert |
| 2 | ✅ Audit-unntak for fritekst + protokolltillegg. **Før fase 3** | levert |
| 3 | ✅ Sentralbordet: enhetsliste med utledet status, opprett, tildel, flytt, rediger, **lokasjonsadmin som side**. Polling med ETag | levert |
| 4 | ✅ Enhetsskjermen: statusmaskin, smale endepunkter, objektsjekk, de to skjulereglene, visning av `automatisk` | levert |
| 4b | ✅ Korreksjoner: ny rad som overstyrer, `gjeldende()`-manager | levert |
| 5 | ✅ Offline-kø med idempotens | levert |
| 6 | Statistikkregisteret + oppdragsfanen | 5–7 t |
| 7 | Arkivering: `AbstractArkiv` + handler og egen arkivknapp under `/oppdrag/` | 5–7 t |

Fase 2 står før fase 3 fordi fritekstfeltet ellers ville vært i produksjon med
verdilogging på, og de radene kan ikke fjernes i ettertid uten å røre auditsporet.

**Fase 6 river ut den direkte importen** fra statistikkappen til `patients.services`.
Pasientfanen skal se lik ut etterpå — det er en refaktorering med en ny modul som
akseptansekriterium, ikke en ny visning.

**Fase 7 er stedet `AbstractArkiv` endelig skal bygges.** TODO har utsatt den til «modell
nummer to faktisk skrives» — dette er modell nummer to. `VaktArkiv` skal *ikke* migreres til
basemodellen: SHA-signaturene er låst til dagens payload-form, og hvert eksisterende arkiv i
prod ville meldt tukling.

**Arkiveringen slås ikke sammen i denne runden.** Oppdrag får sin egen knapp under
`/oppdrag/`, og pasientarkivet beholder sin under `/pasienter/`. Det er en bevisst
utsettelse, ikke en forglemmelse — og prisen står i §12.1.

## 12. Åpne avklaringer

### 12.1 Arkiveringen ligger to steder inntil videre — og det har en pris

`core/arkiv/` er modul-agnostisk for frysing, verifisering og kollaps, men to ting ble
aldri flyttet ut av pasientmodulen: **opprettelsen** (`arkiver_aktiv_vakt()` i
`patients/services.py`; handler-kontrakten har ingen `opprett_arkiv`) og **knappen**, som
ligger i admin-kortene på `/pasienter/`.

En vakt er ikke en pasientting. Knappen hører hjemme i `/portal-admin/`, ved siden av
innstillingene som flyttet dit i §4.1. Men én knapp som lager to *urelaterte* arkivrader er
verre enn to knapper — da tror man de hører sammen. Sammenslåingen krever derfor en rad i
`core` som grupperer dem:

```python
class Vaktarkivering(BaseTimeStampedModel):   # core
    arrangement_navn, tidspunkt, utfort_av, utfort_av_navn
```

Hver moduls arkiv får en nullbar FK dit. **Signaturene overlever**, og det er ikke flaks:
`patients/arkiv.py` bestemmer selv hva som går inn i `sha_payload()`, så et felt handleren
ikke nevner endrer ingenting. `ArkivSignaturLaastTests` beviser det. Eksisterende arkiver
får `NULL` — de er fra før grupperingen fantes.

**Besluttet 28. aug. 2026: utsettes.** Oppdrag får sin egen knapp i fase 7, og
sammenslåingen tas som egen sak når begge arkivene finnes. Prisen er at portalen i en
periode har to steder å arkivere fra, og at **noen kan arkivere pasienter og glemme
oppdrag**. Det er en operativ risiko, ikke en teknisk: den håndteres med et punkt i
`docs/RUNBOOK_VAKT.md`, som faktisk leses ved vaktslutt.

### 12.2 Skal `automatisk`-flagget påvirke statistikken, ikke bare vises?

Fra fase 4 lagres flagget, og fra fase 4 vises det (§4.5). Om responstider skal *regnes*
annerledes når sluttiden er avledet — utelates, merkes, eller telles som alle andre — er
lettere å svare på når tallene finnes. Tas i fase 6.
