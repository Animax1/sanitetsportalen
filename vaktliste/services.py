"""Tjenester for vaktlistemodulen.

Reglene som ikke hører hjemme i et view: å lage en planlagt vakt, å kopiere
et oppsett, og å avgjøre hvem som får røre hva.

**Korps-sjekkene bor her, ikke i viewene.** Regelen er skrevet én gang, på
ett sted, og viewene tar den i bruk — det er derfor et endepunkt ikke kan
huske badgen og glemme reservasjonen.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.auth_decorators import er_global_admin, har_tilgang

from . import choices
from .models import Belastningsgrenser, Mannskap, Ressurs, Vaktliste


# ── Vakter som ennå ikke er aktive ───────────────────────────────────────────

def opprett_planlagt_vakt(navn, startet=None, planlagt_slutt=None):
    """Lag en `core.Vakt` som ikke er aktiv, og en tom vaktliste for den.

    **Rører ikke portalens peker.** `AppSetting['aktiv_vakt_id']` står som
    den står — oktobervakta skal kunne planlegges i august uten at pasienter
    og oppdrag plutselig scopes til den. Aktiv vakt byttes der den alltid
    byttes, i vaktadministrasjonen.

    Dette er det andre stedet i portalen som lager `Vakt`-rader (det første
    er «Avslutt vakt» i pasientmodulen). Det er notert som en ryddejobb i
    TODO sammen med `hent_aktiv_vakt` — vaktas livssyklus bør samles i
    `core` når noen er i den koden uansett.

    **Slutten tas imot her, ikke bare i «Innstillinger».** Fram til
    11. sep. 2026 spurte «Ny vaktliste» bare om start, og slutten lå bak
    «Vaktas lengde» inne i innstillingsvinduet — André fant den ikke. Det er
    samme regel som i `vaktliste_detalj_view`: slutten må komme etter
    starten, ellers finnes ikke spennet kurvene tegnes over.

    Returnerer den nye vaktlista.
    """
    from core.models import Vakt

    navn = (navn or '').strip()
    if not navn:
        raise ValueError('Vakta må ha et navn.')
    if Vakt.objects.filter(navn=navn).exists():
        raise ValueError(
            f'En vakt med navnet «{navn}» finnes allerede. '
            f'Legg på en dato eller velg et annet navn.')

    startet = startet or timezone.now()
    if planlagt_slutt is not None and planlagt_slutt <= startet:
        raise ValueError('Vakta må slutte etter at den begynner.')
    with transaction.atomic():
        vakt = Vakt.objects.create(
            navn=navn,
            year=timezone.localtime(startet).year,
            startet=startet,
            er_aktiv=False,
        )
        return Vaktliste.objects.create(vakt=vakt, planlagt_slutt=planlagt_slutt)


# ── Planleggeren: grunnlaget for vaktlista (15. sep. 2026) ───────────────────
#
# André: «Planleggerfanen lar en generere skift og sette de opp på
# enheter/ressurser … tre firemanns lag fra kl 14-22 og en ambulanse fra 15-03
# mens en ambulanse går 8 timer rotasjon. Den skal sette opp planen som lager
# grunnlaget for vaktlisten.»
#
# **Ressursen er subjektet, vinduene hører til den.** Sola 56 får to adskilte
# 12-timersvakter (fre. og lør. 15–03); Haugesund 56 får ett vindu på 48 timer
# delt i åttetimersskift. Var linja enheten og ikke ressursen, ville Sola 56
# blitt til to ulike biler.
#
# **`skiftlengde` er det ene feltet som skiller de to.** Tom betyr ett skift
# som dekker vinduet; et tall deler vinduet i bolker rygg mot rygg.


class Planleggerfeil(ValueError):
    """Noe i oppsettet lar seg ikke generere. Meldingen går til brukeren."""


#: Sperre for hele oppsettet. En generering som lager mer enn
#: dette er ikke et grunnlag, det er et uhell man må rydde opp i for hånd.
MAKS_PLASSER_TOTALT = 2000


def _linjens_skift(linje):
    """Skiftene for **én** ressurs i linja, som ``[(fra, til, plasser), …]``.

    **Ett skiftvindu er ett skift.** Feltet `skiftlengde`, som delte vinduet i
    bolker, er borte (André, 15. sep. 2026: «har vi noe behov for
    skiftlengde?» → nei). Den var en *skjult multiplikator*: den lagde seks
    skift ut av ett vindu, du så dem aldri, og alle seks fikk samme antall
    plasser — altså nettopp det som ikke lot seg uttrykke da plassene ble
    flyttet til vinduet. En rotasjon settes opp som de skiftene den er, og
    «Nytt skiftvindu» begynner der det forrige sluttet.

    **Plassene hører til vinduet, ikke til ressursen** (samme dag: «noen
    ganger ønsker man å ha mindre og mer plasser på enkelte skift visse deler
    av døgnet»). Samleplassen kan da ha seks plasser 14–22 og to 22–06 — det
    er én ressurs med to vinduer, ikke to samleplasser.

    Linja sier *hva* (gruppe, hvor mange enheter), vinduet sier *når og hvor
    mange*. Lå plassene på linja, måtte man opprettet en ressurs til for å
    endre bemanningen om natta.

    Hver ressurs i linja får de samme vinduene — «tre firemanns lag fra 14–22»
    betyr at alle tre går 14–22.
    """
    vinduer = linje.get('vinduer') or []
    if not vinduer:
        raise Planleggerfeil('Hver ressurs må ha minst ett skiftvindu.')
    ut = []
    for vindu in vinduer:
        fra, til = vindu.get('fra'), vindu.get('til')
        if fra is None or til is None or til <= fra:
            raise Planleggerfeil('Skiftvinduet må slutte etter at det begynner.')
        # **Parsingen står her, ikke i viewet.** Viewet gjorde `_int(...) or
        # 1`, og da ble et eksplisitt `0` stille til 1 — en regel som later
        # som den avviser noe. Tomt felt er «én plass», null er en feil.
        raa = vindu.get('plasser')
        if raa in (None, ''):
            plasser = 1
        else:
            try:
                plasser = int(raa)
            except (TypeError, ValueError):
                raise Planleggerfeil(
                    'Antall plasser må være et helt tall.')
        if plasser < 1:
            raise Planleggerfeil('Hvert skiftvindu må ha minst én plass.')
        ut.append((fra, til, plasser))
    return ut


def _nye_plasser(rad):
    """Hvor mange plasser hvert vindu i raden faktisk vil opprette.

    **«Plasser» i planleggeren er vinduets hele bemanning, ikke et påslag.**
    Står det seks 14–22, skal det være seks etterpå — også når to av dem
    allerede har navn på seg. De som står, telles derfor fra, og bare
    differansen lages. Uten det ville en ressurs man redigerte to ganger
    vokst for hver gang, og tallet i feltet sluttet å bety det det sier.

    **Beholdningen forbrukes per vindu** (`igjen`), ikke slås opp på nytt:
    to vinduer med nøyaktig samme tider i samme rad ville ellers begge fått
    trekke fra de samme plassene, og til sammen laget for få.

    Returnerer ``[(fra, til, antall_nye), …]`` i vinduenes rekkefølge.
    """
    igjen = dict(rad.get('beholdt') or {})
    ut = []
    for fra, til, plasser in rad['skift']:
        staar = igjen.get((fra, til), 0)
        brukt = min(staar, plasser)
        igjen[(fra, til)] = staar - brukt
        ut.append((fra, til, plasser - brukt))
    return ut


def _sammendrag(plan):
    """Tallene for en plan: ressurser, plasser og timer, totalt og per rad.

    **Regnes av planen, ikke av basen.** `generer_grunnlag` kalte først
    `forhaandsvis_grunnlag` på nytt etter skrivingen, og da planla den mot den
    *nye* tilstanden: navnene i svaret ble «Lag 4, 5, 6» fordi Lag 1–3 nå sto
    der. Sammendraget skal si hva som ble laget, ikke hva som ville blitt
    laget en gang til.

    **Tallene er endringen, ikke sluttsummen.** `plasser` er de som lages og
    `fjernes` de kladdplassene som ryddes bort — det er de to tallene en
    bekreftelsesdialog må vise. En rad som allerede står slik den skal, viser
    null i begge, og det er riktig svar: ingenting skjer med den.
    """
    def _plasser(rad):
        return sum(nye for _, _, nye in _nye_plasser(rad))

    def _timesum(rad):
        return round(sum(_timer(fra, til) * nye
                         for fra, til, nye in _nye_plasser(rad)), 2)

    return {
        # **Bare de nye ressursene telles.** Raden som peker på en ressurs
        # som alt står, oppretter ingen — «2 ressurser» om en generering som
        # bare flytter tidene på to biler ville vært en løgn om hva som skjer.
        'ressurser': sum(1 for p in plan if p['ressurs'] is None),
        'plasser': sum(_plasser(p) for p in plan),
        'fjernes': sum(p.get('kladd', 0) for p in plan),
        'timer': round(sum(_timesum(p) for p in plan), 2),
        'linjer': [{
            'navn': p['navn'],
            'gruppe': p['gruppe'].navn,
            'finnes': p['ressurs'] is not None,
            'skift': len(p['skift']),
            'plasser': _plasser(p),
            'fjernes': p.get('kladd', 0),
            'timer': _timesum(p),
        } for p in plan],
    }


def forhaandsvis_grunnlag(vaktliste, linjer):
    """Hva en generering ville laget — uten å skrive noe.

    **Samme kode regner ut svaret som den som skriver det** (`_planlegg` og
    `_sammendrag`), og det er hele poenget med at den finnes: en
    forhåndsvisning som regner på egen hånd er en forhåndsvisning som før
    eller siden viser noe annet enn det som skjer.
    """
    return _sammendrag(_planlegg(vaktliste, linjer))


def _beholdt_og_kladd(ressurs):
    """Ressursens plasser delt i to: de som står, og kladden som ryddes bort.

    **Kladden er generatorens eget utkast** (`er_planlagt`): tom, uten korps,
    ikke åpnet for alle. Den kan lages på nytt fra oppsettet, og må kunne det
    — ellers var det ikke mulig å *redusere* et vindu fra seks plasser til
    fire. Alt annet er et løfte til noen: en plass med navn på, en satt av til
    et korps, en åpnet for alle. De står, og telles derfor som beholdt.

    Returnerer ``(beholdt, kladd)`` der `beholdt` er antall per ``(fra, til)``.
    """
    beholdt = {}
    kladd = 0
    for vp in ressurs.vaktposter.all():
        if vp.mannskap_id is None and er_planlagt(vp):
            kladd += 1
            continue
        beholdt[(vp.fra_tid, vp.til_tid)] = beholdt.get(
            (vp.fra_tid, vp.til_tid), 0) + 1
    return beholdt, kladd


def _planlegg(vaktliste, linjer):
    """Oppsettet oversatt til ressurser og skiftvinduer, uten å røre basen.

    Returnerer én rad per ressurs som skal finnes etterpå, med navnet den får,
    vinduene den skal ha, og om den fantes fra før (`ressurs`).

    **En linje med `ressurs_id` redigerer en ressurs som alt står** (André,
    15. sep. 2026: «når en har lagt grunnlag og vil redigere så er det ikke
    lenger i planlegger»). Planleggeren leser oppsettet tilbake fra vaktlista,
    så et andre trykk på «Lag grunnlaget» retter det som ble laget i stedet
    for å lage «Lag 4, 5, 6» ved siden av «Lag 1, 2, 3».

    **Gruppa og navnet følger ressursen, ikke linja.** Å flytte en bil til en
    annen gruppe eller døpe den om er redigering av ressursen og hører hjemme
    i «Rediger ressurs», der sletting og enhetskobling alt ligger. Leste vi
    dem fra linja, ville planleggeren vært en andre vei inn til de samme
    feltene — og den som er to steder kommer i utakt.
    """
    from .models import Ressurs, Ressursgruppe

    if not linjer:
        raise Planleggerfeil('Oppsettet er tomt.')

    grupper = {g.pk: g for g in Ressursgruppe.objects.all()}
    # Navnetelleren må kjenne både det som står i basen og det de tidligere
    # linjene i *denne* innsendingen kommer til å lage — ellers gir to linjer
    # på samme gruppe to ressurser som heter det samme.
    brukte_navn = set(
        Ressurs.objects.filter(vaktliste=vaktliste)
        .values_list('navn', flat=True))
    finnes_i_gruppa = {}
    for gid in grupper:
        finnes_i_gruppa[gid] = Ressurs.objects.filter(
            vaktliste=vaktliste, gruppe_id=gid).count()

    plan = []
    sett_ressurs = set()
    for linje in linjer:
        skift = _linjens_skift(linje)

        ressurs_id = linje.get('ressurs_id')
        if ressurs_id is not None:
            ressurs = Ressurs.objects.filter(
                pk=ressurs_id, vaktliste=vaktliste
            ).select_related('gruppe').first()
            if ressurs is None:
                raise Planleggerfeil(
                    'Ressursen finnes ikke lenger på denne vaktlista.')
            # **Én linje per ressurs.** To linjer på samme ressurs ville latt
            # den andre rydde bort kladden den første nettopp lagde, og
            # resultatet avhengt av rekkefølgen.
            if ressurs.pk in sett_ressurs:
                raise Planleggerfeil(
                    f'«{ressurs.navn}» står to ganger i oppsettet.')
            sett_ressurs.add(ressurs.pk)
            beholdt, kladd = _beholdt_og_kladd(ressurs)
            plan.append({
                'gruppe': ressurs.gruppe,
                'navn': ressurs.navn,
                'skift': skift,
                'ressurs': ressurs,
                'beholdt': beholdt,
                'kladd': kladd,
            })
            continue

        gruppe = grupper.get(linje.get('gruppe_id'))
        if gruppe is None:
            raise Planleggerfeil('Ukjent ressursgruppe.')

        antall = int(linje.get('antall') or 1)
        if antall < 1:
            raise Planleggerfeil('Antall ressurser må være minst én.')

        # **Noen grupper finnes i ett eksemplar.** Samme regel som
        # `ressurser_view`, og den må stå her også: en generator som lager
        # «Samleplass 2» er akkurat den feilen `flere_enheter` finnes for.
        if not gruppe.flere_enheter:
            if antall > 1:
                raise Planleggerfeil(
                    f'«{gruppe.navn}» finnes i ett eksemplar.')
            if finnes_i_gruppa[gruppe.pk]:
                raise Planleggerfeil(
                    f'«{gruppe.navn}» finnes i ett eksemplar, og står '
                    f'allerede på denne vaktlista.')

        for _ in range(antall):
            navn = _neste_navn(gruppe, brukte_navn, finnes_i_gruppa)
            plan.append({
                'gruppe': gruppe,
                'navn': navn,
                'skift': skift,
                'ressurs': None,
                'beholdt': {},
                'kladd': 0,
            })

    # **Grensen måles på det som skal lages**, ikke på tallene i feltene: en
    # rad som allerede står med sine seks plasser lager ingen, og skal ikke
    # telle mot taket hver gang noen retter et klokkeslett.
    totalt = sum(nye for p in plan for _, _, nye in _nye_plasser(p))
    if totalt > MAKS_PLASSER_TOTALT:
        raise Planleggerfeil(
            f'Oppsettet ville laget {totalt} plasser. Grensen er '
            f'{MAKS_PLASSER_TOTALT} — sjekk tidene og antallet.')
    return plan


def _neste_navn(gruppe, brukte_navn, finnes_i_gruppa):
    """«Lag 1», «Lag 2» … det første navnet som ikke er i bruk.

    **Teller forbi hull.** Står «Lag 1» og «Lag 3» fra før, blir den neste
    «Lag 2» og ikke «Lag 4» — nummeret er en etikett, ikke en ID, og et hull
    i rekka er noe man har laget ved å slette noe.

    Grupper som finnes i ett eksemplar får gruppenavnet bart: «Samleplass»,
    ikke «Samleplass 1».
    """
    if not gruppe.flere_enheter:
        navn = gruppe.navn
        brukte_navn.add(navn)
        finnes_i_gruppa[gruppe.pk] = finnes_i_gruppa.get(gruppe.pk, 0) + 1
        return navn
    n = 1
    while f'{gruppe.navn} {n}' in brukte_navn:
        n += 1
    navn = f'{gruppe.navn} {n}'
    brukte_navn.add(navn)
    finnes_i_gruppa[gruppe.pk] = finnes_i_gruppa.get(gruppe.pk, 0) + 1
    return navn


def generer_grunnlag(vaktliste, linjer):
    """Opprett — eller rett opp — ressursene og de tomme plassene oppsettet
    beskriver.

    Dette er planleggerens hele jobb: fra en tom liste til et skjelett som kan
    fordeles og spisses i fanene som alt finnes, og tilbake hit igjen når
    grunnlaget skal rettes.

    **Plassene fødes som planlagt kladd** (notatets beslutning 10): ikke
    reservert til noe korps, ikke åpnet for alle, og dermed usynlig for
    korps-brukerne til lederen deler dem ut. Uten det ser et halvferdig
    oppsett ferdig ut for alle korps i det øyeblikket generatoren kjører —
    samme grunn til at `kopier_oppsett` aldri tar personene med.

    **Bare kladden på de ressursene oppsettet nevner røres** (beslutning 4 og
    11, strammet 15. sep. 2026). Plasser reservert til et korps, plasser åpne
    for alle, og **alle** bemannede står — en tom plass uten reservasjon er
    generatorens eget utkast, en som er delt ut er et løfte til noen. Og en
    ressurs som *ikke* står i oppsettet lar generatoren være i fred: å fjerne
    en ressurs er en sletting, og den hører hjemme bak de to bekreftelsene i
    «Rediger ressurs». Den gamle `erstatt_kladd`-bryteren, som ryddet kladd på
    hele lista, er borte med samme begrunnelse: den rørte ting oppsettet ikke
    nevnte.

    **Ingen `bulk_create`.** Den hopper over auditsignalene, og en generering
    som lager hundre plasser er nettopp stedet noen vil gripe etter den —
    `kopier_oppsett` gikk i den fella 12. sep. 2026.

    **Alt i én `transaction.atomic()`**, fordi slettingen kommer før
    skrivingen: en feil halvveis ville ellers etterlatt lista tommere enn før
    man trykket.

    Returnerer det samme som `forhaandsvis_grunnlag`, pluss `slettet`.
    """
    from .models import Ressurs, Vaktpost

    plan = _planlegg(vaktliste, linjer)
    slettet = 0
    with transaction.atomic():
        for rad in plan:
            ressurs = rad['ressurs']
            if ressurs is None:
                ressurs = Ressurs.objects.create(
                    vaktliste=vaktliste,
                    navn=rad['navn'],
                    gruppe=rad['gruppe'],
                    rekkefolge=neste_rekkefolge(vaktliste),
                )
            else:
                for vp in ressurs.vaktposter.all():
                    if vp.mannskap_id is None and er_planlagt(vp):
                        vp.delete()
                        slettet += 1
            for fra, til, nye in _nye_plasser(rad):
                for _ in range(nye):
                    Vaktpost.objects.create(
                        ressurs=ressurs, fra_tid=fra, til_tid=til)

    svar = _sammendrag(plan)
    svar['slettet'] = slettet
    return svar


def neste_rekkefolge(vaktliste) -> int:
    """Neste ledige fanerekkefølge på lista — altså «sist».

    `Ressurs.rekkefolge` er det ene stedet i modulen der rekkefølgen *betyr*
    noe: den styrer fanene på planleggingssiden, og alfabetisk ville stokket
    om på den operative rekkefølgen (samleplass, biler, lag, KO blir
    «Ambulanse, KO, Lag 1, Mannskapsbil 1»).

    Men brukeren skal ikke skrive et tall. Den som bygger vakta legger inn
    ressursene i den rekkefølgen hun tenker på dem, og det er den rekkefølgen
    fanene skal ha. Steget på 10 gir plass til å skyte inn en ressurs mellom
    to andre den dagen noen vil kunne omorganisere.
    """
    fra_for = (vaktliste.ressurser
               .order_by('-rekkefolge')
               .values_list('rekkefolge', flat=True)
               .first())
    return (fra_for or 0) + 10


def neste_grupperekkefolge() -> int:
    """Neste ledige rekkefølge for en ressursgruppe — «sist», altså.

    Samme grep som `neste_rekkefolge`, men globalt: gruppene er ikke knyttet
    til én vaktliste. Den som legger til «Førstehjelpstelt» skal ikke måtte
    finne på et tall, og en ny gruppe hører naturlig sist.
    """
    from .models import Ressursgruppe
    hoyest = (Ressursgruppe.objects
              .order_by('-rekkefolge')
              .values_list('rekkefolge', flat=True)
              .first())
    return (hoyest or 0) + 10


def kopier_oppsett(fra_vaktliste, til_vaktliste):
    """Kopier ressursene — med gruppe, reservasjon, enhet og rekkefølge —
    og timetaket.

    **Aldri personene.** Å kopiere folk ville satt dem opp på en vakt de ikke
    har sagt ja til, og en liste ingen har sagt ja til er verre enn en tom
    liste: den ser ferdig ut.

    **Taket følger med** (15. sep. 2026, planleggernotatets beslutning 6).
    Det ligger nærmere ressursene enn personene: det er en egenskap ved
    *arrangementet* man setter opp på nytt. Og det er ufarlig å ta feil her,
    i motsetning til personene — et tak som følger med og ikke stemmer gir et
    gult varsel man retter på fem sekunder, mens et navn på en vakt ingen har
    sagt ja til er en liste som ser ferdig ut.

    Returnerer antall kopierte ressurser.
    """
    # Én `create` per rad, ikke `bulk_create`: den hopper over signalene, og
    # da ble ikke kopiene auditlogget (12. sep. 2026). En vakt har en håndfull
    # ressurser, så spørringene koster ingenting.
    antall = 0
    for r in fra_vaktliste.ressurser.all():
        Ressurs.objects.create(
            vaktliste=til_vaktliste,
            navn=r.navn,
            gruppe_id=r.gruppe_id,
            korps=r.korps,
            enhet=r.enhet,
            rekkefolge=r.rekkefolge,
        )
        antall += 1
    # Skrives bare når det finnes noe å skrive: en `save()` uten endring
    # ville laget en auditrad om at ingenting skjedde.
    if fra_vaktliste.timetak is not None:
        til_vaktliste.timetak = fra_vaktliste.timetak
        til_vaktliste.save(update_fields=['timetak'])
    return antall


# ── Kompetansestigen ─────────────────────────────────────────────────────────
#
# `Kompetanse.bygger_paa` peker på det kurset denne overordner: AFØR bygger på
# VFØR, som bygger på GFØR. Reglene under er de to som trengs for at pekeren
# skal bety noe — én for visning, én for å hindre at stigen blir en ring.


def _foreldrekjede(kompetanse_id, foreldre, _sett=None):
    """Alle IDene over `kompetanse_id` i stigen, transitivt.

    `foreldre` er ``{id: bygger_paa_id}`` for hele registeret, slått opp én
    gang av kalleren — en spørring per kompetanse ville gitt N+1 på en liste
    med hundre mannskaper.

    `_sett` stopper en ring. Ringer skal ikke kunne oppstå (`lager_sykel`
    hindrer dem ved skriving), men en gammel rad eller en manuell endring i
    basen skal gi en avkortet kjede, ikke en evig løkke.
    """
    _sett = _sett if _sett is not None else set()
    forelder = foreldre.get(kompetanse_id)
    if forelder is None or forelder in _sett:
        return _sett
    _sett.add(forelder)
    return _foreldrekjede(forelder, foreldre, _sett)


def synlige_kompetanser(kompetanser, foreldre):
    """De kompetansene som ikke overordnes av en annen personen har.

    Har hun AFØR, VFØR og Sykepleier, står hun igjen med AFØR og Sykepleier:
    VFØR er implisert, og Sykepleier er ikke i den stigen i det hele tatt.

    `kompetanser` er radene personen har; `foreldre` er kartet fra
    `foreldrekart()`. Rekkefølgen bevares.
    """
    holdt = {k.pk for k in kompetanser}
    implisert = set()
    for pk in holdt:
        implisert |= _foreldrekjede(pk, foreldre)
    return [k for k in kompetanser if k.pk not in implisert]


def foreldrekart():
    """``{id: bygger_paa_id}`` for hele kompetanseregisteret.

    Slås opp én gang per forespørsel og sendes med til `synlige_kompetanser`.
    """
    from .models import Kompetanse
    return dict(Kompetanse.objects.values_list('pk', 'bygger_paa_id'))


def lager_sykel(kompetanse_id, nytt_forelder_id) -> bool:
    """True hvis pekeren ville laget en ring i stigen.

    «A bygger på B, B bygger på A» har ikke noe svar på hvilken som er
    øverst, og ville gjort `synlige_kompetanser` til en smakssak. Det stoppes
    ved skriving framfor å håndteres ved lesing: en ring i basen er en feil
    som ikke skal kunne oppstå, ikke en tilstand koden skal tåle.
    """
    if nytt_forelder_id is None:
        return False
    if nytt_forelder_id == kompetanse_id:
        return True
    return kompetanse_id in _foreldrekjede(nytt_forelder_id, foreldrekart())


# ── Hvem får røre hva ────────────────────────────────────────────────────────
#
# Håndheves fra fase 3, på hvert endepunkt. Fire nivåer av «hvem»:
#
#   kan_lede            — `skriv_leder`/admin. Setter opp selve vakta.
#   kan_skrive_alt      — `skriv_full`/admin. Blander korps fritt, deler ut
#                         ressurser, styrer verdimengdene.
#   kan_*_korps/…       — `skriv_handling` avgrenset av badgen.
#   (ingenting)         — `les` skriver ikke.
#
# **`les` gjelder hele lista med vilje.** Poenget med en vaktliste er
# samordning på tvers av korps; den som ikke skal se andre korps, skal ikke ha
# modulen (§4.4).

def kan_skrive_alt(user) -> bool:
    """`skriv_full` eller høyere — står utenfor badge og reservasjon.

    Samlet her framfor å gjentas i hvert view: det er terskelen for alt som
    gjelder *vakta* framfor *et korps* — å bemanne på tvers, å dele ut
    ressurser, og å styre `Korps`/`Kompetanse`.

    Stigen er ordnet, så `skriv_leder` er sant her også. Det er meningen:
    lederen gjør alt bemanneren gjør, og litt til.
    """
    return er_global_admin(user) or har_tilgang(user, 'vaktliste', 'skriv_full')


def kan_lede(user) -> bool:
    """`skriv_leder` eller global admin — den som *setter opp* vakta.

    **Skillet mot `kan_skrive_alt` er hva slags skade en feil gjør** (30. aug.
    2026). Bemanneren setter folk på plasser: retter hun noe galt, retter hun
    det tilbake. Lederen oppretter og fjerner ressurser og vaktlister, endrer
    vaktas lengde og lager roller og grupper — og en fjernet ressurs tar
    bemanningen med seg. Det er ikke en handling man angrer.

    Terskelen er ikke global admin, og det er poenget med å ha nivået i det
    hele tatt: en vaktleder skal kunne sette opp sin egen vaktliste uten å få
    brukeradministrasjon, backup og arkiv på kjøpet.
    """
    return er_global_admin(user) or har_tilgang(user, 'vaktliste', 'skriv_leder')


def kan_stemple(user) -> bool:
    """Får brukeren stemple møtt og av vakt?

    **Avklaring 11.3 sa nei til `skriv_handling`,** og det er hele grunnen
    til at regelen har et eget navn. Korps-føreren fører sitt eget korps —
    hun setter dem opp, flytter dem og retter tidene deres. Men innsjekk er
    noe annet: «Tilstede nå» er brannsikkerhet på et sted med overnatting,
    og det tallet skal ha én ansvarlig, ikke ett per korps.

    Terskelen er den samme som `kan_skrive_alt`, og funksjonen er derfor et
    kall videre. Den finnes likevel: leter noen etter «hvem sjekker folk
    inn», skal de finne beslutningen og ikke bare terskelen — og skulle den
    en dag åpnes for korpsføreren, er det ett sted å endre.
    """
    return kan_skrive_alt(user)


#: Stemplingene, som **data**. Hver overgang sier hvilket felt den rører,
#: om den setter eller fjerner et tidspunkt, og hva som må være sant fra før.
#:
#: Samme grep som `oppdrag.services.OVERGANGER`, og av samme grunn: skrevet
#: som `if`-er i viewet vokser de til en trapp der bare den som skrev den
#: siste grenen vet hva de andre gjør.
#:
#: **Forutsetningene er ikke pedanteri.** «Av vakt» uten «møtt» gir en rad
#: som sier at noen gikk av en vakt hun aldri kom til, og `er_tilstede`
#: leser nettopp de to feltene sammen. Å angre «møtt» mens «av vakt» står,
#: gir samme rad. Begge stenges her, ett sted.
STEMPLINGER = {
    'mott': {
        'felt': 'mott_at', 'setter': True,
        'krever_tomt': (),
        'krever_satt': (),
        'nekt': 'Personen er alt registrert møtt.',
    },
    'av_vakt': {
        'felt': 'av_vakt_at', 'setter': True,
        'krever_tomt': (),
        'krever_satt': ('mott_at',),
        'nekt': 'Personen må registreres møtt før hun kan gå av vakt.',
    },
    'angre_mott': {
        'felt': 'mott_at', 'setter': False,
        'krever_tomt': ('av_vakt_at',),
        'krever_satt': ('mott_at',),
        'nekt': 'Angre «av vakt» først — ellers står raden igjen som '
                'avgått uten å ha møtt.',
    },
    'angre_av_vakt': {
        'felt': 'av_vakt_at', 'setter': False,
        'krever_tomt': (),
        'krever_satt': ('av_vakt_at',),
        'nekt': 'Personen står ikke som av vakt.',
    },
}


#: Klienttid eldre enn dette forkastes — en stempling som har ligget i køen
#: et døgn er ikke lenger et tidspunkt man kan stole på.
KLIENTTID_MAKS_ALDER_SEK = 24 * 3600
#: Litt slingringsmonn framover: PC-klokker går feil med sekunder, ikke timer.
KLIENTTID_MAKS_FRAMTID_SEK = 120


def vurder_klienttid(klienttid, naa=None):
    """Tidspunktet en stempling skal få (offline drift, 13. sep. 2026).

    Drifts-PC-en legger møtt/av vakt i kø når serveren ikke svarer, og sender
    dem når den svarer igjen. Da er det trykket som er hendelsen, ikke
    mottaket: Kari møtte 08:04, ikke 09:30 da nettet kom tilbake. Klienttiden
    brukes derfor når den er rimelig — ikke i framtiden ut over
    klokkeslingring, ikke eldre enn et døgn — og ellers servertid. Samme
    regel som bilens stemplinger i oppdragsmodulen, uten `forsinket`-flagget:
    vaktlista har ikke et felt å bære det i, og avviket ses av auditloggen.
    """
    naa = naa or timezone.now()
    if klienttid is None:
        return naa
    if timezone.is_naive(klienttid):
        klienttid = timezone.make_aware(klienttid)
    avstand = (naa - klienttid).total_seconds()
    if avstand < -KLIENTTID_MAKS_FRAMTID_SEK or avstand > KLIENTTID_MAKS_ALDER_SEK:
        return naa
    return min(klienttid, naa)


def stemple(vaktpost, handling, naa=None):
    """Utfør én navngitt stempling. Returnerer ``(ok, feilmelding)``.

    Skriver ikke til basen — den som kaller lagrer. Da kan regelen testes
    uten en rad, og viewet eier transaksjonen.

    **En ledig plass kan ikke stemples.** Den har ingen som kan ha møtt, og
    `er_tilstede` krever en person nettopp derfor.
    """
    regel = STEMPLINGER.get(handling)
    if regel is None:
        return False, f'Ukjent stempling «{handling}».'
    if vaktpost.mannskap_id is None:
        return False, 'Plassen er ledig — det er ingen å registrere.'

    for felt in regel['krever_satt']:
        if getattr(vaktpost, felt) is None:
            return False, regel['nekt']
    for felt in regel['krever_tomt']:
        if getattr(vaktpost, felt) is not None:
            return False, regel['nekt']

    # Å sette et stempel som alt står er ikke en feil verdt å stoppe for —
    # to trykk på samme knapp skal gi samme rad, ikke en rød boks. Men
    # tidspunktet skal ikke flytte seg: det første er det som skjedde.
    if regel['setter'] and getattr(vaktpost, regel['felt']) is not None:
        return True, ''

    setattr(vaktpost, regel['felt'],
            (naa or timezone.now()) if regel['setter'] else None)
    return True, ''


def brukerens_korps(user):
    """Korpset kontoen arver fra mannskapsraden sin, eller ``None``.

    Badgen (§4). Koblingen `Mannskap.user` gir i seg selv ingen tilgang —
    den sier bare hvem du er, som `Enhet.user` i oppdragsmodulen.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    mannskap = Mannskap.objects.filter(user=user).select_related('korps').first()
    return mannskap.korps if mannskap else None


def ser_alle_korps(user) -> bool:
    """Ser brukeren alle korps på `/vaktliste/`, eller bare sitt eget?

    11. sep. 2026 så korps-føreren (`skriv_handling`) bare sitt eget korps.
    Snudd 12. sep.: «Endre skrive: eget korps til å inkludere lese: alle
    korps.» Fra `les_alle` og oppover ser man alle; bare `les` ser sitt
    eget. **Å se er ikke å redigere** — korps-føreren redigerer fortsatt bare
    eget korps (`kan_fore_korps`), og nedtrekkene tilbyr bare hennes folk
    (`mannskap_brukeren_kan_sette`). Global admin ser alt.

    Gjelder bare `/vaktliste/`. Sentralbordets besetning i oppdragsmodulen
    er uendret: den er gatet på `les` i vaktlista og viser bilens folk
    uansett korps — der er spørsmålet «er bilen klar», ikke «hvem er mine».
    """
    from core.auth_decorators import nivaa_for
    if kan_skrive_alt(user):
        return True
    return nivaa_for(user, 'vaktliste') in ('les_alle', 'skriv_handling')


def poster_for_korps(qs, korps_id):
    """Skiftene som hører til ett korps: personene med badgen, **og de ledige
    plassene satt av til det** — via plassen eller via ressursen, samme
    sammenslåing som `reservert_korps()`. Én regel, to lesere: korpsfilteret
    for korps-brukeren, og korpsvelgeren for den som ser alle."""
    from django.db.models import Q
    return qs.filter(
        Q(mannskap__korps_id=korps_id)
        | Q(mannskap__isnull=True, korps_id=korps_id)
        | Q(mannskap__isnull=True, korps__isnull=True, ressurs__korps_id=korps_id)
        # Tildelt alle korps: hennes å fylle, altså hennes å se.
        | Q(mannskap__isnull=True, alle_korps=True))


def synlige_vaktposter(qs, user):
    """Skiftene brukeren får se: alle, eller bare sitt eget korps.

    For korps-brukeren: personene i hennes korps, **og de ledige plassene som
    er satt av til det** — via plassen eller via ressursen, samme
    sammenslåing som `reservert_korps()`. En ledig plass hun kan fylle må
    hun kunne se. Uten badge finnes intet korps, og lista er tom —
    fail-closed, som skrivingen.
    """
    if ser_alle_korps(user):
        return qs
    korps = brukerens_korps(user)
    if korps is None:
        return qs.none()
    return poster_for_korps(qs, korps.pk)


def synlig_mannskap(qs, user):
    """Registeret slik brukeren får se det: alle, eller bare sitt eget korps."""
    if ser_alle_korps(user):
        return qs
    korps = brukerens_korps(user)
    return qs.filter(korps=korps) if korps is not None else qs.none()


def kan_fore_korps(user, korps_id) -> bool:
    """Får brukeren føre folk i dette korpset?

    Grunnregelen begge mannskapssjekkene hviler på. `skriv_full` og global
    admin: alle korps. `skriv_handling`: kun sitt eget. Uten mannskapsrad har
    kontoen ingen badge og kan ikke skrive noe — fail-closed, samme form som
    en enhetskonto uten enhet.
    """
    if kan_skrive_alt(user):
        return True
    if not har_tilgang(user, 'vaktliste', 'skriv_handling'):
        return False
    korps = brukerens_korps(user)
    return korps is not None and korps_id == korps.pk


def mannskap_brukeren_kan_sette(user):
    """Personene brukeren får sette på en plass — for nedtrekkene. Speiler
    `kan_redigere_mannskap`: alle for den som skriver alt, eget korps for
    korps-føreren, ingen uten badge."""
    qs = Mannskap.objects.filter(er_aktiv=True).select_related('korps')
    if kan_skrive_alt(user):
        return qs
    korps = brukerens_korps(user)
    if korps is None or not har_tilgang(user, 'vaktliste', 'skriv_handling'):
        return qs.none()
    return qs.filter(korps=korps)


def kan_redigere_mannskap(user, mannskap) -> bool:
    """Får brukeren redigere denne personen? Avgjøres av personens korps."""
    return kan_fore_korps(user, mannskap.korps_id)


def kan_flytte_mannskap(user, mannskap, nytt_korps_id) -> bool:
    """Får brukeren flytte personen til et annet korps?

    **Begge korpsene teller.** Sjekket vi bare det personen har i dag, kunne
    korps-brukeren flytte sine egne folk ut i et hvilket som helst annet
    korps; sjekket vi bare målet, kunne hun hente inn andres. Det er samme
    feilform som den doble regelen i `kan_sette_vaktpost` — og siden
    `skriv_handling` per definisjon bare har ett korps, betyr det i praksis at
    hun ikke flytter noen i det hele tatt. Flytting er `skriv_full`.
    """
    return (kan_fore_korps(user, mannskap.korps_id)
            and kan_fore_korps(user, nytt_korps_id))


def kan_bemanne_ressurs(user, ressurs) -> bool:
    """Får brukeren sette folk på denne ressursen?

    Regelen er dobbel (§4.2), og dette er den ene halvdelen: ressursen må
    være reservert brukerens korps. En **ureservert** ressurs er ikke et
    fristed — den er `skriv_full`/admins bord, typisk KO og samleplass.
    """
    if kan_skrive_alt(user):
        return True
    if not har_tilgang(user, 'vaktliste', 'skriv_handling'):
        return False
    korps = brukerens_korps(user)
    return (korps is not None
            and ressurs.korps_id is not None
            and ressurs.korps_id == korps.pk)


def er_planlagt(vaktpost) -> bool:
    """En **planlagt** plass er lederens kladd (André, 12. sep. 2026): ikke
    satt av til noe korps, og ikke åpnet for alle. Korps-brukerne ser den
    ikke. Den går én vei — til et korps, eller til «åpen for alle» (alle ser og
    kan fylle) — og aldri tilbake."""
    return not vaktpost.alle_korps and reservert_korps(vaktpost=vaktpost) is None


def reservert_korps(vaktpost=None, ressurs=None):
    """Hvilket korps er denne plassen satt av til?

    **Ett sted, fordi reservasjonen finnes på to nivåer.** `Ressurs.korps` er
    standarden — hele bilen er HGSDs. `Vaktpost.korps` overstyrer den for én
    plass, og finnes fordi en samleplass bemannes av flere korps.

    Leses de to hver for seg ute i endepunktene, vil ett av dem før eller
    siden huske ressursen og glemme plassen — og da er en plass satt av til
    Karmøy plutselig HGSDs igjen.
    """
    if vaktpost is not None and vaktpost.korps_id is not None:
        return vaktpost.korps_id
    if vaktpost is not None:
        return vaktpost.ressurs.korps_id
    return ressurs.korps_id if ressurs is not None else None


def kan_bemanne_plass(user, ressurs, vaktpost=None) -> bool:
    """Reservasjonshalvdelen, lest fra plassen når den har sin egen.

    `kan_bemanne_ressurs` svarer på ressursnivået og brukes fortsatt der det
    er ressursen som er spørsmålet (å dele den ut, å fjerne den). Denne
    svarer på plassen, og er den som gjelder når man bemanner.
    """
    if kan_skrive_alt(user):
        return True
    # **Tildelt alle korps** (11. sep. 2026): enhver korps-bruker med badge
    # får fylle den. Badgen kreves fortsatt — uten korps finnes ingen
    # person å sette inn, og ingen å avgrense til.
    if vaktpost is not None and vaktpost.alle_korps:
        return (har_tilgang(user, 'vaktliste', 'skriv_handling')
                and brukerens_korps(user) is not None)
    korps_id = reservert_korps(vaktpost=vaktpost, ressurs=ressurs)
    return kan_fore_korps(user, korps_id)


def kan_sette_vaktpost(user, ressurs, mannskap, vaktpost=None) -> bool:
    """Begge halvdelene av regelen: badgen på personen, og reservasjonen.

    Skrevet som én funksjon slik at et endepunkt ikke kan huske den ene og
    glemme den andre.

    **`mannskap=None` er en ledig plass, og den er `skriv_full`.** Å opprette
    et behov — «Lag 1 trenger fire, én av dem lagleder» — er å planlegge
    vakta, ikke å føre sitt eget korps. Korps-brukeren *fyller* plassene som
    er satt av til henne; hun bestemmer ikke hvor mange det skal være. Uten
    dette unntaket ville badge-halvdelen ikke hatt noe å sjekke mot, og
    regelen falt åpen på nøyaktig det tilfellet som er nytt.
    """
    # **Egen person på andres plass (André, 12. sep. 2026).** Står en av
    # korpsets egne på en plass satt av til et annet korps, er raden
    # korpsets så lenge personen står der: hun kan byttes mot en annen av
    # egne, eller tas ut så plassen blir ledig igjen. Reservasjonen sier
    # hvem som får *fylle* en tom plass — ikke hvem som får rydde opp i sin
    # egen bemanning.
    egen_staar_der = (vaktpost is not None and vaktpost.mannskap_id is not None
                      and kan_redigere_mannskap(user, vaktpost.mannskap))
    if mannskap is None:
        return egen_staar_der or kan_skrive_alt(user)
    if egen_staar_der and kan_redigere_mannskap(user, mannskap):
        return True
    return (kan_bemanne_plass(user, ressurs, vaktpost)
            and kan_redigere_mannskap(user, mannskap))


def kan_rore_vaktpost(user, vaktpost) -> bool:
    """Får brukeren redigere denne raden slik den står?

    **Et annet spørsmål enn `kan_sette_vaktpost`,** og det er verdt å holde
    dem fra hverandre:

    - `kan_sette_vaktpost(bruker, ressurs, person)` spør om *paret* kan
      opprettes. Med `person=None` er det å opprette et behov — `skriv_full`.
    - `kan_rore_vaktpost(bruker, rad)` spør om brukeren i det hele tatt får
      ta i raden. En **ledig** plass på hennes egen ressurs skal hun få ta i,
      for det er nettopp den hun skal fylle.

    Ble den første brukt til begge, låste den korps-brukeren ute av akkurat
    de plassene som var satt av til henne — funnet av
    `LedigPlassTilgangTests`.
    """
    # **En fylt rad følger personen, en tom følger reservasjonen** (12. sep.
    # 2026). Egen person på andres plass er egen rad; andres person på egen
    # ressurs er deres. Se `kan_sette_vaktpost`.
    if vaktpost.mannskap_id is not None:
        return kan_redigere_mannskap(user, vaktpost.mannskap)
    return kan_bemanne_plass(user, vaktpost.ressurs, vaktpost)


#: Feltene på et skift som **setter det opp**, framfor å bemanne det.
#:
#: André, 15. sep. 2026: «Det eneste de skal få lov til er å legge inn folk,
#: rolle, og redigere ressursens navn — men ikke gruppe, reservering, enhet i
#: oppdragsmodulen og sletting.» Tidene er vaktas rammer for én plass;
#: `probono` og `merknad` er utsagn om hva skiftet *er*, ikke om hvem som står
#: der. Reservasjonen og «åpen for alle» er å dele ut, og sto her fra før —
#: de to var bare skrevet som hver sin `if` ute i viewet.
#:
#: **`antall` er med fordi opprettelsen tar den:** én forespørsel kunne lage
#: femti tomme plasser, og å sette opp behovet er nettopp det korps-føreren
#: ikke skal gjøre.
SKIFT_OPPSETTFELTER = ('fra_tid', 'til_tid', 'korps_id', 'alle_korps',
                       'probono', 'merknad', 'antall')

#: Det samme på en ressurs. **Navnet står bevisst ikke her:** det er det ene
#: korps-føreren skal kunne rette, og reservasjonen, gruppa og
#: enhetskoblingen er det hun ikke skal røre.
RESSURS_OPPSETTFELTER = ('gruppe_id', 'korps_id', 'enhet_id', 'rekkefolge')


def oppsettfelter(data, felter) -> list[str]:
    """Hvilke av `felter` står i denne forespørselen?

    **Egen funksjon, og listene er konstanter, fordi begge har to lesere** —
    opprettelsen og redigeringen av et skift, PUT og DELETE på en ressurs.
    Spurte hvert endepunkt for seg med sine egne `if`-er, ville det ene før
    eller siden husket tidene og glemt `probono`. Det er samme grunn til at
    `reservert_korps()` og `kan_sette_vaktpost()` finnes: en regel med to
    lesere skrives én gang.

    Ikke `data.keys() & set(felter)` — rekkefølgen er listas, så feilmeldingen
    nevner feltene i samme rekkefølge hver gang.
    """
    return [f for f in felter if f in data]


def kan_sette_opp_skift(user) -> bool:
    """Får brukeren opprette et skift, flytte tidene, eller dele plassen ut?

    Et kall videre til `kan_skrive_alt`, og det finnes for at beslutningen
    skal ha et sted å bo — som `kan_stemple`. Skillet er det samme som ellers
    i modulen: **å bemanne er å fylle en plass noen andre har satt opp.** Den
    som fører sitt eget korps setter hvem og i hvilken rolle; tidene, hvor
    mange plasser det er, og hvem de er satt av til, er vaktas rammer.

    Fram til 15. sep. 2026 sa dokumentasjonen dette («å opprette en ledig
    plass er `skriv_full`»), mens koden bare sjekket `kan_sette_vaktpost` —
    altså badgen. En korps-fører kunne opprette skift med frie tidspunkt og
    femti tomme plasser på sin egen ressurs, og flytte tidene på dem som sto.
    """
    return kan_skrive_alt(user)


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
    # dermed null uansett. Det som *må* stå her er vakten mot `spenn[0]` på
    # en tom liste. (Mutasjonsprøvd 15. sep. 2026: `< 1` overlever fordi den
    # er ekvivalent, `< 0` gir IndexError og fanges.)
    if len(spenn) < 2:
        return 0.0
    sekunder = sum((til - fra).total_seconds() for fra, til in spenn)
    # Unionen: slå sammen spenn som berører hverandre, og legg sammen
    # lengdene av de sammenslåtte.
    union = 0.0
    start, slutt = spenn[0]
    for fra, til in spenn[1:]:
        # `>` og `>=` gir samme sum her — berører spennene hverandre nøyaktig,
        # blir de enten ett segment eller to som til sammen er like lange.
        # Mutanten overlever, og den er ekvivalent, ikke et hull i testene.
        if fra > slutt:
            union += (slutt - start).total_seconds()
            start, slutt = fra, til
        else:
            slutt = max(slutt, til)
    union += (slutt - start).total_seconds()
    return round((sekunder - union) / 3600, 2)


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

    rader.sort(key=lambda r: (-r['timer'], r['navn'].lower()))
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


def besetning(enhet_id, naa=None):
    """Hvem som er på bilen nå — navn, rolle og innsjekkstatus.

    Sentralbordets spørsmål er **«er bilen bemannet?»**, ikke «hvem har vakt i
    løpet av helga». Derfor bare skiftene som dekker tidspunktet: en liste med
    tretti rader over to døgn svarer ikke på noe man kan handle på.

    **Telefon og ISSI er med, kompetanseliste og `notat` er det ikke** (§6,
    snudd for telefon 12. sep. 2026 — André: «på koblede enheter i /oppdrag
    skal det vises telefon nummer og ISSI for hver person som er på
    enheten»). Sentralbordet skal kunne ringe bilen på nødnett eller mobil
    uten å åpne vaktlista; personalmappa skal det fortsatt ikke lese.

    Returnerer ``None`` hvis enheten ikke er koblet til en ressurs i vakta.
    Det er noe annet enn «ingen på vakt», og de to skal ikke se like ut:
    ubemannet er et problem, ukoblet er et oppsett som mangler.

    **Lista i drift vinner** (André, 12. sep. 2026: «koblingen fungerer
    ikke»). Scopet var portalens aktive vakt alene, og da fant sentralbordet
    ingenting når vaktlista som faktisk kjørte lå på en annen vakt. Er en
    liste satt i drift med bilen koblet, er det den som gjelder; ellers den
    aktive vaktas. Og dekker ingen skift akkurat nå, sendes **neste skift**
    med, så svaret er «ingen nå, Kari og Ola fra 16:00» og ikke bare «ingen».
    """
    from core.vakt import hent_aktiv_vakt
    from .models import Vaktpost

    naa = naa or timezone.now()
    vakt = hent_aktiv_vakt()

    kandidater = (Ressurs.objects
                  .filter(enhet_id=enhet_id)
                  .select_related('vaktliste__vakt'))
    ressurs = (kandidater.filter(vaktliste__status=choices.DRIFT).first()
               or (kandidater.filter(vaktliste__vakt=vakt).first() if vakt else None))
    if ressurs is None:
        return None

    def _rad(vp):
        return {
            'navn': vp.mannskap.navn,
            'rolle': vp.rolle.navn if vp.rolle else '',
            'telefon': vp.mannskap.telefon,
            'issi': vp.mannskap.issi,
            'tilstede': vp.er_tilstede,
            'mott': vp.mott_at is not None,
        }

    bemannede = (Vaktpost.objects
                 .filter(ressurs=ressurs, mannskap__isnull=False)
                 .select_related('mannskap', 'rolle'))
    poster = bemannede.filter(fra_tid__lte=naa, til_tid__gte=naa).order_by('mannskap__navn')
    mannskap = [_rad(vp) for vp in poster]

    neste, neste_fra = [], None
    if not mannskap:
        forste = bemannede.filter(fra_tid__gt=naa).order_by('fra_tid').first()
        if forste is not None:
            neste_fra = forste.fra_tid
            neste = [_rad(vp) for vp in
                     bemannede.filter(fra_tid=neste_fra).order_by('mannskap__navn')]

    # **De som er i bilen først.** Operatørens spørsmål er «hvem har jeg», og
    # da skal svaret stå øverst; de som mangler er den andre halvdelen av
    # samme liste.
    #
    # Sorteringen skjer **i Python**, ikke i basen, av to grunner: `tilstede`
    # er en utledet egenskap uten kolonne å sortere på, og `rolle__navn` er
    # nullbar — og SQLite (dev) og PostgreSQL (prod) plasserer NULL i hver sin
    # ende. En besetningsliste som står i ulik rekkefølge lokalt og i drift er
    # en feil man aldri ser før den betyr noe.
    mannskap.sort(key=lambda m: (not m['tilstede'], m['navn'].lower()))

    return {
        'ressurs_navn': ressurs.navn,
        'vaktliste_navn': ressurs.vaktliste.vakt.navn,
        'i_drift': ressurs.vaktliste.i_drift,
        'mannskap': mannskap,
        # Neste skift når ingen dekker nå — navn og klokkeslett, ikke et tomt svar.
        'neste': neste,
        'neste_fra': neste_fra.isoformat() if neste_fra else None,
        'antall': len(mannskap),
        # **Tilstede utledes av stemplene** (`Vaktpost.er_tilstede`), aldri av
        # en lagret status. Er lista ikke i drift, er ingen stemplet — og da
        # er tallet 0 med rette: innsjekken har ikke åpnet.
        'tilstede': sum(1 for m in mannskap if m['tilstede']),
    }


def koblet_i_annen_vakt(enhet_id):
    """Navnet på en vakt der enheten *er* koblet, men som ikke er den aktive.

    Finnes for at feilmeldingen skal kunne si sannheten. «Ikke koblet til en
    ressurs i denne vakta» leses som «koblingen din er ødelagt» — og André
    brukte en kveld på å lete etter en feil som ikke fantes, fordi han hadde
    planlagt oktobervakta i august og koblet bilene der.

    Spørringen kjøres **bare** når `besetning()` alt har svart nei, så den
    koster ingenting i det vanlige tilfellet — og av samme grunn trengs ingen
    `exclude()` på den aktive vakta: har den en ressurs for enheten, kom vi
    aldri hit. Nyeste vakt først, fordi det er den man planla sist.
    """
    ressurs = (Ressurs.objects
               .filter(enhet_id=enhet_id)
               .select_related('vaktliste__vakt')
               .order_by('-vaktliste__vakt__startet')
               .first())
    return ressurs.vaktliste.vakt.navn if ressurs else None


def vaktspenn(vaktliste):
    """(start, slutt) for vakta — eller ``(None, None)`` hvis den mangler.

    Starten er `Vakt.startet`; slutten er `Vaktliste.planlagt_slutt`. Se
    modellkommentaren for hvorfor de to ikke bor samme sted.

    Brukes av bemanningskurven, som skal tegnes over **hele** vakta: leste
    den bare skiftene, ville hullet i begynnelsen vært usynlig nettopp fordi
    ingen er satt opp der ennå.
    """
    start = vaktliste.vakt.startet
    slutt = vaktliste.planlagt_slutt
    if start is None or slutt is None or slutt <= start:
        return (None, None)
    return (start, slutt)
