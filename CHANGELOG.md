# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

---

## 2026-09-26 — `requirements.txt` under 3.13, skallcachen som vokste, polling i skjulte faner, død CSS (G5)  `#drift #frontend #vaktliste #ko`

**`requirements.txt`** var kompilert med Python 3.11 mens `runtime.txt` sier 3.13. Kompilert
på nytt under 3.13 med de samme pinnene: **oppløsningen ble identisk**, bare overskriften
endret seg — ingen pakke har en markør som skiller de to versjonene i dag. Verifisert med
`pip install --dry-run --require-hashes` under 3.13: alle hjulene har hash. Verdien er at
neste `pip-compile` løser for riktig versjon.

**Service workerens skallcache vokste for hver deploy.** WhiteNoise hasher filnavnene, så en
endret fil fikk ny URL, ble lagt til — og den gamle lå igjen på hver drifts-PC til neste
`VERSJON`-bump. `kopiForst()` kaller nå `ryddEldreUtgaver()` når en fil hentes under et navn
cachen ikke har: alle andre utgaver av *samme fil* (`filnokkel()`, Djangos 12 heks-tegn)
kastes. Andre filer røres ikke. Testen kjører `kopiForst` mot en falsk `caches` i node.

**Polling i skjulte faner.** Endringsnummeret hoppet alt over skjulte faner, men
sikkerhetsnettene under hver side gjorde det ikke — en KO-fane i bakgrunnen hentet logg,
tavle, plan og ressurser hele vakta. `naarSynlig(fn)` og `fanenErSkjult()` i
`portal-utils.js`; sju nett i `ko*.js` og `oppdrag-sentral-lasting.js` går gjennom den.
**Ikke** bilens lydvarsel og henting, køene, klokkene eller KO-vinduenes BroadcastChannel —
det som varsler eller sender skal gå med skjermen av. `core/tests_js_polling.py` leser hvert
`setInterval` ut av kilden og krever `naarSynlig` eller en rad i `UNNTAK` med grunnen.

**Død CSS:** `.role-badge` med fire varianter (`style.css`, fra rollene som forsvant i deploy
2), `.hendelse-hode*`/`.hendelse-tittel` (`oppdrag.css`, grupperingen på tavla som ble fjernet)
og `.vl-fanerad` (`vaktliste.css`). Kontrollert mot maler, JS og Python, også dynamisk bygde
klassenavn.

**scipy/numpy vurdert, ikke endret** — se `TODO.md`: koden tåler at de mangler, så å fjerne
dem er å fjerne χ² og Kruskal-Wallis fra statistikksiden. Et produktvalg.

**Mutasjon:** 9 mutanter, alle røde til slutt. Skallcachen: kallstedet fjernet, den nye
utgaven ikke spart, hashlengden løsnet, vilkåret snudd, filnøkkelen ikke sammenlignet.
Pollingen: `naarSynlig` snudd, `fanenErSkjult` alltid nei, KO-loggen uten gate, og
`sjekkEndringer` uten sjekk — den **så ut til å overleve**, men jeg hadde kjørt
`core.tests_endringer` og ikke `core.tests_endringer_js`; med riktig modul er den rød. To
harnesser som bygde `koTavleStart` alene tar nå med `naarSynlig` fra `portal-utils.js`.

## 2026-09-26 — Offsite-feilen ble vist uvasket to av tre steder; vaskingen og helseprobene ett sted (E6)  `#core #sikkerhet #drift`

**Vaskingen.** `core/offsite.py` hadde sin egen `_vask`, som byttet ut S3-nøklene men ikke
URL-legitimasjon — `core.vask.vask` gjorde det motsatte. Å slå dem sammen avdekket det
viktigste: **`_vask` ble brukt på ett av tre steder der en offsite-feil når nettleseren.**
`OffsiteKopi.feil` (vises på `/portal-admin/backup/`) og den generelle feilen fra
livssykluskortet ble lagret og vist rå. boto3 legger gjerne hele forespørselen i teksten.

- `vask(tekst, *, hemmeligheter=(), maks=None)` tar begge nå: URL-legitimasjon alltid, kjente
  hemmeligheter når kallstedet oppgir dem. **`maks` kapper etter vaskingen** — kappet først,
  kunne en halv nøkkel stått igjen.
- `offsite._vask(melding, maks)` er en tynn innpakning som oppgir tilgangsnøkkel,
  hemmelig nøkkel **og krypteringsnøkkelen**, og brukes på alle tre stedene.

**Helseprobene.** `SELECT 1` og skriv/les/slett-proben sto i både `core/health.py`
(`/healthz/`) og `core/admin_status.py` (server-status), og hadde glidd: server-status sjekket
ikke at `SELECT 1` ga 1, og `/healthz/` skrev «OperationalError: OperationalError». Nå
`maal_db()` og `maal_cache()` i `core/health.py`, som returnerer en `Maaling`. **Målingen er
felles, framstillingen er leserens:** `/healthz/` er offentlig og viser bare unntakstypen;
server-status er admin og viser den vaskede meldingen (`Maaling.feiltekst(detaljert=…)`).
Svaret fra `/healthz/` har samme form som før — Better Stack ser bare på statuskoden.

**Nye prøver som går gjennom den ekte proben.** De gamle `/healthz/`-testene patchet
`_check_cache` og så derfor aldri et ekte unntak; `ProbeneGjennomDenEkteVeienTests` gjør det,
og prøver `SELECT 1` som svarer 0. `core/tests_vask.py` er nye enhetstester for `vask`.
En testfelle underveis: klassefiksturen i `core/tests_offsite.py` har tilgangsnøkkel `'a'`,
og vaskingen byttet ut hver «a» i feilteksten — samme felle testen over allerede advarer mot.
Den nye testen setter realistiske nøkler.

**Mutasjon:** 10 mutanter, alle røde — hemmelighetene ignorert (4), kapp før vask, URL-regexen
av (8), opplastingsfeilen uvasket, den generelle livssyklusfeilen uvasket, `secret_key` ikke
oppgitt, `/healthz/` med detaljert tekst, radsjekken fjernet, server-status' cache alltid
frisk, databasefeil uten `return`.

## 2026-09-26 — Intervallene i vaktlista ett sted, og bilskjermens kopier kan ikke gli (E5, fjerde del)  `#vaktliste #oppdrag`

**Intervallene.** «Slå sammen `(fra, til)` som overlapper eller møtes» sto tre ganger:
`statistikk.union`, `pauser._slaa_sammen` og som egen løkke i `services._overlappstimer`
(sum minus union). Nå `vaktliste/intervaller.py` — `slaa_sammen()` og `sekunder()` — og de
tre kaller den. `slaa_sammen` forkaster tomme og baklengse intervaller selv, så `pauser`
slipper å huske det. Ingen atferdsendring.

**En overlevende mutant avdekket et eldre hull:** sammenslåingen av bemannet tid *per enhet*
i bemanningsstatistikken kunne fjernes uten at noe ble rødt. `Ressurs.enhet` er en FK, så to
ressurser (dagbil og nattbil) kan være samme bil — overlapper skiftene, ville
`bemannet_timer` talt dobbelt. `test_to_ressurser_paa_samme_bil_telles_en_gang` holder det
nå. **Samme dobbelttelling finnes i `enhetstimer`**, som summerer per ressurs — ført i
`TODO.md`, ikke rettet her, fordi det endrer et tall brukeren ser.

**Bilskjermens kopier.** `oppdrag-enhet.js` laster ikke `oppdrag-kort.js` (bilen skal ikke
bære tavlas tilstand for å låne fem enlinjere), så `oppdragsnr`, `hendelsesnr`,
`hastegradKlasse`, `_medAntall` og `_problemMedAntall` står i begge. Kopiene blir stående;
`oppdrag/tests_js_kopier.py` krever at hver funksjon som står i begge filene er lik
(kommentarer unntatt). **Én hadde glidd:** reservetabellen i `lydTerskler()` —
sentralbordets manglet «Plassering», bilens hadde den. Rettet, og testen kjører begge i node
og krever samme svar.

*Vurdert og forkastet:* en felles `oppdrag-ord.js` for de fem. Riktigere på sikt, men en ny
fil er en ny rad i rot-`CLAUDE.md` (34 tegn igjen) og et nytt ledd i lasterekkefølgen på
tre sider — for fem enlinjere som nå ikke kan gli.

**Mutasjon:** 8 mutanter, alle røde til slutt. Intervaller: `<=` → `<` (kanter slås ikke
sammen), `max` fjernet, filteret for tomme fjernet, overlappet uten sammenslåing (9 røde),
`pauser` uten sammenslåing, bemannet per enhet uten sammenslåing — **overlevde**, rød etter
den nye testen. JS: `oppdragsnr` endret i bilen — rød; «Plassering» fjernet igjen — rød
(det er den opprinnelige koden).

## 2026-09-26 — Fem HTML-escapere, to som ikke escapet `'` — og fire byggere utenfor skanningen (E5, tredje del)  `#frontend #sikkerhet #patients`

**Hvorfor:** `static/js/` hadde fem escapere. `_escHtml` (i `portal-utils.js`) og `esc` (i
`notifications.js`) escapet ikke `'` — trygge i tekst og i `"`-attributter, ikke i
`'`-attributter, og navnene sa ingenting om det. Ingen av dem sto i en `'`-attributt i dag.

- **`_escHtml` er slettet.** De seks kallene i `patients-admin.js` bruker `escapeHtml()`,
  som har samme «falsy → tom»-regel og escaper `'`. Ti testharnesser i `oppdrag` og
  `vaktliste` hentet den inn som hjelper uten at koden de prøvde brukte den, og to
  `ESCAPING_CALLS` godtok den; alle er ryddet.
- **`esc` i `notifications.js` escaper `'`.** Den blir stående som egen kopi fordi fila
  lastes av `base_portal`, og sidene under `/portal-admin/` (brukeradministrasjonen) laster
  ikke `portal-utils.js`.
- **`core/tests_js_escaping.py` utleder escaperne** — hver funksjon, også en nøstet, som gjør
  `<` til `&lt;` — og kjører dem i node mot samme fiendtlige streng. Alle skal gi samme
  svar. En ny kopi er med den dagen den skrives. Den ene lovlige forskjellen er falsy:
  `escapeHtml(0)` er `''` og `escHtmlValue(0)` er `'0'`, begge med vilje. (Den femte
  varianten står inline i `admin_status.html` og flytter med G1 — da fanges den.)

**Og en overlevende mutant avdekket et eldre hull:** `${a.tittel}` uten escaping i
arkivlista gikk grønt gjennom både `patients/tests_xss_stats.py` og `core/tests_js_regler.py`.
`HTML_BUILDERS` der er ført for hånd, og **fire byggere sto utenfor**: `loadArkivListe`,
`visArkivDetalj`, `visVakter` (alle `patients-admin.js`) og `fmtChi2Inline`
(`statistikk.js`). Ingen hadde uescapet brukerdata — tallfeltene fra API-et er pakket i
`escHtmlValue()` likevel, så de trenger ingen unntaksliste. Seks lokalt bygde uttrykk står i
`REVIEWED_INTERPOLATIONS` med begrunnelse. **`test_ingen_bygger_staar_utenfor_skanningen`**
sammenligner nå lista med kilden, som `oppdrag/tests_xss.py` har gjort siden 16. sep. —
den samme feilen, i en fil der vernet ikke var kopiert.

**Mutasjon:** 6 mutanter. `'` fjernet i `esc` og i `escapeHtml` — røde; en ny escaper uten
`'` lagt i `backlog.js` — rød (første forsøk traff ikke, ankeret fantes ikke, og ble kjørt
på nytt); `${a.tittel}` rå — **overlevde**, rød etter rettingen; `${d.notat}` rå — rød;
`visArkivDetalj` tatt ut av lista — rød.

## 2026-09-26 — Sesjonsdekodingen ett sted, og passordbyttet tåler en rar sesjon (E5, andre del)  `#core #accounts #sikkerhet`

**Hvorfor:** Djangos sesjonstabell ble dekodet fire steder med tre ulike feilhåndteringer:
`_invalidate_other_sessions` og `_invalidate_all_sessions` i `accounts/views.py` fanget
ingenting, `core/sesjoner.aktive_sesjoner` og `admin_session_kill` fanget alt. Djangos
`decode()` gir selv `{}` for en ødelagt signatur — men gyldig JSON som ikke er et objekt
kom rett gjennom, og da kastet `.get()` **midt i passordbyttet**, før resten av brukerens
sesjoner var slettet. Det er den ene operasjonen der en sesjon som overlever er hele
feilmodusen.

**`core/sesjoner.py`** har nå `dekod(sesjon)` (kaster aldri, alltid dict),
`bruker_id_i(data)` (`int` eller `None`, leser `django.contrib.auth.SESSION_KEY` i stedet
for strengen `'_auth_user_id'`) og `slett_brukerens_sesjoner(bruker, unntatt=None)`. De
fire stedene bruker dem. Sammenligningen er `int` mot `int`, ikke `str(...)` mot `str(...)`.

**Tester:** `core/tests_sesjoner.py` — ikke-objekter gir `{}`, slettingen sparer unntaket,
andre brukere og anonyme, og en uleselig sesjon stopper den ikke.

**Mutasjon:** 8 mutanter, 7 røde. `unntatt` fjernet (4 røde), brukersjekken fjernet (9),
hvert av de to kallstedene i `accounts` fjernet (2 og 4), `unntatt` ikke sendt (3),
`isinstance` fjernet (1), `uid` i `admin_session_kill` nullet (2). **Overlevde:** `if
bruker_id is None: continue` i `aktive_sesjoner` fjernet — ekvivalent, `brukere.get(None)`
tre linjer lenger ned hopper over den samme raden. Sjekken står for lesbarhetens skyld.

## 2026-09-26 — Én `json_body` og én `json_feil`, i `core` (E5, første del)  `#core`

**Hvorfor:** `_json_body` sto i fem moduler (`patients`, `vaktliste`, `backlog`, `ko`,
`oppdrag`) og `_feil` i fire, pluss én i `core.verdilister`. **Innholdet hadde ikke glidd** —
M8 rettet «`[]` gir 500» i alle fem samtidig — men det var fordi M8 fant alle kopiene ved å
lete, ikke fordi noe holdt dem like. En sjette kopi skrevet dagen før M8 ville stått igjen.

**Nå:** `core/jsonkropp.py` har `json_body(request)` og `json_feil(melding, status=400)`.
Alle modulene importerer derfra; definisjonene og de fire `import json` som bare fantes for
dem er borte. Ingen atferdsendring. `patients/CLAUDE.md` pekte på `_json_body` i
`views_common.py` og er rettet.

**Regelen er utledet, ikke listet:** `core/tests_jsonkropp.py` leser alle appene med AST og
avviser en toppnivå-funksjon som heter `json_body`, `_json_body`, `json_feil` eller `_feil`
utenfor `core/jsonkropp.py` — en ny modul er dekket den dagen den kommer. Metoder
(`verifiser_vakt._feil`) rammes ikke. Oppførselsprøvene for `[]`/`null`/`"x"` som sto i
`oppdrag` og `vaktliste` peker nå på `core.jsonkropp`.

**Mutasjon:** 3 mutanter, alle røde — en `_json_body` lagt tilbake i `ko/views.py`,
`isinstance`-sjekken fjernet (3 tester røde, i tre apper), `message` → `melding` i
feilsvaret.

## 2026-09-26 — TODO som ikke stemte, og resten av `hent_aktiv_vakt`-flyttingen (F3)  `#docs #core`

**Hvorfor:** tre punkter i `TODO.md` sa noe annet enn koden.

- **«Flytt `hent_aktiv_vakt` ut av pasientmodulen» var gjort** — funksjonen bor i
  `core/vakt.py`. Men restene sto: re-eksporten i `patients/services.py`, unntaket i
  `TILLATT` (`StatistikkappenNavngirIngenKilde`) og en kommentar på fem linjer i
  `statistikk/views.py` om at flyttingen «hører til den ryddejobben». Punktet er slettet og
  restene ryddet. **Re-eksporten var i bruk:** `views_patients.py`, `tests.py`,
  `tests_arkiv.py` og `tests_arkiv_kollaps.py` importerte `vakt_for_year` fra
  `patients.services` i en *flerlinjes* `import (…)` — et søk på én linje så ingen av dem,
  og det var suiten som sa fra. De importerer nå fra `core.vakt`. `TILLATT` er tom.
- **To punkter om `style-src 'unsafe-inline'`** med hvert sitt tall (271 og «~50»). Slått
  sammen, med tallet talt på nytt: **313** — 209 `style="` i maler, 104 `style=` i JS.
- **Nytt punkt: `core.vakt.opprett_vakt()`.** Tre steder lager `Vakt`-rader, og vaktlistas
  `exists()` før `create()` er et kappløp: to samtidige innsendinger av samme navn gir 500
  (`Vakt.navn` er unik, `IntegrityError` fanges ikke), og `kopier_oppsett` kjører utenfor
  transaksjonen. Kontrollert mot koden før punktet ble skrevet.
- Punktet om rotas tak sa «~170 tegn igjen av 65 500» og hadde en avkappet setning. Nå: ~35
  igjen av 66 000.

**Mutasjon:** 1 mutant — `statistikk/views.py` importerer `hent_aktiv_vakt` fra
`patients.services` igjen — rød nå som `TILLATT` er tom.

## 2026-09-26 — Rot-`CLAUDE.md`: audit-avsnittet sa det motsatte av koden (F2)  `#docs`

**Hvorfor:** avsnittet «Audit-logging» sa at feltendringer logges automatisk av
`audit/signals.py`, og «legg aldri til manuell audit-kode». Begge deler var feil:
`audit/signals.py` fyller bare `app_label`, loggingen skjer i hver moduls egen `signals.py`,
og en handling som **ikke** er en feltendring (frysing, rollebytte, sletting av en vaktliste)
må logges der den skjer. Den som fulgte regelen ordrett, laget nettopp hullene B2 og B3 —
«aldri manuell audit» er en regel som produserer manglende audit.

**Rettet, uten å gjøre rota lengre** (65 975 → 65 966 tegn av 66 000):
- Audit-avsnittet sier nå hvem som logger hva, og peker på `core.arkiv.logg_arkivhendelse`.
- «Importer den i `_REGISTERED_MODULES`» — navnet har aldri eksistert; registeret bygges av
  `_build_registry()`. Rettet i rota og i docstringen i `core/modules.py`, og navnet står i
  `SLETTET` i `core/tests_dokumentråte.py`, så det ikke kommer tilbake.
- Steg 3 sa «legg til permission-flagg på `CustomUser` via migrasjon» — flaggene er borte
  siden deploy 3. Nå: ingen migrasjon, tilgang er `ModulTilgang`-rader.
- `skriv_leder` ble sagt å deklareres av vaktlista og oppdrag; KO og backlog gjør det også.

**Mutasjon:** 1 mutant — `_REGISTERED_MODULES` tilbake i rota — rød.

## 2026-09-26 — Én verdilistefabrikk for oppdrag og KO, i `core` (E2)  `#core #oppdrag #ko`

**Hvorfor:** lokasjonene, enhetstypene og problemstillingene i oppdrag og ansvarsområdene,
konserttypene og kjennetegnene i KO administreres likt — liste for `les`, opprett/endre/
omsortere for den som leder, sletting for global admin med `confirm`. **To fabrikker med rundt
130 like linjer**, og de hadde glidd:

| | oppdrag | KO | nå |
|---|---|---|---|
| Unikt navn | eksakt | uten store/små | **uten store/små** |
| Maks lengde | ingen sjekk — for langt navn ga 500 på PostgreSQL | sjekket | **sjekket**, lest av modellfeltet |
| `ProtectedError` ved sletting | 409 | **500** | **409** |
| Ukjent ID | JSON-404 | HTML-404 | **JSON-404** |
| ETag på lista | ja | nei | **ja** |

**`core/verdilister.py`:** `Verdiliste` beskriver en tabell (felter, «i bruk», faste rader,
ekstrafelt), `lag_views()` gir liste-, detalj- og rekkefølgeviewet. Modulene melder inn
tabellene og sin egen regel for hvem som leder (`oppdrag.views_common.kan_lede`,
`ko.views.kan_lede_ko`) — tilgangen er modulens, mekanikken felles. Ligger i `core` fordi KO
ikke skal kjenne oppdrag. **Rate-limit-gruppene er uendret** (`oppdrag:verdier:…`, `ko:…`).

**`core/jsonkropp.py`** er den første `json_body` i `core` (M8-versjonen). Fabrikken trengte
en, og en sjette kopi ville gjort E5 større; de fem andre samles dit i E5.

**Modulenes egne tester gikk uendret gjennom** (754 i oppdrag, 899 i KO). `core/tests_verdilister.py`
prøver hver forskjell i modulen der den *før* var feil, gjennom den ekte URL-en.
**Mutanter: 8, alle drept** — hver av de fem forskjellene satt tilbake, og de tre portene
(409 ved bruk, `confirm`, admin for sletting).

## 2026-09-26 — Arkivene verifiseres og logges ett sted (E3)  `#core #patients #oppdrag`

**Verifiseringen:** `patients/views_arkiv.py` hadde regelen for «er arkivet tuklet med»
skrevet ut i viewet — radsignaturen, eller aggregatets etter kollaps — mens oppdrag kalte
`core.arkiv.verifiser()`. Samme regel to steder; en endring i den ene ville gitt to svar.
Pasientviewet kaller nå `verifiser(get_handler('patients'), arkiv)`. Handleren henter radene
med samme funksjon arkiveringen brukte, så signaturene er uendret (`ArkivSignaturLaastTests`
grønne).

**Loggingen:** tre former for samme slags hendelse. Pasientarkivet logget «lagret» og «slettet»
som `table_name='backup'` med `record_id=0`; oppdragsarkivet som `oppdrag_oppdragarkiv`, også
med 0; kollaps-kommandoen med arkivets eget tabellnavn og ID. Et søk på «hvem slettet arkivet»
fant det ene og ikke det andre. **`core.arkiv.logg_arkivhendelse()`** skriver nå alle tre på
arkivets tabell og ID, med bruker og IP når det finnes en forespørsel. Gamle rader står som de
sto — bruddet er datert, og `'backup'` → `patients` i `audit/signals.py` blir stående.

**Test:** lagring og sletting gjennom endepunktene gir to rader på `patients_vaktarkiv` med
arkivets ID og admin som bruker — det var udekket. **Mutanter: 5, alle drept** — verifiseringen
alltid «ok», feil tabell i hjelperen, brukeren glemt, slettingen og kollapsen uten logg.

## 2026-09-26 — «Kan lede» i oppdrag: knappen og døra svarer likt (E4)  `#oppdrag #ko #vaktliste`

**Hvorfor:** «kan sette opp verdimengdene» sto to steder med to ulike regler. Knappen
«Valglister» i sentralbordet (`sentralbordkontekst`) sa `er_global_admin or skriv_leder`;
endepunktene bak den (`views_verdier._kan_lede`) sa det samme **pluss** «ikke en
enhetskonto» (M6). En bilkonto med `skriv_leder` fikk knappen og så 403 — en knapp som fører
til en vegg. Nås gjennom `/ko/`, som bygger sentralbordet for alle med KO-tilgang.

**`oppdrag.views_common.kan_lede(user)`** er nå den ene regelen, og begge leser den.

**`er_global_admin(...) or` er borte fra alle tre** (`oppdrag`, `ko`, `vaktliste.kan_lede`):
`nivaa_for` har gitt admin toppen av stigen siden 13. sep. (M10), så `or`-en var overflødig —
og kommentaren ved den i oppdrag påsto fortsatt at admin fikk `skriv_full`.

**Test gjennom inngangene:** `oppdrag/tests_kan_lede.py` spør `sentralbordkontekst` (knappen)
og `POST /oppdrag/api/lokasjoner/` (døra) for leder, bilkonto og `skriv_full`. **Mutanter: 5,
alle drept** — knappen med den gamle regelen; enhetskontoen sluppet inn; nivået ett trinn ned
i oppdrag, KO og vaktlista. Den tredje overlevde først i et for smalt testutvalg; hele
oppdrag-suiten ga 7 røde, og den nye testen dekker den nå selv.

## 2026-09-26 — Ankomster per time: samme svar i begge statistikkene, og i riktig rekkefølge (E1)  `#patients #statistikk`

**Hvorfor:** pasientstatistikken ble regnet to steder, og de ga **ulike tall for samme
vakt**. Grunnstatistikken grupperte ankomst per døgn og time (`'%d.%m %H:00'`), full
statistikk per klokketime (`'%H:00'`) — på en vakt over flere døgn slo den siste sammen
kl. 14 fredag og kl. 14 lørdag. André valgte **døgn og time** («E1 a»): det viser hvordan
vakta gikk, og døgnrytmen kan regnes ut av det — ikke omvendt.

**Og en feil til, i den som var «riktig»:** den sorterte på etiketten, så `'01.10 08:00'`
kom foran `'30.09 22:00'` — en vakt over et månedsskifte sto baklengs i grafen.

**`patients.services.ankomster_per_time(pts)`** er nå kjernen begge bruker. Den sorterer på
tidspunktet og skriver etiketten `dd.mm HH:00` (grafen i `statistikk.js` bruker nøklene som
akse, så den trengte ingen endring). **Allerede kollapsede arkiver** har aggregatet frosset
med signatur og viser fortsatt klokketimene — de røres ikke.

**Ingen test brakk av endringen** — verken klokketime-formatet eller rekkefølgen var prøvd.
`patients/tests_ankomster.py` går gjennom `basic_stats` og `full_stats` (ikke hjelperen) med
data over et månedsskifte. **Mutanter: 3, alle drept** — tilbake til klokketime, sortering på
etiketten, og full statistikk med sin egen regel igjen.

## 2026-09-26 — Tilgangsreglene i docstringene sa det motsatte av koden (F1)  `#vaktliste #accounts #oppdrag`

**Hvorfor først i pulje F:** den som leser en docstring før hun endrer en tilgangsport, leser
feil regel. Fasit er `vaktliste.services.ser_alle_korps()`: **`les` ser sitt eget korps,
`les_alle` og oppover ser alle** — også `skriv_handling`, snudd 12. sep. 2026 («Endre skrive:
eget korps til å inkludere lese: alle korps»), men som fortsatt bare *fører* sitt eget.

| Hvor | Sa | Nå |
|---|---|---|
| `vaktliste/views.py` | «`les` — hele lista, alle korps (§4.4)» | eget korps; `les_alle`+ alle; peker på `ser_alle_korps()` |
| `vaktliste/services.py` | «`les` gjelder hele lista med vilje» | peker på `ser_alle_korps()` |
| `vaktliste/module.py` | `skriv_handling` «ser likevel bare sitt eget korps»; vaktlista «den eneste modulen» med `skriv_leder` | snudd 12. sep.; oppdrag, KO og backlog har det også |
| `accounts/models.py` | «`SKRIV_HANDLING` er tomt i dag … tas i bruk når oppdragsmodulen skrives», pluss de to over | brukes av oppdrag (bilen) og vaktlista |
| `vaktliste/tests_tilgang.py` | tabellen: `kb` «ser likevel bare sitt eget» — mens testen rett under krevde `{'Kari', 'Ola'}` | «alle — fører bare sitt eget» |
| `docs/BESLUTNING_VAKTLISTE.md` | «Synligheten følger ikke stigen» | datert: snudd 12. sep. |

**De to siste fantes ikke i planen** — de dukket opp da jeg søkte etter flere kopier av de
samme setningene. En regel skrevet ut seks steder glir fra hverandre; derfor peker tekstene nå
på funksjonen i stedet for å gjenta regelen.

**`lokasjon`-kommandoen** sa at oppdragsmodulen «har ingen URL ennå» — den har hatt det siden
fase 3, og lokasjonene redigeres i «Valglister». Kommandoen står igjen som verktøy (grei for å
fylle staging), med ny tekst. **Testen hadde en død `skipTest`-gren** (`if modul.url is None`)
som ville hoppet stille over seg selv den dagen URL-en faktisk forsvant; nå `assertIsNotNone`.

**Mutant: 1 gyldig, drept.** Den første kjøringen traff `url=None` i *docstringen* til
`oppdrag/module.py` og gikk grønn — løgn nr. 1 i mutasjonsavsnittet. Mot kodelinjen: rød.

## 2026-09-26 — Brytere og ruter uten virkning: `/api/` gir 410, `backup_enabled` ut, `createcachetable` ut (D4)  `#core`

**`/api/…` svarer 410 i stedet for 301.** Adressene flyttet til `/pasienter/api/` i fase 2.
En **301 gjør en POST om til en GET** i nettleseren, så en gammel klient som lagret noe fikk
et svar uten at noe ble lagret — stille. Ingen JS i portalen bruker dem; `/api/varsler/` og
`/api/endringer/` har egne ruter foran. **Hvert treff logges som advarsel**
(`core.api_flyttet`): André søkte på `path=/api/` i Railway uten funn, men de linjene tar
bare trege forespørsler (over 200 ms eller over 1 MB minne) — derfor fant han ikke
`/api/endringer/` heller, som polles hvert 2,5 s. Uten advarselen ville et gammelt kall vært
usynlig. `sikkerhetsruter.json` er regenerert (9 omdirigeringer, var 10), og 410 teller som
«stengt» i testen og i `scripts/sikkerhetssjekk.py`.

**`ModuleSettings.backup_enabled` er ute av modellen — i to steg.** Feltet hadde ingen
virkning (hjelpeteksten sa selv «ingen effekt»), og en bryter som ikke gjør noe ser ut som en
beslutning. Å slette kolonnen i samme deploy ville gitt 500 i vinduet der Railway har kjørt
`migrate` men ikke byttet container: den gamle koden velger kolonnen i hver spørring mot
moduloppsettet. `core/0012` er derfor `SeparateDatabaseAndState`: Django glemmer feltet, og
kolonnen får `db_default=False` — på PostgreSQL bare `SET DEFAULT false`. **Prøvd mot ekte
PostgreSQL:** ny kode oppretter en rad (kolonnen får `false`), gammel kodes `SELECT` virker.
**Deploy 2 — slette kolonnen — står i TODO.** Gamle portalfiler bærer feltet;
`UTGAATTE_FELT` tar det ut, og en rundtur-test laster en slik rad.

**`createcachetable` er ute av `Procfile`.** Den lager bare tabellen for Djangos
*databasecache*; portalen bruker Redis eller LocMem. `TEKNISK_DOKUMENTASJON.md` påsto at
`django-ratelimit` trengte den, og feilsøkingsavsnittet for 500 ved innlogging anbefalte å
kjøre den. Begge er rettet — rate-limitingen faller dessuten åpen ved cachefeil.

**Migrasjonsprøvene fant en feil hele suiten gikk forbi.** `verifiser_migrasjoner` migrerer
til et *eldre* punkt (`migrate vaktliste 0006`), og da fyrer `post_migrate` — der
`_ensure_module_settings_defaults` lagde moduloppsett med **dagens** modell. Den kjenner ikke
`backup_enabled`, mens kolonnen på det punktet ennå var `NOT NULL` uten standard:
`null value in column "backup_enabled" … violates not-null constraint`, alle tre prøvene røde.
En vanlig `migrate` til siste versjon går forbi det, så deployen hadde trolig virket — men
mottakeren bruker nå den **historiske** modellen fra `post_migrate` (`kwargs['apps']`), som er
riktig uansett. **4 681 tester grønne på SQLite, og feilen synes bare mot PostgreSQL med
prøvene** — CI (D1) ville stoppet den før deploy.

**Mutanter: 5, alle drept.** 410 → 200; advarselen fjernet; `db_default` fjernet (gir
`NOT NULL constraint failed: core_modulesettings.backup_enabled` ved første nye modulrad —
nøyaktig det prod ville fått); raden i `UTGAATTE_FELT` fjernet; ruten tilbake i
`OMDIRIGERER`.

## 2026-09-26 — Én skanner for markup bygget med `+`, for alle JS-filene (D3)  `#core #backlog #ko`

**Hvorfor:** `backlog.js` bygger markup med `'<…' + x` og hadde ingen statisk skanner. KO
hadde sin egen, i `ko/tests_js.py`. Prøvd på alle filene: **elleve** bygger markup slik.

**`core/tests_js_konkatenering.py`:** byggerne **utledes** av kilden (en funksjon som limer
noe inn i en streng med en tagg), så en ny fil er dekket uten at noen fører den opp. Hvert
datafelt (`rad.navn`) skal escapes eller stå i `GJENNOMGATT` med grunn — tre rader.
`test_unntakene_finnes_fortsatt` sier fra når en rad blir død.

**Funn:** 14 treff utenfor KO, **ingen ekte hull** — ID-er (tall), `textContent`, og
verdier escapet lenger ned. Regexen fikk `.` i lookaheaden, så `s.grupper.map(` ikke lenger
gir falske treff. `backlog.js` fikk `escHtmlValue()` på ni ID-er i stedet for unntak.

**KO sin kopi er fjernet, og med den en død liste.** `KO_GJENNOMGATT` hadde 32 «gjennomgåtte»
lokale variabelnavn — men regexen krevde et punktum, så **ingen av dem kunne noen gang
treffe**. En unntaksliste som ikke påvirker noe, ser ut som en dekning den ikke er.

**Grensen, skrevet ned:** lokale variabler (`+ merke`) skannes ikke — 131 av dem. For dem er
oppførselsprøvene motmiddelet. TODO-punktet om vaktlistas `+`-hull er skrevet om til dette.

**Mutanter: 7 gyldige, alle drept til slutt.** Én overlevde først: at kommentarene strippes før
skanning. Ingen kommentar i dag slo ut, så ingenting merket det. Prøvd nå gjennom `byggere()`
med en midlertidig fil — ikke ved å kalle hjelperen, så også et fjernet kallsted blir rødt.

## 2026-09-26 — Død kode som testene holdt i live (D2)  `#vaktliste #patients #statistikk`

**Hvorfor:** «løgn nr. 3» fra mutasjonsavsnittet i `CLAUDE.md`, i praksis — tester som kaller
en funksjon ingen annen kode kaller. Suiten ser da ut til å dekke mer enn den gjør, og
funksjonen ser levende ut for neste som leser den.

| Hva | Brukt av | Gjort |
|---|---|---|
| `_posterPerGruppe()` (`vaktliste-oversikt.js`) | tre tester | Slettet. Testene går nå gjennom `_posterIGruppe`, som `mkGruppekurve` bruker |
| `_koMedianP90()` (`statistikk-ko.js`) | bare harnesslista | Slettet |
| `services.vaktspenn()` (`vaktliste`) | én test | Slettet med testen |
| `har_arkiv_backup_etter` (`patients.services`) | ingen | Slettet |
| `kollaps_arkiv` (`patients.services`) | bare testene | Slettet. **Kollapstestene går nå samme vei som kommandoen**: registeret og `core.arkiv.kollaps` — kollapsen er irreversibel, så testene skal prøve veien som faktisk sletter |
| Validatorene «re-eksportert» via `patients.services` | ett view, to tester, én test av omveien | Viewet og testene henter fra `core.validators`. Testen av omveien er slettet, og en ny (`test_ingen_henter_validatorene_via_patients_services`) holder den stengt |

**Det verste funnet:** testen «gruppe uten skift tegnes ikke» prøvde **det motsatte** av det
koden gjør. `mkGruppekurve` tegner en flat kurve uten skift siden 30. aug. 2026 («hullet man
planlegger for å tette er størst når ingen er satt opp»), men den gamle regelen levde videre i
`_posterPerGruppe()` — og testen var grønn. Slettet; den levende regelen har
`test_gruppe_uten_skift_faar_kurven_likevel`.

**«Re-eksporten» var mest en merkelapp:** alle åtte navnene brukes av `patients/services.py`
selv. Det var kommentaren «bakoverkompatibilitet» og `noqa: F401` som var feil, ikke importen.

**Mutanter: 2, begge drept** — filteret i `_posterIGruppe` fjernet (3 røde), og omveien lagt
tilbake i `views_patients.py` (vakten rød).

**TODO:** C3 og C4 står som åpne valg som venter til utviklingen er der (André: «vi er ikke
ferdig med å utvikle og kan holde de der de er inntil videre»).

## 2026-09-26 — Norsk alfabetisk rekkefølge i hele portalen: Æ Ø Å sist, likt overalt  `#core`

**Hvorfor:** raden på server-status viste staging: **«Blandet inn (Æ=AE, Ø=O, Å=A)» —
`en_US.utf8`, PostgreSQL 18.6**. Korps-nedtrekket i vaktlista sto som «Ærø · Ålesund ·
bergen · Ørsta · Oslo», nedtrekket for skift satte «Ærlig Ærdal» over «Anne Berg», og
førstehjelperne i pasientskjemaet likeså. André valgte den hele løsningen framfor å sortere
nedtrekkene i nettleseren, etter spørsmålet «Kompliserer denne sorteringen de ulike
reglene vi har allerede? F.eks vaktliste hvor leder rolle skal stå øverst i skiftene».

**`core/sortering.py` — én regel, tre innganger:**

| Hvor | Bruk |
|---|---|
| `Meta.ordering` / `order_by()` | `Norsk('navn')` → PostgreSQL: `LOWER(x) COLLATE "nb-NO-x-icu"`; SQLite: egen kollasjon `norsk` |
| Python | `sorted(..., key=norsk_nokkel)` |
| JS | `localeCompare(…, 'nb')` |

Norsk rekkefølge: Andøy · bergen · Bergen · Émile · Haugesund · Oslo · Zeta · Ærø · Ørsta ·
Ålesund · Aasen. **«Aa» er Å** (CLDR, som ICU og nettleseren). ICU, `norsk_nokkel` og
nettleserens `'nb'` ga identisk rekkefølge; `BasenSortererNorskTests` holder ICU og nøkkelen
enige i CI.

**`Norsk` er bare navnenøkkelen.** «Lagleder før hospitant» (`Ressursrolle.rekkefolge`) og
«tid før rolle» i skiftene står foran den og er urørt — `RollenFoerNavnetTests` prøver det
med en leder som heter Øyvind.

**Mangler ICU-kollasjonen, faller den tilbake** til `LOWER(x)` — dagens sortering, ikke
en 500 på hver liste. Raden på server-status viser nå **portalens** rekkefølge, med
«Basen alene» under; blir den gul, er kollasjonen borte.

**Omfang — og hvorfor stedene utledes:** 18 modeller (`Meta.ordering`), 19 argumenter til
`order_by(...)`, 6 Python-sorteringer, 9 `localeCompare`. Min første gjennomgang fant 4 av
`order_by`-argumentene; `HverNavnesorteringErNorskTests` fant **15 til** (KO-tavla, programmet, lokasjonene, pasientregistrene, vaktlista som fil,
besetningen) — et søk på `order_by('navn')` så ikke `order_by('rekkefolge', 'navn')`. Testen
leser `Meta.ordering` fra modellene og `order_by(...)` med AST, og `test_regelen_ser_det_den_skal`
holder at den kjenner igjen `'navn'`, `Lower('navn')` og `F('…__navn')`. Unntatt: arkivets
`enhet_navn` (signert radform). **Migrasjoner:** fem `AlterModelOptions` (`*_norsk_sortering`),
uten SQL.

**Bifunn rettet:** `vaktliste/api/mannskap/` teller skift med `annotate(Count)`, og da dropper
Django `Meta.ordering` — lista kom usortert. Eksplisitt `order_by` nå, med test gjennom
endepunktet. **CI kjører PostgreSQL 18**, som Railway (var 16). **Rotas tegngrense hevet til
66 000**, bevisst, med begrunnelse i `core/tests_claude_md.py`; kommentaren om `--parallel`
rettet samtidig (feilen var `tblib`, ikke `core`).

**Tester som før unngikk Æ/Ø/Å bruker dem nå:** «ålesund 1» er tilbake i enhetslista
(`oppdrag/tests_runde_e.py`), og verdimengdetesten i `vaktliste/tests.py` har Ærø, Ølen, Åkra.

**Mutanter: 17 gyldige, alle drept til slutt.** To overlevde: besetningens to
Python-sorteringer (`besetning`, `ressurser_uten_enhet`) kunne byttes tilbake til `.lower()`
— ingen test hadde Æ/Ø/Å der. Tester lagt til i `tests_besetning` og
`tests_ressurser_uten_enhet`. **To mutanter var ugyldige og ble kjørt på nytt:** én traff to
steder, og én ga en syntaksfeil i stedet for å fjerne `connection_created`-koblingen (kallet
går over to linjer) — «rødt» fra en syntaksfeil beviser ingenting. Riktig kjørt gir den
`no such collation sequence: norsk`.

**Kjørt:** hele suiten på SQLite og på PostgreSQL 16 lokalt — 3 823 + 862, grønn begge.

## 2026-09-26 — Server-status viser hvordan basen sorterer Æ, Ø og Å  `#core/drift`

**Hvorfor:** CI viste at «ålesund» sorteres først i en_US og sist i C, og spørsmålet ble
om prod gjør det samme. André: «Jeg syns at vi skal teste først om det faktisk skjer og er
sikre.» SQL-en i Railway ga *syntax error near datlocprovider*, og uten tilgang til basen
fra økta var svaret å la **portalen selv si det** — André: «da har vi mer kontroll».

**Prøvd lokalt mot to PostgreSQL 16-baser gjennom de ekte endepunktene:**

| Base | Korps-nedtrekket i vaktlista |
|---|---|
| en_US (ICU) | Aasen · **Ærø · Ålesund** · Andøy · Haugesund · Korps bergen · **Ørsta** · Oslo · Zeta |
| C.UTF-8 | Aasen · Andøy · Haugesund · Korps bergen · Oslo · Zeta · **Ålesund · Ærø · Ørsta** |

en_US leser Æ som AE, Ø som O og Å som A — «Øyvind Ødegård» står mellom Anne og Ola i
nedtrekket for skift. C legger dem sist, men som Å, Æ, Ø. Førstehjelper-nedtrekket i
pasientskjemaet og mannskapsnedtrekket gjør det samme. **Ikke** berørt: registertabellen i
vaktlista og sentralbordets ressursliste — de sorteres på nytt i nettleseren.

**Og `datcollate` lyver:** en_US-basen, laget med ICU, sa `C.UTF-8`. Raden viser derfor
**svaret, ikke innstillingen** — basen sorterer seks prøvenavn med `ORDER BY lower(n)`,
slik appens egne `Lower('navn')` gjør, og `sortering_vurdering()` kaller svaret `norsk`,
`kodepunkt` eller `blandet`. `datcollate` og versjonen står under, som opplysning.
Prøven har egen `try`: feiler den, står resten av databasekortet.

**Mutanter: 6, alle drept** — vurderingen snudd, `kodepunkt`-grenen fjernet, `ORDER BY`
fjernet, `lower()` fjernet, `try` fjernet, kallstedet fjernet. **`lower()` overlevde
første gang**: prøvenavnene begynte alle med stor bokstav, så `lower()` endret ingenting.
«Bergen» ble «bergen».

**Bifunn, ikke rettet:** `vaktliste/api/mannskap/` bruker `annotate(Count(...))`, og da
dropper Django `Meta.ordering`. Uten følger i dag; ført i TODO.

## 2026-09-26 — CI rød ved første kjøring: «ålesund» sorterte først, og tblib manglet  `#core/drift`

**Første kjøring av D1 (`668acff` på staging) var rød: 1 ekte feil, 31 følgefeil.**

**Den ekte:** `test_enhetslista_er_alfabetisk_uten_hensyn_til_store_bokstaver` ventet
`['bergen 2', 'Haugesund 56', 'Karmøy 12']` og fikk `['ålesund 1', 'bergen 2', …]`.
PostgreSQL i CI er initialisert med **en_US.utf8**, der å sorteres som a; den lokale
basen er **C.UTF-8**, der å kommer etter z. Testen prøvde altså maskinens kollasjon, ikke
regelen den heter etter (store og små bokstaver). Den bruker nå «voss 1» og krever hele
lista — bytealfabetet ville satt begge de små sist. Mutant: `Lower('navn')` → `'navn'` i
`oppdrag/views.py`, **drept**.

**Men funnet er ekte:** kjører Railway-basen også en_US, sorteres «Ålesund» som «Alesund»
i prod i dag — i enhetslista og i vaktlisteregistrene. Punktet om norsk sortering i
`TODO.md` er skrevet om med dette; ikke rettet her, fordi det er en atferdsendring og
kollasjonen på Railway bør sjekkes først.

**Følgefeilene:** 31 × `InterfaceError('connection already closed')` i ko, sammen med
«cannot pickle 'traceback' object … install tblib». Uten `tblib` kan ikke `--parallel`
sende en traceback til foreldreprosessen, så Django **kaster inne i arbeideren** ved første
feil (`RemoteTestResult.check_picklable`). Klassen avbrytes midt i transaksjonen,
`tearDownClass` kjøres aldri, og hver testklasse som kommer etter i samme arbeider arver en
død tilkobling. Én feil ble til 32 — og det så ut som en tilkoblingsfeil i ko.
`tblib==3.2.2` ligger nå i **`requirements-ci.txt`**, med hash, og *ikke* i
`requirements.txt` — den er det Railway installerer, og prod trenger ikke pakken.
`core/tests_ci.py` krever at workflowen installerer den.

**Railway venter nå på CI** på både staging og main (André satte det 26. sep.) — punktet i
`TODO.md` er slettet. Det betyr også at `668acff` ikke ble deployet til staging; denne
commiten er den første som kan.

## 2026-09-26 — CI: testene kjører mot PostgreSQL med node ved push til staging og main (D1)  `#core/drift`

**Hvorfor:** suiten kjørte bare lokalt, på **SQLite**, og rundt **160 JS-tester hoppet over
seg selv** når node manglet — en grønn suite kunne bety at halvparten av JS-reglene aldri
kjørte. A3 (runde 1) viste hva det koster: en databasefeil i en signalmottaker veltet
stemplingen **bare i PostgreSQL**, grønt lokalt og rødt i prod.

**`.github/workflows/tester.yml`** — ved push til **`staging` og `main`**, og PR-er mot dem
(André: «det holder med staging og main», arbeidet går alltid via staging):
PostgreSQL 16 som tjeneste, Python 3.13 som `runtime.txt`, node 22, avhengighetene med
hasher som på Railway, og stegene fra kommandoblokka i `CLAUDE.md`: `check`,
**`makemigrations --check`** (ny — fanger en modellendring uten migrasjon), `collectstatic`,
alt utenom `core` med `--parallel 4`, `core` serielt, og **`verifiser_migrasjoner`** —
«husk å kjøre migrasjonsprøvene» er ikke lenger noe man må huske.

**`KREV_NODE=1`: en JS-test uten node feiler, den hopper ikke over.**
`patients.js_test_utils.node_available()` kaster når variabelen er satt og node mangler.
Den er nå **det eneste stedet** node sjekkes: ni tester spurte `shutil.which('node')` selv,
og ville gått forbi kravet i stillhet. `NodeSjekkesEttStedTests` holder det. Lokalt er alt
som før. **Bevist med node skjult fra PATH:** uten kravet `OK (skipped=31)` — den grønne,
hule tilstanden — med kravet `RuntimeError`.

**Én test gikk ut fra SQLite** (`test_sqlite_har_ingen_signaler_og_ingen_feil`) og ble rød
første gang den møtte PostgreSQL, der databasekortets signaler finnes som de skal. Den
kjører nå bare på SQLite, og har fått en søster, **`EktePostgresTests`**, som kjører
spørringene mot `pg_stat_activity` **uten mock** — de var til nå bare prøvd med mock.

**`core/tests_ci.py`:** hver app med tester står i CI-kjøringen (samme feil som da
`myproject` manglet i `CLAUDE.md` til 14. sep.), og workflowen krever node og PostgreSQL.

**Kjørt ende til ende før push, på CI-ens versjoner:** et nytt venv på **Python 3.13**,
installert fra `requirements.txt` med hasher, PostgreSQL 16, `KREV_NODE=1`: `check` og
`makemigrations --check` rene, **3 821 + 834 tester grønne**, **3 av 3 migrasjonsprøver**,
211 sekunder. **Hele suiten hadde aldri kjørt mot PostgreSQL før**, og den eneste feilen var
testen over.

**Mutasjonstesting:** 4 mutanter — `myproject` ute av workflowen, `KREV_NODE` fjernet
(begge fanget av `tests_ci`), og node skjult med og uten kravet (over). `CLAUDE.md` har én
linje om CI; kommentaren om `myproject` ble kortet inn, siden `tests_ci` nå holder den.

**Ikke gjort, og André sin sak:** CI stopper ikke Railway. «Vent på grønne sjekker» for
`main` er en innstilling i Railway.

## 2026-09-26 — Django-admin er skrivebeskyttet for kontoene, og regelen om `role` dekker flere former (B4)  `#core/tilgang`

**André: «skrivebeskyttet».** Django-admin rutes bare under `DEBUG` — aldri i prod eller
på staging — men der kunne `accounts/admin.py` opprette og endre kontoer med egne skjemaer
som skrev **`role` og `is_superuser` rett inn**: en superbruker nummer to, og
degradering uten sperra «siste admin». Frysehandlingen der skrev ingen auditrad, og
innloggingsloggen kunne slettes rad for rad. En vei rundt sperrene er en vei rundt dem,
også lokalt.

**Nå:** `CustomUserAdmin` og `LoginEventAdmin` kan **se, ikke legge til, endre eller
slette** — heller ikke som superbruker. Passordhashen vises ikke. De to skjemaene,
frysehandlingene og sesjonshjelperen er slettet; endringer skjer i
`/portal-admin/brukere/`, der sperrene og auditen er. **`LoginEventAdmin` ble tatt med
uten at det sto i funnet** — sletting av rader i innloggingsloggen er samme sort vei rundt.

**Og regelen som skulle holde dette, dekket bare én form.**
`RollenSettesBareGjennomSkjemaeneTests` fant `x.role = …`, og slapp gjennom:
- et `ModelForm` med `role` eller `is_superuser` i `Meta.fields` — nøyaktig det
  Django-admin-skjemaene var; nå lov bare i `accounts/forms.py`, der sperrene sitter,
- `.update(role=…)`,
- `setattr(x, 'role', …)`,
- og `is_superuser` i det hele tatt.

Samme lærdom som N11: en regel som bare dekker halve syntaksen måler noe annet enn den
later som. Den utvidede regelen fant de to skjemaene med én gang.

**Tester:** `DjangoAdminErSkrivebeskyttetTests` (se ja, alt annet nei, med en superbruker).
`FreezeThawAdminActionTests` (seks tester av handlingen som er borte) er fjernet —
portalens frysing har sine egne, for sesjonene, auditraden og sperra mot å fryse seg selv.
**Mutasjonstesting:** 6 mutanter — hver av de tre tillatelsene slått på, og hver av de tre
nye formene lagt inn i en fil. Alle drept. `accounts` (308): grønt.

## 2026-09-26 — Vaktlista: nye og slettede lister, timetaket, registrene og grensene satte ingen spor (B3)  `#core/audit` `#vaktliste/roller`

Mannskapet, skiftene, ressursene, pausene og overnattingen ble auditlogget. Dette ble det
ikke:

| Hva | Hvorfor det betyr noe |
|---|---|
| **En vaktliste opprettet eller slettet** — bare `pre_save` var koblet | Å slette en liste river hele oppsettet |
| **`timetak`** — sto ikke i den håndskrevne feltlista | Vaktas budsjett |
| **`Korps`, `Kompetanse`, `Ressursgruppe`, `Ressursrolle`** | Å slette en gruppe tar rollene med seg (CASCADE) |
| **`Belastningsgrenser`** | Flytter varslene for *alle* lister |

**Begrunnelsen for hullet var foreldet.** Modulens docstring sa at registrene «endres fra
Django-admin, som har sin egen historikk». Registrene flyttet inn på `/vaktliste/`
30. aug. 2026, og Django-admin er ikke rutet i prod.

**Rettingen:**
- `Vaktliste` logger **alle kolonnene**, ikke en liste (`notat` uten verdi, som
  `Mannskap.notat`), pluss opprettelse og sletting. Ny kolonne logges som standard.
- De fem registrene får opprett/endre/slett gjennom hjelperne som fantes, med verdi — de er
  organisasjonsoppsett uten personopplysninger.
- **Stablede `@receiver`, ikke en løkke med `.connect()`**: `SignalerFyrerIkkeUnderLoaddataTests`
  leser dekoratørene med regex, og min første versjon med en løkke ville gått rett forbi
  den — samme grunn som tavla i `ko/signals.py` står stablet.

**`HverModellHarSporTests` går gjennom *alle* modellene i appen** og krever mottakere for
opprett, endre og slett — eller en plass i `UNNTATT` med grunn (`Utsending`, som logger seg
selv i `send_fil`). Neste modell kan ikke komme uten at noen tar stilling. Samme form som
`BrukerpekereStrippesEllerBegrunnesTests`.

**Tester** (`vaktliste/tests_audit_registre.py`): strukturtesten, og fem gjennom
endepunktene — korps opprettet/endret/slettet, grensene med verdi, timetaket, en vaktliste
opprettet og slettet, og notatet uten verdi. **Mutasjonstesting (tungt, audit):**
7 mutanter — vaktlistas opprett- og slettemottaker fjernet, notatet med verdi, korps uten
endringsmottaker, grensene uten sletting og uten endring, og opprett-vilkåret snudd. Alle
drept. `vaktliste` (1 316): grønt.

## 2026-09-26 — Sikkerhetssjekken dekket 75 av 186 ruter, og meldte grønt om tre som ikke fantes (B5)  `#core/sikkerhet`

`scripts/sikkerhetssjekk.py` prøver en kjørende portal utenfra: at ingen side eller API
svarer 200 uten innlogging, og at skriveendepunktene avviser POST uten CSRF. Lista over hva
den prøvde, var **skrevet for hånd «fra urlpatterns 13. sep. 2026»**, og hadde forfalt:

- **111 av 186 ruter manglet** — hele `/ko/` (42), `/backlog/` (9), `/api/endringer/`, og
  deler av oppdrag, vaktlista, portal-admin og pasientene.
- **Tre av stiene fantes ikke lenger** (`/portal-admin/backup/patients/`, `…/last-ned/1/`,
  `…/run/`). De ga 404 — og 404 telte som «stengt». Scriptet meldte altså grønt om ruter
  som ikke var der: en skanner som melder dekning den ikke har.

**Rettingen: lista utledes av `urlpatterns`.**
- `core/sikkerhetsruter.py` + `python manage.py sikkerhetsruter` skriver
  `scripts/sikkerhetsruter.json`: hver rute som en eksempelsti (`<int:…>` → `1`, andre → `x`).
- **Alt er stengt med mindre det står i `AAPNE` (8) eller `OMDIRIGERER` (10), med grunn.**
- Scriptet leser fila og prøver **hver stengt rute med både GET og POST** anonymt. Da trenger
  ingen å vite hvilke metoder et view tar: en rute som bare tar POST, svarer 405 på GET.
- De åpne kan svare **400** — en invitasjons- eller passordlenke med ugyldig token sier fra.

**`core/tests_sikkerhetsruter.py` holder det i live**, og gjør scriptets jobb inne i suiten:
fila er det kommandoen ville skrevet («Kjør: python manage.py sikkerhetsruter»),
klassifiseringen peker ikke på ruter som er borte, hver åpning er begrunnet, og hver stengt
rute gir aldri 200 eller 500 anonymt — GET og POST.

**Kjørt ende til ende** mot en lokal server: 168 ruter stengt for GET og POST, de ti gamle
adressene sender videre. **Mutasjonstesting:** 4 mutanter — en rute fjernet fra fila, en død
klassifisering, en tom begrunnelse, og `@modul_kreves` fjernet fra et view i backlog. Alle
drept.

**Og én feil i min egen første versjon:** eksempelstien for de gamle regex-adressene ble
`/admin/server-status/(?Pxx)` — `(?P<rest>…)` ble lest som en `<parameter>`. Rekkefølgen er
snudd.

## 2026-09-26 — Feilen fra e-postutsendingen: rå tekst til alle med `les`, og «kaster aldri» som kastet (B7)  `#vaktliste/offline`

**Tre ting ved samme feil:**

1. **Uvasket.** `send_fil` lagret `str(exc)` rått i `Utsending.feil`. En transport kan
   legge en URL med brukernavn og passord i feilmeldingen (`smtp://bruker:hemmelig@…`) —
   server-status vasker slik tekst, vaktlista gjorde det ikke.
2. **Til alle.** Feilteksten sto i `siste_utsending` i vaktlistas hovedsvar, som alle med
   `les` får. Nå ser den som ikke kan sende (under `skriv_full`) bare **«Utsendingen
   feilet.»** — at det gikk galt, ikke hva transporten svarte. `_vaktliste_til_dict(vl,
   user)` tar brukeren **påkrevd**, så et nytt endepunkt ikke kan glemme det.
3. **«Kaster aldri» kastet.** Docstringen lovet det, men `rader_for()` og brannlista ble
   bygget **utenfor `try`**. Feilet de, falt «Sett i drift» med 500 i stedet for å melde at
   fila ikke gikk. Byggingen står nå innenfor løftet, og raden får feilen.

**`core/vask.py` er ny og offentlig.** Vaskingen lå som den private `_scrub_secrets` i
`core/admin_status.py`, og `core/driftstatus.py` importerte det private navnet derfra. En
tredje leser skulle enten gjort det samme eller kopiert en sikkerhetsregex. Navnet
`_scrub_secrets` står igjen i `admin_status` som import, for de elleve kallstedene der;
omdøping og sammenslåing med `offsite._vask` er E6.

**Tester** (`FeilteksteTests`): legitimasjonen vaskes før lagring, leseren får den generelle
teksten og lederen den faktiske, og `send_fil` lager en rad i stedet for å kaste når fila ikke
lar seg bygge. **Mutasjonstesting:** 4 mutanter — uvasket tekst, feilen til alle, `vis_feil`
ignorert i serialiseringen, og byggingen utenfor løftet. Alle drept. `vaktliste` (1 309) og
`core` (820): grønt.

## 2026-09-26 — Brukeradministrasjonen: nytt passord, «Lås opp» og feltendringer satte ingen spor (B2)  `#core/audit`

**Jo mer inngripende, jo mindre spor** — mønsteret rot-`CLAUDE.md` kaller feil vei rundt,
funnet i `/portal-admin/brukere/<pk>/`. Frysing, tining, utlogging, rolle og modultilgang
skrev auditrad. Disse gjorde det ikke:

| Handling | Før | Nå |
|---|---|---|
| **«Nytt midlertidig passord»** — gir admin et passord som virker | ingenting | `password`, **aldri passordet** |
| **«Lås opp»** | ingenting | `locked_until`, fra → `None` |
| **Redigering** | bare `role` | **hvert felt som endret seg**: `email`, `fullt_navn`, `mfa_required`, `er_delt_konto`, `role` |
| **«Nullstill MFA»** | bare innloggingsloggen, der raden står på *brukeren*, ikke admin | også `mfa` i auditloggen, med admin |
| **«Send invitasjon»** — en lenke som setter passord | ingenting | `invitasjon`, med adressen |
| **Sletting av en backupfil** (`/portal-admin/backup/`) | ingenting, og ingen bekreftelse på serveren | auditrad (`DELETE`, filnavnet), `bekreft=ja` kreves, `backup:slett` 30/m |

**En endret e-post er veien til en passordlenke**, og det var nettopp den som kunne endres
sporløst. Redigeringen leser nå verdiene før `form.save()` og logger hvert felt i
`AdminUserEditForm.Meta.fields` som faktisk endret seg — et uendret felt gir ingen rad.
Backupslettingen var irreversibel og uten spor, mens gjenopprettingen, som er reversibel,
skriver en rad.

**Merk:** dette er manuell audit, gjennom den eksisterende `_log_user_admin_action`. Rot-
`CLAUDE.md` sier «legg aldri til manuell audit-kode — signalet tar seg av det», og det
stemmer ikke: `audit/signals.py` fyller bare ut `app_label`. Det rettes i F2.

**Tester:** `accounts/tests_brukeradmin_audit.py` (seks, også at passordet ikke står i
loggen og at en uendret redigering ikke gir rader) og to i `BackupAdminViewTests`.
**Mutasjonstesting (tungt, audit):** 8 mutanter — hver av de fire nye loggelinjene fjernet,
feltvilkåret snudd, redigeringsloggen fjernet, bekreftelsen fjernet og backupraden fjernet.
Alle drept. `accounts`+`audit` (338) og `core.tests_backup` (125): grønt.

## 2026-09-26 — ETag-en er hele svaret: en endring i oppdragsvinduet druknet i en 304 (A2)  `#oppdrag/sentralbord`

**Symptomet:** en operatør endret hastegrad, problemstilling, lokasjon eller notatet rett i
oppdragsvinduet (levert 23. sep.), og **de andre operatørene så det ikke** — lista svarte
**304**, fordi ETag-en var uendret. **Bilen** sto med gammel lokasjon og gammelt notat til
neste stempling, og en **bil nummer to** på et oppdrag som var i gang, synes heller ikke.

**Roten:** de tre listene som polles — sentralbordets oppdrag, bilens oppdrag og
enhetslista — hadde hver sin **håndskrevne liste over felt** som skulle inn i ETag-en.
CHANGELOG har rettet dem felt for felt i to uker («skal ikke drukne i en 304»):
meldings-ID-ene, «Rett tid», avbrytelsene, avventingen, hendelsen, lagene, de delte linjene,
lokasjonen i enhetslista. Neste felt noen la til i svaret, manglet igjen.

**Rettingen lukker feilklassen:** `views_common.etag_for_svar()` hasher **hele den
serialiserte payloaden** (`json.dumps(sort_keys=True)`), med historikktallet ved siden av.
Tre feltlister og deres kommentarer er borte. Prefikset er `v2:`, så ingen gammel ETag kan
treffe. `etag_for()` står igjen for verdimengdene, der den alt tar hele radene.

**Prisen, og vakta:** svaret får ikke bære noe regnet ut fra klokka — da ville hver polling
gitt ny ETag og aldri 304, og trafikken økt i stedet for å synke. Payloaden er lest felt for
felt: bare lagrede verdier. `test_uendret_gir_304` holder det for alle tre listene, også mot
PostgreSQL (rekkefølgen i usorterte spørringer kan variere der).

**Tester:** `oppdrag/tests_etag.py` — hastegrad, lokasjon og problemstilling i alle tre
listene, notatet hos sentralbordet og bilen, en bil til på et oppdrag i gang, og 304 når
ingenting er endret. **Mutasjonstesting:** 4 mutanter — bare id og status i hashen,
enhetslista uten data, historikktallet ute, og et klokkefelt i hashen (vakta over). Alle
drept. `oppdrag`+`ko`+`statistikk` (1 688): grønt; ETag-testene grønne på PostgreSQL.

**Én testfeil underveis, min:** «antall» på «Pustevansker» ga samme ETag — riktig, fordi
bare «Transport» bærer antall og ingenting ble endret. Byttet til problemstillingen.

## 2026-09-26 — «Flytt» i Venter tok med seg den gamle bilens varsling (A4)  `#oppdrag/enhetsskjerm`

`flytt_til_enhet()` pekte koblingsraden om når bilen sto i **Venter**, og lot alt annet
stå — docstringen sa «ingenting blir feil eier». Men varslingen var den gamle bilens:

- **Den nye bilen fikk ingen rad i bjella** — samme feil som A1, via en annen dør.
- **Den gamle bilens bjellerad ble aldri merket lest**, så den sto som et oppdrag hun
  ikke lenger hadde.
- **`varslet_at`** var den gamles: **lydvarselet i den nye bilen** målte ventetida fra da
  den *forrige* ble varslet, og kunne pipe med én gang.
- **`varslet_modus`** var den gamles: passiv-statistikken («oppdrag i passiv tid») talte
  feil bil.

**Rettingen:** raden pekes fortsatt om — `ta_av_enhet` nekter den siste bilen, og flytt av
den eneste er det vanligste — men den gamles bjellerad merkes lest, `varslet_at`,
`varslet_av` og `varslet_modus` settes for den nye, og den nye får bjella.

**Og en test som ikke sa noe:** A1-testen for modusen sammenlignet
`varslet_modus` med `gjeldende_modus(bilen)` på en enhet uten type som kan gå passiv vakt
— `'' == ''`. Begge testene har nå en slik type og krever `'passiv'` bokstavelig.

**Test:** `test_flytt_i_venter_varsler_den_nye_bilen`, gjennom flytt-endepunktet.
**Mutasjonstesting:** 5 mutanter, én per linje i rettingen (lest-merkingen, `varslet_at`,
`varslet_av`, `varslet_modus`, bjella). Alle drept. `oppdrag`+`ko`+`statistikk` (1 684):
grønt.

**Ikke gjort:** KO-loggen får ingen «varslet»-linje for den nye bilen ved flytt i Venter
(`enhet_varslet` fyrer bare på en ny rad). Det var slik før også, og er KOs sak.

## 2026-09-26 — En arkivert vaktliste i drift styrte fortsatt sentralbordet, KO og e-posten (A6)  `#vaktliste/offline`

**Arkiveringen satte bare `arkivert_at` og rørte ikke `status`.** En liste som ble
arkivert mens den **sto i drift**, var borte fra velgeren, men:

- vant fortsatt «lista i bruk» for **KO-tavla** (`vaktliste_i_bruk()`),
- vant fortsatt **besetningen** på sentralbordet (`besetning()`),
- ble **sendt på e-post med telefonnumre** på intervall (`fil.send_planlagte()`),
- og sto på server-status som «i drift».

Ingen på skjermen kunne se den, og derfor ingen stoppe den.

**Rettingen, to lag:**
1. **Sperre i hver retning, 409:** en liste i drift arkiveres ikke («Ta den ut av drift
   før den arkiveres»), og en arkivert liste settes ikke i drift. Ut av drift er en dør,
   ikke en sletting, og rører ingen stempler.
2. **`services.lister_i_drift()`** — `status=drift` **og** ikke arkivert — er én spørring
   for alle fire leserne. Den tar listene som alt er arkivert i drift i prod.

**Og en søsterfeil:** `besetning()` sorterte ikke, og falt på `Ressurs.Meta.ordering`
(navnet), mens `vaktliste_i_bruk()` tar den **sist satt i drift**. Med to lister i drift
kunne sentralbordet og KO vise hver sin liste for samme bil. Nå samme rekkefølge.

**Tester** (`ArkiveringAvVaktlisteTests`): begge sperrene, en arkivert liste i drift mot
alle fire leserne, og to lister i drift med navn valgt så basens rekkefølge peker på den
gamle. **Mutasjonstesting:** 8 mutanter — hver sperre fjernet, arkivfilteret fjernet fra
hjelperen, hver av de fire leserne tilbake til den gamle spørringen, og sorteringen i
`besetning()` fjernet. Alle drept. `vaktliste`+`ko`+`oppdrag` (2 954 tester): grønt.

`vaktliste/CLAUDE.md` traff taket med dagens tillegg (C1, C2, A6) og ble kortet inn på
stedet, ikke hevet.

## 2026-09-26 — Planleggerens kladd var synlig for `les_alle` og korps-føreren (C2)  `#vaktliste/tilgang`

**André: «skjul, bare de som har skriverett kan se den».** En ledig plass som ikke er delt
ut — ikke reservert et korps, ikke åpnet for alle — er lederens kladd. Tre kommentarer og
planleggeren lovet at den var «usynlig for korpsene til du deler dem ut», men
`synlige_vaktposter()` slapp alt gjennom for den som ser alle korps: **`les_alle` og
`skriv_handling` så halvferdig planlegging** som om det var vaktlista. Bare `er_planlagt()`
var prøvd, aldri synligheten. Regelen «korps-føreren ser alle, også lederens kladd» sto som
bevisst fra 12. sep.; den er nå snudd.

**Tolkningen:** «skriverett» er **`skriv_full` og oppover** — de som kan dele ut og fylle en
kladdeplass (`kan_skrive_alt`). `skriv_handling` («fører eget korps») ser den ikke.

**Kladd er en *ledig* plass.** `services.KLADD` (et `Q`) er ledig + ikke `alle_korps` +
verken plassen eller ressursen reservert — samme sammenslåing som `reservert_korps()`. En
**bemannet** plass på en ressurs uten reservasjon (KO) er ikke kladd og vises som før;
derfor holdt ikke `er_planlagt()` alene, den spør ikke om personen. Timeoversikten leser
samme filter, så `ledige_plasser` teller heller ikke kladden for `les_alle`.
Budsjettallene (`planlegging`) er uendret — et aggregat, vist i «Planlegger», som er
lederens.

**Tester:** `vaktliste/tests_kladden.py` — fem slags plasser mot seks kontotyper gjennom
hovedsvaret, og tellingen i timeoversikten. `TildeltAlleKorpsTests` dokumenterte den gamle
regelen og er snudd med henvisning. **Mutasjonstesting (tungt, tilgang):** 6 mutanter —
skriveretten mister kladden, filteret fjernet, og hvert av de fire leddene i `KLADD` fjernet
for seg. Alle drept. `vaktliste`+`ko` (2 204 tester): grønt.

## 2026-09-26 — Overnattingsfanen viste andre korps' skift til en ren `les` (C1)  `#vaktliste/tilgang`

**Funnet i kodegjennomgangen 25. sep., gikk til prod med `7c21318` samme kveld.** En ren
`les`-bruker fikk skiftdetaljene til alle som overnattet — «Ola, Karmøy: Ambulanse 2,
22:00–06:00» — mens hovedsvaret i vaktlista filtrerer de samme skiftene bort for henne.
`paa_vakt()` gikk utenom `synlige_vaktposter`.

**André valgte «a»:** alle ser *at* en person er på vakt om natta — opptellingen trenger
det, «4 i rommet, 1 på vakt» — men **hvilken ressurs og når følger telefonen** (`vis_telefon`:
eget korps, eller den som ser alle). Én regel for hvem som ser et annet korps, ikke to.

- Serveren sender `er_paa_vakt` til alle, og `paa_vakt` (skiftene) bare der telefonen vises.
- Klienten teller og merker på `er_paa_vakt`, ikke på lengden av `paa_vakt` — ellers ville
  brannlista sagt at Ola skal være inne mens han kjører ambulansen.
- Fila på e-post er uendret: den går til de faste mottakerne admin har satt.
- **Personvernprotokollen v1.13**, A.6: tilgangsavsnittet for overnatting nevner nå
  skiftdetaljene. `vaktliste/CLAUDE.md` likeså.

**Tester:** tre i `LesingenTests` gjennom hovedsvaret (ingen detalj om et annet korps i
svaret, detaljene for eget korps, den som ser alle ser alt) og én i JS (tellingen og merket
uten detaljer). **Mutasjonstesting:** 4 mutanter — detaljene til alle, `er_paa_vakt` alltid
falsk, tellingen på detaljene og merket på detaljene. Alle drept.

## 2026-09-26 — Bjella ringte ikke for den første bilen på et oppdrag (A1)  `#oppdrag/enhetsskjerm`

**Kravet fra 15. sep.** — «en bruker som er koblet til en enhet … som får et oppdrag skal få
varsel på varselbjella» — **holdt ikke i det vanligste tilfellet: ett oppdrag, én bil.**
POST `/oppdrag/api/oppdrag/` opprettet oppdraget med `enhet=enheter[0]` og kalte
`varsle_enhet` bare for `enheter[1:]`. Den første enhetens koblingsrad ble laget av **broen
i `Oppdrag.save()`**, som går utenom `varsle_bjelle`. Enhet nummer to og tre fikk bjella;
den første, som oftest er den eneste, fikk ingenting.

**Hvorfor ingen test så det:** alle i `VarselbjellaTests` kalte `varsle_enhet` direkte —
løgn nr. 3 i mutasjonsavsnittet, i praksis. Regelen var prøvd; inngangen var det ikke.

**Rettingen:** oppdraget opprettes med `enhet=None`, og **alle** enhetene varsles gjennom
`varsle_enhet`. Den gjør allerede den første til primær, fryser `varslet_modus` og
nullstiller «trenger ressurs» — det broen gjorde, pluss bjella. `rekkefolge` blir 1, 2, …
i stedet for 0, 1, …; `primaer` leser bare rekkefølgen innbyrdes. **Ingen produksjonskode når
broen lenger**, bare testene — første steg mot deploy 2. Står i `oppdrag/CLAUDE.md`.

**Tester:** to nye gjennom POST — bjella for én bil, og at den første fortsatt er primær med
modusen frosset (passiv vakt) og bare én bjellerad. Røde uten rettingen (`0 != 1`).
**Mutasjonstesting:** 2 mutanter — den gamle formen (`enheter[1:]` med `enhet=enheter[0]`),
og `enheter[1:]` med `enhet=None` (den første bilen mistes helt). Begge drept.
`oppdrag`+`ko`+`statistikk` (1 683) grønt på SQLite, `oppdrag`+`ko` (1 648) grønt på
PostgreSQL.

## 2026-09-26 — «Aktiv nå» var feil for hver synlig fane: bjella og pasientsiden sendte ikke `X-Portal-Inaktiv` (A8)  `#core/drift`

Tilstedeværelsen fra 16. sep. hviler på at **pollingen har headeren** og at en forespørsel
uten den er en handling. Premisset holdt ikke:

- **Bjella** (`notifications.js`, lastet av `base_portal` på alle sider) pollet hvert 30.
  sekund med sin egen `fetch`.
- **Pasientsidens auto-refresh** — fem rå `fetch` i `patients-app.js` og
  `patients-table.js`.
- **Server-status** pollet hvert 10. sekund, også med rå `fetch`.

En glemt, synlig fane sto derfor som **«aktiv nå»** — nøyaktig fana funksjonen skulle finne,
og «N aktive nå» på `/portal-admin/server-status/` ble for høyt. Testen viste det rett ut:
en poll uten header flyttet «siste interaksjon» en time fram, til nå.

**Rettingen:**
- Pasientsiden bruker `apiFetch` (den laster `portal-utils.js` fra før).
- Bjella sender `sekunderSidenInteraksjon()` der `portal-utils.js` finnes, og **`ukjent`**
  der den ikke gjør det — admin-sidene laster den ikke. Server-status sender `ukjent`.
- `les_inaktiv()` gir `None` for `ukjent`, og middlewaren **skriver ingenting**: en poll som
  ikke vet, skal verken si «aktiv» eller «inaktiv». Ingen ny makt til klienten — et stort
  tall kunne alt si «inaktiv». Raden står i tabellen i rot-`CLAUDE.md`.

**Tester** (`core/tests_brukeraktivitet.py`): `ukjent` skriver ingenting; hele
`notifications.js` kjøres i node med stubbet DOM og `fetch`, med og uten målingen;
og **`IngenRaaFetchTests`** — ingen rå `fetch(` i `static/js/` utenom tre navngitte unntak
med begrunnelse, kommentarer strippet først.
**Mutasjonstesting:** 4 mutanter drept — bjella uten hode, alltid `ukjent`, `ukjent` lest
som 0, og én rå `fetch` tilbake i pasientsiden. **Ett ekvivalent:** å fjerne
`if sekunder is None: return` i middlewaren gir `TypeError`, som `__call__` svelger — samme
utfall. Linja står for lesbarheten. `core` (819) og `patients` (371): grønt.

**Kjent hull:** skriptet i `admin_status.html` er inline, og `IngenRaaFetchTests` leser bare
`static/js/`. Det lukkes når skriptet flyttes ut (G1 i planen).

## 2026-09-26 — Pasientregistreringen: en ukjent førstehjelper forsvant stille (B8)  `#core/drift`

POST og PUT på `/pasienter/api/patients/` slo opp førstehjelper og helsepersonell og svelget
`DoesNotExist` med `pass`. Svaret var **201/200**, pasienten sto **uten behandler**, og
**tildelingsvarselet ble aldri sendt**. Operatøren så «lagret» og hadde ingen grunn til å
sjekke. Det skjer uten at noen gjør noe galt: et nedtrekk tegnet før noen fjernet personen
fra registeret, sender en ID som var gyldig da.

**Rettingen:** `_hent_person()` i `patients/views_patients.py` gir personen, `None` for tom
verdi, eller «Ukjent førstehjelper. Last siden på nytt og velg igjen.» med 400. Oppslaget
sto skrevet fire ganger; nå står det én gang. I PUT slås personene opp **før** noe settes
på objektet, så en avvist endring ikke etterlater et halvt endret objekt.

**Tester:** `patients/tests_ukjent_behandler.py` — POST og PUT for begge felt, at en avvist
PUT ikke endrer plasseringen, at `''` fortsatt fjerner personen, og at en avvist innsending
**ikke brenner idempotensnøkkelen** (valideringen står fortsatt foran `reserver()`).
**Mutasjonstesting:** 3 mutanter — feilen svelget igjen, sjekken fjernet i POST, og i PUT.
Alle drept. `patients` (371 tester): grønt.

## 2026-09-26 — Datofiltrene i auditlogg og innloggingslogg ga 500 på en ugyldig dato (B6)  `#core/drift`

`?date_from=2026-13-45` — eller «i går», eller 30. februar — gikk rett inn i
`created_at__date__gte`, og Django kastet `ValidationError`: **500** på
`/portal-admin/auditlog/`, CSV-eksporten og `/portal-admin/innloggingslogg/` for en
skrivefeil i adresselinja. Filterlogikken sto dessuten skrevet to ganger.

**Rettingen:** `core.validators.les_iso_dato()` leser verdien til en `date` eller `None`.
Et filter som ikke lar seg lese, ignoreres og vises tomt i skjemaet, så det synes at det
ikke ble brukt — framfor en feilside, eller et filter som stille sto på en annen dag.

**Tester:** `core/tests_datofilter.py` — fire ugyldige verdier × to felt × tre sider uten
500, og at et gyldig filter fortsatt filtrerer (ellers ville en sperre som ignorerte alt
vært grønn). **Mutasjonstesting:** 3 mutanter drept — funksjonen som alltid gir `None`, og
den rå verdien tilbake i hvert av de to viewene. **To mutanter var no-ops og telles ikke**:
den første versjonen byttet bare verdien i `filter()`, men `if fra_dato:` stoppet den
ugyldige verdien før den nådde fram — løgn nr. 2 i mutasjonsavsnittet. Byttet på nytt så
mutanten går utenom hele sperra. `core` (814) og `accounts`+`audit` (332): grønt.

## 2026-09-26 — Vaktlista: en ukjent rolle, korps eller enhet ga 500 eller feil melding (A7)  `#vaktliste/planlegging`

**Tre feil med samme rot.** Fremmednøklene er utsatt til commit, så en `rolle_id`,
`korps_id` eller `enhet_id` som ikke finnes, ble først en `IntegrityError` da
`transaction.atomic()` lukket seg — og der sto en `except` skrevet for unik-skranken:

- **Ny ledig plass (`vaktposter_view`) → 500.** Meldingen leste `mannskap.navn`, og på en
  ledig plass er `mannskap` `None`.
- **Ny eller endret ressurs → «finnes allerede på denne vaktlista»** om en enhet eller et
  korps som ikke fantes. Endringen ga i tillegg 500 når svaret skulle tegnes.
- **Endret plass → «Personen står allerede …»** om en ukjent rolle, og 500 samme vei.

Det skjer uten at noen gjør noe galt: et nedtrekk tegnet før noen slettet rollen, sender en
ID som var gyldig da.

**Rettingen:** `_ukjent_peker()` i `vaktliste/views.py` slår opp pekerne før skrivingen og
svarer «Ukjent rolle.» / «Ukjent korps.» / «Ukjent enhet.» med 400. Målmodellen leses av
feltet, så vaktlista slipper å importere `oppdrag` for å sjekke en enhet. `except`-grenen
på den ledige plassen tåler `None` som et ekstra nett.

**Tester:** `vaktliste/tests_ukjente_pekere.py`, seks stykker gjennom endepunktene, pluss at
`''` («Ingen valgt») fortsatt er lov. **Mutasjonstesting:** 4 mutanter — sperra fjernet på
hvert kallsted. Alle drept. `vaktliste` (1 294 tester): grønt.

**Ikke gjort her:** at rollen hører til ressursens gruppe valideres fortsatt ikke. Det er en
annen regel, og står i planen.

## 2026-09-26 — Å endre en verdi i oppdraget kunne skrive over en stempling: `update_fields` (A5)  `#oppdrag/sentralbord`

**Kappløpet:** PUT i `oppdrag_detalj_view` (verdiene rett i vinduet, 23. sep.) leser
oppdraget, validerer, og lagret med `oppdrag.save()` — **alle** felt. Stemplet bilen i
mellomtiden, ble den gamle statusen skrevet tilbake, sammen med `trenger_ressurs`,
`historikk_fra` og `enhet`. Stemplingen sto i statusmeldingene, men oppdraget viste
«Venter».

**Rettingen:** PUT samler feltene den faktisk endrer og lagrer med
`update_fields=endret + ['updated_at']`. Svaret leses på nytt fra basen, så det viser
stemplingen og ikke det gamle objektet.

**Test:** `test_en_stempling_mens_verdien_endres_overlever` legger en ekte stempling inn
akkurat mellom lesingen og lagringen, gjennom endepunktet. Rød uten rettingen
(`'venter' != 'rykker_ut'`).

**Mutasjonstesting:** 6 mutanter — `update_fields` fjernet, og hvert av de fem feltene
tatt ut av lista ett om gangen. **To overlevde først**: fritekst og lokasjon.
Testene deres sjekket bare tidslinjen, og tidslinjen leser objektet i minnet — så et felt
som aldri ble lagret, så ut som lagret. Begge testene krever nå verdien fra basen. Alle 6
drept. `oppdrag` (744 tester): grønt.

## 2026-09-26 — Innloggingen avslørte om et brukernavn fantes: «låst i 15 minutter» fjernet (B1)  `#core/sikkerhet`

**Brukernavn-enumerering.** Femte feilede forsøk på en konto som finnes, ga meldingen
**«For mange feil forsøk. Kontoen er låst i 15 minutter.»** Et brukernavn som ikke finnes
kan ikke låses, og fikk alltid «Feil brukernavn eller passord». Fem gjett avslørte dermed om
et navn fantes — mens kommentaren M14 rett over påsto at «alle andre får samme svar som ved
feil passord». `KontolaasRoeperIkkeTests` sammenlignet bare en konto som *alt* var låst, og
så det aldri.

**Rettingen:** samme melding hver gang. Låsingen virker som før; eieren får vite at kontoen
er låst ved neste forsøk med riktig passord («midlertidig låst»), som er M14-regelen.
Meldingen i MFA-steget står: der har brukeren alt bevist passordet.

**Test:** `test_forsoket_som_laaser_kontoen_sier_ikke_fra` sender fem feil mot et navn som
finnes og et som ikke gjør det, og krever lik melding — pluss at kontoen faktisk er låst.
**Mutasjonstesting:** 2 mutanter — den gamle meldingen tilbake, og kallet som teller og
låser fjernet. Begge drept. `accounts` (307 tester): grønt.

## 2026-09-26 — KO-loggen kunne velte en stempling i PostgreSQL: savepoint i `_trygt` (A3)  `#ko/loggen`

**Hva som var galt:** `ko/signals.py` løfter bilens stemplinger inn i KO-loggen, og hver
mottaker er pakket i `_trygt`, som lover at «en KO-logg som ikke lar seg skrive skal ikke ta
ned en stempling i en bil». Løftet holdt bare for Python-feil. Mottakerne kjører inne i
stemplingens `transaction.atomic()`, og **i PostgreSQL gjør en databasefeil hele
transaksjonen ubrukelig**: `_trygt` fanget unntaket, stemplingen fortsatte, og neste
spørring ble avvist med **«current transaction is aborted, commands ignored until end of
transaction block»**. Bilen fikk 500 og stemplingen ble rullet tilbake. SQLite fortsetter
transaksjonen, så suiten var grønn — samme felle som 30. aug. 2026.

**Rettingen:** `with transaction.atomic():` rundt kallet i `_trygt`. Inne i en åpen
transaksjon er det et **savepoint**, så bare KO-linja rulles tilbake. `varsle_bjelle` gjorde
det allerede slik.

**Bevist mot ekte PostgreSQL 16** i containeren, ikke bare resonnert:
`test_en_databasefeil_i_loftet_stopper_ikke_stemplingen` fremkaller en databasefeil i
mottakeren og stempler gjennom `/oppdrag/api/oppdrag/<pk>/status/rykker_ut/`. Uten
rettingen: **500** med `InFailedSqlTransaction` på PostgreSQL, grønn på SQLite. Med
rettingen: grønn på begge. Den eksisterende testen kastet `RuntimeError`, som er den
ufarlige feilen, og kunne aldri se dette. **Kjør den mot PostgreSQL** (`DATABASE_URL=postgres://…`)
— på SQLite beviser den ingenting.

**Mutasjonstesting:** 1 mutant — savepointet fjernet — drept på PostgreSQL, overlever på
SQLite (dokumentert i testen). Hele `ko` og `oppdrag` (1 645 tester) kjørt mot PostgreSQL:
grønt.

## 2026-09-25 — Kodegjennomgang av hele appen: pseudokode og teknisk gjeld, med plan  `#core/dokumentasjon`

**André:** «kjør en runde hvor du ser etter pseudokode og teknisk gjeld i hele appen. Ikke
endre noe», og så «lag en plan for håndtering så vi kan ta det senere». Ingen kode er
endret. Planen står i `docs/PLAN_TEKNISK_GJELD_2026-09-25.md`, med puljene A–G i `TODO.md`.

**Grunnlaget:** revisjonen ble gjort på staging `7c21318`. **Alt unntatt ett funn finnes også
i prod** (`main` `636e1f2`). Unntaket er overnattingsfanen, som ennå bare står på staging.

**Pseudokode fantes nesten ikke.** Det nærmeste er flater som later som de gjør noe:
bryteren `backup_enabled` uten virkning, filteret `is_active` som ingen setter, feltet
`avmeldt_at` uten skrivevei, og `manage.py lokasjon` som fortsatt mener at modulen «ikke har
noen URL ennå».

**Åtte feil i drift, samlet i pulje A.** Stikkordene er med så de kan søkes opp:

- **«Bjella ringer ikke» for den første bilen på et oppdrag.** Broen i `Oppdrag.save()`
  går utenom `varsle_enhet`.
- **ETag-ene mangler felt.** En redigering inne i oppdraget gir **304** hos de andre
  operatørene.
- **`_trygt` fanger unntak uten savepoint.** Feilen finnes **bare i PostgreSQL**.
- **«Flytt» i Venter** tar med seg den gamle bilens `varslet_modus`.
- **PUT uten `update_fields`.**
- **En arkivert vaktliste i drift** styrer fortsatt sentralbordet og KO, og sendes fortsatt
  på e-post.
- **500 på ledig plass** i `vaktposter_view`.
- **Tilstedeværelsen:** bjellas polling sender ikke `X-Portal-Inaktiv`, så en glemt, synlig
  fane står som **«aktiv nå»**.

**Og i spor og tilgang:**

- **Låsemeldingen avslører at brukernavnet finnes** (brukernavn-enumerering).
- **`reset_password` og `unlock` skriver ingen audit.**
- **Planleggerens kladd er synlig** for `les_alle`/`skriv_handling`.

**Tre rotårsaker går igjen:**

1. Lister som vedlikeholdes for hånd: ETag-feltene, `STENGT_GET`, auditens feltlister.
2. Tester som kaller hjelperen i stedet for inngangen. Bjella over er eksempelet.
3. SQLite og ingen CI. Rundt 160 JS-tester hopper stille over når node mangler.

**Kontroll av funnene:** fem lesere tok hvert sitt område. Alle funn merket «Høy» er
kontrollert mot koden en gang til. «Vurder GitHub Actions» er slått inn i pulje D1.

## 2026-09-25 — Overnatting: plasseringene slettes 30 dager etter natta, og personvernprotokollen  `#vaktliste` `#personvern`

André valgte «A» av tre: hvem som sov hvor har ingen verdi etter vakta, og fila sa
allerede «slett etter vakta». **Plasseringene slettes 30 dager etter natta** av
`purge_old_logs`, gjennom `core/opprydding.py` (`vaktliste/opprydding.py`). Rommene står,
så de kan kopieres til neste år. Fristen regnes **per natt i norsk dato**, ikke fra vaktas
slutt — da virker den også når planlagt slutt mangler.

**Fella som ble unngått:** slettesignalet auditlogger hver plassering med navn, rom og
natt. En vanlig `delete()` i ryddingen ville skrevet nøyaktig det som skulle bort inn i
revisjonsloggen, som har 730 dagers lagringstid. `slett_utlopte()` setter et flagg
(`ContextVar`) som får signalet til å tie; antallet står i cron-jobbens kjøringslogg, uten
navn. En vanlig fjerning av en person logges som før.

**Personvernprotokollen, v1.12:** A.6 har fått en underseksjon for overnatting (felter,
kategori, tilgang, og at revisjonsloggen og backupen bevisst lever lenger), A.9 en rad for
lagringstiden, og raden om fila på e-post nevner brannlista. **Dette skulle vært med i
leveransen av overnattingen** — det ble oppdaget ved gjennomgangen etterpå. Versjonshodet
sto på 1.10 mens endringsloggen var på 1.11; rettet.

**Tester:** seks nye i `LagringstidenTests`, gjennom kommandoen og ikke hjelperen —
grensen på 30/31 dager, tørrkjøring, at ryddingen ikke skriver i auditloggen, at flagget
slippes etterpå, og at fristen regnes i norsk dato (23:30 UTC er neste dag i Norge).
**Mutasjonstesting:** 9 mutanter — grensen, fristen, datoen, flagget satt og sluppet,
slettingen, signalets sjekk, registreringen i `apps.ready()` og tørrkjøringen. Alle drept.
Datomutanten ville overlevd uten testen med et tidspunkt etter midnatt: testene går på
dagtid, der UTC og norsk dato er like.

## 2026-09-25 — Staging-grenen heter `staging`, ikke `rollemodell`  `#drift` `#deploy`

André ga grenen nytt navn i GitHub og byttet grenen staging-tjenesten deployer fra i
Railway. **«rollemodell» betydde to ting**: staging-grenen og tilgangsmodellen
(`docs/BESLUTNING_ROLLEMODELLEN.md`), og en setning som «ligger på rollemodell» måtte leses
i sammenheng for å vite hvilken. Ingen kode, test eller CI avhenger av grennavnet — sjekket
før omdøpingen.

Oppdatert: arbeidsflyten i `CLAUDE.md`, `docs/DEPLOY_GUIDE.md` §9 (tabell og
push-kommando), testsjekklistene for KO og vaktlista, og `docs/RUNBOOK_VAKT.md`.
**Historiske dokumenter står urørt** — CHANGELOG, `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`
og `docs/PLAN_FLYTTING_TIL_CORE.md` beskriver hva som skjedde da grenen het `rollemodell`,
og en omskriving ville gjort dem feil. `CLAUDE.md` og deploy-guiden sier derfor at grenen
het det før.

Lokale kloner: `git branch -m rollemodell staging`, `git fetch origin`,
`git branch -u origin/staging staging`, `git remote set-head origin -a`.

## 2026-09-25 — Overnatting i vaktlista: hvem sover hvor, og brannlista på papir  `#vaktliste` `#brannsikkerhet`

André: «Vi skal jobbe med /vaktliste. Jeg vil ha en overnatting-del hvor vi registrerer
hvilke mannskap som skal sove der og hvor. Det må gå an å sette dette opp samt romnavn.
Dens funksjon er for brannsikkerhet.» Skissert og planlagt før koden; svarene samme dag:
**per natt**, **bare mannskap fra registeret**, tilgangen som foreslått, **ingen
mobilopptelling nå** («vi printer ut», står som idé i TODO), og brannrutinen skal lederen
kunne skrive selv.

**Ny fane «Overnatting»** på `/vaktliste/` (bakre bolk, foran «Timeoversikt»):
- **Rom** med navn, plassering (bygg/etasje), kapasitet og merknad (nødutgang). Lederens
  (`skriv_leder`). Kapasiteten **varsler** («Fullt», gult «Over kapasiteten»), sperrer ikke.
- **Plassering per natt.** «Natt til lørdag 03.10» — lagret som kvelden (fredag), samme
  regel som `_dagnokkel()`. Nettene er de der 22:00–06:00 overlapper vaktas spenn; en
  dagvakt har ingen, og fanen sier at vaktas lengde må settes.
- **Én person, ett sted, per natt** — unik skranke `(mannskap, natt)`, også på tvers av
  vaktlister. Sover personen et annet sted, svarer serveren **409** og vinduet tilbyr
  «Flytt hit»; en seng på en annen vakt flyttes aldri herfra. `plasser()` er én
  transaksjon — en kollisjon midt i skrivingen etterlater ingenting.
- **«På vakt i natt»**: den som står på et skift på lista som overlapper natta, merkes, og
  telleren sier **overnatter · på vakt · skal være inne**. Avmeldte skift teller ikke.
- **Brannrutinen** (`Vaktliste.brannrutine`) står øverst i fanen og på lista — samleplass og
  hva som gjøres ved alarm. Lederens, satt i vaktlistas PUT.
- **Brannlista på papir**: «Brannliste» skriver ut natta som vises, «Alle netter» alle — én
  side per natt, avkryssingsboks per person, rutinen i ramme (eller en linje å skrive
  samleplassen på). Den står også i **fila på e-post**, og `fil.signatur()` tar den med
  når den finnes, så en ny plassering gir ny utsending.
- **Hint** nederst: «Har vakt dette døgnet, men ingen overnatting registrert» — sammenslått,
  for mange sover hjemme.

**Tilgang:** rom og rutine `kan_lede`; å plassere og ta ut følger personens korps
(`kan_fore_korps` — alle for `skriv_full`, eget korps for korps-føreren); **alle med
`les` ser alle rom og navn**, uten korpsfilter, fordi den som teller opp trenger hele lista.
**Telefonen følger korpsfilteret** som ellers. Knappene gates i klienten på det samme.

**Offline:** dataene står i vaktlistas hovedsvar (`overnatting.data_for`), så de følger
med i service workerens kopi uten nytt endepunkt.

**Teknisk:** `vaktliste/overnatting.py` (regler), modellene `Overnattingsrom` og
`Overnatting` + `Vaktliste.brannrutine` (migrasjon `0022`, bare skjema), fire endepunkter
(`api/vaktlister/<pk>/overnattingsrom/`, `api/overnattingsrom/<pk>/`,
`…/plasser/`, `api/overnattinger/<pk>/`), auditlogging (`vaktliste_overnattingsrom`,
`vaktliste_overnatting`, `brannrutine` med verdi), ny fil `static/js/vaktliste-overnatting.js`
(sju vaktlistefiler, 33 i `static/js/`), tre vinduer i malen. Ruter: 185 (vaktlista 36).
Backupen tar de nye tabellene av seg selv (`apps = ['vaktliste']`).

**Dokumentasjon:** reglene står i docstringene i `vaktliste/overnatting.py`; seksjonen i
`vaktliste/CLAUDE.md` har bare de fire man må kjenne før man rører annen kode, og flaten
står i `templates/vaktliste/CLAUDE.md`. **Taket på `vaktliste/CLAUDE.md` er hevet 800 tegn**
(`FOR_STORE_I_DAG`, til 44 750): seksjonen ble kortet fra 3 761 tegn, og de siste 691 ville
ellers vært hentet ved å stryke begrunnelser andre steder. Krympingen står i TODO.

**Tester:** `vaktliste/tests_overnatting.py` (47 — nettene, rommene, plasseringen,
«på vakt», tilgangen per nivå, lesingen og telefonen, fila, signaturen, intervallsendingen
gjennom kallstedet, audit) og `vaktliste/tests_overnatting_js.py` (18 — standardnatta,
kapasiteten, hvem som får plassere, escaping, knappene per nivå, brannlista, og
`tegnPanel()` som kallsted). Fanerekka i `FanerekkaHarToBolkerTests` har fått
«Overnatting»; harnessene som tegner fanene har fått de nye hjelperne.

**Mutasjonstesting:** 78 mutanter — 46 i tjenestelaget, viewene, fila og signalene
(tungt/middels), 32 i JS-reglene, byggernes gater og kallstedene (middels/lett). **Fire
overlevde første runde, alle tettet:** grensen i `paa_vakt()` (med to netter henter
spørringen hele spennet, og da er løkka alene det som holder et dagskift 06–14 utenfor
natta før), nattfilteret i fila (testen hadde bare én natt), telefonen i fila (assertionen
traff Kari i vaktlistedelen av fila, ikke i brannlista — nå leses bare bolken), og et tomt
rom på papiret. **Én var ekvivalent:** tidlig retur i `brannliste()` uten plasseringer — løkka
gir tom liste uansett. To mutanter traff ikke første gang (feil mønster) og ble kjørt på
nytt. Før runden: `transaction.atomic()` i `plasser()` var udekket, fordi konflikten
oppdages før noe skrives — ny test simulerer en kollisjon midt i skrivingen.

**Skjermbilder** tatt i Chromium mot en lokal base: fanen, konfliktvinduet, papirutgaven
og mobil (390 px). Papirutgaven fikk fast kolonnebredde etter første bilde — «Telefon»
flyttet seg fra rom til rom.

## 2026-09-25 — Databasekortet på server-status: henger, eldste transaksjon, låskø og deadlocks  `#drift` `#database`

André: «Ja gjør det» og «la oss gjøre det du skisserte» (Artifact «Databasekortet»), med
svarene: rødt løfter beredskapstrinnet, deadlocks med nå, grensene som foreslått.

**Før:** kortet viste svartid og tilkoblinger. Begge kunne stå grønne mens én transaksjon
holdt en lås og alt sto i kø bak den — situasjonen P95 først ser når skaden er skjedd.
**Nå, fire rader til (PostgreSQL):**
- **Arbeider · ledige · henger** — «henger» er *idle in transaction* over 5 s. Gul 1–2, rød ≥ 3
  eller én over 30 s.
- **Eldste transaksjon** — gul 5–30 s, rød over 30 s.
- **Venter på lås** — gul 1–2, rød ≥ 3.
- **Deadlocks siden `pg_stat_reset()`** — gul fra én: to operasjoner låste hverandre, en kodefeil.

Regelen står i `db_signaler()` (`core/admin_status.py`), og kortet fargelegger bare. **Rødt kort
løfter beredskapstrinnet til minst Oransje** (`beredskap_med_databasen()`), med «· databasen»
i merket og et eget tiltak: flere workers hjelper ikke på en lås — også når P95 alene ga
rødt. Dashbordets egen tilkobling og Postgres' bakgrunnsprosesser telles ikke. Aktiviteten
har sin egen `try`: feiler spørringen, står svartid og tilkoblinger fortsatt.

**Prøvd mot en ekte PostgreSQL 16** (lokal engangsbase): en transaksjon som holdt en lås og
en forespørsel bak den ga «1 · 1 · 1», eldste 6,5 s, 1 venter — gult. Etter 31 s: rødt, og
banneret «Oransje · databasen». En fremprovosert deadlock ga `deadlocks = 1`. Så dashbordet
selv mot samme base i nettleseren: kortet og banneret sa det samme.

**Funnet underveis — statusfargene i radene har aldri vist:** `.status-row .val` har høyere
spesifisitet enn `.status-ok`/`.status-warn`/`.status-crit`, så **hver farget verdi i en rad
sto hvit** — svartid, 5xx, offsite-status og tilkoblinger. Ingenting feilet; fargen bare
uteble. Rettet; målt med `getComputedStyle` etterpå.

**Mutasjonstesting: 15 mutanter, 13 drept.** To overlevde, begge hull i testene: mocken ga
samme objekt til kortet og banneret, så to databasekall var usynlige; og PostgreSQL-grenen i
`_get_db_health` kjørte aldri. Tettet i `core/tests_databasekortet.py`; begge drept.

Runbook §2 (løftet av trinnet) og §8 (radene, grensene og hva man gjør når svartiden er grønn
og kortet rødt). `docs/TEKNISK_DOKUMENTASJON.md`: panelraden oppdatert.

## 2026-09-25 — Runbook §8a: helsesjekk av databasen, og første avlesning av indeksene  `#drift` `#database`

André: «Okei kan du skrive det viktigste i runbooken for meg?» og «helt ærlig jeg vet ikke om
dette er fra prod elelr staging».

**Første avlesning** (**staging** — bekreftet etterpå med `railway status`; tellerne aldri nullstilt, `stats_reset` tom): **320
indekser**, alle fremmednøkler og unike felt dekket, og sammensatte indekser på de varme
stiene (`ko_logg_vakt_id_idx`, `oppdrag_vakt_status_idx`, `core_notif_user_read_idx`).
Største tabell `ko_logglinje` med 377 rader, så Postgres leser alt rad for rad med vilje.
**Ingen indeks mangler.** Den mest spurte tabellen er `oppdrag_statusmelding` (183 000
`seq_scan`), og den er den første som vil trenge indeksene sine på en stor vakt.
`patients_appsetting` leses ved nesten hver forespørsel (166 000), gratis med 13 rader.
Ubrukte indekser (`idx_scan = 0`) er 16–104 kB, og står. `pg_stat_statements` er av.

**`docs/RUNBOOK_VAKT.md` §8a**:
1. Hvilken base: `railway status` — staging og prod heter begge `railway`, så psql-prompten
   sier ingenting.
2. Før vakt: `SELECT pg_stat_reset();`, også som steg 6 i vakt-modus (§1c).
3. Helsa: størrelse, døde rader og autovacuum, cache-treff, med grenser for friskt.
4. Etter vakt: `seq_scan`/`idx_scan` per tabell og ubrukte indekser, og hvordan de leses.

**Prod, samme dag:** 14 MB, cache-treff 100 %, under 40 døde rader per tabell, ingen
manglende indeks. Basen har ikke hatt en ekte vakt ennå; det eneste som går, er
backupklokka (`core_backupplan`, 68 000 oppslag). `n_live_tup` er et anslag, og sto på 0
for `accounts_customuser`. Ført i §8a.

Alt på én linje per spørring: en skrivefeil (`ORDERY BY`) forkaster hele spørringen i psql.
Avlesningen står som punkt 4 i §10a, **før** arkiveringen, som sletter oppdragene.
TODO-punktet er skrevet om til å peke hit.

## 2026-09-24 — TODO: les av indeksene i Postgres etter en vakt  `#drift` `#database`

André: «Den databasen om indekserte kan du skrive det som en todo for meg med konkret
instruks og så poster jeg det til deg for vurdering.» Punktet står under «Krever Andre»:
fire spørringer som bare leser (`pg_stat_database`, `pg_stat_user_tables`,
`pg_stat_user_indexes`, `pg_extension`), `railway connect Postgres`, og hva som skal
vurderes. Tallene skal leses **etter en vakt med ekte last**; statistikken gjelder fra
Postgres sist startet, og spørring A sier når det var. Ingenting tyder på et
indeksproblem i dag; dette er en helsesjekk.

## 2026-09-24 — Oversikt over oppdateringsintervallene: runbook §3d  `#drift` `#dokumentasjon`

André: «Kan du skrive ned i runbook evt en annen plass som er egnet
oppdateringsintervallene på enhver ting /pasiwnter /ko /vaktliste osv så vi har oversikt?»

**`docs/RUNBOOK_VAKT.md` §3d** — ved siden av §3c, der lasten regnes på. Én tabell per side
(alle sider, `/ko/`, sentralbordet, bilens skjerm, `/pasienter/`, `/vaktliste/`,
server-status) med hva som hentes, hvor ofte, om det går over nettet, når løkka står
stille, og fil · funksjon. Nederst: hva én fane koster i forespørsler per sekund når
ingenting skjer — `/ko/` ≈ 0,58, sentralbordet ≈ 0,5, `/pasienter/` ≈ 0,13, bilen ≈ 0,1,
`/vaktliste/` ≈ 0,03 — og rundt 6 i sekundet i kjernetid på KO.

**Holdt i live av `core/tests_oppdateringsintervaller.py`:** hver fil med `setInterval` i
`static/js/` og malene skal stå i §3d (funnet ved å lete, ikke fra en liste), og tallet for
hver navngitt konstant (`KO_LOGG_MS`, `ENDRING_MS` …) skal stemme med raden. Et tall skrevet
rett i kallet kontrolleres ikke — grensen står i testen.
**Mutasjonstesting: 4 mutanter, 4 drept** — etter én rettelse: «2,5 s» inneholder «5 s»,
så `ENDRING_MS` endret til 5000 gikk først grønt. Testen krever nå hele tallet.

**Funnet underveis:** §3 rådet til å «lukke statistikk-fanen mellom oppslag». `/statistikk/`
har ingen løkke, og henter bare når den lastes, så rådet hjalp ikke. Det er byttet ut med «lukk
ekstra faner av samme side». Vaktlista henter heller ikke data av seg selv; bare køen av
stemplinger gjort uten nett sendes hvert 15. s.

## 2026-09-24 — Endringsnummeret for resten av /ko: loggen og sentralbordet oppdaterer seg på 2,5 sekunder  `#ko` `#oppdrag` `#rammeverk`

André: «Okei la oss ta resten av /ko som vi snakket om». Skissen fra tavla (Artifact
«Tavlas endringsnummer») sa: «Loggen og oppdragslista kobles på samme tall i neste runde,
når dere har sett tavla virke.»

**Før:** tavla fulgte endringsnummeret, men loggen hentet hvert 15. sekund og
sentralbordets lister (enheter og oppdrag) hvert 30. — i `/ko/` og på `/oppdrag/`. En bil
som stemplet, eller et nytt oppdrag, kunne stå usett i et halvt minutt hos kollegaen.
**Nå:** alle tre hentes når tallet er nytt. **Prøvd i nettleseren med to brukere: Kari så
Andrés logglinje etter 0,2 s og hans nye oppdrag etter 2,5 s, både i `/ko/` og på
`/oppdrag/`.**

**Ett spørsmål for alle områdene — `folgEndringer()` i `portal-utils.js`**
- Listene melder seg: `folgEndringer('logg', koHentLogg)`, `folgEndringer('oppdrag',
  lastAlt)`, `folgEndringer('tavle', koHentTavle, koTavleErFramme)`. Fanen spør **én gang**
  hvert 2,5 sekund om alle (`/api/endringer/?omrader=logg,oppdrag,tavle`) og henter bare de
  som er nye. Tre løkker ville tredoblet trafikken, og en delt drifts-PC med fire vinduer
  ville nådd bremsen på 240/m.
- Tavlas egen løkke (`koSjekkTavleVersjon`, `koTavleSkalHente`) er borte; regelen «likhet,
  ikke størrelse» bor nå i `endringSkalHente()`.
- En skjult fane spør ikke; en liste som ikke står framme (tavla parkert), er ikke med.
- **Sikkerhetsnettet er 30 s** for loggen (var 15) og sentralbordet, 60 s for tavla.

**`oppdrag` — meldt inn av oppdragsmodulen** (`oppdrag/endringer.py`), ikke av KO: lista er
sentralbordets, og `/oppdrag/` skal være like raskt uten KO. Øker på oppdrag,
koblingsrader, statusmeldinger, enhetshendelser, enhetsbytter, enheter, enhetstyper og
lokasjoner. **KO øker det for det KO eier på oppdragsraden** — prioriteten (H-merket),
lagene og delte linjer — men **ikke for en vanlig linje i strømmen**: da ville hver linje
fått sentralbordet til å hente begge listene. Gate: `les` i oppdrag. **Bilens skjerm
følger det ikke** (TODO).

**`logg` — KO** (`ko/endringer.py`): alt `logg_view` sender — linjene (også festing,
fjerning og deling, som endrer en rad uten ny id), hendelsene med lag og deltakere, og
oppdragene, fordi hendelseslista teller de åpne. Gate: `les` i KO.

**Skrivinger utenom signalene** (`.update()`, `bulk_*`) finnes nå med én felles leser,
`core/test_helpers.skrivinger_utenom_signalene()`, brukt av tavla, oppdrag og loggen.
Den fant én ny: `Linjedeling.bulk_create` i `korriger()` — vurdert: funksjonen er atomisk,
og tallet øker ved commit, etter delingene.

**Mutasjonstesting: 30 mutanter, 28 drept.** To overlevde:
- Den indre `try` rundt hver henting i `sjekkEndringer` var en no-op — alle hentingene er
  startet før `Promise.all` feiler. **Fjernet.**
- «Bare linjer *i en hendelse* øker oppdragslista» kunne utvides til «bare rader med
  `hendelse_id`» uten at noe ble rødt: testene gikk gjennom tjenester som *også* skriver en
  linje i hendelsen, så `Hendelse` og `Linjedeling` alene ble aldri prøvd. **To tester lagt
  til** — redigering av hodet (ingen systemlinje) og deling med ett oppdrag.

## 2026-09-24 — Hendelsen åpnes i hendelsesloggen, med de pågående i en sidebar, og skjerm 2 følger klikkene  `#ko` `#hendelser`

André: «Så må vi se på det med å åpne hendelser fra hendelsesloggen som vises over
loggstrømmen. Der lurer jeg på om vi heller bør ha hendelser i hendelsesloggen men når det
vises i det vinduet så får du en sidebar fra venstre med pågående hendelser (ingen
lukkede)», og «Hendelser bør og kunne åpnes som egen vindu og da når en trykker på en
hendelse i hendelsesloggen så oppdateres den hendelses vinduet». Skissert først (skisse
v2), med svarene: «1 ja. 2. kan sidebaren justeres på slik at vi «taper» mer informasjon
fra den dess mindre den blir? Prioritetsfaege og nummer består, tittel er det siste som
fjernes. 3. nei. 4. enig. Noen skal kanskje registrere noengerdig. 5. ikke noe frst per nå.»

**Før:** et klikk på en hendelse åpnet den i **loggstrømmens** vindu, der den skjulte
strømmen og skrivefeltet. Ingen av rolleoppsettene har loggstrømmen oppe, så klikket så ut
som om det ikke skjedde noe når loggvinduet var skjult. ↗ på loggvinduet åpnet hendelsen i
et nytt vindu per hendelse.

**Nå:**
- **Hendelsen står i hendelsesloggens vindu.** Tabellen byttes mot hendelsen, med de
  pågående (åpne) hendelsene i en sidebar til venstre, i tabellens rekkefølge: nummer,
  prioritetsfarge, tittel, sted, tid siden opprettet. «← Alle hendelser» gir tabellen
  tilbake. Søket, «Vis lukkede» og ↗ i hodet skjules imens.
- **Sidebaren taper informasjon når den smalner**: tid først, så sted, så tittel —
  nummeret og fargen står alltid. Container-spørringer, så det er sidebarens bredde som
  teller, ikke skjermens. Kanten kan dras, og bredden huskes per nettleser.
- **Loggstrømmen viser aldri en hendelse** («3. nei»). Strømmen, filteret og skrivefeltet
  står der uansett.
- **H-merket i strømmen og lagkortet henter fram en skjult hendelseslogg** — punktet «En
  hendelse åpnes i loggvinduet — også når det er skjult» er borte fra TODO.
- **Skjerm 2:** «Eget vindu» i hendelsen (eller ↗ i hodet) åpner ett navngitt vindu,
  `ko-hendelser`. Mens det lever går klikk i hovedvinduet dit; tabellen blir stående med
  raden merket, og hodet sier «H12 vises på skjerm 2». Lukkes det, åpner klikkene seg på
  stedet igjen. Ingen «fest» (svar 5). Hovedvinduet vet om skjerm 2 finnes gjennom et
  livstegn hvert 5. sekund på `BroadcastChannel('ko-hendelse')` (frist 12 s, og «borte» når
  vinduet lukkes) — ikke `localStorage`, der et lukket vindu ville blitt stående som
  «finnes».
- **En hendelse en annen lukker, blir stående åpen, merket «Lukket»** («4. enig»), og går
  ut av sidebaren.
- Gårsdagens `?vindu=logg&hendelse=` er erstattet av `?vindu=hendelser&hendelse=`.

**Prøvd i nettleseren:** sidebaren ved 260/190/140/80/56 px (alt → uten tid → uten sted →
bare nummer), draing av kanten, skjerm 2 som bytter hendelse på klikk i hovedvinduet,
«vises på skjerm 2» som forsvinner når vinduet lukkes, og skjult hendelseslogg som kommer
fram på et H-merke. Ingen JS-feil.

**Mutasjonstesting: 39 mutanter, 36 drept.** Tre overlevde:
- `koErFolger()`-vakten i `koFolgerTilstede` var en no-op: et vindu for seg setter aldri
  `koFolgerSett`. **Fjernet.**
- Merket som skulle forsvinne når skjerm 2 er borte, og at hovedvinduets fanetittel ikke
  røres, var utestet. **To påstander lagt til; begge mutantene drept.**
- Kallstedet i ko.js prøves ved å kjøre den ekte `DOMContentLoaded`-kroken med hvert navn
  byttet mot en opptaker — også rekkefølgen (`koOppsettStart` før `koHendelseVinduStart`).

## 2026-09-24 — Endringsnummeret: tavla oppdaterer seg på 2,5 sekunder, med «Per · nå» på stolpen  `#ko` `#tavle` `#rammeverk`

André: «ta core og tavla fyst». Skissert først (Artifact «Tavlas endringsnummer»), med
forslagene derfra: 2,5 s, merket i 30 s og bare for andre enn deg, ingen kollisjonssperre
ennå, tavla alene først.

**Før:** hver fane hentet hele tavla hvert 15. sekund, også når ingenting hadde skjedd, og
den andre på tavla så en flytting 0–15 sekunder senere. **Nå:** fanen spør om et tall hvert
2,5 sekund og henter tavla bare når tallet er nytt. **Prøvd i nettleseren med to brukere:
Kari så «andre · nå» 0,8 sekunder etter at André flyttet laget.**

**Rammeverket — `core/endringer.py`** (nytt register, som `driftstatus` og `opprydding`)
- Modulene melder inn områder med en gate: `registrer('tavle', gate)`. Endepunktet
  `/api/endringer/?omrader=tavle` svarer bare om områdene brukeren har tilgang til — et tall
  uten tilgang sier at noe har skjedd.
- `endret(navn)` øker tallet **etter commit** (`transaction.on_commit`): ellers kunne fanen
  hentet det gamle bildet, sett det nye tallet og blitt stående feil.
- **Likhet, ikke størrelse.** Tømt cache (omstart, Redis) gir en ny startverdi, og alle
  henter én gang. Tallet ligger i Redis på vakt, delt mellom workerne.
- **Holdt utenfor P95** (`RequestMetricsMiddleware`, som `/healthz/`): fire raske svar i
  sekundet ville trukket P95 ned og beredskapstrinnet vist grønt mens tavla var treg.
- Kaster aldri: en cache som er nede skal ikke stoppe en flytting.

**Tavla — `ko/endringer.py`, `ko/signals.py`**
- **Alt tavla leser, øker tallet**, gjennom signaler: plasseringer, planer, programmet,
  hendelser og lag i KO; pauser, skift og ressurser i vaktlista; oppdrag, statusmeldinger,
  enheter og lokasjoner i oppdragsmodulen; og `ko.tavle_*`-innstillingene — **ikke**
  pasienttelleren, som skrives ved hver registrering. Lagring og sletting.
- **Skrivinger utenom signalene** (`.update()`, `bulk_*`) finnes med AST og må stå i en
  vurdert liste (`TavleEndringerFangesTests`). To står der i dag, begge i samme transaksjon
  som noe som øker tallet. Skanningen fant også et hull i første utkast: sletting av et
  oppdrag eller en hendelse (bilen blir ledig) var ikke med.
- Sikkerhetsnett: hele tavla hvert 60. sekund (var 15 s som eneste henting), for det ingen
  skrev — et skift som begynner.
- Spør bare når tavla står framme **og** fana er synlig.
- **«Per · nå»** på en stolpe noen *andre* satte de siste 30 sekundene (`av_navn` er nå med
  i svaret). Gult merke; flyttingen står også i loggstrømmen som før.

**Mutasjonstesting:** 25 mutanter. **Første runde løy:** alle JS-mutantene «drept» med 5
feil hver — også en som fjernet et kall ingen test rørte. Testfila var selv i stykker
(samme funksjon to ganger i harnessen), så hver kjøring feilet uansett mutant. Rettet og
kjørt på nytt. Da overlevde to: **(1)** `setInterval(koSjekkTavleVersjon, …)` kunne fjernes
fra `koTavleStart` — alle testene av funksjonen var grønne mens tavla aldri spurte. Ny test
går gjennom `koTavleStart`. **(2)** `cache.add` i økningen endret ingenting — `versjon()`
setter uansett en ny start ved neste lesing. Fjernet fra koden. Resten drept.

**Dokumenter:** 181 ruter (tallfasit), registeret i rot-CLAUDE.md (taket hevet til 65 800
med begrunnelse), pollingsetningen der rettet, tavlas rad i `templates/ko/CLAUDE.md`.

## 2026-09-24 — TODO: kontooppryddingen i prod er gjort  `#todo`

André: «Kontooppryddingen er gjort, slett punktet». Punktet «⚠️ Kontoopprydding i prod —
MÅ gjøres før deploy til prod» (besluttet 28. aug. 2026: slett alle kontoer unntatt
admin og én les/skriv-konto, backup av `accounts` først, kontroller at en admin står
igjen) er slettet fra TODO. Punktet om `skriv_handling` for bilkontoer sto under samme
overskrift og har fått sin egen.

## 2026-09-24 — Tråderegelen står på dashbordet, ved tiltakstabellen  `#drift` `#server-status`

André: «er du ikke enig i å legge inn flere tråder i runbook/beredskap under vakt da tråder
gir kjappere database?» Nei — **tråder gjør ikke databasen raskere**, de lar appen sende
flere spørringer samtidig. De hjelper når appen venter på seg selv (lav CPU, rask database,
likevel høy P95), og gjør det verre når det er databasen som er treg. Derfor er de ikke et
trinn i tabellen. Men regelen sto bare i runbook §5, ikke på dashbordet, der man ser under
stress.

- **Under tiltakstabellen på server-status:** «Workers eller tråder? Lav CPU i Railway
  (Metrics) og rask database, men likevel høy P95? … `WEB_THREADS=6` i stedet for flere
  workers (runbook §5). Er det databasen som er treg, gjør flere tråder det verre.»
- Teksten og tallet står ett sted (`TRAADREGEL`, `TRADER_VED_VENTING` i
  `core/admin_status.py`), og testen som holder §5 og tilkoblingstaket i takt leser
  samme konstant.

## 2026-09-24 — Runbooken: workers eller tråder (se CPU), og taket på databasetilkoblinger  `#drift` `#runbook`

André: «Det skal bare øke workers og ikke tråder?» og «kan jeg i teorien ha 10 workers og
8 tråder og da er jeg på 80 connections?»

- **Workers eller tråder avgjøres av CPU** (§2, §5). Python kjører én tråd om gangen per
  prosess (GIL): tråder hjelper når forespørslene *venter*, workers når de *regner*. Høy
  CPU og høy P95 → workers; lav CPU og høy P95 → se «Database», deretter tråder. Til nå
  sa §5 bare «tråder hjelper når de venter», uten å si hvor man ser det.
- **§1c: `WEB_THREADS` skal stå på 4** (eller ikke være satt) ved vaktstart — en 6-er
  igjen fra forrige vakt betyr at vakt-modus ikke er det §2 regner fra.
- **Tilkoblingene regnet riktig** (§3c): ikke `workers × tråder`, men **≈ workers ×
  (tråder + 2)** — hver worker har sin egen backupklokke-tråd, og reservenettet i
  middlewaren kan starte én til. 10 × 8 er da ~100, altså **taket**: tilkobling 101 gir
  `too many clients` og 500 på hver side som trenger en ny. Hold dere under ~80.
- **Test:** `BeredskapstrinnTilkoblingerTests` — høyeste trinn med §5-trådene (4 × 6 → ~32)
  holder seg under 100 minus 20 i margin, og §5 sier fortsatt 6 tråder.

## 2026-09-24 — Server-status og runbooken regnet fra vakt-modus: P95 først, trinnene ett sted  `#drift` `#runbook` `#server-status`

André: «før vakten skal starte spinner vi opp redis og 2 workers og 4 tråder», og Railway
Pro på vakt. Gjennomgangen av runbooken mot dashbordet viste at begge var skrevet som om
man **starter** på 1 worker og skalerer opp ved belastning.

**Det som var feil**
- **Tiltakene startet på feil trinn.** «Oransje: oppgrader til 2 workers» — i runbook §2 og
  i hurtigreferansen nederst på dashbordet. I vakt-modus er det alt gjort. «Rødt» var
  «2 workers + 6 tråder».
- **Dashbordet farget 300–500 ms grønt** (`classifyP95` i malen); runbooken sa gult.
- **Det viktigste tallet var det minste.** Runbooken sier P95; det store tallet på kortet
  var *snittet*, og P95 sto som en liten rad under.
- **Runbook §4 sa at metrikkene er per prosess og «hopper»** — utdatert siden de ble samlet
  i Redis, og i strid med §1c, som ber deg sjekke nettopp det.
- **«Logg ut inaktive»** var gult-tiltaket for alle med flere pålogget enn personell. Med
  KO-operatører på to skjermer er det en operatør som mister vaktbildet.
- **§11 anbefalte Hobby for opptil 40 brukere**, og §5 satte `WEB_WORKERS=2` som «tyngre
  skalering».

**Nå**
- **Trinnene står ett sted:** `BEREDSKAPSTRINN` i `core/admin_status.py`, regnet fra
  `VAKTMODUS` (Pro, 2 × 4, Redis). Grønt < 300 ms · Gult 300–500 · **Oransje 500–1000 eller
  1–2 5xx → `WEB_WORKERS=3`**, etter å ha sett på «Tregeste stier» og «Database» · **Rødt
  > 1000 eller ≥ 3 5xx → `WEB_WORKERS=4`** · Kritisk → last-shed. Dashbordet tegner tabellen
  herfra, og `BeredskapstrinneneIRunbookenTests` holder runbook §2 i takt.
- **`beredskapsnivaa()` regner trinnet på serveren**: det høyeste trinnet der P95 *eller*
  5xx har nådd grensen — 5xx alene kan gi rødt. **Under 20 forespørsler siste 5 min sier
  kortet «få målinger»**: sett på dashbordet — tre forespørsler og én treg ga «Oransje».
- **P95 er det store tallet**, farget etter trinnet, med tiltaket under og raden i
  tabellen markert. Kortet sier om tallene er **«Samlet fra 2 workers»** eller **«Bare
  denne workeren»** (rødt når det er flere workers uten Redis).
- **Worker-kortet sier modusen** (`driftsmodus()`): «Vakt-modus: 2 workers, Redis OK»,
  «Lavkostnad-modus», «Redis er på, men bare 1 worker», eller **rødt ved 2+ workers uten
  virkende Redis**.
- **Dashbordet i to deler:** «Under belastning» (responstid, feil, tregeste stier,
  database, workers, cache, requests, minne, sesjoner) øverst, «Sjekk før vakt» (vaktbildet,
  backup, klokka, cron, konfig, e-post, innlogging, disk) under.
- **Runbooken:** vakt-modus = Pro + Redis + 2 × 4 (§1b–1c, Pro er ikke lenger «valgfritt»),
  §2 som over, §3/3b logger bare ut sesjoner inaktive over én time, §3c sier at KO ikke er
  målt, §4–5 regnet fra 2 workers og «finn flaskehalsen før du skalerer mer», §10c
  nedgraderer Pro etter vakt, §11 og vedlegget peker på trinnene. **Rate-limit-nødbremsen
  er tatt ut av «Kritisk»** — den hjelper mot 429, ikke mot en treg server.

**Mutasjonstesting:** 13 mutanter (trinngrensene, 5xx-leddet, `>=` mot `>`, «få
målinger», modusene, kilden, kallstedet i payloaden, og runbookens `WEB_WORKERS=3`), alle
drept. Prøvd i nettleseren.

**Og den uforklarte røde testen fra 23. sep. er forklart.** `KonsertplanleggerenFolgerTavlaJsTests`
satte `koTavleKlokkeavvik = NAA - Date.now()`, og `koTegnPlan` leste klokka noen
millisekunder senere: vinduet begynte da like etter hel time, og timene ble 13 i stedet
for 12. Rød av og til under full last. Klokka fryses nå (`Date.now = () => NAA`), også i
tavle-testen med samme mønster. Feilen var i testen, ikke i koden — 13 timer er riktig
for et vindu som ikke begynner på en hel time.

**TODO:** KO med fem operatører — endringsnummeret, hendelsen i et skjult loggvindu,
oppsett per rolle og måling av KO-trafikken.

## 2026-09-23 — ↗ på en åpen hendelse åpner hendelsen, ikke loggstrømmen  `#ko` `#vinduer`

André: «Når vi skal åpne en hendelse som ligger i loggstrøms vinduets plass og vil åpne som
et eget vindu så åpner du loggstrøms vinduet istedenfor.»

**Årsaken:** hendelsen åpnes inne i loggvinduet — de deler plassen — og ↗ sendte bare
`?vindu=logg`. Den nye siden visste ikke hvilken hendelse som sto der, og viste strømmen.

- **Står en hendelse åpen, er det den som får eget vindu:** `/ko/?vindu=logg&hendelse=<id>`,
  og siden åpner den ved oppstart. Fanetittelen er hendelsen («H1 · Fall ved scenen · KO»),
  så to slike kan skilles i oppgavelinja.
- **Ett nettleservindu per hendelse** (`ko-hendelse-<id>`): to hendelser kan stå side om
  side på skjerm to, og ↗ på samme hendelse igjen henter fram det som alt er åpent.
- **I hovedvinduet lukkes hendelsen, og strømmen står igjen** — loggvinduet skjules *ikke*,
  slik det gjør når hele loggstrømmen flyttes ut. Uten åpen hendelse er alt som før.
- `&hendelse=` leses som data: bare for `logg`, og bare et positivt heltall.

**Mutasjonstesting:** 9 mutanter (`koEgetVinduHendelse`, `koEgetVinduUrl`,
`koApneEgetVindu`, kallstedet i `koOppsettStart`, fanetittelen), alle drept. Kallstedet
prøves gjennom `koOppsettStart` med en tom DOM, ikke bare lesingen av adressen. Prøvd i
nettleseren: H1 åpen → ↗ → nytt vindu med H1, hovedvinduet viser strømmen.

## 2026-09-23 — Tavla og konsertplanleggeren, runde 2: framover i tid, «+ Planlegg» på alle rader, «Flytt nå», felles tidslinje og egne vinduer  `#ko` `#tavle` `#planlegger`

André etter test på staging: «Tidslinjen på tavlen er litt rar. Når du drar over en enhet så
begynner navnet i "fortid", det må heller gå fremover i fremtid. Og planleggeren ser ut til å
være ren konsert planlegger. Greit nok men da må vi omgjøre på navnet. Og trenger planlegg
knapp på alle lokasjonene for å kunne sette ressurser. Vi må og kunne se lenger frem i tid enn
bakover. Og kunne scrolle tilbake og frem i tid for å planlegge. Endre navnet konserttyper til
Artist. … Og så er planlegger broken, du har bare valgt dager. Jeg må jo få en tidslinje aktig
oppsett som kan følge tavle. og hvis jeg går frem i tid på planlegger tidslinjen skjer det
samme med tavlen.»

Skissert først (Artifact «Planleggeren, runde 2»). Svarene: **1.** planleggingen inn i tavla,
konsertdelen blir eget vindu, «Konsertplanlegger» — og «Den funksjonaliteten må gjelde alle
vinduer vi har i flaten vår» (eget nettleservindu) · **2.** artistlista er KO-lederens · **3.**
«KO skal trykke flytt nå» · **4.** alle som fører tavla planlegger, «kan være vi strammer inn» ·
**5.** «la admin og ko-leder kunne justere på rulling» · **6.** synk begge veier. «Gjør alt i
helhet.»

**Tavla**
- **Stolpen vokser framover.** Den åpne plasseringen var høyreforankret ved nå og vokste
  *bakover* til 72 px — et lag som nettopp var plassert sto med navnet «i fortid». Nå begynner
  den der laget kom, og ligger over sin egen stiplede slutt.
- **Mer framover enn bakover:** ¼ av vinduet før nå som standard (var ⅔). KO-leder setter
  andelen (0–50 %) og hvor langt ◀ ▶ flytter (15–720 min) i KO-innstillinger → «Tavla».
  Verdier utenfor avvises ved lagring og klemmes ved lesing; uten feltene i kroppen skrives
  ingenting (ingen tomme auditrader).
- **◀ Nå ▶, og dra i aksen** for å gå fram og tilbake i tid. Er nå utenfor det man ser, står
  «Du ser ikke nå · Tilbake til nå», og nå-streken tegnes ikke — før ble den klemt til kanten
  og så ut som nå.
- **«+ Planlegg» i hver rad**, ikke bare i Pause-raden. `PlanlagtPause` har fått `pause` og
  `lokasjon`/`lokasjon_navn` (migrasjon `ko/0020`): en plan i Pause-raden (≤ 4 t) eller på et
  sted (≤ 1 døgn). Planen står stiplet i raden den skal til. **Laget må ha skift når planen
  begynner** (`paa_vakt_ved`), ikke være på vakt *nå* — en plan for i morgen gjelder laget som
  går vakt i morgen. Nedtrekket er hele vaktlista (`alle_ressurser`), biler bare på et sted.
  Klokkeslettene leses nær der tidslinja står, så en plan kan legges i morgen.
- **«Flytt nå»** (og «Pause nå») fra ti minutter før — på stolpen og på kortet i «Uten plass»
  («Flytt nå · Village»). KO trykker; tavla flytter ingen. Står laget alt der, knyttes planen
  til den plasseringen. **Planens slutt blir plasseringens planlagte slutt**, så overtiden
  vises som for alt annet — men en slutt KO alt har satt, overskrives ikke. Et sted som er
  slettet etter at planen ble lagt, gir en feilmelding med det frosne navnet.
- En plan på et sted skjuler ikke vaktlistas pause, og trekkes ikke fra i dekningen — bare
  pauser gjør det.

**Konsertplanleggeren** (het «Planlegger»)
- **Følger tavlas tidslinje** — samme vindu, samme ◀ Nå ▶, samme drag. Ruller du det ene,
  ruller det andre. Døgnknappene er borte; «Liste» viser hele programmet døgn for døgn.
- **Dekningen hentes for vinduet**: `/ko/api/program/dekning/?fra=<time>&timer=N` (1–48;
  `?dogn=` virker fortsatt). Søylene står i prosent under tidslinja, så de treffer båndene
  også når vinduet ikke begynner på en hel time. Hentes ikke mens aksen dras.
- **«Konserttyper» heter «Artister»** (fanen, skjemaet, lista). Modellen heter fortsatt
  `Konserttype` — backupfilene bærer modellnavnet. **Navnet på konserten er valgfritt**; tomt er
  artistens. Typeforslagene fra `0017` («Headliner», «Pop», «Fast post (ikke konsert)» …) er
  typer, ikke artister, og fjernes der de er ubrukt (`ko/0021`); en i bruk blir stående.

**Egne vinduer — alle seks**
- **«Åpne i eget vindu»** (↗) i hodet på hvert KO-vindu: `/ko/?vindu=<navn>` viser bare det
  vinduet over hele flaten, for skjerm to. Samme side, ikke en egen mal — ett sted vinduet
  tegnes. Oppsettet lagres ikke derfra. I hovedvinduet skjules det og står i stripa.
- **Tidslinja synkes mellom vinduene** over `BroadcastChannel('ko-tid')`: et nytt vindu spør
  de andre hvor de står. Ikke `localStorage` — en fane som lastes på nytt, skal følge nå.
  Meldingene leses som data (`koTidMelding`): bare et positivt tall eller `null`.

**Funnet i nettleseren:** teksten over tidslinja sa «Ons. 23.09. 14:11 – Ons. 23.09. 02:11» —
datoen kom fra døgnnøkkelen (døgnstart 06), der natta hører til onsdagen. Klokka 02 er
torsdag; teksten bruker nå kalenderdatoen. **Og `start_pause` mistet den planlagte slutten**:
`sett_planlagt_slutt` henter raden på nytt med `select_for_update` og returnerer den nye, og
returverdien ble kastet — funnet av den første testen.

**Mutasjonstesting (for hånd):** 23 mutanter i tjenestelaget og viewene (`ko/tavle.py`,
`ko/program.py`, `ko/views.py`, `0021`) og 31 i JS-reglene (`ko-tavle.js`, `ko-plan.js`, `ko-layout.js`). **To overlevde i første
runde, begge tettet:** (1) testen for at en stedsplan ikke skjuler vaktlistas pause la de to i
*hvert sitt* tidsrom, så regelen ble aldri prøvd; (2) `if 'andel_bak' in data …` kunne
fjernes uten at noe ble rødt, fordi standardverdiene ga samme resultat — testen krever nå at
ingenting skrives. **I JS overlevde én:** kortet i «Uten plass» kunne si «Pause 22:00» om en
plan på et sted uten at noe ble rødt — byggeren var prøvd, men ikke veien gjennom
`koTavleUtenPlass`. Tettet.

**Tester:** `ko/tests_tavle_plan.py` (ny), `ko/tests_tavle_runde2_js.py` (ny, med
`koTegnTavle` og `koTegnPlan` gjennom den ekte inngangen), og de eksisterende tavle- og
planleggertestene skrevet om til et eksplisitt anker der de forutsatte ⅔ bakover.

## 2026-09-23 — Forslag: kartmodul med værlag (vind, nedbør, farevarsler)  `#kart` `#docs`

Ingen kode. Utredning lagt i `docs/FORSLAG_KARTMODUL.md` og som eget prosjekt under
«Ideer / backlog» i `TODO.md` — **ikke noe som gjøres i år** (André, 23. sep. 2026), men
arbeidet med kilder og arkitektur skal ikke måtte gjøres på nytt.

**Avgjort av André:** kart med topografi og flyfoto/satellitt, farevarsler,
vindretningspiler og nedbørsmengde, fra **MET, Kartverket og NVE/Varsom**. Ingen
kommersielle kilder (Windy og OpenWeatherMap ble vurdert og valgt bort). Nødfall uten nett
tas ikke i første omgang. Kildehenvisningen står som vannmerke nede til høyre.

**Kostnad: 0 kr i data.** Alle tre er åpne data (NLOD / CC BY 4.0). En helg med ti
lokasjoner er rundt 1 000 kall mot MET; grensen er 20 forespørsler per sekund.

**Tre funn som styrer arkitekturen:**
- **Portalen har ingen kart, ingen værdata, og `oppdrag.Lokasjon` har ingen
  koordinater** — kontrollert i koden.
- **CSP-en blokkerer kartflisene i stillhet** (`img-src 'self' data:`). Grått kart, ingen
  feilmelding — samme felle som `media-src blob:`.
- **MET krever `User-Agent`, som JavaScript ikke kan sette** — derfor henter serveren
  værdataene og cacher dem, mens nettleseren henter flisene direkte fra Kartverket.

**Og flyfotoet er ikke åpent lenger.** Kartverket har lagt ned de åpne WMTS-tjenestene
for Norge i bilder; den nye tjenesten krever GeoID-token og er for parter i Norge
digitalt. Står som åpent spørsmål i notatet (§6.1), med Sentinel-2 som reserve.

---
## 2026-09-23 — Avtalte pauser i vaktlista, og KO-tavla henter dem  `#vaktliste` `#ko` `#pauser`

André: «vi har planer om å hente avtalte pauser fra /vaktliste som er en funksjon som ikke er
lagt inn enda». Svarene før koden: **1. per lag/ressurs · 2. teller i timene: ja · 3. leder ·
4. mannskapet ser dem, «men admin kan skjule det i innstillinger» · 5. regel i planleggeren:
«nå»**.

**Vaktlista**
- **Ny modell `vaktliste.Pause`** (migrasjon `0021`), per ressurs. Regler i `vaktliste/pauser.py`:
  innenfor skiftene (et skiftbytte 14–22 / 22–06 er sammenhengende, så 21:45–22:15 går),
  **høyst fire timer**, og **aldri to over hverandre** på samme ressurs. Samme tre regler som
  KOs pauser, så en pause lagt inn her ikke kan bli avvist på tavla.
- **Pausen teller i timene**: budsjettet, timeoversikten og belastningen er uendret. Testet.
- **Lederen** (`kan_lede`) legger inn, flytter og fjerner: «+ Pause» og brikkene i en ny
  **pauselinje i hodet på ressurskortet**. Alle med `les` ser dem. Nye endepunkter:
  `POST api/ressurser/<pk>/pauser/`, `PUT/DELETE api/pauser/<pk>/`. Auditlogget
  (`vaktliste_pause`).
- **Regelen i planleggeren**: «Pause (min) etter (timer)» per ressurs, og **forskjøvet** eller
  samtidig. Tre lag som starter 14:00 med «30 min etter 4 t» tar pause **18:00, 18:30 og 19:00**,
  ikke alle samtidig. Regelen står på ressursen og leses tilbake. Regelpausene lages på nytt
  ved hver «Lag grunnlaget»; en pause lederen har lagt inn eller rettet for hånd, står og
  vinner. Et for kort skift får ingen pause. Får ikke de forskjøvne pausene plass i skiftet,
  sier planleggeren fra (400), i stedet for å droppe dem stille. Bekreftelsen viser antall
  pauser.
- **Utskriften og fila på e-post** viser pausene («Pause: 02.10 18:00–18:30»). Oversikt har
  dem under tida. **Admin kan skjule dem** under portalinnstillingene («Pausene i
  vaktlista»); på skjermen står de alltid.

**KO-tavla**
- **Vaktlistas pauser står i Pause-raden av seg selv, uten kopi** (`tavle.effektive_pauser`,
  id `v<pk>`). Retningen er `ko` → `vaktliste`; vaktlista vet ingenting om KO.
- **Endrer, starter («Pause nå») eller fjerner KO en av dem, blir den KOs**
  (`PlanlagtPause.fra_vaktliste`, migrasjon `ko/0019`), i samme transaksjon som handlingen. En
  avvist endring etterlater ingen kopi. Endret er **«endret i drift»** (prikket kant,
  `title`). Fjernet blir **`avlyst`**, ikke slettet, ellers dukket vaktlistas opp igjen ved
  neste poll. **Vaktlista overstyrer ikke KOs versjon lenger**, og KO vinner også når en egen
  KO-pause overlapper en av vaktlistas.
- **Dekningsstripa i planleggeren trekker fra lag i pause midt i timen**, og tipset sier
  «(2 i pause)». Det er her en pause lagt midt i headlineren blir synlig før vakta.

**`vaktliste/CLAUDE.md` er delt**, som KO og oppdrag før den. Fila sto 32 tegn under taket
sitt, og pausene trengte plass. Flaten (planleggingsflatene, tabellene og tidsfeltene,
JS-filene) er flyttet **uendret** til `templates/vaktliste/CLAUDE.md`; skriptet sammenlignet
linjene før og etter, og ingen manglet. Taket for vaktlistefila er senket fra 56 900 til
43 950, så delingen ikke gror igjen. Rotas tak er hevet 200 tegn, bevisst: raden i kartet
over modulfilene er rammeverk, og rota sto 17 tegn under.

**Kjente grenser:** pause per person (samleplassen der seks tar pause én og én) finnes ikke;
det kommer bare om en ekte vakt ber om det. En KO-overtakelse står som KOs egen pause etter en
gjenoppretting, fordi `fra_vaktliste` strippes i backupen (pekeren går mot vaktlista, og
sirkelen er den samme som for `ressurs`).

**Mutasjonstesting: 78 mutanter**: 37 i vaktlistas tjenestelag og porter, 21 i KO, 20 i JS.
**Ti overlevde første runde:**
- **Én var en ekte feil i oppførselen** (vaktlista #23): et lag på «samtidig» tok ingen plass i
  forskyvningen, så et forskjøvet lag i samme gruppe kunne legge seg oppå det. Nå tar alle lag
  med pause en plass i rekka. Mutantens oppførsel var bedre enn koden, og den ble tatt inn.
- **Én var et ekte hull i en port** (KO #15): uten den første sjekken ble bilens pause overtatt
  for en bruker uten oppdragstilgang, og raden ble stående selv om svaret var 404, fordi en
  404 inne i `transaction.atomic()` ikke ruller tilbake. Testen krever nå at ingenting er
  overtatt.
- **Seks var hull i testene:**
  - en pause inntil *foran* en annen
  - en annen ressurs sin pause på samme tid
  - riktig melding for halv regel
  - at «samtidig» lagres på ressursen
  - sorteringen når vaktlistas pause kommer mellom KOs
  - at dekningsendepunktet sender vakta videre
  - og i JS at «+ Pause» er borte for `skriv_full`
- **Én er ekvivalent** (filteret på vaktlista i `fil.rader_for`): pausene slås opp på
  ressursens id, så filteret sparer bare spørringen.

Alt annet ble drept, blant annet:
- grensene (`<`/`<=` i alle ender: fire timer, skiftet, overlapp, regelens kanter, midten av
  timen)
- `and` → `or` i «innenfor skiftene»
- sperrene på KOs overtakelse, avlysning og overlapp
- transaksjonen rundt overtakelsen
- ledergatene
- «bare lista i bruk»
- escapingen

## 2026-09-23 — Planleggeren: endringshistorikk, plan mot faktisk og «kopier programmet»  `#ko` `#planlegger`

Steg 5 og siste av tavleplanleggeren. André: «det er egentlig kjempesmart. Og fint for videre
år på samme arrangement å kunne se hva vi hadde på de konsertene og risikovurdering/
beredskapsnivå.»

- **Hver endring i programmet lagres** (`ko.Programendring`, migrasjon `0018`): lagt til og
  slettet med hele bildet, endret med **bare feltene som endret seg** — «beredskap Gul → Rød,
  behov 1 Ambulanse, 2 Lag → 2 Ambulanse, 3 Lag». Å lagre uten å endre noe gir ingen rad.
  Bildet er tekst, ikke pekere, og tida har dato, så historikken kan leses også når stedet
  eller gruppa er borte.
- **Systemlinje i KO-loggen bare i drift** (`program_endret`): når konserten pågår eller
  begynner innen to timer, før *eller* etter endringen. Planlegging i god tid havner i
  historikken, ikke i loggen. Å utsette en konsert som skulle begynt om en time, er nettopp
  det loggen skal vise.
- **Ny visning i planleggeren: «Etterpå»** (tredje knapp). Per konsert: beredskap, behov
  (med «opprinnelig: …» når det er endret), **faktisk på stedet** — snitt, og minutter under
  behovet per gruppe, fra tavlas plasseringer (pauser teller ikke) — antall oppdrag på stedet
  mens konserten pågikk, og hvor mange ganger den ble endret. Historikken står under.
  Døgnvalget er skjult der, fordi visningen gjelder hele vakta.
- **Tidligere vakter** (vaktvelgeren) og **«Kopier programmet hit»** er KO-lederens. Kopien
  flyttes i **hele døgn** så første konsertdøgn lander på valgt dato, og klokkeslettene
  står. En konsert kl. 05:30 hører til døgnet før, som på tavla. Sted og gruppe matches på
  id, ellers på navn. **Det som ikke kan tas med, blir nevnt**: et sted som er borte, eller
  **en gruppe som er borte** (den siste ble funnet underveis — resten av behovet kom med, og
  linja ble borte uten at noe ble sagt). Har aktiv vakt alt et program, spør den først (409):
  «Kopien legges til ved siden av, ingenting erstattes. Fortsette?»
- Oppdrag fra en arkivert vakt telles per oppdragsnummer (arkivet har én rad per oppdrag
  *og enhet*). **Etter kollaps står det «–», ikke 0**, fordi 0 ville vært en påstand og
  ikke et tall.

**Kjent grense:** «faktisk» er tavlas plasseringer, som i «Besøk». Tida en bil bruker på et
oppdrag på stedet, er ikke med.

**Mutasjonstesting: 38 i tjenestelaget og viewene, 12 i JS.** Python: grensene i «i drift»
(`<=`/`<` i begge ender, forvarselet fjernet), systemlinja bare i drift, ingen rad uten
endring, «før *eller* etter», slettingen, diffen, `_dekket` (`<` mot `<=`, `and` → `or`,
tom lengde), pause, sted og gruppe (id og navn), klippingen, «startet», antall endringer,
arkiv og kollaps, oppdragsvinduet, døgnforskyvningen, stedsmatchingen og portene (403, 404,
409, «ikke fra seg selv»). **Åtte overlevde i første runde, og sju var ekte hull:**
plasseringer fra før konserten ble ikke klippet, oppdrag før konserten, arkiv etter kollaps,
`distinct` på oppdragsnummer, døgnet til en konsert før døgnstart, inaktivt sted på id med et
aktivt med samme navn, og kopi fra seg selv. Den siste gikk grønn fordi testen traff «ingen
program å kopiere» først. Døgnmutanten overlevde også den nye testen første gang: **01:30
norsk tid er 23:30 UTC dagen før**, så `.date()` traff riktig døgn ved en tilfeldighet. Testen
bruker nå 05:30. Den åttende var en ekvivalent mutant: et ekstra `transaction.atomic()` rundt
`lagre_post`, som selv er atomisk og gir lagringspunktet. Den er fjernet, med en kommentar.
JS: 12 av 12 drept (ledergaten, «ikke på aktiv vakt», «opprinnelig» bare ved endring, «–»
for ukjent, escaping av historikken og raden).

## 2026-09-23 — Planleggeren: tidslinja over døgnet, og dekningen mot vaktlista  `#ko` `#planlegger`

Steg 4 av tavleplanleggeren — «tabletoppen» fra skissene: **hvor mange trengs, og har vi
dem?**

- **Tidslinja** er nå standardvisningen i planleggeren (listen er den andre, knappene i
  hodet). Hele døgnet fra døgnstarten, **stedene som har noe det døgnet som rader**, i samme
  rekkefølge som på tavla, og konsertene som bånd i beredskapsfargen med navn og behov.
  Konserter som overlapper på samme sted får hver sin bane. Nå-streken når døgnet er i dag.
  KO-leder klikker et bånd for å endre konserten.
- **Dekningsstripa** under: én søyle per time, **behovet mot hvor mange vaktlista har på
  vakt** i den gruppa — «7/6» — med én fane per ressursgruppe som har et behov det døgnet.
  **Rød når det trengs flere enn det er på vakt.**
- **«På vakt» er vaktlistas regel, og ingen egen**: et skift med mannskap, ikke avmeldt,
  som dekker midten av timen. Regelen er skilt ut som
  `vaktliste.services.ressurser_med_skift` og brukes nå av både ressursoversikten og
  planleggeren — **og den teller bilene ut fra skiftene deres**, fordi bilens «på vakt»-bryter
  er hva KO har skrudd på *nå*, ikke hva som er planlagt i kveld.
- **En konsert teller i hver time den berører** — 22:30–23:30 trenger folk i både 22- og
  23-timen. Forsiktig med vilje: stripa sier heller «for få» enn «nok» når den er i tvil.
- Tallene er vaktlistas, så porten er vaktlistas `les` (som tavla). Uten den sier stripa
  hvorfor, i stedet for å vise null.

**Mutasjonstesting: 22 mutanter** — midten av timen, døgnstarten, begge vilkårene i «på vakt»
(mannskap, avmeldt), at lagene i ressursoversikten fortsatt er uten biler, porten,
overlappen i timen (`<` mot `<=` i begge ender), summeringen, «for få» bare med kjente tall,
fanene, vinduet, banene, radrekkefølgen, nå-streken, ledergaten og escapingen. **To
overlevde**, begge grensetilfeller testen ikke berørte: en gruppe uten id (ble til nøkkelen
«null»), og *akkurat nok* — trengs lik på vakt skal ikke være «for få». Tettet.

**Underveis:** en gammel testserver fra forrige runde sto fortsatt på porten, så det første
skjermbildet viste gammel kode («Kunne ikke hente dekningen», knappene manglet). Ikke en feil
i koden, men verdt å vite neste gang et skjermbilde ser rart ut.

## 2026-09-23 — Tavla: behovet i drift, «Lag 2/4» per sted  `#ko` `#tavle`

Steg 3 av tavleplanleggeren. Under stedsnavnet på tavla står nå **behovet til konserten
som pågår — mot det som står der**: «Lag 2/4», «Ambulanse 0/1». **Gult når noe mangler,
grønt når det holder**, og verktøytipset sier det med ord.

- **Fra 30 minutter før konserten begynner**, så lagene er på plass når den starter
  (`KO_TAVLE_BEHOV_FORVARSEL_MIN`), og til den er slutt.
- **Det som teller som «står der»**: en åpen plassering på stedet, **og** et lag på en
  hendelse eller en bil på et oppdrag der — opptatt på stedet er fortsatt på stedet. Et lag
  i pause eller på et annet sted teller ikke.
- **To konserter samtidig på samme sted legges sammen.**
- Gruppa matches på id, og på navnet når id-en er borte (en gjenopprettet backup stripper
  pekeren til vaktlista).

**Mutasjonstesting: 13 mutanter** — forvarselets grense (`<=` mot `<`), slutten, filteret på
sted, `kommer`, summeringen (`+=`), lukket plassering, opptatt på stedet, navnematchen,
«mangler» på grensen, og begge kallstedene (`koTavleRader` og `koTavleRadHtml`). Alle drept.

## 2026-09-23 — Programmet: konserter med beredskapsnivå og behov, planleggervinduet, bånd på tavla  `#ko` `#tavle` `#planlegger`

Steg 2 av tavleplanleggeren. André: «Kunne legge inn type konserter på ulike konsertsteder.
… Risikonivå med farge. Og planlegge for antall lag og andre ressurser», og svarene før
koden: beredskapsnivå **«grønn, gul, oransje og rød … en standardisert form»**,
**«Konserttyper skal ikke automatisk sette ressurser»**, «Spesiallag er en fast type lag»,
**«KO-leder»** legger programmet, og planleggeren **«inni i ko rutenettet med samme løsning
som tavlen, at den er minimert»**.

**Planleggervinduet** — det sjette vinduet i KO. Det **deler plass med oppdragslista** og
står **parkert i stripa som standard** («Skjult: Planlegger»). Hentes det fram, kan tavla og
planleggeren stå side om side i nederste rad. «⇄ Planlegger» i oppdragslistas hode og
«⇄ Oppdragsliste» i planleggerens bytter.

- **Konsertene per døgn og sted**: tid, navn, type, beredskapsnivå, behov («4 Lag · 2
  Ambulanse»), forventet publikum og kjennetegn. Døgnknappene i hodet, fra vaktstart og
  hvert døgn som har en konsert.
- **«+ Konsert» og klikk på en konsert er KO-lederens** (`skriv_leder` i KO); alle med `les`
  ser programmet.
- **Skjemaet**: sted, navn, døgn, fra–til, type, forventet publikum, beredskapsnivå
  (grønn/gul/oransje/rød eller «ikke satt» for et fast behov), kjennetegn og **behov per
  ressursgruppe i vaktlista** — ett tallfelt per gruppe, skrevet inn for hånd. **Typen fyller
  ikke inn noe.** Et klokkeslett før døgnstarten hører til natta etter («01:00 fredag» er natt
  til lørdag), og 22:00–00:30 går over midnatt av seg selv.
- **Konserttyper og kjennetegn er lister KO-leder setter opp**, som ansvarsområdene: nye
  faner i KO-innstillinger. Seedet med forslaget fra skissene — typene Headliner, Hiphop /
  rap, Rock / metal, Pop, Elektronisk / DJ, Akustisk / lokal, Fast post; kjennetegnene
  **Pyro**, Sittende publikum, Moshing ventet, Mye barn, Alkoholservering. Svaret fra
  samarbeidspartneren legges inn der den dagen det kommer, uten en ny versjon av portalen.
  En type eller et kjennetegn i bruk — også i fjorårets program — slettes ikke, men kan
  deaktiveres.
- **Spesiallag**: opprettes som en ressursgruppe i vaktlistas oppsett. Ingen kode.

**På tavla**: konsertene står som **bånd bak radene** — skravur og en kant øverst i
beredskapsfargen, med navnet, og hele teksten i verktøytipset. Formen er bevisst en annen
enn prioriteten på hendelsene, så «rødt» ikke betyr to ting på samme skjerm.

**«Følg konserten»**: i «Tider og slutt» for et lag som står på et sted med en konsert, kan
slutten settes til konsertens. **Forsinkes konserten, følger lagets slutt med** uten at noen
retter noe. Bare samme sted, og bare en konsert som ikke er over. Egen tid og «følg» er
aldri begge; slettes konserten, har laget ingen planlagt slutt lenger.

**Under panseret:** `ko/program.py`; modellene `Konserttype`, `Kjennetegn`, `Programpost`,
`Programbehov` og `Tavleplassering.folger` (migrasjon `0016`, forslaget i `0017`). Alt
valideres før noe skrives, og lagringen er én transaksjon — en konsert blir aldri stående
uten behovet sitt. Sted, type og ressursgruppe fryses som navn, så programmet kan leses år
etter år; pekerne ut av modulen strippes i backupen. Endepunkter: `/ko/api/program/`,
`/ko/api/program/<pk>/`, og de to listene. `ko-plan.js` er KOs femte JS-fil.

**Mutasjonstesting: 43 mutanter.** Tjenesten tungt (hver grense i navn, tid, antall og
publikum; hver sperre på sted, type, gruppe, beredskap og kjennetegn; behovet som byttes ut;
transaksjonen; «følg»-reglene), portene (lederkravet på POST og PUT/DELETE, vaktscopet,
`folger_id`) og JS-reglene (døgnstarten `<` mot `<=`, «til» etter «fra», døgnvalget,
kroppen, lederknappen, båndenes filter, «følg» i kroppen og rekkefølgen bånd–stolpe).
**Tre overlevde første runde, og alle tre var hull i testene:** en test gjorde sted *og*
type inaktive samtidig, så feilen kunne komme fra typen; transaksjonen var usynlig fordi
valideringen skjer før all skriving (testen feiler nå skrivingen halvveis med en mock); og
**ingen test gikk gjennom `koTavleRader` med et program**, så kallstedet kunne fjernes —
nøyaktig fella CLAUDE.md beskriver. Tettet.

**Funnet i nettleseren:** beredskapsmerket i planleggeren var grått. Standardfargen sto som
`--bf` på grunnregelen, senere i fila enn `.ko-beredskap-*` og med samme spesifisitet — den
vant. Står nå i `var(--bf, …)`.

## 2026-09-23 — Tavla: planlagt slutt på plasseringen, og overtid  `#ko` `#tavle`

Steg 1 av tavleplanleggeren. André: «planlegge tid per plassering med beskjed/tegn på
overtid i faktisk drift. Både i planlegger men og generelt i tavlen.» Skissene
(Artifact «Tavleplanleggeren») ble avtalt før koden; resten av stegene står i TODO.

**Hva er nytt:** en plassering kan få en **planlagt slutt** — «Lag 1 står på Parkscene
til 23:45». Den settes i skjemaet «Tider og slutt» (knappen i linja når laget er valgt,
eller klikk på den stiplede slutten), og tomt felt er ingen plan.

- **Stiplet fra nå og fram til slutten** på tavla, med «til 23:45».
- **Når tida er ute: rød kant på laget og «26 min over»**, en rød strek der det skulle
  sluttet, og «1 over» i radhodet.
- **Planen flytter ingen.** Samme regel som de planlagte pausene: et lag midt i noe skal
  ikke forsvinne fra raden sin fordi klokka sa det. KO flytter det.
- **Bare på den åpne plasseringen, fram i tid, høyst et døgn** (`sett_planlagt_slutt`).
  Planen står igjen på den lukkede plasseringen — «planlagt til 23:45, gikk 00:10» er
  grunnlaget for plan mot faktisk i steg 5 — og en ny plassering arver den ikke.
- **Tidene og slutten lagres som én ting**: PUT på plasseringen tar `fra` og
  `planlagt_til` i samme transaksjon. Feiler slutten, er heller ikke «fra» rettet.
- `skriv_full` i KO setter og endrer, `les` ser. Tida på en plassering er drift og
  hører til operatøren.

**Mutasjonstesting: 20 mutanter.** Tjenesten tungt (hver grense: `<=` mot `<` på «fram
i tid», `>` mot `>=` på døgnet, sperren på den lukkede, lagringen), porten (transaksjonen,
tolkningen av `planlagt_til`, «ingenting å endre») og JS-reglene (over/ikke over på
minuttet, banen som holdes av den stiplede, kallstedet for byggeren, skrivegaten, escaping).
**Én overlevde**, og den var en test som løy: den lette etter `ko-tavle-over` og fant
strengen inne i `ko-tavle-over-tekst`, så klassen kunne fjernes. Testen leser nå klassen
alene. Én mutant jeg skrev var en no-op, og er ikke talt med. **Én test jeg skrev påsto
ingenting** (`all(True for _ in …)`) — skrevet om til den ene situasjonen der noe står fram
i tid i samme rad: en planlagt pause i Pause-raden.

## 2026-09-23 — Ressursoversikten: «Vis»-meny (synlighetsknapp) i stedet for minimering og Alle | Biler | Lag  `#ko` `#oppdrag/sentralbord`

André: «istedenfor minimer som tar plass at vi har en synlighetsknapp istedenfor på
ressursoversikt», og etter forslaget: «ja jeg vil ha forslaget ditt i ressursoversikten».

**Hva som er endret:** en **«Vis»-knapp med øye** over ressurslista, med en avkrysning per
gruppe — Ambulanse, Mannskapsbil, Lag til fots, og vaktlistas grupper (Lag, Samleplass …).
Gruppene står under to seksjoner, **«Biler» og «Lag»**, og et klikk på seksjonen skjuler
eller viser hele — det er den gamle Alle | Biler | Lag, som er borte. Menyen blir stående
åpen mens man krysser av, og «Vis alle» står nederst når noe er skjult.

**En skjult gruppe tar null plass** — heller ikke overskriften står igjen, som den gjorde
med minimering. **Men det skjulte synes:** knappen sier «Vis · 3 skjult» (antall
*ressurser*, ikke grupper — det er ambulansen man leter etter) og er **gul** så lenge noe
er skjult. Er alle bilene skjult, står «Alle bilene er skjult — se «Vis»» der lista var.

**Samme meny i `/oppdrag/`**, ved «Ressurser», med bare «Biler» — lista er den samme
funksjonen på begge sidene, og valget huskes felles per nettleser
(`tavle.grupper.skjult`). **Tidligere lukkede grupper og Alle | Biler | Lag-valget er ikke
tatt med over** — alt står synlig første gang, og de gamle nøklene leses ikke lenger.

**Funnet underveis:** `portal.css` setter kant og tekst på alle `.btn-outline-secondary`
med `!important`, så knappens gule «noe er skjult» ble slått ut og knappen så lik ut uansett
— sett i skjermbildet, ikke av testene. `.ko-legende-knapp.aktiv` (kolonneknappen) har
trolig samme feil; ikke rørt her.

**Tilgang:** `oppdrag-kort.js` lastes bare med oppdragstilgang, men `ko.js` lastes alltid —
`ko.js` kaller derfor menyen gjennom en vakt (`koOppdaterSynlighet`), ellers ville
oppstarten kastet en `ReferenceError` for den som bare har vaktlista.

**Mutasjonstesting: 19 mutanter** på reglene — filteret i begge listene, vippingen,
seksjonsregelen (`some` → `every`), «Vis alle», tallet (ressurser, ikke grupper), gult merke,
kallstedene og escapingen i menyen og overskriften. **To overlevde første runde**, og begge
var ekte hull: kallet i `tegnEnhetsliste` er det *eneste* som tegner menyen i `/oppdrag/`,
men testen hadde alltid KO-funksjonene til stede; og at lagene kommer inn i menyen når
`koHentRessurser` henter dem, var ikke prøvd. Begge har egen test nå.

## 2026-09-23 — Opprydding: «Velg…» i nedtrekkene, hastegraden som forsvant, ledig i enhetsvalget, to kolonner som overlappet  `#oppdrag/sentralbord` `#ko` `#vaktliste`

André: «Neste ledd er litt opprydning».

**Bug: «når du trykker at opprett så mister en hastegraden sin».** Rotårsak funnet og
gjenskapt i Chromium. «Nytt oppdrag» i `/ko/` har en hendelsesvelger som arver
hendelsens hastegrad, og den pollet hvert 15. sekund (`koFyllHendelsevalg` →
`koHendelsevalgEndret`). Når skjemaet ble åpnet, **slettet** `koNullstillHendelsevalg`
merket for hva som sist var arvet i stedet for å sette det til «ingen hendelse». Den
første pollen etter åpningen så da «uten hendelse» som et *nytt* valg, arvet ingenting
— og kalte `velgHastegrad('')`, som tømte hastegraden operatøren nettopp hadde valgt.
**«Hender det at»** fordi det kom an på om pollen rakk å gå før «Opprett». To rettinger,
hver av dem nok alene: merket settes til `''`, og det arves bare når det faktisk er en
hendelse (`h &&`). Skjer det at en hendelse tas bort eller lukkes mens skjemaet står
åpent, står hastegraden som den står. Test:
`test_pollen_etter_aapning_tommer_ikke_hastegraden`.

**«Velg…» øverst i nedtrekkene uten lagret verdi.** André: «Hvis man har valgt og lagret
en verdi så må jo den så klart være selected … Hvis obligatorisk felt så feilmelding om
man lagrer med "Velg..." selected.» `velgValg(valgt)` og `velgTekst()` i
`portal-utils.js` er den ene kilden. Nedtrekkene det gjelder:
- **Nytt oppdrag:** lokasjon og problemstilling. Før sto første lokasjon og «Udefinert»
  valgt, og det så ut som valg noen hadde gjort. `nyttOppdragMangler()` sier «Velg hvor.»,
  «Velg hastegrad.» eller «Velg problemstilling.» ved knappen, i skjemaets rekkefølge.
  Byttes hastegraden etter at en problemstilling var valgt, gjelder vinduets regel —
  beholdes om den kan, ellers «Udefinert» — ikke tilbake til «Velg…».
- **Oppdragsvinduet:** brikkenes nedtrekk (hastegrad, problemstilling, lokasjon, ressurs),
  «Legg til» og «Flytt» (fra og til). «Velg…» lagret er en feilmelding, ingen forespørsel.
  **Ressursen er ikke obligatorisk** — «Opprett uten enhet» finnes — så på et oppdrag uten
  enhet er «Velg…» ingen handling. Med én enhet: «Oppdraget har én enhet — velg en annen
  for å flytte det».
- **KO:** «Knytt eksisterende oppdrag» og lag-valget i «Planlegg pause» på tavla.
- **Vaktlista:** gruppe i «Ny ressurs» («Velg hvilken gruppe ressursen hører til.») og
  korps i personskjemaet.
- **Ikke endret, med vilje:** nedtrekk der det tomme valget *er* en verdi med navn —
  «— ledig plass —» i vaktlista, «Uten hendelse», «Hele vakten», «Alle» i backlogfilteret,
  «Legg til lag …». Å kalle dem «Velg…» ville sagt at noe mangler når det ikke gjør det.
  De som alt sto med «—» (pasientskjemaet, lokasjon i ny hendelse) oppfyller «"Velg..."
  eller "-"» og står som før.

**Ønske: «Ledig i nedtrekkslista».** Enhetsvalget i «Nytt oppdrag» viser statusen ved
navnet — prikken og «Ledig»/«Fremme» osv. — og ledig står grønt og uthevet. Rekkefølgen er
fortsatt type og navn: en liste som stokker seg om mens man krysser av, er verre.

**Bug: «Overlapp kolonne visning ressursoversikt».** **Ikke gjenskapt** — i Chromium på
340, 463 og 626 px bredde var det null overlapp før og etter. Men oppsettet var skjørt:
CSS-`columns: 2` på beholderen med `break-inside: avoid` på hver gruppe. En gruppe kunne
ikke deles, så **alle lagene sto i én kolonne med den andre tom**, og multikolonne rundt
rutenett er der nettleserne fragmenterer ulikt. Nå er det **to spor inne i hver gruppe**,
gruppene under hverandre i full bredde, og `minmax(0, 1fr)` lar ikke et langt navn dytte
sporet ut i naboen. Et rutenett fragmenterer ikke. Ser André overlappet igjen, trengs et
skjermbilde og nettleseren.

**Ønske: synlighetsknapp i stedet for minimering** — besvart, ikke bygget. Står i TODO.

**Også:** `sentralbordkontekst` sendte `problemstillinger` for første hastegrad til malen,
som ikke lenger brukte den — fjernet. `flyttOppdrag` fikk vist sin egen feil (teksten ble
satt i et skjult element; funnet ved mutasjon).

**Mutasjonstesting: 33 mutanter.** 32 på reglene: `velgValg`, `nyttOppdragMangler` (hvert
ledd og synligheten), `problemstillingEtterBytte` (hvert ledd og kallstedet),
`_verdiValg`/`_verdiForesporsel`/`lagreVerdi`, vaktene i `varsleEnhet`/`flyttOppdrag`,
«Velg…» i `_varsleValg`/`_flyttValg`, ledig-merket og escapingen i `mkEnhetsvalg`, tavlas
lag-vakt, «Knytt», hastegradsrettingen og vaktlistas gruppevakt. **Tre overlevde første
runde**, og alle tre var hull i testene: at feilteksten i «Nytt oppdrag» blir *synlig*,
kallstedet i `lagreVerdi`, og «Velg…»-markeringen på hastegrad. Tettet. Den 33. —
`delete sel.dataset.arvet` tilbake — overlever og er **ekvivalent**: `h &&`-vakten alene
hindrer feilen. Begge står, fordi hver av dem alene er nok.

## 2026-09-23 — Oppdraget: verdiene endres rett i vinduet, uten «Rediger», og står i tidslinjen  `#oppdrag/sentralbord`

Backlog punkt 4 og 5. André: «klikke på disse verdiene når de er skrevet ut gir en liten
dropdown for de andre valgene», og «Ikke måtte trykke rediger for å se/redigere info i et
oppdrag». 23. sep.: «rediger knappen inne i oppdraget gjemmer redigerbar info».

**Inne i oppdraget, ikke i oppdragslista.** Begge ble vurdert. Lista tegnes på nytt ved
hver polling, så et åpent nedtrekk forsvinner; hele raden er en knapp som åpner
oppdraget; og et feilklikk på en travel liste endrer et oppdrag uten at noen ser det.
André: «avvent litt» med lista — den står i TODO.

**Hva som er endret i oppdragsvinduet:** «Rediger»-knappen og skjemaet er borte.
**Hastegrad, problemstilling, lokasjon og tildelt ressurs står som brikker** øverst; et
klikk gir et nedtrekk med den gjeldende verdien valgt, og valget lagres med én gang, ett
felt om gangen. **Oppdragsnotatet står alltid framme**, med «Endre»/«Legg til».

**Svarene André ga før koden:**
- **Hastegraden alene:** problemstillingen **beholdes om den passer**, ellers blir den
  **«Udefinert»** — for eksempel Akutt → Drift med «Pustevansker». Før ga det en 400.
  «Udefinert» sperrer Ledig til noen setter en som passer. Sendes hastegrad og
  problemstilling sammen, gjelder valideringen som før.
- **Tildelt ressurs:** uten enhet legges den valgte til; med én flyttes oppdraget
  (`flytt_til_enhet`, som alt står i tidslinjen); **med flere er brikken låst**, og
  «Flytt»/«Legg til» under gjelder.
- **Hver endring står i oppdragets tidslinje:** «Hastegrad: Akutt → Drift · andre»,
  «Problemstilling: Pustevansker → Udefinert (passet ikke den nye hastegraden)»,
  «Oppdragsnotat endret». **Notatet logges uten verdier**, samme regel som audit.

Ny modell **`Oppdragsendring`** (migrasjon `oppdrag/0032`) med frosne verdier som tekst, så
en omdøpt lokasjon ikke skriver om historikken; `endret_av` strippes i backupen. `endringer`
følger med i `GET /oppdrag/api/oppdrag/<id>/`. Samme vindu i `/oppdrag/` og `/ko/`.

**Prøvd i Chromium:** Akutt → Drift på O1 ga «Udefinert» automatisk, notatet ble lagt til,
og de tre linjene sto i tidslinjen med hvem. Ingen konsollfeil.

**Mutasjoner: 20, alle drept** — regelen for hastegrad begge veier, at den bare gjelder når
hastegraden kommer alene, loggingen og «uten verdier», at uendret ikke logges, at
«før»-verdiene leses fra basen, backup-strippingen, og i nettleseren: låsen med flere
enheter, skrivegaten, «legg til» mot «flytt», filtrene i nedtrekkene, escapingen og
kallstedet i tidslinjen. En gammel prøve ble endret med vilje: «hastegrad Drift alene gir
400» er nå «gir Udefinert» — det var Andrés avgjørelse.

## 2026-09-23 — KO fører «Avbrutt» for en bil, og `oppdrag/CLAUDE.md` er delt  `#oppdrag/statusmaskin` `#core/dokumentasjon`

**«Avbrutt» i sentralbordets «Endre status»** (bestilt 22. sep. 2026). Bilen melder på
samband at den avbryter; før kunne KO bare føre «Ledig», og da ble det ikke ført som
avbrutt, og oppdraget ble ikke flagget «trenger ny ressurs». Nå står **«Avbrutt — trenger
ny ressurs»** sist under «Videre» når bilen står i Rykker ut eller Fremme — samme steder
bilen selv har Avbryt-knappen. Gjelder både `/oppdrag/` og `/ko/` (delt malbit).

`services.foer_avbrutt` er bilens `avbryt_oppdrag` ført av sentralbordet: samme regel
(`AVBRYT_FRA`, prøvd ett sted), samme «trenger ny ressurs»-logikk og samme
`Enhetshendelse.AVBRUTT`, men med operatøren som meldt av, meldingen merket `manuell`, og
tidspunktet prøvd som en ny melding (ikke i framtida, ikke før det bilen alt har meldt).
Endepunktet er det sentralbordet alt bruker: `POST …/enheter/<id>/status/avbryt/`
(`skriv_full`). Lista over hvor Avbrutt finnes kommer fra serveren
(`window.OPPDRAG_AVBRYT_FRA`), så nedtrekket og bilen kan ikke bli uenige. Prøvd i
Chromium: MB 2 i Fremme → Avbrutt → oppdraget flagget, merket på plass.

**Mutasjoner: 10, alle drept** — sperrene i tjenesten, `manuell` begge ledd, portene i
viewet, regelen i nedtrekket og linja i malbiten. En dublett ble fjernet før mutasjonene:
`foer_avbrutt` sjekket `AVBRYT_FRA` selv, og `avbryt_oppdrag` sjekker det samme.

**`oppdrag/CLAUDE.md` er delt** (sto 3 tegn under taket). Frontendseksjonen — de to
grensesnittene, ressurslista delt med `/ko/`, sentralbordet i `/ko/` — er flyttet ordrett
til `templates/oppdrag/CLAUDE.md`, som lastes når noen arbeider i `templates/oppdrag/`,
samme grep som KO-fila fikk dagen før. Kontrollert med skript: hver ikke-tom linje fra før
står i en av de to filene. Oppdragsfila er nede fra 22 636 til rundt 18 000 tegn, og
unntaket i `FOR_STORE_I_DAG` er strøket — den står under `MODUL_TEGNGRENSE` som de andre.
Rota peker på den nye fila i begge tabellene; plassen ble hentet ved å korte rotas egen
rad («Det som gjelder alle moduler — se overskriftene») i stedet for en regel.

## 2026-09-22 — KO-tavla, steg 2: planlagte pauser, retting, «Besøk» og innstillingene  `#ko/oppsett`

André: «Ja kjør begge stegene du.» Steg 2 er resten av skissene.

**Pause-raden planlegges** (André: «la oss kunne sette en pause rad og legge inn pauser der
for lagene»). «+ Planlegg» i Pause-raden gir et skjema med lag, fra og til; den planlagte
står stiplet blå i raden, og **klikk på den** endrer eller fjerner. Fra ti minutter før får
laget **«Pause nå»** — på stolpen i Pause-raden og på kortet i «Uten plass» — og KO starter
den; **tavla flytter ingen av seg selv**. Står laget alt i pause, knyttes planen til den.
Rød kant når tida gikk uten at pausen ble tatt. Regler: maks fire timer, ikke i fortida,
aldri to over hverandre (heller ikke oppå en som er startet). Ny modell
`ko.PlanlagtPause` (migrasjon `ko/0014`). **Vaktlistas avtalte pauser finnes ikke ennå** —
regelen for når de kommer (vaktlista er utgangspunktet, KOs endring i drift vinner, merket
«endret i drift») står i TODO; den trenger et kildefelt som legges til da.

**Retting i etterkant** (skisse 3): klikk på en lukket stolpe, eller «Rett tidene» i linja
når et lag er valgt. Et skjema med fra/til, ikke et dra i kanten — et feildrag på en travel
tavle skal ikke flytte historikken stille. **Naboene tilpasses** (den forrige kortes, den
neste begynner senere), men **en nabo forsvinner aldri**, og tida på en hendelse rettes
ikke og gås ikke inn i. «Til» er låst på den åpne og der en hendelse tok over. «Fjern
plasseringen» for en som aldri skjedde. Loggen får «Lag 1 Parkscene rettet: fra 20:10 →
20:00» / «… fjernet fra tavla» (`TAVLE_RETTET`).

**«Besøk»** (knappen i tavlas hode, skisse 4): per lokasjon, per ressurs, antall eller tid
per døgn, hele vakta, tid totalt og sist der — «Lag 1 var 3 ganger på fredag men 0 på
lørdag». Døgnet regnes fra døgnstarten (06:00), så en konsert kl. 01 hører til fredagen.
Tida på en hendelse teller, også den laget står på nå. **På et fulgt sted (★) står nullene
øverst**, så færrest besøk, så den som var der for lengst siden. Under tavla: **«★ Ikke
vært på Parkscene denne vakta: Lag 4, …»**.

**Innstillingene** (skisse 5): tidsvinduet **12–24 timer** og **døgnstarten** er
portalinnstillinger (global admin, `/portal-admin/innstillinger/`). **KO-innstillinger fikk
fanen «Tavla»** (`skriv_leder`): per lokasjon «På tavla» og «Følg besøk ★». KO eier
avkryssingene, ikke lokasjonene — to ID-lister i `AppSetting`, auditlogget.

**Endepunkter:** `PUT/DELETE /ko/api/tavle/plasseringer/<id>/`, `POST /ko/api/tavle/pauser/`,
`PUT/DELETE /ko/api/tavle/pauser/<id>/`, `POST /ko/api/tavle/pauser/<id>/start/`,
`GET/PUT /ko/api/tavle/oppsett/` — 167 ruter nå. Skriving er `skriv_full` i KO (oppsettet
`skriv_leder`); bilene fortsatt bare med oppdragstilgang. Et ugyldig tidspunkt er en 400,
ikke «nå» som i loggen: en retting som stille ble til nå, har skrevet om historikken.

**Prøvd i Chromium:** «Pause nå» flyttet Lag 2 fra Village til Pause, «+ Planlegg» la inn
en pause for Lag 3, retting av Lag 1s pause 20 minutter tidligere kortet Parkscene-stolpen
før den, «Besøk» med nuller øverst, og fanen «Tavla» — ingen konsollfeil. **Én feil funnet
der:** korte planlagte pauser lot teksten flyte over naboene, og «Pause nå» lå under en
annen stolpe; klikket traff feil ting. Stolpen vokser nå framover til navnet og knappen får
plass, og banen holdes opptatt så lenge.

**Mutasjoner: 69, alle drept eller likeverdige.** Tjenestelaget, portene og
portalinnstillingene (44): **5 overlevde første runde.** Tre av dem — at tida på en
hendelse ikke rettes eller gås inn i — ble «drept» av prøver som avviste av **feil grunn**:
tidene lå i framtida, så «fram i tid» slo til først. Prøven er skrevet om med alt i
fortida. Den fjerde avdekket en regel: en startet pause blokkerte ikke en ny plan oppå
seg; nå gjør den det. Den femte: fanen «Tavla» for `skriv_full` var ikke prøvd. JS (25):
**6 overlevde** — tre fikk prøver (kortet viser neste pause som ikke er tatt; en knapp
velger ingenting; et klikk som flytter åpner ikke skjemaet i tillegg), og tre var
likeverdige og er forenklet bort (en pausesjekk i Besøk, «sist der» som alt er sist, og en
midnattsomregning `koTavleTidNaer` alt gjør).

## 2026-09-22 — KO-tavla, steg 1: vinduet, dra og slipp, «Uten plass» og forrangen  `#ko/oppsett`

André: «Hvis tavlen skal være på /ko så finner jeg den ikke» — den var skissert, ikke
bygget. Nå er den der: **«Tavle» i hodet på Ressursoversikten**, og i stripa over
konsollen («Skjult: Tavle»). Tavla og ressursoversikten **deler én plass** i rutenettet
(`KO_PAR` i `ko-layout.js`); den som ikke står der, står i stripa. Et oppsett lagret før
tavla fantes er gyldig som det er — ingen KO-PC mister oppsettet sitt.

**Hva som er med:** lokasjonene fra oppdragsmodulen som rader med **Pause** fast øverst;
tidslinja med nå-streken ved to tredjedeler (12 t foreløpig); **«Uten plass»** som egen
kolonne og slippmål, med «Siden pause: 1 t 30» på de ledige og de opptatte under;
**dra og slipp** med pekerhendelser (virker på nettbrett), og **klikk laget, så raden**
(også Enter/Esc); filteret er vaktlistas ressursgrupper (Alle, Lag, Ambulanse,
Mannskapsbil …); ⏱ på et lag som har stått over tre timer på samme sted.

**Forrangen (André: «hendelser og oppdrag tar prioritet men skal vises på tavlen»):**
bare en ledig ressurs kan dras. Et lag på en åpen hendelse står stiplet i raden til
hendelsens lokasjon, «På H14»; en bil fra første opptatt-status står stiplet ved
oppdragets lokasjon, «O12 Fremme». Laget som går på en hendelse forlater plassen sin, og
**når det går av eller hendelsen lukkes, står det uten plass** — tida på hendelsen blir
en lukket rad med H-nummeret, så «Besøk» (steg 2) teller den. Bilens plass lukkes av
signalet på første opptatt-status, også når sentralbordet fører Fremme uten Rykker ut;
en tidsretting på et ferdig oppdrag rører den ikke.

**Tilgang:** tavla krever `les` i KO **og** i vaktlista; bilene bare med `les` i
oppdragsmodulen — også ved flytting (404, ikke 403). Flytte er `skriv_full` i KO. Hver
flytting er en systemlinje: «Lag 1 → Parkscene (fra Club Venue)», «Lag 1 uten plass (var
Parkscene)».

**Modell:** `ko.Tavleplassering` (migrasjon `ko/0013`) — ressurs, lokasjon eller pause,
fra/til, frosne navn, maks én åpen per ressurs (håndhevet av basen). `ressurs`,
`lokasjon` og `av` strippes i backupen. Endepunkter: `GET /ko/api/tavle/`,
`POST /ko/api/tavle/plasser/`, `POST /ko/api/tavle/uten-plass/` — 162 ruter nå.

**Prøvd i Chromium** med seedede lag, en hendelse og en bil på oppdrag: drag fra «Uten
plass» til en rad, klikk-så-rad til Pause, ingen konsollfeil. To ting ble rettet av det:
en åpen stolpe med minimumsbredde stakk forbi nå-streken (den vokser nå bakover), og
rutenettet hadde `min-width` som rullet nå-streken ut av syne i den smale plassen.
Klikk på en rad etter å ha valgt et lag gjorde ingenting med mus — klikket ble bare lest
i `pointerup`, som ikke fyrer for en rad uten drag; `click` tar det nå, og klikket etter
et drag svelges.

**Mutasjoner: 66, alle drept utenom fire likeverdige.** Tjenestelaget og portene (44):
de første 33 lot **9 overleve**, og hver fikk en prøve — slettet lokasjon er ikke pause,
av og på i samme øyeblikk gir ingen rad, en åpen hendelse i en annen vakt gjør ikke laget
opptatt, inaktive lokasjoner og andre vakters plasseringer er ikke i svaret, tidsretting
rører ikke plassen, et stempel ført bakover gir ingen rad som slutter før den begynte.
`med_biler` i `opptatt()` var død (bilene er med når de er blant ressursene) og er
fjernet, og signalet lukker nå på hver opptatt-status, ikke bare Rykker ut — funnet av
mutanten. JS (22): **3 overlevde og er likeverdige** — pause-raden sjekket `!p.pause` to
ganger (forenklet), og de to leddene i `koGyldigePlasser` impliserer hverandre med ett
par og fire plasser (begge beholdt: med to par trengs begge). ⏱ på en lang pause fikk en
prøve. `OPPTATT_STATUSER` + `tildelt` er likeverdig: tildelt har ingen koblingsrad.

**Kjent grense:** bilens tid på oppdrag blir ikke tavlehistorikk; den står i
oppdragsmodulen. Lag uten ressurs i vaktlista står ikke på tavla.

## 2026-09-22 — KO-tavla: pauser planlegges i Pause-raden  `#ko/oppsett`

André: «la oss kunne sette en pause rad og legge inn pauser der for lagene. Som skal
overstyres av /vaktliste men kunne endres på i drift og hvis lag ikke har fått planlagt
pause i /vaktliste.» Regelen i TODO: **vaktlista er utgangspunktet, KOs endring i drift
vinner**, merket «endret i drift», og KO kan planlegge for lag vaktlista ikke har gitt
pause. Skisse 2 viser det: «+ Planlegg» i Pause-raden, klikk på en planlagt pause for å
endre eller fjerne, farger per kilde (vaktliste, KO, endret i drift), og «Pause nå» på
laget når tiden er inne — KO starter den; tavla flytter ingen av seg selv.

## 2026-09-22 — KO-tavla: svarene på skissene, og avtalte pauser i TODO  `#ko/oppsett` `#core/dokumentasjon`

André svarte på de fire spørsmålene skissene reiste: **Pause** er en fast rad øverst;
**når hendelsen lukkes** går laget til **«Uten plass»**, som skal være en egen kolonne;
fulgte steder og lokasjonene på tavla er KO-lederens innstilling; filteret bygges fra
ressursgruppene i vaktlista. Skisse 2 er oppdatert: «Uten plass» er slippmål (dra dit for
å avslutte en plassering), en demoknapp lukker H14 og viser Lag 3 flytte dit med
hendelsens tid som stiplet historikk, og en avtalt pause står stiplet i Pause-raden.
**Avtalte pauser i vaktlista** er ført i TODO — funksjonen finnes ikke; vaktlista har
hviletid mellom skift (`_hviletider()`), ikke pauser i et skift.

## 2026-09-22 — `ko/CLAUDE.md` delt: flaten til `templates/ko/CLAUDE.md`, og skisser av KO-tavla  `#core/dokumentasjon` `#ko/oppsett`

**KO-fila var på taket** (22 249 av 22 300 tegn etter at taket ble hevet 21. sep.), og
tavla kommer med et avsnitt til. André: «ko/claude.md finn en god løsning og løs det.»

**Delingen følger når fila lastes.** Claude Code laster en CLAUDE.md når noen arbeider i
mappa den står i. Modellene og reglene — retningen, nivåene, loggen, hendelsene — står
igjen i `ko/CLAUDE.md` (15 455 tegn). **Flaten** — vinduene, rutenettet, hendelsesloggen i
nettleseren, ressursoversikten og sentralbordet i `/ko/` — er flyttet til
`templates/ko/CLAUDE.md` (7 494), fordi vinduer og knapper endres i `templates/ko/`.
Flyttet, ikke skrevet om: hver ikke-tom linje fra før står i en av de to filene
(kontrollert med skript). `static/js/ko-*.js` laster ingen av dem, som før; flatefila sier
det i ingressen, og rotas frontend-tabell peker dit.

**Vaktene kjenner flatefila** (`core/tests_claude_md.py`): `_modulfiler()` tar med
`templates/<app>/CLAUDE.md`, så den må stå i `DOKUMENTER`, i tabellen i rota og under
taket som modulfilene — ellers hadde delingen vært en vei rundt alle tre reglene.
`ko/CLAUDE.md` er ute av `FOR_STORE_I_DAG`. Tre mutanter på vaktene, alle drept. Rota fikk
plass til raden ved å korte kommentaren om `myproject` i kommandoblokka.

**Skisser av KO-tavla** (`#ko/oppsett`), før koden, som André ba om: Artifact «KO-tavla —
skisser» med fem artboards — `/ko/` med tavla på ressursoversiktens plass, tavla i detalj
med dra og slipp og klikk-så-rad, retting av en plassering, «Besøk» per lokasjon og døgn,
og innstillingene. Svarene hans og det som gjenstår å avklare står i TODO.

## 2026-09-22 — Bilen kan avbryte også i Fremme, og «Dashboard» er borte fra menyen  `#oppdrag/enhetsskjerm` `#oppdrag/statusmaskin` `#core/grensesnitt`

**Avbryt gjelder fra Rykker ut til og med Fremme** (`#oppdrag/statusmaskin`). André: «avbrutt
som gjelder fra en trykker rykker ut til og med når en er fremme, gjelder ikke fra avreist
av.» Avbryt var *den andre knappen* i Rykker ut (`ALTERNATIV`), og i Fremme hadde
«Behandlet på sted» den plassen. **Avbryt er derfor sin egen knapp nå**, styrt av
`services.AVBRYT_FRA = {Rykker ut, Fremme}`; `ALTERNATIV` har bare Behandlet igjen.
`avbryt_oppdrag` avviser alt utenfor settet med 409 — fra Avreist har hun en pasient i
bilen, og veien er Leverer eller KO. Det som skjer ved avbrytelsen er uendret: raden blir
Ledig uten Udefinert-sperre, oppdraget går tilbake til KO som «trenger ny ressurs», og
`Enhetshendelse.AVBRUTT` skrives. **En bil som avbryter i Fremme har ikke løst
oppdraget** — `noen_loste_oppdraget()` teller bare Behandlet og Leverer.

**På bilens skjerm** (`#oppdrag/enhetsskjerm`) står Avbryt i full bredde under de to andre,
med rød kant, og spør før den sender. Tre knapper på rad fikk ikke plass på en telefon —
Avbryt havnet utenfor kortet på 390 px — og den som sjelden brukes skal ikke ta plass fra
dem som brukes hele tiden. Serveren sender `kan_avbryte` per rad, og siden får
`OPPDRAG_AVBRYT_FRA` slik at knappen står også mens et trykk ligger usendt uten dekning.

**«Dashboard» er borte fra modulmenyen** (`#core/grensesnitt`). André: «om du trykker på
Sanitetsportalen så kommer du til hjemskjerm.» Logo og navn er nå **én** lenke hjem
(«Til forsiden»). **Og headeren var for trang på telefon** etter at menyen flyttet inn i
den: på 390 px overlappet bjella hamburgeren og klokka ble kuttet. Under 576 px står logoen
alene som lenken hjem, og navnet gir plass. Sjekket i Chromium på 390 og 1440 px.

**Mutasjonstesting:** 9 mutanter — settet uten Fremme, settet med Avreist, sperra i
`avbryt_oppdrag` fjernet, `kan_avbryte` feil utledet, projeksjonen uten settet, knappen
ugatet, knappen ikke tegnet, `OPPDRAG_AVBRYT_FRA` borte fra malen, og Dashboard tilbake i
menyen. **Alle drept.** At malen sender `OPPDRAG_AVBRYT_FRA` hadde ingen test; den ble
skrevet før mutanten ble kjørt, fordi Avbryt uten lista ville forsvunnet nettopp når bilen
er uten dekning.

## 2026-09-22 — Menyen inn i headeren, «Behandlet» rosa, og KO setter alle statuser uten å slette loggen  `#oppdrag/statusmaskin` `#oppdrag/sentralbord` `#core/grensesnitt` `#core/dokumentasjon`

Tre punkter fra backloggen i portalen, tatt stilling til med André først. Migrasjon
`oppdrag/0031` legger bare til to nullbare felter; ingen eksisterende rad endres.

**KO/administrator kan sette alle statuser — og «Angre» sletter ikke lenger loggen**
(`#oppdrag/statusmaskin`). Backloggen: «I dropdown for status bør KO/administrator kunne
sette alle statuser, også de som har vært. Blir feil å trykke angre i loggen, for loggen
må bevares og det er ikke intuitivt å endre det der.» Det var verre enn det så ut:
**`angre_siste_status` slettet statusmeldingene fra basen** (`_slett_meldinger`), og
sporet fantes bare i revisjonsloggen, som bare admin ser. Det sto i strid med modulens
egen regel for «Rett tid» — «`Statusmelding` er et spor av hva som faktisk ble meldt» —
som skriver en ny rad og lar den gamle stå.

- **«Endre status» tilbyr alle statuser** utenom den enheten står i, i to grupper:
  *Videre* og *Tilbake til*. Forvalget er neste ledd, som før; for den som er ledig er det
  statusen hun sto i før.
- **Framover kan ledd hoppes over.** Leddene imellom står **uten** tidspunkt — de diktes
  ikke. En responstid som mangler er ærligere enn en som er funnet på.
- **Bakover trekkes meldingene tilbake**, med hvem og når
  (`Statusmelding.trukket_tilbake_at`/`_av`). De står i tidslinjen, gjennomstreket, med
  «trukket tilbake 19:45 av andre». Ingen ny melding skrives og ingen tid trengs, så
  klokkeslettfeltet skjules (`_trengerTid()`).
- **Over i den andre grenen** (Behandlet ↔ Avreist/Leverer) trekkes grenen tilbake og målet
  føres som ny melding.
- **«Angre» og «Gjenåpne» er borte**, med endepunktene `…/angre/` og `…/gjenaapne/`
  (159 ruter, var 161). Den som er ledig får «Endre status» som alle andre.
  48-timersgrensen for `Ledig` gjelder fortsatt: eldre enn det er oppdraget arkivets.

**Én regel, ett sted:** `gjeldende_bulk()` siler bort tilbaketrukne rader, og alt som
regner — statistikken, arkivet, bilens knapper, KO-tavla — går gjennom den. De to
spørringene som går rett på tabellen fikk samme filter: `ledig_siden_bulk()` og
`noen_loste_oppdraget()` — **en tilbaketrukket Leverer er ikke en jobb som ble gjort.**
En tilbaketrukket retting overstyrer fortsatt originalen, så originalen blir ikke gjeldende
igjen. «Rett tid» avviser en tilbaketrukket melding. Brukerpekeren strippes i backup som
`meldt_av`.

Reglene er to rene funksjoner, `trekkes_tilbake()` og `kan_foeres_til()`, prøvd uttømmende.
`sett_status(hopp=True)` er sentralens vei; bilen går fortsatt gjennom `OVERGANGER`.

**Mutasjonstesting:** 30 mutanter — 20 i tjenestelaget og viewet, 9 i JS-en som avgjør, og 1
etter at en test ble lagt til. **2 overlevde først:**
1. `>=` → `>` i `trekkes_tilbake`. **Ekvivalent:** det eneste paret på samme trinn er
   Behandlet/Avreist, og det dekker `_andre_gren()` alene. Koden er forenklet til `>` så den
   ikke later som den har en regel til.
2. `_trengerTid()` uten Venter-regelen. **Ekte hull**, og test lagt til: Venter har ingen
   melding å peke på, så uten regelen måtte KO fylt inn en tid som ikke brukes.

**«Behandlet på sted» er rosa, ikke grønn** (`#oppdrag/sentralbord`). Backloggen: «Nå er
den grønn, bør ikke være akkurat samme farge som Ledig.» Det var `#10b981` mot `#22c55e`,
to grønnfarger som knapt skilles på en skjerm. Nå `#ec4899`: rosa finnes ikke andre steder
på tavla, og ligger langt nok fra rødt til ikke å lese som alarm. **Fargeforklaringen fulgte
med av seg selv** — `koLegendeHtml()` bruker CSS-klassen — og sier nå «Behandlet på sted /
Utført», som statusen heter på oppdrag uten pasient.

**Modulmenyen står i den blå headeren** (`#core/grensesnitt`). Backloggen: «Gi mer plass i
høyden. Menyraden bør flyttes inn i hamburgermeny … fjern margin-top i .portal-footer.»
Footeren ga ingen rader på `/ko/`: konsollen måler høyden sin og fyller vinduet ned til
16 px over bunnen, så footeren lå alt under kanten. **Det som tok plassen var menyraden** —
~45 px, og for en admin med tretten lenker brakk den til to linjer. Valgt sammen med André:

- **Modulene i headeren, admin-lenkene i avatar-menyen.** Én rad spart, og bytte mellom
  `/ko/` og `/vaktliste/` er fortsatt ett klikk. Fire av admin-lenkene sto alt begge steder;
  nå står alle sju der, under «Administrasjon», med den aktive markert.
- **Hamburger under 1200 px**, der modulene ikke får plass ved siden av klokka og bjella.
  Lenkene tegnes fra én mal, `partials/_portal_moduler.html`, begge steder.
- **Footerens luft er 0,5rem**, ikke 0. Footeren står igjen: den bærer byggnummeret staging
  verifiseres mot.

Headeren er sjekket i Chromium på 1440 og 1100 px, uten konsollfeil.

**Og i dokumentene:** `oppdrag/CLAUDE.md` sa at «sentralens føring følger `OVERGANGER` som
før» — det gjør den ikke lenger. Rettet innenfor taket (22 647 av 22 650 tegn), med en
dublerende kryssreferanse strøket. `TEKNISK_DOKUMENTASJON.md`: 159 ruter, 32 under
`/oppdrag/`.

## 2026-09-22 — TODO: det som gjenstår etter 21. sep. skrevet ned  `#core/dokumentasjon`

Pulje 7d står med det som *er* bestemt (S6/S7, nedlasting som HTML, minst mulig
personopplysninger, aktiv vakt) og det ene åpne valget (`les_alle` med etikett eller nytt
`les_leder`), så det ikke må tas opp igjen. To nye punkter: pause KOs polling når fana er
skjult, og «Til» i «Flytt oppdrag» som fortsatt tilbyr opptatte biler. Det gamle «Pulje 7
— avventes, haster ikke» fra 18. sep. er slettet: 7a–7c er bygget.

## 2026-09-21 — Vinduer kan skjules, loggstrømmen filtreres, og avvent klonet enheten  `#ko/oppsett` `#ko/loggen` `#oppdrag/statusmaskin` `#oppdrag/sentralbord`

Sju punkter fra André, 21. sep. 2026.

**Vinduene kan skjules og hentes tilbake** (`#ko/oppsett`). Rammen holdt alle fire synlige
fram til nå («en ramme rundt som sperrer for at de kan gjemmes og forsvinnes», 18. sep.).
Bekymringen — en flate ingen ser er en flate ingen vet har endret seg, siden sida poller —
er nå besvart i konstruksjonen framfor med et forbud: **et skjult vindu står alltid som en
knapp i stripa over konsollen**, med navnet sitt, og `koKanSkjule()` nekter å skjule det
siste synlige. Skjulknappen (`bi-eye-slash`) står i hvert vindus hode; `skjult` ligger i
`ko.oppsett` og overlever en sidelasting. Naboen tar plassen; er begge i en rad skjult,
forsvinner raden og den andre tar høyden — ellers sto en tom stripe igjen. Alle fire i
`skjult` avvises ved innlesing: lagringen skal ikke kunne bære tilbake en tilstand
grensesnittet har nektet.

**Loggstrømmen filtreres: Alle | Meldinger | System** (`#ko/loggen`). Huskes per nettleser
som Alle | Biler | Lag. **Festede linjer står uansett** — de er festet med vilje, og et
filter som tok dem bort ville gjort festingen utilregnelig. Hodet teller det som faktisk
står der, ikke totalen. Knapperaden skjules mens en hendelse står i vinduet: da filtrerer
den ikke det man ser på. Tom strøm sier om det er filteret eller om det ikke står noe der,
samme regel som `koOppdragTomMelding()`.

**Og `avvent_oppdrag` er idempotent mens hun avventer.** Å skjule knappen holder ikke:
`visOppdrag()` kan tegne på en liste som er et poll gammel, og offline-køen sender på
nytt. Funnet ved å prøve endepunktet direkte etter at knappen var fikset — to «Avventer»
i tidslinjen og to i hendelsens logg.

**Bug: «Avvent» klonet enheten på tavla** (`#oppdrag/statusmaskin`). «Hvis du trykker
avvent så klones det i oppdragslistens oversikt.» Klonen fulgte av konstruksjonen og var
derfor sikker, ikke tilfeldig: `avventer_av_bulk` tar med **bare** rader som fortsatt står
i `Venter` — altså nøyaktig de radene som også står i `enheter` — og det egne merket
«Avventer: Lege 02» sto ved siden av hennes egen brikke. Avventingen er nå et merke **på**
brikken (`enhetAvventer()`), og samme form i hendelsens oppdragsoversikt. **Og «Avvent»
tilbys ikke på en som alt avventer:** raden blir stående i `Venter`, så serveren tok imot
trykk nummer to og skrev en `Enhetshendelse` til — enheten kom da to ganger i tidslinjen.

**Bug: tidslinjen kalte avvent «Tatt av»** (`#oppdrag/sentralbord`). Grenen var en ternær
som endte på «Tatt av», så *alt* som ikke var avbrutt eller rykket videre ble til «Tatt
av». `enhetshendelseTekst()` har nå ett ord per type og **ingen «ellers»** — en ny type i
`Enhetshendelse` skal se rar ut, ikke lyve.

**Enhetshendelsene henges på hendelsen oppdraget hører til** (`#ko/loggen`). «Det må
logges i oppdrags tidslinjen at en enhet blir satt på avvent — det må og komme opp i
hendelsens logg.» Uten `hendelse` havnet linja bare i vaktas logg, og `koIStrommen()`
holder enhetslinjer ute av loggstrømmen — så den som satt i H6 så ingenting av at
Mannskapsbil 1 avventet H6s eget oppdrag. Alle fire typene henges på, ikke bare
avventingen: «tatt av» på et oppdrag i H6 er like mye H6s situasjon, og en logg med den
ene og ikke de andre leser som et hull.

**«Fra» i «Flytt oppdrag» viste biler som ikke har oppdraget.** Koblingsraden blir stående
når en bil melder seg `Ledig` — stemplene hennes skal bevares — og hun sto derfor igjen i
«Fra» på et oppdrag hun var ferdig med. På et oppdrag som har gått gjennom to biler så
lista ut som hele flåten. `flyttFraEnheter()` tar bare rader som ikke er `Ledig`; er ingen
igjen, står det at veien videre er «Legg til» i stedet for et nedtrekk som ikke virker.

**«Varsle enhet til» heter «Legg til».**

**Hendelsens oppdragsoversikt: én brikke per enhet, med status og tid.** «Det må og stå
tidspunkt for nåværende status … må og skille mellom flere enheters ulike statuser.» Sto
som ett navnedrag med *oppdragets* utledede status, og da var «Ambulanse 1, Lag 3 · Fremme»
usant for begge. **`varslet_at` teller når hun ikke har stemplet ennå:** en enhet i
«Venter» har ingen `Statusmelding`, og feltet sto tomt på nøyaktig den raden man lurer på —
hvor lenge har hun visst om dette uten å rykke ut? «Trenger ressurs» står nå *foran*
enhetene i stedet for i stedet for dem: begge kan være sanne samtidig.

Mutanter: 28 skrevet, 28 drept — én overlevende underveis (`koLesLoggfilter` uten
validering av lagret verdi) ble tettet med en test på en ukjent lagret verdi.

Verifisert i Playwright mot seed: avvent på O4 (H6) gir én brikke, «Avventer: Mannskapsbil
1» i tidslinjen og «Mannskapsbil 1 avventer O4» i H6s logg; skjuling overlever reload og
det siste vinduet lar seg ikke skjule; filteret gir 12 + 6 = 18.

## 2026-09-21 — Hendelsen åpnes i loggstrømmens vindu, ikke over hendelsesloggen  `#ko/hendelseslogg`

André, 21. sep. 2026: «når vi åpner en hendelse så skal det vises i loggstrømmens vindu og
ikke i hendelsesloggens vindu, for det er viktig å ha oversikten i hendelsesloggen foran
loggstrømmen.» Variant A av to skisser, uten bånd om at strømmen går i bakgrunnen.

- **`#ko-hendelse-detalj` bor i loggseksjonen** i malen; ingen ny CSS. `koTegnHendelser()`
  tegner lista alltid, med den åpne raden merket (`h-apen`), og kaller så `koTegnDetalj()`
  eller `koVisStrommen(true)`. `koVisStrommen(vis)` er den ene bryteren: detaljen mot
  strømlista og skrivefeltet — og feltet vises bare igjen for den som kan skrive, ellers
  hadde `les` fått det tilbake etter første hendelse.
- **Raden vipper** (`koVippHendelse`): samme rad igjen lukker, en annen rad bytter direkte.
  H-merkene i strømmen og på lagkortene bruker fortsatt `koApneHendelse` og bare åpner —
  et H5-merke i en logglinje skal ikke lukke H5 fordi den sto oppe.
- **Loggvinduets hode** sier `· H5 · Bevisstløs person` mens hendelsen er åpen, ellers
  `· 18 linjer` (`koLoggHodeTekst`, kalt fra både `koTegnLogg` og bryteren). Tilbakeknappen
  heter «← Loggstrøm».
- **Smal skjerm** (< 1200 px, vinduene stablet): loggvinduet rulles inn i synsfeltet ved
  åpning (`koRullTilLoggvinduet`) — ellers så klikket ut som om det ikke gjorde noe.

Tester: `HendelsenILoggvinduetTests` i `ko/tests_js.py` kjører `koTegnDetalj()` for
alvor mot et DOM-stubb (`VINDU_DOM`). Mutanter 10/10 drept (vipp invertert, `les` får
feltet, lista ikke tegnet når åpen, hodet sier alltid linjer, detaljen skjuler ikke
strømmen, borte hendelse gir ikke strømmen, ruller alltid, raden bare åpner, `h-apen`
borte, `koApneHendelse` tegner ikke). Playwright mot seed: kari åpner, bytter, lukker via
rad og knapp, skriver i tråden, poll mens åpen; ola (`les`) får ikke feltet tilbake; 900 px
ruller til loggvinduet.

## 2026-09-21 — Ferdige i historikken telles, og to filtre: «Oppdrag uten ressurs» og «Tildelt»  `#ko/sentralbordet` `#oppdrag/sentralbord`

André, 21. sep. 2026: «ferdige oppdrag som vises i historikk vises ikke som "ferdig" i
tallstatistikken», «litt dobbelt opp med ventende statistikk og knapp», flytt knappen til
venstre for «Nytt oppdrag», og en knapp til: «Tildelt».

- **Bug:** et ferdig oppdrag går til historikken av seg selv i `sett_status`, og lista
  `/oppdrag/api/oppdrag/` utelater historikken — så «ferdig» i oppdragslistas hode sto på
  null hele vakta. Svaret bærer nå `antall_i_historikk`, og tallet er med i ETag-en (et
  oppdrag som ryddes bort endrer ikke radene som står igjen). `koOppdragTelling(liste,
  iHistorikk)` legger det til; argumentet er et argument, ikke en global, så regelen lar
  seg kjøre i node.
- **Hodet teller aktive · ferdig.** «Ventende» er borte fra teksten; tallet står på
  knappen, ett sted.
- **To filtre, ett om gangen**, til venstre for «Nytt oppdrag»: «Oppdrag uten ressurs»
  (`trenger_ressurs`, het «Ventende») og «Tildelt» (en enhet varslet, ennå ikke rykket ut
  — samme betydning som «Tildelt» på enhetskortet). `koVippFilter(valg)` gjennom
  `data-arg`; `koOppdragTomMelding()` sier om lista er tom fordi filteret tok alt eller
  fordi tavla er tom.

**Første utgave ga 500 på lista** — «Kunne ikke hente lista — prøver igjen om 30
sekunder» på `/ko/`: tallet lå som en tuppel *inne i* radene ETag-en sorterer, og
`sorted()` sammenlignet tekstnøkkelen mot en tall-ID. Testen så det ikke, fordi tavla var
tom i begge kallene og det aldri ble sammenlignet noe. `etag_for(rader, ekstra=…)` legger
det som ikke er en rad ved siden av, og testen har en rad på tavla hele veien. Funnet av
Playwright mot seed, ikke av suiten.

**Og en test som var avhengig av klokka på veggen:** `test_tatt_av_med_staatid` (7b) lot
«nå» være `timezone.now()`, og et åpent intervall fra 20:00 i går løp inn i time 20 i dag
— timebolkene slår sammen dager, så tallet ble 3 etter kl. 20 og 2 før. Grønn hele
formiddagen, rød om kvelden. `oppdrag_stats(vakt, naa=…)` tar nå «nå» som argument, og
fiksturen setter det til 23:00. En Django-malkommentar `{# … #}` over to linjer ble
tegnet som tekst i oppdragslistas hode — den er énlinjes; `{% comment %}` for resten.

---

## 2026-09-21 — Statistikk pulje 7c: fanen «Bemanning» — belastning mot bemanning  `#statistikk/oppdragsfanen` `#statistikk/ko` `#vaktliste/belastning`

André: «gå videre på 7c». Fjerde kilde på `/statistikk/` (`vaktliste/statistikk.py`,
`statistikk-bemanning.js`, `_bemanning.html`), retningen `vaktliste` → `oppdrag`.

- **På vakt per klokketime**: personer, møtt, lag og enheter — vaktlistas skift lagt
  under trykket. **Personer, ikke skift**: én på to overlappende skift er én. Møtt telles
  fra møtt-tidspunktet. Enhetstimer og lagtimer er unionen av skiftene per ressurs.
- **Oppdrag per enhetstime** — det ene normaliserte tallet uten publikumstall.
- **Enhetsutnyttelse per bil**: bemannet tid, tid på oppdrag (varslet → ledig, pågående
  til nå), andel (kappet ved 100) og lengste sammenhengende ledigtid innenfor bemannet
  tid. **«Ukjent», ikke null**, for en bil som ikke er koblet til en ressurs i vaktlista.
- **Linjene i de to andre fanene**: enheter og lag på vakt over køen i oppdragsfanen,
  lag og personer over åpne hendelser i KO-fanen. `sikreBemanning()` henter én gang;
  fanene kaller den gjennom `_kallOppdrag()` og tegner på nytt når svaret kommer — uten
  tilgang står stolpene alene. `mkStabletChart` fikk `opts.linjer` på en høyre akse.

**Kilden krever `les_alle`, ikke `les`.** `les` i vaktlista er «sitt eget korps», og hele
bemanningen er ikke det. `BaseStatistikkHandler.nivaa` (standard `les`) er det nye
knappet; statistikkappen spør `har_tilgang(user, slug, h.nivaa)`. Svaret bærer aldri
personnavn — `GateTests` leser hele svaret.

**Funnet underveis:** `fmtMin()` skrev «2t 60m» for 179,9 minutter — timene ble regnet
av råtallet og minuttene av resten, avrundet hver for seg. Rundes nå til hele minutter
først (`FmtMinTests` i `statistikk/tests.py`). Og «Personer» i grafen sto på 30 med 15
personer: den talte skift. Og grafen «På vakt per klokketime» sto på 30 med 14: en
stablet y-akse stabler linjer også, så personer + møtt + lag lå oppå hverandre —
`mkStabletChart` stabler nå bare når det finnes stolper. 30 JS-filer.

Mutanter: **19/19 drept** i `union`, `lengste_hull`, `_timebolker`, per-time-tallene,
enhetstimer, utnyttelsen og gaten. Tre overlevde første runde: en no-op (`lengste_hull`
slo sammen intervaller kallet alt hadde slått sammen — nå bare sortert), et oppdrag
*etter* bemannet tid som ingen test hadde, og en median av to verdier som var lik
snittet. Playwright mot seed med koblede biler: fanen og linjene tegnes uten feil.

---

## 2026-09-21 — Statistikk pulje 7a: KO-fanen — hvem løste hendelsen, tid til første ressurs, stillhet  `#statistikk/ko` `#ko/hendelseslogg`

André: «Ansvarsområde er ikke viktig, trenger ikke per person og forventet publikum.
Trenger ikke sammenligning per nå.» Skissene S4 og S5 er bygget som fane «KO» på
`/statistikk/` (`ko/statistikk.py`, `statistikk-ko.js`, `_ko.html`), gatet på `les` i KO
som oppdragsfanen på oppdrag. Setningen øverst: tallene teller **hendelser**, ikke
pasienter.

- **Hvem løste hendelsen**: lukkede hendelser utenom Drift og Plassering i fire ruter —
  lag og oppdrag, bare lag, bare oppdrag, verken — per prioritet, med tida fra lag satt på
  til oppdrag laget. **Rød og Viktig lukket uten lag og uten oppdrag listes med navn**,
  tid, hvem som lukket og siste operatørlinje.
- **Tid til første ressurs** per prioritet: til oppdrag, til Rykker ut, til lag på, og det
  første av dem. Klokka starter når KO hørte om hendelsen. `alle` regnes av hendelsene.
- **Samtidighet** (åpne hendelser per klokketime, høyeste prioritet i fargen),
  **eskaleringer** fra → til med opp/ned og median tid etter opprettelse, gjenåpninger,
  varighet per prioritet med p90, fordeling per prioritet, lokasjon og melder.
- **Lag på hendelser**: lagtimer og hendelser per lag. **Lagene leses av systemlinjene**
  (`hendelse_lag_paa`/`_av`, laglista på `hendelse_opprettet`), ikke av `HendelseLag` —
  raden slettes ved tatt av. `HendelseLag.til` fra forslaget ble ikke lagt til.
- **Loggen**: linjer per time (operatør/system), rettinger med tid til retting,
  fjerninger, delte hendelseslinjer med tid til deling, KO-førte og forsinkede
  stemplinger, og **stillhet**: de tre lengste hullene uten operatørlinje mens noe sto
  åpent, med det som pågår nå.

Ingen arkiv for KO. `mkStabletChart` flyttet fra `statistikk-oppdrag.js` til `statistikk.js`
— KO-fanen tegner med den, og oppdragsfila lastes ikke uten oppdragstilgang.
`_kallOppdrag()` vokter begge de betinget lastede filene (navnet er historisk).
29 JS-filer. Testene i `ko/tests_statistikk.py` setter `registrert_at` på linjene — feltet
er `auto_now_add`, og tid til retting/deling regnes av det.

Mutanter: **24/24 drept** (én til var en no-op: `fjern()` tømmer teksten, så
fjernet-sjekken i «siste linje» var overflødig og er tatt bort). Seks overlevde første
runde: symmetriske tall (én KO-ført og én forsinket stempling), «høyeste prioritet» som
tilfeldigvis var den sist behandlede, oppdrag alltid etter laget, og kanten «lukket
nøyaktig på hel time» — den avslørte at `<=` talte time 22 for en hendelse lukket 22:00,
og er rettet til `<`. Playwright mot seed: fanen tegnes uten feil.

---

## 2026-09-21 — Statistikk pulje 7b: ventetida i to, køen, KO mot bilen, alle fem hastegradene  `#statistikk/oppdragsfanen` `#oppdrag/statusmaskin`

André valgte fra skissene: ventetida som **både** stolper og tabell, «hvem løste» som
tabell, navnet «Meldt hastegrad (KO) × bilens grovsortering». «Kjør på.»

**Oppdragsfanen har åtte nye blokker** (`docs/FORSLAG_KO_STATISTIKK.md` C1–C8):

- **Ventetida delt i to.** Dagens «ventetid» (opprettet → Rykker ut) blandet KOs tid og
  bilens. Nå: **KO-ventetid** = uten ressurs → enhet varslet, **reaksjonstid** = varslet →
  Rykker ut, begge median/p90 per hastegrad, reaksjonstid også per enhet; passiv vakt for
  seg. «Uten ressurs» starter ved opprettelsen og ved hver avgang (avbrutt, rykket videre,
  avventer) som etterlot oppdraget alene — samme spørsmål som `trenger_ny_ressurs` stiller
  live, stilt i ettertid på radene (`_andre_aktive`). Slutter ved neste varsling **eller**
  neste Rykker ut: den som avventet kan ombestemme seg. Åpne intervaller telles ikke i
  ventetida (ikke målt ennå), men i køen.
- **Køen per klokketime**: uten ressurs og tildelt-men-venter som stablede stolper, med
  lengste ståtid over. Kort for lengste uten ressurs og flest i kø samtidig.
- **Tildelt, men rykket aldri ut**: tatt av (med ståtid) og meldt ledig fra Venter.
- **Meldt hastegrad × bilens grovsortering** med enige / bilen høyere / bilen lavere;
  Drift og Plassering utenfor. **Avreist til** per sted og sted × hastegrad, med «Annet
  sted»-tekstene (bare live). **Utfall per problemstilling** (behandlet/utført,
  transportert, verken — er én bil avreist, er pasienten transportert). **Enhetshendelser
  per enhet.**
- **p90** i alle varighetstabellene (`_sd`, nærmeste rang). **Alle fem hastegradene** i
  AMK-rekkefølge i smultringen og tabellene, også på null; «Plassering» har fått lilla —
  den falt til grå.

**Arkivet følger med** (`oppdrag/0030`): `ArkivertOppdrag` fryser `varslet_at`,
`grovsortering`, `avreist_til` og oppdragets `enhetshendelser` (JSON, gjentatt per rad
som hastegraden — en enhet som ble tatt av har ingen rad). I SHA-payloaden **bare når
satt**, som `varslet_modus`; eldre arkiv verifiserer uendret. `sted_tekst` fryses ikke
(fritekst). Et åpent intervall i et arkiv slutter ved `importert_at`, ikke ved nå.
**`Enhetshendelse.varslet_at`** settes for alle fire typene: koblingsraden slettes ved
tatt av, og med den forsvant «hvor lenge sto hun bundet».

**Fiksturen bar ikke prod-formen.** `Oppdrag.save()` lager koblingsraden med
`varslet_at=now`, og testene skrudde `created_at` tilbake — så hver reaksjonstid var
negativ og hver KO-ventetid en time. `_oppdrag()`-hjelperne i `tests_statistikk`,
`tests_arkiv` og den nye `tests_statistikk_7b` setter nå `varslet_at` = opprettelsen.
Spørringsbudsjettet for oppdragsfanen er 7, ikke 6 (én prefetch til), og
`tests_flere_enheter` ventet `{'Akutt': 1}` alene — nå står de fire andre der på null.

Mutanter: **24/24 drept** i `_ventetid_og_koe`, `_andre_aktive`, `_konkordans`,
`_utfall_per_problemstilling`, `_avreist_til`, `_i_hastegradrekkefolge`, `_p90`, arkivets
payload og `services` — fire overlevde første runde og avslørte fire svake tester:
symmetriske tall i konkordansen (1 og 1 lot høyere/lavere bytte), ingen rad med både
behandlet og avreist, «nå» som var lik `importert_at` innenfor avrundingen, og kanten
«en annen meldte ledig i samme øyeblikk». Playwright mot seed: fanen tegnes uten feil.

---

## 2026-09-21 — Forslag: statistikk fra KO (pulje 7)  `#ko/hendelseslogg` `#statistikk/ko` `#statistikk/oppdragsfanen`

André: «Ut ifra alt vi genererer av data i /ko, hva er interessant å få hentet ut?»
`docs/FORSLAG_KO_STATISTIKK.md`, kontrollert mot koden: hva som finnes av felt og
systemlinjer, hva oppdragsfanen alt regner, og 26 tall i fire lag — hendelsesbildet, loggen,
oppdragsfanen utvidet, belastning mot bemanning — med hvilke felt hvert tall regnes av. Med
p90 framfor snitt, krysstabeller der to vurderinger møtes, og §8-regelen om at registrene
teller kontakter og ikke personer. To hull sagt på forhånd: `HendelseLag` mangler `til`
(loggen bærer det), og enhet på/av vakt er ikke tidsstemplet. Ingenting bygget.

Samme dag, tre vinklinger fra André: **ventetida deles i KO-ventetid og reaksjonstid**
(uten ressurs → varslet, varslet → Rykker ut), en kø-kurve for «trenger ressurs» og «tildelt
men venter», hendelser løst av *lag alene / oppdrag alene / verken* uten Drift og Plassering
(A5, C4–C4c), og **«det mangler en hastegrad»** i oppdragsfanen: fargekartet i
`statistikk-oppdrag.js` kjenner fire, «Plassering» faller til grå, og smultringen sorteres på
antall, ikke i AMK-rekkefølge (C8, først i 7b).

---

## 2026-09-19 — «Utført» på drift, skjemaet som hoppet ut, fritekst ved «Annet sted», to kolonner, «Ventende»  `#oppdrag/enhetsskjerm` `#oppdrag/sentralbord` `#oppdrag/statusmaskin` `#ko/ressursbildet` `#ko/sentralbordet`

André, 19. sep. 2026, fem punkter.

- **«Utført» i stedet for «Behandlet på sted» på Drift og Plassering.** Statusen i basen er
  fortsatt `behandlet`; ordet byttes ett sted, `choices.status_navn_for(hastegrad, status)`,
  og leses av bilens knapp (`alternativ_for(fra, hastegrad)`), meldingen, tidslinja,
  enhetskortet og KO-loggens statuslinje. Bilens offline-projeksjon har samme regel.
- **«Ved nytt oppdrag så hoppes det av og til ut av skjema».** Årsaken: pollingen bygde om
  nedtrekkene og avkryssingen med `innerHTML` hvert 10.–30. sekund — et åpent nedtrekk
  lukkes av det, og et element man er i ferd med å trykke på byttes ut. `fyllNedtrekk`
  venter nå til neste poll når fokus står i det viste skjemaet (`skjemaErIBruk`), og rører
  ikke markup som er uendret. `koFyllHendelsevalg` («Hendelse» i skjemaet) gjør det samme.
- **Fritekst ved «Avreist → Annet sted».** Bilen får ett felt og én knapp i stedet for de
  seks (`stempleAnnetSted`), teksten følger raden gjennom offline-køen og sendes som
  `sted_tekst` i kroppen — det ene domenefeltet i det lukkede skjemaet
  (`STEMPLING_TILLATTE_NOKLER`), lest bare når stedet er `annet`, kappet til 120 tegn.
  `Statusmelding.sted_tekst` (`0029`); korreksjoner arver den; aldri verdilogget i audit
  (`FELT_UTEN_VERDILOGGING`). Vises som «Annet sted: Legevakt Karmøy» i tidslinja, på tavla
  og på enhetskortet. Sentralbordets føring har fått samme felt.
- **To kolonner i ressursoversikten.** Kolonneknappen i hodet, huskes per nettleser
  (`ko.ressurskolonner`). CSS-kolonner, og hver gruppe er en blokk med
  `break-inside: avoid` — «en gruppe som mannskapsbil skal ikke begynne i kolonne 1 og så
  gå over i kolonne 2». Blokkene tegnes av `tegnEnhetsliste` og `koTegnRessurser`.
- **«Ventende» i oppdragslista.** Hodet teller «aktive · ventende · ferdig», der ventende
  er oppdrag uten ressurs, og knappen «Ventende» filtrerer lista til dem
  (`koOppdragFilter`, gjennom en vakt i `renderOppdrag` — på `/oppdrag/` finnes ikke
  filteret). Ikke husket: et filter som overlever en refresh er et filter man glemmer.

Mutasjonstesting, 20 mutanter, 20 drept etter to runder: `status_navn_for` på alt
behandlet, `alternativ_for` uten hastegrad, KO-loggen fra `STATUS_NAVN`, teksten lagret
uansett sted (overlevde først — API-et vasket før tjenesten; testet i tjenesten nå),
korreksjonen mister teksten, `_sted_tekst` leser ikke kroppen, `sted_navn_for` uten tekst,
verdilogging, føringen uten tekst, `skjemaErIBruk` alltid false, ombygging uansett,
hendelsevalget under fokus, tellingen, filteret slipper alt, `renderOppdrag` uten filter,
kolonner ikke husket, gruppene uten blokk, «Annet sted» stempler rett (overlevde først),
køen mister teksten, projeksjonen uten «Utført» (overlevde først).

---

## 2026-09-19 — Testsjekklister for `/ko` og `/vaktliste`  `#ko` `#vaktliste` `#dokumentasjon`

André, 19. sep. 2026: «Kan du lage to sjekklister for testing av appen? En for /ko og en
for /vaktliste?»

- **`docs/TESTSJEKKLISTE_KO.md`** og **`docs/TESTSJEKKLISTE_VAKTLISTE.md`** — manuelle
  gjennomganger for staging, etter deploy, og før vakt. Begge er skrevet mot koden i samme
  økt (`ko/views.py`, `ko/services.py`, `ko/models.py`, `vaktliste/services.py`, malene og
  JS-filene), ikke mot hukommelsen: prioritetsrekka i KO er de seks som faktisk finnes
  (Viktig, Rød, Gul, Grønn, Drift, **Plassering** — modulfila sier fortsatt fem),
  meldervalgene er `MELDER_VALG`, stemplingsreglene er `services.STEMPLINGER`, og
  fanerekkefølgen i vaktlista er den `tegnFaner()` bygger.
- **Kontooppsett først, ikke til slutt.** Begge listene begynner med en tabell over
  testkontoer per nivå, fordi **fravær av rad er ingen tilgang** og global admin får toppen
  av stigen uten rader: en gjennomgang gjort med admin prøver nøyaktig den ene brukeren som
  aldri møter en sperre. Vaktlistelista har seks kontoer, blant dem korps-føreren **uten
  badge** — synligheten følger ikke stigen (`skriv_handling` ser alle korps, `les` bare
  sitt eget).
- **Hvert nivå prøves to ganger:** at knappen er borte, **og** at endepunktet svarer 403.
  En knapp som fører til en vegg er verre enn ingen knapp, og en vegg uten knapp er ikke
  det samme som en gate som virker.
- **Egen seksjon for regresjoner som har truffet prod.** `[object Object]` i en
  mal-streng, nedtrekket som lagret på klikk (`data-hendelse`), `readonly` uten virkning på
  `datetime-local` i Safari, 403 på en merknad korps-føreren har lov til å skrive,
  nattevakter på feil dag, «Mitt korps» inne i gruppefanene, planleggerfelter som ble
  blanke. Alle er billige å prøve og dyre å oppdage på vakt.
- **Ett funn av å lese framfor å huske: «tidligere vakters logg» har ingen flate.**
  Nivået `skriv_leder` er deklarert for den i `ko/module.py`, men `logg_view` svarer bare
  for aktiv vakt, og «Historikk»-knappen i KOs oppdragsliste er **oppdragsarkivet** —
  gatet av oppdragstilgang, ikke av KO-nivået. Sjekklista sier det rett ut, så ingen
  melder et manglende vaktvelger-nedtrekk som en feil.
- **Listene sier hva de ikke er.** Reglene er prøvd i suiten, med mutanter; finner noen et
  funn her som suiten burde ha tatt, er det to funn — feilen, og hullet i dekningen.
- **Begge er ført opp i `DOKUMENTER` i `core/tests_dokumentråte.py`.** En sjekkliste som
  peker på en fil eller en knapp som er flyttet, blir stille hoppet over av den som leser
  den under tidspress — og det er den sorten dokument som råtner uten at noen gjør noe
  galt. `TODO.md` har gjennomkjøringen som to åpne punkter, med iPhone/iPad nevnt for
  låsepunktene i vaktlistelista.

Ingen kodeendring, og derfor ingen mutanter: laget er «CSS, maler og tekster» i tabellen i
`CLAUDE.md`, der øyet er raskere enn en mutant. Det ene som er kode — de to radene i
`DOKUMENTER` — er kontrollert ved å kjøre `core.tests_dokumentråte` med en oppdiktet
filsti i hver av de nye filene og se at den blir rød.

---

## 2026-09-19 — Oppdrag uten enhet, «Tildelt», «Ikke aktuelt», «Plassering», fargeforklaring i ressursoversikten  `#oppdrag/sentralbord` `#oppdrag/statusmaskin` `#oppdrag/enhetsskjerm` `#ko/ressursbildet` `#ko/hendelseslogg`

André, 19. sep. 2026, fire punkter med skisser først (A1/A2, B, C, D, E1 — alle valgt).

- **Å opprette oppdrag behøver ikke en ressurs.** `Oppdrag.enhet` er nullbar
  (`oppdrag/0028`); `enhet_ider: []` oppretter oppdraget med `trenger_ressurs` satt fra
  første sekund, og tavla viser det med samme merke og opptrapping (0/5/15 min) som når en
  bil rykket videre — mekanismen fantes, bare inngangen er ny. Ingen lyd: «lyd skal bare
  komme til enheter», og ingen er varslet. Knappen i «Nytt oppdrag» skifter til «Opprett
  uten enhet» med et varsel når ingen er krysset av (`utenEnhetValgt`,
  `oppdaterOpprettKnapp`), så det ikke skjer ved et uhell. Den første som varsles blir
  primær og fyller kolonnen (`varsle_enhet`). En kropp helt uten enhetsfelt er fortsatt
  400 — en gammel klient som glemte feltet skal ikke stille få et oppdrag uten bil.
  Arkivet gir én rad med tomt enhetsnavn i stedet for ingen. Merket heter nå «Trenger
  ressurs» (var «Trenger ny ressurs»); i hendelsens oppdragsliste står det samme merket.
- **Ledig → Tildelt.** En enhet uten påbegynt oppdrag, men med ett som venter, vises som
  «Tildelt 16:02 · 2 min» (`tildelt_siden` fra første varsling) i stedet for «Ledig · 1
  venter». Visning, ikke status: `services.TILDELT` finnes ikke i statusmaskinen, og
  koblingsradene står i Venter. Passiv vakt vises som før (avtalt). Prikken er en **hul
  grønn ring** — paletten er brukt opp (Fremme blå, Behandlet grønn), og formen skiller
  seg for den som ser dårlig forskjell på nyanser. «N ledig» i vinduets hode teller ikke
  tildelte.
- **Grovsortering «Ikke aktuelt»** (`ikke_aktuelt`, grått) — teller som satt der
  grovsortering kreves. Feltet vidåpnet fra 8 til 16 tegn.
- **«Plassering»** som prioritet i KO (etter Drift, lilla, `ko/0012`) **og** som hastegrad
  i oppdragsmodulen med samme navn, så «Nytt oppdrag» arver den likt. Uten pasient som
  Drift: driftens problemstillinger, aldri grovsortering. `choices.UTEN_PASIENT` er navnet
  på regelen — den sto som `== DRIFT` seks steder.
- **Fargeforklaring i ressursoversikten** (variant E1): «i» i hodet folder ut en stripe
  med alle prikkene, trekanten, «passiv vakt» og «På H14»; valget huskes per nettleser
  (`ko.legende`), av som standard.
- **Sentralbordet på `/oppdrag/`** står — «avvente inntil videre» — kartlagt i TODO under
  KO-modulen.

Mutasjonstesting, 17 mutanter, 17 drept etter to runder: Tildelt på passiv vakt og med
påbegynt, flagget ved opprettelse, `varsle_enhet` fyller kolonnen, manglende felt = ingen
enhet, `passer` og `grov_kreves_for` bare Drift, grovraden og grovmerket på Plassering,
`utenEnhetValgt`, legenden tegnes ikke / på som standard, hendelsesraden uten merke, kortet
uten `tildelt_siden`, tom brikke uten enhet, arkivet mister oppdraget, Plassering før
Drift. Én overlevde første runde: `_kanGrovsortere` var bare prøvd med Drift.

---

## 2026-09-19 — KO: bare lag på vakt nå i ressursoversikten og lagvelgeren; sted på kortene  `#ko/ressursbildet` `#ko/hendelseslogg` `#vaktliste/roller` `#oppdrag/sentralbord`

André, 19. sep. 2026: «bug: lag vises i ressursoversikt og i ny hendelse over lag selv om de
ikke er på vakt enda, det er viktig at det er bare de som er på vakt nå som vises av lag.
Enheter som er koblet til oppdrag må manuelt skrus av og på av ko som før.» Og: «I
ressursoversikt er det ønskelig at lokasjon vises.»

- **Bare lag med et skift som dekker nå.** `vaktliste.services.ressurser_paa_vakt_naa()`
  er regelen — et skift med mannskap, ikke avmeldt, `fra_tid ≤ nå ≤ til_tid` — og den har
  to lesere: `ressurser_uten_enhet()` (kortene) og `ko.services.lag_som_kan_velges()`
  (lagvelgeren i «Ny hendelse» og «Legg til lag»). «På vakt» er vaktlistas eget begrep, ikke
  om laget har *møtt*: et lag med skift nå og ingen møtt står som «0 av 2 møtt». Et lag hvis
  skift starter senere vises ikke lenger som «ubemannet» med «neste»; `neste`/`neste_fra`
  er ute av svaret og av `koRessursMannskap`. Bilene røres ikke — `pa_vakt` settes av KO
  som før.
- **Et lag som står på hendelsen får bli når skiftet går ut.** Skjemaet og brikkene sender
  hele lista, og uten unntaket kunne lista ikke lagres: `lag_som_kan_velges(vakt, hendelse)`
  tar med det som alt står der. Å *legge til* et lag uten skift avvises fortsatt.
- **Sted på kortene.** Bilens kort viser oppdragets lokasjon etter problemstillingen
  (`lokasjon_navn` i `enhetskort`, i ETag-en fordi «Rediger oppdrag» flytter uten å røre
  status), på `/oppdrag/` og `/ko/`. Lagets kort viser hendelsens sted: «På H14 · Hovedscene
  · 23 min».

Mutasjonstesting, 8 mutanter, 8 drept etter to runder: skiftet som gikk ut, avmeldte,
laget som står der, alle lag når hendelsen er oppgitt, opprett uten skiftsjekk, `koLagPaa`
og kortet uten sted, ETag uten lokasjon (overlevde først — ingen test flyttet et oppdrag;
`test_etag_endres_naar_oppdragets_lokasjon_endres` finnes nå).

---

## 2026-09-19 — KO: «Logg i hendelse» med deling til enhetene, oppdragsnotat, hastegrad arver prioriteten, gult minutt i bilen, hvit «Fra»-tekst  `#ko/hendelseslogg` `#ko/loggen` `#oppdrag/sentralbord` `#oppdrag/enhetsskjerm`

André, 19. sep. 2026: «inne i hendelsen så endrer vi beskrivelses loggen og løpende loggen
om til en "Logg i hendelse" … det skal kunne sendes internt som vil si ikke til ressurser
som standard. Men meldinger kan ettersendes til ressurs, alle som har oppdrag fra
hendelsen. Individuelle settes inne i oppdraget.» Og: «Deling skal angres. Og alt som er
delt skal deles med alle fremtidige og pågående oppdrag.»

- **Én logg i hendelsen.** «Beskrivelse» og «Løpende» er slått sammen til «Logg i
  hendelse», med skrivelinja fra «Løpende». Beskrivelsen fra «Ny hendelse» er den første
  linja i loggen — `Logglinje.beskrivelse` (tillegg-merket fra tidligere i dag) er borte
  (`ko/0011`), og `legg_til_beskrivelse`, tilleggsskjemaene og `koTilleggSubmit` med den.
  Rediger/fjern står som før på hver linje.
- **Intern til den deles.** En linje er KOs arbeidsnotat til noen trykker «Del».
  `del_linje(linje)` setter `delt_at`/`delt_av` på linja: delt med **alle oppdrag i
  hendelsen, nå og senere** — et oppdrag som opprettes etter delingen ser den også.
  «Del med \<enhet\>» inne i oppdraget gir `ko.Linjedeling(linje, oppdrag)` — bare det
  ene. Begge angres (`angre_deling`); å angre enkeltdelingen på en linje som er delt med
  alle avvises med beskjed om hvor den angres. Delte linjer får merket **«Delt»** i
  hendelsen (eller «Delt · O47» når de er delt enkeltvis); i oppdragets detaljvisning står
  det ingen merker (bilde 3 er fasit), bare «alle» / «Angre» / «Del med Mannskapsbil 2».
  Systemlinjer, fjernede og rettede linjer deles ikke; en retting arver delingen og
  enkeltdelingene. Deling er en tilstand, ikke en hendelse — ingen systemlinje.
- **Én leser:** `Hendelse.delte_linjer_for(oppdrag)` gir oppdragsmodulen og bilen det
  som er delt (`delte_linjer` i `oppdrag_til_dict`, erstatter `hendelse_beskrivelse`),
  skjult for terminal bil som friteksten. ETag-en bærer `(id, delt_at)` — en linje som
  angres og deles på nytt har samme id. KO-klienten får tilstanden hel med hver poll
  (`delte`, som `fjernede`/`festede`): det som ikke står i lista er intern.
- **Bilen: «Fra loggen i H14»**, og hver delt linje står **gul i ett minutt** fra
  delingen (`erNyDelt`, `.b-tillegg.ny`). `lastMine` tegner på nytt ved 304 så lenge noe
  er gult, ellers hadde det gule stått til neste endring på serveren. Det gule «NYTT» i
  KO er borte (`koErNytt`).
- **«Nytt oppdrag» arver hendelsen.** Hastegraden settes av prioriteten (Viktig→Akutt,
  Rød→Akutt, Gul→Haster, Grønn→Vanlig, Drift→Drift, `koHastegradForHendelse`) og
  oppdragsnotatet av den første linja i loggen — begge kan endres. Arven kjører **bare når
  valget faktisk byttet**: nedtrekket fylles på nytt ved hver poll, og uten sperren ville
  operatørens hastegrad blitt satt tilbake hvert 15. sekund. Notatet overskrives bare når
  det er tomt eller er det forrige arvede. **Uten hendelse er ingen hastegrad valgt**
  (tomt valg først i nedtrekket, «Velg hastegrad først» i problemstillingene, «Velg
  hastegrad.» ved knappen); «Rediger» tilbyr ikke det tomme valget.
- **Fritekst heter Oppdragsnotat** — i «Nytt oppdrag», i «Rediger» og i hjelpeteksten.
  «Bare dette oppdraget» er borte.
- **Bug: hvit tekst ved «Fra»/«Til» i «Flytt oppdraget til en annen enhet».** Bootstraps
  `.input-group-text` har lys bakgrunn og mørk tekst som standard; `oppdrag.css` gir den
  kortets farger (`style.css` hadde alt regelen for pasientsiden).
- **Backup:** `Linjedeling` er ekskludert — den peker på et oppdrag, og oppdragene
  gjenopprettes *etter* KO; `delt_av` strippes som de andre brukerpekerne; filer fra
  timene med `logglinje.beskrivelse` lastes fortsatt (`UTGAATTE_FELT`).
- 161 endepunkter (23 under `/ko/`: `logg/<pk>/del/`, `logg/<pk>/angre-deling/`).

Mutasjonstesting, 26 mutanter, 26 drept etter to runder: tjenestelaget (sperrene i
`_kan_deles`, hendelsesjekken, idempotens, «angre enkelt når delt med alle», «angre alle
lar enkeltdelingene stå», rettingen arver `delt_at` og delingene, filtrene i
`delte_linjer_for`), portene (nivået på del-viewet, `delte` i pollen, bilen etter
avslutning, `delt_at` i ETag-en, `Linjedeling` i backupen) og JS (arven ved hver poll,
tabellen Rød→Akutt, `<` mot `<=` i det gule minuttet, 304-tegningen, `koTaImotDelte`
nullstiller, systemlinjer og fjernede ute av «Fra loggen» og søket, Del-knappen for `les`,
hastegradsjekken i `opprettOppdrag`). To overlevde første runde og sa noe om testene, ikke
koden: Rød→Akutt overlevde fordi testen hadde skrevet tabellen av i sin egen preamble — den
står nå inne i funksjonen; hastegradsjekken fordi ingen test gikk gjennom `opprettOppdrag`.
Ikke prøvd: `kilde=KILDE_OPERATOR` i `delte_linjer_for` (en systemlinje får aldri `delt_at`,
så mutanten er en no-op) og `linje__hendelse=self` på enkeltdelingene (samme grunn:
`_oppdrag_i_hendelsen` sperrer ved opprettelse).

---

## 2026-09-19 — KO: rediger/fjern inne i hendelsen, lagvelger uten forhåndsvalg, skrivefeltet overlever pollen, oppdragsstemplene ut av strømmen, lukk går til lista  `#ko/hendelseslogg` `#ko/loggen`

André, 19. sep. 2026, fem punkter etter testing på staging.

- **Rediger og fjern inne i hendelsen.** Tilleggene i beskrivelsen og kommentarene i
  «Løpende» hadde ingen knapper — bare strømmen hadde. Nå har hver linje i hendelsen
  rediger (`skriv_full`) og fjern (`skriv_leder`), samme handlinger som i strømmen
  (`koRettFjernKnapper`); fest og «lag hendelse» tilbys ikke der, en linje i hendelsen er
  alt i en. Systemlinjer rettes fortsatt ikke. `koRett` henter loggen på nytt etterpå, så
  det rettede tillegget kommer fra serveren som resten av beskrivelsen.
- **Lagvelgeren** i hendelsen sto på det første laget — «Legg til» kunne registrere et lag
  ingen hadde valgt. Første valg er nå ledeteksten «Legg til lag …», og knappen heter
  «Legg til». Uten valg skjer ingenting.
- **Operatøren datt ut av skrivefeltet.** Hendelsen tegnes på nytt ved hver poll, og
  `innerHTML` kastet feltene med det man hadde skrevet. `koBevarFelter()` tar vare på
  verdi, markør og fokus i skrivefeltet, tidsfeltet, tilleggsfeltet, lagvelgeren og
  knytt-velgeren før tegningen, og setter dem tilbake etter.
- **Oppdragenes stempler er ute av loggstrømmen**, og «System»-bryteren gikk ut med dem.
  Strømmen viser operatørlinjer uten hendelse og systemlinjene *om* hendelsene
  (opprettet, lukket, prioritet, lag, knyttet). Stemplene står på tavla, i oppdraget og i
  loggen for utskriften — de er ikke slettet, bare ikke i strømmen (`koIStrommen`).
- **«Lukk hendelse» går tilbake til hendelsesloggen.**

Reglene er prøvd i node: strømfilteret for fem oppdragskoder med og uten hendelse,
knappene per nivå (les/skriv_full/skriv_leder) på tillegg, kommentar og systemlinje,
lagvelgerens ledetekst, og at feltet får verdi, markør og fokus tilbake.

---

## 2026-09-19 — KO: «Vis lukkede» huskes og er av som standard; lukkede hendelser grået ut  `#ko/hendelseslogg`

André: «Når en refresher siden vises også avsluttede hendelser. Selv om vis lukkede er trykt
av. Kan og vær nyttig at lukkede hendelsers linjer er mer tydelig lukket, grået ut.»

- Bryteren sto som `checked` i markupen og `true` i JS, og valget ble ikke lagret — hver
  refresh startet på «vis». Nå huskes det per nettleser (`ko.vis_lukkede`, som oppsettet),
  og **standarden er av**: tallet i vinduets hode («· 4 åpne · 2 lukket») sier at de
  finnes, og en lukket hendelse i lista er støy for den som sitter med samband.
- Lukkede rader: grå venstrekant uansett prioritet (ingen rød ramme for en lukket Viktig),
  dempet (55 %), gjennomstreket tittel, prioritetsikonet borte, merkene i gråtoner. Hodet
  på en åpnet lukket hendelse er grået ut på samme måte.

---

## 2026-09-19 — Bugs: «Flytt» ga den nye bilen den gamles status, skjemaer husket avviste forsøk, Lagre/Avbryt i feil rekkefølge  `#oppdrag/statusmaskin` `#oppdrag/sentralbord` `#vaktliste/roller`

André, 19. sep. 2026: «Setter oppdrag til f.eks. Sandnes 56, de endrer status til Rykker ut.
Tar Sandnes 56 av oppdrag og endrer til Haugesund 56. Da er status til Hgsd også Rykker ut.
Det blir misvisende da det ikke er den enheten som har satt statusen.» «Hvis man lagrer et
skjema og får valideringsfeil, og så åpner det igjen så bør det nullstilles.» «Knappen for
lagre og avbryt er feil plassert … primær lagre-knapp helt til høyre.»

- **«Flytt til enhet» etter utrykning.** Ja, det var en feil — fra 11. sep. 2026, da statusen
  ble per enhet. `flytt_til_enhet` pekte koblingsraden om til den nye bilen med status og
  stempler intakt, så Haugesund 56 sto som «Rykker ut» med Sandnes 56 sine stempler i sin
  tidslinje. Nå: står raden i **Venter**, pekes den om som før (ingen stempler, ingenting
  blir feil eier). Har bilen **rykket ut**, får den nye sin egen rad i Venter og tar den
  gamles plass i rekka (primær), og den gamle meldes Ledig — automatisk, ikke stemplet —
  med stemplene sine i eget navn. Oppdragets status utledes til Venter: den nye bilen
  skal stemple utrykningen selv. Responstiden som ble målt står på den som kjørte den.
  `Enhetsbytte`-raden skrives som før. Testen `test_statusen_staar_ved_bytte` («en
  responstid som faktisk ble målt skal ikke nullstilles») låste den gamle regelen; den er
  erstattet — responstiden nullstilles fortsatt ikke, den flytter bare ikke over.
- **Skjemaer som husket et avvist forsøk.** Kartlagt modal for modal: de fleste fylles av
  JS før de vises og var riktige. Feilen lå i dem som åpnes med `data-bs-toggle` uten kode
  på åpningsveien: «Avslutt vakt» og «Lagre som arkiv» (pasientsiden), «Vaktarkiv» og
  «Historikk» (sentralbordet) — verdiene og feilmeldingen fra forrige forsøk sto igjen. Ny
  hjelper `nullstillModalVedLukking(modalId, felter, feilId)` i `portal-utils.js`
  nullstiller de navngitte feltene ved **lukking** (ikke åpning: `show.bs.modal` fyrer inne
  i `.show()`, og et skjema JS fyller rett før visning ville fått verdiene vasket bort).
  Bare navngitte felter — modaler med innstillinger hentet fra serveren (bilinnstillingene,
  timetak, grenser) blankes ikke, for en blank innstilling er ikke den lagrede. I tillegg
  fire enkeltfelter som manglet i sine åpningsfunksjoner: `n-helsepersonell` i «Ny
  pasient», `ny-ressurs-navn` i «Ny ressurs», `ny-vakt-kopier` i «Ny vaktliste», «ny verdi»
  i valglistene.
- **Funnet under kartleggingen:** `koNyttOppdragFraHendelse` satte stedet og hendelsen
  *før* `.show()`, og `nullstillNyttOppdrag` (på `show.bs.modal`) satte stedet tilbake til
  første valg etterpå — usynlig i demoen fordi Hovedscene tilfeldigvis var først. Fyller nå
  etter visning.
- **Lagre/Avbryt.** Enig: sekundær til venstre, primær helt til høyre, i nedre høyre hjørne.
  Rettet der de sto omvendt eller til venstre: «Rediger oppdrag», «Endre status» og «Rett
  tid» i detaljvinduet, navneredigeringen i vaktlista (`_redigeringsrad`) og verdiskjemaet
  under «Verdier». Modalfotene var alt riktige.

Mutasjoner mot `oppdrag.tests.EnhetsbytteTests` (4 s hver): alltid ompeking (gammel regel),
den gamle meldes ikke ledig, Ledig som stempel i stedet for automatisk, den nye tar ikke
plassen i rekka, primær følger ikke. **5 av 5 fanget.** `nullstillFelter` prøvd mot et
minimalt DOM (`core/tests_js_nullstill.py`); knappe-rekkefølgen er markup og prøves ikke.

---

## 2026-09-19 — KO/oppdrag: ingen forhåndsvalgt prioritet, hastegrad som knapper, «Flytt» viste enheter av vakt, beskrivelsen synlig i «Nytt oppdrag»  `#ko/hendelseslogg` `#oppdrag/sentralbord`

André, 19. sep. 2026, etter forrige pulje: «litt misvisende med forhåndsvalgt prioritet»;
«bytte nytt oppdrag fra select til lignende oppsett som ved prioritet»; «bug i redigering
av oppdrag hvor flytt til enhet viser alle enheter uavhengig om de er av eller ei … hvem er
fra og hvem er til?»; «viktig at inne i ny oppdrag at det kommer frem at beskrivelse fra
hendelse medfølger, og at i fritekst bare gjelder enheter knyttet til oppdraget».

- **«Ny hendelse» har ingen prioritet valgt på forhånd.** Skjemaet nekter å sende uten
  («Velg prioritet.», `koPrioritetValgt`). Serveren beholder Grønn som standard for et
  kall som utelater feltet — det er API-ets regel, og den var prøvd; skjemaet er det som
  var misvisende.
- **Hastegrad i «Nytt oppdrag» er knapper** — Akutt, Haster, Vanlig, Drift, oppdragets
  egne navn — i samme form som prioritetsknappene. Nedtrekket `#nytt-hastegrad` står igjen
  skjult som verdien: «Rediger» kopierer valgene derfra, og `hastegradEndret('nytt')`
  bytter problemstillingene som før; knappen setter nedtrekket og går den veien
  (`velgHastegrad`). Hastegraden er fortsatt forhåndsvalgt (Akutt) — problemstillingene
  avhenger av den, og lista ville stått tom til noen valgte. Si fra om den også skal stå
  åpen.
- **«Flytt» i detaljvinduet tilbød alle enheter**, også de av vakt — serveren avviste dem,
  så feilen var en 400 etter valget. Nå bare enheter **på vakt** som ikke alt står på
  oppdraget, samme utvalg som «Varsle enhet til» (`_flyttValg`). Og «Fra» / «Til» står
  skrevet: med én enhet på oppdraget vises den som tekst under «Fra», med flere som et
  nedtrekk. Hinten sier hva flytting gjør (enheten under «Fra» tas av, status står) og
  peker på «Varsle enhet til» for den som vil *legge til*. Uten kandidater står «ingen
  andre enheter på vakt», ingen knapp.
- **«Nytt oppdrag» viser beskrivelsen fra hendelsen** når en hendelse er valgt
  («Beskrivelse fra H14 — følger med til enhetene på oppdraget», lesevisning), og
  friteksten heter da **«Bare dette oppdraget»** med hinten «gjelder bare enhetene på dette
  oppdraget». Etiketten og hinten i den delte malbiten fikk id-er; KO bytter tekstene
  gjennom `koHendelsevalgEndret` og setter dem tilbake uten hendelse. På `/oppdrag/` står
  de som før.

Mutasjoner (3–8 s hver): `_flyttValg` × 3 (av vakt tilbys, enheten på oppdraget tilbys,
navnet rått), `velgHastegrad` uten `hastegradEndret`, knappene speiler ikke nedtrekket,
`koPrioritetValgt` alltid sant, etiketten byttes ikke, teksten i hendelsesinfoen rå.
**8 av 8 fanget.** Kallstedet for prioritetssperra i `koLagreHendelse` er ikke prøvd —
det er en DOM-handling uten harness, og sperra ble sett i nettleseren (Playwright).

---

## 2026-09-19 — KO: lag på hendelsen, beskrivelsen som tillegg, melder som avkryssing, besetning bak et klikk  `#ko/hendelseslogg` `#ko/ressursbildet` `#oppdrag/sentralbord` `#oppdrag/enhetsskjerm` `#vaktliste/roller`

André, 19. sep. 2026, etter fire skisser som ble avtalt før koden: «Det viktige er å vise om
laget er opptatt på hendelse … Husk at lag får ikke oppdrag, de får oppdrag muntlig
kommunisert på samband og blir registrert på hendelsen.» «Jeg elsker innspillet ditt med
eget for oppdrag.» «Ressursoversikten viser ikke besetning og telefon som standard, du må
trykke på ressursen for å se, da sparer vi plass.»

- **Lagene på hendelsen** er nå rader (`ko.HendelseLag`) som peker på vaktlistas ressurser
  uten oppdragsenhet — de samme som står som kort i ressursoversikten. Velges som
  avkryssing i «Ny hendelse» (med «på H13 · 18 min» som hint der laget er opptatt), og
  legges til / tas av inne i hendelsen som brikker med «siden 21:42 · 23 min». Hvert lag
  som kommer til eller går er en systemlinje (`HENDELSE_LAG_PAA`, `HENDELSE_LAG_AV`);
  ved opprettelse står lagene på opprettelseslinja. Lukket hendelse tar ikke imot.
  **Lagkortet viser «På H14 · 23 min»** ved å slå laget opp i de åpne hendelsene på
  klienten (`koLagPaa`) — ingen egen status, ingen ny poller. `Ressursbehov`-tabellen,
  fanen under KO-innstillinger og fritekstfeltet `lagsressurser` er borte
  (`ko/0008`–`0010`). Backupfiler fra 18. sep. bærer dem fortsatt: `core.backup` fikk
  `UTGAATTE_FELT`/`UTGAATTE_MODELLER` (søsteren til `GAMLE_MODELLNAVN`) som tar dem ut
  ved gjenoppretting, eksplisitt og ikke med `--ignorenonexistent`. `HendelseLag.ressurs`
  strippes som `Hendelse.lokasjon` (sirkel `ko` → `vaktliste` → `oppdrag` → `ko`);
  navnet fryses i `ressurs_navn`.
- **Beskrivelsen er tillegg, aldri overskriving.** Hvert tillegg er en logglinje i
  hendelsen med `Logglinje.beskrivelse=True`, så hvem og når står der av seg selv, og
  retting/fjerning går gjennom loggens regler. Samme rekke vises i hendelsen, i
  oppdragets detaljmodal («Beskrivelse H14», med skjema for å legge til på `/ko/`) og
  på bilens skjerm (`hendelse_beskrivelse` i `oppdrag_til_dict`, i ETag-en; utelatt for
  avsluttede oppdrag som friteksten). Nyeste tillegg er uthevet, og «nytt» står i ti
  minutter (`koErNytt`). Oppdragets fritekst heter **«Bare dette oppdraget»** når
  oppdraget hører til en hendelse. Det som sto i `Hendelse.beskrivelse` ble første
  tillegg (`ko/0009`), ført av den som opprettet.
- **Funnet under lesing, rettet:** `korriger()` kopierte ikke `hendelse` til den nye
  raden — **en rettet kommentar i H14 falt ut av hendelsen og inn i loggstrømmen.**
  Retting arver nå hendelsen og `beskrivelse`-merket.
- **Melder** er avkryssing: Egen ressurs, AMK, Brann, Politi, LSKO, Andre — fast liste i
  kode (`MELDER_VALG`), flere kan velges, «Andre» krever tekst og teksten tømmes uten
  «Andre». Lagres som `melder_typer` (JSON) + `melder`; et gammelt melder-navn ble
  «Andre» med teksten.
- **Ressursoversikten**: Alle | Biler | Lag i vinduets hode, husket per nettleser
  (`ko.ressursvisning`), det skjulte som et tall («4 biler skjult»). **Lagkortet åpner
  besetningen ved klikk** — navn, møtt (●/○), telefon som `tel:`-lenke, ISSI — én om
  gangen som bilens. `vaktliste.services.ressurser_uten_enhet` bærer derfor telefon og
  ISSI fra 19. sep.; det var utelatt med vilje 18. sep. («et nummer man ikke trenger er
  et nummer på en skjerm i et rom»), og holdes ved at tallene står bak klikket.
- 159 ruter, 21 under `/ko/` (`api/hendelser/<pk>/lag/` kom til, tre ressursbehov-ruter
  gikk). `ko/CLAUDE.md` og `TODO.md` (lagsstatus-punktet) oppdatert. Sjekket i
  nettleseren med seedet vakt (Playwright): hendelsen med brikker og tillegg, skjemaet,
  lagkortet klikket, Alle/Biler/Lag, oppdragets detaljmodal med «Beskrivelse H5» og
  «Bare dette oppdraget» — ingen JS-feil.

Mutasjoner, hver mot testene som dekker den (2–6 s per mutant): `rens_melder` × 3 (Andre
uten tekst, tekst uten Andre, ukjent kode), `sett_lag` × 3 (lukket tar imot, ingen
`HENDELSE_LAG_AV`, `bli_med` borte), `lag_som_kan_velges` uten `enhet__isnull`, `_lag_fra`
med ukjent id stille utelatt, `skriv_linje` tillegg uten hendelse, `korriger` × 2
(hendelsen og merket arves ikke), `beskrivelse_tillegg` × 2 (fjernede med, overstyrte ledd
med), `_tillegg_prefetch` uten `beskrivelse=True`, `opprett_hendelse` × 2 (lagene ikke på
linja, beskrivelsen ikke lagt til), `rediger_hendelse` med lag-endring ignorert,
`fjern_utgaatte` × 2, ETag uten tilleggene, `hendelse_lag_view` senket til `les`,
`for_enhet` viser beskrivelsen for avsluttede, vaktlista uten telefon, og JS: `koLagPaa`
med lukkede, `koErNytt` grensa snudd, `koSkjultTall` feil tall, `koLagBrikkeHtml` rått
navn, klikk-gaten på kortet borte, og **kallstedet** `koTaImotHendelser` →
`koTegnRessurser` fjernet. **29 av 29 fanget.**

---

## 2026-09-18 — KO-innstillinger: «Nullstill» og redigerbare ansvarsområder  `#ko/hendelseslogg` `#ko/loggen`

André: «Er det mulig å få til en nullstill knapp på oppdrag, hendelser og logg? Kan ha de
i KO-innstillinger. Samme med å redigere ansvarsområder. Admin er eneste som kan
nullstille. Det skal gå ann for test og utvikling. På prod så står admin ansvarlig for
databehandlingen.»

- **Nullstill**-fane i KO-innstillinger, bare for global admin: «Nullstill oppdragslista»,
  «Nullstill hendelsesloggen», «Nullstill loggstrømmen». Alle tre scopet til **aktiv vakt**,
  krever `confirm` server-side, og skriver én auditrad (`ko_nullstill_<hva>`) med antall
  og hvem. Oppdragene nullstilles av oppdragsmodulens egen `nullstill_vakt` — samme
  tømming som `arkiver_vakt(tomm=True)` gjør etter frysingen, bare uten frysingen; O- og
  H-serien starter på 1 igjen. Hendelser slettet: linjene og oppdragene står, uten
  H-merket (`SET_NULL`). Logg slettet: hendelsene står. Enheter, lokasjoner og valglister
  røres aldri. Sjekket først: «Slett alle i historikken» fantes (bare historikken), og
  vaktarkivet tømmer etter frysing — ingen av dem var «tøm uten spor», så inngangen er ny.
- **Ansvarsområder** er en liste (`ko.Ansvarsomraade`) under KO-innstillinger, ikke lenger
  tuppelen `ANSVARSOMRAADER` i kode. De fire gamle seedes av `ko/0007`. Merket på linjer og
  kontoer er fortsatt tekst — omdøping skriver ikke om loggen. «I bruk» = kontoer som bærer
  merket nå. Samme fabrikk som ressursbehovene i `ko/views.py` (`VERDILISTER`).
- Sentralbordets valgliste-JS fikk en generell krok til: en ekstra fane kan oppgi `tegn`
  (navnet på en global funksjon) og tegne seg selv, som «Bilen» — `koTegnNullstill()`.
- 161 ruter, 23 under `/ko/`.

Mutasjoner mot `ko.tests_nullstill` (2,6 s): scope fjernet fra hver av de tre
nullstillingene, telleren ikke slettet (O og H), admin-sjekken fjernet, `confirm` fjernet,
deaktivert område godtatt, ukjent område godtatt. **8 av 8 fanget.**

---

## 2026-09-18 — KO: fire flater i 2×2, hendelsesloggen som egen flate  `#ko/hendelseslogg` `#ko/oppsett` `#oppdrag/sentralbord` `#oppdrag/enhetsskjerm`

André, 18. sep. 2026: «Ko modulen skal ha 4 flater. Hendelseslogg, Loggstrøm,
Ressursoversikt og Oppdragsliste. Idag så er det uoversiktlig og meget basic.» Åtte skisser
ble laget og avtalt **før** koden («Nydelig design og oppsett. Akkurat slik jeg så det for
meg!»), og de er målet. Dette overstyrer «tre kolonner er taket» og «hendelser er en
gruppering av oppdragslista» fra 17.–18. sep.; prinsippet uten faner står.

### Det som er bygget

- **2×2-rutenett** (`static/js/ko-layout.js`, `ko.css`): Hendelseslogg │ Loggstrøm øverst,
  Ressursoversikt │ Oppdragsliste nederst. Håndtaket i hvert vindu dras over et annet for å
  **bytte plass**; skillelinjene endrer **bredde per rad og høyde** mellom radene. Rammen
  holder alle fire synlige — gulvet `KO_MIN_PROSENT` og `min-width`/`min-height` gjør det
  umulig å dra en flate bort. Oppsettet huskes per nettleser (`ko.oppsett`); «Oppsett» i
  verktøylinja tilbakestiller. `koGyldigOppsett()` avviser et lagret oppsett som mangler et
  vindu.
- **Hendelsesloggen** (`static/js/ko-hendelser.js`): stripete tabell — annenhver rad i to
  toner — med prioritet, H-nr, tid, tittel med beskrivelse og melder, sted, ressursbehov,
  oppdrag, opprettet av, status. **Prioritetene er Viktig, Rød, Gul, Grønn, Drift**
  (André); Viktig gir rød ramme og rødt trekant-utropstegn, de andre en farget venstrekant
  og et merke med tekst. Sortering som oppdragslista: lukkede nederst, så prioritet, så
  nummer. **Søkeknapp** som åpner et felt i flata (nummer, tittel, sted, melder,
  beskrivelse, lag). Bryter «Vis lukkede».
- **Hendelsen åpnes inne i vinduet**, ikke i en modal: hode med prioritetsknapper og en
  godt synlig grønn «Lukk hendelse», sted, melder, ressursbehov, opprettet av; «Oppdrag på
  hendelsen» med **Nytt oppdrag** (sentralbordets skjema, hendelse og sted forhåndsvalgt)
  og **Knytt eksisterende**; **Lagsressurser** som tekstfelt; tråden «Løpende» med
  kommentarer og systemlinjer; skrivefelt (Enter sender). «På hendelsen: kari, andre» —
  **den som registrerer noe i hendelsen er automatisk med** (kommentar, oppdrag,
  prioritet, redigering), pluss en «Bli med»-knapp. `ko.HendelseDeltaker`, vises og styrer
  ingenting.
- **«Ny hendelse»-skjema** i Andrés rekkefølge: hvor, hva, melder, beskrivelse, prioritet
  (fem knapper), ressurser som **avkryssing**. Opprettet av og tid settes automatisk.
  Erstatter `prompt()`. Samme skjema redigerer hodet.
- **Ressursbehovene** er en egen liste i KO (`ko.Ressursbehov`) under **KO-innstillinger**
  — sentralbordets valgliste-modal med en fane til, lagt inn gjennom den generelle kroken
  `verdifaner_ekstra`/`window.VERDIFANER_EKSTRA`, så `oppdrag` fortsatt ikke kjenner `ko`.
  Settes opp av KO-leder eller admin; sletting er admin og bare for ubrukte. Begrepet ble
  sjekket mot `oppdrag.Enhetstype` og `vaktliste.Ressursgruppe` først: politi og
  arrangørvakter er ikke portalens ressurser, så en egen liste er riktig.
- **Loggstrømmen** med **festede linjer** («noen skal kunne pinnes») øverst i egen boks:
  `Logglinje.festet_at/festet_av/festet_av_navn`, `fest`/`losne`-stier på `skriv_full`,
  idempotent, aldri systemlinjer. `festede` sendes hele med pollen, som `fjernede` — festing
  har ingen ny id. Strømmen viser linjene uten hendelse pluss systemlinjene om hendelsene
  (`koIStrommen`); kommentarene står i hendelsen. Skrivefeltet heter **«Loggfør»** og står
  nederst; nyeste linje øverst. Bryter «System» demper stemplene, aldri hendelseslinjene.
- **Oppdragslista uten hendelser** — grupperingen fra pulje 5 er fjernet. H-merket bærer
  koblingen og rød trekant når hendelsen er Viktig, og raden viser **«Lag: Lag 1, Lag 3»**
  fra hendelsen. Det samme feltet står i **bilen** (aktivt og ventende kort) — «et felt
  med lagsressurser som kobles til hendelsen … såfremt oppdraget er koblet til en
  hendelse». `oppdrag_til_dict` bærer `hendelse_prioritet` og `hendelse_lagsressurser`,
  begge med i ETag-ene.
- **«Nytt oppdrag»** i Andrés rekkefølge: hvor, hastegrad, problemstilling, enhet,
  fritekst, hendelse. Gjelder også `/oppdrag/`. «Hendelse» fylles av KO i
  `#nytt-hendelse-plass`.
- **Knappene står i vinduet de gjelder**: «Nytt oppdrag» og «Historikk» rett etter
  oppdragslistas tittel («den lå for langt vekke»), «Enheter» i ressursoversikten, «Ny
  hendelse» i hendelsesloggen. «Valglister» heter **«KO-innstillinger»** på `/ko/`, «Hvem
  er pålogget» heter **«Pålogget»**. Oppsettvarselet er egen malbit
  (`_sentralbord_oppsettvarsel.html`), så `/ko/` kan ha sin egen verktøylinje.
- **Prioritetsendring er en systemlinje** (`HENDELSE_PRIORITET`): «H14 satt til Viktig
  (var Grønn) · tittel», med hvem. Opprettelseslinja bærer prioriteten når den ikke er
  Grønn.
- Modell: `Hendelse.prioritet/beskrivelse/melder/lagsressurser/ressursbehov`,
  `HendelseDeltaker`, `Ressursbehov`, `Logglinje.festet_*` (`ko/0006`). Backup stripper
  `festet_av` og `HendelseDeltaker.bruker`; navnene står frosset.
- JS: `ko.js` delt i tre (`ko-layout.js`, `ko-hendelser.js`, `ko.js`), `KO_JS` er en
  tuppel og registrert i `core/tests_js_splitt.py`. 28 JS-filer, 157 ruter, 19 under
  `/ko/` — `TEKNISK_DOKUMENTASJON.md` oppdatert.

### Sett i nettleseren, ikke bare i suiten

Sida ble kjørt lokalt med seedet demovakt og styrt med Playwright: ingen JS-feil, oppsettet
lagres, skjemaene har feltene i rett rekkefølge. Én feil funnet slik: **tråden i en åpen
hendelse ble klemt til én linje** når hodet var høyt — `min-height: 10rem` på `.h-traad`.

### Mutasjonstesting

18 mutanter mot `ko/services.py`, `ko/systemlinjer.py` og `ko/views.py`, kjørt mot
`ko.tests_hendelseslogg` (1,5 s): `bli_med` fjernet fra hvert av de fem kallstedene, ukjent
prioritet sluppet gjennom, samme prioritet gir linje, prioritetsendring uten systemlinje,
fest to ganger bytter navn, systemlinje kan festes, kommentar i annen vakt, ukjent
ressursbehov utelatt stille, grense av med én, ressursbehov alene teller ikke, Grønn på
opprettelseslinja, alle kan sette opp ressursbehov, ressursbehov i bruk kan slettes,
hendelse utenfor vakta som kommentar. **18 av 18 fanget.** Prøvene for rutenettet
(`koGyldigOppsett`, `koBytt`, `koKlemProsent`), sorteringen, søket og `koIStrommen` kjøres i
node (`ko/tests_js.py`); `TavlaSierFraTilKoTests` holder kallstedet i `renderOppdrag()` i
live.

### Åpent, ført i TODO

Utskrift med alt kronologisk (strømmen skjuler hendelseskommentarene), linje i strømmen →
hendelse i etterkant, oppsett per bruker på serveren.

---

## 2026-09-18 — KO pulje 7 (statistikk) avventes  `#ko/sentralbordet`

André: «Vi avventer statistikk delen … det haster ikke.» Punktet i `TODO.md` er skrevet om
med begrunnelsen: notatet §8 krever data fra en ekte vakt, og neste er ca. 250 dager fram.
Tas opp etter første ekte vakt på `/ko/`. Ingen kode.

---

## 2026-09-18 — KO pulje 6: chat, ansvarsmerke, minimerbare grupper og vaktlistas ressurser på tavla  `#ko/sentralbordet` `#vaktliste/planlegging`

**Notatet sa «chat og filter». André sa noe annet, og det er det som er bygget** (tre svar
18. sep. 2026, alle notert i `FORSLAG_KO.md` §4.5, §5.1 og §7.2):

- «Chat er bare en chattelogg hvor en kan skrive fritt med tidsstempel. Admin skal kunne slå
  dette på/av. Hendelse må vises tydelig i loggen/chatten som Hendelse. Og hvem som
  opprettet den.»
- «Skal ikke være direkte filter sånn initielt tenker men **ressurstypene må kunne
  minimeres**. Og så må vi få inn alle enheter fra vaktlisten som kan velges i /ko som ikke
  allerede er i /oppdrag.» — og på oppfølgingen: **operatøren velger hvilke som vises**.
- «Ansvarsområde er bare et merke som gjør at folk vet hvem som har ansvar for hva. Ingen
  annen praktisk formål.»

### Det som er bygget

- **Chat er et merke på linja i samme logg** (`Logglinje.uformell`), ikke en tabell (§4.5).
  Avkryssingen «chat» i skrivefeltet finnes bare når `ko.chat_tillatt` er på — en
  `AppSetting`, auditlogget, **av som standard**, med avkryssing på
  `/portal-admin/innstillinger/`. Sperren står i `skriv_linje` og ikke bare i skjemaet.
  Bryteren styrer om *nye* kan skrives; linjene som alt finnes vises uansett, ellers får
  loggen et hull. Retting arver merket. Linja vises dempet med «chat».
- **Hendelseslinjene vises tydelig**: `koLinjeMerke()` gir `hendelse` for `hendelse_*`-kodene
  foran `system`, blått merke, uthevet linje, og den som opprettet står under (frosset i
  pulje 5).
- **Ansvarsmerket** (§5.1): `ko.Ansvarsmerke`, én rad per konto, nedtrekk i toppen av `/ko/`
  (samband / ressurser / logg / media — fast liste i kode, «Samband» og «samband» er ett
  merke), `POST /ko/api/ansvar/` på `les`-nivå. Står ved navnet i «Hvem er pålogget» og
  stemples på linjene (`skriv_linje` når kallet ikke oppgir noe; oppgitt verdi, også tom,
  vinner). **Ikke i backupen** — merket er hva som gjelder nå.
- **Ressurstypene kan minimeres.** Gruppeoverskriften på tavla er en knapp
  (`gruppehode()`/`vippGruppe()` i `oppdrag-kort.js`, altså på begge sidene), husket per
  nettleser under `tavle.grupper.lukket`, **og viser antallet når gruppa er lukket** — «2 ·
  1 ledig». Det som er skjult er lesbart (§7.2).
- **Vaktlistas ressurser uten oppdragsenhet står på tavla**: lag, samleplass, KO, under
  enhetslista i sin egen beholder (`#vaktliste-ressurser` — sentralbordet tegner
  `#enhetsliste` om igjen ved hver poll). `vaktliste.services.ressurser_uten_enhet()` og
  `/vaktliste/api/ressurser/uten-enhet/`: skiftene som dekker nå, ellers neste skift,
  **uten telefon og ISSI**, samme scope som `vaktliste_i_bruk()` og samme gate som
  besetningen (`les` i vaktliste + alle korps). Kortet sier hvem og om de er møtt — **ingen
  status**: hva en KO-ført status for et lag skal hete er fortsatt ubesvart (`TODO.md`), og
  det ble ikke funnet på denne gangen heller.
- `/ko/` 11 → 12 endepunkter, `/vaktliste/` 29 → 30, portalen 150.

**Ryddet:** `oppdrag.services.tomt_enhetskort()` og `TomtEnhetskortHarSammeFormTests` — død
kode siden pulje 4 tok KOs egen ressursliste bort; den eneste leseren var sin egen test.

### Sett i nettleser

Playwright mot seedet base: «Ansvar: samband» i toppen, «chat»-avkryssing, `∨ AMBULANSE` /
`∨ UTEN TYPE` / `∨ LAG` / `∨ KO` som overskrifter, `Lag 1 · 1 av 2 møtt · Kari Nordmann,
Ola Hansen (ikke møtt)`, `Lag 2 · ubemannet · Ingen nå · 15:04: Per Olsen`, `KO · ubemannet ·
Ingen på vakt`.

### Vern og mutanter

`ko/tests_pulje6.py` (22: chatreglene, ansvarsmerket, portene, bryteren gjennom
handleren), `vaktliste/tests_ressurser_uten_enhet.py` (7: scope, bemanning nå/neste,
avmeldte, ingen telefon, gaten), `ko/tests_js.py` (+10: merkene, minimeringen med stubbet
`localStorage`, ressurskortene, escaping).

**20 mutanter, alle drept.** Tjenestelaget (9): chat-sperra fjernet, bryteren alltid av,
ansvar stemples ikke, merket vinner over oppgitt, ukjent område slipper gjennom, retting
arver ikke, `tilstede` uten ansvar, innstillingens fravær slår av, merket med i dumpen.
Vaktlista (5): bilene med, avmeldte teller, gaten fjernet, neste skift borte, telefon
lekker. JS (6): hendelse blir system, chat fjernet, lukket gruppe tegner kortene likevel,
antallet borte fra overskriften, valget huskes ikke, overskriften uescapet.

**Skanneren i `ko/tests_js.py` sa fra fire ganger** underveis — `escapeHtml(a + ' ' + b)`
og `x.liste.map(...)` limt rett inn ser den som uescapet, fordi den leser konkatenering og
ikke kall. Hoistet ut i `const`-er, som resten av byggerne. Den er streng på riktig side.

### Dokumentene

`ko/CLAUDE.md` (nytt avsnitt «Chat, ansvar og tavla»; tre avsnitt strammet for å holde
taket på 22 000 tegn — 21 916), `vaktliste/CLAUDE.md` (ett tillegg; 56 895 av 56 900 tegn
— taket der er nådd, neste tillegg må ta noe ut), `FORSLAG_KO.md` (§10 ✅ 6, og Andrés svar
i §4.5, §5.1, §7.2), `TEKNISK_DOKUMENTASJON.md`, `TODO.md` (pulje 6 ut; nytt punkt om at
KO-ført lagstatus nå er mer synlig, ikke mindre).

---

## 2026-09-18 — KO pulje 5: hendelser — `H12`, gruppering av tavla, lukking med 409, `O45` overalt  `#ko/sentralbordet` `#oppdrag/sentralbord`

**To spørsmål ble besvart før koden** (André): en lukket hendelse **kan åpnes igjen** —
«å åpne en hendelse vil være pga misforståelse eller feilklikk … må logges at den ble åpnet
igjen» — og **`Hxx` og `Oxx` overalt**, ikke bare i loggen. Begge står i `FORSLAG_KO.md` §11
som besvart, og §10 har ✅ på pulje 4 og 5 (pulje 4 manglet haken).

### Det som er bygget

- **`ko.Hendelse`** (§3.3): vakt, `hendelsesnummer`, tittel, lokasjon (FK til
  `oppdrag.Lokasjon` **pluss frosset `lokasjon_navn`**), status åpen/lukket, `versjon`,
  opprettet/lukket av med frosne navn, `opprettet_fra_linje`. **Ingen statusmaskin.**
  `Logglinje.hendelse` (nullbar, `SET_NULL`) — linja er fasit, hendelsen er en gruppering.
- **`Oppdrag.hendelse`**: nullbar FK til `'ko.Hendelse'` som strengreferanse — ingen import,
  `KJENTE_UNNTAK` i `ko/tests_avhengighet.py` er fortsatt tom. **Skrives bare av
  `ko.services.knytt_oppdrag`**; oppdragsmodulen leser den i `oppdrag_til_dict`
  (`hendelse_id`, `hendelse_nummer`, `hendelse_tittel`) og har den i ETag-en — uten leddet
  sto grupperingen gammel til neste stempling.
- **Nummerserien** `next_hendelse_nr_vakt_<pk>`, tvilling av oppdragstelleren, atomisk,
  gjenskapt fra data hvis raden mangler, **og i `NOKLER_UTEN_AUDIT` i samme commit** (§6:
  «nøyaktig fella pasienttelleren gikk i»). Uavhengig av O-serien; nullstilles ikke av
  vaktarkivet, for hendelsene arkiveres ikke — de følger loggens 730 dager i
  `slett_utlopte`.
- **Fem regler i `ko/services.py`:** `opprett_hendelse` (fra en linje: linja *blir stående*
  og får hendelsen, hendelsen peker tilbake — §4.5), `rediger_hendelse` (`versjon`, 409 ved
  uenighet — §7.1; ingen systemlinje, `audit/` fører feltendringer), `lukk_hendelse` (**409
  med antallet** åpne oppdrag, gjennom med `confirm`, og antallet står på linja — §4.6;
  ferdige oppdrag teller ikke), `gjenapne_hendelse` (logget, `lukket_*` tømt),
  `knytt_oppdrag` (knytt/flytt/løsne med hver sin setning; lukket hendelse tar ikke imot;
  annen vakt avvises). Alle skriver en systemlinje **med operatøren frosset som forfatter** —
  «H12 lukket» uten hvem svarer ikke på det man leser loggen for.
- **Fire nye systemkoder** i `ko/systemlinjer.py`: `hendelse_opprettet`, `hendelse_lukket`
  («— med 2 åpne oppdrag» når døra ble åpnet bevisst), `hendelse_gjenapnet` («H12 åpnet
  igjen»), `oppdrag_knyttet` («O45 knyttet til H12» / «flyttet fra H3 til H12» / «løsnet fra
  H2»). Ni → tretten.
- **`O45` i stedet for `#45`**, ett sted: `oppdrag.services.oppdragsnr()` (brukt av
  `Enhetshendelse.detalj`, bjellevarselet, `__str__`, KO-loggen) og `oppdragsnr()` i
  `oppdrag-kort.js` (tavla, historikken, detaljtittelen); `oppdrag-enhet.js` har sin egen kopi
  som de andre hjelperne der. **Hele logghistorikken skiftet form uten en migrasjon** — det
  er grunnen til at systemlinjer lagres som kode + data, og det var første gang det ble brukt.
  Eldre `Enhetshendelse.detalj`-rader står med `#`.
- **Endepunktene** (`ko/urls.py`, 6 → 11): `api/hendelser/ny/`, `<pk>/rediger/`, `<pk>/lukk/`,
  `<pk>/gjenapne/`, og `api/oppdrag/<pk>/hendelse/` (knytt/løsne). Alle `ko:skriv_full`;
  **knytting krever `oppdrag:skriv_full` i tillegg**, sjekket i viewet — det skriver på en
  oppdragsrad, og hvem som får det er oppdragsmodulens sak. **Lesingen har ingen egen
  poller:** `logg_view` svarer med `hendelser` (hele lista, som `fjernede`) hver gang.
- **Tavla:** `renderOppdrag()` spør `koGrupperOppdrag()` gjennom en vakt (`typeof … ===
  'function'`) — på `/oppdrag/` finnes den ikke og lista er flat som før. Regelen: åpne
  hendelser nyeste først, også uten oppdrag; lukkede bare mens de har rader; «Uten hendelse»
  sist, og bare når den har rader eller er alene. **Bryteren «Gruppér på hendelse» skjuler
  ingenting** (§7.2) og huskes i `localStorage`. Raden bærer `H12`-merket på begge sidene.
  Detaljmodalen har knytt/løsne (`koHendelseValg`), «Nytt oppdrag» får et hendelsesnedtrekk
  lagt inn av `ko.js` (`koEtterOpprettet` knytter etter opprettelse), loggen har «Hendelse»
  på hver operatørlinje og en knapp for hendelse uten linje.
- **Backup:** `ko/backup.py` stripper `Hendelse.lokasjon` (og de to brukerpekerne). Uten det
  var det en **sirkel** — oppdrag peker på ko, ko på oppdrag — og en sirkel lar seg ikke
  gjenopprette. Dermed snur rekkefølgen: **`portal → ko → patients → arkiv → oppdrag →
  oppdrag_arkiv → vaktliste`**. KO er øverste lag i koden og nest først i gjenopprettingen;
  det er ikke en motsigelse, det er forskjellen på hvem som kjenner hvem og hvem som peker
  på hvem. `bindinger()` utledet kanten, `avvik()` sa fra, og
  `GjenopprettingsrekkefolgenIDokumenteneTests` pekte på de fire dokumentene som måtte
  rettes (`CLAUDE.md`, `RUNBOOK_VAKT.md`, `TEKNISK_DOKUMENTASJON.md` × 2).

### Sett i nettleser

Playwright mot seedet base: `H2 Savnet barn ved inngang nord · 0 oppdrag`, `H1 Slagsmål
scene sør · Scene · 1 oppdrag · 1 åpne` med «Rediger» og «Lukk», raden `O1 H1 AKUTT Transport
· 3 pasienter` under, loggen med `O1 opprettet`, `Haugesund 56: Fremme (O1)`. Det som ble
rettet av å se det: en tom «Uten hendelse · 0 oppdrag» sto som en overskrift over ingenting.

### Vern og mutanter

`ko/tests_hendelser.py` (44 tester: nummerering, opprettelse, redigering, lukking,
gjenåpning, knytning, opprydding, portene, at loggen bærer hendelsene, at oppdragslista
bærer hendelsen og ETag-en følger, og at backupen ikke har en sirkel) og `ko/tests_js.py`
(grupperingsregelen som ren funksjon, nummerformene, **og kallstedet**:
`TavlaSpoerEtterGrupperingenTests` kjører `renderOppdrag()` med `koGrupperOppdrag` til stede).

**30 mutanter, 29 drept med det samme, én overlevde og ble drept etter at testen ble
strammet.** Tjenestelaget (14): lukket-sperra, vaktsjekken og systemlinja i `knytt`;
`confirm`-kravet, ferdige oppdrag talt med og antallet borte fra linja i `lukk`; systemlinja
og `lukket_av_navn` i `gjenåpne`; versjonssjekken og tellingen i `rediger`; linja uten
hendelse og forfatter uten frysing i `opprett`; tellingen i `hendelser_for`; oppryddingen.
Portene (3): oppdrag-skriv-kravet, 409 uten antall, ukjent lokasjon stille `None`. ETag (1),
backup-strippingen (1), audit-prefikset (1). JS (10): bryteren ignorert, åpne uten rader
utelatt, lukkede uten rader tatt med, ukjent hendelse falt ut, eldste først, tittelen
uescapet, tom uten-gruppe alltid med / borte når alene, **kallstedet til `koGrupperOppdrag`
fjernet** — og **`${hendelseMerke}` fjernet fra raden, som overlevde**: testen søkte etter
`hendelse-merke` i hele tavla, og overskriften bærer samme klasse. Den prøver nå raden alene
(`_oppdragRadHtml`), og mutanten er død. Det er lyveren nr. 1 i `CLAUDE.md` — den traff et
annet sted enn testen så.

### Dokumentene

`ko/CLAUDE.md` (fem utdaterte avsnitt om «pulje 3/5 kommer» er skrevet om; nytt avsnitt om
hendelsene og om at kanten snur gjenopprettingen), `oppdrag/CLAUDE.md` (FK-en og `O45`),
`FORSLAG_KO.md` §10/§11, `CLAUDE.md` (rekkefølgen, «tre ting binder»; 65 497 av 65 500 tegn),
`TEKNISK_DOKUMENTASJON.md` (148 endepunkter, `/ko/` 11), `RUNBOOK_VAKT.md`. `TODO.md`: pulje
5-blokka og `O45`-punktet er borte; to nye punkter — linje → hendelse i etterkant som del av
pulje 6, og et lite skjema i stedet for `prompt()` når noen har brukt den på en vakt.

**Ryddet i forbifarten:** `ko/views.py` hadde et dødt `ressurser_view` igjen fra pulje 3 —
uten rute, og det kalte `services.ressursbildet`, som ikke finnes. Borte.

**Suiten:** fire tester forventet `#`-formen (`ko/tests_logg`, `oppdrag/tests_runde_c`,
`tests_runde_d`, `tests_xss`) og er rettet til `O`. Den siste gjemte seg bak
`TypeError: cannot pickle 'traceback' object` fra `--parallel` — feilmeldingen som ikke
ligner det den er (`CLAUDE.md`, «Commands»). Åtte node-harnesser fikk `_oppdragRadHtml`,
`oppdragsnr` og `hendelsesnr` klippet med. 2 811 + 757 tester grønne.

---

## 2026-09-18 — `/ko/` lastet aldri `oppdrag.css`: derfor så ikke lista ut som i `/oppdrag/`  `#ko/sentralbordet` `#oppdrag/sentralbord`

**Symptomet:** ressursoversikten og oppdragslista i `/ko/` var «ikke lik den i /oppdrag» —
ingen kort, ingen statusprikker, ingen hastegradsmerker, bare tekst under hverandre
(«Haugesund 56 / Fremme 06:59 · nå / #1 Akutt Bil: —»). Tre forsøk på å rette det gikk
grønne og feilet likevel (André: «opus prøvd 3 ganger … mislykkes»).

**Årsaken var én manglende linje.** Sentralbordets markup bærer klassene (`.enhet-kort`,
`.oppdrag-rad`, `.status-prikk`, `.hastegrad-*`, `.enhet-brikke`), men *reglene* står i
`static/css/oppdrag.css` — og `templates/ko/index.html` lastet bare `ko.css`. Samme markup,
samme data, samme JS; arket manglet. `oppdrag.css` lastes nå **før** `ko.css`, så konsollen
kan overstyre.

**Hvorfor tre forsøk ikke fant det:** alle tre verifiserte på server- og JS-siden — konteksten
lik, skriptene like, ID-ene like, ti endepunkter identiske før og etter. Alt det var sant.
Ingen tegnet sida i en nettleser. Denne gangen ble begge sidene åpnet med Playwright mot en
seedet SQLite-base (`skjermbilde.js` i scratch: innlogging, 1920×1080, teller `.enhet-kort`,
lister stilarkene), og feilen sto i stilarklista på første kjøring: `/oppdrag/` endte på
`oppdrag.css`, `/ko/` på `ko.css`. **Lærdom:** en påstand om *utseende* bevises med et
skjermbilde, ikke med en diff av svaret. Står som punkt i `TODO.md`.

**To layoutfeil til, sett i samme skjermbilde** (`static/css/ko.css`, malen):
- Skjemakortet øverst i loggkolonnen ble klemt: `.ko-kolonne > .card { flex: 1 1 auto }`
  traff *begge* kortene, og hint-linja «Ikke skriv navn …» lå oppå kortkanten.
  `#ko-logg-skjema { flex: 0 0 auto }`.
- Loggen rullet ikke: `ko-rull` sto på `#ko-logg-liste` inne i en `card-body` uten
  `min-height: 0`, så lista vokste forbi kortet og sida rullet i stedet. `ko-rull` står nå
  på `card-body`, som i de to andre kolonnene.

**Og to ganger på fem minutter skrev jeg en flerlinjes `{# … #}`** i malen — den rendres som
tekst øverst på sida. `FlerlinjesMalkommentarTests` (13. sep.) ville sagt fra i suiten; jeg så
det i skjermbildet før jeg kjørte den. Byttet til `{% comment %}`.

**Vern:** `test_ko_laster_stilarkene_sentralbordet_er_tegnet_med` i `ko/tests_sentralbord.py`
— hvert stilark `/oppdrag/` laster, laster `/ko/`, med `oppdrag.css` før `ko.css`, og med en
sperrehake på at `/oppdrag/` faktisk laster `oppdrag.css` (ellers er kravet tomt). Navnene
sammenlignes uten WhiteNoise-hashen (`oppdrag.bb76….css`). **Mutanter (3, alle drept):**
`oppdrag.css` fjernet fra KO-malen, rekkefølgen snudd, `oppdrag.css` fjernet fra
`sentral.html`. CSS-laget prøves ikke, etter tabellen i `CLAUDE.md`.

**Dokumentene:** `CLAUDE.md` sa «Fem stilark» mens `static/css/` hadde sju — `notifications.css`
og `oppdrag.css` sto ikke i tabellen, og det var nettopp den manglende raden som kunne fortalt
at KO-sida trengte den. Tabellen har nå alle sju. Rota er 65 493 tegn av 65 500. `TODO.md`:
et duplisert `oppdrag-enhet.js`-punkt fjernet (sto to ganger, med to datoer), og punktet om
visuell kontroll lagt til.

`/oppdrag/` er ikke rørt.

## 2026-09-18 — KO pulje 4: sentralbordet flyttet inn i `/ko/`  `#ko/sentralbordet` `#oppdrag/sentralbord`

Den største puljen i KO-løpet. `/ko/` viser nå ressurslista, oppdragslista, verktøylinja og
alle modalene — **oppdragsmodulens egne**, ikke en gjenskaping.

### Ett spørsmål ble stilt før koden

Notatet sier ikke hvordan den flyttede oppdragsflata gates, og det er et valg som endrer
hvem som får bruke KO. Spurt, og svaret var **oppdrag-tilgang styrer**:

> KO *viser* oppdragsmodulens data, og hvem som får se dem er oppdragsmodulens sak.

Det er komposisjonsregelen fra rollemodellen §5, den samme `kan_se_besetning` bruker for
vaktlista. Konsekvensen: **en KO-operatør trenger to rader**, `ko` for loggen og `oppdrag`
for oppdragene. Alternativet — egne KO-nivåer foran ~20 av oppdragsmodulens endepunkter —
ville lagt tilgangsmodellen to steder.

Det gjorde puljen til en flytting uten en eneste ny gate, og det er grunnen til at den ble
liten i stedet for stor.

### Delt på fire nivåer

| Hva | Hvor | Delt av |
|---|---|---|
| Konteksten | `oppdrag.views.sentralbordkontekst()` | begge sidene |
| Verktøylinja | `templates/oppdrag/_sentralbord_verktoy.html` | begge |
| Modalene | `templates/oppdrag/_sentralbord_modaler.html` | begge |
| Globaler og skript | `templates/oppdrag/_sentralbord_skript.html` | begge |

`/ko/api/ressurser/` er **borte** — den gatet oppdragsdata på `ko:les`, og det er nettopp
det valget over sier nei til. `ko.js` henter derfor verken ressurser eller oppdrag:
sentralfilene eier begge listene med sin egen ETag og polling. En henter til ville vært en
andre poller mot de samme endepunktene, og to pollere som skriver til samme `#enhetsliste`
blir uenige.

### `/oppdrag` er bevist uendret, ikke antatt uendret

Ti endepunkter ble dumpet før flyttingen — enheter (med og uten `?alle=1`), oppdrag,
lokasjoner, enhetstyper, problemstillinger, historikk, arkiv, bilinnstillinger og sida selv
— med en fikstur som dekker et oppdrag under arbeid, en enhet i passiv vakt, en av vakt og
en pensjonert. Baselinen ble kjørt på nytt etter **hvert** steg:

- etter at konteksten ble skilt ut → uendret
- etter at malbitene ble skilt ut → uendret
- etter at KO tok dem i bruk → uendret

**En flytting bevises ved å sammenligne svaret, ikke ved å lese diffen.** Målingen avdekket
også sin egen forutsetning: backupklokka er en tråd i web-prosessen og ga
`SessionInterrupted` midt i dumpen, som så ut som endepunktfeil og ikke var det.

### Mutasjonstesting

**7 mutanter.** Gaten byttet fra `oppdrag` til `ko`, konteksten redusert til et utvalg,
modalene utelatt fra KO, sentralfilene ikke lastet — alle drept.

**To overlevde først, og begge var samme feilklasse:** testen min målte at de to sidene er
*like*, ikke at de er *komplette*. Begge leser samme malbit, så en skriptfil som faller ut
faller ut begge steder og likheten består. Og knappegaten kunne fjernes fordi testen så
etter modalen — som gates i en *annen* malbit — og ikke etter knappen.
`test_alle_sentralbordfilene_lastes` måler nå mot `OPPDRAG_SENTRAL_JS`, og knappetesten ser
etter både knappen og modalen.

### To vakter ble blindet av flyttingen, og det er verdt å merke seg

`JsSplittenErKompletTests` og `CsrfPaaSkrivendeFlaterTests` leste malfila direkte. Da
skriptene flyttet inn i `{% include %}`-biter, sluttet begge å se dem — **uten å bli
røde**, som er det verste utfallet. De ble røde her bare fordi sentralbordfilene forsvant
helt ut av sida de leste.

Ny `core/maltekst.py`: les en mal **med alt den inkluderer**. Samme regel
`MorkTekstPaaMorkBakgrunnTests` alt følger for `{% extends %}` — følg lastekjeden, ikke én
fil. Og CSRF-vakten vurderer nå *sider* og ikke malbiter: en fil som begynner med `_` er en
bit noen inkluderer, ikke en flate noen åpner, og tokenet hører hjemme på sida.

Tre mutanter på vaktene selv (en fil fjernet fra skriptbiten, rekkefølgen snudd,
csrf-metaen fjernet fra basemalen) — alle drept. **En vakt som overlevde en flytting er
ikke bevist å virke; den er bevist å ikke ha sett noe.**

### Hva som står igjen

`/oppdrag/` er **uendret og fortsatt i drift**. Å slå av sentralbordet der er en beslutning
om en flate folk bruker, ikke en refaktorering — den tas når KO er prøvd på en ekte vakt.
Står i `TODO.md`.

---

## 2026-09-18 — Verifisering av at `/oppdrag` står uendret — og én regresjon funnet  `#oppdrag/sentralbord`

André: «Jeg er ekstremt skeptisk på det du har levert til nå i /ko. Men husk /oppdrag var i
en veldig god stand før vi begynte med /ko.»

Skepsisen er fortjent, og «stol på meg» er ikke et svar. Bekymringen er etterprøvbar, så den
ble etterprøvd.

### Hva målingen viste

**Ti av tolv flyttede JS-funksjoner er byte for byte identiske** med utgaven før flyttingen
(`hastegradKlasse`, `_problemMedAntall`, `_medAntall`, `_grovMerke`, `tidSiden`,
`_typeRekkefolge`, `_grupperEnheter`, `kanSeBesetning`, `mkBesetning`,
`_besetningKontakt`).

**Og serversvaret er identisk.** `/oppdrag/api/enheter/` ble dumpet fra en `git worktree` på
commit-en før endringene og fra dagens kode, med samme fikstur — fire enheter, én på
oppdrag med tre pasienter, én i passiv vakt, én av vakt, én pensjonert. `diff` er tom.
Mønsteret er verdt å huske: **en flytting bevises ved å sammenligne svaret, ikke ved å lese
diffen.**

### Den ene som ikke var identisk var en ekte regresjon

`visBesetning()` og `hentBesetning()` tegnet før på nytt med `renderEnheter()`, som leser
den **levende** `enheter`. Etter flyttingen kalte de `tegnEnhetsliste(sisteEnhetsliste)` —
og `sisteEnhetsliste` er referansen fra forrige tegning.

`lastEnheter()` gjør `enheter = (await res.json()).data`, altså en **ny array**, og tegner
**ikke** i samme slengen: `lastAlt()` gjør det etterpå. Mellom de to fyres
`hentBesetning(apenBesetning)` uten `await`. Løser den i det vinduet, tegnet den forrige
rundes enheter. Vinduet er kort og retter seg selv ved neste tegning — men forskjellen var
ekte, og det holder ikke i en modul som var i god stand.

Sida melder nå inn hvor lista bor (`settEnhetslisteKilde`), og den delte koden **spør** i
stedet for å huske. Innmeldingen står *i* `renderEnheter()` og ikke som en linje på
toppnivå, og det er en testbarhetsregel: en toppnivålinje kjøres ikke av `build_harness()`,
så kallstedet kunne fjernes uten at noe ble rødt — mutanten overlevde nøyaktig sånn.

### Mutasjonstesting

**4 mutanter.** Tilbake til husket liste (drept), kallstedet fjernet (**overlevde først** —
testen satte kilden selv, mutantløgn nummer tre), og begge på nytt etter at innmeldingen
flyttet inn i `renderEnheter()`.

`DenDelteListaLeserDenLevendeEnhetslistaTests` går gjennom `renderEnheter()`, som er den
ekte inngangen: den bytter ut arrayen uten en tegning imellom, og krever at den nye lista
er den som tegnes.

---

## 2026-09-18 — Ressurslista rullet tilbake: verdimengden var funnet på  `#ko/ressursbildet` `#oppdrag/sentralbord`

André: «Du har ikke direkte kopiert sentralbord delene fra /oppdrag. Jeg hadde aldri noe
pause og ute av drift på de i /oppdrag. Her har du tatt deg grove friheter utenfor rammene
som er satt. Vi vil ha det likt i funksjonalitet som vi hadde det i /oppdrag før vi begynte
på /ko men med det vi har sagt av logg og slikt.»

Han har rett, og feilen er verdt å navngi presist. **`docs/FORSLAG_KO.md` §3.1 sier at KO
skal føre status for dem som ikke stempler selv — men ikke med hvilke ord.** Jeg fylte inn
«Ledig», «Opptatt», «Pause», «Ute av drift» og skrev en overbevisende begrunnelse for at de
hørte hjemme i kode og ikke i en tabell. Begrunnelsen var god; valget var ikke mitt å ta.
**Et hull i et notat er et spørsmål, ikke en invitasjon.**

Verre: gårsdagens arbeid het «feature parity» og *la til* funksjonalitet `/oppdrag/` aldri
har hatt. Det er ikke parity, det er noe annet med et parity-navn på.

### Hva som er borte

`ko/choices.py`, modellen `ko.Ressursstatus`, `services.sett_ressursstatus()`, systemkoden
`ressurs_status`, skrive-endepunktet `/ko/api/ressurser/<pk>/status/` og statusknappene i
nettleseren. `ko/migrations/0003` slipper tabellen — den sto på staging i under et døgn,
uten produksjonsbruk, og bar ingenting som ikke også lå som en systemlinje i loggen.

### Hva som står i stedet

**`/ko/` viser `oppdrag.Enhet`, tegnet av sentralbordets egen funksjon.**
`tegnEnhetsliste()` flyttet fra `oppdrag-sentral-kjerne.js` til den delte
`static/js/oppdrag-kort.js`, sammen med grupperingen på enhetstype, besetningspanelet og
«av vakt»-telleren. `renderEnheter()` i sentralbordet er nå **ett kall** inn i den. Begge
sidene bruker `#enhetsliste` og `#av-vakt-teller`.

Serversiden var alt delt fra i går: `oppdrag.services.enhetskort()`.
`ko.services.ressursbildet()` returnerer nå den samme lista som
`/oppdrag/api/enheter/` — og `test_samme_svar_som_oppdragsmodulens_endepunkt`
sammenligner **hele svaret** fra de to endepunktene. Ikke bare nøklene: en KO-side som
filtrerte, sorterte eller scopet annerledes ville vært usynlig for en nøkkelsjekk.

**KO fikk ingen skrive-endepunkter på enhetene.** Av vakt og passiv vakt er
oppdragsmodulens, og blir KOs når sentralbordet flytter (pulje 4). Et eget i mellomtiden
ville vært en andre vei inn til samme tilstand.

### Konsekvensen skal stå skrevet

**Et lag uten `oppdrag.Enhet` vises ikke på lista** — akkurat som i `/oppdrag/` i dag. Den
tredje kilden i §3.1 er utsatt, ikke forkastet, og den er ikke en kodeoppgave: noen må
bestemme hva statusene skal hete. Står i `TODO.md`.

### Mutasjonstesting

**7 mutanter.** KO som filtrerer bort enheter av vakt, KO som tar med pensjonerte,
`ledig_siden` droppet, besetningsgaten fjernet, sentralbordet som tegner sitt eget igjen.

**Sorteringen overlevde først.** `test_samme_svar_som_oppdragsmodulens_endepunkt`
sammenligner de to endepunktene — men med to enheter opprettet alfabetisk gir `pk` og
`Lower('navn')` samme rekkefølge. Testdataene skilte ikke de to. Ny test med «Zulu 9»,
«alfa 1», «Bravo 5» opprettet i den rekkefølgen: den dreper både `order_by('pk')` og
`order_by('navn')` uten `Lower`, altså også den der «alfabetisk» blir databasens eget
alfabet. Det er `CLAUDE.md` sin egen regel — «krev rekkefølgen i svaret, med data som
avslører databasens alfabet» — og jeg hadde skrevet testen uten å følge den.

---

## 2026-09-17 — Feature parity med sentralbordet: samme kode, ikke samme flid  `#ko/ressursbildet` `#oppdrag/sentralbord`

André: «Du har tatt friheter med ressursoversikten. Det er ikke feature parity med
/oppdrag. Jeg vil ha det likt feature messig inn her i /ko.» Og: «Endre navnet fra «rett»
til «rediger» i loggen» — gjort, både på knappen og i ledeteksten.

Han har rett. KOs første kort viste navn, besetning og status. Sentralbordets kort viser i
tillegg **passiv vakt, antall ventende, «ledig siden», hvor bilen dro, og hele
oppdragslinja** — nummer, hastegrad, bilens grovsortering og problemstillingen med
pasientantall.

### Parity som holder er den som følger av at det er samme kode

To steder, samme grep:

| Lag | Den ene kilden | Leses av |
|---|---|---|
| Server | `oppdrag.services.enhetskort()` | `oppdrag.views.enheter_view` og `ko.services._enhetsstatuser` |
| Klient | `enhetskortInnmat()` i nye `static/js/oppdrag-kort.js` | `_enhetskort()` i sentralbordet og `koRessursHtml()` i KO |

Å kopiere feltene ville gitt parity **den dagen**, og så tapt den ved neste felt noen la
til — uten at noe ble rødt. Det er den samme feilklassen som gjenopprettingsrekkefølgen i
morges: en påstand skrevet fire steder går i utakt, en utledning gjør det ikke.

`tomt_enhetskort()` gir raden samme form for en ressurs **uten** enhet, så klienten slipper
å spørre «finnes feltet» før hver avlesing — en manglende nøkkel blir `undefined` midt i en
mal-streng.

### Tre feil funnet mens paritet ble bygget

**1. «antall» betød to ting i samme rad.** `enhetskort()` bruker `antall` om *pasienter* på
oppdraget, og `_problemMedAntall()` leser nettopp det feltet. KOs rad skrev mannskapstallet
dit. En bil på et transportoppdrag ville vist antall folk i bilen som antall pasienter — en
feil ingen ser som en feil, bare som et tall som er litt rart. Heter nå `bemanning_antall`
og `bemanning_tilstede`. **Funnet av testen, ikke av lesing:** det var første gang de to
feltsettene møttes i samme rad.

**2. Mannskapslista lå åpen for alle med `ko:les`.** Sentralbordet gater
besetningspanelet på `har_tilgang(bruker, 'vaktliste', 'les')` — komposisjonsregelen fra
rollemodellen §5, så en modul ikke gir avledet innsyn i en annens data. KOs ressursbilde
sendte navnene til alle med KO-tilgang. Sto slik fra pulje 3 til nå; feilen var min, og den
var stille — markupen så helt riktig ut. Gaten er nå den samme, og
`test_endepunktet_gater_paa_vaktliste_og_ikke_paa_ko` prøver den gjennom den ekte inngangen.

**3. `window.OPPDRAG_MED_ANTALL` manglet på KO-sida.** Det delte kortet slår opp der for å
vite om problemstillingen bærer et antall. Uten den står «Transport» der det skulle stått
«Transport · 3 pasienter»: kortet ser riktig ut og er fattigere, som er den stille varianten
av å mangle parity.

### Mutasjonstesting — to overlevende, og begge var ekte hull

**9 mutanter.** Sperra mot koblet bil, gaten på vaktliste, KO som tegner sitt eget kort,
et felt ute av `tomt_enhetskort()`, og fire til.

**«KO leser `enhet_status` i stedet for `enhetskort`» overlevde først.** Raden får alle
nøklene av `tomt_enhetskort()`, så testen min på «har feltet» gikk grønn mens feltene sto
tomme. Den prøvde formen, ikke innholdet. `test_feltene_er_fylt_og_ikke_bare_til_stede`
krever nå verdiene.

**«ledig_siden droppes» overlevde.** Ingen test hadde en enhet som faktisk *var* ledig etter
et oppdrag. Nå finnes den.

Og én mutant var en ekte no-op: mannskapstallet skrevet i `antall` overskrives av
`enhetskort()` like etter — for **enheten**. For laget finnes ingen slik overskriving, og
det er der regelen måtte prøves. Mutantløgn nummer to, sett fra riktig kant.

### Det som ikke ble delt

`oppdrag-enhet.js` — bilens egen skjerm — har fortsatt sine egne kopier av
`hastegradKlasse` og `_problemMedAntall`. Den laster ikke `oppdrag-kort.js`, og å rive i
enhetsskjermen hører til pulje 4. Står i TODO.

---

## 2026-09-17 — KO som konsoll: tre kolonner, og sida ruller ikke  `#ko/skallet`

André, etter å ha sett pulje 3: «Logg skal være den sentrale delen. Ressursoversikt henger
sammen med oppdragslisten. PC er hoved måten en bruker dette på. Hva tenker du er den
ideelle ux løsningen?»

### Det avgjørende funnet lå i sentralbordet

`templates/oppdrag/sentral.html` er i dag `col-lg-4` Ressurser + `col-lg-8` Oppdragsliste,
side om side. Paringen André beskriver er altså ikke en hypotese — den står i prod, virker,
og er nøyaktig den blokka pulje 4 skal flytte inn i KO. En annen arrangering nå hadde betydd
at pulje 4 måtte slåss mot den.

### Formen: `Logg │ Ressurser │ Oppdrag`, 4 : 3 : 5

**Rekkefølgen er arbeidsflyten fra venstre mot høyre:** du hører noe, fører linja, ser hvem
som er ledig, og sender. Loggen står først, der øyet lander i en latinsk lesning.

**«Sentral» er lest som *primær og permanent*, ikke som *midterste kolonne*** — og det er
et valg jeg skrev ned framfor å gjette på. Loggen bokstavelig i midten gir
`Ressurser │ Logg │ Oppdrag`, og da splittes paret som hører sammen, mens den hyppigste
handlingen på skjermen — matche en ledig ressurs mot et ventende oppdrag — spenner over hele
bredden. Rekkefølgen håndheves nå av en test, så neste omstokking må være bevisst.

### Sida ruller ikke — kolonnene gjør det

Det er forskjellen på en konsoll og en nettside. Rulles sida, flytter skrivefeltet seg idet
tavla får en rad til, og operatøren treffer feil felt midt i sambandstrafikk. **Dette var en
ekte feil i det jeg pushet tidligere samme dag:** `max-height: 45vh` på tavla og `60vh` på
loggen betyr at *sida* ruller.

Høyden **måles** (`koKonsollhoyde()`) og regnes ikke ut av en `calc()` med et fast tall: over
konsollen står portalheaderen, navigasjonen og eventuelle meldinger, og alle tre kan brekke
til to linjer. Et fast tall ville vært riktig på én skjerm og galt på alle andre. Gulvet
`KO_MIN_HOYDE` er en regel og ikke en margin — uten det gir et kort vindu tre ubrukelige
rullefelt samtidig, og da er det bedre at sida ruller.

### `.portal-content` var kappet til 1400 px, og det ville drept hele formen

Funnet i den rendrede sida, ikke i CSS-en: `base_portal.html` setter
`max-width: 1400px` på innholdet. Riktig for en leseflate — en tekstlinje på 1900 px er vond
å følge — men for en konsoll betyr det at tre kolonner deler 1400 px **uansett hvor stor
skjermen er**. En 2560-skjerm ville vært nøyaktig like trang som en laptop: 466 / 350 / 583.

Sluppet fri i `ko.css` med `body:has(.ko-konsoll)`, altså i sidas eget ark og ikke som en ny
blokk i `base_portal`. Faller `:has()` bort, er resultatet den gamle bredden — trang, ikke
ødelagt.

### Sidebaren er et nedtrekk, ikke en kolonne

«Hvem har KO oppe» er en håndfull navn man kikker på, ikke noe man overvåker. Knappen har
`data-bs-toggle="dropdown"` og **ingen** `data-action`: begge ville fyrt på samme klikk, og
det er nettopp fella `klikkSkalKjore()` i `portal-utils.js` finnes for. Sparingen fra pulje 1
står — ingen polling av en liste ingen ser på — bare snudd: lista er lukket som standard og
hentes når nedtrekket åpnes.

### Nytt stilark, uten fargevariabler

`static/css/ko.css` (femte ark). Regelen i rota om at et nytt modulark må definere de fire
`base_portal` ikke aliaser, gjelder et ark som **bruker** dem — dette er ren layout, og fire
variabler ingen regel refererer til er død kode som i tillegg lyver om å være i bruk.

### Mutasjonstesting

**4 mutanter, alle drept:** gulvet i høyderegelen fjernet, kolonneklassen omdøpt,
`data-action` tilbake ved siden av `data-bs-toggle`, og — den som betydde noe —
**kolonnene faktisk byttet om**. Den første omdøpingen traff bare tilstedeværelsesprøven;
rekkefølgeprøven krevde en ekte ombytting for å bli rød, og den ble det.

Fire node-prøver på `koKonsollhoyde()`, inkludert at gulvet holder når regnestykket blir
negativt.

### En tabbe i verktøyet, igjen

Første forsøk på å skrive malen brukte en **ukvotert** heredoc (`<<PY` og ikke `<<'PY'`), så
bash kjørte backtick-uttrykkene inne i den norske prosaen som kommandoer. Skriptet meldte
«ok» og malen parset — den var bare tømt for halve innholdet. Rullet tilbake med
`git checkout` og skrev om via en skriptfil i stedet. **Samme lærdom som i går: tell
resultatet, ikke returkoden.**

---

## 2026-09-17 — KO pulje 3: ressursbildet  `#ko/ressursbildet`

Tavla over hvem som er på vakt og hvor de står — `docs/FORSLAG_KO.md` §3.1. Flyttet fram
fra pulje 4 samme dag, fordi den er uavhengig av alt annet og er den flata operatøren
faktisk sitter og ser på.

### En projeksjon, ikke et register

KO eier ingen ressurser. Tavla settes sammen av tre kilder, og bare den tredje er ny:
vaktlista svarer på hvem som finnes og hvem som er på skift nå,
`oppdrag.services.enhet_status` på statusen til dem som stempler selv, og
`ko.Ressursstatus` på statusen til dem som ikke gjør det.

**Hvem som fører utledes av `Ressurs.enhet`, ikke av et flagg.** Er den satt, eier
oppdragsmodulen statusen; er den `NULL` — et lag har ingen `Enhet` i det hele tatt, det er
hele poenget med at de ikke logger inn — er det KO. Et flagg ville vært en andre sannhet om
det samme, og de to ville stått i strid den dagen noen koblet en enhet uten å rydde flagget.

**Rutingflagget i §3.2 er ikke bygget, og det er et valg.** Det avgjør `/oppdrag/` mot
`/park/`, og `/park/` finnes ikke — bygget nå er det en bryter med én stilling. At det
korrelerer med «hvem stempler selv» er tilfeldig, ikke det samme spørsmålet. Flyttet til
`/park/`-punktet i TODO, der det allerede sto.

### Tabellen er nåtilstand, historikken er loggen

Én rad per ressurs, oppdatert og ikke påført. Hver føring skriver i stedet en systemlinje —
den tiende koden, `ressurs_status`, og den første som **ikke** løftes av et signal: dette er
KOs egen handling, så tjenesten skriver linja direkte. To kilder til samme historikk går i
utakt første gang noe feiler halvveis, og da er det den lagrede som lyver.

De to skrives i samme transaksjon. `test_ingen_rad_uten_linje` er prøven på det, og den er
verdt å ha: en status uten linja si er en endring som aldri skjedde.

**Fravær av rad er «Ledig»** — utledet, ikke lagret, av samme grunn som
`oppdrag.services.enhet_status` gir det samme svaret ved vaktstart. En lagret standard måtte
settes for hver ressurs i hver vaktliste, og da er spørsmålet «hvem glemte å sette den».

**Verdimengden er kode** (`ko/choices.py`): Ledig, Opptatt, Pause, Ute av drift. Regelen
står i `oppdrag/choices.py` og gjelder her — *faglige verdimengder i kode, arrangementsdata
i databasen*. Og de er **ikke** oppdragsstatusene: et lag uten oppdrag er ikke «venter», det
står på post. Å gjenbruke den ene ville tvunget operatøren til å lyve om den andre.

### Den feilen jeg nesten skrev inn

«Lista i drift vinner» (André, 12. sep. 2026) sto inline i `vaktliste.services.besetning()`,
og tavla trengte det samme. Jeg trakk den ut i `vaktliste_i_bruk()` og lot `besetning()`
bruke den — **og det var galt.** Flere vaktlister kan stå i drift samtidig, ingenting hindrer
det, og `driftstatus.py` regner med det. `besetning()` spør om *én enhet* og må lete i alle
listene i drift; tavla spør globalt og skal ha én. Sammenslåingen gjorde at en enhet koblet i
den andre driftslista ble usynlig for sentralbordet.

**Hele suiten var grønn** — 1 756 tester i `vaktliste` og `oppdrag` — fordi ingen test har to
lister i drift samtidig. Rullet tilbake: `vaktliste_i_bruk()` er KOs globale spørsmål,
`besetning()` beholder sin ressurs-scopede spørring, og begge bærer nå en kommentar om at de
deler *prioriteringen* og ikke spørringen. Den globale er dessuten gjort deterministisk
(`-satt_i_drift_at`): et ressursbilde som bytter innhold mellom to pollinger er verre enn ett
som viser feil liste, fordi det siste lar seg se.

### Vakten fra i formiddag tok kanten selv

`ko.Ressursstatus.ressurs` peker inn i `vaktliste`, og `rekkefolge.bindinger()` — skrevet
noen timer før — meldte straks `ko → {portal, vaktliste}` og bekreftet at `ko` alt står
etter `vaktliste` i gjenopprettingsrekkefølgen. Hadde den stått før, ville `avvik()` blitt
rød. Det er første gang den nye vakten svarer på et spørsmål ingen stilte den.

### Mutasjonstesting

**17 mutanter, alle drept.** Tungt lag på tjenestelaget og portene, middels på de to
JS-funksjonene som avgjør noe, ingenting på markup.

Sperra mot å føre status på en koblet bil, statusvalideringen, `_fort_av_ko` invertert,
transaksjonen fjernet, skiftets sluttid ignorert, tilgangsnivået senket fra `skriv_full` til
`les`, vaktliste-scopet fjernet fra ressursoppslaget, drift som ikke slår aktiv vakt,
systemlinja som ikke skrives, `er_gyldig` som alltid svarer ja, standardstatusen byttet,
`strip_fields` uten `satt_av`, koden ute av `KODER` — og på klienten: ett ledd i
`koKanStyreRessurs` fjernet, **kallstedet** for knappene fjernet (ikke bare funksjonen),
ukjent status farget grønn, escaping av mannskapsnavn fjernet.

**En feil jeg gjorde i mitt eget verktøy er verdt å skrive ned:** JS-blokka ble satt inn med
en `assert` på en kort streng og en `replace` på en lengre som ikke matchet. Assert-en gikk,
replace-en var en no-op, og skriptet meldte «ok». Det er mutantløgn nummer to rettet mot meg
selv, og det ble bare oppdaget fordi jeg talte linjer i fila etterpå i stedet for å tro på
meldingen. **Tell resultatet, ikke returkoden.**

---

## 2026-09-17 — KO uten faner: flatene står ved siden av hverandre  `#ko/skallet`

André, om skallet: «Å ha de som 4 faner med ressursoversikt, oppdragsliste, logg og
hendelser er dårlig ux. Det må faktisk fikses.» Og: knappen for å føre en logglinje het
«Før» — «virker som et dårlig oversatt ord til norsk». Den heter **«Ny»** nå.

### Hvorfor faner var feil form her

En fane er riktig når flatene er *alternativer* — man gjør det ene eller det andre. KOs
flater brukes i **én** bevegelse: sambandet sier noe, du fører linja, du ser hvem som er
ledig, og du sender. Tre av fire trengs for å fullføre én handling, og hver fane koster et
bytte som mister det du leste.

Den andre kostnaden er verre, og den gjør ikke vondt før det haster: **en skjult fane er en
fane du ikke vet har endret seg.** Siden poller (§7.1), så en annen operatørs logglinje, et
nytt oppdrag eller en ressurs som nettopp ble opptatt lander i en rute ingen ser på. Et
merke sier *at* noe skjedde, ikke *hva* — enda et klikk midt i sambandstrafikk, mens hele
grunnen til at KO finnes er at situasjonsbildet skal være i ett blikk. Det er også derfor
vaktsentraler, ICS-tavler og stripbord er samtidige paneler: statusbildet skjules ikke.

**Notatet sa aldri «faner».** §7 sto som «fire flater, én side», og pulje 1 leste det som
`nav-tabs`. Det er verdt å merke seg for neste notat: «én side» og «én skjerm» er ikke det
samme, og ordet som manglet var *samtidig*.

### Formen nå: to kolonner, tre flater

Venstre: ressursoversikten øverst (den skannes hele tiden), oppdrag under (der man handler).
Høyre: loggen som fast panel med skrivefeltet øverst, og sidebaren over seg. Loggen er smal,
skrives konstant og leses konstant — den hører hjemme som et panel, ikke bak en fane.
Sidebaren fikk ikke beholde sin egen kolonne: den er en håndfull navn, og en tredje kolonne
ville tatt bredde fra loggen på nøyaktig de skjermene KO brukes på.

**Under `xl` stables kolonnene, og det er akseptert og ikke løst.** KO brukes på en skjerm i
et kommandopunkt, og en telefon kan uansett ikke vise en ressurstavle. Kommer kravet om
mobil, er det en egen oppgave — og svaret er ikke faner.

### Hendelser er en gruppering, ikke en flate — og det flytter to puljer

Fire flater ble tre, og den som forsvant er «Hendelser». `Oppdrag.hendelse` er en nullbar FK
(§3.3): hendelsen *er* grupperingen. Og §4.6 sperrer lukking med 409 når hendelsen har åpne
oppdrag — operatøren må altså se hendelsens oppdrag i det hun lukker den, og to flater ville
lagt nøyaktig den opplysningen i den fana hun ikke står i. Grupperingen blir en bryter på
lista: de fleste oppdrag har `hendelse = NULL`, og en permanent «Uten hendelse»-bøtte med
mesteparten av radene er et tegn på at grupperingen ikke duger som hovedakse.

Det endrer rekkefølgen på puljene, og endringen følger av formen og ikke av en preferanse:

| Var | Er | Hvorfor |
|---|---|---|
| 3 — hendelser | **3 — ressursoversikten** | Uavhengig av alt annet, og den flata operatøren faktisk sitter og ser på. Kommer to puljer tidligere |
| 4 — ressursoversikten | **4 — sentralbordet flyttes** | Blokkerer nå hendelser |
| 5 — sentralbordet flyttes | **5 — hendelser** | En gruppering av en liste som ikke er der ennå, lar seg ikke prøve |

Prisen står i TODO: pulje 4 var «den største» og er nå også den som blokkerer. Blir den
lang, er ressursoversikten levert i mellomtiden, og den er nyttig alene.

### Hvorfor nå og ikke i pulje 5

Tre av fire flater er fortsatt tomme. Å rette formen nå er å flytte fire kort i en mal; å
rette den etter pulje 5 er å bygge om tre fylte skjermer, hver med sin polling og sin
tilstand. **Den billigste dagen å rette en layout på er den siste dagen den er tom.**

### Testen, og hvorfor den har to halvdeler

`SidenHarIngenFanerTests` rendrer det ekte viewet — ikke malfila, så en fane som kommer inn
via et partial fanges også. Den nekter `nav-tabs`, `tab-pane`, `role="tablist"` og
`data-bs-toggle="tab"`, **og** krever at loggen og tavla faktisk står samtidig. Bare den
første ville gått grønn om noen skjulte en flate med `d-none` og en egen knapp i stedet —
samme skade, annet navn.

**3 mutanter** (lett lag: markup som bærer en regel). Fanen satt inn igjen, tavla omdøpt,
loggen skjult med `d-none` ved lasting. Alle drept.

---

## 2026-09-17 — Gjenopprettingsrekkefølgen står i kode, ikke i fire dokumenter  `#core/backup` `#core/dokumentasjon`

Avstemming etter at KO pulje 2 og backlog-kommentarene ble flettet på `rollemodell`.
Mergen var ren og suiten grønn — **3 485 tester** — og det var nettopp derfor
gjennomgangen var verdt noe: begge feilene under sto bak grønne vakter.

### Tre av fire dokumenter mistet `ko` i gjenopprettingsrekkefølgen

Rekkefølgen sto skrevet ut for hånd fire steder. Da `ko` fikk backup-handler ble ett av
dem oppdatert og tre stående — og det oppdaterte var ikke `docs/RUNBOOK_VAKT.md`, altså
den ene fila man har foran seg *mens* man gjenoppretter. `core/tallfasit.py` sa ingenting,
fordi den teller handlere, og antallet var riktig i alle fire hele tiden. Det var
rekkefølgen som ikke var dekket.

Fasiten ligger nå i `core/backup/rekkefolge.py` — `GJENOPPRETTINGSREKKEFOLGE` og
`UTEN_BINDING` — av samme grunn som `core/tallfasit.py` er en modul og ikke en test: den
som skal rette et dokument må kunne spørre om svaret. `AlleFileneGjenopprettesTests`
henter lista derfra i stedet for å ha sin egen femte kopi, og
`GjenopprettingsrekkefolgenIDokumenteneTests` leter etter **enhver** pilkjede som starter
på `portal` i hvert dokument. En håndskrevet liste over hvor setningen står ville hatt
nøyaktig samme svakhet som den den erstatter: den femte kopien er usynlig for den.

### Og begrunnelsen dokumentene ga var for smal

Alle fire sa én ting: «fordi alt peker på vakta med et heltall». Det er sant, og det er
ikke alt. `vaktliste.Ressurs.enhet` peker på `oppdrag.Enhet`, også med et heltall, siden
`Enhet` ikke har noen natural key. Den som leste den oppgitte grunnen og stokket om,
ville lagt `vaktliste` rett etter `portal` — lovlig etter teksten. Prøvd, og det feiler:

```
IntegrityError: vaktliste_ressurs.enhet_id contains a value '1' that does not have a
corresponding value in oppdrag_enhet.id
```

`bindinger()` utleder derfor kantene fra modellene i stedet for å gjenta en påstand, og
`avvik()` sier fra når rekkefølgen ikke holder dem. Da er rekkefølgen ikke bare riktig,
men **kontrollert** riktig — og forskjellen viser seg først den dagen noen gjenoppretter.

**Utledningen min var selv for smal i første forsøk.** Et filter på `many_to_one` alene
gikk forbi `vaktliste.Vaktliste.vakt`, som er en `OneToOneField` — altså nettopp den
pekeren dokumentene begrunner rekkefølgen med. Utledningen meldte `vaktliste` fri mens
den er bundet. Egen test på den kanten nå, med begrunnelsen i assertion-meldinga.

### `Modulfiler`-raden i deploy-guiden har talt feil siden den ble skrevet

Raden navngir modulfilene og sier hvor mange det er. Den har sagt «Sju» om seks, «Åtte»
om sju og «Ni» om åtte — fordi påstanden var registrert mot `backup_handlere` i
`PAASTANDER`, og `full` står i raden under. Tre av oss har rettet tallet oppover etter tur
fordi testen ba om det. **En vakt som håndhever feil tall er verre enn ingen vakt:** den
gjør det gale til noe man ikke får lov å rette. Raden sier nå `Åtte handlere`, og
påstanden peker på `backup_modulfiler`.

### Mutasjonstesting

**15 mutanter**, tungt lag (backup og gjenoppretting). Én overlevde først: `f.name in
felt_uten` i `bindinger()` kunne fjernes uten at noe ble rødt, fordi hvert felt i
`strip_fields` i dag peker på en konto og ingen modulfil eier kontoene. Grenen er riktig,
men var riktig ved et uhell — `test_en_strippet_peker_er_ingen_binding` prøver den med
`Ressurs.enhet`, som er den ekte kandidaten til å bli strippet en dag. Drept etter det.

En mutant traff ikke i det hele tatt (feil søkestreng mot `CLAUDE.md`) og ble meldt som
«kunne ikke mutere» i stedet for som overlevende. Det er mutantløgn nummer to, og den
eneste grunnen til at den ikke ble et falskt «OK» er at skriptet skiller de to tilfellene.

Fire tester til: `test_en_modul_foer_den_den_peker_paa`, `test_en_bundet_modul_erklaert_fri`,
`test_en_registrert_modul_som_ikke_er_plassert`, `test_en_slug_som_ikke_finnes` — alle med
konstantene byttet ut, fordi `avvik()` mot fasiten er grønn også for en funksjon som
alltid returnerer `[]`.

`test_alle_seks_filene_kan_lastes_i_rekkefolge` het fortsatt «seks» mens den lastet åtte.
Heter nå `test_alle_modulfilene_kan_lastes_i_rekkefolge`.

---

## 2026-09-17 — KO pulje 2: loggen  `#ko/loggen`

Logglinjer, retting som ny rad, sletteinngangen, polling med `?siden=`, ni kuraterte
systemhendelser, backup-handler, oppbevaringstid og de tre nivåene. `docs/FORSLAG_KO.md`
§4, §7.1 og §10.

### De to valgene ble besvart før koden, og det var riktig rekkefølge

André svarte på begge. Det ene svaret endret konstruksjonen, og hadde ikke gjort det om
loggen var bygget først.

**«2 år initielt, men det bør nok være en railway variabel jeg kan styre. Enig?»**
Enig i tallet, uenig i variabelen — og prosjektet hadde alt tatt det valget én gang.
`purge_old_logs` sin egen docstring sier at grensene ligger i kode «slik at en endring av
lagringstid skjer i kode som kan revideres, **ikke i en skjult jobbkonfigurasjon**». En
Railway-variabel er en skjult jobbkonfigurasjon: ingen auditspor, må settes likt på både
web- og cron-tjenesten (samme felle som en kopiert `DATABASE_URL`), og usynlig i portalen.
Fristen er nå **`AppSetting['ko.logg_dager']`, standard 730 dager**, styrt fra
`/portal-admin/innstillinger/` av global admin, auditlogget av `core/signals.py`.
Nøkkelen skal aldri inn i `NOKLER_UTEN_AUDIT` — den er noe et menneske har bestemt, ikke
noe maskinen har talt.

**«Cron jobben purge_logs er vel den som fjerner data?»** Ja — `purge_old_logs`, som alt
kjører på Railway Cron natt til søndag og bare rører databasen.

**«Hvilke systemhendelser?» → «hva mener du?»** Forslaget ble godkjent som det sto: ni
koder, med regelen skrevet ned i `ko/systemlinjer.py`.

### «Når denne vakten er ferdig er det minst 12 mnd til neste vakt. Blir ikke det problematisk?»

**Spørsmålet avdekket en felle jeg ikke hadde sett.** Scopingen løser det André var redd
for — `hent_aktiv_vakt()` gjør at ny vakt gir tom logg, så den nye operatøren møter ikke
fjorårets linjer. Men `oppdrag/arkiv.py` sier dette om arkivering: «oppdragene slettes fra
tavla og historikken når de er frosset, og telleren nullstilles». **En FK fra logglinja til
`Oppdrag` hadde vært en felle uansett `on_delete`:** `PROTECT` blokkerer arkiveringen,
`CASCADE` sletter halve loggen stille, `SET_NULL` etterlater en linje som sier «meldte
Fremme» uten å si hvem. Linja fryser derfor teksten — `#45`, kallesignalet — med FK-en
utelatt. Det er samme regel §4.5 og §4.7 alt krever for brukernavn og kallesignal; jeg
hadde bare ikke sett at den også gjaldt oppdragsnummeret.

**Og det virkelige vinduet er ikke 12 måneder, det er de tre ukene etter vakta.** §4.2 sier
loggen er «i praksis et dokument man leser etter et arrangement der noe gikk galt» — det
leses dager til uker etter. Hadde linjene forsvunnet ved vaktarkivering, var dokumentet
borte akkurat når det skulle leses.

### Lesbar historikk, ikke et signert arkiv

`NOTAT_DPIA_OG_FRITEKST.md` §7 slår fast at fritekst bevisst ikke arkiveres, og
`Oppdrag.fritekst` er alt holdt utenfor `ArkivertOppdrag` av den grunn. **Et felt i en
SHA-payload er låst i 24 måneder ved konstruksjon**, så sletteinngangen i §4.4 ville fått
arkivet til å melde tukling. To funksjoner som spiser hverandre; valget falt på
sletteinngangen.

Prisen er sagt høyt, ikke gjemt: **loggen kan ikke bevise at den er urørt.** Den sporer
hvem som gjorde hva, men ikke at teksten ikke er endret.

**Fristen er ikke en sletterett**, og det står nå tre steder — i malbiten på
innstillingssiden, i `ko/backup.py` og i A.9. En fjernet linje ligger i modulfila offsite i
inntil 730 dager og i den hele fila i 90. Samme forbehold som DPIA-notatet §6 tar for
`Oppdrag.fritekst`.

### Ni systemhendelser, og regelen bak dem

`ko/systemlinjer.py`. **Inkluderingsliste, og det er motsatt av `NOKLER_UTEN_AUDIT` — med
vilje.** Der logges en ny nøkkel som standard, fordi en teller for mye er støy mens en
innstilling for lite er et hull man oppdager et år senere. Her er det omvendt: loggen er et
dokument et menneske leser, og en hendelse for mye koster lesbarheten til alle de andre.

Regelen, i tre setninger: **løft det som endrer situasjonen, ikke det som endrer oppsettet;
løft hendelsen, ikke feltet; én linje per ting som skjedde, ikke én per skriving.**

Løftes: oppdrag opprettet, hver statusovergang per enhet, korrigert tidspunkt, enhet
varslet, tatt av, rykket videre, avbrøt, avventer, og vaktmodus. Løftes ikke: verdimengder,
feltendringer på oppdraget, innlogging, drift, pasientregistreringer — og vaktlistas
stemplinger, som er grensesaken. «Lag 3 gikk av vakt» er ekte situasjonsinformasjon, men
per-person-stempling på hver vaktpost ville druknet loggen ved hvert vaktskifte. Tas opp i
pulje 4, der lag-begrepet får et hjem.

**«Trenger ny ressurs» ble et flagg og ikke en linje til** (regel 3): bilen forsvant *og*
oppdraget står uten ressurs er én hendelse sett fra hver sin side.

**Fire av de ni kodene fantes allerede** som `oppdrag.Enhetshendelse` — `tatt_av`,
`rykket_videre`, `avbrutt`, `avventer`, med tidspunkt og bruker. §2-erfaringen om igjen:
sjekk om oppdragsmodulen har begrepet før du designer det inn i KO.
`test_hver_enhetshendelse_er_vurdert` krever at hver type der enten løftes eller står i
`ENHETSHENDELSER_UTELATT` med en begrunnelse — ellers ville en ny type falt stille ut.

### Løftet går med signaler, ikke med et register i `core`

Retningen `ko` → `oppdrag` holdes av konstruksjonen. Et push-register hadde krevd at
`oppdrag/services.py` meldte fra, og oppdragsmodulen skal ikke røres før pulje 5.

Forbeholdet er skrevet ned: **et signal ser raden, ikke intensjonen.** «Avbrutt fordi ingen
svarte» og «avbrutt fordi pasienten gikk hjem» er samme rad. Trenger en linje intensjon,
må kallstedet dytte — og *da* bygges registeret, ikke før.

Mottakerne kaster aldri. **En KO-logg som ikke lar seg skrive skal ikke ta ned en stempling
i en bil**: bilen er det operative, loggen er dokumentasjonen. En test pakker `systemlinje`
i `side_effect=RuntimeError` og krever at oppdraget opprettes likevel.

### `korrigerer` *og* `rot` — to felter som ser ut som ett for mye

`korrigerer` er kjeden, som i `Statusmelding`. `rot` er plassen i fortellingen. Med bare
`korrigerer` ville ledd tre i en kjede arvet ledd to sin plass, altså bunnen av loggen — og
§4.3 sier hvorfor det er galt: linjene skal ikke hoppe rundt etter en korreksjon.
`Coalesce('rot_id', 'id')` gjør de to til én sortering uten en join.
`test_kjedet_retting_beholder_ogsaa_plassen` er prøven som skiller dem.

`korrigerer` er en **OneToOne**, så databasen selv nekter to rettinger av samme linje. Et
kappløp gir 409 og ikke en 500 — viewet fanger `IntegrityError` også, fordi sjekken i
`korriger()` bare er for feilmeldingens skyld.

### Sletteinngangen tømmer **hele kjeden**

Den viktigste prøven i `ko/tests_logg.py`. Rettes en linje og deretter fjernes den, ville
den opprinnelige teksten blitt stående i den overstyrte raden — usynlig i loggen, men fullt
lesbar i basen og i backupfila. **En sletteinngang som lar en kopi ligge igjen, er ikke en
sletteinngang.** Prøvd fra begge kanter: fra roten og fra rettingen.

Auditraden skrives av viewet, som i `restore_backup`, og **bærer ikke den fjernede
teksten** — lå den der, ville den ligget i auditloggen i 730 dager og inngangen vært et
skuespill. Samme valg som `FELT_UTEN_VERDILOGGING` tar for `notat` i vaktlista.
Systemlinjer røres ikke: de bærer ingen fritekst, og en inngang som nådde dem ville vært en
vei til å fjerne sporet etter en overstyring.

### `fjernede` i pollingsvaret, og hvorfor den ikke er sløsing

Sletteinngangen **endrer** en rad i stedet for å legge til en ny, så den har ingen ny `id`
og ville aldri kommet med i et `?siden=`-svar. Uten lista ville teksten blitt stående på
hver annen operatørs skjerm til hun lastet siden på nytt — altså nøyaktig den teksten noen
nettopp bestemte at ikke skulle stå der. Lista er liten og idempotent.

### Oppryddingen måtte gå gjennom et register

`purge_old_logs` ligger i `audit/`, som er rammeverk og måles av
`core/tests_avhengighetsretning.py` med samme målestokk som `core`. **En cron-jobb er ingen
unntaksgrunn.** Nytt register `core/opprydding.py`, samme idiom som `core/driftstatus.py`
og `core/portalinnstillinger.py`; `ko/opprydding.py` melder seg inn fra `apps.ready()`.

**`--days` gjelder rammeverkets tabeller og rører ikke handlerne.** Modulenes frister eies
av modulene, fordi det er modulen som vet hva dataene er — ett flagg som stilte på to helt
ulike lagringstider samtidig ville vært en felle den dagen noen brukte det. Én feilende
handler stopper ikke de andre, men gjør jobben rød: å avbryte på den første ville latt en
modul med en ødelagt spørring holde alle de andre lagringstidene uhåndhevet, stille, og å
svelge feilen ville gitt en grønn jobb som ikke gjorde det den sier.

**Klokka går fra `registrert_at`, ikke `tidspunkt`.** `tidspunkt` er korrigerbart, og en
frist som lar seg flytte ved å rette et klokkeslett er ingen frist.

### Nivåene: `les`, `skriv_full`, `skriv_leder` — lagt til i samme commit som endepunktene

`ko/module.py` deklarerte bare `les` i pulje 1, med vilje. Nå er alle tre der, delt etter
**hva slags skade en feil gjør**: den som fører loggen kan rette tilbake, fordi en retting
er en ny rad som peker på den gamle; den som fjerner en linje tømmer innholdet for godt.

KO er den første modulen der `skriv_leder` ikke betyr *oppsett mot drift*, men **hva som
lar seg angre**. `MED_LEDER` i `vaktliste/tests_tilgang.py` er fire moduler nå, og
begrunnelsen står der.

`skriv_handling` er bevisst **ikke** deklarert: nivået leser ikke request-kroppen, og å
føre en logglinje gjør nettopp det.

**Historikk krever `skriv_leder` av en annen grunn: dataminimering** (André). En ny operatør
på vakt i kveld har ingen operativ grunn til å lese fjorårets helseopplysninger. Flata
kommer i pulje 3; nivået står allerede, fordi det er det som gir `les` sin betydning —
«aktiv vakt», ikke «alt».

### To skannere som meldte grønt om en dekning de ikke hadde

**`SignalerFyrerIkkeUnderLoaddataTests` leste bare `sender=Klasse`.** Regexen var
`sender=(\w+)`, og `sender='oppdrag.Oppdrag'` ville gått rett forbi den — fem nye
mottakere uten dekning, med testen grønn. Regexen tar nå begge formene, og `ko/signals.py`
bruker klasser som de andre modulene.

**XSS-skanneren i `oppdrag/tests_xss.py` leser mal-strenger; `ko.js` bygger med
konkatenering.** En kopi av den skanneren ville funnet null byggere og meldt grønt.
`ko/tests_js.py` har sin egen som leser `'...' + felt + '...'`, med grensen skrevet ned:
den ser datafelt limt rett inn, ikke lokale variabler bygget lenger oppe. Derfor står fem i
`KO_GJENNOMGATT`, og derfor finnes oppførselsprøven som kjører byggerne med
`<img src=x onerror=alert(1)>` i tekst, forfatter, ansvarsområde **og** `fjernet_av` — den
siste er en gren som bare kjøres når noen har fjernet noe, altså sjelden og lett å glemme.

En detalj som kostet to runder: `\+\s*([a-z]\w*(?:\.\w+)+)(?!\()` backtracker `\w+` til
«ma» for å tilfredsstille lookaheaden, og rapporterer «rader.ma». Lookaheaden må være
`(?![\w(])`. **En regel som melder «rader.ma» er en regel ingen forstår.**

### Tre ting testene fant i min egen kode

1. **`koKanSkrive()` og `koKanFjerne()` returnerte `undefined`**, ikke `false`, fordi
   `|| t.admin` gir det siste leddet i kjeden. Falsy holdt i praksis; det er ikke det
   samme som å være riktig, og en avgjørelsesfunksjon som svarer «undefined» på «har hun
   lov?» er en funksjon man ikke kan stole på i en `=== false`.
2. **Et manglende `ko_logg_dager` avviste hele innstillingssiden** — arrangementsnavnet og
   vaktlistas felter med — fordi KO ikke fant sitt eget felt. **En modul som kan lamme
   naboene sine ved å mangle en nøkkel, er feil bygget.** Fraværende felt betyr nå «behold
   dagens verdi»; *tomt* felt betyr at et menneske har tømt det, og avvises.
3. **Nivåetiketten manglet ordet «leder».** `LedernivaaetsPlassIStigenTests` krever det av
   hver modul som deklarerer trinnet, og konvensjonen finnes fordi etiketten skal navngi
   rollen. «Lede KO» ble «KO-leder».

### Mutasjonstesting: 24 mutanter, tre overlevde først

Tjenestelaget tungt, portene middels, markup ingen — som tabellen i `CLAUDE.md` sier. Kjørt
med bare de testene som dekker hver mutant, ikke hele appen, og med diffen lest hver gang.

**Tjenestelaget (10):** `MAKS_ALDER` av med én; `MAKS_FRAMTID` av med én; `MAKS_FRAMTID`
fjernet; klemmingen i `oppbevaringsdager()` fjernet; `rot=linje.rot or linje` → `rot=linje`;
sletteinngangen tømmer bare raden og ikke kjeden; `registrert_at` → `tidspunkt` i
`slett_utlopte`; `korrigerer`-sjekken fjernet; `KILDE_SYSTEM`-grenen i `fjern()` fjernet;
`if kode not in KODER` fjernet.

**Modellen (2):** `filter(korrigert_av__isnull=True)` fjernet fra `gjeldende()`;
`Coalesce('rot_id','id')` → `'id'`.

**Portene (4):** `skriv_leder` → `skriv_full` på fjern-endepunktet; `confirm`-kravet
fjernet; 409 → 400; vakt-scopet fjernet fra `logg_view`.

**Løftet (4):** `fort_av_ko` invertert; ukjent konto påstår overstyring; `avventer` ut av
`ENHETSHENDELSER`; korreksjonsgrenen fjernet fra `statusmelding_skrevet`.

**JS og tegning (4):** `koKanFjerne` invertert; systemlinje-gaten fjernet fra
`koLinjeKnapper`; `escapeHtml` fjernet fra teksten; `escapeHtml` fjernet fra `fjernet_av`;
`trenger_ressurs`-flagget fjernet fra `tegn()`.

**Tre overlevde, og alle tre var ekte hull:**

1. **Begge tidsgrensene var udekket på selve grensa.** Prøvene sto et sekund utenfor og
   tretti sekunder innenfor, så `>` → `>=` gikk grønt begge veier. Bakover treffer en
   operatør som fører gårsdagens siste linje rett etter midnatt nøyaktig der; framover er
   det en nettleserklokke som går et helt minutt foran.
2. **`if kode not in KODER` var udekket.** Lista var dokumentasjon, ikke en port — en
   skrivefeil i en signalmottaker kunne lagt en rad i loggen som `tegn()` ikke kjenner, og
   den blir en tom linje: en rad som sier at noe skjedde uten å si hva.

Alle 24 drept etter at prøvene ble skrevet.

**Mutant 25, etter flettingen:** `fjernet_av` fjernet fra `strip_fields` i `ko/backup.py`
— drept av den nye `test_hver_brukerpeker_er_strippet_eller_begrunnet`, som kom inn med
kommentartråden samme dag. Kjørt nettopp for å se at den nye vakten faktisk dekker KO og
ikke bare gikk grønt fordi handleren tilfeldigvis sto riktig.

### Tallene fulgte med

137 → 141 endepunkter, `/ko/` fra 2 til 6 ruter, åtte → ni backup-handlere. (Etter at
kommentartråden i backlog ble flettet inn samme dag, står totalen på **143**.)
Gjenopprettingsrekkefølgen er **portal → patients → arkiv → oppdrag → oppdrag_arkiv →
vaktliste → ko**; `Logglinje.vakt` er en heltallspeker uten natural key, som alt annet som
er scopet til vakta.

### Ikke bygget, med vilje

Logglinja har **ingen FK til en hendelse ennå** — den kommer i pulje 3, sammen med regelen
om at en linje kan knyttes til en hendelse i etterkant. Historikkflata for tidligere vakter
er skrevet inn i TODO, ikke bygget: nivået den skal ligge bak står allerede.

---

## 2026-09-17 — Kommentarer på hvert innspill — og en mutant som fant fire hull i backupen  `#backlog/modulen` `#core/backup`

**André:** «Kan du legge til en kommentar funksjon på hver sak/innspill?»

En tråd under hver sak. Lesing er `les`, skriving `skriv_full` — den som bare ser
backloggen er en tilskuer, ikke en deltaker. Antallet står på knappen inn til tråden, så
den svarer på «er det noe her?» i det man ser etter veien inn.

### Tre valg spørsmålet tvang fram

| Valg | Hvorfor |
|---|---|
| **Tråden er åpen også på en løst sak** | Bevisst avvik fra at et løst innspill ikke kan redigeres. «Rettet i bygg `f3b279d`» **er** svaret, og det skrives etter at flagget er satt. Stengte vi tråden ved lukking, ble det umulig å notere hvordan saken ble løst akkurat der noen ville lett etter det |
| **`kan_endre_kommentar` har to vilkår, ikke tre** | Forfatteren og fristen, uten `lost`. En kommentar er ikke spørsmålet; den er en setning i tråden, og en skrivefeil rettet av forfatteren ti minutter senere velter ingenting. Grensen selv deles — `_innen_fristen()` — for en grense skrevet to steder er to grenser |
| **Sletting er strengere enn redigering** | Har noen *andre* skrevet i tråden, er saken ikke lenger et utkast — den er en samtale, og `CASCADE` ville tatt den andres setning med seg uten et ord. 409 med rådet «rediger den i stedet». Egne kommentarer teller ikke |

`kan_slettes` er sitt eget svar i API-et, ikke `kan_endres`: **en sletteknapp som gir 409
er en knapp som fører til en vegg.**

**Varselet går til tråden, ikke til alle som kan løse.** Forfatteren og de som har
kommentert, minus den som skriver nå. Varsler man bredere, blir tråden til støy for folk
som ikke har spurt om noe; varsler man smalere — bare forfatteren — går et svar fra
forfatteren aldri tilbake til den som spurte.

### Ti mutanter, ni drept — og den tiende var det verdt å høre på

Mutanten som fjernet `'backlog.Kommentar': ['opprettet_av']` fra `strip_fields`
**overlevde**. Det er den verste sorten overlevende: mekanikken er dokumentert i
`BaseBackupHandler.strip_fields` — serialiseringen kjører med `natural_foreign`, så en FK
til en konto lagres som brukernavnet, og er kontoen slettet feiler **hele**
gjenopprettingen med `DeserializationError`. Feilen viser seg bare den dagen man trenger
backupen.

**Det fantes ingen vakt.** Hver handler vedlikeholdt `strip_fields` for hånd, og en glemt
brukerpeker var usynlig — nøyaktig «en håndholdt liste forfaller i stillhet», for tredje
gang i dette prosjektet.

`BrukerpekereStrippesEllerBegrunnesTests` **utleder** nå hvilke FK-er det gjelder, med
samme oppløsning av `apps` som serialiseringen selv bruker (både «app» og «app.Modell» —
en test som leste bare den ene formen ville hoppet over arkivhandlerne i stillhet).
Regelen er ikke «alt må strippes»: å beholde pekeren er gyldig når koblingen er verdt mer
enn gjenopprettbarheten. Regelen er at valget skal være **tatt**.

**Og den fant fire ustrippede pekere i moduler arbeidet ikke gjaldt:**
`patients.Forstehjelper.user`, `patients.Helsepersonell.user`,
`oppdrag.Vaktmodusperiode.satt_av`, `oppdrag.Enhetshendelse.kvittert_av`. Alle fire er
`null=True` med `SET_NULL`, altså teknisk strippbare — og `Forstehjelper.user` er en
kontokobling av samme slag som `Mannskap.user`, som vaktlista **valgte** å stryke.

De står i `IKKE_STRIPPET` som **ikke vurdert**, og ikke som rettet: å stryke et felt fra en
dump er et valg om hva en gjenoppretting skal gi tilbake, og det hører til den som eier
modulen. Ført i `TODO.md`.

Tallene fulgte med: 137 → 139 endepunkter, `/backlog/` fra 7 til 9 ruter.

Suite: 3 382 tester, grønn.

---

## 2026-09-17 — Backlog: typene styres av admin, varsel til dem som kan løse, «Rediger»  `#backlog/modulen`

Tre ting etter at modulen gikk på staging, alle fra André.

### «Kan ikke admin få legge til flere typer?»

**Jo, og begrunnelsen min for `choices` var for smal.** Jeg skrev at «er dette en feil eller
et ønske» er et strukturelt skille som ikke endrer seg med arrangementet — men behovet som
melder seg, «spørsmål», «teknisk gjeld», «dokumentasjon», skal ikke vente på en utrulling,
like lite som en dronegruppe i vaktlista skal det.

`Innspilltype` er nå en tabell etter mønsteret i `oppdrag/views_verdier.py`: navn,
`er_aktiv`, `rekkefolge`, og sletting **bare når ingen bruker raden**. Administreres i
**«Backloginnstillinger»** på siden, av `skriv_leder` — samme nivå som setter opp
verdimengdene i oppdrag.

**`er_aktiv` er viktigere enn sletting.** En type i bruk kan ikke fjernes uten å ta
innspillene med seg (`PROTECT`), og da er «skjul den fra nedtrekket» det svaret man faktisk
vil ha:

- filteret viser **alle** typene — en deaktivert type må kunne filtreres fram
- skjemaet viser **bare de aktive** — den skal ikke kunne velges på noe nytt
- serveren håndhever det siste i `_hent_aktiv_type()`, ikke bare klienten

**409-svaret bærer rådet, ikke bare avslaget:** «Deaktiver den i stedet — da forsvinner den
fra nedtrekket, men blir stående på dem som alt har den.» «Kan ikke slettes» alene
etterlater brukeren uten en vei videre, og da er neste trekk å slette innspillene.

**Migrasjonen er delt i tre** (`0002`–`0004`), og det er ikke pynt. `0003` fyller FK-en med
data; `0004` fjerner den gamle kolonnen. Står de i samme migrasjon, er det en skriving
etterfulgt av `ALTER TABLE` i én transaksjon — fella som tok ned deployen 30. aug. 2026 med
«pending trigger events». Å dele migrasjonen i to er den tredje av de tre dokumenterte
veiene ut. `0002` seeder Bug og Ønske, så en tom base har noe å velge mellom fra første
innlogging.

### «Varsel til admin er fint»

`varsler.meld_nytt_innspill()`. **Mottakerne er de som kan løse, ikke alle som kan lese** —
kontoene med `skriv_leder` på `backlog`, pluss global admin. En bjelle som pling-er for folk
som ikke kan gjøre noe, er en bjelle man slår av, og da varsler den ikke den gangen det
haster. Innsenderen varsles ikke om sitt eget, av samme grunn.

Teksten bærer **tittelen**, ikke bare «nytt innspill»: det er tittelen som avgjør om man går
og ser nå eller i morgen. `notify()` dedupliserer på *meldingen* siste 24 timer, så to ulike
innspill gir to varsler mens et dobbelttrykk gir ett.

**Varselet er en sideeffekt, ikke en del av innmeldingen** — `meld_nytt_innspill()` kaster
aldri, og en test pakker `notify` i en `side_effect=RuntimeError` og krever 201 likevel.

### «Endre «rett» til «rediger», mye tydeligere språk»

«Rett» leser som en korrigering av noe som er galt; det man som regel gjør er å legge til
det man glemte. Knappen heter **«Rediger»**, vinduene heter **«Nytt innspill»** og
**«Rediger innspill»**, og nivåetiketten i matrisen sier «melder inn, redigerer sitt eget».
Hjelpetekstene er skrevet om: «Valgfritt, men hjelper mye: hva du gjorde, hva du forventet,
og hva som faktisk skjedde.»

### Ni mutanter til, alle drept

Fem på typeadministrasjonen (deaktivert type kan likevel velges, typeporten fjernet,
sletting uten global admin, `confirm`-kravet fjernet, duplikatsjekk uten `iexact`) og fire
på varslene (innsenderen varsles om sitt eget, alle med tilgang varsles i stedet for bare
de som kan løse, tittelen ut av meldingen slik at dedup slår inn, og **kallstedet** fjernet
fra viewet — den siste er regel 3 i `CLAUDE.md`: muter kallstedet, ikke bare funksjonen).

Tallene fulgte med: 135 → 137 endepunkter, `/backlog/` fra 5 til 7 ruter.

**Og backfillen ble prøvd mot ekte rader, ikke bare mot en tom testbase.**
Djangos testbase lages ved å kjøre migrasjonene mot en *tom* base — et dataskritt uten data
skriver ingenting, og `fyll()` i `0003` ville stått udekket. Kjørt manuelt mot en
engangsbase: migrer alt, rull `backlog` tilbake til `0001` (som samtidig prøver
reversibiliteten), legg inn tre rader i den gamle formen, migrer fram. `bug` → «Bug»,
`onske` → «Ønske», og den ukjente kodeverdien `sporsmal` **beholdt meningen sin** som en ny
type i stedet for å tvinges inn i «Bug» — det er `get_or_create` i `fyll()` som gjør det,
og den grenen er hele grunnen til at den står der.

Suite: 3 355 tester, grønn.

---

## 2026-09-17 — Ny modul: `/backlog/` — endringsønsker og bugs  `#backlog/modulen` `#core/tilgang`

**André:** «Da blir modulen en backlog i systemet i stedet for innspill spredt i chatter.»

Ett innspill per rad, klassifisert som **bug** eller **ønske**, med et **løst-flagg**.
Lista filtreres på type, status og modul. Modulen er utviklingsverktøy for et knippe
mennesker, ikke en flate for alle som går vakt.

**Ingenting fantes fra før.** `Notification` er per mottaker med lest/ulest, altså et annet
problem — men `notify()`-API-et ligger der om backloggen en dag skal si fra til noen.

### Tre valg som ikke sto i bestillingen

| Valg | Hvorfor |
|---|---|
| **Modulen står utenfor vaktscopet** | Alt annet er scopet til en `core.Vakt` fordi det beskriver *en vakt*. Et innspill beskriver **portalen**: «nedtrekket lukker seg når jeg velger» gjelder like mye i oktober. Scopet det til vakta, ville lista tømt seg selv ved hvert vaktbytte — og en backlog som glemmer er ikke en backlog |
| **Angrefristen måles fra opprettelsen**, ikke fra siste endring | Fra endringstidspunktet ville hver retting forlenget fristen, og et innspill kunne holdes redigerbart i det uendelige ved å røres hver time. Da er ikke fristen en frist |
| **En løst sak kan ikke rettes, selv innen timen** | Løst er et svar noen har gitt. Lar man forfatteren skrive om spørsmålet etterpå, blir svaret uforståelig. Følger av at løst er et flagg og ikke en sletting |

**Global admin er ikke unntatt fristen.** Den verner ikke forfatteren, den verner *loggen* —
«blir som en logg» var hele bestillingen.

### Nivåene: Andrés tre, oversatt

| Hans | Portalens | Etikett i matrisen |
|---|---|---|
| les | `les` | Lese: ser backloggen |
| les/skriv | `skriv_full` | Skrive: melder inn, retter sitt eget |
| les/skriv full | `skriv_leder` | Skrive full: leder backloggen, setter løst |

**`skriv_handling` er hoppet over med vilje.** Nivået er «navngitte overganger som *ikke*
leser request-kroppen», og å melde inn et innspill er nettopp å lese kroppen.

**Og en eksisterende vakt sa fra med en gang.**
`LedernivaaetsPlassIStigenTests.MED_LEDER` krever at en modul som deklarerer `skriv_leder`
står på lista over dem som har *forklart* hva «leder» betyr der — ellers ville toppnivået
snike seg inn uten at noen hadde definert det. Backlog står nå der med begrunnelse, og
etiketten sier hva lederen gjør. Tre moduler, tre betydninger av samme trinn: «setter opp
vakta», «setter opp verdimengdene», «leder backloggen».

### Den andre vakten som fanget noe

`AlleFileneGjenopprettesTests.REKKEFOLGE` krever at hver registrert backup-handler står i
gjenopprettingsrekkefølgen. Backup-handleren ble skrevet i **samme commit som modellen** —
vaktlistemodulen sto uten backup i det hele tatt fra den gikk i prod til 13. sep. 2026, og
det ble oppdaget ved en gjennomgang og ikke av noe rødt.

`backlog` står sist i rekkefølgen, og **plasseringen er vilkårlig**: modulen er den eneste
uten peker til `core.Vakt`, så den har ingen forutsetning om at portalfila er lastet først.
Begge brukerpekerne strippes (`opprettet_av`, `lost_av`) — med `natural_foreign` lagres de
som brukernavn, og er kontoen slettet feiler **hele** gjenopprettingen. Navnene står frosset
på raden og bærer opplysningen.

### Filteret

Serverens, med `?type=`, `?lost=` og `?modul=`. **Et ugyldig filter gir 400, ikke hele
lista:** `?lost=kanskje` ville ellers vist alt, og den som filtrerte ville lest det som at
det ikke finnes noen uløste. Et ukjent filter*navn* ignoreres derimot — en lenke fra en
gammel fane skal vise lista, ikke en feilmelding.

Telleren står i bildet hele tiden, også ufiltrert, så den ikke blir et signal man lærer seg
å overse. **Et filter skal aldri skjule noe stille.**

### Sekstenmutanter, alle drept — og to av dem løy først

Tungt på tilgangsregelen (`kan_endres`: forfattersjekken, løst-vilkåret, grensen av med én,
fristen målt fra endring), middels på portene (innmeldingsporten, løs-porten senket ett
trinn, `kan_endres` fjernet fra viewet, ugyldig filterverdi), middels på JS-funksjonene som
avgjør noe (`backlogNivaaMinst` invertert og av med én, `backlogTellertekst`, gatene i
byggeren), lett på escapingen.

**Én mutant hadde tom diff og ble meldt som overlevende** — søk-og-erstatt-strengen traff
ikke, fordi markupen er `'</strong></div>'` og ikke `'</strong>'`. Det er mutantløgn nr. 2 i
`CLAUDE.md`, en no-op, og den ble bare synlig fordi diffen leses. Kjørt på nytt med riktig
streng: drept.

### To feil funnet i egen kode underveis

- **`klokke()` gir bare klokkeslett.** Riktig for en vakt der alt skjedde i dag,
  misvisende i en backlog der et innspill kan være tre uker gammelt — «14:32» på noe fra
  forrige måned lyver med et tall som ser presist ut. Egen `backlogTidspunkt()`.
- **`toLocaleDateString` med `2-digit` er ikke stabil.** Den ga «17.9.» i node og «17.09»
  andre steder. Et format som skifter med ICU-versjonen er et format man ikke kan skrive
  en test på. Formateres nå for hånd, nullpolstret.

Og en tredje, i harness-en: `extract_function()` leser fra signaturen til første `}` i
kolonne 0, så en ettlinjes funksjon svelger den neste når den klippes ut. De to
nivågatene er derfor skrevet over flere linjer, med kommentaren som sier hvorfor.

Tallene fulgte med: 130 → 135 endepunkter, 24 → 25 JS-filer, sju → åtte backup-handlere,
fem → seks brukervendte moduler, `/backlog/` som kjent prefiks i `tallfasit` med egen rad i
`PAASTANDER`, og `backlog` i testkommandoen.

Suite: 3 339 tester, grønn.

---

## 2026-09-17 — De to valgene som blokkerer KO pulje 2, opp i toppen  `#core/dokumentasjon` `#ko/skallet`

Ingen kodeendring. De to åpne valgene om KO-loggen lå som barn under «Pulje 2 — loggen»,
og der var de riktig plassert så lenge pulje 2 var en idé ingen hadde tatt opp:
**«Krever Andre» betyr «blokkerer nå»**, og et valg inne i en upåbegynt idé gjør ikke det.

Nå tas pulje 2 opp, og da blokkerer de. De står derfor i toppseksjonen, som er den ene
lista André skal kunne stole på — og de er **skrevet om så de står på egne bein**, jf.
regelen i `CLAUDE.md`: et barn henter ofte meningen sin fra forelderen, og et punkt som
bare gir mening under overskriften det ble løftet fra, er et punkt ingen kan handle på.

De to:

- **Hvor lenge oppbevares KO-loggen, og skal den arkiveres?** Konflikten er innebygget:
  `NOTAT_DPIA_OG_FRITEKST.md` §7 sier at fritekst bevisst ikke arkiveres, mens et felt i
  et arkivs SHA-signatur er låst i 24 måneder ved konstruksjon — og §4.4 krever samtidig
  én smal sletteinngang. **Bygges loggen først, er svaret allerede gitt av konstruksjonen.**
- **Hvilke systemhendelser løftes inn i loggen?** Kuratert, ikke automatisk: «Enhet 3 satt
  til på stedet» hører hjemme der, «Enhetstype fikk nytt navn» gjør ikke. Lista skal være
  eksplisitt og begrunnet, som `NOKLER_UTEN_AUDIT`.

Det tredje valget — om en lukket hendelse skal kunne åpnes igjen — blir stående under
pulje 3, fordi det er der det blokkerer.

---

## 2026-09-17 — 97 entries merket: fra 200 grep-treff til 5 oppslag  `#core/dokumentasjon`

Mekanismen kom tidligere i dag; dette er merkingen som gjør den til noe. **13.–17. sep. er
merket — 97 entries, 15 temaer.** Det er der oppslagene faktisk gjøres.

**Målingen som viser hva det er verdt:**

| Spørsmål | Før | Nå |
|---|---|---|
| «Hva har skjedd med roller i vaktlista?» | `grep -i rolle` → **200 linjetreff** spredt over 84 entries | `--tema vaktliste/roller` → **5 entries** |

**Merket med en eksplisitt tittel-til-tema-tabell, ikke nøkkelordsgjetting.** Hver av de 97
titlene er lest og tilordnet for hånd. Skriptet krevde at **hver tittel i tabellen finnes i
CHANGELOG** — en skrivefeil ville blitt rød, ikke en stille ikke-merking. Alle 97 traff.
Nøkkelordsgjetting ville vært samme feilklasse som en skanner med falske funn: den ville
merket «rollemodellen» som `vaktliste/roller`, og da svarer temaet med entries som ikke
handler om det.

**Vokabularet ble utvidet fra 4 til 15 temaer — etter merkingen, ikke foran.** To temaer
manglet bøtte og kom til underveis: `core/audit` og `core/sikkerhet`. Sju andre fra
utkastet ble **ikke** registrert, fordi ingen av de 97 hørte til dem
(`patients/*`, `statistikk/kilder`, `oppdrag/verdimengder`, `oppdrag/arkiv`,
`vaktliste/besetning`) — de hører til halen, og registreres den dagen noen merker den.
`test_hvert_registrert_sokeord_er_i_bruk` håndhever rekkefølgen.

**Fordelingen sier noe om hvor arbeidet har ligget:** `core/dokumentasjon` 21,
`vaktliste/planlegging` 17, `core/backup` 17, `core/drift` 10, `core/sikkerhet` 6.

**182 entries står fortsatt umerket** — 29. aug. og bakover. Det er ført i `TODO.md` med
begrunnelsen for at det ikke haster: for halen duger tittelindeksen alene, og
`--umerkede` viser nøyaktig hva som gjenstår.

Suite: 3 296 tester, grønn.

---

## 2026-09-17 — Søkeord i CHANGELOG, så arkivet kan slås opp i  `#core/dokumentasjon`

**André:** «Hensikten med slike søkeord er jo at da slipper du lese hele changelog som er
gigantisk.» Han hadde rett, og jeg svarte først på feil problem.

**Det er to behov, ikke ett:**

| Behov | Virket før? |
|---|---|
| **Følge en peker** — «regelen viser til CHANGELOG 16. sep.» | Ja. 280 overskrifter, **null duplikate titler**, ett `grep` |
| **Ramse opp et tema** — «hva har skjedd med planleggeren?» | **Nei** |

**Målt, og verre enn antatt.** Arkivet er 11 651 linjer og 650 000 tegn. «Rolle» gir **84**
entries som nevner ordet og **seks** som handler om det. «Korps» 51 mot fire. «Offline» 35
mot to. `CLAUDE.md` sier at CHANGELOG `grep`-es og ikke leses, og det stemmer så lenge du
kjenner symptomet — «[object Object]» var søkbart fordi det sto der ordrett. Det holder
ikke når spørsmålet er et tema; da er arkivet i praksis stengt for den som ikke alt vet
hvor hun skal se.

**Formen er `` `#<app>/<tema>` `` i overskriftslinja**, ikke på en linje under: ett `grep`
skal gi dato, tittel og tema samtidig. Står søkeordet for seg selv, får du en naken streng
og må slå opp en gang til.

**App-halvdelen utledes, tema-halvdelen registreres.** Appen er en ekte Django-app og
validerer seg selv, så en ny modul er dekket fra dagen den finnes. Temaene står i `TEMAER`
i `core/changelog.py` — et vokabular uten register er en håndholdt liste, og de forfaller
i stillhet: `#vaktliste/planlegger` og `#vaktliste/planlegging` ville vært to temaer ingen
la merke til at var ett, og det ene ville svart med halvparten.

**To regler som peker hver sin vei**, i `core/tests_changelog.py`:

- Hvert søkeord i bruk er registrert — fanger skrivefeilen.
- Hvert registrert søkeord er i bruk — speilet, og den som betydde noe her.

**Den andre regelen tok min egen første versjon.** Jeg registrerte tjue temaer og hadde
merket fire; testen meldte seksten døde. Det er ikke pedanteri: `--temaer` ville vist
seksten rader med null, og et søk som svarer med ett treff der det finnes fem får deg til
å tro du har sett alt. Samme feilklasse som en skanner som melder grønt om en dekning den
ikke har. **Vokabularet skal vokse med merkingen, ikke foran den** — og testen håndhever
rekkefølgen.

Fire entries er merket. Resten er ført i `TODO.md` med utkastet til temaer, og med
rekkefølgen: ta 13.–17. sep. først, der oppslagene faktisk gjøres.

**For halen bakover finnes kommandoen nå:**

```powershell
python manage.py changelog                  # alle titlene — 280 linjer mot 11 651
python manage.py changelog --temaer         # vokabularet, med antall per tema
python manage.py changelog --tema ko/skallet
python manage.py changelog --app vaktliste
python manage.py changelog --umerkede       # hva som gjenstår
```

Sperrehaker: parseren må finne over 200 entries, titlene må være unike (pekeren skal ikke
være tvetydig), halen må leses ut av overskriften **og** en tittel uten søkeord må fortsatt
gi hele tittelen — ellers ville de umerkede mistet navnet sitt i parsingen.

Suite: 3 296 tester, grønn.

---

## 2026-09-17 — Vaktlistefila fikk seksjoner, og vakten fikk noe å peke på  `#core/dokumentasjon`

**Oppgaven var «del `vaktliste/CLAUDE.md`», og den ble ikke løst slik.** Tre funn i
rekkefølge, og hvert av dem snudde planen:

**1. En fil ved siden av modulfila lastes ikke.** `vaktliste/CLAUDE.md` leses når noen
arbeider i `vaktliste/`; `vaktliste/drift.md` leses av ingen. En filsplitt ville flyttet
reglene til et sted der de bare finnes for den som vet at de finnes — nøyaktig fella
prosjektet dokumenterer i sin egen innledning, der to-grener-regelen sto i en deploy-guide
som ikke lastes.

**2. Det var ikke noe fett å skjære bort.** Hele fila ble lest før noe ble rørt. Hvert
avsnitt bærer en regel **og** feilen som lærte oss den — `readOnly` som ikke virker på
`datetime-local`, `nulls_last` som skiller SQLite fra PostgreSQL, `splice(2, …)` mot en
liste som ennå ikke hadde fått «Mannskap». Å hente tusen tegn ved å stryke «hvorfor» ville
gjort fila kortere og dokumentasjonen dårligere, og det er akkurat det
`core/tests_claude_md.py` advarer mot i sin egen docstring: grensa «kan tilfredsstilles ved
å slette noe nyttig».

**3. Den ekte defekten var ikke størrelsen.** **707 av 736 linjer lå under én
overskrift.** Et flatt punktliste på den lengden har ingen steder ting hører hjemme, så alt
havner nederst — og ingen kan se hvilken del som vokser. Størrelsen var symptomet.

**Fila har nå 13 seksjoner der den hadde én**, største 109 linjer: tilgang, plassen og
skiftet, vakta og tidene, registrene, kompetanse og roller, planleggingsflatene, tabeller
og felter, besetningen mot `/oppdrag/`, belastning og budsjett, innsjekk og drift,
planleggeren, drift-reserven, frontend.

**Omstokkingen ble gjort av et skript som beviste at ingenting gikk tapt.** Fila ble
parset i blokker, hver blokk tilordnet en seksjon, og skriptet krevde at hver linje ble
brukt **nøyaktig én gang** og at mengden av ikke-tomme linjer var identisk før og etter.
Det er den eneste måten å stokke om 736 linjer uten å risikere at en regel forsvinner i
redigeringen. Ingen setning er endret.

**Prisen er 1 056 tegn** (55 743 → 56 799) for overskriftene og seksjonsingressene. Det er
en bevisst byttehandel: en fil man kan lete i, og en vakt som kan si *hvilken* del som
vokser. Pinnen i `FOR_STORE_I_DAG` er justert, og begrunnelsen står i koden.

**To nye regler — og det er den første som ville fanget vaktlista i august:**

| Regel | Hva den fanger |
|---|---|
| `test_en_stor_modulfil_maa_ha_seksjoner` | En modulfil over 8 000 tegn må ha minst tre `## `-seksjoner. Måler **årsaken** (ingen struktur), ikke bare symptomet (størrelse) |
| `test_ingen_enkeltseksjon_blir_en_monolitt` | Ingen seksjon over 9 000 tegn. Uten den er neste feil den forrige med et hakk mer struktur: én seksjon som eter resten |

**Og regelen fant med en gang en fil til:** `oppdrag/CLAUDE.md` er 17 275 tegn under
**én** overskrift — samme flate vegg, bare mindre. Den står i `UTEN_SEKSJONER_I_DAG` med
begrunnelse og et punkt i `TODO.md`. Statusmaskinen, verdimengdene, bilens utganger og
historikk-mot-arkiv er fire ting.

**Tre mutanter, alle drept:** unntaket for oppdragsfila fjernet (regelen må fyre), to
seksjoner slått sammen til én på 15 766 tegn (monolittregelen må fyre), og `_seksjoner()`
satt til å lete etter `#### ` slik at den finner null (sperrehaken må fyre).

Suite: 3 288 tester, grønn.

---

## 2026-09-17 — Rota kartlegger, modulfila forklarer — og vaktene måler tegn  `#core/dokumentasjon`

Ingen kodeendring, bare dokumentasjon og de testene som holder den i live.

**Utløseren var at `CLAUDE.md` sto fire linjer fra `ROT_GRENSE`.** Gjennomgangen viste at
grensa målte feil ting. To rader i frontend-tabellen hadde vokst til **888 og 652 tegn** —
lydvarselets terskler, offline-køens ventetid, vaktlistas faneoppsett og skjøten mellom
`tegning` og `oversikt`. Det er to hele modulavsnitt, skrevet som **to linjer**. En
linjetelling så to; konteksten betalte ~470 tokens. Og `test_ingen_modul_har_sitt_eget_avsnitt_i_rota`
så ingenting i det hele tatt, fordi den leter etter overskrifter av formen
`### Noe (oppdrag/)` og en tabellrad ikke har noen.

**Modulstoffet er flyttet dit det hører hjemme.** Rota beholder *når* en fil lastes — det
er en grense mellom moduler — og modulfila forklarer hva den gjør:

| Hvor | Hva som kom |
|---|---|
| `patients/CLAUDE.md` | De fem filene, og at alt en ikke-admin kan nå må ligge i en alltid-lastet fil |
| `oppdrag/CLAUDE.md` | Sentralbordets fire filer, og enhetsskjermen: knappene, offline-køen, lydvarselet, og at tida måles fra bilens `varslet_at` |
| `vaktliste/CLAUDE.md` | De seks filene, og hvorfor skjøten går mellom regnearket og oppsummeringene |
| `statistikk/CLAUDE.md` | De to filene, `_kallOppdrag`-gaten, og at tabellene rulles på beholderen |

**Målingen som forklarer hele saken:** etter flyttingen gikk rota **opp** to linjer og
**ned** 1 751 tegn. Under den gamle grensa så oppryddingen altså ut som en forverring.
Derfor måler grensene nå tegn: `ROT_TEGNGRENSE = 65 500` mot dagens 62 338.

**Modulfilene har fått sitt eget tak** — `MODUL_TEGNGRENSE = 22 000`. Delingen 15. sep.
flyttet 574 linjer ut av rota og satte ikke noe tak på der de havnet, og «flytt det til
modulfila» er et svar som virker helt til modulfila er den nye monolitten.
`vaktliste/CLAUDE.md` er 55 743 tegn og står som **navngitt unntak** i `FOR_STORE_I_DAG`,
pinnet på dagens størrelse: fila kan krympe, ikke vokse. `test_unntakene_blir_ikke_slakke`
krever at taket følger den nedover, ellers ville «vi rydder i vaktlista» kunne gjøres
halvveis uten at noe merket det. Selve delingen står i `TODO.md`.

**`RotaKartleggerBareTests` fanger tabellraden.** Regelen er bevisst *ikke* «ingen
modulnavn i rota» — en gjennomgang fant femten slike, og **alle femten var riktige**: rota
må kunne skrive `patients/tests_modul_dekorator.py` når den forklarer at hvert view skal
være dekorert, og `oppdrag.Enhet` når den forklarer unntakslista i avhengighetsretningen.
En test med falske funn blir slått av. Regelen er derfor smal: navngir første celle i en
tabellrad en fil modulen eier, skal raden være et oppslag og ikke en beskrivelse (200
tegn). Eierskapet **utledes** av filnavnet mot modulene som har egen fil — `ko.js` var
dekket før noen skrev regelen.

**Én ting ble rettet i rota fordi den var en dublett på vei til å bli to:**
«last ikke `patients-utils.js` utenfor pasientsiden» ble først flyttet til
`patients/CLAUDE.md` — men det er en regel for *andre* moduler, og den som bygger `/ko/`
leser ikke pasientmodulens fil. Den står i rota. Samme vurdering tok CSP-ens `media-src`
tilbake fra `oppdrag/CLAUDE.md`: den er portalens header, ikke oppdragsmodulens.

**Ni mutanter: sju drept, to vakuøse.** Den som betydde noe:
`FOR_STORE_I_DAG['vaktliste/CLAUDE.md']` var satt fra `wc -c`, som teller **bytes** — og
æ, ø og å er to hver i UTF-8. Pinnen sto 1 441 tegn for høyt og lot fila vokse fritt;
mutanten som la 1 150 tegn til vaktlistefila **overlevde**. Alle tre tallene er nå målt i
tegn slik testen måler dem. De to vakuøse er mutasjoner av selve assertion-vilkåret
(`if tegn >= tak` → `if False`), og de sier ingenting så lenge det ikke finnes brudd å
finne: **den meningsfulle mutasjonen for en vakt er å innføre bruddet den skal fange.**
Det er nettopp det sperrehakene `test_regelen_finner_faktisk_rader` og
`test_ingen_modulfil_er_uten_tak` finnes for.

Suite: 3 278 tester, grønn.

---

## 2026-09-17 — KO-modulen, pulje 1: skallet  `#ko/skallet` `#core/tilgang`

**`/ko/` finnes.** Modulen er registrert, siden har de fire flatene fra `FORSLAG_KO.md` §7,
sidebaren over hvem som har KO oppe virker, og `ModulTilgang('ko')` slipper folk inn. Ingen
data, ingen modeller, ingen migrasjon. Puljen er først fordi **tilgangen må virke før noe
legges bak den** — og da er det tilgangen som må prøves, ikke at siden rendrer.

Nye filer: `ko/module.py`, `ko/views.py`, `ko/urls.py`, `ko/tilstede.py`, `ko/models.py`
(tom, med begrunnelse), `ko/CLAUDE.md`, `templates/ko/index.html`, `static/js/ko.js`,
`core/sesjoner.py`. Ruter: `/ko/` og `/ko/api/tilstede/`.

**Modulen deklarerer bare `les`, og det er et valg og ikke en forglemmelse.** Notatets §5.1
nevner fire nivåer; skallet har ingen skriveendepunkter. Et nivå som ikke gir noe er lett å
dele ut i god tro — nøyaktig feilen den globale nivålista gjorde mot `statistikk`, som står
dokumentert i `core/modules.py`. Her er den verre enn der: `statistikk` har aldri fått
skriving, så et utdelt `skriv_full` ble liggende dødt. Et `skriv_full` på `ko` i dag ville
ligget i basen og **trådt stille i kraft** den dagen pulje 2 landet, uten at noen tok den
avgjørelsen da. Hver pulje legger til sitt nivå i samme commit som nivået får mening.
Avklart med André 17. sep.

**Tre innvendinger mot notatet, meldt før koden:**

| Notatet sa | Det som ble bygget | Hvorfor |
|---|---|---|
| Sidebaren er «`_list_active_sessions` filtrert på `ModulTilgang('ko')`» | `har_tilgang`-semantikk i mengdeform, `ko/tilstede.py` | **Global admin har ingen `ModulTilgang`-rader.** Filteret ville utelatt nettopp den som sitter i KO og administrerer portalen — hun ville sett alle andre og ikke seg selv, og lista hadde sett helt riktig ut |
| (usagt) Radene er adminradene | Egen, smal projeksjon uten `session_key` | `session_key` er håndtaket `admin_session_kill` **avslutter** en sesjon med. Et felt hvis eneste bruk er destruktiv skal ikke ligge i et svar enhver operatør henter hvert 30. sekund og vente på at noen finner ut hva det er |
| «Tom side med de fire flatene» | Hver flate sier hva som kommer, i hvilken pulje, og hvor tingen bor i dag | En blank «Oppdragsliste» ser ødelagt ut mens sentralbordet fortsatt står på `/oppdrag/`. Samme regel som «en knapp som fører til en vegg», fra den andre siden: **en flate som ikke forklarer seg, leses som en feil** |

**Sesjonsloopen flyttet til `core/sesjoner.py`** fordi den nå har to lesere. Adminflatens
`_list_active_sessions` bygger på den og beholder sin egen projeksjon (`session_key`,
`role`); KO har sin. Primitivet er delt, projeksjonen er ikke — og det er hele poenget med
fila. `_inaktiv_sekunder` heter nå `core.sesjoner.inaktiv_sekunder`.

**Sidebaren viser én rad per person, ikke per sesjon.** Adminlista på server-status lister
*sesjoner*, fordi den skal kunne avslutte én av dem. Denne svarer på hvem som er der, og
samme operatør med KO på PC-en og på telefonen er én person. `inaktiv_s` blir den ferskeste
av fanene: står den ene urørt i to timer mens den andre brukes, er personen til stede. En
delt konto er merket «delt» — «Enhet 2» og «Kari Nordmann» betyr fundamentalt ulike ting,
og blir lista noen gang lest i en personalsak er den forskjellen alt (§4.5).

**Avhengighetsretningen er håndhevet fra dag én**, ikke fra den dagen KO får en modell.
`ko/tests_avhengighet.py` leser importene med AST og krever at ingen modul under KO
importerer den — `ko` → `vaktliste` og `ko` → `oppdrag`, aldri motsatt. Testen bor i `ko/`
av samme grunn som `OppdragImportererIkkeVaktlista` bor i `vaktliste/`: det er den
importerte som mister uavhengigheten sin. `core/tests_avhengighetsretning.py` har `ko` i
`MODULAPPER`, og `core/modules.py` → `ko.module` er den ene tillatte importen.

**16 mutanter, alle drept — men tre av dem var grønne til testene ble skrevet.**
Den dyreste: fjernes `modul_slug=SLUG` fra spørringen i `_har_ko_tilgang_ider`, overlevde
mutanten, fordi den eneste testen som prøvde en konto uten KO-tilgang brukte en konto uten
*noen* rader. Den faller ut uansett. Feilen mutanten slapp gjennom er at **hvem som helst
med tilgang til én modul ville stått oppført som til stede i KO**. De to andre var
`_laveste()` — `min` → `max`, og `None` som vinner — som begge ville fått lista til å melde
fravær om noen som satt der. Mutantene gikk på tilgangsfilteret (tungt lag), portene i
viewene og de to JS-funksjonene som *avgjør* noe: `koInaktivTekst()` og `koKontomerke()`.
`koTegnTilstede()` er tegning og ble ikke mutert, jf. tabellen i `CLAUDE.md`.

**Tallene i dokumentene fulgte med:** 128 → 130 endepunkter, `/ko/` er et kjent prefiks i
`core/tallfasit.py` med egen rad i `PAASTANDER`, 23 → 24 JS-filer, fire → fem brukervendte
moduler, og `ko` står i testkommandoen i `CLAUDE.md` (`TestkommandoenDekkerAltTests` ville
ellers sagt fra). `ko/CLAUDE.md` er ført opp i `DOKUMENTER` og i tabellen «Hvor
dokumentasjonen bor».

**Modulen er synlig i nav og på dashbordet fra pulje 1** (avklart med André). Uten en dør i
menyen kan man ikke verifisere at tilgangen virker uten å skrive `/ko/` manuelt, og det er
nettopp det puljen finnes for. `ensure_defaults_exist()` slår modulen på automatisk
(`ModuleSettings.enabled=True`); den kan slås av på `/portal-admin/moduler/`.

**Rota er nå 996 av 1 000 linjer** (`ROT_GRENSE` i `core/tests_claude_md.py`). Fire linjer
igjen er et punkt i `TODO.md`, ikke et problem i dag — men neste rammeverksregel får ikke
plass uten at noen tar et valg.

Suite: 3 275 tester, grønn.

---

## 2026-09-17 — Planforslag for KO-modulen, og datteroppdrag forkastet  `#ko/skallet`

Ingen kodeendring. `docs/FORSLAG_KO.md` er et planforslag (ikke besluttet) etter en
gjennomgang med André 16.–17. sep.: **KO-modulen** — situasjonsbildet med ressursoversikt,
oppdragsliste, logg/chat, hendelser og en sidebar over påloggede med KO-tilgang.
`/oppdrag/` snevres inn til enhetens egen skjerm, og **sentralbordet flytter til KO** som
en flytting av `oppdrag-sentral-*.js`, ikke en kopi.

**`docs/FORSLAG_DATTEROPPDRAG.md` er arkivert — erstattet, ikke gjennomført.** Notatet fra
13. sep. foreslo `Oppdrag.forelder` og forkastet i §2 uttrykkelig en egen hendelsestabell,
med begrunnelsen «Moren *er* et oppdrag med biler og stemplinger før noen vet hvor mange
pasienter det er». Den begrunnelsen holdt **så lenge oppdraget var øverste nivå**. I KO er
premisset snudd: hendelsen finnes *før* oppdraget, ofte uten oppdrag i det hele tatt, og
den dekker i tillegg lag — som datteroppdrag aldri kunne. Hele resonnementet står i
`FORSLAG_KO.md` §9.3. Det åpne spørsmålet i det gamle notatets §7 (hva skjer med morens bil)
faller bort med modellen.

`docs/archived/README.md` har fått en ny kategori, **«Forslag som er erstattet»**, og
datteroppdrag-notatet er det eneste dokumentet der som har fått et banner på toppen.
Grunnen: de andre arkiverte dokumentene beskriver gjennomført arbeid, og det leser man seg
til. Et forkastet forslag leser nøyaktig som et levende forslag, og den som finner det ved
å søke på «datteroppdrag» har ingen grunn til å åpne indeksfila først.

**Gjennomgangen fant seks ting som allerede var bygget** (`FORSLAG_KO.md` §2). `Ressurs.enhet`
— koblingen mellom vaktlistas ressurs og oppdragsmodulens enhet — er den viktigste: den er
grunnlaget for hele ressursoversikten i KO, og den har ligget der siden fase 6.
`CustomUser.er_delt_konto`, `Ressursgruppe` («samleplass, ambulanse, mannskapsbil, lag» —
docstringen nevner KO selv), `Enhetstype`-flaggene, `neste_oppdragsnummer()` og
`_list_active_sessions` er de fem andre. Mønsteret er nå navngitt i notatet: **før noe
designes inn i KO, sjekk om vaktlista, oppdrag eller kontoappen allerede har begrepet.**

De viktigste rammene som ble lagt:

| Valg | Kort begrunnelse |
|---|---|
| **Enheter produserer tid, lag produserer utfall** | Setningen som fordeler ansvaret mellom `/oppdrag/` og `/park/`. Lagdata skal aldri havne i en responstidsstatistikk — ikke «mangler data», men «måler ikke det» |
| Ressursoversikten er en **projeksjon**, ikke et register | Et eget KO-register ville gitt to navn på samme bil midt i en vakt. §9.1 |
| **Én logg**, chat og hendelseskommentarer som linjer i den | Er chatten et eget sted, kommer dagen da den viktigste setningen ble sagt der og ikke står i loggen. §4.5 |
| Loggen sorteres på **registreringsrekkefølge**, ikke på `tidspunkt` | En korrigert tid flytter ellers linja, og fortellingen blir uleselig — og det er som fortelling loggen har verdi. §4.3 |
| Én smal, logget **sletteinngang** | Append-only og «fjern personopplysninger» står i direkte konflikt. Billig fra start, vond å ettermontere. §4.4 |
| To nummerserier, **aldri omnummerert** | `H12` og `O45`, begge per vakt. Hierarkisk `H12.1` er forkastet: et oppdrag knyttes ofte til en hendelse i etterkant, og **et nummer som endrer seg er ikke en identifikator**. §6, §9.4 |
| Ansvarsområde **vises**, tilgangsnivå **styrer** | Å la området gi tilgang dobler matrisen, og første gang den rette er opptatt møter du en vegg. §5.1 |
| Hold KO **påføringsformet** | Flere operatører fungerer i `/oppdrag/` i dag fordi arbeidet der er nye rader. Polling holder så lenge det er sant; WebSockets er et infrahopp uten gevinst her. §7.1 |
| De tre registrene teller **kontakter, ikke personer** | Én person kan bli registrert i `/park/`, i `/oppdrag/` og på samleplass. Summert blir 210 mennesker til 340 «pasienter». Ordet i overskriften er det eneste som hindrer feilen. §8 |

`Oppdrag` får én nullbar FK til `Hendelse`; `ko` importerer `vaktliste` og `oppdrag`, ingen
av dem importerer `ko`. KO blir øverste lag, og begge kantene skal håndheves med AST slik
`OppdragImportererIkkeVaktlista` gjør i dag.

Tre spørsmål står åpne i §11 og er lagt i `TODO.md` under «KO-modulen», hvert med hvilken
pulje det må besvares før: oppbevaring/arkivering av loggen, hvilke systemhendelser som
løftes inn i den, og om en lukket hendelse kan åpnes igjen. De står som «Åpent valg» og
ikke under «Krever Andre» — modulen er upåbegynt, og seksjonen øverst er det som blokkerer
*nå*.

**To regler inn i `CLAUDE.md`.** Den første er lærdommen over, som regel: *sjekk om
begrepet finnes før du designer det, og les koden før du hevder noe om den* — egen kort
seksjon foran «Commands», med de seks funnene som belegg.

Den andre er et hull som ble synlig da promptmalen for en ny KO-sesjon skulle skrives:
**`rollemodell` er staging, `main` er prod, og det sto ingen steder i `CLAUDE.md`.** Bare i
`docs/DEPLOY_GUIDE.md` §9 — en fil som ikke lastes med mindre noen åpner den. Samtidig sa
SHA-avsnittet i `CLAUDE.md` allerede «bygg nr jeg kommer til å se på staging/prod», altså
brukte et begrep fila aldri innfører. En ny sesjon kunne lese hele `CLAUDE.md` og likevel
ikke vite hvor den skulle pushe.

Ryddet med: `docs/PLAN_REKKEFOLGE_2026-09.md` (trinn 5 strøket, banner om at trinn 1–4 er
gjennomført), `docs/FORSLAG_RAPPORTMODUL.md` (peker nå på `FORSLAG_KO.md` som eksempel på
`FORSLAG_*`), `core/tests_todo.py` (docstringen pekte på datteroppdrag-punktet som mønster
for «Åpent valg»). `- [ ] Vaktliste` og `- [ ] KO-tavle` er fjernet fra «Framtidige
moduler»: vaktlista står i prod, og KO har fått sin egen seksjon.

---

## 2026-09-16 — Resten av pulje 3 og sesjonsaktiviteten ut i prod  `#vaktliste/planlegging` `#core/drift`

Fire commits, `d16b6f6` → `0405a17`, verifisert på staging:

| Bygg | Hva |
|---|---|
| `bbc13cd` | Punkt 3 brutt — korpsdelen var alt løst av `Ressurs.korps` |
| `1499b49` | Fanerekka i to bolker; «Mitt korps» sto inne i gruppeblokka |
| `4e03b17` | Funnet: «pålogget» er ikke «til stede», og hvorfor |
| `0405a17` | Sesjonslista viser om det sitter noen der |

**Ingen migrasjoner.** Release-fasen rører ikke skjemaet, så deployen er bare et
containerbytte.

Én ting å vite om første oppstart: sesjonene som alt er i gang har ingen
`siste_interaksjon`, og viser derfor **«ukjent»** til eieren gjør noe. Det er med vilje —
«vet ikke» skal kunne skilles fra «aktiv nå», og alternativet hadde vært å la hver gammel
sesjon se ut som om noen satt der.

Suiten grønn på `0405a17`: 3 243 tester.

---

## 2026-09-16 — Sesjonslista viser nå om det sitter noen der  `#core/drift`

**André:** «Enig med polling for å vise hvem som er aktiv nå — og så må jeg fortsatt se alle
som er innlogget.»

Begge deler. **Aktiviteten er en kolonne, ikke et filter:** en fane som har stått i to timer
er nettopp den man leter etter, og et filter ville skjult den. Linja under lista sier begge
tallene — «7 påloggede · 3 aktive nå».

### Fana bærer svaret selv

`apiFetch` sender `X-Portal-Inaktiv` med sekunder siden siste
`pointerdown`/`keydown`/`wheel`/`touchstart`. `BrukerAktivitetMiddleware` regner om til et
tidspunkt i sesjonen. **Ingen ny trafikk og ingen ny tabell** — feltet henger på en
forespørsel som alt går, og `_list_active_sessions` dekoder alt sesjonsdataene.

Fire valg som hver kunne vært en stille feil:

- **Sekunder, ikke et tidspunkt.** Da slipper serveren å stole på klientens klokke, som kan
  stå hvor som helst på en delt drifts-PC.
- **Manglende header = 0, altså «en handling».** Sidelastinger og skjemainnsendinger går
  ikke gjennom `apiFetch`, og *de* er nettopp det et menneske gjør. Pollingen har headeren,
  og det er den som skal kunne se gammel ut.
- **`None` og ikke 0 for «vet ikke».** En sesjon fra før middlewaren fantes må kunne skilles
  fra «aktiv nå» — ellers ser hver gammel sesjon ut som om noen sitter der.
- **`scroll` teller ikke som interaksjon.** Treghetsrulling på mobil fyrer lenge etter at
  fingeren er borte, og ville gjort en glemt fane «aktiv» i et halvt minutt av seg selv.

Serveren klipper dessuten verdien: negativt blir null, og taket er 48 timer. To sperrer i
stedet for én er billigere enn å finne ut hvilken som sviktet.

### Ti mutanter, alle røde

Blant dem «manglende header blir ukjent i stedet for en handling» og «klienten måler fra
feil punkt» — de to som ville gjort hele kolonnen feil uten å se ødelagt ut.

### Og ett punkt droppet

«Må kunne fordele til hele enheten/laget» er ute av TODO — André: «jeg skjønner den ikke».
Den sto med to mulige lesninger og ingen av dem var hans; et punkt ingen kan forklare er
et punkt som blir liggende og se ut som gjeld.

**Endret:** `core/middleware.py`, `core/admin_status.py`, `static/js/portal-utils.js`,
`templates/patients/admin_status.html`, `myproject/settings.py`,
`core/tests_brukeraktivitet.py` (ny, 14 tester), `CLAUDE.md`, `TODO.md`.

---

## 2026-09-16 — Hvorfor «pålogget» ikke betyr «til stede»  `#core/drift`

**André:** «I /server-status/ ser du hvem som er pålogget, men de trenger ikke være faktisk
aktive og bruke nettsiden — det kan være en fane.»

Han har rett, og grunnen lot seg måle i stedet for å gjettes:

- `SESSION_SAVE_EVERY_REQUEST = True` — sesjonen fornyes ved **hver** forespørsel.
- Portalen poller av seg selv hvert **5.–30. sekund**: lydvarselet 5 s, offline-køen 15 s,
  tavla og auto-refresh 30 s.

En glemt fane holder derfor sesjonen fersk i åtte timer, helt uten et menneske. `expire_date`
er ikke et dårlig mål på tilstedeværelse — det er **ikke et mål på det i det hele tatt**.

Det avgjør også spørsmålet som sto åpent i TODO («hva er aktiv — siste forespørsel eller
siste skriving?»): **ingen av dem.** Siste forespørsel er polling. Siste skriving er for
strengt — en vaktleder som leser lista i en time arbeider.

**Forslaget som står igjen: la pollingen bære svaret.** Fana snakker med serveren uansett;
la den sende hvor lenge siden brukeren sist rørte siden. Ingen ny polling, ett felt på en
forespørsel som alt går — og det er det ene tallet som svarer på spørsmålet.

Ingen kode skrevet. Funnet og forslaget står i TODO, sammen med det som må avgjøres før
noen bygger: om en inaktiv sesjon skal logges ut automatisk, eller bare vises. Automatikk
midt i en vakt er en risiko — bilen som ikke har rørt skjermen på en time er fortsatt på
vakt.

**Endret:** `TODO.md`. Ingen kodeendring.

---

## 2026-09-16 — Pulje 3 punkt 5: fanerekka er to slags ting, og sto som én  `#vaktliste/planlegging`

**André:** «De faste fanene skal se annerledes ut enn ressursgruppefanene. I dag ser
«Oversikt» og «Ambulanse» like ut, og de er to ulike slags ting.»

### Først en feil som gjorde oppgaven umulig

Fanerekka så slik ut med to grupper:

```
Oversikt · Mannskap · Ambulanse · Mitt korps · Lag · Timeoversikt · …
```

**«Mitt korps» sto inne i gruppeblokka.** Rekka ble bygget med `push` og så
`splice(2, 0, …)` for «Mitt korps» og `splice(1, 0, …)` for «Mannskap» — men indeks 2 var
regnet mot en liste som ennå ikke hadde fått «Mannskap». Med én gruppe så det riktig ut;
med to landet den midt inni.

Ingen test så det, fordi **ingen test leste rekkefølgen** — bare at hver fane fantes. Og
to slags faner kan ikke gis hvert sitt utseende så lenge de står om hverandre, så dette
måtte rettes før utseendet ga mening.

### Tre bolker i stedet for indeksregning

```
Oversikt · Mannskap │ Ambulanse · Lag · + Ny ressurs │ Mitt korps · Timeoversikt · Planlegger · Ikke plassert
```

«Ny ressurs» flyttet inn i gruppebolken — den lager en ressurs, og ressursene er det
bolken handler om.

### Utseendet: form, ikke farge

Gruppefanene får fylt flate, tydeligere kant og halvfet skrift. **Ikke en ny farge:** i
denne modulen varsler gult, grønt er tilstede og blått er valgt. En farge til ville vært
et signal som konkurrerte med dem. Formen var ledig.

Skillene tegnes bare når det finnes grupper — en strek mot ingenting er en strek man lurer
på.

### Sju mutanter, alle røde

Blant dem den som setter flettingen tilbake. `FanerekkaHarToBolkerTests` pinner hele rekka
i sin helhet, så en ny fane lagt til feil sted blir rød der i stedet for å bli oppdaget på
staging.

**Endret:** `static/js/vaktliste-tegning.js`, `static/css/vaktliste.css`,
`vaktliste/tests_belastning.py` (+4), `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Punkt 3 brutt: korpsdelen var alt løst  `#vaktliste/tilgang`

**André:** «Bryt dette og bare sett det i TODO for noe å vurdere senere. Det fungerer
forsåvidt når det gjelder korps og du går inn på rediger ressurs og setter korps der.»

Han har rett, og det er verdt å skrive ned *hvorfor* — punktet var formulert som «sett
korps og rolle på flere skift samtidig», og halve det er en funksjon som har vært der hele
tiden: `Ressurs.korps` er standarden for **alle** plassene på ressursen
(`services.reservert_korps`), så «Rediger ressurs» *er* bulkoperasjonen for korps.
`Vaktpost.korps` overstyrer per plass, og finnes for samleplassen som deles mellom korps —
unntaket, ikke normalen.

Det som faktisk gjenstår er **rollen**, som bare finnes per plass. Ingen kode skrevet;
punktet står i TODO med de tre åpne spørsmålene og et forslag om å se på en standardrolle
på ressursen først — er «Lag 1» alltid én lagleder og tre lagsmedlemmer, er det oppsettet
som gjentar seg, ikke en handling man gjør om igjen.

**Endret:** `TODO.md`. Ingen kodeendring.

---

## 2026-09-16 — Pulje 3A og 3B ut i prod  `#vaktliste/planlegging` `#vaktliste/roller`

Sju commits, `64f62a3` → `5b9ac15`, alle verifisert på staging av André:

| Bygg | Hva |
|---|---|
| `4cc042a` | «Planlegging»-fanen heter «Timeoversikt» |
| `3325c8d` | «Oversikt» ble en faktisk oversikt — tid, timer, plasser, besatt, ledige, totalt |
| `55c5fb8` | Ressursgruppene kan endres og deaktiveres; rollene rangeres |
| `d8d08c4` | Regresjonstester for rollerekkefølgen |
| `d2af252` | Roller kan døpes om, med én form for navneendring i modulen |
| `f3c1aa4` | Laget sorteres etter rolle, ikke etter når radene ble laget |
| `5b9ac15` | Tidskolonnen i «Oversikt» er en celle igjen |

**To migrasjoner, og bare én rører data.** `0020` endrer bare `Meta.ordering`.
`0019` legger til `Ressursrolle.rekkefolge` og sprer dagens alfabetiske rekkefølge utover
med ti — **skjema først, data etterpå**, altså den trygge retningen: regelen om
PostgreSQLs triggerkø gjelder migrasjoner som skriver rader og *deretter* endrer skjema.

Ingenting flytter seg av migrasjonen. Rollene står som før til noen bruker pilene.

Suiten grønn på `5b9ac15`: 3 225 tester.

---

## 2026-09-16 — «Kolonnen tid viser seg annerledes, samt linjen er ujevn»  `#vaktliste/planlegging`

**Meldt fra staging (André)** om «Oversikt»-fanen jeg bygget noen timer før. Cella hadde
fått `.vl-blokktid` — en klasse laget for et `<span>` på en blokklinje, med
`display: inline-block`, `font-weight: 700` og `margin-right`. På en `<td>` tar
`inline-block` cella ut av kolonnesporet, og marginen skyver innholdet.

Regelen står i `vaktliste/CLAUDE.md` og er håndhevet av en test som heter
`TabellcellersLayoutTests`. Den så det ikke — **av to grunner**, og begge er verdt å
skrive ned.

### 1. Byggerlista var håndholdt

Testen leste `<td class="…">` fra seks navngitte byggere. `blokkrad` i den nye «Oversikt»
sto utenfor. **Tredje gang på ett døgn** at en håndholdt byggerliste er svaret på «hvorfor
var ingenting rødt» — etter `_enhetskort` i XSS-skanneren og de ni byggerne der. Nå leses
hele kilden.

### 2. Svartelista manglet nettopp den verdien

`FARLIGE` var `flex`, `grid`, `inline-flex`, `inline-grid`, `block` — og ikke
`inline-block`. Så da lista ble utvidet til å finne klassen, sa regelen fortsatt at den var
grei.

Enhver `display` som ikke er `table-cell` tar cella ut av kolonnesporet. En svarteliste må
være **komplett** for å virke, og den var det ikke. Den er nå en **hvitliste** —
`table-cell`, eller ingen `display` — som er komplett av seg selv.

### Og navnet jeg først valgte var opptatt

`.vl-tidcelle` finnes fra før, med `display: flex`, på en `<div>` *inne* i regnearkets
tidskolonne — helt riktig der, for den er ikke cella. Testen fanget kollisjonen i samme
kjøring. «Oversikt» har nå sin egen `.vl-oversikt-tid` uten `display` og uten margin.

### Fem mutanter — og tre av dem overlevde først

Alle tre var mutasjoner på **testen**, ikke på koden: hvitlista kunne slakkes,
byggerlista snevres inn, og sperrehaken tømmes, uten at noe ble rødt. Regelen lot seg bare
prøve mot den *ekte* CSS-en, og der er den grønn så snart koden er riktig.

Sjekken er derfor skilt ut som `_funn(css, klasser)` og prøves mot en **kjent-dårlig**
CSS-snutt for hele familien av verdier, og dekningen pinnes med to klasser som bare finnes
i den nye byggeren. Den gamle «fant vi noen klasser i det hele tatt»-testen er fjernet:
den nye er strengere, og en test med én assertion overlever alltid at assertionen fjernes
med mindre noe tester testen.

**Endret:** `static/js/vaktliste-oversikt.js`, `static/css/vaktliste.css`,
`vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Laget sorteres etter rolle, ikke etter når radene ble laget  `#vaktliste/roller`

**André:** «Det er en enhet/lag som har i synkende rekkefølge: lagsmedlem, lagleder,
lagsmedlem, hospitant. Når jeg justerer på førstenevnte så flyttes den ikke i enheten etter
sin rolle.»

Reprodusert med hans egne fire plasser: `Lagsmedlem, Lagleder, Lagsmedlem, Hospitant` — ren
innsettingsrekkefølge. Etter: `Lagleder, Lagsmedlem, Lagsmedlem, Hospitant`.

### Rangeringen styrte nedtrekket, ikke radene den beskriver

`Ressursrolle.rekkefolge` kom samme dag (punkt 6) og sorterte rollelista. Men
`Vaktpost.Meta.ordering` var `['fra_tid', 'mannskap__navn']` — rollen var ikke med i det
hele tatt. Rangeringen var altså riktig der man *velger* rollen og uten virkning der man
*ser* den. Klienten sorterer ikke (`_posterFor()` filtrerer bare), så rekkefølgen er
serverens.

**Tida vinner fortsatt over rollen.** En hospitant som møter 08 står før en lagleder som
møter 16 — ellers slutter lista å være kronologisk, og det er tida man planlegger etter.

### Og en påstand i koden som bare var sann i dev

Kommentaren over `ordering` sa at ledige plasser sorteres først innenfor samme starttid.
Det stemmer i **SQLite**, som legger NULL først i stigende sortering — og aldri i
**PostgreSQL**, som legger dem sist. Regelen var udekket av noen test, så ingen hadde sett
at dev og prod svarte hver sitt.

Sorteringen bærer nå `nulls_last`/`nulls_first` eksplisitt:

- **En rad uten rolle hører nederst.** Rangeringen er hele poenget, og en rolleløs rad sier
  ingenting om hvor den hører hjemme.
- **En ledig plass står først blant sine egne** — den gamle intensjonen, nå på det nivået
  der den fortsatt betyr noe, og nå lik i begge basene.

Fem mutanter, alle røde — deriblant begge NULL-plasseringene, som var det som manglet
dekning i utgangspunktet.

### Og et spørsmål som viste seg å være besvart

«Rollene må gjelde for hele ressursgruppe og ikke egne roller per enhet.» Det gjør de:
`Ressursrolle.gruppe` peker på gruppa, og rollevinduet sier det selv — «Rollene gjelder
alle ressurser i gruppa «Lag», ikke bare Lag 1». Vinduet *åpnes* fra en ressurs, og det er
nok til at det kan leses som ressursens; teksten står der nettopp derfor.

**Endret:** `vaktliste/models.py`, `vaktliste/migrations/0020_vaktpost_sortering.py` (ny,
bare `Meta`), `vaktliste/tests_registre.py` (+4), `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Roller kan endelig døpes om, og modulen har én form for det  `#vaktliste/roller`

**André:** «Det bør gå relativt automatisk ved endring av rollenavn, se andre navn i
enheten (altså ambulanse, lag osv).»

### Det fantes ingen omdøping av roller

Rollevinduet hadde bare «slett». Og siden `Vaktpost.rolle` gjør en rolle *i bruk*
uslettelig, var en omdøping ikke bare tungvint — den var **umulig** for enhver rolle som
faktisk sto på et skift. Det forklarer også hvorfor André endte med å slette og opprette:
det var den eneste veien.

Serveren har støttet `PUT` hele tiden. Dette er tredje gang på én dag at punktet viser seg
å være **manglende flate over en mekanisme som virker** — gruppene og `er_aktiv` var de to
andre.

### Og jeg hadde nettopp innført en annen form for det samme

Gruppa fikk en `prompt()` noen timer før. Det er **oppdragsmodulens** idiom; vaktlista
redigerer verdimengder i et skjema (korps og kompetanser har «Rediger»). To former for
samme handling i samme modul er to kilder som glir fra hverandre — nøyaktig det
`CLAUDE.md` advarer mot for regler, og det gjelder grensesnitt også.

Begge bruker nå `_redigeringsrad()`: raden blir et felt med navnet i, med «Lagre» og
«Avbryt». **I raden, ikke i et vindu på et vindu** — rollevinduet er alt en modal, og en
modal nummer to over den er en stabel man mister oversikten i.

### To detaljer som ville vært stille feil

- **Tilstanden ligger i JS, ikke i DOM-en.** Lista bygges på nytt ved hver lagring; en
  `<input>` i markupen ville forsvunnet med den. Samme grunn som `ressursApen`.
- **Lagring henter hele registeret, ikke bare rollelista.** Rollenavnet står i nedtrekket
  på hver rad i regnearket også — hentes bare lista, viser skiftene det gamle navnet til
  neste sidelasting. Mutanten som tok `_lastRegisterOgListe()` bort er rød.

Og en kjenning: de nye `let`-bindingene hentes ikke av `build_harness`, som bare tar
funksjoner. Fire tester døde på en `ReferenceError` før snuttene satte dem selv — samme
felle som `SISTE_LISTE_NOKKEL` gikk i tidligere samme dag.

Åtte mutanter, alle røde.

**Endret:** `static/js/vaktliste-handlinger.js`, `vaktliste/tests_registre.py` (+6),
`vaktliste/CLAUDE.md`.

---

## 2026-09-16 — «Endret en rolle til hospitant og nå står den øverst»  `#vaktliste/roller`

**Meldt fra staging (André).** Symptomet er ekte, og årsaken er den alfabetiske
sorteringen: «Hospitant» går foran «Lagleder», «Lagsmedlem» og «Sjåfør». Det er nøyaktig
det punkt 6 avskaffer — meldingen kom mens staging fortsatt kjørte `3325c8d`, bygget før
rangeringen. Rettelsen ligger i `55c5fb8`.

**Reprodusert før noe ble sagt**, i stedet for å anta: en omdøping i dagens kode lar
`rekkefolge` stå urørt, og rollen blir der den er.

### Men symptomet fortjente sine egne tester

Det er to måter rangeringen kan velte tilbake til alfabetet, og begge ville sett ut som
nøyaktig denne meldingen:

- **`Meta.ordering` mister `rekkefolge`,** eller får navnet foran den. Testen døper om en
  rolle til noe som sorterer først alfabetisk, og krever at den blir stående.
- **Klienten sorterer selv.** `rollerForGruppe()` *filtrerer* bare, og alt annet i modulen
  sorterer alfabetisk — en `.sort()` lagt til i god tro ville gitt riktig rekkefølge i
  basen og feil på skjermen, uten at én servertest ble rød. Testen kjører funksjonen mot
  serverens faktiske svar.

Tre mutanter, alle røde.

**Endret:** `vaktliste/tests_registre.py` (+2). Ingen kodeendring — rettelsen var alt
pushet.

---

## 2026-09-16 — Pulje 3B: ressursgruppene kan endres, og rollene rangeres  `#vaktliste/roller`

To punkter fra pulje 3. Begge viste seg å være **manglende flate over en mekanisme som
alt virket** — den sorten hull der ingenting feiler, fordi funksjonen bare er uoppnåelig.

### Punkt 4: gruppene

André: «de som er i bruk på vaktlister nå må jo få bli.» Databasen var enig fra før —
`Ressurs.gruppe` er `PROTECT` — så halve svaret sto der. Det som manglet:

- **Redigering i det hele tatt.** Serveren har støttet `PUT` siden gruppene ble en tabell;
  klienten kunne bare opprette og slette. En gruppe kunne altså ikke omdøpes.
- **`er_aktiv` hadde ingen vei inn.** Feltet fantes fra 30. aug. 2026, nedtrekkene
  respekterte det, og ingen skjerm kunne sette det. En gruppe i bruk kunne derfor verken
  slettes eller skjules.
- **`Ressursrolle.gruppe` er `CASCADE`.** En gruppe *uten* ressurser lar seg slette — og
  tok rollene sine med seg **uten et ord**. «Lagleder» og «Sjåfør» er oppsett noen har
  skrevet inn. Funnet ved å lese `on_delete` på begge sidene, ikke ved at noe feilet.
  Nå: 409 med antallet, og `{"confirm": true}` for å fortsette — men bare når det
  *finnes* roller. Et ekstra klikk på en tom gruppe er en vane man slutter å lese, og da
  er bekreftelsen verdiløs den gangen den betyr noe.

De seks seedede gruppene har aldri vært vernet, så «også de seks» krevde ingen endring.

### Punkt 6: rollene rangeres

«Leder øverst, hospitant nederst.» Alfabetisk satte «Hospitant» over «Lagleder», og et
nedtrekk der den vanligste rollen ligger midt i lista koster et blikk hver gang.

**Rangeringen er data, ikke en liste i koden.** Rollene seedes ikke med faste navn — de kom
fra det som fantes ved migrasjon `0007` — så en hardkodet rangering ville truffet noen
installasjoner og ikke andre. Migrasjon `0019` legger til `rekkefolge` og sprer dagens
alfabetiske rekkefølge utover med ti, så ingenting *flytter* seg; den gjør bare rekkefølgen
til noe som kan endres.

**Migrasjonen er skjema først, data etterpå** — den trygge retningen. Regelen om
PostgreSQLs triggerkø gjelder migrasjoner som skriver rader og *deretter* endrer skjema;
her kommer `AddField` først og skrivingen sist, så verken `SET CONSTRAINTS ALL IMMEDIATE`
eller `atomic = False` trengs. Det står i migrasjonens egen docstring.

To detaljer verdt å nevne:

- **«Ny rolle havner sist» ligger i `Ressursrolle.save()`**, ikke i et view. Rollene
  opprettes av den generiske registerfabrikken, som bare kjenner *tekstfelter*
  (`ekstra_felt` gjør `.strip()` på vei inn) — et heltall måtte fått et unntak inni
  fabrikken, og da sto regelen der for alle tre verdimengdene mens bare én har den.
- **Omsorteringen sender hele lista**, ikke «opp» per rad. To kall som krysser hverandre
  bytter to par og etterlater en rekkefølge ingen ba om. Serveren krever **nøyaktig**
  gruppas roller: et delvis sett ville gitt noen rader nye tall og latt resten stå.

### Tolv mutanter, og den ene som «overlevde» var min egen feil

Mutanten for tilgangsporten på gruppene satte `pass` rett etter `def` — som ikke gjør noe
i det hele tatt, siden kroppen fortsetter under. **Felle nummer to i lista over måter en
mutant lyver på**, og den ga et falskt «OK» på nøyaktig den sjekken jeg ville prøve.
Skrevet om til å slå ut selve `if`-en: rød.

Alle tolv røde. Én test måtte skrives om — `test_verdimengdene_sorteres_alfabetisk` var
sann for `Ressursrolle` til i dag, og er nå delt i to: de to andre registrene sorterer
fortsatt alfabetisk, rollen sorterer på rangering med navnet som uavgjort.

**Endret:** `vaktliste/models.py`, `vaktliste/migrations/0019_rollerekkefolge.py` (ny),
`vaktliste/views.py`, `vaktliste/views_registre.py`, `vaktliste/urls.py`,
`static/js/vaktliste-handlinger.js`, `vaktliste/tests_registre.py` (+18),
`vaktliste/tests.py`, `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Pulje 3A: «Oversikt» ble en faktisk oversikt  `#vaktliste/belastning`

**André, pulje 3 punkt 2:** «Ressursfanen som heter Oversikt viser mye av det som allerede
er i de respektive ressursfanene. Må være en faktisk oversikt. Derfor nevnte jeg de ordene
som tid, timer, totalt, plasser ledig og besatt.»

### Hva den var, og hva den er

Fanen listet **hver person** med navn, korps, rolle og merknad, gruppert på ressurs under
hver dag — nøyaktig de fire kolonnene man alt hadde lest i gruppefanen. Arket ble langt, og
det svarte ikke på det en oversikt skal svare på.

Nå: én rad per **ressurs per tidsblokk**, med Ressurs, Tid, Timer, Plasser, Besatt, Ledige
og Totalt — og en sumrad per dag. Rader med ledige plasser er dempet merket, fordi en
oversikt leses for å finne hullene.

### Tre regler tabellen bærer

- **`Totalt` bruker `_sumTimer`, ikke `timer × plasser`.** Probono-skift teller null
  (11. sep. 2026: timene går, men de er ikke organisasjonens). Regner man lengden ganger
  antallet, blir totalen et annet tall enn budsjettlinja og enn `belastning_per_person`.
- **Sumraden teller de ledige plassenes timer med.** De er planlagt.
- **Dagen er fortsatt ytterst** (14. sep. 2026), og et skift over midnatt står under
  startdagen. Snuingen overlevde omskrivingen.

### Nitten tester bar den gamle formen — og ble skrevet om, ikke slettet

Det er den tyngste delen av jobben og den viktigste. Hver test beholdt poenget sitt:

| Testen sa | Nå |
|---|---|
| «Oversikten har **ingen** tidskolonne» | «Oversikten **har** tidskolonnen tilbake» — med begrunnelsen for at regelen snudde: kolonnen gjentok seg på hver personrad, nå *er* raden blokken |
| Ressursen er en `<h3>` | Ressursen er en rad, og rekkefølgen er fortsatt gruppas |
| Probono-merket står ved navnet | Probono bæres av `Totalt`; merkelappen prøves der personene bor |
| Ledig plass viser reservert korps | Ledige er et tall; reservasjonen prøves i gruppefanen, så `_plassKorps()` ikke mister sin eneste dekning |
| Mannskapsnavnet escapes | Navnet skal ikke være der **i det hele tatt** — og ressursnavnet, som er der, dekkes av sin egen test |

To av dem tok jeg først feil på, fordi jeg gjettet på fiksturen i stedet for å lese den:
Nina står på samleplassen, ikke på Ambulanse 2, og samleplassen har *to* blokker fredag, så
et samlet radtall sier ingenting om hvilke dager den står under. Begge er nå skrevet mot det
fiksturen faktisk inneholder.

### Ti mutanter, og den ene som overlevde var sumraden

Sumraden lot seg endre til å summere bare de **besatte** timene uten at noe ble rødt — den
var tabellens fasit og helt udekket. Det er nettopp den feilen som ikke ville blitt oppdaget
i bruk: et budsjettall som stille utelater de ledige plassene ser rimelig ut, det er bare
for lavt, og man planlegger etter det.

Etter at testen kom: alle ti røde, inkludert begge de to stedene `ledige` regnes ut (de sto
med identisk kode i rad og sumrad, så mutanten måtte gjøres entydig først — fella «den traff
et annet sted enn du tror»).

**Endret:** `static/js/vaktliste-oversikt.js`, `static/css/vaktliste.css`,
`vaktliste/tests_xss.py` (19 omskrevet, +1), `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Pulje 3A: «Planlegging»-fanen heter «Timeoversikt»  `#vaktliste/belastning`

**André, pulje 3 punkt 1:** fanen skal hete «Timeoversikt», og siles på korps for den som
ikke er leder.

### Halve punktet var alt gjort

`belastning_per_person()` kaller `synlige_vaktposter(poster, user)`, og
`KorpsvelgerTests.test_parameteret_er_ingen_dor_for_korps_brukeren` viser at en `les` med
badge bare ser sitt eget korps — også når hun sender `?korps=` for et annet. Silingen var
altså på plass og dekket. Det som gjensto var navnet.

Verdt å si høyt: jeg fant det ved å **lese testen**, ikke bare koden. At kallet står i fila
sier ikke at det virker — det er samme skille som mellom en statisk regel og en
migrasjonsprøve.

### Og navnet var opptatt

`Vaktliste.status` har verdien «Planlegging» ved siden av «I drift», og den står som et
merke øverst på siden. Fanen og merket sa samme ord om to ulike begreper: hva lista *koster
i timer*, og om innsjekk er *åpen*. «Timeoversikt» sier hva fanen viser, og «Planlegging»
betyr nå bare status.

**Et søk-og-erstatt over ordet ville vært feil.** «Planlegging» står i `choices.py` som
statusverdi, i `0002_oppsett` som migrert choice, og i fem tester som `status_navn`. Bare
fanens ene linje skulle endres — samme familie som mutantfella «den traff et annet sted enn
du tror», bare på forhånd.

### Testen manglet, og det var derfor kollisjonen kunne oppstå

Omdøpingen var **grønn før testen ble skrevet**: ingen test sa noe om fanenavnet, så det
kunne vært hva som helst. `FanenHeterTimeoversiktTests` prøver nå **regelen** og ikke ordet
— *et fanenavn kan ikke være en statusetikett* — så en framtidig omdøping som gjeninnfører
kollisjonen blir rød uansett hvilket ord det er.

Fire mutanter, alle røde, deriblant den som tømmer `STATUS_NAVN` så regelen ikke lenger har
noe å måle mot.

### Og en regel som fanget meg innen timen

Punktet ble levert, og jeg **krysset det av** i TODO — i en fil hvis egen topp sier at
ferdige punkter slettes, etter en regel jeg skrev samme formiddag. Testen fanget det ikke,
fordi den bare forbød åpne punkter *under* avkryssede.

Den forbyr nå `[x]` i det hele tatt. Det er den riktige formen på beslutningen — er
historien i CHANGELOG, er et avkrysset punkt en andre kilde — og det er dessuten
forutsetningen for den første regelen: finnes ingen avkryssede foreldre, kan ingenting
begraves under dem.

Vanen sitter i fingrene lenge etter at regelen er bestemt. Det er nøyaktig det tester er
til for, og det er tredje gang på to dager at svaret har vært å gjøre en intensjon til noe
som kan bli rødt.

**Endret:** `static/js/vaktliste-tegning.js`, `vaktliste/tests_belastning.py` (+2),
`core/tests_todo.py` (+1), `vaktliste/CLAUDE.md`.

---

## 2026-09-16 — Pulje 2 og de tre rundene etter ut i prod  `#oppdrag/statusmaskin`

André: «Kan vi pushe det vi har gjort til main?» Seks commits, `11c068b` → `a7239c5`:

| Bygg | Hva |
|---|---|
| `38f32cc` | Pulje 2, første halvdel — «ledig siden» og varselbjella |
| `031ac97` | Pulje 2, andre halvdel — passiv vakt, «avvente», kvittert avbrytelse |
| `5ef0aa7` | Typeflaggene kan krysses av i «Valglister» |
| `e4369f2` | Puljene skrevet ned, målrettet mutasjonskjøring, delt testsuite |
| `b6f66df` | «[object Object]» på hver enhet — og de tre lagene under |
| `a7239c5` | TODO ryddet, to vakter som holder den ryddig |

**Én migrasjon, `oppdrag/0026`, og den er rene tillegg** — to felter på `Enhetstype`, ett
på `Enhet`, `Oppdragsenhet` og `ArkivertOppdrag`, pluss tabellen `Vaktmodusperiode`. **Null
`RunPython`/`RunSQL`**, så regelen om PostgreSQLs triggerkø er ikke i spill og release-fasen
er trygg. Ingen eksisterende rad endres.

Og funksjonen er **inert til noen slår den på**: passiv vakt og «avvente» krever at flagget
settes på enhetstypen i «Valglister». Gjøres ikke det, oppfører oppdragsmodulen seg nøyaktig
som før deployen. Det er den beste formen en prod-endring kan ha — den kan verifiseres i ro,
og den kan ikke overraske noen som ikke har bedt om den.

Suiten grønn på `a7239c5`: 3 184 tester.

---

## 2026-09-16 — TODO var mer arkiv enn arbeidsliste  `#core/dokumentasjon`

**André:** «Hva kan vi gjøre med TODO for å optimalisere?» Målt først, ryddet etterpå.

### Diagnosen

| Funn | Tall |
|---|---|
| Linjer som beskrev **ferdig** arbeid | **1 316 av 2 495 (53 %)** |
| Linjer som beskrev åpent arbeid | 858 |
| Åpne punkter begravd under et avkrysset punkt | **23** |
| — av dem: punkter som ventet på André | **6** |
| Tester som håndhevet noe i TODO | **0** |

Regelen mot begravde punkter sto i `CLAUDE.md` fra 14. sep. 2026, skrevet da det var
**to**. To dager senere var det 23 — og **to av dem la jeg der dagen før**, i en fil jeg
leser hver økt. Prosaen hindret ingenting, fordi ingenting ble rødt. Det er samme lærdom som
avhengighetsretningen: en intensjon er ikke en regel.

De seks som ventet på André er det som gjorde det dyrt. Blant dem verifiseringen av
Scaleway-kortet og staging-lista fra 16. sep. — altså nøyaktig det han var bedt om å gjøre,
plassert der han ikke ser det.

### Avgjørelsen: ferdige punkter slettes

André: «Vi sletter. Du skal jo legge inn hva du gjorde i CHANGELOG, og det som står i TODO
og det som ble gjort kan bli to ting med forskjellig vri. **CHANGELOG blir arkivets
sannhet.**»

Det er den riktige delingen, og den avvikler en dobbeltføring vi ikke hadde lagt merke til:
et TODO-punkt beskriver *hva som skal gjøres*, en CHANGELOG-oppføring *hva som ble gjort og
hvorfor*. Å beholde begge er to kilder som glir fra hverandre.

**2 495 → 869 linjer.** 206 avkryssede blokker slettet.

### De 23 er skrevet om, ikke flyttet

Et begravd barn henter ofte meningen sin fra forelderen som ble avkrysset. «Prøv
gjenopprettingen én gang» sier ingenting uten at man vet at det handler om Scaleway. Hvert
av dem er derfor skrevet om til å stå alene. To forsvant underveis:

- **Ett var utdatert.** «Gjenstår: ut i prod — `main` står på `7435dec`» hadde vært sant til
  superbruker-runden gikk ut. `main` står på `11c068b` og har den. Punktet var både usynlig
  og feil, og det er ingen tilfeldighet at de to henger sammen.
- **To var duplikater** av hverandre — begge ba om verifisering av Scaleway-kortet, fra hver
  sin runde. Slått sammen.

### To vakter, og en presisering av hva «Krever Andre» betyr

`core/tests_todo.py`: ingen åpne punkter under avkryssede, og alt merket «Krever Andre» skal
stå i toppseksjonen.

Den andre regelen tvang fram en avklaring med én gang. Et punkt under datteroppdrag-ideen —
«hva skjer med morens bil når den første datteren lages?» — var merket «Krever Andre», men
blokkerer ingenting: ideen er ikke påbegynt. **«Krever Andre» må bety «blokkerer nå»**,
ellers fylles toppen av fila med ting han ikke kan handle på, og da slutter han å stole på
den. Punktet heter nå «Åpent valg, besvares når ideen tas opp», med begrunnelsen i teksten.

Og som i `core/tests_js_regler.py`: en sperrehake som krever at mønstrene kjenner igjen sin
egen feil. En vakt som ikke kan bli rød, vokter ingenting.

**Endret:** `TODO.md` (2 495 → 869 linjer), `core/tests_todo.py` (ny, 4 tester),
`CLAUDE.md` (sletting framfor avkryssing, og at CHANGELOG skrives for `grep`).

---

## 2026-09-16 — «[object Object]» på hver enhet: én linje, tre lag  `#oppdrag/sentralbord`

**Meldt fra staging (André):** «I /oppdrag i «ressurser»-listen vises enhver enhet med
navnet på enheten og `[object Object]` — på alle enhetene, uavhengig av hva flagget sier.»

### Feilen

```js
<div class="enhet-navn">${escapeHtml(e.navn)}${trustedHtml(passiv)}</div>
```

`trustedHtml()` er **ikke en escaper**. Den returnerer `{__trustedHtml: '…'}`, en merkelapp
`cellHtml()` pakker ut når en Tabulator-celle skal ta imot markup vi har bygget selv. I en
mal-streng blir objektet til `[object Object]`.

Og det forklarer «uavhengig av flagget»: `trustedHtml('')` er et objekt like fullt, så den
*tomme* grenen viste det også. Passivmerket var borte og teksten sto på hvert eneste kort —
altså så feilen ut som noe helt annet enn den var.

Reprodusert i node før noe ble rørt, som fire røde tester.

### Lag 2: ingen test så kortet

`_enhetskort` var ikke i `HTML_BUILDERS_PER_FIL`. Den ble hoistet ut av `renderEnheter` en
gang i fjor, og **lista fulgte ikke med** — fra da av var hvert enhetskort på tavla
uskannet. Åtte andre byggere sto utenfor på samme vis. Ingen av dem hadde uescapet
brukerdata, så ingenting smalt; men skanneren meldte grønt om en dekning den ikke hadde, og
det er verre enn en rød test.

En håndholdt liste forfaller i stillhet. `test_ingen_bygger_staar_utenfor_skanningen`
sammenligner den nå med kilden, så neste utklipping sier fra selv.

### Lag 3: skanneren anbefalte fella

Feilmeldingen sa: «Pakk verdien i escapeHtml() **eller trustedHtml() hvis det er markup du
har bygget selv**». Det er riktig for en Tabulator-celle og galt for en mal-streng, og det
er råd jeg fulgte. Teksten sier nå det motsatte, med grunnen.

Samme felle tok «Rett tid» fra fase 3 til 11. sep. 2026. Advarselen ble den gang skrevet som
en kommentar ved det ene kallstedet — 500 linjer unna, i en annen fil. Fem dager senere gikk
jeg i den samme. **En advarsel som bare finnes der feilen alt er rettet, advarer ingen.**
Regelen står nå i `core/tests_js_regler.py`, der den gjelder alle filene i `static/js/`.

### Ti mutanter — og to overlevde først

- **Å ta escapingen ut av `data-id="${escHtmlValue(meldingId)}"` overlevde.**
  `REVIEWED_INTERPOLATIONS` er nøklet på uttrykkets *tekst*, så `meldingId` godkjent fordi
  den står i en `getElementById`-streng var samtidig godkjent i en ekte attributt.
  Godkjenningen smittet fra en selektor over på markup. Skanneren leser nå bare mal-strenger
  **med en tagg i** (`_markuplitteraler()`) — og da trenger ingen av DOM-id-ene å stå i lista
  i det hele tatt.
- **Å peke regelen mot et navn som ikke finnes overlevde.** `trustedHtml` → `trustedHtmlXX`
  *inne i mønsteret* ga en regel som er grønn for alltid. Navnet står nå ett sted
  (`HJELPER`), begge mønstrene bygges av det, og sperrehaken krever at de slår ut på en
  kjent-dårlig bit kode. **En vakt som ikke kan bli rød, vokter ingenting.**

**Endret:** `static/js/oppdrag-sentral-kjerne.js` (feilen), `-oppdrag.js` (én id escapet),
`-lasting.js` (nøstet mal-streng hoistet ut), `oppdrag/tests_xss.py` (ni byggere inn,
markup-skillet, to nye vakter), `core/tests_js_regler.py` (ny),
`oppdrag/tests_passiv_avvente.py` (+3), `CLAUDE.md`. Suiten: 3 180 grønne på 109 sekunder
med den delte kommandoen.

---

## 2026-09-16 — Puljene skrives ned, og to testregler som koster en time i uka  `#core/dokumentasjon`

**André:** «Ligger puljene som vi har planlagt i noe notat? For jeg syns hver arbeid du
gjør tar enormt lang tid.»

Svaret på det første var **nei**, og det er en feil i seg selv. Lista på sytten punkter var
prioritert i fire puljer som bare fantes i samtalen — mens `TODO.md` sier i sin egen topp at
et punkt som ikke står der, ikke blir gjort. Pulje 1 og 2 var levert og krysset av; pulje 3
og 4 ville forsvunnet med sesjonen. Alle fire står nå under «Puljene fra Andrés gjennomgang
16. sep. 2026», med det som gjenstår og de to avklaringene pulje 4 venter på.

### Og så det andre spørsmålet, som var det viktigere

Tidsstemplene på mutasjonsskriptene lot seg lese som en logg, og den forteller dette:

| Hva | Målt |
|---|---|
| `manage.py test oppdrag` | **38 s** |
| `oppdrag.tests_passiv_avvente` (som dekker mutantene) | **5 s** |
| Mutanter kjørt over økta | **~100** |

Nesten alle kjørte **hele appen**. Ett skript alene — 21 mutanter mot `oppdrag` — brukte
tretten minutter på å gi et svar 42 tester kunne gitt på to. Over hundre mutanter er
forskjellen i størrelsesorden **en klokketime**, brukt på å kjøre tester som ikke kunne bli
røde av mutasjonen uansett.

Begrunnelsen jeg hadde for det var fella «mutanten traff et annet sted enn du tror» — som
står i denne fila. Men den fella løses ved å **lese diffen til mutanten**, ikke ved å kjøre
560 urelaterte tester. Regelen står nå i mutasjonsavsnittet.

### Suiten kan deles

190 sekunder serielt, **~106 delt** på fire kjerner. `core` må stå for seg:
`core/tests_backup.py` skriver ekte backupfiler til én mappe og rører det globale
handlerregisteret, så fire arbeidere kolliderer. Feilen kommer ut som «cannot pickle
'traceback' object», som ikke ligner det den er — derfor er den skrevet ned, både i
kommandoblokka og som et punkt.

Og mens jeg målte: **`core/tests_verifiser_backup.py` er 47 sekunder alene** — en firedel av
hele suiten, fordi den starter `migrate` i en underprosess per test. Det er riktig for det
den prøver, og den skal ikke slettes; den er den ene testen som svarer på om *innholdet* i
backupfilene duger. Men prisen betales av hver kjøring, og et tag-skille er ført opp.

**Endret:** `TODO.md` (puljene + to målte punkter), `CLAUDE.md` (målrettet mutasjonskjøring,
delt suite). Ingen kodeendring.

---

## 2026-09-16 — Pulje 2, andre halvdel: passiv vakt, «avvente» og kvittert avbrytelse  `#oppdrag/statusmaskin`

Resten av pulje 2 i én runde, etter spesifikasjonen André ga samme dag. Tre ting som
henger sammen, og én migrasjon — `oppdrag/0026`, **rene tillegg, null `RunPython`**, så
release-fasen er trygg.

### Flaggene står på enhetstypen, ikke på enheten

«Kan gå passiv vakt» og «kan avvente» er egenskaper ved *slaget* ressurs — spesialressurser
går bakvakt, ambulanser gjør det ikke — så de er to felter på `Enhetstype`
(`kan_passiv_vakt`, `kan_avvente`). Sto de på hver enhet, måtte de settes på nytt for hver
bil som opprettes, og en glemt avkryssing ville sett ut som en bevisst beslutning.

**To separate flagg, ikke ett.** Å avvente et oppdrag og å sove i bakvakt er to ulike ting,
og en ressurs kan gjøre det ene uten det andre. Ett felles flagg ville koblet dem for alltid
og vært umulig å skille i ettertid uten en datamigrasjon.

### Passiv vakt er ikke «av vakt»

Hun kan varsles, og hun teller i beredskapen — hun holder en 24/7-vakt gjennom hele
arrangementet. Poenget med moduset er å **dokumentere** hvor mange timer og hvor mange
oppdrag som falt i tida hun helst skulle sovet. Derfor er grensesnittet dempet: et merke på
ressurskortet, og `Lege 02 (passiv vakt)` på brikka når hun står på et oppdrag. Er hun
aktiv, står det ingenting ekstra — en merking av det normale er en merking ingen leser.

Svaret ligger to steder, og begge trengs:

- **`Oppdragsenhet.varslet_modus`** — modusen **frosset** i det hun ble varslet. Leste vi
  enhetens `passiv_vakt` når statistikken ble regnet ut, ville et oppdrag hun kjørte i
  passiv vakt hoppet over til «aktiv» i det hun gikk aktiv neste morgen, og dokumentasjonen
  vært verdiløs.
- **`Vaktmodusperiode`** — hvor lenge hun sto slik, inkludert timene ingenting skjedde. Som
  er akkurat de timene man vil dokumentere. `sett_vaktmodus()` lukker den åpne perioden og
  åpner en ny, er idempotent, og en databasesperre (`en_apen_vaktmodus_per_enhet`) holder
  at det aldri finnes to åpne perioder for samme enhet i samme vakt. En åpen periode
  summeres **fram til nå** — ellers viste vakta som pågår null.

### «Avvente» er en beskjed, ikke en status

En varslet spesialressurs kan svare at hun ikke rykker ut nå. Hun **blir stående varslet**
på oppdraget, og operatøren kan trykke «Rykk ut» senere; begge deler står i loggen
(`Enhetshendelse.AVVENTER`). Derfor teller hun **ikke** som «noen er på vei» i
`trenger_ny_ressurs`: står hun avventende alene, skal det stå «trenger ny ressurs» — som er
hele grunnen til at spørsmålet stilles. Det var André sitt svar på spørsmål 2, og det er
den eneste lesningen som gir mening for en ressurs som vanligvis rykker ut som ekstra enhet.

### Avbrutt-merket kvitteres nå

Det forsvant aldri av seg selv, og et merke som blir stående gjennom vakta er et merke man
slutter å se. To veier ut: operatøren trykker «Kvitter» i merket, eller **en ny enhet
varsles** — `varsle_enhet` kvitterer, fordi det å sende noen ny *er* svaret på
avbrytelsen. (`kvittert_at`/`kvittert_av` på `Enhetshendelse`; `avbrutt_av` og
`avbrutt_av_bulk` filtrerer på ukvittert.)

### Arkivet og statistikken

`ArkivertOppdrag.varslet_modus` står i SHA-payloaden **bare når den er satt**, nøyaktig som
`behandlet_at`: rader for enheter uten passiv vakt — de fleste — får samme payload som før,
og eldre signaturer verifiserer uendret. Statistikken har `enheter_passiv`, `passiv_timer`
og `oppdrag_i_passiv`. De to første er live-tall og finnes ikke i arkivet (som
`enheter_pa_vakt`); det tredje overlever arkiveringen, fordi stempelet ligger på radene.

### 21 mutanter — og én av dem var en ekte feil

Alle 21 røde. Én av dem fant en **kodefeil, ikke et testhull**, og det er verdt å skrive
ned hvordan:

> **Broen i `Oppdrag.save()` stemplet ikke modusen.** Den lager den *første* koblingsraden
> for et oppdrag opprettet med `enhet` satt — `varsle_enhet` lager de neste. Uten stempelet
> der talte `oppdrag_i_passiv` bare enheter som ble lagt til *etterpå*, altså aldri det
> vanlige tilfellet. Mutanten «broen stempler ikke modusen» var grønn da jeg skrev den, og
> det var svaret: koden gjorde allerede det mutanten skulle gjøre.

Det er nettopp den sorten feil mutasjonstesting finnes for. Regelen sto riktig ett sted og
manglet i det andre, begge stiene var dekket av tester, og begge testene var grønne — fordi
ingen av dem gikk gjennom den ene inngangen der feltet manglet.

### Og flaggene måtte kunne krysses av

Flaggene sto på `Enhetstype` med riktig standard og riktig lesing, alle 21 mutantene var
røde — og **ingen skjerm kunne sette dem**. En funksjon som bare lar seg skru på fra et
skall er ikke levert; den er skrevet. De ligger nå i «Valglister» → Enhetstyper, gjennom
`Verdimengde.ekstra`, som er den samme mekanismen `kategori` og `med_antall` bruker.

Ni mutanter til på den veien. Åtte røde med det samme; den niende avslørte en assertion jeg
hadde skrevet for løst:

> Testen krevde strengen `data-action="settTypeflagg" data-hendelse="change"` *ett sted* i
> markupen — og den sto i begge nedtrekkene. Fjernet man hendelsen fra det ene, fant
> assertionen den fortsatt i det andre og gikk grønn. Uten hendelsen fyrer handlingen på
> *klikket* som åpner nedtrekket, med den gamle verdien: nøyaktig feilen som gjorde
> vaktlistevelgeren «treg» dagen før.

Rettelsen var å skrive **regelen** i stedet for treffet: hvert `<select>` i en verdirad som
bærer `data-action` må også bære `data-hendelse="change"` og `data-felt`. Den dekker
problemstillingsfeltene på kjøpet, og den neste som legges til.

**Endret:** `oppdrag/models.py` (+`Vaktmodusperiode`, fem felter),
`oppdrag/migrations/0026_…` (rene tillegg), `oppdrag/services.py`, `oppdrag/views.py`,
`oppdrag/views_common.py`, `oppdrag/urls.py` (+3 ruter), `oppdrag/arkiv.py`,
`oppdrag/statistikk.py`, `static/js/oppdrag-sentral-{kjerne,oppdrag,admin}.js`,
`static/css/oppdrag.css`, `oppdrag/views_verdier.py`,
`oppdrag/tests_passiv_avvente.py` (ny, 42 tester), `oppdrag/tests_runde_e.py` (+3),
`oppdrag/tests_xss.py`, `oppdrag/CLAUDE.md`, `docs/TEKNISK_DOKUMENTASJON.md` (rutetallene).
Hele suiten (3 172 tester) grønn.

---

## 2026-09-16 — Pulje 2, første halvdel: «ledig siden» og varselbjella  `#oppdrag/sentralbord`

To av de tre små i oppdragsmodulen. Ingen av dem rører statusmaskinen eller skjemaet;
avbrutt-kvitteringen kommer for seg, fordi den trenger en migrasjon.

### «Ledig siden» i ressursdelen

En ledig enhet har ingen aktiv koblingsrad, så `status_tidspunkt` er tomt og statusen sto
som et ord uten tid. Operatøren som skal sende noen vil vite hvem som har stått lengst.

`services.ledig_siden_bulk()` leser siste **gjeldende** `Ledig`-melding per enhet i denne
vakta. Tre ting er verdt å nevne, og alle tre ble funnet av mutasjonstesting:

- **Korreksjoner teller.** Retter operatøren tidspunktet, er det det rettede som gjelder.
- **Vakta er scope.** Uten filteret ville fjorårets arrangement stått der som om det var
  i dag.
- **Feltet sendes bare når hun faktisk er ledig.** Står hun på et oppdrag, er «ledig siden»
  forrige gang — et tall som ser ut som nåtid og ikke er det.

Klienten viser det gjennom samme uttrykk som alle de andre statusene
(`status_tidspunkt || ledig_siden`), med klokkeslett og tid siden. To måter å vise «siden
når» ville vært én for mye.

### Varselbjella

Nummer, hastegrad og klokkeslett — **ikke problemstillingen**. «Intet mer» er ikke bare
knapphet: varselraden blir stående i 30 dager, og problemstillingen er en helseopplysning.

**Nøkkelen bærer oppdrags-ID-en**, fordi `notify()` dedupliserer på `kind` i 24 timer. Med
en fast verdi ville oppdrag nummer to blitt svelget, og det er nettopp det andre oppdraget
hun trenger å se. Varselet merkes lest når hun rykker ut — ellers hoper bjella seg opp
gjennom vakta, og et ulest-tall som bare vokser er et tall ingen ser på.

Begge kaster aldri: en bil uten bjellerad er et savn, en varsling som velter utrykningen er
en feil. Og begge har `transaction.atomic()` rundt seg — `varsle_enhet` kan kjøre inne i en
transaksjon, og en databasefeil fanget uten savepoint etterlater den ubrukelig.

### Tolv mutanter, og tre overlevde først

Alle tre var testhull, ikke kodefeil — og **to av dem var fikstureringen igjen**:

- **Korreksjonen flyttet tidspunktet framover.** Da vinner den korrigerte raden uansett,
  fordi den er nyest, og testen kunne ikke skille «vi hoppet over den overstyrte» fra «vi
  tok den seneste». Rettelsen flytter nå bakover.
- **Enheten hadde aldri vært ledig** før hun rykket ut, så feltet var tomt uansett hva
  regelen gjorde. Nå kjøres hun gjennom ett oppdrag først, med en sperrehake som krever at
  hun har et tidspunkt å miste.
- **Ingen test hadde en enhet som var ledig i en annen vakt**, så vaktfilteret lot seg
  fjerne.

Det er tredje gang denne uka at «fikstureringen bar ikke prod-formen» er svaret. Regelen
står i `CLAUDE.md`; den fortjener å bli lest før neste test skrives, ikke etter.

**Endret:** `oppdrag/services.py`, `oppdrag/views.py`,
`static/js/oppdrag-sentral-kjerne.js`, `oppdrag/tests_flere_enheter.py` (+19 tester),
`oppdrag/CLAUDE.md`. Ingen migrasjon. Hele suiten (3 127 tester) grønn.

---

## 2026-09-16 — Velgeren var ikke treg, den fyrte på feil hendelse  `#vaktliste/planlegging`

**Meldt fra staging (André):** «Når jeg skifter vaktliste tar det lang tid før fanene og
vaktene oppdateres. Det er og forvirrende at om jeg er på en vaktliste og går ut av
/vaktliste/, så går jeg tilbake til den som er øverst på listen.»

### Det var ikke treghet — det skjedde ingenting

`<select id="vaktliste-velger" data-action="byttVaktliste">` manglet
`data-hendelse="change"`. Klikkdelegeringen i `portal-utils.js` treffer *alle*
`[data-action]`, mens `change`-lytteren bare treffer dem som oppgir hendelsen sin. To ting
skjedde derfor samtidig:

- **Klikket som åpnet nedtrekket** kalte `byttVaktliste()` med verdien som alt sto der —
  altså en full henting og omtegning av lista man allerede så, hver gang man åpnet
  velgeren. Det er stutteren man kjenner mens man prøver å velge.
- **Selve valget gjorde ingenting.** Lista byttet først ved *neste* klikk på velgeren.

Regelen sto allerede i `CLAUDE.md`, og `klikkSkalKjore()` finnes nettopp for den. Markupen
ble bare skrevet som om den ikke gjorde det — samme sort feil som planleggerfeltene 15.
sep. `VelgerenFyrerPaaEndringTests` skanner nå alle maler: et `<select>` eller `<textarea>`
med `data-action` skal oppgi hendelsen sin. `<input>` er utenfor med vilje — en knapp er et
`<input>` også, og der *er* klikk riktig hendelse. Én synder i dag, og det var denne; de to
andre nedtrekkene hadde det riktig.

### Og sida husker hvilken liste du sto på

`lastVaktlister()` tok `vaktlister[0].id`, hver gang. Nå leser `forsteListe()` den siste
fra `localStorage` og **sjekker den mot lista serveren faktisk sendte** — en vaktliste kan
være slettet, eller tilgangen borte, siden sist, og da er øverst riktig, som første gang.
Uten den sjekken ville sida bedt om en ID serveren svarer 404 på, og stått tom uten å si
hvorfor.

Minnet er **per nettleser, ikke per konto**: det er en bekvemmelighet, ikke en innstilling,
og «Logg ut» sender `Clear-Site-Data`, som rydder den på en delt drifts-PC. Lagringen
kaster i privat modus, så begge kallene står i `try/catch`.

### Sju mutanter, og de to som overlevde var kallstedene

`forsteListe()` og `huskListe()` var prøvd for seg. Det holdt ikke: **begge kallene lot seg
fjerne uten at én test ble rød** — `lastVaktlister()` kunne gå tilbake til `vaktlister[0]`,
og `lastListe()` kunne slutte å lagre. Da husker sida ingenting mens testene bekrefter en
dekning som ikke finnes. Felle nummer tre fra mutasjonsbolken, igjen.

`MinnetBrukesFraDeEkteInngangeneTests` kjører nå de ekte inngangene mot stubbet `apiFetch`
og `localStorage`, og leser hvilken ID oppstarten ba om og hva lastingen lagret. Etter
rettingen: **sju mutanter, ingen overlevende.**

**Og en testfelle til, verdt å kjenne:** `try/catch`-en rundt `localStorage` svelger
`ReferenceError` like villig som en blokkert butikk. `build_harness` klipper ut funksjoner,
ikke konstanter, så `SISTE_LISTE_NOKKEL` fantes ikke i node — og testen falt tilbake på
«øverst» og *så ut* som om funksjonen ikke husket noe, mens den i virkeligheten ikke fant
navnet sitt. Nøkkelen leses nå ut av kilden.

**Endret:** `templates/vaktliste/index.html`, `static/js/vaktliste-kjerne.js`,
`vaktliste/tests_tilgang.py` (+9 tester), `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.
Ingen migrasjon. Hele suiten (3 108 tester) grønn.

---

## 2026-09-16 — Porten gjaldt innsendingen, ikke endringen  `#vaktliste/tilgang`

**Meldt fra staging (André):** «Kan rapportere bug at de med les alle / skriv eget korps
ikke kan skrive merknad hvis det står ledig plass. Bør de ha tilgang der når det står ledig
plass for å skrive merknad?»

**Ja** — og dagens oppførsel var ikke engang et bevisst nei. Den var en regel som fyrte på
en endring som ikke skjedde.

### Mekanismen

Skiftvinduet sender hele skjemaet, så `mannskap_id` står i kroppen også når ingen har rørt
nedtrekket. På en ledig plass betyr det **`null` over `null`** — og
`kan_sette_vaktpost(..., mannskap=None)` er `skriv_full`, med god grunn: *å la en plass stå
tom* er å sette opp et behov, og korps-føreren bestemmer ikke hvor mange plasser det skal
være.

Regelen er riktig. Den sto bare på feil side av spørsmålet: den sjekket **innsendingen**
framfor **overgangen**. Viewet sammenligner nå `ny_id != vaktpost.mannskap_id` først. **En
skriving som ikke endrer noe, trenger ingen tillatelse til å endre det.**

### Og svaret på spørsmålet er ja

«Mangler sjåfør, ringer rundt» hører hjemme nettopp på en tom plass, og korps-føreren er den
som vet det. Plassen er alt hennes å *fylle* — reservasjonen sier så — og merknaden følger
raden etter gårsdagens avklaring. Da er den hennes å skrive på.

Det hun fortsatt ikke kan: opprette plassen, fjerne den, flytte tidene eller endre hvem den
er satt av til. Hun kan altså **merke et behov, ikke finne på eller fjerne ett.**

### Fire mutanter, tre røde — og den fjerde er ekvivalent

Den fjerde byttet `ny_id != vaktpost.mannskap_id` med `ny_id is not None`, altså «sjekk bare
når noen settes inn». Den overlevde, og **det betyr ingenting**: de to er
oppførselsmessig like her. Forskjellen kan bare oppstå når noen tømmes ut av en rad, og
inngangsporten for en fylt rad er `kan_redigere_mannskap(user, vaktpost.mannskap)` — nøyaktig
det samme uttrykket `egen_staar_der` leser. Slipper hun inn i raden, passerer hun også
`kan_sette_vaktpost`.

Det er felle nummer to fra mutasjonsbolken i `CLAUDE.md`: *den var en no-op*. Ført opp her
framfor å skrives en test rundt — en test som «fanger» en ekvivalent mutant, fanger
ingenting og ser ut som dekning.

**Endret:** `vaktliste/views.py`, `vaktliste/tests_tilgang.py` (+3 tester),
`vaktliste/CLAUDE.md`. Ingen migrasjon. Hele suiten (3 099 tester) grønn.

---

## 2026-09-16 — Et låst felt skal se låst ut, og fortsatt kunne leses  `#vaktliste/planlegging`

**André:** «De feltene i rediger skift og rediger ressurs som korps-fører ikke kan endre bør
endre farge i feltet til noe som tydeliggjør at den er låst. Fortsatt lesbar.»

Enig — og `disabled` alene gjorde det motsatte av begge deler. Bootstrap demper deaktiverte
felter, nettleseren demper dem én gang til, og **Safari ignorerer `color` på et deaktivert
felt** og leser `-webkit-text-fill-color` i stedet. Resultatet var et felt som verken så
låst ut eller var godt å lese — særlig på iPhone, som er der dette ble meldt begge ganger.

`.vl-laast` gir stiplet kant, dempet flate og **full tekstkontrast tilbake**. Stiplet
framfor en ny farge, av to grunner: fargene i modulen betyr alt noe (gult varsler, grønt er
tilstede), og en strek man ser forskjell på i gråtoner fungerer også for den som ikke
skiller farger.

**Fargen sier at feltet er låst, ikke hvorfor.** En stiplet kant uten forklaring leser som
en feil, så hvert vindu har nå én linje som sier hvem som setter feltene — og den vises av
*samme funksjon* som låser dem. `_laasFelter()` i `vaktliste-kjerne.js` gjør alle tre
tingene: `disabled`, klassen, hintet. Et vindu som husket to av dem ville sett ut som om det
virket.

### Mutasjonstesting: åtte mutanter, og den siste var en test som leste sin egen prosa

Sju bet med én gang. Den åttende — «Safari-regelen fjernet fra stilarket» — overlevde, og
grunnen er verdt å skrive ned: testen krevde `-webkit-text-fill-color` i regelen, og den
strengen står **også i kommentaren** som forklarer hvorfor den trengs. Fjernet man
deklarasjonen, sto prosaen igjen og testen gikk grønn.

Det er en ny variant av «skillet går på hva assertionen påstår»: en regel som leser sin egen
begrunnelse måler at noen har skrevet om kommentaren, ikke at koden gjør det den sier.
Testen stripper nå kommentarer før den søker, og krever deklarasjonen med kolon. Regelen
står i `CLAUDE.md` ved siden av de fem andre mønstrene. Etter rettingen: **åtte mutanter,
ingen overlevende.**

**Endret:** `static/css/vaktliste.css`, `static/js/vaktliste-{kjerne,offline,handlinger}.js`,
`templates/vaktliste/index.html`, `vaktliste/tests_tilgang.py` (+6 tester),
`vaktliste/CLAUDE.md`, `CLAUDE.md`. Ingen migrasjon. Hele suiten (3 096 tester) grønn.

---

## 2026-09-16 — Merknaden følger raden, ikke oppsettet  `#vaktliste/tilgang`

**André:** «Merknad skal ikke låses for korps-føreren.»

15. sep. låste jeg den sammen med tidene, fordi «det eneste de skal få lov til er å legge
inn folk, rolle» ble lest strengt. Det var feil sted å trekke grensen. **Merknaden er en
beskjed om raden** — «Kommer 17:30», «kjører selv» — og den som setter personen på plassen
er den som vet det. Tidene er vaktas rammer; merknaden er ikke det.

Den følger derfor samme port som person og rolle, `kan_rore_vaktpost`, og hun når bare
radene som er hennes. **`probono` ble stående**, og det er et annet spørsmål: det sier hva
vakta *koster*, og tallet leses av budsjettlinja for hele lista — den som fører sitt eget
korps skal ikke kunne flytte totalen for alle.

Sju tester bar den gamle regelen og er snudd tilbake. At grensen flyttet seg to ganger på
ett døgn står i `services.SKIFT_OPPSETTFELTER` med begge begrunnelsene: hvorfor merknaden
gikk inn, og hvorfor den kom ut. En liste uten den historikken inviterer til at noen
flytter den tredje gang.

### Mutasjonstesting fant et hull merknaden avslørte

Seks mutanter, og **den sjette overlevde**: `const merknad = kanRore` lot seg bytte med
`true` uten at noe ble rødt. Ingen test spurte hva den som *ikke* får røre raden ser — og
svaret hadde da blitt et skrivbart felt som avvises ved lagring, altså nøyaktig feilen
`readOnly`-glippen dagen før handlet om.

Hullet fantes fordi alle testene av regnearket sto på hennes egen rad. Nå tegnes også en rad
som tilhører et annet korps, med en sperrehake ved siden av: er raden uredigerbar av en
annen grunn, måler «ingen felter» ingenting. Etter rettingen: **seks mutanter, ingen
overlevende.**

**Endret:** `vaktliste/services.py`, `static/js/vaktliste-{kjerne,tegning,offline}.js`,
`vaktliste/tests_tilgang.py` (+4 tester, 7 snudd), `vaktliste/CLAUDE.md`. Ingen migrasjon.

---

## 2026-09-16 — En lås som ikke låste, og en navnerett som var stengt  `#vaktliste/tilgang`

To glipper i gårsdagens tilgangsrunde, meldt fra staging.

### `readOnly` virker ikke på `datetime-local`

**André:** «Når en per skift trykker på rediger, så ser jeg at i det minste på iPhone kan
man trykke på tid/datoen og justere den. Men får ingen tilgang når man prøver å få det
gjennom. Ikke mulighet til å bare ikke la det i det hele tatt få trykke på den?»

Jeg låste tidsfeltene i skiftvinduet med `readOnly`. **Det attributtet har ingen virkning på
`datetime-local`** — HTML-standarden lar `readonly` gjelde felter man taster fritt i, og på
`date`, `time`, `datetime-local`, `color`, `file` og avkryssinger gjør det ingenting.
Velgeren åpnet seg, segmentene lot seg dra, tallet endret seg på skjermen — og ble så
filtrert bort av `bareTillatteFelter()` ved lagring.

**Det er verre enn å ikke kunne røre feltet.** Man tror man har gjort noe, og oppdager
etterpå at man ikke har. En lås som *ser ut* som en lås, men ikke er det, er den dårligste
av de tre tilstandene — dårligere enn et åpent felt og dårligere enn et stengt.

`disabled` er det ene attributtet som virker på alle feltformene, og gjør nøyaktig det som
ble bedt om: feltet lar seg ikke trykke på. Verdien leses fortsatt av JS, så visningen står.

`LaaseneVirkerPaaAlleFeltformeneTests` håndhever regelen for begge vinduene. **Testen leser
attributtet vi setter, ikke nettleserens oppførsel** — den kan ingen enhetstest måle. Det
den håndhever er derfor regelen som følger av den: *på et felt vi låser, bruker vi
`disabled`.*

### Navneretten var stengt av en detalj i «Ny ressurs»

**André:** «Og så må de få endre navn på ressursen, det ble fjernet ser jeg.»

Den ble ikke fjernet — den ble aldri nåbar. Porten sto på `kan_bemanne_ressurs`, altså
ressursens egen reservasjon. Men **«Ny ressurs» spør bare om navn og gruppe**, med den
begrunnelsen at reservasjonen hører til plassen og koblingen til enheten, og begge settes i
«Rediger». En fersk ressurs er derfor **ureservert** — og «Rediger» er lederens.

Resultatet: regelen slapp bare gjennom de bilene lederen alt hadde reservert til korpset, og
knappen var borte akkurat der korps-føreren står. Et hull som ikke slipper noen inn, men som
ser ferdig ut i koden.

`services.kan_gi_nytt_navn()` spør nå om hun kan bemanne ressursen **eller noen av plassene
på den** — samme to nivåer som `reservert_korps()` alltid har hatt: en samleplass kan stå
ureservert og likevel ha fire plasser som er Haugesunds. Navneretten er dermed bredere enn
bemanningsretten på ressursnivå, og det er med vilje. **Den drar ikke oppsettet med seg:**
gruppe, reservasjon, enhetskobling og sletting leser `kan_lede` hver for seg, og en test
krever at hun fortsatt ikke kan reservere ressursen hun nettopp fikk navngi.

**Ni mutanter, alle røde.** Den som er verdt å nevne: «navneretten teller plasser, ikke
korps» — leses regelen som «har ressursen plasser i det hele tatt», er enhver bemannet
ressurs fritt vilt.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-{kjerne,tegning,offline}.js`, `vaktliste/tests_tilgang.py`
(+9 tester), `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`. Ingen migrasjon.

---

## 2026-09-15 — Superbrukeren er én konto, ikke en kategori  `#core/tilgang`

**André, etter forrige runde:** «`is_superuser` skal ikke kunne demotes fra sin
`role = admin`, siden is superuser er og skal være eksklusivt til bootstrap-kontoen.»

Sperren mot degradering kom noen timer tidligere, men den var lagt i viewet alene — og
kravet er strengere enn det. **«Eksklusivt til bootstrap-kontoen» er en invariant, ikke en
sperre på ett endepunkt.** Tre hull sto igjen, og de er ulike:

| Hull | Hva som sto galt |
|---|---|
| Nedtrekket lot seg velge i | Skjemaet tegnet «Bruker» som et gyldig valg på superbrukeren, og viewet avviste innsendingen etterpå. Det er en kontroll som fører til en vegg — regelen fra CLAUDE.md, brutt av rettelsen på forrige punkt |
| `create_admin` laget superbruker nummer to | Kommandoen er idempotent på *brukernavn*. Kjørt med et nytt navn laget den én superbruker til, og da verner sperrene mot degradering og sletting en nødutgang det finnes flere av — altså ingenting |
| Ingenting stoppet en ny kodesti | Sperrene lå i skjemaet og i viewet. `bruker.role = 'bruker'` i et framtidig endepunkt går utenom begge, uten at én test blir rød |

**Rollen låses nå med Djangos `disabled`**, som gjør to ting i én: feltet tegnes grått, og
innsendt verdi forkastes til fordel for instansens. `_kan_degraderes()` og `_kan_slettes()`
står igjen som andre lag — forsvinner låsen, skal noe fortsatt stoppe det.

**`create_admin` avviser en superbruker til**, og sier hvem som har plassen. Den er fortsatt
idempotent på samme brukernavn: blir andre kjøring en feil, knekker den deployen den skulle
hjelpe. Sperra leser `is_superuser`, ikke `role` — leste den rollen, kunne bootstrap aldri
kjørt på en portal som alt hadde en administrator.

**Og `RollenSettesBareGjennomSkjemaeneTests` leter etter nye veier** i stedet for å vedlikeholde
en liste noen må huske. Den går gjennom kodebasen med AST og krever at ingen skriver `.role`
direkte; i dag finnes ingen slik skriving, og unntakslista er tom. Det er den samme sorten
regel som vakten mot `loaddata`: den som kommer til å bryte invarianten neste gang, har ikke
lest denne changeloggen.

**Sju mutanter, alle røde** — blant dem «en ny kodesti skriver `role` direkte», som er den
eneste av dem som beskriver en feil ingen har gjort ennå.

**Endret:** `accounts/forms.py`, `accounts/management/commands/create_admin.py`,
`accounts/tests_sikkerhet_runde1.py` (+10 tester), `CLAUDE.md`. Ingen migrasjon.
Hele suiten (3 077 tester) grønn.

**NB — dette ligger på `rollemodell`, ikke på `main`.** Prod (`7435dec`) har ingen av de to
rundene, og der kan en administrator fortsatt degradere superbrukeren.

---

## 2026-09-15 — Superbrukeren er nødutgangen, og Scaleway-kortet løy  `#core/tilgang` `#core/backup`

To korte punkter fra samme runde som vaktliste-porten over.

### `is_superuser` kan ikke fratas admin-rollen

**André:** «`is_superuser` må være immun mot å bli nedgradert fra administrator. Ser at når
noen blir gjort administrator så blir de ikke gjort til `is_superuser`, som er slik det skal
være.»

Observasjonen er riktig, og den er verdt å skrive ned: **`is_superuser` og `is_staff` betyr
ingenting for portalen.** De gater `/django-admin/`, som er rutet av i produksjon (S1).
Portaltilgang er `role == 'admin'` og `ModulTilgang`. Flaggene settes bare av
`manage.py create_admin`, og skal ikke følge med når noen forfremmes.

Nettopp derfor er kontoen noe annet enn «en administrator til»: den er den ene man kommer
tilbake inn med. **Og «siste admin»-sperra dekket den ikke** — er det tre administratorer,
kunne superbrukeren degraderes uten at noe protesterte, og da var nødutgangen borte mens
portalen så helt normal ut.

`_kan_degraderes()` sperrer nå på `target.is_superuser`. **Og `_kan_slettes()` gjør det
samme,** selv om det ikke sto i bestillingen: en regel som sperrer degradering, men slipper
sletting, verner ingenting — sletting tar kontoen og ikke bare rollen, og er i tillegg
endelig. **Frysing står igjen med vilje.** Grensen går ved om handlingen lar seg reversere,
og «Tø konto» står ved siden av.

Fire mutanter, alle røde — blant dem «sperra treffer alle admins», som ville gjort hver
administrator udegraderbar. Den retningen er like gal, bare stillere.

### Scaleway-kortet meldte avvik som ikke fantes

**André:** «Bug med lifecycle-tilbakemeldingen fra Scaleway. Permissions skal være korrekt,
er feilen i koden?»

Ja, i hvert fall delvis. `_les_livssyklus()` leste prefikset fra `Filter.Prefix` og det
gamle `Prefix` på toppnivå — men **ikke fra `Filter.And.Prefix`**, som er formen S3 sender
når en regel kombinerer prefiks med en tag eller en størrelsesgrense. Da leste vi tomt
prefiks, og `_avvik()` meldte «ingen livssyklusregel for `backups/` — filene der blir
liggende for alltid» om en regel som sto helt riktig i bucketen.

**Det er den verste sorten feilmelding:** den peker på en ekte fare, på et tidspunkt der
faren ikke finnes, og lærer den som leser den å overse kortet. De tre formene leses nå av
`_prefiks()`, med en sperrehake som krever at «ingen prefiks» fortsatt er et avvik — leses
det som «treffer alt», ville enhver regel sett riktig ut og kortet sluttet å måle noe.

**Og feilteksten sier nå hva Scaleway faktisk svarte.** Den sa «nøkkelen mangler
ObjectStorageBucketsRead» uansett hvilken kode som kom tilbake, og da er en riktig satt
nøkkel og en feil i vår egen kode umulig å skille fra hverandre — begge ser ut som et
rettighetsproblem, og man leter på feil sted. Koden og meldinga står nå i teksten, vasket
for nøkler.

**Er det fortsatt galt på staging, er det nå mulig å se hvorfor** — kortet sier koden.

**Én test ble degenerert underveis, og det er verdt å merke seg:** vaskingen prøves mot
klassens fikstur, der `secret_key` er `'b'`. Da består testen — eller feiler — på om
bokstaven «b» tilfeldigvis står i feilteksten («Object»), ikke på om vaskingen virker. Den
har nå en realistisk nøkkel. En sannhet om ett tegn er ikke en sannhet om en nøkkel.

**Endret:** `accounts/views.py`, `core/offsite.py`,
`accounts/tests_sikkerhet_runde1.py` (+6 tester), `core/tests_offsite.py` (+5 tester),
`CLAUDE.md`. Ingen migrasjon. Hele suiten (3 067 tester) grønn.

---

## 2026-09-15 — Korps-føreren bemanner, hun setter ikke opp  `#vaktliste/tilgang`

**Meldt fra staging (André):**

> «På /vaktliste/ så kan skrive: eget korps, ser alle — opprette vakter og redigere tider.
> Det må de ikke få lov til. Det eneste de skal få lov til er å legge inn folk, rolle, og
> redigere ressursens navn, men ikke gruppe, reservering, enhet i oppdragsmodulen og
> sletting.»

### Hullet sto i dokumentasjonen som lukket

`CLAUDE.md` sa det allerede: «å *opprette* en ledig plass er `skriv_full`, å *fylle* den
krever badge og reservasjon». Koden sjekket bare badgen. `vaktposter_view` gikk rett på
`kan_sette_vaktpost()`, så `skriv_handling` kunne opprette skift med frie tidspunkt — og
med `antall` inntil femti tomme plasser — på hver ressurs reservert til korpset hennes.
`vaktpost_detalj_view` hadde egne `if`-er for `korps_id` og `alle_korps`, mens
`fra_tid`/`til_tid`, `merknad` og `probono` gikk rett gjennom.

**Det er den typen hull som overlever lengst:** ingen får en feilmelding, dokumentasjonen
leser riktig, og regelen står tre steder som hver dekker sin del av den.

### Regelen er to lister, ikke en `if` per felt

| Nytt | Hva det er |
|---|---|
| `services.SKIFT_OPPSETTFELTER` | `fra_tid`, `til_tid`, `korps_id`, `alle_korps`, `probono`, `merknad`, `antall` |
| `services.RESSURS_OPPSETTFELTER` | `gruppe_id`, `korps_id`, `enhet_id`, `rekkefolge` — **navnet står bevisst ikke der** |
| `services.oppsettfelter(data, felter)` | Hvilke av dem står i kroppen |
| `services.kan_sette_opp_skift(user)` | Kall videre til `kan_skrive_alt`, som `kan_stemple`. Beslutningen skal ha et sted |

Listene er konstanter fordi de har **to lesere hver** — opprettelsen og redigeringen av et
skift, PUT og DELETE på en ressurs. Med en `if` per felt i hvert view ville det ene før
eller siden husket tidene og glemt `probono`; det var akkurat det som hadde skjedd.

**`ressurs_detalj_view` har nå to terskler i ett endepunkt:** navnet krever badge og
reservasjon, alt annet krever `kan_lede`. Bilen heter «Sola 56», ikke «Ambulanse 2», og den
som står ved bilen er den som vet det — mens gruppe, reservasjon og enhetskobling er
beslutninger om *hvem ressursen er til for*, og de flytter tilgangen til seg selv.

**Sletting av et skift ble strengere, også for fylte rader.** Sperren sto bare på de ledige,
fordi et hull i bemanningen ikke skal kunne skjules ved å slette raden som viste det. Det
argumentet gjelder ordrett på en fylt rad: sletter korps-føreren skiftet framfor å melde
forfall, forsvinner plassen og ikke bare personen. Hun tømmer raden i stedet, og da står
behovet.

### Klienten måtte siles, ikke bare gates

**Ett felt hun ikke får sette, velter hele forespørselen** — med vilje, så en halvlagret rad
ikke finnes. Vinduene sendte alltid alle feltene, så uten siling ville et personbytte hun
har lov til gitt 403. `bareTillatteFelter()` i `vaktliste-kjerne.js` siler før sending, med
listene speilet fra `services` og holdt like av `SkiftetsOppsettfelterTests`.

Og markupen måtte si det samme: «Opprett vakt» og tidsfeltene i regnearket sto på
`kanBemanne()` — badgen — så de førte til en vegg. **Tidene vises fortsatt, som tekst:** et
felt man kan skrive i og ikke lagre er verre enn en tekst, for det ser ut som om endringen
gikk igjennom.

### Seks tester sa det gamle, og ble skrevet om framfor slettet

Policyen endret seg, så testene som håndhevet den var ikke feil — de var utdaterte. Hver
enkelt er snudd og har beholdt sitt poeng: `test_korpsbruker_bemanner_sin_egen_ressurs` ble
`test_korpsbruker_oppretter_ikke_skift_men_fyller_dem`, med begge halvdelene i samme test,
fordi hver for seg leser de som om hun enten har alt eller ingenting.

### Mutasjonstesting: 28 mutanter, og fire overlevde først

Etter regelen fra i dag: tungt lag, så hver gren og hver sperre. Seksten på serveren, alle
røde med én gang. Tolv på klienten, der fire overlevde — og alle fire var kjente feller fra
bolken vi skrev noen timer tidligere:

- **To var fikstureringens feil.** Testraden manglet `korps_id`, og `kanRoreRad()` leser
  personens korps på en fylt rad. Raden var altså uredigerbar av en helt annen grunn enn
  den testen målte, og cellene ble tegnet som tekst uansett hva mutanten gjorde. En
  sperrehake står nå ved siden av og krever at raden faktisk *er* hennes.
- **To var kallstedet, ikke funksjonen.** `bareTillatteFelter()` var prøvd for seg, så
  kallet lot seg fjerne fra begge lagrefunksjonene uten at noe ble rødt — altså nøyaktig
  feilen silingen fantes for. `VinduetSenderBareDetHunFaarSetteTests` kjører nå
  `lagreVaktpost()` og `lagreRessurs()` mot en stubbet DOM og leser hva som faktisk ble
  lagt i forespørselen.

Etter rettingene: **28 mutanter, ingen overlevende.**

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-{kjerne,tegning,handlinger,offline}.js`,
`templates/vaktliste/index.html`, `vaktliste/tests_tilgang.py` (+25 tester),
`vaktliste/tests_belastning.py`, `vaktliste/tests_xss.py`, `vaktliste/CLAUDE.md`.
Ingen migrasjon. Hele suiten (3 057 tester) grønn.

---

## 2026-09-15 — CLAUDE.md delt, og mutasjonstestingen har fått et budsjett  `#core/dokumentasjon`

**Bedt om (André), to punkter fra forrige økt:** «CLAUDE.md skal splittes i rot +
per-modul-filer» og «hold mutasjonstesting proporsjonal — tungt på services, lett på UI».

### 1. Fila var blitt en modulhåndbok med et rammeverk foran

1 433 linjer, og 651 av dem — nær halvparten — gjaldt én modul om gangen: vaktlista
alene 489, oppdrag 105, statistikk 44. Alt sammen ble lest inn hver gang, også når arbeidet gjaldt en
skrivefeil i `accounts/`.

| Fil | Linjer | Innhold |
|---|---|---|
| `CLAUDE.md` | 1 433 → 859 | Arbeidsflyt, rammeverk, tilgangsmodell, backup, arkiv, audit, frontend, migrasjoner, drift |
| `patients/CLAUDE.md` | 17 | API-mønsteret og viewdelingen |
| `oppdrag/CLAUDE.md` | 109 | Statusmaskinen, verdimengdene, bilens utganger |
| `vaktliste/CLAUDE.md` | 493 | Korps, skift, drift, planleggeren, offline |
| `statistikk/CLAUDE.md` | 48 | Kilderegisteret og de to gatene |

**Regelen for hva som står hvor følger koden:** ligger den i `core/` eller gjelder den
alle, står den i rota; ligger den i en app, står den i appens fil. Teksten er flyttet
ordrett — dette er en deling, ikke en omskriving.

**Det som *må* vites før man rører en modul, ble værende i rota.** Modulfilene lastes når
noen arbeider i mappa, ikke alltid, så avhengighetsretningen, tilgangsnivåene og «hvert
view under en modul skal være dekorert» kan ikke bo hos modulen. Avhengighetsavsnittet har
derfor fått ett nytt avsnitt: at modul-til-modul går én vei, at `oppdrag` ikke importerer
vaktlista, og at statistikkappen ikke navngir noen kilde — med detaljene hos modulene.

### Den farligste feilen var stille, og den er det testen er til for

`core/tests_dokumentråte.py` leser en liste over dokumenter og kontrollerer at hver filsti,
hver `manage.py`-kommando og hvert slettet symbol i dem fortsatt stemmer. Lista inneholdt
`CLAUDE.md`. **I det øyeblikket nær halvparten av innholdet flyttet ut, ville kontrollen
stilltiende ha sluttet å gjelde for dem** — og det er nettopp modulbeskrivelsene som råtner
fortest, fordi de nevner flest navn. Modulfilene står nå i `DOKUMENTER`.

`core/tests_claude_md.py` (ny) håndhever de tre feilene delingen gjør mulige, etter samme
mønster som `core/tests_js_splitt.py` gjorde for JS-delingen:

| Regel | Hva den fanger |
|---|---|
| Hver `*/CLAUDE.md` står i `DOKUMENTER` | At en ny modulfil slipper unna dokumentråte-kontrollen |
| Tabellen «Hvor dokumentasjonen bor» og filene på disk stemmer begge veier | En modulfil ingen peker på, og en rad som peker på ingenting |
| Ingen modul med egen fil har et avsnitt i rota | At avsnittet vokser tilbake, og regelen finnes to steder |
| Rota under 1 000 linjer | Røykvarsler for at delingen opphever seg selv |

**Fem mutasjoner prøvd, alle røde** — men den femte overlevde først, og på en måte som er
verdt å skrive ned: jeg hadde endret ingressen i `vaktliste/CLAUDE.md` uten å fjerne ordet
regelen faktisk ser etter. Mutanten traff ikke regelen, og et «OK» fra den ville ha
bekreftet en dekning som ikke fantes. Rettet mutant: rød.

**Grensen testen ikke ser:** at fila er delt, ikke at innholdet står riktig sted. En
vaktlisteregel skrevet i rota fanges bare hvis den får en overskrift med `(vaktliste/)` i.
Det er samme grense som resten av dokumentverktøyet har — tall og navn lar seg måle, mening
ikke.

### 2. Mutasjonstesting: budsjettet følger hva en overlevende mutant koster

Anledningen var tretten mutanter på et `datetime-local`-felt og to på en tilgangsport.
Regelen står nå i `CLAUDE.md`, som en stige fra tungt til ingenting: tjenestelaget og
rammeverket (tilgang, arkiv, backup, offsite, migrasjoner) tungt, views og de
JS-funksjonene som *avgjør* noe — `avgjor()`, `kanBemannePlass()`, `lydSkalSpille()`,
`klikkSkalKjore()` — middels, byggere og tegning lett, CSS og tekst ingenting.
**Målestokken er hva brukeren ville sett:** ser hun feilen med det samme, holder én mutant
på regelen som avgjør; ser hun den aldri, hører innsatsen hjemme der.

Med regelen følger **de tre måtene en mutant lyver på**, alle tre sett i dette prosjektet
og alle tre spredt i eldre CHANGELOG-oppføringer der ingen leter: at søk-og-erstatt traff
et annet sted enn du tror, at mutanten var en no-op, og at testen kaller hjelperen selv så
kallstedet kan fjernes. Pluss den fjerde, som ikke er mutantens feil — at fikstureringen
ikke bar prod-formen, slik `_dagbolker()` overlevde fordi testskiftene sto i norsk tid og
ORM-en gir UTC.

**Endret:** `CLAUDE.md`, `patients/CLAUDE.md`, `oppdrag/CLAUDE.md`, `vaktliste/CLAUDE.md`,
`statistikk/CLAUDE.md` (alle fire nye), `core/tests_claude_md.py` (ny, 6 tester),
`core/tests_dokumentråte.py`, `README.md`, `TODO.md`. Ingen kodeendring — hele suiten
(3 024 tester) grønn.

---

## 2026-09-15 — «Ny vaktliste»: tidsfeltene som i planleggeren  `#vaktliste/planlegging`

**Bedt om (André):**

> «Etterpå når det er i orden så vil jeg ha lik tidsfelt som vi har i planleggeren når en
> skal lage ny vaktliste. Der er det mismatch og den i ny vaktliste er litt knotete.»

**`type` og `step` var like fra før** — begge er `datetime-local` med `step="300"`. Det som
manglet, var alt det andre som gjør planleggerens felter behagelige. Et tomt
`datetime-local` må tastes inn segment for segment uten noe å nudge på, og det er det
«knotete» betyr.

| Regel | Hvorfor |
|---|---|
| **Feltene står aldri tomme** | `apneNyVaktliste()` fyller dem ut *før* vinduet vises. Derfor åpnes vinduet nå av JS og ikke av `data-bs-toggle`: et skjema som fyller seg selv etter at man ser det, ser ut som om noe rettet det man skrev |
| **Starten settes til neste hele time** | `new Date()` gir 21:37, og med `step="300"` er nærmeste lovlige verdi 21:35 — et tall ingen har ment. Planleggeren slipper spørsmålet fordi den har vaktas start å bygge på; her *er* feltet vaktas start |
| **Slutten følger starten, til noen rører den** | Samme idé som at et nytt skiftvindu begynner der det forrige sluttet. Har du skrevet «søndag 14:00», skal en rettelse av startdatoen ikke dra sluttiden med seg — da hadde feltet spist det du nettopp skrev. Et tomt sluttfelt teller ikke som rørt |
| **Spennet leses tilbake under feltene** | «Vakten varer 2 d 6 t.» Som tallet under et skiftvindu i planleggeren, og den ene tilbakemeldingen som fanger den vanligste tastefeilen her: riktig klokkeslett på feil dato |

`_varighetstekst()` skriver «2 d 6 t», ikke «54 t»: planleggeren skriver bare timer fordi
et skift er kort nok til at tallet leses, men en vakt går over dager, og et tosifret
timetall sier ikke om man traff riktig dato. Hele døgn skrives uten timerest — «2 d 0 t»
leser som om noe mangler.

Et bakvendt spenn merkes **gult, ikke rødt**, som et ugyldig skiftvindu: serveren avviser
det uansett (`opprett_planlagt_vakt` hadde regelen fra før), så dette er en beskjed om at
man ikke er ferdig.

**Mutasjonsprøvd** — tretten mutanter på de fire reglene.

**Endret:** `static/js/vaktliste-handlinger.js`, `templates/vaktliste/index.html`,
`vaktliste/tests_xss.py` (+17 tester), `vaktliste/tests_tilgang.py`, `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: budsjettet manglet, og oppsettet ble glemt  `#vaktliste/planlegging` `#vaktliste/belastning`

**Meldt fra staging (André):**

> «1. tak på vaktene og timene er ikke synlige når du oppretter ny vaktliste og går inn i
> planlegger.
> 2. når en har lagt grunnlag og vil redigere så er det ikke lenger i "planlegger" det må
> vel gå ann å huske dem og la en redigere der?»

### 1. Budsjettlinja ble aldri hentet

`mkBudsjett()` gir tom streng uten `belastning`, og `visFane()` hentet den bare for
belastningsfanen. Planleggeren sto utenfor regelen, så taket og timene var **usynlige
nettopp der de skal styre arbeidet** — og synlige bare i fanen som rapporterer i etterkant.
Ingenting feilet; linja bare manglet.

Regelen står nå som **én funksjon**, `faneTrengerBelastning(id)`, fordi den har to lesere:
fanevalget i `visFane()` og korpsvelgeren i `velgKorps()`, som nullstiller tallene og
henter dem på nytt.

### 2. Planleggeren leser oppsettet tilbake fra vaktlista

Etter en generering tømte klienten `planleggerlinjer`, med den begrunnelsen at et andre
trykk ellers ville laget «Lag 4, 5, 6» ved siden av «Lag 1, 2, 3». Begrunnelsen var riktig;
løsningen var feil sted å løse den.

**Planleggeren husker ikke det du skrev — den leser hva som står.** Det er en viktigere
forskjell enn den ser ut: en husket kladd og virkeligheten glir fra hverandre i det
øyeblikket noen retter et skift i regnearket, og da ville et trykk på «Lag grunnlaget»
rullet den rettelsen tilbake.

| Nytt | Hva det gjør |
|---|---|
| `planleggerLesTilbake()` | Én rad per ressurs, vinduene gruppert på plassenes tider. Seks plasser 14–22 leses tilbake som ett vindu med seks |
| `planleggerSikreLinjer()` | Står det ingenting i oppsettet, leses det tilbake. Har du skrevet noe, røres det ikke |
| `linje.ressurs_id` | Gjør raden til en **redigering** på serveren |
| `services._beholdt_og_kladd()` | Ressursens plasser delt i to: de som står, og kladden som lages på nytt |
| `services._nye_plasser()` | Hvor mange hvert vindu faktisk oppretter |

**«Plasser» er vinduets hele bemanning, ikke et påslag.** Står det fire 14–22, skal det
være fire etterpå — også når to av dem har navn på seg. De som står telles fra, og bare
differansen lages. Uten fratrekket ville en ressurs man redigerte to ganger vokst for hver
gang, og tallet i feltet sluttet å bety det det sier. Beholdningen forbrukes **per vindu**,
ellers ville to like vinduer i samme rad begge trukket fra de samme plassene.

**Gruppa og navnet følger ressursen, ikke linja.** Raden som står viser navnet der
nedtrekket ellers står, og knappen heter «Ta ut» — å fjerne en ressurs er en sletting, og
den ligger bak de to bekreftelsene i «Rediger ressurs».

**`erstatt_kladd` er fjernet.** Bryteren ryddet kladd på hele lista, også på ressurser
oppsettet ikke nevnte. Nå er raden som peker på ressursen den eneste som rører den, og en
ressurs utenfor oppsettet lar generatoren være i fred.

**Bekreftelsen viser endringen, panelet viser oppsettet.** Sammendraget teller bare nye
ressurser og nye plasser, og har fått `fjernes` ved siden: å redigere et vindu fra seks
plasser til fire sletter to, og det er det eneste i hele planleggeren som fjerner noe.

### Mutasjonsprøvd

Atten mutanter. Den ene som overlevde første runde er verdt å merke seg: testene kalte
`planleggerSikreLinjer()` selv, så `tegnPanel()` kunne slutte å kalle den uten at noe ble
rødt — altså nøyaktig feilen André meldte. `PlanleggerenTegnesMedOppsettetTests` tegner nå
panelet med den ekte `tegnPanel()`.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-kjerne.js`, `-tegning.js`, `-oversikt.js`, `-handlinger.js`,
`templates/vaktliste/index.html`, `static/css/vaktliste.css`,
`vaktliste/tests_planlegger.py`, `vaktliste/tests_xss.py`, `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: tidsfeltene lot seg ikke skrive i  `#vaktliste/planlegging`

**Meldt fra staging (André):**

> «Her er det frustrerende vanskelig å redigere med tastatur på tidsrom, jeg kan bare ta
> inn ett tall om gangen.»

Årsaken var min egen: hver `change` kalte `tegnPanel()`, som bygger hele panelet på nytt
med `innerHTML`. Da **erstattes feltet man står i**, og fokus og markør forsvinner med det.
`datetime-local` melder `change` per segment, så feltet forsvant etter hvert tall man skrev.

### Regelen som mangler

**Feltendringer oppdaterer tallene på plass; strukturendringer tegner på nytt.**

`planleggerTegnTall()` setter `textContent` på `[data-vindutall]`, `[data-linjetall]` og
`[data-plantall]` — tallet under vinduet, regnestykket under raden, og totalen nederst.
Advarselen for et bakvendt tidsrom settes med `classList.toggle`, ikke med ny markup.

**Gruppevalget er unntaket** og tegner fortsatt på nytt: «Antall» finnes ikke for grupper i
ett eksemplar, så raden skifter form — og et nedtrekk er man ferdig med når man har valgt,
så omtegningen koster ingen markør.

Teksten under vinduet bygges av `_vindutallTekst()`, som er **ren tekst uten markup**:
samme funksjon brukes av byggeren og av oppdateringen, så de to formene ikke kan komme i
utakt.

### Mutasjonsprøvd

Fem mutanter, og den ene som overlevde er verdt å merke seg: testen min sjekket bare
*totalen*, så et vindutall som frøs gikk grønn. Den måler nå alle tre nivåene, og at
advarselsklassen faktisk settes.

**Endret:** `static/js/vaktliste-oversikt.js`, `static/js/vaktliste-handlinger.js`,
`vaktliste/tests_xss.py` (+4 tester), `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: «Legg til ressurs» flyttet ned  `#vaktliste/planlegging`

**Meldt fra staging (André):**

> «Legg til ressurs bør ligge mellom sist opprettet ressurs og lag grunnlag for
> forståelsen skyld. For nå er det lett å tro at man bare lager en ressurs og så er man
> ferdig.»

Knappen sto i hodet, over radene. Der leser den som **«start her»** — og har du laget den
ene raden, er det neste du ser generer-knappen. Mellom radene og «Lag grunnlaget» leser den
som **«legg til én til»**, og rekkefølgen i panelet blir den man arbeider i: sett opp, legg
til flere, lag grunnlaget.

Den står også når oppsettet er tomt; ellers kommer man aldri i gang.

Tre mutanter prøvd: knappen tilbake i hodet, knappen etter generer-knappen, og knappen
borte på et tomt oppsett. Alle fanges — plasseringen er en regel nå, ikke en tilfeldighet i
markupen.

**Endret:** `static/js/vaktliste-oversikt.js`, `static/css/vaktliste.css`,
`vaktliste/tests_xss.py` (+2 tester), `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: plassene flyttet til vinduet, skiftlengde fjernet  `#vaktliste/planlegging`

**Meldt fra staging (André):**

> «Fungerte veldig fint for ressurser som deler like tider. For samleplass og KO ble
> «antall» forvirrende, «skiftlengde» er og forvirrende. Noen ganger ønsker man å ha
> mindre og mer plasser på enkelte skift visse deler av døgnet.» … «Har vi noe behov for
> skiftlengde?»

### Tre tilbakemeldinger som viste seg å være én

**Plassene hører til vinduet, ikke til ressursen.** Samleplassen kan ha seks plasser
14–22 og to 22–06 — det er **én** samleplass med to vinduer, ikke to samleplasser. Linja
sier nå *hva* (gruppe, hvor mange enheter), vinduet sier *når og hvor mange*.

**Og det er grunnen til at `skiftlengde` måtte gå.** Den var en *skjult multiplikator*:
den lagde seks skift ut av ett vindu, du så dem aldri, og alle seks fikk samme antall
plasser — altså nøyaktig det som ikke lot seg uttrykke etter flyttingen. En rotasjon settes
nå opp som de skiftene den er, og «Nytt skiftvindu» begynner der det forrige sluttet og
arver antallet, så Haugesund 56 er seks klikk. André valgte å fjerne den helt framfor å
erstatte den med en «del opp»-knapp.

**«Antall» finnes ikke for Samleplass og KO.** `flere_enheter=False` betyr at det bare kan
være én; serveren avviste alt annet fra før, men feltet sto der og lot som om det var et
valg. Nå står det «Finnes i ett eksemplar» i stedet.

### En feil funnet på veien

`plasser: 0` ble stille til `1`. Viewet gjorde `_int(...) or 1` **før** services fikk se
verdien, så regelen «hvert skiftvindu må ha minst én plass» kunne aldri fyre på et
eksplisitt null. Parsingen er flyttet til `services._linjens_skift()`, som eier regelen;
viewet sender råverdien videre.

### Mutasjonsprøvd

Åtte mutanter, sju drept med en gang: plassene lest fra linja igjen, null stille til én,
alle vinduer med første vindus antall, timesummen uten plasser, antallsfeltet vist/skjult
for alle, og klienten som teller per linje i stedet for per vindu.

Den ene som overlevde var «nytt vindu arver ikke forrige vindus antall» — en oppførsel jeg
valgte bevisst og ikke testet. Den har en test nå.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`,
`static/js/vaktliste-oversikt.js`, `static/js/vaktliste-handlinger.js`,
`static/css/vaktliste.css`, `vaktliste/tests_planlegger.py`, `vaktliste/tests_xss.py`,
`CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: feltene lot seg ikke fylle ut  `#vaktliste/planlegging`

**Meldt fra staging (André):**

> «1) Når jeg har satt dato for vakten og åpner tidsrom skiftene skal starte, så begynner
> de på dagens dato og ikke vaktens starttidspunkt. 2) Og den er mer kritisk: jeg får ikke
> fylt feltene, de gir meg blankt på alle — antall, plasser per skift, fra, til.»

### Én feil, ikke to

Delegeringen i `portal-utils.js` sender **ett** argument — med mindre elementet bærer
`data-felt`, og da sender `hendelseArgumenter()` `(id, felt, verdi)`. Planleggerfeltene
ble skrevet med `data-arg="0:1:fra"` og handlere som tok `(arg, verdi)`. `verdi` var
derfor alltid `undefined`: hvert tastetrykk skrev `undefined` inn i tilstanden, og feltet
ble blankt ved neste tegning.

**Bug 1 var en følge av bug 2.** Standardvinduet var riktig hele tiden — målt: med vaktas
start 2. okt. 14:00 fylles feltet med `2026-10-02T14:00`. Men bug 2 tømte feltet ved første
berøring, og en tom `datetime-local` åpner på dagens dato.

**Regelen sto allerede i `CLAUDE.md`**, i avsnittet om `data-action` + `data-hendelse`.
Jeg skrev koden som om den ikke gjorde det.

### Fikset

Feltene bruker nå samme idiom som cellene i ressurstabellen — `data-felt` + `data-id` — og
adressen er en **stabil klient-ID**, ikke en indeks: `splice()` ville ellers flyttet
adressen til hver rad under den man fjernet, og neste tastetrykk skrevet i feil rad.

I tillegg: har vakta **ingen starttid**, faller standardvinduene tilbake til nå, og da sier
panelet fra. «Dagens dato» uten forklaring ser ut som et valg noen har tatt framfor et
fravær.

### Testen som manglet, og hvorfor de gamle ikke så det

De fjorten testene fra i dag kalte `mkPlanlegger()` og leste markupen. Ingen av dem rørte
handlerne, så en feil signatur var usynlig.

`PlanleggerfanenTests._skriv()` plukker nå attributtene ut av den **ekte** markupen og
sender dem gjennom delegeringens egen `hendelseArgumenter()` — argumentene bygges nøyaktig
som i nettleseren. Fire mutanter prøvd mot den: den opprinnelige signaturen, et felt uten
`data-felt`, indeks i stedet for ID, og `new Date()` i standardvinduet. Alle fanges.

**Og én av de nye testene gikk grønn ved flaks.** «Å fjerne en rad flytter ikke adressen
til de andre» sjekket bare lengden og den siste ID-en — med ID-ene 1, 3, 5 falt indeksene
slik at den siste ble den samme uansett hvilken rad som forsvant. Den krever nå hele
ID-lista.

**Endret:** `static/js/vaktliste-oversikt.js`, `static/js/vaktliste-handlinger.js`,
`vaktliste/tests_xss.py` (+10 tester), `CLAUDE.md`.

---

## 2026-09-15 — Planleggeren: fanen som lager grunnlaget  `#vaktliste/planlegging`

**Meldt fra staging (André):**

> «Litt usikker på om vi har skjønt hverandre. Du har lagt det inn i «planlegging»-fanen.
> Jeg ba om en **planlegger**. Den skal bare admin og leder ha tilgang til. For den
> genererer grunnlaget på alt. Vi skal kunne legge inn skift f.eks. tre firemanns lag fra
> kl. 14–22 og en ambulanse fra 15–03 mens en ambulanse går 8 timer rotasjon.»

### Misforståelsen, og hvor den kom fra

Hans opprinnelige melding nevnte generering først og timetallet sist. Notatet jeg skrev på
grunnlag av den snudde rekkefølgen: taket ble hovedsaken, og generatoren ble «steg 5, i sin
enkleste form — N plasser på én ressurs». Det er ikke det han ba om.

**«Planlegging» og «Planlegger» er to ulike fanér med to ulike spørsmål:**

| Fane | Spørsmål | Hvem |
|---|---|---|
| Planlegging | Hva koster lista dem som står i den? | `les` |
| **Planlegger** | Hva skal lista bestå av? | `kan_lede` |

Budsjettlinja og dagslinja er flyttet til «Planlegger» — «sette inn total timer og jobbe
overordnet» er lederens verktøy. Regnestykket var uavhengig av flata og fulgte med
uendret; det var bare plasseringen som var feil.

### Ressursen er subjektet, skiftvinduene hører til den

Andrés to ambulanser har ulik form, og Sola 56 bestemte datamodellen i skjemaet:

| Enhet | Oppsett | Blir |
|---|---|---|
| Haugesund 56 | 2 plasser, fre. 14 → søn. 14, skiftlengde 8 | 6 skift × 2 = **12 plasser, 96 t** |
| Sola 56 | 2 plasser, **to vinduer**: fre. og lør. 15–03 | 2 skift × 2 = **4 plasser, 48 t** |
| Lagene | 3 ressurser, 4 plasser, fre. 14–22 | **12 plasser, 96 t** |

Sola 56 er grunnen: hennes to vakter er **adskilte** — ikke en periode som deles, og ikke
to biler. Var raden i skjemaet et skiftvindu framfor en ressurs, hadde hun blitt til
«Ambulanse 1» og «Ambulanse 2».

**`skiftlengde` er det ene feltet som skiller formene.** Tom = ett skift som dekker
vinduet; et tall deler vinduet rygg mot rygg. Den siste bolken **kortes av, den strekkes
ikke**: 20 timer i åttetimersskift er 8 + 8 + 4, og et skift som varer lenger enn vakta
ville dukket opp som et brudd på skiftlengdegrensa uten at noen satte det opp.

### «Plasser per skift», ikke «antall folk»

André beskriver Haugesund 56 som «4 stk fordelt på 2 lag som går 8 på og 8 av». Modellen
trenger **2** — bilen har to seter, og de fire er bemanningspoolen som fyller tolv
skiftplasser over 48 timer. Feltet heter derfor «plasser per skift», og regnestykket står
under raden: «2 plasser × 6 skift = 12 plasser, 96 t». Oversettelsen fra hvordan man
snakker om bemanning til hva modellen lagrer skal være synlig **før** man trykker.

### Det som holder genereringen trygg

- **Plassene fødes som planlagt kladd** — usynlige for korpsene til lederen deler dem ut.
  Uten det ser et halvferdig oppsett ferdig ut i det øyeblikket knappen trykkes.
- **`erstatt_kladd` rører bare kladden.** Korpsreserverte, `alle_korps` og **alle**
  bemannede står. Reservasjonen leses av `reservert_korps()`, ikke av feltet — leses
  feltet direkte, slettes en hel bils plasser fordi ressursen bærer korpset.
- **Ingen `bulk_create`, alt i én `transaction.atomic()`.** Ikke bare for signalenes
  skyld: `erstatt_kladd` sletter før den skriver, så en feil halvveis ville etterlatt
  lista tommere enn før man trykket.
- **`?forhaandsvis` regnes av samme kode** (`_planlegg` + `_sammendrag`), på samme
  endepunkt. En forhåndsvisning som regner på egen hånd viser før eller siden noe annet
  enn det som skjer.
- **Grupper i ett eksemplar** (`flere_enheter`) avvises også her. En generator som lager
  «Samleplass 2» er akkurat den feilen flagget finnes for.

### Mutasjonstesting: 24 mutanter, og tre bommer verdt å skrive ned

**En mutasjon traff feil funksjon.** `if not services.kan_lede(request.user):` står også i
`vaktliste_detalj_view`, og `replace(..., 1)` tok den første — så porten jeg trodde jeg
prøvde var en annen. Et «OK» fra en mutasjon som ikke traff er verre enn ingen mutasjon:
den *bekrefter* en dekning som ikke finnes.

**To mutanter var no-ops.** `start = start + steg if False else slutt` er identisk med
`start = slutt`. Overlevelse betyr ingenting da.

**To fant ekte hull:**
- `erstatt_kladd` uten scope til vaktlista overlevde, fordi testen la «plassen på den
  andre lista» på en ressurs som var reservert til Haugesund — altså beholdt uansett. Den
  ligger nå på en ureservert ressurs, med en assertion om at den faktisk *er* kladd.
- `transaction.atomic()` lot seg fjerne, fordi all validering skjer i `_planlegg` *før*
  skrivingen. Det som manglet var en feil underveis: en test patcher nå
  `Ressurs.objects.create` til å feile på andre kall, og krever at den slettede kladden
  står der etterpå.

På klientsiden overlevde `Math.ceil` → `Math.floor`, fordi alle eksemplene mine gikk opp i
hele skift (48/8, 8/8). Og porten på selve fanen lot seg fjerne — ingen test spurte om
fanen var *borte* for `skriv_full`. Begge har tester nå.

### Ellers

**Skanneren leste ikke de nye byggerne** — igjen. `mkPlanlegger`, `_planleggerLinje`,
`_planleggerVindu` og `_genererFasit` sto én kjøring uten å være i `HTML_BUILDERS`. Det er
andre gang på én dag.

**Og skanneren har et hull som er verdt å kjenne:** den ser bare `${…}` inne i
template-literaler. `mkPlanlegger()` og `mkBelastning()` avslutter begge med
`hode + \`…\` + linjer + tomt`, og de konkatenerte leddene går forbi registeret uten et
ord. Verdiene er lokalt bygget markup i begge tilfeller, så det er ikke et hull i dag —
men regelen dekker mindre enn den ser ut til. Ført opp i TODO; det er samme sort feil som
`accounts/decorators.py` hadde, der en test som bare dekket halve syntaksen sto grønn i
et år.

**Endret:** `vaktliste/services.py`, `vaktliste/views.py`, `vaktliste/urls.py`,
`static/js/vaktliste-{kjerne,tegning,oversikt,handlinger}.js`,
`static/css/vaktliste.css`, `templates/vaktliste/index.html`,
`vaktliste/tests_planlegger.py` (ny, 42 tester), `vaktliste/tests_xss.py` (+16 tester),
`docs/FORSLAG_PLANLEGGERFANE.md`, `docs/TEKNISK_DOKUMENTASJON.md`, `CLAUDE.md`, `TODO.md`.

---

## 2026-09-15 — Vaktas budsjett: steg 2 og 3 mot planleggerfanen  `#vaktliste/belastning`

`docs/FORSLAG_PLANLEGGERFANE.md` §7, steg 2 og 3. **Gjort i samme omgang med vilje:** en
«budsjettlinje» uten et budsjett er halve funksjonen, og taket er ett felt pluss én linje i
`kopier_oppsett`. Å dele dem ville betydd å bygge linja to ganger.

### Tre beslutninger til, tatt fordi koden sa noe annet enn notatet

**12. Linja bor i fanen som alt finnes.** Skissen sa «fanen ligger ved siden av «Oversikt»
og «Mannskap»» — men det finnes allerede en slik fane, og den heter **«Planlegging»**. En
ny ved siden av ville gitt to faner med én bokstavs forskjell, og den som leter etter
tallene sine måtte prøve begge. Budsjettlinja står derfor øverst i «Planlegging», over «Per
person»: vaktas tall først, den enkeltes under — motsatt ville begravet totalen under en
persontabell som kan bli lang.

**13. Taket er `skriv_leder`, ikke `skriv_full`.** Notatets §4 sa `skriv_full`. Det holdt
ikke mot koden: taket settes i **samme PUT** som vaktas start og planlagte slutt, og den er
`skriv_leder` med en begrunnelse som gjelder ord for ord her også — «spennet gjelder hele
vakta, ikke ett korps' del av den». Taket er tallet *alle* varsler på lista måles mot. Og
en PUT der `startet` krever ett nivå og `timetak` et annet er en regel ingen klarer å lese
riktig. Det gjør taket til per-vakt-søsteren av `Belastningsgrenser`, som også er
`skriv_leder`; forskjellen er rekkevidden, ikke hvem som bestemmer.

**14. Tallene sendes bare til den som ser alle korps.** De er hele vaktas og filtreres
aldri — taket gjelder lista, så et «satt opp» for ett korps kunne ikke sammenlignes med
det. Men da kan de heller ikke sendes til alle: for en `les` med badge ville summen vært et
aggregat over skift hun ikke får se. Samme regel som statistikkmodulen bruker.
`belastning_view` sender `planlegging: null`, og klienten tegner ingen linje — **ingen tom
ramme**, for den ville sagt «her er noe du ikke får se», som er en dårligere beskjed enn
ingen beskjed. Hennes egne timer står i «Mitt korps».

### Tallene

`services.planleggingstall()` gir **tre tall side om side**, fordi hvert av dem alene lyver
litt: «satt opp» er behovet, men ingen betaler for en tom plass; «bemannet» er nærmest
kostnad, men står på null når lista er halvt satt opp; «probono» vises for seg så summen
ikke utelater noe i stillhet (beslutning 9), og bare når det finnes noe å vise.

Avstanden mellom de to første er **selve arbeidslista**, så den regnes ut og står der:
312 satt opp mot 244 bemannet er 68 timer som mangler folk.

**`igjen` måles mot «satt opp»**, ikke mot «bemannet»: planlegging handler om behovet, og
et budsjett som først fylles når navnene er på plass sier «du har alt igjen» på en liste
som er ferdig satt opp. Går man over, blir tallet gult og etiketten bytter fra «igjen» til
«over taket» — et negativt tall under «igjen» leses som en regnefeil. **Ingenting avvises.**

**Dagslinja** bryter ned «satt opp» per dag, uten egne tak (beslutning 2), og sier det i
overskriften: «Satt opp per dag». Uten etiketten måtte leseren gjette hvilket av de to
tallene over den dagene summerer til. Den står ikke på en endagsvakt — én dag er ingen
nedbryting, bare totalen skrevet to ganger.

### To mutanter som fant ekte hull

**Rekkefølgen var garantert av modellen, ikke av regelen** — nøyaktig samme felle som
`_hviletider()` dokumenterer, og som traff oss 14. sep. også. `sorted()` lot seg fjerne
uten at noe ble rødt, fordi `Vaktpost.Meta.ordering` alt sorterer på `fra_tid`, så testene
gjennom basen målte modellens ordering. Dagbolkene er nå en egen funksjon, `_dagbolker()`,
prøvd med lister kalleren *ikke* har sortert.

**`timezone.localtime()` lot seg fjerne**, og testen min kunne ikke se det: de falske
skiftene bar norsk tid, mens ORM-en leverer UTC — da var `.date()` alt riktig. Rettet i
testen, ikke i koden. Feilen den vokter er verdt å kjenne: et skift som begynner 00:30
norsk tid er 22:30 UTC dagen før, så uten `localtime()` havner hver eneste nattevakt på
feil dag. Usynlig for alt som begynner på dagtid.

### Ellers

**Skanneren leste ikke de nye byggerne.** `mkBudsjett`, `mkDagslinje` og `_budsjettpost`
sto én kjøring uten å være i `HTML_BUILDERS`, og da var escaping-regelen stille av for dem
— suiten var grønn fordi ingen så etter, ikke fordi koden var riktig. En ny bygger som
skanneren ikke leser er nøyaktig det hullet den lista finnes for.

`kanSetteTak()` leser **serverens** `kan_sette_tak`, ikke `MODUL_TILGANG`: regnet klienten
den ut selv, kunne knappen og endepunktet komme i utakt, og en knapp som fører til en vegg
er verre enn ingen knapp.

Migrasjonen (`vaktliste/0018`) er ren skjemaendring uten `RunPython`, så den har ingen
triggerkø å tømme.

**Endret:** `vaktliste/models.py` + `migrations/0018_vaktliste_timetak.py`,
`vaktliste/services.py`, `vaktliste/views.py`, `static/js/vaktliste-oversikt.js`,
`static/js/vaktliste-kjerne.js`, `static/js/vaktliste-handlinger.js`,
`static/css/vaktliste.css`, `templates/vaktliste/index.html`,
`vaktliste/tests_belastning.py` (+29 tester), `vaktliste/tests_xss.py` (+14 tester),
`docs/FORSLAG_PLANLEGGERFANE.md`, `TODO.md`, `CLAUDE.md`.

---

## 2026-09-15 — Overlappet har fått et navn: steg 1 mot planleggerfanen  `#vaktliste/belastning`

Første kodesteg fra `docs/FORSLAG_PLANLEGGERFANE.md` §7. Punktet sto i TODO fra
14. sep. 2026 og var ført opp som det som måtte løses **før** planleggeren: et tak som
telles feil er verre enn ikke noe tak.

### Docstringen lovet en telling som ikke fantes

`vaktliste/services._hviletider()` sa «Overlappet i seg selv fanges av
`overlapp`-tellingen». Det var ingen `overlapp`-nøkkel i belastningsraden. Det som
faktisk skjedde var at `korteste_hvile` ble `0.0` og raden ble flagget som **kort
hvile** — altså ble et dobbeltbooket mannskap vist som et hvileproblem, og planleggeren
fikk aldri vite hva det egentlig var.

### `_overlappstimer()`: sum minus union

12:00–20:00 og 16:00–22:00 er 8 + 6 = 14 timer skift, mens personen er til stede fra 12
til 22 — ti timer. Differansen, fire, er overlappet. Definisjonen er valgt fordi den gir
invarianten `timer - overlapp = faktisk tilstedeværelse`, og den er målt i en test framfor
antatt i en kommentar.

**Summen står fortsatt på 14.** Den er ikke korrigert, den er **navngitt**: raden sier at
fire av timene er dobbeltbooket, og vaktlederen retter det. Et tall som stille korrigerer
seg selv ville skjult nettopp den feilen vi ville vise — «varsler, de sperrer ikke».

**Probono teller med her, i motsetning til i `timer`.** Summen er det organisasjonen
betaler for; et overlapp er at én person står to steder, og kroppen skiller ikke på lønn.
Samme resonnement som `lengste_skift` og `korteste_hvile` alt sto på.

**Rundet én gang, til slutt.** Summeres avrundede timetall hver for seg, kommer
differansen ut som 0.01 for skift som ikke overlapper — og et varsel som fyrer på en
avrundingsfeil er et varsel man slår av. Testen bruker et **funnet** tilfelle
(02:53–07:27, 07:27–14:40, 16:56–21:01), søkt fram blant tilfeldige oppsett, fordi den
første varianten jeg skrev ned ga −0,03 og altså ikke viste det jeg påsto den viste.

### I grensesnittet

Ny **Overlapp**-kolonne i belastningstabellen, som bare står når noen faktisk er
dobbeltbooket — samme regel som Faktisk-kolonnen: en kolonne full av nuller stjeler bredde
fra dem som betyr noe. Pluss et varsel i hodet: «1 dobbeltbooket — 4 t».

**Varselet sier timene, ikke en terskel.** Et langt skift måles mot organisasjonens
grense, fordi det er en vurdering noen har gjort. To skift på samme person samtidig er en
planleggingsfeil uansett hva grensene sier, så det har ingen grense å måle mot.

**`<colgroup>` regnes nå ut.** To valgfrie kolonner gir fire former, og fire håndskrevne
blokker er fire steder å glemme når kolonne nummer ni kommer — med `table-layout: fixed`
gir feil antall `<col>` ingen feilmelding, bare en tabell som er litt gal.
`_kolonneandeler()` normaliserer vektene til hele prosenter og fordeler resten etter
størrelse, ikke etter rekkefølge. Testen teller `<th>`-ene framfor å skrive av et
forventet tall.

### Mutasjonsprøvd

Ni mutanter, sju drept med en gang. To overlevde og var **ekvivalente** (`len(spenn) < 1`
og `fra >= slutt` gir samme svar) — begge er nå notert i koden, slik at neste leser ikke
leter etter et hull som ikke finnes.

To mutanter avslørte ekte svake assertions, og begge av samme sort: testen traff et annet
sted i svaret enn den mente. «4 t» står både i varselet og i raden, så en `assertIn` mot
hele utdata gikk grønn når cella alltid ga streken, og når varselet mistet tallet sitt.
Begge leser nå ut av sin egen blokk (`<tbody>`, `vl-varsler`).

### Beslutning 9–11 i planleggernotatet

Tre spørsmål notatet ikke stilte, funnet ved å lese koden før byggingen begynte:

- **Probono teller ikke mot taket, men vises for seg.** `_sumTimer()` utelot dem allerede;
  en budsjettlinje som utelater noe uten å si det er et tall noen vil bestride.
- **Genererte plasser fødes som planlagt kladd** (`services.er_planlagt()`), usynlig for
  korps-brukerne til de deles ut.
- **«Åpen for alle»-plasser overlever en ny generering**, som de korpsreserverte. Med
  beslutning 10 blir regelen én setning: generatoren rører bare det `er_planlagt()` kaller
  kladd.

### Og en fil som måtte deles

De nye linjene dyttet `vaktliste-tegning.js` over 1 800, og
`test_hver_del_er_mindre_enn_den_var` sa fra. Det er nettopp den regelen som gjør
JS-delingen fra 14. sep. verdt noe: uten den kunne én fil vokst tilbake til 3 800 linjer
mens de andre sto tomme, og alle de andre reglene vært grønne hele veien.

`vaktliste-oversikt.js` er skilt ut, og skjøten er ikke vilkårlig: **alt over den tegner
regnearket** — fanene, ressurskortene og radene man redigerer i — og **alt under leser de
samme skiftene og svarer på noe annet**: bemanningskurvene, utskriftslista, belastningen,
«Tilstede nå», «Mitt korps». De to sidene deler `_posterFor()`, `_sumTimer()` og
`_skifttimer()`, som blir stående i tegningsfila.

941 og 921 linjer. `VAKTLISTE_JS` og `<script>`-taggene i malen holdes like av
`VaktlisteFileneDekkerAltTests`, og ingenting i den nye fila kjører på toppnivå.

**CLAUDE.md sa «Sytten filer i `static/js/`».** Det var 23. Tallet sto ikke i
`PAASTANDER`, så `TallpaastanderTests` kunne ikke se det — den vokter
`TEKNISK_DOKUMENTASJON.md`, som var riktig helt til denne delingen og ble rettet av testen
med en gang. Et tall ingen test leser, råtner; begge er rettet nå.

**Endret:** `vaktliste/services.py`, `static/js/vaktliste-tegning.js`,
`static/js/vaktliste-oversikt.js` (ny), `templates/vaktliste/index.html`,
`patients/js_test_utils.py`, `vaktliste/tests_belastning.py` (+19 tester),
`vaktliste/tests_xss.py` (+6 tester), `docs/FORSLAG_PLANLEGGERFANE.md`,
`docs/TEKNISK_DOKUMENTASJON.md`, `CLAUDE.md`, `TODO.md`.

---

## 2026-09-15 — Planleggerfanen: åtte beslutninger, og en rettelse av mitt eget notat  `#vaktliste/planlegging`

Gjennomgang av `docs/FORSLAG_PLANLEGGERFANE.md` med André. Ingenting er bygget — dette er
underlaget som gjør at det *kan* bygges uten å ta de samme avgjørelsene om igjen.

### Rettelsen først

Notatets §3.3 hevdet at planleggeren «bør følge rapportmodulens midnattsregel, fordi det er
*timer* som telles», og at de to reglene derfor sto i konflikt. **Det var feil.** Splitting
ved midnatt endrer ikke en totalsum — fredag 20:00 til lørdag 04:00 er åtte timer uansett
hvilken dag de føres på. Regelen betyr bare noe når timene **brytes ned per dag**.

Det gjorde spørsmålet i §5 feilstilt: det fantes ingen konflikt å løse, bare et valg om
hvilken dag dagslinja fører timene på. Avsnittet er skrevet om, med feilen stående, fordi
et notat som stille retter seg selv ikke lærer den neste leseren noe.

### Beslutningene (André)

| # | Spørsmål | Svar |
|---|---|---|
| 1 | Hva er timetallet? | **Tak som varsler**, ikke inngangsverdi (avgjort tidligere) |
| 2 | Tak per dag? | **Nei — ett tak for hele vakta**, pluss en dagslinje uten egne tak |
| 3 | Skal generatoren fylle plassene? | **Nei, bare tomme plasser** |
| 4 | Ny generering over eksisterende? | **Erstatt tomme — behold de korpsreserverte og alle bemannede** |
| 5 | Teller taket ledige eller bemannede? | **Begge, side om side** |
| 6 | Kopieres taket av `kopier_oppsett`? | **Ja** |
| 7 | Hvilken midnattsregel? | **Startdagen**, som resten av vaktlisteflaten |
| 8 | Overlapp-punktet? | **Først** |

Tre av dem er verdt begrunnelsen sin:

**Beslutning 3 holder tilgangsmodellen utenfor en løkke.** En generator som bare lager
tomme plasser er `skriv_full` og ferdig med det; en som fyller må bære
`kan_sette_vaktpost()` — badge *og* reservasjon — inn i hver eneste rad den lager. Og den
holder linja fra `kopier_oppsett`: en liste ingen har sagt ja til ser ferdig ut.

**Beslutning 4 skiller utkast fra løfte.** En tom plass uten reservasjon er generatorens
eget utkast, og å skrive over det koster ingenting. En tom plass reservert til et korps er
noe noen har sagt «denne er deres» om — korpset ser den i «Mitt korps» og planlegger mot
den. Reservasjonen leses av `services.reservert_korps()`, ikke av feltet, fordi plassens
`korps` overstyrer ressursens og tom verdi betyr «som ressursen».

**Beslutning 5, fordi hvert tall alene lyver litt.** «Satt opp» er behovet — det
planleggingen handler om — men ingen betaler for en tom plass. «Bemannet» er nærmest
kostnad, men står på null når lista er halvt satt opp. Avstanden mellom dem er dessuten
selve arbeidslista: 312 mot 244 er 68 timer som mangler folk.

### Regelen som nå skal stå tre steder

**Planlegging fører skiftet på startdagen; fakturering splitter ved midnatt.** Den står i
`CLAUDE.md` (for `_dagnokkel()`) og i planleggernotatet; `docs/FORSLAG_RAPPORTMODUL.md`
§2.2 er det tredje stedet, og er ført opp i TODO. Forskjellen er bevisst og skal ikke
«rettes» — spørsmålene er ulike: «hvem er på vakt den dagen» mot «hvor mange timer skal
betales for det døgnet».

**Endret:** `docs/FORSLAG_PLANLEGGERFANE.md` (§3.2–§3.4 og §4 skrevet om, §5 er nå
avklarte spørsmål, ny §6 med beslutningene, §7 er rekkefølgen), `TODO.md`.

---

## 2026-09-15 — «Avbrutt» og «trenger ny ressurs» var ett spørsmål, og måtte være to  `#oppdrag/statusmaskin`

**Meldt fra staging (André):**

> «Akutt oppdrag opprettes, to enheter varsles. Ene bilen behandler på stedet, andre bil
> slo avbrutt. Da står det trenger ressurs selv om oppdraget er løst — og trykker en bil
> avbryt så må det vises.»

### Feilen

Regelen sto som ett spørsmål: *finnes det andre enheter som ikke er ledige?* Den kan ikke
skille en bil som ble ledig fordi hun **ble ferdig** fra en som ble ledig fordi hun
**avbrøt** — begge deler er `Ledig` på koblingsraden.

Så: Bil A behandlet på stedet og ble ledig. Bil B avbrøt. Ingen andre var «aktive», og
oppdraget ble merket «trenger ny ressurs» — et krav om handling på et ferdig oppdrag.
Reprodusert som test før noe ble rørt.

`trenger_ny_ressurs()` stiller nå **begge** spørsmålene: er noen fortsatt på vei, *og* var
noen framme. `LOSER_OPPDRAGET` er `(Behandlet, Leverer)` — og `Ledig` står bevisst ikke
der, siden det er nettopp den statusen som er tvetydig.

Svaret leses av **statusmeldingene, ikke koblingsradene**: `behandle_paa_sted` sender raden
videre til `Ledig` med samme tidspunkt, så raden bærer ikke lenger spor av at jobben ble
gjort.

**Samme feil sto i `start_oppdrag`** — en bil som rykker videre fra et oppdrag noen andre
alt hadde løst, etterlot det samme feilmerket. Begge kallsteder bruker nå funksjonen.

### Andre halvdel: avbrytelsen må vises

Feilrettingen gjør dette *viktigere*, ikke mindre viktig: før ble et slikt oppdrag stående
på tavla (med feil merke); nå ryddes det bort av seg selv. Uten et merke ville rettingen
gjort avbrytelsen usynlig i stedet for feilmerket.

`avbrutt_av` står nå i svaret — på tavla, i detaljen og i historikken — og tegnes som et
eget merke i enhetsmatrisen. **Dempet, ikke alarmerende:** en avbrytelse er en opplysning
om hva som skjedde, mens «trenger ny ressurs» er et krav om handling nå. Fikk de samme
farge, ville den ene lært operatøren å overse den andre. Begge kan stå samtidig, og da er
de to opplysninger.

Merket er med i **ETag-en**. En bil som avbryter på et oppdrag noen alt har løst endrer
verken status eller tidspunkt, så uten det ville merket druknet i en 304.

*Valgt form: merke i lista, ingen sperre (André). Restrisikoen er at et løst oppdrag ryddes
til historikken med det samme, så operatøren kan gå glipp av merket live — det står i
historikklista, men ikke på tavla.*

### Tester

`oppdrag/tests_avbrutt.py` — 22 tester. **Ni mutasjoner prøvd, alle fanget** etter at to av
mine egne tester ble rettet:

- Bulk-testen hadde bare **én** avbrytelse, så rekkefølgen kunne ikke vises — en bulk som
  sorterte feil vei gikk grønn.
- ETag-testen avbrøt siste bil, og da endret oppdragets *status* seg uansett. Den målte
  altså ikke det den påsto. Isolert nå: en annen bil står fortsatt i Fremme, så status og
  tidspunkt er like før og etter, og merket er det eneste som skiller svarene.

En tredje test hadde dødkode (`... if False else None`) fra en halvferdig formulering og
påsto dermed nesten ingenting. Skrevet om til Andrés scenario helt ut.

### Notat: planleggerfane — `docs/FORSLAG_PLANLEGGERFANE.md`

Andrés andre punkt. Timetallet er avklart som **et tak som varsler**, ikke en inngangsverdi
generatoren regner fra — samme linje som `Belastningsgrenser`.

Notatet peker på at det meste finnes: `_sumTimer`, `mkGruppekurve`, `_vaktensSpenn`,
`belastning_per_person`, og — viktigst — at «å generere et skift» er å opprette `Vaktpost`
uten `mannskap`, som modellen alt er bygget for. Tre feller er navngitt: `bulk_create`
ville tømt auditsporet (`kopier_oppsett` gikk i den fella), den doble regelen må gjelde
også når maskinen setter plasser, og **overlapp-punktet i TODO bør løses først** — et tak
som telles feil er verre enn ikke noe tak.

---

## 2026-09-15 — Vaktlista: dagen ytterst i «Oversikt», og sammenslåtte ressurskort  `#vaktliste/planlegging`

To av de tre ønskene fra 14. sep. er levert. Drift-automatikken står igjen og tas for seg.

### Først: en feil i mitt eget notat

TODO sa at planleggingstabellen «viser radene i serverens rekkefølge, sortert men **uten
dagskille**», og at dagrupperingen derfor måtte bygges der. Det var galt — `mkRessurs()`
har kalt `_blokkerMedDager()` hele tiden, og en test håndhevet det. Feilen betydde at
arbeidet så større ut enn det var; den er rettet i TODO.

### Dagen er én regel, to visninger

`_dagnokkel()` er det ene stedet som avgjør hvilken dag et skift hører til, og svaret er
**startdagen**: «fre. 20:00 – lør. 04:00» står under fredag. Ikke under begge dager, ikke
splittet ved midnatt (André, 15. sep. 2026).

**Merk spenningen mot rapportmodulen, som er bevisst:** der splittes skift ved midnatt
(`FORSLAG_RAPPORTMODUL.md` §2.2), fordi spørsmålet er hvor mange timer som skal betales.
Her er spørsmålet hvem som er til stede. De to skal ikke «rettes» mot hverandre.

Nøkkelen er nå **nullpolstret** (`2026-09-04`), fordi `_grupperPaaDag()` sorterer på den og
`2026-9-15 < 2026-9-4` som tekst. Hjelperen sorterer selv framfor å hvile på at den som
kaller har sortert — samme grunn som `_hviletider()`.

### «Oversikt» snudd: dag ytterst, ressurs under

Før svarte arket på «hvem står på denne bilen, og når» — begrunnelsen i `CLAUDE.md` var at
den som leser står ved bilen. Nå svarer det på **«hvem er på vakt i dag, og hvor»**, som er
det den som møter om morgenen spør om. Begge er gyldige; dette er et valg om hvem arket er
for, og `CLAUDE.md` er skrevet om i samme commit.

En ressurs med skift to dager står nå i begge dagbolkene. Det er prisen for snuingen, og
den er riktig her. Summene per ressurs er dermed **per dag**; totalen i arkhodet er
fortsatt for hele vakta.

`_blokkrader()` er skilt ut av `_blokkerMedDager()`: «Oversikt» har dagen som overskrift
over tabellen, og en dagrad inni ville sagt det samme to ganger på rad.

**Utskrift:** `.vl-dagtittel` har `break-after: avoid` — en dagoverskrift alene nederst på
et ark er en side ingen kan bruke. Hele dagbolken får *ikke* `break-inside: avoid`: en dag
med tolv ressurser er lengre enn et ark, og regelen ville enten blitt ignorert eller
skjøvet en halv tom side foran seg.

### Dagoverskriften vises nå alltid

Også på en endagsvakt (André: «alltid»). Den gamle regelen — bare på flerdagsvakter — hadde
en reell kostnad: planleggeren måtte vite at *fraværet* av en dagrad betydde noe, og
tabellen skiftet form når vakta ble forlenget.

### Sammenslåtte ressurskort

En fane med ti ambulanser var ti regneark under hverandre. Kortene er nå sammenslåtte som
standard — men **bare når gruppa har mer enn én ressurs** (André snevret det 15. sep.): en
vakt med én ambulanse ville ellers kostet et klikk hver gang for å se det eneste som er der.

Tre valg det er verdt å kunne begrunne:

- **Tilstanden ligger i `ressursApen` i `vaktliste-kjerne.js`, ikke i DOM-en.** `mkRessurs()`
  bygges på nytt ved hvert panelbytte — samme grunn til at `gateKnapper()` ikke kan gate den.
- **Map, ikke Set.** Fraværende nøkkel betyr «som standarden». Et Set kunne ikke skilt «ikke
  rørt» fra «utvidet for hånd», og et kort man åpnet ville slått seg sammen igjen neste gang
  noen la til en bil i gruppa.
- **Ikke `localStorage`.** En sidelasting er et nytt blikk på vakta; et kort man slo sammen i
  går skal ikke være skjult når man kommer tilbake for å planlegge.

**Et sammenslått kort er ingen blindvei:** «Rediger», «Roller» og «Opprett vakt» blir
stående i hodet, og sammendraget sier hva som er der — «1 skift · 1 mannskap · 1 ledig ·
16 t». `apneVaktpost()` åpner kortet, ellers lagrer man et skift og ser ingenting skje.

**En latent feil ble synlig:** `ressurser.map(mkRessurs)` sendte indeksen som andre
argument. Det var harmløst så lenge byggeren tok ett argument, og sluttet å være det i det
øyeblikket den tok to — bil nummer null hadde stått lukket og resten åpne.

### Samme dag, etter tilbakemelding fra staging

**André:** *«Ser initielt greit ut på oversikt, men i ressursgruppene så må det være likt
som oversikt — ressurser per dag. Minimer-knappen er fin.»*

Gruppefanen var fortsatt en stabel ressurskort med dagrader inni, mens «Oversikt» hadde
fått dagen som nivå over. Nå er dagen ytterste nivå **begge steder**:

```
Fane «Ambulanse»
  bemanningskurven
  Fredag 3. okt
    Bil A   (kort, minimerbart)
    Bil B
  Lørdag 4. okt
    Bil A
  Uten skift
    Bil C
```

Tre ting fulgte av snuingen:

- **`mkRessurs(r, apen, egne)` tegner de skiftene den får.** Dagbolken sender sin egen dags
  skift, så ett kort dekker én dag — og kortet bruker `_blokkrader`, siden en dagrad inni
  ville gjentatt tittelen rett over. `_blokkerMedDager()` er dermed bare «Mitt korps» igjen;
  den flata har én tabell på tvers av ressursene og altså ingen seksjon å legge dagen i.
- **«Uten skift» er en egen bolk.** En ressurs uten skift hører til ingen dag, og uten
  bolken ville kortet med «Opprett vakt» ikke funnes noe sted — ingen kunne satt opp den
  første vakta på en ny bil. Bolken vises bare når noen faktisk står der.
- **Vippa sitter på ressursen, ikke på ressursen-den-dagen.** En bil som står i to
  dagbolker slås sammen begge steder; to tilstander for én ting ville vært verre enn ingen.

**En mutasjon avslørte at en garanti var en tilfeldighet.** Rekkefølgen i dagbolken skal
være ressursenes, ikke skiftenes — men skiftene ble samlet per ressurs først, så
rekkefølgen fulgte av *hvordan lista ble bygget* og ikke av regelen. Å fjerne regelen
endret ingenting, og testen gikk grønn. `_gruppedagbolker()` leser nå skiftene i serverens
rekkefølge og filtrerer ressurslista, slik at regelen faktisk bærer — og mutasjonen
feiler. Testen måtte også legge skiftet **først** i lista (`unshift`), ellers var det
innsettingsrekkefølgen som ble målt.

Den nye byggeren er lagt i `HTML_BUILDERS`: en markup-bygger XSS-skanneren ikke leser er
nøyaktig det hullet den lista finnes for.

Sju nye tester, fire mutasjoner prøvd — alle fanget etter at kilden ble rettet.

### Og én gang til: velgeren over utskriftslista

**André:** *«Vi beholder «hele vakten» men fjerner ressursene fra det nedtrekksvinduet og
bytter med dag. Så går vakten 1 dag så får du ikke flere valg; går den over flere dager får
du den enkelte dag.»*

Ressursvalget var riktig da arket var gruppert på ressurs. Etter snuingen var «Ambulanse 1»
et snitt på tvers av det arket er bygget rundt — man valgte én akse i en liste sortert på en
annen. `utskriftRessurs` er erstattet av `utskriftDag` (en `_dagnokkel()`-streng, eller
`null` for hele vakta).

- **En endagsvakt får ingen velger.** Ett valg i et nedtrekk er en kontroll som ikke gjør
  noe — «hele vakten» og «den ene dagen» er samme ark. Utskriftsknappen står igjen alene.
- **Filtreringen skjer før tallene regnes.** Skriver man ut lørdag, sier arkhodet lørdagens
  timer og ikke hele vaktas. Ligger filteret i dagbolkene i stedet, blir hodet stående og
  beskrive noe annet enn arket under det.
- **Et valg som ikke finnes lenger gir et tomt ark**, ikke en feil — lista kan ha blitt
  lastet på nytt siden man valgte.

**To av mine egne tester målte feil etter endringen**, og det er verdt å merke seg hvorfor:
dagnavnene står nå *også* i velgeren, som kommer først i markupen. Et søk på «Lørdag 5. sep»
traff da verktøylinja, og sliced hele arket i stedet for lørdagsbolken — testen var fortsatt
grønn, men målte noe annet enn den påsto. Assertionene slicer nå på `<h2 class="vl-dagtittel">`.

Fire mutasjoner prøvd, alle fanget.

### Tester

Elleve nye i to klasser (`DagenErYtterstTests`, `SammenslaatteRessurserTests`), og den
gamle dagoverskrift-bolken er skrevet om mot den nye strukturen. **Elleve mutasjoner
prøvd, alle fanget.**

En av dem avslørte en svak assertion hos meg: `ut.count('vl-dagbolk')` teller også
`vl-dagbolk-x`, så en omdøpt klasse slapp gjennom. Assertionene teller nå `class="..."`
eksakt.

To ting ble rettet underveis fordi eksisterende gjerder fanget dem: escaping-skanneren
avviste sammendraget bygget som template-literal (skrevet om med `+`, som `_blokklinje()`
gjør), og et søk-og-erstatt i testfilene traff en JS-streng i stedet for en harness-liste.

---

## 2026-09-14 — To notater: DPIA-vurderingen og vaktlisteutbedringene (ingen kode)  `#core/dokumentasjon`

To samtaler skrevet ned. Ingen kodeendring — begge notatene finnes for at beslutningene
skal kunne tas med åpne øyne, og TODO peker til dem.

### `docs/NOTAT_DPIA_OG_FRITEKST.md`

Utløst av Andrés spørsmål om AMK-adresse kan legges i `Oppdrag.fritekst`, og av at
fritekst aldri slettes fra historikken.

**Ett premiss måtte rettes:** «vi slipper DPIA fordi vi har personverndokumentasjon» er
ikke det A.12 sier, og ville heller ikke holdt — da kunne enhver behandling dokumentert seg
ut av art. 35. A.12 bygger på tre andre ben: ingen direkte identifikatorer, ikke stor skala,
ingen profilering. **Skalaen holder, og en adresse endrer den ikke.** Men A.12 har selv
skrevet utløseren — «særlig dersom nye moduler tar inn direkte identifikatorer» — så
vurderingen er allerede forpliktet til å tas opp igjen i akkurat dette tilfellet.

**Og luken er større enn DPIA-spørsmålet:** A.12 er en *sikkerhets*risikovurdering. Den
måler sannsynlighet for og konsekvens av brudd — risiko sett fra systemets side. Art.
35(7)(c) spør noe annet: hva skjer med pasienten hvis det går galt? Det spørsmålet stilles
ikke noe sted i dokumentet. Samme slags feil som `rullTilFeil()` rettet samme dag:
vurderingen er gjort, bare ikke fra det ståstedet den skulle.

Kartlagt i samme slengen — **hvor fritekst faktisk lever**: skjult for bilen straks
oppdraget er `Ledig`, hele oppdraget borte etter 30 min, aldri arkivert, aldri verdilogget
— og **stående for alltid i KOs historikk**, pluss 730/90 dager i backupfilene. Beskyttelsen
er bygget helt og holdent mot bilen. En slettefrist er derfor reell beskyttelse mot at noen
leser historikken tre måneder senere, men den er **ikke** en sletterett; det skal stå
skrevet, ikke oppdages senere.

**Den viktigste enkeltadvarselen:** adressen må ikke legges i `Lokasjon`. `Lokasjon.navn`
fryses som `ArkivertOppdrag.lokasjon_navn` og inngår i **SHA-signaturen** — en adresse lagt
der er låst i 24 måneder ved konstruksjon og kan ikke fjernes uten at arkivet melder
tukling. Det tilsynelatende ryddige nedtrekket er den farligste plasseringen.

To ting er merket for **primærkildesjekk** framfor å gjettes på: Datatilsynets liste over
behandlinger som alltid krever DPIA, og WP248-kriteriene i gjeldende form.

### `docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md`

De tre ønskene fra 14. sep. sto punktvis i TODO, hver for seg. Notatet finnes fordi de
henger sammen på en måte som ikke synes da:

**To av tre trenger dagruppering, og de ber om den på hvert sitt sted** — «Oversikt» vil ha
dagen ytterst, gruppefanene vil ha dagoverskrifter i planleggingstabellen. I dag finnes
dagen bare i `_blokkerMedDager()`. Bygges de hver for seg, får portalen to dagrupperinger
som kan komme i utakt — og det er en stillegående utakt: to lister som grupperer dagen ulikt
ser begge riktige ut hver for seg. Anbefalingen er én funksjon, to kallsteder, og at
midnattsvalget dermed tas én gang.

Midnatt er også allerede i spill: rapportmodulen har avklart at **timer** splittes ved
midnatt, mens oversikten spør om *tilstedeværelse*, ikke timer. De to kan lande ulikt — men
da skal det stå hvorfor, ellers leses forskjellen som en feil.

Den tredje, «fjern Sett i drift», deler ingen kode med de to andre og kan tas parallelt.
Men knappen gjør **fire** ting, og to av dem mister hjemmet sitt hvis drift bare utledes:
`satt_i_drift_av` mister mening, og e-postutløseren forsvinner. Det peker mot «automatisk
med unntak» framfor rent utledet — den som møter 30 minutter før vaktstart skal fortsatt
kunne stemple.

---

## 2026-09-14 — 400 ved bemanning av ledig plass: nedtrekket tilbød et umulig valg  `#vaktliste/planlegging`

**Meldt fra staging (André):**

```
PUT https://testportal.sanitet.net/vaktliste/api/vaktposter/88/  →  400 (Bad Request)
endreVaktpost @ vaktliste-offline.js
```

…og etterpå: *«Jeg fikk feilen i konsoll på f12, så ingenting i nettleseren ellers.»*

Det er **to feil i én melding**, og de er verdt å skille:

### 1. Serveren gjorde riktig; grensesnittet spurte om noe umulig

`Vaktpost` har `UniqueConstraint(ressurs, mannskap, fra_tid)`. Nedtrekket for en ledig
plass ble bygget av `_fyllValgFor()`, som listet **hele** mannskapsregisteret uten å se på
hvem som alt sto på den ressursen til den starttiden. Valgte man en av dem, avviste
viewet med «Personen står allerede på denne ressursen fra dette tidspunktet» — riktig
svar på et spørsmål som aldri skulle vært stilt.

Det bryter portalens egen regel: **«en knapp som fører til en vegg er verre enn ingen
knapp.»** Regelen sto skrevet om `window.MODUL_TILGANG` og gjelder like fullt her.

`opptattPaaPlassen(vp, poster)` er ny og filtrerer nedtrekket. Den ligger som **egen
funksjon**, ikke som en `filter` inne i byggeren, av samme grunn som `klikkSkalKjore()`:
en regel som ikke lar seg kalle, lar seg ikke prøve. Fire ledd, og hvert av dem er en
egen feil å gjøre — raden selv teller ikke, ledige plasser (`mannskap_id === null`)
sperrer ingen, annen ressurs er fritt fram, annen starttid er en annen rad. Alle fire er
mutasjonsprøvd.

Kilden er `alle_vaktposter` — alt serveren sendte — ikke `vaktposter`, som er det
korpsfilteret slapp gjennom. Skranken er en databasekjensgjerning uavhengig av hvem som
ser raden. Det lekker ingenting: filteret kan bare *fjerne* valg, aldri vise et navn.
**Restrisikoen står igjen** — serveren filtrerer i tillegg sitt eget svar, så en
korps-bruker kan fortsatt treffe veggen. Da vises meldingen, og den rulles nå fram.

**Merk hva den *ikke* gjør:** den sperrer ikke overlapp på tvers av ressurser. Å stå på
KO og på bilen samtidig er bevisst tillatt (`test_overlapp_paa_tvers_av_ressurser_stoppes_ikke`),
og er ført opp for seg i TODO.

### 2. Feilmeldingen ble skrevet utenfor skjermen

`endreVaktpost()` kalte `visPanelfeil()` som den skulle, og `#vl-feil` sto i malen. Men
banneret ligger rett over `#vl-panel`, altså **øverst på sida**, mens nedtrekket som ble
avvist kan stå tretti rader ned i et regneark som ruller. Meldingen ble skrevet — bare
der ingen så den.

En feilmelding ingen ser er verre enn ingen feilmelding: brukeren tror lagringen gikk
igjennom, mens raden ruller tilbake til lagret verdi uten forklaring. `rullTilFeil()`
bringer banneret fram med `block: 'nearest'` — ruller minst mulig, så et banner som alt
står i bildet ikke får sida til å hoppe. Uten `scrollIntoView` (eldre nettleser) vises
meldingen som før; rullingen er en forbedring, ikke en forutsetning.

*Dette punktet ble ikke funnet av en test — det ble funnet fordi André sa hva han
**ikke** så. Verdt å merke seg: suiten kan bekrefte at en melding skrives, men ikke at
noen leser den.*

### Hva som med vilje **ikke** ble rørt

`apneRedigerVaktpost()` fyller sitt nedtrekk fra hele registeret på samme måte, og kan
derfor treffe samme skranke. Det ble stående, av to grunner:

- **Vinduet kan endre `fra_tid` i samme lagring.** Et filter regnet ut da vinduet ble
  åpnet gjelder den *gamle* starttiden; flytter man skiftet til et tidspunkt der plassen
  er ledig, ville en gyldig person vært borte fra lista. Å skjule et lovlig valg er en
  vanskeligere feil å oppdage enn en 400 med melding.
- **Veggen er skiltet der.** `lagreVaktpost()` viser avslaget med `_visFeil(...)` inne i
  vinduet, altså der brukeren ser. Det var nettopp dét som manglet i raden.

### Nye tester

`vaktliste/tests_dobbeltbooking.py` — ti tester i to klasser. Seks mot filtreringsregelen
(fire mutasjoner fanget), fire mot banneret (tre mutasjoner fanget: fjernet kall,
`'nearest'` → `'start'`, fjernet `typeof`-vakt).

De seks eksisterende harness-listene som når `_fyllValgFor` fikk `opptattPaaPlassen` lagt
til. **Det er prisen for at harnessene navngir funksjoner eksplisitt** — en ny hjelper
brukt av en testet funksjon gir `ReferenceError` i tolv tester før noen har skrevet en
linje ny test. Prisen er bevisst: alternativet er å laste hele fila, som har
toppnivå-avhengigheter til DOM-en.

---

## 2026-09-14 — Minimerbare ressurser ført i TODO (ingen kode)  `#core/dokumentasjon`

**André:** minimerbare lag/ambulanser i gruppefanene, dagruppering som i Oversikt, og alle
minimert som standard.

Problemet er konkret: en fane med ti ambulanser er i dag ti regneark under hverandre.
Gruppefanen har allerede bemanningskurven øverst, og den *er* oversikten over gruppa —
kortene under er detaljen. Med alt sammenslått blir fanen «kurve + hvilke biler finnes»,
som er den riktige første visningen.

**Dagrupperingen avdekket en reell forskjell mellom de to flatene.** Oversikt har
`_blokkerMedDager()` og setter dagoverskrifter; planleggingstabellen har ingen — den
viser radene i serverens rekkefølge (`Vaktpost.Meta.ordering = ['fra_tid',
'mannskap__navn']`), altså sortert men uten dagskille. Samme funksjon bør kunne brukes
begge steder.

Tre ting ført opp som må avklares før noen bygger:

- **Hvor lever sammenslått/utvidet?** `tegnFaner()` og `mkRessurs()` bygger markupen på
  nytt ved hvert panelbytte — samme grunn til at `gateKnapper()` ikke kan gate dem.
  Tilstanden må ligge utenfor markupen; `erDempet` i `oppdrag-enhet.js` er presedensen.
- **Alltid minimert, eller bare når det er mer enn én?** En vakt med én ambulanse gir et
  klikk hver gang for å se det eneste som er der. `_blokkerMedDager()` har presedensen for
  det motsatte valget — dagoverskrifter vises bare når vakta har mer enn én dag. Ført som
  spørsmål, ikke som innvending: Andrés ordlyd er «alle minimert som standard».
- **Åpnes kortet automatisk når man må inn i det?** Ellers leder «Rediger ressurs» til noe
  man ikke ser.

---

## 2026-09-14 — To vaktlisteønsker ført i TODO (ingen kode)  `#core/dokumentasjon`

**«Sett i drift» skal bort — drift skal følge vakta** (André). Problemet den løser er
ekte: glemmer noen å trykke, kan ingen stemple møtt ved vaktstart, altså nøyaktig når det
betyr noe og når alle har mest å gjøre.

Men knappen gjør **fire ting, ikke én** (`drift_view`): setter status, setter
`satt_i_drift_at`, setter `satt_i_drift_av`, og **sender vaktlista på e-post** når admin
har slått det på. To av dem mister sitt hjem hvis knappen forsvinner — `satt_i_drift_av`
mister mening, og e-postutløseren må flyttes til en klokke. Begge er ført opp.

Designspørsmålet er om drift skal **utledes** eller **klokkesettes**. Utledet er mest i
portalens ånd — presedensen er `Vaktpost.er_tilstede`, «utledes, aldri lagres; to kilder
til samme sannhet går i utakt første gang noe feiler halvveis». Og kantene som må avklares:
den som møter tidlig, og den som glemte å stemple av.

**«Oversikt» skal siles etter dag først, så ressurs** (André). Dagen finnes allerede som
begrep — `_blokkerMedDager()` setter en dagoverskrift *inne i* hver ressurs — så dette er
en omstrukturering, ikke et nytt begrep.

Lesemodellen er det som endrer seg. I dag svarer lista på «hvem står på denne bilen, og
når»; begrunnelsen i `CLAUDE.md` var «den som leser den står ved bilen». Snudd svarer den
på **«hvem er på vakt i dag, og hvor»** — spørsmålet den som møter om morgenen faktisk
stiller.

Ett spørsmål må avgjøres: **hvor havner et skift som krysser midnatt?** I dag files det
under startdagen (`_dagnokkel(fra_tid)`). Med dag ytterst blir det et reelt valg — bare
startdagen betyr at den som ser på lørdag morgen ikke ser Kari, selv om hun er på vakt.
Merk spenningen mot rapportmodulen: for **timer** er det avklart at skift splittes ved
midnatt, men for **oversikten** er spørsmålet hvem som er til stede, ikke hvor mange timer
som skal faktureres. De to kan lande ulikt — men da bevisst.

---

## 2026-09-14 — Rapportnotatet skrevet ferdig (ingen kode)  `#core/dokumentasjon`

`docs/FORSLAG_RAPPORTMODUL.md` er revidert etter diskusjonen med André. Fortsatt et
forslag — ingen kode skrevet.

**Jeg tok feil i første utkast, og det står nå i notatet.** Jeg frarådet LLM-tolkning med
eksempelet «én rød pasient, hjertestans, kl. 14:32». André ba meg se på hva
statistikkmodulen faktisk sender. **Eksempelet finnes ikke i dataene** — payloaden er
aggregater, uten radnivå, uten ID-er, uten klokkeslett per hendelse, og `fritekst`,
`notat` og `merknad` går ingen steder.

Det endrer jussen, ikke bare risikovurderingen: GDPR gjelder ikke anonyme data
(fortalepunkt 26), så A.8 er ikke i spill. Jeg hoppet over det spørsmålet og gikk rett til
«ny databehandler». Feil rekkefølge, og skrevet ned så neste leser slipper å gjøre samme
feil.

**Andrés forslag om å ekskludere risikoproblemstillinger framfor å undertrykke små celler
er bedre**, og notatet forklarer hvorfor de ikke løser samme problem: undertrykking retter
seg mot *identifiserbarhet*, ekskludering mot *skade*. Verdimengden i `patients/choices.py`
avgjør saken — «Mistanke overgrep» og «Psykiatri» står side om side med «Skade ankel/fot».
Én av hver har samme identifiserbarhet og helt ulik konsekvens.

Ekskludering er dessuten bedre for små vakter, som er normaltilfellet: en vakt med tolv
pasienter ville fått nesten alle celler undertrykt under en `n < 5`-regel — formelt trygt
og praktisk verdiløst.

**Den avklarende innsikten: filteret gjelder bare maskinen.** I portalen trengs verken
undertrykking eller ekskludering — den som ser rapporten har allerede `les` på
kildemodulen og kan åpne pasientlista. Filteret hører hjemme på payloaden som *forlater*
portalen. Det løser også regneproblemet: menneskerapporten er komplett, maskinpayloaden er
redusert, og ingen leser maskinpayloaden som en rapport.

**Filteret må feile lukket**, og det er motsatt av `NOKLER_UTEN_AUDIT` i `core/signals.py`
— av nøyaktig samme resonnement. Merkes kategorier som skal *ekskluderes*, slipper en
glemt ny kategori ut. Merkes de som er *godkjent for utsending*, ekskluderes en glemt ny
til noen aktivt godkjenner den. En auditliste skal feile mot mer logging; et
personvernfilter mot mindre deling.

**Notatet er skrevet med to varianter**, etter Andrés ønske: variant A uten LLM er et
komplett produkt alene, variant B legger tolkningen på toppen. Stegene 1–4 i anbefalt
rekkefølge krever ingen personvernbeslutning i det hele tatt.

**Midnatt er avklart:** rapporten skal vise både per dag og totalt, så skift som krysser
splittes — 4 timer på fredag, 4 på lørdag. Bemanningskurven gjør det allerede
(`vl-dogn`), så alternativet ville gitt to flater i samme portal med ulike tall.

**Leverandør: Scaleway Generative APIs anbefales**, først og fremst fordi Scaleway SAS
allerede står i A.2 med signert DPA. Zero retention som standard, franske datasentre, ingen
amerikansk morselskap og dermed ingen CLOUD Act-eksponering. Mistral er nærmeste
alternativ, men zero retention ligger bak Scale-planen. **Merket i notatet som ikke
verifisert mot primærkilden** — Scaleways domene var blokkert av egress-proxyen.

---

## 2026-09-14 — Vaktlista: overlappende skift ført i TODO (ingen kode)  `#core/dokumentasjon`

Funnet mens rapportmodulen ble diskutert, men punktene hører hjemme i vaktlista og er
uavhengige av om rapporten noen gang bygges.

**Docstringen lover en telling som ikke finnes.** `vaktliste/services._hviletider()` sier
«Overlappet i seg selv fanges av `overlapp`-tellingen». Det er ingen `overlapp`-nøkkel i
belastningsraden. Det som faktisk skjer er at `korteste_hvile` blir `0.0` og raden flagges
som **kort hvile** — altså vises et overlapp som et hvileproblem, og planleggeren får ikke
vite hva det egentlig er.

**Og et overlapp blåser opp timesummen.** Målt: skift 12:00–20:00 (8 t) og 16:00–22:00
(6 t) på samme person gir `timer = 14.0`, mens personen var til stede i 10 timer. I dag er
det harmløst fordi ingen betaler etter tallet — det er et planleggingsvarsel. Som
fakturagrunnlag er det fire timer noen betaler for uten at noen var der.

**Timer har ingen dagdimensjon.** `_timer()` er ren varighet; fredag 20:00 → lørdag 04:00
gir 8,0 timer uten at koden har noe begrep om hvilken dag de tilhører. Spørsmålet var
ubesvart i koden fordi ingenting hadde stilt det. Bemanningskurven har presedensen — den
bøtter per time og markerer midnatt (`vl-dogn`) — så Andrés regel «fredag 23:59 er fredag,
lørdag 00:00 er lørdag» betyr at et skift **splittes ved midnatt**.

**En sperre hører ikke hjemme i databasen.**
`test_overlapp_paa_tvers_av_ressurser_stoppes_ikke` dokumenterer at dagens oppførsel er
bevisst: «noen ganger står man på to lister». Å sperre det i basen krever
`ExclusionConstraint`, som **ikke finnes i SQLite** — da ville suiten vært grønn lokalt
mens prod oppførte seg annerledes, nøyaktig fella fra 30. aug. 2026. Riktig sted å nekte er
ved **frysing** av en liste som skal bli fakturagrunnlag, ikke ved planlegging der
overlappet bare er informasjon.

Ingen kode skrevet. `docs/FORSLAG_RAPPORTMODUL.md` er ikke oppdatert ennå — diskusjonen
pågår.

---

## 2026-09-14 — Forslag: rapportmodul (ingen kode)  `#core/dokumentasjon`

`docs/FORSLAG_RAPPORTMODUL.md`, skrevet på Andrés spørsmål om en `/rapport/`-modul som
henter fra vaktlista og statistikken. **Ingen kode er skrevet** — dette er grunnlag for
en beslutning.

**Del 1, timeregnskap med kroner per korps: anbefales.** Mye finnes allerede —
`belastning_per_person()` regner timene, og `Vaktpost.probono` bærer skillet «går, men
telles ikke i timene», med kommentaren «summen er det organisasjonen betaler for».
Betalingstanken var altså inne i modellen før noen planla den.

Den viktigste innsikten i notatet: **tall som brukes til penger må fryses.** I dag er
vaktlistedata operative og kan rettes fritt. Som fakturagrunnlag må de slutte å bevege
seg — ellers retter noen et skift i mars, og fjorårets faktura stemmer ikke lenger med
det portalen viser. Portalen har mønsteret to ganger (`core.arkiv`), så dette er ikke nytt
arbeid, men det gjør del 1 større enn «en tabell med timer».

**Del 2, LLM-tolkning: frarådes i første omgang**, og begrunnelsen er ikke teknisk:

- En språkmodell er en **ny databehandler**. `PERSONVERN_DOKUMENTASJON.md` A.8 sier i dag
  «ingen overføring av personopplysninger til land utenfor EU/EØS» — verifisert mot
  dokumentet, ikke husket
- **«Uten navn» er ikke anonymt.** Én rød pasient med hjertestans kl. 14:32 på et navngitt
  arrangement er sannsynligvis nøyaktig én person. Det som beskytter er små tall, ikke
  fravær av navn
- **Tolkningen er den delen leseren ikke kan etterprøve.** Rapporten leses av noen som
  ikke var der — det er poenget med den — og da kan de heller ikke se at tolkningen er
  feil. Tallene er signert; en setning er det ikke

Forslaget er å skille rapporten fra tolkningen: portalen lager tallene, og den som vil ha
prosa tar det utenfor portalen under eget ansvar. Da slipper portalen å stå i
behandlerkjeden for noe den ikke trenger å stå i.

Fem åpne spørsmål står i §5. Del 1 kan begynne uten at del 2 er avgjort, og det er en
fordel: timeregnskapet har verdi alene og tvinger ikke fram en personvernbeslutning før
dere er klare til å ta den.

Hver påstand i notatet er verifisert mot koden — funksjonsnavn, felter, filstier og
A.8-formuleringen.

---

## 2026-09-14 — Tallgjerdet: dokumentene kan ikke lenger lyve om antall  `#core/dokumentasjon`

Det ene av tre åpne punkter som var verdt å lukke. De to andre —
`accounts` → `oppdrag.Enhet` og `style-src 'unsafe-inline'` — ble gjennomgått og
**bevisst latt stå**; begrunnelsene står i `docs/TEKNISK_DOKUMENTASJON.md` kap. 15.

**`core/tallfasit.py` (ny)** regner ut antall ruter (totalt og per prefiks), backup-
handlere, moduler, statistikk-kilder og JS-filer fra koden.
`python manage.py tallfasit` skriver dem ut — den som skal oppdatere et dokument
trenger å vite hva det riktige tallet er, og da må utregningen finnes utenfor testen.

**`TallpaastanderTests` krever at dokumentene stemmer.** Tretten påstander er registrert
i README, CLAUDE.md, deploy-guiden og teknisk dokumentasjon.

Dette dekker den halvdelen av dokumentråte som oppstår **uten at noen gjør noe galt**:
«178 tester totalt» var sant da det ble skrevet, og «16 endepunkter» var sant da det var
alt som fantes. Legger noen til en rute, feiler testen til dokumentet følger etter.

**Påstandene registreres eksplisitt, ikke gjettes ut av prosaen.** Et mønster som lette
etter «\<tall\> endepunkter» hvor som helst ville truffet setninger som ikke er påstander
om totalen — og en test med falske funn blir slått av, ikke fulgt. Regexen må dessuten
treffe nøyaktig ett sted; flere treff er enten duplisert påstand eller et for løst
mønster, og testen skiller de to feilene i meldingen.

**Gjerdet fant en feil før det var ferdig skrevet, og den var min:** kapittel 5 oppga 8
ruter under «`/varsler/`, `/api/`, m.fl.» Det riktige er 13 — jeg hadde glemt `/healthz/`,
`robots.txt`, manifestet, «min profil» og videresendingen fra `/api/`. Nøyaktig den sorten
feil tallgjerdet finnes for.

Tre mutasjoner prøvd, alle fanget:

| Mutasjon | Meldingen |
|---|---|
| Dokumentet påstår feil tall | «totalt antall ruter står som '99', men koden har 123» |
| Koden får en ny rute, dokumentet står stille | «står som '123', men koden har 124» |
| Fasiten går i stykker | Sperrehaken sier «fant nesten ingen ruter» — i stedet for at alle rader feiler og leses som «dokumentene er gale» |

Den midterste er poenget: **drift fanges av seg selv**, uten at noen må huske å telle.

`docs/TEKNISK_DOKUMENTASJON.md` kap. 15.8 er skrevet om og viser nå åpent hvor lite
gjerdet ville fanget av dokumentrunden: to av fem funn. De tre andre — nedlastings-
oppskriften, `TypeError`-signaturen og feil regex — er påstander om *innhold*, og de
løses av at noen leser diffen.

---

## 2026-09-14 — Dokumentrunden del 3: resten av teknisk dokumentasjon  `#core/dokumentasjon`

André: «Hvis teknisk dokumentasjon ikke er ferdig gjennomgått så må vi gjøre det.» Riktig
innvending — **halvveis verifisert dokumentasjon er verre enn tydelig uverifisert**, fordi
merket forsvinner ved neste redigering og det uetterprøvde da ser ut som resten. Kapittel
5, 8A–8E og 13–16 er nå gjennomgått, og alle markørene er borte.

**Kapittel 5 dokumenterte 16 av 123 endepunkter**, med tilgangskrav oppgitt som `admin`,
`lead`, `read_write`. Strukturen er endret med vilje: en håndskrevet liste over 123
endepunkter råtner fra dagen den skrives. Nå står **konvensjonene og tilgangsmønsteret**
fullstendig, med et kart over hvor endepunktene bor og en kodesnutt som skriver ut den
autoritative lista — **verifisert ved å kjøre den ordrett**.

Det viktigste som manglet: **dekoratøren gater lesing, viewet gater skriving.** Det er
grunnen til at et skriveendepunkt kan se ut til å kreve bare `les`, og uten den
forklaringen leser tabellen som et hull i sikkerheten.

**Kapittel 8B dokumenterte en signatur som ikke finnes.**
`@cached_stats_response(ttl=15, key_prefix=...)` ville gitt `TypeError` — parameteren
heter `cache_key` og kommer først. Verre: påstanden om at nøkkelen bygges av «aktivt år og
rollen som ber om dataene» var feil i begge retninger. Den lovet en isolasjon per rolle
som ikke finnes, og skjulte kravet som faktisk gjelder — at **kallstedet** må legge slug
og vakt-ID i nøkkelen selv.

**`_scrub_secrets` var gjengitt feil.** Den dokumenterte regexen krevde `bruker:passord@`;
den ekte krever ikke kolon, og treffer derfor også `redis://token@host`. Fem kodelinjer
er nå verifisert ordrett mot kilden.

**8A hadde en hengende tabellrest** fra en sletting som ble gjort i overskriften og ikke i
kroppen: avsnittet sa «fjernet 13. sep.» og beskrev deretter flagget som om det fantes,
med en `is_feature_enabled()` som ikke er skrevet. Det er den vanligste formen for
dokumentråte.

**Kapittel 13 viste til `PUT /api/backup-config/` og `POST /api/reset-active-year/`** —
ingen av dem finnes, og den siste beskrev en nullstilling av «aktivt år» som
vakt-modellen erstattet.

**Kapittel 14 oppga «178 tester».** Nå er det 2 751. Kapittelet er skrevet om til
prinsipper som holder — hvorfor `myproject` skal med, hvorfor migrasjonsprøver mot ekte
PostgreSQL ikke kan erstattes av suiten, skillet mellom å lese kildekode og å påstå at en
kodelinje står der, vinduskanten i rate-limit — pluss **tretten testklasser som håndhever
regler om kodebasen**. Alle tretten er verifisert å eksistere.

**Kapittel 15 fikk tre nye kjente begrensninger**, alle ærlige: `style-src` tillater
fortsatt `unsafe-inline`, `accounts` → `oppdrag.Enhet` står igjen i
`KJENTE_UNNTAK_RAMMEVERK`, og gjerdet mot dokumentråte har en luke som ikke kan lukkes
uten å gjøre historiske avsnitt umulige.

**Gjerdet er utvidet til å lese stier uten backticks.** `patients/middleware._MetricsStore`
sto i en tabellcelle og slapp forbi da modulen flyttet — stier uten backticks er like døde
som stier med.

**Og gjerdet tok meg selv, to ganger.** Først på `manage.py show_urls`, som jeg skrev inn
med et forbehold om django-extensions — men et forbehold i teksten er ikke godt nok når
kommandoen ikke virker. Så avdekket det at **mine egne «ikke gjennomgått»-markører tiet
regelen for hele kapitler**, fordi en seksjonsmarkør gjelder til neste overskrift. Det er
et argument mot slike markører i seg selv, og de er nå borte.

*To av mine egne mutasjonsforsøk traff ingenting fordi jeg muterte tekst som ikke sto der
— feilen var i mutasjonen, ikke i testen. Det står her fordi «mutasjonen ble ikke fanget»
og «mutasjonen ble aldri utført» ser helt like ut i en logg.*

---

## 2026-09-14 — Dokumentrunden del 2, og den uforklarte feilen fikk et navn  `#core/dokumentasjon`

Gjeldspunkt 3 er ferdig: alle seks dokumenter gjennomgått mot koden, pluss et gjerde
som gjør mekanisk dokumentråte til en rød test.

**Personvernprotokollen dokumenterte en annen tilgangsmekanisme enn den som finnes.**
A.10 listet `read_only`, `read_write`, `lead_view`, `lead` og `admin` med hver sine
rettigheter i en matrise. **De fire første ble slettet i deploy 2.** Det er alvorligere
her enn i README: dette er dokumentet man legger fram ved en DPA-gjennomgang. Samme feil
sto i A.6 (`role` som «tilgangsnivå») og i sjekklista C.1, der man ble bedt om å
verifisere roller som ikke finnes. Den ekte modellen er dessuten *strengere* — en konto
uten `ModulTilgang`-rader ser ingenting — så fortellingen var også unødig svak.

**A.2: bucketen hos Scaleway inneholder nå autentiseringsdata.** Da hel databasebackup
ble lagt til, endret innholdet seg materielt: passord-hasher, TOTP-hemmeligheter og
audit-logg. Protokollen sa fortsatt «modulenes data». Ført inn med de tre tiltakene
risikoen håndteres med — kryptering med en nøkkel Scaleway ikke har, 90 dagers frist mot
modulfilenes 730, og en IAM-nøkkel uten sletterett. Den korte fristen var en riktig
avgjørelse som ikke var dokumentert som en avgjørelse.

Endringsloggen hoppet fra 29. august til i dag, og versjonshodet sto på «1.8» mens siste
oppføring var v1.10. **Hullet er beskrevet framfor etterdatert** — en endringslogg som
fylles inn i ettertid er verdiløs nettopp som endringslogg.

**Teknisk dokumentasjon:** tittelen sa «Pasientregistreringssystemet» og kapittel 3
beskrev tre apper. Portalen har seks. Kapittel 3, 4, 6, 7, 8, 9 og 10 er skrevet om —
registrene, den ekte nivåstigen, CSP slik den er i dag, backup i to lag, og JS-en etter
delingen. **Ti døde filstier** rettet. Kapitler som *ikke* er gjennomgått er merket der
de står, i stedet for å se like ferske ut som resten.

**`core/tests_dokumentråte.py` (ny).** Dokumentasjon har ingen testsuite, og det er
dagens feilmodus. Testen krever at hver filsti, hver `manage.py`-kommando og hvert
slettet symbol dokumentene navngir, stemmer med koden. Den fant umiddelbart tre ting jeg
hadde oversett — blant dem en rad i personvernprotokollens A.13 som fortsatt påsto at
«backup ekskluderer sensitive data» fordi `BACKUP_APPS` var satt til `['patients']`.

Fire mutasjoner prøvd, tre fanget. **Den fjerde slapp gjennom og står skrevet i testen:**
skriver man `> **Historisk**` over en påstand, tier regelen til neste kapittel. Det er en
bevisst luke som er lett å misbruke, og den løses av at noen leser diffen — ikke av at
testen blir strengere.

**Og den uforklarte enkeltfeilen fikk endelig et navn.** Den het
`core.tests_ratelimit.RateLimitEndepunktTests.test_opprett_pasient_strupes`, og fanget
seg selv i det øyeblikket en full PostgreSQL-kjøring ble tatt vare på med `tee` i stedet
for grep-et bort — nøyaktig det jeg skrev i evalueringen at jeg skulle gjøre annerledes.

Årsaken er vinduskanten i `django_ratelimit`, altså samme rotårsak jeg rettet tidligere
samme dag: 65 forsøk mot `60/m` deles i to bøtter der ingen når 60. **Den var brutt tre
steder, ikke ett** — også `test_full_stats_strupes` (35 mot 30) og
`test_auditlog_eksport_strupes` (15 mot 10). Regelen er derfor nå funksjonen
`nok_til_a_bryte(grense)` med begrunnelsen i docstringen, ikke tre tall man skriver av.
Bekreftet med 30 kjøringer på PostgreSQL uten én feil.

---

## 2026-09-14 — Dokumentrunden, del 1: deploy-guide, runbook og README  `#core/dokumentasjon`

Gjeldspunkt 3. Tre av seks dokumenter; de to store og gjerdet står igjen.

**`docs/DEPLOY_GUIDE.md` var verre enn utdatert — den motsa en sikkerhetsbeslutning.**
Kapittel 5 sa «en backup skal kun inneholde pasientdata – aldri brukere, passord eller
audit-logg», og ga så en oppskrift på å **laste ned backupfila** for å kontrollere det.
Begge deler er feil: den hele databasebackupen inneholder brukere, MFA-hemmeligheter og
logg med vilje, og backupfiler skal ikke lastes ned i det hele tatt. Hadde noen fulgt
oppskriften, hadde de lagt en helseopplysningsdump i nedlastingsmappa mens de trodde de
gjorde en sikkerhetskontroll. Erstattet med `verifiser_backup`.

Den beskrev også `BACKUP_APPS` og `BackupConfig.interval_minutes` — begreper som ikke
finnes — og manglet AHASend, offsite, cron-tjenestene, hash-låste avhengigheter og
staging-flyten. Nytt **kapittel 10, rollback**, sto ikke på lista: en redeploy i Railway
ruller ikke tilbake databasen, så release-loggen må leses først.

**`docs/RUNBOOK_VAKT.md`: to av tre punkter på lista var alt gjort.** §8b dekket allerede
hel backup, tom base og den bindende rekkefølgen, og §14 med `scripts/sikkerhetssjekk.py`
fantes. Lista var utdatert, ikke dokumentet. Det som manglet var **§8c, «Deployen knakk —
rull tilbake»**, som ingen hadde ført opp. §1 har fått et punkt om ingen deploy fra
sjekklista til vakta er over, med byggnummeret notert.

**`README.md` var den mest villedende av dem alle.** Den beskrev rollemodellen
`read_only`/`read_write`/`lead_view`/`lead` og fem `kan_redigere_*`-flagg på
`CustomUser` — **ingen av delene finnes**, de ble slettet i deploy 2 og 3. En leser bygget
altså feil mental modell av hele tilgangsstyringen. Den påsto også «178 tester totalt»
(nå 2 744) og at backup «inneholder kun pasientdata (`BACKUP_APPS=['patients']`)».

Skrevet om som **inngangsdør, ikke kopi**: en tabell over hvor ting står, korrekt
arkitektur med de sju registrene, den ekte tilgangsmodellen, og pekere til deploy-guiden i
stedet for en duplisert Railway-oppskrift som ville drevet fra hverandre. Testtallet er
tatt ut — et tall der råtner fra dagen det skrives.

Hver påstand i deploy-guiden og README er maskinelt verifisert mot koden: kommandoer,
filstier, miljøvariabler, interne lenker, og `Procfile`-linjene ordrett.

---

## 2026-09-14 — Arbeidsflyt: byggnummer ved push, og åpne punkter som ikke får gjemme seg  `#core/dokumentasjon`

To regler i `CLAUDE.md`, begge fra ting som gikk galt i dag.

**Commit-SHA ved hver push.** André: «når du pusher ting så vil jeg ha bygg nr
jeg kommer til å se på staging/prod». Sju tegn, for hver gren som ble pushet.
Det er nummeret som står i Railway-deployen, og uten det må den som verifiserer
gjette om det hun ser på er det som nettopp gikk ut.

**Et åpent punkt skal aldri stå som barn under et avkrysset punkt.** Da jeg
krysset av gjeldspunkt 1 og 2, ble to uavkryssede barn stående under dem —
`accounts` → `oppdrag.Enhet`, og den uforklarte enkeltfeilen. De var «i TODO» i
bokstavelig forstand og usynlige i praksis. Løftet til en egen bolk øverst, med
en peker igjen der de lå.

---

## 2026-09-14 — Service workeren til `vl-sw-5`, og utkastingen fikk en test  `#vaktliste/offline`

Bumpet foran prod-deployen. `activate` sletter alle `vl-sw-`-cacher som ikke
bærer gjeldende versjon, og fram til nå lå den gamle, udelte `vaktliste.js`
igjen i skallcachen på hver drifts-PC som hadde vært innom — død vekt, ikke
feil versjon, siden WhiteNoise hasher filnavnene og sida hentes nett-først.

**Prisen står i koden**: datakopien slettes med, så en PC som mister nettet
rett etter en bump står uten offline-liste til den har lastet én gang online.
Derfor ikke ved hver endring — en ny fil hentes uansett uten at versjonen røres.

**Utkastingen var udekket, altså den ene oppførselen bumpen hviler på.**
Regelen er nå `skalKastes()`, skilt ut som navngitt funksjon ved siden av
`avgjor()` og `erForGammel()`.

*Mitt første forsøk var feil, og det står i testens docstring:* jeg kopierte
`filter`-kroppen inn i testen som en streng. Da måler testen sin egen kopi og
går grønn uansett hva workeren gjør — nøyaktig synden gjeldspunkt 3.8 handlet
om, begått samme dag som jeg ryddet den. Funksjonen ble skilt ut i stedet.

Fem tester, tre mutasjoner fanget: likhet i stedet for prefiks (da overlever
både `-skall` og `-data`), `vl-sw-`-sjekken droppet (da slettes cacher
workeren ikke eier), og versjonen ikke bumpet.

---

## 2026-09-14 — Portalens egne tabeller auditlogges, og to lister som måtte finne selv  `#core/audit`

**`core/signals.py`: `AppSetting`, `ModuleSettings` og `Vakt`.** Hullet André
fant ved å spørre «logges ingenting fra core?». Svaret var nesten nei, og det
var ikke nytt av flyttingen — det hadde stått slik hele tiden. Portalen logget
hvert feltbytte på en pasient minutiøst, mens «noen slo av pasientmodulen for
alle» og «noen flyttet sesjonstimeouten fra 8 til 720 timer» ikke etterlot noe.
Feil vei rundt: jo mer inngripende handlingen var, jo mindre spor satte den.

**Den vanskelige halvdelen var å la være å logge.** `AppSetting` er
nøkkel/verdi og blander innstillinger et menneske har bestemt med tellere
maskinen har talt.

Jeg ga først André cron-linjene som eksempel. Det var det svakeste — fem rader
i måneden, knapt et problem. Da jeg gikk etter tallene i stedet for min egen
påstand, fant jeg det som faktisk betyr noe: `next_patient_nr_vakt_<id>`
telles opp ved **hver pasientregistrering**, og `next_oppdrag_nr_vakt_<id>` per
oppdrag. Uten unntaket gir en vakt med hundre pasienter hundre auditrader som
ingen har gjort, blandet inn mellom de ekte pasientradene — på nøyaktig de
vaktene der loggen betyr mest.

Regelen står som én navngitt funksjon, `nokkel_logges()`: **logg det et
menneske har bestemt, ikke det maskinen har talt.** Prefikser og ikke eksakte
navn, fordi tellerne bærer vakt-ID — en eksakt liste ville virket i test og
lekket ved neste vakt. Og det er en **unntaksliste**: en ny nøkkel logges som
standard, fordi en teller for mye er støy mens en innstilling for lite er et
hull man oppdager et år senere.

Verdiene logges, e-postmottakerne inkludert (Andrés avgjørelse): «hvem ble lagt
til» er hele spørsmålet man stiller, og oppbevaringen er den `purge_old_logs`
alt håndhever — ingen ny mekanisme, ingen ny frist.

`EKSPLISITT_MAPPING` i `audit/signals.py` blir virksom for første gang her.
Fram til nå merket den ingen rader, fordi ingen skrev tabellnavnene — noe jeg
skrev i TODO da jeg oppdaget det, framfor å la den se ut som den gjorde jobb.

**To lister som lette på steder i stedet for å finne dem — samme lærdom, samme dag.**

`SignalerFyrerIkkeUnderLoaddataTests` håndhever at hvert lagringssignal har
`@ikke_under_loaddata`. Den scannet `('oppdrag', 'patients', 'vaktliste')`
skrevet for hånd — så `core/signals.py` ville gått rett forbi den dagen den ble
skrevet, mens testen sa «alle lagringssignaler» og målte tre apper. Den globber
nå `*/signals.py`, med `VAKTEN_UNNTATT` for det ene tilfellet som med vilje står
uten (`audit.fyll_app_label` kortslutter på tomt felt).

Og `core/tests_testkommandoen.py` (ny) gjør det samme for testkommandoen i
CLAUDE.md: hver toppnivåpakke med `test*.py` må stå i den, og kommandoen må ikke
navngi noe som ikke finnes. Den utelot `myproject` i lang tid uten at noe sa
fra, og feilen ble funnet fordi et testtall ikke stemte — det er flaks, ikke en
mekanisme, og flaks kan man ikke planlegge to ganger.

Begge testene har en sperrehake mot seg selv: finner oppdagelsen nesten
ingenting, feiler den framfor å gå grønn mens den måler tomhet.

Tester: `core/tests_signaler.py` (16) og `core/tests_testkommandoen.py` (4).
Fem mutasjoner prøvd, alle fanget — tellerne fjernet fra unntakslista,
unntakslista snudd til inkluderingsliste, `pre_save` som ikke spør basen om
raden finnes, `myproject` fjernet fra kommandoen igjen, og en app som ikke
finnes lagt til.

---

## 2026-09-14 — To funn fra staging: CSP blokkerte lydbæreren, modaler holdt på fokus  `#oppdrag/enhetsskjerm`

Begge meldt av André ved verifisering på staging, og begge var ekte feil bak en
melding som så ut som støy.

**`media-src 'self' blob:` lagt til i CSP** (`core/middleware.py`). Konsollen sa:

    Loading media from 'blob:…' violates … "default-src 'self'". Note that
    'media-src' was not explicitly set, so 'default-src' is used as a fallback.

Det som ble blokkert er `_stilleLydbaerer()` i `oppdrag-enhet.js` — den stumme,
loopende WAV-en som finnes fordi iOS ellers regner Web Audio som «ambient» og
demper lydvarselet med ringebryteren. `default-src 'self'` dekker ikke `blob:`.

**Symptomet skjulte alvoret.** Oppdraget lastet, siden virket, og feilen sto
bare i konsollen — men på iOS betyr den at bilen ikke piper når telefonen står
på lydløs, altså nøyaktig det tilfellet lydbæreren er bygd for. En advarsel på
en side som ellers oppfører seg er ikke det samme som en advarsel uten
konsekvens.

Direktivet er smalt med vilje: `'self' blob:`, ingen verter, og `default-src`
er **ikke** slakket. En blob-URL kan bare lages av skript på vårt eget origin,
så den som kan lage en har allerede skriptkjøring — utvidelsen flytter ingen
grense som betyr noe. Å svare med `default-src 'self' blob:` ville derimot
sluppet blob-er inn i hvert direktiv som arver.

**`slippFokusFoerSkjul()` i `portal-utils.js`.** Bootstrap 5.3 setter
`aria-hidden="true"` på modalen når den lukkes, men flytter ikke fokus ut
først; lukker du med krysset, står fokus igjen på `.btn-close` inne i det som
nettopp ble skjult, og nettleseren **nekter** å sette attributtet:

    Blocked aria-hidden on an element because its descendant retained focus.

Konsekvensen er reell i begge ender: modalen blir liggende eksponert for
skjermlesere etter at den visuelt er borte, og den som navigerer med tastatur
mister fokuspunktet sitt i samme øyeblikk.

`hide.bs.modal` bobler, så **én** lytter i fila alle sidene laster dekker hver
modal i portalen. Alternativet Bootstrap selv peker på, `inert`, måtte vært
satt og fjernet per vindu — samme feil gjentatt ett sted per modal. Funksjonen
er navngitt og ikke anonym av samme grunn som `klikkSkalKjore()`: en `if` inne
i en lytter lar seg ikke kjøre i en test.

Tester: `patients/tests_security_headers.MediaSrcSlipperLydbaerenTests` (fem,
inkludert én som krever at kilden *fortsatt* lager blob-en — et direktiv som
verner om ingenting er verre enn ingen regel) og `core/tests_modalfokus.py`
(seks). Tre mutasjoner prøvd, alle fanget: media-src fjernet, `hide` byttet til
`hidden`, og `contains`-sjekken fjernet slik at fokus rives vekk uansett hvor
det står.

---

**Og et tredje funn, som kom av å telle testene:** kjøringen ga 2 687 der
forrige fulle kjøring ga 2 709. Differansen var ikke tester som forsvant —
**testkommandoen i CLAUDE.md utelot appen `myproject`**, 32 tester på
databasevalg, cache, `_env_bool`, statiske filer og migrasjoner. Det er vaktene
rundt «`DATABASE_URL` må være PostgreSQL på Railway» og rundt den `_env_bool`
som hadde rate-limitingen av i prod til 13. sep. Den som fulgte dokumentasjonen
kjørte dem aldri. Kommandoen er rettet.

At alt annet *er* med, er verifisert og ikke antatt: en AST-telling av
testmetoder per app stemmer eksakt med det kjøreren rapporterer for seks av
sju apper (`vaktliste` avviker med 54, som er arv fra basisklasser), og alle
98 testfiler samles inn.

**`myproject/tests_cache_config.py` hadde en ekte feil i opprydningen.**
`finally: importlib.reload(...)` sto *inne* i `with mock.patch.dict(...)`, med
kommentaren «Reload tilbake uten REDIS_URL så andre tester ikke påvirkes» — men
inne i blokken er `REDIS_URL` fortsatt satt, så modulen ble lastet tilbake med
den oppdiktede Redis-verten. Koden gjorde det motsatte av det kommentaren sa,
og det er den verste sorten: den som leser slutter å se etter.

Nå `addCleanup`, som kjører uansett utfall og etter at `with` er ute. Å bare
flytte `finally` utenfor ville vært verre enn før — en feilende assertion ville
hoppet over opprydningen helt.

**To mutasjoner mot den nye påstanden slapp gjennom**, og det står i koden:
opprydningen i *neste* test i klassen reparerer modulen før noen ser den gal,
så bare den siste testen alfabetisk kan lekke ut av klassen. Påstanden er
beholdt fordi den er gratis og sier at opprydningen gjorde jobben — men den er
ikke et gjerde rundt mønsteret, og kommentaren sier nå det i stedet for å la
den se sterkere ut enn den er.

**Én ting står uløst.** Den kjøringen som først tok med `myproject` endte
`FAILED (failures=1)`. Jeg fanget ikke hvilken test det var, og den har ikke
kommet tilbake på fire fulle kjøringer etterpå. Den er *ikke* forklart av
opprydningsfeilen over — det er en hypotese jeg ikke har bevist. Se TODO.


## 2026-09-14 — Gjeldspunkt 3.6: de to store JS-filene delt  `#vaktliste/planlegging` `#oppdrag/sentralbord`

`vaktliste.js` var 3 801 linjer, `oppdrag-sentral.js` 1 991. Nå fem og fire.

**Jeg rådet fra denne**, og står ved begrunnelsen: uten bundler er en deling
ren flytting av tekst, og refaktorering uten anledning innfører feil uten å
løse noe. André ba om den likevel, og da er den hans avgjørelse. Så den er
gjort med et sikkerhetsnett foran, ikke etter.

**Sikkerhetsnettet først.** Før en linje ble flyttet, tok jeg en fasit over de
182 + 95 toppnivåfunksjonene og de 25 + 22 toppnivåbindingene. Etter delingen:
samme antall, ingen mangler, ingen dubletter.

Delingen følger seksjonsmarkørene som alt sto i filene:

| Fil | Innhold |
|---|---|
| `vaktliste-kjerne.js` | Tilstand, tilgang, tid, henting, korpsvelger, nedtrekk |
| `vaktliste-tegning.js` | Tegning og byggere |
| `vaktliste-handlinger.js` | Handlinger og ressursroller |
| `vaktliste-offline.js` | Offline-køen |
| `vaktliste-register.js` | Mannskapsregisteret, korps og kompetanser |

**Den viktigste innsikten gjelder rekkefølgen, og jeg tok først feil om den.**
Jeg skrev i malen at «all toppnivå-tilstand står i kjernen». Det stemte ikke —
`STEMPLINGER`, `offlineTilstand` og ni andre lå i senere filer — og et krav
ingen holder er verre enn ingen. `let`/`const` på toppnivå er *skript-scopede*,
altså delt mellom filene, og en temporal dead zone treffes bare hvis noe
**kjører** før bindingen er nådd.

Den ekte regelen er derfor: **alt som kjører på toppnivå står i den siste
fila** — i praksis `DOMContentLoaded`-krokene. `core/tests_js_splitt.py`
håndhever den, sammen med at ingen funksjon er duplisert, at malens
`<script>`-rekkefølge stemmer med testenes, at de gamle samlefilene er borte,
og at ingen del er over 1 800 linjer. Uten den siste kunne én fil vokst tilbake
til 3 800 mens de andre sto tomme, med alt annet grønt.

Alle tre feilklassene er **prøvd mot mutasjoner**: en duplisert funksjon, et
kall lagt på toppnivå i kjernen, og to `<script>`-tagger byttet om. Alle tre
faller.

`VAKTLISTE_JS` og `OPPDRAG_SENTRAL_JS` i `js_test_utils` er nå **tupler**, og
`read_js()` skjøter dem. Det var grepet som holdt 62 testreferanser uendret —
for alt som leser kilden er de fortsatt én fil, som de er i nettleseren.

2709 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Gjeldspunkt 3.8: fem tester som målte kode, ikke oppførsel  `#core/dokumentasjon`

Gjeldskartet sa «en del eldre tester grep-er etter kodelinjer». Da jeg gikk
gjennom dem, var de fleste treffene **legitime**: XSS-skannerne leser kilden
for å *finne* en bygger før de kjører den, CSP-testene måler rendret utdata, og
regler som «ingen mal peker på et CDN» har ingen kjøretid å måle. Skillet går
på hva assertionen påstår, ikke på om fila leses.

Fem påsto implementasjonstekst, og de er skrevet om:

| Var | Er nå |
|---|---|
| `assertIn("if (metode !== 'GET')", sw.js)` | `avgjor()` kjøres for POST, PUT, PATCH, DELETE, HEAD, OPTIONS |
| `assertIn('mannskap.sort(', kilde)` | Rekkefølgen i svaret, med rader uten rolle og navn i motsatt rekkefølge inn |
| `assertIn("classList.toggle('active-mine'", js)` | `toggleBoardMine()` kalles mot et minimalt DOM, to ganger |
| `assertNotIn('fjernRessurs', kilde)` | `mkRessurs()` tegnes, og markupen spørres |
| `assertIn("'…Middleware',\n", settings_py)` | `settings.MIDDLEWARE_I_DRIFT` |

Tre av dem ble **bedre**, ikke bare mindre skjøre. Service worker-testen dekket
før bare POST — nå PUT, PATCH og DELETE også, som den literale linja aldri
sjekket. Sorteringstesten kjører nå mot begge databasene og ville fanget et
databasealfabet som slapp gjennom. Og `fjernRessurs`-sjekken var en
*omdøpingssjekk*: den ville gått grønn om noen la en `data-action="slettRessurs"`
rett i kortet.

Hver av dem er prøvd mot feilen den skal fange, ikke bare kjørt grønn.

**Og så fant suiten en ekte flake — den jeg noterte som uavklart i går.**
`RateLimitPaaBrukeradminTests.test_sletting_strupes` feilet én gang av mange og
gikk grønt ved neste kjøring. Årsaken er ikke «flaky test» som forklaring, men
`django_ratelimit._get_window`: den legger vinduskanten et fast antall sekunder
inn i hvert minutt, jittret per nøkkel med `crc32`. Tolv forsøk mot `10/m` som
straddler den kanten deles i to bøtter der ingen når ti — altså ingen 429, og
testen faller.

Forsøkene er nå **2 × grensen + 1**. Da må den ene siden av en hvilken som helst
oppdeling bryte grensa, uansett når i minuttet testen kjører. Naboen i
`core/tests_ratelimit.py` hadde samme svakhet mot `10/5m` og er rettet likt.
Regelen står i `CLAUDE.md`.

---

## 2026-09-14 — Gjeldspunkt 3.1: kontoappen kjenner ingen modul ved navn  `#core/tilgang`

`accounts/forms.py` importerte `patients.models` for å tegne kortet
«Pasientregistrering» på brukersiden — kontoappen kjente altså én modul ved
navn. `core/kontokobling.py` er det tredje registeret på like mange timer, og
`PasientRolleForm` med malbiten sin bor nå i pasientmodulen.

**Koblingen er domenedata, ikke tilgang.** Den setningen står i kodetreet nå,
der den hører hjemme. Radioen satte en gang også `kan_redigere_pasienter`, og
sammenblandingen gjorde det umulig å være koblet som førstehjelper uten å ha
skrivetilgang. Samme skille som `Mannskap.user` i vaktlista.

`handling` — verdien i skjemaets skjulte `action` — må være **unik**, og
registeret avviser to handlere som deler den: viewet finner handleren på det
navnet, så to moduler med samme handling ville latt den ene lagre den andres
skjema, med «lagret» over noe helt annet.

**Et funn gjeldskartet ikke hadde:** `accounts` har en kobling til i samme
klasse. Velger admin kontotypen «bil», valideres enhetsnavnet i `forms.py` og
`oppdrag.Enhet`-raden opprettes — eller hentes fram igjen, om den er
pensjonert — i `views.py`. Det er samme slags avhengighet, men en annen form:
her er det *selve kontoopprettelsen* som får en sideeffekt i en modul, ikke et
skjema ved siden av kontoen. Å flytte den er kirurgi i brukeropprettelsen, og
hører ikke hjemme i samme runde som alt annet.

Avhengighetstesten dekker derfor nå **`accounts` og `audit` også** — de er
rammeverk de også (`TEKNISK_GJELD.md` §1) — med `KJENTE_UNNTAK_RAMMEVERK` som
sperrehake på de to `Enhet`-importene. `core`s egen liste står fortsatt tom.

2704 tester grønne.

---

## 2026-09-14 — To registre til: `core` kjenner ingen modul ved navn lenger  `#core/drift`

`KJENTE_UNNTAK` er tom. Den sto med fem rader i går kveld — de eneste stedene
rammeverket fortsatt importerte en modul — og begge er nå registre etter samme
idiom som `core/stats.py` fra i fjor.

**`core/driftstatus.py`.** Server-status viste hvilke vaktlister som var i
drift og hvor mange oppdrag som sto på tavla, ved å importere `vaktliste.models`
og `oppdrag.models`. Nå melder modulene seg inn fra `apps.ready()`.

Payloaden er **bit for bit den samme** — nøklene klienten leser er uendret, og
JS-en er ikke rørt. Det som endret seg er hvem som regner dem ut.

To egenskaper det var verdt å skrive tester for:

- **Én død modul tar ikke med seg dashbordet.** `samle()` fanger hver handler
  for seg; feilen havner i `error` med modulnavnet foran, vasket med
  `_scrub_secrets`, og de andre kortene tegnes. Et dashbord som selv gir 500
  fordi vaktlista har en treg spørring, er borte akkurat når man trenger det.
- **Standardnøklene settes i `core`, ikke i handlerne.** Er en modul av eller
  ikke registrert, skal kortet vise «–» og ikke forsvinne fra siden.

**`core/portalinnstillinger.py`.** Den vanskeligere av de to: portalens
innstillingsside hadde vaktlistas fire e-postfelter — markup, validering og
lagring — midt inne i rammeverkets view og mal. Nå registrerer modulen
`mal`, `kontekst()`, `valider()` og `lagre()`, og malbiten bor i
`vaktliste/templates/`.

`valider()` og `lagre()` er **delt i to med vilje**. Vaktas navn skrives på
`Vakt`, resten i `AppSetting`, og ingen transaksjon binder dem — todelingen er
det eneste som hindrer at en avvist innsending lagrer halve skjemaet. Viewet
validerer alle handlere *og* portalens egne felter før én eneste skriving skjer.
`core/tests_registre.py` prøver det med en handler som alltid nekter, og krever
at vaktas navn står urørt etterpå.

*Én test måtte rettes underveis, og det var testen som tok feil:* jeg antok at
`_scrub_secrets` vasker vilkårlige ord. Den vasker credentials i URL-er, som er
det den er til for. Prøven bruker nå en ekte connection-streng og krever
`[scrubbed]@` i svaret.

2699 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Flytting fase 4: adminflaten samlet, `core/views.py` delt, skimet slettet  `#core/drift`

Siste fase i flytterunden. Ingen migrasjon.

**`/portal-admin/` er ett sted** (gjeldspunkt 3.2). De 21 rutene lå i tre
filer — `myproject/urls.py`, `core/urls.py` og `accounts/urls.py` — og ingen
kunne se hele adminflaten uten å lete tre steder. Nå: `core/urls_admin.py`,
inkludert fra prosjektet.

**Og her var det en felle jeg gikk i.** Jeg tok et snapshot av rutekartet før
samlingen og sammenlignet etterpå: 21 ruter, identiske stier, identiske navn.
Men `pattern.name` er navnet **uten navnerom**, og `accounts` og `core` har
hver sin `app_name`. Kartet var «identisk» mens hver
`{% url 'accounts:user_list' %}` i malene var død. Viewtestene fanget det —
tre tester som tilfeldigvis rendret de riktige sidene.

To ting kom ut av det:

- **Adminflaten har nå ett navnerom, `portaladmin`.** 131 referanser i 25
  filer skiftet prefiks. Det samme skjermbildet het `accounts:user_list` eller
  `core:backup_admin` avhengig av hvilken app som tilfeldigvis eide viewet;
  nå er det flaten som bestemmer navnet.
- **`core/tests_malenes_urler.py`** leser hver `{% url %}` i hver mal og
  krever at navnet lar seg slå opp. Django feiler på en ukjent rute først når
  malen *rendres*, så en tagg inne i en `{% if %}` som bare vises for én rolle
  kan være død i måneder med suiten grønn. Testen fant fem med det samme:
  server-status-rutene hadde aldri hatt navnerom, så omskrivingen min traff
  dem ikke.
- **`core/tests_urls_admin.py`** låser hele kartet til literale verdier *med*
  navnerom, og rendrer hver GET-side under `/portal-admin/`. Lista er utledet
  av kartet, så en ny adminside dekkes i det øyeblikket ruta legges inn.

**`core/views.py` er delt i fire** (gjeldspunkt 3.7): `views_portal`
(dashbord, min profil), `views_admin` (innstillinger, moduler, auditlogg),
`views_backup` og `views_varsler`. 830 linjer og 24 views om alt fra backup til
varsler — samme grep `patients/views.py` fikk i N13.3.

**`accounts/decorators.py` er slettet** (gjeldspunkt 3.3). Den var en ren
re-eksport av `admin_required`, og den eneste leseren var testen som
verifiserte at den virket.

*Og slettingen avdekket at regelen sto brutt:* testen som skulle håndheve
«ingen produksjonskode importerer fra skimet» lette bare etter den absolutte
formen `from accounts.decorators import`. `accounts/views.py` brukte den
relative, `from .decorators import`, og slapp unna i et år med testen grønn.
En regel som bare dekker halve syntaksen måler noe annet enn den later som.

**Etterslep rettet samme dag:** «Tilgangskontroll»-bolken i `CLAUDE.md` beskrev
fortsatt `accounts/decorators.py` som et skim som beholdes fordi en test
verifiserer det. Fila er slettet. En arkitekturbeskrivelse som peker på noe som
ikke finnes, er verre enn ingen beskrivelse — den neste leter etter fila.

2691 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Flytting fase 3: scopet, middlewaren, helsesjekken og dashbordet  `#core/drift`

Ingen migrasjon — ren kodeflytting.

- **`core/vakt.py`**: `hent_aktiv_vakt` og `vakt_for_year`. De lå i
  `patients/services.py` fordi `AppSetting`-pekeren gjorde det, og da måtte
  oppdragsmodulen, vaktlista og statistikken importere *pasientmodulen* for å
  vite hvilken vakt de var i. Ingen av de to rører pasientdata.
- **`core/middleware.py`**: CSP-headerne, metrikkene og backupklokka. Ingen av
  dem er pasientspesifikke, og `settings.MIDDLEWARE` pekte dermed på en modul
  som kunne tas ut.
- **`core/health.py`** og **`core/admin_status.py`** med testene sine.

**Gevinsten, målt:** `core` importerer nå en modul på **fem** steder i
produksjonskode, mot rundt tjue før runden. Fire av dem er modulregisteret, som
skal navngi modulene sine — det er det et register er.

`core/tests_avhengighetsretning.py` låser det med AST, samme idiom som
`OppdragImportererIkkeVaktlista`. Uten en test er dette en intensjon, og
retningen snek seg feil vei én gang før.

**Et funn flyttingen gjorde synlig, og som er ekte gjeld:** `admin_status.py`
og portalinnstillingene importerer `vaktliste` og `oppdrag` — dashbordet viser
tall per modul, og innstillingene skriver vaktlistas e-postmottakere.
Koblingen fantes før flyttingen også, men da lå filene i `patients`, så den
leste som «modul → modul» og ikke som «rammeverk → modul». Riktig løsning er
den statistikkappen alt bruker: et register modulene melder seg inn i. Det er
en egen jobb med egen risiko og skal ikke ri på en flytterunde, så de fem
importene står i `KJENTE_UNNTAK` — en **sperrehake**: lista skal aldri vokse,
og en test krever at en importvei som ryddes tas ut av den.

2652 tester grønne på SQLite og PostgreSQL 16 (2684 med `myproject`).

---

## 2026-09-14 — Flytting fase 2: `AppSetting` og `Backup` til `core`  `#core/drift`

De to portalvide modellene har aldri vært pasientdata. De lå i `patients` fordi
den var første app og det ikke fantes noe annet sted — og resultatet var at
**rammeverket avhang av modulen**: `core.backup`, `core.arkiv` og `core.offsite`
importerte alle `patients.models`.

`core/0011` + `patients/0018`, begge `SeparateDatabaseAndState` med tom
`database_operations`. **Ingen SQL i det hele tatt.** `db_table` er bundet til
`patients_appsetting` og `patients_backup`, og det er et valg: Railway kjører
release-fasen *før* den bytter container, så en omdøpt tabell ville gitt 500 på
tilnærmet hver forespørsel i vinduet mellom `migrate` og byttet — `AppSetting`
bærer pekeren til aktiv vakt.

**En felle planen hadde plassert feil.** `AppSetting` lå i pasientbackupen fordi
pasienthandleren dumper `apps = ['patients']` og fikk modellen med på kjøpet.
Portalfila lister modellene sine ved navn, og planen la den raden i fase 4. Det
ville latt portalinnstillingene — aktiv vakt, lydvarslene, e-postmottakerne —
ligge utenfor **alle** backupfiler mellom de to deployene, uten at noe sa fra.
`core.AppSetting` er derfor lagt i portalfila i samme commit som flyttingen.

**Audit-loggen** (Andrés valg, vei 2): `EKSPLISITT_MAPPING` får
`patients_appsetting` og `patients_backup` → `core`. Uten dem ville utledningen
lest «patients» av tabellnavnet og merket hver framtidig rad med feil modul —
forvirringen flyttet fra kodetreet til loggen. Gamle rader endres ikke; bruddet
er datert.

Navnetabellen fra fase 1 fikk sine to rader, og **hele kjeden er prøvd mot ekte
PostgreSQL**, ikke bare i suiten:

- **Oppgraderingssimulering:** en base migrert med koden som står i prod i dag,
  seedet med innstillinger, backuprader og pasienter, så migrert med den nye.
  Alle rader intakt, FK-en til brukeren intakt, tabellnavnene uendret — og
  ingen tom `core_appsetting` ved siden av den fulle.
- **Gammel fil, ny kode:** en backup tatt med prod-koden bærer
  `patients.appsetting`. Gjenopprettet med den nye logger den «oversatte 2
  modellnavn fra en eldre fil», og radene kommer tilbake som `core.AppSetting`.
  Det er den prøven som svarer på om de 730 dagene med offsite-filer fortsatt er
  gjenopprettbare.

39 filer fikk nye importlinjer. To former skriptet ikke fanget, og som testene
gjorde: en flerlinjes import i parentes, og ett `apps.get_model('patients',
'AppSetting')` i `verifiser_vakt`. De samme oppslagene i *historiske*
migrasjoner står urørt med vilje — de løses mot tilstanden der modellen fortsatt
bodde i `patients`.

2647 tester grønne på SQLite og PostgreSQL 16, 3 migrasjonsprøver OK.

---

## 2026-09-14 — Flytting fase 1: navnetabellen, satt på plass før den trengs  `#core/drift`

`core.backup.oversett_modellnavn()` og `GAMLE_MODELLNAVN`. Tabellen er **tom**,
så fasen endrer ingenting i dag. Det er hele poenget.

En backupfil bærer modellnavnet — `{"model": "patients.appsetting", …}` — og
`loaddata` slår det opp i app-registeret. Flytter modellen til `core`, svarer en
fil tatt før flyttingen «Invalid model identifier» i stedet for å laste. Og
modulfilene ligger 730 dager hos Scaleway. Uten tabellen ville hver flytting
gjort hele arkivet av eldre filer ubrukelig i det øyeblikket koden ble deployet,
uten at noe sa fra: filene lastes jo opp som før.

Røret settes derfor på plass nå, før fase 2 fyller det. Gjøres de sammen, er
deployen som flytter modellene også den som først prøver oversettelsen — og
feiler den, viser det seg den dagen noen gjenoppretter.

Oversettelsen står **før** `_inspect_payload`, ikke rett før `loaddata`, slik at
kontrollen ser dagens modellnavn og slipper å kjenne begge.

**Rask vei:** er ingen av navnene å finne i bytene, returneres fila *identisk*
uten at JSON-en parses — testet med `assertIs`, ikke `assertEqual`, fordi en hel
databasefil ikke skal serialiseres fram og tilbake for en tabell som ikke har
noe å si.

Testene kjører mekanismen mot en **oppdiktet** flytting (`gammelapp.patient` →
`patients.patient`), siden den ekte ikke har skjedd ennå — med motprøven: uten
tabellen feiler nøyaktig samme fil med «Invalid model identifier:
gammelapp.patient», og gjenopprettingen rulles tilbake.

*Testen fant én inkonsistens i første utkast:* oppslaget var ufølsomt for store
bokstaver, men den raske veien var det ikke — et navn med store bokstaver ville
sluppet forbi uoversatt og feilet i `loaddata`, altså nøyaktig det tabellen
finnes for å hindre. Porten er nå like ufølsom, og prisen (én `bytes.lower()`)
betales bare når tabellen har rader.

Avklart samtidig: audit-loggens `app_label` mappes til `core` for de flyttede
tabellene i fase 2, rekkefølgen på fasene står, og `accounts/decorators.py`
slettes i fase 4.

2644 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Neste post planlagt: det portalvide ut av `patients`  `#core/drift`

`docs/PLAN_FLYTTING_TIL_CORE.md`. Trinn 2 i `PLAN_REKKEFOLGE_2026-09.md`, nå
som backupomleggingen er ferdig og prod har en gjenopprettbar backup foran den
migrasjonen som rører modellene.

**Lista har krympet siden kartleggingen 13. sep.** `BackupConfig`,
`backup_service.py` og `RETENTION_HOURS` er slettet i fase 8, `Lydvarsel`-hullet
falt ut da slettelista ble utledet, og `core.Vakt` fikk sin portalfil i fase 3.
Igjen står `AppSetting`, `Backup`, `hent_aktiv_vakt`, tre middlewarer,
`/healthz/` og server-status — 34 produksjonsfiler og 30 testfiler, nesten alt
importlinjer.

To funn planleggingen ga, som ikke sto i kartleggingen:

- **Tabellnavnene skal beholdes, og argumentet er nedetid.** Railway kjører
  release-fasen *før* den bytter container, så mellom `migrate` og byttet står
  gammel kode og serverer mot nytt skjema. En omdøpt `patients_appsetting` ville
  gitt 500 på tilnærmet hver forespørsel i det vinduet — tabellen bærer pekeren
  til aktiv vakt. Kartleggingen anbefalte også å beholde, men på kosmetisk
  grunnlag.
- **Audit-loggens `app_label` utledes av tabellnavnet** (`split('_', 1)[0]`).
  Beholder vi navnene, står hver framtidig auditrad for portalinnstillingene som
  «patients» selv når modellen bor i `core` — forvirringen flyttet fra kodetreet
  til loggen. Tre veier ut, anbefaling i notatets §3.2, og valget er Andrés fordi
  det handler om hva han ser i filteret.

**Fella som styrer faserekkefølgen:** backupfilene bærer modellnavnet
(`"model": "patients.appsetting"`), og en fil tatt før flyttingen lar seg ikke
laste etterpå — `loaddata` svarer «Unknown model». Filene lever 730 dager
offsite. Navnetabellen bygges derfor i **fase 1**, der den er en no-op, slik at
den er i prod og prøvd før fase 2 fyller den. Gjøres de sammen, oppdages en feil
i tabellen den dagen noen gjenoppretter.

---

## 2026-09-14 — Prefiksrutingen låst: `full/` kan ikke bli `backups/` i stillhet  `#core/backup`

André, etter deployen: «Hele databasen heter `backup-full-auto-…`, mens modulene
heter `backup-<modul>-…`. Vil det fungere med `full/` og `backups/`?»

Ja — det er to ulike prefikser. `backup-` er del av *filnavnet*, og bærer slugen
så `slug_fra_filnavn()` kan lese den tilbake når man henter. `full/` og
`backups/` er *objektnavnet*, altså mappa, og det er den livssyklusreglene
filtrerer på. De to har ingenting med hverandre å gjøre.

Men spørsmålet pekte på noe ekte: `prefiks_for()` sammenligner mot strengen
`'full'` direkte, ikke mot `Backupplan.FULL_SLUG`. Avveiningen er grei — den
slipper å importere modeller inn i `offsite.py` — men den etterlater slugen
skrevet to steder som må endres samtidig.

**Og de to feiler ulikt.** Døper noen om den hele fila i modellen uten å røre
`offsite.py`, går ingenting i stykker med det samme: filene lastes opp som før,
bare til `backups/`. Da lever hele databasen — med passordhasher og
TOTP-hemmeligheter — i 730 dager i stedet for 90. Ingenting feiler, ingen logg
sier fra, og kortet på backup-siden ser riktig ut: reglene *står* jo som de
skal, det er filene som ligger feil sted. En personvernbeslutning endret av en
navneendring.

`PrefiksRutingTests` låser fire ting: at `prefiks_for(FULL_SLUG)` gir `full/`,
at hver **registrert** handler (registeret er fasit, ikke en liste i testen)
ruter dit den skal, at filnavnet leser tilbake til samme prefiks som
opplastingen brukte — opplastingen får slugen som argument, hentingen leser den
av navnet, og blir de uenige lastes fila opp ett sted og letes etter et annet —
og at de to prefiksene ikke er forstavelser av hverandre, for da ville én regel
truffet begge og fristene ikke latt seg skille.

*Prøvd mot feilen de påstår å fange*, ikke bare kjørt grønne: med slugen endret
i `offsite.py` faller to av dem med «filene ville havnet under backups/ og fått
730 dagers oppbevaring i stedet for 90», og med `PREFIKS_FULL` satt til
`backups/full/` faller overlapp-testen.

2634 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-14 — Migrasjonsprøve for Backupplan, før prod  `#core/backup`

Før omleggingen går til prod: en prøve som kjører `core/0008`–`0010` mot ekte
PostgreSQL **med rader i basen**, i den historiske formen.

Det er den ene tingen verken suiten eller `makemigrations --check` svarer på.
Djangos testbase lages ved å kjøre migrasjonene mot en *tom* base, så
dataskrittet i `0009` finner ingenting å oversette, skriver ingenting, og går
grønt uten å ha gjort noe. Feilen som tok ned release-fasen 30. august krevde
PostgreSQL **og** rader — og en backup-omlegging som crash-looper release-fasen
er den verst tenkelige tida å oppdage det på.

Prøven seeder de seks tilstandene som betyr noe: en modul som er på, en som
står av via `enabled=False`, en som står av via `interval_minutes=0` (to måter
å si det samme, og begge finnes), og intervaller som går opp i timer, døgn og
ikke i det hele tatt. Den sjekker oversettelsen, at ingen rad forsvant, at
`behold` overlevde omdøpingen, at standardplanen ble opprettet, og at de gamle
kolonnene faktisk er borte etter steg 3.

**Og den viktigste påstanden: ingen eksisterende rad arver standardplanen.**
Gjorde de det, ville oppgraderingen endret hvor ofte prod tar backup uten at
noen ba om det — og det ville vist seg som en fil som ikke kom.

*Funn underveis, om prod snarere enn om koden:* første utkast av prøven
kolliderte på `patients`, fordi `core/0002` og `0005` selv oppretter de radene.
Prod har dem altså allerede — seedet av migrasjoner, noen av dem siden redigert
i grensesnittet — og seeden bruker nå `ON CONFLICT DO UPDATE` for å ligne på
det.

3 av 3 prøver grønne mot PostgreSQL 16.

---

## 2026-09-14 — Backup fase 8: den gamle veien er stengt  `#core/backup`

Siste fase i backupomleggingen, og den eneste som bare fjerner ting. Tre
levninger fra før `core.backup` er slettet, og migrasjonen er `patients/0017`.

**`patients/backup_service.py`** var en tynn proxy som het seg å være
bakoverkompatibilitet. Problemet var ikke at den var død kode — den ble brukt,
av vaktavslutningen og av testene. Problemet var signaturen: `create_backup()`
uten slug, med «patients» bakt inn. Etter fase 4 er slugen hele forskjellen på
en pasientfil og en hel database, og et kall som ikke nevner den har ingen måte
å ta feil på synlig vis. `core.backup.create_backup(slug=...)` krever den som
førsteargument, og det er nå den eneste veien inn.

**`db_backup`** het som om den tok hele databasen og tok pasientmodulen. Den
sto i `CRON_JOBBER` til 13. sep. uten noen gang å ha vært satt opp i Railway —
og det var flaks, for et volum kan bare henge på én tjeneste, så en
cron-tjeneste uten `/data` ville skrevet fila til et flyktig filsystem og
etterlatt en `Backup`-rad uten fil. Klokka er en tråd i web-prosessen
(`core/backup/klokke.py`), og `backup_kjor` er den manuelle inngangen.

**`patients.BackupConfig`** var én singleton for hele portalen: ett intervall,
valgt fra fem faste verdier. `core.Backupplan` er per modul, med tre moduser og
fritt intervall. Verdiene ble kopiert over allerede 13. sep. av
`core/0002_modulebackupconfig`, så det er ingen data å ta vare på her.

**`RETENTION_HOURS = 72`** ble aldri lest av noe. Oppryddingen er
antallsbasert (`Backupplan.behold`, cap på filer *på volumet*), og hvor lenge
kopien lever offsite er bucketens livssyklusregel — to helt forskjellige ting.
En konstant som beskriver en tredje, ikke-eksisterende regel er verre enn ingen.

`LegacyBackupErBorteTests` håndhever at ingen av de tre kommer tilbake, og at
`create_backup` fortsatt krever slug. Testen finnes fordi hver av dem ville
kommet tilbake som en bekvemmelighet, ikke som en feil noen la merke til.

**Om migrasjonen:** den avhenger av `core/0002`, som gjør
`apps.get_model('patients', 'BackupConfig')` i et `RunPython`-steg. Prøvd uten
avhengigheten: Django la dem i riktig rekkefølge likevel, fordi `core/0002`
selv peker på `patients/0005`. Kanten står der for at rekkefølgen skal være
skrevet i stedet for et sammentreff i grafen. Ren skjemaendring — ingen
`RunPython`, ingen triggerkø, ingen prøve i `core/migrasjonsprover.py`.

2630 tester grønne på SQLite og PostgreSQL 16. **Backupomleggingen er ferdig:
alle åtte fasene er levert.**

---

## 2026-09-14 — Backup fase 7: oppbevaringstidene, og et kort som leser dem tilbake  `#core/backup`

Fristene offsite håndheves av **Scaleway, ikke av oss**. Portalens IAM-nøkkel
har ikke sletterett, og `enforce_cap` rører bare volumet — livssyklusreglene i
bucketen er dermed den eneste mekanismen som noen gang sletter en offsite-kopi.

André satte reglene i konsollen 14. sep. 2026: `backups/` 730 dager for
modulfilene, `full/` 90 dager for den hele databasen. Regelen sto til da på
«alle objekter i bucketen», og måtte snevres inn til `backups/` **før** regelen
på `full/` ble lagt til: to regler som treffer samme objekt er et sted å gjette.

**Kortet på `/portal-admin/backup/` leser nå reglene tilbake fra bucketen** og
sammenligner dem med beslutningen (`core.offsite.livssyklus()`,
`FORVENTET_DAGER`). Det er ikke pynt. Sammenligningen er på **nøyaktig**
prefiks, fordi den feilen man faktisk gjør er `/full` i stedet for `full/` — en
regel som ser riktig ut i konsollen og treffer ingenting. Da blir filene
liggende for alltid, og det eneste som sier fra er at noen leser
`get-bucket-lifecycle-configuration` for hånd. Nå står avviket i rødt ved siden
av backupene, hver gang noen er på siden.

Fem tilstander kortet skiller mellom, fordi de har ulik årsak og ulikt svar:
regelen mangler, regelen står på feil prefiks, regelen er slått av, regelen har
feil antall dager, og bucketen har ingen regler i det hele tatt
(`NoSuchLifecycleConfiguration` — «filene blir liggende for alltid», ikke en
lesefeil). Mangler nøkkelen `ObjectStorageBucketsRead`, står det «ukjent» med
årsaken, ikke et falskt grønt.

`livssyklus()` **kaster aldri**, og cacher svaret i fem minutter: et kort som
selv gir feil når nettverket er nede, er borte akkurat når man trenger det, og
et S3-kall per sidelasting er et kall for mye.

2627 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-13 — Backup fase 6: `verifiser_backup`  `#core/backup`

En backup ingen har gjenopprettet er en hypotese. Suiten har hatt en test som
gjenoppretter alle filene i rekkefølge siden fase 3, men den bruker syntetiske
data og svarer på om *koden* virker. `verifiser_backup` tar **filene som
faktisk ligger på volumet**, laster dem inn i en engangsbase, og sammenligner
radene mot det filene inneholder — modell for modell.

Den rører ingenting. Alt skjer i en flyktig SQLite-fil i en midlertidig mappe
som slettes etterpå, og backupfilene kopieres dit først, så
pre-restore-øyeblikksbildene gjenopprettingen lager havner i søpla og ikke
blant de ekte backupene.

**Den kaller `gjenopprett`, ikke `restore_backup`.** Da er det kommandoen man
faktisk ville kjørt i en katastrofe som er prøvd, ikke en nabo til den.

To ting den lærte underveis, begge om å ikke lyve:

- **En tom fil er ikke en bestått prøve.** Første kjøring sa «6 modeller kom
  tilbake» om et sett der arkivfilene ikke inneholdt en eneste rad. Nå står det
  hvor mange objekter hver fil har, og en tom fil får en egen advarsel: enten er
  modulen tom, eller så ble fila tatt før dataene fantes.
- **Gjenopprettingen skriver sin egen auditrad**, og i den hele fila er
  `audit.AuditLog` med i slettelista. Basen skal altså ha én rad *mer* enn fila,
  og det er riktig. Sammenlignet strengt meldte prøven avvik på noe som
  fungerte akkurat som det skulle — og en prøve som roper ulv blir ikke lest
  neste gang.

`PORTAL_ENGANGSBASE=1` er en ny, navngitt åpning i `settings.py`: sjekken som
ellers nekter SQLite på Railway slipper engangsbasen gjennom, så kommandoen kan
kjøres **der filene er**, uten en ekstra databaseserver og uten å lage baser ved
siden av produksjonsdata. Flagget settes av den ene kommandoen og skal aldri stå
på en tjeneste.

Testene kjører ekte underprosesser mot en ekte engangsbase — tregere enn resten
av suiten, og det er poenget: det er nettopp underprosessen og filstien som skal
prøves. Én av dem ødelegger en fil med vilje og krever at prøven ser det; uten
den ville «alt kom tilbake» bare betydd «noe kom tilbake».

Runbooken §8b sier når kommandoen skal kjøres: etter første backup i en ny vakt.

Verifisert: 2618 tester grønne på SQLite og PostgreSQL 16, og kommandoen kjørt
mot ekte filer — normalveien, den hele fila, en ødelagt fil og en tom.

---

## 2026-09-13 — Backup fase 5: gjenoppretting fra kommandolinja  `#core/backup`

`manage.py gjenopprett` finnes nå. Veien fantes ikke før: `hent_offsite` henter
og dekrypterer fila, men rører ikke databasen — siste linje den skrev var
«gjenopprett fra /portal-admin/backup/». I en tom base, som er akkurat der man
er når man trenger den, er det ingen å logge inn som. Katastrofeveien gikk
altså gjennom en nettleser uten bruker.

`--list` viser filene på volumet, `--siste <modul>` tar den nyeste og hopper
over pre-restore-øyeblikksbildene (de er tilstanden man nettopp gikk bort fra),
og `--hent <objekt>` henter fra Scaleway og gjenoppretter i ett. Samme funksjon
som knappen kaller: samme pre-restore-øyeblikksbilde, samme auditrad.

**`--ja` er nødvendig, ikke bekvemt.** `railway ssh -- <kommando>` kjører uten
interaktiv terminal, så et `input()` ville hengt til noe ga opp — uten at det
sto hvorfor, i en katastrofe. Kommandoen ser etter terminalen og sier hva som
mangler i stedet for å vente. **`--full` kreves** når fila er hele databasen:
slugen leses av filnavnet, så flagget er teknisk overflødig, men brukere,
passord og MFA skal ikke kunne erstattes av en skrivefeil.

**Auditraden er flyttet fra viewet inn i `restore_backup`**, med en kilde-tekst
(«grensesnittet» / «kommandolinja»). Sto den i viewet, ville katastrofeveien
vært den eneste gjenopprettingen som ikke etterlot seg et spor. Begge
inngangene gir nå nøyaktig én rad — verifisert av en test som ville fanget både
den manglende og en dobbel.

`slug_fra_filnavn` er flyttet til `core.backup.service`, ved siden av
`_build_filename` som bygger navnet. Den sto i `core/offsite.py` og leste en
form som defineres et annet sted; nå blir begge feil samtidig om formen endres,
i stedet for hver for seg.

Runbooken §8b har fått hele katastrofeprosedyren: den korte veien gjennom den
hele fila, den lange gjennom modulfilene i bindende rekkefølge (portal først,
fordi alt peker på vakta), og at `purge_old_logs` og `kollaps_arkiv` skal kjøres
rett etterpå — backupen har egen slettefrist, og det som var slettet i basen
skal ikke komme tilbake.

Verifisert: 2608 tester grønne på SQLite og PostgreSQL 16, og kommandoen er
kjørt mot en ekte base: sperrene slår ut som de skal, gjenopprettingen henter
dataene tilbake, og auditraden står med kilde.

---

## 2026-09-13 — Backup fase 4: hele databasen i én fil  `#core/backup`

Katastrofekopien finnes nå. `core/backup/full.py` dumper alt i databasen unntatt
sesjoner, contenttypes, permissions, `admin.LogEntry` og backup-metadata.
Brukere med passordhasher, MFA-enheter, tilganger, audit- og innloggingslogg,
vakta og alle modulenes data er med — fila er **selvbærende**, og
fremmednøkler til kontoer strippes derfor ikke slik modulfilene gjør.

**Appene listes ikke opp for hånd.** `collect_apps()` regner dem ut fra
app-registeret ved hvert kall, så en ny modul er med fra dagen den finnes. En
hardkodet liste ville vært en ny sjanse til å glemme noe, og en katastrofekopi
som stille mangler en app er verre enn ingen — fordi man tror man har den.

**Eget prefiks offsite.** `full/` ved siden av `backups/`, fordi
livssyklusreglene i bucketen filtrerer på sti og 90 dager ikke kan skilles fra
730 uten. `hent_offsite` utleder prefikset av slugen i filnavnet, så man trenger
ikke vite hvor fila ligger.

**Bevist i en tom PostgreSQL-base:** hele basen tilbake fra den ene fila —
brukere, MFA-enheter, audit, vakt, pasienter, oppdrag, mannskap og vaktposter,
alle tall like — og innlogging med det opprinnelige passordet virker etterpå.
En gjenoppretting man ikke kan logge inn etter, er ingen gjenoppretting.

**Funnet som stoppet den første kjøringen var en eksisterende feil.** Ingen av
de atten lagringssignalene i portalen så etter `raw=True`. Django sender det når
`loaddata` skriver en rad, og det betyr «denne raden kommer fra en fil, ikke fra
noen som gjorde noe». Uten vakten fyrte audit-signalene under hver eneste
gjenoppretting, og de leser relaterte objekter for å skrive hva som ble endret.
I den hele fila kommer et `Vaktpost` før sitt `Mannskap`, og gjenopprettingen
stoppet med «Mannskap matching query does not exist». Modulenes gjenopprettinger
feilet ikke, men skrev **én auditrad per lastet rad** — tusen pasienter tilbake
ga tusen «endret»-rader uten en bruker som hadde endret noe.
`audit.utils.ikke_under_loaddata` er vakten nå, lagt på alle atten,
og `SignalerFyrerIkkeUnderLoaddataTests` krever den også av neste mottaker.
Selve gjenopprettingen logges fortsatt, av viewet, med hvem som gjorde den.

Gjenopprettingsbekreftelsen sier hva som skjer: brukere, passord, MFA, tilganger
og logger erstattes, kontoer opprettet etter backupen forsvinner, og **kontoen
du er logget inn med byttes ut underveis** — var passordet et annet da backupen
ble tatt, blir du logget ut med det samme.

`CLAUDE.md`-avsnittet om backup er skrevet om: sju handlere,
gjenopprettingsrekkefølgen, den utledede slettelista, `raw`-vakten, de to
prefiksene og at det ikke finnes nedlasting.

Verifisert: 2592 tester grønne på SQLite og PostgreSQL 16.

**Krever André før dette er i prod:** livssyklusregelen på `full/` (fase 7).
Uten den lander de første hele backupene under 730-dagersregelen.

---

## 2026-09-13 — Backup fase 3: vaktlista dekket, og slettelista utledes  `#core/backup`

**Vaktlistemodulen hadde ingen backup i det hele tatt.** Korps, mannskap med
telefon, e-post og ISSI, kompetanser, ressursgrupper og -roller, ressursene,
vaktpostene, vaktlistene og belastningsgrensene lå utenfor alle fire filer siden
appen gikk i prod 11. september. Det er samme feil oppdragsmodulen hadde fram
til sin fase 7, og den er ikke synlig noe sted før dagen man trenger filene.
`vaktliste/backup.py` dekker den nå, med bruker-FK-ene strippet — `Mannskap.user`
er domenedata lederen setter på nytt, mens en slettet konto ville tatt hele
gjenopprettingen med seg.

**Portalfila er ny og er den de andre hviler på.** `core.Vakt` og
`ModuleSettings` i én fil, først i rekkefølgen. `Backupplan`, `OffsiteKopi` og
`Notification` er utelatt: de to første er metadata *om* backup, og å laste dem
tilbake ville gjenopplive rader for filer som ikke finnes.

**Slettelista utledes nå topologisk** fra `apps` minus `exclude`, barn før
foreldre, og de fire håndskrevne listene er slettet. Utledningen traff alle fire
og fant den ene kjente feilen: **`Lydvarsel` — gjeldspunkt 3.4 — er dekket uten
at noen måtte huske den.** `SlettelistaDekkerDumpenTests` håndhever at hver
modell som dumpes også tømmes, så feilen ikke kan komme tilbake gjennom en ny
modell eller en ny modul. Én ting måtte håndteres underveis: `apps`-lista kan
peke på enkeltmodeller og ikke bare apper, slik arkivhandlerne gjør, og
utledningen må lese lista på samme måte som `dumpdata` gjør.

**Gjenoppretting i tom base er bevist, ikke påstått.** Alle seks filene lastet i
rekkefølge i en fersk PostgreSQL-base — portal → patients → arkiv → oppdrag →
oppdrag_arkiv → vaktliste — og hver rad kom tilbake. Motprøven er like viktig:
uten portalfila feiler alle tre modulfilene med «Key (vakt_id)=(1) is not present
in table core_vakt», som er nøyaktig hullet `docs/TEKNISK_GJELD.md` §4 beskrev.
`AlleFileneGjenopprettesTests` gjør den samme øvelsen i suiten, så den blir
stående.

Modulen `arkiv` heter nå **«Pasientregistreringsarkiv»**. «Vaktarkiv» sa ikke
hva den er, og oppdrag har sitt eget arkiv ved siden av.

Verifisert: 2582 tester grønne på SQLite og PostgreSQL 16.

---

## 2026-09-13 — Backup fase 2: alt på én side  `#core/backup`

`/portal-admin/backup/` er nå hele backup-flaten. Oversikten, én side per modul
og veien mellom dem er lagt ned.

**Det som var tungvint, målt:** å ta backup av alt kostet fire runder gjennom
tre sider; å gjenopprette kostet fem steg. Nå står standardplanen øverst, og
hver modul er en rad som folder seg ut der den står med plan, knapper og
filliste i samme boks. «Ta backup av alle nå» er én knapp. «Gjenopprett siste»
dekker det man vil i ni av ti tilfeller.

**Gjenopprettingen beholdt sin egen bekreftelsesside.** Den er ikke det som var
tungvint — den er den ene handlingen her som sletter rader, og skal koste et
bevisst klikk. Men den sier nå **hvor mange rader i hvor mange tabeller** som
forsvinner. «Slett og erstatt» er et annet svar når man ser at det gjelder 1 240
rader i ni tabeller.

**Nedlastingsknappene er fjernet helt**, også for modulfilene: backupfilene skal
ikke finnes andre steder enn hos Scaleway eller på Railway. Argumentet mot å
laste ned den hele fila — passordhasher og TOTP-hemmeligheter til en laptop — er
like gyldig for pasientfila, som er en helseopplysningsdump utenfor portalens
kontroll.

**«Verste tilfelle nå»** står øverst, per modul, og er målt mot siste
*vellykkede opplasting til Scaleway* — ikke mot siste fil på volumet. Er volumet
borte, er det bare bucketen som teller, og en linje som leste volumet ville vist
fire minutter mens den virkelige avstanden var to dager. Uten offsite
konfigurert sier kortet det selv framfor å påstå noe det ikke vet.

**Vakthunden har fått flate:** rødt på backup-siden, egen linje på
`/portal-admin/server-status/` ved siden av cron-jobbene (ikke blant dem — klokka
er ingen cron-jobb), og et varsel til global admin. Varselet sendes **bare fra
reservenettet i middlewaren**, aldri fra tråden: et varsel om at klokka er død,
sendt av klokka, er et varsel som aldri kommer. Reservenettet kjører i en
forespørsel, altså i live, og oppdager derfor nettopp det tråden ikke kan melde
om seg selv. Det varsler heller ikke om planer som aldri er vurdert — «har aldri
kjørt» og «har sluttet å kjøre» er to tilstander, og bare den andre er en feil.

**Funn underveis, fanget av et skjermbilde og ikke av suiten:** `{# … #}` er en
**enlinjes** kommentar i Django. Strekker den seg over flere linjer, rendres den
som tekst midt i grensesnittet — malen er gyldig, testene passerer, ingenting
logges. Den sto både i den nye malen og i `templates/accounts/user_form.html`
fra før. Begge rettet til `{% comment %}`, og
`patients.tests.FlerlinjesMalkommentarTests` skanner nå alle maler så den ikke
kan komme tilbake.

Verifisert: 2563 tester grønne på SQLite og PostgreSQL 16, og siden er kjørt i
Chromium — lagring av standardplan og modulplan, et avvist intervall med lesbar
melding, «ta backup av alle» og gjenopprettingsbekreftelsen.

---

## 2026-09-13 — Backup fase 1: `Backupplan`, og klokka ut av trafikken  `#core/backup`

Første kode i omleggingen (`docs/PLAN_BACKUP_OMLEGGING.md` fase 1).

**`core.Backupplan` erstatter `ModuleBackupConfig`.** Tre moduser — av, ved
endring, alltid — og intervallet settes **fritt i minutter, timer eller døgn**,
der det før var et nedtrekk med sju faste valg. Enheten lagres slik den ble
valgt: «3 døgn» skal ikke leses tilbake som «4320 minutter». `behold` er cap på
filer på volumet, og gjelder like mye for moduler som for hele basen når den
kommer. En standardplan modulene arver gjør tre tall av atten.

**Modusen «alltid» er ny og er poenget med runden.** «Ved endring» skriver ikke
når innholdet står stille, og er dermed *stum*: ingen ny fil kan bety «ingenting
har endret seg» eller «jobben er død». `create_backup` fikk `hopp_over_like`, så
«alltid» skriver uansett og et hull i rekka er en synlig feil. I tillegg bærer
planen nå **to** tidsstempler — `sist_sjekket_at` ved hver vurdering,
`sist_fil_at` bare når noe faktisk ble skrevet — og det er de to som gjør at
«stille» og «stoppet» kan skilles i alle moduser.

**Klokka er flyttet ut av trafikken og inn i en tråd.** Fram til nå var
`BackupSchedulerMiddleware` den eneste utløseren, så uten forespørsler ble det
ingen backup — og mellom vaktene står portalen stille. Tråden starter fra
`CoreConfig.ready()` og tikker hvert minutt uavhengig av trafikk, med jitter så
gunicorn-arbeiderne ikke banker samtidig, samme radlås som før, og opprydding av
foreldreløse filer ved oppstart. Middlewaren står igjen som reservenett gjennom
samme funksjon.

**Og den er en tråd, ikke en cron-tjeneste, fordi volumet bare kan henge på én
tjeneste.** En cron-tjeneste som tok backup ville skrevet fila til sitt eget
flyktige containerfilsystem og etterlatt en `Backup`-rad uten fil — og
`core.arkiv.har_backup_etter()` spør bare etter raden, så **kollapssperra ville
åpnet seg på spøkelsesbackuper**. Det var flaks at `db_backup` aldri ble satt
opp i Railway (bekreftet av André: bare `purge_old_logs` og `kollaps_arkiv`
kjører). `db_backup` er tatt ut av `CRON_JOBBER` uten erstatning — server-status
viste «Aldri» for en jobb som aldri kom, og et varsel som alltid står rødt lærer
deg å ikke se på dashbordet. `CLAUDE.md` er rettet fra tre cron-jobber til to.

**Én regel til det gikk å ta feil av:** forfall måles mot `sist_sjekket_at`, ikke
mot `sist_fil_at`. Målt mot siste fil ville en plan i «ved endring» vært forfalt
ved hvert eneste tikk etter første «uendret» — altså serialisert hele modulen
hvert minutt for å bekrefte stillstand. Intervallet sier hvor ofte vi ser etter,
ikke hvor ofte vi lykkes.

`backup_kjor` er ny manuell inngang (`--status`, `--alle`, `--modul`), og
`klokke.vakthund()` melder planer som ikke er vurdert på tre ganger intervallet
— svaret på at en tråd ikke er synlig i Railways grensesnitt slik en cron-jobb
er. Flata for den kommer i fase 2.

Migrasjonen er delt i **tre** (skjema, data, skjema) framfor å tømme triggerkøen,
så `cannot ALTER TABLE … because it has pending trigger events` ikke kan oppstå.
Eksisterende rader settes til «egen plan» og beholder oppførselen sin: å la dem
arve standarden ville endret hvor ofte prod tar backup uten at noen ba om det.

Verifisert: 2557 tester grønne på SQLite og på PostgreSQL 16,
`verifiser_migrasjoner` OK, og en oppgraderingssimulering mot ekte PostgreSQL
der fire rader i historisk form — inkludert en modul admin hadde slått av — ble
migrert fram og kom ut med oppførselen i behold.

---

## 2026-09-13 — Backup-planen versjon 3: klokka blir en tråd, ikke en cron-jobb  `#core/backup`

Ingen kodeendring. På spørsmål om cron er den ideelle klokka ble fire alternativer veid,
og svaret er nei — av en grunn som først ble synlig da filene ble fulgt til der de
skrives.

**Et Railway-volum kan bare henge på én tjeneste.** `/data` henger på web-tjenesten. En
cron-tjeneste som kjørte `backup_kjor` ville serialisert riktig, skrevet fila til sitt eget
flyktige containerfilsystem, opprettet `Backup`-raden, og forsvunnet med fila. Raden ville
blitt stående og påstått at det finnes en backup. Og `core.arkiv.har_backup_etter()` —
sperra som skal hindre at et arkiv kollapser uten at slettingen er gjenopprettbar — spør
bare etter raden, ikke etter fila. **Kollapssperra ville altså åpnet seg på
spøkelsesbackuper.** Det var flaks at `db_backup` aldri ble satt opp i Railway.

De to jobbene som faktisk står der, rører bare databasen og trenger ikke volumet. Det er
hele forskjellen.

Klokka blir derfor en daemon-tråd startet fra `CoreConfig.ready()`, i prosessen som
faktisk eier volumet: ett tikk i minuttet, jitter så workerne ikke banker samtidig, samme
radlås som før, og den starter ikke under test eller `migrate`. Web-tjenesten står oppe
mellom vaktene — lavkostnad-modus er én worker uten Redis, ikke en pauset tjeneste — så
klokka går hele året. `backup_kjor` beholdes som manuell inngang, `db_backup` går ut av
`CRON_JOBBER` uten erstatning, og `CLAUDE.md` rettes fra tre cron-jobber til to.

Innvendingen mot en tråd er at den ikke er synlig noe sted. Svaret er en vakthund: er en
plan ikke sjekket på tre ganger intervallet, står det rødt på begge adminsidene og det
opprettes et varsel. Cron er riktig verktøy for å *sjekke* og feil verktøy for å *gjøre* —
en ren vakthund-cron kan komme senere, siden den bare leser databasen og dermed overlever
at web-tjenesten ligger nede.

**Nedlasting fjernes helt**, også for modulfilene: filene skal ikke finnes andre steder enn
hos Scaleway eller på Railway. Knappen ble bare brukt til å se hva som er inni en fil, og
den jobben gjør `verifiser_backup` bedre, på serveren. Argumentet mot å laste ned den hele
fila — passordhasher og TOTP-hemmeligheter til en laptop — er like gyldig for pasientfila,
som er en helseopplysningsdump utenfor portalens kontroll.

Bucketen heter `sanitetsportalen`, og står nå i instruksen og runbooken. Planen har ingen
åpne punkter.

---

## 2026-09-13 — Backup-planen versjon 2: svarene innarbeidet  `#core/backup`

Ingen kodeendring. André svarte på de fem spørsmålene, og planen er skrevet om.

**Intervallet settes fritt i minutter, timer eller døgn**, med enheten lagret slik den ble
valgt — «3 døgn» skal ikke leses tilbake som «4320 minutter». Cap på antall filer gjelder
både moduler og hel database, med standard: moduler ved endring hvert 10. minutt og cap
50, arkivene hver 6. time, hel base alltid hver 24. time og cap 7.

**Tilpasning til den enkelte vakt løses med modusen, ikke med to intervaller.** «Ved
endring» med kort intervall er vaktadaptiv av seg selv: under vakt endres dataene hele
tiden og det skrives en fil hvert intervall, mellom vaktene skrives ingenting. To
intervaller med automatisk omslag ble vurdert og lagt bort — `Vakt.er_aktiv` står på til
noen avslutter vakta, vaktlistas driftsflagg ville vært feil vei i avhengighetene, og en
manuell vaktbryter er den man glemmer å slå av.

**Siden viser hva som faktisk står på spill:** «verste tilfelle nå» per modul, målt mot
siste *vellykkede offsite-kopi* og ikke mot siste fil på volumet. Er volumet borte, er det
bare bucketen som teller, og en linje som leser volumet ville vist fire minutter mens den
virkelige avstanden var to dager.

**Gjenoppretting får en CLI-vei.** Den finnes ikke i dag: `hent_offsite` henter og
dekrypterer, men skriver «gjenopprett fra /portal-admin/backup/». Ny `gjenopprett`-kommando
med `--list`, `--full`, `--hent` og `--ja` — flagget er nødvendig, ikke bekvemt, fordi
`railway ssh` kjører uten interaktiv terminal.

**To fakta fra André som endrer planen:** `db_backup` står **ikke** i Railway, så prod har
aldri hatt en klokkedrevet backup — alt som er tatt, er utløst av web-trafikk. Og
livssyklusregelen i bucketen står på 730 dager med scope «alle objekter», så den må
snevres inn til `backups/` før 90-dagersregelen på `full/` legges til, og det må skje før
den første hele backupen lastes opp.

Ett spørsmål står igjen: skal den hele fila kunne lastes ned fra nettleseren. Anbefaling
nei — nedlasting og gjenoppretting er ulike ting, og bare den ene flytter portalens
legitimasjon til en laptop.

---

## 2026-09-13 — Backup-omleggingen planlagt: `docs/PLAN_BACKUP_OMLEGGING.md`  `#core/backup`

Ingen kodeendring. Bestillingen var at modulenes backup og gjenoppretting er tungvint, at
intervallet skal kunne settes fritt med valget mellom konsekvent lagring og lagring ved
endring, at det samme skal gjelde en hel databasebackup, og at oppbevaringstidene i
Scaleway skal skilles: 90 dager for hele basen, 730 for modulene.

Planen i sju faser: `core.Backupplan` med tre moduser og fritt intervall erstatter
nedtrekket med sju valg, en standardplan modulene arver, og `backup_kjor` som
Railway-cron blir klokka. Én side i stedet for en side per modul. `get_restore_models()`
utledes topologisk, med test som krever dekning. Hel backup med `flush` + `loaddata` og
eget prefiks `full/`. `verifiser_backup` laster de nyeste filene i en engangsbase, fordi
en backup ingen har gjenopprettet er en hypotese.

Tre funn under lesingen av koden: **klokka er trafikk** — uten forespørsler tas ingen
backup, så «konsekvent lagring hvert tidsintervall» er ikke mulig med dagens mekanisme;
**`db_backup` er en felle** — den står i `CRON_JOBBER` og `CLAUDE.md` sier den er én av
tre Railway-jobber, men tabellen i TODO lister to, og kommandoen går uansett gjennom det
nedlagte `patients/backup_service.py` og tar bare pasientmodulen; og **`restore_models`
vedlikeholdes for hånd**, som er sykdommen bak gjeldspunkt 3.4.

Rekkefølgen komprimering → kryptering står fast, mot bestillingens «kryptering og så
komprimering»: chiffertekst lar seg ikke komprimere, mens gzip på dumpdata-JSON typisk
gir 5–15 % av rå størrelse. Dagens kode gjør det riktig allerede.

---

## 2026-09-13 — Strategisk plan for rekkefølgen: `docs/PLAN_REKKEFOLGE_2026-09.md`  `#core/dokumentasjon`

Ingen kodeendring. På spørsmål om hva som bør tas først av teknisk gjeld, backup,
datteroppdrag og statistikk-utvidelsen: **backuphullene først** (vaktlista er udekket og
offsite-kopiene kan ikke gjenopprettes i tom base), **så flyttingen ut av `patients`**
(med gjenopprettbar backup foran migrasjonen), så hel backup og dokumentrunden. De to
funksjonene står etter: begge er blokkert på avgjørelser fra André, og oppdragsmodulen
har ikke hatt sin første skarpe vakt. Notatet begrunner avviket fra `BACKUP.md` §3 (det
som ikke rører `AppSetting` kan bygges før flyttingen), anbefaler å beholde tabellnavnene
ved flyttingen, og at statistikk-utvidelsen bygges som A- og B-nivå med F4-lasttest før,
og lar C/D vente. TODO har fått en henvisning under «Teknisk gjeld».

---

## 2026-09-13 — Forslag: datteroppdrag, og `docs/` ryddet  `#core/dokumentasjon`

Ingen kodeendring. `docs/FORSLAG_DATTEROPPDRAG.md` er et idénotat (ikke besluttet):
ett oppdrag deles i datteroppdrag, ett per pasient — `Oppdrag.forelder` med dybde låst
til ett nivå, pasientantall bare på bladene, `forelder_nummer` i arkivet bare når satt.
Hva det gir i loggen og statistikken, hva det koster, og det ene spørsmålet
sentralbordet må svare på først. Står i TODO under «Ideer».

`docs/` gjennomgått: `DATAIMPORT_FRA_GAMMEL_PROD.md` (utført 22. aug.) og
`OPPSETT_KOLLAPS_CRON.md` (jobben har gått siden 22. aug.) er flyttet til
`docs/archived/` med indekslinjer, og lenkene til dem oppdatert. Beslutningsnotatene
blir stående — de forklarer hvorfor. `DEPLOY_GUIDE.md` og `TEKNISK_DOKUMENTASJON.md` er
utdaterte, men aktive, og står i dokumentrunden i TODO.

## 2026-09-13 — Backup-planen: `docs/BACKUP.md`  `#core/backup`

Ingen kodeendring. Besluttet: **to lag med hver sin frist** — en hel backup (alt unntatt
sesjoner, kryptert, 90 dager, få filer) som katastrofekopi, og modulfilene som i dag med
730 dager, fordi kollapsen krever dem. Portalfil med `Vakt` og innstillingene,
`vaktliste`-handler, og en test som gjenoppretter alle filene i en tom database.
Slettefristene er begrunnet mot A.9 (egen kategori, forholdsmessig, slettingen kjøres
på nytt etter gjenoppretting). Rekkefølgen er bindende: flyttingen ut av `patients`
først. Dokumentrunden etterpå tar med alt fra 11.–13. september — lista over hva som
mangler hvor står i §5, og i `TODO.md`.

## 2026-09-13 — Teknisk gjeld kartlagt: `docs/TEKNISK_GJELD.md`  `#core/dokumentasjon`

Ingen kodeendring. På spørsmål om hva backupene faktisk inneholder, og hvordan appen
henger sammen, ble appene, modellene, importene på kryss, middlewaren og rutene gått
gjennom. Notatet beskriver rammeverk-pluss-moduler-tanken, den store gjelden —
`patients` er den gamle monolitten, og `core` avhenger av den (`AppSetting`, `Backup`,
`hent_aktiv_vakt`, CSP, `healthz`, server-status) — åtte mindre punkter, og hullene i
backupen: `core.Vakt` ligger ikke i noen fil (gjenoppretting i tom base feiler),
vaktlista har ingen handler, og «Vaktarkiv» skal hete «Pasientregistreringsarkiv».
Arbeidslista står i `TODO.md` under «Teknisk gjeld», med bindende rekkefølge:
flyttingen først, backupene etterpå.

## 2026-09-13 — Prodtest av sikkerhetsrundene: fire funn rettet  `#core/sikkerhet`

Ingen migrasjon. Andrés prodtest på staging av runde 1 og 2 ga 39 OK og 0 FEIL i
scriptet, og fire ting på sidene:

- **Fanikonet er merket på blått igjen** (`logo.svg`, samme fil som PWA-ikonet).
  Den lyse utgaven uten bakgrunn fra 12. sep. er tatt bort («Jeg bruker mørk modus
  og det er en mørk blå bakgrunn som var der før. Jeg vil ha det slik det var.»).
  `Clear-Site-Data` står på 302-svaret fra «Logg ut» og var riktig — det er
  innloggingssiden DevTools viser etterpå.
- **Sentralbordet ved første besøk** (3.1): «Laster…» sto tomt. Oppstarten var fire
  kall på rad uten feilhåndtering — feilet ett, tegnet ingen noe, og pollingen ble
  aldri satt. `oppstart()` tegner nå listene uansett («Kunne ikke hente lista —
  prøver igjen om 30 sekunder» til første henting lykkes; tom og ikke hentet er to
  ulike ting), og `setInterval` står i `finally`.
- **Bilen: «venter på dekning» først etter 3 sekunder** (3.4). Trykket legges i
  køen før det sendes, og meldingen kom opp i det halve sekundet sendingen tok —
  også med full dekning. `visUsendt()` venter til eldste rad i køen er
  `USENDT_VENTETID_MS` gammel, og kommer tilbake av seg selv når fristen er ute.
- **Korps-føreren uten badge** (4.1): admin koblet fra hennes egen mannskapsrad, og
  sida sa «Mannskapsregisteret er tomt» — meldingen leste lista over dem hun får
  *sette* (tom uten badge), ikke registeret hun *ser* (alle korps). Nå leser den
  registeret (`registeretErTomt`), og sida sier hvorfor hun ikke får redigere:
  «Kontoen din er ikke knyttet til et korps. Du ser alle korps, men kan bare føre
  ditt eget» (`mangler_badge`). Varselet fantes bare for `les`.
- **E-postkoblingen er leder og global admin** (M5, snevret): `skriv_full` lagrer
  e-posten uten å koble, som korps-føreren. Den som bemanner skal ikke velge
  hvilken konto som blir hvem; merket sier at kontoen finnes, og lederen kobler.
  `tests_registre` og `tests_sikkerhet_runde1` bruker `skriv_leder` der de
  forutsatte kobling.

Tester: `oppdrag/tests_prodtest_13sep.py` (oppstarten og fristen, i node) og
`vaktliste/tests_prodtest_13sep.py` (badge-varselet, koblingen, `registeretErTomt`).

## 2026-09-13 — Sikkerhetsgjennomgangen, runde 2: 9 funn rettet  `#core/sikkerhet`

Ingen migrasjon. Numrene viser til `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.

- **H3 — bibliotekene inn i repoet.** Bootstrap 5.3.2, Bootstrap Icons 1.11.3,
  Tabulator 6.2.5 og Chart.js 4.4.2 ligger under `static/vendor/` (fra npm,
  uten kartreferanser, med lisens og `README.md` om oppdatering) og serveres av
  WhiteNoise. Alle tretten malene peker dit. CSP-en har ingen verter lenger:
  `script-src 'self' 'nonce-…'`, `style-src 'self' 'unsafe-inline'`,
  `font-src 'self' data:`. Service-workerens CSP er `'self'`, `CDN`-lista er tom
  og `VERSJON` bumpet til `vl-sw-4`. `tests_security_headers` krever at ingen mal
  laster fra et CDN.
- **M12 — trust-cookien** signeres med egen `salt` og bærer et passordavtrykk:
  bytter eller nullstilles passordet, må enheten godkjennes på nytt. Cookies
  fra før i dag avvises, så alle med «stol på denne enheten» tar MFA én gang til.
- **M13** — passordskjemaene får brukeren, så «kan ikke ligne brukernavnet»
  håndheves. **M14** — hasheren kjøres også for låste kontoer, og «kontoen er
  låst» vises bare for den som har riktig passord; alle andre får «feil
  brukernavn eller passord». Låsen i seg selv er uendret (5 feil, 15 min) — den
  er det ene vernet som ikke hviler på cachen.
- **M15** — `LocMemCache` går fra 200 til 5000 poster. **L1** —
  `SlankReporterFilter` skjuler alle cookies i Djangos reserve-feilrapport
  (`DEFAULT_EXCEPTION_REPORTER_FILTER`).
- **M16 — avhengighetene er låst.** `requirements.in` bærer ønskene,
  `requirements.txt` er `pip-compile --generate-hashes --strip-extras` (25
  pakker, 471 hasher). `pip-audit`: ingen kjente sårbarheter. Railway
  installerer nå nøyaktig det som er testet.
- **L13** — `@rate_limit` på resten av skriveendepunktene: verdimengdene,
  bilinnstillinger, arkivering og sletting i begge arkiver, vaktlistas detalj-
  PUT/DELETE (vaktliste, gruppe, ressurs, vaktpost, mannskap, registre),
  pasientregistrene, backup run/restore, arkiv-statistikk, brukeradmin.
  Eksisterende bremser dekker nå også DELETE der den fantes.
- **L14** — `admin_required` merker viewet, og `core/tests_sikkerhet_runde2.py`
  går gjennom alt under `/portal-admin/`, `/varsler/`, `/api/varsler/` og
  `/min-profil/` med anonym og vanlig bruker.
- 19 nye tester i `*/tests_sikkerhet_runde2.py`.
- **Rettelse samme dag:** `.gitignore` hadde `vendor/`, så bibliotekfilene ble aldri
  commitet, og første deploy til staging ga 500 på alle sider («Missing staticfiles
  manifest entry»). `!static/vendor/` i `.gitignore`, og en test som krever at filene
  er sporet av git.

## 2026-09-13 — Sikkerhetsgjennomgangen, runde 1: 19 funn rettet  `#core/sikkerhet`

Ingen migrasjon. Numrene viser til `docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`.

- **H1 — data inn i `<script>` escapes.** `core/jsdata.js_json()` bytter `<`, `>`
  og `&` med `\u003c`/`\u003e`/`\u0026` som Djangos `json_script`; de fjorten
  variablene på `/oppdrag/` går gjennom den, og malene har ikke lenger `|safe`.
  Et problemstillingsnavn kan ikke lukke skriptet.
- **H2 — klient-IP ett sted.** `core/klientip.klient_ip()` tar *siste* ledd i
  `X-Forwarded-For` (Railway er én betrodd proxy), validerer det, og faller
  tilbake til `REMOTE_ADDR`. Brukt av innloggingsloggen, alle tre audit-signalene,
  begge arkivviewene, sesjonsverktøyet og — som `ratelimit_nokkel` — bøttene
  `login:ip` og `reset:ip`, som fram til nå talte på proxyens adresse.
- **H4 — «Logg ut» rydder drifts-PC-en.** `logout_view` sender
  `Clear-Site-Data: "cache", "storage"` (Cache Storage, localStorage og
  service-workeren i ett; cookies røres ikke). Workeren serverer heller ikke en
  datakopi eldre enn 24 timer (`erForGammel`), og sletter den.
- **M1** — riktig passord nullstiller ikke kontolåsen for kontoer med MFA; det
  skjer først når koden er bestått. **M2** — innloggingsskjemaet valideres før
  noe skrives (et brukernavn over 64 tegn ga 500 på PostgreSQL). **L5** —
  MFA-stegene krever aktiv konto. **M11** — `current_session_key` skrives etter
  at passordbyttet har rotert sesjonen. **L11** — sidene med midlertidig passord
  har `never_cache`.
- **M7** — «Rediger» kan ikke ta admin-rollen fra deg selv (`_kan_degraderes`),
  og `is_active` er ute av skjemaet: frys/tø er veien som logges og dreper
  sesjoner.
- **M3** — besetningsendepunktet krever at man ser alle korps eller har
  `oppdrag:les`; en ren `vaktliste:les` får 403. **M5** — e-postkoblingen
  utløses bare av admin og `skriv_full`+; korps-føreren lagrer e-posten, og
  merket sier at kontoen finnes.
- **M4** — bilens detalj-, stemplings-, grovsorterings- og antall-endepunkt
  følger 30-minuttersvinduet (`_synlig_for_bilen`). **M6** — enhetskontoer får
  403 på enhetslista, flytting og verdimengdene.
- **M8** — de tre JSON-parserne gir tom dict for gyldig JSON som ikke er et
  objekt. **M9** — audit-CSV prefikser `=`, `+`, `-`, `@`, tab og CR med `'`.
  **M10** — `nivaa_for(admin)` er toppen av stigen (`skriv_leder`), ikke
  `skriv_full`. **L2** — `patient_detail_view` er scopet til aktiv vakt.
  **L3** — `offsite.hent` avviser objektnavn med katalogskilletegn før S3
  kalles. **L10** — `ALLOWED_HOSTS` strippes, og `SECRET_KEY` under 50 tegn
  stopper oppstarten når `DEBUG=False`.
- 46 nye tester i `*/tests_sikkerhet_runde1.py`; `tests_besetning` oppdatert
  til den nye regelen.

## 2026-09-13 — Sikkerhetsgjennomgang: rapport  `#core/sikkerhet`

`docs/SIKKERHETSGJENNOMGANG_2026-09-13.md`. Statisk gjennomgang i fire deler, hvert
funn verifisert mot koden. Ingen kritiske. Fire høye: lagret JS-injeksjon gjennom
verdimengdene i oppdrag (`json.dumps` + `|safe`, og CSP-vertslista slipper det gjennom),
klient-IP lest på tre ulike måter (rate-limit per IP teller på proxyen, auditsporets IP
er klientstyrt), CDN uten SRI, og service-workerens kopi av mannskapsregisteret som
ingenting rydder ved utlogging. Seksten middels, 22 lave, og en foreslått rekkefølge i
tre runder. Ingen kode er endret i denne commiten.

## 2026-09-13 — Sikkerhetssjekk utenfra: `scripts/sikkerhetssjekk.py`  `#core/sikkerhet`

**Rettelse etter første kjøring mot staging:** Cloudflare sender hodenavn med små
bokstaver (`location`), og WhiteNoise hasher `oppdrag-enhet.js` — scriptet meldte 65
falske FEIL. Hodene normaliseres nå, og enhetsskjermen gjenkjennes på navnet uten hash.

Et script som kjøres fra en PC mot staging (runbook §14). Bare standardbiblioteket.
Anonymt: HTTPS-omdirigering, HSTS, CSP, X-Content-Type-Options, rammesperre,
Referrer-Policy, cookieflagg, 64 sider og API-er som skal være stengt uten
innlogging, 14 skriveendepunkter uten CSRF, rate-limiting på innlogging, egen
404, Django-admin og kjente filer. Med `--admin/--leser/--enhet`: rollegrensene,
sesjonsfiksering, utlogging med POST, at gammel sesjons-ID dør, og konfigsjekken
fra server-status. Kjørt lokalt mot en dev-server som kontroll av selve scriptet.

## 2026-09-13 — Rate-limiting var av i prod: `RATELIMIT_ENABLE=true` ble lest som False  `#core/sikkerhet`

Funnet av konfigsjekken på server-status, første kvelden den var oppe: kortet sa
`RATELIMIT_ENABLE: False`, Railway sa `true`. `settings.py` leste variabelen med
`== 'True'` — stor T — mens README, runbook og Railway skrev `true`. Dermed har
rate-limitingen på innlogging, MFA og API-ene vært **av** i prod så lenge
variabelen har stått slik.

- `_env_bool(navn, default)` i `settings.py` leser boolske variabler uavhengig
  av store og små bokstaver (`1/true/yes/on/ja` er ja, alt annet nei, tom eller
  manglende gir default). Brukes for `DEBUG`, `RATELIMIT_ENABLE` og
  `EMAIL_USE_TLS` — alle tre hadde samme feil. `DEBUG=true` ga False, som var
  ufarlig; `EMAIL_USE_TLS=true` ga False, som ville skrudd av TLS mot SMTP
  (brukes bare lokalt).
- `myproject/tests_env_bool.py` låser regelen.
- Ingen migrasjon. Etter deploy skal konfigsjekken vise `RATELIMIT_ENABLE: True`
  uten at noe endres i Railway.

## 2026-09-13 — Server-status: ni nye mål på /portal-admin/server-status/  `#core/drift`

Ingen migrasjon. Gjennomgangen av dashbordet etter reserve 3 fant at det målte
serveren, men ikke det serveren er til for, og at ett tall var galt.

- **Minne viste toppen, ikke nå.** `ru_maxrss` går aldri ned, så kortet kunne
  bare stige. Nå leses RSS fra `/proc/self/status`, med toppen som egen rad.
- **Offsite-kopien** står i backup-kortet: konfigurert/ikke, antall filer, sist
  lastet opp, siste feil. Rødt når siste opplasting feilet, gult over ett døgn.
- **Disk på volumet** (`BACKUP_DIR`): brukt/ledig og hvor mye backupfilene tar.
- **Database:** svartid på `SELECT 1`, og på PostgreSQL tilkoblinger mot
  `max_connections` — feilen som kommer først når `WEB_WORKERS` skrus opp.
- **Vaktbildet:** aktiv vakt, vaktlister i drift, oppdrag på tavla, ventende,
  «trenger ressurs» med eldste ventende i minutter, og siste vaktlistefil.
- **Tregeste stier siste 5 min** — P95 per sti, under tre treff utelatt
  (`metrics_store.tregeste_stier()`), så «P95 er høy» blir «det er den siden».
- **Konfigsjekk:** DEBUG, RATELIMIT_ENABLE, HTTPS, ALLOWED_HOSTS,
  CSRF_TRUSTED_ORIGINS, cache, e-posttransport, ADMINS, offsite — hver rad ✓/✗,
  pluss versjon. Reglene er prods; lokalt står DEBUG og HTTPS rødt med vilje.
- **Innlogging siste time:** feilede forsøk, hvor mange brukernavn og IP-er de
  kom fra, avviste MFA-koder. Én IP bak fem feil markeres rødt.
- **Cron-jobbenes siste kjøring** — jobbene registrerer seg selv via
  `lesbar_dbfeil(..., navn=...)` → `AppSetting['cron.<navn>']`, ok eller feil
  med melding (`core.kommando.registrer_kjoring`/`siste_kjoringer`). Gult når
  `db_backup`/`purge_old_logs` er over 26 timer gamle, `kollaps_arkiv` over 8
  døgn. «Aldri» til jobben har kjørt én gang etter denne deployen.
- **E-post:** transporten (AHASend/SMTP/konsoll) og siste vellykkede og feilede
  utsending av vaktlistefila. Ingen prøvesending fra et kort som polles hvert
  10. sekund.
- Hver innhenter tåler at delen den leser er nede — kortet viser feilen, siden
  viser resten. Payloadnøkkelen `memory_mb` er byttet ut med `memory.naa/topp`.
- **Feature-flagg-kortet er fjernet**, med `feature.live_stats_enabled`,
  endepunktet `/portal-admin/server-status/flag/` og testene (André: «Den
  trenger vi ikke»). Funksjonen det skulle styre ble aldri bygget. Runbook §6
  står som «utgått» så §7 og oppover peker riktig.
- Verdiene i konfigsjekken brekker inne i kortet (`overflow-wrap: anywhere`,
  høyrestilt) i stedet for å gå utenfor — gjelder alle `status-row`-verdier.

## 2026-09-13 — Runbook §8b: offsite-backup — oppsett, kontroll og gjenoppretting  `#core/backup`

Dokumentasjon. Oppsettet hos Scaleway og i Railway, kontrollen før hver vakt,
og gjenopprettingen med `hent_offsite`, inn i `docs/RUNBOOK_VAKT.md` som §8b.
10a og lenketabellen peker dit.

## 2026-09-13 — Reserve 3: backupene ut av Railway, til Scaleway  `#core/backup`

Én migrasjon, `core/0007` (`OffsiteKopi`). To nye avhengigheter: `boto3` og
`cryptography`. Inert uten variablene — bare prod skal ha dem.

- **Hver ny backup-fil lastes opp til Scaleway Object Storage**, kryptert
  før den forlater Railway (AES-256-GCM, nøkkel avledet av
  `OFFSITE_BACKUP_KEY`). Henger på at `create_backup` faktisk skrev en ny fil;
  hash-skip gir ingen opplasting. Ingen egen klokke.
- **Kaster aldri:** feiler bucketen, står backupen på volumet som før, og
  raden `OffsiteKopi` bærer feilen. Kortet «Offsite-kopi (Scaleway)» øverst på
  /portal-admin/backup/ viser status, siste opplasting og siste feil.
- **Gjenoppretting:** `python manage.py hent_offsite --list` og
  `hent_offsite <filnavn>` henter, dekrypterer og legger fila i `BACKUP_DIR`
  med en `Backup`-rad, så den kan gjenopprettes fra backup-siden.
- Variabler: `OFFSITE_S3_BUCKET`, `OFFSITE_S3_REGION`, `OFFSITE_S3_ENDPOINT`,
  `OFFSITE_S3_ACCESS_KEY`, `OFFSITE_S3_SECRET_KEY`, `OFFSITE_BACKUP_KEY`.
- Scaleway inn i personverndokumentasjonen A.2 som databehandler, med DPA.

## 2026-09-13 — Reserve 2 og 4: offline drift på /vaktliste/, gammel offline-modus lagt ned  `#vaktliste/offline`

Ingen migrasjon. Deployes til staging først; testes i Chrome/Edge på PC.

- **Service worker for `/vaktliste/`** (`static/js/vaktliste-sw.js`, servert av
  `/vaktliste/sw.js`): holder siden, stilene, skriptene og siste svar fra
  vaktliste-API-et lokalt. Svarer ikke serveren, vises kopien, med banner «viser
  lista slik den var kl …». Innloggingssiden lagres aldri som kopi.
- **Møtt/av vakt i kø** når serveren ikke svarer: stemplingen vises som satt
  (merket), legges i `localStorage` med tida trykket skjedde, og sendes i
  rekkefølge hvert 15. sekund og når nettet kommer tilbake. Serveren tar
  tidspunktet fra køen (`stempling/` leser `tidspunkt` i kroppen;
  `services.vurder_klienttid` klipper urimelige). Et trykk serveren avviser
  fjernes med beskjed.
- **Utgått innlogging** stopper køen og sier fra i banneret; den sendes etter
  ny innlogging i en annen fane.
- **«Klar for offline»** i vaktlinja når workeren styrer siden og lista ligger i
  kopi — sjekket, ikke antatt.
- **Den gamle offline-modusen er lagt ned:** `OFFLINE_MODE`, CSRF åpen for LAN,
  `ALLOWED_HOSTS=*`, Django-admin under offline, `create_offline_users`,
  `.env.offline.example`, `OFFLINE_PASSORD.md` og USB-pakken. Django-admin
  rutes nå bare under `DEBUG`. `import_offline_data` står igjen som
  importverktøy for den gamle appens SQLite. Dokumentasjonen (teknisk §11,
  personvern A.11, runbook) er skrevet om til den nye reserven.

## 2026-09-13 — Reserve 1b: intervallsending mens lista er i drift  `#vaktliste/offline`

Én migrasjon, `vaktliste/0017` (`Utsending.innhold_sha256`, ny utløser
«intervall»). Deployes til staging først.

- **Send på nytt hvert N. minutt mens lista er i drift**, satt under
  Portalinnstillinger → «Vaktlista på e-post». 0 = av. Klokka går fra forrige
  utsending uansett hva som utløste den, så et feilet forsøk gir ikke ett nytt
  per minutt mens e-posten er nede.
- **«Bare hvis vaktlista er endret siden forrige utsending»**: fila får en
  signatur over innholdet, og en uendret liste går ikke ut igjen. Stemplene
  (møtt/av vakt) står ikke i fila og teller ikke som endring.
- Kjøres av `vaktliste.middleware.FilutsendingMiddleware` etter trafikk, maks
  én sjekk i minuttet per prosess, i bakgrunnstråd — samme klokke som
  backup-planleggeren. Tas ut under test, som den.

## 2026-09-12 — Reserve 1: vaktlista som fil på e-post

Én migrasjon, `vaktliste/0016` (`Utsending`). Deployes til staging først.

- **Vaktlista som selvstendig HTML-fil**: grupper, ressurser og skift med korps,
  rolle, telefon og ISSI. Ikke e-post, notat eller merknad. Åpner uten nett og
  skrives ut fra nettleseren. «Last ned som fil» og «Send på e-post» i
  «Innstillinger» på vaktlista, for `skriv_full`.
- **Sendes automatisk ved «Sett i drift»** når admin har slått det på og satt
  mottakere. Feiler e-posten, åpner innsjekken likevel, og vaktleder får feilen.
- **Mottakere og bryteren** settes av global admin under Portalinnstillinger →
  «Vaktlista på e-post». Adressene valideres før noe lagres.
- **Hver utsending logges**: `Utsending`-rad og auditrad med hvem, når, hvilke
  adresser og antall skift. Teksten i «Innstillinger» sier hva som skjedde sist.
- AHASend-transporten sender vedlegg (base64, v2-formatet). Første vedlegg som
  går gjennom den — bekreftes på staging.
- Vurderingen av ukryptert sending står i vaktlistenotatet §12.

## 2026-09-12 — ISSI på mannskapet, telefon og ISSI i sentralbordets besetning

Én migrasjon, `vaktliste/0015` (`Mannskap.issi`). Deployes til staging først.

- **ISSI** (nødnettsterminalens nummer) på hver person i mannskapsregisteret,
  etter telefon og e-post: kolonne i tabellen, felt i skjemaet, søkbart.
  Tekst, så ledende nuller overlever.
- **Sentralbordets besetning viser telefon og ISSI per person** på koblede
  enheter. Telefonen er en `tel:`-lenke. §6 i vaktlistenotatet er snudd
  for telefon: operatøren skal kunne ringe bilen uten å åpne vaktlista.
  Kompetanse, notat, e-post og konto er fortsatt ikke med.

## 2026-09-12 — Statistikk: chi²-merket bryter på iPhone

Ingen migrasjon. «✗ N.S. (χ²=12.0, p=0,062)» gikk utenfor kortet i
krysstabellene og på obspost; merket får nå bryte, og tittel og merke står
på hver sin linje når det ikke er plass til begge.

## 2026-09-12 — Vaktliste: skift, ressurser og stemplene i auditloggen

Ingen migrasjon. Deployes til staging først.

- **Skift logges på feltnivå** (`vaktliste_vaktpost`): opprettet, hver
  feltendring med gammel og ny verdi, og slettet — med hvem og når.
  Møtt/av vakt og angringene er feltendringer på `mott_at`/`av_vakt_at`, og
  får dermed sitt spor. `merknad` logges som endret, uten verdier, som
  `Mannskap.notat`.
- **Ressurser logges** (`vaktliste_ressurs`): opprettet, endret, slettet.
  Slettes en ressurs, får hvert skift som ryker med sin egen rad.
  Kopiert oppsett går nå én rad om gangen, så kopiene logges.

## 2026-09-12 — Prodtest runde G–I, del 3: iPhone-rettelser

Ingen migrasjon. Deployes til staging først.

- **Alle statistikktabellene ruller sidelengs** på en smal skjerm, i
  pasientfanen som i oppdragsfanen. Beholderne bærer klassen `stats-rull`
  i malen; ingen inline-stiler lenger.
- **Vaktlinja på telefonen:** statusmerket («Planlegging · 12.09 08:00 –
  13.09 20:00») gikk utenfor kortet — spennet bryter nå til linja under
  formen. Vaktvelgeren tar bredden, og «Innstillinger»/«Ny vaktliste» står
  alltid sist på egen linje, så korpsvelgeren ikke havner et sært sted i
  liggende visning.

## 2026-09-12 — Prodtest runde G–I, del 2: lyd per hastegrad, ett trykk, Drift

Én migrasjon, `oppdrag/0025` (`Lydvarsel.aktiv`). Deployes til staging først.

- **Ventevarselet kan slås av per hastegrad** i fanen «Bilen»: en avkryssing
  per rad. Rører ikke pipet ved nytt oppdrag, som ikke er per hastegrad.
- **«Behandlet på sted» lukker med Ledig i samme trykk.** Serveren skriver
  Behandlet og Ledig med samme tidspunkt (`services.behandle_paa_sted`);
  Ledig-meldingen er målt, ikke automatisk, så statistikken teller
  oppdragstiden. Udefinert stopper alt før noe skrives.
- **Drift har ingen grovsortering:** raden i bilen og merket hos operatøren
  er borte for Drift. Serveren krevde den aldri der.
- Statistikk: tabellene ruller sidelengs på iPhone i stedet for å gå ut av
  kortet.

## 2026-09-12 — Prodtest runde G–I: lyd, grovsortering, iPhone

Ingen migrasjon. Deployes til staging først.

- **Lyd på som standard, med dempeikon** i bilen (per enhet, husket lokalt)
  i stedet for «alltid på uten valg». Linja «trykk hvor som helst» er
  dempet tekst, ikke en gul boks, og forsvinner etter første trykk.
- **Admin kan slå lydvarselet av** for alle biler, i fanen «Bilen» i
  «Valglister» (het «Lydvarsel»). Endepunktet heter `api/bilinnstillinger/`.
- **iOS med lydbryteren på stille:** Web Audio dempes av bryteren; bilen
  starter en stum, loopende lydfil ved første trykk og ber om
  «playback»-lydøkt, som er omveien som finnes. Ingen garanti fra Apple.
- **Grovsortering kreves** før «Behandlet på sted» og før Ledig etter
  Leverer — alltid, unntatt på Drift. Før Avreist bare når admin har slått
  det på («Krev grovsortering også før Avreist»). Bilen får beskjeden idet
  hun trykker; serveren avviser uansett.
- Statistikk: «På stedet» heter «Behandlet på stedet».
- iPhone: gruppeoverskriftene i «Nytt oppdrag» tar hele linja igjen.

## 2026-09-12 — Andrés forbedringsliste, del I: lydvarselet

To migrasjoner, `oppdrag/0023` (tabellen `Lydvarsel`) og `0024` (seed med
første utgaves tall). Data og skjema hver for seg. Deployes til staging
først.

- **Lyden er alltid på.** «Lyd av/på»-knappen er borte. Nettleseren krever
  fortsatt et trykk før lyd får spille; en gul linje øverst sier «trykk hvor
  som helst» til det første trykket har vekket den, og et ikon ved klokka
  viser tilstanden.
- **Lengre varsel:** Akutt seks toner på tre sekunder, Haster fire, Vanlig
  og Drift tre rolige. Aldri over tre sekunder.
- **Admin justerer tersklene** per hastegrad — første varsel og gjentakelse
  i sekunder — i ny fane «Lydvarsel» i «Valglister» (bare global admin), og
  om bilen skal pipe når den får et nytt oppdrag. Bilen henter tallene hvert
  femte minutt.
- **Pip ved nytt oppdrag:** to stigende toner når et ventende oppdrag dukker
  opp i bilens liste, ikke for det som lå der da siden åpnet.
- **Utheving hos operatør:** på sentralbordet pulserer raden i gult når et
  oppdrag har ventet forbi første terskel på at bilen skal rykke ut, regnet
  fra da den første ventende bilen ble varslet.

## 2026-09-12 — Andrés forbedringsliste, del H: bilens utganger

Én migrasjon, `oppdrag/0022`: statusvalg og hendelsestyper, og kolonnen
`behandlet_at` på arkivrader. Ren skjemaendring. Deployes til staging først.

- **«Behandlet på sted»** er en ny status fra Fremme: pasienten ble ferdig
  der bilen sto, ingen transport. Neste er Ledig. Statistikken regner tid på
  stedet fram til behandlet, og arkivet får kolonnen — i signaturen bare når
  den er satt, så eldre arkiv verifiserer som før.
- **«Avbryt» i Rykker ut** der Ledig sto: enheten meldes ledig, og oppdraget
  går tilbake til Venter hos sentralen som «trenger ny ressurs», med
  «Avbrutt: HGSD 56» i tidslinjen. Bilen spør om bekreftelse først.
- **Ingen Ledig mellom Avreist og Leverer.** Bilen melder Ledig bare fra
  Leverer og Behandlet, og den egne Ledig-knappen er borte: Ledig er «neste»
  der. Sentralen fører og retter som før, fra alle statuser.

## 2026-09-12 — Andrés forbedringsliste, del G: vaktlista

Ingen migrasjon. Deployes til staging først.

- **«Sett i drift» ligger i «Innstillinger»**, i bolken for lista, med en
  linje som sier hva knappen gjør. Statusmerket i vaktlinja er større:
  ikon, «Planlegging»/«I drift» i fet, og i drift en pulserende grønn prikk.
- **Redigering under drift som i planlegging.** Driftraden er regnearket
  med innsjekken foran — tider, rolle, kompetanse og merknad rettes der de
  står. Tabellen ruller sidelengs på en laptop; stempelet står først.
- **Drift inn og ut står i auditloggen**, på feltnivå med hvem som gjorde
  det (`vaktliste_vaktliste`: status, satt i drift når/av, planlagt slutt,
  arkivert).
- **Knappene med grå kant** (`btn-outline-secondary`, «Innstillinger» m.fl.)
  har lys tekst og portalens kantfarge på alle portalsider.
- **Én innlogging per konto** har stått siden N10 — logger kontoen inn et
  nytt sted, ryker den forrige økta. Nå låst av tester fra utsiden.

## 2026-09-12 — Feilvarsel: `django`-loggeren bruker vår e-posthandler

En skanner (leakix) prøvde `testportal.sanitet.net` mot staging, fikk 400
på hver forespørsel — og hver forespørsel ble en e-post med **full
Settings- og META-dump**, rundt hundre på fem minutter.

- **Årsak:** Django konfigurerer sin egen `DEFAULT_LOGGING` før vår, og en
  logger vi ikke nevner beholder handlerne derfra. `django.request` var
  vår, men `django.security.DisallowedHost` propagerte til `django`, som
  fortsatt hadde Djangos AdminEmailHandler — uten demping og uten den slanke
  rapportøren. Den slanke rapporten var altså bare i bruk for uhåndterte
  exceptions i views.
- **Rettet:** `django` står nå i LOGGING med vår handler,
  `django.security.DisallowedHost` går bare til konsollen (Djangos egen
  anbefaling — feil Host-header er skannere, ikke feil hos oss), og
  e-posthandleren har `require_debug_false` som Djangos.
- Ikke rettet i kode: staging-tjenesten har prods `ALLOWED_HOSTS` og en
  `CSRF_TRUSTED_ORIGINS` med en skrivefeil (`/ https://*.railway.app`). Se
  TODO.

## 2026-09-12 — «Valglister», og fanene i mørkt

- Knappen og vinduet «Verdier» heter **«Valglister»** (André: «noe annet
  bedre beskrivende»), med undertittelen lokasjoner, enhetstyper og
  problemstillinger.
- Fanene i vinduet var Bootstraps lyse: hvit aktiv fane med mørk tekst. De
  følger nå sidens mørke flater.

## 2026-09-12 — Andrés runde på staging, del F: lydvarsel i bilen

Ingen migrasjon.

- **Et ventende oppdrag bilen ikke har rykket ut på, piper.** Akutt etter
  ett minutt og så hvert tiende sekund; Haster etter fem minutter og så
  hvert minutt; Vanlig og Drift etter et kvarter og så hvert minutt. Tida
  regnes fra da *bilen* ble varslet. Lyden lages i nettleseren (ingen fil,
  ingen dekning) og varer under tre sekunder; Akutt har tre toner, Haster
  to, resten én.
- **«Lyd»-knappen øverst på bilskjermen** slår varselet på og av og husker
  valget. Nettleseren krever et trykk før den får spille lyd — er lyden på
  fra før, holder det første trykket hvor som helst på skjermen, og en
  linje under knappen sier det til lyden er vekket.
- Raden pulserer i gult når terskelen er passert, uansett om lyden er på:
  lyd alene overhøres i en bil med sirene.
- Et trykk som ligger usendt i køen teller som svart — da piper det ikke.

## 2026-09-12 — Andrés runde på staging, del E: verdimengdene som tabeller

Tre migrasjoner, `oppdrag/0019`–`0021`: tabellene `Enhetstype` og
`Problemstilling`, seeding fra listene i `choices.py` med oversetting av
`Enhet.type` til FK, og fjerning av det gamle feltet. Delt i tre så
dataskrittet ikke står i samme transaksjon som en skjemaendring
(PostgreSQLs triggerkø). **Kjør `verifiser_migrasjoner` ikke — mønsteret
finnes ikke her — men ta backup før `main`, som alltid.** Eksisterende
enheter beholder typen sin; nye står som «Uten type» til noen setter den.

- **Problemstillinger, enhetstyper og lokasjoner redigeres og sorteres på
  sentralbordet**, i ett vindu med tre faner («Verdier»). Opp/ned flytter
  raden, og rekkefølgen er rekkefølgen i nedtrekkene. Problemstillingene har
  kategori (medisinsk, drift, begge) og om de bærer antall. «Udefinert» er
  fast og står alltid øverst.
- **Oppsettet er `skriv_leder`** — nytt trinn i oppdragsmodulen («Skrive:
  leder (verdimengdene)»). Lokasjonene var `skriv_full` én dag. Sletting er
  fortsatt global admin, og bare for verdier ingenting bruker.
- **Enhetene står alfabetisk innenfor gruppa**, i enhetslista, tavla og
  «Nytt oppdrag».
- **Antall pasienter settes av bilen**, ikke av operatøren: to store knapper
  på det påbegynte oppdraget der problemstillingen bærer et antall. Tomt
  vises som «1 pasient», ellers «N pasienter». Feltet er borte fra
  operatørens skjemaer.
- Et oppdrag beholder problemstillingen sin om noen deaktiverer den — KO kan
  fortsatt rette fritekst og hastegrad på det.

## 2026-09-12 — Andrés runde på staging, del D: småfeil og visning

Én migrasjon, `oppdrag/0018`: `Oppdrag.trenger_ressurs_siden`. Ren
skjemaendring.

- **Innloggingssiden:** fanikonet er en lys utgave av merket uten bakgrunn
  (`static/img/favicon.svg`) — merket på blått ble en mørk flekk i en mørk
  fanelinje. PWA-ikonene er som før. «Vis passord» er portalens egen, lyse
  knapp; nettleserens svarte øye (Edge) skjules.
- **«Nytt oppdrag»:** avkryssingen av enheter og valgt lokasjon overlever at
  pollingen tegner lista på nytt — det var derfor krysset forsvant. Alle
  nedtrekkene starter øverst hver gang vinduet åpnes, og fritekst og antall
  tømmes.
- **Oppdragslista på sentralbordet sorteres på hastegraden operatøren satte**
  (Akutt, Haster, Vanlig, Drift) og innenfor den på nummer. Ferdige nederst.
- **«Trenger ny ressurs» trappes opp med tida:** gul kant de første fem
  minuttene, oransje rad til et kvarter, så rødt med puls. Merket har egen
  trekant, ikke statusprikken bilene har, og sier hvor lenge det har stått.
  Bilen som rykket videre står i loggen, ikke lenger i enhetsraden på lista.
- **Bilen:** «Nylig avsluttet» viser oppdragsnummeret. Står problemstillingen
  som «Udefinert», sier kortet fra *før* hun trykker «Ledig»: meld
  problemstillingen til KO. Avvisningen fra serveren ble tidligere skjult i
  samme åndedrag som køen ble tom — bilen så bare «venter på dekning».
- **Adminkontoer er aldri mannskap** («Den er utenfor.»): de kobles ikke på
  e-post, tilbys ikke i kontolista, og avvises ved kobling for hånd.

## 2026-09-12 — «Teknisk» heter «Drift»

Migrasjon `oppdrag/0017`: nye hastegradvalg, og rader som sto som «Teknisk»
på staging rettes til «Drift». «Udefinert» står øverst i alle fire listene,
og `choices` håndhever det.

## 2026-09-12 — Andrés runde på staging, del C: «trenger ny ressurs»

Én migrasjon, `oppdrag/0016`: `Oppdrag.trenger_ressurs` og
`Enhetshendelse.detalj`. Rene skjemaendringer.

- **Rykker bilen ut på et nytt oppdrag mens hun står på et annet, blir det
  forrige stående på tavla som «Trenger ny ressurs»** i stedet for å ryddes
  til historikken. Hennes rad lukkes automatisk som før (§4.3); oppdraget
  gjør det ikke. Merket står først i enhetsmatrisen, tidslinjen sier «Rykket
  videre til #12», og sentralbordet varsler en ny enhet — det nullstiller
  flagget — eller sletter oppdraget hvis det ikke lenger trengs.
- Var en annen bil fortsatt på oppdraget, endres ingenting: hun kjører
  videre, og oppdraget følger henne.

## 2026-09-12 — Andrés runde på staging, del B: oppdragsmodulen

Én migrasjon, `oppdrag/0015`: `Enhet.type`, `Oppdrag.antall` og de nye
hastegradvalgene. Rene skjemaendringer; eksisterende enheter får «Annet».

- **Hastegrad «Teknisk», i blått**, med egne problemstillinger
  (matutlevering, transport, utstyr, forsyning, annet teknisk). «Vanlig» er
  grønn, som i statistikken. Problemstillingen må høre til hastegraden —
  serveren avviser paret, og skjemaet bygger nedtrekket om når hastegraden
  endres.
- **Rekkefølgen i skjemaet er hastegrad → lokasjon → problemstilling**, i
  «Nytt oppdrag» og i «Rediger».
- **«Udefinert»** som problemstilling i alle listene. Bilen får ikke melde
  ledig før sentralbordet har satt en ekte problemstilling; meldingen står på
  enhetsskjermen.
- **Transport har antall**, et helt tall, vist som «Transport · 3» på tavla,
  i bilen og på enhetskortet.
- **Enhetstyper.** Ambulanse, mannskapsbil, lag til fots, annet — settes i
  enhetspanelet, og grupperer ressursoversikten og avkryssingen i «Nytt
  oppdrag» med ambulansene først.
- **Lokasjoner:** sentralbordet (`skriv_full`) legger til og endrer navn;
  global admin sletter ubrukte, med bekreftelse. Brukte kan bare deaktiveres.

## 2026-09-12 — Andrés runde på staging, del A: vaktlisten

Én migrasjon, `vaktliste/0014`: `Mannskap.epost`, ingen data flyttes.

- **Rettet: besetningen i sentralbordet fant ikke bilen.** Scopet var portalens
  aktive vakt alene; nå vinner vaktlista som er **i drift**, og den aktive
  vakta er reserven. Dekker ingen skift nå, står neste skift i svaret («Neste
  skift 16:00: Kari, Ola») i stedet for bare «ingen».
- **E-post på mannskapet, og kontoen kobles av seg selv.** Finnes en aktiv,
  ledig portalkonto med samme e-post, kobles den ved lagring. Et merke ved
  adressen sier at en bruker finnes. Adminkontoer kobles bare av global admin.
- **Kontokobling for hånd er global admin.** Konto-feltet og -kolonnen finnes
  bare for admin; vaktlederen kobler gjennom e-posten.
- **«Skrive: eget korps» ser alle korps.** Korps-føreren ser hele lista og
  registeret, får korpsvelgeren, og redigerer fortsatt bare sitt eget.
  Etiketten i matrisen heter «Skrive: eget korps, ser alle».
- **Probono i bemanningskurven** som den øverste delen av søylen, i grønt,
  med egen post i tegnforklaringen.
- Registeret annoterer «i bruk» i stedet for én spørring per rad.

## 2026-09-12 — Plan: reserve og offline

Ingen kode. Planen for reserve og offline står i `TODO.md` under «Pågående / neste»:
vaktlista som fil på e-post, offline drift på drifts-PC-en, backupene kryptert og
komprimert til Scaleway Object Storage, og fjerning av den gamle offline-arkitekturen.
Speiling til staging ble vurdert og tatt ut, fordi det ikke deployes under vakt.

## 2026-09-12 — Hjem-skjerm-ikonet: full flate, og kortnavnet

- **Rettet: ikonet på hjem-skjermen hadde blå flekk øverst til venstre og
  gjennomsiktig resten.** Rendringen skalerte bakgrunnsrektangelet sammen
  med `<svg>`-taggen, så flaten dekket 180 av 512 enheter. Generatoren
  ligger nå i `scripts/lag_ikoner.py` og skalerer bare rot-elementet;
  `IkonfileneTests` leser hjørnepikslene i PNG-ene (egen liten PNG-leser,
  Pillow er ikke i requirements) og stopper det.
- **Kortnavnet er «Sanitetsportalen»**, som navnet (André: «Vi har
  sanitetsportalen på begge»).

## 2026-09-12 — Andrés rapport 4: arkivering lukker vakta, ny logo

Ingen migrasjon.

- **Arkivering av oppdragsvakta lukker den.** Radene fryses med signatur
  som før, og deretter tømmes tavla og historikken og telleren nullstilles,
  så neste oppdrag får #1 (André: «tallene må resettes … historikklisten
  tømmes»). Avvises med 400 mens noe står på tavla — et pågående oppdrag
  slettet halvveis er en hendelse uten slutt. `arkiver_vakt(..., tomm=False)`
  fryser uten å rydde, for testene som sammenligner arkiv med live. Vaktarkivet
  var alt global admin i alle fire endepunkter.
- **Bilen ser de andres stempler også mens hun venter.** Tidslinjen sto
  bare på det aktive kortet; nå står den på det ventende når andre biler har
  stemplet.
- **Bemanningskurven forsvant** på en vaktliste der vaktens start lå uker
  før slutten: spennet over 14 dager ga stille opp. Nå faller den tilbake på
  skiftene, og uten spenn sier kortet hva som mangler i stedet for å stå tomt.
  Bunnlinja heter «N personell på det meste» og teller folk, ikke plasser.
- **Ny logo:** et skjold med en person i, to farger på portalens blå. Den
  første leste som EKG («trenger bare noe subtilt»).

## 2026-09-12 — Andrés rapport 3, manifest og logo

Ingen migrasjon. Nye arkiv får tittelen «Arkivert dd.mm.åååå hh:mm»; eldre
arkiv står som før i basen, og klienten klipper vaktnavnet av tittelen.

- **Bilen ser de andre bilenes stempler i tidslinjen** (§7.3 snudd: «nyttig
  for de å vite historikken der»). `andre_meldinger` i lista og detaljen,
  tegnet dempet med bilens navn på raden. Egen kjede og knappene bygger
  fortsatt bare på `statusmeldinger`, og de andres ID-er er med i ETag-en.
- **Vaktarkivets tittel uten vaktnavnet.** Det sto på raden under alt, og
  leste dobbelt («Test — arkivert … / Test · arkivert av»).
- **«Mitt korps» skiller å dekke for korpset fra åpent for alle.** 32 t «å
  dekke» der det meste var åpent for alle, leste som korpsets gjeld.
- **Bemanningskurvens hode har tre tall og ikke mer:** «Ledige plasser: N ·
  M plasser dekket» og «K plasser på det meste». Lista over ledige skift er
  borte («for mye clutter»).
- **«Arkiv» ved siden av «Arkiver vaktlisten», i sitt eget vindu.**
  Vaktvinduet lukkes først (`_byttModal`), så to modaler aldri står oppå
  hverandre — det var den feilen som frøs oppdragsvinduet.
- **Manifest og logo.** `/manifest.webmanifest` (`core/manifest.py`, uten
  innlogging, med `{% static %}`-stier fordi WhiteNoise hasher navnene) og
  `static/img/logo.svg` med PNG-er i 192, 512, maskable og apple-touch.
  Merket er en ring — portalen — med en pulslinje — sanitet; bevisst uten
  kors, som er Røde Kors-emblemet. `partials/_ikoner.html` tas med i hver
  mal med eget `<head>`, og logoen står i portalheaderen og på innloggingen.
  `core/tests_manifest.py` håndhever alt tre.

## 2026-09-12 — Andrés rapport 2, runde 2: vaktlisten og statistikken

Ingen migrasjon.

- **«Utildelt» heter «Åpen for alle».** André foreslo «ledig korps»; «ledig»
  er alt plassen uten person, og to «ledig» i samme rad leser som ett. Bare
  navnet — nedtrekket, oversikten og «Mitt korps». Feltet er fortsatt
  `alle_korps`.

- **Nedtrekkene tilbyr bare dem brukeren får sette inn.** Korps-føreren
  kunne velge hvem som helst; serveren avviste, men lista lot som.
  `services.mannskap_brukeren_kan_sette` speiler `kan_redigere_mannskap`:
  alle for den som skriver alt, eget korps med badge, ellers ingen.
- **«Mitt korps» teller bemannet, å dekke og probono hver for seg.** Ett
  samlet «avsatt» blandet korpsets egne timer med de ledige plassene og
  leste som feil (24 t der André ventet 16).
- **Bemanningskurven lister ledige skift, ikke plasstimer.** «20 ubesatte
  plasstimer» ble «Ledige plasser: 2 × fre 17:00 – lør 03:00». Bunnlinja
  sier «3 plasser på det meste»; «topp 3 plasser kl. 11–15» er borte.
- **«Dupliser som ledig plass»** i skiftvinduet: samme spenn, rolle,
  reservasjon og probono, uten personen. `skriv_full`, som å opprette.
- **«Slett vaktlisten»** for global admin ved siden av «Arkiver», med to
  bekreftelser og `{"confirm": true}` (endepunktet fantes). **Arkiverte
  vaktlister ligger bak én knapp** og vises først når man ber om det.
- **Registeret hentes ved sidelasting**, så «Korps» i innstillingene åpner
  uten ventetid første gang.
- **Lesbar tidstekst på /statistikk/.** Ventetid, tid på obspost, total
  behandlingstid og krysstabellens radsum sto med `color:#1e293b` rett i
  markupen — mørk tekst for lys bakgrunn. Nå `.kpi-tid` og `.xt-total` i
  stilarket. **«Til pasientregistrering»-knappen er fjernet.**

## 2026-09-12 — Andrés rapport 2, runde 1: oppdragsmodulen

Én migrasjon, `oppdrag/0014`: ny tabell `Enhetshendelse`, ingen data flyttes.

- **Rettet: «kan ikke ligge i framtiden» når man trykket med én gang.**
  Nettleserens klokke kan gå sekunder foran serverens, og «nå» rundet ned
  til minuttet lå da i framtiden for serveren. `MINUTTSLAKK` gjelder nå
  begge veier, i føring og «Rett tid».
- **Rettet: oppdraget ble stående på tavla** når én bil meldte ledig og en
  annen ble tatt av etterpå. `ta_av_enhet` rydder til historikken når den
  som ble tatt av var den siste som ikke var ledig.
- **Tidslinjen viser hvem som ble varslet og hvem som ble tatt av.**
  Varslingen leses av koblingsradens `varslet_at`; fjerningen får et eget
  spor, `Enhetshendelse` — raden er borte, hendelsen står. Flytting sto der
  fra før.
- **«Angre» på enhetens siste status** (`angre_siste_status`, `POST
  …/enheter/<pk>/angre/`): meldingene for statusen slettes med
  rettingshistorikken sin, og raden går tilbake til den forrige.
  Slettingen logges i revisjonsloggen. **«Gjenåpne» gjør nå det samme** for
  «Ledig», med 48-timersgrensen — den la før en korreksjonsrad med forrige
  status, og da sto forrige status dobbelt og et nytt angre landet på den
  samme. Knappen står ved «Rett tid» på enhetens siste melding.
- **Sletting av oppdrag** (`DELETE api/oppdrag/<pk>/`, `{"confirm": true}`):
  sentralbordet mens alle biler venter — er noen på vei, angres statusen
  først — og global admin i historikken, enkeltvis eller «Slett alle i
  historikken» (`DELETE api/historikk/`). Korreksjonsradene kobles fra før
  slettingen (`korrigerer` er PROTECT, og stoppet ellers alt).
- **Sentralbordet redigerer oppdraget**: «Rediger» i detaljvinduet gir
  problemstilling, hastegrad, lokasjon og fritekst (PUT-endepunktet fantes).
- **«Avreist → Sykehus» synes i sentralbordet**: på enhetskortet, i
  oppdragslistas brikker og i enhetsradene (`sted_navn`).
- **«Endre»** heter knappen i skjemaet (var «Før»), og radens «Endre
  status» låses mens skjemaet står. «endret av KO» i tidslinjene (var «ført
  av sentralen»), i bilen og i sentralbordet.
- **Arkivlista viser notatet.**

## 2026-09-12 — Planlagt og utildelt: navnene, og én vei

André: «Utildelte vakter må vises til alle, og så må vi ha en annen som heter
planlagt. En kan ikke bytte tilbake til planlagt etter den er satt til
utildelt eller er tildelt et korps.» Avklart: utildelt = alle ser; planlagt =
synlig for lederne før de deler ut.

Ingen skjemaendring: dagens skjulte «utildelt» *er* planlagt, og dagens
«alle korps» *er* utildelt. Det som manglet var navnene og énveisregelen.

- **Navnene.** Nedtrekket på plassen sier «Planlagt», «Utildelt» og korpsene;
  oversikten og «Mitt korps» skriver «Utildelt» der det sto «Alle korps», og
  «Planlagt» der kolonnen sto tom. Korpsvelgeren i vaktlinja heter fortsatt
  «Alle korps» — den er et filter, ikke en tildeling.
- **Planlagt går én vei.** `services.er_planlagt` (ingen reservasjon, ikke
  utildelt). PUT som ville gjort en delt-ut plass planlagt igjen får 400 med
  forklaring; nedtrekket tilbyr «Planlagt» bare så lenge plassen står der.
  «Som ressursen» på en ressurs med korps er ikke planlagt — den veien er åpen.
  `PlanlagtGaarEnVeiTests` på server, `_plassKorps` i node.

## 2026-09-12 — Andrés testrapport, runde 2: vaktlisten

Én migrasjon, `vaktliste/0013`: `Vaktliste.arkivert_at`, rent `AddField`.

- **Egne folk på andres plass.** «En ressurs som er tildelt et annet korps
  men har fått et personell fra et annet korps kan ikke den med skriv eget
  korps redigere.» Nå: **en fylt rad følger personen, en tom følger
  reservasjonen** (`kan_rore_vaktpost`, `kan_sette_vaktpost`, og
  `kanRoreRad` i JS). Står en av korpsets egne på Karmøys plass, kan
  korps-føreren rette raden, bytte til en annen av egne, eller ta henne ut
  så plassen blir ledig — men ikke fylle den med et annet korps, og er
  raden først tom, er den Karmøys igjen. Andres person på egen ressurs er
  deres rad. `EgenPersonPaaAndresPlassTests` på server, speilet i JS.
- **Arkivering av vaktliste i stedet for sletting.** «Vi må kunne
  lagre/arkivere vaktlista for å hente den igjen ved feil.» Global admin
  får «Arkiver vaktlisten» i vaktvinduet: lista går ut av velgeren, alt
  står, og «Arkiverte vaktlister» under har «Hent tilbake».
  `POST api/vaktlister/<pk>/arkiver/` og `gjenopprett/` — to navngitte stier,
  ikke `<str:retning>`, som ville fanget `ressurser/` og `belastning/`
  (testen fant det). `DELETE` finnes fortsatt, uten knapp.
- **Til-tiden foreslås som fra + 8 t** i «Opprett vakt» og «Rediger skift»
  når den er tom eller ligger før fra (`foreslaaTil`); et til som alt står
  etter fra røres ikke.
- **«Mitt korps» viser timer**: avsatt (uten probono) og probono for seg.
- **Probono-merket vises også på en ledig plass**, i ressurstabellen og i
  «Mitt korps».
- **Bare global admin kan koble en adminkonto til et korps**
  (`_kobler_til_admin` i registerviewet): badgen avgjør hva kontoen får
  redigere, og en vaktleder skal ikke kunne gi eller ta administratorens
  korps.
- **«Korps»-etiketten ved korpsvelgeren er borte.** Den leste som en knapp
  som ikke gjorde noe; nedtrekkets «Alle korps» sier hva det er.

## 2026-09-12 — Andrés testrapport, runde 1: oppdrag og statistikk

Fra prodtesten på staging (rapporten i chatten). Ingen migrasjon.

- **Rettet: sted- og grovsorteringsknappene i bilen gjorde ingenting.**
  «Jeg får trykke knappen men kommer ikke videre.» Knappene bar nøkkelen i
  `data-id`, og klikkdelegeringen gjør `data-id` om til tall — `Number('sykehus')`
  er NaN, og handlingen avviste den stille. Nå `data-arg`.
  `StedOgGrovKnappeneTests` kjører delegeringens argumentregel mot knappenes
  markup, og røyktesten i Chromium går hele kjeden: Rykker ut, Fremme, Gul,
  Avreist → Sykehus, Leverer, Ledig. Node-testene som fantes så bare på
  markupen; ingen klikket.
- **Grovsorteringen finnes fra Fremme**, ikke fra Rykker ut: den er en
  vurdering av pasienten, og den finnes ikke før bilen er framme.
  Knappene har fått fargen sin også før de er valgt — tre grå knapper med
  ordene Rød/Gul/Grønn var en lesejobb i en bil i bevegelse.
- **Rettet: historikken viste bare den primære bilen.** Alle enhetene står
  der nå.
- **«Nytt oppdrag» nullstilles ved hver åpning** (`show.bs.modal`), uansett
  hvilken vei forrige forsøk gikk. Kunne ikke reproduseres, men regelen er
  nå uavhengig av stien dit.
- **«Før status» heter «Endre status».** «Før» leste som fortid. Stedet vises
  bare når «Avreist» er valgt i nedtrekket (`foerStatusEndret`). Mens ett
  skjema står åpent, skjules knappene på de andre radene — ett om gangen. Et
  avvist klokkeslett settes tilbake til nå.
- **Tidslinjen begynner med «Oppdrag opprettet».** Uten «Rett tid»: den er
  ikke et stempel, og ingen melding kan rettes til før den.
- **Oppdragsarkivets tall vises på /statistikk/**, som pasientarkivet, via
  `?kilde=oppdrag&arkiv=<id>` (`lastOppdragArkivStatistikk`) med banner og
  «Tilbake». «Vis tall» i vaktarkivet viste én linje ren tekst; knappen heter
  «Vis statistikk» nå, og «Signatur» viser det den viste før.
- **KPI-boksen «Oppdrag»** viser tallet alene, og «N enhetsinnsatser» som
  undertekst når det skiller — «(15 enhetsinnsatser)» i selve tallet fikk
  ikke plass. Underteksten «i vakta» er borte.
- **«vakta» → «vakten»** i alle brukervendte tekster i maler og JS (46 steder).

## 2026-09-12 — Rettet: sida frøs etter «Ta av» eller «Varsle» i detaljvinduet

Funnet av André i prod rett etter deployen: «fjerner en bil eller gir en annen
bil et oppdrag og du går ut av det vinduet så fryser appen.»

**Årsaken var en modalinstans for mye.** Handlingene per enhet tegner
detaljvinduet på nytt mens det står åpent, og `visOppdrag()` gjorde
`new bootstrap.Modal(el).show()` hver gang. Bootstrap 5 lar ett element ha
én instans: den nye overtok, `.show()` på den la en bakgrunn til, og
lukkingen fjernet bare den sistes. De andre ble liggende over hele sida.
«Rett tid» og «Før status» hadde samme feil, og alle modalene i vaktlista
og pasientarkivet gikk samme vei ved gjentatte åpninger.

Reprodusert med ekte Bootstrap 5.3.2 i Chromium: to bakgrunner igjen etter
lukking, null med rettelsen, og «Nytt oppdrag»-knappen klikkbar igjen.
`bootstrap.Modal.getOrCreateInstance(el).show()` overalt der et vindu åpnes
— ni steder — og `DetaljvinduetTegnesPaaNyttTests` kjører `visOppdrag()`
tre ganger mot en Modal-stubb med Bootstraps regler og krever én instans.
Ingen migrasjon. **Pushet til `main` som `9437986`** samme kveld.

## 2026-09-12 — Merget til prod: flere enheter, korpsfilter, utskrift

`rollemodell` → `main` (`4c6017b`), fast-forward. 19 commits: 59 files changed, 7288 insertions(+), 403 deletions(-).
Åtte migrasjoner gikk ut — `accounts.0016` (nivået `les_alle`),
`vaktliste.0011`–`0012` (probono, plass tildelt alle korps), `oppdrag.0009`–`0013`
(avreist til/grovsortering, koblingsraden `Oppdragsenhet`, backfill, `manuell`,
arkivrad per enhet). **Én av dem skriver data**, `oppdrag.0011`: én koblingsrad per
eksisterende oppdrag. Backup av prod bekreftet tatt før pushen (André, «Backup
tatt — push»).

Innholdet er alt siden forrige merge: tidsblokker og «8,5 t», korpsfilteret med
`les_alle` og korpsvelgeren, bygg og dato i footeren, prosjektleders tre runder,
flere enheter på ett oppdrag i fire trinn, og utskrift per korps eller ressurs
med korpsvelgeren rettet.

**Verifisert før merge:** 2186 tester grønne, `verifiser_migrasjoner` OK mot
PostgreSQL 16 for begge prøvene (`vaktliste.0007` og `oppdrag.0011` med rader i
den historiske formen), og røyktester i Chromium av sentralbordet med to biler
og av korpsvelgeren. Ingen oppgraderingssimulering av hele basen denne gangen —
den ene datamigrasjonen er dekket av prøven, og de sju andre er rene
skjemaendringer.

**Deploy 2 står igjen** (eget punkt i TODO): fjerne `Oppdrag.enhet` og gjøre
`Statusmelding.oppdragsenhet` NOT NULL, når koden har gått en stund med broene.

## 2026-09-12 — Korpsvelgeren virket ikke, og utskrift per korps eller ressurs

**2186 tester grønne** (7 nye), og en røyktest i Chromium: velg korps, velg
ressurs, begge samtidig, og velgeren borte i utskrift. Ingen migrasjon.

- **Rettet: korpsvelgeren i vaktlinja filtrerte ingenting.** André: «Når vi
  setter til et korps i nedtrekksvinduet så vises fortsatt alt i oversikt.»
  Markupen var riktig (`data-action="velgKorps" data-hendelse="change"`), og
  `velgKorps()` virket når den ble kalt — men ingen kalte den. Klikkdelegeringen
  i `portal-utils.js` hopper over `data-hendelse`-elementer med vilje
  (`klikkSkalKjore`), og den eneste `change`-lytteren var scopet til
  ressurspanelet og hardkodet til `endreVaktpost`. Korpsvelgeren står utenfor
  panelet. Nå har `change` sin egen delegering ved siden av klikk,
  `haandterHendelse`, og `hendelseArgumenter` gir cellene (id, felt, verdi) og
  alt annet ett argument. Panellytteren er borte. `HendelsedelegeringTests`
  kjører delegeringen mot falske elementer — testene som fantes kalte
  `velgKorps()` direkte og så aldri at knappen ikke var koblet.
- **Utskrift per korps eller per ressurs.** «Oversikt» har fått en velger over
  lista: «Hele vakta» eller én ressurs, gruppert på ressursgruppe og bare
  ressurser med skift (`mkUtskriftsverktoy`, `velgUtskrift`, `utskriftRessurs`).
  Korpset er korpsvelgerens — de to kombineres — og for korps-brukeren er lista
  alt hennes korps. **Arket sier selv hva det er avgrenset til**
  (`_utvalgstekst`, «Haugesund · Ambulanse 1» i arkhodet), for velgeren
  kommer ikke med på papiret. Summene i arkhodet er utvalgets. En
  «Skriv ut»-knapp står ved velgeren.

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 4: arkiv og statistikk

**2179 tester grønne** (5 nye). Én migrasjon, `oppdrag/0013`: unikhet og
rekkefølge på `ArkivertOppdrag` — ren skjemaendring, ingen data flyttes.
Alle fire trinn er levert; deploy 2 (fjerne `Oppdrag.enhet`, stramme
`Statusmelding.oppdragsenhet`) står igjen som eget punkt.

- **Én arkivrad per oppdrag × enhet** (§5 A). Nummeret gjentas per bil, og
  hver rad bærer *hennes* tidsstempler og sluttstatus. Samme radform og samme
  signaturform: `sha_payload` sorterer nå på `(oppdragsnummer, enhet_navn)`,
  som for unike nummer er den gamle rekkefølgen — `SignaturLaastTests` står
  urørt, og eksisterende arkiver verifiserer som før. `arkiv._per_enhet()` er
  det ene stedet som sier hva en rad er.
- **Statistikken teller oppdrag distinkt og varigheter per bil.** Det som er
  bilens — responstid, ventetid, utrykning, tid på stedet, oppdragstid,
  `per_enhet` — per rad; det som er oppdragets — antall, hastegrad,
  problemstilling, lokasjon, status nå, ankomster — én gang per nummer, med
  status utledet som på tavla (`services.utledet_av_statuser`, delt). Et
  arkiv med én bil per oppdrag gir nøyaktig de gamle tallene, og
  `ArkivStatsMatcherTests` er utvidet til to biler: arkivet gir det live gir.
- **`summary.enhetsinnsatser`** er radtallet; statistikksiden viser
  «12 (15 enhetsinnsatser)» når de skiller. Arkivlista viser `antall_oppdrag`
  distinkt og `antall_enhetsrader` ved siden av.
- Koblingsradene hentes med én `Prefetch` med enheten joinet inn —
  `GjeldendeBulkTests` holder statistikken på fire spørringer uansett antall
  oppdrag.

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 3: sentralbordets knapper

**2174 tester grønne** (15 nye), og en røyktest i Chromium mot hele flyten:
opprett med to biler, før status for den ene, ta den andre av, varsle henne
igjen. Ingen migrasjon.

- **«Nytt oppdrag» krysser av enheter** (`mkEnhetsvalg`), ikke velger én. Den
  første i lista blir primær; ingen avkrysset gir «Kryss av minst én enhet» før
  noe sendes.
- **Oppdragslista viser én brikke per enhet** (`_enhetsmatrise`): prikk, navn,
  status og tid siden. Samme brikke med én enhet — lista skal lese likt.
  Oppdragets utledede status står fortsatt til høyre.
- **Detaljvisningen har fått «Enheter»** (`mkEnhetsrader`): én rad per enhet
  med status, klokkeslett og tid siden, og bare knappene som kan brukes —
  «Før status» (ikke når hun er ledig), «Gjenåpne» (bare da), «Ta av» (bare
  mens hun venter, og ikke den siste). «Varsle enhet til» under, med enhetene
  på vakt som ikke alt står på oppdraget. Feil fra handlingene står under
  innholdet, så de overlever at det tegnes på nytt.
- **«Før status» er et skjema i raden**, som «Rett tid»: nedtrekket tilbyr
  neste ledd og «Ledig» (`_lovligeOverganger` speiler `services.OVERGANGER`),
  sted ved «Avreist», og klokkeslett med nå som utgangspunkt. Stedet sendes
  bare når statusen er «Avreist».
- **Tidslinjen sier hvem sin melding** når oppdraget har flere enheter
  («KARM 12: Fremme»), og «ført av sentralen (adm)» på det operatøren førte.
  `melding_til_dict` bærer `enhet_navn`; `gjeldende_bulk` henter enheten med,
  så det ikke koster en spørring per rad.
- **Flytt av én rad:** med flere enheter får «Flytt til enhet» et «fra»-valg.
- **Rettet: «Rett tid» viste «[object Object]».** Skjemaet ble satt med
  `trustedHtml(...)` som innerHTML — den pakker inn i et objekt for
  `cellHtml()`. Det har stått slik siden fase 3; ingen test kjørte funksjonen.
  `InnlinjeskjemaeneTests` kjører begge skjemaene mot en DOM-stubb nå.
- **Ett minutts slakk mot `created_at`** (`services.MINUTTSLAKK`) i føring og
  «Rett tid»: `datetime-local` har minuttoppløsning, og «nå» rundet ned lå før
  et oppdrag opprettet sekunder tidligere. Røyktesten fant det.

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 2: endepunktene og §9

**2159 tester grønne** (30 nye). Én migrasjon, `oppdrag/0012`: ett `AddField`,
`Statusmelding.manuell`, standard `False`.

Endepunktene fra notatets §4, og sentralbordets føring fra §9 — data og API;
knappene kommer i trinn 3.

- **`POST api/oppdrag/` tar `enhet_ider`** — den første er primær, dubletter
  strykes, og én enhet som ikke er på vakt avviser hele opprettelsen: operatøren
  mente å sende flere, og skal ikke få ett oppdrag med færre enn hun krysset av.
  `enhet_id` godtas fortsatt og betyr én.
- **`POST`/`DELETE api/oppdrag/<pk>/enheter/<enhet_pk>/`** varsler en enhet til
  og tar henne av. Ta av bare mens hun venter, og aldri den siste. `skriv_full`,
  og enhetskontoer stengt ute uansett nivå — som «Rett tid».
- **`POST api/oppdrag/<pk>/enheter/<enhet_pk>/status/<overgang>/[<sted>/]`** er
  sentralbordets føring av en status bilen glemte (§9). `tidspunkt` i kroppen er
  **påkrevd** — poenget er å føre bakover i tid — og derfor `skriv_full`, ikke
  `skriv_handling`: bilens stemplingsendepunkt leser ingen domenefelt, og dette er
  en annen aktør. Overgangsreglene gjelder operatøren også; tidspunktet må være
  inntruffet, etter oppdraget og etter bilens siste melding. Raden merkes
  `manuell`, og tidslinjen sier «ført av sentralen».
- **`POST api/oppdrag/<pk>/enheter/<enhet_pk>/gjenaapne/`** tar «Ledig» tilbake
  innen `KORRIGERBAR_ETTER_LEDIG` (48 t, André: «innenfor en rimelig
  tidsperiode»). En korreksjon, ikke en sletting: `Ledig`-meldingen blir stående,
  og en ny rad peker på den med statusen som gjaldt før — med *dens* tidspunkt,
  så ingen varighet flytter seg. Oppdraget hentes tilbake fra historikken.
- **`flytt/` tar `fra_enhet_id`**: med flere enheter er flytt flytt av én rad.
  Uten er det den primære, som før.
- **Rettet fra trinn 1:** `_naboer` målte korreksjoner mot hele oppdragets
  meldinger, så den andre bilens «Rykker ut» sto i veien for å rette denne bilens
  «Fremme». Nå per koblingsrad.
- **`enheter[]` bærer `status_tidspunkt`** per enhet, uten en spørring per rad —
  lista gjenbruker `gjeldende_bulk`, og en test holder spørringstallet flatt.
- **Bilen ser «Også varslet: KARM 12»** på aktivt og ventende kort — navn, ikke
  status (§7.3).

## 2026-09-11 — Flere enheter på ett oppdrag, trinn 1: koblingsraden

**2129 tester grønne** (32 nye i `oppdrag/tests_flere_enheter.py`). To migrasjoner,
`oppdrag/0010` (skjema) og `0011` (bare data, med prøve i `core/migrasjonsprover.py`).
**Backup av prod før deploy** — `0011` skriver én rad per oppdrag.

**`Oppdragsenhet` er nå det en statusmelding hører til.** Én melding er *én enhets*
utsagn om *ett* oppdrag, og kjeden Venter → Rykker ut → … → Ledig går per koblingsrad
(`services.sett_status(..., enhet=)`, `start_oppdrag(..., enhet=)`). `Oppdrag.status`
er fra nå **utledet** (`services.utledet_status`): den mest aktive enheten vinner,
`Ledig` bare når alle er ledige — og det er da oppdraget flyttes til historikken. Med
én enhet gir det samme svar som før; 305 eksisterende oppdragstester gikk uendret,
bortsett fra én hjelper som satte statuscachen for hånd og nå setter den der den bor.

- **Broene i deploy 1.** `Oppdrag.enhet` lever til deploy 2, og `Oppdrag.save()` lager
  koblingsraden ved opprettelse; `Statusmelding.save()` fyller `oppdragsenhet` fra
  oppdragets primære rad når en melding lages med bare `oppdrag`. Ingen eldre kode
  trenger å vite at raden finnes. `0012` (NOT NULL) er derfor flyttet til deploy 2 —
  notatets §6 er oppdatert.
- **Per enhet, ikke per oppdrag:** den automatiske lukkingen (§4.3) lukker *hennes*
  pågående, 30-minuttersvinduet på enhetsskjermen måles mot *hennes* ledig-melding,
  `enhet_status` og `ventende_oppdrag` leser radene, og `flytt_til_enhet` flytter én
  rad (og holder den gamle kolonnen i takt når den primære flyttes).
- **`varsle_enhet` / `ta_av_enhet`** (§4): varsle legger raden sist i `Venter`, og
  henter et ferdig oppdrag tilbake fra historikken; ta av bare mens hun venter, og
  aldri den siste. Endepunktene kommer i trinn 2.
- **Bilen ser sin egen kjede og de andres navn** (§7.3). `oppdrag_til_dict(...,
  koblingsrad=)` gir `status`/`neste_overgang` fra *hennes* rad og `varslede` som
  navneliste uten status; liste og detalj sender bare hennes meldinger. Eierskapet i
  detalj, stempling og grovsortering er «har enheten en rad», så bil nummer to kan
  stemple på et oppdrag som ble opprettet med bil én.
- **Sentralbordet får matrisen** som `enheter` på hvert oppdrag — data først, UI i
  trinn 3. Lista prefetcher radene.
- **Backup** tar koblingsraden med, mellom meldingen og oppdraget i
  gjenopprettingsrekkefølgen; `varslet_av` strippes som de andre kontopekerne.
  `BackupTests` gjenoppretter to enheter med hver sin status.

## 2026-09-11 — Beslutningsnotat: flere enheter på ett oppdrag

`docs/BESLUTNING_FLERE_ENHETER_PER_OPPDRAG.md` — utkast, ikke besluttet. Det siste
punktet fra prosjektleders runde, og det eneste som snur en antakelse som ligger i ni
steder: at et oppdrag er tildelt én enhet. Notatet foreslår `Oppdragsenhet` som
koblingsrad med egen statuskjede, oppdragsstatus utledet som «mest aktive», ferdig
når alle er ledige, én arkivrad per oppdrag × enhet (samme payload-form — gamle
arkiver verifiserer som før), og deploy i to trinn som `year` → `vakt`. Fire
spørsmål til André i §7 før kode; §7.1 (arkivformen) lar seg ikke gjøre om etterpå.
**Besvart samme dag** — alle fire som anbefalt, med én presisering på §7.2: enhetens
oppdrag er ferdig når hun melder ledig, oppdraget forlater tavla når alle er det. Og
ett krav til, §9: sentralbordet skal kunne føre status manuelt for enhver enhet, også
på ferdige oppdrag innenfor en rimelig tid (forslag: 48 t). Kode starter.


**2097 tester grønne** (18 nye, to mutasjoner satt rødt først). Én migrasjon,
`vaktliste/0012`, ett `AddField` med `False` som standard — ingen eksisterende
plass blir universal ved oppgraderingen.

**Tre tilstander på en ledig plass.** Prosjektleder: «Dine tildelte vakter og
de vakter som er satt universal tildelt. Utildelte vakter skal ikke deles ut.»
Det er ett nytt flagg, `Vaktpost.alle_korps`, og én regelendring:
- **Tildelt ett korps** — som før (`Vaktpost.korps`, eller ressursens).
- **Tildelt alle korps** — `alle_korps`. Enhver korps-bruker med badge får
  fylle den (`kan_bemanne_plass`); badgen kreves fortsatt, uten korps finnes
  ingen å sette inn. Flagget vinner over `korps`: en plass alle kan fylle er
  ikke satt av til én.
- **Utildelt** — vaktlederens bord, deles ikke ut. Som før.
Å tildele er å dele ut: `skriv_full`, samme port som reservasjonen.
Korpsfilteret tar de universale med — hennes å fylle, altså hennes å se.

**Reservasjonsnedtrekket** i ressursraden og i begge skiftvinduene har fått
«Alle korps», og «— alle —» heter nå «— utildelt —»: det var feil ord for en
plass som ikke deles ut til noen. `_korpsKropp()` oversetter de tre
tilstandene til serverens to felt.

**Fanen «Mitt korps».** Plassene korpset har ansvar for, på tvers av alle
ressursene: «N plasser å dekke» øverst, så blokkene med dagoverskrifter,
ledige først i hver blokk, med nedtrekket for å fylle dem. For korps-brukeren
er det hennes korps; for den som ser alle, det korpsvelgeren står på — uten
korps finnes ikke fanen. Tallet på fanen er det som gjenstår.

**Rettet på veien:** korps-brukeren så ikke nedtrekket på en plass satt av til
henne på en *ureservert* ressurs — klienten spurte bare ressursen. `kanBemannePlass()`
speiler nå `services.kan_bemanne_plass` plass for plass.


**2079 tester grønne** (19 nye, tre mutasjoner satt rødt først). Én
migrasjon, `vaktliste/0011`, ett `AddField` med `False` som standard.

**Probono-skift telles ikke i timene — men i alt annet.** `Vaktpost.probono`,
en avkryssing i «Opprett vakt» og «Rediger skift», redigerbar av alle som kan
redigere raden (samme port som merknaden — det er ikke å dele ut noe, det er å
si hva skiftet er). Timesummene hopper over det: blokklinja (nei — blokkas
timer er skiftets lengde), ressursoverskriften, arkhodet, planleggingstallenes
«timer» per person og i sammendraget, og faktiske timer. **Lengste skift og
korteste hvile teller det fortsatt**: et probono-skift sliter like mye, og
varslene handler om sliting, ikke om lønn. Merket «Probono» står ved navnet,
ikke i timekolonnen — timene i raden står som før, det er summene som hopper
over dem, og det skal man kunne se hvorfor. `probono_skift` per person følger
med i planleggingstallene.

**Dagoverskrifter over blokkene.** «Fredag 4. sep» / «Lørdag 5. sep» i
ressursfanene og utskriftslista, der dagen skifter — men bare når vakta
faktisk spenner over mer enn én dag; en endagsvakt ser ut som før.
Starttiden bestemmer dagen (prosjektleder): et skift 17:00–03:00 er fredagens.
`_dagnokkel()` bruker lokal dato, `_blokkerMedDager()` er det ene stedet som
setter overskriftene, og begge tabellene går gjennom den.


**2060 tester grønne** (27 nye, to mutasjoner satt rødt først). Én migrasjon,
`oppdrag/0009`, to `AddField` med tom streng som standard — intet dataskritt.

**«Avreist» spør hvor.** Samleplass, Skadepol, Legevakt, Sykehus, Annen
ambulanse, Annet sted — forkortet, som prosjektleder ba om. Stedet er et
URL-ledd, `status/avreist/<sted>/`, ikke et felt i kroppen: stemplings-
endepunktet leser ingen domenefelt derfra (rollemodellen §3.2), og «Avreist
til Sykehus» er ett navngitt endepunkt til. Lagres på **statusmeldingen**
(`Statusmelding.sted`) — meldingen er det som ble meldt, og en korreksjon
av klokkeslettet arver stedet. `sett_status` avviser et sted på enhver annen
status; viewet gir 404 før det. Uten sted virker «Avreist» som før, så gamle
køer ikke feiler.
- **Bilen:** «Avreist»-knappen åpner seks store knapper og «Avbryt» *i
  stedet for* knapperaden — midt i valget skal det ikke finnes en feil knapp
  å treffe. Valget følger «Avreist» gjennom offline-køen (`rad.sted`), og
  `synk` legger det i URL-en.
- **Tidslinjene** sier «Avreist → Sykehus», på begge skjermene.

**Bilens grovsortering: Rød/Gul/Grønn, ved siden av hastegraden.** To
vurderinger fra to ståsteder: KO/AMK setter hastegrad ved opprettelsen,
bilen setter grovsortering underveis — og begge skal synes. Hastegrad står
til venstre, «Bil: Rød» til høyre, med fargeprikk og tekst (fargen alene
bærer ikke informasjonen). Tom vises som «Bil: —»: «ikke vurdert ennå» er
informasjon. `Oppdrag.grovsortering`, satt av bilen via
`grovsortering/<rod|gul|gronn>/` — samme form som stemplingene, men ikke
gjennom `sett_status` (det er en vurdering som kan endres, ikke et ledd i
kjeden) og ikke i køen (uten dekning sier skjermen fra). Sentralbordet
setter den ikke. Vises på det aktive kortet i bilen (tre knapper, den
valgte fylt), i oppdragslista og på enhetskortet.

**Arkivet er urørt.** Ingen av feltene inngår i `ArkivertOppdrag` eller i
SHA-payloaden — signaturene i prod verifiserer som før. Skal de arkiveres,
er det en egen beslutning (payloadens form er låst).


**2033 tester grønne** (15 nye). Fem av elleve punkter fra prosjektleder —
de som var klare og små. Resten står i TODO med plan.

- **Kompetansekolonnen i Mannskap «detter fra kolonne–rad-matchingen».**
  Bekreftet: `.vlr-komp` satte `display: flex` rett på `<td>`-en — samme feil
  som ressurstabellen hadde 30. aug. Layouten ligger nå på en wrapper inne i
  cella, og `TabellcellersLayoutTests` leser mannskapstabellen også; den
  hadde funnet feilen om den hadde lest den.
- **Bemanningskurven står nederst i drift.** I planlegging er hullene jobben
  og kurven det første man ser; i drift er spørsmålet «hvem har møtt», og
  stemplene står øverst.
- **«Oppdrag i vakta» heter «Oppdragsliste».**
- **Enhetskortet i sentralbordet viser oppdraget i ett blikk**: nummer,
  hastegrad, problemstilling — og statusen med klokkeslett og tid siden,
  «Fremme 14:32 · 12 min». Enhetslista bærer feltene fra serveren
  (`_aktivt_oppdrag_felter`), og statustidspunktet er med i ETag-en: «Rett
  tid» endrer det uten å røre statusen.
- **«Tid siden» på oppdragslista**: «Fremme · 12 min» og «14:20 · 31 min
  siden». `status_tidspunkt_for()` finner den gjeldende meldingen bak hvert
  oppdrags status i én spørring for hele lista (`gjeldende_bulk`) — testen
  krever at antall spørringer ikke vokser med radene. Klienten tegner lista
  på nytt én gang i minuttet, siden serveren svarer 304 når ingenting er
  endret og «12 min» ellers ville stått stille.


André: «de med rollen skrive eget korps ser bare de som er med i sitt eget
korps, og samme med de som bare har lesetilgang — gjelder bare /vaktliste/».
Og om leseren uten korps: «to lesetilganger, en for eget korps og en for
alle korps».

**Nytt trinn `les_alle`** mellom `les` og `skriv_handling` i `NIVAA_HIERARKI`
(`accounts/0016`, ren `AlterField`). Vaktlista er den eneste som deklarerer
det: `les` = «Lese: eget korps», `les_alle` = «Lese: alle korps».
**Eksisterende `les`-rader ble smalere**, ikke videre — den trygge retningen;
den som skal samordne får `les_alle` i matrisen.

**Synligheten følger ikke stigen.** `skriv_handling` ligger over `les_alle`
og ser likevel bare sitt eget korps; `skriv_full` og oppover ser alle.
`services.ser_alle_korps()` er det ene stedet. `synlige_vaktposter()` og
`synlig_mannskap()` filtrerer i svaret sida bygges av — `vaktliste_detalj_view`,
`belastning_view`, `mannskap_view` — så oversikt, ressursfaner, tilstede,
kurver, planleggingstall og registeret følger med på én gang. Ledige plasser
satt av til eget korps vises (via plassen eller ressursen, samme
sammenslåing som `reservert_korps()`). Uten badge er lista tom, og malen
sier hvorfor. Sentralbordets besetning i `/oppdrag/` er **ikke** filtrert.

Notatets §4.4 («`les` ser hele lista — poenget er samordning») er strøket
med dato og begrunnelse; CLAUDE.md oppdatert.

**Korpsvelgeren for den som ser alle** (samme dag): «Det må og være en måte
for de med full tilgang å sortere på korps.» Et nedtrekk i vaktlinja — «Alle
korps / HGSD — Haugesund / …» — som gjør i nettleseren det serveren gjør for
korps-brukeren: `_synligePoster()` speiler `poster_for_korps()`, og
`brukKorpsfilter()` legger den på `aktivListe.vaktposter` og
`register.mannskap`, så oversikt, ressursfaner, tilstede, kurver og registeret
følger med uten å vite om den. Planleggingstallene regnes på serveren og får
`?korps=<id>` — honorert bare for den som ser alle. Velgeren finnes ikke for
korps-brukeren: hun er alt avgrenset, og et nedtrekk med ett valg ser
ødelagt ut. Skiftet bærer nå `korps_id` (personens), ved siden av
`reservert_korps_id` (plassens).

**Footeren viser datoen alene** — klokkeslettet står i tooltipen.

---

## 2026-09-11 — Bygg og dato i footeren, og en planleggingstabell som ikke klemmes

**1972 tester grønne** (13 nye). To punkter fra André.

**Footeren viser bygg og dato** — «Sanitetsportalen · adm · a03b5e5 ·
11.09.2026 10:15». Det er svaret på «er dette den nye koden, eller cachen?».
`core/versjon.py` prøver tre kilder i rekkefølge: `bygg.json` skrevet i
byggfasen på Railway (`nixpacks.toml` kjører `core/skriv_bygg.py`, som bare
bruker standardbiblioteket — et Django-oppsett i bygget ville gjort footeren
til en grunn til at deployen feiler), så `git` i arbeidskatalogen, så
`RAILWAY_GIT_COMMIT_SHA` alene med `manage.py` sin mtime som dato. Ingen
kilde gir «ukjent», ikke tomt. Regnes ut én gang per prosess.
- **Første deploy med `nixpacks.toml` må ses på.** Fila legger bare til ett
  byggsteg etter «install», og Python-provideren oppdages som før — men det
  er første gang bygget har en egen fase. Feiler steget, står footeren
  likevel med SHA fra miljøet.

**Planleggingstabellen på mobil.** «Veldig tett»: den arvet `min-width: 0`
fra drifttabellen, og `table-layout: fixed` delte 308 px likt på seks
kolonner — 51 px hver, «Korteste hvile» i tre linjer over et tall. Nå har
den egen klasse med gulvbredde og kolonneandeler, så den ruller i ramma på
en telefon i stedet for å klemmes, som ressurstabellen gjør.
- **«Fortsatt litt overlapp»** etter første runde: målt i iPhone-viewport
  var det overskriftene «Lengste skift» (114 px) og «Korteste hvile»
  (123 px) som skrev seg over nabocella — `thead th` er `nowrap`. Denne
  tabellen får bryte i hodet, gulvbredden er 38rem, og de to kolonnene fikk
  19 % hver. Målt etterpå: ingen celle flyter over.

**Footeren første gang på staging:** «8447399 · 11.09.2026 12:34» — det
er byggtiden i norsk tid (pushen gikk 10:34 UTC), altså riktig, og det
viser at byggsteget i `nixpacks.toml` kjørte.

---

## 2026-09-11 — Tidsblokker, slutt-tid i «Ny vaktliste», og «8,5 t» overalt

**1956 tester grønne** (25 nye, fem mutasjoner satt rødt først). Tre punkter
fra André etter at han hadde brukt modulen i prod.

**«Ny vaktliste» spør om slutten.** Feltet fantes, men bare bak «Vaktas
lengde» inne i innstillingsvinduet — og han fant det ikke. Dialogen har nå
«Slutter (planlagt)» rett under «Starter»; `opprett_planlagt_vakt` tar det
imot og håndhever samme regel som endringsendepunktet: slutten må komme etter
starten.

**Skift med samme fra–til samles i tidsblokker.** Mange på en vakt deler tid,
og en liste der «fre. 20:00 – lør. 04:00» sto på fire rader under hverandre
var lang og lik — man så ikke skiftbyttet før man hadde lest hver rad.
`_tidsblokker()` grupperer på *likhet* (ikke overlapp — et skift som slutter
en time før de andre er sitt eget), og `_blokklinje()` skriver tiden, timene
og antallet én gang over blokka: «Fre 2. okt 20:00 – lør 3. okt 04:00 · 8 t ·
4 satt opp · 1 ledig». Gjelder ressursfanene i planlegging og drift, og
utskriftslista. Radene under er hvem.
- Driftraden mistet «Skift» og «Timer» — de står på blokklinja — og
  drifttabellen ble fem kolonner. Planleggingsraden ble hevet ut til
  `_planrad()`; den er uendret, men står ikke lenger inne i `mkRessurs()`.
- Utskriftslista mistet kolonnen «Tid» av samme grunn, og fikk sum timer
  per ressurs i overskriften og for hele vakta i arkhodet.

**Ett timeformat: «8,5 t».** Ressurstabellen skrev komma, planleggingsfanen
skrev «8.5». `_tall()` er nå det ene stedet, og `_varighet()` går gjennom den.

**Rettet på veien:** «1 ledige» og «1 ledige plasser» i oversikten.

**Ordene, samme dag:** «Skift må vel tolkes som ulike vakttider, og
personell som mannskap.» Tellingene skrev «9 skift» om ni rader. Nå er et
skift en blokk — én vakttid — og mannskap er de bemannede radene:
«2 skift · 5 mannskap · 70,8 t · 1 ledig». Over hele vakta er skiftene de
*ulike* vakttidene, så samme spenn på samleplassen og bilen er ett skift.
`_telling()` er det ene stedet; gruppehodet, ressursoverskriften, arkhodet,
blokklinja og innstillingsvinduet bruker den. Belastningsfanen står som
før — der er «skift» per person nettopp skift.

**På en telefon henger ingen kolonne fast.** André så merknadskolonnen følge
med når tabellen rullet på mobilen, og ville ikke ha noe som fulgte. I
Chromium med iPhone-viewport er det bare blyantcella som er sticky, så det
han ser er trolig en WebKit-forskjell jeg ikke kan gjenskape her — men
sticky-kolonnen ble laget for laptopen, og på 390 px tar den en sjettedel
av det synlige. Under 768 px slås begge sticky-reglene av, cella og hodet.

---

## 2026-09-11 — Vaktlistemodulen merget til prod

`rollemodell` → `main` (`567ee11`). 33 commits, 66 filer, 18551 linjer.
Hele `vaktliste`-appen var **ny for prod** — den fantes ikke på `main` i det
hele tatt. Elleve migrasjoner gikk ut: `vaktliste.0001`–`0010` og
`accounts.0015` (det nye nivået `skriv_leder`, rent additivt).

Innholdet er vaktliste fase 1–6 — registre og planleggingsside, tilgangsmodellen
med badge og reservasjon, drift med stemplingsregler som data, planleggingstall
som varsler uten å sperre, og besetning i sentralbordet. Med på lasset:
lesbare cron-feil (`core/kommando.py`), sperren mot stille SQLite-tilbakefall i
`settings.py`, og migrasjonsprøvene mot ekte PostgreSQL.

**Verifisert før merge**, fordi `vaktliste.0007` tok ned release-fasen én gang:
1931 tester grønne, `verifiser_migrasjoner` OK, full migrasjon fra tom base mot
PostgreSQL 16, og en oppgraderingssimulering — en base migrert til `main`,
seedet med prod-lignende rader (brukere, tilganger, vakt, pasienter), deretter
migrert med den nye koden. Elleve migrasjoner OK, alle rader intakt, de seks
ressursgruppene seedet riktig.

Backup av prod tatt av André før pushen. Pushen ble holdt igjen til den var
bekreftet: push til `main` *er* deployen, og elleve migrasjoner er ikke noe man
angrer på uten backup.

---

## 2026-08-30 — «Ingen biler oppkoblet» var feil vakt, ikke feil oppsett

**1931 tester grønne** (13 nye, fire mutasjoner satt rødt først). Meldt av
André: han hadde koblet bilene, men sentralbordet sa at ingen var koblet.
Hans egen mistanke — at det hang sammen med at han hadde planlagt en vakt
fram i tid — var riktig.

**Reprodusert:** vakta han planla er `er_aktiv=False`, og sentralbordet scoper
til portalens **aktive** vakt. Koblingen lå i den planlagte vaktlista og var
derfor usynlig.

**Scopingen er riktig og beholdes.** Å vise oktobers besetning på tavla mens
man kjører i kveld ville vært verre enn å vise ingenting.

**Meldingen løy ved å tie.** «Ikke koblet til en ressurs i denne vakta» leses
som «koblingen din er ødelagt», og sendte André ut på jakt etter en feil som
ikke fantes. Endepunktet skiller nå mellom to helt ulike problemer:

- **Koblet i en annen vakt:** navngir vakta og sier hva som må gjøres — «bytt
  den aktive vakta i vaktadministrasjonen, eller koble enheten i vaktlista for
  vakta som går nå».
- **Ikke koblet noe sted:** et oppsett som mangler, som før.

Klienten viser serverens tekst uendret. Skrev den sin egen generiske, forsvant
nettopp forklaringen som gjør forskjellen.

**Ryddet på veien:** `koblet_i_annen_vakt()` hadde en `exclude()` på den aktive
vakta som ikke lot seg sette rød — kallstedet garanterer allerede at den aktive
vakta ikke har ressursen. En gren ingen test kan nå er en gren man ikke kan
begrunne, så den er borte.

---

## 2026-08-30 — Vaktliste fase 6: besetning i sentralbordet

**1918 tester grønne** (16 nye, ni mutasjoner satt rødt først). Ingen migrasjon
— `Ressurs.enhet` har pekt på `oppdrag.Enhet` siden fase 2.

113 klikker på en enhet i sentralbordet og ser hvem som er i bilen: navn,
rolle og innsjekkstatus, med de som faktisk er der øverst.

- **Avhengighetsretningen går én vei: `vaktliste` → `oppdrag`** (§6).
  Oppdragsmodulen importerer ikke vaktlista; sentralbordet henter
  `/vaktliste/api/enhet/<pk>/besetning/` og rendrer svaret. Koblingen ligger i
  nettleseren, ikke i Python — samme grep som lot statistikkappen slutte å
  importere pasientmodulen. `OppdragImportererIkkeVaktlista` leser importene
  med AST og håndhever det.
- **Gaten er `les` i vaktliste, ikke i oppdrag.** Komposisjonsregelen fra
  rollemodellen §5: en operatør med oppdragstilgang men uten vaktlistetilgang
  får ikke avledet innsyn i hvem som går vakt — panelet finnes ikke for henne.
- **Svaret er innskrenket med vilje.** Navn, rolle og innsjekkstatus. Ikke
  telefonnummer, ikke kompetanseliste, ikke `notat`: sentralbordet skal se om
  bilen er klar, ikke lese personalmapper. En test leser rå-svaret og krever
  at ingen av feltene er der.
- **Bare skiftene som dekker nå.** «Er bilen bemannet» er et annet spørsmål
  enn «hvem har vakt i helga», og en liste med tretti rader over to døgn
  svarer ikke på noe man kan handle på.
- **Ukoblet er ikke ubemannet.** 404 mot 200-med-null: ubemannet er et problem
  her og nå, ukoblet er et oppsett som mangler, og de to skal ikke se like ut.
- **Hentes når operatøren spør**, ikke ved hver polling — enhetslista pollet
  hvert par sekund ville gitt ett kall per bil per runde. Bufferet tømmes når
  lista faktisk endret seg, *etter* 304-sjekken; tømte vi det på hver runde,
  ville et åpent panel stått på «Henter…» for alltid.

**Rettet før det rakk ut:** første utgave sorterte besetningen på
`rolle__navn`, som er nullbar — og **SQLite (dev) og PostgreSQL (prod)
plasserer NULL i hver sin ende**. Lista ville stått i ulik rekkefølge lokalt og
i drift, en feil man aldri ser før den betyr noe. Sorteres nå i Python: de som
er i bilen først, så alfabetisk.

**Og en test som ikke målte noe:** «ressurs i en annen vakt teller ikke» ga
begge ressursene samme navn, så den gikk grønt uansett hvilken endepunktet
fant. Funnet ved mutasjonstesting, to ganger — andre forsøk trengte også
`rekkefolge=0` på den andre raden for at den skulle vinne uten vaktfilteret.

---

## 2026-08-30 — Vaktliste fase 5: planleggingstall

**1902 tester grønne** (45 nye, sytten mutasjoner satt rødt først). Ny fane
«Planlegging»: hva vakta koster dem som går den.

- **Per person: timer, skift, lengste skift, korteste hvile.** Sortert på
  timer synkende — den som er i ferd med å bli brukt opp skal ligge øverst,
  ikke på rad tolv i en alfabetisk liste.
- **Varsler, ikke sperrer.** Et skift over grensa eller en hvile under den
  merkes, og det er alt. Ingenting avvises: noen ganger *må* noen ta et langt
  skift, og da skal lista si det høyt framfor å tvinge planleggeren til å lyve
  om tidene for å komme videre. Fargen er **gul, ikke rød** — et langt skift
  er ikke galt, det er noe man skal se og ta stilling til.
- **Grensene er organisasjonens, ikke portalens.** Ny modell
  `Belastningsgrenser` (migrasjon `0010`), én rad, standard 12 t skift og 8 t
  hvile. `skriv_leder` flytter dem: det endrer hva *alle* vaktlister varsler
  om, og er en beslutning om hvordan organisasjonen bemanner.
- **Faktisk mot planlagt.** Har noen stemplet både møtt og av vakt, kommer en
  «Faktisk»-kolonne opp ved siden av planen. Et *pågående* skift får ingen
  faktisk tid — et anslag som endrer seg mens man ser på det er ikke et tall.
  Kolonnen står bare når det finnes noe å vise; en kolonne med bare streker
  stjeler bredde fra dem som betyr noe.
- **Ledige plasser telles i sammendraget, ikke i persontabellen.** De er et
  behov, ikke en belastning, og en rad uten navn i en persontabell ser ut som
  en feil.
- **Overlapp gir hvile 0, ikke et negativt tall.** To lister på samme tid er
  noe planleggeren skal se, men et negativt tall i en «korteste hvile»-kolonne
  ser ut som en regnefeil framfor et varsel.

**To lærdommer, begge fra mutasjonstesting:**

- Sorteringen inne i `_hviletider()` lot seg fjerne uten at noe ble rødt,
  fordi `Vaktpost.Meta.ordering` alt sorterer på `fra_tid` — testene gjennom
  basen målte *modellens* ordering, ikke hjelperens. Nå prøves hjelperen
  direkte, med usortert inndata.
- `test_steget_er_et_helt_minutt` leste *alle* `step="…"` på sida, og ble rød
  den dagen et `<input type="number">` fikk `step="1"` — riktig for et tall,
  meningsløst for et klokkeslett. Den leser nå bare `datetime-local`-felt.

**Ikke levert, og det står i notatet:** kompetansedekning per ressurs («har
samleplassen helsepersonell hele åpningstiden») er merket som mulig utvidelse,
ikke første leveranse.

---

## 2026-08-30 — Drifttabellen bytter form

**1857 tester grønne** (6 nye, fem mutasjoner satt rødt først). André: «Møtt-
knappen er ikke helt på plass ennå.» Han hadde rett, og målingene sa hvorfor.

**Slik den var:** 45 × 21 px — den *minste* kontrollen på raden — på x=1092,
mens navnet sto på x=41. Tusen piksler fra navnet du leser til knappen du skal
treffe, og bak en sidescroll, siden tabellen er 1377 px og ruller på både 1440
og 1180 px. På skjermen leste den som enda en liten grå knapp etter
Timer/Kompetanse/Merknad.

**Slik den er:** 171 × 44 px på x=49, først i raden, og tabellen får plass
uten sidescroll.

- **Tabellen har to former, og drift er den andre.** Under drift legges
  planleggingsfeltene bort: tidene vises som tekst i stedet for
  `datetime-local`, og kompetanse og merknad tas ut. Det er de tre som gjør
  raden 1377 px bred, og ingen av dem røres mens man sjekker folk inn. Uten
  dem er det plass til at stempelet kan være stort.
- **Lista kan fortsatt endres** — folk uteblir og bytter — men gjennom
  blyanten, som åpner redigeringsvinduet.
- **Uten stemplerett vises statusen** i stedet for en knapp. `les` ser hele
  lista, og «hvem har møtt» er samme spørsmål enten man kan svare på det eller
  ikke.

**Lærdom:** jeg leste notatet for tynt. Det sto «to store knapper per rad,
**ikke et redigeringsskjema**», og jeg behandlet den andre halvdelen som en
omskrivning av den første. Den var en egen instruksjon om *raden*. Da jeg i
forrige runde begrunnet én knapp med at «to knapper i en kolonne på 5 % blir
to små knapper», var den riktige slutningen at kolonnen var feil — ikke at
knappen skulle bli én.

---

## 2026-08-30 — Vaktliste fase 4: drift

**1851 tester grønne** (45 nye, sytten mutasjoner satt rødt først). Modellen
bar feltene fra fase 2, så fasen er endepunkter og flate — **ingen migrasjon**.

- **Drift er en innsjekk-port, ikke en livssyklus** (§5). `POST
  .../drift/start/` og `.../drift/stopp/` — retningen står i URL-en, ikke i
  kroppen: et veksle-endepunkt gir et kappløp når to trykk kommer tett, og den
  som trykket sist vet ikke hva hun endte på. Ut av drift er reversibel og
  **rører ingen stempler**; det er en dør, ikke en sletting.
  - Knappen står ved statuslinja den endrer. Lå den i «Innstillinger», måtte
    man åpne et vindu for å se om innsjekken var åpen — og det er det første
    man vil vite når vakta begynner.
- **Møtt og av vakt, som navngitte overganger.** Ett endepunkt per overgang,
  og kroppen leses ikke — samme grep som oppdragsmodulens stemplinger.
  Reglene er **data** i `services.STEMPLINGER`, ikke `if`-er i viewet.
  - Forutsetningene er ikke pedanteri: «av vakt» uten «møtt» gir en rad som
    sier at noen gikk av en vakt hun aldri kom til, og `er_tilstede` leser
    nettopp de to feltene sammen. Å angre «møtt» mens «av vakt» står gir
    samme rad. Begge stenges ett sted.
  - To trykk på samme knapp gir samme rad, ikke en rød boks — men det første
    tidspunktet er det som skjedde, og det flytter seg ikke.
- **Korps-føreren stempler ikke** (avklaring 11.3). Hun setter opp sine egne
  folk, men «Tilstede nå» er brannsikkerhet, og det tallet skal ha én
  ansvarlig — ikke ett per korps. Verifisert i nettleseren: hun ser hverken
  drift-knappen eller stemplene.
  - Tilgangsporten svares **før** driftporten, med vilje: en korps-fører som
    trykker skal få vite at hun ikke har lov, ikke at lista ikke er i drift —
    et råd som fører henne til en knapp hun heller ikke har.
- **«Tilstede nå» — modulens mest alvorlige visning.** Tellingen står øverst,
  stor: i en evakuering teller man hoder mot et tall. Definisjonen er
  knivskarp — møtt, og ikke gått av vakt — og utledet av stemplene, aldri
  lagret. Lista er gruppert på ressurs og kan skrives ut; strøm og nett er det
  første som ryker i nettopp situasjonen den finnes for.
  - Fanen finnes bare i drift. I planlegging er den tom per definisjon, og en
    fane som alltid sier null er en fane man slutter å se.
  - Den er lesbar for alle med `les`. I en evakuering er flere lesere bedre
    enn færre, og det er samme data lista alt viser.

**Ett avvik fra notatet, med vilje.** Det ba om «to store knapper per rad».
Det ble **én** — den som gjelder nå — pluss en liten angre. Raden er i
nøyaktig én tilstand: «Møtt» på en som alt har møtt gjør enten ingenting eller
noe hun ikke ba om, og to knapper i en kolonne på 5 % blir to *små* knapper,
altså det motsatte av bestillingen. Stemplene står i handlingskolonnen, som er
`sticky` og den ene som aldri ruller bort.

---

## 2026-08-30 — Cron-jobbene skal si hva som gikk galt

**1806 tester grønne** (12 nye). To cron-jobber i staging — `purge_old_logs` og
`kollaps_arkiv` — falt på `FATAL: password authentication failed for user
"postgres"`. Årsaken var en feil `DATABASE_URL` på cron-tjenestene, og André
rettet den i Railway. Det som er gjort her, er å sørge for at neste gang blir
lettere å se.

- **Én lesbar linje i stedet for fire stablede tracebacks.**
  `core/kommando.py::lesbar_dbfeil()` gjør en `OperationalError` om til en
  `CommandError`: jobben avslutter fortsatt med kode 1 og meldes fortsatt som
  feilet, men loggen sier hva som ikke ble gjort, hvorfor, og hva man skal se
  på. Psycopg2 gjentar seg selv — den gjentakelsen klippes bort, og
  `raise … from` beholder hele sporet for den som vil ha det.
  - **Alle tre jobbene bruker den**: `purge_old_logs`, `kollaps_arkiv` og
    `db_backup`. Den som blir glemt er den som feiler uleselig den dagen det
    haster, og for backupen er «den dagen» per definisjon en dag noe alt har
    gått galt.
- **Den stille SQLite-fallbacken er stengt.** `dj_database_url.config()`
  faller tilbake til en fil i containeren når `DATABASE_URL` mangler. På
  Railway er den filen tom og flyktig — og fallbacken er *stille*.
  `purge_old_logs` ville talt null rader i en tom base, skrevet «Slettet 0
  audit-logger» og avsluttet med kode 0: **en grønn jobb som aldri håndhever
  lagringstidene i A.9.** Det er en verre feil enn krasjen, fordi den ikke
  oppdages før noen spør hvorfor det ligger fire år med logger i basen.
  Oppstarten stopper nå høylytt, som ved manglende `SECRET_KEY`.
  - Sjekken henger på `RAILWAY_ENVIRONMENT`, ikke på `DEBUG`: offline-modus
    kjører `DEBUG=False` på en laptop og *skal* bruke SQLite.

**Lærdom, funnet ved mutasjonstesting:** offline-testen gikk grønt uansett
hvordan sjekken var skrudd sammen, fordi utviklermiljøet kjører `DEBUG=True`.
Den beviste ingenting før den satte `DEBUG=False` eksplisitt. Samme feil som
sist runde: en test kan gå grønt uten å teste formen den beskriver.

**Merk at `ALLOWED_HOSTS` ikke var årsaken** — den leses av request-håndteringen,
og en cron-container betjener aldri en forespørsel. Det står fortsatt et eget
punkt i TODO om å ha både `portal.sanitet.net` og Railway-domenet der til
domenet er verifisert.

---

## 2026-08-30 — Tidsfeltene: fem minutter, og datoen står der

**1794 tester grønne** (7 nye). Andrés punkt: `datetime-local` er fin på mobil
og knotete på desktop. Feltet er beholdt som det er — samme native velger,
samme visning — men to ting rundt det er endret.

- **`step="300"` på alle sju tidsfeltene.** Piltastene og velgeren hopper fem
  minutter, ikke ett. En vakt planlegges ikke på minuttet, og standardsteget
  gjorde et kvarter til tolv piltrykk. Steget er et multiplum av 60, så feltet
  får *ikke* et sekundsegment i tillegg. Verifisert i nettleseren:
  `08:00 → 08:05 → 08:20`.
- **«Opprett vakt» står på vaktas startdato**, ikke på klokka nå. Feltet var
  tomt, så hele datoen måtte tastes for hvert eneste skift — tolv siffer der
  fire holder. Vaktas start og ikke `new Date()`: en oktobervakt planlegges i
  august, og «i dag» er da et årstall på avveie.
  - Fikset på veien: feltene sto helt urørt ved åpning, så de bar tidene fra
    forrige gang vinduet var åpent — på en annen bil, i en annen gruppe.
- **Et eldre skift på 08:03 blir ikke rørt.** `step` styrer bare hva
  piltasten og velgeren *tilbyr*; verdien vises og leses tilbake som før.
  Nettleseren regner feltet som ugyldig, men ingenting leser
  `checkValidity()` og ingen CSS farger `:invalid`. Notert i malen, fordi en
  framtidig `was-validated` ville gjort de radene røde uten grunn.

Vaktas egen start og slutt er fortsatt `datetime-local` med full dato: de
settes én gang per vakt, og der *er* datoen informasjonen.

---

## 2026-08-30 — Mannskapet flytter inn i planleggingen

**1787 tester grønne** (7 nye, og en håndfull skrevet om). Registersiden
`/vaktliste/registre/` er **lagt ned**; mannskapet er en fane på `/vaktliste/`,
korps og kompetanser ligger i «Innstillinger».

Argumentet for en egen side holdt ikke i bruk: registrene er globale og fanene
gjelder én vakt, men et klikk til registeret kostet deg plassen i
planleggingen — og mannskap og ressurser er nettopp de to man veksler mellom.

- **«Mannskap» er en ekte fane**, ikke en lenke med pil ut av sida. Fanen bærer
  antallet i registeret, tabellen har søk og sortering som før, og skjemaet er
  det samme.
- **Fanen står også når det ikke finnes noen vaktliste**, og velges automatisk
  da. Korps må inn før mannskap, og mannskap før noen kan settes på vakt — lå
  registeret bak en vaktliste, sto man fast på skritt én. Av samme grunn åpner
  «Innstillinger» seg uten en liste; bolkene som gjelder én vakt skjules.
- **Korps og kompetanser ligger i «Innstillinger»**, sammen med
  ressursgruppene. De røres sjelden, og de er portalens oppsett — ikke denne
  vaktas. Lista og skjemaet står i **samme vindu**: vinduet åpnes selv fra
  «Innstillinger», og et tredje lag er ett lag man ikke finner tilbake fra.
- **Tomt register uten korps sier «Legg inn korps»**, ikke «Nytt mannskap».
  Knappen åpnet korpsvinduet uansett — en knapp som gjør noe annet enn det den
  heter, klikker man på én gang og stoler aldri på igjen.
- **En lagret person henter både registeret og vaktlista.** Navn, korps og
  aktiv-flagget står i nedtrekkene på planleggingssiden også; uten begge
  bemannet man fra en liste som var utdatert.
- `vaktliste-registre.js` og `registre.html` er **slettet**, ikke bare koblet
  fra. En fil ingen laster er en fil som råtner uten at noe feiler — en test
  krever nå at de er borte.

Verifisert i nettleseren hele veien: tom portal → korps → kompetanse →
mannskap → fanen ved siden av «Ambulanse», med nedtrekket i planleggingen
oppdatert av lagringen.

---

## 2026-08-30 — Ny ressurs spør bare om det man vet

**1777 tester grønne** (18 nye). Niende runde fra Andrés bruk, og tre punkter
som alle handler om det samme: skjemaet skal ikke be om svar man ikke har ennå,
og knappen skal ikke tilby noe som ikke finnes.

- **«Ny ressurs» spør bare om navn og gruppe.** Reservert korps og enhet i
  oppdragsmodulen sto i opprettelsesskjemaet, men hører hjemme ett nivå lavere
  etter at reservasjonen flyttet til plassen: koblingen settes på den enkelte
  bilen, i «Rediger». Å spørre om dem ved opprettelsen ga et skjema man måtte
  fylle ut før man visste svaret — og det leste som om gruppa *var* enheten.
- **Ingenting opprettes i oppdragsmodulen på veien.** André mistenkte at en ny
  gruppe også lagde en enhet. Verifisert i nettleseren at den ikke gjør det:
  `grupper: 6 → 7`, `ressurser: 0`, `enheter: 0`. Det som *så* slik ut var
  skjemaet over, som ba om en enhet man ikke hadde.
- **Samleplass og KO finnes i ett eksemplar.** Nytt felt
  `Ressursgruppe.flere_enheter` (migrasjon `0009`), av for de to gruppene
  migrasjon `0007` seeder som samlingspunkt for flere korps. «Samleplass 2» er
  ikke en ny samleplass, det er en delt vaktliste ingen leser riktig. Den
  *første* må man fortsatt kunne opprette, så plassen tar slutt først når den
  ene står der. Nye grupper er flåter som standard — huket av i
  gruppevinduet gjør dem til ett eksemplar.
  - Regelen står som **én funksjon** (`gruppaHarPlass()`) fordi den har to
    lesere: knappen inne i fanen og nedtrekket i «Ny ressurs». Første runde
    skjulte bare knappen — og da kunne man fortsatt velge gruppa i nedtrekket,
    altså en regel som var halvveis. Serveren avviser den også: en regel som
    bare finnes i klienten er ingen regel.
  - Sperren er **per vaktliste**. Var den global, kunne neste vakt ikke hatt
    samleplass i det hele tatt.
- **Migrasjon `0009` har dataskrittet sist**, etter `AddField`. Da er det ingen
  skjemaendring igjen som triggerkøen kan avvise — motsatt av `0007`, som måtte
  tømme køen. Kjørt fra bunnen mot ekte PostgreSQL, og
  `verifiser_migrasjoner` går grønt.

**Lærdom:** en test som går grønt kan likevel teste en vei brukeren ikke har.
Første utgave av «den første enheten kan alltid opprettes» leste `mkGruppe()` —
men en tom gruppe har ingen fane, så den koden tegnes aldri. Veien inn til den
første går gjennom nedtrekket, og det var det som måtte testes.

---

## 2026-08-30 — Bil A, bil B, bil C: veien inn var usynlig

**1759 tester grønne** (11 nye). Bare grensesnitt — men det som manglet var det
André satt fast på i flere runder, og det var min feil å ikke se det.

**Modellen var riktig hele tiden: én `Ressurs` per bil, inne i gruppa, hver med
sin egen enhetskobling.** Det var *veien dit* som ikke fantes.

- **Gruppefanen har nå sitt eget hode med «Ny Ambulanse»-knapp.** Den eneste
  måten å legge til en bil på lå sist i fanerekka og het «Ny ressurs». Fra
  inne i «Ambulanse»-fanen så man én rad med knapper og ingen antydning om at
  fanen rommer bil A, bil B og bil C — man trodde gruppa *var* bilen. Hodet
  sier nå «Ambulanse · 3 enheter · 12 skift», og knappen ved siden av lager
  den fjerde.
- **Tomme grupper forklarer hva de rommer.** «Ingen Ambulanse satt opp ennå.
  Hver enhet er sin egen rad her — én per bil, lag eller post — med egne skift
  og egen kobling mot oppdragsmodulen.» Med knappen ved siden av.
- **Enhetskoblingen vises også når den mangler.** Merkelappen sto bare der
  bilen *var* koblet, så den som ikke hadde koblet noe så ingenting — og kunne
  ikke vite at koblingen finnes per bil i det hele tatt. Nå står «Ikke koblet»
  som en stiplet plass som åpner redigeringsvinduet.
- **Ressursgrupper har fått en flate.** `/api/grupper/` fantes fra i går uten
  noe som brukte det — nøyaktig feilen Django-admin ga oss én gang før: et
  register som bare finnes i API-et, finnes ikke for brukeren. Man kunne ikke
  lage «Førstehjelpstelt», bare velge blant de seks migrasjonen seedet.
  Manageren ligger i Innstillinger, med «i bruk»-telling og sletting sperret
  for grupper som er i bruk.
- Tre mutasjoner prøvd, alle røde.

**Lærdom.** Tre runder gikk med til at jeg forsvarte en modell som var riktig,
mens brukeren beskrev at han ikke fant veien inn i den. «Det er ikke synlig»
er ikke en uenighet om arkitektur — det er en feilmelding om grensesnittet, og
den skulle vært lest som det med én gang.

## 2026-08-30 — Utskriftslista sorterer og grupperer på noe som betyr noe

**1756 tester grønne** (8 nye). Bare grensesnitt.

- **Sorteringen stoppet på `fra_tid`.** André så det i sine egne rader: et
  skift som slutter 22:15 lå som nummer tre blant skift som slutter 03:00
  neste dag. Alle begynte 17:00, så de var uavgjort — og resten var
  innsettingsrekkefølge forkledd som sortering. `_skiftrekkefolge()` sorterer
  nå på fra, så til, så navn, og brukes både på arket og i ressurstabellen.
- **Utskriftslista er gruppert på ressurs, ikke på korps.** Den som leser
  lista står ved bilen eller på samleplassen og spør «hvem er her, og når?».
  Korpset er et kjennetegn ved personen, ikke et sted — det er en kolonne nå,
  ikke en overskrift. Overskriften er ressursen, med gruppa og antallet ved
  siden av.
- **En ledig plass viser korpset den er satt av til.** Ellers sto de
  reserverte plassene som «—» på arket, og reservasjonen var usynlig akkurat
  der den skal brukes.
- **Ressurser uten skift tas ikke med på arket.** En tom tabell på papiret er
  en linje man må lese for å se at det ikke står noe der.
- Arkhodet teller ledige plasser — tallet man planlegger etter.
- Tre mutasjoner prøvd. Én overlevde: testen på reservasjonen i lista lette
  etter et korps som også sto på de bemannede radene, så den ville vært grønn
  uansett. Den bruker nå et korps som *bare* finnes på de ledige plassene.

## 2026-08-30 — Reservasjonen ned på plassen

**1748 tester grønne** (10 nye). Migrasjon `vaktliste.0008`, rent additiv.

- **`Vaktpost.korps`: en plass kan settes av til ett korps.** Andrés
  innvending, og den var riktig: `Ressurs.korps` reserverer *hele* ressursen
  til ett korps, men en samleplass bemannes av flere. Uten dette måtte
  samleplassen deles i én ressurs per korps — og da er den ikke lenger én
  samleplass. Nå kan den ha to plasser til Haugesund og én til Karmøy, i
  samme tabell.
- **De to nivåene slås sammen ett sted**, `services.reservert_korps()`. Tom
  verdi på plassen betyr «som ressursen», ikke «ingen» — ellers ville alle
  eksisterende plasser blitt fritt vilt ved oppgraderingen. Migrasjonen er
  derfor ren `AddField`: oppførselen er uendret til noen faktisk setter et
  korps på en plass.
- **Å reservere er å dele ut, og krever `skriv_full`.** Korps-brukeren fyller
  plassene som er satt av til henne; hun bestemmer ikke hvilke. Mutasjonstesting
  avslørte at den første testen min ikke prøvde regelen i det hele tatt —
  plassen tilhørte et annet korps, så inngangsporten stoppet henne før
  reservasjonssjekken. Testen som faktisk biter bruker en plass hun *får* ta
  i, og viser at hun likevel ikke kan skrive om hvem den tilhører.
- **Korpskolonnen svarer nå på to ulike spørsmål.** Står det en person der, er
  det *hennes* korps — et faktum. Er plassen ledig, er det korpset plassen er
  *satt av til* — en beslutning, redigerbar i raden for den som deler ut.
- **«Sett på vakt» heter nå «Opprett vakt».** Knappen lager en plass, som ofte
  er tom; «sett på vakt» lovet en person.
- **Kurven tegnes selv når gruppa ennå ikke har et eneste skift.** Den falt
  bort i akkurat den tilstanden man setter opp i, og det var feil på samme
  måte som at kurven en gang bare dekket skiftene: hullet man planlegger for å
  tette er størst når ingen er satt opp, og da forsvant hele kurven.
- Tre mutasjoner prøvd. Én overlevde og fikk testen beskrevet over.

## 2026-08-30 — Fanen er gruppa, ikke bilen

**1737 tester grønne** (23 nye). Bare grensesnitt.

- **Én fane per ressursgruppe, ikke per ressurs.** «Ambulanse» er nå alle
  ambulansene som skal på vakt, med hver bil som sitt eget kort inni. Én fane
  per bil ga ti faner på en vakt med ti biler, og ingen plass der man kunne se
  dem i sammenheng — som er nettopp det man planlegger etter. Gruppekurven
  ligger øverst i fanen, over de ressursene den summerer, og tallet på fanen
  teller skiftene i hele gruppa.
- **Det som er per ressurs blir stående på ressursen.** Enhetskoblingen mot
  oppdragsmodulen, korpsreservasjonen, rollene og «Sett på vakt» hører til den
  enkelte bilen, og ligger derfor på kortet inne i fanen — ikke på gruppa.
- **«Ny ressurs» forhåndsvelger gruppa du står i.** Står du i
  «Ambulanse»-fanen er det oftest en ambulanse til du skal lage. Det er
  fortsatt et nedtrekk, så den første ressursen i en ny gruppe har også en vei
  inn. Etter opprettelsen åpnes gruppas fane; sletter du den siste ressursen i
  en gruppe, forsvinner fanen og «Oversikt» tar over.
- **Innstillinger står nå til venstre for «Ny vaktliste».** Begge handler om
  vakta som helhet, og hører derfor på vaktlinja.
- **Mannskap er flyttet inn i fanerekka, rett etter «Oversikt»** — dit man
  veksler oftest. Den er fortsatt en lenke og ikke en fane, og bærer en liten
  pil: fanene bytter innhold i panelet under, denne forlater sida. Uten pila
  koster et klikk deg plassen din uten å ha spurt.
- Fem mutasjoner prøvd, alle røde: bare første ressurs vist i fanen, tomme
  grupper som faner, fanetallet som bare teller én ressurs, Mannskap flyttet
  ut av posisjon, og pila fjernet.
- **En feil jeg gjorde underveis, verdt å notere:** da jeg byttet ut hele
  regionen mellom to funksjoner, forsvant `visFane`, `_ikkePlassert` og
  `skrivUt` med den. Testene fanget det umiddelbart — men et
  `git diff | grep '^-function'` før commit er billigere enn å lete i en rød
  suite.

## 2026-08-30 — «Ny ressurs» inn i fanerekka, Mannskap ned til fanene

**1728 tester grønne** (5 nye). Bare grensesnitt.

- **«Ny ressurs» står sist i fanerekka**, som pluss-fanen i en nettleser. Den
  lå til høyre for hele rekka og leste som enda en handling på sida; en
  ressurs *er* en fane, så knappen hører hjemme der fanene slutter. Stiplet
  kant skiller den fra fanene som faktisk er noe.
- **Tilgangen måtte flytte med.** Knappen lå i malen og ble skjult av
  `gateKnapper()` ved sidelasting. `tegnFaner()` tegner på nytt ved hvert
  panelbytte, så en klasse satt én gang rekker ikke over den — `kanLede()`
  sjekkes nå rett i byggeren. Mutasjonstestet: uten sjekken ser bemanneren en
  knapp som gir 403.
- **Mannskap er flyttet ned til fanene, men står utenfor rekka.** Fanene
  bytter innhold i panelet under; Mannskap forlater sida. En knapp som ser ut
  som en fane og navigerer bort er en felle — den har derfor skillelinje foran
  og beholder knappeformen. Nærheten er poenget: fanene og
  mannskapsregisteret er de to stedene man veksler mellom.

## 2026-08-30 — Rediger-knappen innenfor skjermen, og en topp som er ryddet

**1723 tester grønne** (2 nye). Bare grensesnitt.

- **Ressurstabellen krympet fra 82rem til 66rem.** Den første verdien hadde
  slark: tidsfeltene fikk 210 px der de trenger 185, og prisen var at
  rediger-knappen i siste kolonne lå utenfor skjermen selv på en stor laptop.
  Målt i nettleseren nå: tabellen ruller ikke i det hele tatt fra 1280 px og
  opp, mot 1600 px før.
- **Og handlingskolonnen henger fast til høyre.** Under 1280 px ruller
  tabellen fortsatt, og da var rediger-knappen det første som forsvant — altså
  den ene knappen raden finnes for. `position: sticky` holder den i syne;
  bakgrunnen settes eksplisitt, ellers ruller innholdet synlig under den.
  Verifisert med tabellen rullet helt til venstre på 1000 px.
- **Toppen av siden er tre nivåer i den rekkefølgen man tenker.** Før lå alt
  på én linje: hvilken vakt man planla, hvem man er, hva man vil lage — og
  vaktas navn sto midt inne i en knapperad og leste som en innstilling. Nå:
  sida øverst (Mannskap, Innstillinger), så en egen linje for vakta med
  velgeren, statusen og «Ny vaktliste», og til slutt fanene med «Ny ressurs»
  ved siden av seg. «Ny ressurs» hører til fanene fordi en ressurs *er* en
  fane; «Ny vaktliste» hører til velgeren fordi den lager noe velgeren skal
  peke på.
- **«Vakta» heter nå «Innstillinger».** Et substantiv blant handlinger, og
  det sa ikke hva som lå bak.
- **Kurven er ute av «Oversikt».** Den sto samlet der før hver gruppe fikk sin
  i sin egen fane, og to steder å lese den samme kurven er ett for mye. På
  papiret var den uansett skjult, så «Oversikt» er nå utskriftslista og bare
  det. `mkKurve()` er slettet framfor å bli stående ubrukt.
- Tre mutasjoner prøvd, alle røde — for smal tabell, tidskolonner krympet på
  bekostning av «Timer», og kurven snek tilbake inn i «Oversikt».

## 2026-08-30 — Rediger skiftet, og en kurve som sier når

**1722 tester grønne** (15 nye). Ingen migrasjon — alt ligger i grensesnittet;
serveren tok allerede alt redigeringsvinduet trenger i én PUT.

- **Skiftet redigeres, det slettes ikke og settes opp på nytt.** Å bytte
  person på en rad krevde før å fjerne den og begynne forfra — og da mistet
  man tidene og rollen som allerede sto der. Blyanten i raden åpner et vindu
  med mannskap, rolle, tider og merknad; alt går i ett kall, og serveren
  sjekker den doble regelen på nytt mot den som skal inn. Å velge «— ledig
  plass —» tar personen av uten å miste plassen i oppsettet.
- **Sletting av et skift ligger inne i vinduet, bak en bekreftelse.** Samme
  grep som på ressursen: den nakne søppelbøtta i raden var ett feilklikk fra
  å fjerne noe.
- **Bemanningskurven står i fanen den gjelder.** Ambulansefanen viser
  ambulansenes kurve, samleplassen sin. Å lete etter samleplassens bemanning
  under «Oversikt» mens man bemanner samleplassen er ett skifte for mye.
  «Oversikt» viser fortsatt alle gruppene samlet, til den som vil sammenligne
  dem.
- **Klokkeslett under søylene, og toppen oppgitt med tidspunkt.** «topp 4
  plasser kl. 14:00–18:00» svarer på spørsmålet kurven finnes for; å lese det
  av søylehøyder er å gjette. Timeaksen har én celle per søyle med samme
  flex-bredde, så tallet står under den timen det gjelder — målt i nettleseren
  på tvers av alle søylene. Tettheten glisner med lengden (hver time opp til
  14, deretter hver andre, fjerde, sjette): tall som står oppå hverandre gjør
  kurven uleselig av å være «mer informativ».
- **Den hvite streken er midnatt, ikke nåværende tidspunkt.** André måtte
  spørre, og en strek man må spørre om forklarer ingenting — den står nå i
  tegnforklaringen. Den er beholdt: arrangementer varer flere døgn, og
  døgnskillet er det man orienterer seg etter.
- Fem mutasjoner prøvd. Én overlevde — at bare første klokkeslett ble skrevet
  ut — fordi testen talte celler og ikke hvor mange som hadde tall i seg. Den
  teller nå begge deler.

## 2026-08-30 — Migrasjonsprøver mot ekte PostgreSQL

**1713 tester grønne** (4 nye, én hoppes over uten PostgreSQL). Lukker hullet
den statiske regelen fra forrige runde ikke nådde.

- **`core/migrasjonsprover.py` + `python manage.py verifiser_migrasjoner`.**
  Hver migrasjon som skriver rader og deretter endrer skjema må ha en prøve:
  `foregaaende` sier hvor basen settes, `seed` legger inn rader i den
  *historiske* formen med rå SQL, `sjekk` leser hva migrasjonen gjorde med
  dem. Kommandoen lager sin egen engangsbase, kjører prøven, og sletter den —
  den rører aldri basen URL-en peker på.
- **Å kjøre testsuiten mot PostgreSQL ville ikke fanget feilen.** Det var det
  TODO-punktet sa, og det var feil. Djangos testbase lages ved å kjøre
  migrasjonene mot en *tom* base: dataskrittet finner ingenting å flytte,
  skriver ingenting, og fyller ingen triggerkø. Feilen krever tre ting
  samtidig — PostgreSQL, rader, og en skjemaendring etter skrivingen — og det
  er nettopp de tre prøven setter opp.
- **Prøven kjører `migrate` i en underprosess mot `default`**, ikke som et
  andre databasealias. Atten migrasjoner i prosjektet gjør ORM-kall i
  `RunPython` uten `schema_editor.connection.alias`, altså mot `default`; med
  et alias ville de skrevet til utviklerens egen base i stedet for prøvebasen,
  og prøven ville målt noe annet enn den later som. Underprosessen kjører
  dessuten nøyaktig den stien release-fasen kjører.
- **Fem mutasjoner, alle røde.** To fanges ved at migrasjonen kræsjer —
  deriblant «hjelperen står, men kallstedet er fjernet», som er akkurat det
  den statiske regelen *ikke* ser. Tre fanges av påstandene: ukjent
  ressurstype som faller til feil gruppe, en pensjonert rolle som blir aktiv
  i kopien, og roller som ikke viftes ut til alle grupper. De tre migrerer
  helt fint og gir bare gale data — den slags feil finnes det ellers ingen
  sperre mot.
- **Testsuiten håndhever registeret**, ikke bare regelen: en ny migrasjon med
  mønsteret må ha en prøve, en prøve må peke på en migrasjon som finnes, og
  `foregaaende` må finnes. Uten det tredje feiler prøven på sitt eget oppsett
  og ser ut som dekning man ikke har.
- Kjøres med `MIGRASJONSPROVE_DATABASE_URL` satt; hoppes over ellers.
  Serveren kan være en lokal PostgreSQL eller en egen Postgres-tjeneste i
  Railway — se CLAUDE.md.

## 2026-08-30 — Deployfiks: migrasjonen som kræsjet på PostgreSQL

**1709 tester grønne** (3 nye). Ingen ny migrasjon — `vaktliste.0007` er rettet
på plass, og den har aldri blitt anvendt noe sted.

- **`vaktliste.0007` tok ned deployen i crash-loop.** PostgreSQL svarte
  `cannot ALTER TABLE "vaktliste_ressursrolle" because it has pending trigger
  events`. Årsaken: Djangos fremmednøkler er `DEFERRABLE INITIALLY DEFERRED`,
  så hver skriving i dataskrittet legger en triggerhendelse i kø som først
  fyres ved commit — og migrasjonen er én transaksjon. `ALTER TABLE` på en
  tabell med hendelser i køen avvises. Løst med `SET CONSTRAINTS ALL
  IMMEDIATE` mellom dataskrittet og skjemaskrittene, i begge retninger.
- **Reprodusert før den ble rettet.** En lokal PostgreSQL 16 ble satt opp,
  basen rullet tilbake til `0006`, ekte rader lagt inn — ressurser, en rolle,
  vaktposter — og `0007` kjørt: samme feil, ord for ord. Etter rettelsen går
  den gjennom, dataene står riktig (rollene viftet ut per gruppe, hver
  vaktpost på sin egen gruppes kopi, `gruppe_id` NOT NULL, `type`-kolonnen
  borte), og veien tilbake til `0006` virker også. Hele historikken kjører
  dessuten rent fra tom base.
- **Databasen trengte ingen opprydding.** Migrasjonen er atomisk, så den
  rullet helt tilbake ved hver feilede oppstart; basen sto på `0006`.
- **Testsuiten kunne ikke se feilen, og det er det egentlige problemet.**
  SQLite har ingen utsatte triggere — en migrasjon som rører rader og deretter
  endrer skjema er noe dev-basen ikke kan si noe om i det hele tatt.
  `DataOgSkjemaISammeTransaksjonTests` flytter regelen inn i suiten: skriver en
  migrasjon rader og gjør noe som blir til `ALTER TABLE` etterpå, må den enten
  tømme køen, sette `atomic = False`, eller deles i to. Åtte eldre migrasjoner
  har mønsteret og står i `KJENTE_UNNTAK` — alle er anvendt i produksjon, og
  hele historikken er kjørt fra null mot PostgreSQL for å bekrefte at de ikke
  feller på en tom base.
- **Mutasjonstesting fant en svakhet i sperren.** Første versjon lette etter
  strengen i fila, og gikk grønn når kallet ble fjernet mens docstringen som
  *forklarer* regelen sto igjen. En migrasjon som omtaler sperren er ikke en
  migrasjon som har den. Nå leses fila med AST, og strengen må stå som
  argument i et kall. Grensen som står igjen er notert i testen: den ser at
  kallet finnes, ikke at det kjøres — det krever å kjøre suiten mot
  PostgreSQL, som nå står i TODO.

## 2026-08-30 — Ressursgrupper, et ledernivå, og en popup som blinket bort

**1706 tester grønne** (49 nye). Migrasjoner `vaktliste.0007` og
`accounts.0015`. Femte runde på Andrés tilbakemelding, og den største:
tilgangsmodellen fikk et trinn til, og ressurstypen ble en tabell.

- **Ressurstypen er nå tabellen `Ressursgruppe`.** Den lå i `choices.py` med
  den begrunnelsen at et nytt ikon uansett krever deploy. Den holdt ikke: et
  arrangement kan ha et førstehjelpstelt eller en MC-patrulje, og en vaktleder
  som trenger gruppa i kveld kan ikke vente på en utrulling. Ikonet ble et
  felt — feil ikon er en skjønnhetsfeil, en manglende gruppe er en vaktliste
  man ikke får satt opp. Gruppa gjør tre ting samtidig, og det er derfor den
  er én ting: den ikonlegger fanen, den samler bemanningskurven, og den
  avgrenser rollene.
- **Rollen hører til gruppa, ikke til portalen.** «Sjåfør» gir mening på hver
  ambulanse og ikke på samleplassen. Gruppa er riktig nivå og ikke den enkelte
  ressursen: har du tre ambulanser vil du lage rollen én gang, ikke tre.
  Manageren åpnes derfor inne i ressursen — «Roller»-knappen i kortets topp —
  og navnet er unikt *per gruppe*. Migrasjonen vifter hver eksisterende rolle
  ut til alle seks gruppene og peker vaktpostene på kopien som hører til sin
  egen ressurs' gruppe. Å gjette hvilken gruppe «Lagleder» *egentlig* hørte
  til ville tatt rollen bort fra rader som lovlig brukte den; noen ubrukte
  rader man kan slette er den billige feilen.
- **Nytt nivå: `skriv_leder` («Skrive: leder — setter opp vakta»).** Det
  fjerde trinnet i `NIVAA_HIERARKI`, og det første siden stigen ble laget.
  Skillet mot `skriv_full` er hva slags skade en feil gjør: bemanneren setter
  folk på plasser og kan rette tilbake; lederen oppretter og fjerner ressurser
  og vaktlister, endrer vaktas lengde og lager roller og grupper — og en
  fjernet ressurs tar bemanningen med seg. `skriv_full` beholder alt som
  handler om å bemanne, inkludert utskriften. Terskelen er ikke global admin,
  og det er hele poenget: en vaktleder skal kunne sette opp sin egen vaktliste
  uten å få brukeradministrasjon, backup og arkiv på kjøpet. Vaktlista er den
  eneste modulen som deklarerer nivået, så det er additivt for de andre.
- **«Fjern ressurs» ligger bak «Rediger ressurs», og krever bekreftelse to
  ganger.** Knappen sto naken ved siden av «Sett på vakt», og CASCADE tar
  skiftene: ett feilklikk kostet hele bemanningen på bilen. Nå må man inn i
  vinduet, bekrefte i dialogen, og serveren krever i tillegg
  `{"confirm": true}` — dialogen stopper feilklikket, kroppen stopper et kall
  som treffer URL-en uten å mene det.
- **Vaktas lengde og utskriften er samlet i ett vindu for vakta.** To løse
  knapper i toppen konkurrerte med «Ny ressurs» om plassen uten å høre til
  samme spørsmål. Utskriften er åpen for alle som ser lista — den er hele
  grunnen til at bemanneren har den; lengden inne i vinduet krever
  `skriv_leder`.
- **Kolonnene i ressurstabellen leser nå som ett strekk:** Navn, Korps, Rolle,
  Fra, Til, Timer, Kompetanse, Merknad. «Dag» er borte som egen kolonne — den
  var et tredje sted å lese for å forstå én rad, og `datetime-local` bærer
  datoen selv; det manglet bare ukedagen, som nå står under feltet den hører
  til. «Timer» er nytt, og er det ene tallet man ellers regner ut i hodet for
  hver rad: «20:00 til 04:30» er ikke åtte timer.
- **Kompetansekolonnen flyttet seg fordi cella var `display: flex`.** En
  `<td>` med flex slutter å være en `table-cell` og faller ut av kolonnesporet,
  så alt etter den forskyves i forhold til overskriftene — `table-layout:
  fixed` hjelper ikke mot det. Layouten ligger nå på et element *inne* i cella.
  `TabellcellersLayoutTests` leser hvilke klasser som står på `<td>`-ene og
  krever at ingen av dem får en `display` som bryter tabellen, så neste
  cellemerkelapp fanges av samme test.
- **Bemanningskurven følger grupperingen.** Én samlet kurve summerte
  samleplassen, ambulansene og KO til ett tall, og det tallet svarer ikke på
  noe: fire på samleplassen og null på ambulansen ser likt ut som to og to.
  Kurvene deler spenn, så søylene ligger under hverandre — to kurver man ikke
  kan sammenligne er verre enn én samlet. Grupper uten et eneste skift tegnes
  ikke.
- **«En kort popup som forsvinner» var to lyttere på samme element.**
  Nedtrekkene i ressurstabellen er `<select data-action="…"
  data-hendelse="change">`, og klikkdelegeringen i `portal-utils.js` traff dem
  også: klikket som åpnet lista kalte handlingen uten felt og verdi, sendte en
  tom PUT, og tegnet panelet på nytt — så lista ble revet bort i det øyeblikket
  den kom. Regelen er nå `klikkSkalKjore()`: et element som melder sin egen
  hendelse fyrer ikke på klikk. Den traff hver celle i tabellen, ikke bare
  nedtrekket, så hvert klikk i et tekstfelt kostet en tom skriving og en full
  ny-tegning.
- Elleve mutasjoner prøvd. Én overlevde — kompetansecellas layout — og fikk
  testen over. Verifisert i nettleser: kolonnene står på linje med
  overskriftene på 1600, 1280 og 1000 px, og klikk på nedtrekket gir null kall
  og null ny-tegninger.

## 2026-08-30 — Ressursroller, og kolonner som blir stående

**1659 tester grønne** (12 nye). Migrasjon `vaktliste.0006`. Fjerde runde på
Andrés tilbakemelding, og den korteste: to ting han pekte på etter å ha brukt
planleggingssiden.

- **`VaktRolle` heter nå `Ressursrolle`.** Navnet var misvisende på den måten
  navn er farlige: rollen gjelder plassen på ressursen — lagleder *på bilen*,
  sjåfør *på bilen* — ikke vakta. «Vaktrolle» leste som noe man har på hele
  vakta, og en modul der to begreper heter nesten det samme får de to
  forvekslet før den får dem forklart. Migrasjonen er en ren `RenameModel`;
  ingen rad flyttes.
- **Rolleadministrasjonen flyttet fra registersiden til planleggingssiden.**
  Rollene brukes der ressursene settes opp, og de var det eneste registeret man
  måtte forlate siden for å endre. Nå ligger de bak «Roller» i toppen av
  `/vaktliste/`, med «i bruk»-tellingen i lista — en rolle man kan slette uten å
  se hvor mange skift som peker på den, sletter man for lett. Registersiden har
  tre faner igjen: mannskap, korps og kompetanser.
- **Nedtrekket i raden tilbyr bare aktive roller — pluss den raden alt står
  på.** Uten det siste ville en deaktivert rolle forsvunnet fra sin egen rad ved
  første tegning, og en tilfeldig annen rolle blitt valgt neste gang noen rørte
  cella.
- **Kolonnene i ressurstabellen flyter ikke lenger inn i hverandre.** Årsaken
  ble målt i nettleseren, ikke gjettet: `datetime-local`- og tekstfeltene var
  bredere enn cellene sine på alle skjermbredder. `min-width` opp til `82rem`,
  `<colgroup>`-andelene rebalansert, og `box-sizing: border-box; min-width: 0`
  på feltene. Målt igjen på 1600, 1280 og 1000 px: ingen kolonne beveger seg,
  ingen felt stikker ut.
- **To mutasjoner overlevde første runde, og fikk hver sin test.**
  `RessurstabellensBreddeTests` regner ut hva tidskolonnene faktisk blir i
  piksler av `min-width` og `<colgroup>`-andelene, og krever at de rommer et
  datetime-felt — den låser *regelen*, ikke tallene, så en rebalansering som
  fortsatt holder er lov. `RollenedtrekketTests` kjører filteret i node.

## 2026-08-30 — Vaktlengde, ledige plasser og en kurve over hele vakta

**1647 tester grønne** (33 nye). Migrasjon `vaktliste.0005`. Tredje runde på
Andrés tilbakemelding, og den som endret modellen mest.

- **`Vaktpost.mannskap` er nullbar: en ledig plass er et skift som mangler en
  person.** Planlegging begynner med behovet — «Lag 1 trenger fire, én av dem
  lagleder» — og personene fylles inn etter hvert. En egen plassholder-modell
  ville duplisert tider, rolle og ressurs, og gjort «å fylle plassen» til en
  flytting mellom to tabeller i stedet for én feltendring. `antall` lager flere
  like plasser i ett kall; NULL er ikke lik NULL i unik-skranken, så fire tomme
  plasser til samme tid går fint.
- **Vakta kan få og endre en lengde.** Starten redigeres på `Vakt.startet` — den
  *er* starten — mens planlagt slutt er et nytt felt på `Vaktliste`.
  `Vakt.avsluttet` betyr «vakta ble avsluttet», en hendelse noen utløste, og kan
  ikke bære et anslag man flytter på mens man planlegger. Året følger starten,
  fordi vakta kan flyttes over et årsskifte og `year` er portalens scope-nøkkel.
- **Kurven dekker hele vakta, ikke bare skiftene**, og viser to tall per time:
  fylte plasser i mettet farge, alle plasser i lys. Avstanden mellom dem er det
  som gjenstår å bemanne. Uten vaktas spenn var hullet i begynnelsen usynlig
  nettopp fordi ingen er satt opp der ennå. Mangler sluttiden, faller den
  tilbake på skiftene — bedre en kurve som dekker for lite enn ingen kurve.
- **Utskriftslista holdes i sin egen ramme.** Tabellene arvet `min-width` fra
  `.vl-tabell` uten en ramme rundt seg og stakk ut av kortet; på papiret
  nullstilles begge deler. Ledige plasser samles i sin egen gruppe til slutt —
  de hører ikke til noe korps ennå.
- **Regelen måtte deles i to, funnet av en ny test.** `kan_sette_vaktpost` spør
  om et *par* kan opprettes (og `mannskap=None` er å planlegge, altså
  `skriv_full`). `kan_rore_vaktpost` spør om brukeren får ta i en rad som
  finnes. Brukt den første til begge, låste den korps-brukeren ute av akkurat de
  plassene som var satt av til henne. Og å *avlyse* en ledig plass er
  `skriv_full`: korpset fyller plasser, det skjuler ikke hull ved å slette raden
  som viste dem.
- Mutasjonstestet åtte veier, alle røde.

---

## 2026-08-30 — Planleggingssiden: regneark, datoer, utskrift og bemanningskurve

**1614 tester grønne** (15 nye). Kun frontend og serialisering — ingen migrasjon.
Andre runde på Andrés tilbakemelding.

- **Ressursen er et regneark.** Rader er skift, kolonner er det man
  sammenligner på tvers av dem: Navn · Korps · Kompetanse · Rolle · Dag · Fra ·
  Til · Merknad. Rolle, tider og merknad redigeres **der de står** — cellene ser
  ut som celler til man er i ferd med å endre dem. Avviser serveren endringen
  (et skift som slutter før det begynner), rulles raden tilbake til det som
  faktisk er lagret, og meldingen står over tabellen.
- **Rollen flyttet dit arbeidet skjer.** Den lå allerede riktig i modellen — på
  vaktposten, ikke på personen — men i grensesnittet kunne den bare settes i
  «Sett på vakt»-modalen. Å endre den krevde å fjerne skiftet og sette det opp
  på nytt. Samme person er sjåfør på bilen én vakt og lagleder på samleplass
  neste.
- **Kompetansekolonnen** følger vaktposten, så et lags sammensetning kan
  vurderes uten å bla til registeret. Stigen gjelder også her: AFØR skjuler GFØR.
- **Dato og dag, ikke bare klokkeslett.** Et skift lørdag 20:00 til søndag 04:00
  sto som «20:00–04:00», uten at noe sa at det krysset midnatt. Dagen nevnes én
  gang når skiftet holder seg innenfor et døgn og to ganger når det ikke gjør
  det; vaktvelgeren viser datoen; vaktas spenn utledes av skiftene framfor å
  være et felt noen må vedlikeholde.
- **«Oversikt» er utskriftslista.** Hele vakta på ett ark, gruppert på korps,
  med en «Skriv ut»-knapp. `@media print` fjerner nav, faner, knapper og kurve —
  en knapp på et ark er bare blekk — og en korpsgruppe brytes ikke over to sider.
- **Bemanningskurven** står over lista: én søyle per time, døgnskillet markert,
  hullene synlige. Rene CSS-søyler framfor Chart.js, som kun lastes på
  `/statistikk/`.
- **To kanter funnet av de nye testene.** `new Date(null)` gir epoken (1970), ikke
  en ugyldig dato — et tomt tidsfelt ville vist «01:00» i stedet for ingenting.
  Og `toISOString()` i `datetime-local`-feltene ville gitt UTC og flyttet hvert
  skift to timer om sommeren.
- Mutasjonstestet ni veier, alle røde til slutt. Den ene som ikke bet med én
  gang — kompetansene fjernet fra vaktpost-svaret — avdekket at
  ressurstabellens data var utestet; fem nye tester dekker den nå, inkludert at
  PUT-svaret har samme form som lesestien (ellers ville kolonnen tømt seg selv
  i det man endret rollen).

---

## 2026-08-30 — Mannskapstabellen: kolonnene flyter ikke lenger inn i hverandre

**1599 tester grønne** (4 nye). Kun frontend.

Meldt av André: en person med mange kompetanser blåste opp kompetansekolonnen
og skjøv telefon og konto ut av linje med radene over — nøyaktig det tabellen
skulle løse.

- **Årsaken var `table-layout: auto`.** Der sizer nettleseren kolonnene etter
  innhold, og `max-width` på en `td` er bare et forslag. Nå `table-layout:
  fixed` med et `<colgroup>` som setter andelene, så innholdet brytes inni cella
  i stedet for å dytte naboene. Målt i nettleser på 1400, 1000 og 780 px: alle
  radene har identiske kolonneposisjoner, og ingenting flyter ut av cella.
- **Handlingsknappene ble ikoner.** «Rediger» + «Slett» som tekst trenger
  ~150 px og sprengte sin egen kolonne på smal skjerm. `title` og `aria-label`
  bærer betydningen, og knappene har fast bredde så kolonnen ikke hopper mens
  ikonfonten laster.
- **Fire regresjonstester**, fordi hver av bitene ser overflødig ut ved siden av
  de andre: `table-layout: fixed` ser unødvendig ut når det står et `<colgroup>`
  der, og omvendt. Begge trengs — den ene slår av innholdsbasert sizing, den
  andre sier hva andelene skal være.

Sidevis vannrett rulling på 780 px kommer fra portalens header, ikke fra
tabellen, og bare i testmiljøet: Bootstrap-CSS er CDN-sperret der, så
brukermenyen står åpen i stedet for skjult.

---

## 2026-08-30 — Registersiden: kompetansestige og mannskapstabell

**1595 tester grønne** (15 nye). Migrasjon `vaktliste.0004`. Første runde på
Andrés tilbakemelding fra å faktisk bruke modulen.

- **Mannskapslista er en tabell.** Med én kompetanse så den gamle
  merkelapp-raden fin ut; med åtte brøt den om og skjøv telefonnummeret ut av
  syne. Faste kolonner — Navn · Korps · Kompetanse · Telefon · Konto — gjør at
  det du leter etter alltid står samme sted. Sticky kolonnehode, sortering på
  navn/korps/telefon, og et søkefelt som filtrerer på alt inkludert kompetanse.
  Søkefeltet ligger **utenfor** panelet som tegnes på nytt; lå det inni, mistet
  det fokus etter første bokstav.
- **`Kompetanse.bygger_paa`: en stige, ikke en rangering.** AFØR bygger på VFØR,
  som bygger på GFØR. Har personen AFØR, er de to under implisert og vises ikke
  — hele settet ligger i `title` på cellen, så «har hun egentlig VFØR?» kan
  besvares uten å åpne skjemaet. En peker framfor et rangtall fordi et tall
  måtte være globalt, og da ville «Sykepleier» og «Sjåfør kode 160» fått en
  innbyrdes rekkefølge de ikke har. Ringer stoppes ved skriving; en ring som
  likevel finnes i basen gir en avkortet kjede, ikke en evig løkke. SET_NULL:
  fjernes VFØR, står AFØR igjen frittstående.
- **Funn i nettleseren, ikke i testene: registerfanene viste «ubrukt» på et
  korps med mannskap.** Siden tegner dem fra mannskapsendepunktets nyttelast,
  ikke fra `/api/korps/`, og de to formene var skrevet hver for seg — så
  `i_bruk` og `bygger_paa_navn` nådde aldri fram. Hver test spurte det
  endepunktet den selv beskrev, og så det ikke. Nå deler begge veier én
  `verdi_til_dict()`, og `SammeFormBeggeVeierTests` sammenligner dem direkte.
- Mutasjonstestet seks veier på stigen, alle røde: stigen ignorert, kjeden
  avkortet til ett trinn, sykkelvernet fjernet, «bygge på seg selv» sluppet
  gjennom, ringvernet i kjeden fjernet, og CASCADE i stedet for SET_NULL.

---

## 2026-08-30 — `rekkefolge` ut av verdimengdene: alfabetisk holder

**1580 tester grønne** (6 nye). Migrasjon `vaktliste.0003`.

**Andrés innvending, og den var riktig.** Feltet ga allerede alfabetisk: hver
rad sto på standardverdien 100, så `ordering = ['rekkefolge', 'navn']` falt
uansett tilbake på navnet. Det vi hadde var altså alfabetisk sortering med et
tallfelt i skjemaet som pris — et felt du måtte se på og lure på hva «100»
betyr mens du skrev «Sykepleier».

- **Fjernet fra `Korps`, `Kompetanse` og `VaktRolle`.** Ingen tallfelt igjen i
  grensesnittet. Trygt å droppe kolonnene: modulen har aldri vært i prod.
- **Beholdt på `Ressurs`, men brukeren skriver ikke tallet.** Der *betyr*
  rekkefølgen noe — den styrer fanene på planleggingssiden — og alfabetisk ville
  stokket om på den operative rekkefølgen («Ambulanse, KO, Lag 1, Mannskapsbil
  1» framfor samleplass, biler, lag, KO). `services.neste_rekkefolge()` setter
  den til «sist», så fanene følger den rekkefølgen du la ressursene inn i.
  Steget på 10 gir plass til å skyte inn en ressurs den dagen noen vil
  omorganisere.
- **Funn fra den nye testen: «alfabetisk» er databasens alfabet.** SQLite
  sorterte «Åsen» før «Ærlig» og ville sortert «karmøy» etter begge; PostgreSQL
  svarer annerledes på begge. Sorteringen bruker derfor `Lower(...)`, som gjør
  store/små bokstaver deterministisk i enhver base. **Æ/Ø/Å står vi igjen med
  databasens svar på** — en ekte norsk kollasjon krever en sorteringsnøkkel eller
  `db_collation`, og for en håndfull korps er det ikke verdt det. Notert i TODO.
  Testen sier det samme: den prøver store/små bokstaver, ikke æ/ø/å, fordi en
  test på det siste ville målt hvilken base som kjørte den.
- Mutasjonstestet fire veier, alle røde: `Lower()` fjernet, `neste_rekkefolge`
  som alltid gir 10 (kolliderende faner), telling på tvers av vaktlister, og
  ressursen tilbake på fast 100.

---

## 2026-08-29 — Vaktlistemodulen fase 3: tilgangsmodellen tas i bruk

**1574 tester grønne** (48 nye). Ingen migrasjon. `admin_only` er av — modulen
er åpen for nivåene.

Fase 2 skrev reglene og lot dem stå ubrukte bak en admin-gate; fase 3 håndhever
dem, per objekt, på hvert endepunkt. Tre terskler, og skillet mellom dem er
*hva slags utsagn* nivået får avgi:

| Handling | Krav |
|---|---|
| Lese lista og registeret | `les` — hele lista, **alle** korps (§4.4) |
| Bemanne en ressurs, føre eget mannskap | badge **og** reservasjon (§4.2) |
| Dele ut ressurser, planlegge vakt, styre verdimengdene | `skriv_full` |
| Slette en vaktliste | global admin — irreversibelt |

- **Den doble regelen håndheves nå der den står i veien for noen.** Badgen på
  personen *og* reservasjonen på ressursen, som én funksjon
  (`services.kan_sette_vaktpost`). En ureservert ressurs er fortsatt ikke et
  fristed.
- **Verdimengdene er `skriv_full`.** Kunne korps-brukeren opprette korps, kunne
  hun lage seg et nytt å føre — og badgen hennes ville sluttet å avgrense noe.
  Samme resonnement stengte «endre reservasjonen på en ressurs»: den korteste
  veien rundt hele regelen er å sette `korps` på KO til sitt eget og bemanne den
  etterpå.
- **To felter på `Mannskap` er unntatt badgen.** `korps_id` sjekkes mot *begge*
  korps — sjekket vi bare det personen har i dag, kunne hun eksporteres ut av
  rekkevidde; bare målet, og andres kunne hentes inn. `user_id` er `skriv_full`
  fordi koblingen flytter en badge: kontoen arver korpset, og dermed hva *den*
  kontoen får redigere. Sperren står både på POST og PUT — ellers er den ene
  bare en omvei rundt den andre.
- **§4.5 løst: etikett per modul per nivå.** `Module.nivaa_navn` er par framfor
  `dict` fordi dataklassen er frosset og hashable. Matrisen og «Min profil»
  viser nå «Skrive: eget korps» på vaktlista og «Skrive: stempling» på oppdrag,
  der begge før het «Skrive: handling». Nivået er det samme; betydningen er det
  ikke, og den som deler ut skal se hvilken.
- **Grensesnittet gater på `window.MODUL_TILGANG`**, og badgen sendes med slik
  at nettleseren kan regne ut det samme som `kan_bemanne_ressurs()`.
  Verifisert i nettleser som korps-bruker: «Sett på vakt» vises kun på egen
  ressurs, «Ny vaktliste»/«Ny ressurs» og kontofeltet er borte, og Rediger/Slett
  står bare på eget korps sine folk.
- **Kontolista sendes bare til den som kan bruke den.** `user_id` er
  `skriv_full`-felt, og en liste over portalens brukernavn er ikke noe en
  korps-fører trenger for å føre lista si.
- Mutasjonstestet tolv veier. Elleve bet; den tolvte — reservasjonssjekken
  fjernet fra JS-ens `kanBemanne()` — gjorde det **ikke**: serveren stoppet
  kallet uansett, så hullet var kosmetisk. Men det er nettopp den slags hull som
  overlever til noen stoler på grensesnittet, så JS-gatingen kjøres nå i node
  (`GrensesnittetsGatingTests`), og de tre JS-mutasjonene bet etterpå.

---

## 2026-08-29 — Registersiden: portalen får tilbake det Django-admin gjorde

**1534 tester grønne** (43 nye). Ingen migrasjon. Ny side på `/vaktliste/registre/`.

**Funnet av André, og det er et hull fase 1 og 2 begge gikk forbi.** Registrene
kunne bare fylles fra Django-admin, og den flaten er kun rutet under `DEBUG` og
`OFFLINE_MODE` (S1). I produksjon fantes det altså ingen vei til å opprette et
korps eller et mannskap i det hele tatt — planleggingssiden hadde en
nedtrekksliste som aldri kunne fylles, og banneret på den pekte brukeren mot en
dør som ikke finnes. Fase 1 skrev til og med i `admin.py` at Django-admin var
«riktig hjem» for registrene.

**Ingen test var rød.** Alle testene laget radene sine med ORM-en, så ingen av
dem gikk den veien en bruker må gå. Testene på registersiden går derfor gjennom
HTTP hele veien — fra tom base til bemannet vakt — og
`SjekkAtIngenPekerPaaDjangoAdminTests` skanner alle maler for at det ikke skal
skje igjen.

- **Mannskapslista er gruppert på korps med kompetansene synlige**, ikke en flat
  admin-tabell: det var slik bestillingen beskrev den. Inaktive rader vises
  nedtonet framfor å forsvinne — pensjonering er den normale veien ut, ikke en
  feiltilstand, og raden må kunne leses av den som skal aktivere den igjen.
- **Egen side, ikke en fane på planleggingssiden.** Registrene er globale;
  fanene på `/vaktliste/` er ressursene i én vakt. To omfang i samme faneliste
  ville sagt at «Mannskap» hører til oktobervakta.
- **De tre verdimengdene deler fabrikk** (`_register_views`), som
  `patients/views_registre.py` gjør for navneregistrene. Korps har ett felt til,
  og fabrikken tar derfor en liste over valgfrie tekstfelter framfor å bli to
  fabrikker.
- **Sletting er ikke veien ut av et register.** `Korps`, `VaktRolle` og
  `Mannskap` er PROTECT-et, og `Kompetanse` blokkeres eksplisitt selv om M2M-en
  ikke ville protestert — å slette den ville stilltiende strippet kompetansen fra
  alle som har den. Antall bruk vises i lista, ikke bare i feilmeldingen: en
  verdimengde man kan slette uten å vite hva som henger i den, sletter man for
  lett.
- **Funn underveis, fanget av en av de nye testene:** et HTML-nedtrekk med «Ingen
  valgt» sender `''`, ikke `null`. Sendt rett inn i et FK-filter kaster Django
  `ValueError`, og brukeren fikk 500 der hun skulle fått «velg korps». Alle
  ID-er fra klienten går nå gjennom `_int()` — også i planleggingsviewene, der
  `or None` dekket den tomme strengen, men ikke en ikke-numerisk.
- Mutasjonstestet seks veier. Fem bet med én gang; den sjette — korps som teller
  bare mannskap og ikke reserverte ressurser — gjorde det **ikke**, fordi
  `ProtectedError`-fallbacken ga 409 uansett. Testen sjekket bare statuskoden.
  Den leser nå `i_bruk`-tallet, som er det eneste telle-sjekken faktisk styrer:
  uten den står et korps som eier et lag oppført som «ubrukt», og da trykker man
  slett i god tro.

---

## 2026-08-29 — Vaktlistemodulen fase 2: oppsettet og planleggingssiden

**1491 tester grønne** (68 nye). Migrasjon `vaktliste.0002`. Siden ligger på
`/vaktliste/`, og modulen er synlig for global admin.

Tre modeller til: `Vaktliste` (1:1 med `core.Vakt`), `Ressurs` og `Vaktpost`.

- **Reservasjonen er `Ressurs.korps`** (§4.2 i notatet). `skriv_full`/admin deler ut
  et lag eller en bil til et korps; korps-brukeren bemanner bare det som bærer hennes
  egen badge. **Tom er ikke fritt fram** — det er vaktlederens bord, typisk KO og
  samleplass. Motsatt tolkning ville gitt enhver korps-bruker de to ressursene ingen
  hadde tenkt å dele ut.
- **Den doble regelen er én funksjon.** `services.kan_sette_vaktpost()` sjekker både
  badgen på personen og reservasjonen på ressursen, slik at et endepunkt ikke kan huske
  den ene og glemme den andre. Reglene håndheves først i fase 3 — modulen er admin-only
  til da, fordi et nivå som slipper inn uten korps-regelen ville gitt korps-brukeren
  *alle* korps.
- **«Ny planlagt vakt» rører ikke portalens peker.** `opprett_planlagt_vakt` lager en
  `core.Vakt` med `er_aktiv=False` og lar `aktiv_vakt_id` stå: oktobervakta skal kunne
  planlegges i august uten at pasienter og oppdrag registrert i dag scopes til den.
  Dette er portalens andre sted som lager `Vakt`-rader, og det er notert i TODO sammen
  med `hent_aktiv_vakt`.
- **Kopiering tar oppsettet, aldri personene.** En liste ingen har sagt ja til er verre
  enn en tom liste — den ser ferdig ut.
- **Plan og faktisk er fire felter, ikke to.** `fra_tid`/`til_tid` er planen,
  `mott_at`/`av_vakt_at` hva som skjedde. Avviket mellom dem er selve informasjonen.
  Feltene finnes fra denne fasen, men ingen sti setter dem før fase 4.
- **Et skift er én rad.** Går Per to skift på bilen, er det to `Vaktpost`-rader. Det er
  det som gjør timer, hviletid og skiftlengde (§8b) til spørringer i stedet for tolkning.
  Overlapp *på tvers av* ressurser stoppes bevisst ikke — planleggingstallene flagger det.
- **Funn underveis: `IntegrityError` må fanges rundt et savepoint.** Uten
  `transaction.atomic()` rundt skrivingen er transaksjonen ubrukelig etter at skranken
  slår til, og sesjonslagringen på vei ut av forespørselen river feilmeldingen bort og
  etterlater en naken 400-side. Feilen var usynlig for en test som bare leste
  statuskoden; testene leser nå `message`.
- **Ryddet en stale import**: `myproject/tests_cache_config.py` importerte fortsatt
  `patients.stats_cache`, som flyttet til `core` da statistikk ble sin egen app. Testen
  hadde vært rød siden da, men ligger utenfor den daglige testkommandoen.
- Mutasjonstestet åtte veier, alle røde: ureservert ressurs som fristed, `and` → `or` i
  den doble regelen, kopiering som tar personene, planlagt vakt som blir aktiv,
  opprettelse som flytter pekeren, `<=` → `<` på skifttidene, savepointet fjernet, og
  admin-gaten fjernet fra ett endepunkt.

---

## 2026-08-29 — Vaktlistemodulen fase 1: registrene og mannskapet

**1404 tester grønne** (15 nye). Migrasjon `vaktliste.0001`.

Ny app `vaktliste/` med fire modeller: `Korps`, `Kompetanse` og `VaktRolle` som
admin-styrte tabeller — motsatt av oppdragsmodulens `choices.py`, fordi dette er
organisasjonsdata, ikke faglige verdimengder — og `Mannskap`, portalens tredje
personregister og det første over **egne frivillige**.

- **`Mannskap.korps` er badgen** tilgangsmodellen hviler på fra fase 3. PROTECT:
  korpset skal ikke kunne rives bort under folkene. Navn er unikt per korps, ikke
  globalt — to korps kan ha hver sin Ola Hansen. Kontokoblingen er SET_NULL og gir i
  seg selv ingen tilgang, som `Enhet.user`.
- **`notat` er unntatt verdilogging i audit fra første lagring**, etter mønster av
  `Oppdrag.fritekst` og med samme rekkefølgekrav: kostbehov skal ikke inn i portalen
  (§7 i notatet), og fritekst er der helseopplysninger havner når det ikke finnes et
  felt for dem. Mutasjonstestet begge veier: fjernes unntaket, lekker verdiene til
  loggen og en test blir rød; fjernes rå-sammenligningen, gir hver lagring en falsk
  «notat endret»-rad og en annen test blir rød.
- **Personvernprotokollen hevet til v1.10**: ny A.6-seksjon for mannskapsdata
  (berettiget interesse, art. 6(1)(f) — en annen registrertgruppe enn pasientene) og
  A.9-rader med pensjonering som normal vei ut av registeret.
- **Modulen er registrert, men usynlig**: `url=None` og begge `show_*`-flagg av, som
  oppdragsmodulen i sin fase 1 — den får side i fase 2. Nivåene er deklarert som
  besluttet, med merknad om at `skriv_handling` her betyr «fører sitt eget korps».

---

## 2026-08-29 — Beslutningsnotat: vaktlistemodulen

Ingen kode. `docs/BESLUTNING_VAKTLISTE.md` er skrevet for å gjøre de seks
avklaringene i §11 mulige å svare på, og for å få de to tunge tingene på bordet før
første linje kode — slik oppdragsnotatet gjorde.

**Den ene er tilgangsmodellen.** Bestillingen innfører portalens andre akse: en bruker
fra korps Z skal kunne redigere korps Z og ingen andre. Rollemodellen har hittil hatt
én akse — en ordnet stige per modul — og statistikk ble i sin tid skilt ut som egen
modul nettopp for å slippe to akser i én. Notatet anbefaler å utlede scopet fra
`Mannskap.korps`, altså fra domenedata, framfor å legge det i en tildelingstabell:
da betyr `skriv_korps` noe alene, og det finnes ingen ekstra rad å glemme. Idiomet er
det samme som `Enhet.user` i oppdragsmodulen, der koblingen avgjør hvilket
grensesnitt kontoen får uten selv å gi tilgang.

**Den andre er kostbehov.** Matallergi er en helseopplysning, altså en særlig
kategori etter GDPR art. 9, og dette er første gang portalen ville lagret slikt om
*egne frivillige* framfor om pasienter. Notatet foreslår fem tiltak som må stå før
feltet tas i bruk — smal verdimengde, samtykke som grunnlag, snevrere synlighet enn
resten av lista, unntak fra verdilogging, og ingen arkivering — og legger dem i en
egen fase 2 som står **før** feltet ships. Samme rekkefølgekrav som audit-unntaket i
oppdragsmodulen, av samme grunn: rader skrevet feil kan ikke fjernes i ettertid uten
å røre sporet.

Notatet dekker ellers ordboken (fire ord som ligner: vakt, vaktliste, ressurs,
vaktpost), modellene, livsløpet planlegging → drift, koblingen til `/oppdrag` — som
går én vei, `vaktliste` → `oppdrag`, med panelet hentet i nettleseren slik
statistikkappen gjør — og forholdet til de to personregistrene som finnes fra før.

**Seks avklaringer besvart samme dag, og tre av dem endret utformingen:**

- **Korps er en badge, ikke en ny akse.** Forslaget om nivået `skriv_korps` er
  forkastet: stigen portalen har holder. `skriv_handling` betyr «fører sitt eget
  korps», `skriv_full` «alle korps» — og `skriv_full` er dessuten den eneste som
  stempler møtt og av vakt. Skillet mellom de to skrivenivåene er ikke bredde, men
  art: å føre inn sine egne folk er planlegging, å stemple noen inn er et utsagn om
  hva som faktisk skjedde. Ingen ny verdi i `NIVAA_HIERARKI`, ingen migrasjon.
  Prisen er notert: nivånavnet betyr noe annet her enn i oppdragsmodulen, og matrisen
  viser en global etikett — så det trengs en valgfri etikett per modul per nivå,
  ellers deles nivået ut i god tro med feil forventning.
- **Matallergi lagres ikke i portalen.** Grunnen til at utkastet trengte fem tiltak
  rundt feltet, er også grunnen til at det ble tatt ut: det er en helseopplysning
  etter art. 9, og fem mekanismer for én kolonne som skal brukes til å bestille mat er
  feil pris. Samles inn utenfor portalen. Konsekvensen står i notatet: lista kan ikke
  brukes til matbestilling. Utkastets fase 2 utgår, og personvernarbeidet som blir
  igjen — rader i protokollen, audit-unntak for `notat` — flyttes inn i fase 1.
- **Pasientmodulens to personregistre forblir urørt.** Heller ingen valgfri kobling:
  de svarer på «hvem behandlet pasienten», ikke «hvem er på vakt». Prisen er at et
  navn kan stå to steder, og den er akseptert — en nullbar FK er en additiv migrasjon
  den dagen behovet melder seg.

**Andre runde samme dag besvarte resten, og notatet står som besluttet:**

- **Ressurser reserveres til korps.** `skriv_full`/admin tildeler lag, mannskapsbiler
  og ambulanser til korpsene; korps-brukeren bemanner bare ressurser med sin egen
  badge, med skifttider. KO og samleplass står typisk ureservert og er
  `skriv_full`/admins bord. Regelen er dobbel og håndheves per objekt: personen må ha
  badgen, ressursen må være reservert korpset.
- **Drift er kun en innsjekk-port, og den er reversibel.** «Sett i drift» åpner
  møtt/av vakt, «ut av drift» stenger den igjen; stemplene består. Ingen kobling til
  portalens aktive vakt — spørsmålet fra utkastet falt bort med svaret.
- **To bruksområder kom til:** planleggingstall (timer per person, hviletid mellom
  skift, skiftlengder, bemanningskurve, admin-styrte varselgrenser — varsler, ikke
  sperrer) og en tilstedeoversikt som brukes av brannsikkerhetshensyn ved overnatting.
  Den siste er modulens mest alvorlige flate: definisjonen er «møtt og ikke gått av»,
  utledet av stemplene, med telling øverst og en ren utskriftsvisning — papir er
  reserven når strøm og nett ryker.
- **Kopiering fra forrige vakt:** oppsettet (ressurser, reservasjoner, roller), aldri
  personene.

Et skift er en `Vaktpost` med `fra_tid`/`til_tid`; `mott_at`/`av_vakt_at` er hva som
skjedde. Plan og faktisk holdes atskilt fordi avviket mellom dem er selve
informasjonen. Sju faser, 37–49 timer. Ingen kode er skrevet.

---

## 2026-08-29 — Oppdragsmodulen fase 7: vaktarkiv for oppdrag

**1383 tester grønne** (41 nye). Migrasjon `oppdrag.0008`. Med denne er alle sju fasene
i `docs/BESLUTNING_OPPDRAGSMODULEN.md` levert.

**`AbstractArkiv` er endelig bygget.** TODO har utsatt basemodellen til «modell nummer
to faktisk skrives» — `OppdragArkiv` er modell nummer to, og da var det ikke lenger
gjetning hva som er felles: tittel, vakt med frosset navn, antall rader, hvem som
arkiverte med frosset brukernavn, signatur, kollapstidspunkt og aggregat med egen
signatur. `VaktArkiv` er som planlagt **ikke** migrert dit: `year_snapshot` og
`arrangement_navn` inngår i SHA-payloaden til hvert arkiv i prod, og et arkiv som byttet
feltnavn ville meldt tukling. Duplikatet mellom de to modellene er prisen for at
signaturene fortsatt verifiserer.

- **Arkivet fryser vakta, historikken rydder tavla.** To knapper, fordi det er to
  handlinger: historikk flytter ett oppdrag ut av den aktive lista og er reversibel,
  arkivering fryser hele vakta med signatur og starter klokka mot en kollaps som sletter
  radnivået etter 24 måneder. Oppdrag som ligger i historikken arkiveres selvsagt med —
  de er en del av vakta.
- **Tidspunktene fryses i flate kolonner**, én per status, og hvilke stemplinger som var
  automatiske ligger som data ved siden av. Da gjelder §12.2-regelen også i arkivet:
  uten flagget ville en avledet sluttid blitt telt som målt straks vakta var arkivert.
  En test går gjennom statuskjeden og krever en kolonne for hver — legges en status til,
  må arkivet følge med.
- **`fritekst` arkiveres ikke.** Feltet er unntatt verdilogging i audit nettopp fordi det
  kan inneholde noe en operatør skrev og angret på. Å fryse det i et arkiv med 24
  måneders lagringstid ville gjort unntaket meningsløst.
- **Én utregning, to kilder.** `_stats_fra_rader()` regner på nøytrale dicter, og både
  den aktive vakta og arkivet bygger slike — samme grep som pasientmodulens
  `_compute_full_stats_from_dicts`. En test sammenligner arkivets tall mot live rad for
  rad: arkivering skal ikke endre et eneste tall.
- **Statistikkendepunktet fra fase 6 virker nå**, uten at statistikkappen ble rørt.
  Kollapset arkiv leverer det frosne aggregatet — å regne på ingenting ville gitt nuller
  som så ut som målinger.
- **To mangler kom for en dag underveis**, begge reelle:
  - **Modulen hadde ingen backup i det hele tatt.** Arkivet gjorde det synlig (sperren
    foran kollaps krever en backup av modulens arkiv), men mangelen gjaldt hele modulen:
    en vakts oppdrag lå utenfor all dekning utenom Railways databasebackup, som er aktiv
    én måned i året. Nå finnes `oppdrag` og `oppdrag_arkiv`.
  - **`kollaps_arkiv` kjente bare pasientarkivet.** Kommandoen går nå gjennom
    `core.arkiv`-registeret, kjører sperren per modul og navngir modulen som mangler
    backup. `--modul <slug>` avgrenser. Cron-jobben trenger ingen endring.
- **Scheduleren finner moduler gjennom registeret nå.** Den leste
  `ModuleBackupConfig`-radene direkte, og radene ble opprettet først når en admin åpnet
  `/portal-admin/backup/` — så de to nye modulene hadde ingen automatisk backup før noen
  tilfeldigvis besøkte den siden. For `oppdrag_arkiv` var det verre enn en manglende
  fil: uten backup nekter `kollaps_arkiv` å kjøre, så mangelen ville vist seg som en
  blokkert sletting to år senere. Registeret er fasit for hvilke moduler som finnes;
  konfigraden lages med standardverdier første gang scheduleren ser en handler uten en,
  og admin bestemmer fortsatt intervall og av/på. Mutasjonstestet.
- **En testisolasjonsfeil ble avdekket av de nye testene:** `clear_registry()` i
  backup-testene ble ryddet opp med pasientmodulens `register_handlers()`, så
  oppdragsmodulens handlere forsvant for resten av kjøringen — og feilen dukket opp i en
  helt annen fil. `core.backup.registrer_alle_moduler()` går veien om app-registeret, så
  modul nummer tre ikke må huskes.
- **Dokumentasjonen fulgte med:** personvernnotatet er hevet til v1.9 med reviderte
  A.9-rader (merknaden ba selv om revisjon når fasen var levert), og runbookens §10a har
  fått et punkt som navngir begge arkivknappene. Risikoen for å arkivere det ene og
  glemme det andre står nå der den leses, ikke bare i et beslutningsnotat.
- **Verifisert i nettleser:** arkivering, liste, tallene og signaturen, uten JS-feil.
  Mutasjonstestet: fjernes automatisk-flagget fra arkivet, admin-gaten fra endepunktene
  eller backup-sperren foran kollaps, blir testene røde.

---

## 2026-08-29 — Oppdragsmodulen fase 6: statistikkregisteret og oppdragsfanen

**1342 tester grønne** (46 nye). Ingen migrasjoner.

**Statistikkappen navngir ingen kildemodul lenger.** Den importerte `patients.services`
direkte — det virket så lenge det fantes én kilde, og var samtidig hele grunnen til at
kilde nummer to ikke kunne legges til uten å endre appen. `core/stats.py` er registeret,
samme idiom som `core.backup` og `core.arkiv`: hver modul melder inn en
`BaseStatistikkHandler` fra `apps.ready()`, og handleren eier både utregningen og formen
på payloaden. Pasienttallene flyttet ikke en linje — `full_stats()` ligger fortsatt i
`patients/services.py`, og handleren er koblingen.

- **Endepunktene bærer kilden:** `/statistikk/api/kilde/<slug>/full-stats/` og
  `.../arkiv/<pk>/full-stats/`. Ett endepunkt per kilde, ikke ett samlet: en fane som
  ikke er åpnet skal ikke koste noe, og cache-nøkkelen bærer både slug og vakt-ID — delte
  de nøkkel, ville kilde nummer to servert kilde éns tall i 60 sekunder. De gamle stiene
  videresender (302), av samme grunn som pasientmodulens gjorde da endepunktene flyttet:
  en fane som sto åpen da deployen traff feiler ellers stille.
- **Arkivoppslaget gjør handleren**, ikke statistikkappen — `VaktArkiv` er
  pasientmodulens modell, og det var nettopp den importen som skulle bort. Oppdrag
  arkiverer først i fase 7; basisklassen svarer `None`, som blir 404.
- **Tilgangsregelen måtte endres i samme slengen.** §5 sa «vis kun kilder brukeren kan
  lese», men koden ga 403 på hele siden om én kilde manglet. Det var det samme så lenge
  det fantes én kilde; med to ville det tatt statistikken fra alle som leser pasienter
  uten å ha oppdrag. Nå vises kildene kontoen har, og 403 er forbeholdt «ingen kilder».
  En modul som er slått av i `ModuleSettings` forsvinner fra fanene — `har_tilgang`
  svarer nei for den.
- **Oppdragsfanen** viser responstid (opprettet → fremme), ventetid, utrykningstid, tid
  på stedet og hele oppdraget, fordelinger per hastegrad, problemstilling, lokasjon og
  enhet, status akkurat nå, og oppdrag per klokketime. Egen mal og egen JS-fil, lastet
  kun for kontoer med oppdragstilgang; kall fra `statistikk.js` går gjennom
  `_kallOppdrag()`, samme vern som `_kall()` på pasientsiden.
- **§12.2 er besvart (André): den avledede varigheten utelates, ikke oppdraget.** Trykker
  en enhet «Rykker ut» på et nytt oppdrag mens et annet pågår, lukkes det gamle med samme
  tidsstempel og merkes `automatisk`. Sluttiden er da avledet — mannskapet kan ha vært
  ferdig et kvarter før — så varigheter som *slutter* i en slik stempling telles ikke.
  Oppdraget telles i alle antall og fordelinger, og responstiden fram til «Fremme» teller
  som vanlig. Negative varigheter (en klokke som gikk feil offline) telles heller ikke.
  Begge utelatelsene står på siden: et tall som er utelatt uten at noen får vite det, er
  verre enn et tall som mangler.
- **`Statusmelding.objects.gjeldende_bulk()`** kom til fordi statistikken går gjennom
  hele vaktas oppdrag — ett kall per oppdrag ga én spørring per rad. Regelen «nyeste
  ikke-korrigerte rad vinner» står fortsatt bare i manageren, og `gjeldende()` er nå ett
  oppslag i bulk-resultatet. Låst av en test på manageren selv: statistikken ville
  bestått uten regelen, fordi «siste rad per status» tilfeldigvis sammenfaller med den.
- **Verifisert i nettleser**, ikke bare i testene: fanebytte begge veier, tallene mot
  seedede oppdrag, og at et enhetsnavn med markup vises som tekst.

---

## 2026-08-29 — Vakt som scope, deploy 2: vakta er fasit

**1296 tester grønne** (13 nye/omskrevne rundt vakt-semantikken). Migrasjoner
`patients.0016` og `oppdrag.0007`. Forutsetter «Ingen funn» fra `verifiser_vakt` i prod
— det kom samme dag, og deployen er den lesende halvdelen deploy 1 forberedte.

**Migrasjonene er enveis, med vilje.** Begge starter med en sperre som teller rader uten
vakt og stopper med henvisning til `verifiser_vakt` — kjøres deploy 2 mot en base deploy
1 ikke har fylt, skal den nekte, ikke gjette. Revers rammer `RuntimeError`: etter at
`year` er borte fra radene kan koblingen ikke bygges opp igjen når flere vakter deler år.
Rollback er gjenoppretting fra backup, og det står i feilmeldingen.

- **All lesing går på vakta.** `get_active_year`/`set_active_year` er slettet;
  `hent_aktiv_vakt()` er eneste scope-kilde. Pasientliste, statistikk (cache-nøkkel
  bærer vakt-ID), oppdragsvisninger, arkivering og offline-import filtrerer på
  `vakt`-FK-en.
- **`year` er fjernet fra `Patient` og `Oppdrag`.** `VaktArkiv.year_snapshot` står —
  frosset, fordi den inngår i SHA-payloaden til eksisterende arkiver i prod.
  `verifiser_vakt` er krympet tilsvarende: year-sammenligningene mistet grunnlaget og er
  fjernet (ikke gjemt); igjen står arkiv-mot-vakt, pekersjekken og per-vakt-oppsummering.
- **Sperrene bor i basen:** `UniqueConstraint (vakt, pasientnummer)` og
  `(vakt, oppdragsnummer)` erstatter global `unique=True` og per-år-sperren. Numrene
  restarter per vakt; tellerne heter `next_patient_nr_vakt_<id>` /
  `next_oppdrag_nr_vakt_<id>` og selvrepareres fra `Max()` om nøkkelen mangler.
  Migrasjonene flytter driftsverdiene og sletter `active_year`, `next_patient_nr` og
  `event_name` — arrangementsnavnet ER vaktas navn nå, og skrives via
  portalinnstillingene (som validerer unikhet ved omdøping).
- **«Avslutt vakt» erstatter «Nullstill år»** (`/api/avslutt-vakt/`): pre-reset-backup,
  slett vaktas pasienter, merk avsluttet — og ny vakt med påkrevd, unikt fritekstnavn i
  samme flyt, så portalen aldri står uten aktiv vakt. Oppdragene røres ikke (fase 7 sitt
  ansvar). **«Gjenåpne»** (`/api/gjenaapne-vakt/`) bytter aktiv vakt fram til vaktas
  arkiv er kollapset — da finnes ikke radnivået, og døra er låst (mutasjonstestet).
  Gjenåpning henter ikke slettede rader tilbake; de bor i backupen. «Tidligere
  vakter»-lista (`/api/vakter/`, kun admin) viser status og kollaps per vakt.
- **JS-kontrakten består:** `GET /api/settings/` svarer fortsatt `event_name` og
  `active_year`, nå beregnet fra vakta — klienten skal ikke vite at kilden byttet.
- **Testkulturen fulgte med:** `patients.test_helpers.sett_aktiv_vakt(år)` er den ene
  måten tester setter scope på; `year=`-fixturer og `AppSetting['active_year']`-oppsett
  er skrevet om i alle appene.

---

## 2026-08-29 — Vakt som scope: besluttet, og deploy 1 kodet

**1288 tester grønne** (16 nye). Migrasjoner `core.0006`, `patients.0014–0015`,
`oppdrag.0005–0006`.

**Beslutningen er tatt.** André besvarte de fem avklaringene i §7 — alle med notatets
anbefaling: fritekst-vaktnavn (unikt), gjenåpning fram til kollaps, pasientnummer per
vakt (sperren flyttes i deploy 2), manuell sletting av tomme vakter, ingen gruppering nå.
`docs/BESLUTNING_VAKT_SOM_SCOPE.md` står som besluttet.

**Deploy 1 er den additive halvdelen, og den er bevisst kjedelig:** `Vakt` finnes,
FK-ene skrives — og *ingenting* leser dem ennå. All lesing går fortsatt fra `year`.
Kontrakten i mellomtiden er at `year` og vakta aldri er uenige, og den kontrolleres av
`verifiser_vakt` — som også forhåndssjekker deploy 2-sperrene `(vakt, pasientnummer)` og
`(vakt, oppdragsnummer)`, slik at den migrasjonen ikke kan overraske.

Det som ligger i deployen:

- **`core.Vakt`**: navn (unikt, fritekst), `year` (utledet, men lagret — sesongstatistikk
  skal slippe å regne det ut per spørring), `startet`/`avsluttet`, `er_aktiv`. Bevisst
  ikke `BaseTimeStampedModel`: `startet` er vaktas egen tid, og `created_at` ville løyet
  for backfillede vakter. Bærer ingen personopplysninger.
- **Backfill i to migrasjoner som følger kodens avhengighetsretning**: `patients.0015`
  lager vaktene og kobler pasienter + arkiv, `oppdrag.0006` kobler oppdragene og avhenger
  av den — oppdrag avhenger av patients i kode, og migrasjonsgrafen går samme vei. Navnet
  blir årstallet, ikke `event_name`: den er én global verdi som beskriver vakta som var
  aktiv da noen sist skrev den, og å fryse den inn på historiske vakter ville påstått noe
  vi ikke vet. `startet`/`avsluttet` er estimater fra radenes tidsstempler, redigerbare.
- **Reverseringen nuller FK-ene før vaktene slettes** — `PROTECT` nekter ellers, også i
  en rollback. Bevist mot en base med data i tre år (ett av dem kun som arkiv): backfill,
  full rollback med alle rader intakt, og ny kjøring.
- **Fire skrivestier setter vakta**: pasientoppretting, offline-import (vakta for radens
  *eget* år, ikke den aktive — en import kan bære et annet år), arkivering og
  oppdragsoppretting. Mutasjonstestet: fjernes tildelingen, blir testene røde.
- **`hent_aktiv_vakt()`** i `patients.services`, ved siden av `get_active_year` — flyttes
  til core i deploy 2. Lat opprettelse på fersk base (samme mønster som `get_active_year`
  sin egen AppSetting-rad), og en død `aktiv_vakt_id`-peker repareres i stedet for å
  stoppe registrering: en pasient som ikke lar seg registrere fordi en peker er borte, er
  verre enn en peker som må repareres.
- **`verifiser_vakt`** slår opp modellene via `apps.get_model` i stedet for å importere
  `patients` og `oppdrag` fra `core` — en driftskommando skal ikke snu
  avhengighetsretningen for hele appen. Arkiver uten vakt er info, ikke feil: NULL der
  betyr «fra før grupperingen fantes».

Kjøreplanen står i notatet: deploy 1 ut, `verifiser_vakt` mot prod, og først da deploy 2
— der lesingen bytter kilde, tellerne blir per vakt, «Nullstill år» blir «Avslutt vakt»,
og `year` forsvinner fra radene.

---

## 2026-08-29 — Fase 5: stemplingen overlever at dekningen ryker

**1272 tester grønne** (23 nye). Ingen migrasjon.

Ved knappetrykk skrives stemplingen til `localStorage` **først**, skjermen oppdaterer seg
med en gang, og synkingen skjer i bakgrunnen. Feiler den, blir raden liggende og forsøkes
på nytt — ved neste trykk, ved neste poll, og ved `online`-hendelsen.

**Nøkkelen er det som gjør avspilling trygg.** Den lages ved trykket og beholdes gjennom
hvert forsøk. Serveren kobler den nå til `core.idempotency`, og svarer en avspilling med
`ok` og den **opprinnelige** meldingen i stedet for 409. Uten det kunne køen ikke skille
«allerede levert» fra «avvist fordi skjermen har sakket akterut» — den ville enten hengt
fast, eller kastet en stempling som faktisk kom fram.

**Reservert etter all validering**, aldri før. Et avvist forsøk skal ikke brenne nøkkelen:
køen som retter seg og prøver igjen ville ellers fått «allerede levert» på noe som aldri
kom fram. `forkast()` frigir den når statusmaskinen avviser overgangen. Egen test som
sender en ulovlig overgang først og krever at den lovlige etterpå går gjennom.

**Synkingen er seriell og stopper på første feil.** To parallelle sendinger kunne landet
«Avreist» før «Fremme», og `Statusmelding` er et spor av hva som faktisk skjedde. En 4xx
som ikke er `duplikat` stryker raden og melder fra — serveren vil avvise den igjen, og å
beholde den ville låst køen for alt bak.

**Klienttiden fryses ved trykket**, ikke ved sendingen. Uten det ville statistikken vist
når dekningen kom tilbake i stedet for når mannskapet meldte. `forsinket`-flagget fra
§5.1 gjør at tallet kan leses for det det er.

**Skjermen viser hva som ligger usendt** — §6: en knapp som ser ut til å ha virket, men
ikke har det, er verre enn en som feiler synlig. Eget banner, roligere tone enn
feilbanneret: dette er en ventetilstand, ikke en feil.

### Kjeden måtte til klienten, og det er verdt å si hvorfor

Skjermen kjente ikke statuskjeden — serveren sendte `neste_overgang` per rad. Det holder
online, men ikke i en bil uten dekning: første trykk ville drept knappen, og køen vært
halvveis. Kjeden følger nå med siden som data, og brukes **kun** til å regne ut hva neste
knapp skal hete mens noe ligger usendt.

§4.2-invarianten er urørt. Den handler om at *serveren* ikke skal utlede handlingen av
tilstanden — `POST .../status/neste/` ville gitt kappløpet når to trykk kommer tett.
Klienten måtte uansett vite hvilket navngitt endepunkt den poster til. En test låser
kjeden som sendes mot `services.neste_i_kjeden`, så de to ikke kan komme i utakt: sendes
en annen kjede enn serveren håndhever, viser knappen ett steg og endepunktet godtar et
annet. Sentralbordet får den ikke — det har ingen kø.

### To feller i testoppsettet, begge verdt å notere

`build_harness` klipper ut **funksjoner og ingenting annet**, så `const KO_NOKKEL` var
udefinert i node — og `koLes()` sin try/catch svelget `ReferenceError` og meldte «tom kø».
Alle tolv testene bestod i den forstand at de ikke krasjet, men målte ingenting. Nøkkelen
er nå `koNokkel()`, altså en funksjon harnesset kan se, og det står i koden hvorfor.

Og `crypto` er skrivebeskyttet global fra node 19 — stubben kastet. Node har
`randomUUID` innebygd, så den er droppet; testene sammenligner aldri nøkler mot faste
verdier.

Seks av kø-testene er sett røde ved å slå av projeksjonen.

---

## 2026-08-29 — Oppklart: innloggingen feilet i feil miljø

**Ingen kodeendring.** Kontoen `karmøy56` kom ikke inn fordi innloggingsforsøkene gikk mot
**prod**, mens kontoen ligger på **staging**. André fant det selv.

Det forklarer alt som ikke stemte: `last_login_at` sto stille fordi forespørslene aldri
nådde den databasen diagnosen leste, og `sjekk_brukernavn` — som bare finnes i koden på
`rollemodell` — beskrev hele tiden en annen base enn den innloggingen traff.

**De tre foregående oppføringene står, men ikke som løsningen på dette.** Ingen av
funnene var årsaken; alle er ekte feil som lå der uansett, og som ble funnet fordi noen
lette:

| Funn | Står på egne bein fordi |
|---|---|
| Hullet i kontolåsen | `login_view` slo opp kontoen eksakt mens `authenticate` var tolerant. Passordgjetting kunne kjøres i det uendelige ved å variere store bokstaver. Reell sårbarhet, uavhengig av denne saken |
| Unicode-normalisering | `å` limt inn i NFD-form fant ingen konto. `Ø` mot `ø` bommet på SQLite, altså i offline-modus |
| Forvekslingstegn i midlertidig passord | `0`/`O` og `1`/`l`/`I` i et passord som leses av en skjerm og tastes på en telefon |

**Lærdommen er operativ, ikke teknisk.** To miljøer som ser helt like ut i nettleseren, og
ingenting på siden sier hvilket man står i. Det kostet en arbeidsøkt her, og vil koste mer
under en vakt — der forskjellen er om en pasient registreres i ekte journal eller i en
testbase. Ført opp i TODO.

---

## 2026-08-29 — En vei inn når passordet ikke lar seg gjette

**1249 tester grønne** (12 nye). Ingen migrasjon.

Kontoen kom fortsatt ikke inn med det midlertidige passordet. Diagnosen sto klar:
brukernavnet lagret rent, ingenting i kontotilstanden blokkerte, ingen lås — og
**`last_login_at` sto stille på 07:07**. Siden feltet settes ved *hver* vellykket
innlogging, betyr det at forsøkene ikke lyktes. Passordet traff ikke hashen.

**En sannsynlig grunn lå i genereringen.** Det midlertidige passordet ble trukket fra
`string.ascii_letters + string.digits` — tolv tegn som kan inneholde `0` mot `O`, og `1`
mot `l` mot `I`. Det leses av en skjerm og tastes inn et annet sted, ofte på en telefon.
Feiltastingen er umulig å skille fra «feil passord», og etter fem forsøk låses kontoen
mens brukeren tror hen skriver riktig.

Alfabetet utelater nå `0 O 1 l I`. Kostnaden er 69,7 bit i stedet for 71,4 over tolv tegn
— uvesentlig for et passord som uansett skal byttes. Genereringen lå duplisert to steder,
ved opprettelse og ved «tilbakestill passord»; den er nå én funksjon i `accounts/passord.py`.

**Og en vei inn:** `python manage.py sett_passord <navn>`. Den slår opp brukernavnet med
samme tolerante regel som innlogging, godtar `\uXXXX`-rømming for kanaler uten norske
tegn, validerer det nye passordet mot de samme reglene som skjemaet, nullstiller
kontolåsen, og **fjerner kravet om passordbytte som standard** — det er som regel hele
poenget med å kjøre den. Uten `--passord` genereres ett og skrives ut én gang.

At låsen nullstilles er ikke en detalj: har noen prøvd seg fram på den gamle verdien,
skal ikke den nye møte en sperre satt av de forsøkene. Egen test.

### En blindvei, notert fordi den kostet tid

Første reproduksjon viste `GET /accounts/change-password/` med **400**, og det så ut som
selve forklaringen. Det var **testoppsettet mitt**: backup-planleggeren kjørte mot en
in-memory SQLite og feilet med «database table is locked». Med planleggeren av svarer
siden 200. Feilen lå aldri i appen, og påstanden ble trukket tilbake med en gang den lot
seg etterprøve.

---

## 2026-08-29 — Kontolåsen hadde et hull, funnet mens vi lette etter noe annet

**1237 tester grønne** (5 nye). Ingen migrasjon.

Utskriften fra `sjekk_brukernavn` mot prod viste `karmøy56` med **`feilede forsøk: 0`** og
**`sist innlogget: 07:07 i dag`**. Kontoen hadde altså logget inn, og telleren sto på null.
Det siste tallet viste seg å ikke bety noe.

**`login_view` slo opp kontoen med nøyaktig treff:**

```python
user_obj = CustomUser.objects.get(username=username)
```

mens `authenticate()` bruker det tolerante oppslaget. To ulike svar på «hvilken konto er
dette», og konsekvensen er en **hullete kontolås**: skriver man `Karmøy56` med stor K, blir
`user_obj` `None`, `_registrer_mislykket_forsok` hoppes over, telleren står stille — og
kontoen låses aldri. Riktig passord slipper fortsatt gjennom, siden `authenticate` finner
kontoen. Gjettingen kan altså kjøres i det uendelige ved å variere store bokstaver.

Ironien er at kommentaren fem linjer over forklarer hvorfor *rate-limit-nøkkelen* er
normalisert, med nøyaktig samme argument. Oppslaget under fikk ikke samme behandling.

Oppslaget er nå løftet ut som `backends.finn_kandidater` / `finn_konto`, og både viewet og
`authenticate` kaller den. Én regel for «hvilken konto er dette». Tre av de fem nye testene
er sett røde mot det gamle oppslaget.

**Rate-limit-taket sto uansett** (10 forsøk / 5 min per brukernavn, 50 per IP, begge på
normalisert nøkkel), så hullet var i den per-konto låsen, ikke i bremsen foran den.

**Et første testforsøk målte feil ting.** Det krevde `failed_login_attempts == 5` etter fem
forsøk og feilet med `0 != 5`. Koden hadde rett: `_registrer_mislykket_forsok` nullstiller
telleren når den setter `locked_until`. `is_locked()` er invarianten, ikke tallet — det står
nå i testen.

**For kontoen som utløste dette:** ingenting i tilstanden blokkerer innlogging, men
`må bytte passord: True` står fortsatt etter innloggingen 07:07. `MustChangePasswordMiddleware`
sender da hver forespørsel til `/accounts/change-password/` i stedet for til portalen — og
utenfra ser det ut som at man «ikke kommer inn». Verktøyet sier nå fra om nettopp den
kombinasjonen, med tidspunktet for siste innlogging som bevis på at byttet ikke ble fullført.

---

## 2026-08-29 — `ø` var ikke feilen, og verktøyet sier nå hva som er det

**1232 tester grønne** (6 nye). Ingen migrasjon.

Kontoen som ikke kom inn heter `karmøy56`. Utskriften fra `sjekk_brukernavn` viste den
lagret **helt rent** — `karm[ø U+00F8]y56`, riktig prekomponert, ingen lookalike, ingen
NFD, ingen mellomrom. **Brukernavnet var altså ikke feilen**, og hypotesen forrige
oppføring bygget på traff ikke dette tilfellet.

Da sto man uten neste steg, og det var mangelen: verktøyet svarte på ett spørsmål og
stoppet der. Det viser nå kontoens tilstand når navnet stemmer, og navngir det som
faktisk blokkerer:

| Tilstand | Hvorfor den stopper innlogging |
|---|---|
| `is_active=False` | Kontoen er deaktivert |
| Ingen brukbar passord-hash | Opprettet med invitasjon, lenken aldri brukt. **Ingen** passord virker |
| `locked_until` i framtiden | Fem feilede forsøk låser i 15 min |
| `mfa_required` uten bekreftet TOTP-enhet | Innlogging går til MFA-oppsett, ikke til portalen |

Den midterste er den lumske: feilmeldingen ved innlogging er identisk med «feil passord»,
med vilje, så utenfra er de to umulige å skille. En utløpt `locked_until` regnes ikke som
blokkering — det er en gammel hendelse, ikke en sperre. Egen test.

**Verdt å kjenne for enhetskontoer:** invitasjonsflyten krever `not er_delt_konto` *og* en
e-postadresse. En bilkonto er en delt konto uten e-post, så den får alltid et **generert
12-tegns midlertidig passord** og `must_change_password=True` — ikke et passord man velger
selv ved opprettelsen. Skriver man inn passordet man *trodde* man satte, feiler det, og
brukernavnet med `ø` i er en nærliggende, men uskyldig, mistenkt.

**Et funn til, som ikke forklarer dette tilfellet men er ekte:** `set_password` kaller
`make_password` rett på råstrengen — **Django normaliserer ikke passord**. Et passord med
`å` satt i én Unicode-normalform og skrevet i en annen gir ulik hash, uten at noe kan ses.
`æ` og `ø` dekomponerer ikke og rammes ikke, så det forklarer ikke `karmøy56`. Verktøyet
sier fra om det når ingenting annet blokkerer. **Ikke rettet** — en fallback som også
prøver den normaliserte formen ville utvidet hva som godtas som passord, og det er en
avgjørelse som fortjener å tas bevisst, ikke i forbifarten.

---

## 2026-08-29 — Innlogging med æøå, og en grønn prikk for ledig

**1220 tester grønne** (7 nye). Ingen migrasjon.

### Brukernavn med norske tegn

Meldt fra prod: en konto med `ø` i navnet kom ikke inn, selv med brukernavn og passord
limt inn. **Det tilfellet lot seg ikke reprodusere** — `bjørn.rød` logger inn på første
forsøk her. Men to ekte feil i samme mekanikk ble funnet på veien, og begge er rettet.

**1. Unicode-normalform.** `å` finnes som ett tegn (U+00E5, NFC) og som `a` pluss
kombinerende ring (U+0061 U+030A, NFD). macOS produserer NFD i flere sammenhenger, så
«kopier brukernavnet og lim det inn» er nok til å bomme — de to strengene er pikselidentiske
på skjermen og forskjellige for databasen. Verken oppretting eller innlogging normaliserte.

Målt underveis, og verdt å vite: **`æ` og `ø` dekomponerer ikke.** De er egne bokstaver,
ikke bokstav pluss aksent. `å` og `Å` gjør. Feilen rammer altså navn med `å` — noe som
svekker normalisering som forklaring på nettopp `ø`-tilfellet, og det står i koden.

**2. `iexact` case-folder ikke unicode på SQLite.** `Ø` mot lagret `ø` gir null treff.
På PostgreSQL virker det, fordi `UPPER()` der håndterer unicode. **Offline-modus kjører
SQLite**, så det er ikke en teoretisk forskjell — det er feltbruk uten nett.

Oppslaget går nå i tre stadig bredere steg, billigst først: `iexact` som før, deretter
nøyaktig treff på en NFKC-normalisert og casefoldet nøkkel, og først om begge bommer en
Python-side sammenligning som tåler at *lagret* verdi selv er unormalisert. Det siste
steget kjører kun på et forsøk som ellers ville feilet, og har et tak på 500 kontoer med
logglinje om det passeres — det skal ikke stille bli dyrt om tallet vokser.
`clean_username` normaliserer også ved oppretting, så nye kontoer har én form.

**Tvetydighet slår fortsatt aldri ut i feil konto:** matcher flere kontoer, kreves
nøyaktig treff. De fire nye testene er sett røde mot den gamle backenden.

**For `ø`-tilfellet i prod finnes nå et verktøy:** `python manage.py sjekk_brukernavn
[navn]`. Les-only. Den skriver hvert brukernavn tegn for tegn med kodepunkt og
Unicode-navn, flagger unormaliserte og kontoer med mellomrom i enden, og sier om et gitt
oppslag ville truffet. Den finnes fordi «brukernavnet ser riktig ut» ikke lar seg
feilsøke ved å se på det — en kyrillisk `е` ser ut som en latinsk `e`, og den fella traff
dette prosjektet i et dokument tidligere samme dag.

**Og kanalen selv var en felle.** Railways `ssh` bærer ikke `ø` inn på kommandolinja, så
verktøyet var i praksis ubrukelig for nettopp det tegnet det skulle undersøke. To ting
retter det: **uten argument lister kommandoen alle kontoer** — man trenger ikke skrive
navnet i det hele tatt — og argumentet godtar `\uXXXX`-rømming, mens utskriften viser
hvert navn i samme form. Første forsøk skrev ascii-formen med Pythons egen
`backslashreplace`, som gir `\xf8` for tegn under U+0100; den formen tolkes ikke tilbake,
så rundturen var brutt og utskriften ubrukelig i den kanalen den var laget for. Nå skrives
alltid `\uXXXX`, og en test limer hver form tilbake og krever samme streng.

### Grønn prikk for ledig enhet

`.status-ledig` var grå, som `.status-venter`. Grått leste som «av», og 113 skal se hvem
som kan sendes uten å lese teksten først. Nå grønn (`#22c55e`). `Venter` beholder grått —
det er nettopp forskjellen mellom «tildelt, men ikke rykket ut» og «klar» som skal være
synlig. Fargen bærer fortsatt ikke informasjonen alene; statusteksten står ved siden av
(WCAG 1.4.1).

---

## 2026-08-29 — Fase 4b: 113 kan rette et tidspunkt, uten å viske ut det som ble meldt

**1213 tester grønne** (18 nye). Ingen migrasjon.

Maskineriet kom i fase 1 og var ubrukt: `services.korriger_tidspunkt` og
`Statusmelding.objects.gjeldende()` har ligget der siden 28. aug. Det som manglet var
endepunktet, reglene og en vei inn fra grensesnittet.

**Rettingen er en ny rad som peker på den gamle.** Originalen røres ikke, og begge står i
tidslinjen — den erstattede gjennomstreket, rettingen merket «rettet av sentralen».
`Statusmelding` er et spor av hva som *ble meldt*; redigerte man raden, kunne «hva sa
bilen egentlig?» bare besvares fra `AuditLog`, en admin-flate som ikke er der oppdraget
vises. Testen som holder det ærlig setter `melding.tidspunkt` direkte i tillegg til å
skrive den nye raden — og blir rød.

**Fire regler, alle fail-closed:**

1. **Raden må være gjeldende.** Retter man en allerede overstyrt rad, finnes to
   korreksjoner av samme original og «hvilken gjelder» har ikke lenger noe entydig svar.
   Korreksjoner *kan* kjedes — man retter den nyeste.
2. **Ikke i framtiden.** Et tidspunkt som ikke har inntruffet er ikke en observasjon.
3. **Ikke før oppdraget ble opprettet.**
4. **Rekkefølgen må holde.** Dette er den som betyr noe. Settes `Fremme` før
   `Rykker ut`, blir responstiden negativ — og fase 6 ville regnet på den uten å vite at
   tallet er umulig. Sjekken måler mot de *gjeldende* naboene, ikke mot alle rader: en
   overstyrt rad beskriver ikke lenger noe som gjelder, og å måle mot den ville låst
   rettingen til verdien man retter bort. Feilmeldingen navngir naboen som er i veien
   («`Fremme` kan ikke være før `Rykker ut` (14:36)»), så operatøren vet om hun må rette
   en annen rad først.

**Endepunktet er bevisst ikke et handling-endepunkt.** Det tar et tidspunkt, altså en
feltverdi, og ligger derfor på `skriv_full` med vanlig kroppsvalidering. Å presse det inn
under `skriv_handling` ville uthult det lukkede skjemaet i §5.1 med én gang — da hadde
stemplingskroppen fått et domenefelt. Enhetskontoer får 403 uansett nivå: en bil som kunne
rette sine egne tidspunkt ville gjort stemplingen til en påstand i stedet for en måling.
Bilen *ser* rettingen (§4.5), den gjør den ikke.

**To fikstur som målte feil regel.** Begge ble funnet ved at testene feilet, ikke ved
gjennomlesing. Det første stemplet oppdraget i samme millisekund som det ble opprettet, så
enhver retting bakover traff «før oppdraget ble opprettet» — fiksturet har nå realistisk
tidsspenn. Det andre stemplet `Avreist` med servertid og rettet `Fremme` til fem minutter
etter; det havnet i framtiden, så framtidsregelen svarte først og testen ville bestått også
uten rekkefølgesjekken. Begge er notert i koden, siden mønsteret kommer tilbake.

**Én feil verdt å notere:** `@transaction.atomic` sto over `korriger_tidspunkt`, og den nye
`KorreksjonUgyldig`-klassen ble satt inn *under* dekoratoren. Da var ikke unntaket lenger
en klasse, og `except` kastet `TypeError: catching classes that do not inherit from
BaseException`. Fanget av testene med en gang. Verdt å huske når noe settes inn rett foran
en dekorert funksjon.

---

## 2026-08-29 — «Arkiv» heter Historikk i oppdragsmodulen

**1195 tester grønne** (ingen nye). Migrasjon `oppdrag.0004_historikk_ikke_arkiv` —
ren `RenameField`, ingen data endres.

Knappen het «Ferdigstilte» og handlingen «Arkiver». Begge er borte: flaten heter
**Historikk**.

**Grunnen er en navnekollisjon som ville blitt verre, ikke bedre.** `core.arkiv` fryser,
signerer og kollapser hele vakter, og oppdragsmodulen får sin *egen* `BaseArkivHandler` i
fase 7. Hadde begge hett «arkiv», ville `arkiver_view` og `ArkivHandler` stått i samme app
og betydd hver sin ting — den ene rydder en liste, den andre skriver en SHA-256-signatur
som ikke kan angres. Den som leste feil av de to ville trodd raden var fryst.

Derfor er omdøpingen ført hele veien inn, ikke bare på knappen:

| Før | Nå |
|---|---|
| `arkivert_at` / `arkivert_av` | `historikk_fra` / `historikk_av` |
| `bruker.arkiverte_oppdrag` | `bruker.oppdrag_lagt_i_historikk` |
| `arkiver_oppdrag()` | `flytt_til_historikk()` |
| `KanIkkeArkiveres` | `KanIkkeFlyttes` |
| `POST /api/oppdrag/<pk>/arkiver/` | `POST /api/oppdrag/<pk>/historikk/` |
| `GET /api/arkiv/` | `GET /api/historikk/` |
| `arkivert` i JSON-svaret | `historikk_fra` |

`related_name` er den som betyr mest i kode: `bruker.arkiverte_oppdrag` ville fortsatt
lovet arkivering fra et helt annet sted i kodebasen. Testklassene og testnavnene er også
byttet — det er der neste utvikler leter etter hva ordene betyr.

De to gjenværende treffene på «arkiv» i modulens tester er selve forklaringen på hvorfor
navnet ble byttet, og skal stå.

---

## 2026-08-29 — Ferdigstilte oppdrag rydder seg selv bort

**1195 tester grønne** (7 nye). Ingen migrasjon. Oppfølging samme dag: den manuelle
arkivknappen løste ikke problemet den var laget for.

**Innvendingen var god.** Krever ryddingen et trykk per oppdrag under en travel vakt, blir
den ikke gjort — og da fylles tavla opp likevel, med en knapp ingen rakk å bruke. Et
oppdrag arkiveres nå i det øyeblikket det blir `Ledig`.

**Regelen ligger i `sett_status`, ikke i stemplingsviewet**, og det er ikke en
smaksdetalj: ikke alle `Ledig`-overganger kommer fra et knappetrykk. Starter en enhet
neste oppdrag, lukkes det pågående automatisk (§4.3) gjennom samme funksjon. Lå regelen i
viewet, ville tavla beholdt nettopp de oppdragene ingen trykket på — de som ble lukket av
seg selv. Testen som dekker det er sett rød ved å unnta `automatisk=True` fra regelen.

**`arkivert_av` står som NULL ved automatisk arkivering, og det er informasjon.** NULL
betyr «ryddet bort av seg selv», satt betyr «noen trykket». Samme skille som
`Statusmelding.automatisk`. Å føre opp bilens konto der ville dessuten motsagt regelen om
at enheter ikke arkiverer — den stempler, systemet rydder.

**Arkiveringen henger på overgangen, ikke på statusen.** Forskjellen merkes i «Hent
tilbake»: et oppdrag hentet fram igjen blir *stående* på tavla, fordi det ikke finnes noen
ny overgang til `Ledig` som kunne fjernet det. Var arkiveringen i stedet et statusfilter,
ville raden forsvunnet igjen ved neste poll, og knappen vært uten virkning. Egen test.

**Bilens 30-minuttersvindu er urørt**, og det er verdt å gjenta fordi de to nå ser enda
likere ut. Mannskapet ser fortsatt oppdraget sitt i en halvtime etter at de meldte seg
ledige; det er sentralbordets tavle som ryddes. Koblet dem, ville oppdraget forsvunnet fra
skjermen i bilen i samme øyeblikk knappen ble trykket — mens de fortsatt sto og så på det.
Egen test som krever begge deler samtidig.

Den manuelle knappen står igjen for hånd-tilfellene: hent tilbake til tavla, og rydd bort
igjen etterpå. Hjelpeteksten i «Ferdigstilte» sier nå at oppdrag havner der av seg selv —
den beskrev en knapp som i praksis ikke lenger er hovedveien inn.

---

## 2026-08-29 — Oppdragsnummer, og en arkivknapp som rydder tavla

**1188 tester grønne** (22 nye). Migrasjon `oppdrag.0003_oppdragsnummer_og_arkivering`.
Bestilt under uttesting av fase 4, utenom faseplanen.

**Nummeret er per år, ikke globalt.** `pasientnummer` er globalt unikt fordi
nullstillingen der sletter radene; oppdrag har ingen slik nullstilling, så uniktheten
bæres av `(year, oppdragsnummer)` med en databasesperre. Nummeret restarter på 1 hver
sesong — «oppdrag 14» skal være kort nok til å leses opp på samband, og i år tre ville en
global teller gitt tresifrede numre uten grunn. Telleren står i `AppSetting` per år og
låses med `select_for_update`, som `next_patient_nr`, og gjenskapes fra dataene hvis raden
mangler, slik at en slettet innstilling ikke gir kollisjon.

**Migrasjonen backfiller før den strammer inn.** Tre steg i rekkefølge: nullbar kolonne,
backfill per år i `created_at`-rekkefølge, deretter `NOT NULL` og unikhetskravet. Legges
kolonnen til med en default i ett steg, får alle eksisterende rader samme nummer og
sperren feiler. Backfillen setter også `AppSetting`-telleren for hvert år den fant — uten
det ville neste opprettelse startet på 1 og kollidert med rad nummer 1. Kjørt mot en
testbase med rader i to år og blandet innsettingsrekkefølge: nummereringen følger
`created_at`, ikke innsettingen.

**«Arkiver» rydder tavla. Den fryser ingenting.** Dette er *ikke* vaktarkivet i
`core.arkiv`-forstand — ingen SHA-signatur, ingen kollaps, ingen backup-sperre. Et
ferdigstilt oppdrag flyttes ut av den aktive lista og inn i en «Ferdigstilte»-visning som
kan søkes på nummer, problemstilling, lokasjon eller enhet. Raden er urørt og kan hentes
tilbake. Fase 7 bygger fortsatt det ekte vaktarkivet; de to er ikke i veien for hverandre
— den ene er drift under vakt, den andre dokumentasjon etter vakt.

Fordi handlingen er reversibel ligger den på `skriv_full`, ikke på global admin: §3.3
reserverer admin for det irreversible, og en knapp som bare rydder en liste hører til
drift. Enhetskontoer stenges ute selv med `skriv_full` — rydding er sentralbordets jobb.

**Kun ferdigstilte kan arkiveres.** Å rydde bort et pågående oppdrag ville skjult noe som
fortsatt skjer, og det er samme feilklasse som å ta en enhet av vakt midt i et oppdrag —
allerede stengt i `enhet_vakt_view`. Knappen vises bare når den kan brukes.

**Arkivering rører ikke enhetens 30-minuttersvindu**, og det er verdt å si eksplisitt
fordi de to reglene ser like ut. Vinduet er personvern — en bil kan bli stående ulåst.
Arkiveringen er sentralbordets rydding av sin egen tavle. Koblet dem, kunne sentralbordet
fjernet et oppdrag fra skjermen til et mannskap som fortsatt sto og så på det.

**Et fikstur som påsto mer enn det viste.** Søket på nummer treffer eksakt, ikke som
delstreng — søker man «1» skal man ikke få 1, 10 og 11. Testen sa nettopp det, men
fiksturet hadde bare numrene 1, 2 og 3, så den bestod også da søket ble byttet til
`__icontains`. Numrene er nå 1, 10 og 11, og mutasjonen gjør testen rød. De øvrige nye
vernene er også sett røde: sperra mot å arkivere pågående (5 feil) og ekskluderingen fra
den aktive lista (1 feil).

Personvernprotokollen er ført til v1.8: begge feltene inn i A.6-tabellen, med presisering
av at `oppdragsnummer` identifiserer *oppdraget* og ikke personen, og en merknad i A.9 om
at arkivflagget ikke påvirker noen lagringstid.

---

## 2026-08-29 — Fase 4: enhetsskjermen, og første faktiske bruk av `skriv_handling`

**1166 tester grønne** (29 nye). Ingen migrasjon. Mellomtilstanden fra fase 3
(`enhet_kommer.html`) er slettet — enhetskontoer får nå en ekte skjerm.

**Stemplingsendepunktene: fem, ikke seks.** Planen sa «seks navngitte endepunkter», men
talte statusene: `venter` settes ved oppretting og stemples aldri. Settet skrives ikke ned
noe sted — `services.STEMPLBARE` utledes av overgangstabellen (`frozenset().union(*OVERGANGER.values())`),
så et endepunkt finnes hvis og bare hvis en rad peker på det. URL-en er
`POST /oppdrag/api/oppdrag/<pk>/status/<overgang>/` med statusverdien som navn; ukjent navn
gir 404, ulovlig overgang 409.

**Det lukkede kroppsskjemaet fra §5.1 er testbart ved uttømming, og testes slik.** To
nøkler — `klienttid` og `idempotency_key` — og alt annet gir 400 uten sideeffekt; testen
sender domenefelt og krever at ingenting endret seg. `klienttid` valideres etter §5.1:
framtid, før oppdragets opprettelse eller eldre enn et døgn gir servertid, og avvik over to
minutter fra ankomsttid setter `forsinket=True` uansett hvilket stempel som vant — avviket
er informasjonen. Uleselig klienttid gir 400, ikke stille servertid: det er en klientfeil,
ikke et gammelt stempel.

**`idempotency_key` godtas, men kobles først i fase 5.** Statusmaskinen gjør en ren
avspilling ufarlig allerede: samme overgang to ganger er ulovlig andre gang og gir 409 uten
ny rad. Verdien av `core.idempotency` her er å svare «ok» på en replay i stedet for 409, og
det svaret hører til offline-køen som skal tolke det.

**To porter, og nivå er ikke nok.** `skriv_handling` i dekoratøren, eierskap i viewet — og
`skriv_full` *uten* enhetskobling får 403. Sentralbordet stempler ikke; det korrigerer
(fase 4b). Stemplingen er en måling fra bilen, og en operatør som stempler «for» en enhet
ville forfalsket den. Testene dekker også kombinasjonen enhetskobling uten
`ModulTilgang`-rad: koblingen gir ingen tilgang, samme regel som `Forstehjelper.user`.

**Skjermen kjenner ikke statuskjeden.** Serveren sender `neste_overgang` og `neste_navn`
på hver rad (kun i enhetens payload), og «neste»-knappen poster dit den blir fortalt. En
kopi av kjeden i JS ville vært enda et sted å komme i utakt — §2.6 i rollemodellnotatet i
miniatyr. Dobbelttrykk møter 409 og besvares med å hente ferskt, uten feilbanner.

Resten av skjermen: to knapper med 64px trykkflater (en tommel i en bil i bevegelse, ikke
en musepeker), ventende sortert på hastegrad men valgt av mannskapet, tidslinje på det
aktive kortet, `automatisk`-markøren i gråtoner på klokkeslettet (§4.5), og et feilbanner
som blir stående til noe lykkes — med beskjed om å melde over nødnett, som er det ærlige
svaret til offline-køen finnes (fase 5). Polling hvert 15. sekund med ETag; enhetens ETag
inkluderer meldings-ID-ene, slik at en korreksjon (fase 4b) ikke drukner i en 304.

**`klokke()` flyttet til `portal-utils.js`** — begge oppdragssidene bruker den, og helpere
flyttes, de kopieres ikke. `hastegradKlasse()` er duplisert med vilje: den er domene, ikke
primitiv, og de to filene lastes aldri sammen. XSS-vernet i `tests_xss.py` skanner nå
byggerne i begge filene, og kjører enhetsskjermens byggere i node med markup i fritekst,
knappenavn og statusnavn.

---

## 2026-08-29 — Fase 2 lukket: protokollen dekker oppdragsmodulen

Kun dokumentasjon — `PERSONVERN_DOKUMENTASJON.md` går fra v1.6 til v1.7. Ingen kodeendring,
ingen migrasjon. **1137 tester grønne.**

Dette var resten av fase 2 i `docs/BESLUTNING_OPPDRAGSMODULEN.md`. Kodedelen — at fritekst
logges som *endret* i audit, men aldri med verdier — har vært på plass fra feltets første
lagring (28. aug.); det som sto igjen var at behandlingsprotokollen faktisk beskriver
behandlingen. Rekkefølgekravet var «før feltet er i prod med logging på», og det holdt:
modulen finnes kun på staging, så verdilogging av fritekst har aldri vært aktiv noe sted.

Hva som kom inn, og hvorfor det ligger der det ligger:

- **A.6, ny seksjon «Oppdragsdata».** Feltene med kategori og hjemmel, etter samme lest som
  pasienttabellen. Det bærende poenget står først: personen oppdraget gjelder registreres
  **uten noen identifikator** — ikke pasientnummer, ikke navn, ingen kobling til
  pasientmodulen. Fritekst-tiltakene er samlet her som nummerert liste: audit-unntaket,
  de to server-side skjulereglene mot enhetskontoer, hjelpeteksten i skjemaet, og at
  oppdragsdata ikke caches. `Leverer`-uten-leveringssted er ført som det bevisste valget
  det er.
- **A.6, audit-tabellen.** Raden som lover «gammel verdi, ny verdi» på feltnivå har fått
  unntaket ført inn. Uten den linja motsier protokollen seg selv fra to seksjoner.
- **A.9, rad + merknad.** Ærlig svar på lagringstid: **ingen automatisk sletting ennå.**
  Radene er årsscopet som pasientdata, men blir stående til fase 7 leverer arkivering med
  24-måneders kollaps. Merknaden sier eksplisitt at raden skal revideres da — samme grep
  som kollaps-verifiseringsmerknaden fra v1.6: dokumentet skal si hva som er bevist, ikke
  hva som er planlagt.
- **A.12, ny sårbarhet.** Fritekst er portalens første frie tekstfelt, og en operatør *kan*
  skrive identifikatorer der. Tiltakene henvises, og restrisikoen står: selve feltverdien
  ligger i oppdragstabellen til oppdraget slettes eller arkiveres.
- **B.2, merknad.** Personvernerklæringen henvender seg til pasienten, og en utrykning
  gjelder samme person — da skal erklæringen også dekke den. Kort avsnitt: oppdraget
  registreres uten identifikator, og fritekst skjules for enheten ved avslutning.

**Funn underveis, ført inn i A.9 og TODO:** oppdragsdata står utenfor applikasjonens
modulbackup. Ingen handler er registrert i `core.backup`-registryet, så fram til fase 7 er
Railways databasebackup — aktiv omtrent én måned i året — eneste dekning. Ikke akutt så
lenge modulen er på staging, men det må få en handler senest sammen med arkiveringen.

Fasetabellen i beslutningsnotatet er samtidig ført ajour: fase 2 og fase 3 står nå som
levert (fase 3 ble levert 29. aug. uten at tabellen ble oppdatert), og §9 har fått en
gjennomført-note etter samme mønster som rollemodellnotatets §7.

---

## 2026-08-29 — «Pensjoner» er borte, og et pensjonert navn er ledig igjen

**1137 tester grønne** (2 nye, 7 fjernet). Ingen migrasjon.

Målt på staging: `Enheter uten konto: 0 av 2`. Dermed hadde Pensjoner-knappen ingen jobb
igjen — alle enheter har en konto, og kontoen er veien inn og ut. Knappen, Gjenopprett,
`_settAktiv`, `PUT /oppdrag/api/enheter/<pk>/`, `GET /oppdrag/api/kontoer/` og
`_enhet_admin_dict` er slettet. Det samme er `OPPDRAG_TILGANG.erAdmin`, som ikke hadde noen
leser igjen.

**Men å fjerne knappen alene ville satt en felle.** Sletter du kontoen til en bil som har
kjørt, pensjoneres enheten i stedet for å slettes — historikken er `PROTECT`. `Enhet.navn`
er `unique`, så «Haugesund 56» ville vært brent for godt: skjemaet ville sagt «finnes
allerede», og uten Pensjoner-knappen fantes ingen vei tilbake utenom `manage.py shell`.

Et pensjonert, ukoblet navn regnes derfor som ledig. Oppretter du kontoen på nytt, tas den
gamle raden i tjeneste igjen i stedet for at det lages en ny — bilen kommer tilbake med
oppdragene sine. En ny rad ville gitt to «Haugesund 56» i statistikken, én med historikk og
én uten. Navn som holdes av en enhet i tjeneste, eller av en med konto, er fortsatt opptatt.

Enhetens livssyklus har dermed én kilde: kontoen. Opprett den, og bilen finnes; slett den,
og bilen forsvinner eller pensjoneres; opprett den igjen, og bilen er tilbake.

**Under arbeidet slettet jeg `enheter_view` ved et uhell** — den lå mellom to funksjoner som
skulle vekk, og utsnittet tok den med. Fanget med en gang fordi skriptet skrev ut hvilke
funksjoner det faktisk fjernet; gjenopprettet fra `git show HEAD`. Verdt å merke seg som
argument for å la slike skript rapportere, ikke bare gjøre.

---

## 2026-08-29 — Enheten følger kontoen, også ut

**1142 tester grønne** (5 nye, 1 fjernet). Ingen migrasjon.

André: «Fjern legg til enhet-knappen i enheter-vinduet. Den skal ikke brukes av noen og er
bare forvirrende. Vi trenger heller ikke pensjoner? Jeg kan jo bare slette brukeren?»

**«Legg til enhet» er borte** — knappen, JS-funksjonen, `POST /oppdrag/api/enheter/ny/` og
URL-en. Enheter fødes med kontoen («Bil eller ambulanse» i kontoskjemaet), og to veier inn
til samme rad er én for mye. Malen sa det selv med «vanligvis trengs ikke denne», som er en
knapp som ber om unnskyldning for å finnes. Testen som krevde at endepunktet fantes er
snudd: nå kreves 404.

**Premisset om sletting stemte ikke — nå gjør det det.** `Enhet.user` er `SET_NULL`, så å
slette bilkontoen etterlot enheten som en rad uten kobling: fortsatt på ressursoversikten,
merket rødt, og hvis den hadde kjørt oppdrag, umulig å bli kvitt — `Oppdrag.enhet` er
`PROTECT`. Sletting av kontoen tar nå enheten med seg, og pensjonerer den i stedet når den
har oppdrag i historikken. Samme skille som ellers i portalen: data uten spor slettes, data
med spor fryses.

**Frysing tar enheten av vakt.** En frosset konto kan ikke logge inn, så bilen kan ikke
melde. Å la den stå som ledig ville sendt 113 etter en bil ingen kan kvittere for. Frysing
er reversibel, så enheten pensjoneres ikke — den settes inn igjen manuelt ved opptining.

**«Pensjoner» blir stående.** Den er nå nødutgangen for enheter uten konto — rader som ble
til før koblingen fantes, eller fra `manage.py shell`. De kan ikke fjernes ved å slette en
konto, for det finnes ingen. Etter denne endringen er det den eneste jobben knappen har.

---

## 2026-08-29 — Lukkekrysset var svart på mørk modal

**1139 tester grønne** (1 ny). Ingen migrasjon.

André meldte at X-en i Nytt oppdrag, Enheter og Lokasjoner er svart og ikke passer vinduet.

`portal.css` hadde **ingen** modalregler. Bootstraps `--bs-modal-bg` arver `--bs-body-bg`,
som `base_portal` setter til sidebakgrunnen — så modalen fikk nøyaktig samme farge som siden
bak seg, og `.btn-close`, som er en svart SVG, forsvant i den. Ingenting feilet; det så bare
ut som en tom flate med et kryss som ikke var der.

Pasientsiden har aldri hatt problemet: den er frittstående, laster `style.css`, og hver
knapp der har `btn-close-white`. Feilen bodde kun i portalgrenen, og derfor hører fiksen
hjemme i `portal.css` — ikke i `oppdrag.css`. Alle modulsider som kommer etter, arver den.

Modalen får nå `--portal-surface` og en kant, så den løfter seg fra siden bak, og krysset
inverteres.

Testen fant et sted til jeg ikke hadde sett etter: **`base_portal.html` har selv en
`.btn-close`** — lukkeknappen på Django-meldingene. Den sto svart på `.alert-danger`s
mørkerøde bakgrunn på hver eneste portalside. Samme linje løser begge.

Guarden ligger i `MorkTekstPaaMorkBakgrunnTests`, som allerede løser `{% extends %}` og
`{% static %}`: en mal med `.btn-close` må ha overstyringen i et stilark den faktisk laster.
Samme feilklasse som dempet tekst — en Bootstrap-standard laget for lys bakgrunn, som er
usynlig i stedet for å feile.

---

## 2026-08-29 — Sperra på Pensjoner er testet, ikke bare tegnet

**1138 tester grønne** (2 nye). Ingen migrasjon.

André spurte hvem som når Pensjoner-knappen. Svaret var riktig — global admin, både i
tegningen og på serveren — men bare halvparten av det var testet.

Da Enheter-panelet ble åpnet for `skriv_full` i forrige økt, fikk den gruppa et panel som
også nevner `PUT /oppdrag/api/enheter/<pk>/`. Endepunktet krevde global admin hele veien;
testene dekket bare `enheter/ny/`. En knapp som ikke tegnes er ingen sperre — sperra er
serveren, og den skal ha en test som går rød når noen fjerner den.

To tester lagt til: `skriv_full` uten admin får 403 på både lesing og pensjonering av en
enhet, og enheten er fortsatt aktiv etterpå.

---

## 2026-08-29 — Tavla viser ressurser og oppdrag, resten ligger bak knappen

**1136 tester grønne** (2 nye). Ingen migrasjon.

André: «for nå så er det dårlig UI med på vakt, av vakt og oppdragslisten nederst. De to
viktigste er, hvilke ressurser er tilgjengelige og oppdrag.»

Tavla har derfor to ting: **Ressurser** — enhetene som er på vakt, med status — og
**Oppdrag**. Enheter av vakt vises ikke der lenger; tavla svarer på ett spørsmål, og det er
«hvem kan sendes nå».

Antallet av vakt står på Enheter-knappen («Enheter (1 av vakt)»), der hele lista ligger.

Første utgave hadde *to* signaler om det samme — også en linje under ressurslista. André tok
det bort: «jeg gir jo folk opplæring, de som skal bruke det er godt informerte. Nå dummer vi
det veldig ned.» Han har rett. Vernet mot at en bil forsvinner ubemerket er ett tall, ikke
to plasseringer av det, og et grensesnitt som gjentar seg for brukere som er lært opp er
støy — ikke omtanke.

**Enheter-knappen er ikke lenger et koblingspanel.** Den viser hele lista: på vakt, av vakt
og pensjonerte, med vaktbryteren der. Kontokoblingen vises som tekst, men redigeres ikke —
nye biler får den ved oppretting av kontoen, så nedtrekket var en tredje vei til noe som
allerede var gjort. Verre: det inviterte til å tro at koblingen *er* tilgangen. Mangler
koblingen, står det med rød tekst; det er en ekte feiltilstand og verdt å se.

`?alle=1` på enhetsendepunktet tar med pensjonerte. Ressursoversikten skal ikke se dem —
de er borte for godt — men panelet er stedet man gjenoppretter dem fra, og da må de være
synlige et sted. En probe som droppet filteret gjorde begge testene røde.

Panelet er åpnet for `skriv_full`: å ta biler på og av vakt er drift. Oppretting og
pensjonering står fortsatt på global admin.

Verifisert i nettleser, ikke bare i tester: ressurslista viser én enhet, notisen og
knappetelleren viser den andre, nedtrekket i «Nytt oppdrag» har bare den som er på vakt, og
panelet lister begge med riktig bryter.

---

## 2026-08-29 — Biler tas på og av vakt

**1134 tester grønne** (9 nye). Migrasjon `oppdrag.0002_enhet_pa_vakt`.

André ville at `skriv_full` skal kunne ta biler ut av tilgjengelige enheter — «det er jo en
ressursoversikt».

**Det ble et nytt felt, ikke gjenbruk av `er_aktiv`.** De to svarer på forskjellige
spørsmål, og forskjellen er hvem som endrer dem og hvor ofte. `er_aktiv` er oppsett: admin
pensjonerer en bil, og da skal den bort for godt. `pa_vakt` er drift: 113 tar biler på og av
gjennom vakta. Ett felt for begge ville gjort «pensjonert» og «hjemme i kveld» til samme
tilstand, og den som skulle skru bilen på igjen ville ikke funnet den. Det er den samme
sammenblandingen deploy 1–3 brukte tre runder på å rydde bort.

To regler holder oversikten ærlig, begge testet:

- **En enhet av vakt skjules ikke** — den vises i en egen gruppe på sentralbordet. En bil
  som forsvinner fra tavla er en bil ingen husker å sette inn igjen, og da mangler den neste
  vakt uten at noen vet hvorfor. En probe som filtrerte dem bort i API-et gjorde testen rød.
- **En enhet med påbegynt oppdrag kan ikke tas av vakt.** Den er ute akkurat nå. Et ventende
  oppdrag hindrer derimot ikke — bilen har ikke rykket ut, og motstykket er testet så
  sperren ikke kan bli en som alltid slår til.

Flytting er ingen bakvei: et oppdrag kan ikke flyttes til en enhet som er av vakt.

Endepunktet er skilt fra `enhet_detalj_view`, som er admin-flaten for navn, kobling og
pensjonering. Drift og oppsett har ulike brukere og ulik frekvens, og bør ikke dele dør.

---

## 2026-08-29 — Nivåene tilbys per modul, og bilnivået forhåndsvelges

**1125 tester grønne** (5 nye). Ingen migrasjon.

André: «det står ingenting på oppdrag om skrive:handling. Bare lese eller skrive: full.»

`ModulTilgangForm` hadde én global liste over valgbare nivåer, og `skriv_handling` sto ikke
i den. Begrunnelsen var at ingen modul brukte nivået ennå, og at et nivå som ikke gir noe er
lett å dele ut i god tro. **Den begrunnelsen sluttet å gjelde da oppdragsmodulen ble
skrevet** — nivået var bygget for akkurat den — og ingenting fanget det opp, fordi lista lå
i skjemaet og modulen ikke hadde noe å si om saken.

Samme liste hadde motsatt feil samtidig: den tilbød `skriv_full` på `statistikk`, som ikke
har et eneste skriveendepunkt.

**Hver modul deklarerer nå sine egne nivåer** i `Module.nivaaer`. Patients: `les`,
`skriv_full`. Oppdrag: hele stigen. Statistikk: bare `les`. Et nivå brukeren allerede har
står fortsatt i lista selv om modulen ikke tilbyr det — ellers ville et lagre-trykk stille
fjernet det.

### «Hvorfor settes ikke tilgangen automatisk?»

Fordi en usynlig tilgangsendring er nøyaktig fella §7.3 delte `PasientRolleForm` for å
unngå: der satte én radio både funksjonen i felt og tilgangen, så en domenehandling endret
autorisasjon uten at noen så det.

Men innvendingen har et poeng — en bil uten `skriv_handling` kan ikke gjøre det biler gjør.
Løsningen er **forhåndsvalgt, ikke satt i bakgrunnen**: velger man «Bil eller ambulanse»,
settes Oppdrag-raden i matrisen til «Skrive: handling», med en forklaring ved siden av.
Admin ser verdien i det samme skjemaet hun sender inn, og kan endre den. Valget forblir
hennes, og auditraden viser hva som faktisk ble sendt.

---

## 2026-08-29 — Kontotypen velges, og bilen opprettes i ett steg

**1120 tester grønne** (9 nye). Ingen migrasjon.

André: «jeg er sterkt kritisk til å måtte koble en delt konto. Å koble slikt er tullete.»
Han har rett. Å sette opp én bil krevde tre handlinger — opprett konto, opprett `Enhet`
inne i oppdragsmodulen, koble dem — med to av dem på en helt annen side enn den første, og
ingenting som forklarte hvorfor de hang sammen.

`AdminUserCreateForm` har nå ett valg med tre verdier: **Person**, **Delt konto**, **Bil
eller ambulanse**. Velger man den siste, blir enheten opprettet og knyttet til kontoen i
samme innsending.

**Ett valg, ikke avkrysningsboks pluss navnefelt.** `er_delt_konto` er ikke lenger en boks
på opprettingsskjemaet — den utledes av valget. To kontroller som overlapper er nettopp det
som gjorde `role` til et rot: man kunne krysse av for delt konto og *likevel* skrive et
enhetsnavn, eller la være, og skjemaet måtte gjette hva som var ment. Redigeringsskjemaet
beholder boksen; der endrer man en konto som finnes, og det er noe annet enn å bestemme hva
som skal lages.

**Det som ble slått sammen er to opprettelser — ikke tilgang og domenedata.** §7.3-skillet
står uendret, og en test holder det: en bil opprettet slik får 403 på `/oppdrag/` helt til
noen gir den en `ModulTilgang`-rad. Prøvd motsatt vei også — en probe som lot
enhetsopprettingen dele ut `skriv_handling` gjorde testen rød.

Enhetsnavnet sjekkes som ledig i `clean()`, ikke i viewet. En unik-feil fra databasen ville
kommet etter at kontoen var lagret, og etterlatt en konto uten enhet.

Retningen `accounts` → `oppdrag` er verdt å merke seg. Importen er lokal i funksjonen, som
`core.views` gjør mot `patients.models`. Skal en modul nummer to også kunne opprettes fra
brukerskjemaet, er det der et registry hører hjemme — etter samme idiom som `core.backup`
og `core.arkiv`. Med én modul ville registeret vært mer maskineri enn nytte.

---

## 2026-08-29 — CSRF: hver skriving fra en modulside var brutt

**1111 tester grønne** (8 nye). Ingen migrasjon. `static/js/portal-utils.js` og
`core/tests_csrf_flater.py`.

André meldte at han ikke fikk opprettet et oppdrag som **admin**. Første diagnose var feil —
jeg antok at kontoen manglet `skriv_full`, fordi det forklarte symptomet og passet med
oppsettet han beskrev. Det gjorde det ikke: han var admin hele tiden. Sida ble derfor kjørt
i en ekte nettleser, og da kom svaret på ett forsøk:

```
Forbidden (CSRF token from the 'X-Csrftoken' HTTP header has incorrect length.)
POST /oppdrag/api/oppdrag/ 403
```

**`CSRF_COOKIE_HTTPONLY = True`, så JS kan aldri lese `csrftoken`-cookien.**
`getCsrfToken()` prøvde cookien først og falt tilbake på `#csrf-token-holder` — et element
bare pasientsiden har. Oppdragssiden hadde ingen av delene, så tokenet ble tom streng, hver
POST/PUT/DELETE fikk en HTML-403, og `res.json()` kastet på `<!DOCTYPE` *før*
feilmeldingsboksen ble fylt. Brukeren så at ingenting skjedde.

`base_portal.html` har hatt `<meta name="csrf-token">` på hver eneste side hele tiden — lagt
inn for akkurat dette formålet, og aldri lest. **Fiksen er å lese den**, ikke å legge en
holder i hver mal: da ville neste modul gjort samme feil.

### Hvorfor 37 view-tester ikke så det

`Client()` settes opp med `enforce_csrf_checks=False`. Hele API-et var testet og grønt mens
hver eneste skriving fra nettleseren var brutt. Det er en feilklasse vanlige view-tester er
blinde for, og den må testes eksplisitt.

### Første testforsøk var også grønt på feil grunnlag

Testen jeg skrev lette etter `csrf_token` hvor som helst i malens arvekjede. Den passerte
med feilen intakt, fordi `base_portal.html` har en utloggingsknapp med `{% csrf_token %}`
inne i et skjema: tokenet *var* på sida, bare ikke et sted `getCsrfToken()` så etter. Testen
måler nå kildene hjelperen faktisk leser — meta-taggen eller holderen — og cookien står
uttrykkelig ikke i lista.

Tre vern, alle sett røde: hjelperen kjørt i node mot en stubbet DOM, et strukturelt vern
over alle maler som laster skrivende JS, og et oppførselsvern med `enforce_csrf_checks=True`
som henter tokenet fra meta-taggen slik nettleseren gjør.

---

## 2026-08-29 — Enhetsadmin, og et oppsett som sier fra før det feiler

**1103 tester grønne** (11 nye). Ingen migrasjon.

André prøvde å ta modulen i bruk på staging og meldte at det var «litt knotete». Det var
det, og det var to feil i fase 3 — ikke i oppsettet hans.

**Enheter kunne bare lages fra `manage.py shell`.** Det var ikke en bevisst avgrensning som
`lokasjon`-kommandoen, det var en glipp: sentralbordet fikk lokasjonsadmin, men enheter ble
aldri gitt en flate. En modul som ikke kan tas i bruk uten Railway-konsollen er ikke ferdig.
Enheter opprettes, aktiveres og knyttes til kontoer i et eget admin-panel nå.

Koblingspanelet sier det rett ut, fordi det er stedet feilen ville blitt gjort: **å knytte en
konto til en enhet gir ingen tilgang.** Koblingen avgjør hvilket grensesnitt kontoen får;
hva den har lov til står i modulmatrisen. En test setter en enhet på en konto uten
`ModulTilgang`-rad og krever 403.

At en konto ikke kan være to biler samtidig håndheves nå med en setning admin kan lese.
`OneToOneField` ville avvist det uansett — med en 500.

**Skjemaet lot deg fylle ut alt og feilet ved lagring.** Uten enheter eller lokasjoner ga
«Nytt oppdrag» en «Ukjent eller inaktiv enhet» først etter at du hadde valgt problemstilling,
hastegrad og skrevet fritekst. Det er den verste rekkefølgen: arbeidet gjøres først,
beskjeden kommer etterpå. Siden viser nå hva som mangler, og knappen er avslått til det er
på plass.

### Det som *ikke* var feil

Brukernavn lagres med små bokstaver — `clean_username()` gjør `.strip().lower()`, og
`test_brukernavn_lagres_med_smaa_bokstaver` låser det. `Enhet.navn` er et visningsnavn uten
noen kobling til brukernavnet; «Haugesund 56» og `haugesund56` er to uavhengige strenger.
At de ligner er en felle verdt å kjenne, ikke en sammenheng.

Det som stoppet André var at kontoen hadde **`les`**, og at oppretting krever `skriv_full`.
Siden gjorde akkurat det den skulle — den viste ingen «Nytt oppdrag»-knapp — men den sa ikke
hvorfor. Reprodusert i en diagnose før noe ble endret, så fiksen traff riktig sted.

---

## 2026-08-29 — Oppdragsmodulen fase 3: sentralbordet

**1092 tester grønne** (33 nye). Ingen migrasjon. Modulen er synlig i meny og
dashboard nå som den har en side.

Sentralbordet: enhetsliste med utledet status, oppdragslista for vakta, oppretting,
flytting mellom enheter, tidslinje per oppdrag, og lokasjonsadmin. Polling hvert 30. sekund
med ETag, så et poll uten endring koster en 304 uten kropp.

**To grensesnitt bak én URL.** `/oppdrag/` velger skjerm på om kontoen er knyttet til en
`Enhet` — ikke på nivået. En test setter `skriv_full` på en enhetskonto og krever at den
*fortsatt* får enhetsskjermen: hadde valget stått på «er nivået nøyaktig `skriv_handling`»,
ville den testen vært rød, og feilen §2.3 beskriver ville vært tilbake.

Enhetsskjermen kommer i fase 4. Fram til da får en enhetskonto en mellomtilstand som sier
det rett ut. Alternativet — å sende henne til sentralbordet — ville vist henne alle oppdrag
i vakta, altså nettopp det hun ikke skal se.

**Skjulereglene håndheves i serverens svar.** Testene leser den rå responskroppen, ikke det
serialiserte objektet: `assertNotIn('sensitivt notat', raa)`. Det er den eneste formen som
faktisk beviser at teksten ikke ble sendt. To motstykker holder dem ærlige — fritekst
*vises* mens oppdraget pågår, og sentralbordet beholder den etter `Ledig`.

### To feil testene fant

**`trustedHtml()` ble brukt feil, og hele rendringen var ødelagt.** Funksjonen returnerer en
markør-*objekt* for `cellHtml()`, ikke en streng. `el.innerHTML = trustedHtml(...)` gir
`[object Object]`. Det så riktig ut i koden, og ville vist en tom side i nettleseren. Fanget
av node-testen som kjører byggerne og leser resultatet.

**XSS-gjennomgangen kunne ikke lese sin egen kode.** Regexen som finner `${...}` stopper på
første `}`, så en nøstet mal-streng inne i en interpolasjon ble usynlig — og en uescapet
verdi der ville passert stille. Fragmentene er derfor hoistet ut til variabler over
mal-strengen. Det er bedre kode uansett, men her er det også det som gjør vernet virksomt.

Gjennomgangen leste dessuten sine egne kommentarer: en kommentar som *nevner* `${...}` for å
forklare regelen ble rapportert som et funn. Den stripper `//`-linjer nå, samme grep som
`JsModulLastingTests` gjør for kall.

### Verifisert ved å bryte

Alle vernene er sett røde: radfilteret fjernet (3 feil), fritekstregelen slått av (1),
`@modul_kreves` tatt av flytt-endepunktet (URL-gjennomgangen fanget det og navnga ruta).

Første forsøk på den siste proben **matchet ikke teksten** — `@rate_limit` sto mellom
dekoratørene — så testen «bestod» uten at noe var endret. Verdt å merke seg: en probe som
ikke treffer ser ut som et vern som virker.

Én test til fortjener plassen sin: `test_url_en_svarer` henter modulens URL og krever 200.
Den fanget en 500 som bare oppstår med `ManifestStaticFilesStorage` — altså i prod — fordi
et nytt stilark ikke lå i manifestet.

---

## 2026-08-28 — Oppdragsmodulen fase 1: modeller og regler

**1048 tester grønne** (46 nye). Migrasjon `oppdrag.0001_initial`. Ingen brukervendte
flater — modulen er registrert, men står med `url=None` og begge `show_*`-flagg av.

Fem modeller: `Enhet`, `Lokasjon`, `Oppdrag`, `Statusmelding`, `Enhetsbytte`. Ingen av dem
rører `patients`.

**Fase 2 ble delvis overflødig, og det er en god nyhet.** Planen forutsatte at
audit-logging var noe man måtte melde seg *av*, siden feltlista utledes fra modellen (N2).
Det stemmer per modell: `patients/signals.py` kobler seg på `sender=Patient`, og en ny app
får ingenting automatisk. Audit-signalet for oppdrag er derfor nyskrevet kode, og
skjulingen av `fritekst` er bygget inn fra første lagring i stedet for ettermontert. Det
fjerner vinduet der feltet kunne stått i prod med verdilogging på — og de radene kan ikke
fjernes uten å røre auditsporet.

Skjulingen er en **tredje kategori**, ikke bare et unntak til: `FELT_UTEN_AUDIT` gir ingen
rad i det hele tatt, mens `FELT_UTEN_VERDILOGGING` gir en rad som sier at feltet ble
endret, av hvem og når — men ikke hva som sto der. Sammenligningen gjøres på råverdien;
ellers ville `(skjult) == (skjult)` gjort enhver endring i fritekst usynlig.

Fire invarianter er kodet og testet, alle sett røde først:

- **Statusmaskinen er data**, ikke `if`-er i views. Ukjent status gir `False`, ikke `True` —
  samme regel som ukjent nivånavn i `har_tilgang`.
- **Enhetens status utledes.** Én test krever at `Enhet` *ikke* har en `status`-kolonne, som
  vern mot at noen legger den til «for enkelhets skyld». Et ventende oppdrag gjør ikke
  enheten opptatt: den har ikke rykket ut, og kan fortsatt sendes.
- **Korreksjoner er nye rader** som peker på den gamle, og kan kjedes. Regelen «nyeste
  ikke-korrigerte rad per status vinner» bor i en manager-metode, ikke i en `if` per
  spørring.
- **Fritekst logges uten verdier.** Testen leser den faktiske auditraden og krever at
  teksten ikke er i den.

Å starte et oppdrag mens et annet er i gang lukker det pågående med samme tidsstempel og
`automatisk=True`. En test krever at en manuelt meldt `Ledig` *ikke* får flagget — ellers
ville skillet vært verdiløst.

**Modulen er registrert, men skjult.** En test binder `url`, `show_in_nav` og
`show_in_dashboard` sammen: slås flaggene på uten at URL-en settes, feiler den. Da kan ikke
fase 3 glemme halve jobben.

To tester holder rollemodellen på plass: en konto knyttet til en `Enhet` ser **ikke**
modulen uten en `ModulTilgang`-rad, og en konto med raden ser den. Koblingen er domenedata,
som `Forstehjelper.user` — §7.3 delte `PasientRolleForm` nettopp for å holde kobling og
autorisasjon fra hverandre.

**Lokasjonene vedlikeholdes med `python manage.py lokasjon` inntil fase 3**, ikke med en
admin-side. Planen sa admin-side i fase 1, og den beslutningen ble snudd av en grunn som
først ble tydelig da siden skulle plasseres: modulen har ingen URL ennå, med vilje. En
admin-side uten vei inn er den samme feilen som et modulkort som fører til 404, med et
ekstra steg — og portalen har allerede hatt én slik, oppdaget ved at noen måtte skrive
URL-en for hånd.

Å gi modulen en URL bare for å ha et sted å henge siden ville løst plasseringen ved å
innføre problemet. Kommandoen følger `appsetting`-presedensen — samme rolle, samme
begrunnelse — og gjør staging mulig å fylle med testdata før fase 3 skrives. Den permanente
flaten kommer i modulens eget admin-område, sammen med sentralbordet.

`--deaktiver` framfor sletting: FK-en fra `Oppdrag` er `PROTECT`, så en lokasjon i bruk kan
ikke forsvinne uten å ta historikken med seg. En test sjekker begge deler.

Med det er fase 1 ferdig.

---

## 2026-08-28 — Oppdragsmodulen er planlagt

Kun dokumentasjon. Ingen kodeendring. `docs/BESLUTNING_OPPDRAGSMODULEN.md`.

Modulen blir den første som tar `skriv: handling` i bruk. Nivået ble definert i deploy 1 med
akkurat denne bruken i tankene (§3.2 i rollemodellnotatet) og har stått tomt siden.

**Det André kalte kinkig — to grensesnitt avhengig av tilgang — er ikke et tilgangsproblem.**
Fristelsen er å la nivået velge skjerm: «har du `skriv_handling`, får du bilskjermen». Det er
samme feil som §2.3 beskrev, å bruke et *ordnet* nivå som en *identitet*. Stigen sier at
`skriv_full` dekker `skriv_handling`, og et oppslag på «er nivået nøyaktig `skriv_handling`»
bryter den regelen stille.

Skillet er i stedet rolle i felt: **er kontoen knyttet til en `Enhet`?** Da får den
enhetsskjermen. Ellers sentralbordet, redigerbart med `skriv_full` og skrivebeskyttet med
`les`. Mønsteret finnes allerede — `Forstehjelper.user` er domenedata, ikke autorisasjon, og
§7.3 delte `PasientRolleForm` nettopp for å holde de to fra hverandre. Samme regel her: å
knytte en konto til en enhet gir ingen tilgang.

**Én invariant måtte skjerpes for å overleve offline-kravet.** §3.2 slo fast at et
handling-endepunkt ikke skal lese request-kroppen. En stempling utført uten dekning må kunne
fortelle når den skjedde, ellers viser statistikken når nettet kom tilbake. Regelen er derfor
skrevet om strengere, ikke svakere: kroppen har et lukket skjema på to nøkler — `klienttid`
og `idempotency_key` — og alt annet gir 400. Det er testbart ved uttømming, i motsetning til
en feltwhitelist inne i en generell PUT, der settet av felter vokser med modellen.

**To ting fulgte av kravene uten å være bestilt.** At en enhet skal kunne ha ventende
oppdrag betyr at et oppdrag må kunne være tildelt uten å være påbegynt — altså en status
`Venter` før `Rykker ut`, og at det er enheten som setter `Rykker ut`, ikke 113 ved
oppretting. Gjorde 113 det, ville responstiden løpe fra et tidspunkt ingen i bilen hadde sett
oppdraget. Og at lokasjon ble en admin-vedlikeholdt nedtrekksliste flyttet personvernrisikoen:
feltet er ikke lenger fritekst, A.6/A.12 holder for det, og **fritekst står alene igjen** som
det som må unntas verdilogging. Det halverte fase 2.

Andre avgjørelser verdt å notere:

- **Offline gjelder kun enhetens stemplinger.** Skulle begge sider virke frakoblet, kunne to
  klienter endret samme oppdrag uten å vite om hverandre. Med kun stemplinger finnes ikke den
  konflikten: hver melding er en ny rad.
- **To knapper i grensesnittet, seks navngitte endepunkter på serveren.** Én «neste»-knapp og
  én «Ledig» er nok i en bil i bevegelse; fem knapper der fire alltid er ulovlige er fire
  måter å trykke feil på. Men `POST .../status/neste/` ville latt serveren utlede handlingen
  av gjeldende tilstand, med det kappløpet som følger når to trykk kommer tett.
- **Å starte neste oppdrag lukker det pågående automatisk.** Valgt for farten i felt.
  Kostnaden er at den `Ledig`-meldingen er avledet, ikke målt — derfor lagres et
  `automatisk`-flagg på raden, selv om ingenting viser det. Skillet kan ikke gjenskapes i
  ettertid, og en boolean koster ingenting.
- **«Ledig» er enhetens tilstand, ikke oppdragets, og den lagres ikke.** Ved vaktstart står
  alle enheter som `Ledig` — ikke fordi noe setter verdien, men fordi det er hva «ingen
  påbegynte oppdrag» ser ut som. En lagret status måtte nullstilles ved vaktstart og holdes
  i takt med oppdragsradene resten av vakta; to kilder til samme sannhet går i utakt første
  gang noe feiler halvveis, og da er det den lagrede som lyver. Sentralbordet viser
  `Ledig (2 venter)` — utledet av oppdragene.
- **Enhetsbytte er egen modell**, ikke en radtype i `Statusmelding`. Et bytte er ikke en
  status, og statistikken måler statusene — blandes de, må hver spørring huske å filtrere.
  Statusen står når et oppdrag flyttes: meldingene den første enheten rakk å sende skjedde.
- **To skjuleregler for enheten, begge server-side.** Fritekst utelates fra svaret straks
  status blir `Ledig`; hele oppdraget utelates 30 minutter etter. Skjules fritekst i JS,
  ligger teksten fortsatt i responsen — og en bil som blir stående ulåst er nettopp
  scenarioet regelen finnes for.
- **`Leverer` registrerer ikke hvor det leveres.** Bevisst, for å holde helseopplysninger og
  posisjon fra hverandre.
- **Ingen kobling til `patients`.** «Leveranse oppretter pasient» er notert som noe å vurdere
  senere; i dag ville det latt en `skriv_handling`-konto skrive indirekte inn i
  pasientmodulen.

**Fase 6 utløser registeret CLAUDE.md har varslet.** `/statistikk/` skal få én fane per
kildemodul — pasienter fra samleplass/skadestue, oppdrag fra bil/ambulanse, senere lag. I dag
importerer statistikkappen `patients.services` direkte, og CLAUDE.md sier hva som skjer når
modul nummer to skal levere tall: importen erstattes av et registry etter samme idiom som
`core.backup` og `core.arkiv`. Dette er modul nummer to. §5 gjelder uendret — en fane vises
kun hvis brukeren har `les` på kildemodulen, ellers gir aggregatene avledet innsyn.

Fase 2 står før fase 3: ellers er fritekstfeltet i prod med verdilogging på, og de radene kan
ikke fjernes uten å røre auditsporet. Fase 7 er stedet `AbstractArkiv` bygges — TODO har
utsatt den til modell nummer to faktisk skrives.

Sju faser, 31–44 t. To avklaringer står åpne nederst i notatet; ingen blokkerer fase 1.

---

## 2026-08-28 — `/pasienter/api/stats/` er slettet

**1002 tester grønne.** Ingen migrasjon.

Endepunktet var en rest fra Flask-porten, der header-chipsene ble hentet fra serveren. I dag
regnes de ut i `patients-table.js` fra pasientlista `/api/patients/` allerede har hentet, og
ingen JS-fil i repoet har noen gang kalt stien. Det var gatet på `patients: les` siden
deploy 1, så dette er opprydding, ikke en tetting.

**Det hadde allerede kostet noe.** Da statistikken ble skilt ut, ble det først skrevet at
endepunktet mater chipsene. Det stemte ikke, og forklaringen sto i docstringen til den ble
funnet. Et endepunkt uten konsument tiltrekker seg forklaringer ingen kan falsifisere.

Borte: `patients/views_stats.py` og URL-en. **Ingen redirect satt opp** — en videresending
finnes for klienter som *pleide* å kalle noe, og her fantes ingen.

**`basic_stats()` står igjen**, i motsetning til det jeg først la opp til. Den så ut til å
ha én kaller, endepunktet, men har to: `StatsMatcher` i `patients/tests_arkiv.py` arkiverer
en vakt og krever at `compute_arkiv_stats` gir nøyaktig samme tall. Skulle testen bygget
spørringen selv, ville den speilet produksjonskoden i stedet for å måle den — og sluttet å
fange en endring i hvilke pasienter som teller. Funksjonen er live-siden av den invarianten,
og det står nå i docstringen dens.

Testene i `core/tests_stats_cache.py` brukte endepunktet som prøveklut for
cache-dekoratoren, og kjører nå mot full statistikk. Kontrasten mellom 15 s og 60 s forsvant
med det — den var det eneste stedet 15-sekunders-TTL-en ble brukt — men at dekoratoren
respekterer den TTL-en den får, dekkes av lavnivåtestene som setter den eksplisitt.

Grensetesten i `statistikk/tests.py` er **snudd, ikke slettet**: den låste før at
endepunktet sto igjen, med et notat om at den skulle endres bevisst når rollemodell-arbeidet
avgjorde saken. Nå krever den 404. Neste som lurer på hvor stien ble av finner svaret i en
test i stedet for i git-historikken. Sett rød: la jeg URL-en tilbake, feilet den.

Fulgt opp i dokumentasjonen: `README.md`, `CLAUDE.md`, `core/stats_cache.py`,
`statistikk/views.py`, `docs/TEKNISK_DOKUMENTASJON.md` og `docs/BESLUTNING_STATISTIKK.md`.
Sistnevnte forutsatte at stien fantes og lot spørsmålet stå åpent til
`/pasienter/api/stats/live/` skulle bygges; svaret er nå gitt, og live-endepunktet er
upåvirket — det er et nytt endepunkt med et faktisk formål, og stien er ledig.

---

## 2026-08-28 — To avklaringer: testkontoen og `leder`-nivået

Kun dokumentasjon. Ingen kodeendring.

**Testkontoen i prod er Andrés egen konto uten admin.** Forrige oppføring førte den opp som
en åpen oppgave med den begrunnelsen at «den kan opprette og redigere ekte pasienter under
et navn som ikke tilhører noen på vakt». Det premisset holdt ikke — navnet tilhører noen, og
André håndterer kontoen selv. Punktet er lukket, med mekanikken (CASCADE på `ModulTilgang`,
SET_NULL på `Helsepersonell.user`, `AuditLog.user` blir NULL) beholdt for den dagen den
faktisk slettes.

**`leder`-nivået er merket «VURDER», ikke «skal gjøres».** Bruken er skrevet ned og
begrunnelsen står i §3.1, men behovet er ikke aktuelt. Det tas opp igjen når noen faktisk
skal ha nivået — et tomt nivå er lett å dele ut i god tro, og gir automatisk mer den dagen
det fylles.

---

## 2026-08-28 — Deploy 3: de fem flaggene er borte, og profilkortet sluttet å lyve

**1003 tester grønne** (6 nye). Migrasjon `accounts.0014_fjern_modulflagg`.

Siste steg av de tre i §8. `kan_redigere_pasienter`, `kan_redigere_vakter`,
`kan_redigere_utstyr`, `kan_se_rapport` og `kan_redigere_beredskap` er slettet fra
`CustomUser`. De sto igjen gjennom deploy 1 og 2 fordi en rollback måtte kunne bygge
matrisen fra `role`; da deploy 2 krympet feltet, lukket det vinduet uansett.

**Én ting leste dem fortsatt, og den viste feil svar til brukeren.** Kortet «Modul-tilganger»
på `/min-profil/` bygde på de fem flaggene. Backfillen i deploy 1 utledet fra `role` og rørte
flagget med vilje (§8.1), så en konto med `patients: skriv_full` fikk «Nei» på
pasientregistrering — over teksten «Ta kontakt om du trenger flere tilganger». Siden ba altså
brukeren melde fra om noe hen allerede hadde. Målt før endringen, med kollegaens matrise:

```
  Pasientregistrering    Nei
  Vakter                 Nei
  Utstyr                 Nei
  Rapport                Nei
  Beredskap              Nei
```

Etterpå:

```
  Pasientregistrering    Skrive: full
  Statistikk             Lese
```

To ting endret seg. Kortet **leser `ModulTilgang`** — samme kilde som håndhevelsen — og det
**følger modulregisteret** i stedet for fem hardkodede etiketter. «Vakter», «Utstyr» og
«Beredskap» er ikke moduler; de var plassholdere for apper som aldri ble skrevet, og kortet
lovet tilgang til noe som ikke finnes. Statistikk sto ikke i lista i det hele tatt.

Nivået vises nå med navn (`Lese`, `Skrive: full`) i stedet for Ja/Nei — kortet kan ikke si
«Ja» til en stige med tre trinn uten å skjule hvilket trinn du står på.

**«Slått av» og «ingen tilgang» holdes fra hverandre.** En deaktivert modul får merket «Av»
ved siden av nivået. Slås de sammen, leser brukeren et driftsvalg som et tilgangsvalg og ber
om noe hen allerede har fått.

Testen som fantes krevde bare at de fem etikettene sto i HTML-en, og var grønn hele veien
gjennom feilen. Den er erstattet av seks som måler innholdet, hver med et motstykke som
viser at funnet kan utebli. Alle tre er sett røde: jeg gjeninnførte flagg-oppførselen og
fjernet «Av»-skillet, og fikk henholdsvis tre og én feil.

`test_flagget_paavirker_ingenting` i `BackfillTests` er fjernet, ikke omskrevet. Den lagde to
brukere med samme rolle og ulikt flagg og krevde identiske rader. Uten feltet er de to
brukerne identiske, og testen kunne ikke lenger feile — en test som ikke kan feile er verre
enn ingen test, fordi den ser ut som et vern. Regelen står fortsatt i §8.1, og kartleggingen
låses av testen ved siden av.

`CustomUserPermissionFlagsTests` er snudd i stedet for slettet: den krevde før at de fem
feltene *fantes*, og krever nå at de er borte og at et forsøk på å sette dem feiler høylytt.

---

## 2026-08-28 — Kollegaens nivå satt i prod, og en testkonto som må vekk

Kun dokumentasjon. Ingen kodeendring.

Kollegaens konto står nå på `patients: skriv_full` + `statistikk: les`, med
Helsepersonell-koblingen på plass. Det er den kombinasjonen backfillen ville gitt en `lead`,
satt for hånd i matrisen etter §7.3-splitten — koblingen og tilgangen er to steg nå, med
vilje.

André opprettet i tillegg en testkonto i prod for å kontrollere de samme nivåene selv.
**Den står oppført som en oppgave, ikke som en ferdig ting.** En konto med `skriv_full` i
prod er ikke et testmiljø: den kan opprette og redigere ekte pasienter, og gjør det under et
navn som ikke tilhører noen på vakt. Den må slettes eller deaktiveres før neste vakt, og den
har nøyaktig samme nivåer som kollegaens — det er navnet som skiller dem.

---

## 2026-08-28 — Deploy 2: `role` krympet til `admin`/`bruker`

**997 tester grønne.** Migrasjon `accounts.0013_krymp_role`. **Ikke deployet til prod** —
det krever en egen avgjørelse, se under.

`role` hadde fem verdier. Fire av dem — `lead`, `lead_view`, `read_write`, `read_only` —
beskrev *hva brukeren fikk lov til*, og ingen view leste dem etter at `@modul_kreves` ble
håndhevet i deploy 1. En verdi som ser ut som tilgangskontroll uten å være det er verre enn
ingen verdi: den inviterer neste utvikler til å gate på den. De er nå `bruker`.

**Rekkefølgen var poenget.** Først ble koden gjort uavhengig av de fire verdiene, så krympet
feltet. Motsatt vei ville gitt et vindu der en `has_role_at_least(user, 'read_write')`
sammenlignet mot en verdi som ikke lenger fantes — og den sammenligningen feiler ikke, den
svarer bare feil.

Det som forsvant med koden:

- `has_role_at_least`, `role_required`, `write_required`, `stats_required` og
  `dataset_scope_all` fra `core.auth_decorators`. Igjen står `er_global_admin`,
  `admin_required`, `har_tilgang` og `modul_kreves`.
- `ARKIV_VIEW_MIN_ROLE` og `ARKIV_WRITE_ROLE` fra `patients.services`. De var
  «konfigurerbare» — kommentaren foreslo `lead_view` eller `lead` — til verdier som ikke
  finnes lenger. Arkivet er global admin, og sier det nå rett ut.
- **De to bulk-knappene på brukerlista.** De skrev `kan_redigere_pasienter` på en gruppe
  kontoer og meldte «Fjernet pasientregistrering fra N bruker(e)» uten at noen mistet noe.
  Den meldingen er farligere enn ingen knapp: neste gang tilgang faktisk skal trekkes
  tilbake, tror admin at jobben er gjort.
- **Halve `verifiser_modultilgang`.** Sammenligningen mot `role` og §10.1-tellingen er
  fjernet, ikke gjemt bak en sjekk. Begge krevde at de fire verdiene fantes; etter
  krympingen ville de svart «ingen avvik» og «Antall: 0» om hver eneste database. Et svar
  som alltid er grønt er verre enn ingen kontroll. Igjen står kontroller som holder seg
  like sanne om ti moduler: kontoer uten rader, rader på en modul som ikke finnes, rader
  med et nivå stigen ikke kjenner, og rolleverdier feltet ikke lenger har.

Grensesnittet: rollebadgene i `user_list.html` og `user_detail.html` viser admin mot bruker,
og rollefeltet har fått hjelpetekst. «Bruker» skal ikke leses som «vanlig tilgang» — kontoen
ser ingenting før matrisen sier noe annet.

**Testene sier nå hva kontoen kan, ikke hva den het.** `gi_standardtilgang(bruker)` leste
`bruker.role` og slo opp radene backfillen ville gitt. Det gikk så lenge rollen *var* en
tilgangsverdi; nå ville oppslaget gitt alle testbrukere det samme, nemlig ingenting.
Hjelperen tar en profil eksplisitt — `leser`, `skriver`, `leder_les`, `leder`, `admin` — og
et ukjent profilnavn kaster i stedet for å gi tom tilgang. Det siste er ikke pedanteri: en
test som forventer 403 ville bestått uten å teste noe.

`BackfillTests` skriver fortsatt `read_write` og `lead` med vilje. Migrasjon 0012 kjørte mot
en database der de verdiene fantes, og det er den kjøringen som avgjorde hva kontoene i prod
fikk. Skrev testen `bruker`, ville den bekreftet at backfillen ikke gjør noe.

**Migrasjonen er reverserbar, men vinduet er ikke.** `bruker` → `read_only` ved reversering:
den laveste av de gamle verdiene, fordi reverseringen ikke kan vite hvem som var `lead`.
Matrisen står urørt begge veier — verifisert ved å kjøre migrasjonen fram og tilbake mot en
prod-lignende database. Men etter deploy 2 kan **ikke** en rollback av deploy 1 bygge
matrisen på nytt fra `role`. `ModulTilgang` er eneste fasit fra da av.

På PostgreSQL kjører `AlterField` ingen SQL: `choices` er ikke et databaseattributt. SQLite
bygger tabellen om uansett, men det gjelder bare lokalt og i offline-modus.

---

## 2026-08-28 — `leder`-nivået har fått en begrunnelse, men bygges ikke

Kun dokumentasjon. Ingen kodeendring.

Da `leder` ble tatt ut igjen tidligere samme dag, var argumentet at nivået **ikke hadde
noen definert bruk**, og at et tomt nivå er lett å dele ut i god tro. Det premisset holder
ikke lenger: André har navngitt bruken — **«admin light»**, en vaktleder som skal kunne mer
enn `skriv: full` uten å være global admin.

Sannsynlig innhold, ut fra hva som i dag er admin og som *ikke* er irreversibelt:
arkivere en vakt, se arkivet, redigere navneregistrene. §3.3 gjelder fortsatt for resten —
nullstilling, kollaps, brukeradmin og backup er irreversible eller konto-nære og skal ikke
desentraliseres. «Admin light» er ikke «admin med færre klikk».

**Nivået bygges ikke nå**, fordi behovet ikke er aktuelt. Men begrunnelsen er skrevet ned
så neste runde slipper å utlede den på nytt — og fordi den motsier argumentet som ble brukt
for å ta nivået ut. Å legge til verdien er en `-- (no-op)`-migrasjon; kostnaden ligger i å
bestemme innholdet.

**Kontoen i prod beholdes.** Spørsmålet var om den skulle slettes. Den er den eneste
ikke-admin-kontoen i produksjon, og admin har bypass på hele den nye tilgangsmodellen — uten
den er modulsynlighet, `les` mot `skriv_full` og den server-side gatingen av knapper
utestet i prod til noen får en konto. Da oppdages en feil av en som skal jobbe.

---

## 2026-08-28 — Forhåndsvisning av backfillen, før den kjøres

**1002 tester grønne** (5 nye). Ingen migrasjon.

`verifiser_modultilgang` kunne bare kjøres *etter* deploy 1 — den leser `ModulTilgang`, og
tabellen finnes ikke i prod før migrasjonen har kjørt. `--forhandsvis` viser hva backfillen
**vil** gi hver konto, lest fra `role` alene, uten å røre tabellen. En test teller
spørringer mot den for å håndheve det: går det én, ville kommandoen krasjet i prod.

Den advarer særskilt om én felle: **å «redusere» en konto ved å fjerne
`kan_redigere_pasienter` gjør ingenting.** Flagget stengte aldri et endepunkt (§2.1), og
backfillen utleder fra `role` alene (§8.1) — så kontoen får `skriv_full` likevel. Uten
advarselen ville noen tro de hadde tatt bort skrivetilgang, og oppdaget det motsatte etter
deploy.

Skal en konto ha mindre: endre `role` **før** deploy, eller sett nivået i matrisen
**etter**.

---

## 2026-08-28 — `.admin-only` og `.write-only` rendres server-side

**997 tester grønne.** Ingen migrasjon, ingen endring i hvem som har tilgang.

Klassene skjulte markup i nettleseren med `display:none`. Elementene lå i HTML-en uansett
rolle — inkludert URL-ene til alle admin-sidene. Endepunktene var gatet, så det var ingen
tilgangsgrense, men det er ingen grunn til å sende noe vi vet mottakeren ikke skal ha.

Seks admin-kort og tre skriveknapper rendres nå bak `{% if er_global_admin %}` og
`{% if kan_skrive %}`. Målt i nettleser:

| Konto | «Ny pasient» | Admin-kort | `/portal-admin/` i HTML |
|---|---|---|---|
| `les` | nei | nei | nei |
| `skriv_full` | ja | nei | nei |
| admin | ja | ja | ja |

**`applyRoleVisibility()` er borte.** Den gatet nøyaktig disse tre klassene, og hadde
ingenting igjen å gjøre. `.list-only` var dessuten allerede dødt: `les` er terskelen for å
nå siden i det hele tatt, så betingelsen var alltid sann.

**`er_global_admin` er en context processor** i stedet for noe hvert view sender.
Malene gatet på `request.user.role == 'admin'` direkte — det virker fortsatt, siden `admin`
overlever krympingen i deploy 2, men det er rollefeltet, og hele poenget med rollemodellen
er at maler ikke skal spørre om rollen. Én kilde, med samme navn som helperen i
`core.auth_decorators`.

Testene som kjørte `applyRoleVisibility()` i node er erstattet av tester på riktig lag, og
de er **strengere**: de krever fravær fra HTML-en, ikke at noe er skjult. Verifisert ved å
bytte begge gatene til `{% if True %}` og se seks tester bli røde.

---

## 2026-08-28 — Kontrollkommandoen før deploy 2, og dokumentasjonen ajour

**997 tester grønne** (6 nye). Ingen migrasjon, ingen atferdsendring.

**`python manage.py verifiser_modultilgang`** svarer på §10.1, som deploy 2 ikke kan
kjøres uten. Den skriver ingenting, og har en test som håndhever det: deploy 2 krymper
`role`, og etter det er `ModulTilgang` eneste fasit — feil i denne kontrollen oppdages
først når det ikke lenger går an å regne seg tilbake.

Tre spørsmål den svarer på: hvor mange kontoer hadde skrivetilgang uten flagget (altså en
tilgang de ikke var ment å ha), hvem har ingen rader i det hele tatt (ser en tom portal),
og hvor avviker matrisen fra det backfillen ga.

**Admin er utelatt fra §10.1-tallet**, selv om notatet skriver «role >= read_write».
Formålet er «kontoer som hadde en tilgang de ikke var ment å ha», og global admin var ment
å ha den — de har alltid hatt bypass. Tas de med, teller tallet kontoer som aldri var et
problem, og signalet drukner. På staging var forskjellen 6 mot 4.

**`WRITE_ROLES` er fjernet.** Den var én av de fem kopiene av rollelista (§2.6), og sto
igjen som en ubrukt import etter at skrivesjekkene byttet til `har_tilgang`.

**Dokumentasjonen er ajour:** `CLAUDE.md` beskrev fortsatt rollehierarkiet og
`permission_flag` som gjeldende, og `docs/BESLUTNING_STATISTIKK.md` hadde en tilgangstabell
med `admin/lead/lead_view`. Den siste sier nå eksplisitt at full-stats krever **både**
`statistikk: les` og `patients: les` — modulen komponerer tilgang, den eier den ikke.

---

## 2026-08-28 — To mangler i deploy 1, meldt fra staging

**991 tester grønne** (4 nye). Ingen migrasjon. Begge var funksjonalitet som var *bygget*
men ikke *nåbar* — endepunktet var riktig, veien dit fantes ikke.

**Portalinnstillingene hadde ingen lenke.** `/portal-admin/innstillinger/` var kun
tilgjengelig ved å skrive stien. En side ingen finner er i praksis ikke levert. Lenken
ligger nå i admin-navigasjonen, og `PortalAdminNavTests` går gjennom **hele** nav-blokka —
ikke bare den nye siden — så neste admin-side ikke kan få samme mangel.

**Sletteknappen manglet for `skriv_full`.** Endepunktet var riktig fra §4.2, men knappen i
redigeringsskjemaet var `.admin-only`, så bare admin så den. Rollemodellen var ny; knappen
var gammel.

Den kunne ikke bare bytte klasse: **om en pasient kan slettes avhenger av hvem som
opprettet den og når**, og ingen av delene finnes i klienten. Serveren sender derfor
`kan_slettes` per pasient, og knappen følger det feltet. Standarden er skjult — mangler
feltet, forsvinner knappen.

Flagget koster **én spørring for hele lista**, ikke én per pasient: oppslaget er filtrert på
både bruker og 30-minutters-vinduet, så resultatet er lite uansett listestørrelse. Et
oppslag per rad ville gitt N+1 på endepunktet som pollet hvert 30. sekund av hver klient —
nettopp det `select_related` ble innført for å fjerne.

### Notert, ikke fikset

`.admin-only` og `.write-only` skjules i nettleseren, ikke på serveren — markupen ligger i
HTML-en uansett rolle. Endepunktene er gatet, så det er ikke en tilgangsgrense, men det
røper URL-strukturen for admin-sidene. Husets etablerte mønster, og eldre enn dette
arbeidet. Lagt i TODO; `PortalAdminNavTests` beskriver skillet mellom nav-blokka (gatet
server-side, og testet) og resten.

---

## 2026-08-28 — Deploy 1 ferdig: §4.1 og §4.2

**989 tester grønne** (18 nye). Ingen migrasjon. Deploy 1 er dermed komplett.

### §4.1 — portalinnstillingene flyttet

Arrangementsnavn og sesjonstimeout lå under `/pasienter/` fordi pasientmodulen var den
eneste som fantes. Ingen av dem hører til der: navnet gjelder vakten, som med flere moduler
dekker mer enn pasientregistreringen, og timeouten gjelder innloggingen. Begge krevde
dessuten global admin — og **et admin-endepunkt inne i en modul sier at modulgrensen ikke
betyr noe**, som er nettopp den sammenblandingen `ModulTilgang` skal fjerne.

Begge ligger nå på `/portal-admin/innstillinger/`. `PUT /pasienter/api/settings/` og hele
`api/session-timeout/` er borte; `GET /api/settings/` blir igjen, fordi headeren og
årsfiltreringen trenger verdiene og de er ufarlige for alle som kan lese modulen.
Innstillingsfanen har en lenke i stedet for feltene, og `saveEventName` er ute av
pasientmodulens JS — som F7-notatet i §4.1 forutså.

Validering flyttet med: `AppSetting` er en generisk nøkkel/verdi-tabell uten den, og en
timeout på 0 timer ville logget ut alle umiddelbart. Arrangementsnavnet skrives **etter** at
timeouten er validert, så en avvist innsending ikke lagrer halve skjemaet — det har egen
test.

### §4.2 — slettevindu på 30 minutter

`skriv_full` kan hard-slette **egne** pasienter opprettet siste 30 minutter. Eldre
sletting, og andres, forblir global admin.

Treffer feilregistrering — en duplikat eller et feiltrykk som blokkerer et pasientnummer og
forstyrrer statistikken — uten å gjøre sletting til et hverdagsverktøy. Den som oppdager
feilen er den som registrerte, ikke en admin som kanskje ikke er på vakt.

**«Egen pasient» avgjøres fra auditloggen, ikke fra et nytt felt.** `Patient` har
`created_at`, men ingen `opprettet_av`. `AuditLog` har CREATE-raden med `user`, og
`(table_name, record_id)` er indeksert — billig oppslag, ingen migrasjon.

**Fail-closed:** mangler CREATE-raden, eller har den ingen `user` (importerte rader),
nektes slettingen. «Vet ikke hvem som opprettet den» skal ikke bety «hvem som helst».

Forbeholdet fra §4.2 følger med: DELETE-loggingen lagrer bare pasientnummeret, ikke
innholdet. Etter en sletting vet man *at* pasient #14 ble slettet av Kari 14:32, ikke hva
som sto der. Innenfor et 30-minutters vindu på egne rader er det akseptabelt. Åpnes
sletting bredere senere, må DELETE-loggingen utvides først.

### Verifisert i nettleser

Hele innstillingsflyten: lagring i portal-admin slår gjennom i pasientmodulens header.
Underveis så det ut som lagring logget admin ut — det var probens egen selektor som traff
utloggingsknappen i headeren, ikke skjemaets. Verdt å notere fordi konklusjonen «lagring
dreper sesjonen» ville vært en alvorlig feilmelding å sende videre.

---

## 2026-08-28 — Deploy 1, del 5: varsler, og §9-oppryddingen

**971 tester grønne** (5 nye). Ingen migrasjon. Siste del av deploy 1 utenom §4.1 og §4.2.

**`notify()` sjekker modultilgang** (§10.4). Tilstanden var umulig før `PasientRolleForm`
ble splittet: radioen satte koblingen og tilgangsflagget samtidig, så den som var koblet
hadde per definisjon tilgang. Etter splitten er de uavhengige — og da kunne
`_notify_assignment` sendt et varsel som inneholder et **pasientnummer** og lenker til en
side brukeren får 403 på. Både en lekkasje og en blindvei.

Sjekken ligger i `notify()`, ikke hos hver kaller: en kaller som glemmer den feiler stille,
og `notify()` er den ene porten alle varsler går gjennom.

**En ukjent `module_slug` logges høyt.** Uten det skillet ville en skrivefeil («patient» for
«patients») fått alle varsler til å forsvinne — samme utfall som manglende tilgang, men en
helt annen årsak, og den ene er en feil ingen ville oppdaget. Testene brukte selv
`module_slug='p'`, som ikke er en registrert modul; det ble funnet av nettopp denne sjekken.

### §9-oppryddingen

**`accounts/mixins.py` er fjernet.** Ingenting importerte den, og den var feil:
`RoleRequiredMixin.dispatch()` kalte `super().dispatch()` *først* — altså kjørte viewet —
og reiste `PermissionDenied` etterpå. En POST ville blitt utført og deretter fått 403.
Første klassebaserte view som grep etter `WriteRequiredMixin` ville arvet det.

**`dataset_scope_all` er fjernet.** Definert, re-eksportert i shimen og testet, men sto
aldri på et view.

`accounts/decorators.py` beholdes som shim så lenge `core/tests.py` verifiserer den (N11).

**`docs/TEKNISK_DOKUMENTASJON.md` §6.3 er skrevet om.** Den beskrev et rollehierarki
håndhevet via shimen, med en rollematrise som ikke lenger stemmer og en rad som kalte
hard-deleten «soft». Seksjonen beskriver nå de tre kategoriene, nivåstigen, og at
`CustomUser.role` er under avvikling.

---

## 2026-08-28 — Deploy 1, del 4: grensesnittet gater på det samme som døra

**966 tester grønne** (8 nye). Ingen migrasjon. Meldt fra staging: en konto ble satt ned
fra `skriv_full` til `les`, og «Ny pasient» ble stående. Brukeren fikk opp
registreringsskjemaet, fylte det ut, og møtte 403 på lagre.

Serveren var riktig hele tiden. `applyRoleVisibility()` gatet på `window.USER_ROLE` — og
rollen sier ikke lenger noe om hva du får gjøre i en modul. En `read_write`-konto med bare
`les` fikk `canWrite = true` i nettleseren.

**En knapp som fører til en vegg er verre enn ingen knapp:** brukeren rekker å gjøre
arbeidet før hen får vite at det ikke gikk.

§7.4 er dermed framskyndet fra deploy 2. `window.USER_ROLE` er borte; malen sender
`window.MODUL_TILGANG = {patients: <nivå>, admin: <bool>}`. `admin` er eget felt fordi
global admin står utenfor modulaksen. Redigeringsskjemaet gates på samme kilde — det kunne
også åpnes av en `les`-bruker, med 403 først på lagre.

**Standarden er ingen tilgang.** Mangler globalen, skjules alt som krever noe. Feiler
malen, skal knappene forsvinne — ikke dukke opp.

**Ett skille forsvant med rollene.** `les` dekker både gamle `read_only` og `lead_view`,
som var uenige om pasientlista: den ene fikk den, den andre ikke. Skillet lå aldri i
dataene — `/api/patients/` returnerer det samme til begge, og tavla viser de samme
pasientene. Lista gis derfor til alle som kan lese.

Testene kjører `applyRoleVisibility()` i node med et stubbet DOM, ikke som grep etter
kodelinjer. Verifisert ved å sette `canWrite = true` og se dem bli røde.

---

## 2026-08-28 — Deploy 1, del 3: hullet fra §2.1 er lukket

**958 tester grønne** (9 nye). Ingen migrasjon. Meldt fra staging: en konto uten
modultilgang kom fortsatt inn ved å skrive `/pasienter/` i adressefeltet.

Riktig observert. Synligheten var strammet i del 1, men døra sto åpen — og det er den
kombinasjonen §2.1 beskriver som verst: menyen sier nei, endepunktet sier ja.

**`@modul_kreves` står nå på alle ruter under `/pasienter/` og `/statistikk/`.**
Skrivesjekkene inne i viewene har byttet fra `WRITE_ROLES` til
`har_tilgang(user, 'patients', 'skriv_full')` — rollelista var én av fem kopier (§2.6).

Målt før og etter, med de samme tre kallene notatet brukte:

| | Før | Nå |
|---|---|---|
| `GET /pasienter/` | 200 | **403** |
| `GET /pasienter/api/patients/` | 200 | **403** |
| `POST /pasienter/api/patients/` | 201 (pasient opprettet) | **403**, ingenting opprettet |

Verifisert i nettleser, ikke bare i testklienten.

**URL-gjennomgangstesten er vernet §6 etterlyste.** Den går gjennom `urlpatterns` for
modulens prefiks og krever at hvert view bærer markøren dekoratøren setter — den gjetter
ikke, for en gjetning som tar feil den ene veien slipper et udekorert endepunkt gjennom.
To ruter står i en unntaksliste med begrunnelse; begge er rene videresendinger til
endepunkter som har sin egen gate. Testen sjekker også at unntakene fortsatt finnes, og at
den i det hele tatt finner ruter — en URL-gjennomgang som ikke finner noe passerer
trivielt, og det skjedde i denne kodebasen samme dag med en annen test.

Den fant to hull med en gang: en navnløs legacy-videresending, og statistikkmodulen, som
fortsatt gikk på `stats_required`.

**§5-komposisjonen er på plass.** Statistikkmodulen viser kun kilder brukeren har minst
`les` på i kildemodulen. Uten den er statistikk en bakvei rundt modultilgangen — aggregater
gir avledet innsyn i data man ikke har tilgang til. I dag er `patients` eneste kilde, så
sjekken er én linje; når kilde nummer to kommer, blir det en løkke over registeret.

**Én reell svakhet funnet underveis:** en POST som utelot matrisefeltene fjernet all
modultilgang. Nettleseren sender alltid alle `<select>`-ene, men et delvis skjema, et
skript eller en integrasjon ville stille tilbakekalt tilgang. Fravær av nøkkel er nå ikke
det samme som «velg ingen». Å trekke tilbake tilgang skal være et valg noen tar.

**~90 testbrukere fikk radene backfillen ville gitt dem**, via `gi_standardtilgang()` i
`accounts/test_helpers.py`. En bruker uten rader er en kanttilstand i produksjon, ikke
normalen — de som fantes fikk rader av migrasjonen, nye får dem av matrisen. Testene som
handler om *fravær* av tilgang har bevisst ikke kallet, og sier det i en kommentar.

---

## 2026-08-28 — Deploy 1, del 2: matrisen som faktisk setter tilgang

**946 tester grønne.** Ingen migrasjon. Meldt fra staging: en ny testkonto fikk
«Pasientregistrering» og «Førstehjelper» satt, men så ingen modul på dashboardet.

Det var forutsigbart og forutsagt — §10.3 i beslutningsnotatet — men det gjorde
grensesnittet direkte villedende: avkrysningsboksen «Pasientregistrering» satte
`kan_redigere_pasienter`, og synligheten sluttet å lese det flagget i forrige commit.
Boksen lovet noe den ikke gjorde.

**De fem boksene er erstattet av en matrise modul × nivå**, generert fra
`get_all_modules()`. Boksene var hardkodet i malen, så hver ny modul krevde en redigering
der i tillegg til et nytt felt på `CustomUser`. `admin_only`-moduler er utelatt: de gates
av global admin og bruker ikke `ModulTilgang`, og å vise dem ville antydet at nivået betyr
noe for dem.

**Matrisen ligger på opprettingsskjemaet også** (§10.3), ikke bare på redigering. Uten det
lander den nyopprettede i en tom portal og må redigeres etterpå — og den som oppretter
kontoen er den som vet hva den skal ha.

**`skriv_handling` tilbys ikke i grensesnittet ennå.** Nivået finnes i modellen, og det er
nettopp derfor det ikke trengs en migrasjon den dagen det tas i bruk. Men det er tomt
inntil en modul har et handling-endepunkt, og et nivå som ikke gir noe er lett å dele ut i
god tro. Samme resonnement som `leder` ble tatt ut på. Har en bruker likevel nivået, står
det i lista — ellers ville et lagre-trykk stille fjernet det.

**`PasientRolleForm` er splittet** (§7.3). Radioen satte både FK-en og
`kan_redigere_pasienter`; det er funksjon i felt og autorisasjon i samme kontroll.
Sammenblandingen gjorde det umulig å være koblet som førstehjelper uten å ha tilgang, og
omvendt. To steg i stedet for ett, bevisst.

**Tilgangsendringer auditeres nå**, én rad per modul som endres, med
`table_name='accounts_modultilgang'` slik at de ikke ser ut som endringer på selve kontoen.
**Rolleendring auditeres også** — frysing og sletting skrev auditrad, men det å gi noen
admin gjorde det ikke. Et lagre-trykk uten endring skriver ingenting.

`create_offline_users` gir `vakt-offline` sin rad. Den hadde `role='read_write'` og ingen
tilgang; med håndhevelse ville feltmaskinen møtt en tom portal, og det oppdages i det den
skal brukes — på en vakt uten nett.

En egen test sjekker at matrisen ligger **inne i** riktig `<form>`. POST-testene hadde
bestått uansett hvor i malen feltene havnet.

---

## 2026-08-28 — Deploy 1, del 1: `ModulTilgang` og håndhevelsen

**937 tester grønne** (23 nye). To migrasjoner, begge rullbare. Første del av deploy 1 i
`docs/BESLUTNING_ROLLEMODELLEN.md`; håndhevelsen på endepunktene kommer i neste commit.

`accounts.ModulTilgang(bruker, modul_slug, nivaa)` erstatter de fem
`kan_redigere_*`-flaggene. Nivåene er `les < skriv_handling < skriv_full`; **ingen rad er
ingen tilgang**, og det finnes ingen `'ingen'`-verdi å lagre — to måter å uttrykke det
samme på kommer før eller siden i utakt.

`modul_slug` er bevisst ikke en FK: modulregisteret ligger i kode, ikke i basen, og en rad
for en modul som fjernes fra registeret skal bli liggende ubrukt i stedet for å forsvinne
stille med en CASCADE.

**Backfillen utleder fra `role` alene, ikke fra flagget** (§8.1). Flagget har aldri stengt
et endepunkt, så en bruker som i dag *kan* nå modulen via URL-en ville mistet den i det
håndhevelsen slås på — og en migrasjon som stille trekker tilbake tilgang oppdager du
midt i en vakt. Radene som oppstår bekrefter tilgang folk allerede hadde; ingen
privilegier oppstår, de blir bare synlige. Innstrammingen gjøres etterpå, for hånd.

**Synligheten leser nå samme kilde som håndhevelsen.** `Module.is_visible_for()` leste de
fem flaggene, som ingen view sjekket — menyen og døra var uenige, og det var døra som sto
åpen. `Module.permission_flag` og det midlertidige `min_rolle` er fjernet fra dataklassen;
modellfeltene på `CustomUser` står til deploy 3, ellers har en rollback ingenting å bygge
radene fra.

**`ModuleSettings.enabled=False` stenger nå URL-en** (§2.2). Toggelen var en menybryter —
`GET /pasienter/` ga 200 med modulen deaktivert. Global admin slipper fortsatt inn, ellers
kan man deaktivere seg selv ut av å kunne reaktivere.

`@modul_kreves('patients', 'skriv_full')` er dekoratør, ikke middleware (§6): middleware er
ett sted å glemme, men også ett sted å ta feil av `/pasienter/api/...`. Ukjent nivånavn gir
**False**, ikke True — en skrivefeil i en dekoratør skal stenge døra. Dekoratøren setter en
markør URL-gjennomgangstesten leser, slik at testen ikke trenger å gjette på om et view er
dekorert.

Radene caches per brukerobjekt: nav-menyen kaller `is_visible_for` én gang per modul, og
uten cachen ble det én spørring per modul per sidevisning.

**Backfillen testes ved å kalle migrasjonens egen funksjon**, ikke ved å gjenta
kartleggingen — en test som gjentar logikken består selv om migrasjonen gjør noe annet.
Verifisert ved å forfalske kartleggingen og se testen bli rød.

---

## 2026-08-28 — To feil på staging, og testene som ikke fanget dem

**913 tester grønne** (2 nye). Begge feilene ble meldt fra staging, og begge var samme
klasse: **kode flyttet til en side som ikke gir den det den trenger.** Ingen av dem ga
syntaksfeil, og ingen ble fanget av testsuiten — som er serverside, eller som
sammenligner navn og ikke oppslag.

**«Ny pasient» sluttet å virke.** `patients-utils.js` hadde fortsatt `Chart.defaults` på
toppnivå. Blokken ble kopiert til `statistikk.js`, men aldri fjernet her — og pasientsiden
laster ikke lenger Chart.js. `ReferenceError` drepte resten av fila, så `allPatients`,
klokka og `bsNew`/`bsEdit` aldri ble opprettet. Alt under den linja var borte.
`patients-admin.js` erklærte i tillegg `forstehjelpere` og `helsepersonellListe` på nytt;
to `let` med samme navn i global scope er en `SyntaxError` som drepte hele den fila.

**Statistikkfanene byttet ikke.** `loadStats()` begynte med en rollesjekk på
`window.USER_ROLE` — en global bare pasientmalen setter. På `/statistikk/` falt den til
`'read_only'` og returnerte før første hent. Statistikken var permanent tom, uten én
feilmelding. Kommentaren jeg selv skrev i toppen av fila sa at sjekken var fjernet; den
var ikke det. Endepunktet den kalte var dessuten den gamle stien.

Begge er funnet ved å kjøre sidene i headless Chromium og lese konsollen, ikke ved å lese
koden. Klikkbanen er verifisert samme vei.

**Fanen bytter nå før hentingen, ikke etter.** `loadStats()` returnerer uten å rendre hvis
hentingen feiler (403, 429) — så en bruker som trykket på «Tidsanalyse» ble stående på
forrige fane uten forklaring, også når koden ellers virket.

### To nye tester, begge verifisert ved å gjeninnføre feilen

- **`window.X` må settes av malen** som laster fila. En global malen ikke setter er
  `undefined`, ikke en feil — og det er nettopp derfor den er farlig: koden tar en stille
  default og gjør noe annet enn den skal.
- **`Chart`/`Tabulator`/`bootstrap` må lastes av siden** som laster fila.

**Første utgave av den andre testen var falsk grønn, to ganger.** Den leste rå malmarkup,
og `{% comment %}`-blokken som forklarer at Chart.js *ikke* lastes lenger inneholder
strengen «Chart.js». Rettet til å lese `<script>`-tagger — hvorpå
`src=["\']([^"\']+)["\']` stoppet på den første fnutten inne i
`src="{% static 'js/x.js' %}"`, JS-lista ble tom, og **begge** testene passerte uten å
sammenligne noe. Begge gangene ble det oppdaget ved å gjeninnføre feilen og se at testen
ikke merket det. En test som ikke er sett rød er ikke en test.

### `leder`-nivået reversert

Lagt til tidligere samme dag, tatt ut igjen. Begrunnelsen var at et nytt nivå senere ville
koste en migrasjon på en tabell med produksjonsdata. Det stemmer ikke: `choices` ligger i
Djangos `Field.non_db_attrs`, og `sqlmigrate` sier `-- (no-op)`. Uten den kostnaden står
bare ulempene igjen — nivået har ingen definert bruk, og et tomt nivå i matrisen er lett å
gi bort i god tro. `skriv: handling` beholdes: det er også tomt i dag, men har en navngitt
bruker og en testbar invariant. Se §3.1 i beslutningsnotatet.

---

## 2026-08-28 — Statistikk er sin egen modul

**Etterord samme dag:** denne leveransen ble planlagt uten at
`docs/BESLUTNING_ROLLEMODELLEN.md` var lest — notatet lå på branchen `rollemodell`, ikke
på `main`, og jeg lette ikke etter andre brancher før jeg la planen. Beslutningen fra
24. aug. sier allerede det meste av det som ble utledet på nytt her, og sier det bedre:
statistikk først (§5), backfill fra `role` alene (§8.1), eksplisitt dekoratør (§6), tre
deployer (§8). To ting ble utledet annerledes og er nå rettet mot notatet:

- **Nivåstigen.** Notatet har `ingen → les → skriv:handling → skriv:full`; her ble det
  utledet `les → skriv → leder`. Besluttet 28. aug.: begge, altså
  `ingen → les → skriv:handling → skriv:full → leder`. Se §3.1.
- **Statistikkmodulen komponerer ikke tilgang ennå.** §5 krever at modulen kun viser
  kilder brukeren har minst `les` på i kildemodulen — ellers er den en bakvei rundt
  modultilgangen. Det kan først bygges når `ModulTilgang` finnes, og er lagt til deploy 1.

Koden under står som levert; ingenting av den er feil. Men flere av begrunnelsene er
gjenoppdagelser, og notatet er fasit der de spriker.


**911 tester, alle grønne** (17 nye i `statistikk/tests.py`, 3 nye i
`JsModulLastingTests`). Ingen migrasjon, ingen modellendring, ingen tilgangsendring.

Første av tre leveranser mot rollemodellen. Rekkefølgen ble snudd underveis, og grunnen er
verdt å skrive ned: **statistikk måtte ut av pasientmodulen før `ModulTilgang` kunne
utformes.**

Så lenge «ser statistikk» og «kan skrive» var to akser i samme modul, trengte et
tilgangsnivå per modul fire trinn — det er nettopp derfor `lead_view` (2) står over
`read_write` (1) i `ROLE_HIERARKI` uten å ha skrivetilgang, og derfor `write_required` er
en eksplisitt liste og ikke et `has_role_at_least`-kall. Med statistikk som egen modul blir
den aksen en rad til i tilgangstabellen, og stigen per modul blir `les < skriv < leder`:
en ekte stige. Bygget vi rollemodellen først, ville vi migrert inn en firetrinns kolonne og
måttet migrere den om igjen.

Backfillen hadde fått samme problem. `lead_view` skal ha en `statistikk`-rad, og finnes
ikke slug-en i `get_all_modules()`, er raden foreldreløs: admin-matrisen genereres fra
registeret, så ingen kunne sett eller rettet den.

**`lead_view` sin eneste forskjell fra `read_only` var statistikk.** Tre steder, alle tre
statistikk: `full_stats_view`, nav-elementet `.stats-only` og lastingen av
`patients-stats.js`. Sammenslåingen i den kommende backfillen er derfor tapsfri, ikke en
forenkling.

### Hva som flyttet

| Fra | Til |
|---|---|
| `patients/views_stats.py: full_stats_view` | `statistikk/views.py` |
| `patients/views_arkiv.py: arkiv_full_stats_view` | `statistikk/views.py` |
| `patients/stats_cache.py` | `core/stats_cache.py` |
| statistikkfanen i `templates/patients/index.html` | `templates/statistikk/index.html` |
| statistikkreglene i `static/css/style.css` | `static/css/statistikk.css` |
| ~600 linjer rendering i `patients-stats.js` | `static/js/statistikk.js` |
| ~370 linjer admin i `patients-stats.js` | `static/js/patients-admin.js` |
| primitivene i `patients-utils.js` | `static/js/portal-utils.js` |

`/pasienter/api/stats/` ble **ikke** flyttet.

**Rettelse, samme dag:** begrunnelsen som først sto her — «header-chipsene er for alle
innloggede og hører til siden de står på» — var feil. Chipsene regnes ut i nettleseren, i
`patients-table.js`, fra pasientlista `/api/patients/` allerede har hentet. Ingen JS-fil i
dette repoet har noen gang kalt `/api/stats/`; endepunktet er en rest fra Flask-porten, og
`basic_stats`-docstringen sa det hele tiden. Feilen var å gjøre en foreldet docstring til
bærende begrunnelse uten å sjekke hvem som faktisk kaller endepunktet.

Konsekvensen for denne leveransen er ingen — endepunktet ble uansett stående urørt. Men det
står nå uten kjent konsument, og valget mellom å gate det på pasientmodulen og å slette det
er lagt til rollemodell-arbeidet. `basic_stats()` som *funksjon* blir uansett stående: den
deler aggregeringen med `compute_arkiv_stats`.

### Fire ting som ikke var åpenbare

**Stilarket måtte deles.** `style.css` lastes kun av `patients/index.html`, så hver eneste
statistikkregel ville vært virkningsløs på den nye siden — en endring som ser ut som
ingenting, ikke som en feil. Verre: fire av variablene reglene bruker
(`--text-muted`, `--text-soft`, `--surface-3`, `--header-bg`) er definert i `style.css` og
er *ikke* blant aliasene `base_portal.html` setter. En udefinert custom property gjør ikke
regelen ugyldig — den gjør fargen arvet. Tabelltekst ville altså blitt lesbar eller
uleselig tilfeldig, uten at noe feilet. De fire er derfor definert i `statistikk.css` med
verdiene de hadde; de fire portalen faktisk aliaser er ikke gjentatt, så temaene ikke kan
komme i utakt.

**`patients-utils.js` kunne ikke bare lastes av den nye siden.** Den gjør arbeid på
toppnivå: setter `Chart.defaults` og kaller
`new bootstrap.Modal(document.getElementById('newModal'))`. Uten `#newModal` kaster fila
ved lasting. Primitivene begge sidene trenger — CSRF-fetch, escaping, submit-guard,
`data-action`-delegeringen og `fmtMin` — ligger nå i `portal-utils.js`, som ikke rører
DOM-en før den kalles. `fmtMin` ble faktisk glemt i første forsøk, og statistikksiden ville
kastet `ReferenceError` på hver varighet. `JsModulLastingTests` har fått en test som
sammenligner hva `statistikk.js` kaller mot hva den faktisk laster.

**Arkivstatistikken arvet nesten feil gate.** Endepunktet fulgte med til statistikk-appen,
men tilgangen skulle ikke: arkivet er strengere beskyttet enn live-statistikken
(`ARKIV_VIEW_MIN_ROLE`, i dag `admin`). Hadde det arvet statistikkmodulens gate, ville
`lead_view` fått innsyn i arkiverte vakter uten at noen bestemte det. Viewet har derfor to
gates, og `test_arkiv_full_stats_krever_riktig_rolle` dekker `lead_view` og `lead`.

**De gamle stiene videresender (302).** En deploy midt i en vakt treffer klienter med
gammel JS i cache, og `loadStats()` feiler stille: den logger en advarsel og lar forrige
visning bli stående. Brukeren ville sett gamle tall uten beskjed. 302 og ikke 301, så en
nettleser ikke sitter fast på videresendingen for godt.

### Tilgang: uendret, men strammere JS-lasting

`stats_required` gjelder fortsatt, nå på både siden og endepunktet. Modulsynligheten går
gjennom et nytt, **midlertidig** `min_rolle`-felt på `Module` — alternativet var et
`kan_se_statistikk`-flagg med migrasjon som uansett skulle kastes når `ModulTilgang` kommer.
Feltet fjernes sammen med `permission_flag`.

`patients-admin.js` lastes nå kun for `admin`, ikke for `lead`/`lead_view` som før. Alt som
ble igjen i fila krever `role='admin'` server-side, så de to rollene lastet ~370 linjer de
aldri kunne bruke — hvert endepunkt avviste dem.
---

## 2026-08-24 — Rollemodellen besluttet: modultilgang som faktisk håndheves

Ingen kodeendring. `docs/BESLUTNING_ROLLEMODELLEN.md` erstatter TODO-punktet
«Rollemodellen — trenger beslutning», som sto ubesvart siden 22. aug. Beslutningen måtte
tas før modul nummer to skrives.

**Flaggene var aldri tilgangskontroll.** Verifisert ved å kjøre koden: en `read_write`-bruker
med `kan_redigere_pasienter=False` får 200 på `/pasienter/`, 200 på `GET /api/patients/`
og **201 på POST** — altså full skrivetilgang til en modul hun ikke ser i menyen.
`permission_flag` leses kun av `Module.is_visible_for()`, som bare kalles fra dashboard og
nav. Fire endepunkt-grupper i `patients` er i dag beskyttet av `@login_required` alene.

**`ModuleSettings.enabled=False` stenger heller ikke URL-en** — `GET /pasienter/` gir 200
med modulen deaktivert. Toggelen er en menybryter, ikke nødbryteren navnet lover. Begge
deler rettes: modultilgang håndheves server-side med `@modul_kreves(...)`, og deaktivert
modul gir 403 for alle utenom global admin.

**Hierarkiet var ikke et hierarki av rettigheter.** `lead_view` ligger over `read_write`
(2 mot 1), men har ikke skrivetilgang — så `has_role_at_least(user, 'read_write')` er
`True` for en bruker som ikke står i `WRITE_ROLES`. Ingen live-bug: den hierarkiske
hjelperen brukes kun med `'admin'`, i `views_arkiv.py`. Men den er en felle for neste
modul, og forsvinner med den nye modellen.

**Modellen blir: global admin, pluss ett nivå per modul.** Utgangspunktet var to akser
(les × skriv), fordi dagens fem roller er nettopp det. Den ene aksen kollapset da
statistikk ble besluttet skilt ut som egen modul: `lead_view` gir nemlig *bare*
statistikk — `stats_required` beskytter to endepunkter, `.stats-only` dekker ett nav-punkt
og én fane, og `dataset_scope_all` er død kode som aldri har vært brukt. «Større leserett»
var «tilgang til statistikkmodulen» hele tiden. Igjen står
`ingen → les → skriv:handling → skriv:full`.

**`skriv: handling` finnes fordi en bil-konto skal kunne stemple, men ikke skrive fritekst.**
Det lar seg ikke løse med en rollesjekk: `stamp_pabegynt_if_needed()` og de to andre kalles
fra innsiden av den generelle `PUT`-en, med hele request-kroppen som argument — et
tidsstempel er i dag en bivirkning av en redigering. En feltwhitelist inne i viewet ville
sviktet stille første gang noen la til et felt. Regelen er derfor at en innskrenket aktør
får et *smalt endepunkt*, ikke et filtrert bredt et, og at et `handling`-endepunkt ikke
leser request-kroppen. Det siste er en invariant en test kan håndheve.

**Sletting åpnes forsiktig.** Hard-delete er admin-only i dag, ikke tilgjengelig for
skrivetilgang som antatt. Den åpnes for `skriv: full`, men bare på pasienter brukeren selv
opprettet siste 30 minutter — nok til å rydde en feilregistrering, ikke nok til å bli et
hverdagsverktøy. «Egen pasient» avgjøres fra `AuditLog`s CREATE-rad, som allerede har
bruker og er indeksert på `(table_name, record_id)`; ingen ny kolonne trengs. Forbeholdet
som følger med: DELETE-loggingen lagrer bare pasientnummeret, ikke innholdet — åpnes
sletting bredere senere, må den utvides først.

**Statistikkmodulen komponerer tilgang, den eier den ikke.** Den skal kun vise kilder
brukeren har minst `les` på i kildemodulen. Ellers er den en bakvei rundt modultilgangen.
Rekkefølgen følger av det: statistikk skilles ut før eller sammen med rollemodellen, ellers
bygges en les-akse som umiddelbart rives ned igjen.

**Tre deployer, ikke to.** TODO sa minimum to. Rollekrympingen (`role` → `admin`/`bruker`)
er destruktiv og må ligge mellom «legg til og fyll `ModulTilgang`» og «fjern flaggene».
Defaulten utledes fra `role` alene, ikke fra flagget: en migrasjon som stille trekker
tilbake tilgang oppdager du midt i en vakt.

Ryddes med på veien: `accounts/mixins.py` (død kode, og feil — `dispatch()` kjører viewet
*før* rollesjekken, så en POST ville blitt utført og deretter fått 403), `dataset_scope_all`,
og §6.3 i den tekniske dokumentasjonen, som peker på shimen og kaller hard-deleten «soft».
`session_timeout` og `event_name` flytter til portal-admin — de er portalinnstillinger som
tilfeldigvis bor under `/pasienter/`.

**Én forutsetning gjenstår, og den må kontrolleres i prod:** hvor mange kontoer har `role`
≥ `read_write` men `kan_redigere_pasienter=False`? Det er kontoene som i dag har en tilgang
de ikke var ment å ha, og tallet avgjør hvor stor oppryddingen blir etter deploy 1.

---

## 2026-08-23 — `/accounts/glemt-passord/` var en blank side i produksjon

**910 tester, alle grønne** (3 nye). Rettelse av forrige punkt, meldt av André minutter
etter deploy.

Alle fire reset-malene ble satt sammen ved å ta `head -22` av `invitasjon.html` som felles
hode. Det linjetallet stemte da jeg først så på fila — men jeg hadde selv lagt til
`::placeholder`-regelen der tidligere samme dag, og linjene hadde flyttet seg. `head -22`
kuttet dermed **midt i `<style>`-blokken**: ingen `</style>`, ingen `</head>`, ingen
`<body>`. Nettleseren leste resten av dokumentet som CSS og viste ingenting.

Rettet ved å klippe til og med `<body>` i stedet for til et gjettet linjetall.

**Testene fanget det ikke, og grunnen er verdt å skrive ned.** De sjekket at responsen var
`200`, og at innholdet var **identisk** mellom en adresse som finnes og en som ikke gjør
det. Begge var like ødelagte, så likhetstesten passerte med glans.

En test på at to ting er like sier ingenting om at noen av dem er riktige. Det er en
annen feilmodus enn den vanlige — testen var ikke for svak i seg selv, den var svar på et
annet spørsmål enn det som avgjorde om siden virket.

`SidestrukturTests` sjekker nå at hvert åpnet `<style>`, `<head>` og `<html>` også lukkes,
at `<body>` finnes, og at skjemaet faktisk har et e-postfelt og en submit-knapp. Verifisert
ved å gjenskape feilen: da feiler den, med en melding som forklarer at resten av dokumentet
tolkes som innholdet i det uavsluttede elementet.

Det er tredje gang i dag en test måtte skrives om fordi den bekreftet antakelsen min i
stedet for oppførselen.

## 2026-08-23 — Passord-reset: de sju beslutningene, bygget

**907 tester, alle grønne** (21 nye). Punkt 5 og siste i `BESLUTNING_BRUKERE_OG_EPOST.md` §8.

| § | Beslutning | Hvordan |
|---|---|---|
| 6.1 | Delte kontoer utelates | På `er_delt_konto`, aldri utledet fra «har e-post» |
| 6.2 | MFA kan ikke omgås | Flyten logger ingen inn — den ender på innloggingssiden |
| 6.3 | Sesjoner drepes | `_invalidate_all_sessions()` ved fullført reset |
| 6.4 | `must_change_password` nullstilles | Brukeren velger selv; flagget ville krevd to passord på rad |
| 6.5 | Egen rate-limit-bøtte | `reset:epost` 3/10 min og `reset:ip` 20/10 min |
| 6.6 | Kortere token-levetid | **1 time** |
| 6.7 | Ingen kontoenumerering | Identisk svar, verifisert ved sammenligning |

**Token-maskineriet er generalisert, ikke duplisert.** `accounts/signert_lenke.py` er ny og
eier den delte kjernen; `invitasjon.py` og `passord_reset.py` er tynne lag over den. De 27
invitasjonstestene passerte uendret gjennom refaktoreringen — det var hele poenget med å
gjøre den slik.

**Hver bruk har sin egen salt**, og det er testet begge veier: et invitasjonstoken kan ikke
leses som reset, og omvendt. Uten det ville en invitasjon med tre døgns levetid kunnet
brukes der reset har én time.

**§6.7 kan ikke testes på én respons.** «Ingen kontoenumerering» er en påstand om at to
tilfeller ser like ut, så testene sammenligner faktisk `response.content` mellom en adresse
som finnes og en som ikke gjør det. Tre varianter dekkes: ukjent adresse, delt konto, og en
utsending som feilet — den siste fordi en feilmelding også ville vært et svar.

Rate-limit-svaret er med i samme resonnement. Strupes kun eksisterende adresser, er
strupingen i seg selv et signal. Derfor telles forsøket **før** oppslaget.

**`PASSWORD_RESET_TIMEOUT` er fortsatt ikke satt, og det er riktig.** Notatets §6.6 pekte på
den, men innstillingen leses kun av Djangos egen `PasswordResetTokenGenerator`, som vi ikke
bruker. Å sette den ville antydet en kontroll som ikke er i spill.

**E-posten sier eksplisitt at to-faktor fortsatt gjelder**, og at et passord er uendret hvis
man ikke ba om noe. Begge deler for å unngå at en frivillig som får en uventet e-post tror
kontoen er kompromittert eller at MFA er borte.

## 2026-08-23 — Tvungen utlogging, og MFA som gjelder med det samme

**886 tester, alle grønne** (7 nye).

**«Logg ut brukeren» på brukersiden.** Avslutter sesjonene uten å røre kontoen. Til
forskjell fra «frys» kan brukeren logge inn igjen med det samme — poenget er at de må
*gjennom* innloggingen på nytt. `_invalidate_all_sessions()` fantes allerede fra frys og
admin-reset, så jobben var å koble den til en knapp.

**Og det som faktisk løser problemet: å slå på «Krev MFA» avslutter sesjonene automatisk.**

Behovet kom fra en reell situasjon: glemmer admin å sette MFA ved oppretting og retter det
etterpå, har brukeren kanskje sju timer igjen av sesjonen sin. Kravet gjelder da ikke for
den personen før cookien dør av seg selv. **En sikkerhetsinnstilling som venter på en cookie
er valgfri i praksis** — og den som slo den på tror den gjelder.

Kun overgangen av→på utløser det. En ren navneendring på brukersiden skal ikke kaste noen ut
midt i en vakt, og egen test vokter det.

**«Krev MFA» mangler ikke lenger i opprettingsskjemaet.** Den lå bare i redigeringsskjemaet,
så MFA måtte settes i to steg — akkurat det som skapte behovet over. Samme regel som ellers:
kan ikke kombineres med delt konto, håndhevet i valideringen.

Admin kan ikke logge ut seg selv herfra. Ikke fordi det er farlig, men fordi knappen står
blant handlinger man utfører *på noen andre*, og en admin som mister sin egen sesjon midt i
en vaktstart har et større problem enn den som skulle vært logget ut.

## 2026-08-23 — Placeholder-teksten, og en mal ingen brukte

**879 tester, alle grønne** (1 ny). Meldt inn fra mobil etter at invitasjonsflyten ble
testet ende-til-ende: e-posten kom fram, stor forbokstav i brukernavnet ble håndtert,
og passordet ble satt. To ting igjen.

**`::placeholder` var aldri overstyrt i `portal.css`.** «Fornavn Etternavn» og «Valgfritt» i
brukerskjemaet sto praktisk talt i bakgrunnsfargen. `style.css` har hatt regelen hele tiden,
så pasientmodulen var upåvirket — **nok en gang gjaldt en fiks kun den halvparten av
portalen som laster den fila.** Det er tredje gang i dag den delingen biter.

Regelen er lagt i `portal.css` og i de fire frittstående mørke sidene. Egen tone, dimmere
enn `--portal-text-muted`: en placeholder skal ikke kunne forveksles med utfylt innhold.

Passordsiden i invitasjonen var **ikke** rammet — `SettPassordForm` setter ingen
placeholder. Sjekket fordi det var det naturlige neste spørsmålet, ikke fordi det var meldt.

**Testen er utvidet til å dekke pseudo-elementet, ikke bare klassene.** Regelen den
håndhever nå: farger en mal `.form-control` mørkt, må den også overstyre
`.form-control::placeholder`. Feltet ser riktig ut uten den, og bare innholdet forsvinner —
lettere å glemme enn å oppdage.

**Og den fant `templates/base.html`.** 102 linjer som overstyrte `.form-control` uten
placeholder — men ingenting arver fra den, ingenting rendrer den, og eneste henvisning var
en utdatert docstring i `core/tests.py`. Slettet, jf. prosjektets egen regel om at død kode
skal vekk og ikke få en merknad om at den er ubrukt. Docstringen er rettet til å peke på
`base_portal.html`, som er malen testene faktisk treffer.

**Invitasjons-e-posten har fått `Reply-To: support@sanitet.net`.** Avsenderen er en no-reply
på et domene som ikke tar imot post. Uten dette ville et svar fra en frivillig som lurer på
noe forsvunnet i stillhet — og det er nettopp de som trenger å nå fram, siden de akkurat har
fått en lenke de ikke ba om.

## 2026-08-23 — Innlogging bryr seg ikke lenger om store bokstaver

**878 tester, alle grønne** (9 nye). Utløst av en observasjon fra felt: mobiltastatur setter
automatisk stor forbokstav i tekstfelt.

En konto som heter `kari.nordmann` blir `Kari.nordmann` når den skrives på telefon, og
Postgres skiller på det. Brukeren får «feil brukernavn eller passord» — uten noen antydning
om hva som er galt, fordi meldingen med vilje ikke røper hvilket av de to som feilet.

Det rammer nettopp de som **ikke valgte brukernavnet sitt selv**. Brukernavnet velges av
admin, fordi det er nøkkelen i auditloggen og i koblingen til førstehjelper- og
helsepersonellregisteret — en fast konvensjon er det som gjør loggen lesbar. Prisen er at
brukeren må gjette skrivemåten, og den prisen skal ikke betales ved vaktstart.

Tre lag, som alle trengs:

| Lag | Hva |
|---|---|
| `accounts/backends.py` | Oppslag med `iexact` ved innlogging |
| Innloggingsskjemaet | `autocapitalize="none"`, `autocorrect="off"`, `spellcheck="false"` |
| Oppretting | Brukernavn normaliseres til små bokstaver |

Skjema-attributtene er ikke pynt: de stopper problemet før det oppstår, slik at brukeren
ser det de faktisk skrev.

**Tvetydighet slår aldri ut i feil konto.** Finnes det flere kontoer som kun skiller seg på
store bokstaver — mulig i data som er eldre enn normaliseringen — faller oppslaget tilbake
til nøyaktig treff. En bruker som må skrive navnet sitt nøyaktig er et irritasjonsmoment;
feil konto er et sikkerhetsbrudd.

**En følgefeil måtte lukkes i samme slengen.** Rate-limit-bøtta for innlogging brukte
`post:username` på den rå verdien. Med ufølsom innlogging ville «kari», «Kari» og «KARI»
fått hver sin teller mot én og samme konto, og en angriper kunne mangedoblet
forsøksbudsjettet sitt ved å variere store bokstaver. Nøkkelen normaliseres nå på samme måte
som oppslaget. Egen test som feiler hvis den slutter å gjøre det.

## 2026-08-23 — Testsuiten var flaky, og årsaken var en ekte backup per test

Oppdaget mens brukernavn-testene ble skrevet: samme suite ga syv `ERROR` i én kjøring og
null i den neste, med `sqlite3.OperationalError: database table is locked` fra
`backup_scheduler` — i tester som ikke har noe med backup å gjøre.

`_should_run_now()` returnerer True når `last_run_at` er null, og i en fersk testdatabase er
den alltid det. **Første request i enhver test som gikk gjennom middleware-stacken utløste
derfor en ekte backup**, som skrev filer og rader og av og til låste SQLite-tabellen.

Planleggeren tas nå ut av stacken under test, ved siden av den eksisterende
`_RUNNING_TESTS`-bryteren for passord-hashing. Den testes fortsatt direkte i
patients-testene, så ingen dekning går tapt.

Verifisert med tre kjøringer på rad: 878 grønne hver gang, og låsemeldingene borte fra
tester som ikke er backup-tester.

Dette er verdt mer enn de ni nye testene. En flaky suite lærer deg å kjøre om igjen i stedet
for å lese — og hele dagens arbeidsmåte har hvilt på at «alle grønne» faktisk betyr noe.

## 2026-08-23 — Invitasjonsflyt: det midlertidige passordet finnes ikke lenger

**864 tester, alle grønne** (15 nye). Punkt 4 i `BESLUTNING_BRUKERE_OG_EPOST.md` §8.

Admin oppretter kontoen, systemet sender en signert lenke, brukeren setter sitt eget
passord. Gevinsten er ikke bekvemmelighet: **det finnes ingenting å formidle.** Fram til nå
genererte `user_create_view` et 12-tegns passord som ble vist på skjermen én gang og måtte
sendes videre — typisk over en kanal man ikke vil ha passord i.

**Enbruks uten tabell.** Tokenet inneholder et avtrykk av brukerens passord-hash. Setter
brukeren et passord, endres hashen, og avtrykket i lenken slutter å stemme. Ingen tabell å
rydde, ingen jobb som må huske å utløpe noe. Samme mekanisme Djangos egen
`PasswordResetTokenGenerator` bygger på, uttrykt med den `TimestampSigner` kodebasen
allerede bruker til MFA-trust-cookies — med egen salt, så et token herfra aldri kan
gjenbrukes der.

Kontoen opprettes med `set_unusable_password()`. Den kan altså ikke logges inn på før
lenken er brukt, og `must_change_password` settes **ikke** — brukeren velger passordet selv,
og flagget ville tvunget dem gjennom et nytt passordbytte rett etterpå.

**Tre valg avklart 23. aug. 2026:**

| Valg | Avgjørelse | Begrunnelse |
|---|---|---|
| Levetid | 3 døgn | Er den ikke brukt innen da, blir den sannsynligvis ikke det. Admin sender heller en ny |
| Etter passordsetting | Til innloggingssiden | Brukeren møter MFA-oppsettet på vanlig måte, og får bekreftet at innloggingen virker mens de fortsatt har hjelp tilgjengelig |
| Midlertidig passord | Beholdes som reserve | Delte kontoer har ingen innboks, og e-post kan feile midt i en vaktstart |

**Én melding for alle avvisningsgrunner.** Utløpt, brukt, ugyldig signatur eller frosset
konto gir samme side. Å skille dem ville fortalt en tilfeldig besøkende at en konto finnes —
samme resonnement som ligger bak at innlogging sier «feil brukernavn eller passord», aldri
hvilken. For en frivillig organisasjon er medlemskap en personopplysning i seg selv.

**`er_delt_konto` fikk sine to første regler.** Valideringen *nekter* e-post og navn på en
delt konto i stedet for å la dem stå tomme, og MFA kan ikke kreves — en bil-konto deler
enhet mellom folk som kommer og går, så MFA ville betydd én delt TOTP-enhet eller ingen vei
inn. Begge håndheves i skjemaet, ikke bare i grensesnittet, så de ikke kan omgås ved å poste
direkte.

Utelukkelsen skjer på **flagget**, aldri på «har e-post». Utledningen ville slått feil den
dagen noen la inn en kontakt-e-post på en bil-konto, og da er reset-lenken en lateral vei
inn i systemet.

**Feiler utsendingen, blir kontoen stående.** Admin får en advarsel og en «send på nytt»-knapp
på brukersiden, i stedet for en 500-side og tvil om brukeren i det hele tatt ble opprettet.

En eksisterende test måtte endres: oppretting med e-post gir nå 302 i stedet for 200, fordi
personlige kontoer går invitasjonsveien. Testens egentlige poeng — at adressen trimmes — er
uendret, og den sjekker nå i tillegg at invitasjonen faktisk gikk ut.

**Feltene måtte også inn i redigeringsskjemaet.** Første utgave la dem kun i
opprettingsskjemaet, og da var funksjonen halvferdig for alle kontoer som allerede fantes —
altså alle. De kunne ikke få navn i det hele tatt. Begge felter er nå redigerbare, med de
samme kontotype-reglene: en personlig konto kan ikke gjøres delt med e-posten i behold, og
MFA kan ikke slås på i samme lagring som «delt konto».

**Kontoer uten e-post og navn er upåvirket.** Migrasjonen ga alle eksisterende
`fullt_navn=''` og `er_delt_konto=False`, som begge er gyldige. De logger inn med passordet
sitt som før; invitasjon gjelder kun nye kontoer. `EksisterendeKontoerTests` låser det.

**Men admin-kontoen bør få en e-post.** `create_admin` har `--email` som valgfritt, og
oppsettet i CLAUDE.md kaller den uten. Det er uproblematisk i dag, men når passord-reset
bygges blir admin den ene kontoen som ikke kan bruke den — og det finnes ingen annen admin
til å nullstille den. Ført i TODO.

## 2026-08-23 — `fullt_navn` og `er_delt_konto` på `CustomUser`

**849 tester, alle grønne.** Punkt 3 i `BESLUTNING_BRUKERE_OG_EPOST.md` §8. Kun `AddField`.

| Felt | Type | Formål |
|---|---|---|
| `fullt_navn` | `CharField(max_length=150, blank=True, default='')` | Kjenne igjen personen bak et brukernavn som `superman64` |
| `er_delt_konto` | `BooleanField(default=False)` | Bil-innlogginger og andre ikke-personlige kontoer |

Ett fritekstfelt for navnet, ikke for- og etternavn: det håndterer mellomnavn, doble
etternavn og folk som skriver navnet sitt annerledes enn en skjemadesigner forventer.
`CustomUser` arver `AbstractBaseUser`, så `first_name`/`last_name` finnes ikke å arve.

**Ingen håndhevingslogikk i denne leveransen.** `er_delt_konto` er en kontotype med fire
regler — nekter e-post og navn, MFA kan ikke kreves, selvbetjent reset avvises, passord
settes direkte av admin — men de hører til invitasjons- og reset-arbeidet. Migrasjonen
legger til to kolonner. Det er alt den gjør.

Migrasjonen fikk nummer `0010` og inneholder nøyaktig to `AddField`. Det er gevinsten fra
oppryddingen rett før: uten den ville forslaget fått nummer `0009` og dratt
`is_superuser`-endringen med seg.

**Hva som er verifisert, og hva som ikke er det.** `sqlmigrate` lokalt kjører mot SQLite,
som bygger hele tabellen på nytt for en `AddField` — det er en SQLite-egenskap og sier
ingenting om Postgres. Den utskriften er derfor ikke lagt til grunn.

Grunnlaget for at dette regnes som trygt er i stedet formen på endringen: to kolonner med
default, ingen indekser, ingen constraints, ingen datamigrering, og en brukertabell med en
håndfull rader. På Postgres 11+ er `ADD COLUMN` med default en ren metadataoperasjon.
Skulle databasen være eldre, koster en omskriving av den tabellen uansett millisekunder.

## 2026-08-23 — Migrasjonsavvikene var ikke det vi trodde. Begge er ryddet

**849 tester, alle grønne** (1 ny). To no-op-migrasjoner, ingen SQL mot databasen.

Siden Django 5-oppgraderingen har `makemigrations` foreslått to migrasjoner ved hver
kjøring. Begge ble latt ligge, og disiplinen «husk å strippe det Django foreslår» bodde i
en docstring og i hodet til den som deployet. Etter et spørsmål om vi egentlig var sikre på
årsaken, ble prod-tilstanden lest i stedet for antatt.

**Indeksen: databasen hadde rett hele tiden.**

| | Navn |
|---|---|
| Prod (`pg_indexes`) | `audit_audit_created_2c1626_idx` |
| Djangos tilstand etter `0002` | `audit_audit_created_a3c1b8_idx` |
| Modellen | `audit_audit_created_2c1626_idx` |

Databasen og modellen var enige. Kun bokføringen avvek. Og `a3c1b8` er ikke et navn Django
genererer for den indeksen — verken for `['created_at']` (`2c1626`) eller `['-created_at']`
(`6e540c`). De to andre navnene `0002` satte er eksakt riktige. `0002` skrev altså ett navn
som aldri har hatt dekning i modellen.

**Det forklarer nedetiden 13. august presist.** Den gamle `0004` prøvde
`ALTER INDEX audit_audit_created_a3c1b8_idx RENAME TO ...`, og den indeksen fantes ikke —
databasen sto allerede på målnavnet. Migrasjonen var ikke farlig fordi den gjorde noe
drastisk; den var umulig fordi den beskrev en fortid som ikke hadde skjedd.

Rettet med `audit/0004`, en `SeparateDatabaseAndState` med tom `database_operations`.
Release-fasen er det siste stedet man vil ha en betinget kodesti, så den retter bokføringen
og rører ingenting.

**`is_superuser` var aldri farlig.** Eneste forskjell mot `0001_initial` er `help_text`,
som står i Djangos `Field.non_db_attrs`. Da returnerer `_field_should_be_altered()` False
og `alter_field()` returnerer før den rører databasen — uansett backend. `sqlmigrate`
bekrefter: `-- (no-op)`. Den ble strippet ut av `0008` i august fordi indeks-omdøpingen
crash-loopet samme dag. Riktig forsiktighet under en hendelse, men de to var ikke i samme
klasse.

**Å la dem ligge hadde en pris som var i ferd med å forfalle.** Forslaget for `is_superuser`
fikk nummer `0009` — samme nummer som neste ekte migrasjon. Migrasjonen for `fullt_navn` og
`er_delt_konto`, som står som neste oppgave, ville fått nøyaktig det nummeret. Den som kjørte
`makemigrations accounts && git add -A` uten å lese resultatet, ville fått
indeks-omdøpingens tvillingsøster med på lasset i en helt annen leveranse.

**Disiplinen er flyttet fra hukommelse til testsuite.** `MigrasjonerErISyncTests` kjører
`makemigrations --check`. Er det avvik mellom modellene og migrasjonene, feiler den der —
ikke i release-fasen. Verifisert ved å fjerne `audit/0004`: da feiler den, med Djangos eget
forslag i meldingen.

Testens docstring sier eksplisitt at man **ikke** skal kjøre `makemigrations` for å gjøre
den grønn, men lese forslaget og verifisere med `sqlmigrate` først. Det er den vanen som
manglet.

## 2026-08-23 — «Mine pasienter» så mer påslått ut når den var av

**848 tester, alle grønne.** Kun CSS.

Knappen hadde tre tilstander som ikke rangerte riktig:

| Tilstand | Utseende | Kilde |
|---|---|---|
| Av | Lyseblå ramme, lyseblå tekst | Bootstrap `.btn-outline-info` |
| På | Blek blå fyll, mørk turkis tekst | `.active-mine` |
| Av, med markør/fokus på knappen | **Full cyan fyll, svart tekst** | Bootstrap `:hover` |

Den siste er kraftigst av de tre, og den betyr «av». Etter et klikk blir markøren stående
på knappen, så det er nettopp den tilstanden man ser rett etter å ha slått filteret av.

**På touch er det verre.** `:hover` henger igjen etter et trykk til man treffer noe annet,
så på iPhone ble knappen stående fylt — ikke bare et øyeblikk.

Det fantes ingen hover-regel for knappen i det hele tatt; Bootstraps egen tok over.
På-tilstanden trengte ingen fiks — `#btn-board-mine.active-mine` har ID-spesifisitet og
`!important`, og slår Bootstraps hover allerede. Det var kun av-tilstanden som måtte
dempes, til et svakt hint i stedet for en fylling. `:focus` er med i selektoren fordi
fokus blir liggende igjen etter et trykk.

**Filterknappene i lista er urørt.** Der er den sist trykkede alltid den aktive, så den
etterslepende hover-tilstanden treffer en knapp som uansett har sin egen farge fra en
`!important`-regel. Problemet er spesifikt for en av/på-bryter.

Ingen test på dette. En regel-eksisterer-test ville gitt samme falske trygghet som den
gjorde tidligere i dag — invarianten er visuell, og bekreftes i grensesnittet.

## 2026-08-23 — Fargen var riktig i prod hele tiden. Nettleseren fikk den bare aldri

**848 tester, alle grønne** (2 nye). Årsaken til to runder med «ingenting har endret seg».

Begge CSS-fiksene lå ute i produksjon. `curl` mot `/static/css/portal.css` ga det nye
innholdet. Likevel så André den gamle fargen.

`STATICFILES_STORAGE` **ble fjernet i Django 5.1.** Prosjektet kjører 5.2, så linja sto
igjen som død konfigurasjon og ble ignorert — uten sjekk, advarsel eller feilmelding.
Django falt tilbake til `StaticFilesStorage`:

* ingen hashing av filnavn, altså **ingen cache-busting**
* WhiteNoise serverte fila under samme navn med `Cache-Control: public, max-age=14400`
* enhver CSS- eller JS-endring var dermed usynlig for en bruker som hadde besøkt siden,
  i inntil **fire timer** etter deploy

Sporet lå i release-loggen hele tiden: «138 static files copied to '/app/staticfiles'» —
uten det etterfølgende «post-processed», som er manifest-steget. Etter fiksen sier den
«414 post-processed».

Rettet ved å flytte til `STORAGES`-innstillingen, som er den Django 5 faktisk leser.

**Dette har gjeldt hver frontend-endring siden oppgraderingen til Django 5.1.** Ingen av
dem var feil; de nådde bare ikke fram til en nettleser som allerede hadde vært innom.
CSS-arbeidet i sommer, F7-oppdelingen av JS-modulene, dagens tekstfarger — alle har hatt
opptil fire timers forsinkelse ut til brukeren, uten at noe sa fra.

**Testen sjekker oppførsel, ikke innstillingsnavn.** En test på
`settings.STORAGES['staticfiles']['BACKEND']` ville gått god for nøyaktig samme feil neste
gang Django flytter en innstilling: navnet ville stått der, og ingenting ville brukt det.
`StatiskLagringTests` slår i stedet opp lagringen som faktisk er i bruk og krever at den
hasher.

**En stille testsvekkelse fulgte med.** `JsModulLastingTests` sjekket `assertIn` og
`assertNotIn` på `'patients-stats.js'` ordrett. Med hashing heter fila
`patients-stats.<hash>.js`, så den positive testen feilet — synlig og greit. Men den
negative ville **bestått uansett**, også om `read_only` faktisk lastet statistikkbundlen.
Det er hele F7-vernet. Begge er gjort hash-tolerante.

**Fellesnevneren med resten av dagen:** verifiseringen ble gjort på feil sted. `curl` mot
serveren svarte riktig, men beviset som trengtes var hva nettleseren faktisk lastet.

## 2026-08-23 — Hjelpeteksten var fortsatt uleselig: fiksen lå i feil fil

**846 tester, alle grønne.** Rettelse av forrige punkt.

Regelen for `.form-text` ble lagt i `style.css`. **Ingen av de tre meldte sidene laster den
fila.** `style.css` lastes kun av pasientmodulens `index.html`; alt som arver
`base_portal.html` — passordbytte, begge backup-sidene — får `portal.css`. To mørke temaer,
to filer. Regelen er nå lagt i `portal.css` også.

Den i `style.css` blir stående: `index.html` bruker `.form-text` to steder selv.

**Testen hadde samme blindsone som fiksen.** Den hentet markup fra begge malkatalogene, men
sjekket kun `style.css` — og bestod dermed mens sidene var like uleselige som før. At jeg
verifiserte at den feilet uten fiksen hjalp ikke: den fulgte endringen min trofast, den
fulgte bare ikke lastekjeden.

Testen løser nå `{% extends %}` og `{% static %}` for hver mal, og krever overstyringen i
det stilarket malen faktisk kan se — inkludert arvede `<style>`-blokker.

**Da dukket fire til opp**, ingen av dem meldt inn:

| Mal | Klasse |
|---|---|
| `templates/403.html` | `.text-muted` |
| `templates/accounts/mfa_setup.html` | `.text-muted` |
| `templates/accounts/mfa_verify.html` | `.text-muted`, `.form-text` |
| `core/templates/core/backup_admin_restore.html` | `.form-text` |

De tre første er frittstående sider med egen `<style>`-blokk og `background: #0f172a`, uten
noen overstyring. De har vært like uleselige hele tiden — bare på sider man sjelden er på.
Alle er rettet med samme verdi, `#94a3b8`.

**Lærdommen er ikke «skriv en test».** Det gjorde jeg. Den var like avgrenset som fiksen,
fordi jeg utledet den fra endringen i stedet for fra kravet. En test som speiler antakelsen
din bekrefter antakelsen, ikke oppførselen.

Caching var forresten aldri involvert: `CompressedManifestStaticFilesStorage` hasher
filnavnene, så den nye `style.css` ble servert med det samme. Den var bare aldri lastet av
de sidene det gjaldt.

## 2026-08-23 — AHASend-avtalen var aldri en mangel

Kun dokumentasjon. Ingen kodeendring.

TODO har ført «Databehandleravtale med AHASend» som **forfalt** siden 22. august, med den
begrunnelsen at leverandøren er i bruk i produksjon uten avtale på plass. Den premissen
var feil.

AHASends DPA (https://ahasend.com/dpa) krever ingen signatur. Den er inkorporert i Terms
of Use, og teksten er utvetydig: *«By using the Services, Controller accepts this DPA.»*
Avtalen har dermed vært i kraft siden portalen sendte sin første melding. En motsignert
utgave kan bes om, men endrer ikke rettsvirkningen.

Det som faktisk mangler er derfor mindre enn antatt, men ikke ingenting: **dataflyten er
fremdeles ikke dokumentert i A.2**, og C.3 påstår fortsatt «Ingen andre databehandlere er
for øyeblikket i bruk». Det står som eget punkt til dokumentgjennomgangen.

Nøkkelpunktene er notert i TODO for den gjennomgangen. To ting er verdt å trekke fram:

**Underbehandlerne er alle i EØS som standard** — Hetzner (Tyskland/Finland), DA
International Group (Bulgaria) og Blix Solutions (Norge) — og behandlingen skjer
*«primarily within the European Economic Area»*. US-infrastruktur hos Hetzner er
tilgjengelig «upon request». Er den valgt, utløses SCC-sporet og A.2 må beskrive en
tredjelandsoverføring. Det er ett blikk i konsollen, og står som eget punkt.

**Avtalen forbyr sensitive data:** *«Controller agrees not to use the Services to send or
store Sensitive Data.»* Feilvarselet vårt inneholder brukernavn, rolle, klient-IP, URL og
traceback — personopplysninger, men ingen helseopplysninger. Slankingen 22. august fjernet
skjemadata, cookies, settings og lokale variabler, og `core/tests_error_reporting.py`
vokter det.

Den testen er dermed ikke lenger bare en personvernfinesse. Den holder oss innenfor en
kontraktsforpliktelse overfor databehandleren, og bør leses som det neste gang noen
vurderer å utvide varselet.

## 2026-08-23 — To synlige feil: umarkert filter og uleselig hjelpetekst

**846 tester, alle grønne** (3 nye). Ingen backend-endring.

**Hjelpetekst forsvant i bakgrunnen.** Bootstraps `.form-text` er `#6c757d` — laget for
lys bakgrunn — og var aldri overstyrt for portalens mørke tema (`--app-bg: #0f172a`).
`.text-muted` og `.text-secondary` var overstyrt for lenge siden; `.form-text` ble aldri
med. Rammet passordreglene på `/accounts/change-password/` og begge hjelpetekstene på
`/portal-admin/backup/patients/` og `/arkiv/`.

Én regel med samme verdi som `.text-muted`, så all sekundærtekst i portalen har én farge.

Testen er skrevet bredere enn de tre tilfellene: den finner hvilke Bootstrap-klasser for
dempet tekst som faktisk brukes i malene, og krever en overstyring for hver. Neste gang
noen tar i bruk en ny slik klasse, sier suiten fra — i stedet for at noen må lese teksten
for å oppdage det.

**«Mine pasienter» var umarkert på tavla.** `toggleBoardMine()` satte `.active-mine` på
`#btn-board-mine`, men eneste regel var `.filter-btn.active-mine`, og den knappen har
ikke `filter-btn`. Klassen ble satt hver gang og traff aldri noe. Filteret virket —
markeringen var usynlig.

TODO foreslo å legge `filter-btn` på knappen. **Det ble ikke gjort.** Klassen gir
pille-form og 0.78rem skrift, og tavleknappen står ved siden av «Ny pasient» i
verktøylinja, ikke i filterraden. Den ville blitt visuelt ulik naboen — én visuell feil
byttet mot en annen. Selektoren er utvidet i stedet.

**Testen bestod først uten at fiksen var der.** `re.findall` på CSS-en matchet prosaen i
kommentaren jeg nettopp hadde skrevet over regelen, med tom prefiks-gruppe, og
`treffer`-sjekken godtok den. Testen ble rettet til å stripe kommentarer først, og
deretter verifisert ved å reversere fiksen: da feiler den, slik den skal.

Det er verdt å notere som mønster, ikke bare som en rettelse. En test som bare kjøres
etter at fiksen er på plass, forteller ingenting om at den ville fanget feilen.

## 2026-08-23 — F3: dobbeltregistreringen fra 30. april kan ikke skje igjen

**843 tester, alle grønne** (14 nye).

30. april 2026 ble en pasient registrert dobbelt på Grønn sone i prod fordi brukeren
dobbeltklikket før serveren rakk å svare. Delte soner har ingen unik-sjekk, så begge
forespørslene gikk gjennom. `withSubmitGuard()` kom som svar på klikket. F3 dekker
tilfellene guarden ikke ser, fordi de skjer utenfor knappen.

`core/idempotency.py` er ny. Klienten lager en nøkkel når registreringsskjemaet åpnes og
sender den som `idempotency_key`. Serveren reserverer den med `cache.add()` — atomisk;
`get()` etterfulgt av `set()` ville sluppet begge gjennom i nettopp det vinduet mekanismen
finnes for å lukke.

| Tilstand | Svar |
|---|---|
| Nøkkelen ledig | Oppretter, `201` |
| Første forespørsel pågår fortsatt | `409` med `duplikat: true` |
| Nøkkelen brukt opp | Samme pasient, `200` — ikke `201`, for ingenting ble opprettet nå |
| Ingen eller ugyldig nøkkel | Nøyaktig som før F3 |

**Rekkefølgen er hele poenget: reserver etter all validering, aldri før.** Brenner en
avvist innsending nøkkelen, får brukeren som retter feilen «allerede sendt inn» på det
korrigerte forsøket — og kommer ikke videre uten å lukke og åpne skjemaet på nytt. Feiler
`save()` etter reservasjonen, frigis nøkkelen. Begge stiene har egen test.

**`crypto.randomUUID()` alene ville brukket feltbruk.** Den finnes kun i «secure context»,
altså ikke over ren HTTP — og `OFFLINE_MODE` kjører nettopp uten TLS, med vilje. Uten
fallback ville hver registrering i felt kastet `TypeError` på en linje som ser triviell ut.
`crypto.getRandomValues` er tilgjengelig også uten TLS og bærer fallbacken.

**To faner er ikke dekket, og skal ikke være det.** Nøkkelen lages når skjemaet åpnes, så
to faner har hver sin. Det kan være to reelle pasienter, og å slå dem sammen ville vært en
verre feil enn den vi retter. Dekket er dobbeltinnsending fra samme skjema, automatisk
nettverks-retry, og API-klienter som prøver på nytt etter tidsavbrudd.

**409 vises ikke som en feil.** Pasienten blir opprettet uansett, så modalen lukkes og
lista lastes — samme utfall som suksess. En rød boks ville bedt brukeren rette noe som
ikke er galt, og er den typen melding som fører til at noen registrerer på nytt.

Cache-feil betyr «opprett uansett», som i `core/ratelimit.py`. Under vakt er en
dobbeltregistrering et irritasjonsmoment; en pasient som ikke lar seg registrere fordi en
cache er nede er det ikke.

## 2026-08-23 — Verifisert i prod: cron, backup og passordbytte. Og en slettemekanisme som ikke finnes

**829 tester, alle grønne.** Én docstring rettet, ellers bokføring.

Tre punkter bekreftet i produksjon, alle tre kjørt av André der de faktisk hører hjemme:

- **`kollaps_arkiv --dry-run` i containeren:** «Ingen arkiv eldre enn 730 dager som ikke
  allerede er kollapset.» Ventet — arkivene er fra 2026. Første skarpe kjøring 1. september
  har dermed ingenting å slette
- **Manuell backup tatt:** 270 pasienter
- **Passordbytte:** feil nåværende passord gir «Nåværende passord er feil», ikke 429.
  Rettelsen tidligere i dag virker i prod

**270, ikke 273.** Tre av de importerte var testpasienter og ble slettet før backupen.
Det er tallet en framtidig restore skal gi — ser man 273, er man på en eldre backup.

**Og der dukket et dokumentasjonsavvik opp.** For å si hva «270» betyr for backupen måtte
jeg vite om de tre var soft-slettet eller borte. Svaret: borte.
`DELETE /api/patients/<pk>/` er en hard-delete som fjerner raden og resirkulerer
pasientnummeret.

Docstringen på viewet påsto det motsatte — «Oppdater eller slett (soft-delete) en pasient».
Den er rettet, og sier nå eksplisitt at eneste vei tilbake er en backup tatt før slettingen.
Det er ikke en detalj å ta feil av i en docstring over en destruktiv operasjon.

Mer alvorlig: **ingen produksjonskode setter noen gang `Patient.is_active = False`.** Feltet
finnes på modellen og leses av `?include_archived`, men kan bare settes via Django-admin —
og den flaten er av i produksjon siden S1. Soft-delete av pasientdata er altså en mekanisme
som er beskrevet, men som ingenting utløser.

`PERSONVERN_DOKUMENTASJON.md` beskriver den likevel to steder: A.6 kaller `is_active=False`
«logisk slettet / soft-delete», og rettighetstabellen sier «Pasientdata soft-slettes;
permanent sletting på forespørsel». Avviket går i registrertes favør — sletting er *mer*
endelig enn dokumentert, ikke mindre — men dokumentet er art. 30-protokollen og skal
beskrive det som faktisk skjer. **Ikke rettet her**, fordi en endring i det formelle
dokumentet hører sammen med de andre punktene som venter på gjennomgang. Lagt i TODO.

Det er samme sjekk som S7 handlet om, med motsatt fortegn: forrige gang beskrev dokumentet
en sletting som ikke fant sted. Denne gangen beskriver det en bevaring som ikke finner sted.

## 2026-08-23 — Passordbytte kunne stenge en ny bruker ute av portalen

**829 tester, alle grønne** (2 nye). Rettelse av S3, samme dag som den ble deployet.

En gjennomgang av om takene var realistisk satt fant at fire av fem var det, og at ett var
satt på feil hendelse.

`accounts:change-password` lå som dekoratør på hele viewet med `10/5m`, og telte dermed
**hver** POST — også de som ble avvist av skjemavalidering. Django avviser for kort passord,
passord som ligner brukernavnet, vanlige passord og rene tall, i tillegg til bekreftelse som
ikke stemmer.

Det som gjorde dette alvorlig er hva som ligger rundt endepunktet.
`MustChangePasswordMiddleware` sperrer hver eneste URL unntatt passordbytte, utlogging,
innlogging og static. En bruker med `must_change_password=True` kommer altså ikke inn i
portalen i det hele tatt før byttet lykkes. En ny frivillig som fomlet med passordreglene
på mobiltastatur ved vaktstart kunne bruke opp ti forsøk på fem minutter, og var da stengt
ute av **hele portalen** til vinduet løp ut.

Og bøtta beskyttet ingenting i den tilstanden: `old_password` sjekkes kun når
`must_change_password` er `False`. I tvungen-bytte-stien finnes det ikke noe gammelt passord
å gjette.

Det er samme feil som N4, i ny drakt — **telleren telte feil hendelse.** Der var det MFA-
forsøk som havnet i samme bøtte fordi nøkkelen slo opp et felt skjemaet ikke sendte. Her var
det skjemafeil som ble talt som om de var angrep.

**Fiksen:** tellingen er flyttet fra dekoratøren inn i viewet, til punktet der gjettet
allerede er slått fast som feil. Bøtta heter nå `password:old-guess` — navnet sier hvilken
hendelse den teller, ikke hvilket endepunkt den henger på. Konsekvensene:

- Tvungent passordbytte rører aldri bøtta. En ny bruker kan ikke låse seg ute
- Et **riktig** nåværende passord koster ikke kvote
- Avviste skjemaer koster ikke kvote
- Ti feilede gjett på nåværende passord gir fortsatt 429, som før

To nye tester dekker nettopp de to første punktene, siden det er dem en refaktorering vil
miste først.

**De fire andre takene ble stående.** Målt mot hva appen faktisk gjør: `doAutoRefresh`
kaller `loadStats` kun mens statistikkfanen er aktiv, altså rundt 2/min mot en grense på 30.
`PUT`/`DELETE` mot en pasient har to kallsteder, begge modal-lagringer bak
`withSubmitGuard`. Pasientregistrering krever fem utfylte felt, så 1–3/min er realistisk
peak mot en grense på 60. Marginene er store med vilje: takene skal skille et menneske fra
en løkke, ikke bremse noen.

**Én luke notert, ikke lukket:** `/api/innstillinger/arkiv/<pk>/full-stats/` kjører samme
tunge beregning som `/api/full-stats/`, men fikk ingen bøtte. Admin-only og uten
auto-refresh, så eksponeringen er lav. Ligger i TODO.

## 2026-08-23 — S3: rate-limiting utover innlogging, og en kommentar som løy

**812 tester, alle grønne** (15 nye).

Innlogging har hatt rate-limiting siden N4. Alt annet var ubeskyttet: en
`read_write`-bruker — eller en stjålet sesjonscookie — kunne opprette pasienter i løkke så
fort serveren rakk å svare, og en admin kunne hente 5000 auditrader per kall uten grense på
antall kall.

`core/ratelimit.py` er ny og eier mønsteret. Grensene:

| Endepunkt | Metode | Grense | Bøtte |
|---|---|---|---|
| `POST /pasienter/api/patients/` | POST | 60/min | `patients:create` |
| `PUT`/`DELETE /pasienter/api/patients/<pk>/` | PUT, DELETE | 120/min | `patients:detail-write` |
| `GET /pasienter/api/full-stats/` | GET | 30/min | `patients:full-stats` |
| `POST /accounts/change-password/` | POST | 10/5 min | `accounts:change-password` |

> Bøtta over ble omdøpt til `password:old-guess` samme dag, og teller nå kun feilede
> gjett — se rettelsen øverst i denne fila.
| `GET /portal-admin/auditlog/eksport.csv` | GET | 10/min | `audit:csv-export` |

Nøkkelen er per bruker, og gruppen oppgis eksplisitt på hvert kallsted. Det er lærdommen
fra N4 gjort til regel: der havnet alle MFA-forsøk fra alle brukere i samme bøtte, og ved
vaktstart fikk bruker nummer elleve 429 uten at noe var galt med kontoen. Utledes gruppen
av funksjonsnavnet, kan en flytting mellom moduler slå to bøtter sammen igjen — stille.

Pasient-redigering sto ikke i S3s opprinnelige liste. Den er tatt med fordi akseptansen
handler om skrivelast mot databasen, og `PUT` er skrivelast. Bøtta er romsligere enn ved
opprettelse: obs-tider stemples, sonen endres, pasienten skrives ut — redigering skjer
oftere enn registrering.

**Kommentaren i `settings.py` løy, og det betydde noe.** Den påsto at django-ratelimit
«failopener av seg selv ved cache-feil». Pakken gjør det motsatte, i begge retninger:

- `RATELIMIT_FAIL_OPEN` er `False` som default. Svarer cachen uten verdi, settes
  `should_limit=True` — altså 429 på **alt**.
- Kaster cachen i stedet — som `cache.add()` gjør mot en død Redis — fanges det ikke.
  `socket.gaierror` er eneste unntak pakken tar. Endepunktet ville svart 500.

Uten S3 gjaldt dette bare innlogging, der det er ubehagelig. Med S3 ville det gjeldt
pasientregistrering under vakt, der det er uakseptabelt. Begge stier er nå lukket: flagget
settes `True`, og `er_rate_limited` fanger exceptions og slipper forespørselen gjennom med
en `WARNING` i loggen.

Prioriteringen er den samme som F3 formulerer for idempotens, og som `stats_cache.py`
allerede gjør for statistikken: **bedre en manglende bremse enn en pasient som ikke kan
registreres.** Innlogging mister ikke noe reelt på dette — kontolåsingen (5 feilede forsøk
= 15 min) ligger i databasen og er uavhengig av cachen. `accounts/views.py::_er_rate_limited`
delegerer nå til kjernen, så den stien får samme håndtering.

**429 måtte bli synlig, ellers var strupingen farligere enn problemet.** Skjemaet i
`patients-forms.js` håndterte kun 400. En strupet registrering ville derfor sett ut som
ingenting: modalen ble stående åpen, uten feilmelding, mens pasienten ikke var lagret.
Både registrerings- og redigeringsskjemaet viser nå serverens tekst ved 429.
Statistikkfanen leste tidligere svarkroppen uansett status utenom 403; den lar nå forrige
visning stå i stedet for å rendre tomme grafer over en feilmelding. To nye node-tester
kjører `_saveNewImpl()` med stubbet DOM og verifiserer begge deler — ingen grep etter
kodelinjer, jf. N9.

**Grensene er bare så delte som cachen er.** Appen kjører i dag én gunicorn-worker med
fire tråder mot LocMemCache, så telleren er felles for all trafikk. Settes `WEB_WORKERS`
høyere uten `REDIS_URL`, får hver worker sin egen teller og den reelle grensen blir
grensen ganger antall workers; `--max-requests 1000` resirkulerer i tillegg workeren
jevnlig og nullstiller tellerne. Begge avvikene går samme vei — bremsen blir mildere enn
konfigurert, aldri strengere. Det er den ufarlige retningen.

Nød-bryteren `RATELIMIT_ENABLE=False` slår av alt uten deploy, som før.

## 2026-08-23 — Cron er bevist i drift: 3 varsler faktisk slettet

Kun dokumentasjon. Ingen kodeendring.

`purge_old_logs` fyrte som Railway Cron natt til søndag 23. august, og slettet de 3
varslene fra 12. mai. Cron-tjenestens logg:

```
Starting Container
Slettet 0 login-events eldre enn 730 dager.
Slettet 0 audit-logger eldre enn 730 dager.
Slettet 3 varsler eldre enn 30 dager.
```

**Hvorfor dette er beviset og tørrkjøringen ikke var det.** Teksten er den skarpe
varianten — en tørrkjøring hadde skrevet «Ville slettet», med `[Tørrkjøring]` foran.
Tallet 3 er nøyaktig det tørrkjøringen dagen før identifiserte. Og den kjørte i
containeren, mot produksjonsdatabasen, utløst av cron. Alle tre leddene som kunne
sviktet stille — at cron fyrer, at `startCommand` treffer riktig kommando i stedet for
gunicorn, og at slettingen rammer de riktige radene — er dermed dekket av samme
observasjon.

Det er forskjellen S7 handlet om: en kontroll som står dokumentert er ikke det samme som
en kontroll som finner sted.

**`PERSONVERN_DOKUMENTASJON.md` v1.6.** Ny datert merknad under retensjonstabellen i A.9.
Ingen lagringstid er endret — det som er endret er grunnlaget for å påstå at de
etterleves.

**Sjekklistepunktet i C.4 er bevisst ikke krysset av.** TODO pekte på det, men C.4 er
malen for *årlig* revisjon. Krysses den av nå, står avkryssingen der i 2027 også og
påstår en verifisering som ikke er gjort det året. En datert merknad ved A.9, der
lagringstidene faktisk står, sier det samme uten å råtne.

**`kollaps_arkiv` er ikke verifisert på samme måte**, og skal ikke regnes som det. Den
har ennå ingenting å kollapse — arkivene er fra 2026, grensen er 24 måneder — så en
kjøring beviser foreløpig bare at kommandoen starter. Første skarpe kjøring er 1.
september, og `--dry-run` bør kjøres manuelt før den.

## 2026-08-22 — Portalen står i `production`, med cron. Dokumentasjonen i takt

Kun dokumentasjon og Railway-oppsett. **797 tester, alle grønne.** Ingen kodeendring.

**Portalen ble ikke flyttet.** Det opprinnelige `production`-miljøet — den gamle
Pasientregistreringsappen — er slettet, og portalens miljø døpt om fra `staging` til
`production`. Alternativet, å faktisk flytte portalen, ville betydd å migrere hele
produksjonsdatabasen mellom to Postgres-instanser: 273 pasienter, brukerkontoer,
MFA-hemmeligheter, auditspor og arkiver. Samme klasse operasjon som dataimporten, men uten
`--dry-run` som sikkerhetsnett — for å vinne et navn.

Miljøet har nå tre tjenester som alle bygger fra `Animax1/sanitetsportalen`:

| Tjeneste | Start Command | Plan |
|---|---|---|
| `web` | (Procfile) | — |
| `purge_old_logs` | `python manage.py purge_old_logs` | `0 0 * * SUN` |
| `kollaps_arkiv` | `python manage.py kollaps_arkiv` | `0 4 1 * *` |

**To feil i cron-oppsettet, begge stille:**

- **`startCommand` manglet på begge.** Uten den arver tjenesten `Procfile`-ens `web:`-linje
  og starter gunicorn i stedet for kommandoen. Jobben ville gjort ingenting, uten å feile —
  og med `restartPolicy: NEVER` bare stått til Railway rev den ned
- **`kollaps_arkiv` hadde `OFFLINE_MODE=True`.** `settings.py` kaster `ImproperlyConfigured`
  ved oppstart når den står på Railway, med vilje. Tjenesten ville krasjet før Django lastet,
  én gang i måneden, uten at noen merket det

Sperren mot `OFFLINE_MODE` ble skrevet for web-tjenesten, men fanget dette like godt.

Begge kommandoene tørrkjørt mot produksjonsdatabasen: `kollaps_arkiv` har ingenting å
kollapse (arkivene er fra 2026, grensen er 730 dager), `purge_old_logs` fant 3 varsler eldre
enn 30 dager.

**Verifiseringen er ikke ferdig, og det står som eget punkt.** En tørrkjøring beviser at
kommandoen kjører, ikke at cron utløser den. `purge_old_logs` fyrer førstkommende søndag og
skal slette varsel `id` 1, 2 og 3 fra 12. mai. Er de borte etterpå, er mekanismen bevist —
og **først da** kan sjekklistepunktet i `PERSONVERN_DOKUMENTASJON.md` linje 724 krysses av.
Å krysse av på grunnlag av en tørrkjøring ville vært nøyaktig den dokumenterte-men-ikke-reelle
kontrollen S7 handlet om.

**Dokumentasjonen sier nå at e-post går over HTTP-API, ikke SMTP.**
`BESLUTNING_BRUKERE_OG_EPOST.md` var bygget rundt SMTP fra ende til annen: den påsto at
`EMAIL_HOST` ikke var satt i produksjon, at all e-post havnet i Railway-loggen, og listet
fire SMTP-leverandører å velge mellom. Seksjon 1–3 er skrevet om — transporten er AHASends
HTTP-API v2, leverandørvalget er tatt, og kravet til en framtidig erstatter er at den har et
HTTP-API, ikke bare SMTP.

**Databehandleren er nå en forfalt mangel, ikke et framtidig valg.** Notatet behandlet
e-postleverandøren som noe som skulle avklares før invitasjonsflyten bygges. Men AHASend er
i bruk *allerede*, til feilvarsling, og er dermed databehandler i dag. Varselet inneholder
brukernavn, rolle, klient-IP, URL og traceback — ingen kliniske opplysninger, men
personopplysninger — og de går gjennom to tredjeparter: AHASend ved utsending og Google som
mottakerens innboks. Begge skal inn i A.2.

**Den gamle appens database er slettet.** Den manuelle backupen i portalen er eneste
gjenopprettingspunkt for de 273 importerte pasientene.

## 2026-08-22 — Dataimport fra gammel prod: 273 pasienter inn i portalen

Årets pasientdata er hentet fra den gamle Pasientregistreringsappen og ligger nå i
portalen. **797 tester, alle grønne** (1 ny).

**Resultatet, verifisert mot kilden felt for felt:**

| Kontroll | Portal | Gammel prod |
|---|---|---|
| Pasienter 2026 | 273 | 273 |
| Med førstehjelper | 216 | 216 |
| Med helsepersonell | 108 | 108 |
| Grønn / Gul / Rød | 163 / 91 / 19 | 163 / 91 / 19 |
| `journal=Ja` | 48 | 48 |
| `utskrevet` utfylt | 270 | 270 |
| `lege` utfylt | 29 | 29 |

Triage-fordelingen er den som betyr noe: statistikken er beregnet, ikke importert, så like
tall der betyr at grunnlaget faktisk er identisk. 273 `IMPORT`-rader i auditloggen, én per
pasient. `enja` og `morten` fantes allerede i førstehjelperregisteret og ble gjenbrukt, ikke
duplisert — registrene endte på 15 og 9.

### `import_offline_data` var ødelagt mot Postgres

Tørrkjøringen stoppet med `DataError: value too long for type character varying(10)`.
Kommandoen skrev `action='imported_offline'` til `AuditLog.action`, som er `max_length=10`.
Verdien er 16 tegn.

**Hele testsuiten var grønn.** Testene kjører på SQLite, som ikke håndhever varchar-lengde;
Postgres gjør det. `patients/tests_offline.py` filtrerte til og med på
`action='imported_offline'` og bekreftet dermed feilen som riktig oppførsel.

Verdien er nå `IMPORT` — seks tegn, som får plass i kolonnen som den er.

**Den står bevisst ikke i `AuditLog.ACTION_CHOICES`.** Å legge den til krever en migrasjon i
`audit`-appen, og `makemigrations` viser hvorfor det ikke er greit:

```
~ Rename index audit_audit_created_a3c1b8_idx on auditlog
                        to audit_audit_created_2c1626_idx
~ Alter field action on auditlog
```

Indeks-omdøpingen er den som tok ned produksjon i 30 minutter 13. august, og indeksen finnes
ikke i Postgres under det navnet. Enhver migrasjon i `audit` drar den med seg. Choices
håndheves ikke av databasen og `objects.create()` validerer ikke mot dem, så `IMPORT`
virker. Den kan normaliseres den dagen noen tar indeks-avviket bevisst — det er en egen jobb
med egne avveininger.

**Ny test, backend-uavhengig:** `test_import_offline_data_audit_action_passer_i_kolonnen`
leser `max_length` fra modellen og sammenligner med verdiene som faktisk skrives. Verifisert
ved å gjeninnføre feilen med vilje:

```
AssertionError: 16 not less than or equal to 10 : action='imported_offline'
er 16 tegn, men kolonnen tar 10. Dette feiler mot Postgres, ikke mot SQLite.
```

Det var hullet som lot feilen leve: en grense definert i modellen, håndhevet av én database
og ignorert av den andre.

### Fire feil i prosedyredokumentet

`docs/DATAIMPORT_FRA_GAMMEL_PROD.md` ble skrevet 14. august og hadde drevet:

- **`DATABASE_URL` når ikke fram utenfra.** Den peker på `postgres.railway.internal`, som
  kun er nåbar innenfra Railways nettverk. Begge miljøene har en `DATABASE_PUBLIC_URL` over
  TCP-proxy, men det sto ingen steder
- **`PYTHONUTF8=1` mangler.** Uten den skriver `dumpdata -o` fila i Windows' lokale kodesett,
  ikke UTF-8, og neste steg feiler med `UnicodeDecodeError ... byte 0xf8` — som er `ø`.
  Fanget på første forsøk; 468 norske tegn ville blitt ødelagt
- **Rådet om å øve mot staging er tomt.** Dokumentet ble skrevet da portalen sto i staging og
  produksjon var den gamle appen. Nå betjener staging-miljøet `portal.sanitet.net`.
  `--dry-run` er hele sikkerhetsnettet
- **`action`-verdien** var oppgitt som `imported_offline` to steder

### Verdt å vite for neste import

Den gamle appens `migrate` sår ti generiske `Behandler 1`–`Behandler 10`-rader, så
SQLite-fila får 25 behandlere der prod har 15. Ingen pasient peker på dem, og importen leser
gjennom en join — derfor kom kun de 14 faktisk brukte navnene med. Verdt å vite hvis noen
teller rader og lurer.

Importen matcher navn **case-sensitivt**, mens `0009_link_behandlere_to_users` matchet
`iexact`. Her var alt små bokstaver, men et avvik i store/små bokstaver ville gitt to rader
med pasientene fordelt mellom seg — uten feilmelding.

## 2026-08-22 — `verifiser_feilvarsel` sier hvor den kjører

**796 tester, alle grønne** (2 nye).

Tre ganger på én dag traff en variabel eller en test feil miljø: API-nøklene ble satt i
`production` (den gamle appen) i stedet for `staging` (portalen), to ganger, og
verifiseringen ble til slutt kjørt lokalt i PowerShell i stedet for i containeren — fordi
SSH-økta var avsluttet uten at det var synlig i utskriften.

Ingen av gangene var det uoppmerksomhet. Miljønavnene er arvet og inverterte, og
kommandoens utskrift så helt lik ut uansett hvor den kjørte. Et lokalt «grønt» og et
container-«grønt» betyr helt forskjellige ting: lokalt er utgående SMTP åpent, i containeren
er det sperret.

Kommandoen begynner nå med å si hvor den er:

```
Kjorer i Railway: miljo "staging", tjeneste "web", vert 57329c3660a9
   Svaret under gjelder dette miljoet. Merk at miljonavnene er arvet:
   portalen kjorer i "staging", mens "production" er den gamle appen.
```

Kjørt lokalt sier den i stedet, med advarselsfarge, at svaret **ikke** gjelder produksjon,
og hvordan man kjører den riktig. Testene krever begge deler — inkludert at
container-varianten nevner inverteringen, siden en utskrift som bare sier «staging» like
gjerne kan feilleses som «ikke produksjon».

## 2026-08-22 — Railway sperrer SMTP: e-post går nå over HTTPS

**794 tester, alle grønne** (21 nye).

Feilvarslingen så ferdig ut, men virket ikke i produksjon. Den ble testet med
`railway run`, som henter Railways miljøvariabler og kjører koden **på utviklingsmaskinen**.
Først da kommandoen ble kjørt inne i containeren, via `railway ssh`, kom sannheten fram:
den hang i `sock.connect()`.

**Målt fra containeren:**

| Port | |
|---|---|
| 587, 2525, 465, 25 | **alle stengt** |
| 443 mot `send.ahasend.com` | åpen |
| 443 mot `1.1.1.1` (kontroll) | åpen |

Utgående trafikk virker. Railway sperrer SMTP spesifikt — en vanlig plattformpolicy mot
spam-misbruk. **Å bytte SMTP-leverandør ville truffet samme vegg.**

**`core/mail_backends.py`** sender derfor over AHASends HTTP-API i stedet:
`POST https://api.ahasend.com/v2/accounts/{konto}/messages`. Backenden bytter kun
*transporten* — `mail_admins()`, `AdminEmailHandler`, `send_mail()` og den slanke
feilrapporten fungerer uendret.

Valg som er tatt bevisst:

- **`urllib` fra standardbiblioteket, ikke `requests`.** Én HTTP-POST rettferdiggjør ikke en
  ny avhengighet, og dette er stien som skal virke når alt annet feiler
- **`fail_silently` respekteres strengt** — `AdminEmailHandler` kaller alltid slik. Men
  feilen logges alltid: en stille feil uten loggspor er umulig å feilsøke
- **`Idempotency-Key` per melding**, siden dempingsfilteret er per prosess og to
  Gunicorn-arbeidere kan sende samme varsel
- **Ikke støttet:** vedlegg, egendefinerte headere, `cc`/`bcc` som egne felter. Portalen
  sender kun til `ADMINS`. Et bevisst utvidelsespunkt, ikke en glemt detalj

Backend velges etter hva som er konfigurert: HTTP-API-et først fordi det er det eneste som
kommer ut av containeren, så SMTP (som virker lokalt og i offline-modus), så konsoll.

### `EMAIL_TIMEOUT` — den viktigste enkeltendringen

Hendelsen avslørte noe verre enn manglende tilkobling. `EMAIL_TIMEOUT` var ikke satt, og
Djangos standard er `None`. Da arver `smtplib` Pythons globale socket-timeout, som også er
`None`. Tracebacken fra containeren viste det presist:

```
smtplib.py:320   socket.create_connection((host, port), timeout, ...)
socket.py:853    sock.connect(sa)      <- sto her til Ctrl+C
```

`AdminEmailHandler` sender **synkront, i requestens egen tråd**. Gunicorn kjører med fire
tråder per worker. Fire uhåndterte feil mens SMTP henger, og hele worker-poolen er låst —
appen slutter å svare for alle, også de som ikke opplevde noen feil. En feil som skulle gitt
én e-post ville i stedet tatt ned portalen, og det ville skjedd under vakt.

`EMAIL_TIMEOUT = 10` er nå satt, og en test krever at den er ≤ 30. Dempingsfilteret
begrenser skaden ytterligere, men det er tidsgrensen som gjør varslingen ufarlig for driften.

### `verifiser_feilvarsel` ga nesten falsk grønt

Steg 2 åpnet en SMTP-forbindelse. For HTTP-backenden er `open()` en arvet no-op fra
`BaseEmailBackend` — kommandoen ville meldt «Åpnet og autentisert» uten å ha kontaktet noe.
Falsk grønt på nøyaktig det spørsmålet kommandoen finnes for å svare på.

Steg 2 prøver nå den transporten som faktisk er i bruk: SMTP-forbindelse for SMTP, en ekte
sendt melding for HTTP-API-et — det eneste som prøver DNS, TLS, autentisering og om
avsenderdomenet er godkjent. Backender uten transport (konsoll, locmem) hopper over steget
og sier fra at de gjør det, i stedet for å rapportere suksess.

Kommandoen har også fått `--timeout` (standard 15 s) og en feilmelding som skiller
**droppet** fra **avvist** — det er den forskjellen som leder deg mot brannmur i stedet for
at du bruker en time på å sjekke passordet. En test krever at `EMAIL_HOST_PASSWORD` ikke
nevnes i tidsavbrudds-meldingen.

## 2026-08-22 — Feilvarselet slanket: 14 810 → 673 tegn

**769 tester, alle grønne** (14 nye).

Spørsmålet som utløste dette: *er det nødvendig å sende settings?* Nei. Django gjenbruker
feilsidens mal (`technical_500.txt`) til varslings-e-posten, og den malen er skrevet for en
utvikler med DEBUG på som trenger å se alt. Den dumper hele `Settings:`-tabellen og hele
`META:`-tabellen. I en e-post er det rundt 13 av 14 KB støy — og et ganske detaljert bilde
av systemet som forlot serveren hver gang noe kræsjet.

`core/error_reporting.py` erstatter den med det varselet faktisk trenger: hva som skjedde,
hvor, hvem det traff, og når. Målt på samme feil: **14 810 → 673 tegn, altså 4 %.**

**Fravalgene er sikkerhetsegenskapen**, og testene vokter dem — innhold er lett å se at
stemmer, mens en gjeninnført Settings-dump ville gått upåaktet hen:

| Utelatt | Hvorfor |
|---|---|
| `Settings:` | Hemmelighetene var maskert, men resten er en konfigurasjonsoversikt varselet ikke trenger |
| `META:` | Hele WSGI-miljøet. Vi plukker ut IP, nettleser og referer |
| `GET`/`POST`/`COOKIES` | **Det viktigste.** En POST mot pasient-API-et har kliniske opplysninger i kroppen |
| Lokale variabler | Var aldri med i tekstmalen, og legges ikke til. En stackramme i en pasientvisning har pasientdata i minnet |

Rapportøren settes via `reporter_class` på selve handleren, ikke via
`DEFAULT_EXCEPTION_REPORTER`. Feilsiden i DEBUG beholder dermed full detalj — det er kun
e-posten som slankes. Ved enhver feil i rapportøren selv faller den tilbake til Djangos
egen: en loggehandler som kaster, tar med seg varslingen den skulle levere.

**`include_html=False` har fått en kommentar som sier hvorfor den står der.** Det er ikke
en formateringssak: `technical_500.html` tar med lokale variabler for hver stackramme.
Skal den noen gang settes til `True`, må personvernkonsekvensen vurderes på nytt først.

**Verifisert med ekte produksjonsverdier** at ingenting lekker: `SECRET_KEY`,
`EMAIL_HOST_PASSWORD`, databasepassord, databasevert, POST-data og sesjonscookie er alle
fraværende i rapporten. Djangos egen maskering (`API|AUTH|TOKEN|KEY|SECRET|PASS|SIGNATURE|HTTP_COOKIE`)
dekket hemmelighetene allerede, men databaseverten slapp gjennom fordi `DATABASES` og
`HOST` ikke matcher mønsteret. Nå er hele seksjonen borte, så spørsmålet er uaktuelt.

**Et hull notert i TODO:** personverndokumentasjonen omtaler ikke e-postvarsling i det hele
tatt. Det er en dataflyt til to tredjeparter — AHASend og Google — som hører hjemme i A.2.
Varselet inneholder brukernavn, rolle, klient-IP, URL og traceback; ingen kliniske
opplysninger.

## 2026-08-22 — E-postvarsling verifisert, og en kommando som gjør det etterprøvbart

**755 tester, alle grønne** (5 nye).

E-postvarslingen ved uhåndterte feil (F1) har stått ferdig i koden siden 13. august, men
aldri vært bekreftet mot en faktisk SMTP-tjener. Nå er den det: AHASend via
`send.ahasend.com:587`, med `noreply@mail.sanitet.net` som avsender.

**`python manage.py verifiser_feilvarsel`** er lagt til fordi denne stien er stille når
den er ødelagt. Djangos `AdminEmailHandler` kaller `mail_admins(..., fail_silently=True)`,
og en loggehandler som feiler river aldri ned requesten som utløste den. Det er riktig
oppførsel — men konsekvensen er at feil SMTP-oppsett ser nøyaktig ut som et system uten
feil. Tom `ADMINS` er verre: da har varselet null mottakere, og ingenting protesterer.

Kommandoen skiller de tre tingene som kan svikte, og sier hvilken det er:

1. **Oppsettet** — backend, mottakere, avsender. Tom `ADMINS` gir `CommandError`, ikke et
   grønt svar på et spørsmål ingen stilte
2. **SMTP-forbindelsen** — åpnes eksplisitt med `fail_silently=False`, så feil legitimasjon
   eller avvist avsenderadresse gir et unntak i stedet for stillhet
3. **Varslingskjeden** — en ekte exception logges til `django.request` med `exc_info` og et
   syntetisk request-objekt, altså slik Django selv gjør det ved en uhåndtert feil. Den går
   gjennom dempingsfilteret og `AdminEmailHandler`

Steg 2 er det som roper. Steg 3 beviser at kjeden er koblet, men kan ikke rapportere
leveranse — handleren svelger sine egne feil. Derfor kjøres begge: steg 2 utelukker at
steg 3 feilet stille. `--dry-run` kontrollerer oppsettet uten å sende.

Verifisert mot Railway-variablene: SMTP åpnet og autentisert, og
`django.request` har `['StreamHandler', 'AdminEmailHandler']`.

`audit/tests_verifiser_feilvarsel.py` vokter at kommandoen selv ikke er stille når noe er
galt — en verifiseringskommando som feiler stille er verre enn ingen kommando. Fila heter
`verifiser_feilvarsel.py`, ikke `test_*`, nettopp for at testoppdageren ikke skal plukke
opp en management-kommando som testmodul.

**Et lokalt funn underveis, uten betydning for drift:** første forsøk feilet med
`CERTIFICATE_VERIFY_FAILED: certificate has expired`. Sertifikatet til AHASend er gyldig
(Let's Encrypt, 1. aug → 30. okt 2026, `openssl` verifiserer kjeden med kode 0). Det er
Windows-sertifikatlageret på utviklingsmaskinen som har et utløpt sertifikat i
Let's Encrypt-stien — `letsencrypt.org` feiler også, mens `pypi.org` går fint.
Railway-containeren har sin egen, oppdaterte `ca-certificates` og er ikke berørt.

## 2026-08-22 — `docs/` konsolidert: TODO er arbeidslista, tre dokumenter slettet

Kun dokumentasjon. **750 tester, alle grønne.** Ingen brutte relative lenker i repoet.

`docs/` er nede fra ti aktive dokumenter til åtte — tre slettet, ett nytt.
`FORBEDRINGER_2026-08.md` (1836 linjer),
`GDPR_TILTAKSPLAN.md` (260) og `docs/README.md` (56) er slettet. Alt som fortsatt er åpent
står nå i `TODO.md`, med begrunnelsen med seg — ikke som peker til et dokument.

**Hvorfor sletting og ikke arkivering.** Backlog-dokumentet var 23 av 28 punkter ferdige.
De 23 er allerede fortalt i denne fila under 13.–22. august, med mer detalj enn matrisen
hadde. Å beholde dokumentet ville gitt to steder å lese status fra, og de ville drevet fra
hverandre. GDPR-tiltaksplanen sa det samme om seg selv i toppteksten: «Når alle faser er
ferdige, har dokumentet gjort jobben sin og kan slettes.» Den hadde ett åpent punkt igjen.
`docs/README.md` var en indeks som kun fantes fordi det var mange filer.

**Statistikk-utvidelsen (F6) ble reddet ut, ikke komprimert.** 96 linjer med tilgangsmodell,
faseinndeling, statistiske metoder (Dunn post-hoc, Wilson-KI, Cramér's V) og fem ubesvarte
spørsmål lar seg ikke koke ned til en kulepunkt-linje uten at det som gjør den brukbar
forsvinner. Den ligger nå som `docs/BESLUTNING_STATISTIKK.md`, etter samme mønster som de
to andre beslutningsnotatene. Den er en plan som venter på avgjørelser, ikke et punkt på
en liste — samme skille som avgjorde at runbook, deploy-guide og dataimport beholdes.

**F8 (PgBouncer) står ikke lenger som oppgave.** Den var markert «bevisst utsatt», ikke
åpen. Begrunnelsen — 16 forbindelser mot en grense på ~100, og `conn_max_age=600` som
demper ytterligere — er beholdt i TODO som en note om *hvorfor det ikke er en oppgave*, med
terskelen for å ta den opp igjen (`WEB_WORKERS` ≥ 4).

**En løs tråd ble funnet under flyttingen:** F7 er merket ferdig, men første-paint på mobil
4G ble aldri målt. `read_only` laster 49 % av admin-bundlen, og gevinsten i faktisk
oppstartstid er udokumentert. Den står nå som eget punkt i stedet for som en parentes under
et avkrysset punkt.

**Migrasjonssekvensen skrevet ned.** Railway-prosjektet har to miljøer, og navnene er
arvet fra forgjengeren: `production` er den *gamle* Pasientregistreringsappen
(`pasientregistrering.up.railway.app`), mens `staging` er Sanitetsportalen — det er den
som betjener `portal.sanitet.net`. Portalen skal over på `production` når dataimporten er
kjørt, og `purge_old_logs`- og `kollaps_arkiv`-jobbene kobles på der. Rekkefølgen står nå
i TODO fordi den ikke kan tas i vilkårlig orden: `production` må stå urørt til importen er
ferdig, siden det er der årets pasientdata ligger.

Konsekvensen i mellomtiden er notert samme sted: portalens miljø har ingen cron-tjeneste,
så verken audit-logger, innloggingshendelser eller varsler slettes ennå.
`PERSONVERN_DOKUMENTASJON.md` A.9 oppgir 730/30 dager med «`purge_old_logs` via Railway
Cron» som mekanisme — den påstanden blir sann etter migrasjonen, ikke før, og
sjekklistepunktet i samme dokument kan krysses av da. Backloggens F2 ble avkrysset som
«allerede på plass»; det stemte for den gamle appen, ikke for portalen.

**Ni referanser til de slettede filene rettet** i `accounts/tests_user_admin.py`,
`patients/js_test_utils.py`, `PERSONVERN_DOKUMENTASJON.md`, `RUNBOOK_VAKT.md`,
`TEKNISK_DOKUMENTASJON.md` og de to arkivindeksene. To av dem avslørte utdaterte påstander:
den tekniske dokumentasjonen omtalte arkiv-kollaps som «planlagt endring» selv om GDPR
fase 3.1 leverte den i august, og personverndokumentasjonen pekte på et dokument som ikke
lenger fantes for et avvik som fortsatt er reelt.

**`.env.example` pekte på SendGrid** og `sanitetsportalen@dittdomene.no`. Prod bruker
AHASend med `mail.sanitet.net` som avsenderdomene. Kommentaren forklarer nå hvorfor
`DEFAULT_FROM_EMAIL` må ligge på et autorisert domene: gjør den ikke det, avvises
feilvarselet ved innsending, og da får man aldri vite at noe kræsjet.

### Kontrollert og funnet i orden (fra gjennomgangen i august)

Bevart her fordi det er verdt å slippe å revidere på nytt neste gang:

- **Endepunktdekning.** Alle views i `patients`, `core`, `accounts` og `admin_status` har
  `@login_required` eller en rolledekoratør. Ingen ubeskyttede endepunkter funnet. Den
  eneste `@csrf_exempt` er `/healthz/`, som er `@require_safe` og ikke rører data.
- **Path traversal via backup-filnavn er lukket.** `backup_admin_download_view` og
  `backup_admin_delete_view` bygger stier fra `Backup.filename`, men modellen er eksplisitt
  ekskludert fra sin egen dump (`patients/backup.py:31`), så en restore kan ikke injisere
  rader med `../` i filnavnet. Filnavn genereres kun av `_build_filename()`.
- **Django admin-endringer på pasienter blir audit-logget.** Signalet er
  entry-point-agnostisk.
- **Offline-modus** (`ALLOWED_HOSTS=['*']`, CSRF-wildcards for private subnett) er et
  bevisst dokumentert valg, med hard sperre mot at `OFFLINE_MODE` aktiveres på Railway
  (`settings.py:58–62`).
- **MFA trust-cookien invalideres korrekt** når admin nullstiller MFA: `_check_mfa_trust`
  slår opp TOTP-enheten, og `reset_mfa` sletter den.
- **`SECRET_KEY`** hard-feiler ved oppstart når `DEBUG=False`, både på tom verdi og på de
  kjente eksempelverdiene.

## 2026-08-22 — Dokumentstrukturen strammet: TODO som arbeidsliste, docs som referanse

Kun dokumentasjon. **750 tester, alle grønne** — ingen kodeendring.

**Skillelinjen er skjerpet.** Den forrige oppryddingen delte `docs/` i «levende» og
«aktive planer». Det holdt ikke som kriterium — det sa noe om alder, ikke om funksjon. Den
nye regelen er: *en prosedyre du utfører beholdes som fil, en arbeidsliste foldes inn i
`TODO.md`.* Runbooken leses under vakt, deploy-guiden følges steg for steg, dataimporten
kjøres én gang med tre forbehold om datakvalitet — ingen av dem tåler å ligge spredt i en
liste man scroller i. Backlog-dokumenter gjør det motsatte: de duplisere TODO og drifter.

**To arkiverte filer slettet i stedet.** `DEPLOY_FASE_3A.md` beskrev hvordan man pakket en
zip oppå en frisk clone — indeksen sa selv at den etterlot seg «ingenting» i koden.
`ENDRINGSLOGG_2026-05-15.md` var et endringsnotat fra før CHANGELOG fantes, og innholdet
står her under `2026-05-15 (sesjon 1)`. Begge fikk en indekslinje som forklarte at de var
tomme; nå er de borte i stedet. Poenget med å arkivere er å bevare *begrunnelser* — et
dokument uten begrunnelse å bevare skal slettes. Historikken ligger i git.

**Dokumentgjennomgang lagt inn i TODO**, med funnene ferdig kartlagt så jobben er avgrenset
når den skal gjøres. Den tas når funksjonaliteten vi bygger nå er på plass, ikke før:

- `TEKNISK_DOKUMENTASJON.md` er merket «April 2026» og har ikke fulgt med på fire måneders
  refaktorering — `views.py` delt i fem, `core/backup/`, `core/arkiv/` og modulregistryet
  mangler. Alternativet til å oppdatere den er å merke den ærlig som et øyeblikksbilde
- `RUNBOOK_VAKT.md` og `DEPLOY_GUIDE.md` har `<din-app>.railway.app` seks steder til sammen
- `PERSONVERN_DOKUMENTASJON.md` er en annen øvelse: den er art. 30-protokollen og skal
  verifiseres mot koden, ikke slankes. AHASend er en ny databehandler som skal inn

**`OPPSETT_KOLLAPS_CRON.md` er Andres.** Den beskriver en oppgave bare han kan utføre, og
han sletter den selv når jobben står i Railway. Merket i både TODO og `docs/README.md` slik
at en senere opprydding ikke rydder den bort.

**Rettelser:** den arkiverte `FORBEDRINGER.md` ba fortsatt om å bli oppdatert når et punkt
ble ferdig — stikk i strid med at arkivet ikke skal endres. `README.md` oppga Django 5.1
der `requirements.txt` krever `>=5.2.1`. Crawler-seksjonen under var datert 15. august og
skrevet den 22.

## 2026-08-22 — Crawler-sperre: robots.txt og X-Robots-Tag

Portalen får eget domene (`portal.sanitet.net`), og skal ikke kunne finnes via
søk eller havne i et treningsdatasett. **750 tester, alle grønne** (8 nye).

**Utgangspunktet er bedre enn antatt.** En gjennomgang av hele URL-treet uten
innlogging viser at kun to endepunkter svarer 200: `/accounts/login/` og
`/healthz/`. Alt annet — dashboard, pasient-API, statistikk, admin — redirecter
til innlogging. En crawler kan altså aldri nå pasientdata, uavhengig av
tiltakene under. Det som faktisk sto på spill var at innloggingssiden kunne bli
indeksert, ikke at data kunne høstes.

**`core/robots.py`** serverer `/robots.txt` med `Disallow: /` for alle, pluss 22
navngitte AI-crawlere (GPTBot, ClaudeBot, CCBot, Google-Extended, PerplexityBot,
Bytespider m.fl.). Botene navngis eksplisitt fordi flere av dem kun leser regler
adressert til sitt eget agent-navn, og dermed går rett forbi `User-agent: *`.
Endepunktet er bevisst uten auth — en regel ingen får lese, virker ikke.

**`X-Robots-Tag: noindex, nofollow, noarchive, nosnippet, noimageindex`** settes
nå i `SecurityHeadersMiddleware` på *alle* responser, ikke bare de to offentlige
sidene. Grunnen er at et endepunkt som en gang gjøres åpent ellers ville blitt
indekserbart uten at noen la merke til det.

De to mekanismene løser ulike problemer og trengs begge: robots.txt ber
crawleren la være å *hente* siden, headeren ber om at den ikke *vises*. Det
siste dekker også sider som havner i indeksen via en ekstern lenke. Rekkefølgen
mellom dem har en felle som er dokumentert i `core/robots.py`: en URL blokkert i
robots.txt kan ikke leses, så headeren ses aldri — skal noe allerede indeksert
*ut*, må det midlertidig tillates i robots.txt. Ikke et problem for et nytt
domene, men verdt å vite før noen feilsøker det senere.

`core/tests_robots.py` vokter begge: at robots.txt er offentlig og `text/plain`,
at hver `User-agent`-linje faktisk følges av `Disallow: /` (en User-agent uten
Disallow under seg blokkerer ingenting), at alle navngitte boter er med, og at
headeren står på både offentlige og innloggede sider.

**Grensen for hva dette er verdt:** robots.txt er frivillig, og headeren
respekteres kun av crawlere som velger å respektere den. Mot en scraper som
ignorerer begge, er innloggingskravet den eneste reelle beskyttelsen — og det er
også det som faktisk beskytter pasientdataene.

## 2026-08-15 — Dokumentasjonsopprydding: `docs/archived/`, og TODO som eneste arbeidsliste

Kun dokumentasjon. Ingen kodeendring. Suiten kjørt for sikkerhets skyld: **742 tester, alle
grønne.**

Planleggingen hadde spredt seg over ti dokumenter i `docs/`, uten at det gikk an å se hvilke
som fortsatt gjaldt. Ti av dem beskrev arbeid som var ferdig for flere måneder siden, og et
par av de aktive hadde avkryssinger som ikke stemte med koden lenger. Ingenting er slettet.

**Ny mappe `docs/archived/`** — ti dokumenter flyttet dit med `git mv`, historikken intakt:

| Fil | Hvorfor |
|---|---|
| `SANITETSPORTAL_PLAN.md` | Høynivå-skisse v0.1 fra 6. mai. Alle fem faser er levert |
| `SANITETSPORTAL_FASE_1..5.md` (6 filer) | Leveransenotater for faser som er i prod |
| `DEPLOY_FASE_3A.md` | Engangsprosedyre for å pakke en zip oppå en frisk clone |
| `ENDRINGSLOGG_2026-05-15.md` | Duplikat — innholdet står ordrett i CHANGELOG under `2026-05-15 (sesjon 1)` |
| `FORBEDRINGER.md` | Erklærte seg selv som historisk arkiv allerede i toppteksten |

De ni resterende dokumentene i `docs/` er beholdt uendret i innhold. `docs/README.md` skiller
dem i **levende dokumenter** (teknisk, personvern, runbook, deploy — skal holdes oppdatert)
og **aktive planer** (har et sluttpunkt, arkiveres eller slettes når jobben er gjort), med
en tabell over hvor ny dokumentasjon hører hjemme. `docs/archived/README.md` forklarer hva
hver arkiverte fil etterlot seg i koden, og advarer om de to tingene som går igjen der:
`patients/views.py` finnes ikke lenger, og `Behandler` heter `Forstehjelper`.

**`TODO.md` er nå eneste arbeidsliste.** Ny topptekst med kart over hvor ting hører hjemme.
Fem punkter fra forbedringsbacklogen sto åpne uten å være løftet hit — **S3** (rate-limiting
kun på innlogging), **F3** (server-side idempotency), **F4** (lasttest), **F6**
(statistikk-utvidelse) og **F9** (kolonne-kryptering, nedprioritert) — de står nå i TODO med
begrunnelse. Det samme gjelder DPIA-vurderingen fra GDPR fase 5.

De løse punktene nederst er gruppert i «Framtidige moduler» og «Løse punkter». De tre
ubesvarte spørsmålene fra §7 i den arkiverte skissen er tatt vare på under framtidige
moduler — de må avklares før modul nummer to skrives. Med en merknad om at skissens
modulliste (`vakter`/`utstyr`/`rapport`/`beredskap`) er utdatert, mens arkitekturvalgene
står seg. «Fjerne varsler eldre enn 30 dager» var oppført som åpent, men ble gjort som GDPR
fase 2.3 — krysset av.

**Rettelser i aktive dokumenter:**

- `GDPR_TILTAKSPLAN.md`: fase 1 og 2 var merket ✅ FERDIG i overskriften mens samtlige
  underpunkter sto uavkrysset. Avkryssingene stemmer nå med koden. Ny statustabell øverst
  viser de tre punktene som faktisk gjenstår. Fire døde lenker til `patients/views.py`
  (delt i fem moduler ved N13.3) er avlenket — linjenumrene beholdt som historisk kontekst,
  med en merknad om hvorfor
- `FORBEDRINGER_2026-08.md`: vedlikeholdsnotisen ba om at ferdige punkter flyttes til
  `FORBEDRINGER.md`, som nå er arkivert og ikke skal endres. Rutinen er skrevet om.
  F6 viser til to statistikkdokumenter som aldri har ligget i dette repoet — de er fra den
  gamle Pasientregistreringsappen, og det står nå i seksjonen
- `README.md` pekte på `../SANITETSPORTAL_FASE_3A.md`, en sti som aldri traff noe fra
  rotmappa. Rettet til den arkiverte plasseringen
- `accounts/migrations/0007_module_permission_flags.py`: docstringen viser til
  `SANITETSPORTAL_PLAN.md` — stien er oppdatert. Eneste endring utenfor dokumentasjon,
  og den er en kommentar

Alle relative markdown-lenker i repoet er verifisert til å peke på noe som finnes.

## 2026-08-14 — Beslutningsnotater: brukere/e-post og dataimport fra gammel prod

Kun dokumentasjon. Ingen kodeendring.

**`docs/BESLUTNING_BRUKERE_OG_EPOST.md`** — hvordan e-post fungerer i dag (kort: den gjør
det ikke, `EMAIL_HOST` er ikke satt så alt går til Railway-loggen), hva som kreves for at
SMTP skal virke inkludert SPF/DKIM, tre konkrete leverandøralternativer med
miljøvariabler, og de sju beslutningene rundt passord-reset.

Besluttet: invitasjon med signert lenke som registreringsvei, ikke invitasjonskode — koden
er den eneste av alternativene som kan misbrukes, og bulk-onboarding er ikke vist å være et
reelt problem ennå.

To modellendringer spesifisert men ikke kjørt: `fullt_navn` (ett fritekstfelt, ikke
for-/etternavn) og `er_delt_konto` for bil-innlogginger. `CustomUser` arver
`AbstractBaseUser`, så `first_name`/`last_name` finnes ikke i dag.

To ting notatet fremhever som ellers oppdages sent: en e-postleverandør blir
**databehandler** og må inn i personvernprotokollen med avtale, og
**leveringsevne avgjør om funksjonen er brukbar** — en reset-lenke i spam midt i en vakt
betyr at brukeren ringer admin likevel, men nå i tro på at selvbetjening finnes.

**`docs/DATAIMPORT_FRA_GAMMEL_PROD.md`** — årets pasientdata skal fra den gamle
Pasientregistreringsappen inn i portalen.

Funnet ved gjennomgang av `C:\Programmering\pasientregistrering`: **verktøyet finnes
allerede.** `import_offline_data` leser nøyaktig det gamle skjemaet — kolonne for kolonne,
inkludert `behandler_id` og `journal` — fordi kommandoen ble skrevet for
offline-SQLite-filer, og de filene *er* den gamle appen. Ingen ny kode trengs.

Prosedyren er tre standardoperasjoner: `dumpdata` fra prod (read-only), bygg en lokal
SQLite med gammelt skjema, importer med `--dry-run` først.

Tre forbehold dokumentert: `created_at` blir importdatoen (statistikken påvirkes ikke, den
regner på tekstfeltene), det gamle `helsepersonell`-tekstfeltet importeres ikke siden
portalen fjernet det i migrasjon 0010, og whitelisten kan avvise verdier fra før
`choices.py` ble innført.

**Arkiverte vakter importeres ikke, og bør ikke.** SHA-256-signaturen er beregnet over
`arkiv_id`, altså primærnøkkelen — får arkivet ny pk i portalen, melder det tukling. Å
skrive om signaturen for å passe ville undergravd hele poenget. Anbefalingen er å importere
pasientradene og arkivere vakten på nytt fra portalen.

**Rollemodellen er lagt inn som eget TODO-punkt.** Dagens ene globale `role` pluss fem
`kan_redigere_*`-flagg holder ikke med fire moduler til. Flaggene er dessuten feilnavngitt
— `help_text` sier de styrer synlighet i nav-menyen, ikke redigering.

---

## 2026-08-13 — Arkivmønsteret generalisert til `core/arkiv/`

Forberedelse til park-, oppdrags- og rapportmodulen. Frysing, integritetssjekk og kollaps
lå i `patients/services.py` og måtte ellers kopieres tre ganger.

`core/arkiv/` følger samme idiom som `core/backup/`: `BaseArkivHandler` med registry,
registrert fra `apps.ready()`. Core eier kanonisering (`sort_keys=True`,
`ensure_ascii=False`), hashing, valg av signatur ut fra kollaps-tilstand, og
orkestreringen av kollaps. Handleren eier *hva* som går inn i payloaden.

**Den arbeidsdelingen er hele poenget.** SHA-256-signaturen ligger lagret på hvert
`VaktArkiv` i produksjon, og payloadens form er del av den — nøkkelen `'pasienter'`,
sorteringen på `pasientnummer`, feltutvalget. Hadde core bestemt formen, ville samtlige
eksisterende arkiver meldt tukling ved neste visning. `patients/arkiv.py` bygger derfor
payloaden ordrett som før.

**Rekkefølgen var viktig:** signaturene ble først låst til to literale hex-verdier
(`ArkivSignaturLaastTests`), *før* koden ble flyttet. En test som regner ut fasit på nytt
ville ikke fanget dette, siden begge sider endret seg samtidig. Testene passerte etter
flyttingen, altså er hashene bit-identiske.

Nytt i det generiske laget, som pasientmodulen ikke hadde eksplisitt:

- `verifiser()` returnerer `False` for arkiver uten lagret signatur. Det gjelder arkiver
  fra før signaturen ble innført, og å melde tukling på dem ville vært misvisende.
- `har_backup_etter()` returnerer `False` når handleren mangler `backup_slug` — ingen
  sperre betyr at kollaps må tvinges bevisst, ikke at den er fri.
- Aggregatet beregnes *før* transaksjonen åpnes, slik at en feilende beregning ikke
  etterlater slettede rader. Egen test verifiserer rekkefølgen ved å sjekke at aggregatet
  inneholder radantallet fra før slettingen.

19 nye tester i `core/tests_arkiv.py`, med en dummy-handler slik at det generiske laget
dekkes uavhengig av pasientmodulen.

**Ingen migrasjon, ingen modellendring.** `makemigrations --check` rapporterer fortsatt
indeks-omdøpingen i `audit` — det er det kjente avviket som tok prod ned 13. august, og
det skal stå i fred. Det har ingen sammenheng med denne endringen.

**Nesten-ulykke verdt å notere:** `.gitignore` hadde `arkiv/` uten anker. Mønsteret
matcher på alle nivåer, så hele `core/arkiv/`-pakken var usynlig for git. Ble den pushet
slik, ville `patients/apps.py` importert en modul som ikke fantes i repoet — `ready()`
kaster ved oppstart, containeren crash-looper, 502. Samme feilmodus som
migrasjonshendelsen samme dag, med en helt annen årsak.

Linja er endret til `/arkiv/`, som fortsatt dekker den tomme filmappa i rota (rest etter
GDPR fase 2.4). De øvrige uankrede mønstrene er gjennomgått: bare `__pycache__/`, som
skal være uankret, og `vendor/` inne i den allerede ignorerte `staticfiles/`.

Lærdommen er at `git status` må sjekkes for nye *pakker*, ikke bare nye filer. En fil som
mangler gir en importfeil i test; en hel pakke som mangler gir grønne tester lokalt, fordi
fila ligger på disk.

**Utsatt med vilje:** `AbstractArkiv`-basemodell for felt (`sha256`, `kollapset_at`,
`aggregat`, frosset `importert_av_navn`). Den bør skrives når modell nummer to faktisk
finnes, ikke gjettes fram nå — og `VaktArkiv` skal ikke migreres til den.

757 tester grønne.

---

## 2026-08-13 — Ytelse: pasientlista tåler 1000 pasienter og 100 brukere

Foranlediget av en skaleringsgjennomgang: portalen skal ta 10–20 brukere døgnkontinuerlig
med peak rundt 100, og rundt 1000 pasienter per arrangement.

**N+1 på det mest pollede endepunktet.** `_patient_to_dict()` leser navnet på både
førstehjelper og helsepersonell, men `patients_list_view` hadde ikke `select_related`.
Målt på 1000 pasienter (250 med full data fra samleplass, 750 enklere fra park):

| | Før | Etter |
|---|---|---|
| Spørringer per kall | **515** | **15** |
| Ved 25 pollende lesere | ~430/sek | ~12/sek |

Konstant, ikke lineært med radantallet. `PasientlisteYtelseTests` sammenligner
spørringsantallet ved 5 og 60 pasienter i stedet for å låse et absolutt tall — da tåler
testen at annen middleware endrer grunnkostnaden, men fanger fortsatt at kostnaden
begynner å følge radantallet. Verifisert ved å fjerne `select_related` midlertidig.

**ETag på `/api/patients/`.** Svaret er 454 kB ved 1000 pasienter, hentet av hver klient
hvert 30. sekund. Nå returneres 304 uten kropp når ingenting er endret. Kroppen
serialiseres én gang og hashes, i stedet for å hashe feltverdier separat — da kan ETag-en
per definisjon ikke komme i utakt med det som sendes, og den varierer riktig med
`?filter`, `?mine` og `?include_archived` uten at de må håndteres eksplisitt.

Merk hva det sparer: båndbredden, ikke databasearbeidet. Spørringen og serialiseringen
kjører uansett for å regne ut hashen.

**To feller underveis:**

`setFilter()` stoler på at `loadPatients()` kaller `applyFilter()`. En rå tidlig retur på
304 ville latt griden stå med forrige filter når «Mine pasienter» slås av — knappen ville
byttet utseende, men innholdet ikke. 304-grenen kjører derfor `applyFilter()` før den
returnerer.

`renderBoard()` hentet hele lista på nytt ved hver auto-refresh, i tillegg til
`loadPatients()`. Tavlefanen doblet altså trafikken. Den har nå sin egen ETag — den
henter en annen URL (alltid ufiltrert), så den kan ikke dele etag med lista.

**Bakgrunn som ikke ble til kode:** F8 (PgBouncer) er avklart som ikke aktuell. Ved 4
workers × 4 threads bruker appen 16 forbindelser mot grensen på 100, og flaskehalsen var
spørringer og båndbredde — ikke forbindelser. Railways edge-grenser (10 000 samtidige
forbindelser, 11 000 req/s) er heller ikke i nærheten. Målte tall og
`pg_stat_activity`-spørringen er lagt inn i `docs/RUNBOOK_VAKT.md` §3c, siden §2-tersklene
sier hva man skal gjøre når P95 stiger, men ikke hva som ryker først.

735 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — F5, trinn 2: `unsafe-inline` fjernet fra script-src

Trinn 1 er verifisert manuelt i prod — filterknapper, registreringsskjema med
tidsstempler, bekreftelsesdialoger i brukeradministrasjonen og arkivet. Da kunne headeren
flippes.

Hver request får nå et nonce fra `secrets.token_urlsafe(16)`, satt på `request.csp_nonce`
i `SecurityHeadersMiddleware` *før* viewet kjører, og lest i templates via en ny
context-prosessor. `script-src` er
`'self' 'nonce-…' https://cdn.jsdelivr.net https://unpkg.com`.

**Det som er verdt å vite om nonce:** så snart CSP inneholder et, ignorerer nettleseren
`unsafe-inline` for samme direktiv. Det finnes ingen gradvis overgang — enten har hver
eneste inline `<script>` riktig nonce, eller så kjører den ikke. Fire blokker fantes, i
`index.html`, `mfa_verify.html` og `admin_status.html` (to).

CDN-bibliotekene er upåvirket. Tabulator, Chart.js og Bootstrap lastes som eksterne
`<script src=...>`, og vertsnavnene i direktivet gjelder fortsatt — nonce slår ikke ut
allowlisten slik `strict-dynamic` ville gjort. Det besvarer tiltakspunktet «Sjekk om
Tabulator og Chart.js krever `unsafe-inline`»: nei.

**`style-src` beholder `unsafe-inline`.** Akseptansekriteriet for F5 gjelder kun
`script-src`. Markup har rundt 50 inline `style=`-attributter pluss stilsetting bygget i
statistikk-tabellene; det er et eget stykke arbeid, lagt inn som eget TODO-punkt.

`CspNonceTests` sjekker at direktivet mangler `unsafe-inline`, at nonce er unikt per
request, at hver inline `<script>` i alle maler har nonce, og — viktigst — at nonce i
markup er **identisk** med det i headeren. Den siste er den som ville fanget et nonce
generert på feil sted i request-syklusen. Verifisert ved å fjerne nonce fra `index.html`
midlertidig: to tester ble røde, både fil-skanningen og den rendrede siden.

Med dette er `unsafe-inline` og den manglende escapingen i statistikk-tabellene lukket
samme dag. Fram til i dag manglet vi begge lagene samtidig.

730 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — F5, trinn 1: inline event-handlere ut av markup

Forberedelse til å fjerne `unsafe-inline` fra CSP-ens `script-src`. **CSP-headeren er
ikke rørt i denne commiten** — den flippes i trinn 2, slik at hvis noe brekker, vet vi
hvilken halvdel det var.

**Omfanget var større enn punktet beskrev.** F5 nevner «rundt 30 inline `onclick=` i
`index.html`». Det stemte, men i tillegg fantes:

- 6 `onclick=` som *genereres* av `patients-stats.js` (arkivlista og admin-registrene).
  CSP ser det ferdige DOM-et, så attributter satt fra JS blokkeres på samme måte.
- 2 `oninput=` i `index.html`.
- 7 `onsubmit="return confirm(...)"` fordelt på brukeradministrasjonen og
  backup-flaten. Disse var de alvorligste: bekreftelsen foran sletting av bruker,
  frysing av konto og MFA-nullstilling ville forsvunnet stille. Ikke handlingen — bare
  spørsmålet om man var sikker.

Alt går nå gjennom `data-action` (+ `data-arg`/`data-id`), delegert fra `document` i
`patients-app.js`, og `data-confirm` i en ny `static/js/ui-actions.js` som lastes fra
`base_portal.html`.

**Fellen med argumenter:** `toggleForstehjelper(id)` slår opp med `x.id === id`, streng
likhet. Et data-attributt kommer inn som streng, så `x.id === "3"` er usant og funksjonen
ville returnert uten å gjøre noe — og uten feilmelding. Derfor skilles `data-arg`
(streng) fra `data-id` (tall), og delegeringen kjører `Number()` på den siste.

Én sammensatt handler lot seg ikke uttrykke med ett `data-action`:
`onclick="stamp('e-utskrevet');updateTotal()"` er nå `stampUtskrevet()` i
`patients-utils.js`. En annen viste seg overflødig —
`onclick="document.getElementById('n-inntid').value=nowStr()"` er nøyaktig det `stamp()`
gjør.

`InlineHandlerTests` går gjennom alle maler i alle app-mapper og alle JS-moduler, og
feiler med fil og linjenummer hvis en inline handler dukker opp igjen.

**Ikke rørt:** `unsafe-inline` for `style-src`. Akseptansekriteriet i F5 gjelder kun
`script-src`, og markup har 48 inline `style=`-attributter pluss JS-genererte
stilsettinger i statistikk-tabellene.

**Krever manuell QA.** Alle knapper i pasientmodulen og brukeradministrasjonen går nå
gjennom ny kode. Testene ser at attributtene er borte og at delegeringen finnes — de
klikker ikke.

724 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — F7: betinget lasting av statistikkmodulen. F8 utsatt

**Tiltaket slik det var beskrevet ville tatt ned appen.** F7 sa «last
`patients-stats.js` kun for roller som har statistikktilgang», og forutsatte at fila bare
inneholder statistikk. Det gjorde den ikke: `DOMContentLoaded`-bootstrappen lå der —
`initTable()`, `loadPatients()`, `startRefreshInterval()` — sammen med faneskiftet,
auto-refresh og lasterne for navneregistrene, som `patients-forms.js` trenger for
nedtrekkslistene. En `read_only`-bruker ville fått en side uten tabell, uten data og uten
fungerende faner.

Bootstrappen er derfor flyttet til en ny `patients-app.js` (5,9 kB) som lastes for alle
roller. `patients-stats.js` beholder statistikk, arkiv og admin-handlinger, og lastes kun
for `admin`, `lead` og `lead_view`.

**Rollefellen som ikke er åpenbar:** `read_write` har skrivetilgang uten
statistikktilgang. Lagre-knappen for arrangementsnavn er `write-only` og dermed synlig for
den rollen, så `saveEventName` måtte til `patients-app.js`. Samme resonnement flyttet
`renderForstehjelperAdmin`/`renderHelsepersonellAdmin` motsatt vei — de bygger knapper med
`onclick` mot toggle/delete-funksjoner som bare finnes i statistikkmodulen. Det fant ikke
jeg; det fant testen, etter at jeg først hadde plassert dem feil.

Kall fra alltid-lastet kode til den betingede modulen går nå gjennom `_kall('navn')`.
`JsModulLastingTests` leser funksjonsnavnene i `patients-stats.js` og feiler hvis en
alltid-lastet modul kaller noen av dem direkte. Verifisert ved å sette inn et direkte
`loadStats()`-kall midlertidig.

**Måling:** alltid lastet 41 161 bytes, statistikkmodulen 41 516 bytes, admin-bundle
82 677 bytes. En `read_only`-bruker laster **49 %** av admin-bundlen; akseptansekriteriet
var < 50 %.

**Ikke verifisert:** «Første-paint på mobil 4G < 1,5 s». Det krever måling på enhet.
Halvert nedlasting er en forutsetning, ikke et bevis.

**F8 (PgBouncer) er bevisst utsatt.** Punktet sier selv «Kun relevant ved 4+ workers».
Driftsmodusen er 1 worker mellom vakter og 2 under vakt, altså maks 8 forbindelser mot
~100 tilgjengelige, og `conn_max_age=600` demper det ytterligere. Tiltaket er dessuten i
hovedsak en Railway-operasjon, ikke en kodeendring. Tas opp igjen hvis `WEB_WORKERS` økes.

721 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N13.2 og N13.3: navneliste-fabrikk, og `views.py` delt i fem

**N13.2.** `forstehjelpere_view`, `forstehjelper_detail_view`, `helsepersonell_view` og
`helsepersonell_detail_view` var ord for ord like bortsett fra modellnavnet og ordlyden i
feilmeldingene — inkludert hele ETag-blokken og `ProtectedError`-håndteringen.
`_navneliste_views(model, etikett, etikett_bestemt)` bygger nå begge par.

Hele testsuiten passerte uendret etter sammenslåingen, uten at én test måtte røres. Det er
den beste indikasjonen på at oppførselen er bevart. Feilmeldingene vises direkte i
grensesnittet og var det eneste ingen test dekket, så de er pinnet i
`NavneregisterFeilmeldingTests` — inkludert skillet mellom ubestemt og bestemt form
(«Førstehjelper ikke funnet» vs. «Førstehjelperen er knyttet til pasienter»).

**N13.3.** `views.py` (797 linjer) er delt i fem moduler og slettet:

| Modul | Linjer | Ansvar |
|---|---|---|
| `views_common.py` | 82 | `_json_body`, `_patient_to_dict`, `_ensure_pabegynt_not_before_inntid` |
| `views_patients.py` | 382 | Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD, nullstilling |
| `views_registre.py` | 136 | Navneregistrene |
| `views_stats.py` | 47 | `/api/stats/` og `/api/full-stats/` |
| `views_arkiv.py` | 198 | Vaktarkivet |

**Ingen shim.** `urls.py` og de fire testimportene peker direkte på de nye modulene. Å
legge igjen en `views.py` som re-eksporterte alt ville vært å innføre nøyaktig den typen
bakoverkompatibilitets-lag N11 nettopp ryddet bort — og som viste seg å drive fra hverandre.

Testene fanget den ene reelle feilen underveis: `Forstehjelper` og `Helsepersonell` ble
ikke importert i `views_patients.py`, og fem tester på FK-tilordning feilet med `NameError`
på `/api/patients/`. Det er en feil som ville nådd prod uten testdekning på de stiene.

`CLAUDE.md` og teknisk dokumentasjon er oppdatert — begge pekte på `patients/views.py`.

716 tester grønne. Ingen databaseendringer, ingen endring i API-oppførsel.

---

## 2026-08-13 — Restore-kontroll, dødt per-år-navn fjernet, driftsoppgaver løftet i TODO

**Kliniske felt kontrolleres ved backup-restore.** `loaddata` går utenom all
applikasjonsvalidering, og var etter N6 den siste veien inn i databasen der en verdi
utenfor whitelisten kunne lande usett. Ny hook `BaseBackupHandler.inspect_restore_payload()`
kalles fra `restore_backup()` med de deserialiserte objektene;
`PatientsBackupHandler` sjekker mot `patients/choices.py` og rapporterer per felt og verdi,
med antall rader.

**Kontrollen advarer, den blokkerer ikke.** Det er et bevisst valg og motsatt av
`import_offline_data`, som avbryter og krever `--force`. Forskjellen: importen tar inn
fremmed data i en rolig stund, mens restore henter tilbake våre egne data i en stresset
situasjon. En backup fra før whitelisten ble innført må kunne gjenopprettes — å nekte det
ville gjort verktøyet ubrukelig akkurat når man trenger det. `_inspect_payload()` svelger
dessuten alle feil, slik at ødelagt JSON eller en handler som kaster aldri kan bli grunnen
til at en gjenoppretting feiler.

Ni tester, inkludert at en restore med ugyldig verdi fullfører, logger advarsel, og gir
raden tilbake uendret.

**Dødt per-år-arrangementsnavn fjernet.** `set_event_name()`, `get_event_name()` og
`get_event_name_or_legacy()` ble aldri kalt fra noe sted — mekanismen med `event_name_<år>`
er aldri tatt i bruk. Slettet, sammen med whitelist-oppføringen i
`SETTINGS_READ_WHITELIST` fra N12, som dermed beskyttet en nøkkel ingenting skriver.

En test avslørte underveis at den passerte på en bivirkning: `_readable_settings_keys()`
kalte `get_active_year()`, som *oppretter* `active_year`-raden. Uten det kallet fantes ikke
raden i testen. Testen oppretter den nå eksplisitt.

**TODO-en er omstrukturert.** De tre oppgavene som krever Railway-tilgang eller en
avgjørelse utenfor prosjektet ligger nå i en egen seksjon øverst, med konsekvens beskrevet
for hver. Felles for dem: ingen oppdages av testsuiten, ingen gir feilmelding — de er bare
stille inaktive, som er nettopp derfor de har blitt liggende.

712 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — Fiks: template-kommentar rendret som synlig tekst

Kommentaren som ble lagt inn i forrige commit sto synlig i headeren for brukerne.

**Årsak:** `{# ... #}` er **enlinjes** i Djangos template-språk. En kommentar over to
linjer parses ikke som kommentar — den rendres som ren tekst. Flerlinjes kommentarer må
bruke `{% comment %}`/`{% endcomment %}`.

Testene fanget det ikke: de sjekket at `LS26` var borte og at arrangementsnavnet kom med,
ikke at responsen var fri for uparset template-syntaks. Ny test
`test_ingen_uparsede_template_kommentarer_lekker_ut` ser etter `{#`, `#}`,
`{% comment %}` og kommentarteksten i den ferdige responsen. Verifisert mot forrige
versjon av templaten, der teksten faktisk lå i utdataen.

705 tester grønne.

---

## 2026-08-13 — Fiks: gammelt arrangementsnavn sto synlig i headeren ved sidelasting

Meldt fra manuell testing: går man fra portalforsiden inn i `/pasienter/`, vises `LS26` et
kort øyeblikk før det riktige arrangementsnavnet kommer.

**Årsak:** `LS26` var hardkodet som innhold i `#event-name-display` i templaten.
`loadSettings()` byttet det ut, men kalles i `DOMContentLoaded` *etter* tre awaitede
fetch-er — førstehjelpere, helsepersonell og pasienter. Et gammelt arrangementsnavn sto
altså synlig så lenge de tre rundturene tok.

**Fiks:** arrangementsnavnet sendes med i konteksten fra `index_view` og rendres
server-side. Da er headeren riktig i første render, og det finnes ingenting å bytte ut.
`loadSettings()` er beholdt — den henter samme nøkkel, så den kan ikke lenger vise noe
annet, og den fanger fortsatt opp at en annen admin har endret navnet.

**Funnet underveis, og verre enn det som ble meldt:** samme `LS26` var hardkodet i
`value`-attributtet på innstillingsfeltet (`#setting-event-name`). Var `event_name` tom i
databasen, sto plassholderen i feltet uten at noe overskrev den — og et lagre ville skrevet
`LS26` inn som arrangementsnavn. Rettet på samme måte.

Fem tester, hvorav den viktigste sjekker at `LS26` ikke finnes noe sted i responsen når
`event_name` er tom. Et hardkodet navn vises for alle brukere uansett hvilket arrangement
som faktisk er registrert, så det er verdt en vakt.

704 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N12: whitelist på GET /api/settings/, og `invalidate_stats_cache` slettet

**N12.** Endepunktet returnerte hele `AppSetting`-tabellen til enhver innlogget bruker,
også `read_only`. Ingenting der er sensitivt i dag — `event_name`, `active_year`,
`next_patient_nr`, `session_timeout_hours`, `feature.live_stats_enabled` — men tabellen er
generisk nøkkel/verdi-lagring. Neste driftsverdi noen lagret der ville havnet i responsen
automatisk. PUT hadde whitelist fra før; GET hadde ikke, og den asymmetrien er den typen
som blir et problem lenge etter at den ble innført.

`SETTINGS_READ_WHITELIST` speiler nå PUT-lista, og `SETTINGS_WRITE_WHITELIST` gjør
PUT-siden til en navngitt konstant i stedet for en lokal variabel — begge listene ligger
ved siden av hverandre, med kommentar om at utvidelse skal være et bevisst valg.
`event_name_<aktivt år>` beregnes i `_readable_settings_keys()`, siden nøkkelen er
årsavhengig. Spørringen er samtidig blitt `filter(key__in=...)` i stedet for
`objects.all()`.

Sju tester, inkludert akseptansekriteriet: en ny nøkkel er usynlig via API-et til noen
legger den til bevisst.

**Oppfølging fra N11:** `invalidate_stats_cache()` er slettet. Den ble beholdt tidligere i
dag med en docstring om at den var ubrukt; beslutningen er omgjort. En funksjon ingen
kaller er dødkode uansett hvor godt den er dokumentert, og `cache.delete()` er tre linjer
å skrive på nytt den dagen F6 trenger den. De to testene som dekket den er fjernet.
Failsafe-dekningen for cache-utfall er urørt — den ligger på lese-stien
(`test_stats_cache_overlever_redis_feil`), ikke på invalideringen.

699 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N11: CLAUDE.md i samsvar med koden

Fire påstander i «Arkitektur»-seksjonen stemte ikke. Tre av dem var dokumentet som var
utdatert, én var koden.

**Statistikk-caching** — dokumentet lovet invalidering ved pasientendringer via signal.
Det har aldri vært koblet opp; `invalidate_stats_cache()` kalles kun fra tester. Teksten
beskriver nå den reelle mekanismen: TTL på 15/60 sekunder, og try/except rundt alle
cache-operasjoner slik at en død cache degraderer til vanlig beregning.

**Backup** — beskrivelsen («kun `patients`-appen», «logikk i `patients/backup_service.py`»)
var fra før per-modul-omleggingen. Erstattet med en tabell over de to registrerte
handlerne, `patients` og `arkiv`, og en presisering av at logikken ligger i `core/backup/`
mens `backup_service.py` er en proxy som beholdes for `db_backup`, `views.py` og eldre
tester.

**Dekorator-importene** — her var det koden som var feil. `patients/views.py`,
`core/views.py` og `patients/admin_status.py` importerte fra
bakoverkompatibilitets-shimen `accounts/decorators.py`, mens CLAUDE.md sa at man alltid
skal importere fra `core.auth_decorators`. Alle tre er byttet — samme objekter, ren
søk-og-erstatt. Shimen er beholdt, siden `core/tests.py` verifiserer at den fortsatt
virker.

Ny test `test_produksjonskode_importerer_ikke_fra_shimen` går gjennom produksjonsfilene i
alle fem appene og feiler med filnavn hvis noen tar shimen i bruk igjen. Verifisert ved å
sette `core/views.py` tilbake midlertidig. Uten den vakten driver regelen på nytt så snart
noen kopierer en importlinje fra en eldre fil — som er nøyaktig slik de tre oppsto.

**Avvik fra tiltaket:** `invalidate_stats_cache()` er beholdt, ikke slettet. Den er
triviell, testet, og F6 (live-dashbord) vil trenge den. Docstringen sier nå eksplisitt at
den er ubrukt i dag, og at den bør slettes hvis den fortsatt er det ved neste
gjennomgang. Å slette den ville ikke gjort noen påstand i CLAUDE.md mer sann.

693 tester grønne. Ingen databaseendringer.

---

## 2026-08-13 — N9: `script.js` slettet, dobbeltklikk-vernet faktisk testet

`static/js/script.js` (2159 linjer) er borte. Ingen mal lastet den — monolitten ble delt
i fire moduler i mai, og fila har ligget død siden. Den bar også en kopi av den uescapede
statistikk-koden fra N6, som dermed forsvinner helt.

Det som gjorde punktet verdt mer enn en sletting: `DoubleClickGuardTests` leste nettopp
den døde fila. Testene var grønne, og ville vært grønne også om `withSubmitGuard`
forsvant fra den levende koden. Vernet mot dobbel pasientregistrering — innført etter en
reell hendelse 30. april — var i praksis utestet.

**Tiltakspunkt 3 i N9 spurte om «grep i JS-fil» i det hele tatt er riktig verktøy.
Svaret er nei, ikke alene.** Testene kjører nå guarden i node i stedet for å lete etter
den. Fire nye oppførselstester dekker det vernet skal gjøre:

- to raske klikk gir én registrering
- knappen låses umiddelbart, ikke først når svaret kommer
- låsen holdes i minst 250 ms selv om serveren svarer raskt
- en mislykket lagring frigir låsen, og feilen når fortsatt kalleren

Verdien er målt, ikke antatt: deaktiverer man in-flight-sjekken i `withSubmitGuard`,
feiler den nye testen med `forventet 1 registrering, fikk 2`. Hendelsen fra 30. april,
gjenskapt. De gamle testene var grønne gjennom nøyaktig den endringen.

Tekstsøkene er beholdt der de fortsatt gir mening — at `saveNew`/`saveEdit` bruker
guarden, og at malen har knappe-id-ene — men supplert med en test på at malen faktisk
laster modulene testene leser. Det var den manglende koblingen som gjorde hele problemet
mulig.

Node-plumbingen er trukket ut i `patients/js_test_utils.py` og delt med
`tests_xss_stats.py` fra N6. Modulen heter bevisst ikke `tests_*`, så den ikke plukkes
opp av testoppdagelsen.

**Dokumentasjon:** `CLAUDE.md` og teknisk dokumentasjon beskrev fortsatt frontend som «én
stor `script.js`». Begge er rettet til de fire modulene, med escaping-reglene fra N6 og
en merknad om at nye JS-tester skal kjøre koden, ikke grep-e etter den. Historiske
referanser i eldre dokumenter er latt stå.

677 tester grønne. Ingen databaseendringer. `staticfiles/` er gitignorert og regenereres
av `collectstatic` ved deploy.

---

## 2026-08-13 — N13 delpunkt 1: én feltliste for arkiv-signaturen

De samme 17 feltnavnene var skrevet ut tre steder: ved arkivering
(`arkiver_aktiv_vakt`), ved statistikk (`_arkiv_pasienter_dicts`) og ved
integritetsverifikasjon (`arkiv_detalj_view`). Ble ett av stedene glemt når et felt kom
til, beregnet verifikasjonen SHA-256 over et annet feltsett enn arkiveringen gjorde — og
arkivet meldte «tukling» uten at noe var rørt. En falsk integritetsalarm på GDPR-arkivet
er verre enn en ekte feil, fordi den undergraver tilliten til hele mekanismen.

Nå ligger `ARKIVERT_PASIENT_FELTER` i `patients/services.py`, og alle tre stedene går via
`_arkiv_pasienter_dicts()`.

**Lista er frosset med vilje, ikke utledet fra modellen.** Den nærliggende løsningen — å
utlede feltene fra `ArkivertPasient._meta`, slik N2 gjorde for audit-lista — ville vært
aktivt skadelig her: signaturen lagres på `VaktArkiv.sha256` ved arkivering, så et nytt
felt ville endret signaturen for *alle eksisterende* arkiver samtidig og fått hvert eneste
av dem til å melde tukling. Nøyaktig den feilmoden punktet skulle forhindre.

I stedet: eksplisitt tuple, `ARKIVERT_PASIENT_FELTER_UNNTATT` for `id`/`arkiv`, og
`ArkivFeltlisteTests` som feiler hvis modellen og lista kommer i utakt. Testen tvinger
fram et bevisst valg — «med i signaturen» eller «unntatt» — i stedet for at et nytt felt
havner utenfor stilltiende. Feilmeldingen sier eksplisitt at gamle arkiver får en signatur
som ikke lenger kan reproduseres hvis lista utvides.

Fire nye tester, verifisert ved å fjerne `journal` fra konstanten midlertidig og bekrefte
at vakten peker på riktig felt. Hele suiten: 672 grønne.

Delpunkt 2 (navneliste-fabrikk for de fire førstehjelper/helsepersonell-viewene) og 3
(splitting av `views.py`) står igjen som ren opprydding.

Ingen databaseendringer, ingen endring i beregnet signatur for eksisterende arkiver.

---

## 2026-08-13 — N6: escaping i statistikk-tabellene

Statistikkfanen bygde HTML-strenger og satte dem inn med `innerHTML` uten å escape
verdiene. Rad- og kolonnenøklene i krysstabellene *er* pasientdata (`problemstilling`,
`transport`, `grovsortering`, `utskrevet_til`), og CSP-en tillater fortsatt
`unsafe-inline` for `script-src`, så et injisert `<img onerror=...>` ville kjørt.

**Escaping.** Ny hjelper `escHtmlValue()` i `patients-utils.js`, brukt i `mkStatsTable`,
`mkCrosstab`, `mkObsTable` og `mkInterpretation`. Den finnes ved siden av `escapeHtml()`
og `_escHtml()` fordi de to eldre returnerer tom streng for alt falsy — `escapeHtml(0)`
gir `''`. I tabellceller er det feil: 0 er en gyldig verdi som skal vises.

**Klarert markup.** Å escape alle celler blindt var ikke mulig. `renderTester` sender
bevisst `<span style="color:#22c55e">&#10004; Ja</span>` inn i `mkStatsTable`, og
`sigCol`-logikken leter etter `&#10004;` i strengen. `trustedHtml()` markerer markup koden
har bygget selv, `cellHtml()` slipper den gjennom og escaper alt annet. Unntaket er dermed
et bevisst valg per celle, ikke en generell åpning — to celler bruker det i dag.

**Funn utenfor punktet:** `renderForstehjelperAdmin` og `renderHelsepersonellAdmin` satte
også navnene uescapet i `innerHTML`. Det er verre enn N6 selv, siden
`Forstehjelper.name`/`Helsepersonell.name` er fritekst uten `choices` — whitelisten som
demper resten gjelder ikke der i det hele tatt. Rettet i samme runde.

**Import-validering.** `import_offline_data` bygde `Patient`-objekter direkte og gikk
utenom whitelisten. Den kaller nå `validate_patient_choice_fields` per rad, før noe
skrives. Ugyldige verdier avbryter importen med en rapport som dekker alle radene på én
gang; nytt `--force` importerer dem likevel, for bevisst import av gamle data.

**Tester.** `patients/tests_xss_stats.py`, to lag:

- Node kjører tabell-byggerne mot HTML-holdige feltverdier og verifiserer
  akseptansekriteriet direkte. Hoppes over hvis `node` ikke finnes.
- En statisk vaktpost krever at hver `${...}` i byggerne er escapet eller står i
  `REVIEWED_INTERPOLATIONS` med begrunnelse. Verifisert ved å fjerne escapingen
  midlertidig og bekrefte at testen peker på riktig uttrykk. Det er dette laget som
  betyr noe for F6 senere: de sju nye krysstabellene der kan ikke gli inn uescapet.

Fire nye tester i `patients/tests_offline.py` dekker import-valideringen. Hele suiten:
668 tester grønne.

**Ikke gjort:** F5 (CSP-stramming) ble *ikke* tatt i samme runde, slik
FORBEDRINGER-dokumentet foreslo. Den krever at ~30 inline `onclick=`-handlere i
`index.html` flyttes til `addEventListener`, som er mesteparten av arbeidet der.
`unsafe-inline` står fortsatt. Escapingen er på plass uavhengig av det, så vi mangler ikke
lenger begge lagene samtidig.

**Gjenstår som uvalidert vei inn i basen:** backup-restore via `loaddata`. Den går utenom
all validering, og er nå den eneste igjen. `static/js/script.js` har samme uescapede kode
i den døde kopien sin, men fila skal slettes (N9) og ble derfor stående.

Ingen databaseendringer.

---

## 2026-08-13 — Fiks: uregistrerte sesjoner overlevde innlogging på ny enhet

Funnet ved manuell testing i prod. Innlogging på enhet 2 kastet ikke ut enhet 1 —
én-sesjon-per-bruker-policyen var brutt.

**Årsak:** `current_session_key` ble innført tom for alle brukere. En sesjon opprettet før
feltet fantes er ikke registrert, så innloggingen fant ingen nøkkel å slette.
`_registrer_aktiv_sesjon` behandlet tom nøkkel som «ingen sesjoner finnes», mens den i
virkeligheten betyr «vi vet ikke om det finnes noen».

**Fiks:** Er feltet tomt, faller vi tilbake til den fullstendige gjennomgangen av
sesjonstabellen. Det koster ett fullt gjennomløp per bruker, første gang de logger inn
etter at feltet ble innført; deretter gjelder den raske stien og ytelsesgevinsten fra N10
består.

Passordbytte fjernet sesjonen korrekt hele tiden — den stien har alltid hatt den grundige
gjennomgangen, og skillet fungerte som designet.

Regresjonstesten ble verifisert ved å reversere fiksen midlertidig og bekrefte at den
feiler med nøyaktig det observerte symptomet.

**Merk:** Fiksen rydder ikke opp i sesjoner som allerede har overlevd. De forsvinner når de
utløper (maks 8 timer), ved passordbytte, eller ved at admin dreper dem fra
`/portal-admin/server-status/`.

Full suite: 650 tester, grønn. Ingen migrasjon.

---

## 2026-08-13 — Ytelse: N7, N8, N10

Tre steder der kostnaden lå i requestens kritiske vei.

**Redis-klienten ble bygget på nytt for hver request (N7).**
`_MetricsStore._get_redis_client()` kalte `redis.Redis.from_url()` ved hvert kall, og den
lager en ny `ConnectionPool` hver gang — verken pool eller TCP-forbindelse ble gjenbrukt.
`_record_to_redis()` kalles for hver eneste request i vakt-modus, så vi betalte en
TCP-handshake per request for å skrive én metrikk-linje. I koden som finnes for å måle
ytelse.

Nå én delt klient per prosess med dobbeltsjekket låsing. `redis.Redis`-instanser er
trådtrygge og har egen intern pool, så det er riktig mønster. Metoden er beholdt som
delegat, slik at de eksisterende testene som patcher den virker uendret.

**Audit-signalet gjorde én INSERT per endret felt (N8).** En typisk PUT der behandler
settes utløser samtidig `pabegynt`-stempling og plasseringsendring — 1 SELECT + 3 INSERT +
selve UPDATE for én brukerhandling. Nå samles radene og skrives med `bulk_create`.
`app_label` settes eksplisitt, siden `bulk_create` hopper over `pre_save`-signalet som
ellers fyller feltet; uten det ville radene vist seg som «Ukjent» i modulfilteret.
Verifisert med `CaptureQueriesContext`: tre endrede felt gir én INSERT.

**Sesjonsinvalidering dekodet hele sesjonstabellen ved hver innlogging (N10).**
`get_decoded()` er signaturverifisering og JSON-parsing per rad, og kallet lå i
innloggingsstien — de ti minuttene ved vaktstart der alle logger på samtidig.

**Her fulgte vi ikke backloggens anbefaling.** Alternativ A var å droppe kallet ved ordinær
innlogging, beskrevet som «en policy-avgjørelse, ikke en sikkerhetsnødvendighet». Men
policyen er reell og bevisst: portalen har én-sesjon-per-bruker, og `SingleSessionTests`
vokter den eksplisitt. Å droppe kallet ville stille endret produktoppførsel — innlogget på
mobil og laptop samtidig — under dekke av en ytelsesforbedring.

I stedet: `CustomUser.current_session_key`, ett nullbart felt (ingen ny tabell, som svarer
på innvendingen mot alternativ B om foreldreløse rader). Innlogging sletter forrige sesjon
med ett indeksert oppslag. Feltet er en cache av policyen, ikke fasit for hvilke sesjoner
som finnes — derfor beholder passordbytte, admin-reset, frys og sletting den fullstendige
gjennomgangen, der garantien er hele poenget og operasjonen er sjelden. En test verifiserer
at passordbytte også fjerner en uregistrert sesjon.

Verifisert: antall spørringer ved innlogging er identisk med 0 og med 30 fremmede sesjoner
i tabellen.

**Re-landet etter rollback.** Første forsøk (`48d861c`) tok ned produksjon — men ikke på
grunn av ytelsesarbeidet. Den commiten inneholdt også `audit/0004`, en uetterspurt
indeks-omdøping som viste seg umulig å kjøre mot den faktiske databasen. Se hendelsesnotatet
under.

Denne gangen følger kun `accounts/0008`, håndskrevet til å gjøre én ting: legge til én
nullbar kolonne. `makemigrations` ville tatt med en `AlterField` på `is_superuser` i samme
slengen — samme slags kosmetiske opprydding som forårsaket nedetiden, og derfor utelatt.
Drift-advarselen ved oppstart består, og er ufarlig.

**Andre nedetid samme dag, og hva den lærte oss:** første forsøk på å re-lande feilet med
`DuplicateColumn: column "current_session_key" already exists`. Årsaken var at
`accounts/0008` **hadde** blitt anvendt under den opprinnelige deployen — hver migrasjon
kjører i egen transaksjon, så den commitet før `audit/0004` feilet. Analysen av den første
loggen konkluderte feilaktig med at ingen av migrasjonene hadde gått gjennom.

Da migrasjonen ble skrevet om for hånd, fikk fila samtidig et nytt, mer beskrivende navn.
**Django matcher migrasjoner på app + navn, ikke på innhold.** Databasen hadde
`0008_customuser_current_session_key_and_more` registrert; repoet hadde
`0008_customuser_current_session_key`. Django så en ukjent migrasjon og prøvde å legge til
kolonnen på nytt.

Fila heter derfor fortsatt `..._and_more` selv om innholdet ikke lenger inneholder «more».
Det står som en advarsel øverst i migrasjonens docstring. Fiksen ble verifisert mot en
lokal database satt i nøyaktig samme tilstand som produksjon — kolonne til stede,
migrasjon registrert under det gamle navnet — der `migrate` svarer «No migrations to
apply».

15 nye tester i `patients/tests_ytelse.py`. Full suite: 648 tester, grønn.

---

## 2026-08-13 — HENDELSE: produksjon nede ~30 min. Ytelses-commiten rullet tilbake

**Symptom:** 502 på portalen. Railway crash-loopet release-kommandoen, med nytt forsøk
hvert par sekund fra 09:42:50 UTC.

**Rotårsak:**

```
django.db.utils.ProgrammingError:
relation "audit_audit_created_a3c1b8_idx" does not exist
```

`audit/0004` forsøkte å døpe om en indeks som ikke finnes i produksjonsdatabasen. Django
trodde den fantes fordi `audit/0002` står registrert som anvendt og er migrasjonen som ga
indeksen det navnet — men den fysiske indeksen i Postgres heter noe annet. Djangos
migrasjonshistorikk og databasen har vært ute av takt hele tiden. Advarselen «*models in
app(s) 'accounts', 'audit' have changes that are not yet reflected*», som står i samtlige
deploy-logger langt tilbake, var symptomet på nettopp det.

Release-kommandoen avbrøt ved første feilende migrasjon, så `accounts/0008` ble aldri
forsøkt. **Ingen av de to migrasjonene ble anvendt** — databaseskjemaet er uendret.

**Hvorfor det skjedde:** `audit/0004` var ikke en del av ytelsesarbeidet. Den ble generert
på eget initiativ som opprydding av et kosmetisk avvik, og lagt inn i samme deploy. Det
gjorde en uetterspurt skjemaendring til en del av en leveranse — på nettopp den tabellen
`FORBEDRINGER.md` #1 dokumenterer at har hatt rotete migrasjonshistorikk før. Selve
ytelsesarbeidet (N7, N8, N10) er ikke det som brakk noe.

**Tiltak:** Hele ytelses-commiten `48d861c` er revertert, inkludert `audit/0004`. Koden er
tilbake på `32f417d`, som deploy-loggen viser at kjørte normalt og registrerte en pasient
(`POST /pasienter/api/patients/ status=201`) kl. 11:16.

N7, N8 og N10 er satt tilbake til ⏳ i backloggen og re-landes som egen, verifisert
leveranse — uten indeks-migrasjonen.

**Indeks-avviket i `audit` lar vi stå.** Indeksen fungerer uansett hva den heter; det er
kun Djangos bokføring som er skjev. Skal det ryddes, må det gjøres ved å lese det faktiske
indeksnavnet i Postgres først — ikke ved å la `makemigrations` gjette.

**Lærdom:**

1. Ikke bland uetterspurt skjemarydding inn i en funksjonell leveranse.
2. `makemigrations` genererer mot Djangos *modellstatus*, ikke mot databasen. Der de to har
   drevet fra hverandre, produserer den migrasjoner som feiler i prod og går grønt lokalt.
3. Deploy én pulje av gangen og verifiser i prod før neste. Tre uverifiserte deploys på rad
   gjorde at feilsøkingen måtte starte med å finne ut hvilken av dem som brakk noe — og to
   av tre var uskyldige.

---

## 2026-08-13 — Sporbarhet og korrekthet: N2, N5, S7

**Audit-loggen var ufullstendig (N2).** `felt_to_track` var en håndholdt liste, og
`helsepersonell_ref_id` hadde falt ut av den. Endret man hvem som var oppfølgingsansvarlig
for en pasient, ble det ikke skrevet noen `AuditLog`-rad — samtidig som
`PERSONVERN_DOKUMENTASJON.md` A.10 lover at alle pasientendringer logges på feltnivå.

Løst med det grundige alternativet: lista utledes nå fra modellen. `FELT_UTEN_AUDIT`
inneholder de fire feltene som bevisst ikke logges (`id`, `pasientnummer`, `created_at`,
`updated_at`), og `felt_som_spores()` returnerer alt annet. Vendingen er poenget —
glemsomhet gir nå for mye logging i stedet for for lite. En test itererer modellens felter
og feiler hvis noe verken spores eller er eksplisitt unntatt.

**Sidefunn i samme funksjon:** `str(getattr(obj, felt, '') or '')` kollapset alle falsy
verdier til tom streng, også `False`. Deaktivering av en pasient ble derfor logget med
`new_value=''`, og DELETE-grenen — som sammenlikner mot `'False'` — kunne aldri slå til.
Alle deaktiveringer har stått som UPDATE i loggen. Rettet med `_audit_verdi()`, som kun
gjør `None` til tom streng.

Begge fixene virker kun fremover. Historiske endringer av helsepersonell er tapt.

**Container-tid (N5).** `get_active_year()` og `Patient.save()` brukte
`datetime.now().year`, som gir naiv container-lokaltid — UTC på Railway, uavhengig av
`TIME_ZONE='Europe/Oslo'`. Mellom midnatt og kl. 01:00 norsk vintertid er UTC-året fortsatt
det forrige, så en nyttårsvakt ville lagret pasienter på året som nettopp gikk.
Listevisningen filtrerer på samme funksjon og ville vært konsistent med seg selv — feilen
ville ikke blitt sett før noen så på statistikken i ettertid.

Ny `core.validators.current_local_year()` ved siden av `now_local_str()`, brukt begge
steder. Akseptansekriteriet er automatisert: en test parser `patients/` og `core/` med AST
og feiler hvis noe kaller `datetime.now()`. AST og ikke tekstsøk, så omtale i docstrings
ikke gir falske treff. Testet med frosset tid 31.12 kl. 23:30 UTC → 2027, kl. 22:00 UTC →
2026.

**Personverndokumentasjonen (S7).** Fire punkter, lukket på tre ulike måter:

1. **Audit-dekning** — rettet i koden (N2). Påstanden i A.10 er sann igjen uten tekstendring.
2. **Lagringstider** — var aldri et avvik; `purge_old_logs` kjører som cron. Se gårsdagens
   rettelse.
3. **`escapeHtml()`-dekning** — rettet i dokumentet, siden N6 fortsatt står åpen. A.10 og
   teknisk dokumentasjon sier nå eksplisitt at dekningen gjelder pasientskjemaet og
   arkivvisningen, ikke statistikk-tabellene, med henvisning til N6 og en merknad om at
   serverside-whitelisten demper risikoen.
4. **Argon2** — rettet i teknisk dokumentasjon, som sa at Argon2 var i bruk. Den er ikke
   installert. A.10 hadde det riktig hele tiden; de to dokumentene motsa hverandre.

12 nye tester i `patients/tests_audit_og_tid.py`. Full suite: 633 tester, grønn.

---

## 2026-08-13 — Drift: logging som når fram (N3) og e-postvarsel ved feil (F1)

**Applikasjonsloggene har aldri nådd fram (N3).** `LOGGING` hadde én logger (`memory`) og
ingen rot-logger. Alt `patients`, `core` og `accounts` logget propagerte opp til en rot uten
handler, og havnet i Pythons `lastResort` — som skriver til stderr først fra WARNING. All
INFO-logging var altså slått av i produksjon, inkludert nettopp de linjene RUNBOOK-en ber
deg lete etter for å verifisere at backup kjører.

Nå: rot-logger med handler, `standard`-formatter med tidsstempel, loggernavn og nivå, og
`LOG_LEVEL` som miljøvariabel (default `INFO`) slik at man kan skru til DEBUG på Railway
uten deploy. Verifisert at INFO fra alle tre appene faktisk når stdout formatert.

**E-postvarsel ved kritiske feil (F1).** Tatt i samme runde som N3, slik backloggen
anbefalte — `LOGGING` måtte uansett bygges om. `django.request` logger nå til både konsoll
og `mail_admins`. Dempingen ligger i `core/log_filters.py::ThrottleByMessageFilter`: maks
én mail per feiltype per 15 minutter, der feiltype er (logger, nivå, fil, linje) og ikke
meldingsteksten — samme kodefeil gir ofte varierende tekst (ulike pasient-ID-er), og en
tekstbasert nøkkel ville sluppet gjennom hver variant som om den var ny.

Filterets state er per prosess, så med to arbeidere kan man i verste fall få to mailer per
vindu. Bevisst valg: delt state i Redis ville gjort varslingsstien avhengig av at Redis er
oppe, nøyaktig det man ikke vil når man varsler om at noe er galt.

Uten SMTP-variabler er alt inert — `EMAIL_BACKEND` faller tilbake til konsoll. Variablene
er dokumentert i `.env.example` og `CLAUDE.md`.

**Rettelse av F2 og S7 — et funn som ikke var et funn.** Augustgjennomgangen skrev at
`purge_old_logs` aldri var satt opp som cron-jobb, og at lagringstidene på 730/30 dager i
`PERSONVERN_DOKUMENTASJON.md` A.9 dermed var en dokumentert, men ikke reell kontroll. S7
beskrev dette som det mest alvorlige av fire dokumentasjonsavvik, siden det gjaldt en
slettepraksis oppgitt overfor både de registrerte og tilsynsmyndighet.

**Det stemte ikke.** Jobben kjører som aktiv Railway Cron Job. Feilen oppsto fordi
cron-jobber lever i Railway-dashbordet og ikke er synlige i repoet — gjennomgangen leste
fravær i koden som fravær i drift. En in-process scheduler ble bygget og deretter rullet
tilbake da dette kom fram; to mekanismer som sletter de samme radene, hvorav den ene er
usynlig inne i web-prosessen, er verre enn én eksplisitt cron-jobb.

F2 og den ene raden i S7 er rettet i backloggen, med lærdommen notert: infrastruktur
utenfor repoet må verifiseres med den som eier driften før den skrives ned som funn. En
gjennomgang som påstår et GDPR-avvik som ikke finnes, er ikke ufarlig.

10 nye tester i `core/tests_drift.py`. Full suite: 621 tester, grønn.

---

## 2026-08-13 — To feil funnet ved manuell testing av innloggingsflyten

Begge forhåndseksisterende, begge avdekket fordi `?next=` ble testet manuelt i prod.

**`?next=` har aldri virket.** Skjemaet i `login.html` poster til
`action="{% url 'accounts:login' %}"`, som ikke tar med query-strengen. Verdien gikk
dermed tapt i det brukeren trykket «Logg inn», og man havnet alltid på forsiden — også når
`@login_required` hadde sendt en dit fra en bestemt side. Fikset med et skjult `next`-felt,
og viewet leser nå fra POST først og query-strengen som fallback. Samme mønster som Django
sin egen `LoginView`.

Verdt å merke: dette betydde at den åpne redirecten i N1 ikke var utnyttbar i praksis via
skjemaet — verdien nådde aldri fram til `redirect()`. Valideringen fra N1 er like fullt
riktig, og er nå det som holder når parameteren faktisk virker.

**Innloggingssiden manglet `@never_cache`.** Uten den kan nettleseren servere en lagret
kopi av skjemaet, og CSRF-tokenet i den kopien er knyttet til en cookie som er rotert
siden — både `login()` og `logout()` kaller `rotate_token()`. Resultatet er «CSRF-
verifisering feilet. Forespørsel avbrutt.» ved innsending, observert på iOS. Django sin
egen `LoginView` er dekorert på samme måte, av samme grunn.

**Testhullet som slapp begge gjennom:** de eksisterende testene poster direkte til
`/accounts/login/?next=...` og treffer dermed viewet, ikke nettleserflyten. Ny testklasse
`NextGjennomSkjemaTests` henter siden, leser feltene ut av HTML-en og poster til skjemaets
faktiske action med `Client(enforce_csrf_checks=True)` — altså det nettleseren gjør.

5 nye tester. Full suite: 611 tester, grønn.

---

## 2026-08-13 — Herding av innloggingsflyten: N1, S4, N4, S5, S6

Siste pulje på innloggingsflaten. Med denne er alle sikkerhetspunktene rundt innlogging fra
augustgjennomgangen lukket.

**Åpen redirect (N1 + S4).** `login_view` sendte `?next=` rett til `redirect()`, som godtar
absolutte URL-er. En lenke som `?next=https://falsk-sanitetsportal.example/` sendte altså
brukeren til angriperens side *rett etter en vellykket innlogging* — i det øyeblikket de
har mest tillit til at de er på riktig sted. Ny felles helper
`core/url_safety.py::safe_redirect_url()` bygger på `url_has_allowed_host_and_scheme` og
brukes begge steder: `next` valideres ett sted, der den leses, så MFA-stegene arver den
validerte verdien via sesjonen (og validerer den på nytt ved lesing, i tilfelle sesjonen
stammer fra en eldre release). Samme helper på `Notification.url` i
`notification_mark_read_view` (S4) — i dag settes den kun med hardkodede relative stier,
men `notify()` er designet som et generisk API for framtidige moduler.

**MFA-rate-limiting (N4).** MFA-stegene håndteres inne i `login_view`, men skjemaene sender
ingen `username` — bare koden. Dekoratoren med `key='post:username'` slo derfor opp en tom
verdi, og **alle MFA-forsøk fra alle brukere delte én bøtte**: 10 MFA-innlogginger per 5
minutter totalt for hele appen. Ved vaktstart, når alle logger på samtidig, ville bruker
nummer 11 fått 429 uten at noe var galt med kontoen.

Løst ved å flytte rate-limitingen fra dekoratorer til eksplisitte `is_ratelimited`-kall per
steg. Steg 1 beholder sine to bøtter (brukernavn og IP); MFA-stegene får hver sin bøtte
nøklet på bruker-ID fra sesjonen. Ingen URL-endring, og ingen brukernavn i POST-body.

Kontosperren er utvidet til å gjelde MFA-steget: `_registrer_mislykket_forsok()` deles nå
av begge steg, og `is_locked()` sjekkes ved inngangen til verifiseringen. Tidligere kunne
man gjette TOTP-koder i det uendelige uten at telleren ble rørt. Rate-limit-sjekken ligger
bevisst før sperresjekken, ellers ville den låste kontoen vært den ubegrensede stien.

**Utlogging krever POST (S5).** `logout_view` hadde ingen metode-restriksjon, og malene
lenket til den med `<a href>`. Enhver side på internett kunne logge ut brukeren vår med en
`<img src=".../accounts/logout/">`. De tre malene bruker nå skjema med CSRF-token.

**Trust-cookie i offline-modus (S6).** `is_secure = not DEBUG` ga `Secure`-flagget i
offline-modus, som kjører bevisst uten TLS — nettleseren kastet cookien, og «stol på denne
enheten» virket aldri i felt. Nå `request.is_secure()`, som tar hensyn til
`SECURE_PROXY_SSL_HEADER` og er riktig både på Railway og offline.

**Bemerket underveis:** `django_otp` throttler i tillegg selve TOTP-enheten etter feilede
`verify_token()`-kall (`ThrottlingMixin`, eksponentiell backoff). Et uavhengig lag som
allerede virket — verdt å kjenne til, siden det gjør at en korrekt kode rett etter flere
feilforsøk avvises en kort stund.

23 nye tester i `accounts/tests_innlogging_herding.py`. Full suite: 606 tester, grønn.

---

## 2026-08-13 — S1 + S2: én innloggingsflate, all administrasjon under /portal-admin/

**`/django-admin/` er slått av i produksjon.** Django sin innebygde admin var en parallell
innloggingsflate som omgikk samtlige sikringer appen har på innlogging: rate-limiting per
brukernavn og IP, kontosperre etter 5 feilede forsøk, MFA-tvang for brukere med
`mfa_required`, tvungent passordbytte og `LoginEvent`-logging. Alt dette ligger på
`accounts.views.login_view`; `django_otp` sin `OTPMiddleware` håndhever ingenting, den
setter kun `request.user.otp_device`. Bak flaten lå `Patient`, `CustomUser`, `AuditLog` og
`AppSetting`.

`admin.site.urls` monteres nå kun bak `if settings.DEBUG or settings.OFFLINE_MODE`, altså
som lokalt utviklerverktøy. Begge retninger er verifisert: med `DEBUG=False` gir
`/django-admin/` 404 og `reverse('admin:index')` kaster `NoReverseMatch`; med `DEBUG=True`
monteres den som før. `/django-admin/` er også fjernet fra
`MustChangePasswordMiddleware.ALLOWED_PATHS` — unntaket gjorde passordbytte-påbudet
valgfritt for alle med `is_staff`.

**`create_superuser` arver `must_change_password=True`** (S2). Modellens default er `True`,
men manageren overstyrte den til `False`, så bootstrap-adminen — kontoen med mest tilgang,
opprettet med passord fra en miljøvariabel ved hver deploy — aldri ble bedt om å bytte.
Tre eksisterende tester feilet på endringen fordi de opprettet en superbruker og forventet
å nå vanlige sider. Det var beviset på at sikringen virker.

**Paritet før fjerning.** To hull måtte lukkes først:

- **`/portal-admin/innloggingslogg/`** — global, paginert `LoginEvent`-visning med filter på
  brukernavn/IP, hendelsestype, resultat og datoperiode. Brukerdetaljsiden viser kun siste
  20 for én bruker og svarer ikke på spørsmål som går på tvers («kom det en serie feilede
  forsøk fra én IP i natt»).
- **`python manage.py appsetting`** — `--list`, `--get`, `--set`, `--delete`.
  `PUT /api/settings/` skriver kun `event_name`, så `active_year`, `next_patient_nr` og
  feature-flagg hadde ingen annen vei inn enn django-admin. Bevisst en CLI og ikke en
  UI-flate: verdiene endres sjelden og har konsekvenser for nummerserie og årshåndtering.

**Brukeradmin flyttet til `/portal-admin/brukere/`.** `/accounts/users/*` svarer med 301.
Begrunnelsen er ikke kosmetisk: `MustChangePasswordMiddleware` matcher stier med
`startswith`, og framtidige regler (rate-limiting, ekstra rollesjekk) vil naturlig skrives
på samme form. Lå brukeradministrasjonen igjen under `/accounts/`, ville en regel for
`/portal-admin/*` stille gått utenom nettopp den flaten som oppretter kontoer og deler ut
admin-rollen. `accounts/urls.py` mountes derfor på root og fordeler selv mellom
`/accounts/` (innlogging, utlogging, passordbytte) og `/portal-admin/` (administrasjon).
URL-*navnene* er uendret, så maler og tester var upåvirket av flyttingen.

25 nye tester i `accounts/tests_admin_flate.py`. Full suite: 583 tester, grønn.

---

## 2026-08-13 — Brukeradministrasjon i portalen: 500-feil, MFA-toggle, frys og sletting

Forarbeid til **S1** (fjerne `/django-admin/`). Portalens egen brukeradministrasjon på
`/accounts/users/` manglet funksjonalitet som kun fantes i Django admin — den kan ikke
fjernes før paritet er på plass.

**Rettet 500-feil ved opprettelse av bruker.** `AdminUserCreateForm.clean_email` kalte
`.strip()` på `None`. Modellfeltet er `null=True`, så ModelForm setter `empty_value=None`
på skjemafeltet: lot man e-post stå tom ble `cleaned_data['email']` `None`, ikke `''`, og
defaultverdien i `.get('email', '')` slo aldri inn. Feilen traff kun brukere uten e-post,
som er grunnen til at den så tilfeldig ut. `AdminUserEditForm` hadde allerede riktig
mønster.

**«Krev MFA» kan nå styres fra portalen.** `mfa_required` var ikke med i
`AdminUserEditForm.Meta.fields` og hadde ingen avkrysning i malen. Eneste vei til feltet
var «Nullstill MFA», som tvinger det til `True` — altså kunne MFA slås på, men aldri av
igjen uten Django admin. Feltet vises nå både i redigeringsskjemaet og som kolonne i
brukerlista.

**Frys/tø konto** (paritet med bulk-aksjonen i `CustomUserAdmin`): deaktiverer kontoen og
sletter aktive sesjoner i samme operasjon, slik at en allerede innlogget bruker ikke kan
fortsette til cookien utløper. Sperre mot å fryse egen konto.

**Permanent sletting av brukerkonto** — `POST /accounts/users/<pk>/slett/`. Sletting er
trygt fordi alle referanser til brukeren er `SET_NULL` (`LoginEvent`, `AuditLog`,
`Forstehjelper.user`, `Helsepersonell.user`, `Backup.created_by`,
`ModuleSettings.updated_by`, og `VaktArkiv.importert_av` siden GDPR fase 4.1, som fryser
navnet i `importert_av_navn`). Navn bevares altså på historiske pasienter og i arkivet.
`core.Notification` er `CASCADE` — varsler til en slettet bruker skal bort.

To sperrer: man kan ikke slette sin egen konto, og ikke den siste aktive administratoren.
Den siste blir kritisk når `/django-admin/` fjernes, siden det da ikke finnes noen
nødutgang tilbake inn i brukeradministrasjonen. I tillegg må admin skrive brukernavnet
ordrett som bekreftelse.

Frys og sletting skrives til `AuditLog` (`table_name='accounts_customuser'`) og er dermed
synlige i `/portal-admin/auditlog/`. Revisjonsraden har ingen FK til brukeren og overlever
derfor slettingen.

22 nye tester i `accounts/tests_user_admin.py`. Full suite: 558 tester, grønn.

**Gjenstår før S1 kan lukkes:** `LoginEvent` har ingen global visning i portalen (kun
siste 20 per bruker), og `AppSetting` kan ikke redigeres utenom `event_name`.

---

## 2026-08-13 — Sikkerhetsvurdering: dokumentasjonsavvik (S7)

Etter en samlet sikkerhetsvurdering av kodebasen mot `TEKNISK_DOKUMENTASJON.md` og
`PERSONVERN_DOKUMENTASJON.md` er fire punkter der dokumentasjonen påstår kontroller som
ikke er reelle i dag lagt til som **S7** i `docs/FORBEDRINGER_2026-08.md`. Fortsatt ingen
kodeendringer.

`PERSONVERN_DOKUMENTASJON.md` er behandlingsprotokollen etter GDPR art. 30 — et avvik der
er ikke bare unøyaktighet, det er dokumentasjon som ikke stemmer med behandlingen:

- A.10 sier «alle pasient-endringer logges på felt-nivå» — `helsepersonell_ref_id`
  mangler i sporingen (N2)
- A.9 sier lagringstid 730/30 dager — `purge_old_logs` er aldri satt opp som cron, så
  fristene håndheves ikke i praksis (F2)
- A.10/§7.9 viser til `escapeHtml()` som generell XSS-beskyttelse — statistikk-tabellene
  er ikke dekket (N6)
- §7.1 i teknisk dokumentasjon sier Argon2 er i bruk; A.10 sier korrekt at den ikke er
  installert — de to dokumentene motsier hverandre

Mest alvorlig er lagringstidene, siden det er en slettepraksis beskrevet overfor både de
registrerte (del B) og tilsynsmyndighet (del A) som ikke finner sted.

---

## 2026-08-12 — Kodegjennomgang: ny forbedringsbacklog

Full gjennomgang av kodebasen for å finne hva som bør forbedres. **Ingen kode er endret** —
dette er kun kartlegging og dokumentasjon.

Nytt dokument `docs/FORBEDRINGER_2026-08.md` er den aktive backloggen. Den inneholder 13
nye funn (N1–N13), 6 funn fra et eget sikkerhetspass (S1–S6) og de 9 punktene fra
mai-runden som fortsatt sto åpne (F1–F9).
`docs/FORBEDRINGER.md` er konvertert til et historisk arkiv over det som ble gjennomført,
med en peker til den nye fila.

To punkter i mai-dokumentet var merket som åpne, men viste seg å være ferdig implementert
— hash-skip for identiske auto-backups (`core/backup/service.py`) og `/healthz/`
(`patients/health.py`). Begge er nå dokumentert som gjennomført.

### De mest konkrete nye funnene

- **N1** `next`-parameteren i innloggingen valideres ikke — åpen redirect til vilkårlig
  host rett etter vellykket innlogging
- **N2** `helsepersonell_ref` mangler i `felt_to_track` i audit-signalet. Endring av
  oppfølgingsansvarlig etterlater ingen spor, i strid med det personvernprotokollen lover
- **N3** `LOGGING` har ingen rot-handler. All INFO-logging — inkludert hver eneste
  vellykkede backup — forsvinner i stillhet, selv om RUNBOOK ber deg lete etter den
- **N4** MFA-skjemaene sender ingen `username`, så `key='post:username'` samler alle
  MFA-forsøk fra alle brukere i én bøtte: 10 per 5 minutter globalt. Ved vaktstart kan
  det låse ute folk som ikke har gjort noe galt
- **N5** `get_active_year()` og `Patient.save()` bruker fortsatt `datetime.now().year`.
  Samme feilklasse som ble ryddet i #20 — en nyttårsvakt etter midnatt lagrer pasienter i
  feil år
- **N9** De tre testene som skal beskytte dobbeltklikk-fixen leser `static/js/script.js`,
  som ingen mal laster lenger. De ville vært grønne selv om guarden forsvant fra den
  levende koden

### Sikkerhetspasset

- **S1** `/django-admin/` er en parallell innloggingsflate som omgår samtlige sikringer
  appen bygger rundt `accounts.views.login_view`: rate-limiting, kontosperre, MFA-tvang,
  tvungent passordbytte og `LoginEvent`-logging. Bak den ligger `Patient`, `CustomUser`
  og `AuditLog`. `OTPMiddleware` hjelper ikke — den setter `request.user.otp_device`, den
  håndhever ingenting
- **S2** `create_superuser` setter `must_change_password=False`, så bootstrap-adminen kan
  gå i årevis på deploy-passordet. Henger sammen med S1 og bør tas samtidig
- **S3** Rate-limiting finnes kun på innlogging — ingen struping på skriveendepunktene
- **S4** Lagret open redirect i varsel-visningen (`core/views.py:612`). Ikke utnyttbar i
  dag, men `notify()` er designet som generisk API for framtidige moduler
- **S5** Utlogging skjer via GET — en tredjepartsside kan tvinge utlogging
- **S6** MFA trust-cookie settes med `secure=True` i offline-modus, så nettleseren kaster
  den og «stol på denne enheten» virker ikke i felt

Dokumentet noterer også hva som ble kontrollert og funnet i orden, så det ikke revideres
på nytt: endepunktdekning, path traversal via backup-filnavn, audit-logging fra Django
admin, offline-modusens bevisste unntak og invalidering av MFA trust-cookien.

---

## 2026-08-12 — Backup samlet på én flate

Pasientmodulen hadde sitt eget backup-panel under Innstillinger, med egne
`/pasienter/api/backup/`-endepunkter. Det var to UI-er over samme backend: samme
`Backup`-tabell, samme filer på disk, samme `core.backup.restore_backup`.

**Det var ikke bare duplisering.** Panelets intervall-innstilling skrev til
`patients.BackupConfig` — den gamle singleton-modellen — mens scheduleren utelukkende
leser `core.ModuleBackupConfig`. Endret du intervallet der, skjedde ingenting. «Siste
automatiske backup» ble heller aldri oppdatert. Listen viste dessuten backuper fra alle
moduler blandet, uten å si hvilken modul de tilhørte.

- Fjernet de seks `/pasienter/api/backup/`-endepunktene med tilhørende URL-er
- Fjernet backup-panelet og ~130 linjer JS fra pasientmodulen
- Innstillinger lenker nå til `/portal-admin/backup/` i stedet
- `BackupAPITests` fjernet; portal-admin-flaten har allerede bedre dekning. Lagt til
  `test_run_view_requires_admin` for full paritet

536 tester, alle grønne.

Gjenstår som egne oppgaver (se TODO): den døde modellen `patients.BackupConfig` med
kommandoen `db_backup`, og `static/js/script.js` som ingen mal laster.

---

## 2026-08-12 — GDPR fase 3.1: arkiv kollapser til aggregat etter 24 måneder

Siste fase i GDPR-gjennomgangen. Arkiverte pasientrader slettes permanent etter 24
måneder og erstattes av den ferdig beregnede statistikken. Formålet — evaluering og
planlegging — er da uttømt, og art. 5(1)(e) tillater ikke at helseopplysninger på
radnivå blir liggende på ubestemt tid.

**Alt som vises i arkivvisningen bevares:** sammendrag, triagefordeling, ankomstkurve,
tidsstatistikk per gruppe, krysstabeller, kji-kvadrat og Kruskal-Wallis. Det som
forsvinner er enhver opplysning om enkeltpasienter. Etter kollaps kan ingenting i
arkivet føres tilbake til en person.

- Nye felt på `VaktArkiv`: `kollapset_at`, `aggregat` (JSON), `aggregat_sha256`
- `compute_arkiv_stats` / `compute_arkiv_full_stats` leser frosset aggregat når radene
  er borte — samme returstruktur, så grensesnittet er uendret
- Ny kommando `kollaps_arkiv` med `--dry-run`. Migrasjon `patients.0013`

### Integritetssjekk

`sha256` er beregnet over pasientradene og kan ikke verifiseres etter kollaps. Ved
kollaps beregnes en ny sjekksum over aggregatet, som overtar tuklingsdeteksjonen. Den
opprinnelige beholdes som historisk fingeravtrykk, men er ikke lenger etterprøvbar.
Arkiv-API-et eksponerer `kollapset` slik at grensesnittet kan skille tilstandene — et
arkiv som melder «ingen tukling» uten at noe faktisk sjekkes ville vært verre enn
ingen sjekk.

### Sikkerhetssperrer for en irreversibel operasjon

- Kommandoen nekter å kollapse med mindre det finnes en `arkiv`-backup tatt etter at
  arkivet ble opprettet. Fase 3.2 gjorde denne sperren mulig
- `--dry-run` viser nøyaktig hva som ville blitt slettet
- Hver kollaps loggføres i `AuditLog`
- Egen cron-jobb, ikke del av `purge_old_logs`: irreversibel sletting av helsedata skal
  ikke fyre som bieffekt av en loggopprydding

20 nye tester. 545 tester totalt, alle grønne.

Oppsettsinstruks for cron-jobben: `docs/OPPSETT_KOLLAPS_CRON.md` (midlertidig, slettes
når jobben er satt opp).

---

## 2026-08-12 — GDPR fase 3.2: arkivet som egen backup-modul

Tidligere var `VaktArkiv` ekskludert fra pasient-backupen mens `ArkivertPasient` ble tatt
med — barna uten forelderen. Det ga to problemer: en restore av pasientdata **feilet** på
fremmednøkkel dersom arkivet var slettet i mellomtiden, og arkivet kunne uansett ikke
gjenopprettes fra den backupen siden forelderen manglet. Null gjenopprettingsevne, bare
nedside.

- Ny `ArkivBackupHandler` (slug `arkiv`) med `VaktArkiv` + `ArkivertPasient` samlet
- Begge arkivmodellene ekskludert fra `PatientsBackupHandler`
- Egen `ModuleBackupConfig` via migrasjon `core.0005`: døgnintervall, cap 20.
  Arkivet endres bare når en vakt arkiveres, og innholds-hashen hindrer duplikater
- Vises som egen modul i `/portal-admin/backup/` med egen konfigurasjonsside

Motivasjonen er at Railways databasebackup kun er aktiv den måneden abonnementet er
oppgradert. Resten av året er dette den eneste dekningen arkivet har.

### Fallgruve avdekket underveis

Serialiseringen kjører med `natural_foreign=True`, så `VaktArkiv.importert_av` ble lagret
som brukernavnet. Var kontoen slettet, feilet **hele** gjenopprettingen med
`DeserializationError` — altså nøyaktig i scenarioet fase 4.1 nettopp gjorde mulig.

Løst med ny deklarativ `strip_fields` på `BaseBackupHandler`: angitte felter fjernes fra
dumpen før lagring. Arkiv-handleren utelater `importert_av`, siden brukernavnet uansett
ligger frosset i `importert_av_navn`. Mekanismen er generell og tilgjengelig for
framtidige moduler med FK-er som peker ut av eget datasett.

16 nye tester, blant annet at en pasient-restore nå går gjennom selv om et arkiv er
slettet, og at arkiv-restore virker etter at brukeren er borte. 525 tester, alle grønne.

---

## 2026-08-12 — GDPR fase 4.1: brukere kan slettes etter arkivering

`VaktArkiv.importert_av` hadde `on_delete=PROTECT`. En bruker som hadde arkivert en vakt
kunne dermed ikke slettes — databasen avviste med `ProtectedError`, og sletterett etter
GDPR art. 17 var blokkert på databasenivå. Med få admin-brukere merkes det ikke, men det
ville truffet ved første sletteforespørsel når frivillige får egen konto.

- Nytt felt `VaktArkiv.importert_av_navn`: frosset brukernavn som overlever brukersletting.
  Samme mønster som `ArkivertPasient.forstehjelper_navn` allerede brukte
- `importert_av` endret til `on_delete=SET_NULL, null=True`
- Migrasjon `0012` med datamigrasjon som fyller navnet på eksisterende arkiver
- Ny `VaktArkiv.importert_av_visning` brukes av `arkiv_liste_view` og `arkiv_detalj_view`.
  Begge leste tidligere `importert_av.username` direkte og ville fått `AttributeError`
  på `None` etter en sletting
- 8 nye tester: sletting fungerer, arkiv og pasientrader består, begge API-visningene
  overlever, og SHA-256-integritetssjekken påvirkes ikke

509 tester, alle grønne.

---

## 2026-08-12 — Testsuiten: 500 s → 15 s

Suiten brukte 8 minutter på 501 tester, noe som gjorde det upraktisk å kjøre den
under utvikling.

**Årsak:** Django-standarden PBKDF2 med 1 000 000 iterasjoner koster ~630 ms per hashing,
og suiten oppretter brukere og logger inn hundrevis av ganger. Alene stod dette for
mesteparten av kjøretiden — `accounts` brukte 141 s på 36 tester.

**Fiks:** `PASSWORD_HASHERS` settes til MD5 når — og bare når — `manage.py test` kjører
(`sys.argv[1] == 'test'`). Verifisert at gunicorn og `runserver` fortsatt bruker PBKDF2.

| | Før | Etter |
|---|---|---|
| `accounts` | 141 s | 0,9 s |
| Hele suiten | 504 s | 15,5 s |

Alle 501 tester fortsatt grønne.

**Dokumentasjonsfeil oppdaget underveis:** README og personvernprotokollen oppga
passord-hashing som «argon2 / pbkdf2». `argon2-cffi` er ikke i `requirements.txt`, så det
er PBKDF2 alene. Rettet begge steder. Argon2 kan aktiveres senere ved å legge til pakken.

---

## 2026-08-12 — GDPR fase 2: kodefikser

### Serverside-validering av kliniske felt (2.1)

- Ny `patients/choices.py` med kanonisk verdimengde for `problemstilling`, `arsak`,
  `transport`, `grovsortering`, `plassering`, `utskrevet_til`, `lege`, `medisiner` og `journal`
- `patient_create` og `patient_detail_view` avviser nå verdier utenfor mengden med HTTP 400.
  Tidligere ble verdiene skrevet rett inn fra request-body, slik at en klient som gikk utenom
  grensesnittet kunne lagre fritekst — i verste fall navn — i felt som skal være
  ikke-identifiserende
- Ny `patients/tests_choices.py` (15 tester), inkludert drift-vakt som leser `index.html` og
  feiler hvis skjemaet og hvitelisten kommer i utakt
- Testdata oppdatert: 48 plassholderverdier (`'A'`, `'Test'`, `'Båre 1'`, `'Hjem'`) byttet til
  reelle verdier. `journal='Oppfølging'` var en rest fra da feltet var en kategori

### Øvrige fikser

- **2.2:** `SECRET_KEY` hard-feiler ved oppstart med `DEBUG=False` hvis nøkkelen mangler eller er
  en kjent eksempelverdi. Tidligere falt den stilltiende tilbake på en hardkodet utviklingsnøkkel
- **2.3:** `purge_old_logs` sletter nå også varsler eldre enn 30 dager, med egen
  `--notification-days`. 5 nye tester
- **2.4:** Fjernet dødt `GET /api/archives/` med tilhørende UI-seksjon og JS. Endepunktet listet
  JSON-filer i `arkiv/`, men ingenting skrev slike filer; mappa lå dessuten på containerens
  flyktige disk på Railway. Rest fra Flask-tiden

### Windows-fiks (nødvendig for å kunne kjøre testene lokalt)

- `core/middleware.py` importerte `resource` ubetinget — en Unix-modul. Siden middlewaren står i
  `MIDDLEWARE`, feilet **hver eneste HTTP-test** på Windows. Importen er nå betinget, og
  minnelogging degraderer til ren responstid-logging der modulen mangler. Linux-oppførselen
  er uendret

Hele suiten: 501 tester, alle grønne.

---

## 2026-08-12 — GDPR-gjennomgang: protokoll v1.5

### Rettslig grunnlag omskrevet

- Avklart at systemet **ikke** er et behandlingsrettet helseregister. Journalføring skjer i eksternt
  system; feltet `journal` er kun et Ja/Nei-flagg som registrerer om journal er ført der
- Helsepersonelloven §§ 39–40 og pasientjournalloven fjernet som rettslig grunnlag
- Art. 6(1)(d) + art. 9(2)(h) står igjen, med taushetspliktvilkåret i art. 9(3) dokumentert

### Lagringstider korrigert som følge av bortfalt journalplikt

- Audit-logg: 10 år → **2 år**. Dokumentet samsvarer nå med det `purge_old_logs` faktisk håndhever
- Arkiverte pasientrader: **24 måneder**, deretter kollaps til aggregert statistikk *(planlagt)*
- Varsler: **30 dager** *(planlagt)*
- Backup: «72 timer» var feil — oppryddingen er antallsbasert (`max_backups`, standard 50).
  `RETENTION_HOURS` er død kode

### Nye kategorier og behandlinger dokumentert

- `VaktArkiv`, `ArkivertPasient` og `core.Notification` lagt inn i A.6
- Railway databasebackup lagt inn som egen behandling i A.2, med presisering av at den omfatter
  hele databasen — i motsetning til modul-backupen

### Vurderinger dokumentert (art. 5(2))

- Fravalg av innsynslogg, med begrunnelse
- Fravalg av begrenset lesetilgang («Mine pasienter» som tilgangsgrense)
- DPIA vurdert som ikke påkrevd
- Korrigert påstanden om at fritekst-risiko er «eliminert» — verdimengden håndheves foreløpig
  kun i grensesnittet, ikke i API-et

### Øvrig

- Ny **Del B.8**: informasjon til appbrukere (frivillige og helsepersonell), som manglet helt
- Merknad i A.1 om at behandlingsansvaret ligger hos privatperson
- Kjent begrensning dokumentert: `VaktArkiv.importert_av` (`PROTECT`) blokkerer sletting av brukere
- Dokumentasjonen konsolidert: `PERSONVERN_DOKUMENTASJON.md`, `TEKNISK_DOKUMENTASJON.md` og
  `RUNBOOK_VAKT.md` bor nå kun i `docs/`. Kopiene i rot var nyest og er flyttet dit; de utdaterte
  `docs/`-versjonene er overskrevet
- Ny `docs/GDPR_TILTAKSPLAN.md` med gjenstående faser

---

## 2026-06-23 — Python 3.13 + arbeidsflyt-regel

### Oppgradering til Python 3.13

- `runtime.txt` satt tilbake til `python-3.13` (var utilsiktet flippet til `3.12` i fase-3a-commit `75258f8`)
- Matcher miljøet pasientregistrering kjører på Railway — én færre variabel ved kommende repo-bytte på Railway
- Ingen avhengigheter er pinnet til 3.12; `requirements.txt` uendret

### Ny arbeidsflyt-regel

- `CLAUDE.md`: alle endringer som skal commites/pushes skal oppdatere CHANGELOG og TODO i forkant (samme commit)

---

## 2026-05-25 — Behandler → Førstehjelper + Mine pasienter

### Rename: Behandler → Førstehjelper (Fase 6)

- `Behandler`-modellen omdøpt til `Forstehjelper` i kode, database og UI
- Django-migrasjon med `RenameModel` + `RenameField` — ingen tap av data
- API-endepunkt `/api/behandlere/` → `/api/forstehjelpere/`
- `UserPatientLinkForm` erstattet av `PasientRolleForm` — enkel radio (Ingen / Førstehjelper / Helsepersonell) i brukeradmin
- Alle JS-moduler, templates, tester og admin oppdatert (~250 forekomster)
- 475 tester, alle grønne

### «Mine pasienter» — listevisning

- Endret fra checkbox/toggle til filterknapp i rekken med Alle / Rød / Gul / osv.
- Eksklusivt filter (ikke kombinerbart); klikker man en annen — nullstilles «mine»
- Server-side filtrering via `?mine=1` bevart; localStorage-persistering fungerer

### «Mine pasienter» — tavle

- Ny knapp ved siden av «Ny pasient» i tavle-visningen
- Viser alle pasienter, men dimmer (opacity + desaturate) pasienter som ikke er dine
- Ledige plasser («Ledig») påvirkes ikke

### Diverse UI

- Spacing-fix: «Ny pasient»-knappen har nå riktig avstand ned til sonene i tavlen

---

## 2026-05-16 — Mørkt tema konsolidert

### Designstrategi

Portalen bruker nå et konsistent mørkt tema på alle sider — i harmoni med pasientregistrerings-appen. Prinsipp fremover: `portal.css` styrer all theming globalt; templates bruker bare Bootstrap-klasser og `--portal-*`-variabler, ingen inline `background:` eller `color:` for standard innholdsbokser.

### `portal.css` — utvidet til komplett dark-theme grunnmur

- **`.card`**: mørk bakgrunn (`--portal-surface`), synlig border (`--portal-border`), lys tekst
- **`.card-header/.card-footer`**: mørkere bakgrunn (`--portal-surface-2`)
- **`.table td, .table th`**: eksplisitt `color: var(--portal-text)` — fikser svart tekst i alle tabellceller inkl. `<strong>`-elementer
- **`code`**: lyseblå farge (`--portal-accent`) med svak blå bakgrunn — erstatter Bootstrap sin knallrosa standard (`#d63384`)
- **`.pagination`**: dark-theme for alle fremtidige pagineringselementer
- **Kommentar**: oppdatert til å reflektere faktisk innhold

### `base_portal.html` `:root` — Bootstrap-tokens

- `--bs-body-bg`, `--bs-body-color`, `--bs-border-color` lagt til — gir Bootstrap-utilities korrekte mørke verdier og synlig kortkant mot mørk sidefarge

### Global dato/klokkeslett

- **`portal-clock.js`**: Ny dedikert fil med `updateClock()` — viser norsk dag, dato og tid (oppdateres hvert sekund)
- **`base_portal.html`**: `#header-dt`-element lagt til i headeren (mellom varselbjelle og avatar) — klokken vises nå på alle portal-sider
- **`script.js`**: `DAYS_NO` og `updateClock()` fjernet — dekkes nå globalt av `portal-clock.js`

### Template-opprydding

- **`module_admin_list.html`**: redundante inline-stiler på `<table>` og `<thead>` fjernet — portal.css håndterer dette globalt
- **`audit_log_list.html`**: 5 duplikate CSS-regler fjernet fra `{% block extra_head %}`; `.pagination`-regler flyttet til portal.css; audit-spesifikke regler beholdt

---

## 2026-05-15 (sesjon 2)

### CSS-gjennomgang og fremtidssikring

- **Bootstrap dark-theme tokens**: `--bs-body-color`, `--bs-body-bg` m.fl. overstyrt i `:root` slik at alle Bootstrap text-/bg-utilities automatisk fungerer mot portalens mørke bakgrunn
- **`portal.css`**: Ny fil for Bootstrap dark-theme overrides (`.text-muted`, `.card`, `.table`, `.form-control`, `.alert-*`). Erstatter inline CSS-blokk i `base_portal.html`
- **CSS-variabel-aliaser**: `--surface-1`, `--border-color` m.fl. aliasert til `--portal-*` for bakoverkompatibilitet
- **4 accounts-templates migrert**: `change_password.html`, `user_form.html`, `user_detail.html`, `ratelimited.html` byttet fra `base.html` til `base_portal.html`
- **Kortbakgrunn-fix**: `--bs-table-bg: transparent` lagt til i `.table`-regel — forhindrer at Bootstrap tildekker kortets bakgrunnsfarge med sidefarge

### Prosjektstruktur

- 14 historiske `.md`-filer flyttet til `docs/`-mappe
- `CHANGELOG.md` og `TODO.md` opprettet i roten

481 tester, alle grønne.

---

## 2026-05-15 (sesjon 1)

### URL-rydding: server-status flyttet

- Kanonisk URL endret fra `/pasienter/admin/server-status/` → `/portal-admin/server-status/`
- Bakover-kompatible redirects (301) bevarer gamle URL-er
- 4 hardkodede `fetch()`-URL-er i `admin_status.html` erstattet med Django `{% url %}`-tags via `ADMIN_URLS`-objekt
- Middleware-skiplist, tester (~30 referanser) og legacy-redirect i `core/urls.py` oppdatert

### Visuell konsistens

- **Server-status**: CSS-variabler (`--surface-1` etc.) byttet til `--portal-*`-varianter etter template-bytte
- **Portal-header**: Brukernavn og rolle-badge fjernet fra headeren, vises nå kompakt øverst i dropdown
- **Admin-nav**: «Brukere»-lenke lagt til for admin-brukere
- **Pasientmodul-dropdown**: «Min profil»-lenke lagt til

### Testresultat

481 tester, alle grønne.

---

## 2026-05-14 (tidligere sesjon)

### Fase 5: Bruker-behandler-kobling + varselbjelle

- Behandlere og helsepersonell kan kobles til brukerkonto
- Generisk varsel-bjelle implementert med deduplisering (24t-vindu)
- `script.js` delt opp i 4 moduler: `patients-utils.js`, `patients-table.js`, `patients-forms.js`, `patients-stats.js`
- `accounts/users/` og `admin_status.html` byttet fra `base.html` til `base_portal.html`
