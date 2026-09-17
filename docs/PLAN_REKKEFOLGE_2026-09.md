# Strategisk plan: rekkefølgen på teknisk gjeld, backup, datteroppdrag og statistikk

> **Delvis foreldet 17. sep. 2026.** Trinn 5 (datteroppdrag) er strøket — forslaget er
> arkivert og erstattet av `docs/FORSLAG_KO.md`. Trinn 1–4 er gjennomført. Resten av
> notatet står fordi begrunnelsene for rekkefølgen fortsatt gjelder.

Status: **forslag, 13. september 2026.** Skrevet på spørsmål om hva som bør tas først av
de fire tingene som ligger i backloggen etter kartleggingene 13. sep. Underlaget er
`docs/TEKNISK_GJELD.md`, `docs/BACKUP.md`, `docs/archived/FORSLAG_DATTEROPPDRAG.md`,
`docs/BESLUTNING_STATISTIKK.md`, `TODO.md` og `CLAUDE.md`, kontrollert mot koden samme
dag. Arbeidslista er fortsatt `TODO.md`; dette notatet forklarer hvorfor den ser ut som
den gjør. Slettes når rekkefølgen er gjennomført eller endret.

---

## 1. De fire kandidatene på én side

| Kandidat | Hva slags arbeid | Hva som skjer om det ligger | Blokkert av André? | Anslag |
|---|---|---|---|---|
| **Backup** (`BACKUP.md` §3) | Risikoreduksjon | Offsite-kopiene i prod kan **ikke gjenopprettes i tom base** (`core.Vakt` mangler), og **vaktlista er ikke dekket** — mannskap med telefon, e-post og ISSI ligger utenfor alle filer siden prod-merget 11. sep. | Bare livssyklusregelen (90 dager) på bucketen | 3–4 kvelder samlet |
| **Teknisk gjeld** (`TEKNISK_GJELD.md` §2) | Risikoreduksjon / struktur | Ingenting går i stykker. Neste modul og neste utvikler betaler litt mer hver gang. Backupen speiler hvor modellene bor | Nei | 2 kvelder for flyttingen, småtingene underveis |
| ~~**Datteroppdrag**~~ (arkivert 17. sep. 2026) | — | Strøket. Grupperingen hører hjemme i KO, se `FORSLAG_KO.md` §9.3 | — | — |
| **Statistikk-utvidelsen** (`BESLUTNING_STATISTIKK.md`) | Ny funksjon | Ingenting operativt. Sanntidsfanen (A1–A4) har verdi under vakt, B–D er evaluering | **Ja**, fem spørsmål, og underlaget ligger i det gamle repoet | 25–35 timer, 8–12 kvelder |

De fire er ikke samme slags arbeid. To av dem fjerner risiko, to av dem lager noe nytt —
og begge de nye er stoppet på en avgjørelse som ikke kan tas fra kodebasen. Det gjør
halve prioriteringen for oss: det som er ublokkert er det som kan gjøres nå.

## 2. Tre regler rekkefølgen er utledet fra

1. **Tett hullet som kan tape data før du bygger noe som lager mer data.** Én av de
   fire er en reell driftsrisiko i dag. De tre andre er ikke.
2. **Ha en fungerende gjenoppretting *før* den migrasjonen som kan gå galt.**
   Flyttingen i `TEKNISK_GJELD.md` §2 er en tilstandsmigrasjon over fire modeller i
   prod. Den er trygg med testsuiten og `verifiser_migrasjoner`, men det er nettopp
   den typen deploy backupen finnes for — og i dag er backupen ikke gjenopprettbar
   alene. Repoets eget mønster er «backup før, og la prod gå noen vakter» (TODO,
   broene i `Oppdrag.save()`). Det bør gjelde her også.
3. **Ikke bygg videre på en modul før den har hatt sin første skarpe vakt.** Testsuiten
   finner ikke om knappene sitter der hendene forventer dem. Datteroppdrag og
   hendelsesstatistikk legger nye felter i en signert arkivradform; hver variant som
   kommer inn før feltprøven er en variant vi må verifisere for alltid.

## 3. Rekkefølgen

### Trinn 1 — Tett backuphullene, uten å vente på flyttingen (1–2 kvelder)

Det som er uavhengig av hvor `AppSetting` bor, og som lukker risikoen:

- **`vaktliste/backup.py`** etter mønsteret i `oppdrag/backup.py`: alle modellene,
  bruker-FK-er strippet (`Mannskap.user`, `Utsending.sendt_av`), `restore_models` barn
  først. Registreres fra `apps.ready()`. Dette er den største udekkede datamengden.
- **Portalfil fra `core`** med `core.Vakt` og `core.ModuleSettings`. `AppSetting` blir
  stående i pasientfila til trinn 2 — den er dekket der i dag, og gjenopprettingen i tom
  base virker med rekkefølgen portal → patients → arkiv → oppdrag → oppdrag_arkiv →
  vaktliste.
- **Testen som mangler** (`BACKUP.md` §3.6): seed en base, ta alle filene, tøm
  tabellene, gjenopprett i rekkefølge, og sammenlign. Djangos testbase er alt migrert
  og tom, så testen er en vanlig `TestCase`. Kjør den én gang mot PostgreSQL gjennom
  `verifiser_migrasjoner`-infrastrukturen før merge — SQLite har ikke utsatte
  fremmednøkler, og det er der `Vakt`-FK-ene faktisk sjekkes.
- `Lydvarsel` inn i `restore_models` (gjeld 3.4), og «Vaktarkiv» →
  «Pasientregistreringsarkiv». Fem minutter hver, samme commit.

**Ferdig når:** testen er grønn på begge databaser, og `hent_offsite` + gjenoppretting
er prøvd én gang i prod-containeren (står alt i TODO under «Reserve og offline»).
Merges til prod som egen leveranse.

### Trinn 2 — Flyttingen ut av `patients` (2 kvelder)

`TEKNISK_GJELD.md` §2 slik den står: `AppSetting`, `Backup`, `BackupConfig`,
`hent_aktiv_vakt`, middlewaren, `healthz` og server-status til `core`. To ting å
bestemme før koden skrives, og begge er ærlige avveininger:

| Valg | For | Mot |
|---|---|---|
| **Behold tabellnavnene** (`db_table = 'patients_appsetting'`) | Ingen datamigrasjon, ingen `ALTER TABLE`, ingen triggerkø-felle | Tabellene heter `patients_*` i `core` for alltid; neste som leser `\dt` blir forvirret |
| **Døp om tabellene** (`RunSQL ... RENAME`) | Basen speiler koden | En skjemaendring i prod, og en migrasjonsprøve må skrives |

Anbefaling: **behold navnene**, med en kommentar på hver `Meta`. Prisen er kosmetisk,
gevinsten er at migrasjonen er ren tilstand. Modellene har ikke `db_table` i dag, så
navnet må settes eksplisitt — glemmes det, lager migrasjonen tomme tabeller ved siden av
de fulle.

Det andre: **backupfilene bærer modellnavnet** (`patients.AppSetting`, `patients.Backup`
i `patients/backup.py:31–48`). Lasteren får en navnetabell gammelt → nytt, og en test
som laster en fil i gammel form. Sjekk samtidig om audit-loggen lagrer
`app_label.model`-strenger som må mappes på samme måte.

Ta med i samme runde, fordi man er i filene uansett: `patients/backup_service.py` og
`RETENTION_HOURS` (3.3), `BackupConfig`/`db_backup` (løst punkt i TODO — de er samme
sak), og `/portal-admin/` samlet i én URL-fil (3.2, faller ut av seg selv når
server-status flytter). `core/views.py` deles (3.7) når man først flytter ting inn i
den. 3.1 (brukeradmin kjenner pasientregistrene) er en annen retning på gjelden og tas
for seg, ikke her.

**Ferdig når:** 2500+ tester grønne, `verifiser_migrasjoner` OK, og en
oppgraderingssimulering som 11. sep.: base migrert til `main`, seedet, migrert med den
nye koden, alle rader intakt. Backup av prod før merge — og nå er den gjenopprettbar.

### Trinn 3 — Hel backup og portalfila komplett (1–2 kvelder)

Nå bor modellene der de skal, og resten av `BACKUP.md` §3 bygges én gang:

- `AppSetting` flyttes fra pasientfila til portalfila (navnetabellen fra trinn 2 tar
  eldre filer).
- **Hel backup**: én handler over alle apper unntatt `sessions`, `django_otp` med, eget
  prefiks `full/` offsite, standard 5 filer lokalt, global admin og `{"confirm": true}`
  for gjenoppretting. Testen fra trinn 1 får en variant som gjenoppretter den hele fila
  alene.
- **Krever André** når koden er ute: livssyklusregel 90 dager på `full/`.

### Trinn 4 — Dokumentrunden (1–2 kvelder, én runde)

`BACKUP.md` §5 og TODO punkt 3. Tas **etter** trinn 1–3, ikke stykkevis, fordi
`TEKNISK_DOKUMENTASJON.md` og `CLAUDE.md` skal beskrive appene *etter* flyttingen og
backupen i to lag. Personverndokumentasjonen (A.2, A.9) skal beskrive fristene som
faktisk gjelder — den er art. 30-protokollen, og skal ikke ligge foran koden.

### Port — første skarpe vakt med oppdragsmodulen

Ikke kode, men den står mellom trinn 4 og alt under. Modulen er ferdig og testet, aldri
brukt live. Det som kommer ut av den vakta bestemmer hva sentralbordet trenger neste
gang.

### Trinn 5 — ~~Datteroppdrag~~ — strøket 17. sep. 2026

Forslaget var godt formet, og det ble likevel feil svar: grupperingen det beskrev hører
hjemme i KO-modulen, som en `Hendelse` som finnes *før* oppdraget og også dekker lag og
hendelser uten en eneste enhet. `docs/FORSLAG_KO.md` §9.3 har hele begrunnelsen; notatet
selv ligger i `docs/archived/`.

### Trinn 6 — Statistikk-utvidelsen, delt i to (8–12 kvelder)

Sist, og ikke som én blokk. Notatet selv anbefaler «fase 1 + smal fase 2 med kun A1 og
A4», og det er riktig — men to ærlige innvendinger til resten av planen bør avgjøres før
timene brukes:

- **A-nivået (sanntid) er operativt** og har verdi for alle med `patients: les` under
  vakt. Det er den delen som bør bygges, og den trenger F4-lasttesten (3–4 timer, står
  i TODO) *før* seg, ikke etter — akseptansekriteriet er CPU-bruk med 20 brukere på
  fanen, og det kan ikke måles uten en lasttest.
- **D-nivået (Dunn post-hoc, Cramér's V, bootstrap-CI) er statistisk verktøy for
  datamengder vi ikke har.** Én vakt gir noen hundre pasienter fordelt på triage,
  plassering og problemstilling; krysstabellene får celler med n < 5, og «forbedret
  automatisk tolkning» av p-verdier på det grunnlaget vil lese som presisjon den ikke
  har. B-nivået (utfall, plassering, årsak × problemstilling) er nyttig for evaluering.
  Anbefaling: bygg A og B, og la C/D vente til det er sett hva noen faktisk spør om
  etter en vakt. B2 (behandlerproduksjon) holdes utenfor til den er drøftet — notatet
  sier det samme.
- **Underlaget må hentes** fra `C:\Programmering\pasientregistrering` eller skrives på
  nytt før fase 1. Notatet står på egne ben, men A2 forutsetter at audit-loggen dekker
  tildeling av både førstehjelper og helsepersonell, og at loggens frist er lengre enn
  analysevinduet. Det må sjekkes i koden, ikke antas.

## 4. Der dette avviker fra `BACKUP.md`

`BACKUP.md` §3 sier flyttingen skal komme først, «ellers bygges backupen på feil
grunnlag». Det stemmer for portalfilas *innhold* (`AppSetting`) og for hel backup — og
de er derfor lagt i trinn 3, etter flyttingen. Det stemmer ikke for `vaktliste`-handleren,
`core.Vakt` i en fil og gjenopprettingstesten: ingen av dem rører `AppSetting`, og alle
tre kan bygges i dag uten å gjøres om. Prisen for å dele det i to er at portalfilas
modell-liste får én rad til i trinn 3, og at testens forventning oppdateres. Prisen for
å vente er at prod står uten gjenopprettbar backup gjennom den ene deployen som mest
trenger den. Rekkefølgen i `BACKUP.md` bør derfor leses som «innholdet i portalfila
ferdigstilles etter flyttingen», ikke «ingen backuparbeid før flyttingen».

## 5. Hva som trengs fra André, sortert etter når det stopper noe

| Når | Hva | Hvor det står |
|---|---|---|
| Trinn 1, prod-verifisering | IAM-nøkkel og de seks offsite-variablene på prod, prøv `hent_offsite` én gang | TODO, «Reserve og offline» punkt 3 |
| Trinn 3, når koden er ute | Livssyklusregel 90 dager på `full/` | TODO, «Teknisk gjeld» punkt 2 |
| Før trinn 6 | De fem spørsmålene i `BESLUTNING_STATISTIKK.md`, og hvor underlaget hentes | TODO, «Forbedringsbacklog» |
| Uavhengig | Organisasjonsnavn i A.4 | TODO, «Krever Andre» |

Ingen av avgjørelsene stopper trinn 1–4. Det er poenget med rekkefølgen.
