# Dataimport: pasientdata fra gammel produksjon inn i portalen

Sanitetsportalen står i staging på Railway. I produksjon kjører fortsatt den gamle
Pasientregistreringsappen — forgjengeren, før den ble gjort om til portal. Årets
pasientdata ligger der, og skal med inn i portalen.

Skrevet 14. aug. 2026, etter gjennomgang av `C:\Programmering\pasientregistrering`.

---

## Kortversjonen

**Verktøyet finnes allerede.** `python manage.py import_offline_data` i portalen leser
nøyaktig den gamle appens skjema — den ble skrevet for offline-SQLite-filer fra feltbruk,
og de filene *er* den gamle appen. Ingen ny kode trengs.

Kolonnene i gammel `patients_patient` stemmer kolonne for kolonne med det kommandoen
forventer, inkludert `behandler_id`, `helsepersonell_ref_id` og `journal`.

Arbeidet ligger i å få prod-dataene ut av Postgres og inn i en SQLite-fil kommandoen kan
lese. Det gjøres med standardoperasjoner — ingen håndredigering av data.

---

## Hva som importeres

| Med | Ikke med |
|---|---|
| `Patient` — alle kliniske felt for valgt år | Brukere, passord, MFA-hemmeligheter |
| `Behandler` → `Forstehjelper`, matchet på navn | Audit-logg |
| `Helsepersonell`, matchet på navn | Backup-metadata |
| | `VaktArkiv` / `ArkivertPasient` (se seksjon 5) |

**Statistikken importeres ikke — den beregnes.** All statistikk i portalen er utledet fra
`Patient`-radene ved forespørsel. Kommer pasientene inn, kommer statistikken av seg selv.
Det finnes ingen lagret statistikk å flytte, med unntak av frosne aggregater i kollapsede
arkiv (seksjon 5).

---

## Framgangsmåte

Tre steg. Hvert steg er en standardoperasjon; ingen av dem endrer prod.

### Steg 1 — Hent dataene ut av gammel prod (read-only)

Fra `C:\Programmering\pasientregistrering`, med prod-databasen som mål:

```powershell
# MERK: bruk DATABASE_PUBLIC_URL, ikke DATABASE_URL. Sistnevnte peker på
# postgres.railway.internal, som kun er nåbar innenfra Railways nettverk.
$env:PYTHONUTF8 = "1"
$env:DATABASE_URL = "<DATABASE_PUBLIC_URL fra Railway, Postgres-tjenesten>"
python manage.py dumpdata patients.Patient patients.Behandler patients.Helsepersonell `
    --natural-foreign --indent 2 -o arsdata-2026.json
```

`dumpdata` leser bare. Prod røres ikke.

**`PYTHONUTF8=1` er ikke valgfritt.** Uten den skriver `dumpdata -o` fila i Windows'
lokale kodesett (cp1252), ikke UTF-8. Neste steg feiler da med
`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xf8` — `0xf8` er `ø`. Sett den på
begge stegene, og kontroller etterpå at fila lar seg dekode som UTF-8.

**Sjekk størrelsen på fila etterpå.** Er den mistenkelig liten, har du sannsynligvis
truffet en tom lokal database i stedet for prod — `DATABASE_URL` er lett å sette i feil
skall.

### Steg 2 — Bygg en SQLite-fil med gammelt skjema

Fortsatt fra den gamle appen, nå mot en fersk lokal fil:

```powershell
Remove-Item -ErrorAction SilentlyContinue import-kilde.sqlite3
$env:DATABASE_URL = "sqlite:///import-kilde.sqlite3"
python manage.py migrate
python manage.py loaddata arsdata-2026.json
```

Nå har du en SQLite-fil med gammelt skjema og prod-innhold. Det er nøyaktig formatet
portalens importkommando forventer.

### Steg 3 — Importer inn i portalen

Fra `C:\Programmering\sanitetsportalen`.

> **Det finnes ikke lenger et miljø å øve mot.** Dette dokumentet ble skrevet da portalen
> sto i staging og produksjon var den gamle appen. Etter 22. aug. 2026 betjener
> staging-miljøet `portal.sanitet.net` — det *er* produksjon. `--dry-run` er dermed hele
> sikkerhetsnettet. Kjør den, les rapporten, og ta en manuell backup i portalen før du
> kjører uten.

```powershell
python manage.py import_offline_data ..\pasientregistrering\import-kilde.sqlite3 `
    --year 2026 --dry-run
```

`--dry-run` kjører hele importen i en transaksjon og ruller tilbake. Les rapporten før du
kjører uten.

Så uten `--dry-run` når rapporten ser riktig ut.

---

## Hva kommandoen gjør for deg

- **Renummererer pasientnummer** til `max(eksisterende) + 1, 2, 3…`, så kollisjon med
  pasienter som allerede finnes i portalen er umulig.
- **Matcher førstehjelper og helsepersonell på navn**, og oppretter dem hvis de mangler.
  `Behandler` i gammel base blir `Forstehjelper` i portalen — omdøpingen skjedde i
  migrasjon `0011`, og kommandoen leser fortsatt `patients_behandler`.
- **Validerer kliniske felt** mot whitelisten i `patients/choices.py` (N6). Finnes verdier
  som ikke er gyldige, avbrytes hele importen med rapport per rad. `--force` importerer dem
  likevel.
- **Loggfører** hver importert pasient i `AuditLog` med `action='IMPORT'`.
- **Kjører alt i én transaksjon.** Feiler noe, er ingenting skrevet.

---

## Tre forbehold på datakvalitet

### `created_at` blir importdatoen, ikke den opprinnelige

Feltet er `auto_now_add`, så importerte pasienter får dagens dato. **Statistikken påvirkes
ikke** — den regner på `inntid`, `pabegynt`, `utskrevet` og de andre tekstfeltene, som
importeres uendret. Men sorterer du på «opprettet», er rekkefølgen importrekkefølgen.

### Det gamle `helsepersonell`-tekstfeltet importeres ikke

Gammel `Patient` har både `helsepersonell` (fritekst, utgående) og `helsepersonell_ref`
(fremmednøkkel). Portalen fjernet tekstfeltet i migrasjon `0010`, og
`PATIENT_COPY_FIELDS` inkluderer det derfor ikke.

For årets data er det sannsynligvis uproblematisk, siden fremmednøkkelen var i bruk. Sjekk
det før import:

```sql
SELECT count(*) FROM patients_patient
 WHERE year = 2026 AND helsepersonell != '' AND helsepersonell_ref_id IS NULL;
```

Er svaret 0, går ingenting tapt. Er det ikke 0, må de radene håndteres for seg — enten ved
å opprette `Helsepersonell`-rader fra tekstverdiene først, eller ved å godta tapet bevisst.

### Whitelisten kan avvise gamle verdier

Verdimengdene i `choices.py` ble innført etter at den gamle appen var i drift. Er et
valgalternativ endret siden, avbryter importen med rapport. Da har du to valg: rett kilden,
eller kjør med `--force` og godta verdiene som de er. Rapporten viser hvilke verdier det
gjelder og hvor mange rader.

---

## Arkiverte vakter

Gammel prod kan ha `VaktArkiv`-rader hvis noen har arkivert en vakt der. De importeres
**ikke** av `import_offline_data`.

Det er sannsynligvis riktig å la dem være:

- Arkivmodellene har divergert. Portalen la til `importert_av_navn` (frosset brukernavn),
  endret `importert_av` fra `PROTECT` til `SET_NULL` (GDPR fase 4.1), og la til
  kollaps-feltene `kollapset_at`, `aggregat` og `aggregat_sha256` (fase 3.1). Gammel base
  har ingen av dem.
- **SHA-256-signaturen kan ikke overføres.** Den er beregnet over `arkiv_id`, altså
  primærnøkkelen. Får arkivet ny pk i portalen, stemmer ikke signaturen, og arkivet melder
  tukling. Å skrive om signaturen for å passe ville undergravd hele poenget med den.

**Anbefaling:** importer pasientradene, og arkivér vakten på nytt fra portalen når dataene
er inne. Da får arkivet en signatur som faktisk kan verifiseres, og alle feltene portalen
forventer.

Trengs den gamle arkivhistorikken likevel, er den bevart i den gamle appens egne backuper —
og det er en egen jobb med egne avveininger.

---

## Etter import

1. **Sjekk antallet** mot det gamle systemet: `Patient.objects.filter(year=2026).count()`.
2. **Åpne statistikkfanen** og sammenlign nøkkeltall med den gamle appen. Statistikken er
   beregnet, så avvik betyr at data mangler eller er endret.
3. **Se over `AuditLog`** — det skal ligge én `IMPORT`-rad per pasient.
4. **Ta en manuell backup** i portalen før noe annet skrives, slik at importen har et eget
   gjenopprettingspunkt.

Kjør hele løpet mot staging først. Importen er transaksjonell og trygg, men å oppdage et
forbehold fra seksjonen over på staging koster ingenting.
