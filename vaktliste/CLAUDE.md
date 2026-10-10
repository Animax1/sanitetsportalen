# Vaktlistemodulen (vaktliste/)

> **Modulfil.** Den lastes når noen arbeider i `vaktliste/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Fase 1–6 levert, 7 delvis: statistikken, men ingen `core.arkiv`-signatur — lista
arkiveres med `arkivert_at` og slettes med vakta. Se `docs/BESLUTNING_VAKTLISTE.md` §10.

| Regel | Hvor |
|---|---|
| Badgen på kontoen | `Kontokorps` (admin, brukersiden), ellers `Mannskap.korps` via `Mannskap.user` |
| Reservasjonen på ressursen | `Ressurs.korps` — tom betyr **vaktlederens bord**, ikke fritt fram |
| Reservasjonen på plassen | `Vaktpost.korps` — overstyrer ressursens, `services.reservert_korps()` |
| Begge halvdelene sjekkes samlet | `services.kan_sette_vaktpost()` |
| Ett skift er én rad | `Vaktpost`, med plan og faktisk i hvert sitt feltpar |
| Planlagt vakt rører ikke pekeren | `services.opprett_planlagt_vakt()` |
| Pausene | `vaktliste/pauser.py`, `vaktliste.Pause` |
| Overnattingen og brannlista | `vaktliste/overnatting.py`, `Overnattingsrom`, `Overnatting`, `Vaktliste.brannrutine` |

**Flaten — fanene, ressurskortene, regnearket, tidsfeltene og JS-filene — står i
`templates/vaktliste/CLAUDE.md`** (delt 23. sep. 2026).

## Tilgang: badgen, reservasjonen og korpsfilteret

Hvem som får se og røre hva. Rammeverkets nivåstige står i rota; her står hva
nivåene *betyr* i vaktlista, og de to halvdelene som må sjekkes samlet.

- **`Mannskap.korps` er badgen** tilgangsmodellen hviler på fra fase 3:
  `skriv_handling` betyr her «fører sitt eget korps» (avgrenset av badgen, ingen
  innsjekk), ikke stempling som i oppdrag. Matrisen trenger derfor en etikett per
  modul per nivå (§4.5) før nivået deles ut.
- **Kontoen kan føre et korps uten å være mannskap** (`Kontokorps`, 1. okt. 2026): satt av
  global admin i kortet «Vaktlisten: korps» på brukersiden, og lest *før* mannskapsraden i
  `services.brukerens_korps`. Har kontoen begge, **må de være like** —
  `models.korpskonflikt()`, i viewene (409 med begge navnene) og i `save()`.
- **Den doble regelen er skrevet som én funksjon**, `kan_sette_vaktpost()`, nettopp for
  at et endepunkt ikke skal kunne huske badgen og glemme reservasjonen.
- **Reservasjonen finnes på to nivåer, og plassen vinner** (30. aug. 2026).
  `Ressurs.korps` er standarden; `Vaktpost.korps` overstyrer den for én plass, fordi en
  samleplass bemannes av flere korps. `services.reservert_korps()` er det ene stedet som
  slår dem sammen — leses de hver for seg, vil ett endepunkt før eller siden huske
  ressursen og glemme plassen. **Tom verdi betyr «som ressursen», ikke «ingen»**: en
  annen tolkning ville gjort alle eksisterende plasser fritt vilt ved oppgraderingen.
  Å *sette* reservasjonen er å dele ut, og krever `skriv_full`.
- **Korpsfilteret (11.–12. sep. 2026): bare `les` ser sitt eget korps på `/vaktliste/`;
  `les_alle`, `skriv_handling` og oppover ser alle.** `skriv_handling` så én dag bare sitt
  eget; André snudde det 12. sep. («inkludere lese: alle korps»). **Å se er ikke å
  redigere**: korps-føreren redigerer fortsatt bare eget korps (`kan_fore_korps`), og
  nedtrekkene tilbyr bare hennes folk (`mannskap_brukeren_kan_sette`).
  `services.ser_alle_korps()` er det ene stedet; `synlige_vaktposter()` og
  `synlig_mannskap()` filtrerer i svaret sida bygges av, så alle fanene følger med.
  Uten badge er lista tom, og malen sier hvorfor. Sentralbordets besetning i
  `/oppdrag/` er **ikke** filtrert — der er spørsmålet «er bilen klar» — men
  endepunktet krever derfor `ser_alle_korps` eller `oppdrag:les` (13. sep. 2026):
  en ren `les` skal ikke kunne iterere `<pk>` og få telefon og ISSI for alle korps.
  **Den som ser alle får en korpsvelger** i vaktlinja: `_synligePoster()` i
  `vaktliste.js` speiler `poster_for_korps()` og legges på `aktivListe.vaktposter`
  og `register.mannskap` i `brukKorpsfilter()`, så byggerne følger med uten å vite om
  den. Planleggingstallene regnes på serveren og får `?korps=` — bare honorert for den
  som ser alle; for korps-brukeren ville parameteret vært en dør rundt badgen.
- **Tre terskler, og skillet er hva slags utsagn nivået får avgi.** Badge + reservasjon
  bemanner — og *bare* bemanner: hvem, og i hvilken rolle (se «Å bemanne er å fylle en
  plass noen andre har satt opp» under). `skriv_full` setter opp og deler
  *ut*: skift og tider, ressurser, reservasjoner, nye vakter og verdimengdene — kunne
  korps-brukeren opprette et korps eller omreservere KO, ville badgen sluttet å avgrense
  noe. Sletting av en vaktliste er global admin.
- **`Mannskap.korps_id` og `Mannskap.user_id` er unntatt badgen.** Flytting sjekkes mot
  *begge* korps, og kontokobling **for hånd er global admin** (12. sep. 2026) fordi den
  flytter en badge — kontoen arver korpset, og dermed hva den kontoen får redigere. Alle
  andre kobler gjennom **`Mannskap.epost`**: finnes en aktiv, ledig portalkonto med samme
  e-post, kobles den av seg selv ved lagring (`views_registre._koble_paa_epost`) — men
  **bare når den som lagrer er `skriv_leder` eller global admin** (13. sep. 2026, M5):
  den som bemanner skal ikke velge hvilken konto som blir hvem. Andre lagrer e-posten.
  **Bare en adresse lederen selv skrev** (`epost_fra_leder`, 28. sep.): lagret uendret
  godkjenner hun den ikke — hun må endre den og tilbake, eller admin kobler for hånd.
  **Korps-føreren uten badge** ser alle korps, men fører ingen — sida sier det
  (`mangler_badge`), og «Mannskapsregisteret er tomt» leser registeret hun *ser*
  (`registeretErTomt`), ikke lista over dem hun får sette.
  **Adminkontoer er aldri mannskap** (12. sep. 2026: «Den er utenfor.») —
  `_koblbare_kontoer()` er det ene stedet som sier hvem som kan kobles, og e-postmerket,
  autokoblingen og kontolista leser alle derfra; kobling for hånd til en adminkonto gir
  400. `konto_finnes` i svaret sier om en bruker med adressen finnes, regnet av ett sett
  e-poster, ikke én spørring per rad.

## Plassen og skiftet — hvem får røre hva

Skillet mellom å **sette opp** en plass og å **fylle** den går gjennom hele modulen:
`kan_sette_vaktpost()` og `kan_rore_vaktpost()`, og de må ikke slås sammen. Hvordan hver
regel ble funnet, står i CHANGELOG på datoen.

- **En ledig plass er en `Vaktpost` uten `mannskap`, i én av tre tilstander** (11.–12.
  sep.): tildelt ett korps (`Vaktpost.korps`/ressursens), **åpen for alle**
  (`alle_korps`, vinner over `korps`), eller **planlagt** — lederens kladd, usynlig under
  `skriv_full` (`services.KLADD`). **Planlagt går én vei:** viewet avviser veien tilbake,
  og nedtrekket tilbyr «Planlagt» bare mens plassen står der. «Mitt korps»
  (`mkMittKorps`) viser korpsets og de åpne plassene; `kanBemannePlass()` speiler serveren.
- **«Del ut» er handlingen, med ett endepunkt** (pulje 4, 30. sep.):
  `POST api/vaktlister/<pk>/del-ut/`, fra kortets vindu og planleggerens sluttsteg —
  `services.del_ut()`. Bare kladden røres; til et korps settes `Ressurs.korps`, til alle
  `alle_korps` per plass. **Tømmes enhetens reservasjon, blir plassene som arvet den åpne
  for alle** (`frigi_arvede_plasser`), ikke kladd igjen — André: «så en ser hva som noen
  korps ikke kunne ta».
- **Å bemanne er å fylle en plass noen andre har satt opp** (15. sep., André: «legge inn
  folk, rolle, og redigere ressursens navn»). Korps-føreren setter **hvem**, **rollen** og
  **merknaden** (16. sep.: «kommer 17:30» er en beskjed om raden), og retter **navnet**.
  Tider, antall, reservasjon, `alle_korps`, `probono` og sletting er oppsett —
  `kan_sette_opp_skift()`. `probono` sier hva vakten *koster*, og hører derfor ikke til raden.
- **Regelen står som lister, ikke som en `if` per felt:** `SKIFT_OPPSETTFELTER`,
  `RESSURS_OPPSETTFELTER` og `RESSURS_UTDELINGSFELTER`, lest av `services.oppsettfelter()`.
  **Ett felt hun ikke får sette, velter hele forespørselen**, så klienten siler først
  (`bareTillatteFelter()`, listene speilet og holdt like av `SkiftetsOppsettfelterTests`).
- **Porten på `mannskap_id` gjelder overgangen, ikke innsendingen** (16. sep.): vinduet
  sender `null` over `null` på en ledig plass. **En skriving som ikke endrer noe, trenger
  ingen tillatelse til å endre det** — `ny_id != vaktpost.mannskap_id` først.
- **Markupen sier det samme som serveren:** knapper og tidsfelt står på
  `kanSetteOppSkift()`, ikke på badgen, og tidene vises som tekst for den som ikke får
  endre dem — et felt man kan skrive i og ikke lagre, ser ut som en endring som gikk igjennom.
- **Et låst felt låses med `disabled`, aldri `readOnly`** (16. sep., iPhone): `readonly`
  virker ikke på `datetime-local`, avkryssinger m.fl. **`.vl-laast`** gir stiplet kant og
  full kontrast tilbake (Safari leser `-webkit-text-fill-color`). `_laasFelter()` setter
  `disabled`, klassen og hintet i ett; hintene står i malen, og en test krever dem.
- **`ressurs_detalj_view` har tre terskler.** Navnet krever `kan_gi_nytt_navn()` — som
  spør om hun kan bemanne enheten **eller en av plassene på den**, ellers var navneretten
  stengt på hver fersk enhet (16. sep.). Reservasjonen er utdeling: `kan_sette_opp_skift`
  (30. sep., André: «de kan begge ha likt»). Type, kobling, rekkefølge og sletting: `kan_lede`.
- **Sletting av et skift er `skriv_full`, også når raden er fylt** (15. sep.): ellers kan
  et hull skjules ved å slette raden som viste det. Korps-føreren tømmer raden i stedet.
- **Et skift redigeres i et vindu** (`apneRedigerVaktpost()`, én PUT, den doble regelen
  sjekket på nytt) — å bytte person ved å slette raden mistet tidene og rollen.

## Vakta, tidene og skrivingene

- **Vaktas lengde: start på `Vakt.startet`, slutt på `Vaktliste.planlagt_slutt`.**
  `Vakt.avsluttet` betyr «vakta ble avsluttet» — en hendelse — og kan ikke bære
  et anslag man flytter på. Spennet er det bemanningskurven tegnes over.
- **Plan og faktisk er fire felter, ikke to.** `fra_tid`/`til_tid` er planen,
  `mott_at`/`av_vakt_at` hva som skjedde. Avviket er informasjonen.
- **«Ny planlagt vakt» lager en `core.Vakt` med `er_aktiv=False` og lar `aktiv_vakt_id`
  stå.** Oktobervakta skal kunne planlegges i august uten at pasienter og oppdrag
  registrert i dag scopes til den. Kopiering av oppsett tar ressursene, **aldri**
  personene — en liste ingen har sagt ja til ser ferdig ut.
- **Skrivinger som kan bryte en unik-skranke står i `transaction.atomic()`.** Databasen
  er fasit for duplikater, men en `IntegrityError` som fanges uten savepoint etterlater
  transaksjonen ubrukelig: sesjonslagringen feiler på vei ut, og brukeren får en naken
  400-side i stedet for feilmeldingen viewet formulerte.

## Registrene og verdimengdene

- **Registrene administreres på `/vaktliste/`, ikke i Django-admin.** Den
  flaten er kun rutet under `DEBUG` (S1), så `vaktliste/admin.py` er et
  utviklerverktøy — et register som *bare* finnes der, finnes ikke for brukeren.
  `SjekkAtIngenPekerPaaDjangoAdminTests` skanner alle maler for lenker dit.
- **Mannskapet er en fane på planleggingssiden; korps og kompetanser ligger i
  «Innstillinger»** (30. aug. 2026). `/vaktliste/registre/` er lagt ned.
  Argumentet for en egen side — registrene er globale, fanene gjelder én vakt —
  holdt ikke i bruk: et klikk dit kostet plassen i planleggingen, og mannskap
  og ressurser er nettopp de to man veksler mellom. **Både fanen og
  «Innstillinger» står uten vaktliste**, og fanen velges automatisk da: korps
  må inn før mannskap, og mannskap før noen kan settes på vakt.
  `mkMannskap()` tegner registeret, `apneVerdier(navn)` åpner korps eller
  kompetanser — lista og skjemaet i **samme** vindu, siden vinduet selv åpnes
  fra «Innstillinger». En lagring kaller `_lastRegisterOgListe()`: navnene
  står i planleggingens nedtrekk også.
- **`Ressursgruppe` er typen, og den er en tabell** (30. aug. 2026 — lå i `choices.py`
  før det). Gruppa gjør tre ting samtidig, og det er derfor den er én ting og ikke tre:
  ikonlegger fanen, samler bemanningskurven, og avgrenser rollene. Ikonet er et felt —
  feil ikon er en skjønnhetsfeil, en manglende gruppe er en vaktliste man ikke får satt
  opp. Migrasjon `0007` seeder de seks standardgruppene; testene slår dem opp med
  `test_helpers.gruppe()` framfor å lage sine egne, slik at seeding som slutter å virke
  blir synlig.
- **Rollen heter `Ressursrolle`, hører til en `Ressursgruppe`, og administreres inne i
  ressursen.** Den gjelder plassen på ressursen — lagleder *på bilen* — ikke vakta;
  «vaktrolle» leste som noe man har på hele vakta. Gruppa er riktig nivå og ikke den
  enkelte ressursen: «Sjåfør» hører hjemme på hver ambulanse, og har du tre av dem vil du
  lage rollen én gang. Navnet er derfor unikt *per gruppe*. Nedtrekket i raden filtrerer
  på tre ting, og hvert ledd er en egen feil å gjøre: gruppa, `er_aktiv`, **og den rollen
  raden alt står på** — uten det siste forsvinner en deaktivert rolle fra sin egen rad ved
  neste tegning, og velges bort i stillhet.
- **Sletting av en ressurs ligger bak «Rediger ressurs» og krever bekreftelse to ganger.**
  CASCADE tar skiftene. Dialogen stopper feilklikket; `{"confirm": true}` i kroppen stopper
  et kall som treffer URL-en uten å mene det. De to er ikke samme sperre.
- **Ressursgruppene kan endres, deaktiveres og slettes** (16. sep. 2026, punkt 4). Serveren
  har støttet PUT hele tiden; det manglet knapper. Tre regler:
  - **En gruppe i bruk slettes ikke** (André: «de som er i bruk på vaktlister nå må jo få
    bli») — `Ressurs.gruppe` er `PROTECT`, og viewet svarer med hvor mange ressurser det
    gjelder og peker på `er_aktiv` som veien ut.
  - **`er_aktiv` hadde ingen vei inn.** Feltet fantes fra 30. aug., nedtrekkene respekterte
    det (`gruppaHarPlass`, og ressursens egen gruppe beholdes), og ingen skjerm kunne sette
    det. Det er den verste sorten hull: mekanismen virker, så ingenting feiler, den er bare
    uoppnåelig.
  - **`Ressursrolle.gruppe` er `CASCADE`.** En gruppe *uten* ressurser lar seg slette — og
    tok rollene sine med seg uten et ord. Sletting av en slik gruppe gir nå 409 med
    antallet, og krever `{"confirm": true}`. Bekreftelsen kreves **bare når det finnes
    roller**: et ekstra klikk på en tom gruppe er en vane man slutter å lese, og da er
    bekreftelsen verdiløs den gangen den betyr noe.
- **De øvrige verdimengdene sorteres alfabetisk — det finnes ingen `rekkefolge` å
  vedlikeholde.** `Ressurs` er unntaket, fordi der styrer den fanerekkefølgen, og
  der settes den automatisk til opprettelsesrekkefølgen. Sorteringen bruker
  `Norsk('navn')` (`core/sortering.py`, 26. sep. 2026): Æ Ø Å sist, likt i SQLite
  og PostgreSQL. Med `Lower(...)` sto Ærø øverst og Ørsta blant O-ene på Railway.
- **ID-er fra klienten går gjennom `views._int()`.** Et nedtrekk med «Ingen valgt»
  sender `''`, ikke `null`, og den strengen i et FK-filter gir `ValueError` — altså 500
  der brukeren skulle fått «velg korps». `or None` dekker den tomme strengen, men ikke
  en ikke-numerisk.

- **Kostbehov/matallergi lagres ikke** (art. 9 — besluttet holdt utenfor portalen), og
  `Mannskap.notat` er unntatt verdilogging i audit (`signals.FELT_UTEN_VERDILOGGING`).

## Kompetanse, roller og rekkefølge

- **`Kompetanse.bygger_paa` er en stige.** Har personen AFØR, skjules VFØR og
  GFØR i alle lister — `services.synlige_kompetanser()`. Ringer stoppes ved
  skriving; en ring som likevel finnes gir avkortet kjede, ikke evig løkke.
- **`Ressursrolle` har en rangering, og den er data** (16. sep. 2026, André: «rollene
  sorteres meningsfullt — leder øverst, hospitant nederst»). Alfabetisk satte «Hospitant»
  over «Lagleder». `rekkefolge` + `Meta.ordering = [gruppe__rekkefolge, rekkefolge,
  Lower(navn)]`; navnet avgjør bare uavgjort. **Ikke en liste i koden:** rollene seedes
  ikke med faste navn — de kom fra det som fantes ved migrasjon `0007` — så en hardkodet
  rangering ville truffet noen installasjoner og ikke andre. Samme begrunnelse
  `Ressursgruppe` fikk 30. aug.
  - **En ny rolle havner sist, og regelen ligger i `Ressursrolle.save()`.** Rollene
    opprettes av den generiske registerfabrikken i `views_registre`, som bare kjenner
    tekstfelter (`ekstra_felt` gjør `.strip()`); et heltall måtte fått et unntak inni
    fabrikken, og da sto regelen der for alle tre verdimengdene mens bare én har den.
    Telleren er **per gruppe** — «Sjåfør» på ambulansen og på laget er to rader.
  - **Omsorteringen sender hele lista** (`PUT api/roller/rekkefolge/`, `kan_lede`), ikke
    «opp» per rad: to kall som krysser hverandre bytter to par og etterlater en rekkefølge
    ingen ba om. Serveren krever **nøyaktig** gruppas roller — et delvis sett ville gitt
    noen rader nye tall og latt resten stå, og det er også den eneste måten å oppdage at
    klienten og serveren ser ulike lister.
- **Radene i en ressurs sorteres på tid, så rollens rangering, så navn**
  (`Vaktpost.Meta.ordering`, 16. sep. 2026 — André: «en enhet/lag som har i synkende
  rekkefølge lagsmedlem, lagleder, lagsmedlem, hospitant … flyttes ikke i enheten etter sin
  rolle»). Laget sto i innsettingsrekkefølge, og da må man lese hver rad for å finne
  lederen. Uten dette leddet var `Ressursrolle.rekkefolge` bare en sortering av
  *nedtrekket* — den styrte ikke radene den beskriver. **Tida vinner over rollen:** en
  hospitant som møter 08 står før en lagleder som møter 16, ellers slutter lista å være
  kronologisk.
  - **`nulls_last`/`nulls_first` står eksplisitt, og det er ikke pynt.** PostgreSQL (prod)
    legger NULL sist i stigende sortering, SQLite (dev) legger dem først. Den gamle
    kommentaren her påsto at ledige plasser sto først «innenfor samme starttid» — sant i
    SQLite, aldri i prod, og udekket av noen test. En rad uten rolle hører nederst; en
    ledig plass står først blant sine egne.
  - Klienten sorterer **ikke** (`_posterFor()` filtrerer), så rekkefølgen er serverens.
- **Navn endres i raden, med `_redigeringsrad()` — én form for hele modulen** (16. sep.
  2026, André: «Det bør gå relativt automatisk ved endring av rollenavn, se andre navn i
  enheten»). Rollen hadde **ingen** redigering: man måtte slette og opprette, og
  `Vaktpost.rolle` gjør en rolle i bruk uslettelig — en omdøping var altså umulig. Gruppa
  fikk en `prompt()` tidligere samme dag, som er *oppdragsmodulens* idiom; to former for
  samme handling i samme modul er to kilder som glir fra hverandre.
  - **Redigering i raden, ikke i et vindu på et vindu.** Rollevinduet er alt en modal.
  - **Tilstanden (`rolleRedigeres`, `gruppeRedigeres`) ligger i JS, ikke i DOM-en** — samme
    grunn som `ressursApen`: lista bygges på nytt ved hver lagring, og en `<input>` i
    markupen ville forsvunnet med den. De er `let` på toppnivå, så en node-test må sette
    dem selv (`build_harness` henter bare funksjoner).
  - **Lagring kaller `_lastRegisterOgListe()`, ikke bare rollelista.** Rollenavnet står i
    nedtrekket på hver rad i regnearket også; hentes bare lista, viser skiftene det gamle
    navnet til neste sidelasting.

## Besetningen — koblingen til `/oppdrag/`

**Besetningen i sentralbordet (fase 6) går én vei: `vaktliste` → `oppdrag`.**
Oppdragsmodulen importerer **ikke** vaktlista; `oppdrag-sentral.js` henter
`/vaktliste/api/enhet/<pk>/besetning/` og rendrer svaret.
`OppdragImportererIkkeVaktlista` leser importene med AST og håndhever det. KO henter
ressursene **uten** enhet og **på vakt nå** fra `api/ressurser/uten-enhet/` — samme gate.
**Statistikken** (`vaktliste/statistikk.py`, 7c) leser oppdragene samme vei; krever `les_alle`.

- **Gatet på `les` i vaktliste**, ikke i oppdrag — komposisjonsregelen fra
  rollemodellen §5. Malen får et flagg via `har_tilgang(..., 'vaktliste', ...)`:
  en slug gjennom `core`, ikke en import.
- **Svaret bærer navn, rolle, innsjekkstatus, telefon og ISSI** (de to siste fra
  12. sep. 2026). Ikke kompetanser, ikke `notat`, ikke e-post eller konto —
  sentralbordet skal kunne ringe bilen, ikke lese personalmapper. `Mannskap.issi`
  (`0015`) er nødnettsterminalens nummer, tekst med ledende nuller.
- **Bare skiftene som dekker nå**, og **404 når enheten er ukoblet**: ubemannet
  og ukoblet er ulike svar på ulike problemer.
- **Lista i drift vinner — ikke arkivert, sist satt i drift (`lister_i_drift()`); ellers portalens aktive vakt** (12. sep. 2026 — «koblingen
  fungerer ikke»: vaktlista som kjørte lå på en annen vakt enn den aktive). Dekker
  ingen skift nå, sendes **neste skift** med (`neste`, `neste_fra`), så svaret er «ingen
  nå, Kari fra 16:00». 404-meldingen skiller «koblet i en annen vakt» fra «ikke koblet
  noe sted» (`services.koblet_i_annen_vakt`) — det kostet André en kveld 30. aug.
- **Rekkefølgen sorteres i Python.** `rolle` er nullbar, og SQLite (dev) og
  PostgreSQL (prod) plasserer NULL i hver sin ende.

## Belastning, budsjett og timeoversikt

**Planleggingstall (fase 5) varsler, de sperrer ikke.** `services` regner timer, skift,
lengste skift, korteste hvile og **overlapp** per person mot `Belastningsgrenser` (én rad,
organisasjonens — `skriv_leder` flytter dem for *alle* vaktlister). Fargen er gul
(`--vl-varsel`), ikke rød: noen ganger må noen ta et langt skift, og da skal listen si det høyt.

- **Budsjettet står øverst i «Planlegger»** (15. sep., `FORSLAG_PLANLEGGERFANE.md`):
  `planleggingstall()` gir `satt_opp`, `bemannet` og `probono` side om side, fordi hvert av
  dem alene lyver litt; avstanden mellom de to første er arbeidslisten. `Vaktliste.timetak`
  er *denne* vaktens tak, `igjen` måles mot **satt opp**. Taket settes i
  `vaktliste_detalj_view`s PUT med start og slutt, og er derfor `skriv_leder`.
- **Budsjettallene sendes bare til den som `ser_alle_korps`** — for en `les` ville de vært
  et aggregat over skift hun ikke får se. Ellers `planlegging: null`, og klienten tegner
  ingenting. `kanSetteTak()` leser serverens `kan_sette_tak`, ikke `MODUL_TILGANG`.
- **«Oversikt» er en talltabell** (16. sep., André: «Må være en faktisk oversikt»): én rad
  per enhet per tidsblokk, med sumrad per dag. **Totalt bruker `_sumTimer`**, ikke
  `timer × plasser` (probono og ugyldige spenn teller null — ellers tre steder som skal si
  det samme, med tre tall), og **sumraden teller de ledige plassene** (en mutant fant at
  den ikke gjorde det). Navnene står i typefanen, og utskriften skriver ut fanen man står i.
- **Et fanenavn kan ikke være en statusetikett** (`FanenHeterTimeoversiktTests`): fanen het
  «Planlegging» til 16. sep., samme ord som statusmerket. `choices.STATUS_VALG` bærer ordet
  fortsatt — et søk-og-erstatt ville døpt om statusen.
- **Overlappende skift gir hvile 0**, og `_overlappstimer()` (sum minus union) står ved
  siden av, så `timer - overlapp` er tilstedeværelse. **Summen korrigeres ikke, den
  navngis** — et tall som stille retter seg selv ville skjult dobbeltbookingen. Probono
  teller her: kroppen skiller ikke på lønn. Overlappet har ingen grense å måle mot.
- **Faktisk tid regnes bare av ferdige skift** — et pågående skift ville gitt et tall som
  endrer seg mens man ser på det.
- **`_hviletider()` og `_dagbolker()` sorterer og regner selv**, uten å hvile på kalleren
  (begge funnet ved mutasjonstesting). `_dagbolker()` regner dagen i **lokal tid**: 00:30
  norsk tid er 22:30 UTC dagen før. En test med falske skift må derfor bære **UTC**, som
  ORM-en gjør; bærer den norsk tid, går mutanten grønn.

## Innsjekk, stempling og drift

**Drift (fase 4) er en innsjekk-port, ikke en livssyklus.** `Vaktliste.status`
har to verdier, og `drift` betyr én ting: møtt/av vakt er åpen. Overgangen går
begge veier og rører ingen stempler.

- **Retningen og overgangen står i URL-en**, ikke i kroppen —
  `drift/<start|stopp>/` og `stempling/<handling>/`. Et veksle-endepunkt gir et
  kappløp når to trykk kommer tett. Samme grep som oppdragsmodulen.
- **Stemplingsreglene er data**, `services.STEMPLINGER`, med forutsetninger:
  «av vakt» krever «møtt», og «angre møtt» krever at «av vakt» ikke står. Uten
  dem finnes rader der `er_tilstede` ikke svarer på noe.
- **`kan_stemple()` er ikke `skriv_handling`** (avklaring 11.3). Korps-føreren
  fører sitt eget korps, men «Tilstede nå» skal ha én ansvarlig. Funksjonen er
  et kall videre til `kan_skrive_alt`, og finnes for at beslutningen skal ha et
  sted.
- **Tilgangsporten svares før driftporten.** En korps-fører som trykker skal
  få vite at hun ikke har lov, ikke at lista ikke er i drift.
- **«Tilstede nå» utledes, aldri lagres** (`Vaktpost.er_tilstede`). To kilder
  til samme sannhet går i utakt første gang noe feiler halvveis — og denne
  brukes til å telle hoder ved brann.
- **Drift er planleggingsraden pluss innsjekken foran** (12. sep. 2026 — André:
  «Kunne redigere mannskaper selv om vi er i drift modus»). Fram til da var
  driftraden en egen, smal form uten tidsfelt, kompetanse og merknad, med
  redigering bak blyanten; det holdt ikke i bruk. `_driftrad` er stempelet (44 px
  høy knapp, først i raden) + `_plancellene`, som `_planrad` også bruker.
  Prisen er bredden: `.vl-tabell-drift` har eget `min-width` over regnearkets, og
  `RessurstabellensBreddeTests` regner ut at tidskolonnene rommer feltet i begge
  former.
- **Klokka setter lista i drift ved vaktas start; knappen er overstyringen** (30. sep.
  2026). Reglene: `services.skal_settes_i_drift()` — én gang, bare lister planlagt i
  forveien, aldri stenging. Går i `FilutsendingMiddleware` og i viewene; auditraden
  skrives `uten_request()`, og `drift_automatisk` sier at det var klokka.
- **«Sett i drift» bor i «Innstillinger»** (12. sep. 2026), i bolken for én liste,
  og tegnes av `tegnDriftknapp()` både ved lasting og når vinduet åpnes. Statusmerket
  i vaktlinja (`tegnStatus`, `.vl-status.vl-drift`/`.vl-planlegging`) sier formen med
  ikon og fet skrift, i drift med pulserende prikk. Drift inn og ut auditlogges på
  feltnivå (`vaktliste/signals.py`, `vaktliste_vaktliste`).
- **Skift og ressurser auditlogges på feltnivå** (12. sep. 2026 — «for å få logget det
  meste»): `vaktliste_vaktpost` og `vaktliste_ressurs`, opprettet/endret/slettet med hvem.
  Stemplene er feltendringer på `mott_at`/`av_vakt_at` og trenger ingen egen kode.
  `Vaktpost.merknad` er fritekst og logges uten verdier, som `Mannskap.notat`. Derfor
  **ingen `bulk_create` på disse modellene** — den hopper over signalene; `kopier_oppsett`
  gikk i den fella.
- **Klienten har én `data-action` per overgang**, ikke én generisk:
  klikkdelegeringen i `portal-utils.js` sender ett argument. `STEMPLINGER` i
  `vaktliste.js` og i `services.py` holdes like av `StemplingsnavnTests`.

## Planleggeren — grunnlaget for vaktlista

**Planleggeren lager grunnlaget for vaktlista** (15. sep. 2026, `services.generer_grunnlag`,
`POST api/vaktlister/<pk>/generer/`, `kan_lede`). Du sier «tre firemannslag 14–22, én
ambulanse 15–03, én på åttetimers rotasjon», og etterpå finnes ressursene og de tomme
plassene — klare til å fordeles og spisses i fanene som alt virker.

| Regel | Hvorfor |
|---|---|
| **Ressursen er subjektet, skiftvinduene hører til den** | Sola 56 har to adskilte 12-timersvakter (fre./lør. 15–03). Var linja vinduet, hadde hun blitt to ulike biler |
| **Ett skiftvindu er ett skift** | `skiftlengde`, som delte vinduet i bolker, er fjernet 15. sep. 2026 (André: «har vi noe behov for skiftlengde?»). En rotasjon settes opp som de skiftene den er; «Nytt skiftvindu» begynner der det forrige sluttet |
| **Plassene hører til vinduet, ikke til ressursen** | André: «noen ganger ønsker man å ha mindre og mer plasser på enkelte skift visse deler av døgnet.» Samleplassen kan ha seks 14–22 og to 22–06 — én ressurs med to vinduer. Det var også grunnen til at `skiftlengde` måtte gå: den ga alle sine genererte skift samme antall |
| **«Antall» finnes ikke for grupper i ett eksemplar** | Samleplass og KO (`flere_enheter=False`). Det kan bare være én, serveren avviser alt annet, og en kontroll som ikke gjør noe er en kontroll man lurer på |
| **«Legg til ressurs» står mellom siste rad og «Lag grunnlaget»** | André: «for nå er det lett å tro at man bare lager en ressurs og så er man ferdig». I hodet leste den som «start her»; mellom radene og knappen leser den som «legg til én til», og panelets rekkefølge blir den man arbeider i |
| **Feltendringer oppdaterer tallene på plass; strukturendringer tegner på nytt** | `tegnPanel()` bygger panelet med `innerHTML`, så feltet man står i erstattes og fokus forsvinner. `datetime-local` melder `change` per segment, så man mistet feltet etter hvert tall (André: «jeg kan bare ta inn ett tall om gangen»). `planleggerTegnTall()` setter `textContent` på `[data-vindutall]`, `[data-linjetall]` og `[data-plantall]`. Gruppevalget er unntaket — raden skifter form, og et nedtrekk er man ferdig med |
| **Plassene fødes som planlagt kladd** | `er_planlagt()` — usynlig for korpsene til lederen deler dem ut. Samme grunn som at `kopier_oppsett` aldri tar personene |
| **Bare kladden på de ressursene oppsettet nevner røres** | Korpsreserverte, `alle_korps` og **alle** bemannede står. Reservasjonen leses av `reservert_korps()`, ikke av feltet — ellers slettes en hel bils plasser fordi ressursen bærer korpset. En ressurs *utenfor* oppsettet lar generatoren være i fred: å fjerne en ressurs er en sletting, og den ligger bak de to bekreftelsene i «Rediger ressurs». Den gamle `erstatt_kladd`-bryteren, som ryddet kladd på hele lista, er borte 15. sep. 2026 av samme grunn |
| **Ingen `bulk_create`, alt i én `transaction.atomic()`** | Signalene, og: genereringen sletter kladd før den skriver, så en feil halvveis ville etterlatt lista tommere enn før man trykket |
| **`?forhaandsvis` regnes av samme kode** | Samme endepunkt, `_planlegg` + `_sammendrag`. En forhåndsvisning som regner på egen hånd viser før eller siden noe annet enn det som skjer |

**Feltet heter «plasser per skift», ikke «antall folk».** André beskriver Haugesund 56 som
«4 stk fordelt på 2 lag»; bilen har to seter, og de fire er bemanningspoolen. Regnestykket
står under raden — «6 skift × 1 ressurs = 12 plasser, 96 t» — nettopp for at den
oversettelsen skal være synlig før man trykker. Plassene står ikke som et ledd der, fordi
de kan være ulike fra vindu til vindu: hvert vindu viser sitt eget tall, raden summen.

**Parsingen av `plasser` står i `services._linjens_skift()`, ikke i viewet.** Viewet gjorde
`_int(...) or 1`, og da ble et eksplisitt `0` stille til 1 — en regel som later som den
avviser noe.

**Klientens tall er et anslag, serverens er fasit.** `_planleggerVindutall()` speiler
`_linjens_skift()` for å tegne regnestykket mens man skriver; `apneGenerer()` henter
serverens forhåndsvisning før bekreftelsen. `PlanleggerfanenTests` måler at de to sier det
samme på Andrés egne eksempler.

**Planleggeren leser oppsettet tilbake fra vaktlista** (15. sep. 2026 — André: «når en har
lagt grunnlag og vil redigere så er det ikke lenger i planlegger»). Den **husker ikke det
du skrev; den leser hva som står** — en husket kladd og virkeligheten glir fra hverandre i
det øyeblikket noen retter et skift i regnearket, og da ville et trykk på «Lag grunnlaget»
rullet den rettelsen tilbake.

| Regel | Hvor |
|---|---|
| Én rad per ressurs, vinduene gruppert på plassenes tider | `planleggerLesTilbake()` |
| Står det ingenting i oppsettet, leses det tilbake — har du skrevet noe, røres det ikke | `planleggerSikreLinjer()`, kalt av `tegnPanel()` |
| `ressurs_id` gjør raden til en **redigering**; gruppa og navnet følger ressursen | `services._planlegg` |
| «Plasser» er vinduets hele bemanning, ikke et påslag — de som står telles fra | `services._nye_plasser()` |
| Beholdningen forbrukes **per vindu** | to like vinduer i samme rad ville ellers begge trukket fra de samme plassene |
| Panelet viser oppsettet, bekreftelsen viser endringen | `_sammendrag` teller nye ressurser og nye plasser, og `fjernes` ved siden |

**Tilstanden settes på vei inn i panelet, ikke i byggeren.** `mkPlanlegger()` skal kunne
kalles uten å endre noe. Mutasjonsprøvd 15. sep. 2026: testene kalte `planleggerSikreLinjer()`
selv, så `tegnPanel()` kunne slutte å kalle den uten at noe ble rødt — og da var
planleggeren tom igjen etter en generering, altså nøyaktig feilen den skulle rette.
`PlanleggerenTegnesMedOppsettetTests` har egen harness med den **ekte** `tegnPanel()`,
fordi de andre planleggertestene stubber den for å telle omtegninger.

**Budsjettlinja og belastningsfanen leser de samme tallene**, og regelen står som én
funksjon: `faneTrengerBelastning(id)` i `vaktliste-kjerne.js`. Den har to lesere —
fanevalget i `visFane()` og korpsvelgeren i `velgKorps()`. Sto planleggeren utenfor, var
taket og timene usynlige nettopp der de skal styre arbeidet, og synlige bare i fanen som
rapporterer i etterkant; det var tilstanden på en ny vaktliste til 15. sep. 2026, uten at
noe feilet.

## Pausene — per ressurs, og KO leser dem (23. sep. 2026)

`vaktliste.Pause` og `vaktliste/pauser.py`; docstringen der har hele begrunnelsen. André
svarte på fem spørsmål før koden: **per lag/ressurs**, **teller i timene**, **lederen**
legger dem inn, **mannskapet ser dem** men admin kan skjule dem, og **en regel i
planleggeren nå**.

| Regel | Hvorfor |
|---|---|
| Per ressurs, ikke per plass | Tavla i `/ko/` flytter lag, ikke personer. Pause per plass kommer bare om en ekte vakt ber om det |
| Innenfor skiftene (sammenslått, så 21:45–22:15 over et skiftbytte går), høyst fire timer, aldri to over hverandre | Samme tre regler som KOs pauser — ellers kunne en pause lagt inn her blitt avvist på tavla |
| **Rører ingen timer**: budsjettet, timeoversikten og belastningen er uendret | «Ja» på «teller pausen i timene». Mannskapet er på vakt og kan kalles inn |
| `kan_lede`, som planleggeren. `les` ser dem (ingen korpsfilter — de hører til ressursen) | André: «leder» |
| **Regelen** står på ressursen (`pause_etter_min`, `pause_min`, `pause_forskyv`) og leses tilbake som resten av oppsettet. Pausene den lager er `fra_regel` og lages på nytt ved hver generering; en pause lederen har lagt inn eller rettet, står og vinner over regelen | Samme skille som kladden og det som er delt ut |
| **Forskyvningen telles per gruppe og skiftstart over hele planen**, ikke per linje — og et lag på «samtidig» tar også en plass | Leses oppsettet tilbake, er hvert lag sin egen linje; en teller per linje satte alle lagene på samme klokkeslett. Uten plassen la et forskjøvet lag seg oppå dem |
| For kort skift: ingen pause. Forskjøvet ut av skiftet: `Planleggerfeil`, ikke en stille utelatelse | Et lag som mangler pausen sin er noe lederen må få vite |
| Utskrift og fila på e-post viser dem til admin skrur av `vaktliste_vis_pauser` (portalinnstillingene) | På skjermen står de alltid; det er papiret som går til mannskapet |
| Auditlogges (`vaktliste_pause`) | Oppsett, som skiftene |

**KO leser pausene uten å kopiere dem** — `ko.tavle.effektive_pauser`, retningen `ko` →
`vaktliste`. Se `ko/CLAUDE.md`.

## Overnatting — hvem sover hvor, for brannsikkerheten (25. sep. 2026)

`vaktliste/overnatting.py`; reglene og Andrés svar står i docstringene der. Det man må vite
før man rører *annen* kode:

- **Én person, ett sted, per natt — også på tvers av vaktlistene** (`(mannskap, natt)` er
  unik). En seng på en annen vakt flyttes aldri herfra.
- **Alle med `les` ser hele lista, men telefonen og skiftdetaljene følger korpsfilteret**
  (`vis_telefon`). Alle får `er_paa_vakt` (C1).
- **Dataene står i vaktlistas hovedsvar** (`data_for`), så de følger offline-kopien.
- **Brannlista står i fila på e-post**, og `fil.signatur()` tar den med bare når den finnes.

## Drift-reserven: fil på e-post og offline

To måter lista overlever at noe er nede — og begge er reserver, ikke
hovedveier.

- **Vaktlista som fil på e-post er reserven** (12. sep. 2026, notatet §12):
  `vaktliste/fil.py` bygger `templates/vaktliste/fil.html` — selvstendig, uten
  `{% static %}` og uten ikon-partialen (unntatt i `core/tests_manifest.py`). Telefon og
  ISSI er med, **ikke** e-post, notat eller merknad. Mottakerne og bryteren for «Sett i
  drift» er `AppSetting`-nøkler (`fil.MOTTAKERE_NOKKEL`, `fil.VED_DRIFT_NOKKEL`) satt
  under portalinnstillingene; `send_fil()` kaster aldri og lager alltid en
  `Utsending`-rad (auditlogget), og drift-viewet sender *etter* at drift er lagret —
  e-post nede skal ikke stenge innsjekken. AHASend-transporten sender vedlegg som
  base64 (`_vedlegg`). **Intervallsendingen** (13. sep. 2026, `fil.send_planlagte()`,
  `INTERVALL_NOKKEL`/`BARE_ENDRET_NOKKEL`) kjøres av
  `vaktliste.middleware.FilutsendingMiddleware` — trafikken er klokka, som for
  backup — og sammenligner `Utsending.innhold_sha256` mot den sist *sendte*; klokka går
  fra forrige *forsøk*. Middlewaren tas ut under test i `settings.py`, som
  backup-planleggeren.
- **Offline drift på `/vaktliste/`** (13. sep. 2026, notatet §13): service workeren
  `static/js/vaktliste-sw.js` serveres av `vaktliste.views.sw_view` på `/vaktliste/sw.js`
  (en worker styrer bare stier under sin egen; uten innlogging, unntatt i
  `patients/tests_modul_dekorator.py`, med egen CSP begrenset til `'self'`).
  `avgjor()` er den ene regelen: API-GET nett først med kopi som reserve (header
  `X-Vl-Kopi`), siden nett først, statisk kopi først; **aldri POST, aldri en
  omdirigering** (innloggingssiden), og **ingen datakopi eldre enn 24 timer**
  (`erForGammel`). **«Logg ut» sender `Clear-Site-Data: "cache", "storage"`** (13. sep.
  2026) — Cache Storage, localStorage og workeren ryddes i ett på en delt drifts-PC;
  cookies røres ikke, og står noe i køen, spør knappen først (`ui-actions.js`, 10. okt.). Køen for møtt/av vakt ligger i `vaktliste.js`
  (`koLes`/`koSkriv`, `_leggIKo`, `_projiserKo`, `synkKo`, `tegnOffline`) — samme
  mønster som bilens kø i `oppdrag-enhet.js`. **Nøkkelen er per bruker** (`brukerNokkel()`,
  L17, 8. okt. 2026): en annen konto på samme PC spiller ikke av køen. **Står noe i kø, går alt i kø** —
  rekkefølgen er regelen. `stempling_view` leser `tidspunkt` i kroppen, og
  `services.vurder_klienttid` klipper det urimelige. Den gamle `OFFLINE_MODE`-en er
  borte; Django-admin rutes bare under `DEBUG`.
