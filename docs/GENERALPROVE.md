# Generalprøve før vakta

**Hva denne er.** Én sammenhengende øvelse på staging, med ekte folk og ekte telefoner,
noen uker før neste vakt. Den prøver det verken testsuiten eller sjekklistene kan prøve
alene: at sentralbordet, bilene, KO, vaktlista og pasientregistreringen **henger sammen**
når flere mennesker bruker dem samtidig.

**Hvorfor nå, og hvorfor denne gangen.** Neste vakt er første gang **flere biler per
oppdrag** (innført 11. sep. 2026) brukes i virkeligheten. Den gamle kolonnen
`Oppdrag.enhet` står fortsatt som nødutgang, og G6b/G6c i `TODO.md` fjerner den først
*etter* vakta. Generalprøven er testen den nødutgangen egentlig ventet på. Den prøver også
alt som er endret i rundene siden forrige vakt.

**Hva den ikke er.** Den er ikke en erstatning for
[`TESTSJEKKLISTE_KO.md`](./TESTSJEKKLISTE_KO.md) og
[`TESTSJEKKLISTE_VAKTLISTE.md`](./TESTSJEKKLISTE_VAKTLISTE.md), som går gjennom én modul om
gangen. Kjør dem i forkant, gjerne dagen før. Denne lista peker på dem der de dekker
detaljene, og bruker tiden sin på samspillet.

---

## 0. Før dagen

**Når.** 3–4 uker før vakta, **etter fastfrysingen** (se `TODO.md`). Det er bygget som
prøves her som skal kjøres på vakta. Endres koden etterpå, er generalprøven prøvd på noe
annet.

**Bygget.** Noter byggnummeret i footeren på staging. Det skal være det samme som går til
`main` før vakta. Står det noe annet, er det ikke det samme som prøves.

**Folk og utstyr.** Minst seks personer, eller færre som bytter rolle:

| Rolle | Konto | Utstyr | Hvorfor |
|---|---|---|---|
| Sentralbord 1 og 2 | `oppdrag` `skriv_full` | To PC-er | To operatører på samme tavle er der endringsnummeret og ETag-ene prøves |
| KO-leder | `ko`/`oppdrag` `skriv_leder`, `vaktliste` `les_alle` | PC, gjerne to skjermer | Skjerm 2 og hendelsene |
| Bil A | Enhetskonto (delt), `skriv_handling` | **iPhone** | iOS demper lyd med ringebryteren — lydvarselet må prøves der |
| Bil B | Enhetskonto (delt), `skriv_handling` | Android | Den andre plattformen |
| Bil C (spesialressurs) | Enhetskonto på en enhetstype med **passiv vakt** og **avvente** | Hvilken som helst | Avvent og passiv vakt |
| Vaktleder | `vaktliste` `skriv_leder` | Drifts-PC | Drift, stempling, offline |
| Pasientregistrering | `patients` `skriv_full` | PC eller nettbrett | Den parallelle flyten |
| Admin | Global admin | PC | Server-status, arkiv, backup |

**Oppsett på staging.**
- En aktiv vakt, og en vaktliste **i drift** med skift som dekker øvelsestiden.
- Bilene er koblet til sine enheter, står **på vakt**, og har en enhetstype.
- Lokasjoner, problemstillinger (også en som bærer antall, som «Transport») og
  lydvarselets terskler er satt opp i «Valglister».
- **Ta manuelle backuper** på `/portal-admin/backup/` før dere begynner (modulene dere
  bruker, eller den hele), så staging kan settes tilbake etterpå.
- `/portal-admin/server-status/` er grønn: konfig, offsite og databasen.

---

## 1. Oppstart (10 min)

- [ ] Alle logger inn. Bilene åpner `/oppdrag/` og får bilskjermen, ikke sentralbordet.
- [ ] Hver bil trykker én gang hvor som helst for å vekke lyden. **Bil A prøver med
      ringebryteren på lydløs**: lyden skal likevel komme.
- [ ] Sentralbordet ser alle tre bilene i ressurslista, som «Ledig».
- [ ] KO-leder åpner `/ko/`, og ser de samme bilene i ressursoversikten.

## 2. Ett oppdrag, hele kjeden (15 min)

- [ ] Sentralbord 1 oppretter et oppdrag på bil A. **Bil A piper** og får en rad i bjella.
- [ ] Sentralbord 2 ser det nye oppdraget innen noen sekunder, uten å laste siden på nytt.
- [ ] Bil A: Rykker ut → Fremme → Avreist («Annet sted» med fritekst) → Leverer → Ledig.
      Sentralbordet ser hver status med klokkeslett.
- [ ] **Grovsorteringen kreves** før Ledig fra Leverer. Prøv å hoppe over den.
- [ ] **«Udefinert»-sperra:** opprett et oppdrag med problemstilling «Udefinert». Bilen
      skal ikke kunne melde Ledig før sentralbordet har satt problemstillingen.
- [ ] Oppdraget går til **historikken** av seg selv når det er ferdig.

## 3. Flere biler på ett oppdrag — det nye (25 min)

Dette er hovedgrunnen til generalprøven.

- [ ] Opprett et oppdrag på bil A. **Varsle bil B** på samme oppdrag («Legg til»).
      Begge piper.
- [ ] Begge rykker ut. Hver bil ser **sin egen kjede**, og den andres stempler i
      tidslinjen med navn på raden.
- [ ] Sentralbordet ser matrisen: begge bilene med hver sin status.
- [ ] Bil A melder Ledig. **Oppdraget er ikke ferdig** før bil B også er det.
- [ ] Bil B blir ferdig, og oppdraget går til historikken.
- [ ] **Historikksøket** finner oppdraget både på bil A og **på bil B**.
- [ ] **Ta av en bil** mens den står i Venter. Prøv det samme etter at den har rykket ut:
      det skal ikke gå.
- [ ] **Flytt** et oppdrag fra bil A til bil C mens det venter. Bil C piper, bil A slutter.
      «Fra» i flytt-vinduet viser bare biler som fortsatt har oppdraget.
- [ ] **Opprett et oppdrag uten bil.** Det står som «trenger ressurs». Varsle en bil, og
      den første som varsles blir primær.

## 4. Når noe går annerledes (20 min)

- [ ] **Avbryt fra bilen** (i Rykker ut eller Fremme): oppdraget får «trenger ny
      ressurs», og et **dempet** avbrutt-merke. Kvitter merket. Varsle en ny bil, og merket
      forsvinner av seg selv.
- [ ] **Sentralbordet fører «Avbrutt»** for en bil som melder det på samband.
- [ ] **Behandlet på sted:** ett trykk gir Behandlet og Ledig. På Drift og Plassering heter
      knappen «Utført».
- [ ] **Rykk ut på et nytt oppdrag** mens bilen står på et annet: det forrige lukkes for
      bilen, og tavla sier hva som skjedde.
- [ ] **Sentralbordet fører status** bakover og framover. Bakover trekkes meldingene
      tilbake, de slettes ikke.
- [ ] **«Rett tid»** på en statusmelding: rettingen legges som en ny rad ved siden av den
      gamle, og tidslinjen viser den rettede tida.
- [ ] **Bil C (spesialressurs):** sett den i **passiv vakt**. Merket vises på kortet. Varsle
      den, og la den **avvente**: oppdraget skal fortsatt si «trenger ny ressurs». La den så
      rykke ut.
- [ ] **Antall pasienter:** på «Transport» setter bilen antallet, og sentralbordet ser det.

## 5. Nettet forsvinner (15 min)

- [ ] **Bil B i flymodus:** stemple to overganger. Skjermen sier at noe ikke er sendt. Slå av
      flymodus, og meldingene kommer fram **med tida trykket skjedde**, ikke tida de ble
      sendt.
- [ ] **Drifts-PC-en uten nett:** følg
      [`TESTSJEKKLISTE_VAKTLISTE.md`](./TESTSJEKKLISTE_VAKTLISTE.md) §11.
- [ ] **En skjult fane:** la sentralbord 2 ligge i bakgrunnen i fem minutter mens det skjer
      ting. Hent den fram, og tavla skal være à jour innen noen sekunder.

## 6. KO og samspillet (20 min)

Detaljene står i [`TESTSJEKKLISTE_KO.md`](./TESTSJEKKLISTE_KO.md). Her prøves koblingen
til sentralbordet og bilene:

- [ ] KO-leder oppretter en **hendelse**, knytter et av oppdragene til den, og setter et
      **lag** på hendelsen.
- [ ] KO **deler en logglinje** med bilen på oppdraget. Bilen ser den nye teksten.
- [ ] **Skjerm 2** viser hendelsen som er valgt på skjerm 1.
- [ ] Endringer på tavla og i loggen synes hos den andre operatøren innen få sekunder.

## 7. Pasientregistrering parallelt (hele tiden)

- [ ] Registrer pasienter mens resten pågår: ankomst, grovsortering, obs, utskrevet.
- [ ] Header-tallene og `/statistikk/` (pasientfanen) følger med.

## 8. Under belastning (hele tiden)

- [ ] Admin holder `/portal-admin/server-status/` oppe: beredskapstrinnet, P95, feil (5xx),
      databasen og sesjonene, med hvem som faktisk er aktiv.
- [ ] **Ingen 5xx** i løpet av øvelsen. Dukker det opp én, noter tid og hva som ble gjort.

## 9. Avslutningen — like viktig som resten (20 min)

- [ ] Rydd tavla: alt i historikken.
- [ ] **Arkiver oppdragene.** Arkiveringen skal nekte mens noe står på tavla. Etterpå er
      tavla, historikken og telleren tomme, og neste oppdrag får nummer 1.
- [ ] **Statistikken for arkivet:** «oppdrag» og «enhetsinnsatser» er to ulike tall når
      flere biler har vært på samme oppdrag. Sjekk at begge ser riktige ut, og at
      responstiden er per bil.
- [ ] **Avslutt vakta i pasientregistreringen** («Avslutt vakt»). Den tar backup først.
- [ ] `/portal-admin/backup/`: backupene er skrevet, og **offsite står grønt**.
- [ ] Til slutt, om staging skal tilbake til utgangspunktet: gjenopprett fra backupene i
      §0 på `/portal-admin/backup/`.

---

## Funn

**Hvert funn går i `/backlog/`** som bug, med byggnummer, rolle, hva som ble gjort, og hva
som skjedde. Da ligger funnene ett sted, og kan følges til de er rettet.

Et funn som suiten burde ha fanget er **to** funn: feilen, og hullet i dekningen. Si fra om
begge.

## Etterpå: avgjørelsene generalprøven gir

| Utfall | Hva det betyr |
|---|---|
| Ingen funn, eller bare småting | Bygget kan gå til `main`. G6b/G6c tas etter vakta som planlagt |
| Funn i flyten med flere biler | Rettes før vakta. Nødutgangen (den gamle kolonnen) blir stående |
| Funn som krever endringer etter fastfrysingen | Rett bare det som må rettes, og kjør de berørte delene av prøven på nytt |
