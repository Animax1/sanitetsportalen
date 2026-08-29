"""``AbstractArkiv`` — feltene et modularkiv trenger, én gang.

``VaktArkiv`` i pasientmodulen var det første arkivet, og de fem feltene som
gjorde det til et *arkiv* — frosset navn på den som arkiverte, signatur,
kollapstidspunkt, aggregat og aggregatsignatur — måtte ellers skrives på nytt
i hver modul som arkiverer. Basemodellen er derfor skrevet nå, med
oppdragsmodulen som modell nummer to: da ser man hva som faktisk er felles i
stedet for å gjette (TODO-punktet under «Generaliser arkivmønsteret»).

**``VaktArkiv`` migreres bevisst ikke hit.** Feltene ville vært de samme, men
en `AlterField`-runde på en tabell i produksjon er ikke gratis, og verre:
`year_snapshot` og `arrangement_navn` inngår i SHA-payloaden til hvert
eksisterende arkiv. Basemodellen bærer `vakt_navn`, ikke `arrangement_navn` —
navnet kommer fra vakta nå — og et arkiv som byttet feltnavn ville meldt
tukling. Duplikatet mellom de to modellene er prisen for at signaturene i prod
fortsatt verifiserer.

Arbeidsdelingen ellers er som før: ``core.arkiv`` eier kanonisering, hashing
og orkestrering av kollaps, handleren eier payloadens form.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class AbstractArkiv(models.Model):
    """Basemodell for en modulens vaktarkiv. Abstrakt — ingen egen tabell.

    Modulen legger til det som er dens eget (antall-felt med modulens navn,
    ekstra snapshot-kolonner) og lager sin egen radmodell med FK hit.
    """

    tittel = models.CharField(max_length=255, verbose_name='Tittel')

    # SET_NULL, ikke PROTECT: arkivet skal overleve at vaktraden slettes. Alt
    # det trenger for å beskrive seg selv er frosset på det selv — se
    # `vakt_navn` rett under. Nullbar for godt, av samme grunn som i
    # `VaktArkiv`: arkiver kan være eldre enn grupperingen.
    vakt = models.ForeignKey(
        'core.Vakt',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_arkiver',
        verbose_name='Vakt',
    )
    vakt_navn = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Vaktnavn (frosset)',
        help_text=(
            'Navnet vakta hadde da arkivet ble laget. Frosset her fordi vakta '
            'kan bli omdøpt eller slettet, mens arkivet skal beskrive seg selv.'
        ),
    )

    antall_rader = models.IntegerField(
        default=0,
        verbose_name='Antall rader',
        help_text='Antall arkiverte rader da arkivet ble laget.',
    )
    notat = models.TextField(blank=True, default='', verbose_name='Notat')

    importert_at = models.DateTimeField(
        auto_now_add=True, db_index=True, verbose_name='Arkivert')
    # SET_NULL, ikke PROTECT: med PROTECT kunne en bruker som hadde arkivert
    # aldri slettes, og sletterett etter GDPR art. 17 var blokkert på
    # databasenivå. Navnet fryses i stedet i `importert_av_navn`.
    importert_av = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_arkiver',
        verbose_name='Arkivert av',
    )
    importert_av_navn = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name='Arkivert av (navn)',
        help_text=(
            'Frosset brukernavn. Settes ved arkivering og overlever sletting '
            'av brukerkontoen.'
        ),
    )

    sha256 = models.CharField(max_length=64, blank=True, verbose_name='SHA-256')

    # ── Kollaps til aggregat ──────────────────────────────────────────────
    # Etter N måneder slettes radnivået permanent og erstattes av ferdig
    # beregnede tall. Art. 5(1)(e) tillater ikke at opplysninger på radnivå
    # ligger igjen på ubestemt tid når formålet er uttømt.
    kollapset_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Kollapset',
        help_text=(
            'Tidspunkt da radene ble slettet og erstattet av frosset '
            'aggregat. Tomt betyr at radnivået fortsatt finnes.'
        ),
    )
    aggregat = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Frosset statistikk',
        help_text='Ferdig beregnede tall lagret ved kollaps.',
    )
    aggregat_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='SHA-256 (aggregat)',
        help_text=(
            'Sjekksum over det frosne aggregatet. Overtar integritetssjekken '
            'etter kollaps, siden «sha256» er beregnet over rader som ikke '
            'lenger finnes.'
        ),
    )

    class Meta:
        abstract = True
        ordering = ['-importert_at']

    def __str__(self) -> str:
        return self.tittel

    @property
    def er_kollapset(self) -> bool:
        """True hvis radene er slettet og kun aggregatet finnes."""
        return self.kollapset_at is not None

    @property
    def importert_av_visning(self) -> str:
        """Navnet som skal vises for den som arkiverte.

        Bruker det frosne navnet, faller tilbake på FK-en for rader uten
        snapshot, og til slutt på en nøytral tekst når kontoen er slettet og
        navnet aldri ble satt.
        """
        if self.importert_av_navn:
            return self.importert_av_navn
        if self.importert_av_id and self.importert_av:
            return self.importert_av.username
        return 'ukjent bruker'
