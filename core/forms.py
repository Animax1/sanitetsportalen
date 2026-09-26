"""Forms for core-appen (Sanitetsportal).

Inneholder:
- ``ModuleSettingsForm``: redigering av enkelt-modul-instillinger.
"""
from __future__ import annotations

from django import forms

from core.models import ModuleSettings


class ModuleSettingsForm(forms.ModelForm):
    """Skjema for å redigere én ``ModuleSettings``-rad.

    Brukes på ``/portal-admin/moduler/<slug>/``. ``slug`` redigeres ikke —
    den bindes til en spesifikk modul i registret og endres aldri etter
    første ``ensure_defaults_exist()``.

    Validering håndterer hovedregelen: kjernemoduler kan ikke deaktiveres.
    Det avgjøres ved å slå opp ``Module.is_core`` på modulen som matcher
    ``self.instance.slug`` — slik unngår vi at admin tilfeldigvis skrur av
    portal-skjelettet (accounts, core).
    """

    class Meta:
        model = ModuleSettings
        fields = ['enabled', 'note']
        widgets = {
            'enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'note': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Valgfritt — f.eks. "Deaktivert pga. driftsavbrudd"',
                'maxlength': 255,
            }),
        }
        labels = {
            'enabled': 'Aktivert',
            'note': 'Admin-notat',
        }

    def clean_enabled(self):
        """Hindre at kjernemoduler deaktiveres.

        Hentes fra ``core.modules``-registret. Hvis modulen ikke finnes
        i registret (rest fra tidligere kode) lar vi feltet stå —
        ``ensure_defaults_exist()`` rydder opp ved neste deploy.
        """
        # Lazy import for å unngå sirkulær import med core.modules
        from core.modules import get_module  # noqa: WPS433

        enabled = self.cleaned_data['enabled']
        modul = get_module(self.instance.slug)
        if modul and modul.is_core and not enabled:
            raise forms.ValidationError(
                f'Kjernemodulen «{modul.name}» kan ikke deaktiveres — '
                'portalen krever den for å fungere.'
            )
        return enabled


class BackupplanForm(forms.ModelForm):
    """Skjema for én backupplan — modus, intervall og cap.

    Intervallet er **to felter**, tall og enhet, og ikke et nedtrekk med faste
    valg slik det var fram til 13. sep. 2026. Det var nettopp de faste valgene
    som gjorde at «hvert 10. minutt» og «hver tredje dag» ikke fantes.

    Grensene er vide med vilje: 1 til 1000 filer, og et hvilket som helst
    positivt intervall. Konsekvensen av et tett intervall vises i
    grensesnittet som antall filer i døgnet — **varsle, ikke avvis**, som
    vaktlistas belastningstall. Den som setter fem minutter under en stor vakt,
    vet som regel hvorfor.
    """

    class Meta:
        from core.models import Backupplan as _BP
        model = _BP
        fields = ['folger_standard', 'modus', 'intervall_verdi',
                  'intervall_enhet', 'behold']
        widgets = {
            'folger_standard': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'modus': forms.Select(attrs={'class': 'form-select'}),
            'intervall_verdi': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 10000, 'step': 1,
            }),
            'intervall_enhet': forms.Select(attrs={'class': 'form-select'}),
            'behold': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 1000, 'step': 1,
            }),
        }
        labels = {
            'folger_standard': 'Følg standardplanen',
            'modus': 'Modus',
            'intervall_verdi': 'Intervall',
            'intervall_enhet': 'Enhet',
            'behold': 'Behold filer på volumet',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Standardplanen og hele databasen styrer alltid seg selv. Å vise
        # avkrysningsboksen for dem ville tilbudt et valg som ikke finnes.
        from core.models import Backupplan
        instans = kwargs.get('instance') or self.instance
        if instans is not None and instans.slug in Backupplan.EGENRÅDIGE:
            self.fields.pop('folger_standard', None)

        # `PositiveIntegerField.formfield()` setter `min_value=0`, og det
        # vinner over `min` i widgetens attrs. Uten dette lover nettleseren at
        # 0 er lov, og feltet avvises først av `clean_` — altså en tur til
        # serveren for å få vite noe skjemaet visste.
        for navn in ('intervall_verdi', 'behold'):
            if navn in self.fields:
                self.fields[navn].min_value = 1
                self.fields[navn].widget.attrs['min'] = 1

    def clean_intervall_verdi(self):
        verdi = self.cleaned_data['intervall_verdi']
        if verdi < 1:
            raise forms.ValidationError('Intervallet må være minst 1.')
        if verdi > 10000:
            raise forms.ValidationError('Intervallet kan ikke overstige 10000.')
        return verdi

    def clean_behold(self):
        value = self.cleaned_data['behold']
        if value < 1:
            raise forms.ValidationError('Antall filer må være minst 1.')
        if value > 1000:
            raise forms.ValidationError('Antall filer kan ikke overstige 1000.')
        return value


class BackupRestoreConfirmForm(forms.Form):
    """Bekreftelses-skjema før restore. Admin må skrive modul-slug eksakt."""

    confirm_slug = forms.CharField(
        max_length=64,
        label='Skriv modul-navnet for å bekrefte',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
            'autofocus': 'autofocus',
        }),
        help_text='Skriv inn slug på modulen for å bekrefte gjenopprettingen.',
    )

    def __init__(self, *args, expected_slug: str = '', **kwargs):
        super().__init__(*args, **kwargs)
        self._expected_slug = expected_slug

    def clean_confirm_slug(self):
        value = (self.cleaned_data.get('confirm_slug') or '').strip()
        if value != self._expected_slug:
            raise forms.ValidationError(
                f'Bekreftelsen må være eksakt «{self._expected_slug}».'
            )
        return value
