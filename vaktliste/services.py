"""Tjenester for vaktlistemodulen.

Reglene som ikke hører hjemme i et view: å lage en planlagt vakt, å kopiere
et oppsett, og å avgjøre hvem som får røre hva.

**Korps-sjekkene bor her, ikke i viewene.** Regelen er skrevet én gang, på
ett sted, og viewene tar den i bruk — det er derfor et endepunkt ikke kan
huske badgen og glemme reservasjonen.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.auth_decorators import er_global_admin, har_tilgang

from .models import Kontokorps, Mannskap, Ressurs, Vaktliste


# ── Vakter som ennå ikke er aktive ───────────────────────────────────────────

def opprett_planlagt_vakt(navn, startet=None, planlagt_slutt=None):
    """Lag en `core.Vakt` som ikke er aktiv, og en tom vaktliste for den.

    **Gjør ikke vakta aktiv.** Portalens aktive vakt står som den står —
    oktobervakta skal kunne planlegges i august uten at pasienter og oppdrag
    plutselig scopes til den. Aktiv vakt byttes der den alltid byttes, i
    vaktadministrasjonen. Vakta havner i den gjeldende portalen
    (`core.portal.gjeldende_portal`, 17. okt. 2026).

    Vakta lages av `core.vakt.opprett_vakt` (26. sep. 2026), som alle andre
    steder som lager vakter: navnekappløpet gir 400, ikke 500.

    **Slutten tas imot her, ikke bare i «Innstillinger».** Fram til
    11. sep. 2026 spurte «Ny vaktliste» bare om start, og slutten lå bak
    «Vaktas lengde» inne i innstillingsvinduet — André fant den ikke. Det er
    samme regel som i `vaktliste_detalj_view`: slutten må komme etter
    starten, ellers finnes ikke spennet kurvene tegnes over.

    Returnerer den nye vaktlista.
    """
    from core.vakt import opprett_vakt

    startet = startet or timezone.now()
    if planlagt_slutt is not None and planlagt_slutt <= startet:
        raise ValueError('Vakten må slutte etter at den begynner.')
    with transaction.atomic():
        vakt = opprett_vakt(navn, year=timezone.localtime(startet).year,
                            startet=startet)
        return Vaktliste.objects.create(vakt=vakt, planlagt_slutt=planlagt_slutt)


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
# **Hvem som *ser* hvilke korps står i `ser_alle_korps()`, ikke her.** `les`
# ser sitt eget korps, `les_alle` og oppover ser alle (11.–12. sep. 2026). Å se
# er ikke å skrive: stigen over gjelder skriving. Her sto «`les` gjelder hele
# lista med vilje» (§4.4) til 26. sep. 2026 — regelen som ble snudd 11. sep.

def korps_i_portal(portal=None):
    """Korpsene vaktlista viser og godtar: `type='korps'`, med i portalen.

    `docs/BESLUTNING_PORTALER.md` §4.3 (17. okt. 2026). Katalogen er felles
    (`core.Tilhorighet`), og admin velger hvilke som er med i hver portal — en
    lokal portal har ett korps, en tverrfaglig flere. «Annet» (som «Leger») er
    aldri et korps i vaktlista. **Det ene stedet** dette avgjøres: lista,
    registeret og hvert oppslag på `korps_id` går gjennom her, så et korps fra en
    annen portal ikke kan settes på noen ved å sende ID-en for hånd.
    """
    from core.portal import gjeldende_portal

    from .models import Korps
    return Korps.objects.filter(type=Korps.KORPS, portaler=portal or gjeldende_portal())


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
    # Global admin trenger ingen egen `or`: `nivaa_for` gir toppen av stigen.
    return har_tilgang(user, 'vaktliste', 'skriv_leder')


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
    """Korpset kontoen fører, eller ``None``.

    Badgen (§4). **Kontoens eget korps først** (`Kontokorps`, 1. okt. 2026) —
    satt av admin på brukersiden, for den som fører et korps uten selv å være
    mannskap. Ellers korpset fra mannskapsraden kontoen er koblet til, som før.
    Har kontoen begge, er de like: `models.korpskonflikt()` sørger for det.

    Koblingen gir i seg selv ingen tilgang — nivået gjør det. Korpset sier
    bare *hvilket* korps `les` ser og `skriv_handling` fører.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    kk = Kontokorps.objects.filter(user=user).select_related('korps').first()
    if kk is not None:
        return kk.korps
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


#: Lederens kladd som spørring: ledig, ikke åpnet for alle, og verken plassen
#: eller ressursen reservert et korps. Samme sammenslåing som `reservert_korps()`.
KLADD = Q(mannskap__isnull=True, alle_korps=False, korps__isnull=True,
          ressurs__korps__isnull=True)


def synlige_vaktposter(qs, user):
    """Skiftene brukeren får se: alle, eller bare sitt eget korps.

    For korps-brukeren: personene i hennes korps, **og de ledige plassene som
    er satt av til det** — via plassen eller via ressursen, samme
    sammenslåing som `reservert_korps()`. En ledig plass hun kan fylle må
    hun kunne se. Uten badge finnes intet korps, og lista er tom —
    fail-closed, som skrivingen.
    """
    if ser_alle_korps(user):
        if kan_skrive_alt(user):
            return qs
        # **Kladden er skriverettens** (26. sep. 2026, C2 — André: «bare de som
        # har skriverett kan se den»). `les_alle` og `skriv_handling` ser alle
        # korps, men ikke lederens halvferdige planlegging. Kladd er en *ledig*
        # plass: en bemannet plass på en ressurs uten reservasjon (KO) er ikke
        # kladd, og derfor holder ikke `er_planlagt()` alene her.
        return qs.exclude(KLADD)
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


def ikke_delt_ut(ressurs):
    """Plassene på enheten som fortsatt er lederens kladd."""
    from .models import Vaktpost
    return Vaktpost.objects.filter(KLADD, ressurs=ressurs)


def del_ut(ressurs, korps_id=None, alle=False) -> int:
    """**«Del ut»** (pulje 4, 30. sep. 2026): gi kladden på én enhet til et
    korps eller til alle. Svarer med hvor mange plasser som ble delt ut.

    **Bare kladden røres.** En plass som er delt ut til noen andre, eller
    bemannet, står — samme grense som generatoren (`generer_grunnlag`).

    **Til et korps settes reservasjonen på enheten**, ikke på hver plass. Da
    arver plassene den, og et nytt skift på enheten er korpsets fra start —
    «Reservert korps» i «Rediger enhet» er det samme valget, lest som standard.
    **Til alle settes `alle_korps` per plass**, fordi enheten ikke har noe
    slikt felt: «åpen for alle» er en egenskap ved plassen.

    Hver plass lagres for seg — ingen `update()` — fordi audit-signalene
    skal se hver endring. Kalleren eier transaksjonen.
    """
    plasser = list(ikke_delt_ut(ressurs))
    if not plasser:
        return 0
    if alle:
        for vp in plasser:
            vp.alle_korps = True
            vp.save(update_fields=['alle_korps'])
    else:
        ressurs.korps_id = korps_id
        ressurs.save(update_fields=['korps'])
    return len(plasser)


def frigi_arvede_plasser(ressurs) -> int:
    """Enhetens reservasjon tømmes: plassene som arvet den blir **åpne for alle**.

    **Uten dette kunne kladden komme tilbake via enheten.** En plass som er
    delt ut kan ikke settes tilbake til planlagt (`vaktpost_detalj_view`), men tømte
    lederen enhetens reservasjon, ble hver plass som bare arvet den kladd
    igjen — og forsvant fra korpset som så den, uten et ord.

    **Åpen for alle, ikke festet til det gamle korpset** (André, 30. sep.
    2026: «er det ikke greit å ha ledig for alle slik at en ser hva som noen
    korps ikke kunne ta og dermed kan noen andre sikre seg det?»). Å tømme
    reservasjonen er å si at korpset ikke tar enheten; da skal de andre se det.

    Kalles med enheten slik den står i basen, **før** reservasjonen tømmes —
    de som arver er plassene uten eget korps og uten `alle_korps`.
    """
    if ressurs.korps_id is None:
        return 0
    plasser = list(ressurs.vaktposter.filter(korps__isnull=True, alle_korps=False))
    for vp in plasser:
        vp.alle_korps = True
        vp.save(update_fields=['alle_korps'])
    return len(plasser)


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


def kan_gi_nytt_navn(user, ressurs) -> bool:
    """Får brukeren rette navnet på denne ressursen?

    **Et bredere spørsmål enn `kan_bemanne_ressurs`, og det må det være**
    (16. sep. 2026). «Ny ressurs» spør bare om navn og gruppe, så en fersk
    ressurs står **ureservert** — reservasjonen settes i «Rediger», som er
    lederens. Leste navneretten ressursens reservasjon alene, ville
    korps-føreren nesten aldri sett knappen: hun fikk rette de bilene lederen
    alt hadde delt ut til henne, og det er ikke dem hun står ved.

    Ressursen er hennes å navngi hvis hun kan bemanne den, **eller** hvis noen
    av plassene på den er satt av til korpset hennes. Det er samme tolkning
    `reservert_korps()` har: reservasjonen finnes på to nivåer, og en
    samleplass kan stå ureservert og likevel ha fire plasser som er
    Haugesunds.

    **Navnet er fortsatt det eneste som følger med.** Gruppe, reservasjon,
    enhetskobling og sletting leser `kan_lede` hver for seg i viewet — å
    kunne rette et navn er ikke å kunne dele ut ressursen.
    """
    if kan_bemanne_ressurs(user, ressurs):
        return True
    # **Ikke plasser «åpne for alle»** (28. sep. 2026, André: «nei»). Den kan
    # hvem som helst med badge fylle — så var den nok, kunne korps-føreren fra
    # Haugesund gi Karmøys ambulanse nytt navn, og navnet følger med til
    # KO-tavla, besetningen og fila som sendes ut. Å fylle en plass er ikke å
    # eie ressursen; «satt av til korpset hennes» er ordlyden over.
    return any(kan_bemanne_plass(user, ressurs, vp)
               for vp in ressurs.vaktposter.all() if not vp.alle_korps)


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
#: oppdragsmodulen og sletting.» Tidene er vaktas rammer for én plass, og
#: reservasjonen og «åpen for alle» er å dele ut — de to sto her fra før, bare
#: skrevet som hver sin `if` ute i viewet.
#:
#: **`merknad` sto her ett døgn, og André tok den ut igjen** (16. sep. 2026).
#: Jeg leste «det eneste» strengt og låste den sammen med tidene. Det var feil
#: sted å trekke grensen: merknaden er en beskjed om *denne raden* — «kommer
#: 17:30», «kjører selv» — og den som setter personen på plassen er den som
#: vet det. Den følger derfor samme port som person og rolle,
#: `kan_rore_vaktpost`, og hun når bare de radene som er hennes.
#:
#: **`probono` ble stående**, og det er et annet spørsmål: det sier hva vakta
#: *koster*, og tallet leses av budsjettlinja for hele lista. Den som fører
#: sitt eget korps skal ikke kunne flytte totalen for alle.
#:
#: **`antall` er med fordi opprettelsen tar den:** én forespørsel kunne lage
#: femti tomme plasser, og å sette opp behovet er nettopp det korps-føreren
#: ikke skal gjøre.
SKIFT_OPPSETTFELTER = ('fra_tid', 'til_tid', 'korps_id', 'alle_korps',
                       'probono', 'antall')

#: Det samme på en ressurs, for `kan_lede`. **Navnet står bevisst ikke her:**
#: det er det ene korps-føreren skal kunne rette.
RESSURS_OPPSETTFELTER = ('gruppe_id', 'enhet_id', 'rekkefolge')

#: **Reservasjonen på enheten er utdeling, og krever det samme som på plassen**
#: — `kan_sette_opp_skift` (André, 30. sep. 2026: «de kan begge ha likt»). Den
#: sto i lista over til da, altså `skriv_leder`, mens nedtrekket på plassen var
#: `skriv_full` — og tabellen øverst i `views.py` sa `skriv_full` for begge.
RESSURS_UTDELINGSFELTER = ('korps_id',)


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
