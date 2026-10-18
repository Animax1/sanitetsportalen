"""E-post til `ADMINS` når serveren har det tungt — og når den er tilbake (18. okt. 2026).

André: «en epost varsel som sendes til meg når serveren opplever høy belastning». Betterstack
overvåker allerede utenfra og melder når portalen er **nede**; dette melder når den er **treg
og i trøbbel**, noe bare serveren selv ser. Mottaker er `ADMINS`, som feilvarslene. Ingen bjelle.

| Valg | Hvorfor |
|---|---|
| **Det brukeren merker, ikke maskinens tall** — P95-svartid, 5xx, minne mot taket, databasen | Mange raske forespørsler er en travel vakt, ikke et problem |
| **Tilstanden må vare** (`varighet_min`, 5 som standard) | Én treg forespørsel skal ikke gi e-post |
| **Én e-post når det starter, én når det er over** | Ikke én per minutt: en innboks full av like varsler blir ikke lest |
| **P95 teller bare med nok forespørsler** (`MIN_FORESPORSLER`) | I en stille time er én treg side P95 |
| **Bare tall og stier i e-posten**, gjennom `vask()` | Aldri brukere, pasienter eller innhold |
| **Tersklene er admins innstillinger** (`/admin/innstillinger/`, kortet «Belastningsvarsel») | Justeres uten deploy. Klemmes ved lesing, som fristene ellers |

**Kjøres av backup-klokkas tråd** (`core/backup/klokke.py`), hvert minutt — det er den ene
tråden web-prosessen har. Er klokka slått av (`BACKUP_KLOKKE=av`), vurderes ingenting.

**Kjent grense:** en server som er helt nede, melder ingenting. Det er Betterstacks jobb.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: `AppSetting`-nøklene, og grensene de klemmes til.
INNSTILLINGER = {
    #             nøkkel                       standard  min    maks
    'p95_ms':     ('belastning_p95_ms',        2000,     200,   60000),
    'feil_5xx':   ('belastning_feil_5xx',      5,        1,     1000),
    'minne_pst':  ('belastning_minne_prosent', 85,       50,    99),
    'varighet':   ('belastning_varighet_min',  5,        1,     60),
}
AKTIV_NOKKEL = 'belastning_aktiv'

VINDU_S = 300
#: Under så mange forespørsler i vinduet sier P95 ingenting.
MIN_FORESPORSLER = 20
TILSTAND_NOKKEL = 'belastning:tilstand'
TILSTAND_TTL_S = 7 * 24 * 3600


def terskler() -> dict:
    """De fire tersklene, klemt. Søppel gir standarden. Kaster aldri."""
    from core.models import AppSetting

    ut = {}
    for navn, (nokkel, standard, minst, mest) in INNSTILLINGER.items():
        try:
            verdi = int(str(AppSetting.get(nokkel, standard)).strip())
        except Exception:
            verdi = standard
        ut[navn] = min(max(verdi, minst), mest)
    return ut


def er_aktiv() -> bool:
    from core.models import AppSetting

    try:
        return str(AppSetting.get(AKTIV_NOKKEL, '1')).strip() not in ('0', '', 'av', 'False')
    except Exception:
        return True


@dataclass
class Maaling:
    antall: int = 0
    p95_ms: float | None = None
    feil_5xx: int = 0
    minne_pst: float | None = None
    minne_mb: float | None = None
    db_ok: bool = True
    db_ms: float | None = None
    tregeste: list = field(default_factory=list)


def _minne() -> tuple[float | None, float | None]:
    """``(prosent av taket, MB)`` for containeren — cgroup v2, så v1. ``(None, None)`` uten
    tak: utenfor en container finnes ingen grense å måle mot."""
    for brukt_fil, tak_fil in (('/sys/fs/cgroup/memory.current', '/sys/fs/cgroup/memory.max'),
                               ('/sys/fs/cgroup/memory/memory.usage_in_bytes',
                                '/sys/fs/cgroup/memory/memory.limit_in_bytes')):
        try:
            with open(brukt_fil, encoding='ascii') as f:
                brukt = int(f.read().strip())
            with open(tak_fil, encoding='ascii') as f:
                tak_raa = f.read().strip()
        except Exception:
            continue
        # «max», eller cgroup v1s «ingen grense» (et tall nær 2**63).
        if not tak_raa.isdigit() or int(tak_raa) >= 2 ** 60:
            return None, round(brukt / 2 ** 20, 1)
        return round(100 * brukt / int(tak_raa), 1), round(brukt / 2 ** 20, 1)
    return None, None


def maal() -> Maaling:
    """Tallene akkurat nå. Hver kilde fanges for seg — en feil i én skal ikke skjule de andre."""
    from core.health import maal_db
    from core.middleware import metrics_store

    m = Maaling()
    try:
        s = metrics_store.snapshot(window_seconds=VINDU_S)
        m.antall = s.get('count', 0)
        m.feil_5xx = s.get('errors_5xx', 0)
        if m.antall >= MIN_FORESPORSLER:
            m.p95_ms = s.get('p95_ms')
        m.tregeste = metrics_store.tregeste_stier(window_seconds=VINDU_S, antall=5)
    except Exception:
        logger.warning('belastning: metrikkene kunne ikke leses', exc_info=True)
    try:
        m.minne_pst, m.minne_mb = _minne()
    except Exception:
        pass
    try:
        db = maal_db()
        m.db_ok, m.db_ms = db.ok, db.ms
    except Exception:
        m.db_ok = False
    return m


def vurder(m: Maaling, t: dict) -> list[str]:
    """Hva som er over terskelen, som lesbare linjer. Tom liste: alt er normalt.

    Egen funksjon, uten tilstand og uten I/O, så regelen lar seg prøve.
    """
    over = []
    if m.p95_ms is not None and m.p95_ms > t['p95_ms']:
        over.append(f'Svartid P95 {m.p95_ms:.0f} ms (terskel {t["p95_ms"]} ms, '
                    f'{m.antall} forespørsler siste {VINDU_S // 60} min)')
    if m.feil_5xx >= t['feil_5xx']:
        over.append(f'{m.feil_5xx} serverfeil (5xx) siste {VINDU_S // 60} min '
                    f'(terskel {t["feil_5xx"]})')
    if m.minne_pst is not None and m.minne_pst >= t['minne_pst']:
        over.append(f'Minne {m.minne_pst:.0f} % av taket, {m.minne_mb:.0f} MB '
                    f'(terskel {t["minne_pst"]} %)')
    if not m.db_ok:
        over.append('Databasen svarer ikke')
    return over


def neste(tilstand: dict | None, over: list[str], naa: float, varighet_min: int):
    """``(ny tilstand, handling)`` der handlingen er ``'start'``, ``'slutt'`` eller ``None``.

    Ren funksjon — reglene for når det sendes, uten cache og uten e-post:
    - Over terskelen: husk når det begynte. Har det vart `varighet_min`, send «start» én gang.
    - Normalt igjen etter et sendt varsel: send «slutt». Uten sendt varsel: glem det stille —
      en topp som gikk over før den hadde vart, skal ikke gi noen e-post.
    """
    tilstand = dict(tilstand or {})
    if over:
        tilstand.setdefault('siden', naa)
        if not tilstand.get('varslet') and naa - tilstand['siden'] >= varighet_min * 60:
            tilstand['varslet'] = True
            return tilstand, 'start'
        return tilstand, None
    if tilstand.get('varslet'):
        return {}, 'slutt'
    return {}, None


def _send(handling: str, over: list[str], m: Maaling, tilstand: dict, naa: float) -> None:
    from django.core.mail import mail_admins

    from core.miljo import miljo
    from core.vask import vask

    prefiks = miljo()['epost']
    minutter = round((naa - tilstand.get('siden', naa)) / 60)
    if handling == 'start':
        emne = f'{prefiks}Høy belastning på portalen'
        linjer = [f'Serveren har vært over terskelen i {minutter} minutter:', '',
                  *[f'- {o}' for o in over]]
        if m.tregeste:
            linjer += ['', 'Tregeste stier (P95):',
                       *[f'- {r.get("path")}: {r.get("p95_ms")} ms ({r.get("count")} treff)'
                         for r in m.tregeste]]
        linjer += ['', 'Du får én e-post til når den er tilbake til normalt.',
                   'Detaljer: /admin/server-status/']
    else:
        emne = f'{prefiks}Belastningen er normal igjen'
        linjer = [f'Portalen er under tersklene igjen, etter omtrent {minutter} minutter.']
    try:
        mail_admins(emne, vask('\n'.join(linjer)), fail_silently=False)
    except Exception:
        # Et varsel som ikke kom fram, skal ikke ta ned klokketråden. Loggen har det.
        logger.exception('belastning: e-posten «%s» ble ikke sendt', emne)


def vurder_og_varsle(naa: float | None = None) -> str | None:
    """Ett tikk: mål, vurder, send ved behov. Returnerer handlingen. Kaster aldri.

    Tilstanden står i cachen (`TILSTAND_NOKKEL`): med flere arbeidere og Redis er den delt,
    og `cache.add` på låsnøkkelen sørger for at bare én av dem sender.
    """
    from django.core.cache import cache

    if not er_aktiv():
        return None
    naa = time.time() if naa is None else naa
    try:
        t = terskler()
        m = maal()
        over = vurder(m, t)
        tilstand = cache.get(TILSTAND_NOKKEL) or {}
        ny, handling = neste(tilstand, over, naa, t['varighet'])
        if handling and not cache.add(f'{TILSTAND_NOKKEL}:{handling}:{tilstand.get("siden")}',
                                      1, TILSTAND_TTL_S):
            return None   # en annen arbeider sendte akkurat denne
        cache.set(TILSTAND_NOKKEL, ny, TILSTAND_TTL_S)
        if handling:
            _send(handling, over, m, tilstand if handling == 'slutt' else ny, naa)
        return handling
    except Exception:
        logger.exception('belastning: vurderingen feilet')
        return None
