# Testsjekkliste – `staging` til `main`, september 2026

**Hva denne er.** Det som bør prøves for hånd på staging før det som ligger der går til
prod. Den dekker **bare det som er endret** mellom `main` (`4813cee`) og `staging`
(`729fe04`; commitene etter `6a6a8a6` er bare dokumenter): de tekniske rundene 6–8, G6a og feilrettingene underveis. Alt står i
`CHANGELOG.md` under 26. sep. 2026.

**Hva den ikke er.** En gjennomgang av hele portalen. Den finnes i
[`GENERALPROVE.md`](./GENERALPROVE.md) og testsjekklistene for KO og vaktlista. Denne er
kortere med vilje: det meste av arbeidet var intern omstrukturering som suiten og
mutantene dekker, og som du ikke ville sett forskjell på i grensesnittet.

**Når den er brukt opp.** Etter at `staging` er i `main`. Slettes da, eller flyttes til
`docs/archived/`.

**Før du begynner.** Noter byggnummeret i footeren på staging. Regn med rundt en time.
Funn går i `/backlog/`, med byggnummer.

---

## 1. Må testes: rører data eller noe destruktivt (20 min)

**Oppdrag og biler** (runde 7: transaksjonen og låsingen i statusmeldingene, G4 og G6a)
- [ ] Kjør ett oppdrag gjennom hele kjeden fra en bil på telefonen: Rykker ut → Fremme →
      Avreist → Leverer → Ledig. Hver status skal komme én gang, med riktig tid.
- [ ] Trykk **«Opprett» flere ganger fort** i «Nytt oppdrag», på `/oppdrag/` og på `/ko/`:
      ett oppdrag (27. sep.). Åpne vinduet igjen og opprett: det blir et nytt.
- [ ] **Dobbelttrykk** på en stemplingsknapp i bilen (27. sep.): skjermen viser neste steg
      med en gang, knappene er grå et øyeblikk, bare én status kommer — og **ingen rød boks**
      med «Oppdraget står i …».
- [ ] Legg til **bil nummer to** på et oppdrag og kjør begge ferdig. Tavla, detaljvinduet,
      historikken og **historikksøket på bil nr. 2** skal vise riktige biler.
- [ ] **Arkiver vakta i oppdrag** og åpne arkivstatistikken: tall per bil og antall
      oppdrag skal se riktige ut.

**Vakter** (runde 8: én felles måte å lage vakter på)
- [ ] `/vaktliste/`, «Ny vaktliste» med et **navn som allerede finnes**: du skal få en
      melding, ikke en feilside.
- [ ] «Ny vaktliste» med «kopier fra» en eksisterende liste: ressursene blir med.
- [ ] Pasientsiden, «Avslutt vakt» med et navn som finnes: melding, og **ingen pasienter
      slettet**. Kjør den så med et nytt navn. Dette er destruktivt, men på staging er det
      greit.

**Kontoer** (runde 8: pensjonering av bil)
- [ ] Slett kontoen til en bil som har vært **bil nummer to** på et oppdrag. Du skal få
      «Enheten er pensjonert», ikke en feilside.
- [ ] Bytt passord med en konto som er innlogget i to nettlesere. Den andre skal bli
      logget ut.

**Moduloppsett og backup** (runde 8: `backup_enabled`-kolonnen er slettet)
- [ ] `/portal-admin/moduler/`: slå en modul av og på.
- [ ] Slå av `/ko/`: en **vanlig bruker** får 403 på adressen, admin kommer inn (med vilje —
      forberedelse i kulissene). Menyen skjuler den for begge.
- [ ] `/portal-admin/backup/`: ta en backup av én modul. Offsite skal stå grønt.

## 2. Bør testes: sider som er flyttet eller skrevet om (20 min)

**`/portal-admin/server-status/`** (G1: hele skriptet er flyttet ut av malen)
- [ ] Alle kortene fylles, og den oppdaterer seg hvert 10. sekund.
- [ ] Sesjonslista viser **«aktiv nå» for deg selv**. Dashbordet måler nå
      tilstedeværelse; før viste det «ukjent».
- [ ] «Logg ut» på én sesjon virker. **Ikke trykk «Nødbrems»**; den logger ut alle
      andre.

**KO-tavla** (G4)
- [ ] En bil på oppdrag vises med merke («O12 Rykker ut») og riktig «fra»-tid. Et lag på
      en hendelse vises med «På H…».

**Faner i bakgrunnen** (G5: pollingen i skjulte faner)
- [ ] Legg `/ko/` og sentralbordet i en bakgrunnsfane i et par minutter mens noen gjør
      endringer. Hent fanene fram: de skal være oppdatert innen noen sekunder.

**Vaktlista offline** (G5: cachen i service workeren)
- [ ] Last `/vaktliste/`, slå av nettet og last siden på nytt. Lista skal vises fra
      kopien.

## 3. Et raskt blikk: sjekk at utseendet ikke har endret seg (5 min)

- [ ] **Pasientsiden:** klokka i toppen går (G3, felles klokke). Headeren ser ut som før,
      siden død CSS er slettet.
- [ ] **Pasientsiden, Innstillinger → arkivlista og arkivdetaljen:** tittel, notat og tall
      vises (escapingen er endret der).
- [ ] **Varselbjella:** en melding med apostrof vises riktig.
- [ ] **KO-tavla og vaktlistas faner** ser ut som før (mer død CSS er slettet).
- [ ] **Sentralbordet:** et ventende oppdrag på «Plassering» blir uthevet etter terskelen.

## 4. Railway og drift (5 min)

- [ ] **Byggnummeret i footeren** er det siste som ble pushet. Da gikk installasjonen av
      avhengighetene gjennom, hashene inkludert — feiler den, blir det ingen ny container.
- [ ] `/portal-admin/server-status/`, kortet **Konfigurasjon**: raden **«Migrasjoner»** står
      grønt med «alle kjørt» (27. sep.; `core.0013` er med). Rødt viser hvilke som mangler.
      *Det står også i Railway: tjenesten → Deployments → deployen → loggen, «Applying
      core.0013…» — men raden er enklere.*
- [ ] `/healthz/` svarer 200.
- [ ] Valgfritt: `railway ssh -- python manage.py kollaps_arkiv --dry-run`. Kommandoen er
      flyttet til en annen app, men har samme navn, så cron-jobben er uberørt.

---

## Selve pushen

Send `main` i **tre framspolinger**, slik `TODO.md` sier under «Veien til neste vakt», og se
over staging-funnene før hver. En push til `main` er alltid «alt fram til og med en commit»,
så ingenting trenger å stokkes om:

| Omgang | Kommando | Hva som går ut |
|---|---|---|
| 1 ✅ 27. sep. | `git push origin 0660da0:main` | Tekniske runder 6 og 7, vaktfabrikken og historikksøket |
| 2 ✅ 27. sep. | `git push origin 68fed55:main` | **Bare kolonneslettingen** (`backup_enabled`). Ta backup av prod rett før — det er den ene endringen som ikke kan angres uten tilbakerulling |
| 3 | `git push origin <siste commit på staging>:main` (i dag `729fe04`) | Resten: felles klokke, kommandoene til `core`, bil-kontoen, G6a og dokumentene |

Den er trygg fordi prod allerede kjører `4813cee`, og den koden bruker ikke kolonnen.

| Utfall | Hva det betyr |
|---|---|
| Ingen funn | Klart for `main` |
| Funn i §1 | Rettes før `main` |
| Funn i §2–§3 | Vurder: rett først, eller send og rett etterpå hvis det bare er kosmetisk |
