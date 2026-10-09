# Oppdragsflaten (templates/oppdrag/)

> **Flatefil.** Den lastes når noen arbeider i `templates/oppdrag/`. Modellene og reglene
> bak — statusmaskinen, verdimengdene, bilens utganger, historikk mot arkiv — står i
> `oppdrag/CLAUDE.md`, og rammeverket i `CLAUDE.md` i rota. `static/js/oppdrag-*.js`
> ligger utenfor mappa og laster ingen av dem: les denne før du rører JS-en.

## Frontend — to grensesnitt, to filsett

Hva som lastes når står i rota; hva filene gjør står her.

**`oppdrag-sentral-*.js` (fire: kjerne, oppdrag, admin, lasting)** — sentralbordet:
enhetsliste, oppdragsliste, tidslinje, lokasjonsadmin. `oppstart()` tegner listene uansett
hva første henting ga (`LASTEFEIL` til den lykkes), og pollingen settes i `finally`. Uten
det ble en tom side stående etter én feilet henting, og den så ut som en vakt uten enheter.

> Filene kjører i `/ko/` fra pulje 4 og er fortsatt oppdragsmodulens (`docs/FORSLAG_KO.md`
> §10). Sentralbordet i `/oppdrag/` slås av først etter en ekte vakt — se `TODO.md`.

**`oppdrag-enhet.js`** — enhetsskjermen. Fire ting den gjør, og hver av dem har en grunn:

| Hva | Detalj |
|---|---|
| Knappene | «Neste», den andre knappen og Avbryt mot de **navngitte** stemplingsendepunktene — de leser ikke request-kroppen |
| Offline-køen | `localStorage`, **nøkkel per bruker** (`brukerNokkel()`, L17, 8. okt.) — en annen konto på telefonen spiller den ikke av. «Venter på dekning» vises først når eldste rad er 3 s gammel — `usendtAlder`, `USENDT_VENTETID_MS`. Uten forsinkelsen blinket varselet ved hvert trykk på god dekning |
| Lydvarselet | `lydTerskler()` leser `OPPDRAG_LYDVARSEL` fra tabellen `Lydvarsel`, hentet på nytt hvert 5. min; `skalPipe()` og `lydTikk()` hvert 5. s. Web Audio, **alltid på**, vekket av det første trykket på siden (`lydErKlar()`). `nyeOppdrag()` + `pipNytt()` for nytt oppdrag om admin ikke har slått det av |
| Posisjon til kartet (30. sep.) | Bare når `OPPDRAG_KART_KOBLING` er sann — ellers spørres nettleseren aldri, og **bare da får siden `geolocation=(self)`** (resten av portalen har `()`). `watchPosition` holder siste fix i minnet; `posisjonForStempling()` gir den bare om den er under 120 s. `_stemple` legger den i **køraden**, så den som sendes er fra trykket. Bryteren «Del posisjon» per skjerm (`delerPosisjon`), på som standard. Stemplingen venter aldri på GPS |
| Hvem deler posisjon (4. okt.) | `posisjonsdelingTilstand()` er regelen — `null` uten kobling eller av vakt, ellers `av` før nettleserens `nektet`/`utilgjengelig`, ellers `deler` (gammel fix er ikke en tilstand). Rir på `lastMine` som header og ligger i køraden fra trykket. `erPaVakt()` leses fra `X-Enhet-Pa-Vakt`; **overgangen av → på nullstiller bryteren til på** (`notePaVakt`), fordi `localStorage` overlever fra forrige vakt. Linja sier at KO ser tilstanden, og hvor «nektet» rettes; bryteren er grå av vakt og uten GPS (`bryterSperret`) |
| «Send posisjon» (7. okt.) | Knappen under enhetsnavnet — «her er jeg, hvor skal jeg?» — står med og uten oppdrag. `sendPosisjon()` bruker fixen i minnet om den er under 30 s (`posisjonForKnapp`), ellers `getCurrentPosition` **innenfor en egen frist** (`medFrist`, 20 s) — nettleserens `timeout` teller først når tilgangen er gitt, og uten fristen hang knappen på et spørsmål som aldri ble vist. Et nei som alt er gitt (`posisjonstilgang()`) sies med en gang; etter fristen brukes en fix under 120 s. **Bryteren «Del posisjon» styrer den ikke** (et trykk er et valg); av vakt er den grå (`sendPosisjonSperret`). Ingen kø: uten dekning sier den fra. Kvitteringen er «Delt kl. … KO ser bilen i kartet til kl. …» (`sendPosisjonKvittering`), med `utloper` fra serveren. Vises og gråes gjennom `tegnPosisjonLinje()` → `tegnSendPosisjon()` |
| «Annet sted»-feltet (7. okt.) | Pollingen hvert 15. s tegner kortet med `innerHTML`, og byttet feltet ut midt i skrivingen. `stedfeltetErApent()` lar kortet stå så lenge feltet i DOM-en (`data-oppdrag`) gjelder et oppdrag som fortsatt venter på «Avreist». Fokus tilbake hjelper ikke: iOS åpner ikke tastaturet uten et trykk |
| Skjermen holdes våken (9. okt.) | Screen Wake Lock, ellers sovner telefonen i holderen og pollingen og lyden stopper. `skjermSkalHoldesVaaken(synlig, trykket, holder)` er regelen; `startVaakenLaas()` henter låsen ved trykk **og på nytt på `visibilitychange`** — nettleseren slipper den ved hvert appbytte og hver samtale. Avslaget (iOS i strømsparing) er stille, så `#vaaken-linje` sier fra. Kaster aldri. `Permissions-Policy` må ikke få `screen-wake-lock=()` |
| Tida det måles fra | Bilens `varslet_at` — og **et usendt trykk i køen teller som svart**, ellers ville bilen pipt om et oppdrag mannskapet nettopp kvitterte ut uten dekning |

**Serveren sender `neste_overgang`/`alternativ_overgang` per rad.** Kjeden og alternativene
følger med som data **kun** for å projisere neste steg mens noe ligger usendt — klienten
eier ikke statusmaskinen, og en klient som regnet den ut selv ville blitt uenig med
serveren i nøyaktig det øyeblikket en overgang ble endret.

**Hvorfor `_stilleLydbaerer()` finnes** (14. sep. 2026): den bygger en stum WAV som Blob —
uten den demper iOS' ringebryter lydvarselet, fordi Web Audio alene regnes som «ambient».
Derfor er CSP-ens `media-src` `'self' blob:` (regelen står i rota). Feilen var *stille der det
telte*: siden virket, oppdraget lastet, og bare konsollen sa fra — mens bilen ikke pep.

## Ressurslista, delt med `/ko/`

**Posisjonsikonet står helt til høyre på kortet** (4. okt. 2026, `posisjonsdelingIkon` i
`oppdrag-kort.js`): fire tilstander som skiller seg på form og lysstyrke, ikke bare farge —
dempet pin for deler, gul med strek for av (en samtale, ikke en alarm), blå med utropstegn
for kan-ikke (nektet og uten GPS, ulik tekst), stiplet med spørsmålstegn for ukjent. Tom
streng når `OPPDRAG_KART_KOBLING` er usann — da melder ingen bil noe, og et «?» på hver bil
hadde sagt at noe var galt som ikke var det. Fargeforklaringen i KO får de fire radene fra
`posisjonsdelingLegende()` med samme gate. Mappingen står inne i funksjonen, fordi harnessene
henter funksjoner alene. Stilen i `oppdrag.css` (`.posdeling-*`).

**Hele ressurslista er delt med `/ko/`** (18. sep. 2026). Serversiden:
`services.enhetskort()` er den ene serialiseringen, og både `views.enheter_view` og
`ko.services.ressursbildet` leser den. Klienten: `static/js/oppdrag-kort.js` bærer
`tegnEnhetsliste()` — grupperingen på enhetstype, kortet, besetningspanelet og
«av vakt»-telleren — pluss ordforrådet rundt: `tidSiden`, `hastegradKlasse`, `_grovMerke`,
`_problemMedAntall`. `renderEnheter()` her er nå ett kall inn i den.

Begge sidene bruker ID-ene `#enhetsliste` og `#av-vakt-teller`, og begge må sette
`window.OPPDRAG_ENHETSTYPER`, `OPPDRAG_MED_ANTALL` og `KAN_SE_BESETNING`.

`tomt_enhetskort()` fantes fra pulje 3 til 18. sep. 2026, for KO-ressurser uten enhet; den ble
død kode da KO fikk sentralbordets liste, og er slettet. Vaktlistas ressurser tegnes av
`koRessurskort()` i `ko.js` med sin egen form.

**`oppdrag-enhet.js` deler ikke dette.** Bilens egen skjerm har fortsatt sine egne kopier
av `hastegradKlasse` og `_problemMedAntall`, og de står igjen med vilje: den siden laster
ikke `oppdrag-kort.js`, og å rive i enhetsskjermen hører til pulje 4. Står i `TODO.md`.

**Sentralbordet eier `enheter`, og melder det inn i `renderEnheter()`.** `lastEnheter()`
bytter ut arrayen uten å tegne — `lastAlt()` tegner etterpå — og fyrer `hentBesetning()`
uten `await` i mellomtiden. Husket den delte koden forrige tegnede liste, tegnet en
besetning som løste i det vinduet forrige rundes enheter (funnet 18. sep. 2026, ved å
sammenligne mot koden før flyttingen). `settEnhetslisteKilde(() => enheter)` gjør at den
spør i stedet.

Innmeldingen står **i** tegnefunksjonen og ikke på toppnivå, og det er en testbarhetsregel:
`build_harness()` plukker ut funksjoner og kjører ikke toppnivålinjer, så et kallsted der
kan fjernes uten at noe blir rødt. Mutanten overlevde nøyaktig sånn.

## Sentralbordet i `/ko/`

**Sentralbordet kjører også i `/ko/` fra pulje 4** (18. sep. 2026), og delingen går på fire
nivåer: konteksten (`views.sentralbordkontekst`), tre malbiter (`_sentralbord_verktoy`,
`_sentralbord_modaler`, `_sentralbord_skript`), JS-en (`oppdrag-kort.js` pluss de fire
`oppdrag-sentral-*.js`) og endepunktene, som er uendret.

**Gatene er denne modulens, også når sida er KO.** `kan_skrive`, `kan_lede` og
`kan_se_besetning` kommer fra `sentralbordkontekst()`, og KO legger bare til `kan_se_oppdrag`
— om flata tegnes i det hele tatt. En ny gate skal derfor inn i `sentralbordkontekst()` og
ikke i den ene malen; ellers virker den bare på én av sidene.

`/oppdrag/` er uendret i denne puljen — verifisert ved å sammenligne svaret fra ti endepunkter
før og etter, ikke ved å lese diffen.

**KO pulje 5 rører modulen to steder** (18. sep. 2026). `Oppdrag.hendelse` er en nullbar FK
til `'ko.Hendelse'` — strengreferanse, ingen import, og **skrives bare av
`ko.services.knytt_oppdrag`**; her leses den i `oppdrag_til_dict` (`hendelse_id`, `_nummer`,
`_tittel`) og står i ETag-en. Og nummeret skrives **`O45`**, ikke `#45`: formen bor i
`services.oppdragsnr()` og `oppdragsnr()` i `oppdrag-kort.js` (enhetsskjermen har egen kopi),
og `Enhetshendelse.detalj` og bjellevarselet bruker den. Eldre `detalj`-rader står med `#`.

## Oppdragsvinduet og «Nytt oppdrag»

**«Endre status» tilbyr «Avbrutt — trenger ny ressurs»** (23. sep. 2026) der bilen selv har
Avbryt-knappen: `_statusvalg` leser `OPPDRAG_AVBRYT_FRA` fra `sentralbordkontekst()`, så
begge sidene får den, og serveren (`foer_avbrutt`) avgjør uansett.

**Oppdragsvinduet har ingen «Rediger»** (backlog punkt 4 og 5, 23. sep. 2026 — André: «rediger
knappen inne i oppdraget gjemmer redigerbar info»). Hastegrad, problemstilling, lokasjon og
tildelt ressurs står som brikker; et klikk gir et nedtrekk, og valget lagres med én gang
(`_verdiForesporsel`). **Ressursen er ikke et felt:** uten enhet legges den valgte til, med én
flyttes oppdraget, med flere er brikken låst og «Flytt»/«Legg til» under gjelder. Notatet står
alltid framme. **Inne i oppdraget, ikke i lista** — André: «avvent litt»; fellene står i TODO.

**«Velg…» står øverst i hvert nedtrekk uten lagret verdi** (23. sep. 2026, André: «Hvis man
har valgt og lagret en verdi så må jo den så klart være selected … Hvis obligatorisk felt så
feilmelding»). `velgValg(valgt)` i `portal-utils.js` bygger valget — valgt bare når ingenting
er lagret — og `velgTekst()` er teksten, en funksjon fordi harnessene henter funksjoner og
ikke konstanter. Å lagre «Velg…» gir en melding ved knappen, aldri en forespørsel:
`nyttOppdragMangler()` (i skjemaets rekkefølge), `{feil}` fra `_verdiForesporsel`, og vaktene
i `varsleEnhet`/`flyttOppdrag`. **Ressursen er ikke obligatorisk** — «Opprett uten enhet»
finnes — så uten enhet er «Velg…» der ingen handling. Bytter hastegraden i «Nytt oppdrag»
etter at en problemstilling var valgt, gjelder vinduets regel: beholdes om den kan, ellers
«Udefinert» (`problemstillingEtterBytte`), ikke tilbake til «Velg…».

**Enhetsvalget i «Nytt oppdrag» viser statusen** ved navnet, ledig framhevet (André: «så kan
du se hvem som er ledig»). Rekkefølgen er fortsatt typen og navnet — en liste som stokker seg
om mens man krysser av, er verre enn en som må leses.

**«Vis»-menyen over ressurslista er delt med `/ko/`** (23. sep. 2026) — malbiten
`_synlighetsmeny.html` og `oppdaterSynlighetsmeny()` i `oppdrag-kort.js`, kalt til slutt i
`tegnEnhetsliste()`. Her har den bare seksjonen «Biler». Hvordan den virker står i
`templates/ko/CLAUDE.md`, under Ressursoversikten.
