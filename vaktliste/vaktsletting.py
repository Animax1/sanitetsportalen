"""Vaktlista når en tidligere vakt slettes (`core/vaktsletting.py`).

Sist: lagenes registreringer peker på ressursene. Ressursene og skiftene går med
vaktlista; mannskapet, korpsene og kompetansene er ikke vaktas og står.
"""
from __future__ import annotations

from core.vaktsletting import BaseVaktslettHandler, register


class VaktlisteVaktsletting(BaseVaktslettHandler):
    slug = 'vaktliste'
    order = 50
    # `Vaktmannskap` (18. okt. 2026) går med vakta (CASCADE): registeret til en vakt
    # som slettes, er ingenting å ta vare på — personene står i portalen.
    modeller = ('vaktliste.Vaktliste', 'vaktliste.Vaktmannskap')

    def antall(self, vakt):
        from .models import Vaktliste, Vaktpost
        return [('vaktlister', Vaktliste.objects.filter(vakt=vakt).count()),
                ('skift', Vaktpost.objects.filter(ressurs__vaktliste__vakt=vakt).count())]

    def slett(self, vakt) -> None:
        from .models import Vaktliste
        Vaktliste.objects.filter(vakt=vakt).delete()


def register_handlers() -> None:
    register(VaktlisteVaktsletting())
