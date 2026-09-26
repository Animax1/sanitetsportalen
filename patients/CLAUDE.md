# API-mønster (patients/views_*.py)

> **Modulfil.** Den lastes når noen arbeider i `patients/`. Rammeverket — tilgangsmodellen,
> backup, arkiv, audit, migrasjoner og frontend-reglene — står i `CLAUDE.md` i rota, og
> gjelder her også. Regelen for hva som står hvor: ligger koden i en app, står regelen
> her; gjelder den alle, står den i rota.

Viewene er delt i fem moduler (N13.3) — `views.py` finnes ikke lenger:

| Modul | Ansvar |
|-------|--------|
| `views_common.py` | `_patient_to_dict` — delt av de andre. JSON-kroppen er `core.jsonkropp` |
| `views_patients.py` | Hoved-side, innstillinger, sesjonstimeout, pasient-CRUD, vaktavslutning/-gjenåpning |
| `views_registre.py` | Førstehjelper- og helsepersonellregisteret (én fabrikk bygger begge) |
| `views_arkiv.py` | Vaktarkivet |

Alle endepunkter er JSON-API-er beskyttet med `@login_required` + rollesjekk. Responser følger mønsteret `{'status': 'ok', 'data': ...}` eller `{'status': 'error', 'message': ...}`.

## Frontend — fem filer, og skillet som er en tilgangsgrense

Hva som lastes når står i rota; hva filene gjør står her.

| Fil | Ansvar |
|---|---|
| `patients-utils.js` | Rollesynlighet, delt tilstand, klokke, skjemahjelpere |
| `patients-table.js` | Tabulator-grid og tavle |
| `patients-forms.js` | Registrerings- og redigeringsskjema |
| `patients-app.js` | Oppstart (`DOMContentLoaded`), faneskift, auto-refresh, lastere for navneregistrene |
| `patients-admin.js` | Registeradmin, sesjonstimeout, vaktavslutning/-gjenåpning, vaktarkiv |

**Alt en ikke-admin kan nå, må ligge i en alltid-lastet fil.** `patients-admin.js` lastes
kun for admin, men skrivetilgang uten admin-tilgang finnes — derfor bor f.eks.
`saveEventName` i `patients-app.js`. Kall fra alltid-lastet kode inn i admin-fila går
gjennom `_kall('navn')`, som sjekker at funksjonen finnes. `JsModulLastingTests`
håndhever begge deler.
