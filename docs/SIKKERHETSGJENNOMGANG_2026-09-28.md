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

### Pulje 2 — før `staging` går til `main` (ferdig 29. sep., se CHANGELOG)

Alt her var ny kode på `staging`.

- **Fritekst og personnavn ble frosset inn i statistikken.** `core.vaktstatistikk.frys()`
  lagret `full_stats()` som den var i `VaktStatistikk` — uten lagringsfrist, og med i
  `portal`-backupen, 730 dager offsite. To moduler bar slikt: `annet_tekster` i oppdrag, og
  i KO lista over Rød/Viktig uten ressurs med **tittel, siste logglinje og hvem som lukket**
  (funnet da rettingen ble gjort — ingen av gjennomgangene hadde sett den). Frysingen går nå
  gjennom `frys_stats()`, som tømmer dem; to datamigrasjoner vasker det staging alt hadde.
- **Arkivsletting uten backup og uten reell bekreftelse** — på **tre** veier, ikke én:
  vakt-siden, pasientmodulen og oppdragsmodulen kalte hver sin `delete()`. Nå én tjeneste
  med `pre_slett`-backup, og vakt-siden krever tittelen skrevet inn.
- **Pekeren til aktiv vakt ble byttet uten lås** — ved gjenåpning, og (funnet underveis)
  ved «Avslutt vakt», der to samtidige avslutninger med hvert sitt navn frøs samme vakt to
  ganger, den andre gangen med nuller. Dobbel vaktsletting tok to hele dumper.
  `pre_slett` fikk eget tak (ti per modul).
- **`json_body` godtok `Infinity`, `NaN` og `1e999`** — 500 fra `/lag/r/` uten innlogging.

### Pulje 3 — backup og offsite (ferdig 29. sep., se CHANGELOG)

- **Chifferteksten var ikke bundet til navnet sitt.** AES-GCM hadde bare `SPBK1` som AAD,
  modul-slugen ble lest av S3-metadata, og `restore_backup` *advarte* om modeller utenfor
  handleren, men lastet dem. Med bucketens skrivenøkkel (men ikke krypteringsnøkkelen) kunne
  en gammel `full`-fil legges ut som modulfil og gi tilbake passordhasher og
  TOTP-hemmeligheter. Nytt format `SPBK2` med objektnavnet i AAD; slug og type leses av
  navnet; `hent()` skriver ikke over.
- **`SPBK1` må leses i 730 dager, og kan fortsatt gis nytt navn**, så det egentlige vernet
  er to sperrer i gjenopprettingen: en modulfil laster bare modeller fra modulens apper (og
  modeller flyttet fra dem — ellers ville ekte eldre filer blitt avvist), og en «hel
  database» må ha brukere. Den siste ble funnet under arbeidet: en modulfil med navnet
  `backup-full-…` ville tømt alle tabellene.
- `verifiser_backup` nuller `OFFSITE_*`. `Backupplan` har audit. Feiltekstene vaskes.
  Advarsel på backup-siden når `OFFSITE_BACKUP_KEY` er kortere enn 32 tegn — ikke en hard
  sjekk, fordi den kunne stoppet deployen på en nøkkel ingen vet lengden på.
- **Endret fra planen: audit-loggen står *ikke* urørt ved full gjenoppretting.** Det ville
  krevd at brukertabellen ble slettet uten at Django nullet brukerfeltet på hver audit-rad —
  kirurgi midt i katastrofeveien, for et spor som allerede finnes: pre-restore-bildet, på
  volumet og offsite der ingen fra portalen kan slette det. Auditraden for gjenopprettingen
  navngir nå det bildet.

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
