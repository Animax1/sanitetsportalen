# Sikkerhetsgjennomgang 13. september 2026

Statisk gjennomgang av koden på `rollemodell` (`de2b834`), i fire deler: transport og
konfigurasjon, innlogging og kontohåndtering, tilgang på objektnivå, og inndata/utdata/
avhengigheter. Hvert funn under er lest opp mot koden før det ble tatt med. Den dynamiske
delen kjøres mot staging med `scripts/sikkerhetssjekk.py` (runbook §14) og rapporteres
separat.

**Ingen kritiske funn.** Kjernen holder: tilgangsmodellen håndheves der CLAUDE.md sier den
skal, CSRF dekker alle skriveendepunkter, det finnes ingen SQL- eller kommandoinjeksjon,
`next` valideres, hemmeligheter ligger ikke i repoet, og cookies, HSTS og de andre hodene
står riktig. Funnene er hull i kantene — og to av dem er reelle veier inn for en som alt
har en konto.

## Høy

### H1. Lagret JS-injeksjon gjennom verdimengdene i oppdrag, og CSP-en stopper den ikke
`templates/oppdrag/sentral.html:319-324`, `templates/oppdrag/enhet.html:76-83`,
`oppdrag/views.py:53-71`, `patients/middleware.py:56-67`.

Problemstillinger, enhetstyper og lydvarsel settes inn i `<script>` som
`{{ x|safe }}` av `json.dumps(...)`. `json.dumps` escaper ikke `<`. Navnet på en
problemstilling settes fritt av `skriv_leder` (bare `strip()`, 64 tegn), så
`</script><script src="https://cdn.jsdelivr.net/npm/…"></script>` lukker det
nonce-merkede skriptet og starter et nytt. Noncen hjelper ikke: `script-src` har
`cdn.jsdelivr.net` og `unpkg.com` som vertskilder, og uten `'strict-dynamic'` gjelder
vertslista fortsatt — jsdelivr serverer vilkårlige npm-pakker. En `skriv_leder` på
oppdrag får dermed kjørt JavaScript hos alle som åpner `/oppdrag/`, global admin
inkludert.

**Fiks:** escap som `json_script` gjør (`<` → `\u003c`, `>` → `\u003e`, `&` → `\u0026`)
før `mark_safe`, i én hjelper alle de seks variablene går gjennom. Og på sikt H3.

### H2. Klient-IP leses på tre ulike måter, og ingen av dem er riktig bak Railway
`accounts/views.py:45-50, 365`; `patients/signals.py:36-40`; `oppdrag/signals.py:61-63`;
`vaktliste/signals.py:62`; `patients/views_arkiv.py:34`; `oppdrag/views_arkiv.py:49`;
`patients/admin_status.py:504`.

Rate-limit-bøtta `login:ip` (50/5 min) og `reset:ip` teller på `REMOTE_ADDR`, som bak
Railways proxy er proxyens adresse: hele organisasjonen deler én bøtte, og ved vaktstart
kan bruker nummer 51 få 429 uten at noe er galt — mens ingen angriper bremses. Samtidig
tar innloggingsloggen og pasient-/oppdragsaudit *første* ledd i `X-Forwarded-For`, som
klienten selv kan sette: IP-feltet i revisjonssporet er forfalskbart. Vaktliste-audit og
arkivene logger proxyens adresse. Tre svar på «hvem gjorde dette», alle feil.

**Fiks:** én funksjon, `core.klientip.klient_ip(request)`, som tar *siste* ledd i
`X-Forwarded-For` (Railway er én betrodd proxy), validerer med `ipaddress` og faller
tilbake til `REMOTE_ADDR`. Brukt alle sju stedene og som `key=` i de to IP-bøttene.

### H3. CSP-vertslista og manglende SRI gjør noncen verdiløs mot HTML-injeksjon
`patients/middleware.py:56-67`; alle maler med CDN-lenker (ingen `integrity=`).

Se H1. Seks eksterne filer (Bootstrap css/js, ikoner, Tabulator css/js, Chart.js) lastes
fra to CDN-er uten Subresource Integrity, og begge vertene er åpne i `script-src`.
Kompromitteres CDN-et, eller finnes én HTML-injeksjon, kjører fremmed JS med full tilgang
til pasientdata og sesjon — også på innloggings- og MFA-sidene.

**Fiks:** legg de seks filene under `static/vendor/` (WhiteNoise hasher dem alt), og fjern
CDN-vertene fra CSP, `font-src`, `connect-src` i service-workerens CSP og `CDN`-lista i
`vaktliste-sw.js`. Offline-driften blir også mer robust. Minimum: `integrity` +
`crossorigin="anonymous"` på alle seks, og `'strict-dynamic'` i `script-src`.

### H4. Service-workeren lagrer vaktlista og mannskapsregisteret på disk, og ingenting rydder ved utlogging
`static/js/vaktliste-sw.js:73-99`; `accounts/views.py:628-640`.

Alle 200-svar under `/vaktliste/api/` og selve sida legges i Cache Storage. Registersvaret
bærer navn, telefon, e-post, ISSI og `notat` — feltet som er unntatt verdilogging i audit.
Kopien lever til `VERSJON` bumpes. `nettForst` serverer kopien ved nettverksfeil uten
innloggingssjekk: på en delt drifts-PC kan neste person etter utlogging koble fra nettet
og åpne `/vaktliste/`, eller lese alt i DevTools. Offline drift er besluttet (§13), men
prisen må rammes inn.

**Fiks:** `Clear-Site-Data: "cache", "storage"` på svaret fra `logout_view` (sletter Cache
Storage, localStorage og workeren i én header); maks alder på datakopien (vaktas lengde);
og et avsnitt i runbooken om at drifts-PC-en er en enhet portalen legger data på, og at
«Logg ut» er det som rydder.

## Middels

### M1. Riktig passord nullstiller kontolåsen før MFA er bestått
`accounts/views.py:396-399`. Telleren og `locked_until` nullstilles idet passordet er
godkjent, også når MFA gjenstår. Den som har passordet kan gjette fire koder, logge inn
på nytt og få telleren nullstilt. TOTP har django-otps egen throttle; backup-kode-stien
(`:573-585`) har ingen utover cache-bremsen, som faller åpen. **Fiks:** nullstill bare
`locked_until`-sjekken der begge faktorene er bevist (`_do_complete_login` gjør det alt),
ikke på passordsteget for kontoer med MFA.

### M2. Innloggingsviewet skriver uvalidert brukernavn til databasen
`accounts/views.py:372-373, 388, 433`. `LoginForm` opprettes men `is_valid()` kalles
aldri; `username` leses rått fra POST. `LoginEvent.username_attempt` er `varchar(64)`,
`ip` er `inet`. Et brukernavn over 64 tegn gir `DataError` på PostgreSQL → 500 og
feil-e-post, fra uinnlogget. SQLite håndhever ingen av delene, så testene ser det ikke.
**Fiks:** `form.is_valid()`/`cleaned_data`, og validér IP før lagring (H2).

### M3. Besetningsendepunktet gir en leser telefon og ISSI for alle korps
`vaktliste/views.py:655-692`. `/vaktliste/api/enhet/<pk>/besetning/` er gatet på
`vaktliste:les` alene. En `les`-bruker som på `/vaktliste/` bare ser sitt eget korps kan
iterere `<pk>` og få navn, rolle, telefon og ISSI for alle på alle biler. 404-meldingen
lekker i tillegg navnet på planlagte vakter. **Fiks:** krev `ser_alle_korps` eller
`oppdrag:les` i tillegg, eller filtrer radene med `poster_for_korps` for `les`.

### M4. Enhetsskjermens detalj-, grovsorterings- og antall-endepunkt respekterer ikke 30-minuttersvinduet
`oppdrag/views.py:462-505, 778, 815` mot `services.synlige_for_enhet`. Lista utelater
oppdraget 30 min etter Ledig («en bil som blir stående ulåst»); detaljendepunktet sjekker
bare `koblingsrad`. Bilen kan hente og endre ethvert oppdrag den har vært på i vakta.
**Fiks:** slå opp via `synlige_for_enhet(...).filter(pk=pk)` for enhetskontoer.

### M5. E-postkoblingen lar en korps-fører dele ut en badge
`vaktliste/views_registre.py:328-344, 488, 574`. Kobling for hånd er global admin fordi
den flytter en badge, men `_koble_paa_epost` kjører for alle med `kan_fore_korps`: en
`skriv_handling`-bruker kan skrive e-posten til en hvilken som helst ledig portalkonto på
en person i eget korps, og kontoen arver korpset. **Fiks:** autokoble bare for admin og
`kan_skrive_alt`; ellers lagre e-posten uten kobling.

### M6. Enhetskontoer ser hele flåtens aktive oppdrag gjennom enhetslista
`oppdrag/views.py:142-203`. `enheter_view` er `les` uten enhetskonto-sjekk: bilen får
status, oppdragsnummer, hastegrad, problemstilling og kontonavn for alle enheter.
`flytt_view` og `views_verdier` mangler også sperren de andre sentralbord-viewene har.
**Fiks:** 403 for `er_enhetskonto` i `enheter_view`, `flytt_view` og verdi-skrivingene.

### M7. Admin kan degradere eller deaktivere seg selv og siste admin via «Rediger», uten spor
`accounts/views.py:1070-1108`, `accounts/forms.py:354-360`. Sletting og frys sperrer
«deg selv» og «siste admin»; `edit` gjør det ikke, og `is_active=False` den veien skriver
ingen auditrad og dreper ingen sesjoner. Uten Django-admin i prod finnes ingen nødutgang.
**Fiks:** fjern `is_active` fra redigeringsskjemaet (frys/tø er den sporede veien) og
avvis rolleendring på egen konto og på siste admin.

### M8. JSON-parserne sjekker ikke typen — 500 på gyldig JSON
`patients/views_common.py:17-22`, `oppdrag/views_common.py:12-17`,
`vaktliste/views.py:66-70`. `[]`, `"x"` og `null` gir `AttributeError` på første
`.get()`, fra enhver innlogget bruker, med feil-e-post. **Fiks:** `isinstance(data, dict)`
i alle tre.

### M9. Formelinjeksjon i audit-CSV
`core/views.py:446-462`. `old_value`/`new_value` er brukerinnskrevne og skrives rått;
`=`, `+`, `-`, `@` tolkes som formler i Excel, som er nettopp det fila er laget for.
**Fiks:** prefiks slike celler med `'`.

### M10. Global admin får `skriv_full`, ikke toppen av stigen
`core/auth_decorators.py:157-158`. `nivaa_for(admin)` gir `skriv_full` (3) mens
`skriv_leder` er 4; hvert `skriv_leder`-kallsted må derfor huske `er_global_admin(...) or`.
Én glemt `or` er et 403 for admin. **Fiks:** returnér høyeste nivå i stigen.

### M11. Én-sesjon-policyen mister taket etter passordbytte
`accounts/views.py:685-687`. `current_session_key` skrives *før* `update_session_auth_hash`
roterer nøkkelen; feltet peker så på en nøkkel som ikke finnes, og neste innlogging fra en
annen enhet dreper ingenting. Treffer alle nye brukere (tvunget passordbytte).
**Fiks:** bytt rekkefølge.

### M12. Trust-cookien er et bærer-token uten binding og uten salt
`accounts/views.py:167-216`. `"<uid>:<did>"` signert med `TimestampSigner()` uten salt,
ikke bundet til passord-hash; overlever passordbytte, reset og «Logg ut brukeren» i 30
dager. **Fiks:** ta et passordavtrykk med i verdien (som `signert_lenke` gjør), egen
`salt`, og slett cookien ved passordbytte og reset.

### M13. Likhetsvalidatoren for passord er en no-op i alle tre skjemaene
`accounts/forms.py:70, 123`. `validate_password` kalles uten `user`, så «kan ikke ligne
brukernavnet» håndheves ikke. **Fiks:** send `user` inn.

### M14. Kontolåsen er en utestengelsesvektor og røper brukernavn
`accounts/views.py:385-391, 431`. Fem feil mot et brukernavn låser kontoen for alle i
15 min; brukernavn er `fornavn.etternavn`. Låst konto gir egen melding og hopper over
hasheren, så svartid og tekst skiller kjent fra ukjent bruker. **Fiks:** lås per
(konto, IP) eller stigende forsinkelse; alltid samme melding; kjør hasheren uansett.

### M15. LocMemCache med `MAX_ENTRIES=200` deles av rate-limit, idempotens og statistikk
`myproject/settings.py:342-351`. Uten Redis kan 200 ulike brukernavn mot innlogging
kaste ut tellerne. Konfigsjekken flagger «ikke redis». **Fiks:** noen tusen, og Redis i
prod.

### M16. Avhengighetene er ikke låst
`requirements.txt` (alle `>=`), ingen lock-fil, ingen `pip-audit` i bygget. Hver deploy
henter nyeste `boto3`, `cryptography`, `redis` osv. `pip-audit` i dag: ingen kjente
sårbarheter — for dagens oppløsning. **Fiks:** `pip-compile --generate-hashes` og
`--require-hashes` i bygget; Dependabot eller ukentlig `pip-audit`.

## Lav

- **L1.** Feil-e-posten til `ADMINS` inneholder `sessionid`: Djangos `cleanse_setting`
  skjuler bare nøkler som matcher `KEY|TOKEN|SECRET|PASS…`. Egen `SafeExceptionReporterFilter`
  som redigerer cookien (`myproject/settings.py:476-486`).
- **L2.** `patient_detail_view` er ikke scopet til aktiv vakt (`patients/views_patients.py:338`).
- **L3.** `offsite.hent` bygger sti av objektnavnet uten å sile `/` (`core/offsite.py:187`).
  Bare CLI, men en kompromittert bucket blir da en vei til filsystemet.
- **L4.** «Vellykket innlogging» og `last_login_at` settes før MFA er bestått
  (`accounts/views.py:396-403`).
- **L5.** MFA-steg 2 og 3 filtrerer ikke på `is_active` (`accounts/views.py:453, 531`).
- **L6.** Backup-koder lagres i klartekst (django-otp `StaticToken`) og i sesjonen under oppsett.
- **L7.** `reset_password`, `unlock` og `send_invitasjon` skriver ingen auditrad.
- **L8.** Reset-lenken er ikke bundet til `last_login`; utsendingen er synkron og røper om
  adressen finnes gjennom svartiden (`accounts/views.py:972`).
- **L9.** Ikke-atomisk telling av feilede forsøk (`accounts/views.py:288-295`).
- **L10.** `SECRET_KEY` sjekkes ikke for lengde; `ALLOWED_HOSTS` splittes uten `strip()`;
  `SECURE_PROXY_SSL_HEADER` står også lokalt; minste passordlengde er Djangos 8.
- **L11.** Sider som viser midlertidig passord mangler `@never_cache`
  (`accounts/views.py:865, 1057`).
- **L12.** Sesjonen glir uten absolutt tak (`SESSION_SAVE_EVERY_REQUEST`).
- **L13.** Rate-limiting mangler på en rekke skrivende/tunge endepunkter bak `skriv_*`/admin
  (verdimengder, ressurs/vaktpost-PUT, backup run/restore, arkiv-statistikk, brukeradmin).
- **L14.** Dekoratørtesten dekker ikke `/portal-admin/`, `/varsler/` og `/min-profil/`;
  `admin_required` setter ingen markør.
- **L15.** Sletting i vaktlistas registre krever ikke `confirm` (korps/kompetanse/gruppe/rolle).
- **L16.** Tabulator-formattere i `patients-table.js:8, 22, 30` setter inn rå strenger;
  verdiene er låst i dag, men sinken er ubevoktet. Flere `innerHTML`-byggere står utenfor
  XSS-skannernes lister (de escaper riktig i dag).
- **L17.** Offline-køene i localStorage er ikke knyttet til bruker; en annen konto på samme
  enhet spiller av forgjengerens usendte stemplinger.
- **L18.** `/healthz/` røper cache-type, unntaksklassenavn og git-SHA uten innlogging.
- **L19.** Feilvarsel logger `get_full_path()` — søkeparametre kan inneholde navn.
- **L20.** `Procfile` kjører `createcachetable` uten DB-cache; README beskriver
  `DJANGO_SUPERUSER_*`-automatikk som ikke finnes.
- **L21.** Ugyldig dato i `date_from`/`date_to` gir 500 for admin (audit- og innloggingslogg).
- **L22.** `LoginEvent` (forsøkt brukernavn, IP, UA, 730 dager) bør stå i personvernnotatet;
  AHASend som mottaker av feilvarsel bør stå i databehandleroversikten.

## Bekreftet riktig

Transport (SSL-redirect, HSTS 1 år + subdomener, proxy-header, nosniff, `Referrer-Policy`,
`X-Frame-Options: DENY` + `frame-ancestors 'none'`, COOP). Cookies (`Secure`, `HttpOnly`,
`SameSite=Lax`; CSRF-token via `<meta>`, ikke cookie). CSP med 128-bits nonce, ingen
`unsafe-inline`/`unsafe-eval` i `script-src`, `object-src 'none'`, `base-uri`,
`form-action`. Ingen hardkodede hemmeligheter; `.env`, `db.sqlite3` og `backups/` aldri
commitet; `SECRET_KEY` nekter oppstart med plassholder. Feil-e-post uten HTML/locals/POST.
Rate-limiting med eksplisitte grupper, fail-open dokumentert, normalisert brukernavn-nøkkel.
Idempotensnøkler namespacet per bruker. Sesjonsfiksering stoppet av `cycle_key`; `next`
validert med `require_https`; én sesjon per konto; POST-only utlogging. TOTP-replay stoppet
av `last_t`; backup-koder engangs; TOTP-hemmelighet kan ikke leses ut. CSRF: eneste
`csrf_exempt` er `healthz` (`require_safe`). Alle muterende views har metode-sjekk. Bil A
kan ikke stemple bil B (`koblingsrad` overalt). Oppdrag scopet til aktiv vakt.
Masseoppdatering med navngitte felt; `vakt`/`opprettet_av` server-side. Korpsfilteret
fail-closed uten badge; `?korps=` bare for `ser_alle_korps`. Backup-nedlasting/restore
via DB-rad bundet til `pk` og slug. Ingen `.raw()`/`.extra()`/`eval`/`pickle`; `subprocess`
kun `git log` med faste argumenter. Eneste `|safe` er de i H1. `pip-audit`: ingen kjente
sårbarheter i dagens oppløsning; Django 5.2 er LTS.

## Status og rekkefølge

**13. sep. 2026:** runde 1 (commit `2b88853`) og runde 2 er rettet på `rollemodell`, se
CHANGELOG. M14 er rettet for brukernavn-røping og svartid; låsen er fortsatt global per
konto, bevisst — utestengelsesvektoren står under «senere». «Senere» står igjen.

**Runde 1 — nå, uten migrasjon:** H1 (escaping), H2 (klient-IP-hjelper), H4
(`Clear-Site-Data` + maks alder), M1, M2, M3, M4, M5, M6, M7, M8, M9, M10, M11, L2, L3,
L5, L10 (strip/lengde), L11. Alt er små, avgrensede endringer med tester.

**Runde 2:** H3 (vendor CDN-bibliotekene, stram CSP, fjern CDN fra service-workeren),
M12 (trust-cookie), M13, M14, M15, M16 (lock-fil), L1, L13, L14.

**Senere / avgjørelser:** L6 (hashede backup-koder — krever egen tabell), L12 (absolutt
sesjonstak), L8, L17, L18, L22 (dokumentasjon).
