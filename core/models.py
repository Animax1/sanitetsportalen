"""Felles modeller for sanitetsportalen.

Inneholder:
- ``BaseTimeStampedModel``: abstrakt mixin med created_at/updated_at.
- ``ModuleSettings``: konfigurasjon per modul (enabled-toggle, backup-flagg).
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.sortering import Norsk


class BaseTimeStampedModel(models.Model):
    """Abstrakt baseklasse som gir created_at + updated_at automatisk.

    Bruk:
        class MinModell(BaseTimeStampedModel):
            navn = models.CharField(...)

    Feltene oppdateres automatisk av Django og skal ikke settes manuelt.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Opprettet',
        help_text='Tidspunktet raden ble opprettet.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Sist oppdatert',
        help_text='Tidspunktet raden sist ble endret.',
    )

    class Meta:
        abstract = True


class ModuleSettings(models.Model):
    """Database-styrt konfigurasjon per modul.

    Hver rad tilsvarer én modul i ``core.modules.get_all_modules()``. Admin
    kan toggle ``enabled`` på/av i sanntid uten deploy. Kjernemoduler
    (``Module.is_core=True``) kan ikke deaktiveres — det håndheves i admin
    via ``ModuleSettingsAdmin``.

    Hva som blir tatt backup av avgjøres av backup-registeret (hvilke moduler
    som har en handler) og av ``core.Backupplan`` (om, og hvor ofte) — ikke
    her. ``backup_enabled`` sto her til 26. sep. 2026 uten noen virkning
    (D4): en bryter som ikke gjør noe ser ut som en beslutning. Kolonnen står
    igjen i basen til neste deploy, se migrasjon ``0012``.
    """

    slug = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Modul-slug',
        help_text='Matcher Module.slug i core.modules (ofte lik Django app-label).',
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name='Aktivert',
        help_text=(
            'Hvis avkrysset vises modulen i dashboard og nav-meny for brukere '
            'som har riktig permission-flagg. Kjernemoduler kan ikke deaktiveres.'
        ),
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Admin-notat',
        help_text='Valgfri kommentar — f.eks. årsak til at modulen er deaktivert.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Sist endret',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name='Sist endret av',
    )

    class Meta:
        verbose_name = 'Modulinnstilling'
        verbose_name_plural = 'Modulinnstillinger'
        ordering = ['slug']

    def __str__(self) -> str:
        status = 'aktiv' if self.enabled else 'deaktivert'
        return f'{self.slug} ({status})'

    @classmethod
    def get_enabled_slugs(cls) -> set[str]:
        """Returner sett med slugs for moduler som er ``enabled=True``.

        Moduler som ikke har en rad i tabellen behandles som **deaktivert**.
        ``ensure_defaults_exist()`` sørger for at en rad finnes for hver
        registrert modul, og kalles fra core.apps.CoreConfig.ready().
        """
        return set(cls.objects.filter(enabled=True).values_list('slug', flat=True))

    @classmethod
    def ensure_defaults_exist(cls, modell=None, portalmodell=None) -> None:
        """Sørg for at hver registrert modul har en rad i tabellen.

        Idempotent: kjører ``get_or_create`` for hver modul. Kalles fra
        ``CoreConfig.ready()`` etter at app-registret er ferdig lastet.

        Kjernemoduler får ``enabled=True`` per default og kan ikke deaktiveres.
        Andre moduler får ``enabled=True`` ved første registrering — admin må
        eksplisitt skru av.

        ``modell`` er den historiske modellen fra ``post_migrate``. Den kjenner
        feltene tabellen har *på det migrasjonspunktet*; ``cls`` kjenner dagens.
        De er ulike når noen migrerer til et eldre punkt — og da ga dagens
        modell en rad uten ``backup_enabled`` mot en kolonne som ennå var
        ``NOT NULL`` uten standard (26. sep. 2026, funnet av migrasjonsprøvene).
        """
        # Lazy import: modules.py importerer fra denne fila, så vi kan ikke
        # importere på toppnivå.
        from core.modules import get_all_modules  # noqa: WPS433

        modell = modell or cls
        for module in get_all_modules():
            _, ny = modell.objects.get_or_create(
                slug=module.slug,
                defaults={'enabled': True},
            )
            # **En ny modul kommer inn i alle portaler** (17. okt. 2026), med
            # taket på toppen — samme regel som `enabled=True` over: admin tar
            # den ut der den ikke skal være. Bare når raden er ny: en modul admin
            # har tatt ut av en portal, skal ikke komme tilbake ved neste deploy.
            if ny and portalmodell is not None:
                portalmodell.legg_i_alle_portaler(module.slug)


class Backupplan(models.Model):
    """Hvor ofte, hvordan og hvor mange — for én modul eller for hele basen.

    Én rad per registrert backup-handler, pluss ``full`` for hele databasen og
    ``standard``, som er malen modulene arver. Erstatter
    ``ModuleBackupConfig`` (13. sep. 2026), som hadde intervallet som et
    nedtrekk med sju faste valg og ingen måte å si «skriv en fil uansett».

    **Tre moduser, og skillet mellom de to aktive er verdt å forstå:**
    ``ved_endring`` serialiserer og sammenligner hash — er innholdet likt
    forrige fil, skrives ingenting. Den er effektiv, men *stum*: ingen ny fil
    kan bety «ingenting har endret seg» eller «jobben er død», og de to ser
    like ut utenfra. ``alltid`` skriver uansett, og er dermed en puls der et
    hull i rekka er en synlig feil.

    Derfor har raden **to** tidsstempler: ``sist_sjekket_at`` settes ved hver
    vurdering, ``sist_fil_at`` bare når det faktisk ble skrevet noe. Uten det
    første ville «stille» og «stoppet» vært umulig å skille, uansett modus.

    **Intervallet lagres som verdi + enhet, ikke som minutter.** Setter du
    «3 døgn» og får «4320 minutter» tilbake neste gang siden åpnes, må du
    regne for å lese din egen innstilling. ``intervall_min`` regner det ut når
    klokka trenger det.

    **Arv er ikke en snarvei, det er poenget.** Med seks modulfiler er
    forskjellen på å vedlikeholde tre tall og atten. ``folger_standard``
    gjelder bare modulene; ``standard`` og ``full`` styrer alltid seg selv.
    Bare modus, intervall og cap arves — tidsstemplene hører til raden selv.
    """

    MODUS_AV = 'av'
    MODUS_VED_ENDRING = 'ved_endring'
    MODUS_ALLTID = 'alltid'
    MODUS_VALG = [
        (MODUS_AV, 'Av'),
        (MODUS_VED_ENDRING, 'Ved endring'),
        (MODUS_ALLTID, 'Alltid'),
    ]

    ENHET_MINUTT = 'minutt'
    ENHET_TIME = 'time'
    ENHET_DOGN = 'dogn'
    ENHET_VALG = [
        (ENHET_MINUTT, 'minutter'),
        (ENHET_TIME, 'timer'),
        (ENHET_DOGN, 'døgn'),
    ]
    #: Enhet → minutter. Eneste stedet omregningen står.
    ENHET_MINUTTER = {ENHET_MINUTT: 1, ENHET_TIME: 60, ENHET_DOGN: 1440}

    #: Malen modulene arver. Er ikke en backup-handler og tas aldri backup av.
    STANDARD_SLUG = 'standard'
    #: Hele databasen. Har egen plan, arver aldri standarden.
    FULL_SLUG = 'full'
    #: Sluggene som styrer seg selv.
    EGENRÅDIGE = (STANDARD_SLUG, FULL_SLUG)

    #: Startverdier for slugger som ikke skal følge standarden.
    #: Arkivene endres én gang per arrangement — å serialisere hele
    #: arkivtabellen hvert 10. minutt for å finne ut at ingenting skjedde, er
    #: å bruke CPU på å bekrefte stillstand.
    OPPSTARTSVERDIER = {
        STANDARD_SLUG: (MODUS_VED_ENDRING, 10, ENHET_MINUTT, 50, False),
        FULL_SLUG:     (MODUS_ALLTID,      24, ENHET_TIME,    7, False),
        'arkiv':         (MODUS_VED_ENDRING, 6, ENHET_TIME,  20, False),
        'oppdrag_arkiv': (MODUS_VED_ENDRING, 6, ENHET_TIME,  20, False),
    }

    slug = models.CharField(
        max_length=64, unique=True, verbose_name='Slug',
        help_text='Modul-slug, «full» for hele databasen, eller «standard» for malen.',
    )
    folger_standard = models.BooleanField(
        default=True, verbose_name='Følger standardplanen',
        help_text='Av for å gi denne modulen egne innstillinger.',
    )
    modus = models.CharField(
        max_length=16, choices=MODUS_VALG, default=MODUS_VED_ENDRING,
        verbose_name='Modus',
    )
    intervall_verdi = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)],
        verbose_name='Intervall',
    )
    intervall_enhet = models.CharField(
        max_length=8, choices=ENHET_VALG, default=ENHET_TIME,
        verbose_name='Enhet',
    )
    behold = models.PositiveIntegerField(
        default=50, validators=[MinValueValidator(1)],
        verbose_name='Behold filer',
        help_text=(
            'Eldste filer på Railway-volumet slettes når antallet overstiges. '
            'Gjelder ikke kopiene hos Scaleway — de styres av bucketens '
            'livssyklusregel. Pre-restore-snapshots telles ikke.'
        ),
    )
    sist_sjekket_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Sist vurdert')
    sist_fil_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Siste fil')
    sist_resultat = models.CharField(
        max_length=200, blank=True, default='', verbose_name='Siste resultat')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Backupplan'
        verbose_name_plural = 'Backupplaner'
        ordering = ['slug']

    def __str__(self) -> str:
        if self.modus == self.MODUS_AV:
            return f'{self.slug} (av)'
        return f'{self.slug} ({self.get_modus_display().lower()}, {self.intervall_tekst()})'

    # ── Intervall ────────────────────────────────────────────────────────────

    @property
    def intervall_min(self) -> int:
        """Intervallet i minutter. Minst 1 — et intervall på 0 ville betydd
        «kjør ved hvert tikk», og den betydningen har ``modus`` allerede."""
        return max(1, self.intervall_verdi * self.ENHET_MINUTTER.get(
            self.intervall_enhet, 1))

    #: Determinativ og entallsform per enhet. «Time» er felleskjønn og får
    #: «hver»; «minutt» og «døgn» er intetkjønn og får «hvert». Å utlede det
    #: av flertallsformen i ``ENHET_VALG`` ga «hver døgn» og «hvert 6. time».
    ENHET_ENTALL = {
        ENHET_MINUTT: ('hvert', 'minutt'),
        ENHET_TIME: ('hver', 'time'),
        ENHET_DOGN: ('hvert', 'døgn'),
    }

    def intervall_tekst(self) -> str:
        """«hver time», «hvert 10. minutt», «hvert 3. døgn»."""
        determinativ, ord = self.ENHET_ENTALL.get(
            self.intervall_enhet, ('hvert', self.intervall_enhet))
        if self.intervall_verdi == 1:
            return f'{determinativ} {ord}'
        return f'{determinativ} {self.intervall_verdi}. {ord}'

    # ── Arv ──────────────────────────────────────────────────────────────────

    @property
    def arver(self) -> bool:
        """Om raden henter modus, intervall og cap fra standardplanen."""
        return self.folger_standard and self.slug not in self.EGENRÅDIGE

    def gjeldende(self) -> 'Backupplan':
        """Raden som faktisk bestemmer — seg selv, eller standardplanen.

        Finnes ingen standardrad ennå (en helt fersk base før første tikk),
        er svaret raden selv. Å opprette den her ville gjort en lesning til en
        skriving, og denne kalles fra visninger.
        """
        if not self.arver:
            return self
        standard = type(self).objects.filter(slug=self.STANDARD_SLUG).first()
        return standard or self

    @property
    def modus_effektiv(self) -> str:
        return self.gjeldende().modus

    @property
    def intervall_min_effektiv(self) -> int:
        return self.gjeldende().intervall_min

    @property
    def behold_effektiv(self) -> int:
        return self.gjeldende().behold

    @property
    def eget_modusvalg_overstyres(self) -> bool:
        """Står det en annen modus i nedtrekket enn den som faktisk gjelder?

        Skjemaet lagrer radens egen modus også når haken «Følg standardplanen»
        står på, og da gjelder standardens. Velger man «Av» med haken på,
        lagres «Av» uten at noe slås av — og ingenting sa fra (André, 4. okt.
        2026: «når jeg skal sette planen av så får jeg av og til dette»).
        Egen funksjon og ikke en `if` i viewet, så regelen lar seg prøve.
        """
        return self.arver and self.modus != self.gjeldende().modus

    @property
    def skriver_alltid(self) -> bool:
        """«Alltid» betyr at hash-skippet slås av for denne planen."""
        return self.modus_effektiv == self.MODUS_ALLTID

    # ── Oppslag ──────────────────────────────────────────────────────────────

    @classmethod
    def hent(cls, slug: str) -> 'Backupplan':
        """Hent planen for slugen, opprett med riktige startverdier ved behov.

        Idempotent. Kalles av klokka når den ser en handler uten plan — at
        registeret er fasit og ikke tabellen, er grunnen til at en nyregistrert
        modul får dekning uten at noen åpner en adminside først.
        """
        modus, verdi, enhet, behold, folger = cls.OPPSTARTSVERDIER.get(
            slug, (cls.MODUS_VED_ENDRING, 10, cls.ENHET_MINUTT, 50, True))
        obj, _ = cls.objects.get_or_create(slug=slug, defaults={
            'modus': modus, 'intervall_verdi': verdi, 'intervall_enhet': enhet,
            'behold': behold, 'folger_standard': folger,
        })
        return obj

    @classmethod
    def standardplanen(cls) -> 'Backupplan':
        return cls.hent(cls.STANDARD_SLUG)


class Notification(models.Model):
    """Generisk varsel som vises i bjella i topp-nav.

    Fase 5: Første bruksområde er pasient-tildeling (modul ``patients``),
    men modellen er designet generisk slik at framtidige moduler (vakter,
    utstyr, beredskap) kan opprette varsler uten endring i denne fila.

    Bruks-API: ``core.notifications.notify(user, module_slug, kind, ...)``.

    Felt-beskrivelse:
        user         — mottaker (FK til CustomUser)
        module_slug  — hvilken modul som lagde varselet ('patients', 'vakter', ...)
        kind         — fri streng som identifiserer varseltypen for filter
                       og dedup ('patient_assigned', 'patient_transferred_away',
                       'shift_assigned', osv.)
        level        — alvorlighetsgrad. ``info`` (default) er grønn,
                       ``warning`` gul, ``critical`` rød. Brukes som hook
                       for fremtidige UI-features (badge-farge, lyd, push).
                       Per Fase 5 vises alle varsler likt i bjella.
        title        — kort overskrift (vises fett i liste)
        message      — detaljtekst (under tittel)
        url          — hvor brukeren skal sendes ved klikk (relativ URL)
        is_read      — om mottakeren har åpnet eller markert som lest
        created_at   — når varselet ble opprettet
    """

    LEVEL_INFO = 'info'
    LEVEL_WARNING = 'warning'
    LEVEL_CRITICAL = 'critical'
    LEVEL_CHOICES = [
        (LEVEL_INFO, 'Info'),
        (LEVEL_WARNING, 'Advarsel'),
        (LEVEL_CRITICAL, 'Kritisk'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Mottaker',
    )
    # Portalen varselet gjelder (17. okt. 2026, `docs/BESLUTNING_PORTALER.md`
    # §4.14). Bjella står utenfor portalene — kontoen er global — så varselet
    # må selv si hvor det hører til. Tom for varsler fra før portalene fantes.
    portal = models.ForeignKey(
        'core.Vaktportal', on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name='Portal',
    )
    module_slug = models.CharField(
        max_length=64,
        db_index=True,
        verbose_name='Modul',
        help_text='Slug for modulen som lagde varselet.',
    )
    kind = models.CharField(
        max_length=64,
        verbose_name='Varseltype',
        help_text='Maskinell identifikator for varseltypen (brukes til filter og dedup).',
    )
    level = models.CharField(
        max_length=16,
        choices=LEVEL_CHOICES,
        default=LEVEL_INFO,
        verbose_name='Nivå',
        help_text=(
            'Alvorlighetsgrad. Reservert for fremtidige UI-features '
            '(badge-farge, lyd, push). Per Fase 5 vises alle likt.'
        ),
    )
    title = models.CharField(
        max_length=200,
        verbose_name='Tittel',
    )
    message = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Melding',
    )
    url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Lenke',
        help_text='Relativ URL som brukeren sendes til ved klikk.',
    )
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Lest',
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Lest tidspunkt',
        help_text='Settes til timezone.now() når brukeren markerer varselet som lest.',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Opprettet',
    )

    class Meta:
        verbose_name = 'Varsel'
        verbose_name_plural = 'Varsler'
        ordering = ['-created_at']
        indexes = [
            # Bjelle-count: hent ulest pr. bruker, ferskeste først
            models.Index(
                fields=['user', 'is_read', '-created_at'],
                name='core_notif_user_read_idx',
            ),
            # Filter pr. modul: framtidig moduldropdown i varselliste
            models.Index(
                fields=['user', 'module_slug', '-created_at'],
                name='core_notif_user_module_idx',
            ),
        ]

    def __str__(self) -> str:
        status = 'lest' if self.is_read else 'ulest'
        return f'[{self.module_slug}] {self.title} ({status})'


class Tilhorighet(BaseTimeStampedModel):
    """En tilhørighet — et korps, eller «annet» som «Leger» (17. okt. 2026).

    `docs/BESLUTNING_PORTALER.md` §4.3. **Én felles katalog**, ikke en liste
    per portal: «HGSD» finnes én gang. Portalen velger hvilke tilhørigheter som
    er med (`Vaktportal.tilhorigheter`), og det ene valget styrer to ting:
    moderatorens brukerliste, og korpslista i vaktlista (bare `type='korps'`).

    **Var `vaktliste.Korps`.** Tabellen heter fortsatt `vaktliste_korps`, av
    samme grunn som `patients_appsetting`: i release-vinduet står gammel kode og
    leser den, og en omdøpt tabell ville gitt 500 der. `core` eier den fordi
    kontoene skal kunne ha en tilhørighet, og `accounts`/`core` får ikke
    importere en modul. Vaktlista kaller den fortsatt `Korps`.

    **Bare global admin oppretter og endrer** (beslutning 10): katalogen er
    felles, og en endring i den gjelder alle portaler.
    """

    KORPS = 'korps'
    ANNET = 'annet'
    TYPE_VALG = [(KORPS, 'Korps'), (ANNET, 'Annet')]

    navn = models.CharField(max_length=120, unique=True, verbose_name='Navn')
    kortnavn = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Kortnavn',
        help_text='Vises i trange kolonner, f.eks. «HGSD». Valgfritt.',
    )
    er_aktiv = models.BooleanField(
        default=True,
        verbose_name='Aktiv',
        help_text='Inaktive korps skjules i nedtrekkslister, men beholdes '
                  'på mannskapet som allerede tilhører dem.',
    )
    # `db_default`: gammel kode lager korps uten feltet i release-vinduet.
    type = models.CharField(
        max_length=16, choices=TYPE_VALG, default=KORPS, db_default=KORPS,
        verbose_name='Type',
        help_text='«Korps» står i vaktlista; «Annet» — som «Leger» — bare i brukerlistene.')

    class Meta:
        db_table = 'vaktliste_korps'
        verbose_name = 'Tilhørighet'
        verbose_name_plural = 'Tilhørigheter'
        ordering = [Norsk('navn')]

    def __str__(self) -> str:
        return self.navn


class Kontotilhorighet(models.Model):
    """At en konto hører til en tilhørighet (17. okt. 2026). En konto kan ha flere.

    Domenedata, ikke tilgang — samme skille som `Mannskap.user`. Moderatoren ser
    kontoene med portalens tilhørigheter; det gir ingen tilgang i seg selv.
    """

    bruker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='tilhorigheter', verbose_name='Bruker')
    # PROTECT, som `Mannskap.korps`: en tilhørighet noen har, forsvinner ikke under dem.
    tilhorighet = models.ForeignKey(
        Tilhorighet, on_delete=models.PROTECT,
        related_name='kontoer_med', verbose_name='Tilhørighet')

    class Meta:
        verbose_name = 'Kontoens tilhørighet'
        verbose_name_plural = 'Kontoenes tilhørigheter'
        constraints = [
            models.UniqueConstraint(fields=['bruker', 'tilhorighet'],
                                    name='en_kontotilhorighet_per_par'),
        ]

    def __str__(self):
        return f'{self.bruker_id}:{self.tilhorighet_id}'


class Vaktportal(models.Model):
    """Én portal — et miljø som kjører sine egne vakter (`docs/BESLUTNING_PORTALER.md`).

    «Brann» kjører kamp 1–15, «Landsskytter» ett stevne i året, og de skal ikke
    se hverandres mannskap, pasienter eller oppdrag. Portalen ligger **over**
    vakta: hver vakt hører til én portal, og hver portal har høyst én aktiv vakt
    (`Vakt.Meta.constraints`).

    **Heter `Vaktportal` i koden og «portal» på skjermen.** «portal» betyr
    allerede produktet i `base_portal.html`, `portal-utils.js` og `PORTAL_MILJO`;
    ett ord for to ting gjør `grep` ubrukelig.

    **Ingen peker til aktiv vakt her** (beslutning 19). En `aktiv_vakt`-FK ville
    gitt sykelen `Vaktportal → Vakt → Vaktportal`, og `utled_restore_models`
    legger sykler bakerst — i `portal`-handleren, som gjenopprettes først. Den
    aktive vakta er `Vakt.er_aktiv`, og databasen håndhever at det er én.

    Slettes ikke når den har vakter (`Vakt.portal` er `PROTECT`); den
    deaktiveres. Bærer ingen personopplysninger.
    """

    navn = models.CharField(max_length=120, unique=True, verbose_name='Navn')
    slug = models.SlugField(
        max_length=64, unique=True, verbose_name='Kortnavn',
        help_text='Sendes til kartet og står i offline-nøklene. Endres ikke etter at '
                  'portalen er tatt i bruk.')
    er_aktiv = models.BooleanField(
        default=True, verbose_name='Aktiv',
        help_text='En deaktivert portal kan ikke velges, men alt i den står.')
    opprettet_at = models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')
    #: Hvilke tilhørigheter som er med i portalen — admin velger (§4.3).
    tilhorigheter = models.ManyToManyField(
        Tilhorighet, blank=True, related_name='portaler',
        verbose_name='Tilhørigheter')

    class Meta:
        verbose_name = 'Portal'
        verbose_name_plural = 'Portaler'
        ordering = [Norsk('navn')]

    def __str__(self):
        return self.navn


class Portalmodul(models.Model):
    """En modul i en portal, og taket for hva moderator kan dele ut (17. okt. 2026).

    `docs/BESLUTNING_PORTALER.md` §4.2: **admin setter hver portals moduler og
    tak**; moderator deler ut innenfor. **En modul uten rad finnes ikke i
    portalen** — ingen kan få tilgang til den der, og den står ikke i menyen.
    Nivået en konto får er det laveste av raden sin og taket
    (`core.auth_decorators._tilganger`), så et tak som senkes gjelder med en gang,
    også for det som alt er delt ut.

    **En ny portal får alle modulene med taket på toppen**
    (`core.signals.portalens_moduler`); admin snevrer inn på samme side. Det er
    ufarlig fordi portalen ikke har medlemmer ennå. **En ny modul kommer inn i
    alle portaler** når `ModuleSettings` får raden sin (`ensure_defaults_exist`),
    som `enabled=True` alt gjør — admin tar den ut der den ikke skal være.
    """

    portal = models.ForeignKey(Vaktportal, on_delete=models.CASCADE,
                               related_name='moduler', verbose_name='Portal')
    modul_slug = models.CharField(max_length=64, verbose_name='Modul')
    tak = models.CharField(max_length=32, verbose_name='Tak',
                           help_text='Det høyeste nivået moderator kan dele ut i portalen.')

    class Meta:
        verbose_name = 'Modul i portalen'
        verbose_name_plural = 'Moduler i portalen'
        ordering = ['portal', 'modul_slug']
        constraints = [models.UniqueConstraint(fields=['portal', 'modul_slug'],
                                               name='en_rad_per_modul_i_portalen')]

    def __str__(self):
        return f'{self.portal}: {self.modul_slug} (tak {self.tak})'

    #: Toppen av stigen. Taket en ny portal og en ny modul får er **modulens**
    #: øverste nivå (`toppen_for`); denne er for en modul registeret ikke kjenner.
    TOPPEN = 'skriv_leder'

    @classmethod
    def toppen_for(cls, slug) -> str:
        """Det øverste nivået modulen selv har — statistikken har bare `les`."""
        from core.auth_decorators import NIVAA_HIERARKI
        from core.modules import get_module
        modul = get_module(slug)
        if modul is None or not modul.nivaaer:
            return cls.TOPPEN
        return max(modul.nivaaer, key=lambda n: NIVAA_HIERARKI.get(n, -1))

    @classmethod
    def legg_i_alle_portaler(cls, slug, modell=None) -> None:
        """Modulen inn i hver portal som ikke har den, med modulens øverste nivå som tak."""
        modell = modell or cls
        portal_modell = modell._meta.get_field('portal').related_model
        for portal in portal_modell.objects.all():
            modell.objects.get_or_create(portal=portal, modul_slug=slug,
                                         defaults={'tak': cls.toppen_for(slug)})


class PortalQuerySet(models.QuerySet):
    """Spørresettet til en modell som hører til én portal (`PortalEid`)."""

    def i_portal(self, portal=None):
        """Radene i portalen — den oppgitte, ellers den gjeldende. Gjetter aldri:
        uten kontekst og med flere portaler kaster `gjeldende_portal()`."""
        from core.portal import gjeldende_portal
        return self.filter(portal=portal or gjeldende_portal())


class VaktbundetQuerySet(models.QuerySet):
    """`i_portal()` for rader som har portalen **gjennom vakta** (17. okt. 2026).

    `PortalEid` er for det som hører til en portal uten å henge på en vakt.
    Vaktlistas lister, ressurser og skift henger på vakta, og vakta har
    portalen — men et oppslag på ID alene går forbi den. Modellen oppgir veien
    i `PORTAL_STI`, og hvert oppslag på en ID fra klienten går gjennom her.
    """

    def i_portal(self, portal=None):
        from core.portal import gjeldende_portal
        return self.filter(**{self.model.PORTAL_STI: portal or gjeldende_portal()})


class PortalEid(models.Model):
    """Mixin for data som hører til én portal, men ikke til én vakt (17. okt. 2026).

    `docs/BESLUTNING_PORTALER.md` §4.12: **det som beskriver et sted eller en
    person er per portal** — mannskapet, førstehjelperne, lokasjonene, KOs
    ansvarsområder. Det som henger på en vakt, har portalen gjennom vakta og
    trenger ikke denne.

    **Én mekanisme, ikke én per modell.** Feltet, oppslaget (`i_portal()`) og
    hvor portalen kommer fra ved lagring står her. `save()` henter portalen fra
    konteksten (`core.portal.gjeldende_portal`) når den mangler — i en
    forespørsel er det portalen brukeren står i, og uten kontekst med flere
    portaler kaster den i stedet for å gjette.

    `portal` er nullbar i basen bare for release-vinduet og migrasjonene som
    fyller den; ingen vei lagrer en rad uten.
    """

    portal = models.ForeignKey(
        'core.Vaktportal', on_delete=models.PROTECT, null=True, related_name='+',
        verbose_name='Portal')

    objects = PortalQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.portal_id is None:
            from core.portal import gjeldende_portal
            self.portal = gjeldende_portal()
        super().save(*args, **kwargs)


class Vakt(models.Model):
    """Én vakt — scopet pasienter, oppdrag og statistikk henger på.

    Erstatter `year` som avgrensning (`docs/BESLUTNING_VAKT_SOM_SCOPE.md`).
    Portalen brukes på forskjellige arrangementer, ikke på det samme én gang i
    året — og `year` var allerede et vakt-id i forkledning for pasienter:
    arkiver → nullstill *er* vaktgrensen, dokumentert i personvernprotokollens
    C.2 som «nullstilles for neste event».

    Ligger i `core` fordi begge modulene scopes på den. I `patients` ville den
    gitt `oppdrag → patients` for noe som ikke er pasientdata — samme
    begrunnelse som `core.stats_cache` og `core.arkiv`.

    **Én aktiv vakt per portal**, håndhevet av databasen: en delvis unik
    indeks på `portal` der `er_aktiv` (17. okt. 2026, beslutning 19 i
    `docs/BESLUTNING_PORTALER.md`). Fram til da var `AppSetting['aktiv_vakt_id']`
    fasit og `er_aktiv` en kopi som kunne komme i utakt. Flere samtidige vakter
    i *samme* portal ville krevd et vaktvalg i hver eneste visning, og en feil i
    det valget er en pasient registrert på feil vakt.

    **`portal` er nullbar med vilje.** Backupfiler fra før portalene fantes
    ligger 730 dager offsite og har ikke feltet; `core.vakt.opprett_vakt` krever
    det, og ingen produksjonsvei lager en vakt uten.

    Bærer ingen personopplysninger: navn på arrangementet og tidspunkter.
    """

    navn = models.CharField(
        max_length=255,
        verbose_name='Vaktnavn',
        help_text='Fritekst, satt ved vaktstart: «Landsskytterstevnet 2026». '
                  'Unikt i portalen — to vakter med samme navn lar seg ikke skille '
                  'i statistikken. Trengs navnet igjen, legg på en dato.',
    )
    # Utledet, men lagret: sesongstatistikken grupperer på år, og å regne det
    # ut fra `startet` i hver spørring ville gjort en billig gruppering dyr.
    year = models.IntegerField(db_index=True, verbose_name='År')
    startet = models.DateTimeField(verbose_name='Startet')
    avsluttet = models.DateTimeField(
        null=True, blank=True, verbose_name='Avsluttet',
        help_text='Settes av «Avslutt vakt». En avsluttet vakt kan gjenåpnes '
                  'fram til arkivet er kollapset — etter det finnes ikke '
                  'radnivået lenger.',
    )
    # **Standard `False`** (17. okt. 2026, var `True`). Med den unike indeksen
    # feiler en ny rad som påstår å være aktiv mens portalen har en — en vakt
    # gjøres aktiv med vilje (`core.vakt.gjor_aktiv`), aldri ved å bli laget.
    er_aktiv = models.BooleanField(default=False, verbose_name='Aktiv')
    portal = models.ForeignKey(
        Vaktportal, on_delete=models.PROTECT, null=True, blank=True,
        related_name='vakter', verbose_name='Portal')

    # Bevisst ikke BaseTimeStampedModel: `startet` er vaktas egen tid og skal
    # kunne settes og rettes; en auto_now_add ved siden av ville vært en
    # kilde til å blande dem. created_at ville dessuten løyet for
    # backfillede vakter, som er eldre enn raden sin.

    class Meta:
        verbose_name = 'Vakt'
        verbose_name_plural = 'Vakter'
        ordering = ['-startet']
        constraints = [
            models.UniqueConstraint(
                fields=['portal'], condition=models.Q(er_aktiv=True),
                name='en_aktiv_vakt_per_portal'),
            # **Navnet er unikt per portal** (17. okt. 2026, §4.12), så Brann og
            # Standard kan ha hver sin «Kamp 7». Var unikt for hele installasjonen
            # — og da kunne `vakt_for_year()` aldri lage «2026» i portal nummer to.
            models.UniqueConstraint(fields=['portal', 'navn'], name='vaktnavn_unikt_per_portal'),
        ]

    def __str__(self):
        return self.navn


class VaktStatistikk(models.Model):
    """Tallene fra én statistikkfane for én vakt, frosset da vakta ble avsluttet.

    **Hvorfor fryse i stedet for å regne ut på nytt** (28. sep. 2026): etter
    «Avslutt vakt» finnes ikke radene lenger der fanene leser dem —
    pasientene slettes, oppdragene arkiveres og tømmes. Bemanning regner
    oppdragstallene sine fra `Oppdrag.objects.filter(vakt=...)` og ville vist
    0 for en avsluttet vakt. En fane per modul, én mekanisme for alle.

    **Legges til, skrives aldri over.** En vakt som gjenåpnes og avsluttes
    igjen, får et sett til: radene fra første gang er tømt, og en ny frysing
    over bare det som kom etterpå ville visket ut første del. `frosset_at` er
    avslutningen settet hører til — alle fanene i ett sett deler den.

    **`data` har formen handleren hadde den dagen** — `versjon` sier hvilken.
    Visningen må tåle de eldre; tallene regnes ikke ut på nytt.

    Et aggregat, ikke personopplysninger på radnivå. At små tall er med er et
    valg global admin tar (TODO: «Avslutt vakt, arkiv og tidligere vakter»).
    """

    vakt = models.ForeignKey(
        Vakt, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='statistikk', verbose_name='Vakt')
    #: Frosset: vakta kan bli omdøpt eller slettet, tallene skal fortsatt kunne
    #: si hvilken vakt de er fra. Samme mønster som arkivene.
    vakt_navn = models.CharField(max_length=255, verbose_name='Vaktnavn')
    slug = models.CharField(max_length=64, verbose_name='Statistikkilde')
    versjon = models.PositiveSmallIntegerField(default=1, verbose_name='Formversjon')
    data = models.JSONField(verbose_name='Tallene')
    frosset_at = models.DateTimeField(db_index=True, verbose_name='Frosset')
    frosset_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Frosset av')
    frosset_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Frosset av (navn)')

    class Meta:
        verbose_name = 'Frosset vaktstatistikk'
        verbose_name_plural = 'Frosset vaktstatistikk'
        ordering = ['-frosset_at', 'slug']
        constraints = [
            models.UniqueConstraint(fields=['vakt', 'slug', 'frosset_at'],
                                    name='vaktstatistikk_en_per_fane_per_avslutning'),
        ]

    def __str__(self):
        return f'{self.vakt_navn} · {self.slug} · {self.frosset_at:%d.%m.%Y %H:%M}'


class OffsiteKopi(models.Model):
    """Én opplasting av en backup-fil til Scaleway (13. sep. 2026).

    Raden er sporet: hvilken fil, hvor den ligger i bucketen, hvor stor den
    ble kryptert, når den gikk — og `feil` når den ikke gikk. Et mislykket
    forsøk får også en rad; oversikten på /admin/backup/ viser den
    siste feilen, for en offsite-backup som stille har sluttet å virke er
    den feilen man oppdager den dagen Railway er borte.
    """

    backup_filnavn = models.CharField(max_length=255, verbose_name='Backup-fil')
    module_slug = models.CharField(max_length=50, blank=True, default='', verbose_name='Modul')
    objektnavn = models.CharField(max_length=300, verbose_name='Objekt i bucketen')
    bytes = models.BigIntegerField(default=0, verbose_name='Bytes (kryptert)')
    sendt_at = models.DateTimeField(null=True, blank=True, verbose_name='Lastet opp')
    feil = models.TextField(blank=True, default='', verbose_name='Feil')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Forsøkt')

    class Meta:
        verbose_name = 'Offsite-kopi'
        verbose_name_plural = 'Offsite-kopier'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.objektnavn} ({"ok" if not self.feil else "feilet"})'

    @property
    def gikk(self) -> bool:
        return not self.feil


# ── Flyttet fra `patients` 14. sep. 2026 ─────────────────────────────────────
#
# Begge er portalvide og har aldri vært pasientdata. De lå i `patients` fordi
# den var første app og det ikke fantes noe annet sted — se
# `docs/PLAN_FLYTTING_TIL_CORE.md`.
#
# **`db_table` er bundet til det gamle navnet, og det er et valg, ikke en
# forglemmelse.** Railway kjører release-fasen *før* den bytter container, så
# mellom `migrate` og byttet står gammel kode og serverer mot nytt skjema. En
# omdøpt `patients_appsetting` ville gitt 500 på tilnærmet hver forespørsel i
# det vinduet, fordi tabellen bærer pekeren til aktiv vakt. Prisen er at
# tabellen heter `patients_*` i `core`; den er kosmetisk.
#
# Fjernes `db_table`, lager Django en *ny*, tom tabell ved siden av den fulle —
# en feil som ser ut som «alle innstillingene forsvant».

class AppSetting(models.Model):
    """Applikasjonsinnstillinger (nøkkel-verdi-par).

    Portalvid: aktiv vakt, lydvarselbryterne i oppdrag, e-postmottakerne for
    vaktlistefila, sesjonstimeout, og siste kjøring av cron-jobbene.
    """

    key = models.CharField(max_length=64, primary_key=True, verbose_name='Nøkkel')
    value = models.TextField(verbose_name='Verdi')

    class Meta:
        db_table = 'patients_appsetting'      # se kommentaren over
        verbose_name = 'Appinnstilling'
        verbose_name_plural = 'Appinnstillinger'

    def __str__(self):
        return f'{self.key} = {self.value}'

    @classmethod
    def get(cls, key, default=None):
        """Hent verdi for nøkkel, eller standard-verdi."""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key, value):
        """Sett verdi for nøkkel (opprett eller oppdater)."""
        obj, _ = cls.objects.update_or_create(
            key=key,
            defaults={'value': str(value)},
        )
        return obj

    # ── Portalens innstillinger (17. okt. 2026, `docs/BESLUTNING_PORTALER.md` §4.7) ──
    #
    # Noen nøkler er portalens: mottakerne av vaktlistefila, lydvarselet i bilene,
    # tavlas oppsett. De lagres som `<nøkkel>@p<portal-id>`, og **den globale
    # verdien er standarden** — en ny portal arver det systemet er satt opp med.
    #
    # **Etterledd, ikke forstavelse:** auditens unntaksliste, tavlas `ko.tavle*`-
    # lytter og `cron.*` leser starten av nøkkelen, og virker da uendret.
    # **To navngitte kall, ikke et register:** det står i koden hvilke nøkler som
    # er portalens, og `core` slipper å kjenne modulenes nøkkelnavn.

    @staticmethod
    def portalnokkel(key, portal) -> str:
        return f'{key}@p{portal.pk}'

    @classmethod
    def get_i_portal(cls, key, default=None, portal=None):
        """Portalens verdi, ellers den globale, ellers `default`. `portal` når
        kalleren har den fra dataene; ellers `gjeldende_portal()` — konteksten,
        eller den eneste. Er det uklart (flere, ingen kontekst), er svaret
        systemets verdi: standarden, ikke en gjetning på en portal."""
        from core.portal import UklarPortal, gjeldende_portal
        if portal is None:
            try:
                portal = gjeldende_portal()
            except UklarPortal:
                portal = None
        if portal is not None:
            verdi = cls.get(cls.portalnokkel(key, portal))
            if verdi is not None:
                return verdi
        return cls.get(key, default)

    @classmethod
    def set_i_portal(cls, key, value, portal=None):
        """Sett portalens verdi. Uten portal og med flere kaster
        `gjeldende_portal()` — en innstilling skal aldri havne i feil portal."""
        from core.portal import gjeldende_portal
        return cls.set(cls.portalnokkel(key, portal or gjeldende_portal()), value)


class Backup(models.Model):
    """Metadata om en backup-fil. Selve filen ligger på disk/volume."""
    KIND_CHOICES = [
        ('auto',        'Automatisk'),
        ('manual',      'Manuell'),
        ('pre_restore', 'Før gjenoppretting'),
        ('pre_reset',   'Før nullstilling av år'),
        # Hel databasebackup før en tidligere vakt slettes (`core/vaktsletting.py`).
        ('pre_slett',   'Før sletting av vakt'),
    ]
    filename    = models.CharField(max_length=255, unique=True)
    kind        = models.CharField(max_length=20, choices=KIND_CHOICES)
    size_bytes  = models.BigIntegerField()
    created_at  = models.DateTimeField(auto_now_add=True)
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='backups_created',
    )
    note        = models.CharField(max_length=200, blank=True, default='')
    content_hash = models.CharField(
        max_length=64, blank=True, default='',
        help_text='SHA256 over ukomprimert JSON-innhold. '
                  'Brukes til å hoppe over identiske auto-backups.',
    )
    module_slug = models.CharField(
        max_length=64,
        default='patients',
        db_index=True,
        help_text='Hvilken modul backupen tilhører. Brukes av core.backup '
                  'for per-modul-cap og restore-rutting.',
    )

    class Meta:
        db_table = 'patients_backup'          # se kommentaren over
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['kind', '-created_at'], name='backup_kind_created_idx'),
            models.Index(fields=['module_slug', '-created_at'],
                         name='backup_module_created_idx'),
        ]

    def __str__(self):
        return f'{self.filename} ({self.get_kind_display()})'
