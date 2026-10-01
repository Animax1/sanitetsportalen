"""Vaktlistas kort på brukersiden: hvilket korps kontoen fører (1. okt. 2026).

André: «bruker med tilgang til /vaktliste kan og bli satt på korps». Til da
fikk en konto korps bare gjennom mannskapsraden sin, og en korpsleder som ikke
selv går vakt hadde ingen vei inn. Se `models.Kontokorps` for modellen og
regelen, og `core/kontokobling.py` for registeret.

**Bare global admin** setter korpset (André, 1. okt. 2026: «Admin foreløpig»):
korpset avgjør hva `les` ser og hva `skriv_handling` fører, og brukersiden er
admins. Kan åpnes for vaktlistas ledere senere.
"""
from __future__ import annotations

from django import forms
from django.db import transaction

from core.kontokobling import BaseKontokoblingHandler, register


class KontokorpsForm(forms.Form):
    """Velg korps, eller «Ingen» for å la mannskapsraden gjelde."""

    korps = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label='Ingen — korpset følger mannskapsraden, om kontoen har en',
        label='Korps',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q

        from .models import Kontokorps, Korps, Mannskap
        self.user = user
        self.naa = Kontokorps.objects.filter(user=user).select_related('korps').first()
        # Inaktive korps tilbys ikke — men det kontoen alt fører, står i lista,
        # ellers ville skjemaet stille byttet det ut ved neste lagring.
        filter_ = Q(er_aktiv=True)
        if self.naa is not None:
            filter_ |= Q(pk=self.naa.korps_id)
        self.fields['korps'].queryset = Korps.objects.filter(filter_)
        if not args and 'data' not in kwargs:
            self.fields['korps'].initial = self.naa.korps_id if self.naa else None
        self.mannskapsrad = (Mannskap.objects.filter(user=user)
                             .select_related('korps').first())

    def clean_korps(self):
        from .models import korpskonflikt
        korps = self.cleaned_data.get('korps')
        if korps is not None:
            feil = korpskonflikt(self.user.pk, korps.pk)
            if feil:
                raise forms.ValidationError(feil)
        return korps

    def save(self):
        from .models import Kontokorps
        korps = self.cleaned_data.get('korps')
        with transaction.atomic():
            if korps is None:
                # `delete()` per rad, ikke på spørringen: auditsignalet skal fyre.
                for rad in Kontokorps.objects.filter(user=self.user):
                    rad.delete()
                return
            rad = Kontokorps.objects.filter(user=self.user).first()
            if rad is None:
                Kontokorps.objects.create(user=self.user, korps=korps)
            elif rad.korps_id != korps.pk:
                rad.korps = korps
                rad.save()


class VaktlisteKontokobling(BaseKontokoblingHandler):
    slug = 'vaktliste'
    order = 20
    handling = 'sett_vaktliste_korps'
    mal = 'vaktliste/kontokobling.html'
    suksessmelding = 'Korpset i vaktlisten er oppdatert.'

    def skjema(self, user, data=None):
        return KontokorpsForm(user, data) if data is not None else KontokorpsForm(user)


def register_handlers() -> None:
    register(VaktlisteKontokobling())
