# Forbedringer – kodegjennomgang august 2026

> **Versjon:** August 2026 (etter full gjennomgang av kodebasen)
> **Formål:** Aktiv utviklings-backlog. Inneholder (1) nye funn fra kodegjennomgangen og
> (2) de fortsatt åpne punktene som er flyttet hit fra `FORBEDRINGER.md`.
> **Forholdet til [`FORBEDRINGER.md`](./FORBEDRINGER.md):** Den fila er nå et **historisk
> arkiv** over gjennomførte tiltak fra mai-runden. Alt som fortsatt står åpent er flyttet
> hit. Nye forslag skal legges til her, ikke der.
> **Bruk:** Plukk fra topp og ned. Høy verdi / lav innsats er listet først.

Ingen kode er endret som del av denne gjennomgangen — dette er kun en kartlegging.

---

## Sammendrag — prioriterings-matrise

Status: ⏳ pending · 🔧 påbegynt · ✅ ferdig · ⚪ ikke aktuell

### Nye funn (august 2026)

| # | Tittel | Status | Verdi | Innsats | Type |
|---|---|---|---|---|---|
| N1 | **Åpen redirect i innloggingsflyten (`next` valideres ikke)** | ⏳ | Høy | 1 t | Sikkerhet |
| N2 | **`helsepersonell_ref` mangler i audit-sporingen** | ⏳ | Høy | 30 min | Personvern / sporbarhet |
| N3 | **Applikasjonsloggene når aldri fram (LOGGING mangler rot-handler)** | ⏳ | Høy | 30 min | Drift |
| N4 | **MFA-steget deler én rate-limit-bøtte — kan låse ute hele vakten** | ⏳ | Høy | 1–2 t | Drift / sikkerhet |
| N5 | `get_active_year()` og `Patient.save()` bruker container-tid | ⏳ | Middels–Høy | 30 min | Korrekthet |
| N6 | Statistikk-tabellene setter inn feltverdier uescapet i `innerHTML` | ⏳ | Middels | 2 t | Sikkerhet (dybdeforsvar) |
| N7 | Redis-klienten bygges på nytt for hver eneste request | ⏳ | Middels | 1 t | Ytelse |
| N8 | Audit-signalet gjør N+1 skrivinger per pasientendring | ⏳ | Middels | 1–2 t | Ytelse |
| N9 | Tre tester verifiserer dobbeltklikk-fixen i **død** JS-fil | ⏳ | Middels | 30 min | Testkvalitet |
| N10 | Sesjonsinvalidering dekoder hele sesjonstabellen ved hver innlogging | ⏳ | Middels | 2–3 t | Ytelse |
| N11 | Dokumentasjonsdrift: `CLAUDE.md` beskriver ting koden ikke gjør | ⏳ | Lav–Middels | 30 min | Dokumentasjon |
| N12 | `GET /api/settings/` eksponerer hele `AppSetting`-tabellen | ⏳ | Lav | 30 min | Dybdeforsvar |
| N13 | Duplisert kode i `views.py` og `services.py` (ETag-blokk, feltlister) | ⏳ | Lav | 3–4 t | Vedlikehold |

### Sikkerhetsgjennomgang (eget pass)

| # | Tittel | Status | Verdi | Innsats |
|---|---|---|---|---|
| S1 | **`/django-admin/` omgår samtlige av appens innloggingssikringer** | ⏳ | Høy | 1–2 t |
| S2 | **`create_superuser` setter `must_change_password=False`** | ⏳ | Middels–Høy | 15 min |
| S3 | Rate-limiting finnes kun på innlogging | ⏳ | Middels | 2 t |
| S4 | Lagret open redirect i varsel-visningen | ⏳ | Lav–Middels | 15 min |
| S5 | Utlogging skjer via GET | ⏳ | Lav | 30 min |
| S6 | MFA trust-cookie settes med `secure=True` i offline-modus | ⏳ | Lav | 15 min |
| S7 | **Personverndokumentasjonen påstår kontroller som ikke er reelle i dag** | ⏳ | Høy | 1 t |

### Overført fra FORBEDRINGER.md (fortsatt åpne)

| # | Tittel | Opprinnelig nr. | Status | Verdi | Innsats |
|---|---|---|---|---|---|
| F1 | E-postvarsel ved kritiske feil (uten Sentry) | #3 | ⏳ | Høy | 2–3 t |
| F2 | Automatisert audit-purge (`purge_old_logs` i scheduler/cron) | #13 | ⏳ | Middels–Høy | 1–2 t |
| F3 | Server-side idempotency for pasient-opprettelse (Fix B) | #18 | ⏳ | Middels–Høy | 2–3 t |
| F4 | Lasttest-script før stor vakt | #7 | ⏳ | Middels | 3–4 t |
| F5 | CSP-stramming (fjerne `unsafe-inline`) | #8 | ⏳ | Middels | 2 t |
| F6 | Statistikk-utvidelse (live-dashbord + utvidet analyse) | #12 | ⏳ | Middels–Høy | 25–35 t |
| F7 | Frontend bundle-størrelse / lazy loading | #9 | ⏳ | Lav | 4–6 t |
| F8 | PgBouncer / Postgres connection pooler | #10 | ⏳ | Lav | 2–3 t |
| F9 | Kolonne-kryptering for følsomme felter | #14 | ⏳ | Lav | 8–12 t |

**Anbefalt rekkefølge:** **S1 og S2 først** — de henger sammen og undergraver alt det
andre sikkerhetsarbeidet i appen. Deretter N1 → N2 → N3 → N4, som alle er små og har
konkret risiko knyttet til seg. N5 bør tas før nyttår (se begrunnelsen).

---

# Del 1 — Nye funn fra kodegjennomgangen

## N1. Åpen redirect i innloggingsflyten

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 1 t &nbsp;|&nbsp; **Type:** Sikkerhet

**Bakgrunn:** `login_view` leser `next` rett fra query-strengen og sender den videre til
`redirect()` uten noen validering:

```python
# accounts/views.py:162
next_url = request.GET.get('next', '/')
...
# accounts/views.py:133 (_do_complete_login)
return redirect(next_url)
```

Samme verdi lagres i `request.session['mfa_next_url']` og brukes på nytt i
`_handle_mfa_setup` (linje 306) og `_handle_mfa_verify` (linje 374).

`django.shortcuts.redirect()` godtar en absolutt URL. En lenke som
`https://<app>/accounts/login/?next=https://falsk-sanitetsportal.example/` sender altså
brukeren til angriperens side **rett etter en vellykket innlogging** — akkurat i det
øyeblikket brukeren har mest tillit til at de er på riktig sted. Det er den klassiske
oppskriften på et phishing-steg to.

Django sin egen `LoginView` beskytter mot dette med `url_has_allowed_host_and_scheme()`.
Denne appen bruker et egenskrevet innloggingsview og har aldri fått den sjekken —
funksjonen finnes ikke i kodebasen i det hele tatt.

**Tiltak:**

1. Legg til en helper i `accounts/views.py`:
   ```python
   from django.utils.http import url_has_allowed_host_and_scheme

   def _safe_next(request, candidate, fallback='/'):
       if candidate and url_has_allowed_host_and_scheme(
           candidate,
           allowed_hosts={request.get_host()},
           require_https=request.is_secure(),
       ):
           return candidate
       return fallback
   ```
2. Kjør `next_url` gjennom `_safe_next()` **ett sted** — der den leses (linje 162) — slik
   at både MFA-stegene og direkte innlogging arver den validerte verdien.
3. Tester: `?next=https://evil.example/` → redirect til `/`; `?next=/pasienter/` →
   redirect dit; `?next=//evil.example` (protokoll-relativ) → redirect til `/`.

**Akseptansekriterium:** Ingen verdi av `next` kan sende en innlogget bruker til en annen
host enn appen selv.

---

## N2. `helsepersonell_ref` mangler i audit-sporingen

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 30 min &nbsp;|&nbsp; **Type:** Personvern / sporbarhet

**Bakgrunn:** `patient_pre_save` sporer feltendringer mot en fast liste:

```python
# patients/signals.py:70–75
felt_to_track = [
    'problemstilling', 'arsak', 'transport', 'inntid', 'grovsortering',
    'pabegynt', 'plassering', 'forstehjelper_id', 'lege',
    'medisiner', 'inn_obspost', 'ut_obspost', 'utskrevet',
    'utskrevet_til', 'journal', 'year', 'is_active',
]
```

`forstehjelper_id` er med. **`helsepersonell_ref_id` er ikke.** Endrer man hvem som er
oppfølgingsansvarlig for en pasient, skrives det ingen `AuditLog`-rad. Feltet er ellers
likestilt med førstehjelper i hele appen: det utløser `pabegynt`-stempling
(`TREATMENT_TRIGGER_FIELDS` i `services.py:169`), det sender varsel ved tildeling og
flytting (`signals.py:149–167`), og det arkiveres som `helsepersonell_navn`.

Dette er ikke en teoretisk mangel. `PERSONVERN_DOKUMENTASJON.md` og
`GDPR_TILTAKSPLAN.md` bygger begge på at endringsloggen er komplett — det er den som
begrunner at systemet kan svare på «hvem hadde ansvar for denne pasienten, og når ble
det endret». For helsepersonell-rollen kan vi i dag ikke svare på det.

**Tiltak:**

1. Legg `'helsepersonell_ref_id'` inn i `felt_to_track`.
2. Vurder samtidig å utlede lista fra modellen i stedet for å håndholde den — f.eks.
   alle konkrete felter unntatt `created_at`/`updated_at`/`pasientnummer`. Da kan et nytt
   felt aldri igjen falle utenfor loggen stilltiende.
3. Test: PUT som bytter `helsepersonell_ref` skal gi én `AuditLog`-rad med
   `field_name='helsepersonell_ref_id'`, gammel og ny ID.

**Merk:** Fixen virker kun fremover. Historiske endringer av helsepersonell er tapt og
kan ikke rekonstrueres.

**Akseptansekriterium:** Enhver endring av et lagret pasientfelt gir en audit-rad. En test
som itererer modellens felter og feiler hvis noen mangler i `felt_to_track`.

---

## N3. Applikasjonsloggene når aldri fram

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 30 min &nbsp;|&nbsp; **Type:** Drift

**Bakgrunn:** `LOGGING` i `myproject/settings.py:310–325` konfigurerer én eneste logger:

```python
'loggers': {
    'memory': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
},
```

Det finnes ingen rot-logger og ingen logger for `patients`, `core` eller `accounts`.
Alt de modulene logger propagerer opp til rot-loggeren, som ikke har noen handler — og
havner da i Pythons `lastResort`-handler, som skriver til stderr **fra og med WARNING**.

Konsekvensen er at all INFO-logging i praksis er slått av i produksjon:

- `core/backup/service.py:143` — «auto-backup hoppet over (identisk innhold)»
- `core/backup/service.py:165` — «opprettet \<filnavn\> (n bytes)»
- `patients/backup_scheduler.py:108–116` — hver eneste vellykkede automatiske backup
- `core/backup/service.py:266` — hvem som gjenopprettet hvilken backup

Dette er nøyaktig de linjene RUNBOOK-en ber deg lete etter i `railway logs` når du skal
verifisere at backup faktisk kjører. De har aldri vært der. Og `logger.exception(...)` i
`patients/views.py:676` og `patients/signals.py:170` kommer riktignok fram, men uten
formatering — ingen tidsstempel, ingen loggernavn, ingen nivå.

**Tiltak:**

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'memory': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
```

`LOG_LEVEL` som miljøvariabel gjør at man kan skru til DEBUG under feilsøking på Railway
uten deploy. Vurder `WARNING` som default hvis INFO viser seg å bli for prateglad — men
gjør det som et bevisst valg, ikke som i dag hvor det er en bieffekt.

**Akseptansekriterium:** `railway logs --latest` viser en formatert linje per automatisk
backup. Dette er også en forutsetning for F1 (e-postvarsel ved kritiske feil).

---

## N4. MFA-steget deler én rate-limit-bøtte — kan låse ute hele vakten

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 1–2 t &nbsp;|&nbsp; **Type:** Drift / sikkerhet

**Bakgrunn:** `login_view` har to rate-limit-dekoratorer:

```python
# accounts/views.py:141–142
@ratelimit(key='post:username', rate='10/5m', method='POST', block=True)
@ratelimit(key='ip',            rate='50/5m', method='POST', block=True)
```

MFA-stegene håndteres **inne i samme view** (`_handle_mfa_setup` og `_handle_mfa_verify`
kalles fra `login_view`, linje 167–172), så dekoratorene kjører også for MFA-POST-ene.
Men MFA-skjemaene sender ingen `username` — de sender `totp_code`, `backup_code` og
`trust_device` (`templates/accounts/mfa_verify.html:38–76`).

`key='post:username'` slår da opp en tom verdi, og **alle MFA-POST-er fra alle brukere
havner i samme bøtte**. Grensen blir 10 MFA-forsøk per 5 minutter *totalt for hele
appen*, ikke per bruker.

Det er et driftsproblem før det er et sikkerhetsproblem: ved vaktstart logger alle på
omtrent samtidig. Er 10 av dem MFA-brukere, får den ellevte 429 og
`accounts/ratelimited.html` — uten at noe er galt med kontoen deres.

I tillegg er MFA-steget det eneste som ikke har noen kontosperre:
`failed_login_attempts` og `locked_until` (`accounts/views.py:236–240`) oppdateres bare i
passord-steget. Feiler man TOTP-koden hundre ganger, skjer det ingenting med kontoen.

**Tiltak:**

1. Bruk en nøkkel som faktisk identifiserer brukeren i MFA-steget. Enkleste vei: gi
   `_handle_mfa_setup`/`_handle_mfa_verify` egne view-funksjoner med egne URL-er og egen
   `@ratelimit(key=...)` basert på sesjonens `mfa_verify_user_id`. Alternativt: legg
   `username` som `<input type="hidden">` i MFA-skjemaene så eksisterende nøkkel virker
   (raskest, men lekker brukernavnet i POST-body).
2. Tell feilede MFA-forsøk på brukeren og gjenbruk 15-minutters-sperren fra passord-steget.
3. Tester: 11 MFA-forsøk fra to ulike brukere skal ikke blokkere hverandre; 5 feilede
   TOTP-forsøk skal låse kontoen.

**Akseptansekriterium:** 20 brukere kan gjøre MFA-verifisering innenfor samme 5-minutters
vindu. Én bruker som gjetter koder blir låst etter 5 forsøk.

---

## N5. `get_active_year()` og `Patient.save()` bruker container-tid

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 30 min &nbsp;|&nbsp; **Type:** Korrekthet

**Bakgrunn:** Dette er nøyaktig samme feilklasse som ble ryddet i FORBEDRINGER #20 —
bare på to steder som slapp unna:

```python
# patients/services.py:130
current = datetime.now().year

# patients/models.py:170
self.year = datetime.now().year
```

`datetime.now()` returnerer naiv container-lokaltid. På Railway er det UTC, uavhengig av
`TIME_ZONE='Europe/Oslo'`. Mellom midnatt og kl. 01:00 norsk vintertid (02:00 sommertid)
er UTC-året fortsatt det forrige.

Praktisk utslag: en nyttårsvakt som registrerer pasienter etter midnatt 1. januar får
`active_year` satt til året som nettopp gikk. Pasientene lagres i feil år, og
listevisningen — som filtrerer på `get_active_year()` — vil være konsistent med seg selv,
så feilen oppdages ikke før noen ser på statistikken i ettertid.

Sanitetsvakter på nyttårsaften er ikke et hypotetisk scenario.

**Tiltak:**

1. Bruk samme mønster som `now_local_str()` i `core/validators.py`:
   ```python
   from django.utils import timezone as djtz
   current = djtz.localtime(djtz.now()).year
   ```
2. Gjør det begge steder. Vurder en liten `core.validators.current_local_year()` slik at
   det finnes ett sted å endre.
3. Test med `@override_settings(TIME_ZONE='Europe/Oslo')` og frosset tid 31.12 kl. 23:30
   UTC → skal gi år+1.

**Akseptansekriterium:** Ingen `datetime.now()` igjen i kode som utleder dato eller år.
Et grep etter `datetime.now()` i `patients/` og `core/` skal komme tomt tilbake.

---

## N6. Statistikk-tabellene setter inn feltverdier uescapet i `innerHTML`

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 2 t &nbsp;|&nbsp; **Type:** Sikkerhet (dybdeforsvar)

**Bakgrunn:** Arkiv-koden i `patients-stats.js` escaper konsekvent (`_escHtml` på linje
956, 1003, 1007–1010). Statistikk-tabellene gjør det ikke:

```javascript
// static/js/patients-stats.js:106 (mkStatsTable)
headers.forEach(h => { html += `<th>${h}</th>`; });
...
html += `<td class="${cls}">${cell}</td>`;

// static/js/patients-stats.js:126 (mkCrosstab)
cols.forEach(c => { html += `<th>${c}</th>`; });
...
html += `<tr><td>${r}</td>`;
```

Rad- og kolonnenøklene her **er** pasientdata: `problemstilling`, `transport`,
`grovsortering`, `utskrevet_til`. Resultatet settes rett inn med `innerHTML`.

Serverside-whitelisten (`patients/choices.py`, GDPR fase 2.1) beskytter alt som kommer
inn via API-et, og er grunnen til at dette ikke er akutt. Men den dekker ikke alle veier
inn i databasen:

- `patients/management/commands/import_offline_data.py:115` bygger `Patient(...)`-objekter
  direkte, uten å kalle `validate_patient_choice_fields`
- `core/backup/service.py` sin restore kjører `loaddata`, som går utenom all validering
- Rader opprettet før whitelisten ble innført er aldri validert

Og CSP-en tillater `unsafe-inline` for `script-src` (`patients/middleware.py:49`), så et
injisert `<img onerror=...>` ville faktisk kjøre. Kombinasjonen «uescapet innsetting +
`unsafe-inline`» er den som gjør dette verdt å rydde i, selv om hver enkelt del isolert
er lavrisiko.

**Tiltak:**

1. Kjør alle nøkler og celleverdier gjennom `_escHtml` i `mkStatsTable`, `mkCrosstab`,
   `mkObsTable` og `mkInterpretation`. Tall trenger ikke escaping, men det koster
   ingenting å være konsekvent.
2. La `import_offline_data` kalle `validate_patient_choice_fields` per rad, med
   `--force`-flagg for bevisst import av gamle data.
3. Ta dette **sammen med F5 (CSP-stramming)** — de to tiltakene forsterker hverandre.

**Akseptansekriterium:** En pasientrad med `problemstilling = '<img src=x onerror=alert(1)>'`
lagt inn direkte i databasen vises som tekst i statistikkfanen, ikke som kjørende kode.

---

## N7. Redis-klienten bygges på nytt for hver eneste request

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 1 t &nbsp;|&nbsp; **Type:** Ytelse

**Bakgrunn:** `_MetricsStore._get_redis_client()` (`patients/middleware.py:159–176`) gjør
dette ved hvert kall:

```python
return redis.Redis.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)
```

`from_url()` lager en **ny `ConnectionPool`** hver gang. Poolen — og dermed
TCP-forbindelsen — gjenbrukes ikke mellom kall. `_record_to_redis()` kalles fra
`record()` for hver eneste request i vakt-modus, og `_read_from_redis()` kalles to ganger
per lasting av admin-status.

Vi betaler altså en TCP-handshake mot Redis per request, for å skrive én metrikk-linje.
Ironien er at metrikkene finnes for å måle ytelse.

**Tiltak:**

```python
_redis_client = None
_redis_client_lock = threading.Lock()

def _get_shared_redis_client():
    global _redis_client
    if _redis_client is None:
        with _redis_client_lock:
            if _redis_client is None:
                url = getattr(settings, 'REDIS_URL', '') or ''
                if not url:
                    return None
                try:
                    import redis
                    _redis_client = redis.Redis.from_url(
                        url, socket_timeout=2, socket_connect_timeout=2,
                    )
                except Exception:
                    return None
    return _redis_client
```

`redis.Redis`-instanser er trådtrygge og har egen intern pool — én per prosess er riktig
mønster. Behold all eksisterende try/except: en død Redis skal fortsatt bare degradere til
lokal deque.

**Merk:** `MetricsRedisAggregeringTests` mocker `_get_redis_client`. Testene må peke på
det nye navnet, og bør nullstille modul-globalen mellom kjøringer.

**Akseptansekriterium:** Antall TCP-forbindelser mot Redis fra én worker er stabilt under
last, ikke proporsjonalt med antall requests.

---

## N8. Audit-signalet gjør N+1 skrivinger per pasientendring

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 1–2 t &nbsp;|&nbsp; **Type:** Ytelse

**Bakgrunn:** `patient_pre_save` (`patients/signals.py:56–91`) gjør per lagring:

1. Én ekstra `SELECT` for å hente forrige tilstand (linje 57)
2. Én separat `INSERT` per endret felt (linje 82)

En typisk PUT der behandler settes utløser samtidig `pabegynt`-stempling og
plasseringsendring — altså 1 SELECT + 3 INSERT + selve UPDATE, fem rundturer til
databasen for én brukerhandling. Ved en travel vakt med hyppige oppdateringer er dette
den mest skrivetunge stien i appen, og den ligger inne i requestens kritiske vei.

Det er heller ingen retention-jobb som kjører (se F2), så tabellen vokser ubegrenset.

**Tiltak:**

1. Samle radene og skriv dem med `AuditLog.objects.bulk_create(rader)`.
   **Viktig:** `bulk_create` kjører ikke `pre_save`, så `app_label` må settes eksplisitt
   på hver rad — `audit.signals.utled_app_label('patients_patient')` gir riktig verdi og
   er allerede offentlig i modulen.
2. `SELECT`-en kan ikke unngås uten større omskriving (Django har ikke gamle verdier i
   `pre_save`). Den er billig; det er skrivingene som er problemet.
3. Verifiser med `assertNumQueries` at en PUT som endrer tre felter gir ett INSERT-kall.

**Akseptansekriterium:** Antall databasespørringer per pasient-PUT er konstant, uavhengig
av hvor mange felter som endres.

---

## N9. Tre tester verifiserer dobbeltklikk-fixen i en død JS-fil

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 30 min &nbsp;|&nbsp; **Type:** Testkvalitet

**Bakgrunn:** `static/js/script.js` lastes ikke av noen mal — `templates/patients/index.html:1018–1022`
laster `patients-utils.js`, `patients-table.js`, `patients-forms.js` og `patients-stats.js`.
At fila skal slettes står allerede i `TODO.md`.

Det som **ikke** står der, er at `DoubleClickGuardTests` (`patients/tests.py:965–995`)
leser og asserter mot nettopp den døde fila:

```python
js_path = Path(settings.BASE_DIR) / 'static' / 'js' / 'script.js'
self.assertIn('async function withSubmitGuard(', content, ...)
self.assertIn("withSubmitGuard('btn-save-new'", content, ...)
```

Testene er grønne. De ville også vært grønne om `patients-utils.js` mistet
`withSubmitGuard` i morgen. Beskyttelsen mot dobbel pasientregistrering — som ble innført
etter en reell hendelse 30. april — er altså i praksis ikke testdekket lenger.

Guarden finnes riktignok fortsatt i den levende koden (`patients-utils.js:41`, brukt fra
`patients-forms.js:21` og `:127`), så det er ingen aktiv feil. Men testene beskytter feil
fil.

**Tiltak:**

1. Pek `DoubleClickGuardTests` mot `patients-utils.js` (helper) og `patients-forms.js`
   (bruksstedene) — i **samme commit** som `script.js` slettes, ellers blir suiten rød.
2. Sjekk samtidig om andre tester leser `script.js`.
3. Vurder generelt om «grep i JS-fil»-tester er riktig verktøy. De gir en påminnelse, ikke
   en garanti. Alternativet er ingen dekning, så behold dem — men kommenter hva de faktisk
   beviser.

**Akseptansekriterium:** Sletter man `withSubmitGuard` fra den levende koden, blir suiten
rød.

---

## N10. Sesjonsinvalidering dekoder hele sesjonstabellen

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 2–3 t &nbsp;|&nbsp; **Type:** Ytelse

**Bakgrunn:** `_invalidate_other_sessions` og `_invalidate_all_sessions`
(`accounts/views.py:38–51`) itererer **alle** ikke-utløpte sesjoner og kaller
`get_decoded()` på hver — det er signaturverifisering og JSON-parsing per rad:

```python
for sess in Session.objects.filter(expire_date__gte=timezone.now()):
    data = sess.get_decoded()
    if str(data.get('_auth_user_id')) == str(user.pk) ...
```

Django har ingen indeks fra bruker til sesjon, så mønsteret er i og for seg det vanlige.
Problemet er hvor det kalles: ved **hver eneste innlogging** (`_do_complete_login`), ved
hver MFA-fullføring, ved passordbytte og ved admin-reset.

Med `SESSION_SAVE_EVERY_REQUEST = True` og 8 timers levetid samler det seg opp sesjoner
gjennom en vakt. Kostnaden treffer nettopp innloggingsstien — den som er travlest de
første ti minuttene av en vakt, når alle logger på samtidig.

`patients/admin_status.py:185–227` har samme mønster, men der er det et admin-verktøy som
kjøres sjelden. Det er akseptabelt.

**Tiltak — to alternativer:**

**A (enkel):** Behold logikken, men kall den kun der den faktisk trengs. Ved ordinær
innlogging er «logg ut mine andre sesjoner» en policy-avgjørelse, ikke en
sikkerhetsnødvendighet — ved passordbytte og admin-reset er den det. Vurder å droppe
kallet i `_do_complete_login`.

**B (grundig):** Før en liten `UserSession(user, session_key, created_at)`-tabell som
skrives ved innlogging. Invalidering blir da ett indeksert oppslag. Krever migrasjon og
opprydding av foreldreløse rader.

**Anbefaling:** A først — den er gratis og fjerner mesteparten av kostnaden. B kun hvis
sesjonstabellen faktisk vokser seg stor.

**Akseptansekriterium:** Innlogging gjør et konstant antall spørringer, uavhengig av
antall aktive sesjoner i systemet.

---

## N11. Dokumentasjonsdrift i `CLAUDE.md`

**Verdi:** Lav–Middels &nbsp;|&nbsp; **Innsats:** 30 min &nbsp;|&nbsp; **Type:** Dokumentasjon

**Bakgrunn:** `CLAUDE.md` er det første både mennesker og verktøy leser. Fire påstander
stemmer ikke lenger med koden:

| Påstand i CLAUDE.md | Faktisk tilstand |
|---|---|
| «Statistikk-caching … Invalideres ved pasientendringer via signal» | `invalidate_stats_cache()` kalles **ikke** fra noen produksjonskode — kun fra tester. Den reelle mekanismen er TTL på 15/60 s. |
| «Backup-innhold er kun `patients`-appen» | Backup er per modul via `core.backup`-handlers. `arkiv` er egen backup-modul siden GDPR fase 3.2. |
| «All backup-logikk ligger i `patients/backup_service.py` og `core/backup/`» | Den levende logikken ligger i `core/backup/`. `patients/backup_service.py` er legacy — jf. TODO-punktet om `patients.BackupConfig` og `db_backup`. |
| «Importér alltid dekoratorer fra `core.auth_decorators` (ikke `accounts.decorators`)» | Tre produksjonsfiler importerer fortsatt fra shimen: `patients/views.py:38`, `core/views.py:24`, `patients/admin_status.py:28`. |

**Tiltak:**

1. Rett de tre første punktene i `CLAUDE.md` — det er dokumentet som er utdatert, ikke
   koden.
2. For det fjerde: bytt de tre importene til `core.auth_decorators` (ren søk-og-erstatt,
   samme objekter), eller bløtgjør regelen til «nye filer skal importere fra core».
   Å ha en regel som kodebasen selv bryter tre steder, er verre enn å ikke ha den.
3. Bestem hva som skal skje med `invalidate_stats_cache()`: enten koble den til
   `patients.signals` (som dokumentasjonen lover), eller fjern funksjonen og rett
   dokumentasjonen. Den korte TTL-en gjør at det siste antagelig er riktig.

**Akseptansekriterium:** Hver påstand i «Arkitektur»-seksjonen i `CLAUDE.md` kan
verifiseres i koden.

---

## N12. `GET /api/settings/` eksponerer hele `AppSetting`-tabellen

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 30 min &nbsp;|&nbsp; **Type:** Dybdeforsvar

**Bakgrunn:**

```python
# patients/views.py:127–129
if request.method == 'GET':
    settings_dict = {s.key: s.value for s in AppSetting.objects.all()}
    return JsonResponse(settings_dict)
```

Enhver innlogget bruker — også `read_only` — får hele nøkkel/verdi-tabellen. I dag ligger
det `event_name`, `event_name_<år>`, `active_year`, `next_patient_nr` og
`feature.live_stats_enabled` der. Ingenting av det er sensitivt.

Men PUT-en rett under har en eksplisitt `allowed = {'event_name'}`-whitelist, mens GET
ikke har noen. `AppSetting` er en generisk nøkkel/verdi-tabell — neste gang noen trenger å
lagre en driftsverdi der, havner den automatisk i responsen til alle. Det er den typen
asymmetri som blir et problem lenge etter at den ble innført.

**Tiltak:** Speil PUT-ens whitelist i GET — returner kun de nøklene frontend faktisk
bruker (`event_name`, `event_name_<aktivt år>`, `active_year`). Legg en kommentar om at
lista skal utvides bevisst.

**Akseptansekriterium:** En ny `AppSetting`-nøkkel er ikke synlig via API-et før noen
eksplisitt legger den til i whitelisten.

---

## N13. Duplisert kode i `views.py` og `services.py`

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 3–4 t &nbsp;|&nbsp; **Type:** Vedlikehold

**Bakgrunn:** Tre konkrete dubletter, alle av typen «kopiert og lett tilpasset»:

1. **ETag-blokken for navnelister.** `forstehjelpere_view` (`patients/views.py:414–430`) og
   `helsepersonell_view` (`:492–508`) er ord for ord like bortsett fra modellnavnet. Det
   samme gjelder `forstehjelper_detail_view` (`:448–481`) og `helsepersonell_detail_view`
   (`:526–558`) — inkludert `ProtectedError`-håndteringen. To modeller med identisk form
   (`name`, `user`, `is_active`), fire views.

2. **Feltlista for arkiverte pasienter.** De samme 17 feltnavnene er skrevet ut tre steder:
   `patients/views.py:748–752`, `patients/services.py:786–791` og `:803–808`. Legger noen
   til et felt på `ArkivertPasient` og glemmer ett av stedene, blir SHA-256-verifikasjonen
   inkonsistent med det som faktisk arkiveres — og arkivet melder «tukling» uten at noe har
   skjedd.

3. **`patients/views.py` er 815 linjer** og dekker pasient-CRUD, to navneregistre, arkiv,
   statistikk og nullstilling. Fila er velkommentert og lesbar, men ansvarsflaten er bred.

**Tiltak:**

1. Trekk feltlista ut som `ARKIVERT_PASIENT_FELTER` i `patients/services.py` og bruk den
   alle tre stedene. **Dette punktet alene er verdt tiden** — det er det eneste som kan gi
   feil oppførsel.
2. Lag en generisk `_navneliste_view(model, label)`-fabrikk for de fire
   førstehjelper/helsepersonell-viewene.
3. Vurder å splitte `views.py` i `views_patients.py`, `views_registre.py`, `views_arkiv.py`
   og `views_stats.py`. Ingen hast — gjør det når fila neste gang skal endres substansielt.

**Akseptansekriterium:** Et nytt felt på `ArkivertPasient` krever endring ett sted.

---

# Del 2 — Sikkerhetsgjennomgang

Eget pass over autentisering, autorisasjon, endepunktdekning og de administrative
flatene. N1 (åpen redirect), N4 (MFA-rate-limit) og N6 (uescapet `innerHTML`) hører
tematisk hjemme her, men er beskrevet i Del 1.

## S1. `/django-admin/` omgår samtlige av appens innloggingssikringer

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 1–2 t

**Bakgrunn:** Appen har bygget et gjennomtenkt forsvar rundt innlogging i
`accounts/views.py`: rate-limiting per brukernavn og per IP, kontosperre etter 5 feilede
forsøk, tvungen MFA for brukere med `mfa_required`, tvungen passordbytte, og `LoginEvent`
for hver eneste hendelse.

**Alt dette sitter på `accounts.views.login_view`.** Ved siden av står en helt egen
innloggingsflate som ikke har noe av det:

```python
# myproject/urls.py:24
path('django-admin/', admin.site.urls),
```

Dette er Djangos standard `AdminSite`, ikke `django_otp.admin.OTPAdminSite`. Den har sitt
eget innloggingsskjema på `/django-admin/login/`. Konsekvensene, punkt for punkt:

| Sikring | `/accounts/login/` | `/django-admin/login/` |
|---|---|---|
| Rate-limiting (10/5m per bruker, 50/5m per IP) | ✅ | ❌ ubegrenset |
| Kontosperre (5 forsøk → 15 min låst) | ✅ | ❌ telleren røres ikke |
| MFA-tvang ved `mfa_required=True` | ✅ | ❌ kun passord |
| Tvungen passordbytte | ✅ | ❌ eksplisitt unntatt |
| `LoginEvent`-logging | ✅ | ❌ ingen spor |

At `django_otp.middleware.OTPMiddleware` står i `MIDDLEWARE` hjelper ikke — den setter kun
`request.user.otp_device`, den håndhever ingenting. `mfa_required` sjekkes utelukkende i
`login_view:208`.

Unntaket for passordbytte er eksplisitt: `/django-admin/` står i
`MustChangePasswordMiddleware.ALLOWED_PATHS` (`accounts/middleware.py:17`).

Og bak flaten ligger alt: `Patient` (`patients/admin.py:16`), `CustomUser`
(`accounts/admin.py:83`), `AuditLog`, `AppSetting`, `ModuleSettings`. En angriper som
kommer inn her har pasientjournaler og full brukeradministrasjon.

Flaten krever `is_staff`, så den gjelder i praksis bootstrap-adminen — se S2, som gjør
akkurat den kontoen ekstra utsatt.

**Én ting er i orden:** pasientendringer gjort via Django admin blir audit-logget.
Signalet i `patients/signals.py` er entry-point-agnostisk og
`RequestAuditMiddleware` setter thread-local også for admin-requests. Det er
*innloggingen* som ikke logges, ikke endringene.

**Tiltak — velg én:**

1. **Slå av Django admin i produksjon** (renest). Portalen har allerede egne flater for
   det admin trenger: `/portal-admin/moduler/`, `/portal-admin/auditlog/`,
   `/portal-admin/backup/`, `/accounts/users/` og `/portal-admin/server-status/`. Behold
   `/django-admin/` bak `if DEBUG or OFFLINE_MODE`. Sjekk først om noe i RUNBOOK-en
   forutsetter den.
2. **Krev OTP på admin-flaten** (minst inngripende):
   ```python
   from django_otp.admin import OTPAdminSite
   admin.site.__class__ = OTPAdminSite
   ```
   Da må superbrukeren ha en bekreftet TOTP-enhet. NB: dette låser deg ute hvis
   bootstrap-adminen ikke har satt opp MFA ennå — gjør oppsettet via `/accounts/login/`
   først.
3. **Som minimum:** legg `@ratelimit` på admin-login og fjern `/django-admin/` fra
   `ALLOWED_PATHS`.

**Anbefaling:** Alternativ 1. En innloggingsflate som ingen bruker, men som omgår alle
sikringene, er ren nedside.

**Akseptansekriterium:** Det finnes én vei inn i systemet, og den har rate-limiting,
kontosperre, MFA-tvang og hendelseslogging.

---

## S2. `create_superuser` setter `must_change_password=False`

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 15 min

**Bakgrunn:**

```python
# accounts/managers.py:29
extra_fields.setdefault('must_change_password', False)
```

Modellens eget default er `True` (`accounts/models.py:41`) — hver vanlig bruker må bytte
passord ved første innlogging. Superbrukere er unntatt.

`create_admin`-kommandoen kjøres i release-fasen ved **hver deploy**, med passordet fra
`DJANGO_SUPERUSER_PASSWORD` (se FORBEDRINGER #17 om Custom Start Command). Kommandoen er
idempotent og hopper over hvis brukeren finnes, så passordet settes kun første gang — men
det betyr også at kontoen kan gå i årevis på det opprinnelige deploy-passordet, uten at
noe i systemet ber om noe annet.

Passordet står dessuten som klartekst i miljøvariablene, og siden det ligger på
kommandolinjen til `create_admin` er det synlig i prosessliste og deploy-logg.

Kombinert med S1: den ene kontoen med mest tilgang har både den svakeste
innloggingsstien og det passordet som er minst sannsynlig at noen har byttet.

**Tiltak:**

1. Fjern linjen. La superbrukere arve modellens `must_change_password=True`.
   `create_superuser` brukes kun av `create_admin` og av `manage.py createsuperuser` —
   begge er bootstrapping der tvungent bytte er nøyaktig riktig oppførsel.
2. Verifiser at bootstrap-adminen i prod faktisk har byttet passord siden opprettelsen
   (`last_login_at` og feltet `must_change_password` i Django admin, eller via `shell`).
3. Vurder å sette `mfa_required=True` på alle admin-kontoer.

**Merk:** Fjernes linjen uten at S1 er løst, får det ingen effekt for den kontoen — den
kan fortsatt logge inn på `/django-admin/`, som er unntatt fra kravet. Punktene henger
sammen og bør tas samlet.

**Akseptansekriterium:** En nyopprettet superbruker blir sendt til passordbytte ved
første innlogging, uansett hvilken flate hen bruker.

---

## S3. Rate-limiting finnes kun på innlogging

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 2 t

**Bakgrunn:** `@ratelimit` forekommer nøyaktig to steder i kodebasen, begge på
`login_view` (`accounts/views.py:141–142`). Ingen andre endepunkter har noen form for
struping:

- `POST /pasienter/api/patients/` — en innlogget `read_write`-bruker (eller en stjålet
  sesjonscookie) kan opprette pasienter i en løkke så fort serveren rekker. Uten F3
  (idempotency) finnes det ingen bremse i det hele tatt.
- `POST /accounts/change-password/` — ingen struping på gjetting av `old_password`.
- `GET /pasienter/api/full-stats/` — den dyreste spørringen i appen (scipy-beregninger
  over hele årets datasett). Cachet 60 s, så en enkelt bruker gjør lite skade, men
  cache-miss-stien er ubeskyttet.
- `GET /portal-admin/auditlog/eksport.csv` — 5000 rader per kall, ubegrenset antall kall.

Dette er et lavere prioritert punkt fordi alle endepunktene krever innlogging, og
brukergruppen er liten og kjent. Men appen har allerede `django-ratelimit` installert og
en nødbryter (`RATELIMIT_ENABLE`), så kostnaden ved å dekke skriveendepunktene er lav.

**Tiltak:**

- Legg `@ratelimit(key='user', rate='60/m', method='POST', block=True)` på
  pasient-skriveendepunktene. 60/min er langt over reell bruk under vakt, men stopper en
  løpsk klient.
- Strengere grense på `change_password_view` (f.eks. `10/5m` per bruker).
- Husk at rate-limiting med LocMemCache er per prosess. I lavkostnad-modus (1 worker) er
  det riktig; i vakt-modus deles telleren via Redis.

**Akseptansekriterium:** Ingen autentisert bruker kan generere ubegrenset skrivelast mot
databasen.

---

## S4. Lagret open redirect i varsel-visningen

**Verdi:** Lav–Middels &nbsp;|&nbsp; **Innsats:** 15 min

**Bakgrunn:**

```python
# core/views.py:612–613
target_url = notif.url or '/varsler/'
return redirect(target_url)
```

`notification_mark_read_view` godtar GET (bevisst, så vanlige `<a>`-lenker virker) og
redirecter til `Notification.url` uten validering. Feltet er `CharField(max_length=500)`
uten validator (`core/models.py:280`).

I dag er dette **ikke utnyttbart**: `notify()` kalles kun fra `patients/signals.py:184`
med hardkodede relative URL-er. Men `core.notifications.notify()` er eksplisitt designet
som et generisk API for framtidige moduler («vakter, utstyr, beredskap»), og docstringen
inviterer til bruk. Første modul som lar brukerinput påvirke `url` gjør dette til en
ekte open redirect — med en lenke som ser ut til å komme fra portalen selv.

**Tiltak:** Bruk samme `_safe_next()`-helper som N1 innfører, eller valider enklere: krev
at `url` starter med `/` og ikke med `//`. Gjør det begge steder — også i
`notification_mark_read_view` sin JSON-variant hvis den senere begynner å redirecte.

Ta det sammen med N1 — det er samme fix, og da blir det ett mønster i kodebasen.

**Akseptansekriterium:** En `Notification` med `url='https://evil.example/'` sender
brukeren til `/varsler/`, ikke ut av appen.

---

## S5. Utlogging skjer via GET

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 30 min

**Bakgrunn:** `logout_view` (`accounts/views.py:394`) har ingen metode-restriksjon, og
malene lenker til den med en vanlig `<a href>` (`templates/base.html:64`,
`templates/patients/index.html:87`). Enhver side på internett kan logge ut brukeren vår
med `<img src="https://<app>/accounts/logout/">`.

Konsekvensen er irritasjon, ikke datatap — men midt i en vakt er det ikke ingenting, og
Django 5 fjernet GET-utlogging fra sin egen `LogoutView` nettopp av denne grunn.

**Tiltak:** Gjør `logout_view` til `@require_POST` og bytt lenkene til et lite skjema med
CSRF-token (Bootstrap-dropdown tåler en `<button type="submit" class="dropdown-item">`
fint). Sjekk om noen tester treffer utloggings-URL-en med GET.

**Akseptansekriterium:** `GET /accounts/logout/` gir 405. Utloggingsknappen virker som
før.

---

## S6. MFA trust-cookie settes med `secure=True` i offline-modus

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 15 min

**Bakgrunn:**

```python
# accounts/views.py:376
is_secure = not getattr(django_settings, 'DEBUG', True)
```

Offline-modus kjører bevisst `DEBUG=False` uten TLS (`settings.py:49–53`). `is_secure`
blir da `True`, cookien settes med `Secure`-flagget over ren HTTP, og nettleseren kaster
den. «Stol på denne enheten» virker altså ikke i felt — brukeren må taste TOTP-kode hver
gang, uten at noe forteller hvorfor.

Dette er en funksjonell feil med sikkerhetsfortegn, ikke et hull: feilen går i sikker
retning. Men det er nøyaktig samme feilklasse som `_HTTPS_ENABLED` allerede løser andre
steder i `settings.py` — offline-modus er unntaket som `not DEBUG` ikke fanger.

**Tiltak:** Bruk `request.is_secure()` (som tar hensyn til `SECURE_PROXY_SSL_HEADER` og
dermed er riktig både på Railway og offline), eller gjenbruk `_HTTPS_ENABLED`-logikken.
Samme sjekk bør gjennomgås for andre `set_cookie`-kall.

**Akseptansekriterium:** Trust-cookien lagres og virker i offline-modus, og har fortsatt
`Secure` i produksjon.

---

## S7. Personverndokumentasjonen påstår kontroller som ikke er reelle i dag

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 1 t

**Bakgrunn:** `PERSONVERN_DOKUMENTASJON.md` er ikke bare intern prosa — A.10 er
behandlingsprotokollen etter GDPR art. 30, og ansvarlighetsprinsippet i art. 5(2) krever
at vi kan *demonstrere* at tiltakene vi lister faktisk er på plass. Fire punkter i
dokumentet stemmer ikke med koden slik den er i dag:

| Påstand | Hvor | Faktisk tilstand |
|---|---|---|
| «Alle pasient-endringer logges på felt-nivå» (A.10) | `patient_pre_save` | `helsepersonell_ref_id` mangler i `felt_to_track` — se N2. Endring av oppfølgingsansvarlig etterlater ingen spor |
| Lagringstid 730 dager (logger) / 30 dager (varsler) (A.9) | `purge_old_logs` | Kommandoen finnes og er komplett, men er aldri satt opp som cron-jobb — se F2. De dokumenterte fristene håndheves ikke |
| «manuell `escapeHtml()` i JavaScript» (A.10, §7.9) | statistikk-tabellene | `mkStatsTable`/`mkCrosstab`/`mkObsTable` setter feltverdier uescapet i `innerHTML` — se N6. Referansen i dokumentet stemmer for arkiv-visningen, ikke for statistikkfanen |
| «Passord-hashing (argon2 / PBKDF2)» (§7.1) | `settings.py` / `requirements.txt` | Argon2 er ikke installert. A.10 sier dette riktig («Argon2 er ikke installert i dag»), §7.1 i teknisk dokumentasjon sier det feil |

Det mest alvorlige er lagringstidene. Dokumentet beskriver overfor de registrerte (del B)
og overfor tilsynsmyndighet (del A) en slettepraksis som ikke finner sted i produksjon.
Det er forskjellen mellom en dokumentert kontroll og en reell kontroll — og det er
nøyaktig den forskjellen art. 5(2) ber oss unngå.

**Tiltak:**

1. **Rett koden, ikke dokumentet, for N2 og F2** — de er reelle mangler (se egne punkter).
   Når de er lukket, blir påstandene sanne igjen uten at teksten må endres.
2. **Rett dokumentet for de to andre:** presiser i A.10/§7.9 at `escapeHtml()`/`_escHtml`
   dekker arkiv-visningen og pasientskjemaet, ikke (ennå) statistikk-tabellene — inntil N6
   er lukket. Rett §7.1 til å matche A.10s mer presise formulering om Argon2.
3. Legg inn en enkel rutine: hver gang et FORBEDRINGER-punkt lukkes som direkte motsier en
   påstand i personverndokumentasjonen, sjekk om dokumentet må oppdateres i samme runde.
   Ingen slik kobling finnes i dag — det er sånn disse fire oppsto.

**Akseptansekriterium:** Hver påstand i A.9, A.10 og kapittel 7 i teknisk dokumentasjon
kan verifiseres direkte mot kjørende kode. Ingen krysser N2 eller F2 av som løst uten å
sjekke om personverndokumentasjonen fortsatt er korrekt.

---

## Kontrollert og funnet i orden

Notert her så det ikke revideres på nytt neste gang:

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

---

# Del 3 — Overført fra FORBEDRINGER.md

Disse punktene sto fortsatt åpne i mai-dokumentet og er flyttet hit uendret i innhold.
Der gjennomgangen i august har avdekket noe nytt om punktet, er det notert som
**Oppdatering august 2026**.

---

## F1. E-postvarsel ved kritiske feil (uten Sentry)

*Opprinnelig FORBEDRINGER #2 → senere #3*

**Verdi:** Høy &nbsp;|&nbsp; **Innsats:** 2–3 timer

**Bakgrunn:** Sentry ble fjernet fra prosjektet etter brukerens ønske. Dermed har vi ikke
lenger automatisk varsel ved 500-feil i prod. RUNBOOK §13 dekker manuell feilsøking, men
proaktiv varsling mangler.

**Tiltak:**

- Konfigurer Djangos innebygde `AdminEmailHandler` i `LOGGING`-blokken i `settings.py`.
- Legg til `ADMINS = [('André', 'andre.eritsland@gmail.com')]`.
- SMTP via Railway-variabler: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`. Bruk f.eks. SendGrid free tier (100 mail/dag).
- Throttling: filter på logging slik at én feil-burst ikke spammer 200 mailer. Begrens til
  én mail per feiltype per 15 min.
- Test ved å simulere en 500 i staging.

**Oppdatering august 2026:** **Ta N3 først.** `LOGGING`-blokken må uansett bygges om for å
få en fungerende rot-logger, og `AdminEmailHandler` hektes naturlig på i samme runde.
Gjøres N3 og F1 hver for seg, skrives den samme blokken om to ganger.

**Akseptansekriterium:** Når en uhåndtert exception kastes i prod, mottas e-post med
stacktrace innen 1 minutt. Maks 1 mail per 15 min for samme feiltype.

---

## F2. Automatisert audit-purge i scheduler/cron

*Opprinnelig FORBEDRINGER #13*

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 1–2 timer

**Bakgrunn:** `purge_old_logs`-kommandoen kjører ikke automatisk. `AuditLog` vokser
ubegrenset til noen kjører kommandoen manuelt.

**Oppdatering august 2026:** Kommandoen finnes og er komplett —
`audit/management/commands/purge_old_logs.py`, med `--days` (default 730),
`--notification-days` (default 30) og `--dry-run`. Docstringen sier at den «kjøres av
Railway Cron», men det er ikke satt opp. Tre tabeller vokser derfor uten tak: `AuditLog`,
`LoginEvent` og `core.Notification`.

Dette er ikke bare et diskspørsmål. `GDPR_TILTAKSPLAN.md` og
`PERSONVERN_DOKUMENTASJON.md` A.9 fastsetter 730 dager for logger og 30 dager for varsler
som **våre dokumenterte lagringstider**. Uten en jobb som håndhever dem, er de en påstand
vi ikke oppfyller. Sammen med N8 (én audit-rad per endret felt) vokser tabellen fortere
enn man skulle tro.

Merk at det allerede finnes et beslektet, åpent TODO-punkt: cron for `kollaps_arkiv`
(`docs/OPPSETT_KOLLAPS_CRON.md`). De to jobbene bør settes opp i samme runde — samme
mekanisme, samme verifisering.

**Tiltak:**

- Sett opp Railway Cron Job: `0 3 1 * *` (månedlig, 03:00 UTC den 1.) som kjører
  `python manage.py purge_old_logs`.
- Alternativt: scheduler-middleware som kjører purge én gang per døgn (samme mønster som
  `BackupSchedulerMiddleware`).
- Logg purge-resultatet (antall slettede rader) — forutsetter N3.
- Gjør det sammen med `kollaps_arkiv`-cronen.

**Akseptansekriterium:** Audit-tabellen vokser ikke ut over forventet rate. Begge
purge-jobbene er synlige i Railway Cron Jobs, og `OPPSETT_KOLLAPS_CRON.md` kan slettes.

---

## F3. Server-side idempotency for pasient-opprettelse (Fix B)

*Opprinnelig FORBEDRINGER #18*

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 2–3 timer

**Bakgrunn:** 30. april 2026 ble en pasient registrert dobbelt opp på Grønn sone i prod
fordi brukeren dobbeltklikket på «Registrer pasient» før serveren rakk å svare. På delte
soner (Grønn/Gul/blank plassering) finnes ingen unik-sjekk, så begge requests gikk gjennom.

**Fix A (frontend, implementert):** `withSubmitGuard()` disabler knappen umiddelbart, viser
spinner og holder lock i minst 250 ms.

**Fix A's begrensninger:** beskytter ikke mot API-klienter (Postman, curl), ikke mot to
nettleserfaner med samme skjema, og ikke mot automatisk nettverks-retry.

**Tiltak — Fix B (server-side idempotency-token):**

- Frontend genererer `crypto.randomUUID()` når nytt-pasient-skjemaet åpnes, og sender den
  som `idempotency_key` i POST-body.
- Backend slår opp `patient_create:{user.id}:{key}` i cache før opprettelse. Treff →
  returner samme respons som første gang (status 200, ikke 201).
- Lagre responsen under nøkkelen i 5 minutter.
- Race-håndtering: `cache.get()` + `cache.set()` er ikke atomisk. Bruk `cache.add()`
  (atomisk, returnerer False hvis nøkkelen finnes) som lås.

**Tester:** samme token gir én pasient; token utløper etter 5 min; klienter uten token får
dagens oppførsel; tokens er isolert per bruker; to samtidige requests med samme token gir
én pasient.

**Risiko:** Krever Redis (finnes i vakt-modus, men **ikke** i lavkostnad-modus — der er
cachen per prosess, så beskyttelsen gjelder kun innen én worker). Cache-feil må falle
tilbake til «opprett uansett» — bedre dobbel registrering enn ingen registrering.

**Oppdatering august 2026:** `withSubmitGuard` ligger nå i `patients-utils.js:41`, ikke i
`script.js`. Se N9 — testene som skal beskytte Fix A peker fortsatt på den døde fila.

**Akseptansekriterium:** To raske POST-er fra samme bruker med samme `idempotency_key`
skaper kun én pasient. Andre POST returnerer samme pasientdata med status 200.

---

## F4. Lasttest-script før stor vakt

*Opprinnelig FORBEDRINGER #7*

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 3–4 timer

**Bakgrunn:** Det er foreslått en lasttest før første vakt med 15–20 brukere for å
verifisere at Redis + 2 workers + 4 tråder faktisk holder forventet last.

**Tiltak:**

- `locust` eller et enklere script som simulerer: 20 samtidige innloggede brukere;
  polling av pasientliste hvert 30. sekund; 5 brukere oppretter pasient hvert 2. minutt;
  2 brukere endrer en eksisterende pasient hvert minutt.
- Kjør mot staging (eller et midlertidig miljø likt prod).
- Sjekk: gj.snitt responstid < 500 ms, ingen 5xx, cache-hit-ratio i admin-dashbord, minne
  og CPU i Railway-metrics.

**Oppdatering august 2026:** Ta N4 med i testplanen. Rate-limit-bøtta som deles av alle
MFA-forsøk er nettopp den typen feil en lasttest ville avdekket — og som ellers først
oppdages under en reell vaktstart.

**Akseptansekriterium:** Rapport som viser at konfigurasjonen tåler 25 samtidige brukere
uten degradering.

---

## F5. CSP-stramming

*Opprinnelig FORBEDRINGER #8*

**Verdi:** Middels &nbsp;|&nbsp; **Innsats:** 2 timer

**Bakgrunn:** CSP-en i `SecurityHeadersMiddleware` (`patients/middleware.py:47–59`) bruker
`'unsafe-inline'` for både `script-src` og `style-src`. Kommentaren i koden begrunner det
med at all brukerdata escapes med `escapeHtml()` før innsetting i DOM.

**Oppdatering august 2026:** Den begrunnelsen holder ikke fullt ut — se N6.
Statistikk-tabellene escaper ikke. Så lenge begge deler står, mangler vi begge lagene
samtidig.

I tillegg har `templates/patients/index.html` rundt 30 inline `onclick=`-handlere. De må
flyttes til `addEventListener` før `unsafe-inline` kan fjernes fra `script-src` — det er
mesteparten av arbeidet i dette punktet.

**Tiltak:**

- Audit dagens CSP. Sjekk om Tabulator og Chart.js krever `unsafe-inline`.
- Innfør nonce for de gjenværende inline-scriptene via en template tag.
- Flytt `onclick="..."` til `addEventListener` i JS-modulene.
- Test i alle nettlesere brukerne benytter (Chrome, Edge, Safari iOS).
- Ta N6 i samme runde.

**Akseptansekriterium:** CSP-headeren inneholder ikke `unsafe-inline` for `script-src`.
Manuell QA på alle hovedflyt.

---

## F6. Statistikk-utvidelse (live-dashbord + utvidet analyse)

*Opprinnelig FORBEDRINGER #12*

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 25–35 timer totalt, faseinndelt

Dette er den største enkeltforbedringen i backloggen. Den er forankret i to tidligere
dokumenter: `STATISTIKK_ANALYSE_FORSLAG.md` og `STATISTIKK_IMPLEMENTERINGSPLAN.md`.

Forbedringen deles i to leveranser med ulik personvernprofil, som kan deployes uavhengig:
**(a) live-statistikk for alle innloggede** og **(b) utvidet evalueringsstatistikk for
admin/lead**.

### Tilgangsmodell

| Endepunkt | Tilgang | Innhold | Polling |
|---|---|---|---|
| `/api/stats/` | Alle innloggede | Header-chips (eksisterende) | 30 s |
| **`/api/stats/live/`** (NY) | Alle innloggede | A1–A4 (operativ sanntid) | 30–60 s |
| `/api/full-stats/` | admin/lead/lead_view | B1–B6, C1–C2, D1–D5 | 60–120 s |

**Rasjonale:** Live-data er aggregert og operativt — alle på vakt har nytte av
kø-situasjonen. Full-stats inneholder personvernfølsomme krysstabeller og evalueringsdata
som krever fagansvar.

### (a) Live-dashbord — A-nivå

- **A1 Samtidighetskurve** — 15-min buckets, event-basert sweep O(n log n), per-triage-fordeling + peak. Chart.js stacked area.
- **A2 Tid-til-behandler** — fra `inntid` til behandler er tildelt. Vi har ikke timestamp på FK-en, men `AuditLog` har det: første rad med `field_name='forstehjelper_id'` og ikke-tom `new_value`. Output `{n, mean, median, p90, per_triage}`.
- **A3 Gjennomstrømning** — `utskrevet` og `inntid` bucket per time, to serier + akkumulert netto-gap.
- **A4 Flaskehalsindikator** — tre reelle tilstander blant `utskrevet=''`: venter behandling, under behandling, på obspost. Horisontal stacked stolpe + heuristiske varsler.

### (b) Utvidet evaluering — B/C/D-nivå

- **B1** Utfallsfordeling (stacked bar først, Sankey senere) · **B2** Behandler-produksjon, **aggregert med k≥3** · **B3** Plasseringsbelastning · **B4** Årsak × Problemstilling · **B5** Medisiner og lege-konsultasjoner · **B6** Journal-rate
- **C1** Boxplot (`chartjs-chart-boxplot`, ~8 KB) · **C2** Persentiler P50/P90/P95 i `sd()`
- **D1** Dunn post-hoc (egen 30-linjers implementasjon, ikke `scikit-posthocs`) · **D2** Effektstørrelser (Cramér's V, Epsilon²) · **D3** Konfidensintervall (Wilson, bootstrap) · **D4** Fisher's exact for 2×2 · **D5** Forbedret automatisk tolkning som kombinerer p-verdi, effektstørrelse og n

### Faseinndeling

| Fase | Innhold | Estimat |
|---|---|---|
| 1 — Infrastruktur | `services_stats_live.py`, cache-wrapper, cache-invalidering, tomt `/api/stats/live/`, AuditLog-indeks, smoke-tester | 4–6 t |
| 2 — Live-dashbord | A1–A4 + «Sanntid»-fane for alle, Chart.js-rendering, tester | 6–8 t |
| 3 — B/C-utvidelser | B1–B6, C1, C2 | 6–8 t |
| 4 — Statistiske tester | D1–D5 + 7 nye krysstabeller | 4–6 t |
| 5 — Test og personvern | Alle tester grønne, oppdater personvern- og teknisk dokumentasjon | 3–4 t |
| 6 — Deploy og overvåkning | Deploy, overvåk CPU/RAM første uke, juster cache-TTL | 1–2 t |

### Kritiske forbehold

1. **B2 må personvernvurderes.** Selv aggregert behandlerstatistikk kan re-identifisere ved få behandlere. Krev k≥3, ingen histogrammer som kan lekke.
2. **Invester i caching fra dag 1.** Forskjellen på elegant løsning og Railway-overraskelse på regningen.
3. **Hopp over Sankey i første versjon.** Stacked bar gir 80 % av verdien for 10 % av kompleksiteten.
4. **Merk «lite datagrunnlag» når n < 30.**
5. **Lasttest etter fase 2** (se F4) før fase 3 deployes.

### Åpne avklaringer

1. Bekreft tilgangsmodellen i tabellen over.
2. Sankey eller stacked bar for B1? (Anbefaling: stacked bar.)
3. Er B2 OK med k≥3-aggregat, eller utelates den inntil den er drøftet med verneombud?
4. Hvilken fase startes med? (Anbefaling: fase 1 + smal fase 2 med kun A1 og A4, for å se reell CPU-påvirkning.)
5. Polling-frekvens for live-fanen ved 20+ samtidige brukere: 30 s eller 60 s?

**Oppdatering august 2026:** To ting å ta hensyn til hvis dette startes.

- **Live-stats-flagget finnes allerede** som `feature.live_stats_enabled` i
  `patients/admin_status.py:40–41`, med default `'false'` nettopp fordi funksjonen ikke er
  bygget. Flytt defaulten til `'true'` i samme commit som leverer fase 2 — kommentaren i
  koden ber eksplisitt om det.
- **A2 avhenger av audit-loggen** for å utlede tildelingstidspunkt. Da bør N2 være løst
  først, ellers dekker A2 kun førstehjelper og ikke helsepersonell. Og F2 må settes opp
  med en retention som er lengre enn analysevinduet — det nytter ikke å regne på data
  purge-jobben nettopp slettet.

**Akseptansekriterium:** Live-dashbord (fase 1+2) deployet, alle innloggede ser
«Sanntid»-fanen, A1–A4 oppdateres uten manuell refresh. CPU-bruk ikke mer enn +10 % fra
baseline med 20 brukere på fanen. Cache-hit-ratio > 80 % under aktiv vakt.

---

## F7. Frontend bundle-størrelse / lazy loading

*Opprinnelig FORBEDRINGER #9*

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 4–6 timer

**Bakgrunn:** Frontend lastes i sin helhet ved hvert sidebesøk. På mobil over 4G kan
første-paint være treg.

**Oppdatering august 2026:** Premisset er delvis innfridd. Monolitten er splittet i fire
filer (`patients-utils` 247, `patients-table` 312, `patients-forms` 255, `patients-stats`
1086 linjer), men **alle fire lastes ubetinget** i `index.html:1018–1021`. Så det er fire
requests i stedet for én, ikke mindre kode.

Det reelle potensialet ligger i `patients-stats.js` — den er større enn de tre andre til
sammen og brukes kun av admin/lead/lead_view. En `read_only`-bruker laster i dag hele
statistikk-modulen uten å kunne åpne den. Betinget lasting basert på rolle er en liten
endring med målbar effekt, og enklere enn generell code splitting.

Mål først: `script.js` (2159 linjer) skal uansett slettes (TODO + N9), så tallene bør tas
etter det.

**Tiltak:**

- Mål bundle-størrelse og Time to Interactive på mobil.
- Last `patients-stats.js` kun for roller som har statistikktilgang.
- Vurder dynamisk `import()` for admin-funksjoner.

**Akseptansekriterium:** Første-paint på mobil 4G < 1,5 s. Read-only-brukere laster < 50 %
av admin-bundlen.

---

## F8. PgBouncer / Postgres connection pooler

*Opprinnelig FORBEDRINGER #10*

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 2–3 timer

**Bakgrunn:** Med `WEB_WORKERS=2` og `WEB_THREADS=4` kan vi i verste fall ha 8 samtidige
Postgres-forbindelser per app-instans. Skalerer vi til 4 workers blir det 16. Railway
Hobby Postgres har ~100 forbindelser, så dette er ikke akutt — men en pooler reduserer
presset.

**Tiltak:**

- Vurder `pgbouncer-railway` (community service), eller connection pooling-parametre via
  `dj-database-url`.
- Test grundig at sesjons-pooling fungerer med Django (transaksjoner!).

**Oppdatering august 2026:** `conn_max_age=600` er allerede satt (`settings.py:165`), så
forbindelser gjenbrukes i 10 minutter per worker. Det demper problemet ytterligere. Merk
også at `BackupSchedulerMiddleware` starter en **bakgrunnstråd** som gjør DB-arbeid
(`backup_scheduler.py:189`) — den tråden tar sin egen forbindelse utenom
worker/thread-regnestykket. Ikke mye, men verdt å ha med når man dimensjonerer.

**Merk:** Kun relevant ved 4+ workers. Ikke prioriter før vi faktisk skalerer.

**Akseptansekriterium:** Antall åpne Postgres-forbindelser fra app-instansen ≤ 4 ved 16
inngående requests.

---

## F9. Kolonne-kryptering for følsomme felter

*Opprinnelig FORBEDRINGER #14*

**Verdi:** Lav &nbsp;|&nbsp; **Innsats:** 8–12 timer

**Bakgrunn:** Pasientdata lagres i klartekst i Postgres. Kryptering at-rest leveres av
Railway på disknivå, og kryptering i transitt er TLS. Feltnivå-kryptering (f.eks.
`django-encrypted-fields`) ville gitt ekstra forsvar mot eksponering av en DB-dump, men er
kompleks: spørringer, indekser og nøkkelrotasjon blir alle vanskeligere.

**Tiltak:** Kun ved skjerpet trusselbilde eller eksplisitt krav. Innfører betydelig
vedlikeholdslast.

**Oppdatering august 2026:** Verdien har gått ytterligere ned. GDPR fase 3.1 gjør at
arkiverte pasientrader kollapser til aggregat etter 24 måneder, så mengden helsedata som
faktisk ligger lagret over tid er kraftig redusert. Det er den mekanismen som bærer
dataminimeringen nå — ikke kryptering.

**Akseptansekriterium:** Ikke prioritert.

---

> **Vedlikehold av dette dokumentet:** Når et punkt er gjennomført, flytt det til
> «Avsluttede»-tabellen nederst i [`FORBEDRINGER.md`](./FORBEDRINGER.md) med en kort
> statusnotis, og stryk raden i matrisen her. Nye forslag legges til her med rangering.
> Hold lista kort — kun det som faktisk vurderes.
