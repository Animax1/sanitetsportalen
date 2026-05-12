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


class UserPatientLinkForm(forms.Form):
    """Skjema for å koble en bruker til Behandler ELLER Helsepersonell.

    Fase 5: Bruker kan kobles til EN av rollene (ønsket adferd — ikke begge
    samtidig). Tom verdi i begge feltene tillates (= ingen kobling).
    Begge feltene fylt ut gir valideringsfeil.
    """
    behandler = forms.ModelChoiceField(
        queryset=None,  # Settes i __init__ for å unngå sirkulær import
        required=False,
        label='Førstehjelper (Behandler)',
        empty_label='— Ikke koblet —',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        help_text='Koble brukeren til en oppføring i Behandler-listen.',
    )
    helsepersonell = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label='Oppfølgingsansvarlig (Helsepersonell)',
        empty_label='— Ikke koblet —',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        help_text='Koble brukeren til en oppføring i Helsepersonell-listen.',
    )

    def __init__(self, *args, target_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Lokal import for å unngå sirkulær import på modul-load
        from patients.models import Behandler, Helsepersonell
        self._target_user = target_user
        # Vis behandlere som enten er uten kobling, eller koblet til DENNE brukeren
        beh_qs = Behandler.objects.filter(user__isnull=True).order_by('name')
        hp_qs = Helsepersonell.objects.filter(user__isnull=True).order_by('name')
        if target_user is not None:
            beh_qs = (Behandler.objects.filter(user=target_user) | beh_qs).distinct().order_by('name')
            hp_qs = (Helsepersonell.objects.filter(user=target_user) | hp_qs).distinct().order_by('name')
        self.fields['behandler'].queryset = beh_qs
        self.fields['helsepersonell'].queryset = hp_qs
        # Pre-velg gjeldende kobling
        if target_user is not None:
            current_beh = Behandler.objects.filter(user=target_user).first()
            current_hp = Helsepersonell.objects.filter(user=target_user).first()
            if current_beh:
                self.fields['behandler'].initial = current_beh.pk
            if current_hp:
                self.fields['helsepersonell'].initial = current_hp.pk

    def clean(self):
        cleaned = super().clean()
        beh = cleaned.get('behandler')
        hp = cleaned.get('helsepersonell')
        if beh and hp:
            raise forms.ValidationError(
                'En bruker kan kun kobles til én rolle (enten Førstehjelper '
                'eller Oppfølgingsansvarlig), ikke begge samtidig.'
            )
        return cleaned

    def save(self):
        """Bytt kobling atomisk: frigjør gammel og sett ny."""
        from django.db import transaction
        from patients.models import Behandler, Helsepersonell
        user = self._target_user
        if user is None:
            return
        beh = self.cleaned_data.get('behandler')
        hp = self.cleaned_data.get('helsepersonell')
        with transaction.atomic():
            # Frigjør alle eksisterende koblinger for denne brukeren
            Behandler.objects.filter(user=user).exclude(pk=beh.pk if beh else None).update(user=None)
            Helsepersonell.objects.filter(user=user).exclude(pk=hp.pk if hp else None).update(user=None)
            # Sett nye koblinger
            if beh and beh.user_id != user.pk:
                beh.user = user
                beh.save(update_fields=['user'])
            if hp and hp.user_id != user.pk:
                hp.user = user
                hp.save(update_fields=['user'])
