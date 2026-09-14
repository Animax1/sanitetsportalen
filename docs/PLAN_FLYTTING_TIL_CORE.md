# Plan: det portalvide ut av `patients` og inn i `core`

Status: **forslag, 14. september 2026.** Neste post etter backupomleggingen, jf.
`PLAN_REKKEFOLGE_2026-09.md` trinn 2. Underlaget er `TEKNISK_GJELD.md` §2 og §3,
kontrollert mot koden 14. sep. — og den har flyttet seg siden kartleggingen, så
tallene under er dagens. Slettes når flyttingen er gjennomført.

---

## 1. Hva saken er

`patients` var første app, portert fra Flask, og alt som var «portalen» havnet der fordi
det ikke fantes noe annet sted. Resultatet er at **rammeverket avhenger av modulen**:
`core` importerer `patients`, ikke omvendt.

Ingenting går i stykker av det. Det er derfor dette er gjeld og ikke en feil — det koster
litt mer hver gang noen skal finne noe, og det ville kostet mye den dagen pasientmodulen
skulle tas ut eller byttes.

**Det konkrete utslaget vi alt har sett:** backupen speilet hvor modellene bodde.
Portalinnstillingene lå i *pasient*-backupen fordi `AppSetting` ligger i `patients`, og
`core.Vakt` lå ikke i noen fil fordi ingen modul eide den. Det siste er rettet (fase 3 i
backupomleggingen ga vakta en egen portalfil), men det første står igjen.

## 2. Hva som faktisk gjenstår — lista har krympet

`TEKNISK_GJELD.md` §2 ble skrevet 13. sep. Fire av punktene er borte siden:

| Sto i §2 | Status 14. sep. |
|---|---|
| `BackupConfig` | **Slettet** (fase 8, `patients/0017`) |
| `patients/backup_service.py` | **Slettet** (fase 8) |
| `RETENTION_HOURS` (3.3) | **Slettet** (fase 8) |
| `Lydvarsel` mangler i `restore_models` (3.4) | **Falt ut av seg selv** — lista utledes topologisk nå |
| `core.Vakt` i ingen backup (§4) | **Rettet** — `core/backup/portal.py` |

Det som gjenstår å flytte:

| Hva | Fra | Størrelse |
|---|---|---|
| `AppSetting` | `patients/models.py` | 30 linjer, **ingen fremmednøkler**, PK er en tekstnøkkel |
| `Backup` | `patients/models.py` | 45 linjer, én FK til brukeren, ingen til pasientmodeller |
| `hent_aktiv_vakt` | `patients/services.py` | 53 kallsteder utenfor `patients` |
| `SecurityHeadersMiddleware`, `RequestMetricsMiddleware`, `BackupSchedulerMiddleware` | `patients/middleware.py` | 466 linjer |
| `/healthz/` | `patients/health.py` | 137 linjer |
| Server-status + sesjonsverktøyet | `patients/admin_status.py` | 628 linjer, 5 ruter koblet i prosjektet |

**Omfanget målt i filer som må endres: 34 produksjonsfiler og 30 testfiler.** Det er en
stor, men mekanisk endring — nesten alt er importlinjer.

Verdt å merke seg at de to modellene er **uvanlig lette å flytte**: `AppSetting` har
ingen fremmednøkler i det hele tatt, og ingenting i `patients` peker på noen av dem med
FK. Det er derfor dette kan bli en ren tilstandsmigrasjon.

## 3. De to avgjørelsene

### 3.1 Tabellnavnene: behold

| | For | Mot |
|---|---|---|
| **Behold** (`db_table = 'patients_appsetting'`) | Ingen `ALTER TABLE`, ingen datamigrasjon, ingen triggerkø. **Og ingen nedetid** — se under | Tabellene heter `patients_*` i `core` for alltid |
| **Døp om** | Basen speiler koden | Skjemaendring i prod, migrasjonsprøve må skrives, **og et vindu der portalen svarer 500** |

**Anbefaling: behold navnene**, med en kommentar på hver `Meta`.

Argumentet som ikke sto i kartleggingen 13. sep., og som jeg mener avgjør saken:
**Railway kjører release-fasen før den bytter til den nye containeren.** Mellom
`migrate` og byttet står den *gamle* koden og serverer mot det *nye* skjemaet. For en
omdøpt tabell betyr det at gammel kode spør etter `patients_appsetting` mens tabellen
heter `core_appsetting` — og `AppSetting` leses på tilnærmet hver eneste forespørsel,
fordi den bærer pekeren til aktiv vakt. Vinduet er sekunder til et minutt, men i de
sekundene er portalen nede. Det er ikke en pris verdt å betale for at `\dt` skal lese
penere.

Modellene har ikke `db_table` i dag, så navnet **må settes eksplisitt**. Glemmes det,
lager migrasjonen tomme tabeller ved siden av de fulle — og det er en feil som ser ut
som «alle innstillingene forsvant».

### 3.2 Audit-loggens `app_label`: et funn som ikke sto i kartleggingen

`audit/signals.py` utleder `app_label` fra tabellnavnet:

```python
return table_name.split('_', 1)[0]      # 'patients_appsetting' → 'patients'
```

Beholder vi tabellnavnene — som jeg anbefaler — vil **hver framtidig auditrad for
portalinnstillingene og backupene stå som «patients»** i modulfilteret, selv når
modellene bor i `core`. Det er nøyaktig den forvirringen flyttingen skal fjerne, flyttet
fra kodetreet til loggen.

Det finnes alt en åpning for dette: `EKSPLISITT_MAPPING = {'backup': 'patients'}`.

Tre veier, og valget er ditt fordi det handler om hva *du* skal se i filteret:

1. **La det stå.** Historikken er sammenhengende; loggen sier «patients» før og etter.
   Prisen er at etiketten er feil fra den dagen modellene flytter.
2. **Map nye rader til `core`.** Filteret blir riktig framover. Prisen er et brudd:
   en søk på «patients» finner rader fra før flyttingen, en på «core» finner dem etter.
3. **Utled `app_label` fra modellen i stedet for fra tabellnavnet.** Riktigst, men
   rører en fellesmekanisme alle modulene bruker, og gamle rader endres ikke uansett.

**Anbefaling: 2.** Bruddet er ærlig og datert, og det er lettere å forklare («flyttet
14. sep.») enn en etikett som er varig feil. 3 er riktigere i prinsippet, men det er en
egen jobb med egen risiko, og den bør ikke ri på denne.

## 4. Den ene tekniske fella: backupfilene bærer modellnavn

En `dumpdata`-fil ser slik ut:

```json
{"model": "patients.appsetting", "fields": {...}}
```

Flytter modellen, blir etiketten `core.appsetting` — og **en fil tatt før flyttingen lar
seg ikke lenger laste**. `loaddata` svarer «Unknown model». Det gjelder hver
modulfil og hver hel fil som ligger i Scaleway, og de ligger der i **730 dager**. En
backup vi ikke kan gjenopprette er ikke en backup.

Den gode nyheten er at innlastingen har **ett** sted å gripe inn:
`core/backup/service.py:330–353` leser fila til `raw`, skriver den til en midlertidig
fil, og kaller `loaddata`. Navnetabellen legges mellom de to.

```python
GAMLE_MODELLNAVN = {
    'patients.appsetting': 'core.appsetting',
    'patients.backup': 'core.backup',
}
```

To ting som er lette å overse:

- **Handlernes `exclude`-lister nevner modellene ved navn** (`patients.Backup` i
  `patients/backup.py`, og i `core/backup/full.py`). De må følge med, ellers havner
  backuptabellen i sin egen dump.
- **En gammel `patients`-fil inneholder `AppSetting`-rader.** Etter flyttingen står ikke
  `AppSetting` lenger i pasienthandlerens slettelista, så en gjenoppretting av en gammel
  fil vil *skrive* innstillingene uten å ha tømt dem først. For `AppSetting` er det
  ufarlig — PK-en er nøkkelen, så det blir en oppdatering — men det bør stå skrevet, for
  det er ikke åpenbart.

## 5. Fasene

Hver fase er et eget commit-sett med grønne tester, og kan deployes for seg.

| # | Innhold | Anslag |
|---|---|---|
| 1 | **Navnetabellen i lasteren**, med test som laster en fil i gammel form. Tabellen er **tom i dag**, så fasen endrer ingenting — den setter røret på plass og beviser at det virker, før det trengs | ½ kveld — **gjort 14. sep. 2026** |
| 2 | **`AppSetting` og `Backup` til `core`**, `db_table` beholdt, tilstandsmigrasjon. Navnetabellen får sine to rader. Alle 34+30 filene retter importen | 1–2 kvelder |
| 3 | **`hent_aktiv_vakt`, middlewaren, `healthz`, server-status til `core`.** Ingen migrasjon i det hele tatt — ren kodeflytting. Middlewarestiene i `settings.py` og de fem rutene i `myproject/urls.py` følger med | 1 kveld |
| 4 | **Portalfila tar `AppSetting`** (den hører hjemme der, ikke i pasientfila). Ryddingen som faller ut av seg selv: `/portal-admin/` samlet i én URL-fil (3.2), `core/views.py` delt (3.7) | 1 kveld |

**Fase 1 først er poenget.** Navnetabellen er en no-op til fase 2 fyller den, og da er
den alt i prod og prøvd. Gjøres de sammen, er deployen som flytter modellene også den
som må håndtere gamle filer — og feiler tabellen, oppdages det den dagen noen
gjenoppretter.

**Ferdig når** (hver fase): suiten grønn på SQLite og PostgreSQL,
`verifiser_migrasjoner` OK, og for fase 2 i tillegg en oppgraderingssimulering:
base migrert til `main`, seedet med rader, migrert med den nye koden, alle rader intakt.
Og `verifiser_backup` mot en fil tatt **før** fasen — det er den prøven som svarer på om
navnetabellen virker i praksis.

## 6. Hva som ikke er med, og hvorfor

- **3.1 — brukeradmin kjenner pasientregistrene** (`accounts/forms.py` importerer
  `Forstehjelper`). Det er gjeld i en *annen retning* (`accounts` → `patients`), og
  løsningen er en annen: la modulen eie koblingen, som `Mannskap.user` gjør i vaktlista.
  Egen sak, ikke denne.
- **3.6 — `vaktliste.js` på 3 800 linjer.** Deles når neste større endring i fila kommer,
  ikke som eget prosjekt.
- **3.8 — eldre tester som grep-er i JS og maler.** Skrives om når de knekker.
- **Omdøping av tabellene.** Se §3.1. Kan gjøres senere, i et varslet vindu, hvis det
  noen gang blir verdt det.

## 7. Avklart (14. sep. 2026)

1. **Audit-loggens `app_label`: vei 2.** Nye rader for de flyttede tabellene mappes til
   `core` gjennom `EKSPLISITT_MAPPING`. Filteret blir riktig framover, og bruddet er
   datert: et søk på «patients» finner rader fra før flyttingen, «core» finner dem
   etter. Gjøres i fase 2, i samme commit som modellene, så etiketten skifter nøyaktig
   der tabellen skifter eier.
2. **Rekkefølgen står** (André: «gjør det som er i henhold til best practice»).
   Modellene i fase 2, koden i fase 3, portalfila og ryddingen i fase 4 — da røres hver
   importlinje bare én gang, og den ene fasen med migrasjon står alene.
3. **Deploy-takt som før:** fase for fase, til `rollemodell` og `main` samtidig, med
   suiten grønn på begge databaser før hver push.

Tatt med etter avklaringen: **`accounts/decorators.py`** (3.3) slettes i fase 4 sammen
med testen som er dens eneste leser. Ingen produksjonskode importerer fra den.
