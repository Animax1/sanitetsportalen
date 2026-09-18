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
from django.db.models.functions import Coalesce


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
