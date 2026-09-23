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
| Offline-køen | `localStorage`. «Venter på dekning» vises først når eldste rad er 3 s gammel — `usendtAlder`, `USENDT_VENTETID_MS`. Uten forsinkelsen blinket varselet ved hvert trykk på god dekning |
| Lydvarselet | `lydTerskler()` leser `OPPDRAG_LYDVARSEL` fra tabellen `Lydvarsel`, hentet på nytt hvert 5. min; `skalPipe()` og `lydTikk()` hvert 5. s. Web Audio, **alltid på**, vekket av det første trykket på siden (`lydErKlar()`). `nyeOppdrag()` + `pipNytt()` for nytt oppdrag om admin ikke har slått det av |
| Tida det måles fra | Bilens `varslet_at` — og **et usendt trykk i køen teller som svart**, ellers ville bilen pipt om et oppdrag mannskapet nettopp kvitterte ut uten dekning |

**Serveren sender `neste_overgang`/`alternativ_overgang` per rad.** Kjeden og alternativene
følger med som data **kun** for å projisere neste steg mens noe ligger usendt — klienten
eier ikke statusmaskinen, og en klient som regnet den ut selv ville blitt uenig med
serveren i nøyaktig det øyeblikket en overgang ble endret.

**Hvorfor `_stilleLydbaerer()` finnes** står i rota, under CSP — `media-src` måtte
åpnes for `blob:` for at iOS' ringebryter ikke skal dempe varselet.

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

**«Endre status» tilbyr «Avbrutt — trenger ny ressurs»** (23. sep. 2026) der bilen selv har
Avbryt-knappen: `_statusvalg` leser `OPPDRAG_AVBRYT_FRA` fra `sentralbordkontekst()`, så
begge sidene får den, og serveren (`foer_avbrutt`) avgjør uansett.
