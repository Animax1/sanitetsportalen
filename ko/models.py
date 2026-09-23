"""KO-loggen (pulje 2) — én tabell med alle linjer.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Modulen eier fortsatt ingen
ressurser; det som kommer hit er *det som ble sagt og det som skjedde*, ikke et
register over hvem som finnes. `Hendelse` (pulje 5) er grupperingen av
oppdragslista og filteret i loggen — se klassen nederst.

**Én tabell, ikke to** (§4.1). Menneskeskrevne linjer, kommentarer og de
systemhendelsene som løftes inn ligger side om side. Det gir hele loggen og
hendelsen-som-filter gratis, og det er den eneste formen der «en linje kan
knyttes til en hendelse i etterkant» er en oppdatering og ikke en flytting.

**Den er ikke audit-loggen** (§4.2). `audit/` er automatisk, på feltnivå,
teknisk, og finnes for sikkerhet. Denne er menneskeskrevet, append-only,
utskrivbar, og i praksis dokumentet man leser etter et arrangement der noe gikk
galt. De to skal ikke slås sammen, og **det er derfor `tekst` aldri får en
verdiloggende auditrad** — se `ko/signals.py`. Ville innholdet ligget i
auditloggen i 730 dager uansett, var sletteinngangen under et skuespill.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone


#: Hvem som skrev linja. To verdier, og skillet er det §3.1 kaller «bilen sa
#: det» mot «KO førte det» — det skal være synlig i grensesnittet og i loggen,
#: ikke noe man utleder av at forfatteren tilfeldigvis er en delt konto.
KILDE_OPERATOR = 'operator'
KILDE_SYSTEM = 'system'
KILDE_VALG: tuple[tuple[str, str], ...] = (
    (KILDE_OPERATOR, 'Ført av operatør'),
    (KILDE_SYSTEM, 'Systemhendelse'),
)


class LogglinjeManager(models.Manager):
    """Regelen «nyeste ikke-korrigerte rad i kjeden vinner», ett sted.

    Bevisst samme form som `oppdrag.StatusmeldingManager.gjeldende()`, som
    §4.3 peker på som mønsteret. Den ligger i en manager og ikke i en `if` per
    view av samme grunn som der: glemmes den ett sted, viser den visningen det
    gamle tidspunktet, og da er loggen uenig med seg selv.
    """

    def gjeldende(self, vakt):
        """Linjene som skal vises for `vakt`, i fortellingens rekkefølge.

        En linje er overstyrt når en annen linje peker på den via
        ``korrigerer``. Korreksjoner kan kjedes: retter man en retting, er det
        den siste som står.

        **Rekkefølgen er registreringsrekkefølgen til den første linja i
        kjeden, ikke `tidspunkt`** (§4.3). Rettes et klokkeslett fra 21:40 til
        21:14, skal linja bli stående der den sto — ellers hopper den bakover
        forbi fem andre linjer, og fortellingen blir uleselig. Det er som
        fortelling loggen har verdi.
        """
        return (self.filter(vakt=vakt)
                    .filter(korrigert_av__isnull=True)
                    .select_related('forfatter', 'fjernet_av', 'hendelse')
                    .prefetch_related('delinger')
                    .order_by(Coalesce('rot_id', 'id'), 'id'))


class Logglinje(models.Model):
    """Én linje i KO-loggen.

    **Append-only, med ett navngitt unntak.** Retting skjer som en ny rad som
    peker på den gamle (§4.3), aldri ved å endre den. Det ene som *endrer* en
    rad er sletteinngangen i §4.4, og den tømmer innholdet uten å fjerne rada.

    **Ingen FK til `oppdrag.Oppdrag`, med vilje.** `oppdrag.arkiv.arkiver_vakt`
    sletter oppdragsradene når vakta arkiveres — «oppdragene slettes fra tavla
    og historikken når de er frosset, og telleren nullstilles». En FK hit ville
    vært en felle uansett `on_delete`: `PROTECT` blokkerer arkiveringen,
    `CASCADE` sletter halve loggen stille, `SET_NULL` etterlater en linje som
    sier «meldte Fremme» uten å si hvem. Linja **fryser teksten** i stedet, som
    §4.5 og §4.7 alt krever for brukernavn og kallesignal.
    """

    objects = LogglinjeManager()

    #: Scopet, som alt annet. `PROTECT` fordi loggen er det som overlever
    #: vakta — en vakt som lar seg slette under en logg ville tatt
    #: fortellingen med seg.
    vakt = models.ForeignKey(
        'core.Vakt', on_delete=models.PROTECT,
        related_name='ko_logglinjer', verbose_name='Vakt')

    kilde = models.CharField(
        max_length=16, choices=KILDE_VALG, default=KILDE_OPERATOR,
        db_index=True, verbose_name='Kilde')

    #: Hvilken systemhendelse dette er, fra `ko.systemlinjer.KODER`. Tom for
    #: menneskeskrevne linjer. **Kode og data, ikke ferdig tekst**: setningen
    #: skal kunne skrives om — «O45» i stedet for «#45» når pulje 3 innfører
    #: nummerserien — uten at historikken må skrives om med den. Identitetene
    #: som *kan forsvinne* fryses derimot i `systemdata`, jf. §4.5.
    systemkode = models.CharField(
        max_length=32, blank=True, default='', db_index=True,
        verbose_name='Systemkode')

    #: Frosne verdier systemlinja trenger for å kunne tegnes om: kallesignal,
    #: oppdragsnummer, statusnavn. Aldri fritekst.
    systemdata = models.JSONField(
        default=dict, blank=True, verbose_name='Systemdata')

    #: **Når det faktisk skjedde.** Korrigerbart — men bare ved en ny rad.
    tidspunkt = models.DateTimeField(db_index=True, verbose_name='Tidspunkt')

    #: **Når linja ble skrevet.** Aldri korrigerbart, og derfor `auto_now_add`
    #: og ikke et felt noen kan sende inn. De to blandes aldri (§4.3).
    registrert_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name='Registrert')

    #: Selve linja. Tom for systemlinjer, og tom for en linje som er fjernet.
    tekst = models.TextField(blank=True, default='', verbose_name='Tekst')

    #: **Frosset navn ved siden av FK-en** (§4.5). Visningsnavn endres og
    #: kontoer slettes, og en logg der avsenderen forsvinner er verdiløs
    #: akkurat når den leses.
    forfatter = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_logglinjer',
        verbose_name='Ført av')
    forfatter_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Ført av (navn)')

    #: **En delt konto må se ut som en delt konto i loggen** (§4.5). «Enhet 2»
    #: er to til tre personer man må slå opp i vaktlista for å finne; «Kari
    #: Nordmann» er én. Blir loggen lest i en personalsak, er den forskjellen
    #: alt — og den kan ikke slås opp i ettertid, fordi kontoen kan ha byttet
    #: type siden. Derfor frosset her, og ikke lest fra `CustomUser`.
    forfatter_delt_konto = models.BooleanField(
        default=False, verbose_name='Delt konto')

    #: **Ansvarsområde vises, tilgangsnivå styrer** (§5.1). Fritt felt fordi
    #: det *ikke* gater noe: «bare sambandsoperatøren kan føre sambandslinjer»
    #: dobler matrisen, og første gang den rette er opptatt møter du en vegg i
    #: en situasjon der vegger er dyre. KO er et rom der folk dekker for
    #: hverandre.
    ansvarsomraade = models.CharField(
        max_length=40, blank=True, default='', verbose_name='Ansvarsområde')

    #: Linja denne retter. Speiler `Statusmelding.korrigerer`.
    korrigerer = models.OneToOneField(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='korrigert_av', verbose_name='Korrigerer')

    #: **Første linje i korreksjonskjeden**, og bare til sortering. Uten den
    #: ville en retting av en retting (A ← B ← C) havnet på B sin plass i
    #: fortellingen, som er like galt som å havne sist. `NULL` betyr «jeg er
    #: første ledd», og `Coalesce('rot_id', 'id')` gjør de to til én sortering
    #: uten en join.
    rot = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='kjede', verbose_name='Første ledd')

    #: Sletteinngangen (§4.4). Satt betyr «innholdet er tømt» — rada står, og
    #: linja viser «fjernet av André, 22:10». Append-only og «fjern
    #: personopplysninger» står i direkte konflikt, og konflikten løses med én
    #: navngitt vei, ikke med en generell redigering.
    fjernet_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name='Fjernet')
    fjernet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_fjernede_logglinjer',
        verbose_name='Fjernet av')
    fjernet_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Fjernet av (navn)')

    #: **Hendelsen linja hører til, om noen** (§4.1). Nullbar, og settes i
    #: etterkant like gjerne som ved skriving: man skjønner fem linjer på
    #: etterskudd at de hørte sammen. `SET_NULL`, ikke `CASCADE` — slettes en
    #: hendelse ved oppryddingen, skal linja bli stående; det er loggen som er
    #: fasit, hendelsen er en gruppering av den.
    hendelse = models.ForeignKey(
        'Hendelse', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='linjer', verbose_name='Hendelse')

    #: **Chat er ikke en egen tabell** (§4.5, pulje 6) — det er en linje i
    #: samme logg med dette merket. Er chatten et eget sted, kommer dagen da
    #: den viktigste setningen ble sagt der og ikke står i loggen. Merket gjør
    #: to ting: linja tegnes dempet, og admin-bryteren `ko.chat_tillatt`
    #: avgjør om operatørene får sette det — ikke om linjene som alt finnes
    #: vises.
    uformell = models.BooleanField(default=False, verbose_name='Uformell (chat)')

    #: **Delt med enhetene** (André, 19. sep. 2026). Loggen i hendelsen er
    #: intern i KO til operatøren deler en linje; da ser hver enhet med
    #: oppdrag fra hendelsen den — også oppdrag som kommer til etterpå («alt
    #: som er delt skal deles med alle framtidige og pågående oppdrag»). Kan
    #: angres. Deling med **ett** oppdrag er `Linjedeling`. Et flagg på linja
    #: og ikke en rad per oppdrag, nettopp fordi framtidige oppdrag skal
    #: arve den uten at noen kopierer.
    delt_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name='Delt')
    delt_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_delte_logglinjer',
        verbose_name='Delt av')
    delt_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Delt av (navn)')

    #: **Festet i loggstrømmen** (André, 18. sep. 2026: «Nyttige beskjeder,
    #: noen skal kunne pinnes»). Et tidspunkt og ikke en boolsk verdi, så
    #: rekkefølgen blant de festede er «sist festet nederst» uten en kolonne
    #: til. Navnet fryses som forfatteren: den som festet kan være borte når
    #: noen lurer på hvorfor linja står øverst. Løsning tømmer alle tre.
    festet_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name='Festet')
    festet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_festede_logglinjer',
        verbose_name='Festet av')
    festet_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Festet av (navn)')

    class Meta:
        verbose_name = 'Logglinje'
        verbose_name_plural = 'Logglinjer'
        # Standardrekkefølgen er registreringsrekkefølgen. `gjeldende()` gjør
        # den om til fortellingens rekkefølge; her er den bare stabil.
        ordering = ['id']
        indexes = [
            # Pollingen (`?siden=<id>`) er den spørringen som går hvert 15.
            # sekund gjennom hele vakta, fra hver operatør.
            models.Index(fields=['vakt', 'id'], name='ko_logg_vakt_id_idx'),
        ]

    def __str__(self):
        if self.systemkode:
            return f'[{self.systemkode}] {self.tidspunkt:%H:%M}'
        return f'{self.forfatter_navn}: {self.tekst[:40]}'

    @property
    def er_fjernet(self) -> bool:
        return self.fjernet_at is not None

    @property
    def er_systemlinje(self) -> bool:
        return self.kilde == KILDE_SYSTEM

    @property
    def er_festet(self) -> bool:
        return self.festet_at is not None

    @property
    def er_delt(self) -> bool:
        return self.delt_at is not None


class Linjedeling(models.Model):
    """Én linje delt med **ett** oppdrag (André, 19. sep. 2026: «individuelle
    settes inne i oppdraget»). Motstykket til `Logglinje.delt_at`, som deler
    med alle oppdrag fra hendelsen.

    **Peker på oppdraget, og er derfor ikke med i backupen** (`ko/backup.py`):
    oppdragene slettes ved arkivering og gjenopprettes etter KO, så raden
    ville pekt på ingenting i en tom base. Slettes med oppdraget (CASCADE) —
    linja står. Det er den ene pekeren fra loggen til et oppdrag, og den er
    lov fordi den bærer en *tilstand nå*, ikke historikk: «denne bilen ser
    denne linja». Historikken om hva som ble sagt står i linja.
    """

    linje = models.ForeignKey(
        Logglinje, on_delete=models.CASCADE, related_name='delinger',
        verbose_name='Linje')
    oppdrag = models.ForeignKey(
        'oppdrag.Oppdrag', on_delete=models.CASCADE, related_name='ko_delinger',
        verbose_name='Oppdrag')
    delt_at = models.DateTimeField(default=timezone.now, verbose_name='Delt')
    delt_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_linjedelinger',
        verbose_name='Delt av')
    delt_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Delt av (navn)')

    class Meta:
        verbose_name = 'Linjedeling'
        verbose_name_plural = 'Linjedelinger'
        constraints = [
            models.UniqueConstraint(fields=['linje', 'oppdrag'], name='en_deling_per_oppdrag'),
        ]

    def __str__(self):
        return f'linje {self.linje_id} → oppdrag {self.oppdrag_id}'


#: Hendelsens to tilstander. **Ingen statusmaskin** (§3.3): hendelser har ikke
#: et forløp, oppdrag har. Åpen eller lukket, og lukket kan åpnes igjen — en
#: lukking er som regel en misforståelse eller et feilklikk når den må angres
#: (André, 18. sep. 2026), og gjenåpningen logges som egen systemlinje.
HENDELSE_APEN = 'apen'
HENDELSE_LUKKET = 'lukket'
HENDELSE_STATUS_VALG: tuple[tuple[str, str], ...] = (
    (HENDELSE_APEN, 'Åpen'),
    (HENDELSE_LUKKET, 'Lukket'),
)


#: Prioritetene (André, 18. sep. 2026: «Grønn, Gul, Rød, Drift, Viktig med
#: rød trekant utropstegn»). **Samme ordforråd som bilens grovsortering og
#: oppdragets hastegrad**, med vilje: Grønn/Gul/Rød er det folk sier på
#: samband, Drift er det oppdragsmodulen alt kaller det ikke-medisinske, og
#: Viktig er flagget over dem alle. Rekkefølgen her er rangen — først i lista
#: er øverst på tavla — og `PRIORITET_RANG` utledes av den, så de to aldri kan
#: være uenige.
PRIORITET_VIKTIG = 'viktig'
PRIORITET_ROD = 'rod'
PRIORITET_GUL = 'gul'
PRIORITET_GRONN = 'gronn'
PRIORITET_DRIFT = 'drift'
#: «Plassering» (André, 19. sep. 2026): et lag eller en bil som skal stå et
#: sted. Sist, etter Drift — og finnes som hastegrad i oppdragsmodulen med
#: samme navn, så «Nytt oppdrag» arver den likt.
PRIORITET_PLASSERING = 'plassering'
PRIORITET_VALG: tuple[tuple[str, str], ...] = (
    (PRIORITET_VIKTIG, 'Viktig'),
    (PRIORITET_ROD, 'Rød'),
    (PRIORITET_GUL, 'Gul'),
    (PRIORITET_GRONN, 'Grønn'),
    (PRIORITET_DRIFT, 'Drift'),
    (PRIORITET_PLASSERING, 'Plassering'),
)
PRIORITET_NAVN: dict[str, str] = dict(PRIORITET_VALG)
PRIORITET_RANG: dict[str, int] = {v: i for i, (v, _) in enumerate(PRIORITET_VALG)}
PRIORITET_STANDARD = PRIORITET_GRONN

#: Hvem som meldte hendelsen (André, 19. sep. 2026: avkryssing, flere kan
#: velges, «Andre» med tekst). **Fast liste i kode, ikke en valgliste:** de
#: fem første er nødetatene og egen organisasjon, og de endrer seg ikke fra
#: arrangement til arrangement. «Andre» bærer fritekst — arrangørvakt,
#: publikum — og teksten kreves når den er valgt. Ingen peker: melderen er
#: oftest ikke en konto.
MELDER_EGEN = 'egen'
MELDER_ANDRE = 'andre'
MELDER_VALG: tuple[tuple[str, str], ...] = (
    (MELDER_EGEN, 'Egen ressurs'),
    ('amk', 'AMK'),
    ('brann', 'Brann'),
    ('politi', 'Politi'),
    ('lsko', 'LSKO'),
    (MELDER_ANDRE, 'Andre'),
)
MELDER_NAVN: dict[str, str] = dict(MELDER_VALG)


class Hendelse(models.Model):
    """Én hendelse — det man kaller den på samband (§3.3).

    **Egen modell i `ko`, ikke `Oppdrag.forelder`** (§9.3): hendelsen finnes
    *før* oppdraget, kan leve i tjue minutter før en ressurs sendes, og kan
    avsluttes uten at noen rykket ut. `Oppdrag.hendelse` peker hit — fra
    oppdrag til hendelse, aldri motsatt, så `oppdrag` ikke trenger å kjenne
    `ko` (strengreferanse, ingen import; `ko/tests_avhengighet.py`).

    **Nummeret identifiserer, FK-en relaterer** (§6). `H12` tildeles ved
    opprettelse og endres aldri; hvilke oppdrag som hører til er en peker på
    oppdraget og kan flyttes. Serien er per vakt og uavhengig av
    oppdragsserien, så `H12` og `O12` er to ulike ting på nabolinjer.

    **Hodet er det ene delte redigerbare i KO** (§7.1): tittel, lokasjon og
    status. `versjon` og 409 ved uenighet, ellers spiser siste skriver den
    andres tekst i stillhet. Alt annet i modulen er påføringer.

    **Lokasjonen fryses som navn ved siden av FK-en**, som logglinja fryser
    forfatteren: backupen stripper pekeren (den går *ut* av modulen, og
    gjenopprettingen leser KO før oppdrag), og et arrangement der lokasjonen
    er omdøpt i etterkant skal fortsatt vise hva som sto der da.
    """

    vakt = models.ForeignKey(
        'core.Vakt', on_delete=models.PROTECT,
        related_name='ko_hendelser', verbose_name='Vakt')
    hendelsesnummer = models.IntegerField(verbose_name='Hendelsesnummer')
    tittel = models.CharField(max_length=120, verbose_name='Tittel')
    lokasjon = models.ForeignKey(
        'oppdrag.Lokasjon', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_hendelser', verbose_name='Lokasjon')
    lokasjon_navn = models.CharField(
        max_length=255, blank=True, default='', verbose_name='Lokasjon (navn)')
    status = models.CharField(
        max_length=8, choices=HENDELSE_STATUS_VALG, default=HENDELSE_APEN,
        db_index=True, verbose_name='Status')
    versjon = models.PositiveIntegerField(default=1, verbose_name='Versjon')

    #: Prioriteten (18. sep. 2026). Endres med en egen systemlinje, ikke
    #: stille: «H14 satt til Viktig av Kari» er nøyaktig det man leter etter
    #: når man i etterkant spør hvorfor to biler ble sendt.
    prioritet = models.CharField(
        max_length=12, choices=PRIORITET_VALG, default=PRIORITET_STANDARD,
        db_index=True, verbose_name='Prioritet')
    #: **Beskrivelsen er ikke et felt** (19. sep. 2026). Den var en
    #: `TextField` fra 18. sep., og er nå den første linja i hendelsens logg
    #: — fordi André ville se *hva som er nytt* og hvem som skrev det. Et
    #: felt som overskrives kan ikke svare på det. Enhetene ser bare det som
    #: er *delt*: `delte_linjer_for()` under er den ene leseren, og
    #: oppdragsmodulen kaller den gjennom `Oppdrag.hendelse` uten å kjenne
    #: linjemodellen. Teksten er fritekst som før: aldri verdilogget i audit,
    #: aldri i en SHA-signatur (`NOTAT_DPIA_OG_FRITEKST.md` §7).
    #:
    #: Hvem som meldte: kodene fra `MELDER_VALG`, flere er lov, og `melder` er
    #: teksten bak «Andre» — tom når «Andre» ikke er valgt.
    melder_typer = models.JSONField(default=list, blank=True, verbose_name='Melder')
    melder = models.CharField(max_length=120, blank=True, default='', verbose_name='Melder (andre)')

    opprettet_at = models.DateTimeField(auto_now_add=True, verbose_name='Opprettet')
    opprettet_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_hendelser_opprettet',
        verbose_name='Opprettet av')
    opprettet_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Opprettet av (navn)')
    #: Linja hendelsen ble laget av (§4.5). **Linja blir stående** i loggen;
    #: hendelsen peker tilbake. Flyttes linja inn i hendelsen, får loggen et
    #: hull akkurat der det viktige skjedde.
    opprettet_fra_linje = models.ForeignKey(
        Logglinje, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='hendelser_opprettet_fra', verbose_name='Opprettet fra linje')

    lukket_at = models.DateTimeField(null=True, blank=True, verbose_name='Lukket')
    lukket_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_hendelser_lukket',
        verbose_name='Lukket av')
    lukket_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Lukket av (navn)')

    class Meta:
        verbose_name = 'Hendelse'
        verbose_name_plural = 'Hendelser'
        ordering = ['-hendelsesnummer']
        constraints = [
            models.UniqueConstraint(
                fields=['vakt', 'hendelsesnummer'],
                name='unikt_hendelsesnummer_per_vakt',
            ),
        ]

    def __str__(self):
        return f'H{self.hendelsesnummer} {self.tittel}'

    @property
    def er_lukket(self) -> bool:
        return self.status == HENDELSE_LUKKET

    def delte_linjer_for(self, oppdrag) -> list[dict]:
        """Linjene i hendelsen som er delt med `oppdrag`, i rekkefølge:
        `[{id, rot, tekst, av, tid, delt_at}]`. Delt med alle
        (`Logglinje.delt_at`) eller med dette ene (`Linjedeling`). Gjeldende
        ledd i hver kjede, fjernede og systemlinjer utelatt.

        **Den ene leseren**: oppdragsmodulen kaller den gjennom
        `Oppdrag.hendelse` for detaljvinduet og bilen, og kjenner verken
        `Logglinje` eller delingen. `delt_at` er linjas når den er delt med
        alle, ellers delingens — det er tidspunktet bilen regner «ny tekst»
        fra.
        """
        egne = {d.linje_id: d.delt_at
                for d in Linjedeling.objects.filter(oppdrag=oppdrag, linje__hendelse=self)}
        rader = (self.linjer
                 .filter(kilde=KILDE_OPERATOR, fjernet_at__isnull=True,
                         korrigert_av__isnull=True)
                 .filter(Q(delt_at__isnull=False) | Q(pk__in=list(egne)))
                 .order_by(Coalesce('rot_id', 'id'), 'id'))
        return [{'id': l.pk, 'rot': l.rot_id or l.pk, 'tekst': l.tekst,
                 'av': l.forfatter_navn, 'tid': l.tidspunkt.isoformat(),
                 'delt_at': (l.delt_at or egne.get(l.pk)).isoformat()}
                for l in rader]

    def lag_navn(self) -> list[str]:
        """Navnene på lagene som er på hendelsen, i den rekkefølgen de kom.
        Frosset navn (`ressurs_navn`), ikke ressursens: det er det som står
        etter en gjenoppretting, og det er det som sto da det skjedde."""
        return [l.ressurs_navn for l in self.lag.all()]


class HendelseLag(models.Model):
    """Et lag som er **på** hendelsen (André, 19. sep. 2026).

    «Lag får ikke oppdrag, de får oppdrag muntlig kommunisert på samband og
    blir registrert på hendelsen.» Derfor er dette en rad på hendelsen og
    ikke en `oppdrag.Enhet`: laget stempler aldri, og det som skal vises er
    *at* det er opptatt, *på hva*, og *hvor lenge* — «På H14 · 23 min» på
    kortet i ressursoversikten. Erstatter fritekstfeltet `lagsressurser` og
    listen `Ressursbehov` fra 18. sep., som begge var ord uten en peker.

    **Pekeren går til vaktlistas ressurs**, ikke til et eget lagregister:
    modulen eier ingen ressurser (§3.1, §9.1). Bare ressurser **uten**
    oppdragsenhet kan stå her — bilene har oppdragene.

    **`ressurs` strippes i backupen, og navnet fryses ved siden av.** Kanten
    `ko` → `vaktliste` ville ellers gitt en sirkel i gjenopprettingen
    (`vaktliste.Ressurs.enhet` → `oppdrag`, `oppdrag.Oppdrag.hendelse` → `ko`),
    nøyaktig som `Hendelse.lokasjon`. Etter en gjenoppretting står navnet;
    koblingen til kortet er borte, og det er prisen.

    Registrering og fjerning skriver hver sin systemlinje (`HENDELSE_LAG_PAA`,
    `HENDELSE_LAG_AV`) — hvem som ble sendt hvor er nøyaktig det man leser
    loggen for. Raden slettes når laget tas av; historien står i loggen.
    """

    hendelse = models.ForeignKey(
        Hendelse, on_delete=models.CASCADE, related_name='lag',
        verbose_name='Hendelse')
    ressurs = models.ForeignKey(
        'vaktliste.Ressurs', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_hendelser', verbose_name='Ressurs')
    ressurs_navn = models.CharField(max_length=120, verbose_name='Ressurs (navn)')
    fra = models.DateTimeField(verbose_name='På hendelsen fra')
    av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_lag_registrert',
        verbose_name='Registrert av')
    av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Registrert av (navn)')

    class Meta:
        verbose_name = 'Lag på hendelse'
        verbose_name_plural = 'Lag på hendelser'
        ordering = ['fra', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['hendelse', 'ressurs'],
                name='et_lag_en_gang_per_hendelse',
            ),
        ]

    def __str__(self):
        return f'{self.ressurs_navn} på H{self.hendelse.hendelsesnummer}'


class HendelseDeltaker(models.Model):
    """Hvem som er *på* hendelsen (André, 18. sep. 2026: «hvis en bruker
    registrerer noe i hendelsen så er de automatisk med»).

    **Vises, styrer ingenting** — samme regel som ansvarsmerket (§5.1). Lista
    svarer på «hvem jobber med H14 nå», så to operatører ikke sender hver sin
    bil på samme melding. Raden skrives av `services.bli_med`, som kalles fra
    hver skriving på hendelsen og fra «Bli med»-knappen; å lese hendelsen
    melder ingen inn. Navnet fryses som på linja (§4.5).
    """

    hendelse = models.ForeignKey(
        Hendelse, on_delete=models.CASCADE, related_name='deltakere',
        verbose_name='Hendelse')
    bruker = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_hendelser_deltatt',
        verbose_name='Bruker')
    brukernavn = models.CharField(max_length=150, verbose_name='Brukernavn')
    fra = models.DateTimeField(auto_now_add=True, verbose_name='Med fra')

    class Meta:
        verbose_name = 'Hendelsesdeltaker'
        verbose_name_plural = 'Hendelsesdeltakere'
        ordering = ['fra', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['hendelse', 'brukernavn'],
                name='en_deltaker_per_hendelse',
            ),
        ]

    def __str__(self):
        return f'{self.brukernavn} på H{self.hendelse.hendelsesnummer}'


class Ansvarsomraade(models.Model):
    """Ansvarsområdene operatørene kan velge mellom — «samband», «ressurser»…

    Var en fast tuppel i kode (`ANSVARSOMRAADER`) til 18. sep. 2026, da André
    ville redigere dem under KO-innstillinger. Samme form som `oppdrag.Lokasjon`:
    navn, aktiv, rekkefølge. Merket på linjene (`Logglinje.ansvarsomraade`) og
    på kontoen (`Ansvarsmerke.omraade`) er fortsatt **tekst**, ikke en peker:
    et område som omdøpes eller deaktiveres skal ikke skrive om loggen.
    """

    navn = models.CharField(max_length=40, unique=True, verbose_name='Ansvarsområde')
    er_aktiv = models.BooleanField(default=True, verbose_name='Aktiv')
    rekkefolge = models.IntegerField(default=100, verbose_name='Rekkefølge')

    class Meta:
        verbose_name = 'Ansvarsområde'
        verbose_name_plural = 'Ansvarsområder'
        ordering = ['rekkefolge', 'navn']

    def __str__(self):
        return self.navn


class Ansvarsmerke(models.Model):
    """Hva operatøren gjør nå — samband, ressurser, logg, media (§5.1).

    **Vises, styrer ingenting** (André, 18. sep. 2026: «bare et merke som gjør
    at folk vet hvem som har ansvar for hva. Ingen annen praktisk formål»).
    Står ved navnet i «Hvem har KO oppe» og stemples på linjene hun skriver.
    Aldri en gate: «bare sambandsoperatøren kan føre sambandslinjer» dobler
    matrisen, og første gang den rette er opptatt møter du en vegg der vegger
    er dyre.

    **Én rad per konto, ikke per sesjon.** Samme person med KO på PC-en og på
    telefonen har ett ansvar. Og i KO og ikke i sesjonen fordi `core/sesjoner.py`
    ikke skal kjenne en KO-nøkkel — rammeverket kjenner ingen modul ved navn.

    Ikke med i backupen: merket er hva som gjelder *nå*, og etter en
    gjenoppretting er «nå» et annet.
    """

    bruker = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='ko_ansvar', verbose_name='Bruker')
    omraade = models.CharField(max_length=40, blank=True, default='',
                               verbose_name='Ansvarsområde')
    satt_at = models.DateTimeField(auto_now=True, verbose_name='Satt')

    class Meta:
        verbose_name = 'Ansvarsmerke'
        verbose_name_plural = 'Ansvarsmerker'

    def __str__(self):
        return f'{self.bruker_id}: {self.omraade or "—"}'


class Tavleplassering(models.Model):
    """Hvor et lag står på tavla, og fra når (André, 22. sep. 2026).

    Tavla på veggen i KO digitalt: lokasjonene som rader, tida som kolonner,
    og en rad per gang en ressurs ble satt et sted. **Den åpne raden**
    (`til` tom) er der ressursen står nå; de lukkede er historikken som
    «Besøk» teller («Lag 1 var 3 ganger fredag, 0 lørdag»).

    **Pekeren går til vaktlistas ressurs og oppdragsmodulens lokasjon** —
    KO eier ingen ressurser og ingen lokasjoner (§3.1). Begge strippes i
    backupen og navnene fryses ved siden av, som `HendelseLag`: kanten ut av
    modulen ville ellers gitt en sirkel i gjenopprettingen.

    **Bare ledige plasseres** (André): den som er på en hendelse eller et
    oppdrag står på tavla som det, og det har forrang. Når laget går på en
    hendelse, lukkes plasseringen (`ko.tavle.avslutt_for_hendelse`); når det
    går av igjen, står tiden på hendelsen som en lukket rad med
    `hendelse_nummer` — historikk, ikke noe noen satte — og laget står
    **uten plass**.

    `pause` er Pause-raden, som ikke er en lokasjon: da sto «Pause» som sted i
    «Nytt oppdrag».
    """

    vakt = models.ForeignKey(
        'core.Vakt', on_delete=models.PROTECT,
        related_name='ko_tavleplasseringer', verbose_name='Vakt')
    ressurs = models.ForeignKey(
        'vaktliste.Ressurs', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_tavleplasseringer', verbose_name='Ressurs')
    ressurs_navn = models.CharField(max_length=120, verbose_name='Ressurs (navn)')
    lokasjon = models.ForeignKey(
        'oppdrag.Lokasjon', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_tavleplasseringer', verbose_name='Lokasjon')
    lokasjon_navn = models.CharField(
        max_length=255, blank=True, default='', verbose_name='Lokasjon (navn)')
    pause = models.BooleanField(default=False, verbose_name='Pause')
    #: Satt når raden er tiden laget sto på en hendelse — historikk skrevet
    #: av KO selv, ikke en plassering noen gjorde.
    hendelse_nummer = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Hendelse')
    fra = models.DateTimeField(verbose_name='Fra')
    til = models.DateTimeField(null=True, blank=True, verbose_name='Til')
    #: Hvor lenge laget skal stå der (André, 23. sep. 2026: «planlegge tid per
    #: plassering med beskjed/tegn på overtid»). **Flytter ingen**: når tida er
    #: ute, står laget der med rød kant til KO flytter det. Står igjen når
    #: plasseringen lukkes — «planlagt til 23:45, gikk 00:10» er historikk.
    planlagt_til = models.DateTimeField(null=True, blank=True, verbose_name='Planlagt til')
    #: «Følger konserten» (steg 2): slutten er konsertens, og flyttes konserten,
    #: følger den med. Satt i stedet for `planlagt_til`, aldri sammen med den.
    folger = models.ForeignKey(
        'Programpost', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='plasseringer', verbose_name='Følger konserten')
    av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_tavleplasseringer',
        verbose_name='Satt av')
    av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Satt av (navn)')

    class Meta:
        verbose_name = 'Tavleplassering'
        verbose_name_plural = 'Tavleplasseringer'
        ordering = ['fra', 'id']
        constraints = [
            # Én åpen plassering per ressurs — ett sted om gangen. I basen og
            # ikke bare i tjenesten: to operatører som drar samme lag samtidig
            # skal få en feil, ikke et lag på to steder.
            models.UniqueConstraint(
                fields=['ressurs'], condition=Q(til__isnull=True),
                name='en_aapen_tavleplassering_per_ressurs'),
        ]

    def __str__(self):
        sted = 'Pause' if self.pause else self.lokasjon_navn
        return f'{self.ressurs_navn} · {sted}'


class PlanlagtPause(models.Model):
    """En pause KO har planlagt for et lag (André, 22. sep. 2026).

    «La oss kunne sette en pause rad og legge inn pauser der for lagene. Som
    skal overstyres av /vaktliste men kunne endres på i drift og hvis lag
    ikke har fått planlagt pause i /vaktliste.» **Vaktlista har ingen pauser
    ennå** (TODO): i dag er alle planlagte pauser KOs egne. Den dagen
    vaktlista får dem, blir de utgangspunktet, og en KO-endring i drift vinner
    — det trenger et felt for kilden, og det legges til da, ikke nå.

    **Planen flytter ingen.** Når tiden er inne, får laget «Pause nå», og KO
    starter den; da blir det en vanlig plassering i Pause-raden, og `startet`
    peker på den. Tavla flytter ingen av seg selv — et lag midt i noe skal
    ikke forsvinne fra raden sin fordi klokka sa det.
    """

    vakt = models.ForeignKey(
        'core.Vakt', on_delete=models.PROTECT,
        related_name='ko_planlagte_pauser', verbose_name='Vakt')
    ressurs = models.ForeignKey(
        'vaktliste.Ressurs', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_planlagte_pauser', verbose_name='Ressurs')
    ressurs_navn = models.CharField(max_length=120, verbose_name='Ressurs (navn)')
    fra = models.DateTimeField(verbose_name='Fra')
    til = models.DateTimeField(verbose_name='Til')
    startet = models.ForeignKey(
        Tavleplassering, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='planlagt_pause', verbose_name='Startet som')
    av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_planlagte_pauser',
        verbose_name='Planlagt av')
    av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Planlagt av (navn)')

    class Meta:
        verbose_name = 'Planlagt pause'
        verbose_name_plural = 'Planlagte pauser'
        ordering = ['fra', 'id']

    def __str__(self):
        return f'{self.ressurs_navn} · pause'


# ── Programmet (tavleplanleggeren, steg 2 — 23. sep. 2026) ───────────────────
#
# Konsertene per sted, med beredskapsnivå og behov. Skissene og svarene står i
# Artifact «Tavleplanleggeren»; reglene i `ko/program.py`.

#: Beredskapsnivå — standardisert (André, 23. sep. 2026: «grønn, gul, oransje
#: og rød som beredskapsnivå på konsertene som er en standardisert form»). Tomt
#: er «ikke satt», for et fast behov som ikke er en konsert.
BEREDSKAP_VALG: tuple[tuple[str, str], ...] = (
    ('gronn', 'Grønn'),
    ('gul', 'Gul'),
    ('oransje', 'Oransje'),
    ('rod', 'Rød'),
)
BEREDSKAP_NAVN: dict[str, str] = dict(BEREDSKAP_VALG)


class Konserttype(models.Model):
    """Hva slags konsert — «Headliner», «Hiphop / rap». **Beskriver, setter
    ingenting** (André: «Konserttyper skal ikke automatisk sette ressurser»).
    Den finnes for å sammenligne samme slags konsert år for år. Lista er
    KO-lederens, som ansvarsområdene; ikke per vakt."""

    navn = models.CharField(max_length=60, unique=True, verbose_name='Konserttype')
    er_aktiv = models.BooleanField(default=True, verbose_name='Aktiv')
    rekkefolge = models.IntegerField(default=100, verbose_name='Rekkefølge')

    class Meta:
        verbose_name = 'Konserttype'
        verbose_name_plural = 'Konserttyper'
        ordering = ['rekkefolge', 'navn']

    def __str__(self):
        return self.navn


class Kjennetegn(models.Model):
    """Avkrysninger på en konsert — «Pyro» først. **En liste KO-leder setter
    opp, ikke faste felt i koden**: svaret fra samarbeidspartneren om hva en
    konsert skal bære, kan da legges inn den dagen det kommer."""

    navn = models.CharField(max_length=60, unique=True, verbose_name='Kjennetegn')
    er_aktiv = models.BooleanField(default=True, verbose_name='Aktiv')
    rekkefolge = models.IntegerField(default=100, verbose_name='Rekkefølge')

    class Meta:
        verbose_name = 'Kjennetegn'
        verbose_name_plural = 'Kjennetegn'
        ordering = ['rekkefolge', 'navn']

    def __str__(self):
        return self.navn


class Programpost(models.Model):
    """En konsert — eller et fast behov som ikke er en konsert — på ett sted i
    ett tidsrom. **Behovet skrives inn for hånd** (`Programbehov`), per
    ressursgruppe i vaktlista.

    Pekerne ut av modulen — lokasjonen og typen — har navnet frosset ved
    siden av, som `Tavleplassering`: programmet skal kunne leses år etter år,
    også når stedet er omdøpt eller typen slettet. **Ingen fritekst om
    personer**: da kan programmet stå fra år til år.
    """

    vakt = models.ForeignKey(
        'core.Vakt', on_delete=models.PROTECT, related_name='ko_program', verbose_name='Vakt')
    lokasjon = models.ForeignKey(
        'oppdrag.Lokasjon', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_program', verbose_name='Sted')
    lokasjon_navn = models.CharField(max_length=255, verbose_name='Sted (navn)')
    navn = models.CharField(max_length=120, verbose_name='Navn')
    konserttype = models.ForeignKey(
        Konserttype, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='poster', verbose_name='Konserttype')
    konserttype_navn = models.CharField(
        max_length=60, blank=True, default='', verbose_name='Konserttype (navn)')
    beredskap = models.CharField(
        max_length=10, blank=True, default='', choices=BEREDSKAP_VALG, verbose_name='Beredskapsnivå')
    fra = models.DateTimeField(verbose_name='Fra')
    til = models.DateTimeField(verbose_name='Til')
    publikum = models.PositiveIntegerField(null=True, blank=True, verbose_name='Forventet publikum')
    kjennetegn = models.ManyToManyField(Kjennetegn, blank=True, related_name='poster',
                                        verbose_name='Kjennetegn')
    endret_at = models.DateTimeField(auto_now=True, verbose_name='Sist endret')
    endret_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_programposter', verbose_name='Sist endret av')
    endret_av_navn = models.CharField(max_length=150, blank=True, default='',
                                      verbose_name='Sist endret av (navn)')

    class Meta:
        verbose_name = 'Programpost'
        verbose_name_plural = 'Programposter'
        ordering = ['fra', 'lokasjon_navn', 'id']

    def __str__(self):
        return f'{self.navn} · {self.lokasjon_navn}'


class Programbehov(models.Model):
    """Hvor mange av én ressursgruppe konserten trenger — «4 lag», «2
    ambulanser». Gruppa er vaktlistas (`Ressursgruppe`); «Spesiallag» er en
    egen gruppe der (André: «en fast type lag»). Navnet står frosset."""

    post = models.ForeignKey(Programpost, on_delete=models.CASCADE, related_name='behov',
                             verbose_name='Programpost')
    gruppe = models.ForeignKey(
        'vaktliste.Ressursgruppe', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='ko_behov', verbose_name='Ressursgruppe')
    gruppe_navn = models.CharField(max_length=60, verbose_name='Ressursgruppe (navn)')
    antall = models.PositiveSmallIntegerField(verbose_name='Antall')

    class Meta:
        verbose_name = 'Behov'
        verbose_name_plural = 'Behov'
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['post', 'gruppe'], name='ett_behov_per_gruppe'),
        ]

    def __str__(self):
        return f'{self.antall} {self.gruppe_navn}'
