"""Modeller for oppdragsmodulen.

Se ``docs/BESLUTNING_OPPDRAGSMODULEN.md`` for begrunnelsene. De to som er
verdt å ha i hodet når man leser fila:

1. **Enheten har ingen statuskolonne.** «Ledig» er hva «ingen påbegynte
   oppdrag» ser ut som. En lagret status måtte nullstilles ved vaktstart og
   holdes i takt med oppdragsradene resten av vakta; to kilder til samme
   sannhet går i utakt første gang noe feiler halvveis, og da er det den
   lagrede som lyver — den ser autoritativ ut.
2. **`Statusmelding` er et spor, ikke en tilstand.** Rettinger legges som nye
   rader som peker på den gamle. Redigerte man raden, ville «hva sa bilen
   egentlig?» bare kunne besvares fra `AuditLog` — en admin-flate som ikke er
   der oppdraget vises.

Ingen av modellene her rører ``patients``.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import BaseTimeStampedModel

from . import choices


class Enhet(BaseTimeStampedModel):
    """En bil eller beredskapsambulanse.

    Visningsnavnet er atskilt fra brukernavnet med vilje: ``haugesund56`` er en
    innloggingsdetalj, «Haugesund 56» er det man sier på samband.

    **Koblingen til en konto gir ingen tilgang.** Den er domenedata, på samme
    måte som ``Forstehjelper.user`` i pasientmodulen — og §7.3 i
    rollemodellnotatet delte `PasientRolleForm` nettopp for å holde kobling og
    autorisasjon fra hverandre. Uten en ``ModulTilgang('oppdrag', ...)``-rad
    ser kontoen ingenting, enhet eller ei.
    """

    navn = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Enhetsnavn',
        help_text='Navnet som brukes på samband, f.eks. «Haugesund 56».',
    )
    # SET_NULL, ikke CASCADE: slettes kontoen, skal enheten og dens
    # oppdragshistorikk bestå. Samme valg som Forstehjelper.user.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='enhet',
        verbose_name='Innlogget som',
        help_text='Kontoen enheten logger inn med. Bør være en delt konto.',
    )
    # To felter, ikke ett, og forskjellen er hvem som endrer dem og hvor ofte.
    #
    # `er_aktiv` er oppsett: finnes enheten i det hele tatt. Admin pensjonerer
    # en bil, og da skal den bort fra alle lister for godt.
    #
    # `pa_vakt` er drift: er den i tjeneste akkurat nå. 113 tar biler på og av
    # gjennom vakta. Slås de sammen, ser «pensjonert» likt ut som «hjemme i
    # kveld» — og den som skulle skru den på igjen finner den ikke.
    er_aktiv = models.BooleanField(
        default=True,
        verbose_name='Aktiv',
        help_text='Pensjonerte enheter skjules overalt. Settes av admin.',
    )
    pa_vakt = models.BooleanField(
        default=True,
        verbose_name='På vakt',
        help_text='Enheter som ikke er på vakt kan ikke få nye oppdrag.',
    )

    class Meta:
        verbose_name = 'Enhet'
        verbose_name_plural = 'Enheter'
        ordering = ['navn']

    def __str__(self) -> str:
        return self.navn


class Lokasjon(BaseTimeStampedModel):
    """Et sted på arrangementet. Vedlikeholdes av admin.

    Egen tabell framfor en tuple i ``choices.py``: problemstilling og
    hastegrad er faglige verdimengder som endres sjelden og hører hjemme i
    kode, der en endring blir en commit. Lokasjonene skifter fra vakt til
    vakt.

    **Dette flytter personvernrisikoen, til det bedre.** Med en nedtrekksliste
    er lokasjon ikke fritekst, og argumentet i A.6/A.12 — at feltet ikke kan
    inneholde navn — holder. Da står ``Oppdrag.fritekst`` alene igjen som
    feltet som må unntas verdilogging.
    """

    navn = models.CharField(max_length=120, unique=True, verbose_name='Lokasjon')
    er_aktiv = models.BooleanField(
        default=True,
        verbose_name='Aktiv',
        help_text='Inaktive lokasjoner skjules i nedtrekkslista, men beholdes '
                  'på oppdragene som allerede bruker dem.',
    )
    rekkefolge = models.IntegerField(
        default=100,
        verbose_name='Rekkefølge',
        help_text='Lavere kommer først i lista.',
    )

    class Meta:
        verbose_name = 'Lokasjon'
        verbose_name_plural = 'Lokasjoner'
        ordering = ['rekkefolge', 'navn']

    def __str__(self) -> str:
        return self.navn


class Oppdrag(BaseTimeStampedModel):
    """Ett oppdrag, tildelt én enhet.

    ``status`` er en cache av siste gjeldende statusmelding, holdt for at
    lister og filtre skal slippe et underspørsmål per rad. Fasiten om *når*
    noe skjedde ligger i ``Statusmelding``.
    """

    # Vakta oppdraget tilhører — scopet, etter deploy 2. `year` som sto her
    # er borte; vakta bærer året. Se Patient.vakt for resonnementet.
    vakt = models.ForeignKey(
        'core.Vakt',
        on_delete=models.PROTECT,
        related_name='oppdrag',
        verbose_name='Vakt',
    )
    # Løpenummeret man sier på samband: «oppdrag 14». Unikt per vakt —
    # nummeret restarter på 1 hver vakt, slik at det holder seg kort nok til
    # å leses opp, og «oppdrag 14» aldri er tvetydig innenfor vakta.
    oppdragsnummer = models.IntegerField(verbose_name='Oppdragsnummer')
    # PROTECT: et oppdrag uten enhet eller lokasjon gir ingen mening, og
    # historikken skal ikke kunne forsvinne under den.
    enhet = models.ForeignKey(
        Enhet, on_delete=models.PROTECT, related_name='oppdrag', verbose_name='Enhet')
    problemstilling = models.CharField(max_length=255, verbose_name='Problemstilling')
    hastegrad = models.CharField(
        max_length=16, choices=[(h, h) for h in choices.HASTEGRAD],
        verbose_name='Hastegrad')
    lokasjon = models.ForeignKey(
        Lokasjon, on_delete=models.PROTECT, related_name='oppdrag', verbose_name='Lokasjon')
    # Eneste frie felt i modulen. Unntatt verdilogging i audit — se signals.py.
    fritekst = models.TextField(blank=True, default='', verbose_name='Fritekst')
    status = models.CharField(
        max_length=16,
        choices=choices.STATUS_VALG,
        default=choices.VENTER,
        db_index=True,
        verbose_name='Status',
    )
    opprettet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='opprettede_oppdrag',
        verbose_name='Opprettet av')

    # ── Historikk ────────────────────────────────────────────────────────────
    #
    # **Ordet «arkiv» er bevisst unngått her.** `core.arkiv` fryser, signerer
    # og kollapser hele vakter; dette flagget flytter ett oppdrag ut av den
    # aktive tavla og inn i historikken. Raden forblir levende og redigerbar,
    # og ingenting slettes. Vaktarkivet for oppdrag bygges i fase 7 og får en
    # ekte `BaseArkivHandler` i denne appen — bruker vi «arkiv» om begge, står
    # de to med samme navn i samme modul og betyr helt ulike ting.
    #
    # Nullbar dato framfor en boolean: «når gikk den ut av tavla» er verdt å
    # vite når noen leter etter et oppdrag som forsvant fra lista, og en
    # boolean kan ikke svare på det. NULL = står på tavla.
    historikk_fra = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name='I historikk fra')
    historikk_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='oppdrag_lagt_i_historikk',
        verbose_name='Flyttet av')

    class Meta:
        verbose_name = 'Oppdrag'
        verbose_name_plural = 'Oppdrag'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['vakt', 'oppdragsnummer'],
                name='unikt_oppdragsnummer_per_vakt',
            ),
        ]
        indexes = [
            # Enhetsskjermen henter «mine oppdrag» ved hver poll, og
            # sentralbordet filtrerer på vakt + status. Begge går på dette.
            models.Index(fields=['enhet', 'status'], name='oppdrag_enhet_status_idx'),
            models.Index(fields=['vakt', 'status'], name='oppdrag_vakt_status_idx'),
        ]

    def __str__(self) -> str:
        return (f'Oppdrag #{self.oppdragsnummer} – {self.problemstilling} '
                f'({self.get_status_display()})')

    @property
    def er_avsluttet(self) -> bool:
        return self.status == choices.TERMINAL

    @property
    def i_historikk(self) -> bool:
        return self.historikk_fra is not None


class StatusmeldingManager(models.Manager):
    """Manager med regelen «nyeste ikke-korrigerte rad per status vinner».

    Regelen bor her, ikke i en ``if`` per view eller per statistikkspørring.
    Glemmes den ett sted, teller enten det gamle eller det korrigerte
    tidspunktet feil — og det er den stille sorten feil.
    """

    def gjeldende(self, oppdrag):
        """Meldingene som gjelder for oppdraget, én per status.

        En melding er overstyrt hvis en annen melding peker på den via
        ``korrigerer``. Korreksjoner kan kjedes: retter man en retting, er det
        den siste som står, og den forrige blir overstyrt på samme måte.
        """
        alle = list(self.filter(oppdrag=oppdrag).order_by('created_at'))
        overstyrte = {m.korrigerer_id for m in alle if m.korrigerer_id}
        return [m for m in alle if m.pk not in overstyrte]

    def gjeldende_for_status(self, oppdrag, status):
        """Den gjeldende meldingen for én status, eller ``None``."""
        for melding in self.gjeldende(oppdrag):
            if melding.status == status:
                return melding
        return None


class Statusmelding(BaseTimeStampedModel):
    """Én statusovergang, slik den ble meldt.

    Egen tabell framfor fem tidsstempelkolonner på ``Oppdrag``. Kolonner ville
    låst modellen til akkurat disse statusene, og en korreksjon fra 113 ville
    overskrevet historikken i stedet for å legge seg ved siden av den.
    """

    oppdrag = models.ForeignKey(
        Oppdrag, on_delete=models.CASCADE, related_name='statusmeldinger')
    status = models.CharField(max_length=16, choices=choices.STATUS_VALG)
    # Hendelsestid, ikke lagringstid. De to er ikke like når bilen var uten
    # dekning — se `forsinket`.
    tidspunkt = models.DateTimeField(verbose_name='Tidspunkt')
    meldt_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='statusmeldinger',
        verbose_name='Meldt av')
    forsinket = models.BooleanField(
        default=False,
        verbose_name='Meldt forsinket',
        help_text='Klienten var frakoblet da knappen ble trykket.',
    )
    automatisk = models.BooleanField(
        default=False,
        verbose_name='Satt automatisk',
        help_text='Oppdraget ble avsluttet fordi enheten startet det neste.',
    )
    # PROTECT: den korrigerte raden skal ikke kunne forsvinne under
    # korreksjonen — da ville tidslinjen vist en retting av ingenting.
    korrigerer = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='korreksjoner', verbose_name='Korrigerer')

    objects = StatusmeldingManager()

    class Meta:
        verbose_name = 'Statusmelding'
        verbose_name_plural = 'Statusmeldinger'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['oppdrag', 'status'], name='statusmelding_opp_st_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.get_status_display()} {self.tidspunkt:%d.%m %H:%M}'


class Enhetsbytte(BaseTimeStampedModel):
    """113 flyttet oppdraget til en annen enhet.

    Egen modell framfor en radtype i ``Statusmelding``. Et bytte er ikke en
    status, og statistikken måler statusene — blandes de, må hver eneste
    spørring huske å filtrere bort den ene typen. Tidslinjen i grensesnittet
    er unionen av de to, og det er en visningsjobb.

    **Statusen står når et oppdrag flyttes.** Meldingene den første enheten
    rakk å sende blir stående, med ``meldt_av`` intakt: de skjedde. Et oppdrag
    som var `Fremme` er fortsatt `Fremme` når den nye enheten overtar — å
    nullstille til `Venter` ville slettet en responstid som faktisk ble målt.
    """

    oppdrag = models.ForeignKey(
        Oppdrag, on_delete=models.CASCADE, related_name='enhetsbytter')
    fra_enhet = models.ForeignKey(Enhet, on_delete=models.PROTECT, related_name='+')
    til_enhet = models.ForeignKey(Enhet, on_delete=models.PROTECT, related_name='+')
    byttet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='enhetsbytter')

    class Meta:
        verbose_name = 'Enhetsbytte'
        verbose_name_plural = 'Enhetsbytter'
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.fra_enhet} → {self.til_enhet}'
