# Arkivert dokumentasjon

Historikk. Alt her beskriver arbeid som **er gjennomført**, planer som er utført og
erstattet av virkeligheten, eller forslag som er **forkastet til fordel for noe annet**.

**Ingenting her skal oppdateres.** Er en påstand i et av disse dokumentene i utakt med
koden, er det riktig — dokumentet beskriver kodebasen slik den var da leveransen ble gjort.
Aktiv dokumentasjon ligger ett nivå opp i [`docs/`](../); arbeidslista er
[`TODO.md`](../../TODO.md) i rotmappa.

Filene er beholdt fordi de forklarer *hvorfor* arkitekturen ble som den ble. Det er den
begrunnelsen som er verdifull, ikke statusen.

---

## Portalens faseleveranser (mai–august 2026)

Sanitetsportalen ble bygget som fem faser oppå den gamle Pasientregistreringsappen. Hvert
dokument er leveransenotatet for sin fase: hva som ble laget, hvilke valg som ble tatt og
hvorfor.

| Dokument | Fase | Hva den etterlot seg i koden |
|---|---|---|
| [`SANITETSPORTAL_PLAN.md`](./SANITETSPORTAL_PLAN.md) | Høynivå-skisse v0.1 (6. mai 2026) | Beslutningen om modulær monolitt, avhengighetsgrafen `accounts ← core ← moduler`, og fase-inndelingen under. Alle fem fasene er levert |
| [`SANITETSPORTAL_FASE_1.md`](./SANITETSPORTAL_FASE_1.md) | 1 — core-appen | `core/` med validatorer og `auth_decorators`. Shimen i `accounts/decorators.py` stammer herfra |
| [`SANITETSPORTAL_FASE_2.md`](./SANITETSPORTAL_FASE_2.md) | 2 — portal-skallet | `base_portal.html`, dashboard på `/`, pasientappen flyttet til `/pasienter/` med 301-redirects |
| [`SANITETSPORTAL_FASE_3A.md`](./SANITETSPORTAL_FASE_3A.md) | 3a — modul-registry | `core/modules.py`, `ModuleSettings`, de fem `kan_redigere_*`-flaggene, `AuditLog.app_label` |
| [`SANITETSPORTAL_FASE_3B.md`](./SANITETSPORTAL_FASE_3B.md) | 3b — admin-UI | `/portal-admin/moduler/`, `/portal-admin/auditlog/`, `/min-profil/` |
| [`SANITETSPORTAL_FASE_4.md`](./SANITETSPORTAL_FASE_4.md) | 4 — backup per modul | `core/backup/` med handler-registry, `ModuleBackupConfig`, `/portal-admin/backup/` |
| [`SANITETSPORTAL_FASE_5.md`](./SANITETSPORTAL_FASE_5.md) | 5 — brukerkobling og varsler | `Forstehjelper.user`/`Helsepersonell.user`, `core.Notification`, «Mine pasienter» |

## Avsluttede gjennomganger

| Dokument | Hva det er |
|---|---|
| [`FORBEDRINGER.md`](./FORBEDRINGER.md) | Forbedringsrunden fra mai 2026. Punktene som fortsatt sto åpne gikk videre til august-gjennomgangen, og derfra til [`../../TODO.md`](../../TODO.md) — som er den aktive arbeidslista |

## Utførte prosedyrer (arkivert 13. sep. 2026)

Engangsarbeid som er gjort. Beholdt fordi de forklarer hvordan, og hva som ble
kontrollert.

| Dokument | Hva det er | Hva det etterlot seg |
|---|---|---|
| [`DATAIMPORT_FRA_GAMMEL_PROD.md`](./DATAIMPORT_FRA_GAMMEL_PROD.md) | Planen for å få årets pasientdata fra den gamle Pasientregistreringsappen inn i portalen (14. aug. 2026) | Utført 22. aug. 2026: 273 pasienter, 12 førstehjelpere, 6 helsepersonell, alle kontroller grønne — se TODO under «Dataimport fra gammel prod». `import_offline_data` er kommandoen som ble brukt, og den finnes fortsatt |
| [`OPPSETT_KOLLAPS_CRON.md`](./OPPSETT_KOLLAPS_CRON.md) | Oppsettet av `kollaps_arkiv` som cron-jobb i Railway | Jobben står i `production` (`0 4 1 * *`) siden 22. aug. 2026, tørrkjørt 23. aug. Dokumentet ba selv om å bli slettet når jobben var oppe; det er arkivert i stedet, fordi sperrene det beskriver (backup etter arkivet, audit per kollaps) er verdt å ha et sted |

## Forslag som er erstattet (arkivert 17. sep. 2026)

Denne kategorien er ny, og den er annerledes enn de over: dokumentet beskriver ikke arbeid
som er gjort, men arbeid som **ikke skal gjøres**.

| Dokument | Hva det foreslo | Hva som erstattet det |
|---|---|---|
| [`FORSLAG_DATTEROPPDRAG.md`](./FORSLAG_DATTEROPPDRAG.md) | Ett oppdrag deles i datteroppdrag, ett per pasient, med `Oppdrag.forelder`. §2 forkastet uttrykkelig en egen hendelsestabell | [`../FORSLAG_KO.md`](../FORSLAG_KO.md). KO eier hendelsen, og da er premisset i §2 snudd: i KO finnes hendelsen *før* oppdraget, og ofte uten oppdrag. Begrunnelsen er tatt vare på i KO-notatets §9.3 |

**Dette er det ene dokumentet her som har fått et banner på toppen.** De andre beskriver
gjennomført arbeid, og en leser skjønner av innholdet at det er historie. Et forkastet
forslag gjør ikke det — det leser nøyaktig som et levende forslag, og den som finner det
ved å søke på «datteroppdrag» har ingen grunn til å gå hit for å lese indekslinja. Regelen
«ingenting her skal oppdateres» gjelder innholdet; banneret sier hva dokumentet *er*.

---

## To dokumenter ble slettet, ikke arkivert

`DEPLOY_FASE_3A.md` og `ENDRINGSLOGG_2026-05-15.md` lå her et øyeblikk, men er fjernet
22. aug. 2026. Den første beskrev hvordan man pakket en zip oppå en frisk clone — en
prosedyre som ikke etterlot seg noe i koden, og som er erstattet av vanlig git-arbeidsflyt.
Den andre var et endringsnotat for én dag fra før `CHANGELOG.md` fantes; innholdet står
i CHANGELOG under `2026-05-15 (sesjon 1)`, forkortet, men uten at noe av betydning mangler.

Begge er i git-historikken om noen skulle savne dem. Poenget med å arkivere er å ta vare
på *begrunnelser* — et dokument uten begrunnelse å ta vare på skal slettes, ikke få en
indekslinje som forklarer at det er tomt.

---

## Merknader om innholdet

Disse dokumentene ble skrevet før senere refaktoreringer. To ting går igjen:

- **`patients/views.py` finnes ikke lenger.** Fila ble delt i `views_common.py`,
  `views_patients.py`, `views_registre.py`, `views_stats.py` og `views_arkiv.py` (N13.3,
  13. aug. 2026). Linjehenvisninger til `views.py` gjelder koden slik den var før delingen.
- **`Behandler` heter `Forstehjelper`.** Modellen ble omdøpt 25. mai 2026.
