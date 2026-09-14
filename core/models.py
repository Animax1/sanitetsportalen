"""Felles modeller for sanitetsportalen.

Inneholder:
- ``BaseTimeStampedModel``: abstrakt mixin med created_at/updated_at.
- ``ModuleSettings``: konfigurasjon per modul (enabled-toggle, backup-flagg).
"""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


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

    ``backup_enabled`` har ingen effekt: hva som blir tatt backup av avgjøres
    av backup-registeret (hvilke moduler som har en handler) og av
    ``core.Backupplan`` (om, og hvor ofte). Å la feltet også kunne slå av
    backup ville gitt to steder å se etter når en fil mangler.
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
    backup_enabled = models.BooleanField(
        default=False,
        verbose_name='Inkluder i backup',
        help_text=(
            'Reservert for fremtidig modul-styrt backup. Per Fase 3a har dette '
            'feltet ingen effekt — backup styres fortsatt av BACKUP_APPS i kode. '
            'Settes opp i en senere fase.'
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
    def ensure_defaults_exist(cls) -> None:
        """Sørg for at hver registrert modul har en rad i tabellen.

        Idempotent: kjører ``get_or_create`` for hver modul. Kalles fra
        ``CoreConfig.ready()`` etter at app-registret er ferdig lastet.

        Kjernemoduler får ``enabled=True`` per default og kan ikke deaktiveres.
        Andre moduler får ``enabled=True`` ved første registrering — admin må
        eksplisitt skru av.
        """
        # Lazy import: modules.py importerer fra denne fila, så vi kan ikke
        # importere på toppnivå.
        from core.modules import get_all_modules  # noqa: WPS433

        for module in get_all_modules():
            cls.objects.get_or_create(
                slug=module.slug,
                defaults={'enabled': True},
            )


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

    **Én aktiv vakt om gangen** — pekt på av `AppSetting['aktiv_vakt_id']`,
    ikke av `er_aktiv` alene. Flere samtidige vakter ville krevd et vaktvalg i
    hver eneste visning, og en feil i det valget er en pasient registrert på
    feil vakt. Modellen sperrer det ikke for framtiden; grensesnittet
    forutsetter én.

    Bærer ingen personopplysninger: navn på arrangementet og tidspunkter.
    """

    navn = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Vaktnavn',
        help_text='Fritekst, satt ved vaktstart: «Landsskytterstevnet 2026». '
                  'Unikt — to vakter med samme navn lar seg ikke skille i '
                  'statistikken. Trengs navnet igjen, legg på en dato.',
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
    er_aktiv = models.BooleanField(default=True, verbose_name='Aktiv')

    # Bevisst ikke BaseTimeStampedModel: `startet` er vaktas egen tid og skal
    # kunne settes og rettes; en auto_now_add ved siden av ville vært en
    # kilde til å blande dem. created_at ville dessuten løyet for
    # backfillede vakter, som er eldre enn raden sin.

    class Meta:
        verbose_name = 'Vakt'
        verbose_name_plural = 'Vakter'
        ordering = ['-startet']

    def __str__(self):
        return self.navn


class OffsiteKopi(models.Model):
    """Én opplasting av en backup-fil til Scaleway (13. sep. 2026).

    Raden er sporet: hvilken fil, hvor den ligger i bucketen, hvor stor den
    ble kryptert, når den gikk — og `feil` når den ikke gikk. Et mislykket
    forsøk får også en rad; oversikten på /portal-admin/backup/ viser den
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
