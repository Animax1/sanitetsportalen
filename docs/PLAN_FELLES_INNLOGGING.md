# Innlogging i kartet fra KO (19. okt. 2026)

> Opphever «Innloggingene forblir separate» (17. okt. 2026, `BESLUTNING_PORTALER.md` §4.10)
> for én vei inn: knappen «Åpne kartet» i KO. Kartets egen innlogging står uendret, som
> reserve og for brukere uten KO. Kartets side av saken står i `kart-sanitet/docs/PLAN.md` §1.

## 1. Beslutninger

| Spørsmål | Beslutning |
|---|---|
| Hvem kommer inn | **Den som har KO (`les`) i portalen de står i nå.** Ingen egen tilgangsrad |
| Hvor knappen står | **I KO**, åpner kartet i ny fane |
| Av og på | **Én global bryter for admin** på `/admin/innstillinger/` (KO-kortet), av som standard. Bryteren stenger på serveren, ikke bare knappen. Kartet har sin egen: uten `PORTAL_INNLOGGING_NOKKEL` tar det ikke imot |
| Hva de ser | **Gruppene i kartet som viser portalen de kom fra.** Medlemskapet i grupper med portal settes ved hver innlogging til nøyaktig disse; grupper uten portal røres ikke. Finnes ingen slik gruppe, avvises innloggingen med en forklaring i stedet for et tomt kart |
| Hva de kan | **KO `les` ser, `skriv_full` og opp kan tegne.** Nivået ligger i økten, ikke på kontoen, og en portalkonto uten nivå i økten kan bare lese |
| Identitet i kartet | **Egen konto per portalbruker** (`Bruker.portal_bruker_id`), uten passord og uten admin. Kobles ikke til en eksisterende kartkonto i denne runden |
| Retning | **Bare portal → kart, gjennom nettleseren** (B2 står): portalen lager billetten, nettleseren poster den, kartet ringer aldri tilbake |
| Økten | **12 timer**, ikke kartets vanlige 7 døgn — den kan ikke trekkes tilbake fra portalen ennå |

## 2. Billetten

```
<base64url(JSON)>.<hex HMAC-SHA256(nøkkel, "kartinnlogging.v1." + base64url-delen)>
```

JSON: `aud` (kartets vert), `portal` (slug), `bruker` (portalens bruker-ID), `navn`, `skriv`
(bool), `iat`, `exp` (høyst 120 s etter `iat`, portalen gir 60), `jti` (32 hex-tegn).

| Regel | Hvorfor |
|---|---|
| **Egen nøkkel** (`KART_INNLOGGING_NOKKEL` / `PORTAL_INNLOGGING_NOKKEL`), og eget prefiks i signaturen | En lekket posisjonsnøkkel skal ikke kunne logge inn som hvem som helst |
| **Brukes én gang** (`konto.BruktBillett`) | Posisjonskanalen tåler gjentak med vilje; en gjentatt billett er en ny økt |
| **POST, aldri i URL-en** | Holder den ute av logger, historikk og `Referer` |
| **Slugen står inne i billetten** | Ellers kunne den som har KO i én portal se en annens biler og lag |
| **`aud` sjekkes mot verten** | En billett til testkartet virker ikke i prod, selv om noen deler nøkkel ved en feil |
| **Forrige nøkkel godtas** (`…_FORRIGE`) | Rotasjon uten nedetid, som posisjonsnøkkelen |

`TESTVEKTOR` i begge repoene låser formatet: samme nøkkel og innhold gir samme billett, og
testen er rød i begge hvis én side endrer formen.

## 3. Flyten

1. KO tegner «Åpne kartet» som et skjema (`POST /ko/kart/`, `target="_blank"`) når bryteren er
   på og kartet er satt opp.
2. `ko.views.kart_view` sjekker bryteren og KO-nivået, lager billetten og svarer med en side
   som poster den videre til `<KART_URL>/konto/fra-portalen/`. CSP-ens `form-action` får
   kartets vert på akkurat dette svaret.
3. Kartet sjekker billetten, lager eller oppdaterer kontoen, setter gruppene, logger inn med
   en `konto.PortalEnhet` som MFA-enhet (portalen har alt krevd MFA) og sender til kartet.

## 4. Ikke i denne runden

| Hva | Hvorfor |
|---|---|
| Portalen melder «fryst/slettet» til kartet | Økten er 12 timer og ingen ny billett utstedes; meldingen er neste steg (TODO i begge) |
| Kobling til en eksisterende kartkonto | Der feil i kontokobling gjør skade, og gevinsten er liten når tegningene hører til gruppa |
| Bryter per portal | Én global holder til det trengs |
