# Beslutningsnotat: rollemodellen

Status: **besluttet 24. aug. 2026. §5 levert 28. aug.; resten ikke bygget.** Én
forutsetning må kontrolleres i prod før migrasjonen skrives — den står i «Åpne
avklaringer» nederst.

Endret 28. aug. 2026: stigen sto kort med et femte trinn, `leder`. **Det er reversert** —
begrunnelsen holdt ikke, se §3.1. Stigen er som opprinnelig besluttet.

Erstatter TODO-punktet «Rollemodellen — trenger beslutning». Beslutningen måtte tas før
modul nummer to skrives, ikke etterpå.

**Slettes** når modellen er levert. Da er begrunnelsen CHANGELOG sin.

---

## 1. Hva modellen er i dag

Tre lag som blandes, og bare det ene håndheves:

| Lag | Hva det er | Håndheves? |
|---|---|---|
| `role` (5 nivåer) | Autorisasjon | **Ja** — dekoratorer og inline-sjekker |
| `kan_redigere_*` (5 bools) | Modul-synlighet | **Nei** — kun meny og dashboard |
| `Forstehjelper.user` / `Helsepersonell.user` | Funksjon i felt (domenedata) | n/a |

## 2. Funnene som utløste beslutningen

Alle verifisert ved å kjøre koden, ikke bare lese den.

### 2.1 Modulflaggene er ikke tilgangskontroll

En `read_write`-bruker med `kan_redigere_pasienter=False`:

```
GET  /pasienter/                 -> 200
GET  /pasienter/api/patients/    -> 200
POST /pasienter/api/patients/    -> 201   (pasient opprettet)
```

`permission_flag` leses kun av `Module.is_visible_for()`, som bare kalles fra
`get_visible_modules()` — altså dashboard og nav. Ingen view sjekker flagget.
Avkrysningsboksen heter «Kan se pasientregistrering», men skjuler bare kortet.

### 2.2 `ModuleSettings.enabled=False` stenger ikke URL-en

`GET /pasienter/` gir 200 med modulen deaktivert. Toggelen er en menybryter, ikke en
nødbryter. Verdt å vite *før* noen prøver å stenge en modul under en hendelse.

### 2.3 Hierarkiet er ikke et hierarki av rettigheter

`lead_view` ligger over `read_write` (2 mot 1), men har ikke skrivetilgang. De to
mekanismene er derfor uenige:

```
read_only   has_role_at_least(read_write)=False  i WRITE_ROLES=False
read_write  has_role_at_least(read_write)=True   i WRITE_ROLES=True
lead_view   has_role_at_least(read_write)=True   i WRITE_ROLES=False   <-- uenighet
lead        has_role_at_least(read_write)=True   i WRITE_ROLES=True
admin       has_role_at_least(read_write)=True   i WRITE_ROLES=True
```

Ingen live-bug i dag — `has_role_at_least` brukes kun med `'admin'`, i `views_arkiv.py`.
Men den som skriver `has_role_at_least(user, 'read_write')` i neste modul gir `lead_view`
skrivetilgang uten å merke det.

### 2.4 `accounts/mixins.py` er både død og feil

Ingenting importerer den. `RoleRequiredMixin.dispatch()` kaller `super().dispatch()`
*først* — altså kjører viewet — og reiser `PermissionDenied` etterpå. En POST ville blitt
utført og deretter fått 403. Første klassebaserte view som griper etter
`WriteRequiredMixin` arver den. **Fjernes.**

### 2.5 `dataset_scope_all` er død kode

Definert i `core/auth_decorators.py:78`, re-eksportert i shimen, aldri brukt. **Fjernes.**

### 2.6 Rollelistene finnes i fem kopier

`auth_decorators.py`, `mixins.py`, `WRITE_ROLES` i `views_common.py`, tre JS-filer, og
hardkodede `{% if %}` i malene (`index.html:1040` gjentar stats-trioen). Ikke en feil i
dag; med fire moduler til er det tjue kopier.

### 2.7 Dokumentasjonsdrift

`docs/TEKNISK_DOKUMENTASJON.md` §6.3 sier hierarkiet håndheves via
`accounts/decorators.py` — det er shimen (N11). Tabellraden «Slette pasient (soft)» er en
hard-delete. Kosmetisk: `lead_view` får samme grå badge som `read_only` i brukerlista.

## 3. Den nye modellen

**Tre kategorier, ikke to.**

1. **Global admin** — brukeradmin, backup, moduloppsett, audit, arkiv, og de irreversible
   handlingene. Ett flagg, ingen modulakse.
2. **Modulbasert** — `ModulTilgang(bruker, modul_slug, nivå)`. Fravær av rad = ingen tilgang.
3. **Globalt, men ikke admin** — innlogging, min profil, passordbytte, MFA. Krever bare
   innlogging.

### 3.1 Én akse per modul, ikke to

Utgangspunktet var to akser (`les: basis|utvidet` × `skriv: ja|nei`), fordi dagens fem
roller er nettopp det. Statistikkmodulen (§5) kollapser `les`-aksen, og igjen står:

```
ingen  →  les  →  skriv: handling  →  skriv: full
```

| Nivå | Betyr |
|---|---|
| `ingen` | Ingen rad. Modulen er usynlig og URL-en gir 403 |
| `les` | Kan se modulens data |
| `skriv: handling` | Kan utløse modulens navngitte overganger (stemplinger). **Leser ikke request-kroppen** |
| `skriv: full` | Kan redigere felter |

### `leder` — lagt til 28. aug., reversert samme dag

Et femte trinn `leder` («utvidet tilgang på modulen du er på») ble kort besluttet, og så
tatt ut igjen. Begge deler er verdt å notere, for argumentet kommer tilbake.

Begrunnelsen for å definere det med én gang var at `ModulTilgang.nivaa` ellers ville
trengt en ny migrasjon den dagen nivået fikk innhold. **Den begrunnelsen er feil.**
`choices` ligger i Djangos `Field.non_db_attrs`; å legge til en verdi senere gir en
tilstandsmigrasjon uten SQL. Kontrollert:

```
-- Alter field role on customuser
-- (no-op)
```

Samme kategori som `help_text` i `accounts/0009`. Kostnaden argumentet hvilte på finnes
ikke.

Uten den står bare ulempene igjen. `skriv: handling` er også tomt i dag, men har en
navngitt bruker, et konkret endepunkt og en testbar invariant (§3.2) — vi vet hva det er
når det fylles. Et tomt nivå i matrisen er dessuten lett å gi bort i god tro: det gir
ingenting i dag, og gir automatisk mer den dagen noen fyller det, uten at beslutningen tas
på nytt.

**Innføres når noe faktisk skal ligge der, ikke før.**

#### Bruken finnes nå — men den haster ikke (28. aug. 2026)

Argumentet over var at `leder` ikke hadde noen definert bruk. Det stemmer ikke lenger.
André har navngitt den: **«admin light»** — en vaktleder som skal kunne mer enn `skriv:
full`, uten å være global admin.

Sannsynlig innhold, ut fra hva som i dag er admin og som ikke er irreversibelt:

- arkivere en vakt (`arkiv_lagre_view`)
- se arkivlista og arkivdetaljer (`ARKIV_VIEW_MIN_ROLE`)
- redigere førstehjelper- og helsepersonellregisteret

**§3.3 gjelder fortsatt for resten.** Nullstilling av år, hard-delete utenfor
slettevinduet, arkiv-kollaps, brukeradministrasjon og backup er irreversible eller
konto-nære, og skal ikke desentraliseres. «Admin light» er ikke «admin med færre klikk» —
det er de reversible tingene en vaktleder trenger.

Behovet er ikke aktuelt ennå, så nivået bygges ikke nå. Men når det gjøres: begynn med
lista over, ikke med å flytte alt som i dag er admin. Og merk at det å legge til verdien i
`TilgangsNivaa` er en `-- (no-op)`-migrasjon — kostnaden ligger i å bestemme innholdet, ikke
i skjemaet.

### 3.2 Hvorfor `handling` er et eget nivå

Bruk: en bil-/ambulansekonto skal kunne trykke «fremme» og få et tidsstempel, men ikke
redigere fritekst.

Det lar seg ikke løse med en rollesjekk slik koden er i dag. Stemplingen er ikke en egen
handling — `stamp_pabegynt_if_needed()`, `stamp_obs_times_if_needed()` og
`stamp_utskrevet_if_needed()` kalles alle fra innsiden av den generelle `PUT`-en, med hele
request-kroppen som argument. Et tidsstempel oppstår som *bivirkning av en redigering*.
Ga vi en bil-konto skrivetilgang der, måtte begrensningen bli en feltwhitelist inne i
viewet — og den typen whitelist svikter stille den dagen noen legger til et felt.

**Regelen er derfor at en innskrenket aktør får et smalt endepunkt, ikke et filtrert
bredt et:**

- `POST /oppdrag/<pk>/fremme/` — leser ingenting fra kroppen, stempler server-tid
- `PUT /oppdrag/<pk>/` — tar feltverdier, krever `skriv: full`

**Invarianten er testbar:** et `handling`-endepunkt skal ikke lese request-kroppen. En
test kan håndheve det; «husk å utelate fritekst» kan den ikke.

Henger sammen med to eksisterende TODO-punkter for oppdragsmodulen — fritekstfeltet som
skal unntas audit-verdilogging, og «fjernes fra bilen etter 1–2 timer» som visningsfilter.
Bil-kontoen er den samme aktøren i alle tre.

### 3.3 Ingen modul-admin

De destruktive handlingene forblir global admin: hard-delete av pasient utenfor
slettevinduet, nullstill år, navneregistrene, arkivering og arkiv-kollaps. Grunnen er at
de er irreversible — hard-delete resirkulerer pasientnummeret, kollaps kan ikke angres —
og organisasjonen er liten nok til at de bør ligge hos de samme få.

## 4. Endepunktene i `patients`

Alle 16 URL-ene i `patients/urls.py`:

| Endepunkt | I dag | Ny modell |
|---|---|---|
| `/pasienter/` | **kun `@login_required`** | modul: les |
| `api/patients/` GET | **kun `@login_required`** | modul: les |
| `api/forstehjelpere/`, `api/helsepersonell/` GET | **kun `@login_required`** | modul: les |
| `api/settings/` GET | **kun `@login_required`** | modul: les |
| `api/patients/` POST, `<pk>/` PUT | `WRITE_ROLES` | modul: skriv full |
| `api/settings/` PUT | `WRITE_ROLES` | → portal-admin (§4.1) |
| `api/stats/`, `api/full-stats/` | `stats_required` | → statistikkmodulen (§5) |
| `api/patients/<pk>/` DELETE | admin | skriv full, i vindu (§4.2). Ellers admin |
| `api/reset-active-year/` | admin | global admin |
| navneregistrene POST/PUT/DELETE | admin | global admin |
| `api/innstillinger/arkiv/*` | admin | global admin |
| `api/session-timeout/` PUT | admin | → portal-admin (§4.1) |

De fire uthevede radene er hullet fra §2.1: **i dag åpne for enhver innlogget bruker.**

### 4.1 `session-timeout` og `event_name` flyttes

Begge er portalinnstillinger som ligger under `/pasienter/`. De hører hjemme i
portal-admin. Egen liten opprydding, men den gjøres i samme omgang siden
tilgangssjekkene deres uansett skrives om.

Merk at `saveEventName` da flytter ut av pasientmodulens JS. Se F7-regelen i `CLAUDE.md`
om hva som må ligge i alltid-lastede moduler.

### 4.2 Slettevinduet

`skriv: full` kan hard-slette **pasienter brukeren selv opprettet, de siste 30 minuttene.**
Eldre sletting forblir global admin.

Det treffer feilregistrering — en duplikat eller et feiltrykk som blokkerer et
pasientnummer og forstyrrer statistikken — uten å gjøre sletting til et hverdagsverktøy.
Den som oppdager feilen er den som registrerte, ikke en admin som kanskje ikke er på vakt.

**«Egen pasient» avgjøres fra auditloggen, ikke fra et nytt felt.** `Patient` har
`created_at`, men ingen `opprettet_av`. `AuditLog` har CREATE-raden med `user`, og
`(table_name, record_id)` er indeksert — så oppslaget er billig og krever ingen migrasjon.
Mangler CREATE-raden, nektes slettingen (fail-closed).

**Forbehold som følger med:** auditloggen lagrer i dag bare pasientnummeret ved DELETE
(`patients/signals.py:266`), ikke innholdet i raden. Etter en sletting vet man *at*
pasient #14 ble slettet av Kari 14:32, ikke hva som sto der. Innenfor et 30-minutters
vindu på egne rader er det akseptabelt. Åpnes sletting bredere senere, må DELETE-loggingen
utvides først.

## 5. Statistikk blir egen modul — og det forenkler modellen

`lead_view` gir i dag **bare statistikk**. Kontrollert:

- `stats_required` beskytter `/api/stats/` og `/api/full-stats/` — det er alt
- `.stats-only` i malen dekker nav-punktet (`index.html:108`) og fanepanelet (`:200`) — det er alt
- `dataset_scope_all` er død kode (§2.5)
- Arkivet er admin, ikke `lead_view`

Flyttes statistikk ut i egen modul, har `les`-aksen **null gjenværende brukere**. «Større
leserett» viser seg å ha vært «tilgang til statistikkmodulen» hele tiden. En person med
større leserett og ingen skrivetilgang blir da `patients: les` + `statistikk: les`.

**Rekkefølge: statistikkmodulen skilles ut før eller sammen med rollemodellen.** Gjøres
rollemodellen først, bygges en `les`-akse som umiddelbart rives ned igjen.

**Levert 28. aug. 2026.** `statistikk/`-appen, `/statistikk/`-siden, endepunktene,
JS-delingen og eget stilark. Ingen tilgangsendring: `stats_required` gjelder fortsatt, og
modulsynligheten gates midlertidig på `Module.min_rolle` — et felt som fjernes sammen med
`permission_flag`. Arkiv-endepunktet beholdt `ARKIV_VIEW_MIN_ROLE` i tillegg, ellers ville
`lead_view` fått innsyn i arkiverte vakter ved flyttingen.

**Komposisjonskravet i avsnittet under er ikke innfridd ennå** — det kan det ikke bli før
`ModulTilgang` finnes. I dag gates modulen på `stats_required` alene, så den viser
pasienttall til alle med statistikktilgang. Kravet innføres i deploy 1.

**Statistikkmodulen komponerer tilgang, den eier den ikke.** Den viser kun kilder brukeren
har minst `les` på i kildemodulen. Ellers er den en bakvei rundt modultilgangen — en
person uten oppdragstilgang ville fått avledet innsyn i oppdragsdata.

Se `docs/BESLUTNING_STATISTIKK.md`. Tilgangstabellen der (`/api/full-stats/` →
admin/lead/lead_view) må skrives om til modulnivåer når dette bygges.

## 6. Håndhevelse

**Eksplisitt dekoratør, ikke middleware:**

```python
@modul_kreves('patients', nivaa='les')
```

Middleware på URL-prefiks er ett sted å glemme, men også ett sted å ta feil av
`/pasienter/api/...`. Dekoratør matcher husets stil.

Risikoen er en glemt dekoratør på et nytt endepunkt. **Den lukkes med en test som går
gjennom `urlpatterns` for modulens prefiks og krever at hvert view er dekorert.** Den
testen finnes ikke i dag — gjennomgangen i CHANGELOG (2026-08-22, «Kontrollert og funnet i
orden») ble gjort for hånd, og holder bare til neste endepunkt.

**`ModuleSettings.enabled=False` stenger URL-en med 403.** Global admin slipper fortsatt
inn — ellers kan man deaktivere seg selv ut av å kunne reaktivere.

## 7. Modellendringer

### 7.1 `role` krymper til `admin` / `bruker`

Et eget `er_admin`-felt ville gitt en migrasjon til og etterlatt `role` som dødt felt.

> **Gjennomført 28. aug. 2026** — `accounts.0013_krymp_role`. Ikke deployet til prod ennå.
> Rekkefølgen innad i deployen var poenget: først ble koden gjort uavhengig av de fire
> verdiene, så krympet feltet. Motsatt vei ville gitt et vindu der
> `has_role_at_least(user, 'read_write')` sammenlignet mot en verdi som ikke fantes — og
> den sammenligningen feiler ikke, den svarer bare feil.

### 7.2 De fem `kan_redigere_*`-flaggene fjernes

Erstattes helt av `ModulTilgang`. Navnene var uansett feil: de gjorde verken redigering
eller tilgang.

### 7.3 `PasientRolleForm` splittes

Radioen setter i dag **både** FK-en (`Forstehjelper.user` / `Helsepersonell.user`) og
`kan_redigere_pasienter`. Det er to forskjellige ting: funksjon i felt er domenedata,
tilgang er autorisasjon. Etter splitten setter radioen kun koblingen, og tilgang settes i
en matrise modul × nivå. To steg i stedet for ett — bevisst.

### 7.4 Frontend: `window.USER_ROLE` → `window.MODUL_TILGANG`

```js
window.MODUL_TILGANG = { nivaa: 'skriv_full', admin: false };
```

Fjerner JS-kopiene av rollelistene (§2.6). Betinget lasting av `patients-stats.js` (F7)
blir irrelevant når statistikk er egen modul.

## 8. Migrasjonen — tre deployer, ikke to

TODO sa minimum to. Det blir tre, fordi rollekrympingen er destruktiv.

| Deploy | Innhold | Rullbar? |
|---|---|---|
| **1** | Legg til `ModulTilgang`, fyll den fra `role`, innfør `@modul_kreves` + håndhevelse. `role` og de fem flaggene står urørt | Ja |
| **2** | Krymp `role` til `admin`/`bruker`. Bytt maler og JS | Kun med `ModulTilgang` som fasit |
| **3** | Fjern de fem flaggene | Ja |

Status: **1 er i prod** (28. aug. 2026), **2 er kodet, ikke deployet**, 3 gjenstår.

Slås 1 og 3 sammen, mister en rollback dataene. Deploy 2 kan ikke komme før matrisen er
verifisert i prod: `lead_view` → `bruker` kan ikke rulles tilbake uten `ModulTilgang`.

### 8.1 Defaulten utledes fra `role` alene, ikke fra flagget

Alle beholder nøyaktig den tilgangen de har i dag; ingen mister noe under deploy.

| Dagens `role` | `ModulTilgang('patients', ...)` |
|---|---|
| `read_only` | `les` |
| `read_write` | `skriv: full` |
| `lead_view` | `les` + `statistikk: les` |
| `lead` | `skriv: full` + `statistikk: les` |
| `admin` | global admin — ingen rad nødvendig |

**Merk at `lead` ikke får noen egen merkelapp.** Rollens faktiske forskjell fra
`read_write` er statistikk, og den bevares som en `statistikk`-rad. Kartleggingen er
dermed tapsfri etter *rettigheter*; «leder» som betegnelse bevares bevisst ikke — se
§3.1 om hvorfor nivået ikke finnes.

**Grunnen til å ignorere flagget:** en migrasjon som stille trekker tilbake tilgang
oppdager du midt i en vakt. Innstrammingen gjøres etterpå, for hånd, i matrisen — synlig
og reversibel.

Merk hva dette betyr: brukere som i dag ikke *ser* modulen i menyen, men som kunne nå den
via URL-en (§2.1), får en rad som bekrefter tilgangen de allerede hadde. Ingen privilegier
oppstår; de blir bare synlige.

## 9. Opprydding som følger med

- `accounts/mixins.py` fjernes (§2.4)
- `dataset_scope_all` fjernes (§2.5)
- `docs/TEKNISK_DOKUMENTASJON.md` §6.3 rettes: shimen, hard-delete, ny tilgangstabell
- `lead_view`-badgen i `user_list.html` / `user_detail.html` — bortfaller med rollekrympingen

**Lagt til i deploy 2, ikke planlagt her:**

- **De to bulk-knappene på brukerlista.** «Gi ledere pasienttilgang» og «fjern
  pasienttilgang fra alle» skrev `kan_redigere_pasienter` på en gruppe kontoer og meldte
  suksess uten at noen fikk eller mistet noe. De ble ikke fanget av §2.1-gjennomgangen
  fordi de skriver et flagg, ikke leser det — men konsekvensen er den samme fella:
  neste gang tilgang skal trekkes tilbake, tror admin at jobben er gjort.
- **`ARKIV_VIEW_MIN_ROLE` og `ARKIV_WRITE_ROLE`** i `patients/services.py`. De var
  «konfigurerbare» til `lead_view` og `lead` — verdier som ikke finnes etter §7.1.
  Arkivet er global admin, og sier det nå rett ut.
- **Halve `verifiser_modultilgang`.** §10.1-tellingen og sammenligningen mot `role` er
  fjernet, ikke gjemt bak en versjonssjekk: begge ville svart «ingen avvik» og «Antall: 0»
  om hver eneste database etter krympingen. Et svar som alltid er grønt er verre enn ingen
  kontroll.

`accounts/decorators.py` beholdes som shim så lenge `core/tests.py` verifiserer den (N11).

## 10. Åpne avklaringer

1. ~~**Kontroller i prod før migrasjonen skrives:** hvor mange kontoer har `role` ≥
   `read_write` men `kan_redigere_pasienter=False`?~~ **Besvart 28. aug. 2026: 0 av 2.**
   Ingen kontoer uten rader, ingen avvik fra backfillen. Kontrollen ble kjørt mot prod
   mellom deploy 1 og 2, og kan ikke tas om igjen — deploy 2 fjerner grunnlaget, og en
   rollback gir alle den samme rollen.
2. Skal `handling`-nivået innføres allerede i deploy 1, eller først når oppdragsmodulen
   skrives? Anbefaling: definer nivået nå (så `ModulTilgang` ikke trenger ny migrasjon),
   men ta ikke i bruk før det finnes et `handling`-endepunkt å bruke det på.
3. **Skal matrisen ligge på opprettingsskjemaet?** `AdminUserCreateForm` har `role`, men
   ikke modulflaggene — de finnes kun på redigeringsskjemaet. I dag er det udramatisk
   siden flaggene ikke gjør noe. Med håndhevelse lander den nyinviterte i en tom portal
   og må redigeres etterpå. Anbefaling: legg matrisen på opprettingsskjemaet.
4. **Varsler til brukere uten modultilgang.** `_notify_assignment`
   (`patients/signals.py:234`) fyrer på at `role_obj.user` er satt, og sjekker ikke
   modultilgang. Før splitten i §7.3 var tilstanden umulig — `PasientRolleForm` satte
   koblingen og flagget samtidig. Etterpå kan man være koblet som helsepersonell uten
   `ModulTilgang('patients')`, og få et varsel med lenke til en 403. Varselet inneholder
   dessuten et pasientnummer. Anbefaling: `notify()` hopper over brukere som mangler
   tilgang til `module_slug`.

**Akseptansekriterium:** ingen endepunkt i en modul er nåbart uten `ModulTilgang`-rad;
URL-gjennomgangstesten er grønn; `ModuleSettings.enabled=False` gir 403 for ikke-admin;
ingen bruker mistet tilgang ved deploy 1.
