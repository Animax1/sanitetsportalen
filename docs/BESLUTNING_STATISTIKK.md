# Beslutningsnotat: statistikk-utvidelse

Status: **besluttet i prinsippet, ikke bygget. Fem spørsmål må besvares før noen skriver
kode.** De står i «Åpne avklaringer» nederst.

Dette er den største enkeltoppgaven i backloggen — 25–35 timer, faseinndelt. Den lå som
punkt F6 i `docs/FORBEDRINGER_2026-08.md` fram til 22. aug. 2026, da den fila ble folt inn
i `TODO.md`. F6 fulgte ikke med: den er ikke et punkt på en liste, den er en plan med
personvernvurderinger og et statistikkfaglig innhold som ikke lar seg komprimere til en
kulepunkt-linje uten at det som gjør den brukbar forsvinner.

**Underlaget mangler.** Seksjonen bygger opprinnelig på `STATISTIKK_ANALYSE_FORSLAG.md` og
`STATISTIKK_IMPLEMENTERINGSPLAN.md`. De to finnes ikke i dette repoet og har aldri gjort
det — de stammer fra den gamle Pasientregistreringsappen
(`C:\Programmering\pasientregistrering`). Skal dette bygges, må underlaget enten hentes
derfra eller skrives på nytt. Notatet under står på egne ben i mellomtiden.

**Slettes** når statistikk-utvidelsen er levert, eller når den avlyses. Da er begrunnelsen
CHANGELOG sin.

---

**Verdi:** Middels–Høy &nbsp;|&nbsp; **Innsats:** 25–35 timer totalt, faseinndelt

Forbedringen deles i to leveranser med ulik personvernprofil, som kan deployes uavhengig:
**(a) live-statistikk for alle innloggede** og **(b) utvidet evalueringsstatistikk for
admin/lead**.

### Tilgangsmodell

**Oppdatert 28. aug. 2026:** tabellen er skrevet om til modulnivåer. Rollene
`admin/lead/lead_view` styrer ikke lenger tilgang — se
`docs/BESLUTNING_ROLLEMODELLEN.md`.

| Endepunkt | Tilgang | Innhold | Polling |
|---|---|---|---|
| **`/pasienter/api/stats/live/`** (NY) | `patients: les` | A1–A4 (operativ sanntid) | 30–60 s |
| `/statistikk/api/full-stats/` | `statistikk: les` **og** `patients: les` | B1–B6, C1–C2, D1–D5 | 60–120 s |

**Rasjonale:** Live-data er aggregert og operativt — alle som kan lese modulen har nytte av
kø-situasjonen, og de ser uansett de samme pasientene i lista. Full-stats inneholder
personvernfølsomme krysstabeller og evalueringsdata som krever fagansvar.

**Full-stats krever begge**, ikke bare statistikkmodulen: modulen komponerer tilgang, den
eier den ikke (§5 i rollemodellnotatet). Uten kravet om `patients: les` ville aggregatene
gitt avledet innsyn i pasientdata til noen som ikke har tilgang til dem.

**`/api/stats/` er slettet (28. aug. 2026).** Notatet forutsatte at stien fantes, og lot
spørsmålet om å beholde eller slette den stå åpent til `/api/stats/live/` skulle bygges.
Svaret ble sletting, og det ble tatt før: endepunktet matet aldri header-chipsene — de
regnes ut i `patients-table.js` fra pasientlista — og hadde ingen kjent konsument.

Det påvirker ikke `/pasienter/api/stats/live/`. Den er et nytt endepunkt med et faktisk
formål, ikke en videreføring av det slettede, og stien er ledig.

### (a) Live-dashbord — A-nivå

- **A1 Samtidighetskurve** — 15-min buckets, event-basert sweep O(n log n), per-triage-fordeling + peak. Chart.js stacked area.
- **A2 Tid-til-behandler** — fra `inntid` til behandler er tildelt. Vi har ikke timestamp på FK-en, men `AuditLog` har det: første rad med `field_name='forstehjelper_id'` og ikke-tom `new_value`. Output `{n, mean, median, p90, per_triage}`.
- **A3 Gjennomstrømning** — `utskrevet` og `inntid` bucket per time, to serier + akkumulert netto-gap.
- **A4 Flaskehalsindikator** — tre reelle tilstander blant `utskrevet=''`: venter behandling, under behandling, på obspost. Horisontal stacked stolpe + heuristiske varsler.

### (b) Utvidet evaluering — B/C/D-nivå

- **B1** Utfallsfordeling (stacked bar først, Sankey senere) · **B2** Behandler-produksjon, **aggregert med k≥3** · **B3** Plasseringsbelastning · **B4** Årsak × Problemstilling · **B5** Medisiner og lege-konsultasjoner · **B6** Journal-rate
- **C1** Boxplot (`chartjs-chart-boxplot`, ~8 KB) · **C2** Persentiler P50/P90/P95 i `sd()`
- **D1** Dunn post-hoc (egen 30-linjers implementasjon, ikke `scikit-posthocs`) · **D2** Effektstørrelser (Cramér's V, Epsilon²) · **D3** Konfidensintervall (Wilson, bootstrap) · **D4** Fisher's exact for 2×2 · **D5** Forbedret automatisk tolkning som kombinerer p-verdi, effektstørrelse og n

### Faseinndeling

| Fase | Innhold | Estimat |
|---|---|---|
| 1 — Infrastruktur | `services_stats_live.py`, cache-wrapper, cache-invalidering, tomt `/api/stats/live/`, AuditLog-indeks, smoke-tester | 4–6 t |
| 2 — Live-dashbord | A1–A4 + «Sanntid»-fane for alle, Chart.js-rendering, tester | 6–8 t |
| 3 — B/C-utvidelser | B1–B6, C1, C2 | 6–8 t |
| 4 — Statistiske tester | D1–D5 + 7 nye krysstabeller | 4–6 t |
| 5 — Test og personvern | Alle tester grønne, oppdater personvern- og teknisk dokumentasjon | 3–4 t |
| 6 — Deploy og overvåkning | Deploy, overvåk CPU/RAM første uke, juster cache-TTL | 1–2 t |

### Kritiske forbehold

1. **B2 må personvernvurderes.** Selv aggregert behandlerstatistikk kan re-identifisere ved få behandlere. Krev k≥3, ingen histogrammer som kan lekke.
2. **Invester i caching fra dag 1.** Forskjellen på elegant løsning og Railway-overraskelse på regningen.
3. **Hopp over Sankey i første versjon.** Stacked bar gir 80 % av verdien for 10 % av kompleksiteten.
4. **Merk «lite datagrunnlag» når n < 30.**
5. **Lasttest etter fase 2** (se F4) før fase 3 deployes.

### Åpne avklaringer

1. Bekreft tilgangsmodellen i tabellen over.
2. Sankey eller stacked bar for B1? (Anbefaling: stacked bar.)
3. Er B2 OK med k≥3-aggregat, eller utelates den inntil den er drøftet med verneombud?
4. Hvilken fase startes med? (Anbefaling: fase 1 + smal fase 2 med kun A1 og A4, for å se reell CPU-påvirkning.)
5. Polling-frekvens for live-fanen ved 20+ samtidige brukere: 30 s eller 60 s?

**Oppdatering august 2026:** To ting å ta hensyn til hvis dette startes.

- **Live-stats-flagget finnes allerede** som `feature.live_stats_enabled` i
  `patients/admin_status.py:40–41`, med default `'false'` nettopp fordi funksjonen ikke er
  bygget. Flytt defaulten til `'true'` i samme commit som leverer fase 2 — kommentaren i
  koden ber eksplisitt om det.
- **A2 avhenger av audit-loggen** for å utlede tildelingstidspunkt. Da bør N2 være løst
  først, ellers dekker A2 kun førstehjelper og ikke helsepersonell. Og F2 må settes opp
  med en retention som er lengre enn analysevinduet — det nytter ikke å regne på data
  purge-jobben nettopp slettet.

**Akseptansekriterium:** Live-dashbord (fase 1+2) deployet, alle innloggede ser
«Sanntid»-fanen, A1–A4 oppdateres uten manuell refresh. CPU-bruk ikke mer enn +10 % fra
baseline med 20 brukere på fanen. Cache-hit-ratio > 80 % under aktiv vakt.
