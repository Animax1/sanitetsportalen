# Databehandleravtale – Sanitetsportalen og kart.sanitet.net

**Utkast** · 12. oktober 2026, oppdatert 15. oktober · André Eritsland

> **Hvor utkastet bor:** det skrives og kommenteres i Claude Docs
> (<https://claude.ai/code/artifact/3edfaced-340f-4057-9ae2-cf311f3f57d8>), og denne fila er
> kopien som følger koden. Endres det ene, oppdateres det andre i samme økt. Når avtalen er
> signert, er **den signerte versjonen** fasit: den føres inn i
> `docs/PERSONVERN_DOKUMENTASJON.md` A.1 og A.2, og «utkast» går ut av filnavnet.

## Om utkastet

Dette er et utkast til databehandleravtale etter personvernforordningen (GDPR) art. 28, mellom
Kverneland Røde Kors som behandlingsansvarlig og André Eritsland som databehandler. Den dekker
**begge appene**: Sanitetsportalen og kart.sanitet.net.

Innholdet bygger på behandlingsprotokollen (`docs/PERSONVERN_DOKUMENTASJON.md`, v1.21) og på det
koden faktisk gjør per 12. oktober 2026. Kartets del er fylt inn fra kartets egen kode og
personvernside 15. oktober 2026. Det som gjenstår, står som åpne punkter til slutt.

Utkastet er ikke juridisk kvalitetssikret. Les det sammen med korpset, og vurder å la noen med
personvernkompetanse i Røde Kors-systemet se over før signering.

## 1. Partene og bakgrunn

| Rolle | Part | Kontakt |
| --- | --- | --- |
| Behandlingsansvarlig | Kverneland Røde Kors, org.nr. [fylles inn] | [navn og rolle i korpset] |
| Databehandler | André Eritsland, privatperson | andre.eritsland@gmail.com |

André Eritsland eier, drifter og utvikler Sanitetsportalen og kart.sanitet.net. Korpset bruker
appene i sin sanitetsberedskap og bestemmer formålet med opplysningene og hvilke opplysninger som
registreres. Korpset er derfor behandlingsansvarlig, og André behandler opplysningene på korpsets
vegne.

Henvendelser fra de registrerte går til **personvern@sanitet.net**, som databehandler leser og
videreformidler til korpset etter punkt 4. Drift og feilvarsler går til **admin@sanitet.net**,
og brukerstøtte til **support@sanitet.net**. Alle tre er egne innbokser hos Proton (punkt 6).

## 2. Formål, art og varighet

Databehandler drifter, vedlikeholder og videreutvikler to apper for korpsets sanitetsberedskap
ved arrangementer, og behandler personopplysninger bare for å levere dem.

| App | Hva den brukes til |
| --- | --- |
| Sanitetsportalen | Pasienttavle under vakt, oppdrag for biler og lag, vaktlister og mannskapsregister, koordinering (KO-logg), lagregistrering, statistikk og arkiv etter vakt |
| kart.sanitet.net | Kart over egne ressurser under vakt: bilenes og lagenes siste posisjon og plassering, mottatt fra portalen, og vist for medlemmer av korpsets kartgrupper |

**Behandlingen består av:** lagring, sikkerhetskopiering, gjenoppretting, feilsøking, utsending
av e-post fra portalen (invitasjoner, glemt passord, vaktlista som fil, driftsvarsler), og
sletting etter fristene i punkt 7.

**Varighet:** så lenge korpset bruker appene. Ved opphør gjelder punkt 7.

## 3. Registrerte og opplysninger

| Registrerte | Opplysninger | App |
| --- | --- | --- |
| Pasienter | Løpenummer (ikke navn eller fødselsnummer), problemstilling og årsak fra fast liste, triage, transport, behandler, medisiner ja/nei, tidspunkter, journal ja/nei. **Helseopplysninger (art. 9)** | Portalen |
| Personer i utrykningsoppdrag og KO-logg | Hendelsestype, hastegrad, sted, tider; KO-loggens fritekst kan inneholde indirekte identifiserende helseopplysninger | Portalen |
| Brukere med konto | Brukernavn, e-post, kontotype og tilganger, innloggings- og endringslogg med IP-adresse og nettleser, varsler, tofaktor-hemmelighet | Portalen |
| Mannskap (vaktlista) | Navn, korps, kompetanser, telefon, ISSI, vakter og tider, overnattingsrom, notat | Portalen |
| Lag | Lagregistreringer uten identifikator; lagets posisjon når laget selv deler den | Portalen og kartet |
| Mannskap i biler | Bilens posisjon ved stempling og på «Send posisjon», og om deling er slått av | Portalen og kartet |
| Kartets brukere | Navn, e-post, rolle, grupper, passord (hashet) og tofaktor-nøkkel; kartobjektene de lager (veipunkter, ruter, teiger, notater) med hvem som laget og endret dem, og en endringslogg; innloggingslogg (e-post, IP-adresse, nettleser, tid) og feilede innloggingsforsøk (e-post, IP-adresse) | Kartet |

Detaljene, med feltnavn og hjemmel, står i behandlingsprotokollen del A.6. Endres protokollen,
endres dette vedlegget med den.

## 4. Databehandlers plikter

1. **Bare etter instruks.** Databehandler behandler opplysningene bare etter korpsets
   dokumenterte instruks — denne avtalen og behandlingsprotokollen — og ikke til egne formål.
   Mener databehandler at en instruks strider mot personvernreglene, sier han fra straks.
2. **Taushetsplikt.** Databehandler har taushetsplikt om opplysningene, også etter at avtalen er
   slutt, og signerer korpsets taushetserklæring.
3. **Tilgang i appene.** Databehandler gir og fjerner tilgang etter korpsets beslutning. Korpset
   bestemmer hvem som får konto og hvilket nivå.
4. **De registrertes rettigheter.** Henvendelser til personvern@sanitet.net videresendes korpset
   innen [5] virkedager. Databehandler hjelper med innsyn, retting, sletting og utlevering, så
   korpset kan svare innen én måned.
5. **Bistand ellers.** Databehandler bistår med vurderinger av personvernkonsekvenser og
   forhåndsdrøfting med Datatilsynet når det trengs.
6. **Endringer i behandlingen.** Nye typer opplysninger eller nye formål avtales med korpset før
   de tas i bruk, og føres i protokollen. Det gjelder også historikk over posisjoner og løpende
   posisjonsdeling, som i dag ikke finnes.

## 5. Sikkerhet (art. 32)

Databehandler holder minst dette nivået, og varsler korpset før noe av det svekkes:

| Område | Tiltak i dag |
| --- | --- |
| Tilgang | Innlogging med passord og tofaktor; tilgang per modul og nivå; kontosperre etter gjentatte feilede forsøk; sesjonen utløper etter 8 timer uten bruk (innstilling) |
| Overføring | HTTPS overalt. Kartet tar bare imot meldinger signert med HMAC fra portalen |
| Lagring | Passord hashet, aldri i klartekst. Data i EU (Railway, Nederland) |
| Sikkerhetskopier | Kryptert med AES-256-GCM før de forlater portalen, med en nøkkel leverandøren ikke har. Leverandørnøkkelen kan ikke slette kopier |
| Sporbarhet | Endringer og innlogginger logges med bruker, tid og IP-adresse i 730 dager |
| Utvikling | Automatiske tester og sårbarhetssjekk av avhengighetene før hver utrulling; egne miljøer for test og drift |

Fullstendig liste står i protokollen A.10.

## 6. Underdatabehandlere

Korpset godkjenner ved signering at databehandler bruker leverandørene under. En ny eller byttet
leverandør varsles korpset minst [30] dager før, og korpset kan protestere. Databehandler sørger
for at hver av dem er bundet av en avtale etter art. 28 med minst samme vern.

| Leverandør | Hva | Hvor | App |
| --- | --- | --- | --- |
| Railway Corp. | Drift av appene og databasene | EU, Nederland (europe-west4) for portalen; Railways EU-region for kartet | Begge |
| Scaleway SAS | Krypterte sikkerhetskopier | EU, Nederland (nl-ams) | Portalen |
| AhaSend | E-post fra portalen (`noreply@mail.sanitet.net`) | EØS | Portalen |
| Proton AG | E-post til `@sanitet.net`: personvern@, admin@, support@ og en catch-all | Sveits (adekvansbeslutning, art. 45) | Begge |

Overføring utenfor EU/EØS skjer bare med et gyldig grunnlag etter GDPR kapittel V, for eksempel
EU–US Data Privacy Framework eller standard personvernbestemmelser. Den eneste i dag er e-posten
hos Proton i Sveits, som har adekvansbeslutning fra EU-kommisjonen.

**Kartleverandørene og datakildene er ikke underdatabehandlere.** Kartverket, MapTiler (Sveits)
og EOX (Østerrike) leverer kartbildene direkte til brukerens nettleser. De ser IP-adressen og
hvilket område som vises, men ikke hvem brukeren er, og de behandler ikke opplysninger på
korpsets vegne — de leverer en tjeneste til den som ber om den. MET, NVE og Kartverkets
stedssøk hentes av kartets server, så de ser bare serveren. Alle er navngitt på kartets
personvernside.

**Cloudflare er ikke underdatabehandler.** Den er bare DNS-leverandør for `sanitet.net`, med alle
oppføringer som «DNS only»: trafikken går rett til Railway, og Cloudflare ser den ikke. Skal
proxyen slås på, er det en ny underdatabehandler etter avsnittet over.

## 7. Avvik, revisjon og sletting

**Avvik.** Databehandler varsler korpset uten ugrunnet opphold, og senest innen [24] timer etter
at et brudd på personopplysningssikkerheten er oppdaget: hva skjedde, hvilke opplysninger og hvor
mange, hva er gjort. Korpset melder til Datatilsynet innen 72 timer der det kreves. Rutinen står
i protokollen A.15 og C.5.

**Revisjon.** Databehandler gir korpset den informasjonen som trengs for å kontrollere at avtalen
følges, og går gjennom den årlige sjekklisten (protokollen C.4) sammen med korpset.

**Lagringstid.** Fristene i protokollen A.9 gjelder. De viktigste:

| Opplysninger | Frist |
| --- | --- |
| Arkiverte pasient- og oppdragsrader | 24 måneder, deretter bare anonym statistikk |
| Innloggings- og endringslogg, KO-logg, lagregistreringer | 730 dager |
| Sikkerhetskopier hos Scaleway | 730 dager (modulfiler), 90 dager (hele databasen) |
| Overnatting | 30 dager etter natta |
| Posisjoner i kartet | Siste posisjon slettes 24 timer etter siste melding; delt posisjon når visningstiden er ute |
| Kartet: innloggingslogg, feilede innloggingsforsøk, papirkurv | 30 dager, 15 minutter, 30 dager. Kontoer som ikke er brukt på 12 måneder gås gjennom og deaktiveres eller slettes |
| E-post i innboksene hos Proton | Vaktlista som fil 30 dager og feilvarsler 90 dager (slettes av Proton); henvendelser til personvern@ når saken er avsluttet |

**Ved opphør.** Når avtalen slutter, skal databehandler etter korpsets valg levere opplysningene
tilbake i et lesbart format (JSON eller CSV) eller slette dem, i begge appene, innen [60] dager.
Sikkerhetskopier slettes når fristene over løper ut. Databehandler bekrefter slettingen
skriftlig.

## 8. Varighet, endringer og signatur

Avtalen gjelder fra signering og så lenge databehandler behandler opplysninger for korpset.
Begge parter kan si den opp med [3] måneders varsel; punkt 7 gjelder ved opphør. Endringer
avtales skriftlig. Norsk rett gjelder.

| | Behandlingsansvarlig | Databehandler |
| --- | --- | --- |
| Navn | | André Eritsland |
| Rolle | [rolle i Kverneland Røde Kors] | Eier og drifter av appene |
| Sted og dato | | |
| Signatur | | |

## Åpne punkter før signering

- [ ] **AhaSend og Proton:** før inn referansen til databehandleravtalen for hver av kontoene.
- [ ] **Tallene i klammer:** varslingstid ved avvik (24 t), videresending av henvendelser
      (5 dager), varsel om ny leverandør (30 dager), sletting ved opphør (60 dager),
      oppsigelse (3 måneder).
- [ ] **Sikkerhetskopier ved opphør:** modulfilene ligger 730 dager hos Scaleway og kan ikke
      slettes med portalens nøkkel. Avklar om korpset godtar det, eller om de skal slettes
      manuelt ved opphør.
- [ ] **Hvis du blir borte:** avtalen bør si hvem som får tilgang til drift og
      sikkerhetskopier hvis du ikke kan drifte appene, så korpset ikke står uten opplysningene
      midt i en sesong.
- [ ] **Korpsets org.nr. og signatar.**
- [ ] **Når signert:** føres inn i protokollen A.1 og A.2, og punktet i TODO slettes.
