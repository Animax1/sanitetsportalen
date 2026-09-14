# Notat: DPIA-vurderingen, fritekstfeltet og adresse fra AMK

**Skrevet 14. september 2026.** Bakgrunn: André spurte om det kan legges adresse i
`Oppdrag.fritekst` når oppdraget kommer fra AMK, og påpekte samtidig at fritekst aldri
slettes fra historikken. Notatet holder svaret, og den personvernvurderingen som fulgte.

**Dette er ikke juridisk rådgivning.** Det er en gjennomgang av portalens egen
dokumentasjon og kode, med de tingene som må sjekkes mot primærkilde tydelig merket.
Ingenting her er besluttet — notatet finnes for at beslutningen skal tas med åpne øyne.

---

## 1. Premisset som må rettes: dokumentasjon fritar ikke for DPIA

André, 14. sep. 2026: *«Vi har ikke noe DPIA og slik jeg forsto det så var vi unnlat det
med at vi har vår personverndokumentasjon?»*

Det er to forskjellige plikter, og de oppfyller ikke hverandre:

| Plikt | Hjemmel | Hva den er hos oss |
|---|---|---|
| Protokoll, risikovurdering, informasjon til registrerte | art. 30, 32, 13 | `docs/PERSONVERN_DOKUMENTASJON.md` |
| **DPIA** | **art. 35** | En egen vurdering av risiko **for den registrerte**. Finnes ikke |

God dokumentasjon er *bevis* som støtter en vurdering av at DPIA ikke kreves. Den er ikke
et fritak. Var den det, kunne enhver behandling dokumentert seg ut av art. 35.

**Dokumentet vårt har rett; det er hukommelsen om begrunnelsen som har glidd.** A.12 sier
ikke «vi har dokumentasjon, altså slipper vi» — den bygger på tre helt andre ben.

## 2. Hva fritaket faktisk hviler på

Fra `docs/PERSONVERN_DOKUMENTASJON.md`, A.12, «DPIA (art. 35) – vurdert som ikke påkrevd»:

> Behandlingen omfatter særlige kategorier personopplysninger, men i begrenset omfang,
> **uten direkte identifikatorer**, uten profilering eller automatiserte avgjørelser, og
> uten systematisk overvåking av offentlig område. Vilkåret om behandling **«i stor
> skala»** anses ikke oppfylt.

Tre ben, og det tyngste er skalaen. Art. 35(3)(b) gjør DPIA obligatorisk ved behandling av
art. 9-data **i stor skala** — en sanitetsvakt er ikke det. **Det benet holder, og en
adresse endrer det ikke.**

### Dokumentet har skrevet sin egen utløser

Samme avsnitt slutter slik:

> Vurderingen tas opp igjen ved den årlige revisjonen og ved vesentlige endringer i
> behandlingens art, omfang eller formål — **særlig dersom nye moduler tar inn direkte
> identifikatorer.**

En adresse er nettopp det. Dokumentet har altså allerede forpliktet oss til å ta
vurderingen opp igjen i akkurat dette tilfellet. Det er godt skrevet — men det betyr at
spørsmålet ikke kan besvares med «vi har jo dokumentasjonen».

## 3. Terskelen står nærmere enn formuleringen gir inntrykk av

Art. 35(3) er **ikke** utløst. Men art. 35(1) — den generelle regelen om «høy risiko» — er
den som gjelder her. EDPBs ni kriterier (WP248) sier at to eller flere normalt peker mot
DPIA:

| Kriterium | Vurdering |
|---|---|
| Sensitive data / data av svært personlig karakter | **Oppfylt i dag** — `problemstilling` og `hastegrad` er klassifisert som art. 9 i A.6 |
| Sårbare registrerte | **Trolig oppfylt i dag** — skadde personer på et arrangement, som ikke velger å bli registrert og ikke kan protestere i situasjonen |
| Stor skala | Ikke oppfylt |
| Evaluering, scoring, automatiserte avgjørelser | Ikke oppfylt |
| Systematisk overvåking av offentlig område | Ikke oppfylt |
| Sammenstilling av datasett | Ikke oppfylt |

**To kriterier, allerede før adressen.** Det gjør ikke DPIA påbudt — den
behandlingsansvarlige kan dokumentere hvorfor risikoen likevel ikke er høy, og det er
nettopp det A.12 gjør. Men det er en nærmere avgjørelse enn ordlyden «vurdert som ikke
påkrevd» antyder, og den bør ikke leses som avsluttet.

### Må sjekkes mot primærkilde før noe bygges på det

- [ ] **Datatilsynets liste** over behandlinger som alltid krever DPIA — om sanitetstjeneste,
      akutthjelp eller helseopplysninger om sårbare grupper er nevnt der. Ikke gjettet på
      her med vilje.
- [ ] **WP248-kriteriene** i gjeldende form. Tabellen over er skrevet etter hukommelsen om
      dem og skal verifiseres før den siteres videre.

## 4. Det som faktisk mangler er mindre enn man skulle tro

Art. 35(7) krever fire ting. Tre av dem finnes allerede:

| Krav | Hvor vi står |
|---|---|
| (a) Systematisk beskrivelse av behandlingen og formålene | A.2, A.5, A.6 — dekket, grundig |
| (b) Nødvendighet og proporsjonalitet | A.4 + «Vurderte og fravalgte tiltak» — delvis dekket |
| (c) **Risiko for de registrertes rettigheter og friheter** | **Mangler** |
| (d) Planlagte tiltak for å møte risikoen | A.6, A.10, A.11 — dekket |

**Punkt (c) er den ekte luken, og den er verdt å se nøye på.**

A.12 er en **sikkerhetsrisikovurdering**, ikke en personvernkonsekvensvurdering. Den måler
«sannsynlighet for sikkerhetsbrudd» og «konsekvens ved sikkerhetsbrudd» — altså risiko sett
fra *systemets* side. En DPIA spør noe annet: **hva skjer med pasienten hvis dette går
galt?** Det spørsmålet stilles ikke noe sted i dokumentet.

Det er samme slags feil som `rullTilFeil()` rettet i vaktlista samme dag: meldingen ble
skrevet, men ikke der noen så den. Her er risikoen vurdert, men fra feil ståsted.

Konsekvens: en DPIA for dette systemet er ikke et digert løft. Det er i hovedsak å
omstrukturere det som finnes inn i art. 35(7)-formen, og skrive det ene kapittelet som
mangler. Kapittel (c) er nyttig i seg selv, uavhengig av om en DPIA noen gang blir påkrevd.

## 5. Det som veier tyngre enn DPIA-spørsmålet

Fra A.1:

> Behandlingsansvaret er per i dag lagt til André Eritsland **som privatperson**, ikke til
> organisasjonen som gjennomfører sanitetsvaktene.

Tre grunner til at dette bør avklares **før** adressen legges inn, ikke ved neste årlige
revisjon:

1. **Behandlingsansvar følger virkeligheten, ikke papiret.** Er det foreningen som i
   praksis bestemmer formål og midler — at det skal føres pasientregistrering på vakt, hvem
   som får konto, hva som registreres — så *er* de behandlingsansvarlig, uansett hva
   dokumentet sier. Da beskriver dokumentet noe annet enn det som skjer.
2. **Art. 9(2)(h) forutsetter behandling «under ansvar av» en fagperson med taushetsplikt.**
   Det er en anstrengt konstruksjon når ansvarssubjektet er en privatperson.
3. **Personlig eksponering.** Innsynskrav, avviksmelding til Datatilsynet og det rettslige
   ansvaret ligger på behandlingsansvarlig personlig.

Dokumentet flagger det selv som noe som «bør revurderes ved den årlige revisjonen» (C.4).
Vurderingen her er at det bør opp tidligere, fordi det påvirker alle de andre svarene.

---

## 6. Den konkrete bakgrunnen: hvor fritekst faktisk lever

`Oppdrag.fritekst` er en `TextField` uten validering (`oppdrag/models.py`). Det er portalens
eneste frie felt, og A.12 sier allerede at en operatør *kan* skrive direkte identifikatorer
der. Kartlagt 14. sep. 2026:

| Hvor | Ser fritekst? | Forsvinner når? |
|---|---|---|
| Bilen, aktivt oppdrag | Ja | — |
| Bilen, etter `Ledig` | **Nei** — utelates server-side i `views_common.oppdrag_til_dict` | Straks |
| Bilen, 30 min etter `Ledig` | Hele oppdraget borte (`services.SKJUL_ETTER_LEDIG`) | 30 min |
| KO, tavla | Ja | — |
| **KO, historikken** | **Ja** | **Aldri** |
| Vaktarkivet | Nei — arkiveres bevisst ikke (`ArkivertOppdrag`) | — |
| Auditloggen | Nei — står som `(skjult)` (`signals.FELT_UTEN_VERDILOGGING`) | — |
| **Backup, modulfila `oppdrag`** | **Ja** | 730 dager hos Scaleway |
| **Backup, den hele fila** | **Ja** | 90 dager hos Scaleway |

**Beskyttelsen er bygget helt og holdent mot bilen.** «En bil som blir stående ulåst» er
scenarioet hele `synlige_for_enhet()` finnes for. Mot KO finnes det ingen frist i det hele
tatt. Det eneste som faktisk fjerner teksten i dag er **arkivering av vakta**, som sletter
oppdragsradene — og det avhenger av at et menneske husker å trykke.

A.12 sier det selv, i en setning som dermed er en åpen gjeldspost:

> Restrisiko: selve feltverdien står i oppdragstabellen til oppdraget slettes eller
> arkiveres.

### To ting som ikke må forveksles

- **En slettefrist på den levende raden fjerner ikke teksten fra backupene.** `fritekst` er
  med i `oppdrag`-modulfila og i den hele fila — 730 og 90 dager. En frist gir ekte
  beskyttelse mot «noen leser historikken tre måneder senere»; den er **ikke** en
  sletterett. Det skal stå skrevet, ikke oppdages senere.
- **Sletting må være tømming av feltet, ikke av raden.** Oppdraget trengs til statistikken
  og arkivet. `fritekst = ''` er hele operasjonen.

---

## 7. Adresse: hvor den bør ligge, og hvor den ikke må ligge

### Fella: ikke i lokasjonsnedtrekket

Den «trygge» veien ser ut til å være nedtrekket — `Lokasjon` er en tabell, og `skriv_leder`
kan opprette rader i den. Altså kunne noen lage lokasjonen «Storgata 5».

**Det er den klart verste plasseringen.** `Lokasjon.navn` fryses som
`ArkivertOppdrag.lokasjon_navn`, og det feltet inngår i **SHA-signaturen** til arkivet.
Adressen kan da ikke fjernes uten at arkivet melder tukling — den er låst i 24 måneder ved
konstruksjon. Fritekst er langt mindre farlig, nettopp fordi fritekst bevisst ikke
arkiveres.

### Anbefaling: eget felt, ikke fritekst

| Med eget `adresse`-felt | Med adresse i fritekst |
|---|---|
| Kan få sin egen slettefrist, uavhengig av notatet | Én frist må dekke to ulike behov |
| Kan dokumenteres som egen rad i A.6 med egen hjemmel | Skjuler seg i «fritekst kan inneholde hva som helst» |
| Bilen kan få den som navigasjonsinfo, ikke som et notat | Blandes inn i løpende tekst |
| Fristen kan være **kort** — adressen trengs til bilen er fremme | Notatet kan trenge lengre levetid |
| Ett formål per felt | Navn, telefon og adresse havner i samme blob |

Prisen er en migrasjon, et felt i skjemaet og en ny rad i A.6. Det er billig.

**Merk hva adressen gjør med argumentet i A.6.** Hele GDPR-resonnementet der hviler på
denne setningen:

> der pasienten har et løpenummer, har oppdraget ingenting. Re-identifisering krever
> kunnskap utenfra.

En adresse *er* den kunnskapen utenfra, lagt inn i raden. Kombinert med `hastegrad` og
`problemstilling` blir raden en opplysning om en identifiserbar person. Det er ikke
ulovlig, men det er en annen vurdering enn den som står skrevet, og den må skrives om.

---

## 8. Slettefristen: hvordan den bør bygges

Uavhengig av adressen. Fristen lukker en restrisiko som står åpen i A.12 i dag.

**Vis-regelen og slette-regelen er to ting, og begge trengs** — samme grep som
`_synlig_for_bilen` i `oppdrag/views.py`:

1. **Serveren utelater fritekst fra svaret** straks fristen er passert. Da lyver aldri
   nedtellingen, selv om feiingen er sen.
2. **En feiing tømmer feltet for alvor.** Naturlig sted er `purge_old_logs` — den kjører
   allerede på Railway Cron, rører bare databasen, og trenger ikke volumet. Ingen ny
   infrastruktur. (Backup er ikke en cron-jobb, av grunner som står i `CLAUDE.md`; denne
   jobben har ikke det problemet.)

**Klokka går fra `historikk_fra`**, som er Andrés ordlyd. Én konsekvens å ta bevisst:
`services.hent_tilbake` nullstiller `historikk_fra`, så henter KO oppdraget tilbake til
tavla, starter nedtellingen på nytt. Vurderingen her er at det er riktig — men det er et
valg, ikke noe som skal arves fra implementasjonen.

**Fristen bør være en `AppSetting`, ikke et tall i koden.** Samme begrunnelse som
`Belastningsgrenser` i vaktlista: grensene er organisasjonens, ikke portalens. Global admin,
ved siden av lyd-bryterne.

**Nedtellingen** sendes som et felt i payloaden og rendres i historikkraden
(`renderHistorikk()` i `static/js/oppdrag-sentral-admin.js`). Ett forbehold: vis den **bare
når det faktisk står tekst der** — en nedtelling på et tomt felt er støy, og det er slik
støy som gjør at folk slutter å lese varsler.

### Ett spørsmål som ikke er avgjort

- [ ] **Oppdrag som aldri når historikken.** Et oppdrag med `trenger_ressurs` står i
      `Venter` på ubestemt tid og beholder fritekst for alltid. Skal klokka i stedet gå fra
      **siste `Ledig`-stempling**, som bilens 30-minutters-regel gjør? Det dekker flere
      tilfeller, men bryter med ordlyden «i historikken». Hullet bør lukkes bevisst.

---

## 9. Anbefalt rekkefølge

1. **Avklar behandlingsansvaret** (§5). Billigst, størst effekt, og påvirker alle de andre
   svarene.
2. **Bygg slettefristen på fritekst** (§8). Står som åpen restrisiko i A.12 allerede i dag,
   uavhengig av adressen — og den er det som gjør adressen forsvarlig senere.
3. **Deretter adressen** (§7), med DPIA-vurderingen tatt opp igjen og **skrevet ned enten
   svaret blir ja eller nei**. Art. 5(2) krever at vurderingen dokumenteres, ikke at den
   lander på et bestemt svar.
4. **Skriv kapittel (c)** — risiko sett fra pasientens side (§4). Nyttig i seg selv, og blir
   en DPIA senere nødvendig, er den da halvveis skrevet.

Punkt 1 og 3 er av den typen der en halvtime med noen som faktisk kan feltet er verdt mer
enn en grundig lesning av dokumentene.
