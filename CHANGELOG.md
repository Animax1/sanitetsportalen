# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

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
