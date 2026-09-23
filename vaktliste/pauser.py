"""Avtalte pauser i vaktlista (André, 22.–23. sep. 2026).

«vi har planer om å hente avtalte pauser fra /vaktliste som er en funksjon som
ikke er lagt inn enda». Svarene som styrer konstruksjonen, 23. sep.:

- **Per lag/ressurs**, ikke per person — tavla flytter lag.
- **Teller i timene** — ingenting her rører budsjettet eller belastningen.
- **Lederen** legger dem inn (`kan_lede`), som planleggeren.
- **Mannskapet ser dem** på utskriften og i fila på e-post, men admin kan
  skjule dem der (`VIS_NOKKEL`).
- **Regelen i planleggeren kommer nå** — `regelpause()`.

Egen fil og ikke i `services.py`, som alt er lang: pausene er én ting med
sine egne regler, og de leses også av KO (`ko.tavle`), som ikke skal måtte
kjenne resten av vaktlistas tjenester for å finne dem.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Pause

#: Samme tak som KOs planlagte pauser (`ko.tavle.MAKS_PAUSE`): lengre enn
#: dette er nesten sikkert en skrivefeil i klokkeslettet.
MAKS_PAUSE = timedelta(hours=4)

#: Planleggerregelens grenser, i minutter.
MIN_LENGDE_MIN = 5
MAKS_LENGDE_MIN = int(MAKS_PAUSE.total_seconds() // 60)
MAKS_ETTER_MIN = 24 * 60

#: Portalinnstillingen: skal pausene stå på utskriften og i fila på e-post?
#: André: «ja men admin kan skjule det i innstillinger». Standard er ja.
VIS_NOKKEL = 'vaktliste_vis_pauser'


class Ugyldig(ValueError):
    """Pausen lar seg ikke lagre. Meldingen går til brukeren."""


def vises_for_mannskapet() -> bool:
    """Står pausene på utskriften og i fila? Leses på hvert kall — en
    innstilling admin nettopp endret, skal gjelde neste utskrift."""
    from core.models import AppSetting
    return AppSetting.get(VIS_NOKKEL, '1') != '0'


def _klokke(t) -> str:
    return timezone.localtime(t).strftime('%H:%M')


def _slaa_sammen(intervaller):
    """Intervallene slått sammen der de overlapper eller møtes — et lag med
    skift 14–22 og 22–06 er på vakt 14–06."""
    ut = []
    for fra, til in sorted(intervaller):
        if ut and fra <= ut[-1][1]:
            ut[-1] = (ut[-1][0], max(ut[-1][1], til))
        else:
            ut.append((fra, til))
    return ut


def skiftspenn(ressurs):
    """Tida ressursen har skift, som sammenslåtte `(fra, til)`.

    **Alle plassene teller, også de ledige.** Pausen gjelder laget, og laget
    er satt opp for den tida uansett om alle navnene er fylt inn ennå.
    """
    return _slaa_sammen(
        (vp.fra_tid, vp.til_tid) for vp in ressurs.vaktposter.all()
        if vp.fra_tid and vp.til_tid and vp.til_tid > vp.fra_tid)


def valider(ressurs, fra, til, *, pause=None) -> None:
    """Kaster `Ugyldig` med en melding brukeren kan handle på.

    Tre regler, de samme som KOs pauser har: **innenfor skiftene**, **høyst
    fire timer**, og **aldri to over hverandre** på samme ressurs.
    """
    if fra is None or til is None:
        raise Ugyldig('Pausen må ha både fra og til.')
    if til <= fra:
        raise Ugyldig('«Til» må være etter «fra».')
    if til - fra > MAKS_PAUSE:
        raise Ugyldig('En pause kan ikke være lengre enn fire timer.')
    if not any(a <= fra and til <= b for a, b in skiftspenn(ressurs)):
        raise Ugyldig(f'Pausen må ligge innenfor skiftene til {ressurs.navn}.')
    andre = Pause.objects.filter(ressurs=ressurs, fra__lt=til, til__gt=fra)
    if pause is not None:
        andre = andre.exclude(pk=pause.pk)
    kollisjon = andre.first()
    if kollisjon is not None:
        raise Ugyldig(f'{ressurs.navn} har alt en pause '
                      f'{_klokke(kollisjon.fra)}–{_klokke(kollisjon.til)}.')


@transaction.atomic
def lagre(ressurs, fra, til, *, pause=None) -> Pause:
    """Ny pause, eller `pause` flyttet.

    **En regelpause som rettes for hånd, blir lederens** (`fra_regel=False`):
    ellers ville neste generering i planleggeren lagt den tilbake der regelen
    sa, og rettelsen var borte uten at noen gjorde noe.
    """
    # Låsen på ressursen gjør overlappsjekken og skrivingen til én handling:
    # to ledere som legger inn hver sin pause samtidig, skal ikke begge slippe
    # gjennom sjekken.
    type(ressurs).objects.select_for_update().filter(pk=ressurs.pk).first()
    valider(ressurs, fra, til, pause=pause)
    if pause is None:
        return Pause.objects.create(ressurs=ressurs, fra=fra, til=til)
    pause.fra, pause.til, pause.fra_regel = fra, til, False
    pause.save(update_fields=['fra', 'til', 'fra_regel', 'updated_at'])
    return pause


def slett(pause) -> None:
    pause.delete()


def til_dict(p) -> dict:
    return {
        'id': p.pk,
        'ressurs_id': p.ressurs_id,
        'fra': p.fra.isoformat(),
        'til': p.til.isoformat(),
        'fra_regel': p.fra_regel,
    }


# ── Regelen i planleggeren ────────────────────────────────────────────────────

def les_regel(linje) -> tuple[int, int, bool] | None:
    """`(etter_min, lengde_min, forskyv)` fra en planleggerlinje, eller `None`.

    **Begge feltene tomme er «ingen regel»; ett av dem er en feil.** En
    lengde uten «etter» ville ellers stille blitt pause ved skiftstart.
    """
    from .services import Planleggerfeil

    etter, lengde = linje.get('pause_etter_min'), linje.get('pause_min')
    if etter in (None, '') and lengde in (None, ''):
        return None
    if etter in (None, '') or lengde in (None, ''):
        raise Planleggerfeil('Pauseregelen trenger både lengde og når den kommer.')
    try:
        etter, lengde = int(etter), int(lengde)
    except (TypeError, ValueError):
        raise Planleggerfeil('Pauseregelen må være hele minutter.') from None
    if not MIN_LENGDE_MIN <= lengde <= MAKS_LENGDE_MIN:
        raise Planleggerfeil(
            f'En pause må vare mellom {MIN_LENGDE_MIN} minutter og fire timer.')
    if not 0 <= etter <= MAKS_ETTER_MIN:
        raise Planleggerfeil('Pausen må komme innen et døgn etter skiftstart.')
    return etter, lengde, bool(linje.get('pause_forskyv', True))


def regelpause(fra, til, *, etter_min, lengde_min, indeks=0):
    """Pausen regelen gir i skiftet `fra`–`til`, eller `None`.

    **Et skift for kort til regelen får ingen pause** — «pause etter fire
    timer» sier ingenting om et tretimersskift. **`indeks` forskyver**: lag
    nummer to i samme gruppe med samme skiftstart tar pausen etter lag
    nummer én, så ikke alle går ut samtidig (André: «det er egentlig
    kjempesmart» om dekningen; her er det samme tanke).

    Får den forskjøvne pausen ikke plass før skiftet slutter, er det en feil
    og ikke en stille utelatelse — et lag som mangler pausen sin er noe
    lederen må få vite.
    """
    from .services import Planleggerfeil

    lengde = timedelta(minutes=lengde_min)
    etter = timedelta(minutes=etter_min)
    if til - fra < etter + lengde:
        return None
    start = fra + etter + lengde * indeks
    if start + lengde > til:
        raise Planleggerfeil(
            f'Pausene får ikke plass i skiftet {_klokke(fra)}–{_klokke(til)} når de '
            f'forskyves for {indeks + 1} ressurser. Kort ned pausene, legg dem '
            f'tidligere, eller slå av forskyvningen.')
    return start, start + lengde
