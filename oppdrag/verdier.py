"""Verdimengdene som bor i tabeller: problemstillinger og enhetstyper.

Til 12. sep. 2026 lå de i `choices.py`. André ville redigere lista og
rekkefølgen selv — «som i lokasjoner» — og da er kode feil sted: en endring
ble en deploy. Dette er det ene stedet som leser tabellene på vegne av
viewene, så «hvilke problemstillinger passer Drift» ikke regnes ut på tre
måter.

Regler som ikke står i tabellen:

- **«Udefinert» først, alltid.** Uansett `rekkefolge`, og uansett om noen
  har prøvd å deaktivere den — `Problemstilling.er_fast`.
- **Ukjent hastegrad gir tom liste**, ikke alt. En skrivefeil skal stenge.
- **Et oppdrag beholder problemstillingen sin** om den deaktiveres:
  `valider_problemstilling()` godtar den gjeldende verdien ved redigering
  (`gjeldende`), så en KO som retter fritekst ikke stoppes av at noen tok
  «Utstyr» ut av lista i mellomtida.
"""
from __future__ import annotations

from django.db.models.functions import Lower

from . import choices
from .models import Enhetstype, Lydvarsel, Problemstilling


def _sortert(rader):
    """Udefinert først; resten på rekkefølge, så navn."""
    return sorted(rader, key=lambda r: (0 if r.er_fast else 1, r.rekkefolge, r.navn.lower()))


def problemstillinger(*, inkluder_inaktive=False):
    qs = Problemstilling.objects.all()
    if not inkluder_inaktive:
        qs = qs.filter(er_aktiv=True)
    return _sortert(qs)


def problemstillinger_for(hastegrad: str) -> list[str]:
    """Navnene som tilbys for hastegraden, Udefinert først."""
    if hastegrad not in choices.HASTEGRAD:
        return []
    return [p.navn for p in problemstillinger() if p.passer(hastegrad)]


def problemstillinger_per_hastegrad() -> dict[str, list[str]]:
    rader = problemstillinger()
    return {h: [p.navn for p in rader if p.passer(h)] for h in choices.HASTEGRAD}


def med_antall() -> list[str]:
    """Navnene som bærer et antall."""
    return [p.navn for p in problemstillinger() if p.med_antall]


def baerer_antall(navn: str) -> bool:
    return Problemstilling.objects.filter(navn=navn, med_antall=True).exists()


def problemstilling_passer(hastegrad: str, navn: str, *, gjeldende: str | None = None) -> bool:
    """Er paret lovlig? Den gjeldende verdien på oppdraget godtas selv om
    raden er deaktivert — men bare for *den* hastegraden den passer."""
    if navn == choices.UDEFINERT:
        return hastegrad in choices.HASTEGRAD
    rad = Problemstilling.objects.filter(navn=navn).first()
    if rad is None:
        return False
    if not rad.er_aktiv and navn != gjeldende:
        return False
    return rad.passer(hastegrad)


def valider_problemstilling(data, *, gjeldende: str | None = None):
    """Normaliser og sjekk `data['problemstilling']` mot tabellen. Muterer
    ``data``. Returnerer feiltekst eller None. Feltet rørt ikke om det
    mangler — delvise oppdateringer er trygge."""
    if 'problemstilling' not in data:
        return None
    raa = data['problemstilling']
    verdi = '' if raa is None else str(raa).strip()
    data['problemstilling'] = verdi
    if verdi == choices.UDEFINERT or verdi == gjeldende:
        return None
    if not Problemstilling.objects.filter(navn=verdi, er_aktiv=True).exists():
        return f'Ugyldig verdi for «problemstilling»: {verdi!r}.'
    return None


def enhetstyper(*, inkluder_inaktive=False):
    qs = Enhetstype.objects.all()
    if not inkluder_inaktive:
        qs = qs.filter(er_aktiv=True)
    return list(qs.order_by('rekkefolge', Lower('navn')))


# ── Lydvarselet ──────────────────────────────────────────────────────────────

#: Tallene fra første utgave (André, 12. sep. 2026) — fasit til raden finnes.
LYDVARSEL_STANDARD = {'Akutt': (60, 10), 'Haster': (300, 60), 'Vanlig': (900, 60),
                      'Drift': (900, 60), 'Plassering': (900, 60)}
LYD_NYTT_NOKKEL = 'oppdrag_lyd_nytt'


def lydvarsel() -> dict[str, list[int]]:
    """{hastegrad: [første, gjenta]} i sekunder — tabellen, med standard for
    hastegrader som mangler rad."""
    rader = {r.hastegrad: [r.forste_sekunder, r.gjenta_sekunder] for r in Lydvarsel.objects.all()}
    return {h: rader.get(h, list(LYDVARSEL_STANDARD.get(h, (900, 60)))) for h in choices.HASTEGRAD}


LYD_AKTIV_NOKKEL = 'oppdrag_lyd_aktiv'
KREV_GROV_AVREIST_NOKKEL = 'oppdrag_krev_grov_avreist'


def _bryter(nokkel, standard='1') -> bool:
    from core.models import AppSetting
    return AppSetting.get(nokkel, standard) == '1'


def lydvarsel_aktive() -> dict[str, bool]:
    """{hastegrad: True/False} — om ventevarselet er på for hastegraden."""
    rader = {r.hastegrad: r.aktiv for r in Lydvarsel.objects.all()}
    return {h: rader.get(h, True) for h in choices.HASTEGRAD}


def lyd_ved_nytt_oppdrag() -> bool:
    return _bryter(LYD_NYTT_NOKKEL)


def lyd_aktiv() -> bool:
    """Lydvarselet i bilene, som helhet (André, 12. sep. 2026: «Må kunne slå
    av lydvarsel»). Av betyr stille i alle biler, uansett terskler."""
    return _bryter(LYD_AKTIV_NOKKEL)


def krev_grov_for_avreist() -> bool:
    """Om bilen må ha satt grovsortering før Avreist (André, 12. sep. 2026:
    «La det være en innstilling»). Før Behandlet på sted og før Ledig fra
    Leverer kreves den alltid — se `grov_kreves_for`."""
    return _bryter(KREV_GROV_AVREIST_NOKKEL, '0')


def bilinnstillinger() -> dict:
    return {
        'terskler': lydvarsel(),
        'aktive': lydvarsel_aktive(),
        'nytt_oppdrag': lyd_ved_nytt_oppdrag(),
        'lyd_aktiv': lyd_aktiv(),
        'krev_grov_avreist': krev_grov_for_avreist(),
    }


def grov_kreves_for(oppdrag, overgang: str, fra_status: str) -> bool:
    """Må grovsorteringen stå før bilen får gjøre denne overgangen?

    Alltid før «Behandlet på sted» og før Ledig fra Leverer (André, 12. sep.
    2026: «Må kreve at grovsortering settes før ledig ved levering som
    minimum»); før Avreist bare når innstillingen sier det. Aldri på Drift —
    der er det ingen pasient å sortere."""
    if oppdrag.hastegrad in choices.UTEN_PASIENT:
        return False
    if overgang == choices.BEHANDLET:
        return True
    if overgang == choices.LEDIG and fra_status == choices.LEVERER:
        return True
    if overgang == choices.AVREIST:
        return krev_grov_for_avreist()
    return False
