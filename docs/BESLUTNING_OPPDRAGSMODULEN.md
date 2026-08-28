# Beslutningsnotat: oppdragsmodulen

Status: **besluttet 28. aug. 2026, ikke bygget.** Fire åpne avklaringer nederst; ingen av
dem blokkerer fase 1.

Modulen er den første som tar `skriv: handling` i bruk. Nivået ble definert i deploy 1 av
rollemodellen nettopp med denne bruken i tankene (§3.2 i
`docs/BESLUTNING_ROLLEMODELLEN.md`), og har stått tomt siden — «tomt i dag» i CLAUDE.md
peker hit.

**Slettes** når modulen er levert. Da er begrunnelsen CHANGELOG sin.

---

## 1. Hva modulen er

Oppdragshåndtering for bil og beredskapsambulanse under vakt. En operatør på sykestua —
rollen som tilsvarer 113 — oppretter et oppdrag, tildeler det en enhet, og følger enhetens
statusmeldinger. Enheten melder status fra bilen.

Bilen kjører hovedsakelig transportoppdrag; beredskapsambulansen rykker ut. Begge er
samme modell, og forskjellen viser seg i hvilke statuser som faktisk brukes.

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

### 2.1 Bilkontoene er delte kontoer

`haugesund56` er ikke en person. `CustomUser.er_delt_konto` finnes allerede for akkurat
dette: ingen e-post, ingen MFA, ingen selvbetjent passord-reset — admin setter passordet.
Enhetskontoer skal opprettes med det flagget, og valideringen som allerede ligger i
`AdminUserCreateForm` håndhever resten.

## 3. Datamodellen

Tre modeller. Ingen av dem rører `patients`.

### 3.1 `Enhet`

Bilen eller ambulansen. Har et visningsnavn («Haugesund 56») atskilt fra brukernavnet,
fordi et brukernavn er en innloggingsdetalj og et enhetsnavn er noe man sier på samband.

```python
class Enhet(BaseTimeStampedModel):
    navn = models.CharField(max_length=64, unique=True)      # «Haugesund 56»
    user = models.OneToOneField(CustomUser, null=True, on_delete=models.SET_NULL)
    er_aktiv = models.BooleanField(default=True)
```

`SET_NULL`, ikke `CASCADE`: slettes kontoen, skal enheten og dens oppdragshistorikk bestå.
Samme valg som `Forstehjelper.user`, og av samme grunn.

### 3.2 `Oppdrag`

```python
class Oppdrag(BaseTimeStampedModel):
    year = models.IntegerField(db_index=True)         # aktiv vakt, som Patient.year
    enhet = models.ForeignKey(Enhet, on_delete=models.PROTECT)
    problemstilling = models.CharField(max_length=255)   # fra oppdrag/choices.py
    hastegrad = models.CharField(max_length=16)          # Akutt | Haster | Vanlig
    lokasjon = models.CharField(max_length=255)
    fritekst = models.TextField(blank=True, default='')
    status = models.CharField(max_length=16, default='rykker_ut')
    opprettet_av = models.ForeignKey(CustomUser, null=True, on_delete=models.SET_NULL)
```

`PROTECT` på enheten: et oppdrag uten enhet gir ingen mening, og en enhet med historikk
skal ikke kunne forsvinne under den.

**Verdimengdene håndheves server-side**, i `oppdrag/choices.py`, etter mønsteret fra
`patients/choices.py`. Problemstillingene tar utgangspunkt i pasientmodulens liste. De to
listene skal *ikke* dele modul: et oppdrag er ikke en pasient, og den dagen den ene listen
skal endres uten den andre, er en delt konstant det som står i veien.

Hastegradene er AMK-inndelingen — `Akutt`, `Haster`, `Vanlig` — og ikke fargenavn.
Fargekoding i grensesnittet er en presentasjonsdetalj; navnet skal være det personellet
faktisk sier.

### 3.3 `Statusmelding`

Én rad per overgang. Oppdraget bærer gjeldende status som et felt for raske oppslag;
sannheten om *når* noe skjedde ligger her.

```python
class Statusmelding(BaseTimeStampedModel):
    oppdrag = models.ForeignKey(Oppdrag, related_name='statusmeldinger', on_delete=models.CASCADE)
    status = models.CharField(max_length=16)
    tidspunkt = models.DateTimeField()          # hendelsestid, ikke lagringstid
    meldt_av = models.ForeignKey(CustomUser, null=True, on_delete=models.SET_NULL)
    forsinket = models.BooleanField(default=False)   # satt når klienten var frakoblet
```

Egen tabell framfor fem tidsstempelkolonner på `Oppdrag`. Kolonner ville låst modellen til
akkurat disse fem statusene, og en korreksjon fra 113 ville overskrevet historikken i
stedet for å legge seg ved siden av den.

## 4. Statusmaskinen

```
                    ┌──────────────────────────────────────┐
                    │                                      │
(opprettet) → Rykker ut ──→ Fremme ──→ Avreist ──→ Leverer ──→ Ledig
                    │           │                              ▲
                    └───────────┴──────────────────────────────┘
                         avbrutt / ingen transport
```

| Fra | Til |
|---|---|
| *(oppretting)* | `Rykker ut` |
| `Rykker ut` | `Fremme`, `Ledig` |
| `Fremme` | `Avreist`, `Ledig` |
| `Avreist` | `Leverer` |
| `Leverer` | `Ledig` |
| `Ledig` | *(ingen — terminal)* |

Overgangstabellen ligger i `oppdrag/services.py` som data, ikke som `if`-er spredt i
viewene, og håndheves server-side. Grensesnittet viser kun de knappene som er lovlige, men
det er ikke der regelen bor: en knapp som ikke vises er ikke en knapp som ikke kan trykkes.

**«Ledig» er enhetens tilstand, ikke oppdragets — og det er verdt å være bevisst på.**
Statusen betyr «denne enheten er fri igjen», og den avslutter oppdraget. Å lagre
tilgjengelighet *også* på `Enhet` ville gitt to kilder til samme sannhet, og de ville gått
i utakt første gang noe feilet halvveis. En enhet er ledig når den ikke har et oppdrag i
en ikke-terminal status. Utledes, lagres ikke.

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
| `POST /oppdrag/api/oppdrag/<pk>/status/<overgang>/` | `skriv_handling` | Enhet må eie oppdraget |

### 5.1 Stemplingsendepunktet leser (nesten) ingenting

§3.2 slo fast at et `handling`-endepunkt ikke skal lese request-kroppen, og at invarianten
er testbar. Offline-kravet bryter den bokstavelig: en stempling som ble utført uten nett må
kunne fortelle *når* den skjedde, ellers viser statistikken når dekningen kom tilbake.

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

**Overgangen ligger i URL-en, ikke i kroppen.** `POST .../status/fremme/` er en navngitt
handling; `POST .../status/` med `{"status": "fremme"}` ville gjort den til en redigering
med ett felt.

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

Et avsluttet oppdrag forsvinner **30 minutter etter `Ledig`**. Det er et visningsfilter,
aldri sletting: sentralbordet og statistikken beholder raden. Vinduet er kort med vilje —
en bil kan stå ulåst — og feil kan korrigeres av 113 i etterkant, over nødnett eller
ansikt til ansikt.

## 8. Personvern

To punkter fra TODO faller inn her, og begge må være på plass **før fritekstfeltet ships**:

1. **Fritekst skal unntas verdilogging i audit.** `AuditLog.old_value`/`new_value` er
   `TextField` med 730 dagers lagring, og feltlista utledes fra modellen (N2) — et nytt
   fritekstfelt havner der av seg selv. Skriver en operatør noe sensitivt og retter det,
   ligger begge versjonene i loggen i to år. Signalet trenger en opt-out per felt: at
   *feltet ble endret* logges, verdiene gjør det ikke.
2. **Protokollen må presiseres.** A.6/A.12 i `docs/PERSONVERN_DOKUMENTASJON.md` begrunner
   whitelisten med at kliniske felt ikke kan inneholde navn. Det argumentet bærer ikke her:
   «kvinne, pustevansker, Storgata 5, 22:40» er mer identifiserende enn pasientraden det
   knytter seg til, og lokasjon er et nytt felt uten fortilfelle i protokollen.

## 9. Frontend

Egen side, egne filer. Reglene i CLAUDE.md gjelder og håndheves av eksisterende tester:

- **`patients-utils.js` kan ikke lastes.** Den gjør arbeid på toppnivå og kaster på en side
  uten pasientskjemaene. Trengs en helper derfra, flyttes den til `portal-utils.js`.
  `JsModulLastingTests` sammenligner hva en side kaller mot hva den laster.
- **Eget stilark** som definerer de fire variablene `base_portal` ikke aliaser
  (`--text-muted`, `--text-soft`, `--surface-3`, `--header-bg`), og ikke gjentar de fire
  den faktisk setter. `statistikk.css` er mønsteret.
- **Brukerdata som settes inn med `innerHTML` escapes.** Fritekst og lokasjon er
  fritekstfelt fra en operatør — første virkelige XSS-flate i portalen som ikke er en
  nedtrekksliste.

To maler, ikke én med `{% if %}` gjennom hele: `oppdrag/enhet.html` og
`oppdrag/sentral.html`. De deler nesten ingen markup, og en sammenslått mal ville vært to
layouter i én fil for å spare en `render`-linje.

## 10. Faser

| Fase | Innhold | Estimat |
|---|---|---|
| 1 | App, modulregistrering, tre modeller, `choices.py`, admin-matrise. Ingen UI | 4–6 t |
| 2 | Audit-unntak for fritekst + protokolltillegg. **Før fase 3** | 2–3 t |
| 3 | Sentralbordet: opprett, tildel, liste, rediger. Polling med ETag | 6–8 t |
| 4 | Enhetsskjermen: statusmaskin, smale endepunkter, objektsjekk, 30-min-filter | 5–7 t |
| 5 | Offline-kø med idempotens | 4–6 t |
| 6 | Arkivering: `AbstractArkiv` + handler for oppdrag | 4–6 t |

Fase 2 står før fase 3 fordi fritekstfeltet ellers ville vært i produksjon med
verdilogging på, og de radene kan ikke fjernes i ettertid uten å røre auditsporet.

**Fase 6 er stedet `AbstractArkiv` endelig skal bygges.** TODO har utsatt den til «modell
nummer to faktisk skrives» — dette er modell nummer to. `VaktArkiv` skal *ikke* migreres
til basemodellen: SHA-signaturene er låst til dagens payload-form, og hvert eksisterende
arkiv i prod ville meldt tukling.

## 11. Åpne avklaringer

1. **Kan 113 flytte et pågående oppdrag til en annen enhet?** Antatt ja, med auditrad. Da
   må det avgjøres hva som skjer med statusmeldingene den første enheten rakk å sende —
   forslag: de blir stående, fordi de faktisk skjedde.
2. **Skal en enhet kunne ha to oppdrag samtidig?** Antatt nei i v1. Sier vi ja, må
   enhetsskjermen kunne vise flere og «ledig» blir tvetydig.
3. **Arkiveres oppdrag sammen med vakta, eller for seg?** `core.arkiv` er per modul, så
   teknisk hver for seg. Om admin skal ha én knapp som arkiverer begge, er et
   grensesnittspørsmål som kan tas i fase 6.
4. **Skal `Leverer` registrere hvor det leveres?** I dag et fritekstfelt. Blir det en
   nedtrekksliste (sykestua, legevakt, sykehus), er det statistikk verdt å ha — og et felt
   til i personvernvurderingen.
