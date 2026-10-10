# Backup innvendig (core/backup/)

> **Modulfil for rammeverket.** Den lastes når noen arbeider i `core/backup/`. Det hver
> modul må vite — handlertabellen, gjenopprettingsrekkefølgen, `@ikke_under_loaddata`,
> `strip_fields` og at backupfilene bare finnes hos Scaleway og Railway — står i
> `CLAUDE.md` i rota. Her står hvordan maskineriet virker innvendig.

Flyttet ut av rota 10. okt. 2026, uendret, da rota sto 312 tegn under taket.

## Brukerpekerne

**`BrukerpekereStrippesEllerBegrunnesTests` utleder hvilke FK-er dette gjelder**
(17. sep. 2026), i stedet for å stole på at hver handler husker. Regelen er ikke
«alt må strippes» — å beholde pekeren er gyldig når koblingen er verdt mer enn
gjenopprettbarheten — men valget skal være **tatt**, og stå enten i
`strip_fields` eller i `IKKE_STRIPPET` med en begrunnelse. Testen kom av at en
mutant som fjernet en strippet peker overlevde, og den fant fire ustrippede
pekere i moduler arbeidet ikke gjaldt. Det er den verste sorten overlevende:
feilen viser seg bare den dagen man trenger backupen.

## Klokka og planene

**Klokka er en tråd i web-prosessen** (`core/backup/klokke.py`), ikke en
cron-jobb: et Railway-volum kan bare henge på én tjeneste, og `/data` henger på
web-tjenesten. Se «Cron-jobbene» i rota for hva en cron-tjeneste uten volum ville
gjort. `BackupSchedulerMiddleware` står igjen som reservenett gjennom samme
`kjor_forfalte()`, og er det eneste stedet som varsler om at tråden har stoppet
— et varsel om at klokka er død, sendt av klokka, kommer aldri fram.

**`core.Backupplan` styrer hva som skjer når.** Tre moduser — `av`,
`ved_endring`, `alltid` — og intervallet settes fritt som tall + enhet
(minutt/time/døgn). `behold` er cap på filer **på volumet**; oppbevaringen
offsite styres av bucketens livssyklusregel og er noe helt annet.
Modulene arver en `standard`-plan; `full` og `standard` styrer alltid seg selv.
Raden har **to** tidsstempler: `sist_sjekket_at` ved hver vurdering,
`sist_fil_at` bare når noe ble skrevet — uten det første er «ingenting har
endret seg» umulig å skille fra «jobben er død».

**Registeret er fasit for hvilke moduler som finnes, ikke plantabellen.** En
modul uten plan får en med standardverdier første gang klokka ser handleren.
Leste vi tabellen direkte, var en nyregistrert modul uten backup til noen
tilfeldigvis åpnet `/portal-admin/backup/` — og for et arkiv betyr manglende
backup at kollapsen nekter å kjøre, altså en feil som først viser seg to år
senere.

En test som kaller `clear_registry()` må rydde opp med
`core.backup.registrer_alle_moduler()`, ikke med én moduls `register_handlers()`.
Gjør den det siste, mister resten av testkjøringen de andre modulenes handlere,
og feilen dukker opp i en helt annen fil. `core/backup/__init__.py` har derfor
sin egen `register_handlers()` som tar **både** portalfila og den hele.

## Offsite, `gjenopprett` og `verifiser_backup`

**Offsite til Scaleway (13. sep. 2026, `core/offsite.py`):** `create_backup`
kaller `offsite.meld_ny_backup(backup, path)` etter at fila er skrevet — inert
uten `OFFSITE_S3_BUCKET`/nøklene/`OFFSITE_BACKUP_KEY`, og **kaster aldri**:
volumet er første nett, og feilen står i `OffsiteKopi.feil` og på
`/portal-admin/backup/`. Fila **komprimeres først, krypteres så** — chiffertekst
lar seg ikke komprimere. AES-256-GCM, format `SPBK2`+nonce+chiffer med
objektnavnet i AAD (`SPBK1` leses fortsatt). **To prefikser, ett per
oppbevaringstid:** `backups/` for modulfilene (730 dager) og `full/` for den
hele (90 dager) — fristene kan bare skilles i bucketen hvis filene ligger på
hver sin sti, fordi livssyklusreglene filtrerer på prefiks. **Fristene håndheves
av Scaleway, ikke av oss** — nøkkelen har ikke sletterett, og `enforce_cap` rører
bare volumet — så `offsite.livssyklus()` leser reglene *tilbake* fra bucketen og
`_avvik()` sammenligner dem med `FORVENTET_DAGER` på **nøyaktig** prefiks;
`/full` er ikke `full/`, og en regel som treffer ingenting er en oppbevaringstid
som stille ble uendelig. Avviket står på `/portal-admin/backup/`; funksjonen
kaster aldri og cacher i fem minutter. **Prefikset leses av `_prefiks()`, som kjenner tre
former**, og feilteksten bærer koden Scaleway svarte — hvorfor står i `core/offsite.py`. `hent_offsite --list`
/ `hent_offsite <filnavn>` henter, dekrypterer og legger fila i `BACKUP_DIR` med
en `Backup`-rad; prefikset utledes av slugen i filnavnet. **`gjenopprett` er den
som rører basen** (`--list`, `--siste <modul>`, `--hent <objekt>`, `--full`,
`--ja`) — den finnes fordi veien gjennom nettleseren ikke duger i en tom base,
der det ikke er noen å logge inn som. `--ja` er nødvendig og ikke bekvemt:
`railway ssh -- <kommando>` har ingen terminal, så et spørsmål ville hengt.
**Auditraden skrives av `restore_backup`, ikke av viewet**, slik at begge
inngangene etterlater nøyaktig én rad med hvem og hvorfra.

**`verifiser_backup` laster filene som ligger på volumet inn i en engangsbase**
og sammenligner radene mot det filene inneholder — suiten svarer på om koden
virker, denne på om *innholdet* gjør det. Engangsbasen er en flyktig SQLite-fil
i en midlertidig mappe, og `PORTAL_ENGANGSBASE=1` er den ene, navngitte
åpningen i `settings.py`-sjekken som ellers krever PostgreSQL på Railway.
Filene kopieres dit først, så pre-restore-øyeblikksbildene havner i søpla.
Kommandoen kaller `gjenopprett`, ikke `restore_backup`: da er det veien man
faktisk ville brukt som er prøvd, ikke en nabo til den. S3 mockes i
`core/tests_offsite.py` ved å bytte ut `_klient`. Nøkkelen skal også ligge i en
passordbehandler — uten den er bucketen uleselig, og det er meningen.
