"""Pasientmodulens frie felt i sladdingen (`core/sladding.py`, fase 7, 18. okt. 2026).

**Bare arkivets notat.** De kliniske feltene er verdimengder og tidspunkter, validert av
`choices.py` og `validate_patient_time_fields` siden 12. aug. 2026 — det er ingen fritekst der
et navn kan havne. Notatet står utenfor `sha_payload()` (`arkiv.py`), så en sladding der
bryter ingen signatur.

Det som *står* i signaturen og kan bære et navn, er førstehjelperens og helsepersonellets
frosne navn på `ArkivertPasient` — frivillige, ikke pasienter. Å sladde dem krever ny
signering av arkivet, og er ikke bygget (TODO).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError

from core.sladding import BaseSladdHandler, Funn

VAKTARKIV = 'patients.vaktarkiv'


class PasientSladdHandler(BaseSladdHandler):
    slug = 'patients'
    etikett = 'Pasientarkivet'
    felt = {VAKTARKIV: ('notat',)}

    def sok(self, q):
        from .models import VaktArkiv

        return [Funn(VAKTARKIV, a.pk, 'notat', 'Arkivets notat', a.notat,
                     f'{a.tittel} · {a.arrangement_navn}', a.importert_at)
                for a in VaktArkiv.objects.filter(notat__icontains=q).order_by('-importert_at')]

    def sladd(self, modell, pk, felt, *, bruker):
        if not self._tom(pk):
            raise ValidationError('Arkivet finnes ikke.')
        return [(VAKTARKIV, pk, 'notat')]

    def gjenta(self, rad):
        return self._tom(rad.rad_id)

    @staticmethod
    def _tom(pk) -> bool:
        from .models import VaktArkiv

        arkiv = VaktArkiv.objects.filter(pk=pk).first()
        if arkiv is None:
            return False
        if arkiv.notat:
            arkiv.notat = ''
            arkiv.save(update_fields=['notat'])
        return True


def register_handlers() -> None:
    from core import sladding

    sladding.register(PasientSladdHandler())
