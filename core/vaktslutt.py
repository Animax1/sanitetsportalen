"""«Avslutt vakt» — ett trykk som arkiverer og tømmer alle modulene (28. sep. 2026).

Steg 2 av planen i `TODO.md`. André: «etter hver vakt [...] arkiveres modulene
samtlige som admin trykker. Da er det ikke bare å arkivere hver eneste modul men
alt blir gjort i ett.»

**Hvordan det var:** fire forskjellige ting. Pasientenes «Avslutt vakt»
slettet pasientene etter bare en backup, *uten* å arkivere — arkivet var en
egen knapp man måtte huske først. Oppdrag arkiverte og tømte fra sin egen
side. KO og Lag hadde ikke noe.

**Hvordan det er:** én orkestrator her, og et register modulene melder seg
inn i — samme idiom som `core/opprydding.py`. `core` kjenner ingen modul ved
navn. Bare moduler som **tømmer** noe trenger en handler: KO-loggen og
lagenes registreringer er scopet på vakta og blir liggende (de slettes etter
fristen sin av `purge_old_logs`), og tallene til alle fanene fryses av
`core/vaktstatistikk.py` uansett.

**Rekkefølgen er hele poenget:**

1. Sperrene — noe som gjør avslutningen feil (et oppdrag står på tavla).
   Ingenting er rørt ennå.
2. Backup av hver modul som tømmes (`pre_reset`), *før* transaksjonen.
3. I én transaksjon: sperrene én gang til → frys statistikken → arkiver og
   tøm hver modul → lukk vakta → åpne den nye. Feiler noe, rulles alt
   tilbake — også frysingen.
"""
from __future__ import annotations

from typing import ClassVar

from django.db import transaction
from django.utils import timezone


class BaseVaktsluttHandler:
    """Subklasses per modul som arkiverer og tømmer noe når vakta avsluttes."""

    #: Modul-slug.
    slug: ClassVar[str] = ''
    #: Hva som tømmes, i flertall: «pasienter», «oppdrag». Står i oversikten.
    etikett: ClassVar[str] = ''
    #: Samme i entall — «1 pasienter» leses som en feil. Tom: flertallet brukes.
    entall: ClassVar[str] = ''
    #: Backup-sluggen som tas `pre_reset` før tømmingen, eller '' for ingen.
    backup_slug: ClassVar[str] = ''
    #: Rekkefølgen i oversikten og i avslutningen. Lavest først.
    order: ClassVar[int] = 100

    def antall(self, vakt) -> int:
        """Hvor mange rader som arkiveres og tømmes."""
        raise NotImplementedError

    def sperre(self, vakt) -> str:
        """Hvorfor vakta ikke kan avsluttes nå, eller '' hvis den kan.

        En sperre er noe som ville gjort avslutningen *feil*, ikke bare
        uvanlig: et oppdrag som står på tavla ville blitt slettet halvveis.
        """
        return ''

    def avslutt(self, vakt, bruker, request=None) -> int:
        """Arkiver og tøm. Kalles inne i transaksjonen. Returnerer antallet.

        Ingen rader skal gi ingen arkiv — et tomt arkiv er støy i lista.
        `request` er for auditraden (`logg_arkivhendelse`); den er `None` fra
        en kommando.
        """
        raise NotImplementedError


_REGISTER: dict[str, BaseVaktsluttHandler] = {}


def register(handler: BaseVaktsluttHandler) -> None:
    """Registrer en handler fra `apps.ready()`. Idempotent på slug."""
    if not handler.slug:
        raise ValueError(f'{handler.__class__.__name__} mangler slug.')
    _REGISTER[handler.slug] = handler


def all_handlers() -> list[BaseVaktsluttHandler]:
    return sorted(_REGISTER.values(), key=lambda h: (h.order, h.slug))


class Sperret(Exception):
    """Vakta kan ikke avsluttes nå. `grunner` er én tekst per sperre."""

    def __init__(self, grunner: list[str]):
        super().__init__('; '.join(grunner))
        self.grunner = grunner


def oversikt(vakt) -> dict:
    """Det admin skal se *før* det trykkes: hva som arkiveres, og hva som sperrer.

    Tallene fra statistikkfanene er med slik at det står hvilke faner som
    fryses — også de som ikke tømmes.
    """
    from core.stats import all_handlers as statistikkfaner

    moduler = [
        {'slug': h.slug, 'etikett': h.etikett, 'entall': h.entall or h.etikett,
         'antall': h.antall(vakt), 'sperre': h.sperre(vakt)}
        for h in all_handlers()
    ]
    return {
        'vakt': vakt.navn,
        'moduler': moduler,
        'fryses': [h.display_name for h in statistikkfaner()],
        'sperrer': [m['sperre'] for m in moduler if m['sperre']],
    }


def avslutt(vakt, *, ny_vakt_navn, bruker, request=None) -> dict:
    """Avslutt `vakt` og start `ny_vakt_navn`. Kaster `Sperret` eller
    `VaktnavnOpptatt`; i begge tilfeller er ingenting endret.

    Backupene tas før transaksjonen: de skriver filer, og en fil lar seg ikke
    rulle tilbake. Blir avslutningen avvist etter at de er tatt, står det en
    backup for mye — det er riktig vei å feile.
    """
    from core.backup import create_backup
    from core.models import AppSetting
    from core.vakt import hent_aktiv_vakt, laas_aktiv_vakt, opprett_vakt
    from core.validators import current_local_year
    from core.vaktstatistikk import frys

    handlere = all_handlers()
    grunner = [g for g in (h.sperre(vakt) for h in handlere) if g]
    if hent_aktiv_vakt().pk != vakt.pk:
        # Tidlig, så en avsluttet vakt ikke koster backuper. Vernet er låsen i
        # transaksjonen under — denne sjekken er et kappløp.
        grunner.insert(0, f'«{vakt.navn}» er ikke den aktive vakta.')
    if grunner:
        raise Sperret(grunner)

    for h in handlere:
        if h.backup_slug:
            create_backup(slug=h.backup_slug, kind='pre_reset', user=bruker,
                          note=f'Før avslutning av vakta «{vakt.navn}»')

    with transaction.atomic():
        # Låst, og sjekket at vakta fortsatt er den aktive (28. sep. 2026). To
        # samtidige avslutninger med hvert sitt nye navn frøs ellers samme vakt
        # to ganger; den andre gangen var radene tømt, og det nyeste settet —
        # det som vises — var nuller.
        if laas_aktiv_vakt().pk != vakt.pk:
            raise Sperret([f'«{vakt.navn}» er ikke lenger den aktive vakta — '
                           'den er avsluttet i mellomtiden.'])
        # En gang til: backupene tar tid, og et oppdrag lagt på tavla imens
        # ville ellers blitt arkivert og slettet halvveis.
        grunner = [g for g in (h.sperre(vakt) for h in handlere) if g]
        if grunner:
            raise Sperret(grunner)
        frys(vakt, bruker=bruker)
        tomt = {h.slug: h.avslutt(vakt, bruker, request) for h in handlere}
        vakt.er_aktiv = False
        vakt.avsluttet = timezone.now()
        vakt.save(update_fields=['er_aktiv', 'avsluttet'])
        ny = opprett_vakt(ny_vakt_navn, year=current_local_year(), startet=timezone.now())
        AppSetting.set('aktiv_vakt_id', ny.pk)
    return {'avsluttet_vakt': vakt.navn, 'ny_vakt': ny.navn, 'tomt': tomt}
