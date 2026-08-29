"""Vaktarkiv for oppdragsmodulen (fase 7).

To ting skjer her: **opprettelsen** av arkivet, og **handleren** som lar
``core.arkiv`` signere, verifisere og kollapse det. Frysing, hashing og
kollaps eies av core; denne fila eier hva som går inn i payloaden — samme
arbeidsdeling som ``patients/arkiv.py``.

**Arkivering er ikke det samme som historikk.** `Oppdrag.historikk_fra` rydder
ett oppdrag av tavla og er fullt reversibel. Dette fryser hele vakta, med
signatur og en kollaps som sletter radnivået etter 24 måneder. De to ligger på
hver sin knapp fordi de er to helt ulike handlinger — og oppdrag i historikken
arkiveres selvsagt med: de er en del av vakta.

**Arkiveringen slås ikke sammen med pasientarkivet i denne runden** (§12.1 i
beslutningsnotatet). Prisen er at noen kan arkivere pasienter og glemme
oppdrag; det er en operativ risiko, og den håndteres med et punkt i
`docs/RUNBOOK_VAKT.md` som faktisk leses ved vaktslutt.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.arkiv import BaseArkivHandler, beregn_sha256, register

from . import choices
from .models import ArkivertOppdrag, Oppdrag, OppdragArkiv, Statusmelding
from .statistikk import _STATUSFELT, arkiv_stats


def arkiver_vakt(vakt, notat, user):
    """Frys oppdragene i ``vakt`` som et arkiv. Returnerer (arkiv, antall).

    Hele operasjonen ligger i én transaksjon: et arkiv med signatur over rader
    som ikke ble opprettet, ville meldt tukling ved første visning.

    Rettinger er regnet inn før frysingen — radene bygges fra `gjeldende()`,
    så det er det korrigerte tidspunktet som lagres. Originalen blir liggende i
    `Statusmelding` så lenge vakta finnes, og i auditsporet etterpå.
    """
    with transaction.atomic():
        oppdragene = list(
            Oppdrag.objects
            .filter(vakt=vakt)
            .select_related('enhet', 'lokasjon')
            .order_by('oppdragsnummer')
        )
        meldinger = Statusmelding.objects.gjeldende_bulk(
            [o.pk for o in oppdragene])

        naa_lokal = timezone.localtime(timezone.now())
        arkiv = OppdragArkiv.objects.create(
            tittel=f"{vakt.navn} — arkivert {naa_lokal.strftime('%d.%m.%Y %H:%M')}",
            vakt=vakt,
            # Frosset: vakta kan bli omdøpt eller slettet, arkivet skal
            # fortsatt kunne fortelle hvilken vakt det er.
            vakt_navn=vakt.navn,
            antall_rader=len(oppdragene),
            notat=notat or '',
            importert_av=user,
            importert_av_navn=getattr(user, 'username', '') or '',
            sha256='',   # settes når radene finnes
        )

        rader = []
        for oppdrag in oppdragene:
            gjeldende = meldinger[oppdrag.pk]
            per_status = {m.status: m for m in gjeldende}
            felter = {
                felt: (per_status[status].tidspunkt if status in per_status else None)
                for status, felt in _STATUSFELT.items()
            }
            rader.append(ArkivertOppdrag(
                arkiv=arkiv,
                oppdragsnummer=oppdrag.oppdragsnummer,
                enhet_navn=oppdrag.enhet.navn if oppdrag.enhet else '',
                lokasjon_navn=oppdrag.lokasjon.navn if oppdrag.lokasjon else '',
                problemstilling=oppdrag.problemstilling or '',
                hastegrad=oppdrag.hastegrad or '',
                sluttstatus=oppdrag.status,
                opprettet_at=oppdrag.created_at,
                automatiske_statuser=sorted(
                    m.status for m in gjeldende if m.automatisk),
                antall_forsinket=sum(1 for m in gjeldende if m.forsinket),
                **felter,
            ))
        ArkivertOppdrag.objects.bulk_create(rader)

        handler = OppdragArkivHandler()
        arkiv.sha256 = beregn_sha256(handler, arkiv)
        arkiv.save(update_fields=['sha256'])

        return arkiv, len(rader)


class OppdragArkivHandler(BaseArkivHandler):
    """Arkivering av oppdrag i én vakt."""

    slug = 'oppdrag'
    display_name = 'Oppdragsarkiv'
    arkiv_model = OppdragArkiv

    # `core.backup`-handleren som dekker arkivmodellene. Kollaps nektes med
    # mindre det finnes en backup med denne slugen tatt etter at arkivet ble
    # opprettet — se `oppdrag/backup.py`.
    backup_slug = 'oppdrag_arkiv'

    # 24 måneder, som pasientarkivet. Begrunnelsen er den samme og står i
    # `docs/PERSONVERN_DOKUMENTASJON.md` A.9: to hele sesonger, slik at årets
    # vakt kan sammenlignes med fjorårets under planleggingen.
    retention_dager = 730

    def rad_dicts(self, arkiv):
        """Radene som inngår i signaturen.

        Tidspunkt som ISO-strenger: payloaden skal kunne hashes kanonisk, og
        et `datetime` er ikke JSON. Formen er *ny* — ingen arkiver finnes i
        prod ennå — men fra første arkivering er den låst på samme måte som
        pasientmodulens, og `ArkivSignaturLaastTests` pinner den.
        """
        rader = []
        for rad in arkiv.oppdrag.all():
            data = {
                'oppdragsnummer': rad.oppdragsnummer,
                'enhet_navn': rad.enhet_navn,
                'lokasjon_navn': rad.lokasjon_navn,
                'problemstilling': rad.problemstilling,
                'hastegrad': rad.hastegrad,
                'sluttstatus': rad.sluttstatus,
                'opprettet_at': rad.opprettet_at.isoformat(),
                'automatiske_statuser': list(rad.automatiske_statuser or []),
                'antall_forsinket': rad.antall_forsinket,
            }
            for status, felt in _STATUSFELT.items():
                verdi = getattr(rad, felt)
                data[felt] = verdi.isoformat() if verdi else None
            rader.append(data)
        return rader

    def sha_payload(self, arkiv, rader):
        """Radnivå-payload. **Endres denne, verifiserer ingen arkiv igjen.**"""
        return {
            'arkiv_id': arkiv.pk,
            'vakt_navn': arkiv.vakt_navn,
            'oppdrag': sorted(rader, key=lambda r: r['oppdragsnummer']),
        }

    def aggregat_sha_payload(self, arkiv, aggregat):
        return {
            'arkiv_id': arkiv.pk,
            'vakt_navn': arkiv.vakt_navn,
            'aggregat': aggregat,
        }

    def bygg_aggregat(self, arkiv):
        """Tallene som fryses ved kollaps.

        Kun `full` — oppdragsmodulen har ingen egen «basis»-statistikk slik
        pasientmodulen har til header-chipsene. Nøkkelen beholdes likevel,
        slik at formen er den samme i begge arkivene.
        """
        return {'full': arkiv_stats(arkiv)}

    def antall_rader(self, arkiv):
        return arkiv.oppdrag.count()

    def slett_rader(self, arkiv):
        return ArkivertOppdrag.objects.filter(arkiv=arkiv).delete()[0]


def register_handlers() -> None:
    """Kalles fra ``oppdrag.apps.OppdragConfig.ready()``."""
    register(OppdragArkivHandler())
