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
