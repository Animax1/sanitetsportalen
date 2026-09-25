# Testsjekkliste – `/vaktliste`

**Hva denne er.** En manuell gjennomgang av vaktlisteflata før en vakt, etter en deploy,
eller når noe er endret i modulen. Den prøver det testsuiten **ikke** kan prøve: at
felter lar seg fylle ut på en telefon, at en lås ser låst ut, at tallene i fire flater sier
det samme, og at lista fortsatt virker når nettet forsvinner.

**Hva den ikke er.** Ikke en erstatning for `python manage.py test vaktliste` — den doble
regelen (badge + reservasjon), stemplingsreglene og belastningstallene er prøvd der, med
mutanter. Finner du noe her som suiten burde ha funnet, har du funnet **to** ting: feilen,
og et hull i dekningen.

**Noter byggnummeret i footeren** og hvilken gren miljøet står på (`staging` =
staging, `main` = prod).

---

## 0. Før du begynner

**Kontoene.** Halve lista handler om hvem som får røre hva, og det kan ikke prøves med én
konto. Modulen har fem nivåer, og **synligheten følger ikke stigen** — `skriv_handling`
ligger over `les_alle` og ser likevel alle korps, mens `les` bare ser sitt eget.

| Konto | Nivå | Badge (`Mannskap.korps`) | Prøver |
|---|---|---|---|
| `test-vl-les` | `les` | Korps A | Korpsfilteret: ser bare eget korps |
| `test-vl-lesalle` | `les_alle` | – | Ser alle, skriver ingenting |
| `test-vl-fore` | `skriv_handling` | Korps A | Korps-føreren: ser alle, fører eget |
| `test-vl-full` | `skriv_full` | Korps A | Bemanner alle korps, stempler |
| `test-vl-leder` | `skriv_leder` | Korps A | Setter opp vakta |
| `test-vl-uten` | `skriv_handling` | **ingen** | Korps-føreren uten badge |
| `admin` | global admin | | Sletting av vaktliste, kontokobling |

**Data.** Minst to korps, fire mannskap fordelt på begge, to ressursgrupper (én med
`flere_enheter`, f.eks. Ambulanse, og én uten, f.eks. Samleplass), og en vaktliste som
spenner over **to døgn** — endagsvakter skjuler flere av reglene under.

**Enheter.** Minst én ressurs koblet til en oppdragsenhet, og én ukoblet.

**Nettlesere.** Chrome/Edge på PC, **og** Safari på iPhone eller iPad for §6 og §13 —
flere av feilene under finnes bare der.

---

## 1. Oppstart, korpsfilter og badge

- [ ] **Sida åpner** med vaktlinja, fanerekka og panelet. Ingen feil i konsollen.
- [ ] **`test-vl-les`** ser banneret «Du ser bare ditt eget korps: \<navn\>», og lista viser
      korpsets skift **og** ledige plasser satt av til korpset — ikke de andres.
- [ ] **`test-vl-lesalle` og `test-vl-fore`** ser alle korps, og får en **korpsvelger** i
      vaktlinja. Velg korps B → fanene, tallene og «Mitt korps» følger med.
- [ ] **`test-vl-uten`** ser alle korps, men får beskjed om at kontoen mangler kobling, og
      kan ikke redigere noen rad.
- [ ] **En konto med `les` uten badge** får en tom liste **med forklaring**, ikke en tom
      side som ser ut som en vakt ingen har satt opp.
- [ ] **Uten vaktlistetilgang** er `/vaktliste/` 403 og modulen borte fra menyen.
- [ ] **Sida kommer tilbake til lista du sto på** etter en sidelasting. Slett den lista som
      admin, last på nytt → øverste liste, ingen feil.

## 2. Vaktlister

- [ ] **«Ny vaktliste»** (`test-vl-leder`): tidsfeltene er **fylt ut** når vinduet åpnes —
      start på neste hele time, slutt følger starten.
- [ ] **Rør sluttfeltet**, endre så starten → slutten står som du satte den.
- [ ] **Spennet leses tilbake** under feltene («2 d 6 t»), og det stemmer med feltene.
- [ ] **Vakta opprettes som planlagt** og rører **ikke** portalens aktive vakt: registrer en
      pasient etterpå og se at den havner på den gamle vakta.
- [ ] **«Kopier oppsett fra»** tar ressursene og **aldri personene**.
- [ ] **Vaktlistevelgeren bytter liste når du velger**, ikke ved neste klikk. *Symptomet på
      feilen er at velgeren føles «treg».*
- [ ] **Vaktas lengde og timetak** (`test-vl-leder` under «Innstillinger»): lar seg endre.
      `test-vl-full` ser dem ikke og får 403 fra endepunktet.
- [ ] **Arkiver en vaktliste** → den forsvinner fra velgeren og står under «Arkiverte
      vaktlister». Gjenopprett → tilbake.
- [ ] **Slett en vaktliste**: bare global admin. `test-vl-leder` skal ikke ha knappen.

## 3. Fanerekka

- [ ] **Rekkefølgen er:** Oversikt · Mannskap · \<én fane per ressursgruppe\> · Ny ressurs ·
      Mitt korps · Timeoversikt · Planlegger · Tilstede nå.
- [ ] **Gruppefanene ser annerledes ut** enn de faste visningene, med et skille mellom
      bolkene. *De to er ulike slags ting: det ene er der du fører, det andre er der du ser
      hva føringen ble.*
- [ ] **«Planlegger»** finnes bare for `test-vl-leder`/admin.
- [ ] **«Tilstede nå»** finnes bare når lista står i drift.
- [ ] **«Mitt korps»** finnes når du har badge eller har valgt et korps i velgeren, og
      tallet er plassene som gjenstår å dekke.
- [ ] **Uten vaktliste** står «Mannskap»-fanen alene, og den er valgt.

## 4. Ressurser og kort

- [ ] **«Ny ressurs»** spør bare om navn og gruppe. Reservasjon og enhetskobling settes i
      «Rediger».
- [ ] **En gruppe i ett eksemplar** (Samleplass): knappen i gruppehodet **og** valget i
      nedtrekket forsvinner når den ene står der. Prøv begge.
- [ ] **«Rediger ressurs»** (`test-vl-leder`): gruppe, reservert korps, enhet i
      oppdragsmodulen, rekkefølge og sletting.
- [ ] **Navnet kan endres av korps-føreren** når hun kan bemanne ressursen **eller en av
      plassene på den** — prøv med en ureservert samleplass som har én plass satt av til
      korps A. De øvrige feltene i vinduet er låst for henne.
- [ ] **Sletting krever to bekreftelser** (dialogen, og bekreftelsen i kallet), og tar
      skiftene med seg.
- [ ] **Kortene er slått sammen** som standard når gruppa har mer enn én ressurs. Åpne ett
      → legg til en ny bil i gruppa → det åpne kortet er fortsatt åpent.
- [ ] **Vippa sitter på ressursen**: en bil som står i to dagbolker er slått sammen begge
      steder.
- [ ] **Ukoblede enheter** viser «Ikke koblet», ikke ingenting.

## 5. Skift — å sette opp og å bemanne

*Dette er modulens vanskeligste grense, og den går to steder: hvem som får **sette opp** en
plass, og hvem som får **fylle** den.*

- [ ] **«Opprett vakt»** (`test-vl-full`+): antall plasser, korps, rolle, tider, probono.
      Plassene fødes tomme.
- [ ] **`test-vl-fore` har ikke «Opprett vakt»** og ikke tidsfeltene i regnearket — tidene
      vises som **tekst**, ikke som felter hun kan skrive i uten å få lagret.
- [ ] **`test-vl-fore` fyller en plass** som er satt av til korps A → går gjennom. Plass satt
      av til korps B → knappen tilbyr ikke hennes folk, og endepunktet sier 403.
- [ ] **«Åpen for alle»** (`alle_korps`) → alle korps ser og kan fylle plassen.
- [ ] **En planlagt plass** (lederens kladd) er **usynlig** for `test-vl-les` og lar seg
      ikke fylle av `test-vl-fore`. Gjør plassen alminnelig → den kan ikke settes tilbake
      til «Planlagt».
- [ ] **Merknaden.** `test-vl-fore` skriver «Kommer 17:30» på **en plass hun kan fylle**,
      uten å røre nedtrekket for person → **lagres**. *Feilen var 403 her: vinduet sender
      hele skjemaet, og porten skal gjelde overgangen, ikke innsendingen.*
- [ ] **Ett felt hun ikke får sette velter hele forespørselen** — og klienten skal ha silt
      det bort først, så vanlig redigering ikke treffer det.
- [ ] **Forfall meldes ved å tømme raden**, ikke ved å slette den: `test-vl-fore` har ingen
      slett-knapp på skiftet, heller ikke på en fylt rad.
- [ ] **Rediger et skift** (person, rolle, tider, merknad) i **ett** vindu, én lagring.
- [ ] **Dupliser et skift** → ny rad med samme oppsett.
- [ ] **Rekkefølgen i ressursen**: tid først, så rollens rangering, så navn. En hospitant
      som møter 08 står **før** en lagleder som møter 16. Rader uten rolle står nederst;
      ledige plasser først blant sine egne.
- [ ] **«— ledig plass —»** står som valget i nedtrekket, ikke tomt.

## 6. Låste felter (gjør denne på iPhone/iPad)

- [ ] **Et felt korps-føreren ikke får sette er `disabled`**, ikke `readonly`: prøv å åpne
      tidsvelgeren på et låst `datetime-local` på iPhone → den skal **ikke** åpne seg.
      *`readonly` er uten virkning på slike felter — verdien lar seg endre på skjermen og
      blir filtrert bort ved lagring, som er verre enn å ikke kunne røre feltet.*
- [ ] **Låste felter er lesbare**: stiplet kant, dempet flate, teksten fortsatt kontrastrik
      (også i Safari).
- [ ] **Hintet står der og sier hvorfor** — i både skiftvinduet og ressursvinduet.

## 7. Registrene

- [ ] **Mannskap**: opprett, endre, deaktiver. Telefon, e-post og ISSI lagres; ISSI beholder
      ledende nuller.
- [ ] **E-postkobling.** Legg inn en e-post som finnes som aktiv portalkonto, lagret av
      `test-vl-leder` → kontoen kobles av seg selv. Samme lagring gjort av `test-vl-full` →
      e-posten lagres, merket sier at kontoen finnes, men **ingen kobling**.
- [ ] **Adminkontoer er aldri mannskap**: en adminkonto står ikke i kontolista, og manuell
      kobling til den gir 400.
- [ ] **Kontokobling for hånd er global admin**, og flytting mellom korps sjekkes mot
      **begge** korps.
- [ ] **Notat lagres uten verdier i audit-loggen** (sjekk en endring i audit).
- [ ] **Korps og kompetanser** under «Innstillinger»: opprett, endre navn, deaktiver.
- [ ] **Kompetansestigen**: gi noen AFØR → VFØR og GFØR skjules i listene.
- [ ] **Ressursgrupper**: opprett med ikon, endre, deaktiver. Slett en gruppe **i bruk** →
      avvist med antallet og et peik på `er_aktiv`. Slett en tom gruppe **med roller** →
      409 med antallet, og bekreftelse kreves. Slett en tom gruppe **uten roller** → går
      rett gjennom, uten et ekstra klikk.
- [ ] **Ressursroller**: opprett (havner sist i sin gruppe), endre navn **i raden**, endre
      rekkefølge, deaktiver.
- [ ] **Et rollenavn som endres slår gjennom i regnearkets nedtrekk** uten sidelasting.
- [ ] **En deaktivert rolle blir stående** på raden som alt har den, og forsvinner ikke i
      stillhet ved neste tegning.

## 8. Planleggeren (`test-vl-leder`)

- [ ] **Sett opp et grunnlag**: «tre firemannslag 14–22, én ambulanse 15–03». Legg til
      linjer og skiftvinduer.
- [ ] **Plassene hører til vinduet**: samleplass med seks plasser 14–22 og to 22–06 i samme
      rad.
- [ ] **Regnestykket under raden** («6 skift × 1 ressurs = 12 plasser, 96 t») oppdateres
      mens du skriver — **uten** at feltet du står i mister fokus. Skriv et firesifret
      klokkeslett tall for tall i et `datetime-local` og se at du beholder feltet.
- [ ] **«Antall» finnes ikke** for grupper i ett eksemplar.
- [ ] **Forhåndsvisningen før bekreftelsen** sier det samme som panelet, og teller nye
      ressurser, nye plasser og hva som fjernes.
- [ ] **«Lag grunnlaget»** → ressursene og de tomme plassene finnes, som **planlagt kladd**.
- [ ] **Kjør generatoren en gang til** → bemannede plasser, korpsreserverte og «åpne for
      alle» står urørt. Bare kladden på de ressursene oppsettet nevner røres.
- [ ] **Åpne planleggeren på nytt** → den viser **det som står i lista nå**, ikke det du
      skrev sist. Rett et skift i regnearket først, og se at planleggeren følger.
- [ ] **En ressurs utenfor oppsettet** røres ikke.
- [ ] **Budsjettlinja står også i planleggeren**, ikke bare i «Timeoversikt».

## 9. Tall: Oversikt, Timeoversikt og budsjett

- [ ] **«Oversikt»** er en talltabell: én rad per ressurs per tidsblokk, med Ressurs, Tid,
      Timer, Plasser, Besatt, Ledige og Totalt, og **en sumrad per dag**.
- [ ] **Sumraden teller de ledige plassenes timer med** — de er planlagt.
- [ ] **Probono-skift teller null timer** i totalen, men **teller med** i overlappet.
- [ ] **Budsjettlinja** viser satt opp, bemannet og probono **side om side**, og «igjen»
      måles mot satt opp.
- [ ] **Tre steder sier det samme:** budsjettlinja, «Oversikt»-totalen og
      belastningstallene per person.
- [ ] **`test-vl-les` og `test-vl-fore` (uten `ser_alle_korps`) får ingen budsjettall** —
      og ingen tom ramme heller.
- [ ] **Varsler, ikke sperrer**: sett opp et 14-timers skift → gult varsel, lagringen går
      gjennom.
- [ ] **Overlappende skift** på samme person → korteste hvile **0**, ikke et negativt tall,
      og overlappstimene står navngitt ved siden av.
- [ ] **Faktisk tid** regnes bare av skift som har både møtt og av vakt.
- [ ] **Et skift som begynner 00:30** havner på **riktig dag** i dagbolkene. *Nattevakter er
      der denne regelen brytes: ORM-en gir UTC, dagen skal regnes i lokal tid.*

## 10. Drift og stempling

- [ ] **«Sett i drift»** står under «Innstillinger» og virker både ved sidelasting og når
      vinduet åpnes på nytt.
- [ ] **Statusmerket** i vaktlinja skifter til drift, med pulserende prikk.
- [ ] **Stemplingsrekkefølgen**: «Av vakt» før «Møtt» → avvist med en forklaring. «Angre
      møtt» mens «av vakt» står → avvist. «Angre av vakt» → går.
- [ ] **«Tilstede nå»** teller hodene, og tallet stemmer med radene.
- [ ] **Stempling krever `skriv_full`**: `test-vl-fore` får 403 — og får vite at hun ikke
      har lov, **ikke** at lista ikke er i drift. Prøv med lista ute av drift også.
- [ ] **Redigering virker i drift**: tider, kompetanse og merknad står i driftraden, ikke
      bare bak en blyant.
- [ ] **Drift inn og ut står i audit-loggen**, med hvem.

## 11. Offline (drifts-PC uten nett)

- [ ] **Service workeren er registrert** (`/vaktliste/sw.js` under Application →
      Service Workers), og merket «klar for offline» kommer i vaktlinja.
- [ ] **Slå av nettet** (DevTools → Offline) → sida laster fortsatt, med et varsel om at
      den viser en kopi.
- [ ] **Stemple møtt offline** → raden oppdaterer seg, og stemplingen står i kø.
- [ ] **Stemple flere** → alt går i kø, i rekkefølge. *Står noe i kø, går alt i kø.*
- [ ] **Slå på nettet igjen** → køen går gjennom innen ~15 sekunder, og stemplingene får
      **tidspunktet du trykket**, ikke tidspunktet nettet kom tilbake.
- [ ] **En kopi eldre enn 24 timer brukes ikke.**
- [ ] **Innlogging omdirigeres aldri fra kopien**: logg ut i en annen fane, gå offline, og
      se at du ikke får en «innlogget» side du ikke er innlogget på.
- [ ] **«Logg ut» rydder**: etterpå er Cache Storage og `localStorage` for
      `/vaktliste/` tomme, og workeren borte.

## 12. Reserven: lista som fil

- [ ] **Last ned fila** fra «Innstillinger» → den åpner i nettleseren, uten nett, og er
      lesbar uten portalens CSS.
- [ ] **Innholdet**: navn, rolle, tider, korps, telefon og ISSI. **Ikke** e-post, notat
      eller merknad.
- [ ] **Send til mottakerne** (satt under `/portal-admin/innstillinger/`) → utsendingen står
      i lista, med resultat.
- [ ] **E-post nede stenger ikke innsjekken**: sett en ugyldig mottaker og sett lista i
      drift → drift lagres, og feilen står på utsendingen.
- [ ] **Intervallsending**: sett et kort intervall, endre noe i lista → ny utsending. Endre
      ingenting → ingen ny utsending.

## 13. Koblingen til `/oppdrag/`

- [ ] **Besetningen i sentralbordet**: åpne en koblet enhet i `/oppdrag/` → navn, rolle,
      innsjekkstatus, telefon og ISSI.
- [ ] **Ikke** kompetanser, notat, e-post eller konto.
- [ ] **En ukoblet enhet** gir «ikke koblet»; en enhet koblet i **en annen vakt** gir en
      annen beskjed. De to skal ikke se like ut.
- [ ] **Dekker ingen skift nå** → svaret sier «ingen nå, \<navn\> fra 16:00».
- [ ] **Besetningen filtreres ikke på korps** — sentralbordet spør «er bilen klar».
- [ ] **En ren `les`-konto uten oppdragstilgang** kan ikke hente besetningen for en
      vilkårlig enhet (403).
- [ ] **Lista i drift vinner** over portalens aktive vakt når de er ulike.

## 14. Utskrift

- [ ] **Utskriftslista er gruppert dag → ressurs**, med korps som kolonne.
- [ ] **Dagvelgeren** avgrenser til én dag, og tallene i arkhodet gjelder **den** dagen.
- [ ] **En endagsvakt har ingen dagvelger** — bare utskriftsknappen.
- [ ] **Dagoverskriften står også på en endagsvakt.**
- [ ] **Utskrift fra en gruppefane** skriver ut den fanen du står i.
- [ ] **En ressurs uten skift** står under «Uten skift», og bare da.

## 15. Skjerm og form

- [ ] **Under 992 px** brytes vaktlinja til tre linjer, og knappene står samlet.
- [ ] **Under 1280 px** ruller ressurstabellen — og **handlingskolonnen blir stående**, med
      egen bakgrunn, så innholdet ikke ruller synlig under den.
- [ ] **Tidsfeltene stikker ikke ut over nabocella** i noen bredde, verken i planleggings-
      eller driftformen.
- [ ] **Kolonnene står rett under overskriftene sine** i alle tabellene. *Et flex-oppsett
      lagt rett på en `<td>` forskyver alt etter den.*
- [ ] **Tidsfeltene har fem minutters steg** og ikke et sekundsegment.
- [ ] **Ingen dempet Bootstrap-tekst som forsvinner** mot den mørke bakgrunnen.

## 16. Tilgangsmatrise — prøv at veggen kommer før knappen

| Handling | `les` | `les_alle` | `skriv_handling` | `skriv_full` | `skriv_leder` | admin |
|---|---|---|---|---|---|---|
| Se eget korps | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Se alle korps | ✖ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Fylle plass i eget korps | ✖ | ✖ | ✔ | ✔ | ✔ | ✔ |
| Fylle plass i annet korps | ✖ | ✖ | ✖ | ✔ | ✔ | ✔ |
| Rette ressursens navn | ✖ | ✖ | ✔¹ | ✔ | ✔ | ✔ |
| Opprette/slette skift, sette tider | ✖ | ✖ | ✖ | ✔ | ✔ | ✔ |
| Stemple møtt / av vakt | ✖ | ✖ | ✖ | ✔ | ✔ | ✔ |
| Reservere, `alle_korps`, enhetskobling | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ |
| Opprette/slette ressurs, grupper, roller | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ |
| Vaktas lengde og timetak | ✖ | ✖ | ✖ | ✖ | ✔ | ✔ |
| Slette en vaktliste, koble konto for hånd | ✖ | ✖ | ✖ | ✖ | ✖ | ✔ |

¹ når hun kan bemanne ressursen eller en av plassene på den.

- [ ] Hver ✖ prøvd i grensesnittet (knappen er borte) **og** mot endepunktet (403).

## 17. Regresjoner — det som har truffet prod før

- [ ] **Låst felt som lot seg endre** på iPhone og ble filtrert bort ved lagring (§6).
- [ ] **403 på å skrive en merknad** i en plass korps-føreren har lov til å fylle (§5).
- [ ] **Vaktlistevelgeren som bare byttet liste ved neste klikk** (§2).
- [ ] **Tomme tidsfelter i «Ny vaktliste»**, som måtte tastes segment for segment (§2).
- [ ] **«Mitt korps» inne i gruppefanene** i stedet for etter dem (§3).
- [ ] **Nattevakter på feil dag** i dagbolkene (§9).
- [ ] **Planleggerfelter som ble blanke** ved neste tegning, og planleggeren som sto tom
      etter en generering (§8).
- [ ] **Knapper som førte til 403** fordi markupen gatet på badgen i stedet for på hva
      nivået faktisk får gjøre (§5, §16).

---

## Etterpå

Skriv resultatet der det kan finnes igjen: byggnummer, gren, dato, hvilke punkter som
feilet, og hva som ble gjort. Et funn som ikke er skrevet ned er et funn som blir gjort
på nytt neste gang.
