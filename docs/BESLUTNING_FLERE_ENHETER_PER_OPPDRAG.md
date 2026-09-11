# Beslutningsnotat: flere enheter på ett oppdrag

Status: **utkast 11. sep. 2026, ikke besluttet.** Skrevet før kode, slik de andre
fasene ble. Fire åpne spørsmål nederst; ingen kode før André har svart på §7.1.

Bestillingen (prosjektleder, via André 11. sep. 2026):

> Når «AMK-operatøren» lager oppdrag må den kunne krysse på flere enheter og så gi
> oppdraget til flere enheter. De andre enhetene må kunne se hvem som er varslet men ikke
> nødvendigvis deres status. Mens «AMK-operatørene» kan se alt.

Og som alternativ i samme punkt: «dupliser oppdrag for å kjapt kunne lage for flere
enheter». **Dupliser er forkastet** til fordel for dette: to oppdrag med samme
problemstilling er to ting å lukke, to ting å arkivere, og to steder statistikken teller
responstid på samme hendelse.

---

## 1. Hva som er sant i dag, og hva som må snus

`Oppdrag` er «tildelt én enhet» — én FK, `Oppdrag.enhet`. Alt annet hviler på det:

| Hva | Hvor | Antakelsen |
|---|---|---|
| Statusmeldingene | `Statusmelding.oppdrag` | én kjede per oppdrag |
| Statuscachen | `Oppdrag.status` | siste melding *er* oppdragets status |
| Enhetens status | `services.enhet_status` → `aktivt_oppdrag(enhet)` | `enhet.oppdrag` er enhetens oppdrag |
| Hva bilen ser | `services.synlige_for_enhet` | `enhet.oppdrag` |
| Stemplingen | `stempling_view`: `oppdrag.enhet_id == request.user.enhet.pk` | eieren er én |
| Auto-lukking | `start_oppdrag`: lukker enhetens *pågående* | ett pågående per enhet |
| Overføring | `Enhetsbytte`, `flytt_til_enhet` setter `oppdrag.enhet` | fra én til én |
| Arkivet | `ArkivertOppdrag.enhet_navn` + fem tidsstempelkolonner | én kjede per rad |
| Statistikken | responstid per rad, `per_enhet` på `enhet_navn` | samme |

Det er ikke ett sted å endre; det er en antakelse som ligger i ni. Derfor et notat.

## 2. Modellen

### 2.1 `Oppdragsenhet` — koblingsraden

```
Oppdragsenhet
  oppdrag      FK Oppdrag (CASCADE)        related_name='enheter'
  enhet        FK Enhet   (PROTECT)        related_name='oppdragsenheter'
  varslet_at   DateTimeField               når enheten ble satt på
  varslet_av   FK bruker (SET_NULL)
  status       CharField (STATUS_VALG)     cache, som Oppdrag.status i dag
  rekkefolge   PositiveSmallIntegerField   den første er «primær» — se §2.3
  unique (oppdrag, enhet)
```

**Statusmeldingene flytter til koblingsraden.** `Statusmelding.oppdragsenhet` erstatter
`Statusmelding.oppdrag` som den meningsbærende nøkkelen — en melding er *én enhets*
utsagn om *ett* oppdrag. `Statusmelding.oppdrag` beholdes som avledet kolonne for
spørringer (`gjeldende_bulk` går på oppdrag i dag), og settes fra koblingsraden.

### 2.2 `Oppdrag.status` blir utledet

Cachen står, men betyr «det mest aktive av enhetenes statuser»: står én bil i `Fremme`
og én i `Ledig`, er oppdraget i `Fremme`. Rekkefølgen er `KJEDEN` baklengs — `Leverer`
> `Avreist` > `Fremme` > `Rykker ut` > `Venter` — og `Ledig` teller bare når alle er
der. Lista sorteres på den som i dag. Detaljvisningen viser hver enhet for seg.

**Oppdraget er ferdig når alle enhetene er ledige.** Historikk-flyttingen
(`sett_status` → `historikk_fra`) skjer da, ikke ved første `Ledig`.

### 2.3 `Oppdrag.enhet` forsvinner — i to deploys

Kolonnen tas ut av modellen, og «primær enhet» er `Oppdragsenhet` med lavest
`rekkefolge`. Den finnes som begrep bare fordi arkivet og statistikken i dag har én
`enhet_navn` per rad — se §5.

Som med `year` → `vakt`: **deploy 1** legger til koblingsraden og fyller den fra
`Oppdrag.enhet`, og lar kolonnen stå; **deploy 2** fjerner den når koden ikke leser den
lenger. Én migrasjon som både backfyller og dropper kolonnen er nettopp det
`0007`-mønsteret advarer mot, og det er uansett ikke noe man angrer på uten backup.

## 3. Reglene

| Spørsmål | Svar |
|---|---|
| Hvem ser hva på bilen | Sitt eget oppdrag som før, pluss **navnene** på de andre varslede — «Varslet: HGSD 56, KARM 12». Ikke deres status (§7.3). |
| Hvem ser hva i sentralbordet | Matrisen: hvert oppdrag med hver enhet og dens status og tidslinje. |
| Stempling | `stempling_view` finner enhetens `Oppdragsenhet` på oppdraget; finnes den ikke, 403 som i dag. Endepunktene er de samme — bilen vet ikke at oppdraget har flere. |
| Auto-lukking | Per enhet: «Rykker ut» på et nytt oppdrag lukker *enhetens* pågående koblingsrad, ikke oppdraget. |
| Overføring | `Enhetsbytte` flytter én koblingsrad fra én enhet til en annen. Formen beholdes. |
| Legge til en enhet senere | «Varsle enhet» på oppdraget i sentralbordet, `skriv_full`. Ny koblingsrad i `Venter`. |
| Ta en enhet av | Bare mens koblingsraden står i `Venter` — har bilen rykket ut, er det en hendelse, og da er svaret `Ledig` fra bilen eller en korreksjon. |
| Offline-køen | Uendret. Køen bærer `oppdragId` + overgang; serveren finner koblingsraden. |
| Enhetens status (`enhet_status`) | Utledes av enhetens koblingsrader i stedet for `enhet.oppdrag`. Samme regel. |

## 4. Endepunktene

- `POST api/oppdrag/` tar `enhet_ider: [..]` (minst én). `enhet_id` godtas fortsatt og
  betyr én — gamle klienter og tester skal ikke brekke.
- `POST api/oppdrag/<pk>/enheter/<enhet_pk>/` — varsle en enhet til. `skriv_full`.
- `DELETE api/oppdrag/<pk>/enheter/<enhet_pk>/` — ta av, bare i `Venter`. `skriv_full`.
- `oppdrag_til_dict` får `enheter: [{enhet_id, enhet_navn, status, status_navn,
  status_tidspunkt}]`. `enhet_id`/`enhet_navn` på toppnivå beholdes som primær.
- For bilen (`for_enhet=True`): egen koblingsrad som `status`/`neste_overgang` som i dag,
  og `varslede: ['HGSD 56', 'KARM 12']` — bare navn.

## 5. Arkivet og statistikken — den avgjørende beslutningen

`sha_payload` er låst: «Endres denne, verifiserer ingen arkiv igjen.» Radene er
`ArkivertOppdrag` med **ett** `enhet_navn` og fem tidsstempler. To veier:

**A. Én arkivrad per oppdrag × enhet.** `oppdragsnummer` gjentas for hver enhet, hver
rad har sin enhets tidsstempler. Payloaden er *samme form* — samme felter, samme sortering
(sortert på `oppdragsnummer`, og `enhet_navn` som andre nøkkel for at to rader med samme
nummer skal ligge stabilt). Gamle arkiver har én rad per oppdrag og verifiserer som før.
Statistikken teller *oppdrag* som distinkte `oppdragsnummer` og *responstider* per rad —
som er riktig: responstiden er bilens, ikke oppdragets.

**B. Én rad per oppdrag med enhetene som liste.** Ny form, versjonert payload, to
kodeveier i `sha_payload` for all framtid.

**Forslaget er A.** Det endrer ingenting for eksisterende arkiver, og det er den formen
tallene faktisk har. Prisen er at «antall oppdrag» i statistikken må telle distinkt, og at
det står i notatet så neste person ikke «retter» det.

## 6. Migrasjonen og deployen

1. `0010`: `Oppdragsenhet` + nullbar `Statusmelding.oppdragsenhet`.
2. `0011` (`RunPython`, egen migrasjon): én koblingsrad per oppdrag fra `Oppdrag.enhet`,
   meldingene pekes på den. `SET CONSTRAINTS ALL IMMEDIATE` før skjemasteget i `0012`.
3. `0012`: `Statusmelding.oppdragsenhet` blir `NOT NULL`.
4. Prøve i `core/migrasjonsprover.py` med rader i den historiske formen — regelen fra
   30. aug.
5. **Backup av prod før pushen** — Andrés regel for enveismigrasjoner.
6. Deploy 2, senere: `Oppdrag.enhet` fjernes.

## 7. Åpne spørsmål — svar før kode

### 7.1 Arkivrad per oppdrag × enhet (§5 A)?
Det ene valget som ikke lar seg gjøre om uten å versjonere payloaden. **Anbefaling: A.**

### 7.2 «Ferdig» = alle enheter ledige?
Alternativet er «ferdig når primær er ledig», og da rydder tavla mens KARM 12 fortsatt
kjører. **Anbefaling: alle.**

### 7.3 Skal bilen se de andres status?
Prosjektleder: «ikke nødvendigvis». Navnene koster ingenting og hjelper på samband
(«HGSD 56 er også varslet»); statusen er sentralbordets bilde, og to biler som leser
hverandres status over en skjerm i stedet for over nødnett er ikke noe vi vil oppmuntre.
**Anbefaling: bare navn.**

### 7.4 Kan en enhet tas av etter «Rykker ut»?
**Anbefaling: nei** — det er en hendelse, og hendelser lukkes med `Ledig` eller rettes.

## 8. Anslag

Fire trinn, hvert med tester og grønn suite før neste:

| Trinn | Innhold | Anslag |
|---|---|---|
| 1 | Modell, migrasjoner, prøve, `services` (status per enhet, utledet oppdragsstatus, auto-lukking per enhet, overføring) | 5–6 t |
| 2 | Endepunkter og bilen: `enhet_ider`, varsle/ta av, stempling via koblingsrad, `varslede` | 3–4 t |
| 3 | Sentralbordet: avkryssing ved opprettelse, matrisen i lista og detaljvisningen, «Varsle enhet» | 3–4 t |
| 4 | Arkiv (rad per enhet) og statistikk (distinkte oppdrag, responstid per rad) | 3 t |

Rundt to arbeidsdager. Deploy 2 (fjerne `Oppdrag.enhet`) er en halvtime, senere.
