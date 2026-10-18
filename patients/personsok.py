"""Førstehjelperne og helsepersonellet i personsøket på tvers av portalene
(18. okt. 2026, `core/personsok.py`).

Navneregistrene pasientskjemaet velger fra. En rad som står på en pasient slettes
ikke herfra — pasientjournalen er dokumentasjon, og `PROTECT` ville stoppet det uansett.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from core.personsok import BasePersonsokHandler, Treff, register
from core.sortering import Norsk


class _Navneregister(BasePersonsokHandler):
    modell_navn = ''

    def _qs(self):
        from django.apps import apps
        modell = apps.get_model('patients', self.modell_navn)
        return (modell.objects.select_related('portal', 'user')
                .annotate(antall_pasienter=Count('patients')))

    def _sperre(self, r) -> str:
        if r.antall_pasienter:
            return (f'Står på {r.antall_pasienter} pasient(er) — journalen er dokumentasjon. '
                    'Sett raden inaktiv i stedet.')
        return ''

    def sok(self, q):
        qs = self._qs().filter(Q(name__icontains=q) | Q(user__email__icontains=q)).order_by(
            Norsk('name'), 'pk')
        return [Treff(
            pk=r.pk, navn=r.name, portal=r.portal.navn if r.portal_id else '',
            felter=[('Konto', r.user.username if r.user_id else '–'),
                    ('Aktiv', 'Ja' if r.is_active else 'Nei')],
            bruk=[f'{r.antall_pasienter} pasient(er)'],
            sperre=self._sperre(r),
        ) for r in qs]

    def slett(self, pk):
        r = self._qs().filter(pk=pk).first()
        if r is None:
            raise ValidationError('Raden finnes ikke lenger.')
        sperre = self._sperre(r)
        if sperre:
            raise ValidationError(sperre)
        navn = r.name
        r.delete()
        return navn


class ForstehjelperHandler(_Navneregister):
    slug = 'patients_forstehjelper'
    etikett = 'Pasientregistrering: førstehjelpere'
    modell_navn = 'Forstehjelper'


class HelsepersonellHandler(_Navneregister):
    slug = 'patients_helsepersonell'
    etikett = 'Pasientregistrering: helsepersonell'
    modell_navn = 'Helsepersonell'


def register_handlers() -> None:
    register(ForstehjelperHandler())
    register(HelsepersonellHandler())
