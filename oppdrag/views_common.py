"""Delte hjelpere for oppdragsmodulens views."""
from __future__ import annotations

import hashlib
import json

from django.utils import timezone

from . import choices, services


def json_body(request):
    """Parse JSON-kroppen, eller returner tom dict."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}
    # `[]`, `"x"` og `null` er gyldig JSON og ga 500 på første `.get()` (M8).
    return data if isinstance(data, dict) else {}


def etag_for(rader, ekstra=None) -> str:
    """ETag over en liste av sammenlignbare tupler.

    Samme mønster som navneregistrene: sha256 brukes kun til identitet, ikke
    sikkerhet, og kortes til 16 tegn for å holde headeren kompakt.

    `ekstra` er det som ikke er en rad — antall i historikken (21. sep.
    2026). Det legges *ved siden av* radene, ikke inn i lista: `sorted()`
    sammenligner tuplene ledd for ledd, og en tekstnøkkel mot en tall-ID
    gir `TypeError` — og 500 på lista, som testen ikke så fordi tavla var
    tom i begge kallene.
    """
    raa = str(sorted(rader)) + ('' if ekstra is None else '|' + str(ekstra))
    return '"v1:' + hashlib.sha256(raa.encode('utf-8')).hexdigest()[:16] + '"'


def etag_for_svar(data, ekstra=None) -> str:
    """ETag over **hele** den serialiserte payloaden (26. sep. 2026, A2).

    `etag_for` tar en håndskrevet liste med felt, og de tre listene som polles
    manglet felt for felt i to uker — sist hastegrad, lokasjon, antall,
    fritekst og enhetslista, så en endring i oppdragsvinduet druknet i en 304.
    Hashes hele svaret, er et nytt felt med uten at noen husker det.

    **Prisen:** svaret får ikke bære noe regnet ut fra klokka, ellers blir
    hver polling en ny ETag og aldri 304. `tests_etag.test_uendret_gir_304`
    holder det. `default=str` tar tidspunkt og desimaler som måtte dukke opp.
    """
    raa = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    if ekstra is not None:
        raa += '|' + str(ekstra)
    return '"v2:' + hashlib.sha256(raa.encode('utf-8')).hexdigest()[:16] + '"'


def er_enhetskonto(user) -> bool:
    """True hvis kontoen er knyttet til en `Enhet`.

    **Dette, og ikke tilgangsnivået, avgjør hvilket grensesnitt kontoen får.**
    Å velge skjerm på «er nivået nøyaktig `skriv_handling`» ville brukt et
    ordnet nivå som en identitet — samme feil som §2.3 i rollemodellnotatet
    beskriver. Stigen sier at `skriv_full` dekker `skriv_handling`, så det
    oppslaget ville vært galt i det noen fikk begge.

    Koblingen gir ingen tilgang i seg selv; den avgjør bare hva som er nyttig
    å vise.
    """
    return getattr(user, 'enhet', None) is not None


def status_tidspunkt_for(oppdrag_liste, meldinger=None) -> dict:
    """``{oppdrag_id: iso-tidspunkt}`` for den gjeldende meldingen bak hvert
    oppdrags nåværende status — «Fremme siden 14:32».

    Én spørring for hele lista (`gjeldende_bulk`), ikke én per rad: sentralbordet
    henter lista hvert 30. sekund. Oppdrag uten melding for statusen (venter,
    før noen har stemplet) får ``None``, og klienten viser da bare tiden siden
    opprettelse.
    """
    from .models import Statusmelding
    if meldinger is None:
        meldinger = Statusmelding.objects.gjeldende_bulk([o.pk for o in oppdrag_liste])
    ut = {}
    for o in oppdrag_liste:
        treff = [m for m in meldinger.get(o.pk, []) if m.status == o.status]
        ut[o.pk] = treff[-1].tidspunkt.isoformat() if treff else None
    return ut


def enheter_til_liste(oppdrag, meldinger=None) -> list:
    """Enhetene på oppdraget med hver sin status — matrisen sentralbordet
    ser. Leser `oppdrag.enheter`; kalleren prefetcher `enheter__enhet` der
    det er mange oppdrag.

    ``status_tidspunkt`` per enhet er når *hun* fikk statusen hun står i.
    ``meldinger`` er oppdragets gjeldende meldinger (fra `gjeldende_bulk`)
    når kalleren alt har dem; ellers hentes de her — én spørring, som er
    greit for ett oppdrag og ikke for en liste."""
    from .models import Statusmelding
    if meldinger is None:
        meldinger = Statusmelding.objects.gjeldende(oppdrag)
    ut = []
    for rad in oppdrag.enheter.all():
        treff = [m for m in meldinger
                 if m.oppdragsenhet_id == rad.pk and m.status == rad.status]
        siste = treff[-1] if treff else None
        ut.append({
            'enhet_id': rad.enhet_id,
            'enhet_navn': rad.enhet.navn,
            # **Modusen slik den var da hun ble varslet** (André, 16. sep.
            # 2026: «når de får tildelt oppdrag skal det vises f.eks. Lege02
            # (passiv vakt)»). Frosset ved varslingen, ikke lest fra enheten
            # nå — ellers ville merket på et gammelt oppdrag skiftet tekst i
            # det noen vipper bryteren. Tom for alle som ikke har passiv vakt,
            # og da vises ingenting: «Aktiv» på en ambulanse er støy.
            'varslet_modus': rad.varslet_modus,
            'status': rad.status,
            'status_navn': choices.status_navn_for(oppdrag.hastegrad, rad.status),
            'status_tidspunkt': siste.tidspunkt.isoformat() if siste else None,
            # «Avreist → Sykehus» skal synes i sentralbordet, ikke bare i
            # tidslinjen (André, 12. sep. 2026).
            'sted_navn': choices.sted_navn_for(siste.sted, siste.sted_tekst) if siste else '',
            'varslet_at': rad.varslet_at.isoformat(),
            'rekkefolge': rad.rekkefolge,
        })
    return ut


def oppdrag_til_dict(oppdrag, *, for_enhet: bool = False,
                     status_tidspunkt=None, koblingsrad=None, meldinger=None,
                     avbrutt_av=None, avventer_av=None) -> dict:
    """Serialiser ett oppdrag.

    ``for_enhet=True`` **utelater fritekst når oppdraget er avsluttet**. Det er
    en av de to skjulereglene, og den håndheves her — i serverens svar — ikke i
    nettleseren. Skjules teksten i JS, ligger den fortsatt i responsen, og en
    bil som blir stående ulåst er nettopp scenarioet regelen finnes for.

    ``status_tidspunkt`` er når oppdraget fikk statusen det står i (fra
    `status_tidspunkt_for`). Sentralbordet viser «tid siden» av den —
    prosjektleder, 11. sep. 2026 — og den sendes bare der lista bygges, slik at
    ett kall per rad ikke sniker seg inn via denne funksjonen.

    ``koblingsrad`` er **bilens** rad på oppdraget (flere enheter, 11. sep.
    2026). Med den er `status` og `neste_overgang` hennes, ikke oppdragets
    utledede — bilen skal se sin egen kjede. `varslede` er de andre
    enhetenes navn; deres stempler sendes som `andre_meldinger` der lista og
    detaljen bygges (§7.3, snudd 12. sep. 2026).

    ``meldinger`` sendes videre til `enheter_til_liste` av samme grunn som
    ``status_tidspunkt``: lista skal ikke koste én spørring per rad.

    ``avbrutt_av`` er navnene på enhetene som trykket «Avbryt» (15. sep. 2026,
    André: «trykker en bil avbryt så må det vises»). Sendes den ikke, slås den
    opp for dette ene oppdraget; lista sender den ferdig, av samme grunn som
    over.
    """
    status = koblingsrad.status if koblingsrad is not None else oppdrag.status
    data = {
        'id': oppdrag.pk,
        # Nummeret man sier på samband. `id` er databasenøkkelen og skal ikke
        # vises — den er global og hopper mellom år.
        'nummer': oppdrag.oppdragsnummer,
        # Tomt når oppdraget ble opprettet uten enhet (19. sep. 2026).
        'enhet_id': oppdrag.enhet_id,
        'enhet_navn': oppdrag.enhet.navn if oppdrag.enhet_id else '',
        'problemstilling': oppdrag.problemstilling,
        # Antall for problemstillinger som bærer et (transport); ellers null.
        'antall': oppdrag.antall,
        'hastegrad': oppdrag.hastegrad,
        # Bilens Rød/Gul/Grønn. Tom til bilen har satt den — klienten viser
        # «—», og det er informasjon: ikke vurdert ennå.
        'grovsortering': oppdrag.grovsortering,
        'grovsortering_navn': choices.GROVSORTERING_NAVN.get(oppdrag.grovsortering, ''),
        'lokasjon_id': oppdrag.lokasjon_id,
        'lokasjon_navn': oppdrag.lokasjon.navn,
        'status': status,
        'status_navn': choices.status_navn_for(oppdrag.hastegrad, status),
        'enheter': enheter_til_liste(oppdrag, meldinger),
        'opprettet': oppdrag.created_at.isoformat(),
        'status_tidspunkt': status_tidspunkt,
        'historikk_fra': (oppdrag.historikk_fra.isoformat()
                          if oppdrag.historikk_fra else None),
        # Bilen rykket videre; oppdraget står på tavla og venter på en ny.
        'trenger_ressurs': oppdrag.trenger_ressurs,
        'trenger_ressurs_siden': (oppdrag.trenger_ressurs_siden.isoformat()
                                  if oppdrag.trenger_ressurs_siden else None),
        # **«Avbrutt» og «trenger ny ressurs» er to ulike beskjeder**, og var
        # én fram til 15. sep. 2026: avbrøt en bil et oppdrag en annen alt
        # hadde løst, sto det «trenger ny ressurs» på et ferdig oppdrag.
        # Nå sier flagget bare om noen må sendes, og dette feltet hvem som
        # avbrøt — uavhengig av hverandre.
        'avbrutt_av': (list(avbrutt_av) if avbrutt_av is not None
                       else services.avbrutt_av(oppdrag)),
        # **«Avventer» er en tredje beskjed** (16. sep. 2026), og den er igjen
        # noe annet: avbrutt sier hva som *skjedde*, trenger-ressurs krever
        # handling nå, avventer sier at noen har svart — bare ikke ja.
        # Sendes ferdig av lista (`avventer_av_bulk`), av samme grunn som
        # `avbrutt_av`: slås den opp her, koster tavla to spørringer per rad.
        'avventer_av': (list(avventer_av) if avventer_av is not None
                        else services.avventer_av_bulk([oppdrag.pk]).get(oppdrag.pk, [])),
        # **Hendelsen oppdraget hører til** (KO pulje 5, 18. sep. 2026). Lest
        # herfra, skrevet bare av `ko.services.knytt_oppdrag`. Nummer og
        # tittel følger med så tavla kan gruppere uten et oppslag per rad;
        # `None` er «uten hendelse», som er det vanlige (§7).
        'hendelse_id': oppdrag.hendelse_id,
        'hendelse_nummer': (oppdrag.hendelse.hendelsesnummer
                            if oppdrag.hendelse_id else None),
        'hendelse_tittel': oppdrag.hendelse.tittel if oppdrag.hendelse_id else '',
        # Prioriteten, lagene og de delte logglinjene på hendelsen (KO,
        # 18.–19. sep. 2026). Lest her som nummer og tittel over: bilen skal
        # se hvilke lag som er på hendelsen og det KO har *delt* om den, og
        # KO-raden bærer prioritetsmerket. Tomt når oppdraget ikke hører til
        # noen. Lagene og linjene er KOs, lest gjennom to metoder på
        # hendelsen (`lag_navn`, `delte_linjer_for`) — denne modulen kjenner
        # verken lagmodellen eller loggen, og skal ikke gjøre det.
        'hendelse_prioritet': oppdrag.hendelse.prioritet if oppdrag.hendelse_id else '',
        'hendelse_lag': oppdrag.hendelse.lag_navn() if oppdrag.hendelse_id else [],
    }
    skjul_fritekst = for_enhet and status == choices.TERMINAL
    data['fritekst'] = '' if skjul_fritekst else oppdrag.fritekst
    # De delte linjene følger fritekstens regel: fritekst er der
    # helseopplysningene havner (`NOTAT_DPIA_OG_FRITEKST.md` §7), og bilen
    # skal ikke sitte med dem etter at oppdraget er avsluttet. Hver rad
    # bærer `delt_at`, så bilen kan vise det som er nytt for henne.
    data['delte_linjer'] = (
        [] if skjul_fritekst or not oppdrag.hendelse_id
        else oppdrag.hendelse.delte_linjer_for(oppdrag))
    if for_enhet:
        # «Neste»-knappen vet hvilken overgang den utfører fordi serveren sier
        # det her — JS-en har ingen egen kopi av kjeden å komme i utakt med.
        neste = services.neste_i_kjeden(status)
        data['neste_overgang'] = neste
        data['neste_navn'] = choices.status_navn_for(oppdrag.hastegrad, neste) if neste else None
        # Den andre knappen (12. sep. 2026): «Behandlet på sted» i Fremme —
        # «Utført» på Drift og Plassering (19. sep. 2026).
        # Ingen egen Ledig-knapp lenger — Ledig er «neste» etter Leverer og
        # Behandlet, og finnes ikke mellom Avreist og Leverer.
        alternativ = services.alternativ_for(status, oppdrag.hastegrad)
        data['alternativ_overgang'] = alternativ[0] if alternativ else None
        data['alternativ_navn'] = alternativ[1] if alternativ else None
        # «Avbryt» er sin egen knapp fra 22. sep. 2026, i Rykker ut og Fremme.
        data['kan_avbryte'] = status in services.AVBRYT_FRA
        egen = koblingsrad.enhet_id if koblingsrad is not None else None
        data['varslede'] = [e['enhet_navn'] for e in data['enheter']
                            if e['enhet_id'] != egen]
        # Når *hun* ble varslet — lydvarselet i bilen (12. sep. 2026) måler
        # ventetida fra dette, ikke fra da oppdraget ble opprettet.
        data['varslet_at'] = (koblingsrad.varslet_at.isoformat()
                              if koblingsrad is not None else None)
    return data


def melding_til_dict(melding) -> dict:
    return {
        'id': melding.pk,
        'status': melding.status,
        'status_navn': choices.status_navn_for(melding.oppdrag.hastegrad, melding.status),
        # Hvem sin melding: med flere enheter må tidslinjen si det.
        'enhet_id': melding.oppdragsenhet.enhet_id if melding.oppdragsenhet_id else None,
        'enhet_navn': melding.oppdragsenhet.enhet.navn if melding.oppdragsenhet_id else '',
        'tidspunkt': melding.tidspunkt.isoformat(),
        'meldt_av': getattr(melding.meldt_av, 'username', '') or '',
        'forsinket': melding.forsinket,
        'automatisk': melding.automatisk,
        # Ført av sentralbordet (§9), ikke stemplet av bilen.
        'manuell': melding.manuell,
        'korrigerer': melding.korrigerer_id,
        # Trukket tilbake av sentralbordet (22. sep. 2026). Raden står i
        # tidslinjen, gjennomstreket, med hvem og når — den slettes ikke.
        'trukket_tilbake_at': (melding.trukket_tilbake_at.isoformat()
                               if melding.trukket_tilbake_at else None),
        'trukket_tilbake_av': getattr(melding.trukket_tilbake_av, 'username', '') or '',
        # «Avreist → Sykehus». Tom for alle andre statuser.
        'sted': melding.sted,
        'sted_tekst': melding.sted_tekst,
        'sted_navn': choices.sted_navn_for(melding.sted, melding.sted_tekst),
    }


def hendelse_til_dict(h) -> dict:
    return {
        'id': h.pk,
        'type': h.type,
        'type_navn': h.get_type_display(),
        'detalj': h.detalj,
        'enhet_navn': h.enhet.navn,
        'tidspunkt': h.tidspunkt.isoformat(),
        'av': getattr(h.av, 'username', '') or '',
    }


def endring_til_dict(endring) -> dict:
    """En endring i oppdragets verdier, til tidslinjen."""
    return {
        'id': endring.pk,
        'felt': endring.felt,
        'felt_navn': endring.get_felt_display(),
        'fra': endring.fra_verdi,
        'til': endring.til_verdi,
        'automatisk': endring.automatisk,
        'tidspunkt': endring.created_at.isoformat(),
        'av': endring.endret_av_navn,
    }


def bytte_til_dict(bytte) -> dict:
    return {
        'id': bytte.pk,
        'fra_enhet': bytte.fra_enhet.navn,
        'til_enhet': bytte.til_enhet.navn,
        'tidspunkt': bytte.created_at.isoformat(),
        'byttet_av': getattr(bytte.byttet_av, 'username', '') or '',
    }


def naa():
    return timezone.now()
