# KO-modulen (ko/)

> **Modulfil.** Den lastes når noen arbeider i `ko/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Pulje 1 levert (skallet: modulen registrert, `/ko/` med de fire flatene, sidebaren).
Pulje 2–7 gjenstår — se `docs/FORSLAG_KO.md` §10, som er et **forslag**, ikke besluttet.

**`/oppdrag/` er enhetsverktøyet, `/ko/` er situasjonsverktøyet.** Én bil, én
statusmaskin, én stempling om gangen — mot hva skjer på arrangementet, hvem er hvor, hva
vet vi. Forskjellen er tidsaksen: et oppdrag begynner når bilen får det; **en hendelse
begynner når noen sier noe over samband**, kan leve i tjue minutter før en ressurs sendes,
og kan bli avsluttet uten at noen rykket ut.

| Regel | Hvor |
|---|---|
| Hvem har KO oppe (sidebaren) | `ko/tilstede.py` |
| Sesjonsloopen den bygger på | `core/sesjoner.py` — delt med adminflaten |
| Modulens nivåer | `ko/module.py` — **bare `les` i pulje 1** |
| Siden og de to endepunktene | `ko/views.py`, `ko/urls.py` |
| Sidebaren i nettleseren | `static/js/ko.js` |

## Retningen: KO er øverste lag

`ko` → `vaktliste` og `ko` → `oppdrag`. **Ingen av dem kjenner `ko`**, og det håndheves
med AST i `ko/tests_avhengighet.py` — samme grep som `OppdragImportererIkkeVaktlista`.
Testen bor her fordi det er KOs kant å forsvare: skriver noen `from ko.models import …` i
`oppdrag/`, er det KO som har fått en ny og usynlig forelder.

Den ene kanten som skal gå andre veien når den kommer, er `Oppdrag.hendelse` — en nullbar
FK fra oppdrag til hendelsen (pulje 3/5). Den peker fra oppdrag til hendelse og aldri
motsatt, og må da **navngis og begrunnes** i unntakslista, ikke bare skrives.

`core` skal fortsatt kunne kjøre uten `ko`: `core/tests_avhengighetsretning.py` har `ko` i
`MODULAPPER`, og den ene tillatte importen er `core/modules.py` → `ko.module`, som er
registeret som navngir modulene sine.

## Modulen eier ingen ressurser, og skal aldri gjøre det

Ressursbildet er en **projeksjon** (§3.1): vaktlista sier hvem som finnes og hvem som er
på vakt, oppdragsmodulen sier status for dem som stempler selv, og KO fører status for dem
som ikke gjør det. Et eget ressursregister her ble forkastet i §9.1, og begrunnelsen er
verdt å huske fordi den ikke handler om opprettelse: feilen oppstår ved **endring**. Noen
retter kallesignalet ett sted, og tavla og enhetsskjermen viser ulike navn på samme bil
midt i en vakt.

Det gjelder også `oppdrag.Enhetstype` mot `vaktliste.Ressursgruppe`, som er den samme
taksonomien vedlikeholdt to steder (§2.1). Den skal **ikke** slås sammen i dette arbeidet —
den krymper av seg selv når sentralbordet flytter — men den er kjent, og skal ikke oppdages
på nytt som om den var ny.

## Sidebaren svarer på «hvem har KO oppe», ikke «hvem dekker samband»

`ko/tilstede.py`. Tre valg som hver for seg er en mulig feil:

- **Filteret er `har_tilgang`-semantikk, ikke en rå `ModulTilgang`-spørring.** Notatets
  §5.3 sier «`_list_active_sessions` filtrert på `ModulTilgang('ko')`», og det filteret
  ville utelatt global admin — som ingen rader har, og full tilgang. Altså nettopp den som
  sitter i KO og administrerer portalen.
- **Én rad per person, ikke per sesjon.** Adminlista på server-status lister *sesjoner*,
  fordi den skal kunne avslutte én av dem. Denne svarer på hvem som er der, og samme
  operatør med KO på PC-en og på telefonen er én person. `inaktiv_s` blir den ferskeste av
  fanene.
- **Ingen `session_key` ut.** Det er adminflatens håndtak for å avslutte en sesjon. En
  KO-operatør har ingenting med det å gjøre, og et felt hvis eneste bruk er destruktiv
  skal ikke ligge og vente på at noen finner ut hva det er.

**Pålogget er ikke til stede** — se rota. Derfor er `inaktiv_s` med som kolonne, og derfor
er `null` («vet ikke») noe annet enn `0`. `koInaktivTekst()` i `static/js/ko.js` tar det
samme valget på klientsida, og er en egen funksjon fordi den *avgjør* hva lista påstår om
en person.

## Nivåene legges til når de betyr noe

`Module.nivaaer` er `('les',)` i pulje 1. Skallet har ingen skriveendepunkter, og et nivå
som ikke gir noe er lett å dele ut i god tro — det er feilen den globale nivålista gjorde
mot `statistikk`, dokumentert i `core/modules.py`.

Her er den verre enn der. `statistikk` har aldri fått skriving, så et utdelt `skriv_full`
ble bare liggende dødt. Et `skriv_full` delt ut på `ko` i dag ville ligget i basen og
**trådt stille i kraft** den dagen pulje 2 landet, uten at noen tok den avgjørelsen da.
Hver pulje legger derfor til sitt eget nivå i samme commit som nivået får mening — og et
nytt trinn er additivt, så matrisen tilbyr bare det modulen faktisk deklarerer.

## Det som ikke er bygget, og hvorfor det ikke skal gjettes på

Loggen (pulje 2) og `Hendelse` (pulje 3) har **åpne valg som skal besvares før koden**,
ikke under — de står i `TODO.md`. Ett av dem er ikke en detalj: `NOTAT_DPIA_OG_FRITEKST.md`
§7 slår fast at fritekst bevisst *ikke* arkiveres, mens et felt som inngår i arkivets
SHA-signatur er låst i 24 måneder ved konstruksjon. KO-loggen er i all hovedsak fritekst,
og sletteinngangen i §4.4 har nøyaktig den samme konflikten. Bygges loggen først og
oppbevaringen avgjøres etterpå, er svaret allerede gitt av konstruksjonen.
