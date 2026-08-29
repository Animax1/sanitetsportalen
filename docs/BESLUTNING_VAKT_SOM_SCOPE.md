# Beslutningsnotat: vakt som scope, ikke år

Status: **utkast 29. aug. 2026. Ikke besluttet.** Premisset er fastslått av André;
utformingen er ikke. Åpne avklaringer nederst må besvares før migrasjonen skrives.

Erstatter TODO-punktet «Vakt som scope, ikke år». Notatet må ligge før fase 6 og 7 av
oppdragsmodulen — begge bygger på scopet, og bygges de først, bygges de to ganger.

**Slettes** når modellen er levert. Da er begrunnelsen CHANGELOG sin.

---

## 1. Premisset

Portalen skal brukes på **forskjellige vakter**, ikke på det samme arrangementet én gang
i året. En vakt er enheten alt annet henger på: pasienter, oppdrag, statistikk, arkiv.

I dag er den enheten `year` — et heltall.

## 2. Funnene

Alle verifisert ved å lese og kjøre koden, ikke bare anta.

### 2.1 `year` er allerede et vakt-id i forkledning — for pasienter

Vaktsyklusen finnes og er dokumentert. `C.2 Sjekkliste etter hvert event` i
`PERSONVERN_DOKUMENTASJON.md` sier:

> «Vurder om arbeidsdata skal nullstilles for **neste event** (ny triagering fra null) —
> ta backup/pre-reset snapshot først»

Og `reset_active_year_view` gjør nettopp det: hard-sletter alle pasienter i aktivt år og
setter `next_patient_nr` tilbake til 1, etter en automatisk pre-reset-backup.

**Altså: arkiver → nullstill er allerede vaktgrensen.** Kjøres to arrangementer i 2026
med den syklusen mellom, har `year=2026` allerede betydd to forskjellige vakter etter
hverandre. Pasientnumrene restarter riktig, fordi telleren nullstilles i samme operasjon.

**Dokumentasjonen er foran koden.** Prosedyren sier «event»; feltet heter `year`.

### 2.2 Oppdragsmodulen har ingen slik syklus — der er `year` et ekte kalenderår

Det finnes ingen nullstilling for oppdrag, og ingen arkivering (fase 7 er ubygget).
Radene blir liggende. `year` filtrerer dem, og det er alt.

Konsekvensen er at de to modulene mener forskjellige ting med samme felt:

| Modul | Hva `year` faktisk avgrenser |
|---|---|
| `patients` | Perioden siden forrige nullstilling — i praksis én vakt |
| `oppdrag` | Kalenderåret. Alle vakter i året ligger sammen |

Det er ikke en feil noen har gjort; det er at oppdragsmodulen ennå ikke har fått
livssyklusen pasientmodulen har. Men det betyr at «bare døp om `year` til `vakt`» ville
gitt to ulike betydninger samme navn.

### 2.3 Oppdragsnummeret teller feil under premisset

Levert 29. aug., og allerede utsatt for premisset. `oppdragsnummer` er unikt per
`(year, oppdragsnummer)` med telleren `next_oppdrag_nr_<år>`.

Kjøres tre vakter i 2026, teller numrene **1–40 tvers gjennom alle tre**. «Oppdrag 14»
blir dermed tvetydig neste vakt — som er nøyaktig det nummeret ble laget for å unngå.

Under vakt-scoping skal sperren være `(vakt, oppdragsnummer)` og telleren per vakt.
Dette er den mest konkrete grunnen til at notatet ikke kan vente til etter fase 6.

### 2.4 `Nullstill år` sletter for mye så snart en vakt ikke er et år

Knappen hard-sletter **alle** pasienter i aktivt år. I dag er det riktig: ett år er én
vakt, og arkivet er tatt først.

Med flere vakter i året er navnet direkte farlig. Den som har arkivert vakt A og vil
tømme tavla før vakt B, leser «Nullstill år» og nøler — eller trykker, og sletter også
det som ikke var arkivert ennå. Knappen må hete det den gjør, og gjøre det mot én vakt.

### 2.5 `Vaktarkivering` og `Vakt` er samme entitet sett fra hver sin ende

§12.1 i `BESLUTNING_OPPDRAGSMODULEN.md` foreslår allerede en rad i `core` som grupperer
modulenes arkiver:

```python
class Vaktarkivering(BaseTimeStampedModel):   # core
    arrangement_navn, tidspunkt, utfort_av, utfort_av_navn
```

Den skulle opprettes **ved arkivering**. En `Vakt` ville eksistert **fra vaktstart**. Det
er de samme feltene, og nesten den samme raden — forskjellen er bare når den blir til.

**Da bør det være én ting.** En vakt som opprettes ved vaktstart og lukkes ved arkivering
dekker begge behov; to rader ville betydd at «hvilken vakt» og «hvilken arkivering»
kunne komme i utakt. Dette er hovedgrunnen til at fase 7 ikke bør bygges før dette er
avgjort: den ville lagt inn `Vaktarkivering` og deretter måttet rive den.

### 2.6 Vaktnavnet finnes allerede halvveis

`AppSetting['event_name']` holder ett navn, globalt. `VaktArkiv` fryser
`arrangement_navn` på seg selv ved arkivering.

`patients/services.py` noterer dessuten at en mekanisme for navn **per år**
(`event_name_<år>` med `get_event_name`/`set_event_name`) fantes og ble slettet
13. aug. 2026 som ubrukt. Den ble skrevet for et behov som ikke var der da, og som nå er
her — men riktig akse er per vakt, ikke per år.

## 3. Forslaget

**`Vakt` blir en modell i `core`, og er scopet alt annet henger på.**

```python
class Vakt(BaseTimeStampedModel):        # core
    navn = models.CharField(max_length=255)          # «Landsskytterstevnet 2026»
    startet = models.DateTimeField()
    avsluttet = models.DateTimeField(null=True, blank=True)
    er_aktiv = models.BooleanField(default=True)
```

### 3.1 Hvorfor en modell, ikke en streng til

`event_name` er én global streng. Den kan ikke svare på «hvilke vakter har vi hatt», og
to vakter kan ikke eksistere samtidig i den. En FK gir dessuten databasesperren
oppdragsnummeret trenger (`unique_together(vakt, oppdragsnummer)`), som en streng ikke
kan bære.

Den ligger i `core` og ikke i `patients`, fordi begge modulene scopes på den — og fordi
avhengighetsretningen ellers blir `oppdrag → patients` for noe som ikke er pasientdata.
Samme begrunnelse som `core.stats_cache` og `core.arkiv`.

### 3.2 Én aktiv vakt om gangen

`AppSetting['aktiv_vakt_id']` erstatter `active_year`, og `get_aktiv_vakt()` erstatter
`get_active_year()`.

Flere samtidige vakter er ikke foreslått. Portalen viser én tavle, én pasientliste og ett
sett med enheter; to åpne vakter ville krevd et vaktvalg i hver eneste visning, og en
feil i det valget er en pasient registrert på feil vakt. Behovet er heller ikke meldt.
Modellen sperrer det ikke for framtiden — `er_aktiv` er en boolean, ikke en unik nøkkel —
men grensesnittet forutsetter én.

### 3.3 Hva som scopes på vakt

| I dag | Etter |
|---|---|
| `Patient.year` | `Patient.vakt` (FK, PROTECT) |
| `Oppdrag.year` | `Oppdrag.vakt` (FK, PROTECT) |
| `AppSetting['active_year']` | `AppSetting['aktiv_vakt_id']` |
| `AppSetting['event_name']` | `Vakt.navn` |
| `next_patient_nr` (global) | Teller per vakt |
| `next_oppdrag_nr_<år>` | Teller per vakt |
| `VaktArkiv.year_snapshot` | `VaktArkiv.vakt` (FK, nullbar) |

`PROTECT` framfor `CASCADE`: en vakt med pasienter eller oppdrag skal ikke kunne slettes
og ta historikken med seg. Samme valg som `Oppdrag.enhet`.

**`year` beholdes som utledet felt på `Vakt`**, ikke på radene. Statistikk som
sammenligner sesonger trenger året, og å regne det ut fra `Vakt.startet` hver gang ville
gjort en billig gruppering dyr.

### 3.4 «Nullstill år» blir «Avslutt vakt»

Operasjonen er den samme — backup, arkiver, tøm tavla — men den gjelder én vakt, og
navnet sier det. Ny vakt opprettes i samme flyt, slik at man ikke kan ende opp med en
tømt portal uten aktiv vakt.

## 4. Hva som skjer med data som finnes

**Prod har 273 importerte pasienter på `year=2026`. Staging har oppdrag.**

Backfillen lager én `Vakt` per distinkt `year` som finnes, og peker radene dit:

```
Vakt(navn='2026', startet=<eldste created_at det året>, er_aktiv=<year == active_year>)
```

Navnet blir årstallet, ikke `event_name`. Grunnen er at `event_name` er **én global
verdi i dag** — den beskriver den vakten som var aktiv da noen sist skrev den, ikke
nødvendigvis den som eide radene fra 2026. Å fryse dagens `event_name` inn på en
historisk vakt ville påstått noe vi ikke vet. Årstallet er sant, og kan endres for hånd
etterpå av den som vet hva vakten het.

**Arkivene beholder signaturene sine.** `patients/arkiv.py` bestemmer selv hva som går
inn i `sha_payload()`, så en nullbar FK handleren ikke nevner endrer ingenting.
`ArkivSignaturLaastTests` beviser det — samme resonnement som §12.1 allerede fører for
`Vaktarkivering`. Eksisterende arkiver får `vakt=NULL`; de er fra før grupperingen fantes.

## 5. Konsekvenser for oppdragsmodulens faseplan

**Fase 4b og 5 er upåvirket og kan gjøres nå.** 4b rører `Statusmelding` og en
manager-metode; 5 rører stemplingskroppen og `localStorage`. Ingen av dem tar stilling
til hva en vakt er.

**Fase 6 og 7 er det ikke:**

- **Fase 6** grupperer statistikk. Bygges den på `year`, må hver spørring skrives om når
  scopet endres — og oppdragsfanen ville sammenlignet kalenderår der brukeren mener
  vakter.
- **Fase 7** arkiverer *en vakt*. Den ville lagt inn `Vaktarkivering` fra §12.1, som
  dette notatet foreslår å erstatte med `Vakt` (§2.5).

## 6. Migrasjonen — to deployer

| Deploy | Innhold | Rullbar? |
|---|---|---|
| **1** | Legg til `Vakt`, backfill fra `year`, legg til nullbare `vakt`-FK-er og fyll dem. `year` og `active_year` står urørt og leses fortsatt | Ja |
| **2** | Bytt all lesing til `vakt`, gjør FK-ene `NOT NULL`, fjern `year` fra radene og `active_year` fra `AppSetting` | Kun med `Vakt` som fasit |

Skillet er det samme som i rollemodellen: legg til og fyll først, bytt lesing etterpå.
Slås de sammen, mister en rollback koblingen mellom rad og vakt, og den kan ikke bygges
opp igjen fra `year` alene når flere vakter deler år.

**Deploy 1 må verifiseres i prod før deploy 2** — `python manage.py verifiser_vakt`
etter mønster av `verifiser_modultilgang`: rader uten vakt, vakter uten rader, og
oppdragsnumre som kolliderer innenfor en vakt.

## 7. Åpne avklaringer

1. **Hva heter en vakt, og hvem gir den navnet?** Forslaget er fritekst satt ved
   vaktstart. Alternativet er en mal («\<arrangement\> \<dato\>»), som gir ryddigere
   statistikk men mindre presisjon.
2. **Skal en vakt kunne gjenåpnes etter avslutning?** Arkiveringen er irreversibel, men
   selve vakten kunne vært satt aktiv igjen om noen avslutter for tidlig. Anbefaling: ja,
   så lenge arkivet ikke er kollapset — en feilklikk-avslutning midt i en vakt er ellers
   en katastrofe uten vei tilbake.
3. **Skal pasientnummeret restarte per vakt?** Det gjør det allerede i praksis, via
   nullstillingen (§2.1). Under vakt-scoping blir det eksplisitt. Men merk at
   `pasientnummer` er `unique=True` **globalt** i dag; restart per vakt krever at sperren
   flyttes til `(vakt, pasientnummer)`, altså en migrasjon på en tabell med
   produksjonsdata.
4. **Hva skjer med vakter uten data?** En vakt opprettet ved en feil, uten pasienter
   eller oppdrag, kan slettes fritt (`PROTECT` slipper den). Bør den ryddes automatisk,
   eller står den til noen fjerner den?
5. **Skal statistikken kunne sammenligne på tvers av vakter?** Dagens arkivstatistikk
   sammenligner år. Med vakter blir «forrige tilsvarende arrangement» mer nyttig enn
   «i fjor» — men det krever at vakter kan grupperes, og det er et felt til.

**Akseptansekriterium:** ingen rad i `patients` eller `oppdrag` er uten vakt;
`verifiser_vakt` er grønn; oppdragsnummer er unikt per vakt og restarter på 1;
«Avslutt vakt» rører kun én vakt; alle eksisterende arkivsignaturer verifiserer fortsatt.
