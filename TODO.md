# TODO – Sanitetsportalen

## Pågående / neste

- [ ] ...


## Ideer / backlog

- [ ] Faktisk kobling mellom brukere og behandler/helsepersonell.
- [ ] Vurder å endre behandler til førstehjelper?
- [ ] Vaktliste
- [ ] KO-tavle.
- [ ] Fytte sesjons delen til en admin side.
- [ ] Fjerne sanitetsportal og brukeradministrasjon fra /portal-admin/moduler/
- [ ] Integrasjon med produksjons database.
- [ ] ...

## Ferdig ✓

- [x] Rydde opp i CSS filene, det er flere plasser hvor tekst farger er for mørke, det må vi se litt på. Dette krever nok en del arbeid.
- [x] Del opp `script.js` i separate moduler (patients-utils, patients-table, patients-forms, patients-stats)
- [x] Visuell konsistens: `accounts/users/` og `admin_status.html` bruker nå `base_portal.html`
- [x] Flytt server-status URL: `/pasienter/admin/server-status/` → `/portal-admin/server-status/`
- [x] Fjern brukernavn/rolle fra portal-header, vis i dropdown i stedet
- [x] Legg «Brukere» til i admin-navigasjonen i portalen
- [x] «Min profil»-lenke lagt til i pasientmodul-dropdown
