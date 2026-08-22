# Arkivert dokumentasjon

Historikk. Alt her beskriver arbeid som **er gjennomført**, eller planer som er utført og
erstattet av virkeligheten.

**Ingenting her skal oppdateres.** Er en påstand i et av disse dokumentene i utakt med
koden, er det riktig — dokumentet beskriver kodebasen slik den var da leveransen ble gjort.
Aktiv dokumentasjon ligger ett nivå opp; se [`../README.md`](../README.md).

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
| [`FORBEDRINGER.md`](./FORBEDRINGER.md) | Forbedringsrunden fra mai 2026. Punktene som fortsatt sto åpne er flyttet til [`../FORBEDRINGER_2026-08.md`](../FORBEDRINGER_2026-08.md) del 3 — den fila er den aktive backloggen |

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
