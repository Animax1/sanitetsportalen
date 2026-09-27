"""Park-modulens tabeller — se `docs/FORSLAG_PARK.md` §3.

**Ingen fritekst, og det er sikkerhetsmodellen** (B1). Registreringene kommer
fra en side uten innlogging; et fritt felt der er et felt der et navn havner en
travel kveld, skrevet av noen vi ikke vet hvem er. Med bare verdimengder kan
raden ikke inneholde et navn, og da kan backupen og statistikken vise den uten
pasientmodulens vern.

**Pekerne ut av modulen fryser navnet ved siden av seg**, som `ko.HendelseLag`
og `ko.Tavleplassering`: vaktlistas ressurser er nye rader for hver vaktliste,
og oppdragsmodulens lokasjoner kan deaktiveres. Statistikken teller navnet.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.sortering import Norsk


class _Verdi(models.Model):
    """Felles form for de to verdimengdene: navn, rekkefølge, aktiv.

    Mønsteret fra `oppdrag.Lokasjon` og `oppdrag.Problemstilling`. En inaktiv
    rad skjules i nedtrekket, men registreringene som bruker den beholder
    navnet — de lagrer det som tekst.
    """

    navn = models.CharField(max_length=64, unique=True, verbose_name='Navn')
    rekkefolge = models.IntegerField(default=100, verbose_name='Rekkefølge')
    er_aktiv = models.BooleanField(default=True, verbose_name='Aktiv')

    class Meta:
        abstract = True
        ordering = ['rekkefolge', Norsk('navn')]

    def __str__(self) -> str:
        return self.navn


class Problemstilling(_Verdi):
    """Hva laget hjalp med (B6). Satt opp av `skriv_leder` og admin.

    Startverdiene er **kopiert** fra `patients.choices.PROBLEMSTILLING` av
    `0002`, ikke lest derfra: park importerer ikke pasientmodulen, og fra første
    endring er lista parks egen.
    """

    class Meta(_Verdi.Meta):
        verbose_name = 'Problemstilling'
        verbose_name_plural = 'Problemstillinger'


class Utfall(_Verdi):
    """Hvordan det endte (B7). Satt opp av global admin."""

    class Meta(_Verdi.Meta):
        verbose_name = 'Utfall'
        verbose_name_plural = 'Utfall'


class Parklenke(models.Model):
    """Lenken i tiltakskortet (B3). Tokenet lagres ikke — bare hashen (§4.1).

    **Ikke bundet til en vakt** (B18): tiltakskortet kan stå fra vakt til vakt,
    og oppetiden er grensen. Registreringen havner på vakta som er aktiv når den
    sendes.

    **Fjerning er en markering, ikke sletting.** Registreringene beholder sin
    peker, og lista viser at lenken fantes — det er slik man finner ut hva en
    lekket lenke har levert (§4.6).
    """

    navn = models.CharField(
        max_length=120, verbose_name='Navn',
        help_text='Hvor lenken ligger, f.eks. «Tiltakskort Bliksund».')
    # RISIKOVALG(park-lenke-en-gang): bare hashen lagres, så lenken kan vises
    # én gang og aldri igjen. Alternativet står i FORSLAG_PARK.md §4.7.
    hemmelighet_hash = models.CharField(
        max_length=64, unique=True, verbose_name='Hash av tokenet')
    aapen_fra = models.DateTimeField(verbose_name='Åpen fra')
    aapen_til = models.DateTimeField(verbose_name='Åpen til')
    opprettet_at = models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')
    opprettet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Opprettet av')
    opprettet_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Opprettet av (navn)')
    fjernet_at = models.DateTimeField(null=True, blank=True, verbose_name='Fjernet')
    fjernet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Fjernet av')
    fjernet_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Fjernet av (navn)')
    sist_brukt_at = models.DateTimeField(null=True, blank=True, verbose_name='Sist brukt')

    class Meta:
        verbose_name = 'Parklenke'
        verbose_name_plural = 'Parklenker'
        ordering = ['-opprettet_at', '-id']
        constraints = [
            models.CheckConstraint(
                condition=Q(aapen_til__gt=models.F('aapen_fra')),
                name='parklenke_til_etter_fra'),
        ]

    def __str__(self) -> str:
        return self.navn


class Registrering(models.Model):
    """Én registrering fra et lag: problemstilling × antall, sted og utfall."""

    FORHANDSVALG_KO = 'ko'
    FORHANDSVALG_REGISTRERING = 'registrering'
    FORHANDSVALG_TELEFON = 'telefon'
    FORHANDSVALG_INGEN = 'ingen'
    FORHANDSVALG = (
        (FORHANDSVALG_KO, 'KO-tavla'),
        (FORHANDSVALG_REGISTRERING, 'Lagets siste registrering'),
        (FORHANDSVALG_TELEFON, 'Telefonens siste valg'),
        (FORHANDSVALG_INGEN, 'Ingen'),
    )

    vakt = models.ForeignKey(
        'core.Vakt', on_delete=models.PROTECT, related_name='park_registreringer',
        verbose_name='Vakt')
    lenke = models.ForeignKey(
        Parklenke, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='registreringer', verbose_name='Lenke')
    ressurs = models.ForeignKey(
        'vaktliste.Ressurs', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='park_registreringer', verbose_name='Lag')
    ressurs_navn = models.CharField(max_length=120, verbose_name='Lag (navn)')
    # Tekst, ikke FK, som `Oppdrag.problemstilling`: navnet er det som telles,
    # og en omdøpt rad skal ikke skrive om historikken.
    problemstilling = models.CharField(max_length=64, verbose_name='Problemstilling')
    antall = models.PositiveSmallIntegerField(default=1, verbose_name='Antall')
    utfall = models.CharField(max_length=64, verbose_name='Utfall')
    lokasjon = models.ForeignKey(
        'oppdrag.Lokasjon', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='park_registreringer', verbose_name='Sted')
    lokasjon_navn = models.CharField(max_length=120, verbose_name='Sted (navn)')
    # Uten offline (B14) er dette også når det skjedde: ingen klienttid.
    registrert_at = models.DateTimeField(auto_now_add=True, verbose_name='Registrert')
    #: Klientgenerert UUID. Gjør en dobbeltsending til én rad, og er
    #: **angre-nøkkelen**: bare telefonen som sendte raden kjenner den (§4.4).
    idempotency_key = models.CharField(max_length=36, verbose_name='Idempotensnøkkel')
    #: Målingen (B21): hvor stedet i nedtrekket kom fra, og om laget endret det.
    forhandsvalg_kilde = models.CharField(
        max_length=16, choices=FORHANDSVALG, default=FORHANDSVALG_INGEN,
        verbose_name='Forhåndsvalg fra')
    forhandsvalg_endret = models.BooleanField(
        default=False, verbose_name='Forhåndsvalget endret')
    #: B20: `skriv_leder` sletter en feilregistrering. Raden står, og
    #: statistikken utelater den — en sletting som ikke synes er en statistikk
    #: ingen kan etterprøve. Lagets egen angring sletter raden helt.
    slettet_at = models.DateTimeField(null=True, blank=True, verbose_name='Slettet')
    slettet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Slettet av')
    slettet_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Slettet av (navn)')
    slettet_grunn = models.CharField(
        max_length=200, blank=True, default='', verbose_name='Grunn til sletting')

    class Meta:
        verbose_name = 'Registrering'
        verbose_name_plural = 'Registreringer'
        ordering = ['-registrert_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['lenke', 'idempotency_key'],
                name='park_en_registrering_per_nokkel'),
            models.CheckConstraint(
                condition=Q(antall__gte=1), name='park_antall_minst_en'),
        ]
        indexes = [
            models.Index(fields=['vakt', 'ressurs', '-registrert_at'],
                         name='park_reg_vakt_ressurs'),
        ]

    def __str__(self) -> str:
        return f'{self.ressurs_navn}: {self.antall} × {self.problemstilling}'
