"""Løpende posisjon fra bilene, og «Hent posisjon» fra KO (19. okt. 2026).

`docs/PLAN_LOPENDE_POSISJON.md`. André: «Fra en går inn på /oppdrag/ så skal
oppdateres hver 5 min og på haste og akutt oppdrag så skal det være hver 30
sekund. Og så må KO kunne hente posisjon … på enkelt ressurs og alle
ressurser.» Grunnlaget er berettiget interesse (personverndokumentet A.6).

**Regelen står her og ingen andre steder.** Serveren regner ut intervallet og
sender det til bilen i en header på pollet (`X-Posisjon-Intervall`), og den
samme funksjonen er bremsen når bilen sender. En kopi i JavaScript ville vært
en regel som kunne gli fra bremsen — og da ville bilen enten sendt oftere enn
serveren tok imot, eller sjeldnere enn admin bestemte, uten at noe var rødt.

Fire regler:

- **Av som standard.** Hovedbryteren (`oppdrag_posisjon_lopende`) er av til
  admin slår den på, og av betyr «slik det var»: posisjon bare ved stempling og
  «Send posisjon». Den slår av «Hent posisjon» også.
- **Intervallet følger det bilen har påbegynt**, aldri det hun bare er varslet
  på. Flere påbegynte: det korteste vinner. Ingen påbegynte: «uten oppdrag».
  0 sekunder er «ikke løpende i denne tilstanden».
- **Passiv vakt sender ikke løpende** (André, 19. okt. 2026), med mindre bilen
  har rykket ut på et oppdrag som ikke er Plassering.
- **Ingen koordinater i portalen.** Det som lagres på `Enhet` er *når* KO ba
  om posisjonen, hvem, og når den kom fram til kartet — aldri hvor.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.dispatch import Signal
from django.utils import timezone

from core import kartkobling

from . import choices

AKTIV_NOKKEL = 'oppdrag_posisjon_lopende'
UTEN_OPPDRAG = 'uten'
#: Rekkefølgen er skjemaets og bilskjermens.
TILSTANDER: tuple[str, ...] = (*choices.HASTEGRAD, UTEN_OPPDRAG)
#: Andrés tall: akutt og haster hvert 30. sekund, alt annet hvert 5. minutt.
STANDARD: dict[str, int] = {'Akutt': 30, 'Haster': 30, 'Vanlig': 300, choices.DRIFT: 300,
                            choices.PLASSERING: 300, UTEN_OPPDRAG: 300}
MIN_S = 15
MAKS_S = 3600

#: Hvor lenge en forespørsel fra KO står åpen. Bilen poller hvert 15. sekund;
#: en skjerm som ikke har svart på to minutter, er ikke på siden.
HENT_FRIST = timedelta(minutes=2)

#: «Hent posisjon» i KO-loggen (C3, André: «jeg vil ha det logget»). Sendes med
#: `enheter` (liste), `bruker` og `alle` (bool). Et signal og ikke et kall, fordi
#: oppdragsmodulen ikke får kjenne KO; KO lytter (`ko/signals.py`).
posisjon_hentet = Signal()


#: Alle sekundene i **én** nøkkel, som JSON. Seks nøkler ville vært opptil tolv
#: spørringer på hvert poll fra hver bil (hvert 15. sekund) for å lese tall som
#: endres et par ganger i året. Auditraden viser hele objektet før og etter.
SEKUNDER_NOKKEL = 'oppdrag_posisjon_sekunder'


def lopende_aktiv() -> bool:
    from core.models import AppSetting
    return AppSetting.get_i_portal(AKTIV_NOKKEL, '0') == '1'


def _les_sekunder(raa, standard: int) -> int:
    """0 er «av i denne tilstanden»; ellers klemt til grensene. Søppel gir standard."""
    try:
        verdi = int(str(raa).strip())
    except (TypeError, ValueError):
        return standard
    if verdi <= 0:
        return 0
    return min(max(verdi, MIN_S), MAKS_S)


def sekunder() -> dict[str, int]:
    """{tilstand: sekunder} — én verdi per tilstand, alltid alle. En tilstand
    som mangler eller er søppel, får standarden; ødelagt JSON gir alle standard."""
    from core.models import AppSetting
    try:
        lagret = json.loads(AppSetting.get_i_portal(SEKUNDER_NOKKEL, '{}') or '{}')
    except (TypeError, ValueError):
        lagret = {}
    if not isinstance(lagret, dict):
        lagret = {}
    return {t: _les_sekunder(lagret.get(t, STANDARD[t]), STANDARD[t]) for t in TILSTANDER}


def innstillinger() -> dict:
    """Til `bilinnstillinger()`: skjemaet og linja på bilskjermen."""
    return {'aktiv': lopende_aktiv(), 'sekunder': sekunder(), 'min': MIN_S, 'maks': MAKS_S}


def valider(data) -> tuple[dict | None, str | None]:
    """``(nye, None)`` eller ``(None, feiltekst)`` for `{"aktiv", "sekunder"}`.

    Ingenting lagres her: viewet validerer alt før noe skrives, så en ugyldig
    verdi i ett felt ikke etterlater halvparten av skjemaet lagret.
    """
    if not isinstance(data, dict) or not set(data) <= {'aktiv', 'sekunder'}:
        return None, 'Send `posisjon` som {"aktiv": true/false, "sekunder": {…}}.'
    nye: dict = {}
    if 'aktiv' in data:
        nye['aktiv'] = bool(data['aktiv'])
    sek = data.get('sekunder', {})
    if not isinstance(sek, dict):
        return None, 'Send `sekunder` som {tilstand: sekunder}.'
    for tilstand, verdi in sek.items():
        if tilstand not in TILSTANDER:
            return None, f'Ukjent tilstand «{tilstand}».'
        if isinstance(verdi, bool) or not isinstance(verdi, int):
            return None, f'{_navn(tilstand)}: send hele sekunder.'
        if verdi != 0 and not (MIN_S <= verdi <= MAKS_S):
            return None, (f'{_navn(tilstand)}: {MIN_S}–{MAKS_S} sekunder, '
                          'eller 0 for ikke løpende.')
        nye.setdefault('sekunder', {})[tilstand] = verdi
    return nye, None


def lagre(nye: dict) -> None:
    """Skriv det `valider` godtok. Hver nøkkel auditlogges av `core/signals.py`."""
    from core.models import AppSetting
    if 'aktiv' in nye:
        AppSetting.set_i_portal(AKTIV_NOKKEL, '1' if nye['aktiv'] else '0')
    if nye.get('sekunder'):
        AppSetting.set_i_portal(SEKUNDER_NOKKEL, json.dumps({**sekunder(), **nye['sekunder']}))


def intervall_tekst(sekunder: int) -> str:
    """«hvert 30. sekund», «hvert 5. minutt», «ikke løpende» — samme ord som bilskjermen."""
    if sekunder <= 0:
        return 'ikke løpende'
    if sekunder % 60 == 0:
        return 'hvert minutt' if sekunder == 60 else f'hvert {sekunder // 60}. minutt'
    return f'hvert {sekunder}. sekund'


def personvern_kontekst() -> dict:
    """Til `/personvern/` (`core/personvern.py`): om løpende posisjon er på, og
    intervallet per tilstand — fra innstillingene, så erklæringen aldri oppgir et
    tall admin har flyttet."""
    tall = sekunder()
    return {'lopende_posisjon': {
        'aktiv': lopende_aktiv(),
        'rader': [(_navn(t), intervall_tekst(tall[t])) for t in TILSTANDER],
    }}


def _navn(tilstand: str) -> str:
    return 'Uten oppdrag' if tilstand == UTEN_OPPDRAG else tilstand


def pabegynte_hastegrader(enhet, vakt) -> list[str]:
    """Hastegraden på hvert oppdrag bilen har påbegynt — rykket ut og ikke
    ledig, samme betydning som `services.aktiv_koblingsrad`."""
    from .models import Oppdragsenhet
    qs = (Oppdragsenhet.objects.filter(enhet=enhet)
          .exclude(status__in=(choices.VENTER, choices.LEDIG)))
    if vakt is not None:
        qs = qs.filter(oppdrag__vakt=vakt)
    return list(qs.values_list('oppdrag__hastegrad', flat=True))


def intervall_for(enhet, vakt) -> int | None:
    """Sekunder mellom hver løpende posisjon fra bilen nå, eller ``None``.

    ``None`` når det ikke skal sendes løpende: bryteren av, bilen av vakt, i
    passiv vakt uten et påbegynt oppdrag som teller, eller 0 for tilstanden.
    """
    if not lopende_aktiv() or not enhet.pa_vakt:
        return None
    from .services import gjeldende_modus
    from .models import Vaktmodusperiode
    hastegrader = pabegynte_hastegrader(enhet, vakt)
    if gjeldende_modus(enhet) == Vaktmodusperiode.PASSIV:
        # «med mindre de har fått et oppdrag de har trykket rykker ut på som
        # ikke er plassering» — Akutt, Haster, Vanlig og Drift.
        hastegrader = [h for h in hastegrader if h != choices.PLASSERING]
        if not hastegrader:
            return None
    tabell = sekunder()
    kandidater = [tabell.get(h, 0) for h in hastegrader] if hastegrader else [tabell[UTEN_OPPDRAG]]
    kandidater = [s for s in kandidater if s > 0]
    return min(kandidater) if kandidater else None


def bremse_s(intervall: int) -> int:
    """Hvor lenge serveren avviser en ny løpende sending fra samme bil. Under
    intervallet, så en klokke som går litt fort eller et poll som kommer sent
    ikke avvises; aldri under 10 s."""
    return max(10, int(intervall * 0.8))


# ── «Hent posisjon» fra KO ───────────────────────────────────────────────────

def hindring(enhet, *, lopende: bool | None = None) -> str | None:
    """Hvorfor KO ikke kan hente posisjonen fra bilen nå, eller ``None``.

    «Ikke hørt fra bilskjermen» (`ukjent`) er **ingen** hindring: den kan være
    på siden uten å ha meldt seg, og svaret står på kortet (André: «det er
    risiko at bilens mobil/nettbrett ikke er på nettsiden»). De tre ordene der
    bilen selv har sagt at den ikke kan, er det.
    """
    if not kartkobling.er_konfigurert():
        return 'Kartkoblingen er ikke satt opp.'
    if not (lopende_aktiv() if lopende is None else lopende):
        return 'Løpende posisjon er slått av i bilinnstillingene.'
    if not enhet.er_aktiv or not enhet.pa_vakt:
        return f'{enhet.navn} er ikke på vakt.'
    if enhet.user_id is None:
        return f'{enhet.navn} har ingen bilskjerm å spørre.'
    if enhet.posisjonsdeling == choices.POSISJONSDELING_AV:
        return f'{enhet.navn} har slått av deling av posisjon.'
    if enhet.posisjonsdeling in (choices.POSISJONSDELING_NEKTET, choices.POSISJONSDELING_UTILGJENGELIG):
        return f'{enhet.navn} kan ikke dele posisjon — se ikonet på kortet.'
    return None


def kan_hentes(enhet, *, lopende: bool | None = None) -> bool:
    """Til enhetskortet: skal «Hent posisjon» tilbys? `lopende` sendes inn av den
    som tegner mange kort, så innstillingen leses én gang per liste."""
    return hindring(enhet, lopende=lopende) is None


def be_om(enhet, bruker, *, naa=None) -> None:
    """Merk at KO vil ha posisjonen. Bilen ser det på neste poll."""
    enhet.posisjon_bedt_at = naa or timezone.now()
    enhet.posisjon_bedt_av = getattr(bruker, 'username', '') or ''
    enhet.save(update_fields=['posisjon_bedt_at', 'posisjon_bedt_av'])


def er_onsket(enhet, naa=None) -> bool:
    """Står en forespørsel fra KO åpen? Innenfor fristen, og ikke besvart."""
    bedt = enhet.posisjon_bedt_at
    if bedt is None:
        return False
    if (naa or timezone.now()) - bedt > HENT_FRIST:
        return False
    mottatt = enhet.posisjon_mottatt_at
    return mottatt is None or mottatt < bedt


def noter_mottatt(enhet, naa=None) -> None:
    enhet.posisjon_mottatt_at = naa or timezone.now()
    enhet.save(update_fields=['posisjon_mottatt_at'])
