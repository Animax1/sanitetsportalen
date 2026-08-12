# Oppsett: cron-jobb for arkiv-kollaps

**Midlertidig dokument.** Slett det når jobben er satt opp i Railway.

Gjelder kommandoen `kollaps_arkiv`, som håndhever 24-måneders lagringstid for
arkiverte pasientrader (se `PERSONVERN_DOKUMENTASJON.md` A.9).

---

## Hva jobben gjør

Sletter permanent pasientradene i vaktarkiv eldre enn 24 måneder, og erstatter dem med
den ferdig beregnede statistikken. Alle tall du ser i arkivvisningen i dag bevares —
det er kun opplysningene om enkeltpasienter som forsvinner.

**Operasjonen er irreversibel.** Derfor er det bygget inn to sperrer:

1. Kommandoen nekter å kollapse et arkiv med mindre det finnes en backup av modulen
   `arkiv` tatt **etter** at arkivet ble opprettet. Da er slettingen gjenopprettbar.
2. Hver kollaps loggføres i `AuditLog`.

---

## Før du setter opp jobben

Du har antakelig ingen arkiver som er 24 måneder gamle ennå. Sjekk hva som ville skjedd:

```bash
python manage.py kollaps_arkiv --dry-run
```

Forventet svar i dag:

```
Ingen arkiv eldre enn 730 dager som ikke allerede er kollapset.
```

Får du det svaret, gjør jobben ingenting før arkivene faktisk blir gamle nok. Det er
som forventet — sett den opp nå, så virker den når tiden kommer.

---

## Sett opp i Railway

1. Åpne prosjektet i Railway
2. **+ New** → **Cron Job** (eller legg til en ny tjeneste fra samme repo og sett
   *Cron Schedule* under **Settings**)
3. Koble tjenesten til samme database og samme volum som web-tjenesten
4. Sett følgende:

| Felt | Verdi |
|---|---|
| **Start Command** | `python manage.py kollaps_arkiv` |
| **Cron Schedule** | `0 4 1 * *` |

`0 4 1 * *` betyr kl. 04:00 den 1. i hver måned. Månedlig er rikelig — grensen er
24 måneder, så noen dagers slingring spiller ingen rolle. Nattestid unngår at jobben
kolliderer med en vakt.

5. Sørg for at tjenesten har de samme miljøvariablene som web-tjenesten, minimum:
   `DATABASE_URL`, `SECRET_KEY`, `BACKUP_DIR`

> **Viktig:** `BACKUP_DIR` må peke på `/data/backups`, samme som web-tjenesten.
> Uten den finner ikke kommandoen arkiv-backupene, og backup-sperren vil stoppe
> alle kollapser.

---

## Hvorfor ikke bare legge den i `purge_old_logs`?

Den kommandoen kjører allerede som cron og håndhever de andre lagringstidene. Men
`kollaps_arkiv` sletter helseopplysninger permanent, og en slik operasjon bør ikke fyre
som bieffekt av en loggopprydding. Holdes de adskilt, kan du kjøre logg-oppryddingen
uten å risikere noe irreversibelt.

---

## Verifisere at det virker

Etter første kjøring, sjekk loggen i Railway. Forventet utdata når noe faktisk
kollapses:

```
  Kollapset «Festivalen — arkivert 12.06.2024 23:14»: 47 pasientrader slettet.

Ferdig: 1 arkiv kollapset, 0 hoppet over.
```

Ser du derimot:

```
  HOPPET OVER «...» (47 pasientrader): ingen arkiv-backup tatt etter at
  arkivet ble opprettet. Kjør en backup av modulen «arkiv» først.
```

…så virker sperren som den skal. Gå til `/portal-admin/backup/arkiv/`, lag en manuell
backup, og la jobben gå igjen ved neste kjøring.

---

## Manuell kjøring ved behov

Via Railway Shell på web-tjenesten:

```bash
python manage.py kollaps_arkiv --dry-run    # se hva som ville skjedd
python manage.py kollaps_arkiv              # utfør
python manage.py kollaps_arkiv --days 900   # annen grense
```

Flagget `--ignorer-backup-sperre` finnes, men bør ikke brukes. Det slår av den eneste
beskyttelsen mot at en feil blir permanent.
