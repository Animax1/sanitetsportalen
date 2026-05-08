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
        fields = ['enabled', 'backup_enabled', 'note']
        widgets = {
            'enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'backup_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'note': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Valgfritt — f.eks. "Deaktivert pga. driftsavbrudd"',
                'maxlength': 255,
            }),
        }
        labels = {
            'enabled': 'Aktivert',
            'backup_enabled': 'Inkluder i backup',
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


class ModuleBackupConfigForm(forms.ModelForm):
    """Skjema for ModuleBackupConfig — admin redigerer interval/cap/enabled."""

    class Meta:
        from core.models import ModuleBackupConfig as _MBC
        model = _MBC
        fields = ['enabled', 'interval_minutes', 'max_backups']
        widgets = {
            'enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'interval_minutes': forms.Select(attrs={'class': 'form-select'}),
            'max_backups': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 1000,
                'step': 1,
            }),
        }
        labels = {
            'enabled': 'Automatisk backup aktivert',
            'interval_minutes': 'Backup-intervall',
            'max_backups': 'Maks antall backuper',
        }
        help_texts = {
            'enabled': (
                'Hvis avkrysset kjøres backup automatisk på intervallet under. '
                'Hvis ikke avkrysset må admin starte backup manuelt.'
            ),
            'max_backups': (
                'Eldste backuper slettes når dette antallet overstiges. '
                'Pre-restore-snapshots telles ikke.'
            ),
        }

    def clean_max_backups(self):
        value = self.cleaned_data['max_backups']
        if value < 1:
            raise forms.ValidationError(
                'Maks antall backuper må være minst 1.'
            )
        if value > 1000:
            raise forms.ValidationError(
                'Maks antall backuper kan ikke overstige 1000.'
            )
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
