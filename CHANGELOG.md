# Changelog – Sanitetsportalen

Nyeste endringer øverst. Legg til ny seksjon med `## YYYY-MM-DD` ved hver arbeidsøkt.

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
