# Plan: backup-løsningen lagt om

Status: **plan, 13. september 2026, versjon 2 — Andrés fem svar innarbeidet.**
Ingenting er bygget. Denne planen skal være klar før noe iverksettes.

Bestillingen: modulenes backup og gjenoppretting er tungvint, intervallet skal kunne
settes fritt i minutter, timer og dager for å kunne tilpasses den enkelte vakt og holde
risikoen for datatap lav, det skal finnes cap på antall backuper for både moduler og hel
database, det samme oppsettet skal gjelde den hele databasen, leveransen til Scaleway skal
være lik for begge, gjenoppretting skal kunne gjøres både fra Railway CLI og fra
grensesnittet, og det skal finnes en instruks for at hele basen slettes etter 90 dager
mens modulene beholdes i 730.

Underlaget er `docs/BACKUP.md` (hva som skal finnes) og `docs/TEKNISK_GJELD.md` §4
(hullene). Dette notatet er **hvordan**. Rekkefølgen mot resten av arbeidet står i
`docs/PLAN_REKKEFOLGE_2026-09.md`.

---

## 1. Hva som faktisk er tungvint i dag

Målt på koden:

| Handling | Hva det koster nå |
|---|---|
| Ta backup av alt | Fire runder: oversikt → modulside → «Kjør backup» → tilbake, én gang per modul. Ingen knapp tar alle |
| Gjenopprette en modul | Fem steg: oversikt → modulside → finn fila i en liste på 200 → gjenopprettingsside → skriv modul-slugen → send |
| Gjenopprette fra kommandolinja | **Finnes ikke.** `hent_offsite` henter og dekrypterer fila, men skriver «gjenopprett fra /portal-admin/backup/». Siste halvdel av veien er kun nettleser |
| Endre intervall | Én side per modul, og intervallet er et nedtrekk med sju faste valg. Hvert 10. minutt finnes ikke, og «hver tredje dag» finnes ikke |
| Se om det virker | «Sist kjørt» sier når det sist ble *skrevet en fil*. Sto innholdet stille, står tidspunktet stille — og det ser likt ut som en jobb som har stoppet |

Og tre funn som er verre enn tungvint:

**1.1 Klokka er trafikk.** `BackupSchedulerMiddleware` kjører sjekken etter hver
forespørsel, throttlet til én gang per 60 sekunder per prosess. **Kommer det ingen
forespørsel, tas ingen backup.** Mellom vaktene står portalen stille, og da står backupen
også stille.

**1.2 Det finnes ingen backup-cron i prod — bekreftet.** André, 13. sep.: Railway har
**to** cron-tjenester, `purge_old_logs` og `kollaps_arkiv`. `db_backup` er ikke satt opp.
Tre følger av det:

- **Alle backuper prod har tatt, er tatt av web-trafikk.** Sammen med 1.1 betyr det at
  dekningen følger når folk er innlogget. Under vakt er det godt nok; mellom vaktene tas
  det ingenting — og en hel databasebackup som skal gå hver 24. time, ville ikke gått.
- `CRON_JOBBER` i `core/kommando.py` lister `db_backup`, så
  `/portal-admin/server-status/` viser **«Aldri»** for en jobb som aldri kommer til å
  kjøre. Et varsel som alltid står rødt lærer deg å ikke se på dashbordet.
- `CLAUDE.md` påstår at tre jobber kjøres av Railway Cron. Det er feil, og rettes.

**1.3 `restore_models` vedlikeholdes for hånd.** Hver handler lister modellene som skal
slettes før `loaddata`, i barn-først-rekkefølge. Glemmer du én, blir radene stående igjen
etter en gjenoppretting — gjeldspunkt 3.4 (`Lydvarsel`) er symptomet. Feilen er at lista
kan være ufullstendig uten at noe sier fra.

## 2. Planen som styrer alt: modus, intervall, cap

`core.ModuleBackupConfig` erstattes av én modell som gjelder like mye for de seks
modulfilene som for den hele databasen:

```python
class Backupplan(models.Model):          # core
    slug              # modul-slug, 'full', eller 'standard' (malen de andre arver)
    folger_standard   # bool — modulen bruker standardplanen
    modus             # 'av' | 'ved_endring' | 'alltid'
    intervall_verdi   # fritt heltall
    intervall_enhet   # 'minutt' | 'time' | 'dogn'
    behold            # cap: antall filer på volumet
    sist_sjekket_at   # når planen sist ble vurdert
    sist_fil_at       # når det sist ble skrevet en fil
    sist_resultat     # 'ny' | 'uendret' | 'feil: …'
```

### 2.1 De tre modusene

| Modus | Hva som skjer hvert intervall | Når den er riktig |
|---|---|---|
| **Av** | Ingenting automatisk. Manuell knapp virker fortsatt | Moduler som ikke er i bruk |
| **Ved endring** | Serialiser, sammenlign SHA-256 mot forrige fil. Lik → ingen fil, ingen opplasting | Modulene. Se §2.4 |
| **Alltid** | Skriv en fil hver gang, uansett om innholdet er likt | Hel database. Se §5.3 |

Skillet er hele svaret på «mer kontroll»:

> **«Ved endring» er effektiv, men stum.** Står det ingen ny fil, kan det bety at
> ingenting har endret seg — eller at jobben er død. De to ser like ut utenfra.
> **«Alltid» er en puls:** hver fil er et bevis på at jobben kjørte, og et hull i rekka er
> en feil du ser med øynene.

Derfor oppdateres `sist_sjekket_at` ved **hver vurdering**, ikke bare når det skrives en
fil. Grensesnittet sier da

> *Sjekket 14:05 · siste fil 11:30 (uendret siden da)*

og det er ikke lenger mulig å forveksle «stille» med «stoppet». Det er en billigere puls
enn å skrive 96 like filer i døgnet.

### 2.2 Intervall i minutter, timer eller døgn

Tall pluss enhet, begge fritt valgt. Enheten lagres slik du satte den, og minuttene regnes
ut når scheduleren trenger dem:

```python
@property
def intervall_min(self) -> int:
    return self.intervall_verdi * {'minutt': 1, 'time': 60, 'dogn': 1440}[self.intervall_enhet]
```

Grunnen til at enheten lagres og ikke bare minuttene: setter du «3 døgn» og får «4320
minutter» tilbake neste gang du åpner siden, må du regne for å lese din egen innstilling.
Intensjonen er verdt en kolonne.

To ting står i grensesnittet framfor å bli sperret:

- **Oppløsningen er tikken.** Klokka (§3) spør «er noe forfalt?» med et fast mellomrom.
  Setter du 3 minutter og tikken er 5, får du 5. Feltteksten sier hva tikken faktisk er.
- **Konsekvensen regnes ut mens du skriver:** *«Hvert 15. minutt = 96 filer i døgnet, ca.
  35 000 i året offsite. Anslått diskbruk med cap 50: 12 MB.»* Med 730 dagers oppbevaring
  offsite er antallet filer tallet som betyr noe, ikke minuttene.

Ingen sperre utover at verdien må være minst 1. Det følger portalens egen linje fra
vaktlistas belastningstall: **varsle, ikke avvis.** Du vet når du trenger å bryte en
tommelfingerregel.

### 2.3 Cap, og hvorfor cap og oppbevaring er to forskjellige ting

`behold` er et fritt tall per plan, for moduler og hel database likt. Etter hver vellykket
skriving slettes de eldste filene for den planen til antallet er nede i `behold`.
Pre-restore-øyeblikksbilder telles ikke og slettes ikke — de er sikkerhetsnettet.

**Men cap gjelder bare volumet på Railway.** Det er verdt å si rett ut, for de to tallene
leses lett som ett:

| | Hvem sletter | Hvor lenge |
|---|---|---|
| **Volumet på Railway** | `behold` i planen | Til antallet overstiges |
| **Bucketen hos Scaleway** | Livssyklusregelen (§7) | 730 dager (moduler) / 90 dager (hel base) |

Portalens IAM-nøkkel hos Scaleway har **ikke** sletterett — det ble bevisst satt slik
13. sep. Det har en pen konsekvens: en kompromittert portal kan ikke slette backupene
våre, og oppbevaringen offsite håndheves av plattformen alene. Det betyr også at
`behold = 7` aldri fjerner noe fra bucketen. Kortet på siden sier begge tallene ved siden
av hverandre, slik at «behold 7» ikke leses som «det finnes bare 7».

Én ting cap faktisk beskytter mot: **et fullt volum.** Går volumet tomt, kan portalen ikke
skrive — heller ikke backup. Siden viser derfor `shutil.disk_usage(BACKUP_DIR)` med
anslått forbruk for de valgte innstillingene, så en cap på 500 med timesintervall er
synlig som et tall før den blir en hendelse.

### 2.4 Tilpasning til den enkelte vakt

Du skrev at intervallet skal kunne tilpasses den enkelte vakt, for å holde risikoen for
datatap lav. Jeg vil anbefale å løse det med **modusen framfor med to intervaller**, og
grunnen er at det virker av seg selv:

> **«Ved endring» med kort intervall er allerede vaktadaptiv.** Under vakt endrer
> pasienter og oppdrag seg hele tiden, så et intervall på 10 minutter gir en fil hvert
> 10. minutt. Mellom vaktene endres ingenting, så det skrives ingenting — ingen filer,
> ingen opplasting, ingen plass. Du får tett dekning når det er noe å miste, og null støy
> når det ikke er det, uten å endre en innstilling.

**Vurdert og lagt bort:** to intervaller per plan, «under vakt» og «ellers», som slår om
av seg selv. Det høres riktig ut, men signalet er dårlig: `Vakt.er_aktiv` står på til noen
avslutter vakta, og gjør den ikke det, står portalen i «under vakt» i ukevis.
Vaktlistas `status == 'drift'` er et ærligere signal, men `core` skal ikke importere en
modul — det er feil vei i avhengighetene. Og en manuell vaktbryter flytter bare problemet:
den man glemmer å slå av, er verre enn den som aldri fantes.

Trenger du likevel noe annet for én enkelt vakt, er det to felt å endre på
standardplanen, og alle modulene følger med.

**Anbefalte standardverdier**, som alle kan endres fra siden:

| Plan | Modus | Intervall | Cap |
|---|---|---|---|
| Standard (modulene arver) | Ved endring | **10 minutter** | 50 |
| Arkivene (`arkiv`, `oppdrag_arkiv`) | Ved endring | 6 timer | 20 |
| Hel database | Alltid | **24 timer** | 7 |

Arkivene endres én gang per arrangement; å spørre dem hvert 10. minutt er å serialisere
hele arkivtabellen 144 ganger i døgnet for å finne ut at ingenting skjedde.

### 2.5 Hva du taper i verste fall — regnet ut og vist fram

Det du egentlig ber om er ikke et intervall, det er en øvre grense for hvor mye arbeid som
kan gå tapt. Siden regner den ut og viser den:

> **Verste tilfelle hvis Railway forsvinner nå:**
> pasienter 4 min · oppdrag 4 min · vaktliste 9 min · brukere og logg 6 t

Ett krav til den utregningen, og det er det som gjør den sann: den skal måles på **siste
vellykkede opplasting til Scaleway** (`OffsiteKopi.sendt_at` med tom `feil`), ikke på
siste fil på volumet. Er volumet borte, er det bare bucketen som teller. En linje som
leser volumet ville vist fire minutter mens den virkelige avstanden var to dager fordi
opplastingene har feilet siden i forgårs.

## 3. Klokka: en tikk som ikke avhenger av trafikk

Ny kommando `python manage.py backup_kjor`, satt opp som Railway Cron-tjeneste ved siden
av de to som står der:

```
backup_kjor   python manage.py backup_kjor   */5 * * * *
```

Kommandoen spør databasen hva som er forfalt og kjører det. **Intervallene ligger i basen,
ikke i cron-uttrykket.** Det er hele poenget: du endrer «hver time» til «hvert 20. minutt»
i portalen, uten å røre Railway og uten en deploy.

Tre ting den arver fra resten av portalen:

- `lesbar_dbfeil('ingen backup ble tatt', navn='backup_kjor')` — én lesbar linje i
  cron-loggen i stedet for fire tracebacks, og `AppSetting['cron.backup_kjor']` skrevet
  både når det gikk og når det ikke gikk, så server-status viser den.
- `select_for_update(nowait=True)` på planraden som i dag, så to tikker som overlapper
  ikke lager to filer.
- `CRON_JOBBER` bytter `db_backup` mot `backup_kjor` **i fase 1**, ikke i oppryddingen —
  ellers står dashbordet og lyver en fase lenger.

**Middlewaren blir stående som reservenett**, skrevet om til å kalle samme funksjon.
Faller cron-tjenesten ut, tar trafikken over; står portalen stille, tar cron det. Begge går
gjennom den samme låsen, så det koster ingenting å ha begge.

> **Sjekk ved oppsett:** hva Railway tillater som minste cron-intervall. Det tallet blir
> gulvet for oppløsningen i §2.2 og skal stå i feltteksten. Ikke anta `*/5`.

## 4. Modulløsningen forenklet

### 4.1 Én side, ikke N

`/portal-admin/backup/` blir én side. Modulsidene og gjenopprettingssiden legges ned.

```
┌─ Hel database ──────────────────────────────────────────────┐
│ Alltid · hver 24. time · behold 7      [Endre] [Ta nå]       │
│ Siste: 13.09 03:00 (4,2 MB) · offsite OK · neste ca. 03:00   │
└──────────────────────────────────────────────────────────────┘
┌─ Verste tilfelle nå ────────────────────────────────────────┐
│ pasienter 4 min · oppdrag 4 min · vaktliste 9 min           │
│ brukere og logg 6 t          (målt mot siste offsite-kopi)  │
└──────────────────────────────────────────────────────────────┘
┌─ Offsite (Scaleway) ────────────────────────────────────────┐
│ Aktiv · bucket sanitet-backup · 1 284 filer · sist 03:01     │
│ Oppbevaring: backups/ 730 dager · full/ 90 dager             │← lest fra bucketen
│ Volum: 310 MB brukt av 1 GB                                  │
└──────────────────────────────────────────────────────────────┘
┌─ Moduler ──────────────────────── [Ta backup av alle nå] ───┐
│ Standardplan: Ved endring · hvert 10. minutt · behold 50 [✎] │
│                                                              │
│ Pasienter          følger standard  11:30 ny      42 filer ▾ │
│ Pasientregistre…   egen: hver 6. t  09:00 uendret  8 filer ▾ │
│ Oppdrag            følger standard  11:30 ny      41 filer ▾ │
│ Vaktliste          følger standard  11:30 uendret 12 filer ▾ │
└──────────────────────────────────────────────────────────────┘
```

Fire grep gjør jobben:

1. **Standardplanen.** Modus, intervall og cap settes **ett sted**, og alle modulene følger
   den. Vil én modul noe annet, hukes «egen plan» av på den raden. Med seks modulfiler er
   det forskjellen på å vedlikeholde tre tall og atten.
2. **«Ta backup av alle nå»** — én knapp, alle modulene og den hele fila.
3. **Fillista er inline** (`▾` folder ut raden), ikke en egen side. De 20 nyeste, med «vis
   alle» under.
4. **«Gjenopprett siste»** per modul, fordi det er det man vil i ni av ti tilfeller.
   Eldre filer ligger i den utfoldede lista.

Bekreftelsen blir stående — den er ikke det som er tungvint. Men den flytter inn i en
dialog på samme side, og teksten sier hva som skjer: *«N rader i M tabeller slettes og
erstattes. Et pre-restore-øyeblikksbilde tas først.»* Antallet hentes fra basen når
dialogen åpnes. Å skrive modul-slugen beholdes som andre sperre, slik
`{"confirm": true}`-mønsteret ellers i portalen.

### 4.2 `restore_models` utledes

`BaseBackupHandler.get_restore_models()` **regner ut lista selv** når handleren ikke har
oppgitt den: alle modellene i `apps` minus `exclude`, topologisk sortert på fremmednøkler
slik at barn kommer først. `restore_models` beholdes som overstyring der rekkefølgen ikke
kan utledes (selvreferanser som `Statusmelding.erstatter`).

To gevinster, og den andre er den store:

- Modul nummer seks og sju slipper å skrive lista.
- **En modell kan ikke lenger være i dumpen uten å være i slettelista.** Gjeldspunkt 3.4
  (`Lydvarsel`) forsvinner, og kan ikke oppstå igjen.

Pluss en test som for hver registrerte handler serialiserer og krever at hver modelletikett
i dumpen finnes i `get_restore_models()`. Billig, og den fanger feilen for alle framtidige
moduler.

### 4.3 De to manglende handlerne

Fra `BACKUP.md` §3, uendret:

- **`vaktliste`** — alle modellene, `Mannskap.user` og `Utsending.sendt_av` strippet. Dette
  er den største udekkede datamengden i dag: korps, mannskap med telefon, e-post og ISSI,
  kompetanser, ressurser, vaktposter og belastningsgrensene.
- **`portal`** — `core.Vakt`, `core.ModuleSettings` og (etter flyttingen i
  `TEKNISK_GJELD.md` §2) `AppSetting`. Uten `Vakt` kan ingen av de andre filene
  gjenopprettes i en tom base: pasienter og oppdrag peker på den med fremmednøkkel.

## 5. Den hele databasebackupen

### 5.1 Hva som er med

Én handler, `slug='full'`, med samme plan-modell, samme moduser, samme intervallenheter og
samme cap som modulene.

| Med | Utelatt, og hvorfor |
|---|---|
| Alle appene: brukere med passordhasher, MFA-enheter og reservekoder, `ModulTilgang`, audit- og innloggingslogg, varsler, `Vakt`, alle modulenes data og alle arkivene | `sessions` — innlogginger som uansett er utløpt |
| | `contenttypes` og `auth.Permission` — gjenskapes av `migrate`, og lastes de på nytt kolliderer primærnøklene |
| | `Backup`, `OffsiteKopi`, `Backupplan` — metadata om backupfiler. Å laste dem tilbake ville gjenopplive rader for filer som ikke finnes |
| | `admin.LogEntry` — Django-admin er av i prod (S1) |

Serialiseres med `natural_foreign` og `natural_primary`, som modulfilene.

### 5.2 Gjenoppretting er `flush` + `loaddata`

For modulene er slett-i-rekkefølge riktig, fordi resten av basen skal stå urørt. For hele
databasen er det feil verktøy: det er over hundre modeller på tvers av sju apper, og
rekkefølgen mellom dem er nettopp det ingen skal måtte vedlikeholde. `flush` tømmer alt og
lar `migrate`s post-hooks gjenskape contenttypes og permissions først.

**Og du blir logget ut.** Sesjonene ligger i databasen, og `flush` tar dem. Brukerraden du
er logget inn som slettes og lastes inn igjen fra fila — kanskje med et annet passord enn
det du logget inn med. Det skal stå i dialogen med rene ord:

> *Du blir logget ut. Logg inn igjen med passordet som gjaldt da backupen ble tatt.*

Feiler `loaddata`, rulles alt tilbake i samme transaksjon, og du står der du sto.

### 5.3 Hvorfor «alltid» med langt intervall er riktig her

En hel base endrer seg konstant — audit-loggen vokser ved hver forespørsel. «Ved endring»
ville derfor aldri hoppe over noe, og du får en fil hvert intervall uansett. Da er «alltid»
det ærlige valget: du ser at det er det du har bedt om.

Intervallet er et regnestykke, ikke en smakssak: fila er hele basen, og oppbevaringen er
90 dager. Hver 24. time gir 90 filer offsite. Hver time gir 2 160. **Standard blir hver 24.
time med cap 7 lokalt**, som avtalt — og heller en manuell «Ta nå» før en deploy eller en
risikofylt migrasjon, slik du uansett gjør før merge til prod.

## 6. Leveransen til Scaleway

### 6.1 Rekkefølgen er komprimering, så kryptering — ikke omvendt

Du skrev «kryptering og så komprimering». Det er den ene rekkefølgen som ikke virker, og
feilen er usynlig: **kryptert data lar seg ikke komprimere.** AES-256-GCM produserer bytes
som er statistisk umulige å skille fra tilfeldig støy, og komprimering lever av å finne
gjentakelser. Gzip på en kryptert fil gir null gevinst — i praksis noen byte *større*, på
grunn av gzips eget hode. Komprimerer du først, jobber gzip på JSON, som er svært
repetitivt: en dumpdata-fil krymper typisk til 5–15 % av rå størrelse. Deretter krypterer
du det lille resultatet.

Dagens kode gjør allerede dette riktig, og det beholdes:

```
dumpdata → JSON → gzip (nivå 6) → fil på volumet
                                → les → AES-256-GCM → last opp som <navn>.enc
```

(Den kjente innvendingen mot å komprimere før kryptering er kompresjonsorakel-angrep av
CRIME/BREACH-typen. De forutsetter at en angriper kan sprøyte valgt tekst inn i samme strøm
og måle chiffertekstens lengde mange ganger. En backupfil skrevet én gang og lastet opp én
gang er ikke det scenarioet.)

### 6.2 Ett prefiks per oppbevaringstid

Fristene kan bare skilles i bucketen hvis filene ligger på hver sin sti:

| Prefiks | Innhold | Frist |
|---|---|---|
| `backups/` | De seks modulfilene, som i dag | 730 dager |
| `full/` | Hele databasen | 90 dager |

`core/offsite.py` henter prefikset fra backupens slug i stedet for konstanten `PREFIKS`, og
`hent_offsite --list` viser begge. Alt annet — krypteringen, formatet `SPBK1`, at den aldri
kaster, at den er inert uten variablene — står uendret.

**Én ting til, som ellers blir en løgn i grensesnittet:** livssyklusregelen sletter objektet
i bucketen, men `OffsiteKopi`-raden i vår base blir stående og påstår at fila finnes.
Oversikten skal derfor lese bucketen (`list_objekter()`, cachet 5 minutter) når den viser
hva som *finnes* offsite, og bruke radene bare til å vise hva som er *sendt*.

## 7. Instruks: oppbevaringstidene i Scaleway

**Utgangspunktet, bekreftet av André 13. sep.:** det står én regel i dag — *730 dager,
scope: alle objekter i bucketen* — pluss regelen for uferdige flerdelsopplastinger.

Det betyr at regelen i dag også vil treffe `full/`-filene når de kommer. Derfor er
rekkefølgen under bindende: **snevre den eksisterende regelen inn først, legg den nye til
etterpå.** To regler som treffer samme objekt er et sted å gjette, og ingen skal gjette om
en sletting.

### 7.1 I konsollen

1. Logg inn på Scaleway → **Object Storage** → bucketen (Amsterdam, `nl-ams`).
2. Fanen **Lifecycle rules**.
3. **Åpne den eksisterende 730-dagersregelen og sett scope til prefiks `backups/`**
   i stedet for «alle objekter». Lagre. Ingenting endres for filene som ligger der —
   de ligger alle under `backups/` fra før.
4. **Ny regel** → prefiks `full/` → *Expire current versions of objects* → **90 dager**.
   Lagre.
5. La regelen for uferdige flerdelsopplastinger (7 dager) stå. Den rydder avbrutte
   opplastinger, ikke innhold.

**Gjør dette før den første hele backupen lastes opp** (altså før fase 4 er i prod).
Rekker du det ikke, er det ikke tapt: livssyklus regner alder fra objektets egen
tidsstempel, ikke fra da regelen ble laget, så en fil som er ti dager gammel når regelen
kommer, slettes 80 dager senere. Men da har filene ligget en periode under feil frist, og
90-dagersfristen er en personvernbeslutning (`BACKUP.md` §2), ikke en preferanse.

### 7.2 Med kommandolinje

Konsollen er lettest. Denne er etterprøvbar, og erstatter **hele** konfigurasjonen, så alle
tre reglene må være med i samme kall:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --endpoint-url https://s3.nl-ams.scw.cloud \
  --bucket <bucketnavn> \
  --lifecycle-configuration '{
    "Rules": [
      {"ID": "moduler-730", "Status": "Enabled",
       "Filter": {"Prefix": "backups/"}, "Expiration": {"Days": 730}},
      {"ID": "hel-base-90", "Status": "Enabled",
       "Filter": {"Prefix": "full/"},    "Expiration": {"Days": 90}},
      {"ID": "avbrutte-opplastinger", "Status": "Enabled",
       "Filter": {"Prefix": ""},
       "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}}
    ]}'
```

**Merk hvilken nøkkel som kan gjøre dette.** Portalens IAM-applikasjon har
`ObjectStorageObjectsWrite`, `ObjectStorageObjectsRead` og `ObjectStorageBucketsRead` —
den kan *lese* bucket-oppsettet, men ikke skrive det. Kallet over krever en nøkkel med
bucket-skriverett, eller at du gjør det i konsollen som deg selv. Det er riktig slik: en
portal som kunne endre sin egen oppbevaringsregel, kunne også forkorte den.

### 7.3 Kontroller at den virker

En dokumentert kontroll som ikke er reell, er det alvorligste avviket vi kan ha — det er
begrunnelsen bak S7 i CHANGELOG, og den gjelder her.

```bash
aws s3api get-bucket-lifecycle-configuration \
  --endpoint-url https://s3.nl-ams.scw.cloud --bucket <bucketnavn>
```

Svaret skal vise nøyaktig de tre reglene. **Og kortet på `/portal-admin/backup/` gjør det
samme kallet** og viser «`backups/` 730 dager · `full/` 90 dager». Da slipper vi å tro på
et dokument — bucketen svarer selv. Lesingen skal være dekket av
`ObjectStorageBucketsRead`; svarer Scaleway 403 likevel, viser kortet «ukjent» framfor å
feile, og det er et punkt til runbooken.

En regel virker fra neste opprydding, ikke med det samme. Det første objektet som faktisk
forsvinner under den nye regelen, gjør det 90 dager fram i tid — så kontrollen over er det
eneste beviset vi får før den tid.

## 8. Gjenoppretting: både fra Railway CLI og fra grensesnittet

**Svar på spørsmålet ditt:** du husker halvparten riktig. Det som finnes i dag er
`hent_offsite`, som henter fila ned fra Scaleway, dekrypterer den og legger den i
`BACKUP_DIR` med en `Backup`-rad — men den **rører ikke databasen**, og siste linje i
utskriften er «gjenopprett fra /portal-admin/backup/». Selve gjenopprettingen finnes bare
i nettleseren. (`import_offline_data` er noe annet: pasientimport fra den gamle appens
SQLite-fil.)

Så veien må bygges. Én tjenestefunksjon, to innganger:

```bash
python manage.py gjenopprett --list                 # filene i BACKUP_DIR, nyeste først
python manage.py gjenopprett <filnavn>              # modulfil — spør om bekreftelse
python manage.py gjenopprett <filnavn> --ja         # uten spørsmål (for railway ssh)
python manage.py gjenopprett --full <filnavn> --ja  # hele databasen
python manage.py gjenopprett --hent <objekt> --ja   # hent fra Scaleway og gjenopprett i ett
```

Fire ting er verdt å merke seg:

- **`--ja` er ikke bekvemmelighet, det er nødvendig.** `railway ssh --service web -- …`
  kjører uten interaktiv terminal, så en `input()`-bekreftelse ville hengt til timeout.
  Uten flagget spør kommandoen; med flagget går den rett på.
- **`--hent` er den korte veien i en katastrofe.** I en tom base er rekkefølgen ellers
  fire kommandoer; med `--hent` er den én per fil.
- **Samme funksjon som knappen kaller.** Ingen andre regler, ingen annen rekkefølge, samme
  pre-restore-øyeblikksbilde, samme audit-rad. To innganger til én dør.
- **Grensesnittet kan gjenopprette begge deler**, hel base inkludert, med advarselen fra
  §5.2 i dialogen.

### 8.1 Nedlasting er ikke det samme som gjenoppretting

Svaret ditt handlet om gjenoppretting, og der er vi enige: begge veier, både CLI og UI.
Spørsmålet mitt gjaldt **nedlasting** — knappen som legger fila i nedlastingsmappa på
maskinen du sitter ved. De to er ulike ting, og skillet er hvor fila havner:

| | Hvor dataene ender | Vurdering |
|---|---|---|
| Gjenoppretting (UI eller CLI) | Blir på serveren | Ja, begge veier |
| Nedlasting av **modulfil** | På din maskin | Beholdes som i dag |
| Nedlasting av **hel fil** | På din maskin | **Anbefaler nei** |

Den hele fila bærer passordhasher og TOTP-hemmeligheter for alle kontoer. Én knapp flytter
hele portalens legitimasjon til en laptop, og derfra til sikkerhetskopien av laptopen.
Trenger du fila lokalt, finnes den i Scaleway-konsollen, og da er det en bevisst handling.

Og for katastrofeveien trengs den ikke: ny Postgres → `migrate` → `gjenopprett --hent
--full` inne i containeren. Fila er aldri innom en klientmaskin.

**Dette er det ene punktet jeg ber deg bekrefte før fase 4.**

## 9. Kontroll og verifisering

«Mer kontroll» er ikke bare flere brytere. Det er å kunne se at det virker:

- **«Sist sjekket» ved siden av «siste fil»** (§2.1) — skiller stille fra stoppet.
- **«Verste tilfelle nå»** (§2.5) — målt mot siste vellykkede offsite-kopi.
- **`/portal-admin/server-status/`** viser `backup_kjor` blant cron-jobbene, med tid og
  ok/feil, som de to andre.
- **`python manage.py verifiser_backup`** — ny kommando, og den viktigste i planen. Den
  lager en engangsdatabase slik `verifiser_migrasjoner` alt gjør, kjører `migrate`, laster
  den nyeste fila for hver modul i riktig rekkefølge (portal → patients → arkiv → oppdrag →
  oppdrag_arkiv → vaktliste) og skriver ut radtall per modell. `--full` gjør det samme med
  den hele fila alene.

  > En backup ingen har gjenopprettet er en hypotese. Denne kommandoen er forskjellen på å
  > tro at vi har backup og å vite det, og den kan kjøres når som helst uten å røre noe.

- **Testen fra `BACKUP.md` §3.6** er samme øvelse i suiten, mot en seedet base. Den må
  kjøres mot PostgreSQL minst én gang før merge: SQLite har ingen utsatte fremmednøkler, og
  det er dem testen finnes for.

## 10. Faser

Hver fase er et eget commit-sett med grønne tester. Fase 1–2 kan deployes uten fase 3.

| # | Innhold | Anslag |
|---|---|---|
| 1 | `Backupplan` med tre moduser, intervall i minutt/time/døgn og cap; datamigrasjon fra `ModuleBackupConfig`; `backup_kjor` med `lesbar_dbfeil`; `CRON_JOBBER` bytter `db_backup` → `backup_kjor`; middlewaren skrevet om til samme funksjon; `CLAUDE.md` rettet fra tre til tre *andre* cron-jobber | 1 kveld |
| 2 | Én side: standardplan, «verste tilfelle»-linja, diskbruk, inline fillister, «Ta backup av alle nå», «Gjenopprett siste», bekreftelse i dialog. Modulsidene legges ned | 1–2 kvelder |
| 3 | `vaktliste`- og `portal`-handler; `get_restore_models()` utledet topologisk + testen som krever dekning; 3.4 faller ut av seg selv; `arkiv` døpes om til «Pasientregistreringsarkiv» | 1 kveld |
| 4 | Hel backup: handler, `flush` + `loaddata`, prefikset `full/`, dialogen som sier at du blir logget ut | 1 kveld |
| 5 | `gjenopprett`-kommandoen med `--list`, `--ja`, `--full` og `--hent` (§8) | ½ kveld |
| 6 | `verifiser_backup` + testen fra `BACKUP.md` §3.6, kjørt mot PostgreSQL | 1 kveld |
| 7 | Livssyklusreglene i Scaleway (§7, **krever André**) og kortet som leser dem | ½ kveld |
| 8 | Rydding: `db_backup`, `patients/backup_service.py`, `patients.BackupConfig`, `RETENTION_HOURS`. Krever migrasjon | ½ kveld |

**Rekkefølgekrav:** fase 7 (livssyklusreglene) skal være gjort **før** fase 4 er i prod, så
den første hele backupen ikke lander under 730-dagersregelen. Se §7.1.

**Migrasjonsfellen i fase 1:** datamigrasjonen skriver rader og endrer deretter skjema i
samme transaksjon. Det er akkurat mønsteret som tok ned release-fasen 30. august
(`cannot ALTER TABLE … because it has pending trigger events`). Enten
`SET CONSTRAINTS ALL IMMEDIATE` mellom skrivingen og skjemaendringen, eller del i to
migrasjoner — og en prøve i `core/migrasjonsprover.py`, ellers går den statiske regelen
grønn uten at noe er testet.

**Forholdet til flyttingen ut av `patients`:** `Backupplan` ligger i `core` fra første
stund, så den er upåvirket. `Backup`-modellen flytter i `TEKNISK_GJELD.md` §2, og
navnetabellen som skrives der dekker også `full`-fila. Fase 1–6 kan derfor kjøres før
flyttingen, som `PLAN_REKKEFOLGE_2026-09.md` legger opp til — `portal`-handleren tar
`AppSetting` med når den kommer.

## 11. Avklart og gjenstående

**Avklart av André 13. sep. 2026:**

1. Intervall settes fritt i minutter, timer og døgn, med «ved endring» og «av» som moduser.
   Cap på antall backuper for både moduler og hel database. → §2.2, §2.3
2. Hel database hver 24. time som standard, men fritt valgbart som modulene. → §5.3
3. Gjenoppretting skal finnes både fra Railway CLI og i grensesnittet. → §8
4. `db_backup` er **ikke** satt opp i Railway; bare `purge_old_logs` og `kollaps_arkiv`
   kjører. → §1.2
5. Livssyklusregelen står i dag på 730 dager med scope «alle objekter i bucketen». → §7

**Gjenstår før fase 4:**

- **Nedlasting av den hele backupfila fra nettleseren — ja eller nei?** Anbefaling: nei,
  begrunnelsen står i §8.1. Gjenoppretting er upåvirket uansett svar.

**Gjenstår før fase 7 (Scaleway):**

- Bucketnavnet, for instruksen og for runbooken.
