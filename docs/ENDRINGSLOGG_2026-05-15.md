# Endringslogg – 15. mai 2026

## URL-rydding: server-status flyttet

- Kanonisk URL endret fra `/pasienter/admin/server-status/` → `/portal-admin/server-status/`
- Bakover-kompatible redirects (301) bevarer gamle URL-er: `/admin/server-status/` og `/pasienter/admin/server-status/` redirecter automatisk til ny adresse
- 4 hardkodede `fetch()`-URL-er i `admin_status.html` erstattet med Django `{% url %}`-tags via et `ADMIN_URLS`-objekt
- Middleware-skiplist, tester (~30 referanser) og legacy-redirect i `core/urls.py` oppdatert

## Visuell konsistens

- **Server-status**: CSS-variablene (`--surface-1`, `--border-color` o.l.) fra den gamle `base.html` var udefinerte etter template-bytte til `base_portal.html` → byttet til `--portal-*`-varianter. Overflødig `.admin-content`-wrapper fjernet.
- **Portal-header**: Brukernavn og rolle-badge fjernet fra headeren (alltid synlig). Kompakt navn + rolle vises nå øverst inne i bruker-dropdown-en i stedet.
- **Admin-nav**: «Brukere»-lenke lagt til i portal-navigasjonen for admin-brukere (var tidligere bare tilgjengelig via dropdown).
- **Pasientmodul-dropdown**: «Min profil»-lenke lagt til for konsistens med portal-dropdown-en.

## Testresultat

481 tester, alle grønne.
