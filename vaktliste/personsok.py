"""Mannskapet i personsøket på tvers av portalene (18. okt. 2026, `core/personsok.py`).

Ola som går vakt i to portaler, er to rader — begge skal med i et svar på innsyn.
Slettes bare når han ikke står på et skift eller i en overnatting: det er
dokumentasjonen av vakta. `Vaktmannskap` (registeret per vakt) går med raden.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from core.personsok import BasePersonsokHandler, Treff, register
from core.sortering import Norsk


class MannskapHandler(BasePersonsokHandler):
    slug = 'vaktliste_mannskap'
    etikett = 'Vaktliste: mannskap'

    def _sperre(self, m) -> str:
        if m.antall_skift or m.antall_netter:
            return (f'Står på {m.antall_skift} skift og {m.antall_netter} overnatting(er) — '
                    'det er vaktens dokumentasjon. Sett personen inaktiv i stedet.')
        return ''

    def _qs(self):
        from .models import Mannskap
        return (Mannskap.objects.select_related('korps', 'portal', 'user')
                .annotate(antall_skift=Count('vaktposter', distinct=True),
                          antall_netter=Count('overnattinger', distinct=True),
                          antall_vakter=Count('vakter', distinct=True)))

    def sok(self, q):
        qs = self._qs().filter(Q(navn__icontains=q) | Q(epost__icontains=q)
                               | Q(user__email__icontains=q)).order_by(Norsk('navn'), 'pk')
        return [Treff(
            pk=m.pk, navn=m.navn, portal=m.portal.navn if m.portal_id else '',
            felter=[('Korps', m.korps.navn), ('Telefon', m.telefon or '–'),
                    ('E-post', m.epost or '–'), ('ISSI', m.issi or '–'),
                    ('Konto', m.user.username if m.user_id else '–'),
                    ('Aktiv', 'Ja' if m.er_aktiv else 'Nei')],
            bruk=[f'{m.antall_skift} skift', f'{m.antall_vakter} vakter i registeret',
                  f'{m.antall_netter} overnatting(er)'],
            sperre=self._sperre(m),
        ) for m in qs]

    def slett(self, pk):
        m = self._qs().filter(pk=pk).first()
        if m is None:
            raise ValidationError('Personen finnes ikke lenger.')
        sperre = self._sperre(m)
        if sperre:
            raise ValidationError(sperre)
        navn = m.navn
        m.delete()
        return navn


def register_handlers() -> None:
    register(MannskapHandler())
