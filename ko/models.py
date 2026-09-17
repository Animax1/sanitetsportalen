"""KO-loggen (pulje 2) — én tabell med alle linjer.

Se `ko/CLAUDE.md` og `docs/FORSLAG_KO.md` §4. Modulen eier fortsatt ingen
ressurser; det som kommer hit er *det som ble sagt og det som skjedde*, ikke et
register over hvem som finnes. `Hendelse` kommer i pulje 3, og logglinja har
derfor ennå ingen FK til en hendelse — den legges til der, sammen med regelen
om at en linje kan knyttes til en hendelse i etterkant.

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

from . import choices as ko_choices


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
                    .select_related('forfatter', 'fjernet_av')
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


class Ressursstatus(models.Model):
    """KO-ført status på én ressurs — **én rad per ressurs, ikke en historikk**.

    Tredje rad i projeksjonen (§3.1): de som ikke stempler selv. En bil har en
    `oppdrag.Enhet` og melder sin egen status; et lag har ingen `Enhet` i det
    hele tatt — det er hele poenget med at de ikke logger inn — og da er det
    operatøren som fører den.

    **Hvem som fører utledes av `Ressurs.enhet`, ikke av et flagg.** Er den
    satt, eier oppdragsmodulen statusen og denne raden skal ikke finnes; er den
    `NULL`, er det KO. Et eget flagg ville vært en andre sannhet om det samme,
    og de to ville stått i strid den dagen noen koblet en enhet uten å rydde
    flagget. Rutingflagget i §3.2 er **et annet spørsmål** — det avgjør
    `/oppdrag/` mot `/park/`, som ikke finnes ennå — og hører hjemme der.

    **Historikken ligger i loggen, ikke her.** Hver føring skriver en
    systemlinje (`ko/systemlinjer.py`, koden `ressurs_status`), og det er den
    som svarer på «hvor lenge sto lag 3 ute av drift». To kilder til samme
    historikk går i utakt første gang noe feiler halvveis, og da er det den
    lagrede som lyver — den ser autoritativ ut. Derfor er denne tabellen ren
    nåtilstand, oppdatert i stedet for påført.

    **Fravær av rad er «Ledig»**, og det er ikke en verdi noen setter: det er
    hva «KO har ikke ført noe» ser ut som. Samme konstruksjon som
    `oppdrag.services.enhet_status`, og av samme grunn — en lagret standard
    måtte settes for hver ressurs i hver vaktliste, og da er spørsmålet «hvem
    glemte å sette den» i stedet for «hvem er ledig».
    """

    #: `CASCADE` og ikke `SET_NULL`: ressursen henger på én vaktliste (§3.1),
    #: og en status uten ressursen sin er ikke et spor — den er en foreldreløs
    #: rad ingen kan lese. Sporet ligger i loggen, som overlever.
    ressurs = models.OneToOneField(
        'vaktliste.Ressurs', on_delete=models.CASCADE,
        related_name='ko_status', verbose_name='Ressurs')

    status = models.CharField(
        max_length=16, choices=ko_choices.STATUS_VALG,
        default=ko_choices.STANDARD, verbose_name='Status')

    satt_at = models.DateTimeField(verbose_name='Satt')

    #: Kontoen kan forsvinne, og navnet skal ikke gjøre det — samme regel som
    #: `forfatter_navn` på logglinja (§4.5). Navnet er fasit, FK-en er
    #: bekvemmelighet, og backup-handleren stripper derfor FK-en og ikke navnet.
    satt_av = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='ko_ressursstatuser',
        verbose_name='Satt av')
    satt_av_navn = models.CharField(
        max_length=150, blank=True, default='', verbose_name='Satt av (navn)')

    class Meta:
        verbose_name = 'KO-ført ressursstatus'
        verbose_name_plural = 'KO-førte ressursstatuser'
        ordering = ['ressurs_id']

    def __str__(self):
        return f'{self.ressurs_id}: {self.status}'
