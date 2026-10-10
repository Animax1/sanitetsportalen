"""Slettefristen på oppdragets frie tekst (10. okt. 2026, A.12).

`Oppdrag.fritekst` og «Annet sted: …» (`Statusmelding.sted_tekst`) er de to
frie feltene i modulen, og det er der en adresse, et navn eller en
helseopplysning havner. Fram til nå ble de liggende i historikken hos KO til
noen trykket «Avslutt vakt» — et menneske som husker det. A.12 har sagt det
selv: «Restrisiko: selve feltverdien står i oppdragstabellen til oppdraget
slettes eller arkiveres.» Se `docs/NOTAT_DPIA_OG_FRITEKST.md` §8.

**Klokka går fra siste aktivitet på oppdraget** (André, 10. okt. 2026: «C, 3
dager»), ikke fra `historikk_fra`. Et oppdrag som står med «trenger ny ressurs»
kommer aldri til historikken, og ville beholdt teksten for alltid. Et oppdrag
noen arbeider med blir rørt hele tiden — hver stempling, hver endring, hver
varsling flytter klokka — så det er bare det som faktisk er glemt som tømmes.

**To regler, og begge trengs** — samme grep som `_synlig_for_bilen`:

1. **Vis-regelen:** `views_common.oppdrag_til_dict` utelater teksten straks
   fristen er passert. Da lyver aldri nedtellingen, selv om feiingen er sen —
   og den er sen: `purge_old_logs` går natt til søndag.
2. **Feiingen:** `tom_utlopte()`, kalt av `purge_old_logs` gjennom
   `oppdrag/opprydding.py`, tømmer feltene for alvor. Raden står — oppdraget
   trengs til statistikken og arkivet. `fritekst = ''` er hele operasjonen.

**Fristen fjerner ikke teksten fra backupene.** `oppdrag`-modulfila ligger 730
dager hos Scaleway og den hele fila 90. Fristen verner mot at noen leser
historikken tre måneder senere; den er ikke en sletterett, og det står i
personverndokumentet.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import DateTimeField, F, IntegerField, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Greatest

#: `AppSetting`-nøkkelen. Fristen er organisasjonens, ikke portalens — samme
#: grunn som KO-loggens oppbevaringstid (`ko/services.py`).
DAGER_NOKKEL = 'oppdrag_fritekst_frist_dager'
DAGER_STANDARD = 3
#: Under ett døgn kunne en tekst forsvinne mellom to vaktskift på et oppdrag
#: som fortsatt er i arbeid; over tretti er det ikke lenger en frist.
DAGER_MIN = 1
DAGER_MAKS = 30


def frist_dager() -> int:
    """Fristen, lest fra `AppSetting` med kodedefault.

    Klemmes ved **lesing**, ikke bare ved lagring: en verdi skrevet for hånd i
    shellet skal ikke kunne gjøre fristen til null og tømme alt med én gang.
    """
    from core.models import AppSetting

    try:
        dager = int(AppSetting.get(DAGER_NOKKEL, None))
    except (TypeError, ValueError):
        return DAGER_STANDARD
    return max(DAGER_MIN, min(DAGER_MAKS, dager))


def _siste_i(modell, felt: str):
    """Seneste `felt` blant radene som peker på oppdraget, som delspørring.

    Delspørring og ikke `Max` over en join: fem joins i samme `annotate` ganger
    radene med hverandre, og lista over oppdrag polles.
    """
    return Subquery(
        modell.objects.filter(oppdrag=OuterRef('pk')).order_by()
        .values('oppdrag').annotate(m=Max(felt)).values('m')[:1],
        output_field=DateTimeField())


def _kilder():
    """Hva som teller som aktivitet. **Én liste**, brukt av både visningen og
    feiingen — to utregninger av samme klokke ville før eller siden vist en
    nedtelling feiingen ikke holdt.

    - Statusmeldingene på `updated_at`: en ny stempling, en korreksjon og en
      tilbaketrekking. Feiingen tømmer `sted_tekst` med `update()`, som ikke
      rører `updated_at` — ellers ville feiingen startet klokka på nytt.
    - Endringene i verdiene, også notatet selv: skriver KO en ny tekst, er
      teksten ny.
    - Varslingene, enhetshendelsene (avbrutt, avventer, tatt av) og byttene.
    """
    from .models import Enhetsbytte, Enhetshendelse, Oppdragsendring, Oppdragsenhet, Statusmelding

    return (
        (Statusmelding, 'updated_at'),
        (Oppdragsendring, 'created_at'),
        (Oppdragsenhet, 'varslet_at'),
        (Enhetshendelse, 'created_at'),
        (Enhetsbytte, 'created_at'),
    )


def med_siste_aktivitet(qs, dager: int | None = None):
    """Legg `siste_aktivitet` på hvert oppdrag i `qs`.

    `Coalesce` rundt hvert ledd fordi `Greatest` gir NULL på SQLite så snart ett
    ledd er NULL — et oppdrag uten endringer ville da aldri fått noen frist.
    Oppdragets egen `updated_at` er med som nedre grense: grovsorteringen og
    antallet lagres rett på raden.
    """
    ledd = [Coalesce(_siste_i(m, f), F('created_at')) for m, f in _kilder()]
    ledd += [Coalesce(F('historikk_fra'), F('created_at')), F('updated_at'), F('created_at')]
    # Fristen følger med på hver rad: lest én gang for hele lista, ikke én
    # `AppSetting`-spørring per oppdrag (`tests_ytelse_polling`).
    dager = frist_dager() if dager is None else dager
    return qs.annotate(siste_aktivitet=Greatest(*ledd, output_field=DateTimeField()),
                       fritekst_frist_dager=Value(dager, output_field=IntegerField()))


def frist_for(oppdrag) -> tuple:
    """``(siste_aktivitet, dager)`` for ett oppdrag.

    Leser annotasjonen om lista har satt den, ellers én spørring — og
    **husker svaret på instansen**: detaljvinduet spør både for notatet og for
    tidslinjens «Annet sted», og det skal ikke koste to.
    """
    siste = getattr(oppdrag, 'siste_aktivitet', None)
    dager = getattr(oppdrag, 'fritekst_frist_dager', None)
    if siste is not None and dager is not None:
        return siste, dager
    from .models import Oppdrag

    rad = (med_siste_aktivitet(Oppdrag.objects.filter(pk=oppdrag.pk))
           .values_list('siste_aktivitet', 'fritekst_frist_dager').first())
    siste, dager = rad if rad else (None, frist_dager())
    oppdrag.siste_aktivitet, oppdrag.fritekst_frist_dager = siste, dager
    return siste, dager


def tekst_utlopt(oppdrag, naa=None) -> bool:
    """Er fristen ute for dette oppdragets frie tekst nå?"""
    from django.utils import timezone

    siste, dager = frist_for(oppdrag)
    return er_utlopt(siste, naa or timezone.now(), dager)


def slettes_at(siste, dager: int | None = None):
    """Når teksten slettes, regnet fra siste aktivitet."""
    if siste is None:
        return None
    return siste + timedelta(days=frist_dager() if dager is None else dager)


def er_utlopt(siste, naa, dager: int | None = None) -> bool:
    """Regelen. **Ved grensa er den utløpt**: `slettes_at` er tidspunktet
    teksten er borte, ikke det siste den står."""
    frist = slettes_at(siste, dager)
    return frist is not None and naa >= frist


def _utlopte(naa):
    from .models import Oppdrag

    dager = frist_dager()
    grense = naa - timedelta(days=dager)
    return (med_siste_aktivitet(Oppdrag.objects.all(), dager)
            .filter(siste_aktivitet__lte=grense)
            .filter(Q(fritekst__gt='') | Q(statusmeldinger__sted_tekst__gt=''))
            .order_by().values_list('pk', flat=True).distinct())


def antall_utlopte(naa) -> int:
    """Oppdrag med tekst som *ville* blitt tømt. Brukes av `--dry-run`."""
    return len(list(_utlopte(naa)))


def tom_utlopte(naa) -> int:
    """Tøm de frie feltene på oppdrag der fristen er ute. Returnerer antall
    oppdrag.

    `update()` og ikke `save()`: audit-signalet ville skrevet en rad per
    oppdrag med «Fritekst: (skjult)», og tidslinjen ville fått en endring
    ingen gjorde. Cron-loggen bærer antallet.
    """
    from .models import Oppdrag, Statusmelding

    with transaction.atomic():
        ider = list(_utlopte(naa))
        if not ider:
            return 0
        Oppdrag.objects.filter(pk__in=ider).exclude(fritekst='').update(fritekst='')
        Statusmelding.objects.filter(oppdrag_id__in=ider).exclude(sted_tekst='').update(sted_tekst='')
        # `update()` sender ingen signaler, så tallet sentralbordet følger må
        # meldes her (`oppdrag/tests_endringer.py`, `VURDERT`).
        from .endringer import oppdrag_endret
        oppdrag_endret()
    return len(ider)
