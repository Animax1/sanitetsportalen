# Vaktlistemodulen (vaktliste/)

> **Modulfil.** Den lastes når noen arbeider i `vaktliste/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Fase 1–2 levert (registre, mannskap, oppsett og planleggingsside på `/vaktliste/`);
fase 3–7 gjenstår — se `docs/BESLUTNING_VAKTLISTE.md`, som er besluttet i sin helhet.

| Regel | Hvor |
|---|---|
| Badgen på personen | `Mannskap.korps`, arvet av kontoen via `Mannskap.user` |
| Reservasjonen på ressursen | `Ressurs.korps` — tom betyr **vaktlederens bord**, ikke fritt fram |
| Reservasjonen på plassen | `Vaktpost.korps` — overstyrer ressursens, `services.reservert_korps()` |
| Begge halvdelene sjekkes samlet | `services.kan_sette_vaktpost()` |
| Ett skift er én rad | `Vaktpost`, med plan og faktisk i hvert sitt feltpar |
| Planlagt vakt rører ikke pekeren | `services.opprett_planlagt_vakt()` |

- **`Mannskap.korps` er badgen** tilgangsmodellen hviler på fra fase 3:
  `skriv_handling` betyr her «fører sitt eget korps» (avgrenset av badgen, ingen
  innsjekk), ikke stempling som i oppdrag. Matrisen trenger derfor en etikett per
  modul per nivå (§4.5) før nivået deles ut.
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
  **bare når den som lagrer er `skriv_leder` eller global admin** (13. sep. 2026, M5 —
  først `skriv_full`+, snevret samme kveld: «Fiks alt inkludert kobling»): koblingen
  flytter en badge, og den som bemanner skal ikke velge hvilken konto som blir hvem.
  Alle andre lagrer e-posten; merket sier at kontoen finnes, og lederen kobler.
  **Korps-føreren uten badge** ser alle korps, men fører ingen — sida sier det
  (`mangler_badge`), og «Mannskapsregisteret er tomt» leser registeret hun *ser*
  (`registeretErTomt`), ikke lista over dem hun får sette.
  **Adminkontoer er aldri mannskap** (12. sep. 2026: «Den er utenfor.») —
  `_koblbare_kontoer()` er det ene stedet som sier hvem som kan kobles, og e-postmerket,
  autokoblingen og kontolista leser alle derfra; kobling for hånd til en adminkonto gir
  400. `konto_finnes` i svaret sier om en bruker med adressen finnes, regnet av ett sett
  e-poster, ikke én spørring per rad.
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
- **Vaktlistevelgeren må ha `data-hendelse="change"`** (16. sep. 2026). Uten den fyrer
  klikkdelegeringen i `portal-utils.js` på *klikk* — med verdien som alt sto der — og
  ikke når man velger. Symptomet var «treg»: hvert forsøk på å åpne nedtrekket hentet
  lista man allerede så, og byttet skjedde først ved neste klikk på velgeren.
  `VelgerenFyrerPaaEndringTests` skanner malene: et `<select>` eller `<textarea>` med
  `data-action` skal alltid oppgi hendelsen sin. `<input>` er utenfor med vilje — en
  knapp er et `<input>` også, og der *er* klikk riktig hendelse.
- **Sida kommer tilbake til lista man sto på**, ikke til den øverste
  (`forsteListe()`/`huskListe()`, `localStorage`). ID-en sjekkes mot lista serveren
  faktisk sendte: en vaktliste kan være slettet, eller tilgangen borte, siden sist — og
  da er øverst riktig, som første gang. **Per nettleser, ikke per konto:** det er en
  bekvemmelighet, ikke en innstilling, og «Logg ut» sender `Clear-Site-Data`, som rydder
  den på en delt drifts-PC. Lagringen kaster i privat modus, så begge kallene står i
  `try/catch` — en glemt liste er en bagatell, en side som dør på oppstart er det ikke.
- **Offline drift på `/vaktliste/`** (13. sep. 2026, notatet §13): service workeren
  `static/js/vaktliste-sw.js` serveres av `vaktliste.views.sw_view` på `/vaktliste/sw.js`
  (en worker styrer bare stier under sin egen; uten innlogging, unntatt i
  `patients/tests_modul_dekorator.py`, med egen CSP begrenset til `'self'`).
  `avgjor()` er den ene regelen: API-GET nett først med kopi som reserve (header
  `X-Vl-Kopi`), siden nett først, statisk kopi først; **aldri POST, aldri en
  omdirigering** (innloggingssiden), og **ingen datakopi eldre enn 24 timer**
  (`erForGammel`). **«Logg ut» sender `Clear-Site-Data: "cache", "storage"`** (13. sep.
  2026) — Cache Storage, localStorage og workeren ryddes i ett på en delt drifts-PC;
  cookies røres ikke. Køen for møtt/av vakt ligger i `vaktliste.js`
  (`koLes`/`koSkriv`, `_leggIKo`, `_projiserKo`, `synkKo`, `tegnOffline`) — samme
  mønster som bilens kø i `oppdrag-enhet.js`. **Står noe i kø, går alt i kø** —
  rekkefølgen er regelen. `stempling_view` leser `tidspunkt` i kroppen, og
  `services.vurder_klienttid` klipper det urimelige. Den gamle `OFFLINE_MODE`-en er
  borte; Django-admin rutes bare under `DEBUG`.
- **Kostbehov/matallergi lagres ikke** (art. 9 — besluttet holdt utenfor portalen), og
  `Mannskap.notat` er unntatt verdilogging i audit (`signals.FELT_UTEN_VERDILOGGING`).
- **En ledig plass har tre tilstander** (11.–12. sep. 2026): tildelt ett korps
  (`Vaktpost.korps`/ressursens), **åpen for alle** (`Vaktpost.alle_korps` — alle ser og kan
  fylle; het «utildelt» én dag), eller **planlagt** — lederens kladd, som `les` ikke ser og
  som ingen under `skriv_full` kan fylle (`services.er_planlagt`). `alle_korps` vinner over `korps`. Å dele ut er `skriv_full`,
  og **planlagt går én vei**: en plass som er delt ut tas ikke tilbake til kladden —
  viewet avviser det, og nedtrekket tilbyr «Planlagt» bare så lenge plassen står der. Fanen «Mitt korps» (`mkMittKorps`) viser korpsets tildelte og
  universale plasser på tvers av ressursene; `kanBemannePlass()` i JS speiler serveren
  plass for plass, og `_korpsKropp()` oversetter nedtrekkets tre tilstander til to felt.
- **En ledig plass er en `Vaktpost` uten `mannskap`.** Planlegging begynner med
  behovet, og «å fylle plassen» er én feltendring. Å *opprette* et skift er
  `skriv_full` (vaktleder setter behovet), å *fylle* det krever badge og
  reservasjon som ellers — de to spørsmålene er `services.kan_sette_vaktpost()`
  og `services.kan_rore_vaktpost()`, og de må ikke slås sammen.
- **Å bemanne er å fylle en plass noen andre har satt opp** (15. sep. 2026, André:
  «Det eneste de skal få lov til er å legge inn folk, rolle, og redigere ressursens
  navn — men ikke gruppe, reservering, enhet i oppdragsmodulen og sletting»).
  Korps-føreren setter **hvem**, **i hvilken rolle** og **merknaden** på raden, og
  retter **ressursens navn**. Tidene, antallet plasser, reservasjonen, `alle_korps`,
  `probono` og sletting er oppsett — `services.kan_sette_opp_skift()`, som er et kall
  videre til `kan_skrive_alt` og finnes for at beslutningen skal ha et sted, som
  `kan_stemple`.

  **Merknaden sto blant oppsettfeltene ett døgn, og André tok den ut igjen** (16. sep.
  2026). «Det eneste de skal få lov til» ble lest strengt, og det var feil sted å trekke
  grensen: «Kommer 17:30» er en beskjed om *denne raden*, og den som setter personen på
  plassen er den som vet det. Den følger derfor `kan_rore_vaktpost`, som person og rolle —
  hun når bare radene som er hennes. **`probono` ble stående**, og det er et annet
  spørsmål: det sier hva vakta *koster*, og tallet leses av budsjettlinja for hele lista.

  **Og porten på `mannskap_id` gjelder overgangen, ikke innsendingen** (16. sep. 2026).
  Vinduet sender hele skjemaet, så feltet står i kroppen også når ingen har rørt
  nedtrekket. På en **ledig plass** er det `null` over `null` — og
  `kan_sette_vaktpost(..., mannskap=None)` er `skriv_full`, fordi *å la en plass stå tom*
  er å sette opp et behov. Regelen er riktig; den fyrte bare på en endring som ikke
  skjedde, og korps-føreren fikk 403 på å skrive «mangler sjåfør» i en plass hun har lov
  til å fylle. Viewet sammenligner derfor `ny_id != vaktpost.mannskap_id` først: **en
  skriving som ikke endrer noe, trenger ingen tillatelse til å endre det.**

  **Regelen står som to lister, ikke som en `if` per felt:**
  `services.SKIFT_OPPSETTFELTER` og `RESSURS_OPPSETTFELTER`, lest av
  `services.oppsettfelter(data, felter)`. Fram til da sto `korps_id` og `alle_korps`
  som hver sin `if` ute i viewene, mens `fra_tid`/`til_tid` gikk rett gjennom — og
  det var hullet: dokumentasjonen sa «å opprette en ledig plass er `skriv_full`»
  mens koden bare sjekket badgen. En regel med to lesere skrives én gang.

  **Ett felt hun ikke får sette, velter hele forespørselen** — med vilje, så en
  halvlagret rad ikke finnes. Derfor må klienten sile *før* den sender:
  `bareTillatteFelter()` i `vaktliste-kjerne.js`, med listene speilet fra `services`
  og holdt like av `SkiftetsOppsettfelterTests`. Uten silingen ville et personbytte
  korps-føreren har lov til gitt 403, fordi vinduet alltid sendte alle feltene.

  **Og markupen må si det samme:** «Opprett vakt» og tidsfeltene i regnearket sto på
  `kanBemanne()` — altså badgen — så knappene førte til en vegg. De står nå på
  `kanSetteOppSkift()`. Tidene *vises* fortsatt, som tekst: et felt man kan skrive i
  og ikke lagre er verre enn en tekst, for det ser ut som om endringen gikk igjennom.

  **Et låst felt i et vindu låses med `disabled`, aldri med `readOnly`** (16. sep. 2026,
  meldt fra staging). HTML-standarden lar `readonly` gjelde felter man taster fritt i; på
  `date`, `time`, `datetime-local`, `color`, `file` og avkryssinger er attributtet **uten
  virkning**. Velgeren åpnet seg på iPhone, segmentene lot seg dra, verdien endret seg på
  skjermen — og ble så filtrert bort ved lagring. Det er verre enn å ikke kunne røre
  feltet: man tror man har gjort noe, og ser etterpå at man ikke har.
  `LaaseneVirkerPaaAlleFeltformeneTests` håndhever at `_laasOppsettfelter()` og
  `_laasRessursoppsett()` bruker `disabled`.

  **Og et låst felt skal se låst ut uten å bli uleselig** (André, 16. sep. 2026).
  `disabled` alene gjør det motsatte: Bootstrap demper feltet, nettleseren demper det én
  gang til, og **Safari ignorerer `color` på et deaktivert felt** — den leser
  `-webkit-text-fill-color`. `.vl-laast` gir stiplet kant, dempet flate og full
  tekstkontrast tilbake. Stiplet framfor en ny farge, fordi fargene i modulen alt betyr
  noe (gult varsler, grønt er tilstede) og en strek leses også i gråtoner.

  **Låsen er tre ting samtidig, og derfor én funksjon:** `_laasFelter()` i
  `vaktliste-kjerne.js` setter `disabled`, klassen og hintet som sier *hvorfor*. Et vindu
  som husket to av dem ville sett ut som om det virket. Hintene (`vaktpost-laast-hint`,
  `ressurs-laast-hint`) står i malen, og en test krever at de finnes — `_laasFelter()`
  tier helt når `getElementById` gir `null`.
- **`ressurs_detalj_view` har to terskler i ett endepunkt.** Navnet krever
  `services.kan_gi_nytt_navn()` — bilen heter «Sola 56», ikke «Ambulanse 2», og den som
  står ved bilen er den som vet det. Gruppe, reservasjon, enhetskobling, rekkefølge og
  sletting krever `kan_lede`: de er beslutninger om *hvem ressursen er til for*, og
  flyttes de, flytter de tilgangen til seg selv.
- **Navneretten leser plassene, ikke bare ressursen** (16. sep. 2026). Porten sto på
  `kan_bemanne_ressurs` ett døgn og var i praksis stengt: **«Ny ressurs» spør bare om navn
  og gruppe**, så en fersk ressurs er ureservert, og reservasjonen settes i «Rediger» —
  som er lederens. Regelen slapp derfor bare gjennom de bilene lederen alt hadde delt ut,
  og knappen var borte akkurat der korps-føreren står. `kan_gi_nytt_navn()` spør derfor
  om hun kan bemanne ressursen **eller noen av plassene på den** — samme to nivåer som
  `reservert_korps()`: en samleplass kan stå ureservert og likevel ha fire plasser som er
  Haugesunds. Å navngi er fortsatt ikke å dele ut; oppsettfeltene leser `kan_lede` hver
  for seg.
- **Sletting av et skift er `skriv_full`, også når raden er fylt** (15. sep. 2026).
  Sperren sto bare på de ledige, fordi et hull i bemanningen ikke skal kunne skjules
  ved å slette raden som viste det. Argumentet gjelder ordrett på en fylt rad: sletter
  korps-føreren skiftet framfor å melde forfall, forsvinner plassen og ikke bare
  personen, og lista ser dekket ut. Hun tømmer raden i stedet (`mannskap_id: null`),
  og da står behovet.
- **Vaktas lengde: start på `Vakt.startet`, slutt på `Vaktliste.planlagt_slutt`.**
  `Vakt.avsluttet` betyr «vakta ble avsluttet» — en hendelse — og kan ikke bære
  et anslag man flytter på. Spennet er det bemanningskurven tegnes over.
- **Plan og faktisk er fire felter, ikke to.** `fra_tid`/`til_tid` er planen,
  `mott_at`/`av_vakt_at` hva som skjedde. Avviket er informasjonen. Stemplene settes
  først i fase 4, og da bak `skriv_full`.
- **«Ny planlagt vakt» lager en `core.Vakt` med `er_aktiv=False` og lar `aktiv_vakt_id`
  stå.** Oktobervakta skal kunne planlegges i august uten at pasienter og oppdrag
  registrert i dag scopes til den. Kopiering av oppsett tar ressursene, **aldri**
  personene — en liste ingen har sagt ja til ser ferdig ut.
- **Skrivinger som kan bryte en unik-skranke står i `transaction.atomic()`.** Databasen
  er fasit for duplikater, men en `IntegrityError` som fanges uten savepoint etterlater
  transaksjonen ubrukelig: sesjonslagringen feiler på vei ut, og brukeren får en naken
  400-side i stedet for feilmeldingen viewet formulerte.
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
- **En `<td>` må forbli en `table-cell`.** `display: flex` direkte på en celle tar den ut
  av tabellens boksmodell, og alt etter den forskyves i forhold til overskriftene —
  `table-layout: fixed` hjelper ikke. Legg layouten på et element *inne* i cella.
  `TabellcellersLayoutTests` leser klassene som står på `<td>` **hvor som helst** i
  modulens JS og håndhever regelen for dem alle.
  - **Hvitliste, ikke svarteliste** (16. sep. 2026): en `<td>` får ha `display: table-cell`
    eller ingen `display`. Lista sto som fem *farlige* verdier og manglet `inline-block` —
    nøyaktig den `.vl-blokktid` har. En svarteliste må være komplett for å virke; en
    hvitliste er det av seg selv.
  - **Byggerne finnes ved å lete, ikke ved å stå i en liste.** Den håndholdte lista nevnte
    seks byggere, og «Oversikt»-tabellen sto utenfor. Samme forfall som XSS-skanneren hadde
    samme dag.
  - **En klasse som er laget for et element *inne* i cella skal ikke settes på cella.**
    `.vl-tidcelle` har `display: flex` og hører til en `<div>` i regnearkets tidskolonne;
    «Oversikt» har sin egen `.vl-oversikt-tid` uten `display`.
- **Et skift redigeres i et vindu, ikke ved å settes opp på nytt.**
  `apneRedigerVaktpost()` endrer mannskap, rolle, tider og merknad i én PUT;
  serveren sjekker den doble regelen på nytt mot personen som skal inn. Å
  bytte person ved å slette raden mistet tidene og rollen som sto der.
  Sletting ligger inne i vinduet bak en bekreftelse, som på ressursen.
- **Utskriftslista grupperes på dag, så ressurs** (15. sep. 2026 — snudd fra
  ressurs-først). Den svarer nå på «hvem er på vakt i dag, og hvor», som er det den som
  møter om morgenen spør om; før svarte den på «hvem står på denne bilen, og når», med
  begrunnelsen at leseren sto ved bilen. Begge er gyldige — dette er et valg om hvem arket
  er for. Korpset er fortsatt en kolonne, og `_skiftrekkefolge()` har `til_tid` som andre
  ledd fordi skift som begynner samtidig ellers står i innsettingsrekkefølge, og et kort
  skift havner midt blant de lange.
- **`_dagnokkel()` er den ene regelen for hvilken dag et skift hører til: startdagen.**
  «fre. 20:00 – lør. 04:00» står under fredag — ikke under begge dager, ikke splittet
  (André, 15. sep. 2026). **Merk at rapportmodulen har landet motsatt for timer**
  (`FORSLAG_RAPPORTMODUL.md` §2.2, splitting ved midnatt): der er spørsmålet hvor mange
  timer, her er det hvem som er til stede. Forskjellen er bevisst og skal ikke «rettes».
  Nøkkelen er nullpolstret fordi den sorteres — `2026-9-15` < `2026-9-4` som tekst.
- **Dagen er ytterste nivå på begge planleggingsflatene** (15. sep. 2026 — André: «i
  ressursgruppene må det være likt som oversikt, ressurser per dag»). `_grupperPaaDag()`
  brukes av «Oversikt» *og* av `_gruppedagbolker()` i gruppefanen; i begge er dagen en
  seksjonsoverskrift og ressurskortene står under den. `mkRessurs(r, apen, egne)` tegner
  derfor **de skiftene den får**, og bruker `_blokkrader` — en dagrad inni kortet ville
  gjentatt tittelen rett over. **`_blokkerMedDager()` er nå bare «Mitt korps»**, som har én
  tabell på tvers av ressursene og altså ingen seksjon å legge dagen i.
- **Utskriftsvelgeren avgrenser til en dag, ikke til en ressurs** (15. sep. 2026).
  `utskriftDag` er en `_dagnokkel()`-streng eller `null` for hele vakta. Ressursvalget ga
  mening da arket var gruppert på ressurs; etter snuingen ville «Ambulanse 1» vært et snitt
  på tvers av det arket er bygget rundt. **En endagsvakt får ingen velger i det hele tatt** —
  ett valg i et nedtrekk er en kontroll som ikke gjør noe; utskriftsknappen står igjen alene.
  Filtreringen skjer **før** tallene regnes, så arkhodet sier den valgte dagens timer og
  ikke hele vaktas.
- **En ressurs uten skift hører til ingen dag, og får bolken «Uten skift».** Uten den ville
  kortet med «Opprett vakt» ikke finnes noe sted, og ingen kunne satt opp den første vakta
  på en ny bil. Bolken vises bare når noen faktisk står uten skift.
- **Rekkefølgen i dagbolken er ressursenes, ikke skiftenes.** `_gruppedagbolker()` leser
  skiftene i serverens rekkefølge (`fra_tid`) og filtrerer så *ressurslista* — samles de per
  ressurs først, er rekkefølgen garantert av hvordan lista ble bygget og ikke av regelen,
  og en mutasjon som fjerner regelen går grønn. Det skjedde 15. sep. 2026.
- **Dagoverskriften vises alltid, også på en endagsvakt** (15. sep. 2026). Fram til da sto
  den bare når vakta spente over mer enn én dag; da måtte planleggeren vite at *fraværet*
  av en dagrad betydde noe, og tabellen skiftet form når vakta ble forlenget.
- **Ressurskortene i gruppefanen kan slås sammen**, og er det som standard når gruppa har
  mer enn én ressurs (André, 14.–15. sep. 2026). Tilstanden ligger i `ressursApen` i
  `vaktliste-kjerne.js`, **ikke i DOM-en** — `mkRessurs()` bygges på nytt ved hvert
  panelbytte, samme grunn til at `gateKnapper()` ikke kan gate den. **Map, ikke Set:**
  fraværende nøkkel betyr «som standarden», så et kort man åpnet ikke slår seg sammen igjen
  når noen legger til en bil i gruppa. Knappene blir stående i hodet på et sammenslått
  kort, og `apneVaktpost()` åpner kortet — ellers lagrer man et skift og ser ingenting
  skje. **Vippa sitter på ressursen, ikke på ressursen-den-dagen**: en bil som står i to
  dagbolker slås sammen begge steder, ellers hadde én ting hatt to tilstander.
  `map(mkRessurs)` sender indeksen som `apen` — den formen var harmløs til byggeren tok
  flere argumenter.
- **Hver enhet er sin egen `Ressurs` inne i gruppa** — bil A, bil B og bil C er tre
  rader i fanen «Ambulanse», hver med egne skift og egen `enhet`-kobling. Modellen var
  riktig fra første stund, men veien dit var usynlig: knappen lå sist i fanerekka og het
  «Ny ressurs». Gruppefanen har derfor et hode med antall enheter og en «Ny
  <gruppe>»-knapp, og ukoblede enheter viser «Ikke koblet» framfor ingenting.
- **Noen grupper finnes i ett eksemplar** (`Ressursgruppe.flere_enheter`, av
  for Samleplass og KO). «Samleplass 2» er ikke en ny samleplass, det er en
  delt vaktliste ingen leser riktig. Den *første* må man fortsatt kunne
  opprette, så plassen tar slutt først når den ene står der.
  `services`-siden er serverens sperre i `ressurser_view`, **per vaktliste** —
  var den global, kunne neste vakt ikke hatt samleplass. Klienten har regelen i
  **én** funksjon, `gruppaHarPlass()`, fordi den har to lesere: knappen i
  gruppehodet og nedtrekket i «Ny ressurs». Skjules bare knappen, kan man
  fortsatt velge gruppa i nedtrekket.
- **«Ny ressurs» spør bare om navn og gruppe.** Reservasjonen ligger på
  plassen og koblingen på den enkelte enheten, så begge settes i «Rediger».
  Skjemaet ba tidligere om dem, og da måtte man svare før man visste svaret —
  det leste som om gruppa *var* enheten. Nedtrekket fylles derfor i
  `apneNyRessurs()`, ikke i `fyllNedtrekk()`: hvilke grupper som har plass
  endrer seg hver gang en ressurs opprettes.
- **Et endepunkt uten flate finnes ikke for brukeren.** `/api/grupper/` sto en dag uten
  UI, og da kunne ingen lage en gruppe som ikke var seedet — samme feil som Django-admin
  ga oss i fase 1. Manageren ligger i «Innstillinger».
- **Fanen er ressursgruppa, ikke ressursen.** «Ambulanse» er alle ambulansene
  på vakta, med hver bil som sitt eget kort inni (`mkGruppe`). Én fane per bil
  ga ti faner på en vakt med ti biler, og ingen plass der man så dem i
  sammenheng. `aktivFane` bærer derfor en **gruppe-ID**. Det som er per
  ressurs — enhetskobling, reservasjon, roller — blir stående på ressursen.
- **Kurven står i fanen den gjelder** (`mkGruppekurve`), ikke i «Oversikt» —
  og timeaksen har én celle per søyle med samme flex-bredde, så
  klokkeslettet står under sin egen time uansett hvor lang vakta er. Tettheten
  glisner med lengden (`_timesteg`). Den hvite streken i kurven er **midnatt**
  (`vl-dogn`), ikke nåværende tidspunkt; den står i tegnforklaringen fordi en
  strek man må spørre om ikke forklarer noe.
- **Bemanningskurven tegnes per ressursgruppe, over ett felles spenn.** Én samlet kurve
  summerte samleplassen, ambulansene og KO til ett tall som ikke svarer på noe. Spennet er
  felles (`_vaktensSpenn()`) fordi to kurver man ikke kan sammenligne er verre enn én
  samlet.
- **Markup som tegnes på nytt kan ikke gates av `gateKnapper()`.** Den setter
  `.d-none` én gang ved sidelasting; `tegnFaner()` og `mkRessurs()` bygger på
  nytt ved hvert panelbytte og må derfor spørre `kanLede()`/`kanBemanne()`
  selv. «Ny ressurs» sist i fanerekka er eksempelet.
- **Handlingskolonnen i ressurstabellen er `position: sticky`.** Tabellen
  ruller under 1280 px, og uten den var rediger-knappen det første som forsvant
  — altså den ene knappen raden finnes for. Bakgrunnen må settes eksplisitt,
  ellers ruller innholdet synlig under den.
- **Kolonnebredde i ressurstabellen er `min-width` + `<colgroup>`-andeler, og
  begge deler betyr noe.** Et `datetime-local`-felt har en gulvbredde nettleseren
  bestemmer; blir kolonnen smalere enn den, stikker feltet ut over nabocella —
  `table-layout: fixed` klipper ikke innholdet. `RessurstabellensBreddeTests`
  regner ut hva tidskolonnene faktisk blir og krever at de rommer feltet, altså
  regelen og ikke tallene.
- **Tidsfeltene er `datetime-local` med `step="300"`.** Fem minutters steg,
  ikke ett — en vakt planlegges ikke på minuttet. Steget må være et multiplum
  av 60, ellers får feltet et sekundsegment. «Opprett vakt» forhåndsutfyller
  fra- og til-feltet med **vaktas start**, ikke `new Date()`: en oktobervakt
  planlegges i august. Et eldre skift på 08:03 vises og leses tilbake som før;
  `step` styrer bare hva velgeren tilbyr, og ingenting leser `checkValidity()`.
- **Et tidsfelt står aldri tomt** (15. sep. 2026 — André: «lik tidsfelt som vi
  har i planleggeren … den i ny vaktliste er litt knotete»). `type` og `step`
  var like fra før; det som skilte «Ny vaktliste» fra planleggeren var at
  feltene startet tomme, og et tomt `datetime-local` må tastes inn segment for
  segment uten noe å nudge på. `apneNyVaktliste()` fyller dem ut **før**
  vinduet vises — derfor åpnes det av JS og ikke av `data-bs-toggle`; et skjema
  som fyller seg selv etterpå ser ut som om noe rettet det man skrev.
  **Starten settes til neste hele time** (`_nesteHeleTime()`): `new Date()` gir
  21:37, og nærmeste lovlige verdi med `step="300"` er 21:35, et tall ingen har
  ment. Planleggeren slipper spørsmålet fordi den har vaktas start å bygge på;
  her *er* feltet vaktas start. **Slutten følger starten til noen rører den**
  (`nyVaktSluttRort`) — samme idé som at et nytt skiftvindu begynner der det
  forrige sluttet, men en rettelse av startdatoen skal ikke spise et sluttidspunkt
  man alt har skrevet. Et tomt sluttfelt teller ikke som rørt. **Spennet leses
  tilbake under feltene** (`nyVaktSpenntekst()`), som tallet under et skiftvindu:
  det er den ene tilbakemeldingen som fanger riktig klokkeslett på feil dato.
  `_varighetstekst()` skriver «2 d 6 t» og ikke «54 t» — et skift er kort nok
  til at timetallet leses, en vakt er det ikke — og hele døgn uten timerest.
- **Tid vises med dag når skiftet krysser et døgn.** `_tidsspenn()` i
  `vaktliste.js` nevner dagen én gang innenfor ett døgn og to ganger ellers —
  «20:00–04:00» alene sier ikke at skiftet går over midnatt, og arrangementer
  varer flere dager. Vaktas spenn utledes av skiftene, ikke av et felt.
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
  `Lower(...)`: uten den er «alfabetisk» databasens alfabet, og SQLite (dev) og
  PostgreSQL (prod) svarer ulikt på store/små bokstaver. Æ/Ø/Å er fortsatt
  databasens svar.
- **ID-er fra klienten går gjennom `views._int()`.** Et nedtrekk med «Ingen valgt»
  sender `''`, ikke `null`, og den strengen i et FK-filter gir `ValueError` — altså 500
  der brukeren skulle fått «velg korps». `or None` dekker den tomme strengen, men ikke
  en ikke-numerisk.

**Besetningen i sentralbordet (fase 6) går én vei: `vaktliste` → `oppdrag`.**
Oppdragsmodulen importerer **ikke** vaktlista; `oppdrag-sentral.js` henter
`/vaktliste/api/enhet/<pk>/besetning/` og rendrer svaret.
`OppdragImportererIkkeVaktlista` leser importene med AST og håndhever det.

- **Gatet på `les` i vaktliste**, ikke i oppdrag — komposisjonsregelen fra
  rollemodellen §5. Malen får et flagg via `har_tilgang(..., 'vaktliste', ...)`:
  en slug gjennom `core`, ikke en import.
- **Svaret bærer navn, rolle, innsjekkstatus, telefon og ISSI** (telefon og ISSI
  fra 12. sep. 2026 — «på koblede enheter i /oppdrag skal det vises telefon nummer
  og ISSI»). Ikke kompetanser, ikke `notat`, ikke e-post eller konto — sentralbordet
  skal kunne ringe bilen, ikke lese personalmapper. `Mannskap.issi` (`0015`) er
  nødnettsterminalens nummer, tekst med ledende nuller, etter telefon og e-post i
  registeret.
- **Bare skiftene som dekker nå**, og **404 når enheten er ukoblet**: ubemannet
  og ukoblet er ulike svar på ulike problemer.
- **Lista i drift vinner; ellers portalens aktive vakt** (12. sep. 2026 — «koblingen
  fungerer ikke»: vaktlista som kjørte lå på en annen vakt enn den aktive). Dekker
  ingen skift nå, sendes **neste skift** med (`neste`, `neste_fra`), så svaret er «ingen
  nå, Kari fra 16:00». 404-meldingen skiller fortsatt «koblet i en annen vakt» fra «ikke
  koblet noe sted» (`services.koblet_i_annen_vakt`) — det kostet André en kveld 30. aug.
- **Rekkefølgen sorteres i Python.** `rolle` er nullbar, og SQLite (dev) og
  PostgreSQL (prod) plasserer NULL i hver sin ende.

**Planleggingstall (fase 5) varsler, de sperrer ikke.** `services`
regner ut timer, skift, lengste skift, korteste hvile og **overlapp** per person;
`Belastningsgrenser` (én rad) bærer grensene varslene måles mot.

**Vaktas budsjett står øverst i «Planlegger»** (15. sep. 2026,
`docs/FORSLAG_PLANLEGGERFANE.md` steg 2–3): `services.planleggingstall()` gir
`satt_opp`, `bemannet` og `probono` **side om side**, fordi hvert av dem alene lyver litt
— ingen betaler for en tom plass, og «bemannet» står på null når lista er halvt satt opp.
Avstanden mellom de to første er arbeidslista. `Vaktliste.timetak` er **denne** vaktas
budsjett (`Belastningsgrenser` er organisasjonens og gjelder alle), `igjen` måles mot
**satt opp** og ikke mot bemannet, og `_dagbolker()` bryter ned per dag uten egne tak.

**Linja sto først i «Timeoversikt», og ble flyttet samme dag.** Jeg leste «en planlegger»
som «planleggingstall» og la budsjettet i belastningsfanen; André: «Jeg ba om en
planlegger … Den skal bare admin og leder ha tilgang til. For den genererer grunnlaget på
alt.» Det er to ulike ting: **«Timeoversikt» er lista regnet sammen** (`les`, hva den
koster dem som står der), **«Planlegger» er stedet grunnlaget lages** (`kan_lede`).

**«Oversikt» er en talltabell, ikke en personliste** (16. sep. 2026, André: «Den viser mye
av det som allerede er i de respektive ressursfanene. Må være en faktisk oversikt»). Én rad
per **ressurs per tidsblokk**, med kolonnene Ressurs, Tid, Timer, Plasser, Besatt, Ledige og
Totalt, og en sumrad per dag. Navn, korps, rolle og merknad sto her til da — altså nøyaktig
de fire kolonnene man alt hadde lest i gruppefanen.

Tre ting er verdt å kjenne:

- **Totalt bruker `_sumTimer`, ikke `timer × plasser`.** Probono-skift teller null (11. sep.
  2026), og et skift uten gyldig spenn teller null. Regner man i stedet lengden ganger
  antallet, blir totalen et annet tall enn budsjettlinja og enn `belastning_per_person` —
  tre steder som skal si det samme.
- **Sumraden teller de ledige plassenes timer med.** De er planlagt, og et budsjettall som
  stille utelot dem ville sett rimelig ut og vært for lavt. Regelen sto udekket til en
  mutant fant den.
- **Personopplysningene er ikke borte, de har flyttet dit de gjelder.** Reservasjonen på en
  ledig plass (`_plassKorps`) og probono-merkelappen prøves nå i gruppefanen. Utskrift av et
  navneark skjer derfra — utskrifts-CSS-en er generisk og skriver ut den fanen man står i.

**Fanen het «Planlegging» til 16. sep. 2026**, og navnet var opptatt: `Vaktliste.status`
har verdien «Planlegging» ved siden av «I drift», og den står som et merke øverst på siden.
Fanen og merket sa altså samme ord om to ulike begreper — hva lista *koster i timer*, og om
innsjekk er *åpen*. Regelen står som en test (`FanenHeterTimeoversiktTests`): **et fanenavn
kan ikke være en statusetikett.** Den prøver regelen og ikke ordet, så en framtidig
omdøping som gjeninnfører kollisjonen blir rød uansett hvilket ord det er.

*Bare fanen ble omdøpt.* `choices.STATUS_VALG` har fortsatt «Planlegging» som statusverdi,
og migrasjonene bærer den — et søk-og-erstatt over ordet ville døpt om statusen, som er noe
helt annet.

- **Taket settes i `vaktliste_detalj_view`s PUT, sammen med start og planlagt slutt, og
  er derfor `skriv_leder`** — ikke `skriv_full`. Rekkevidden er den samme (hele vakta,
  ikke ett korps' del), og én forespørsel kan ikke ha to tilgangsnivåer inni seg.
- **Budsjettallene sendes bare til den som `ser_alle_korps`.** De filtreres aldri på
  korps — taket gjelder lista — så for en `les` med badge ville de vært et aggregat over
  skift hun ikke får se. `belastning_view` sender `planlegging: null`, og klienten tegner
  ingenting; en tom ramme ville sagt «her er noe du ikke får se».
- **`kanSetteTak()` leser serverens `kan_sette_tak`**, ikke `MODUL_TILGANG`. Regnes den
  ut i klienten, kan knappen og endepunktet komme i utakt.

- **Grensene er organisasjonens**, ikke portalens — derfor data og ikke tall i
  en `if`. `skriv_leder` flytter dem: det endrer hva *alle* vaktlister varsler
  om.
- **Ingenting avvises.** Noen ganger må noen ta et langt skift, og da skal
  lista si det høyt. Fargen er gul (`--vl-varsel`), ikke rød.
- **Overlappende skift gir hvile 0**, ikke et negativt tall — et negativt tall
  i en «korteste hvile»-kolonne ser ut som en regnefeil. **Null der betyr to ulike ting**
  (skift som henger sammen, og skift som overlapper), og det er derfor
  `_overlappstimer()` finnes ved siden av: sum minus union, så
  `timer - overlapp` er faktisk tilstedeværelse. **Summen korrigeres ikke, den
  navngis** — et tall som stille retter seg selv ville skjult dobbeltbookingen.
  Probono teller med her selv om den ikke teller i `timer`: kroppen skiller ikke på lønn.
  Overlappet har **ingen grense å måle mot**, med vilje — én person kan ikke stå to
  steder uansett hva `Belastningsgrenser` sier.
- **Faktisk tid regnes bare av ferdige skift** (både `mott_at` og
  `av_vakt_at`). Et pågående skift ville gitt et tall som endrer seg mens man
  ser på det.
- `_hviletider()` **sorterer selv**, selv om `Vaktpost.Meta.ordering` gjør det
  også: en hjelper skal ikke hvile på at den som kaller den har sortert. Uten
  den egne sorteringen målte testene modellens ordering. **`_dagbolker()` er skilt ut av
  `planleggingstall()` av nøyaktig samme grunn** (15. sep. 2026, funnet på nytt ved
  mutasjonstesting) — og den regner dagen i **lokal tid**: et skift som begynner 00:30
  norsk tid er 22:30 UTC dagen før, så `.date()` rett på tidspunktet legger hver eneste
  nattevakt på feil dag. En test med falske skift må derfor bære **UTC**, som ORM-en
  gjør; bærer den norsk tid, går mutanten grønn.

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
