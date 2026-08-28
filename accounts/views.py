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
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from datetime import timedelta

from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from core.ratelimit import er_rate_limited as core_er_rate_limited

from audit.models import AuditLog
from core.url_safety import safe_redirect_url

from .decorators import admin_required
from .forms import (
    LoginForm, ChangePasswordForm, AdminUserCreateForm, AdminUserEditForm,
    GlemtPassordForm, ModulTilgangForm,
    PasientRolleForm, SettPassordForm,
)
from .invitasjon import kan_inviteres, les_token, send_invitasjon
from .passord_reset import (
    finn_bruker, les_token as les_reset_token, send_reset,
)
from .models import CustomUser, LoginEvent


def _get_client_ip(request):
    """Hent klientens IP-adresse fra request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _registrer_aktiv_sesjon(user, session_key):
    """Avslutt brukerens forrige sesjon og registrer den nye (N10).

    Portalen har én-sesjon-per-bruker som policy: logger du inn på en ny enhet,
    ryker den gamle. Det var tidligere implementert ved å iterere **alle**
    ikke-utløpte sesjoner og kalle ``get_decoded()`` på hver — signaturverifisering
    og JSON-parsing per rad. Django har ingen indeks fra bruker til sesjon, så
    mønsteret er i og for seg det vanlige; problemet var hvor det ble kalt.
    Kostnaden traff innloggingsstien, altså de ti minuttene ved vaktstart der
    alle logger på samtidig.

    Nå lagrer vi sesjonsnøkkelen på brukeren, og invalidering blir ett indeksert
    oppslag. Feltet er en cache av policyen, ikke fasit for hvilke sesjoner som
    finnes. Derfor beholder de sikkerhetskritiske stiene — passordbytte,
    admin-reset, frys og sletting — den grundige gjennomgangen.

    **Tom `current_session_key` betyr ikke «ingen sesjoner».** Den betyr at vi
    ikke *vet* om det finnes noen: brukeren kan ha en sesjon opprettet før feltet
    ble innført. Skjedde i produksjon 13. august 2026 — en bruker som allerede var
    innlogget på én enhet forble innlogget der etter å ha logget inn på en annen,
    fordi det ikke sto noen nøkkel å slette. Derfor faller vi tilbake til den
    grundige gjennomgangen når feltet er tomt. Det koster ett fullt gjennomløp
    per bruker, første gang de logger inn etter at feltet ble innført; deretter
    gjelder den raske stien.
    """
    forrige = user.current_session_key

    if not forrige:
        _invalidate_other_sessions(user, session_key)
        return

    if forrige != session_key:
        Session.objects.filter(session_key=forrige).delete()
        user.current_session_key = session_key
        user.save(update_fields=['current_session_key'])


def _invalidate_other_sessions(user, current_session_key):
    """Slett alle aktive sesjoner for brukeren, unntatt nåværende sesjon.

    Grundig variant: itererer og dekoder alle ikke-utløpte sesjoner. Brukes ved
    passordbytte, der det å garantere at ingen annen sesjon overlever er selve
    poenget — og hvor kostnaden er irrelevant fordi operasjonen er sjelden.
    Innloggingsstien bruker ``_registrer_aktiv_sesjon()`` i stedet.
    """
    for sess in Session.objects.filter(expire_date__gte=timezone.now()):
        data = sess.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.pk) and sess.session_key != current_session_key:
            sess.delete()

    if user.current_session_key != current_session_key:
        user.current_session_key = current_session_key
        user.save(update_fields=['current_session_key'])


def _invalidate_all_sessions(user):
    """Slett alle aktive sesjoner for brukeren (admin-reset, frys, sletting).

    Grundig av samme grunn som over: brukes kun i sikkerhetsoperasjoner der en
    overlevende sesjon er hele feilmodusen man vil unngå.
    """
    for sess in Session.objects.filter(expire_date__gte=timezone.now()):
        data = sess.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.pk):
            sess.delete()

    if user.current_session_key:
        user.current_session_key = None
        user.save(update_fields=['current_session_key'])


def _log_user_admin_action(request, target_user, action, field_name=None,
                           old_value=None, new_value=None,
                           table_name='accounts_customuser'):
    """Skriv en AuditLog-rad for en administrativ handling på en brukerkonto.

    Frysing og sletting av kontoer er ikke pasientdata, så ``patients.signals``
    fanger dem ikke opp. Vi skriver raden eksplisitt her slik at handlingen blir
    synlig i ``/portal-admin/auditlog/``.

    ``record_id`` er en ren integer uten FK, så raden overlever at brukeren
    slettes — hvilket er hele poenget for DELETE-tilfellet.

    ``table_name`` styrer hvilken modul raden havner under i admin-filteret:
    ``audit.signals.utled_app_label`` leser prefikset. Modultilgang skrives med
    ``accounts_modultilgang`` slik at en tilgangsendring ikke ser ut som en
    endring på selve kontoen.
    """
    AuditLog.objects.create(
        table_name=table_name,
        record_id=target_user.pk,
        action=action,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        user=request.user if request.user.is_authenticated else None,
        ip=_get_client_ip(request),
    )


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
    """Fullfør innlogging: kall login(), avslutt forrige sesjon, redirect."""
    login(request, user)
    _registrer_aktiv_sesjon(request.user, request.session.session_key)
    return redirect(next_url)


def ratelimited_view(request, exception=None):
    """Vises når rate-limit overskrides på innlogging."""
    return render(request, 'accounts/ratelimited.html', status=429)


def _epost_nokkel(group, request):
    """Rate-limit-nøkkel for reset, normalisert som oppslaget.

    Oppslaget er ufølsomt for store bokstaver, så telleren må være det
    også — ellers gir «Kari@…» og «kari@…» hver sin bøtte mot samme
    innboks.
    """
    return (request.POST.get('email') or '').strip().lower()


def _brukernavn_nokkel(group, request):
    """Rate-limit-nøkkel for innlogging, normalisert som oppslaget.

    Innlogging slår opp brukernavnet uten hensyn til store bokstaver (se
    `accounts/backends.py`). Teller vi på den rå verdien, får «kari» og
    «Kari» hver sin bøtte mot én og samme konto.
    """
    return (request.POST.get('username') or '').strip().lower()


def _er_rate_limited(request, group, key, rate):
    """Tell ett forsøk mot en rate-limit-bøtte og si om grensen er passert.

    Innpakning rundt ``core.ratelimit.er_rate_limited`` slik at kallstedene
    under blir lesbare. ``increment=True`` skjer inne i den — kall derfor
    denne én gang per forsøk, ikke i en betingelse som kan evalueres flere
    ganger.

    Delegeringen kom med S3: kjernen fanger nå feil i cache-laget og faller
    åpen i stedet for å svare 500 eller 429 på alt. For innloggingsstien
    betyr det at en død Redis ikke låser alle ute — kontolåsingen i databasen
    (5 feilede forsøk = 15 min) står uansett, og er den som faktisk stopper
    gjetting mot én konto.
    """
    return core_er_rate_limited(
        request, group=group, key=key, rate=rate, method='POST',
    )


def _registrer_mislykket_forsok(user):
    """Tell opp feilede forsøk og lås kontoen i 15 min ved femte.

    Delt mellom passord-steget og MFA-steget. Uten dette var MFA-verifiseringen
    det eneste steget uten kontosperre: man kunne gjette TOTP-koder i det
    uendelige uten at telleren ble rørt.

    Returnerer True hvis kontoen ble låst av dette forsøket.
    """
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= 5:
        user.locked_until = timezone.now() + timedelta(minutes=15)
        user.failed_login_attempts = 0
        user.save(update_fields=['failed_login_attempts', 'locked_until'])
        return True
    user.save(update_fields=['failed_login_attempts', 'locked_until'])
    return False


@never_cache
def login_view(request):
    """Innloggingsview med MFA-støtte, lockout-policy og rate-limiting.

    ``@never_cache`` er ikke pynt: uten den kan nettleseren servere en lagret
    kopi av innloggingssiden, og CSRF-tokenet i det lagrede skjemaet er da
    knyttet til en cookie som er rotert siden. Både ``login()`` og ``logout()``
    kaller ``rotate_token()``, så et gammelt skjema gir «CSRF-verifisering
    feilet» ved neste innlogging. Django sin egen ``LoginView`` er dekorert på
    samme måte, av samme grunn.

    Rate-limit (N4): grensene håndheves med eksplisitte ``is_ratelimited``-kall
    i hvert steg, ikke med dekoratorer på hele viewet. Grunnen er at MFA-stegene
    håndteres inne i dette viewet, men **ikke** sender noe ``username``-felt —
    de sender bare koden. En dekorator med ``key='post:username'`` slo derfor
    opp en tom verdi, og alle MFA-forsøk fra alle brukere havnet i samme bøtte:
    10 MFA-innlogginger per 5 minutter *totalt for hele appen*. Ved vaktstart,
    når alle logger på samtidig, ville den ellevte fått 429 uten at noe var galt
    med kontoen.

    Grensene nå:
      - Steg 1, per brukernavn: 10 POST / 5 min (bruteforce mot én konto)
      - Steg 1, per IP: 50 POST / 5 min (høyt nok for 10+ enheter bak samme NAT)
      - Steg 2 og 3, per bruker-ID fra sesjonen: 10 POST / 5 min

    Kan deaktiveres helt med ``RATELIMIT_ENABLE=False`` (nød-bryter uten deploy).
    Individuell brukerlåsing: 5 feilede forsøk = 15 min låst. Låsingen gjelder
    nå både passord- og MFA-steget; tidligere kunne man gjette TOTP-koder i det
    uendelige uten at det skjedde noe med kontoen.

    Flyt:
      Stage 1 – username/password-validering
      Stage 2 – MFA-oppsett (første gang, hvis mfa_required=True)
      Stage 3 – MFA-verifisering (innlogging nr. 2+)
      Stage 4 – Innlogging fullført
    """
    if request.user.is_authenticated:
        return redirect('/')

    # `next` leses fra POST først, deretter fra query-strengen. Skjemaet poster
    # til `{% url %}`, som ikke tar med query-strengen — uten det skjulte
    # next-feltet i malen gikk verdien tapt i det brukeren trykket «Logg inn»,
    # og man havnet alltid på forsiden i stedet for der man skulle. Django sin
    # egen LoginView bruker samme hidden-field-mønster.
    #
    # N1: valider ett sted — her, der den leses. MFA-stegene arver den
    # validerte verdien via sesjonen, så det finnes ingen vei rundt sjekken.
    next_url = safe_redirect_url(
        request, request.POST.get('next') or request.GET.get('next'),
    )
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
        # Nøkkelen normaliseres på samme måte som oppslaget. Med
        # `post:username` ville «Kari» og «kari» vært to bøtter mot én og
        # samme konto, og en angriper kunne mangedoblet forsøksbudsjettet
        # sitt ved å variere store bokstaver.
        if _er_rate_limited(request, 'login:username', _brukernavn_nokkel, '10/5m') \
                or _er_rate_limited(request, 'login:ip', 'ip', '50/5m'):
            return ratelimited_view(request)

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
                if user_obj and _registrer_mislykket_forsok(user_obj):
                    error = 'For mange feil forsøk. Kontoen er låst i 15 minutter.'
                LoginEvent.objects.create(
                    user=user_obj, username_attempt=username, success=False,
                    ip=ip, user_agent=user_agent, event_type=LoginEvent.EVENT_LOGIN,
                )

    return render(request, 'accounts/login.html', {
        'form': form,
        'error': error,
        'next_url': next_url,
    })


def _handle_mfa_setup(request, next_url):
    """Håndter MFA-oppsett (Stage 2): QR-kode + backup-koder + bekreftelse."""
    user_id = request.session.get('mfa_setup_user_id')
    # Verdien ble validert da den ble lagt i sesjonen, men vi validerer på nytt
    # ved lesing: en sesjon kan stamme fra en eldre release uten sjekken.
    next_url = safe_redirect_url(request, request.session.get('mfa_next_url'), next_url)

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
        # N4: nøkkelen er brukerens ID fra sesjonen. Skjemaet sender ingen
        # `username`, så uten dette ville alle brukeres MFA-oppsett delt bøtte.
        if _er_rate_limited(request, 'mfa:setup', lambda g, r: f'mfa-setup:{user.pk}', '10/5m'):
            return ratelimited_view(request)

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
            _registrer_aktiv_sesjon(request.user, request.session.session_key)
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
    # Verdien ble validert da den ble lagt i sesjonen, men vi validerer på nytt
    # ved lesing: en sesjon kan stamme fra en eldre release uten sjekken.
    next_url = safe_redirect_url(request, request.session.get('mfa_next_url'), next_url)

    try:
        user = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        request.session.pop('mfa_verify_user_id', None)
        return redirect('accounts:login')

    error = None

    # N4: rate-limit per bruker, ikke per (tomt) brukernavn. Se docstring i
    # login_view. Sjekken ligger før kontosperren med vilje — en låst konto som
    # hamres på skal også bremses, ellers er den billige stien den ubegrensede.
    if request.method == 'POST' and _er_rate_limited(
        request, 'mfa:verify', lambda g, r: f'mfa-verify:{user.pk}', '10/5m',
    ):
        return ratelimited_view(request)

    # Kontosperren fra passord-steget gjelder også her. Uten sjekken kunne en
    # låst konto fortsatt gjette TOTP-koder, siden sperren bare ble lest i
    # steg 1.
    if user.is_locked():
        remaining = int((user.locked_until - timezone.now()).total_seconds() / 60) + 1
        return render(request, 'accounts/mfa_verify.html', {
            'error': f'Kontoen er midlertidig låst. Prøv igjen om {remaining} minutt(er).',
        })

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

            # Nullstill telleren — brukeren har bevist begge faktorer.
            if user.failed_login_attempts:
                user.failed_login_attempts = 0
                user.save(update_fields=['failed_login_attempts'])

            request.session.pop('mfa_verify_user_id', None)
            request.session.pop('mfa_next_url', None)
            login(request, user)
            _registrer_aktiv_sesjon(request.user, request.session.session_key)
            response = redirect(next_url)
            if trust_device and used_device:
                # S6: request.is_secure() tar hensyn til SECURE_PROXY_SSL_HEADER
                # og er derfor riktig både på Railway og i offline-modus. Det
                # gamle uttrykket `not DEBUG` satte Secure-flagget i
                # offline-modus, som kjører bevisst uten TLS — nettleseren kastet
                # da cookien, og «stol på denne enheten» virket ikke i felt.
                _set_mfa_trust_cookie(response, user, used_device, request.is_secure())
            return response
        else:
            _log_event(user, user.username, False, request,
                       LoginEvent.EVENT_MFA_VERIFY_FAILED)
            if _registrer_mislykket_forsok(user):
                error = 'For mange feil forsøk. Kontoen er låst i 15 minutter.'
            elif code:
                error = 'Feil kode. Prøv igjen.'
            elif backup_code:
                error = 'Ugyldig backup-kode.'
            else:
                error = 'Skriv inn en kode for å logge inn.'

    return render(request, 'accounts/mfa_verify.html', {
        'error': error,
    })


@require_POST
def logout_view(request):
    """Logg ut bruker. Kun POST (S5).

    Med GET kunne enhver side på internett logge ut brukeren vår med en
    ``<img src="https://<app>/accounts/logout/">``. Konsekvensen er irritasjon
    og ikke datatap, men midt i en vakt er det ikke ingenting. Django 5 fjernet
    GET-utlogging fra sin egen ``LogoutView`` av samme grunn.

    Malene bruker et lite skjema med CSRF-token i stedet for ``<a href>``.
    """
    logout(request)
    return redirect('accounts:login')


@login_required
def change_password_view(request):
    """Endre passord – påkrevd ved must_change_password.

    Rate-limit (S3): bøtta teller **kun feilede gjett på nåværende passord**,
    ikke POST-er mot dette viewet.

    Skillet er ikke kosmetisk. `MustChangePasswordMiddleware` sperrer hver
    URL unntatt denne, utlogging, innlogging og static — en bruker med
    `must_change_password=True` kommer ikke inn i portalen før byttet lykkes.
    En dekoratør på hele viewet ville telt hver avvist skjemainnsending også:
    for kort passord, passord som ligner brukernavnet, bekreftelse som ikke
    stemmer. En ny frivillig som fomler ved vaktstart ville da blitt stengt
    ute av *hele* portalen i fem minutter.

    Og i den tilstanden beskytter bøtta ingenting: `old_password` sjekkes kun
    når `must_change_password` er False, så i tvungen-bytte-stien finnes det
    ikke noe gammelt passord å gjette. Samme feil som N4 — telleren telte feil
    hendelse.
    """
    form = ChangePasswordForm()
    error = None

    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            if not request.user.must_change_password:
                old = form.cleaned_data.get('old_password', '')
                if not request.user.check_password(old):
                    # Telles her, etter at gjettet er slått fast som feil:
                    # et riktig passord skal aldri koste brukeren kvote.
                    if _er_rate_limited(
                        request, 'password:old-guess', 'user', '10/5m',
                    ):
                        return ratelimited_view(request)
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
    """Liste over alle brukere.

    **Bulk-aksjonene er borte (deploy 2).** To knapper skrev til
    ``kan_redigere_pasienter`` på en gruppe kontoer om gangen: «gi ledere
    pasienttilgang» og «fjern pasienttilgang fra alle». Begge sluttet å bety
    noe da ``@modul_kreves`` og ``Module.is_visible_for`` gikk over til å lese
    ``ModulTilgang`` — flagget de skrev til ble ikke lest av noe.

    En knapp som melder «Fjernet pasientregistrering fra 7 brukere» uten at
    noen mistet noe er verre enn ingen knapp: neste gang tilgang faktisk skal
    trekkes tilbake, tror admin at jobben er gjort. Tilgang settes per konto i
    matrisen på ``user_detail``, som skriver til tabellen håndhevelsen leser.
    """
    users = CustomUser.objects.all().order_by('username')
    return render(request, 'accounts/user_list.html', {'users': users})


@admin_required
@require_http_methods(['GET'])
def login_event_list_view(request):
    """Global, paginert visning av LoginEvent.

    Brukerdetaljsiden viser kun siste 20 hendelser for én bruker. Denne flaten
    svarer på spørsmålene som går på tvers: «hvem har prøvd å logge inn på denne
    kontoen», «kom det en serie feilede forsøk fra én IP i natt», «hvem fikk
    MFA nullstilt forrige uke». Det var funksjonalitet som kun fantes i
    `/django-admin/`, og som måtte på plass før den flaten kunne fjernes (S1).

    Filtre (GET-parametre): ``q`` (brukernavn eller IP), ``event_type``,
    ``result`` (ok/fail) og ``date_from`` / ``date_to`` (ISO-dato).

    Merk at ``purge_old_logs`` også sletter LoginEvent etter 730 dager (F2), så
    denne visningen viser aldri mer enn retensjonsvinduet.
    """
    qs = LoginEvent.objects.select_related('user')

    filters = {
        'q': (request.GET.get('q') or '').strip(),
        'event_type': (request.GET.get('event_type') or '').strip(),
        'result': (request.GET.get('result') or '').strip(),
        'date_from': (request.GET.get('date_from') or '').strip(),
        'date_to': (request.GET.get('date_to') or '').strip(),
    }

    if filters['q']:
        qs = qs.filter(
            Q(username_attempt__icontains=filters['q'])
            | Q(ip__icontains=filters['q'])
        )
    if filters['event_type']:
        qs = qs.filter(event_type=filters['event_type'])
    if filters['result'] == 'ok':
        qs = qs.filter(success=True)
    elif filters['result'] == 'fail':
        qs = qs.filter(success=False)
    if filters['date_from']:
        qs = qs.filter(created_at__date__gte=filters['date_from'])
    if filters['date_to']:
        qs = qs.filter(created_at__date__lte=filters['date_to'])

    paginator = Paginator(qs.order_by('-created_at'), 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'accounts/login_event_list.html', {
        'page_obj': page_obj,
        'filters': filters,
        'event_type_choices': LoginEvent.EVENT_TYPE_CHOICES,
        'total_count': paginator.count,
    })


def _lagre_ny_modultilgang(request, user, tilgang_form):
    """Skriv matrisen for en nyopprettet bruker, og loggfør den.

    Skjemaet ble bygget uten `bruker`, så det kjenner ingen nåværende rader —
    alt som er satt er en endring fra «ingen».
    """
    for slug, fra, til in tilgang_form.save(user):
        _log_user_admin_action(
            request, user, 'CREATE', field_name=slug,
            old_value=fra or 'ingen', new_value=til or 'ingen',
            table_name='accounts_modultilgang',
        )


@admin_required
def user_create_view(request):
    """Opprett ny bruker — med invitasjon, eller med midlertidig passord.

    Invitasjon er hovedveien: kontoen får ingen brukbar passord-hash, og
    brukeren setter sitt eget via en signert lenke. Da finnes det **ingenting
    å formidle** — i motsetning til det midlertidige passordet, som må sendes
    videre over en kanal man sjelden vil ha passord i.

    Midlertidig passord beholdes som reserve for to tilfeller som begge er
    reelle: en delt konto har ingen innboks å invitere til, og e-post kan
    feile midt i en vaktstart. Admin velger med `metode` i skjemaet.

    `must_change_password` settes kun på den midlertidige stien. Ved
    invitasjon velger brukeren passordet selv, og da ville flagget tvunget
    dem til å velge to passord på rad uten forklaring.
    """
    form = AdminUserCreateForm()
    # §10.3: matrisen hører hjemme her, ikke bare på redigeringsskjemaet.
    # Uten den lander den nyinviterte i en tom portal og må redigeres etterpå
    # — og den som oppretter kontoen er den som vet hva den skal ha.
    tilgang_form = ModulTilgangForm()
    temp_password = None

    if request.method == 'POST':
        form = AdminUserCreateForm(request.POST)
        tilgang_form = ModulTilgangForm(request.POST)
        if form.is_valid() and tilgang_form.is_valid():
            user = form.save(commit=False)
            vil_invitere = (
                request.POST.get('metode', 'invitasjon') == 'invitasjon'
                and not user.er_delt_konto
                and bool(user.email)
            )

            if vil_invitere:
                # Ingen brukbar hash: kontoen kan ikke logges inn på før
                # brukeren har vært innom lenken.
                user.set_unusable_password()
                user.must_change_password = False
                user.save()
                _lagre_ny_modultilgang(request, user, tilgang_form)

                if send_invitasjon(user, request):
                    messages.success(
                        request,
                        f'Bruker «{user.username}» er opprettet, og '
                        f'invitasjonen er sendt til {user.email}.',
                    )
                else:
                    messages.warning(
                        request,
                        f'Bruker «{user.username}» er opprettet, men '
                        f'invitasjonen kunne ikke sendes. Send den på nytt '
                        f'fra brukersiden, eller sett et passord manuelt.',
                    )
                return redirect('accounts:user_detail', pk=user.pk)

            alphabet = string.ascii_letters + string.digits
            temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))
            user.set_password(temp_password)
            user.must_change_password = True
            user.save()
            _lagre_ny_modultilgang(request, user, tilgang_form)
            messages.success(request, f'Bruker «{user.username}» er opprettet.')
            return render(request, 'accounts/user_form.html', {
                'form': AdminUserCreateForm(),
                'tilgang_form': ModulTilgangForm(),
                'temp_password': temp_password,
                'created_user': user,
            })

    return render(request, 'accounts/user_form.html', {
        'form': form,
        'tilgang_form': tilgang_form,
        'temp_password': temp_password,
    })


def glemt_passord_view(request):
    """Be om en reset-lenke. Åpen uten innlogging.

    §6.7: svaret er identisk enten adressen finnes eller ikke — samme side,
    samme tekst, samme statuskode. For en frivillig organisasjon avslører «har
    konto» hvem som er medlem og har vakter.

    §6.5: egen rate-limit-bøtte, med to nøkler. Per adresse hindrer at noen
    spammer én innboks ved å be om reset i løkke. Per IP hindrer at noen feier
    gjennom en liste med adresser. Begge telles **før** oppslaget, slik at
    strupingen ikke i seg selv røper om adressen finnes.
    """
    form = GlemtPassordForm()

    if request.method == 'POST':
        if _er_rate_limited(request, 'reset:epost', _epost_nokkel, '3/10m') \
                or _er_rate_limited(request, 'reset:ip', 'ip', '20/10m'):
            return ratelimited_view(request)

        form = GlemtPassordForm(request.POST)
        if form.is_valid():
            bruker = finn_bruker(form.cleaned_data['email'])
            if bruker is not None:
                send_reset(bruker, request)
            # Ingen else. Utfallet er det samme uansett — også hvis
            # utsendingen feilet, for en feilmelding ville vært et svar.
            return render(request, 'accounts/glemt_passord_sendt.html')

    return render(request, 'accounts/glemt_passord.html', {'form': form})


def passord_reset_view(request, token):
    """Landingssiden for en reset-lenke: brukeren velger nytt passord.

    §6.3: alle sesjoner avsluttes. Uten det overlever en stjålet sesjon
    passordbyttet, og resetten har ikke gjort det den skulle.

    §6.4: `must_change_password` nullstilles. Flagget er riktig når admin har
    generert et midlertidig passord, men her velger brukeren selv — står det
    igjen, må de velge to passord på rad uten forklaring.

    §6.2: ingen innlogging skjer her. Brukeren sendes til innloggingssiden, og
    møter MFA-steget der hvis rollen krever det.
    """
    user = les_reset_token(token)
    if user is None:
        return render(request, 'accounts/reset_ugyldig.html', status=400)

    form = SettPassordForm()
    if request.method == 'POST':
        form = SettPassordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['new_password1'])
            user.must_change_password = False
            user.save(update_fields=['password', 'must_change_password'])
            _invalidate_all_sessions(user)
            messages.success(
                request,
                'Passordet er endret. Logg inn med det nye passordet.',
            )
            return redirect('accounts:login')

    return render(request, 'accounts/passord_reset.html', {
        'form': form,
        'bruker': user,
    })


def invitasjon_view(request, token):
    """Landingssiden for en invitasjonslenke: brukeren setter sitt eget passord.

    Åpen uten innlogging — det er hele poenget. Sikkerheten ligger i at
    tokenet er signert, tidsbegrenset og dør i det passordet settes.

    Alle avvisningsgrunner gir samme side og samme melding: ugyldig signatur,
    utløpt lenke, brukt lenke, frosset konto. Å skille dem ville fortalt en
    tilfeldig besøkende om en konto finnes — samme resonnement som ligger bak
    at innlogging sier «feil brukernavn eller passord», aldri hvilken.

    Etter at passordet er satt sendes brukeren til innlogging, ikke rett inn.
    Da møter de MFA-oppsettet på vanlig måte hvis rollen krever det, og de får
    bekreftet at innloggingen faktisk virker mens de fortsatt har oss på tråden.
    """
    user = les_token(token)
    if user is None:
        return render(request, 'accounts/invitasjon_ugyldig.html', status=400)

    form = SettPassordForm()
    if request.method == 'POST':
        form = SettPassordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['new_password1'])
            user.must_change_password = False
            user.save(update_fields=['password', 'must_change_password'])
            messages.success(
                request,
                'Passordet er satt. Logg inn for å komme i gang.',
            )
            return redirect('accounts:login')

    return render(request, 'accounts/invitasjon.html', {
        'form': form,
        'invitert': user,
    })


@admin_required
def user_detail_view(request, pk):
    """Vis og rediger brukerdetaljer."""
    user = get_object_or_404(CustomUser, pk=pk)
    form = AdminUserEditForm(instance=user)
    tilgang_form = ModulTilgangForm(bruker=user)
    link_form = PasientRolleForm(user)
    temp_password = None
    recent_events = LoginEvent.objects.filter(user=user).order_by('-created_at')[:20]

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'edit':
            mfa_for = user.mfa_required
            rolle_for = user.role
            form = AdminUserEditForm(request.POST, instance=user)
            tilgang_form = ModulTilgangForm(request.POST, bruker=user)
            if form.is_valid() and tilgang_form.is_valid():
                form.save()

                # Rolleendring ble ikke loggført i det hele tatt: frysing og
                # sletting skrev auditrad, men det å gi noen admin gjorde det
                # ikke. Modultilgang loggføres per modul som endres.
                if user.role != rolle_for:
                    _log_user_admin_action(
                        request, user, 'UPDATE', field_name='role',
                        old_value=rolle_for, new_value=user.role,
                    )
                for slug, fra, til in tilgang_form.save(user):
                    _log_user_admin_action(
                        request, user, 'UPDATE', field_name=slug,
                        old_value=fra or 'ingen', new_value=til or 'ingen',
                        table_name='accounts_modultilgang',
                    )

                # Slås «Krev MFA» på mens brukeren har en levende sesjon,
                # gjelder kravet ikke for dem før cookien dør — de kan ha
                # timer igjen. Sesjonene avsluttes derfor med det samme, slik
                # at neste pålogging faktisk går gjennom MFA-oppsettet.
                # Dette er en sikkerhetsinnstilling; å la den vente på en
                # cookie ville gjort den valgfri i praksis.
                if user.mfa_required and not mfa_for:
                    _invalidate_all_sessions(user)
                    messages.success(
                        request,
                        f'Bruker oppdatert. «{user.username}» er logget ut, '
                        f'slik at MFA settes opp ved neste pålogging.',
                    )
                else:
                    messages.success(request, 'Bruker oppdatert.')
                return redirect('accounts:user_detail', pk=pk)

        elif action == 'link_patient_role':
            link_form = PasientRolleForm(user, request.POST)
            if link_form.is_valid():
                link_form.save()
                messages.success(request, 'Pasient-rolle oppdatert.')
                return redirect('accounts:user_detail', pk=pk)

        elif action == 'send_invitasjon':
            # Ny lenke på forespørsel. Den gamle dør ikke av at en ny lages —
            # begge peker på samme passord-avtrykk — men begge utløper etter
            # tre døgn, og den første som brukes dreper resten.
            if not kan_inviteres(user):
                messages.error(
                    request,
                    'Kontoen kan ikke inviteres: den mangler e-post, eller '
                    'den er en delt konto.',
                )
            elif send_invitasjon(user, request):
                messages.success(
                    request, f'Ny invitasjon er sendt til {user.email}.',
                )
            else:
                messages.error(
                    request,
                    'Invitasjonen kunne ikke sendes. Sjekk e-postoppsettet, '
                    'eller sett et passord manuelt.',
                )
            return redirect('accounts:user_detail', pk=pk)

        elif action == 'logg_ut':
            # Avslutt sesjonene uten å røre kontoen. Til forskjell fra «frys»
            # kan brukeren logge inn igjen med det samme — poenget er at de
            # må *gjennom* innloggingen på nytt.
            #
            # Utløst av et konkret behov: slår admin på «Krev MFA» mens
            # brukeren har sju timer igjen av sesjonen, gjelder ikke MFA for
            # den personen før cookien dør av seg selv.
            if user.pk == request.user.pk:
                messages.error(
                    request,
                    'Du kan ikke logge ut deg selv herfra — bruk Logg ut i menyen.',
                )
                return redirect('accounts:user_detail', pk=pk)

            _invalidate_all_sessions(user)
            _log_user_admin_action(
                request, user, 'UPDATE',
                field_name='sessions', old_value='active', new_value='cleared',
            )
            messages.success(
                request,
                f'«{user.username}» er logget ut. Neste pålogging går gjennom '
                f'hele innloggingen på nytt.',
            )
            return redirect('accounts:user_detail', pk=pk)

        elif action == 'freeze':
            # Frys = deaktiver kontoen OG slett aktive sesjoner i samme
            # operasjon. Uten sesjonsslettingen kan en allerede innlogget
            # bruker fortsette å jobbe til cookien utløper.
            if user.pk == request.user.pk:
                messages.error(request, 'Du kan ikke fryse din egen konto.')
                return redirect('accounts:user_detail', pk=pk)

            user.is_active = False
            user.save(update_fields=['is_active'])
            _invalidate_all_sessions(user)
            _log_user_admin_action(
                request, user, 'UPDATE',
                field_name='is_active', old_value='True', new_value='False',
            )
            messages.success(
                request,
                f'Kontoen til «{user.username}» er frosset og aktive sesjoner er avsluttet. '
                f'Bruk «Tø konto» for å reversere.',
            )
            return redirect('accounts:user_detail', pk=pk)

        elif action == 'thaw':
            user.is_active = True
            user.save(update_fields=['is_active'])
            _log_user_admin_action(
                request, user, 'UPDATE',
                field_name='is_active', old_value='False', new_value='True',
            )
            messages.success(
                request,
                f'Kontoen til «{user.username}» er tødd. Brukeren kan logge inn med samme passord.',
            )
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
    kan_slettes, slette_sperre = _kan_slettes(user, request.user)

    return render(request, 'accounts/user_detail.html', {
        'target_user': user,
        'form': form,
        'tilgang_form': tilgang_form,
        'link_form': link_form,
        'temp_password': temp_password,
        'recent_events': recent_events,
        'has_totp_device': has_totp_device,
        'kan_slettes': kan_slettes,
        'slette_sperre': slette_sperre,
    })


def _kan_slettes(target, actor):
    """Avgjør om ``actor`` har lov til å slette ``target``.

    Returnerer ``(bool, begrunnelse)``. Begrunnelsen vises i UI-et når
    sletting er sperret, slik at admin skjønner hvorfor knappen mangler.

    To sperrer:

    1. **Ikke deg selv.** Å slette egen konto midt i en sesjon etterlater et
       system uten den som skulle rydde opp.
    2. **Ikke siste admin.** Sletter man den eneste administratoren, finnes det
       ingen vei tilbake inn i brukeradministrasjonen — og etter at
       ``/django-admin/`` fjernes (S1) heller ingen nødutgang.
    """
    if target.pk == actor.pk:
        return False, 'Du kan ikke slette din egen konto.'

    if target.role == 'admin':
        andre_admins = CustomUser.objects.filter(
            role='admin', is_active=True,
        ).exclude(pk=target.pk).count()
        if andre_admins == 0:
            return False, 'Dette er den siste aktive administratoren og kan ikke slettes.'

    return True, ''


@admin_required
@require_http_methods(['POST'])
def user_delete_view(request, pk):
    """Slett en brukerkonto permanent.

    Sletting er trygt fordi alle referanser til brukeren er ``SET_NULL``:
    ``LoginEvent``, ``AuditLog``, ``Forstehjelper.user``, ``Helsepersonell.user``,
    ``Backup.created_by``, ``ModuleSettings.updated_by`` og — siden GDPR fase 4.1
    — ``VaktArkiv.importert_av``, som fryser navnet i ``importert_av_navn``.
    Historiske pasienter og arkivet beholder altså navnet på den som utførte
    arbeidet. ``core.Notification`` er ``CASCADE``: varsler til en slettet bruker
    har ingen mottaker og skal bort.

    Krever at admin skriver brukernavnet ordrett som bekreftelse. Det er en
    bevisst friksjon — sletting kan ikke angres, og knappen står vegg i vegg med
    «Frys konto», som er den reversible varianten.
    """
    user = get_object_or_404(CustomUser, pk=pk)

    tillatt, begrunnelse = _kan_slettes(user, request.user)
    if not tillatt:
        messages.error(request, begrunnelse)
        return redirect('accounts:user_detail', pk=pk)

    bekreftelse = (request.POST.get('confirm_username') or '').strip()
    if bekreftelse != user.username:
        messages.error(
            request,
            'Brukernavnet du skrev stemmer ikke. Kontoen er ikke slettet.',
        )
        return redirect('accounts:user_detail', pk=pk)

    username = user.username

    # Sesjonene må bort før raden slettes — _invalidate_all_sessions slår opp
    # på bruker-ID i sesjonsdataene, og etter delete() finnes ingen kobling å
    # slå opp på. Sesjonsradene ville da blitt liggende til de utløp.
    _invalidate_all_sessions(user)

    # Revisjonsraden skrives før slettingen slik at record_id og navnet er
    # kjent. Raden har ingen FK til brukeren og overlever derfor slettingen.
    _log_user_admin_action(
        request, user, 'DELETE',
        field_name='username', old_value=username, new_value=None,
    )

    user.delete()

    messages.success(request, f'Brukeren «{username}» er slettet permanent.')
    return redirect('accounts:user_list')
