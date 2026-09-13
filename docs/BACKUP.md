# Backup — planen, besluttet 13. september 2026

Hva som skal tas backup av, hvor det ligger, hvor lenge, og hvordan det gjenopprettes.
Dette er planen. Det som *er* bygget står i CHANGELOG, og arbeidslista er `TODO.md`
under «Teknisk gjeld» — dette dokumentet forklarer hvorfor lista ser ut som den gjør.

Bakgrunn: `docs/TEKNISK_GJELD.md` §4. På spørsmål om hva som faktisk går til Scaleway
viste det seg at de fire filene dekker pasienter og oppdrag, og ikke mer — og at de ikke
kan gjenopprettes i en tom database, fordi vakta de peker på ikke er med.

---

## 1. Beslutningen: to lag, hver med sin frist

| Lag | Innhold | Frist | Formål |
|---|---|---|---|
| **Hel backup** | Alt i databasen unntatt sesjoner: brukere med passordhasher, MFA-enheter og backup-koder, `ModulTilgang`, audit- og innloggingslogg, varsler, portalinnstillinger, `Vakt`, alle modulenes data og arkiver | **90 dager**, få filer | Katastrofekopien. Gjenoppretting i tom base er én operasjon |
| **Modulfiler** | Som i dag: `patients`, `arkiv` (heter «Pasientregistreringsarkiv»), `oppdrag`, `oppdrag_arkiv` — pluss `vaktliste` og en portalfil med innstillingene og vaktene | **730 dager** (bucketens livssyklusregel), antallsbegrenset lokalt | Kollapsens sperre (den nekter uten fersk arkivbackup), og gjenoppretting av én modul uten å røre resten |

Begge lagene krypteres med AES-256-GCM før de forlater Railway, og lastes opp til
Scaleway under hvert sitt prefiks (`backups/` og `full/`), slik at livssyklusreglene kan
være ulike.

**Hvorfor to lag og ikke ett.** Én hel fil er enklest å gjenopprette, men den bærer
legitimasjon og logg, og bør ikke ligge i to år. Modulfilene bærer bare modulens data
og *må* ligge lenge, fordi kollapsen etter 24 måneder er irreversibel og krever at
slettingen er gjenopprettbar. Fristen følger innholdet, ikke omvendt.

**Hvorfor hel backup nå, når den ble valgt bort før.** Begrunnelsen mot var at en
backupfil på volumet med passordhasher og TOTP-hemmeligheter er en legitimasjonsdump.
Den var riktig for en ukryptert fil. Med kryptering før opplasting, og en nøkkel Scaleway
ikke har, er innholdet ikke lesbart for noen uten `OFFSITE_BACKUP_KEY`. Prisen for å
*ikke* ha den var at gjenoppretting i tom base begynte med `create_admin` og kontoer for
hånd — og ingen hadde skrevet ned den prosedyren.

## 2. Slettefristene og personvernet

Regelen i databasen er 730 dager for alt som bærer personopplysninger: arkivradene
kollapser, audit- og innloggingsloggen slettes av `purge_old_logs`. En backup er en kopi
som lever ved siden av, og har lov til å ha egen frist på tre vilkår:

1. **Fristen står i protokollen** (A.9) som egen kategori, ikke utledet av databasens.
2. **Fristen er forholdsmessig.** Katastrofekopien dekker «basen gikk tapt i forrige
   uke», ikke «vi vil se fjorårets rader». 90 dager.
3. **Gjenoppretting kjører slettingen på nytt** med en gang: `purge_old_logs` og
   `kollaps_arkiv` rett etter `loaddata`, så det som var slettet i basen ikke kommer
   tilbake.

Merk at dette allerede gjelder modulfilene: en arkivfil tatt dagen før kollapsen
inneholder rader som er nesten to år gamle, og fila selv ligger 730 dager. Radnivået
kan altså finnes hos Scaleway i opptil fire år. Det er innenfor vilkårene over så lenge
det står i A.9 — og det gjør det ikke tydelig i dag. Det rettes i dokumentrunden (§5).

## 3. Det som må bygges, i rekkefølge

Rekkefølgen er bindende, fordi backupen speiler hvor modellene bor.

1. **Flyttingen** (`TEKNISK_GJELD.md` §2): `AppSetting`, `Backup`, `BackupConfig`,
   `hent_aktiv_vakt`, middlewaren, `healthz` og server-status ut av `patients` og inn i
   `core`. Tabellnavnene beholdes. Lasteren får en navnetabell så eldre filer med
   `patients.AppSetting` fortsatt kan lastes, med test.
2. **Portalfila**: `core.Vakt` og `AppSetting` (og `ModuleSettings`) som egen modulfil,
   registrert fra `core`. Uten den kan ingen av de andre gjenopprettes i tom base.
3. **`vaktliste`-handler** etter samme mønster som `oppdrag`: alle modellene, bruker-FK-er
   strippet (`Mannskap.user`, `Utsending.sendt_av` o.l.), `restore_models` barn først.
4. **Hel backup**: én handler som dumper alle apper unntatt `sessions`, med `django_otp`
   inkludert. Eget prefiks offsite, eget antall lokalt (standard 5), egen livssyklusregel
   på bucketen (90 dager). Bare global admin kan ta og gjenopprette den, og
   gjenoppretting krever `{"confirm": true}` som sletting ellers.
5. **Småtingene**: «Vaktarkiv» → «Pasientregistreringsarkiv»; `Lydvarsel` inn i
   `restore_models` i oppdrag.
6. **Testen som mangler**: gjenoppretting av *alle* filene i en tom database, både
   modulfilene i riktig rekkefølge (portal → patients → arkiv → oppdrag → oppdrag_arkiv →
   vaktliste) og den hele fila alene. Testen lager basen med `migrate` og laster inn.
   Uten den vet vi ikke at backupen er en backup.

## 4. Gjenoppretting i tom base — prosedyren som skal inn i runbooken

1. Ny Postgres i Railway, `DATABASE_URL` pekt dit, `python manage.py migrate`.
2. `hent_offsite --list`, hent den nyeste hele fila, `hent_offsite <filnavn>`.
3. Gjenopprett den fra `/portal-admin/backup/` — eller, hvis den hele fila mangler:
   modulfilene i rekkefølgen i §3 punkt 6, deretter `create_admin` og kontoene for hånd.
4. `python manage.py purge_old_logs` og `python manage.py kollaps_arkiv` med en gang.
5. Sjekk `/portal-admin/server-status/`: konfigsjekk grønn, siste backup, offsite.
6. Alle logger inn på nytt; MFA-trust-cookies er ugyldige etter passordbytte, ikke etter
   gjenoppretting — men si det likevel.

## 5. Dokumentene som skal oppdateres når §3 er levert

Skrives i én runde, ikke stykkevis, og tar med seg alt fra 11.–13. september:

| Dokument | Hva som mangler der |
|---|---|
| `docs/TEKNISK_DOKUMENTASJON.md` | Kap. 3 og 4: appene slik de er etter flyttingen (modellene i `core`); kap. 8: to lag, seks modulfiler, hel backup, offsite, gjenoppretting i tom base; kap. 6–7: alt fra sikkerhetsrundene (klient-IP, `js_json`, vendor-bibliotekene, hash-låste avhengigheter, trust-cookien, rate-limiting) |
| `README.md` | Arkitekturavsnittet (moduler og `core`), backup-avsnittet, sikkerhetsavsnittet, `requirements.in`/`pip-compile` |
| `docs/RUNBOOK_VAKT.md` | §8b utvidet med hel backup og prosedyren i §4 over; henvisning til `sikkerhetssjekk.py` (§14 finnes) |
| `docs/PERSONVERN_DOKUMENTASJON.md` | A.2: Scaleway-raden sier «hele databasen», ikke «modulenes data»; A.9: én rad for hel backup (90 dager) og tydelig frist for modulfilene offsite (730 dager); A.10: krypteringen, vendor-bibliotekene, `Clear-Site-Data`; A.11 og A.6: vaktlista som fil på e-post og offline drift på drifts-PC-en (det står alt i TODO under «Reserve og offline») |
| `CLAUDE.md` | Backup-avsnittet: seks handlere, hel backup, hvor modellene bor |
| `docs/DEPLOY_GUIDE.md` | Heter fortsatt «Pasientregistreringssystem». Portal-domenet, AHASend- og offsite-variablene, `requirements.txt` med hasher |
