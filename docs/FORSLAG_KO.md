# Forslag: KO-modulen — situasjonsbildet, loggen og hendelsene

Status: **forslag, ikke besluttet.** Skrevet 17. september 2026 etter en gjennomgang med
André 16.–17. sep., der rammene ble lagt. Ingenting er bygget. Arbeidslista er `TODO.md`.

**Dette notatet erstatter `FORSLAG_DATTEROPPDRAG.md`**, som er arkivert samme dag. Den
foreslo å gruppere flere pasienter under et moroppdrag med `Oppdrag.forelder`, og forkastet
uttrykkelig en egen hendelsestabell. Konklusjonen var riktig **så lenge oppdraget var
øverste nivå**. Med KO får grupperingen et hjem som også dekker lag og hendelser uten en
eneste enhet, og da er datteroppdrag feil svar på et spørsmål som ikke lenger stilles.
Begrunnelsen er tatt vare på i §9.3.

---

## 1. Hva KO er, og hva det ikke er

`/oppdrag/` er et **enhetsverktøy**: én bil, én statusmaskin, én stempling om gangen. Alt i
modulen forutsetter at ressursen selv sitter med skjermen.

`/ko/` er et **situasjonsverktøy**: hva skjer på arrangementet, hvem er hvor, hva vet vi.
Her sitter noen andre enn ressursen og fører.

Tidsaksen er ulik, og det er den forskjellen resten av notatet henger på. Et oppdrag
begynner når bilen får det. **En hendelse begynner når noen sier noe over samband**, kan
leve i tjue minutter før en ressurs sendes, og kan bli avsluttet uten at noen rykket ut.

Etter omleggingen fordeler ansvaret seg slik:

| Modul | Eier | Konto |
|---|---|---|
| `/vaktliste/` | Hvem finnes, hvem er på vakt | Personlig |
| `/oppdrag/` | Enhetens skjerm og statusmaskinen | **Delt** — og bare denne |
| `/park/` | Lagets utfallsregistrering (eget notat senere) | Ingen — vaktnøkkel, skrive-bare |
| `/ko/` | Situasjonsbildet, loggen, hendelsene, status for dem som ikke stempler selv | Personlig |
| `/pasienter/` | Pasienten fra samleplass og inn | Personlig |

**Sentralbordet flytter til KO.** `/oppdrag/` beholder det ikke. Det er en flytting, ikke
en kopi — to skjermer som viser de samme oppdragene ville før eller siden blitt uenige
under en vakt, og da er ingen av dem til å stole på.

Setningen som forklarer resten: **enheter produserer tid, lag produserer utfall.**

## 2. Det som allerede finnes

Seks ting i gjennomgangen viste seg å være bygget. Det er ikke en kuriositet — det er
grunnen til at forslaget er lite, og et arbeidsmønster verdt å bruke bevisst: **før noe
designes inn i KO, sjekk om vaktlista, oppdrag eller kontoappen allerede har begrepet.**

| Det vi trodde manglet | Det som finnes | Hva som gjenstår |
|---|---|---|
| Et begrep for «hva slags ressurs» | `vaktliste.Ressursgruppe` — docstringen sier selv «samleplass, ambulanse, mannskapsbil, lag», og nevner KO | Ett flagg for ruting, §3.2 |
| Et begrep for «den enkelte ressurs» | `vaktliste.Ressurs` — «Noe som bemannes: samleplass, bil, lag, KO» | Ingenting |
| En kobling mellom ressurs og enhet | `Ressurs.enhet` → `oppdrag.Enhet`, `SET_NULL`, lagt inn for at sentralbordet skulle kunne vise besetningen | Ingenting |
| Et skille mellom personlig og delt konto | `CustomUser.er_delt_konto` — styrer i dag e-post, MFA og selvbetjent reset | Den skal også avgrense modultilgang, §5.2 |
| Et sted å slå av og på egenskaper per ressurstype | `Enhetstype.kan_passiv_vakt` / `kan_avvente`, admin-styrt | Mønsteret gjenbrukes, §3.2 |
| En løpenummerteller per vakt | `oppdrag.services.neste_oppdragsnummer()` med `AppSetting`-nøkkel, atomisk | En tvilling for hendelser, §6 |

### 2.1 Dubletten vi kjenner, og som ikke skal røres nå

`oppdrag.Enhetstype` og `vaktliste.Ressursgruppe` er **den samme taksonomien vedlikeholdt
to steder** — ambulanse, mannskapsbil, lag står i begge.

Den skal ikke slås sammen i dette arbeidet. Grunnen er at oppdragsmodulen samtidig snevres
inn: når sentralbordet flytter til KO, forsvinner `Enhetstype` sin grupperingsrolle, og bare
flaggene blir igjen. Dubletten krymper av seg selv underveis, og sammenslåingen er billigere
etterpå enn nå. Men den skal stå skrevet ned som kjent, slik at den ikke oppdages på nytt
som om den var ny.

## 3. Datamodellen

### 3.1 Ressursbildet er en projeksjon, ikke et register

KO eier **ikke** ressursene. Tavla settes sammen av tre kilder:

| Hva | Kilde |
|---|---|
| Hvem finnes, og hvem er på vakt nå | `vaktliste.Ressurs` + skift |
| Status for dem som stempler selv | `oppdrag.Enhet` gjennom `Ressurs.enhet` |
| Status for dem som ikke stempler selv | **KO**, ført av operatøren |

Alternativet — et eget ressursregister i KO — ble lagt bort, se §9.1.

Det siste punktet er det eneste nye, og det er ikke et register men en tilstand:
`(ressurs, status, tidspunkt, ført av hvem)`. Den bærer i seg selv skillet mellom «bilen sa
det» og «KO førte det», og det skillet må være synlig i grensesnittet og i loggen.

**Ressurs henger på én vaktliste** (`FK` med `CASCADE`). «Lag 3» er altså en ny rad for hver
vaktliste, mens `oppdrag.Enhet` er permanent. Konsekvensen er at statistikk over enheter
gjennom en sesong er rett fram, mens statistikk over lag må matche på navn og gruppe, ikke
på ID. Det er ikke et problem, men det er et sted en spørring kan gi feil svar uten å feile.

### 3.2 Ruting: hvem bruker `/oppdrag/`, hvem bruker `/park/`

Flagget hører hjemme på **`Ressursgruppe`**, ved siden av `flere_enheter` og `er_aktiv`.

Det kan ikke ligge på `Enhetstype`: et lag har ingen `Enhet` i det hele tatt — det er hele
poenget med at de ikke logger inn. Og det skal være admin-styrt og ikke en konstant i kode,
av samme grunn som `Ressursgruppe` selv sluttet å være en `choices`-tuple: et arrangement
kan ha en dronegruppe i kveld, og den som trenger den kan ikke vente på en utrulling.

### 3.3 Hendelse

Egen modell i `ko`. Ikke et polymorft superoppdrag, og ikke `Oppdrag.forelder` — se §9.3.

| Felt | Merknad |
|---|---|
| `vakt` | Scopet, som alt annet |
| `hendelsesnummer` | Per vakt, fra 1. §6 |
| `tittel` | Det man kaller den på samband |
| `lokasjon` | Gjenbruker `oppdrag.Lokasjon` — verdimengden finnes og styres av `skriv_leder` |
| `status` | Åpen / lukket. Ingen statusmaskin — hendelser har ikke et forløp, oppdrag har |
| `opprettet_av`, `lukket_av`, `lukket_at` | Hvem, og når |
| `opprettet_fra_linje` | Nullbar FK til logglinja den ble laget av |

`Oppdrag` får **én** ny nullbar FK, `hendelse`. Den peker fra oppdrag til hendelse, aldri
motsatt, slik at `oppdrag` ikke trenger å kjenne `ko`.

> **Avhengighetsretningen:** `ko → vaktliste` og `ko → oppdrag`. Ingen av dem kjenner `ko`.
> KO blir øverste lag. `core/tests_avhengighetsretning.py` skal håndheve begge kantene med
> AST, som `OppdragImportererIkkeVaktlista` gjør i dag. FK-en fra `Oppdrag` til hendelsen
> er unntaket som må navngis og begrunnes der.

## 4. Loggen og hendelsene

### 4.1 Én logg, ikke to

Loggen er **én tabell** med alle linjer: menneskeskrevne linjer, chat, kommentarer inne i en
hendelse, og navngitte systemhendelser løftet inn. En linje har en nullbar FK til en
hendelse.

Det gir to visninger gratis — hele loggen, og hendelsen som filter — og én egenskap vi
kommer til å trenge: **en linje kan knyttes til en hendelse i etterkant.** Det er slik det
faktisk går; man skjønner fem linjer på etterskudd at de hørte sammen.

At loggen blir stor og uoversiktlig er ikke et problem som skal løses *i* loggen. Den skal
være fullstendig og kjedelig; hendelsesoversikten er der man ser hva som gjelder nå. Den
eneste fella er å begynne å skjule ting i loggen for å gjøre den ryddig — da er den ikke
lenger fasit.

### 4.2 Den er ikke audit-loggen

`audit/` er automatisk, på feltnivå, teknisk, og finnes for sikkerhet. Hendelsesloggen er
menneskeskrevet, append-only, utskrivbar, og i praksis et dokument man leser etter et
arrangement der noe gikk galt. **De må ikke slås sammen.**

Systemhendelser løftes inn i hendelsesloggen **kuratert, ikke automatisk**: «Enhet 3 satt
til på stedet» hører hjemme der, «Enhetstype fikk nytt navn» gjør ikke. Lista over hvilke
som løftes skal være eksplisitt og begrunnet, på samme måte som `NOKLER_UTEN_AUDIT` — og
den er selve designarbeidet i denne delen, ikke en detalj.

### 4.3 Retting

Retting skjer som **ny rad som peker på den gamle**, aldri ved å endre. Mønsteret finnes i
`Statusmelding.objects.gjeldende()`.

To felter som aldri blandes:

- `tidspunkt` — når det faktisk skjedde. Korrigerbart.
- `registrert_at` — når linja ble skrevet. Aldri korrigerbart.

**Loggen sorteres på registreringsrekkefølge, ikke på `tidspunkt`.** Ellers hopper linjene
rundt etter en korreksjon, og fortellingen blir uleselig — og det er som fortelling loggen
har verdi. Den korrigerte tida vises i linja.

Statistikken må lese den korrigerte verdien. Gjør den ikke det, er loggen og statistikken
uenige, og da stoler ingen på noen av dem.

### 4.4 Sletting — unntaket fra append-only

KO-loggen dekker **det som skjer utenfor samleplass og sykestue**; pasienten blir pasient i
`/pasienter/`. Opplæringen er at direkte identifiserende opplysninger — navn, adresse,
fødselsnummer, telefon — ikke skrives i feltet.

Det reduserer risikoen reelt, og det er den sterkeste formen for dataminimering som finnes.
Men to ting følger likevel:

1. **«Ingen direkte identifiserende» er ikke «ikke personopplysninger».** «Mann, ca. 60,
   kollapset ved scene sør 21:14» er indirekte identifiserende på et arrangement med kjent
   deltakerliste, og det er helseopplysninger uansett. Loggen skal derfor ha **samme**
   tilgangsnivå som pasientdata, ikke et lettere.
2. **Opplæring forvitrer under press.** En travel kveld skriver noen et navn. Designet må
   anta det.

Derfor: **én smal, logget sletteinngang** som tømmer innholdet i en linje og lar rada stå —
«fjernet av André, 22:10». Append-only og «fjern personopplysninger» står i direkte
konflikt, og den konflikten løses med én navngitt vei, ikke med en generell redigering.
Bygges den inn fra start er den billig; ettermonteres den i en append-only modell er den
vond.

### 4.5 Chat

Chat er **ikke en egen tabell** — det er logglinjer uten hendelse. Er chatten et eget sted,
kommer dagen da den viktigste setningen ble sagt der og ikke står i loggen.

Admin-bryteren betyr derfor «har operatørene lov til å skrive uformelle linjer», ikke «skru
av en funksjon som etterlater hull i arkivet».

En chatlinje kan gjøres om til en hendelse. **Linja blir stående**, og hendelsen peker
tilbake på den (`opprettet_fra_linje`). Flyttes linja inn i hendelsen, får loggen et hull
akkurat der det viktige skjedde.

Hver linje viser brukernavnet til den som skrev den, **frosset på linja**. Visningsnavn
endres og kontoer slettes, og en logg der avsenderen forsvinner er verdiløs akkurat når den
leses. FK-en står ved siden av.

**En delt konto må se ut som en delt konto i loggen.** «Enhet 2» og «Kari Nordmann» betyr
fundamentalt ulike ting — den ene er en person, den andre er to til tre personer man må slå
opp i vaktlista for å finne. Blir loggen noen gang lest i en personalsak, er den forskjellen
alt.

### 4.6 Lukking

Operatøren er den eneste som lukker en hendelse. Oppdrag ferdigstilles som hovedregel av
ressursen selv; operatøren kan overstyre, slik det virker i dag — og det skal stå i sporet
at KO avsluttet på enhetens vegne.

**Lukking sperres med 409 når hendelsen har åpne oppdrag**, med antallet i svaret, og går
gjennom med `confirm`. En lukket hendelse med kjørende biler er nøyaktig den tilstanden der
en enhet blir glemt. Operatøren skal aldri møte en vegg, bare en dør hun må åpne bevisst.

### 4.7 Besetningen på en logglinje

Den delte kontoen kan ikke svare på hvem som satt i bilen kl. 21:14 — den brukes av 06–14,
14–22 og 22–06, og besetningen byttes på noen ressurser og ikke på andre. Svaret finnes bare
i vaktlista, via skiftet.

Loggen skriver derfor **enheten**, og besetningen utledes gjennom vaktliste + tidspunkt.
Utledet, ikke frosset: en retting i vaktlista i etterkant retter som regel virkeligheten.
Kallesignalet og operatørens brukernavn fryses derimot på linja, jf. §4.5.

## 5. Tilgang og kontotyper

### 5.1 Ansvarsområde vises, tilgangsnivå styrer

To ting som lett får samme ord:

| | Hva det er | Endres | Hva det gjør |
|---|---|---|---|
| **Tilgangsnivå** | Hva du har lov til — `les`, `skriv_handling`, `skriv_full`, `skriv_leder` | Sjelden, av admin | Styrer |
| **Ansvarsområde** | Hva du gjør nå — samband, ressurser, logg, media | Flere ganger i vakta | Vises |

Ansvarsområdet skal **ikke gi tilgang**. «Bare sambandsoperatøren kan føre sambandslinjer»
dobler matrisen, og første gang den rette er opptatt møter du en vegg i en situasjon der
vegger er dyre. KO er et rom der folk dekker for hverandre — det er hele grunnen til at de
sitter sammen.

Området står på linja («ført av Kari, samband») og kan være et filter i visningen. Skal noe
gates ekstra — lukke en hendelse, overstyre en enhet — er `skriv_leder` verktøyet, og det
finnes.

### 5.2 Delt konto får bare oppdragsmodulen

`CustomUser.er_delt_konto` finnes og styrer i dag e-post, MFA og selvbetjent reset. Den skal
også avgrense modultilgang: **en delt konto kan ikke ha `ModulTilgang` til annet enn
`oppdrag`.**

Ikke som konvensjon, men håndhevet i flere lag — skjemaet, datalaget og en test — på samme
måte som superbrukerflagget er vernet i dag. Grunnen er at sperrene ellers verner nøyaktig
de veiene som finnes akkurat nå, og en ny vei er usynlig for dem.

Personlige kontoer er dem som har tilgang til data på tvers av ett oppdrag: `/pasienter/`,
`/vaktliste/`, `/ko/`.

### 5.3 Sidebaren

Vis/skjul-lista over påloggede med `/ko/`-tilgang er `_list_active_sessions` filtrert på
`ModulTilgang('ko')`, med `inaktiv_s`-kolonnen fra 16. sep. Nesten ferdig.

Den svarer på «hvem har KO oppe», **ikke** på «hvem dekker samband nå» — pålogget er ikke
til stede, og det er allerede dokumentert i `CLAUDE.md`. Blir det siste et behov, er det en
egen liten ting.

## 6. Nummerering

To uavhengige serier, begge per vakt, begge fra 1:

- **Hendelse 12** — `H12` der plassen er trang
- **Oppdrag 45** — `O45`

Hendelsestelleren er en tvilling av `neste_oppdragsnummer()`: `AppSetting`-nøkkelen
`next_hendelse_nr_vakt_<pk>`, atomisk, med `Max()` som fallback. **Nøkkelen må inn i
`NOKLER_UTEN_AUDIT`-prefiksene**, ellers får du én auditrad per hendelse midt blant de ekte
radene — nøyaktig fella pasienttelleren gikk i.

Oppdragsnummeret vises i dag som `#45`. Det bør bli `O45` samtidig. Alene er `#45`
utvetydig; i en logg der begge står på nabolinjer er det ikke det, og det er i loggen de
møtes.

**Nummeret tildeles ved opprettelse og endres aldri** — heller ikke når et oppdrag knyttes
til, løsnes fra eller flyttes mellom hendelser. Regelen bak: **nummeret identifiserer,
FK-en relaterer.** Visningen bærer relasjonen: «Oppdrag 45 · Hendelse 12».

Hierarkisk nummerering (`H12.1`) er forkastet, se §9.4.

`/park/`-registreringer får **ikke** et nummer i denne familien — de sies aldri høyt, og en
tredje serie er en tredje ting å forveksle. En kvittering til den som registrerte holder.

## 7. Grensesnittet

Fire flater, én side:

| Flate | Innhold |
|---|---|
| **Ressursoversikt** | Tavla fra §3.1 — enheter og alt annet som bemannes |
| **Oppdragsliste** | Sentralbordet, flyttet fra `/oppdrag/` |
| **Logg / chat** | Strømmen, med «Ny hendelse» på en linje |
| **Hendelser** | Pågående hendelser, hver med sine linjer og sine oppdrag |
| *Sidebar* | Vis/skjul, påloggede med KO-tilgang |

**Sentralbordkoden flyttes, ikke kopieres.** `oppdrag-sentral-*.js` (fire filer) blir KO
sine; `oppdrag-enhet.js` blir hele `/oppdrag/`. Regelen om at hver del skal være under
1 800 linjer gjelder uendret, og `patients/js_test_utils.py` sine tupler følger med.

### 7.1 Hold KO påføringsformet

Flere operatører samtidig fungerer i `/oppdrag/` i dag, og grunnen er at arbeidet der er
**påføringer**: nye oppdrag, nye statuser, nye rader. Ingen konflikt er mulig, og polling
holder.

Det skal KO også være. Loggen er append-only, kommentarer er append-only, og det eneste
delte redigerbare er **hendelsens hode** (tittel, lokasjon, status). Der trengs et
versjonsnummer og 409 ved uenighet — ellers spiser siste skriver den andres tekst i
stillhet.

Så lenge nesten alt er nye rader, skalerer polling fint, og **WebSockets skal ikke tas i
bruk**: det er et stort infrahopp på Railway med synkron Django, uten en gevinst som
forsvarer det. Loggen pollers med `?siden=<id>`.

### 7.2 Filter per operatør

Operatørene har ulike behov — den som har ansvar for bilressurser vil se dem, den som har
lag vil se lagene. Løses som et **synlig filter husket per bruker i nettleseren**. Ingen ny
tabell, ingen admin.

Én regel uansett løsning: **et filter skal aldri skjule noe stille.** «Viser 2 av 5 grupper»
skal stå i bildet hele tiden. Et filter satt forrige vakt som skjuler den ene ressursen noen
leter etter, er usynlig for den som har det.

Ansvarsområdet kan sette standardfilteret. Det er bare et utgangspunkt, og derfor ufarlig.

## 8. Statistikk

Både `ko` og `park` melder seg inn i kilderegisteret i `core/stats.py`, som er mønsteret.

Det som ikke er rett fram: **de tre registrene teller kontakter, ikke personer.** Et lag
finner noen og registrerer i `/park/`, tilkaller ambulanse som får et oppdrag, og pasienten
havner på samleplass. Én person, tre rader, tre registre. Summeres de, står det 340
pasienter i sesongrapporten der det var 210 mennesker.

Det er ikke en feil som skal rettes — det er tre ekte målinger av tre ekte ting. Men **det
må stå i tallet selv**: «registreringer», ikke «pasienter», på alt som krysser
registergrensene. Ordvalget i overskriften er det eneste som hindrer feilen, for ingen leser
metodikken før de siterer tallet.

Tall KO kan svare på som ingen kan i dag: hendelser per vakt, varighet per hendelse,
ressursbruk per hendelse, tid fra første logglinje til første ressurs på vei, og hvor mange
hendelser som ble løst uten utrykning.

## 9. Det vi har lagt bort, og hvorfor

### 9.1 Eget ressursregister i KO

Forkastet. Bilene ville finnes to steder. Feilen oppstår ikke ved opprettelse men ved
endring: noen retter kallesignalet ett sted, og tavla og enhetsskjermen viser ulike navn på
samme bil midt i en vakt. Man vinner en selvstendighet KO ikke trenger.

### 9.2 Å utvide `oppdrag.Enhet` til å dekke lag

Forkastet. Det motsier definisjonen `/oppdrag/` får i denne omleggingen — «ressurs med skjerm
som stempler selv» — og hvert sted som antar at `enhet.user` finnes måtte tåle `None`.
Statusmaskinen ville fått en gren for «stempler aldri selv», altså en gren som aldri er den
som brukes.

### 9.3 `Oppdrag.forelder` (datteroppdrag)

Forkastet, og det er en **omgjøring** av `FORSLAG_DATTEROPPDRAG.md` §2 fra 13. sep. 2026.

Den gangen ble en grupperingstabell lagt bort med en god begrunnelse: *«Moren er et oppdrag
med biler og stemplinger før noen vet hvor mange pasienter det er. En gruppetabell måtte
enten dobbeltlagre det, eller la den første utrykningen stå utenfor hendelsen.»*

Premisset er snudd i KO. Der finnes hendelsen **før** oppdraget, og ofte uten oppdrag i det
hele tatt. Innvendingen rammer altså ikke en hendelsestabell på KO-nivå. Og KO-hendelsen
gjør alt §4 i det gamle notatet lovet — én tidslinje, ressursbruk per hendelse, spredning —
i tillegg til at den dekker lag og hendelser uten en eneste enhet, som datteroppdrag aldri
kunne.

Det åpne spørsmålet i det gamle notatets §7 — hva skjer med morens bil når første datter
lages — faller bort med modellen. Bilen står på sitt oppdrag; oppdraget peker på hendelsen.

### 9.4 Hierarkisk nummerering, `H12.1`

Forkastet av to grunner:

1. Et oppdrag opprettes ofte før hendelsen finnes og knyttes til den etterpå. Da måtte det
   omnummereres — og **et nummer som endrer seg er ikke en identifikator**. Det er allerede
   sagt på samband, skrevet i loggen og notert på en lapp.
2. «Tolv punktum tre» er dårligere over samband enn «oppdrag førtifem».

### 9.5 Chat som egen modell

Forkastet, se §4.5.

### 9.6 Ansvarsområde som tilgangsakse

Forkastet, se §5.1.

### 9.7 Pekere mellom `/ko/`, `/oppdrag/` og `/pasienter/`

**Utsatt med vilje**, ikke forkastet. Registrene holdes uten pekere til hverandre inntil
videre.

Grunnen er den samme som i §8: uten kobling er tallene ærlig adskilte. Med en halvveis
kobling ville noen begynt å avduplisere og fått noe som ser riktigere ut enn det er. Skal
det kobles en dag, er **pasientnummeret i en logglinje** den billigste broen — det er ikke
identifiserende i seg selv, og det fjerner fristelsen til å skrive «kvinne, 34,
brystsmerter» i loggen for å huske hvem det var. En ekte FK ville begynt å gjøre KO-loggen
til del av pasientjournalen, og det er nettopp det grensen i §4.4 unngår.

## 10. Foreslåtte puljer

Den minste KO som er nyttig på én ekte vakt er hendelser, logg og ressursoversikt. Chat,
filtre og statistikk er forbedringer *av* det bildet og legges oppå uten å rive noe.

| Pulje | Innhold | Hvorfor den rekkefølgen |
|---|---|---|
| **1 — Skallet** | Modulen registrert, `ModulTilgang('ko')`, tom side med de fire flatene, sidebar | Tilgangen må virke før noe legges bak den |
| **2 — Loggen** | Logglinjer, retting, sletteinngang, polling med `?siden=` | Alt annet skriver inn i den |
| **3 — Hendelser** | `Hendelse`, nummerserie, linje → hendelse, oversikt, lukking med 409 | Krever loggen |
| **4 — Ressursoversikten** | Projeksjonen i §3.1, KO-ført status, rutingflagget | Uavhengig av 2 og 3; kan bytte plass |
| **5 — Sentralbordet flyttes** | `oppdrag-sentral-*.js` → KO, `Oppdrag.hendelse` | Den største, og den eneste som rører `/oppdrag/` |
| **6 — Chat og filter** | Admin-bryter, uformelle linjer, filter per operatør | Forbedringer |
| **7 — Statistikk** | Kilde i `core/stats.py`, tallene i §8 | Trenger data fra en ekte vakt først |

`/park/` får sitt eget notat og kommer etter. Flagget i §3.2 hører til der, men er nevnt her
fordi det er samme valg.

## 11. Åpne spørsmål

Disse skal besvares før koden, ikke under:

1. **Hvilke systemhendelser løftes inn i loggen?** Lista i §4.2 er selve designarbeidet.
   Forslag skrives her og avklares med André.
2. **Skal en lukket hendelse kunne åpnes igjen?** Sannsynligvis ja, som en ny logglinje —
   men det er en operativ avgjørelse.
3. **Hvor lenge oppbevares KO-loggen, og arkiveres den?** `NOTAT_DPIA_OG_FRITEKST.md` §7
   slår fast at «fritekst bevisst ikke arkiveres» — et felt som inngår i arkivets
   SHA-signatur er låst i 24 måneder ved konstruksjon og kan ikke fjernes uten at arkivet
   melder tukling. KO-loggen er i all hovedsak fritekst, og sletteinngangen i §4.4 har
   nøyaktig den samme konflikten. Svaret må gis før loggen bygges, ikke ryddes opp i
   etterpå.
