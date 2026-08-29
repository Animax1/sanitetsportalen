"""Modeller for vaktlistemodulen — fase 1: registrene og mannskapet.

Se ``docs/BESLUTNING_VAKTLISTE.md``. To ting er verdt å ha i hodet når man
leser fila:

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

Vaktliste, ressurser og vaktposter kommer i fase 2. Ingen modell her rører
``patients`` eller ``oppdrag``.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import BaseTimeStampedModel


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
    rekkefolge = models.IntegerField(
        default=100,
        verbose_name='Rekkefølge',
        help_text='Lavere kommer først i lister.',
    )

    class Meta:
        verbose_name = 'Korps'
        verbose_name_plural = 'Korps'
        ordering = ['rekkefolge', 'navn']

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
    rekkefolge = models.IntegerField(
        default=100,
        verbose_name='Rekkefølge',
        help_text='Lavere kommer først i lister.',
    )

    class Meta:
        verbose_name = 'Kompetanse'
        verbose_name_plural = 'Kompetanser'
        ordering = ['rekkefolge', 'navn']

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
    rekkefolge = models.IntegerField(
        default=100,
        verbose_name='Rekkefølge',
        help_text='Lavere kommer først i lister.',
    )

    class Meta:
        verbose_name = 'Vaktrolle'
        verbose_name_plural = 'Vaktroller'
        ordering = ['rekkefolge', 'navn']

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
        ordering = ['korps__rekkefolge', 'korps__navn', 'navn']
        constraints = [
            # Unikt per korps, ikke globalt: to korps kan ha hver sin
            # «Ola Hansen», men to like navn i samme korps er umulige å
            # skille i en liste — da må det ene få et mellomnavn.
            models.UniqueConstraint(
                fields=['korps', 'navn'], name='unikt_navn_per_korps'),
        ]

    def __str__(self) -> str:
        return f'{self.navn} ({self.korps.kortnavn or self.korps.navn})'
