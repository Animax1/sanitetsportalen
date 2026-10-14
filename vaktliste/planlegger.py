"""Planleggeren: grunnlaget for vaktlisten (15. sep. 2026).

Ressursene og de tomme plassene fra et oppsett — `generer_grunnlag`, og
forhåndsvisningen som regnes av samme kode. Reglene står i `vaktliste/CLAUDE.md`
under «Planleggeren».

Skilt ut av `vaktliste/services.py` i G2 (14. okt. 2026).
"""
from __future__ import annotations

from django.db import transaction

from . import pauser
from .services import er_planlagt, neste_rekkefolge
from .belastning import _timer


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
        raise Planleggerfeil('Hver enhet må ha minst ett skiftvindu.')
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
        # Pausene regelen legger inn. De lages på nytt ved hver generering,
        # så tallet er hele regelens, ikke en endring.
        'pauser': sum(len(p.get('pauser', [])) for p in plan),
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
            'pauser': len(p.get('pauser', [])),
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
        regel = pauser.les_regel(linje)

        ressurs_id = linje.get('ressurs_id')
        if ressurs_id is not None:
            ressurs = Ressurs.objects.filter(
                pk=ressurs_id, vaktliste=vaktliste
            ).select_related('gruppe').first()
            if ressurs is None:
                raise Planleggerfeil(
                    'Enheten finnes ikke lenger på denne vaktlisten.')
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
                'pauseregel': regel,
            })
            continue

        gruppe = grupper.get(linje.get('gruppe_id'))
        if gruppe is None:
            raise Planleggerfeil('Ukjent ressurstype.')

        antall = int(linje.get('antall') or 1)
        if antall < 1:
            raise Planleggerfeil('Antall enheter må være minst én.')

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
                    f'allerede på denne vaktlisten.')

        for _ in range(antall):
            navn = _neste_navn(gruppe, brukte_navn, finnes_i_gruppa)
            plan.append({
                'gruppe': gruppe,
                'navn': navn,
                'skift': skift,
                'ressurs': None,
                'beholdt': {},
                'kladd': 0,
                'pauseregel': regel,
            })

    _planlegg_pauser(plan)

    # **Grensen måles på det som skal lages**, ikke på tallene i feltene: en
    # rad som allerede står med sine seks plasser lager ingen, og skal ikke
    # telle mot taket hver gang noen retter et klokkeslett.
    totalt = sum(nye for p in plan for _, _, nye in _nye_plasser(p))
    if totalt > MAKS_PLASSER_TOTALT:
        raise Planleggerfeil(
            f'Oppsettet ville laget {totalt} plasser. Grensen er '
            f'{MAKS_PLASSER_TOTALT} — sjekk tidene og antallet.')
    return plan


def _planlegg_pauser(plan):
    """Pausene regelen gir, lagt på hver rad som `pauser`.

    **Forskyvningen telles per gruppe og skiftstart, over hele planen** — ikke
    per linje. Leses oppsettet tilbake, er hver ressurs sin egen linje, og en
    teller per linje ville satt alle lagene tilbake på samme klokkeslett ved
    neste generering. Rekkefølgen er planens, og den er ressursenes.

    **En pause lederen har lagt inn for hånd, vinner.** Regelpausen som ville
    overlappet den, hoppes over — lederen har alt bestemt noe om den tida.
    """
    teller = {}
    for rad in plan:
        rad['pauser'] = []
        regel = rad.get('pauseregel')
        if regel is None:
            continue
        etter, lengde, forskyv = regel
        egne = []
        if rad['ressurs'] is not None:
            egne = [(p.fra, p.til) for p in rad['ressurs'].pauser.all() if not p.fra_regel]
        for fra, til, _ in rad['skift']:
            nokkel = (rad['gruppe'].pk, fra)
            indeks = teller.get(nokkel, 0) if forskyv else 0
            tid = pauser.regelpause(fra, til, etter_min=etter, lengde_min=lengde, indeks=indeks)
            if tid is None:
                continue
            # **Også et lag på «samtidig» tar en plass i rekka.** Ellers la et
            # forskjøvet lag i samme gruppe seg oppå dem, og to lag var borte
            # samtidig — nettopp det forskyvningen finnes for å hindre.
            # Funnet ved mutasjonstesting.
            teller[nokkel] = teller.get(nokkel, 0) + 1
            if any(a < tid[1] and tid[0] < b for a, b in egne):
                continue
            rad['pauser'].append(tid)


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
    from .models import Pause, Ressurs, Vaktpost

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
            # **Regelen står på ressursen, og regelpausene lages på nytt.**
            # Pausene lederen har lagt inn eller rettet for hånd står, som
            # det som er delt ut av plassene.
            etter, lengde, forskyv = rad['pauseregel'] or (None, None, True)
            ressurs.pause_etter_min, ressurs.pause_min = etter, lengde
            ressurs.pause_forskyv = forskyv
            ressurs.save(update_fields=['pause_etter_min', 'pause_min', 'pause_forskyv',
                                        'updated_at'])
            for p in ressurs.pauser.filter(fra_regel=True):
                p.delete()
            for fra, til in rad['pauser']:
                Pause.objects.create(ressurs=ressurs, fra=fra, til=til, fra_regel=True)

    svar = _sammendrag(plan)
    svar['slettet'] = slettet
    return svar
