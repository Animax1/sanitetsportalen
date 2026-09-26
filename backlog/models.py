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

from core.sortering import Norsk


class Innspilltype(models.Model):
    """Bug, ønske — og det admin ellers finner ut at det trengs.

    **Dette var `choices` i én dag** (17. sep. 2026). Begrunnelsen var at «er
    dette en feil eller et ønske» er et strukturelt skille som ikke endrer seg
    med arrangementet, i motsetning til `vaktliste.Ressursgruppe`. André snudde
    det samme dag: «Kan ikke admin få legge til flere typer?»

    Og han har rett i at det er samme mønster som de andre verdimengdene: et
    behov som melder seg — «spørsmål», «teknisk gjeld», «dokumentasjon» — skal
    ikke vente på en utrulling. Mønsteret er `oppdrag.views_verdier`:
    **navn, `er_aktiv` og `rekkefolge`, slettes bare når ingen bruker den.**

    `er_aktiv` er viktigere enn sletting: en type som har vært i bruk kan ikke
    fjernes uten å ta innspillene med seg (`PROTECT`), og da er «skjul den fra
    nedtrekket» det svaret man faktisk vil ha.
    """

    navn = models.CharField(max_length=40, unique=True, verbose_name='Navn')
    er_aktiv = models.BooleanField(
        default=True,
        verbose_name='Aktiv',
        help_text='Inaktive typer kan ikke velges på nye innspill, men blir '
                  'stående på dem som alt har den.',
    )
    rekkefolge = models.IntegerField(
        default=100,
        verbose_name='Rekkefølge',
        help_text='Styrer rekkefølgen i nedtrekket. Settes automatisk til '
                  'opprettelsesrekkefølgen.',
    )

    class Meta:
        verbose_name = 'Innspilltype'
        verbose_name_plural = 'Innspilltyper'
        ordering = ['rekkefolge', Norsk('navn')]

    def __str__(self):
        return self.navn

    def save(self, *args, **kwargs):
        """En ny type havner sist.

        Regelen ligger her og ikke i viewet fordi den har to lesere — skjemaet
        og en framtidig import — og en regel med to lesere skrives én gang.
        Telleren er `Max` + 10, ikke `count()`: slettes en rad, ville `count()`
        gitt et tall som alt er i bruk.
        """
        if self.pk is None and self.rekkefolge == 100:
            siste = Innspilltype.objects.aggregate(m=models.Max('rekkefolge'))['m']
            self.rekkefolge = (siste or 0) + 10
        super().save(*args, **kwargs)


class Innspill(models.Model):
    """Ett innspill: en bug eller et ønske, løst eller ikke.

    **Løst er et flagg, ikke en sletting.** En løst sak blir stående med
    `lost_av` og `lost_at` satt — det er hele forskjellen på en backlog og en
    huskeliste man stryker i. Lista filtreres på det i stedet.
    """

    #: **`PROTECT`, ikke `CASCADE`.** Slettes en type som er i bruk, ville
    #: innspillene forsvinne med den — og et innspill er nettopp det som ikke
    #: skal kunne forsvinne stille. Viewet svarer 409 med antallet og peker på
    #: `er_aktiv` som veien ut, samme svar som oppdragsmodulens verdimengder.
    type = models.ForeignKey(
        'backlog.Innspilltype',
        on_delete=models.PROTECT,
        related_name='innspill',
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
        return f'{self.type}: {self.tittel}'


class Kommentar(models.Model):
    """En kommentar på ett innspill. Tråden under saken.

    **Kommentarer kan skrives også på en løst sak.** Det er et bevisst avvik fra
    regelen om at et løst innspill ikke kan redigeres: å skrive «rettet i bygg
    f3b279d» *er* svaret, og det skrives etter at flagget er satt. Å stenge
    tråden ved lukking ville gjort det umulig å notere hvordan saken ble løst
    akkurat der noen ville lett etter det.

    **`CASCADE` på innspillet**, fordi en kommentar uten saken sin er en
    setning uten sammenheng. Sperren mot å miste dem ligger et annet sted:
    `services.kan_slettes()` nekter å slette et innspill andre har kommentert.
    """

    innspill = models.ForeignKey(
        'backlog.Innspill',
        on_delete=models.CASCADE,
        related_name='kommentarer',
        verbose_name='Innspill',
    )
    tekst = models.TextField(verbose_name='Kommentar')

    opprettet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='backlog_kommentarer',
        verbose_name='Skrevet av',
    )
    #: Frosset, av samme grunn som på innspillet: en tråd der avsenderen
    #: forsvinner er verdiløs akkurat når den leses.
    opprettet_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Skrevet av (navn)')
    opprettet_at = models.DateTimeField(auto_now_add=True, verbose_name='Skrevet')
    endret_at = models.DateTimeField(auto_now=True, verbose_name='Sist endret')

    class Meta:
        verbose_name = 'Kommentar'
        verbose_name_plural = 'Kommentarer'
        # **Eldste først.** En tråd leses ovenfra og ned; nyeste først ville
        # gjort svaret til å stå over spørsmålet.
        ordering = ['opprettet_at', 'pk']

    def __str__(self):
        return f'{self.opprettet_av_navn}: {self.tekst[:40]}'
