# Beslutningsnotat: flere portaler i én installasjon

Status: **besluttet 17. okt. 2026.** Avklart med André i én samtale samme dag; svarene står
i §3 med hans ord der de var avgjørende. Deretter **gjennomgått tre runder mot koden**, av
to modeller som kontrollerte hverandre (§9) — rettelsene derfra står inne i teksten, og
beslutningene 19–24 kom av dem. Faseplanen er §6, og hver fase står i `TODO.md`.

**Slettes** når modellen er levert. Da er begrunnelsen CHANGELOG sin.

---

## 1. Premisset

Flere enn ett miljø i organisasjonen vil kjøre sine egne vakter i portalen. «Brann» kjører
fotballkamper 1–15 gjennom sesongen, «Landsskytter» ett stevne i året, og de skal ikke se
hverandres mannskap, pasienter eller oppdrag.

**To veier, og vi tar den første** (André): **A** — flere *portaler* i én installasjon, for
samme organisasjon. **B** — én installasjon per organisasjon på Railway, uten kodeendring.
B holdes i bakhånd «avhengig av hvor mye denne appen tar av på sikt». Designet under skal
derfor ikke gjøre B vanskeligere: isolasjonen skal sitte i kolonner, slik at en portal kan
skilles ut til egen installasjon den dagen det trengs.

## 2. Funnene — hva som finnes

Kontrollert mot koden 17. okt. 2026, jf. «Før du designer noe nytt» i `CLAUDE.md`.

| Det som trengs | Hva som står i dag |
|---|---|
| «Iterasjoner av vakt» (kamp 1–15) | `core.Vakt` er scopet for pasienter, oppdrag, KO, park og statistikk (`BESLUTNING_VAKT_SOM_SCOPE.md`) |
| Én vaktliste per vakt | `vaktliste.Vaktliste` er `OneToOneField` til `core.Vakt` |
| Planlegge neste vakt mens denne går | `vaktliste.services.opprett_planlagt_vakt()` lager en vakt med `er_aktiv=False` |
| Avslutt vakt | `core/vaktslutt.py`, bak `@admin_required` i `core/views_vakt.py` |
| Tilgang per modul | `accounts.ModulTilgang(bruker, modul_slug, nivaa)` — **global**, ingen portal |
| Hvilken vakt er aktiv | `AppSetting['aktiv_vakt_id']` — **én for hele installasjonen**, lest i 29 filer (§8) |
| Gruppering av kontoer | **Finnes ikke.** Kontotypene er `person`, `delt`, `enhet` (`accounts/forms.py`) |
| Kontoens korps | `vaktliste.Kontokorps` og `Mannskap.korps` — vaktlistas, ikke kontoens |
| Mannskapsregisteret | Globalt (`BESLUTNING_VAKTLISTE.md` 11.1). `Mannskap.user` er `OneToOneField` |
| Bilkontoene | `oppdrag.Enhet.user` er `OneToOneField` |
| Sist innlogget | `CustomUser.last_login_at` **finnes og oppdateres**, men vises bare i Django-admin og `sjekk_brukernavn` — en manglende flate, ikke en manglende funksjon |
| Fritekst i audit | Logges uten verdi: `oppdrag/signals.py` `FELT_UTEN_VERDILOGGING`, KO-teksten likeså |
| Fritekst i arkiv | **Oppdragsarkivet tar ikke med `fritekst`.** Pasientarkivet har tekstfelt (`problemstilling`, `arsak`, `plassering`) **i SHA-payloaden** |
| Kartet | Egen innlogging. `konto.Gruppe.viser_portalen` er ja/nei; posisjonene er unike på **navn** alene, og `steder_for()` slår opp i *alle* grupper som viser portalen |

`core.Vakt`-docstringen forutså dette: *«Modellen sperrer det ikke for framtiden;
grensesnittet forutsetter én.»* Det er grensesnittet — pekeren til aktiv vakt — som må
endres, ikke vakta.

## 3. Beslutningene

| # | Spørsmål | Beslutning |
|---|---|---|
| 1 | A eller B | **A nå, B i bakhånd** |
| 2 | Navnet | **«portal» på skjermen, `Vaktportal` i koden.** «portal» betyr allerede *produktet* i `base_portal.html`, `portal-utils.js`, `PORTAL_MILJO` og kartets `/api/portal/`; ett ord for to ting gjør `grep` ubrukelig |
| 3 | `/portal-admin/` | **Blir `/admin/`**, med 301 fra den gamle en periode. Django-admin står på `/django-admin/` og bare under DEBUG, så stien er ledig. Backup-slugen `portal` står — den står i filnavn som ligger 730 dager offsite |
| 4 | Roller | **Global admin, moderator, medlem. Ingen portaladmin** (André: «Admin er admin og moderator er den som styrer sin portal med admin som universal tilgang/kontroll») |
| 5 | Rollen hører til | **Paret (bruker, portal).** Moderator i Brann kan være medlem i Landsskytter |
| 6 | Hvilken portal står du i | **Sesjonen, med fanevakt** — §4.4. Ikke portalen i URL-en |
| 7 | Moderator og kontoer | **Oppretter, legger til og fjerner — sletter aldri.** Fjerning tar bare raden i portalen |
| 8 | Moderatorens brukerliste | **Liste, sortert på tilhørighet — men bare de tilhørighetene admin har lagt i portalen** (§4.3). lege02 er «annet», ikke korps |
| 9 | Korpslista | **Per portal** («noen er bare for sitt lokale korps, noen vakter er mer tverrfaglig») — som et utvalg fra én felles katalog, ikke egne tabeller |
| 10 | Hvem lager tilhørigheter | **Bare admin.** En konto kan ha flere |
| 11 | Mannskapet | **Per portal.** «Brann-portalen ser bare mannskapslisten i vaktlisten fra sine vakter. Ikke andre portaler» |
| 12 | Bilkontoene | **Globale.** `Enhet` er felles; bilen får tilgang per portal som andre kontoer |
| 13 | Modultilgang | **Admin setter portalens moduler og tak; moderator deler ut innenfor** |
| 14 | Avslutt vakt | **Moderator.** Gjenoppretting og hard-delete står hos admin |
| 15 | Sladding av fritekst | **Admin, KO først**, med sladderegister som kjøres på nytt etter gjenoppretting (§4.9) |
| 16 | Opprydding | **Admin ser «Sist innlogget», portalene, og filtrene «Uten portal» og «Inaktiv 12 mnd»** |
| 17 | Innstillingene | **Sorteres i system og portal** (§4.7) |
| 18 | Kartet | **Gruppe → én portal, gruppevelger i kartet, ny vakt tømmer posisjonene** (§4.10). Separate innlogginger står |
| 19 | Hvilken vakt er aktiv | **`Vakt.er_aktiv` med en delvis unik indeks per portal**, ikke en peker (§4.1) |
| 20 | Medlemskap og modulrad | **`ModulTilgang` henger på `Portaltilgang` med `CASCADE`** — én sannhet (§4.2) |
| 21 | Ingen portal valgt | **Portalregelen** (§4.4): én mulig velges og lagres i sesjonen; flere stopper lesing og skriving til valget er tatt; null er foreldreløs. **Aldri «Standard» som reserve** |
| 22 | Pasientens fallback | **Fjernes**, med `lag_pasient()` til testene (§4.13) |
| 23 | Verdimengdene | **Sted og person er per portal, fag er globalt** — tabellen i §4.12 |
| 24 | Én-til-én fra konto til portaldata | **Unik per (portal, konto)** — `Mannskap.user`, `Kontokorps`, `Ansvarsmerke`, `Forstehjelper.user`, `Helsepersonell.user` (§4.12) |

## 4. Modellen

```
CustomUser (global: admin | bruker)        én innlogging, én MFA — som i dag
  ├─ Kontotilhorighet ──▶ Tilhorighet       «HGSD» (korps), «Leger» (annet)
  └─ Portaltilgang(bruker, portal, rolle)   moderator | medlem
       └─ ModulTilgang(bruker, portal, modul, nivå)

Vaktportal                                  «Brann», «Landsskytter»
  ├─ aktiv_vakt ──▶ core.Vakt
  ├─ tilhorigheter (M2M)                    hvilke admin har lagt i portalen
  ├─ Portalmodul(modul, tak)                hvilke moduler, og høyeste nivå
  └─ core.Vakt (FK portal)                  «Kamp 7 mot Molde»
        └─ Vaktliste (1:1, som før)
```

### 4.1 `Vaktportal` og aktiv vakt

`core.Vaktportal(navn, slug, er_aktiv)`. `core.Vakt` får `portal` (FK, `PROTECT` — en
portal med vakter slettes ikke, den deaktiveres). Én aktiv vakt *per portal* — samme
begrunnelse som før (et vaktvalg i hver visning er en pasient på feil vakt), bare én etasje ned.

**Ingen peker** (beslutning 19). `AppSetting['aktiv_vakt_id']` erstattes av
`Vakt.er_aktiv` med en **delvis unik indeks på `(portal) WHERE er_aktiv`**, og
`core.vakt.hent_aktiv_vakt(portal)` leser den. Tre grunner:

- **Databasen håndhever regelen.** I dag er pekeren fasit og `er_aktiv` en kopi som kan
  komme i utakt (`core/views_vakt.py` sier det selv: «Pekeren er fasit»).
- **En peker på portalen ville gitt en sykel** `Vaktportal → Vakt → Vaktportal`.
  `utled_restore_models` legger sykler bakerst alfabetisk og logger — i `portal`-handleren,
  som står først i gjenopprettingsrekkefølgen.
- **Låsen finnes fortsatt:** `laas_aktiv_vakt()` låser portalraden (`select_for_update`)
  i stedet for `AppSetting`-raden. Gjenåpningen slår allerede av de andre før den slår på
  sin egen (`core/views_vakt.py`), som er rekkefølgen en unik indeks krever.

Eksisterende data går til én portal, «Standard». **Med én portal skal ingenting se
annerledes ut:** ingen velger, ingen ny meny. Det er det som gjør de første deployene trygge.

### 4.2 Roller og tilgang

- **`Portaltilgang(bruker, portal, rolle)`** med `moderator | medlem`. Ingen rad = ingen
  tilgang til portalen, samme prinsipp som `ModulTilgang`.
- **`ModulTilgang` henger på `Portaltilgang`, med `CASCADE`** (beslutning 20), og
  unikheten blir `(portaltilgang, modul_slug)`. En modulrad uten medlemskap kan da ikke
  finnes, og «fjern fra portalen» er én sletting. En egen `portal`-FK ved siden av
  medlemskapet ville gitt to sannheter om samme ting — feilen `kan_redigere_*`-flaggene var.
- **`har_tilgang(user, …)` beholder signaturen.** Den aktive portalen legges på
  brukerobjektet av middlewaren som leser sesjonen, ved siden av tilgangscachen som alt
  ligger der (`core/auth_decorators.py`). De 56 kallstedene endres ikke. **Mangler
  portalen på brukeren, er svaret ingen tilgang** — aldri «Standard» (se §4.4).
- **`Portalmodul(portal, modul_slug, tak)`**, satt av admin. Moderator deler ut innenfor
  taket. En modul uten rad finnes ikke i portalen, heller ikke i menyen.
- **Moderator kan aldri dele ut over eget nivå eller over taket**, og aldri gjøre noen til
  moderator eller global admin. Moderatorer utnevnes av admin.
- **Global admin** står utenfor som i dag: alle portaler, alle moduler, toppen av stigen.

### 4.3 Tilhørighet

Én global katalog, `Tilhorighet(navn, kortnavn, type, er_aktiv)` med `type ∈ {korps, annet}`.
Bare admin oppretter. En konto kan ha flere (`Kontotilhorighet`).

Admin velger per portal hvilke tilhørigheter som er med. **Det ene valget styrer to ting:**

1. **Moderatorens brukerliste** — kontoer med portalens tilhørigheter, gruppert og sortert
   på dem. Kontoer utenfor ser moderator ikke, og en ny konto må få en av portalens.
2. **Vaktlistas korpsliste i portalen** — tilhørighetene av typen `korps`. «Leger» er ikke
   et korps i vaktlista.

**Hvorfor én katalog og ikke korps per portal:** da finnes «HGSD» én gang. Med egne
tabeller per portal og en kontogruppe ved siden av, finnes den tre steder og glir fra
hverandre. Prisen er at moderator ikke kan opprette et korps selv.

**`vaktliste.Korps` blir katalogen.** `accounts` og `core` får ikke importere en modul
(avhengighetsretningen), så katalogen må bo i `core`. Mønsteret er `AppSetting`: modellen
flytter, `db_table` beholdes, og `core.backup.GAMLE_MODELLNAVN` oversetter
`vaktliste.korps` i gamle backupfiler. Avgjøres endelig i fase 3, når feltene er lest.

### 4.4 Hvilken portal står du i — sesjonen og fanevakten

**Portalregelen** (beslutning 21). *Mulige portaler* er de aktive portalene brukeren har
`Portaltilgang` i — for global admin alle aktive.

| Mulige | Hva skjer |
|---|---|
| Én | Velges automatisk og **skrives i sesjonen** |
| Flere, ingen valgt | **Både lesing og skriving** stoppes; brukeren sendes til portalvelgeren |
| Null | Foreldreløs konto: en side som sier det, ikke en tom portal |

Valget lagres **én gang** og står til brukeren bytter selv — regnes det ut per forespørsel,
blir hun kastet til velgeren midt i arbeidet den dagen admin legger henne til i portal
nummer to. Men det **kontrolleres ved hver forespørsel**: er hun fjernet fra portalen, eller
er den deaktivert, er valget ugyldig med en gang. Med én portal i installasjonen velges den
for alle — testene som logger inn med `force_login` går derfor uendret.

**Sesjonen alene er farlig:** bytter fane B portal, skriver fane A plutselig i feil portal.

Derfor **fanevakten**: siden vet hvilken portal den ble tegnet for, `apiFetch` sender den
i `X-Portal` (samme grep som `X-Portal-Inaktiv`), og en middleware svarer **409** — «Du
byttet portal i en annen fane. Last siden på nytt.» — når den ikke stemmer med sesjonen.
Skjemainnsendinger bærer den som skjult felt. Portalnavnet står i toppen av hver side og
først i fanetittelen, slik miljømerket gjør.

| Valg | Hvorfor |
|---|---|
| Sesjon, ikke URL | URL-modellen endrer hver sti og hvert kall i 38 JS-filer; fanevakten gir samme vern |
| 409, ikke stille omdirigering | En skriving som havner i feil portal er verre enn en som stoppes |
| Mangler headeren på en skriving: avvis | Ellers er vakten valgfri, og den første glemte stien er hullet |
| Offline-køene får portalen i nøkkelen | En kø fra Brann skal ikke spilles av i Landsskytter på samme PC (`brukerNokkel()`, `koNokkel()`) |

### 4.5 Mannskapet per portal

`Mannskap.portal`. Isolasjonen sitter i kolonnen, ikke i et filter som kan glemmes — og det
er nettopp den formen B trenger.

- **Ulempe, akseptert:** går Ola vakt i to portaler, er han to rader, og et nytt
  telefonnummer rettes to steder.
- **«Hent inn fra de siste to årene»:** når en vakt opprettes, foreslås alle med en
  `Vaktpost` i portalens vakter de siste 24 månedene. Samme frist som radnivået ellers.
- **Følgefeil som må tas med:** `Mannskap.user` og `Kontokorps.user` er `OneToOneField` i
  dag. Én konto skal kunne kobles i hver portal, så de blir unike per `(portal, user)` —
  regelen i §4.12.
- **Personvernet:** retting og sletting av én person skjer i flere rader. Innsyn og sletting
  krever derfor et søk på tvers av portalene, på e-post og navn, for admin.
- Overnattingsregelen «én person, ett sted, per natt» gjelder innen portalen.

### 4.6 Bilkontoene er globale

`oppdrag.Enhet` står felles: «Haugesund 56» finnes én gang. Bilkontoen får
`Portaltilgang` i portalene den skal brukes i, og velger portal ved innlogging som andre.
`Ressurs.enhet` kan peke på samme enhet fra to portaler. Kontoopprettelsen for «bil» (en
av radene i `KJENTE_UNNTAK_RAMMEVERK`) endres ikke av dette.

### 4.7 Innstillingene

`AppSetting` blandes i dag. Sorteringen fullføres i fase 4; utgangspunktet:

| Kurv | Nøkler |
|---|---|
| **System** | sesjonstid, backup og offsite, `statusmelding`, `kart_delt_posisjon_min`, `cron.*`, `park_angrefrist_min` |
| **Portal** | `aktiv_vakt_id` (blir `Vaktportal.aktiv_vakt`), `vaktliste_fil_*`, `vaktliste_vis_pauser`, `oppdrag_lyd_*`, `oppdrag_krev_grov_avreist`, `ko.*`, `tavle.*`, `park_ko_posisjon`, `park_hjelp_varighet_min` |
| **Tellerne** | `next_patient_nr_vakt_<id>` m.fl. er allerede per vakt, og dermed per portal |
| **Avgjøres** | `oppdrag_fritekst_frist_dager` — en slettefrist er personvern og hører trolig til systemet |

Portalens innstillinger lagres per portal med systemverdien som standard. Moderator ser
portalens kort på innstillingssiden; admin ser begge.

### 4.8 Avslutt vakt flytter til moderator

**Endring av `BESLUTNING_ROLLEMODELLEN.md` §3.3** («Ingen modul-admin»). Grunnen til §3.3
var at det irreversible skal ligge hos de få. Det holder fortsatt: «Avslutt vakt» tar
`pre_reset`-backup og kan gjenåpnes til arkivet er kollapset, og er altså reversibelt.
Uten det blir admin flaskehals for hver kamp.

| Moderator, i egen portal | Global admin |
|---|---|
| Avslutt vakt, ny vakt, planlagt vakt, gi vakta navn | Gjenoppretting fra backup |
| | Hard-delete, sletting av tidligere vakt og arkiv |
| | Kollaps av arkiv |
| | Sladding (§4.9) |

### 4.9 Sladding av fritekst

Admin skal kunne fjerne fritekst i etterkant når helseopplysninger har havnet der de ikke
skal (André). **KO først**, så oppdrag og pasient.

1. **Backupene beholder teksten.** De er krypterte, ligger opptil 730 dager offsite og
   kan ikke redigeres — og **en gjenoppretting tar teksten tilbake**. Derfor et
   **sladderegister**: hva (modell, rad, felt), hvem, når og hvorfor, **aldri teksten**.
   Gjenopprettingen kjører registeret på nytt før den melder ferdig. Avviket føres med at
   kopien i backup forsvinner når lagringstiden løper ut.
2. **Audit er trygt** — fritekstfeltene logges uten verdi (§2).
3. **Signaturen.** KO er backup, ikke arkiv, og oppdragsarkivet tar ikke med `fritekst`
   — ingen av dem har en signatur å bryte. **Pasientarkivet har det:** tekstfeltene står i
   `sha_payload()`, og en endring der melder tukling. Sladding der må signere på nytt *med
   registeret som begrunnelse*. Det er grunnen til at pasient kommer sist.
4. KO har allerede begrepet «en linje som er fjernet» (`ko.Logglinje.tekst`, tom).
   Det som mangler er admins søk-og-sladd-flate over hele modulen.

### 4.10 Kartet

I dag ser **alle** i en hvilken som helst gruppe med `viser_portalen` **alle** biler og lag,
og `steder_for()` slår opp «Hovedpost» i alle slike grupper — med to portaler kan
Brann-laget havne på Landsskytters «Hovedpost».

- **Portalen sender portalens slug og vakt-ID** i den signerte meldingen.
- **`Gruppe.viser_portalen` (ja/nei) blir `Gruppe.portal`** (slug, tom = viser ikke).
  Posisjonene, delte posisjoner og `steder_for()` filtreres på den.
- **Posisjonene blir unike per (portal, navn)**, ikke navn alene.
- **Gruppevelger i kartet** for den som er med i flere grupper: kartet viser én gruppes
  tegninger, biler og lag om gangen.
- **Vakt A og B i samme portal krever ingenting av brukeren.** Ser kartet en ny vakt-ID for
  en portal, fjernes posisjonene fra den forrige med en gang. Tegningene står — de hører
  til gruppa, og stadion er det samme hver kamp. Skal en vakt ha eget kart, lages en egen
  gruppe.
- **Overgangen:** kartet godtar en melding uten slug som «standard» til portalen sender den.
- Samme HMAC-nøkkel for installasjonen holder under A. Kartinnlogging felles med portalen
  er et eget prosjekt, ikke dette.

### 4.11 Brukeradministrasjonen

- **Admin:** kolonnene «Sist innlogget» (`last_login_at`) og «Portaler», filtrene «Uten
  portal» og «Ikke innlogget på 12 mnd». Når moderatorer kan opprette kontoer, vokser
  antallet, og en konto som er fjernet fra sin siste portal er **foreldreløs**: den kan
  logge inn, men ser ingenting.
- **Moderator:** brukerne i sin portal, og listen over kontoer med portalens tilhørigheter.
  Ny konto får engangspassord (`must_change_password`). Superbrukerens sperrer
  (`AdminUserEditForm`, `_kan_degraderes()`, `RollenSettesBareGjennomSkjemaeneTests`)
  gjelder uendret — moderatorens flate skriver aldri `role`.

### 4.12 Verdimengdene

Alle er unike på navn for hele installasjonen i dag. **Regelen: det som beskriver et sted
eller en person, er per portal; det som beskriver faget, er globalt** (beslutning 23).

| Per portal | Global |
|---|---|
| `oppdrag.Lokasjon` («skifter fra vakt til vakt») | `oppdrag.Problemstilling` og hastegrad («faglige verdimengder») |
| `patients.Forstehjelper`, `patients.Helsepersonell` — personnavn | `oppdrag.Enhetstype` — bilene er globale |
| KO: `Ansvarsomraade`, `Artist`, `Kjennetegn` — satt opp per arrangement | `vaktliste.Kompetanse`, `vaktliste.Ressursgruppe` |
| `core.Vakt.navn` — unik **per portal**, så begge kan ha «Kamp 7» | park: `Problemstilling`, `Utfall` |

**En én-til-én fra en global konto til portaldata blir unik per (portal, konto)**
(beslutning 24). Dagens fem treff: `Mannskap.user`, `Kontokorps.user`,
`ko.Ansvarsmerke.bruker` (`PortalEid`, ikke en peker til `Portaltilgang`: global admin har
ingen og skal kunne ha samband — 4c, 17. okt.), `Forstehjelper.user` og
`Helsepersonell.user` — og «mine pasienter»-filteret følger med. Regelen står her for at
den sjette skal finnes ved å lese, ikke ved en tilfeldighet.

### 4.13 Kallstedene uten forespørsel

De 29 kallstedene i §8 deles i fire, etter hvor portalen kan komme fra:

| Har | Eksempel | Portalen kommer fra |
|---|---|---|
| **Request** | viewene | `request.user` (§4.2) |
| **Data** | `ko.signals.posisjon_delt`, stemplingen | Reiser med signalet og raden — **slås aldri opp** |
| **Lenke** | parks side uten innlogging (`Parklenke` har verken vakt eller portal) | Lenken bærer portalen |
| **Ingenting** | kommandoer, cron, `import_offline_data` (slår opp på *år*) | Oppgis eksplisitt, ellers feil |

**Pasientens fallback fjernes** (beslutning 22). `Patient.save()` faller tilbake på aktiv
vakt «for tester og shell»; ingen produksjonskode bruker den — begge skrivestiene setter
vakt selv. Et vilkår om «én portal finnes» ville vært installasjonsskopet, ikke brukerens,
og virket helt til portal nummer to ble opprettet. `patients.test_helpers.lag_pasient()`
erstatter den, etter mønsteret fra `oppdrag.test_helpers.lag_oppdrag()`.

### 4.14 Cachenøklene og varslene

- **Endringsnumrene** (`core/endringer.py`) får portalen i nøkkelen. De lekker ingenting —
  de sier bare «hent på nytt» — men med to samtidige arrangementer henter hver Brann-fane
  på nytt ved hver skriving i Landsskytter.
- **Full statistikk** er allerede per vakt (`full:{slug}:vakt:{pk}`), og dermed per portal.
- **Varslene** (`core.Notification`) får portalen, og vises med portalnavn.

## 5. Utenfor denne runden

| Hva | Hvorfor |
|---|---|
| Backup og gjenoppretting **per portal** | Backup er per modul. Én portal kan ikke rulles tilbake alene; en gjenoppretting gjelder alle |
| Felles innlogging med kartet | Eget prosjekt |
| Flere aktive vakter i *samme* portal | Samme grunn som i 2026: ett vaktvalg i hver visning |
| Moderator oppretter korps | Bare admin (beslutning 10) |
| Statistikk på tvers av portaler for moderator | Admin ser på tvers, moderator sin egen |

## 6. Faseplanen

Hver fase kan deployes og rulles tilbake for seg. **Portal nummer to opprettes ikke i
prod før fase 4 er levert** — før det er isolasjonen ufullstendig, og knappen «Ny portal»
kommer først i fase 5.

| Fase | Innhold | Synlig endring |
|---|---|---|
| **0** | `/portal-admin/` → `/admin/`, 301 fra den gamle. **Tas rett før fase 5**, så de nye sidene får riktig sti fra starten | Adressen |
| **1** | `core.Vaktportal`, `Vakt.portal` fylt til «Standard», aktiv vakt som delvis unik indeks, `hent_aktiv_vakt(portal)` i alle 29 filene etter §4.13, pasientens fallback fjernet | Ingen |
| **2** | `Portaltilgang`, `ModulTilgang` på medlemskapet, portalregelen og aktiv portal på brukerobjektet, fanevakten (`X-Portal`, 409), portal i offline-nøklene | Ingen med én portal |
| **3** | Tilhørighet: `vaktliste.Korps` → `core`, typen `annet`, kontoens tilhørigheter, portalens utvalg | Admin får katalogen |
| **4** | Data per portal: `Mannskap.portal`, verdimengdene og én-til-én-koblingene etter §4.12, innstillingene, cachenøkler og varsler (§4.14), portalfilter i statistikk og arkiv, søk på tvers for innsyn | Ingen med én portal |
| **5** | Flatene: «Ny portal», moduler og tak, moderatorens brukere og tilgang, «Avslutt vakt» til moderator, «Sist innlogget» og filtrene, portalvelgeren, «hent fra 24 mnd» | Alt |
| **6** | Kartet, i begge repoer: slug og vakt-ID i meldingen, `Gruppe.portal`, `steder_for()`, gruppevelgeren | Kartet |
| **7** | Sladding: KO, så oppdrag, så pasient med ny signering. **Uavhengig av portalene** og kan tas når som helst | Admin |

**Migrasjonene i fase 1, 2 og 4 skriver data og endrer skjema.** De følger regelen i
`CLAUDE.md` («Migrasjoner»): `SET CONSTRAINTS ALL IMMEDIATE` eller delt migrasjon, og en
prøve i `core/migrasjonsprover.py` kjørt mot PostgreSQL før push. Release-vinduet krever
det samme som `BESLUTNING_VAKT_SOM_SCOPE.md` §6: ny kolonne nullbar og fylt i én deploy,
`NOT NULL` i den neste, og `AppSetting['aktiv_vakt_id']` holdes oppdatert til gammel kode
ikke lenger leser den.

### 6.1 Vaktene som skal holde isolasjonen

Isolasjonen er en regel som må gjelde *hvert* sted, og en manuell gjennomgang holder bare
til neste modell. Samme mønster som `patients/tests_modul_dekorator.py`:

- **Hver modell** har en vei til `Vaktportal` (direkte, gjennom `Vakt`, eller gjennom en
  forelder) **eller** står i en liste over globale modeller med begrunnelse (`Enhet`,
  `Tilhorighet`, `CustomUser`, …). En ny modell uten noen av delene gjør testen rød.
- **Hvert skrivende endepunkt** avviser en forespørsel uten riktig `X-Portal`.
- **En test per modul** med to portaler og én bruker i hver, som krever at ingen svar fra
  den ene inneholder den andres rader.

## 7. Risikoene

| Risiko | Mottiltak |
|---|---|
| Et filter som glemmes → data fra én portal i en annen | Kolonner framfor filtre (§4.5), vaktene i §6.1, portal nr. to først etter fase 4 |
| Fane skriver i feil portal | Fanevakten (§4.4) |
| Gammel kode mot nytt skjema i release-vinduet | To-deploy-mønsteret (§6) |
| Moderator gir seg selv eller andre for mye | Taket per portal, aldri over eget nivå, aldri `role` (§4.2, §4.11) |
| Foreldreløse kontoer hoper seg opp | «Uten portal» og «Inaktiv 12 mnd» (§4.11) |
| Sladdet tekst kommer tilbake med en backup | Sladderegisteret kjøres etter gjenoppretting (§4.9) |

## 8. Kallstedene for aktiv vakt

Leser `hent_aktiv_vakt` eller `aktiv_vakt_id` i dag, utenom tester (17. okt. 2026). Fase 1
gjør hvert av dem til et spørsmål om *portalens* aktive vakt.

| App | Filer |
|---|---|
| `core` | `admin_status.py`, `management/commands/appsetting.py`, `management/commands/verifiser_vakt.py`, `models.py`, `vakt.py`, `vaktsletting.py`, `vaktslutt.py`, `views_vakt.py` |
| `ko` | `kartkobling.py`, `services.py`, `signals.py`, `views.py`, `views_hendelser.py`, `views_innstillinger.py`, `views_program.py`, `views_tavle.py`, `views_utskrift.py` |
| `oppdrag` | `views.py` |
| `park` | `services.py`, `views.py` |
| `patients` | `management/commands/import_offline_data.py`, `migrations/0015_vakt_backfill.py`, `migrations/0016_vakt_er_fasit.py`, `models.py`, `services.py`, `views_patients.py` |
| `statistikk` | `views.py` |
| `vaktliste` | `services.py`, `vaktdrift.py` |

De to migrasjonene røres ikke — de er historikk. Inndelingen etter hvor portalen kommer
fra, står i §4.13. `vaktdrift.lister_i_drift()` («sist satt
i drift vinner») må i tillegg avgrenses til portalen: med to portaler i drift samtidig
ville den ellers valgt den andre portalens liste til sentralbordets besetning.

## 9. Gjennomgangene

Notatet ble lest mot koden i tre runder 17. okt. 2026, av to modeller som kontrollerte
hverandres påstander (André limte svarene mellom dem). Det som endret planen:

| Runde | Funn | Hvor |
|---|---|---|
| 1 | `har_tilgang` kjenner ingen forespørsel; to kallsteder har ingen request; medlemskap og modulrad var to sannheter; pekeren ga en sykel; verdimengdene var ikke avgjort | §4.1, §4.2, §4.12, §4.13 |
| 2 | Park-lenken; `Ansvarsmerke` og hjelperregistrene er én-til-én; lesing må stoppes like mye som skriving | §4.4, §4.12, §4.13 |
| 3 | Valget lagres i sesjonen; fallbacken er installasjonsskop, ikke brukerskop | §4.4, §4.13 |

**Én påstand ble godtatt av begge og var feil:** at header-chipsene lå i en global
statistikkcache (`stats:basic`). Strengen står i en docstring i `core/stats_cache.py`;
det eneste kallstedet bærer vakt-ID i nøkkelen. Søket bekreftet at teksten *fantes*, ikke
at den ble *brukt* — samme felle som kommentarråte i `CLAUDE.md`. Testene i §6.1 er
fasiten for isolasjonen, ikke en gjennomlesing.
