"""KO på papir — `/ko/utskrift/` (13. okt. 2026), og den lagrede kopien uten nett.

**Et øyeblikksbilde, ikke et arkiv** (André, 13. okt. 2026: «Vi trenger ikke
vise lukkede hendelser og trenger nok bare loggstrøm fra de siste 8 timer. Og
så må vi få utskrift av tavlen og ikke minst konsertplanleggeren og
oppdragene»). Papiret er reserven når portalen eller nettet er borte midt i en
vakt: det man trenger da er hva som pågår *nå* og hva som kommer, ikke hele
historikken.

**Alt, alltid, ingen valg** (André, samme dag: «alt sammen av info i ko er
viktig. Så utskrift siden må printe ut alle vinduer og ikke la oss
selektere»). Delene følger KOs vinduer:

| Del | Hva | Gate |
|---|---|---|
| `hendelser` | De åpne hendelsene | `les` i KO |
| `ressurser` | Bilene med status og besetning, lagene med mannskap — navn, rolle, telefon, ISSI, møtt | Bilene: `les` i oppdrag; besetningen og lagene: `les` i vaktliste |
| `logg` | Loggen de siste `LOGG_TIMER` timene — **med** kommentarene i hendelsene | `les` i KO |
| `oppdrag` | Sentralbordets aktive oppdrag | `les` i oppdrag |
| `tavle` | Hvor hver ressurs står nå, og planlagte pauser og flyttinger i tavlas vindu | `les` i vaktliste; bilene bare med `les` i oppdrag |
| `program` | Konsertene som pågår eller kommer i tavlas vindu, med behov | `les` i KO |

**Gatene er de samme som skjermens**, del for del (komposisjonsregelen i
rollemodellen §5): KO *viser* oppdragsmodulens og vaktlistas data, og hvem som
får se dem er de modulenes sak. En del man mangler tilgang til står som en
setning på papiret, ikke som en 403 for hele utskriften.

**Samme rader som skjermen.** Loggen og hendelsene tegnes av `_til_dict` og
`_hendelse_til_dict` i `ko/views.py`, oppdragene av
`oppdrag.views.sentralbord_liste`, tavla av `tavle.tavle_data`, programmet av
`program.poster`, ressursene av `oppdrag.services.enhetskort_liste`,
`vaktliste.services.besetning` og `ressurser_uten_enhet`. Det som legges til
her er bare utvalget (tidsvinduet, de åpne) og tidene som lokale tidspunkter —
aldri en egen spørring som kan bli uenig med skjermen.

**Uten nett** (André: «KO har bare personlige brukere med mfa. Så nr 2 er
aktuelt»): KO-siden henter utskriften i bakgrunnen hvert `KOPI_MINUTTER`, og
`/ko/sw.js` legger den i nettleseren. Mister PC-en nettet, åpner
«Skriv ut» kopien, merket med hvor gammel den er. **Bare personlige kontoer**:
svaret bærer `KOPI_HODE` bare når kontoen ikke er delt, og workeren lagrer
ingenting uten det — en delt konto på en delt PC skal ikke etterlate
helseopplysninger i nettleseren. Høyst 24 timer, og «Logg ut» sletter den.

**Ingen redigering uten nett** (André: «Offline logg er bare ment for å kunne ta
utskrift av det som er»). En logglinje i kø på én PC er en linje ingen andre i
rommet ser, og den ville landet med et klokkeslett fra før — lappen og muntlig
beskjed er tryggere, og føres inn når nettet er tilbake.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.auth_decorators import har_tilgang

from .models import HENDELSE_APEN, PRIORITET_NAVN, Logglinje

#: Loggen på papiret: de siste åtte timene (André, 13. okt. 2026). Et skift,
#: omtrent — det den neste operatøren trenger å vite, ikke hele vakta.
LOGG_TIMER = 8

#: Hvor ofte KO-siden henter utskriften i bakgrunnen, så kopien uten nett er
#: fersk. Fem minutter: en kopi er aldri mer enn det bak, og det koster én
#: sidegenerering per KO-PC i kvarteret tre ganger — tavla poller hvert 2,5 s.
KOPI_MINUTTER = 5

#: Hodet som gir workeren lov til å lagre svaret. Satt bare for personlige
#: kontoer (`kan_lagres_lokalt`).
KOPI_HODE = 'X-Ko-Kopi'


def lokal(tid):
    """Et tidspunkt som norsk tid — ORM-en gir UTC, og et dagskille eller et
    klokkeslett regnet av UTC er feil to timer av døgnet om sommeren."""
    if isinstance(tid, str):
        tid = parse_datetime(tid) if tid else None
    return timezone.localtime(tid) if tid else None


def kan_lagres_lokalt(bruker) -> bool:
    """Kopien uten nett er for **personlige** kontoer. En delt konto er
    nettopp den som sitter på en PC flere bruker — der skal ingen
    helseopplysninger bli liggende i nettleseren.

    I dag kommer en delt konto ikke inn i KO i det hele tatt (`ko.module`
    sier ikke ja til `tillat_delt_konto`). Dette er laget under: åpnes KO en
    dag for delte kontoer, skal ikke kopien følge med uten at noen bestemmer det.
    """
    return bool(bruker.is_authenticated) and not getattr(bruker, 'er_delt_konto', False)


# ── Delene ────────────────────────────────────────────────────────────────────

def hendelser_del(vakt) -> list[dict]:
    """De åpne hendelsene, lavest nummer først. Lukkede står ikke på papiret."""
    from . import services
    from .views import _hendelse_til_dict

    ut = []
    for h in sorted(services.hendelser_for(vakt), key=lambda h: h.hendelsesnummer):
        if h.status != HENDELSE_APEN:
            continue
        rad = _hendelse_til_dict(h)
        rad.update(opprettet=lokal(h.opprettet_at),
                   prioritet_navn=PRIORITET_NAVN.get(h.prioritet, h.prioritet))
        ut.append(rad)
    return ut


def logg_del(vakt, naa) -> list[dict]:
    """Linjene som skjedde de siste `LOGG_TIMER` timene, i `gjeldende()` sin
    rekkefølge — en rettet linje står der den ble skrevet.

    **Alt i vinduet, også kommentarene i hendelsene** (som strømmen på
    skjermen skjuler) og linjene i hendelser som er lukket siden: loggen er
    fasit, og en linje som forsvant fra papiret fordi hendelsen ble lukket fem
    minutter før utskriften, er nøyaktig hullet papiret skal dekke.
    """
    from .views import _til_dict

    grense = naa - timedelta(hours=LOGG_TIMER)
    ut = []
    for linje in Logglinje.objects.gjeldende(vakt).filter(tidspunkt__gte=grense):
        rad = _til_dict(linje)
        tid = lokal(linje.tidspunkt)
        rad.update(tid=tid, dag=tid.date(), registrert=lokal(linje.registrert_at),
                   fjernet_tid=lokal(linje.fjernet_at))
        ut.append(rad)
    return ut


def oppdrag_del(vakt) -> list[dict]:
    """Sentralbordets aktive oppdrag, eldste først — på papir leses lista
    ovenfra, og det eldste er det som har ventet lengst."""
    from oppdrag.views import sentralbord_liste

    ut = []
    for rad in reversed(sentralbord_liste(vakt)):
        rad['opprettet_tid'] = lokal(rad['opprettet'])
        rad['status_tid'] = lokal(rad['status_tidspunkt'])
        for e in rad['enheter']:
            e['status_tid'] = lokal(e.get('status_tidspunkt'))
        ut.append(rad)
    return ut


def tavle_del(vakt, naa, *, med_biler: bool) -> dict:
    """Tavla som tabell: hvert sted med det som står der nå, pausene, de som
    er opptatt, de uten plass — og det som er planlagt i tavlas vindu.

    Bygget av `tavle_data`, samme svar som tavla på skjermen tegnes av.
    **Opptatt har forrang**, som der — og det trengs ingen egen sjekk her:
    tavla lukker plassen i det ressursen går på en hendelse eller rykker ut
    (`services.sett_lag`, `bil_rykket_ut`), så en opptatt ressurs har ingen åpen
    plassering å stå på.
    """
    from . import tavle

    data = tavle.tavle_data(vakt, naa, med_biler=med_biler)
    til = naa + timedelta(hours=tavle.timer())
    ressurser = {r['id']: r for r in data['ressurser']}
    opptatte = [dict(navn=r['navn'], bil=r['bil'], tekst=r['opptatt']['tekst'],
                     fra=lokal(r['opptatt']['fra']))
                for r in data['ressurser'] if r['opptatt']]
    # Bare ressursene som er på tavla nå: en plassering for en ressurs som
    # har gått av vakt, eller en bil den som skriver ut ikke får se, står ikke.
    aapne = [p for p in data['plasseringer']
             if p['til'] is None and p['ressurs_id'] in ressurser]
    plassert = {p['ressurs_id'] for p in aapne}

    def rad(p):
        return dict(navn=p['ressurs_navn'], fra=lokal(p['fra']),
                    planlagt_til=lokal(p['planlagt_til']))

    steder = []
    for r in data['rader']:
        her = [rad(p) for p in aapne if p['lokasjon_id'] == r['id'] and not p['pause']]
        if her:
            steder.append({'navn': r['navn'], 'ressurser': sorted(her, key=lambda d: d['navn'])})
    planlagt = [dict(navn=q['ressurs_navn'], fra=lokal(q['fra']), til=lokal(q['til']),
                     hvor='Pause' if q['pause'] else (q['lokasjon_navn'] or '–'))
                for q in data['pauser']
                if not q['startet'] and lokal(q['til']) > naa and lokal(q['fra']) < til
                and q['ressurs_id'] in ressurser]
    return {
        'steder': steder,
        'pause': sorted((rad(p) for p in aapne if p['pause']), key=lambda d: d['navn']),
        'opptatt': sorted(opptatte, key=lambda d: d['navn']),
        'uten_plass': sorted(r['navn'] for r in data['ressurser']
                             if not r['opptatt'] and r['id'] not in plassert),
        'planlagt': planlagt,
        'til': lokal(til),
        'med_biler': med_biler,
    }


def ressurser_del(vakt, *, med_biler: bool, med_vaktliste: bool) -> dict:
    """Ressursoversikten: bilene med status, aktivt oppdrag og besetning, og
    vaktlistas lag som er på vakt nå, med mannskapet.

    **Telefon og ISSI står på papiret** — det er det man trenger når
    sambandet eller portalen er borte. Samme felter som besetningen bak et
    klikk på skjermen (`vaktliste.services.besetning`), ikke flere: notat og
    kompetanser står heller ikke der.
    """
    from oppdrag.models import Enhet
    from oppdrag.services import enhetskort_liste, ledig_siden_bulk

    from core.sortering import Norsk

    biler = []
    if med_biler:
        enheter = list(Enhet.objects.filter(er_aktiv=True)
                       .select_related('user', 'enhetstype').order_by(Norsk('navn')))
        for kort in enhetskort_liste(enheter, vakt, ledig_siden_bulk(enheter, vakt)):
            kort['status_tid'] = lokal(kort.get('status_tidspunkt'))
            kort['ledig_tid'] = lokal(kort.get('ledig_siden'))
            kort['besetning'] = None
            biler.append(kort)
        if med_vaktliste:
            from vaktliste.services import besetning
            for kort in biler:
                kort['besetning'] = besetning(kort['id'])
        # På vakt først, så av vakt — samme deling som sentralbordet.
        biler.sort(key=lambda k: not k['pa_vakt'])
    lag = []
    if med_vaktliste:
        from vaktliste.services import ressurser_uten_enhet
        lag = ressurser_uten_enhet()
    return {'biler': biler, 'lag': lag, 'med_biler': med_biler, 'med_vaktliste': med_vaktliste}


def program_del(vakt, naa) -> dict:
    """Konsertene som pågår eller begynner innen tavlas vindu, i tidsrekkefølge,
    med beredskap, publikum, kjennetegn og behov — konsertplanleggerens liste."""
    from . import program, tavle

    til = naa + timedelta(hours=tavle.timer())
    poster = []
    for p in sorted(program.poster(vakt), key=lambda p: (p['fra'] or '', p['lokasjon_navn'])):
        fra, slutt = lokal(p['fra']), lokal(p['til'])
        if slutt is None or slutt <= naa or fra >= til:
            continue
        p.update(fra_tid=fra, til_tid=slutt, pagar=fra <= naa)
        poster.append(p)
    return {'poster': poster, 'til': lokal(til)}


# ── Hele papiret ──────────────────────────────────────────────────────────────

def bygg(request, vakt, naa=None) -> dict:
    """Konteksten til malen: hver del, eller en grunn i `stengt` når den som
    skriver ut mangler tilgang til modulen delen viser."""
    from oppdrag.views_common import er_enhetskonto

    naa = naa or timezone.now()
    bruker = request.user
    kan_oppdrag = har_tilgang(bruker, 'oppdrag', 'les') and not er_enhetskonto(bruker)
    kan_vaktliste = har_tilgang(bruker, 'vaktliste', 'les')
    ut = {'stengt': {}, 'naa': lokal(naa), 'logg_timer': LOGG_TIMER,
          'hendelser': hendelser_del(vakt),
          'ressurser': ressurser_del(vakt, med_biler=kan_oppdrag, med_vaktliste=kan_vaktliste),
          'program': program_del(vakt, naa),
          'linjer': logg_del(vakt, naa),
          'logg_fra': lokal(naa - timedelta(hours=LOGG_TIMER))}
    if not kan_oppdrag and not kan_vaktliste:
        ut['stengt']['ressurser'] = ('Ressursoversikten krever lesetilgang i oppdragsmodulen '
                                     'eller vaktlista.')
    if kan_oppdrag:
        ut['oppdrag'] = oppdrag_del(vakt)
    else:
        ut['stengt']['oppdrag'] = 'Oppdragene krever lesetilgang i oppdragsmodulen.'
    if kan_vaktliste:
        ut['tavle'] = tavle_del(vakt, naa, med_biler=kan_oppdrag)
    else:
        ut['stengt']['tavle'] = 'Tavla viser vaktlistas ressurser, og krever lesetilgang i vaktlista.'
    return ut
