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
from django.utils import timezone

from core.arkiv import AbstractArkiv
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
    # **Passiv vakt er ikke «av vakt»** (André, 16. sep. 2026). Enheten har en
    # 24/7-vakt gjennom arrangementet; passiv er bakvakt — hun sover, men kan
    # varsles. Derfor et eget felt ved siden av `pa_vakt`, ikke en tredje
    # verdi i det: «kan ikke få nye oppdrag» er noe helt annet enn «ligger og
    # sover, men kommer».
    #
    # Feltet er *tilstanden nå*. Historikken — timene — ligger i
    # `Vaktmodusperiode`, fordi et boolsk felt aldri kan svare på «hvor lenge».
    passiv_vakt = models.BooleanField(
        default=False, verbose_name='Passiv vakt',
        help_text='Bakvakt: enheten kan varsles, men står ikke klar. '
                  'Krever at enhetstypen tillater det.',
    )
    # Typen grupperer enhetene i sentralbordet, ambulansene først (André,
    # 12. sep. 2026). Tom som standard: kontoskjemaet vet ikke hva bilen er,
    # og et gjett ville stått som fasit til noen la merke til det. PROTECT:
    # en type med biler i kan ikke slettes — deaktiver den.
    enhetstype = models.ForeignKey(
        'Enhetstype', null=True, blank=True, on_delete=models.PROTECT,
        related_name='enheter', verbose_name='Enhetstype')

    class Meta:
        verbose_name = 'Enhet'
        verbose_name_plural = 'Enheter'
        ordering = ['navn']

    def __str__(self) -> str:
        return self.navn


class Enhetstype(BaseTimeStampedModel):
    """Grupperingen av enhetene — ambulanse, mannskapsbil, lag til fots.

    Var en tuple i `choices.py` én dag (12. sep. 2026); André ville redigere
    og sortere grupperingene selv, «som i lokasjoner». Rekkefølgen er
    visningsrekkefølgen i tavla og i «Nytt oppdrag». Migrasjon `0020` seeder
    de fire standardtypene.
    """

    navn = models.CharField(max_length=64, unique=True, verbose_name='Enhetstype')
    er_aktiv = models.BooleanField(
        default=True, verbose_name='Aktiv',
        help_text='Inaktive typer tilbys ikke i enhetspanelet, men enheter som har dem beholder dem.')
    rekkefolge = models.IntegerField(default=100, verbose_name='Rekkefølge')
    # **Flaggene bor på typen, ikke på enheten** (André, 16. sep. 2026: «når vi
    # lager gruppene som spesialressurs eller ambulanse»). Da arver hver enhet
    # dem av seg selv, og «Lege 03» opprettet midt i arrangementet har dem med
    # én gang. Per enhet måtte noen husket det hver gang.
    #
    # **To flagg, ikke ett.** «Kan stå passiv» og «kan avvente» har oftest
    # samme svar, men ikke alltid: en frivillig enhet som alltid er aktiv kan
    # godt ha lov til å si nei. Ett flagg ville tvunget fram passiv vakt for
    # noen som ikke har det, bare for å la dem avvente.
    kan_passiv_vakt = models.BooleanField(
        default=False, verbose_name='Kan stå i passiv vakt',
        help_text='Bakvakt gjennom hele arrangementet. Enheter av denne typen '
                  'kan settes aktiv/passiv, og passiv tid dokumenteres.')
    kan_avvente = models.BooleanField(
        default=False, verbose_name='Kan avvente et oppdrag',
        help_text='Operatøren kan sette enheten til «avventer» når hun sier på '
                  'nødnett at hun ikke kan ta oppdraget nå.')

    class Meta:
        verbose_name = 'Enhetstype'
        verbose_name_plural = 'Enhetstyper'
        ordering = ['rekkefolge', 'navn']

    def __str__(self) -> str:
        return self.navn


class Vaktmodusperiode(BaseTimeStampedModel):
    """Én sammenhengende periode der en enhet sto aktiv eller passiv.

    **Et boolsk felt kan ikke svare på «hvor lenge»** (André, 16. sep. 2026:
    «da kan vi logge antall oppdrag og timer brukt i passiv tid når en helst
    skulle sovet»). `Enhet.passiv_vakt` sier hva tilstanden er *nå*; vipper
    noen bryteren klokka 03, er gårsdagen borte uten denne tabellen.

    Audit-loggen redder det ikke. Den ville fanget hver endring, men slettes
    etter to år — og viktigere: en rapport som må rekonstrueres ved å spille
    av en revisjonslogg er ikke en rapport.

    **Scopet til vakta**, som alt annet i modulen: timene gjelder *dette*
    arrangementet. `til` står tom mens perioden løper, og skranken under
    sikrer at det bare finnes én åpen om gangen per enhet og vakt — to åpne
    perioder er et regnestykke som teller de samme timene to ganger.
    """

    AKTIV = 'aktiv'
    PASSIV = 'passiv'
    MODUS = ((AKTIV, 'Aktiv vakt'), (PASSIV, 'Passiv vakt'))

    enhet = models.ForeignKey(
        Enhet, on_delete=models.PROTECT, related_name='vaktmodusperioder',
        verbose_name='Enhet')
    vakt = models.ForeignKey(
        'core.Vakt', on_delete=models.PROTECT, related_name='vaktmodusperioder',
        verbose_name='Vakt')
    modus = models.CharField(max_length=8, choices=MODUS, verbose_name='Modus')
    fra = models.DateTimeField(default=timezone.now, verbose_name='Fra')
    til = models.DateTimeField(null=True, blank=True, verbose_name='Til')
    satt_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+', verbose_name='Satt av')

    class Meta:
        verbose_name = 'Vaktmodusperiode'
        verbose_name_plural = 'Vaktmodusperioder'
        ordering = ['fra']
        constraints = [
            models.UniqueConstraint(
                fields=['enhet', 'vakt'], condition=models.Q(til__isnull=True),
                name='en_apen_vaktmodus_per_enhet'),
        ]

    def __str__(self) -> str:
        return f'{self.enhet} {self.modus} fra {self.fra}'


class Problemstilling(BaseTimeStampedModel):
    """Problemstillingene i nedtrekket, én rad per navn.

    Lå i `choices.py` som to lister til 12. sep. 2026; André ville redigere
    lista og rekkefølgen selv. `kategori` sier hvilke hastegrader raden
    tilbys for: medisinsk (Akutt/Haster/Vanlig), drift, eller begge.
    `Oppdrag.problemstilling` er fortsatt en tekst — arkivets radform er
    signert, og navnet er det som sies på samband — og valideres mot de
    aktive radene her (`verdier.py`).

    **«Udefinert» er en fast rad**: står alltid først, kan ikke endres,
    deaktiveres eller slettes — `services.sett_status` sperrer «Ledig» på
    navnet, og et navn som kan skrives om er ingen sperre.
    """

    MEDISINSK = 'medisinsk'
    DRIFT = 'drift'
    BEGGE = 'begge'
    KATEGORI = (
        (MEDISINSK, 'Medisinsk (Akutt, Haster, Vanlig)'),
        (DRIFT, 'Drift'),
        (BEGGE, 'Begge'),
    )

    navn = models.CharField(max_length=64, unique=True, verbose_name='Problemstilling')
    kategori = models.CharField(
        max_length=12, choices=KATEGORI, default=MEDISINSK, verbose_name='Kategori')
    med_antall = models.BooleanField(
        default=False, verbose_name='Bærer antall',
        help_text='Bilen setter antall pasienter på oppdraget (f.eks. transport).')
    er_aktiv = models.BooleanField(default=True, verbose_name='Aktiv')
    rekkefolge = models.IntegerField(default=100, verbose_name='Rekkefølge')

    class Meta:
        verbose_name = 'Problemstilling'
        verbose_name_plural = 'Problemstillinger'
        ordering = ['rekkefolge', 'navn']

    def __str__(self) -> str:
        return self.navn

    @property
    def er_fast(self) -> bool:
        return self.navn == choices.UDEFINERT

    def passer(self, hastegrad: str) -> bool:
        if self.kategori == self.BEGGE:
            return hastegrad in choices.HASTEGRAD
        if self.kategori == self.DRIFT:
            return hastegrad in choices.UTEN_PASIENT
        return hastegrad in choices.HASTEGRAD and hastegrad not in choices.UTEN_PASIENT


class Lydvarsel(BaseTimeStampedModel):
    """Terskler for lydvarselet i bilen, én rad per hastegrad (André,
    12. sep. 2026: «Admin kan justere frekvens på lydvarsler, både første
    gangs og repeterende, på de ulike hastegradene»). Seedet av `0024` med
    tallene fra første utgave; global admin endrer dem i «Valglister».
    Om det skal pipe når bilen får et nytt oppdrag ligger i `AppSetting`
    (`oppdrag_lyd_nytt`), fordi det ikke er per hastegrad."""

    hastegrad = models.CharField(max_length=16, unique=True, verbose_name='Hastegrad')
    forste_sekunder = models.PositiveIntegerField(
        default=60, verbose_name='Første varsel etter (sekunder)')
    gjenta_sekunder = models.PositiveIntegerField(
        default=60, verbose_name='Gjenta hvert (sekunder)')
    # Per hastegrad av/på (André, 12. sep. 2026). Rører ikke pipet ved nytt
    # oppdrag — det er ikke per hastegrad.
    aktiv = models.BooleanField(default=True, verbose_name='Aktiv')

    class Meta:
        verbose_name = 'Lydvarsel'
        verbose_name_plural = 'Lydvarsler'
        ordering = ['hastegrad']

    def __str__(self) -> str:
        return f'{self.hastegrad}: {self.forste_sekunder}/{self.gjenta_sekunder} s'


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
    # PROTECT: historikken skal ikke kunne forsvinne under oppdraget.
    # **Nullbar fra 19. sep. 2026** (André: «å opprette oppdrag behøver ikke
    # en ressurs»): et oppdrag kan opprettes uten enhet og står da som
    # «Trenger ressurs» (`trenger_ressurs`) til sentralbordet varsler en. Den
    # første som varsles blir primær, og kolonnen fylles da — se
    # `services.varsle_enhet`.
    enhet = models.ForeignKey(
        Enhet, null=True, blank=True, on_delete=models.PROTECT,
        related_name='oppdrag', verbose_name='Enhet')
    problemstilling = models.CharField(max_length=255, verbose_name='Problemstilling')
    hastegrad = models.CharField(
        max_length=16, choices=[(h, h) for h in choices.HASTEGRAD],
        verbose_name='Hastegrad')
    lokasjon = models.ForeignKey(
        Lokasjon, on_delete=models.PROTECT, related_name='oppdrag', verbose_name='Lokasjon')
    # Bilens egen vurdering, satt fra enhetsskjermen (11. sep. 2026). Står
    # ved siden av `hastegrad` — KO/AMKs vurdering ved opprettelsen — ikke i
    # stedet for. Tom betyr «ikke vurdert ennå», og det skal synes.
    grovsortering = models.CharField(
        max_length=16, blank=True, default='', choices=choices.GROVSORTERING,
        verbose_name='Grovsortering')
    # Antall — for problemstillinger som bærer et (`Problemstilling.med_antall`,
    # transport). Tomt for alle andre. Ikke i arkivet: radformen der er del
    # av signaturen på hvert arkiv i prod.
    antall = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Antall')
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
    # **Trenger ny ressurs** (André, 12. sep. 2026): bilen rykket ut på et
    # annet oppdrag mens dette sto uferdig. Hennes rad lukkes automatisk som
    # før, men oppdraget er ikke ferdig — det står på tavla i `Venter` til
    # sentralbordet varsler en ny enhet, som nullstiller flagget.
    trenger_ressurs = models.BooleanField(
        default=False, verbose_name='Trenger ny ressurs')
    # Når det begynte å stå uten noen — sentralbordet viser det tydeligere
    # jo lenger det har stått. Settes sammen med flagget, tømmes med det.
    trenger_ressurs_siden = models.DateTimeField(
        null=True, blank=True, verbose_name='Trenger ny ressurs siden')
    historikk_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='oppdrag_lagt_i_historikk',
        verbose_name='Flyttet av')
    # **Hendelsen oppdraget hører til** (KO pulje 5, 18. sep. 2026). Nullbar,
    # og peker fra oppdrag til hendelse — aldri motsatt — så denne modulen ikke
    # trenger å kjenne `ko`: strengreferanse, ingen import
    # (`ko/tests_avhengighet.py`). **Skrives bare av KO**
    # (`ko.services.knytt_oppdrag`); `oppdrag_til_dict` leser den.
    # `SET_NULL`: slettes hendelsen ved KO-oppryddingen, står oppdraget igjen
    # som før — nummeret identifiserer, FK-en relaterer (§6).
    hendelse = models.ForeignKey(
        'ko.Hendelse', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='oppdrag', verbose_name='Hendelse')

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
        from .services import oppdragsnr
        return (f'Oppdrag {oppdragsnr(self.oppdragsnummer)} – {self.problemstilling} '
                f'({self.get_status_display()})')

    def save(self, *args, **kwargs):
        # **Broen i deploy 1 av flere enheter** (§2.3 i notatet). `enhet` står
        # fortsatt på oppdraget, og all eksisterende kode og alle tester
        # oppretter oppdrag med den. Koblingsraden lages her, slik at ingen
        # av dem trenger å vite at den finnes før deploy 2 fjerner kolonnen.
        ny = self._state.adding
        super().save(*args, **kwargs)
        if ny and self.enhet_id and not self.enheter.exists():
            # **Modusen stemples her også** (16. sep. 2026). Den *første*
            # enheten på et oppdrag får koblingsraden sin herfra, ikke fra
            # `varsle_enhet` — så uten dette ville «oppdrag i passiv tid» bare
            # talt enhetene som ble varslet i tillegg, og aldri den som fikk
            # oppdraget. Funnet av en test som arkiverte og leste tallet
            # tilbake.
            #
            # Lokal import: `services` importerer denne modulen, og regelen
            # skal stå ett sted — skrives den ut for hånd her, finnes den to.
            from .services import gjeldende_modus
            Oppdragsenhet.objects.create(
                oppdrag=self, enhet_id=self.enhet_id, status=self.status,
                varslet_av=self.opprettet_av, rekkefolge=0,
                varslet_modus=gjeldende_modus(self.enhet))

    @property
    def er_avsluttet(self) -> bool:
        return self.status == choices.TERMINAL

    @property
    def primaer(self):
        """Koblingsraden med lavest `rekkefolge` — den først varslede.

        Finnes som begrep bare fordi arkivet og statistikken i dag har én
        `enhet_navn` per rad, og fordi `Oppdrag.enhet` lever til deploy 2.
        """
        return self.enheter.order_by('rekkefolge', 'created_at').first()

    @property
    def i_historikk(self) -> bool:
        return self.historikk_fra is not None


class Oppdragsenhet(BaseTimeStampedModel):
    """Én enhet på ett oppdrag — med sin egen statuskjede.

    Flere enheter på ett oppdrag (11. sep. 2026, `docs/BESLUTNING_FLERE_
    ENHETER_PER_OPPDRAG.md`). Fram til da var oppdraget «tildelt én enhet»,
    og statusmeldingene hang på oppdraget. Nå er en statusmelding *én enhets*
    utsagn om *ett* oppdrag, og den henger her.

    ``status`` er en cache av siste gjeldende melding for denne enheten, på
    samme måte som `Oppdrag.status` var det — og `Oppdrag.status` er fra nå
    *utledet* av disse: den mest aktive, `Ledig` bare når alle er ledige
    (`services.utledet_status`).
    """

    oppdrag = models.ForeignKey(
        Oppdrag, on_delete=models.CASCADE, related_name='enheter',
        verbose_name='Oppdrag')
    # PROTECT: en enhet med oppdrag bak seg kan pensjoneres, ikke slettes.
    enhet = models.ForeignKey(
        Enhet, on_delete=models.PROTECT, related_name='oppdragsenheter',
        verbose_name='Enhet')
    status = models.CharField(
        max_length=16, choices=choices.STATUS_VALG, default=choices.VENTER,
        db_index=True, verbose_name='Status')
    varslet_at = models.DateTimeField(
        default=timezone.now, verbose_name='Varslet')
    varslet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='varslede_enheter',
        verbose_name='Varslet av')
    # **Modusen fryses ved varsling** (16. sep. 2026). To grunner, og den
    # andre er den som biter først:
    #
    # 1. «Hvor mange oppdrag kom i passiv tid» kan bare svares eksakt her.
    #    Leses `Enhet.passiv_vakt` i ettertid, teller man dagens tilstand.
    # 2. Merket «Lege 02 (passiv vakt)» på et oppdrag fra tre timer siden
    #    ville skiftet tekst i det noen vipper bryteren. Samme grunn som at
    #    `importert_av` fryses som navn i arkivet.
    #
    # Tom streng for alt som ble varslet før feltet fantes — og for enheter
    # uten passiv vakt i det hele tatt, som er de fleste.
    varslet_modus = models.CharField(
        max_length=8, blank=True, default='',
        choices=(('aktiv', 'Aktiv vakt'), ('passiv', 'Passiv vakt')),
        verbose_name='Vaktmodus ved varsling')
    # Den først varslede er «primær» — se `Oppdrag.primaer`.
    rekkefolge = models.PositiveSmallIntegerField(default=0, verbose_name='Rekkefølge')

    class Meta:
        verbose_name = 'Oppdragsenhet'
        verbose_name_plural = 'Oppdragsenheter'
        ordering = ['rekkefolge', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['oppdrag', 'enhet'], name='unik_enhet_per_oppdrag'),
        ]
        indexes = [
            models.Index(fields=['enhet', 'status'], name='oppdragsenhet_enh_st_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.enhet.navn} på #{self.oppdrag.oppdragsnummer} ({self.get_status_display()})'

    @property
    def er_avsluttet(self) -> bool:
        return self.status == choices.TERMINAL


class Enhetshendelse(BaseTimeStampedModel):
    """En hendelse på oppdraget som ikke er en status: en enhet ble tatt av.

    Koblingsraden slettes når enheten tas av mens hun venter, og da sto det
    ingenting igjen i tidslinjen (André, 12. sep. 2026: «hvem som er
    fjernet, for synligheten»). Varslingen leses av koblingsradens
    `varslet_at`; det er bare fjerningen som trenger et eget spor.
    """

    TATT_AV = 'tatt_av'
    RYKKET_VIDERE = 'rykket_videre'
    AVBRUTT = 'avbrutt'
    # **«Avvente» er en hendelse, ikke en status** (André, 16. sep. 2026).
    # Koblingsraden blir stående i `Venter`, så operatøren kan trykke «Rykk
    # ut» på henne senere og begge deler står i loggen. En ny *status* ville
    # krevd en kolonne i `ArkivertOppdrag` og en beslutning om SHA-payloaden;
    # en hendelse rører ikke signaturen i det hele tatt.
    AVVENTER = 'avventer'
    TYPER = (
        (TATT_AV, 'Tatt av oppdraget'),
        # Bilen rykket ut på et annet oppdrag mens dette sto uferdig
        # (12. sep. 2026). `detalj` bærer nummeret på det hun dro til.
        (RYKKET_VIDERE, 'Rykket ut på et annet oppdrag'),
        # Bilen trykket «Avbryt» i Rykker ut (12. sep. 2026): hun er ledig,
        # oppdraget står som «trenger ny ressurs».
        (AVBRUTT, 'Avbrøt oppdraget'),
        # Operatøren satte enheten til «avventer» — hun sa på nødnett at hun
        # ikke kan ta oppdraget nå (16. sep. 2026).
        (AVVENTER, 'Avventer oppdraget'),
    )

    oppdrag = models.ForeignKey(
        Oppdrag, on_delete=models.CASCADE, related_name='enhetshendelser')
    enhet = models.ForeignKey(Enhet, on_delete=models.PROTECT, related_name='+')
    type = models.CharField(max_length=16, choices=TYPER, verbose_name='Hendelse')
    detalj = models.CharField(max_length=64, blank=True, default='', verbose_name='Detalj')
    tidspunkt = models.DateTimeField(default=timezone.now)
    # **Når enheten ble varslet på oppdraget** (21. sep. 2026, statistikk
    # pulje 7b). Koblingsraden slettes ved «tatt av», og med den forsvant
    # det eneste sporet av hvor lenge bilen sto bundet uten å rykke ut —
    # nettopp tallet lista «tildelt, men rykket aldri ut» finnes for. Settes
    # for alle typer, så hendelsen bærer sin egen «hadde vært på oppdraget
    # i». `None` for hendelser fra før feltet fantes.
    varslet_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Varslet på oppdraget')
    av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    # **Kvittering på en avbrytelse** (André, 15. sep. 2026: «trykker en bil
    # avbryt så må det vises, og at det må løses av operatør»). Merket står
    # til noen har tatt stilling — enten ved å sende en ny enhet, som
    # kvitterer av seg selv, eller ved å kvittere manuelt når ingen skal
    # sendes. Per hendelse og ikke per oppdrag: avbryter to biler, er det to
    # ting å ta stilling til, og hvem som gjorde det er verdt å vite.
    kvittert_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Kvittert')
    kvittert_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+', verbose_name='Kvittert av')

    class Meta:
        ordering = ['tidspunkt']
        verbose_name = 'Enhetshendelse'
        verbose_name_plural = 'Enhetshendelser'


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
        return self.gjeldende_bulk([oppdrag.pk])[oppdrag.pk]

    def gjeldende_bulk(self, oppdrag_ider):
        """Samme regel som ``gjeldende()``, for mange oppdrag i én spørring.

        Statistikken går gjennom hele vaktas oppdrag. Ett kall per oppdrag ga
        én spørring per rad — men å skrive regelen om til en spørring der
        borte ville vært verre: da fantes «nyeste ikke-korrigerte rad» to
        steder, og den ene ville før eller siden telt det korrigerte
        tidspunktet. Regelen står derfor fortsatt bare her, og ``gjeldende()``
        er nå ett oppslag i dette resultatet.

        Returnerer ``{oppdrag_id: [melding, ...]}`` med en tom liste for
        oppdrag uten meldinger, slik at kalleren slipper `.get(pk, [])`.
        """
        ider = list(oppdrag_ider)
        # Enheten bak hver melding følger med: tidslinjen med flere enheter
        # skriver «HGSD 56: Fremme», og skal ikke koste én spørring per rad.
        alle = list(self.filter(oppdrag_id__in=ider)
                    .select_related('oppdragsenhet__enhet', 'meldt_av')
                    .order_by('created_at'))
        overstyrte = {m.korrigerer_id for m in alle if m.korrigerer_id}
        ut = {pk: [] for pk in ider}
        for melding in alle:
            if melding.pk not in overstyrte:
                ut[melding.oppdrag_id].append(melding)
        return ut

    def gjeldende_for_enhet(self, oppdragsenhet):
        """De gjeldende meldingene for én enhet på oppdraget, én per status.

        Med flere enheter kan oppdraget ha to `Fremme` som gjelder — én per
        bil. Spørsmål som handler om *bilen* går her; `gjeldende(oppdrag)` er
        hele oppdragets spor.
        """
        return [m for m in self.gjeldende(oppdragsenhet.oppdrag)
                if m.oppdragsenhet_id == oppdragsenhet.pk]

    def gjeldende_for_status(self, oppdrag, status, *, oppdragsenhet=None):
        """Den gjeldende meldingen for én status, eller ``None``.

        Uten `oppdragsenhet` er det **siste** meldingen med statusen som
        gjelder, uansett enhet — det som svarer på «når fikk oppdraget denne
        statusen». Med `oppdragsenhet` er det bilens egen.
        """
        treff = None
        for melding in self.gjeldende(oppdrag):
            if oppdragsenhet is not None and melding.oppdragsenhet_id != oppdragsenhet.pk:
                continue
            if melding.status == status:
                treff = melding
        return treff


class Statusmelding(BaseTimeStampedModel):
    """Én statusovergang, slik den ble meldt.

    Egen tabell framfor fem tidsstempelkolonner på ``Oppdrag``. Kolonner ville
    låst modellen til akkurat disse statusene, og en korreksjon fra 113 ville
    overskrevet historikken i stedet for å legge seg ved siden av den.
    """

    oppdrag = models.ForeignKey(
        Oppdrag, on_delete=models.CASCADE, related_name='statusmeldinger')
    # **Hvilken enhet som meldte.** Meningsbærende nøkkel fra 11. sep. 2026;
    # `oppdrag` over er avledet av den og beholdes for spørringene som går
    # på oppdrag (`gjeldende_bulk`). Nullbar i deploy 1 — settes i `save()`
    # fra `oppdrag.enhet` når den mangler, slik at eldre kode virker.
    oppdragsenhet = models.ForeignKey(
        Oppdragsenhet, null=True, blank=True, on_delete=models.CASCADE,
        related_name='statusmeldinger', verbose_name='Enhet på oppdraget')
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
    # Ført av sentralbordet (§9, 11. sep. 2026) — ikke stemplet av bilen.
    # Lagret, ikke utledet av `meldt_av`: en konto kan bytte enhet, og da
    # ville historien skiftet mening.
    manuell = models.BooleanField(
        default=False, verbose_name='Ført manuelt',
        help_text='Ført av sentralbordet, ikke stemplet av enheten.')
    # Hvor bilen dro — bare meningsfullt for `avreist` (11. sep. 2026).
    # Ligger på meldingen, ikke på oppdraget: meldingen er *det som ble
    # meldt*, og en korreksjon er en ny rad som arver stedet.
    sted = models.CharField(
        max_length=20, blank=True, default='', choices=choices.AVREIST_TIL,
        verbose_name='Avreist til')
    # «Annet sted» får et fritekstfelt (André, 19. sep. 2026). Bare
    # meningsfullt når `sted == 'annet'`; tømmes ellers i `sett_status`.
    # Fritekst som `Oppdrag.fritekst`: logges som endret, aldri verdien.
    sted_tekst = models.CharField(
        max_length=120, blank=True, default='', verbose_name='Annet sted')
    # PROTECT: den korrigerte raden skal ikke kunne forsvinne under
    # korreksjonen — da ville tidslinjen vist en retting av ingenting.
    korrigerer = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='korreksjoner', verbose_name='Korrigerer')

    objects = StatusmeldingManager()

    def save(self, *args, **kwargs):
        # Broen (§2.3): en melding laget med bare `oppdrag` hører til
        # oppdragets primære enhet. Alle nye veier inn oppgir koblingsraden
        # eksplisitt; dette er for koden og testene som ennå ikke gjør det.
        if self.oppdragsenhet_id is None and self.oppdrag_id is not None:
            self.oppdragsenhet = self.oppdrag.primaer
        elif self.oppdrag_id is None and self.oppdragsenhet_id is not None:
            self.oppdrag_id = self.oppdragsenhet.oppdrag_id
        super().save(*args, **kwargs)

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


# ── Arkiv (fase 7) ───────────────────────────────────────────────────────────
#
# Egne modeller, ikke rader i `Oppdrag` med et flagg. Et arkivert oppdrag er
# et *frosset* oppdrag: enheten kan pensjoneres, lokasjonen fjernes og vakta
# slettes uten at arkivet skal endre seg. Derfor er alt som beskriver raden
# kopiert inn som tekst, på samme måte som `ArkivertPasient` fryser
# behandlernavnet.
#
# Merk skillet mot `Oppdrag.historikk_fra`: den er *rydding av tavla* og fullt
# reversibel. Dette er frysing, med signatur og kollaps — det er to helt ulike
# handlinger, og de ligger derfor på hver sin knapp.


class OppdragArkiv(AbstractArkiv):
    """Låst arkiv-snapshot av oppdragene i én vakt.

    Feltene ligger i `core.arkiv.AbstractArkiv` — dette er modell nummer to,
    og den som gjorde basemodellen mulig å skrive uten å gjette.
    """

    class Meta(AbstractArkiv.Meta):
        verbose_name = 'Oppdragsarkiv'
        verbose_name_plural = 'Oppdragsarkiver'


class ArkivertOppdrag(models.Model):
    """Ett frosset oppdrag. Read-only via design.

    **Tidspunktene er flate kolonner, ikke en kopi av statusmeldingene.**
    Statusene er en lukket verdimengde (`choices.STATUS_VALG`), og flate
    kolonner gjør arkivet lesbart både for et menneske og for
    statistikk-koden. `ArkivOppdragsstatusKolonnerTests` sjekker at hver
    status i kjeden har en kolonne — legges en status til, må arkivet følge
    med, og da skal testen si fra i stedet for at tallene stille mister et
    ledd.

    Rettinger er allerede regnet inn: radene bygges fra `gjeldende()`, så det
    er det korrigerte tidspunktet som fryses. Originalen ligger igjen i
    `Statusmelding` fram til vakta slettes, og i auditsporet etterpå.
    """

    arkiv = models.ForeignKey(
        OppdragArkiv, on_delete=models.CASCADE, related_name='oppdrag',
        verbose_name='Arkiv')
    oppdragsnummer = models.IntegerField(verbose_name='Oppdragsnummer')

    # Frosne tekster. FK-ene ville ikke overlevd at en enhet pensjoneres og
    # slettes, eller at en lokasjon fjernes fra lista.
    # **Modusen følger med i arkivet** (16. sep. 2026). Uten den ville
    # «oppdrag i passiv tid» forsvunnet i det vakta ble arkivert — altså
    # nøyaktig når rapporten skrives. Den står i SHA-payloaden **bare når
    # satt**, som `behandlet_at`, så eldre arkiv verifiserer uendret.
    varslet_modus = models.CharField(
        max_length=8, blank=True, default='',
        verbose_name='Vaktmodus ved varsling')
    enhet_navn = models.CharField(max_length=64, blank=True, default='',
                                  verbose_name='Enhet (navn)')
    lokasjon_navn = models.CharField(max_length=120, blank=True, default='',
                                     verbose_name='Lokasjon (navn)')
    problemstilling = models.CharField(max_length=255, blank=True, default='',
                                       verbose_name='Problemstilling')
    hastegrad = models.CharField(max_length=16, blank=True, default='',
                                 verbose_name='Hastegrad')
    sluttstatus = models.CharField(
        max_length=16, blank=True, default='', verbose_name='Status ved arkivering',
        help_text='Statusen oppdraget sto i da vakta ble arkivert.')

    # `fritekst` arkiveres IKKE. Feltet er unntatt verdilogging i audit
    # (§9 i beslutningsnotatet) nettopp fordi det kan inneholde noe en
    # operatør skrev og angret på — å fryse det i et arkiv med 24 måneders
    # lagringstid ville gjort unntaket meningsløst.

    opprettet_at = models.DateTimeField(verbose_name='Opprettet')
    rykker_ut_at = models.DateTimeField(null=True, blank=True, verbose_name='Rykker ut')
    fremme_at = models.DateTimeField(null=True, blank=True, verbose_name='Fremme')
    avreist_at = models.DateTimeField(null=True, blank=True, verbose_name='Avreist')
    leverer_at = models.DateTimeField(null=True, blank=True, verbose_name='Leverer')
    # «Behandlet på sted» (12. sep. 2026). I SHA-payloaden **bare når satt**:
    # eldre arkiv har ingen slik kolonne i signaturen sin, og et felt som
    # alltid sto med `null` ville meldt tukling på hvert av dem. Se
    # `OppdragArkivHandler.rader_for_payload`.
    behandlet_at = models.DateTimeField(null=True, blank=True, verbose_name='Behandlet på sted')
    ledig_at = models.DateTimeField(null=True, blank=True, verbose_name='Ledig')

    # **Statistikk pulje 7b** (21. sep. 2026). Fire felt til, alle i
    # SHA-payloaden **bare når satt**, som `varslet_modus`: eldre arkiv
    # verifiserer uendret. `avreist_til_tekst` finnes med vilje *ikke* —
    # «Annet sted» er fritekst og følger `fritekst`-regelen over.
    varslet_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Varslet',
        help_text='Når enheten ble varslet på oppdraget. Bærer reaksjonstida.')
    grovsortering = models.CharField(
        max_length=16, blank=True, default='', verbose_name='Grovsortering')
    avreist_til = models.CharField(
        max_length=20, blank=True, default='', verbose_name='Avreist til')
    #: Oppdragets enhetshendelser — tatt av, rykket videre, avbrutt, avventer
    #: — som `[{type, tidspunkt, varslet_at, enhet}]` med ISO-tidspunkt.
    #: **Oppdragets, ikke radens**, og gjentatt på hver rad som `hastegrad`
    #: er: en enhet som ble tatt av har ingen rad, og hendelsen hennes må
    #: likevel med. Leseren tar dem fra første rad per nummer.
    enhetshendelser = models.JSONField(
        default=list, blank=True, verbose_name='Enhetshendelser')

    #: Statusene som ble stemplet automatisk, som liste med statusnavn.
    #: §12.2: en varighet som slutter i en slik stempling er avledet, ikke
    #: målt, og telles ikke. Lagres som data framfor én bool per status: i dag
    #: er det bare `ledig` som kan settes automatisk, men det er en egenskap
    #: ved `start_oppdrag` — ikke ved arkivet — og et arkiv som antok det ville
    #: løyet den dagen antakelsen ikke holdt.
    automatiske_statuser = models.JSONField(
        default=list, blank=True, verbose_name='Automatiske stemplinger')
    antall_forsinket = models.IntegerField(
        default=0, verbose_name='Forsinket meldte stemplinger',
        help_text='Stemplinger sendt fra en enhet som var uten dekning.')

    class Meta:
        # Én rad per oppdrag × enhet (flere enheter, 11. sep. 2026, §5 A i
        # notatet): nummeret gjentas for hver bil, med hennes tidsstempler.
        # Eldre arkiver har én rad per oppdrag og passer som før.
        unique_together = [['arkiv', 'oppdragsnummer', 'enhet_navn']]
        ordering = ['oppdragsnummer', 'enhet_navn']
        verbose_name = 'Arkivert oppdrag'
        verbose_name_plural = 'Arkiverte oppdrag'

    def __str__(self) -> str:
        from .services import oppdragsnr
        return f'{oppdragsnr(self.oppdragsnummer)} {self.problemstilling}'
