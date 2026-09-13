# Tredjepartsbibliotekene (13. sep. 2026, sikkerhetsgjennomgangen H3)

Lastet fra CDN fram til da, uten Subresource Integrity, og med CDN-vertene åpne i
CSP-ens `script-src` — én HTML-injeksjon kunne dermed laste en hvilken som helst
npm-pakke. Nå ligger de her, WhiteNoise hasher og serverer dem, og `script-src` er
`'self'` + nonce.

| Mappe | Pakke | Versjon | Fil(er) |
|---|---|---|---|
| `bootstrap/` | `bootstrap` | 5.3.2 | `dist/css/bootstrap.min.css`, `dist/js/bootstrap.bundle.min.js` |
| `bootstrap-icons/` | `bootstrap-icons` | 1.11.3 | `font/bootstrap-icons.min.css`, `font/fonts/*.woff2`/`.woff` |
| `tabulator/` | `tabulator-tables` | 6.2.5 | `dist/css/tabulator_bootstrap5.min.css`, `dist/js/tabulator.min.js` |
| `chartjs/` | `chart.js` | 4.4.2 | `dist/chart.umd.js` (er minifisert) |

`sourceMappingURL`-kommentarene er fjernet: kartfilene følger ikke med, og
manifestlageret ville ellers stoppet `collectstatic` på en fil som ikke finnes.

Oppdatering: `npm pack <pakke>@<versjon>`, pakk ut, kopier filene over, fjern
`sourceMappingURL`, oppdater tabellen og `VERSJON` i `static/js/vaktliste-sw.js`.
