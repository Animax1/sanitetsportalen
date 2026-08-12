# GDPR – tiltaksplan

**Opprettet:** 12. august 2026
**Status:** under arbeid
**Eier:** André Eritsland (behandlingsansvarlig)

Arbeidsdokument for GDPR-gjennomgangen av Sanitetsportalen. Krysses av etter hvert.
Når alle faser er ferdige, har dokumentet gjort jobben sin og kan slettes — de varige
beslutningene lever i `PERSONVERN_DOKUMENTASJON.md`.

---

## Bakgrunnen — les denne først

Gjennomgangen startet som «er vi GDPR-compliant?». Kodegjennomgangen fant at
personvern­dokumentasjonen beskrev flere kontroller som ikke fantes i koden. Underveis
kom en langt viktigere avklaring, som endret hele grunnlaget:

### Systemet er ikke et journalsystem

Protokollen påberopte seg tidligere helsepersonelloven §§ 39–40 og pasientjournalloven.
Det er feil. Sanitetsportalen er en **operativ pasienttavle** for koordinering under vakt:

- `journal`-feltet er en **Ja/Nei-nedtrekksmeny** ([templates/patients/index.html:979](../templates/patients/index.html#L979)) —
  det registrerer *om* journal er skrevet, i et annet system. Det inneholder ikke journal.
- `problemstilling` er grove triage-kategorier («Stor ytre blødning», «Pustevansker»),
  ikke diagnoser
- Resten av modellen er logistikk: plassering, inntid, påbegynt, obspost, transport
- Ingen navn, fødselsnummer, fødselsdato eller fritekst med kliniske notater

Den faktiske journalføringen skjer i et separat system som helsepersonell bruker.

### Hva det får å si

Journalplikten var **begrunnelsen** for lang oppbevaring. Uten den gjelder art. 5(1)(e)
alene: lagre bare så lenge formålet krever. Formålet er drift under vakt pluss evaluering
etterpå — måneder, ikke tiår.

Det snudde to funn i kodens favør:

| | Opprinnelig funn | Etter avklaringen |
|---|---|---|
| Audit-logg | Doc sa 10 år, kode 730 dager → koden var feil | **730 dager er riktig. Dokumentet var feil** |
| Arkiv radnivå | «Behold radene, sett lagringstid» | **Kollaps til aggregat etter 24 mnd** |

Og det fjernet innsynslogg-plikten, som var forankret i pasientjournalloven.

> **Merk:** dataene er fortsatt helseopplysninger etter **artikkel 9**. Triagekategori,
> problemstilling og «fikk medisiner» er helsedata om en person som er identifiserbar i
> konteksten. At journalplikten faller bort gjør ikke dataene mindre sensitive — det
> endrer hvilke regler som styrer lagringstiden.

> **Forbehold:** den rettslige klassifiseringen er en begrunnet vurdering ut fra koden og
> hvordan systemet brukes, ikke en juridisk betenkning. Alt annet henger på den. Tåler et
> second opinion før protokollen signeres.

---

## Fase 0 — Taushetsplikt ✅ AVKLART

Art. 9(2)(h) er hovedgrunnlaget. Art. 9(3) krever at dataene behandles av noen underlagt
taushetsplikt — helsepersonell har den i kraft av loven, frivillige førstehjelpere ikke
automatisk.

**Status:** alle med tilgang har signert taushetserklæring via organisasjonen.
Erklæringene oppbevares hos organisasjonen, ikke hos behandlingsansvarlig.

**Gjenstår:** A.4 bør navngi organisasjonen og si at plikten er forankret der, slik at
kjeden er sporbar (art. 5(2) ansvarlighet).

---

## Fase 1 — Rettslig grunnlag og lagringstider ✅ FERDIG

Gjennomført 12.08.2026. Protokollen er nå **v1.5**. Gjenstår kun: fyll inn organisasjonsnavnet
som står som `[fyll inn organisasjonsnavn]` i A.4.

- [x] **A.4 grunnlag omskrives.** Helsepersonelloven §§ 39–40 og pasientjournalloven ut.
      Inn: art. 6(1)(d) vitale interesser + art. 9(2)(h), som uttrykkelig dekker
      *«administrasjon av helse- og omsorgstjenester»*. Art. 9(3)-betingelsen dokumenteres
- [ ] **A.9 audit-logg:** 10 år → **2 år** (koden er riktig, dokumentet var feil)
- [ ] **A.9 backup:** «72 timer» → **antallsbasert cap** (`max_backups`, default 50).
      `RETENTION_HOURS = 72` er død kode, se [patients/backup_service.py:35-38](../patients/backup_service.py#L35-L38)
- [ ] **A.9 arkiv:** «JSON-filer ved årsskifte» → databasebasert `VaktArkiv`, 24 mnd radnivå
- [ ] **A.2 + A.9 Railway-backup** inn som egen behandling. Merk: inneholder **hele**
      databasen (brukere, audit, arkiv), i motsetning til modul-backupen som kun har `patients`.
      Aktiv kun ~1 mnd i året, under arrangement
- [ ] **A.6:** nye rader for `VaktArkiv`, `ArkivertPasient` og `core.Notification`
- [ ] **A.6:** korriger `journal`-beskrivelsen — Ja/Nei-flagg, ikke journalkategori
- [ ] **A.12:** «fritekst-risiko eliminert» → beskriv den faktiske kontrollen etter fase 2
- [ ] **A.12:** dokumenter fravalg av innsynslogg, med begrunnelse
- [ ] **A.12:** dokumenter beslutning om full lesetilgang, med begrunnelse
- [ ] **Del B:** ny del for appbrukere/frivillige — de er egen kategori registrerte i A.5,
      men får ingen informasjon i dag

---

## Fase 2 — Kodefikser, lav risiko ✅ FERDIG

Gjennomført 12.08.2026. Hele suiten (501 tester) grønn.

**Sidefunn underveis:** `core/middleware.py` importerte Unix-modulen `resource` ubetinget, noe
som gjorde at hver eneste HTTP-test feilet på Windows. Importen er nå betinget. Uten den fiksen
kunne ingenting av fase 2 verifiseres lokalt.

**Restrisiko fra 2.1:** valideringen ligger i API-laget. `loaddata` (gjenoppretting av backup) og
Django-admin går utenom den, så en gammel backup kan bringe tilbake verdier som ikke ville blitt
godtatt i dag.

- [x] **2.1 Whitelist på kliniske felt.** Serverside-validering i `patient_create`
      ([patients/views.py:261-276](../patients/views.py#L261-L276)) og `patient_detail_view`
      ([patients/views.py:335-337](../patients/views.py#L335-L337)). I dag skrives verdiene
      rett inn fra request-body — kun tidsfelt valideres. Verdimengdene ligger kun i HTML-en
      og må ut i én kilde begge sider leser. Tar med `lege`, som er fritekst og etter alt å
      dømme inneholder et legenavn
- [ ] **2.2 `SECRET_KEY` hard-fail** når `DEBUG=False` og nøkkel mangler
      ([myproject/settings.py:16](../myproject/settings.py#L16)). Sjekk først at
      `.env.offline.example` har nøkkel — offline-modus kjører også `DEBUG=False`
- [ ] **2.3 Varsler slettes etter 30 dager.** Legges i `purge_old_logs` sammen med øvrige
      grenser, så cron-jobben plukker det opp uten endring
- [ ] **2.4 Fjern «Arkiv (filer)».** `archives_view`
      ([patients/views.py:785-806](../patients/views.py#L785-L806)) + URL + UI-seksjon.
      Død kode fra Flask-tiden; mappa `arkiv/` er alltid tom og ligger dessuten på
      containerens flyktige disk på Railway

---

## Fase 3 — Arkiv

- [ ] **3.1 Radnivå i 24 måneder, så automatisk kollaps til aggregat.**
      Begrunnelse: dekker to hele sesonger, så årets vakt kan sammenlignes med fjorårets
      under planlegging før radene kollapser. Deretter er formålet uttømt.

      **Irreversibelt** — radene er borte etter kollaps. Kjør første gang med full eksport
      i hånd. SHA-256-integritetssjekken må regnes over aggregatet i stedet for radene
      ([patients/services.py:715](../patients/services.py#L715)).

      Dere har neppe arkiver eldre enn 24 mnd ennå, så regelen biter ikke umiddelbart.
      Bruk tiden til å verifisere at aggregatberegningen er riktig.

- [x] **3.2 Arkiv som egen backup-modul.** ✅ FERDIG 12.08.2026.
      Ny `ArkivBackupHandler` (slug `arkiv`) med `VaktArkiv` + `ArkivertPasient` samlet.
      Begge er nå ekskludert fra pasient-backupen. Egen `ModuleBackupConfig` via migrasjon
      `core.0005`: døgnintervall, cap 20. 16 nye tester.

      **Fallgruve som ble avdekket underveis:** serialiseringen kjører med
      `natural_foreign=True`, så `VaktArkiv.importert_av` ble lagret som brukernavnet.
      Var kontoen slettet, feilet *hele* gjenopprettingen med `DeserializationError` —
      altså nøyaktig i det scenarioet fase 4.1 nettopp gjorde mulig. Løst med en ny
      deklarativ `strip_fields` på `BaseBackupHandler`: FK-en utelates fra dumpen, siden
      navnet uansett ligger frosset i `importert_av_navn`.

      **Bakgrunn:** i dag er `VaktArkiv` ekskludert fra backup mens `ArkivertPasient` er med
      ([patients/backup.py:29-36](../patients/backup.py#L29-L36)) — barna uten forelderen.
      Har du slettet et arkiv etter at backupen ble tatt, feiler `loaddata` på fremmednøkkel
      og hele restoren rulles tilbake. Du kan uansett ikke gjenopprette et arkiv fra
      pasient-backupen, siden forelderen mangler — så dagens oppsett gir null
      gjenopprettingsevne og bare nedside.

---

## Fase 4 — Brukerkoblingen

Planen er å koble portalbrukere til modulroller (førstehjelper/helsepersonell i
pasientmodulen, tilsvarende i senere moduler). Halve mekanismen finnes:
`Forstehjelper.user` og `Helsepersonell.user` er `OneToOneField` med `SET_NULL`.

### 4.1 `VaktArkiv.importert_av` blokkerte sletting av brukere ✅ FERDIG

Gjennomført 12.08.2026, migrasjon `0012_vaktarkiv_importert_av_navn`. Datamigrasjonen fyller
navnet på arkiver som fantes fra før. 8 nye tester dekker sletting av bruker, at arkivet og
pasientradene består, at begge API-visningene overlever, og at SHA-256 ikke påvirkes.

**Opprinnelig problem:**


`on_delete=PROTECT` ([patients/models.py:180-185](../patients/models.py#L180-L185)) gjør at
en bruker som har arkivert en vakt **ikke kan slettes** — databasen nekter med
`ProtectedError`. Det blokkerer sletterett etter art. 17 for frivillige, og treffer ved
første sletteforespørsel når alle får konto.

Ren bytte til `SET_NULL` er ikke nok: to visninger leser `arkiv.importert_av.username`
direkte ([patients/views.py:910](../patients/views.py#L910) og `arkiv_liste_view`) og får
`AttributeError` på `None`.

Full fiks, samme mønster som `forstehjelper_navn`:

- [x] Nytt felt `importert_av_navn` (CharField) — frosset navn som overlever brukersletting
- [x] Datamigrasjon som fyller feltet fra eksisterende `importert_av.username`
- [x] `importert_av` → `on_delete=SET_NULL, null=True`
- [x] `arkiver_aktiv_vakt()` setter navnet ved arkivering
- [x] `arkiv_liste_view` og `arkiv_detalj_view` bruker `importert_av_visning`

SHA-256-en påvirkes ikke — `_compute_sha256_for_arkiv` hasher kun arkiv-id,
arrangementsnavn, år og pasientradene.

### 4.2 «Mine pasienter» som tilgangsgrense — VURDERT OG DROPPET ✅

Alle med tilgang til pasientregistrering har tjenstlig behov for full oversikt ut fra
vaktens art. Beslutningen dokumenteres i A.12.

---

## Fase 5 — Opprydding

- [x] **Doc-konsolidering.** `docs/`-kopiene var eldre (personvern v1.3 med gamle
      `Behandler`/`deleted_at`-navn). Rot-versjonene er kopiert over og duplikatene i rot
      slettet. Alle tre bor nå kun i `docs/`
- [ ] **Slå sammen backup-flatene** til `/portal-admin/backup/`. Pasientmodulens egen
      backup-side og portal-admin er to UI-er over **samme backend** — samme `Backup`-tabell,
      samme filer, samme `core.backup.restore_backup`. Forvirrende at det ser ut som to
      systemer. Ligger i `TODO.md`
- [ ] **DPIA — nedgradert.** Uten journalplikt, med pseudonymiserte data og begrenset
      omfang er art. 35 trolig ikke utløst. Det billige er en kort skriftlig vurdering av at
      den ikke er nødvendig — ikke en full DPIA

---

## Beslutninger tatt underveis

| Beslutning | Begrunnelse |
|---|---|
| Journalplikt gjelder ikke | `journal` er Ja/Nei-flagg mot eksternt system; feltene er triage og logistikk, ikke klinisk journal |
| Audit-logg: 2 år | Uten journalplikt er 10 år uhjemlet. Kodens eksisterende default er riktig |
| Arkiv radnivå: 24 mnd | Dekker to sesonger for sammenligning, deretter uttømt formål |
| Varsler: 30 dager | Rent driftsvarsel uten dokumentasjonsverdi etter vakt |
| Innsynslogg: fravalgt | Plikten var forankret i pasientjournalloven. Dessuten finnes ingen oppslag per pasient å logge — `patient_detail_view` tar kun PUT/DELETE, lesing skjer som helhetlig listevisning til Tabulator-gridet |
| Full lesetilgang beholdes | Tjenstlig begrunnet ut fra vaktens art |
| Behandlingsansvarlig: privatperson | Bevisst valg per i dag. Innebærer at innsynskrav, avviksmelding og ansvar ligger hos André personlig, ikke hos organisasjonen som kjører vaktene |
