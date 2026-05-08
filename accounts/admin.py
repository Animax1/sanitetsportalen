"""Django Admin-registrering for accounts-appen.

Bruker egne ModelAdmin-klasser med tilpassede skjema i stedet for
den innebygde UserAdmin, fordi CustomUser arver AbstractBaseUser +
PermissionsMixin (ikke AbstractUser) og mangler felt som first_name,
last_name og date_joined som UserAdmin forutsetter.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import CustomUser, LoginEvent


# ── Hjelpefunksjon for sesjons-rydding ─────────────────────────────────────

def _delete_active_sessions_for_users(user_ids):
    """Sletter alle aktive sesjoner som tilhører brukerne i `user_ids`.

    Returnerer antall slettede sesjoner.
    Brukes av fryse-actionen for å sikre at brukere kastes ut umiddelbart
    – ikke først når sesjons-cookien deres utløper.
    """
    if not user_ids:
        return 0
    target_strs = {str(uid) for uid in user_ids}
    slettet = 0
    # Vi må dekode session_data for hver rad fordi user_id ligger inni en
    # serialisert dict, ikke som en egen kolonne.
    for s in Session.objects.filter(expire_date__gt=timezone.now()):
        try:
            data = s.get_decoded()
        except Exception:
            continue  # Korrupt session – ignorer
        if str(data.get('_auth_user_id', '')) in target_strs:
            s.delete()
            slettet += 1
    return slettet


# ── Skjemaer ──────────────────────────────────────────────────────────────────

class CustomUserCreationForm(forms.ModelForm):
    """Skjema for å opprette ny bruker i admin."""

    password1 = forms.CharField(label='Passord', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Gjenta passord', widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'role', 'is_active', 'is_staff', 'is_superuser')

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') != cleaned.get('password2'):
            raise forms.ValidationError('Passordene matcher ikke.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class CustomUserChangeForm(forms.ModelForm):
    """Redigering – passord vises ikke her (bruk 'Endre passord'-siden)."""

    class Meta:
        model = CustomUser
        fields = (
            'username', 'email', 'role', 'is_active', 'is_staff', 'is_superuser',
            'must_change_password', 'mfa_required', 'failed_login_attempts', 'locked_until',
            'groups', 'user_permissions',
        )


# ── Admin-klasser ──────────────────────────────────────────────────────────────

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    """Admin for CustomUser med tilpassede forms (uten UserAdmin-avhengighet)."""

    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    list_display = ['username', 'email', 'role', 'is_active', 'is_staff', 'mfa_required', 'last_login_at']
    list_filter = ['role', 'is_active', 'is_staff', 'mfa_required']
    search_fields = ['username', 'email']
    ordering = ['username']
    readonly_fields = ['created_at', 'updated_at', 'last_login_at', 'last_login']
    filter_horizontal = ['groups', 'user_permissions']
    actions = ['freeze_users', 'thaw_users']

    @admin.action(description='Frys valgte brukere (deaktiver + logg ut aktive sesjoner)')
    def freeze_users(self, request, queryset):
        """Deaktiver kontoene OG slett aktive sesjoner i samme operasjon.

        Hindrer at allerede innloggede brukere kan fortsette å bruke siden
        til sesjons-cookien deres utløper. Reversibelt via 'Tø valgte brukere'.
        """
        # Beskytt mot at admin fryser seg selv ut av systemet
        if request.user.pk in queryset.values_list('pk', flat=True):
            self.message_user(
                request,
                'Du kan ikke fryse din egen konto. Fjern den fra utvalget og prøv på nytt.',
                level=messages.ERROR,
            )
            return

        user_ids = list(queryset.values_list('pk', flat=True))
        # Bare de som faktisk er aktive teller som "frosset nå"
        endret = queryset.filter(is_active=True).update(is_active=False)
        slettede_sesjoner = _delete_active_sessions_for_users(user_ids)

        self.message_user(
            request,
            f'Frøs {endret} bruker(e) og slettet {slettede_sesjoner} aktiv(e) sesjon(er). '
            f'Brukerne kan ikke lenger logge inn. Bruk "Tø valgte brukere" for å reversere.',
            level=messages.SUCCESS,
        )

    @admin.action(description='Tø valgte brukere (aktiver kontoen igjen)')
    def thaw_users(self, request, queryset):
        """Reaktiverer frosne kontoer. Bruker beholder samme passord/MFA."""
        endret = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(
            request,
            f'Tøde {endret} bruker(e). De kan nå logge inn igjen med samme passord.',
            level=messages.SUCCESS,
        )

    fieldsets = (
        (None, {'fields': ('username', 'email')}),
        ('Rolle og tilgang', {'fields': (
            'role', 'is_active', 'is_staff', 'is_superuser', 'must_change_password', 'mfa_required',
        )}),
        ('Sikkerhet', {'fields': ('failed_login_attempts', 'locked_until')}),
        ('Grupper og tillatelser', {'fields': ('groups', 'user_permissions')}),
        ('Datoer', {'fields': ('last_login', 'last_login_at', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'password1', 'password2',
                'role', 'is_active', 'is_staff', 'is_superuser',
            ),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """Bruk add_form ved opprettelse, vanlig form ved endring."""
        if obj is None:
            kwargs['form'] = self.add_form
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        """Bruk add_fieldsets ved opprettelse."""
        if obj is None:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    """Admin for LoginEvent."""

    list_display = ['username_attempt', 'user', 'success', 'event_type', 'ip', 'created_at']
    list_filter = ['success', 'event_type']
    search_fields = ['username_attempt', 'ip']
    readonly_fields = ['created_at', 'user', 'username_attempt', 'success', 'ip', 'user_agent', 'event_type']
    date_hierarchy = 'created_at'
