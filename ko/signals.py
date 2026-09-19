"""Løftet av systemhendelser inn i KO-loggen, og auditsporet for sletteinngangen.

**Retningen holdes av konstruksjonen.** `ko` → `oppdrag` er lov og håndheves
med AST i `ko/tests_avhengighet.py`; motsatt vei er det ikke. Signalene leses
derfor *her*, i den importerende modulen, og oppdragsmodulen røres ikke — den
skal først røres i pulje 5. Se `ko/systemlinjer.py` for hvilke hendelser som
løftes og hvorfor, og for forbeholdet om at et signal ser raden og ikke
intensjonen.

**Hver mottaker har `@ikke_under_loaddata`.** Django sender `raw=True` når
`loaddata` skriver en rad, og uten vakten ville en gjenoppretting av
oppdragsfila skrevet en fersk KO-logglinje per historisk statusmelding — altså
en logg som forteller at hele fjorårets vakt skjedde i dag.
`SignalerFyrerIkkeUnderLoaddataTests` leser alle mottakerne og krever vakten.

**Ingen mottaker får kaste.** En KO-logg som ikke lar seg skrive skal ikke ta
ned en stempling i en bil — bilen er det operative, loggen er dokumentasjonen.
Feilen logges, og linja mangler. Motsatt prioritering ville gjort loggen til en
ny grunn til at oppdragsmodulen ikke virker.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from audit.utils import ikke_under_loaddata
# `ko` → `oppdrag` er den tillatte retningen (`ko/tests_avhengighet.py`).
# **Klasser og ikke strengreferanser**: `SignalerFyrerIkkeUnderLoaddataTests`
# leser `@receiver(post_save, sender=Klasse)` med en regex, og `sender='...'`
# ville gått rett forbi den — altså fire mottakere uten dekning, med testen
# grønn. Regexen er utvidet til å ta begge formene i samme slengen, men
# idiomet her følger de andre modulene.
from oppdrag import choices
from oppdrag.models import (
    Enhetshendelse,
    Oppdrag,
    Oppdragsenhet,
    Statusmelding,
    Vaktmodusperiode,
)

from . import systemlinjer
from .services import systemlinje

logger = logging.getLogger(__name__)


def _trygt(navn):
    """Dekoratør: en mottaker som feiler skal logge, ikke kaste. Se docstringen."""
    def ytre(fn):
        def indre(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:   # noqa: BLE001 — bevisst bred, se modulens docstring
                logger.warning('ko: kunne ikke skrive systemlinje for %s',
                               navn, exc_info=True)
        indre.__name__ = fn.__name__
        indre.__doc__ = fn.__doc__
        # `SignalerFyrerIkkeUnderLoaddataTests` leser mottakerne og krever
        # vakten. Den leser den innpakkede funksjonen, så merket må følge med.
        indre.__wrapped__ = fn
        return indre
    return ytre


def _enhetsnavn(enhet) -> str:
    """Kallesignalet, frosset på linja (§4.7).

    Loggen skriver **enheten**, ikke besetningen: den delte kontoen kan ikke
    svare på hvem som satt i bilen kl. 21:14 — den brukes av 06–14, 14–22 og
    22–06. Besetningen utledes gjennom vaktlista og tidspunktet, og *den* skal
    ikke fryses: en retting i vaktlista i etterkant retter som regel
    virkeligheten. Kallesignalet skal.
    """
    return getattr(enhet, 'navn', '') or ''


def _fort_av_ko(melding) -> bool:
    """Meldte noen andre enn bilen selv denne statusen?

    §3.1: tilstanden «bærer i seg selv skillet mellom «bilen sa det» og «KO
    førte det», og det skillet må være synlig i grensesnittet og i loggen».
    Det utledes, det trenger ingen ny kolonne: enheten har en konto
    (`Enhet.user`), og meldte noen annen konto statusen, er det en føring.

    Ingen konto på enheten — en enhet opprettet uten innlogging — gir `False`
    og ikke `True`. «Ukjent» skal ikke tegnes som en overstyring: en påstand
    om at KO overstyrte, på en linje der vi ikke vet, er verre enn ingen
    påstand.
    """
    rad = melding.oppdragsenhet
    enhet_konto = getattr(getattr(rad, 'enhet', None), 'user_id', None)
    if enhet_konto is None or melding.meldt_av_id is None:
        return False
    return melding.meldt_av_id != enhet_konto


# ── Oppdraget ────────────────────────────────────────────────────────────────

@receiver(post_save, sender=Oppdrag)
@ikke_under_loaddata
@_trygt('oppdrag_opprettet')
def oppdrag_opprettet(sender, instance, created, **kwargs):
    """Begynnelsen på et forløp. Bare ved opprettelse.

    Feltendringer på et eksisterende oppdrag løftes **ikke** — `audit/` fører
    dem på feltnivå, og en logg som får en linje hver gang noen retter en
    skrivefeil slutter å bli lest (regel 2 i `ko/systemlinjer.py`).
    """
    if not created:
        return
    systemlinje(
        instance.vakt,
        systemlinjer.OPPDRAG_OPPRETTET,
        {
            'oppdragsnummer': instance.oppdragsnummer,
            'problemstilling': instance.problemstilling,
            'hastegrad': instance.hastegrad,
            'lokasjon': getattr(instance.lokasjon, 'navn', '') if instance.lokasjon_id else '',
        },
        tidspunkt=instance.created_at,
    )


@receiver(post_save, sender=Statusmelding)
@ikke_under_loaddata
@_trygt('oppdrag_status')
def statusmelding_skrevet(sender, instance, created, **kwargs):
    """Hver statusovergang — og hver **retting** som en egen linje.

    De to er samme tabell og skilles på `korrigerer`. Rettingen får sin egen
    kode fordi den er en annen setning: «Fremme rettet fra 21:40 til 21:14» er
    det man leter etter når tidslinja ser rar ut, og uten den ser den ut som
    om den alltid var slik (§4.3).
    """
    if not created:
        return
    oppdrag = instance.oppdrag
    rad = instance.oppdragsenhet
    felles = {
        'oppdragsnummer': oppdrag.oppdragsnummer,
        'enhet': _enhetsnavn(getattr(rad, 'enhet', None)),
        'status_navn': choices.status_navn_for(oppdrag.hastegrad, instance.status),
    }
    if instance.korrigerer_id:
        data = dict(felles)
        data['fra'] = systemlinjer.klokkeslett(instance.korrigerer.tidspunkt)
        data['til'] = systemlinjer.klokkeslett(instance.tidspunkt)
        systemlinje(oppdrag.vakt, systemlinjer.TIDSPUNKT_KORRIGERT, data,
                    tidspunkt=instance.tidspunkt)
        return
    data = dict(felles)
    data['fort_av_ko'] = _fort_av_ko(instance)
    data['forsinket'] = bool(instance.forsinket)
    systemlinje(oppdrag.vakt, systemlinjer.OPPDRAG_STATUS, data,
                tidspunkt=instance.tidspunkt)


@receiver(post_save, sender=Oppdragsenhet)
@ikke_under_loaddata
@_trygt('enhet_varslet')
def enhet_varslet(sender, instance, created, **kwargs):
    """«Vi sendte to biler» står ikke lesbart noe annet sted.

    `varslet_modus` er frosset ved varsling i oppdragsmodulen, og brukes som
    den er: merket «(passiv vakt)» på et oppdrag fra tre timer siden skal ikke
    skifte tekst i det noen vipper bryteren.
    """
    if not created:
        return
    systemlinje(
        instance.oppdrag.vakt,
        systemlinjer.ENHET_VARSLET,
        {
            'oppdragsnummer': instance.oppdrag.oppdragsnummer,
            'enhet': _enhetsnavn(instance.enhet),
            'modus': instance.varslet_modus or '',
        },
        tidspunkt=instance.varslet_at,
    )


#: `Enhetshendelse.type` → KO-kode. **Fire av de ni kodene fantes allerede**
#: som denne tabellen, med tidspunkt og bruker. Det er §2-erfaringen i praksis:
#: sjekk om oppdragsmodulen har begrepet før du designer det inn i KO.
#:
#: En type som ikke står her, løftes ikke — og `ko/tests_systemlinjer.py`
#: krever at hver type i `Enhetshendelse.TYPER` enten er med eller står i
#: `ENHETSHENDELSER_UTELATT` med en begrunnelse. Ellers ville en ny type i
#: oppdragsmodulen falt stille ut av loggen.
ENHETSHENDELSER: dict[str, str] = {
    'tatt_av': systemlinjer.ENHET_TATT_AV,
    'rykket_videre': systemlinjer.ENHET_RYKKET_VIDERE,
    'avbrutt': systemlinjer.ENHET_AVBROT,
    'avventer': systemlinjer.ENHET_AVVENTER,
}

#: Typer som bevisst ikke løftes. Tom i dag — alle fire er situasjon, ikke
#: oppsett. Lista finnes for at den neste skal måtte ta stilling.
ENHETSHENDELSER_UTELATT: dict[str, str] = {}


@receiver(post_save, sender=Enhetshendelse)
@ikke_under_loaddata
@_trygt('enhetshendelse')
def enhetshendelse_skrevet(sender, instance, created, **kwargs):
    """Tatt av, rykket videre, avbrøt, avventer.

    **«Trenger ny ressurs» er et flagg her og ikke en linje til** (regel 3).
    De to er én hendelse sett fra hver sin side: bilen forsvant *og* oppdraget
    står uten ressurs. To linjer ville lest som to ting som skjedde.
    """
    if not created:
        return
    kode = ENHETSHENDELSER.get(instance.type)
    if kode is None:
        return
    oppdrag = instance.oppdrag
    systemlinje(
        oppdrag.vakt,
        kode,
        {
            'oppdragsnummer': oppdrag.oppdragsnummer,
            'enhet': _enhetsnavn(instance.enhet),
            'detalj': instance.detalj or '',
            'trenger_ressurs': bool(oppdrag.trenger_ressurs),
        },
        tidspunkt=instance.tidspunkt,
    )


@receiver(post_save, sender=Vaktmodusperiode)
@ikke_under_loaddata
@_trygt('vaktmodus')
def vaktmodus_satt(sender, instance, created, **kwargs):
    """Forklarer hvorfor en bil ikke ble varslet.

    Perioden og ikke `Enhet.passiv_vakt`: perioden opprettes én gang per
    bytte og bærer vakta selv, mens flagget på enheten skrives ved hver
    lagring og ikke vet hvilken vakt den hører til.
    """
    if not created:
        return
    systemlinje(
        instance.vakt,
        systemlinjer.VAKTMODUS,
        {'enhet': _enhetsnavn(instance.enhet), 'modus': instance.modus},
        tidspunkt=instance.fra,
    )
