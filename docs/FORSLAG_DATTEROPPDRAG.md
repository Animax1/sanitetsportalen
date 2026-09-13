# Forslag: datteroppdrag — én hendelse, flere pasienter

Status: **idé, ikke besluttet.** Skrevet 13. september 2026 etter et hypotetisk spørsmål
fra André. Ingenting av dette er bygget, og ett spørsmål må besvares av den som sitter på
sentralbordet før noen skriver kode (§7). Arbeidslista er `TODO.md` under «Ideer».

---

## 1. Hva det er, og hva det ikke er

Oppdragsmodulen har allerede **flere enheter på ett oppdrag**
(`BESLUTNING_FLERE_ENHETER_PER_OPPDRAG.md`): én hendelse, flere biler på vei til samme
sted. Dette forslaget er noe annet: én hendelse som viser seg å være **flere pasienter**,
der hver pasient får sitt eget løp — egen bil, egen problemstilling, egen grovsortering,
egen tidslinje. Bussulykken er ett oppdrag når meldingen kommer, og fire oppdrag et kvarter
senere.

Det operative poenget: moroppdraget er ikke en tom beholder. Den første meldingen er
«masseskade ved scene, send to biler», og det er et ekte oppdrag med enheter og
stemplinger. Døtrene oppstår når bilen som er fremme melder at det er tre pasienter, og
operatøren *deler*.

## 2. Modellvalg: peker til moren, ikke egen hendelsestabell

Et datteroppdrag er et vanlig `Oppdrag` med ett nytt felt, `forelder` (nullbar FK til seg
selv, `PROTECT`). Alternativet — en egen `Hendelse`-tabell som grupperer flate oppdrag —
ble vurdert og lagt bort, av to grunner:

- Moren *er* et oppdrag med biler og stemplinger før noen vet hvor mange pasienter det er.
  En gruppetabell måtte enten dobbeltlagre det, eller la den første utrykningen stå
  utenfor hendelsen.
- Alt som finnes i dag — stemplinger, køen i bilen, korreksjoner, «trenger ny ressurs»,
  arkivet — er gyldig for døtrene uten endring, fordi de er oppdrag.

**Dybden låses til ett nivå.** Pekeren tillater et helt tre, men tjenestelaget avviser en
datter av en datter, og grensesnittet og statistikken forstår mor og datter. Trenger vi
mer en dag, er det én sjekk i `services` som slippes, ikke en ny modell.

## 3. Reglene

| Regel | Begrunnelse |
|---|---|
| «Del i datteroppdrag» er én navngitt overgang i `services`, som lager et nytt oppdrag med morens lokasjon og hastegrad som forslag, og eventuelt flytter en bil dit | Samme form som de andre overgangene — data, ikke `if`-er i views. Enhetsbytte finnes allerede |
| Moren er ferdig når alle døtrene er ferdige og ingen bil står igjen på henne | Utledes, lagres ikke — som `enhet_status()` |
| **Pasientantallet bor bare på bladene.** Morens `antall` blir utledet (sum av døtrene) | Ellers telles bussens fire pasienter to ganger. To kilder til samme sannhet går i utakt |
| Historikk og arkivering tar hele treet, aldri en halv hendelse | Et arkiv med moren og ikke døtrene er en hendelse ingen kan lese |
| Døtrene får **egne løpenumre**, ikke «12.1» | Telleren og arkivsignaturen er bygget på heltall. «#14, del av #12» sier det samme |
| Bilens knapper er uendret; kortet får én linje «del av hendelse #12» | Bilen ser sitt eget oppdrag. Hun trenger ikke vite om treet for å stemple |

## 4. Hva vi får ut av det

Loggen blir en hendelse i stedet for løse oppdrag som tilfeldigvis har samme lokasjon og
klokkeslett:

- **Hele hendelsen på én tidslinje** — alle bilene, alle pasientene, fra første varsling
  til siste bil er ledig. Den man vil ha i evalueringen etterpå.
- **Ressursbruk per hendelse**: antall biler, bil-minutter til sammen, og hvor lenge
  samleplassen sto uten ledig bil mens hendelsen pågikk.
- **Spredningen**: tid fra moren ble varslet til hver datter fikk sin bil. Tallet som
  sier om vi hadde kapasitet, eller om pasient nummer tre ventet tjue minutter.
- **Triagebildet per hendelse**: rød/gul/grønn innenfor samme hendelse, ikke bare over
  hele vakta.
- **Hvor ofte en hendelse vokser**: andelen oppdrag som får døtre, og hvor mange. Inn i
  planleggingen av neste vakt, ved siden av belastningskurven i vaktlista.

## 5. Hva det gjør med statistikken

- **«Antall oppdrag» blir tvetydig** i det øyeblikket døtre finnes. Telles på to nivåer:
  hendelser (røtter) og pasientoppdrag (blader). Hastegrad og problemstilling teller
  bladene — det er der pasienten er.
- **Varighetene per bil** er per enhetskobling og endrer seg ikke. Regelen om automatiske
  stemplinger (`summary['utelatt']`) gjelder som før.
- **Responstid trenger to definisjoner for døtre**: fra delingen, og fra morens
  varsling. Datterens «varslet» kan være lenge etter at hendelsen begynte. Begge, med
  tydelige navn.
- Ny bolk «Hendelser» i statistikkfanen med tallene i §4. Arkivstatistikken får det
  samme fra `forelder_nummer` i radformen.

## 6. Teknisk

Mindre enn «flere enheter» var.

| Del | Hva |
|---|---|
| Modell | `Oppdrag.forelder` — nullbar self-FK, `PROTECT`, `related_name='dotre'`. Migrasjon uten data |
| Tjenester | `del_oppdrag(mor, ...)`, dybdesjekk, `er_ferdig()` for mor, utledet `antall`, «trenger ressurs» per blad som før |
| Endepunkter | `POST api/oppdrag/<pk>/del/` (`skriv_full`); lista bærer `forelder_id` og `dotre` |
| Sentralbordet | Døtrene innrykket under moren i `_sorterOppdrag()`; «Del» i detaljvinduet; hendelsestidslinjen slår sammen døtrenes |
| Bilen | Én linje på kortet. Ingen nye knapper |
| Arkiv | `forelder_nummer` i `ArkivertOppdrag` og i SHA-payloaden **bare når satt** — samme grep som `behandlet_at`, så eldre arkiv verifiserer |
| Statistikk | Bolken «Hendelser» i `oppdrag/statistikk.py` og `statistikk-oppdrag.js` |
| Tester | Reglene i §3 (dybde, ferdig, antall, historikk/arkiv av hele treet), signaturlås for radformen med og uten `forelder_nummer`, node-tester for lista |

Anslag: to til tre kvelder, mesteparten på reglene og statistikken.

## 7. Spørsmålet som må besvares først

**Hva skjer med morens bil når den første datteren lages?** Blir den stående på moren,
eller flyttes den til datteren? Det bestemmer hvordan hendelsen ser ut i loggen — om
moren er «den første utrykningen» eller «rammen rundt» — og det er et spørsmål til den
som sitter på sentralbordet, ikke til utvikleren. Svaret skrives inn her før koden.
