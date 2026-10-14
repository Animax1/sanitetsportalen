# Forslag: ordboka i `/oppdrag/` og `/ko/`

*14. okt. 2026. Kartlagt mot koden samme dag; ingenting er endret ennå. Vaktlista fikk sin
ordbok 30. sep. 2026 (CHANGELOG, «Vaktlista, pulje 3»), og `vaktliste/tests_ordboka.py`
holder den. Dette er neste steg: de samme ordene i de to andre modulene som viser de samme
tingene.*

## 0. Hva André bestemte for vaktlista

> **Ressurs er typen** (ambulanse, lag, mannskapsbil), **enhet er den konkrete** (Karmøy 51)
> — og **«vakten», ikke «vakta»**, med -en-form også for vaktlisten, filen, natten og gruppen.

Byttet gjaldt bare etikettene. Modellene heter det samme (`Ressurs`, `Ressursgruppe`), og
det skal de fortsette med.

## 1. Hva som er funnet

Talt med vaktlistevaktens egen leser (`synlig_tekst()` i `vaktliste/tests_ordboka.py`).
Den leser bare tekst brukeren ser — tekstnoder, `title`/`placeholder`/`aria-label`,
meldingsstrenger — og ikke kode, kommentarer eller docstrings.

| | `/oppdrag/` | `/ko/` |
|---|---:|---:|
| Treff på vaktlistas «gamle ord» | 16 | 89 |
| …av dem bøyningsformer (`tavla`, `vakta`, `vaktlista`, `lista`, `natta`) | 9 | 62 |
| …av dem «ressurs» om noe konkret | 7 | 25 |
| …av dem «ressursgruppe» | 0 | 2 |

**Bøyningsformene er mekaniske.** De trenger bare et ja til at regelen gjelder hele portalen
(spørsmål A). **Fire ting krever en avgjørelse** (B–E), og to av dem er ekte konflikter som
fantes før ordboka: samme ord betyr to ting på tvers av sidene.

## 2. Spørsmålene

### A. Gjelder -en-formen hele portalen?

`tavla` → `tavlen`, `vakta` → `vakten`, `vaktlista` → `vaktlisten`, `lista` → `listen`,
`natta` → `natten`, og `ressursgruppe` → `ressurstype` (to feilmeldinger i KOs program).

    Før:  Tavla viser vaktlistas ressurser, og krever lesetilgang i vaktlista.
    Etter: Tavlen viser vaktlistens enheter, og krever lesetilgang i vaktlisten.

**Anbefaling: ja.** I dag står `/vaktliste/` i -en-form og `/ko/` i -a-form, og den som
sitter i KO med vaktlista i nabofanen leser begge samtidig.

### B. Det konkrete heter «enhet» også i `/oppdrag/` og `/ko/`

Lista over biler og lag heter tre ting i dag: «Ressurser» på sentralbordet,
«Ressursoversikt» i KO, og en fane som heter «Enheter» inne i den.

    Sentralbordet (før)          Sentralbordet (etter)
    ┌ Ressurser ──────────┐      ┌ Enheter ────────────┐
    │ Karmøy 51   Ledig   │      │ Karmøy 51   Ledig   │
    │ Lag 3       Ute     │      │ Lag 3       Ute     │

    KO (før)                         KO (etter)
    ┌ Ressursoversikt ──────────┐    ┌ Enhetsoversikt ───────────┐
    │ [Enheter] [Oppdrag uten   │    │ [Enheter] [Oppdrag uten   │
    │            ressurs]       │    │            enhet] ← se C  │
    │ Tavle: kolonnen «Ressurs» │    │ Tavlen: kolonnen «Enhet»  │

Det gjelder også «Ukjent ressurs», «Ressursen finnes ikke lenger i vaktlista», og hjelpeteksten
i KO-innstillingene: «Vaktlistas ressurser uten oppdragsenhet — de som får oppdrag muntlig på
samband» blir «Vaktlistens enheter uten delt konto — de som får oppdrag muntlig på samband».
«Delt konto» er vaktlistas ord fra 30. sep. for koblingen til en oppdragskonto.

**«Lag» står.** Lag 3 *er* en enhet av typen lag, og ordet er riktig som det er.

**Anbefaling: ja.** Dette er selve poenget med ordboka. Uten det står «enhet» for Karmøy 51
i vaktlista og i feltet «Enheter» i «Nytt oppdrag», mens overskriften over den samme bilen
sier «Ressurser».

### C. «Trenger ressurs» — fagord eller ordbok?

Statusen på et oppdrag uten noen å sende står fem steder: «Trenger ressurs», «Oppdrag uten
ressurs», «Avbrutt — trenger ny ressurs», «Ingen ressurs» og «Tildelt ressurs». Den står
også i KO-loggens systemlinjer, «— oppdraget trenger ny ressurs».

| | For | Mot |
|---|---|---|
| **1. «Trenger enhet»** | Én betydning av «ressurs» i hele portalen | «Ressurs» er det sektoren sier om noe man sender — på samband og i AMK. Systemlinjene som alt står i KO-loggen beholder det gamle ordet, så arkivet får to |
| **2. Behold «Trenger ressurs» som fagord** | Det operatøren sier høyt. Loggen og skjermen sier det samme | Ordboka får ett navngitt unntak, og «ressurs» betyr to ting: typen i vaktlista, «noen å sende» her |

**Anbefaling: 2.** Det er et statusnavn og ikke en etikett på en ting, og et statusnavn
er noe folk lærer og sier på samband. Unntaket skrives inn i vakten med begrunnelse, så det
ikke «rettes» av neste gjennomgang. Men det er ditt ord, ikke mitt: velger du 1, er det fem
etiketter og to systemlinjer.

### D. «Tavla» betyr to ting

I `/ko/` er tavlen plasseringene: hvor hvert lag står nå og senere. I `/oppdrag/` brukes
«tavla» om oppdragslista: «Oppdraget opprettes som *Trenger ressurs* og står gult på tavla»,
og «Hent tilbake til tavla».

    /oppdrag/ (før):   …og står gult på tavla til du velger en enhet.
    /oppdrag/ (etter): …og står gult i oppdragslisten til du velger en enhet.

**Anbefaling: «oppdragslisten» i `/oppdrag/`, og «tavlen» bare i `/ko/`.** Sentralbordet
står også inne i `/ko/`. Der ligger «tavla» med to betydninger på samme skjerm.

### E. «Enhetstyper» i `/oppdrag/` og «Ressurstyper» i `/vaktliste/`

To verdilister for omtrent det samme: `oppdrag.Enhetstype` (ambulanse, mannskapsbil, lag til
fots, med flaggene for passiv vakt og avventing) og `vaktliste.Ressursgruppe` (samleplass,
ambulanse, mannskapsbil, lag, med ikon og roller). Begge kan redigeres, og «ambulanse»
finnes i begge.

**Anbefaling: la navnene stå ulike inntil videre.** Med samme navn på to lister som ikke er
den samme, vil admin rette i den ene og lete etter endringen i den andre. Det egentlige
spørsmålet er om de *skal* være én liste. Det er et spørsmål om datamodellen og ikke om
ordboka, og det hører hjemme i en egen runde. Ordboka gjør det synlig, den løser det ikke.

## 3. Slik bygges det når svarene er der

1. **Leseren flyttes til `core`.** I dag bor den i `vaktliste/tests_ordboka.py`. Med tre
   moduler er den en regel for flere moduler, og den hører hjemme i rota (CLAUDE.md:
   «En regel som gjelder to moduler hører hjemme i rota»). Hver modul beholder sin egen
   liste over gamle ord og sin egen test.
2. **Én vakt per modul**, med samme form som vaktlistas: ingen gamle ord i teksten brukeren
   ser, en `test_leseren_ser_teksten` med de nye ordene, og unntaket fra C (hvis 2) med
   begrunnelse.
3. **Etikettene byttes, ikke modellene og ikke URL-ene.** `/ko/api/tavle/`, `ressurs_id` og
   `trenger_ressurs` står. Vaktlistebyttet 30. sep. ga 404 på hvert kall mot en enhet fordi
   et ord inntil `/` ble byttet, og grensen i `GRENSE` er laget for nettopp det.
4. **Systemlinjene i KO-loggen er lagret tekst.** Nye linjer får de nye ordene, og gamle
   linjer står som de ble skrevet. Arkivet er historie og skal ikke skrives om.
5. **Skisser på staging før `main`**, som for vaktlista: sentralbordet, KOs enhetsoversikt,
   tavlen og «Nytt oppdrag».

Anslag: A og B er rundt 100 etiketter og én pulje. C og D er et titalls til.
