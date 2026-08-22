# Dokumentasjon – Sanitetsportalen

Oversikt over hva som ligger her, og hva hvert dokument er til for.

> **Planlegging hører hjemme i [`../TODO.md`](../TODO.md).** Det er den ene lista over hva
> som skal gjøres videre. Dokumentene under er *underlag* — de forklarer bakgrunn,
> vurderinger og framgangsmåte, men de er ikke arbeidslista. Når et punkt her er ferdig,
> krysses det av i TODO, og [`../CHANGELOG.md`](../CHANGELOG.md) beskriver hva som faktisk
> ble gjort.

---

## Levende dokumenter

Disse skal holdes oppdatert. Er noe her i utakt med koden, er dokumentet feil.

| Dokument | Hva det er | Når du leser det |
|---|---|---|
| [`TEKNISK_DOKUMENTASJON.md`](./TEKNISK_DOKUMENTASJON.md) | Full teknisk referanse: stack, modeller, endepunkter, middleware, drift | Ved overtakelse, eller når du trenger detaljer `CLAUDE.md` ikke har |
| [`PERSONVERN_DOKUMENTASJON.md`](./PERSONVERN_DOKUMENTASJON.md) | Behandlingsprotokoll (GDPR art. 30) + personvernvurderinger. Formelt dokument overfor tilsynsmyndighet | Ved endringer som berører persondata — nye felt, nye lagringstider, ny modul |
| [`RUNBOOK_VAKT.md`](./RUNBOOK_VAKT.md) | Handlingsregler under vakt: driftsmodus, terskler, tiltak ved belastning. Inneholder også skaleringstallene (§3c) | Før og under vakt |
| [`DEPLOY_GUIDE.md`](./DEPLOY_GUIDE.md) | Railway-oppsett fra bunnen: prosjekt, Postgres, volum, miljøvariabler | Ved nytt miljø eller ny deploy-target |

## Aktive planer og beslutninger

Disse er arbeidsdokumenter med et sluttpunkt. De arkiveres eller slettes når jobben er
gjort — TODO peker på dem så lenge de er i bruk.

| Dokument | Status | Hva som gjenstår |
|---|---|---|
| [`FORBEDRINGER_2026-08.md`](./FORBEDRINGER_2026-08.md) | Aktiv backlog | S3, F3, F4, F6, F9 + `style-src`-delen av F5. Nye forbedringsforslag skal legges til her |
| [`GDPR_TILTAKSPLAN.md`](./GDPR_TILTAKSPLAN.md) | Under arbeid | Organisasjonsnavn i A.4, cron for `kollaps_arkiv`, DPIA-vurdering. Slettes når alt er lukket — de varige beslutningene lever i personverndokumentasjonen |
| [`BESLUTNING_BRUKERE_OG_EPOST.md`](./BESLUTNING_BRUKERE_OG_EPOST.md) | Besluttet, ikke bygget | Invitasjonsflyt og passord-reset. Blokkert av at SMTP ikke er verifisert |
| [`DATAIMPORT_FRA_GAMMEL_PROD.md`](./DATAIMPORT_FRA_GAMMEL_PROD.md) | Klar til utførelse | Framgangsmåte for å hente årets pasientdata fra den gamle Pasientregistreringsappen. Ingen ny kode trengs |
| [`OPPSETT_KOLLAPS_CRON.md`](./OPPSETT_KOLLAPS_CRON.md) | Andres | Framgangsmåte for en oppgave bare Andre kan utføre. **Han sletter den selv** når cron-jobben står — ikke rydd den bort |

## Arkiv

[`archived/`](./archived/) er historikk: faseleveranser som er levert, og planer som er
utført. De beskriver hvorfor arkitekturen ble som den ble, og er verdt å slå opp i når et
designvalg virker rart. **Ingenting der skal oppdateres.** Se
[`archived/README.md`](./archived/README.md) for hva som ligger hvor.

---

## Hvor ting hører hjemme

| Skal du skrive… | Legg det i |
|---|---|
| …hva som skal gjøres videre | `../TODO.md` |
| …hva som ble gjort | `../CHANGELOG.md` |
| …hvordan koden henger sammen, kort | `../CLAUDE.md` |
| …hvordan koden henger sammen, i detalj | `TEKNISK_DOKUMENTASJON.md` |
| …et nytt forbedringsforslag | `FORBEDRINGER_2026-08.md` |
| …noe som berører persondata | `PERSONVERN_DOKUMENTASJON.md` |
| …et større valg som skal tas i ro før det bygges | nytt `BESLUTNING_*.md` her, med lenke fra TODO |
