"""Søkeord i CHANGELOG — så arkivet kan slås opp i, ikke bare leses.

**Problemet er målt** (17. sep. 2026). CHANGELOG er 11 651 linjer og 650 000
tegn. `CLAUDE.md` sier at den aldri leses i sin helhet — den `grep`-es — og det
virker når du kjenner symptomet: «[object Object]» og «to enheter varsles» var
søkbare fordi de sto der ordrett.

Det virker **ikke** når spørsmålet er et tema. «Hva har skjedd med roller?» gir
84 entries som nevner ordet, og seks som handler om det. «Korps» gir 51 mot
fire, «offline» 35 mot to. Det er ikke et oppslag, det er lesing — og da er
arkivet i praksis stengt for den som ikke alt vet hvor hun skal se.

**To ulike behov, to ulike mekanismer:**

| Behov | Mekanisme |
|---|---|
| Følge en peker — «regelen viser til CHANGELOG 16. sep.» | Overskriften. Ingen duplikate titler, ett `grep` |
| Ramse opp et tema — «alt om planleggeren» | **Søkeordet**, denne fila |

Formen er `` `#<app>/<tema>` `` **i overskriftslinja**, ikke på en linje under:
ett `grep` skal gi dato, tittel og tema samtidig. Står taggen for seg selv, får
du en naken streng og må slå opp en gang til.

    ## 2026-09-16 — Laget sorteres etter rolle, ikke etter når radene ble laget  `#vaktliste/roller`

**App-halvdelen utledes, tema-halvdelen registreres.** Appen er en ekte
Django-app, så den validerer seg selv og en ny modul er dekket fra dagen den
finnes. Temaene må stå i `TEMAER` — et vokabular uten register er en håndholdt
liste, og de forfaller i stillhet: `#vaktliste/planlegger` og
`#vaktliste/planlegging` ville vært to temaer ingen la merke til at var ett.

**Historikken er ikke merket, og blir det ikke av seg selv.** `manage.py
changelog` uten argumenter skriver ut alle titlene — én linje per entry mot
11 651 — og dekker halen til den som leter i fortida. `--umerkede` sier hvor
mange som gjenstår. Søkeord settes framover, og bakover når noen først er inne
i en entry.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

#: `## 2026-09-16 — Tittel  `#vaktliste/roller` `#vaktliste/registre``
OVERSKRIFT = re.compile(r'^## (\d{4}-\d{2}-\d{2}) — (.+?)\s*((?:`#[a-z_]+/[a-z-]+`\s*)*)$')
SOKEORD = re.compile(r'`#([a-z_]+)/([a-z-]+)`')

#: Temaene hver modul kan merke en entry med, og hva de dekker.
#:
#: **Registrert, ikke gjettet** — samme grunn som `PAASTANDER` i
#: dokumentråte-testen: et mønster som godtok hva som helst ville sluppet
#: gjennom skrivefeilen det finnes for å fange. Hver rad er et bevisst valg om
#: at akkurat det temaet er verdt å kunne ramse opp.
#:
#: **Grovt, ikke fint.** Et tema som treffer to entries er ikke et tema, det er
#: en tittel — og et vokabular med femti navn er et vokabular ingen husker, så
#: folk finner på nye. Regn med en håndfull per modul.
#:
#: **Lista vokser med merkingen, ikke foran den.** Første utkast hadde tjue
#: temaer og fire i bruk, og `--temaer` ville da vist seksten rader med null. Det er verre enn en kort liste: et søkeord som
#: svarer med ett treff der det finnes fem, får deg til å tro du har sett alt.
#: Samme feilklasse som en skanner som melder grønt om en dekning den ikke har.
#: `test_hvert_registrert_sokeord_er_i_bruk` håndhever rekkefølgen: merk
#: entriene først, registrer temaet i samme commit.
TEMAER: dict[str, dict[str, str]] = {
    'core': {
        'audit': 'auditlogg, hva som logges og hva som med vilje ikke gjør det',
        'backup': 'handlere, planen, klokka, offsite, gjenoppretting',
        'dokumentasjon': 'CLAUDE.md, TODO, CHANGELOG, vaktene rundt dem',
        'drift': 'Railway, cron, server-status, sesjoner, flyttingen til `core`',
        'sikkerhet': 'gjennomgangene, rate-limiting, CSP, hodene',
        'tilgang': 'ModulTilgang, nivåstigen, dekoratørene, superbrukeren',
    },
    'backlog': {
        'modulen': 'innspill, angrefristen, løst-flagget, filteret',
    },
    'ko': {
        'skallet': 'modulen, tilgangen, flatene, sidebaren',
        'loggen': 'logglinjer, retting, sletteinngangen, systemhendelsene som løftes inn',
        'ressursbildet': 'tavla: projeksjonen av vaktliste + oppdrag + KO-ført status',
        'sentralbordet': 'sentralbordet flyttet inn i /ko/, delingen og gatene',
        'hendelseslogg': 'hendelsesloggen som egen flate: prioritet, bli med, festing, lagene på hendelsen, beskrivelsen som tillegg, melder',
        'oppsett': '2×2-rutenettet: bytte plass, skillelinjer, oppsettet i localStorage',
    },
    'oppdrag': {
        'enhetsskjerm': 'bilens side, offline-køen, lydvarselet',
        'sentralbord': 'operatørens side, oppdragslista, tidslinja',
        'statusmaskin': 'overganger, stemplinger, passiv vakt, avvente',
    },
    'vaktliste': {
        'belastning': 'timer, budsjett, tak, hvile, timeoversikt',
        'offline': 'service worker, køen, fil på e-post, reserven',
        'planlegging': 'skift, plasser, ressurser, dagbolker, utskrift, planleggeren',
        'roller': 'Ressursrolle, Ressursgruppe, kompetanser, rekkefølge',
        'tilgang': 'badgen, reservasjonen, korpsfilteret, hvem får røre hva',
    },
}


def _tekst() -> str:
    return (Path(settings.BASE_DIR) / 'CHANGELOG.md').read_text(encoding='utf-8')


def entries() -> list[dict]:
    """[{dato, tittel, sokeord, linje}, ...] for hver entry i CHANGELOG."""
    ut = []
    for nr, linje in enumerate(_tekst().split('\n'), 1):
        m = OVERSKRIFT.match(linje)
        if not m:
            continue
        dato, tittel, hale = m.groups()
        ut.append({
            'dato': dato,
            'tittel': tittel.strip(),
            'sokeord': [f'{a}/{t}' for a, t in SOKEORD.findall(hale or '')],
            'linje': nr,
        })
    return ut


def sokeord_i_bruk() -> set[str]:
    return {s for e in entries() for s in e['sokeord']}


def registrerte() -> set[str]:
    return {f'{app}/{tema}' for app, temaer in TEMAER.items() for tema in temaer}


def ukjente() -> dict[str, list[str]]:
    """{søkeord: [titlene som bruker det]} for søkeord utenfor registeret."""
    kjent = registrerte()
    ut: dict[str, list[str]] = {}
    for e in entries():
        for s in e['sokeord']:
            if s not in kjent:
                ut.setdefault(s, []).append(f"{e['dato']} — {e['tittel']}")
    return ut


def ubrukte() -> list[str]:
    """Registrerte søkeord ingen entry bruker — dødt vokabular."""
    return sorted(registrerte() - sokeord_i_bruk())


def finn(sokeord: str | None = None, app: str | None = None) -> list[dict]:
    """Entries merket med søkeordet, eller med noe fra appen."""
    ut = entries()
    if sokeord:
        ut = [e for e in ut if sokeord in e['sokeord']]
    if app:
        ut = [e for e in ut if any(s.startswith(f'{app}/') for s in e['sokeord'])]
    return ut
