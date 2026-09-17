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
| Typene, som admin styrer | `models.Innspilltype`, `views.typer_view` |
| Hvem som varsles om et nytt innspill | `varsler.meld_nytt_innspill()` |
| Hvem som varsles om en kommentar | `varsler.meld_ny_kommentar()` — tråden, ikke alle |
| Når en sak ikke lenger kan slettes | `services.kan_slettes()` |
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

I grensesnittet heter handlingen **«Rediger»**, ikke «Rett» (André, 17. sep. 2026: «mye
tydeligere språk»). «Rett» leser som en korrigering av noe som er galt; det man som
regel gjør er å legge til det man glemte.

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
| les/skriv | `skriv_full` | Melder inn, og redigerer sitt eget innen fristen |
| les/skriv full | `skriv_leder` | Setter løst, gjenåpner, og styrer typene i «Backloginnstillinger» |

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

## Typen er en tabell — og var `choices` i én dag

Jeg valgte `choices` med den begrunnelsen at «er dette en feil eller et ønske» er et
strukturelt skille som ikke endrer seg med arrangementet. André snudde det samme dag: «Kan
ikke admin få legge til flere typer?»

Han har rett, og begrunnelsen min var for smal. Behovet som melder seg — «spørsmål»,
«teknisk gjeld», «dokumentasjon» — skal ikke vente på en utrulling, like lite som en
dronegruppe i vaktlista skal det. Mønsteret er `oppdrag/views_verdier.py`: **navn,
`er_aktiv`, `rekkefolge`, og sletting bare når ingen bruker raden.**

**`er_aktiv` er viktigere enn sletting.** En type som har vært i bruk kan ikke fjernes uten
å ta innspillene med seg (`PROTECT`), og da er «skjul den fra nedtrekket» det svaret man
faktisk vil ha. Derfor:

- filteret viser **alle** typene — en deaktivert type må kunne filtreres fram, innspillene
  som har den finnes fortsatt
- skjemaet viser **bare de aktive** — den skal ikke kunne velges på noe nytt
- serveren håndhever det siste i `_hent_aktiv_type()`, ikke bare klienten

**409-svaret bærer rådet, ikke bare avslaget.** «Kan ikke slettes» alene etterlater brukeren
uten en vei videre, og da er neste trekk å slette innspillene i stedet — altså å miste det
sperren fantes for å verne.

**Migrasjonen er delt i tre** (`0002`–`0004`), og det er ikke pynt: `0003` fyller FK-en med
data, og `0004` fjerner den gamle kolonnen. Står de i samme migrasjon, er det en skriving
etterfulgt av `ALTER TABLE` i én transaksjon — fella som tok ned deployen 30. aug. 2026. Å
dele migrasjonen i to er den tredje av de tre dokumenterte veiene ut.

## Varselet går til dem som kan løse, ikke til alle som kan lese

`varsler.meld_nytt_innspill()`. Mottakerne er kontoene med `skriv_leder` på `backlog`,
pluss global admin — som står utenfor modulaksen og har toppen av stigen uansett.

**En bjelle som pling-er for folk som ikke kan gjøre noe, er en bjelle man slår av** — og da
varsler den ikke den gangen det haster. **Innsenderen varsles ikke om sitt eget**, av samme
grunn.

Teksten bærer **tittelen**, ikke bare «nytt innspill»: det er tittelen som avgjør om man går
og ser nå eller i morgen. Og `notify()` dedupliserer på *meldingen* siste 24 timer, så to
ulike innspill gir to varsler mens et dobbelttrykk gir ett.

**Varselet er en sideeffekt, ikke en del av innmeldingen.** `meld_nytt_innspill()` kaster
aldri — et innspill skal ikke gå tapt fordi bjella feilet.

## Ingen feltnivå-audit, og begrunnelsen står her

Samme vurdering som vaktlistas registre (`Korps`, `Kompetanse`, `Ressursrolle`), som heller
ikke auditlogges: de er oppsett uten personopplysninger, og dette er utviklingsmetadata av
samme slag. Det ene som må kunne leses i ettertid — **hvem som satte noe løst** — står som
felter på raden (`lost_av_navn`, `lost_at`), der det også er synlig for den som leser lista.
En auditrad ville båret det samme ett sted til, og bare den ene av de to ville blitt lest.

Viser det seg feil, er det billig å rette: mønsteret ligger i `vaktliste/signals.py`, og
vakten `@ikke_under_loaddata` må da med fra første signal.


## Kommentarer: tre valg spørsmålet tvinger fram

**Tråden er åpen også på en løst sak.** Det er et bevisst avvik fra at et løst innspill
ikke kan redigeres. `kan_endres` nekter der fordi et løst innspill er et *spørsmål noen har
svart på*, og en omskriving gjør svaret uforståelig. Men «rettet i bygg `f3b279d`» **er**
svaret, og det skrives etter at flagget er satt — stengte vi tråden ved lukking, ble det
umulig å notere hvordan saken ble løst akkurat der noen ville lett etter det.

Av samme grunn har `kan_endre_kommentar` **to vilkår, ikke tre**: forfatteren og fristen,
uten `lost`. En kommentar er ikke spørsmålet; den er en setning i tråden, og en skrivefeil
rettet av forfatteren ti minutter senere velter ingenting. Grensen selv deles —
`_innen_fristen()` — fordi en grense skrevet to steder er to grenser som glir fra hverandre
ved neste justering.

**Sletting er strengere enn redigering, og kommentarene er grunnen.** Har noen *andre*
skrevet i tråden, er saken ikke lenger et utkast — den er en samtale, og `CASCADE` ville
tatt den andres setning med seg uten et ord. `services.kan_slettes()` er derfor sitt eget
svar, og det følger med hver rad i API-et: en sletteknapp som gir 409 er en knapp som fører
til en vegg. Egne kommentarer teller ikke — har man bare svart seg selv, er det fortsatt
ens eget.

**Varselet går til tråden, ikke til alle som kan løse.** Forfatteren og de som har
kommentert, minus den som skriver nå. Varsler man bredere, blir tråden til støy for folk som
ikke har spurt om noe; varsler man smalere — bare forfatteren — går et svar fra forfatteren
aldri tilbake til den som spurte. Lederen fikk sitt varsel da saken ble meldt inn; et varsel
per replikk i hver tråd ville vært en bjelle man slår av.
