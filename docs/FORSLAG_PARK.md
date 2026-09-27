# Forslag: `/park/` — lagets utfallsregistrering

Status: **under avklaring.** Første utkast 27. september 2026 fra staging `8327d8f`; André
svarte samme dag, og svarene står som **besluttet** under. §9 er det som gjenstår. **Ingen
kode før §9 er tom** (André: «Vi starter ikke kode før vi har alt av punkter på plass»).
Arbeidslista er `TODO.md`.

Underlaget som allerede sto skrevet, og som dette notatet bygger på:

| Hvor | Hva det sa om park |
|---|---|
| `TODO.md`, «Skalering mot 2027» (13. aug. 2026) | Egen modell, ikke rader i `Patient`. Skriveendepunkt uten innlogging, rate-limit per token, kvittering — aldri data |
| `TODO.md`, KO-seksjonen | Problemstilling, lokasjon, utfall. Ingen stempling, ingen pålogging. Egen statistikk-kilde, ingen kobling til `/pasienter/`. Rutingflagget hører til her |
| `docs/RUNBOOK_VAKT.md` §3c | Lagene **poller ikke** — de registrerer uten å lese |
| `docs/FORSLAG_KO.md` §1, §3.2, §6, §8 | «Enheter produserer tid, lag produserer utfall.» Flagget på `Ressursgruppe`. Intet nummer i `H`/`O`-familien. Tallene heter «registreringer», ikke «pasienter» |

---

## 1. Hva park er, og hva det ikke er

Et lag går rundt på arrangementsområdet. Det plastrer en blemme, gir vann til en som er
varm, følger en beruset til samleplassen, eller tilkaller bil. **Ingenting av dette blir
registrert i dag**, med mindre personen havner i `/pasienter/` — og da er det sykestua som
registrerer, ikke laget. Statistikken ser de som kom inn, ikke de som ble tatt hånd om ute.

`/park/` er **en tellemaskin på én side**, ikke et journalsystem:

| Park er | Park er ikke |
|---|---|
| «Sandnes 2.1 hjalp tre med skrubbsår ved Parkscene, alle gikk videre selv» | En pasient. Ingen navn, ingen alder, intet nummer som sies høyt |
| Én side med nedtrekk, på en telefon | Et skjema man fyller ut etterpå |
| Skrive-bare for laget. Det ser en kvittering | En liste laget kan bla i |
| Tall til KO og til statistikken «Lag» | Grunnlag for oppfølging av en enkeltperson |

**Den siste raden er premisset for resten.** Så lenge ingen enkeltregistrering skal kunne
følges opp, trenger raden ingen personopplysninger — og da trenger endepunktet ingen
pålogging. Glipper premisset («vi må kunne finne igjen han med hodeskaden»), er det
`/pasienter/` det gjelder.

---

## 2. Besluttet 27. sep. 2026 (André)

| # | Hva | Beslutning |
|---|---|---|
| B1 | Fritekst | **Ingen.** Bare nedtrekk og antall |
| B2 | Tilgangsnivåer | `les`, `skriv_leder` og global admin — som ellers i portalen |
| B3 | Lenken | **Én lenke**, lagt i et tiltakskort i Bliksund, der tilgangen allerede er avgrenset. Settes opp og fjernes av `skriv_leder` og admin, med **oppetid fra og til** |
| B4 | Lagvalget | Laget velger seg selv i et nedtrekk. **Valget huskes på telefonen** til neste gang siden åpnes |
| B5 | Tokenet | «Best practice går foran»: tilfeldig token, bare hashen lagres (§4.1) |
| B6 | Problemstillinger | Egen liste, satt opp av `skriv_leder` og admin, **startverdier fra `/pasienter/`** |
| B7 | Utfall | Egen liste, satt opp av **admin** |
| B8 | Personen | Ingen kjønn, ingen alder |
| B9 | Antall | En registrering kan gjelde **flere med samme problemstilling**. Etter registrering starter en ny, med lag og sted husket — stedet kan endres. **Alt av nedtrekk på én side** |
| B10 | Lokasjon | Arves (§5), men kan alltid endres av laget |
| B11 | Angre | Ja. **5 minutter** som standard, styrt av admin |
| B12 | Statistikk | En egen kilde, **«Lag»** |
| B13 | QR-koder | Ikke nå. Står i `TODO.md` som mulighet |
| B14 | Offline | **Ikke nødvendig** |
| B15 | KO | De med `/ko/`-tilgang skal se registreringene og handle på dem i `/ko/` uten `ModulTilgang('park')` (§7) |
| B16 | Tavla | Stedet laget setter selv og stedet KO har plassert det — hvordan det vises på tavla står i `TODO.md` |

**Hva B3 og B4 endret fra første utkast.** Utkastet foreslo én lenke per lag, med
begrunnelsen at et nedtrekk ingen kontrollerer er en påstand. André: «det blir svært
komplisert for lagene». Tiltakskortet er stedet lagene allerede slår opp, og én lenke der
er én ting å vedlikeholde. **Prisen skal stå:** hvem som helst med tilgang til
tiltakskortet kan registrere som et hvilket som helst lag, og statistikken per lag er
akkurat så god som valget i nedtrekket. At valget huskes på telefonen (B4) reduserer den
feilen mer enn noe annet — det er det første valget som må være riktig, ikke hvert.

**Hva B14 endret.** Utkastet kalte offline en forutsetning, fordi dekningen er dårligst der
lagene er. André har vurdert det annerledes, og konsekvensen er ærlig: **uten nett feiler
registreringen, og siden sier det.** Den skal aldri late som den lagret. Idempotensnøkkelen
(§3.1) beholdes likevel, fordi en telefon med dårlig dekning sender samme forespørsel to
ganger også når den er på nett.

---

## 3. Datamodellen

### 3.1 `park.Registrering`

| Felt | Merknad |
|---|---|
| `vakt` | Scopet, som alt annet |
| `lenke` | FK til `Parklenke`, `SET_NULL`. Hvilken lenke som ble brukt |
| `ressurs` / `ressurs_navn` | FK til `vaktliste.Ressurs`, `SET_NULL`, **strippes i backupen**; navnet frosset, som `HendelseLag` |
| `problemstilling` | Tekst, validert mot `park.Problemstilling` (B6). Tekst og ikke FK, som `Oppdrag.problemstilling`: navnet er det som telles, og en omdøpt rad skal ikke skrive om historikken |
| `antall` | Heltall ≥ 1, standard 1 (B9). Øvre grense 99 — et tall det er lett å skrive feil |
| `utfall` | Tekst, validert mot `park.Utfall` (B7) |
| `lokasjon` / `lokasjon_navn` | FK til `oppdrag.Lokasjon` + frosset navn, som `Tavleplassering` |
| `lokasjon_kilde` | `ko` / `laget` — om stedet var arvet fra KO-plasseringen eller satt av laget. Det er det B16 trenger for å vise forskjellen |
| `registrert_at` | Når raden kom inn. Uten offline er det også når det skjedde — ingen klienttid, ingen `vurder_klienttid` |
| `idempotency_key` | Klientgenerert UUID, unik per lenke. Er også **angre-nøkkelen**, §4.4 |
| `slettet_at`, `slettet_av_navn`, `slettet_grunn` | Bare for KO sin sletting (§7). Laget sin angring sletter raden helt — den har ikke vært synlig for noen i fem minutter som betyr noe |

**Ingen fritekst er sikkerhetsmodellen, ikke en forenkling** (B1). Et felt som tar imot hva
som helst fra et endepunkt uten innlogging er et felt der et navn havner en travel kveld,
skrevet av noen vi ikke vet hvem er. Med bare nedtrekk kan raden ikke inneholde et navn, og
da kan backupen, statistikken og KO vise den uten pasientmodulens vern.

### 3.2 `park.Parklenke`

| Felt | Merknad |
|---|---|
| `navn` | «Tiltakskort Bliksund» — så den som ser lista vet hvor lenken ligger |
| `hemmelighet_hash` | SHA-256 av tokenet. Selve tokenet lagres ikke (§4.1) |
| `aapen_fra`, `aapen_til` | Oppetiden (B3). Begge påkrevd — en lenke uten slutt er en lenke noen glemmer |
| `opprettet_av` / `_navn`, `opprettet_at` | Hvem, og når |
| `fjernet_at`, `fjernet_av_navn` | «Fjernes» (B3) er en markering, ikke sletting: registreringene beholder sin peker, og lista viser at lenken fantes |
| `sist_brukt_at` | «Ingen registreringer på fire timer» kan bety en død lenke |

**Lenken er ikke bundet til en vakt.** Registreringen havner på vakta som er aktiv når den
sendes, og er ingen vakt aktiv, er siden stengt. Se §9, spørsmål 2 — det er et valg.

### 3.3 Verdimengdene

| Tabell | Hvem setter opp | Startverdier |
|---|---|---|
| `park.Problemstilling` | `skriv_leder` og admin (B6) | De 21 i `patients.choices.PROBLEMSTILLING`, kopiert inn av migrasjonen |
| `park.Utfall` | Admin (B7) | §9, spørsmål 4 |

Begge med `navn`, `rekkefolge`, `er_aktiv` — mønsteret fra `oppdrag.Lokasjon` og
`oppdrag.Problemstilling`. **Kopiert, ikke lest:** park importerer ikke pasientmodulen. Lista
er en startverdi, og fra første endring er den parks egen — to lister som delte kilde ville
endret seg sammen uten at noen ba om det.

### 3.4 Rutingflagget på `Ressursgruppe`

`FORSLAG_KO.md` §3.2 plasserte det her og utsatte det. Med B4 får det én virkning:

> **`registrerer_i_park`** (bool, standard `False`): ressursene i gruppa står i lagnedtrekket
> på `/park/r/`.

Bevisst **ikke** en `choices` med `oppdrag`/`park`/`ingen` — om en ressurs stempler i
`/oppdrag/` avgjøres allerede av `Ressurs.enhet`, og to kilder for samme sannhet er uenige
den dagen det teller.

---

## 4. Siden uten innlogging

### 4.1 Tokenet (B5)

**Tilfeldig token (`secrets.token_urlsafe(32)`), SHA-256 i basen.** Standardmønsteret for
API-nøkler, og bedre enn en signert streng her:

| | Signert (`django.core.signing`) | **Tilfeldig, hash i basen** |
|---|---|---|
| Fjerne én lenke | Krever en rad likevel | Sett `fjernet_at` |
| `SECRET_KEY` roteres | Lenken dør midt i vakta | Upåvirket |
| Basen lekker | — | Hash, ikke token: lenken kan ikke gjenskapes |

**Konsekvensen av best practice er at lenken vises én gang**, i det den lages. Står den ikke
i tiltakskortet da, lages en ny. Å kunne vise den igjen krever at tokenet lagres slik det
kan leses, og da er en lekket base en lekket lenke. Se §9, spørsmål 2.

**Tokenet står i fragmentet: `/park/r/#<token>`.** Alt etter `#` sendes aldri til serveren
— det havner ikke i Railways tilgangslogg, ikke i `Referer`. Siden leser det med JS og
sender det i headeren `X-Park-Lenke`.

### 4.2 Flatene

| Sti | Hvem | Hva |
|---|---|---|
| `/park/` | `les` | Registreringene denne vakta, per lag og per sted |
| `/park/oppsett/` | `skriv_leder`, admin | Lenker (lag, fjern, oppetid), problemstillinger. Utfall: bare admin |
| `/park/r/` | **Ingen innlogging** | Skjemaet. Én statisk side |
| `/park/r/api/oppsett/` | Gyldig token | Vaktnavn, lagene, stedene, verdimengdene, og hvor KO har plassert hvert lag (§5) |
| `/park/r/api/registrer/` | Gyldig token | Lagrer, svarer med kvittering |
| `/park/r/api/angre/` | Gyldig token + angre-nøkkel | Sletter én rad innenfor fristen |

De tre under `/park/r/` står i unntakslista i `patients/tests_modul_dekorator.py` med
begrunnelse, som `vaktliste/sw.js`. `ModuleSettings.enabled=False` stenger dem også — det er
nødbryteren om lenken har lekket. Utenfor oppetiden, fjernet lenke og ugyldig token gir
**samme** svar, som `signert_lenke.les()`: forskjellen hjelper bare den som prøver seg.

### 4.3 Siden (B4, B9)

Én side, alt synlig, ovenfra og ned: **Lag · Sted · Problemstilling · Antall · Utfall ·
Registrer.**

- **Lag og sted huskes** i `localStorage`. Ressursene er nye rader for hver vaktliste, så
  valget huskes på **navn** («Sandnes 2.1»), ikke på ID — ellers er det glemt neste vakt.
- **Etter «Registrer»** tømmes problemstilling, antall (tilbake til 1) og utfall. Lag og sted
  står.
- **Kvitteringen** står øverst: «Registrert 21:14 · 3 × Skrubbsår · Parkscene · Gikk videre
  selv», med «Angre» og nedtelling. Pluss en teller: «Sandnes 2.1 har registrert 12 denne
  vakta» — et tall, ikke data, og det som forteller laget at det faktisk kommer fram.
- **Uten nett** sier siden «Ikke lagret — prøv igjen», og beholder valgene.

### 4.4 Angre (B11)

Angre-nøkkelen er `idempotency_key`: en UUID bare telefonen som sendte raden kjenner.
`angre` krever lenken **og** nøkkelen **og** at `registrert_at` er innenfor fristen. En
annen telefon med samme lenke kan ikke angre noe den ikke sendte selv.

Fristen er en `AppSetting`, satt av admin på `/portal-admin/innstillinger/` gjennom
`park/portalinnstillinger.py` — registeret finnes (`core/portalinnstillinger.py`).

### 4.5 Rate-limit og CSRF

- **Per lenke**: `park:registrer`, `120/m`. Én lenke deles nå av alle lagene (B3), så bøtta
  må romme dem samlet — men være lav nok til at et skript med en lekket lenke ikke fyller
  statistikken før noen ser det.
- **Per IP, bare for ugyldige tokens.** Ikke per IP på gyldige: telefoner på mobilnett deler
  IP-adresser bak operatørens NAT, og på en festival kan ti lag stå bak samme adresse.
- **CSRF**: `csrf_exempt`, begrunnet ved dekoratøren. CSRF verner en innlogget sesjon; her
  finnes ingen, og en fremmed side kan ikke sette headeren med tokenet.

---

## 5. Lokasjonen: arvet, men lagets egen (B10)

**Lista er `oppdrag.Lokasjon`** — den samme KO plasserer lag på. **Forhåndsvalget** er, i
denne rekkefølgen:

1. Stedet **KO har plassert laget** på tavla nå (`ko.Tavleplassering`, den åpne raden)
2. Stedet **denne telefonen** valgte sist
3. Ingenting — laget må velge

Endrer laget stedet, lagres `lokasjon_kilde = 'laget'`. Da kan tavla vise forskjellen (B16).

**Retningen er problemet, og løsningen finnes.** KO skal lese park (§7), så park kan ikke
importere `ko` — det ville vært en sirkel. Svaret er samme idiom som `core/kontokobling.py`
og `core/driftstatus.py`: et lite register i `core` der KO melder inn «hvor står ressurs X nå»,
og park spør registeret. Park vet ikke at KO finnes; er KO slått av, er punkt 1 tomt.

---

## 6. Resten av rammeverket

| Hva | Forslag |
|---|---|
| Modul | `park/module.py`, `nivaaer = ('les', 'skriv_leder')` (B2) |
| Backup | `park/backup.py`. `ressurs`, `lokasjon` og brukerpekerne strippes; navnene er frosset. Plass i `GJENOPPRETTINGSREKKEFOLGE` etter `vaktliste` |
| Arkiv | Ikke i første omgang. Park følger arkiveringen når den flytter til `/portal-admin/` (`TODO.md`), som KO |
| Statistikk | `park/statistikk.py`, fanen **«Lag»** (B12): per problemstilling, utfall, sted, lag, time. Summerer `antall`. Overskriften sier «kontakter», ikke «pasienter» (`FORSLAG_KO.md` §8) |
| Audit | Lenke laget og fjernet, verdimengdene, KO sin sletting. Registreringene selv logges ikke — de er dataene, ikke en endring av dem |
| Endringsnummer | `park/endringer.py`, så KO følger med uten å polle tabellen |
| Personvern | Ny rad i `PERSONVERN_DOKUMENTASJON.md` A.6: tid, sted, problemstilling, antall — ingen identifikator |

---

## 7. KO (B15)

**Retningen er `ko` → `park`.** KO importerer parks tjenestelag for å lese og handle; park
kjenner ikke KO. Det er retningen KO har mot `vaktliste` og `oppdrag` allerede.

**Tilgangen:** handlingene i `/ko/` gates på KO-nivået, ikke på park. Det er forsvarlig og
ikke en bakvei: KO-loggen har samme vern som pasientdata (`FORSLAG_KO.md` §4.4), og
parkregistreringene er *mindre* følsomme enn den. Å kreve `ModulTilgang('park')` i tillegg
ville vært en rad å huske for hver operatør, uten at den beskytter noe.

**Statistikken «Lag» må følge samme regel**, ellers ser KO-operatøren registreringene i
`/ko/` og ikke i statistikken. Registeret spør i dag om `har_tilgang(user, h.slug,
h.nivaa)`; det trengs én utvidelse — en handler kan oppgi en **alternativ gate**
(`('ko', 'les')`). Liten, men det er en endring i rammeverket, og derfor nevnt.

**Hva «handle på dem» betyr er §9, spørsmål 3.**

---

## 8. Puljer

Frysingen er noen uker før vakta (`TODO.md`, «Veien til neste vakt»), og park skal være
prøvd på generalprøven.

| Pulje | Innhold |
|---|---|
| **1 — Modellen og siden** | App, modul, de fire tabellene, rutingflagget, `/park/r/` med lag/sted husket, angre, rate-limit, backup, modultestene |
| **2 — Oppsettet** | `/park/oppsett/` (lenker med oppetid, verdimengdene), angrefristen i portalinnstillingene |
| **3 — KO** | Registeret for plassering (§5), registreringene i `/ko/`, handlingene fra §9.3 |
| **4 — Tallene** | `/park/`-oversikten, statistikk-kilden «Lag» med alternativ gate |

**Anslag: 4–5 økter.** Uten offline er det usikre borte; det største enkeltstykket er nå
pulje 3.

---

## 9. Det som gjenstår før koden

1. **Lokasjon — har jeg forstått «arves fra /ko eller /oppdrag» riktig?** Min lesning i §5:
   lista er stedene fra `/oppdrag/` (de samme KO bruker), og forhåndsvalget er der KO har
   plassert laget, ellers det telefonen valgte sist.
2. **Lenkens levetid.** (a) Er lenken bundet til én vakt, eller lever den på tvers av vakter
   så tiltakskortet kan stå — med oppetiden som eneste grense? Forslag: på tvers, §3.2.
   (b) Er det greit at lenken bare vises **én gang**, når den lages (§4.1)? Det er
   best practice, men betyr at mister man den, lages en ny og tiltakskortet må oppdateres.
3. **Hva skal KO kunne gjøre med registreringene?** Forslag, i stigende omfang:
   - (a) **Se dem** — en liste og en teller per lag på lagkortet. *Anbefalt.*
   - (b) **Slette en feilregistrering** etter angrefristen, med grunn, logget. *Anbefalt.*
   - (c) **Rette** problemstilling, antall, utfall eller sted.
   - (d) **Lage en hendelse eller logglinje** av en registrering. *Frarådes* — et lag som
     trenger ressurser sier det på samband, og to kanaler for samme bestilling er én for
     mye.

   Og hvilket KO-nivå per handling: `les` for (a), `skriv_full` for (b) og (c)?
4. **Startverdiene for utfall.** Admin kan endre dem, men migrasjonen må ha noe. Utkast:
   «Gikk videre selv», «Fulgt til samleplass», «Tilkalt bil», «Avslo hjelp», «Overlatt til
   andre (vakt/politi)».
