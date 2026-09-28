# Sikkerhetsgjennomgang 28. september 2026

Statisk gjennomgang av `staging` (`f441dc0`), gjort **to ganger, uavhengig av hverandre**, og
så slått sammen. Den ene (A) delte kodebasen i fem angrepsflater — innlogging og rammeverk,
`/lag/r/` uten innlogging, pasient/oppdrag/statistikk, vaktliste/KO/backlog, backup og
admin. Den andre (B) tok de 18 commitene som står på `staging` og ikke på `main`, og et
sveip over resten. Hvert funn under er lest opp mot koden; der de to var uenige, er
uenigheten avgjort i koden og står under «Trukket».

**Ingen kritiske funn.** Grunnmuren holder: dekoratør på hvert view, scope til aktiv vakt
på hvert oppslag, nonce-CSP uten verter, signerte engangstokens, ingen rå SQL, ingen
`|safe`. Men det ene alvorlige funnet — **M1** — lå nettopp i en tilstandsmaskin
dokumentasjonen sa var dekket.

## Det gjennomgangen lærte om seg selv

- **To gjennomganger fant hver sine hull.** A fant kontoovertakelsen, B fant ikke den; B
  fant arkivslettingen og driftspunktene, A vektet dem for lavt eller så dem ikke.
- **Begge hadde feil i lista over det som «holder».** A godkjente brukernavnenes tegnsett
  (`CustomUser` arver `AbstractBaseUser`, ikke `AbstractUser`, og har ingen validator) og
  vaskingen av feiltekster i backup-viewene. B skrev at MFA og reset var solide. En lang
  «sjekket og OK»-liste er ikke dekning.
- **Den som bekrefter vern finner færre hull enn den som prøver å bryte dem.** B fikk
  beskjed om å hoppe over det `CLAUDE.md` alt håndterer; M1 lå der.

## Beslutninger (André, 28. sep. 2026)

| Spørsmål | Svar |
|---|---|
| MFA påbudt for global admin og bootstrap-kontoen? | **Nei.** André har MFA i prod, ikke på staging. Ingen advarsel på server-status heller |
| `manage.py nullstill_mfa`? | **Ja.** Railway-innloggingen er vakta; Railway og GitHub har 2FA. Står i runbook §8d |
| Kontolås på delte kontoer | **Brukernavn + IP**, IP-bremsen står |
| Navnebytte via plasser «åpne for alle» (A11)? | **Nei** — følg ordlyden «satt av til korpset hennes» |
| `konto_finnes` for korps-førere (A12)? | Bare for `kan_lede` |
| Park-lenkens oppetid | Advarsel over 7 dager, ikke et tak |
| Rekkefølge | Puljene gjøres ferdig før `staging` går til `main` |
| `REDIS_URL` i prod | Ikke satt mellom vaktene — **med vilje**, runbook §1b (lavkostnad-modus). Vakt-modus slår den på |

## Puljene

### Pulje 1 — kontoovertakelse (ferdig, se CHANGELOG 28. sep. 2026)

**M1. Et halvferdig MFA-oppsett overlevde at passordet ble byttet.** Den som hadde
passordet til en konto uten bekreftet enhet, stoppet på QR-koden og ventet. Admin
tilbakestilte passordet; `slett_brukerens_sesjoner` slettet bare innloggede sesjoner, og
den halve var anonym. Angriperen sendte koden fra sin egen enhet og var inne — og fordi
resetten satte `must_change_password`, slapp de å oppgi det gamle passordet ved
passordbyttet. Variant: en gammel oppsettsesjon kunne legge til en enhet nummer to etter
at eieren hadde satt opp sin.

Resten av puljen: passordsteget logget `success=True` og `last_login_at` før MFA;
telleren for feilede forsøk tapte samtidige forsøk; `sett_passord` og invitasjonslenken
logget ikke ut; svartiden på «glemt passord» røpet om adressen hadde konto; fem feil passord
fra hvor som helst låste en bilkonto overalt; og det fantes ingen vei tilbake uten en annen
admin når MFA-enheten var borte.

### Pulje 2 — før `staging` går til `main`

Alt her er ny kode på `staging`.

- **Fritekst fryses inn i statistikken.** `_avreist_til()` legger `annet_tekster` inn i
  `full_stats`, og `core.vaktstatistikk.frys()` lagrer payloaden som den er i
  `VaktStatistikk` — uten lagringsfrist, og med i `portal`-backupen, 730 dager offsite.
  Bryter med at fritekst ikke fryses.
- **Arkivsletting uten backup og uten reell bekreftelse.** `bekreft=ja` er et skjult felt
  (`core/templates/core/vakt.html`), og `slett_arkiv` tar ingen `pre_slett`-backup.
  Vaktslettingen på samme side krever begge.
- **Gjenåpning uten lås, og dobbel vaktsletting.** `hent_aktiv_vakt()` leses utenfor
  transaksjonen; to innsendinger av vaktslettingen gir to hele dumper.
- **`json_body` godtar `Infinity`, `NaN` og `1e999`.** `int(float('inf'))` kaster
  `OverflowError`, som ingen av de rundt 40 kallstedene fanger — 500 fra `/lag/r/`, uten
  innlogging.

### Pulje 3 — backup og offsite

- **Chifferteksten er ikke bundet til navnet sitt.** AES-GCM har bare `SPBK1` som AAD, og
  modul-slugen leses fra S3-metadata. Med bucketens skrivenøkkel (men ikke
  krypteringsnøkkelen) kan en gammel `full`-fil legges ut som en modulfil, og
  `restore_backup` laster den — den *advarer* om modeller utenfor handleren, men stopper
  ikke. Da kommer gamle passordhasher og TOTP-hemmeligheter tilbake, uten `--full`-sperra.
  Nytt format `SPBK2` med objektnavnet som AAD; `SPBK1` beholdes som lesesti, prøvd mot en
  ekte blob.
- Full gjenoppretting tømmer `AuditLog` og `LoginEvent`.
- `verifiser_backup` arver `OFFSITE_*` og laster engangsbasens pre-restore-filer opp til
  den ekte bucketen.
- `OFFSITE_BACKUP_KEY` har ingen lengdekrav og avledes med én runde SHA-256.
- `Backupplan` har ingen audit. Feiltekstene i backup-viewene vises uvasket.

### Pulje 4 — opprydding og drift

- Pasienttabellen setter førstehjelper- og helsepersonellnavn inn uten escaping (Tabulator
  skriver formatter-strengen som `innerHTML`). `window.USER_NAME` uten `escapejs`, og
  brukernavn uten tegnsettvalidering. `_csv_trygg` på brukernavnkolonna i auditeksporten.
- Vaktliste: navnebytte via plasser åpne for alle; `konto_finnes` til korps-førere; en
  e-post plantet på egen mannskapsrad kobles stille til korpset neste gang en leder lagrer.
- Park: tokenet slettes ikke ved 403; advarsel når oppetiden passerer 7 dager.
- Adminlista over sesjoner sender rå `session_key`. Enhetskontoer avvises ikke på
  `skriv_full`-endepunktene i oppdrag, eller i statistikkens oppdragskilde.
- `pip-audit` i CI. `X-Forwarded-For` leses bare når `RAILWAY_ENVIRONMENT` er satt. Den
  hele backupen på volumet er ukryptert og bærer TOTP-hemmeligheter — til risikoregisteret.

## Trukket

- **Lekket park-lenke sulter ut de ekte lagene** (A17). Avveiningen er tatt:
  `docs/FORSLAG_PARK.md` — «det er taket per lenke, oppetiden og at lenken kan fjernes som
  stopper ham».
- **Sjekk at Redis er satt i prod** (B). Lavkostnad-modus er bevisst (runbook §1b), og
  dashbordet viser rødt for 2+ arbeidere uten Redis. Kontolåsen tar høyde for det: taket
  per delt konto står i databasen, ikke i cachen.
