"""Modeller for vaktlistemodulen — fase 1: registrene og mannskapet.

Se ``docs/BESLUTNING_VAKTLISTE.md``. To ting er verdt å ha i hodet når man
leser fila:

0. **Verdimengdene sorteres alfabetisk, uten et `rekkefolge`-felt.** Feltet
   fantes til 30. aug. 2026, men alle radene sto på standardverdien, så
   `ordering` falt uansett tilbake på navnet — det var alfabetisk i praksis,
   med et tallfelt i skjemaet som pris. `Ressurs` beholder sitt, fordi der
   *betyr* rekkefølgen noe (fanerekkefølgen på planleggingssiden), og der
   settes den automatisk.

   **`Lower(...)` er ikke pynt.** Uten den sorterer basen på kodepunkt, og da
   havner «karmøy» etter «Åsen» i én base og før «Bokn» i en annen — sorteringen
   ville sett ulik ut i dev (SQLite) og prod (PostgreSQL). Æ/Ø/Å står vi
   derimot igjen med databasens svar på: en ekte norsk kollasjon krever enten
   en sorteringsnøkkel-kolonne eller en `db_collation`, og for en håndfull
   korps er det ikke verdt det. Det er notert i TODO om noen får et korps som
   begynner på Å.
1. **`Korps`, `Kompetanse` og `VaktRolle` er tabeller, ikke `choices.py`.**
   Motsatt av oppdragsmodulen, der problemstilling og hastegrad ligger i
   kode. Skillet er det samme som mellom `PROBLEMSTILLING` og `Lokasjon`:
   faglige verdimengder som endres sjelden hører i kode, organisasjonsdata i
   basen — og bestillingen sier eksplisitt at admin skal styre disse.
2. **`Mannskap.korps` er badgen hele tilgangsmodellen hviler på** (§4 i
   notatet). Feltet sier hvor personen hører hjemme — men fordi en konto kan
   knyttes til et mannskap (`Mannskap.user`), er det også det som fra fase 3
   avgjør hvilke rader kontoen får redigere. Koblingen gir i seg selv ingen
   tilgang, akkurat som ``Enhet.user`` i oppdragsmodulen.

Fase 2 la til `Vaktliste`, `Ressurs` og `Vaktpost` — selve oppsettet. Tre
regler er verdt å kjenne før man rører dem:

3. **Reservasjonen er `Ressurs.korps`** (§4.2). `skriv_full`/admin tildeler et
   lag eller en bil til et korps; korps-brukeren bemanner bare ressurser med
   sin egen badge. Tom = ureservert, og da er den `skriv_full`/admins bord —
   KO og samleplass er typisk slike. Sjekkene håndheves fra fase 3.
4. **Et skift er en `Vaktpost`.** Går Per to skift på ambulansen, er det to
   rader med hver sine tider. Det er det som gjør timer, hviletid og
   skiftlengde til spørringer i stedet for tolkning (§8b).
5. **Plan og faktisk holdes atskilt.** `fra_tid`/`til_tid` er planen;
   `mott_at`/`av_vakt_at` er hva som skjedde. Avviket mellom dem er selve
   informasjonen, og derfor er de fire ulike felter — ikke to som overskrives.

Ingen modell her rører ``patients``. `Ressurs.enhet` peker på ``oppdrag`` —
den ene koblingen, og den går én vei (§6).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from core.models import BaseTimeStampedModel

from . import choices


class Korps(BaseTimeStampedModel):
    """Et korps — organisasjonsenheten mannskapet hører til.

    Badgen i tilgangsmodellen (§4): en ressurs kan reserveres til et korps,
    og en korps-bruker bemanner bare ressurser reservert sitt eget. Feltet
    har ingen funksjon utover det — bestillingen var eksplisitt på å ikke
    overkomplisere korpsbegrepet.
    """

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
    class Meta:
        verbose_name = 'Korps'
        verbose_name_plural = 'Korps'
        ordering = [Lower('navn')]

    def __str__(self) -> str:
        return self.navn


class Kompetanse(BaseTimeStampedModel):
    """En kompetanse — «Sanitetsvakt», «Sykepleier», «Sjåfør kode 160» …

    Beskriver hva personen kan, ikke hva hun gjør på en gitt vakt — det er
    `VaktRolle` sin jobb. Skillet er bevisst: kompetansen følger personen,
    rollen følger vaktposten.
    """

    navn = models.CharField(max_length=120, unique=True, verbose_name='Navn')
    er_aktiv = models.BooleanField(
        default=True,
        verbose_name='Aktiv',
        help_text='Inaktive kompetanser skjules i nedtrekkslister, men '
                  'beholdes på mannskapet som har dem.',
    )
    class Meta:
        verbose_name = 'Kompetanse'
        verbose_name_plural = 'Kompetanser'
        ordering = [Lower('navn')]

    def __str__(self) -> str:
        return self.navn


class VaktRolle(BaseTimeStampedModel):
    """En rolle under vakt — «Lagleder», «Fagleder helse», «KO-operatør» …

    Settes på vaktposten (fase 2), ikke på personen: samme person kan være
    lagleder lørdag og sjåfør søndag.
    """

    navn = models.CharField(max_length=120, unique=True, verbose_name='Navn')
    er_aktiv = models.BooleanField(
        default=True,
        verbose_name='Aktiv',
        help_text='Inaktive roller skjules i nedtrekkslister, men beholdes '
                  'på vaktposter som allerede bruker dem.',
    )
    class Meta:
        verbose_name = 'Vaktrolle'
        verbose_name_plural = 'Vaktroller'
        ordering = [Lower('navn')]

    def __str__(self) -> str:
        return self.navn


class Mannskap(BaseTimeStampedModel):
    """Én person i mannskapsregisteret.

    Registeret er **globalt** (§11.1 i notatet): personellet organisasjonen
    har, som hver vakt plukker fra. Det er portalens tredje personregister —
    `Forstehjelper` og `Helsepersonell` i pasientmodulen forblir urørt (§9),
    og det finnes bevisst ingen kobling dit: de svarer på «hvem behandlet
    pasienten», dette svarer på «hvem er på vakt».

    **Kostbehov/matallergi lagres ikke** (§7). Det er en helseopplysning
    etter GDPR art. 9, og samles inn utenfor portalen. `notat` er unntatt
    verdilogging i audit nettopp fordi fritekst er der helseopplysninger
    havner når det ikke finnes et felt for dem — se `signals.py`.
    """

    navn = models.CharField(max_length=150, verbose_name='Navn')
    # PROTECT: korpset er badgen, og et mannskap uten korps kan verken
    # vises riktig i lista eller redigeres av en korps-bruker. Sletting av
    # et korps med mannskap skal stoppes, ikke kaskadere.
    korps = models.ForeignKey(
        Korps,
        on_delete=models.PROTECT,
        related_name='mannskap',
        verbose_name='Korps',
    )
    kompetanser = models.ManyToManyField(
        Kompetanse,
        blank=True,
        related_name='mannskap',
        verbose_name='Kompetanser',
    )
    telefon = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Telefon',
        help_text='Brukes av KO og vaktleder under vakt. Valgfritt.',
    )
    # Badgen-koblingen (§4): kontoen arver korpset herfra. SET_NULL, ikke
    # CASCADE — slettes kontoen, består personen i registeret. Samme valg
    # som `Enhet.user` og `Forstehjelper.user`.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='mannskap',
        verbose_name='Koblet konto',
        help_text='Valgfri kobling til en portalbruker. Fra fase 3 avgjør '
                  'den hvilket korps kontoen kan redigere. Gir i seg selv '
                  'ingen tilgang.',
    )
    er_aktiv = models.BooleanField(
        default=True,
        verbose_name='Aktiv',
        help_text='Pensjonerte mannskaper skjules i lister, men beholdes på '
                  'historiske vaktposter. Den normale veien ut av registeret.',
    )
    notat = models.TextField(
        blank=True,
        default='',
        verbose_name='Notat',
        help_text='Fritekst. Verdiene logges ikke i revisjonsloggen. '
                  'IKKE skriv helseopplysninger her — kostbehov og allergier '
                  'skal ikke inn i portalen.',
    )

    class Meta:
        verbose_name = 'Mannskap'
        verbose_name_plural = 'Mannskap'
        ordering = [Lower('korps__navn'), Lower('navn')]
        constraints = [
            # Unikt per korps, ikke globalt: to korps kan ha hver sin
            # «Ola Hansen», men to like navn i samme korps er umulige å
            # skille i en liste — da må det ene få et mellomnavn.
            models.UniqueConstraint(
                fields=['korps', 'navn'], name='unikt_navn_per_korps'),
        ]

    def __str__(self) -> str:
        return f'{self.navn} ({self.korps.kortnavn or self.korps.navn})'


# ── Oppsettet (fase 2) ───────────────────────────────────────────────────────


class Vaktliste(BaseTimeStampedModel):
    """Personelloppsettet for **én** vakt.

    1:1 med `core.Vakt`. Alternativet — flere lister per vakt — løser
    ingenting bestillingen beskriver, og gjør «hvem er på vakt nå» til et
    spørsmål med flere svar.

    **Status er en innsjekk-port, ikke en livssyklus** (§5). `planlegging`
    betyr at møtt/av vakt er stengt; `drift` at den er åpen. Overgangen går
    begge veier: en pause i arrangementet eller et feilklikk skal kunne
    rettes, og stemplene som alt er satt består. Statusen rører **ikke**
    portalens aktive vakt — det byttes i vaktadministrasjonen, som før.
    """

    # PROTECT: vakta er listas identitet. Slettes den under, står lista igjen
    # uten å kunne si hvilken vakt den gjaldt.
    vakt = models.OneToOneField(
        'core.Vakt',
        on_delete=models.PROTECT,
        related_name='vaktliste',
        verbose_name='Vakt',
    )
    status = models.CharField(
        max_length=16,
        choices=choices.STATUS_VALG,
        default=choices.PLANLEGGING,
        db_index=True,
        verbose_name='Status',
    )
    satt_i_drift_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Satt i drift')
    satt_i_drift_av = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='vaktlister_satt_i_drift',
        verbose_name='Satt i drift av',
    )
    notat = models.TextField(blank=True, default='', verbose_name='Notat')

    class Meta:
        verbose_name = 'Vaktliste'
        verbose_name_plural = 'Vaktlister'
        ordering = ['-vakt__startet']

    def __str__(self) -> str:
        return f'Vaktliste for {self.vakt.navn}'

    @property
    def i_drift(self) -> bool:
        """True når innsjekk er åpen. Utledet av statusen, ikke lagret to steder."""
        return self.status == choices.DRIFT


class Ressurs(BaseTimeStampedModel):
    """Noe som bemannes: samleplass, bil, lag, KO.

    **`korps` er reservasjonen** (§4.2), ikke en eier: `skriv_full`/admin
    setter den, og korps-brukeren bemanner bare ressurser med sin egen badge.
    Tom betyr ureservert — ikke fritt fram, men `skriv_full`/admins bord.

    **`enhet` er koblingen til oppdragsmodulen** (§6). Er den satt, er
    ressursen den bilen 113 tildeler oppdrag til, og sentralbordet kan vise
    besetningen (fase 6). SET_NULL: pensjoneres enheten, består ressursen og
    dens bemanning — historikken om hvem som gikk vakt skal ikke rives bort
    av et oppsettsvalg i en annen modul.
    """

    vaktliste = models.ForeignKey(
        Vaktliste,
        on_delete=models.CASCADE,
        related_name='ressurser',
        verbose_name='Vaktliste',
    )
    navn = models.CharField(
        max_length=120,
        verbose_name='Navn',
        help_text='Slik den omtales på vakta, f.eks. «Mannskapsbil 1».',
    )
    type = models.CharField(
        max_length=16,
        choices=choices.RESSURSTYPE_VALG,
        default=choices.ANNET,
        verbose_name='Type',
    )
    korps = models.ForeignKey(
        Korps,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='reserverte_ressurser',
        verbose_name='Reservert korps',
        help_text='Korpset som har fått ressursen. Tom = ureservert, og '
                  'bemannes da av vaktleder.',
    )
    enhet = models.ForeignKey(
        'oppdrag.Enhet',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='vaktliste_ressurser',
        verbose_name='Enhet i oppdragsmodulen',
        help_text='Kobles for biler og ambulanser, slik at sentralbordet kan '
                  'vise besetningen.',
    )
    rekkefolge = models.IntegerField(
        default=100, verbose_name='Rekkefølge',
        help_text='Styrer fanerekkefølgen. Settes automatisk til '
                  'opprettelsesrekkefølgen — se services.neste_rekkefolge().')

    class Meta:
        verbose_name = 'Ressurs'
        verbose_name_plural = 'Ressurser'
        ordering = ['rekkefolge', 'navn']
        constraints = [
            models.UniqueConstraint(
                fields=['vaktliste', 'navn'], name='unikt_ressursnavn_per_vaktliste'),
        ]

    def __str__(self) -> str:
        return self.navn


class Vaktpost(BaseTimeStampedModel):
    """Ett skift: én person på én ressurs, med rolle og tider.

    To skift for samme person er to rader. Det er derfor timer, hviletid og
    skiftlengde (§8b) kan regnes ut i stedet for å tolkes.

    **De fire tidsfeltene er to par.** `fra_tid`/`til_tid` er planen — den
    settes i planleggingen. `mott_at`/`av_vakt_at` er hva som skjedde, og
    settes først når lista er i drift (fase 4). Å slå dem sammen ville
    slettet avviket, og avviket er det man vil vite om etterpå.

    `avmeldt_at` er en tredje ting: personen har sagt fra at hun ikke kommer.
    Raden blir stående — den forteller at plassen ble tom, og at det var
    kjent på forhånd.
    """

    ressurs = models.ForeignKey(
        Ressurs,
        on_delete=models.CASCADE,
        related_name='vaktposter',
        verbose_name='Ressurs',
    )
    # PROTECT: historikken om hvem som gikk vakt skal ikke kunne rives bort
    # under en sletting. Pensjonering (`er_aktiv=False`) er veien ut.
    mannskap = models.ForeignKey(
        Mannskap,
        on_delete=models.PROTECT,
        related_name='vaktposter',
        verbose_name='Mannskap',
    )
    rolle = models.ForeignKey(
        VaktRolle,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='vaktposter',
        verbose_name='Rolle',
    )

    fra_tid = models.DateTimeField(verbose_name='Fra')
    til_tid = models.DateTimeField(verbose_name='Til')

    # ── Drift (fase 4) ───────────────────────────────────────────────────
    # Feltene finnes fra fase 2 slik at plan og faktisk er atskilt fra
    # første rad, men settes først når innsjekk åpnes. Samme grep som
    # `korrigerer`/`automatisk` i oppdragsmodulen, der maskineriet kom i
    # fase 1 og endepunktene i fase 4b.
    mott_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Møtt')
    av_vakt_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Av vakt')
    avmeldt_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Avmeldt',
        help_text='Personen har meldt fra at hun ikke kommer. Raden blir '
                  'stående, slik at det synes at plassen ble tom.')
    merknad = models.CharField(
        max_length=255, blank=True, default='', verbose_name='Merknad')

    class Meta:
        verbose_name = 'Vaktpost'
        verbose_name_plural = 'Vaktposter'
        ordering = ['fra_tid', 'mannskap__navn']
        constraints = [
            # Samme person, samme ressurs, samme starttid er en dobbeltføring.
            # Overlapp på tvers av ressurser stoppes bevisst *ikke*: noen
            # ganger står man på to lister med vilje, og planleggingstallene
            # (§8b) flagger det i stedet for å nekte.
            models.UniqueConstraint(
                fields=['ressurs', 'mannskap', 'fra_tid'],
                name='unikt_skift_per_person_og_ressurs'),
        ]
        indexes = [
            models.Index(fields=['ressurs', 'fra_tid'], name='vaktpost_ress_tid_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.mannskap.navn} på {self.ressurs.navn}'

    @property
    def er_tilstede(self) -> bool:
        """Møtt, og ikke gått av vakt.

        Definisjonen «Tilstede nå» hviler på (§8). Utledet av stemplene,
        aldri en lagret status — to kilder til samme sannhet går i utakt
        første gang noe feiler halvveis.
        """
        return self.mott_at is not None and self.av_vakt_at is None
