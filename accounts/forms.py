"""Skjemaer for brukerkontoer."""
from django import forms
from django.contrib.auth import password_validation

from .models import CustomUser, ModulTilgang, TilgangsNivaa, UserRole

#: Hjelpetekst på rollefeltet, delt av opprettings- og redigeringsskjemaet.
#: Rollen er kontotype, ikke tilgangsnivå. Feltet hadde fem verdier fram til
#: deploy 2; de fire som beskrev tilgang ble til `bruker`, og tilgangen ligger
#: nå i modulmatrisen. Uten denne teksten leser en admin «Bruker» som «har
#: vanlig tilgang» — og det har kontoen ikke før matrisen sier noe annet.
ROLLE_HJELP = (
    'Administrator har tilgang til alt og står utenfor modulmatrisen. '
    'Bruker får kun det matrisen gir — uten en rad der ser kontoen ingen moduler.'
)


class LoginForm(forms.Form):
    """Innloggingsskjema."""
    username = forms.CharField(
        max_length=64,
        label='Brukernavn',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autofocus': True,
            'placeholder': 'Brukernavn',
            # Mobiltastatur setter stor forbokstav og autokorrigerer i vanlige
            # tekstfelt. Innlogging er ikke prosa. Backenden slår opp uten
            # hensyn til store bokstaver uansett, men her stoppes problemet
            # før det oppstår — og brukeren ser det de faktisk skrev.
            'autocapitalize': 'none',
            'autocorrect': 'off',
            'autocomplete': 'username',
            'spellcheck': 'false',
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


class GlemtPassordForm(forms.Form):
    """Be om en reset-lenke.

    Feltet er e-post og ikke brukernavn, av to grunner: brukernavnet er valgt
    av admin og er nettopp det man kan ha glemt, og en adresse er noe man
    uansett må ha tilgang til for å fullføre.

    Ingen validering av om adressen finnes — §6.7. Skjemaet skal ikke kunne
    skille en adresse med konto fra en uten.
    """
    email = forms.EmailField(
        label='E-postadressen din',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autofocus': True,
            'placeholder': 'navn@eksempel.no',
            'autocapitalize': 'none',
            'autocorrect': 'off',
            'autocomplete': 'email',
            'spellcheck': 'false',
        }),
    )


class SettPassordForm(forms.Form):
    """Brukeren setter sitt eget passord fra en invitasjonslenke.

    Ingen `old_password`: brukeren har ikke noe passord ennå — kontoen er
    opprettet med `set_unusable_password()`. Validatorene er de samme som ved
    passordbytte, så reglene er like uansett hvilken vei man kom inn.
    """
    new_password1 = forms.CharField(
        label='Velg et passord',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'autofocus': True,
        }),
    )
    new_password2 = forms.CharField(
        label='Gjenta passordet',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    def clean_new_password2(self):
        p1 = self.cleaned_data.get('new_password1', '')
        p2 = self.cleaned_data.get('new_password2', '')
        if not p2:
            raise forms.ValidationError('Du må gjenta passordet.')
        if p1 and p1 != p2:
            raise forms.ValidationError('Passordene stemmer ikke overens.')
        password_validation.validate_password(p2)
        return p2


class AdminUserCreateForm(forms.ModelForm):
    """Skjema for admin til å opprette ny bruker.

    **Kontotypen velges, den krysses ikke av.** Fram til 29. aug. 2026 var det
    en avkrysningsboks for «delt konto», og en bil måtte i tillegg opprettes
    som `Enhet` og kobles til kontoen i et tredje steg inne i oppdragsmodulen.
    André kalte det tullete, og det var det: tre handlinger for én bil, med to
    av dem på en helt annen side enn den første.

    Nå er det ett valg med tre verdier, og det som skal lages blir laget:

    ===============  =====================================================
    Person           Personlig konto. E-post og navn, kan inviteres
    Delt konto       Ingen personlig eier. F.eks. en felles PC på sykestua
    Bil/ambulanse    Delt konto **og** en `Enhet`, opprettet i samme steg
    ===============  =====================================================

    Ett valg framfor «avkrysningsboks pluss et navnefelt» er med vilje: to
    kontroller som overlapper er nettopp det som gjorde `role` til et rot.
    Da kunne man krysse av for delt konto og *likevel* skrive et enhetsnavn,
    eller la være, og skjemaet måtte gjette hva som var ment.

    **Valideringen nekter e-post og navn på begge de delte typene** i stedet
    for å la dem stå tomme — ellers må unntaket huskes hver gang, og den dagen
    noen legger inn en kontakt-e-post på en bil, er det plutselig en lateral
    vei inn i systemet via passord-reset.

    **Enheten gir fortsatt ingen tilgang.** Den avgjør hvilket grensesnitt
    kontoen får; hva den har lov til settes i matrisen på samme side. Det er
    §7.3-skillet, og det står uendret — det som ble slått sammen her er to
    *opprettelser*, ikke tilgang og domenedata.
    """

    PERSON = 'person'
    DELT = 'delt'
    ENHET = 'enhet'
    KONTOTYPER = (
        (PERSON, 'Person'),
        (DELT, 'Delt konto (felles innlogging)'),
        (ENHET, 'Bil eller ambulanse'),
    )

    kontotype = forms.ChoiceField(
        choices=KONTOTYPER,
        initial=PERSON,
        label='Kontotype',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text=(
            'Bil eller ambulanse oppretter også enheten, og knytter den til '
            'kontoen. Enheten avgjør hvilket grensesnitt kontoen får — ikke '
            'hva den har lov til.'
        ),
    )
    enhetsnavn = forms.CharField(
        required=False,
        max_length=64,
        label='Enhetsnavn',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Haugesund 56',
        }),
        help_text='Navnet som brukes på samband. Ikke det samme som brukernavnet.',
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'fullt_navn', 'email', 'role',
                  'mfa_required']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'fullt_navn': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fornavn Etternavn',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kreves for invitasjon',
            }),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'mfa_required': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'er_delt_konto': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'username': 'Brukernavn',
            'fullt_navn': 'Fullt navn',
            'email': 'E-post',
            'role': 'Rolle',
            'mfa_required': 'Krev to-faktor (MFA)',
            'er_delt_konto': 'Delt konto (bil e.l.)',
        }
        help_texts = {
            'role': ROLLE_HJELP,
            'email': 'Invitasjonslenken sendes hit. Kan stå tom for delt konto.',
            'fullt_navn': 'Så du kjenner igjen hvem kontoen tilhører.',
            'mfa_required': (
                'Brukeren må sette opp autentiseringsapp ved første '
                'pålogging. Kan ikke kombineres med delt konto.'
            ),
            'er_delt_konto': (
                'Ikke-personlig konto. Får ikke e-post, navn eller '
                'selvbetjent passord-reset — admin setter passordet.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        self.fields['fullt_navn'].required = False

    def clean_username(self):
        """Konvensjon: `fornavn.etternavn`, alltid små bokstaver.

        Innlogging er ufølsom for store bokstaver uansett, men å lagre én
        skrivemåte holder auditloggen konsistent — og sikrer at to kontoer
        aldri kan skille seg kun på store bokstaver, som er det ene tilfellet
        backenden må falle tilbake til nøyaktig treff for.
        """
        return (self.cleaned_data.get('username') or '').strip().lower()

    def clean(self):
        data = super().clean()
        type_ = data.get('kontotype') or self.PERSON
        delt = type_ in (self.DELT, self.ENHET)

        # `er_delt_konto` er ikke lenger en avkrysningsboks — den utledes av
        # valget. Én kilde, så «delt konto uten enhetsnavn» og «enhetsnavn
        # uten delt konto» ikke kan oppstå i det hele tatt.
        data['er_delt_konto'] = delt

        if delt:
            if data.get('email'):
                self.add_error('email', 'En delt konto skal ikke ha e-post.')
            if data.get('fullt_navn'):
                self.add_error(
                    'fullt_navn',
                    'En delt konto har ingen personlig eier. La feltet stå tomt.',
                )
            if data.get('mfa_required'):
                # Samme regel som ved redigering: en bil-konto deler enhet
                # mellom folk som kommer og går, så MFA ville betydd én delt
                # TOTP-enhet eller ingen vei inn.
                self.add_error(
                    'mfa_required',
                    'MFA kan ikke kreves på en delt konto — enheten deles av flere.',
                )

        navn = (data.get('enhetsnavn') or '').strip()
        data['enhetsnavn'] = navn

        if type_ == self.ENHET:
            if not navn:
                self.add_error(
                    'enhetsnavn',
                    'En bil eller ambulanse må ha et enhetsnavn.',
                )
            else:
                # Sjekkes her, ikke i viewet: en unik-feil fra databasen ville
                # kommet etter at kontoen var opprettet, og etterlatt en konto
                # uten enhet.
                from oppdrag.models import Enhet  # noqa: WPS433
                if Enhet.objects.filter(navn=navn).exists():
                    self.add_error(
                        'enhetsnavn', f'Enheten «{navn}» finnes allerede.')
        elif navn:
            self.add_error(
                'enhetsnavn',
                'Enhetsnavn gjelder kun for bil eller ambulanse.',
            )

        return data

    def save(self, commit=True):
        """Sett `er_delt_konto` fra kontotypen. Enheten lages i viewet.

        Enheten kan ikke opprettes her: den trenger brukerens pk, og
        `commit=False` er nettopp stien opprettingsviewet bruker for å velge
        mellom invitasjon og midlertidig passord før lagring.
        """
        bruker = super().save(commit=False)
        bruker.er_delt_konto = bool(self.cleaned_data.get('er_delt_konto'))
        if commit:
            bruker.save()
        return bruker

    def skal_lage_enhet(self):
        """(navn,) hvis kontoen er en bil eller ambulanse, ellers ``None``."""
        if self.cleaned_data.get('kontotype') == self.ENHET:
            return self.cleaned_data.get('enhetsnavn')
        return None

    def clean_email(self):
        # Normaliser tom streng til None slik at NULL lagres i databasen.
        # NB: modellfeltet er null=True, så ModelForm setter empty_value=None på
        # skjemafeltet. Tom e-post gir da None — ikke '' — og en default i .get()
        # slår aldri inn. Derfor `or ''` og ikke `.get('email', '')`.
        email = (self.cleaned_data.get('email') or '').strip()
        return email or None


class AdminUserEditForm(forms.ModelForm):
    """Skjema for admin til å redigere eksisterende bruker.

    Modul-tilgang settes **ikke** her, men i ``ModulTilgangForm``. De fem
    ``kan_redigere_*``-boksene lå tidligere på dette skjemaet; de styrte kun
    meny og dashboard, aldri et endepunkt, og etter at synligheten begynte å
    lese ``ModulTilgang`` gjorde de ingenting i det hele tatt. Feltene står
    på modellen til deploy 3 av rollback-hensyn, men de vises ikke lenger —
    en boks som ikke gjør noe er verre enn ingen boks.
    """

    class Meta:
        model = CustomUser
        fields = [
            'fullt_navn', 'email', 'role', 'is_active', 'mfa_required',
            'er_delt_konto',
        ]
        widgets = {
            'fullt_navn': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fornavn Etternavn',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Valgfritt',
            }),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'mfa_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'er_delt_konto': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'fullt_navn': 'Fullt navn',
            'email': 'E-post (valgfritt)',
            'role': 'Rolle',
            'is_active': 'Aktiv konto',
            'er_delt_konto': 'Delt konto (bil e.l.)',
            'mfa_required': 'Krev to-faktor (MFA)',
        }
        help_texts = {
            'role': ROLLE_HJELP,
            'email': 'Brukes kun som kontaktinformasjon. Kan stå tom.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        self.fields['fullt_navn'].required = False

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip()
        return email or None

    def clean(self):
        """Samme kontotype-regler som ved oppretting.

        Uten dette kunne en konto opprettes som personlig og gjøres delt i
        etterkant — med e-post og navn i behold. Da ville reset-lenken hatt en
        vei til en delt innboks likevel, og hele poenget med flagget falt bort.
        """
        data = super().clean()
        if data.get('er_delt_konto'):
            if data.get('email'):
                self.add_error('email', 'En delt konto skal ikke ha e-post.')
            if data.get('fullt_navn'):
                self.add_error(
                    'fullt_navn',
                    'En delt konto har ingen personlig eier. La feltet stå tomt.',
                )
        return data

    def clean_mfa_required(self):
        """MFA kan ikke kreves på en delt konto.

        En bil-konto deler enhet mellom folk som kommer og går. Krever man
        MFA, må én TOTP-enhet deles av alle — eller ingen kommer inn. Regelen
        håndheves her, ikke bare i grensesnittet, slik at den ikke kan omgås
        ved å poste skjemaet direkte.
        """
        paakrevd = self.cleaned_data.get('mfa_required')
        # `self.data` og ikke `cleaned_data`: `er_delt_konto` er ikke
        # nødvendigvis renset ennå når feltvalideringen kjører, og admin kan
        # sette begge i samme lagring.
        blir_delt = bool(self.data.get('er_delt_konto'))
        er_delt = blir_delt or (self.instance and self.instance.er_delt_konto)
        if paakrevd and er_delt:
            raise forms.ValidationError(
                'MFA kan ikke kreves på en delt konto — enheten deles av flere.'
            )
        return paakrevd


class ModulTilgangForm(forms.Form):
    """Matrise modul × nivå. Erstatter de fem avkrysningsboksene.

    **Feltene genereres fra ``get_all_modules()``.** De fem boksene var
    hardkodet i malen, så hver ny modul krevde en redigering der i tillegg til
    et nytt felt på ``CustomUser``. Nå følger matrisen registeret av seg selv.

    ``admin_only``-moduler er utelatt: de gates av global admin og bruker ikke
    ``ModulTilgang`` i det hele tatt. Å vise dem ville antydet at nivået betyr
    noe for dem.

    ``skriv_handling`` tilbys **ikke** i grensesnittet ennå. Nivået finnes i
    modellen — det er derfor det ikke trengs en migrasjon den dagen det tas i
    bruk — men det er tomt inntil en modul har et handling-endepunkt å bruke
    det på (§3.2/§10.2). Et nivå som ikke gir noe er lett å dele ut i god tro,
    og gir automatisk mer den dagen det fylles.
    """

    PREFIKS = 'modul_'
    INGEN = ''

    # Nivåene admin kan velge i dag. Rekkefølgen er stigens.
    VALGBARE = ('les', 'skriv_full')

    def __init__(self, *args, bruker=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.bruker = bruker
        self._naavaerende = self._les_naavaerende(bruker)

        for modul in self.moduler():
            navn = self.PREFIKS + modul.slug
            har = self._naavaerende.get(modul.slug, self.INGEN)
            valg = [(self.INGEN, 'Ingen tilgang')]
            valg += [(v, l) for v, l in TilgangsNivaa.choices if v in self.VALGBARE]
            # Et nivå brukeren allerede har, men som ikke tilbys, må stå i
            # lista — ellers ville et lagre-trykk stille fjernet det.
            if har and har not in [v for v, _ in valg]:
                valg.append((har, dict(TilgangsNivaa.choices).get(har, har)))
            self.fields[navn] = forms.ChoiceField(
                choices=valg,
                required=False,
                initial=har,
                label=modul.name,
                help_text=modul.description,
                widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
            )

    @staticmethod
    def moduler():
        """Modulene matrisen dekker, i registerets rekkefølge."""
        from core.modules import get_all_modules
        return [m for m in get_all_modules() if not m.admin_only]

    @staticmethod
    def _les_naavaerende(bruker):
        if bruker is None or bruker.pk is None:
            return {}
        return dict(
            ModulTilgang.objects.filter(bruker=bruker)
            .values_list('modul_slug', 'nivaa')
        )

    def rader(self):
        """(felt, nåværende nivå) for malen, så den slipper å slå opp navn."""
        for modul in self.moduler():
            yield self[self.PREFIKS + modul.slug]

    def endringer(self):
        """[(modul_slug, fra, til)] for det som faktisk endres.

        Returneres slik at kalleren kan skrive én auditrad per endring. Uten
        den er en tilgangsendring usporbar — og det å gi noen skrivetilgang
        er nettopp det man vil kunne se i ettertid.
        """
        ut = []
        for modul in self.moduler():
            navn = self.PREFIKS + modul.slug
            # **Fravær av nøkkel er ikke «velg ingen».** Et felt som ikke ble
            # sendt inn i det hele tatt skal la tilgangen stå. Uten dette
            # ville enhver innsending som utelater matrisen — et delvis
            # skjema, et skript, en test — stille fjernet all modultilgang.
            # Nettleseren sender alltid alle select-ene, så den vanlige veien
            # er upåvirket.
            if navn not in self.data:
                continue
            fra = self._naavaerende.get(modul.slug, self.INGEN)
            til = self.cleaned_data.get(navn, self.INGEN)
            if fra != til:
                ut.append((modul.slug, fra, til))
        return ut

    def save(self, bruker=None):
        """Skriv matrisen. Returnerer endringene, for audit.

        Sletter raden i stedet for å lagre en tom verdi: fravær av rad *er*
        ingen tilgang, og en 'ingen'-verdi ville vært en andre måte å si det
        samme på.
        """
        from django.db import transaction
        from core.auth_decorators import tom_tilgangscache

        bruker = bruker or self.bruker
        endringer = self.endringer()

        with transaction.atomic():
            for slug, _fra, til in endringer:
                if til == self.INGEN:
                    ModulTilgang.objects.filter(
                        bruker=bruker, modul_slug=slug).delete()
                else:
                    ModulTilgang.objects.update_or_create(
                        bruker=bruker, modul_slug=slug,
                        defaults={'nivaa': til},
                    )

        # Uten dette ville en visning i samme request lest det gamle svaret.
        tom_tilgangscache(bruker)
        return endringer


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
