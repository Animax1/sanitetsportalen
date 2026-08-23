# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

---

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
