"""Vaktlisten i drift: når den går i drift av seg selv, og hvem som er på vakt nå.

Lesestiene her er det `/oppdrag/`, `/ko/` og `/lag/` leser av vaktlisten —
besetningen, ressursene på vakt, og hvilken liste som gjelder.

Skilt ut av `vaktliste/services.py` i G2 (14. okt. 2026).
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.sortering import Norsk, norsk_nokkel

from . import choices
from .models import Ressurs, Vaktliste


# ── Drift ved vaktas start (30. sep. 2026) ───────────────────────────────────
#
# André, 14. sep.: «fjern i drift-knappen og heller ha det slik at når
# vaktlisten starter så er den automatisk i drift». Avgjort 15. sep.
# (`docs/FORSLAG_VAKTLISTE_UTBEDRINGER.md` §6): **automatisk, med overstyring
# beholdt**. Glemmer noen knappen, er innsjekken stengt ved vaktstart — altså
# nøyaktig når alle har mest å gjøre.
#
# **Klokkesatt, ikke utledet.** `status` står som et felt, satt av klokka: da
# overlever `satt_i_drift_at`, auditsporet og e-postutsendingen ved drift, og
# «ut av drift» betyr fortsatt noe. Et utledet `i_drift` ville hatt ingen av dem.
#
# **Klokka åpner, den stenger aldri** (André, 30. sep.: «vi trenger ikke å ha
# det»). Den som møter tidlig åpner med knappen; lista står i drift til noen
# tar den ut eller arkiverer den. En innsjekk som stengte seg selv ved
# `planlagt_slutt`, ville tatt fra noen muligheten til å stemple av.

#: Uten planlagt slutt setter klokka lista i drift bare det første døgnet.
#: En liste som aldri fikk slutt og ble glemt, skal ikke åpne seg en uke senere.
AUTODRIFT_UTEN_SLUTT = timedelta(hours=24)


def skal_settes_i_drift(vl, naa) -> bool:
    """Skal klokka sette denne lista i drift nå? Hver regel er en egen ting
    noen kan ville løsne på, og hver har en grunn:

    - **Bare én gang.** `satt_i_drift_at` er satt så snart lista har vært i
      drift — av knappen eller av klokka. Tok noen den *ut* av drift, var det
      et valg, og klokka skal ikke overstyre det et minutt senere.
    - **Starten må ha ligget fram i tid da lista ble laget.** «Ny vaktliste»
      uten start gir start = nå; uten denne regelen ville lista gått i drift
      idet den ble opprettet, midt i planleggingen. Den samme regelen gjør at
      gamle lister ikke åpner seg den dagen dette deployes.
    - **Ikke etter slutten** — `planlagt_slutt`, eller et døgn uten den.
    - **Ikke arkivert, ikke en avsluttet vakt.** Samme sperre som knappen.
    """
    vakt = vl.vakt
    if vl.status != choices.PLANLEGGING or vl.arkivert_at is not None:
        return False
    if vl.satt_i_drift_at is not None:
        return False
    if vakt.avsluttet is not None or vakt.startet is None:
        return False
    if vl.created_at is None or vl.created_at >= vakt.startet:
        return False
    slutt = vl.planlagt_slutt or (vakt.startet + AUTODRIFT_UTEN_SLUTT)
    return vakt.startet <= naa < slutt


def autodrift_tidspunkt(vl):
    """Når klokka vil sette lista i drift, eller `None` om den ikke vil.

    For grensesnittet: knappen skal kunne si «settes i drift av seg selv fre.
    15:00». Svaret er vaktas start når reglene vil slippe den gjennom da."""
    start = vl.vakt.startet
    if start is None:
        return None
    return start if skal_settes_i_drift(vl, max(start, timezone.now())) else None


def laas_portalen(vl) -> None:
    """Lås portalraden til `vl` til transaksjonen er ferdig.

    **Det er portalen som låses, ikke lista**: regelen under gjelder alle
    listene i portalen, og to trykk på to *ulike* lister ville ellers begge
    sett «ingen andre i drift» og begge gått inn. Kalles inne i en
    `transaction.atomic()`.
    """
    from core.models import Vaktportal
    if vl.vakt.portal_id is not None:
        Vaktportal.objects.select_for_update().filter(pk=vl.vakt.portal_id).first()


def annen_i_drift(vl):
    """En **annen** vaktliste i drift i samme portal som `vl`, eller ``None``.

    **Én vaktliste i drift per portal** (André, 17. okt. 2026: «det er bare en
    vaktliste per portal som er tanken»). Med to i drift var tavla i `/ko/`
    tvetydig: `vaktliste_i_bruk()` lot den sist satte vinne, så lagene fra den
    andre sto på tavla uten å kunne flyttes — «jeg kan ikke forflytte lag i
    tavlen». Sperren står ved inngangen (knappen og klokka), ikke i leserne.
    """
    return (lister_i_drift().filter(vakt__portal_id=vl.vakt.portal_id)
            .exclude(pk=vl.pk).select_related('vakt')
            .order_by('-satt_i_drift_at', '-pk').first())


def sett_i_drift_ved_start(vl, naa=None) -> bool:
    """Sett én liste i drift hvis tiden er kommet. Returnerer True om klokka
    gjorde det — da er `vl` sin rad endret, og kalleren må lese den på nytt.

    **Låst og sjekket på nytt i transaksjonen.** Klokka i middlewaren og et
    view kan komme til samme liste samtidig; uten `select_for_update` ville
    begge satt drift, og begge sendt fila.

    **Auditraden står uten bruker** (`uten_request`): klokka kan gå inne i et
    view, og da ville raden stått på den som åpnet siden.

    Fila sendes som ved knappen, etter at drift er lagret og aldri som en
    sperre — `send_fil` kaster ikke.
    """
    from audit.utils import uten_request

    from . import fil
    from .models import Utsending

    naa = naa or timezone.now()
    with transaction.atomic():
        laas_portalen(vl)
        laast = (Vaktliste.objects.select_for_update()
                 .select_related('vakt').filter(pk=vl.pk).first())
        if laast is None or not skal_settes_i_drift(laast, naa):
            return False
        # Står en annen alt i drift, venter klokka: den tar ikke over en liste
        # noen har satt i drift for hånd, og prøver igjen neste minutt.
        if annen_i_drift(laast) is not None:
            return False
        laast.status = choices.DRIFT
        laast.satt_i_drift_at = naa
        laast.satt_i_drift_av = None
        laast.drift_automatisk = True
        with uten_request():
            laast.save(update_fields=['status', 'satt_i_drift_at', 'satt_i_drift_av',
                                      'drift_automatisk', 'updated_at'])
    # Lista bærer portalen — klokka går uten forespørsel.
    if fil.sendes_ved_drift(laast.vakt.portal) and fil.mottakere(laast.vakt.portal):
        fil.send_fil(laast, bruker=None, utloest=Utsending.DRIFT)
    return True


def sett_forfalte_i_drift(naa=None) -> list:
    """Klokka: sett i drift hver liste som har nådd starten. Returnerer dem som
    ble satt. Én spørring når ingenting er forfalt — den går hvert minutt.

    Kalles av `FilutsendingMiddleware`, og av viewene som leser lista eller
    stempler, så innsjekken er åpen i det første trykket etter start og ikke
    et minutt senere."""
    naa = naa or timezone.now()
    kandidater = (Vaktliste.objects
                  .filter(status=choices.PLANLEGGING, arkivert_at__isnull=True,
                          satt_i_drift_at__isnull=True,
                          vakt__startet__lte=naa, vakt__avsluttet__isnull=True)
                  .select_related('vakt'))
    return [vl for vl in kandidater
            if skal_settes_i_drift(vl, naa) and sett_i_drift_ved_start(vl, naa)]


def lister_i_drift(portal=None):
    """Vaktlistene som står i drift — **og ikke er arkivert**.

    **Én spørring, fire lesere** (26. sep. 2026, A6): `vaktliste_i_bruk()`,
    `besetning()`, intervallsendingen i `fil` og driftstatus. Arkiveringen satte
    bare `arkivert_at`, så en liste arkivert i drift var borte fra velgeren men
    styrte fortsatt sentralbordet og KO, og ble sendt på e-post med
    telefonnumre. Sperra i viewet hindrer nye; dette tar dem som finnes.
    """
    from .models import Vaktliste
    qs = Vaktliste.objects.filter(status=choices.DRIFT, arkivert_at__isnull=True)
    # `portal` for leserne som svarer i én portal (`vaktliste_i_bruk`, `besetning`).
    # Fila på e-post og driftstatus går over alle, og kaller uten.
    return qs if portal is None else qs.filter(vakt__portal=portal)


def vaktliste_i_bruk():
    """Vaktlista som gjelder **nå** — den i drift, ellers den aktive vaktas.

    Regelen er André sin, 12. sep. 2026 («koblingen fungerer ikke»): scopet var
    portalens aktive vakt alene, og da fant sentralbordet ingenting mens
    vaktlista som faktisk kjørte lå på en annen vakt. En liste satt i drift er
    den som gjelder, uansett hvilken vakt portalen står på.

    **Den ligger her og ikke i hver leser.** `besetning()` hadde den inline, og
    KOs ressursoversikt trengte nøyaktig den samme — to kopier av samme regel
    er to kilder som glir fra hverandre, og de ville glidd på den ene dagen det
    betyr noe: under en vakt der de to flatene sa hvert sitt om hvem som var på
    bilen.

    **Dette er det globale spørsmålet, ikke `besetning()` sitt.** Den spør om
    *én enhet* og må derfor lete i alle lister i drift — en liste i drift der
    enheten ikke er koblet skal ikke komme i veien for en der hun er. De to
    deler prioriteringen og ikke spørringen, og et forsøk på å slå dem sammen
    (17. sep. 2026) brøt nettopp den forskjellen uten at noen test ble rød.

    **Høyst én liste i drift per portal** fra 17. okt. 2026 (`annen_i_drift`),
    og lista hentes i portalen. Lister satt i drift før sperren kom kan likevel
    stå to — da vinner den som sist ble satt i drift.
    Rekkefølgen er oppgitt og ikke overlatt til basen: et ressursbilde som
    bytter innhold mellom to pollinger er verre enn ett som viser feil liste,
    fordi det siste lar seg se.

    Returnerer `None` når ingen liste er i drift **og** den aktive vakta ikke
    har noen liste. `hent_aktiv_vakt()` er aldri `None` — den reparerer
    pekeren og lager vakta om den mangler — så det er vaktlista som kan mangle
    her, ikke vakta.
    """
    from core.vakt import hent_aktiv_vakt
    from .models import Vaktliste

    # **I portalen** (17. okt. 2026): Branns tavle skal aldri vise Standards liste.
    vakt = hent_aktiv_vakt()
    i_drift = (lister_i_drift(vakt.portal)
               .select_related('vakt')
               .order_by('-satt_i_drift_at', '-pk').first())
    if i_drift is not None:
        return i_drift
    return Vaktliste.objects.filter(vakt=vakt).select_related('vakt').first()


def bilressurser(enhet_ider) -> dict:
    """``{enhet_id: Ressurs}`` — vaktlisteressursen hver bil hører til **nå** (20. okt. 2026).

    **Én regel, to lesere:** `besetning()` (ressursoversikten) og KO-tavla. Tavla lette bare i
    `vaktliste_i_bruk()` — én liste — mens besetningen lette i alle lister i drift. Sto
    ambulansene i en annen liste i drift enn lagene, var de synlige med besetning i
    ressursoversikten og borte på tavla (André: «dette var koblede biler som er på vakt»).

    Samme prioritering som før, per enhet: en liste i drift i portalen, sist satt i drift
    først; ellers den aktive vaktas liste. En liste i drift der enheten *ikke* er koblet, står
    ikke i veien for en der hun er — det er forskjellen fra `vaktliste_i_bruk()` (17. sep. 2026).
    """
    from core.vakt import hent_aktiv_vakt

    ider = list(enhet_ider)
    if not ider:
        return {}
    vakt = hent_aktiv_vakt()
    ut = {}
    i_drift = (Ressurs.objects
               .filter(enhet_id__in=ider, vaktliste__in=lister_i_drift(vakt.portal))
               .select_related('vaktliste__vakt', 'gruppe', 'enhet')
               .order_by('-vaktliste__satt_i_drift_at', '-vaktliste__pk', 'pk'))
    for r in i_drift:
        ut.setdefault(r.enhet_id, r)
    rest = [i for i in ider if i not in ut]
    if rest and vakt is not None:
        for r in (Ressurs.objects.filter(enhet_id__in=rest, vaktliste__vakt=vakt)
                  .select_related('vaktliste__vakt', 'gruppe', 'enhet').order_by('pk')):
            ut.setdefault(r.enhet_id, r)
    return ut


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

    # **Ressurs-scopet, ikke globalt** — og forskjellen fra `vaktliste_i_bruk()`
    # er verdt å kjenne: her spørres det om *denne enheten*, så en liste i drift
    # der enheten ikke er koblet skal ikke komme i veien for en der hun er.
    # Et forsøk på å slå de to sammen (17. sep. 2026) gjorde nettopp det, og
    # suiten var grønn — ingen test hadde to lister i drift samtidig.
    # Regelen står i `bilressurser()` (20. okt. 2026), så sentralbordet og KO-tavla viser
    # samme ressurs for samme bil — også når to lister står i drift.
    ressurs = bilressurser([enhet_id]).get(enhet_id)
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
    poster = bemannede.filter(fra_tid__lte=naa, til_tid__gte=naa).order_by(Norsk('mannskap__navn'))
    mannskap = [_rad(vp) for vp in poster]

    neste, neste_fra = [], None
    if not mannskap:
        forste = bemannede.filter(fra_tid__gt=naa).order_by('fra_tid').first()
        if forste is not None:
            neste_fra = forste.fra_tid
            neste = [_rad(vp) for vp in
                     bemannede.filter(fra_tid=neste_fra).order_by(Norsk('mannskap__navn'))]

    # **De som er i bilen først.** Operatørens spørsmål er «hvem har jeg», og
    # da skal svaret stå øverst; de som mangler er den andre halvdelen av
    # samme liste.
    #
    # Sorteringen skjer **i Python**, ikke i basen, av to grunner: `tilstede`
    # er en utledet egenskap uten kolonne å sortere på, og `rolle__navn` er
    # nullbar — og SQLite (dev) og PostgreSQL (prod) plasserer NULL i hver sin
    # ende. En besetningsliste som står i ulik rekkefølge lokalt og i drift er
    # en feil man aldri ser før den betyr noe.
    mannskap.sort(key=lambda m: (not m['tilstede'], norsk_nokkel(m['navn'])))

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


def ressurser_paa_vakt_naa(vaktliste, naa=None):
    """Ressursene uten oppdragsenhet som har et skift som dekker **nå**.

    «Det er viktig at det er bare de som er på vakt nå som vises av lag»
    (André, 19. sep. 2026). «På vakt» er vaktlistas eget begrep: et skift med
    mannskap, ikke avmeldt, som dekker tidspunktet — ikke om laget har møtt.
    Bilene styres ikke herfra; de skrus av og på av KO som før (`pa_vakt`).

    Ett sted for regelen, fordi den har to lesere: kortene i ressursoversikten
    (`ressurser_uten_enhet`) og lagvelgeren i hendelsen
    (`ko.services.lag_som_kan_velges`). Et lag man kan velge skal være et lag
    man kan se — og var regelen skrevet to ganger, ville de gledet fra
    hverandre ved neste endring.
    """
    return ressurser_med_skift(vaktliste, naa or timezone.now()).filter(enhet__isnull=True)


def ressurser_med_skift(vaktliste, tidspunkt):
    """Alle ressursene — **også bilene** — som har et skift som dekker
    `tidspunkt`: med mannskap, ikke avmeldt. Selve regelen for «på vakt»;
    `ressurser_paa_vakt_naa` er den samme for lagene, nå.

    Skilt ut 23. sep. 2026 for tavleplanleggeren i KO, som teller hvor mange
    av hver gruppe vaktlista har på vakt time for time — også fram i tid, og
    også ambulansene. Der er bilens `pa_vakt` ikke svaret: den sier hva KO har
    skrudd på *nå*, ikke hva som er planlagt i kveld. Én regel, to lesere.
    """
    from django.db.models import Exists, OuterRef

    from .models import Vaktpost

    dekker = Vaktpost.objects.filter(
        ressurs=OuterRef('pk'), mannskap__isnull=False, avmeldt_at__isnull=True,
        fra_tid__lte=tidspunkt, til_tid__gte=tidspunkt)
    return (Ressurs.objects.filter(vaktliste=vaktliste)
            .annotate(_paa_vakt=Exists(dekker)).filter(_paa_vakt=True))


def ressurser_uten_enhet(naa=None):
    """Ressursene i lista i bruk som **ikke** er koblet til en oppdragsenhet
    — lag, samleplass, KO (KO pulje 6, André 18. sep. 2026: «få inn alle
    enheter fra vaktlisten som kan velges i /ko som ikke allerede er i
    /oppdrag»).

    Samme scope som `vaktliste_i_bruk()`: lista i drift, ellers den aktive
    vaktas — og **bare ressursene med et skift som dekker nå**
    (`ressurser_paa_vakt_naa`, 19. sep. 2026). Samme svar per ressurs som
    `besetning()` gir for en bil — skiftene som dekker *nå* — **med telefon og ISSI**
    fra 19. sep. 2026 (André: «alle ressurser … må ha navn, om de er
    registrert møtt, telefonnummer og ISSI»). Svaret var uten dem til da,
    med begrunnelsen at et nummer man ikke trenger er et nummer på en skjerm
    i et rom; det holdes ved at kortet viser besetningen først ved klikk,
    som bilene — ikke ved å holde tallene ute av svaret.

    Ingen status i vaktlistas svar. Om laget er opptatt på en hendelse
    er KOs sak (`ko.HendelseLag`), og KO legger det på kortet selv.

    Én spørring for vaktpostene, gruppert i Python: lista polles.
    """
    from .models import Vaktpost

    naa = naa or timezone.now()
    vaktliste = vaktliste_i_bruk()
    if vaktliste is None:
        return []
    ressurser = list(ressurser_paa_vakt_naa(vaktliste, naa)
                     .select_related('gruppe')
                     .order_by('gruppe__rekkefolge', Norsk('gruppe__navn'), 'rekkefolge', Norsk('navn')))
    if not ressurser:
        return []
    poster = (Vaktpost.objects
              .filter(ressurs__in=ressurser, mannskap__isnull=False, avmeldt_at__isnull=True)
              .select_related('mannskap', 'rolle')
              .order_by('fra_tid', Norsk('mannskap__navn')))
    per_ressurs: dict[int, list] = {}
    for vp in poster:
        per_ressurs.setdefault(vp.ressurs_id, []).append(vp)

    def _rad(vp):
        return {'navn': vp.mannskap.navn,
                'rolle': vp.rolle.navn if vp.rolle else '',
                'telefon': vp.mannskap.telefon,
                'issi': vp.mannskap.issi,
                'tilstede': vp.er_tilstede}

    ut = []
    for r in ressurser:
        alle = per_ressurs.get(r.pk, [])
        naa_poster = [vp for vp in alle if vp.fra_tid <= naa <= vp.til_tid]
        mannskap = [_rad(vp) for vp in naa_poster]
        mannskap.sort(key=lambda m: (not m['tilstede'], norsk_nokkel(m['navn'])))
        ut.append({
            'id': r.pk,
            'navn': r.navn,
            'gruppe_id': r.gruppe_id,
            'gruppe_navn': r.gruppe.navn,
            'gruppe_ikon': r.gruppe.ikon,
            'mannskap': mannskap,
            'antall': len(mannskap),
            'tilstede': sum(1 for m in mannskap if m['tilstede']),
        })
    return ut


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
    from core.portal import gjeldende_portal
    ressurs = (Ressurs.objects
               .filter(enhet_id=enhet_id, vaktliste__vakt__portal=gjeldende_portal())
               .select_related('vaktliste__vakt')
               .order_by('-vaktliste__vakt__startet')
               .first())
    return ressurs.vaktliste.vakt.navn if ressurs else None
