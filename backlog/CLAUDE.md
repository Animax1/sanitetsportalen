# Backlog-modulen (backlog/)

> **Modulfil.** Den lastes når noen arbeider i `backlog/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Endringsønsker og bugs, ett innspill per rad, med et løst-flagg. Bestilt av André
17. sep. 2026: «Da blir modulen en backlog i systemet i stedet for innspill spredt i
chatter.» Modulen er utviklingsverktøy for **et knippe mennesker**, ikke en flate for alle
som går vakt — og det er derfor den er liten.

| Regel | Hvor |
|---|---|
| Angrefristen — én time, forfatterens egen | `services.kan_endres()` |
| Hva slags modul et innspill kan gjelde | `services.gyldig_modul_slug()` — utledet av registeret |
| De tre nivåene og hva de betyr her | `module.py` |
| Løst og gjenåpnet | `views.lost_view`, to navngitte stier |

## Modulen står utenfor vaktscopet, og det er et bevisst avvik

Alt annet i portalen er scopet til en `core.Vakt`, fordi dataene beskriver *det som skjedde
på en vakt*. **Et innspill beskriver portalen, ikke en vakt** — «nedtrekket lukker seg når
jeg velger» gjelder like mye i oktober som i august.

Konsekvensen er verdt å merke seg: `backlog`-fila i backup har **ingen plass i
gjenopprettingsrekkefølgen** og kan lastes når som helst. Hver annen modulfil forutsetter at
portalfila er lastet først, fordi den peker på vakta med et heltall.

## Angrefristen måles fra opprettelsen, ikke fra siste endring

André: «Forfatteren kan rette og slette sitt innlegg innen 1 time etter den kom.»

Fra endringstidspunktet ville hver retting forlenget fristen, og et innspill kunne holdes
redigerbart i det uendelige ved å røre det hver time — da er ikke fristen en frist.

**`kan_endres()` bærer tre vilkår, og de må sjekkes samlet:** kontoen er forfatteren (FK-en,
ikke det frosne navnet), fristen er ikke ute, og innspillet er ikke løst. Det siste sto
ikke i bestillingen; det følger av at løst er et flagg og ikke en sletting — en løst sak er
et svar noen har gitt, og lar man forfatteren skrive om spørsmålet etterpå, blir svaret
uforståelig. Regelen ligger som **én funksjon** av samme grunn som `kan_sette_vaktpost()`:
et endepunkt som husket to av tre vilkår ville sett ut som om det virket.

**Global admin er ikke unntatt.** Fristen verner ikke mot forfatteren, den verner *loggen* —
«blir som en logg» var hele bestillingen. Skal en rad bort etter fristen, er det en
avgjørelse noen tar i basen, ikke en knapp.

**Serveren regner ut `kan_endres` og sender det med hver rad.** Klienten skal ikke regne
fristen selv: en klokke som står feil ville gitt en knapp som fører til 403, eller skjult
en knapp brukeren har lov til å trykke på.

## Nivåene er Andrés tre, oversatt

| Hans | Portalens | Hva den får gjøre |
|---|---|---|
| les | `les` | Ser lista og filtrene |
| les/skriv | `skriv_full` | Melder inn, og retter sitt eget innen fristen |
| les/skriv full | `skriv_leder` | Setter løst og gjenåpner |

`skriv_handling` er **hoppet over med vilje**. Nivået er «navngitte overganger som ikke
leser request-kroppen», og å melde inn et innspill er nettopp å lese kroppen. Å bruke det
her ville vært å dele ut et nivå med feil betydning i hodet — den ene feilen `nivaa_navn`
finnes for å hindre.

## Filteret skal aldri skjule noe stille

Filterlinja står **synlig over lista**, aldri i en meny, og telleren under står i bildet
hele tiden — også når ingenting er filtrert bort, slik at den ikke blir et signal man lærer
seg å overse. Standardfilteret er «uløste», som er det man som regel vil se; at det *er* et
filter sier telleren.

**Et ugyldig filter gir 400, ikke hele lista.** `?lost=kanskje` ville ellers vist alt, og
den som filtrerte ville lest det som at det ikke finnes noen uløste. Et ukjent
filter*navn* ignoreres derimot — en lenke fra en gammel fane skal vise lista, ikke en
feilmelding.

## Typen er `choices`, ikke en tabell

I motsetning til `vaktliste.Ressursgruppe` og oppdragsmodulens verdimengder. Skillet er om
verdimengden er **organisasjonens** eller **portalens**: en vaktleder kan trenge en
dronegruppe i kveld og kan ikke vente på en utrulling, mens «er dette en feil eller et
ønske» er et strukturelt skille som ikke endrer seg med arrangementet.

Trengs en tredje verdi en dag, er det en migrasjon på én linje. Blir de mange og skiftende,
er `Verdimengde` i oppdragsmodulen mønsteret å flytte til.

## Ingen feltnivå-audit, og begrunnelsen står her

Samme vurdering som vaktlistas registre (`Korps`, `Kompetanse`, `Ressursrolle`), som heller
ikke auditlogges: de er oppsett uten personopplysninger, og dette er utviklingsmetadata av
samme slag. Det ene som må kunne leses i ettertid — **hvem som satte noe løst** — står som
felter på raden (`lost_av_navn`, `lost_at`), der det også er synlig for den som leser lista.
En auditrad ville båret det samme ett sted til, og bare den ene av de to ville blitt lest.

Viser det seg feil, er det billig å rette: mønsteret ligger i `vaktliste/signals.py`, og
vakten `@ikke_under_loaddata` må da med fra første signal.
