# Beslutningsnotat: brukerregistrering, passord-reset og e-post

Status: **til gjennomgang.** Ingenting av dette er bygget. Notatet finnes for at
beslutningene skal tas i ro, og for at rekkefølgen skal være riktig når de bygges.

Skrevet 14. aug. 2026.

---

## 1. Hvordan e-post fungerer i dag

Én bryter styrer alt, i `myproject/settings.py`:

```python
if EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

`EMAIL_HOST` er **ikke satt i produksjon**. All e-post skrives derfor til Railway-loggen
i stedet for å sendes. Ingenting feiler — det forsvinner bare.

Den eneste avsenderen er Djangos `AdminEmailHandler`, koblet inn som `mail_admins`-handler
i `LOGGING`. Den sender stacktrace til `ADMINS` ved uhåndterte 500-feil (F1). Det finnes
ingen brukerrettet e-post og ingen passord-reset.

To detaljer som betyr noe:

- `DEFAULT_FROM_EMAIL` har default `sanitetsportalen@example.invalid` — et bevisst ugyldig
  domene, slik at ingenting sendes fra et domene vi ikke eier hvis SMTP skrus på uten å
  sette avsender.
- `CustomUser.email` er **valgfri**, med `help_text` «Brukes kun som kontaktinformasjon for
  admin». Unik hvis satt, via betinget constraint. Gjøres den til reset-kanal, endrer
  feltet rolle fra kontaktinfo til **gjenopprettingsvei for legitimasjon**.

---

## 2. Hva som kreves for at SMTP skal virke

Fire deler. Den tredje er den folk hopper over, og grunnen til at «SMTP virker» men ingen
får mailen.

### 2.1 En server som vil sende for oss

Vert, port, brukernavn, passord.

### 2.2 En avsenderadresse på et domene vi kontrollerer

`DEFAULT_FROM_EMAIL`, f.eks. `Sanitetsportalen <ingen-svar@dittdomene.no>`.

### 2.3 DNS-oppføringer på det domenet

Mottakeren sjekker om serveren som sender har lov til å sende for domenet vårt. Uten
**SPF** og **DKIM** havner mailen i spam eller avvises. Leverandørene under gir 2–3
DNS-oppføringer å lime inn hos domeneleverandøren, og håndterer DKIM-signeringen selv.

### 2.4 Miljøvariablene i Railway

Se eksemplene under.

---

## 3. Alternativer for SMTP

### Brevo (fransk, innenfor EØS) — anbefalt

```
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=<brevo-innlogging>
EMAIL_HOST_PASSWORD=<smtp-nøkkel fra Brevo>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=Sanitetsportalen <ingen-svar@dittdomene.no>
```

### Resend (enkelt oppsett, god dokumentasjon)

```
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=<api-nøkkel>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=Sanitetsportalen <ingen-svar@dittdomene.no>
```

### Gmail / Google Workspace (raskest i gang)

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=dinkonto@gmail.com
EMAIL_HOST_PASSWORD=<app-passord, ikke kontopassordet>
EMAIL_USE_TLS=True
```

App-passord krever 2FA på kontoen. Har sendegrenser, og avsender må matche kontoen — altså
kan vi ikke sende fra organisasjonens domene med mindre kontoen ligger der.

### Organisasjonens egen e-postserver

Mest kontroll, men avhenger av at IT vil åpne for relay fra Railway.

### Gratisnivåene

Alle de kommersielle ligger på flere hundre til noen tusen e-poster i måneden. Dette
prosjektet trenger langt mindre — noen titalls invitasjoner før en vakt, pluss reset ved
behov.

---

## 4. Databehandler: må avklares før valg

En e-postleverandør blir **databehandler**. Reset- og invitasjonsmail inneholder
brukernavn og e-postadresse, altså personopplysninger som går gjennom tredjepart.

Det krever:

- en databehandleravtale med leverandøren
- at leverandøren føres opp i `docs/PERSONVERN_DOKUMENTASJON.md` sammen med Railway

Velges en leverandør innenfor EØS, er det en kort avtale og en linje i protokollen. Velges
en amerikansk, må overføringsgrunnlaget beskrives. Ikke et hinder — men mye enklere å gjøre
nå enn å oppdage ved neste gjennomgang.

---

## 5. Registrering: invitasjon (besluttet)

Admin oppretter kontoen med rolle og navn, systemet sender en signert lenke, brukeren
setter sitt eget passord.

Fordelen framfor dagens flyt: **det midlertidige passordet finnes ikke.** I dag genererer
`user_create_view` et 12-tegns passord som vises på skjermen én gang og må formidles
videre — typisk over en kanal man ikke vil ha passord i. Med invitasjon er det ingenting å
formidle.

Admin beholder full kontroll over hvem som eksisterer og hvilken rolle de får.

### Vurdert og ikke valgt

**Invitasjonskode med begrenset bruk.** Admin lager en kode, deler den med et vaktlag, folk
registrerer seg selv. Løser bulk-onboarding, men koden kan lekke. Ville krevd utløpsdato,
maks antall bruk, fast lav rolle som admin hever, og logging per bruk. Bygges ikke nå —
først hvis bulk-onboarding viser seg å være et reelt problem.

**Domenebegrenset selvregistrering** (`@dinorganisasjon.no`). Svakest kontroll, og krever
e-postverifisering uansett.

---

## 6. Passord-reset: syv beslutninger

Django har flyten innebygd og godt testet (`PasswordResetView` m.fl.). Det som er
prosjektspesifikt:

### 6.1 Ikke-personlige kontoer utelates

Bil-kontoene deler enhet og har ingen personlig eier. En reset-lenke til en delt innboks er
en lateral vei inn i systemet.

Løses med et **eksplisitt flagg**, ikke ved å utlede fra «har e-post» — ellers slår det feil
den dagen noen legger inn en kontakt-e-post på en bil-konto. Admin-reset beholdes for alle.

### 6.2 MFA kan ikke omgås

Reset via e-post gir nytt passord, men MFA-steget gjelder fortsatt. Mistes MFA-enheten, må
admin være eneste vei. Det er tilfellet i dag (`reset_mfa` er admin-only) og må forbli slik
— ellers er MFA verdiløst.

### 6.3 Sesjoner drepes

Som ved admin-reset. Uten det overlever en stjålet sesjon passordbyttet.

### 6.4 `must_change_password` nullstilles

Flagget håndheves av `accounts/middleware.py`: er det satt, omdirigeres brukeren til
passordbytte og kommer ikke videre.

Det er riktig når **admin** har generert et midlertidig passord. Ved selvbetjent reset
velger brukeren passordet selv i reset-skjemaet — står flagget igjen, må de velge to
passord på rad uten forklaring. Sett det derfor til `False` når resetten fullføres.

### 6.5 Egen rate-limit-bøtte

Mønsteret finnes i `accounts/views.py::_er_rate_limited` (fra N4). Uten det kan hvem som
helst spamme en brukers innboks ved å be om reset i loop.

### 6.6 Kortere token-levetid

`PASSWORD_RESET_TIMEOUT` er ikke satt, så Djangos default på tre døgn gjelder. For en
vaktkontekst er noen timer riktigere.

### 6.7 Ingen kontoenumerering

Hvis skjemaet svarte «ingen bruker med den adressen», kunne hvem som helst prøve adresser
og få vite hvilke som har konto. For en frivillig organisasjon avslører det **hvem som er
medlem og har vakter** — en personopplysning i seg selv, uavhengig av om noen kommer inn.

Djangos standardvisning svarer identisk uansett: «Har du en konto med denne adressen, er
det sendt en lenke.» Behold den oppførselen. Samme prinsipp gjelder innloggingsskjemaet —
«feil brukernavn eller passord», aldri hvilken av dem.

---

## 7. Modellendringer som kreves

`CustomUser` arver fra `AbstractBaseUser`, **ikke** `AbstractUser`. `first_name`/`last_name`
finnes derfor ikke. To felt må legges til:

| Felt | Type | Begrunnelse |
|---|---|---|
| `fullt_navn` | `CharField(max_length=150, blank=True, default='')` | Ett fritekstfelt, ikke for-/etternavn. Formålet er å kjenne igjen personen bak `superman64@mail.com`, og ett felt håndterer mellomnavn, doble etternavn og folk som skriver navnet sitt annerledes enn en skjemadesigner forventer. |
| `er_delt_konto` | `BooleanField(default=False)` | Ikke-personlig konto: bil-innlogginger og liknende. |

### Hva `er_delt_konto` må håndheves som

Dette er en **kontotype**, ikke bare et flagg. Hvert unntak må ellers huskes hver gang:

- valideringen **nekter** e-post og navn, ikke bare lar dem stå tomme
- MFA kan ikke kreves — «Krev MFA»-knappen bør være avslått i admin-UI, ikke bare ignorert
- selvbetjent reset avvises, selv om noen senere legger inn en kontakt-e-post
- passordet **settes direkte av admin**, i stedet for å genereres

Forbehold på det siste: admin-valgte passord blir i praksis mønstre — `Bil1-2027`,
`Bil2-2027`. Passordvalidatorene må fortsatt gjelde, og hver bil må ha et distinkt passord.
Ellers er én lekket bil-konto alle bil-kontoene.

### Migrasjonen

**Kun `AddField`. Gjør den ene tingen. Ikke bundle med noe annet.**

Modellstatus stemmer ikke med prod-databasen i dette prosjektet, og 13. aug. 2026 tok en
uetterspurt indeks-omdøping ned prod i 30 minutter fordi release-fasen kjører `migrate` og
en feilende migrasjon crash-looper containeren. `accounts/0008` er håndskrevet av samme
grunn.

Før den pushes: sett opp en lokal database i den tilstanden prod faktisk er i, og kjør
`migrate` mot den. Ikke resonner deg fram til hva som er anvendt.

---

## 8. Rekkefølge

1. **SMTP verifisert.** Sett `EMAIL_HOST`, `DEFAULT_FROM_EMAIL` og resten, legg inn
   SPF/DKIM, og verifiser med en framprovosert 500 slik TODO sier. Sjekk at mailen lander i
   **innboksen**, ikke spam — og på de klientene folk faktisk bruker.
2. **Databehandleravtale** og oppføring i personvernprotokollen.
3. **Migrasjonen** for `fullt_navn` og `er_delt_konto`, alene.
4. **Invitasjonsflyten.**
5. **Passord-reset**, med de syv punktene i seksjon 6.

Punkt 1 er ikke en formalitet. Uten SMTP er hele funksjonen inert: brukeren ber om reset,
får «vi har sendt en lenke», og ingenting kommer. Det er verre enn ingen funksjon, fordi de
slutter å ringe deg mens de venter.

Og leveringsevne avgjør om det blir brukbart i det hele tatt. En reset-lenke i spam midt i
en vakt betyr at brukeren ringer deg likevel — men nå i tro på at selvbetjening finnes.
