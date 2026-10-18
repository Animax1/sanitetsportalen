"""Oppdragsmodulens frie felt i sladdingen (`core/sladding.py`, fase 7, 18. okt. 2026).

`Oppdrag.fritekst` og «Annet sted: …» (`Statusmelding.sted_tekst`) — de samme to som
`fritekstfrist.py` tømmer etter tre dager. Sladdingen er for teksten som ikke kan vente på
fristen, og for den en gjenoppretting tar tilbake. Ingen av dem står i arkivet eller i den
frosne statistikken (`arkiv.py`, `statistikk.py`), så det er ingen kopi å sladde der.

**«Annet sted» arves av en korreksjon**, så samme tekst står på flere meldinger: en sladding
tar alle på oppdraget med den teksten.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.sladding import BaseSladdHandler, Funn

OPPDRAG = 'oppdrag.oppdrag'
STATUSMELDING = 'oppdrag.statusmelding'


def _hvor(oppdrag) -> str:
    from .services import oppdragsnr

    deler = [oppdragsnr(oppdrag.oppdragsnummer)]
    if oppdrag.vakt_id:
        deler.append(oppdrag.vakt.navn)
        if oppdrag.vakt.portal_id:
            deler.append(oppdrag.vakt.portal.navn)
    return ' · '.join(deler)


class OppdragSladdHandler(BaseSladdHandler):
    slug = 'oppdrag'
    etikett = 'Oppdrag'
    felt = {OPPDRAG: ('fritekst',), STATUSMELDING: ('sted_tekst',)}

    def sok(self, q):
        from .models import Oppdrag, Statusmelding

        funn = [Funn(OPPDRAG, o.pk, 'fritekst', 'Oppdragsnotat', o.fritekst, _hvor(o), o.created_at)
                for o in (Oppdrag.objects.filter(fritekst__icontains=q)
                          .select_related('vakt__portal').order_by('-created_at'))]
        sett = set()
        for m in (Statusmelding.objects.filter(sted_tekst__icontains=q)
                  .select_related('oppdrag__vakt__portal').order_by('-created_at')):
            # Én rad per tekst og oppdrag: korreksjonene arver teksten.
            if (m.oppdrag_id, m.sted_tekst) in sett:
                continue
            sett.add((m.oppdrag_id, m.sted_tekst))
            funn.append(Funn(STATUSMELDING, m.pk, 'sted_tekst', '«Annet sted»', m.sted_tekst,
                             _hvor(m.oppdrag), m.created_at))
        return funn

    def sladd(self, modell, pk, felt, *, bruker):
        from .models import Oppdrag, Statusmelding

        if modell == OPPDRAG:
            oppdrag = Oppdrag.objects.filter(pk=pk).first()
            if oppdrag is None:
                raise ValidationError('Oppdraget finnes ikke.')
            _tom_notat(oppdrag)
            return [(OPPDRAG, pk, 'fritekst')]
        melding = Statusmelding.objects.filter(pk=pk).first()
        if melding is None:
            raise ValidationError('Meldingen finnes ikke.')
        like = list(Statusmelding.objects.filter(oppdrag_id=melding.oppdrag_id,
                                                 sted_tekst=melding.sted_tekst)
                    .values_list('pk', flat=True)) if melding.sted_tekst else [melding.pk]
        _tom_sted(like)
        return [(STATUSMELDING, p, 'sted_tekst') for p in like]

    def gjenta(self, rad):
        from .models import Oppdrag, Statusmelding

        if rad.modell == OPPDRAG:
            oppdrag = Oppdrag.objects.filter(pk=rad.rad_id).first()
            if oppdrag is None:
                return False
            _tom_notat(oppdrag)
            return True
        return bool(_tom_sted([rad.rad_id]))


def _tom_notat(oppdrag) -> None:
    # `save()` og ikke `update()`: audit fører at notatet ble endret (uten verdier,
    # `signals.FELT_UTEN_VERDILOGGING`), og endringsnummeret får sentralbordet til å hente.
    if oppdrag.fritekst:
        oppdrag.fritekst = ''
        oppdrag.save(update_fields=['fritekst', 'updated_at'])


def _tom_sted(pks) -> int:
    # `update()` går utenom signalene, så endringsnummeret økes her — som feiingen i
    # `fritekstfrist.py` gjør. Ellers viser sentralbordet «Annet sted» til neste endring.
    from .endringer import oppdrag_endret
    from .models import Statusmelding

    antall = Statusmelding.objects.filter(pk__in=pks).update(sted_tekst='')
    if antall:
        oppdrag_endret()
    return antall


def register_handlers() -> None:
    from core import sladding

    sladding.register(OppdragSladdHandler())
