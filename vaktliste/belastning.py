"""Belastningen og planleggingstallene (fase 5) — timer, hvile, overlapp.

Varsler, sperrer ikke: tallene måles mot `Belastningsgrenser`. Reglene står i
`vaktliste/CLAUDE.md` under «Belastning, budsjett og timeoversikt».

Skilt ut av `vaktliste/services.py` i G2 (14. okt. 2026).
"""
from __future__ import annotations

from django.utils import timezone

from core.sortering import norsk_nokkel

from . import intervaller
from .models import Belastningsgrenser
from .services import poster_for_korps, synlige_vaktposter


def _timer(fra, til):
    """Timer mellom to tidspunkt, eller ``0.0`` hvis spennet ikke gir mening."""
    if fra is None or til is None or til <= fra:
        return 0.0
    return round((til - fra).total_seconds() / 3600, 2)


def _hviletider(skift):
    """Hullene mellom en persons skift, i timer, i kronologisk rekkefølge.

    **Overlappende skift gir hvile 0, ikke en negativ verdi.** To lister på
    samme tid er noe planleggeren skal se, og et negativt tall i en
    «korteste hvile»-kolonne ser ut som en regnefeil framfor et varsel.
    Overlappet i seg selv fanges av `_overlappstimer()`.

    **Null her betyr to ulike ting, og det er med vilje.** Skift som henger
    sammen (08–16 og 16–20) gir null hvile, og det er sant. Overlappende
    skift gir også null. Kolonnen kan ikke skille dem — det er nettopp
    derfor `overlapp` er sitt eget tall, og ikke noe man skal lese ut av
    denne.
    """
    ordnet = sorted(skift, key=lambda vp: vp.fra_tid)
    ut = []
    for forrige, neste in zip(ordnet, ordnet[1:]):
        if neste.fra_tid < forrige.til_tid:
            ut.append(0.0)
        else:
            ut.append(_timer(forrige.til_tid, neste.fra_tid))
    return ut


def _overlappstimer(skift):
    """Hvor mange timer av en persons skift som er dobbeltbooket.

    **Definisjonen er «sum minus union».** 12–20 og 16–22 er 8 + 6 = 14 timer
    skift, mens personen er til stede fra 12 til 22 — ti timer. Differansen,
    fire, er overlappet. Da gjelder også `timer - overlapp = faktisk
    tilstedeværelse`, som er det tallet vaktlederen egentlig spør etter.

    Punktet sto i `TODO.md` fra 14. sep. 2026: `_hviletider()` lovet denne
    tellingen i docstringen sin, men den fantes ikke. Det som skjedde i
    stedet var at `korteste_hvile` ble 0.0 og raden ble flagget som **kort
    hvile** — altså ble et dobbeltbooket mannskap vist som et hvileproblem,
    og planleggeren fikk aldri vite hva det egentlig var.

    **Probono teller med, i motsetning til i `timer`.** Summen er det
    organisasjonen betaler for og hopper derfor over probono; et overlapp er
    en beskjed om at én person står to steder samtidig, og kroppen skiller
    ikke på lønn. Samme resonnement som `lengste_skift` og `korteste_hvile`.

    Regnet i sekunder og rundet **én gang** til slutt. Summeres avrundede
    timetall hver for seg, kan to skift som ikke overlapper gi 0.01 — og et
    varsel som fyrer på en avrundingsfeil er et varsel man slår av.
    """
    spenn = sorted((vp.fra_tid, vp.til_tid) for vp in skift
                   if vp.fra_tid and vp.til_tid and vp.til_tid > vp.fra_tid)
    # `< 2` er en snarvei, ikke en regel: ett skift gir sum lik union og
    # dermed null uansett. (Til 26. sep. 2026 vernet den også `spenn[0]` på
    # en tom liste; løkka bor nå i `intervaller.slaa_sammen`, som tåler det.)
    if len(spenn) < 2:
        return 0.0
    sum_s = intervaller.sekunder(spenn)
    union_s = intervaller.sekunder(intervaller.slaa_sammen(spenn))
    return round((sum_s - union_s) / 3600, 2)


def belastning_per_person(vaktliste, grenser=None, user=None, korps_id=None):
    """Timer, skift, lengste skift og korteste hvile — per person.

    Bestillingen bak §8b: «lista skal hjelpe planleggeren å se *belastningen*
    før vakta, ikke bare bemanningen».

    **Sortert på totaltimer, synkende.** Den som er i ferd med å bli brukt opp
    skal ligge øverst — en alfabetisk liste ville skjult henne på rad tolv.

    **Ledige plasser telles ikke som en person.** De er et behov, ikke en
    belastning, og en rad uten navn i en persontabell ser ut som en feil.

    Under drift følger et **faktisk**-tall med, regnet fra stemplene i stedet
    for planen (`mott_at`/`av_vakt_at`). Da blir «planlagt mot faktisk»
    synlig: hvem gikk lengre enn planlagt. Det koster lite når feltene alt er
    atskilt — samme grep som oppdragsstatistikkens plan/målt-skille.
    """
    from .models import Vaktpost
    grenser = grenser or Belastningsgrenser.hent()

    poster = (Vaktpost.objects
              .filter(ressurs__vaktliste=vaktliste, mannskap__isnull=False)
              .select_related('mannskap__korps'))
    # Korps-brukeren ser sine egne (11. sep. 2026). `user=None` er hele
    # lista — for kall som ikke kommer fra et view.
    if user is not None:
        poster = synlige_vaktposter(poster, user)
    # Korpsvelgeren for den som ser alle — viewet sender bare parameteret
    # når brukeren har rett til å velge.
    if korps_id is not None:
        poster = poster_for_korps(poster, korps_id)

    per_person = {}
    for vp in poster:
        per_person.setdefault(vp.mannskap_id, []).append(vp)

    rader = []
    for skift in per_person.values():
        person = skift[0].mannskap
        timer = [_timer(vp.fra_tid, vp.til_tid) for vp in skift]
        hvile = _hviletider(skift)
        # **Probono telles ikke i timene, men i alt annet.** Summen er det
        # organisasjonen betaler for; lengste skift og korteste hvile er
        # hva kroppen tåler, og den skiller ikke på lønn.
        betalt = [t for vp, t in zip(skift, timer) if not vp.probono]
        # Faktisk tid finnes bare for skift som er både møtt og av vakt. Et
        # pågående skift har ingen sluttid å regne mot, og et anslag der
        # ville vært et tall som endrer seg mens man ser på det.
        faktisk = [_timer(vp.mott_at, vp.av_vakt_at) for vp in skift
                   if vp.mott_at and vp.av_vakt_at and not vp.probono]

        overlapp = _overlappstimer(skift)

        rader.append({
            'mannskap_id': person.pk,
            'navn': person.navn,
            'korps_kort': person.korps.kortnavn or person.korps.navn,
            'antall_skift': len(skift),
            'timer': round(sum(betalt), 2),
            'probono_skift': sum(1 for vp in skift if vp.probono),
            'lengste_skift': max(timer) if timer else 0.0,
            'korteste_hvile': min(hvile) if hvile else None,
            'overlapp': overlapp,
            'faktiske_timer': round(sum(faktisk), 2) if faktisk else None,
            # Varslene regnes her og ikke i klienten: grensene ligger i
            # basen, og to steder å sammenligne dem er ett sted for mye.
            'langt_skift': bool(timer) and max(timer) > grenser.maks_skift_timer,
            'kort_hvile': bool(hvile) and min(hvile) < grenser.min_hvile_timer,
            # **Ingen grense å måle mot, og det er riktig.** Et langt skift
            # og en kort hvile er vurderinger — organisasjonen setter hvor
            # grensen går. Et overlapp er en planleggingsfeil: personen kan
            # ikke stå to steder, uansett hva grensene sier.
            'har_overlapp': overlapp > 0,
        })

    rader.sort(key=lambda r: (-r['timer'], norsk_nokkel(r['navn'])))
    return rader


def _dagbolker(skift):
    """Timene per dag, ført på skiftets **startdag**, kronologisk.

    Egen funksjon og ikke en løkke inne i `planleggingstall`, av samme grunn
    som `_hviletider()`: da kan regelen prøves med en liste kalleren *ikke*
    har sortert. Funnet ved mutasjonstesting 15. sep. 2026 — `sorted()` lot
    seg fjerne uten at noe ble rødt, fordi `Vaktpost.Meta.ordering` alt
    sorterer på `fra_tid`, så testene gjennom basen målte modellens ordering
    og ikke hjelperens.

    **Dagen regnes i lokal tid.** `date()` rett på tidspunktet gir UTC, og
    et skift som begynner 00:30 norsk tid ville da havnet på dagen før — i
    vintertid 23:30 UTC, i sommertid 22:30. Feilen er usynlig for alle skift
    som begynner på dagtid, altså de fleste, og viser seg bare på nattskift.

    **Startdagen, ikke splittet ved midnatt** (planleggernotatets beslutning
    7). «fre. 20:00 – lør. 04:00» er åtte timer under fredag. Rapportmodulen
    splitter, og forskjellen er bevisst: splitting endrer ikke en totalsum,
    bare hvilken dag timene føres på — og spørsmålene er ulike.
    """
    dager = {}
    for vp in skift:
        if vp.fra_tid is None:
            continue
        nokkel = timezone.localtime(vp.fra_tid).date().isoformat()
        rad = dager.setdefault(
            nokkel, {'nokkel': nokkel, 'fra_tid': vp.fra_tid.isoformat(),
                     'timer': 0.0})
        rad['timer'] += _timer(vp.fra_tid, vp.til_tid)
    return [{**d, 'timer': round(d['timer'], 2)}
            for d in sorted(dager.values(), key=lambda d: d['nokkel'])]


def planleggingstall(vaktliste):
    """Vaktas budsjett: taket, det som er satt opp, og timene per dag.

    `docs/FORSLAG_PLANLEGGERFANE.md` §6. Svarer på «hvor mye vakt har jeg
    satt opp, og hvor mye er igjen av budsjettet» — ikke på hva det koster
    den enkelte, som er `belastning_per_person`.

    **Hele vakta, aldri filtrert på korps.** Taket gjelder lista, så tallene
    må gjøre det også: et «satt opp» som bare teller ett korps ville stått
    ved siden av et tak for alle, og de to kan ikke sammenlignes. Viewet
    sender derfor bare disse tallene til den som **ser alle korps** — for
    `les` med badge ville summen vært et aggregat over skift hun ikke får
    se, altså avledet innsyn.

    **Tre tall, ikke ett** (beslutning 5 og 9), fordi hvert av dem alene
    lyver litt:

    | Tall | Hva det er | Hvorfor ikke alene |
    |---|---|---|
    | `satt_opp` | Alle plasser, ledige inkludert | Ingen betaler for en tom plass |
    | `bemannet` | Bare plasser med mannskap | Står på null når lista er halvt satt opp |
    | `probono` | Skiftene organisasjonen ikke betaler for | Utelates fra de to over, som i `_sumTimer()` |

    Avstanden mellom `satt_opp` og `bemannet` er dessuten arbeidslista: 312
    mot 244 er 68 timer som mangler folk.

    **`igjen` måles mot `satt_opp`**, ikke mot `bemannet`: planlegging
    handler om behovet, og et budsjett som først fylles når navnene er på
    plass sier «du har alt igjen» på en liste som er ferdig satt opp.

    **Dagslinja fører skiftet på startdagen** (beslutning 7), som
    `_dagnokkel()` i `vaktliste-tegning.js` og resten av vaktlisteflaten.
    Rapportmodulen splitter ved midnatt, og det er en bevisst forskjell:
    splitting endrer ikke en totalsum, bare hvilken dag timene føres på — og
    spørsmålene er ulike. Trenger man time-for-time-bildet, er svaret
    bemanningskurven.

    Dagene har **ingen egne tak**. Et tak per dag ville sperret det man
    faktisk gjør: flytte timer mellom dagene mens totalen står.
    """
    from .models import Vaktpost
    poster = list(Vaktpost.objects.filter(ressurs__vaktliste=vaktliste))

    def _sum(utvalg):
        return round(sum(_timer(vp.fra_tid, vp.til_tid) for vp in utvalg), 2)

    betalte = [vp for vp in poster if not vp.probono]
    satt_opp = _sum(betalte)
    timetak = vaktliste.timetak

    return {
        'timetak': timetak,
        'satt_opp': satt_opp,
        'bemannet': _sum([vp for vp in betalte if vp.mannskap_id is not None]),
        'probono': _sum([vp for vp in poster if vp.probono]),
        # `None` når det ikke er satt noe tak — ikke 0. «0 timer igjen» er en
        # beskjed om at budsjettet er brukt opp; «ingen tak satt» er fraværet
        # av et budsjett, og de to skal ikke se like ut.
        'igjen': None if timetak is None else round(timetak - satt_opp, 2),
        'over_taket': timetak is not None and satt_opp > timetak,
        'dager': _dagbolker(betalte),
    }


def belastning_sammendrag(vaktliste, rader, user=None, korps_id=None):
    """Tallene som står over lista: hvor mange, hvor mye, hvor mange varsler."""
    from .models import Vaktpost
    ledige = Vaktpost.objects.filter(
        ressurs__vaktliste=vaktliste, mannskap__isnull=True)
    if user is not None:
        ledige = synlige_vaktposter(ledige, user)
    if korps_id is not None:
        ledige = poster_for_korps(ledige, korps_id)
    ledige = ledige.count()
    return {
        'personer': len(rader),
        'skift': sum(r['antall_skift'] for r in rader),
        'timer': round(sum(r['timer'] for r in rader), 2),
        'ledige_plasser': ledige,
        'lange_skift': sum(1 for r in rader if r['langt_skift']),
        'korte_hviler': sum(1 for r in rader if r['kort_hvile']),
        # Både timene og hodene: «4 t» sier hvor mye budsjettet er blåst opp,
        # «1 person» sier hvor mange rader man må rette. Ett av dem alene
        # gjør det andre til et regnestykke leseren må gjøre selv.
        'overlapp': round(sum(r['overlapp'] for r in rader), 2),
        'overlappende_personer': sum(1 for r in rader if r['har_overlapp']),
    }
