"""Skjemaer for brukerkontoer."""
from django import forms
from django.contrib.auth import password_validation

from .models import CustomUser, UserRole


class LoginForm(forms.Form):
    """Innloggingsskjema."""
    username = forms.CharField(
        max_length=64,
        label='Brukernavn',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autofocus': True,
            'placeholder': 'Brukernavn',
        }),
    )
    password = forms.CharField(
        label='Passord',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Passord',
        }),
    )


class ChangePasswordForm(forms.Form):
    """Skjema for å endre passord."""
    old_password = forms.CharField(
        label='Nåværende passord',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False,
    )
    new_password1 = forms.CharField(
        label='Nytt passord',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )
    new_password2 = forms.CharField(
        label='Bekreft nytt passord',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    def clean_new_password2(self):
        p1 = self.cleaned_data.get('new_password1', '')
        p2 = self.cleaned_data.get('new_password2', '')
        if not p2:
            raise forms.ValidationError('Du må bekrefte det nye passordet.')
        if p1 and p1 != p2:
            raise forms.ValidationError('Passordene stemmer ikke overens.')
        password_validation.validate_password(p2)
        return p2


class AdminUserCreateForm(forms.ModelForm):
    """Skjema for admin til å opprette ny bruker."""

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'role']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Valgfritt',
            }),
            'role': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'username': 'Brukernavn',
            'email': 'E-post (valgfritt)',
            'role': 'Rolle',
        }
        help_texts = {
            'email': 'Brukes kun som kontaktinformasjon. Kan stå tom.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False

    def clean_email(self):
        # Normaliser tom streng til None slik at NULL lagres i databasen.
        email = self.cleaned_data.get('email', '').strip()
        return email or None


class AdminUserEditForm(forms.ModelForm):
    """Skjema for admin til å redigere eksisterende bruker.

    Fra Fase 3b inkluderer skjemaet også de 5 modul-permission-flaggene som
    bestemmer hvilke moduler brukeren ser i dashboard og nav-meny. Admin har
    bypass i ``Module.is_visible_for``, så disse flaggene gjelder kun for
    ikke-admin-brukere.
    """

    class Meta:
        model = CustomUser
        fields = [
            'email', 'role', 'is_active',
            'kan_redigere_pasienter',
            'kan_redigere_vakter',
            'kan_redigere_utstyr',
            'kan_se_rapport',
            'kan_redigere_beredskap',
        ]
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Valgfritt',
            }),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'kan_redigere_pasienter': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'kan_redigere_vakter': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'kan_redigere_utstyr': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'kan_se_rapport': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'kan_redigere_beredskap': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'email': 'E-post (valgfritt)',
            'role': 'Rolle',
            'is_active': 'Aktiv konto',
            'kan_redigere_pasienter': 'Pasientregistrering',
            'kan_redigere_vakter': 'Vakter',
            'kan_redigere_utstyr': 'Utstyr',
            'kan_se_rapport': 'Rapport',
            'kan_redigere_beredskap': 'Beredskap',
        }
        help_texts = {
            'email': 'Brukes kun som kontaktinformasjon. Kan stå tom.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        return email or None
