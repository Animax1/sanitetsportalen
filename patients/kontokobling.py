"""Pasientmodulens kobling mellom portalkonto og registerrad (14. sep. 2026).

Lå i `accounts/forms.py` som en direkte import av `patients.models` —
kontoappen kjente altså én modul ved navn (`docs/TEKNISK_GJELD.md` §3.1). Se
`core/kontokobling.py` for registeret.
"""
from __future__ import annotations

from django import forms

from core.kontokobling import BaseKontokoblingHandler, register


class PasientRolleForm(forms.Form):
    """Brukerens **funksjon i felt** — ikke tilgangen hens.

    Ingen / Førstehjelper / Helsepersonell. Finner eller oppretter en matchende
    oppføring i Forstehjelper/Helsepersonell-tabellen og kobler brukeren til
    den.

    **Radioen satte tidligere også `kan_redigere_pasienter`** (§7.3). Det er to
    forskjellige ting: funksjon i felt er domenedata, tilgang er autorisasjon.
    Sammenblandingen gjorde det umulig å være koblet som førstehjelper uten å
    ha tilgang — og omvendt. Tilgang settes nå i matrisen modul × nivå. To steg
    i stedet for ett, bevisst.
    """
    CHOICES = [
        ('ingen',          'Ingen funksjon'),
        ('forstehjelper',  'Førstehjelper'),
        ('helsepersonell', 'Helsepersonell'),
    ]
    pasient_rolle = forms.ChoiceField(
        choices=CHOICES,
        widget=forms.RadioSelect,
        label='',
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from patients.models import Forstehjelper, Helsepersonell
        self.user = user
        if not args and 'data' not in kwargs:
            if Forstehjelper.objects.filter(user=user).exists():
                self.fields['pasient_rolle'].initial = 'forstehjelper'
            elif Helsepersonell.objects.filter(user=user).exists():
                self.fields['pasient_rolle'].initial = 'helsepersonell'
            else:
                self.fields['pasient_rolle'].initial = 'ingen'

    def save(self):
        from django.db import transaction
        from patients.models import Forstehjelper, Helsepersonell
        rolle = self.cleaned_data['pasient_rolle']
        user = self.user
        with transaction.atomic():
            Forstehjelper.objects.filter(user=user).update(user=None)
            Helsepersonell.objects.filter(user=user).update(user=None)
            if rolle == 'forstehjelper':
                f = (
                    Forstehjelper.objects.filter(name=user.username).first()
                    or Forstehjelper(name=user.username)
                )
                f.user = user
                f.save()
            elif rolle == 'helsepersonell':
                h = (
                    Helsepersonell.objects.filter(name=user.username).first()
                    or Helsepersonell(name=user.username)
                )
                h.user = user
                h.save()


class PasientKontokobling(BaseKontokoblingHandler):
    slug = 'patients'
    order = 10
    handling = 'link_patient_role'
    mal = 'patients/kontokobling.html'
    suksessmelding = 'Pasient-rolle oppdatert.'

    def skjema(self, user, data=None):
        return PasientRolleForm(user, data) if data is not None \
            else PasientRolleForm(user)


def register_handlers() -> None:
    register(PasientKontokobling())
