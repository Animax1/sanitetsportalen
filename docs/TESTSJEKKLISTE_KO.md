# Testsjekkliste – `/ko`

**Hva denne er.** En manuell gjennomgang av KO-flata før en vakt, etter en deploy, eller
når noe er endret i modulen. Den prøver det testsuiten **ikke** kan prøve: at markupen
tegnes, at to operatører på hver sin PC ser det samme, at et trykk fører et sted, og at
sammensetningen av tre moduler (KO, oppdrag, vaktliste) henger sammen i en nettleser.

**Hva den ikke er.** Den er ikke en erstatning for `python manage.py test ko` — reglene i
`ko/services.py` er prøvd der, og med mutanter. Går en av dem i stykker, skal suiten si
fra, ikke denne lista. Finner du noe her som suiten burde ha funnet, er funnet **to**
ting: feilen, og et hull i dekningen.

**Noter byggnummeret i footeren** før du begynner, og hvilken gren miljøet står på
(`rollemodell` = staging, `main` = prod). Uten det vet ikke den som leser resultatet hva
som ble prøvd.

---

## 0. Før du begynner

**Kontoene.** Nivåene er poenget med halve lista, og de kan ikke prøves med én konto.
Sett opp fem, og la dem stå mellom gjennomgangene:

| Konto | `ko` | `oppdrag` | `vaktliste` | Prøver |
|---|---|---|---|---|
| `test-ko-les` | `les` | – | – | Loggen alene, uten oppdragsflate |
| `test-ko-fore` | `skriv_full` | `skriv_full` | `les` | Den vanlige operatøren |
| `test-ko-leder` | `skriv_leder` | `skriv_leder` | `les_alle` | Sletteinngangen, KO-innstillingene |
| `test-ko-uten` | – | `skriv_full` | `les` | At `/ko/` er stengt uten KO-rad |
| `admin` | (global admin) | | | Nullstilling, portalinnstillinger |

*Hvorfor fem:* fravær av rad **er** ingen tilgang, og global admin får toppen av stigen
uten rader i det hele tatt. En gjennomgang med bare admin prøver derfor nøyaktig den ene
brukeren som aldri møter en sperre.

**Data.** En aktiv vakt, minst to ressurser i vaktlista **uten** oppdragsenhet (lag) med
skift som dekker nå, minst to koblede enheter (biler), og ett åpent oppdrag.

**Nettlesere.** Chrome eller Edge på KO-PC-en (den flata er bygget for), og én
gjennomgang av §2 og §10 på en liten skjerm.

---

## 1. Oppstart og tilgang

- [ ] **`/ko/` åpner med fire vinduer.** Logg inn som `test-ko-fore` → `Hendelseslogg` og
      `Loggstrøm` øverst, `Ressursoversikt` og `Oppdragsliste` nederst. Ingen faner.
- [ ] **Ingen feil i konsollen** ved lasting. *Særlig verdt å se etter: `ReferenceError` —
      KO lastes av tre JS-filer, og alt som kjører på toppnivå står i den siste.*
- [ ] **Uten KO-rad er døra stengt.** `test-ko-uten` → `/ko/` gir 403, og KO står ikke i
      menyen.
- [ ] **Uten oppdragstilgang står loggen.** `test-ko-les` → hendelsesloggen og loggstrømmen
      virker; oppdragsflata er erstattet av «Krever tilgang til oppdragsmodulen», ikke av
      en tom kolonne.
- [ ] **Modulen slått av** (`/portal-admin/moduler/` → KO av) gir 403 for alle andre enn
      global admin. Slå den på igjen.
- [ ] **Vaktnavnet i hodet** er den aktive vakta.

## 2. Rutenettet (`static/js/ko-layout.js`)

- [ ] **Bytt plass på to vinduer.** Dra håndtaket (⠿) i ett vindu over et annet → de bytter
      plass. Alle fire er fortsatt synlige.
- [ ] **Dra skillelinja mellom to vinduer** i samme rad → bredden endres, og begge vinduene
      har fortsatt innhold. Dra helt ut → vinduet blir smalt, men **forsvinner ikke**.
- [ ] **Dra skillelinja mellom radene** → høydene endres, og ingen rad kollapser.
- [ ] **Oppsettet huskes.** Last siden på nytt → samme plassering og bredder. Logg ut, logg
      inn som en annen KO-konto i samme nettleser → **samme** oppsett. *Det er per
      nettleser med vilje: KO-PC-en beholder sitt uansett hvem som sitter der.*
- [ ] **«Tilbakestill oppsett»** (nedtrekket i verktøylinja) → 2×2 tilbake.
- [ ] **Et ødelagt oppsett avvises.** Sett `ko.oppsett` i `localStorage` til `{"a":1}` og
      last på nytt → standardoppsettet, ingen tom side.
- [ ] **Sida ruller ikke.** Legg inn nok logglinjer til at loggstrømmen fylles → det er
      *vinduet* som ruller, ikke sida.
- [ ] **Zoom til 150 % og smal vindusbredde** slik at verktøylinja brekker til to linjer →
      vinduene fyller fortsatt skjermen uten at nederste rad havner under folden.
- [ ] **Under 1200 px** stables de fire vinduene, og sida ruller normalt.

## 3. Loggstrømmen

- [ ] **Loggfør en linje.** Skriv tekst, la tidsfeltet stå blankt → linja står i strømmen
      med klokkeslettet nå, navnet ditt og ansvarsmerket ditt.
- [ ] **Oppgi et tidspunkt** i tidsfeltet → linja får det tidspunktet, ikke nå.
- [ ] **Tom tekst** → skjemaet sier fra, ingenting lagres.
- [ ] **Maks lengde** håndheves (feltet stopper), og lang tekst brytes i strømmen.
- [ ] **To faner, én vakt.** Skriv en linje i fane A → den står i fane B innen 15 sekunder
      uten at du gjorde noe. *Pollen er 15 s for loggen.*
- [ ] **Rett en linje** (`skriv_full`) → den rettede teksten står, og den opprinnelige er
      synlig som rettet, ikke borte. Rett rettelsen → linja **hopper ikke** i strømmen.
- [ ] **Fjern en linje** (`test-ko-leder`) → teksten er borte fra strømmen i *begge* faner.
      `test-ko-fore` har ingen fjern-knapp, og endepunktet gir 403.
- [ ] **Fest en linje** → den står festet. Fest den igjen → ingen endring, ingen feil.
      Løsne → tilbake i strømmen. Festing skal slå gjennom i den andre fana uten
      sidelasting.
- [ ] **En systemlinje kan ikke festes** og ikke merkes uformell.
- [ ] **Ansvarsmerket.** Velg et ansvarsområde i nedtrekket → merket står på linjene du
      skriver etterpå, og i sidebaren. Prøv med `test-ko-les` → **hun får lov**; merket er
      `les`-nivå.
- [ ] **Chat er av som standard.** Avkryssingen «uformell» finnes ikke. Slå på
      `ko.chat_tillatt` under `/portal-admin/innstillinger/` → avkryssingen kommer. Slå av
      igjen → linjene som alt er skrevet **står fortsatt**, bare nye stoppes.
- [ ] **XSS.** Loggfør `</script><img src=x onerror=alert(1)>` → teksten står som tekst,
      ingen dialog, ingen `[object Object]` i strømmen.

## 4. Systemlinjene

- [ ] **Stemple et oppdrag** fra `/oppdrag/` (eller fra tavla) → én linje i strømmen om det
      som skjedde, ikke én per felt.
- [ ] **Endre et oppsettfelt** (f.eks. en lokasjon under verdilistene) → **ingen** linje.
      *Regelen er «løft det som endrer situasjonen, ikke det som endrer oppsettet».*
- [ ] **KO-loggen er aldri kritisk vei.** Tar du KO-modulen av mens en bil stempler, skal
      stemplingen gå gjennom i bilen som før.

## 5. Hendelsene

- [ ] **Ny hendelse.** «Ny hendelse» → skjemaet har Hvor, Hva skjer, Melder, Beskrivelse,
      Prioritet og Lag. Opprett → hendelsen får et **H-nummer**, står øverst i
      hendelsesloggen, og beskrivelsen er første linje i hendelsens egen logg.
- [ ] **Nummerserien er KOs egen** — H-nummeret følger ikke O-nummeret på oppdragene.
- [ ] **Melder.** Kryss av flere (AMK + Politi) → begge står. Kryss av «Andre» uten tekst →
      avvist. Skriv tekst, fjern «Andre» igjen → teksten tømmes.
- [ ] **Prioritet.** Standard er Grønn. Sett Viktig → rangeringen flytter hendelsen øverst,
      og endringen står som **egen linje** med fra, til og hvem. Prøv hele rekka: Viktig,
      Rød, Gul, Grønn, Drift, Plassering.
- [ ] **Lagene.** Velgeren tilbyr bare ressurser uten oppdragsenhet **med skift som dekker
      nå**. Et lag hvis skift starter om to timer skal ikke stå der.
- [ ] **Et lag som alt står på hendelsen kan bli** når skiftet går ut — lagringen skal ikke
      låse seg. Å *legge til* et lag uten skift avvises.
- [ ] **Hendelsen åpnes i loggstrømmens vindu**, ikke i en modal: hendelsesloggen står
      med raden merket blått, og ressursoversikten og oppdragslista er synlige mens du
      arbeider i den. Klikk på samme rad igjen → lukkes; klikk på en annen rad → bytter.
      «← Loggstrøm» gir strømmen og skrivefeltet tilbake — **ikke** skrivefeltet for en
      konto med bare `les`.
- [ ] **Rediger hodet i to faner samtidig.** Åpne samme hendelse i A og B, lagre i A, lagre
      så i B → B får **409** og en beskjed om at noen andre har endret, ikke en stille
      overskriving.
- [ ] **Lukk en hendelse med åpne oppdrag** → 409 med **antallet**, og en bekreftelse som
      lar deg gå videre. Antallet står på linja etterpå.
- [ ] **Gjenåpne** en lukket hendelse → den åpnes, og det står i loggen.
- [ ] **En lukket hendelse tar ikke imot** nye lag eller nye oppdragsknytninger, men tar
      imot en **kommentar** (etterskrift).
- [ ] **«Bli med»** → du står blant deltakerne. Skriv en kommentar / sett prioritet som en
      annen konto → hun meldes inn av seg selv. **Å bare lese melder ingen inn.**
- [ ] **Søket** filtrerer på H-nummer, tittel, sted, melder, loggen og lag.
- [ ] **«Vis lukkede»** → lukkede hendelser kommer fram, nederst.
- [ ] **Hendelse fra en logglinje** → linja **blir stående** i strømmen og får hendelsen;
      hendelsen peker tilbake.

## 6. Loggen i hendelsen og deling til enhetene

- [ ] **Intern som standard.** Skriv en kommentar i H-en → den står i hendelsen, **ikke** i
      loggstrømmen, og bilen ser den ikke.
- [ ] **«Del»** → linja går til **alle** oppdrag i hendelsen. Knytt et nytt oppdrag til
      hendelsen etterpå → den delte linja følger med dit også.
- [ ] **«Del med \<enhet\>»** i et oppdrag → bare den ene bilen ser den.
- [ ] **I bilen** (`/oppdrag/` som enhetskonto) står den delte linja, **gul det første
      minuttet**.
- [ ] **Angre deling** begge veier → linja forsvinner fra bilen.
- [ ] **En retting arver delingen** — rett en delt linje, og bilen ser rettelsen.
- [ ] **«Nytt oppdrag» fra hendelsen** arver hastegrad av prioriteten og beskrivelsen som
      oppdragsnotat.

## 7. Ressursoversikten

- [ ] **Alle | Biler | Lag** filtrerer, det skjulte står som et tall, og valget huskes ved
      sidelasting (per nettleser).
- [ ] **Lagkortet** viser hvor mange som er møtt («0 av 2 møtt» er et gyldig svar), og «På
      H14 · Hovedscene · 23 min» når laget står på en åpen hendelse.
- [ ] **Bilkortet** viser oppdragets sted etter problemstillingen. Flytt oppdraget til en
      annen lokasjon fra «Rediger oppdrag» → kortet følger etter uten sidelasting.
- [ ] **Besetningen bak et klikk**, én om gangen: åpne bil A, så bil B → A lukkes.
- [ ] **«i» i hodet** folder ut fargeforklaringen, og valget huskes.
- [ ] **Ingen `[object Object]`** på noe kort. *Den har truffet prod to ganger — se §12.*
- [ ] **Et lag uten skift nå** står ikke i lista i det hele tatt.

## 8. Oppdragslista (oppdragsmodulens flate i KO)

- [ ] **Samme som sentralbordet.** Opprett et oppdrag fra `/ko/`, og sammenlign med
      `/oppdrag/` i en annen fane → samme kort, samme knapper, samme status.
- [ ] **H-merket** står på raden når oppdraget hører til en hendelse, med rød trekant når
      hendelsen er Viktig. Ingen gruppering på hendelse i lista.
- [ ] **Knytt et eksisterende oppdrag** til en hendelse → merket kommer, og det står i
      loggen.
- [ ] **Minimering.** Klikk gruppeoverskriften → gruppa lukkes, antallet står i
      overskriften, og tilstanden huskes ved sidelasting.
- [ ] **«Nytt oppdrag» uten enhet** → oppdraget opprettes med «Trenger ressurs», og
      knappen skiftet tekst før du trykket.
- [ ] **«Historikk»** åpner **oppdragsarkivet** — oppdragsmodulens flate, og den følger
      oppdragstilgangen, ikke KO-nivået. `test-ko-les` (uten oppdrag) ser den ikke.
- [ ] **Tilgangen er oppdragsmodulens.** Ta `oppdrag`-raden fra `test-ko-fore` → flata
      forsvinner, loggen står.

## 9. Sidebaren «Har KO oppe»

- [ ] **Åpne nedtrekket** → én rad per person, ikke per fane. Logg inn som samme bruker på
      telefon og PC → fortsatt **én** rad.
- [ ] **Global admin står i lista** selv uten `ModulTilgang`-rad.
- [ ] **Inaktiv-kolonnen** teller opp når du lar fana stå urørt, og nullstilles ved et
      klikk i portalen. En sesjon fra før måles ikke som «aktiv nå».
- [ ] **Nedtrekket åpnes med ett klikk** og lukkes med ett. *Knappen har bevisst ingen
      `data-action` — to lyttere på samme klikk er en kjent felle.*
- [ ] **Lista pollers bare når nedtrekket er åpent** (se nettverksfanen).

## 10. KO-innstillinger og nullstilling

- [ ] **Ansvarsområder** (`test-ko-leder`): opprett, endre navn, endre rekkefølge, slett.
      «I bruk» teller kontoene som bærer merket nå.
- [ ] **Et slettet område rører ikke loggen** — linjene beholder teksten sin.
- [ ] **`test-ko-fore` ser fanen, men får ikke redigere** (403 fra endepunktet).
- [ ] **Nullstilling** (bare `admin`): oppdrag, hendelser og logg hver for seg, med
      bekreftelse. Uten bekreftelse → 400. Som `test-ko-leder` → 403.
- [ ] **Etterpå står det i audit-loggen** hvem som tømte hva, og hvor mange rader.
- [ ] **Portalinnstillingene**: `ko.logg_dager` lar seg endre innenfor grensene, avvises
      utenfor, og endringen står i audit-loggen.

## 11. Tilgangsmatrise — prøv at veggen kommer før knappen

*Regelen er at grensesnittet gater på tilgang, ikke på rolle: en knapp som fører til 403 er
verre enn ingen knapp. Prøv derfor begge deler — at knappen er borte, **og** at endepunktet
sier nei.*

| Handling | `les` | `skriv_full` | `skriv_leder` | admin |
|---|---|---|---|---|
| Se loggen og hendelsene (aktiv vakt) | ✔ | ✔ | ✔ | ✔ |
| Sette eget ansvarsmerke | ✔ | ✔ | ✔ | ✔ |
| Føre og rette linjer | ✖ | ✔ | ✔ | ✔ |
| Feste / løsne | ✖ | ✔ | ✔ | ✔ |
| Opprette og lukke hendelser | ✖ | ✔ | ✔ | ✔ |
| Fjerne en linje | ✖ | ✖ | ✔ | ✔ |
| Redigere ansvarsområdene | ✖ | ✖ | ✔ | ✔ |
| Nullstille | ✖ | ✖ | ✖ | ✔ |

- [ ] Hver ✖ prøvd i grensesnittet (knappen er borte) **og** mot endepunktet (403).

**Tidligere vakters logg har ingen flate ennå.** Nivået `skriv_leder` er deklarert for
den, men `api/logg/` svarer bare for **aktiv vakt** — let ikke etter en vaktvelger i
loggstrømmen, og meld den ikke som en feil. «Historikk»-knappen i oppdragslista er
oppdragsarkivet, som er noe annet.

## 12. Regresjoner — det som har truffet prod før

*Disse står her fordi de har skjedd. De er billige å prøve og dyre å oppdage på vakt.*

- [ ] **`[object Object]` på et kort eller i en celle.** Egenbygd markup som havner i en
      mal-streng blir til dette, også når innholdet er tomt — altså på *hver* rad.
- [ ] **Et nedtrekk som lagrer ved klikk.** Åpne ansvarsnedtrekket uten å velge noe → ingen
      lagring, ingen omtegning, og lista forsvinner ikke under fingeren.
- [ ] **Lydvarsel i bilen** på iPhone med ringebryteren av: oppdrag til en enhet skal pipe.
- [ ] **Modal som blir liggende for skjermlesere.** Lukk en modal og trykk Tab → fokus er i
      sida bak, ikke i den lukkede modalen.
- [ ] **Vinduer som forsvinner** når man drar en skillelinje helt ut (gulvet skal stoppe
      det).

---

## Etterpå

Skriv resultatet der det kan finnes igjen: byggnummer, gren, dato, hvilke punkter som
feilet, og hva som ble gjort. Et funn som ikke er skrevet ned er et funn som blir gjort
på nytt neste gang.
