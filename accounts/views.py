"""Views for brukerkontoer og admin-panel."""
import base64
import io
import secrets
import string

import qrcode
from django.conf import settings as django_settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.sessions.models import Session
from django.core import signing
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import timedelta

from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited

from .decorators import admin_required
from .forms import LoginForm, ChangePasswordForm, AdminUserCreateForm, AdminUserEditForm
from .models import CustomUser, LoginEvent


def _get_client_ip(request):
    """Hent klientens IP-adresse fra request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _invalidate_other_sessions(user, current_session_key):
    """Slett alle aktive sesjoner for brukeren, unntatt nåværende sesjon."""
    for sess in Session.objects.filter(expire_date__gte=timezone.now()):
        data = sess.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.pk) and sess.session_key != current_session_key:
            sess.delete()


def _invalidate_all_sessions(user):
    """Slett alle aktive sesjoner for brukeren (brukes ved admin-reset)."""
    for sess in Session.objects.filter(expire_date__gte=timezone.now()):
        data = sess.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.pk):
            sess.delete()


def _log_event(user, username_attempt, success, request, event_type=LoginEvent.EVENT_LOGIN):
    """Logg en LoginEvent med valgfri hendelsestype."""
    ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    LoginEvent.objects.create(
        user=user,
        username_attempt=username_attempt,
        success=success,
        ip=ip,
        user_agent=user_agent,
        event_type=event_type,
    )


def _check_mfa_trust(request, user):
    """Sjekk om denne enheten er klarert via trust-cookie.

    Returnerer True hvis cookie eksisterer, signaturen er gyldig og ikke utløpt.
    Cookie-verdien er et signert token med user_id og device_id.
    """
    cookie_name = f'mfa_trusted_{user.pk}'
    token = request.COOKIES.get(cookie_name)
    if not token:
        return False

    trust_days = getattr(django_settings, 'MFA_TRUST_DEVICE_DAYS', 30)
    max_age = trust_days * 86400  # sekunder

    signer = signing.TimestampSigner()
    try:
        value = signer.unsign(token, max_age=max_age)
        user_id_str, device_id_str = value.split(':', 1)
        if str(user_id_str) != str(user.pk):
            return False
        # Sjekk at enheten fortsatt finnes og er bekreftet
        device_id = int(device_id_str)
        TOTPDevice.objects.get(pk=device_id, user=user, confirmed=True)
        return True
    except (signing.BadSignature, signing.SignatureExpired, ValueError, TypeError,
            TOTPDevice.DoesNotExist):
        return False


def _set_mfa_trust_cookie(response, user, device, is_secure):
    """Sett trust-cookie på response."""
    trust_days = getattr(django_settings, 'MFA_TRUST_DEVICE_DAYS', 30)
    signer = signing.TimestampSigner()
    value = f'{user.pk}:{device.pk}'
    token = signer.sign(value)
    cookie_name = f'mfa_trusted_{user.pk}'
    response.set_cookie(
        cookie_name,
        token,
        max_age=trust_days * 86400,
        httponly=True,
        secure=is_secure,
        samesite='Lax',
    )


def _delete_mfa_trust_cookie(response, user):
    """Slett trust-cookie for brukeren."""
    cookie_name = f'mfa_trusted_{user.pk}'
    response.delete_cookie(cookie_name)


def _generate_qr_base64(config_url):
    """Generer QR-kode som base64-kodet PNG-string."""
    img = qrcode.make(config_url)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode('utf-8')


def _do_complete_login(request, user, next_url='/'):
    """Fullfør innlogging: kall login(), invalider andre sesjoner, redirect."""
    login(request, user)
    _invalidate_other_sessions(request.user, request.session.session_key)
    return redirect(next_url)


def ratelimited_view(request, exception=None):
    """Vises når rate-limit overskrides på innlogging."""
    return render(request, 'accounts/ratelimited.html', status=429)


@ratelimit(key='post:username', rate='10/5m', method='POST', block=True)
@ratelimit(key='ip', rate='50/5m', method='POST', block=True)
def login_view(request):
    """Innloggingsview med MFA-støtte, lockout-policy og rate-limiting.

    Rate-limit (dobbel dekorator):
      - Per brukernavn: 10 POST-forsøk / 5 min (beskytter den enkelte konto mot bruteforce)
      - Per IP: 50 POST-forsøk / 5 min (beskytter mot IP-baserte angrep; høyt nok til å
        tåle 10+ enheter bak samme NAT/wifi)
    Kan deaktiveres helt ved å sette RATELIMIT_ENABLE=False i miljøvariabler (nød-bryter
    uten deploy). Individuell brukerlåsing: 5 forsøk per bruker = 15 min låst.

    Flyt:
      Stage 1 – username/password-validering
      Stage 2 – MFA-oppsett (første gang, hvis mfa_required=True)
      Stage 3 – MFA-verifisering (innlogging nr. 2+)
      Stage 4 – Innlogging fullført
    """
    if request.user.is_authenticated:
        return redirect('/')

    next_url = request.GET.get('next', '/')
    ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    # ── Stage 2: MFA-oppsett ─────────────────────────────────────────────────
    if 'mfa_setup_user_id' in request.session:
        return _handle_mfa_setup(request, next_url)

    # ── Stage 3: MFA-verifisering ────────────────────────────────────────────
    if 'mfa_verify_user_id' in request.session:
        return _handle_mfa_verify(request, next_url)

    # ── Stage 1: Username/password ───────────────────────────────────────────
    form = LoginForm()
    error = None

    if request.method == 'POST':
        form = LoginForm(request.POST)
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        try:
            user_obj = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            user_obj = None

        if user_obj and user_obj.is_locked():
            remaining = int((user_obj.locked_until - timezone.now()).total_seconds() / 60) + 1
            error = f'Kontoen er midlertidig låst. Prøv igjen om {remaining} minutt(er).'
            LoginEvent.objects.create(
                user=user_obj, username_attempt=username, success=False,
                ip=ip, user_agent=user_agent, event_type=LoginEvent.EVENT_LOGIN,
            )
        else:
            user = authenticate(request, username=username, password=password)
            if user is not None and user.is_active:
                # Tilbakestill feilede forsøk
                user.failed_login_attempts = 0
                user.locked_until = None
                user.last_login_at = timezone.now()
                user.save(update_fields=['failed_login_attempts', 'locked_until', 'last_login_at'])
                LoginEvent.objects.create(
                    user=user, username_attempt=username, success=True,
                    ip=ip, user_agent=user_agent, event_type=LoginEvent.EVENT_LOGIN,
                )

                if user.mfa_required:
                    # Sjekk om brukeren allerede har en bekreftet TOTP-enhet
                    confirmed_device = TOTPDevice.objects.filter(
                        user=user, confirmed=True
                    ).first()

                    if confirmed_device is None:
                        # Stage 2: Tving MFA-oppsett
                        request.session['mfa_setup_user_id'] = user.pk
                        request.session['mfa_next_url'] = next_url
                        return redirect('accounts:login')
                    else:
                        # Sjekk trust-cookie
                        if _check_mfa_trust(request, user):
                            _log_event(user, username, True, request,
                                       LoginEvent.EVENT_MFA_TRUST_COOKIE_USED)
                            return _do_complete_login(request, user, next_url)
                        # Stage 3: Krev TOTP-verifisering
                        request.session['mfa_verify_user_id'] = user.pk
                        request.session['mfa_next_url'] = next_url
                        return redirect('accounts:login')
                else:
                    # Ingen MFA – logg inn direkte
                    return _do_complete_login(request, user, next_url)
            else:
                error = 'Feil brukernavn eller passord.'
                if user_obj:
                    user_obj.failed_login_attempts += 1
                    if user_obj.failed_login_attempts >= 5:
                        user_obj.locked_until = timezone.now() + timedelta(minutes=15)
                        user_obj.failed_login_attempts = 0
                        error = 'For mange feil forsøk. Kontoen er låst i 15 minutter.'
                    user_obj.save(update_fields=['failed_login_attempts', 'locked_until'])
                LoginEvent.objects.create(
                    user=user_obj, username_attempt=username, success=False,
                    ip=ip, user_agent=user_agent, event_type=LoginEvent.EVENT_LOGIN,
                )

    return render(request, 'accounts/login.html', {'form': form, 'error': error})


def _handle_mfa_setup(request, next_url):
    """Håndter MFA-oppsett (Stage 2): QR-kode + backup-koder + bekreftelse."""
    user_id = request.session.get('mfa_setup_user_id')
    next_url = request.session.get('mfa_next_url', next_url)

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        request.session.pop('mfa_setup_user_id', None)
        return redirect('accounts:login')

    # Hent eller opprett en ubekreftet TOTP-enhet
    device_id = request.session.get('mfa_setup_device_id')
    device = None
    if device_id:
        try:
            device = TOTPDevice.objects.get(pk=device_id, user=user, confirmed=False)
        except TOTPDevice.DoesNotExist:
            device = None

    if device is None:
        # Opprett ny ubekreftet enhet
        device = TOTPDevice.objects.create(
            user=user,
            name='Standard enhet',
            confirmed=False,
        )
        request.session['mfa_setup_device_id'] = device.pk

    # Hent eller generer backup-koder
    backup_codes = request.session.get('mfa_setup_backup_codes')
    if backup_codes is None:
        # Slett eventuelle gamle StaticDevices og lag nye backup-koder
        StaticDevice.objects.filter(user=user).delete()
        static_device = StaticDevice.objects.create(user=user, name='Backup-koder')
        backup_codes = []
        for _ in range(10):
            code = secrets.token_hex(4).upper()  # 8 hex-tegn = lesbart format
            StaticToken.objects.create(device=static_device, token=code)
            backup_codes.append(code)
        request.session['mfa_setup_backup_codes'] = backup_codes

    error = None

    if request.method == 'POST':
        code = request.POST.get('totp_code', '').strip().replace(' ', '')
        if device.verify_token(code):
            device.confirmed = True
            device.save()
            request.session.pop('mfa_setup_user_id', None)
            request.session.pop('mfa_setup_device_id', None)
            request.session.pop('mfa_setup_backup_codes', None)
            _log_event(user, user.username, True, request,
                       LoginEvent.EVENT_MFA_SETUP_COMPLETED)
            # Logg inn brukeren
            login(request, user)
            _invalidate_other_sessions(request.user, request.session.session_key)
            return redirect(next_url)
        else:
            error = 'Feil kode. Prøv igjen – kontroller at klokkene er synkronisert.'

    # Generer QR-kode som base64 PNG
    qr_base64 = _generate_qr_base64(device.config_url)

    return render(request, 'accounts/mfa_setup.html', {
        'qr_base64': qr_base64,
        'backup_codes': backup_codes,
        'error': error,
    })


def _handle_mfa_verify(request, next_url):
    """Håndter MFA-verifisering (Stage 3): verifiser TOTP eller backup-kode."""
    user_id = request.session.get('mfa_verify_user_id')
    next_url = request.session.get('mfa_next_url', next_url)

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        request.session.pop('mfa_verify_user_id', None)
        return redirect('accounts:login')

    error = None

    if request.method == 'POST':
        code = request.POST.get('totp_code', '').strip().replace(' ', '')
        backup_code = request.POST.get('backup_code', '').strip().upper()
        trust_device = request.POST.get('trust_device') == 'on'

        # Prøv TOTP-enhet(er)
        verified = False
        used_backup = False
        used_device = None

        if code:
            for device in TOTPDevice.objects.filter(user=user, confirmed=True):
                if device.verify_token(code):
                    verified = True
                    used_device = device
                    break

        # Fallback: backup-kode
        if not verified and backup_code:
            static_device = StaticDevice.objects.filter(user=user).first()
            if static_device:
                token_obj = StaticToken.objects.filter(
                    device=static_device, token=backup_code
                ).first()
                if token_obj:
                    token_obj.delete()  # Backup-koder er engangs
                    verified = True
                    used_backup = True
                    used_device = TOTPDevice.objects.filter(
                        user=user, confirmed=True
                    ).first()

        if verified:
            _log_event(user, user.username, True, request,
                       LoginEvent.EVENT_MFA_BACKUP_USED if used_backup
                       else LoginEvent.EVENT_MFA_VERIFY_SUCCESS)

            request.session.pop('mfa_verify_user_id', None)
            request.session.pop('mfa_next_url', None)
            login(request, user)
            _invalidate_other_sessions(request.user, request.session.session_key)
            response = redirect(next_url)
            if trust_device and used_device:
                is_secure = not getattr(django_settings, 'DEBUG', True)
                _set_mfa_trust_cookie(response, user, used_device, is_secure)
            return response
        else:
            _log_event(user, user.username, False, request,
                       LoginEvent.EVENT_MFA_VERIFY_FAILED)
            if code:
                error = 'Feil kode. Prøv igjen.'
            elif backup_code:
                error = 'Ugyldig backup-kode.'
            else:
                error = 'Skriv inn en kode for å logge inn.'

    return render(request, 'accounts/mfa_verify.html', {
        'error': error,
    })


def logout_view(request):
    """Logg ut bruker."""
    logout(request)
    return redirect('accounts:login')


@login_required
def change_password_view(request):
    """Endre passord – påkrevd ved must_change_password."""
    form = ChangePasswordForm()
    error = None

    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            if not request.user.must_change_password:
                old = form.cleaned_data.get('old_password', '')
                if not request.user.check_password(old):
                    error = 'Nåværende passord er feil.'
                    return render(request, 'accounts/change_password.html', {'form': form, 'error': error})

            new_pass = form.cleaned_data['new_password1']
            request.user.set_password(new_pass)
            request.user.must_change_password = False
            request.user.save(update_fields=['password', 'must_change_password'])

            current_session_key = request.session.session_key
            _invalidate_other_sessions(request.user, current_session_key)
            update_session_auth_hash(request, request.user)

            messages.success(request, 'Passordet er oppdatert.')
            return redirect('/')
        else:
            error = 'Skjemaet inneholder feil.'

    return render(request, 'accounts/change_password.html', {'form': form, 'error': error})


# ── Admin-panel: brukeradministrasjon ─────────────────────────────────────────

@admin_required
def user_list_view(request):
    """Liste over alle brukere med valgfri bulk-aksjon.

    Bulk-aksjoner (Fase 3b) lar admin slå på ett permission-flagg på en gruppe
    brukere i én operasjon — typisk «gi alle leads tilgang til
    pasientregistrering». Aksjonene skal være idempotente og lesbare.
    """
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'grant_pasienter_to_leads':
            qs = CustomUser.objects.filter(role__in=['lead', 'lead_view'])
            updated = qs.update(kan_redigere_pasienter=True)
            messages.success(
                request,
                f'Aktivert pasientregistrering for {updated} lead-bruker(e).',
            )
            return redirect('accounts:user_list')

        elif action == 'revoke_pasienter_from_all':
            # Trygg "reset" — fjerner kun pasient-flagget, beholder andre
            qs = CustomUser.objects.exclude(role='admin')
            updated = qs.update(kan_redigere_pasienter=False)
            messages.success(
                request,
                f'Fjernet pasientregistrering fra {updated} ikke-admin-bruker(e).',
            )
            return redirect('accounts:user_list')

    users = CustomUser.objects.all().order_by('username')
    return render(request, 'accounts/user_list.html', {'users': users})


@admin_required
def user_create_view(request):
    """Opprett ny bruker og vis midlertidig passord."""
    form = AdminUserCreateForm()
    temp_password = None

    if request.method == 'POST':
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            alphabet = string.ascii_letters + string.digits
            temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))
            user = form.save(commit=False)
            user.set_password(temp_password)
            user.must_change_password = True
            user.save()
            messages.success(request, f'Bruker «{user.username}» er opprettet.')
            return render(request, 'accounts/user_form.html', {
                'form': AdminUserCreateForm(),
                'temp_password': temp_password,
                'created_user': user,
            })

    return render(request, 'accounts/user_form.html', {'form': form, 'temp_password': temp_password})


@admin_required
def user_detail_view(request, pk):
    """Vis og rediger brukerdetaljer."""
    user = get_object_or_404(CustomUser, pk=pk)
    form = AdminUserEditForm(instance=user)
    temp_password = None
    recent_events = LoginEvent.objects.filter(user=user).order_by('-created_at')[:20]

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'edit':
            form = AdminUserEditForm(request.POST, instance=user)
            if form.is_valid():
                form.save()
                messages.success(request, 'Bruker oppdatert.')
                return redirect('accounts:user_detail', pk=pk)

        elif action == 'unlock':
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['failed_login_attempts', 'locked_until'])
            messages.success(request, f'Kontoen til «{user.username}» er låst opp.')
            return redirect('accounts:user_detail', pk=pk)

        elif action == 'reset_password':
            alphabet = string.ascii_letters + string.digits
            temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))
            user.set_password(temp_password)
            user.must_change_password = True
            user.save(update_fields=['password', 'must_change_password'])

            _invalidate_all_sessions(user)

            messages.success(request, 'Nytt midlertidig passord generert (vises nedenfor).')

        elif action == 'reset_mfa':
            # Slett alle TOTP-enheter
            TOTPDevice.objects.filter(user=user).delete()
            # Slett alle static/backup-enheter
            StaticDevice.objects.filter(user=user).delete()
            # Sett mfa_required=True (brukeren tvinges til oppsett på nytt)
            user.mfa_required = True
            user.save(update_fields=['mfa_required'])
            # Invalider alle sesjoner
            _invalidate_all_sessions(user)
            # Logg hendelsen
            _log_event(user, user.username, True, request,
                       LoginEvent.EVENT_MFA_RESET_BY_ADMIN)
            messages.success(
                request,
                f'MFA nullstilt for «{user.username}» — de må sette opp på nytt ved neste pålogging.',
            )
            return redirect('accounts:user_detail', pk=pk)

    # Sjekk om brukeren har MFA-enheter (for å vise/skjule nullstill-knapp)
    has_totp_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()

    return render(request, 'accounts/user_detail.html', {
        'target_user': user,
        'form': form,
        'temp_password': temp_password,
        'recent_events': recent_events,
        'has_totp_device': has_totp_device,
    })
