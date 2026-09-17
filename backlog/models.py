"""Backlog: endringsønsker og bugs, ett innspill per rad.

Formålet er å samle det som ellers ligger spredt i chatter. Modulen er
utviklingsverktøy for et knippe mennesker, ikke en flate for alle som går vakt.

**Ingen `vakt`, og det er et bevisst avvik.** Alt annet i portalen er scopet til
en vakt (`core.Vakt`) fordi dataene beskriver *det som skjedde på en vakt*. Et
innspill beskriver **portalen**, ikke en vakt: «nedtrekket lukker seg når jeg
velger» gjelder like mye i oktober som i august. Scopet det til vakta, ville
lista tømt seg selv ved hvert vaktbytte — og en backlog som glemmer er ikke en
backlog.

**Ingen feltnivå-audit, samme begrunnelse som vaktlistas registre.** De
auditlogges ikke fordi de er organisasjonsoppsett uten personopplysninger;
dette er utviklingsmetadata av samme slag. Det ene som *må* kunne leses i
ettertid — hvem som satte noe løst — står som felter på raden (`lost_av`,
`lost_at`), der det også er synlig for den som leser lista. En auditrad ville
båret det samme ett sted til, og bare den ene av de to ville blitt lest.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Innspilltype(models.TextChoices):
    """Bug eller ønske.

    **`choices` og ikke en tabell**, i motsetning til `vaktliste.Ressursgruppe`
    og oppdragsmodulens verdimengder. Skillet er om verdimengden er
    *organisasjonens* eller *portalens*: en vaktleder kan trenge en dronegruppe
    i kveld og kan ikke vente på en utrulling, mens «er dette en feil eller et
    ønske» er et strukturelt skille som ikke endrer seg med arrangementet.

    Trengs en tredje verdi en dag — «spørsmål», «teknisk gjeld» — er det en
    migrasjon på én linje. Blir de mange og skiftende, er `Verdimengde` i
    oppdragsmodulen mønsteret å flytte til.
    """

    BUG = 'bug', 'Bug'
    ONSKE = 'onske', 'Ønske'


class Innspill(models.Model):
    """Ett innspill: en bug eller et ønske, løst eller ikke.

    **Løst er et flagg, ikke en sletting.** En løst sak blir stående med
    `lost_av` og `lost_at` satt — det er hele forskjellen på en backlog og en
    huskeliste man stryker i. Lista filtreres på det i stedet.
    """

    type = models.CharField(
        max_length=16,
        choices=Innspilltype.choices,
        db_index=True,
        verbose_name='Type',
    )
    tittel = models.CharField(
        max_length=200,
        verbose_name='Tittel',
        help_text='Én setning. Det du ville sagt i chatten.',
    )
    beskrivelse = models.TextField(
        blank=True,
        default='',
        verbose_name='Beskrivelse',
        help_text='Valgfritt. Hva du gjorde, hva du forventet, hva som skjedde.',
    )
    #: Hvilken modul innspillet gjelder. **Slug, ikke FK** — modulregisteret
    #: ligger i kode (`core.modules`), ikke i basen, av samme grunn som
    #: `ModulTilgang.modul_slug`: en rad for en modul som er fjernet fra
    #: registeret skal bli liggende ubrukt i stedet for å blokkere slettingen.
    #: Tom streng betyr «gjelder ikke én bestemt modul», som er et gyldig svar.
    modul_slug = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        verbose_name='Gjelder modul',
    )

    opprettet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='backlog_innspill',
        verbose_name='Meldt inn av',
    )
    #: **Navnet fryses på raden.** Kontoer slettes og visningsnavn endres, og en
    #: liste der avsenderen forsvinner er verdiløs akkurat når den leses. FK-en
    #: står ved siden av og bærer «er dette meg?»-spørsmålet så lenge kontoen
    #: finnes; navnet bærer «hvem skrev dette» for alltid. Samme grep som
    #: `importert_av_navn` på arkivene.
    opprettet_av_navn = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Meldt inn av (navn)',
    )
    opprettet_at = models.DateTimeField(auto_now_add=True, verbose_name='Meldt inn')
    endret_at = models.DateTimeField(auto_now=True, verbose_name='Sist endret')

    lost = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Løst',
    )
    lost_av = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='backlog_lost',
        verbose_name='Løst av',
    )
    lost_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Løst av (navn)')
    lost_at = models.DateTimeField(null=True, blank=True, verbose_name='Løst når')

    class Meta:
        verbose_name = 'Innspill'
        verbose_name_plural = 'Innspill'
        # Nyeste først. Uløste og løste blandes med vilje — filteret er
        # brukerens valg, og en standardsortering som skjulte de løste ville
        # vært et filter ingen hadde slått på.
        ordering = ['-opprettet_at', '-pk']

    def __str__(self):
        return f'{self.get_type_display()}: {self.tittel}'
