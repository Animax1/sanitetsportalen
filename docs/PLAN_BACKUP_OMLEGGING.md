# Plan: backup-løsningen lagt om

Status: **plan, 13. september 2026.** Bestilling fra André samme dag: modulenes backup og
gjenoppretting er tungvint, han vil ha mer kontroll over *når* det lagres, det samme skal
gjelde en hel databasebackup, leveransen til Scaleway skal være lik for begge, og det må
finnes en instruks for at hele basen slettes etter 90 dager mens modulene beholdes i 730.

Underlaget er `docs/BACKUP.md` (hva som skal finnes) og `docs/TEKNISK_GJELD.md` §4 (hullene).
Dette notatet er **hvordan**. Rekkefølgen står i `docs/PLAN_REKKEFOLGE_2026-09.md`; denne
planen er trinn 1 og 3 der, skrevet ut.

---

## 1. Hva som faktisk er tungvint i dag

Målt på koden, ikke på følelsen:

| Handling | Hva det koster nå |
|---|---|
| Ta backup av alt | Fire runder: oversikt → modulside → «Kjør backup» → tilbake, én gang per modul. Ingen knapp tar alle |
| Gjenopprette en modul | Fem steg: oversikt → modulside → finn fila i en liste på 200 → gjenopprettingsside → skriv modul-slugen → send |
| Endre intervall | Én side per modul, og intervallet er et **nedtrekk med sju faste valg** (av, 5, 15, 30, 60, 360, 1440 min). Vil du ha hvert 10. minutt, finnes det ikke |
| Se om det virker | «Sist kjørt» sier når scheduleren sist *skrev en fil*. Sto innholdet stille, står tidspunktet stille — og det ser likt ut som en jobb som har stoppet |

Og tre ting jeg fant under lesingen som er verre enn tungvint:

**1.1 Klokka er trafikk.** `BackupSchedulerMiddleware` kjører sjekken etter hver
forespørsel, throttlet til én gang per 60 sekunder per prosess. **Kommer det ingen
forespørsel, tas ingen backup.** Mellom vaktene står portalen stille, og da står backupen
også stille. I dag skjuler hash-skippet dette — når ingenting endrer seg, ville det
uansett ikke blitt skrevet noen fil — men i det øyeblikket du ber om «konsekvent lagring
hvert tidsintervall», er trafikkdrevet klokke feil mekanisme. Den kan ikke levere det du
ber om.

**1.2 `db_backup`-cronjobben er en felle.** Kommandoen finnes, står i `CRON_JOBBER` i
`core/kommando.py`, og `CLAUDE.md` sier at den er én av tre Railway-cronjobber. Men
Railway-tabellen i `TODO.md` har bare to rader, `purge_old_logs` og `kollaps_arkiv`. Én av
de to påstandene er feil, og begge utfallene er dårlige:

- Er jobben **ikke** satt opp, står `/portal-admin/server-status/` og sier «Aldri» om en
  jobb som aldri kommer til å kjøre.
- Er den **satt opp**, kjører den gjennom `patients/backup_service.py` og leser
  `patients.BackupConfig` — singletonen ingen flate redigerer lenger. Da tar en jobb som
  heter «db_backup» backup av **én modul**, på et intervall ingen kan se, og navnet lover
  hele databasen.

Dette må sjekkes i Railway-konsollen, og kommandoen erstattes uansett utfall (§4).

**1.3 `restore_models` vedlikeholdes for hånd.** Hver handler lister opp modellene som
skal slettes før `loaddata`, i barn-først-rekkefølge. Glemmer du én, blir radene stående
igjen etter en gjenoppretting — og det er nettopp det som er gjeldspunkt 3.4 (`Lydvarsel`
er i oppdragsdumpen, men ikke i lista). Feilen er ikke at noen var uoppmerksom. Feilen er
at lista kan være ufullstendig uten at noe sier fra.

## 2. Beslutningen: én plan, tre moduser, fritt intervall

Én modell styrer alt som kan tas backup av — de fem modulfilene, portalfila og den hele
databasen. `core.ModuleBackupConfig` erstattes av:

```python
class Backupplan(models.Model):          # core
    slug             # modul-slug, 'full', eller 'standard' (malen de andre arver)
    folger_standard  # bool — modulen bruker standardplanen
    modus            # 'av' | 'ved_endring' | 'alltid'
    intervall_min    # fritt heltall, ikke et nedtrekk
    behold           # antall filer på volumet
    sist_sjekket_at  # når planen sist ble vurdert
    sist_fil_at      # når det sist ble skrevet en fil
    sist_resultat    # 'ny' | 'uendret' | 'feil: …'
```

### 2.1 De tre modusene, og hvorfor begge de to aktive trengs

| Modus | Hva som skjer hvert intervall | Når den er riktig |
|---|---|---|
| **Av** | Ingenting automatisk. Manuell knapp virker fortsatt | Moduler som ikke er i bruk |
| **Ved endring** | Serialiser, sammenlign SHA-256 mot forrige fil. Lik → ingen fil, ingen opplasting | Standard. Under vakt endrer dataene seg hele tiden, så den skriver like ofte som «alltid». Mellom vaktene skriver den ingenting, og det er riktig |
| **Alltid** | Skriv en fil hver gang, uansett om innholdet er likt | Når du vil ha en **puls**. En fil som *mangler* er et synlig alarmsignal |

Skillet er verdt å forstå, for det er hele svaret på «mer kontroll»:

> **«Ved endring» er effektiv, men stum.** Står det ingen ny fil, kan det bety at
> ingenting har endret seg — eller at jobben er død. De to ser like ut utenfra.
> **«Alltid» er en puls.** Hver fil er et bevis på at jobben kjørte, og et hull i rekka
> er en feil du ser med øynene.

Derfor gjør vi **begge deler synlige uansett modus**: `sist_sjekket_at` oppdateres ved
hver vurdering, ikke bare når det skrives en fil. Grensesnittet kan da si

> *Sjekket 14:05 · siste fil 11:30 (uendret siden da)*

og det er ikke lenger mulig å forveksle «stille» med «stoppet». Det er en billigere måte
å få pulsen på enn å skrive 96 like filer i døgnet.

**Anbefaling:** modulene på «ved endring», den hele databasen på «alltid» med langt
intervall. Begrunnelsen står i §5.3.

### 2.2 Fritt intervall, med konsekvensen synlig

`intervall_min` blir et fritt tall. To ting følger av det, og begge skal stå i
grensesnittet framfor å bli sperret:

- **Oppløsningen er tikken.** Klokka (§3) spør «er noe forfalt?» med et fast mellomrom.
  Setter du 3 minutter og tikken er 5, får du 5. Feltet sier hva tikken er.
- **Antall filer er en konsekvens du skal se før du lagrer.** Under feltet står en linje
  som regnes ut mens du skriver: *«Hvert 15. minutt = 96 filer i døgnet, ca. 35 000 i
  året offsite.»* Med 730 dagers oppbevaring på modulfilene er det tallet som betyr noe,
  ikke minuttene.

Ingen øvre eller nedre sperre utover 1 minutt. Det følger portalens egen linje fra
vaktlistas belastningstall: **varsle, ikke avvis.** Du vet når du trenger å bryte en
tommelfingerregel; koden gjør ikke det.

## 3. Klokka: en tikk som ikke avhenger av trafikk

Ny kommando `python manage.py backup_kjor`, satt opp som Railway Cron-tjeneste ved siden
av de to som alt står der:

```
backup_kjor   python manage.py backup_kjor   */5 * * * *
```

Kommandoen gjør ingenting annet enn å spørre databasen hva som er forfalt og kjøre det.
**Intervallene ligger i basen, ikke i cron-uttrykket.** Det er hele poenget: du endrer
«hver time» til «hvert 20. minutt» i portalen, uten å røre Railway og uten en deploy.

Tre ting den arver fra resten av portalen:

- `lesbar_dbfeil('ingen backup ble tatt', navn='backup_kjor')` — én lesbar linje i
  cron-loggen i stedet for fire tracebacks, og `AppSetting['cron.backup_kjor']` skrevet
  både når det gikk og når det ikke gikk, så server-status viser den.
- `select_for_update(nowait=True)` på planraden som i dag, så to tikker som overlapper
  ikke lager to filer.
- `CRON_JOBBER` utvides med navnet, ellers finnes jobben ikke for dashbordet.

**Middlewaren blir stående som reservenett**, men skrives om til å kalle samme funksjon.
Faller cron-tjenesten ut, tar trafikken over; står portalen stille, tar cron det.
Det koster ingenting å ha begge, fordi begge går gjennom den samme låsen.

> **Sjekk før oppsett:** hva Railway faktisk tillater som minste cron-intervall. Det tallet
> blir gulvet for oppløsningen i §2.2, og skal stå i feltteksten. Ikke anta `*/5`.

## 4. Modulløsningen forenklet

### 4.1 Én side, ikke N

`/portal-admin/backup/` blir én side. Modulsidene og gjenopprettingssiden legges ned.

```
┌─ Hel database ──────────────────────────────────────────────┐
│ Alltid · hver 24. time · behold 7      [Endre] [Ta nå]       │
│ Siste: 13.09 03:00 (4,2 MB) · offsite OK · neste ca. 03:00   │
└──────────────────────────────────────────────────────────────┘
┌─ Offsite (Scaleway) ────────────────────────────────────────┐
│ Aktiv · bucket sanitet-backup                                │
│ Oppbevaring i bucketen:  backups/ 730 dager · full/ 90 dager │← lest fra bucketen
│ 1 284 filer · sist 13.09 03:01                               │
└──────────────────────────────────────────────────────────────┘
┌─ Moduler ──────────────────────── [Ta backup av alle nå] ───┐
│ Standardplan: Ved endring · hver time · behold 50  [Endre]   │
│                                                              │
│ Pasienter          følger standard   11:30 ny      42 filer ▾│
│ Pasientregistre…   egen: hver 6. t   09:00 uendret  8 filer ▾│
│ Oppdrag            følger standard   11:30 ny      41 filer ▾│
│ Vaktliste          følger standard   11:30 uendret 12 filer ▾│
└──────────────────────────────────────────────────────────────┘
```

Fire grep gjør jobben:

1. **Standardplanen.** Du setter modus og intervall **ett sted**, og alle modulene følger
   den. Vil én modul noe annet, hukes «egen plan» av på den raden. Med seks modulfiler er
   forskjellen mellom å vedlikeholde ett tall og seks.
2. **«Ta backup av alle nå»** — én knapp, alle modulene og den hele fila.
3. **Fillista er inline** (`▾` folder ut raden), ikke en egen side. De 20 nyeste, med
   «vis alle» under.
4. **«Gjenopprett siste»** per modul, fordi det er det man vil i ni av ti tilfeller.
   Gjenoppretting av en eldre fil ligger i den utfoldede lista.

Bekreftelsen blir stående — den er ikke det som er tungvint. Men den flytter inn i en
dialog på samme side, og teksten sier hva som skjer: *«N rader i M tabeller slettes og
erstattes. Et pre-restore-øyeblikksbilde tas først.»* Antallet hentes fra basen mens
dialogen åpnes. Å skrive modul-slugen beholdes som andre sperre, slik
`{"confirm": true}`-mønsteret ellers i portalen.

### 4.2 `restore_models` utledes

`BaseBackupHandler` får en `get_restore_models()` som **regner ut lista selv** når
handleren ikke har oppgitt den: alle modellene i `apps` minus `exclude`, topologisk
sortert på fremmednøkler slik at barn kommer først. `restore_models` beholdes som
overstyring for de tilfellene der rekkefølgen ikke kan utledes (selvreferanser som
`Statusmelding.erstatter`).

To gevinster, og den andre er den store:

- Modul nummer seks og sju slipper å skrive lista.
- **En modell kan ikke lenger være i dumpen uten å være i slettelista.** Gjeldspunkt 3.4
  (`Lydvarsel`) forsvinner, og kan ikke oppstå igjen.

I tillegg en test som går gjennom hver registrerte handler, serialiserer, og krever at
hver modelletikett i dumpen finnes i `get_restore_models()`. Den er billig og fanger
feilen for alle framtidige moduler.

### 4.3 De to manglende handlerne

Fra `BACKUP.md` §3, uendret, og de hører til her:

- **`vaktliste`** — alle modellene, `Mannskap.user` og `Utsending.sendt_av` strippet.
  Dette er den største udekkede datamengden i dag: korps, mannskap med telefon, e-post og
  ISSI, kompetanser, ressurser, vaktposter og belastningsgrensene.
- **`portal`** — `core.Vakt`, `core.ModuleSettings` og (etter flyttingen i
  `TEKNISK_GJELD.md` §2) `AppSetting`. Uten `Vakt` kan ingen av de andre filene
  gjenopprettes i en tom base: pasienter og oppdrag peker på den med fremmednøkkel.

## 5. Den hele databasebackupen

### 5.1 Hva som er med

Én handler, `slug='full'`, med samme plan-modell og samme moduser som modulene.

| Med | Utelatt, og hvorfor |
|---|---|
| Alle appene: brukere med passordhasher, MFA-enheter og reservekoder, `ModulTilgang`, audit- og innloggingslogg, varsler, `Vakt`, alle modulenes data og alle arkivene | `sessions` — innlogginger som uansett er utløpt |
| | `contenttypes` og `auth.Permission` — gjenopprettes av `migrate`, og lastes de på nytt kolliderer primærnøklene |
| | `Backup`, `OffsiteKopi`, `Backupplan` — metadata om backupfiler. Å laste dem tilbake ville gjenopplive rader for filer som ikke finnes |
| | `admin.LogEntry` — Django-admin er av i prod (S1) |

Serialiseres med `natural_foreign` og `natural_primary` som i dag.

### 5.2 Gjenoppretting er `flush` + `loaddata`, ikke en slettelista

For modulene er slett-i-rekkefølge riktig, fordi resten av basen skal stå urørt. For hele
databasen er det feil verktøy: det er hundre modeller på tvers av sju apper, og
rekkefølgen mellom dem er nettopp det ingen skal måtte vedlikeholde. `flush` tømmer alt og
lar `migrate`s post-hooks gjenskape contenttypes og permissions først.

**Og du blir logget ut.** Sesjonene ligger i databasen, og `flush` tar dem. Brukerraden du
er logget inn som slettes og lastes inn igjen fra fila — kanskje med et annet passord enn
det du logget inn med. Det skal stå i dialogen med rene ord, ikke oppdages etterpå:

> *Du blir logget ut. Logg inn igjen med passordet som gjaldt da backupen ble tatt.*

Feiler `loaddata`, rulles alt tilbake i samme transaksjon, og du er der du var.

Samme funksjon kalles fra `python manage.py gjenopprett_full <fil>`, som er veien i en tom
base (`BACKUP.md` §4), der det ikke finnes noen å logge inn som ennå.

### 5.3 Hvorfor «alltid» med langt intervall er riktig her

En hel base endrer seg konstant — audit-loggen alene vokser ved hver forespørsel. «Ved
endring» ville derfor aldri hoppe over noe, og du får en fil hvert intervall uansett. Da
er «alltid» det ærlige valget: du ser at det er det du har bedt om.

Intervallet bør være langt, og det er et regnestykke, ikke en smakssak: fila er hele
basen, og oppbevaringen er 90 dager. Hver 24. time gir 90 filer. Hver time gir 2 160.
Anbefaling: **hver 24. time, behold 7 lokalt**, og heller en manuell «Ta nå» før en deploy
eller en risikofylt migrasjon — som ved merge til prod, der André uansett tar backup først.

### 5.4 Tilgang

Bare global admin, som resten av `/portal-admin/`. Og ett tillegg jeg vil anbefale ut over
det `BACKUP.md` sier:

> **Ingen nedlastingsknapp for den hele fila.** Modulfilene kan lastes ned — de bærer
> modulens data. Den hele fila bærer passordhasher og TOTP-hemmeligheter, og en
> nedlastingsknapp flytter hele portalens legitimasjon til en tilfeldig laptop med ett
> klikk. Veien til fila er `hent_offsite` i containeren, der den som henter den allerede
> har bevist at de har tilgangen.

## 6. Leveransen til Scaleway

### 6.1 Rekkefølgen er komprimering, så kryptering — ikke omvendt

Du skrev «kryptering og så komprimering». Det er den ene rekkefølgen som ikke virker, og
det er verdt et avsnitt fordi feilen er usynlig:

**Kryptert data lar seg ikke komprimere.** AES-256-GCM produserer bytes som er statistisk
umulige å skille fra tilfeldig støy, og komprimering lever av å finne gjentakelser. Gzip på
en kryptert fil gir null gevinst — i praksis noen byte *større*, på grunn av gzips eget
hode. Komprimerer du derimot først, jobber gzip på JSON, som er svært repetitivt: en
dumpdata-fil krymper typisk til 5–15 % av rå størrelse. Deretter krypterer du det lille
resultatet.

Dagens kode gjør allerede dette riktig, og det beholdes:

```
dumpdata → JSON → gzip (nivå 6) → fil på volumet
                                → les → AES-256-GCM → last opp som <navn>.enc
```

(Den kjente innvendingen mot å komprimere før kryptering er kompresjonsorakel-angrep av
CRIME/BREACH-typen. De forutsetter at en angriper kan sprøyte valgt tekst inn i samme
strøm og måle chiffertekstens lengde mange ganger. En backupfil skrevet én gang, lastet
opp én gang, er ikke det scenarioet.)

### 6.2 Ett prefiks per oppbevaringstid

Fristene kan bare skilles i bucketen hvis filene ligger på hver sin sti. Derfor:

| Prefiks | Innhold | Frist |
|---|---|---|
| `backups/` | De seks modulfilene, som i dag | 730 dager |
| `full/` | Hele databasen | 90 dager |

`core/offsite.py` får prefikset fra backupens slug i stedet for konstanten `PREFIKS`, og
`hent_offsite --list` viser begge. Alt annet — krypteringen, formatet `SPBK1`, at den
aldri kaster, at den er inert uten variablene — står uendret.

**Én ting til, som ellers blir en løgn i grensesnittet:** livssyklusregelen sletter
objektet i bucketen, men `OffsiteKopi`-raden i vår base blir stående og påstår at fila
finnes. Oversikten skal derfor lese bucketen (`list_objekter()`, cachet 5 minutter) når
den viser hva som *finnes* offsite, og bruke radene bare til å vise hva som er *sendt*.

## 7. Instruks: oppbevaring i Scaleway

Dette er det som må gjøres i Scaleway-konsollen når koden er ute. Regelen som står der i
dag ble satt til 730 dager på hele bucketen, og **den må snevres inn før den nye legges
til** — to regler som begge treffer samme objekt er et sted å gjette, og ingen skal gjette
om en sletting.

### 7.1 I konsollen

1. Logg inn på Scaleway → **Object Storage** → bucketen (Amsterdam, `nl-ams`).
2. Fanen **Lifecycle rules**.
3. **Endre den eksisterende 730-dagersregelen:** sett filteret til prefiks `backups/`.
   Sto den uten prefiks, gjaldt den alt i bucketen. Lagre.
4. **Ny regel** → prefiks `full/` → *Expire current versions of objects* → **90 dager**.
   Lagre.
5. La regelen for ufullstendige flerdelsopplastinger (7 dager) stå — den gjelder opprydding
   av avbrutte opplastinger, ikke innhold.

### 7.2 Med kommandolinje, og som kontroll

Konsollen er lettest, men denne er etterprøvbar. Kjøres med Scaleway-nøklene, ikke
portalens:

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

Merk at kallet **erstatter hele konfigurasjonen** — alle reglene må være med i samme kall,
også den for avbrutte opplastinger.

### 7.3 Kontroller at den virker

En dokumentert kontroll som ikke er reell, er det alvorligste avviket vi kan ha — det er
begrunnelsen bak S7 i CHANGELOG, og den gjelder her.

```bash
aws s3api get-bucket-lifecycle-configuration \
  --endpoint-url https://s3.nl-ams.scw.cloud --bucket <bucketnavn>
```

Svaret skal vise nøyaktig de tre reglene. **Og kortet på `/portal-admin/backup/` leser det
samme kallet** og viser «`backups/` 730 dager · `full/` 90 dager». Står det noe annet der
enn det du tror du satte, er det bucketen som har rett. Da slipper vi å tro på et dokument.

En regel virker fra neste opprydding, ikke med det samme; Scaleway kjører den asynkront,
typisk innen et døgn. Det første objektet som faktisk forsvinner, gjør det 90 dager fram i
tid — så kontrollen over er det eneste beviset vi får før den tid.

## 8. Kontroll og verifisering

«Mer kontroll» er ikke bare flere brytere. Det er å kunne se at det virker:

- **Kolonnen «sist sjekket» ved siden av «siste fil»** (§2.1). Skiller stille fra stoppet.
- **`/portal-admin/server-status/`** viser `backup_kjor` blant cron-jobbene, med tid og
  ok/feil, akkurat som de to andre.
- **`python manage.py verifiser_backup`** — ny kommando, og den viktigste i planen.
  Den lager en engangsdatabase på samme måte som `verifiser_migrasjoner` alt gjør, kjører
  `migrate`, laster den nyeste fila for hver modul i riktig rekkefølge (portal → patients
  → arkiv → oppdrag → oppdrag_arkiv → vaktliste), og skriver ut radtall per modell. Med
  `--full` gjør den det samme med den hele fila alene.

  > En backup ingen har gjenopprettet er en hypotese. Denne kommandoen er forskjellen på å
  > tro at vi har backup og å vite det, og den kan kjøres når som helst uten å røre noe.

- **Testen fra `BACKUP.md` §3.6** er den samme øvelsen i suiten, mot en seedet base.
  Den må kjøres mot PostgreSQL minst én gang før merge: SQLite har ingen utsatte
  fremmednøkler, og det er nettopp `Vakt`-fremmednøklene testen finnes for.

## 9. Faser

Hver fase er et eget commit-sett med grønne tester, og fase 1–2 kan deployes uten fase 3.

| # | Innhold | Anslag |
|---|---|---|
| 1 | `Backupplan` med de tre modusene og fritt intervall; datamigrasjon fra `ModuleBackupConfig`; `backup_kjor` med `lesbar_dbfeil` og `CRON_JOBBER`; middlewaren skrevet om til samme funksjon | 1 kveld |
| 2 | Én side: standardplan, inline fillister, «Ta backup av alle nå», «Gjenopprett siste», bekreftelse i dialog. Modulsidene legges ned | 1 kveld |
| 3 | `vaktliste`- og `portal`-handler; `get_restore_models()` utledet med topologisk sortering + testen som håndhever dekning; `Lydvarsel` (3.4) faller ut av seg selv | 1 kveld |
| 4 | Hel backup: handler, `flush`+`loaddata`, `gjenopprett_full`, prefikset `full/`, ingen nedlasting | 1 kveld |
| 5 | `verifiser_backup` + testen fra `BACKUP.md` §3.6, kjørt mot PostgreSQL | 1 kveld |
| 6 | Livssyklusreglene i Scaleway (§7, **krever André**) og kortet som leser dem | ½ kveld |
| 7 | Rydding: `db_backup`, `patients/backup_service.py`, `patients.BackupConfig`, `RETENTION_HOURS`. Krever migrasjon | ½ kveld |

**Migrasjonsfellen i fase 1:** datamigrasjonen skriver rader og endrer deretter skjema i
samme transaksjon. Det er akkurat mønsteret som tok ned release-fasen 30. august
(`cannot ALTER TABLE … because it has pending trigger events`). Enten `SET CONSTRAINTS ALL
IMMEDIATE` mellom skrivingen og skjemaendringen, eller del i to migrasjoner — og en prøve i
`core/migrasjonsprover.py`, ellers går den statiske regelen grønn uten at noe er testet.

**Forholdet til flyttingen ut av `patients`:** `Backupplan` ligger i `core` fra første
stund, så den er upåvirket. `Backup`-modellen flytter i `TEKNISK_GJELD.md` §2, og
navnetabellen som skrives der dekker også `full`-fila. Fase 1–5 kan derfor kjøres før
flyttingen, som `PLAN_REKKEFOLGE_2026-09.md` legger opp til — `portal`-handleren tar
`AppSetting` med når den kommer.

## 10. Spørsmål til André

Ingen av dem stopper fase 1–3. Svarene trengs før fase 4 og 6.

1. **Standardintervall for modulene?** Forslag: ved endring, hver time, behold 50. Under
   vakt betyr det en fil i timen per modul som har aktivitet.
2. **Hel backup: hver 24. time, behold 7 lokalt?** Hver time gir 2 160 filer offsite på
   90 dager mot 90. Se §5.3.
3. **Er du enig i at den hele fila ikke skal kunne lastes ned fra nettleseren** (§5.4)?
   Den bærer passordhasher og MFA-hemmeligheter.
4. **Er `db_backup` faktisk satt opp som cron-tjeneste i Railway?** `CLAUDE.md` sier tre
   jobber, `TODO.md` lister to. Utfallet avgjør om fase 7 er sletting av kode alene, eller
   også av en tjeneste (§1.2).
5. **Bucketnavnet og hva livssyklusregelen står på i dag** — har den et prefiks, eller
   gjelder den hele bucketen? Trengs for §7.1 steg 3.
