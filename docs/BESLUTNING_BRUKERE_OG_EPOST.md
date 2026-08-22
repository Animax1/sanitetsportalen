# Beslutningsnotat: brukerregistrering, passord-reset og e-post

Status: **til gjennomgang.** Ingenting av dette er bygget. Notatet finnes for at
beslutningene skal tas i ro, og for at rekkefølgen skal være riktig når de bygges.

Skrevet 14. aug. 2026.

---

## 1. Hvordan e-post fungerer i dag

**Oppdatert 22. aug. 2026. E-post virker nå i produksjon** — dette avsnittet beskrev
tidligere en tilstand der ingenting ble sendt.

Transporten er **AHASends HTTP-API v2**, ikke SMTP:

```
POST https://api.ahasend.com/v2/accounts/{account_id}/messages
Authorization: Bearer aha-sk-...
```

Implementert i `core/mail_backends.py`. Backend velges etter hva som er satt
(`myproject/settings.py`):

```python
if AHASEND_API_KEY and AHASEND_ACCOUNT_ID:
    EMAIL_BACKEND = 'core.mail_backends.AhaSendApiBackend'
elif EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

**SMTP er ikke et alternativ på Railway.** Målt fra containeren 22. aug. 2026 er portene
587, 2525, 465 og 25 alle stengt, mens 443 mot samme vert er åpen. Det er en
plattformpolicy mot spam-misbruk — å bytte SMTP-leverandør ville truffet samme vegg.
SMTP-grenen beholdes fordi den virker lokalt og i offline-modus.

Avsender er `Sanitetsportalen <noreply@mail.sanitet.net>`, og verifisert helt fram til
innboks. Den eneste avsenderen er fortsatt Djangos `AdminEmailHandler` ved uhåndterte
500-feil (F1); det finnes ingen brukerrettet e-post og ingen passord-reset ennå.

To detaljer som fortsatt betyr noe:

- `DEFAULT_FROM_EMAIL` må ligge på et domene leverandøren er autorisert for. Gjør den ikke
  det, avvises meldingen ved innsending — og varselet du skulle fått, uteblir stille.
- `CustomUser.email` er **valgfri**, med `help_text` «Brukes kun som kontaktinformasjon for
  admin». Unik hvis satt, via betinget constraint. Gjøres den til reset-kanal, endrer
  feltet rolle fra kontaktinfo til **gjenopprettingsvei for legitimasjon**.

---

## 2. Forutsetningene som allerede er på plass

Fire deler måtte til. Alle er dekket — nevnt her fordi den tredje er den folk hopper over,
og fordi de må vurderes på nytt hvis leverandør noen gang byttes.

### 2.1 En tjeneste som vil sende for oss ✅

AHASend, med API-nøkkel og konto-ID i Railway-variablene `AHASEND_API_KEY` og
`AHASEND_ACCOUNT_ID`. Nøkkelen bør ha det domenebegrensede scopet
`messages:send:mail.sanitet.net`, ikke `messages:send:all`.

### 2.2 En avsenderadresse på et domene vi kontrollerer ✅

`noreply@mail.sanitet.net`.

### 2.3 DNS-oppføringer på det domenet ✅

Mottakeren sjekker om avsenderen har lov til å sende for domenet vårt. Uten **SPF** og
**DKIM** havner mailen i spam eller avvises. Bekreftet i praksis: testmeldingene landet i
innboksen, ikke i spam.

### 2.4 Miljøvariablene i Railway ✅

`ADMINS`, `DEFAULT_FROM_EMAIL`, `AHASEND_API_KEY` og `AHASEND_ACCOUNT_ID` på `web`-tjenesten.
Verifiser med `python manage.py verifiser_feilvarsel` — **kjørt inne i containeren**, ikke
via `railway run`, som kjører koden på utviklingsmaskinen med et annet nettverk.

---

## 3. Leverandørvalget er tatt

AHASend er valgt og i drift. Dette avsnittet listet tidligere SMTP-alternativer (Brevo,
Resend, Gmail, egen server) — de er uaktuelle så lenge portalen kjører på Railway, siden
utgående SMTP er sperret uansett leverandør.

Skal leverandør byttes, er kravet at tjenesten har et **HTTP-API**, ikke bare SMTP. Da må
`core/mail_backends.py` skrives om for det nye API-et, og seksjon 2 gjennomgås på nytt —
særlig DNS-oppføringene, som er leverandørspesifikke.

Volum er ikke en begrensning: prosjektet trenger noen titalls invitasjoner før en vakt,
pluss reset ved behov.

---

## 4. Databehandler: må avklares før valg

**Dette er nå en åpen mangel, ikke et framtidig valg.** AHASend er tatt i bruk og er
dermed databehandler allerede — også før invitasjons- og reset-flyten bygges.

Feilvarselet som sendes i dag inneholder brukernavn og rolle på den som opplevde feilen,
klient-IP, forespurt URL og traceback. Ingen kliniske opplysninger — skjemadata, cookies,
settings og lokale variabler er bevisst utelatt, og `core/tests_error_reporting.py` vokter
det. Men det er personopplysninger, og de går gjennom to tredjeparter: AHASend ved
utsending, og Google som mottakerens innboks.

Det krever:

- en databehandleravtale med AHASend
- at både AHASend og Google føres opp i `docs/PERSONVERN_DOKUMENTASJON.md` A.2, sammen med
  Railway. Lagringstiden i mottakerens innboks styres av Google, ikke av applikasjonen —
  samme forbehold som allerede står om Railways databasebackup

Bygges invitasjon og reset senere, utvides innholdet med e-postadresser, men
databehandlerforholdet er det samme. Står i TODO under dokumentgjennomgangen.

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

1. ~~**Utsending verifisert.**~~ ✅ Gjort 22. aug. 2026: AHASends HTTP-API, SPF/DKIM på
   plass, og testmeldinger bekreftet i innboksen — ikke spam. Verifiseres på nytt med
   `verifiser_feilvarsel` etter enhver endring i oppsettet.
2. **Databehandleravtale** med AHASend og oppføring i personvernprotokollen. **Denne er nå
   forfalt** — leverandøren er i bruk, se seksjon 4.
3. **Migrasjonen** for `fullt_navn` og `er_delt_konto`, alene.
4. **Invitasjonsflyten.**
5. **Passord-reset**, med de syv punktene i seksjon 6.

Punkt 1 var ikke en formalitet. Uten fungerende utsending er hele funksjonen inert: brukeren ber om reset,
får «vi har sendt en lenke», og ingenting kommer. Det er verre enn ingen funksjon, fordi de
slutter å ringe deg mens de venter.

Og leveringsevne avgjør om det blir brukbart i det hele tatt. En reset-lenke i spam midt i
en vakt betyr at brukeren ringer deg likevel — men nå i tro på at selvbetjening finnes.
