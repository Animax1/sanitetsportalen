"""Modeller for brukerkontoer, modultilgang og innloggingshendelser."""
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.models import BaseTimeStampedModel

from .managers import CustomUserManager


class UserRole(models.TextChoices):
    ADMIN = 'admin', 'Administrator'
    LEAD = 'lead', 'Leder'
    LEAD_VIEW = 'lead_view', 'Leder (kun lesing)'
    READ_WRITE = 'read_write', 'Les/skriv'
    READ_ONLY = 'read_only', 'Kun lesing'


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Tilpasset brukermodell med roller og sikkerhetsfelter."""

    username = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Brukernavn',
    )
    email = models.EmailField(
        max_length=120,
        null=True,
        blank=True,
        verbose_name='E-post',
        help_text='Valgfritt. Brukes kun som kontaktinformasjon for admin.',
    )
    # Ett fritekstfelt, ikke for- og etternavn. Formålet er å kjenne igjen
    # personen bak et brukernavn som `superman64`, og ett felt håndterer
    # mellomnavn, doble etternavn og folk som skriver navnet sitt annerledes
    # enn en skjemadesigner forventer.
    fullt_navn = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Fullt navn',
        help_text='Valgfritt. Vises til admin for å kjenne igjen brukeren.',
    )
    # Kontotype, ikke bare et flagg. En delt konto (bil-innlogging og
    # liknende) skal aldri ha e-post, aldri kreves MFA, og aldri kunne be om
    # selvbetjent passord-reset. Håndhevingen kommer med invitasjons- og
    # reset-arbeidet; feltet legges til først slik at migrasjonen gjør én ting.
    er_delt_konto = models.BooleanField(
        default=False,
        verbose_name='Delt konto',
        help_text=(
            'Ikke-personlig konto, f.eks. en bil. Utelukkes fra selvbetjent '
            'passord-reset.'
        ),
    )
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.READ_ONLY,
        verbose_name='Rolle',
    )
    is_active = models.BooleanField(default=True, verbose_name='Aktiv')
    is_staff = models.BooleanField(default=False, verbose_name='Stab (Django Admin)')
    must_change_password = models.BooleanField(
        default=True,
        verbose_name='Må endre passord',
    )
    mfa_required = models.BooleanField(
        default=False,
        verbose_name='Krev MFA',
        help_text='Krev to-faktor-autentisering ved pålogging',
    )
    # Nøkkelen til brukerens aktive sesjon (N10). Portalen har
    # én-sesjon-per-bruker som policy; feltet gjør invalidering ved innlogging
    # til ett indeksert oppslag i stedet for en full gjennomgang av
    # sesjonstabellen. Det er en cache av policyen, ikke fasit for hvilke
    # sesjoner som finnes — sikkerhetsoperasjoner (passordbytte, admin-reset,
    # frys, sletting) gjør fortsatt full gjennomgang.
    current_session_key = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name='Aktiv sesjonsnøkkel',
    )
    failed_login_attempts = models.IntegerField(default=0, verbose_name='Mislykkede innloggingsforsøk')
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name='Låst til')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Oppdatert')
    last_login_at = models.DateTimeField(null=True, blank=True, verbose_name='Siste innlogging')

    # ── Modul-permissions (Fase 3a) ────────────────────────────────────────
    # Boolske flag som bestemmer om brukeren ser/redigerer hver portal-modul.
    # Roller (admin/lead/lead_view/read_write/read_only) styrer fortsatt
    # overordnet tilgang innenfor hver app, mens disse flaggene styrer hvilke
    # moduler som vises i dashboard og nav-meny.
    #
    # Admin (role='admin') ser alle moduler uavhengig av flagg.
    # Vi pre-registrerer alle 5 flagg i samme migrasjon for å unngå
    # fragmenterte migrasjoner når framtidige moduler aktiveres.
    kan_redigere_pasienter = models.BooleanField(
        default=False,
        verbose_name='Kan se pasientregistrering',
        help_text='Gir tilgang til /pasienter/-modulen i dashboard og nav-meny.',
    )
    kan_redigere_vakter = models.BooleanField(
        default=False,
        verbose_name='Kan se vakt-modulen',
        help_text='Reservert for fremtidig vakt-administrasjon (planlagt).',
    )
    kan_redigere_utstyr = models.BooleanField(
        default=False,
        verbose_name='Kan se utstyr-modulen',
        help_text='Reservert for fremtidig utstyrs-/lager-modul (planlagt).',
    )
    kan_se_rapport = models.BooleanField(
        default=False,
        verbose_name='Kan se rapport-modulen',
        help_text='Reservert for fremtidig rapport-/statistikk-modul (planlagt).',
    )
    kan_redigere_beredskap = models.BooleanField(
        default=False,
        verbose_name='Kan se beredskap-modulen',
        help_text=(
            'Reservert for fremtidig beredskap-/ambulanse-modul (planlagt). '
            'Krever egen GDPR-vurdering før aktivering.'
        ),
    )

    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []  # email er valgfri

    class Meta:
        verbose_name = 'Bruker'
        verbose_name_plural = 'Brukere'
        ordering = ['username']
        constraints = [
            # E-post er valgfri (NULL tillatt), men hvis satt må den være unik.
            # Betinget constraint slik at flere brukere kan ha NULL samtidig.
            models.UniqueConstraint(
                fields=['email'],
                condition=models.Q(email__isnull=False),
                name='unique_email_if_set',
            ),
        ]

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    def is_locked(self):
        """Sjekk om kontoen er midlertidig låst."""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False


class TilgangsNivaa(models.TextChoices):
    """Nivåene i ``ModulTilgang``. Stigen er ordnet, se ``NIVAA_HIERARKI``.

    ``ingen`` finnes ikke som verdi — fravær av rad *er* ingen tilgang. To
    måter å uttrykke det samme på ville før eller siden kommet i utakt.

    ``SKRIV_HANDLING`` er tomt i dag. Det finnes fordi en bil-/ambulansekonto
    skal kunne utløse en navngitt overgang (et tidsstempel) uten å kunne
    redigere fritekst, og fordi det ikke lar seg løse med en feltwhitelist
    inne i den generelle PUT-en — der er stemplingen en bivirkning av en
    redigering. Regelen er at en innskrenket aktør får et *smalt endepunkt*
    som ikke leser request-kroppen. Tas i bruk når oppdragsmodulen skrives.
    Se §3.2 i docs/BESLUTNING_ROLLEMODELLEN.md.
    """

    LES = 'les', 'Lese'
    SKRIV_HANDLING = 'skriv_handling', 'Skrive: handling'
    SKRIV_FULL = 'skriv_full', 'Skrive: full'


class ModulTilgang(BaseTimeStampedModel):
    """Én brukers tilgangsnivå på én modul.

    Erstatter de fem ``kan_redigere_*``-flaggene på ``CustomUser``. Flaggene
    var både feilnavngitt og virkningsløse: de leses kun av
    ``Module.is_visible_for()``, altså dashboard og nav-meny. En
    ``read_write``-bruker med ``kan_redigere_pasienter=False`` fikk **201 på
    ``POST /api/patients/``**. Denne tabellen er tilgangskontroll, og
    ``@modul_kreves`` håndhever den.

    **Global admin står utenfor.** ``role='admin'`` gir alt, uten rader.
    Grunnen er at de irreversible handlingene — hard-delete utenfor
    slettevinduet, nullstilling, arkiv-kollaps — ikke skal desentraliseres,
    og at en modul-admin ville vært et sted til å gi dem bort fra.

    ``modul_slug`` er ikke en FK. Modulregisteret ligger i kode
    (``core.modules``), ikke i basen, og en rad for en modul som er fjernet
    fra registeret skal bli liggende ubrukt i stedet for å blokkere
    slettingen — eller forsvinne stille med en CASCADE.
    """

    bruker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='modultilganger',
        verbose_name='Bruker',
    )
    modul_slug = models.CharField(
        max_length=64,
        verbose_name='Modul',
        help_text='Matcher Module.slug i core.modules.',
    )
    nivaa = models.CharField(
        max_length=20,
        choices=TilgangsNivaa.choices,
        verbose_name='Nivå',
    )

    class Meta:
        verbose_name = 'Modultilgang'
        verbose_name_plural = 'Modultilganger'
        ordering = ['bruker__username', 'modul_slug']
        constraints = [
            models.UniqueConstraint(
                fields=['bruker', 'modul_slug'],
                name='unik_modultilgang_per_bruker',
            ),
        ]
        # Ingen eksplisitt indeks på `bruker`: ForeignKey lager sin egen, og
        # den dekker oppslaget som skjer på hver request (alle radene for én
        # bruker). En Meta.indexes i tillegg ville gitt to identiske indekser
        # på samme kolonne — dobbel skrivekostnad, null gevinst.

    def __str__(self):
        return f'{self.bruker_id}:{self.modul_slug}={self.nivaa}'


class LoginEvent(models.Model):
    """Logg over innloggingsforsøk og MFA-hendelser."""

    # Hendelsestyper for MFA-audit
    EVENT_LOGIN = 'login'
    EVENT_MFA_SETUP_COMPLETED = 'mfa_setup_completed'
    EVENT_MFA_VERIFY_SUCCESS = 'mfa_verify_success'
    EVENT_MFA_VERIFY_FAILED = 'mfa_verify_failed'
    EVENT_MFA_BACKUP_USED = 'mfa_backup_used'
    EVENT_MFA_TRUST_COOKIE_USED = 'mfa_trust_cookie_used'
    EVENT_MFA_RESET_BY_ADMIN = 'mfa_reset_by_admin'

    EVENT_TYPE_CHOICES = [
        (EVENT_LOGIN, 'Innlogging'),
        (EVENT_MFA_SETUP_COMPLETED, 'MFA-oppsett fullført'),
        (EVENT_MFA_VERIFY_SUCCESS, 'MFA-verifisering vellykket'),
        (EVENT_MFA_VERIFY_FAILED, 'MFA-verifisering feilet'),
        (EVENT_MFA_BACKUP_USED, 'MFA backup-kode brukt'),
        (EVENT_MFA_TRUST_COOKIE_USED, 'MFA trust-cookie brukt'),
        (EVENT_MFA_RESET_BY_ADMIN, 'MFA nullstilt av admin'),
    ]

    user = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='login_events',
        verbose_name='Bruker',
    )
    username_attempt = models.CharField(max_length=64, verbose_name='Brukernavn forsøkt')
    success = models.BooleanField(verbose_name='Vellykket')
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP-adresse')
    user_agent = models.TextField(blank=True, verbose_name='User-agent')
    event_type = models.CharField(
        max_length=30,
        choices=EVENT_TYPE_CHOICES,
        default=EVENT_LOGIN,
        verbose_name='Hendelsestype',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Tidspunkt')

    class Meta:
        verbose_name = 'Innloggingshendelse'
        verbose_name_plural = 'Innloggingshendelser'
        ordering = ['-created_at']

    def __str__(self):
        status = 'OK' if self.success else 'FEIL'
        return f'{self.username_attempt} [{status}] {self.created_at}'
